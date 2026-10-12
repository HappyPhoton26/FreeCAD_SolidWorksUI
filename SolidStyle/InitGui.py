# SolidStyle workbench - a SolidWorks-like front end for FreeCAD.
import os
import FreeCAD as App
import FreeCADGui as Gui


class SolidStyleWorkbench(Gui.Workbench):
    MenuText = "SolidWorks Style"
    ToolTip = "SolidWorks-like CommandManager, names, shortcuts and look for Part Design, Sketcher, Assembly and TechDraw"
    Icon = os.path.join(App.getUserAppDataDir(), "Mod", "SolidStyle", "solidstyle", "icons", "Workbench.svg")

    def Initialize(self):
        from solidstyle import setup
        setup.initialize(self)

    def Activated(self):
        from solidstyle import setup
        setup.activated()

    def Deactivated(self):
        from solidstyle import setup
        setup.deactivated()

    def ContextMenu(self, recipient):
        from solidstyle import setup
        setup.context_menu(self, recipient)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(SolidStyleWorkbench())


def _give_back_shortcuts():
    # FreeCAD was closed while this workbench had borrowed some keys: return them.
    wb = Gui.activeWorkbench()
    if wb and wb.name() == "SolidStyleWorkbench":
        return
    if App.ParamGet("User parameter:BaseApp/Preferences/Mod/SolidStyle").GetString("ShortcutStash", ""):
        try:
            from solidstyle import shortcuts
            shortcuts.give_back()
        except Exception as e:
            App.Console.PrintWarning("SolidStyle: could not restore shortcuts: %s\n" % e)


try:
    from PySide import QtCore
    QtCore.QTimer.singleShot(3000, _give_back_shortcuts)  # after all workbenches registered commands
except Exception:
    pass
