[CmdletBinding()]
param(
    [string]$Path,
    [switch]$RequireHats,
    [int]$MaxFaceCorners = 65534,
    [int]$RecommendedTextureSize = 512
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:ErrorCount = 0
$script:WarningCount = 0

if ([string]::IsNullOrWhiteSpace($Path)) {
    $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    $Path = Join-Path $scriptDirectory '..\exports\Resources\HATS'
}

function Add-Result {
    param(
        [ValidateSet('ERROR', 'WARN', 'INFO')][string]$Level,
        [string]$Message
    )
    if ($Level -eq 'ERROR') { $script:ErrorCount++ }
    elseif ($Level -eq 'WARN') { $script:WarningCount++ }
    Write-Host ('[{0}] {1}' -f $Level, $Message)
}

function Get-PngInfo {
    param([string]$FilePath)
    $stream = [IO.File]::Open($FilePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $bytes = New-Object byte[] 24
        if ($stream.Read($bytes, 0, 24) -lt 24) {
            return [pscustomobject]@{ Valid = $false; Width = 0; Height = 0; Reason = 'short PNG header' }
        }
        $signature = @(137, 80, 78, 71, 13, 10, 26, 10)
        for ($i = 0; $i -lt $signature.Count; $i++) {
            if ($bytes[$i] -ne $signature[$i]) {
                return [pscustomobject]@{ Valid = $false; Width = 0; Height = 0; Reason = 'invalid PNG signature' }
            }
        }
        if ($bytes[12] -ne 73 -or $bytes[13] -ne 72 -or $bytes[14] -ne 68 -or $bytes[15] -ne 82) {
            return [pscustomobject]@{ Valid = $false; Width = 0; Height = 0; Reason = 'missing IHDR' }
        }
        $width = [uint32]([uint64]$bytes[16] * 16777216 + [uint64]$bytes[17] * 65536 + [uint64]$bytes[18] * 256 + [uint64]$bytes[19])
        $height = [uint32]([uint64]$bytes[20] * 16777216 + [uint64]$bytes[21] * 65536 + [uint64]$bytes[22] * 256 + [uint64]$bytes[23])
        return [pscustomobject]@{ Valid = ($width -gt 0 -and $height -gt 0); Width = $width; Height = $height; Reason = 'invalid dimensions' }
    }
    finally {
        $stream.Dispose()
    }
}

function Get-ObjStats {
    param([string]$FilePath)
    $vertices = 0
    $uvs = 0
    $normals = 0
    $faces = 0
    $corners = 0
    $invalid = 0
    $whitespace = 0
    $maxVertex = 0
    $maxUv = 0
    $maxNormal = 0
    foreach ($line in [IO.File]::ReadLines($FilePath)) {
        $trimmed = $line.Trim()
        if ($trimmed -notmatch '^(v|vt|vn|f)\s+(.+)$') { continue }
        $kind = $Matches[1]
        $payload = $Matches[2]
        if ($line -cne (($trimmed -split '\s+') -join ' ')) { $whitespace++ }
        $tokens = @($payload -split '\s+')
        switch ($kind) {
            'v' { $vertices++; if ($tokens.Count -lt 3) { $invalid++ } }
            'vt' { $uvs++; if ($tokens.Count -lt 2) { $invalid++ } }
            'vn' { $normals++; if ($tokens.Count -lt 3) { $invalid++ } }
            'f' {
                $faces++
                $corners += $tokens.Count
                if ($tokens.Count -ne 3) { $invalid++ }
                foreach ($token in $tokens) {
                    if ($token -notmatch '^([1-9][0-9]*)/([1-9][0-9]*)/([1-9][0-9]*)$') {
                        $invalid++
                        continue
                    }
                    $vertex = [int64]$Matches[1]
                    $uv = [int64]$Matches[2]
                    $normal = [int64]$Matches[3]
                    if ($vertex -gt $maxVertex) { $maxVertex = $vertex }
                    if ($uv -gt $maxUv) { $maxUv = $uv }
                    if ($normal -gt $maxNormal) { $maxNormal = $normal }
                }
            }
        }
    }
    $outOfRange = ($maxVertex -gt $vertices -or $maxUv -gt $uvs -or $maxNormal -gt $normals)
    return [pscustomobject]@{
        Vertices = $vertices
        UVs = $uvs
        Normals = $normals
        Faces = $faces
        FaceCorners = $corners
        Invalid = $invalid
        Whitespace = $whitespace
        OutOfRange = $outOfRange
    }
}

$normalized = [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
if (-not (Test-Path -LiteralPath $normalized -PathType Container)) {
    Add-Result ERROR "HATS path does not exist: $normalized"
    Write-Host ("SUMMARY hats=0 errors={0} warnings={1}" -f $script:ErrorCount, $script:WarningCount)
    exit 1
}

$rootItem = Get-Item -LiteralPath $normalized -ErrorAction Stop
$rootFiles = @(Get-ChildItem -LiteralPath $rootItem.FullName -File -ErrorAction Stop)
$rootLooksLikeHat = @($rootFiles | Where-Object {
    $_.Name -ceq "$($rootItem.Name).obj" -or
    $_.Name -ceq "t_$($rootItem.Name).png" -or
    $_.Name -ceq "m_$($rootItem.Name).txt"
}).Count -gt 0
if ($rootLooksLikeHat) {
    $hats = @($rootItem)
}
else {
    $hats = @(Get-ChildItem -LiteralPath $normalized -Directory -ErrorAction Stop | Sort-Object Name)
}
if ($hats.Count -eq 0) {
    if ($RequireHats) { Add-Result ERROR "No hat packages found under $normalized" }
    else { Add-Result INFO "No hat packages found" }
}

$summary = @()
foreach ($hat in $hats) {
    Write-Host ''
    Write-Host ("== {0} ==" -f $hat.FullName)
    $required = @(
        "$($hat.Name).obj",
        "t_$($hat.Name).png",
        "m_$($hat.Name).txt"
    )
    $files = @(Get-ChildItem -LiteralPath $hat.FullName -File -ErrorAction Stop)
    foreach ($name in $required) {
        $exact = @($files | Where-Object { $_.Name -ceq $name })
        if ($exact.Count -ne 1) {
            $caseMatch = @($files | Where-Object { $_.Name -ieq $name })
            if ($caseMatch.Count -gt 0) { Add-Result ERROR "$($hat.Name): filename case mismatch; expected $name" }
            else { Add-Result ERROR "$($hat.Name): missing $name" }
        }
    }
    $nested = @(Get-ChildItem -LiteralPath $hat.FullName -Recurse -File -ErrorAction Stop | Where-Object { $_.DirectoryName -ne $hat.FullName })
    if ($nested.Count -gt 0) { Add-Result ERROR "$($hat.Name): nested files are not supported" }

    $objPath = Join-Path $hat.FullName "$($hat.Name).obj"
    if (Test-Path -LiteralPath $objPath -PathType Leaf) {
        $stats = Get-ObjStats -FilePath $objPath
        if ($stats.Vertices -eq 0 -or $stats.UVs -eq 0 -or $stats.Normals -eq 0 -or $stats.Faces -eq 0) {
            Add-Result ERROR "$($hat.Name): OBJ is empty or lacks v/vt/vn/f data"
        }
        if ($stats.Invalid -gt 0 -or $stats.OutOfRange) {
            Add-Result ERROR "$($hat.Name): invalid OBJ data (invalid=$($stats.Invalid), outOfRange=$($stats.OutOfRange))"
        }
        if ($stats.Whitespace -gt 0) { Add-Result ERROR "$($hat.Name): OBJ data contains importer-unsafe whitespace" }
        if ($stats.FaceCorners -gt $MaxFaceCorners) { Add-Result ERROR "$($hat.Name): face-corners exceed $MaxFaceCorners" }
        $summary += [pscustomobject]@{
            Hat = $hat.Name
            v = $stats.Vertices
            vt = $stats.UVs
            vn = $stats.Normals
            Triangles = $stats.Faces
            FaceCorners = $stats.FaceCorners
        }
    }

    $pngPath = Join-Path $hat.FullName "t_$($hat.Name).png"
    if (Test-Path -LiteralPath $pngPath -PathType Leaf) {
        $png = Get-PngInfo -FilePath $pngPath
        if (-not $png.Valid) { Add-Result ERROR "$($hat.Name): invalid PNG ($($png.Reason))" }
        elseif ($png.Width -ne $RecommendedTextureSize -or $png.Height -ne $RecommendedTextureSize) {
            Add-Result WARN "$($hat.Name): texture is $($png.Width)x$($png.Height), expected ${RecommendedTextureSize}x${RecommendedTextureSize}"
        }
    }

    $materialPath = Join-Path $hat.FullName "m_$($hat.Name).txt"
    if (Test-Path -LiteralPath $materialPath -PathType Leaf) {
        $materialLines = @([IO.File]::ReadAllLines($materialPath) | Where-Object { $_.Contains('=') })
        if ($materialLines.Count -eq 0) { Add-Result ERROR "$($hat.Name): material file has no key=value parameters" }
    }
}

if ($summary.Count -gt 0) {
    $summary | Format-Table -AutoSize | Out-String -Width 180 | Write-Host
}
Write-Host ("SUMMARY hats={0} errors={1} warnings={2}" -f $hats.Count, $script:ErrorCount, $script:WarningCount)
if ($script:ErrorCount -gt 0) { exit 1 }
exit 0
