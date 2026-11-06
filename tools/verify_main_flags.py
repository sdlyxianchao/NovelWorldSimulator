# -*- coding: utf-8 -*-
"""真机验证：运行界面布局随「天机」里的全局开关自适应。

四个场景分别改 CFG（不落盘），重绘运行界面，检查：
  · 关掉的功能不再出现对应行，而是折成一行「已关闭：…」
  · story_day 才出现「暂停间隔」；开了夜间暂停才出现该行；AUTO_RUN_DAYS=0 不出现
  · 顶栏 flags 随开关变化
  · 全程无编造数据；叙事区与命令栏依然紧贴（间距 < 30px）

产出：assets/screenshots/flags_*.png + main_flags_report.json

English:
Real device verification: the runtime UI layout adapts to the global switch in "天机".
For the four scenarios, change CFG separately (without persisting to disk), redraw the runtime
UI, and check:
  · Disabled features no longer show their corresponding row, but are collapsed into a single row "已关闭：…"
  · "暂停间隔" only appears for story_day; that row only appears when night pause is enabled; it does not appear when AUTO_RUN_DAYS=0
  · The top bar flags change with the switches
  · No fabricated data throughout; the narrative area and the command bar remain tightly adjacent (spacing < 30px)
Output: assets/screenshots/flags_*.png + main_flags_report.json
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft  # noqa: E402
import os as _os
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

VU.patch_flat_background()          # 必须在构建界面之前：纯色背景，量测才确定
# [EN] Must be before building the interface: solid background, measurement is only determined after

from gui.app_flet import NovelWorldApp, HEADER_H  # noqa: E402
from store.project import Project  # noqa: E402
from i18n import set_lang  # noqa: E402
from util.flet_shutdown import shutdown, exit_now  # noqa: E402

set_lang('zh')
OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

FORBIDDEN = ['主角', '阿枝', '第3天', '节点 N07', '张力 0.6', '前台 4', '导演 · 运行中']


def walk(c, out, d=0):
    if c is None or d > 40:
        return
    out.append(c)
    for a in ('controls', 'content', 'actions', 'title'):
        v = getattr(c, a, None)
        if isinstance(v, list):
            for x in v:
                walk(x, out, d + 1)
        elif v is not None and hasattr(v, '__class__'):
            walk(v, out, d + 1)


def all_texts(page) -> list[str]:
    out: list = []
    for c in page.controls:
        walk(c, out)
    vals = []
    for c in out:
        if isinstance(c, ft.Text) and c.value:
            vals.append(str(c.value))
        if isinstance(c, ft.TextField):
            for a in ('value', 'hint_text'):
                v = getattr(c, a, None)
                if v:
                    vals.append(str(v))
    return vals


def gap_px(png: bytes, x: int) -> int:
    """叙事区与命令栏之间的垂直空白（纯色背景 + 合成色，见 verify_ui_common）。
        English:
    The vertical whitespace between the narrative area and the command bar (solid background +
    composite color, see verify_ui_common).
    """
    gap, _ = VU.vertical_gap_between(png, VU.panel_rgb(), VU.field_rgb(),
                                     y_from=HEADER_H)
    return gap


SCENARIOS = {
    'A_默认全开': {
        'DIRECTOR_ENABLED': 'true', 'COMPLIANCE_ENABLED': 'true',
        'EMBEDDING_PROVIDER': 'ollama', 'RUN_MODE': 'story',
        'PAUSE_AT_NIGHT': 'false', 'AUTO_RUN_DAYS': '1',
        'STORY_DAY_EVERY_DAYS': '3', 'TOKEN_BUDGET_PER_DAY': '500000',
        'DEBUG_MODE': 'false', 'COMPLIANCE_LEVEL': 'standard',
    },
    'B_全关': {
        'DIRECTOR_ENABLED': 'false', 'COMPLIANCE_ENABLED': 'false',
        'EMBEDDING_PROVIDER': 'none', 'RUN_MODE': 'story',
        'PAUSE_AT_NIGHT': 'false', 'AUTO_RUN_DAYS': '0',
        'TOKEN_BUDGET_PER_DAY': '0', 'DEBUG_MODE': 'false',
    },
    'C_story_day夜间自动': {
        'DIRECTOR_ENABLED': 'false', 'COMPLIANCE_ENABLED': 'true',
        'EMBEDDING_PROVIDER': 'local', 'RUN_MODE': 'story_day',
        'PAUSE_AT_NIGHT': 'true', 'AUTO_RUN_DAYS': '30',
        'STORY_DAY_EVERY_DAYS': '5', 'TOKEN_BUDGET_PER_DAY': '100000',
        'DEBUG_MODE': 'true', 'COMPLIANCE_LEVEL': 'relaxed',
    },
    'D_open模式': {
        'DIRECTOR_ENABLED': 'false', 'COMPLIANCE_ENABLED': 'true',
        'EMBEDDING_PROVIDER': 'api', 'RUN_MODE': 'open',
        'PAUSE_AT_NIGHT': 'false', 'AUTO_RUN_DAYS': '0',
        'TOKEN_BUDGET_PER_DAY': '0', 'DEBUG_MODE': 'false',
        'COMPLIANCE_LEVEL': 'strict',
    },
}

EXPECT = {
    # ⚠ 2026-10-12：「导演 · 未启动」那一行**被用户点名去掉了**
    #   （「导演这一样可以先去掉 没有特别的意义」）—— 它只在导演开着时出现，
    #   而那是**默认状态**，既不说明导演在干什么、也不随推演变化，白占一行。
    #   所以这一支的断言跟着改：**开着时不许出现那行**（防它悄悄回来），
    #   关掉时的「已关闭：导演」照旧要出现（那是"是你自己关的"，是另一件事）。
    # [EN] ⚠ 2026-10-12: the row "导演 · 未启动" was **named for removal by the user**
    # [EN] ("the director one can go for now, it has no particular meaning") -- it only appeared
    # [EN] when the director was on, which is the **default** state; it said nothing about what the
    # [EN] director was doing and never changed during a run, a wasted row.
    # [EN] So this branch's assertions change accordingly: **the row must not appear while it is
    # [EN] on** (guarding against it quietly coming back), and the "已关闭：导演" while it is off
    # [EN] still must appear (that one means "you turned it off yourself", a different thing).
    'A_默认全开': {
        'must': ['合规 · 标准', '记忆检索', 'ollama',
                 'Token 预算', '运行模式', '时间倍率', '心跳间隔', '走完故事',
                 '自动运行上限', '1 天'],
        'must_not': ['已关闭', '暂停间隔', '夜间暂停', '调试模式', '导演已关', '合规已关',
                     '导演 · 未启动', 'story', 'open'],
    },
    'B_全关': {
        'must': ['已关闭', '导演', '合规', '向量检索', '关闭（关键词退化）', '走完故事'],
        'must_not': ['合规 · 标准', '合规 · 严格', '合规 · 宽松',
                     'Token 预算', '调试模式', '暂停间隔', '自动运行上限',
                     '夜间暂停', '导演已关', '合规已关', 'story_day', 'story', 'open'],
    },
    'C_story_day夜间自动': {
        'must': ['暂停间隔', '5 天', '夜间暂停', '自动运行上限', '30 天',
                 '调试模式 · 已开', '合规 · 宽松', '定期暂停'],
        'must_not': ['合规 · 标准', '合规 · 严格', 'story_day', 'story'],
    },
    'D_open模式': {
        'must': ['不限期限', '合规 · 严格', '已关闭：导演'],
        'must_not': ['暂停间隔', '自动运行上限', '夜间暂停',
                     'Token 预算', '调试模式', 'open', 'story_day', 'story'],
    },
}


async def main(page: ft.Page):
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    report: dict = {'scenarios': {}}
    # ★★★ 2026-10-17 修：`isolate_projects_dir()` 返回的是**换之前的老值**
    #   （`.env` 的 `DEFAULT_PROJECTS_DIR`），不是新目录 ——
    #   原来拼上夹具名 ⇒ 每次都往**用户真实项目目录**里写一个「开关自适应验证」。
    #   ⇒ 返回值只作还原用，落点自己留。
    # [EN] ★★★ Fixed 2026-10-17: `isolate_projects_dir()` returns the **old value** (the `.env`
    # [EN] `DEFAULT_PROJECTS_DIR`), not the new directory -- appending the fixture name meant writing a
    # [EN] "开关自适应验证" into the **user's real project directory** every run.
    # [EN] => The return value is only for restoring; keep the landing path yourself.
    _seed = APP_DIR / 'assets' / 'screenshots' / '_proj' / '开关自适应验证'
    VU.isolate_projects_dir(_seed)
    proj_root = _seed / '开关自适应验证'
    try:
        proj_root.mkdir(parents=True, exist_ok=True)
        (proj_root / '设定集').mkdir(exist_ok=True)
        proj = Project(proj_root, '开关自适应验证')
        proj.write_nwsproj()
        app.current_project = proj

        for name, flags in SCENARIOS.items():
            CFG.update(flags)
            app.show_main_screen()
            page.update()
            await asyncio.sleep(0.9)

            texts = all_texts(page)
            joined = '\n'.join(texts)
            exp = EXPECT[name]
            missing = [s for s in exp['must'] if s not in joined]
            leaked = [s for s in exp['must_not'] if s in joined]
            fake = [s for s in FORBIDDEN if s in joined]

            png = await page.take_screenshot()
            (OUT / f'flags_{name}.png').write_bytes(png)

            report['scenarios'][name] = {
                'flags': flags,
                'missing_expected': missing,
                'leaked_forbidden': leaked,
                'fake_data': fake,
                'gap_px': gap_px(png, page.width // 2),
                'header': next((t for t in texts if t.startswith('【')), ''),
                'header_flags': next((t for t in texts if t.startswith('· ')), ''),
                'sys_lines': [t for t in texts if '已关闭' in t or '导演' in t
                              or '合规' in t or '调试' in t],
                'ok': not missing and not leaked and not fake,
            }
        # ── 场景 E：把窗口压到最小尺寸，确认多出来的「运行配置」面板不把侧栏顶出可视区 ──
        # [EN] ── Scenario E: shrink the window to its minimum size, confirm the extra "Run Config" panel does
        # [EN] not push the sidebar out of the visible area ──
        try:
            page.window.width = 1100
            page.window.height = 700
            page.update()
            await asyncio.sleep(1.4)
            app.show_main_screen()
            page.update()
            await asyncio.sleep(1.0)
            texts = all_texts(page)
            joined = '\n'.join(texts)
            need = ['时间', '运行配置', '小地图', '风格控制', '在场人物', '剧情', '系统']
            png = await page.take_screenshot()
            (OUT / 'flags_E_小窗口.png').write_bytes(png)
            im = Image.open(__import__('io').BytesIO(png)).convert('RGB')
            from collections import Counter
            px = list(im.resize((160, 100)).getdata())
            top_ratio = Counter(px).most_common(1)[0][1] / len(px)
            report['small_window'] = {
                'size': list(im.size),
                'missing_panels': [n for n in need if n not in joined],
                'dominant_ratio': round(top_ratio, 3),
                'not_blank': top_ratio < 0.95,
            }
            report['small_window']['ok'] = (
                not report['small_window']['missing_panels']
                and report['small_window']['not_blank'])
        except Exception as e:
            report['small_window'] = {'ok': False, 'error': repr(e)}

        # 收尾把配置还原成场景 A，避免影响后续人工查看
        # [EN] At the end, restore the config to scenario A to avoid affecting subsequent manual inspection
        CFG.update(SCENARIOS['A_默认全开'])
        report['ok'] = (all(v['ok'] and 0 <= v['gap_px'] < 30
                            for v in report['scenarios'].values())
                        and report.get('small_window', {}).get('ok', False))
    except Exception:
        import traceback
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        VU.safe_rmtree(proj_root, ignore_errors=True)
        (OUT / 'main_flags_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` will raise
        # [EN] CancelledError
        # [EN] Cancel this coroutine, written on the line after `await shutdown(page)` as `exit_now(...)`
        # [EN] **Never executed** (exit code is always 0 = false green). See `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report.get('ok') else 2)


ft.run(main)
