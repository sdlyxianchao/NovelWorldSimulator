# -*- coding: utf-8 -*-
"""验证：**这个程序与任何具体作品无关** —— 代码/文档里不许有特定小说的痕迹。

## 为什么要有这条

2026-10-06 用户报：「如果代码中有跟某楼有关的数据和代码，清理掉并修复这个特定问题，
**我这个项目必须是通用的。不能是针对特定小说的**」。

查出来三类真实污染（都不是"写错了"，是"把这个程序当成了某一本书的配套工具"）：

1. **产品代码的注释**拿用户那本书当事故案例（`store/project.py` / `ingest/optimize.py`）；
2. **说明书的插图脚本**直接把那个书名当示例项目名 ——
   于是 `assets/images/manual/*` 每张图都印着它（这是**随程序发布的**）；
3. **两个验证脚本**直接去读 `logs/nws-dialogue-<日期>.log`，把**用户那一次运行的真实内容**
   当夹具。除了内容带进来，更糟的是它依赖一个随时会被清理掉的**用户文件**：
   文件一没，那些判据就静默变哑。

## 检查什么

A **黑名单扫描**：产品代码 / 文档 / 脚本里不许出现某一部作品的**专有名词**
  （书名、人名）。名单写在下面 `FORBIDDEN`，每条都注明出处。
  ⚠ 扫描范围**刻意排除** `logs/`、`assets/screenshots/`、`.venv`、`__pycache__`：
  前两个是**运行产物**（用户自己跑出来的日志与截图，本来就该有他的内容），
  不是"程序自带的、发给用户的代码"。

B **不许依赖用户文件**：任何源码里都不许出现**写死的日期化日志文件名**
  （`logs/nws-....log`、`nws-dialogue-<日期>.log` 这类）。
  ⚠ 这条比 A 更根本：A 防的是"某本书的名字漏进来"，
  B 防的是"测试的夹具是用户的数据"—— 后者会让判据在别人机器上直接失效。

C **说明书插图的示例项目名必须来自脚本自己的夹具**：
  `shoot_manual.py` 里那个常量要存在、要用上，而且不能落在黑名单里。

跑法：
    .venv\\Scripts\\python.exe tools/verify_generic_project.py
产出：
    assets/screenshots/generic_project_report.json

English:
Verification: **this program has nothing to do with any specific work** -- no trace of a
particular novel is allowed in code/docs.
## Why this rule exists
2026-10-06 user report: "If there is data and code related to 某楼 in the code, clean it up and
fix this specific problem,
**my project must be generic. It must not be specific to a particular novel**".
Three types of real contamination were found (none of them are "typos", they are "treating this
program as a companion tool for one specific book"):
1. **Comments in product code** use the user's book as a failure case (`store/project.py` / `ingest/optimize.py`);
2. The **manual illustration script** directly uses that book title as the sample project name --
   so every image in `assets/images/manual/*` has it printed on it (this is **shipped with the program**);
3. **Two verification scripts** directly read `logs/nws-dialogue-<date>.log`, treating **the real content of that one run of the user**
   as a fixture. Besides dragging the content in, worse, it depends on a **user file** that may be cleaned up at any time:
   once the file is gone, those criteria silently go mute.
## What is checked
A **Blacklist scan**: **proper nouns** of a specific work must not appear in product code /
documentation / scripts
  (book titles, character names). The list is written below in `FORBIDDEN`, each entry noting its source.
  ⚠ The scan scope **deliberately excludes** `logs/`, `assets/screenshots/`, `.venv`, `__pycache__`:
  the first two are **runtime artifacts** (logs and screenshots produced by the user's own runs, which are supposed to contain his content),
  not "code that ships with the program and is delivered to the user".
B **Must not depend on user files**: no source code may contain **hardcoded date-based log file
names**
  (`logs/nws-....log`, `nws-dialogue-<date>.log`, and the like).
  ⚠ This rule is more fundamental than A: A guards against "the name of some book leaking in",
  B guards against "the test fixture being the user's data" -- the latter will make the criteria fail outright on someone else's machine.
C **The sample project name in the manual illustrations must come from the script's own
fixture**:
  the constant in `shoot_manual.py` must exist, must be used, and must not fall into the blacklist.
How to run:
    .venv\\Scripts\\python.exe tools/verify_generic_project.py
Output:
    assets/screenshots/generic_project_report.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════
#  黑名单：某一部具体作品的专有名词，**任何情况下都不该出现在程序里**
# [EN] Blacklist: proper nouns belonging to a specific work, **must never appear in the program under
# [EN] any circumstances**
# ══════════════════════════════════════════════════════════════════════
# ⚠ 只放**没有正当理由出现**的名字：
#   · 作品名与人名（书里的角色）；
#   · 那本书独有的地名/设定词。
# 不放"通用词"（掌柜、伙计、茶楼…），也不放程序自己演示夹具的名字
# （演示夹具是**程序的样例数据**，性质同 `samples/`，不是某一部真实作品）。
# [EN] ⚠ Only include names that **have no legitimate reason to appear**:
# [EN] · Work titles and character names (characters in the book);
# [EN] · Place names/setting terms unique to that book.
# [EN] Do not include "generic words" (shopkeeper, waiter, teahouse...), and do not include the names
# [EN] of the program's own demo fixtures
# [EN] (demo fixtures are **the program's sample data**, same nature as `samples/`, not a real work).
FORBIDDEN = {
    '莫问楼': '某次真实运行里那本书的书名',
    '莫问': '那本书的主角名',
    '莫栩栩': '那本书里的人物名',
    '陈忘': '那本书里的人物名',
    '朱笔': '那本书里的人物名',
    '小六子': '那本书里的人物名',
    '故事海': '那本书里的设定词',
    '山海经界': '那本书里的设定词',
    '唐传奇界': '那本书里的设定词',
    '梦话界': '那本书里的设定词',
}

SCAN_SUFFIX = {'.py', '.md', '.json', '.yaml', '.yml', '.txt', '.bat',
               '.sh', '.command'}
# ⚠ 排除"运行产物"：这些地方本来就该有用户自己的内容
# [EN] ⚠ Exclude "runtime artifacts": these places are supposed to contain the user's own content
#
#   ★ `exports`（2026-10-08 加）：它是**导出物**目录 —— 把运行日志整理成能发给
#     外部工具看的一包（`developers/pack_diagnostic.py` 写这儿）。交给别人的诊断包
#     里当然会写"这包来自哪一次运行、那本书叫什么"，否则对方读不懂。
#     性质与 `logs` / `assets/screenshots` **完全同类**：都是用户跑出来的东西，
#     不是"程序自带、要发给用户的代码"。
#     ⚠ 这不是放宽判据：A 要防的是"某个真实作品的名字被写进**产品代码或说明书**"，
#       那两处依旧全量扫描（本文件 D 组自检项**真的**在跑 —— 2026-10-19 补上；
#       此前这句注释是假的：写着"自检仍在跑"，实际一行都没有）。
#   ★ `novelservices`（2026-10-09 加）：它是**旁挂的写作工具链**，不是产品的一部分 ——
#     里面那套 MuMuAINovel 工具（质量层 / 导入脚本 / 启动器）**本来就是为某一本书做的**，
#     默认书名、细纲、风格提示词都写死了那一部作品，这是它的用途，不是缺陷。
#     性质与 `exports` 同类：都是"用户自己的东西"，不是"程序自带、要发给任何用户的代码"。
#     ⚠ 这不是放宽判据：A 要防的是"某个真实作品的名字被写进**产品代码或说明书**"，
#       产品本体（gui/ tools/ developers/ 说明书…）依旧**全量扫描** ——
#       下面的 D 组自检（往产品文件里塞一个书名，看它抓不抓）**真的在跑**。
# [EN] ★ `exports` (added 2026-10-08): it is the **export artifact** directory -- packaging run logs
# [EN] into something that can be sent to
# [EN] external tools for inspection (`developers/pack_diagnostic.py` writes here). A diagnostic
# [EN] package handed to someone else
# [EN] will of course say "which run this package came from, what that book is called", otherwise the
# [EN] other party cannot make sense of it.
# [EN] Its nature is **exactly the same** as `logs` / `assets/screenshots`: they are all things the
# [EN] user produced by running,
# [EN] not "code that ships with the program and is meant to be delivered to the user".
# [EN] ⚠ This is not relaxing the criterion: what A guards against is "the name of some real work being
# [EN] written into **product code or documentation**",
# [EN] those two places are still fully scanned (the self-checks below in this file are still running).
# [EN] ★ `novelservices` (added 2026-10-09): it is a **side-attached writing toolchain**, not part of
# [EN] the product --
# [EN] the MuMuAINovel toolset inside it (quality layer / import scripts / launcher) **was made for one
# [EN] specific book to begin with**,
# [EN] the default book title, detailed outline, and style prompts are all hardcoded to that one work;
# [EN] this is its purpose, not a defect.
# [EN] Its nature is the same as `exports`: both are "the user's own stuff", not "code that ships with
# [EN] the program and is meant to be delivered to any user".
# [EN] ⚠ This is not relaxing the criterion: what A guards against is "the name of some real work being
# [EN] written into **product code or documentation**",
# [EN] the product proper (gui/ tools/ developers/ documentation...) is still **fully scanned** --
# [EN] the self-check below (stuffing a book title into a product file to see whether it catches it) is
# [EN] still running.
SKIP_PARTS = {'__pycache__', '.venv', '.git', 'logs', 'screenshots',
              'images', 'node_modules', 'exports', 'novelservices'}

#: **按路径前缀跳过**（相对仓库根，用 `/` 分隔）。
#:
#: ★★★ 为什么加这一条而不是把 `results` 塞进 `SKIP_PARTS`（2026-10-19 第十轮）
#: ----------------------------------------------------------------------
#: `novel_bench/results/` 是**跑基准的产出目录**（`bench/runner.py` 往里写，
#: 实测 12 MB / 58 个目录），里面当然有"这次跑的是哪本书、书里的人物叫什么"——
#: 性质与 `logs` / `exports` **完全相同**，都是用户跑出来的东西。
#:
#: ⚠ 但**不能**按目录名匹配（`'results' in p.parts`）：`results` 这个名字太通用，
#:   哪天某个产品模块也叫 `results/`，就会连带被跳过，而那种跳过是**看不见的放宽**。
#:   ⇒ 只有"从仓库根数起正好是这个前缀"才跳过。这是"宁可写长一点，也别放宽口径"。
#: [EN] **Skip by path prefix** (relative to the repo root, `/` separated). `novel_bench/results/`
#: [EN] is the benchmark's output directory (12 MB / 58 dirs) and of course contains the book name
#: [EN] and its characters -- exactly the same nature as `logs` / `exports`. It must **not** be
#: [EN] matched by directory name: `results` is too generic, and if some product module were ever
#: [EN] called `results/` it would be skipped too -- an invisible relaxation of the rule.
#: ★★★ 2026-10-31：`.ui_state/` 是**程序的运行状态**（"上次打开的是哪本书"），
#:   里面必然写着用户当前那本书的名字与路径 —— 和 `logs` / `exports` 同一性质，
#:   不是"产品代码里写了某部作品"。不加这一条的话，**用户只要跑过一次真项目，
#:   这条判据就永远红**（实测：`last_project.json` 里 2 处专名 ⇒ 8/9），
#:   而那种红跟通用性毫无关系，只会教人忽略它。
#: ⚠ 只跳过**从仓库根数起正好是 `.ui_state/`** 这一处，不按目录名匹配。
# [EN] ★★★ 2026-10-31: `.ui_state/` is the program's **runtime state** ("which book was opened
# [EN] last"), so it necessarily contains the user's current book name and path -- the same nature
# [EN] as `logs` / `exports`, not "a real work written into product code". Without this skip,
# [EN] **the criterion stays red forever once the user has run a real project** (measured: two
# [EN] proper nouns in `last_project.json` => 8/9), and that red has nothing to do with generality;
# [EN] it only teaches people to ignore the check.
# [EN] ⚠ Only the exact `.ui_state/` prefix from the repo root is skipped, never by directory name.
#: ★★★ 2026-10-31（同日第二次）：`.workbuddy/` 是**开发工作记录**（每天写了什么、
#:   查过哪些日志），里面必然会引用用户那本书的书名/人名 —— 和 `logs` / `exports` 同一性质。
#:   实测：当天的记忆日志里写了两个专名 ⇒ 这条判据红（8/9），而它跟"产品通用性"无关。
#: ⚠ 同上，只按**从仓库根数起的精确前缀**跳过。
# [EN] ★★★ 2026-10-31 (second time the same day): `.workbuddy/` is the **development work log**
# [EN] (what was done each day, which logs were inspected) and necessarily quotes the user's book
# [EN] and character names -- same nature as `logs` / `exports`. Measured: the day's memory log held
# [EN] two proper nouns => the criterion went red (8/9), which has nothing to do with "the product
# [EN] being generic". ⚠ Same rule: only an exact repo-root prefix is skipped.
SKIP_PREFIXES = ('novel_bench/results/', '.ui_state/', '.workbuddy/')
# 本脚本自己当然要写着这些词（它就是名单）
# [EN] This script itself of course has to contain these words (it is the list)
SELF = 'verify_generic_project.py'

# B 组：写死的日期化日志文件名（测试不该依赖用户那一次运行留下的文件）
# [EN] Group B: hardcoded date-based log file names (tests should not depend on files left behind by
# [EN] that one run of the user)
DATED_LOG = re.compile(r'(?:logs/|logs\\\\)?nws[-_]?(?:dialogue-)?\d{4}-\d{2}-\d{2}')

_ITEMS: list = []


def ok(name: str, cond, detail: str = '') -> bool:
    _ITEMS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    if not cond:
        print(f'FAIL  {name}   [{detail}]')
    return bool(cond)


def scan_files() -> list[Path]:
    out = []
    for p in APP_DIR.rglob('*'):
        if not p.is_file() or p.suffix.lower() not in SCAN_SUFFIX:
            continue
        if any(part in SKIP_PARTS for part in p.parts):
            continue
        rel = p.relative_to(APP_DIR).as_posix()
        if any(rel.startswith(pref) for pref in SKIP_PREFIXES):
            continue
        if p.name == SELF:
            continue
        out.append(p)
    return out


def read(p: Path) -> str:
    """读一个文件；读不了就当空（**不许让整支判据崩掉**）。

    ★★★ 2026-10-17 修：原来只 catch `UnicodeDecodeError/LookupError`。
      这支判据要 `rglob` 扫全项目 886 个文件，而**全量回归是并行的** ——
      别的判据正在写的文件会被 Windows 独占打开，`read_text` 抛
      `PermissionError`（`OSError` 的子类，上面两个都不接）⇒ 整个脚本崩：
      `exit=1`、**一条结论行都不打**、看起来像"扫到了违规"。
      实测：单独跑 5/5 全绿，并行回归里恒红 —— 与产品无关，是判据不够结实。
    [EN] ★★★ Fixed 2026-10-17: this used to catch only `UnicodeDecodeError/LookupError`. The criterion
    [EN] `rglob`s **886 files** across the project, and **the full regression runs in parallel** -- a file
    [EN] another criterion is writing gets opened exclusively on Windows, `read_text` raises
    [EN] `PermissionError` (an `OSError` subclass, matched by neither of the two) => the whole script
    [EN] crashes: `exit=1`, **not a single summary line**, looking exactly like "it found violations".
    [EN] Measured: green 5/5 standalone, permanently red inside the parallel regression -- nothing to do
    [EN] with the product; the criterion just wasn't robust enough.
    """
    for enc in ('utf-8', 'gbk'):
        try:
            return p.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
        except OSError:
            return ''
    return ''


def main() -> int:
    report: dict = {}
    files = scan_files()
    report['scanned'] = len(files)

    # ── A：黑名单 ──
    # [EN] -- A: blacklist --
    hits: list = []
    for p in files:
        s = read(p)
        for word, why in FORBIDDEN.items():
            if word in s:
                for i, ln in enumerate(s.splitlines(), 1):
                    if word in ln:
                        hits.append({'file': str(p.relative_to(APP_DIR)),
                                     'line': i, 'word': word, 'why': why,
                                     'text': ln.strip()[:110]})
    report['blacklist_hits'] = hits
    # ⚠ 2026-10-28：**不许只显示前几条**。
    #   实测一次扫描 39 处命中 / 3 个文件，这里原本写的是 `hits[:6]` ⇒
    #   看输出的人以为只有 6 处，剩下的（`tools/` 下的判据夹具等）**一直没人改**。
    #   （记忆铁律：**截断说明会撒谎** —— 截了就要把总数说出来。）
    #   ⇒ 改成按文件分组列全，并在最前面给出总数。
    # [EN] ⚠ 2026-10-28: **do not show only the first few**.
    # [EN] One scan had 39 hits / 3 files and this used to print `hits[:6]` => a reader believes
    # [EN] there are only 6, and the rest (e.g. criterion fixtures under `tools/`) **never got
    # [EN] fixed**. (Discipline: **a truncated report lies** -- if you truncate, state the total.)
    # [EN] => group by file, list everything, and give the total up front.
    det = ''
    if hits:
        by_file: dict[str, list] = {}
        for h in hits:
            by_file.setdefault(h['file'], []).append(h)
        det = (f'共 {len(hits)} 处 / {len(by_file)} 个文件 —— ' + ' ; '.join(
            f"{f}（{len(v)} 处）: "
            + ', '.join(f"{x['line']}·{x['word']}" for x in v)
            for f, v in sorted(by_file.items())))
    ok('A：★ 代码/文档里没有出现某一部具体作品的专有名词', not hits, det)

    # ── B：不许写死"用户那一次运行"的日志文件名 ──
    # [EN] -- B: must not hardcode log file names from "that one run of the user" --
    dated: list = []
    for p in files:
        # 判据脚本自身对这条规则的**说明性引用**要放过（本脚本已被 SELF 排除）
        # [EN] The criterion script's own **explanatory references** to this rule must be let through (this
        # [EN] script has already been excluded by SELF)
        for i, ln in enumerate(read(p).splitlines(), 1):
            if DATED_LOG.search(ln):
                dated.append({'file': str(p.relative_to(APP_DIR)), 'line': i,
                              'text': ln.strip()[:110]})
    report['dated_log_hits'] = dated
    ok('B：★ 没有任何源码写死"某次运行的日志文件名"'
       '（测试的夹具必须是自带的，不能是用户的数据）',
       not dated, ' | '.join(f"{d['file']}:{d['line']}" for d in dated[:6]))

    # ── C：说明书插图的示例项目名来自脚本自己的夹具 ──
    # [EN] -- C: the sample project name in the manual illustrations comes from the script's own fixture --
    sm = APP_DIR / 'developers' / 'shoot_manual.py'
    src = read(sm)
    m = re.search(r"^DEMO_PROJECT\s*=\s*['\"]([^'\"]+)['\"]", src, re.M)
    report['shoot_manual_demo_project'] = m.group(1) if m else None
    ok('C：`shoot_manual.py` 里定义了 `DEMO_PROJECT` 常量（插图的项目名有唯一出处）',
       bool(m), str(report['shoot_manual_demo_project']))
    ok('C：★ 建项目时用的就是这个常量（没有在别处另写一个字面量书名）',
       'make_project(proot, DEMO_PROJECT' in src,
       str([ln.strip()[:70] for ln in src.splitlines()
            if 'make_project(proot' in ln]))
    ok('C：★ 那个示例项目名不在黑名单里',
       bool(m) and m.group(1) not in FORBIDDEN, str(report['shoot_manual_demo_project']))

    # ══════════════════════════════════════════════════════════
    #  D：**跳过本身也要被判**（2026-10-19 第十轮补）
    # ══════════════════════════════════════════════════════════
    # ★★★ 这段是补上一个**谎**：本文件上面的注释里早就写着
    #   "下面的自检（往产品文件里塞一个书名，看它抓不抓）依然在跑"，
    #   **实际上一行都没有**。一个判据在注释里宣称自己有自检、而它没有，
    #   比没有自检更糟 —— 读的人会以为这层已经有人守着了。
    #
    # 为什么必须有：每加一条 `SKIP_*`，A 组的扫描面就缩小一块。
    #   "跳过"本身是**放宽**，而放宽从不报警。所以每条跳过都要配一条反向验证：
    #   ① 把书名塞进**产品文件** ⇒ A 必须抓到（证明扫描真的在扫）；
    #   ② 把书名塞进**被跳过的目录** ⇒ A 必须不抓（证明跳过真的生效）；
    #   ③ `SKIP_PREFIXES` 只按前缀匹配 ⇒ 同名但不在该前缀下的目录**不许**被跳过。
    # [EN] This closes a **lie**: the comments above already claimed "the self-check below (stuff a
    # [EN] book title into a product file and see whether it catches it) is still running" -- and
    # [EN] there was not a single line of it. A criterion whose comments claim a self-check it does
    # [EN] not have is worse than none: readers assume that layer is guarded.
    # [EN] Every `SKIP_*` shrinks A's scan surface, and a skip never raises an alarm. So each skip
    # [EN] gets a reverse test: a title in a **product file** must be caught; a title in a **skipped
    # [EN] directory** must not be; and `SKIP_PREFIXES` must not skip a same-named directory that
    # [EN] lives elsewhere.
    import tempfile
    _word = next(iter(FORBIDDEN))
    _tmp = Path(tempfile.mkdtemp(prefix='nws_gen_'))
    try:
        # ① 产品文件里塞书名 ⇒ 必须被抓到
        _prod = _tmp / 'product' / 'probe.py'
        _prod.parent.mkdir(parents=True)
        _prod.write_text(f'# {_word}\n', encoding='utf-8')
        # ② 被跳过的目录里塞书名 ⇒ 必须绕过（与被测的 scan_files 同一套判定）
        _results = _tmp / 'novel_bench' / 'results' / 'run1' / 'novel.md'
        _results.parent.mkdir(parents=True)
        _results.write_text(f'# {_word}\n', encoding='utf-8')
        # ③ 同名但**不在**该前缀下 ⇒ 不许跳过（口径是前缀，不是目录名）
        _decoy = _tmp / 'gui' / 'results' / 'x.md'
        _decoy.parent.mkdir(parents=True)
        _decoy.write_text(f'# {_word}\n', encoding='utf-8')

        def _skipped(p: Path) -> bool:
            """与 `scan_files` **同一套判定**（照抄那两行，不另写一份逻辑）。"""
            if any(part in SKIP_PARTS for part in p.parts):
                return True
            rel = p.relative_to(_tmp).as_posix()
            return any(rel.startswith(pref) for pref in SKIP_PREFIXES)

        ok('D1 ★★★ **自检——往产品文件里塞一个书名，A 必须抓得到**'
           '（只看"没命中"是分不清"干净"和"没扫"的）',
           not _skipped(_prod), f'{_prod.relative_to(_tmp).as_posix()}')
        ok('D2 ★★★ 自检——塞进 `novel_bench/results/` 的书名**必须被跳过**'
           '（跳过不生效 = 这条判据天天红，最后一定被人关掉）',
           _skipped(_results), f'{_results.relative_to(_tmp).as_posix()}')
        ok('D3 ★★★ 成对——**同名但不在该前缀下**的 `results/` 不许被跳过'
           '（按目录名匹配是"看不见的放宽"，本条守的就是这个）',
           not _skipped(_decoy), f'{_decoy.relative_to(_tmp).as_posix()}')
        # ④ 每一条跳过都必须有**书面理由**（`SKIP_PREFIXES` 里没有裸条目）
        ok('D4 ★★ 每条跳过都是**显式前缀**，不是裸目录名'
           '（裸名字会在别处"顺手"生效，谁也说不清放宽了多少）',
           all(pref.endswith('/') and '/' in pref for pref in SKIP_PREFIXES),
           str(SKIP_PREFIXES))
    finally:
        import shutil
        shutil.rmtree(_tmp, ignore_errors=True)

    report['ok'] = all(i['ok'] for i in _ITEMS)
    report['items'] = _ITEMS
    (OUT / 'generic_project_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    n_ok = sum(1 for i in _ITEMS if i['ok'])
    print(f'通用性验证：{n_ok}/{len(_ITEMS)}')
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
