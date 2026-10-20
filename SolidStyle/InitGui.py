# SolidStyle workbench - a SolidWorks-like front end for FreeCAD.
import os
import sys
import FreeCAD as App
import FreeCADGui as Gui


# Note: FreeCAD runs this file with separate globals and locals, so functions here can't see
# names defined at the top level: each one imports what it needs and gets the rest as arguments.

def _here():
    """This workbench's folder (FreeCAD runs InitGui.py without setting __file__)."""
    import inspect
    import os
    import FreeCAD
    for f in (globals().get("__file__"), inspect.currentframe().f_code.co_filename):
        if f and os.path.basename(f) == "InitGui.py" and os.path.isdir(os.path.join(os.path.dirname(f), "solidstyle")):
            return os.path.dirname(os.path.abspath(f))
    return os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "SolidStyle")


def _use_own_copy(here_dir):
    """Import solidstyle from this folder, never from an older copy elsewhere on sys.path
    (e.g. a SolidStyle left in another FreeCAD version's Mod folder). Returns the other copies."""
    import os
    import sys
    here = os.path.normcase(here_dir)
    others = []
    for p in sys.path:
        try:
            d = os.path.normcase(os.path.abspath(p))
        except Exception:
            continue
        if d != here and os.path.isfile(os.path.join(p, "solidstyle", "catalog.py")):
            others.append(os.path.join(p, "solidstyle"))
    while here_dir in sys.path:
        sys.path.remove(here_dir)
    sys.path.insert(0, here_dir)
    old = sys.modules.get("solidstyle")
    if old is not None and os.path.normcase(os.path.dirname(os.path.dirname(os.path.abspath(old.__file__)))) != here:
        for name in [n for n in sys.modules if n == "solidstyle" or n.startswith("solidstyle.")]:
            del sys.modules[name]
    return others


SOLIDSTYLE_DIR = _here()
for _p in _use_own_copy(SOLIDSTYLE_DIR):
    App.Console.PrintWarning("SolidStyle: ignoring an older copy in %s (using %s)\n" % (_p, SOLIDSTYLE_DIR))


class SolidStyleWorkbench(Gui.Workbench):
    MenuText = "SolidWorks Style"
    ToolTip = "SolidWorks-like CommandManager, names, shortcuts and look for Part Design, Sketcher, Assembly and TechDraw"

    def Initialize(self):
        self.UseOwnCopy(self.Dir)
        try:
            from solidstyle import setup
        except Exception as e:
            # say so, instead of quietly showing an empty FreeCAD
            import traceback
            from PySide import QtWidgets
            App.Console.PrintError("SolidStyle could not load:\n%s" % traceback.format_exc())
            QtWidgets.QMessageBox.critical(Gui.getMainWindow(), "SolidWorks Style",
                                           "The SolidWorks Style workbench could not load on FreeCAD %s:\n\n%s: %s"
                                           % (".".join(App.Version()[:3]), type(e).__name__, e))
            raise
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


# (set here: the class body can't see this file's top-level names either)
SolidStyleWorkbench.Icon = os.path.join(SOLIDSTYLE_DIR, "solidstyle", "icons", "Workbench.svg")
SolidStyleWorkbench.Dir = SOLIDSTYLE_DIR
SolidStyleWorkbench.UseOwnCopy = staticmethod(_use_own_copy)
if "SolidStyleWorkbench" in Gui.listWorkbenches():
    # an older copy in another folder registered first: this one replaces it
    Gui.removeWorkbench("SolidStyleWorkbench")
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


def _crash_log():
    # Keep a crash report in <user data>/SolidStyle_crash.log: the Python stack at the crash (faulthandler)
    # plus FreeCAD's own messages and native backtrace, which otherwise go to an unseen terminal.
    import faulthandler
    import time
    path = os.path.join(App.getUserAppDataDir(), "SolidStyle_crash.log")
    try:
        if os.path.exists(path) and os.path.getsize(path) > 2000000:
            os.replace(path, path + ".old")
        f = open(path, "a", buffering=1)
        f.write("\n=== FreeCAD started %s (pid %d) ===\n" % (time.ctime(), os.getpid()))
        for fd in (1, 2):
            if not os.isatty(fd):
                os.dup2(f.fileno(), fd)
        faulthandler.enable(f, all_threads=True)
        globals()["_crash_file"] = f
    except Exception as e:
        App.Console.PrintWarning("SolidStyle: no crash log (%s)\n" % e)


_crash_log()
