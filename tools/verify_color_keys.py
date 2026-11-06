# -*- coding: utf-8 -*-
"""验证 `gui/app_flet.py` 里**每一个配色键都真的存在**（`C[...]` / `INKC[...]`）。

为什么要有这一支
----------------
2026-10-10 用户报：「我打开一次 点了网址 再点击其他页面 或者关闭了重新点击拆书
会报错如下」，日志里是：

    [消息/error] 选示例失败: 'ink'

`'ink'` 是个 `KeyError`。根因是拆书对话框里写了一句
`color=C['ink']` —— 而 **`ink` 在 `INKC` 里、不在 `C` 里**
（两套配色：`C` 是通用界面色，`INKC` 是开始界面的"彩墨"色）。
顺着查下去，同一个对话框里还有 **5 处同类**（`C['ink']` ×2、`C['danger']` ×3），
全是既有的、只是**一直没人踩到那个分支**。

★★ 为什么这类 bug 值得专门一支判据
----------------------------------
它的三个性质凑在一起特别难发现：
  ① **静态看不出来** —— `C['ink']` 语法完全合法，`py_compile` 不报错；
  ② **只在某个分支才炸** —— 那几处分别在"结论带模块"、"范围解析失败"、
     "选中了文件/示例"三条路上，平时走不到；
  ③ **报错信息离根因很远** —— 用户看到的是「选示例失败: 'ink'」，
     而真正错的地方是一个**颜色**。
⇒ 而它又是**完全确定**的：配色键是**字面量**，字典就在同一个文件里，
  AST 过一遍就能全查出来 —— 不需要起界面、不需要真机、毫秒级。

⚠ 口径（别过度声称）
-------------------
只查**字面量键**：`C['ink']` / `INKC["card"]` 这种。
`C[k]`（变量索引）查不了 —— 那种情况这一支**不会**报，也不该报
（"查不到"与"不存在"是两回事，硬报就是假警报）。
所以本判据的立场是"**能确定的错**一个都不放过"，不是"所有错都拦住"。

产出：assets/screenshots/color_keys_report.json
用法：.venv/Scripts/python.exe tools/verify_color_keys.py

English:
Verify that **every color key really exists** in `gui/app_flet.py` (`C[...]` / `INKC[...]`).
Why this check exists
----------------
2026-10-10 user report: "I opened it once, clicked the URL, then clicked another page, or closed
it and clicked 拆书 again
it errors as follows", in the log it's:
`'ink'` is a `KeyError`. Root cause is a line in the 拆书 dialog
`color=C['ink']` -- and **`ink` is in `INKC`, not in `C`**
(two color sets: `C` is the general UI color, `INKC` is the start screen's "彩墨" color).
Following it down, the same dialog has **5 more of the same kind** (`C['ink']` x2, `C['danger']`
x3),
all pre-existing, it's just that **nobody ever hit that branch**.
★★ Why this kind of bug deserves its own dedicated check
----------------------------------
Its three properties together make it especially hard to find:
  ① **Not statically visible** -- `C['ink']` is syntactically perfectly legal, `py_compile` doesn't error;
  ② **Only blows up on a certain branch** -- those spots are on the "conclusion has module", "range parsing failed",
     "file/example selected" three paths, not normally reachable;
  ③ **The error message is far from the root cause** -- what the user sees is "选示例失败: 'ink'",
     while the truly wrong place is a **color**.
=> And it is **fully deterministic**: the color keys are **literals**, the dict is in the same
file,
  one AST pass finds them all -- no need to start the UI, no need for a real device, millisecond-level.
⚠ Scope (don't overclaim)
-------------------
Only check **literal keys**: things like `C['ink']` / `INKC["card"]`.
`C[k]` (variable index) can't be checked -- in that case this check **will not** report, and
shouldn't report
("can't find" and "doesn't exist" are two different things, forcing a report is a false alarm).
So this check's stance is "**certain errors** not one is let through", not "all errors are
caught".
Output: assets/screenshots/color_keys_report.json
Usage: .venv/Scripts/python.exe tools/verify_color_keys.py
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

TARGET = APP_DIR / 'gui' / 'app_flet.py'
#: 要查的配色名（都是 `app_flet.py` 里的模块级 dict）
# [EN] : color name to look up (all are module-level dicts in `app_flet.py`)
PALETTES = ('C', 'INKC')

report: dict = {'steps': []}


def rec(name: str, ok: bool, detail: str = '') -> bool:
    report['steps'].append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(f'  {"✓" if ok else "✗"} {name}' + (f'  — {detail}' if detail else ''),
          flush=True)
    return ok


def dict_keys(src: str, name: str) -> set[str]:
    """模块级 `name = {...}` 字面量的**全部字符串键**（含被 `update()` 补的）。

    ⚠ 不能只看 `ast.Dict` 的字面量：`C` 有一部分键是在
      `apply_ui_opacity()` 里 `C['panel'] = with_alpha(...)` 那样补上的
      （那种键字面量里没有）。所以要把
      `NAME['k'] = ...` / `NAME.update({...})` 两种写法也算进来 ——
      否则本判据会给**合法**的用法报假红。
    
        English:
    **All string keys** of the module-level `name = {...}` literal (including those added by
    `update()`).
        ⚠ Can't only look at the literal of `ast.Dict`: some of `C`'s keys are added
          in `apply_ui_opacity()` via `C['panel'] = with_alpha(...)`
          (those keys aren't in the literal). So we must also count
          `NAME['k'] = ...` / `NAME.update({...})` two forms --
          otherwise this check will false-red a **legal** usage.
    """
    tree = ast.parse(src)
    keys: set[str] = set()
    for node in ast.walk(tree):
        # ① NAME = { ... }
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)
                and any(isinstance(t, ast.Name) and t.id == name
                        for t in node.targets)):
            for k in node.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
        # ② NAME.update({ ... })
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'update'
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == name
                and node.args and isinstance(node.args[0], ast.Dict)):
            for k in node.args[0].keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
        # ③ NAME['k'] = ...
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Subscript)
                and isinstance(node.targets[0].value, ast.Name)
                and node.targets[0].value.id == name
                and isinstance(node.targets[0].slice, ast.Constant)
                and isinstance(node.targets[0].slice.value, str)):
            keys.add(node.targets[0].slice.value)
    return keys


def bad_subscripts(src: str, name: str, have: set[str]) -> list[tuple[int, str]]:
    """所有 `NAME['k']` 里 **`k` 不在 `have` 里**的 `(行号, 键)`。
        English:
    All `(line number, key)` where **`k` is not in `have`** among all `NAME['k']`.
    """
    out: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == name
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
                and node.slice.value not in have):
            out.append((getattr(node, 'lineno', 0), node.slice.value))
    return sorted(out)


def main() -> int:
    print('  配色键验证（`C[...]` / `INKC[...]` 的字面量键都要存在）')
    if not TARGET.exists():
        rec('gui/app_flet.py 在', False, str(TARGET))
        return 2
    src = TARGET.read_text(encoding='utf-8')

    ok_all = True
    for name in PALETTES:
        have = dict_keys(src, name)
        report[f'keys_{name}'] = sorted(have)
        ok_has = rec(f'{name} 有键（{len(have)} 个）', bool(have))
        ok_all &= ok_has
        bad = bad_subscripts(src, name, have)
        report[f'bad_{name}'] = bad
        # ★ 失败信息要**带行号 + 那个键**（否则又要回去 grep 一遍）
        # [EN] ★ failure info must include **the line number + that key** (otherwise you have to go back and
        # [EN] grep again)
        detail = '；'.join(f'第 {ln} 行 {name}[\'{k}\']' for ln, k in bad[:6])
        ok_all &= rec(f'{name}[...] 用的键都存在（字面量键全查）', not bad, detail)

    report['ok'] = ok_all
    (OUT / 'color_keys_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n  共 {len(report["steps"])} 项断言，'
          f'{"全部通过" if ok_all else "有失败"}')
    if not ok_all:
        print('  （`C` 是通用界面色、`INKC` 是开始界面的彩墨色 —— '
              '两套别写混：`ink` 只在 INKC 里）')
    return 0 if ok_all else 2


if __name__ == '__main__':
    sys.exit(main())
