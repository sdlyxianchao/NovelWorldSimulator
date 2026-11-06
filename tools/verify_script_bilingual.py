# -*- coding: utf-8 -*-
"""验证：setup / start / uninstall 那一圈脚本的提示语**都是中英双语**。

为什么要专门验这个
------------------
「漏一句英文」是**静默降级**：不报错、只是少一行，用户在控制台里看到半截中文
也不会来提。所以要有机器判据兜住。

判据分两层：
  A. `tools/platform_install.py`（安装器本体，setup/uninstall 的输出都来自它）
     A1 三个动作 × 三个平台都跑一遍，输出里**不许有漏译句**（`untranslated()` 为空）
     A2 **静态穷举**：用 AST 把每一处 `self.say(…)` / `_touch(…, '…')` 的字面量抽出来，
        把 f-string 的变量位替换成探针值，逐句试翻 —— 这样连
        **运行时走不到的分支**（macOS / Linux 那几段）也能覆盖
     A3 每条含中文的输出行，**下一行必须是对应的英文**（配对结构）
  B. **启动器**（`launchers/` 的 Go 源码）与**进度窗**（`tools/launcher_progress.py`）
     ★ 2026-10-10 改判：原来守的是 `setup/start/uninstall` 那 9 个 `.bat`/`.sh`/
       `.command`（用户要求「删掉，只留 exe」）。**守护的东西没变**，
       只是对象换成了启动器 —— 那一圈的话同样是给用户看的，
       漏一句英文同样是"英文用户看到半句中文"的静默降级。
     B0 真的抽查到了调用点（**脚本删掉之后最容易犯的病：扫了个空集合、于是恒真**）
     B1 每条 `notify(中文标题, 英文标题, 中文正文, 英文正文, 是否错误)` 五段齐全
     B1b 每条 `confirm(中文标题, 英文标题, 中文正文, 英文正文)` 四段齐全
         （卸载前的确认框 —— 用户点「取消/确定」之前唯一看到的东西）
     B2 每条 `bi(中文, 英文)` 的英文那一半里**不许出现中文**
     B3 进度窗自己的按钮/状态文案都是 `中文 / English`
     ⚠ 扫的是 `launchers/*.go` **全量**（不是一张写死的名单）：新加的 Go 文件、
       新加的文案调用点都自动进判据。写死的名单会过期，过期的表现就是
       "新加的文案没人守" —— 这一轮真踩到了（`confirm` 就是这么漏掉的）。

用法：.venv/Scripts/python.exe tools/verify_script_bilingual.py
产出：assets/screenshots/script_bilingual_report.json

English:
Verification: the prompts of the scripts around setup / start / uninstall **are all bilingual
Chinese-English**.
Why verify this specifically
------------------
"Missing one English line" is a **silent degradation**: no error, just one fewer line; the user
sees half a Chinese sentence in the console
and won't report it. So machine criteria are needed to catch it.
Criteria are split into two layers:
  A. `tools/platform_install.py` (the installer itself, both setup/uninstall output comes from it)
     A1 Run all three actions × three platforms, output **must not have untranslated sentences** (`untranslated()` is empty)
     A2 **Static exhaustive enumeration**: use AST to extract every literal at `self.say(…)` / `_touch(…, '…')`,
        replace f-string variable slots with probe values, try translating each sentence -- this way even
        **branches unreachable at runtime** (the macOS / Linux sections) get covered
     A3 For every output line containing Chinese, **the next line must be the corresponding English** (paired structure)
  B. **Launcher** (Go source under `launchers/`) and **progress window** (`tools/launcher_progress.py`)
     ★ 2026-10-10 criteria change: previously guarded the 9 `.bat`/`.sh`/
       `.command` under `setup/start/uninstall` (user asked to "delete them, keep only the exe"). **What is guarded has not changed**,
       only the object switched to the launcher -- that ring of text is also shown to the user,
       missing one English line is likewise a silent degradation of "English user sees half a Chinese sentence".
     B0 Actually spot-checked the call sites (**the easiest mistake after deleting the scripts: scanned an empty set, so it is vacuously true**)
     B1 Every `notify(Chinese title, English title, Chinese body, English body, is_error)` has all five parts present
     B1b Every `confirm(Chinese title, English title, Chinese body, English body)` has all four parts present
         (the confirmation dialog before uninstall -- the only thing the user sees before clicking "Cancel/OK")
     B2 In every `bi(Chinese, English)` the English half **must not contain Chinese**
     B3 The progress window's own button/status text is all `Chinese / English`
     ⚠ Scanning `launchers/*.go` **in full** (not a hardcoded list): newly added Go files,
       newly added text call sites are all automatically covered by the criteria. A hardcoded list goes stale, and going stale shows up as
       "newly added text no one guards" -- this round actually hit it (`confirm` was missed exactly this way).
Usage: .venv/Scripts/python.exe tools/verify_script_bilingual.py
Output: assets/screenshots/script_bilingual_report.json
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

CJK = re.compile(r'[\u3400-\u9fff]')
LATIN_WORD = re.compile(r'[A-Za-z]{2,}')
ITEMS: list[dict] = []
REPORT: dict = {}



def ok(name: str, cond, detail='') -> bool:
    ITEMS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:300]})
    print(f"[{'OK' if cond else 'FAIL'}] {name}" + (f'  — {detail}' if detail else ''))
    return bool(cond)


# ══════════════════════════════════════════════════════════════
#  A. 安装器本体
# [EN] A. The installer itself
# ══════════════════════════════════════════════════════════════
def _import_installer():
    import platform_install as PI
    return PI


def check_runtime(PI) -> None:
    """三个动作 × 三个平台真跑一遍，逐行检查配对。
        English:
    Run all three actions × three platforms for real, check pairing line by line.
    """
    tmp = Path(APP_DIR / '_bi_tmp')          # 只用于 dry-run，不会真写
    # [EN] Only used for dry-run, will not actually write
    all_lines: list[str] = []
    for plat in ('windows', 'macos', 'linux'):
        for act in ('install', 'uninstall', 'status'):
            inst = PI.Installer(dest_root=tmp, dry_run=True, verbose=True)
            inst.plat = plat                     # 强制走该平台分支
            # [EN] Force this platform branch
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    if act == 'install':
                        inst.install()
                    elif act == 'uninstall':
                        inst.uninstall(purge=True, assume_yes=True)
                    else:
                        inst.status()
            except Exception as e:               # noqa: BLE001
                ok(f'A1 {plat}/{act} 跑得通（不抛异常）', False, repr(e)[:160])
                continue
            all_lines.extend(buf.getvalue().splitlines())

    missing = PI.untranslated()
    ok('A1a 三个动作 × 三个平台跑完，没有任何漏译句',
       not missing, f'{len(missing)} 句：{missing[:3]}')

    # A2 配对结构：含中文的行，紧跟着的下一行必须是"它的英文"
    #    （装饰行/纯路径行没有英文，按规则跳过）
    # [EN] A2 pairing structure: a line containing Chinese, the immediately following line must be "its
    # [EN] English"
    # [EN] (decoration lines/pure path lines have no English, skip per rules)
    bad_pair: list[str] = []
    i = 0
    while i < len(all_lines):
        line = all_lines[i]
        if CJK.search(line) and LATIN_WORD.search(line) is None:
            # 这一行是"纯中文"，下一行应当有英文
            # [EN] This line is "pure Chinese", the next line should have English
            nxt = all_lines[i + 1] if i + 1 < len(all_lines) else ''
            if not (nxt.strip() and CJK.search(nxt) is None
                    and LATIN_WORD.search(nxt)):
                bad_pair.append(line.strip()[:70])
            else:
                i += 1                          # 跳过它配对的英文行
                # [EN] Skip its paired English line
        i += 1
    ok('A2 每条中文提示都有紧邻的英文行', not bad_pair, bad_pair[:3])


def check_static(PI) -> None:
    """AST 穷举：把每处 say/_touch 的文案抽出来逐句试翻。

    这一步覆盖**运行时走不到的分支**（macOS 的 .app / Linux 的 .desktop 那几段），
    否则那些句子漏译也不会有人发现。
    
        English:
    AST exhaustive enumeration: extract the text of every say/_touch and try translating each
    sentence.
        This step covers **branches unreachable at runtime** (the macOS .app / Linux .desktop sections),
        otherwise a missing translation of those sentences would go unnoticed.
    """
    src = (APP_DIR / 'tools' / 'platform_install.py').read_text(encoding='utf-8')
    tree = ast.parse(src)

    # 模块级字符串常量：f-string 里常引用它们（如 f'{APP_ZH}  /  {APP_EN}'），
    # 不解析的话探针只能得到 'PROBE  /  PROBE'，判据就废了。
    # [EN] Module-level string constants: f-strings often reference them (e.g. f'{APP_ZH}  /  {APP_EN}'),
    # [EN] Without parsing, the probe can only get 'PROBE  /  PROBE', and the criterion is useless.
    consts: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and isinstance(node.value, ast.Constant) \
                        and isinstance(node.value.value, str):
                    consts[t.id] = node.value.value

    # `_touch()` 内部那句 `self.say(f'{what}: {path}')` 的 what 是**形参**，静态解析不了；
    # 它由下面收集的 `_touch(…, '条目名')` 调用点覆盖，这里跳过免得报假漏译。
    # [EN] The `what` in `self.say(f'{what}: {path}')` inside `_touch()` is a **formal parameter**, which
    # [EN] cannot be statically parsed;
    # [EN] It is covered by the `_touch(…, 'entry name')` call sites collected below, so skip it here to
    # [EN] avoid false missing-translation reports.
    skip_range = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_touch':
            skip_range = (node.lineno, node.end_lineno or node.lineno)

    def probe_all(node, depth: int = 0) -> list[str]:
        """把 f-string 的变量位换成探针值，还原出"半成品句子"。

        ★ 三件必须做对的事，否则会**报假漏译**（第一版就报了 3 条假的）：
          1. 模块常量要解析（`f'{APP_ZH}  /  {APP_EN}'` → 真句子）；
          2. **`if/else` 表达式要两个分支都试**：
             `f'… ({"存在" if x else "缺失"})'` 只取一支的话，
             另一支的英文规则就永远验不到；
          3. 组合数设上限，别为了一句话展开出几十种。
        
                English:
        Replace f-string variable slots with probe values, reconstructing the "half-finished sentence".
                ★ Three things that must be done right, otherwise it will **report false missing translations** (the first version reported 3 false ones):
                  1. Module constants must be resolved (`f'{APP_ZH}  /  {APP_EN}'` → real sentence);
                  2. **`if/else` expressions must try both branches**:
                     `f'… ({"存在" if x else "缺失"})'` if only one branch is taken,
                     the English rule of the other branch is never verified;
                  3. Cap the number of combinations; don't expand dozens of variants for a single sentence.
        """
        if depth > 4:
            return ['PROBE']
        if isinstance(node, ast.Constant):
            return [str(node.value)] if isinstance(node.value, str) else ['PROBE']
        if isinstance(node, ast.Name):
            return [consts[node.id]] if node.id in consts else ['PROBE']
        if isinstance(node, ast.IfExp):
            return (probe_all(node.body, depth + 1)
                    + probe_all(node.orelse, depth + 1))[:4]
        if isinstance(node, ast.JoinedStr):
            outs = ['']
            for v in node.values:
                if isinstance(v, ast.Constant):
                    outs = [o + str(v.value) for o in outs]
                else:
                    ex = getattr(v, 'value', None)
                    parts = probe_all(ex, depth + 1) if ex is not None else ['PROBE']
                    outs = [o + p for o in outs for p in parts][:8]
            return outs
        return ['PROBE']

    samples: list[tuple[int, str]] = []
    touches: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr == 'say' and node.args:
            if skip_range and skip_range[0] <= node.lineno <= skip_range[1]:
                continue
            for s in probe_all(node.args[0]):
                if s.strip():
                    samples.append((node.lineno, s))
        if isinstance(fn, ast.Attribute) and fn.attr == '_touch' and len(node.args) >= 2:
            for w in probe_all(node.args[1]):
                if w:
                    touches.append((node.lineno, w))

    # _touch 的条目名会拼成 `{what}: {path}`
    # [EN] The entry name of _touch gets concatenated into `{what}: {path}`
    for ln, w in touches:
        samples.append((ln, f'{w}: PROBE'))

    no_en_ok = {'=' * 46, ''}
    missed = []
    for ln, s in samples:
        if s in no_en_ok or set(s) == {'='}:
            continue
        if PI.translate_en(s):
            continue
        # 已经是双语的句子（自带英文）不需要翻译规则，例如抬头行
        # `小说世界AI模拟  /  Novel World AI Simulator`。
        # [EN] Sentences that are already bilingual (with their own English) don't need translation rules, e.g.
        # [EN] header lines
        if LATIN_WORD.search(s):
            continue
        missed.append(f'L{ln}: {s[:60]}')
    ok('A3 静态穷举：每处 say/_touch 的文案都翻得出来（含 macOS/Linux 分支）',
       not missed, f'共 {len(samples)} 句，漏 {len(missed)}：{missed[:3]}')
    REPORT['static_samples'] = len(samples)


# ══════════════════════════════════════════════════════════════
#  B. shell / .bat 脚本
# [EN] B. shell / .bat scripts
# ══════════════════════════════════════════════════════════════
def read_script(name: str, enc: str) -> str:
    return (APP_DIR / name).read_bytes().decode(enc)


_BASH_CACHE: list[str | None] = []
#: 探测 bash 的超时（秒）。
#   ⚠ **20 秒在并行回归里不够**（2026-10-07）：回归器一次拉 6 路真机脚本，
#   在 Windows 上创建进程本身就慢，`bash.exe` 冷启动 + 抢 CPU 很容易超过 20s。
#   那时 `_bash()` 返回 None → B3 那批 `bash -n` 语法检查**全红**，
#   而"串行复跑"（一个人跑、没人抢）立刻绿 —— 回归器报的
#   「并行红、串行绿 → 并行不稳」正是这么来的。
#   60 秒给足余量：正常情况 <2 秒就返回，只有真卡住才会走满。
# [EN] : probe bash timeout (seconds).
# [EN] ⚠ **20 seconds is not enough in parallel regression** (2026-10-07): the regressor launches 6
# [EN] real-machine scripts at once,
# [EN] process creation itself is slow on Windows, and `bash.exe` cold start + CPU contention easily
# [EN] exceeds 20s.
# [EN] At that time `_bash()` returns None → B3's batch of `bash -n` syntax checks all turn **red**,
# [EN] while the "serial rerun" (one person running, no contention) immediately turns green — exactly
# [EN] how the regressor's
# [EN] "parallel red, serial green → parallel unstable" came about.
# [EN] 60 seconds gives ample margin: normally it returns in <2 seconds, only a real hang will run the
# [EN] full duration.
_BASH_PROBE_TIMEOUT = 60
#: 探测失败的原因（给人看；以前是 `except: continue` 静默吞掉，
#   红了也说不清是"没装 bash"还是"超时"）。
# [EN] : the reason probe failed (for humans; previously `except: continue` silently swallowed it,
# [EN] so even when red you couldn't tell if it was "bash not installed" or "timeout").
_BASH_WHY: list[str] = []


def _bash() -> str | None:
    """找一个**真能用的** bash。

    ⚠ 不能直接用 `subprocess.run(['bash', ...])`：在本机它解析到 Windows 的
      bash（WSL 入口），输出代理警告并**恒返回非零**，会让语法检查永远假红。
      所以逐个候选试，拿一个已知正确的小脚本验证过才采用。
    
        English:
    Find a **genuinely usable** bash.
        ⚠ Cannot directly use `subprocess.run(['bash', ...])`: on this machine it resolves to Windows
          bash (the WSL entry point), prints a proxy warning and **always returns non-zero**, making the syntax check permanently falsely red.
          So try candidates one by one, and only adopt one after verifying with a known-correct small script.
    """
    if _BASH_CACHE:
        return _BASH_CACHE[0]
    import shutil
    import tempfile
    cands = [
        r'C:\Users\chao\.workbuddy\binaries\PortableGit\versions\1.2.0\bin\bash.exe',
        '/usr/bin/bash',
        shutil.which('bash'),
    ]
    probe = Path(tempfile.mkdtemp()) / 'ok.sh'
    probe.write_text('echo "ok"\n', encoding='utf-8')
    found = None
    for c in cands:
        if not c or not Path(c).exists():
            continue
        try:
            r = subprocess.run([c, '-n', str(probe)], capture_output=True,
                               text=True, timeout=_BASH_PROBE_TIMEOUT)
            if r.returncode == 0:
                found = c
                break
            _BASH_WHY.append(f'{c} → 退出码 {r.returncode}')
        except Exception as e:                               # noqa: BLE001
            # **别静默**：说不清原因的红，下次还得重新查一遍
            # [EN] **Don't be silent**: a red with unclear cause means re-investigating next time
            _BASH_WHY.append(f'{c} → {type(e).__name__}: {e}')
    if found is None:
        print(f'  [!] 没找到可用的 bash（{"; ".join(_BASH_WHY) or "候选都不存在"}）'
              f' —— 下面 shell 语法的判据会红', flush=True)
    _BASH_CACHE.append(found)
    return found


# ── B 组：**启动器**（`launchers/*.go`）与**进度窗**
#    （`tools/launcher_progress.py`）给用户看的文案，必须中英都给。
# [EN] ── Group B: **launchers** (`launchers/*.go`) and the **progress window**
# [EN] (`tools/launcher_progress.py`) user-facing text must provide both Chinese and English.
#
# ★ 2026-10-10 改判：B 组原来守的是 `setup/start/uninstall` 那 9 个 `.bat`/`.sh`/
#   `.command` —— 用户要求「删掉，只留 exe」，那 9 个已经不存在了。
#   但**守护的东西没变**：那一圈里的话都是给用户看的，漏一句英文就是
#   "英文用户看到半句中文"，静默降级、没人会来提。所以 B 组跟着搬到启动器上。
# [EN] ★ 2026-10-10 reclassification: Group B originally guarded the 9 `.bat`/`.sh`/
# [EN] `.command` files in `setup/start/uninstall` — the user requested "delete them, keep only exe",
# [EN] and those 9 no longer exist.
# [EN] But **what is guarded hasn't changed**: the text in that circle is all user-facing; missing one
# [EN] English line means
# [EN] "English users see half a Chinese sentence", a silent degradation nobody will report. So Group B
# [EN] moved along to the launchers.
#
#   ⚠ "判据失去守护对象"是这一轮最容易出的错：脚本删了、判据还在扫，
#     它会因为"文件不在"而红，或者更糟 —— 扫到空集合就**恒真**。
#     下面每一条都要求"至少检查了 N 处"，扫不到就当场红（见 B0）。
# [EN] ⚠ "criterion loses its guard target" is the most likely mistake this round: the script is
# [EN] deleted, but the criterion is still scanning,
# [EN] it will turn red because "the file is missing", or worse — scanning an empty set makes it
# [EN] **vacuously true**.
# [EN] Each item below requires "at least N places checked"; if it scans nothing it turns red on the
# [EN] spot (see B0).
LAUNCHER_DIR = APP_DIR / 'launchers'
#: 有用户可见文案的 Go 源文件。
# [EN] : Go source files with user-visible text.
#
# ★ 2026-10-10 改成**自动发现**（原来是一张写死的名单）。理由是这一轮真踩到的：
#   新加了 `dialog_stub.go`、给 `confirm()` 补了四处双语文案 —— 而写死的名单
#   里没有它/也没有 `confirm` 这类调用，于是"新增的用户可见文案"
#   **默认不受这条判据保护**。名单是会过期的，"新加一份文案"和
#   "判据自动覆盖它"必须是同一件事，否则漏译又会变成静默降级。
#   现在扫 `launchers/*.go` 全量：新文件自动进来，少扫一个都不可能。
# [EN] ★ 2026-10-10 changed to **auto-discovery** (previously it was a hardcoded list). The reason is
# [EN] what was actually hit this round:
# [EN] newly added `dialog_stub.go`, and four bilingual texts added to `confirm()` — but the hardcoded
# [EN] list
# [EN] didn't include it, nor calls like `confirm`, so "newly added user-visible text"
# [EN] is **by default not protected by this criterion**. Lists expire; "adding a new text" and
# [EN] "the criterion automatically covering it" must be the same thing, otherwise missing translations
# [EN] become silent degradation again.
# [EN] Now it scans all of `launchers/*.go`: new files come in automatically, and missing even one scan
# [EN] is impossible.
LAUNCHER_GO = tuple(sorted(p.name for p in LAUNCHER_DIR.glob('*.go')))
#: 每一组"第几个实参是中文、第几个是英文"。
# [EN] : for each group, "which positional argument is Chinese, which is English".
#:
#:   notify(中文标题, 英文标题, 中文正文, 英文正文, 是否错误)
#:   confirm(中文标题, 英文标题, 中文正文, 英文正文)   ← 判据用的替身在 dialog_stub.go
# [EN] :   notify(Chinese title, English title, Chinese body, English body, is error)
# [EN] : confirm(Chinese title, English title, Chinese body, English body) ← the stub used by the
# [EN] criterion is in dialog_stub.go
#:
#: ★ 位置本身就是"哪句是中文、哪句是英文"的声明 ——
#:   这样"漏译一半"在签名层面就写不出来（不能只给一个）。
# [EN] : ★ The position itself is the declaration of "which sentence is Chinese, which is English" —
# [EN] : this way "half-translated" cannot even be written at the signature level (you can't provide
# [EN] only one).
BI_CALLS: dict[str, tuple[int, int, int, int]] = {
    'notify': (0, 1, 2, 3),
    'confirm': (0, 1, 2, 3),
}
PROGRESS_PY = APP_DIR / 'tools' / 'launcher_progress.py'


def _go_strip_comments(src: str) -> str:
    """把 Go 源码里的 `//` 注释**按行就地抹掉**（保留行号）。

    ★ 为什么要做**行内的**剥离、而且必须**认得字符串**（2026-10-17 修）：
      · 只去整行注释是不够的 —— 本项目 Go 也有**行尾**注释，例如 `services.go`
        字段表里的 `prepLabel string //: …（bi() 拼的双语）`。行尾注释里出现 `bi(`
        会被 `_calls` 当成"一个 0 实参的调用"⇒ 判据**自己制造假红**
        （实测：B2 报 `services.go:17/18 实参 0 个（应为 2）`，而那是两句注释）。
      · 所以**不能**"看到 `//` 就切"：文案里有 `https://mirrors.aliyun.com/…`、
        `https://www.python.org/downloads/` 这种，切了会把字符串切坏 ⇒ 另一种假红。
        ⇒ 走一遍**字符级扫描**，带引号状态（`"` / `` ` `` / `'`，`"` 里认 `\\` 转义），
        只在**引号外**遇到 `//` 才截断。
    ⚠ 被抹掉的行**留空行占位**（不删行）⇒ `_calls` 报的行号就是**文件里的真行号**
      （旧版删行会让行号整体前移，报出来的 `services.go:17` 其实在文件第 78 行）。

        English:
    Blank out `//` comments **in place, line by line** (line numbers preserved).

    ★ Why inline stripping, and why it must **understand strings** (fixed 2026-10-17):
      · Whole-line stripping alone is not enough -- this project's Go also has **trailing** comments,
        e.g. the field table in `services.go`:
        `prepLabel string //: …(bi() makes it bilingual)`. A `bi(` inside a trailing comment is read
        by `_calls` as "a call with 0 arguments" ⇒ the criterion **manufactures a false red**
        (observed: B2 reported `services.go:17/18 实参 0 个（应为 2）` while those were two comments).
      · So "cut on seeing `//`" is out: the text contains `https://mirrors.aliyun.com/…`,
        `https://www.python.org/downloads/`, and cutting would corrupt the string ⇒ another false red.
        ⇒ Walk char by char with quote state (`"` / backtick / `'`, honoring `\\` escapes in `"`),
        and truncate only when `//` appears **outside** quotes.
    ⚠ Blanked lines are **kept as empty lines** (not deleted) ⇒ the line numbers reported by `_calls`
      are the **real line numbers in the file** (the old version deleted lines and shifted every number,
      so a reported `services.go:17` was really line 78).
    """
    out: list[str] = []
    for ln in src.split('\n'):
        quote = ''
        cut = len(ln)
        i = 0
        while i < len(ln):
            c = ln[i]
            if quote:
                if quote == '"' and c == '\\':
                    i += 2
                    continue
                if c == quote:
                    quote = ''
                i += 1
                continue
            if c in '"`\'':
                quote = c
                i += 1
                continue
            if c == '/' and i + 1 < len(ln) and ln[i + 1] == '/':
                cut = i
                break
            i += 1
        out.append(ln[:cut].rstrip())
    return '\n'.join(out)


def _split_args(arg_src: str) -> list[str]:
    """把一段实参表按**顶层逗号**切开（跳过字符串、括号内、反引号）。
        English:
    Split an argument list by **top-level commas** (skipping strings, inside parentheses,
    backticks).
    """
    args: list[str] = []
    cur = ''
    depth = 0
    i = 0
    quote = ''
    while i < len(arg_src):
        c = arg_src[i]
        if quote:
            if c == '\\' and quote == '"':
                cur += arg_src[i:i + 2]
                i += 2
                continue
            if c == quote:
                quote = ''
            cur += c
            i += 1
            continue
        if c in '"\u0060':
            quote = c
            cur += c
            i += 1
            continue
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        if c == ',' and depth == 0:
            args.append(cur.strip())
            cur = ''
        else:
            cur += c
        i += 1
    if cur.strip():
        args.append(cur.strip())
    return args


def _calls(src: str, name: str) -> list[tuple[int, list[str]]]:
    """找出源码里所有 `name(…)` 调用的实参表（逐层配平括号 + 跳过字符串）。

    返回 `[(行号, [实参原文, …]), …]`。
    
        English:
    Find all argument lists of `name(…)` calls in the source (balanced parentheses level by level +
    skipping strings).
        Returns `[(line_number, [argument_text, …]), …]`.
    """
    out: list[tuple[int, list[str]]] = []
    key = name + '('
    pos = 0
    while True:
        j = src.find(key, pos)
        if j < 0:
            break
        prev = src[j - 1] if j > 0 else ''
        if prev.isalnum() or prev == '_':
            pos = j + 1
            continue
        # 跳过**函数声明**（`func notify(…)`）：那里也有 `notify(`，
        # 但那是形参表不是调用点 —— 第一版没跳过，于是三条"第 5 个实参应是
        # true/false：isErr bool"的假红冒出来，说的全是函数签名本身。
        # [EN] Skip **function declarations** (`func notify(…)`): there is also `notify(` there,
        # [EN] but that's a parameter list, not a call site — the first version didn't skip it, so three false
        # [EN] reds of
        # [EN] "the 5th argument should be true/false: isErr bool" popped up, all referring to the function
        # [EN] signature itself.
        head = src[:j].rstrip()
        if head.endswith('func') and (len(head) == 4
                                      or not (head[-5].isalnum()
                                              or head[-5] == '_')):
            pos = j + 1
            continue
        p = j + len(key)
        depth = 1
        start = p
        while p < len(src) and depth > 0:
            c = src[p]
            if c == '"':
                p += 1
                while p < len(src):
                    if src[p] == '\\':
                        p += 2
                        continue
                    if src[p] == '"':
                        break
                    p += 1
            elif c in '([{':
                depth += 1
            elif c in ')]}':
                depth -= 1
                if depth == 0:
                    break
            p += 1
        out.append((src[:j].count('\n') + 1, _split_args(src[start:p])))
        pos = p + 1
    return out


def _has_cjk(s: str) -> bool:
    return bool(CJK.search(s))


#: 一个"裸标识符"（不是字面量、也不是表达式）。
# [EN] : a "bare identifier" (not a literal, not an expression).
_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
#: 表达式里引用的双语文案常量（`zhApp + " · Setup"` 这种）。
# [EN] : bilingual text constants referenced in expressions (like `zhApp + " · Setup"`).
_ZH_IDENT = re.compile(r'\bzh[A-Za-z0-9_]*')
_EN_IDENT = re.compile(r'\ben[A-Za-z0-9_]*')


def _zh_ok(a: str) -> bool:
    """这一实参确实承载"中文那一半"。

    三种都算：
      · **裸标识符**以 `zh` 开头（`zhApp`）—— 用命名承载"这是中文那份"，
        这样 `notify` 的四个实参一眼分得清谁是谁，也不必把应用名抄八遍；
      · **字面量**里含中文（`"找不到主程序：\\n" + entry`）；
      · **表达式**里引用了 zh 常量（`zhApp + " · " + name`）。

    ⚠ 裸标识符**必须**靠前缀表明身份，不能"不含中文又全是字母就放行"：
      第一版就是这么写的，于是把 `enApp` 换成 `zhApp`（英文那份给错了）
      照样绿 —— 而"哪一份给错了"正是这条判据要抓的东西。
    
        English:
    This argument indeed carries the "Chinese half".
        All three count:
          · **bare identifier** starting with `zh` (`zhApp`) -- uses naming to carry "this is the Chinese one",
            so the four arguments of `notify` are distinguishable at a glance, and there is no need to copy the app name eight times;
          · **literal** containing Chinese (`"Cannot find main program:\\n" + entry`);
          · **expression** referencing a zh constant (`zhApp + " · " + name`).
        ⚠ Bare identifiers **must** indicate their identity via prefix, cannot "if it has no Chinese and is all letters, let it pass":
          the first version was written that way, so swapping `enApp` for `zhApp` (giving the wrong English half)
          still went green -- and "which half was given wrong" is exactly what this criterion is meant to catch.
    """
    a = a.strip()
    if _IDENT.match(a):
        return a.startswith('zh')
    if _has_cjk(a):
        return True
    return bool(_ZH_IDENT.search(a))


def _en_ok(a: str) -> bool:
    """这一实参确实承载"英文那一半"：**不许有中文**，且必须看得出是英文。
        English:
    This argument indeed carries the "English half": **must not contain Chinese**, and must be
    recognizable as English.
    """
    a = a.strip()
    if _has_cjk(a):
        return False       # 这一条对所有写法都成立：英文那份里不许出现中文
        # [EN] This applies to all forms: the English one must not contain Chinese
    if _IDENT.match(a):
        return a.startswith('en')
    if _EN_IDENT.search(a):
        return True
    return bool(LATIN_WORD.search(a))


def check_launchers() -> None:
    """B 组：启动器 + 进度窗的用户可见文案。
        English:
    Group B: user-visible text of the launcher + progress window.
    """
    n_notify = 0
    n_confirm = 0
    n_bi = 0
    bad_notify: list[str] = []
    bad_confirm: list[str] = []
    bad_bi: list[str] = []

    for fname in LAUNCHER_GO:
        f = LAUNCHER_DIR / fname
        if not f.exists():
            ok(f'B0 {fname} 在（launchers/ 里）', False, '文件不在')
            continue
        src = _go_strip_comments(f.read_text(encoding='utf-8'))

        # ── notify(zhTitle, enTitle, zhBody, enBody, isErr)：**五个实参**，
        #    位置本身就是"哪句是中文、哪句是英文"的声明 ——
        #    这样"漏译一半"在签名层面就写不出来（不能只给一个）。
        # [EN] ── notify(zhTitle, enTitle, zhBody, enBody, isErr): **five arguments**,
        # [EN] the position itself is the declaration of "which sentence is Chinese, which is English" —
        # [EN] this way "half-translated" cannot even be written at the signature level (you can't provide only
        # [EN] one).
        for ln, args in _calls(src, 'notify'):
            n_notify += 1
            if len(args) != 5:
                bad_notify.append(f'{fname}:{ln} 实参 {len(args)} 个（应为 5）')
                continue
            if not _zh_ok(args[0]):
                bad_notify.append(f'{fname}:{ln} 第 1 个（中文标题）看不出中文')
            if not _en_ok(args[1]):
                bad_notify.append(f'{fname}:{ln} 第 2 个（英文标题）不对：{args[1][:40]}')
            if not _zh_ok(args[2]):
                bad_notify.append(f'{fname}:{ln} 第 3 个（中文正文）看不出中文')
            if not _en_ok(args[3]):
                bad_notify.append(f'{fname}:{ln} 第 4 个（英文正文）不对：{args[3][:40]}')
            if args[4] not in ('true', 'false'):
                bad_notify.append(f'{fname}:{ln} 第 5 个应是 true/false：{args[4][:20]}')

        # ── confirm(中文标题, 英文标题, 中文正文, 英文正文)：**四个实参**。
        #    ★ 卸载前那个确认框就是这里的文案 —— 它一度**完全不在判据视野里**
        #      （写死的名单只查 notify / bi），也就是说"框里那句英文漏了"
        #      没人会发现。而它恰恰是用户点「取消/确定」前唯一看到的东西。
        # [EN] ── confirm(Chinese title, English title, Chinese body, English body): **four arguments**.
        # [EN] ★ That confirmation dialog before uninstall is the text here — it was once **completely out of
        # [EN] the criterion's view**
        # [EN] (the hardcoded list only checked notify / bi), meaning "the English line in the dialog was
        # [EN] missing"
        # [EN] would go unnoticed. And it is precisely the only thing the user sees before clicking
        # [EN] "Cancel/OK".
        for ln, args in _calls(src, 'confirm'):
            n_confirm += 1
            if len(args) != 4:
                bad_confirm.append(f'{fname}:{ln} 实参 {len(args)} 个（应为 4）')
                continue
            if not _zh_ok(args[0]):
                bad_confirm.append(f'{fname}:{ln} 第 1 个（中文标题）看不出中文')
            if not _en_ok(args[1]):
                bad_confirm.append(f'{fname}:{ln} 第 2 个（英文标题）不对：{args[1][:40]}')
            if not _zh_ok(args[2]):
                bad_confirm.append(f'{fname}:{ln} 第 3 个（中文正文）看不出中文')
            if not _en_ok(args[3]):
                bad_confirm.append(f'{fname}:{ln} 第 4 个（英文正文）不对：{args[3][:40]}')

        # ── bi(zh, en)：进度窗里的标题/说明/步骤标签。
        # [EN] ── bi(zh, en): the title/description/step labels in the progress window.
        for ln, args in _calls(src, 'bi'):
            n_bi += 1
            if len(args) != 2:
                bad_bi.append(f'{fname}:{ln} 实参 {len(args)} 个（应为 2）')
                continue
            if not _zh_ok(args[0]):
                bad_bi.append(f'{fname}:{ln} 第 1 个看不出中文：{args[0][:40]}')
            if not _en_ok(args[1]):
                bad_bi.append(f'{fname}:{ln} 第 2 个不是干净的英文：{args[1][:40]}')

    # ★ B0：**扫到了才算数**。脚本删掉之后判据最容易出的病就是"扫了个空集合、
    #   于是恒真"——所以这里把"抽查到多少处"摆到明面上。
    # [EN] ★ B0: **only what is scanned counts**. After a script is deleted, the most likely disease of the
    # [EN] criterion is "scanned an empty set,
    # [EN] hence vacuously true" — so here the "how many places were sampled" is put out in the open.
    ok('B0 真的抽查到了启动器的双语调用点（不是扫了个空集合就恒真）',
       n_notify >= 6 and n_bi >= 5 and n_confirm >= 1,
       f'notify {n_notify} 处、confirm {n_confirm} 处、bi {n_bi} 处'
       f'（扫的是 launchers/*.go 全量 {len(LAUNCHER_GO)} 个文件）')
    ok('B1 每一条 `notify(...)` 都**中英各给一份**（标题+正文，共 4 段）'
       '—— 少给一段就写不出来，因为实参是位置对应的',
       not bad_notify, f'{len(bad_notify)} 处不合规：{bad_notify[:3]}')
    ok('B1b 每一条 `confirm(...)`（卸载前的确认框）也**中英各给一份**'
       '—— 那是用户点「取消/确定」之前唯一看到的东西',
       not bad_confirm, f'{len(bad_confirm)} 处不合规：{bad_confirm[:3]}')
    ok('B2 每一条 `bi(...)` 都是"中文 + 干净的英文"'
       '（英文那一半里**不许出现中文** —— 那正是"漏译"的样子）',
       not bad_bi, f'{len(bad_bi)} 处不合规：{bad_bi[:3]}')

    # ── B3：进度窗（tkinter）自己的文案。
    # [EN] ── B3: the progress window (tkinter)'s own text.
    if not PROGRESS_PY.exists():
        ok('B3 进度窗脚本在（tools/launcher_progress.py）', False, '文件不在')
    else:
        txt = PROGRESS_PY.read_text(encoding='utf-8')
        i = txt.find('T = {')
        j = txt.find('\n}', i)
        block = txt[i:j] if i >= 0 and j > i else ''
        n_entries = 0
        half: list[str] = []
        for line in block.split('\n'):
            m = re.match(r"^\s*'([^']+)':\s*(.+?),?\s*$", line)
            if not m:
                continue
            key, val = m.group(1), m.group(2)
            if not _has_cjk(val):
                continue
            n_entries += 1
            # 约定：`中文 / English`（与旧脚本一致 —— 同一行里两种语言都在）。
            # [EN] Convention: `Chinese / English` (consistent with the old scripts — both languages on the same
            # [EN] line).
            if ' / ' not in val or not LATIN_WORD.search(val):
                half.append(key)
        ok('B3 进度窗自己的按钮/状态文案都是"中文 / English"'
           '（用户开着窗口的那几分钟里，这些话是唯一能看的东西）',
           n_entries >= 8 and not half,
           f'查了 {n_entries} 条' + (f'，缺英文：{half}' if half else ''))

    REPORT['launchers'] = {'notify': n_notify, 'confirm': n_confirm, 'bi': n_bi,
                           'bad_notify': bad_notify, 'bad_confirm': bad_confirm,
                           'bad_bi': bad_bi}

def main() -> int:
    print('── A. 安装器本体（setup / uninstall 的输出都来自它）──')
    PI = _import_installer()
    check_runtime(PI)
    check_static(PI)

    print('\n── B. 启动器与进度窗的双语文案 ──')
    check_launchers()

    n_ok = sum(1 for i in ITEMS if i['ok'])
    REPORT['items'] = ITEMS
    REPORT['n_ok'], REPORT['n_all'] = n_ok, len(ITEMS)
    REPORT['ok'] = n_ok == len(ITEMS)
    (OUT / 'script_bilingual_report.json').write_text(
        json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n脚本双语验证：{n_ok}/{len(ITEMS)}')
    print('→', '全部通过' if REPORT['ok'] else '有失败')
    for i in ITEMS:
        if not i['ok']:
            print(f"  [FAIL] {i['name']}  {i['detail']}")
    return 0 if REPORT['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
