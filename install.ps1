# TS800X 工作流 DeepSeek Harness 插件安装脚本（独立版，无需工作流仓库）
#
# 本脚本随「ts8xxx-dev-plugin」文件夹一起分发。运行后会把本文件夹安装到
# $DSH_HOME/plugins/ts800x-workflow，然后：
#   1. 把 cordis.patch.yml 中的预设声明合并进 DSH profile 的 patch 层（托管块，可 -Check 校验）；
#   2. 把 _hook_skills 下的技能以 Junction（目录链接）装到 agent 技能目录（默认 ~/.agents/skills）；
#   3. 设置用户环境变量 TS800X_WORKFLOW_ROOT 指向安装目录；
#   4. 可选：调用已安装 DSH 的解析器校验 patch。
#
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Check
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -DryRun
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Uninstall
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Profile web -Force
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Mode Copy
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -NoCopy
[CmdletBinding()]
param(
    # DSH profile 名；默认读 workflow.manifest.json 的 hosts.deepseek.preset_profile
    [string]$Profile,
    # Junction：技能目录链接（推荐）；Copy：技能目录复制
    [ValidateSet("Junction", "Copy")]
    [string]$Mode = "Junction",
    # 已存在同名技能/托管块时强制替换
    [switch]$Force,
    # 只校验，不写任何文件
    [switch]$Check,
    # 只打印计划，不写文件
    [switch]$DryRun,
    # 卸载：移除托管块、技能链接与安装目录
    [switch]$Uninstall,
    # 不复制到安装目录，直接使用当前文件夹
    [switch]$NoCopy,
    # 不设置 TS800X_WORKFLOW_ROOT 用户环境变量
    [switch]$NoSetEnv,
    # 不调用 DSH 解析器校验 patch
    [switch]$NoValidate
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$sourceDir = $PSScriptRoot
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Fail {
    param([string]$Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
    exit 1
}

function Info {
    param([string]$Message)
    Write-Host "       $Message" -ForegroundColor Gray
}

$manifestPath = Join-Path $sourceDir "workflow.manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    Fail "workflow.manifest.json not found beside install.ps1; this folder is not a complete plugin package"
}
$manifest = Get-Content -Raw -LiteralPath $manifestPath -Encoding UTF8 | ConvertFrom-Json
$workflowVersion = [string]$manifest.workflow_version
$deepseek = $manifest.hosts.deepseek
if ($null -eq $deepseek) { Fail "workflow.manifest.json has no hosts.deepseek entry" }

$presetId = [string]$deepseek.preset_id
if ([string]::IsNullOrWhiteSpace($presetId)) { $presetId = "ts8xxx-dev" }
$patchFileName = [string]$deepseek.preset_patch
if ([string]::IsNullOrWhiteSpace($patchFileName)) { $patchFileName = "cordis.patch.yml" }
$profileName = if ([string]::IsNullOrWhiteSpace($Profile)) { [string]$deepseek.preset_profile } else { $Profile }
if ([string]::IsNullOrWhiteSpace($profileName)) { $profileName = "desktop" }

$sourcePatch = Join-Path $sourceDir $patchFileName
if (-not (Test-Path -LiteralPath $sourcePatch)) {
    Fail "preset patch is missing: $sourcePatch"
}

$userHome = [Environment]::GetFolderPath("UserProfile")
$dshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $userHome ".dsh" }
$agentsHome = if ($env:DSH_AGENTS_HOME) { $env:DSH_AGENTS_HOME } else { Join-Path $userHome ".agents" }
$managedDir = Join-Path $dshHome "plugins\ts800x-workflow"
$profileDir = Join-Path (Join-Path $dshHome "profiles") $profileName
$targetPatch = Join-Path $profileDir $patchFileName
$skillsRoot = Join-Path $agentsHome "skills"

$markerBegin = "# >>> $presetId preset (managed by sync_dsh_preset.ps1) >>>"
$markerEnd = "# <<< $presetId preset <<<"

function Normalize-PatchText {
    param([string]$Text)
    $lines = @(
        ($Text -replace "`r`n", "`n") -split "`n" |
            ForEach-Object { $_.TrimEnd() } |
            Where-Object { $_.Trim().Length -gt 0 }
    )
    return ($lines -join "`n")
}

function Get-SourceBlockText {
    param([string]$PatchPath)
    $text = [IO.File]::ReadAllText($PatchPath, $utf8)
    $text = ($text -replace "`r`n", "`n").TrimEnd("`n") + "`n"
    return ($markerBegin + "`n" + $text + $markerEnd + "`n")
}

# 判断技能目录链接是否指向本插件的技能源目录
function Test-JunctionTarget {
    param([string]$LinkPath, [string]$ExpectedTarget)
    if (-not (Test-Path -LiteralPath $LinkPath)) { return $false }
    $item = Get-Item -LiteralPath $LinkPath -ErrorAction SilentlyContinue
    if ($null -eq $item) { return $false }
    if ($item.LinkType -ne "Junction" -and $item.LinkType -ne "SymbolicLink") { return $false }
    $target = @($item.Target)[0]
    if ([string]::IsNullOrWhiteSpace($target)) { return $false }
    return ((Get-NormalizedPath $target) -eq (Get-NormalizedPath $ExpectedTarget))
}

function Get-NormalizedPath {
    param([string]$Path)
    return [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
}

function Find-DshInstallRoot {
    $candidates = New-Object System.Collections.Generic.List[string]
    $command = Get-Command dsh -ErrorAction SilentlyContinue
    if ($null -ne $command -and -not [string]::IsNullOrWhiteSpace($command.Source)) {
        $candidates.Add((Split-Path -Parent $command.Source))
    }
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $candidates.Add((Join-Path $env:LOCALAPPDATA "pi-node\current"))
    }
    foreach ($candidate in $candidates) {
        $manifestFile = Join-Path $candidate "node_modules\@deepseek-ai\dsh\package.json"
        if (Test-Path -LiteralPath $manifestFile) {
            return (Split-Path -Parent $manifestFile)
        }
    }
    return $null
}

function Invoke-PatchValidation {
    param([string]$ComposedText)
    if ($NoValidate) { return }
    $validator = Join-Path $sourceDir "check_preset_patch.mjs"
    if (-not (Test-Path -LiteralPath $validator)) {
        Write-Host "[WARN] check_preset_patch.mjs is missing; patch validation skipped" -ForegroundColor Yellow
        return
    }
    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($null -eq $node) {
        Write-Host "[WARN] node not found; patch validation skipped" -ForegroundColor Yellow
        return
    }
    $dshRoot = Find-DshInstallRoot
    if ($null -eq $dshRoot) {
        Write-Host "[WARN] DSH installation not found; patch validation skipped" -ForegroundColor Yellow
        return
    }
    $probeFile = Join-Path ([IO.Path]::GetTempPath()) ("ts800x-preset-" + [guid]::NewGuid().ToString("N") + ".yml")
    [IO.File]::WriteAllText($probeFile, $ComposedText, $utf8)
    $previousRoot = $env:DSH_ROOT
    $previousEap = $ErrorActionPreference
    try {
        $env:DSH_ROOT = $dshRoot
        $ErrorActionPreference = "Continue"
        $output = & node $validator $probeFile 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousEap
        $env:DSH_ROOT = $previousRoot
        Remove-Item -LiteralPath $probeFile -Force -ErrorAction SilentlyContinue
    }
    $lines = @($output) |
        ForEach-Object { [string]$_ } |
        Where-Object { $_ -notmatch 'UNDICI-EHPA|trace-warnings|NativeCommandError|CategoryInfo|FullyQualifiedErrorId|^\s*At line:|^\s*\+' }
    foreach ($line in $lines) { Info $line }
    if ($code -eq 1) { Fail "composed patch rejected by the harness validator; nothing was written" }
    if ($code -ne 0 -and $code -ne 3) { Fail "patch validator failed with exit code $code; nothing was written" }
}

# ---------------------------------------------------------------- 卸载
if ($Uninstall) {
    $removed = 0
    if (Test-Path -LiteralPath $targetPatch) {
        $current = [IO.File]::ReadAllText($targetPatch, $utf8)
        if ($current.Contains($markerBegin) -and $current.Contains($markerEnd)) {
            $pattern = "(?s)" + [regex]::Escape($markerBegin) + ".*?" + [regex]::Escape($markerEnd) + "\r?\n?"
            $current = ([regex]::new($pattern)).Replace($current, "", 1).TrimEnd() + "`n"
            if ($DryRun) {
                Write-Host "[PLAN] remove managed block from $targetPatch"
            } else {
                [IO.File]::WriteAllText($targetPatch, $current, $utf8)
                Write-Host "[PASS] removed managed block from $targetPatch"
            }
            $removed++
        }
    }
    if (Test-Path -LiteralPath $skillsRoot) {
        foreach ($child in Get-ChildItem -LiteralPath $skillsRoot -Directory -ErrorAction SilentlyContinue) {
            if (Test-JunctionTarget -LinkPath $child.FullName -ExpectedTarget (Join-Path $managedDir "_hook_skills\$($child.Name)")) {
                if ($DryRun) {
                    Write-Host "[PLAN] remove skill link $($child.FullName)"
                } else {
                    (Get-Item -LiteralPath $child.FullName).Delete()
                    Write-Host "[PASS] removed skill link $($child.FullName)"
                }
                $removed++
            }
        }
    }
    if (Test-Path -LiteralPath $managedDir) {
        if ($DryRun) {
            Write-Host "[PLAN] remove install directory $managedDir"
        } else {
            Remove-Item -LiteralPath $managedDir -Recurse -Force
            Write-Host "[PASS] removed install directory $managedDir"
        }
    }
    $envValue = [Environment]::GetEnvironmentVariable("TS800X_WORKFLOW_ROOT", "User")
    if (-not $DryRun -and $envValue -and (Get-NormalizedPath $envValue) -eq (Get-NormalizedPath $managedDir)) {
        [Environment]::SetEnvironmentVariable("TS800X_WORKFLOW_ROOT", $null, "User")
        Write-Host "[PASS] cleared user TS800X_WORKFLOW_ROOT"
    }
    if ($removed -eq 0) { Write-Host "[INFO] nothing to uninstall" }
    Write-Host "[NEXT] restart the DSH host so the preset disappears from the roster."
    exit 0
}

# ---------------------------------------------------------------- 校验
if ($Check) {
    $ok = $true

    if (-not (Test-Path -LiteralPath $managedDir)) {
        Write-Host "[FAIL] install directory missing: $managedDir" -ForegroundColor Red
        $ok = $false
    } else {
        $installedVersion = ""
        $installedManifest = Join-Path $managedDir "workflow.manifest.json"
        if (Test-Path -LiteralPath $installedManifest) {
            $installedVersion = [string](Get-Content -Raw -LiteralPath $installedManifest -Encoding UTF8 | ConvertFrom-Json).workflow_version
        }
        if ($installedVersion -ne $workflowVersion) {
            Write-Host "[FAIL] installed version '$installedVersion' != package version '$workflowVersion'" -ForegroundColor Red
            $ok = $false
        } else {
            Write-Host "[PASS] installed version $installedVersion"
        }
    }

    if (-not (Test-Path -LiteralPath $targetPatch)) {
        Write-Host "[FAIL] profile patch missing: $targetPatch" -ForegroundColor Red
        $ok = $false
    } else {
        $current = [IO.File]::ReadAllText($targetPatch, $utf8)
        if (-not $current.Contains($markerBegin) -or -not $current.Contains($markerEnd)) {
            Write-Host "[FAIL] managed preset block missing in $targetPatch" -ForegroundColor Red
            $ok = $false
        } else {
            $pattern = "(?s)" + [regex]::Escape($markerBegin) + ".*?" + [regex]::Escape($markerEnd)
            $installedBlock = [regex]::Match($current, $pattern).Value
            $expectedBlock = Get-SourceBlockText -PatchPath (Join-Path $managedDir $patchFileName)
            if ((Normalize-PatchText $installedBlock) -ne (Normalize-PatchText $expectedBlock)) {
                Write-Host "[FAIL] managed preset block differs from the installed package" -ForegroundColor Red
                $ok = $false
            } else {
                Write-Host "[PASS] managed preset block is current"
            }
        }
    }

    $hookSkillsDir = Join-Path $managedDir "_hook_skills"
    $missingLinks = 0
    if (Test-Path -LiteralPath $hookSkillsDir) {
        foreach ($skill in Get-ChildItem -LiteralPath $hookSkillsDir -Directory) {
            $link = Join-Path $skillsRoot $skill.Name
            if (-not (Test-JunctionTarget -LinkPath $link -ExpectedTarget $skill.FullName)) {
                if (Test-Path -LiteralPath $link) {
                    Write-Host "[WARN] $($skill.Name): existing entry in $skillsRoot is not this package's link" -ForegroundColor Yellow
                } else {
                    $missingLinks++
                }
            }
        }
        if ($missingLinks -gt 0) {
            Write-Host "[FAIL] $missingLinks skill link(s) missing under $skillsRoot" -ForegroundColor Red
            $ok = $false
        } else {
            Write-Host "[PASS] skill links under $skillsRoot"
        }
    } else {
        Write-Host "[FAIL] _hook_skills missing in $managedDir" -ForegroundColor Red
        $ok = $false
    }

    $envValue = [Environment]::GetEnvironmentVariable("TS800X_WORKFLOW_ROOT", "User")
    if ([string]::IsNullOrWhiteSpace($envValue)) {
        Write-Host "[WARN] user TS800X_WORKFLOW_ROOT is not set" -ForegroundColor Yellow
    } elseif ((Get-NormalizedPath $envValue) -ne (Get-NormalizedPath $managedDir)) {
        Write-Host "[WARN] user TS800X_WORKFLOW_ROOT points to $envValue (expected $managedDir)" -ForegroundColor Yellow
    } else {
        Write-Host "[PASS] TS800X_WORKFLOW_ROOT = $managedDir"
    }

    if (-not $ok) { exit 1 }
    Write-Host "[PASS] ts8xxx-dev-plugin $workflowVersion is installed and current"
    exit 0
}

# ---------------------------------------------------------------- 安装 / 更新
if (-not (Test-Path -LiteralPath (Join-Path $profileDir "package.json"))) {
    Fail "DSH profile '$profileName' not found at $profileDir. Launch that profile once so DSH creates it, or pass -Profile <name>."
}

$action = "install"
$installSource = $sourceDir
if ($NoCopy) {
    if ((Get-NormalizedPath $sourceDir) -ne (Get-NormalizedPath $managedDir)) {
        Write-Host "[INFO] -NoCopy: using $sourceDir in place"
    }
} else {
    if ((Get-NormalizedPath $sourceDir) -ne (Get-NormalizedPath $managedDir)) {
        $action = if (Test-Path -LiteralPath $managedDir) { "update" } else { "install" }
        if ($sourceDir.StartsWith((Get-NormalizedPath $managedDir) + '\')) {
            Fail "source folder is inside the install directory; move it elsewhere first"
        }
        if ($DryRun) {
            Write-Host "[PLAN] copy $sourceDir -> $managedDir"
        } else {
            if (Test-Path -LiteralPath $managedDir) {
                Remove-Item -LiteralPath $managedDir -Recurse -Force
            }
            New-Item -ItemType Directory -Path (Split-Path -Parent $managedDir) -Force | Out-Null
            Copy-Item -LiteralPath $sourceDir -Destination $managedDir -Recurse -Force
            Write-Host "[PASS] copied plugin to $managedDir"
        }
        $installSource = $managedDir
    } else {
        Write-Host "[INFO] already running from the install directory $managedDir"
    }
}

# 1) 合并预设声明到 profile patch 层
$sourceFile = Join-Path $installSource $patchFileName
$blockText = Get-SourceBlockText -PatchPath $sourceFile
$currentText = $null
if (Test-Path -LiteralPath $targetPatch) {
    $currentText = [IO.File]::ReadAllText($targetPatch, $utf8)
}
if ($null -ne $currentText -and $currentText.Contains($markerBegin)) {
    $pattern = "(?s)" + [regex]::Escape($markerBegin) + ".*?" + [regex]::Escape($markerEnd) + "\r?\n?"
    $evaluator = [System.Text.RegularExpressions.MatchEvaluator] { param($match) $blockText }
    $newText = ([regex]::new($pattern)).Replace($currentText, $evaluator, 1)
    $mergeAction = "update"
} elseif ($null -ne $currentText -and $currentText.Contains($presetId)) {
    Fail "$targetPatch already declares '$presetId' outside the managed block; remove that declaration and rerun"
} elseif ($null -eq $currentText -or $currentText.Trim().Length -eq 0 -or $currentText.Trim() -eq "[]") {
    $newText = "# DSH profile patch layer: applied after every bundle layer." + "`n" + $blockText
    $mergeAction = "install"
} else {
    $newText = $currentText.TrimEnd() + "`n`n" + $blockText
    $mergeAction = "install"
}

if ((Normalize-PatchText $newText) -eq (Normalize-PatchText ([string]$currentText))) {
    Write-Host "[PASS] preset '$presetId' already current in $targetPatch"
} else {
    if ($DryRun) {
        Write-Host "[PLAN] $mergeAction preset '$presetId' into $targetPatch"
    } else {
        Invoke-PatchValidation -ComposedText $newText
        if (Test-Path -LiteralPath $targetPatch) {
            $backup = "$targetPatch.bak-" + (Get-Date -Format "yyyyMMdd-HHmmss")
            Copy-Item -LiteralPath $targetPatch -Destination $backup -Force
            Write-Host "[BACKUP] $backup"
        }
        [IO.File]::WriteAllText($targetPatch, $newText, $utf8)
        Write-Host "[PASS] $mergeAction preset '$presetId' into $targetPatch"
    }
}

# 2) 技能目录链接
$hookSkillsDir = Join-Path $installSource "_hook_skills"
if (-not (Test-Path -LiteralPath $hookSkillsDir)) {
    Fail "_hook_skills is missing in $installSource; the package is incomplete"
}
if (-not $DryRun) {
    New-Item -ItemType Directory -Path $skillsRoot -Force | Out-Null
}
$linked = 0
$skipped = 0
foreach ($skill in Get-ChildItem -LiteralPath $hookSkillsDir -Directory) {
    $target = Join-Path $skillsRoot $skill.Name
    if (Test-JunctionTarget -LinkPath $target -ExpectedTarget $skill.FullName) {
        continue
    }
    if (Test-Path -LiteralPath $target) {
        if (-not $Force) {
            Write-Host "[WARN] $skillsRoot\$($skill.Name) exists and is not this package's link; skipped (use -Force to replace)" -ForegroundColor Yellow
            $skipped++
            continue
        }
        if ($DryRun) {
            Write-Host "[PLAN] replace $target"
        } else {
            (Get-Item -LiteralPath $target -Force).Delete()
        }
    }
    if ($DryRun) {
        Write-Host "[PLAN] link $skillsRoot\$($skill.Name) -> $($skill.FullName)"
    } elseif ($Mode -eq "Junction") {
        New-Item -ItemType Junction -Path $target -Target $skill.FullName | Out-Null
    } else {
        Copy-Item -LiteralPath $skill.FullName -Destination $target -Recurse -Force
    }
    $linked++
}
if ($skipped -gt 0) {
    Write-Host "[WARN] $skipped skill(s) skipped; rerun with -Force to replace existing entries" -ForegroundColor Yellow
}

# 3) 环境变量
if (-not $NoSetEnv) {
    if ($DryRun) {
        Write-Host "[PLAN] set user TS800X_WORKFLOW_ROOT=$installSource"
    } else {
        [Environment]::SetEnvironmentVariable("TS800X_WORKFLOW_ROOT", $installSource, "User")
        Write-Host "[PASS] set user TS800X_WORKFLOW_ROOT=$installSource"
    }
}

Write-Host ""
Write-Host "[PASS] ts8xxx-dev-plugin $workflowVersion installed (skills linked: $linked)"
Write-Host "[NEXT] 1) 重启 DeepSeek Harness（Web 端刷新页面）；2) 新建会话时在预设选择器中选择「TS8XXX 系列开发」；"
Write-Host "[NEXT] 3) 需要校验时运行 install.ps1 -Check；卸载运行 install.ps1 -Uninstall"
