"""SolidWorks-style widgets: CommandManager ribbon, heads-up view toolbar,
confirmation corner, 'S' shortcut bar and the Mass Properties dialog."""
import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
try:
    import shiboken6 as shiboken
except ImportError:
    import shiboken2 as shiboken

from solidstyle import catalog, commands

BIG = 32
SMALL = 16

_manager = None          # CommandManager instance


def mw():
    return Gui.getMainWindow()


def fc_action(cmd):
    """The QAction FreeCAD uses for `cmd`, or None if the command doesn't exist."""
    c = Gui.Command.get(cmd)
    if c is None:
        return None
    acts = c.getAction()
    if not acts:
        return None
    return acts[0]


def run(cmd):
    try:
        Gui.runCommand(cmd, 0)
    except Exception as e:
        App.Console.PrintError("SolidStyle: %s failed: %s\n" % (cmd, e))


def exists(cmd):
    return cmd in _known()


_known_cache = None


def _known():
    global _known_cache
    if _known_cache is None:
        _known_cache = set(Gui.listCommands())
    return _known_cache


def refresh_known():
    global _known_cache
    _known_cache = None


SW_ICONS = os.path.join(os.path.dirname(__file__), "icons", "sw")


def cmd_icon(cmd):
    """SolidStyle's SolidWorks-flavoured icon when there is one, else FreeCAD's."""
    p = os.path.join(SW_ICONS, cmd + ".svg")
    if os.path.exists(p):
        return QtGui.QIcon(p)
    a = fc_action(cmd)
    return a.icon() if a else QtGui.QIcon()


def cmd_tip(cmd, label):
    a = fc_action(cmd)
    tip = label.replace("\n", " ")
    if a:
        fc = a.text().replace("&", "")
        if fc and fc.lower() != tip.lower():
            tip += "  (FreeCAD: %s)" % fc
        if a.shortcut().toString():
            tip += "   [%s]" % a.shortcut().toString()
    return tip


# ======================================================================
# CommandManager
# ======================================================================

# Light, SolidWorks-like ribbon regardless of the FreeCAD theme (the icons are drawn for it).
STYLE = """
QWidget#SS_CommandManager, QWidget#SS_CommandManager QWidget { background: #eef0f3; color: #1e1e1e; }
QWidget#SS_CommandManager QToolButton { color: #1e1e1e; }
QWidget#SS_CommandManager QToolButton:disabled { color: #9a9a9a; }
QMenu { background: #f7f8fa; color: #1e1e1e; border: 1px solid #aab3bf; }
QMenu::item:selected { background: #cfe2fb; color: #000; }
QMenu::item:disabled { color: #9a9a9a; }
QTabWidget#SS_Tabs::pane { border: none; border-top: 1px solid #b8c0cb; top: -1px; }
QTabWidget#SS_Tabs > QTabBar { background: #e2e6eb; }
QTabWidget#SS_Tabs > QTabBar::tab {
    padding: 3px 14px; margin-right: 1px; border: 1px solid transparent;
    border-top: none; color: #1e1e1e; background: transparent; }
QTabWidget#SS_Tabs > QTabBar::tab:selected {
    border-color: #b8c0cb; background: #ffffff; color: #d0262d; font-weight: bold; }
QTabWidget#SS_Tabs > QTabBar::tab:hover:!selected { color: #d0262d; }
QToolButton[ssbig="true"] { padding: 2px 4px; border: 1px solid transparent; border-radius: 3px; }
QToolButton[sssmall="true"] { padding: 1px 3px; border: 1px solid transparent; border-radius: 3px; text-align: left; }
QToolButton[ssbig="true"]:hover, QToolButton[sssmall="true"]:hover {
    border-color: #6aa4e8; background: rgba(106, 164, 232, 60); }
QToolButton[ssbig="true"]:pressed, QToolButton[sssmall="true"]:pressed { background: rgba(106, 164, 232, 120); }
QFrame#SS_Sep { color: #b8c0cb; background: #b8c0cb; }
"""


class CmdButton(QtWidgets.QToolButton):
    """Button bound to a FreeCAD command, showing the SolidWorks name."""

    def __init__(self, cmd, label, big=True, menu_items=None, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.label = label
        self.setProperty("ssbig" if big else "sssmall", True)
        self.setAutoRaise(True)
        sz = BIG if big else SMALL
        self.setIconSize(QtCore.QSize(sz, sz))
        self.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon if big
                                else QtCore.Qt.ToolButtonTextBesideIcon)
        self.setText(label if big else label.replace("\n", " "))
        self.setIcon(cmd_icon(cmd))
        self.setToolTip(cmd_tip(cmd, label))
        if big:
            self.setMinimumWidth(58)
            self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        self.clicked.connect(lambda: run(self.cmd))
        if menu_items:
            menu = QtWidgets.QMenu(self)
            for c, text in menu_items:
                act = menu.addAction(cmd_icon(c), text)
                act.setToolTip(cmd_tip(c, text))
                act.setData(c)
                act.triggered.connect(lambda checked=False, c=c: run(c))
            menu.aboutToShow.connect(lambda m=menu: _sync_menu(m))
            self.setMenu(menu)
            self.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)

    def sync(self):
        a = fc_action(self.cmd)
        self.setEnabled(bool(a and a.isEnabled()) or self.menu() is not None)


def _sync_menu(menu):
    for act in menu.actions():
        a = fc_action(act.data())
        act.setEnabled(bool(a and a.isEnabled()))


def _sep():
    f = QtWidgets.QFrame()
    f.setObjectName("SS_Sep")
    f.setFrameShape(QtWidgets.QFrame.VLine)
    f.setFrameShadow(QtWidgets.QFrame.Plain)
    return f


class CommandManager(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SS_CommandManager")
        self.setStyleSheet(STYLE)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 0)
        self.tabs = QtWidgets.QTabWidget(self)
        self.tabs.setObjectName("SS_Tabs")
        self.tabs.setTabPosition(QtWidgets.QTabWidget.South)  # SolidWorks has tabs under the buttons
        self.tabs.setDocumentMode(True)
        lay.addWidget(self.tabs)
        self.buttons = {}
        self.build()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.sync)
        self.timer.start(400)

    def build(self):
        self.tabs.clear()
        self.buttons = {}
        for name, items in catalog.TABS:
            page = QtWidgets.QWidget()
            h = QtWidgets.QHBoxLayout(page)
            h.setContentsMargins(4, 2, 4, 2)
            h.setSpacing(1)
            btns = []
            last_sep = True
            for item in items:
                if item == "|":
                    if not last_sep:
                        h.addSpacing(3)
                        h.addWidget(_sep())
                        h.addSpacing(3)
                        last_sep = True
                    continue
                kind = item[0]
                if kind == "big" and exists(item[1]):
                    b = CmdButton(item[1], item[2])
                    h.addWidget(b)
                    btns.append(b)
                    last_sep = False
                elif kind == "drop":
                    entries = [(c, t) for c, t in item[2] if exists(c)]
                    if entries:
                        b = CmdButton(entries[0][0], item[1], menu_items=entries)
                        h.addWidget(b)
                        btns.append(b)
                        last_sep = False
                elif kind == "stack":
                    entries = [(c, t) for c, t in item[1] if exists(c)]
                    if entries:
                        col = QtWidgets.QVBoxLayout()
                        col.setSpacing(0)
                        for c, t in entries:
                            b = CmdButton(c, t, big=False)
                            col.addWidget(b)
                            btns.append(b)
                        col.addStretch(1)
                        h.addLayout(col)
                        last_sep = False
            h.addStretch(1)
            self.tabs.addTab(page, name)
            self.buttons[name] = btns

    def sync(self):
        if not self.isVisible():
            return
        name = self.tabs.tabText(self.tabs.currentIndex())
        for b in self.buttons.get(name, []):
            b.sync()

    def select(self, name):
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == name:
                self.tabs.setCurrentIndex(i)
                return


class CommandManagerBar(QtWidgets.QToolBar):
    """Hosts the CommandManager as a full-width toolbar under the menu bar."""

    def __init__(self):
        super().__init__("CommandManager")
        self.setObjectName("SS_CommandManagerBar")
        self.setMovable(False)
        self.setFloatable(False)
        self.manager = CommandManager(self)
        self.addWidget(self.manager)


def show_command_manager(show=True):
    global _manager
    if _manager is None:
        if not show:
            return
        _manager = CommandManagerBar()
        main = mw()
        main.addToolBarBreak(QtCore.Qt.TopToolBarArea)
        main.addToolBar(QtCore.Qt.TopToolBarArea, _manager)
    _manager.setVisible(show)


def select_tab(name):
    if _manager is not None:
        _manager.manager.select(name)


def current_tab():
    if _manager is None:
        return None
    t = _manager.manager.tabs
    return t.tabText(t.currentIndex())


def rebuild_command_manager():
    refresh_known()
    if _manager is not None:
        _manager.manager.build()


# ======================================================================
# Heads-up view toolbar + confirmation corner (live inside each 3D view)
# ======================================================================

HUD_STYLE = """
QToolBar { background: rgba(255,255,255,170); border: 1px solid rgba(80,100,130,90);
           border-radius: 6px; padding: 1px; spacing: 1px; }
QToolButton { border: 1px solid transparent; border-radius: 4px; padding: 2px; }
QToolButton:hover { border-color: #6aa4e8; background: rgba(106,164,232,70); }
QMenu { background: #f7f8fa; color: #1e1e1e; border: 1px solid #aab3bf; }
QMenu::item:selected { background: #cfe2fb; color: #000; }
"""


def _hud_button(bar, cmd, tip=None):
    if not exists(cmd):
        return None
    act = bar.addAction(cmd_icon(cmd), tip or cmd)
    act.setToolTip(cmd_tip(cmd, tip or cmd))
    act.triggered.connect(lambda checked=False, c=cmd: run(c))
    return act


def _hud_menu(bar, icon, tip, entries):
    btn = QtWidgets.QToolButton(bar)
    btn.setIcon(icon)
    btn.setToolTip(tip)
    btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
    menu = QtWidgets.QMenu(btn)
    for cmd, text in entries:
        if exists(cmd):
            a = menu.addAction(cmd_icon(cmd), text)
            a.triggered.connect(lambda checked=False, c=cmd: run(c))
    btn.setMenu(menu)
    bar.addWidget(btn)
    return btn


class HeadsUp(QtWidgets.QToolBar):
    def __init__(self, view):
        super().__init__(view)
        self.setObjectName("SS_HeadsUp")
        self.setStyleSheet(HUD_STYLE)
        self.setIconSize(QtCore.QSize(20, 20))
        _hud_button(self, "SS_ZoomFit", "Zoom to Fit")
        _hud_button(self, "Std_ViewBoxZoom", "Zoom to Area")
        _hud_button(self, "Std_ViewFitSelection", "Zoom to Selection")
        _hud_button(self, "Part_SectionCut", "Section View")
        self.addSeparator()
        _hud_menu(self, QtGui.QIcon(commands.icon("ViewOrientation")), "View Orientation  (Ctrl+1 ... Ctrl+8)",
                  [(n, "%s   %s" % (m, a)) for n, m, a, _s, _p in commands.VIEWS] +
                  [("SS_NormalTo", "Normal To   Ctrl+8")])
        _hud_menu(self, cmd_icon("Std_DrawStyleShaded"), "Display Style",
                  [("Std_DrawStyleAsIs", "Shaded With Edges"),
                   ("Std_DrawStyleShaded", "Shaded"),
                   ("Std_DrawStyleHiddenLine", "Hidden Lines Removed"),
                   ("Std_DrawStyleNoShading", "Hidden Lines Visible"),
                   ("Std_DrawStyleWireframe", "Wireframe")])
        _hud_menu(self, cmd_icon("Std_ToggleVisibility"), "Hide / Show Items",
                  [("Std_ToggleVisibility", "Hide / Show Selection   (Space)"),
                   ("Std_ShowSelection", "Show Selection"),
                   ("Std_HideSelection", "Hide Selection"),
                   ("Std_ShowObjects", "Show All"),
                   ("Std_ToggleTransparency", "Toggle Transparency")])
        _hud_button(self, "Std_SetAppearance", "Edit Appearance")
        self.addSeparator()
        _hud_button(self, "Std_Measure", "Measure")
        _hud_button(self, "SS_NormalTo", "Normal To")
        self.adjustSize()

    def place(self):
        p = self.parentWidget()
        self.adjustSize()
        self.move(max(0, (p.width() - self.width()) // 2), 6)
        self.raise_()


class ConfirmCorner(QtWidgets.QWidget):
    """Green tick / red cross in the top-right corner while a command or sketch is open."""

    def __init__(self, view):
        super().__init__(view)
        self.setObjectName("SS_ConfirmCorner")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.ok = QtWidgets.QToolButton(self)
        self.cancel = QtWidgets.QToolButton(self)
        for b, ic in ((self.ok, "Accept"), (self.cancel, "Cancel")):
            b.setIcon(QtGui.QIcon(commands.icon(ic)))
            b.setIconSize(QtCore.QSize(30, 30))
            b.setAutoRaise(True)
            b.setStyleSheet("QToolButton{background:rgba(255,255,255,150);border:1px solid rgba(80,100,130,90);"
                            "border-radius:6px;padding:3px}QToolButton:hover{background:rgba(106,164,232,90)}")
            lay.addWidget(b)
        self.ok.clicked.connect(self.accept)
        self.cancel.clicked.connect(self.reject)
        self.adjustSize()
        self.hide()

    def place(self):
        p = self.parentWidget()
        self.adjustSize()
        self.move(p.width() - self.width() - 12, 8)
        self.raise_()

    def update_state(self):
        sketch = commands.editing_sketch()
        dialog = Gui.Control.activeDialog()
        if sketch is not None:
            self.ok.setIcon(QtGui.QIcon(commands.icon("ExitSketch")))
            self.ok.setToolTip("Exit Sketch")
        else:
            self.ok.setIcon(QtGui.QIcon(commands.icon("Accept")))
            self.ok.setToolTip("OK")
        self.cancel.setVisible(sketch is None)
        want = bool(dialog or sketch is not None)
        if want != self.isVisible():
            self.setVisible(want)
        if want:
            self.place()

    def accept(self):
        if not _task_button("ok") and commands.editing_sketch() is not None:
            run("Sketcher_LeaveSketch")

    def reject(self):
        if not _task_button("cancel"):
            Gui.Control.closeDialog()


def _task_button(which):
    """Click OK/Cancel on the open task panel. Returns True when a button was clicked."""
    roles = {
        "ok": (QtWidgets.QDialogButtonBox.Ok, QtWidgets.QDialogButtonBox.Apply,
               QtWidgets.QDialogButtonBox.Close, QtWidgets.QDialogButtonBox.Yes),
        "cancel": (QtWidgets.QDialogButtonBox.Cancel, QtWidgets.QDialogButtonBox.Abort,
                   QtWidgets.QDialogButtonBox.No),
    }[which]
    for box in mw().findChildren(QtWidgets.QDialogButtonBox):
        if not box.isVisible() or not _inside_taskview(box):
            continue
        for role in roles:
            b = box.button(role)
            if b is not None and b.isVisible() and b.isEnabled():
                b.click()
                return True
    return False


def _inside_taskview(w):
    while w is not None:
        if "TaskView" in w.metaObject().className():
            return True
        w = w.parentWidget()
    return False


def _overlays(view):
    hud = view.findChild(QtWidgets.QToolBar, "SS_HeadsUp")
    corner = view.findChild(QtWidgets.QWidget, "SS_ConfirmCorner")
    return hud, corner


class _ResizeFilter(QtCore.QObject):
    def eventFilter(self, obj, ev):
        if ev.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show):
            for w in _overlays(obj):
                if w is not None and w.isVisible():
                    w.place()
        return False


_filter = None
_overlay_refs = []   # keep Python wrappers of our overlay subclasses alive


def _views():
    area = mw().findChild(QtWidgets.QMdiArea)
    if area is None:
        return []
    out = []
    for sub in area.subWindowList():
        w = sub.widget()
        if w is not None and shiboken.isValid(w) and w.metaObject().className() == "Gui::View3DInventor":
            out.append(w)
    return out


def update_views(active):
    """Attach heads-up/confirm widgets to new 3D views and show/hide them."""
    global _filter
    if _filter is None:
        _filter = _ResizeFilter()
    for v in _views():
        try:
            hud, corner = _overlays(v)
            if hud is None:
                hud, corner = HeadsUp(v), ConfirmCorner(v)
                _overlay_refs.append((hud, corner))
                v.installEventFilter(_filter)
                hud.place()
            if hud.isVisible() != active:
                hud.setVisible(active)
                if active:
                    hud.place()
            if active:
                corner.update_state()
            else:
                corner.hide()
        except RuntimeError:
            pass  # view is being destroyed
    # forget overlays whose view has gone away
    alive = []
    for pair in _overlay_refs:
        try:
            pair[0].objectName()
            alive.append(pair)
        except RuntimeError:
            pass
    _overlay_refs[:] = alive


# ======================================================================
# 'S' shortcut bar
# ======================================================================

class ShortcutPopup(QtWidgets.QFrame):
    def __init__(self, cmds):
        super().__init__(mw(), QtCore.Qt.Popup)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setStyleSheet("QFrame{background:#eef0f3;border:1px solid #8d99a8;border-radius:4px}"
                           "QToolButton{border:1px solid transparent;border-radius:3px;padding:2px}"
                           "QToolButton:hover{border-color:#6aa4e8;background:rgba(106,164,232,70)}")
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(2)
        cols = 7
        i = 0
        for c in cmds:
            a = fc_action(c)
            if a is None or not a.isEnabled():
                continue
            b = QtWidgets.QToolButton(self)
            b.setAutoRaise(True)
            b.setIcon(cmd_icon(c))
            b.setIconSize(QtCore.QSize(24, 24))
            b.setToolTip(a.text().replace("&", ""))
            b.clicked.connect(lambda checked=False, c=c: (self.close(), run(c)))
            grid.addWidget(b, i // cols, i % cols)
            i += 1
        self.count = i


def show_shortcut_bar():
    cmds = catalog.SHORTCUT_BAR_SKETCH if commands.editing_sketch() else catalog.SHORTCUT_BAR_PART
    pop = ShortcutPopup(cmds)
    if not pop.count:
        return
    pop.adjustSize()
    pos = QtGui.QCursor.pos() - QtCore.QPoint(pop.width() // 2, pop.height() // 2)
    pop.move(pos)
    pop.show()


# ======================================================================
# Mass Properties
# ======================================================================

class MassPropertiesDialog(QtWidgets.QDialog):
    def __init__(self, objs):
        super().__init__(mw())
        self.setWindowTitle("Mass Properties")
        self.objs = objs
        lay = QtWidgets.QVBoxLayout(self)
        names = ", ".join(o.Label for o in objs) or "(nothing - select a body or solid)"
        lay.addWidget(QtWidgets.QLabel("<b>Selected items:</b> " + names))
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Density:"))
        self.density = QtWidgets.QDoubleSpinBox()
        self.density.setDecimals(4)
        self.density.setRange(0.0001, 100.0)
        self.density.setValue(App.ParamGet("User parameter:BaseApp/Preferences/Mod/SolidStyle")
                              .GetFloat("Density", 1.0))
        self.density.setSuffix(" g/cm³")
        self.density.valueChanged.connect(self.update)
        row.addWidget(self.density)
        self.material = QtWidgets.QComboBox()
        for name, d in [("Custom", None), ("Water", 1.0), ("ABS", 1.04), ("PLA", 1.24),
                        ("Nylon 6/6", 1.14), ("Aluminum 6061", 2.70), ("Plain Carbon Steel", 7.80),
                        ("Stainless Steel 304", 8.00), ("Brass", 8.50), ("Copper", 8.96),
                        ("Titanium Ti-6Al-4V", 4.43), ("Oak", 0.75)]:
            self.material.addItem(name, d)
        self.material.currentIndexChanged.connect(self._pick)
        row.addWidget(self.material)
        lay.addLayout(row)
        self.text = QtWidgets.QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        self.text.setMinimumSize(520, 330)
        lay.addWidget(self.text)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        copy = bb.addButton("Copy to Clipboard", QtWidgets.QDialogButtonBox.ActionRole)
        copy.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(self.text.toPlainText()))
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.update()

    def _pick(self, i):
        d = self.material.itemData(i)
        if d:
            self.density.setValue(d)

    def update(self):
        rho = self.density.value() / 1000.0  # g/mm³
        App.ParamGet("User parameter:BaseApp/Preferences/Mod/SolidStyle").SetFloat("Density", self.density.value())
        solids = []
        for o in self.objs:
            solids.extend(o.Shape.Solids)
        if not solids:
            self.text.setPlainText("Nothing to measure.\nSelect a body or solid, or activate a body.")
            return
        import Part
        comp = Part.makeCompound(solids)
        vol = sum(s.Volume for s in solids)
        area = sum(s.Area for s in solids)
        com = App.Vector()
        for s in solids:
            com += s.CenterOfMass * s.Volume
        com = com * (1.0 / vol)
        # inertia about the center of mass, summed with the parallel-axis theorem
        I = [[0.0] * 3 for _ in range(3)]
        for s in solids:
            m = s.MatrixOfInertia
            d = s.CenterOfMass - com
            dv = (d.x, d.y, d.z)
            for r in range(3):
                for c in range(3):
                    val = m.A[r * 4 + c]
                    pa = (d.Length ** 2 if r == c else 0.0) - dv[r] * dv[c]
                    I[r][c] += val + s.Volume * pa
        mass = vol * rho
        Ig = [[I[r][c] * rho for c in range(3)] for r in range(3)]
        bb = comp.BoundBox
        lines = [
            "Mass properties of: %s" % ", ".join(o.Label for o in self.objs),
            "",
            "Density = %.4f grams per cubic centimeter" % self.density.value(),
            "",
            "Mass = %.3f grams" % mass,
            "",
            "Volume = %.3f cubic millimeters" % vol,
            "",
            "Surface area = %.3f square millimeters" % area,
            "",
            "Center of mass: ( millimeters )",
            "\tX = %.3f" % com.x, "\tY = %.3f" % com.y, "\tZ = %.3f" % com.z,
            "",
            "Bounding box: %.3f x %.3f x %.3f mm" % (bb.XLength, bb.YLength, bb.ZLength),
            "",
            "Moments of inertia: ( grams * square millimeters )",
            "Taken at the center of mass and aligned with the output coordinate system.",
            "\tLxx = %.3f\tLxy = %.3f\tLxz = %.3f" % tuple(Ig[0]),
            "\tLyx = %.3f\tLyy = %.3f\tLyz = %.3f" % tuple(Ig[1]),
            "\tLzx = %.3f\tLzy = %.3f\tLzz = %.3f" % tuple(Ig[2]),
        ]
        self.text.setPlainText("\n".join(lines))
