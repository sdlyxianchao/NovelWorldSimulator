# -*- coding: utf-8 -*-
"""验证：运行界面**最下面那条常驻状态提示**（灰字椭圆胶囊）。

用户 2026-10-06 问：「运行界面的最下面的提示小灰色的框 里面的内容对吗 特别是时间信息」。
真机取证查出四个问题，全部已修，这里逐条钉住：

  ① **没在跑的时候挂着一串天文数字** —— 未运行时屏幕上写着「未运行 · 已 1791256630 秒」。
     根因：秒表起点 `_run_status_at` 只在收到状态回调时才存在，
     没初值时 `getattr(..., 0)` 拿到 0，`time.time() - 0` 就是那个数。
  ② **秒表不走** —— `_start_status_ticker()` 写了却**没有任何调用点**。
     于是数字只在"状态变化"那一刻刷新，而每次刷新都刚把起点归零 →
     屏幕上永远停在「已 0 秒」（这个数字本来是用来证明"没卡死"的）。
  ③ **暂停之后文字不更新** —— 同样是 ticker 没跑：按下暂停，屏幕上还写着「运行中」，
     比数字不动更糟，这是实打实的"内容不对"。
  ④ **`'idle'` 那条分支永远走不到** —— `_status_view` 里判断的是 `'waiting'`，
     而 `sim/loop.py` 发的是 `'idle'`，于是只剩干巴巴一句「运行中」，
     用户看不出它在等什么。

判据两层：A 组查"该给哪一句话"（纯逻辑，不弹窗）；
B 组查"屏幕上真是这句话，而且数字真的会走"（真机 + 计时 + 标记色像素取证）。

用法：.venv\\Scripts\\python.exe tools/verify_run_status_bar.py [--logic-only]
产出：assets/screenshots/run_status_bar_probe.png / run_status_bar_report.json

English:
Verify: the **resident status prompt at the very bottom** of the run UI (gray-text oval
capsule).
User asked on 2026-10-06: "The prompt at the very bottom of the run UI, that small gray box --
is the content in it correct, especially the time info?"
Real-machine forensics turned up four problems, all fixed; pinned down one by one here:
  ① **A string of astronomical numbers hangs there when not running** -- when not running the screen reads "not running · 1791256630 seconds elapsed".
     Root cause: the stopwatch start `_run_status_at` exists only once a status callback is received;
     with no initial value, `getattr(..., 0)` gets 0, and `time.time() - 0` is that number.
  ② **The stopwatch does not run** -- `_start_status_ticker()` was written but **has no call site at all**.
     So the number only refreshes at the moment of "status change", and each refresh has just zeroed the start →
     the screen is forever stuck at "0 seconds elapsed" (this number was supposed to prove "not stuck").
  ③ **After pausing, the text does not update** -- again the ticker is not running: press pause and the screen still says "running",
     worse than a frozen number; this is a real case of "wrong content".
  ④ **The `'idle'` branch is never reached** -- `_status_view` checks for `'waiting'`,
     while `sim/loop.py` emits `'idle'`, so only a bare "running" remains,
     and the user cannot tell what it is waiting for.
Two layers of criteria: Group A checks "which line should be shown" (pure logic, no popups);
Group B checks "the screen really shows this line, and the numbers really move" (real machine +
timing + marker-color pixel forensics).
Usage: .venv\\Scripts\\python.exe tools/verify_run_status_bar.py [--logic-only]
Output: assets/screenshots/run_status_bar_probe.png / run_status_bar_report.json
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
import tempfile
import time
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402
import verify_ui_common as VU                                  # noqa: E402
from util.flet_shutdown import shutdown                        # noqa: E402

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')
# 本脚本验的是底部状态条；开场那条路另有脚本（`verify_story_depth`）。
# （开场现在是"推一张卡后直接开跑"，不再等点击 —— 这里关它只为聚焦。）
# [EN] This script verifies the bottom status bar; the opening path has its own script
# [EN] (`verify_story_depth`).
# [EN] (The opening is now "run directly after pushing one card", no longer waiting for a click --
# [EN] disabling it here is just for focus.)
CFG.set('SHOW_OPENING', 'false')
# 一拍拉长到 5 秒 —— 秒表要有可观测的时间窗才判得了"它在走"。
# ⚠ `CFG.set` **只改内存不写盘**（写 .env 是另一步），所以不会污染用户配置。
# [EN] Stretch one beat to 5 seconds -- a stopwatch needs an observable time window to judge "it is
# [EN] running".
# [EN] ⚠ `CFG.set` **only changes memory, does not write to disk** (writing .env is a separate step),
# [EN] so it will not pollute the user's config.
BEAT = '5'
CFG.set('BEAT_SECONDS', BEAT)

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


class FakeText:
    """够用的假控件：只需要 `.value` / `.color` 两个属性。
        English:
    Minimal fake widget: only needs the two attributes `.value` / `.color`.
    """

    def __init__(self) -> None:
        self.value = ''
        self.color = ''


class FakeSession:
    """够用的假会话：`_status_view` / `_run_status_text` 只读这几样。
        English:
    Minimal fake session: `_status_view` / `_run_status_text` only read these few things.
    """

    def __init__(self, status: str = 'running', alive: bool = True,
                 reason: str = '') -> None:
        self.status = status
        self.is_alive = alive
        self.reason = reason

    def snapshot(self) -> dict:
        return {'day': 3}


# ══════════════════════════════════════════════════════════════
#  A. 纯逻辑（不弹窗）
# [EN] A. Pure logic (no popups)
# ══════════════════════════════════════════════════════════════
def logic_checks() -> None:
    from gui.app_flet import NovelWorldApp

    app = NovelWorldApp()               # 只为借它的 `_status_view` / `_refresh_run_status`
    # [EN] Only borrowing its `_status_view` / `_refresh_run_status`
    app._run_bar_text = FakeText()
    app._run_status_dot = FakeText()

    # ── A1 `_status_view` 的分支 ──
    # [EN] ── A1 branches of `_status_view` ──
    views: list = []
    for sess, key in ((None, 'idle'),
                      (FakeSession('running', True), 'idle'),
                      (FakeSession('running', True), 'deciding'),
                      (FakeSession('paused', True), 'idle'),      # 暂停 + 细粒度 key
                      # [EN] Pause + fine-grained key
                      (FakeSession('stopped', False, '手动停止'), 'idle')):
        app.session = sess
        try:
            views.append(app._status_view(key))
        except Exception as e:                                  # noqa: BLE001
            views.append((f'<抛异常 {e!r}>', ''))
    report['views'] = [v[0] for v in views]

    ok('A1 没有会话 → 「未运行」', views[0][0] == t('未运行'), views[0][0])
    ok("A2 ★ idle → 「运行中 —— 等下一次行动」（不再是干巴巴的「运行中」）",
       views[1][0] == t('运行中 —— 等下一次行动'), views[1][0])
    ok('A3 deciding → 「正在生成 —— 人物在行动」',
       views[2][0] == t('正在生成 —— 人物在行动'), views[2][0])
    ok('A4 ★★ 暂停**优先于**细粒度 key（暂停时 key 还是上一个，'
       '顺序写反就会显示成「运行中」）',
       views[3][0] == t('已暂停 —— 等你点「继续」'), views[3][0])
    ok('A5 会话已停 → 交给「状态」那块（「已停止（手动停止）」）',
       '已停止' in views[4][0], views[4][0])

    # ── A6 秒表只在该有的时候挂（回归：未运行时那串天文数字）──
    # [EN] ── A6 the stopwatch mounts only when it should (regression: that astronomical number when not
    # [EN] running) ──
    app.session = None
    app._run_status_key = 'idle'
    app._refresh_run_status()
    v_none = str(app._run_bar_text.value)
    ok('A6 ★★ 没在跑时**不挂秒表**（回归「未运行 · 已 1791256630 秒」）',
       v_none == t('未运行') and '已' not in v_none.replace('未运行', ''),
       v_none)

    app.session = FakeSession('running', True)
    app._run_status_at = time.time() - 7.0
    app._refresh_run_status()
    v_run = str(app._run_bar_text.value)
    ok('A7 ★ 在跑时挂秒表，数字就是"这个状态持续了多久"（这里约 7 秒）',
       ('已 7 秒' in v_run or '已 6 秒' in v_run or '已 8 秒' in v_run), v_run)

    app.session = FakeSession('stopped', False, '手动停止')
    app._refresh_run_status()
    v_stop = str(app._run_bar_text.value)
    ok('A8 ★ 停下来之后秒表**要拿掉**（"已停止 · 已 1234 秒"是噪声）',
       '已停止' in v_stop and '秒' not in v_stop, v_stop)

    # ── A9 同一个状态连续上报**不重置**秒表 ──
    # [EN] ── A9 the same status reported consecutively does **not reset** the stopwatch ──
    app.session = FakeSession('running', True)
    app._run_status_key = 'idle'
    app._run_status_at = time.time() - 5.0
    app._on_status('idle')                     # 与上一个 key 相同 → 不该归零
    # [EN] Same as the previous key -> should not zero out
    kept = time.time() - app._run_status_at
    app._on_status('deciding')                 # key 换了 → 该归零
    # [EN] key changed -> should zero out
    reset = time.time() - app._run_status_at
    ok('A9 ★★ 同一个状态连续上报不重置秒表（主循环每拍末尾都报一次 `idle`，'
       '否则屏幕上永远「已 0 秒」）',
       kept >= 4.5 and reset < 1.0, f'同 key 后 {kept:.2f}s / 换 key 后 {reset:.2f}s')

    # ── A10 `_run_status_at` 建实例时就有初值 ──
    # [EN] ── A10 `_run_status_at` has an initial value when the instance is created ──
    fresh = NovelWorldApp()
    ok('A10 ★ 秒表起点在建实例时就有初值（没有它 → 未运行时那串天文数字）',
       isinstance(getattr(fresh, '_run_status_at', None), float)
       and abs(time.time() - fresh._run_status_at) < 5,
       getattr(fresh, '_run_status_at', '<没有>'))


# ══════════════════════════════════════════════════════════════
#  B. 真机
# [EN] B. Real machine
# ══════════════════════════════════════════════════════════════
def find_btn(root, label: str):
    for c in VU.walk(root):
        if hasattr(c, 'on_click') and c.on_click and label in VU.text_of(c):
            return c
    return None


def pink_box(png: bytes) -> dict:
    """量品红（`#ff00ff`）像素的包围盒 —— 标记色法。

    为什么要标记色：状态条是半透明的纸色胶囊，跟中栏那块半透明纸在像素上
    几乎同色，按原色找不出来（本项目的老问题）。**只动颜色不动几何**。
    
        English:
    Measure the bounding box of magenta (`#ff00ff`) pixels -- the marker-color method.
        Why marker color: the status bar is a translucent paper-colored capsule, and the semi-transparent paper in the middle column is
        almost the same color in pixels, so it cannot be found by its original color (a long-standing issue in this project). **Only change color, not geometry**.
    """
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert('RGB')
    W, H = im.size
    px = im.load()
    xs, ys = [], []
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            c = px[x, y]
            if c[0] > 200 and c[1] < 80 and c[2] > 200:
                xs.append(x)
                ys.append(y)
    if not xs:
        return {'n': 0, 'W': W, 'H': H}
    return {'n': len(xs), 'W': W, 'H': H,
            'x0': min(xs), 'x1': max(xs), 'y0': min(ys), 'y1': max(ys)}


async def gui_checks(page: ft.Page, app, tmp: Path) -> None:
    from verify_run_control import make_project

    def bar() -> str:
        ctl = getattr(app, '_run_bar_text', None)
        return str(ctl.value if ctl is not None else '<控件不存在>')

    def secs(txt: str) -> int:
        """从「… · 已 N 秒」里取出 N（取不到给 -1）。
                English:
        Extract N from "... · N seconds elapsed" (if it cannot be extracted, give -1).
        """
        import re
        m = re.search(r'已\s*(\d+)\s*秒', txt)
        return int(m.group(1)) if m else -1

    try:
        # ── B1 未开跑：只有一句话，**没有秒表** ──
        # [EN] ── B1 not yet started: only one line, **no stopwatch** ──
        proj = make_project(tmp / '状态条')
        app.current_project = proj
        app.show_main_screen()
        await asyncio.sleep(1.2)
        v = bar()
        report['v_before'] = v
        ok('B1 ★★ 刚进运行界面 → 只有「未运行」，**不挂秒表**'
           '（修之前是「未运行 · 已 1791256630 秒」）',
           v == t('未运行'), v)

        # ── 开跑（真实路径：启动故事对话框 → 开始推演）──
        # [EN] ── start running (real path: launch the story dialog -> start deduction) ──
        dlg = app.show_start_story_dialog()
        page.update()
        await asyncio.sleep(0.8)
        btn = find_btn(dlg, t('开始推演'))
        ok('B2 找得到「开始推演」按钮（下面几条都靠它）', btn is not None, '')
        if btn is not None:
            btn.on_click(None)
            for _ in range(80):
                await asyncio.sleep(0.1)
                if app.session is not None and app.session.is_alive:
                    break

        ok('B3 ★ ticker 真的启动了（`_status_task` 非空 —— 以前这个函数'
           '**没有任何调用点**，秒表因此不走）',
           getattr(app, '_status_task', None) is not None,
           type(getattr(app, '_status_task', None)).__name__)

        await asyncio.sleep(1.5)
        # ⚠ 别用"隔 3.5 秒取两次、要求第二次更大"来判"秒表在走" ——
        #   秒表**每拍都会归零**（新一拍开始是一个新状态），跨拍采样必然撞上
        #   归零那一瞬，功能正常时也会红（第一版就是这样）。
        #   改成**密集轮询一个完整拍期**，看这组数字里有没有涨起来过。
        # [EN] ⚠ Do not use "sample twice 3.5 seconds apart, require the second to be larger" to judge "the
        # [EN] stopwatch is running" --
        # [EN] the stopwatch **zeroes out every beat** (a new beat starts as a new status), so cross-beat
        # [EN] sampling will inevitably hit
        # [EN] the instant it zeroes out, which fails even when the feature works correctly (that is how the
        # [EN] first version behaved).
        # [EN] Instead use **dense polling over one full beat period**, and check whether this set of numbers
        # [EN] ever went up.
        nums: list = []
        texts: list = []
        for _ in range(20):                 # 20 × 0.3s = 6 秒，覆盖一个拍期（5 秒）
        # [EN] 20 × 0.3s = 6 seconds, covering one beat period (5 seconds)
            await asyncio.sleep(0.3)
            v = bar()
            texts.append(v)
            nums.append(secs(v))
        report['run_samples'] = texts[-3:]
        ok('B4 在跑 → 带上秒表，而且数字**是个正常数**（不是那串天文数字）',
           nums and all(0 <= n < 600 for n in nums), nums[:10])
        ok('B5 ★★ 秒表**真的在走**（6 秒里涨到过 2 秒以上、且数字确实变过 —— '
           'ticker 不跑的话永远是一串 0）',
           max(nums) >= 2 and len(set(nums)) >= 2, f'样本={nums}')

        # ── 暂停：文字要变、秒表继续走 ──
        # [EN] ── pause: text should change, stopwatch keeps running ──
        app._on_pause_toggle()
        await asyncio.sleep(1.5)
        p1 = bar()
        await asyncio.sleep(2.5)
        p2 = bar()
        report['pause_samples'] = [p1, p2]
        ok('B6 ★★ 暂停后文字**立刻变成"已暂停"**（以前 ticker 不跑，'
           '屏幕上还写着「运行中」—— 内容不对）',
           '已暂停' in p1 and '运行中' not in p1, p1)
        ok('B7 暂停期间秒表继续走（表示"已经暂停了多久"）',
           secs(p2) > secs(p1), f'{secs(p1)} → {secs(p2)}（{p1!r} / {p2!r}）')

        # ── 标记色像素取证：那条胶囊真在屏幕上，而且靠左、不铺满 ──
        # [EN] ── marker-color pixel forensics: that capsule really is on screen, and it is left-aligned, not
        # [EN] full-width ──
        barctl = getattr(app, '_run_status_bar', None)
        old_bg = getattr(barctl, 'bgcolor', None)
        if barctl is not None:
            barctl.bgcolor = '#ff00ff'
            try:
                page.update()
                await asyncio.sleep(0.6)
                png = await page.take_screenshot()
                (OUT / 'run_status_bar_probe.png').write_bytes(png or b'')
            finally:
                barctl.bgcolor = old_bg
                page.update()
        else:
            png = b''
        box = pink_box(png) if png else {'n': 0}
        report['pixel_box'] = box
        ok('B8 ★★ 状态条**真的画在屏幕上**（标记色像素取证），'
           '而且是个"胶囊"：靠左、不铺满整行',
           box.get('n', 0) > 200
           and box.get('y0', 0) > box['H'] * 0.5          # 在下半屏（底部那条）
           # [EN] In the lower half of the screen (that strip at the bottom)
           and (box.get('x1', 0) - box.get('x0', 0)) < box['W'] * 0.6,
           box)

        # ── 停止：秒表拿掉、ticker 收工 ──
        # [EN] ── stop: stopwatch removed, ticker done ──
        app._on_stop_run()
        # ★★ 2026-10-14 改：**轮询等收尾完成**，不再固定睡 2.5 秒。
        #   点「停止」只是**请求**停 —— `RunSession.stop()` 只把 `reason` 改成
        #   「正在停止…」（`_status` 要等收尾跑完才切，见那边的说明），而收尾
        #   要补落最后一天 + 走完收工流程（真机下是几十秒到几分钟）。
        #   固定睡 2.5 秒时，MOCK 下也常常还停在「正在停止…」⇒ 判据**假红**
        #   （实测就是这么红的）。改成最多等 60 秒、见到「已停止」就提前退出。
        # [EN] ★★ Changed 2026-10-14: **poll until the wrap-up finishes** instead of sleeping a
        # [EN] fixed 2.5 seconds.
        # [EN] Clicking "stop" only **requests** a stop -- `RunSession.stop()` merely sets `reason`
        # [EN] to "stopping..." (`_status` only switches after the wrap-up, see the note there), and
        # [EN] the wrap-up backfills the last day and runs the whole shutdown flow (tens of seconds
        # [EN] to minutes on a real machine). With a fixed 2.5s sleep it often still reads
        # [EN] "stopping..." even under MOCK => the criterion **falsely reds** (which is exactly how
        # [EN] it was red). Now wait up to 60 seconds, exiting early once "stopped" appears.
        # ⚠ 2026-10-14 实测补充：**MOCK 下收尾 74 秒仍未完成**（`_await_stop` 里
        #   `s.wait(120)` 等的是"补落最后一天 + 整条收工流程"）。所以这条判据
        #   **在真机上很可能等不到终态** —— 等待上限取 20 秒（够覆盖"点下去
        #   立刻有反应"那一段，又不至于把回归拖成一分钟）。
        #   它现在钉的是两件事：① 点了之后状态**不再是「已暂停」**（那是 2026-10-14
        #   修掉的那个真 bug：`_status_view` 的 paused 分支漏判 `reason`）；
        #   ② 真到了终态就顺带验"秒表收掉"。
        # [EN] ⚠ Measured 2026-10-14: **the wrap-up is still unfinished after 74s under MOCK**
        # [EN] (`s.wait(120)` inside `_await_stop` waits for "backfill the last day + the whole
        # [EN] shutdown flow"). So this criterion **very likely cannot see the terminal state on a
        # [EN] real machine** -- the wait cap is 20s (enough to cover "the click reacts
        # [EN] immediately", without dragging the regression into a minute).
        # [EN] It now pins two things: (1) after the click the status is **no longer "paused"**
        # [EN] (that was the real bug fixed on 2026-10-14: the paused branch of `_status_view` missed
        # [EN] the `reason` check); (2) if the terminal state is reached, it also verifies the
        # [EN] stopwatch is removed.
        v_stop = ''
        for _ in range(40):                     # 40 × 0.5s = 最多 20 秒
            # [EN] 40 × 0.5s = at most 20 seconds
            await asyncio.sleep(0.5)
            v_stop = bar()
            if '已停止' in v_stop:
                break
        report['v_stop'] = v_stop
        ok('B9 ★ 停下来之后秒表拿掉、显示「已停止（…）」',
           '已停止' in v_stop and '秒' not in v_stop, v_stop)
        ok('B10 ★ ticker 自己收工（`_status_task` 清回 None —— '
            '不清的话**第二轮开跑秒表就又不走了**）',
           getattr(app, '_status_task', None) is None,
           type(getattr(app, '_status_task', None)).__name__)
    finally:
        if app.session is not None:
            try:
                await app.session.wait(15)
            except Exception:                                   # noqa: BLE001
                pass
        VU.safe_rmtree(tmp, ignore_errors=True)


async def entry(page: ft.Page) -> None:
    from gui.app_flet import NovelWorldApp
    # ⚠ 项目根隔离必须在建 app **之前**（`NovelWorldApp.__init__` 会读 projects_dir）
    # [EN] ⚠ Project root isolation must happen **before** creating the app (`NovelWorldApp.__init__` reads
    # [EN] projects_dir)
    tmp = Path(tempfile.mkdtemp(prefix='nws_bar_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    # ⚠ **点「开始推演」会 `CFG.save()`**，把脚本里的 MOCK / SHOW_OPENING 等
    #   写进**用户的 .env**。备份/还原必须罩住**整段流程** —— 不能只包"点按钮那一瞬"：
    #   按钮触发的是异步流程，`with` 块会在它跑完前退出，于是 `CFG.save()` 落在还原之后，
    #   `.env` 就被永久改掉了（2026-10-06 实测：SHOW_OPENING 被写成 false）。
    # [EN] ⚠ **Clicking "Start Deduction" will call `CFG.save()`**, writing the script's MOCK /
    # [EN] SHOW_OPENING etc.
    # [EN] into the **user's .env**. Backup/restore must cover the **entire flow** -- it cannot just wrap
    # [EN] "the instant the button is clicked":
    # [EN] the button triggers an async flow, the `with` block exits before it finishes, so `CFG.save()`
    # [EN] lands after the restore,
    # [EN] and `.env` gets permanently modified (measured 2026-10-06: SHOW_OPENING was written as false).
    env_path = APP_DIR / '.env'
    env_backup = env_path.read_text(encoding='utf-8') if env_path.exists() else None
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(1.8)
    try:
        await gui_checks(page, app, tmp)
    except BaseException:                                      # noqa: BLE001
        report['fatal'] = traceback.format_exc()
    finally:
        if env_backup is not None:
            try:
                env_path.write_text(env_backup, encoding='utf-8')
                report['env_restored'] = True
            except OSError as e:                               # noqa: BLE001
                report['env_restore_error'] = str(e)
    # ⚠ 收尾必须在关窗之前（`page.window.destroy()` 会取消本协程）
    # [EN] ⚠ Cleanup must happen before closing the window (`page.window.destroy()` will cancel this
    # [EN] coroutine)
    await shutdown(page, code=finish())


def finish() -> int:
    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    (OUT / 'run_status_bar_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"\n状态条验证：{len(report['checks']) - len(bad)}/{len(report['checks'])}")
    for c in bad:
        print('  ✗', c['name'], '|', c['detail'])
    if report.get('fatal'):
        print(report['fatal'][-1200:])
    print('报告：assets/screenshots/run_status_bar_report.json')
    return 0 if report['ok'] else 2


def main() -> int:
    if '--logic-only' in sys.argv:
        try:
            logic_checks()
        except BaseException:                                  # noqa: BLE001
            report['fatal'] = traceback.format_exc()
        return finish()
    try:
        logic_checks()                                         # A 组先跑，早暴露
        # [EN] Group A runs first, to expose problems early
    except BaseException:                                      # noqa: BLE001
        report['fatal'] = traceback.format_exc()
    ft.run(entry)                  # entry 内部 shutdown（带退出码）
    # [EN] entry internal shutdown (with exit code)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
