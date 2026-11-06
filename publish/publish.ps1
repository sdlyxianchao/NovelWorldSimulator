# ============================================================
#  阶段 B：把仓库推送到 GitHub / Gitee，并打 tag / 建 Release
# ============================================================
#  前置：先跑阶段 A 生成发布包（只有要挂 Release 附件时才必须）
#    .\publish\build.ps1 -Zip
#
#  典型用法：
#    .\publish\publish.ps1 -Token "<你的 GitHub PAT>"                  # 只发 GitHub（英文 README 门面）
#    .\publish\publish.ps1 -Gitee -Token "<你的 GitHub PAT>"           # GitHub + Gitee（Gitee 用中文门面）
#    .\publish\publish.ps1 -GiteeOnly                                  # 只发 Gitee（会弹 Gitee 登录框）
#    .\publish\publish.ps1 -DryRun                                     # 只打印计划，不碰 git、不联网
#    .\publish\publish.ps1 -NoPush                                     # 生成两套工作区并本地提交，不推远端
#    .\publish\publish.ps1 -Gitee -NoProxy                             # 代理没起时直连
#    .\publish\publish.ps1 -Gitee -ResetGiteeCred                      # 令牌输错了 → 丢掉重问
#    .\publish\publish.ps1 -Gitee -Version "v0.3.4" -ReleaseNotes "…"  # 打 tag 并建 Release
#    .\publish\publish.ps1 -Gitee -UploadAsset                         # 顺带把发布包挂到 Release 附件
#
#  ────────────────────────────────────────────────────────────
#  ★★★ 两个远端的**门面不一样**（这是本脚本 2026-11-06 的主要改动）
#  ────────────────────────────────────────────────────────────
#  源码里：README.md = 中文，README_EN.md = 英文。
#  仓库要的：
#    · GitHub → README.md **英文**，中文挪到 README.zh-CN.md
#    · Gitee  → README.md **中文**，英文挪到 README.en.md
#  两份 README 顶上的语言条互相指着对方，换位时必须一起改 ——
#  只改文件名的话，点「English」会停在原地。这段逻辑唯一实现在
#  `publish/readme_variant.py`（顺带做"相对链接都在盘上"的自检）。
#  所以两个远端**不能共用一个 commit**：各自一个工作区、各自一份历史。
#
#  ★★★ 发布包和仓库是两件事
#  ────────────────────────────────────────────────────────────
#  仓库只放源码 + 文档 + 必需资源（字体 / 图片 / 三个启动器 exe），约 200 MB。
#  发布包（含离线运行时）走 Release 附件（`-UploadAsset`），Gitee 收不下就自动分卷。
#  两者都不碰你的源码目录：镜像到 `<工程同级>\_publish_repo_github\` 与
#  `_publish_repo_gitee\`，随时可以整个删掉重来。
#
#  ⚠ 四道安全闸
#    ① 排除清单硬挡 `.env` / `llm_models.json` / `usage.db` / 日志 / 用户作品；
#    ② **拿 `.env` 与 `llm_models.json` 里的真实密钥值去全文搜**（不是只看键名）——
#       密钥被粘进文档、示例、调试脚本时，只有这一条拦得住；
#    ③ 形态体检（sk- / ghp_ / glpat- …），带占位符判据，不会把 `sk-xxxx` 误判成真 key；
#    ④ **token 不写进 `.git/config`**：push 时直接给带凭据的 URL，工作区里不落凭据，
#       中途 Ctrl+C 也不会留下。
#
#  English:
#  Stage B: push the repo to GitHub / Gitee, tag it, create a Release.
#  ★★★ The two remotes need **different front pages**: GitHub shows the English README as
#  `README.md`, Gitee shows the Chinese one. The language links at the top of each file point at
#  the other, so renaming alone would make "English" land on itself. Two workspaces, two histories.
#  ⚠ Four safety gates: hard-excluded secrets, a full-text search for the **real** key values,
#  shape checks with a placeholder test, and no token ever written into `.git/config`.
# ============================================================
param(
    [string]$CommitMessage = "update: sync latest source",
    [string]$Token = "",                                  # GitHub PAT
    [string]$RepoUrl = "https://github.com/sdlyxianchao/NovelWorldSimulator.git",
    [string]$GiteeRepoUrl = "https://gitee.com/sdxianchao/NovelWorldSimulator.git",
    [switch]$Gitee,                                       # 同时推 Gitee（两个远端都发）
    [switch]$GiteeOnly,                                   # 只推 Gitee
    [string]$GiteeToken = "",                             # Gitee 私人令牌；留空则用已保存凭据 / 弹框
    [string]$GiteeUser = "",                              # Gitee 用户名；留空则用已保存的
    [switch]$ResetGiteeCred,                              # 丢掉已保存的 Gitee 凭据，重新询问
    [string]$Version = "",                                # 如 v0.3.4；留空则不打 tag
    [string]$ReleaseNotes = "",
    [string]$Branch = "main",
    [string]$ReleaseDir = "",
    [string]$RepoDir = "",                                # GitHub 工作区；留空 = <工程同级>\_publish_repo_github
    [string]$GiteeRepoDir = "",                           # Gitee 工作区；留空 = <工程同级>\_publish_repo_gitee
    [switch]$UploadAsset,
    [string]$AssetPath = "",
    [switch]$Lite,
    [switch]$WithDev,
    [switch]$NoPush,
    [string]$Proxy = "",                                  # 要走代理时显式给，如 http://127.0.0.1:7890
    [string]$GithubIp = "",                               # github.com 走指定 IP（绕开被墙/半死的 IP）
    [switch]$NoProxy,                                     # 兼容旧命令（默认已经就是直连）
    [switch]$NoCreate,                                    # 不存在时**不**自动建仓，只报告
    [switch]$Private,                                     # 自动建仓时建成私有仓库（默认公开）
    [string]$Description = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot               # 工程根目录
$Sibling = Split-Path -Parent $Root                     # 工程同级（发布版本\ 在这层）
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Py)) { $Py = "python" }

function Write-Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "    [OK] $m"   -ForegroundColor Green }
function Write-Warn2($m){ Write-Host "    [WARN] $m" -ForegroundColor Yellow }
function Write-Err2($m) { Write-Host "    [FAIL] $m" -ForegroundColor Red }
function Write-Gray($m) { Write-Host "    $m"        -ForegroundColor Gray }

# 想发哪几边（后面某一边失败时把 $doXxx 置 false，但 $wantXxx 一直记着"本来要发"）
$wantGithub = $true
$wantGitee = [bool]$Gitee
if ($GiteeOnly) { $wantGithub = $false; $wantGitee = $true }
$doGithub = $wantGithub
$doGitee = $wantGitee
if (-not $doGithub -and -not $doGitee) { Write-Err2 "没有可发布的远端"; exit 2 }

# ============================================================
#  代理控制（-NoProxy）
# ------------------------------------------------------------
#  本机可能有三层代理配置，任一层失效都会让 push 报
#  "Failed to connect to 127.0.0.1 port xxxxx"：
#    ① git config http.<url>.proxy   ② git config http.proxy
#    ③ 环境变量 HTTP_PROXY / HTTPS_PROXY / ALL_PROXY
# ============================================================
# ============================================================
#  git 代理：**默认直连，并且显式清空**
# ============================================================
# ★★★ 2026-11-06 实测踩坑（用户报"始终发布不成功"）：
#   `git config --global` 里留着 `http.https://github.com.proxy = http://127.0.0.1:33210`，
#   而那个端口早就没了（代理每次重启换端口）。**git 的配置优先级高于环境变量**，
#   所以无论脚本怎么"不传代理"，push 都会去撞那个死端口；
#   而当时脚本把 git 的 stderr 用 Out-Null 丢了，只剩一句猜出来的"远端历史不一致"。
#   ⇒ 结论：**不给值 ≠ 用默认**，不给值 = 沿用那条坏配置。这里必须显式给。
#   同理，环境变量里的 HTTP_PROXY 是工具进程注入的，不该被发布脚本继承。
# [EN] Git's own config beats environment variables. A stale `http.https://github.com.proxy`
# [EN] pointing at a dead port makes every push fail while the script reports a made-up reason.
# [EN] "Not passing a proxy" is NOT "no proxy" -- always pass an explicit value.
# 变量放的是**所有"全局" -c 参数**（代理 / TLS 后端 / IP 钉扎），不只代理 ——
# 名字用 $GitArgs，别再叫 Proxy，否则下一个人会以为 TLS 那段跟代理无关。
$GitArgs = @()
if ($Proxy -ne "") {
    $GitArgs = @('-c', "http.proxy=$Proxy", '-c', "https.proxy=$Proxy",
                 '-c', "http.https://github.com.proxy=$Proxy",
                 '-c', "http.https://gitee.com.proxy=$Proxy")
    Write-Ok "git 代理：$Proxy（-Proxy 指定）"
} else {
    $GitArgs = @('-c', 'http.proxy=', '-c', 'https.proxy=',
                 '-c', 'http.https://github.com.proxy=',
                 '-c', 'http.https://gitee.com.proxy=')
    Write-Ok "git 代理：直连（已覆盖 git 全局配置）"
}
# 直连时连环境变量一起清 —— 那些是编辑器 / 工具进程注入的，不是用户的系统代理。
# 只在 -Proxy 显式给定时保留（那时由 -c 参数控制，环境变量无所谓）。
if ($Proxy -eq "") {
    foreach ($pv in @('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy')) {
        Set-Item -Path "Env:$pv" -Value "" -ErrorAction SilentlyContinue
    }
    [System.Net.WebRequest]::DefaultWebProxy = $null
    if ($NoProxy) { Write-Gray "-NoProxy：同默认行为（直连），API 也不走代理" }
}

#: 跑一条**只读**的 git 命令，把 stdout+stderr 收成一段文本 + 退出码。
#: ⚠ 必须临时把 `$ErrorActionPreference` 放回 Continue：PowerShell 5.1 里 `2>&1` 会把
#:   原生命令的 stderr 变成 ErrorRecord，而脚本顶部是 `Stop` ⇒ 探测命令会**直接终止整个脚本**
#:   （实测：DryRun 都跑不完，rc=1，屏幕上只有一句 `NativeCommandError`）。
#:   这个坑以前只在 Push-Tree 内部绕过，没人发现它是全局的。
# [EN] Run a read-only git command and capture stdout+stderr plus the exit code.
# [EN] PS 5.1 turns native stderr into ErrorRecord under `2>&1`; with `$ErrorActionPreference='Stop'`
# [EN] that **terminates the whole script** -- which is exactly what a probe must never do.
function Invoke-GitText([string[]]$gargs) {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $o = @(git @gargs 2>&1)
        $rc = $LASTEXITCODE
        return @{ text = (($o | ForEach-Object { "$_" }) -join "`n"); rc = $rc }
    } finally {
        $ErrorActionPreference = $prevEap
    }
}

# ============================================================
#  TLS 后端：**系统级**配置可能写着这个 git 根本没编进去的后端
# ------------------------------------------------------------
#  ★★★ 2026-11-06 实测（用户报"两个远端都推不上去、永远被拒"）：
#    git 的原话是 `fatal: Unsupported SSL backend 'openssl'. Supported SSL backends: schannel`
#    —— 这台机器的 `C:\Program Files\Git\etc\gitconfig`（**系统级**）写着
#    `http.sslBackend = openssl`，而 `C:\Program Files\Git\cmd\git.exe` 这个构建
#    只编了 schannel ⇒ **它的每一个 https 操作都废**：clone / pull / push 一个都跑不了。
#    跟令牌、网络、代理**全都没有关系**，重输令牌和换 IP 都是白费。
#    更坏的是这条错误被归到了"连不上远端"，于是人被指去换 IP —— 试一晚也不会好。
#  ⇒ 做法：让 git **自己**报出它支持哪些后端：故意给一个不存在的名字，
#    它在**联网之前**就失败（实测 54ms、零流量）并列出 `Supported SSL backends: schannel`。
#    配置里的那个不在列表里，就换成列表里的第一个（命令行的 -c 优先级最高，不用改系统文件）。
# [EN] A **system-level** `http.sslBackend = openssl` on a schannel-only build breaks *every*
# [EN] https operation of that git -- nothing to do with tokens, network or proxies. Ask git
# [EN] which backends it actually has (a bogus name fails before any network I/O) and override
# [EN] the mismatched value with `-c`, which beats both system and global config.
function Get-GitSslBackends {
    $r = Invoke-GitText @('-c', 'http.sslBackend=__probe__', 'ls-remote', 'https://example.invalid/x')
    if ($r.text -match '(?s)Supported SSL backends:\s*(.+?)\s*$') {
        return @($Matches[1] -split '\s+' | Where-Object { $_ -ne '' })
    }
    return @()
}

$effSsl = ((Invoke-GitText @('config', '--get', 'http.sslBackend')).text).Trim()
if ($effSsl -ne '') {
    $supported = @(Get-GitSslBackends)
    $using = $effSsl
    if ($supported.Count -gt 0 -and $supported -notcontains $effSsl) { $using = $supported[0] }
    # 这一行是给判据看的（纯 ASCII，不怕控制台代码页）：
    # 判据自己再探一次 backend 列表，比对 using 是否真在 supported 里。
    Write-Gray "[git-tls] configured=$effSsl supported=$($supported -join ',') using=$using"
    if ($using -ne $effSsl) {
        $GitArgs += @('-c', "http.sslBackend=$using")
        Write-Warn2 "本机 git 配置要 $effSsl，但这个 git 只编了 $($supported -join ' / ')"
        Write-Gray "  · 本次按 $using 跑；永久修：git config --global http.sslBackend $using"
    }
}

# ★★★ 令牌形状告警（只警告、不拦截）：令牌里带 `@` / 空格 / 冒号的，
#   几乎一定是**登录密码**（邮箱样式密码尤其常见）。它拼进 URL 会让 curl 报
#   `URL rejected: Bad hostname`——那句话长得像"网络不通"，其实是本地拼 URL 就失败了。
#   现在拼 URL 已经会转义（`Get-AuthedUrl`），但认证仍会被拒；在**入口**就提醒，
#   别让人拿着密码空跑一轮。GitHub PAT 形如 ghp_xxx，Gitee 私人令牌是 32 位十六进制。
# [EN] Warn (not block) when a token contains URL-hostile characters: it is almost certainly a
# [EN] login password, not a PAT. It used to turn into "Bad hostname" (looks like a network issue).
function Warn-TokenShape([string]$label, [string]$tk) {
    if ($tk -eq '' -or $tk -match '^[A-Za-z0-9_\-]{16,}$') { return }
    Write-Warn2 "$label 令牌里含特殊字符或长度不像令牌 —— 这多半是登录密码，认证大概率会被拒"
    Write-Gray "  · GitHub PAT：https://github.com/settings/tokens（ghp_ 开头）"
    Write-Gray "  · Gitee 私人令牌：https://gitee.com/profile/personal_access_tokens（32 位十六进制）"
}
Warn-TokenShape 'GitHub' $Token
Warn-TokenShape 'Gitee' $GiteeToken

#: "连不上"这一类错误的字样。**只放真·网络 / 握手失败**。
#: `Unsupported SSL backend` 绝不能算进来 —— 那是本机配置错（上面已纠正），
#: 归到这里就会把人指去"换 IP、重输令牌"，而那两件事一点用都没有。
$NetFailRe = 'Could not connect|Failed to connect|unable to access|Connection refused|Connection was reset|Recv failure|timed out|SSL_|schannel|Empty reply from server'

#: "凭据被拒"这一类错误的字样。**全脚本只此一份**：push 失败分类、令牌兜底重试
#: 都要判"是不是认证问题"，两处各写一份正则迟早漂移（2026-11-06 就漂过：
#: 一边有 'Invalid username' 一边没有）。
$AuthFailRe = 'Authentication failed|authentication|Permission denied|403|401|Invalid username'

#: ★★★ 2026-11-06 实测（用户：Gitee 成功、GitHub 的 force push 报
#:   `fatal: Authentication failed`，而**普通 push 那一步拿到的是真被拒 [rejected]**）：
#:   一个"能读不能写"的令牌（经典 PAT 没勾 repo / 细粒度只给 Contents:Read）恰好长这样——
#:   公开仓库的引用广告它读得到（第 1 次 push 能走到 [rejected]），force POST 写入时才被拒。
#:   而 Windows 凭据管理器（git credential manager）里存过的 GitHub 凭据是**能写的**
#:   （实测推小分支 rc=0）。⇒ 令牌被拒时，自动换凭据管理器里的凭据再推一次；
#:   tag 推送跟同一个决定（`$script:GhAuthByHelper`），别让 tag 再撞一次墙。
# [EN] A read-only token passes the ref advertisement (so push #1 gets a genuine
# [EN] [rejected]) but fails the write POST -- looks like "auth worked then broke".
# [EN] Fall back to the credential-manager credential, which can write. Tag push
# [EN] follows the same decision via $script:GhAuthByHelper.
$script:GhAuthByHelper = $false

#: 凭据管理器里有没有存过 GitHub 凭据（cmdkey 只列名字、不读内容）。
#: 兜底重推**必须有这道闸**：没有存过凭据时走 git credential helper，
#: GCM 会弹 GUI / 浏览器登录 —— 无人值守跑（判据 / 定时任务）会一直挂着。
function Test-GcmGithubCred {
    # 临时放回 Continue：cmdkey 是原生命令，PS 5.1 里 stderr 会变 ErrorRecord
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = @(cmdkey /list 2>&1)
        $t = ($out | ForEach-Object { "$_" }) -join "`n"
        return ($t -match 'git:https://github\.com')
    } finally {
        $ErrorActionPreference = $prevEap
    }
}

# ★★★ 2026-11-06 实测：这台机器 `hosts` 里写着 `20.27.177.113 github.com`，
#   上午还能用、晚上就 `Recv failure: Connection was reset`；换 `140.82.116.3` 10 秒就通。
#   ⇒ **不存在"实测可用"的常量 IP**，只有"现试"。下面这份是候选池，不是真理：
#     GitHub 推失败且没指定 -GithubIp 时，脚本会自己按池子试一遍，用能连的那个重推一次。
#   `hosts` 需要管理员才能改，所以走 git 2.47+ 的 `http.curloptResolve`（优先于 hosts / DNS）。
# [EN] A `hosts` entry can be half-dead or dead by tonight. There is no "known good" IP --
# [EN] only "try now". This is a candidate pool; on a failed push the script probes it and
# [EN] retries once with whatever answers, pinned via `http.curloptResolve`.
$GithubIpCandidates = @('140.82.116.3', '20.27.177.113', '20.200.245.247', '4.237.22.38', '140.82.112.3')

function Get-GithubPinArgs([string]$ip) {
    return @('-c', "http.curloptResolve=github.com:443:$ip",
             '-c', "http.curloptResolve=api.github.com:443:$ip")
}

#: 逐个候选 IP 试一次 ls-remote，返回第一个"不是连不上"的。
#: 判"通"用**否定**（不是网络类错误就算通）：仓库还没建 / 需要认证时 git 也会非 0 退出，
#: 但那说明 TLS 已经握手成功、域名已经通了，正是我们要测的东西。
function Find-GithubIp {
    foreach ($ip in $GithubIpCandidates) {
        $pin = @(Get-GithubPinArgs $ip)
        $r = Invoke-GitText ($GitArgs + $pin + @('-c', 'credential.helper=',
                                                'ls-remote', '--heads', $RepoUrl))
        if ($r.text -notmatch $NetFailRe) { return $ip }
        Write-Gray "  · $ip 不通"
    }
    return ''
}

if ($GithubIp -ne "") {
    $GitArgs += @(Get-GithubPinArgs $GithubIp)
    Write-Ok "GitHub 固定走 $GithubIp（curloptResolve，优先于 hosts / DNS）"
}

# ============================================================
#  Gitee 凭据（DPAPI 加密，本机用户级）
# ============================================================
$GiteeEncFile  = Join-Path $Root ".gitee-cred.enc"
$GiteeUserFile = Join-Path $Root ".gitee-user.txt"

function Get-GiteeCred {
    if (-not (Test-Path -LiteralPath $GiteeEncFile) -or
        -not (Test-Path -LiteralPath $GiteeUserFile)) { return $null }
    try {
        $ss = Get-Content -LiteralPath $GiteeEncFile -Raw | ConvertTo-SecureString
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($ss)
        $tk = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        return @{ username = (Get-Content -LiteralPath $GiteeUserFile -Raw).Trim(); token = $tk }
    } catch { return $null }
}

#: 清掉本机保存的 Gitee 凭据（两个文件：加密令牌 + 用户名）。
#: 存在的意义：**存了凭据就不再弹框**，所以令牌输错一次会被一直沿用，
#: 而界面上只会说「建仓失败」—— 用户除了手删文件没有别的路。
#: [EN] Drop the saved Gitee credentials (encrypted token + username). Once saved, the script
#: never prompts again, so a mistyped token gets reused forever while the UI only says
#: "failed to create repo" -- without this the user has no way out but deleting files by hand.
function Clear-GiteeCred {
    $n = 0
    foreach ($f in @($GiteeEncFile, $GiteeUserFile)) {
        if (Test-Path -LiteralPath $f) {
            Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
            if (-not (Test-Path -LiteralPath $f)) { $n++ }
        }
    }
    if ($n -gt 0) {
        Write-Warn2 "已清除本机保存的 Gitee 凭据（$n 个文件）"
    } else {
        Write-Gray "本机没有保存的 Gitee 凭据，无需清除"
    }
}

function Save-GiteeCred($user, $token) {
    $enc = (ConvertTo-SecureString $token -AsPlainText -Force) | ConvertFrom-SecureString
    Set-Content -LiteralPath $GiteeEncFile  -Value $enc  -NoNewline -Encoding ASCII
    Set-Content -LiteralPath $GiteeUserFile -Value $user -NoNewline -Encoding UTF8
    Write-Ok "Gitee 凭据已加密保存（本机专用；不进仓库、不进工作区）"
}

function Set-GiteeCred {
    try { Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction Stop } catch {
        Write-Err2 "无法加载输入框组件（Microsoft.VisualBasic）"; return $null
    }
    $u = [Microsoft.VisualBasic.Interaction]::InputBox(
        "请输入 Gitee 用户名（登录名，如 sdxianchao）：", "Gitee 登录 - 步骤 1/2", "")
    if ([string]::IsNullOrWhiteSpace($u)) { Write-Err2 "未输入用户名"; return $null }
    $k = [Microsoft.VisualBasic.Interaction]::InputBox(
        "请输入 Gitee 私人令牌（Personal Access Token）：`n`n生成地址：`nhttps://gitee.com/profile/personal_access_tokens`n建议勾选 projects 读写权限",
        "Gitee 登录 - 步骤 2/2", "")
    if ([string]::IsNullOrWhiteSpace($k)) { Write-Err2 "未输入令牌"; return $null }
    Save-GiteeCred $u.Trim() $k.Trim()
    return @{ username = $u.Trim(); token = $k.Trim() }
}

# ============================================================
#  版本 / 目录
# ============================================================
function Get-CfgVersion {
    $cfg = Join-Path $Root "config.py"
    if (-not (Test-Path -LiteralPath $cfg)) { return "" }
    foreach ($ln in [System.IO.File]::ReadAllLines($cfg, [System.Text.Encoding]::UTF8)) {
        if ($ln -match '^\s*VERSION\s*=\s*["'']([^"'']+)["'']') { return $Matches[1] }
    }
    return ""
}

$cfgVer = Get-CfgVersion
$tag = $Version
$bare = ""
if ($tag -ne "") {
    $bare = $tag -replace '^v', ''
    if ($cfgVer -ne "" -and $bare -ne $cfgVer) {
        Write-Warn2 "tag '$tag' 与 config.VERSION '$cfgVer' 不一致。"
        Write-Warn2 "  版本号只由你定，照你给的走；但请确认这是你要发的号。"
    }
}

if ($doGithub) {
    if ($RepoDir -eq "") { $RepoDir = Join-Path $Sibling "_publish_repo_github" }
}
if ($doGitee) {
    if ($GiteeRepoDir -eq "") { $GiteeRepoDir = Join-Path $Sibling "_publish_repo_gitee" }
}

# 防呆：工作区不许落在源码目录里（robocopy 镜像会互相打架）
$rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
foreach ($d in @($RepoDir, $GiteeRepoDir)) {
    if ([string]::IsNullOrWhiteSpace($d)) { continue }
    $df = [System.IO.Path]::GetFullPath($d).TrimEnd('\')
    if ($df -eq $rootFull -or $df.StartsWith($rootFull + '\', [StringComparison]::OrdinalIgnoreCase)) {
        Write-Err2 "工作区不能放在源码目录里（镜像时会互相覆盖）：$d"
        exit 2
    }
}

# ============================================================
#  排除清单（两个工作区共用这一份 —— 只写一处）
# ============================================================
$XD = @('.git', '.venv', 'venv', 'env', '__pycache__', 'node_modules',
        '.vscode', '.idea',
        'logs', 'exports', 'Projects', '项目',
        'packages',                                     # 202 MB 离线运行时 —— 走发布包
        'novelservices',                                # 服务本体 GB 级 —— 走发布包（薄壳单独补）
        'generated-images', 'logo_drafts', 'dist',
        '发布版本', '_旧版本（可在资源管理器里删除）',
        '.workbuddy',                                   # AI 开发记忆（逐日日志）
        '.ui_state',                                    # 本机窗口尺寸 / 上次停在哪页
        '字体设置验证', '面板跳转验证', '偷写')          # 判据残留的假项目 / 空目录

# ⚠⚠ 带路径分隔符的排除项必须给**完整路径**。
#   2026-11-06 实测：`/XD assets\screenshots` 这种相对写法**被 robocopy 静默忽略** ——
#   于是 286 MB 调试截图（里面 `audit_screens.json` 存着真的 LLM_API_KEY）原样进了工作区，
#   镜像出来 425 MB，而排除清单读起来完全正确。真正拦住它的是后面的密钥体检，
#   也就是说：**排除清单失效这件事，是靠另一道闸擦屁股才被发现的**。
# [EN] ⚠⚠ Path-style excludes must be **absolute**. Measured 2026-11-06: a relative
# [EN] `/XD assets\screenshots` is **silently ignored** by robocopy, so 286 MB of debug
# [EN] screenshots (whose `audit_screens.json` holds a real LLM_API_KEY) went straight into the
# [EN] workspace; the mirror came out 425 MB while the exclude list read perfectly correct.
$XD_PATHS = @('assets\screenshots', 'novel_bench\results', 'launchers\dist')
foreach ($rel in $XD_PATHS) { $XD += (Join-Path $Root $rel) }

if (-not $WithDev) { $XD += 'developers' }
if ($Lite)         { $XD += 'images' }

$XF = @('*.bak*', '*.bak-bilingual', '*.exitbak', '*~',
        '.env',                                          # ★ 真 API Key
        'llm_models.json',                               # ★ 每条模型都带 Key
        'usage.db', 'usage.db-journal', 'llm_cache.db',   # 用量台账 / 本地缓存
        '.nws_messages.jsonl',
        '.install_manifest.json',                        # 含本机绝对路径
        '.bilingual_done.json',
        'nul', '*.log', '*.pyc', '*.old-*',
        '.gitee-cred.enc', '.gitee-user.txt',            # 本脚本自己的凭据
        'Simulating.gif')                                # 33.8 MB 且 README 没引用（用的是 walkthrough.gif）

# ⚠ `*.exe` **不再**一刀切：根目录的 start.exe / setup.exe / uninstall.exe 是
#   README 里"双击这个"的入口（三个共 10.5 MB）。排除它们 = 文档叫人双击一个不存在的文件。
#   `launchers\dist` 已在上面的目录清单里整目录排掉。

$ScanExt = @('.py', '.md', '.txt', '.json', '.yaml', '.yml', '.ps1', '.go', '.js', '.ts', '.ini', '.cfg', '.bat')
$SkipSeg = @('.git', '.venv', 'node_modules', '__pycache__')

# ============================================================
#  真实密钥值（体检用；只在内存里，不落盘、不打印）
# ------------------------------------------------------------
#  为什么不能只靠"键名 + 长值"的正则：
#    密钥经常不是写在 `.env` 里那一行，而是被**粘到别处** —— 某个调试脚本、
#    某篇文档的示例、某次排障留下的 json。只有拿真值去全文搜才拦得住。
# ============================================================
function Get-SecretValues {
    $vals = @()
    $envFile = Join-Path $Root '.env'
    if (Test-Path -LiteralPath $envFile) {
        foreach ($ln in [System.IO.File]::ReadAllLines($envFile, [System.Text.Encoding]::UTF8)) {
            if ($ln -match '^\s*([A-Z0-9_]*(?:API_KEY|_KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)\s*=\s*(.+?)\s*$') {
                $k = $Matches[1]
                $v = $Matches[2].Trim().Trim('"').Trim("'")
                # 太短的一定不是密钥（TOKEN_BUDGET_PER_DAY=200000 之类）
                if ($v.Length -ge 16 -and $v -notmatch '^(?i)(true|false|none|null|auto|default)$') {
                    $vals += @{ key = $k; value = $v }
                }
            }
        }
    }
    $lmFile = Join-Path $Root 'llm_models.json'
    if (Test-Path -LiteralPath $lmFile) {
        try {
            $raw = [System.IO.File]::ReadAllText($lmFile, [System.Text.Encoding]::UTF8)
            foreach ($m in [regex]::Matches($raw, '"(?:api_?key|apiKey|token|secret)"\s*:\s*"([^"]{16,})"', 'IgnoreCase')) {
                $vals += @{ key = 'llm_models.json'; value = $m.Groups[1].Value }
            }
        } catch { }
    }
    return $vals
}

function Test-Placeholder([string]$tok) {
    # `sk-xxxxxxxx…` / `<your-key>` 这类是**文档里的示例**，不是密钥。
    # ⚠ 必须按"串本身的形态"判，不能按文件名白名单 ——
    #   白名单会让真 key 被粘进 README 时直接漏过去。
    $body = $tok -replace '^(?i)(sk|ghp|gho|ghu|ghs|ghr|github_pat|glpat|hf|AIza)[-_]?', ''
    if ($body -match '(?i)your|xxx|placeholder|example|change_?me|abc123|todo') { return $true }
    # 判据夹具里的假 key 常写成 `sk-abcd1234efgh5678` / `sk-test-…` ——
    # 真 key 是随机的，不会出现连续的字母表 / 数字表片段。
    # [EN] Test fixtures write fake keys like `sk-abcd1234efgh5678`; a real key is random and
    # [EN] never contains an alphabetical/numeric run.
    if ($body -match '(?i)(abcd|efgh|ijkl|1234|5678|qwer|asdf|test)') { return $true }
    $chars = @($body.ToCharArray() | Sort-Object -Unique)
    if ($chars.Count -le 2) { return $true }
    if ($chars.Count -lt 6) { return $true }
    return $false
}

function Scan-Secrets([string]$dir, [string]$label) {
    $bad = @()
    $patterns = @(
        'sk-[A-Za-z0-9_\-]{16,}',
        'ghp_[A-Za-z0-9]{20,}',
        'github_pat_[A-Za-z0-9_]{20,}',
        'gh[ousr]_[A-Za-z0-9]{20,}',
        'glpat-[A-Za-z0-9_\-]{16,}',
        'AKIA[0-9A-Z]{16}',
        'AIza[0-9A-Za-z_\-]{30,}',
        'hf_[A-Za-z0-9]{30,}',
        'xox[baprs]-[A-Za-z0-9\-]{10,}'
    )
    $files = @(Get-ChildItem -LiteralPath $dir -Recurse -File -Force -ErrorAction SilentlyContinue |
             Where-Object {
                 $ScanExt -contains $_.Extension.ToLower() -and
                 -not ($_.FullName -split '[\\/]' | Where-Object { $SkipSeg -contains $_ })
             })
    foreach ($f in $files) {
        $rel = $f.FullName.Substring($dir.Length).TrimStart('\')
        try { $txt = [System.IO.File]::ReadAllText($f.FullName, [System.Text.Encoding]::UTF8) }
        catch { continue }

        # ① 真值全文搜（最硬的一道）
        foreach ($s in $RealSecrets) {
            if ($txt.IndexOf($s.value, [StringComparison]::Ordinal) -ge 0) {
                $bad += "$rel  ← 出现了「$($s.key)」的真实值"
            }
        }
        # ② 形态
        foreach ($p in $patterns) {
            foreach ($m in [regex]::Matches($txt, $p)) {
                if (-not (Test-Placeholder $m.Value)) {
                    $head = $m.Value.Substring(0, [Math]::Min(10, $m.Value.Length))
                    $bad += "$rel  ← 疑似密钥 $head…"
                    break
                }
            }
        }
        # ③ 键名 + 长值
        if ($txt -match '(?m)^\s*[A-Z0-9_]*(API_KEY|_KEY|SECRET|TOKEN|PASSWORD)\s*[=:]\s*["'']?[A-Za-z0-9_\-\.]{24,}["'']?\s*$') {
            $hit = $Matches[0].Trim()
            if (-not (Test-Placeholder $hit)) {
                $bad += "$rel  ← 疑似明文密钥：$($hit.Substring(0, [Math]::Min(28, $hit.Length)))…"
            }
        }
    }
    if ($bad.Count -gt 0) {
        Write-Err2 "$label 扫到 $($bad.Count) 处可能是密钥的内容，**已中止**："
        $bad | Select-Object -First 12 | ForEach-Object { Write-Host "      $_" -ForegroundColor Red }
        if ($bad.Count -gt 12) { Write-Host "      …… 还有 $($bad.Count - 12) 处" -ForegroundColor Red }
        Write-Host "`n    处理：把来源加进本脚本的 `$XD / `$XF 排除清单，或改成 .env.example 那种空值占位。" -ForegroundColor Yellow
        Write-Host "    ⚠ 推上去之后删提交也清不掉历史 —— 宁可停下来。" -ForegroundColor Yellow
        return $false
    }
    Write-Ok "$label 体检通过：$($files.Count) 个文本文件，没扫到真密钥"
    return $true
}

$RealSecrets = @(Get-SecretValues)
if ($RealSecrets.Count -gt 0) {
    Write-Gray "已载入 $($RealSecrets.Count) 个真实密钥值，用来全文搜（值本身不会打印）"
} else {
    Write-Warn2 "没从 .env / llm_models.json 读到可用的密钥值 —— 第二道闸会空转"
    Write-Warn2 "  若你确实配过 Key，检查键名是否含 API_KEY / TOKEN / SECRET / PASSWORD"
}

# ============================================================
#  远端仓库：检查 / 创建
# ------------------------------------------------------------
#  ★ `auto_init = false`：让远端是**空仓库**。
#    用 auto_init 建的话远端会先有一个 README 提交，我们的第一次 push 必然被拒，
#    只能 force 覆盖 —— 那等于把自动生成的东西再砸掉，多此一举。
# ============================================================
function Get-Slug([string]$url) {
    $u = $url -replace '\.git$', '' -replace '/+$', ''
    return ($u -replace '^https?://[^/]+/', '')
}

function Get-HttpCode($err) {
    try { return [int]$err.Exception.Response.StatusCode } catch { return 0 }
}

function Get-GitHubHeaders([string]$tk) {
    $h = @{ Accept = 'application/vnd.github.v3+json'; 'User-Agent' = 'NovelWorldSimulator-publish' }
    if ($tk -ne "") { $h['Authorization'] = "token $tk" }
    return $h
}

function Test-GitHubRepo([string]$slug, [string]$tk) {
    try {
        Invoke-RestMethod -Uri "https://api.github.com/repos/$slug" -Headers (Get-GitHubHeaders $tk) `
                          -Method Get -TimeoutSec 25 -ErrorAction Stop | Out-Null
        return $true
    } catch {
        $c = Get-HttpCode $_
        if ($c -eq 404) { return $false }
        throw
    }
}

function New-GitHubRepo([string]$slug, [string]$tk, [string]$desc) {
    $h = Get-GitHubHeaders $tk
    $name = ($slug -split '/')[-1]
    $body = @{
        name        = $name
        private     = [bool]$Private
        description = $desc
        auto_init   = $false
        has_issues  = $true
        has_wiki    = $true
    } | ConvertTo-Json
    Invoke-RestMethod -Uri "https://api.github.com/user/repos" -Headers $h -Method Post `
                      -Body $body -ContentType 'application/json' -TimeoutSec 40 -ErrorAction Stop | Out-Null
    $vis = '公开'
    if ($Private) { $vis = '私有' }
    Write-Ok "GitHub 仓库已创建：$slug（$vis）"
}

function Test-GiteeRepo([string]$slug) {
    try {
        Invoke-RestMethod -Uri "https://gitee.com/api/v5/repos/$slug" -Method Get -TimeoutSec 25 -ErrorAction Stop | Out-Null
        return $true
    } catch {
        $c = Get-HttpCode $_
        if ($c -eq 404) { return $false }
        throw
    }
}

function New-GiteeRepo([string]$slug, [string]$tk, [string]$desc) {
    $name = ($slug -split '/')[-1]
    $body = @{
        access_token = $tk
        name         = $name
        private      = [bool]$Private
        auto_init    = $false
        description  = $desc
    }
    Invoke-RestMethod -Uri "https://gitee.com/api/v5/user/repos" -Method Post `
                      -Body $body -TimeoutSec 40 -ErrorAction Stop | Out-Null
    $vis = '公开'
    if ($Private) { $vis = '私有' }
    Write-Ok "Gitee 仓库已创建：$slug（$vis）"
}

function Set-DefaultBranch([string]$kind, [string]$slug, [string]$tk, [string]$br) {
    # 空仓库建出来的默认分支常是 master，而我们推的是 main ⇒ 仓库首页会 404。
    # 推完再设一次；失败只提醒（分支本身已经推上去了，手动改一下即可）。
    try {
        if ($kind -eq 'github') {
            $h = Get-GitHubHeaders $tk
            $body = @{ default_branch = $br } | ConvertTo-Json
            Invoke-RestMethod -Uri "https://api.github.com/repos/$slug" -Headers $h -Method Patch `
                              -Body $body -ContentType 'application/json' -TimeoutSec 20 -ErrorAction Stop | Out-Null
        } else {
            $body = @{ access_token = $tk; default_branch = $br }
            Invoke-RestMethod -Uri "https://gitee.com/api/v5/repos/$slug" -Method Patch `
                              -Body $body -TimeoutSec 20 -ErrorAction Stop | Out-Null
        }
        Write-Ok "$kind 默认分支已设为 $br"
    } catch {
        Write-Warn2 "$kind 默认分支没设成（可到网页上手动改）：$($_.Exception.Message)"
    }
}

function Sync-Tree([string]$dst, [string]$label) {
    Write-Step "Phase 1: 镜像 → $label"
    Write-Gray "（源码目录本身不动，也不会变成 git 仓库）"
    if (-not (Test-Path -LiteralPath $dst)) {
        New-Item -ItemType Directory -Force -Path $dst | Out-Null
    }
    $rcArgs = @($Root, $dst, '/MIR', '/NFL', '/NDL', '/NJH', '/NJS', '/NC', '/NS', '/R:2', '/W:2')
    $rcArgs += '/XD'; $rcArgs += $XD
    $rcArgs += '/XF'; $rcArgs += $XF
    & robocopy @rcArgs | Out-Null
    $rc = $LASTEXITCODE
    # robocopy：0=无变化 1=有复制 2=有额外项 3=1+2 … 8 及以上才是真失败
    if ($rc -ge 8) { Write-Err2 "robocopy 失败（退出码 $rc）"; return $false }

    # ⚠ `/XF` 只**阻止复制**，不会删除目标里已经存在的同名文件。
    #   所以"改了排除清单再重跑"时，上一版的残留会一直留在工作区里
    #   （2026-11-06 实测：`verify_sdk.py.exitbak` 就是上一版漏进来的，加了 `*.exitbak`
    #   仍然在，因为 robocopy 认为"源里这个文件名存在，只是被过滤了"）。
    #   这里按清单再扫一遍目标 —— 清单是权威，不是建议。
    # [EN] `/XF` only **prevents copying**; it never deletes an existing file with that name in the
    # [EN] destination. So after changing the exclude list, leftovers from the previous run stay
    # [EN] (measured 2026-11-06: `verify_sdk.py.exitbak`). Sweep the destination by the same list.
    $purged = 0
    foreach ($pat in $XF) {
        Get-ChildItem -LiteralPath $dst -Recurse -File -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like $pat } |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue; $purged++ }
    }
    if ($purged -gt 0) { Write-Gray "清掉 $purged 个上一版残留（按当前排除清单）" }

    $nF = (Get-ChildItem -LiteralPath $dst -Recurse -File -Force | Measure-Object).Count
    $mb = [math]::Round(((Get-ChildItem -LiteralPath $dst -Recurse -File -Force |
          Measure-Object -Property Length -Sum).Sum) / 1MB, 1)
    Write-Ok "镜像完成（robocopy $rc）：$nF 个文件 / $mb MB"
    return $true
}

function Add-ServiceShells([string]$dst, [string]$label) {
    # novelservices 整目录被排除了（服务本体 GB 级），但**桥接薄壳**要进仓库：
    # 没有它们，程序 import 那一句就崩。服务缺席是**被支持的常态**，缺壳不是。
    $srcSvc = Join-Path $Root "novelservices"
    if (-not (Test-Path -LiteralPath $srcSvc)) { return }
    $shellDst = Join-Path $dst "novelservices"
    if (-not (Test-Path -LiteralPath $shellDst)) {
        New-Item -ItemType Directory -Force -Path $shellDst | Out-Null
    }
    $shells = @('__init__.py', 'mumu_bridge.py', 'penshot_bridge.py',
                'plotpilot_bridge.py', 'service_ctl.py')
    $got = 0
    foreach ($f in $shells) {
        $src = Join-Path $srcSvc $f
        if (Test-Path -LiteralPath $src) {
            Copy-Item -LiteralPath $src -Destination (Join-Path $shellDst $f) -Force
            $got++
        }
    }
    $notePath = Join-Path $shellDst "README.md"
    $note = @'
# novelservices

这里**只放桥接薄壳**（`*_bridge.py` / `service_ctl.py` / `__init__.py`）。

三座外部创作服务（MuMuAINovel / PenShot / PlotPilot）的**本体不在这个仓库里** ——
它们是独立的项目，体积以 GB 计，随**发布包**提供，或各自从上游获取。

程序对它们的态度是：**缺席是被支持的常态**。
没有它们，推演、导出、剧情总览、地图全部照常工作，只是少那几项"增强"能力。
'@
    Set-Content -LiteralPath $notePath -Value $note -Encoding UTF8
    Write-Ok "$label 补 novelservices 薄壳 $got 个"
}

function Commit-Tree([string]$dir, [string]$label) {
    Write-Step "Phase 4: 本地提交（$label）"
    Write-Gray "git 把进度写 stderr，PowerShell 5.1 在 Stop 模式下会误判成致命错误 ⇒ 本段切 Continue，靠 `$LASTEXITCODE 判成败"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    Push-Location $dir
    try {
        Set-Content -LiteralPath (Join-Path $dir ".gitignore") -Value $GitIgnore -Encoding UTF8
        if (-not (Test-Path -LiteralPath (Join-Path $dir ".git"))) {
            git init -q
            if ($LASTEXITCODE -ne 0) { Write-Err2 "$label git init 失败"; return $false }
        }
        $uname = (git config user.name 2>$null)
        $umail = (git config user.email 2>$null)
        if (-not $uname) { git config user.name "NovelWorldSimulator" | Out-Null }
        if (-not $umail) { git config user.email "noreply@localhost" | Out-Null }
        git config --global --add safe.directory $dir 2>$null | Out-Null

        git add -A
        $status = git status --porcelain
        if ([string]::IsNullOrWhiteSpace($status)) {
            Write-Ok "$label 无变更，跳过提交"
        } else {
            git commit -m $CommitMessage -q
            if ($LASTEXITCODE -ne 0) { Write-Err2 "$label commit 失败"; return $false }
            $short = (git rev-parse --short HEAD 2>$null)
            Write-Ok "$label commit $short：$CommitMessage"
        }
        git branch -M $Branch | Out-Null
        return $true
    } finally {
        Pop-Location
        $ErrorActionPreference = $prevEap
    }
}

#: 把 git 的输出整理成能给用户看的文本：抹掉令牌、压掉空行。
#: 之前这里直接 `2>&1 | Out-Null`，于是"连不上远端"被当成"历史不一致"，
#: 用户看到的永远是猜出来的原因，真正的 fatal 那行一个字都没留下。
# [EN] Turn git's output into something safe to print: strip the token, drop blank lines.
function Hide-Secret([string]$text, [string]$secret) {
    if ([string]::IsNullOrWhiteSpace($text)) { return '' }
    if (-not [string]::IsNullOrEmpty($secret)) { $text = $text.Replace($secret, '***') }
    $text = [regex]::Replace($text, '(https://[^:/@\s]+:)[^@\s]+@', '$1***@')
    $lines = @($text -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
    return ($lines -join "`n")
}

#: 一次 push 尝试（内含"**只有真被拒**才 force"的第二次尝试）。返回 @{ ok; msg }。
#: 抽成函数是因为"换一个 IP 再推一次"要用同一套逻辑 —— **同一件事不许两处实现**，
#: 否则 force 的判据迟早只长在一条路上。
#: -NoCredClear：**不**清空 credential helper —— 让凭据管理器（GCM）有机会供凭据。
#:   默认清空是隔离（只用 URL 里那个令牌）；兜底重推时要的就是"让 GCM 说话"。
function Invoke-Push([string]$authed, [string[]]$extra, [string]$tk, [switch]$NoCredClear) {
    $cred = @()
    if (-not $NoCredClear) { $cred = @('-c', 'credential.helper=') }
    $r = Invoke-GitText ($GitArgs + @($extra) + $cred + @('push', $authed, "HEAD:refs/heads/$Branch"))
    $msg = Hide-Secret $r.text $tk

    # ★★★ 只有**真的**历史不一致才去 force。
    #   以前是"只要退出码非 0 就当成历史不一致"，于是网络断了也去
    #   "按远端 tip 强制覆盖"，再失败时报一个更离谱的错 —— 用户看到的现象
    #   就是"永远被拒、永远发布不成功"，而真正原因（连不上）一次都没露过面。
    $realReject = $r.rc -ne 0 -and
                  ($msg -match 'non-fast-forward|fetch first|\[rejected\]|updates were rejected')
    if ($realReject) {
        Write-Warn2 "远端有本机没有的提交，按远端 tip 强制覆盖"
        # ⚠ 先把返回值存进变量再取 .text：`Invoke-GitText (...).text -split "x"` 这种
        #   一行到底的写法，命令模式会把 `.text` / `-split` 吃进参数表，函数照常返回
        #   hashtable —— 一字符串化就是 'System.Collections.Hashtable'，
        #   直接喂给 --force-with-lease（2026-11-06 实测就是这么红的）。
        $lr = Invoke-GitText ($GitArgs + @($extra) + $cred +
                              @('ls-remote', $authed, "refs/heads/$Branch"))
        $tip = (((@($lr.text -split "`n") | Select-Object -First 1) -split '\s+')[0])
        # 防呆：喂给 --force-with-lease 的必须是 SHA。拿不到合法 tip 就退回普通 --force，
        # 也**绝不**把一句错误文本当对象名塞进 git。
        if ($tip -and $tip -match '^[0-9a-f]{7,64}$') {
            $r = Invoke-GitText ($GitArgs + @($extra) + $cred +
                                 @('push', $authed, "HEAD:refs/heads/$Branch",
                                   "--force-with-lease=refs/heads/$Branch`:$tip"))
        } else {
            $r = Invoke-GitText ($GitArgs + @($extra) + $cred +
                                 @('push', $authed, "HEAD:refs/heads/$Branch", '--force'))
        }
        $msg = Hide-Secret $r.text $tk
    }
    return @{ ok = ($r.rc -eq 0); msg = $msg }
}

#: 把凭据拼进 https URL。**唯一**的装配点（Push-Tree / Push-Tag 都走它）。
#: ⚠ 令牌/用户名必须 `EscapeDataString` 之后才能进 URL：令牌里一个 `@` 就够让
#:   curl 把"令牌的尾巴"当成主机名 —— git 只会回一句 `URL rejected: Bad hostname`，
#:   看起来像"网络不通"，其实是本地拼 URL 就失败了（2026-11-06 实测复现：
#:   `https://u:202402@yyy@gitee.com` ⇒ unable to access 'https://yyy@gitee.com/...' Bad hostname）。
#:   顺带：含 `@` 的"令牌"多半是**登录密码**，不是私人令牌 —— 见上面的形状告警。
#: ⚠ 不用 `-replace` 拼接：替换串里 `$` 有特殊含义（`$1`、`$&`），令牌里碰上就会被吞。
# [EN] The single place that embeds credentials into an https URL. EscapeDataString first:
# [EN] one `@` in the token makes curl treat part of it as the host ("Bad hostname", looks like
# [EN] a network problem but is local URL assembly). No `-replace` here: `$` is special there.
function Get-AuthedUrl([string]$url, [string]$user, [string]$tk) {
    $u = [System.Uri]::EscapeDataString("$user")
    $k = [System.Uri]::EscapeDataString("$tk")
    if ($url.StartsWith('https://')) {
        return 'https://' + $u + ':' + $k + '@' + $url.Substring(8)
    }
    return $url
}

function Push-Tree([string]$dir, [string]$url, [string]$tk, [string]$user, [string]$label, [string]$kind) {
    Write-Step "Phase 5: push → $label"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    Push-Location $dir
    try {
        $hasOrigin = @(git remote 2>$null) -contains 'origin'
        if (-not $hasOrigin) { git remote add origin $url } else { git remote set-url origin $url }

        $authUser = if ($kind -eq 'github') { 'x-access-token' } else { $user }
        $authed = Get-AuthedUrl $url $authUser $tk

        $r = Invoke-Push $authed @() $tk

        # ── GitHub 的 IP 是**每天都会变**的：没指定 -GithubIp 时现场试一遍候选池 ──
        if (-not $r.ok -and $kind -eq 'github' -and $GithubIp -eq '' -and $r.msg -match $NetFailRe) {
            Write-Gray "github.com 这个 IP 又断了（这台机器上它一天能变几回），现场试一遍候选："
            $ip = Find-GithubIp
            if ($ip) {
                # 钉进 $GitArgs，而不是只给这一次 push —— tag 推送走同一个域名，
                # 只喂给 push 等于让 tag 再去撞那个死 IP。
                # ⚠ 必须写 `$script:` —— 函数里的 `$x +=` 是**赋值**，会在函数内新建一个
                #   同名局部变量，脚本级那份一动不动（现象：push 用了新 IP、tag 还是撞旧的）。
                $script:GitArgs += @(Get-GithubPinArgs $ip)
                Write-Ok "本轮能连的是 $ip —— 用它重推一次（想写死：-GithubIp $ip）"
                $r = Invoke-Push $authed @() $tk
            } else {
                Write-Warn2 "候选池里一个都连不上；稍后再试，或用 -Proxy 走代理"
            }
        }

        # ── 令牌能读不能写：换凭据管理器（GCM）里存的凭据再推一次 ──────────
        #   症状很迷惑（2026-11-06 实测）：第 1 次 push 拿到的是**真的** [rejected]
        #   （公开仓库的引用广告它读得到），force POST 写入时才 `Authentication failed`，
        #   看起来像"认证成功过又坏了"。其实令牌从头就没有写权限。
        #   必须先过 Test-GcmGithubCred 这道闸：没有存过凭据时走 helper 会弹
        #   GUI / 浏览器登录，无人值守跑就挂在那里。
        if (-not $r.ok -and $kind -eq 'github' -and $r.msg -match $AuthFailRe -and (Test-GcmGithubCred)) {
            Write-Warn2 "令牌被 GitHub 拒了（多半能读不能写），改用凭据管理器里存的凭据再推一次……"
            $r = Invoke-Push $url @() $tk -NoCredClear
            if ($r.ok) {
                $script:GhAuthByHelper = $true
                Write-Ok "凭据管理器的凭据可用（令牌侧建议仍去检查 scope：经典 PAT 勾 repo）"
            }
        }

        $msg = $r.msg
        if ($r.ok) {
            Write-Ok "$label push 成功（$Branch）"
            return $true
        }

        # ── 失败：先按**真实错误**分类，再给对应的话 ─────────────────
        Write-Err2 "$label push 失败"
        Write-Gray "git 的原话（令牌已抹掉）："
        foreach ($l in ($msg -split "`n")) { Write-Gray "    $l" }

        if ($msg -match 'Unsupported SSL backend') {
            Write-Warn2 "↑ 这是**本机 git 的 TLS 后端配置错**，不是网络、不是令牌。"
            Write-Gray "  · 配置里写的后端这个 git 没编进去（例如写 openssl、实际只有 schannel）；"
            Write-Gray "  · 一键修：git config --global http.sslBackend schannel（或用报错里列出的那个）"
        } elseif ($msg -match $NetFailRe) {
            Write-Warn2 "↑ 这是**连不上远端**，不是权限问题，重输令牌也没用。"
            if ($kind -eq 'github') {
                Write-Gray "  · hosts 里那条 github.com 很可能已经失效（这台机器上就失效过两次）；"
                Write-Gray "  · 换一个能用的 IP：-GithubIp 140.82.116.3（候选见脚本里的 `$GithubIpCandidates）"
            } else {
                Write-Gray "  · 本脚本已按直连跑（会覆盖 git 全局里残留的代理配置）；"
                Write-Gray "  · 确实要走代理：-Proxy http://127.0.0.1:端口"
            }
        } elseif ($msg -match $AuthFailRe) {
            Write-Warn2 "↑ 这是**凭据被拒**。"
            if ($kind -eq 'github') {
                Write-Gray "  · token 要有 repo 写权限：https://github.com/settings/tokens"
                Write-Gray "    经典 PAT 勾 repo；细粒度 PAT 勾 Contents 的 Read and write"
                Write-Gray "  · 本机凭据管理器里没有可用的 GitHub 凭据，才走到这里（有就会自动换它重推）"
            } else {
                Write-Gray "  · 令牌要勾 projects 读写，且必须是**私人令牌**（不是登录密码）"
                Write-Gray "  · 换过令牌：加 -ResetGiteeCred 重跑，或 -GiteeToken `"<新令牌>`""
            }
        } elseif ($msg -match 'not found|404|does not appear to be a git repository') {
            Write-Warn2 "↑ 远端说**找不到这个仓库**：可能还没建好，或这个 token 看不到它。"
        } else {
            Write-Gray "若不确定：以上面 git 的原话为准，别猜。"
        }
        return $false
    } finally {
        Pop-Location
        $ErrorActionPreference = $prevEap
    }
}

function Push-Tag([string]$dir, [string]$url, [string]$tk, [string]$user, [string]$kind, [string]$label) {
    $authUser = if ($kind -eq 'github') { 'x-access-token' } else { $user }
    $authed = Get-AuthedUrl $url $authUser $tk
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    Push-Location $dir
    try {
        if ($ReleaseNotes -ne "") {
            git tag -a $tag -m "Release $tag" -m $ReleaseNotes 2>$null
        } else {
            git tag -a $tag -m "Release $tag" 2>$null
        }
        $ready = $false
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
        } else {
            # tag 已存在：只要指向当前提交就复用（重跑发布时很常见）
            $tc = (git rev-list -n 1 $tag 2>$null) -join ""
            $hc = (git rev-parse HEAD 2>$null) -join ""
            if ($tc -and $tc -eq $hc) { Write-Ok "$label tag 已存在且指向当前提交，复用"; $ready = $true }
            else { Write-Err2 "$label tag '$tag' 已存在且指向别的提交 —— 换一个 tag，或先删旧 tag" }
        }
        if ($ready) {
            # ★ 令牌被拒、push 已换凭据管理器成功的 ⇒ tag 跟同一个决定，
            #   别让 tag 再拿那个能读不能写的令牌去撞一遍墙（撞完 Release 还建不出来）。
            #   决定只在 Push-Tree 兜底那一处做（$script:GhAuthByHelper），这里只消费。
            $tagUrl = $authed
            $tagCred = @('-c', 'credential.helper=')
            if ($script:GhAuthByHelper -and $kind -eq 'github') {
                $tagUrl = $url
                $tagCred = @()
                Write-Gray "tag 也走凭据管理器（令牌已证明不能写）"
            }
            $traw = @(git @GitArgs @tagCred push $tagUrl $tag 2>&1)
            if ($LASTEXITCODE -eq 0) {
                Write-Ok "$label tag 已推：$tag"
            } else {
                Write-Warn2 "$label tag 推送失败（tag 已存在，或推送被拒）"
                # 同样不许吞：tag 失败可能连带 Release 建不出来，而原因只有这行能说清
                $tmsg = Hide-Secret (($traw | ForEach-Object { "$_" }) -join "`n") $tk
                foreach ($l in ($tmsg -split "`n" | Select-Object -First 4)) { Write-Gray "    $l" }
            }
        }
    } finally {
        Pop-Location
        $ErrorActionPreference = $prevEap
    }
}

function Split-File {
    <# 把大文件切成 .part00/.part01…（Gitee Release 单附件常有 100MB 上限）；
       切完校验"分卷合计 == 源文件大小"，不等就报失败。 #>
    param([string]$FilePath, [int]$ChunkMB = 95)
    if (-not (Test-Path -LiteralPath $FilePath)) { Write-Err2 "文件不存在：$FilePath"; return @() }
    $size = (Get-Item -LiteralPath $FilePath).Length
    if ($size -le ($ChunkMB + 5) * 1MB) { return @($FilePath) }
    $prefix = "$FilePath.part"
    $existing = @(Get-ChildItem -Path "$FilePath.part*" -ErrorAction SilentlyContinue)
    if ($existing.Count -gt 0) {
        $newest = ($existing | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime
        if ($newest -ge (Get-Item -LiteralPath $FilePath).LastWriteTime) {
            Write-Ok "分卷已是最新：$($existing.Count) 个"
            return ($existing | Sort-Object Name).FullName
        }
    }
    Write-Gray "分卷 $([math]::Round($size/1MB,1)) MB → ${ChunkMB}MB/卷"
    $chunk = [int64]$ChunkMB * 1MB
    $inS = [System.IO.File]::OpenRead($FilePath)
    try {
        $buf = New-Object byte[] (4MB)
        $i = 0
        while ($inS.Position -lt $inS.Length) {
            $partPath = "{0}{1:D2}" -f $prefix, $i
            $outS = [System.IO.File]::Create($partPath)
            try {
                $w = [int64]0
                while ($w -lt $chunk -and $inS.Position -lt $inS.Length) {
                    $n = $inS.Read($buf, 0, [int][Math]::Min([int64]$buf.Length, $chunk - $w))
                    if ($n -le 0) { break }
                    $outS.Write($buf, 0, $n); $w += $n
                }
            } finally { $outS.Close() }
            $i++
        }
    } finally { $inS.Close() }
    $parts = @(Get-ChildItem -Path "$FilePath.part*" | Sort-Object Name)
    $sum = ($parts | Measure-Object -Property Length -Sum).Sum
    if ($sum -ne $size) { Write-Err2 "分卷校验失败：$sum ≠ $size"; return @() }
    Write-Ok "分卷完成：$($parts.Count) 个（合计与源文件一致）"
    return $parts.FullName
}

function Send-GitHubAsset {
    param([string]$OwnerRepo, [string]$Tag, [string]$Path, [string]$Token, [string]$Body)
    $h = @{ Authorization = "token $Token"; Accept = "application/vnd.github.v3+json"; 'User-Agent' = 'NovelWorldSimulator-publish' }
    $rel = $null
    try {
        $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$OwnerRepo/releases/tags/$Tag" `
                                 -Headers $h -Method Get -ErrorAction Stop
    } catch {
        $b = @{ tag_name = $Tag; name = "Release $Tag"; body = $Body } | ConvertTo-Json -Depth 5
        try {
            $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$OwnerRepo/releases" `
                                     -Headers $h -Method Post -Body $b -ContentType "application/json" -ErrorAction Stop
            Write-Ok "GitHub Release 已创建：$Tag"
        } catch {
            Write-Err2 "创建 GitHub Release 失败：$($_.Exception.Message)"; return $false
        }
    }
    $name = Split-Path $Path -Leaf
    $detail = Invoke-RestMethod -Uri "https://api.github.com/repos/$OwnerRepo/releases/$($rel.id)" `
                                -Headers $h -Method Get -ErrorAction SilentlyContinue
    if ($detail -and ($detail.assets | Where-Object { $_.name -eq $name })) {
        Write-Ok "已存在，跳过：$name"; return $true
    }
    $mb = [math]::Round((Get-Item -LiteralPath $Path).Length / 1MB, 1)
    Write-Gray "上传 $name（$mb MB）…… 开始 $(Get-Date -Format 'HH:mm:ss')"
    try {
        $resp = Invoke-WebRequest -Uri "https://uploads.github.com/repos/$OwnerRepo/releases/$($rel.id)/assets?name=$name" `
                                  -Method Post -Headers @{ Authorization = "token $Token"; Accept = "application/vnd.github.v3+json" } `
                                  -ContentType "application/octet-stream" -InFile $Path -TimeoutSec 3600 -ErrorAction Stop
        Write-Ok "上传成功：$name（HTTP $($resp.StatusCode)）$(Get-Date -Format ' HH:mm:ss')"
        return $true
    } catch {
        Write-Err2 "上传失败：$name — $($_.Exception.Message)"; return $false
    }
}

function Send-GiteeAsset {
    param([string]$OwnerRepo, [string]$Tag, [string]$Path, [hashtable]$Cred)
    $mb = [math]::Round((Get-Item -LiteralPath $Path).Length / 1MB, 1)
    if ($mb -gt 95) {
        Write-Warn2 "Gitee Release 附件通常限 100MB/个 ⇒ 自动分卷"
        $parts = Split-File -FilePath $Path
    } else {
        $parts = @($Path)
    }
    foreach ($p in $parts) {
        $nm = Split-Path $p -Leaf
        $curl = "C:\Program Files\Git\mingw64\bin\curl.exe"
        if (-not (Test-Path $curl)) { $curl = "curl.exe" }
        $env:MSYS_NO_PATHCONV = "1"
        $relId = $null
        try {
            $rels = Invoke-RestMethod -Uri "https://gitee.com/api/v5/repos/$OwnerRepo/releases?access_token=$($Cred.token)" -Method Get -ErrorAction Stop
            $hit = $rels | Where-Object { $_.tag_name -eq $Tag } | Select-Object -First 1
            if ($hit) { $relId = $hit.id }
        } catch {}
        if (-not $relId) {
            $out = & $curl -s -w "`n%{http_code}" -X POST "https://gitee.com/api/v5/repos/$OwnerRepo/releases" `
                -d "access_token=$($Cred.token)" -d "tag_name=$Tag" -d "target_commitish=$Branch" `
                -d "name=Release $Tag" -d "body=$ReleaseNotes" 2>&1
            $lines = $out -split "`n"
            if ($lines[-1].Trim() -in @('200','201')) {
                try { $relId = (($lines[0..($lines.Count-2)] -join "`n") | ConvertFrom-Json).id } catch {}
                Write-Ok "Gitee Release 已创建：$Tag"
            } else {
                Write-Err2 "创建 Gitee Release 失败（HTTP $($lines[-1].Trim())）"
            }
        }
        if ($relId) {
            Write-Gray "上传 $nm → Gitee ……"
            $o2 = & $curl -s -w "`n%{http_code}" -X POST "https://gitee.com/api/v5/repos/$OwnerRepo/releases/$relId/attach_files" `
                -F "access_token=$($Cred.token)" -F "file=@$p" --connect-timeout 30 --max-time 3600 2>&1
            $l2 = $o2 -split "`n"
            if ($l2[-1].Trim() -in @('200','201')) { Write-Ok "Gitee 附件成功：$nm" }
            else { Write-Err2 "Gitee 附件失败：$nm（HTTP $($l2[-1].Trim())）" }
        }
    }
}

# ============================================================
#  0. DryRun：只打印计划
# ============================================================
if ($DryRun) {
    $sides = @()
    if ($doGithub) { $sides += 'GitHub' }
    if ($doGitee)  { $sides += 'Gitee' }
    Write-Step ("DryRun：将发布到 " + ($sides -join ' + '))
    $ReleaseRoot0 = Join-Path $Sibling "发布版本"
    if ($doGithub) {
        Write-Host "  · GitHub: $(Get-Slug $RepoUrl)" -ForegroundColor Gray
        Write-Host "      工作区：$RepoDir" -ForegroundColor Gray
        Write-Host "      README.md = 英文（README_EN.md 的内容），中文 → README.zh-CN.md" -ForegroundColor Gray
    }
    if ($doGitee) {
        Write-Host "  · Gitee : $(Get-Slug $GiteeRepoUrl)" -ForegroundColor Gray
        Write-Host "      工作区：$GiteeRepoDir" -ForegroundColor Gray
        Write-Host "      README.md = 中文（原样），英文 → README.en.md" -ForegroundColor Gray
    }
    if ($ResetGiteeCred) {
        Write-Host "  · Gitee 凭据：先删掉本机保存的，再重新询问（-ResetGiteeCred）" -ForegroundColor Yellow
    }
    if ($NoCreate) {
        Write-Host "  1) 远端检查；不存在则**报错跳过**（-NoCreate）" -ForegroundColor Gray
    } else {
        Write-Host "  1) 远端检查；不存在则自动创建（auto_init=false，建完不勾 README）" -ForegroundColor Gray
    }
    Write-Host "  2) robocopy 镜像源码（排除：日志 / 发布包 / 离线运行时 / 用户作品 / 凭据 / 34MB gif）" -ForegroundColor Gray
    if (-not $WithDev) { Write-Host "     另外排除 developers\（要带就加 -WithDev）" -ForegroundColor Gray }
    Write-Host "  3) readme_variant.py 换位，并自检相对链接全部落在盘上" -ForegroundColor Gray
    Write-Host "  4) 密钥体检：真值全文搜 + 形态（带占位符判据）+ 键名长值" -ForegroundColor Gray
    Write-Host "  5) git init / add / commit（两边各自一份历史）" -ForegroundColor Gray
    # 计划里必须能看到**真正会写进历史的那句话** —— 否则 -CommitMessage 传没传、传对了没，
    # 只能等真的提交完才知道（而提交完就已经推上去了）。
    Write-Host "     commit -m `"$CommitMessage`"（工作区无变更则跳过提交）" -ForegroundColor Gray
    if ($NoPush) {
        Write-Host "  6) -NoPush：不推远端、不打 tag、不建 Release" -ForegroundColor Gray
    } else {
        Write-Host "  6) push（凭据只出现在命令行，不写 .git/config）" -ForegroundColor Gray
        if ($tag -ne "") {
            Write-Host "  7) tag $tag + Release$(if($UploadAsset){' + 附件'})" -ForegroundColor Gray
        }
    }
    Write-Host "`n（DryRun：什么都没做）" -ForegroundColor White
    exit 0
}

Write-Step ("阶段 B：发布到 " + (@($(if($doGithub){'GitHub'}), $(if($doGitee){'Gitee'})) -join ' + '))

if ($tag -ne "") {
    Write-Ok "tag = $tag    发布目录版本 = $bare"
} else {
    Write-Ok "没给 -Version ⇒ 不打 tag、不建 Release（只推代码）"
}

$ReleaseRoot = Join-Path $Sibling "发布版本"
if ($ReleaseDir -eq "") { $ReleaseDir = Join-Path $ReleaseRoot $bare }
$HasRelease = ($bare -ne "" -and (Test-Path -LiteralPath $ReleaseDir))
if ($HasRelease) {
    $nF = (Get-ChildItem -LiteralPath $ReleaseDir -Recurse -File -Force | Measure-Object).Count
    Write-Ok "发布包：$ReleaseDir（$nF 个文件）"
} elseif ($bare -ne "") {
    Write-Warn2 "没找到发布包目录：$ReleaseDir"
    Write-Warn2 "  不影响推源码仓库；但 -UploadAsset 需要它，请先跑 .\publish\build.ps1 -Zip"
}
if ($doGithub) { Write-Ok "GitHub 工作区：$RepoDir" }
if ($doGitee)  { Write-Ok "Gitee  工作区：$GiteeRepoDir" }

$ghSlug = Get-Slug $RepoUrl
$giSlug = Get-Slug $GiteeRepoUrl

# ============================================================
#  Phase 0：远端检查 / 创建
# ============================================================
$ghExists = $false
$giExists = $false
$gCred = $null

if ($ResetGiteeCred) {
    Write-Step "Phase 0.1: 重置 Gitee 凭据（-ResetGiteeCred）"
    Clear-GiteeCred
}

if (-not $NoPush) {
    Write-Step "Phase 0: 远端仓库检查"

    if ($doGithub) {
        try {
            $ghExists = Test-GitHubRepo $ghSlug $Token
        } catch {
            Write-Warn2 "GitHub 检查失败（网络 / 代理？）：$($_.Exception.Message)"
            Write-Gray "若代理没起：加 -NoProxy 重试"
            $ghExists = $null
        }
        if ($ghExists -eq $true) {
            Write-Ok "GitHub 仓库已存在：https://github.com/$ghSlug"
        } elseif ($ghExists -eq $false) {
            Write-Warn2 "GitHub 仓库不存在：https://github.com/$ghSlug"
            if ($NoCreate) {
                Write-Err2 "-NoCreate：不自动创建。请先在网页上建好空仓库（不要勾 README）。"
                $doGithub = $false
            } elseif ($Token -eq "") {
                Write-Err2 "自动建仓需要 GitHub PAT（-Token），没给 ⇒ 跳过 GitHub"
                $doGithub = $false
            } else {
                try {
                    $d = $Description
                    if ($d -eq "") { $d = "剧情推演器 / 设定试炼场 —— 小说创作辅助工具" }
                    New-GitHubRepo $ghSlug $Token $d
                } catch {
                    Write-Err2 "建 GitHub 仓库失败：$($_.Exception.Message)"
                    Write-Gray "常见原因：token 没有 repo 权限 / 同名仓库已存在 / 该账号无权建仓"
                    $doGithub = $false
                }
            }
        }
    }

    if ($doGitee) {
        try {
            $giExists = Test-GiteeRepo $giSlug
        } catch {
            Write-Warn2 "Gitee 检查失败（网络 / 代理？）：$($_.Exception.Message)"
            $giExists = $null
        }
        if ($giExists -eq $true) {
            Write-Ok "Gitee 仓库已存在：https://gitee.com/$giSlug"
        } elseif ($giExists -eq $false) {
            Write-Warn2 "Gitee 仓库不存在：https://gitee.com/$giSlug"
        }
    }

    # Gitee 凭据（建仓 / 推送都要用）
    if ($doGitee) {
        if ($GiteeToken -ne "") {
            $u = $GiteeUser
            if ($u -eq "") {
                $saved = Get-GiteeCred
                if ($saved) { $u = $saved.username }
            }
            if ($u -eq "") { $u = ($giSlug -split '/')[0] }
            $gCred = @{ username = $u; token = $GiteeToken }
            Write-Ok "Gitee 凭据：来自 -GiteeToken（用户 $u）"
        } else {
            $gCred = Get-GiteeCred
            if (-not $gCred) {
                Write-Warn2 "没有已保存的 Gitee 凭据，弹登录框……"
                $gCred = Set-GiteeCred
            }
            if ($gCred) {
                Write-Ok "Gitee 凭据：已保存的（用户 $($gCred.username)）"
                # 弹框输进来的令牌同样要过形状告警（跟 -GiteeToken / -Token 一个实现）
                Warn-TokenShape 'Gitee' $gCred.token
            }
        }
        if (-not $gCred) {
            Write-Err2 "没拿到 Gitee 凭据 ⇒ 跳过 Gitee（GitHub 侧不受影响）"
            $doGitee = $false
        }
    }

    if ($doGitee -and $giExists -eq $false) {
        if ($NoCreate) {
            Write-Err2 "-NoCreate：不自动创建。请先在网页上建好空仓库（不要勾 README）。"
            $doGitee = $false
        } else {
            try {
                $d = $Description
                if ($d -eq "") { $d = "剧情推演器 / 设定试炼场 —— 小说创作辅助工具" }
                New-GiteeRepo $giSlug $gCred.token $d
                $giExists = $true
            } catch {
                $em = "$($_.Exception.Message)"
                # ★ 401 与 403 必须分开：401 是"令牌本身不对"（重输才有用），
                #   403 是"令牌对但没权限"（重输一百次也没用，要去勾 projects）。
                #   曾经两者都说成"建仓失败"，用户唯一能做的就是反复重输。
                $code = 0
                try { if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode } } catch { }
                Write-Err2 "建 Gitee 仓库失败：$em"
                if ($code -eq 401 -or $em -match '\(401\)|Unauthorized') {
                    Write-Warn2 "401 = 令牌被拒（输错 / 过期 / 已被删除），不是权限问题。"
                    Clear-GiteeCred
                    Write-Gray "旧凭据已作废 ⇒ 重跑会重新问你。想跳过弹框就这样给："
                    Write-Gray "  .\publish.ps1 -Gitee -GiteeUser $($gCred.username) -GiteeToken `"<新令牌>`""
                } elseif ($code -eq 403 -or $em -match '\(403\)|Forbidden') {
                    Write-Warn2 "403 = 令牌有效，但没有建仓权限。去勾 projects 读写权限，**别重输令牌**。"
                    Write-Gray "  https://gitee.com/profile/personal_access_tokens"
                } else {
                    Write-Gray "常见原因：令牌没有 projects 读写权限 / 名字被占用 / 额度已满 / 代理没起。"
                    Write-Gray "若怀疑令牌输错：.\publish.ps1 -Gitee -ResetGiteeCred"
                }
                $doGitee = $false
            }
        }
    }
} else {
    Write-Step "Phase 0: 跳过（-NoPush：不检查、不建仓、不联网）"
    if ($doGitee -and $GiteeToken -ne "") {
        $gCred = @{ username = $GiteeUser; token = $GiteeToken }
    }
}

if (-not $doGithub -and -not $doGitee) { Write-Err2 "两边都没法发，结束"; exit 4 }

# ============================================================
#  .gitignore（两个工作区共用这一份）
# ============================================================
$GitIgnore = @'
# 由 publish\publish.ps1 生成 —— 这是**发布仓库**的忽略清单
.venv/
__pycache__/
*.py[cod]
*.log
*.bak*
*.bak-bilingual
*.exitbak
*~
*.old-*
nul

# 用户数据 / 密钥（同步阶段已排除，这里再兜一层）
.env
llm_models.json
usage.db
usage.db-journal
llm_cache.db
.nws_messages.jsonl
.install_manifest.json
.bilingual_done.json
.gitee-cred.enc
.gitee-user.txt

# 运行期产物
logs/
exports/
assets/screenshots/
generated-images/
launchers/dist/
novel_bench/results/
'@

# ============================================================
#  Phase 1：镜像
# ============================================================
if ($doGithub) {
    if (-not (Sync-Tree $RepoDir 'GitHub 工作区')) { $doGithub = $false }
    else { Add-ServiceShells $RepoDir 'GitHub' }
}
if ($doGitee) {
    if (-not (Sync-Tree $GiteeRepoDir 'Gitee 工作区')) { $doGitee = $false }
    else { Add-ServiceShells $GiteeRepoDir 'Gitee' }
}
if (-not $doGithub -and -not $doGitee) { Write-Err2 "镜像都没成功，结束"; exit 2 }

# ============================================================
#  Phase 2：README 换位（两个远端要的门面不一样）
# ============================================================
$Rv = Join-Path $PSScriptRoot 'readme_variant.py'
if ($doGithub) {
    Write-Step "Phase 2: GitHub 门面 → 英文 README.md"
    Push-Location $Root
    try { & $Py $Rv 'github' $RepoDir } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Write-Err2 "GitHub 的 README 换位失败"; $doGithub = $false }
}
if ($doGitee) {
    Write-Step "Phase 2: Gitee 门面 → 中文 README.md"
    Push-Location $Root
    try { & $Py $Rv 'gitee' $GiteeRepoDir } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Write-Err2 "Gitee 的 README 换位失败"; $doGitee = $false }
}
if (-not $doGithub -and -not $doGitee) { Write-Err2 "README 都没换位成功，结束"; exit 2 }

# ============================================================
#  Phase 3：密钥体检（推之前最后一道闸）
# ============================================================
Write-Step "Phase 3: 密钥体检"
if ($doGithub) { if (-not (Scan-Secrets $RepoDir 'GitHub 工作区')) { exit 3 } }
if ($doGitee)  { if (-not (Scan-Secrets $GiteeRepoDir 'Gitee 工作区'))  { exit 3 } }

# ============================================================
#  Phase 4：本地提交
# ============================================================
if ($doGithub) { if (-not (Commit-Tree $RepoDir 'GitHub')) { $doGithub = $false } }
if ($doGitee)  { if (-not (Commit-Tree $GiteeRepoDir 'Gitee'))  { $doGitee  = $false } }
if (-not $doGithub -and -not $doGitee) { Write-Err2 "两边都没提交成功，结束"; exit 2 }

if ($NoPush) {
    Write-Host "`n══════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "  -NoPush：两套工作区已生成并本地提交，未推任何远端" -ForegroundColor Cyan
    Write-Host "══════════════════════════════════════════" -ForegroundColor Cyan
    if ($doGithub) { Write-Host "  GitHub 工作区：$RepoDir（README.md = 英文）" -ForegroundColor White }
    if ($doGitee)  { Write-Host "  Gitee  工作区：$GiteeRepoDir（README.md = 中文）" -ForegroundColor White }
    Write-Host "  检查无误后去掉 -NoPush 再跑一次即可正式发布。" -ForegroundColor Gray
    Write-Host ""
    exit 0
}

# ============================================================
#  Phase 5：push
# ------------------------------------------------------------
#  ★★★ 不写 remote URL
#    旧写法是 `git remote set-url origin https://<token>@…`，推完再清掉。
#    可 `Ctrl+C` / 断网 / 异常退出时那一步**不会执行** ⇒ token 留在 `.git/config` 里。
#    改成"把凭据放在命令行给的 URL 上"：`.git/config` 里的 origin 永远是干净地址。
# ============================================================
$ghOk = $false
$giOk = $false
if ($doGithub) {
    $ghOk = Push-Tree $RepoDir $RepoUrl $Token '' 'GitHub' 'github'
    if ($ghOk) { Set-DefaultBranch 'github' $ghSlug $Token $Branch }
}
if ($doGitee) {
    $giOk = Push-Tree $GiteeRepoDir $GiteeRepoUrl $gCred.token $gCred.username 'Gitee' 'gitee'
    if ($giOk) { Set-DefaultBranch 'gitee' $giSlug $gCred.token $Branch }
}

# ============================================================
#  Phase 6：tag + Release + 附件
# ============================================================
if ($tag -ne "") {
    if ($ghOk) { Push-Tag $RepoDir $RepoUrl $Token '' 'github' 'GitHub' }
    if ($giOk) { Push-Tag $GiteeRepoDir $GiteeRepoUrl $gCred.token $gCred.username 'gitee' 'Gitee' }

    if ($UploadAsset) {
        Write-Step "Phase 6.1: 上传发布包到 Release 附件"
        if ($AssetPath -eq "") {
            $zipGuess = Join-Path $ReleaseRoot "$bare.zip"
            if (Test-Path -LiteralPath $zipGuess) { $AssetPath = $zipGuess }
        }
        if ($AssetPath -eq "" -or -not (Test-Path -LiteralPath $AssetPath)) {
            Write-Err2 "没找到附件。先跑 .\publish\build.ps1 -Zip，或用 -AssetPath 指定文件。"
        } else {
            Write-Gray "附件：$AssetPath（$([math]::Round((Get-Item -LiteralPath $AssetPath).Length / 1MB, 1)) MB）"
            if ($ghOk -and $Token -ne "") {
                $ok = Send-GitHubAsset -OwnerRepo $ghSlug -Tag $tag -Path $AssetPath -Token $Token -Body $ReleaseNotes
                if ($ok) { Write-Ok "GitHub 附件完成" } else { Write-Warn2 "GitHub 附件未完成" }
            } elseif ($ghOk) {
                Write-Warn2 "没给 -Token，跳过 GitHub 附件上传（需要 PAT）"
            }
            if ($giOk -and $gCred) {
                Send-GiteeAsset -OwnerRepo $giSlug -Tag $tag -Path $AssetPath -Cred $gCred
            }
        }
    } elseif ($HasRelease) {
        Write-Gray "提示：发布包在 $ReleaseDir；要一并挂到 Release 就加 -UploadAsset"
    }
}

# ============================================================
#  收尾：确认工作区里没有凭据残留
# ============================================================
Write-Step "收尾：确认工作区没留凭据"
foreach ($item in @(
        [pscustomobject]@{ Dir = $RepoDir;      On = $doGithub; Url = $RepoUrl },
        [pscustomobject]@{ Dir = $GiteeRepoDir; On = $doGitee;  Url = $GiteeRepoUrl })) {
    if (-not $item.On -or [string]::IsNullOrWhiteSpace($item.Dir)) { continue }
    $cfg = Join-Path $item.Dir ".git\config"
    if (-not (Test-Path -LiteralPath $cfg)) { continue }
    $txt = [System.IO.File]::ReadAllText($cfg, [System.Text.Encoding]::UTF8)
    if ($txt -match '(?i)(ghp_|github_pat_|glpat-|x-access-token|https://[^/\s]+:[^/\s]+@)') {
        Write-Warn2 "$($item.Dir) 的 .git/config 里疑似有凭据，正在抹掉"
        Push-Location $item.Dir
        try { git remote set-url origin $item.Url 2>$null } finally { Pop-Location }
    } else {
        Write-Ok "$($item.Dir) 的 .git/config 干净"
    }
}

# ============================================================
#  汇总
# ============================================================
Write-Host "`n══════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  发布完成" -ForegroundColor Cyan
Write-Host "══════════════════════════════════════════" -ForegroundColor Cyan
if ($wantGithub) {
    $u = $RepoUrl -replace '\.git$', ''
    if ($ghOk) {
        Write-Host "  GitHub: $u  （README.md = 英文，中文在 README.zh-CN.md）" -ForegroundColor White
        if ($tag -ne "") { Write-Host "  Release: $u/releases/tag/$tag" -ForegroundColor White }
    } else {
        Write-Host "  GitHub: ✗ 未完成" -ForegroundColor Yellow
    }
}
if ($wantGitee) {
    $gu = $GiteeRepoUrl -replace '\.git$', ''
    if ($giOk) {
        Write-Host "  Gitee : $gu  （README.md = 中文，英文在 README.en.md）" -ForegroundColor White
        if ($tag -ne "") { Write-Host "  Release: $gu/releases/tag/$tag" -ForegroundColor White }
    } else {
        Write-Host "  Gitee : ✗ 未完成" -ForegroundColor Yellow
    }
}
if ($doGithub) { Write-Host "  GitHub 工作区: $RepoDir" -ForegroundColor Gray }
if ($doGitee)  { Write-Host "  Gitee  工作区: $GiteeRepoDir" -ForegroundColor Gray }
Write-Host ""

# 退出码：**本来要发**的那几边必须全成功。中途被跳过（建仓失败 / 没凭据）不能算绿 ——
# 否则 CI/回头一看"退出码 0"，而页面上根本没有这个仓库。
$allOk = $true
if ($wantGithub -and -not $ghOk) { $allOk = $false }
if ($wantGitee  -and -not $giOk) { $allOk = $false }
if ($allOk) { exit 0 } else { exit 4 }
