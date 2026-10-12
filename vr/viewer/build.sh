#!/bin/bash
cd "$(dirname "$0")"
SVR=/opt/steamvr/bin/linuxarm64
gcc -O2 -Wall -Wno-missing-braces -Wno-unused-variable -Iinclude src/fcvr.c -o fcvr -L$SVR -lopenvr_api -lEGL -lOpenGL -lm -Wl,-rpath,$SVR
