param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"
# JLink DLL 目录注入 PATH
$jlinkDirs = @(
    "D:\Program Files\SEGGER\JLink_V820",
    "D:\Program Files\SEGGER\JLink",
    "C:\Program Files\SEGGER\JLink"
)
foreach ($jlinkDir in $jlinkDirs) {
    if ((Test-Path -LiteralPath $jlinkDir) -and ($env:PATH -notlike "*$jlinkDir*")) {
        $env:PATH = "$jlinkDir$([IO.Path]::PathSeparator)$env:PATH"
    }
}
$sourceRoot = Join-Path $PSScriptRoot "src"
$separator = [IO.Path]::PathSeparator
$env:PYTHONPATH = if ($env:PYTHONPATH) {
    "$sourceRoot$separator$env:PYTHONPATH"
} else {
    $sourceRoot
}

& python -X utf8 -m ts800x_jlink.cli @RemainingArgs
exit $LASTEXITCODE
