@echo off
rem Double-click to install the SolidWorks Style workbench for FreeCAD (Windows).
rem Add -MySettings to also copy the saved FreeCAD settings (close FreeCAD first).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
pause
