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


# ============================================================
#  B 组：README 换位（真跑）
# ============================================================
ZH_BODY = '# 中文标题\n\n[English](README_EN.md)\n\n正文\n'
EN_BODY = '# English Title\n\n[中文](README.md)\n\nbody\n'


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


def main() -> int:
    print('判据：发布脚本（打包 / 推送）')
    a_group()
    b_group()
    c_group()
    return finish({'checks': CHECKS}, label='断言')


if __name__ == '__main__':
    raise SystemExit(main())
