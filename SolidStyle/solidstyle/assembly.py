"""SolidWorks-style assemblies.

The SolidWorks workflow on top of FreeCAD's Assembly workbench:
  * New Assembly opens a new assembly document and goes straight to Insert Components
    (SolidWorks' "Begin Assembly");
  * Insert Components is a PropertyManager listing the part files next to the assembly
    (with thumbnails) and the parts already open: pick one or more, click Insert, repeat.
    The first component is fixed at the origin, the next ones are set down beside it;
  * Mate is a PropertyManager with SolidWorks' mate buttons. Click two faces/edges and it
    picks the mate (concentric for round things, coincident otherwise), OK adds it and the
    panel stays open for the next mate, like SolidWorks' pushpin.
FreeCAD's gates (assembly must be activated, one part grounded, document saved before
linking other files) are taken care of along the way.
"""
import os
import zipfile

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

SW_ICONS = os.path.join(os.path.dirname(__file__), "icons", "sw")
ASM_PREFS = "User parameter:BaseApp/Preferences/Mod/Assembly"
PARAMS = "User parameter:BaseApp/Preferences/Mod/SolidStyle"

# SolidStyle command -> (FreeCAD joint type index, menu text, tooltip)
MATES = {
    "Assembly_CreateJointFixed": (0, "Lock (Fixed)", "Locks two components together."),
    "Assembly_CreateJointRevolute": (1, "Concentric + Coincident (Revolute)",
                                     "Concentric and coincident: the part can only spin about the axis."),
    "Assembly_CreateJointCylindrical": (2, "Concentric (Cylindrical)", "Concentric: spin and slide along the axis."),
    "Assembly_CreateJointSlider": (3, "Slider", "Slide along one direction only."),
    "Assembly_CreateJointBall": (4, "Ball", "Coincident points: free rotation about a point."),
    "Assembly_CreateJointDistance": (5, "Coincident / Distance", "Coincident (distance 0) or a distance mate."),
    "Assembly_CreateJointParallel": (6, "Parallel", "Parallel faces or edges."),
    "Assembly_CreateJointPerpendicular": (7, "Perpendicular", "Perpendicular faces or edges."),
    "Assembly_CreateJointAngle": (8, "Angle", "Angle between faces or edges."),
    "Assembly_CreateJointRackPinion": (9, "Rack Pinion", "Rack and pinion mechanical mate."),
    "Assembly_CreateJointScrew": (10, "Screw", "Screw mechanical mate."),
    "Assembly_CreateJointGears": (11, "Gear", "Gear mechanical mate."),
    "Assembly_CreateJointBelt": (12, "Belt / Pulley", "Belt / pulley mechanical mate."),
}

PM_STYLE = """
QGroupBox { font-weight: bold; border: 1px solid #9aa4b1; border-radius: 4px; margin-top: 16px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 8px; top: 2px; padding: 0 4px; }
"""
HINT_STYLE = "QLabel{background:#fff8d6;color:#222;border:1px solid #e0c34a;border-radius:4px;padding:6px}"


def _modules():
    import UtilsAssembly
    import CommandCreateJoint
    return UtilsAssembly, CommandCreateJoint


def _icon(name):
    p = os.path.join(SW_ICONS, name + ".svg")
    if os.path.exists(p):
        return QtGui.QIcon(p)
    return QtGui.QIcon(":/icons/%s.svg" % name)


def find_assembly(doc=None):
    """The active assembly, else the first assembly in the document."""
    doc = doc or App.ActiveDocument
    if doc is None:
        return None
    gdoc = Gui.getDocument(doc.Name)
    view = gdoc.ActiveView if gdoc else None
    act = view.getActiveObject("part") if view is not None and hasattr(view, "getActiveObject") else None
    if act is not None and act.isDerivedFrom("Assembly::AssemblyObject"):
        return act
    for o in doc.Objects:
        if o.isDerivedFrom("Assembly::AssemblyObject"):
            return o
    return None


def activate(asm):
    """Put the assembly in edit mode (FreeCAD's 'active assembly')."""
    gdoc = Gui.getDocument(asm.Document.Name)
    vp = gdoc.getInEdit()
    if vp is not None and getattr(vp, "Object", None) == asm:
        return True
    if vp is not None:
        gdoc.resetEdit()
    gdoc.setEdit(asm)
    return asm.ViewObject.isInEditMode()


def components(asm):
    # same rule FreeCAD uses: anything placed, minus the grounded-joint entries
    return [o for o in asm.OutList if hasattr(o, "Placement") and not hasattr(o, "ObjectToGround")
            and not o.isDerivedFrom("App::LocalCoordinateSystem") and not o.isDerivedFrom("App::DatumElement")]


def is_grounded(asm):
    jg = [o for o in asm.Group if o.isDerivedFrom("Assembly::JointGroup")]
    return bool(jg) and any(hasattr(j, "ObjectToGround") for j in jg[0].Group)


def ensure_fixed(asm):
    """Fix the first component when nothing is fixed yet, like SolidWorks does."""
    if is_grounded(asm):
        return None
    comps = components(asm)
    if not comps:
        return None
    _u, ccj = _modules()
    asm.Document.openTransaction("Fix first component")
    ccj.createGroundedJoint(comps[0])
    asm.Document.commitTransaction()
    App.Console.PrintMessage("SolidStyle: fixed %s (first component)\n" % comps[0].Label)
    return comps[0]


def _tell(text):
    QtWidgets.QMessageBox.information(Gui.getMainWindow(), "Assembly", text)


def _status(msg, ms=8000):
    try:
        Gui.getMainWindow().statusBar().showMessage(msg, ms)
    except Exception:
        pass


def _ready(need_parts=0):
    """Activate the assembly and check it has enough parts. Returns it or None."""
    asm = find_assembly()
    if asm is None:
        _tell("There is no assembly in this document.\nUse New Assembly first.")
        return None
    if not activate(asm):
        _tell("Could not activate %s." % asm.Label)
        return None
    if need_parts and len(components(asm)) < need_parts:
        _tell("Insert at least %d components first (Insert Components)." % need_parts)
        return None
    return asm


def _close_open_dialog():
    """Close the task panel in the way (FreeCAD's own panel, or one of ours)."""
    if not Gui.Control.activeDialog():
        return True
    try:
        import JointObject
        if JointObject.activeTask:
            JointObject.activeTask.reject()
    except Exception:
        pass
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
    return not Gui.Control.activeDialog()


# ======================================================================
# New Assembly
# ======================================================================

def new_assembly():
    """New assembly document, then straight into Insert Components (SolidWorks' Begin Assembly)."""
    _modules()
    from solidstyle import commands, ui
    name = commands._next_name("Assem")
    doc = App.newDocument(name)
    doc.Label = name
    doc.openTransaction("New Assembly")
    asm = doc.addObject("Assembly::AssemblyObject", "Assembly")
    asm.Type = "Assembly"
    asm.Label = name
    asm.newObject("Assembly::JointGroup", "Joints")
    doc.commitTransaction()
    doc.recompute()
    Gui.ActiveDocument.ActiveView.viewIsometric()
    activate(asm)
    ui.select_tab("Assembly")
    QtCore.QTimer.singleShot(0, lambda: show_insert(asm))


# ======================================================================
# Insert Components
# ======================================================================

def _thumbnail(path):
    """The preview picture FreeCAD saves inside a .FCStd file."""
    try:
        with zipfile.ZipFile(path) as z:
            data = z.read("thumbnails/Thumbnail.png")
        pm = QtGui.QPixmap()
        if pm.loadFromData(data):
            return QtGui.QIcon(pm)
    except Exception:
        pass
    return QtGui.QIcon(":/icons/Document.svg")


def _same_file(a, b):
    try:
        return bool(a) and bool(b) and os.path.samefile(a, b)
    except OSError:
        return os.path.abspath(a) == os.path.abspath(b)


def _open_doc_for(path):
    for d in App.listDocuments().values():
        if _same_file(d.FileName, path):
            return d
    return None


def _shape_ok(o):
    try:
        import Part
        s = Part.getShape(o)
        return not s.isNull() and bool(s.Faces)
    except Exception:
        return False


def insertable(doc, exclude=None):
    """What to link from `doc`: its assembly, else its part(s): an App::Part, else visible bodies/solids."""
    # doc.RootObjects drops anything another file links to (our own links!), so judge by this file only
    roots = [o for o in doc.Objects if o is not exclude and not any(p.Document is doc for p in o.InList)]
    asms = [o for o in roots if o.isDerivedFrom("Assembly::AssemblyObject")]
    if asms:
        return asms[:1]
    if exclude is not None:
        roots = [o for o in roots if exclude not in o.InListRecursive]

    def shown(o):
        vo = getattr(o, "ViewObject", None)
        return vo is None or vo.Visibility

    parts = [o for o in roots if o.isDerivedFrom("App::Part") and _shape_ok(o)]
    if len(parts) == 1:
        return parts
    solids = [o for o in roots if (o.isDerivedFrom("PartDesign::Body") or o.isDerivedFrom("Part::Feature")
                                   or o.isDerivedFrom("App::Part")) and _shape_ok(o)]
    vis = [o for o in solids if shown(o)]
    return vis or solids


def _bound_box(objs):
    import Part
    bb = None
    for o in objs:
        try:
            s = Part.getShape(o)
        except Exception:
            continue
        if s.isNull():
            continue
        b = s.BoundBox
        if bb is None:
            bb = App.BoundBox(b)
        else:
            bb.add(b)
    return bb


class InsertPanel:
    """SolidWorks' Insert Component PropertyManager."""

    def __init__(self, asm):
        self.asm = asm
        self.doc = asm.Document
        self.inserted = []
        self.folder = self._start_folder()

        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("Insert Component")
        self.form.setWindowIcon(_icon("Assembly_InsertLink"))
        self.form.setStyleSheet(PM_STYLE)
        lay = QtWidgets.QVBoxLayout(self.form)

        hint = QtWidgets.QLabel("Pick a part (or several with Ctrl), then click <b>Insert</b>. "
                                "Keep inserting as many as you like. The first one is fixed at the origin.")
        hint.setWordWrap(True)
        hint.setStyleSheet(HINT_STYLE)
        lay.addWidget(hint)

        g = QtWidgets.QGroupBox("Part/Assembly to Insert")
        v = QtWidgets.QVBoxLayout(g)
        row = QtWidgets.QHBoxLayout()
        self.folder_lbl = QtWidgets.QLabel()
        self.folder_lbl.setStyleSheet("color:#555")
        row.addWidget(self.folder_lbl, 1)
        fbtn = QtWidgets.QToolButton()
        fbtn.setText("Folder...")
        fbtn.setToolTip("Show the parts in another folder")
        fbtn.clicked.connect(self._pick_folder)
        row.addWidget(fbtn)
        v.addLayout(row)

        self.list = QtWidgets.QListWidget()
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.list.setIconSize(QtCore.QSize(56, 56))
        self.list.setSpacing(1)
        self.list.setMinimumHeight(260)
        self.list.itemDoubleClicked.connect(lambda _it: self.insert())
        self.list.itemSelectionChanged.connect(self._sel_changed)
        v.addWidget(self.list, 1)

        row = QtWidgets.QHBoxLayout()
        browse = QtWidgets.QPushButton("Browse...")
        browse.setToolTip("Insert part files from anywhere")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        row.addStretch(1)
        row.addWidget(QtWidgets.QLabel("Copies"))
        self.copies = QtWidgets.QSpinBox()
        self.copies.setRange(1, 100)
        row.addWidget(self.copies)
        v.addLayout(row)

        self.insert_btn = QtWidgets.QPushButton("  Insert")
        self.insert_btn.setIcon(_icon("Assembly_InsertLink"))
        self.insert_btn.setIconSize(QtCore.QSize(24, 24))
        self.insert_btn.setMinimumHeight(40)
        self.insert_btn.setStyleSheet("QPushButton{font-weight:bold;font-size:12pt}")
        self.insert_btn.setEnabled(False)
        self.insert_btn.clicked.connect(self.insert)
        v.addWidget(self.insert_btn)
        lay.addWidget(g, 1)

        g2 = QtWidgets.QGroupBox("In this Assembly")
        v2 = QtWidgets.QVBoxLayout(g2)
        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        v2.addWidget(self.summary)
        row = QtWidgets.QHBoxLayout()
        self.undo_btn = QtWidgets.QPushButton("Undo Last")
        self.undo_btn.clicked.connect(self._undo_last)
        row.addWidget(self.undo_btn)
        row.addStretch(1)
        self.mate_btn = QtWidgets.QPushButton("  Next: Add Mates")
        self.mate_btn.setIcon(_icon("Assembly_CreateJointDistance"))
        self.mate_btn.setToolTip("Close this and start mating the components")
        self.mate_btn.clicked.connect(self._to_mates)
        row.addWidget(self.mate_btn)
        v2.addLayout(row)
        lay.addWidget(g2)

        self.fill()
        self._update_summary()

    # ---------------------------------------------------------------- list
    def _start_folder(self):
        if self.doc.FileName:
            return os.path.dirname(self.doc.FileName)
        last = App.ParamGet(PARAMS).GetString("InsertFolder", "")
        if last and os.path.isdir(last):
            return last
        for d in App.listDocuments().values():
            if d.FileName and d is not self.doc:
                return os.path.dirname(d.FileName)
        return os.path.expanduser("~")

    def fill(self, select_path=None):
        self.list.clear()
        self.folder_lbl.setText(self._short(self.folder))
        self.folder_lbl.setToolTip(self.folder)
        seen = set()
        own = self.doc.FileName

        def add(text, icon, data, tip):
            it = QtWidgets.QListWidgetItem(icon, text)
            it.setData(QtCore.Qt.UserRole, data)
            it.setToolTip(tip)
            self.list.addItem(it)
            return it

        def header(text):
            it = QtWidgets.QListWidgetItem(text)
            it.setFlags(QtCore.Qt.NoItemFlags)
            f = it.font()
            f.setBold(True)
            it.setFont(f)
            it.setForeground(QtGui.QBrush(QtGui.QColor("#555")))
            self.list.addItem(it)

        opened = [d for d in App.listDocuments().values() if d is not self.doc and insertable(d)]
        if opened:
            header("Open documents")
            for d in sorted(opened, key=lambda d: d.Label.lower()):
                if d.FileName:
                    seen.add(os.path.abspath(d.FileName))
                icon = _thumbnail(d.FileName) if d.FileName else QtGui.QIcon(":/icons/Document.svg")
                add(d.Label + ("" if d.FileName else "   (not saved yet)"), icon, ("doc", d.Name),
                    d.FileName or "Unsaved document - it will be saved when you insert it")
        files = []
        try:
            for n in os.listdir(self.folder):
                p = os.path.join(self.folder, n)
                if n.lower().endswith(".fcstd") and os.path.isfile(p) and os.path.abspath(p) not in seen \
                        and not _same_file(p, own):
                    files.append(p)
        except OSError:
            pass
        if files:
            header("Files in this folder")
            for p in sorted(files, key=lambda p: os.path.basename(p).lower()):
                it = add(os.path.splitext(os.path.basename(p))[0], _thumbnail(p), ("file", p), p)
                if select_path and _same_file(p, select_path):
                    it.setSelected(True)
        if self.list.count() == 0:
            header("No FreeCAD parts here - use Folder... or Browse...")

    @staticmethod
    def _short(path):
        home = os.path.expanduser("~")
        return "~" + path[len(home):] if path.startswith(home) else path

    def _sel_changed(self):
        self.insert_btn.setEnabled(bool(self.list.selectedItems()))

    def _pick_folder(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(Gui.getMainWindow(), "Folder with parts", self.folder)
        if d:
            self.folder = d
            App.ParamGet(PARAMS).SetString("InsertFolder", d)
            self.fill()

    def _browse(self):
        files, _f = QtWidgets.QFileDialog.getOpenFileNames(
            Gui.getMainWindow(), "Insert Component", self.folder, "FreeCAD parts (*.FCStd *.fcstd)")
        if not files:
            return
        self.folder = os.path.dirname(files[0])
        App.ParamGet(PARAMS).SetString("InsertFolder", self.folder)
        self._insert_sources([("file", f) for f in files])
        self.fill()

    # ---------------------------------------------------------------- inserting
    def insert(self):
        sources = [it.data(QtCore.Qt.UserRole) for it in self.list.selectedItems()]
        sources = [s for s in sources if s]
        if sources:
            self._insert_sources(sources)

    def _resolve(self, src):
        kind, ref = src
        if kind == "doc":
            return App.listDocuments().get(ref)
        d = _open_doc_for(ref)
        if d is None:
            d = App.openDocument(ref, True)       # hidden, like FreeCAD's own insert
        return d

    def _ensure_saved(self, src_doc):
        """FreeCAD links other files by relative path, so both files need a name on disk."""
        if not src_doc.FileName:
            QtWidgets.QMessageBox.information(
                Gui.getMainWindow(), "Insert Component",
                "'%s' has not been saved yet. Save it first, then insert it." % src_doc.Label)
            g = Gui.getDocument(src_doc.Name)
            if g is None or not g.saveAs() or not src_doc.FileName:
                return False
        if not self.doc.FileName:
            folder = os.path.dirname(src_doc.FileName)
            path, _f = QtWidgets.QFileDialog.getSaveFileName(
                Gui.getMainWindow(), "Save the assembly (needed once, so it can reference part files)",
                os.path.join(folder, self.doc.Label + ".FCStd"), "FreeCAD assembly (*.FCStd)")
            if not path:
                return False
            if not path.lower().endswith(".fcstd"):
                path += ".FCStd"
            self.doc.saveAs(path)
            self.doc.Label = os.path.splitext(os.path.basename(path))[0]
        return True

    def _insert_sources(self, sources):
        done = []
        for src in sources:
            try:
                src_doc = self._resolve(src)
            except Exception as e:
                _tell("Could not open %s:\n%s" % (src[1], e))
                continue
            if src_doc is None:
                continue
            if src_doc is self.doc:
                continue
            targets = insertable(src_doc)
            if not targets:
                _tell("%s has no solid to insert." % src_doc.Label)
                continue
            if not self._ensure_saved(src_doc):
                break
            App.setActiveDocument(self.doc.Name)
            Gui.setActiveDocument(self.doc.Name)
            for _i in range(self.copies.value()):
                for t in targets:
                    done.append(self._add(t, src_doc.Label if len(targets) == 1 else t.Label))
        done = [d for d in done if d is not None]
        if done:
            Gui.Selection.clearSelection()
            for c in done:
                Gui.Selection.addSelection(self.doc.Name, self.asm.Name, c.Name + ".")
            Gui.SendMsgToActiveView("ViewFit")
            _status("Inserted %s" % ", ".join(c.Label for c in done))
        self._update_summary()
        self.fill()

    def _add(self, target, label):
        activate(self.asm)
        existing = components(self.asm)
        kind = "Assembly::AssemblyLink" if target.isDerivedFrom("Assembly::AssemblyObject") else "App::Link"
        self.doc.openTransaction("Insert Component")
        try:
            link = self.asm.newObject(kind, target.Label)
            link.LinkedObject = target
            link.Label = label
            link.recompute()
            if kind == "Assembly::AssemblyLink":
                link.Rigid = True
            if existing:
                self._place_beside(link, existing)
            self.doc.commitTransaction()
        except Exception as e:
            self.doc.abortTransaction()
            _tell("Could not insert %s:\n%s" % (target.Label, e))
            return None
        if not existing and not is_grounded(self.asm):
            _u, ccj = _modules()
            self.doc.openTransaction("Fix first component")
            ccj.createGroundedJoint(link)
            self.doc.commitTransaction()
        self.doc.recompute()
        self.inserted.append(link)
        return link

    @staticmethod
    def _place_beside(link, existing):
        """Set the new component down to the right of what is there, so nothing overlaps."""
        have = _bound_box(existing)
        new = _bound_box([link])
        if have is None or new is None:
            return
        gap = max(10.0, 0.25 * max(new.XLength, have.XLength))
        move = App.Vector(have.XMax + gap - new.XMin, have.Center.y - new.Center.y, have.ZMin - new.ZMin)
        link.Placement = App.Placement(link.Placement.Base + move, link.Placement.Rotation)

    def _undo_last(self):
        if not self.inserted:
            return
        c = self.inserted.pop()
        if c.Document is None:
            self._update_summary()
            return
        self.doc.openTransaction("Remove Component")
        for j in list(c.InList):
            if hasattr(j, "ObjectToGround") or hasattr(j, "Reference1"):
                self.doc.removeObject(j.Name)
        self.doc.removeObject(c.Name)
        self.doc.commitTransaction()
        self.doc.recompute()
        self._update_summary()

    def _update_summary(self):
        comps = components(self.asm)
        grounded = set()
        for j in self.doc.Objects:
            if hasattr(j, "ObjectToGround") and j.ObjectToGround is not None:
                grounded.add(j.ObjectToGround.Name)
        if not comps:
            self.summary.setText("Nothing inserted yet.")
        else:
            count, lines = {}, []
            for c in comps:                    # SolidWorks numbers instances: Part<1>, Part<2>
                linked = c.getLinkedObject(True) if hasattr(c, "getLinkedObject") else None
                base = linked.Document.Label if linked is not None and len(insertable(linked.Document)) == 1 \
                    else c.Label
                count[base] = count.get(base, 0) + 1
                lines.append("%s %s&lt;%d&gt;" % ("(f)" if c.Name in grounded else "(-)", base, count[base]))
            self.summary.setText("<br>".join(lines) +
                                 "<br><span style='color:#666'>(f) = fixed. Drag the others to move them.</span>")
        self.undo_btn.setEnabled(bool(self.inserted))
        self.mate_btn.setEnabled(len(comps) >= 2)

    def _to_mates(self):
        self._finish()
        Gui.Control.closeDialog()
        QtCore.QTimer.singleShot(0, lambda: start_mate(None))

    # ---------------------------------------------------------------- task panel API
    def getStandardButtons(self):
        return QtWidgets.QDialogButtonBox.Ok

    def _finish(self):
        Gui.Selection.clearSelection()

    def accept(self):
        self._finish()
        Gui.Control.closeDialog()
        return True

    def reject(self):
        return self.accept()


def show_insert(asm=None):
    asm = asm or find_assembly()
    if asm is None:
        new_assembly()
        return
    if not _close_open_dialog():
        return
    if not activate(asm):
        _tell("Could not activate %s." % asm.Label)
        return
    # SolidWorks fixes the first component without asking.
    p = App.ParamGet(ASM_PREFS)
    if p.GetInt("GroundFirstPart", 0) == 0:
        p.SetInt("GroundFirstPart", 1)
    Gui.Control.showDialog(InsertPanel(asm))


def insert_components():
    show_insert()


# ======================================================================
# Mate
# ======================================================================

# button key -> (text, FreeCAD joint type, icon, tooltip)
# (key, SolidWorks name, FreeCAD joint type, icon, tip)
STANDARD = [
    ("coincident", "Coincident", "Distance", "Mate_Coincident", "Faces/edges/points touch."),
    ("parallel", "Parallel", "Parallel", "Mate_Parallel", "Faces or edges stay parallel."),
    ("perpendicular", "Perpendicular", "Perpendicular", "Mate_Perpendicular", "Faces or edges at 90 degrees."),
    ("tangent", "Tangent", "Distance", "Mate_Tangent",
     "A round face touches a flat or another round face (cylinder, sphere, cone)."),
    ("concentric", "Concentric", "Cylindrical", "Mate_Concentric",
     "Round faces/edges share an axis (can still spin and slide)."),
    ("lock", "Lock", "Fixed", "Mate_Lock", "The two components can't move relative to each other."),
    ("distance", "Distance", "Distance", "Mate_Distance", "A set distance apart."),
    ("angle", "Angle", "Angle", "Mate_Angle", "A set angle between faces or edges."),
]
ADVANCED = [
    ("hinge", "Hinge", "Revolute", "Mate_Hinge", "Concentric + coincident: only spins."),
    ("slider", "Slider", "Slider", "Mate_Slider", "Only slides along one direction."),
    ("ball", "Ball", "Ball", "Mate_Ball", "Points touch, free to rotate (ball joint)."),
    ("gear", "Gear", "Gears", "Mate_Gear", "Gear mate."),
    ("rack", "Rack Pinion", "RackPinion", "Mate_RackPinion", "Rack and pinion mate."),
    ("screw", "Screw", "Screw", "Mate_Screw", "Screw mate."),
    ("belt", "Belt", "Belt", "Mate_Belt", "Belt / pulley mate."),
]
TOUCHING = ("coincident", "tangent")       # Distance joints held at 0
_BY_NAME = {t: k for k, t, *_r in STANDARD + ADVANCED}
_KINDS = {k: (t, jt) for k, t, jt, _i, _tip in STANDARD + ADVANCED}
_BY_JOINT = {"Fixed": "lock", "Revolute": "hinge", "Cylindrical": "concentric", "Slider": "slider", "Ball": "ball",
             "Distance": "coincident", "Parallel": "parallel", "Perpendicular": "perpendicular", "Angle": "angle",
             "RackPinion": "rack", "Screw": "screw", "Gears": "gear", "Belt": "belt"}


def _element(ref):
    """The picked face/edge/vertex of a joint reference [component, [sub, vertex]]."""
    try:
        import Part
        return Part.getShape(ref[0], ref[1][0], needSubElement=True, transform=True)
    except Exception:
        return None


def _round(el):
    import Part
    try:
        if el.ShapeType == "Face":
            return isinstance(el.Surface, (Part.Cylinder, Part.Cone))
        if el.ShapeType == "Edge":
            return isinstance(el.Curve, (Part.Circle, Part.ArcOfCircle))
    except Exception:
        pass
    return False


def _sphere(el):
    import Part
    try:
        return el.ShapeType == "Face" and isinstance(el.Surface, Part.Sphere)
    except Exception:
        return False


def _flat(el):
    import Part
    try:
        return el.ShapeType == "Face" and isinstance(el.Surface, Part.Plane)
    except Exception:
        return False


def guess_mate(ref1, ref2):
    """SolidWorks' default for the two picks: concentric for two round things, tangent for a round
    face on a flat face (or a ball), coincident otherwise."""
    a, b = _element(ref1), _element(ref2)
    if a is None or b is None:
        return "coincident"
    if _round(a) and _round(b):
        return "concentric"
    if (_round(a) or _sphere(a)) and (_flat(b) or _sphere(b)) and a.ShapeType == "Face" or \
            (_round(b) or _sphere(b)) and (_flat(a) or _sphere(a)) and b.ShapeType == "Face":
        return "tangent"
    return "coincident"


def _shape_info(el):
    """(kind, point, direction, radius) of a picked face: plane -> outward normal, cylinder/cone -> axis, sphere."""
    import Part
    if el is None or el.ShapeType != "Face":
        return None
    srf = el.Surface
    if isinstance(srf, Part.Plane):
        u, v = srf.parameter(el.CenterOfMass)
        return ("plane", el.CenterOfMass, el.normalAt(u, v), 0.0)
    if isinstance(srf, Part.Cylinder):
        ax = App.Vector(srf.Axis).normalize()            # point: the middle of the face, on the axis
        return ("cyl", srf.Center + ax * (el.CenterOfMass - srf.Center).dot(ax), ax, srf.Radius)
    if isinstance(srf, Part.Sphere):
        return ("sphere", srf.Center, None, srf.Radius)
    return None


def _turn(a, b):
    """Rotation taking direction a to b (any perpendicular axis when they're opposite)."""
    a, b = App.Vector(a).normalize(), App.Vector(b).normalize()
    if a.cross(b).Length < 1e-9 and a.dot(b) < 0:
        ax = a.cross(App.Vector(1, 0, 0))
        if ax.Length < 1e-6:
            ax = a.cross(App.Vector(0, 1, 0))
        return App.Rotation(ax, 180)
    return App.Rotation(a, b)


def _about(point, rot):
    """Placement rotating by rot about point."""
    return App.Placement(point - rot.multVec(point), rot)


def tangent_motion(fixed, moving):
    """Placement (global) that puts the moving round/flat face tangent to the fixed one, outside it.
    fixed/moving are _shape_info tuples. None when the pair can't be tangent."""
    if fixed is None or moving is None:
        return None
    fk, fp, fd, fr = fixed
    mk, mp, md, mr = moving
    if fk == "plane" and mk in ("cyl", "sphere"):
        t = App.Placement()
        if mk == "cyl":                                   # lay the axis parallel to the face
            proj = md - fd * md.dot(fd)
            if proj.Length < 1e-6:
                proj = fd.cross(App.Vector(1, 0, 0))
                if proj.Length < 1e-6:
                    proj = fd.cross(App.Vector(0, 1, 0))
            t = _about(mp, _turn(md, proj))
        c = t.multVec(mp)
        # sit over the middle of the picked face, on the outside, touching
        return App.Placement(fp + fd * mr - c, App.Rotation()).multiply(t)
    if mk == "plane" and fk in ("cyl", "sphere"):         # move the flat part instead: the inverse motion
        t = tangent_motion(moving, fixed)
        return t.inverse() if t is not None else None
    if fk in ("cyl", "sphere") and mk in ("cyl", "sphere"):
        t = App.Placement()
        if fk == "cyl" and mk == "cyl":                    # axes parallel
            t = _about(mp, _turn(md, fd if md.dot(fd) >= 0 else -fd))
        c = t.multVec(mp)
        v = c - fp
        if fk == "cyl":
            v = v - fd * v.dot(fd)                        # from the fixed axis, square to it
        if v.Length < 1e-6:
            v = (fd.cross(App.Vector(1, 0, 0)) if fd is not None else App.Vector(1, 0, 0))
            if v.Length < 1e-6:
                v = fd.cross(App.Vector(0, 1, 0))
        n = App.Vector(v).normalize()
        return App.Placement(n * (fr + mr - v.Length), App.Rotation()).multiply(t)
    return None


def mate_kind(joint):
    """SolidWorks mate key for a FreeCAD joint (the type saved by the Mate panel, else a guess from the joint)."""
    saved = getattr(joint, "SolidStyleMate", "")
    if saved in _BY_NAME:
        return _BY_NAME[saved]
    key = _BY_JOINT.get(str(getattr(joint, "JointType", "")), "coincident")
    if key == "coincident" and abs(float(getattr(joint, "Distance", 0) or 0)) > 1e-9:
        key = "distance"
    return key


_mate_cls = None


def _mate_class():
    """Built on first use: FreeCAD's joint panel (selection, preview, solving) under SolidWorks' mate buttons."""
    global _mate_cls
    if _mate_cls is not None:
        return _mate_cls
    import JointObject

    class MatePanel(JointObject.TaskAssemblyCreateJoint):
        def __init__(self, kind=None, joint=None):
            if joint is not None:
                kind = mate_kind(joint)
            self.kind = kind or "coincident"
            self.user_kind = kind is not None      # a mate button was clicked (or editing): don't guess
            self.ready = False
            super().__init__(JointObject.JointTypes.index(_KINDS[self.kind][1]), joint, True)
            if not hasattr(self, "jForm"):
                return
            self._build()
            self.ready = True
            if len(self.refs) == 2 and not self.user_kind:     # two picks made before clicking Mate
                self.set_kind(guess_mate(self.refs[0], self.refs[1]))
            self.adaptUi()
            self._show_kind()

        # ------------------------------------------------------------ UI
        def _build(self):
            self.form.setWindowTitle("Mate")
            self.form.setWindowIcon(_icon("Assembly_CreateJointDistance"))
            self.form.setStyleSheet(PM_STYLE)
            jf = self.jForm
            jf.jointType.hide()
            for lbl in jf.findChildren(QtWidgets.QLabel):
                if lbl.buddy() is jf.jointType or lbl.text().strip().rstrip(":").lower() in ("joint type", "type"):
                    lbl.hide()
            top = QtWidgets.QWidget()
            v = QtWidgets.QVBoxLayout(top)
            v.setContentsMargins(0, 0, 0, 0)
            self.hint = QtWidgets.QLabel()
            self.hint.setWordWrap(True)
            self.hint.setStyleSheet(HINT_STYLE)
            self.hint.setMinimumHeight(self.hint.fontMetrics().lineSpacing() * 3 + 16)
            v.addWidget(self.hint)

            g = QtWidgets.QGroupBox("Standard Mates")
            grid = QtWidgets.QGridLayout(g)
            grid.setSpacing(3)
            self.group = QtWidgets.QButtonGroup(top)
            self.group.setExclusive(True)
            self.buttons = {}
            for i, (key, text, _jt, ic, tip) in enumerate(STANDARD):
                b = self._button(key, text, ic, tip)
                grid.addWidget(b, i // 2, i % 2)
            v.addWidget(g)

            g2 = QtWidgets.QGroupBox("Advanced / Mechanical Mates")
            g2.setCheckable(True)
            g2.setChecked(False)
            grid2 = QtWidgets.QGridLayout(g2)
            grid2.setSpacing(3)
            holder = QtWidgets.QWidget()
            hg = QtWidgets.QGridLayout(holder)
            hg.setContentsMargins(0, 0, 0, 0)
            hg.setSpacing(3)
            for i, (key, text, _jt, ic, tip) in enumerate(ADVANCED):
                hg.addWidget(self._button(key, text, ic, tip), i // 2, i % 2)
            grid2.addWidget(holder)
            holder.setVisible(False)
            g2.toggled.connect(holder.setVisible)
            self.adv_box, self.adv_holder = g2, holder
            v.addWidget(g2)

            row = QtWidgets.QHBoxLayout()
            flip = QtWidgets.QPushButton("Flip Alignment")
            flip.setToolTip("Turn the moving component around (aligned / anti-aligned)")
            flip.clicked.connect(self._flip)
            row.addWidget(flip)
            row.addStretch(1)
            self.keep = QtWidgets.QCheckBox("Keep open")
            self.keep.setToolTip("After OK, start the next mate (SolidWorks' pushpin)")
            self.keep.setChecked(App.ParamGet(PARAMS).GetBool("MateKeepOpen", True))
            row.addWidget(self.keep)
            v.addLayout(row)

            sel_title = QtWidgets.QLabel("<b>Mate Selections</b>")
            v.addWidget(sel_title)
            self.form.layout().insertWidget(0, top)
            jf.PushButtonReverse.hide()          # same as Flip Alignment above

        def _button(self, key, text, ic, tip):
            b = QtWidgets.QToolButton()
            b.setText(text)
            b.setIcon(_icon(ic))
            b.setIconSize(QtCore.QSize(22, 22))
            b.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, k=key: self.set_kind(k, user=True))
            self.group.addButton(b)
            self.buttons[key] = b
            return b

        def _show_kind(self):
            b = self.buttons.get(self.kind)
            if b is not None:
                b.setChecked(True)
                if self.kind in [k for k, *_r in ADVANCED]:
                    self.adv_box.setChecked(True)
            n = len(self.refs) if hasattr(self, "refs") else 0
            name = _KINDS[self.kind][0]
            if n == 0:
                self.hint.setText("Click a face, edge or point on the first component.")
            elif n == 1:
                self.hint.setText("Now click a face, edge or point on a second component.")
            else:
                self.hint.setText("<b>%s</b> mate. Pick another mate type if needed, Flip Alignment to turn it "
                                  "around, then OK." % name)

        # ------------------------------------------------------------ mate type
        def set_kind(self, key, user=False):
            if user:
                self.user_kind = True
            self.kind = key
            jt = _KINDS[key][1]
            idx = JointObject.JointTypes.index(jt)
            if self.jForm.jointType.currentIndex() != idx:
                self.jForm.jointType.setCurrentIndex(idx)   # -> onJointTypeChanged
                if len(self.refs) == 2:
                    # re-run FreeCAD's placement + solve for the new type
                    self.joint.Proxy.setJointConnectors(self.joint, self.refs[:1])
                    self.joint.Proxy.setJointConnectors(self.joint, self.refs)
            else:
                self.adaptUi()
            if key == "coincident" and abs(float(self.joint.Distance)) > 1e-9:
                self.joint.Distance = 0.0
            if key == "tangent":
                self._place_tangent()
            self._show_kind()

        def adaptUi(self):
            super().adaptUi()
            if getattr(self, "ready", False) and self.kind in TOUCHING:
                self.jForm.distanceLabel.hide()
                self.jForm.distanceSpinbox.hide()

        def updateJoint(self):
            if len(self.refs) == 2 and not self.user_kind and self.ready:
                key = guess_mate(self.refs[0], self.refs[1])
                if key != self.kind:
                    self.kind = key
                    self.jForm.jointType.blockSignals(True)
                    self.jForm.jointType.setCurrentIndex(JointTypes_index(key))
                    self.jForm.jointType.blockSignals(False)
                    self.jType = _KINDS[key][1]
                    self.joint.Proxy.setJointType(self.joint, self.jType)
                    self.adaptUi()
            super().updateJoint()
            if self.ready:
                if self.kind == "tangent":
                    self._place_tangent()
                self._show_kind()

        def _place_tangent(self):
            """FreeCAD's pre-solve stands a cylinder on end in the middle of a face, and the solver can't get
            it from there to lying against the face: put it there first, on the outside, then solve."""
            if len(self.refs) != 2 or not getattr(self, "creating", True) or self.activeType != "Assembly":
                return
            try:
                import UtilsAssembly
                j, asm = self.joint, self.assembly
                parts = [UtilsAssembly.getMovingPart(r) for r in self.refs]
                j.Suppressed = True
                connected = [asm.isPartConnected(p) for p in parts]
                j.Suppressed = False
                mv = 1 if not connected[1] else 0 if not connected[0] else None
                if mv is None:
                    return
                info = [_shape_info(_element(r)) for r in self.refs]
                motion = tangent_motion(info[1 - mv], info[mv])
                if motion is None:
                    return
                part = parts[mv]
                part.Placement = motion.multiply(part.Placement)
                j.Distance = 0.0
                asm.solve()
                # the solver keeps the round face on the side of the flat face's connector: check it's outside
                kinds = [i[0] for i in info]
                if "plane" in kinds and ("cyl" in kinds or "sphere" in kinds):
                    now = [_shape_info(_element(r)) for r in self.refs]
                    pl = now[kinds.index("plane")]
                    rd = now[1 - kinds.index("plane")]
                    if (rd[1] - pl[1]).dot(pl[2]) < 0:          # ended up inside: other side of the connector
                        j.Distance = -2 * rd[3]
                        asm.solve()
                Gui.updateGui()
            except Exception as e:
                App.Console.PrintLog("SolidStyle: tangent placement: %s\n" % e)

        def _flip(self):
            if len(self.refs) == 2:
                self.onReverseClicked()

        # ------------------------------------------------------------ OK / Cancel
        def accept(self):
            App.ParamGet(PARAMS).SetBool("MateKeepOpen", self.keep.isChecked())
            keep = self.keep.isChecked()
            if len(self.refs) == 0:
                self.reject()
                return True
            if len(self.refs) != 2:
                _status("Pick a face/edge on a second component first")
                return False
            j = self.joint
            if "SolidStyleMate" not in j.PropertiesList:
                j.addProperty("App::PropertyString", "SolidStyleMate", "Joint", "SolidWorks mate type")
                j.setEditorMode("SolidStyleMate", 1)
            j.SolidStyleMate = _KINDS[self.kind][0]
            editing = not getattr(self, "creating", True)
            ok = super().accept()
            if ok and keep and not editing:
                QtCore.QTimer.singleShot(0, lambda: start_mate(None))
            return ok

    def JointTypes_index(key):
        return JointObject.JointTypes.index(_KINDS[key][1])

    _mate_cls = MatePanel
    return MatePanel


def start_mate(kind=None):
    """Open the Mate PropertyManager. kind=None: pick the type from the selections."""
    asm = _ready(2)
    if asm is None:
        return
    ensure_fixed(asm)
    if not _close_open_dialog():
        return
    try:
        panel = _mate_class()(kind)
    except Exception as e:
        _mate_failed(e)
        _u, ccj = _modules()
        ccj.activateJoint(5)
        return
    _show_mate(panel, asm.Document.Name)


def _show_mate(panel, doc_name):
    dlg = Gui.Control.showDialog(panel)
    if dlg is not None:
        dlg.setAutoCloseOnTransactionChange(True)
        dlg.setAutoCloseOnDeletedDocument(True)
        dlg.setDocumentName(doc_name)


def _mate_failed(e):
    """Never fall back to FreeCAD's joint panel silently: say why."""
    import traceback
    tb = traceback.format_exc()
    App.Console.PrintError("SolidStyle: Mate panel failed, using FreeCAD's joint panel:\n%s" % tb)
    try:
        from solidstyle import setup
        with open(setup._status_path(), "a", encoding="utf-8") as f:
            f.write("Mate panel failed (FreeCAD %s)\n%s\n" % (".".join(App.Version()[:3]), tb))
    except Exception:
        pass
    QtWidgets.QMessageBox.warning(Gui.getMainWindow(), "Mate",
                                  "The SolidWorks Mate panel couldn't open on this FreeCAD (%s: %s), so FreeCAD's "
                                  "joint panel is used instead.\n\nTools > Copy SolidWorks Style Diagnostics copies "
                                  "the details." % (type(e).__name__, e))


def edit_mate(joint):
    """Double-clicking a mate opens it in the Mate PropertyManager (instead of FreeCAD's joint panel)."""
    import JointObject
    App.closeActiveTransaction(True)
    task = Gui.Control.activeTaskDialog()
    if task:
        task.reject()
    asm = joint.Proxy.getAssembly(joint)
    if asm is None:
        return False
    if _modules()[0].activeAssembly() != asm:
        Gui.getDocument(asm.Document).setEdit(asm)
    _show_mate(_mate_class()(None, joint), asm.Document.Name)
    return True


def _hook_joint_edit():
    import JointObject
    vp = JointObject.ViewProviderJoint
    if getattr(vp.doubleClicked, "_solidstyle", False):
        return
    orig = vp.doubleClicked

    def doubleClicked(self, vobj):
        if Gui.activeWorkbench().name() == "SolidStyleWorkbench":
            try:
                return edit_mate(vobj.Object)
            except Exception as e:
                _mate_failed(e)
        return orig(self, vobj)
    doubleClicked._solidstyle = True
    vp.doubleClicked = doubleClicked


def run_after_activate(cmd, need_parts=0, fix=False):
    def go():
        asm = _ready(need_parts)
        if asm is None:
            return
        if fix:
            ensure_fixed(asm)
        Gui.runCommand(cmd, 0)
    return go


def fix_float():
    asm = _ready(1)
    if asm is None:
        return
    if not Gui.Selection.getSelectionEx("*", 0):
        _tell("Select the component(s) to fix or float first.")
        return
    Gui.runCommand("Assembly_ToggleGrounded", 0)


class _AsmCmd:
    def __init__(self, menu, tip, icon, fn, needs_asm=True):
        self.menu, self.tip, self.icon, self.fn, self.needs_asm = menu, tip, icon, fn, needs_asm

    def GetResources(self):
        p = os.path.join(SW_ICONS, self.icon + ".svg")
        return {"Pixmap": p if os.path.exists(p) else self.icon, "MenuText": self.menu, "ToolTip": self.tip}

    def IsActive(self):
        if not self.needs_asm:
            return True
        return find_assembly() is not None

    def Activated(self):
        self.fn()


def _mate_kind(fc):
    return _BY_JOINT.get(fc.split("CreateJoint", 1)[1], "coincident")


def register():
    try:
        _modules()
    except Exception as e:
        App.Console.PrintLog("SolidStyle: Assembly module unavailable: %s\n" % e)
        return
    _hook_joint_edit()
    Gui.addCommand("SS_Mate", _AsmCmd(
        "Mate", "Add mates: click a face/edge on two components; the mate type is picked for you.",
        "Assembly_CreateJointDistance", lambda: start_mate(None)))
    Gui.addCommand("SS_InsertComponents", _AsmCmd(
        "Insert Components", "Pick part files from a list and insert them. The first one is fixed.",
        "Assembly_InsertLink", insert_components, needs_asm=False))
    Gui.addCommand("SS_FixFloat", _AsmCmd(
        "Fix / Float", "Fix (ground) or float the selected components.", "Assembly_ToggleGrounded", fix_float))
    Gui.addCommand("SS_RebuildAssembly", _AsmCmd(
        "Rebuild Assembly", "Solve all mates.", "Assembly_SolveAssembly",
        run_after_activate("Assembly_SolveAssembly", 1, True)))
    Gui.addCommand("SS_ExplodedView", _AsmCmd(
        "Exploded View", "Create an exploded view.", "Assembly_CreateView",
        run_after_activate("Assembly_CreateView", 1, True)))
    for key, text, _jt, ic, tip in STANDARD + ADVANCED:      # one command per SolidWorks mate
        Gui.addCommand("SS_Mate_" + text.replace(" ", ""), _AsmCmd(text, text + " mate: " + tip, ic,
                                                                    lambda k=key: start_mate(k)))
    for fc, (idx, menu, tip) in MATES.items():
        Gui.addCommand("SS_" + fc.split("_", 1)[1], _AsmCmd(menu, tip, fc, lambda k=_mate_kind(fc): start_mate(k)))
