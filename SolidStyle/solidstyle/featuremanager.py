"""SolidWorks-style FeatureManager design tree.

While the workbench is active it takes the place of FreeCAD's tree in the Model
panel (renamed FeatureManager; Tasks becomes PropertyManager). FreeCAD's own
tree and property editor stay one click away (the tree button next to Filter).

Part:      Part1 > History, Sensors, Annotations, Solid Bodies(1), Material,
           Front/Top/Right Plane, Origin, features (sketches absorbed under the
           feature that uses them), the rollback bar.
Assembly:  Assem1 > ... planes, (f)/(-) Part1<1> components, Mates.
Drawing:   Draw1 > Annotations, Sheet > Sheet Format1, Drawing View1...

Only what is displayed changes for mates and drawing views; feature names are
set on the objects themselves by setup.DocObserver.
"""
import os
import re

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

ICONS = os.path.join(os.path.dirname(__file__), "icons")

OBJ = QtCore.Qt.UserRole          # (doc name, object name)
KIND = QtCore.Qt.UserRole + 1     # "doc", "folder", "feature", "sketch", "plane", "bar", ...
KEY = QtCore.Qt.UserRole + 2      # stable key for remembering expanded items

CONFIG = {
    "part": " (Default<<Default>_Display State 1>)",
    "assembly": " (Default<Default_Display State-1>)",
    "drawing": "",
}

FEATURE_ICONS = {
    "PartDesign::Pad": "sw/PartDesign_Pad",
    "PartDesign::Pocket": "sw/PartDesign_Pocket",
    "PartDesign::Revolution": "sw/PartDesign_Revolution",
    "PartDesign::Groove": "sw/PartDesign_Groove",
    "PartDesign::AdditivePipe": "sw/PartDesign_AdditivePipe",
    "PartDesign::SubtractivePipe": "sw/PartDesign_SubtractivePipe",
    "PartDesign::AdditiveLoft": "sw/PartDesign_AdditiveLoft",
    "PartDesign::SubtractiveLoft": "sw/PartDesign_SubtractiveLoft",
    "PartDesign::AdditiveHelix": "sw/PartDesign_AdditiveHelix",
    "PartDesign::SubtractiveHelix": "sw/PartDesign_SubtractiveHelix",
    "PartDesign::Fillet": "sw/PartDesign_Fillet",
    "PartDesign::Chamfer": "sw/PartDesign_Chamfer",
    "PartDesign::Thickness": "sw/PartDesign_Thickness",
    "PartDesign::Draft": "sw/PartDesign_Draft",
    "PartDesign::Hole": "sw/PartDesign_Hole",
    "PartDesign::LinearPattern": "sw/PartDesign_LinearPattern",
    "PartDesign::PolarPattern": "sw/PartDesign_PolarPattern",
    "PartDesign::Mirrored": "sw/PartDesign_Mirrored",
    "PartDesign::MultiTransform": "sw/PartDesign_MultiTransform",
    "PartDesign::Scaled": "sw/PartDesign_Scaled",
    "PartDesign::Boolean": "sw/PartDesign_Boolean",
    "PartDesign::Plane": "tree/plane",
    "PartDesign::Line": "tree/axis",
    "PartDesign::Point": "tree/point",
    "PartDesign::CoordinateSystem": "tree/coord_sys",
    "PartDesign::Body": "tree/solid_body",
    "Sketcher::SketchObject": "tree/sketch",
    "App::Plane": "tree/plane",
    "App::Line": "tree/axis",
    "App::Point": "tree/origin",
    "TechDraw::DrawPage": "tree/sheet",
    "TechDraw::DrawSVGTemplate": "tree/sheet_format",
}

# SolidWorks names for FreeCAD joints (shown only; the joint keeps its own label).
MATE_NAMES = {
    "Fixed": "Lock", "Revolute": "Hinge", "Cylindrical": "Concentric", "Slider": "Slider",
    "Ball": "Coincident", "Distance": "Distance", "Parallel": "Parallel", "Perpendicular": "Perpendicular",
    "Angle": "Angle", "RackPinion": "Rack Pinion", "Screw": "Screw", "Gears": "Gear", "Belt": "Belt",
}
_DEFAULT_JOINT = re.compile(r"(Joint|%s)\d*$" % "|".join(MATE_NAMES))
_DEFAULT_PLANE = re.compile(r"(XY|XZ|YZ)[_-][Pp]lane\d*$")
ORIGIN_ORDER = (("XZ_Plane", "Front Plane"), ("XY_Plane", "Top Plane"), ("YZ_Plane", "Right Plane"))
# TechDraw objects the SolidWorks drawing tree does not list
_DRAWING_HIDDEN = ("TechDraw::DrawViewDimension", "TechDraw::DrawViewBalloon", "TechDraw::DrawLeaderLine",
                   "TechDraw::DrawViewDimExtent", "TechDraw::DrawWeldSymbol", "TechDraw::DrawTileWeld",
                   "TechDraw::DrawHatch", "TechDraw::DrawGeomHatch")
# properties whose change alters the tree (anything else, e.g. Shape, is ignored)
WATCH = {"Label", "Tip", "Group", "Suppressed", "Profile", "ObjectToGround", "LinkedObject", "ShapeMaterial",
         "JointType", "Distance", "Views", "Template", "Scale", "SectionSymbol", "Reference", "Constraints",
         "Reference1", "Reference2", "OriginFeatures"}

_icon_cache = {}


def icon(name):
    ic = _icon_cache.get(name)
    if ic is None:
        ic = _icon_cache[name] = QtGui.QIcon(os.path.join(ICONS, name + ".svg"))
    return ic


def _badge(base, color, glyph):
    """The icon with a small round badge (error/warning) in its lower right corner."""
    out = QtGui.QIcon()
    for s in (16, 24, 32, 48):
        pm = base.pixmap(s, s)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = s * 0.55
        rect = QtCore.QRectF(s - r, s - r, r - 0.5, r - 0.5)
        p.setBrush(QtGui.QColor(color))
        p.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), max(1.0, s / 24)))
        p.drawEllipse(rect)
        f = p.font()
        f.setPixelSize(int(r * 0.85))
        f.setBold(True)
        p.setFont(f)
        p.drawText(rect, QtCore.Qt.AlignCenter, glyph)
        p.end()
        out.addPixmap(pm)
    return out


def obj_icon(obj):
    name = FEATURE_ICONS.get(obj.TypeId)
    if name is None:
        if obj.isDerivedFrom("TechDraw::DrawView"):
            name = "tree/view"
        elif obj.isDerivedFrom("Assembly::AssemblyObject"):
            name = "tree/assembly"
    if name is not None:
        ic = icon(name)
    else:
        ic = None
        try:
            ic = obj.ViewObject.Icon
        except Exception:
            pass
        if not isinstance(ic, QtGui.QIcon) or ic.isNull():
            ic = icon("tree/solid_body")
    state = getattr(obj, "State", []) or []
    if "Invalid" in state or "Error" in state:
        ic = _badge(ic, "#d62f2f", "×")
    return ic


def is_solid_feature(o):
    return o.isDerivedFrom("PartDesign::Feature")


def sketch_prefix(sk):
    """SolidWorks' sketch state: '(-) ' under defined, '(+) ' over defined, '(?) ' not solved."""
    try:
        if sk.MalformedConstraints or sk.ConflictingConstraints:
            return "(?) "
        if sk.RedundantConstraints:
            return "(+) "
        return "" if sk.FullyConstrained else "(-) "
    except Exception:
        return ""


def _ratio(s):
    if not s:
        return ""
    return "%g : 1" % s if s >= 1 else "1 : %g" % round(1 / s, 3)


def _default_label(obj, *extra):
    """True while the object still has a FreeCAD-made label (so we may show a SolidWorks name)."""
    stem = re.sub(r"\d+$", "", obj.Name)
    pats = [re.escape(stem)] + [re.escape(e) for e in extra]
    return re.fullmatch(r"(%s)\d*" % "|".join(pats), obj.Label) is not None


# ======================================================================
# The tree widget
# ======================================================================

class _Delegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, tree):
        super().__init__(tree)
        self.tree = tree

    def paint(self, painter, option, index):
        if index.data(KIND) == "bar":
            r = option.rect
            hot = self.tree.bar_hot or self.tree.dragging
            y = r.center().y()
            painter.save()
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            left = r.left() + 2
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor("#1f5fbf" if hot else "#222222"))
            painter.drawRect(QtCore.QRectF(left, y - 3.5, r.right() - left - 4, 7))
            painter.setBrush(QtGui.QColor("#5aa0ff" if hot else "#f5c400"))
            painter.drawRect(QtCore.QRectF(left + 1, y - 2, r.right() - left - 6, 4))
            painter.restore()
            return
        super().paint(painter, option, index)

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        if index.data(KIND) == "bar":
            sh.setHeight(max(10, sh.height() // 2))
        return sh


class FeatureTree(QtWidgets.QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SS_FeatureTree")
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setMouseTracking(True)
        self.setExpandsOnDoubleClick(False)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditKeyPressed)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.setItemDelegate(_Delegate(self))
        self.setAnimated(False)
        self.setIndentation(16)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        h = self.fontMetrics().height()
        self.setIconSize(QtCore.QSize(h + 2, h + 2))
        pal = self.palette()
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor("#ffffff"))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor("#1a1a1a"))
        self.setPalette(pal)
        self.setStyleSheet(
            "QTreeWidget#SS_FeatureTree{background:#ffffff;border:none;outline:0;}"
            "QTreeWidget#SS_FeatureTree::item{padding:1px 3px;border:1px solid transparent;}"
            "QTreeWidget#SS_FeatureTree::item:hover{background:#e5f1fb;border:1px solid #cce4f7;}"
            "QTreeWidget#SS_FeatureTree::item:selected{background:#cce8ff;border:1px solid #7ab8f5;color:#000;}")

        self.doc_name = None
        self.expanded = {}           # key -> bool, remembered per document
        self.bar_hot = False
        self.dragging = False
        self.drop_line = None        # y of the rollback drop indicator
        self.syncing = False
        self.pushing = False
        self.renaming = None
        self.filter_text = ""
        self.hover_key = None

        self.itemSelectionChanged.connect(self._push_selection)
        self.itemDoubleClicked.connect(self._double_clicked)
        self.itemChanged.connect(self._item_changed)
        self.itemExpanded.connect(lambda it: self._remember(it, True))
        self.itemCollapsed.connect(lambda it: self._remember(it, False))
        self.itemEntered.connect(self._hover)
        self.customContextMenuRequested.connect(self._context_menu)
        self.itemDelegate().closeEditor.connect(lambda *a: self._end_rename())

    # ------------------------------------------------------------ helpers
    def obj_of(self, item):
        ref = item.data(0, OBJ) if item is not None else None
        if not ref:
            return None
        doc = App.listDocuments().get(ref[0])
        return doc.getObject(ref[1]) if doc else None

    def _remember(self, item, state):
        key = item.data(0, KEY)
        if key:
            self.expanded[(self.doc_name, key)] = state

    def _add(self, parent, text, ic, kind, obj=None, key=None, expand=False, grey=False):
        it = QtWidgets.QTreeWidgetItem(parent, [text])
        it.setIcon(0, ic)
        it.setData(0, KIND, kind)
        flags = QtCore.Qt.ItemIsEnabled
        if kind != "bar":
            flags |= QtCore.Qt.ItemIsSelectable
        if obj is not None:
            it.setData(0, OBJ, (obj.Document.Name, obj.Name))
            flags |= QtCore.Qt.ItemIsEditable
            key = key or obj.Name
        it.setFlags(flags)
        if grey:
            it.setForeground(0, QtGui.QBrush(QtGui.QColor("#9a9a9a")))
        if obj is not None:
            state = getattr(obj, "State", []) or []
            if "Invalid" in state or "Error" in state:
                it.setForeground(0, QtGui.QBrush(QtGui.QColor("#c00000")))
        if key:
            it.setData(0, KEY, key)
            it.setExpanded(self.expanded.get((self.doc_name, key), expand))
        return it

    # ------------------------------------------------------------ building
    def rebuild(self):
        if self.renaming is not None or self.dragging:
            return
        doc = App.ActiveDocument
        self.syncing = True
        try:
            scroll = self.verticalScrollBar().value()
            self.setUpdatesEnabled(False)
            self.clear()
            self.doc_name = doc.Name if doc else None
            if doc is not None:
                self._build(doc)
            self.apply_filter(self.filter_text)
            self.verticalScrollBar().setValue(scroll)
        finally:
            self.setUpdatesEnabled(True)
            self.syncing = False
        self.pull_selection()

    def _build(self, doc):
        objs = doc.Objects
        bodies = [o for o in objs if o.TypeId == "PartDesign::Body"]
        asms = [o for o in objs if o.isDerivedFrom("Assembly::AssemblyObject")]
        pages = [o for o in objs if o.isDerivedFrom("TechDraw::DrawPage")]
        kind = "assembly" if asms else ("drawing" if pages and not bodies else "part")
        top = self._add(self, doc.Label + CONFIG[kind], icon("tree/" + kind), "doc",
                        bodies[0] if kind == "part" and len(bodies) == 1 else None, key="__doc__", expand=True)
        top.setFlags(top.flags() & ~QtCore.Qt.ItemIsEditable)
        shown = set()
        if kind == "drawing":
            self._folder(top, "Annotations", "annotations", self._drawing_notes(pages))
            for p in pages:
                self._page(top, p, shown)
            self._others(top, doc, shown)
            return

        feats = [f for b in bodies for f in b.Group if is_solid_feature(f)]
        self._folder(top, "History", "history", list(reversed(feats))[:10])
        self._folder(top, "Sensors", "sensors", [])
        self._folder(top, "Annotations", "annotations", [])
        if kind == "assembly":
            for asm in asms:
                self._assembly(top, asm, shown, nested=len(asms) > 1)
        else:
            self._solid_bodies(top, bodies)
            self._material(top, bodies)
            if bodies:
                self._origin(top, bodies[0], shown)
            for b in bodies:
                shown.add(b.Name)
                if len(bodies) > 1:
                    parent = self._add(top, b.Label, icon("tree/solid_body"), "body", b, expand=True)
                    if b is not bodies[0]:
                        self._origin(parent, b, shown)
                else:
                    parent = top
                self._features(parent, b, shown)
        for p in pages:
            self._page(top, p, shown)
        self._others(top, doc, shown)

    def _folder(self, parent, text, ic, children):
        it = self._add(parent, text, icon("tree/" + ic), "folder", key="__" + ic)
        for o in children:
            self._add(it, o.Label, obj_icon(o), "ref", o, key="ref:" + o.Name)
        return it

    def _solid_bodies(self, top, bodies):
        it = self._add(top, "Solid Bodies(%d)" % len(bodies), icon("tree/solid_bodies"), "folder",
                       key="__solid_bodies")
        for b in bodies:
            # SolidWorks names a body after the last feature that changed it
            name = b.Tip.Label if b.Tip is not None else b.Label
            self._add(it, name, icon("tree/solid_body"), "ref", b, key="ref:" + b.Name,
                      grey=not b.Visibility)

    def _material(self, top, bodies):
        name = ""
        for b in bodies:
            m = getattr(b, "ShapeMaterial", None)
            n = getattr(m, "Name", "") if m is not None else ""
            if n and n != "Default":
                name = n
                break
        it = self._add(top, "Material <not specified>" if not name else name, icon("tree/material"), "material",
                       key="__material")
        it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)

    def _origin(self, parent, container, shown):
        origin = getattr(container, "Origin", None)
        if origin is None:
            return
        shown.add(origin.Name)
        roles = {}
        for f in origin.OriginFeatures:
            shown.add(f.Name)
            roles[getattr(f, "Role", "") or re.sub(r"\d+$", "", f.Name)] = f
        for role, sw in ORIGIN_ORDER:
            f = roles.get(role)
            if f is not None:
                label = sw if _DEFAULT_PLANE.fullmatch(f.Label) else f.Label
                self._add(parent, label, icon("tree/plane"), "plane", f)
        o = roles.get("Origin")
        if o is not None:
            self._add(parent, "Origin", icon("tree/origin"), "origin", o)

    def _features(self, parent, body, shown):
        group = [o for o in body.Group if not o.isDerivedFrom("App::Origin")]
        names = {o.Name for o in group}
        absorbed = {}       # sketch -> feature that uses it
        for f in group:
            if is_solid_feature(f):
                for o in f.OutList:
                    if o.Name in names and not is_solid_feature(o) and o.Name not in absorbed and \
                            o.isDerivedFrom("Part::Part2DObject"):
                        absorbed[o.Name] = f
        tip = body.Tip
        bar_pending = tip is None
        rolled = False
        for f in group:
            shown.add(f.Name)
            if f.Name in absorbed:
                continue
            if bar_pending and is_solid_feature(f):
                self._add(parent, "", QtGui.QIcon(), "bar", key=None).setData(0, OBJ, (body.Document.Name, body.Name))
                bar_pending, rolled = False, True
            it = self._feature_item(parent, f, rolled)
            for o in group:
                if absorbed.get(o.Name) is f:
                    self._feature_item(it, o, rolled)
            if f is tip:
                bar_pending = True
        if not rolled:
            self._add(parent, "", QtGui.QIcon(), "bar").setData(0, OBJ, (body.Document.Name, body.Name))

    def _feature_item(self, parent, f, rolled):
        text = f.Label
        kind = "feature" if is_solid_feature(f) else "sketch" if f.isDerivedFrom("Part::Part2DObject") else "datum"
        if f.TypeId == "Sketcher::SketchObject":
            text = sketch_prefix(f) + text
        grey = rolled or bool(getattr(f, "Suppressed", False))
        ic = obj_icon(f)
        if grey:
            ic = QtGui.QIcon(ic.pixmap(64, 64, QtGui.QIcon.Disabled))
        return self._add(parent, text, ic, kind, f, grey=grey)

    # ------------------------------------------------------------ assemblies
    def _assembly(self, top, asm, shown, nested):
        shown.add(asm.Name)
        parent = self._add(top, asm.Label, icon("tree/assembly"), "body", asm, expand=True) if nested else top
        self._origin(parent, asm, shown)
        joints, grounded, comps, rest = [], set(), [], []
        # joints normally live in the Joints group, but look everywhere in the file
        for j in asm.Document.Objects:
            if hasattr(j, "ObjectToGround"):
                shown.add(j.Name)
                if j.ObjectToGround is not None:
                    grounded.add(j.ObjectToGround.Name)
            elif hasattr(j, "JointType") and hasattr(j, "Reference1"):
                shown.add(j.Name)
                joints.append(j)
        for o in asm.Group:
            if o.Name in shown or o.isDerivedFrom("App::Origin") or o.TypeId == "Assembly::JointGroup":
                shown.add(o.Name)
                continue
            shown.add(o.Name)
            if hasattr(o, "Placement") and (o.isDerivedFrom("App::Link") or o.isDerivedFrom("Part::Feature")
                                              or o.isDerivedFrom("App::Part")):
                comps.append(o)
            else:
                rest.append(o)
        count, names = {}, {}
        for c in comps:
            linked = c.getLinkedObject(True) if hasattr(c, "getLinkedObject") else c
            base = linked.Label if linked is not None else c.Label
            # FreeCAD labels copies Part1, Part001, Part002...: those are all Part1<n>
            stem = re.escape(re.sub(r"\d+$", "", base))
            if not re.fullmatch(stem + r"\d*", c.Label) and not _default_label(c, "Link"):
                base = c.Label
            n = count[base] = count.get(base, 0) + 1
            names[c.Name] = "%s<%d>" % (base, n)
            pre = "(f) " if c.Name in grounded else "(-) "
            ic = icon("tree/assembly") if linked is not None and linked.isDerivedFrom("Assembly::AssemblyObject") \
                else icon("tree/component")
            self._add(parent, pre + names[c.Name], ic, "component", c)
        mates = self._add(parent, "Mates", icon("tree/mates"), "folder", key="__mates", expand=True)
        seq = {}
        for j in joints:
            jt = str(getattr(j, "JointType", ""))
            sw = MATE_NAMES.get(jt, jt or "Mate")
            if sw == "Distance" and abs(float(getattr(j, "Distance", 0) or 0)) < 1e-9:
                sw = "Coincident"
            if _DEFAULT_JOINT.fullmatch(j.Label):
                seq[sw] = seq.get(sw, 0) + 1
                text = "%s%d" % (sw, seq[sw])
            else:
                text = j.Label
            parts = [names.get(n) for n in self._joint_parts(asm, j)]
            parts = [p for p in parts if p]
            if parts:
                text += " (%s)" % ",".join(parts)
            self._add(mates, text, icon("tree/mate"), "mate", j)
        for o in rest:
            self._generic(parent, o, shown)

    @staticmethod
    def _joint_parts(asm, j):
        out = []
        for prop in ("Reference1", "Reference2"):
            try:
                ref = getattr(j, prop)
                if not ref:
                    continue
                sub = ref[1][0] if isinstance(ref[1], (list, tuple)) else ref[1]
                first = sub.split(".")[0]
                if ref[0] is not asm and ref[0] is not None:
                    first = ref[0].Name if not first else first
                out.append(first)
            except Exception:
                pass
        return out

    # ------------------------------------------------------------ drawings
    @staticmethod
    def _drawing_notes(pages):
        out = []
        for p in pages:
            for v in p.Views:
                if v.isDerivedFrom("TechDraw::DrawViewAnnotation") or v.isDerivedFrom("TechDraw::DrawRichAnno") \
                        or v.isDerivedFrom("TechDraw::DrawViewSymbol"):
                    out.append(v)
        return out

    def _page(self, parent, page, shown):
        shown.add(page.Name)
        it = self._add(parent, page.Label, icon("tree/sheet"), "page", page, expand=True)
        tpl = getattr(page, "Template", None)
        n_view = [0]
        if tpl is not None:
            shown.add(tpl.Name)
            self._add(it, "Sheet Format1" if _default_label(tpl, "Template") else tpl.Label,
                      icon("tree/sheet_format"), "template", tpl)

        def add_view(v):
            shown.add(v.Name)
            if any(v.isDerivedFrom(t) for t in _DRAWING_HIDDEN):
                return
            if v.isDerivedFrom("TechDraw::DrawViewAnnotation") or v.isDerivedFrom("TechDraw::DrawRichAnno") \
                    or v.isDerivedFrom("TechDraw::DrawViewSymbol"):
                return
            if v.isDerivedFrom("TechDraw::DrawProjGroup"):
                for item in v.Views:
                    add_view(item)
                return
            proj = ("Front", "Top", "Right", "Left", "Bottom", "Rear", "FrontTopLeft", "FrontTopRight",
                    "FrontBottomLeft", "FrontBottomRight")
            text = v.Label
            if v.isDerivedFrom("TechDraw::DrawViewSection") and _default_label(v, "Section"):
                sym = getattr(v, "SectionSymbol", "") or "A"
                text = "Section View %s-%s" % (sym, sym)
            elif v.isDerivedFrom("TechDraw::DrawViewDetail") and _default_label(v, "Detail"):
                text = "Detail View %s (%s)" % (getattr(v, "Reference", "") or "A", _ratio(getattr(v, "Scale", 0)))
            elif v.isDerivedFrom("TechDraw::DrawViewPart") and _default_label(v, "View", *proj):
                n_view[0] += 1
                text = "Drawing View%d" % n_view[0]
            elif not v.isDerivedFrom("TechDraw::DrawViewPart"):
                pass
            else:
                n_view[0] += 1
            self._add(it, text, icon("tree/view"), "view", v)

        for v in page.Views:
            add_view(v)
        for v in page.Views:     # dimensions, notes... belong to the sheet
            shown.add(v.Name)
            for o in v.InList:
                if o.isDerivedFrom("TechDraw::DrawView"):
                    shown.add(o.Name)

    # ------------------------------------------------------------ anything else
    def _others(self, top, doc, shown):
        for o in doc.RootObjects:
            if o.Name in shown or o.isDerivedFrom("App::Origin") or o.isDerivedFrom("App::OriginFeature"):
                continue
            self._generic(top, o, shown)

    def _generic(self, parent, o, shown, depth=0):
        shown.add(o.Name)
        it = self._add(parent, o.Label, obj_icon(o), "object", o)
        if depth > 4:
            return
        try:
            kids = o.ViewObject.claimChildren() if o.ViewObject is not None else []
        except Exception:
            kids = []
        for k in kids or []:
            if hasattr(k, "Name") and k.Name not in shown:
                self._generic(it, k, shown, depth + 1)

    # ------------------------------------------------------------ filter
    def apply_filter(self, text):
        self.filter_text = text = (text or "").strip().lower()

        def walk(it):
            any_child = False
            for i in range(it.childCount()):
                any_child = walk(it.child(i)) or any_child
            kind = it.data(0, KIND)
            if kind == "doc":
                it.setHidden(False)
                return True
            show = not text or (kind != "bar" and text in it.text(0).lower()) or any_child
            it.setHidden(not show)
            if text and any_child:
                it.setExpanded(True)
            return show

        for i in range(self.topLevelItemCount()):
            walk(self.topLevelItem(i))

    # ------------------------------------------------------------ selection
    def _items(self):
        it = QtWidgets.QTreeWidgetItemIterator(self)
        while it.value():
            yield it.value()
            it += 1

    def _push_selection(self):
        if self.syncing:
            return
        self.pushing = True
        try:
            Gui.Selection.clearSelection()
            for item in self.selectedItems():
                o = self.obj_of(item)
                if o is not None:
                    try:
                        Gui.Selection.addSelection(o)
                    except Exception:
                        Gui.Selection.addSelection(o.Document.Name, o.Name)
        finally:
            self.pushing = False
        _context_bar_for(self)

    def pull_selection(self):
        if self.pushing or self.renaming is not None:
            return
        try:
            sel = Gui.Selection.getSelectionEx("", 1)
        except Exception:
            sel = []
        want = set()
        for s in sel:
            want.add((s.DocumentName, s.ObjectName))
            try:
                for name in s.SubElementNames:
                    # a face picked on a body: highlight the feature that made it
                    parts = [p for p in name.split(".") if p][:-1] if name else []
                    for p in parts:
                        want.add((s.DocumentName, p))
            except Exception:
                pass
        self.syncing = True
        try:
            first = None
            for item in self._items():
                ref = item.data(0, OBJ)
                on = bool(ref) and tuple(ref) in want and item.data(0, KIND) not in ("bar", "ref", "doc")
                if item.isSelected() != on:
                    item.setSelected(on)
                if on and first is None:
                    first = item
            if first is not None:
                p = first.parent()
                while p is not None:
                    p.setExpanded(True)
                    p = p.parent()
                self.scrollToItem(first)
        finally:
            self.syncing = False

    def _hover(self, item, _col=0):
        o = self.obj_of(item)
        key = (o.Document.Name, o.Name) if o is not None else None
        if key == self.hover_key:
            return
        self.hover_key = key
        try:
            Gui.Selection.removePreselection()
            if o is not None and item.data(0, KIND) not in ("bar", "material"):
                Gui.Selection.setPreselection(o)
        except Exception:
            pass

    def leaveEvent(self, e):
        self.hover_key = None
        try:
            Gui.Selection.removePreselection()
        except Exception:
            pass
        self.bar_hot = False
        self.viewport().update()
        super().leaveEvent(e)

    # ------------------------------------------------------------ actions
    def _double_clicked(self, item, _col=0):
        kind = item.data(0, KIND)
        o = self.obj_of(item)
        if kind in ("folder", "doc") and o is None:
            item.setExpanded(not item.isExpanded())
            return
        if kind == "material":
            _set_material(self)
            return
        if o is None or kind in ("bar", "plane", "origin", "ref", "doc"):
            return
        edit(o)

    def _item_changed(self, item, _col):
        if self.renaming is None or item is not self.renaming:
            return
        o = self.obj_of(item)
        text = item.text(0).strip()
        self.renaming = None
        if o is not None and text and text != o.Label:
            doc = o.Document
            doc.openTransaction("Rename")
            o.Label = text
            doc.commitTransaction()
        schedule_rebuild()

    def _end_rename(self):
        if self.renaming is not None:
            self.renaming = None
            schedule_rebuild()

    def rename(self, item):
        o = self.obj_of(item)
        if o is None or not (item.flags() & QtCore.Qt.ItemIsEditable):
            return
        self.syncing = True
        item.setText(0, o.Label)
        self.syncing = False
        self.renaming = item
        self.editItem(item, 0)

    def keyPressEvent(self, e):
        if e.key() == QtCore.Qt.Key_F2 and self.currentItem() is not None:
            self.rename(self.currentItem())
            return
        if e.key() == QtCore.Qt.Key_Delete and self.selectedItems():
            _run("Std_Delete")
            return
        super().keyPressEvent(e)

    def _context_menu(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return
        if not item.isSelected() and item.data(0, KIND) != "bar":
            self.setCurrentItem(item)
        menu = QtWidgets.QMenu(self)
        for entry in actions_for(self, item):
            if entry is None:
                menu.addSeparator()
            else:
                text, ic, fn = entry
                a = menu.addAction(ic, text) if ic is not None else menu.addAction(text)
                a.triggered.connect(fn)
        if not menu.isEmpty():
            menu.exec_(self.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------ rollback bar dragging
    def mousePressEvent(self, e):
        item = self.itemAt(e.pos())
        if e.button() == QtCore.Qt.LeftButton and item is not None and item.data(0, KIND) == "bar":
            self.dragging = True
            self.drag_body = self.obj_of(item)
            self.viewport().setCursor(QtCore.Qt.ClosedHandCursor)
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.dragging:
            self.drop_line = self._drop_y(e.pos())
            self.viewport().update()
            return
        item = self.itemAt(e.pos())
        hot = item is not None and item.data(0, KIND) == "bar"
        if hot != self.bar_hot:
            self.bar_hot = hot
            if hot:
                self.viewport().setCursor(QtCore.Qt.OpenHandCursor)
            else:
                self.viewport().unsetCursor()
            self.viewport().update()
        super().mouseMoveEvent(e)

    def _drop_y(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return None
        r = self.visualItemRect(item)
        return r.top() if pos.y() < r.center().y() else r.bottom()

    def mouseReleaseEvent(self, e):
        if self.dragging:
            self.dragging = False
            self.drop_line = None
            self.viewport().unsetCursor()
            body = getattr(self, "drag_body", None)
            target = self._tip_at(e.pos(), body)
            self.viewport().update()
            if body is not None and target is not False:
                roll_to(body, target)
            return
        super().mouseReleaseEvent(e)

    def _tip_at(self, pos, body):
        """The feature the rollback bar dropped at `pos` should follow (None = before all), False = no change."""
        if body is None:
            return False
        item = self.itemAt(pos)
        if item is None:
            return False
        while item.parent() is not None and item.parent().data(0, KIND) in ("feature", "sketch", "datum"):
            item = item.parent()
        above = pos.y() < self.visualItemRect(item).center().y()
        order = [o for o in body.Group if not o.isDerivedFrom("App::Origin")]
        o = self.obj_of(item)
        if o is None or o not in order:
            kind = item.data(0, KIND)
            if kind == "bar":
                return False
            # dropped on the planes/folders above the features: roll back to the start
            return None if self._is_above_features(item, body) else False
        idx = order.index(o) - (1 if above else 0)
        while idx >= 0 and not is_solid_feature(order[idx]):
            idx -= 1
        return order[idx] if idx >= 0 else None

    def _is_above_features(self, item, body):
        first = None
        for it in self._items():
            if self.obj_of(it) in body.Group and it.data(0, KIND) in ("feature", "sketch", "datum"):
                first = it
                break
        if first is None:
            return False
        return self.visualItemRect(item).top() < self.visualItemRect(first).top()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.dragging and self.drop_line is not None:
            p = QtGui.QPainter(self.viewport())
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor("#1f5fbf"))
            p.drawRect(QtCore.QRect(4, self.drop_line - 2, self.viewport().width() - 8, 4))
            p.end()


# ======================================================================
# Commands used by the tree
# ======================================================================

def _run(cmd):
    try:
        Gui.runCommand(cmd, 0)
    except Exception as e:
        App.Console.PrintError("SolidStyle: %s failed: %s\n" % (cmd, e))


def _select_only(o):
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(o)


def edit(o):
    gdoc = Gui.getDocument(o.Document.Name)
    if o.isDerivedFrom("TechDraw::DrawPage"):
        o.ViewObject.doubleClicked()
        return
    if gdoc.getInEdit() is not None:
        gdoc.resetEdit()
    try:
        gdoc.setEdit(o.Name)       # SolidStyle swaps in its own panel for features it knows
    except Exception as e:
        App.Console.PrintWarning("SolidStyle: cannot edit %s: %s\n" % (o.Label, e))


def sketches_of(f):
    return [o for o in f.OutList if o.TypeId == "Sketcher::SketchObject"]


def body_of(o):
    try:
        b = o.getParentGeoFeatureGroup()
    except Exception:
        b = None
    while b is not None and b.TypeId != "PartDesign::Body":
        b = b.getParentGeoFeatureGroup()
    return b


def roll_to(body, feat):
    """Move the rollback bar: features after `feat` are rolled back (feat None = before all)."""
    if body.Tip is feat:
        return
    doc = body.Document
    doc.openTransaction("Rollback")
    try:
        old = body.Tip
        body.Tip = feat
        if old is not None:
            old.Visibility = False
        if feat is not None:
            feat.Visibility = True
        doc.recompute()
    except Exception as e:
        App.Console.PrintError("SolidStyle: rollback failed: %s\n" % e)
    doc.commitTransaction()
    schedule_rebuild()


def _solid_before(body, o):
    order = [x for x in body.Group if is_solid_feature(x)]
    i = order.index(o) if o in order else len(order)
    return order[i - 1] if i > 0 else None


def toggle_suppress(o):
    doc = o.Document
    doc.openTransaction("Suppress" if not o.Suppressed else "Unsuppress")
    o.Suppressed = not o.Suppressed
    doc.recompute()
    doc.commitTransaction()


def toggle_visibility(o):
    o.Visibility = not o.Visibility


def _set_material(tree):
    doc = App.ActiveDocument
    bodies = [o for o in doc.Objects if o.TypeId == "PartDesign::Body"] if doc else []
    if bodies:
        Gui.Selection.clearSelection()
        for b in bodies:
            Gui.Selection.addSelection(b)
    for cmd in ("Std_SetMaterial", "Material_Edit", "SS_MassProperties"):
        if cmd in Gui.listCommands():
            _run(cmd)
            return


def actions_for(tree, item):
    """Context menu / context toolbar entries: (text, icon, callable) or None for a separator."""
    kind = item.data(0, KIND)
    o = tree.obj_of(item)
    out = []
    if kind == "bar":
        body = o
        if body is not None:
            feats = [x for x in body.Group if is_solid_feature(x)]
            if body.Tip is not None and body.Tip in feats:
                prev = _solid_before(body, body.Tip)
                out.append(("Roll to Previous", icon("sw/PartDesign_MoveTip"), lambda: roll_to(body, prev)))
            i = feats.index(body.Tip) if body.Tip in feats else -1
            if i + 1 < len(feats):
                out.append(("Roll Forward", None, lambda: roll_to(body, feats[i + 1])))
                out.append(("Roll to End", None, lambda: roll_to(body, feats[-1])))
        return out
    if kind == "material":
        return [("Edit Material...", icon("tree/material"), lambda: _set_material(tree))]
    if kind == "doc":
        return [("Rebuild", icon("sw/SS_Rebuild"), lambda: _run("SS_Rebuild")),
                ("Mass Properties...", None, lambda: _run("SS_MassProperties"))]
    if o is None:
        return out
    if kind in ("feature", "datum", "mate", "view", "object", "component", "page"):
        out.append(("Edit Feature", icon("tree/edit_feature"), lambda: edit(o)))
    sk = [o] if o.TypeId == "Sketcher::SketchObject" else sketches_of(o) if kind == "feature" else []
    if sk:
        out.append(("Edit Sketch", icon("tree/edit_sketch"), lambda: edit(sk[0])))
    if kind in ("plane",) or o.TypeId == "PartDesign::Plane":
        out.append(("Sketch", icon("sw/PartDesign_NewSketch"),
                    lambda: (_select_only(o), _run("PartDesign_NewSketch"))))
    if kind in ("plane", "sketch") or o.TypeId == "PartDesign::Plane":
        out.append(("Normal To", icon("NormalTo"), lambda: (_select_only(o), _run("SS_NormalTo"))))
    if hasattr(o, "Visibility") and kind not in ("mate", "page", "template", "view"):
        out.append(("Show" if not o.Visibility else "Hide", icon("sw/Std_ToggleVisibility"),
                    lambda: toggle_visibility(o)))
    if hasattr(o, "Suppressed") and kind == "feature":
        out.append(("Unsuppress" if o.Suppressed else "Suppress", icon("tree/suppress"),
                    lambda: toggle_suppress(o)))
    body = body_of(o) if kind in ("feature", "sketch", "datum") else None
    if body is not None and is_solid_feature(o):
        out.append(("Rollback", icon("sw/PartDesign_MoveTip"), lambda: roll_to(body, _solid_before(body, o))))
    out.append(None)
    if kind in ("feature", "datum", "component", "ref", "object", "plane"):
        out.append(("Appearance...", icon("sw/Std_SetAppearance"), lambda: (_select_only(o), _run("Std_SetAppearance"))))
    if item.flags() & QtCore.Qt.ItemIsEditable:
        out.append(("Rename (F2)", None, lambda: tree.rename(item)))
    if kind not in ("plane", "origin", "ref", "template"):
        out.append(("Delete...", None, lambda: (_select_only(o), _run("Std_Delete"))))
    out.append(None)
    out.append(("Properties (FreeCAD)...", icon("tree/fc_tree"), lambda: _panel.show_classic(o) if _panel else None))
    return out


# ======================================================================
# Context toolbar (SolidWorks pops a few icons up next to a clicked feature)
# ======================================================================

class ContextBar(QtWidgets.QFrame):
    def __init__(self):
        super().__init__(None, QtCore.Qt.ToolTip | QtCore.Qt.FramelessWindowHint)
        self.setObjectName("SS_ContextBar")
        self.setStyleSheet("QFrame#SS_ContextBar{background:#fafafa;border:1px solid #9aa1ab;border-radius:3px;}"
                           "QToolButton{border:1px solid transparent;border-radius:2px;padding:2px;}"
                           "QToolButton:hover{background:#e5f1fb;border:1px solid #7ab8f5;}")
        self.lay = QtWidgets.QHBoxLayout(self)
        self.lay.setContentsMargins(2, 2, 2, 2)
        self.lay.setSpacing(1)
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def show_for(self, tree, item):
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        entries = [e for e in actions_for(tree, item) if e is not None and e[1] is not None
                   and not e[0].startswith(("Delete", "Rename", "Properties", "Appearance"))]
        if not entries:
            self.hide()
            return
        s = tree.iconSize().width() + 4
        for text, ic, fn in entries:
            b = QtWidgets.QToolButton(self)
            b.setIcon(ic)
            b.setIconSize(QtCore.QSize(s, s))
            b.setToolTip(text)
            b.setAutoRaise(True)
            b.clicked.connect(lambda checked=False, f=fn: (self.hide(), f()))
            self.lay.addWidget(b)
        self.adjustSize()
        r = tree.visualItemRect(item)
        pt = tree.viewport().mapToGlobal(QtCore.QPoint(r.left() + 24, r.top() - self.height() - 2))
        if pt.y() < tree.mapToGlobal(QtCore.QPoint(0, 0)).y():
            pt = tree.viewport().mapToGlobal(QtCore.QPoint(r.left() + 24, r.bottom() + 2))
        self.move(pt)
        self.show()
        self.raise_()
        self.timer.start(4000)


_context_bar = None


def _context_bar_for(tree):
    global _context_bar
    items = tree.selectedItems()
    if len(items) != 1 or not tree.underMouse():
        if _context_bar is not None:
            _context_bar.hide()
        return
    if _context_bar is None:
        _context_bar = ContextBar()
    QtCore.QTimer.singleShot(250, lambda it=items[0]: _maybe_show_bar(tree, it))


def _maybe_show_bar(tree, item):
    try:
        if tree.selectedItems() == [item] and tree.underMouse() and tree.renaming is None:
            _context_bar.show_for(tree, item)
    except RuntimeError:     # item deleted by a rebuild
        pass


# ======================================================================
# The panel and installing it in place of the Model tree
# ======================================================================

class Panel(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("SS_FeatureManager")
        self.stack = QtWidgets.QStackedWidget(self)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.stack)

        page = QtWidgets.QWidget()
        page.setAutoFillBackground(True)
        pal = page.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#ffffff"))
        page.setPalette(pal)
        v = QtWidgets.QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(4, 3, 4, 3)
        row.setSpacing(3)
        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText("Filter")
        self.filter.setClearButtonEnabled(True)
        self.filter.addAction(icon("tree/filter"), QtWidgets.QLineEdit.LeadingPosition)
        self.filter.setStyleSheet("QLineEdit{background:#fff;color:#222;border:1px solid #c3c8cf;"
                                  "border-radius:2px;padding:1px 2px;}")
        row.addWidget(self.filter, 1)
        self.classic_btn = QtWidgets.QToolButton()
        self.classic_btn.setIcon(icon("tree/fc_tree"))
        self.classic_btn.setToolTip("Show FreeCAD's model tree and property editor")
        self.classic_btn.setAutoRaise(True)
        self.classic_btn.clicked.connect(lambda: self.show_classic())
        row.addWidget(self.classic_btn)
        v.addLayout(row)
        self.tree = FeatureTree(page)
        v.addWidget(self.tree, 1)
        self.stack.addWidget(page)
        self.filter.textChanged.connect(self.tree.apply_filter)

        # FreeCAD's original panel goes on page 2, with a way back
        self.classic_page = QtWidgets.QWidget()
        cv = QtWidgets.QVBoxLayout(self.classic_page)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        back = QtWidgets.QToolButton()
        back.setIcon(icon("tree/part"))
        back.setText("Back to FeatureManager")
        back.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        back.setAutoRaise(True)
        back.clicked.connect(self.show_tree)
        cv.addWidget(back)
        self.classic = None
        self.stack.addWidget(self.classic_page)

    def hold_classic(self, w):
        self.classic = w
        self.classic_page.layout().addWidget(w, 1)
        w.show()

    def release_classic(self):
        w, self.classic = self.classic, None
        if w is not None:
            self.classic_page.layout().removeWidget(w)
        return w

    def show_classic(self, obj=None):
        if obj is not None:
            _select_only(obj)
        if self.classic is not None:
            self.stack.setCurrentIndex(1)

    def show_tree(self):
        self.stack.setCurrentIndex(0)
        schedule_rebuild()


_panel = None
_orig = None
_titles = {}
_rebuild_timer = None
_sel_timer = None
_doc_obs = None
_sel_obs = None


def _dock(name):
    mw = Gui.getMainWindow()
    for d in mw.findChildren(QtWidgets.QDockWidget):
        if d.objectName() == name:
            return d
    return None


def schedule_rebuild(ms=60):
    if _rebuild_timer is not None and _panel is not None:
        _rebuild_timer.start(ms)


def _rebuild():
    if _panel is not None and _panel.isVisible():
        _panel.tree.rebuild()


def _sync_selection():
    if _panel is not None and _panel.isVisible():
        _panel.tree.pull_selection()


class _DocObserver:
    def slotCreatedObject(self, obj):
        schedule_rebuild()

    def slotDeletedObject(self, obj):
        schedule_rebuild()

    def slotChangedObject(self, obj, prop):
        if prop in WATCH:
            schedule_rebuild()

    def slotRecomputedDocument(self, doc):
        schedule_rebuild()

    def slotActivateDocument(self, doc):
        schedule_rebuild(0)

    def slotCreatedDocument(self, doc):
        schedule_rebuild()

    def slotDeletedDocument(self, doc):
        schedule_rebuild()

    def slotRelabelDocument(self, doc):
        schedule_rebuild()

    def slotUndoDocument(self, doc):
        schedule_rebuild()

    def slotRedoDocument(self, doc):
        schedule_rebuild()

    def slotFinishRestoreDocument(self, doc):
        schedule_rebuild()


class _SelObserver:
    def _later(self):
        if _panel is not None and not _panel.tree.pushing and _sel_timer is not None:
            _sel_timer.start(0)

    def addSelection(self, doc, obj, sub, pnt):
        self._later()

    def removeSelection(self, doc, obj, sub):
        self._later()

    def setSelection(self, doc):
        self._later()

    def clearSelection(self, doc):
        self._later()


def install():
    """Put the FeatureManager in the Model panel (called when the workbench is activated)."""
    global _panel, _orig, _rebuild_timer, _sel_timer, _doc_obs, _sel_obs
    dock = _dock("Model")
    if dock is None:
        App.Console.PrintLog("SolidStyle: no Model panel, FeatureManager not installed\n")
        return
    if _panel is None:
        _panel = Panel()
        _rebuild_timer = QtCore.QTimer()
        _rebuild_timer.setSingleShot(True)
        _rebuild_timer.timeout.connect(_rebuild)
        _sel_timer = QtCore.QTimer()
        _sel_timer.setSingleShot(True)
        _sel_timer.timeout.connect(_sync_selection)
    if dock.widget() is not _panel:
        _orig = dock.widget()
        dock.setWidget(_panel)
        _panel.hold_classic(_orig)
    _panel.stack.setCurrentIndex(0)
    for name, title in (("Model", "FeatureManager"), ("Tasks", "PropertyManager")):
        d = _dock(name)
        if d is not None:
            _titles.setdefault(name, d.windowTitle())
            d.setWindowTitle(title)
    if _doc_obs is None:
        _doc_obs = _DocObserver()
        App.addDocumentObserver(_doc_obs)
        _sel_obs = _SelObserver()
        Gui.Selection.addObserver(_sel_obs)
    schedule_rebuild(0)


def uninstall():
    """Give FreeCAD its own tree back (workbench deactivated)."""
    global _doc_obs, _sel_obs
    if _doc_obs is not None:
        App.removeDocumentObserver(_doc_obs)
        Gui.Selection.removeObserver(_sel_obs)
        _doc_obs = _sel_obs = None
    if _context_bar is not None:
        _context_bar.hide()
    dock = _dock("Model")
    if dock is not None and _panel is not None and dock.widget() is _panel:
        w = _panel.release_classic()
        _panel.setParent(None)
        if w is not None:
            dock.setWidget(w)
            w.show()
    for name, title in _titles.items():
        d = _dock(name)
        if d is not None:
            d.setWindowTitle(title)
    _titles.clear()
