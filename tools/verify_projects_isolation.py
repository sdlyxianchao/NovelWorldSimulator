# -*- coding: utf-8 -*-
"""验证：**判据不许把夹具项目写进用户的真实项目目录**（2026-10-17）。

## 为什么单开一支

`verify_ui_common.isolate_projects_dir(base)` 把 `DEFAULT_PROJECTS_DIR` 临时指到
`base`，然后 **返回换之前的老值**（用于收尾还原）。返回值**不是**新目录。

而"想拿新目录"的自然写法是 `Path(isolate_projects_dir(base)) / '名字'` ——
它拼出来是**用户真实项目目录 + 夹具名**。2026-10-17 在 8 处踩到（4 支判据 +
4 个探针）：

    tools/verify_export.py        （已修，当时是「导出验证」那个残留的来历）
    tools/verify_font_settings.py      「字体设置验证」
    tools/verify_run_panel_nav.py      「面板跳转验证」
    tools/verify_main_flags.py         「开关自适应验证」
    tools/verify_main_screen.py        「主界面留空验证」
    tools/verify_usage_layout.py       （接了返回值但没用，差一步就删到用户目录）
    developers/audit_screens.py        「界面排查临时」
    developers/preview_look.py         「配色预览临时」
    developers/probe_usage_widths.py   （同上，接了没用）

后果不是崩，而是**在用户的「拾卷」列表里堆测试项目**，而且靠收尾的
`safe_rmtree` 删 —— 一旦脚本被 Kill / 文件句柄没释放（Windows 上很常见），
就永久留下来（用户机上确实还躺着两个）。这类"不报错的污染"只能靠判据咬。

## 判据分三组

  A 组（AST 静态扫描）：`tools/` 与 `developers/` 下**没有任何一处**
     把 `isolate_projects_dir(...)` 的返回值当落点用
  B 组（行为）：`isolate_projects_dir` 确实返回老值；**照规矩写就落对地方**、
     照错法写就落进"用户目录"—— 两半都当场演示（成对，防"一刀切也能绿"）
  C 组（自指）：本判据自己用的就是正确写法

反例法：`developers/mutate_projects_isolation.py`。

English:
Verify that **criteria never write fixture projects into the user's real project directory**
(2026-10-17).

`verify_ui_common.isolate_projects_dir(base)` points `DEFAULT_PROJECTS_DIR` at `base` and
**returns the previous value** (for restoring at teardown). The return value is **not** the new
directory. The natural-looking `Path(isolate_projects_dir(base)) / 'name'` therefore builds
**the user's real project directory + the fixture name**. Hit in 8 places on 2026-10-17
(4 criteria + 5 probes; see the list above). The damage is not a crash but **fixture projects
piling up in the user's "拾卷" list**, removed only by the teardown `safe_rmtree` -- killed
scripts or unreleased Windows handles leave them forever (two are still sitting on the user's
machine). This class of silent pollution can only be pinned by a criterion.
Three groups: A (AST scan: not a single use of the return value as a landing path under
`tools/` and `developers/`); B (behaviour: the function really returns the old value; the
correct form lands in the right place and the wrong form lands in the "user directory" -- both
demonstrated on the spot, paired so "one-size-fits-all still passes" cannot happen); C
(self-reference: this criterion itself uses the correct form).

跑法：.venv/Scripts/python.exe tools/verify_projects_isolation.py [--logic-only]
产出：assets/screenshots/projects_isolation_report.json
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                   # noqa: E402
import verify_ui_common as VU                            # noqa: E402

CFG.set('MOCK_LLM', 'true')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT_P = OUT / 'projects_isolation_report.json'

report: dict = {'checks': [], 'offenders': []}
_failed: list[str] = []

#: 要扫的目录：判据与探针都在里面（产品代码 `gui/ sim/ …` 不该出现这个调用）
SCAN_DIRS = ('tools', 'developers')

#: `isolate_projects_dir` 的限定名可能长什么样（`VU.isolate_projects_dir` / 裸名）
_FN = 'isolate_projects_dir'


def ok(name: str, cond, detail: str = '') -> bool:
    cond = bool(cond)
    report['checks'].append({'name': name, 'ok': cond, 'detail': str(detail)})
    if not cond:
        _failed.append(name)
    print(f'  {"✓" if cond else "✗"} {name}'
          + (f'   [{detail}]' if detail else ''), flush=True)
    return cond


def _is_iso_call(node: ast.AST) -> bool:
    """判断一个节点是不是 `isolate_projects_dir(...)` 的调用（认 `VU.` 前缀）。"""
    return (isinstance(node, ast.Call)
            and ((isinstance(node.func, ast.Name) and node.func.id == _FN)
                 or (isinstance(node.func, ast.Attribute) and node.func.attr == _FN)))


# ══════════════════════════════════════════════════════════════════════
#  A 组：静态扫描
# ══════════════════════════════════════════════════════════════════════
def scan_static() -> None:
    me = Path(__file__).resolve()
    files = []
    for d in SCAN_DIRS:
        base = APP_DIR / d
        if base.is_dir():
            files += [p for p in base.rglob('*.py')
                      if '__pycache__' not in p.parts and p.resolve() != me]
    report['scanned'] = len(files)
    ok('A0 扫到了东西（tools/ + developers/ 下的 .py）', len(files) > 20,
       f'{len(files)} 个文件')

    offenders: list[str] = []
    for p in files:
        try:
            tree = ast.parse(p.read_text(encoding='utf-8', errors='ignore'))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # 形态一：`Path(isolate_projects_dir(...))` —— 嵌套调用
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == 'Path'
                    and node.args and _is_iso_call(node.args[0])):
                offenders.append(f'{p.relative_to(APP_DIR)}:{node.lineno}')
                continue
            # 形态二：`X = isolate_projects_dir(...)` 之后再 `Path(X)` ——
            #   同一函数作用域里两个都出现就算（够用：真出事就是这种写法）
            #   ⚠ 这条会**误报**一种合法写法：`old = iso(...)` 然后收尾
            #     `if old: CFG.set('DEFAULT_PROJECTS_DIR', old)` —— 那里没有 `Path(old)`。
            #     所以只认"同一函数里既有赋值、又有 `Path(那个名字)`"。
        # 形态二按函数粒度判
        for fn in [n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            names: set[str] = set()
            for node in ast.walk(fn):
                if (isinstance(node, ast.Assign) and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name)
                        and _is_iso_call(node.value)):
                    names.add(node.targets[0].id)
            if not names:
                continue
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == 'Path' and node.args
                        and isinstance(node.args[0], ast.Name)
                        and node.args[0].id in names):
                    offenders.append(f'{p.relative_to(APP_DIR)}:{node.lineno}'
                                     f'（{node.args[0].id}）')

    report['offenders'] = sorted(set(offenders))
    ok('A1 ★★★ 没有任何一处把 `isolate_projects_dir()` 的**返回值当落点**用'
       '（认两种形态：`Path(iso(...))` 与 `x = iso(...); Path(x)`）',
       not offenders,
       '、'.join(report['offenders'][:6]) if offenders else '0 处')


def _demo_hits_here() -> list[int]:
    """本判据自己文件里"故意演示的错法"在哪几行（形态一 + 形态二）。

    ★★ 为什么要单独数：B 组要**当场演示**错法（否则"为什么必须判"没有证据），
      而那段演示本身就是错法 ⇒ A1 会把本判据自己也抓成红（第一次跑就这样）。
      **不能简单跳过本文件**（那等于给自己留后门）。
      做法：本文件里每一处错法都必须**带 `演示：错法` 标记**，且**总数正好是
      `_EXPECTED_DEMOS`** —— 多一处、少一处、或没标记，C1 就红。
    [EN] ★★ Why count separately: group B must **demonstrate** the wrong form on the spot
    [EN] (otherwise "why this must be checked" has no evidence), and that demo *is* the wrong form
    [EN] => A1 would flag this very criterion red (which is what happened on the first run).
    [EN] **Skipping this file is not allowed** (that would leave a backdoor). Instead: every wrong-form
    [EN] occurrence in this file must carry a `演示：错法` marker, and the total must equal
    [EN] `_EXPECTED_DEMOS` -- one more, one fewer, or a missing marker makes C1 red.
    """
    src = Path(__file__).read_text(encoding='utf-8')
    lines = src.splitlines()
    tree = ast.parse(src)
    hits: list[int] = []
    iso_names: set[str] = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and _is_iso_call(node.value)):
            iso_names.add(node.targets[0].id)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'Path' and node.args):
            continue
        a0 = node.args[0]
        if _is_iso_call(a0) or (isinstance(a0, ast.Name) and a0.id in iso_names):
            hits.append(node.lineno)
    # 只认带标记的（窗口取前 4 行：中文标记行与英文 `[EN]` 行各占一行）
    # [EN] Only marker-carrying lines count (window = 4 lines above: the Chinese marker line and the
    # [EN] `[EN]` counterpart each take one line).
    marked = []
    for ln in hits:
        window = '\n'.join(lines[max(0, ln - 5):ln])
        if '演示：错法' in window:
            marked.append(ln)
    return sorted(set(hits)), sorted(set(marked))


# ══════════════════════════════════════════════════════════════════════
#  B 组：行为（真假两半都演示）
# ══════════════════════════════════════════════════════════════════════
def behaviour() -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_iso_'))
    fake_user = tmp / '用户项目目录'
    fake_user.mkdir(parents=True, exist_ok=True)
    iso = tmp / '隔离目录'

    saved = CFG.raw('DEFAULT_PROJECTS_DIR')
    try:
        # 先把"用户目录"设成假的，再隔离 —— 这样老值就是 fake_user
        CFG.set('DEFAULT_PROJECTS_DIR', str(fake_user))
        old = VU.isolate_projects_dir(iso)

        # ⚠ 这里用 `str(old)` 比较、**不用 `Path(old)`**：本判据的 A1/C3 把
        #   "同函数里 `x = iso(...)` 之后又出现 `Path(x)`" 认成错法形态，而这一处
        #   只是**读值做断言**（合法）。写成 `str(...)` 两边都不会被误判 ——
        #   而且本文件里就只剩 B3 那一处"故意演示"的错法，C3 的数字才对得上。
        # [EN] ⚠ Compare with `str(old)`, **not `Path(old)`**: A1/C3 treat "`x = iso(...)` followed by
        # [EN] `Path(x)` in the same function" as the wrong form, while this spot only **reads the value
        # [EN] for an assertion** (legitimate). Using `str(...)` avoids the false hit on both sides --
        # [EN] and leaves B3's deliberate demo as the only wrong-form occurrence, so C3's count matches.
        ok('B1 ★★ `isolate_projects_dir()` 返回的是**换之前的老值**'
           '（不是新目录 —— 这就是那 8 处误用的根）',
           str(old) == str(fake_user) and CFG.projects_dir() == iso,
           f'返回={old}｜现在指向={CFG.projects_dir()}')

        # ── 正例：照规矩写（自己留 seed）⇒ 落在隔离目录里 ──
        seed = iso / '正例夹具'
        VU.isolate_projects_dir(seed)
        good = seed / '正例夹具'
        good.mkdir(parents=True, exist_ok=True)
        (good / '设定集').mkdir(exist_ok=True)
        # ⚠ 两个条件缺一不可（反例法 ④ 教我的）：
        #   ① `CFG.projects_dir() == seed` —— **隔离真的生效了**（把 `isolate_projects_dir`
        #      里的 `CFG.set` 删掉，这一条就红；只判 `good.is_dir()` 的话**照样绿**，
        #      因为 `good` 是 mkdir 出来的，跟 CFG 指哪儿毫无关系）；
        #   ② `good` 落在 `iso` 下面 —— 写法本身对。
        # [EN] ⚠ Both conditions are required (taught by counterexample ④):
        # [EN] (1) `CFG.projects_dir() == seed` -- **the isolation really took effect** (delete the
        # [EN] `CFG.set` inside `isolate_projects_dir` and this goes red; judging only `good.is_dir()`
        # [EN] stays green because `good` is made by mkdir and has nothing to do with where CFG points);
        # [EN] (2) `good` sits under `iso` -- the form itself is right.
        ok('B2 ★★★ 照规矩写（`iso(seed)` 后自己拼 `seed/名字`）⇒ '
           '**隔离真的生效**且夹具落在**隔离目录**里',
           CFG.projects_dir() == seed and good.is_dir() and iso in good.parents,
           f'CFG 指向={CFG.projects_dir()}｜夹具={good}')

        # ── 反例：照错法写 ⇒ 当场落进"用户目录"（证明判据不是空喊）──
        #   这正是那 8 处的写法；在这里复现一次，让"为什么必须判"有证据。
        # [EN] The wrong form, reproduced here so that "why this must be checked" has evidence.
        CFG.set('DEFAULT_PROJECTS_DIR', str(fake_user))
        ret = VU.isolate_projects_dir(tmp / '又一个隔离目录')
        # 演示：错法（本文件唯一允许的一处，A1 已排除本文件、C1 会核这一处带标记）
        # [EN] 演示：wrong form (the only occurrence allowed in this file; A1 excludes this file and
        # [EN] C1 verifies this one carries the marker)
        wrong = Path(ret) / '错法夹具'
        wrong.mkdir(parents=True, exist_ok=True)
        ok('B3 ★★★ 成对：照**错法**写（`Path(返回值)/名字`）⇒ 当场落进「用户目录」'
           '（这就是「拾卷」里冒出测试项目的原因）',
           wrong.is_dir() and fake_user in wrong.parents,
           str(wrong))

        # 用户在「拾卷」里会看到的东西 = 这个目录下的项目
        listed = sorted(p.name for p in fake_user.iterdir() if p.is_dir())
        report['fake_user_listing'] = listed
        ok('B4 ★★ 也就是说：错法跑的每一支判据，都会在用户项目列表里**多一个条目**',
           '错法夹具' in listed,
           str(listed))
    finally:
        if saved is None:
            CFG.set('DEFAULT_PROJECTS_DIR', '')
        else:
            CFG.set('DEFAULT_PROJECTS_DIR', saved)
        VU.safe_rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
#  C 组：自指（本判据自己不许犯）
# ══════════════════════════════════════════════════════════════════════
def self_check() -> None:
    src = Path(__file__).read_text(encoding='utf-8')
    tree = ast.parse(src)
    bad = 0
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'Path' and node.args
                and _is_iso_call(node.args[0])):
            bad += 1
    ok('C1 ★ 本判据自己用的是正确写法（`iso(seed)` 后自己拼），没犯它要抓的错',
       bad == 0, f'{bad} 处')

    # ★★★ 本文件里那处"演示"必须**恰好一处、且带标记** —— 这是不留后门的关键：
    #   A1 排除了本文件，如果这里不核，"在本文件里加一处真错法"就没人管。
    # [EN] ★★★ The single "demo" in this file must be **exactly one occurrence and carry the marker**
    # [EN] -- that is what keeps A1's exclusion of this file from becoming a backdoor.
    all_hits, marked = _demo_hits_here()
    report['self_demo_lines'] = {'all': all_hits, 'marked': marked}
    ok('C3 ★★★ 本文件里的错法**只有那一处演示**，且它带 `演示：错法` 标记'
       '（A1 排除了本文件，所以必须由这一条补上：多一处真错法就该红）',
       len(all_hits) == 1 and len(marked) == 1,
       f'错法 {len(all_hits)} 处，带标记 {len(marked)} 处：{all_hits}')
    ok('C2 ★ `tools/` 与 `developers/` 都在扫描范围内'
       '（漏一个目录就等于漏一整批）',
       all((APP_DIR / d).is_dir() for d in SCAN_DIRS), str(SCAN_DIRS))


def finish() -> int:
    total = len(report['checks'])
    bad = len(_failed)
    report['ok'] = bad == 0
    REPORT_P.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                        encoding='utf-8')
    print('=' * 66)
    if bad:
        print(f'项目隔离验证：{total - bad}/{total} 通过，{bad} 条红：')
        for n in _failed:
            print(f'  ✗ {n}')
    else:
        print(f'项目隔离验证：{total}/{total} 全部通过')
    print(f'报告：{REPORT_P}')
    return 0 if bad == 0 else 2


def main() -> int:
    scan_static()
    behaviour()
    self_check()
    return finish()


if __name__ == '__main__':
    sys.exit(main())
