# -*- coding: utf-8 -*-
"""验证：说明书里**每个命令都写了参数、都给了示例**（2026-10-08）。

用户原话：

    「使用说明里的**命令** 把每个命令的**参数也加上** 并且每个命令**加上示例**」

这一支判据盯的是**说明书与源码不许各说各话**，两个方向都查：

  A. **源码里有的参数，说明书必须有一行专门讲它**
     （表格里以 `` | `--参数 `` 开头的那种行 —— 光在正文里提一嘴不算）。
     抽参数用的是 **AST 的 `add_argument`**；脚本里没 argparse 的
     （技能自带的三个小工具是手工解 `sys.argv`）才退回正则扫全文。
     ⚠ 为什么非要用 AST：`tools/platform_install.py` 里有一句
     `iconutil ... '--out', ...`（生成 .icns 时用的系统命令参数），
     正则会把 `--out` 当成"我们有这个参数"，于是逼着说明书去写一个
     **根本不存在的参数**（差一点就照它改了）。

  B. **说明书里写的参数，源码里必须真的有**（防"文档里编了一个参数出来"）。
     逐行看：这一行调用的是哪个脚本，就从**那个脚本**里找这个参数名。

  C. **每个命令都有示例**：说明书里提到某个脚本的调用行**不能只有一条**
     （只有一条 = 只写了"命令长什么样"，没写"怎么用"）。

用法：.venv\\Scripts\\python.exe tools/verify_manual_commands.py
产出：assets/screenshots/manual_commands_report.json

English:
: Verification: in the manual, **every command has its arguments written and an example given**
(2026-10-08).
: The user's exact words:
    :     "In the usage instructions, for the **commands**, **add the arguments for each command too**, and **add an example for each command**"
: This branch of the criterion watches over the fact that **the manual and the source code must
not each say their own thing**, checking in both directions:
  :   A. **Arguments present in the source code must have a dedicated line in the manual**
     :      (the kind of line in the table beginning with `` | `--参数 `` -- merely mentioning it in the body text does not count).
     :      Argument extraction uses **AST's `add_argument`**; for scripts without argparse
     :      (the three small tools bundled with the skill manually parse `sys.argv`) it falls back to regex-scanning the whole text.
     :      ⚠ Why AST is required: in `tools/platform_install.py` there is a line
     :      `iconutil ... '--out', ...` (a system command argument used when generating .icns),
     :      and a regex would treat `--out` as "we have this argument", thus forcing the manual to write an
     :      **argument that does not exist at all** (I almost changed it to match).
  :   B. **Arguments written in the manual must really exist in the source code** (to prevent "the documentation making up an argument").
     :      Look line by line: whichever script this line invokes, look for this argument name in **that script**.
  :   C. **Every command must have an example**: an invocation line mentioning a script in the manual **cannot be only one line**
     :      (only one line = it only says "what the command looks like", not "how to use it").
Usage: .venv\\Scripts\\python.exe tools/verify_manual_commands.py
Output: assets/screenshots/manual_commands_report.json
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

MANUALS = ('使用说明.md', 'User_Manual.md')

#: (脚本路径, **说明书里用它时出现的文件名**)。
#: 说明书里叫 `my_server.py` 的那个是**举例用的服务器**（并不存在这个文件）——
#: 它演示的是 `_mcpkit.py` 提供的 `--list-tools` / `--call` 这套自检机制，
#: 所以映射过去查（不这么映射的话，这一行会被当成"没有对应的源码"跳过，
#: 而"跳过"与"通过"在报告里长得一样，正是本项目最忌讳的那种判据）。
# [EN] : (script path, **the filename that appears when it is used in the manual**).
# [EN] : The one called `my_server.py` in the manual is an **example server** (this file does not
# [EN] exist) --
# [EN] : it demonstrates the `--list-tools` / `--call` self-check mechanism provided by `_mcpkit.py`,
# [EN] : so map it over to look it up (otherwise this line would be skipped as "no corresponding source
# [EN] code",
# [EN] : and "skipped" and "passed" look the same in the report, which is exactly the kind of criterion
# [EN] this project dreads most).
SCRIPTS: tuple[tuple[str, str], ...] = (
    ('main_gui.py', 'main_gui.py'),
    ('make_art.py', 'make_art.py'),
    ('skills/节气物候/scripts/jieqi.py', 'jieqi.py'),
    ('skills/路程与交通估算/scripts/travel.py', 'travel.py'),
    ('skills/姓名称谓生成/scripts/gen_names.py', 'gen_names.py'),
    ('tools/platform_install.py', 'platform_install.py'),
    ('mcp/servers/_mcpkit.py', 'my_server.py'),
    ('tools/verify_mcp_skills.py', 'verify_mcp_skills.py'),
)

#: 三个**启动器** —— `launchers/` 里用 Go 写的、交叉编译成各平台可执行文件的三个。
# [EN] : Three **launchers** -- the three in `launchers/` written in Go and cross-compiled into
# [EN] executables for each platform.
#:
#: ★ 2026-10-10 改判：这里原来写的是 `start.bat` / `setup.bat` / `uninstall.bat`
#:   （并配 `SH_PASSTHROUGH` 说"它们自己不解析参数、原样透传"）。用户要求
#:   「删掉，只留 exe」，那 9 个脚本已经不存在了 —— 判据的对象跟着换成启动器。
# [EN] : ★ 2026-10-10 reclassification: this used to say `start.bat` / `setup.bat` / `uninstall.bat`
# [EN] : (with `SH_PASSTHROUGH` saying "they do not parse arguments themselves, they pass them through
# [EN] as-is"). The user asked to
# [EN] : "delete them, keep only the exe", so those 9 scripts no longer exist -- the criterion's target
# [EN] is switched to the launchers accordingly.
#:
#: ⚠ 同一个启动器在说明书里有**两个写法**：Windows 是 `start.exe`，
#:   Linux / macOS 是 `./start`。所以"别名"是一组，两种都认。
#:   第一版只认 `.exe`，于是 Linux/macOS 那几行会被当成"没提到这个命令"
#:   而漏掉一整组检查（漏掉和通过长得一样，是本项目最忌讳的那种）。
# [EN] : ⚠ The same launcher has **two forms** in the manual: on Windows it is `start.exe`,
# [EN] :   on Linux / macOS it is `./start`. So the "alias" is a set, and both are recognized.
# [EN] : The first version only recognized `.exe`, so the Linux/macOS lines would be treated as "this
# [EN] command is not mentioned"
# [EN] : and an entire group of checks would be missed (missed and passed look the same, which is what
# [EN] this project dreads most).
LAUNCHERS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    'start': (('start.exe', './start'), ('--mock', '--reinstall')),
    'setup': (('setup.exe', './setup'), ('--dry-run', '--skip-service')),
    'uninstall': (('uninstall.exe', './uninstall'),
                  ('--dry-run', '--purge', '--yes')),
}

#: 这些参数"真认它的地方"。
# [EN] : Where these arguments are "actually recognized".
#:
#: ⚠ 不能用正则扫启动器本体（那是个二进制）—— 扫出来的东西不可信。
#:   所以显式列出**源码里的出处**，回头核"我们承诺的参数真的有人认"。
#:   · `--reinstall` / `--skip-service` → `launchers/flow.go`（启动器自己处理）
#:   · `--mock` → `main_gui.py`（启动器**原样透传**给程序的那一个）
#:   · `--dry-run` / `--purge` / `--yes` → `tools/platform_install.py`（装机脚本）
# [EN] : ⚠ You cannot scan the launcher itself with a regex (it is a binary) -- whatever you scan out
# [EN] is not trustworthy.
# [EN] : So explicitly list the **sources in the source code**, to later verify "the arguments we
# [EN] promised really are recognized by someone".
# [EN] :   · `--reinstall` / `--skip-service` -> `launchers/flow.go` (handled by the launcher itself)
# [EN] :   · `--mock` -> `main_gui.py` (the one the launcher **passes through as-is** to the program)
# [EN] :   · `--dry-run` / `--purge` / `--yes` -> `tools/platform_install.py` (the installer script)
LAUNCHER_SRC: dict[str, tuple[str, ...]] = {
    'start': ('launchers/flow.go', 'main_gui.py'),
    'setup': ('launchers/flow.go', 'tools/platform_install.py'),
    'uninstall': ('launchers/flow.go', 'tools/platform_install.py'),
}

#: 少数脚本**没有 argparse**，正则扫全文会把"它去调别人时用的参数"也算进来 ——
#: `tools/verify_mcp_skills.py` 就是这种：它自己只认 `-v/--verbose`，
#: 而正文里出现的 `--mode` / `--titles` / `--identity` / `--project-dir`
#: 是它跑 travel.py / gen_names.py / project_lore_server.py 时的**别人的**参数。
#: 所以这几个脚本的参数表**显式写死**（宁可写死，也不要让判据去逼说明书
#: 给一个本不属于它的参数配示例）。
# [EN] : A few scripts **have no argparse**, and scanning the whole text with a regex would also count
# [EN] "the arguments it uses when calling others" --
# [EN] : `tools/verify_mcp_skills.py` is one of these: it only recognizes `-v/--verbose` itself,
# [EN] : while the `--mode` / `--titles` / `--identity` / `--project-dir` appearing in its body
# [EN] : are **someone else's** arguments when it runs travel.py / gen_names.py /
# [EN] project_lore_server.py.
# [EN] : So the argument tables of these few scripts are **explicitly hardcoded** (better hardcoded
# [EN] than letting the criterion force the manual
# [EN] : to provide an example for an argument that does not belong to it).
FLAGS_OVERRIDE: dict[str, tuple[str, ...]] = {
    'tools/verify_mcp_skills.py': ('-v', '--verbose'),
}

FLAG = re.compile(r'--[a-z][a-z0-9-]*')
#: 表格行里被反引号包起来的参数。
#: ⚠ **不要求**反引号紧跟着收尾：说明书里的写法是 `--mode <方式>`、`--call <工具名> [JSON]`
#:   这种"参数 + 占位说明"的形式（第一版要求整段都是参数，于是 `--mode` 这些
#:   明明写在表里的也被判成"缺"，假红一大片）。
# [EN] : Arguments wrapped in backticks in table rows.
# [EN] : ⚠ Do **not** require the backticks to be immediately followed by the closing backtick: the [EN] manual's form is `--mode <方式>`, `--call <工具名> [JSON]`
# [EN] : this "argument + placeholder description" form (the first version required the entire span to
# [EN] be an argument, so `--mode` and the like
# [EN] : that were clearly written in the table were also judged "missing", producing a large batch of
# [EN] false reds).
ROW = re.compile(r'`(-{1,2}[a-z][a-z0-9-]*)')


def flags_of(src: str) -> set[str]:
    """脚本对外认的参数：优先 AST 的 `add_argument`，没有就退回正则。
        English:
    Parameters the script recognizes externally: prefer AST's `add_argument`, fall back to regex if
    absent.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        tree = None
    got: set[str] = set()
    if tree is not None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, 'attr', None) or getattr(fn, 'id', None)
            if name != 'add_argument' or not node.args:
                continue
            for a in node.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str) \
                        and a.value.startswith('-'):
                    got.add(a.value)
    if got:
        return got
    return set(FLAG.findall(src))


def bash_blocks(text: str) -> list[list[str]]:
    """把说明书里所有 ```bash 块取出来（逐个块返回，行已 strip）。
        English:
    Extract all ```bash blocks from the manual (returned block by block, lines already stripped).
    """
    out: list[list[str]] = []
    cur: list[str] | None = None
    for ln in text.split('\n'):
        if ln.strip().startswith('```'):
            if cur is None:
                cur = [] if ln.strip()[3:].strip() in ('bash', 'sh', 'shell') else None
                continue
            if cur is not None:
                out.append(cur)
                cur = None
            continue
        if cur is not None:
            cur.append(ln)
    return out


def main() -> int:
    checks: list[dict] = []

    def ok(name: str, cond, detail: str = '') -> None:
        checks.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:500]})

    srcs: dict[str, str] = {}
    for path, _alias in SCRIPTS:
        srcs[path] = (APP_DIR / path).read_text(encoding='utf-8')
    # 启动器参数的"出处"源码（启动器本体是二进制，扫不得）。
    # [EN] : The "source" code for launcher arguments (the launcher itself is a binary, so it cannot be
    # [EN] scanned).
    launcher_srcs: dict[str, str] = {}
    for key, paths in LAUNCHER_SRC.items():
        launcher_srcs[key] = ''.join(
            (APP_DIR / p).read_text(encoding='utf-8', errors='replace')
            if (APP_DIR / p).exists() else '' for p in paths)

    flagof: dict[str, set[str]] = {}
    for p, t in srcs.items():
        ov = FLAGS_OVERRIDE.get(p)
        flagof[p] = set(ov) if ov else flags_of(t)

    for manual in MANUALS:
        mp = APP_DIR / manual
        text = mp.read_text(encoding='utf-8')
        rows = set()
        for ln in text.split('\n'):
            if ln.strip().startswith('|'):
                rows.update(ROW.findall(ln))
        blocks = bash_blocks(text)

        # ── A 源码有的参数 → 说明书必须有专门的一行 ──
        # [EN] : ── A Arguments present in the source -> the manual must have a dedicated line ──
        for path, alias in SCRIPTS:
            miss = sorted(f for f in flagof[path] if f not in rows)
            ok(f'A 「{alias}」源码里的参数，说明书都有一行专门讲',
               not miss,
               f'{manual}：缺 {miss}' if miss else f'{len(flagof[path])} 个参数都在')
        for key, (aliases, want) in LAUNCHERS.items():
            # ① 我们列的那几个参数，**真有人在认**（防我们自己编一个参数出来）。
            #    · 启动器自己处理的（`--reinstall` / `--skip-service`）在 `launchers/`；
            #    · `--mock` 是**透传**给 `main_gui.py` 的，所以要去那儿找；
            #    · `--dry-run` / `--purge` / `--yes` 真认它的是 `platform_install.py`。
            # [EN] : ① The few arguments we listed, **someone really recognizes them** (to prevent us from making
            # [EN] up an argument ourselves).
            # [EN] : · Those handled by the launcher itself (`--reinstall` / `--skip-service`) are in `launchers/`;
            # [EN] : · `--mock` is **passed through** to `main_gui.py`, so you have to look for it there;
            # [EN] : · `--dry-run` / `--purge` / `--yes` are actually recognized by `platform_install.py`.
            base = launcher_srcs[key]
            ghost = [f for f in want if f not in base]
            # ② 每一个都要有专门的一行（表格里反引号包起来的，光正文提一嘴不算）
            # [EN] : ② Each one must have a dedicated line (the backtick-wrapped ones in the table; merely
            # [EN] mentioning it in the body text does not count)
            miss = sorted(f for f in want if f not in rows)
            ok(f'A 「{aliases[0]} / {aliases[1]}」的参数，说明书都有一行专门讲',
               not miss and not ghost,
               f'{manual}：缺 {miss}｜源码里找不到 {ghost}')

        # ── B 说明书写的参数 → 源码里必须真的有 ──
        # [EN] : ── B Arguments written in the manual -> they must really exist in the source code ──
        invented: list[str] = []
        for blk in blocks:
            for ln in blk:
                line = ln.strip()
                if not line or line.startswith('#'):
                    continue
                for path, alias in SCRIPTS:
                    if alias not in line:
                        continue
                    for f in FLAG.findall(line):
                        # ⚠ 用**去掉横杠的名字**去找：`travel.py` 的
                        #   `--mountain` / `--escort` 是从 `LOSS_NOTE` 的键
                        #   动态拼出来的，源码里没有字面量 `--mountain`。
                        # [EN] : ⚠ Look them up by the **name with the dashes removed**: in `travel.py`,
                        # [EN] : `--mountain` / `--escort` are dynamically assembled from the keys of `LOSS_NOTE`,
                        # [EN] : so the source code has no literal `--mountain`.
                        if f.lstrip('-') not in srcs[path]:
                            invented.append(f'{alias} {f}  ← 「{line[:52]}」')
                    break
                else:
                    for key, (aliases, want) in LAUNCHERS.items():
                        if not any(a in line for a in aliases):
                            continue
                        # 启动器透传给程序的参数（`--mock` 走 `main_gui.py`）也算数。
                        # [EN] : Arguments the launcher passes through to the program (`--mock` goes through `main_gui.py`)
                        # [EN] also count.
                        allow = set(want) | flagof.get('main_gui.py', set())
                        for f in FLAG.findall(line):
                            # `--reinstall` 只在自己那一行出现才算数 —— 这条留白
                            # 与旧脚本一致：说明书里写 `start.exe --mock --reinstall`
                            # 是**对的**（2026-10-10 起放哪个位置都生效）。
                            # [EN] : `--reinstall` only counts if it appears on its own line -- this blank
                            # [EN] : is consistent with the old scripts: writing `start.exe --mock --reinstall` in the manual
                            # [EN] : is **correct** (as of 2026-10-10, any position takes effect).
                            if f not in allow:
                                invented.append(f'{aliases[0]} {f}  ← 「{line[:52]}」')
                        break
        ok('B 说明书里写的参数，源码里都真的有（防文档编参数）', not invented,
           '；'.join(invented[:4]))

        # ── C 每个命令都要有示例，而且**表里的每个参数都要在示例里露过面** ──
        # 光"列过参数表"不算给了示例：用户要的是**照着抄就能跑**的一行。
        # 所以这条判的是"这个参数在**某条真的调用行**里出现过"。
        # [EN] : ── C Every command must have an example, and **every argument in the table must appear in an
        # [EN] example** ──
        # [EN] : Merely "listing an argument table" does not count as giving an example: what the user wants is
        # [EN] a line they can **copy and run**.
        # [EN] : So this criterion judges whether "this argument appears in **some actual invocation line**".
        thin: list[str] = []
        for path, alias in SCRIPTS:
            lines = [ln.strip() for blk in blocks for ln in blk
                     if alias in ln and not ln.strip().startswith('#')]
            if not lines:
                thin.append(f'{alias} 一条调用行都没有')
                continue
            for f in sorted(flagof[path]):
                if not any(f in ln for ln in lines):
                    thin.append(f'{alias} 的 {f} 没有示例')
        for key, (aliases, want) in LAUNCHERS.items():
            lines = [ln.strip() for blk in blocks for ln in blk
                     if any(a in ln for a in aliases)
                     and not ln.strip().startswith('#')]
            if not lines:
                thin.append(f'{aliases[0]} 一条调用行都没有')
                continue
            for f in want:
                if not any(f in ln for ln in lines):
                    thin.append(f'{aliases[0]} 的 {f} 没有示例')
        ok('C 每个命令都有示例，且**每个参数都在示例里露过面**'
           '（只写"命令长什么样"不算示例）', not thin, '；'.join(thin[:5]))

    bad = [c for c in checks if not c['ok']]
    report = {'ok': not bad, 'checks': checks,
              'failed': [c['name'] for c in bad]}
    (OUT / 'manual_commands_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\n说明书命令验证：{len(checks) - len(bad)}/{len(checks)}')
    for c in bad:
        print('  ✗', c['name'], '|', c['detail'])
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
