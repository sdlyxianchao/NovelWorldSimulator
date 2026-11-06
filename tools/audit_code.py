# -*- coding: utf-8 -*-
"""审计：**一次性扫出那几类"每次改完都会漏"的东西**。

为什么要有它（2026-10-18 用户的原话）
------------------------------------
「然后你再次全部审查一下代码 我感觉还是每一次都会查到错误」。

这句话是对的，而且原因不在"改得不仔细"，在**审查方式**：以前每轮都是
"顺着刚改的那几行看一遍"，于是只能发现**刚碰到的那类**错误；
换个位置、换个类别的错一个也发现不了。要换方法 —— **按"错误类别"扫全库**，
而不是按"改动的行"扫。

这里扫六类（每一类都是本项目真实踩过的，不是假想）：

  A. **假旋钮**：`config.py` 的 SPEC 里登记了，但**没有任何代码读它** ——
     用户在界面上调它，什么都不会发生，而且界面一切正常。
  B. **静默降级**：`except …: pass` / `except …: return`（不 log、不 warn）——
     本项目明令禁止（"静默降级是明令禁止的"），但一定会漏。
  C. **两份实现**：同名函数在多个文件里各写一遍（"同一件事两处实现是万恶之源"）。
  D. **被写死的数字**：同一个魔法数在多处出现（改一处漏一处）。
  E. **参数加了没传**：函数签名里有这个参数，但调用点一个都没传（半截改动）。
  F. **登记错组**：回归里把真机判据排进 LOGIC、纯逻辑判据排进 GUI。

⚠ 这一支**不是判据**（不进 `run_all_verifications` 的绿/红）—— 它会报出
  "合理的历史遗留"，当判据只会逼人去改注释。它是**给人看的体检报告**。
  真正要守的那几条，各自已经在 `verify_*.py` 里。

跑法：`.venv/Scripts/python.exe tools/audit_code.py`
      `.venv/Scripts/python.exe tools/audit_code.py --cat A,B`   # 只扫两类
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

#: 扫哪些目录（`developers/` 是我们自己的脚本，也要扫；`novelservices/` 是外部项目，不扫）
#: ★★★ 2026-10-18：第一版只写了 15 个目录，漏了 `booklab/` `compliance/` `research/`
#:   `skills/` `mcp/` `craft/` `polish/` `style/` ⇒ A 类当场报出 10 条"假旋钮"，
#:   其中一大半是**误报**（`BOOKLAB_MAX_BATCHES` 在 `booklab/analyzer.py` 里读得好好的）。
#:   ⇒ 目录清单要按 `ls -d */` 逐个核过，不许凭印象列。
# [EN] ★★★ 2026-10-18: the first version listed only 15 directories and missed `booklab/`,
# [EN] `compliance/`, `research/`, `skills/`, `mcp/`, `craft/`, `polish/`, `style/` => category A
# [EN] reported 10 "fake knobs", most of them **false positives** (BOOKLAB_MAX_BATCHES is read fine
# [EN] in `booklab/analyzer.py`). The list must be verified against `ls -d */`, never from memory.
TREES = ('sim', 'crew', 'agent', 'display', 'world', 'director', 'store', 'util',
         'ingest', 'export', 'image_gen', 'llm', 'gui', 'tools', 'developers',
         'novel_bench', 'booklab', 'compliance', 'research', 'skills', 'mcp',
         'craft', 'polish', 'style', 'actors', 'agents', 'refs')
#: 不扫的目录：外部项目、构建产物、用户数据、纯资源
# [EN] Not scanned: external projects, build outputs, user data, pure assets
SKIP_DIRS = {'__pycache__', '.venv', 'node_modules', 'bak-bilingual',
             'novelservices', 'packages', 'assets', 'logs', 'Projects',
             'exports', 'generated-images', 'logo_drafts', 'samples',
             'launchers'}
# ⚠ `refs/` **不能整目录排**：它是"参考资料"目录，但里面有真代码
#   （`refs/indexer.py` 读 `REFERENCE_DIR`）⇒ 排掉之后那个键就成"没人读的假旋钮"。
#   `py_files()` 只收 `.py`，所以 refs 里的 md/txt 本来就不会进来。
# [EN] ⚠ `refs/` must **not** be excluded wholesale: it holds real code
# [EN] (`refs/indexer.py` reads `REFERENCE_DIR`), so excluding it makes that key look fake.
# [EN] `py_files()` only collects `.py`, so the md/txt under refs never enter anyway.
SKIP_FILES = {'audit_code.py'}


def py_files() -> list[Path]:
    out: list[Path] = []
    for t in TREES:
        d = APP / t
        if not d.is_dir():
            continue
        for p in d.rglob('*.py'):
            if any(s in p.parts for s in SKIP_DIRS):
                continue
            if any(x in p.name for x in ('.bak', '_bak', '.tmp')):
                continue
            if p.name in SKIP_FILES:
                continue
            out.append(p)
    return sorted(out)


def _rel(p: Path) -> str:
    return p.relative_to(APP).as_posix()


def _tree(p: Path):
    try:
        return ast.parse(p.read_text(encoding='utf-8', errors='replace'))
    except (SyntaxError, ValueError):
        return None


# ══════════════════════════════════════════════════════════════════
#  A  假旋钮：SPEC 里登记了，没人读
# ══════════════════════════════════════════════════════════════════
def cat_a(files: list[Path]) -> list[str]:
    from config import SPEC
    src_all = {p: p.read_text(encoding='utf-8', errors='replace') for p in files}
    blob = '\n'.join(src_all.values())
    bad: list[str] = []
    for key, meta in SPEC.items():
        # 读法有三种：`CFG.i('KEY')` / `CFG.b('KEY')` / `CFG.s('KEY')`，
        # 以及 `SPEC['KEY']`、`for k in SPEC` 这类遍历。**只认字符串出现**，
        # 因为动态拼 key 的写法（`f'MODEL_{x}'`）扫不到 —— 那种要人工看。
        # [EN] Three read styles (`CFG.i/b/s('KEY')`) plus SPEC lookups. Only **string
        # [EN] occurrences** count; dynamically built keys (`f'MODEL_{x}'`) cannot be found and
        # [EN] need a human look.
        n = len(re.findall(rf'(?<![\w.]){re.escape(key)}(?![\w])', blob))
        if n == 0:
            bad.append(f'{key}（{meta.get("group", "?")}）')
    return bad


# ══════════════════════════════════════════════════════════════════
#  B  静默降级：except 里什么都不说
# ══════════════════════════════════════════════════════════════════
def cat_b(files: list[Path]) -> list[str]:
    """`except` 体里**一句解释都没有**、而且**在关键链路上**的那些。

    ⚠ 742 条（全库）是没用的报告 —— 绝大多数是"可选依赖/可选文件读不到就用默认值"，
      那是设计允许的。真正要人看的是**会吞掉 bug 的那一小撮**：
        · 在**主链路**上（`sim/` `agent/` `crew/` `display/` `world/` `director/`）
          —— 这些地方的异常意味着"这一拍的产出是错的"，不该无声；
        · `except` 捕获的是**宽泛的 Exception**（不是 KeyError/OSError 这类预期异常）；
        · 里面只有 `pass` 或裸 `return`。
    [EN] Only handlers with **no trace at all** AND **on the critical path** AND catching a
    [EN] **broad Exception**. The full 742 is a useless report: most are legitimate "optional
    [EN] dependency missing => use the default" cases. What a human must see is the small set that
    [EN] swallows a real bug (a wrong output for that beat).
    """
    hot = ('sim/', 'agent/', 'crew/', 'display/', 'world/', 'director/')
    bad: list[str] = []
    for p in files:
        rel = _rel(p)
        if not rel.startswith(hot):
            continue
        tree = _tree(p)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            # 只算宽泛捕获（有具体类型名的按预期异常处理）
            # [EN] Broad catches only; a named type is an expected exception.
            t = node.type
            name = ''
            if isinstance(t, ast.Name):
                name = t.id
            elif isinstance(t, ast.Attribute):
                name = t.attr
            if name not in ('Exception', 'BaseException'):
                continue
            silent = True
            for st in node.body:
                if isinstance(st, (ast.Pass, ast.Continue, ast.Break)):
                    continue
                if isinstance(st, ast.Return) and (
                        st.value is None or isinstance(st.value, ast.Constant)):
                    continue
                silent = False
                break
            if silent:
                bad.append(f'{rel}:{node.lineno}')
    return bad


# ══════════════════════════════════════════════════════════════════
#  C  两份实现：同名顶层函数写在多个文件里
# ══════════════════════════════════════════════════════════════════
def cat_c(files: list[Path]) -> list[str]:
    """同名顶层函数（≥12 行，排除 get/__init__ 这类必然重名的）。

    ⚠ 排除清单要**写在这里**、不许临时加：`render` / `main` / `run` 这类
      "每个模块都有自己的入口"是正常设计，不排掉会淹掉真信号。
    [EN] The exclusion list lives here and must not be extended on the fly: `render` / `main` /
    [EN] `run` are legitimately per-module, and not excluding them drowns the real signal.
    """
    skip = {'main', 'run', 'render', 'build', 'get', 'set', 'load', 'save', 'start',
            'stop', 'close', 'reset', 'init', '__init__', 'now', 'parse', 'apply'}
    seen: dict[str, list[str]] = defaultdict(list)
    for p in files:
        tree = _tree(p)
        if tree is None:
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name in skip:
                continue
            if (node.end_lineno or 0) - node.lineno < 12:
                continue
            seen[node.name].append(_rel(p))
    # ⚠ **只看产品代码之间**的重复：`tools/` 与 `developers/` 里的夹具函数
    #   （`_fixture` / `_render` / `_restore_leftovers`…）**本来就该各写一份**
    #   —— 判据之间不共享夹具是有意的（一条判据崩了不该连累另一条）。
    #   第一版没排，报出 148 条，全被这类淹掉（真信号 0 条）。
    # [EN] ⚠ Only count duplicates **between product modules**: fixture helpers in `tools/` and
    # [EN] `developers/` are supposed to be duplicated (else one crashing criterion takes another
    # [EN] down with it). The first version did not exclude them: 148 hits, all drowned out.
    def _prod(path: str) -> bool:
        return not (path.startswith('tools/') or path.startswith('developers/')
                    or path.startswith('novel_bench/'))

    out = [f'{name} → {", ".join(paths)}' for name, paths in seen.items()
           if len(paths) >= 2 and sum(1 for x in paths if _prod(x)) >= 2]
    return sorted(out)


# ══════════════════════════════════════════════════════════════════
#  D  被写死的数字：同一个魔法数在多处
# ══════════════════════════════════════════════════════════════════
def cat_d(files: list[Path]) -> list[str]:
    """`len(x) <= N` / `> N` 这类**判定阈值**写死在多处（改一处漏一处）。

    ⚠ 只收"判定型"用法（`<=`/`>=`/`<`/`>` 里出现的整数），不数普通数字 ——
      否则坐标、尺寸、字号全会上来。已知豁免：0/1/2/100。
    [EN] Only comparison thresholds, not plain numbers (otherwise coordinates, sizes and font
    [EN] scales flood the list). Known exemptions: 0/1/2/100.
    """
    exempt = {0, 1, 2, 3, 4, 5, 6, 8, 10, 100, 1000}
    # ⚠ **只扫产品代码**：`developers/probe_*.py` 里 200/40/20 是**像素与字数**阈值，
    #   它们是探针自己的量具，本来就会到处出现。第一版没排，12 条全是这类假信号。
    # [EN] ⚠ **Product code only**: the numbers in `developers/probe_*.py` are pixel and
    # [EN] character thresholds -- measuring tools' own constants. The first version did not
    # [EN] exclude them and all 12 hits were false.
    def _prod(rel: str) -> bool:
        return not (rel.startswith('tools/') or rel.startswith('developers/')
                    or rel.startswith('novel_bench/'))

    files = [p for p in files if _prod(_rel(p))]
    hits: list[tuple[int, str]] = []
    for p in files:
        tree = _tree(p)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            for c in [node.left] + list(node.comparators):
                if isinstance(c, ast.Constant) and isinstance(c.value, int):
                    if c.value in exempt:
                        continue
                    hits.append((c.value, _rel(p)))
    cnt = Counter(v for v, _ in hits)
    out: list[str] = []
    for v, n in cnt.most_common(12):
        if n < 2:
            break
        where = sorted({f for x, f in hits if x == v})[:4]
        out.append(f'{v} 出现 {n} 次判定：{", ".join(where)}')
    return out


# ══════════════════════════════════════════════════════════════════
#  E  参数加了没传：签名有、调用点一个都没给
# ══════════════════════════════════════════════════════════════════
def cat_e(files: list[Path]) -> list[str]:
    """模块级函数的**可选参数**，全库调用点一个都没传。

    这就是"半截改动"：参数加进去了、路径也改了，但**没人传** ⇒ 永远是默认值，
    看起来像做完了。本项目踩过（`last_own_action` 的 kind 表就是这么假绿的）。
    ⚠ 只在**产品代码**里找候选函数（判据/探针里的可选参数本来就多），
      而且**只统计含有该参数名的调用** —— 用 AST 数，不用正则（正则在大文件上
      回溯爆炸，第一版跑 200 秒超时）。
    [EN] A module-level optional parameter that **no call site passes** -- the half-done change
    [EN] that always uses the default and looks finished.
    [EN] ⚠ Candidate functions come from **product code** only, and call sites are counted with
    [EN] AST rather than regex (the regex version blew up and timed out at 200 s).
    """
    prod = [p for p in files
            if not (_rel(p).startswith('tools/') or _rel(p).startswith('developers/')
                    or _rel(p).startswith('novel_bench/'))]
    blob = '\n'.join(p.read_text(encoding='utf-8', errors='replace') for p in files)

    # 先收集所有"被调用过的名字"（AST，一次遍历）：名字 → 调用点的关键字集合
    # [EN] First collect every called name and the keywords used at its call sites.
    # ⚠ 光看"关键字里有没有它"会误报：`make_image_hook(proj, run)` 是**按位置**传的
    #   （实测第一版把它的 `project=` / `run=` 报成"一个都没传"）。
    #   ⇒ 同时记下**位置实参的个数**，够到那个参数的位置就算传了。
    # [EN] ⚠ Keyword-only detection gives false positives: `make_image_hook(proj, run)` passes
    # [EN] **positionally** (the first version flagged its `project=` / `run=` as never passed).
    # [EN] => also record the **positional argument count**; reaching the parameter's position
    # [EN] counts as passed.
    called: dict[str, set[str]] = defaultdict(set)
    n_pos: dict[str, int] = defaultdict(int)
    n_call: Counter[str] = Counter()
    for p in files:
        tree = _tree(p)
        if tree is None:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                fn = n.func
                name = (fn.id if isinstance(fn, ast.Name)
                        else fn.attr if isinstance(fn, ast.Attribute) else '')
                if not name:
                    continue
                n_call[name] += 1
                called[name] |= {k.arg for k in n.keywords if k.arg}
                n_pos[name] = max(n_pos[name], len(n.args))

    out: list[str] = []
    for p in prod:
        tree = _tree(p)
        if tree is None:
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            a = node.args
            defaults = a.defaults or []
            if not defaults:
                continue
            all_args = [x.arg for x in a.args]
            opt = all_args[len(all_args) - len(defaults):]
            used = called.get(node.name)
            if not used:
                continue          # 没人调用它（可能是回调/入口），不算半截
            for name in opt:
                if name in ('self', 'cls'):
                    continue
                if name in used:
                    continue
                # 位置传到了也算（见上面那段说明）
                # [EN] Reaching it positionally also counts (see the note above).
                if n_pos[node.name] > all_args.index(name):
                    continue
                out.append(f'{_rel(p)}::{node.name}({name}=…)  —— '
                           f'{n_call[node.name]} 处调用，关键字与位置都没给')
    return sorted(set(out))


# ══════════════════════════════════════════════════════════════════
#  F  登记错组
# ══════════════════════════════════════════════════════════════════
def cat_f(files: list[Path]) -> list[str]:
    import importlib.util as u

    spec = u.spec_from_file_location('_rav', APP / 'tools' / 'run_all_verifications.py')
    m = u.module_from_spec(spec)
    spec.loader.exec_module(m)
    out: list[str] = []
    for group, names in (('LOGIC', getattr(m, 'LOGIC', [])),
                         ('GUI', getattr(m, 'GUI', []))):
        for n in names:
            p = APP / 'tools' / f'{n}.py'
            if not p.is_file():
                out.append(f'{n}：登记在 {group}，但文件不存在')
                continue
            src = p.read_text(encoding='utf-8', errors='replace')
            # ★★★ 只认 `ft.run(` 这一个**硬信号**（"真的开了 flet 窗口"）。
            #   试过更宽的判定（`subprocess` + `.exe` / `flet_desktop`）⇒ 立刻多出 8 条误报
            #   （`verify_sdk` / `verify_env_safety` 只是源码里出现了 `.exe` 字样）。
            #   ⇒ **判不准的类别就收窄到只报"确定的那一种"**，剩下的靠人看，
            #     别为了"多报几条"把信号淹掉（这正是本审计要治的病）。
            # [EN] ★★★ Only the single **hard signal** `ft.run(` ("a flet window really opens").
            # [EN] A wider test (`subprocess` + `.exe` / `flet_desktop`) produced 8 immediate false
            # [EN] positives. => **narrow an unreliable category to the one certain case** and let a
            # [EN] human read the rest; do not drown the signal for the sake of "reporting more".
            has_run = 'ft.run(' in src
            if n in KNOWN_GUI_WITHOUT_FTRUN:
                continue
            if group == 'LOGIC' and has_run:
                out.append(f'{n}：登记在 LOGIC，但会 `ft.run(`（真机窗口）—— 并行时抢桌面')
            if group == 'GUI' and not has_run:
                out.append(f'{n}：登记在 GUI，但没有 `ft.run(`（纯逻辑）—— 白占真机名额')
    return out


#: 登记在 GUI 组、但**不靠 `ft.run(`** 开窗口的（它们起的是编好的 exe / 子进程）。
#: 这不是"豁免错误"，而是"这一类别判不准" —— 写在这里，让人**看得见**它们存在。
# [EN] Registered under GUI but not opening a window via `ft.run(` (they launch built exes /
# [EN] subprocesses). Not an amnesty: the category simply cannot be judged automatically, so they
# [EN] are listed here to stay **visible**.
KNOWN_GUI_WITHOUT_FTRUN = {
    'verify_launchers', 'verify_installer', 'verify_orphan_windows',
    'verify_external_services', 'verify_sdk',
}

CATS = {
    'A': ('假旋钮（登记了但没人读的配置项）', cat_a),
    'B': ('静默降级（except 里不留痕）', cat_b),
    'C': ('两份实现（同名顶层函数）', cat_c),
    'D': ('写死的判定阈值（多处出现）', cat_d),
    'E': ('参数加了没传（半截改动）', cat_e),
    'F': ('回归登记错组', cat_f),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--cat', default=''.join(CATS),
                    help='只扫这几类，如 A,B（默认全扫）')
    a = ap.parse_args()
    # ⚠ `--cat ABCDEF` 要当成 A,B,C,D,E,F：默认值就是 `''.join(CATS)`，
    #   而第一版只按逗号切 ⇒ 得到 `['ABCDEF']`，一个类别都不匹配、报告永远是 0 条
    #   （**这是"判据什么都没看见"的经典形态，出现在审计工具自己身上**）。
    # [EN] ⚠ `--cat ABCDEF` must mean A,B,C,D,E,F: the default is `''.join(CATS)`, and the first
    # [EN] version only split on commas => `['ABCDEF']`, matching nothing, so the report was always
    # [EN] 0 rows. The classic "the criterion saw nothing" failure, inside the audit tool itself.
    want: list[str] = []
    for chunk in a.cat.split(','):
        chunk = chunk.strip().upper()
        if not chunk:
            continue
        if len(chunk) > 1 and all(ch in CATS for ch in chunk):
            want.extend(list(chunk))
        else:
            want.append(chunk)
    files = py_files()
    print(f'扫 {len(files)} 个 py 文件 · 类别 {",".join(want)}\n')
    total = 0
    for key in want:
        if key not in CATS:
            continue
        title, fn = CATS[key]
        try:
            rows = fn(files)
        except Exception as e:                               # noqa: BLE001
            rows = [f'（这一类自己崩了：{e!r}）']
        #: 信噪比最差的一类：它数的是"同一个整数出现几次"，
        #: 分不清"像素尺寸"和"逻辑阈值"。**明写出来**，别让人以为它是判决。
        # [EN] The lowest signal-to-noise category: it counts integer occurrences and cannot tell
        # [EN] "pixel size" from "logic threshold". Say so **explicitly** so nobody reads it as a
        # [EN] verdict.
        hint = '（仅供参考：像素/字数阈值也会进来）' if key == 'D' else \
               '（需要人判：多数是合理的可选降级）' if key == 'B' else ''
        print(f'══ {key} · {title}：{len(rows)} 条{hint}')
        for r in rows[:40]:
            print(f'   · {r}')
        if len(rows) > 40:
            print(f'   … 另有 {len(rows) - 40} 条')
        print()
        total += len(rows)
    print(f'合计 {total} 条（这是**体检报告**，不是判据：有的属于合理的历史遗留）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
