"""SolidWorks-like 3D view look & feel, with a backup so it can be undone."""
import json
import os

import FreeCAD as App

BACKUP = os.path.join(App.getUserAppDataDir(), "SolidStyle_backup.json")
VIEW = "User parameter:BaseApp/Preferences/View"
ROOT = "User parameter:BaseApp/Preferences/Mod/SolidStyle"


def rgba(r, g, b, a=255):
    return (r << 24) | (g << 16) | (b << 8) | a


# (group, type, name, value)
SETTINGS = [
    # gradient background: light steel blue at the top fading to white
    (VIEW, "Bool", "Gradient", True),
    (VIEW, "Bool", "RadialGradient", False),
    (VIEW, "Bool", "UseBackgroundColorMid", False),
    (VIEW, "Unsigned", "BackgroundColor2", rgba(184, 202, 224)),
    (VIEW, "Unsigned", "BackgroundColor3", rgba(255, 255, 255)),
    # orange hover highlight, blue selection
    (VIEW, "Unsigned", "HighlightColor", rgba(255, 140, 0)),
    (VIEW, "Unsigned", "SelectionColor", rgba(40, 140, 255)),
    (VIEW, "Bool", "EnablePreselection", True),
    (VIEW, "Bool", "EnableSelection", True),
    # grey parts with black edges
    (VIEW, "Bool", "RandomColor", False),
    (VIEW, "Unsigned", "DefaultShapeColor", rgba(196, 199, 204)),
    (VIEW, "Unsigned", "DefaultShapeLineColor", rgba(0, 0, 0)),
    (VIEW, "Unsigned", "DefaultShapeVertexColor", rgba(0, 0, 0)),
    (VIEW, "Int", "DefaultShapeLineWidth", 1),
    # middle mouse rotates, free (trackball) rotation, zoom about the cursor
    (VIEW, "String", "NavigationStyle", "Gui::BlenderNavigationStyle"),
    (VIEW, "Int", "OrbitStyle", 1),
    (VIEW, "Bool", "ZoomAtCursor", True),
    # sketches: under-defined = blue, fully defined = black, dimensions black
    (VIEW, "Unsigned", "EditedEdgeColor", rgba(0, 0, 230)),
    (VIEW, "Unsigned", "EditedVertexColor", rgba(0, 0, 160)),
    (VIEW, "Unsigned", "SketchEdgeColor", rgba(0, 0, 0)),
    (VIEW, "Unsigned", "SketchVertexColor", rgba(0, 0, 0)),
    (VIEW, "Unsigned", "FullyConstrainedColor", rgba(0, 0, 0)),
    (VIEW, "Unsigned", "FullyConstraintElementColor", rgba(0, 0, 0)),
    (VIEW, "Unsigned", "FullyConstraintConstructionElementColor", rgba(90, 90, 90)),
    (VIEW, "Unsigned", "FullyConstraintInternalAlignmentColor", rgba(90, 90, 90)),
    (VIEW, "Unsigned", "FullyConstraintConstructionPointColor", rgba(40, 40, 40)),
    (VIEW, "Unsigned", "ConstructionColor", rgba(70, 110, 200)),
    (VIEW, "Unsigned", "ConstrainedDimColor", rgba(20, 20, 20)),
    (VIEW, "Unsigned", "ConstrainedIcoColor", rgba(0, 140, 60)),
    (VIEW, "Unsigned", "CreateLineColor", rgba(60, 60, 60)),
    (VIEW, "Unsigned", "CursorTextColor", rgba(0, 0, 200)),
    (VIEW, "Unsigned", "CursorCrosshairColor", rgba(0, 0, 0)),
    (VIEW, "Unsigned", "ExternalColor", rgba(200, 0, 200)),
    # view cube out of the way of the OK/Cancel confirmation corner (bottom right)
    ("User parameter:BaseApp/Preferences/NaviCube", "Int", "CornerNaviCube", 3),
    # stay in this workbench when editing PartDesign features / TechDraw pages
    ("User parameter:BaseApp/Preferences/Mod/PartDesign", "Bool", "SwitchToWB", False),
    ("User parameter:BaseApp/Preferences/Mod/TechDraw/General", "Bool", "SwitchToWB", False),
]


def _existing(grp, typ, name):
    names = getattr(grp, "Get%ss" % typ)()
    if name not in names:
        return None
    return getattr(grp, "Get" + typ)(name)


def apply():
    backup = {}
    if os.path.exists(BACKUP):
        with open(BACKUP) as f:
            backup = json.load(f)  # keep the very first backup
    for group, typ, name, value in SETTINGS:
        grp = App.ParamGet(group)
        key = "%s|%s|%s" % (group, typ, name)
        if key not in backup:
            backup[key] = _existing(grp, typ, name)
        getattr(grp, "Set" + typ)(name, value)
    with open(BACKUP, "w") as f:
        json.dump(backup, f, indent=1)
    App.ParamGet(ROOT).SetBool("LookApplied", True)
    _refresh_views()


def restore():
    if not os.path.exists(BACKUP):
        App.Console.PrintWarning("SolidStyle: no backup found, nothing to restore\n")
        return False
    with open(BACKUP) as f:
        backup = json.load(f)
    for key, value in backup.items():
        group, typ, name = key.split("|")
        grp = App.ParamGet(group)
        if value is None:
            getattr(grp, "Remove" + typ)(name)
        else:
            getattr(grp, "Set" + typ)(name, value)
    os.remove(BACKUP)
    App.ParamGet(ROOT).SetBool("LookApplied", False)
    _refresh_views()
    try:
        _apply_stylesheet_now()
    except Exception:
        pass
    return True


def _refresh_views():
    # Views pick up parameter changes themselves; just nudge a redraw.
    try:
        import FreeCADGui as Gui
        if Gui.ActiveDocument:
            Gui.ActiveDocument.ActiveView.redraw()
    except Exception:
        pass


# ---------------------------------------------------------------- SolidWorks colour scheme (light theme)
MAINWIN = "User parameter:BaseApp/Preferences/MainWindow"
THEMES = "User parameter:BaseApp/Preferences/Themes"
LIGHT_PACK = os.path.join(App.getResourceDir(), "Gui", "PreferencePacks", "FreeCAD Light", "FreeCAD Light.cfg")
SW_ACCENT = [rgba(0, 120, 215), rgba(90, 160, 230), rgba(204, 228, 247)]   # SolidWorks blue, lighter, selection tint
SW_PART_COLOR = rgba(202, 209, 238)                                         # SolidWorks default part colour
NAV_KEYS = ("NavigationStyle", "OrbitStyle", "ZoomAtCursor")                 # leave the user's mouse setup alone


def _import_pack(path):
    """Merge a FreeCAD preference pack .cfg into the user parameters (what Preferences > Theme does)."""
    import xml.etree.ElementTree as ET
    setters = {"FCUInt": ("Unsigned", int), "FCInt": ("Int", int), "FCFloat": ("Float", float),
               "FCText": ("String", lambda v: v or ""), "FCBool": ("Bool", lambda v: v == "1")}

    def walk(node, path):
        for child in node:
            if child.tag == "FCParamGroup":
                walk(child, path + [child.get("Name")])
            elif child.tag in setters:
                typ, conv = setters[child.tag]
                raw = child.text if child.tag == "FCText" else child.get("Value")
                grp = App.ParamGet("User parameter:" + "/".join(path))
                getattr(grp, "Set" + typ)(child.get("Name"), conv(raw))
    root = ET.parse(path).getroot().find("FCParamGroup")      # <Root>
    walk(root, [])


def apply_sw_theme(keep_navigation=True):
    """Light FreeCAD theme + SolidWorks blue accents, gradient background, part and edge colours.
    keep_navigation=False also sets the SolidWorks-like mouse (first run on a new machine)."""
    backup = {}
    if os.path.exists(BACKUP):
        with open(BACKUP) as f:
            backup = json.load(f)
    for group, typ, names in ((MAINWIN, "String", ("StyleSheet", "Theme", "OverlayActiveStyleSheet")),
                              (THEMES, "Unsigned", ("ThemeAccentColor1", "ThemeAccentColor2", "ThemeAccentColor3"))):
        grp = App.ParamGet(group)
        for name in names:
            key = "%s|%s|%s" % (group, typ, name)
            if key not in backup:
                backup[key] = _existing(grp, typ, name)
    with open(BACKUP, "w") as f:
        json.dump(backup, f, indent=1)
    _import_pack(LIGHT_PACK)
    th = App.ParamGet(THEMES)
    for i, c in enumerate(SW_ACCENT, 1):
        th.SetUnsigned("ThemeAccentColor%d" % i, c)
    nav = [(g, t, n, v) for g, t, n, v in SETTINGS if not (keep_navigation and n in NAV_KEYS)]
    nav = [(g, t, n, SW_PART_COLOR if n == "DefaultShapeColor" else v) for g, t, n, v in nav]
    saved = SETTINGS[:]
    SETTINGS[:] = nav
    try:
        apply()                                            # backs up + sets the SolidWorks view colours
    finally:
        SETTINGS[:] = saved
    _apply_stylesheet_now()


def _apply_stylesheet_now():
    """Switch the running GUI to the configured stylesheet (FreeCAD does this itself at the next start)."""
    from PySide import QtGui
    name = App.ParamGet(MAINWIN).GetString("StyleSheet")
    path = os.path.join(App.getResourceDir(), "Gui", "Stylesheets", name)
    if not os.path.exists(path):
        return
    with open(path) as f:
        qss = f.read()
    th = App.ParamGet(THEMES)
    for i in (3, 2, 1):                                    # longest names first is unnecessary, but harmless
        c = th.GetUnsigned("ThemeAccentColor%d" % i)
        qss = qss.replace("@ThemeAccentColor%d" % i, "#%02x%02x%02x" % ((c >> 24) & 255, (c >> 16) & 255, (c >> 8) & 255))
    QtGui.QApplication.instance().setStyleSheet(qss)
