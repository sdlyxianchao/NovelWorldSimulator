# -*- coding: utf-8 -*-
"""验证源码里用到的**每一个 `ft.xxx.yyy` 都真的存在**（Flet 公开 API 对得上）。

为什么要有这一支（2026-10-10 抓到的真 bug）
------------------------------------------
`gui/usage_dialog.py` 里有 4 处 `ft.padding.symmetric(...)` / `ft.padding.all(6)`，
而 **Flet 1.0.3 的 `ft.padding` 模块根本没有这两个函数** ⇒

    AttributeError: module 'flet.controls.padding' has no attribute 'all'

于是一个已经写好、判据也过了的对话框（`verify_usage_stats` **39/39**——
但那支只测**逻辑层**，从来没人打开过那个对话框）**点一次崩一次**。
用户看到的是"点了没反应"，而日志里是 `NameError`（见下一条）。

★★ 为什么值得专门一支判据
--------------------------
这类错误和"配色键写错"（`C['ink']`）是**同一类**，三个性质完全一样：
  ① **静态看不出**——`ft.padding.all(6)` 语法完全合法，`py_compile` 不管；
  ② **只在某个分支才炸**——那个对话框平时没人点；
  ③ **报错离根因很远**。
而它**可以完全确定地查出来**：`ft` 是个真实模块，逐段 `getattr` 就行。
（`tools/verify_color_keys.py` 查的是**字典键**，这支查的是**模块属性**。）

口径（别过度声称）
------------------
只查**源码里写死的属性链**（`ft.padding.all`）。`getattr(ft.Icons, name, None)`
那种**按变量取属性**的写法查不了 —— 那也是`mk_menu_icon` 故意留的兜底分支，
本条不会误报它。

产出：assets/screenshots/ft_api_report.json
用法：.venv/Scripts/python.exe tools/verify_ft_api.py

English:
Verify that **every `ft.xxx.yyy` used in the source actually exists** (matches Flet's public
API).
Why this check exists (a real bug caught on 2026-10-10)
------------------------------------------
`gui/usage_dialog.py` has 4 occurrences of `ft.padding.symmetric(...)` / `ft.padding.all(6)`,
but the **`ft.padding` module in Flet 1.0.3 does not have these two functions at all** =>
    AttributeError: module 'flet.controls.padding' has no attribute 'all'
So a dialog that was already written and whose checks passed (`verify_usage_stats` **39/39** --
but that only tests the **logic layer**; nobody ever opened that dialog) **crashes every time it
is clicked**.
What the user sees is "clicked and nothing happened", while the log shows `NameError` (see next
item).
★★ Why this deserves its own check
--------------------------
This kind of error is **the same class** as "misspelled color key" (`C['ink']`); all three
properties are identical:
  ① **Invisible statically** -- `ft.padding.all(6)` is perfectly legal syntax; `py_compile` doesn't care;
  ② **Only explodes on a certain branch** -- nobody clicks that dialog normally;
  ③ **The error is very far from the root cause**.
And it **can be detected with complete certainty**: `ft` is a real module, just `getattr`
segment by segment.
(`tools/verify_color_keys.py` checks **dictionary keys**; this check checks **module
attributes**.)
Scope (don't overclaim)
------------------
Only check **attribute chains hard-coded in the source** (`ft.padding.all`). `getattr(ft.Icons,
name, None)`
-- that **variable-based attribute access** style cannot be checked -- that is also the fallback
branch `mk_menu_icon` intentionally leaves,
and this check will not falsely report it.
Output: assets/screenshots/ft_api_report.json
Usage: .venv/Scripts/python.exe tools/verify_ft_api.py
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
#: 扫哪些目录（第三方与数据目录不扫）
# [EN] : Which directories to scan (third-party and data directories are not scanned)
SCAN_DIRS = ['gui', 'tools', 'util', 'store', 'craft', 'crew', 'sim', 'display',
             'llm', 'ingest', 'image_gen', 'world', 'polish', 'booklab',
             'director', 'actors', 'agent', 'export', 'config.py', 'i18n.py',
             'logger.py', 'main_gui.py']
SKIP_PARTS = {'__pycache__', '.venv', 'novelservices', 'packages', 'exports',
              'logs', 'screenshots'}

report: dict = {'steps': []}


def rec(name: str, ok: bool, detail: str = '') -> bool:
    report['steps'].append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(f'  {"✓" if ok else "✗"} {name}' + (f'  — {detail}' if detail else ''),
          flush=True)
    return ok


def resolve_chain(parts: list[str]):
    """从 `ft` 出发逐段取属性；返回 `(取值, 失败段)`。

    ⚠ 第一段要先试着**导入同名子模块** —— 否则会误报：
      `ft.canvas` 在**没导入 `flet.canvas` 时取不到**，而
      `import flet.canvas as fcv` 一旦执行过，`canvas` 就挂到了 `flet` 包上
      （`gui/app_flet.py` 第 43 行正是这么导入的）。
      第一版没这一步，于是把 `ft.canvas.Canvas` 报成了错 —— **判据错、代码没错**，
      这种误报比漏报更坏：它会让人去改一个**根本不存在的毛病**。
    
        English:
    Walk attributes segment by segment starting from `ft`; return `(value, failed_segment)`.
        ⚠ For the first segment, first try to **import the submodule of the same name** -- otherwise it will falsely report:
          `ft.canvas` **cannot be resolved when `flet.canvas` has not been imported**, but
          once `import flet.canvas as fcv` has executed, `canvas` is attached to the `flet` package
          (`gui/app_flet.py` line 43 imports it exactly this way).
          The first version lacked this step, so it reported `ft.canvas.Canvas` as an error -- **the check was wrong, the code was not**;
          this kind of false positive is worse than a false negative: it makes people go fix a **nonexistent problem**.
    """
    obj = ft
    for i, p in enumerate(parts):
        if not hasattr(obj, p) and i == 0:
            try:
                import importlib
                importlib.import_module(f'flet.{p}')
            except Exception:                                    # noqa: BLE001
                pass
        if not hasattr(obj, p):
            return None, p
        obj = getattr(obj, p)
    return obj, None


def main() -> int:
    print('  Flet API 验证（源码里的 `ft.xxx.yyy` 都要真的存在）')
    files: list[Path] = []
    for d in SCAN_DIRS:
        p = APP_DIR / d
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files += [f for f in p.rglob('*.py')
                      if not any(s in f.parts for s in SKIP_PARTS)]

    bad: list[tuple[str, int, str, str]] = []
    n_chains = 0
    for f in sorted(files):
        try:
            tree = ast.parse(f.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            # 把 `ft.a.b.c` 收成 ['a','b','c']
            # [EN] Collapse `ft.a.b.c` into ['a','b','c']
            parts: list[str] = []
            cur = node
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if not (isinstance(cur, ast.Name) and cur.id == 'ft'):
                continue
            parts.reverse()
            if len(parts) < 2:          # `ft.Icons` 这种只取一层的不查（常见且安全）
            # [EN] `ft.Icons`-style single-level lookups are not checked (common and safe)
                continue
            n_chains += 1
            _v, miss = resolve_chain(parts)
            if miss is not None:
                bad.append((str(f.relative_to(APP_DIR)), node.lineno,
                            'ft.' + '.'.join(parts), miss))

    report['bad'] = bad
    report['n_chains'] = n_chains
    rec(f'扫了 {len(files)} 个文件、{n_chains} 条 `ft.x.y` 属性链', n_chains > 0)
    rec('每一条都能在 Flet 里取到（不存在的一律报出来）', not bad,
        ('；'.join(f'{f}:{ln} {expr}（没有 `{m}`）' for f, ln, expr, m in bad[:6])
         if bad else ''))

    report['ok'] = all(s['ok'] for s in report['steps'])
    (OUT / 'ft_api_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n  共 {len(report["steps"])} 项断言，'
          f'{"全部通过" if report["ok"] else "有失败"}')
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
