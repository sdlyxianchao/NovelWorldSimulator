# -*- coding: utf-8 -*-
"""真机验证：开卷「交给 AI 之前」的确认（同意门）。

用户要的两件事：
  ① 到了 AI 那一步，**先大概看看用户传入了什么**；
  ② 两条警告分别取同意 —— 含正文要说清"正文会被发给大模型"；
     内容比较多要提醒"可能花不少 token"。

三部分：
  A. **概览数字**（`ingest/preview.py`）：分类统计、正文识别、预计 token/费用、
     截断判定、"内容多"的阈值；以及 `CAPS` 与 `ingest/*.py` 里真实的截取上限**是否一致**
     （这两处脱节，估出来的钱就是假的）。
  B. **管线的闸门行为**：gate 返回 False → 抛 `IngestDeclined` 且 **LLM 请求数 = 0**；
     gate 返回 True → 正常跑完；gate 自己抛异常 → **也中止**（fail closed，
     隐私闸门不能悄悄放行）；**不传 gate** → 老行为不变（回归）。
  C. **真机 GUI**：面板真的出现、日志/对话被让位、明细与两条警告都在、
     必勾项没勾时「同意」是灰的、勾完解锁、点同意后管线继续。

产出 `assets/screenshots/ingest_consent_*.png` + `ingest_consent_report.json`。

跑法：
    .venv/Scripts/python tools/verify_ingest_consent.py
    .venv/Scripts/python tools/verify_ingest_consent.py --logic-only   # 只跑 A/B

English:
Real-machine verification: the confirmation before opening a book "before handing to AI"
(consent gate).
Two things the user wants:
  ① At the AI step, **first take a rough look at what the user has passed in**;
  ② Consent for the two warnings separately — for body-text present, state clearly "the body text will be sent to the large model";
     for lots of content, remind "it may burn a lot of tokens".
Three parts:
  A. **Overview numbers** (`ingest/preview.py`): category stats, body-text detection, estimated tokens/cost,
     truncation decision, the "lots of content" threshold; and whether `CAPS` and the real truncation caps in `ingest/*.py` **are consistent**
     (if these two are out of sync, the estimated cost is fake).
  B. **Pipeline gate behavior**: gate returns False → raises `IngestDeclined` and **LLM request count = 0**;
     gate returns True → runs to completion normally; gate throws an exception itself → **also abort** (fail closed,
     a privacy gate must not silently let things through); **no gate passed** → old behavior unchanged (regression).
  C. **Real-machine GUI**: the panel really appears, logs/dialogue are yielded, details and both warnings are present,
     "Agree" is gray when required checkboxes are unchecked, unlocks after checking, and the pipeline continues after clicking agree.
Produces `assets/screenshots/ingest_consent_*.png` + `ingest_consent_report.json`.
How to run:
    .venv/Scripts/python tools/verify_ingest_consent.py
    .venv/Scripts/python tools/verify_ingest_consent.py --logic-only   # Run only A/B
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                       # noqa: E402
from util.flet_shutdown import shutdown, exit_now            # noqa: E402

CFG.set('MOCK_LLM', 'true')
CFG.set('LANGUAGE', 'zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'steps': [], 'produced': {}}


def rec(name: str, ok: bool, detail: str = '') -> bool:
    ok = bool(ok)
    report['steps'].append({'name': name, 'ok': ok, 'detail': str(detail)[:220]})
    print(f'  [{"OK" if ok else "FAIL"}] {name}' + (f' — {detail}' if detail else ''))
    return ok


class _Item:
    def __init__(self, cat: str, name: str, content: str):
        self.category, self.name, self.content = cat, name, content
        self.path, self.size, self.lines = Path(name), len(content), 0


def _fixture(root: Path, *, novel_paras: int = 3, with_novel: bool = True) -> Path:
    src = root / '雨夜来客'
    (src / '正文').mkdir(parents=True, exist_ok=True)
    (src / '大纲.md').write_text('# 大纲\n起：雨夜来客。\n承：旧事翻出。\n', encoding='utf-8')
    (src / '人物设定.md').write_text('# 人物\n## 主角\n掌柜。\n## 阿枝\n伙计。\n',
                                     encoding='utf-8')
    if with_novel:
        (src / '正文' / '第1章.md').write_text(
            '# 第1章\n\n雨脚敲着檐瓦。\n\n「你今日话里有话。」\n\n' * novel_paras,
            encoding='utf-8')
    return src


# ══════════════════════════════════════════════════════════════
#  A. 概览数字
# [EN] A. Overview numbers
# ══════════════════════════════════════════════════════════════
def test_brief() -> bool:
    print('\n── A. 概览数字 ──')
    from ingest import extractor
    from ingest.preview import BIG_SOURCE_CHARS, CAPS, build_brief, category_rows
    ok = True

    # ① CAPS 必须与代码里真实的截取上限一致（否则估的钱是假的）
    # [EN] ① CAPS must match the real truncation caps in the code (otherwise the estimated cost is fake)
    ok &= rec('CAPS[extract] == extractor._MAX_CONTENT',
              CAPS['extract'] == extractor._MAX_CONTENT,
              f"{CAPS['extract']} vs {extractor._MAX_CONTENT}")
    inline = {
        'genre': ('ingest/genre.py', r'sample\s*=\s*content\[:(\d+)\]'),
        # ★ 2026-10-10：风格卡与前情改成**按句截断**了（`head_sentences(content, 4000)`，
        #   理由：`content[:4000]` 会截在半句上，而**残句在模型眼里也是一种句式**）。
        #   这里因此要同时认两种写法 —— 判据要钉的是"**上限那个数**对不对"，
        #   不是"必须写成切片"。
        # [EN] ★ 2026-10-10: style card and prior context are now **truncated by sentence**
        # [EN] (`head_sentences(content, 4000)`,
        # [EN] reason: `content[:4000]` would cut mid-sentence, and **a truncated sentence is itself a sentence
        # [EN] pattern to the model**).
        # [EN] So here we must accept both forms — the criterion to pin down is whether "**that cap number**"
        # [EN] is correct,
        # [EN] not "it must be written as a slice".
        'style': ('ingest/style.py',
                  r'sample\s*=\s*(?:head_sentences\(content,\s*|content\[:)(\d+)\)?'),
        'progress': ('ingest/progress.py', r'outline_text\[:(\d+)\]'),
        'align': ('ingest/progress.py', r'content\[:(\d+)\]\s*\+\s*"\\n\.\.\.\(截断\)"'),
    }
    for key, (rel, pat) in inline.items():
        src = (APP_DIR / rel).read_text(encoding='utf-8')
        m = re.search(pat, src)
        got = int(m.group(1)) if m else -1
        ok &= rec(f'CAPS[{key}] == {rel} 里写死的截取上限',
                  got == CAPS[key], f'{CAPS[key]} vs 源码里 {got}')

    # ② 含正文的小项目
    # [EN] ② Small project with body text
    items = [_Item('正文', '第1章.md', '正' * 20_000),
             _Item('人物', '人物.md', '人' * 2_000),
             _Item('大纲', '大纲.md', '纲' * 1_500)]
    full = '\n\n'.join(f'【{i.category}】{i.name}\n{i.content}' for i in items)
    b = build_brief(items, full_text=full, novel_text=items[0].content,
                    outline_text=items[2].content, chapters={'第1章': items[0].content},
                    model='deepseek-chat', base_url='https://api.deepseek.com/v1')
    ok &= rec('识别出正文（文件数/字数）',
              b['has_novel'] and b['novel_files'] == 1 and b['novel_chars'] == 20_000,
              f"files={b['novel_files']} chars={b['novel_chars']}")
    ok &= rec('分类明细按固定顺序给出（正文在前）',
              [r[0] for r in category_rows(b)] == ['正文', '人物', '大纲'],
              str([r[0] for r in category_rows(b)]))
    ok &= rec('预计 token 与费用都算出来了',
              b['est_input_tokens'] > 0 and b['est_cost'] > 0,
              f"in={b['est_input_tokens']} out={b['est_output_tokens']} "
              f"¥{b['est_cost']:.4f}")
    ok &= rec('送出去的量按各步上限截断（不会把 20 万字全算成钱）',
              b['sent_chars_total'] == sum(
                  min(n, CAPS[k]) for k, n in
                  {'extract': len(full), 'genre': len(full), 'style': 20_000,
                   'progress': 1_500, 'align': 20_000}.items()),
              f"sent={b['sent_chars_total']} 上限合计={sum(CAPS.values())}")
    ok &= rec('源内容超过单次上限 → 标出会被截断',
              b['truncated'] is True)
    ok &= rec('2 万多字不算「内容比较多」', b['big'] is False,
              f"阈值 {b['big_threshold']}")

    # ③ 大项目 + 没有正文
    # [EN] ③ Large project + no body text
    big_items = [_Item('正文', f'第{i}.md', '字' * 3_000) for i in range(30)]
    big_full = '\n'.join(i.content for i in big_items)
    b2 = build_brief(big_items, full_text=big_full, novel_text=big_full,
                     model='deepseek-chat')
    ok &= rec('30 个正文文件（9 万字）→ 判为「内容比较多」',
              b2['big'] is True and b2['total_chars'] >= BIG_SOURCE_CHARS,
              f"total={b2['total_chars']} big={b2['big']}")
    b3 = build_brief([_Item('人物', '人物.md', '人' * 500)], full_text='人' * 500,
                     model='deepseek-chat')
    ok &= rec('没有正文时 has_novel=False（那条警告就不该出现）',
              b3['has_novel'] is False)
    ok &= rec('没配模型时费用是 0（不猜价）',
              build_brief([_Item('人物', 'a.md', '人' * 100)],
                          full_text='人' * 100)['est_cost'] == 0)

    # ④ 端点只留主机（API Key 常在 query/path 里，不能整串贴到界面上）
    # [EN] ④ Endpoint keeps only the host (API Key is often in the query/path, the whole string must not be
    # [EN] pasted into the UI)
    from util.text import host_of
    ok &= rec('host_of 只留「协议://主机」，把 key 与路径剥掉',
              host_of('https://api.deepseek.com/v1/chat?api_key=sk-SECRET')
              == 'https://api.deepseek.com',
              host_of('https://api.deepseek.com/v1/chat?api_key=sk-SECRET'))
    report['brief'] = {k: v for k, v in b.items() if k != 'caps'}
    return ok


# ══════════════════════════════════════════════════════════════
#  B. 管线闸门
# [EN] B. Pipeline gates
# ══════════════════════════════════════════════════════════════
def test_pipeline() -> bool:
    print('\n── B. 管线闸门 ──')
    from llm.router import llm
    from ingest.pipeline import IngestDeclined, run_ingest

    ok = True
    tmp = Path(tempfile.mkdtemp(prefix='nws_consent_'))
    counts = {'n': 0}

    def _on_llm(ev):
        if ev.get('type') == 'request':
            counts['n'] += 1

    llm.add_listener(_on_llm)
    try:
        # ── ① gate 说"不同意" → 中止，且一次请求都不发 ──
        # [EN] ── ① gate says "no" → abort, and not a single request is sent ──
        src = _fixture(tmp / 'a')
        counts['n'] = 0
        seen: list = []

        def gate_no(brief):
            seen.append(brief)
            return False

        raised = None
        try:
            asyncio.run(run_ingest(src, gate=gate_no))
        except IngestDeclined as e:
            raised = str(e)
        ok &= rec('不同意时抛 IngestDeclined（不是崩，是中止）', raised is not None,
                  raised or '没抛')
        ok &= rec('不同意时 **LLM 请求数 = 0**（一分钱没花）', counts['n'] == 0,
                  f'requests={counts["n"]}')
        ok &= rec('闸门只问一次', len(seen) == 1, f'{len(seen)} 次')
        ok &= rec('闸门拿到的是真概览（含正文、有 token 估算）',
                  bool(seen) and seen[0]['has_novel'] and seen[0]['est_input_tokens'] > 0,
                  json.dumps({k: seen[0][k] for k in
                              ('has_novel', 'est_input_tokens')}, ensure_ascii=False)
                  if seen else '')

        # ── ② gate 说"同意" → 跑完，且请求确实发生了 ──
        # [EN] ── ② gate says "yes" → runs to completion, and the request actually happened ──
        src2 = _fixture(tmp / 'b')
        counts['n'] = 0
        n_gate = {'n': 0}

        def gate_yes(brief):
            n_gate['n'] += 1
            return True

        res = asyncio.run(run_ingest(src2, gate=gate_yes))
        ok &= rec('同意后管线正常跑完（拿到 IngestResult）',
                  res is not None and hasattr(res, 'settings'), type(res).__name__)
        ok &= rec('同意后才真的开始调 LLM', counts['n'] > 0, f'requests={counts["n"]}')
        ok &= rec('同意路径下闸门也只问一次', n_gate['n'] == 1, f'{n_gate["n"]} 次')

        # ── ③ 闸门自己抛异常 → 也要中止（fail closed）──
        # [EN] ── ③ gate throws an exception itself → also abort (fail closed) ──
        src3 = _fixture(tmp / 'c')
        counts['n'] = 0

        def gate_boom(brief):
            raise RuntimeError('模拟确认界面炸了')

        raised2 = None
        try:
            asyncio.run(run_ingest(src3, gate=gate_boom))
        except IngestDeclined as e:
            raised2 = str(e)
        ok &= rec('确认环节自己出错时**也中止**（隐私闸门不许悄悄放行）',
                  raised2 is not None, raised2 or '没抛')
        ok &= rec('出错中止时同样零请求', counts['n'] == 0, f'requests={counts["n"]}')

        # ── ④ 不传 gate → 老行为不变 ──
        # [EN] ── ④ no gate passed → old behavior unchanged ──
        src4 = _fixture(tmp / 'd')
        counts['n'] = 0
        res4 = asyncio.run(run_ingest(src4))
        ok &= rec('不传 gate 时行为不变（老调用方不受影响）',
                  res4 is not None and counts['n'] > 0, f'requests={counts["n"]}')
    finally:
        llm.remove_listener(_on_llm)
        import verify_ui_common as VU
        VU.safe_rmtree(tmp, ignore_errors=True)
    return ok


# ══════════════════════════════════════════════════════════════
#  C. 真机 GUI
# [EN] C. Real-machine GUI
# ══════════════════════════════════════════════════════════════
async def _check_button_visible(page, ui) -> bool:
    """在**屏幕像素**里找「同意」按钮，确认它真的画出来了（没被面板裁掉）。

    **为什么要先把按钮/面板涂成标记色**：
      - 按钮本体底色是米黄 `C['border']`，和满屏的输入框/面板边框**同一个色**，
        按原色根本分不出来；
      - 走 `C['accent']` 也不通 —— 屏幕上唯一的 accent 色块是**进度条**
        （12px 高、也成块），第一版就把它当成按钮量了一次（量错对象）。
    所以临时把两者涂成荧光品红 / 青色（全项目没人用过的颜色），量完再改回去。
    **只动颜色、不动几何**，量出来的就是它们真实的位置与大小。
    
        English:
    Find the "Agree" button in **screen pixels**, and confirm it is actually drawn (not clipped by
    the panel).
        **Why paint the button/panel with a marker color first**:
          - The button's own base color is beige `C['border']`, the **same color** as the input boxes/panel borders all over the screen,
            so by its original color it simply cannot be distinguished;
          - Going with `C['accent']` also fails -- the only accent-colored block on screen is the **progress bar**
            (12px tall, also a block), and the first version measured it as the button once (measured the wrong object).
        So temporarily paint both fluorescent magenta / cyan (colors nobody in the whole project uses), measure, then change back.
        **Only change color, not geometry**, so what you measure is their real position and size.
    """
    from PIL import Image
    btn = ui.get('consent_agree')
    panel = ui.get('consent_panel')
    if btn is None or panel is None:
        return rec('确认面板里有「同意」按钮句柄', False, '拿不到句柄')

    # 两个标记色：按钮底 品红、面板底 青（全项目都没人用这两种颜色）
    # [EN] Two marker colors: button background magenta, panel background cyan (nobody in the whole project
    # [EN] uses these two colors)
    MARK_BTN = '#ff00ff'
    MARK_PANEL = '#00ffff'
    old_btn = getattr(btn, 'bgcolor', None)
    old_panel = getattr(panel, 'bgcolor', None)
    try:
        btn.bgcolor = MARK_BTN
        panel.bgcolor = MARK_PANEL
        page.update()
        await asyncio.sleep(0.5)
        shot = await page.take_screenshot()
    finally:
        btn.bgcolor = old_btn
        panel.bgcolor = old_panel
        try:
            page.update()
        except Exception:                                      # noqa: BLE001
            pass

    png = OUT / 'ingest_consent_btn_probe.png'
    png.write_bytes(shot)
    im = Image.open(png).convert('RGB')
    px = im.load()
    W, H = im.size

    def is_btn(c) -> bool:
        r, g, b = c
        return r > 190 and b > 190 and g < 90          # 品红
        # [EN] magenta

    def is_panel(c) -> bool:
        r, g, b = c
        return g > 190 and b > 190 and r < 90          # 青
        # [EN] cyan

    def _segs(ys: list[int], need: int = 8) -> list[tuple[int, int]]:
        out, st, prev = [], None, None
        for y in ys:
            if st is None:
                st = prev = y
            elif y - prev <= 4:
                prev = y
            else:
                out.append((st, prev))
                st = prev = y
        if st is not None:
            out.append((st, prev))
        return [s for s in out if s[1] - s[0] >= need]

    b_segs = _segs([y for y in range(H)
                    if sum(1 for x in range(0, W, 2) if is_btn(px[x, y])) >= 10])
    p_segs = _segs([y for y in range(H)
                    if sum(1 for x in range(0, W, 2) if is_panel(px[x, y])) >= 60])
    report['produced']['mark_button'] = b_segs
    report['produced']['mark_panel'] = p_segs

    ok = rec('「同意」按钮真的渲染在屏幕上（标记色块存在，高 ≥ 8px）',
             bool(b_segs), f'按钮标记块={b_segs}')
    ok &= rec('确认面板的底色块也量到了（拿来当"容器范围"）',
              bool(p_segs), f'面板标记块={p_segs}')
    if b_segs and p_segs:
        y0, y1 = b_segs[-1]
        p0, p1 = p_segs[-1]
        ok &= rec('按钮整块落在面板之内（没被裁掉）',
                  p0 <= y0 and y1 <= p1,
                  f'面板 y{p0}..{p1}（高 {p1 - p0 + 1}），'
                  f'按钮 y{y0}..{y1}（高 {y1 - y0 + 1}）')
    return ok


async def test_gui(page) -> bool:
    import flet as ft

    import verify_ui_common as VU
    ok = True
    tmpdirs = [Path(tempfile.mkdtemp(prefix='nws_consent_gui_'))]
    try:
        proj_root = tmpdirs[0] / 'projects'
        proj_root.mkdir(parents=True, exist_ok=True)
        VU.isolate_projects_dir(proj_root)
        from gui.app_flet import NovelWorldApp
        from llm.router import llm

        counts = {'n': 0}

        def _on_llm(ev):
            if ev.get('type') == 'request':
                counts['n'] += 1

        app = NovelWorldApp()
        app.main(page)
        page.enable_screenshots = True
        page.update()
        await asyncio.sleep(2.0)

        src = _fixture(tmpdirs[0] / 'src')
        app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.5)
        app._wizard_path = str(src)
        app._wizard_name = '同意门验证'
        app._wizard_opts['ai_optimize'] = False
        # ⚠ 本脚本测的是**同意门**，不是 4.5.3 的「AI 补全并回写引用文件夹」。
        #   那一步默认开、而且也会把 `panes` 让给它的清单面板 —— 不关掉的话，
        #   「同意后面板收起来、日志/对话回到版面里」那条会**假红**
        #   （面板确实收起来了，只是换成了另一个面板）。它由
        #   `tools/verify_repair_writeback.py` 专门验。
        # [EN] ⚠ This script tests the **consent gate**, not 4.5.3's "AI completes and writes back the
        # [EN] reference folder".
        # [EN] That step is on by default and also hands `panes` over to its checklist panel — if not turned
        # [EN] off,
        # [EN] the case "after consent the panel collapses, logs/dialogue return to the layout" will **false
        # [EN] red**
        # [EN] (the panel did collapse, it just swapped to another panel). It is
        # [EN] verified specifically by `tools/verify_repair_writeback.py`.
        app._wizard_opts['repair_source'] = False
        counts['n'] = 0
        llm.add_listener(_on_llm)
        app._do_import(page)
        st = app._ingest_state

        # 等确认面板出现
        # [EN] Wait for the confirmation panel to appear
        panel = None
        for _ in range(150):
            await asyncio.sleep(0.1)
            ui = st.get('ui') or {}
            if ui.get('consent_panel') is not None and ui['consent_panel'].visible:
                panel = ui
                break
        ui = st.get('ui') or {}
        ok &= rec('本地读完后**停住**，确认面板真的显示出来',
                  panel is not None, f"visible={getattr(ui.get('consent_panel'), 'visible', None)}")
        ok &= rec('面板出现时正好是"还没调用过 AI"（请求数 0）',
                  counts['n'] == 0, f'requests={counts["n"]}')
        if panel is None:
            report['ok'] = False
            return False

        facts = [str(c.value) for c in ui['consent_facts'].controls]
        warns = [str(c.value) for c in ui['warn_box'].controls
                 if isinstance(c, ft.Text)]
        boxes = list(ui['consent_boxes'] or [])
        joined_f = '\n'.join(facts)
        joined_w = '\n'.join(warns)

        report['gui'] = {'title': str(ui['consent_title'].value or ''),
                         'facts': facts, 'warns': warns,
                         'box_labels': [str(b.label) for b in boxes]}
        ok &= rec('标题说明了这是"交给 AI 之前"',
                  '交给 AI' in str(ui['consent_title'].value or ''),
                  str(ui['consent_title'].value or '')[:60])
        ok &= rec('列了"传入什么"：文件数 + 分类明细',
                  '文件' in joined_f and '正文' in joined_f,
                  joined_f.replace('\n', ' ｜ ')[:140])
        ok &= rec('给了预计 token 与费用',
                  'token' in joined_f and '¥' in joined_f,
                  next((x for x in facts if 'token' in x), '')[:120])
        ok &= rec('警告①：含正文 → 说清会被发给大模型',
                  any('正文' in w and ('大模型' in w or '发送' in w) for w in warns),
                  next((w for w in warns if '正文' in w), '')[:120])
        ok &= rec('警告①：展示了发送目标（或演示模式提示）',
                  any('将发送到' in w or '演示模式' in w for w in warns),
                  next((w for w in warns if '将发送到' in w or '演示模式' in w), '')[:120])
        ok &= rec('警告①：有必勾的同意框',
                  any('同意' in str(b.label) for b in boxes),
                  ' ｜ '.join(str(b.label) for b in boxes)[:120])
        ok &= rec('没勾之前「同意」是灰的',
                  bool(getattr(ui['consent_agree'], 'disabled', False)))

        # 勾上 → 解锁
        # [EN] Check it → unlock
        for b in boxes:
            b.value = True
            if getattr(b, 'on_change', None):
                b.on_change(None)
        ok &= rec('勾完必勾项后「同意」解锁',
                  not bool(getattr(ui['consent_agree'], 'disabled', True)))

        page.update()
        await asyncio.sleep(0.3)
        report['produced']['shot'] = str(OUT / 'ingest_consent_panel.png')
        (OUT / 'ingest_consent_panel.png').write_bytes(await page.take_screenshot())

        # 真点「同意」→ 管线继续
        # [EN] Actually click "Agree" → pipeline continues
        ui['consent'](True)
        for _ in range(200):
            await asyncio.sleep(0.1)
            if counts['n'] > 0:
                break
        ok &= rec('点同意后管线继续，AI 才开始被调用', counts['n'] > 0,
                  f'requests={counts["n"]}')
        ok &= rec('同意后面板收起来、日志/对话回到版面里',
                  not bool(getattr(ui['consent_panel'], 'visible', True))
                  and bool(getattr(ui['panes'], 'visible', False)))

        # 收尾：别把管线跑完（跑完会建项目、生成肖像）
        # [EN] Wrap up: don't run the pipeline to completion (completing it creates a project and generates a
        # [EN] portrait)
        for _ in range(60):
            await asyncio.sleep(0.1)
            if st.get('phase') in ('chat', 'finishing') or not st.get('running'):
                break
        try:
            ui['cancel'](None)
        except Exception:                                      # noqa: BLE001
            pass
        await asyncio.sleep(0.6)

        # ── 再走一次：这次**不同意** ──
        # [EN] ── Go through again: this time **do not agree** ──
        counts['n'] = 0
        app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.4)
        app._wizard_path = str(src)
        app._wizard_name = '不同意验证'
        app._wizard_opts['ai_optimize'] = False
        # ⚠ `force=True`：这一遍用的还是**同一个素材夹**（本脚本要走"同意门那一次
        #   不同意"的路径，换个文件夹反而偏离了它要测的东西）—— 而 2026-10-07 起，
        #   同一个素材再开卷会先弹「这本已经开过卷了」拦一道（那条路
        #   `tools/verify_ingest_duplicate.py` 专门验）。这里明确说"我知道会撞，
        #   不是本脚本要测的东西"，跟 `app._wizard_opts['repair_source']=False`
        #   是同一类做法：调的是产品自己的参数，不是给程序开后门。
        # [EN] ⚠ `force=True`: this pass still uses the **same material folder** (this script needs to go
        # [EN] through the "consent gate that time,
        # [EN] no consent" path; switching folders would deviate from what it's meant to test) — and since
        # [EN] 2026-10-07,
        # [EN] opening the same material again pops up "this book has already been opened" as a blocker first
        # [EN] (that path is
        # [EN] verified specifically by `tools/verify_ingest_duplicate.py`). Here it explicitly says "I know it
        # [EN] will collide,
        # [EN] that's not what this script tests", which is the same kind of approach as
        # [EN] `app._wizard_opts['repair_source']=False`:
        # [EN] calling the product's own parameters, not opening a back door for the program.
        app._do_import(page, force=True)
        st2 = app._ingest_state
        for _ in range(150):
            await asyncio.sleep(0.1)
            ui2 = st2.get('ui') or {}
            if ui2.get('consent_panel') is not None and ui2['consent_panel'].visible:
                break
        ui2 = st2.get('ui') or {}
        ok &= rec('第二次也照样停下来问', bool(getattr(ui2.get('consent_panel'),
                                                     'visible', False)))
        if ui2.get('consent'):
            ui2['consent'](False)
        for _ in range(60):
            await asyncio.sleep(0.1)
            if not st2.get('running'):
                break
        ok &= rec('点「不同意」后：**一个 LLM 请求都没有**',
                  counts['n'] == 0, f'requests={counts["n"]}')
        ok &= rec('点「不同意」后摄取结束（对话框关掉、任务停下）',
                  not st2.get('running'), f"running={st2.get('running')}")
        # ⚠ 日志里**不只是 `Text`**（v1.39 起阶段之间插了分隔线 + 空行的 `Container`）——
        # 直接读 `.value` 会 `AttributeError`，而且报错在主协程里、窗口还开着，
        # 脚本会一直挂着（连挂两次、8 分钟零输出）。统一走 `VU.log_cells()`。
        # [EN] ⚠ The log has **not just `Text`** (since v1.39, separator lines + blank-line `Container`s are
        # [EN] inserted between stages) —
        # [EN] reading `.value` directly will `AttributeError`, and the error is in the main coroutine with the
        # [EN] window still open,
        # [EN] so the script hangs forever (hung twice, 8 minutes with zero output). Always go through
        # [EN] `VU.log_cells()`.
        log_txt = '\n'.join(VU.log_cells(ui2.get('log_list').controls
                                         if ui2.get('log_list') else []))
        ok &= rec('日志里写明了"未调用任何 AI"',
                  '未调用任何 AI' in log_txt or '中止' in log_txt,
                  next((l for l in log_txt.split('\n') if '中止' in l or '未调用' in l),
                       '')[:110])

        # ── 第三次：**大项目** → 第二条警告（内容多/花 token）与截断提示 ──
        # [EN] ── Third time: **large project** → second warning (lots of content / burns tokens) and
        # [EN] truncation notice ──
        counts['n'] = 0
        big_src = tmpdirs[0] / 'big'
        (big_src / '正文').mkdir(parents=True, exist_ok=True)
        for i in range(6):
            (big_src / '正文' / f'第{i}.md').write_text(
                '# 第%d章\n\n' % i + '雨脚敲着檐瓦，灯被风扑得晃了晃。\n' * 1500,
                encoding='utf-8')
        app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.4)
        app._wizard_path = str(big_src)
        app._wizard_name = '大项目验证'
        app._wizard_opts['ai_optimize'] = False
        app._do_import(page)
        st3 = app._ingest_state
        for _ in range(150):
            await asyncio.sleep(0.1)
            ui3 = st3.get('ui') or {}
            if ui3.get('consent_panel') is not None and ui3['consent_panel'].visible:
                break
        ui3 = st3.get('ui') or {}
        facts3 = [str(c.value) for c in ui3['consent_facts'].controls]
        warns3 = [str(c.value) for c in ui3['warn_box'].controls
                  if isinstance(c, ft.Text)]
        boxes3 = list(ui3['consent_boxes'] or [])
        report['gui_big'] = {'facts': facts3, 'warns': warns3,
                             'box_labels': [str(b.label) for b in boxes3]}
        ok &= rec('大项目：警告②（内容比较多）出现',
                  any('内容比较多' in w for w in warns3),
                  next((w for w in warns3 if '内容比较多' in w), '')[:120])
        ok &= rec('大项目：给了本次预计费用并问是否继续',
                  any('token' in w and '¥' in w for w in warns3),
                  next((w for w in warns3 if '¥' in w), '')[:140])
        ok &= rec('大项目：两条警告 → 两个必勾框',
                  len(boxes3) == 2, ' ｜ '.join(str(b.label) for b in boxes3)[:160])
        ok &= rec('大项目：提示了"中间会被截断"（源内容超过单次上限）',
                  any('截断' in f for f in facts3),
                  next((f for f in facts3 if '截断' in f), '')[:140])
        report['produced']['shot_big'] = str(OUT / 'ingest_consent_big.png')

        for b in boxes3:                       # 只勾一个 → 仍应是灰的
        # [EN] Check only one → should still be gray
            b.value = True
            if getattr(b, 'on_change', None):
                b.on_change(None)
            break
        ok &= rec('大项目：只勾一个必勾项时「同意」仍是灰的',
                  bool(getattr(ui3['consent_agree'], 'disabled', True)))
        # 全勾上 → 按钮变实心主色，**这时才**在像素里找它。
        # （禁用态的按钮是灰的，按主色找必然找不到 —— 第一版就踩了这个。）
        # [EN] Check all → button becomes solid primary color, **only then** look for it in the pixels.
        # [EN] (a disabled button is gray, so searching by primary color will definitely fail — the first
        # [EN] version tripped on this.)
        for b in boxes3:
            b.value = True
            if getattr(b, 'on_change', None):
                b.on_change(None)
        ok &= rec('大项目：两项都勾上后「同意」解锁',
                  not bool(getattr(ui3['consent_agree'], 'disabled', True)))
        page.update()
        await asyncio.sleep(0.4)
        (OUT / 'ingest_consent_big.png').write_bytes(await page.take_screenshot())
        ok &= await _check_button_visible(page, ui3)
        if ui3.get('consent'):
            ui3['consent'](False)              # 收尾：不同意，别真把它跑完
            # [EN] Wrap up: do not agree, don't actually run it to completion
        for _ in range(60):
            await asyncio.sleep(0.1)
            if not st3.get('running'):
                break
        ok &= rec('大项目：不同意同样零请求', counts['n'] == 0, f'requests={counts["n"]}')

        llm.remove_listener(_on_llm)
        report['ok'] = bool(ok)
    except Exception:                                          # noqa: BLE001
        report['ok'] = False
        report['error'] = traceback.format_exc()[-1800:]
        print(report['error'])
    finally:
        import verify_ui_common as VU2
        for d in tmpdirs:
            VU2.safe_rmtree(d, ignore_errors=True)

    _write_report(report.get('logic_ok', True))
    # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
    #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
    #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
    # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` throws
    # [EN] CancelledError
    # [EN] and cancels this coroutine; the line `exit_now(...)` written after `await shutdown(page)`
    # [EN] **never executed** (exit code always 0 = false green). See `util/flet_shutdown.shutdown()`.
    await shutdown(page, code=0 if (report.get('ok') and report.get('logic_ok', True)) else 1)


def _write_report(logic_ok: bool) -> None:
    (OUT / 'ingest_consent_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    n_ok = sum(1 for s in report['steps'] if s['ok'])
    print(f'\n共 {len(report["steps"])} 项，通过 {n_ok} 项')
    print('→', '全部通过' if (report.get('ok') and logic_ok) else '有失败')


if __name__ == '__main__':
    logic_only = '--logic-only' in sys.argv
    logic_ok = test_brief() and test_pipeline()
    report['logic_ok'] = logic_ok
    if logic_only:
        report['ok'] = logic_ok
        (OUT / 'ingest_consent_report_logic.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        n_ok = sum(1 for s in report['steps'] if s['ok'])
        print(f'\n逻辑验证：{n_ok}/{len(report["steps"])} 项通过')
        sys.exit(0 if logic_ok else 1)

    # ⚠ **报告必须在 `ft.run()` 之前写完**（收尾三件套：写报告 → 关窗口 → 结束进程）。
    #   原先是 `ft.run(test_gui)` **之后**才写报告 —— 而 `ft.run` 会**阻塞到窗口关闭才返回**，
    #   这里又没人关窗口，于是脚本跑完全部断言后**静默挂死**（实测挂 8 分钟以上、
    #   一行输出都没有，看着像"跑得慢"，其实是收尾漏了；`ft.run` 后面那几行等于死代码）。
    #   现在把收尾放进 `test_gui` 自己最后：`_write_report()` → `await shutdown(page)`
    #   → `exit_now()`，进程自己退干净。
    # [EN] ⚠ **The report must be fully written before `ft.run()`** (the three wrap-up steps: write report
    # [EN] → close window → end process).
    # [EN] Originally the report was written **after** `ft.run(test_gui)` — but `ft.run` **blocks and only
    # [EN] returns after the window closes**,
    # [EN] and here nobody closes the window, so after running all assertions the script **silently hangs**
    # [EN] (measured 8+ minutes,
    # [EN] not a single line of output, looks like "slow", but actually the wrap-up was missed; the lines
    # [EN] after `ft.run` are dead code).
    # [EN] Now the wrap-up is placed at the end of `test_gui` itself: `_write_report()` → `await
    # [EN] shutdown(page)`
    # [EN] → `exit_now()`, and the process exits cleanly on its own.
    import flet as ft
    ft.run(test_gui)
