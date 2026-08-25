[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Path,

    [string]$ExistingResourcesPath,

    [switch]$RequirePackages,

    [ValidateRange(3, 2147483647)]
    [int]$MaxFaceCorners = 65534,

    [ValidateRange(1, 32768)]
    [int]$RecommendedTextureSize = 512
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:ValidationErrorCount = 0
$script:ValidationWarningCount = 0

if ([string]::IsNullOrWhiteSpace($Path)) {
    $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    $Path = Join-Path $scriptDirectory '..\exports\Resources'
}

$requiredFiles = @(
    'INFO',
    'Head.obj',
    'Hand_Grip_L.obj',
    'Hand_Grip_R.obj',
    'Hand_Open_L.obj',
    'Hand_Open_R.obj',
    't_Head.png',
    'm_Head.txt'
)

$requiredObjNames = @(
    'Head.obj',
    'Hand_Grip_L.obj',
    'Hand_Grip_R.obj',
    'Hand_Open_L.obj',
    'Hand_Open_R.obj'
)

$allowedObjNames = @(
    'Eyes.obj',
    'Eyebrows.obj',
    'Eyes2_Blinks.obj',
    'Hand_Grip_L.obj',
    'Hand_Grip_R.obj',
    'Hand_Open_L.obj',
    'Hand_Open_R.obj',
    'Tail.obj',
    'Head.obj',
    'Head1.obj',
    'Head2.obj',
    'Body_NeckTie.obj',
    'Body_Top.obj',
    'Body_Bottom.obj',
    'Body_Tail.obj',
    'Body_Body.obj',
    'Wheelchair.obj',
    'Knife.obj'
)

function Add-ValidationMessage {
    param(
        [ValidateSet('ERROR', 'WARN', 'INFO')]
        [string]$Level,
        [string]$Message
    )

    if ($Level -eq 'ERROR') {
        $script:ValidationErrorCount++
    }
    elseif ($Level -eq 'WARN') {
        $script:ValidationWarningCount++
    }

    Write-Host ('[{0}] {1}' -f $Level, $Message)
}

function Get-NormalizedPath {
    param([string]$LiteralPath)

    return [System.IO.Path]::GetFullPath($LiteralPath).TrimEnd('\', '/')
}

function Get-ResourcePackages {
    param([string]$RootPath)

    $rootItem = Get-Item -LiteralPath $RootPath -ErrorAction Stop
    if (-not $rootItem.PSIsContainer) {
        throw "Path must be a directory: $RootPath"
    }

    $rootFiles = @(Get-ChildItem -LiteralPath $rootItem.FullName -File -ErrorAction Stop)
    $rootLooksLikePackage = @($rootFiles | Where-Object {
        $_.Name -ceq 'INFO' -or $_.Extension -ieq '.obj' -or
        $_.Name -ceq 't_Head.png' -or $_.Name -ceq 'm_Head.txt'
    }).Count -gt 0

    if ($rootLooksLikePackage) {
        return @($rootItem)
    }

    $result = @()
    foreach ($directory in @(Get-ChildItem -LiteralPath $rootItem.FullName -Directory -ErrorAction Stop)) {
        if ($directory.Name -ieq 'HATS') {
            continue
        }

        $markers = @(Get-ChildItem -LiteralPath $directory.FullName -File -ErrorAction Stop | Where-Object {
            $_.Name -ceq 'INFO' -or $_.Extension -ieq '.obj' -or
            $_.Extension -ieq '.png' -or $_.Extension -ieq '.txt'
        })
        if ($markers.Count -gt 0) {
            $result += $directory
        }
    }

    return @($result)
}

function Get-PngInfo {
    param([string]$FilePath)

    $stream = [System.IO.File]::Open($FilePath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    try {
        $bytes = New-Object byte[] 24
        $read = $stream.Read($bytes, 0, $bytes.Length)
        if ($read -lt 24) {
            return [pscustomobject]@{ Valid = $false; Width = 0; Height = 0; Reason = 'File is shorter than the PNG header' }
        }

        $signature = @(137, 80, 78, 71, 13, 10, 26, 10)
        for ($i = 0; $i -lt $signature.Count; $i++) {
            if ($bytes[$i] -ne $signature[$i]) {
                return [pscustomobject]@{ Valid = $false; Width = 0; Height = 0; Reason = 'Invalid PNG signature' }
            }
        }

        if ($bytes[12] -ne 73 -or $bytes[13] -ne 72 -or $bytes[14] -ne 68 -or $bytes[15] -ne 82) {
            return [pscustomobject]@{ Valid = $false; Width = 0; Height = 0; Reason = 'Missing PNG IHDR chunk' }
        }

        $width = [uint64]$bytes[16] * 16777216 + [uint64]$bytes[17] * 65536 + [uint64]$bytes[18] * 256 + [uint64]$bytes[19]
        $height = [uint64]$bytes[20] * 16777216 + [uint64]$bytes[21] * 65536 + [uint64]$bytes[22] * 256 + [uint64]$bytes[23]
        if ($width -eq 0 -or $height -eq 0 -or $width -gt [uint32]::MaxValue -or $height -gt [uint32]::MaxValue) {
            return [pscustomobject]@{ Valid = $false; Width = 0; Height = 0; Reason = 'Invalid PNG dimensions' }
        }

        return [pscustomobject]@{ Valid = $true; Width = [uint32]$width; Height = [uint32]$height; Reason = '' }
    }
    finally {
        $stream.Dispose()
    }
}

function Test-PowerOfTwo {
    param([uint32]$Value)

    return $Value -gt 0 -and (($Value -band ($Value - 1)) -eq 0)
}

function Get-PositiveIndex {
    param([string]$Text)

    $number = 0
    if (-not [int]::TryParse($Text, [ref]$number) -or $number -le 0) {
        return $null
    }
    return $number
}

function Get-ObjStats {
    param([string]$FilePath)

    $vertices = 0
    $textureCoordinates = 0
    $normals = 0
    $faces = 0
    $faceCorners = 0
    $triangles = 0
    $invalidDataLines = 0
    $invalidFaces = 0
    $invalidCorners = 0
    $unsupportedCorners = 0
    $whitespaceProblems = 0
    $maxVertexReference = 0
    $maxTextureReference = 0
    $maxNormalReference = 0
    $lineNumber = 0

    foreach ($line in [System.IO.File]::ReadLines($FilePath)) {
        $lineNumber++
        $trimmed = $line.Trim()
        if ($trimmed -notmatch '^(v|vt|vn|f)\s+(.+)$') {
            continue
        }

        $kind = $Matches[1]
        $payload = $Matches[2]
        $normalizedLine = (($trimmed -split '\s+') -join ' ')
        if ($line -cne $normalizedLine) {
            $whitespaceProblems++
        }
        $tokens = @($payload -split '\s+')

        switch ($kind) {
            'v' {
                $vertices++
                if ($tokens.Count -lt 3) { $invalidDataLines++ }
            }
            'vt' {
                $textureCoordinates++
                if ($tokens.Count -lt 2) { $invalidDataLines++ }
            }
            'vn' {
                $normals++
                if ($tokens.Count -lt 3) { $invalidDataLines++ }
            }
            'f' {
                $faces++
                $cornerCount = $tokens.Count
                $faceCorners += $cornerCount
                if ($cornerCount -lt 3) {
                    $invalidFaces++
                }
                else {
                    $triangles += $cornerCount - 2
                }

                foreach ($corner in $tokens) {
                    $parts = $corner.Split([char[]]@('/'), [System.StringSplitOptions]::None)
                    if ($parts.Count -ne 1 -and $parts.Count -ne 3) {
                        # The bundled importer cannot safely read v/vt; use v or v/vt/vn (v//vn is allowed).
                        $unsupportedCorners++
                        continue
                    }

                    $vertexIndex = Get-PositiveIndex -Text $parts[0]
                    if ($null -eq $vertexIndex) {
                        $invalidCorners++
                        continue
                    }
                    if ($vertexIndex -gt $maxVertexReference) { $maxVertexReference = $vertexIndex }

                    if ($parts.Count -eq 3) {
                        if ($parts[1].Length -gt 0) {
                            $textureIndex = Get-PositiveIndex -Text $parts[1]
                            if ($null -eq $textureIndex) { $invalidCorners++ }
                            elseif ($textureIndex -gt $maxTextureReference) { $maxTextureReference = $textureIndex }
                        }

                        $normalIndex = Get-PositiveIndex -Text $parts[2]
                        if ($null -eq $normalIndex) { $invalidCorners++ }
                        elseif ($normalIndex -gt $maxNormalReference) { $maxNormalReference = $normalIndex }
                    }
                }
            }
        }
    }

    $outOfRangeReferences = 0
    if ($maxVertexReference -gt $vertices) { $outOfRangeReferences++ }
    if ($maxTextureReference -gt $textureCoordinates) { $outOfRangeReferences++ }
    if ($maxNormalReference -gt $normals) { $outOfRangeReferences++ }

    return [pscustomobject]@{
        Vertices = $vertices
        TextureCoordinates = $textureCoordinates
        Normals = $normals
        Faces = $faces
        FaceCorners = $faceCorners
        Triangles = $triangles
        InvalidDataLines = $invalidDataLines
        InvalidFaces = $invalidFaces
        InvalidCorners = $invalidCorners
        UnsupportedCorners = $unsupportedCorners
        WhitespaceProblems = $whitespaceProblems
        OutOfRangeReferences = $outOfRangeReferences
    }
}

function Get-ExactFile {
    param(
        [object[]]$Files,
        [string]$Name
    )

    return @($Files | Where-Object { $_.Name -ceq $Name })
}

function Read-InfoId {
    param(
        [System.IO.FileInfo]$InfoFile,
        [switch]$Quiet
    )

    $lines = [System.IO.File]::ReadAllLines($InfoFile.FullName)
    $idLines = @($lines | Where-Object { $_ -cmatch '^ID=' })
    if ($idLines.Count -ne 1) {
        if (-not $Quiet) {
            Add-ValidationMessage ERROR ("{0}: INFO must contain exactly one ID=<integer> line; found {1}" -f $InfoFile.Directory.Name, $idLines.Count)
        }
        return $null
    }

    if ($idLines[0] -cmatch '^ID=([0-9]+)$') {
        $value = [int64]$Matches[1]
    }
    else {
        if (-not $Quiet) {
            Add-ValidationMessage ERROR ("{0}: the ID line must be exactly ID=<integer>, without spaces or comments" -f $InfoFile.Directory.Name)
        }
        return $null
    }

    if ($value -lt 0 -or $value -gt 254) {
        if (-not $Quiet) {
            Add-ValidationMessage ERROR ("{0}: ID={1} is outside 0..254" -f $InfoFile.Directory.Name, $value)
        }
        return $null
    }

    return [int]$value
}

$normalizedPath = Get-NormalizedPath -LiteralPath $Path
if (-not (Test-Path -LiteralPath $normalizedPath -PathType Container)) {
    Add-ValidationMessage ERROR "Validation path does not exist: $normalizedPath"
    Write-Host ("SUMMARY packages=0 errors={0} warnings={1}" -f $script:ValidationErrorCount, $script:ValidationWarningCount)
    exit 1
}

$packages = @(Get-ResourcePackages -RootPath $normalizedPath)
if ($packages.Count -eq 0) {
    if ($RequirePackages) {
        Add-ValidationMessage ERROR "No resource packages found under $normalizedPath"
    }
    else {
        Add-ValidationMessage INFO "No resource packages found. This is a valid empty-project state; use -RequirePackages for release checks."
    }

    Write-Host ("SUMMARY packages=0 errors={0} warnings={1}" -f $script:ValidationErrorCount, $script:ValidationWarningCount)
    if ($script:ValidationErrorCount -gt 0) { exit 1 }
    exit 0
}

$currentIdRecords = @()
foreach ($package in $packages) {
    Write-Host ''
    Write-Host ("== {0} ==" -f $package.FullName)
    $files = @(Get-ChildItem -LiteralPath $package.FullName -File -ErrorAction Stop)

    foreach ($requiredFile in $requiredFiles) {
        $exact = @(Get-ExactFile -Files $files -Name $requiredFile)
        if ($exact.Count -eq 0) {
            $caseOnly = @($files | Where-Object { $_.Name -ieq $requiredFile })
            if ($caseOnly.Count -gt 0) {
                Add-ValidationMessage ERROR ("{0}: incorrect filename case; expected {1}, found {2}" -f $package.Name, $requiredFile, $caseOnly[0].Name)
            }
            else {
                Add-ValidationMessage ERROR ("{0}: missing required file {1}" -f $package.Name, $requiredFile)
            }
        }
    }

    $infoFiles = @(Get-ExactFile -Files $files -Name 'INFO')
    if ($infoFiles.Count -eq 1) {
        $packageId = Read-InfoId -InfoFile $infoFiles[0]
        if ($null -ne $packageId) {
            Write-Host ("INFO ID={0}" -f $packageId)
            if ($packageId -lt 64) {
                Add-ValidationMessage WARN ("{0}: ID={1} is in the AYCE-reserved range 0..63" -f $package.Name, $packageId)
            }
            $currentIdRecords += [pscustomobject]@{ Id = $packageId; Name = $package.Name; Path = $package.FullName }
        }
    }

    $objFiles = @($files | Where-Object { $_.Extension -ieq '.obj' } | Sort-Object Name)
    $nestedObjFiles = @(Get-ChildItem -LiteralPath $package.FullName -Recurse -File -ErrorAction Stop | Where-Object {
        $_.Extension -ieq '.obj' -and $_.DirectoryName -ne $package.FullName
    })
    foreach ($nestedObj in $nestedObjFiles) {
        Add-ValidationMessage ERROR ("{0}: OBJ files must be at package root, not nested: {1}" -f $package.Name, $nestedObj.FullName)
    }

    $objStats = @()
    foreach ($objFile in $objFiles) {
        if ($allowedObjNames -cnotcontains $objFile.Name) {
            $caseMatch = @($allowedObjNames | Where-Object { $_ -ieq $objFile.Name })
            if ($caseMatch.Count -gt 0) {
                Add-ValidationMessage ERROR ("{0}: incorrect OBJ filename case: {1}; expected {2}" -f $package.Name, $objFile.Name, $caseMatch[0])
            }
            else {
                Add-ValidationMessage ERROR ("{0}: unsupported OBJ filename: {1}" -f $package.Name, $objFile.Name)
            }
        }

        $stats = Get-ObjStats -FilePath $objFile.FullName
        $objStats += [pscustomobject]@{
            OBJ = $objFile.Name
            v = $stats.Vertices
            vt = $stats.TextureCoordinates
            vn = $stats.Normals
            f = $stats.Faces
            FaceCorners = $stats.FaceCorners
            Triangles = $stats.Triangles
        }

        $isRequiredObj = $requiredObjNames -ccontains $objFile.Name
        if ($isRequiredObj -and ($stats.Vertices -eq 0 -or $stats.Faces -eq 0)) {
            Add-ValidationMessage ERROR ("{0}/{1}: required mesh is empty (v={2}, f={3})" -f $package.Name, $objFile.Name, $stats.Vertices, $stats.Faces)
        }
        elseif (-not $isRequiredObj -and $objFile.Name -cne 'Body_Body.obj' -and $stats.Faces -eq 0) {
            Add-ValidationMessage WARN ("{0}/{1}: optional mesh has no faces" -f $package.Name, $objFile.Name)
        }

        if ($stats.InvalidDataLines -gt 0 -or $stats.InvalidFaces -gt 0 -or $stats.InvalidCorners -gt 0) {
            Add-ValidationMessage ERROR ("{0}/{1}: invalid OBJ data (data-lines={2}, faces={3}, corners={4})" -f $package.Name, $objFile.Name, $stats.InvalidDataLines, $stats.InvalidFaces, $stats.InvalidCorners)
        }
        if ($stats.UnsupportedCorners -gt 0) {
            Add-ValidationMessage ERROR ("{0}/{1}: {2} face corners use an importer-incompatible form; export v, v//vn, or v/vt/vn" -f $package.Name, $objFile.Name, $stats.UnsupportedCorners)
        }
        if ($stats.OutOfRangeReferences -gt 0) {
            Add-ValidationMessage ERROR ("{0}/{1}: face references exceed v/vt/vn counts" -f $package.Name, $objFile.Name)
        }
        if ($stats.WhitespaceProblems -gt 0) {
            Add-ValidationMessage ERROR ("{0}/{1}: {2} OBJ data lines contain leading/trailing/repeated whitespace or tabs; importer requires single spaces" -f $package.Name, $objFile.Name, $stats.WhitespaceProblems)
        }
        if ($stats.FaceCorners -gt $MaxFaceCorners) {
            Add-ValidationMessage ERROR ("{0}/{1}: face-corners={2} exceeds safe limit {3}; decimate or split the part" -f $package.Name, $objFile.Name, $stats.FaceCorners, $MaxFaceCorners)
        }
        elseif ($stats.FaceCorners -gt 60000) {
            Add-ValidationMessage WARN ("{0}/{1}: face-corners={2} is close to the 16-bit index limit" -f $package.Name, $objFile.Name, $stats.FaceCorners)
        }
        if ($stats.Faces -gt 0 -and $stats.TextureCoordinates -eq 0) {
            Add-ValidationMessage WARN ("{0}/{1}: no vt records; texture mapping will fail" -f $package.Name, $objFile.Name)
        }
        if ($stats.Faces -gt 0 -and $stats.Normals -eq 0) {
            Add-ValidationMessage WARN ("{0}/{1}: no vn records; lighting may be incorrect" -f $package.Name, $objFile.Name)
        }
    }

    if ($objStats.Count -gt 0) {
        $objStats | Format-Table -AutoSize | Out-String -Width 220 | Write-Host
    }

    $pngFiles = @($files | Where-Object { $_.Extension -ieq '.png' } | Sort-Object Name)
    $pngStats = @()
    foreach ($pngFile in $pngFiles) {
        $pngInfo = Get-PngInfo -FilePath $pngFile.FullName
        if (-not $pngInfo.Valid) {
            Add-ValidationMessage ERROR ("{0}/{1}: {2}" -f $package.Name, $pngFile.Name, $pngInfo.Reason)
            continue
        }

        $pngStats += [pscustomobject]@{ PNG = $pngFile.Name; Width = $pngInfo.Width; Height = $pngInfo.Height }
        if ($pngInfo.Width -ne $RecommendedTextureSize -or $pngInfo.Height -ne $RecommendedTextureSize) {
            Add-ValidationMessage WARN ("{0}/{1}: size is {2}x{3}; this project recommends {4}x{4}" -f $package.Name, $pngFile.Name, $pngInfo.Width, $pngInfo.Height, $RecommendedTextureSize)
        }
        if ($pngInfo.Width -ne $pngInfo.Height) {
            Add-ValidationMessage WARN ("{0}/{1}: texture is not square" -f $package.Name, $pngFile.Name)
        }
        if (-not (Test-PowerOfTwo -Value $pngInfo.Width) -or -not (Test-PowerOfTwo -Value $pngInfo.Height)) {
            Add-ValidationMessage WARN ("{0}/{1}: texture dimensions are not powers of two" -f $package.Name, $pngFile.Name)
        }
    }

    if ($pngStats.Count -gt 0) {
        $pngStats | Format-Table -AutoSize | Out-String -Width 220 | Write-Host
    }
}

foreach ($group in @($currentIdRecords | Group-Object -Property Id | Where-Object { $_.Count -gt 1 })) {
    $names = ($group.Group | ForEach-Object { $_.Name }) -join ', '
    Add-ValidationMessage ERROR ("Export ID={0} conflict: {1}" -f $group.Name, $names)
}

if ($ExistingResourcesPath) {
    $normalizedExistingPath = Get-NormalizedPath -LiteralPath $ExistingResourcesPath
    if (-not (Test-Path -LiteralPath $normalizedExistingPath -PathType Container)) {
        Add-ValidationMessage ERROR "Existing Resources path does not exist: $normalizedExistingPath"
    }
    elseif (-not $normalizedExistingPath.Equals($normalizedPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        $existingPackages = @(Get-ResourcePackages -RootPath $normalizedExistingPath)
        $existingRecords = @()
        foreach ($existingPackage in $existingPackages) {
            $existingFiles = @(Get-ChildItem -LiteralPath $existingPackage.FullName -File -ErrorAction Stop)
            $existingInfo = @(Get-ExactFile -Files $existingFiles -Name 'INFO')
            if ($existingInfo.Count -ne 1) {
                Add-ValidationMessage WARN ("Existing resource {0} lacks an exact readable INFO; skipping its ID" -f $existingPackage.Name)
                continue
            }

            $existingId = Read-InfoId -InfoFile $existingInfo[0] -Quiet
            if ($null -eq $existingId) {
                Add-ValidationMessage WARN ("Existing resource {0} has an invalid ID; skipping it" -f $existingPackage.Name)
                continue
            }
            $existingRecords += [pscustomobject]@{ Id = $existingId; Name = $existingPackage.Name; Path = $existingPackage.FullName }
        }

        foreach ($record in $currentIdRecords) {
            $conflicts = @($existingRecords | Where-Object { $_.Id -eq $record.Id })
            foreach ($conflict in $conflicts) {
                Add-ValidationMessage ERROR ("ID={0} conflict: export {1} versus existing resource {2}" -f $record.Id, $record.Name, $conflict.Name)
            }
        }
        Write-Host ("ID scan: current={0}, existing={1}" -f $currentIdRecords.Count, $existingRecords.Count)
    }
}

Write-Host ''
Write-Host ("SUMMARY packages={0} errors={1} warnings={2}" -f $packages.Count, $script:ValidationErrorCount, $script:ValidationWarningCount)
if ($script:ValidationErrorCount -gt 0) {
    exit 1
}
exit 0
