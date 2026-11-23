# TS800X 自动化检查脚本（通用版）
# Usage: powershell -File auto_check.ps1 -Check <type> [-SourceDir <path>] [-LogFile <path>] [-MapFile <path>]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("banned_functions", "isr_logging", "flash_layout", "stack_size", "compile_output")]
    [string]$Check,

    [string]$SourceDir = ".\APP\source",
    [string]$LogFile = ".\APP\mdk\obj\ble_project.build_log.htm",
    [string]$MapFile = ".\APP\mdk\obj\ble_project.map",
    [string]$StartupFile = ".\ts800x_sdk\startup\ts800x_startup_gcc.S",
    [string]$LdFile = ".\cmake_env\ld\ts8001_BLE.ld"
)

$ErrorActionPreference = "Stop"
$script:ErrorCount = 0
$script:WarningCount = 0

function Get-CheckResult {
    param($CheckName, $Passed, $Message)
    return @{
        Check = $CheckName
        Status = if ($Passed) { "PASS" } else { "FAIL" }
        Message = $Message
    }
}

$Results = @()

switch ($Check) {
    "banned_functions" {
        if (-not (Test-Path -LiteralPath $SourceDir)) {
            $Results += Get-CheckResult "banned_functions" $false "Source directory not found: $SourceDir"
            break
        }
        $banned = @("delay_ms", "HAL_Delay", "malloc", "free")
        $found = @()
        Get-ChildItem -LiteralPath $SourceDir -Filter "*.c" -Recurse | ForEach-Object {
            $content = Get-Content -LiteralPath $_.FullName -Raw
            foreach ($func in $banned) {
                if ($content -match ("\b" + [regex]::Escape($func) + "\s*\(")) {
                    $found += "$($_.Name): contains '$func'"
                }
            }
        }
        if ($found.Count -eq 0) {
            $Results += Get-CheckResult "banned_functions" $true "No banned functions found"
        } else {
            $Results += Get-CheckResult "banned_functions" $false ($found -join "; ")
        }
    }

    "isr_logging" {
        if (-not (Test-Path -LiteralPath $SourceDir)) {
            $Results += Get-CheckResult "isr_logging" $false "Source directory not found: $SourceDir"
            break
        }
        $isrLogPatterns = @("\bLOG(?:_[A-Z]+)?\s*\(", "\bprintf\s*\(", "SEGGER_RTT", "SEGGER_printf")
        $found = @()
        Get-ChildItem -LiteralPath $SourceDir -Filter "*.c" -Recurse | ForEach-Object {
            $lines = Get-Content -LiteralPath $_.FullName
            for ($i = 0; $i -lt $lines.Count; $i++) {
                $line = $lines[$i]
                if ($line -match "\b(?:\w+_IRQHandler|\w*ISR\w*)\s*\(" -or
                    $line -match "__attribute__\s*\(\(\s*interrupt\s*\)\)") {
                    $braceDepth = 0
                    $enteredBody = $false
                    for ($j = $i; $j -lt [Math]::Min($i + 200, $lines.Count); $j++) {
                        foreach ($pattern in $isrLogPatterns) {
                            if ($lines[$j] -match $pattern) {
                                $found += "$($_.Name):$($j+1): contains '$pattern' in ISR"
                                break
                            }
                        }
                        $braceDepth += ([regex]::Matches($lines[$j], "\{")).Count
                        $braceDepth -= ([regex]::Matches($lines[$j], "\}")).Count
                        if ($braceDepth -gt 0) { $enteredBody = $true }
                        if ($enteredBody -and $braceDepth -le 0) { break }
                    }
                }
            }
        }
        if ($found.Count -eq 0) {
            $Results += Get-CheckResult "isr_logging" $true "No LOG in ISRs"
        } else {
            $Results += Get-CheckResult "isr_logging" $false ($found -join "; ")
        }
    }

    "compile_output" {
        if (-not (Test-Path $LogFile)) {
            $Results += Get-CheckResult "compile_output" $false "Log file not found: $LogFile"
        } else {
            $content = Get-Content $LogFile -Raw
            $errMatches = [regex]::Matches($content, "error:")
            $warnMatches = [regex]::Matches($content, "warning:")
            $script:ErrorCount = $errMatches.Count
            $script:WarningCount = $warnMatches.Count

            if ($script:ErrorCount -eq 0 -and $script:WarningCount -eq 0) {
                $Results += Get-CheckResult "compile_output" $true "errors: 0, warnings: 0"
            } else {
                $msg = "errors: $script:ErrorCount, warnings: $script:WarningCount"
                $Results += Get-CheckResult "compile_output" $false $msg
            }
        }
    }

    "flash_layout" {
        if (-not (Test-Path $MapFile)) {
            $Results += Get-CheckResult "flash_layout" $false "Map file not found: $MapFile"
        } else {
            $content = Get-Content $MapFile -Raw
            $issues = @()

            if ($content -match "VectorTable\s+0x([0-9a-fA-F]+)") {
                $vtAddr = $Matches[1]
                if ($vtAddr -notin @("00000000", "10000000")) {
                    $issues += "VectorTable at 0x$vtAddr (expected 0x00000000 or 0x10000000)"
                }
            }

            if ($issues.Count -eq 0) {
                $Results += Get-CheckResult "flash_layout" $true "VectorTable: OK"
            } else {
                $Results += Get-CheckResult "flash_layout" $false ($issues -join "; ")
            }
        }
    }

    "stack_size" {
        $startupStack = $null
        $ldStack = $null

        if (Test-Path $StartupFile) {
            $startupContent = Get-Content $StartupFile -Raw
            if ($startupContent -match "Stack_Size\s+EQU\s+0x([0-9a-fA-F]+)") {
                $startupStack = [int]("0x$($Matches[1])")
            } elseif ($startupContent -match "Stack_Size\s+=\s+0x([0-9a-fA-F]+)") {
                $startupStack = [int]("0x$($Matches[1])")
            }
        }

        if (Test-Path $LdFile) {
            $ldContent = Get-Content $LdFile -Raw
            if ($ldContent -match "Stack_Size\s+=\s+0x([0-9a-fA-F]+)") {
                $ldStack = [int]("0x$($Matches[1])")
            }
        }

        if ($null -eq $startupStack -or $null -eq $ldStack) {
            $Results += Get-CheckResult "stack_size" $false "Could not parse Stack_Size (startup=$startupStack, ld=$ldStack)"
        } elseif ($startupStack -eq $ldStack) {
            $Results += Get-CheckResult "stack_size" $true "Stack_Size: OK (0x$($startupStack.ToString('x8')))"
        } else {
            $Results += Get-CheckResult "stack_size" $false "Stack_Size: MISMATCH (startup=0x$($startupStack.ToString('x8')), ld=0x$($ldStack.ToString('x8')))"
        }
    }
}

# Output results
foreach ($r in $Results) {
    $statusStr = if ($r.Status -eq "PASS") { "[PASS]" } else { "[FAIL]" }
    Write-Host "$statusStr $($r.Check): $($r.Message)"
}

$allPass = ($Results | Where-Object { $_.Status -eq "PASS" }).Count -eq $Results.Count
exit $(if ($allPass) { 0 } else { 1 })
