[CmdletBinding()]
param(
    [string]$GameDir,
    [switch]$SkipTrailColor
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Find-GameDirectory {
    param([string]$RequestedPath)

    if (-not [string]::IsNullOrWhiteSpace($RequestedPath)) {
        return [IO.Path]::GetFullPath($RequestedPath).TrimEnd('\', '/')
    }

    $candidates = New-Object 'System.Collections.Generic.List[string]'
    foreach ($drive in [IO.DriveInfo]::GetDrives()) {
        if (-not $drive.IsReady) { continue }
        foreach ($relative in @(
            'SteamLibrary\steamapps\common\Overcooked! 2',
            'Program Files (x86)\Steam\steamapps\common\Overcooked! 2'
        )) {
            $candidate = [IO.Path]::GetFullPath((Join-Path $drive.RootDirectory.FullName $relative))
            if (Test-Path -LiteralPath (Join-Path $candidate 'Overcooked2.exe') -PathType Leaf) {
                if (-not $candidates.Contains($candidate)) { $candidates.Add($candidate) }
            }
        }
    }

    if ($candidates.Count -ne 1) {
        $found = if ($candidates.Count -eq 0) { '<none>' } else { $candidates -join '; ' }
        throw "Could not select one game directory. Pass -GameDir explicitly. Found: $found"
    }
    return $candidates[0]
}

function Get-PeMachine {
    param([string]$ExecutablePath)

    $stream = [IO.File]::Open($ExecutablePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    $reader = New-Object IO.BinaryReader($stream)
    try {
        $stream.Position = 0x3c
        $peOffset = $reader.ReadInt32()
        $stream.Position = $peOffset
        if ($reader.ReadUInt32() -ne 0x00004550) { throw 'Invalid PE signature' }
        return $reader.ReadUInt16()
    }
    finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

function Assert-UnderRoot {
    param([string]$Path, [string]$Root, [string]$Label)

    $fullPath = [IO.Path]::GetFullPath($Path)
    $fullRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    if (-not $fullPath.StartsWith($fullRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label escaped the intended root: $fullPath"
    }
    return $fullPath
}

function Move-ToBackup {
    param([string]$SourcePath, [string]$GameRoot, [string]$BackupRoot)

    if (-not (Test-Path -LiteralPath $SourcePath)) { return }
    $sourceFull = Assert-UnderRoot -Path $SourcePath -Root $GameRoot -Label 'Backup source'
    $relative = $sourceFull.Substring($GameRoot.Length).TrimStart('\', '/')
    $destination = Assert-UnderRoot -Path (Join-Path $BackupRoot $relative) -Root $BackupRoot -Label 'Backup destination'
    $destinationParent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
    if (Test-Path -LiteralPath $destination) { throw "Backup destination already exists: $destination" }
    Move-Item -LiteralPath $sourceFull -Destination $destination
}

function Copy-DirectoryContents {
    param([string]$Source, [string]$Destination)

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
    }
}

function Write-YierPreference {
    param([string]$PreferPath, [string]$OfficialListPath)

    $utf8NoBom = New-Object Text.UTF8Encoding($false)
    $result = New-Object 'System.Collections.Generic.List[string]'
    $hasLobbySwitch = $false

    if (Test-Path -LiteralPath $PreferPath -PathType Leaf) {
        foreach ($line in [IO.File]::ReadAllLines($PreferPath)) {
            if ($line -match '^\s*174-yier\s+HAT=') { continue }
            if ($line -match '^\s*LOBBYSWITCHCHEF=') {
                if (-not $hasLobbySwitch) {
                    $result.Add('174-yier HAT=YierCap')
                    $result.Add('')
                    $result.Add($line)
                    $hasLobbySwitch = $true
                }
                continue
            }
            $result.Add($line)
        }
    }
    else {
        foreach ($headName in [IO.File]::ReadAllLines($OfficialListPath)) {
            if (-not [string]::IsNullOrWhiteSpace($headName)) {
                $result.Add($headName.Trim() + ' HAT=Santa')
            }
        }
    }

    if (-not $hasLobbySwitch) {
        while ($result.Count -gt 0 -and [string]::IsNullOrWhiteSpace($result[$result.Count - 1])) {
            $result.RemoveAt($result.Count - 1)
        }
        $result.Add('174-yier HAT=YierCap')
        $result.Add('')
        $result.Add('LOBBYSWITCHCHEF=TRUE')
    }

    $parent = Split-Path -Parent $PreferPath
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    [IO.File]::WriteAllLines($PreferPath, $result.ToArray(), $utf8NoBom)
}

function Ensure-HostUtilities {
    param([string]$PluginsDirectory, [string]$BackupRoot)

    $expectedArchiveHash = 'E38A0589C35B726C7B3D5886163D3267E71534F0DB883FC66E6495AAEADF0220'
    $expectedDllHash = 'E9663293FCC8C4CFFAD75D4F78211406D12E1DC5ED12B9F7B88EBA4D0EE2B022'
    $existing = @(Get-ChildItem -LiteralPath $PluginsDirectory -Filter 'HostUtilities.dll' -Recurse -File -ErrorAction SilentlyContinue)
    foreach ($candidate in $existing) {
        if ((Get-FileHash -LiteralPath $candidate.FullName -Algorithm SHA256).Hash -eq $expectedDllHash) {
            Write-Host "HostUtilities 1.8.0 already present: $($candidate.FullName)"
            return $true
        }
    }
    if ($existing.Count -gt 0) {
        Write-Warning 'Another HostUtilities build is installed. Skipping trail-colour installation to avoid duplicate plugin GUIDs.'
        return $false
    }

    try {
        $downloadRoot = Join-Path ([IO.Path]::GetTempPath()) ('YierPackage-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $downloadRoot | Out-Null
        $archive = Join-Path $downloadRoot 'HostUtilities.Core.zip'
        $expanded = Join-Path $downloadRoot 'expanded'
        Invoke-WebRequest -Uri 'https://github.com/CH3NGYZ/Overcooked-2-HostUtilities-Stable-Releases/releases/download/v1.8.0/HostUtilities.Core.zip' -OutFile $archive
        $actualArchiveHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
        if ($actualArchiveHash -ne $expectedArchiveHash) {
            throw "HostUtilities archive SHA-256 mismatch: $actualArchiveHash"
        }
        Expand-Archive -LiteralPath $archive -DestinationPath $expanded
        $dlls = @(Get-ChildItem -LiteralPath $expanded -Filter 'HostUtilities.dll' -Recurse -File)
        if ($dlls.Count -ne 1) { throw "Expected one HostUtilities.dll, found $($dlls.Count)" }
        $actualDllHash = (Get-FileHash -LiteralPath $dlls[0].FullName -Algorithm SHA256).Hash
        if ($actualDllHash -ne $expectedDllHash) {
            throw "HostUtilities.dll SHA-256 mismatch: $actualDllHash"
        }
        $sourceRoot = Join-Path $expanded 'OC2HostUtilities'
        if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
            throw 'HostUtilities archive layout is not recognized.'
        }
        Copy-DirectoryContents -Source $sourceRoot -Destination (Join-Path $PluginsDirectory 'OC2HostUtilities')
        Write-Host 'Downloaded and installed verified HostUtilities 1.8.0 Core.'
        return $true
    }
    catch {
        Write-Warning ("HostUtilities installation failed; Yier will still work, but trail colours were skipped. " + $_.Exception.Message)
        return $false
    }
}

$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$payloadRoot = Join-Path $packageRoot 'payload'
foreach ($required in @(
    'BepInEx-x86',
    'OC2DIYChef\OC2DIYChef.dll',
    'OC2DIYChef\official-all.txt',
    'Resources\174-yier',
    'Resources\HATS\YierCap'
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $payloadRoot $required))) {
        throw "Package payload is incomplete: $required"
    }
}

$gameRoot = Find-GameDirectory -RequestedPath $GameDir
$gameExe = Join-Path $gameRoot 'Overcooked2.exe'
if (-not (Test-Path -LiteralPath $gameExe -PathType Leaf)) {
    throw "Overcooked2.exe was not found: $gameExe"
}
if ((Get-PeMachine -ExecutablePath $gameExe) -ne 0x014c) {
    throw 'This package contains x86 BepInEx and only supports the Steam standard x86 game build.'
}
if (Get-Process -Name 'Overcooked2' -ErrorAction SilentlyContinue) {
    throw 'Overcooked! 2 is running. Close the game and run the installer again.'
}

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupRoot = Assert-UnderRoot -Path (Join-Path $gameRoot "BepInEx\YierPackageBackups\$timestamp") -Root $gameRoot -Label 'Backup root'
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

$bepInExDll = Join-Path $gameRoot 'BepInEx\core\BepInEx.dll'
if (-not (Test-Path -LiteralPath $bepInExDll -PathType Leaf)) {
    Copy-DirectoryContents -Source (Join-Path $payloadRoot 'BepInEx-x86') -Destination $gameRoot
    Write-Host 'Installed BepInEx 5.4.22 x86.'
}
else {
    Write-Host 'Existing BepInEx detected; core files were left unchanged.'
}

$diyRoot = Join-Path $gameRoot 'BepInEx\plugins\OC2DIYChef'
$resourcesRoot = Join-Path $diyRoot 'Resources'
$hatsRoot = Join-Path $resourcesRoot 'HATS'
New-Item -ItemType Directory -Path $hatsRoot -Force | Out-Null

foreach ($path in @(
    (Join-Path $diyRoot 'OC2DIYChef.dll'),
    (Join-Path $diyRoot 'official-all.txt'),
    (Join-Path $resourcesRoot '174-yier'),
    (Join-Path $hatsRoot 'YierCap'),
    (Join-Path $hatsRoot 'YierBlueCap')
)) {
    Move-ToBackup -SourcePath $path -GameRoot $gameRoot -BackupRoot $backupRoot
}

Copy-Item -LiteralPath (Join-Path $payloadRoot 'OC2DIYChef\OC2DIYChef.dll') -Destination (Join-Path $diyRoot 'OC2DIYChef.dll') -Force
Copy-Item -LiteralPath (Join-Path $payloadRoot 'OC2DIYChef\official-all.txt') -Destination (Join-Path $diyRoot 'official-all.txt') -Force
Copy-DirectoryContents -Source (Join-Path $payloadRoot 'Resources\174-yier') -Destination (Join-Path $resourcesRoot '174-yier')
Copy-DirectoryContents -Source (Join-Path $payloadRoot 'Resources\HATS\YierCap') -Destination (Join-Path $hatsRoot 'YierCap')

$preferPath = Join-Path $diyRoot 'prefer.txt'
if (Test-Path -LiteralPath $preferPath -PathType Leaf) {
    $preferBackup = Join-Path $backupRoot 'BepInEx\plugins\OC2DIYChef\prefer.txt'
    New-Item -ItemType Directory -Path (Split-Path -Parent $preferBackup) -Force | Out-Null
    Copy-Item -LiteralPath $preferPath -Destination $preferBackup
}
Write-YierPreference -PreferPath $preferPath -OfficialListPath (Join-Path $diyRoot 'official-all.txt')

$trailInstalled = $false
if (-not $SkipTrailColor) {
    $pluginsRoot = Join-Path $gameRoot 'BepInEx\plugins'
    if (Ensure-HostUtilities -PluginsDirectory $pluginsRoot -BackupRoot $backupRoot) {
        $trailTarget = Join-Path $pluginsRoot 'OC2DIYChefTrailColor'
        foreach ($name in @('OC2DIYChefTrailColor.dll', 'OC2DIYChefTrailColorGUI.dll')) {
            Move-ToBackup -SourcePath (Join-Path $trailTarget $name) -GameRoot $gameRoot -BackupRoot $backupRoot
        }
        Copy-DirectoryContents -Source (Join-Path $payloadRoot 'TrailColor') -Destination $trailTarget
        $configTarget = Join-Path $gameRoot 'BepInEx\config\local.oc2.diycheftrailcolor.cfg'
        if (-not (Test-Path -LiteralPath $configTarget -PathType Leaf)) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $configTarget) -Force | Out-Null
            Copy-Item -LiteralPath (Join-Path $payloadRoot 'default-trail-color.cfg') -Destination $configTarget
        }
        $trailInstalled = $true
    }
}

$receipt = @(
    'Package=Yier-OC2DIYChef-v0.4.0-test',
    "InstalledAt=$([DateTime]::Now.ToString('o'))",
    "GameDir=$gameRoot",
    "BackupDir=$backupRoot",
    "TrailColorInstalled=$trailInstalled",
    'Hat=YierCap'
)
[IO.File]::WriteAllLines((Join-Path $backupRoot 'INSTALL-RECEIPT.txt'), $receipt, (New-Object Text.UTF8Encoding($false)))

Write-Host ''
Write-Host 'Yier installation completed.' -ForegroundColor Green
Write-Host "Game: $gameRoot"
Write-Host "Backup: $backupRoot"
Write-Host 'Preference: 174-yier HAT=YierCap'
if ($trailInstalled) { Write-Host 'Trail colour GUI: installed (press F10 in game)' }
elseif ($SkipTrailColor) { Write-Host 'Trail colour GUI: skipped by request' }
else { Write-Host 'Trail colour GUI: not installed; see warnings above' }
