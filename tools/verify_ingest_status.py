# -*- coding: utf-8 -*-
"""真机验证：摄取对话框里「**跟大模型沟通**」那一行小字 + 日志的阶段分隔线（v1.39）。

用户原话（2026-10-06）：
「这个窗口 摄取进度 旁边是否可以用一行小字显示跟大模型沟通的状态 比如正在思考 读取文件
等待回复 完成等等什么之类的 **让我看到进展**；然后左侧我想完成一个阶段 下一行出一个横线
然后再下一行一个空行 然后再继续。」

三组判据：

**A 纯逻辑**
  · `AI_STAGES`（哪几步会真调大模型）**逐个对 `ingest/pipeline.py` 的源码核对**：
    每个 AI 阶段 `_emit` 之后紧跟着一个已知的 LLM 调用函数，每个本地阶段后面没有。
    这条**会真的读源码**——阶段表改了而 `AI_STAGES` 没跟着改，就会报红，
    否则那行小字会理直气壮地说「这一步不联网」，而它其实在联网花钱。
  · 那行小字是**小字**（`HINT_FS < BODY_FS`）。
  · 新加的 16 条状态文案中英都有（en 下 `t(k) != k`）。

**B 真机**（MOCK 模式，走真实入口 `show_import_wizard` → `_do_import`）
  · 那行小字与「摄取进度」在**同一个 Row** 里（不是另起一行）；
  · 状态序列覆盖到每一档：待机 → 本地处理（不联网）→ 准备调用 AI → 正在思考·等待回复
    → ✓ 已回复（带耗时/token/花费）→ 已暂停（同意门）→ 轮到你（对话阶段）→ ✓ 全部完成；
    **顺序**也要对（第一条是待机/准备中，最后一条是完成）。
  · 阶段分隔线（结构）：条数 == 阶段数 − 1，每条都是 `Container(height=1)` 后面跟一个空行，
    而且**第一条阶段之前不画**。
  · 阶段分隔线（像素）：**受控夹具 + 真实代码路径** —— 真跑过程中拍不到（`auto_scroll` 停在
    底部，最后一段 AI 正文折十几行，眨眼就把分隔线顶出视野，而 MOCK 整趟只有 1.9 秒，
    一次截图就要 0.3~0.5 秒）。所以改成：把日志清成已知内容，用真的 `_add_stage_sep()`
    插两条线再截图，数"**比对照图多出来的**横线"—— 对照 0 条、插入后正好多 2 条。
    线的**位置与条数**由结构判据保证，像素只证"画得出来、画在了栏里"。
    ⚠ 判"多出来几条"而不是"一共几条"：日志栏自己的上下边框跟分隔线同色同宽，
    会被一起数进来，但在两张图里都在、会抵消；而绝对条数还跟页头高度挂钩（反向实验撞到过）。
  · 那行小字（像素）：**在图上直接量**。清空状态拍一张（页头墨迹 = 标题本身）拿到标题 bbox，
    再放一长句拍一张做差拿到小字 bbox，判「在标题右边 + 与标题同一行 + 整整一行」。

跑法：
    .venv\\Scripts\\python.exe tools/verify_ingest_status.py
产出：
    assets/screenshots/ingest_status_*.png
    assets/screenshots/ingest_status_report.json

English:
Real-machine verification: in the ingestion dialog the small text on the "**talk to the LLM**"
row + the log's stage separator line (v1.39).
User's original words (2026-10-06):
"Next to this window's ingestion progress, can a small line of text show the status of talking
to the LLM, like thinking, reading files,
waiting for reply, done, etc **so I can see progress**; and on the left I want, when a stage
finishes, the next row draws a horizontal line,
then the row after that is blank, then it continues."
Three groups of criteria:
**A Pure logic**
  · `AI_STAGES` (which steps really call the LLM) **checked one by one against the source of `ingest/pipeline.py`**:
    each AI stage's `_emit` is immediately followed by a known LLM call function, each local stage has none after it.
    This one **really reads the source** — if the stage table changed and `AI_STAGES` didn't follow, it reports red,
    otherwise that small text would confidently say "this step doesn't go online" while it's actually going online and spending money.
  · That line of small text is **small text** (`HINT_FS < BODY_FS`).
  · The 16 newly added status strings exist in both Chinese and English (under en, `t(k) != k`).
**B Real machine** (MOCK mode, goes through the real entry `show_import_wizard` → `_do_import`)
  · That small line of text and "ingest progress" are in the **same Row** (not on a separate line);
  · The status sequence covers every stage: idle -> local processing (no network) -> preparing to call AI -> thinking·waiting for reply
    -> ✓ replied (with elapsed time/token/cost) -> paused (consent gate) -> your turn (dialogue stage) -> ✓ all complete;
    The **order** must also be correct (the first is idle/preparing, the last is complete).
  · Stage separators (structure): count == number of stages − 1, each is a `Container(height=1)` followed by a blank line,
    and **not drawn before the first stage**.
  · Stage separators (pixels): **controlled fixture + real code path** -- they can't be captured during an actual run (`auto_scroll` stops at
    the bottom, the last AI body paragraph wraps a dozen lines and instantly pushes the separators out of view, and a full MOCK run is only 1.9 seconds,
    while one screenshot takes 0.3~0.5 seconds). So instead: clear the log to known content, use the real `_add_stage_sep()`
    to insert two lines and screenshot, then count "the **extra** horizontal lines compared to the control image" -- control has 0, after insertion exactly 2 more.
    The **position and count** of the lines are guaranteed by the structural criterion; pixels only prove "it can be drawn, and it's drawn within the column".
    ⚠ Judge by "how many extra" rather than "how many total": the log column's own top/bottom borders have the same color and width as the separators,
    and would be counted along, but they're present in both images and cancel out; the absolute count also depends on the header height (an inverse experiment hit this).
  · That small line of text (pixels): **measure directly on the image**. Clear the state and take one shot (header ink = the title itself) to get the title bbox,
    then put a long sentence and take another shot, diff to get the small-text bbox, and check "to the right of the title + same row as the title + exactly one row".
How to run:
    .venv\\Scripts\\python.exe tools/verify_ingest_status.py
Output:
    assets/screenshots/ingest_status_*.png
    assets/screenshots/ingest_status_report.json
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft  # noqa: E402
import verify_ui_common as VU  # noqa: E402
from PIL import Image, ImageChops  # noqa: E402
from util.flet_shutdown import shutdown, exit_now  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')          # 演示模式：零网络、零成本、可复现
# [EN] Demo mode: zero network, zero cost, reproducible
CFG.set('UI_LANG', 'zh')

from gui.app_flet import (AI_STAGES, BODY_FS, HINT_FS, C,  # noqa: E402
                          NovelWorldApp)
from i18n import set_lang, t  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

# `ingest/pipeline.py` 里那六个"真会发 LLM 请求"的调用（AI 阶段 `_emit` 之后紧跟的那个）
# [EN] The six calls in `ingest/pipeline.py` that "really do send LLM requests" (the one right after
# [EN] `_emit` in the AI stages)
LLM_CALLS = {'extract_settings', 'detect_genre', 'extract_style',
             'build_progress_table', 'align_with_text', 'propose_opening'}

# 分隔线用的就是 `C['border']`（沙金）。⚠ **不能按它的原色精确匹配**——见 `count_sep_lines`。
# [EN] The separator line uses `C['border']` (sand gold). ⚠ **Cannot match exactly by its original
# [EN] color** — see `count_sep_lines`.
SEP_RGB = (217, 201, 163)


def count_sep_lines(png: Path, bb, *, min_run: int = 300, t_lo: float = 0.35,
                    res: int = 6) -> list:
    """日志栏里"整宽的沙金横线"有几条，返回每条的中心 y。

    判据是"这条**线**在不在"，不是"这个**颜色**在不在"，因为 —— 三条实测出来的规矩：

    1. ★ **1 逻辑像素会被抗锯齿摊成两行混合色**。对话框按窗口收过宽度
       （`ING_W=1180` 落到实际约 1161），设备缩放 ≈0.98：`Container(height=1)`
       在屏幕上占不满一个设备像素，于是变成**两行各约 50% 的混合色**
       （实测 (224,214,189) / (234,225,202)）。所以**按 `C['border']` 原色
       (217,201,163) 精确匹配，一条都找不到**（第一版就是这么数出 0 的，
       还以为是"没画出来"，白查了一轮）。
       正解：把判据改成"颜色落在**纸白 → 边框色**这条线段上"——任何混合比例都算。
    2. **区域要从日志栏的边框之内开始**（`bb[1]+145`）。日志栏自己就有
       `make_border(1, C['border'])` 的上下边线，跟分隔线**同色同宽**；
       把区域从 `bb[1]+110` 起，光那两条边线就会数出十几行，判据直接被淹掉。
    3. 再用 `min_run=300` 只要整宽长条：日志栏内宽约 550px，文字行凑不出 300px 同色。

    背景色取**区域里的众数**（自适应），不写死 —— 不同面板的纸白不一样。
    
        English:
    How many "full-width sand-gold horizontal lines" are in the log column; return the center y of
    each.
        The criterion is "whether this **line** is present", not "whether this **color** is present", because -- three empirically measured rules:
        1. ★ **1 logical pixel gets antialiased into two rows of blended color**. The dialogue box width was reduced by the window
           (`ING_W=1180` ends up at about 1161 actual), device scale ≈0.98: `Container(height=1)`
           doesn't fill a full device pixel on screen, so it becomes **two rows each about 50% blended color**
           (measured (224,214,189) / (234,225,202)). So **exact-matching the original `C['border']` color
           (217,201,163) finds not a single one** (the first version counted 0 this way,
           and thought it was "not drawn", wasting a round of investigation).
           Correct approach: change the criterion to "the color lies on the **paper-white -> border-color** line segment" -- any blend ratio counts.
        2. **The region must start inside the log column's border** (`bb[1]+145`). The log column itself has
           `make_border(1, C['border'])` top and bottom lines, which are **the same color and width** as the separators;
           starting the region at `bb[1]+110`, just those two border lines would count a dozen-plus rows and drown the criterion.
        3. Then use `min_run=300` to require only full-width long strips: the log column's inner width is about 550px, text rows can't reach 300px of the same color.
        The background color is taken as the **mode within the region** (adaptive), not hardcoded -- different panels have different paper whites.
    """
    im = Image.open(png).convert('RGB')
    px = im.load()
    y0, y1 = bb[1] + 145, bb[3] - 60
    x0, x1 = bb[0] + 25, bb[2] - 25
    bg = Counter(list(im.crop((x0, y0, x1, y1)).getdata())).most_common(1)[0][0]
    d = [SEP_RGB[i] - bg[i] for i in range(3)]
    dd = sum(v * v for v in d) or 1

    def on_ramp(c) -> bool:
        v = [c[i] - bg[i] for i in range(3)]
        t = sum(v[i] * d[i] for i in range(3)) / dd
        if not (t_lo <= t <= 1.4):
            return False
        return max(abs(v[i] - t * d[i]) for i in range(3)) <= res

    rows: list = []
    for y in range(y0, y1):
        run = mx = 0
        for x in range(x0, x1):
            if on_ramp(px[x, y]):
                run += 1
                mx = max(mx, run)
            else:
                run = 0
        if mx >= min_run:
            rows.append(y)
    # 相邻行（差 ≤2）属于同一条线 —— 抗锯齿会把一条线摊成两行
    # [EN] Adjacent rows (diff ≤2) belong to the same line — anti-aliasing spreads one line across two rows
    lines: list = []
    for y in rows:
        if lines and y - lines[-1][-1] <= 2:
            lines[-1].append(y)
        else:
            lines.append([y])
    return [int(sum(g) / len(g)) for g in lines]


def ink_bbox(png: Path, x0: int, x1: int, y0: int, y1: int,
             thr: int = 380) -> tuple | None:
    """一块区域里"墨迹"（明显比纸白深的像素）的 bbox。用来在图上**直接量**文字在哪。

    ⚠ **阈值必须比"边框"更严**（第一版用 600，把纸边线全算成墨迹了，量出来是个 375×104 的
    大框）：纸白 (251,249,242) 三通道和 742、面板色 ≈745；而**边框**色
    `C['border']` #d9c9a3 = **581**、`C['border_gold']` #c9a24e = **441**；
    真正的文字色 `C['text']` #232830 = 123、`C['gold']` #a8781f = **319**。
    所以取 380：文字（≤335）进、边框（≥441）出。
    
        English:
    The bbox of "ink" (pixels noticeably darker than paper white) within a region. Used to
    **directly measure** on the image where the text is.
        ⚠ **The threshold must be stricter than "border"** (the first version used 600, which counted all paper border lines as ink, measuring out a 375×104
        big box): paper white (251,249,242) three-channel sum 742, panel color ≈745; while the **border** color
        `C['border']` #d9c9a3 = **581**, `C['border_gold']` #c9a24e = **441**;
        the real text color `C['text']` #232830 = 123, `C['gold']` #a8781f = **319**.
        So take 380: text (≤335) in, border (≥441) out.
    """
    im = Image.open(png).convert('RGB')
    px = im.load()
    W, H = im.size
    xs: list = []
    ys: list = []
    for y in range(max(0, y0), min(H, y1)):
        for x in range(max(0, x0), min(W, x1)):
            if sum(px[x, y]) < thr:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def make_fixture(root: Path) -> Path:
    src = root / '雨夜来客'
    (src / '正文').mkdir(parents=True, exist_ok=True)
    (src / '大纲.md').write_text(
        '# 大纲\n\n起：雨夜来客打破平静。\n承：旧事被翻出。\n转：最可信的人露出破绽。\n合：有人离开。\n',
        encoding='utf-8')
    (src / '人物设定.md').write_text(
        '# 人物\n\n## 主角\n掌柜，沉默寡言。\n\n## 阿枝\n伙计，嘴上不饶人。\n', encoding='utf-8')
    (src / '正文' / '第1章.md').write_text(
        '# 第1章\n\n雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃。\n\n'
        '「你今日话里有话。」\n\n「话就是话，哪来的里外。」\n' * 8, encoding='utf-8')
    return src


def long_uniform_rows(*_a, **_k):        # 旧判据已废，留着只为让老调用点报错更清楚
# [EN] Old criterion is deprecated, kept only to make errors at old call sites clearer
    raise AssertionError('别再用它：面板底色本身每行都是"长同色条"，数出来毫无区分力')


async def main(page: ft.Page):
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    items: list = []
    report: dict = {}

    def ok(name: str, cond, detail: str = '') -> bool:
        items.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
        if not cond:
            print(f'FAIL  {name}   [{detail}]')
        return bool(cond)

    tmp = Path(tempfile.mkdtemp(prefix='nws_ist_'))
    # ⚠ 隔离项目根：摄取会真的建一个项目，不隔离就是往用户的「拾卷」里塞东西
    # [EN] ⚠ Isolate the project root: ingestion really creates a project, without isolation it dumps into
    # [EN] the user's "拾卷"
    VU.isolate_projects_dir(tmp / 'Projects')

    async def shot(name: str):
        page.update()
        await asyncio.sleep(0.35)
        p = OUT / name
        p.write_bytes(await page.take_screenshot())
        return p

    def make_row(text: str) -> ft.Text:
        """一条和真日志同款的行（像素夹具用）。

        ⚠ 夹具必须**跟真日志同一套字号/字体/宽度**，否则"有没有换行/占多少高度"都不一样，
        量出来的位置就不代表真实情况。样式抄的是 `_add_log` 里那个 `ft.Text`。
        
                English:
        A line identical to a real log line (for the pixel fixture).
                ⚠ The fixture must **use the same font size/font/width as the real log**, otherwise "whether it wraps/how much height it takes" differs,
                and the measured positions won't represent the real situation. The style is copied from that `ft.Text` in `_add_log`.
        """
        return ft.Text(text, size=12, color='#232830', selectable=True,
                       font_family='Consolas', no_wrap=False)

    try:
        # ══════════ A. 纯逻辑：AI_STAGES 与 pipeline 源码逐个核对 ══════════
        # [EN] ══════════ A. Pure logic: check AI_STAGES against pipeline source one by one ══════════
        from ingest.pipeline import STAGES
        stage_ids = [s[0] for s in STAGES]
        report['stages'] = stage_ids
        report['ai_stages'] = sorted(AI_STAGES)

        unknown = sorted(AI_STAGES - set(stage_ids))
        ok('A：`AI_STAGES` 里的每个阶段都真在 `ingest.pipeline.STAGES` 里',
           not unknown, str(unknown))

        src_txt = (APP_DIR / 'ingest' / 'pipeline.py').read_text(encoding='utf-8')
        lines = src_txt.splitlines()
        emits = [(i, m.group(1)) for i, ln in enumerate(lines)
                 if (m := re.search(r'_emit\(\s*on_stage,\s*"([^"]+)"', ln))]
        mismatch: list[str] = []
        checked: dict[str, str] = {}
        for pos, (i, sid) in enumerate(emits):
            # 一个阶段的"活儿"就在**它的 _emit 到下一个 _emit 之间** ——
            # ⚠ 不能用固定的"往后看 6 行"：`extract_done` 只是个完成标记，
            # 往后 4 行就是下一阶段的 `detect_genre`，会把它误判成 AI 阶段（第一版）。
            # [EN] A stage's "work" is exactly **between its _emit and the next _emit** —
            # [EN] ⚠ Cannot use a fixed "look ahead 6 lines": `extract_done` is just a completion marker,
            # [EN] looking 4 lines ahead reaches the next stage's `detect_genre`, which would misjudge it as an AI
            # [EN] stage (first version).
            end = emits[pos + 1][0] if pos + 1 < len(emits) else len(lines)
            span = '\n'.join(lines[i + 1:end])
            hit = next((c for c in LLM_CALLS if c in span), '')
            checked[sid] = hit or '（本地）'
            want_ai = sid in AI_STAGES
            if bool(hit) != want_ai:
                mismatch.append(f'{sid}: 源码说{"要" if hit else "不要"}调 AI（{hit or "—"}）'
                                f'，AI_STAGES 说{"要" if want_ai else "不要"}')
        report['stage_llm_check'] = checked
        ok('A：★ 每个阶段"要不要调大模型"与 `AI_STAGES` 完全一致（读的是源码，不是注释）',
           not mismatch, ' | '.join(mismatch))

        ok('A：那行小字确实是"小字"（比正文小一档）',
           HINT_FS < BODY_FS, f'HINT_FS={HINT_FS} BODY_FS={BODY_FS}')

        # 动态取值扫不到，这条是真守卫
        # [EN] Dynamic value scanning can't catch it, this is the real guard
        set_lang('en')
        new_keys = ['待机 —— 还没开始', '准备中 —— 先读本地文件',
                    '本地处理：{label}（这一步不联网）', '准备调用 AI：{label}',
                    '正在思考 · 等待回复（已等 0 秒 · {m} · {p}）',
                    '正在思考 · 等待回复（已等 {s} 秒 · {m} · {p}）',
                    '✓ 已回复 · 用时 {ms} ms · {tin}+{tout} token · 花费 ¥{c}',
                    '! 调用失败（第 {n}/{m} 次）', '，正在重试…', '，不再重试',
                    '已暂停：等你确认之后才会调用 AI',
                    '轮到你 —— 打字下指令，AI 在等你', '✓ 摄取完成', '✓ 全部完成',
                    '✗ 失败 —— 详见左侧日志', '已中止（没有发出任何请求）']
        miss = [k for k in new_keys if t(k) == k]
        set_lang('zh')
        ok('A：16 条新状态文案中英都有', not miss, str(miss))

        # ══════════ B. 真机 ══════════
        # [EN] ══════════ B. Real machine ══════════
        src = make_fixture(tmp)
        app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.6)
        app._wizard_path = str(src)
        app._wizard_name = '摄取状态验证'
        app._wizard_opts['ai_optimize'] = True
        app._wizard_opts['repair_source'] = False    # 这一步会停下等确认，脚本里跳过
        # [EN] This step blocks for confirmation, skipped in the script
        app._do_import(page)

        st = app._ingest_state
        for _ in range(80):
            await asyncio.sleep(0.1)
            if st.get('ui') and st['ui']['status_hist']:
                break
        ui = st.get('ui') or {}
        ok('B：摄取对话框起来了，那行小字的句柄在', bool(ui.get('llm_status')))

        # —— 小字与「摄取进度」在同一个 Row ——
        # [EN] —— Small text and "ingestion progress" are in the same Row ——
        header_parents = []
        for psr in VU.walk(ui.get('dlg')):
            kids = getattr(psr, 'controls', None)
            if not isinstance(kids, list):
                continue
            vals = []
            for k in kids:
                vals += [x.value for x in VU.walk(k) if isinstance(x, ft.Text)]
            if t('摄取进度') in vals and any(
                    str(getattr(x, 'value', '')) == ui['llm_status'].value
                    for x in VU.walk(kids[-2] if len(kids) > 1 else kids[0])
                    if isinstance(x, ft.Text)) or (
                    t('摄取进度') in vals
                    and any(c is ui['llm_status'] for c in VU.walk(psr))):
                header_parents.append(psr)
        ok('B：那行小字与「摄取进度」在**同一行**（不是另起一行）',
           bool(header_parents), f'{len(header_parents)} 个候选行')

        # —— 等第一个阶段出来，先拍一张"还没有分隔线"的对照图 ——
        # [EN] —— Wait for the first stage to appear, take a reference shot of "no separator line yet" ——
        for _ in range(80):
            await asyncio.sleep(0.1)
            if st.get('stage_n', 0) >= 1:
                break
        await asyncio.sleep(0.2)
        png_before = await shot('ingest_status_1_first_stage.png')

        # —— 同意门 ——
        # [EN] —— Consent gate ——
        for _ in range(200):
            await asyncio.sleep(0.1)
            if getattr(ui.get('consent_panel'), 'visible', False):
                break
        ui = st.get('ui') or {}
        ok('B：同意门出现时，小字说"已暂停：等你确认之后才会调用 AI"',
           any('已暂停' in x for _ts, x in ui.get('status_hist') or []),
           str([x for _ts, x in (ui.get('status_hist') or [])][-2:]))
        await shot('ingest_status_2_consent.png')
        for b in (ui.get('consent_boxes') or []):
            b.value = True
            if getattr(b, 'on_change', None):
                b.on_change(None)
        if ui.get('consent'):
            ui['consent'](True)

        # —— 走到 AI 对话阶段（那时 13 个阶段都跑完了）——
        # 这里拍的这张只是**留证**（真跑过程中的日志长什么样），不参与判据：
        # 日志那时已经 auto_scroll 到最底，分隔线多半不在视野里（见下面像素判据的注释）。
        # [EN] —— Reach the AI dialog stage (by then all 13 stages have finished) ——
        # [EN] The one taken here is just **for the record** (what the log looks like during a real run), it
        # [EN] doesn't participate in the criterion:
        # [EN] The log has already auto_scroll'ed to the bottom by then, the separator line is mostly out of
        # [EN] view (see the pixel-criterion comment below).
        for _ in range(400):
            await asyncio.sleep(0.1)
            if st.get('phase') == 'chat':
                break
        await asyncio.sleep(1.2)
        ui = st.get('ui') or {}
        # 等日志**真的不再增长**（AI 体检那次请求/响应的正文有 1200 字、折十几行；
        # 不等它写完就清日志，下一行又会被追加进来把夹具顶出视野 —— 第二版就是这么栽的）
        # [EN] Wait for the log to **really stop growing** (the AI checkup's request/response body has 1200
        # [EN] chars, wrapping over a dozen lines;
        # [EN] clearing the log before it finishes writing means the next line gets appended and pushes the
        # [EN] fixture out of view — that's how the second version failed)
        last_n, stable = -1, 0
        for _ in range(100):
            await asyncio.sleep(0.15)
            n = len(ui['log_list'].controls)
            stable = stable + 1 if n == last_n else 0
            last_n = n
            if stable >= 3:
                break
        await shot('ingest_status_3_running.png')
        hist = [x for _ts, x in (ui.get('status_hist') or [])]
        report['status_hist'] = hist
        report['stage_n'] = st.get('stage_n')

        ok('B：第一条小字是"待机 / 准备中"（还没开始跑就说清状态）',
           bool(hist) and ('待机' in hist[0] or '准备中' in hist[0]), hist[:1])
        ok('B：出现过"本地处理…（这一步不联网）"（本地阶段）',
           any('本地处理' in x and '不联网' in x for x in hist),
           str([x for x in hist if '本地处理' in x][:1]))
        ok('B：出现过"准备调用 AI：…"（AI 阶段）',
           any('准备调用 AI' in x for x in hist),
           str([x for x in hist if '准备调用 AI' in x][:1]))
        ok('B：★ 出现过"正在思考 · 等待回复"（带秒表 —— 这就是"看到进展"）',
           any('正在思考' in x and '等待回复' in x for x in hist),
           str([x for x in hist if '正在思考' in x][:1]))
        ok('B：★ 回复到了会说清代价（用时 / token / 花费）',
           any('已回复' in x and 'token' in x and '花费' in x for x in hist),
           str([x for x in hist if '已回复' in x][:1]))
        ok('B：轮到作者下指令时，小字说"轮到你…AI 在等你"',
           any('轮到你' in x for x in hist),
           str([x for x in hist if '轮到你' in x][:1]))
        ok('B：AI 阶段的小字出现在本地阶段之后（顺序对）',
           hist.index(next(x for x in hist if '本地处理' in x))
           < hist.index(next(x for x in hist if '准备调用 AI' in x)),
           f'共 {len(hist)} 条状态')

        # —— 阶段分隔线（结构）——
        # [EN] —— Stage separator line (structure) ——
        logc = ui.get('log_list').controls if ui.get('log_list') else []
        stage_lines = [c for c in logc
                       if isinstance(c, ft.Text) and '▶ ' in str(c.value)]
        dividers = [i for i, c in enumerate(logc)
                    if isinstance(c, ft.Container) and getattr(c, 'height', None) == 1
                    and getattr(c, 'bgcolor', None)]
        n_stage = st.get('stage_n', 0)
        report['stage_lines'] = len(stage_lines)
        report['dividers'] = len(dividers)
        ok('B：每个阶段前都有一条横线（条数 == 阶段数 − 1）',
           len(dividers) == max(0, n_stage - 1) == max(0, len(stage_lines) - 1),
           f'阶段 {n_stage} / ▶ 行 {len(stage_lines)} / 横线 {len(dividers)}')
        ok('B：横线后面紧跟一个空行（用户要的"再下一行一个空行"）',
           all(i + 1 < len(logc)
               and isinstance(logc[i + 1], ft.Container)
               and not getattr(logc[i + 1], 'bgcolor', None)
               and (getattr(logc[i + 1], 'height', 0) or 0) >= 8
               for i in dividers), str(dividers[:5]))
        ok('B：第一个阶段之前**不画**横线（开头不顶一条线）',
           bool(logc) and not (isinstance(logc[0], ft.Container)
                               and getattr(logc[0], 'height', None) == 1),
           f'第一条是 {type(logc[0]).__name__}')
        ok('B：横线紧跟的那个 ▶ 阶段行就是它下面那一行的上一行',
           all(isinstance(logc[i + 2], ft.Text) and '▶ ' in str(logc[i + 2].value)
               for i in dividers), '')

        # —— 阶段分隔线（像素）：屏幕上真的画出了横线 ——
        # [EN] —— Stage separator line (pixel): a horizontal line really is drawn on screen ——
        #
        # ⚠ **别指望在真跑的过程中拍到它**（踩了两轮）：`ListView(auto_scroll=True)` 停在底部，
        # 而阶段之间是 AI 回复正文（一行 1200 字折十几行），眨眼就把分隔线顶出视野；
        # 想在"日志还短"的瞬间拍，MOCK 下整趟只有 1.9 秒，而一次截图本身就要 0.3~0.5 秒，
        # 等快门按下时管线早跑过去了（两张图都是 0 条，就是这个原因）。
        # 所以像素这一关改成**受控夹具 + 真实代码路径**：
        # 在对话阶段（管线已停下等作者输入）把日志清成已知内容，
        # 用**真的 `_add_stage_sep()`** 插两条线，再截图数金线。
        # 「每条线该在哪个位置、该有几条」由上面的结构判据保证，这里只证"画得出来"。
        # [EN] ⚠ **Don't count on capturing it during a real run** (burned twice): `ListView(auto_scroll=True)`
        # [EN] sits at the bottom,
        # [EN] and between stages is the AI reply body (a 1200-char line wrapping over a dozen lines), which
        # [EN] shoves the separator out of view in a blink;
        # [EN] trying to capture it at the instant "the log is still short": under MOCK the whole run is only
        # [EN] 1.9 seconds, and a single screenshot itself takes 0.3~0.5 seconds,
        # [EN] by the time the shutter fires the pipeline has long run past (both shots had 0 lines, that's
        # [EN] why).
        # [EN] So the pixel check was changed to **controlled fixture + real code path**:
        # [EN] At the dialog stage (pipeline already stopped waiting for author input), clear the log to known
        # [EN] content,
        # [EN] use the **real `_add_stage_sep()`** to insert two lines, then screenshot and count gold lines.
        # [EN] "Where each line should be, how many there should be" is guaranteed by the structural criterion
        # [EN] above, here we only prove "it can be drawn".
        ui['set_llm_status']('', C['muted'])
        logc.clear()
        logc.append(make_row('▶ 假阶段一（像素判据的对照）'))
        logc.append(make_row('   一行正文，用来占掉和真日志一样的位置'))
        page.update()
        png_no_sep = await shot('ingest_status_6_fixture_no_sep.png')
        ui['add_stage_sep']()
        logc.append(make_row('▶ 假阶段二'))
        ui['add_stage_sep']()
        logc.append(make_row('▶ 假阶段三'))
        png_sep = await shot('ingest_status_7_fixture_with_sep.png')

        bb = VU.dialog_bbox(Image.open(png_before))
        if bb:
            l0 = count_sep_lines(png_no_sep, bb)
            l2 = count_sep_lines(png_sep, bb)
            # ★ 判"多出来的那两条"，而不是判绝对条数：日志栏**自己的上下边框**
            #   跟分隔线同色同宽，会被一起数进来；而它在两张图里都在、会抵消。
            #   绝对条数还跟页头高度有关（页头一变，那个固定偏移就可能正好压在栏边框上）——
            #   反向实验里就撞到过：把状态行挪到单独一行后，对照图也数出 2 条。
            # [EN] ★ Judge "those two extra lines", not absolute line count: the log column's **own top/bottom
            # [EN] borders**
            # [EN] have the same color and width as the separator, they get counted too; but they appear in both
            # [EN] shots so they cancel out.
            # [EN] Absolute line count also depends on header height (if the header changes, that fixed offset
            # [EN] might land exactly on the column border) —
            # [EN] hit it in the reverse experiment: after moving the status line to its own row, the reference
            # [EN] shot also counted 2 lines.
            added = [y for y in l2 if all(abs(y - y0) > 4 for y0 in l0)]
            report['sep_lines'] = {'fixture_no_sep': l0, 'fixture_with_sep': l2,
                                   'added': added,
                                   'dividers_in_real_log': len(dividers)}
            ok('B：★ 插进去的两条横线真的出现在屏幕上（沙金、整宽、抗锯齿摊销也算一条）',
               len(added) == 2, f'对照 {l0} / 插入后 {l2} / 新增 {added}')
            ok('B：★ 没插的时候一条都不多（多出来的确实是这两条，不是别的东西）',
               len(l2) == len(l0) + 2, f'{len(l0)} → {len(l2)}')
        else:
            ok('B：★ 屏幕上真的画出了那些横线', False, '量不到对话框 bbox')

        # —— 等它跑到 AI 对话阶段（那时所有阶段都跑完了）——
        # [EN] —— Wait for it to reach the AI dialog stage (by then all stages have finished) ——
        for _ in range(400):
            await asyncio.sleep(0.1)
            if st.get('phase') == 'chat':
                break
        await asyncio.sleep(1.2)
        ui = st.get('ui') or {}

        # —— 小字（像素）：**在图上直接量**它画在哪、是不是在「摄取进度」右边 ——
        # 三步：① 把状态清空 → 页头那条墨迹就是标题本身；② 状态放一个短词；
        # ③ 状态放一长句。用 ① 拿到标题的 bbox，用 ③ 拿到状态的 bbox，
        # 再判"在标题右边 + 与标题同一行"。这样不用猜标题有多宽（第一次就是猜的：
        # 拿 `bb[0]+100` 当"标题右边"，实测差 4px 就误判）。
        # [EN] —— Small text (pixel): **measure directly on the image** where it's drawn, whether it's to the
        # [EN] right of "ingestion progress" ——
        # [EN] Three steps: ① clear the status → the ink in the header row is the title itself; ② set status to
        # [EN] a short word;
        # [EN] ③ set status to a long sentence. Use ① to get the title's bbox, use ③ to get the status bbox,
        # [EN] then judge "right of title + same row as title". This avoids guessing how wide the title is (the
        # [EN] first time was a guess:
        # [EN] using `bb[0]+100` as "right of title", off by 4px in practice and it misjudged).
        ui['set_llm_status']('', C['muted'])
        png_t = await shot('ingest_status_4_title_only.png')
        ui['set_llm_status']('短', '#a8781f')
        png_s = await shot('ingest_status_5_status_short.png')
        long_txt = '正在思考 · 等待回复（已等 42 秒 · deepseek-chat · 提取人物与世界观）'
        ui['set_llm_status'](long_txt, '#a8781f')
        png_l = await shot('ingest_status_8_status_long.png')

        diff = ImageChops.difference(Image.open(png_t).convert('RGB'),
                                     Image.open(png_l).convert('RGB')).convert('L')
        dbb = diff.point(lambda v: 255 if v > 24 else 0).getbbox()
        # 标题的 bbox：**在小字所在那一行的左侧**找墨迹（这样就不用猜标题在 y 哪儿）。
        # 它必须真的在、而且宽度像个四字标题 —— 否则"小字在标题右边"就无从谈起。
        # [EN] Title's bbox: **on the left side of the row where the small text is** find the ink (so we don't
        # [EN] have to guess where the title's y is).
        # [EN] It must really be there, and be about as wide as a four-character title — otherwise "small text
        # [EN] right of title" is meaningless.
        title_box = (ink_bbox(png_t, bb[0] + 20, dbb[0] - 2, dbb[1] - 12, dbb[3] + 12)
                     if dbb else None)
        report['status_px'] = {'title_box': list(title_box) if title_box else None,
                              'long_diff_bbox': list(dbb) if dbb else None}
        if title_box and dbb:
            title_w = title_box[2] - title_box[0]
            same_row = not (dbb[3] <= title_box[1] or dbb[1] >= title_box[3])
            right_of = dbb[0] >= title_box[2] - 2      # 容 2px 抗锯齿
            left_edge = title_box[0] <= bb[0] + 60     # 标题贴着内容左边缘
            wide = (dbb[2] - dbb[0]) >= 200            # 一整句话真的排出来了
            short_h = (dbb[3] - dbb[1]) <= 30           # 只有一行（没折行、没顶高）
            # [EN] Tolerate 2px anti-aliasing
            # [EN] Title hugs the content's left edge
            # [EN] A whole sentence really lays out
            # [EN] Only one row (no wrap, no extra height)
            ok('B：★ 那行小字**真的画在屏幕上，且在「摄取进度」右边、与它同一行**',
               same_row and right_of and wide and short_h and left_edge
               and 40 <= title_w <= 130,
               f'标题 {title_box}(宽 {title_w}) / 小字 {dbb} 同一行={same_row} '
               f'在右边={right_of} 宽={dbb[2] - dbb[0]} 高={dbb[3] - dbb[1]}')
        else:
            ok('B：★ 那行小字真的画在屏幕上', False,
               f'标题框={title_box} 小字框={dbb}')

        # —— 收尾 ——
        ui['finish']()          # ⚠ `_finish` 不接参数（`send` 才接 e）
        # [EN] —— Wrap up ——
        # [EN] ⚠ `_finish` takes no arguments (`send` is the one that takes e)
        for _ in range(80):
            await asyncio.sleep(0.1)
            if not st.get('running'):
                break
        await asyncio.sleep(0.6)
        hist = [x for _ts, x in (st.get('ui', {}).get('status_hist') or [])]
        report['status_last'] = hist[-1] if hist else ''
        ok('B：结束时最后一条是"✓ 全部完成"',
           bool(hist) and '全部完成' in hist[-1], repr(report['status_last']))
        ok('B：跑完之后秒表收掉了（没有残留的等待任务）',
           st.get('running') is False, str(st.get('running')))

        report['ok'] = all(i['ok'] for i in items)
    except Exception:
        import traceback
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        report['items'] = items
        report['n_ok'] = sum(1 for i in items if i['ok'])
        report['n_all'] = len(items)
        (OUT / 'ingest_status_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\n摄取状态验证：{report['n_ok']}/{report['n_all']}")
        for i in items:
            if not i['ok']:
                print(f"  ✗ {i['name']}  [{i['detail']}]")
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be applied **before closing the window**: `page.window.destroy()` raises
        # [EN] CancelledError
        # [EN] cancelling this coroutine; write it on the line after `await shutdown(page)`: `exit_now(...)`
        # [EN] **Never executed** (exit code always 0 = false green). See `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report['ok'] else 2)


if __name__ == '__main__':
    ft.run(main)
