"""SolidWorks-style drawings on top of TechDraw (ANSI sheets, decimal inches).

  * Make Drawing from Part - picks an ANSI sheet and a standard scale, places the
    Front / Top / Right views (third angle) and an isometric view, fills the title block;
  * Auto Dimension - overall sizes plus a diameter/radius for every distinct circle;
  * Hole Callout - "2X ⌀.250 THRU" style callouts on the circles you pick;
  * Title Block - edit the fields, scale and weight are kept up to date;
  * Save as PDF.
All positions on a page are in mm, Y up, measured from the lower-left corner.
"""
import datetime
import getpass
import math
import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from solidstyle import commands
from solidstyle.commands import icon

PARAMS = "User parameter:BaseApp/Preferences/Mod/SolidStyle"
INCH = "Imperial decimal (in, lb)"
FMT = "%.3f"     # .XXX - holes and other precise sizes
FMT2 = "%.2f"    # .XX  - overall sizes and radii (general tolerance ±.01)
GENERAL_NOTES = [
    "NOTES:",
    "1. DIMENSIONING AND TOLERANCING PER ASME Y14.5-2018.",
    "2. DIMENSIONS ARE IN INCHES.",
    "3. UNLESS OTHERWISE SPECIFIED:  .XX ±.01   .XXX ±.005   ANGLES ±0.5°",
    "4. BREAK SHARP EDGES .005-.015.",
]
GAP = 22.0      # space between views, mm on the page
MARGIN = 20.0   # the ASME sheets have their inner border about 20 mm in
DIM_ROOM = 16.0 # left of the Front/Top views and right of the Right view: dimensions, datums

# size, template, width, height, title block left edge, title block height (mm)
SHEETS = [
    ("A", "ANSIA_Landscape.svg", 279.4, 215.9, 128.0, 66.0),
    ("B", "ANSIB_Landscape.svg", 431.8, 279.4, 280.0, 72.0),
    ("C", "ANSIC_Landscape.svg", 558.8, 431.8, 385.0, 72.0),
    ("D", "ANSID_Landscape.svg", 863.6, 558.8, 680.0, 76.0),
    ("E", "ANSIE_Landscape.svg", 1117.6, 863.6, 930.0, 86.0),
]
SCALES = [10, 5, 4, 2, 1, 1 / 2, 1 / 4, 1 / 5, 1 / 8, 1 / 10, 1 / 16, 1 / 20, 1 / 50, 1 / 100]
MIN_SCALE_ON_A = 1 / 4  # smaller than this on an A sheet -> go to a bigger sheet

# Title block fields differ between the ASME templates: first name found wins.
FIELDS = {
    "title": ["DrawingTitle1", "Title", "TITLE"],
    "subtitle": ["DrawingTitle2", "Subtitle", "SUBTITLE"],
    "material": ["DrawingTitle3"],
    "number": ["drawing_number", "NUMBER"],
    "rev": ["revision_index"],
    "drawn": ["DrawnBy", "AuthorName", "AUTHOR NAME"],
    "date": ["CreationDate", "CREATION DATE"],
    "scale": ["scale"],
    "weight": ["Weight", "WEIGHT"],
    "sheet": ["Sheet", "SheetNumber", "SHEET"],
    "company": ["CompanyName", "Company_name"],
}

ISO_DIR = App.Vector(1, -1, 1).normalize()
ISO_X = App.Vector(1, 1, 0).normalize()


# ======================================================================
# Helpers
# ======================================================================

def template_path(name):
    return os.path.join(App.getResourceDir(), "Mod", "TechDraw", "Templates", "ASME", name)


def scale_text(s):
    if s >= 1:
        return "%g:1" % round(s, 3)
    return "1:%g" % round(1 / s, 3)


def inch(mm):
    return _ansi(mm / 25.4)


def part_to_draw():
    """Selected body/solid, else the active body, else the first visible body."""
    for o in Gui.Selection.getSelection():
        if hasattr(o, "Shape") and o.Shape.Solids and not o.TypeId.startswith("TechDraw"):
            return o
    try:
        body = Gui.ActiveDocument.ActiveView.getActiveObject("pdbody")
        if body:
            return body
    except Exception:
        pass
    doc = App.ActiveDocument
    for o in doc.Objects:
        if o.isDerivedFrom("PartDesign::Body") and o.Visibility and o.Shape.Solids:
            return o
    for o in doc.Objects:
        if hasattr(o, "Shape") and o.Visibility and not o.InList and o.Shape.Solids:
            return o
    return None


def active_page():
    """Page shown in the active window, else the selected page, else the only page."""
    try:
        mdi = Gui.getMainWindow().centralWidget().activeSubWindow()
        if mdi and "Page" in mdi.windowTitle():
            for o in App.ActiveDocument.Objects:
                if o.isDerivedFrom("TechDraw::DrawPage") and o.Label in mdi.windowTitle():
                    return o
    except Exception:
        pass
    for o in Gui.Selection.getSelection():
        if o.isDerivedFrom("TechDraw::DrawPage"):
            return o
        for p in o.InList:
            if p.isDerivedFrom("TechDraw::DrawPage"):
                return p
    pages = [o for o in App.ActiveDocument.Objects if o.isDerivedFrom("TechDraw::DrawPage")]
    return pages[0] if len(pages) == 1 else (pages[-1] if pages else None)


def page_of(view):
    for p in view.InList:
        if p.isDerivedFrom("TechDraw::DrawPage"):
            return p
        if p.isDerivedFrom("TechDraw::DrawProjGroup"):
            return page_of(p)
    return None


def part_views(page):
    out = []
    for v in page.Views:
        if v.isDerivedFrom("TechDraw::DrawProjGroup"):
            out.extend(v.Views)
        elif v.isDerivedFrom("TechDraw::DrawViewPart"):
            out.append(v)
    return out


def page_views_by_role(page):
    """{"Front": view, "Top": ..., "Right": ..., "Isometric": ...} - from Make Drawing's
    ViewRole, or from a projection group made with Standard 3 View."""
    out = {}
    for v in page.Views:
        if v.isDerivedFrom("TechDraw::DrawProjGroup"):
            for item in v.Views:
                out.setdefault(item.Type, item)
        elif getattr(v, "ViewRole", ""):
            out.setdefault(v.ViewRole, v)
    return out


def wait_for_views(page, timeout=60.0):
    """TechDraw computes view geometry in the background: wait until every view has edges."""
    import time
    end = time.time() + timeout
    while time.time() < end:
        try:
            if all(v.getVisibleEdges() for v in part_views(page)):
                QtWidgets.QApplication.processEvents()
                return True
        except Exception:
            pass
        QtWidgets.QApplication.processEvents()
        time.sleep(0.05)
    return False


def view_center(view):
    """Page position of a view's centre (projection group items are relative to the group)."""
    x, y = view.X.Value, view.Y.Value
    for p in view.InList:  # the anchor view lists its group twice
        if p.isDerivedFrom("TechDraw::DrawProjGroup"):
            return x + p.X.Value, y + p.Y.Value
    return x, y


def view_scale(view):
    for p in view.InList:
        if p.isDerivedFrom("TechDraw::DrawProjGroup"):
            return p.Scale
    return view.Scale


def _extent(shape, direction, xdir):
    """Width/height of the shape's bounding box seen along direction (model mm)."""
    ydir = direction.cross(xdir).normalize()
    bb = shape.BoundBox
    us, vs = [], []
    for x in (bb.XMin, bb.XMax):
        for y in (bb.YMin, bb.YMax):
            for z in (bb.ZMin, bb.ZMax):
                p = App.Vector(x, y, z)
                us.append(p.dot(xdir))
                vs.append(p.dot(ydir))
    return max(us) - min(us), max(vs) - min(vs)


# ======================================================================
# Make Drawing from Part
# ======================================================================

def choose_layout(shape, size=None):
    """(sheet, scale) - the biggest standard scale that fits; bigger sheets for big parts."""
    bb = shape.BoundBox
    X, Y, Z = bb.XLength, bb.YLength, bb.ZLength
    iw, ih = _extent(shape, ISO_DIR, ISO_X)
    sheets = [s for s in SHEETS if s[0] == size] if size else SHEETS
    best = None
    for sheet in sheets:
        _n, _t, W, H, _tbx, tbh = sheet
        aw = W - 2 * MARGIN
        ah = H - MARGIN - tbh - GAP / 2
        for s in SCALES:
            if (X + Y + iw) * s + GAP + 2 * DIM_ROOM <= aw and (Z + Y) * s + GAP <= ah and ih * s <= ah:
                best = (sheet, s)
                break
        if best and (size or best[1] >= MIN_SCALE_ON_A):
            return best
    return best or (sheets[-1], SCALES[-1])


def make_drawing(part, size=None, scale=None, title=None, gap=GAP, notes=True):
    doc = part.Document
    doc.UnitSystem = INCH
    sheet, auto_scale = choose_layout(part.Shape, size)
    s = scale or auto_scale
    name, tpl_file, W, H, _tbx, tbh = sheet

    page = doc.addObject("TechDraw::DrawPage", "Drawing")
    page.Label = "%s Drawing" % part.Label
    tpl = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
    page.Template = tpl
    tpl.Template = template_path(tpl_file)
    page.ProjectionType = "Third angle"
    page.Scale = s
    page.KeepUpdated = True

    # Layout: the 3-view group above the title block on the left, the isometric on the right.
    bb = part.Shape.BoundBox
    X, Y, Z = bb.XLength * s, bb.YLength * s, bb.ZLength * s
    iw, ih = [d * s for d in _extent(part.Shape, ISO_DIR, ISO_X)]
    bottom, top = tbh + gap / 2, H - MARGIN
    gw, gh = X + gap + Y, Z + gap + Y
    # left to right: dimension room, Front, gap, Right, dimension room, isometric (right-aligned)
    free_w = max((W - 2 * MARGIN) - 2 * DIM_ROOM - gw - iw, 0)
    left = MARGIN + DIM_ROOM + free_w / 3
    gx = left + X / 2
    gy = bottom + max(top - bottom - gh, 0) / 2 + Z / 2

    # Front, Top and Right as separate views placed in third-angle positions (a projection
    # group made from Python is drawn at the page origin by FreeCAD 1.1).
    for role, direction, xdir, x, y in (
            ("Front", App.Vector(0, -1, 0), App.Vector(1, 0, 0), gx, gy),
            ("Top", App.Vector(0, 0, 1), App.Vector(1, 0, 0), gx, gy + Z / 2 + gap + Y / 2),
            ("Right", App.Vector(1, 0, 0), App.Vector(0, 1, 0), gx + X / 2 + gap + Y / 2, gy)):
        v = doc.addObject("TechDraw::DrawViewPart", role)
        v.addProperty("App::PropertyString", "ViewRole", "SolidStyle", "Front, Top, Right or Isometric")
        v.ViewRole = role
        v.Source = [part]
        v.Direction = direction
        v.XDirection = xdir
        v.ScaleType = "Custom"
        v.Scale = s
        v.HardHidden = True       # hidden lines dashed in the orthographic views
        v.SmoothVisible = False
        page.addView(v)         # addView centres the view on the page: position it afterwards
        v.X = x
        v.Y = y

    iso = doc.addObject("TechDraw::DrawViewPart", "Isometric")
    iso.Source = [part]
    iso.Direction = ISO_DIR
    iso.XDirection = ISO_X
    iso.ScaleType = "Custom"
    iso.Scale = s
    iso.addProperty("App::PropertyString", "ViewRole", "SolidStyle", "Front, Top, Right or Isometric")
    iso.ViewRole = "Isometric"
    page.addView(iso)
    iso.X = W - MARGIN - iw / 2 - free_w / 3
    iso.Y = min(max(gy + Z / 2 + gap / 2, bottom + ih / 2), top - ih / 2)

    doc.recompute()
    fill_title_block(page, part, reset=True, title=title)
    if notes:
        add_notes(page)
    doc.recompute()
    return page


# ======================================================================
# Title block
# ======================================================================

def _author():
    a = App.ParamGet("User parameter:BaseApp/Preferences/Document").GetString("prefAuthor", "")
    if a:
        return a
    try:
        return getpass.getuser()
    except Exception:
        return ""


def _weight(part):
    rho = App.ParamGet(PARAMS).GetFloat("Density", 0.0)  # g/cm³, set in Mass Properties
    if rho <= 0:
        return ""
    grams = part.Shape.Volume * rho / 1000.0
    return "%.2f lb" % (grams / 453.59237)


def source_part(page):
    for v in page.Views:
        src = getattr(v, "Source", None)
        if src:
            return src[0]
    return None


def title_values(page, part, title=None):
    tpl = page.Template
    texts = dict(tpl.EditableTexts)
    return {
        "title": (title or part.Label).upper(),
        "number": part.Label.upper().replace(" ", "-"),
        "rev": "A",
        "drawn": _author(),
        "date": datetime.date.today().strftime("%m/%d/%y"),
        "scale": scale_text(page.Scale),
        "weight": _weight(part),
        "sheet": "1 OF 1" if "Sheet" in texts else "1/1",
        "company": App.ParamGet(PARAMS).GetString("Company", ""),
        "subtitle": "",
        "material": "",
    }


def field_name(texts, key):
    for n in FIELDS.get(key, []):
        if n in texts:
            return n
    return None


def fill_title_block(page, part, reset=False, title=None, values=None):
    """reset: clear the template's sample texts and fill everything; otherwise only
    refresh the automatic fields (scale, weight)."""
    tpl = page.Template
    texts = dict(tpl.EditableTexts)
    vals = title_values(page, part, title)
    if values:
        vals.update(values)
    if reset:
        texts = {k: "" for k in texts}
        keys = vals.keys()
    else:
        keys = ["scale", "weight"]
    for key in keys:
        n = field_name(texts, key)
        if n is not None and (vals.get(key) or reset):
            texts[n] = vals[key]
    if texts != dict(tpl.EditableTexts):
        tpl.EditableTexts = texts


# ======================================================================
# Auto Dimension / Hole Callout
# ======================================================================

def view_edge(view, name):
    """Edge 'EdgeN' of a view in page mm about the view centre, Y up.
    (getEdgeByIndex/getEdgeBySelection give model size with Y up; getVisibleEdges gives page
    size with Y down - only the former is used here.)"""
    e = view.getEdgeByIndex(int(name[4:])).copy()
    e.scale(view_scale(view), App.Vector(0, 0, 0))
    return e


def view_edges(view):
    """[(name, edge, visible)] for every edge of a view. The visible edges come first."""
    n_vis = len(view.getVisibleEdges())
    out = []
    i = 0
    while True:
        try:
            e = view.getEdgeByIndex(i)
        except Exception:
            break
        if e is None:
            break
        out.append(("Edge%d" % i, view_edge(view, "Edge%d" % i), i < n_vis))
        i += 1
    return out


def _is_circle(e):
    return type(e.Curve).__name__ == "Circle"


def _add_dim(view, kind, refs, x, y, fmt=FMT):
    doc = view.Document
    dim = doc.addObject("TechDraw::DrawViewDimension", "Dimension")
    dim.Type = kind
    dim.MeasureType = "Projected"
    page_of(view).addView(dim)
    dim.References2D = [(view, r) for r in refs]
    dim.Type = kind
    dim.FormatSpec = fmt
    dim.X = x
    dim.Y = y
    return dim


def add_dimension(view, kind, refs, x, y, fmt=FMT):
    """Dimension between edges/vertices of a view ("Edge3", "Vertex7"); x, y: text position
    relative to the view centre, page mm, Y up."""
    return _add_dim(view, kind, refs, x, y, fmt)


def _ansi(v):
    """.002, 1.250 - inch values below one without the leading zero (ASME Y14.5)."""
    t = "%.3f" % v
    return t[1:] if t.startswith("0.") else t


def set_tolerance(dim, plus, minus=None):
    """Size tolerance in inches: ±plus, or +plus/-minus.
    ±tolerances are written right after the size (so a hole callout reads ⌀.500 ±.002 ↧.750)."""
    import re
    if minus is None or abs(minus - plus) < 1e-9:
        dim.FormatSpec = re.sub(r"%[-+ #0]*\d*(?:\.\d+)?[fgw]",
                                lambda m: m.group(0) + " ±" + _ansi(plus), dim.FormatSpec, count=1)
    else:
        dim.EqualTolerance = False
        dim.FormatSpecOverTolerance = "%+.3f"
        dim.FormatSpecUnderTolerance = "%+.3f"
        dim.OverTolerance = plus * 25.4
        dim.UnderTolerance = -minus * 25.4


def view_vertices(view):
    """[(name, point)] for every vertex of a view, page mm about the view centre, Y up.
    Circle centres are included."""
    s = view_scale(view)
    out = []
    i = 0
    while True:
        try:
            v = view.getVertexByIndex(i)
        except Exception:
            break
        if v is None:
            break
        out.append(("Vertex%d" % i, App.Vector(v.Point.x * s, v.Point.y * s, 0)))
        i += 1
    return out


def vertex_at(view, x, y, tol=0.05):
    """Name of the vertex at (x, y) - page mm about the view centre - or None."""
    best = None
    for name, p in view_vertices(view):
        d = math.hypot(p.x - x, p.y - y)
        if d <= tol and (best is None or d < best[1]):
            best = (name, d)
    return best[0] if best else None


def add_notes(page, lines=None):
    """General notes (standard tolerances etc.) in the empty corner left of the title block."""
    lines = lines or GENERAL_NOTES
    tpl = page.Template
    W = tpl.Width.Value
    sheet = next((s for s in SHEETS if abs(s[2] - W) < 1), SHEETS[0])
    room = sheet[4] - MARGIN - 10
    size = min(3.5, room / (max(len(t) for t in lines) * 0.62))
    note = page.Document.addObject("TechDraw::DrawViewAnnotation", "Notes")
    note.Label = "General Notes"
    note.Text = lines
    note.TextSize = size
    note.Font = "osifont"
    page.addView(note)
    width = max(len(t) for t in lines) * size * 0.62
    height = len(lines) * size * 2.3   # osifont line pitch
    note.X = MARGIN + 6 + width / 2
    note.Y = MARGIN + 6 + height / 2
    return note


def view_circles(view):
    """[(edge name, edge, full)] - one entry per circle seen in a view. TechDraw often splits
    a circle into arcs; arcs of the same circle are merged (the longest piece is named)."""
    groups = {}
    for name, e, vis in view_edges(view):
        if not vis or not _is_circle(e):
            continue
        c, r = e.Curve.Center, e.Curve.Radius
        key = (round(c.x, 3), round(c.y, 3), round(r, 3))
        span = 2 * math.pi if e.isClosed() else abs(e.LastParameter - e.FirstParameter)
        g = groups.setdefault(key, [name, e, 0.0])
        g[2] += span
        if e.Length > g[1].Length:
            g[0], g[1] = name, e
    return [(n, e, span >= 2 * math.pi - 1e-3) for n, e, span in groups.values()]


def hole_text(view, edge):
    """'2X ⌀%.3f THRU' or '⌀%.3f ↧.500' for a circle in a view."""
    s = view_scale(view)
    r_page = edge.Curve.Radius
    n = sum(1 for _n, e, full in view_circles(view) if full and abs(e.Curve.Radius - r_page) < 1e-4)
    depth = _hole_depth(view, r_page / s)
    text = "\u2300" + FMT
    if depth == "THRU":
        text += " THRU"
    elif depth:
        text += " \u21a7" + inch(depth)
    if n > 1:
        text = "%dX " % n + text
    return text


def _hole_depth(view, radius):
    """'THRU', a depth in mm, or None - from the cylinder of this radius along the view direction."""
    src = view.Source[0] if view.Source else None
    if src is None:
        return None
    shape = src.Shape
    d = view.Direction
    lo, hi = [], []
    for f in shape.Faces:
        srf = f.Surface
        if type(srf).__name__ != "Cylinder" or abs(srf.Radius - radius) > 1e-3:
            continue
        if abs(abs(srf.Axis.normalize().dot(d)) - 1) > 1e-6:
            continue
        ps = [v.Point.dot(d) for v in f.Vertexes]
        lo.append(min(ps))
        hi.append(max(ps))
    if not lo:
        return None
    span = max(hi) - min(lo)
    full = max(v.Point.dot(d) for v in shape.Vertexes) - min(v.Point.dot(d) for v in shape.Vertexes)
    return "THRU" if span >= full - 1e-3 else span


def auto_dimension(page):
    """Overall sizes on the Front and Top views and one diameter/radius per distinct circle."""
    wait_for_views(page)
    views = page_views_by_role(page)
    if not views:
        return []
    made = []
    front, top, right = views.get("Front"), views.get("Top"), views.get("Right")
    # width under the Front view, height right of the Right view, depth left of the Top view:
    # keeps the edges where datum symbols usually go free
    if front:
        made += _overall(front, horizontal=True, vertical=right is None)
    if right:
        made += _overall(right, horizontal=False, vertical=True, right=True)
    if top:
        made += _overall(top, horizontal=False, vertical=True)
    done = set()
    for v in (top, front, right):
        if v is None:
            continue
        s = view_scale(v)
        vis = [e.BoundBox for _n, e, seen in view_edges(v) if seen]
        right_edge = max(b.XMax for b in vis) if vis else 0
        for name, e, full in view_circles(v):
            key = round(e.Curve.Radius / s, 2)
            if key in done:
                continue
            done.add(key)
            c, r = e.Curve.Center, e.Curve.Radius
            if full:   # text out to the right of the view, a little above the centre
                dim = _add_dim(v, "Diameter", [name], max(c.x + r, right_edge) + 14, c.y + r * 0.4 + 4,
                               hole_text(v, e))
            else:      # radii down and to the right, so they don't meet the diameters
                dim = _add_dim(v, "Radius", [name], c.x + r * 0.75 + 14, c.y - r * 0.75 - 14, "R" + FMT2)
            made.append(dim)
    page.Document.recompute()
    return made


def _overall(view, horizontal, vertical, right=False):
    """Overall width/height of a view as TechDraw extent dimensions (they follow the model)."""
    import TechDraw
    edges = [e for _n, e, vis in view_edges(view) if vis]
    if not edges:
        return []
    xmin = min(e.BoundBox.XMin for e in edges)
    xmax = max(e.BoundBox.XMax for e in edges)
    ymin = min(e.BoundBox.YMin for e in edges)
    doc = view.Document
    out = []
    vx = xmax + 10 if right else xmin - 10
    for direction, wanted, x, y in ((0, horizontal, 0, ymin - 10), (1, vertical, vx, 0)):
        if not wanted:
            continue
        before = {o.Name for o in doc.Objects}
        TechDraw.makeExtentDim(view, [], direction)
        for d in doc.Objects:
            if d.Name not in before and d.isDerivedFrom("TechDraw::DrawViewDimension"):
                d.FormatSpec = FMT2
                d.X = x
                d.Y = y
                out.append(d)
    return out


def selected_view_edges(types=("Circle",)):
    out = []
    for sel in Gui.Selection.getSelectionEx():
        o = sel.Object
        if not o.isDerivedFrom("TechDraw::DrawViewPart"):
            continue
        for sub in sel.SubElementNames:
            if sub.startswith("Edge"):
                e = view_edge(o, sub)
                if type(e.Curve).__name__ in types:
                    out.append((o, sub, e))
    return out


# ======================================================================
# PDF
# ======================================================================

def save_pdf(page, path=None):
    import TechDrawGui
    if path is None:
        doc = page.Document
        folder = os.path.dirname(doc.FileName) if doc.FileName else os.path.expanduser("~")
        path = os.path.join(folder, page.Label + ".pdf")
    TechDrawGui.exportPageAsPdf(page, path)
    return path


# ======================================================================
# Commands
# ======================================================================

def _status(msg):
    from solidstyle import features
    features.status(msg)


def _show(page):
    try:
        page.ViewObject.doubleClicked()
    except Exception:
        pass
    from solidstyle import ui
    ui.select_tab("Drawing")


class MakeDrawing(commands._Cmd):
    pixmap = icon("MakeDrawing")
    menu = "Make Drawing from Part"
    tip = ("New ANSI drawing of the selected part (or the active body): Front, Top, Right and Isometric "
           "views, scale and sheet size picked to fit, title block filled in, inch units")

    def Activated(self):
        part = part_to_draw()
        if part is None:
            from solidstyle import features
            features.warn("Make Drawing", "Select a part or body to draw.")
            return
        dlg = MakeDrawingDialog(part)
        if not dlg.exec_():
            return
        App.ActiveDocument.openTransaction("Make Drawing")
        page = make_drawing(part, dlg.size(), dlg.scale(), dlg.title.text(), notes=dlg.notes.isChecked())
        if dlg.dims.isChecked():
            auto_dimension(page)
        App.ActiveDocument.commitTransaction()
        _show(page)
        _status("%s: %s sheet, scale %s" % (page.Label, dlg.size() or "", scale_text(page.Scale)))


class MakeDrawingDialog(QtWidgets.QDialog):
    def __init__(self, part):
        super().__init__(Gui.getMainWindow())
        self.setWindowTitle("Make Drawing from Part")
        sheet, s = choose_layout(part.Shape)
        lay = QtWidgets.QFormLayout(self)
        lay.addRow(QtWidgets.QLabel("<b>%s</b>" % part.Label))
        self.title = QtWidgets.QLineEdit(part.Label.upper())
        lay.addRow("Title:", self.title)
        self.sheet = QtWidgets.QComboBox()
        for sh in SHEETS:
            self.sheet.addItem('ANSI %s  (%g" x %g")' % (sh[0], sh[2] / 25.4, sh[3] / 25.4), sh[0])
        self.sheet.setCurrentIndex([sh[0] for sh in SHEETS].index(sheet[0]))
        lay.addRow("Sheet:", self.sheet)
        self.scale_box = QtWidgets.QComboBox()
        for v in SCALES:
            self.scale_box.addItem(scale_text(v), v)
        self.scale_box.setCurrentIndex(SCALES.index(s))
        lay.addRow("Scale:", self.scale_box)
        self.sheet.currentIndexChanged.connect(lambda _i: self._refit(part))
        self.dims = QtWidgets.QCheckBox("Auto dimension (overall sizes, holes and radii)")
        self.dims.setChecked(True)
        lay.addRow(self.dims)
        self.notes = QtWidgets.QCheckBox("General notes (ASME Y14.5, .XX ±.01, .XXX ±.005, angles ±0.5°)")
        self.notes.setChecked(True)
        lay.addRow(self.notes)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addRow(bb)

    def _refit(self, part):
        _sheet, s = choose_layout(part.Shape, self.size())
        self.scale_box.setCurrentIndex(SCALES.index(s))

    def size(self):
        return self.sheet.currentData()

    def scale(self):
        return self.scale_box.currentData()


class AutoDimension(commands._Cmd):
    pixmap = icon("AutoDimension")
    menu = "Auto Dimension"
    tip = "Overall sizes on the Front and Top views, plus a diameter or radius for every distinct circle"

    def IsActive(self):
        return commands.has_doc() and active_page() is not None

    def Activated(self):
        page = active_page()
        App.ActiveDocument.openTransaction("Auto Dimension")
        made = auto_dimension(page)
        App.ActiveDocument.commitTransaction()
        _status("Auto Dimension: %d dimensions added" % len(made))


class HoleCallout(commands._Cmd):
    pixmap = icon("HoleCallout")
    menu = "Hole Callout"
    tip = "Pick circular edges in a drawing view: adds '2X ⌀.250 THRU' style callouts (count and depth from the model)"

    def Activated(self):
        picks = selected_view_edges()
        if not picks:
            from solidstyle import features
            features.warn("Hole Callout", "Select one or more hole edges (circles) in a drawing view first.")
            return
        App.ActiveDocument.openTransaction("Hole Callout")
        for view, sub, e in picks:
            c, r = e.Curve.Center, e.Curve.Radius
            off = r * 0.7 + 8
            _add_dim(view, "Diameter", [sub], c.x + off, c.y + off, hole_text(view, e))
        App.ActiveDocument.commitTransaction()
        App.ActiveDocument.recompute()


class TitleBlock(commands._Cmd):
    pixmap = icon("TitleBlock")
    menu = "Title Block"
    tip = "Edit the title block of the current drawing (scale and weight are filled in automatically)"

    def IsActive(self):
        return commands.has_doc() and active_page() is not None

    def Activated(self):
        page = active_page()
        TitleBlockDialog(page).exec_()


class TitleBlockDialog(QtWidgets.QDialog):
    LABELS = [("title", "Title"), ("subtitle", "Subtitle"), ("material", "Material"),
              ("number", "Drawing number"), ("rev", "Revision"), ("drawn", "Drawn by"),
              ("date", "Date"), ("company", "Company"), ("sheet", "Sheet"),
              ("scale", "Scale"), ("weight", "Weight")]

    def __init__(self, page):
        super().__init__(Gui.getMainWindow())
        self.setWindowTitle("Title Block - %s" % page.Label)
        self.page = page
        self.texts = dict(page.Template.EditableTexts)
        part = source_part(page)
        auto = title_values(page, part) if part else {}
        lay = QtWidgets.QFormLayout(self)
        self.edits = {}
        for key, label in self.LABELS:
            n = field_name(self.texts, key)
            if n is None:
                continue
            e = QtWidgets.QLineEdit(self.texts[n])
            if key in ("scale", "weight") and auto.get(key):
                e.setPlaceholderText(auto[key])
            self.edits[n] = e
            lay.addRow(label + ":", e)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addRow(bb)

    def accept(self):
        texts = dict(self.texts)
        for n, e in self.edits.items():
            texts[n] = e.text()
        self.page.Template.EditableTexts = texts
        n = field_name(texts, "company")
        if n in self.edits:  # remembered for the next drawing
            App.ParamGet(PARAMS).SetString("Company", self.edits[n].text())
        super().accept()


class SaveAsPDF(commands._Cmd):
    pixmap = icon("SavePDF")
    menu = "Save as PDF"
    tip = "Save the current drawing sheet as a PDF"

    def IsActive(self):
        return commands.has_doc() and active_page() is not None

    def Activated(self):
        page = active_page()
        doc = page.Document
        folder = os.path.dirname(doc.FileName) if doc.FileName else os.path.expanduser("~")
        path, _f = QtWidgets.QFileDialog.getSaveFileName(
            Gui.getMainWindow(), "Save as PDF", os.path.join(folder, page.Label + ".pdf"), "PDF (*.pdf)")
        if path:
            save_pdf(page, path)
            _status("Saved %s" % path)


def register():
    for name, cls in [("SS_MakeDrawing", MakeDrawing), ("SS_AutoDimension", AutoDimension),
                      ("SS_HoleCallout", HoleCallout), ("SS_TitleBlock", TitleBlock),
                      ("SS_SaveAsPDF", SaveAsPDF)]:
        Gui.addCommand(name, cls())


def update_title_blocks(doc):
    """Keep scale and weight current (called after a recompute)."""
    for page in doc.Objects:
        if page.isDerivedFrom("TechDraw::DrawPage") and page.Template:
            part = source_part(page)
            if part is not None and hasattr(part, "Shape"):
                try:
                    fill_title_block(page, part)
                except Exception:
                    pass
