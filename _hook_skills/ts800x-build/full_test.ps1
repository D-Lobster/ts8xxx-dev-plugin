param(
    [Parameter(Mandatory = $true)]
    [string]$Uvprojx,
    [string]$Module = "",
    [string]$FlashEvidence = "",
    [string]$Port = "",
    [string]$LogFile = "",
    [int]$Duration = 15,
    [string]$Expect = "",
    [string]$TestName = "test_$(Get-Date -Format 'yyyyMMdd_HHmmss')",
    [switch]$SkipBuild,
    [switch]$Rebuild,
    [switch]$NoHardware
)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$workflowRoot = Split-Path (Split-Path $scriptDir -Parent) -Parent
$stateHelper = Join-Path $scriptDir "workflow_state.ps1"
$buildScript = Join-Path $scriptDir "build.ps1"
$uartScript = Join-Path $workflowRoot "_hook_skills\ts800x-log-system\uart_capture.py"
$analyzeScript = Join-Path $workflowRoot "_hook_skills\ts800x-log-system\log_analyze.py"
. $stateHelper
Initialize-Ts800xConsoleEncoding

function Save-FullTestReport {
    param([hashtable]$Results, [string]$Path)
    $Results.timestamp = [DateTimeOffset]::Now.ToString("o")
    $Results | ConvertTo-Json -Depth 20 | Out-File -LiteralPath $Path -Encoding UTF8
    Write-Host "[INFO] Full test report: $Path"
}

function Test-FlashEvidence {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $evidence = Get-Content -Raw -LiteralPath $Path -Encoding UTF8 | ConvertFrom-Json
        $verified = [string]$evidence.verify -eq "PASS" -or $evidence.matched -eq $true
        if (-not $verified -and $evidence.result) {
            $verified = [string]$evidence.result.verify -eq "PASS" -or $evidence.result.matched -eq $true
        }
        return $evidence.success -eq $true -and $verified
    } catch {
        return $false
    }
}

$projectFile = (Resolve-Path -LiteralPath $Uvprojx).Path
$projectRoot = Resolve-Ts800xProjectRoot -Uvprojx $projectFile
$state = Read-Ts800xState -ProjectRoot $projectRoot
if (-not $Module) { $Module = [string]$state.active_module }
$moduleState = if ($Module -and $null -ne $state.modules.PSObject.Properties[$Module]) {
    $state.modules.$Module
} else { $null }

$reportDir = Join-Path $projectRoot "reports"
$logDir = Join-Path $projectRoot "logs"
foreach ($directory in @($reportDir, $logDir)) {
    if (-not (Test-Path -LiteralPath $directory)) { New-Item -ItemType Directory -Path $directory -Force | Out-Null }
}
$fullReport = Join-Path $reportDir "$TestName.full.json"
$analysisReport = Join-Path $reportDir "$TestName.log.json"
$captureFile = if ($LogFile) { [IO.Path]::GetFullPath($LogFile) } else { Join-Path $logDir "$TestName.log" }
$results = @{
    test_name = $TestName
    project = $projectRoot
    module = $Module
    build = "SKIP"
    flash = "FAIL"
    capture = "SKIP"
    analyze = "SKIP"
    hardware_status = "UNVERIFIED"
}

if (-not $SkipBuild) {
    $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $buildScript, "-Uvprojx", $projectFile)
    if ($Rebuild) { $arguments += "-Rebuild" }
    & powershell.exe @arguments
    if ($LASTEXITCODE -ne 0) {
        $results.build = "FAIL"
        Save-FullTestReport -Results $results -Path $fullReport
        exit 1
    }
    $results.build = "PASS"
}

if ($NoHardware) {
    $results.flash = "PENDING_HARDWARE"
    $results.hardware_status = "PENDING_HARDWARE"
    Save-FullTestReport -Results $results -Path $fullReport
    if ($null -ne $moduleState) {
        Set-Ts800xStepStatus -Entry $moduleState -Step "hardware_verify" `
            -Status "pending_hardware" -Evidence $fullReport
        Save-Ts800xState -State $state -ProjectRoot $projectRoot | Out-Null
    }
    Write-Host "[PENDING] Build complete; hardware test was explicitly unavailable."
    exit 2
}

if (-not (Test-FlashEvidence $FlashEvidence)) {
    Write-Host "[STOP] This script does not flash directly. Use the ts800x-flash CLI (run_cli.ps1 flash) and save its JSON result."
    Write-Host "[NEXT] Rerun with -FlashEvidence <verified-flash-result.json>."
    Save-FullTestReport -Results $results -Path $fullReport
    exit 2
}
$results.flash = "PASS"
if ($null -ne $moduleState) {
    Set-Ts800xStepStatus -Entry $moduleState -Step "flash" -Status "pass" `
        -Evidence $FlashEvidence
    Save-Ts800xState -State $state -ProjectRoot $projectRoot | Out-Null
}

if ($Port) {
    $captureArgs = @(
        $uartScript, "--port", $Port, "--duration", [string]$Duration,
        "--output", $captureFile
    )
    if ($Expect) { $captureArgs += @("--expect", $Expect) }
    & python @captureArgs
    if ($LASTEXITCODE -ne 0) {
        $results.capture = "FAIL"
        Save-FullTestReport -Results $results -Path $fullReport
        exit $LASTEXITCODE
    }
    $results.capture = "PASS"
} elseif (Test-Path -LiteralPath $captureFile) {
    $results.capture = "PASS_EXTERNAL"
} else {
    Write-Host "[STOP] Provide -Port for UART, or capture RTT with the ts800x-flash CLI (run_cli.ps1 rtt) and pass -LogFile."
    Save-FullTestReport -Results $results -Path $fullReport
    exit 2
}

$analyzeArgs = @($analyzeScript, "--log", $captureFile, "--output", $analysisReport)
if ($Expect) { $analyzeArgs += @("--expect", $Expect) }
& python @analyzeArgs
$analysisExit = $LASTEXITCODE
$results.analyze = if ($analysisExit -eq 0) { "PASS" } else { "FAIL" }
$results.hardware_status = if ($analysisExit -eq 0) { "LOG_VERIFIED" } else { "FAILED" }
Save-FullTestReport -Results $results -Path $fullReport
if ($null -ne $moduleState) {
    $hardwareState = if ($analysisExit -eq 0) { "pass" } else { "fail" }
    Set-Ts800xStepStatus -Entry $moduleState -Step "hardware_verify" `
        -Status $hardwareState -Evidence $fullReport
    Save-Ts800xState -State $state -ProjectRoot $projectRoot | Out-Null
}
exit $analysisExit
