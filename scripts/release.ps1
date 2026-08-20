<#
.SYNOPSIS
    本地一键发布：构建 frozen exe → 7z 最大压缩 → 创建 GitHub Release。

.DESCRIPTION
    参考 RaceVideoToLog 的发布流程：
      1. 读取 pyproject.toml 的 version（单一事实源）
      2. 检查 tag v<version> 是否已存在
      3. scripts/build_exe.ps1 构建 onedir exe
      4. 7-Zip LZMA2 -mx=9 打包 dist\VideoSubtitleExtractor\* → VideoSubtitleExtractor.<version>.7z
      5. gh release create v<version> <7z> --title v<version> --notes-file（取 release_notes.md 对应节）

    依赖：git、python、gh、7-Zip（C:\Program Files\7-Zip\7z.exe 或 PATH 中 7z）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\release.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# ── 1. 版本 ──
$ver = (& python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()
if (-not $ver) { Write-Error "读取版本失败"; exit 1 }
Write-Host "[release] version = $ver" -ForegroundColor Cyan

if (git tag -l "v$ver") {
    Write-Error "tag v$ver 已存在。如需重新发布请先删除 tag，或先在 pyproject.toml 升版本。"
    exit 1
}

# ── 2. 构建 exe ──
Write-Host "[release] 构建 frozen exe ..." -ForegroundColor Cyan
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "scripts\build_exe.ps1")
if ($LASTEXITCODE -ne 0) { Write-Error "构建失败"; exit 1 }
$exe = Join-Path $root "dist\VideoSubtitleExtractor\VideoSubtitleExtractor.exe"
if (-not (Test-Path $exe)) { Write-Error "dist\VideoSubtitleExtractor\VideoSubtitleExtractor.exe 未生成"; exit 1 }

# ── 3. 7z 最大压缩 ──
$sz = "C:\Program Files\7-Zip\7z.exe"
if (-not (Test-Path $sz)) {
    $sz = (Get-Command 7z -ErrorAction SilentlyContinue).Source
}
if (-not $sz -or -not (Test-Path $sz)) {
    Write-Error "未找到 7-Zip（请安装 7-Zip 或加入 PATH）"; exit 1
}
$archive = Join-Path $root "VideoSubtitleExtractor.$ver.7z"
if (Test-Path $archive) { Remove-Item $archive }
Write-Host "[release] 7z 最大压缩 -> $archive" -ForegroundColor Cyan
Push-Location (Join-Path $root "dist\VideoSubtitleExtractor")
try {
    & $sz a -t7z -mx=9 -m0=LZMA2 -mmt=on $archive "*"
    if ($LASTEXITCODE -ne 0) { throw "7z 打包失败 (exit $LASTEXITCODE)" }
} finally { Pop-Location }

# ── 4. Release notes ──
$notes = Get-Content (Join-Path $root "release_notes.md") -Raw
$esc = $ver -replace "\.", "\."
$m = [regex]::Match($notes, "(?ms)^## v$esc(.*?)(?=^## v\d|\z)")
if (-not $m.Success) {
    Write-Error "release_notes.md 中未找到 v$ver 节"; exit 1
}
$body = ("## v$ver" + $m.Groups[1].Value).TrimEnd()
$sha = (git rev-parse --short HEAD).Trim()
$body += "`n`n---`n构建源: $sha（本地 7-Zip 最大压缩）"
$notesFile = Join-Path $root "notes.md"
[System.IO.File]::WriteAllText($notesFile, $body, (New-Object System.Text.UTF8Encoding($false)))

# ── 5. 创建 GitHub Release ──
Write-Host "[release] gh release create v$ver ..." -ForegroundColor Cyan
gh release create "v$ver" $archive --title "v$ver" --notes-file $notesFile
if ($LASTEXITCODE -ne 0) { Write-Error "创建 GitHub Release 失败"; exit 1 }
Remove-Item $notesFile -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "✔ Release v$ver 已发布" -ForegroundColor Green
