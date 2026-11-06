# -*- coding: utf-8 -*-
"""**真机**：起笔对话框的「前情提要 + 您对接下来剧情发展的建议」（2026-10-11）。

界面那一半为什么要真机
----------------------
用户点名的那两件事，**都是"看得见"才算数**：

| 要求 | 只有真机能答的问题 |
|---|---|
| "在提笔的前情提要的下面……加上建议这个文本框" | 那两块**画出来了吗**？建议框**在前情提要下面**吗？ |
| "确保这里的前情提要和运行窗口……一样" | 屏幕上**这回真的写着**那一句吗（不是只在函数返回值里对） |

纯逻辑那半在 `tools/verify_author_note.py`（A 组拿真 `RunLoop` 对答案）。
本支补三样它答不了的：

  · **控件树**：两块都在对话框里，且**顺序**对（建议框在前情提要之后）；
  · **像素**：建议框**真的画在屏幕上**（标记色法），而且**在前情提要那一块的下方**
    （两者 y 区间一比就知道 —— 这是"位置"唯一的硬证据）；
  · **端到端**：在框里打字 → 点「开始推演」→ **这一轮的 world 上真的带着那句话**，
    而且它**出现在中栏/开场.md 里**（作者填过的看得见、查得到）。

第二轮（同一天，用户看到成品之后的反馈）——
    「前情提要应该是文本，而不是文本框。右侧下拉条跟前情提要盖住了。
      下面这个文本框应该是更宽，现在的太窄了。」
C 组后半（C4~C6b）就是给这三件事立的判据：

  · **C4/C4b/C4c**：前情提要是**纯文本**（那段字直接挂在内容列上、中间不夹容器；
    可选中；那个 `height=96` 的带框容器**已经不存在**）—— "文本，不是文本框"；
  · **C5**：前情提要与建议框的宽度都**写死 `SET_W`** ⇒ 长前情在 520 处折行，
    右边那条 24px 的**滚动条车道**永远是空的 —— "下拉条盖住了"；
  · **C6/C6b**：建议框屏幕上**真的有 520 宽**（改之前 300，探针实测），
    而且前情提要那段字**没越过**建议框的右边缘 —— "太窄了"。

跑法：`.venv\\Scripts\\python.exe tools\\verify_author_note_ui.py`
产出：`assets/screenshots/author_note_dialog.png` + 报告 json

⚠ 夹具是 `verify_run_control.make_project` 造的临时项目（中性的甲/主角那套），
  装在临时项目根里 —— **不碰用户的项目**。
⚠ `VU.redirect_env_writes()`：开跑会走 `CFG.save()`，不禁写就会把测试值写进真实 `.env`
  （本项目为这件事栽过两次，见 `verify_autosave` 的收尾注释）。

English:
Why the UI half needs a real machine
----------------------
The two things the user named, **both count only if "visible"**:
| Requirement | Question only a real machine can answer |
|---|---|
| "below the pre-writing recap... add this suggestion text box" | are those two blocks **actually drawn**? Is the suggestion box **below the recap**? |
| "make sure the recap here is the same as the run window..." | is that sentence **really written on screen this time** (not just matching in a function's return value) |
The pure-logic half is in `tools/verify_author_note.py` (group A checks the answer against a
real `RunLoop`).
This branch adds three things it can't answer:
  · **widget tree**: both blocks are in the dialog, and the **order** is right (suggestion box after the recap);
  · **pixels**: the suggestion box is **really drawn on screen** (marker color method), and **below the recap block**
    (The y-intervals of the two tell you at a glance — this is the only hard evidence of "position");
  · **End-to-end**: type in the box → click "Start Inference" → **the world for this round really carries that sentence**,
    and it **appears in the middle column/开场.md** (what the author filled in is visible and searchable).
Second round (same day, user feedback after seeing the finished product) ——
    "The recap should be text, not a text box. The right-side dropdown bar covers the recap.
      The text box below should be wider; the current one is too narrow."
The second half of group C (C4~C6b) is exactly the criteria established for these three things:
  · **C4/C4b/C4c**: the recap is **plain text** (that text hangs directly on the content column, with no container in between;
    selectable; that bordered container with `height=96` **no longer exists**) —— "text, not a text box";
  · **C5**: both the recap and the suggestion box widths are **hardcoded to `SET_W`** ⇒ long recaps wrap at 520,
    and that 24px **scrollbar lane** on the right is always empty —— "the dropdown bar covers it";
  · **C6/C6b**: the suggestion box **really is 520 wide** on screen (300 before the change, measured by probe),
    and the recap text **does not cross** the right edge of the suggestion box —— "too narrow".
How to run: `.venv\\Scripts\\python.exe tools\\verify_author_note_ui.py`
Output: `assets/screenshots/author_note_dialog.png` + report json
⚠ The fixture is a temporary project created by `verify_run_control.make_project` (the neutral
甲/主角 set),
  installed in the temporary project root —— **does not touch the user's project**.
⚠ `VU.redirect_env_writes()`: running it will go through `CFG.save()`; without write-blocking it
will write test values into the real `.env`
  (this project has been burned by this twice, see the closing comment in `verify_autosave`).
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
import tempfile
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

import flet as ft                                     # noqa: E402
from PIL import Image                                 # noqa: E402

import verify_ui_common as VU                         # noqa: E402
from util.flet_shutdown import shutdown               # noqa: E402

from config import CFG                                # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('LANGUAGE', 'zh')
VU.redirect_env_writes()

from gui.app_flet import (NovelWorldApp, SET_W, DLG_W)  # noqa: E402
from i18n import set_lang, t                          # noqa: E402
set_lang('zh')

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT: dict = {'checks': []}

NOTE = '这三天先埋一个误会，别急着解释'
#: 两个标记色（只动颜色、不动几何）—— 全项目没人用这两种纯色。
MARK_RECAP = '#ff00ff'      # 品红 → 前情提要那一块
MARK_NOTE = '#ffff00'       # 纯黄 → 建议输入框
# [EN] : Two marker colors (color-only, no geometry changes) — nobody in the whole project uses these
# [EN] two pure colors.
# [EN] Magenta → the recap block
# [EN] Pure yellow → the suggestion input box


def ok(name: str, cond, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    print(('  ✓ ' if cond else '  ✗ ') + name
          + (f'\n        {str(detail)[:220]}' if (detail and not cond) else ''))
    return bool(cond)


def _by_attr(root, attr: str):
    for c in VU.walk(root):
        if getattr(c, attr, None):
            return c
    return None


def _find_note_field(root):
    """对话框里那个"多行、空值、占位提示写着可不填"的输入框。

    ⚠ 按**特征**找，不按下标找（下标会随布局变）—— 本项目的老规矩。
    
        English:
    That input box in the dialog that is "multiline, empty value, with placeholder text saying it
    can be left blank".
        ⚠ Find it by **feature**, not by index (indices change with layout) —— the old rule of this project.
    """
    for c in VU.walk(root):
        if not isinstance(c, ft.TextField):
            continue
        if getattr(c, 'multiline', False) and not str(c.value or '').strip():
            hint = str(c.hint_text or '')
            if '可不填' in hint or 'next' in hint.lower():
                return c
    return None


def _paint(ctrl, color: str) -> list:
    """把控件涂成标记色（**只动颜色**），返回原值供还原。
        English:
    Paint the controls with marker colors (**only change color**), return the original values for
    restoration.
    """
    saved: list = []
    for attr in ('border_color', 'bgcolor'):
        if hasattr(ctrl, attr):
            saved.append((ctrl, attr, getattr(ctrl, attr, None)))
            try:
                setattr(ctrl, attr, color)
            except Exception:                                # noqa: BLE001
                pass
    return saved


def _unpaint(saved: list) -> None:
    for obj, attr, old in saved:
        try:
            setattr(obj, attr, old)
        except Exception:                                    # noqa: BLE001
            pass


def _color_rows(raw: bytes) -> dict:
    """截图上两种标记色的 y 区间（各自返回 `(数量, min_y, max_y)`）。

    ★ 也返回 **x 区间**（2026-10-11 加，用户点名的第二、三件事要用）：
      · 「建议输入框应该是更宽，现在的太窄了」—— 宽不宽**只有横向量得出来**；
      · 「右侧下拉条跟前情提要盖住了」—— 有没有钻到那条 24px 的滚动条车道里，
        看的是**右边缘**。
      所以 `bbox` 里给 `(x0, x1, y0, y1)`。
    
        English:
    The y-intervals of the two marker colors on the screenshot (each returns `(count, min_y,
    max_y)`).
        ★ Also return the **x-interval** (added 2026-10-11, needed for the second and third things the user called out):
          · "The suggestion input box should be wider; the current one is too narrow" —— whether it is wide **can only be measured horizontally**;
          · "The right-side dropdown bar covers the recap" —— whether it has dug into that 24px scrollbar lane
            is determined by looking at the **right edge**.
          So `bbox` gives `(x0, x1, y0, y1)`.
    """
    im = Image.open(io.BytesIO(raw)).convert('RGB')
    w, h = im.size
    buf = im.tobytes()
    out = {'recap': [], 'note': [], 'size': (w, h),
           'bbox': {'recap': None, 'note': None}}
    bb = {'recap': [w, -1, h, -1], 'note': [w, -1, h, -1]}
    for i in range(0, len(buf), 3):
        r, g, b = buf[i], buf[i + 1], buf[i + 2]
        n = i // 3
        k = None
        if r > 190 and b > 190 and g < 110:                 # 品红
        # [EN] Magenta
            k = 'recap'
        elif r > 200 and g > 200 and b < 90:                # 纯黄
        # [EN] Pure yellow
            k = 'note'
        if k is None:
            continue
        x, y = n % w, n // w
        out[k].append(y)
        bb[k][0] = min(bb[k][0], x)
        bb[k][1] = max(bb[k][1], x)
        bb[k][2] = min(bb[k][2], y)
        bb[k][3] = max(bb[k][3], y)
    for k in bb:
        if out[k]:
            out['bbox'][k] = tuple(bb[k])
    return out


def _parents(root) -> dict:
    """`id(子) → 父` 的对照表（控件树里没有 `parent` 属性，只能自己走一遍）。

    为什么要它：「前情提要是**文本**、不是文本框」这件事，最直接的证法就是
    **那段字直接挂在内容列上**（`ft.Column`），中间没有夹着任何 `ft.Container`
    —— 夹着就是"一个框"。判据 C4 用的就是这个。
    
        English:
    The `id(child) → parent` lookup table (the control tree has no `parent` attribute, so you have
    to walk it yourself).
        Why it is needed: for the fact that "the recap is **text**, not a text box", the most direct proof is
        **that text hangs directly on the content column** (`ft.Column`), with no `ft.Container` sandwiched in between
        —— sandwiched in means "a box". Criterion C4 uses exactly this.
    """
    out: dict = {}

    def rec(node, parent, depth: int = 0) -> None:
        if node is None or depth > 24:
            return
        if isinstance(node, (str, int, float, bool, bytes)):
            return
        out[id(node)] = parent
        for attr in ('controls', 'content', 'actions', 'title', 'leading',
                     'trailing', 'subtitle'):
            v = getattr(node, attr, None)
            if isinstance(v, list):
                for c in v:
                    rec(c, node, depth + 1)
            elif hasattr(v, '__class__') and not isinstance(
                    v, (str, int, float, bool)):
                rec(v, node, depth + 1)

    rec(root, None)
    return out


async def _body(page, tmp: Path) -> None:
    from verify_run_control import make_project
    from sim import directive as D
    from sim import resume as R
    from sim import setup as SU
    from sim.setup import load_settings

    # ★★ **用量台账指到临时库**：这一支会**真起一轮推演**（走 MOCK），
    #   而 `llm/usage` 记的是**软件根目录**下的 `usage.db` ——
    #   不打桩的话，"起笔真机"这个夹具项目会混进用户的真实用量报表。
    #   与 `verify_ui_english` / `shoot_usage_dialog` 同一套做法。
    # [EN] ★★ **Usage ledger points at a temp DB**: this branch will **actually start a round of
    # [EN] simulation** (via MOCK),
    # [EN] but `llm/usage` records into `usage.db` under the **software root directory** —
    # [EN] without stubbing, the "start real machine" fixture project would pollute the user's real usage
    # [EN] report.
    # [EN] Same approach as `verify_ui_english` / `shoot_usage_dialog`.
    from llm import usage as _U
    _U.db_path = lambda: tmp / 'usage.db'

    proj = make_project(tmp / '起笔真机')
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    await asyncio.sleep(1.8)
    app.current_project = proj
    app.show_main_screen()
    await asyncio.sleep(1.0)

    # ── ① 打开起笔对话框 ──
    # [EN] ── ① Open the start dialog ──
    dlg = app.show_start_story_dialog()
    page.update()
    await asyncio.sleep(1.2)
    if not ok('A1 起笔对话框真的打开了', dlg is not None, '返回 None'):
        return

    texts = [str(x) for x in VU.all_texts(dlg)]
    ok('A2 ★★★ 对话框里有「前情提要」那一块（用户点名"如果没加记得加上"）',
       any(x.strip() == t('前情提要') for x in texts), texts[:8])
    ok('A2b ★★★ 也有「您对接下来剧情发展的建议」那一节',
       any(x.strip() == t('您对接下来剧情发展的建议') for x in texts),
       [x for x in texts if '建议' in x][:4])

    # ── ② 屏幕上那段前情提要 == 运行窗口那份（逐字）──
    # [EN] ── ② The recap text on screen == the one in the run window (verbatim) ──
    plan = app._resume_plan(proj)
    wvt = ''
    try:
        wvt = SU.worldview_text_of(load_settings(proj.settings_dir))
    except Exception:                                        # noqa: BLE001
        wvt = ''
    want = R.start_recap(plan, worldview_text=wvt)
    ok('A3 ★★★ 前情提要在**屏幕上真的写着**（且非空 —— 空的话下面那条就白测）',
       bool(want), repr(want[:70]))
    ok('A3b ★★★ 屏幕上的那段字**逐字等于**运行窗口会念的那一句'
       '（同一个 plan、同一份实现）',
       bool(want) and any(x.strip() == want.strip() for x in texts),
       f'想找={want[:60]!r}\n        屏幕上有={[x[:40] for x in texts if "第" in x][:3]}')

    # ── ③ 建议框：控件树里有、而且**在前情提要下面** ──
    # [EN] ── ③ Suggestion box: present in the widget tree, and **below the recap** ──
    field = _find_note_field(dlg)
    ok('B1 ★★★ 建议输入框在控件树里，而且是**多行**的',
       field is not None and bool(getattr(field, 'multiline', False)),
       type(field).__name__)

    # 顺序：控件树里的先后（body 是一条 Column，先加的在上面）
    # [EN] Order: the order in the widget tree (body is a single Column, earlier added is on top)
    flat = [x for x in VU.walk(dlg)]
    i_recap = next((i for i, x in enumerate(flat)
                    if isinstance(x, ft.Text)
                    and str(x.value or '').strip() == t('前情提要')), -1)
    i_note = flat.index(field) if field is not None else -1
    ok('B2 ★★★ 建议那一节**排在前情提要之后**（用户指名："在前情提要的下面"）',
       -1 not in (i_recap, i_note) and i_recap < i_note,
       f'前情@{i_recap} 建议@{i_note}')

    # ── ④ 像素：两块**真的画出来了**，而且建议框在下面 ──
    #    标记色法：只改颜色不改几何，量到的就是真实位置。
    #  ⚠ 涂**那行文字本身**，不要涂"装着它的容器"：第一版按
    #    "content 是 Column 且子树里有这段话"去找容器，`VU.walk` 是**深度优先**，
    #    第一个命中的是**对话框最外层**那个 Container ⇒ 量出来的 y 区间是整扇窗，
    #    "建议框在它下面吗"当场判成红。文字控件的 `color` 是唯一的那一个，不会认错。
    # [EN] ── ④ Pixels: both blocks are **actually drawn**, and the suggestion box is below ──
    # [EN] Marker color method: only change color, not geometry, so what you measure is the real position.
    # [EN] ⚠ Paint **that line of text itself**, not "the container holding it": the first version looked
    # [EN] by
    # [EN] "content is a Column and the subtree contains this paragraph" to find the container, `VU.walk`
    # [EN] is **depth-first**,
    # [EN] the first hit is the **outermost Container of the dialog** ⇒ the measured y interval is the
    # [EN] whole window,
    # [EN] "is the suggestion box below it" immediately turns red. The text widget's `color` is the only
    # [EN] one, no misidentification.
    saved: list = []
    recap_txt = None
    for x in flat:
        if isinstance(x, ft.Text) and str(x.value or '').strip() == want.strip():
            recap_txt = x
            break
    if recap_txt is not None:
        saved.append((recap_txt, 'color', getattr(recap_txt, 'color', None)))
        recap_txt.color = MARK_RECAP
    if field is not None:
        saved += _paint(field, MARK_NOTE)
    page.update()
    await asyncio.sleep(0.8)
    raw = await page.take_screenshot()
    px = _color_rows(raw) if raw else {'recap': [], 'note': [], 'size': (0, 0)}
    _unpaint(saved)
    page.update()
    await asyncio.sleep(0.4)
    n_r, n_n = len(px['recap']), len(px['note'])
    ok('C1 ★★★ 前情提要那段字**真的画在屏幕上**（标记色法：只动颜色不动几何）',
       n_r >= 150, f'品红像素 {n_r}（一行二十来字的字面像素量级）')
    ok('C2 ★★★ 建议输入框**真的画在屏幕上**（不是"控件树里有、屏幕上看不见"）',
       n_n >= 300, f'纯黄像素 {n_n}')
    ok('C3 ★★★ 而且建议框**就在前情提要那一块的下方**'
       '（两个色块的 y 区间一比就知道 —— 位置唯一的硬证据）',
       bool(px['recap']) and bool(px['note'])
       and min(px['note']) > min(px['recap'])
       and min(px['note']) >= max(px['recap']) - 8,
       f'前情 y∈[{min(px["recap"]) if px["recap"] else "-"},'
       f'{max(px["recap"]) if px["recap"] else "-"}] '
       f'建议 y∈[{min(px["note"]) if px["note"] else "-"},'
       f'{max(px["note"]) if px["note"] else "-"}]')

    # ══ ⑥ 用户 2026-10-11 第二轮的**三件事**（原话）══════════════════════
    #   「前情提要应该是文本，而不是文本框。右侧下拉条跟前情提要盖住了。
    #     下面这个文本框应该是更宽，现在的太窄了。」
    # [EN] ══ ⑥ User's **three things** from the second round on 2026-10-11 (verbatim)
    # [EN] ══════════════════════
    # [EN] "The recap should be text, not a text box. The right-side scrollbar covers the recap.
    # [EN] This text box below should be wider, the current one is too narrow."
    #
    #   第一版的毛病：前情提要装在一个 `height=96` + 边框 + 底色 + **内层 scroll**
    #   的 `Container` 里 ——
    #     · 那副长相就是"输入框"（用户第一件事说的就是这个）；
    #     · 前情一长就溢出那 96px ⇒ **那个盒子自己长出一条滚动条**，正压在正文
    #       右边缘上（第二件事"盖住了"；本判据的夹具前情很短，探针
    #       `developers/_probe_start_dialog.py` 用 121 字的长前情实测过：
    #       那个盒子 96px 高、内容 80px 起就要滚）；
    #     · 建议框**没给宽度** ⇒ Flutter 按"装得下多少算多少"给了 **300px**
    #       （同一页别的控件都是 520）—— 屏幕上就是"短了一截"（第三件事）。
    # [EN] First version's flaws: the recap lives in a `Container` with `height=96` + border + background +
    # [EN] **inner scroll**,
    # [EN] · that appearance *is* a "text box" (this is what the user's first item refers to);
    # [EN] · once the recap is long it overflows that 96px ⇒ **that box grows its own scrollbar**, sitting
    # [EN] right on the text
    # [EN] right edge (the second item's "covers"; this criterion's fixture recap is very short, the probe
    # [EN] `developers/_probe_start_dialog.py` tested with a 121-char long recap:
    # [EN] that box is 96px tall, and content scrolling starts at 80px);
    # [EN] · the suggestion box **was given no width** ⇒ Flutter gave it **300px** based on "however much
    # [EN] fits"
    # [EN] (every other widget on the same page is 520) — on screen it's just "a bit short" (the third
    # [EN] item).
    #
    #   ⚠ 为什么"宽度"这条要写成**结构判据**（`width == SET_W`）而不是只量像素：
    #     结构是**与文字长短无关**的硬保证 —— 写了 520，长前情就在 520 处折行，
    #     永远钻不到那条 24px 的滚动条车道下面；像素那条只能证明"这一屏够宽"。
    # [EN] ⚠ Why the "width" item must be written as a **structural criterion** (`width == SET_W`) rather
    # [EN] than just measuring pixels:
    # [EN] structure is a hard guarantee **independent of text length** — set 520 and a long recap wraps at
    # [EN] 520,
    # [EN] it can never squeeze under that 24px scrollbar lane; the pixel one can only prove "this screen
    # [EN] is wide enough".
    parents = _parents(dlg)
    rec_ctrl = None
    for x in flat:
        if isinstance(x, ft.Text) and str(x.value or '').strip() == want.strip():
            rec_ctrl = x
            break
    rec_parent = parents.get(id(rec_ctrl)) if rec_ctrl is not None else None
    ok('C4 ★★★ 前情提要是**纯文本**，不是文本框：那段字**直接挂在内容列上**，'
       '中间没有夹任何容器（夹着 = 一个"框"；用户指名要"文本，而不是文本框"）',
       isinstance(rec_ctrl, ft.Text) and not isinstance(rec_ctrl, ft.TextField)
       and isinstance(rec_parent, ft.Column),
       f'控件={type(rec_ctrl).__name__ if rec_ctrl is not None else "-"} '
       f'父={type(rec_parent).__name__ if rec_parent else "-"}')
    ok('C4b ★★ 而且它**可选中**（能选中复制 —— 是"读的文本"，不是"填的框"）',
       bool(getattr(rec_ctrl, 'selectable', False)),
       f'selectable={getattr(rec_ctrl, "selectable", None)}')
    ok('C4c ★★★ 而**那个 height=96 的框**在对话框里已经没有了'
       '（它正是"自己长出滚动条、盖住正文"的那一个）',
       not [c for c in flat if isinstance(c, ft.Container)
            and c.height == 96 and getattr(c, 'border', None)],
       '还找得到 height=96 的带框容器')
    ok('C5 ★★★ 前情提要与建议框的宽度都写死 `SET_W`'
       f'（{SET_W}px —— 一行宽：长前情在 520 处折行，'
       '右边那条 24px 滚动条车道永远是空的）',
       int(getattr(rec_ctrl, 'width', 0) or 0) == SET_W
       and int(getattr(field, 'width', 0) or 0) == SET_W,
       f'前情={getattr(rec_ctrl, "width", None)} '
       f'建议={getattr(field, "width", None)} 栅格={SET_W}')
    thin = (px['bbox']['note'][1] - px['bbox']['note'][0] + 1
            if px['bbox']['note'] else 0)
    ok('C6 ★★★ 建议框**屏幕上真的有 520 那么宽**'
       '（改之前是 300 —— 探针实测，用户："太窄了"）',
       thin >= 460, f'实测 {thin}px（旧的窄框是 300px）')
    ok('C6b ★★ 前情提要那段字**没有越过**建议框的右边缘'
       '（两者都从内容列左边起排 —— 越过去就是钻到滚动条下面了）',
       bool(px['bbox']['recap']) and bool(px['bbox']['note'])
       and px['bbox']['recap'][1] <= px['bbox']['note'][1] + 4,
       f'前情 x1={px["bbox"]["recap"][1] if px["bbox"]["recap"] else "-"} '
       f'建议 x1={px["bbox"]["note"][1] if px["bbox"]["note"] else "-"}')

    # ★ 存的是**还原标记色之后**再拍的那一张 —— 给人看的图不该带着品红/纯黄
    #   （量像素那两张只用来数,不落盘）。
    # [EN] ★ What's saved is the shot taken **after restoring the marker colors** — the image for humans
    # [EN] shouldn't carry magenta/pure yellow
    # [EN] (the two pixel-measuring shots are only used for counting, not persisted).
    page.update()
    await asyncio.sleep(0.6)
    raw_clean = await page.take_screenshot() or raw
    if raw_clean:
        (OUT / 'author_note_dialog.png').write_bytes(raw_clean)
        ok('D1 截图落盘（给人看的那一份 —— **已经把标记色还原**）',
           (OUT / 'author_note_dialog.png').is_file())

    # ── ⑤ 端到端：打字 → 点「开始推演」→ 这一轮的 world 上真的有那句话 ──
    # [EN] ── ⑤ End-to-end: type → click "开始推演" → this round's world really has that sentence ──
    base = sum(1 for c in REPORT['checks'] if c['ok'])
    if field is None:
        ok('E1 ★★★ 端到端：填的建议真的跟着这一轮开跑（跳过：没找到输入框）', False)
        return
    field.value = NOTE
    page.update()
    await asyncio.sleep(0.3)
    #  ⚠ 找法照抄 `verify_autosave._find_btn`：`mk_btn` 主按钮是 **`FilledButton`**，
    #    文字挂在 `content`（`ft.Text`）上 —— 第一版只找 `ft.TextButton`，
    #    于是一个"开始推演"都找不到（而这个按钮明明就在屏幕上）。
    # [EN] ⚠ Find method copied from `verify_autosave._find_btn`: `mk_btn`'s primary button is a
    # [EN] **`FilledButton`**,
    # [EN] text hangs on `content` (`ft.Text`) — the first version only looked for `ft.TextButton`,
    # [EN] so it couldn't find a single "开始推演" (even though the button is clearly on screen).
    btn = None
    for c in VU.walk(dlg):
        if hasattr(c, 'on_click') and VU.text_of(c) == t('开始推演'):
            btn = c
            break
    ok('E1 找得到「开始推演」按钮（下面几条靠它）', btn is not None, '')
    if btn is None:
        return
    btn.on_click(None)                     # 真的走 _begin → _start_round → assemble
    # [EN] Really goes through _begin → _start_round → assemble
    ok('E1b ★★ 点下去之后，那句话**已经交到了 app 上**（`_pending_directive`）',
       str(getattr(app, '_pending_directive', '')) == NOTE,
       repr(getattr(app, '_pending_directive', ''))[:60])
    for _ in range(300):                   # 装配要建运行文件夹，给它时间
    # [EN] Assembly needs to create a run folder, give it time
        await asyncio.sleep(0.1)
        if app.session is not None:
            break
    sess = app.session
    ok('E2 ★★★ 这一轮真的起来了（否则下面那条测的是空气）',
       sess is not None and getattr(sess, 'world', None) is not None, '')
    if sess is None or getattr(sess, 'world', None) is None:
        return
    ok('E3 ★★★ **端到端**：对话框里填的那句话真的挂在**这一轮的 world** 上'
       '（不是只存在界面变量里）',
       D.of(sess.world) == NOTE, repr(D.of(sess.world))[:80])
    ok('E3b ★★★ `_pending_directive` **取一次就清**了'
       '（不清 = 下一轮没填也照样生效）',
       str(getattr(app, '_pending_directive', '')) == '',
       repr(getattr(app, '_pending_directive', ''))[:40])
    # ── ⑥ 中栏：填过的要**看得见**（这一条不依赖 `SHOW_OPENING`）──
    # [EN] ── ⑥ Middle column: what was filled in must be **visible** (this item doesn't depend on
    # [EN] `SHOW_OPENING`) ──
    #
    #  ⚠ 探针查出来的实情：本机 `.env` 里 `SHOW_OPENING=false` ⇒
    #    「每轮开场」那张卡片根本不推（`开场.md` 也不写）。所以"看得见"这条
    #    不能挂在开场卡片上 —— 那一行现在由 `RunLoop._push_author_note()`
    #    单独推（紧跟开头那句前情提要），**跟开场开关无关**。
    #    （开场卡片里的那一行另有判据：`verify_author_note` 的 D 组。）
    # [EN] ⚠ What the probe found: on this machine `.env` has `SHOW_OPENING=false` ⇒
    # [EN] the "every round opening" card isn't pushed at all (`开场.md` isn't written either). So "visible"
    # [EN] can't hang on the opening card — that line is now pushed separately by
    # [EN] `RunLoop._push_author_note()`
    # [EN] (right after the opening recap line), **independent of the opening switch**.
    # [EN] (The line inside the opening card has its own criterion: `verify_author_note`'s group D.)
    for _ in range(40):
        await asyncio.sleep(0.1)
        if any(isinstance(x, tuple) and NOTE in str(x[1])
               for x in (app._live_lines or [])):
            break
    rows = [x for x in (app._live_lines or []) if isinstance(x, tuple)]
    hits = [i for i, x in enumerate(rows)
            if str(x[2]) == 'note' and NOTE in str(x[1])]
    ok('E4 ★★★ 作者填过的要求**看得见**（中栏里真的出现了一行）',
       bool(hits), ' | '.join(str(x[1])[:36] for x in rows[:6]))
    # 顺序：开头那条「前情提要」之后
    # [EN] Order: after the "previously on" at the beginning
    i_recap = next((i for i, x in enumerate(rows)
                    if str(x[2]) == 'recap' and want[:12] in str(x[1])), -1)
    ok('E4b ★★★ 而且它**紧跟在开头那句前情提要后面**（顺序对 —— '
       '"演到哪儿了"在前，"往哪走"在后）',
       -1 not in (i_recap, (hits[0] if hits else -1))
       and i_recap < hits[0], f'recap@{i_recap} note@{hits[:2]}')
    # ★★ 真机端到端**再证一次"两边一样"**：中栏那句前情提要里就是对话框那段字
    # [EN] ★★ Real-machine end-to-end **prove "both sides are the same" once more**: the middle-column
    # [EN] recap line is exactly that dialog paragraph
    ok('E4c ★★★ 中栏那句「前情提要」里**就是对话框里显示的那一段字**'
       '（真机端到端再证一次"起笔说的 = 运行窗口念的"）',
       i_recap >= 0 and want in str(rows[i_recap][1]),
       f'中栏={str(rows[i_recap][1])[:70] if i_recap >= 0 else "-"!r}'
       f'\n        对话框={want[:70]!r}')
    ok('E4d ★★ 只在开头推**一次**（不是每个日界都念一遍 —— 那就成噪音了）',
       len(hits) == 1, f'出现 {len(hits)} 次')
    # ★ 收工：判据**不该在用户的机器上留一个跑着的轮次**。
    #   ⚠ 要**轮询等它真的停**，不能 `stop()` 完睡 0.8 秒就断言 ——
    #   主循环是在 `await asyncio.sleep` 的间隙里看 `_running` 的，
    #   那一觉睡完之前 `is_alive` 一直是 True（第一版就是这么假红的）。
    # [EN] ★ Wrap-up: the criterion **shouldn't leave a running round on the user's machine**.
    # [EN] ⚠ Must **poll and wait for it to actually stop**, can't `stop()` then sleep 0.8s and assert —
    # [EN] the main loop checks `_running` in the gaps of `await asyncio.sleep`,
    # [EN] before that sleep finishes `is_alive` stays True (the first version was falsely red exactly like
    # [EN] this).
    try:
        sess.stop()
    except Exception:                                        # noqa: BLE001
        pass
    for _ in range(200):
        await asyncio.sleep(0.1)
        if not bool(getattr(sess, 'is_alive', False)):
            break
    ok('E5 真机段收尾：这一轮**真的停下来了**（不给后面留下跑着的东西）',
       not bool(getattr(sess, 'is_alive', False)),
       f'is_alive={bool(getattr(sess, "is_alive", False))}')
    print(f'  （E 组通过 {sum(1 for c in REPORT["checks"] if c["ok"]) - base} 项）')


def _finish() -> int:
    out = OUT / 'author_note_ui_report.json'
    out.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2),
                   encoding='utf-8')
    bad = [c for c in REPORT['checks'] if not c['ok']]
    n = len(REPORT['checks'])
    print(f'\n起笔对话框 · 前情提要+建议 验证：{n - len(bad)}/{n}')
    for c in bad:
        print(f'  ✗ {c["name"]}')
    return 0 if not bad else 2


async def main(page: ft.Page) -> None:
    code = 1
    tmp = Path(tempfile.mkdtemp(prefix='nws_noteui_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    try:
        await _body(page, tmp)
        code = _finish()
    except BaseException:                                    # noqa: BLE001
        REPORT['checks'].append({'name': '★ 真机段崩了（自己留一条红）',
                                 'ok': False,
                                 'detail': traceback.format_exc()[-900:]})
        code = _finish()
    finally:
        VU.safe_rmtree(tmp, ignore_errors=True)
        await shutdown(page, code=code)


if __name__ == '__main__':
    ft.run(main, assets_dir=str(APP / 'assets'))
