# -*- coding: utf-8 -*-
"""真机验证：运行界面「默认留空 + 组件不留空隙」。

校验：
  1. 不含任何编造数据（主角 / 阿枝 / 第3天 / 节点 N07 / 前台 4 / 导演 · 运行中 / 临河茶肆 …）
  2. 叙事区与命令栏之间**没有大片空白**（实测像素间距 < 30px）
  3. 空项目下叙事区显示占位提示

**量测用的是纯色背景 + 合成色**：面板现在是半透明的，水墨背景会让
「找某一种颜色的连续段」失效。详见 tools/verify_ui_common.py。

产出：assets/screenshots/main_empty.png + main_report.json

English:
Real-device verification: the run UI "defaults to empty + components leave no gaps".
Validation:
  2. **No large blank area** between the narrative area and the command bar (measured pixel gap < 30px)
  3. The narrative area shows a placeholder hint when the project is empty
**Measurement uses a solid-color background + synthesized colors**: the panel is now
translucent, and the ink-wash background will make
"find a contiguous run of a certain color" fail. See tools/verify_ui_common.py for details.
Output: assets/screenshots/main_empty.png + main_report.json
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft  # noqa: E402
from util.flet_shutdown import shutdown, exit_now  # noqa: E402
from PIL import Image  # noqa: E402
import verify_ui_common as VU  # noqa: E402
VU.redirect_env_writes()

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')
# ★ 命令行现在**默认不显示**（`HIDE_COMMAND_BAR`，2026-10-11）——
#   但这一支测的是「叙事区与命令栏之间没有大片空白」，所以这里
#   **显式把命令行打开**，判据的含义不变；默认不显示那件事由
#   `tools/verify_font_settings.py` 的 B 组管。
# [EN] ★ The command bar is now **hidden by default** (`HIDE_COMMAND_BAR`, 2026-10-11) ——
# [EN] but this script checks "no large blank between the narrative area and the command bar",
# [EN] so it **explicitly turns the command bar on** to keep the criterion's meaning; the
# [EN] "hidden by default" part is covered by group B of `tools/verify_font_settings.py`.
CFG.set('HIDE_COMMAND_BAR', 'false')
# 本脚本会启动 GUI → 能力校验 → `CFG.save()`；不拦住就会把上面这些
# 测试值写进用户的真实 `.env`（NWS_ENV_SINK 只在并行回归里由父进程给）。
# [EN] This script starts the GUI -> capability check -> `CFG.save()`; without blocking it the
# [EN] test values above get written into the user's real `.env` (NWS_ENV_SINK is only supplied
# [EN] by the parent process during parallel regression).
import os  # noqa: E402
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

VU.patch_flat_background()          # 必须在构建界面之前：纯色背景，量测才确定
# [EN] Must be before building the UI: solid-color background, measurement is only deterministic then

from gui.app_flet import NovelWorldApp, HEADER_H  # noqa: E402
from store.project import Project  # noqa: E402
from i18n import set_lang  # noqa: E402
set_lang(_lang)
SUFFIX = '' if _lang == 'zh' else f'_{_lang}'

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

# 这些是「绝对不该出现在空运行界面」的编造数据
# [EN] These are fabricated data that "absolutely must not appear in the empty-run UI"
FORBIDDEN = ['主角', '阿枝', '掌柜', '伙计', '临河茶肆', '第3天', '戌时',
             '节点 N07', '破绽', '张力 0.6', '事件 15', '前台 4', '后台 3',
             '导演 · 运行中', '雨脚敲着檐瓦', '小虐·轻松', 'N07/12']


def walk(ctrl, out: list):
    if ctrl is None:
        return
    out.append(ctrl)
    for attr in ('controls', 'content', 'actions', 'title'):
        v = getattr(ctrl, attr, None)
        if isinstance(v, list):
            for c in v:
                walk(c, out)
        elif v is not None and hasattr(v, '__class__'):
            walk(v, out)


def all_texts(page) -> list[str]:
    out: list = []
    for c in page.controls:
        walk(c, out)
    vals = []
    for c in out:
        if isinstance(c, ft.Text) and c.value:
            vals.append(str(c.value))
        # TextField 的 value / hint_text 也算可见文本
        # [EN] TextField's value / hint_text also count as visible text
        if isinstance(c, ft.TextField):
            for a in ('value', 'hint_text'):
                v = getattr(c, a, None)
                if v:
                    vals.append(str(v))
    return vals


def find_new_round_btn(page):
    """运行界面右上角那个「📖 起　笔」按钮（**唯一能开跑的入口**）。
        English:
    The "📖 起 笔" button in the top-right corner of the run UI (**the one and only entry point that
    can start a run**).
    """
    out: list = []
    for c in page.controls:
        walk(c, out)
    for c in out:
        if type(c).__name__ == 'FilledButton':
            v = getattr(c, 'content', '')
            v = v if isinstance(v, str) else getattr(v, 'value', '')
            if '起　笔' in str(v) or 'Pen to paper' in str(v):
                return c
    return None


async def main(page: ft.Page):
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    report: dict = {}
    # ★★★ 2026-10-17 修：`isolate_projects_dir()` 返回的是**换之前的老值**
    #   （`.env` 的 `DEFAULT_PROJECTS_DIR`），不是新目录 ——
    #   原来拼上夹具名 ⇒ 每次都往**用户真实项目目录**里写一个「主界面留空验证」。
    #   ⇒ 返回值只作还原用，落点自己留。
    # [EN] ★★★ Fixed 2026-10-17: `isolate_projects_dir()` returns the **old value** (the `.env`
    # [EN] `DEFAULT_PROJECTS_DIR`), not the new directory -- appending the fixture name meant writing a
    # [EN] "主界面留空验证" into the **user's real project directory** every run.
    # [EN] => The return value is only for restoring; keep the landing path yourself.
    _seed = APP_DIR / 'assets' / 'screenshots' / '_proj' / '主界面留空验证'
    VU.isolate_projects_dir(_seed)
    proj_root = _seed / '主界面留空验证'
    try:
        # 造一个「刚建好、还没跑过」的项目
        # [EN] Create a project that is "just created, never run yet"
        proj_root.mkdir(parents=True, exist_ok=True)
        for sub in ('设定集', '优化后设定', '完整设定集导出'):
            (proj_root / sub).mkdir(exist_ok=True)
        proj = Project(proj_root, '主界面留空验证')
        proj.write_nwsproj()
        app.current_project = proj

        app.show_main_screen()
        page.update()
        await asyncio.sleep(0.9)

        texts = all_texts(page)
        report['all_texts'] = texts
        hits = [f for f in FORBIDDEN if any(f in t for t in texts)]
        report['forbidden_found'] = hits
        report['no_fake_data'] = not hits
        report['has_placeholder'] = any(
            ('尚未开始' in t) or ('Not started yet' in t) or ('has not started' in t)
            for t in texts)
        report['title'] = next((t for t in texts if t.startswith('【')), '')

        # ── 空态必须指向**唯一能开跑的那个入口**（2026-10-05 用户报的错）──
        # 老文案写的是「在下方输入命令开始推演」，可底部命令框只接了
        # help / status / settings，**开不了跑** —— 用户照着做，输入 help 没反应，
        # 跑来问「应该点起　笔还是输入命令」。两条判据把这类谎话钉住：
        #   ① 空态文案里要出现「起　笔」（英文 Pen to paper）；
        #   ② 界面上不许有任何一句话说"输入命令"就能开始。
        # [EN] ── The empty state must point to **the one and only entry point that can start a run** (bug
        # [EN] reported by user on 2026-10-05) ──
        # [EN] The old copy said "enter a command below to start the simulation", but the bottom command box
        # [EN] only wires up
        # [EN] help / status / settings, **it cannot start a run** —— the user followed it, typed help, got no
        # [EN] response,
        # [EN] and came asking "should I click 起　笔 or type a command". Two criteria nail down this kind of lie:
        # [EN] ① The empty-state copy must contain "起　笔" (English: Pen to paper);
        # [EN] ② The UI must not contain any sentence saying you can start by "typing a command".
        hint_texts = [t for t in texts if '尚未开始' in t or 'not started' in t.lower()]
        report['empty_hint'] = hint_texts
        report['empty_hint_points_to_btn'] = any(
            ('起　笔' in t) or ('Pen to paper' in t) for t in hint_texts)
        cmd_claims = [t for t in texts
                      if ('输入' in t and '命令' in t and '开始' in t)
                      or ('type a command' in t.lower() and 'begin' in t.lower())]
        report['command_start_claims'] = cmd_claims
        report['no_command_start_claim'] = not cmd_claims

        btn = find_new_round_btn(page)
        report['new_round_btn'] = (btn is not None,
                                   None if btn is None else bool(btn.disabled))
        report['new_round_btn_usable'] = btn is not None and not btn.disabled

        png = await page.take_screenshot()
        (OUT / f'main_empty{SUFFIX}.png').write_bytes(png)
        # 叙事区（面板色）与命令栏（输入框色）——两种颜色不同，可分别定位
        # [EN] Narrative area (panel color) and command bar (input box color) —— two different colors, can be
        # [EN] located separately
        gap, gdetail = VU.vertical_gap_between(png, VU.panel_rgb(), VU.field_rgb(),
                                               y_from=HEADER_H)
        im = VU.image_of(png)
        report['screen'] = list(im.size)
        report['measure'] = gdetail
        report['gap_px'] = gap
        report['gap_ok'] = 0 <= gap < 30

        report['ok'] = bool(report['no_fake_data'] and report['has_placeholder']
                            and report['gap_ok']
                            and report['empty_hint_points_to_btn']
                            and report['no_command_start_claim']
                            and report['new_round_btn_usable'])
    except Exception:
        import traceback
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        try:
            VU.safe_rmtree(proj_root, ignore_errors=True)
            report['cleaned'] = str(proj_root)
        except Exception as e:
            report['cleanup_error'] = str(e)
        (OUT / f'main_report{SUFFIX}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: v for k, v in report.items() if k != 'all_texts'},
                         ensure_ascii=False, indent=2))
        print('--- 界面可见文本 ---')
        for t in report.get('all_texts', []):
            print('   ', t[:70])
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` will throw
        # [EN] CancelledError
        # [EN] cancels this coroutine; the line `exit_now(...)` written after `await shutdown(page)`
        # [EN] **never executed** (exit code always 0 = false green). See `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report.get('ok') else 2)


ft.run(main)
