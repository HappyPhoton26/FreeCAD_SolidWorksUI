#!/bin/bash
# Install the SolidWorks Style workbench for FreeCAD 1.0 (Linux).
#   ./install.sh                 workbench (+ VR viewer if SteamVR is installed)
#   ./install.sh --no-vr         workbench only
#   ./install.sh --my-settings   also restore the exact FreeCAD settings saved in my_settings/ (close FreeCAD first)
set -e
W="$(cd "$(dirname "$0")" && pwd)"
VR=auto; MINE=0
for a in "$@"; do
    case "$a" in
        --no-vr) VR=no ;; --vr) VR=yes ;; --my-settings) MINE=1 ;;
        *) echo "unknown option $a"; exit 1 ;;
    esac
done

if flatpak info org.freecad.FreeCAD >/dev/null 2>&1; then
    DATA=~/.var/app/org.freecad.FreeCAD/data/FreeCAD; CONF=~/.var/app/org.freecad.FreeCAD/config/FreeCAD
elif command -v freecad >/dev/null || command -v FreeCAD >/dev/null; then
    DATA=~/.local/share/FreeCAD; CONF=~/.config/FreeCAD
else
    echo "FreeCAD 1.0 not found. Install it (e.g. flatpak install flathub org.freecad.FreeCAD) and run this again."
    exit 1
fi
MOD=$DATA/Mod
mkdir -p "$MOD"

# the workbench
rsync -a --delete "$W/SolidStyle/" "$MOD/SolidStyle/"
echo "Installed the SolidWorks Style workbench in $MOD"

# VR model viewer (SteamVR on Linux)
if [ "$VR" = yes ] || { [ "$VR" = auto ] && [ -d /opt/steamvr -o -d ~/.local/share/Steam/steamapps/common/SteamVR ]; }; then
    mkdir -p ~/fcvr
    rsync -a "$W/vr/viewer/" ~/fcvr/
    rsync -a --delete "$W/vr/freecad_addon/" ~/fcvr/freecad_addon/
    rm -rf "$MOD/VRLiveExport"; ln -s ~/fcvr/freecad_addon "$MOD/VRLiveExport"
    if (cd ~/fcvr && ./build.sh); then echo "Installed the VR viewer in ~/fcvr"
    else echo "WARNING: the VR viewer did not build (needs gcc, and SteamVR's libopenvr_api.so; see vr/viewer/build.sh)"; fi
fi

# exact settings from the machine this came from (optional)
if [ "$MINE" = 1 ]; then
    if pgrep -f org.freecad.FreeCAD >/dev/null || pgrep -x FreeCAD >/dev/null || pgrep -x freecad >/dev/null; then
        echo "Close FreeCAD first (it rewrites its settings when it exits), then run again with --my-settings."
        exit 1
    fi
    mkdir -p "$CONF"
    [ -f "$CONF/user.cfg" ] && cp "$CONF/user.cfg" "$CONF/user.cfg.before_install_$(date +%Y%m%d_%H%M%S)"
    cp "$W/my_settings/user.cfg" "$CONF/user.cfg"
    echo "Restored the saved FreeCAD settings (your old ones are next to them as user.cfg.before_install_*)"
fi

echo
echo "Start FreeCAD and pick 'SolidWorks Style' in the workbench list."
echo "The first time, it switches FreeCAD to the SolidWorks look (Tools > Restore My Settings undoes it)."
