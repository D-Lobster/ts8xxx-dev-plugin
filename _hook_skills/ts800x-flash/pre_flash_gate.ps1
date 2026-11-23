param(
    [Parameter(Mandatory = $true)]
    [string]$HexFile,
    [Parameter(Mandatory = $true)]
    [string]$Uvprojx,
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [string]$Module = "",
    [string]$StateFile = "",
    [switch]$NoSourceFiles
)

$ErrorActionPreference = "Stop"
$workflowRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$stateHelper = Join-Path $workflowRoot "_hook_skills\ts800x-build\workflow_state.ps1"
. $stateHelper
Initialize-Ts800xConsoleEncoding

function Get-FullPath {
    param([string]$Path, [string]$Base)
    try {
        $candidate = if ([IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path $Base $Path }
        return [IO.Path]::GetFullPath($candidate)
    } catch {
        Write-Warning "Get-FullPath failed for Path='$Path', Base='$Base': $_"
        return $Path
    }
}

function Test-ChildPath {
    param([string]$Root, [string]$Path)
    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $fullPath = [IO.Path]::GetFullPath($Path)
    return $fullPath.StartsWith($rootPath, [StringComparison]::OrdinalIgnoreCase)
}

function Add-GateResult {
    param([string]$Name, [bool]$Passed, [string]$Evidence)
    $script:checks.Add([pscustomobject]@{ Name = $Name; Passed = $Passed; Evidence = $Evidence }) | Out-Null
}

function Get-StepStatus {
    param($Entry, [string]$Step)
    if ($null -eq $Entry -or $null -eq $Entry.PSObject.Properties[$Step]) { return "missing" }
    return [string]$Entry.$Step.status
}

function Find-NonAsciiLogs {
    param([string[]]$Files)
    $hits = New-Object System.Collections.Generic.List[string]
    $logPattern = '(?i)\b(?:LOG(?:_[A-Z]+)?|printf)\s*\(\s*"([^"]*)"'
    foreach ($file in $Files) {
        $lineNumber = 0
        foreach ($line in Get-Content -LiteralPath $file -Encoding UTF8) {
            $lineNumber++
            foreach ($match in [regex]::Matches($line, $logPattern)) {
                if ($match.Groups[1].Value -match '[^\x00-\x7F]') {
                    $hits.Add("$file`:$lineNumber") | Out-Null
                }
            }
        }
    }
    return @($hits)
}

$projectRootPath = (Resolve-Path -LiteralPath $ProjectRoot).Path
$hexPath = Get-FullPath -Path $HexFile -Base $projectRootPath
$uvprojxPath = Get-FullPath -Path $Uvprojx -Base $projectRootPath
$uvprojxIsLocal = (Test-ChildPath -Root $projectRootPath -Path $uvprojxPath) -and
    (Test-Path -LiteralPath $uvprojxPath -PathType Leaf)
$state = Read-Ts800xState -ProjectRoot $projectRootPath -StateFile $StateFile
if (-not $Module) { $Module = [string]$state.active_module }
$entry = if ($Module -and $null -ne $state.modules.PSObject.Properties[$Module]) {
    $state.modules.$Module
} else {
    $null
}
$checks = New-Object System.Collections.Generic.List[object]

Add-GateResult "编译 0/0（初验）" ((Get-StepStatus $entry "build_initial") -eq "pass") `
    (Get-StepStatus $entry "build_initial")
$qualityStatus = Get-StepStatus $entry "code_quality"
Add-GateResult "ts800x-code-quality 已执行" ($qualityStatus -in @("done", "skipped_whitelist")) $qualityStatus
Add-GateResult "编译 0/0（确认无回归）" ((Get-StepStatus $entry "build_after_code_quality") -eq "pass") `
    (Get-StepStatus $entry "build_after_code_quality")

$sourcePaths = New-Object System.Collections.Generic.List[string]
$sourceErrors = New-Object System.Collections.Generic.List[string]
if ($null -ne $entry) {
    foreach ($source in @($entry.source_files)) {
        if (-not $source) { continue }
        $sourcePath = Get-FullPath -Path ([string]$source) -Base $projectRootPath
        if (-not (Test-ChildPath -Root $projectRootPath -Path $sourcePath)) {
            $sourceErrors.Add("outside project: $source") | Out-Null
        } elseif (-not (Test-Path -LiteralPath $sourcePath)) {
            $sourceErrors.Add("missing: $source") | Out-Null
        } else {
            $sourcePaths.Add($sourcePath) | Out-Null
        }
    }
}

$projectContainsSources = $false
if (-not $uvprojxIsLocal) {
    $sourceErrors.Add("uvprojx must be an existing file inside the project: $uvprojxPath") | Out-Null
} elseif ($NoSourceFiles -and $sourcePaths.Count -eq 0) {
    $projectContainsSources = $true
} elseif ($sourcePaths.Count -gt 0 -and $sourceErrors.Count -eq 0) {
    try {
        $projectXml = [xml](Get-Content -Raw -LiteralPath $uvprojxPath -Encoding UTF8)
        $projectDir = Split-Path -Parent $uvprojxPath
        $includedPaths = foreach ($node in $projectXml.SelectNodes("//FilePath")) {
            if (-not $node.InnerText) { continue }
            Get-FullPath -Path ($node.InnerText -replace '/', '\') -Base $projectDir
        }
        $missingIncludes = @($sourcePaths | Where-Object { $_ -notin $includedPaths })
        $projectContainsSources = $missingIncludes.Count -eq 0
        foreach ($missing in $missingIncludes) { $sourceErrors.Add("not in uvprojx: $missing") | Out-Null }
    } catch {
        $sourceErrors.Add("uvprojx parse failed: $($_.Exception.Message)") | Out-Null
    }
} elseif (-not $NoSourceFiles) {
    $sourceErrors.Add("no source_files evidence; use -NoSourceFiles only for a config-only change") | Out-Null
}
Add-GateResult ".uvprojx 已包含新模块文件" $projectContainsSources ($sourceErrors -join "; ")

$nonAsciiLogs = Find-NonAsciiLogs -Files @($sourcePaths)
Add-GateResult "LOG 无中文字符" ($nonAsciiLogs.Count -eq 0) ($nonAsciiLogs -join "; ")

$dependencyStatus = Get-StepStatus $entry "dependency"
$dependencyEvidence = if ($null -ne $entry) { [string]$entry.dependency.evidence } else { "" }
$dependencyEvidencePath = if ($dependencyEvidence) {
    Get-FullPath -Path $dependencyEvidence -Base $projectRootPath
} else {
    ""
}
$dependencyOk = $dependencyStatus -eq "pass" -and $dependencyEvidencePath -and
    (Test-ChildPath -Root $projectRootPath -Path $dependencyEvidencePath) -and
    (Test-Path -LiteralPath $dependencyEvidencePath -PathType Leaf)
if ($dependencyOk) {
    try {
        $dependencyReport = Get-Content -Raw -LiteralPath $dependencyEvidencePath -Encoding UTF8 |
            ConvertFrom-Json
        $reportRoot = Get-FullPath -Path ([string]$dependencyReport.project_root) -Base $projectRootPath
        $dependencyOk = [int]$dependencyReport.schema_version -ge 2 -and
            $reportRoot -eq $projectRootPath -and
            $null -ne $dependencyReport.changed_files
        if (-not $dependencyOk) {
            $dependencyEvidence = "report schema/project_root/changed_files validation failed"
        }
    } catch {
        $dependencyOk = $false
        $dependencyEvidence = $_.Exception.Message
    }
}
if ($dependencyOk) { $dependencyEvidence = $dependencyEvidencePath }
Add-GateResult "依赖分析已通过" $dependencyOk "$dependencyStatus; $dependencyEvidence"

$artifactOk = Test-ChildPath -Root $projectRootPath -Path $hexPath
$artifactEvidence = ""
if (-not (Test-Path -LiteralPath $hexPath)) {
    $artifactOk = $false
    $artifactEvidence = "missing: $hexPath"
} else {
    $hexInfo = Get-Item -LiteralPath $hexPath
    $inputs = @($uvprojxPath) + @($sourcePaths)
    $latestInput = $inputs | Where-Object { Test-Path -LiteralPath $_ } |
        ForEach-Object { (Get-Item -LiteralPath $_).LastWriteTimeUtc } | Sort-Object -Descending | Select-Object -First 1
    $artifactOk = $artifactOk -and $hexInfo.Length -gt 0 -and
        ($null -eq $latestInput -or $hexInfo.LastWriteTimeUtc -ge $latestInput)
    $artifactEvidence = "size=$($hexInfo.Length); hexUtc=$($hexInfo.LastWriteTimeUtc.ToString('o')); latestInputUtc=$latestInput"
}
Add-GateResult "固件产物非空且新鲜" $artifactOk $artifactEvidence

$allPassed = @($checks | Where-Object { -not $_.Passed }).Count -eq 0
if ($null -ne $entry) {
    Set-Ts800xStepStatus -Entry $entry -Step "pre_flash_gate" `
        -Status $(if ($allPassed) { "pass" } else { "fail" }) `
        -Evidence (($checks | ForEach-Object { "$($_.Name)=$($_.Passed):$($_.Evidence)" }) -join " | ")
    Save-Ts800xState -State $state -ProjectRoot $projectRootPath -StateFile $StateFile | Out-Null
}

Write-Host "【可选交付审计】"
foreach ($check in $checks) {
    $mark = if ($check.Passed) { "x" } else { " " }
    Write-Host "- [$mark] $($check.Name)"
    if (-not $check.Passed -and $check.Evidence) { Write-Host "      $($check.Evidence)" }
}
Write-Host "- [ ] 视觉验证（交付前由用户确认）"
if (-not $allPassed) {
    Write-Host "→ 审计未通过：不影响开发测试烧录，但不得把本结果作为交付证据" -ForegroundColor Yellow
    exit 1
}
Write-Host "→ 审计通过（开发测试烧录本身不要求此审计）" -ForegroundColor Green
