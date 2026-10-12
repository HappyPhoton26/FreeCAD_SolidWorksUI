#!/bin/bash
# Copy the live SolidStyle workbench, VR add-on/viewer and this machine's FreeCAD settings into this folder.
# Run it after changing any of them, then commit + push.
set -e
W="$(cd "$(dirname "$0")" && pwd)"
FC=~/.var/app/org.freecad.FreeCAD
MOD=$FC/data/FreeCAD/Mod
rsync -a --delete --exclude __pycache__ "$MOD/SolidStyle/" "$W/SolidStyle/"
mkdir -p "$W/vr"
rsync -a --delete --exclude __pycache__ "$(readlink -f "$MOD/VRLiveExport")/" "$W/vr/freecad_addon/"
rsync -a --delete --exclude fcvr --exclude fcvr.log --exclude freecad_addon --exclude '*.old' --exclude openxr \
      ~/fcvr/ "$W/vr/viewer/"
mkdir -p "$W/my_settings"
cp "$FC/config/FreeCAD/user.cfg" "$W/my_settings/user.cfg"
echo "solidworks_workbench/ updated from this machine"
