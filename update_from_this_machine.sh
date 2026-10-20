#!/bin/bash
# Copy the live SolidStyle workbench, VR add-on/viewer and this machine's FreeCAD settings into this folder.
# Run it after changing any of them, then commit + push.
set -e
W="$(cd "$(dirname "$0")" && pwd)"
FC=~/.var/app/org.freecad.FreeCAD
VER=v1-1                                    # FreeCAD 1.1 keeps its user files per version
MOD=$FC/data/FreeCAD/$VER/Mod
CFG=$FC/config/FreeCAD/$VER/user.cfg
rsync -a --delete --exclude __pycache__ "$MOD/SolidStyle/" "$W/SolidStyle/"
mkdir -p "$W/vr"
rsync -a --delete --exclude __pycache__ "$(readlink -f "$MOD/VRLiveExport")/" "$W/vr/freecad_addon/"
rsync -a --delete --exclude fcvr --exclude fcvr.log --exclude freecad_addon --exclude '*.old' --exclude openxr \
      ~/fcvr/ "$W/vr/viewer/"
mkdir -p "$W/my_settings"
# settings without this machine's file paths (recent files, folders, programs), which mean nothing on Windows
python3 - "$CFG" "$W/my_settings/user.cfg" <<'PY'
import re, sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()
linux = re.compile(r'^\s*<FCText Name="[^"]*">(/home/|/app/|/usr/|/tmp/|/var/|/run/)[^<]*</FCText>\n', re.M)
text = linux.sub("", text)
# start FreeCAD in this workbench, like the Frame
text = re.sub(r'(<FCText Name="AutoloadModule">)[^<]*(</FCText>)', r'\1SolidStyleWorkbench\2', text)
open(dst, "w", encoding="utf-8", newline="\n").write(text)
PY
echo "updated from this machine (FreeCAD $VER)"
