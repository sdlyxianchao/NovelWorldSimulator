# -*- coding: utf-8 -*-
"""验证：帮助面板的「问个问题」—— 以《使用说明》为根据的使用问答。

要证的四件事（每条都要能红）：

  ① **检索准** —— 问使用上的问题能命中对应章节；问跟软件无关的问题**不命中**
     （命中一堆不相干的东西比不命中更糟：模型会拿着它硬答）。
  ② **不编** —— prompt 里明确写死"只根据这些内容""没写就说没写""不许凭常识补功能"，
     并且**检索为空时一次请求都不发**（什么都不给模型还要它回答 = 让它编）。
  ③ **双语各走各的** —— 中文界面读 `使用说明.md`、英文界面读 `User_Manual.md`，
     问题和手册得是同一种语言才对得上。
  ④ **界面上真能用到** —— 帮助面板有「帮助信息 / 问个问题」两个选项卡、切页真的换内容、
     点示例问题能看到回答、气泡**分左右**、第二问带上第一轮的上下文（多轮）。
     不看代码，看屏幕。

用法：.venv\\Scripts\\python.exe tools/verify_help_qa.py
产出：assets/screenshots/help_qa_*.png / help_qa_report.json

English:
Verification: the help panel's "Ask a question" —— usage Q&A based on the "Usage Manual".
Four things to prove (each one must be able to go red):
  ① **Accurate retrieval** —— usage questions hit the corresponding section; questions unrelated to the software **do not match**
     (matching a bunch of irrelevant stuff is worse than not matching: the model will use it to force an answer).
  ② **No making things up** —— the prompt explicitly hard-codes "only based on this content", "if not written, say it's not written", "do not fill in features from common sense",
     and **when retrieval is empty, not a single request is sent** (giving the model nothing and still asking it to answer = making it up).
  ③ **Each language goes its own way** —— the Chinese UI reads `使用说明.md`, the English UI reads `User_Manual.md`,
     the question and the manual must be in the same language to line up.
  ④ **Really usable in the UI** —— the help panel has two tabs "Help info / Ask a question", switching tabs really changes content,
     clicking a sample question shows an answer, bubbles are **left/right distinct**, the second question carries the first turn's context (multi-turn).
     Don't look at the code, look at the screen.
Usage: .venv\\Scripts\\python.exe tools/verify_help_qa.py
Output: assets/screenshots/help_qa_*.png / help_qa_report.json
"""
from __future__ import annotations

import asyncio
import json
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

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


# ══════════════════════════════════════════════════════════════
#  A. 纯逻辑（不起窗口）
# [EN] A. Pure logic (no window)
# ══════════════════════════════════════════════════════════════
def logic_checks() -> None:
    from research import manual_qa as M

    # ── A1 切段 ──
    # [EN] ── A1 Segmentation ──
    zh = M.load_sections('zh')
    en = M.load_sections('en')
    ok('A1 说明书被切成足够多的节（中英各 ≥ 60 节）',
       len(zh) >= 60 and len(en) >= 60, f'zh={len(zh)} en={len(en)}')
    ok('A1b 标题带**父级路径**（`A › B`）—— 光看「4.5.0 第 2 步…」不知道在讲哪一步',
       any('›' in s['title'] for s in zh)
       and any('›' in s['title'] for s in en),
       [s['title'] for s in zh if '›' in s['title']][:2])
    ok('A1c 中英读的是**两份不同的文档**（不是同一份被翻了两遍）',
       zh[1]['title'] != en[1]['title'], f"zh={zh[1]['title']} / en={en[1]['title']}")

    # ── A2 中文检索：正例（问题 → 期望命中的小节里必须出现的关键词）──
    # [EN] ── A2 Chinese retrieval: positive cases (question → keywords that must appear in the expected
    # [EN] matched section) ──
    good = [('怎么设置运行模式', '运行模式'), ('顶级规则怎么写', '顶级规则'),
            ('帮助面板怎么看', '帮助面板'), ('怎么开卷', '开卷'),
            ('存档在哪里', '存档'), ('怎么暂停', '运行控制'),
            ('token 烧太快怎么办', 'token'), ('对话插图有哪几种', '对话')]
    miss = []
    for q, want in good:
        hits = M.search(q, 'zh', top_k=3)
        if not hits or not any(want in h['title'] for h in hits[:2]):
            miss.append(f'{q} → {[h["title"][:18] for h in hits[:2]]}')
    ok('A2 ★ 使用类问题都能命中对应章节（top2 里出现期望关键词）',
       not miss, str(miss[:4]))

    # ── A3 中文检索：反例（跟软件无关的问题**不许**命中）──
    # [EN] ── A3 Chinese retrieval: negative cases (questions unrelated to the software are **not allowed**
    # [EN] to match) ──
    bad_q = ['今天天气怎么样', '晚饭吃什么', '帮我写一首诗', '推荐一部电影', '谢谢']
    leaked = [q for q in bad_q if M.search(q, 'zh', top_k=3)]
    ok('A3 ★ 跟软件无关的问题**不命中**（宁可说"没写"，也别塞几节不相干的）',
       not leaked, str(leaked))

    # ── A4 英文检索 ──
    # [EN] ── A4 English retrieval ──
    en_bad = []
    for q in ('How do I set the run mode?', 'How do I write top-level rules?',
              'What dialogue image modes are there?'):
        if not M.search(q, 'en', top_k=2):
            en_bad.append(q)
    ok('A4 英文问题在英文手册里也能命中（示例按钮点下去要有东西）',
       not en_bad, str(en_bad))

    # ── A5 全是虚词的问题不检索 ──
    # [EN] ── A5 Questions made entirely of function words are not retrieved ──
    ok('A5 问题里只有疑问词（"怎么""如何"）时不检索',
       M.search('怎么', 'zh') == [] and M.search('how to', 'en') == [],
       f"{M.search('怎么', 'zh')}")

    # ── A6 prompt：把"不许编"写死 ──
    # [EN] ── A6 prompt: hard-code "no making things up" ──
    hits = M.search('顶级规则怎么写', 'zh', top_k=2)
    p = M.build_prompt('顶级规则怎么写', hits, 'zh')
    ok('A6 ★ prompt 里写死了「只根据这些内容」+「没写就说没写」+「不许凭常识补功能」',
       ('只根据' in p) and ('没有写到' in p) and ('不要凭一般常识' in p.replace('**', '')),
       p[:80].replace('\n', '⏎'))
    ok('A6b prompt 里**真的有**检索到的章节标题与正文',
       all(h['title'] in p for h in hits) and hits[0]['body'][:20] in p, '')
    ok('A6c prompt 还要求它给出「依据」（便于回查）', '依据' in p, '')
    pe = M.build_prompt('How do I set the run mode?', M.search('How do I set the run mode?', 'en'),
                        'en')
    ok('A6d 英文 prompt 同样是英文的那一套（只根据 / 说不全 / 不许编）',
       'only these chapters' in pe and 'say so plainly' in pe, pe[:80].replace('\n', '⏎'))

    # ── A7 ★ 检索为空时**一次请求都不发** ──
    # [EN] ── A7 ★ When retrieval is empty, **not a single request is sent** ──
    from llm.router import llm
    calls = {'n': 0}
    real_chat = llm.chat

    async def counting(*a, **kw):
        calls['n'] += 1
        return await real_chat(*a, **kw)

    llm.chat = counting
    try:
        res = asyncio.run(M.answer('今天天气怎么样', 'zh'))
    finally:
        llm.chat = real_chat
    ok('A7 ★★ 检索为空时**连模型都不调**（什么都不给它还要它答 = 让它编）',
       calls['n'] == 0 and res['ok'] is False and res['why'] == 'no_hit'
       and '没有找到' in res['text'],
       f"调用{calls['n']}次 why={res['why']} text={res['text'][:30]}")

    # ── A8 结果拼装 ──
    # [EN] ── A8 Result assembly ──
    res2 = asyncio.run(M.answer('顶级规则怎么写', 'zh'))
    md = M.format_answer(res2)
    ok('A8 MOCK 下能走完一次问答（有正文、有 sources）',
       res2['ok'] and res2['text'].strip() and res2['sources'],
       f"ok={res2['ok']} sources={res2['sources'][:2]}")
    ok('A8b 回答拼装里带上了「参考章节」（没自带依据时补一行）',
       '参考章节' in md or '依据' in md, md[:60].replace('\n', '⏎'))

    # ── A9 多轮：聊天式之后加的（追问要能接上下文）──
    # [EN] ── A9 Multi-turn: added after the chat-style version (follow-ups must pick up context) ──
    hist = [{'role': 'user', 'content': '顶级规则怎么写？'},
            {'role': 'assistant', 'content': '放在 设定/顶级规则.md，文件名带"规则"。'}]
    p1 = M.build_prompt('那放在哪个文件夹', hits, 'zh', history=hist)
    ok('A9 ★ 有历史时 prompt 里带上「此前对话」（否则"那怎么改"里的"那"指什么它不知道）',
       '此前对话' in p1 and '顶级规则怎么写' in p1, p1[:60].replace('\n', '⏎'))
    ok('A9b 没有历史时**不出现**这一段（别凭空多一段空的历史）',
       '此前对话' not in M.build_prompt('顶级规则怎么写', hits, 'zh'), '')
    # ⚠ 夹具要用**真实形状**（问/答交替）。第一版塞了 12 条全是 user 的记录，
    #   于是"只带最近 3 轮（=6 条）"在屏幕上表现为 6 个「问：」，
    #   断言却写「问：≤ 3」→ 功能正常时也是红的（判据的错，不是产品的错）。
    # [EN] ⚠ Fixtures must use the **real shape** (alternating question/answer). The first version stuffed
    # [EN] in 12 records that were all user,
    # [EN] so "only the last 3 turns (= 6 records)" showed on screen as 6 "Q:" entries,
    # [EN] but the assertion said "Q: ≤ 3" → it was red even when the feature worked (the criterion was
    # [EN] wrong, not the product).
    hist_many: list = []
    for i in range(12):
        hist_many += [{'role': 'user', 'content': f'第{i}个旧问题'},
                      {'role': 'assistant', 'content': f'第{i}个旧回答'}]
    _ht = M._history_text(hist_many, 'zh')
    ok('A9c 历史有上限：攒了 12 轮也只带最近 `HISTORY_MAX_TURNS` 轮',
       _ht.count('问：') == M.HISTORY_MAX_TURNS
       and '第0个旧问题' not in _ht and '第11个旧问题' in _ht,
       f"问：{_ht.count('问：')} 条；{_ht[:70]}".replace('\n', '⏎'))
    ok('A9d 英文界面用英文那套（Q/A 与 Earlier conversation）',
       'Earlier conversation' in M.build_prompt('where', hits, 'en', history=hist)
       and 'Q：' in M.build_prompt('where', hits, 'en', history=hist),
       '')

    # ── A10 追问时检索才借上一轮的话 ──
    # [EN] ── A10 On follow-up, retrieval borrows the previous turn's words ──
    ok('A10 ★ 问题自己说不清（"那怎么改？"）→ 检索拼上上一轮的问题',
       '顶级规则' in M._search_query('那怎么改？', hist),
       M._search_query('那怎么改？', hist))
    ok('A10b 问题自己够清楚 → **不借**历史（否则问到第三个问题时，检索还停在第一个话题）',
       M._search_query('对话插图有哪几种', hist) == '对话插图有哪几种',
       M._search_query('对话插图有哪几种', hist))
    ok('A10c 没有历史时追问就按原样检索（不报错、不空转）',
       M._search_query('那怎么改？', None) == '那怎么改？', '')

    report['zh_sections'] = len(zh)
    report['sample_hits'] = [{'q': q, 'top': (M.search(q, 'zh', top_k=1) or [{}])[0].get('title', '')}
                             for q, _ in good[:4]]


# ══════════════════════════════════════════════════════════════
#  B. 真机
# [EN] B. Real device
# ══════════════════════════════════════════════════════════════
def bubble_pixel_stats(png: bytes) -> dict:
    """量两种**标记色**（品红 = 作者气泡、青 = AI 气泡）的像素分布。

    为什么要这样量：控件树里"气泡的 `horizontal_alignment` 是 END" **不等于**
    屏幕上它真的靠在右边（本项目栽过太多次"树里对、屏幕上不对"）。
    而按原色去找也不行 —— 界面上别的浅色（面板底、输入框底）会撞上来
    （实测 `#f2ece0` 一抓两万多个像素，全是对话框底色）。所以：**只动颜色、
    不动几何**，把气泡底色临时换成全项目没人用的荧光色，量完改回去。
    
        English:
    Measure the pixel distribution of two **marker colors** (magenta = author bubble, cyan = AI
    bubble).
        Why measure this way: in the control tree, "the bubble's `horizontal_alignment` is END" **does not mean**
        it's really on the right on screen (this project has fallen for "right in the tree, wrong on screen" too many times).
        And finding by the original color doesn't work either —— other light colors in the UI (panel background, input box background) collide with it
        (measured `#f2ece0` grabs over twenty thousand pixels, all dialog background). So: **only change color,
        not geometry**, temporarily swap the bubble background color for a fluorescent color nobody in the whole project uses, then change it back after measuring.
    """
    import io

    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert('RGB')
    W, H = im.size
    px = im.load()
    out: dict = {'W': W, 'H': H}
    for key, want in (('user', (255, 0, 255)), ('ai', (0, 255, 255))):
        xs: list = []
        for y in range(0, H, 2):
            for x in range(0, W, 2):
                c = px[x, y]
                if (abs(c[0] - want[0]) <= 12 and abs(c[1] - want[1]) <= 12
                        and abs(c[2] - want[2]) <= 12):
                    xs.append(x)
        out[key] = ({'n': len(xs), 'x_min': min(xs), 'x_max': max(xs),
                     'x_mean': round(sum(xs) / len(xs))} if xs
                    else {'n': 0, 'x_min': -1, 'x_max': -1, 'x_mean': -1})
    return out


async def gui_checks(page: ft.Page, app) -> None:
    async def shot(name: str) -> bytes:
        png = await page.take_screenshot()
        (OUT / name).write_bytes(png or b'')
        return png or b''

    print('  [B] 打开帮助…', flush=True)
    # 帮助面板 → 找到「问个问题」按钮
    # [EN] Help panel → find the "Ask a question" button
    app.show_help_dialog()
    await asyncio.sleep(0.8)
    dlgs = VU.open_dialogs(page)
    print('  [B] 帮助已开，开始找按钮…', flush=True)
    hdlg = next((d for d in dlgs if any('帮 助' in x for x in VU.all_texts(d))), None)
    ok('B1 帮助面板能打开（下面是问问题按钮的前提）', hdlg is not None, len(dlgs))

    # ── 两个选项卡（2026-10-06 把「帮助」与「问个问题」合成一个窗口）──
    # [EN] ── Two tabs (2026-10-06 merged "Help" and "Ask a question" into one window) ──
    tabs = next((c for c in VU.walk(hdlg)
                 if hasattr(c, 'selected_index') and hasattr(c, 'length')), None)
    # ⚠ 别用 `VU.walk()` 去找 `ft.Tab` —— **Tab 实例不在 `controls` / `content` 里**，
    #   它们挂在 `TabBar.tabs` 这个列表上，walk 走不到（第一版因此把 labels 读成
    #   `[None]`，功能明明是对的）。要问 TabBar 要 `tabs`。
    # [EN] ⚠ Don't use `VU.walk()` to find `ft.Tab` —— **Tab instances are not in `controls` / `content`**,
    # [EN] they hang on the `TabBar.tabs` list, walk can't reach them (the first version therefore read
    # [EN] labels as
    # [EN] `[None]`, when the feature was obviously correct). Ask the TabBar for `tabs`.
    tabbar = next((c for c in VU.walk(hdlg) if getattr(c, 'tabs', None)), None)
    labels = [str(getattr(x, 'label', '') or '')
              for x in (getattr(tabbar, 'tabs', None) or [])]
    ok('B2 ★ 帮助面板里有**两个选项卡**：「帮助信息」+「问个问题」',
       tabs is not None and len(labels) == 2
       and any('帮助信息' in x for x in labels)
       and any('问个问题' in x for x in labels),
       f'tabs={tabs is not None} labels={labels}')
    ok('B2b 选项卡的 length 与实际页数一致（写错会让最后一页点不到）',
       tabs is not None and int(getattr(tabs, 'length', 0) or 0) == 2,
       getattr(tabs, 'length', None))

    png_tab0 = await shot('help_tab_manual.png')          # 第 1 页：说明书
    # [EN] Page 1: manual
    print('  [B] 切到「问个问题」…', flush=True)
    if tabs is not None:
        tabs.selected_index = 1
    try:
        page.update()
    except Exception:                                      # noqa: BLE001
        pass
    await asyncio.sleep(0.8)

    qdlg = next((d for d in VU.open_dialogs(page)
                 if any('帮 助' in x for x in VU.all_texts(d))), None)
    texts = VU.all_texts(qdlg) if qdlg else []
    ok('B3 ★ 切到第 2 页后，输入框与「发送」按钮都在（那一页真的建出来了）',
       qdlg is not None and any('发送' in x for x in texts)
       and any(x.strip() == t('问题') for x in texts),
       [x[:16] for x in texts if len(x) < 20][:8])
    ok('B3b 页面上说明了「回答只依据随程序附带的说明书」',
       any('只依据' in x for x in texts), [x[:30] for x in texts][:4])
    # ⚠ 判据别写成「含有问号的文本 ≥ 2」—— 示例问题本身**不带问号**
    #   （「怎么设置运行模式」），那种写法在功能正常时也是红的（实测踩过）。
    #   直接拿示例文案去比：删掉示例按钮它就会红。
    # [EN] ⚠ Don't write the criterion as "text containing a question mark ≥ 2" —— the sample questions
    # [EN] themselves **have no question mark**
    # [EN] ("How to set the run mode"), that style is red even when the feature works (hit this in
    # [EN] practice).
    # [EN] Compare directly against the sample text: delete the sample button and it goes red.
    _ex = {t('怎么设置运行模式'), t('顶级规则怎么写'), t('对话插图有哪几种')}
    ok('B3c 页面上有**现成的示例问题**（空框最难的是不知道问什么）',
       sum(1 for x in texts if x in _ex) >= 2, [x for x in texts if x in _ex])

    png_tab1 = await shot('help_tab_ask.png')             # 第 2 页：问问题
    # [EN] Page 2: ask a question
    ok('B3d ★ 两张截图**不一样**（切选项卡真的换了内容，不是摆设）',
       len(png_tab0) > 20000 and len(png_tab1) > 20000 and png_tab0 != png_tab1,
       f'{len(png_tab0)} vs {len(png_tab1)}')

    # 点示例问题 → 等回答；同时**盯着发给模型的 prompt**（多轮只能靠它证）
    # [EN] Click a sample question → wait for the answer; at the same time **watch the prompt sent to the
    # [EN] model** (multi-turn can only be proven by it)
    from llm.router import llm as _llm
    real_chat = _llm.chat
    seen_prompts: list = []

    async def spy_chat(*a, **kw):
        try:
            seen_prompts.append(str(a[1] if len(a) > 1 else kw.get('messages')))
        except Exception:                                  # noqa: BLE001
            seen_prompts.append('')
        return await real_chat(*a, **kw)

    ex = [b for b in VU.walk(qdlg)
          if hasattr(b, 'on_click') and b.on_click and VU.text_of(b)
          and VU.text_of(b) in _ex]
    ok('B4 示例问题按钮存在且带回调', len(ex) >= 2, [VU.text_of(b) for b in ex][:3])

    def _bubbles(dlg) -> list:
        """气泡 = `chat_bubble()` 造的那个 Column（`tight=True` 且 `spacing=0`）。
                English:
        Bubble = the Column created by `chat_bubble()` (`tight=True` and `spacing=0`).
        """
        return [c for c in VU.walk(dlg)
                if type(c).__name__ == 'Column' and getattr(c, 'tight', False)
                and not getattr(c, 'spacing', 1)]

    _llm.chat = spy_chat
    try:
        print('  [B] 点第一个示例问题…', flush=True)
        if ex:
            ex[0].on_click(None)
            for _ in range(40):                  # 最多等 8 秒（MOCK 很快）
            # [EN] Wait at most 8 seconds (MOCK is fast)
                await asyncio.sleep(0.2)
                if len(_bubbles(qdlg)) >= 2:
                    break
        ans_texts = VU.all_texts(qdlg) if qdlg else []
        report['answer_texts'] = [x for x in ans_texts if len(x) > 12][:4]
        ok('B5 ★ 点了示例问题之后，聊天里**真的出现了回答**（问 + 答两个气泡）',
           any('演示' in x or '依据' in x for x in ans_texts)
           and len(_bubbles(qdlg)) >= 2,
           report['answer_texts'])
        aligns = [str(getattr(c, 'horizontal_alignment', '')).lower()
                  for c in _bubbles(qdlg)]
        ok('B5b ★ 气泡**分左右**：作者的问句靠右、回答靠左（聊天最要紧的那个信号）',
           any('end' in a for a in aligns) and any('start' in a for a in aligns),
           aligns)

        # 第二问 → 多轮：历史要真的发给模型
        # [EN] Second question → multi-turn: history must really be sent to the model
        print('  [B] 点第二个示例问题…', flush=True)
        if len(ex) >= 2:
            ex[1].on_click(None)
            for _ in range(40):
                await asyncio.sleep(0.2)
                if len(_bubbles(qdlg)) >= 4:
                    break
        ok('B7 ★ 追问之后气泡变成 4 条（两问两答）—— 聊天是**多轮**的',
           len(_bubbles(qdlg)) >= 4, f'{len(_bubbles(qdlg))} 条')
        ok('B7b ★★ 第二次请求的 prompt 里带上了「此前对话」+ 第一轮的问与答',
           len(seen_prompts) >= 2
           and '此前对话' in seen_prompts[-1]
           and '运行模式' in seen_prompts[-1],
           f'请求 {len(seen_prompts)} 次；末次含「此前对话」='
           f'{bool(seen_prompts and "此前对话" in seen_prompts[-1])}')
    finally:
        _llm.chat = real_chat

    # ── B8 ★★ 标记色取证：气泡真的画在屏幕上，而且**左右分明** ──
    #   上面 B5b 查的是控件属性（树里对），这一条查屏幕（**真的画出来了没有**）。
    #   做法：把气泡底色的模块常量换成荧光色，再发一问 → 新气泡带荧光色 →
    #   量像素。只动颜色不动几何，量到的就是真实位置。
    # [EN] ── B8 ★★ Marker-color forensics: the bubble is really drawn on screen, and **left/right are
    # [EN] clearly distinct** ──
    # [EN] B5b above checks control properties (correct in the tree), this one checks the screen (**is it
    # [EN] really drawn**).
    # [EN] Approach: swap the bubble background color module constant for a fluorescent color, then send
    # [EN] another question → the new bubble has the fluorescent color →
    # [EN] measure pixels. Only change color, not geometry, so what's measured is the real position.
    import gui.app_flet as AC
    old_user, old_ai = AC.BUBBLE_USER_BG, AC.BUBBLE_AI_BG
    AC.BUBBLE_USER_BG, AC.BUBBLE_AI_BG = '#ff00ff', '#00ffff'
    try:
        print('  [B] 换标记色再问一次…', flush=True)
        if len(ex) >= 3:
            ex[2].on_click(None)
            for _ in range(40):
                await asyncio.sleep(0.2)
                if len(_bubbles(qdlg)) >= 6:
                    break
        png_mark = await shot('help_bubble_marker.png')
    finally:
        AC.BUBBLE_USER_BG, AC.BUBBLE_AI_BG = old_user, old_ai
    st = bubble_pixel_stats(png_mark)
    report['bubble_px'] = st
    ok('B8 ★★ 气泡**真的画在屏幕上**，且作者的靠右、AI 的靠左（像素取证，不是查控件属性）',
       st['user']['n'] > 200 and st['ai']['n'] > 200
       and st['user']['x_min'] > st['ai']['x_min']
       and st['user']['x_min'] > st['W'] * 0.5,
       st)

    print('  [B] 截图…', flush=True)
    png = await shot('help_qa_dialog.png')
    print('  [B] 截图完成', flush=True)
    report['shot_bytes'] = len(png)
    ok('B6 截图有内容（不是空白页）', len(png) > 20000, len(png))


async def entry(page: ft.Page) -> None:
    from gui.app_flet import NovelWorldApp
    tmp = Path(tempfile.mkdtemp(prefix='nws_helpqa_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.0)
    try:
        await gui_checks(page, app)
    except BaseException:                                      # noqa: BLE001
        report['fatal'] = traceback.format_exc()
    finally:
        VU.safe_rmtree(tmp, ignore_errors=True)
    # ⚠ **收尾必须在关窗之前**：`page.window.destroy()` 会抛 CancelledError
    #   把本协程取消掉，写在 `await shutdown(page)` 之后的代码**永远不会执行**
    #   （本项目所有脚本的退出码曾经因此恒为 0 = 假绿，
    #    见 `util/flet_shutdown.shutdown()`）。
    #   `ft.run()` **不会自己返回**（窗口不关、UI 循环就一直跑），
    #   所以这行也必须在这里，而不是 ft.run 之后。
    # [EN] ⚠ **Cleanup must happen before closing the window**: `page.window.destroy()` will throw
    # [EN] CancelledError
    # [EN] and cancel this coroutine, code written after `await shutdown(page)` **will never execute**
    # [EN] (all scripts in this project once had an exit code permanently stuck at 0 = false green because
    # [EN] of this,
    # [EN] see `util/flet_shutdown.shutdown()`).
    # [EN] `ft.run()` **does not return on its own** (as long as the window isn't closed, the UI loop keeps
    # [EN] running),
    # [EN] so this line must also be here, not after ft.run.
    await shutdown(page, code=finish())


def finish() -> int:
    """写报告 + 打印结论 + 返回退出码（真机与 --logic-only 共用）。
        English:
    Write report + print conclusion + return exit code (shared by real device and --logic-only).
    """
    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    (OUT / 'help_qa_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"\n帮助问答验证：{len(report['checks']) - len(bad)}/{len(report['checks'])}")
    for c in bad:
        print('  ✗', c['name'], '|', c['detail'])
    if report.get('fatal'):
        print(report['fatal'][-1200:])
    print('报告：assets/screenshots/help_qa_report.json')
    return 0 if report['ok'] else 2


# ══════════════════════════════════════════════════════════════
def main() -> int:
    if '--logic-only' in sys.argv:
        try:
            logic_checks()
        except BaseException:                                  # noqa: BLE001
            report['fatal'] = traceback.format_exc()
        return finish()
    try:
        logic_checks()                                         # A 组先跑，早暴露问题
        # [EN] Run group A first, surface problems early
    except BaseException:                                      # noqa: BLE001
        report['fatal'] = traceback.format_exc()
    ft.run(entry)              # entry 内部会 shutdown（带上退出码）
    # [EN] entry shuts down internally (with the exit code)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
