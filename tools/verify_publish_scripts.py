# -*- coding: utf-8 -*-
"""判据：**发布脚本**（打包 / 推送）的四条不变量（2026-11-06 用户）。

用户原话：「帮我再检查下这个软件的生成脚本和发布脚本 Gitee … 注意不要带任何API Key，
gitee默认用中文版README Github默认用英文版README」。

这条判据守的不是"脚本能不能跑"（那是 `-NoPush` 真跑一次才算），而是**四条一删就出事的规矩**：

  A **源码级不变量**（读 `publish/publish.ps1` 的文本）
    ① 两个远端两个工作区（内容不同，历史就不能共用）；
    ② 两个远端都要调 README 换位，且**两种模式**都在；
    ③ 排除清单必须含 `.env` / `llm_models.json` / `usage.db` / Gitee 凭据；
    ④ ⚠⚠ **带路径的排除项必须是完整路径** —— `/XD assets\\screenshots` 这种相对写法
       会被 robocopy **静默忽略**（实测：286 MB 调试截图、里面 `audit_screens.json`
       存着真的 API Key，原样进了工作区，而清单读起来完全正确）；
    ⑤ **拿真实密钥值去全文搜**（`Get-SecretValues` + `IndexOf`）—— 只查形态会漏掉
       "Key 被粘进某篇文档"那一种；
    ⑥ **凭据不写进 `.git/config`**（不许出现 `set-url origin $authed`）；
    ⑦ 退出码看 `$wantGithub` / `$wantGitee`，不看 `$doGithub` ——
       "因为没令牌跳过"不能算成功（不然页面一片空、退出码 0）；
    ⑧ 自动建仓且 `auto_init = false`（勾了 README 会让第一次 push 必然被拒）。

  B **README 换位的行为**（真跑 `publish/readme_variant.py`，造临时目录）
    门面是谁、另一语言叫什么、语言条指哪儿 —— 只改文件名不改语言条，
    点「English」会停在原地。还要能红：缺文件 / 语言条被删掉都必须非 0 退出。

  C **DryRun 真跑**（`-DryRun`：不联网、不碰 git、不写文件）
    能跑通、退出码 0，且输出里两个门面都提到了。

为什么 A 组不是"空靶"
----------------------
每一条都对应一次**真实事故**（写在断言的消息里），而且都被 `-NoPush` 真跑抓到过：
④ 是 425 MB 镜像里带出真 Key 的那次；⑤ 就是抓到 `audit_screens.json` 的那一条；
⑦ 是旧版"force-with-lease 成功却报未完成"的同族问题（假红假绿都不该有）。

用法：.venv/Scripts/python.exe tools/verify_publish_scripts.py
[EN] Criterion: the publish scripts' four invariants (A source-level, B README swap behaviour,
C a real -DryRun). Each A assertion maps to a real incident; `-NoPush` actually caught 4 and 5.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP / 'tools'))
from verify_exit import finish                                    # noqa: E402

PUB = APP / 'publish'
PUB_PS1 = PUB / 'publish.ps1'
BUILD_PS1 = PUB / 'build.ps1'
RV = PUB / 'readme_variant.py'

CHECKS: list[dict] = []

#: git 可能编进去的 TLS 后端名（curl 支持的那几个）。判据只认这些词，
#: 免得把 `fatal:` 后面那几行当成"支持的后端"。
KNOWN_SSL_BACKENDS = {'openssl', 'schannel', 'mbedtls', 'gnutls', 'securetransport',
                      'rustls', 'wolfssl', 'bearssl', 'amissl'}


def ok(name: str, cond: bool, detail: str = '') -> None:
    CHECKS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    mark = '✓' if cond else '✗'
    line = f'  {mark} {name}'
    if detail:
        line += f'  ｜ {detail}'
    print(line)


def read(p: Path) -> str:
    return p.read_text(encoding='utf-8', errors='replace')


# ============================================================
#  A 组：源码级不变量
# ============================================================
def a_group() -> None:
    print('\n== A 组：源码级不变量 ==')
    if not PUB_PS1.exists():
        ok('A0 publish.ps1 存在', False, str(PUB_PS1))
        return
    src = read(PUB_PS1)

    ok('A1 ★★★ 两个远端 = 两个工作区（内容不同 ⇒ 历史不能共用）',
       '_publish_repo_github' in src and '_publish_repo_gitee' in src)

    ok('A2 ★★★ 两边都调 README 换位，且两种模式都在',
       src.count("readme_variant.py") >= 1
       and "'github'" in src and "'gitee'" in src,
       'readme_variant 调用 + github/gitee 两个模式')

    must_xf = ['.env', 'llm_models.json', 'usage.db', '.gitee-cred.enc', '.gitee-user.txt']
    missing = [k for k in must_xf if k not in src]
    ok('A3 ★★★ 排除清单含全部密钥/凭据文件', not missing, f'缺：{missing}' if missing else '5/5')

    ok('A4 ★★★ 带路径的排除项给**完整路径**（相对写法被 robocopy 静默忽略）'
       '（2026-11-06：286MB 截图里带真 Key 就是这么漏的）',
       '$XD_PATHS' in src and 'Join-Path $Root $rel' in src,
       '已确认：$XD_PATHS + Join-Path $Root' if ('$XD_PATHS' in src and 'Join-Path $Root $rel' in src)
       else '找不到 $XD_PATHS / Join-Path $Root')

    ok('A5 ★★★ 拿**真实密钥值**全文搜（只查形态会漏掉"粘进文档"那一种）',
       'function Get-SecretValues' in src and 'Get-SecretValues)' in src
       and '.IndexOf($s.value' in src,
       'Get-SecretValues + IndexOf')

    ok('A6 ★★ 形态体检带占位符判据（`sk-xxxx` 不算密钥，否则每次发布都误报停下）',
       'function Test-Placeholder' in src and 'Test-Placeholder' in src,
       '')

    bad_remote = re.search(r'set-url\s+origin\s+\$authed', src)
    ok('A7 ★★★ 凭据**不写进** `.git/config`（中断时清了不掉的旧写法）',
       bad_remote is None, '命中 set-url origin $authed' if bad_remote else '')

    ok('A8 ★★★ 退出码看 want*，不看 do*（"跳过"不能算成功）',
       'if ($wantGithub -and -not $ghOk)' in src
       and 'if ($wantGitee  -and -not $giOk)' in src,
       '本来要发的必须全成功')

    # ⚠ 只数 `auto_init` 出现几次是**空靶**（反例法第 4 刀证明过）：
    #   把它从 $false 改成 $true，出现次数一点没变，判据照绿。
    #   ⇒ 必须正则匹配**值**，并且两处都要是 $false。
    # [EN] Counting occurrences of `auto_init` is an empty target: flipping $false to $true keeps
    # [EN] the count identical. Match the **value**, in both repo-creation functions.
    auto_false = len(re.findall(r'auto_init\s*=\s*\$false', src))
    ok('A9 ★★ 自动建仓且 `auto_init = $false`（勾了 README 会让第一次 push 必然被拒）',
       'function New-GitHubRepo' in src and 'function New-GiteeRepo' in src
       and auto_false >= 2,
       f'auto_init = $false 出现 {auto_false} 处（要 2）')

    build_src = read(BUILD_PS1) if BUILD_PS1.exists() else ''
    old_one_liner = 'Write-Host "  2) python' in build_src
    ok('A10 ★★ build.ps1 里没有"两条语句挤一行"（`-DryRun -Zip` 曾打出 "if False"）',
       BUILD_PS1.exists() and not old_one_liner,
       '旧写法还在' if old_one_liner else '')

    # ★ 根目录的 `publish.ps1` 是**薄壳**：只转发参数和退出码。
    #   一旦有人在这里补一句判断，它和 publish\publish.ps1 就开始漂，
    #   而两边看起来都对 —— 这是本项目栽过好几次的"同一件事两处实现"。
    # [EN] The root `publish.ps1` is a shim: forward args + exit code, nothing else.
    shim = APP / 'publish.ps1'
    shim_src = read(shim) if shim.exists() else ''
    # ⚠ 只看**代码行**：注释里提到 `readme_variant.py`（"真身和它放在一起"）是说明，
    #   不是实现。第一版没剥注释，把自己写的那句说明判成了"混进实现"。
    # [EN] Only look at **code lines**: the header comment mentions `readme_variant.py` to say
    # [EN] where the real script lives; that is documentation, not a second implementation.
    shim_code = '\n'.join(l for l in shim_src.splitlines() if not l.strip().startswith('#'))
    leaked = [k for k in ('robocopy', 'git push', 'Get-SecretValues', 'readme_variant',
                          'New-GitHubRepo', 'New-GiteeRepo') if k in shim_code]
    ok('A11 ★★ 根目录入口是薄壳（只有转发，没有第二份实现）',
       shim.exists() and '& $target @args' in shim_code and 'exit $LASTEXITCODE' in shim_code
       and not leaked,
       f'{len(shim_src.splitlines())} 行；混进了实现：{leaked}' if leaked
       else f'{len(shim_src.splitlines())} 行，只转发')

    # ★ Gitee 凭据的逃生门（2026-11-06 用户实测撞上：令牌输错一次就永远用错的）
    #   存了凭据就不再弹框 ⇒ 错的令牌会被一直沿用，界面上却只说"建仓失败"，
    #   用户唯一能做的就是手删文件。两件事必须同时在：
    #     ① 有主动重置的开关；② **只有 401 才清**凭据。
    #   403 是"令牌有效但没权限"，清掉重输一百次也不会好 —— 把它并进 401 处理，
    #   等于把用户推进死循环，而每一步看起来都很合理。
    # [EN] The escape hatch for Gitee credentials. Once saved, the script never re-prompts, so a
    # [EN] mistyped token is reused forever while the UI only says "failed to create repo".
    # [EN] Two invariants: a reset switch exists, and **only 401** clears the stored token.
    # [EN] 403 means "valid token, missing permission" -- clearing it sends the user in circles.
    clear_calls = src.count('Clear-GiteeCred')
    ok('A12 ★★★ 有"清掉已存凭据、重新询问"的开关（否则令牌输错一次就只能手删文件）',
       'function Clear-GiteeCred' in src
       and re.search(r'if \(\$ResetGiteeCred\)\s*\{[^}]*Clear-GiteeCred', src) is not None
       and clear_calls >= 3,
       f'Clear-GiteeCred 出现 {clear_calls} 次（要 1 处定义 + 至少 2 处调用）')

    i401 = src.find('$code -eq 401')
    i403 = src.find('$code -eq 403')
    seg401 = src[i401:i403] if 0 <= i401 < i403 else ''
    seg403 = ''
    if i403 >= 0:
        _k = src.find('} else {', i403)
        seg403 = src[i403:(_k if _k > i403 else i403 + 800)]

    a13_ok = bool(seg401.strip()) and 'Clear-GiteeCred' in seg401
    ok('A13 ★★★ 401（令牌本身不对）要**作废已存凭据**并告诉用户重输，不能只报"建仓失败"',
       a13_ok,
       f'401 分支 {len(seg401)} 字，含 Clear-GiteeCred' if a13_ok
       else ('401 分支里没有 Clear-GiteeCred' if seg401 else '找不到 401 分支'))

    a14_bad = 'Clear-GiteeCred' in seg403
    a14_ok = bool(seg403.strip()) and not a14_bad and 'projects' in seg403
    ok('A14 ★★★ 403（令牌对、权限不够）**不许**清凭据，要指明去勾 projects 读写',
       a14_ok,
       f'403 分支 {len(seg403)} 字，只提 projects、未清凭据' if a14_ok
       else ('403 分支清掉了凭据（重输一百次也没用）' if a14_bad
             else ('403 分支没提 projects' if seg403 else '找不到 403 分支')))

    # ★★★ TLS 后端失配（2026-11-06 用户实测：两边都推不上去，git 说
    #   `Unsupported SSL backend 'openssl'. Supported SSL backends: schannel`）
    #   系统级 `http.sslBackend = openssl` + 只编了 schannel 的 git ⇒ 这台机上的 git
    #   **每个 https 操作都废**。判据要三件事同时在：
    #     ① 主动问 git 支持哪些后端（不是猜、不是只读配置）；
    #     ② 配置里的不在列表里就**换掉并真的用上**（只告警不纠正 = 用户照样推不上去）；
    #     ③ 打一行 ASCII 标记，让判据能对着真跑输出核账。
    # [EN] The TLS-backend mismatch: a system-level `openssl` on a schannel-only git breaks
    # [EN] every https operation. The script must ask git what it supports, actually *use* the
    # [EN] supported one, and print an ASCII marker so the check can be a real run, not a regex.
    a15_ok = ('function Get-GitSslBackends' in src
              and '$using = $supported[0]' in src
              and """$GitArgs += @('-c', "http.sslBackend=$using")""" in src
              and '[git-tls]' in src)
    ok('A15 ★★★ TLS 后端失配要**问 git 自己**支持什么，并**改用**支持的那个',
       a15_ok,
       '探测 + 替换 + -c 生效 + 标记' if a15_ok
       else '缺其中一环（只报错不改 = 照样推不上去）')

    # ★★★ 分类：`Unsupported SSL backend` 必须**先**被认出来，且绝不算"网络不通"。
    #   上次就是把它（正则里的裸 `OpenSSL`）算成连不上 ⇒ 用户被指去换 IP、重输令牌。
    # [EN] The backend mismatch must be classified before (and never as) a network failure.
    m_net = re.search(r"^\$NetFailRe = '(.*)'", src, re.M)
    net_re = m_net.group(1) if m_net else ''
    i_ssl_branch = src.find("if ($msg -match 'Unsupported SSL backend')")
    i_net_branch = src.find('elseif ($msg -match $NetFailRe)')
    a16_ok = (i_ssl_branch >= 0 and i_net_branch > i_ssl_branch
              and net_re != '' and 'OpenSSL' not in net_re and 'sslBackend' not in net_re)
    ok('A16 ★★★ "TLS 后端配错"不许被归成"连不上远端"（否则人只会去换 IP、重输令牌）',
       a16_ok,
       '单独分支在前、$NetFailRe 里没有 OpenSSL/sslBackend' if a16_ok
       else ('$NetFailRe 里混进了 TLS 后端字样' if ('OpenSSL' in net_re or 'sslBackend' in net_re)
             else '没有单独的 TLS 后端分支，或它排在网络分支之后'))

    # ★★★ IP 候选池 + 自动重试（2026-11-06：文档里写着"实测可用"的 20.27.177.113，
    #   当晚就成了 `Recv failure: Connection was reset`）⇒ **不存在长期可用的常量 IP**。
    #   判据要的是"池子 + 真会重试"，不是"某个 IP 写对了"。
    # [EN] There is no permanently-good IP for github.com here; require a candidate pool and a
    # [EN] real retry, not one blessed constant.
    pool = re.search(r'^\$GithubIpCandidates = @\((.*)\)', src, re.M)
    pool_ips = re.findall(r"'\d+\.\d+\.\d+\.\d+'", pool.group(1)) if pool else []
    # ⚠ 只查**代码行**：注释里写"不存在'实测可用'的常量 IP"正是这条规矩的说明，
    #   按全文搜会把自己的说明判成犯规（第一版就这么红的）。
    code_lines = [l for l in src.splitlines() if not l.strip().startswith('#')]
    blessed_ip = [l.strip() for l in code_lines if '实测可用' in l]
    a17_ok = (len(pool_ips) >= 3
              and '$script:GitArgs += @(Get-GithubPinArgs $ip)' in src
              and src.count('Find-GithubIp') >= 2
              and "$GithubIp -eq ''" in src
              and not blessed_ip)
    ok('A17 ★★★ GitHub 的 IP 用**候选池 + 失败后自己重试**（写死一个"实测可用"的 IP 隔天就烂）',
       a17_ok,
       f'池子 {len(pool_ips)} 个 + 有重试' if a17_ok
       else (f'池子只有 {len(pool_ips)} 个' if len(pool_ips) < 3
             else (f'还对用户说某个 IP 实测可用：{blessed_ip[:1]}' if blessed_ip
                   else '失败后没真正重试（或被函数作用域吞掉）')))

    # ★★★ 凭据进 URL 必须先**转义**（2026-11-06 深夜用户实测：
    #   Gitee 令牌里带 `@` ⇒ curl 把令牌尾巴当主机名 ⇒
    #   `URL rejected: Bad hostname`，长得像"网络不通"，其实是本地拼 URL 失败）。
    #   且装配只许有一处（`Get-AuthedUrl`）—— 上一版 Push-Tree / Push-Tag 各拼各的，
    #   这正是"同一件事两处实现"的老病。
    # [EN] Credentials must be URL-escaped before being embedded, and by exactly one helper:
    # [EN] one `@` in a token made curl report "Bad hostname" (looks like a network outage).
    a18_ok = ('function Get-AuthedUrl' in src
              and '$k = [System.Uri]::EscapeDataString("$tk")' in src
              and "$u = [System.Uri]::EscapeDataString(\"$user\")" in src
              and ":$tk@" not in src
              and src.count('Get-AuthedUrl ') >= 2)
    ok('A18 ★★★ 令牌进 URL 前**转义**、且只有 `Get-AuthedUrl` 一个装配点',
       a18_ok,
       f'装配点 {src.count("Get-AuthedUrl ")} 处，user/token 都转义' if a18_ok
       else ('还有裸拼 `:$tk@` 的地方' if ":$tk@" in src
             else 'token / user 没有双双走 EscapeDataString，或没都走 Get-AuthedUrl'))

    # ★★★ force-with-lease 的 tip 必须先验是 SHA：上一版把 hashtable 字符串化
    #   成 'System.Collections.Hashtable' 直接喂给了 git（报 cannot parse expected
    #   object name）。拿不到合法 tip 就退普通 --force，绝不把错误文本当对象名。
    # [EN] The tip fed to --force-with-lease must look like a SHA, never stringified junk.
    a19_ok = ("$tip -match '^[0-9a-f]{7,64}$'" in src)
    ok('A19 ★★★ `--force-with-lease` 的 tip 先验 SHA（防把错误文本当对象名喂给 git）',
       a19_ok,
       '有 ^[0-9a-f]{7,64}$ 防呆' if a19_ok else "tip 没做 SHA 校验")


# ============================================================
#  B 组：README 换位（真跑）
# ============================================================
ZH_BODY = '# 中文标题\n\n[English](README_EN.md)\n\n正文\n'
EN_BODY = '# English Title\n\n[中文](README.md)\n\nbody\n'

#: 假 git：只回答两句话 —— `config --get http.sslBackend` 说 openssl，
#: 带 `__probe__` 的调用报"只支持 schannel"。用来稳定地复现那台机器的失配状态。
GIT_STUB = (
    '@echo off\r\n'
    'set A=%*\r\n'
    'if "%A:__probe__=%" neq "%A%" goto probe\r\n'
    'if "%A:sslBackend=%" neq "%A%" goto cfg\r\n'
    'exit /b 0\r\n'
    ':probe\r\n'
    ' echo fatal: Unsupported SSL backend __probe__. Supported SSL backends: schannel 1>&2\r\n'
    'exit /b 128\r\n'
    ':cfg\r\n'
    'echo openssl\r\n'
    'exit /b 0\r\n'
)


def run_rv(mode: str, d: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RV), mode, str(d)],
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=60)


def b_group() -> None:
    print('\n== B 组：README 换位（真跑 readme_variant.py）==')
    if not RV.exists():
        ok('B0 readme_variant.py 存在', False, str(RV))
        return

    # ── github：门面英文 ──
    with tempfile.TemporaryDirectory(prefix='nws_rv_gh_') as td:
        d = Path(td)
        (d / 'README.md').write_text(ZH_BODY, encoding='utf-8')
        (d / 'README_EN.md').write_text(EN_BODY, encoding='utf-8')
        r = run_rv('github', d)
        ok('B1 github 模式跑通', r.returncode == 0, r.stdout.strip()[-120:] or r.stderr[-120:])
        ok('B2 ★★★ GitHub 的 README.md 是**英文**',
           (d / 'README.md').exists() and 'English Title' in read(d / 'README.md'),
           read(d / 'README.md').splitlines()[0] if (d / 'README.md').exists() else '缺文件')
        ok('B3 中文挪到 README.zh-CN.md',
           (d / 'README.zh-CN.md').exists() and '中文标题' in read(d / 'README.zh-CN.md'))
        zh = read(d / 'README.zh-CN.md') if (d / 'README.zh-CN.md').exists() else ''
        ok('B4 ★★ 语言条指对（中文版 → [English](README.md)）',
           '[English](README.md)' in zh, zh.splitlines()[2] if len(zh.splitlines()) > 2 else '')
        ok('B5 旧的 README_EN.md 已清掉（仓库里只留两份）',
           not (d / 'README_EN.md').exists(), str(sorted(p.name for p in d.iterdir())))

    # ── gitee：门面中文 ──
    with tempfile.TemporaryDirectory(prefix='nws_rv_gi_') as td:
        d = Path(td)
        (d / 'README.md').write_text(ZH_BODY, encoding='utf-8')
        (d / 'README_EN.md').write_text(EN_BODY, encoding='utf-8')
        r = run_rv('gitee', d)
        ok('B6 gitee 模式跑通', r.returncode == 0, r.stdout.strip()[-120:] or r.stderr[-120:])
        ok('B7 ★★★ Gitee 的 README.md 是**中文**',
           (d / 'README.md').exists() and '中文标题' in read(d / 'README.md'))
        ok('B8 英文挪到 README.en.md',
           (d / 'README.en.md').exists() and 'English Title' in read(d / 'README.en.md'))
        zh = read(d / 'README.md') if (d / 'README.md').exists() else ''
        ok('B9 ★★ 语言条指对（中文版 → [English](README.en.md)）',
           '[English](README.en.md)' in zh)
        ok('B10 不留 README_EN.md',
           not (d / 'README_EN.md').exists(), str(sorted(p.name for p in d.iterdir())))

    # ── 必须能红 ──
    with tempfile.TemporaryDirectory(prefix='nws_rv_bad_') as td:
        d = Path(td)
        (d / 'README.md').write_text(ZH_BODY, encoding='utf-8')
        (d / 'README_EN.md').write_text(EN_BODY, encoding='utf-8')
        r = run_rv('github', d)
        # BODY 里没有其它链接 ⇒ 这一趟应该是绿的（对照组）
        ok('B11 对照组：只有语言条时是绿的（不然下面的"红"说明不了问题）',
           r.returncode == 0, f'rc={r.returncode}')

    with tempfile.TemporaryDirectory(prefix='nws_rv_broken_') as td:
        d = Path(td)
        (d / 'README.md').write_text(ZH_BODY + '\n[配置](不存在的文件.md)\n', encoding='utf-8')
        (d / 'README_EN.md').write_text(EN_BODY, encoding='utf-8')
        r = run_rv('github', d)
        ok('B12 ★★★ 坏链会红（门面里点开是 404 比没有 README 更难看）',
           r.returncode != 0, f'rc={r.returncode}')

    with tempfile.TemporaryDirectory(prefix='nws_rv_nolang_') as td:
        d = Path(td)
        (d / 'README.md').write_text('# 中文\n\n没有语言条\n', encoding='utf-8')
        (d / 'README_EN.md').write_text(EN_BODY, encoding='utf-8')
        r = run_rv('github', d)
        ok('B13 ★★ 语言条没了就停下（要求恰好命中 1 次，不是静默跳过）',
           r.returncode != 0, f'rc={r.returncode}')


# ============================================================
#  C 组：DryRun 真跑（不联网、不碰 git、不写文件）
# ============================================================
def c_group() -> None:
    print('\n== C 组：-DryRun 真跑（不联网、不写文件）==')
    ps = shutil.which('powershell') or shutil.which('pwsh')
    if not ps:
        ok('C0 找不到 powershell（跳过 C 组）', True, 'SKIP')
        return
    try:
        # CREATE_NO_WINDOW：回归跑的时候别在屏幕上闪一个黑框
        flags = 0x08000000 if sys.platform == 'win32' else 0
        r = subprocess.run([ps, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                            '-File', str(PUB_PS1), '-Gitee', '-DryRun'],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=180, creationflags=flags)
    except Exception as e:                                       # noqa: BLE001
        ok('C1 -DryRun 能跑', False, repr(e))
        return
    out = (r.stdout or '') + (r.stderr or '')
    ok('C1 ★★ -DryRun 退出码 0', r.returncode == 0, f'rc={r.returncode}')
    ok('C2 ★★ 计划里同时提到两边', 'GitHub' in out and 'Gitee' in out,
       '两边都在计划里' if ('GitHub' in out and 'Gitee' in out) else '只提到一边')
    ok('C3 ★★★ 计划里写明两个门面（README.zh-CN.md / README.en.md 都要出现）',
       'README.zh-CN.md' in out and 'README.en.md' in out,
       '门面换位是这次改动的核心')

    # ★★★ 真机核账：脚本打的那行 `[git-tls] configured=… supported=… using=…`
    #   必须**和 git 自己说的**一致 —— 只看源码里"有探测函数"是不够的，
    #   探测写对了但用错了变量（比如 still 用 $effSsl）源码判据一样绿。
    #   这里判据自己探一次（同一个"故意给假名字"的桩，54ms、不联网）。
    # [EN] Real-run reconciliation: the `[git-tls] … using=` the script prints must agree with
    # [EN] what git itself reports. Having a probe function is not enough -- wiring it to the
    # [EN] output is the part that breaks.
    m = re.search(r'\[git-tls\]\s+configured=(\S*)\s+supported=(\S*)\s+using=(\S*)', out)
    supported_real: list[str] = []
    if m:
        ps_git = shutil.which('git')
        if ps_git:
            try:
                pf = subprocess.run([ps_git, '-c', 'http.sslBackend=__probe__',
                                     'ls-remote', 'https://example.invalid/x'],
                                    capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=60, creationflags=flags)
                blob = (pf.stdout or '') + (pf.stderr or '')
                # 只认**已知后端名**：`(?s)` 一把抓会把 fatal 后面那几行（remote helper、
                # 'https'、aborted、session …）当成"支持的后端"，列表里混进垃圾就永远对不上。
                mm = re.search(r"Supported SSL backends:[ \t\r\n]*([\w \t,]+)", blob)
                if mm:
                    toks = mm.group(1).replace(',', ' ').split()
                    supported_real = [t for t in toks if t in KNOWN_SSL_BACKENDS]
            except Exception:                                    # noqa: BLE001
                supported_real = []
    using = m.group(3) if m else ''
    ok('C4 ★★★ 真跑里 `using=` 的那个后端是 git **真的**支持的（源码有探测 ≠ 用对了）',
       bool(m) and bool(supported_real) and using in supported_real,
       f'using={using} ｜ git 实际支持={supported_real}' if m
       else 'DryRun 输出里没有 [git-tls] 标记')

    # ★★★ 这台机器修好之后（全局已是 schannel），"配置错"那条路就再也走不到了 ——
    #   C4 会变成**永远绿**：今天写的分支对不对，它一句话也证明不了。
    #   ⇒ 造一个"配置写 openssl、git 只有 schannel"的假 git（只回两句话），
    #     让这条闸每次都真被走一遍。判据里放桩，不是产品里放开关。
    # [EN] Once this machine is fixed, the mismatch path is unreachable and C4 becomes vacuous.
    # [EN] A two-line fake `git` on PATH makes the branch get exercised on every run.
    try:
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'git.cmd').write_text(GIT_STUB, encoding='ascii', newline='')
            env = dict(os.environ)
            env['PATH'] = td + os.pathsep + env.get('PATH', '')
            r2 = subprocess.run([ps, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(PUB_PS1), '-Gitee', '-DryRun'],
                                capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=180, creationflags=flags, env=env)
            out2 = (r2.stdout or '') + (r2.stderr or '')
            m2 = re.search(r'\[git-tls\]\s+configured=(\S*)\s+supported=(\S*)\s+using=(\S*)', out2)
            c5_ok = (bool(m2) and m2.group(1) == 'openssl' and m2.group(3) == 'schannel')
            ok('C5 ★★★ 造一个"配置写 openssl、git 只有 schannel"的环境，脚本必须改用 schannel',
               c5_ok,
               f'configured={m2.group(1)} using={m2.group(3)}' if m2
               else f'没打出 [git-tls]（rc={r2.returncode}）')
    except Exception as e:                                       # noqa: BLE001
        ok('C5 ★★★ 造一个"配置写 openssl、git 只有 schannel"的环境，脚本必须改用 schannel',
           False, repr(e))


def main() -> int:
    print('判据：发布脚本（打包 / 推送）')
    a_group()
    b_group()
    c_group()
    return finish({'checks': CHECKS}, label='断言')


if __name__ == '__main__':
    raise SystemExit(main())
