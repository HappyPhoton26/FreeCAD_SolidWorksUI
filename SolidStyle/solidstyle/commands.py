"""SolidStyle's own commands (SolidWorks shortcuts, New Part, Normal To, Mass Properties...)."""
import os

import FreeCAD as App
import FreeCADGui as Gui

ICONS = os.path.join(os.path.dirname(__file__), "icons")


def icon(name):
    return os.path.join(ICONS, name + ".svg")


def has_doc():
    return App.ActiveDocument is not None


def editing_sketch():
    gdoc = Gui.ActiveDocument
    if not gdoc:
        return None
    vp = gdoc.getInEdit()
    if vp and vp.Object.isDerivedFrom("Sketcher::SketchObject"):
        return vp.Object
    return None


class _Cmd:
    pixmap = ""
    menu = ""
    tip = ""
    accel = ""
    needs_doc = True

    def GetResources(self):
        res = {"Pixmap": self.pixmap, "MenuText": self.menu, "ToolTip": self.tip or self.menu}
        if self.accel:
            res["Accel"] = self.accel
        return res

    def IsActive(self):
        return has_doc() if self.needs_doc else True


# ---------------------------------------------------------------- views

class _View(_Cmd):
    def __init__(self, menu, accel, std, pixmap):
        self.menu, self.accel, self.std, self.pixmap = menu, accel, std, pixmap
        self.tip = "%s view (%s)" % (menu, accel)

    def Activated(self):
        Gui.runCommand(self.std, 0)


VIEWS = [
    ("SS_ViewFront", "Front", "Ctrl+1", "Std_ViewFront", "view-front"),
    ("SS_ViewBack", "Back", "Ctrl+2", "Std_ViewRear", "view-rear"),
    ("SS_ViewLeft", "Left", "Ctrl+3", "Std_ViewLeft", "view-left"),
    ("SS_ViewRight", "Right", "Ctrl+4", "Std_ViewRight", "view-right"),
    ("SS_ViewTop", "Top", "Ctrl+5", "Std_ViewTop", "view-top"),
    ("SS_ViewBottom", "Bottom", "Ctrl+6", "Std_ViewBottom", "view-bottom"),
    ("SS_ViewIso", "Isometric", "Ctrl+7", "Std_ViewIsometric", "view-axonometric"),
]


class NormalTo(_Cmd):
    pixmap = icon("NormalTo")
    menu = "Normal To"
    tip = "Look straight at the selected face or plane, or at the sketch being edited (Ctrl+8)"
    accel = "Ctrl+8"

    def Activated(self):
        normal, center = self._target()
        if normal is None:
            if editing_sketch():
                Gui.runCommand("Sketcher_ViewSketch", 0)
            else:
                App.Console.PrintWarning("Normal To: select a planar face, a plane or a sketch\n")
            return
        view = Gui.ActiveDocument.ActiveView
        rot = App.Rotation(App.Vector(0, 0, 1), normal)
        # Same face again flips to its back side, like SolidWorks.
        cur = view.getViewDirection()
        if cur.getAngle(normal * -1) < 1e-3:
            rot = App.Rotation(App.Vector(0, 0, 1), normal * -1)
        view.setCameraOrientation(rot)
        view.fitAll()

    def _target(self):
        for sel in Gui.Selection.getSelectionEx("", 0):
            obj = sel.Object
            for sub in sel.SubElementNames:
                try:
                    shp = obj.getSubObject(sub)
                except Exception:
                    shp = None
                if shp is not None and shp.ShapeType == "Face":
                    try:
                        u0, u1, v0, v1 = shp.ParameterRange
                        n = shp.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
                        return n, shp.CenterOfMass
                    except Exception:
                        pass
            plc = None
            if obj.isDerivedFrom("Sketcher::SketchObject") or obj.isDerivedFrom("App::Plane") \
                    or obj.isDerivedFrom("PartDesign::Plane"):
                plc = obj.getGlobalPlacement()
            if plc is not None:
                return plc.Rotation.multVec(App.Vector(0, 0, 1)), plc.Base
        return None, None


class ZoomFit(_Cmd):
    pixmap = "zoom-all"
    menu = "Zoom to Fit"
    tip = "Zoom to fit (F)"
    accel = "F"

    def Activated(self):
        Gui.runCommand("Std_ViewFitAll", 0)


class Rebuild(_Cmd):
    pixmap = icon("Rebuild")
    menu = "Rebuild"
    tip = "Rebuild the model (Ctrl+B)"
    accel = "Ctrl+B"

    def Activated(self):
        doc = App.ActiveDocument
        for o in doc.Objects:
            o.touch()
        doc.recompute()


class ShortcutBar(_Cmd):
    pixmap = icon("ShortcutBar")
    menu = "Shortcut Bar"
    tip = "Pop up the context shortcut toolbar at the mouse (S)"
    accel = "S"
    needs_doc = False

    def Activated(self):
        from solidstyle import ui
        ui.show_shortcut_bar()


# ---------------------------------------------------------------- new documents

def _next_name(prefix):
    used = {d.Label for d in App.listDocuments().values()}
    i = 1
    while "%s%d" % (prefix, i) in used:
        i += 1
    return "%s%d" % (prefix, i)


class NewPart(_Cmd):
    pixmap = icon("NewPart")
    menu = "New Part"
    tip = "New part document with a body and Front/Top/Right planes"
    needs_doc = False

    def Activated(self):
        name = _next_name("Part")
        doc = App.newDocument(name)
        doc.Label = name
        body = doc.addObject("PartDesign::Body", "Body")
        body.Label = name
        Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", body)
        from solidstyle import setup
        setup.relabel_origin(body)
        doc.recompute()
        Gui.ActiveDocument.ActiveView.viewIsometric()
        Gui.SendMsgToActiveView("ViewFit")


class NewAssembly(_Cmd):
    pixmap = icon("NewAssembly")
    menu = "New Assembly"
    tip = "New assembly document, then pick the parts to insert"
    needs_doc = False

    def Activated(self):
        from solidstyle import assembly
        assembly.new_assembly()


class NewDrawing(_Cmd):
    pixmap = icon("NewDrawing")
    menu = "New Drawing"
    tip = "New drawing sheet in the current document"

    def Activated(self):
        Gui.runCommand("TechDraw_PageDefault", 0)
        from solidstyle import ui
        ui.select_tab("Drawing")


# ---------------------------------------------------------------- evaluate

class MassProperties(_Cmd):
    pixmap = icon("MassProperties")
    menu = "Mass Properties"
    tip = "Mass, volume, surface area, center of mass and moments of inertia"

    def Activated(self):
        from solidstyle import ui
        ui.MassPropertiesDialog(self.targets()).exec_()

    @staticmethod
    def targets():
        objs = [s.Object for s in Gui.Selection.getSelectionEx()]
        if not objs:
            body = Gui.ActiveDocument.ActiveView.getActiveObject("pdbody")
            objs = [body] if body else []
        if not objs:
            objs = [o for o in App.ActiveDocument.Objects
                    if o.isDerivedFrom("PartDesign::Body") and o.Visibility]
        if not objs:
            objs = [o for o in App.ActiveDocument.Objects
                    if hasattr(o, "Shape") and o.Visibility and not o.InList
                    and o.Shape.Solids]
        return [o for o in objs if hasattr(o, "Shape") and o.Shape.Solids]


# ---------------------------------------------------------------- look & feel

class ApplyLook(_Cmd):
    pixmap = icon("Look")
    menu = "Apply SolidWorks Look && Feel"
    tip = "Gradient background, grey parts, blue/black sketches, middle-mouse rotate. Your settings are backed up."
    needs_doc = False

    def Activated(self):
        from solidstyle import look
        look.apply_sw_theme()
        App.Console.PrintMessage("SolidStyle: SolidWorks look applied (Restore My Settings undoes it)\n")


class RestoreLook(_Cmd):
    pixmap = icon("Restore")
    menu = "Restore My Settings"
    tip = "Undo everything 'Apply SolidWorks Look & Feel' changed"
    needs_doc = False

    def Activated(self):
        from solidstyle import look
        if look.restore():
            App.Console.PrintMessage("SolidStyle: your original view settings were restored\n")


class Diagnostics(_Cmd):
    pixmap = icon("Restore")
    menu = "Copy SolidWorks Style Diagnostics"
    tip = "Copy a short report (versions, folders, panels, errors) to the clipboard, to paste when asking for help"
    needs_doc = False

    def Activated(self):
        import platform
        import sys
        from PySide import QtWidgets
        from solidstyle import setup
        mw = Gui.getMainWindow()
        lines = [
            "FreeCAD %s, Python %s, %s" % (".".join(App.Version()[:4]), platform.python_version(), platform.platform()),
            "workbench code: %s" % os.path.dirname(os.path.abspath(__file__)),
            "user data: %s" % App.getUserAppDataDir(),
            "active workbench: %s" % Gui.activeWorkbench().name(),
            "docks: %s" % ", ".join("%s%s" % (d.objectName(), "" if d.isVisible() else " (hidden)")
                                    for d in mw.findChildren(QtWidgets.QDockWidget)),
            "start-up problems: %s" % (setup._problems or "none"),
            "older copies: %s" % (setup.other_copies or "none"),
            "solidstyle folders on sys.path: %s" % [p for p in sys.path
                                                   if os.path.isdir(os.path.join(p, "solidstyle"))],
        ]
        text = "\n".join(lines)
        QtWidgets.QApplication.clipboard().setText(text)
        QtWidgets.QMessageBox.information(mw, "SolidWorks Style", "Copied to the clipboard:\n\n" + text)


def register():
    for name, menu, accel, std, pix in VIEWS:
        Gui.addCommand(name, _View(menu, accel, std, pix))
    for name, cls in [("SS_NormalTo", NormalTo), ("SS_ZoomFit", ZoomFit), ("SS_Rebuild", Rebuild),
                      ("SS_ShortcutBar", ShortcutBar), ("SS_NewPart", NewPart),
                      ("SS_NewAssembly", NewAssembly), ("SS_NewDrawing", NewDrawing),
                      ("SS_MassProperties", MassProperties), ("SS_ApplyLook", ApplyLook),
                      ("SS_RestoreLook", RestoreLook), ("SS_Diagnostics", Diagnostics)]:
        Gui.addCommand(name, cls())
