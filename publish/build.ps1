# ============================================================
#  阶段 A：生成发布包（不推送）
# ============================================================
#  只做一件事：调 `tools/make_release.py` 把当前源码打成
#  `发布版本\<版本号>\`。**不联网、不碰 git、不推送。**
#
#  用法：
#    .\publish\build.ps1                              # 用 config.VERSION 打包
#    .\publish\build.ps1 -Version 0.3.3                # 校验版本号一致后打包
#    .\publish\build.ps1 -Version 0.3.3 -Zip           # 打完再压一个 zip（发布附件用）
#    .\publish\build.ps1 -DryRun                       # 只打印会做什么
#    .\publish\build.ps1 -Force                        # 目标目录已存在时先挪走再重建
#
#  ★★★ 版本号**只由你定**（`config.py` 的 `VERSION` 是唯一来源）。
#     这个脚本**不会改** VERSION，也不会"顺手" bump。
#     `-Version` 只用来**核对**：和你改好的 VERSION 不一致就报错停下。
#
#  ⚠ 为什么重建前必须"先挪走"而不是让脚本删：
#     `make_release.py --force` 的清空动作会被批量删除守卫**静默拦下**（退出码仍是 0），
#     于是你以为重建了、其实旧包还在。所以这里走"移到 _旧版本\ 再建"这条路。
#
#  English:
#  Stage A: build the release folder only. No network, no git, no push.
#  ★★★ The version number is **yours to decide** (`config.VERSION` is the only source).
#  This script never edits VERSION and never bumps it; `-Version` only **cross-checks**.
#  ⚠ Rebuild moves the old folder aside first, because `make_release.py --force`'s wipe is
#  silently blocked by the bulk-delete guard (exit code still 0).
# ============================================================
param(
    [string]$Version = "",          # 留空 = 直接读 config.VERSION
    [string]$ReleaseRoot = "",      # 发布根目录，默认 <工程同级>\发布版本
    [switch]$Zip,                   # 额外压一个 zip（放到发布目录旁边，供 Release 附件用）
    [switch]$Force,                 # 目标已存在时先挪进 _旧版本\
    [switch]$KeepDevTools,          # 发布包里保留 tools/ developers/（默认排除）
    [switch]$KeepDevDocs,           # 发布包里保留开发文档（默认排除）
    [switch]$DryRun                 # 只打印计划
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot          # 工程根目录（本脚本在 publish\ 下）
$Py   = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Py)) { $Py = "python" }

function Write-Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "    [OK] $m"   -ForegroundColor Green }
function Write-Warn2($m){ Write-Host "    [WARN] $m" -ForegroundColor Yellow }
function Write-Err2($m) { Write-Host "    [FAIL] $m" -ForegroundColor Red }

# ── 1. 读 config.VERSION（唯一来源）────────────────────────────
function Get-CfgVersion {
    $cfg = Join-Path $Root "config.py"
    if (-not (Test-Path -LiteralPath $cfg)) { return "" }
    foreach ($ln in [System.IO.File]::ReadAllLines($cfg, [System.Text.Encoding]::UTF8)) {
        if ($ln -match '^\s*VERSION\s*=\s*["'']([^"'']+)["'']') { return $Matches[1] }
    }
    return ""
}

Write-Step "阶段 A：生成发布包"
$cfgVer = Get-CfgVersion
if (-not $cfgVer) { Write-Err2 "读不到 config.py 里的 VERSION；拒绝打包"; exit 2 }
Write-Ok "config.VERSION = $cfgVer"

if ($Version -ne "" -and $Version -ne $cfgVer) {
    Write-Err2 "版本号不一致：-Version 给的是 '$Version'，config.VERSION 是 '$cfgVer'"
    Write-Host "        版本号只由你定 —— 先把 config.py 的 VERSION 改成你要发的号，再来打包。" -ForegroundColor Yellow
    Write-Host "        （脚本不会替你改 VERSION；这条闸就是为了防止'包名和代码里的号对不上'。）" -ForegroundColor Gray
    exit 2
}
$ver = $cfgVer

if ($ReleaseRoot -eq "") {
    $ReleaseRoot = Join-Path (Split-Path -Parent $Root) "发布版本"
}
$Target   = Join-Path $ReleaseRoot $ver
$OldDir   = Join-Path $ReleaseRoot "_旧版本（可在资源管理器里删除）"

Write-Ok "发布根目录: $ReleaseRoot"
Write-Ok "目标目录  : $Target"

if ($DryRun) {
    Write-Host "`n[DryRun] 会执行：" -ForegroundColor Yellow
    Write-Host "  1) 若 $Target 已存在 → 移到 $OldDir\$ver-before-<时间戳>" -ForegroundColor Gray
    # ⚠ 原来是「一条 Write-Host」和「一个 if」挤在同一行、中间没有分号：
    #   `if` 被当成 -ForegroundColor 的后续参数（`$Zip` 未给时渲染成字面量 "if False"），
    #   `-Zip` 时第 3 步**永远不显示**，而 `-DryRun -Zip` 的用户会以为"不会压包"。
    # [EN] These used to share one line with no semicolon: `if` became an argument of the
    # [EN] previous Write-Host (rendering as the literal "if False" when -Zip was absent),
    # [EN] and step 3 never printed even with -Zip.
    $mrLine = "  2) python tools\make_release.py --yes"
    if ($KeepDevTools) { $mrLine += " --keep-dev-tools" }
    if ($KeepDevDocs)  { $mrLine += " --keep-dev-docs" }
    Write-Host $mrLine -ForegroundColor Gray
    if ($Zip) { Write-Host "  3) 压缩成 $ReleaseRoot\$ver.zip" -ForegroundColor Gray }
    Write-Host "`n（DryRun：什么都没做）" -ForegroundColor Green
    exit 0
}

# ── 2. 目标已存在 → 先挪走（绝不让脚本去删）──────────────────
if (Test-Path -LiteralPath $Target) {
    if (-not $Force) {
        Write-Err2 "$Target 已经存在。"
        Write-Host "        要重建请加 -Force（会把旧包移到 _旧版本\，不删）。" -ForegroundColor Yellow
        Write-Host "        若你只是想推送这个已打好的包 → 直接跑阶段 B：.\publish\publish.ps1" -ForegroundColor Gray
        exit 2
    }
    if (-not (Test-Path -LiteralPath $OldDir)) {
        New-Item -ItemType Directory -Force -Path $OldDir | Out-Null
    }
    $stamp = Get-Date -Format "yyyyMMdd-HHmm"
    $dest  = Join-Path $OldDir "$ver-before-$stamp"
    Write-Step "旧包先挪走（不删）：$dest"
    Move-Item -LiteralPath $Target -Destination $dest
    Write-Ok "已挪走"
}

# ── 3. 调 make_release.py ─────────────────────────────────────
Write-Step "打包（tools\make_release.py）"
# ⚠ 变量名避开 `$args` / `$argv` 这类容易和 PowerShell 内置变量混淆的名字。
# [EN] Avoid `$args` / `$argv`, which read like PowerShell built-ins.
$mrArgs = @((Join-Path $Root "tools\make_release.py"), "--yes",
            "--release-root", $ReleaseRoot)
if ($KeepDevTools) { $mrArgs += "--keep-dev-tools" }
if ($KeepDevDocs)  { $mrArgs += "--keep-dev-docs" }

Push-Location $Root
try {
    & $Py @mrArgs
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($code -ne 0) { Write-Err2 "make_release.py 失败（退出码 $code）"; exit $code }
if (-not (Test-Path -LiteralPath $Target)) { Write-Err2 "打包说成功了，但 $Target 不存在"; exit 2 }

$nFiles = (Get-ChildItem -LiteralPath $Target -Recurse -File -Force | Measure-Object).Count
$sizeMB = [math]::Round(((Get-ChildItem -LiteralPath $Target -Recurse -File -Force |
            Measure-Object -Property Length -Sum).Sum) / 1MB, 1)
Write-Ok "产物：$nFiles 个文件 / $sizeMB MB"

# ── 4. 可选：压 zip ──────────────────────────────────────────
if ($Zip) {
    Write-Step "压缩成 zip（Release 附件用）"
    $zipPath = Join-Path $ReleaseRoot "$ver.zip"
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $Target, $zipPath, [System.IO.Compression.CompressionLevel]::Optimal, $true)
    $zMB = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 1)
    Write-Ok "zip：$zipPath（$zMB MB）"
    if ($zMB -gt 100) {
        Write-Warn2 "超过 100 MB —— GitHub Release 能收（上限 2 GB），Gitee Release 通常收不了，"
        Write-Warn2 "          阶段 B 会自动分卷（.part00/.part01…）或建议改用网盘。"
    }
}

# ── 5. 收尾提示 ──────────────────────────────────────────────
Write-Host "`n══════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  阶段 A 完成：$Target" -ForegroundColor Cyan
Write-Host "══════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  下一步（推送，与打包分开）：" -ForegroundColor White
Write-Host "    .\publish\publish.ps1 -Gitee -Token `"<你的PAT>`" -Version `"v$ver`" -ReleaseNotes `"本次更新说明`"" -ForegroundColor Gray
Write-Host ""
exit 0
