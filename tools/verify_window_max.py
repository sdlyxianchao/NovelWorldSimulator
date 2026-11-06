# -*- coding: utf-8 -*-
"""真机验证：**启动即最大化**（以及窗口被还原后能不能被拉回来）。

用户 2026-10-06 的原话走了一圈：
  「为何默认不全屏了？」→「我希望默认打开全屏才对」→
  **「我可能有的地方说错了 我是想默认最大化 不是默认全屏把屏幕都占满」**
所以最终判的是 `maximized`（铺满工作区、**任务栏留着**），不是 `full_screen`。
全屏是可选项，按 **F11** 自己切。

判据设计（★ 关键在 A2，它是**能红**的那条）：
  A1  启动 **2 秒内**窗口就是最大化的（0.35/0.9/1.8 三次里至少一次成了）；
  A2 ★★ 启动后 **2.0 秒**把最大化"还原"（模拟平台把它改回普通窗口），
      到 **3.4 秒**必须已经被**拉回最大化** —— 只有"重试一直到 3.2 秒"的
      实现才过得去；旧的两段重试（0.35/1.55）在这一刻一定是 False。
      ⚠ 这里**直接改 `maximized` 属性**，不走 F11 —— 走 F11 会被
      `_user_toggled_fullscreen` 记成"用户自己接管了"，那就不是被测那条路径了。
  A3  之后保持最大化（不会自己又还原）；
  A4  ★ 默认**不是全屏**（用户要的是最大化，别把任务栏盖掉）；
  A5  ★ 用户按过 F11 之后，启动兜底就收工（不跟他抢窗口状态）；
  B   F11 进/出全屏之后**仍是最大化**（不能按一下 F11 就变成小窗）。

跑法：.venv\\Scripts\\python.exe tools/verify_window_max.py
产出：assets/screenshots/window_max_verify.json / window_max_verify.png

English:
Real-machine verification: **maximized at startup** (and whether the window can be pulled back
after being restored).
The user's exact words from 2026-10-06 went full circle:
  "Why is it no longer fullscreen by default?" → "I want it to open fullscreen by default" →
  **"I may have misspoken somewhere. I want it maximized by default, not fullscreen covering the whole screen"**
So what's ultimately tested is `maximized` (fills the workspace, **taskbar stays visible**), not
`full_screen`.
Fullscreen is optional, toggle it yourself with **F11**.
Criteria design (★ the key is A2, it's the one that **can go red**):
  A1  Within **2 seconds** of startup the window is maximized (at least one of the three checks at 0.35/0.9/1.8 succeeds);
  A2 ★★ At **2.0 seconds** after startup, "restore" the maximized state (the simulated platform changes it back to a normal window),
      by **3.4 seconds** it must already have been **pulled back to maximized** — only an implementation that "retries all the way to 3.2 seconds"
      passes; the old two-stage retry (0.35/1.55) is definitely False at this moment.
      ⚠ Here we **directly change the `maximized` property**, not via F11 — going through F11 would be
      recorded by `_user_toggled_fullscreen` as "the user took over themselves", which is not the path being tested.
  A3  Stays maximized afterward (doesn't restore itself);
  A4  ★ The default is **not fullscreen** (the user wants maximized, don't cover the taskbar);
  A5  ★ After the user has pressed F11, the startup fallback stops (doesn't fight them over window state);
  B   After F11 enters/exits fullscreen it's **still maximized** (pressing F11 once must not turn it into a small window).
How to run: .venv\\Scripts\\python.exe tools/verify_window_max.py
Output: assets/screenshots/window_max_verify.json / window_max_verify.png
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                        # noqa: E402
import verify_ui_common as VU                            # noqa: E402
from util.flet_shutdown import shutdown, exit_now        # noqa: E402

from config import CFG                                   # noqa: E402
CFG.set('MOCK_LLM', 'true')

from gui.app_flet import NovelWorldApp                   # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
VU.redirect_env_writes()

checks: list = []
report: dict = {}


def ok(name: str, cond, detail='') -> bool:
    checks.append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:200]})
    return bool(cond)


class _Key:
    """假键盘事件：`_on_keyboard` 只读 `.key`。
        English:
    Fake keyboard event: `_on_keyboard` only reads `.key`.
    """

    def __init__(self, key):
        self.key = key


async def main(page: ft.Page):
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()

    def state() -> dict:
        w = page.window
        return {'maximized': bool(getattr(w, 'maximized', False)),
                'full_screen': bool(getattr(w, 'full_screen', False)),
                'page': [page.width, page.height]}

    t0 = asyncio.get_event_loop().time()

    async def at(sec: float):
        wait = sec - (asyncio.get_event_loop().time() - t0)
        if wait > 0:
            await asyncio.sleep(wait)

    # ── A1：启动 2 秒内就该是最大化的 ──
    # [EN] ── A1: Should be maximized within 2 seconds of startup ──
    await at(2.0)
    s = state()
    report['A1_at_2s'] = s
    ok('A1 启动 2 秒内窗口已最大化（0.35/0.9/1.8 秒三次里至少成了一次）',
       s['maximized'] is True, s)

    # ── A2 ★★ 「被还原之后还能拉回来」——只有重试覆盖到 3.2 秒才过得去 ──
    # [EN] ── A2 ★★ "Can it be pulled back after being restored" — only passes if the retry covers up to
    # [EN] 3.2 seconds ──
    try:
        page.window.maximized = False          # 模拟平台把窗口改回普通尺寸
        # [EN] The simulated platform changes the window back to normal size
        page.update()
    except Exception as e:                                   # noqa: BLE001
        report['A2_setup_error'] = repr(e)
    await at(2.5)
    report['A2_after_restore_0.5s'] = state()
    await at(3.4)
    s34 = state()
    report['A2_at_3.4s'] = s34
    ok('★★ A2 2.0 秒时被"还原"，3.4 秒时已被拉回最大化'
       '（旧实现只重试到 1.55 秒 → 这条必红）',
       s34['maximized'] is True, s34)

    # ── A3：之后保持最大化 ──
    # [EN] ── A3: Stays maximized afterward ──
    await at(5.0)
    s5 = state()
    report['A3_at_5s'] = s5
    ok('A3 5 秒时仍是最大化（不会自己又还原）', s5['maximized'] is True, s5)
    ok('★ A4 默认**不是全屏**（用户要的是最大化，别把任务栏盖掉）',
       s5['full_screen'] is False, s5)

    # ── A5 ★ 用户按过 F11 之后，启动兜底收工（不跟他抢窗口状态）──
    app._on_keyboard(_Key('F11'))              # 用户亲手进全屏
    # [EN] ── A5 ★ After the user has pressed F11, the startup fallback stops (doesn't fight them over
    # [EN] window state) ──
    # [EN] User manually enters fullscreen
    page.update()
    await asyncio.sleep(1.2)
    s4 = state()
    report['A5_after_user_F11'] = s4
    ok('★ A5 用户按 F11 进全屏后，启动兜底已收工（全屏没被顶掉）',
       s4['full_screen'] is True, s4)

    # ── B：再按一次 F11（退出全屏）──
    # [EN] ── B: Press F11 again (exit fullscreen) ──
    app._on_keyboard(_Key('F11'))
    page.update()
    await asyncio.sleep(1.6)
    sf = state()
    report['B1_after_F11_out'] = sf
    ok('B1 再按 F11 → 退出全屏（full_screen=False）', sf['full_screen'] is False, sf)
    ok('★ B2 退出全屏后仍是**最大化**（不是掉成 1440 那个小窗）',
       sf['maximized'] is True and float(sf['page'][0] or 0) > 1500, sf)

    try:
        png = await page.take_screenshot()
        (OUT / 'window_max_verify.png').write_bytes(png)
    except Exception as e:                                   # noqa: BLE001
        report['shot_error'] = repr(e)

    report['checks'] = checks
    report['passed'] = sum(1 for c in checks if c['ok'])
    report['total'] = len(checks)
    report['ok'] = report['passed'] == report['total']
    (OUT / 'window_max_verify.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for c in checks:
        print(('  ✓ ' if c['ok'] else '  ✗ ') + c['name'] + (
            f"   [{c['detail']}]" if not c['ok'] else ''))
    print(f"\n窗口最大化验证：{report['passed']}/{report['total']}")
    await shutdown(page, code=0 if report['ok'] else 2)


if __name__ == '__main__':
    try:
        ft.run(main)
    except Exception:                                        # noqa: BLE001
        exit_now(2)
