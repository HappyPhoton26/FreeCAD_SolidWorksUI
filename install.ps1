# Install the SolidWorks Style workbench for FreeCAD 1.0 / 1.1 (Windows).
#   install.bat                  workbench + VR viewer; asks whether to copy the saved FreeCAD settings too
#   install.bat -MySettings      also restore the FreeCAD settings saved in my_settings\ without asking
#   install.bat -NoSettings      never touch the FreeCAD settings
#   install.bat -NoVR            skip the VR viewer (Show in VR button; needs SteamVR, e.g. a Steam Frame over Steam Link)
param([switch]$MySettings, [switch]$NoSettings, [switch]$NoVR)
$ErrorActionPreference = "Stop"
$W = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Join-Path $env:APPDATA "FreeCAD"

# ---------------------------------------------------------------------------------------------
# Where does FreeCAD look for add-ons? 1.0 uses %APPDATA%\FreeCAD\Mod, 1.1 and later keep one
# folder per version: %APPDATA%\FreeCAD\v1-1\Mod. Work it out for every FreeCAD installed here.
# ---------------------------------------------------------------------------------------------
function UserDir([int]$major, [int]$minor) {
    if ($major -gt 1 -or ($major -eq 1 -and $minor -ge 1)) { return (Join-Path $Root ("v{0}-{1}" -f $major, $minor)) }
    return $Root
}

$found = @()        # FreeCAD program folders
foreach ($pf in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, (Join-Path $env:LOCALAPPDATA "Programs"))) {
    if ($pf -and (Test-Path $pf)) {
        $found += Get-ChildItem -Path $pf -Directory -Filter "FreeCAD*" -ErrorAction SilentlyContinue |
                  Where-Object { (Test-Path (Join-Path $_.FullName "bin\FreeCAD.exe")) -or
                                 (Test-Path (Join-Path $_.FullName "bin\freecad.exe")) }
    }
}

$targets = @()
foreach ($d in $found) {
    $ver = $null
    if ($d.Name -match '(\d+)\.(\d+)') { $ver = @([int]$Matches[1], [int]$Matches[2]) }
    if (-not $ver) {
        $exe = Join-Path $d.FullName "bin\FreeCAD.exe"
        $pv = (Get-Item $exe -ErrorAction SilentlyContinue).VersionInfo.ProductVersion
        if ($pv -and $pv -match '^(\d+)\.(\d+)') { $ver = @([int]$Matches[1], [int]$Matches[2]) }
    }
    if ($ver) {
        Write-Host ("Found FreeCAD {0}.{1} in {2}" -f $ver[0], $ver[1], $d.FullName)
        $targets += UserDir $ver[0] $ver[1]
    } else {
        Write-Host "Found FreeCAD in $($d.FullName) (version unknown)"
    }
}
# user folders FreeCAD has already made (also covers portable / unusual installs)
if (Test-Path $Root) {
    $targets += Get-ChildItem -Path $Root -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match '^v\d+-\d+$' } | ForEach-Object { $_.FullName }
}
if ($targets.Count -eq 0) {
    Write-Host "Couldn't find FreeCAD; installing for FreeCAD 1.1 (get it from https://www.freecad.org)."
    $targets += UserDir 1 1
}
$targets = $targets | Sort-Object -Unique

# ---------------------------------------------------------------------------------------------
# Settings: ask once (they have to be copied while FreeCAD is closed)
# ---------------------------------------------------------------------------------------------
$saved = Join-Path $W "my_settings\user.cfg"
$doSettings = $MySettings
if (-not $MySettings -and -not $NoSettings -and (Test-Path $saved)) {
    Write-Host ""
    Write-Host "Also copy the FreeCAD settings from the Steam Frame (look, mouse/navigation, toolbars, units)?"
    Write-Host "Your current settings are kept as a backup next to them."
    $a = Read-Host "Copy settings? [Y/n]"
    $doSettings = ($a -eq "" -or $a -match '^[Yy]')
}
# FreeCAD writes its settings back when it closes, so it has to be closed for this
$running = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(FreeCAD|freecad)' }
if ($running) {
    Write-Host ""
    Write-Host "FreeCAD is running. Close it (save your work first), then press Enter."
    Read-Host | Out-Null
    $running = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(FreeCAD|freecad)' }
    if ($running) { Write-Host "FreeCAD is still open - stopping here so nothing gets overwritten."; exit 1 }
}

# ---------------------------------------------------------------------------------------------
# Install into every FreeCAD user folder
# ---------------------------------------------------------------------------------------------
# Start FreeCAD in this workbench (otherwise it opens in Part Design and looks like plain FreeCAD).
function Set-StartWorkbench($cfg) {
    if (-not (Test-Path $cfg)) {
        $xml = '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>' + "`n" +
               '<FCParameters><FCParamGroup Name="Root"><FCParamGroup Name="BaseApp"><FCParamGroup Name="Preferences">' +
               '<FCParamGroup Name="General"><FCText Name="AutoloadModule">SolidStyleWorkbench</FCText></FCParamGroup>' +
               '</FCParamGroup></FCParamGroup></FCParamGroup></FCParameters>' + "`n"
        [IO.File]::WriteAllText($cfg, $xml)
        return
    }
    $doc = New-Object System.Xml.XmlDocument
    $doc.PreserveWhitespace = $true
    $doc.Load($cfg)
    $node = $doc.DocumentElement
    foreach ($name in @("Root", "BaseApp", "Preferences", "General")) {
        $next = $node.SelectSingleNode("FCParamGroup[@Name='$name']")
        if (-not $next) {
            $next = $doc.CreateElement("FCParamGroup")
            $next.SetAttribute("Name", $name)
            $node.AppendChild($next) | Out-Null
        }
        $node = $next
    }
    $auto = $node.SelectSingleNode("FCText[@Name='AutoloadModule']")
    if (-not $auto) {
        $auto = $doc.CreateElement("FCText")
        $auto.SetAttribute("Name", "AutoloadModule")
        $node.AppendChild($auto) | Out-Null
    }
    $auto.InnerText = "SolidStyleWorkbench"
    $w = New-Object System.Xml.XmlTextWriter($cfg, (New-Object System.Text.UTF8Encoding($false)))
    $doc.Save($w)
    $w.Close()
}

function Install-Folder($src, $dest) {
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Copy-Item -Recurse $src $dest
    Get-ChildItem -Path $dest -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
}

# ---------------------------------------------------------------------------------------------
# Older copies anywhere FreeCAD might load them from (another version's Mod folder, a Macro folder,
# FreeCAD's own program folder) would be used instead of this one: move them out of the way.
# ---------------------------------------------------------------------------------------------
$installed = @($targets | ForEach-Object { [IO.Path]::GetFullPath((Join-Path (Join-Path $_ "Mod") "SolidStyle")) })
$search = @()
if (Test-Path $Root) { $search += $Root }
$search += $found | ForEach-Object { $_.FullName }
foreach ($base in $search) {
    $pkgs = Get-ChildItem -Path $base -Recurse -Directory -Filter "solidstyle" -ErrorAction SilentlyContinue |
            Where-Object { ($_.Name -ceq "solidstyle") -and (Test-Path (Join-Path $_.FullName "catalog.py")) -and
                           ($_.FullName -notmatch 'disabled_mods') }
    foreach ($pkg in $pkgs) {
        $owner = $pkg.Parent.FullName                          # the workbench folder holding it
        if ($installed -contains [IO.Path]::GetFullPath($owner)) { continue }   # replaced below anyway
        $what = $owner
        if (-not (Test-Path (Join-Path $owner "InitGui.py")) -or ($pkg.Parent.Name -in @("Mod", "Macro", "FreeCAD"))) {
            $what = $pkg.FullName                              # loose package, e.g. in Macro: move just that
        }
        $off = Join-Path $Root "disabled_mods"
        New-Item -ItemType Directory -Force -Path $off | Out-Null
        $to = Join-Path $off ((Split-Path $what -Leaf) + "_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
        try {
            Move-Item $what $to -ErrorAction Stop
            Write-Host "Moved an older copy out of the way: $what -> $to" -ForegroundColor Yellow
        } catch {
            Write-Host "There's an older copy in $what that couldn't be moved ($_)." -ForegroundColor Red
            Write-Host "  Delete that folder by hand (it may need administrator rights)." -ForegroundColor Red
        }
    }
}

$ok = $true
Write-Host ""
foreach ($t in $targets) {
    $mod = Join-Path $t "Mod"
    New-Item -ItemType Directory -Force -Path $mod | Out-Null

    # an older copy under another folder name would load instead of (or next to) this one
    Get-ChildItem -Path $mod -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne "SolidStyle" -and $_.Name -ne "VRLiveExport" } | ForEach-Object {
            $ig = Join-Path $_.FullName "InitGui.py"
            if ((Test-Path $ig) -and (Select-String -Path $ig -Pattern 'SolidWorks Style' -Quiet)) {
                $off = Join-Path $t "disabled_mods"
                New-Item -ItemType Directory -Force -Path $off | Out-Null
                $to = Join-Path $off $_.Name
                if (Test-Path $to) { Remove-Item -Recurse -Force $to }
                Move-Item $_.FullName $to
                Write-Host "  moved an older copy ($($_.Name)) out of the way to $to"
            }
        }

    $dest = Join-Path $mod "SolidStyle"
    Install-Folder (Join-Path $W "SolidStyle") $dest
    if (-not (Test-Path (Join-Path $dest "InitGui.py"))) { $ok = $false }
    Write-Host "Installed the SolidWorks Style workbench in $dest"

    if (-not $NoVR) {
        Install-Folder (Join-Path $W "vr\freecad_addon") (Join-Path $mod "VRLiveExport")
    }

    if ($doSettings) {
        $cfg = Join-Path $t "user.cfg"
        if (Test-Path $cfg) { Copy-Item $cfg ("$cfg.before_install_" + (Get-Date -Format "yyyyMMdd_HHmmss")) }
        Copy-Item $saved $cfg
        Write-Host "  copied the Steam Frame's FreeCAD settings (old ones: user.cfg.before_install_*)"
    }
    try {
        Set-StartWorkbench (Join-Path $t "user.cfg")
        Write-Host "  FreeCAD will start in the SolidWorks Style workbench"
    } catch {
        Write-Host "  couldn't set the start workbench ($_) - pick 'SolidWorks Style' in the workbench list" -ForegroundColor Yellow
    }
}

# VR viewer: fcvr.exe (the add-on above feeds it and adds the Show in VR button)
if (-not $NoVR) {
    $vrDir = Join-Path $env:LOCALAPPDATA "fcvr"
    Get-Process -Name "fcvr" -ErrorAction SilentlyContinue | Stop-Process -Force
    New-Item -ItemType Directory -Force -Path $vrDir | Out-Null
    Copy-Item -Force (Join-Path $W "vr\viewer\windows\*") $vrDir -Exclude "*.lib"
    Write-Host "Installed the VR viewer in $vrDir"
    $steam = @("${env:ProgramFiles(x86)}\Steam\steamapps\common\SteamVR", "$env:ProgramFiles\Steam\steamapps\common\SteamVR")
    if (-not ($steam | Where-Object { Test-Path $_ })) {
        Write-Host "  (SteamVR wasn't found in the usual place; install it from Steam to use Show in VR)"
    }
}

Write-Host ""
if (-not $ok) {
    Write-Host "Something went wrong copying the files - see the messages above." -ForegroundColor Red
    exit 1
}
Write-Host "Done. Start FreeCAD - it opens in the SolidWorks Style workbench (CommandManager, FeatureManager, Mates)." -ForegroundColor Green
if (-not $doSettings) {
    Write-Host "The first time, it switches FreeCAD to the SolidWorks look (Tools > Restore My Settings undoes it)."
}
