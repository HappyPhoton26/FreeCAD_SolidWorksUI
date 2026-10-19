@echo off
rem Double-click to install the SolidWorks Style workbench for FreeCAD (Windows).
rem Options: -MySettings (copy the saved FreeCAD settings without asking), -NoSettings, -NoVR (skip VR).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
if errorlevel 1 echo. & echo The install did not finish - see the messages above.
pause
