# -*- coding: utf-8 -*-
"""验证：运行界面**左栏「风格控制」那几条**（2026-10-08）。

用户原话：

    「左下角的**风格控制**部分 每个参数的数值**不显示出来** 正常应该是
      **中间线条显示类似进度条的样式** 右侧横线是**数值 5/10** 这样的
      **当值 最大值**的形式」

查出来的根因，两条都不是"显示错"而是"根本没接上/少一个"：

  ① **那几条从来没有人填过值。** 调用处一律 `_style_bar(标签)`，**不传 value**
     → `value=None` → 永远空条 + 「—」；而且**全仓没有任何一处**在后来给它
     填过值。同一天里这已经是**第三次**同一个病：
     底部状态条的秒表（`_start_status_ticker` 没有调用点）、
     左上角的时间面板（建出来没人刷）、现在是风格条。
     —— "控件建出来就没人管"是这块代码的**主旋律**，所以判据里专门钉一条：
     **值必须来自 `CFG`（唯一事实来源），并且要随秒表自己走。**

  ② **右边写的是百分比**（`30%`），用户要的是**当值/最大值**（`3/10`）。
     为什么是 10：这组参数的分档数就是 10（滑块 `divisions=10`）。

  ③ **少一个参数**：左栏只列了 6 条，**没有「世界观展开」**
     （`WORLDBUILDING_PACE`）—— 而「书斋 · 风格控制」和「起笔」里都有 7 个。
     用户照着左栏核对"这一轮怎么讲"，会以为这个参数不存在。
     A1 就是照**配置表**核这条，以后再加参数忘补左栏会当场红。

判据两层：A 组纯逻辑（填值规则 / 坏值降级 / 清单与配置表一致），
B 组真机（屏幕上的字 + 条真的画出来了 + 秒表真的会跟着改）。

用法：.venv\\Scripts\\python.exe tools/verify_style_bar.py
产出：assets/screenshots/style_bar_probe.png / style_bar_report.json

English:
Verified: run the UI's **left column "style control" entries** (2026-10-08).
User's original words:
    "The **style control** section in the lower left -- each parameter's value is **not displayed**. Normally it should be
      **the middle line showing a progress-bar-like style**, the right horizontal line being the **value 5/10** in the
      form of **current value / max value**."
Root causes found -- neither is "displayed wrong" but rather "not wired up at all / missing
one":
  ① **Those entries never had values filled in by anyone.** All call sites are `_style_bar(label)`, **no value passed**
     -> `value=None` -> always empty bar + "—"; and **nowhere in the repo** was it later given a value.
     This is already the **third time** the same disease appeared on the same day:
     the bottom status bar's ticker (`_start_status_ticker` has no call site),
     the top-left time panel (created but nobody refreshes it), now the style bars.
     -- "widgets created but nobody cares for them" is the **main theme** of this code, so a criterion is nailed specifically for it:
     **the value must come from `CFG` (single source of truth), and must follow the ticker on its own.**
  ② **The right side wrote a percentage** (`30%`), but the user wants **current value / max value** (`3/10`).
     Why 10: the number of divisions for this group of parameters is exactly 10 (slider `divisions=10`).
  ③ **One parameter missing**: the left column only listed 6 entries, **no "worldbuilding expansion"**
     (`WORLDBUILDING_PACE`) -- while "study · style control" and "start writing" both have 7.
     If the user cross-checks the left column for "how this round should be narrated", they'd think this parameter doesn't exist.
     A1 is exactly this criterion verified against the **config table**; if a parameter is added later and forgotten in the left column, it fails on the spot.
Two layers of criteria: group A pure logic (value-filling rules / bad-value degradation / list
consistency with config table),
group B real machine (text on screen + bars really drawn + ticker really follows changes).
Usage: .venv\\Scripts\\python.exe tools/verify_style_bar.py
Output: assets/screenshots/style_bar_probe.png / style_bar_report.json
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import sys
import tempfile
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
CFG.set('SHOW_OPENING', 'false')      # 开场那条路另有脚本，这里聚焦左栏
# [EN] The opening path has its own script; here we focus on the left column

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

import gui.app_flet as G                                       # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}

#: 「当值/最大值」的形状：`5/10`。**不接受** `30%`（那正是被换掉的老写法）。
# [EN] : the shape of "current value / max value": `5/10`. `30%` is **not accepted** (that's exactly
# [EN] the old notation being replaced).
NUM_RE = re.compile(r'^(\d+)/(\d+)$')


def ok(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


class _Text:
    """够用的假文字控件（只判 `.value` / `.color`）。
        English:
    A sufficient fake text widget (only checks `.value` / `.color`).
    """

    def __init__(self, value=''):
        self.value = value
        self.color = None

    def update(self):                                          # noqa: D102
        pass


class _Bar:
    def __init__(self, value=0.0, color=None):
        self.value = value
        self.color = color

    def update(self):                                          # noqa: D102
        pass


def logic_checks() -> None:
    """A 组：填值规则 + 清单必须照配置表长。
        English:
    Group A: value-filling rules + list must match the config table.
    """
    # ── A1 ★★★ 左栏那几条**必须**与「配置表 · 风格控制组」逐项对齐 ──
    # ⚠ 这条是照着**配置表**核的，不是照着界面核的 —— 所以"以后加了新参数、
    #   忘了补进左栏"会当场红（这次就是这么发现漏了「世界观展开」）。
    # [EN] -- A1 ★★★ The left column entries **must** align item-by-item with the "config table · style
    # [EN] control group" --
    # [EN] ⚠ This was verified against the **config table**, not against the UI -- so "if a new parameter
    # [EN] is added later,
    # [EN] and someone forgets to add it to the left column" will fail on the spot (this is exactly how the
    # [EN] missing "worldbuilding expansion" was found this time).
    import config as C
    from_cfg = {k for k, v in C.SPEC.items()
                if isinstance(v, dict) and v.get('group') == '风格控制'
                and v.get('type') == 'float'}
    from_gui = {k for _lb, k in G.NovelWorldApp.STYLE_BARS}
    ok('A1 ★★★ 左栏风格条 == 配置里「风格控制」组的那几项（一项都不许少）',
       from_gui == from_cfg,
       f'界面 {sorted(from_gui)} / 配置 {sorted(from_cfg)}'
       + (f'  ← 少 {sorted(from_cfg - from_gui)}' if from_cfg - from_gui else '')
       + (f'  ← 多 {sorted(from_gui - from_cfg)}' if from_gui - from_cfg else ''))

    # ── A2 ★★ 「当值/最大值」的算法 ──
    # [EN] -- A2 ★★ The algorithm for "current value / max value" --
    cls = G.NovelWorldApp
    cases = [(0.0, '0/10'), (0.3, '3/10'), (0.5, '5/10'), (0.8, '8/10'),
             (1.0, '10/10')]
    got: list = []
    bad: list = []
    for v, want in cases:
        CFG.set('ANGST_LEVEL', str(v))
        bar, num = _Bar(), _Text()
        cls._fill_style_bar(cls, 'ANGST_LEVEL', bar, num)
        got.append((v, bar.value, num.value))
        if num.value != want or abs(float(bar.value) - v) > 1e-9:
            bad.append(f'{v}→{num.value}/{bar.value}（期望 {want}/{v}）')
    ok('A2 ★★ 条按真值填充，右边写「当值/最大值」（0.3 → 3/10，不是 30%）',
       not bad, '；'.join(bad) or str(got))

    cf = CFG.f('ANGST_LEVEL')
    CFG.set('ANGST_LEVEL', '0.3')

    # ── A3a ★★ 配置里是个坏值 → `CFG` 自己回默认，界面照默认画 ──
    # ⚠ 这里**原本我写错了期望**：以为 `CFG.f()` 会抛、界面该退成「—」。
    #   实测 `config.coerce()` 对 float 的坏值是 `except ValueError: return 默认值`
    #   —— 所以拿到的永远是合法值，"界面退成 —"这条**根本走不到**。
    #   如实改成：坏值 → 回配置默认值 → 界面按默认画（不抛、不空白）。
    # [EN] -- A3a ★★ A bad value in the config -> `CFG` itself falls back to default, UI draws the default
    # [EN] --
    # [EN] ⚠ Here I **originally wrote the wrong expectation**: thought `CFG.f()` would throw and the UI
    # [EN] should fall back to "—".
    # [EN] Actual testing shows `config.coerce()` for a bad float value does `except ValueError: return
    # [EN] default value`
    # [EN] -- so what's obtained is always a legal value, and "UI falls back to —" **can never be
    # [EN] reached**.
    # [EN] Corrected to: bad value -> fall back to config default -> UI draws the default (no throw, no
    # [EN] blank).
    _default = float(C.SPEC['ANGST_LEVEL']['default'])
    CFG.set('ANGST_LEVEL', '很多')          # 只有内存，不落盘
    # [EN] Memory only, not persisted to disk
    bar3, num3 = _Bar(0.9), _Text('x')
    err = ''
    try:
        cls._fill_style_bar(cls, 'ANGST_LEVEL', bar3, num3)
    except Exception as e:                                     # noqa: BLE001
        err = repr(e)
    ok('A3a ★★ 配置里是坏值（`很多`）→ 回配置默认值、界面照默认画，**不抛**'
       '（`config.coerce` 自己兜着；用户手改 .env 写成非数字完全可能）',
       not err and num3.value == f'{round(_default * 10)}/10'
       and abs(float(bar3.value) - _default) < 1e-9,
       f'err={err} text={num3.value!r} bar={bar3.value}')

    # ── A3b ★★ 真拿不到值（键不存在）→ 空条 + 「—」，不抛 ──
    # [EN] -- A3b ★★ Truly can't get a value (key doesn't exist) -> empty bar + "—", no throw --
    bar3b, num3b = _Bar(0.9), _Text('x')
    err2 = ''
    try:
        cls._fill_style_bar(cls, '__不存在的键__', bar3b, num3b)
    except Exception as e:                                     # noqa: BLE001
        err2 = repr(e)
    ok('A3b ★★ 真拿不到值时 → 空条 + 「—」，不抛（这条才是"防空白"的那道保险）',
       not err2 and num3b.value == '—' and float(bar3b.value) == 0.0,
       f'err={err2} text={num3b.value!r} bar={bar3b.value}')
    CFG.set('ANGST_LEVEL', str(cf))

    # ⚠ 这里**故意没有**"越界值夹回 0~1"那条判据：想让条越界，得先让
    #   `CFG.f()` 返回越界值 —— 而 `config.coerce()` 在**它那一层**就已经
    #   按 SPEC 的 min/max 夹好了（实测 `ANGST_LEVEL=3.5` 读出来就是 1.0）。
    #   UI 里那句 `max(0.0, min(1.0, …))` 是**双保险**，在本项目里**观察不到差异**
    #   —— 为它写一条判据就是写一条"永远绿"的假判据（本项目最忌讳这个）。
    # [EN] ⚠ Here I **deliberately omitted** the criterion "clamp out-of-range value back to 0~1": to make
    # [EN] the bar go out of range, one would first need
    # [EN] `CFG.f()` to return an out-of-range value -- but `config.coerce()` at **its own layer** already
    # [EN] clamps according to the SPEC's min/max (actually tested: `ANGST_LEVEL=3.5` reads back as 1.0).
    # [EN] The line `max(0.0, min(1.0, …))` in the UI is a **double safety net**; in this project it
    # [EN] **observes no difference**
    # [EN] -- writing a criterion for it would just be a "always green" fake criterion (this project's
    # [EN] biggest taboo).


async def gui_checks(page: ft.Page, app, tmp: Path) -> None:
    from verify_run_control import make_project
    import config as C

    proj = make_project(tmp / '风格条')
    app.current_project = proj
    # 先定几个**好认**的值，免得与默认值撞了看不出"到底读没读"
    # [EN] First pick a few **easy-to-recognize** values, so they don't collide with defaults and make it
    # [EN] impossible to tell "was it read or not"
    for _k, _v in (('ANGST_LEVEL', '0.2'), ('HUMOR_LEVEL', '0.7'),
                   ('SATISFACTION_DENSITY', '0.6'), ('ROMANCE_RATIO', '0.4'),
                   ('SUSPENSE_DENSITY', '0.9'), ('WORLDBUILDING_PACE', '0.1'),
                   ('CHARACTER_IQ', '0.8')):
        CFG.set(_k, _v)
    app.show_main_screen()
    await asyncio.sleep(1.4)

    want = {k: CFG.f(k) for _lb, k in app.STYLE_BARS}
    rows = dict(app._ui_run.get('style_rows') or {})
    report['rows'] = {k: [round(float(b.value), 3), str(n.value)]
                      for k, (b, n) in rows.items()}

    # ── B1 ★★ 屏幕上的字真是「N/10」，且一条都不落 ──
    # [EN] -- B1 ★★ The text on screen really is "N/10", and not a single one is missing --
    live = [str(getattr(c, 'value', '') or '') for c in VU.walk(page)
            if type(c).__name__ == 'Text' and NUM_RE.match(
                str(getattr(c, 'value', '') or ''))]
    ok('B1 ★★ 屏幕上真有 7 个「当值/最大值」文字（以前这里是 7 个「—」）',
       len(live) == len(app.STYLE_BARS),
       f'{len(live)} 个：{sorted(live)}')

    # ── B2 ★★★ 每条的值 == CFG 的真值（"数值不显示"就是这条坏的）──
    # [EN] -- B2 ★★★ Each bar's value == CFG's real value ("value not displayed" is this criterion failing)
    # [EN] --
    bad = []
    for _lb, k in app.STYLE_BARS:
        pair = rows.get(k)
        if pair is None:
            bad.append(f'{k}: 没有这条')
            continue
        bar, num = pair
        if abs(float(bar.value) - want[k]) > 1e-6:
            bad.append(f'{k}: 条={bar.value} 期望={want[k]}')
        m = NUM_RE.match(str(num.value))
        if not m or round(want[k] * app.STYLE_DIV) != int(m.group(1)) \
                or int(m.group(2)) != app.STYLE_DIV:
            bad.append(f'{k}: 文字={num.value!r} 期望={round(want[k]*app.STYLE_DIV)}'
                       f'/{app.STYLE_DIV}')
    ok('B2 ★★★ 每条都**照 CFG 的真值**填（条的长度 + 右边的数字，两边都对）',
       not bad, '；'.join(bad) or str(report['rows']))

    # ── B3 一条都不能是「—」（用户报的就是这个）──
    # [EN] -- B3 Not a single one may be "—" (this is exactly what the user reported) --
    dashes = [k for k, (_b, n) in rows.items() if str(n.value) == '—']
    ok('B3 ★★ 一条都不再是「—」（以前是**全部** 7 条都是「—」）',
       not dashes, str(dashes))

    # ── B4 ★★ 条真的画在屏幕上（像素取证）──
    # 为什么还要判这个：控件在树里 ≠ 画出来了。涂一个**别处不会出现**的颜色
    # （品红），数它真的出现的像素数 —— 这一步是"上屏"的硬证据。
    # [EN] -- B4 ★★ The bars are really drawn on screen (pixel evidence) --
    # [EN] Why this is also checked: being in the widget tree ≠ being drawn. Paint with a color that
    # [EN] **won't appear anywhere else**
    # [EN] (magenta), and count the pixels where it actually appears -- this step is the hard evidence of
    # [EN] "making it to screen".
    key0 = 'ANGST_LEVEL'
    bar0, _num0 = rows[key0]
    CFG.set(key0, '0.5')
    app._refresh_style_panel()
    old_color = bar0.color
    try:
        bar0.color = '#ff00ff'
        page.update()
        await asyncio.sleep(0.5)
        png = await page.take_screenshot()
        (OUT / 'style_bar_probe.png').write_bytes(png)
        from PIL import Image
        im = Image.open(io.BytesIO(png)).convert('RGB')
        px = im.load()
        n = sum(1 for y in range(im.height) for x in range(im.width)
                if px[x, y][0] > 200 and px[x, y][1] < 80 and px[x, y][2] > 200)
        report['bar_px'] = n
    finally:
        bar0.color = old_color
        page.update()
    ok('B4 ★★ 那条**真的画在屏幕上**（标记色像素 > 60 —— 控件在树里不等于上屏）',
       int(report.get('bar_px') or 0) > 60, report.get('bar_px'))

    # ── B5 ★★★ 秒表真的跟着走（这才是"接线了"的证据）──
    # 用户会一边跑一边回「书斋」改风格；改完左栏不动 = 界面在骗人。
    # 这里**不手工调刷新**，只改配置，等秒表自己发现。
    # [EN] -- B5 ★★★ The ticker really follows along (this is the evidence of "being wired up") --
    # [EN] The user may change styles in the "study" while running; if the left column doesn't move after
    # [EN] the change = the UI is lying.
    # [EN] Here we **don't manually trigger refresh**, only change the config, and wait for the ticker to
    # [EN] discover it on its own.
    dlg = app.show_start_story_dialog()
    page.update()
    await asyncio.sleep(0.8)
    btn = None
    for c in VU.walk(dlg):
        if getattr(c, 'on_click', None) and t('开始推演') in VU.text_of(c):
            btn = c
            break
    ok('B5a 找得到「开始推演」按钮（下面靠它把秒表跑起来）', btn is not None, '')
    if btn is not None:
        btn.on_click(None)
        for _ in range(80):
            await asyncio.sleep(0.1)
            if app.session is not None and app.session.is_alive:
                break
    ok('B5b 秒表启动了（`_status_task` 非空）',
       getattr(app, '_status_task', None) is not None,
       type(getattr(app, '_status_task', None)).__name__)

    if btn is not None:
        CFG.set('CHARACTER_IQ', '0.1')       # 只改配置，**不碰界面**
        # [EN] Only change the config, **don't touch the UI**
        followed = ''
        for _ in range(24):                  # 秒表 0.5s 一跳 → 12 秒足够
        # [EN] Ticker ticks every 0.5s -> 12 seconds is enough
            await asyncio.sleep(0.5)
            _b, _n = app._ui_run['style_rows']['CHARACTER_IQ']
            followed = str(_n.value)
            if followed == '1/10':
                break
        ok('B5c ★★★ 改配置后左栏**自己**跟上（不手工刷）—— 证明它挂在秒表上，'
           '不是"建界面时读一次就再也不管"',
           followed == '1/10', f'跟到 {followed!r}（期望 1/10）')


async def entry(page: ft.Page) -> None:
    from gui.app_flet import NovelWorldApp
    tmp = Path(tempfile.mkdtemp(prefix='nws_stylebar_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    # 整段流程都不许写真实 `.env`（点「开始推演」会 `CFG.save()`）
    # [EN] The whole flow must not write a real `.env` (clicking "Start deduction" will `CFG.save()`)
    VU.redirect_env_writes()
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(1.8)
    try:
        logic_checks()
        await gui_checks(page, app, tmp)
    except BaseException:                                      # noqa: BLE001
        report['fatal'] = traceback.format_exc()
    finally:
        if app.session is not None:
            try:
                await app.session.wait(15)
            except Exception:                                   # noqa: BLE001
                pass
        VU.safe_rmtree(tmp, ignore_errors=True)
    await shutdown(page, code=finish())


def finish() -> int:
    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    (OUT / 'style_bar_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"\n风格控制条验证：{len(report['checks']) - len(bad)}/"
          f"{len(report['checks'])}")
    for c in bad:
        print('  ✗', c['name'], '|', c['detail'])
    if report.get('fatal'):
        print(report['fatal'][-1200:])
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    ft.run(entry)
    sys.exit(finish())
