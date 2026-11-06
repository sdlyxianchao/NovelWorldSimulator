# -*- coding: utf-8 -*-
"""真机验证：运行模式「前台显示修饰名、后台存变量值」。

三种模式 × 中/英，逐个检查：
  1. 顶栏左上角**带项目名**
  2. 顶栏 / 运行配置面板显示的是修饰后的模式名（走完故事 / 不限期限 / 定期暂停…），
     **不出现** story / open / story_day 这类变量名
  3. 天机 / 书斋的运行模式下拉：label 是修饰名，value 仍是变量值
  4. 后台 CFG('RUN_MODE') 始终是原始变量值（没被前台污染）

产出：assets/screenshots/mode_<mode>_<lang>.png + run_mode_report.json

English:
Real device verification: run mode "foreground displays decorated name, background stores
variable value".
Three modes × Chinese/English, check one by one:
  1. Top bar upper-left **has the project name**
  2. What the top bar / run config panel displays is the decorated mode name (walk through story / unlimited term / periodic pause…),
     **does not show** variable names like story / open / story_day
  3. Tianji / Shuzhai run mode dropdown: label is the decorated name, value is still the variable value
  4. Background CFG('RUN_MODE') is always the raw variable value (not polluted by the foreground)
Output: assets/screenshots/mode_<mode>_<lang>.png + run_mode_report.json
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')

from gui.app_flet import NovelWorldApp, run_mode_name, RUN_MODES  # noqa: E402
from store.project import Project  # noqa: E402
import i18n  # noqa: E402
from util.flet_shutdown import shutdown, exit_now  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

PROJECT_NAME = '模式标签验证'
# 变量值 → (中文修饰名, 英文修饰名)
# [EN] Variable value → (Chinese decorated name, English decorated name)
#
# **名字要自带解释**（用户 2026-10-05：「story_day / story / open 你要用语言解释」）——
# 光写「走完故事」还得猜，所以缀一个括号说明。改名字时**三处要一起改**：
# `gui/app_flet.py` 的 `_MODE_NAME` / 这里的 EXPECT / `i18n.py` 的译文。
# [EN] **Names should be self-explanatory** (user 2026-10-05: "story_day / story / open you need to
# [EN] explain in words") ——
# [EN] Just writing "walk through story" still requires guessing, so append a parenthetical
# [EN] explanation. When renaming, **three places must be changed together**:
# [EN] `_MODE_NAME` in `gui/app_flet.py` / EXPECT here / the translations in `i18n.py`.
EXPECT = {
    'story':     ('走完故事（有终点）', 'Run to the end (has an ending)'),
    'open':      ('不限期限（一直续写）', 'Open-ended (keeps going)'),
    'story_day': ('定期暂停（每几天停一次）', 'Pause every few days'),
}
# 界面上不该出现的"变量名"（按词边界匹配）
# [EN] "Variable names" that should not appear in the UI (matched by word boundary)
FORBIDDEN_TOKENS = ['story_day', 'story', 'open']
# 这些文本里出现 `story` / `open` 是**正常英文散文**，不算"露出变量名"：
#   · 'has not started' / '尚未开始' —— 空态占位提示（"The story has not started…"）
#   · 'story seconds' / 'story day' —— `beat_pace_text()` 的英文节奏说明
# [EN] The appearance of `story` / `open` in these texts is **normal English prose**, not considered a
# [EN] "leaked variable name":
# [EN] · 'has not started' / 'not yet started' —— empty state placeholder hint ("The story has not
# [EN] started…")
# [EN] · 'story seconds' / 'story day' —— the English pacing description in `beat_pace_text()`
#     「15 story seconds ≈ 15.0 real seconds · a story day takes about 24.0 hours」。
#     ★ 2026-10-06 实测的**假红**：中文界面全绿，一换英文就红三个模式 ——
#     因为英文里"故事秒/故事日"本来就写作 story seconds / story day。
#     这是判据的假阳性，不是产品问题（界面上那串确实是人话）。
# ⚠ 加白名单要有针对性：真"露出变量名"的样子是**单独一个 `story` 当标签**
#   （下拉框/页头里那种），那些文本里不含上面这些短语，所以照样能被抓到。
# [EN] ★ 2026-10-06 measured **false red**: Chinese UI all green, switch to English and three modes go
# [EN] red ——
# [EN] Because in English, "story seconds/story day" is naturally written as story seconds / story day.
# [EN] This is a false positive of the criterion, not a product issue (the string in the UI is indeed
# [EN] human language).
# [EN] ⚠ The whitelist must be targeted: the real "leaked variable name" looks like **a lone `story` as
# [EN] a label**
# [EN] (the kind in a dropdown/header); those texts don't contain the above phrases, so they can still
# [EN] be caught.
PROSE_ALLOW = ('has not started', '尚未开始', '故事尚未开始',
               'story seconds', 'story day')


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


def collect(page) -> tuple[list[str], list]:
    out: list = []
    for c in page.controls:
        walk(c, out)
    dlgs = list(getattr(getattr(page, '_dialogs', None), 'controls', []) or [])
    for d in dlgs:
        if getattr(d, 'open', False):
            walk(d, out)
    texts = []
    for c in out:
        if isinstance(c, ft.Text) and c.value:
            texts.append(str(c.value))
        if isinstance(c, ft.TextField):
            for a in ('value', 'hint_text'):
                v = getattr(c, a, None)
                if v:
                    texts.append(str(v))
    return texts, out


def raw_token_hits(texts: list[str]) -> tuple[list[str], list[str]]:
    """找出界面上露出的变量名（按整词匹配）。

    返回 (命中列表, 被当散文跳过的列表)。
    `story` 在英文散文（如 "The story has not started…"）里出现是正常的，
    这类文本按 PROSE_ALLOW 跳过，否则会把正常英文误判成"露出变量名"。
    
        English:
    Find variable names exposed in the UI (matched by whole word).
        Returns (hit list, list skipped as prose).
        `story` appearing in English prose (like "The story has not started…") is normal,
        such texts are skipped per PROSE_ALLOW, otherwise normal English would be misjudged as a "leaked variable name".
    """
    import re
    hits, skipped = [], []
    for tk in FORBIDDEN_TOKENS:
        pat = re.compile(r'(?<![A-Za-z_])' + re.escape(tk) + r'(?![A-Za-z_])')
        for t in texts:
            if not pat.search(t):
                continue
            if any(a in t for a in PROSE_ALLOW):
                skipped.append(f'{tk} ← {t[:60]}')
            else:
                hits.append(f'{tk} ← {t[:60]}')
    return hits, skipped


def _measure_dd_text_width(png: Path) -> int:
    """量「运行模式」下拉框里那串字的**像素宽度**（读不了图，只能量）。

    做法：按边框色找横贯的上下边 → 配成盒子 → 取**最宽的那个**
    （运行模式是整行宽；同页另外几个是半宽字段）→ 量它内部最左侧
    那一段墨迹的宽度（右边 18px 内的算箭头，排除掉）。

    判读：人话「走完故事（有终点）」9 个全角字 ≈ 126px；
    变量值 `story` ≈ 33px。所以宽 ≥90 就说明**屏幕上写的确实是人话**。
    
        English:
    Measure the **pixel width** of the string in the "run mode" dropdown (can't read the image, can
    only measure).
        Approach: find the horizontal top and bottom edges by border color → pair them into boxes → take **the widest one**
        (run mode is full-row width; the others on the same page are half-width fields) → measure the width of the
        leftmost segment of ink inside it (anything within 18px on the right counts as the arrow, exclude it).
        Interpretation: the human-readable phrase "walked through the story (has an ending)" is 9 full-width characters ≈ 126px;
        the variable value `story` ≈ 33px. So a width ≥90 means **what's written on screen really is human-readable text**.
    """
    from PIL import Image
    BORDER = (217, 201, 163)

    def _is_border(c) -> bool:
        return all(abs(c[i] - BORDER[i]) <= 14 for i in range(3))

    def _lum(c) -> float:
        return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]

    def _runs(flags, minw):
        out, st = [], None
        for i, f in enumerate(flags):
            if f and st is None:
                st = i
            elif not f and st is not None:
                if i - st >= minw:
                    out.append((st, i - 1))
                st = None
        if st is not None and len(flags) - st >= minw:
            out.append((st, len(flags) - 1))
        return out

    im = Image.open(png).convert('RGB')
    px = im.load()
    W, H = im.size
    lines = []
    for y in range(230, 900):
        xs = [x for x in range(640, min(1320, W)) if _is_border(px[x, y])]
        rr = _runs([(x in set(xs)) for x in range(W)], 80)
        if rr:
            lines.append((y, rr))
    best = None
    i = 0
    while i < len(lines) - 1:
        y0, rr0 = lines[i]
        y1, rr1 = lines[i + 1]
        if y1 - y0 < 14:
            i += 1
            continue
        for (a0, b0) in rr0:
            for (a1, b1) in rr1:
                a, b = max(a0, a1), min(b0, b1)
                # **只认"一行控件"高度的盒子**（SET_H=24，留点余量取 18~30）。
                # 不加这个过滤会量到标题横幅之类的高盒子，那里的文字很长，
                # 宽度照样"过线"，于是断言看着是绿的、其实量错了对象
                # （改完车道后就踩了一次：量出 388px）。
                # [EN] **Only recognize boxes of a "single-row control" height** (SET_H=24, take 18~30 with some
                # [EN] margin).
                # [EN] Without this filter, it will measure tall boxes like the title banner, where the text is long,
                # [EN] the width still "passes the line", so the assertion looks green but actually measured the wrong
                # [EN] object
                # [EN] (it happened once after changing the lane: measured 388px).
                if b - a >= 60 and 18 <= (y1 - y0) <= 30 \
                        and (best is None or b - a > best[3] - best[2]):
                    best = (y0, y1, a, b)
        i += 2
    if not best:
        return 0
    y0, y1, a, b = best
    cols = [any(_lum(px[x, y]) < 150 for y in range(y0 + 2, y1 - 1))
            for x in range(a + 1, b)]
    segs = _runs(cols, 2)
    # 右侧 34px 内的是**下拉箭头**，不是文字 —— 必须排掉。
    # （第一版只排 18px，箭头还是被算进"文字"，量出来是"从第一个字到箭头"的
    #   跨度 388px，断言看着过绿、其实量错了对象。）
    # [EN] What's within 34px on the right is the **dropdown arrow**, not text —— must be excluded.
    # [EN] (The first version only excluded 18px, the arrow was still counted as "text", and the
    # [EN] measurement was "from the first character to the arrow"
    # [EN] span 388px, the assertion looked green but actually measured the wrong object.)
    text = [s for s in segs if s[1] + a + 1 < b - 34]
    if not text:
        return 0
    return text[-1][1] - text[0][0] + 1


async def main(page: ft.Page):
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    report: dict = {'modes': {}}
    # ⚠⚠ `isolate_projects_dir()` 返回的是**旧的**项目根（调用方收尾时还原用），
    #   **不是**隔离目录！原来写成 `Path(isolate_projects_dir(<iso>)) / NAME`
    #   → 拿到的是"隔离之前那个目录"/NAME = **用户真实的 Projects/NAME**
    #   （实测：跑完回归，用户的 Projects/ 里多了「模式标签验证」「透明度验证」
    #    两个测试夹具，还会让「拾卷」里凭空多出两本书）。
    #   正确写法：自己拼隔离目录，夹具建在**它**里面。
    # ★ 改成**私有临时目录**（2026-10-08）：理由同 `verify_opacity` ——
    #   共享的 `_proj` 下留残留会污染别的脚本（实测害 `verify_resume_menu` 假红）。
    # [EN] ⚠⚠ `isolate_projects_dir()` returns the **old** project root (used by the caller to restore at
    # [EN] the end),
    # [EN] **not** the isolated directory! It was originally written as `Path(isolate_projects_dir(<iso>))
    # [EN] / NAME`
    # [EN] → what you get is "the directory before isolation"/NAME = **the user's real Projects/NAME**
    # [EN] (measured: after running the regression, the user's Projects/ gained "mode label verification"
    # [EN] and "opacity verification"
    # [EN] two test fixtures, and it also makes two books appear out of nowhere in "pick up volume").
    # [EN] Correct approach: build the isolated directory yourself, and create the fixture inside **it**.
    # [EN] ★ Change to a **private temporary directory** (2026-10-08): same reason as `verify_opacity` ——
    # [EN] Residue left under the shared `_proj` will pollute other scripts (measured: caused
    # [EN] `verify_resume_menu` false red).
    _iso = Path(tempfile.mkdtemp(prefix='nws_runmodes_'))
    VU.isolate_projects_dir(_iso)
    proj_root = _iso / PROJECT_NAME
    try:
        proj_root.mkdir(parents=True, exist_ok=True)
        (proj_root / '设定集').mkdir(exist_ok=True)
        proj = Project(proj_root, PROJECT_NAME)
        proj.write_nwsproj()
        app.current_project = proj

        for lang in ('zh', 'en'):
            i18n.set_lang(lang)
            for mode in EXPECT:
                CFG.set('RUN_MODE', mode)          # 后台存变量值
                # [EN] Background stores the variable value
                app.show_main_screen()
                page.update()
                await asyncio.sleep(0.8)
                texts, _ = collect(page)
                zh_name, en_name = EXPECT[mode]
                want = zh_name if lang == 'zh' else en_name

                header = next((t for t in texts if t.startswith('【')), '')
                png = await page.take_screenshot()
                (OUT / f'mode_{mode}_{lang}.png').write_bytes(png)

                leaks, prose_skipped = raw_token_hits(texts)
                entry = {
                    'expected_name': want,
                    'header': header,
                    'header_has_project': PROJECT_NAME in header,
                    'header_has_name': want in header,
                    'name_in_panel': any(t == want for t in texts),
                    'raw_tokens_leaked': leaks,
                    'prose_skipped': prose_skipped,
                    'stored_value': CFG.s('RUN_MODE'),
                    'stored_is_variable': CFG.s('RUN_MODE') == mode,
                    'run_mode_name()': run_mode_name(mode),
                }
                entry['ok'] = bool(entry['header_has_project']
                                   and entry['header_has_name']
                                   and entry['name_in_panel']
                                   and not entry['raw_tokens_leaked']
                                   and entry['stored_is_variable'])
                report['modes'][f'{mode}_{lang}'] = entry

        # 下拉选项：label 是修饰名、value 是变量值
        # [EN] Dropdown options: label is the decorated name, value is the variable value
        #
        # ⚠ **只查 `o.text` 是不够的**（这正是 2026-10-05 漏掉的坑）：
        # `ft.DropdownM2` **忽略 `Option.text`，拿 `key` 当显示文字**
        # （实测见 `developers/probe_dd_option.py`：key='K' + text='MMMMMMMM'
        #   框里只画出 7px，对调后仍是 98px —— 显示的一直是 key）。
        # 所以 Python 侧看着全对，屏幕上却写着 `story`。现在三路一起查：
        #   ① 结构：key 是变量值、`content` 里装的是人话（content 才是真正渲染的）
        #   ② 像素：切到「运行」页量下拉框里那串字的**宽度**（key 只有 ~33px）
        # [EN] ⚠ **Checking only `o.text` is not enough** (this is exactly the pit missed on 2026-10-05):
        # [EN] `ft.DropdownM2` **ignores `Option.text`, and uses `key` as the displayed text**
        # [EN] (measurement see `developers/probe_dd_option.py`: key='K' + text='MMMMMMMM'
        # [EN] the box only draws 7px, after swapping it's still 98px —— what's displayed has always been the
        # [EN] key).
        # [EN] So the Python side looks all correct, but the screen shows `story`. Now check all three paths
        # [EN] together:
        # [EN] ① Structure: key is the variable value, `content` holds the human language (content is what's
        # [EN] actually rendered)
        # [EN] ② Pixels: switch to the "Run" page and measure the **width** of the string in the dropdown (key
        # [EN] is only ~33px)
        i18n.set_lang('zh')
        CFG.set('RUN_MODE', 'story')
        dlg = app.show_global_settings()
        page.update()
        await asyncio.sleep(0.8)
        _, ctrls = collect(page)
        dds = [c for c in ctrls if isinstance(c, (ft.Dropdown, ft.DropdownM2))
               and any(o.key == 'story_day' for o in (c.options or []))]
        if dds:
            opts = dds[0].options

            def _opt_text(o):
                c = getattr(o, 'content', None)
                return str(getattr(c, 'value', '') or '')

            decorated = [o.text for o in opts]
            report['dropdown'] = {
                'labels': decorated,
                'content_texts': [_opt_text(o) for o in opts],
                'values': [o.key for o in opts],
                'labels_are_decorated': all(
                    o.text in ('走完故事（有终点）', '不限期限（一直续写）',
                               '定期暂停（每几天停一次）') for o in opts),
                'values_are_variables': [o.key for o in opts] == list(RUN_MODES),
                # ① 每个选项都得有 content，否则渲染出来的是 key
                # [EN] ① Every option must have content, otherwise what's rendered is the key
                'display_via_content': all(
                    _opt_text(o) == o.text for o in opts),
            }
            report['dropdown']['ok'] = bool(
                report['dropdown']['labels_are_decorated']
                and report['dropdown']['values_are_variables']
                and report['dropdown']['display_via_content'])

            # ② 像素：切到「运行」页，量运行模式下拉框里那串字的宽度
            # [EN] ② Pixels: switch to the "Run" page, measure the width of the string in the run mode dropdown
            nodes: list = []
            walk(dlg, nodes)
            tabs = [c for c in nodes if isinstance(c, ft.Tabs)]
            if tabs:
                labels = [str(getattr(t, 'label', ''))
                          for t in tabs[0].content.controls[0].tabs]
                if '运行' in labels:
                    tabs[0].selected_index = labels.index('运行')
                    page.update()
                    await asyncio.sleep(1.0)
                    png = await page.take_screenshot()
                    (OUT / 'mode_dropdown_pixel.png').write_bytes(png)
                    w = _measure_dd_text_width(OUT / 'mode_dropdown_pixel.png')
                    report['dropdown']['pixel_text_width'] = w
                    # 「走完故事（有终点）」9 个全角字 ≈ 126px；
                    # 变量值 `story` 只有 ~33px。卡 90 分得开。
                    # [EN] "walk through story (has endpoint)" 9 full-width characters ≈ 126px;
                    # [EN] the variable value `story` is only ~33px. Threshold 90 separates them.
                    report['dropdown']['pixel_ok'] = w >= 90
                    report['dropdown']['ok'] &= bool(w >= 90)
        else:
            report['dropdown'] = {'ok': False, 'error': '未找到运行模式下拉'}
        try:
            page.pop_dialog()
        except Exception:
            pass

        report['ok'] = (all(v['ok'] for v in report['modes'].values())
                        and report['dropdown'].get('ok', False))
    except Exception:
        import traceback
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        # ⚠ 删 `_iso`（整层 `_proj/<名字>`），不是只删 `proj_root` ——
        #   理由同 `verify_opacity`：`_proj/*` 是**几个脚本共用**的一层，
        #   留个空壳目录会给别的脚本留下"凭空多出一本书"的假红。
        # [EN] ⚠ Delete `_iso` (the whole layer `_proj/<name>`), not just `proj_root` ——
        # [EN] Reason same as `verify_opacity`: `_proj/*` is a layer **shared by several scripts**,
        # [EN] leaving an empty shell directory will leave other scripts with a "a book appears out of nowhere"
        # [EN] false red.
        VU.safe_rmtree(_iso, ignore_errors=True)
        (OUT / 'run_mode_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` will throw
        # [EN] CancelledError
        # [EN] cancel this coroutine, the line `exit_now(...)` written after `await shutdown(page)`
        # [EN] **has never executed** (exit code is always 0 = false green). See
        # [EN] `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report.get('ok') else 2)


ft.run(main)
