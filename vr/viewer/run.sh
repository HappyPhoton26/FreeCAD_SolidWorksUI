#!/bin/bash
# Start (or restart) the FreeCAD VR model viewer (a SteamVR overlay; the desktop stays).
# "run.sh stop" stops it, "run.sh toggle" starts or stops it (used by FreeCAD's VR button).
cd "$(dirname "$0")"
case "$1" in
  stop) pkill -x fcvr; echo "VR viewer stopped"; exit 0 ;;
  toggle) if pgrep -x fcvr >/dev/null; then pkill -x fcvr; echo "VR viewer stopped"; exit 0; fi ;;
esac
pkill -x fcvr; sleep 0.5
nohup ./fcvr > fcvr.log 2>&1 &
echo "VR viewer started (log: $(pwd)/fcvr.log)"
