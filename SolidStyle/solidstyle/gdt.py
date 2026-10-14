"""GD&T for drawings (ASME Y14.5): feature control frames, datum feature symbols and
basic dimensions.

Frames and datum symbols are TechDraw symbols (SVG, drawn here in mm), so they print
and export like the rest of the sheet. The characteristic symbols are drawn as lines,
not font glyphs, so they look the same on every machine.
"""
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from solidstyle import commands, drawing
from solidstyle.commands import icon

TH = 3.2         # text height, mm (about .12 in)
H = 7.0          # frame height
LW = 0.35        # line width
FONT = "osifont, Arial, sans-serif"

# key, name, datums: "no" (form), "opt" (profile), "yes"
CHARACTERISTICS = [
    ("position", "Position", "yes"),
    ("flatness", "Flatness", "no"),
    ("straightness", "Straightness", "no"),
    ("circularity", "Circularity", "no"),
    ("cylindricity", "Cylindricity", "no"),
    ("profile_surface", "Profile of a Surface", "opt"),
    ("profile_line", "Profile of a Line", "opt"),
    ("perpendicularity", "Perpendicularity", "yes"),
    ("parallelism", "Parallelism", "yes"),
    ("angularity", "Angularity", "yes"),
    ("circular_runout", "Circular Runout", "yes"),
    ("total_runout", "Total Runout", "yes"),
    ("concentricity", "Concentricity", "yes"),
    ("symmetry", "Symmetry", "yes"),
]
NAMES = {k: n for k, n, _d in CHARACTERISTICS}
DATUMS = {k: d for k, _n, d in CHARACTERISTICS}
MODIFIERS = [("", "None (RFS)"), ("M", "Maximum material (MMC)"), ("L", "Least material (LMC)")]


# ======================================================================
# SVG pieces (SVG coordinates: mm, Y down)
# ======================================================================

def _line(x1, y1, x2, y2, w=LW):
    return ('<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f" stroke="#000" stroke-width="%g" '
            'stroke-linecap="round"/>' % (x1, y1, x2, y2, w))


def _circle(cx, cy, r, w=LW, fill="none"):
    return '<circle cx="%.3f" cy="%.3f" r="%.3f" fill="%s" stroke="#000" stroke-width="%g"/>' % (
        cx, cy, r, fill, w)


def _poly(pts, fill="none", close=True):
    d = "M " + " L ".join("%.3f %.3f" % p for p in pts) + (" Z" if close else "")
    return '<path d="%s" fill="%s" stroke="#000" stroke-width="%g" stroke-linejoin="round"/>' % (d, fill, LW)


def _text(x, y, s, size=TH, anchor="middle"):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return ('<text x="%.3f" y="%.3f" font-family="%s" font-size="%g" text-anchor="%s" '
            'fill="#000" stroke="none">%s</text>' % (x, y, FONT, size, anchor, s))


def _arrow(x1, y1, x2, y2, head=1.4):
    """Line from (x1,y1) to (x2,y2) with a filled arrowhead at the end."""
    import math
    a = math.atan2(y2 - y1, x2 - x1)
    bx, by = x2 - head * math.cos(a), y2 - head * math.sin(a)
    px, py = -math.sin(a) * head * 0.33, math.cos(a) * head * 0.33
    return _line(x1, y1, bx, by) + _poly([(x2, y2), (bx + px, by + py), (bx - px, by - py)], fill="#000")


def symbol(key, cx, cy, s):
    """The geometric characteristic symbol, s mm tall, centred on (cx, cy)."""
    h = s / 2
    if key == "straightness":
        return _line(cx - h, cy, cx + h, cy)
    if key == "flatness":
        return _poly([(cx - h, cy + h * 0.45), (cx + h * 0.5, cy + h * 0.45),
                      (cx + h, cy - h * 0.45), (cx - h * 0.5, cy - h * 0.45)])
    if key == "circularity":
        return _circle(cx, cy, h * 0.8)
    if key == "cylindricity":
        return (_circle(cx, cy, h * 0.55) + _line(cx - h * 0.95, cy + h * 0.9, cx - h * 0.15, cy - h * 0.9)
                + _line(cx + h * 0.15, cy + h * 0.9, cx + h * 0.95, cy - h * 0.9))
    if key == "profile_line":
        return '<path d="M %.3f %.3f A %.3f %.3f 0 0 1 %.3f %.3f" fill="none" stroke="#000" stroke-width="%g"/>' % (
            cx - h, cy + h * 0.45, h, h, cx + h, cy + h * 0.45, LW)
    if key == "profile_surface":
        return '<path d="M %.3f %.3f A %.3f %.3f 0 0 1 %.3f %.3f Z" fill="none" stroke="#000" stroke-width="%g"/>' % (
            cx - h, cy + h * 0.45, h, h, cx + h, cy + h * 0.45, LW)
    if key == "perpendicularity":
        return _line(cx, cy - h, cx, cy + h * 0.8) + _line(cx - h, cy + h * 0.8, cx + h, cy + h * 0.8)
    if key == "parallelism":
        return (_line(cx - h * 0.85, cy + h, cx - h * 0.25, cy - h)
                + _line(cx + h * 0.25, cy + h, cx + h * 0.85, cy - h))
    if key == "angularity":
        return _line(cx - h, cy + h * 0.8, cx + h, cy + h * 0.8) + _line(cx - h, cy + h * 0.8, cx + h * 0.75, cy - h * 0.9)
    if key == "position":
        return _circle(cx, cy, h * 0.6) + _line(cx - h, cy, cx + h, cy) + _line(cx, cy - h, cx, cy + h)
    if key == "concentricity":
        return _circle(cx, cy, h * 0.4) + _circle(cx, cy, h * 0.85)
    if key == "symmetry":
        return (_line(cx - h, cy, cx + h, cy) + _line(cx - h * 0.55, cy - h * 0.55, cx + h * 0.55, cy - h * 0.55)
                + _line(cx - h * 0.55, cy + h * 0.55, cx + h * 0.55, cy + h * 0.55))
    if key == "circular_runout":
        return _arrow(cx - h * 0.7, cy + h * 0.9, cx + h * 0.7, cy - h * 0.9)
    if key == "total_runout":
        return (_line(cx - h, cy + h * 0.9, cx + h * 0.3, cy + h * 0.9)
                + _arrow(cx - h, cy + h * 0.9, cx - h * 0.1, cy - h * 0.9)
                + _arrow(cx - h * 0.2, cy + h * 0.9, cx + h * 0.7, cy - h * 0.9))
    return ""


def _diameter(cx, cy, s=TH):
    r = s * 0.36
    return _circle(cx, cy, r) + _line(cx - r * 1.1, cy + r * 1.5, cx + r * 1.1, cy - r * 1.5)


def _modifier(cx, cy, letter):
    r = TH * 0.62
    return _circle(cx, cy, r) + _text(cx, cy + TH * 0.36, letter, TH * 0.95)


def _text_w(s):
    return len(s) * TH * 0.6


def _svg(w, h, body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%.3fmm" height="%.3fmm" '
            'viewBox="0 0 %.3f %.3f">%s</svg>' % (w, h, w, h, body))


def fcf_svg(char, tol, dia=False, mod="", datums=()):
    """Feature control frame. datums: [(letter, modifier)]. Returns (svg, width, height)."""
    pad = 1.6
    cells = []  # (width, draw(x0) -> svg)
    cells.append((H, lambda x: symbol(char, x + H / 2, H / 2, H * 0.62)))
    tw = _text_w(tol)
    w = pad + (TH * 1.1 if dia else 0) + tw + (TH * 1.5 if mod else 0) + pad

    def tol_cell(x, tw=tw):
        out, cx = "", x + pad
        if dia:
            out += _diameter(cx + TH * 0.45, H / 2)
            cx += TH * 1.1
        out += _text(cx, H / 2 + TH * 0.36, tol, anchor="start")
        cx += tw
        if mod:
            out += _modifier(cx + TH * 0.8, H / 2, mod)
        return out

    cells.append((w, tol_cell))
    for letter, m in datums:
        if not letter:
            continue
        lw = pad + _text_w(letter) + (TH * 1.5 if m else 0) + pad

        def d_cell(x, letter=letter, m=m, lw=lw):
            out = _text(x + pad + _text_w(letter) / 2, H / 2 + TH * 0.36, letter)
            if m:
                out += _modifier(x + pad + _text_w(letter) + TH * 0.8, H / 2, m)
            return out

        cells.append((lw, d_cell))
    total = sum(c[0] for c in cells)
    o = LW / 2
    body = '<rect x="%g" y="%g" width="%.3f" height="%.3f" fill="#fff" stroke="#000" stroke-width="%g"/>' % (
        o, o, total - LW, H - LW, LW)
    x = 0.0
    for i, (cw, draw) in enumerate(cells):
        if i:
            body += _line(x, 0, x, H)
        body += draw(x)
        x += cw
    return _svg(total, H, body), total, H


def datum_svg(letter, side):
    """Datum feature symbol: letter in a square, stem, filled triangle on the feature.
    side: where the feature is, seen from the box ("down", "up", "left", "right").
    Returns (svg, width, height, (ax, ay)) - ax, ay: the triangle's base centre measured from the
    SVG centre in page coordinates (mm, Y up)."""
    b = H + 0.6            # box size
    stem = 5.0
    t = 2.6                # triangle height
    if side in ("down", "up"):
        w, h = b, b + stem + t
    else:
        w, h = b + stem + t, b
    body = ""
    if side == "down":
        bx, by = 0, 0
        body += _line(b / 2, b, b / 2, b + stem)
        body += _poly([(b / 2, b + stem), (b / 2 - t * 0.6, h - LW), (b / 2 + t * 0.6, h - LW)], fill="#000")
        anchor = (0, -h / 2)
    elif side == "up":
        bx, by = 0, h - b
        body += _line(b / 2, h - b, b / 2, t)
        body += _poly([(b / 2, t), (b / 2 - t * 0.6, LW), (b / 2 + t * 0.6, LW)], fill="#000")
        anchor = (0, h / 2)
    elif side == "left":
        bx, by = w - b, 0
        body += _line(w - b, b / 2, t, b / 2)
        body += _poly([(t, b / 2), (LW, b / 2 - t * 0.6), (LW, b / 2 + t * 0.6)], fill="#000")
        anchor = (-w / 2, 0)
    else:
        bx, by = 0, 0
        body += _line(b, b / 2, b + stem, b / 2)
        body += _poly([(b + stem, b / 2), (w - LW, b / 2 - t * 0.6), (w - LW, b / 2 + t * 0.6)], fill="#000")
        anchor = (w / 2, 0)
    body += '<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" fill="#fff" stroke="#000" stroke-width="%g"/>' % (
        bx + LW / 2, by + LW / 2, b - LW, b - LW, LW)
    body += _text(bx + b / 2, by + b / 2 + TH * 0.4, letter, TH * 1.1)
    return _svg(w, h, body), w, h, anchor


def preview_pixmap(svg, height_px=40):
    from PySide import QtSvg
    r = QtSvg.QSvgRenderer(QtCore.QByteArray(svg.encode("utf-8")))
    size = r.defaultSize()
    w = max(1, int(height_px * size.width() / max(size.height(), 1)))
    pm = QtGui.QPixmap(w, height_px)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    r.render(p)
    p.end()
    return pm


def symbol_icon(key):
    return QtGui.QIcon(preview_pixmap(_svg(H, H, symbol(key, H / 2, H / 2, H * 0.7)), 32))


# ======================================================================
# Placing things on a page
# ======================================================================

def add_symbol(page, svg, x, y, label):
    doc = page.Document
    sym = doc.addObject("TechDraw::DrawViewSymbol", "GDT")
    sym.Label = label
    sym.Symbol = svg
    page.addView(sym)
    sym.X = x
    sym.Y = y
    return sym


def add_leader(view, start, end, arrow=True):
    """Leader from start (page mm, Y up) to end. Leader positions are relative to the
    parent view and scaled by it; the waypoints are page mm with Y down."""
    doc = view.Document
    page = drawing.page_of(view)
    vx, vy = drawing.view_center(view)
    s = drawing.view_scale(view)
    ld = doc.addObject("TechDraw::DrawLeaderLine", "Leader")
    page.addView(ld)
    ld.LeaderParent = view
    ld.X = (start[0] - vx) / s
    ld.Y = (start[1] - vy) / s
    dx, dy = end[0] - start[0], end[1] - start[1]
    pts = [App.Vector(0, 0, 0)]
    if abs(dy) > 1e-6 and abs(dx) > 1e-6:
        pts.append(App.Vector(dx - (4 if dx > 0 else -4), -dy, 0))   # short horizontal shoulder
    pts.append(App.Vector(dx, -dy, 0))
    ld.WayPoints = pts
    ld.StartSymbol = "Filled arrow" if arrow else "None"
    ld.EndSymbol = "None"
    return ld


def edge_point(view, edge, along=0.5):
    """Page position (mm, Y up) of a point on an edge (along: 0..1) and the outward side of
    the view the edge is on."""
    vx, vy = drawing.view_center(view)
    m = edge.valueAt(edge.FirstParameter + along * (edge.LastParameter - edge.FirstParameter))
    px, py = vx + m.x, vy + m.y
    bb = edge.BoundBox
    if bb.XLength < 1e-6:          # vertical edge
        side = "left" if bb.XMin < 0 else "right"
    else:
        side = "down" if bb.YMin < 0 else "up"
    return (px, py), side


def add_datum(view, edge, letter, along=0.25):
    """Datum feature symbol outside the view with its triangle on the edge.
    along: where on the edge (0..1), away from the middle so it clears the dimensions."""
    (px, py), side = edge_point(view, edge, along)
    # The box sits outside the edge, so the triangle points back at the feature.
    flip = {"down": "up", "up": "down", "left": "right", "right": "left"}[side]
    svg, _w, _h, (ax, ay) = datum_svg(letter, flip)
    return add_symbol(drawing.page_of(view), svg, px - ax, py - ay, "Datum %s" % letter)


def add_fcf(page, x, y, char, tol, dia=False, mod="", datums=()):
    """Frame centred on (x, y), page mm."""
    svg, w, h = fcf_svg(char, tol, dia, mod, datums)
    return add_symbol(page, svg, x, y, "%s %s" % (NAMES.get(char, char), tol)), w, h


def add_fcf_to_edge(view, edge, char, tol, dia=False, mod="", datums=(), along=0.5, dx=None, dy=None):
    """Frame with a leader to a point on the edge. dx, dy: where the leader ends, relative to
    that point (page mm, Y up); by default outward from the view."""
    (px, py), side = edge_point(view, edge, along)
    if dx is None:
        dx = -25.0 if side == "left" else 25.0
    if dy is None:
        dy = -15.0 if side == "down" else 15.0
    svg, w, h = fcf_svg(char, tol, dia, mod, datums)
    end = (px + dx, py + dy)
    cx = end[0] + (w / 2 if dx >= 0 else -w / 2)
    sym = add_symbol(drawing.page_of(view), svg, cx, end[1], "%s %s" % (NAMES.get(char, char), tol))
    add_leader(view, (px, py), end)
    return sym


def add_fcf_under_dimension(dim, char, tol, dia=False, mod="", datums=(), below=4.5):
    """Frame placed directly under a dimension's text (e.g. position under a hole callout).
    below: gap under the text centre in mm - more for steeply angled dimensions."""
    view = dim.References2D[0][0]
    vx, vy = drawing.view_center(view)
    svg, w, h = fcf_svg(char, tol, dia, mod, datums)
    x = vx + dim.X.Value + w / 2 - 6
    y = vy + dim.Y.Value - below - h / 2
    return add_symbol(drawing.page_of(view), svg, x, y, "%s %s" % (NAMES.get(char, char), tol))


def make_basic(dim, fmt=None):
    """Basic (theoretically exact, boxed) dimension: no tolerance, .XXX by default."""
    dim.TheoreticalExact = True
    dim.EqualTolerance = True
    dim.OverTolerance = 0
    if fmt or "%.2f" in dim.FormatSpec:
        dim.FormatSpec = fmt or dim.FormatSpec.replace("%.2f", "%.3f")
    return dim


def used_datums(page):
    out = set()
    for v in page.Views:
        if v.isDerivedFrom("TechDraw::DrawViewSymbol") and v.Label.startswith("Datum ") and len(v.Label) == 7:
            out.add(v.Label[-1])
    return out


def next_datum(page):
    used = used_datums(page)
    for c in "ABCDEFGHJKLMNPRSTUVWXYZ":   # I, O and Q are not used as datum letters
        if c not in used:
            return c
    return "A"


# ======================================================================
# Dialogs and commands
# ======================================================================

def _selection():
    """(view, edge) picks and selected dimensions on a drawing page."""
    edges, dims = [], []
    for sel in Gui.Selection.getSelectionEx():
        o = sel.Object
        if o.isDerivedFrom("TechDraw::DrawViewDimension"):
            dims.append(o)
        elif o.isDerivedFrom("TechDraw::DrawViewPart"):
            for sub in sel.SubElementNames:
                if sub.startswith("Edge"):
                    edges.append((o, drawing.view_edge(o, sub)))
    return edges, dims


class ToleranceDialog(QtWidgets.QDialog):
    def __init__(self, page, char="position"):
        super().__init__(Gui.getMainWindow())
        self.setWindowTitle("Geometric Tolerance")
        lay = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        self.char = QtWidgets.QComboBox()
        self.char.setIconSize(QtCore.QSize(22, 22))
        for k, n, _d in CHARACTERISTICS:
            self.char.addItem(symbol_icon(k), n, k)
        self.char.setCurrentIndex([c[0] for c in CHARACTERISTICS].index(char))
        form.addRow("Symbol:", self.char)
        row = QtWidgets.QHBoxLayout()
        self.dia = QtWidgets.QCheckBox("⌀ zone")
        self.tol = QtWidgets.QLineEdit(".010")
        self.mod = QtWidgets.QComboBox()
        for k, n in MODIFIERS:
            self.mod.addItem(n, k)
        row.addWidget(self.dia)
        row.addWidget(self.tol)
        row.addWidget(self.mod)
        form.addRow("Tolerance:", row)
        self.datums = []
        letters = [""] + sorted(used_datums(page) | set("ABC"))
        for label in ("Primary datum:", "Secondary datum:", "Tertiary datum:"):
            r = QtWidgets.QHBoxLayout()
            letter = QtWidgets.QComboBox()
            letter.setEditable(True)
            letter.addItems(letters)
            m = QtWidgets.QComboBox()
            for k, n in MODIFIERS:
                m.addItem(n, k)
            r.addWidget(letter)
            r.addWidget(m)
            form.addRow(label, r)
            self.datums.append((letter, m))
        self.datums[0][0].setCurrentText("A")
        self.datums[1][0].setCurrentText("B")
        lay.addLayout(form)
        self.preview = QtWidgets.QLabel()
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.preview.setMinimumHeight(60)
        self.preview.setStyleSheet("background: white; border: 1px solid #ccc;")
        lay.addWidget(self.preview)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for w in [self.char, self.mod] + [x for pair in self.datums for x in pair]:
            w.currentIndexChanged.connect(self.update)
        for letter, _m in self.datums:
            letter.editTextChanged.connect(self.update)
        self.dia.toggled.connect(self.update)
        self.tol.textChanged.connect(self.update)
        self.char.currentIndexChanged.connect(self._char_changed)
        self._char_changed()

    def _char_changed(self, *_):
        k = self.char.currentData()
        use = DATUMS[k] != "no"
        for letter, m in self.datums:
            letter.setEnabled(use)
            m.setEnabled(use)
        if k == "position":
            self.dia.setChecked(True)
        elif k in ("flatness", "straightness", "circularity", "cylindricity", "profile_surface",
                   "profile_line", "circular_runout", "total_runout"):
            self.dia.setChecked(False)
        self.update()

    def values(self):
        k = self.char.currentData()
        datums = []
        if DATUMS[k] != "no":
            datums = [(l.currentText().strip().upper(), m.currentData()) for l, m in self.datums
                      if l.currentText().strip()]
        return dict(char=k, tol=self.tol.text().strip(), dia=self.dia.isChecked(),
                    mod=self.mod.currentData(), datums=datums)

    def update(self, *_):
        v = self.values()
        svg, _w, _h = fcf_svg(**v)
        self.preview.setPixmap(preview_pixmap(svg, 44))


class GeometricTolerance(commands._Cmd):
    pixmap = icon("GeometricTolerance")
    menu = "Geometric Tolerance"
    tip = ("Feature control frame (ASME Y14.5). Select an edge in a view to attach it with a leader, "
           "or a dimension to place it under the dimension (e.g. position of a hole)")

    def IsActive(self):
        return commands.has_doc() and drawing.active_page() is not None

    def Activated(self):
        page = drawing.active_page()
        edges, dims = _selection()
        dlg = ToleranceDialog(page, "position" if dims else "flatness" if edges else "position")
        if not dlg.exec_():
            return
        v = dlg.values()
        App.ActiveDocument.openTransaction("Geometric Tolerance")
        if dims:
            for d in dims:
                add_fcf_under_dimension(d, **v)
        elif edges:
            for view, e in edges:
                add_fcf_to_edge(view, e, **v)
        else:
            tpl = page.Template
            add_fcf(page, tpl.Width.Value / 2, tpl.Height.Value / 2, **v)
        App.ActiveDocument.commitTransaction()
        App.ActiveDocument.recompute()


class DatumFeature(commands._Cmd):
    pixmap = icon("DatumFeature")
    menu = "Datum Feature"
    tip = "Datum feature symbol: select an edge in a drawing view (the next free letter is suggested)"

    def IsActive(self):
        return commands.has_doc() and drawing.active_page() is not None

    def Activated(self):
        page = drawing.active_page()
        edges, _dims = _selection()
        if not edges:
            from solidstyle import features
            features.warn("Datum Feature", "Select the edge of the datum feature in a drawing view first.")
            return
        letter, ok = QtWidgets.QInputDialog.getText(Gui.getMainWindow(), "Datum Feature", "Datum letter:",
                                                    text=next_datum(page))
        if not ok or not letter.strip():
            return
        App.ActiveDocument.openTransaction("Datum Feature")
        for view, e in edges:
            add_datum(view, e, letter.strip().upper()[:2])
        App.ActiveDocument.commitTransaction()
        App.ActiveDocument.recompute()


class BasicDimension(commands._Cmd):
    pixmap = icon("BasicDimension")
    menu = "Basic Dimension"
    tip = "Make the selected dimensions basic (boxed, theoretically exact) or back to normal"

    def Activated(self):
        _edges, dims = _selection()
        if not dims:
            from solidstyle import features
            features.warn("Basic Dimension", "Select one or more dimensions first.")
            return
        App.ActiveDocument.openTransaction("Basic Dimension")
        on = not all(d.TheoreticalExact for d in dims)
        for d in dims:
            d.TheoreticalExact = on
        App.ActiveDocument.commitTransaction()
        App.ActiveDocument.recompute()


def register():
    for name, cls in [("SS_GeometricTolerance", GeometricTolerance), ("SS_DatumFeature", DatumFeature),
                      ("SS_BasicDimension", BasicDimension)]:
        Gui.addCommand(name, cls())
