# Shared helpers for TS800X workflow status files.

function Initialize-Ts800xConsoleEncoding {
    try {
        chcp 65001 > $null
        [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
        [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
        $global:OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    } catch { }
}

function Resolve-Ts800xProjectRoot {
    param(
        [string]$ProjectRoot,
        [string]$Uvprojx,
        [string]$HexFile
    )

    if ($ProjectRoot) {
        return (Resolve-Path -LiteralPath $ProjectRoot).Path
    }

    $start = $null
    if ($Uvprojx) {
        $start = Split-Path -Parent (Resolve-Path -LiteralPath $Uvprojx).Path
    } elseif ($HexFile) {
        $start = Split-Path -Parent (Resolve-Path -LiteralPath $HexFile).Path
    } else {
        $start = (Get-Location).Path
    }

    $dir = Get-Item -LiteralPath $start
    while ($dir) {
        if (Test-Path -LiteralPath (Join-Path $dir.FullName "APP")) {
            return $dir.FullName
        }
        if (Test-Path -LiteralPath (Join-Path $dir.FullName ".git")) {
            return $dir.FullName
        }
        $dir = $dir.Parent
    }

    return (Resolve-Path -LiteralPath $start).Path
}

function Resolve-Ts800xUvprojx {
    param(
        [string]$ProjectRoot,
        [string]$Uvprojx
    )

    if ($Uvprojx) {
        return (Resolve-Path -LiteralPath $Uvprojx).Path
    }

    $candidates = @()
    $appMdk = Join-Path $ProjectRoot "APP\mdk"
    if (Test-Path -LiteralPath $appMdk) {
        $candidates += Get-ChildItem -LiteralPath $appMdk -Filter "*.uvprojx" -ErrorAction SilentlyContinue
    }
    $candidates += Get-ChildItem -LiteralPath $ProjectRoot -Recurse -Filter "*.uvprojx" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch "\\ts800x_sdk\\" }

    $unique = $candidates | Sort-Object FullName -Unique
    if ($unique.Count -eq 0) {
        throw "No .uvprojx found under $ProjectRoot"
    }
    if ($unique.Count -gt 1) {
        throw "Multiple .uvprojx files found. Pass -Uvprojx explicitly."
    }
    return $unique[0].FullName
}

function Get-Ts800xStatePath {
    param(
        [string]$ProjectRoot,
        [string]$StateFile
    )

    if ($StateFile) {
        return $StateFile
    }
    return (Join-Path $ProjectRoot "context\module_status.json")
}

function New-Ts800xStateObject {
    param([string]$ProjectRoot)

    return [ordered]@{
        schema_version = 2
        generated_at = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
        project_root = $ProjectRoot
        active_module = ""
        modules = [pscustomobject][ordered]@{}
        final_check = [ordered]@{}
    }
}

function Update-Ts800xStateSchema {
    param($State)

    if ($null -eq $State.modules) {
        $State | Add-Member -NotePropertyName modules -NotePropertyValue ([pscustomobject][ordered]@{}) -Force
    } elseif ($State.modules -is [System.Collections.IDictionary]) {
        $convertedModules = [pscustomobject][ordered]@{}
        foreach ($key in $State.modules.Keys) {
            $convertedModules | Add-Member -NotePropertyName ([string]$key) -NotePropertyValue $State.modules[$key]
        }
        $State.modules = $convertedModules
    }
    foreach ($moduleProperty in $State.modules.PSObject.Properties) {
        $entry = $moduleProperty.Value
        if ($null -eq $entry.PSObject.Properties["code_quality"]) {
            $legacyValue = if ($null -ne $entry.PSObject.Properties["simplify"]) {
                $entry.simplify
            } else {
                [ordered]@{ status = "pending"; timestamp = ""; evidence = "" }
            }
            $entry | Add-Member -NotePropertyName code_quality -NotePropertyValue $legacyValue
        }
        if ($null -eq $entry.PSObject.Properties["build_after_code_quality"]) {
            $legacyValue = if ($null -ne $entry.PSObject.Properties["build_after_simplify"]) {
                $entry.build_after_simplify
            } else {
                [ordered]@{ status = "pending"; timestamp = ""; evidence = "" }
            }
            $entry | Add-Member -NotePropertyName build_after_code_quality -NotePropertyValue $legacyValue
        }
        $entry.PSObject.Properties.Remove("simplify")
        $entry.PSObject.Properties.Remove("build_after_simplify")
    }
    $State.schema_version = 2
    return $State
}

function Read-Ts800xState {
    param(
        [string]$ProjectRoot,
        [string]$StateFile
    )

    $path = Get-Ts800xStatePath -ProjectRoot $ProjectRoot -StateFile $StateFile
    if (-not (Test-Path -LiteralPath $path)) {
        return New-Ts800xStateObject -ProjectRoot $ProjectRoot
    }

    $json = Get-Content -Raw -LiteralPath $path -Encoding UTF8
    if (-not $json.Trim()) {
        return New-Ts800xStateObject -ProjectRoot $ProjectRoot
    }

    $state = $json | ConvertFrom-Json
    return Update-Ts800xStateSchema -State $state
}

function Save-Ts800xState {
    param(
        $State,
        [string]$ProjectRoot,
        [string]$StateFile
    )

    $path = Get-Ts800xStatePath -ProjectRoot $ProjectRoot -StateFile $StateFile
    $dir = Split-Path -Parent $path
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $State.generated_at = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
    $State | ConvertTo-Json -Depth 20 | Out-File -LiteralPath $path -Encoding UTF8
    return $path
}

function Ensure-Ts800xModuleState {
    param(
        $State,
        [string]$Module,
        [string[]]$SourceFiles
    )

    if (-not $Module) {
        throw "Module name is required."
    }

    if ($null -eq $State.modules) {
        $State | Add-Member -NotePropertyName modules -NotePropertyValue ([pscustomobject][ordered]@{})
    }

    $modules = $State.modules
    if ($null -eq $modules.PSObject.Properties[$Module]) {
        $moduleState = [pscustomobject][ordered]@{
            module = $Module
            source_files = @()
            build_initial = [ordered]@{ status = "pending"; timestamp = ""; evidence = "" }
            code_quality = [ordered]@{ status = "pending"; timestamp = ""; evidence = "" }
            build_after_code_quality = [ordered]@{ status = "pending"; timestamp = ""; evidence = "" }
            dependency = [ordered]@{ status = "pending"; timestamp = ""; evidence = "" }
            flash = [ordered]@{ status = "pending"; timestamp = ""; evidence = "" }
            hardware_verify = [ordered]@{ status = "pending"; timestamp = ""; evidence = "" }
        }
        $modules | Add-Member -NotePropertyName $Module -NotePropertyValue $moduleState
    }

    $entry = $modules.$Module
    if ($SourceFiles -and $SourceFiles.Count -gt 0) {
        $entry.source_files = @($SourceFiles | Where-Object { $_ } | Sort-Object -Unique)
    }
    $State.active_module = $Module
    return $entry
}

function Set-Ts800xStepStatus {
    param(
        $Entry,
        [string]$Step,
        [string]$Status,
        [string]$Evidence
    )

    if ($null -eq $Entry.PSObject.Properties[$Step]) {
        $Entry | Add-Member -NotePropertyName $Step -NotePropertyValue ([ordered]@{})
    }
    $Entry.$Step.status = $Status
    $Entry.$Step.timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
    $Entry.$Step.evidence = $Evidence
}
