# Install the SolidWorks Style workbench for FreeCAD 1.0 (Windows).
#   install.bat                  workbench
#   install.bat -MySettings      also restore the exact FreeCAD settings saved in my_settings\ (close FreeCAD first)
# The VR viewer is Linux-only for now, so it isn't installed here.
param([switch]$MySettings)
$ErrorActionPreference = "Stop"
$W = Split-Path -Parent $MyInvocation.MyCommand.Path

# Ask FreeCAD itself where its user folder is (it differs between versions); fall back to %APPDATA%\FreeCAD.
$cmd = $null
$cands = @()
foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, "$env:LOCALAPPDATA\Programs")) {
    if ($root -and (Test-Path $root)) {
        $cands += Get-ChildItem -Path $root -Directory -Filter "FreeCAD*" -ErrorAction SilentlyContinue |
                  ForEach-Object { Join-Path $_.FullName "bin\FreeCADCmd.exe" } | Where-Object { Test-Path $_ }
    }
}
$onPath = Get-Command FreeCADCmd.exe -ErrorAction SilentlyContinue
if ($onPath) { $cands = @($onPath.Source) + $cands }
if ($cands.Count -gt 0) { $cmd = ($cands | Sort-Object -Descending)[0] }

$data = $null
if ($cmd) {
    $py = Join-Path $env:TEMP "ss_where.py"
    Set-Content -Path $py -Value "import FreeCAD; print('SSDIR=' + FreeCAD.getUserAppDataDir() + '|' + FreeCAD.getUserConfigDir())"
    $out = & $cmd $py 2>$null | Select-String "SSDIR=" | Select-Object -First 1
    Remove-Item $py -ErrorAction SilentlyContinue
    if ($out) {
        $parts = $out.ToString().Substring($out.ToString().IndexOf("SSDIR=") + 6).Split("|")
        $data = $parts[0].Trim(); $conf = $parts[1].Trim()
    }
    Write-Host "Found FreeCAD: $cmd"
} else {
    Write-Host "Couldn't find FreeCADCmd.exe; assuming the standard folder. Install FreeCAD 1.0 from https://www.freecad.org if you haven't."
}
if (-not $data) { $data = Join-Path $env:APPDATA "FreeCAD"; $conf = $data }

$mod = Join-Path $data "Mod"
New-Item -ItemType Directory -Force -Path $mod | Out-Null
$dest = Join-Path $mod "SolidStyle"
if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
Copy-Item -Recurse (Join-Path $W "SolidStyle") $dest
Get-ChildItem -Path $dest -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Write-Host "Installed the SolidWorks Style workbench in $dest"

if ($MySettings) {
    if (Get-Process -Name "FreeCAD*" -ErrorAction SilentlyContinue) {
        Write-Host "Close FreeCAD first (it rewrites its settings when it exits), then run again with -MySettings."
        exit 1
    }
    New-Item -ItemType Directory -Force -Path $conf | Out-Null
    $cfg = Join-Path $conf "user.cfg"
    if (Test-Path $cfg) { Copy-Item $cfg ("$cfg.before_install_" + (Get-Date -Format "yyyyMMdd_HHmmss")) }
    Copy-Item (Join-Path $W "my_settings\user.cfg") $cfg
    Write-Host "Restored the saved FreeCAD settings (your old ones are next to them as user.cfg.before_install_*)"
}

Write-Host ""
Write-Host "Start FreeCAD and pick 'SolidWorks Style' in the workbench list."
Write-Host "The first time, it switches FreeCAD to the SolidWorks look (Tools > Restore My Settings undoes it)."
