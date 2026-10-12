"""SolidWorks-style feature workflows ("PropertyManagers").

The SolidWorks order of operations is reproduced on top of PartDesign:
  * click Extruded Boss/Base (or Revolve, Hole Wizard) first, then pick a plane or
    face -> a sketch opens -> 'Exit Sketch' continues straight into the feature;
  * an already selected / just-finished sketch is used directly;
  * Fillet, Chamfer and Shell open their panel first and you pick edges/faces after;
  * end conditions use SolidWorks names (Blind, Through All, Up To Next, Up To Surface,
    Offset From Surface, Up To Body, Mid Plane) and Direction 2;
  * the depth can be dragged with an arrow in the 3D view;
  * double-clicking one of these features re-opens the same panel.
"""
import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

from solidstyle import commands

ICONS = os.path.join(os.path.dirname(__file__), "icons")
SW_ICONS = os.path.join(ICONS, "sw")


def sw_icon(name):
    p = os.path.join(SW_ICONS, name + ".svg")
    return QtGui.QIcon(p) if os.path.exists(p) else QtGui.QIcon()


def status(msg, ms=10000):
    try:
        Gui.getMainWindow().statusBar().showMessage(msg, ms)
    except Exception:
        pass
    App.Console.PrintMessage("SolidStyle: %s\n" % msg)


def warn(title, msg):
    QtWidgets.QMessageBox.warning(Gui.getMainWindow(), title, msg)


# ======================================================================
# Bodies, selections and the "sketch first" flow
# ======================================================================

def active_body(create=True):
    if App.ActiveDocument is None:
        if not create:
            return None
        Gui.runCommand("SS_NewPart", 0)
    doc = App.ActiveDocument
    view = Gui.ActiveDocument.ActiveView
    body = None
    try:
        body = view.getActiveObject("pdbody")
    except Exception:
        pass
    if body is None:
        bodies = [o for o in doc.Objects if o.isDerivedFrom("PartDesign::Body")]
        visible = [b for b in bodies if b.Visibility]
        if visible or bodies:
            body = (visible or bodies)[0]
        elif create:
            body = doc.addObject("PartDesign::Body", "Body")
            from solidstyle import setup
            setup.relabel_origin(body)
            doc.recompute()
        if body is not None:
            try:
                view.setActiveObject("pdbody", body)
            except Exception:
                pass
    return body


def body_of(obj):
    for o in obj.InList:
        if o.isDerivedFrom("PartDesign::Body"):
            return o
    return active_body()


def _is_planar(face):
    import Part
    try:
        return isinstance(face.Surface, Part.Plane) or face.findPlane() is not None
    except Exception:
        return False


def classify(sel_ex=None):
    """('sketch', sketch) | ('plane', obj, '') | ('face', obj, 'FaceN') | ('edge', obj, 'EdgeN') | None."""
    sels = sel_ex if sel_ex is not None else Gui.Selection.getSelectionEx()
    for s in sels:
        obj = s.Object
        if obj.isDerivedFrom("Sketcher::SketchObject"):
            return ("sketch", obj)
        if obj.isDerivedFrom("App::Plane") or obj.isDerivedFrom("PartDesign::Plane"):
            return ("plane", obj, "")
        for sub in s.SubElementNames:
            if sub.startswith("Face"):
                try:
                    face = obj.Shape.getElement(sub)
                except Exception:
                    continue
                if _is_planar(face):
                    return ("face", obj, sub)
    return None


def unconsumed_sketch(body):
    """The newest sketch in the body that no feature uses yet (SolidWorks' 'current sketch')."""
    if body is None:
        return None
    for o in reversed(body.Group):
        if o.isDerivedFrom("Sketcher::SketchObject") and o.Shape.Edges:
            used = any(getattr(f, "Profile", None) and f.Profile[0] == o for f in o.InList)
            return None if used else o
    return None


_pending = {}  # (doc name, sketch name) -> callback(sketch)
_watch = None


def _watch_pending():
    for key in list(_pending):
        doc = App.listDocuments().get(key[0])
        sk = doc.getObject(key[1]) if doc else None
        if sk is None:
            _pending.pop(key)
            continue
        editing = commands.editing_sketch()
        if editing is not None and editing.Name == key[1] and editing.Document.Name == key[0]:
            continue
        cb = _pending.pop(key)
        if sk.Shape.Edges or any(g.TypeId == "Part::GeomPoint" for g in sk.Geometry):
            QtCore.QTimer.singleShot(0, lambda cb=cb, sk=sk: cb(sk))
        else:
            status("Sketch is empty - feature cancelled")


def _ensure_watch():
    global _watch
    if _watch is None:
        _watch = QtCore.QTimer()
        _watch.timeout.connect(_watch_pending)
        _watch.start(200)


def sketch_on(target, then, tool=None, hint=""):
    """Create a sketch on a plane/face, open it, and call then(sketch) on Exit Sketch."""
    kind, obj, sub = target
    body = body_of(obj) if not obj.isDerivedFrom("App::Plane") else active_body()
    doc = body.Document
    doc.openTransaction("Sketch")
    sk = body.newObject("Sketcher::SketchObject", "Sketch")
    prop = "AttachmentSupport" if hasattr(sk, "AttachmentSupport") else "Support"
    setattr(sk, prop, [(obj, sub)])
    sk.MapMode = "FlatFace"
    doc.commitTransaction()
    doc.recompute()
    Gui.Selection.clearSelection()
    Gui.ActiveDocument.setEdit(sk.Name)
    if then is not None:
        _ensure_watch()
        _pending[(doc.Name, sk.Name)] = then
    if tool:
        QtCore.QTimer.singleShot(300, lambda: Gui.runCommand(tool, 0))
    if hint:
        status(hint, 15000)
    return sk


def sketch_first(title, then, hint):
    """SolidWorks order: use the open/selected/current sketch, else ask for a plane."""
    sk = commands.editing_sketch()
    if sk is not None:
        _pending.pop((sk.Document.Name, sk.Name), None)
        Gui.ActiveDocument.resetEdit()
        sk.Document.recompute()
        then(sk)
        return
    k = classify()
    if k and k[0] == "sketch":
        then(k[1])
        return
    if k:
        sketch_on(k, then, hint=hint)
        return
    if Gui.Control.activeDialog():
        status("Finish the open command first")
        return
    body = active_body()
    cur = unconsumed_sketch(body)
    if cur is not None and cur.Visibility:
        then(cur)
        return
    Gui.Control.showDialog(PickPanel(
        title, "Select:\n\n  •  a plane on which to sketch the feature cross-section, or\n"
               "  •  a planar face, or\n  •  an existing sketch.",
        ("sketch", "plane", "face"),
        lambda k: then(k[1]) if k[0] == "sketch" else sketch_on(k, then, hint=hint)))


class PickPanel:
    """'Select a plane...' message box, like SolidWorks shows before a sketch-based feature."""

    def __init__(self, title, prompt, kinds, done):
        self.kinds, self.done = kinds, done
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle(title)
        lay = QtWidgets.QVBoxLayout(self.form)
        msg = QtWidgets.QLabel(prompt)
        msg.setWordWrap(True)
        msg.setStyleSheet("QLabel{background:#fff8d6;color:#222;border:1px solid #e0c34a;border-radius:4px;padding:8px}")
        lay.addWidget(QtWidgets.QLabel("<b>Message</b>"))
        lay.addWidget(msg)
        lay.addStretch(1)
        self.body = active_body()
        self.origin_was = None
        if self.body is not None and "plane" in kinds:
            origin = self.body.Origin
            self.origin_was = origin.Visibility
            origin.Visibility = True
            for f in origin.OriginFeatures:
                f.Visibility = f.isDerivedFrom("App::Plane")
        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(self)

    def getStandardButtons(self):
        return QtWidgets.QDialogButtonBox.Cancel

    def addSelection(self, doc, obj, sub, pnt):
        QtCore.QTimer.singleShot(0, self._check)

    def _check(self):
        k = classify()
        if k and k[0] in self.kinds:
            self._cleanup()
            Gui.Control.closeDialog()
            QtCore.QTimer.singleShot(0, lambda: self.done(k))

    def _cleanup(self):
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass
        if self.origin_was is not None and self.body is not None:
            self.body.Origin.Visibility = self.origin_was
            self.origin_was = None

    def reject(self):
        self._cleanup()
        Gui.Control.closeDialog()
        return True


# ======================================================================
# Shared PropertyManager pieces
# ======================================================================

PM_STYLE = """
QGroupBox { font-weight: bold; border: 1px solid #9aa4b1; border-radius: 4px; margin-top: 16px; padding-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 8px; top: 2px; padding: 0 4px; }
"""


def _spin(value, suffix=" mm", lo=0.0, hi=100000.0, dec=2, step=1.0):
    s = QtWidgets.QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSingleStep(step)
    s.setSuffix(suffix)
    s.setValue(value)
    s.setKeyboardTracking(False)
    return s


def _q(v):
    """Quantity or float -> float."""
    return float(getattr(v, "Value", v))


class _Panel:
    """Base: transaction handling, live preview with debounce, OK/Cancel."""
    title = "Feature"
    icon = ""

    def __init__(self, feat, editing):
        self.feat = feat
        self.doc = feat.Document
        self.editing = editing
        self.base = getattr(feat, "BaseFeature", None)
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle(self.title)
        self.form.setWindowIcon(sw_icon(self.icon))
        self.form.setStyleSheet(PM_STYLE)
        if editing:
            self.form.setWindowTitle(feat.Label)
        self.lay = QtWidgets.QVBoxLayout(self.form)
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._preview)
        self.closed = False

    def changed(self, *_):
        if not self.closed:
            self.timer.start(150)

    def _preview(self):
        if self.closed:
            return
        try:
            self.apply()
            self.doc.recompute()
            self.after_preview()
        except Exception as e:
            App.Console.PrintWarning("SolidStyle preview: %s\n" % e)

    def after_preview(self):
        pass

    def apply(self):
        raise NotImplementedError

    def getStandardButtons(self):
        return QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel

    def validate(self):
        return None

    def accept(self):
        err = self.validate()
        if err:
            warn(self.title, err)
            return False
        self.apply()
        self.doc.recompute()
        if not self.feat.isValid():
            msg = self.feat.getStatusString() if hasattr(self.feat, "getStatusString") else "Rebuild error"
            warn(self.title, "This feature can't be created:\n\n%s" % msg)
            return False
        self.finish(True)
        return True

    def reject(self):
        self.finish(False)
        return True

    def finish(self, ok):
        self.closed = True
        self.timer.stop()
        self.cleanup()
        if ok:
            self.on_ok()
            self.doc.commitTransaction()
        else:
            self.doc.abortTransaction()
            self.on_cancel()
        self.doc.recompute()
        Gui.Control.closeDialog()

    def cleanup(self):
        pass

    def on_ok(self):
        pass

    def on_cancel(self):
        if self.base is not None and not self.editing:
            try:
                self.base.Visibility = True
            except Exception:
                pass


class FacePicker(QtWidgets.QWidget):
    """'Face/Plane' field with a pick button (SolidWorks' pink selection box)."""

    def __init__(self, panel, label, types=("Face",), multi=False):
        super().__init__()
        self.panel, self.types, self.multi = panel, types, multi
        self.items = []  # [(obj, sub)]
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.box = QtWidgets.QLineEdit()
        self.box.setReadOnly(True)
        self.box.setPlaceholderText(label)
        self.box.setStyleSheet("QLineEdit{background:#fde3ee;color:#222}")
        self.btn = QtWidgets.QToolButton()
        self.btn.setText("Select")
        self.btn.setCheckable(True)
        h.addWidget(self.box, 1)
        h.addWidget(self.btn)
        self.btn.toggled.connect(self._toggle)

    def _toggle(self, on):
        if on:
            Gui.Selection.clearSelection()
            Gui.Selection.addObserver(self)
            self.box.setStyleSheet("QLineEdit{background:#ffb3d1;color:#222}")
        else:
            try:
                Gui.Selection.removeObserver(self)
            except Exception:
                pass
            self.box.setStyleSheet("QLineEdit{background:#fde3ee;color:#222}")

    def addSelection(self, doc, obj_name, sub, pnt):
        obj = App.getDocument(doc).getObject(obj_name)
        if obj is None:
            return
        if obj == self.panel.feat:
            obj, sub = map_to_base(self.panel.feat, sub)
            if obj is None:
                status("Pick a face of the existing model, not of the feature being created")
                return
        ok = (sub == "" and (obj.isDerivedFrom("App::Plane") or obj.isDerivedFrom("PartDesign::Plane"))) or \
            any(sub.startswith(t) for t in self.types) or ("Body" in self.types and sub == "")
        if not ok:
            return
        if self.multi:
            self.items.append((obj, sub))
        else:
            self.items = [(obj, sub)]
            QtCore.QTimer.singleShot(0, lambda: self.btn.setChecked(False))
        self.box.setText(", ".join("%s%s" % (o.Label, "." + s if s else "") for o, s in self.items))
        self.panel.changed()

    def set(self, items):
        self.items = list(items)
        self.box.setText(", ".join("%s%s" % (o.Label, "." + s if s else "") for o, s in self.items))

    def close(self):
        self.btn.setChecked(False)


def map_to_base(feat, sub):
    """A face/edge of the preview feature -> the matching element of its base feature."""
    base = getattr(feat, "BaseFeature", None)
    if base is None or not sub:
        return None, None
    try:
        el = feat.Shape.getElement(sub)
    except Exception:
        return None, None
    kind = "Faces" if sub.startswith("Face") else "Edges"
    for i, cand in enumerate(getattr(base.Shape, kind), 1):
        if abs(cand.Length if kind == "Edges" else cand.Area) - (el.Length if kind == "Edges" else el.Area) > 1e-6:
            continue
        if cand.isPartner(el) or cand.CenterOfMass.distanceToPoint(el.CenterOfMass) < 1e-6:
            return base, "%s%d" % (sub.rstrip("0123456789"), i)
    return None, None


# ======================================================================
# Drag handle for depth (SolidWorks' arrow with depth call-out)
# ======================================================================

class DepthDragger:
    def __init__(self, on_drag):
        self.on_drag = on_drag
        self.root = None
        self.muted = False
        try:
            from pivy import coin
            self.coin = coin
            self.root = coin.SoSwitch()
            self.root.whichChild = -1
            sep = coin.SoSeparator()
            self.root.addChild(sep)
            if hasattr(coin, "SoDepthBuffer"):  # draw on top of the model, like SolidWorks' handles
                db = coin.SoDepthBuffer()
                db.test = False
                sep.addChild(db)
            self.xf = coin.SoTransform()
            sep.addChild(self.xf)
            mat = coin.SoMaterial()
            mat.diffuseColor = (0.16, 0.44, 0.86)
            sep.addChild(mat)
            self.dragger = coin.SoTranslate1Dragger()
            sep.addChild(self.dragger)
            self.dragger.addValueChangedCallback(self._moved, None)
            # depth call-out text
            self.label_sep = coin.SoSeparator()
            self.label_pos = coin.SoTranslation()
            col = coin.SoBaseColor()
            col.rgb = (0.05, 0.05, 0.05)
            font = coin.SoFont()
            font.size = 16
            self.text = coin.SoText2()
            for n in (self.label_pos, col, font, self.text):
                self.label_sep.addChild(n)
            sep.addChild(self.label_sep)
            Gui.ActiveDocument.ActiveView.getSceneGraph().addChild(self.root)
        except Exception as e:
            App.Console.PrintLog("SolidStyle: no drag handle (%s)\n" % e)
            self.root = None

    def hide(self):
        if self.root is not None:
            self.root.whichChild = -1

    def place(self, origin, direction, length, scale, label):
        if self.root is None:
            return
        self.root.whichChild = 0
        c = self.coin
        self.scale = max(scale, 1e-3)
        self.muted = True
        try:
            self.xf.translation.setValue(origin.x, origin.y, origin.z)
            self.xf.rotation.setValue(c.SbRotation(c.SbVec3f(1, 0, 0), c.SbVec3f(direction.x, direction.y, direction.z)))
            self.xf.scaleFactor.setValue(self.scale, self.scale, self.scale)
            self.dragger.translation.setValue(length / self.scale, 0, 0)
            self.label_pos.translation.setValue(length / self.scale + 1.5, 0.8, 0)
            self.text.string.setValue(label)
        finally:
            self.muted = False

    def _moved(self, _data, dragger):
        if self.muted:
            return
        x = dragger.translation.getValue()[0]
        self.on_drag(max(0.01, x * self.scale))

    def remove(self):
        if self.root is not None:
            try:
                Gui.ActiveDocument.ActiveView.getSceneGraph().removeChild(self.root)
            except Exception:
                pass
            self.root = None


# ======================================================================
# Extruded Boss/Base and Extruded Cut
# ======================================================================

END_BOSS = [("Blind", "blind"), ("Up To Next", "next"), ("Up To Last (Through All)", "through"),
            ("Up To Surface", "surface"), ("Offset From Surface", "offset"), ("Up To Body", "body"),
            ("Mid Plane", "mid")]
END_CUT = [("Blind", "blind"), ("Through All", "through"), ("Through All - Both", "through_both"),
           ("Up To Next", "next"), ("Up To Surface", "surface"), ("Offset From Surface", "offset"),
           ("Up To Body", "body"), ("Mid Plane", "mid")]


class ExtrudePanel(_Panel):
    def __init__(self, feat, editing=False):
        self.cut = feat.isDerivedFrom("PartDesign::Pocket")
        self.title = "Cut-Extrude" if self.cut else "Boss-Extrude"
        self.icon = "SS_ExtrudeCut" if self.cut else "SS_ExtrudeBoss"
        super().__init__(feat, editing)
        f = feat
        # ---------------- Direction 1
        g1 = QtWidgets.QGroupBox("Direction 1")
        v1 = QtWidgets.QGridLayout(g1)
        self.rev = QtWidgets.QToolButton()
        self.rev.setCheckable(True)
        self.rev.setIcon(QtGui.QIcon(os.path.join(ICONS, "Reverse.svg")))
        self.rev.setToolTip("Reverse Direction")
        self.rev.setChecked(bool(f.Reversed))
        self.end = QtWidgets.QComboBox()
        for text, key in (END_CUT if self.cut else END_BOSS):
            self.end.addItem(text, key)
        v1.addWidget(self.rev, 0, 0)
        v1.addWidget(self.end, 0, 1, 1, 2)
        self.face = FacePicker(self, "Face / Plane", ("Face",))
        self.bodypick = FacePicker(self, "Solid Body (pick any face of it)", ("Face",))
        v1.addWidget(self.face, 1, 0, 1, 3)
        v1.addWidget(self.bodypick, 2, 0, 1, 3)
        self.d1_lbl = QtWidgets.QLabel("D1")
        self.d1 = _spin(_q(f.Length) or 10.0)
        v1.addWidget(self.d1_lbl, 3, 0)
        v1.addWidget(self.d1, 3, 1, 1, 2)
        self.off_lbl = QtWidgets.QLabel("Offset")
        self.off = _spin(_q(f.Offset), lo=-100000.0)
        v1.addWidget(self.off_lbl, 4, 0)
        v1.addWidget(self.off, 4, 1, 1, 2)
        self.draft = QtWidgets.QCheckBox("Draft On/Off")
        self.draft_a = _spin(abs(_q(f.TaperAngle)) or 1.0, "°", 0.0, 89.0, 2, 0.5)
        self.draft_out = QtWidgets.QCheckBox("Draft outward")
        self.draft.setChecked(abs(_q(f.TaperAngle)) > 1e-9)
        self.draft_out.setChecked(_q(f.TaperAngle) < 0)
        v1.addWidget(self.draft, 5, 0, 1, 2)
        v1.addWidget(self.draft_a, 5, 2)
        v1.addWidget(self.draft_out, 6, 0, 1, 3)
        self.lay.addWidget(g1)
        # ---------------- Direction 2
        self.g2 = QtWidgets.QGroupBox("Direction 2")
        self.g2.setCheckable(True)
        self.g2.setChecked(f.Type == "TwoLengths")
        v2 = QtWidgets.QGridLayout(self.g2)
        v2.addWidget(QtWidgets.QLabel("Blind"), 0, 0, 1, 2)
        v2.addWidget(QtWidgets.QLabel("D2"), 1, 0)
        self.d2 = _spin(_q(f.Length2) or 10.0)
        v2.addWidget(self.d2, 1, 1)
        v2.addWidget(QtWidgets.QLabel("Draft"), 2, 0)
        self.draft2 = _spin(_q(f.TaperAngle2), "°", -89.0, 89.0, 2, 0.5)
        v2.addWidget(self.draft2, 2, 1)
        self.lay.addWidget(self.g2)
        # ---------------- Options
        g3 = QtWidgets.QGroupBox("Options")
        v3 = QtWidgets.QVBoxLayout(g3)
        self.refine = QtWidgets.QCheckBox("Merge tangent faces (clean result)")
        self.refine.setChecked(bool(f.Refine))
        v3.addWidget(self.refine)
        self.lay.addWidget(g3)
        self.lay.addStretch(1)

        self._load_end_condition()
        for w in (self.d1, self.off, self.draft_a, self.d2, self.draft2):
            w.valueChanged.connect(self.changed)
        for w in (self.rev, self.draft, self.draft_out, self.refine):
            w.toggled.connect(self.changed)
        self.g2.toggled.connect(self.changed)
        self.end.currentIndexChanged.connect(self._end_changed)
        self.dragger = DepthDragger(self._dragged)
        self._sync_visibility()
        self.changed()

    def _load_end_condition(self):
        f = self.feat
        key = {"Length": "mid" if f.Midplane else "blind", "TwoLengths": "blind",
               "UpToFirst": "next", "UpToLast": "through", "ThroughAll": "through_both" if f.Midplane else "through",
               "UpToFace": "offset" if abs(_q(f.Offset)) > 1e-9 else "surface", "UpToShape": "body"}.get(f.Type, "blind")
        i = self.end.findData(key)
        self.end.setCurrentIndex(max(i, 0))
        if f.UpToFace and f.UpToFace[0]:
            self.face.set([(f.UpToFace[0], (f.UpToFace[1] or [""])[0])])
        if getattr(f, "UpToShape", None):
            self.bodypick.set([(o, (subs or [""])[0]) for o, subs in f.UpToShape])

    def _end_changed(self, *_):
        self._sync_visibility()
        key = self.end.currentData()
        if key in ("surface", "offset") and not self.face.items:
            self.face.btn.setChecked(True)
        if key == "body" and not self.bodypick.items:
            self.bodypick.btn.setChecked(True)
        self.changed()

    def _sync_visibility(self):
        key = self.end.currentData()
        self.face.setVisible(key in ("surface", "offset"))
        self.bodypick.setVisible(key == "body")
        blind = key in ("blind", "mid")
        self.d1.setVisible(blind)
        self.d1_lbl.setVisible(blind)
        self.off.setVisible(key == "offset")
        self.off_lbl.setVisible(key == "offset")
        self.g2.setEnabled(key == "blind")
        if key != "blind":
            self.g2.setChecked(False)

    def _dragged(self, length):
        self.d1.blockSignals(True)
        self.d1.setValue(length)
        self.d1.blockSignals(False)
        self.changed()

    def apply(self):
        f = self.feat
        key = self.end.currentData()
        f.Reversed = self.rev.isChecked()
        f.Midplane = key in ("mid", "through_both")
        f.Offset = self.off.value() if key == "offset" else 0.0
        if key in ("blind", "mid"):
            f.Type = "TwoLengths" if (self.g2.isChecked() and key == "blind") else "Length"
            f.Length = self.d1.value()
            f.Length2 = self.d2.value()
            f.TaperAngle2 = self.draft2.value() if self.g2.isChecked() else 0.0
        elif key == "next":
            f.Type = "UpToFirst"
        elif key in ("through", "through_both"):
            f.Type = "ThroughAll" if self.cut else "UpToLast"
        elif key in ("surface", "offset"):
            if self.face.items:
                o, s = self.face.items[0]
                f.UpToFace = (o, [s] if s else [])
            f.Type = "UpToFace"
        elif key == "body":
            if self.bodypick.items:
                o, s = self.bodypick.items[0]
                f.UpToShape = [(o, [])]
            f.Type = "UpToShape"
        a = self.draft_a.value() if self.draft.isChecked() else 0.0
        f.TaperAngle = -a if self.draft_out.isChecked() else a
        f.Refine = self.refine.isChecked()

    def after_preview(self):
        f = self.feat
        key = self.end.currentData()
        sk = f.Profile[0] if f.Profile else None
        if sk is None or key not in ("blind", "mid") or not sk.Shape.Edges:
            self.dragger.hide()
            return
        n = sk.getGlobalPlacement().Rotation.multVec(App.Vector(0, 0, 1))
        if self.cut:
            n = n * -1
        if f.Reversed:
            n = n * -1
        bb = sk.Shape.BoundBox
        start = bb.Center
        if key == "mid":
            start = start - n * (self.d1.value() / 2.0)
        self.dragger.place(start, n, self.d1.value(), max(bb.DiagonalLength, 10.0) * 0.12,
                           "D1 = %.2f mm" % self.d1.value())

    def validate(self):
        key = self.end.currentData()
        if key in ("surface", "offset") and not self.face.items:
            return "Select a face or plane for 'Up To Surface'."
        if key == "body" and not self.bodypick.items:
            return "Select a body for 'Up To Body'."
        return None

    def cleanup(self):
        self.face.close()
        self.bodypick.close()
        self.dragger.remove()

    def on_ok(self):
        f = self.feat
        if f.Profile:
            f.Profile[0].Visibility = False
        f.Visibility = True
        if self.base is not None:
            self.base.Visibility = False


def start_extrude(cut):
    def go(sk):
        body = body_of(sk)
        doc = body.Document
        doc.openTransaction("Cut-Extrude" if cut else "Boss-Extrude")
        f = body.newObject("PartDesign::Pocket" if cut else "PartDesign::Pad", "Pocket" if cut else "Pad")
        f.Profile = sk
        f.Length = 10.0
        if getattr(f, "BaseFeature", None) is not None:
            f.BaseFeature.Visibility = False
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Control.showDialog(ExtrudePanel(f))
    sketch_first("Cut-Extrude" if cut else "Boss-Extrude", go,
                 "Sketch the profile, then click Exit Sketch (top-right corner) to continue")


# ======================================================================
# Revolved Boss/Base and Revolved Cut
# ======================================================================

def _axis_candidates(sk, body):
    out = []
    n_con = 0
    for i, g in enumerate(sk.Geometry):
        if g.TypeId == "Part::GeomLineSegment" and sk.getConstruction(i):
            out.append(("Centerline %d (sketch)" % (n_con + 1), (sk, ["Axis%d" % n_con])))
            n_con += 1
    out.append(("Sketch vertical axis", (sk, ["V_Axis"])))
    out.append(("Sketch horizontal axis", (sk, ["H_Axis"])))
    if body is not None:
        for f in body.Origin.OriginFeatures:
            if f.isDerivedFrom("App::Line"):
                out.append(("%s (origin)" % f.Label, (f, [""])))
    return out


class RevolvePanel(_Panel):
    def __init__(self, feat, editing=False):
        self.cut = feat.isDerivedFrom("PartDesign::Groove")
        self.title = "Cut-Revolve" if self.cut else "Revolve"
        self.icon = "SS_RevolveCut" if self.cut else "SS_RevolveBoss"
        super().__init__(feat, editing)
        f = feat
        sk = f.Profile[0]
        ga = QtWidgets.QGroupBox("Axis of Revolution")
        va = QtWidgets.QVBoxLayout(ga)
        self.axis = QtWidgets.QComboBox()
        self.axes = _axis_candidates(sk, body_of(sk))
        for text, _ in self.axes:
            self.axis.addItem(text)
        cur = f.ReferenceAxis
        for i, (_t, (o, subs)) in enumerate(self.axes):
            if cur and cur[0] == o and list(cur[1] or [""]) == list(subs):
                self.axis.setCurrentIndex(i)
        va.addWidget(self.axis)
        self.lay.addWidget(ga)

        g1 = QtWidgets.QGroupBox("Direction 1")
        v1 = QtWidgets.QGridLayout(g1)
        self.rev = QtWidgets.QToolButton()
        self.rev.setCheckable(True)
        self.rev.setIcon(QtGui.QIcon(os.path.join(ICONS, "Reverse.svg")))
        self.rev.setToolTip("Reverse Direction")
        self.rev.setChecked(bool(f.Reversed))
        self.end = QtWidgets.QComboBox()
        for text, key in [("Blind", "blind"), ("Mid Plane", "mid")]:
            self.end.addItem(text, key)
        self.end.setCurrentIndex(1 if f.Midplane else 0)
        v1.addWidget(self.rev, 0, 0)
        v1.addWidget(self.end, 0, 1)
        v1.addWidget(QtWidgets.QLabel("Angle"), 1, 0)
        self.a1 = _spin(_q(f.Angle) or 360.0, "°", 0.01, 360.0, 2, 5.0)
        v1.addWidget(self.a1, 1, 1)
        self.lay.addWidget(g1)

        self.g2 = QtWidgets.QGroupBox("Direction 2")
        self.g2.setCheckable(True)
        self.g2.setChecked(f.Type == "TwoAngles")
        v2 = QtWidgets.QGridLayout(self.g2)
        v2.addWidget(QtWidgets.QLabel("Angle"), 0, 0)
        self.a2 = _spin(_q(f.Angle2) or 30.0, "°", 0.0, 360.0, 2, 5.0)
        v2.addWidget(self.a2, 0, 1)
        self.lay.addWidget(self.g2)
        self.lay.addStretch(1)
        for w in (self.a1, self.a2):
            w.valueChanged.connect(self.changed)
        self.rev.toggled.connect(self.changed)
        self.g2.toggled.connect(self.changed)
        self.axis.currentIndexChanged.connect(self.changed)
        self.end.currentIndexChanged.connect(self.changed)
        self.changed()

    def apply(self):
        f = self.feat
        o, subs = self.axes[self.axis.currentIndex()][1]
        f.ReferenceAxis = (o, subs)
        mid = self.end.currentData() == "mid"
        f.Midplane = mid
        f.Reversed = self.rev.isChecked()
        two = self.g2.isChecked() and not mid
        f.Type = "TwoAngles" if two else "Angle"
        f.Angle = self.a1.value()
        if two:
            f.Angle2 = self.a2.value()

    def on_ok(self):
        f = self.feat
        f.Profile[0].Visibility = False
        f.Visibility = True
        if self.base is not None:
            self.base.Visibility = False


def start_revolve(cut):
    def go(sk):
        body = body_of(sk)
        doc = body.Document
        doc.openTransaction("Cut-Revolve" if cut else "Revolve")
        f = body.newObject("PartDesign::Groove" if cut else "PartDesign::Revolution",
                           "Groove" if cut else "Revolution")
        f.Profile = sk
        axes = _axis_candidates(sk, body)
        f.ReferenceAxis = axes[0][1]  # a sketch centerline if there is one, like SolidWorks
        f.Angle = 360.0
        if getattr(f, "BaseFeature", None) is not None:
            f.BaseFeature.Visibility = False
        doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Control.showDialog(RevolvePanel(f))
    sketch_first("Cut-Revolve" if cut else "Revolve", go,
                 "Sketch the profile and a centerline (construction line), then Exit Sketch to continue")


# ======================================================================
# Fillet, Chamfer, Shell - panel first, then pick edges/faces
# ======================================================================

DRESS = {
    "fillet": ("PartDesign::Fillet", "Fillet", "SS_Fillet", ("Edge", "Face"), "Items To Fillet"),
    "chamfer": ("PartDesign::Chamfer", "Chamfer", "SS_Chamfer", ("Edge", "Face"), "Items To Chamfer"),
    "shell": ("PartDesign::Thickness", "Shell", "SS_Shell", ("Face",), "Faces to Remove"),
}


class DressUpPanel(_Panel):
    def __init__(self, feat, kind, editing=False):
        self.kind = kind
        _t, self.title, self.icon, self.types, items_title = DRESS[kind]
        super().__init__(feat, editing)
        f = feat
        self.target = f.Base[0] if f.Base else self.base
        self.items = [s for s in (f.Base[1] if f.Base else []) if s]

        gi = QtWidgets.QGroupBox(items_title)
        vi = QtWidgets.QVBoxLayout(gi)
        self.list = QtWidgets.QListWidget()
        self.list.setStyleSheet("QListWidget{background:#e3effd;color:#222}")
        self.list.setMaximumHeight(110)
        self.list.setToolTip("Click edges/faces in the graphics area. Select an entry and press Delete to remove it.")
        vi.addWidget(self.list)
        row = QtWidgets.QHBoxLayout()
        clr = QtWidgets.QPushButton("Clear Selections")
        clr.clicked.connect(self._clear)
        row.addWidget(clr)
        row.addStretch(1)
        vi.addLayout(row)
        self.lay.addWidget(gi)

        gp = QtWidgets.QGroupBox("Parameters")
        vp = QtWidgets.QGridLayout(gp)
        if kind == "fillet":
            vp.addWidget(QtWidgets.QLabel("Radius"), 0, 0)
            self.r = _spin(_q(f.Radius) or 1.0, lo=0.001)
            vp.addWidget(self.r, 0, 1)
            self.r.valueChanged.connect(self.changed)
        elif kind == "chamfer":
            self.ctype = QtWidgets.QComboBox()
            for text, val in [("Equal distance", "Equal distance"), ("Distance distance", "Two distances"),
                              ("Angle distance", "Distance and Angle")]:
                self.ctype.addItem(text, val)
            self.ctype.setCurrentIndex(max(0, self.ctype.findData(f.ChamferType)))
            vp.addWidget(self.ctype, 0, 0, 1, 2)
            self.s1_lbl = QtWidgets.QLabel("Distance")
            self.s1 = _spin(_q(f.Size) or 1.0, lo=0.001)
            self.s2_lbl = QtWidgets.QLabel("Distance 2")
            self.s2 = _spin(_q(f.Size2) or 1.0, lo=0.001)
            self.ang_lbl = QtWidgets.QLabel("Angle")
            self.ang = _spin(_q(f.Angle) or 45.0, "°", 0.01, 179.99, 2, 1.0)
            self.flip = QtWidgets.QCheckBox("Flip direction")
            self.flip.setChecked(bool(f.FlipDirection))
            for r, (l, w) in enumerate([(self.s1_lbl, self.s1), (self.s2_lbl, self.s2), (self.ang_lbl, self.ang)], 1):
                vp.addWidget(l, r, 0)
                vp.addWidget(w, r, 1)
            vp.addWidget(self.flip, 4, 0, 1, 2)
            for w in (self.s1, self.s2, self.ang):
                w.valueChanged.connect(self.changed)
            self.flip.toggled.connect(self.changed)
            self.ctype.currentIndexChanged.connect(self._ctype)
            self._ctype()
        else:
            vp.addWidget(QtWidgets.QLabel("Thickness"), 0, 0)
            self.t = _spin(_q(f.Value) or 1.0, lo=0.001)
            vp.addWidget(self.t, 0, 1)
            self.out = QtWidgets.QCheckBox("Shell outward")
            self.out.setChecked(bool(f.Reversed))
            vp.addWidget(self.out, 1, 0, 1, 2)
            self.t.valueChanged.connect(self.changed)
            self.out.toggled.connect(self.changed)
        self.lay.addWidget(gp)

        go = QtWidgets.QGroupBox("Preview")
        vo = QtWidgets.QVBoxLayout(go)
        self.full = QtWidgets.QRadioButton("Full preview")
        self.partial = QtWidgets.QRadioButton("Partial preview (pick items)")
        self.partial.setChecked(True)
        vo.addWidget(self.full)
        vo.addWidget(self.partial)
        self.full.toggled.connect(self._preview_mode)
        self.lay.addWidget(go)
        self.lay.addStretch(1)

        self._refresh_list()
        self.list.installEventFilter(self._keys())
        self._preview_mode()
        Gui.Selection.clearSelection()
        for s in self.items:
            Gui.Selection.addSelection(self.target, s)
        Gui.Selection.addObserver(self)

    def _keys(self):
        panel = self

        class F(QtCore.QObject):
            def eventFilter(self, obj, ev):
                if ev.type() == QtCore.QEvent.KeyPress and ev.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
                    for it in panel.list.selectedItems():
                        s = it.text()
                        if s in panel.items:
                            panel.items.remove(s)
                            Gui.Selection.removeSelection(panel.target, s)
                    panel._refresh_list()
                    panel.changed()
                    return True
                return False
        self._key_filter = F()
        return self._key_filter

    def _ctype(self, *_):
        t = self.ctype.currentData()
        self.s2.setVisible(t == "Two distances")
        self.s2_lbl.setVisible(t == "Two distances")
        self.ang.setVisible(t == "Distance and Angle")
        self.ang_lbl.setVisible(t == "Distance and Angle")
        self.changed()

    def _clear(self):
        self.items = []
        Gui.Selection.clearSelection()
        self._refresh_list()
        self.changed()

    def _refresh_list(self):
        self.list.clear()
        for s in self.items:
            self.list.addItem(s)

    def _preview_mode(self, *_):
        full = self.full.isChecked()
        if full:
            self.apply()
            self.doc.recompute()
        self.feat.Visibility = full
        if self.target is not None:
            self.target.Visibility = not full

    # selection observer
    def addSelection(self, doc, obj, sub, pnt):
        if self.closed or self.target is None or obj != self.target.Name:
            return
        if any(sub.startswith(t) for t in self.types) and sub not in self.items:
            self.items.append(sub)
            self._refresh_list()
            self.changed()

    def removeSelection(self, doc, obj, sub):
        if self.closed or self.target is None or obj != self.target.Name:
            return
        if sub in self.items:
            self.items.remove(sub)
            self._refresh_list()
            self.changed()

    def changed(self, *_):
        if self.full.isChecked() if hasattr(self, "full") else False:
            super().changed()

    def apply(self):
        f = self.feat
        if self.target is not None:
            f.Base = (self.target, list(self.items))
        if self.kind == "fillet":
            f.Radius = self.r.value()
        elif self.kind == "chamfer":
            f.ChamferType = self.ctype.currentData()
            f.Size = self.s1.value()
            f.Size2 = self.s2.value()
            f.Angle = self.ang.value()
            f.FlipDirection = self.flip.isChecked()
        else:
            f.Value = self.t.value()
            f.Reversed = self.out.isChecked()
            f.Join = "Intersection"

    def validate(self):
        if not self.items:
            return "Select at least one %s." % ("face" if self.kind == "shell" else "edge or face")
        return None

    def cleanup(self):
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass
        Gui.Selection.clearSelection()

    def on_ok(self):
        self.feat.Visibility = True
        if self.target is not None:
            self.target.Visibility = False

    def on_cancel(self):
        if self.target is not None:
            self.target.Visibility = True


def start_dressup(kind):
    if Gui.Control.activeDialog():
        status("Finish the open command first")
        return
    body = active_body()
    base = body.Tip if body is not None else None
    if base is None or not hasattr(base, "Shape") or not base.Shape.Solids:
        warn(DRESS[kind][1], "Create a solid first (e.g. an Extruded Boss/Base).")
        return
    pre = []
    for s in Gui.Selection.getSelectionEx():
        if s.Object == base:
            pre += [n for n in s.SubElementNames if any(n.startswith(t) for t in DRESS[kind][3])]
    doc = body.Document
    doc.openTransaction(DRESS[kind][1])
    f = body.newObject(DRESS[kind][0], DRESS[kind][1])
    f.Base = (base, pre)
    if kind == "fillet":
        f.Radius = 1.0
    elif kind == "chamfer":
        f.Size = 1.0
    else:
        f.Value = 1.0
    Gui.Control.showDialog(DressUpPanel(f, kind))
    if not pre:
        status("Select %s in the graphics area" % ("faces to remove" if kind == "shell" else "edges or faces"))


# ======================================================================
# Hole Wizard: pick a face, place points, Exit Sketch -> hole specification
# ======================================================================

def start_hole_wizard():
    def place(target):
        sketch_on(target, finish_hole, tool="Sketcher_CreatePoint",
                  hint="Hole Wizard - Positions: click to place hole centers, then Exit Sketch")
    k = classify()
    if k and k[0] == "sketch":
        finish_hole(k[1])
        return
    if k:
        place(k)
        return
    if Gui.Control.activeDialog():
        status("Finish the open command first")
        return
    Gui.Control.showDialog(PickPanel(
        "Hole Position", "Select the planar face or plane where the holes go.\n\n"
                         "You'll then click to place the hole centers (points), and choose the hole type after Exit Sketch.",
        ("plane", "face"), place))


def finish_hole(sk):
    import Part
    import Sketcher
    body = body_of(sk)
    doc = body.Document
    doc.openTransaction("Hole")
    pts = [i for i, g in enumerate(sk.Geometry) if g.TypeId == "Part::GeomPoint" and not sk.getConstruction(i)]
    circles = [g for g in sk.Geometry if g.TypeId == "Part::GeomCircle"]
    for i in pts:
        p = sk.Geometry[i]
        c = sk.addGeometry(Part.Circle(App.Vector(p.X, p.Y, 0), App.Vector(0, 0, 1), 2.5))
        sk.addConstraint(Sketcher.Constraint("Coincident", c, 3, i, 1))
    if not pts and not circles:
        doc.abortTransaction()
        warn("Hole Wizard", "No hole positions: place at least one point in the sketch.")
        return
    h = body.newObject("PartDesign::Hole", "Hole")
    h.Profile = sk
    sk.Visibility = False
    if getattr(h, "BaseFeature", None) is not None:
        h.BaseFeature.Visibility = False
    doc.commitTransaction()
    doc.recompute()
    Gui.ActiveDocument.setEdit(h.Name)  # FreeCAD's hole spec panel (type, size, end condition)
    status("Hole Wizard - Type: choose the hole type, size and end condition, then OK")


# ======================================================================
# Re-opening our panels on double-click / Edit Feature
# ======================================================================

EDITABLE = {
    "PartDesign::Pad": lambda f: ExtrudePanel(f, True),
    "PartDesign::Pocket": lambda f: ExtrudePanel(f, True),
    "PartDesign::Revolution": lambda f: RevolvePanel(f, True),
    "PartDesign::Groove": lambda f: RevolvePanel(f, True),
    "PartDesign::Fillet": lambda f: DressUpPanel(f, "fillet", True),
    "PartDesign::Chamfer": lambda f: DressUpPanel(f, "chamfer", True),
    "PartDesign::Thickness": lambda f: DressUpPanel(f, "shell", True),
}


def reopen(feat):
    """Swap FreeCAD's own task panel for ours."""
    make = EDITABLE.get(feat.TypeId)
    if make is None:
        return
    Gui.ActiveDocument.resetEdit()
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
    doc = feat.Document
    doc.openTransaction("Edit " + feat.Label)
    base = getattr(feat, "BaseFeature", None)
    feat.Visibility = True
    if base is not None:
        base.Visibility = False
    Gui.Control.showDialog(make(feat))


# ======================================================================
# Commands
# ======================================================================

class _FeatCmd:
    def __init__(self, menu, tip, icon, fn, accel=""):
        self.menu, self.tip, self.icon, self.fn, self.accel = menu, tip, icon, fn, accel

    def GetResources(self):
        r = {"Pixmap": os.path.join(SW_ICONS, self.icon + ".svg"), "MenuText": self.menu, "ToolTip": self.tip}
        if self.accel:
            r["Accel"] = self.accel
        return r

    def IsActive(self):
        return not Gui.Control.activeDialog() or commands.editing_sketch() is not None

    def Activated(self):
        self.fn()


def register():
    cmds = [
        ("SS_ExtrudeBoss", "Extruded Boss/Base", "Extrudes a sketch. Click it first, then pick a plane - or select a sketch.",
         "SS_ExtrudeBoss", lambda: start_extrude(False)),
        ("SS_ExtrudeCut", "Extruded Cut", "Cuts a solid by extruding a sketch.", "SS_ExtrudeCut", lambda: start_extrude(True)),
        ("SS_RevolveBoss", "Revolved Boss/Base", "Revolves a sketch around a centerline.", "SS_RevolveBoss",
         lambda: start_revolve(False)),
        ("SS_RevolveCut", "Revolved Cut", "Cuts a solid by revolving a sketch.", "SS_RevolveCut", lambda: start_revolve(True)),
        ("SS_Fillet", "Fillet", "Rounds edges or faces. Pick them before or after clicking Fillet.", "SS_Fillet",
         lambda: start_dressup("fillet")),
        ("SS_Chamfer", "Chamfer", "Bevels edges or faces.", "SS_Chamfer", lambda: start_dressup("chamfer")),
        ("SS_Shell", "Shell", "Hollows the part, removing the faces you pick.", "SS_Shell", lambda: start_dressup("shell")),
        ("SS_HoleWizard", "Hole Wizard", "Pick a face, place hole centers, then choose the hole type.", "SS_HoleWizard",
         start_hole_wizard),
    ]
    for name, menu, tip, icon, fn in cmds:
        Gui.addCommand(name, _FeatCmd(menu, tip, icon, fn))
