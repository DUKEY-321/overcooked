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

function Get-Sha256 {
    param([string]$Path)

    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($sha256.ComputeHash($stream)).Replace('-', '')
    }
    finally {
        $sha256.Dispose()
        $stream.Dispose()
    }
}

function Assert-CompatibleBepInEx {
    param([string]$GameRoot)

    $required = @(
        'winhttp.dll',
        'doorstop_config.ini',
        'BepInEx\core\BepInEx.dll',
        'BepInEx\core\BepInEx.Preloader.dll',
        'BepInEx\core\0Harmony20.dll'
    )
    $missing = @($required | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $GameRoot $_) -PathType Leaf)
    })
    if ($missing.Count -gt 0) {
        throw "Existing BepInEx is incomplete. Missing: $($missing -join ', ')"
    }

    $bepInExDll = Join-Path $GameRoot 'BepInEx\core\BepInEx.dll'
    try {
        $version = [Reflection.AssemblyName]::GetAssemblyName($bepInExDll).Version
    }
    catch {
        throw "Could not read the existing BepInEx version: $($_.Exception.Message)"
    }
    if ($version.Major -ne 5) {
        throw "Existing BepInEx $version is incompatible. This package requires BepInEx 5.x x86."
    }

    $doorstopDll = Join-Path $GameRoot 'winhttp.dll'
    if ((Get-PeMachine -ExecutablePath $doorstopDll) -ne 0x014c) {
        throw 'Existing winhttp.dll is not x86. This package only supports the Steam standard x86 game build.'
    }
    return $version
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

function Assert-PackageIntegrity {
    param([string]$PackageRoot)

    $manifestPath = Join-Path $PackageRoot 'SHA256SUMS.txt'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw 'SHA256SUMS.txt is missing. Extract or copy the complete package before installing.'
    }

    $checked = 0
    $expectedPayloadFiles = @{}
    foreach ($line in [IO.File]::ReadAllLines($manifestPath)) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line -notmatch '^([0-9A-Fa-f]{64})  (.+)$') {
            throw "Invalid SHA256SUMS.txt line: $line"
        }

        $expected = $matches[1].ToUpperInvariant()
        $manifestRelative = $matches[2].Replace('\', '/')
        $relative = $manifestRelative.Replace('/', '\')
        if ([IO.Path]::IsPathRooted($relative) -or $relative.Split('\') -contains '..') {
            throw "Unsafe package manifest path: $relative"
        }

        $target = Assert-UnderRoot `
            -Path (Join-Path $PackageRoot $relative) `
            -Root $PackageRoot `
            -Label 'Package manifest entry'
        if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
            throw "Package file is missing: $relative"
        }

        $actual = Get-Sha256 -Path $target
        if ($actual -ne $expected) {
            throw "Package file SHA-256 mismatch: $relative"
        }
        if ($manifestRelative.StartsWith('payload/', [StringComparison]::OrdinalIgnoreCase)) {
            $expectedPayloadFiles[$manifestRelative.ToLowerInvariant()] = $true
        }
        $checked++
    }

    if ($checked -eq 0) { throw 'SHA256SUMS.txt contains no files.' }

    $payloadRoot = Join-Path $PackageRoot 'payload'
    if (-not (Test-Path -LiteralPath $payloadRoot -PathType Container)) {
        throw 'Package payload directory is missing.'
    }
    $actualPayloadCount = 0
    foreach ($file in Get-ChildItem -LiteralPath $payloadRoot -Recurse -File -Force) {
        $actualRelative = $file.FullName.Substring($PackageRoot.Length + 1).Replace('\', '/')
        if (-not $expectedPayloadFiles.ContainsKey($actualRelative.ToLowerInvariant())) {
            throw "Unlisted package payload file found: $actualRelative"
        }
        $actualPayloadCount++
    }
    if ($actualPayloadCount -ne $expectedPayloadFiles.Count) {
        throw 'Package payload file set does not match SHA256SUMS.txt.'
    }

    Write-Host "Package integrity verified: $checked files."
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

function Invoke-DownloadWithFallback {
    param(
        [string]$Uri,
        [string]$OutFile,
        [string]$ExpectedSha256
    )

    $attempts = @(
        @{ Name = 'system/default network'; Proxy = $null },
        @{ Name = 'local proxy 127.0.0.1:12334'; Proxy = 'http://127.0.0.1:12334' },
        @{ Name = 'local proxy 127.0.0.1:7890'; Proxy = 'http://127.0.0.1:7890' }
    )
    $errors = New-Object 'System.Collections.Generic.List[string]'

    foreach ($attempt in $attempts) {
        if (Test-Path -LiteralPath $OutFile) {
            Remove-Item -LiteralPath $OutFile -Force
        }
        try {
            Write-Host "Downloading with $($attempt.Name)..."
            $parameters = @{
                UseBasicParsing = $true
                Uri = $Uri
                OutFile = $OutFile
                TimeoutSec = 30
            }
            if ($null -ne $attempt.Proxy) { $parameters.Proxy = $attempt.Proxy }
            Invoke-WebRequest @parameters
            $actualHash = Get-Sha256 -Path $OutFile
            if ($actualHash -ne $ExpectedSha256) {
                throw "Downloaded file SHA-256 mismatch: $actualHash"
            }
            return
        }
        catch {
            $errors.Add("$($attempt.Name): $($_.Exception.Message)")
        }
    }

    throw "All download attempts failed. $($errors -join ' | ')"
}

function Write-YierPreference {
    param([string]$PreferPath, [string]$OfficialListPath)

    $utf8NoBom = New-Object Text.UTF8Encoding($false)
    $result = New-Object 'System.Collections.Generic.List[string]'
    $hasLobbySwitch = $false

    if (Test-Path -LiteralPath $PreferPath -PathType Leaf) {
        foreach ($line in [IO.File]::ReadAllLines($PreferPath)) {
            if ($line -match '^\s*174-yier(?:\s|$)') { continue }
            if ($line -match '^\s*LOBBYSWITCHCHEF=') {
                if (-not $hasLobbySwitch) {
                    while ($result.Count -gt 0 -and [string]::IsNullOrWhiteSpace($result[$result.Count - 1])) {
                        $result.RemoveAt($result.Count - 1)
                    }
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
    param([string]$PluginsDirectory)

    $expectedArchiveHash = 'E38A0589C35B726C7B3D5886163D3267E71534F0DB883FC66E6495AAEADF0220'
    $expectedDllHash = 'E9663293FCC8C4CFFAD75D4F78211406D12E1DC5ED12B9F7B88EBA4D0EE2B022'
    $canonicalDll = [IO.Path]::GetFullPath(
        (Join-Path $PluginsDirectory 'OC2HostUtilities\v1.8.0\HostUtilities.dll'))
    $existing = @(Get-ChildItem -LiteralPath $PluginsDirectory -Filter 'HostUtilities.dll' -Recurse -File -ErrorAction SilentlyContinue)
    $matching = $null
    foreach ($candidate in $existing) {
        if ((Get-Sha256 -Path $candidate.FullName) -eq $expectedDllHash -and
            [string]::Equals(
                [IO.Path]::GetFullPath($candidate.FullName),
                $canonicalDll,
                [StringComparison]::OrdinalIgnoreCase)) {
            $matching = $candidate
        }
    }
    if ($existing.Count -eq 1 -and $null -ne $matching) {
        Write-Host "HostUtilities 1.8.0 already present: $($matching.FullName)"
        return $true
    }
    if ($existing.Count -gt 0) {
        Write-Warning 'Another or duplicate HostUtilities build is installed. Skipping trail-colour installation to avoid duplicate plugin GUIDs.'
        return $false
    }

    $downloadRoot = $null
    try {
        $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
        $downloadRoot = [IO.Path]::GetFullPath(
            (Join-Path $tempRoot ('YierPackage-' + [Guid]::NewGuid().ToString('N'))))
        if (-not $downloadRoot.StartsWith($tempRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Temporary download path escaped the temp directory: $downloadRoot"
        }
        New-Item -ItemType Directory -Path $downloadRoot | Out-Null
        $archive = Join-Path $downloadRoot 'HostUtilities.Core.zip'
        $expanded = Join-Path $downloadRoot 'expanded'
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        Invoke-DownloadWithFallback `
            -Uri 'https://github.com/CH3NGYZ/Overcooked-2-HostUtilities-Stable-Releases/releases/download/v1.8.0/HostUtilities.Core.zip' `
            -OutFile $archive `
            -ExpectedSha256 $expectedArchiveHash
        $actualArchiveHash = Get-Sha256 -Path $archive
        if ($actualArchiveHash -ne $expectedArchiveHash) {
            throw "HostUtilities archive SHA-256 mismatch: $actualArchiveHash"
        }
        Expand-Archive -LiteralPath $archive -DestinationPath $expanded
        $dlls = @(Get-ChildItem -LiteralPath $expanded -Filter 'HostUtilities.dll' -Recurse -File)
        if ($dlls.Count -ne 1) { throw "Expected one HostUtilities.dll, found $($dlls.Count)" }
        $actualDllHash = Get-Sha256 -Path $dlls[0].FullName
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
    finally {
        if ($null -ne $downloadRoot -and (Test-Path -LiteralPath $downloadRoot)) {
            Remove-Item -LiteralPath $downloadRoot -Recurse -Force
        }
    }
}

function Install-AsyncLevelLoader {
    param(
        [string]$GameRoot,
        [string]$PayloadRoot,
        [string]$BackupRoot
    )

    $expectedOriginalHash = '18387FF6923281198518D67EDDA3B8E728A4E5AA7407104E03A1F0AC82811D06'
    $expectedStubHash = '28155A7CBF359D6C8900C76F369BB224971A77F3CAE74FB8846717EFBD4B15D1'
    $originalRoot = Join-Path $GameRoot 'BepInEx\plugins\OC2DIYLevel'
    $originalDll = Join-Path $originalRoot 'OC2DIYLevel.dll'
    $stubDll = Join-Path $originalRoot 'LevelEditorStub.dll'
    if (-not (Test-Path -LiteralPath $originalDll -PathType Leaf)) {
        Write-Warning 'OC2DIYLevel.dll was not found; asynchronous level support was not installed.'
        return $false
    }
    if (-not (Test-Path -LiteralPath $stubDll -PathType Leaf)) {
        Write-Warning 'OC2DIYLevel is incomplete (LevelEditorStub.dll is missing); asynchronous level support was not installed.'
        return $false
    }
    if (-not (Test-Path -LiteralPath (Join-Path $originalRoot 'common') -PathType Leaf)) {
        Write-Warning 'OC2DIYLevel is incomplete (common is missing); asynchronous level support was not installed.'
        return $false
    }

    $actualOriginalHash = Get-Sha256 -Path $originalDll
    if ($actualOriginalHash -ne $expectedOriginalHash) {
        Write-Warning "Unsupported OC2DIYLevel.dll SHA-256: $actualOriginalHash. Expected exact 0.9.0; asynchronous level support was not installed."
        return $false
    }
    $actualStubHash = Get-Sha256 -Path $stubDll
    if ($actualStubHash -ne $expectedStubHash) {
        Write-Warning "Unsupported LevelEditorStub.dll SHA-256: $actualStubHash. Expected the verified OC2DIYLevel 0.9.0 dependency; asynchronous level support was not installed."
        return $false
    }

    $pluginsRoot = Join-Path $GameRoot 'BepInEx\plugins'
    $targetRoot = Join-Path $pluginsRoot 'OC2DIYLevelAsyncLoader'
    Move-ToBackup -SourcePath $targetRoot -GameRoot $GameRoot -BackupRoot $BackupRoot
    Copy-DirectoryContents `
        -Source (Join-Path $PayloadRoot 'OC2DIYLevelAsyncLoader') `
        -Destination $targetRoot

    $configTarget = Join-Path $GameRoot 'BepInEx\config\dukey.oc2.diylevel.asyncloader.cfg'
    if (-not (Test-Path -LiteralPath $configTarget -PathType Leaf)) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $configTarget) -Force | Out-Null
        Copy-Item `
            -LiteralPath (Join-Path $PayloadRoot 'config\dukey.oc2.diylevel.asyncloader.cfg') `
            -Destination $configTarget
    }

    Write-Host 'Installed OC2DIYLevelAsyncLoader for verified OC2DIYLevel 0.9.0.'
    return $true
}

$packageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$payloadRoot = Join-Path $packageRoot 'payload'
Assert-PackageIntegrity -PackageRoot $packageRoot

$versionPath = Join-Path $packageRoot 'PACKAGE-VERSION.txt'
if (-not (Test-Path -LiteralPath $versionPath -PathType Leaf)) {
    throw 'PACKAGE-VERSION.txt is missing.'
}
$packageVersion = [IO.File]::ReadAllText($versionPath).Trim()
if ($packageVersion -notmatch '^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$') {
    throw "Invalid package version: $packageVersion"
}

foreach ($required in @(
    'BepInEx-x86',
    'OC2DIYChef\OC2DIYChef.dll',
    'OC2DIYChef\official-all.txt',
    'Resources\174-yier',
    'Resources\HATS\YierCap',
    'TrailColor\OC2DIYChefTrailColor.dll',
    'TrailColor\OC2DIYChefTrailColorGUI.dll',
    'OC2DIYLevelAsyncLoader\OC2DIYLevelAsyncLoader.dll',
    'config\local.oc2.diycheftrailcolor.cfg',
    'config\dukey.oc2.diylevel.asyncloader.cfg'
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

$bepInExDll = Join-Path $gameRoot 'BepInEx\core\BepInEx.dll'
if (-not (Test-Path -LiteralPath $bepInExDll -PathType Leaf)) {
    $partialBepInEx = @(@(
        (Join-Path $gameRoot 'winhttp.dll'),
        (Join-Path $gameRoot 'doorstop_config.ini'),
        (Join-Path $gameRoot 'BepInEx')
    ) | Where-Object { Test-Path -LiteralPath $_ })
    if ($partialBepInEx.Count -gt 0) {
        throw 'A partial or damaged BepInEx installation already exists. Repair or remove it before running this package; no core files were overwritten.'
    }
    Copy-Item `
        -LiteralPath (Join-Path $payloadRoot 'BepInEx-x86\winhttp.dll') `
        -Destination (Join-Path $gameRoot 'winhttp.dll')
    Copy-Item `
        -LiteralPath (Join-Path $payloadRoot 'BepInEx-x86\doorstop_config.ini') `
        -Destination (Join-Path $gameRoot 'doorstop_config.ini')
    Copy-DirectoryContents `
        -Source (Join-Path $payloadRoot 'BepInEx-x86\BepInEx') `
        -Destination (Join-Path $gameRoot 'BepInEx')
    Write-Host 'Installed BepInEx 5.4.22 x86.'
}
else {
    $bepInExVersion = Assert-CompatibleBepInEx -GameRoot $gameRoot
    Write-Host "Compatible BepInEx $bepInExVersion x86 detected; core files were left unchanged."
}

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

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
    if (Ensure-HostUtilities -PluginsDirectory $pluginsRoot) {
        $trailTarget = Join-Path $pluginsRoot 'OC2DIYChefTrailColor'
        Move-ToBackup -SourcePath $trailTarget -GameRoot $gameRoot -BackupRoot $backupRoot
        Copy-DirectoryContents -Source (Join-Path $payloadRoot 'TrailColor') -Destination $trailTarget
        $configTarget = Join-Path $gameRoot 'BepInEx\config\local.oc2.diycheftrailcolor.cfg'
        if (-not (Test-Path -LiteralPath $configTarget -PathType Leaf)) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $configTarget) -Force | Out-Null
            Copy-Item -LiteralPath (Join-Path $payloadRoot 'config\local.oc2.diycheftrailcolor.cfg') -Destination $configTarget
        }
        $trailInstalled = $true
    }
}

$asyncLevelInstalled = Install-AsyncLevelLoader `
    -GameRoot $gameRoot `
    -PayloadRoot $payloadRoot `
    -BackupRoot $backupRoot

$receipt = @(
    "Package=Yier-OC2DIYChef-v$packageVersion",
    'Author=DUKEY',
    "InstalledAt=$([DateTime]::Now.ToString('o'))",
    "GameDir=$gameRoot",
    "BackupDir=$backupRoot",
    "TrailColorInstalled=$trailInstalled",
    "AsyncLevelLoaderInstalled=$asyncLevelInstalled",
    'Hat=YierCap'
)
[IO.File]::WriteAllLines((Join-Path $backupRoot 'INSTALL-RECEIPT.txt'), $receipt, (New-Object Text.UTF8Encoding($false)))

Write-Host ''
Write-Host 'Yier installation completed.' -ForegroundColor Green
Write-Host "Package: v$packageVersion"
Write-Host 'Author: DUKEY'
Write-Host "Game: $gameRoot"
Write-Host "Backup: $backupRoot"
Write-Host 'Preference: 174-yier HAT=YierCap'
if ($trailInstalled) { Write-Host 'Trail colour GUI: installed (press F10 in game)' }
elseif ($SkipTrailColor) { Write-Host 'Trail colour GUI: skipped by request' }
else { Write-Host 'Trail colour GUI: not installed; see warnings above' }
if ($asyncLevelInstalled) { Write-Host 'Async level loader: installed (progress shown on the title screen)' }
else { Write-Host 'Async level loader: not installed; compatible OC2DIYLevel 0.9.0 was not detected' }
