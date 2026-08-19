<#
.SYNOPSIS
    一键启动 GUI（Windows）：用 .venv 的 python 运行 gui.py。

.DESCRIPTION
    未配置 .venv 时提示先运行 scripts\setup.ps1。多余参数会透传给 gui.py。
    一键运行（右键「使用 PowerShell 运行」，或执行）：
        powershell -ExecutionPolicy Bypass -File scripts\run_gui.ps1

.EXAMPLE
    .\scripts\run_gui.ps1
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PassThru
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Error "未找到 .venv，请先运行:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1"
    exit 1
}

Push-Location $root
try {
    & $venvPy gui.py @PassThru
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
