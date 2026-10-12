"""Workbench glue: menus, observers, context-sensitive tabs, staying in this
workbench when FreeCAD would auto-switch (e.g. to Sketcher)."""
import re
import time

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

from solidstyle import assembly, catalog, commands, features, look, shortcuts

WB = "SolidStyleWorkbench"
PARAMS = "User parameter:BaseApp/Preferences/Mod/SolidStyle"
AUTO_SWITCHERS = {"SketcherWorkbench", "PartDesignWorkbench", "AssemblyWorkbench", "TechDrawWorkbench"}

_active = False
_timer = None
_observer = None
_last_edit = None        # view provider in edit at the last poll
_tab_before_edit = None
_last_mdi = None


def _try_import(*mods):
    for m in mods:
        try:
            __import__(m)
        except Exception as e:
            App.Console.PrintLog("SolidStyle: could not load %s: %s\n" % (m, e))


def _flatten(items):
    out = []
    for item in items:
        if item == "|":
            continue
        if item[0] == "big":
            out.append(item[1])
        elif item[0] == "drop":
            out.extend(c for c, _t in item[2])
        elif item[0] == "stack":
            out.extend(c for c, _t in item[1])
    seen, res = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            res.append(c)
    return res


def initialize(wb):
    # Load the GUI parts of the modules whose tools we expose.
    _try_import("PartGui", "PartDesignGui", "SketcherGui", "TechDrawGui", "MeasureGui",
                "Assembly_rc", "CommandCreateAssembly", "CommandInsertLink", "CommandCreateJoint",
                "CommandSolveAssembly", "CommandCreateView", "CommandCreateBom")
    commands.register()
    features.register()
    assembly.register()
    known = set(Gui.listCommands())

    def ok(cmds):
        return [c for c in cmds if c in known]

    wb.appendToolbar("Quick Access", ok(["SS_NewPart", "SS_NewAssembly", "SS_NewDrawing", "Separator",
                                         "SS_Rebuild", "SS_ShortcutBar"]))

    # Menus: every CommandManager tool also lives in a menu (FreeCAD only creates a
    # command's action - and therefore its icon and shortcut - once it is placed somewhere).
    for tab, items in catalog.TABS:
        wb.appendMenu(["&Insert", tab], ok(_flatten(items)))
    wb.appendMenu(["&View", "Orientation (SolidWorks)"],
                  ok([v[0] for v in commands.VIEWS] + ["SS_NormalTo", "SS_ZoomFit"]))
    wb.appendMenu("&Tools", ok(["SS_Rebuild", "SS_ShortcutBar", "SS_MassProperties", "Std_Measure",
                                "Separator", "SS_ApplyLook", "SS_RestoreLook"]))
    wb.appendMenu("&File", ok(["SS_NewPart", "SS_NewAssembly", "SS_NewDrawing"]))

    global _timer, _observer
    _observer = DocObserver()
    App.addDocumentObserver(_observer)
    Gui.getMainWindow().workbenchActivated.connect(_on_workbench_activated)
    _timer = QtCore.QTimer()
    _timer.timeout.connect(_poll)
    _timer.start(250)


def activated():
    global _active
    _active = True
    from solidstyle import ui
    p = App.ParamGet(PARAMS)
    if not p.GetBool("FirstRunDone", False):
        p.SetBool("FirstRunDone", True)
        look.apply_sw_theme(keep_navigation=False)
        App.Console.PrintMessage(
            "SolidStyle: applied the SolidWorks look (Tools > Restore My Settings undoes it).\n")
    shortcuts.take_over()
    ui.refresh_known()
    ui.show_command_manager(True)
    ui.update_views(True)


def deactivated():
    global _active, _deactivated_at
    _active = False
    _deactivated_at = time.time()
    shortcuts.give_back()
    from solidstyle import ui
    ui.show_command_manager(False)
    ui.update_views(False)


def context_menu(wb, recipient):
    if commands.editing_sketch():
        wb.appendContextMenu("", ["Sketcher_Dimension", "Sketcher_ToggleConstruction",
                                  "Sketcher_ConstrainCoincidentUnified", "Sketcher_ConstrainHorizontal",
                                  "Sketcher_ConstrainVertical", "Sketcher_ConstrainEqual",
                                  "Separator", "Sketcher_LeaveSketch"])
        return
    if Gui.Selection.getSelection():
        wb.appendContextMenu("", ["SS_NormalTo", "Std_ToggleVisibility", "Std_SetAppearance",
                                  "PartDesign_MoveTip", "SS_MassProperties", "Separator"])


# ---------------------------------------------------------------- staying in this workbench

def _on_workbench_activated(name):
    global _deactivated_at
    # Note: this signal arrives before our Deactivated() runs.
    if name in AUTO_SWITCHERS and _active:
        _deactivated_at = time.time()
        # Decide once FreeCAD has finished entering edit mode (which may take a moment).
        for ms in (0, 100, 300, 700):
            QtCore.QTimer.singleShot(ms, _maybe_switch_back)


def _edit_key():
    gdoc = Gui.ActiveDocument
    vp = gdoc.getInEdit() if gdoc else None
    obj = getattr(vp, "Object", None) if vp is not None else None
    return (obj.Document.Name, obj.Name) if obj is not None else None


def _maybe_switch_back():
    # Only bounce back when an edit *just started* while we were the active workbench;
    # a deliberate workbench change by the user is left alone.
    if Gui.activeWorkbench().name() == WB:
        return
    key = _edit_key()
    if key is not None and key != _last_edit and time.time() - _deactivated_at < 1.5:
        Gui.activateWorkbench(WB)


_deactivated_at = 0.0


def _poll():
    global _last_edit, _tab_before_edit, _last_mdi
    if not _active:
        return  # _last_edit stays frozen at the state we last saw while active
    from solidstyle import ui
    try:
        ui.update_views(True)
        edit = _edit_key()
        if edit != _last_edit:
            obj = App.getDocument(edit[0]).getObject(edit[1]) if edit else None
            if obj is not None and obj.isDerivedFrom("Sketcher::SketchObject"):
                if _tab_before_edit is None:
                    _tab_before_edit = ui.current_tab()
                ui.select_tab("Sketch")
            elif obj is not None and obj.TypeId == "Assembly::AssemblyObject":
                if _tab_before_edit is None:
                    _tab_before_edit = ui.current_tab()
                ui.select_tab("Assembly")
            elif obj is not None and obj.TypeId in features.EDITABLE and \
                    App.ParamGet(PARAMS).GetBool("SolidWorksPanels", True):
                QtCore.QTimer.singleShot(0, lambda o=obj: features.reopen(o))
            elif edit is None and _tab_before_edit is not None:
                ui.select_tab(_tab_before_edit)
                _tab_before_edit = None
            _last_edit = edit
        area = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
        sub = area.activeSubWindow() if area is not None else None
        mdi = sub.widget() if sub is not None else None
        kind = mdi.metaObject().className() if mdi is not None else None
        if kind != _last_mdi:
            if kind == "TechDrawGui::MDIViewPage":
                ui.select_tab("Drawing")
            elif _last_mdi == "TechDrawGui::MDIViewPage" and kind == "Gui::View3DInventor":
                ui.select_tab("Features")
            _last_mdi = kind
    except Exception as e:  # never let the poll timer spam
        App.Console.PrintLog("SolidStyle poll: %s\n" % e)


# ---------------------------------------------------------------- SolidWorks-style naming

def relabel_origin(body):
    origin = getattr(body, "Origin", None)
    if origin is None:
        return
    for f in origin.OriginFeatures:
        role = getattr(f, "Role", "") or re.sub(r"\d+$", "", f.Name)
        if role in catalog.ORIGIN_NAMES:
            f.Label = catalog.ORIGIN_NAMES[role]


def _relabel_feature(doc_name, obj_name):
    doc = App.getDocument(doc_name) if doc_name in App.listDocuments() else None
    obj = doc.getObject(obj_name) if doc else None
    if obj is None:
        return
    prefix = catalog.FEATURE_NAMES.get(obj.TypeId)
    if prefix is None:
        return
    # only rename FreeCAD's default label ("Pad", "Pad001"...), never a user's name
    if not re.fullmatch(re.escape(obj.Name.rstrip("0123456789")) + r"\d*", obj.Label):
        return
    pat = re.compile(re.escape(prefix) + r"(\d+)$")
    n = 0
    for o in doc.Objects:
        m = pat.match(o.Label)
        if m:
            n = max(n, int(m.group(1)))
    obj.Label = "%s%d" % (prefix, n + 1)


class DocObserver:
    def __init__(self):
        self.restoring = set()

    def slotStartRestoreDocument(self, doc):
        self.restoring.add(doc.Name)

    def slotFinishRestoreDocument(self, doc):
        self.restoring.discard(doc.Name)

    def slotCreatedObject(self, obj):
        if not _active:
            return
        doc = obj.Document
        if doc.Name in self.restoring:
            return
        if obj.TypeId == "PartDesign::Body":
            QtCore.QTimer.singleShot(0, lambda b=obj: relabel_origin(b))
        elif obj.TypeId in catalog.FEATURE_NAMES:
            QtCore.QTimer.singleShot(0, lambda d=doc.Name, n=obj.Name: _relabel_feature(d, n))
