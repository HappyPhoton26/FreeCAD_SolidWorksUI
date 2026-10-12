"""VRLiveExport: after every recompute (and when you switch documents) write the visible shapes of the active
FreeCAD document to ~/.vr-model-viewer/model.bin for the VR model viewer (~/fcvr).

File format (little-endian): b"VRMV", u32 version=2, u32 object count, then per object:
f32 diffuse rgba, f32 ambient rgb, f32 specular rgb, f32 shininess (0-1), f32 line rgb, f32 line width (px), f32 padding;
u32 vertex count, u32 triangle count, u32 line vertex count;
f32 xyz * vertices; u32 abc * triangles; f32 xyz * line vertices (pairs = segments).
Vertices are not shared between faces, so normals smoothed per vertex stay sharp at face boundaries.
Coordinates are FreeCAD world millimetres (Z up).
Also writes ~/.vr-model-viewer/view ("x y z w" camera rotation of the active 3D view) while it changes."""
import os
import struct
import time
import FreeCAD as App

OUT = os.path.expanduser("~/.vr-model-viewer/model.bin")
_state = {"timer": None, "doc": None, "observer": None, "poll": None}


def _replace(tmp, dst):
    """os.replace, retried: on Windows it fails while the viewer has the file open for a moment."""
    for i in range(20):
        try:
            os.replace(tmp, dst)
            return
        except PermissionError:
            time.sleep(0.005)
    os.replace(tmp, dst)


def _color(obj):
    """FreeCAD look of obj: (diffuse rgba, ambient rgb, specular rgb, shininess, line rgb, line width)."""
    vo = getattr(obj, "ViewObject", None)
    dif, amb, spe, shin = (0.8, 0.8, 0.8), (0.2, 0.2, 0.2), (0.0, 0.0, 0.0), 0.9
    line, lw, a = (0.1, 0.1, 0.1), 2.0, 1.0
    try:
        a = 1.0 - (getattr(vo, "Transparency", 0) or 0) / 100.0
        dif = tuple(vo.ShapeColor[:3])
        m = vo.ShapeAppearance[0]
        dif, amb, spe, shin = tuple(m.DiffuseColor[:3]), tuple(m.AmbientColor[:3]), tuple(m.SpecularColor[:3]), m.Shininess
    except Exception:
        pass
    try:
        line, lw = tuple(vo.LineColor[:3]), float(vo.LineWidth)
    except Exception:
        pass
    return dif + (a,) + amb + spe + (shin,) + line + (lw, 0.0)


def _gp(obj):
    """Placement of obj in its document's world frame (own Placement chained through parent App::Parts)."""
    p = getattr(obj, "Placement", None)
    p = App.Placement(p) if p is not None else App.Placement()
    par = obj.getParentGeoFeatureGroup() if hasattr(obj, "getParentGeoFeatureGroup") else None
    while par is not None:
        p = par.Placement.multiply(p)
        par = par.getParentGeoFeatureGroup()
    return p


def _visible(obj):
    vo = getattr(obj, "ViewObject", None)
    return vo is None or vo.Visibility


def _leaves(obj, M, out, depth=0):
    """Collect (shape-in-world, colour) for visible geometry under obj; M maps obj's document frame to world."""
    if depth > 12 or not _visible(obj):
        return
    if obj.TypeId == "App::Link":
        tgt = obj.getLinkedObject(False)
        if tgt is None or tgt is obj:
            return
        Ml = M.multiply(_gp(obj))                     # link frame in world
        sub = Ml.multiply(_gp(tgt).inverse())        # target's document frame in world
        if hasattr(tgt, "Group") and tgt.TypeId != "PartDesign::Body":
            for c in tgt.Group:
                _leaves(c, sub, out, depth + 1)
        else:
            _leaf(tgt, sub, out, color_from=obj if _has_override(obj) else tgt)
        return
    if hasattr(obj, "Group") and obj.TypeId != "PartDesign::Body":
        for c in obj.Group:
            _leaves(c, M, out, depth + 1)
        return
    _leaf(obj, M, out)


def _has_override(link):
    vo = getattr(link, "ViewObject", None)
    return bool(vo is not None and getattr(vo, "OverrideMaterial", False))


def _leaf(obj, M, out, color_from=None):
    shp = getattr(obj, "Shape", None)
    if shp is None or shp.isNull() or not shp.Faces:
        return
    s = shp.copy()
    s.Placement = M.multiply(_gp(obj))
    out.append((s, _color(color_from or obj)))


def export(doc=None):
    import Part  # noqa: F401  (makes sure Shape tessellation is available)
    doc = doc or App.ActiveDocument
    if doc is None:
        return
    t0 = time.time()
    leaves = []
    for o in doc.RootObjects:
        try:
            _leaves(o, App.Placement(), leaves)
        except Exception as e:
            App.Console.PrintWarning("VRLiveExport: skipped %s (%s)\n" % (o.Name, e))
    if not leaves:
        return
    bb = leaves[0][0].BoundBox
    for s, _ in leaves[1:]:
        bb.add(s.BoundBox)
    tol = max(0.01, bb.DiagonalLength * 0.0008)
    chunks = []
    for s, col in leaves:
        try:
            s.tessellate(tol)                         # mesh all faces consistently first
        except Exception:
            continue
        flat, idx = [], []
        for face in s.Faces:
            pts, tris = face.tessellate(tol)
            base = len(flat) // 3
            flat += [c for p in pts for c in (p.x, p.y, p.z)]
            idx += [base + i for t in tris for i in t]
        lines = []
        for e in s.Edges:
            try:
                pts = e.discretize(Deflection=tol)
            except Exception:
                continue
            for p0, p1 in zip(pts, pts[1:]):
                lines += (p0.x, p0.y, p0.z, p1.x, p1.y, p1.z)
        if not idx and not lines:
            continue
        chunks.append(struct.pack("<16f3I", *col, len(flat) // 3, len(idx) // 3, len(lines) // 3)
                      + struct.pack("<%df" % len(flat), *flat) + struct.pack("<%dI" % len(idx), *idx)
                      + struct.pack("<%df" % len(lines), *lines))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "wb") as f:
        f.write(struct.pack("<4sII", b"VRMV", 2, len(chunks)))
        for c in chunks:
            f.write(c)
    _replace(tmp, OUT)
    App.Console.PrintLog("VRLiveExport: %s -> %d objects in %.2f s\n" % (doc.Name, len(chunks), time.time() - t0))


def _schedule(doc=None):
    from PySide import QtCore
    t = _state["timer"]
    if t is None:
        t = QtCore.QTimer(); t.setSingleShot(True)
        t.timeout.connect(lambda: _safe_export())
        _state["timer"] = t
    t.start(400)                                       # coalesce bursts of recomputes


def _safe_export():
    try:
        export()
    except Exception as e:
        App.Console.PrintWarning("VRLiveExport failed: %s\n" % e)


class _Observer:
    def slotRecomputedDocument(self, doc):
        if doc is App.ActiveDocument:
            _schedule()

    def slotChangedObject(self, obj, prop):           # show/hide in the tree also updates the VR model
        if prop == "Visibility" and getattr(obj, "Document", None) is App.ActiveDocument:
            _schedule()


# Hotkeys for the VR viewer (~/fcvr/fcvr). They work anywhere in FreeCAD and write "<seq> <command>" to CMD.
CMD = os.path.join(os.path.dirname(OUT), "cmd")
HOTKEYS = [
    ("Ctrl+Alt+1", "real", "VR model: real size (1:1)"),
    ("Ctrl+Alt+2", "big", "VR model: blown up (about 1.2 m)"),
    ("Ctrl+Alt+3", "fit", "VR model: desk size (about 35 cm)"),
    ("Ctrl+Alt+=", "bigger", "VR model: 1.5x bigger"),
    ("Ctrl+Alt+-", "smaller", "VR model: 1.5x smaller"),
    ("Ctrl+Alt+0", "recenter", "VR model: bring it in front of me"),
    ("Ctrl+Alt+4", "follow", "VR model: turn with the FreeCAD view on/off"),
    ("Ctrl+Alt+S", "ask_scale", "VR model: type a scale (5 = 5x real size)"),
    ("Ctrl+Alt+V", "toggle_viewer", "VR model: show/hide the VR viewer"),
    # move 1 cm per press (hold to keep going), relative to where you face
    ("Ctrl+Alt+Left", "move -0.01 0 0", "VR model: move left"),
    ("Ctrl+Alt+Right", "move 0.01 0 0", "VR model: move right"),
    ("Ctrl+Alt+Up", "move 0 0.01 0", "VR model: move up"),
    ("Ctrl+Alt+Down", "move 0 -0.01 0", "VR model: move down"),
    ("Ctrl+Alt+PgUp", "move 0 0 -0.01", "VR model: move away"),
    ("Ctrl+Alt+PgDown", "move 0 0 0.01", "VR model: move closer"),
    # rotate 5 degrees per press (stops turning with the FreeCAD view; Ctrl+Alt+4 turns that back on)
    ("Ctrl+Shift+Alt+Left", "rotate 0 5 0", "VR model: turn left"),
    ("Ctrl+Shift+Alt+Right", "rotate 0 -5 0", "VR model: turn right"),
    ("Ctrl+Shift+Alt+Up", "rotate -5 0 0", "VR model: tilt away"),
    ("Ctrl+Shift+Alt+Down", "rotate 5 0 0", "VR model: tilt towards you"),
    ("Ctrl+Shift+Alt+PgUp", "rotate 0 0 5", "VR model: roll left"),
    ("Ctrl+Shift+Alt+PgDown", "rotate 0 0 -5", "VR model: roll right"),
    ("Ctrl+Alt+U", "upright", "VR model: stand it upright again"),
]


def ask_scale():
    import FreeCADGui as Gui
    from PySide import QtGui
    v, ok = QtGui.QInputDialog.getDouble(Gui.getMainWindow(), "VR model scale",
                                         "Scale (1 = real size, 5 = 5x bigger):", _state.get("scale", 1.0), 0.01, 1000, 2)
    if ok:
        _state["scale"] = v
        send("scale %g" % v)


WINDOWS = os.name == "nt"
# Windows: the installer puts fcvr.exe, openvr_api.dll and the SteamVR input files here
WIN_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "fcvr")
_NO_WINDOW = 0x08000000   # CREATE_NO_WINDOW


def _viewer_cmd(arg):
    cmd = [os.path.expanduser("~/fcvr/run.sh"), arg]
    if os.path.exists("/.flatpak-info"):
        cmd = ["flatpak-spawn", "--host"] + cmd
    return cmd


def _win_running():
    import subprocess
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq fcvr.exe", "/NH"], capture_output=True, text=True,
                         creationflags=_NO_WINDOW, timeout=10).stdout
    return "fcvr.exe" in out.lower()


def _win_stop():
    import subprocess
    subprocess.run(["taskkill", "/IM", "fcvr.exe", "/F"], capture_output=True, creationflags=_NO_WINDOW, timeout=10)


def _win_toggle():
    """Start/stop fcvr.exe (SteamVR on Windows, e.g. a Steam Frame over Steam Link)."""
    import subprocess
    if _win_running():
        _win_stop()
        return "VR viewer stopped"
    exe = os.path.join(WIN_DIR, "fcvr.exe")
    if not os.path.exists(exe):
        return "VR viewer not installed (run install.bat from FreeCAD_SolidWorksUI)"
    log = open(os.path.join(WIN_DIR, "fcvr.log"), "w")
    subprocess.Popen([exe, "--parent-pid", str(os.getpid())], cwd=WIN_DIR, stdout=log, stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW)
    return "VR viewer started (log: %s)" % os.path.join(WIN_DIR, "fcvr.log")


def stop_viewer():
    """FreeCAD is quitting: close the VR model too (the viewer also notices on its own if FreeCAD crashes)."""
    import subprocess
    try:
        if WINDOWS:
            _win_stop()
        else:
            subprocess.run(_viewer_cmd("stop"), capture_output=True, timeout=5)
    except Exception:
        pass


def toggle_viewer():
    """Start/stop the VR viewer: ~/fcvr/fcvr on Linux (through flatpak-spawn for the flatpak), fcvr.exe on Windows."""
    import subprocess
    try:
        if WINDOWS:
            out = _win_toggle()
        else:
            out = subprocess.run(_viewer_cmd("toggle"), capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception as e:
        out = "could not start the VR viewer: %s" % e
    App.Console.PrintMessage("VR: %s\n" % out)
    if "started" in out:
        show_help()
    try:
        import FreeCADGui as Gui
        Gui.getMainWindow().statusBar().showMessage(out, 4000)
    except Exception:
        pass


HELP_HTML = """<h3>VR model hotkeys</h3>
<table cellspacing=4>
<tr><td><b>Ctrl+Alt+V</b></td><td>show / hide the model in VR (same as the VR button)</td></tr>
<tr><td colspan=2><br><b>Size</b></td></tr>
<tr><td><b>Ctrl+Alt+S</b></td><td>type a scale (1 = real size, 5 = 5x bigger)</td></tr>
<tr><td><b>Ctrl+Alt+1</b></td><td>real size (1:1)</td></tr>
<tr><td><b>Ctrl+Alt+2</b> / <b>3</b></td><td>big (about 1.2 m) / desk size (about 35 cm)</td></tr>
<tr><td><b>Ctrl+Alt+=</b> / <b>-</b></td><td>1.5x bigger / smaller</td></tr>
<tr><td colspan=2><br><b>Move</b> (1 cm per press, hold to keep going)</td></tr>
<tr><td><b>Ctrl+Alt+Arrows</b></td><td>left / right / up / down</td></tr>
<tr><td><b>Ctrl+Alt+PgUp</b> / <b>PgDn</b></td><td>away / closer</td></tr>
<tr><td><b>Ctrl+Alt+0</b></td><td>bring it back in front of you</td></tr>
<tr><td colspan=2><br><b>Rotate</b> (5 degrees per press)</td></tr>
<tr><td><b>Ctrl+Shift+Alt+Left</b> / <b>Right</b></td><td>turn</td></tr>
<tr><td><b>Ctrl+Shift+Alt+Up</b> / <b>Down</b></td><td>tilt</td></tr>
<tr><td><b>Ctrl+Shift+Alt+PgUp</b> / <b>PgDn</b></td><td>roll</td></tr>
<tr><td><b>Ctrl+Alt+U</b></td><td>stand it upright</td></tr>
<tr><td><b>Ctrl+Alt+4</b></td><td>turn with the FreeCAD view on / off (on at start)</td></tr>
</table>"""


def show_help():
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui
    dlg = _state.get("help")
    if dlg is None:
        dlg = QtGui.QDialog(Gui.getMainWindow())
        dlg.setWindowTitle("VR model hotkeys")
        dlg.setWindowFlags(dlg.windowFlags() | QtCore.Qt.Tool)
        lay = QtGui.QVBoxLayout(dlg)
        lab = QtGui.QLabel(HELP_HTML); lab.setTextFormat(QtCore.Qt.RichText)
        lay.addWidget(lab)
        btn = QtGui.QPushButton("Close"); btn.clicked.connect(dlg.hide)
        lay.addWidget(btn)
        _state["help"] = dlg
    dlg.show(); dlg.raise_()


ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")


class _ToggleCmd:
    def GetResources(self):
        return {"Pixmap": os.path.join(ICONS, "VR_Toggle.svg"), "MenuText": "VR view",
                "ToolTip": "Show/hide this model floating in VR (Ctrl+Alt+V)"}

    def Activated(self):
        toggle_viewer()

    def IsActive(self):
        return True


class _HelpCmd:
    def GetResources(self):
        return {"Pixmap": os.path.join(ICONS, "VR_Help.svg"), "MenuText": "VR hotkeys",
                "ToolTip": "List the VR model hotkeys"}

    def Activated(self):
        show_help()

    def IsActive(self):
        return True


def register_commands():
    import FreeCADGui as Gui
    if "VR_Toggle" not in Gui.listCommands():
        Gui.addCommand("VR_Toggle", _ToggleCmd())
        Gui.addCommand("VR_Help", _HelpCmd())


def remove_global_toolbar():
    """Drop the old floating 'VR' Global toolbar; the buttons now live in the SolidWorks Style ribbon."""
    tbs = App.ParamGet("User parameter:BaseApp/Workbench/Global/Toolbar")
    for g in tbs.GetGroups():
        if tbs.GetGroup(g).GetString("Name") == "VR":
            tbs.RemGroup(g)
    try:
        import FreeCADGui as Gui
        from PySide import QtWidgets
        for tb in Gui.getMainWindow().findChildren(QtWidgets.QToolBar):
            if tb.windowTitle() == "VR":
                tb.hide()
                tb.deleteLater()
    except Exception:
        pass


def send(cmd):
    if cmd == "ask_scale":
        return ask_scale()
    if cmd == "toggle_viewer":
        return toggle_viewer()
    # append, so fast key repeats queue up instead of overwriting each other
    os.makedirs(os.path.dirname(CMD), exist_ok=True)
    try:
        if os.path.getsize(CMD) > 65536:
            open(CMD, "w").close()
    except OSError:
        pass
    with open(CMD, "a") as f:
        f.write("%d %s\n" % (time.time() * 1000, cmd))
    if not cmd.startswith(("move", "rotate")):
        App.Console.PrintMessage("VR: %s\n" % cmd)


VIEW = os.path.join(os.path.dirname(OUT), "view")


def _write_view():
    """Publish the active 3D view's camera rotation so the VR model can turn with it."""
    try:
        import FreeCADGui as Gui
        q = Gui.ActiveDocument.ActiveView.getCameraOrientation().Q
    except Exception:
        return
    txt = "%.5f %.5f %.5f %.5f\n" % tuple(q)
    if txt == _state.get("view_txt"):
        return
    _state["view_txt"] = txt
    tmp = VIEW + ".tmp"
    with open(tmp, "w") as f:
        f.write(txt)
    try:
        _replace(tmp, VIEW)
    except OSError:
        _state["view_txt"] = None   # try again next tick


def install_hotkeys():
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui
    mw = Gui.getMainWindow()
    for old in _state.get("shortcuts", []):
        old.setEnabled(False); old.setParent(None)
    made = []
    for key, cmd, _ in HOTKEYS:
        sc = QtGui.QShortcut(QtGui.QKeySequence(key), mw)
        sc.setContext(QtCore.Qt.ApplicationShortcut)
        sc.activated.connect(lambda c=cmd: send(c))
        made.append(sc)
    _state["shortcuts"] = made
    if _state.get("view_timer") is None:
        vt = QtCore.QTimer(); vt.setInterval(33)
        vt.timeout.connect(_write_view); vt.start()
        _state["view_timer"] = vt


def start():
    try:
        from PySide import QtGui
        if not _state.get("quit_hooked"):
            QtGui.QApplication.instance().aboutToQuit.connect(stop_viewer)
            _state["quit_hooked"] = True
    except Exception as e:
        App.Console.PrintWarning("VRLiveExport: no close hook (%s)\n" % e)
    try:
        register_commands()
        remove_global_toolbar()
        install_hotkeys()
    except Exception as e:
        App.Console.PrintWarning("VRLiveExport hotkeys not installed: %s\n" % e)
    if _state["observer"] is not None:
        return
    from PySide import QtCore
    _state["observer"] = _Observer()
    App.addDocumentObserver(_state["observer"])
    try:
        import FreeCADGui as Gui
        Gui.ActiveDocument and None
    except Exception:
        pass
    poll = QtCore.QTimer(); poll.setInterval(1000)    # notice switching to another document
    def check():
        d = App.ActiveDocument
        name = d.Name if d else None
        if name != _state["doc"]:
            _state["doc"] = name
            _schedule()
    poll.timeout.connect(check); poll.start()
    _state["poll"] = poll
    App.Console.PrintMessage("VRLiveExport: exporting the active document to %s\n" % OUT)
