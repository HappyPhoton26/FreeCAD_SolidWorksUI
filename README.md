# SolidWorks Style workbench for FreeCAD

Makes FreeCAD 1.0 look and work like SolidWorks: CommandManager ribbon, SolidWorks tool and feature names,
SolidWorks-style feature panels, shortcuts, light SolidWorks colour scheme with the blue-to-white
gradient background. Optional extra: a VR viewer that floats the model you're editing in a SteamVR headset.

## Install (Linux)
```
./install.sh
```
Then start FreeCAD and choose **SolidWorks Style** in the workbench list. The first time, it applies the
SolidWorks look (light theme, gradient background, part colours, SolidWorks-like mouse).
**Tools > Restore My Settings** puts your old look back.

Options: `--no-vr` (skip the VR viewer), `--my-settings` (also copy the exact FreeCAD settings in
`my_settings/user.cfg`: theme, toolbars, shortcuts, navigation; close FreeCAD first).

**Windows / macOS:** copy the `SolidStyle` folder into FreeCAD's `Mod` folder
(in FreeCAD's Python console, `App.getUserAppDataDir()` shows where that is), then restart FreeCAD.

## What's in here
| Folder | What it is |
|---|---|
| `SolidStyle/` | The workbench (see `SolidStyle/README.md` for all features) |
| `vr/freecad_addon/` | FreeCAD add-on: exports the open model for VR, the **VR** and **?** toolbar buttons, VR hotkeys |
| `vr/viewer/` | The VR viewer (SteamVR overlay, C source); built into `~/fcvr` by the installer |
| `my_settings/user.cfg` | Snapshot of the FreeCAD settings on the machine this was made on |

## Using VR
Click **VR** in FreeCAD (or Ctrl+Alt+V) with SteamVR running. Click **?** for the hotkey list.
The model follows the FreeCAD view; Ctrl+Alt+S types a scale, grip on the controller grabs it.

## Updating this folder (maintainer)
After changing the workbench, VR files or FreeCAD settings on the main machine, run
`./update_from_this_machine.sh`, then commit and push.
