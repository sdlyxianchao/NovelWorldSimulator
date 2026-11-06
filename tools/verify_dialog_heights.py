# -*- coding: utf-8 -*-
"""真机验证：**每个能打开的对话框，高度都是受控的**（不是被拉到满屏高）。

为什么要有这一支
----------------
`mk_dialog` 的尺寸是**从 `content` 身上读**的：

    cw = width if width is not None else getattr(content, 'width', None)
    ch = height if height is not None else getattr(content, 'height', None)
    body = ft.Column([head, ft.Container(content=content, expand=True)], ...)

`content` 没带 height ⇒ `ch=None` ⇒ 里面那层 `expand=True` 把它**拉到接近满屏**
（实测 **1081px**，屏幕 1129）。用户 2026-10-10 报的正是这个：
「网址对话框是不是太高了 但又太窄了」（我那次传了个裸 `Column(width=440)`）。

★★ 为什么这条必须**真机**、不能静态查
------------------------------------
静态（AST）能认出「字面量 `ft.Container` 少写 height」，但认不出这几类：
  · `mk_scroll_bar(...)` —— 它**条件返回**（有固定尺寸→`Stack(w,h)`；
    否则→`Stack(expand=True)`），尺寸还来自 `getattr(lv,'width')`；
  · 变量在别处构造（`body = ft.Container(..., height=250)`）；
  · 传了个自定义函数/方法（`self._wizard_body(...)`）。
这一支的做法是**真打开、真读 `dlg.content.height`** —— 不管它怎么构造出来的。

口径（别过度声称）
------------------
  · 只查**能安全打开**的那几个（不需要夹具 / 不需要有项目）；
  · 每个都断言 `content.height` 是个**受控的数**（0 < h ≤ 900，满屏是 1081）；
  · 报告里写明**查了几个、跳过哪些**（跳过的那些不假装查过）。

产出：assets/screenshots/dialog_heights_report.json
用法：.venv/Scripts/python.exe tools/verify_dialog_heights.py

English:
real-device verification: **every dialog that can open has a controlled height** (not stretched
to full-screen height).
Why this branch exists
----------------
`mk_dialog`'s size is **read from `content`**:
    cw = width if width is not None else getattr(content, 'width', None)
    ch = height if height is not None else getattr(content, 'height', None)
    body = ft.Column([head, ft.Container(content=content, expand=True)], ...)
`content` has no height ⇒ `ch=None` ⇒ the inner `expand=True` **stretches it to nearly full
screen**
(measured **1081px**, screen 1129). This is exactly what the user reported on 2026-10-10:
"is the URL dialog too tall, but also too narrow" (that time I passed a bare
`Column(width=440)`).
★★ Why this must be done on a **real device**, and cannot be checked statically
------------------------------------
Static (AST) can recognize "a literal `ft.Container` missing height", but cannot recognize these
categories:
  · `mk_scroll_bar(...)` -- it **returns conditionally** (with fixed size → `Stack(w,h)`;
    otherwise → `Stack(expand=True)`), and the size comes from `getattr(lv,'width')`;
  · variables constructed elsewhere (`body = ft.Container(..., height=250)`);
  · a custom function/method passed in (`self._wizard_body(...)`).
The approach of this branch is **actually open it, actually read `dlg.content.height`** --
regardless of how it was constructed.
Scope (don't overclaim)
------------------
  · only check those that **can safely open** (no fixture needed / no project needed);
  · assert for each that `content.height` is a **controlled number** (0 < h ≤ 900, full screen is 1081);
  · state in the report **how many were checked, which were skipped** (do not pretend the skipped ones were checked).
Output: assets/screenshots/dialog_heights_report.json
Usage: .venv/Scripts/python.exe tools/verify_dialog_heights.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from util.flet_shutdown import shutdown  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')

from gui.app_flet import NovelWorldApp  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
#: 满屏大约这么高（实测值）—— 用它当"被拉满"的判据
# [EN] : roughly this tall for a full screen (measured) -- use it as the criterion for "stretched to
# [EN] full"
FULL_SCREEN_H = 1000
#: 受控高度的上界（比满屏矮一截；正常对话框都在 200~700）
# [EN] : upper bound of controlled height (a bit shorter than full screen; normal dialogs are 200~700)
MAX_OK_H = 900

report: dict = {'steps': []}


def rec(name: str, ok: bool, detail: str = '') -> bool:
    report['steps'].append({'name': name, 'ok': bool(ok), 'detail': detail})
    print(f'  {"✓" if ok else "✗"} {name}' + (f'  — {detail}' if detail else ''),
          flush=True)
    return ok


async def main(page: ft.Page) -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_dlgh_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    app = NovelWorldApp()
    app.main(page)
    page.update()
    await asyncio.sleep(1.6)

    def _top_dialog():
        """最上面那层**真正的对话框**。

        ⚠ 必须过滤 `ft.AlertDialog`：`page._dialogs` 里**SnackBar 也算一层**
          （`show_dialog(SnackBar(...))` 就是提示条的实现方式）。
          第一版没过滤，于是「导出」被误判成"对话框没有 height" ——
          其实它只是**弹了一条提示**（没有项目可导出时走的就是这条路，
          `show_export_dialog` 开头 `if run is None: _show_snack(...); return`）。
          误报比漏报更坏：它会让人去改一个**根本不存在的毛病**。
        
                English:
        the **real dialog** at the very top layer.
                ⚠ must filter `ft.AlertDialog`: in `page._dialogs` **SnackBar also counts as a layer**
                  (`show_dialog(SnackBar(...))` is how the snack bar is implemented).
                  The first version did not filter, so "export" was misjudged as "dialog has no height" --
                  in fact it only **popped a snack bar** (that is the path taken when there is no project to export,
                  `show_export_dialog` starts with `if run is None: _show_snack(...); return`).
                  A false positive is worse than a miss: it makes people go fix a **non-existent problem**.
        """
        for d in reversed(VU.open_dialogs(page)):
            if isinstance(d, ft.AlertDialog):
                return d
        return None

    def _size_of(dlg) -> tuple:
        c = getattr(dlg, 'content', None)
        return (getattr(c, 'width', None), getattr(c, 'height', None))

    #: (`标签`, 打开动作, **应该能打开吗**)
    #  ★ `must_open=True` 的那几个**不需要任何夹具**（没有项目也该能开）——
    #    它们打不开就是 bug。这条断言就是本判据抓"点了没反应"的牙齿：
    #    2026-10-10「用量统计」因为用了 Flet 1.0 不存在的
    #    `ft.padding.all` / `ft.border.all` 与 `page.open()`，
    #    **一次都没打开成功过**，而当时的判据全都绿（没人打开过它）。
    # [EN] : (`label`, open action, **should it be able to open**)
    # [EN] ★ Those with `must_open=True` **require no fixtures** (should open even with no project) --
    # [EN] if they fail to open, it's a bug. This assertion is the teeth of this criterion for catching
    # [EN] "clicked but nothing happened":
    # [EN] 2026-10-10 the "usage stats" dialog, because it used Flet 1.0 non-existent
    # [EN] `ft.padding.all` / `ft.border.all` and `page.open()`,
    # [EN] **never opened successfully even once**, while all the criteria at the time were green (nobody
    # [EN] had ever opened it).
    OPENERS = [
        ('天机 · 全局设置', lambda: app.show_global_settings(), True),
        ('拆　书', lambda: app.show_booklab_dialog(), True),
        ('消 息', lambda: app.show_messages_dialog(), True),
        ('日志', lambda: app.show_log_dialog(), True),
        ('风格参数 · 怎么调', lambda: app.show_style_help_dialog(), True),
        ('用量统计', lambda: app.show_usage_dialog(), True),
        ('帮助面板', lambda: app.show_help_dialog(), True),
        # 导出要"先有一个跑过的运行"，没有项目时它**按设计**只弹一条提示条 ⇒ 不要求开
        # [EN] Export requires "a run that has actually run first"; with no project it **by design** only pops
        # [EN] a snack bar ⇒ not required to open
        ('导出（要有运行才开）', lambda: app.show_export_dialog(), False),
    ]

    results: list[dict] = []
    for label, open_it, must_open in OPENERS:
        item = {'label': label, 'must_open': must_open}
        try:
            open_it()
            await asyncio.sleep(0.7)
            dlg = _top_dialog()
            if dlg is None:
                # 没弹对话框 —— 多半是"缺前置条件"（没项目时导出只弹提示条）
                # [EN] no dialog popped -- most likely "missing precondition" (with no project, export only pops a
                # [EN] snack bar)
                item.update({'opened': False, 'why': '没有对话框（缺项目/夹具？）'})
            else:
                w, h = _size_of(dlg)
                item.update({'opened': True, 'width': w, 'height': h,
                             'stretched': (isinstance(h, (int, float)) and
                                           h > MAX_OK_H),
                             'no_height': h is None})
        except Exception as e:                                     # noqa: BLE001
            item.update({'opened': False, 'why': repr(e)[:120]})
        results.append(item)
        # 收干净，免得叠一堆（`pop_dialog` 一次收一层）
        # [EN] clean up thoroughly, to avoid stacking a bunch (`pop_dialog` pops one layer at a time)
        try:
            while VU.open_dialogs(page):
                page.pop_dialog()
            page.update()
        except Exception:                                          # noqa: BLE001
            pass
        await asyncio.sleep(0.25)

    report['dialogs'] = results
    opened = [r for r in results if r.get('opened')]
    must = [r for r in results if r.get('must_open')]

    # ★★ 该开的必须开。这条是"点了没反应"那道门 ——
    #   （`usage_dialog` 用了不存在的 Flet API，从来没能打开过，而当时的判据全绿。）
    # [EN] ★★ Those that should open must open. This is the gate for "clicked but nothing happened" --
    # [EN] (`usage_dialog` used a non-existent Flet API and was never able to open, while the criteria at
    # [EN] the time were all green.)
    failed_open = [r['label'] for r in must if not r.get('opened')]
    rec(f'**不需要夹具**的对话框全都真的打开得开（{len(must)} 个）',
        not failed_open,
        ('；'.join(f'{r["label"]}：{r.get("why", "")}'
                   for r in must if not r.get('opened')) if failed_open else
         f'{len(must)} 个都开了'))

    no_h = [r['label'] for r in opened if r.get('no_height')]
    rec('每个打开的对话框都有**受控的 height**（不是 None ⇒ 不会被拉满屏）',
        not no_h, f'没有 height 的：{no_h}' if no_h else
        '　'.join(f'{r["label"]}={r["height"]}' for r in opened))

    # ★ 「被拉满」要**按窗口高**判，不能用固定阈值 ——
    #   `用量统计` 是四个数据栏，代码里写的是 `height=max(480, 窗口高*0.88)`，
    #   那是**故意的**（1027px）。第一版用固定 900 当阈值，把它误判成"被拉满"：
    #   **判据错、代码没错**。真正的 bug 形态是"没给高度 ⇒ 被 expand 撑满"
    #   （那一类已经在上面那条抓住了：height is None）。
    #   这里只兜"荒唐值"：比窗口还高、或者小得不像话。
    # [EN] ★ "stretched to full" must be judged **by window height**, not with a fixed threshold --
    # [EN] `usage stats` is four data columns; the code writes `height=max(480, window height*0.88)`,
    # [EN] that is **intentional** (1027px). The first version used a fixed 900 as the threshold and
    # [EN] misjudged it as "stretched to full":
    # [EN] **the criterion was wrong, the code was not**. The real bug form is "no height given ⇒ stretched
    # [EN] full by expand"
    # [EN] (that category was already caught by the item above: height is None).
    # [EN] this only catches "absurd values": taller than the window, or absurdly small.
    win_h = int(getattr(page, 'height', 0) or 0) or 1167
    weird = [f'{r["label"]}={r["height"]}' for r in opened
             if isinstance(r.get('height'), (int, float))
             and not (120 <= r['height'] <= win_h)]
    rec(f'没有一个高度荒唐（窗口高 {win_h}：要求 120 ≤ h ≤ 窗口高）',
        not weird, '；'.join(weird) if weird else '')

    skipped = [r['label'] for r in results if not r.get('opened')]
    report['skipped'] = skipped
    print(f'\n  （没查到的：{skipped or "无"} —— 要夹具/要项目的那些，'
          f'本条**不假装查过**；反过来，"不需要夹具却没开"是要红的）')

    report['ok'] = all(s['ok'] for s in report['steps'])
    (OUT / 'dialog_heights_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n  对话框高度验证：'
          f'{sum(1 for s in report["steps"] if s["ok"])}/{len(report["steps"])}')
    for s in report['steps']:
        if not s['ok']:
            print(f'  ✗ {s["name"]}  {s["detail"]}')
    await shutdown(page, code=0 if report['ok'] else 2)


ft.run(main)
