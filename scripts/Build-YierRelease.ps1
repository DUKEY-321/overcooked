[CmdletBinding()]
param(
    [string]$Version = '0.4.0-test',
    [string]$DistDir,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ([string]::IsNullOrWhiteSpace($DistDir)) {
    $DistDir = Join-Path $projectRoot 'dist'
}
$distRoot = [IO.Path]::GetFullPath($DistDir).TrimEnd('\', '/')
$packageName = "Yier-OC2DIYChef-v$Version"
$stagingRoot = [IO.Path]::GetFullPath((Join-Path $distRoot 'staging'))
$packageRoot = [IO.Path]::GetFullPath((Join-Path $stagingRoot $packageName))
$zipPath = [IO.Path]::GetFullPath((Join-Path $distRoot ($packageName + '.zip')))
$cacheRoot = [IO.Path]::GetFullPath((Join-Path $distRoot 'cache'))

foreach ($path in @($stagingRoot, $packageRoot, $zipPath, $cacheRoot)) {
    if (-not $path.StartsWith($distRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Release path escaped DistDir: $path"
    }
}

if (Test-Path -LiteralPath $packageRoot) {
    if (-not $Force) { throw "Staging package exists: $packageRoot (use -Force to rebuild)" }
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
}
if (Test-Path -LiteralPath $zipPath) {
    if (-not $Force) { throw "Release ZIP exists: $zipPath (use -Force to rebuild)" }
    Remove-Item -LiteralPath $zipPath -Force
}
New-Item -ItemType Directory -Path $packageRoot,$cacheRoot -Force | Out-Null

function Get-VerifiedDownload {
    param([string]$Uri, [string]$Path, [string]$ExpectedSha256)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Invoke-WebRequest -Uri $Uri -OutFile $Path
    }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $ExpectedSha256) {
        throw "SHA-256 mismatch for $Path. Expected $ExpectedSha256, got $actual"
    }
    return $Path
}

function Copy-DirectoryContents {
    param([string]$Source, [string]$Destination)

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
    }
}

$bepZip = Get-VerifiedDownload `
    -Uri 'https://github.com/BepInEx/BepInEx/releases/download/v5.4.22/BepInEx_x86_5.4.22.0.zip' `
    -Path (Join-Path $cacheRoot 'BepInEx_x86_5.4.22.0.zip') `
    -ExpectedSha256 'EA9ACBE27F8F195B2E7572AD7A8069A96DB0C3C98A591AE9B0EB8C4EE319FBC0'
$diyDll = Get-VerifiedDownload `
    -Uri 'https://raw.githubusercontent.com/gua248/Overcooked2-DIYChef/93ab0554/bin/Release/OC2DIYChef.dll' `
    -Path (Join-Path $cacheRoot 'OC2DIYChef-93ab0554.dll') `
    -ExpectedSha256 '9C696BD6CEDA7E76B6B8009E337DF428546C452C9B9E3A3CC25B742D9872E51E'
$officialList = Get-VerifiedDownload `
    -Uri 'https://raw.githubusercontent.com/gua248/Overcooked2-DIYChef/93ab0554/official-all.txt' `
    -Path (Join-Path $cacheRoot 'official-all-93ab0554.txt') `
    -ExpectedSha256 '507A998700B65227CA98F5C8B4DD2CC1862154E0660E1988B2257F22F483CAC0'
$diyLicense = Get-VerifiedDownload `
    -Uri 'https://raw.githubusercontent.com/gua248/Overcooked2-DIYChef/93ab0554/LICENSE' `
    -Path (Join-Path $cacheRoot 'OC2DIYChef-LICENSE.txt') `
    -ExpectedSha256 'A406579CD136771C705C521DB86CA7D60A6F3DE7C9B5460E6193A2DF27861BDE'
$bepLicense = Get-VerifiedDownload `
    -Uri 'https://raw.githubusercontent.com/BepInEx/BepInEx/v5.4.22/LICENSE' `
    -Path (Join-Path $cacheRoot 'BepInEx-LICENSE.txt') `
    -ExpectedSha256 'E6E534EF6F4347B6449407EE046A3D09CB0174C6F688C996AD0BED94B74B3933'

$bepPayload = Join-Path $packageRoot 'payload\BepInEx-x86'
Expand-Archive -LiteralPath $bepZip -DestinationPath $bepPayload

$diyPayload = Join-Path $packageRoot 'payload\OC2DIYChef'
New-Item -ItemType Directory -Path $diyPayload -Force | Out-Null
Copy-Item -LiteralPath $diyDll -Destination (Join-Path $diyPayload 'OC2DIYChef.dll')
Copy-Item -LiteralPath $officialList -Destination (Join-Path $diyPayload 'official-all.txt')

$resourcesPayload = Join-Path $packageRoot 'payload\Resources'
Copy-DirectoryContents -Source (Join-Path $projectRoot 'exports\Resources\174-yier') -Destination (Join-Path $resourcesPayload '174-yier')
Copy-DirectoryContents -Source (Join-Path $projectRoot 'exports\Resources\HATS\YierCap') -Destination (Join-Path $resourcesPayload 'HATS\YierCap')

$trailPayload = Join-Path $packageRoot 'payload\TrailColor'
New-Item -ItemType Directory -Path $trailPayload -Force | Out-Null
foreach ($source in @(
    (Join-Path $projectRoot 'mods\OC2DIYChefTrailColor\Core\bin\Release\OC2DIYChefTrailColor.dll'),
    (Join-Path $projectRoot 'mods\OC2DIYChefTrailColor\GUI\bin\Release\OC2DIYChefTrailColorGUI.dll')
)) {
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing built trail plugin: $source" }
    Copy-Item -LiteralPath $source -Destination $trailPayload
}
Copy-Item -LiteralPath (Join-Path $projectRoot 'packaging\yier\default-trail-color.cfg') -Destination (Join-Path $packageRoot 'payload\default-trail-color.cfg')

Copy-Item -LiteralPath (Join-Path $projectRoot 'packaging\yier\README.md') -Destination (Join-Path $packageRoot 'README.md')
Copy-Item -LiteralPath (Join-Path $projectRoot 'packaging\yier\Install-Yier.ps1') -Destination (Join-Path $packageRoot 'Install-Yier.ps1')
Copy-Item -LiteralPath (Join-Path $projectRoot 'LICENSE') -Destination (Join-Path $packageRoot 'LICENSE')
Copy-Item -LiteralPath (Join-Path $projectRoot 'THIRD_PARTY_NOTICES.md') -Destination (Join-Path $packageRoot 'THIRD_PARTY_NOTICES.md')

$licensesRoot = Join-Path $packageRoot 'licenses'
New-Item -ItemType Directory -Path $licensesRoot -Force | Out-Null
Copy-Item -LiteralPath $diyLicense -Destination (Join-Path $licensesRoot 'OC2DIYChef-MIT.txt')
Copy-Item -LiteralPath $bepLicense -Destination (Join-Path $licensesRoot 'BepInEx-MIT.txt')
Copy-Item -LiteralPath (Join-Path $projectRoot 'LICENSES\yier-sketchfab-b15f13be.md') -Destination (Join-Path $licensesRoot 'Yier-CC-BY-4.0-Attribution.md')
Copy-Item -LiteralPath (Join-Path $projectRoot 'LICENSES\DISTRIBUTION_NOTICE.md') -Destination (Join-Path $licensesRoot 'DISTRIBUTION_NOTICE.md')

$sumLines = New-Object 'System.Collections.Generic.List[string]'
foreach ($file in Get-ChildItem -LiteralPath $packageRoot -Recurse -File | Sort-Object FullName) {
    if ($file.Name -eq 'SHA256SUMS.txt') { continue }
    $relative = $file.FullName.Substring($packageRoot.Length + 1).Replace('\', '/')
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    $sumLines.Add($hash + '  ' + $relative)
}
[IO.File]::WriteAllLines((Join-Path $packageRoot 'SHA256SUMS.txt'), $sumLines.ToArray(), (New-Object Text.UTF8Encoding($false)))

Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal
$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash
Write-Host "PACKAGE=$packageRoot"
Write-Host "ZIP=$zipPath"
Write-Host "ZIP_SHA256=$zipHash"
Write-Host "FILES=$((Get-ChildItem -LiteralPath $packageRoot -Recurse -File).Count)"
