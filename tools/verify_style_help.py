# -*- coding: utf-8 -*-
"""真机验证：书斋「风格参数」旁边的小「?」+ 参数说明对话框（v1.29）。

用户要的是：「在风格参数旁边加一个小问号，点了之后弹出一个提示框，
里面包含一些常见类型小说的参数说明」。

所以这里查三件事：
  ① 那个「?」**真的画在屏幕上**（控件树里有不算数 —— 这项目栽过好几次）；
  ② 点它**真的弹出对话框**，而且里面**逐项**讲清了八个参数 + 常见类型的建议档；
  ③ 说明里的文案**中英都有**（`STYLE_HELP_ITEMS` 是**动态取值**，
     `i18n_check` 扫不到字面量，全靠 `i18n.py` 里手工登记 —— 漏一条英文界面就冒中文）。

判据里带像素：切到「风格控制」页 → 把「?」临时涂成品红 `#ff00ff`
（**只动颜色不动几何**，量完还原）→ 数品红像素。这是本项目"新加一块 UI"的标准做法。

跑法：
    .venv\\Scripts\\python.exe tools/verify_style_help.py
产出：
    assets/screenshots/style_help_shuzhai.png / style_help_dialog.png
    assets/screenshots/style_help_report.json

English:
Real device verification: the small "?" next to "Style Parameters" in Study + the parameter help
dialog (v1.29).
What the user wants: "add a small question mark next to the style parameters, and when clicked
pop up a tooltip
containing parameter explanations for some common novel genres".
So check three things here:
  ① That "?" is **actually drawn on screen** (being in the widget tree does not count -- this project has been burned several times);
  ② Clicking it **actually pops up the dialog**, and inside it **item by item** explains the eight parameters + suggested levels for common genres;
  ③ The copy in the help has **both Chinese and English** (`STYLE_HELP_ITEMS` is a **dynamic lookup**,
     `i18n_check` cannot scan for the literals, it all relies on manual registration in `i18n.py` -- miss one and Chinese shows up in the English UI).
The criteria involve pixels: switch to the "Style Control" page -> temporarily paint the "?"
magenta `#ff00ff`
(**only color, not geometry**; restore after measuring) -> count magenta pixels. This is the
project's standard way of "adding a new piece of UI".
How to run:
    .venv\\Scripts\\python.exe tools/verify_style_help.py
Outputs:
    assets/screenshots/style_help_shuzhai.png / style_help_dialog.png
    assets/screenshots/style_help_report.json
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
from util.flet_shutdown import shutdown, exit_now  # noqa: E402
from PIL import Image  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('LANGUAGE', 'zh')

from gui.app_flet import (NovelWorldApp, STYLE_HELP_ITEMS,  # noqa: E402
                          STYLE_HELP_GENRES, mk_help_dot)
# ★ 2026-10-30：书斋加了「运行」页 ⇒ 「风格控制」不再是第 1 个页签。
#   下标一律走常量（`TAB_BOOK_STYLEPANEL`），**不写死数字** —— 写死的那次
#   就是这里（`selected_index = 1`），页序一动，「?」画在另一页上，像素判据直接红。
# [EN] ★ 2026-10-30: the Study gained a "Run" tab, so "Style Control" is no longer tab #1.
# [EN] Always use `TAB_BOOK_STYLEPANEL`, never a hardcoded index -- that hardcoded `1` was
# [EN] exactly what went red when the tab order changed.
from store.project import Project  # noqa: E402
from i18n import set_lang, t  # noqa: E402
set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

MAGENTA = (0xff, 0x00, 0xff)
# 界面上那八个滑杆的标签（书斋 · 风格控制）—— 和 STYLE_HELP_ITEMS 的键**必须一致**
# [EN] The eight slider labels in the UI (Study · Style Control) -- **must** match the keys of
# [EN] STYLE_HELP_ITEMS
SLIDER_LABELS = ('虐心程度', '幽默度', '爽点密度', '感情线占比',
                 '悬念密度', '世界观展开', '人物智商')


def count_color(png: Path, rgb, tol: int = 30) -> int:
    im = Image.open(png).convert('RGB')
    px = im.load()
    W, H = im.size
    n = 0
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            c = px[x, y]
            if all(abs(c[i] - rgb[i]) <= tol for i in range(3)):
                n += 1
    return n


async def main(page: ft.Page):
    VU.patch_flat_background()
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    tmp = Path(tempfile.mkdtemp(prefix='nws_sh_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    items: list = []

    def ok(name: str, cond, detail: str = '') -> bool:
        items.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
        if not cond:
            print(f'FAIL  {name}   [{detail}]')
        return bool(cond)

    async def shot(fname: str) -> Path:
        page.update()
        await asyncio.sleep(0.6)
        p = OUT / fname
        p.write_bytes(await page.take_screenshot())
        return p

    report: dict = {}
    try:
        # ── ① 数据与文案 ──
        # [EN] ── ① Data and copy ──
        names = [it[0] for it in STYLE_HELP_ITEMS]
        ok('八项参数说明齐了', len(STYLE_HELP_ITEMS) == 8, str(len(STYLE_HELP_ITEMS)))
        ok('参数名和书斋里的滑杆标签一致（同一份字面量）',
           set(names) == set(SLIDER_LABELS) | {'节奏感'},
           f'{names}')
        ok('每项都有「管什么 / 低↔高 / 常见落点」三段',
           all(len(it) == 4 and all(str(x).strip() for x in it)
               for it in STYLE_HELP_ITEMS))
        ok('常见类型的建议档 ≥ 6 类', len(STYLE_HELP_GENRES) >= 6,
           str(len(STYLE_HELP_GENRES)))
        bad = [n for n, _note, vals in STYLE_HELP_GENRES
               if len([v for v in vals.split('｜') if v.strip()]) != 8]
        ok('每个类型的建议档都是**八个数**（顺序说明不能骗人）', not bad, str(bad))
        # 动态取值的文案：i18n_check 扫不到，这里逐条查英文
        # [EN] Dynamically resolved copy: i18n_check cannot scan it, so check each English entry here one by
        # [EN] one
        set_lang('en')
        miss = []
        for it in STYLE_HELP_ITEMS:
            miss += [s for s in it if t(str(s)) == str(s)]
        for it in STYLE_HELP_GENRES:
            miss += [s for s in it if t(str(s)) == str(s)]
        en_title = t('风格参数 · 怎么调')
        set_lang('zh')
        ok('说明里的文案中英都有（动态取值，靠手工登记）', not miss, str(miss))
        ok('英文界面下对话框标题是英文', 'Style' in en_title, en_title)

        # ── ② 真机：书斋 · 风格控制 页 ──
        # [EN] ── ② Real device: Study · Style Control page ──
        proj = Project.create_new(CFG.projects_dir(), '风格说明验证', genre='玄幻修仙')
        proj.settings_dir.mkdir(parents=True, exist_ok=True)
        (proj.settings_dir / '人物.yaml').write_text(
            '- 姓名: 主角\n  身份: 茶肆掌柜\n', encoding='utf-8')
        app._activate_project(proj)

        dlg = app.show_project_settings()
        page.update()
        await asyncio.sleep(0.7)
        ok('书斋对话框真的打开了',
           dlg is not None and bool(getattr(dlg, 'open', False)))

        dot = VU.find_help_dot(dlg)
        ok('「风格参数」旁边那个「?」在控件树里', dot is not None)
        if dot is not None:
            ok('「?」是可点的（on_click 可调用）', callable(dot.on_click))
            ok('「?」是小尺寸圆点（18×18，不是 48px 的 IconButton）',
               (dot.width, dot.height) == (18, 18), f'{dot.width}×{dot.height}')

        # 切到「风格控制」页（第 2 个选项卡）—— 不切的话它根本不会被绘制
        # [EN] Switch to the "Style Control" page (the 2nd tab) -- otherwise it will not be drawn at all
        tabs = next((c for c in VU.walk(dlg) if isinstance(c, ft.Tabs)), None)
        ok('找到书斋的选项卡控件', tabs is not None)
        if tabs is not None:
            tabs.selected_index = NovelWorldApp.TAB_BOOK_STYLEPANEL
            page.update()
            await asyncio.sleep(0.6)

        # 像素：把「?」涂成品红，确认它**真的画出来了**（不是被裁掉/藏在滚动区外）
        # [EN] Pixels: paint the "?" magenta, confirm it is **actually drawn** (not clipped / hidden outside
        # [EN] the scroll area)
        n_mag = 0
        if dot is not None:
            dot.bgcolor = '#ff00ff'
            png = await shot('style_help_shuzhai.png')
            n_mag = count_color(png, MAGENTA)
            dot.bgcolor = None      # 还原（只动过颜色，没动几何）
            # [EN] Restore (only color was changed, geometry untouched)
            page.update()
        ok('像素：「?」真的画在屏幕上了（标记色法数得到品红）',
           n_mag >= 8, f'品红像素 {n_mag}')
        report['magenta_px'] = n_mag

        # ── ③ 点开说明对话框 ──
        # [EN] ── ③ Open the help dialog ──
        n_before = len(VU.open_dialogs(page))
        if dot is not None:
            dot.on_click(None)
        page.update()
        await asyncio.sleep(0.9)
        hd = [d for d in VU.open_dialogs(page)
              if any('风格参数' in x for x in VU.all_texts(d))]
        ok('点「?」真的弹出说明对话框', bool(hd),
           f'{n_before} → {len(VU.open_dialogs(page))}')
        hdlg = hd[-1] if hd else None
        texts = VU.all_texts(hdlg) if hdlg else []
        joined = ' | '.join(texts)
        ok('对话框标题是「风格参数 · 怎么调」',
           any('风格参数 · 怎么调' in x for x in texts), joined[:80])
        missing_p = [n for n in names if n not in joined]
        ok('正文逐项讲了八个参数', not missing_p, str(missing_p))
        missing_g = [g[0] for g in STYLE_HELP_GENRES if g[0] not in joined]
        ok('正文给了常见类型的建议档', len(missing_g) <= 2, str(missing_g))
        ok('正文说明「这些是起点不是规矩」并指出改值的地方',
           any('起点' in x and '起　笔' in x for x in texts))
        ok('正文有那行「顺序就是上面八项」的对照说明',
           any('顺序就是上面八项' in x for x in texts))

        hpng = await shot('style_help_dialog.png')
        h_im = Image.open(hpng).convert('RGB')
        hp = h_im.load()
        dark = sum(1 for y in range(0, h_im.size[1], 3)
                   for x in range(0, h_im.size[0], 3) if sum(hp[x, y]) < 430)
        ok('像素：说明框里有大量文字墨迹', dark > 400, str(dark))
        # 这个说明框里**没有任何输入框**（全是文字块），所以不能用
        # `measure_input_boxes` 那套；直接量"纸面"的横向跨度：
        # 纯色背景下纸面很亮(≈666)、背景很暗(≈182)，一量就分开。
        # [EN] This help box has **no input boxes** (all text blocks), so the
        # [EN] `measure_input_boxes` approach cannot be used; directly measure the horizontal span of the
        # [EN] "paper":
        # [EN] On a solid-color background the paper is very bright (≈666) and the background is very dark
        # [EN] (≈182), so a single measurement separates them.
        xs = [x for y in range(0, h_im.size[1], 3)
              for x in range(0, h_im.size[0], 3) if sum(hp[x, y]) > 500]
        w = (max(xs) - min(xs)) if xs else 0
        ok('像素：对话框纸面是有界的（画出来了、且没撑满整屏）',
           600 <= w < h_im.size[0] - 8, f'纸面跨度 {w}px / 屏幕 {h_im.size[0]}px')
        report['paper_w'] = w

        # 关掉说明框 → 书斋还在
        # [EN] Close the help dialog -> Study is still there
        page.pop_dialog()
        page.update()
        await asyncio.sleep(0.5)
        ok('关掉说明框后书斋还在（没把两层的栈搞乱）',
           bool(dlg is not None and getattr(dlg, 'open', False)),
           str([bool(getattr(d, 'open', False)) for d in VU.open_dialogs(page)]))

        # ── ④ 其它小节标题不受影响（mk_section 改了形状）──
        # [EN] ── ④ Other section titles are unaffected (mk_section changed shape) ──
        secs = [c for c in VU.walk(dlg)
                if isinstance(c, ft.Container)
                and isinstance(getattr(c, 'content', None), ft.Row)]
        ok('小节标题（含没有「?」的）仍然渲染成一行', len(secs) >= 3, str(len(secs)))
        # ⚠ 2026-10-14 修：原来直接取 `c.content.controls[-1]` —— 只要有一个
        #   **空 Row**（`controls == []`）就 `IndexError`，而它抛在**收尾段**，
        #   于是"23/23 全绿"却让脚本以 exit=2 退出（看着像判据失败）。
        #   ⇒ 先判非空。这一类"判据自己崩了"和"判据变红"必须分得开。
        # [EN] ⚠ Fixed 2026-10-14: it used to index `c.content.controls[-1]` directly --
        # [EN] a single **empty Row** (`controls == []`) raises `IndexError`, and it throws in the
        # [EN] **wrap-up** section, so "23/23 all green" still exits with code 2 (looking like a
        # [EN] criterion failure). => Check for non-empty first. "The criterion itself crashed" and
        # [EN] "the criterion went red" must be kept apart.
        ok('只有「风格参数」那一行带「?」（其余小节没有）',
           len([c for c in secs
                if c.content.controls
                and isinstance(c.content.controls[-1], ft.Container)
                and getattr(c.content.controls[-1], 'width', None) == 18]) == 1,
           str(len(secs)))

        report['ok'] = all(i['ok'] for i in items)
    except Exception:
        import traceback
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        report['items'] = items
        report['n_ok'] = sum(1 for i in items if i['ok'])
        report['n_all'] = len(items)
        (OUT / 'style_help_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        for it in items:
            print(f"{'OK  ' if it['ok'] else 'FAIL'}  {it['name']}"
                  + (f"   [{it['detail']}]" if it['detail'] else ''))
        print(f"\n风格参数说明验证：{report['n_ok']}/{report['n_all']}")
        if report.get('fatal'):
            print(report['fatal'])
        try:
            VU.safe_rmtree(tmp, ignore_errors=True)
        except Exception:
            pass
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` will throw
        # [EN] CancelledError
        # [EN] which cancels this coroutine; write it on the line `exit_now(...)` after `await shutdown(page)`
        # [EN] so it **never executed** (exit code is always 0 = false green). See
        # [EN] `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report.get('ok') else 2)


if __name__ == '__main__':
    ft.run(main)
