"""SolidWorks-style assembly commands.

FreeCAD only enables its joint (mate) tools while the assembly is activated
(in edit mode), one part is grounded and the assembly holds two parts.
SolidWorks has none of those gates, so these wrappers take care of them:
the assembly is activated on demand, the first component is fixed
automatically ("(f)" in SolidWorks) and missing steps are explained.
"""
import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

SW_ICONS = os.path.join(os.path.dirname(__file__), "icons", "sw")
ASM_PREFS = "User parameter:BaseApp/Preferences/Mod/Assembly"

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


def _modules():
    import UtilsAssembly
    import CommandCreateJoint
    return UtilsAssembly, CommandCreateJoint


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
    return [o for o in asm.OutList if hasattr(o, "Placement") and not hasattr(o, "ObjectToGround")]


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


def start_mate(index):
    asm = _ready(2)
    if asm is None:
        return
    ensure_fixed(asm)
    _u, ccj = _modules()
    ccj.activateJoint(index)


def insert_components():
    asm = _ready()
    if asm is None:
        return
    # SolidWorks fixes the first component without asking.
    p = App.ParamGet(ASM_PREFS)
    if p.GetInt("GroundFirstPart", 0) == 0:
        p.SetInt("GroundFirstPart", 1)
    Gui.runCommand("Assembly_InsertLink", 0)


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
    def __init__(self, menu, tip, icon, fn):
        self.menu, self.tip, self.icon, self.fn = menu, tip, icon, fn

    def GetResources(self):
        p = os.path.join(SW_ICONS, self.icon + ".svg")
        return {"Pixmap": p if os.path.exists(p) else self.icon, "MenuText": self.menu, "ToolTip": self.tip}

    def IsActive(self):
        return find_assembly() is not None and not Gui.Control.activeDialog()

    def Activated(self):
        self.fn()


def register():
    try:
        _modules()
    except Exception as e:
        App.Console.PrintLog("SolidStyle: Assembly module unavailable: %s\n" % e)
        return
    Gui.addCommand("SS_Mate", _AsmCmd(
        "Mate", "Add a mate: pick a face/edge on each of two components, then choose the mate type.",
        "Assembly_CreateJointDistance", lambda: start_mate(5)))
    Gui.addCommand("SS_InsertComponents", _AsmCmd(
        "Insert Components", "Insert a part or sub-assembly. The first one is fixed automatically.",
        "Assembly_InsertLink", insert_components))
    Gui.addCommand("SS_FixFloat", _AsmCmd(
        "Fix / Float", "Fix (ground) or float the selected components.", "Assembly_ToggleGrounded", fix_float))
    Gui.addCommand("SS_RebuildAssembly", _AsmCmd(
        "Rebuild Assembly", "Solve all mates.", "Assembly_SolveAssembly",
        run_after_activate("Assembly_SolveAssembly", 1, True)))
    Gui.addCommand("SS_ExplodedView", _AsmCmd(
        "Exploded View", "Create an exploded view.", "Assembly_CreateView",
        run_after_activate("Assembly_CreateView", 1, True)))
    for fc, (idx, menu, tip) in MATES.items():
        Gui.addCommand("SS_" + fc.split("_", 1)[1], _AsmCmd(menu, tip, fc, lambda i=idx: start_mate(i)))
