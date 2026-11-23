param(
    [Parameter(Mandatory = $true)]
    [string]$Uvprojx,
    [string]$Uv4Path = "",
    [switch]$Rebuild,
    [switch]$Clean,
    [switch]$AllowMissingBin
)

$ErrorActionPreference = "Stop"

function Initialize-ConsoleEncoding {
    try {
        chcp 65001 > $null
        [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
        [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
        $global:OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    } catch { }
}

function Get-RegistryUv4Candidates {
    $result = @()
    $registryPaths = @(
        "HKLM:\SOFTWARE\WOW6432Node\Keil\Products\MDK",
        "HKLM:\SOFTWARE\Keil\Products\MDK",
        "HKCU:\SOFTWARE\Keil\Products\MDK"
    )

    foreach ($registryPath in $registryPaths) {
        try {
            $registry = Get-ItemProperty `
                -Path $registryPath `
                -ErrorAction SilentlyContinue
            if (-not $registry) { continue }

            foreach ($propertyName in @("MDKPath", "Path")) {
                $property = $registry.PSObject.Properties[$propertyName]
                if (-not $property -or -not $property.Value) { continue }

                $basePath = ([string]$property.Value).TrimEnd('\', '/')
                $result += Join-Path $basePath "UV4\UV4.exe"
                $parentPath = Split-Path -Parent $basePath
                if ($parentPath) {
                    $result += Join-Path $parentPath "UV4\UV4.exe"
                }
            }
        } catch {
            # Continue with the other registry locations.
        }
    }

    return @($result | Select-Object -Unique)
}

function Resolve-Uv4Path {
    param([string]$ExplicitPath)
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($ExplicitPath) { $candidates.Add($ExplicitPath) }
    if ($env:KEIL_UV4) { $candidates.Add($env:KEIL_UV4) }
    foreach ($candidate in @(Get-RegistryUv4Candidates)) {
        if ($candidate) { $candidates.Add($candidate) }
    }
    foreach ($candidate in @(
        "C:\Keil_v5\UV4\UV4.exe",
        "D:\Keil_v5\UV4\UV4.exe",
        "E:\Keil_v5\UV4\UV4.exe",
        "${env:ProgramFiles}\Keil_v5\UV4\UV4.exe",
        "${env:ProgramFiles(x86)}\Keil_v5\UV4\UV4.exe",
        "C:\Keil\UV4\UV4.exe"
    )) { if ($candidate) { $candidates.Add($candidate) } }

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return (Resolve-Path -LiteralPath $candidate).Path }
    }
    return $null
}

function Get-BuildCounts {
    param([string]$Text)
    $summaryMatches = [regex]::Matches(
        $Text,
        '(?im)(\d+)\s+Error\(s\)\s*,\s*(\d+)\s+Warning\(s\)'
    )
    if ($summaryMatches.Count -gt 0) {
        $summary = $summaryMatches[$summaryMatches.Count - 1]
        return [pscustomobject]@{
            Errors = [int]$summary.Groups[1].Value
            Warnings = [int]$summary.Groups[2].Value
            SummaryFound = $true
        }
    }
    $errors = [regex]::Matches($Text, '(?im)\berror(?:\s+[A-Z]\d+)?\s*:').Count
    $warnings = [regex]::Matches($Text, '(?im)\bwarning(?:\s+[A-Z]\d+)?\s*:').Count
    return [pscustomobject]@{
        Errors = $errors
        Warnings = $warnings
        SummaryFound = $false
    }
}

function Test-FreshArtifact {
    param([string]$Path, [DateTime]$BuildStartUtc)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $item = Get-Item -LiteralPath $Path
    return $item.Length -gt 0 -and $item.LastWriteTimeUtc -ge $BuildStartUtc.AddSeconds(-2)
}

function Test-ArtifactPresent {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    return (Get-Item -LiteralPath $Path).Length -gt 0
}

function Invoke-MdkBuild {
    param([string]$Flag, [switch]$RequireFresh)
    if (Test-Path -LiteralPath $script:logFile) { Remove-Item -LiteralPath $script:logFile -Force }
    $startUtc = [DateTime]::UtcNow
    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    $arguments = "$Flag `"$script:projectPath`" -o `"$script:logFile`" -j0"
    $process = Start-Process -FilePath $script:uv4 -ArgumentList $arguments `
        -WindowStyle Hidden -Wait -PassThru
    $stopwatch.Stop()

    $output = if (Test-Path -LiteralPath $script:logFile) {
        Get-Content -Raw -LiteralPath $script:logFile -ErrorAction SilentlyContinue
    } else { "" }
    $counts = Get-BuildCounts $output
    $hexFresh = Test-FreshArtifact -Path $script:hexFile -BuildStartUtc $startUtc
    $binFresh = Test-FreshArtifact -Path $script:binFile -BuildStartUtc $startUtc
    $hexPresent = Test-ArtifactPresent -Path $script:hexFile
    $binPresent = Test-ArtifactPresent -Path $script:binFile
    $compileOk = $process.ExitCode -eq 0 -and $counts.SummaryFound -and
        $counts.Errors -eq 0 -and $counts.Warnings -eq 0

    # A rebuild must prove it regenerated artifacts. An incremental build may
    # legitimately be "up to date" (Keil skips re-linking) and reuse existing
    # non-empty artifacts, so for -b we only require the artifacts to exist.
    if ($RequireFresh) {
        $artifactsOk = $hexFresh -and ($AllowMissingBin -or $binFresh)
    } else {
        $artifactsOk = $hexPresent -and ($AllowMissingBin -or $binPresent)
    }
    $staleReuse = $compileOk -and $artifactsOk -and
        -not ($hexFresh -and ($AllowMissingBin -or $binFresh))

    return [pscustomobject]@{
        Passed = ($compileOk -and $artifactsOk)
        CompileOk = $compileOk
        ExitCode = $process.ExitCode
        Errors = $counts.Errors
        Warnings = $counts.Warnings
        SummaryFound = $counts.SummaryFound
        HexFresh = $hexFresh
        BinFresh = $binFresh
        HexPresent = $hexPresent
        BinPresent = $binPresent
        StaleReuse = $staleReuse
        Output = $output
        Seconds = [math]::Round($stopwatch.Elapsed.TotalSeconds, 1)
    }
}

function Write-BuildResult {
    param($Result, [string]$Label)
    Write-Host "=== $Label ==="
    $prefix = if ($Result.Passed) { "[PASS]" } else { "[FAIL]" }
    Write-Host "$prefix exit=$($Result.ExitCode), errors=$($Result.Errors), warnings=$($Result.Warnings), time=$($Result.Seconds)s"
    Write-Host "[INFO] Keil summary found: $($Result.SummaryFound)"
    Write-Host "[INFO] HEX fresh: $($Result.HexFresh) (exists: $($Result.HexPresent)) - $script:hexFile"
    Write-Host "[INFO] BIN fresh: $($Result.BinFresh) (exists: $($Result.BinPresent)) - $script:binFile"
    if ($Result.Passed -and $Result.StaleReuse) {
        Write-Host "[INFO] Incremental build had nothing to re-link; reused existing artifacts. Use -Rebuild to force regeneration."
    }
    if ($Result.Output) {
        Write-Host "--- Last 30 lines ---"
        ($Result.Output -split "`r?`n") | Select-Object -Last 30 | ForEach-Object { Write-Host $_ }
    }
}

Initialize-ConsoleEncoding
if (-not (Test-Path -LiteralPath $Uvprojx)) {
    Write-Host "[FAIL] Project not found: $Uvprojx"
    exit 1
}
$projectPath = (Resolve-Path -LiteralPath $Uvprojx).Path
$uv4 = Resolve-Uv4Path -ExplicitPath $Uv4Path
if (-not $uv4) {
    Write-Host "[FAIL] UV4.exe not found. Set KEIL_UV4 or pass -Uv4Path."
    exit 1
}

$projectDir = Split-Path -Parent $projectPath
$projectXml = [xml](Get-Content -Raw -LiteralPath $projectPath -Encoding UTF8)
$outputNameNode = $projectXml.SelectSingleNode("//OutputName")
$outputDirNode = $projectXml.SelectSingleNode("//OutputDirectory")
$outputName = if ($outputNameNode.InnerText) { $outputNameNode.InnerText.Trim() } else { "ble_project" }
$outputDirectory = if ($outputDirNode.InnerText) { $outputDirNode.InnerText.Trim() } else { "obj" }
$normalizedOutputDirectory = $outputDirectory -replace '/', '\'
$objDir = if ([IO.Path]::IsPathRooted($normalizedOutputDirectory)) {
    [IO.Path]::GetFullPath($normalizedOutputDirectory)
} else {
    [IO.Path]::GetFullPath((Join-Path $projectDir $normalizedOutputDirectory))
}
if (-not (Test-Path -LiteralPath $objDir)) { New-Item -ItemType Directory -Path $objDir -Force | Out-Null }

$logFile = Join-Path $objDir "mdk_cli_build.log"
$hexFile = Join-Path $objDir "$outputName.hex"
$binFile = Join-Path $objDir "$outputName.bin"

Write-Host "[INFO] Project: $projectPath"
Write-Host "[INFO] UV4: $uv4"
$flag = if ($Rebuild -or $Clean) { "-r" } else { "-b" }
$result = Invoke-MdkBuild -Flag $flag -RequireFresh:($flag -eq "-r")
Write-BuildResult -Result $result -Label "Build Result"

# Incremental build may legitimately be "up to date" and reuse existing
# artifacts. Only fall back to a rebuild when compilation succeeded but the
# artifacts are missing/empty (e.g. corrupted obj cache after a toolchain
# reinstall), which incremental cannot fix on its own.
if ($flag -eq "-b" -and -not $result.Passed -and $result.CompileOk) {
    Write-Host "[WARN] Incremental build succeeded but artifacts are missing or empty; retrying rebuild."
    $result = Invoke-MdkBuild -Flag "-r" -RequireFresh
    Write-BuildResult -Result $result -Label "Build Result (rebuild)"
}

if (-not $result.Passed) {
    if (-not $result.CompileOk) {
        Write-Host "[FAIL] Build did not complete cleanly (exit=$($result.ExitCode), errors=$($result.Errors), warnings=$($result.Warnings))."
    }
    if (-not $result.SummaryFound) { Write-Host "[FAIL] Keil 0 Error(s), 0 Warning(s) summary is missing." }
    if (-not $result.HexPresent) { Write-Host "[FAIL] HEX is missing or empty." }
    elseif ($flag -eq "-r" -and -not $result.HexFresh) { Write-Host "[FAIL] HEX is stale after rebuild." }
    if (-not $AllowMissingBin -and -not $result.BinPresent) { Write-Host "[FAIL] BIN is missing or empty." }
    elseif (-not $AllowMissingBin -and $flag -eq "-r" -and -not $result.BinFresh) { Write-Host "[FAIL] BIN is stale after rebuild." }
    exit 1
}
if ($result.StaleReuse) {
    Write-Host "[PASS] Build evidence accepted: 0 Error, 0 Warning (reused existing artifacts; no source change detected)."
} else {
    Write-Host "[PASS] Build evidence accepted: 0 Error, 0 Warning, fresh artifacts verified."
}
exit 0
