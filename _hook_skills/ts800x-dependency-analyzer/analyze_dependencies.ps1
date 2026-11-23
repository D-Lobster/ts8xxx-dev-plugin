param(
    [string]$File,
    [string]$Files,
    [switch]$GitDiff,
    [string]$ProjectRoot = ".",
    [switch]$JsonOutput,
    [string]$OutputFile = "dependency_report.json"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Get-RelativePath {
    param([string]$Root, [string]$Path)
    $rootPrefix = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $fullPath = [IO.Path]::GetFullPath($Path)
    if ($fullPath.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        return $fullPath.Substring($rootPrefix.Length).Replace('\', '/')
    }
    return $fullPath.Replace('\', '/')
}

function Read-TargetContent {
    param([string]$RelativePath)
    $fullPath = Join-Path $script:projectRootPath ($RelativePath -replace '/', '\')
    if (Test-Path -LiteralPath $fullPath) {
        return Get-Content -Raw -LiteralPath $fullPath -Encoding UTF8
    }
    $headContent = & git -C $script:projectRootPath show "HEAD:$RelativePath" 2>$null
    if ($LASTEXITCODE -eq 0) { return ($headContent -join [Environment]::NewLine) }
    return $null
}

function Get-RiskLevel {
    param([int]$AffectedCount, [string[]]$Reasons)
    if ($Reasons -match 'SDK changed|build configuration|linker configuration') { return "HIGH" }
    if ($AffectedCount -gt 5) { return "HIGH" }
    if ($AffectedCount -gt 2) { return "MEDIUM" }
    if ($AffectedCount -gt 0) { return "LOW" }
    return "NONE"
}

function Get-LineNumber {
    param([string]$Text, [int]$Index)
    if ($Index -le 0) { return 1 }
    return ([regex]::Matches($Text.Substring(0, $Index), "`n").Count + 1)
}

$projectRootPath = (Resolve-Path -LiteralPath $ProjectRoot).Path
$gitSafeRoot = $projectRootPath.Replace('\', '/')
Write-Host "=== TS800X Dependency Analyzer ==="

if ($GitDiff) {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $tracked = & git -c "safe.directory=$gitSafeRoot" -C $projectRootPath diff --name-only HEAD 2>$null
        $trackedExit = $LASTEXITCODE
        if ($trackedExit -ne 0) {
            $tracked = & git -c "safe.directory=$gitSafeRoot" -C $projectRootPath diff --name-only 2>$null
            $trackedExit = $LASTEXITCODE
        }
        if ($trackedExit -ne 0) {
            throw "git diff failed with exit code $trackedExit"
        }
        $untracked = & git -c "safe.directory=$gitSafeRoot" -C $projectRootPath `
            ls-files --others --exclude-standard 2>$null
        $untrackedExit = $LASTEXITCODE
        if ($untrackedExit -ne 0) {
            throw "git ls-files failed with exit code $untrackedExit"
        }
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $targetFiles = @(
        @($tracked) + @($untracked) | Where-Object { $_ } | Sort-Object -Unique
    )
} elseif ($Files) {
    $targetFiles = @(
        $Files -split ',' | ForEach-Object { $_.Trim().Replace('\', '/') } |
            Where-Object { $_ } | Sort-Object -Unique
    )
} elseif ($File) {
    $targetFiles = @($File.Replace('\', '/'))
} else {
    Write-Host "[FAIL] Specify -File, -Files, or -GitDiff."
    exit 1
}

$allCodeFiles = @(
    Get-ChildItem -LiteralPath $projectRootPath -Recurse -File -Include "*.c", "*.h" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.FullName -notmatch '\\(?:obj|Objects|build|reports|context|\.git)\\' -and
            $_.FullName -notmatch '\\ts800x_sdk\\'
        }
)
$contentCache = @{}
foreach ($codeFile in $allCodeFiles) {
    $relative = Get-RelativePath -Root $projectRootPath -Path $codeFile.FullName
    $contentCache[$relative] = Get-Content -Raw -LiteralPath $codeFile.FullName -Encoding UTF8
}

$impactResults = New-Object System.Collections.Generic.List[object]
foreach ($target in $targetFiles) {
    $normalizedTarget = ([string]$target).Replace('\', '/')
    $extension = [IO.Path]::GetExtension($normalizedTarget).ToLowerInvariant()
    $content = Read-TargetContent -RelativePath $normalizedTarget
    $reasons = New-Object System.Collections.Generic.List[string]
    $functions = @()
    $globals = @()
    $callers = New-Object System.Collections.Generic.List[string]
    $includeDependents = New-Object System.Collections.Generic.List[string]
    $evidence = New-Object System.Collections.Generic.List[object]

    if ($normalizedTarget -match '(^|/)ts800x_sdk/') { $reasons.Add("SDK changed") | Out-Null }
    if ($extension -eq ".uvprojx") { $reasons.Add("build configuration") | Out-Null }
    if ($extension -in @(".sct", ".ld", ".icf")) { $reasons.Add("linker configuration") | Out-Null }

    if ($null -ne $content -and $extension -in @(".c", ".h")) {
        $functionPattern = [regex]'(?m)^(?:[A-Za-z_]\w*[\s\*]+)+(\w+)\s*\([^;{}]*\)\s*\{'
        $functions = @($functionPattern.Matches($content) | ForEach-Object { $_.Groups[1].Value } |
            Sort-Object -Unique)
        $globalPattern = [regex]'(?m)^(?!\s*static\b)(?:extern\s+)?(?:const\s+)?(?:[A-Za-z_]\w*[\s\*]+)+(g_\w+|f_\w+)\s*(?:\[[^]]*\])?\s*(?:=|;)'
        $globals = @($globalPattern.Matches($content) | ForEach-Object { $_.Groups[1].Value } |
            Sort-Object -Unique)

        foreach ($candidate in $contentCache.GetEnumerator()) {
            if ($candidate.Key -eq $normalizedTarget) { continue }
            foreach ($functionName in $functions) {
                $escapedFunction = [regex]::Escape($functionName)
                $callPattern = "(?m)^(?!\s*(?:extern\s+)?(?:[A-Za-z_]\w*[\s\*]+)+$escapedFunction\s*\([^;{}]*\)\s*;).*\b$escapedFunction\s*\("
                $match = [regex]::Match($candidate.Value, $callPattern)
                if ($match.Success) {
                    if (-not $callers.Contains($candidate.Key)) { $callers.Add($candidate.Key) | Out-Null }
                    $evidence.Add([ordered]@{
                        relationship = "possible_call"
                        symbol = $functionName
                        file = $candidate.Key
                        line = Get-LineNumber -Text $candidate.Value -Index $match.Index
                        method = "regex"
                        confidence = "inferred"
                    }) | Out-Null
                }
            }
            foreach ($globalName in $globals) {
                $match = [regex]::Match($candidate.Value, ("\b" + [regex]::Escape($globalName) + "\b"))
                if ($match.Success) {
                    if (-not $callers.Contains($candidate.Key)) { $callers.Add($candidate.Key) | Out-Null }
                    $evidence.Add([ordered]@{
                        relationship = "possible_global_reference"
                        symbol = $globalName
                        file = $candidate.Key
                        line = Get-LineNumber -Text $candidate.Value -Index $match.Index
                        method = "regex"
                        confidence = "inferred"
                    }) | Out-Null
                }
            }
        }

        if ($extension -eq ".h") {
            $headerName = [IO.Path]::GetFileName($normalizedTarget)
            foreach ($candidate in $contentCache.GetEnumerator()) {
                $includePattern = '#\s*include\s*[<"]' + [regex]::Escape($headerName) + '[>"]'
                $match = [regex]::Match($candidate.Value, $includePattern)
                if ($match.Success -and -not $includeDependents.Contains($candidate.Key)) {
                    $includeDependents.Add($candidate.Key) | Out-Null
                    $evidence.Add([ordered]@{
                        relationship = "direct_include"
                        symbol = $headerName
                        file = $candidate.Key
                        line = Get-LineNumber -Text $candidate.Value -Index $match.Index
                        method = "regex"
                        confidence = "observed"
                    }) | Out-Null
                }
            }
        }
    } elseif ($null -eq $content) {
        $reasons.Add("file content unavailable") | Out-Null
    }

    $affected = @(
        @($callers | ForEach-Object { $_ }) +
            @($includeDependents | ForEach-Object { $_ }) |
            Sort-Object -Unique
    )
    $evidenceArray = @($evidence | ForEach-Object { $_ })
    $risk = Get-RiskLevel -AffectedCount $affected.Count -Reasons @($reasons)
    Write-Host "[TARGET] $normalizedTarget - risk=$risk, affected=$($affected.Count)"
    $impactResults.Add([ordered]@{
        target = $normalizedTarget
        functions = $functions
        globals = $globals
        callers = @($callers)
        include_dependents = @($includeDependents)
        affected_files = $affected
        evidence = $evidenceArray
        manual_review_required = ($risk -eq "HIGH" -or @($evidenceArray | Where-Object { $_.confidence -eq "inferred" }).Count -gt 0)
        risk_level = $risk
        risk_reasons = @($reasons)
    }) | Out-Null
}

$riskOrder = @{ NONE = 0; LOW = 1; MEDIUM = 2; HIGH = 3 }
$overallRisk = "NONE"
foreach ($result in $impactResults) {
    if ($riskOrder[$result.risk_level] -gt $riskOrder[$overallRisk]) { $overallRisk = $result.risk_level }
}
$affectedCount = @($impactResults | ForEach-Object { $_.affected_files } | Sort-Object -Unique).Count
$nonCodeFiles = @($targetFiles | Where-Object { [IO.Path]::GetExtension($_) -notin @(".c", ".h") })
$impactArray = @($impactResults | ForEach-Object { $_ })

$report = [ordered]@{
    schema_version = 3
    timestamp = [DateTimeOffset]::Now.ToString("o")
    project_root = $projectRootPath
    method = "regex_static_analysis"
    changed_files = @($targetFiles)
    non_code_changed_files = $nonCodeFiles
    impact_analysis = $impactArray
    overall_risk = $overallRisk
    summary = "$($targetFiles.Count) files changed, $affectedCount unique affected files"
    limitations = @(
        "Function pointers, macro-generated calls, and runtime dispatch require manual review.",
        "HIGH-risk items must be checked against git diff and architecture documents."
    )
}

if ($JsonOutput) {
    $reportPath = if ([IO.Path]::IsPathRooted($OutputFile)) { $OutputFile } else { Join-Path $projectRootPath $OutputFile }
    $reportDir = Split-Path -Parent $reportPath
    if (-not (Test-Path -LiteralPath $reportDir)) { New-Item -ItemType Directory -Path $reportDir -Force | Out-Null }
    $report | ConvertTo-Json -Depth 20 | Out-File -LiteralPath $reportPath -Encoding UTF8
    Write-Host "[PASS] JSON report saved: $reportPath"
}
Write-Host "[PASS] Analysis complete: overall risk=$overallRisk"
