#!/bin/bash
# Cross-compile the viewer for Windows into windows/ (fcvr.exe + openvr_api.dll + SteamVR input files).
# Needs x86_64-w64-mingw32-gcc, or zig (pip install ziglang). The FreeCAD_SolidWorksUI installer copies
# windows/ to %LOCALAPPDATA%\fcvr on Windows.
set -e
cd "$(dirname "$0")"
mkdir -p windows
OVR=https://raw.githubusercontent.com/ValveSoftware/openvr/master
[ -f windows/openvr_api.dll ] || curl -sSLf -o windows/openvr_api.dll $OVR/bin/win64/openvr_api.dll
[ -f windows/openvr_api.lib ] || curl -sSLf -o windows/openvr_api.lib $OVR/lib/win64/openvr_api.lib
[ -f windows/OPENVR_LICENSE ] || curl -sSLf -o windows/OPENVR_LICENSE $OVR/LICENSE
FLAGS="-O2 -Wall -Wno-missing-braces -Wno-unused-variable -Iinclude src/fcvr.c -o windows/fcvr.exe windows/openvr_api.lib -lopengl32 -lgdi32 -luser32"
if command -v x86_64-w64-mingw32-gcc >/dev/null; then
    x86_64-w64-mingw32-gcc $FLAGS -static-libgcc
elif command -v zig >/dev/null; then
    zig cc -target x86_64-windows-gnu $FLAGS
elif ZPY=$(ls -d /tmp/claude-1000/zv/bin/python ~/.local/zig-venv/bin/python 2>/dev/null | head -1) && [ -n "$ZPY" ]; then
    "$ZPY" -m ziglang cc -target x86_64-windows-gnu $FLAGS
else
    echo "No Windows compiler: install mingw-w64, or: python3 -m venv ~/.local/zig-venv && ~/.local/zig-venv/bin/pip install ziglang"
    exit 1
fi
rm -f windows/fcvr.pdb
cp actions.json bindings_frame_controller.json windows/
echo "built windows/fcvr.exe"
