param(
    [Parameter(Mandatory = $true)]
    [string]$Uvprojx,
    [Parameter(Mandatory = $true)]
    [string]$Message,
    [ValidateSet("feat", "fix", "refactor", "docs", "chore", "test")]
    [string]$Type = "feat",
    [string[]]$Paths = @(),
    [switch]$StageAll,
    [switch]$Push,
    [switch]$SkipBuild,
    [switch]$CheckVerification,
    [switch]$AllowPending,
    [switch]$AllowProtectedBranch,
    [string]$ReportFile = "commit_report.json"
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$buildScript = Join-Path $scriptDir "build.ps1"
$stateHelper = Join-Path $scriptDir "workflow_state.ps1"
. $stateHelper

if (-not (Test-Path -LiteralPath $Uvprojx)) { throw "Project file not found: $Uvprojx" }
$projectFile = (Resolve-Path -LiteralPath $Uvprojx).Path
$projectDirectory = Split-Path -Parent $projectFile
$gitRoot = (& git -C $projectDirectory rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $gitRoot) { throw "No Git repository contains $projectFile" }
$gitRoot = $gitRoot.Trim()

if (-not $SkipBuild) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildScript -Uvprojx $projectFile -Rebuild
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAIL] Build failed; commit blocked."
        exit 1
    }
} else {
    Write-Host "[WARN] Build explicitly skipped."
}

$branch = (& git -C $gitRoot branch --show-current).Trim()
if ($branch -in @("master", "main") -and -not $AllowProtectedBranch) {
    Write-Host "[FAIL] Direct commit on '$branch' is blocked. Create a branch or pass -AllowProtectedBranch with explicit user approval."
    exit 1
}

$verifiedModules = @()
$pendingVerification = @()
if ($CheckVerification) {
    $projectRoot = Resolve-Ts800xProjectRoot -Uvprojx $projectFile
    $statePath = Get-Ts800xStatePath -ProjectRoot $projectRoot
    if (-not (Test-Path -LiteralPath $statePath)) {
        Write-Host "[FAIL] Verification state not found: $statePath"
        exit 1
    }
    $state = Read-Ts800xState -ProjectRoot $projectRoot
    if (@($state.modules.PSObject.Properties).Count -eq 0) {
        Write-Host "[FAIL] Verification state contains no modules."
        exit 1
    }
    foreach ($moduleProperty in $state.modules.PSObject.Properties) {
        $moduleState = $moduleProperty.Value
        $moduleStatus = [string]$moduleState.hardware_verify.status
        $coreReady = [string]$moduleState.build_after_code_quality.status -eq "pass" -and
            [string]$moduleState.dependency.status -eq "pass"
        if (-not $coreReady) {
            Write-Host "[FAIL] $($moduleProperty.Name) lacks build/code-quality/dependency evidence."
            exit 1
        }
        if ($moduleStatus -eq "pass") {
            $verifiedModules += $moduleProperty.Name
        } else {
            $pendingVerification += "$($moduleProperty.Name):$moduleStatus"
        }
    }
    if ($pendingVerification.Count -gt 0 -and -not $AllowPending) {
        Write-Host "[FAIL] Pending hardware verification: $($pendingVerification -join ', ')"
        exit 1
    }
}

$status = & git -C $gitRoot status --porcelain
if ($LASTEXITCODE -ne 0) { throw "git status failed" }
if (-not $status) {
    Write-Host "[INFO] No changes to commit."
    exit 0
}

if ($StageAll) {
    & git -C $gitRoot add -A
} elseif ($Paths.Count -gt 0) {
    & git -C $gitRoot add -- @Paths
} else {
    Write-Host "[FAIL] Refusing implicit 'git add -A'. Pass -Paths <files> or explicitly pass -StageAll."
    exit 1
}
if ($LASTEXITCODE -ne 0) { throw "git add failed" }

& git -C $gitRoot diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "[FAIL] No staged changes after applying the requested path scope."
    exit 1
}

$commitMessage = if ($Message -match '^(feat|fix|refactor|docs|chore|test):\s+') {
    $Message
} else {
    "$Type`: $Message"
}
& git -C $gitRoot commit -m $commitMessage
if ($LASTEXITCODE -ne 0) { throw "git commit failed" }
Write-Host "[PASS] Committed: $commitMessage"

if ($Push) {
    & git -C $gitRoot push
    if ($LASTEXITCODE -ne 0) { throw "git push failed" }
    Write-Host "[PASS] Pushed branch: $branch"
} else {
    Write-Host "[INFO] Push not requested."
}

$reportPath = if ([IO.Path]::IsPathRooted($ReportFile)) { $ReportFile } else { Join-Path $gitRoot $ReportFile }
$report = [ordered]@{
    timestamp = [DateTimeOffset]::Now.ToString("o")
    branch = $branch
    commit_message = $commitMessage
    build_result = if ($SkipBuild) { "SKIPPED" } else { "PASS" }
    verified_modules = $verifiedModules
    pending_verification = $pendingVerification
    pushed = [bool]$Push
}
$report | ConvertTo-Json -Depth 10 | Out-File -LiteralPath $reportPath -Encoding UTF8
Write-Host "[PASS] Commit report: $reportPath"
