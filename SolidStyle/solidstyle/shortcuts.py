"""SolidWorks keys (F, S, Ctrl+B ...) clash with a few FreeCAD defaults, and Qt
fires neither action when two share a key. While this workbench is active the
clashing commands lend us their key; it is handed back on deactivation (and at
the next start-up if FreeCAD was closed with this workbench active)."""
import json

import FreeCAD as App
import FreeCADGui as Gui

STASH = "User parameter:BaseApp/Preferences/Mod/SolidStyle"
CUSTOM = "User parameter:BaseApp/Preferences/Shortcut"


def _ours():
    keys = {}
    for name in Gui.listCommands():
        if name.startswith("SS_"):
            k = Gui.Command.get(name).getShortcut()
            if k:
                keys[k] = name
    return keys


def take_over():
    give_back()  # never stack two takeovers
    ours = _ours()
    custom = App.ParamGet(CUSTOM)
    custom_names = set(custom.GetStrings())
    stash = json.loads(App.ParamGet(STASH).GetString("ShortcutStash", "") or "{}")
    for name in Gui.listCommands():
        if name.startswith("SS_"):
            continue
        cmd = Gui.Command.get(name)
        try:
            k = cmd.getShortcut()
        except Exception:
            continue
        if k in ours:
            # remember a user-customised key; None means "FreeCAD default"
            stash[name] = custom.GetString(name) if name in custom_names else None
            cmd.setShortcut("")
    App.ParamGet(STASH).SetString("ShortcutStash", json.dumps(stash))


def give_back():
    p = App.ParamGet(STASH)
    raw = p.GetString("ShortcutStash", "")
    if not raw:
        return
    pending = {}
    for name, value in json.loads(raw).items():
        cmd = Gui.Command.get(name)
        if cmd is None:  # its module isn't loaded yet; try again next time
            pending[name] = value
        elif value is None:
            cmd.resetShortcut()
        else:
            cmd.setShortcut(value)
    if pending:
        p.SetString("ShortcutStash", json.dumps(pending))
    else:
        p.RemString("ShortcutStash")
