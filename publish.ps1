# ============================================================
#  根目录入口（薄壳）—— 真身在 publish\publish.ps1
# ------------------------------------------------------------
#  为什么要这个文件：
#    习惯是 "cd 到工程根目录，.\publish.ps1 -Gitee -Token …"，
#    而实现放在 publish\ 下（和 build.ps1 / readme_variant.py 在一起）。
#    这里只做**转发**：参数原样传过去，退出码原样带回来。
#
#  ★ 实现只有一份。这个文件里不许出现任何业务逻辑 ——
#    一旦在这里写一句判断，它和 publish\publish.ps1 就会开始漂，
#    而两边看起来都对（项目里"同一件事两处实现"已经栽过好几次）。
#  [EN] Root-level shim: the real script is publish\publish.ps1. It only forwards
#  [EN] arguments and the exit code. **No logic here** -- a second implementation would drift.
# ============================================================
$target = Join-Path $PSScriptRoot 'publish\publish.ps1'
if (-not (Test-Path -LiteralPath $target)) {
    Write-Host "找不到 $target" -ForegroundColor Red
    exit 2
}
& $target @args
exit $LASTEXITCODE
