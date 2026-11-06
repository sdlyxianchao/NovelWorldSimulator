# -*- coding: utf-8 -*-
"""**「起笔」对话框的「前情提要 + 作者走向建议」**（2026-10-11）。

用户原话（分两半，正好对应下面两组判据）：

    「我希望在起笔的时候，可以有一个地方加上用户自己对于故事接下来走向的建议。
      我觉得可以在提笔的前情提要的下面（我不确定现在的提笔对话框带不带前情提要，
      如果没加记得加上，然后在下面加上"您对接下来剧情发展的建议"这个文本框）
      **而且请确保这里的前情提要和后续运行窗口对话显示的时候给的前情提要一样**。」

于是两件事：

| 一件 | 判据 |
|---|---|
| **前情提要，两边必须逐字一样** | A 组（拿**真装配出来的 `RunLoop`** 对答案） |
| **建议真的管用**（不是摆在对话框里的装饰） | B/C/D 组（行为级抓真发出去的 messages） |

为什么 A 组非得"拿真 loop 对答案"
--------------------------------
"看起来差不多"是本项目最忌讳的验收方式。前情提要有**两条取数路**
（续跑走 `resume_recap(plan)`；没跑过走 `opening_context(设定集那段话)`），
两路都可能被改成"对话框自己算一遍" —— 那样在**改到某一路**时不会立刻暴露，
要等用户点完起笔发现"对话框说的和屏幕上念的不一样"才暴露。
所以这里直接**装配一个真的 `RunLoop`**，比它的 `_recap_text()`。

跑法：`.venv\\Scripts\\python.exe tools\\verify_author_note.py`
产出：`assets/screenshots/author_note_report.json`

⚠ 全程 `MOCK_LLM`、不联网、不开窗口（界面那一半在 `verify_author_note_ui.py`）。
⚠ 夹具：`verify_run_control.make_project` + 临时目录，**不碰用户的项目**。

English:
**The "Start Writing" dialog's "Recap + Author's Direction Suggestion"** (2026-10-11).
The user's exact words (in two halves, matching the two criteria groups below):
    "I want it so that at the start of writing, there's a place to add the user's own suggestion for where the story goes next.
      I think it can go below the recap when starting to write (I'm not sure whether the current start-writing dialog has a recap;
      if not, remember to add it, then below it add the text box "your suggestion for the next plot development")
      **And please make sure the recap here is the same as the recap shown in the subsequent run-window conversation.**"
So two things:
| One thing | Criterion |
|---|---|
| **Recap, both sides must be word-for-word identical** | Group A (check the answer against a **really assembled `RunLoop`**) |
| **The suggestion is actually useful** (not a decoration sitting in the dialog) | Groups B/C/D (behavioral: capture the messages really sent) |
Why group A must "check the answer against a real loop"
--------------------------------
"Looks about the same" is the most taboo acceptance method in this project. The recap has **two
data-fetch paths**
(resume goes through `resume_recap(plan)`; never run goes through `opening_context(the bit of
setting-bible text)`),
either path could be changed to "the dialog computes it itself" -- then changing **one of the
paths** wouldn't be exposed immediately,
and would only surface after the user finishes start-writing and finds "what the dialog says
differs from what's read on screen".
So here we directly **assemble a real `RunLoop`** and compare its `_recap_text()`.
How to run: `.venv\\Scripts\\python.exe tools\\verify_author_note.py`
Output: `assets/screenshots/author_note_report.json`
WARNING: `MOCK_LLM` throughout, no network, no windows (the UI half is in
`verify_author_note_ui.py`).
WARNING: Fixture: `verify_run_control.make_project` + a temp directory, **does not touch the
user's project**.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

from config import CFG                                  # noqa: E402
CFG.set('MOCK_LLM', 'true')

REPORT: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


def read(rel: str) -> str:
    p = APP / rel
    return p.read_text(encoding='utf-8', errors='replace') if p.is_file() else ''


def between(text: str, start: str, end: str = '') -> str:
    i = text.find(start)
    if i < 0:
        return ''
    j = text.find(end, i + len(start)) if end else -1
    return text[i:j if j > 0 else len(text)]


# ══════════════════════════════════════════════════════════════════════
#  A —— 前情提要：**两边逐字一样**（用户点名的第二条）
# [EN] A -- Recap: **both sides must be word-for-word identical** (the second item the user named)
# ══════════════════════════════════════════════════════════════════════
class _Proj:
    """够用的假项目（`plan()` 只用 `list_runs()`）—— 与 `verify_start_point` 同款。
        English:
    A good-enough fake project (`plan()` only uses `list_runs()`) -- same style as
    `verify_start_point`.
    """

    def __init__(self, runs: list):
        self._runs = list(runs)

    def list_runs(self):
        return list(self._runs)


def _real_round(tmp: Path, name: str, *, resume_recap: str = '',
                user_directive: str = ''):
    """真装配一轮（`make_project` 夹具 + 真 `assemble`）。返回 (proj, run, loop, world, db)。
        English:
    Really assemble one round (`make_project` fixture + real `assemble`). Returns (proj, run, loop,
    world, db).
    """
    from verify_run_control import make_project
    from store.runfolder import RunFolder
    from sim import setup as SU
    proj = make_project(tmp / name, nodes=3)
    run = RunFolder(proj.root, f'第1次模拟{name}').create()
    loop, world, db = SU.assemble(proj, run, image_hook=lambda *a, **k: None,
                                  resume_recap=resume_recap,
                                  user_directive=user_directive)
    return proj, run, loop, world, db


def recap_same_checks(tmp: Path) -> None:
    print('\n── A 前情提要：起笔对话框 == 运行窗口（逐字）──')
    from sim import resume as R
    from sim import setup as SU
    from sim.setup import load_settings

    # ── A1 没跑过（fresh）──
    #    对话框手上只有"设定集里那段世界观文本"，所以走 `worldview_text_of`；
    #    运行窗口那边是 `RunLoop._recap_text()` 落到 `opening_context(world.worldview_text)`。
    # [EN] -- A1 Never run (fresh) --
    # [EN] The dialog only has "that bit of worldview text from the setting bible", so it goes through
    # [EN] `worldview_text_of`;
    # [EN] On the run-window side, `RunLoop._recap_text()` lands on
    # [EN] `opening_context(world.worldview_text)`.
    proj, _run, loop, world, _db = _real_round(tmp, 'fresh')
    wvt = SU.worldview_text_of(load_settings(proj.settings_dir))
    p_fresh = {'kind': R.FRESH, 'day': 1, 'minutes': 480, 'calendar': '',
               'partial_day': None, 'run': None, 'stop': None}
    got_dlg = R.start_recap(p_fresh, worldview_text=wvt)
    got_win = loop._recap_text()
    ok('A1 ★★★ **没跑过**时：起笔对话框算出来的前情提要 == 运行窗口 `_recap_text()`'
       '（逐字相同 —— 用户点名要求的那条）',
       bool(got_dlg) and got_dlg == got_win,
       f'对话框={got_dlg[:60]!r}\n        窗口  ={got_win[:60]!r}')

    # ── A2 续跑（resume / next_day）──
    #    造一个真有停点 + 真有正文的上一轮，`plan()` 读它 → 两边都该是
    #    「上一回演到 第 N 天 …，说到：…」。
    # [EN] -- A2 Resume run (resume / next_day) --
    # [EN] Build a previous round that really has a stop point + real body text, `plan()` reads it -> both
    # [EN] sides should be
    # [EN] "Last time we played to Day N ..., it said: ...".
    prev = tmp / '上一轮' / '第1次模拟2026-10-10-09-00'
    (prev / '每天的生活').mkdir(parents=True, exist_ok=True)
    (prev / '每天的生活' / '第001天.md').write_text(
        '# 第 1 天 · 第1天·辰时 · 晴\n> 在场：主角、柳氏\n\n## 辰时 08:00\n'
        '**场景** 临河茶肆\n\n▸ 出场 主角（已在场）\n\n'
        '· 动作 柳氏：把茶盏搁下\n\n主角：账本在楼上。\n\n柳氏：我上去拿。\n',
        encoding='utf-8')
    R.write_stop_point(prev, day=1, minutes=8 * 60 + 54, calendar='第1天·辰时',
                       shichen='辰时', day_done=False, ticks_today=12,
                       scene='临河茶肆', reason='手动停止', partial_day=1)
    p_res = R.plan(_Proj([prev]))
    ok('A2a 前置：夹具是"当天演了一半"（`resume`）',
       p_res['kind'] == R.RESUME and p_res['day'] == 1, str(p_res)[:90])
    # 忠实模拟 `_start_round`：它把 `RESUME.resume_recap(plan)` 交给装配
    # [EN] Faithfully simulate `_start_round`: it hands `RESUME.resume_recap(plan)` to assembly
    _proj2, _run2, loop2, _w2, _db2 = _real_round(
        tmp, 'resume', resume_recap=R.resume_recap(p_res))
    got_dlg2 = R.start_recap(p_res)
    got_win2 = loop2._recap_text()
    ok('A2 ★★★ **续跑**时：两边逐字相同（含"上一回演到 第 N 天 · 时辰（地点），说到："）',
       bool(got_dlg2) and got_dlg2 == got_win2 and '上一回演到' in got_dlg2,
       f'对话框={got_dlg2[:70]!r}\n        窗口  ={got_win2[:70]!r}')

    # ── A3 两条路**共用一份实现**（不是各写一遍）──
    # [EN] -- A3 Both paths **share one implementation** (not written out twice) --
    from director import day_plan as DAYPLAN
    wv = str(getattr(world, 'worldview_text', '') or '')
    ok('A3 ★★★ `opening_context(文本)` 与 `_opening_context(world)` 是同一份实现'
       '（同文本 → 同结果；不是"两个函数碰巧都对"）',
       bool(wv) and DAYPLAN.opening_context(wv) == DAYPLAN._opening_context(world),
       f'{DAYPLAN.opening_context(wv)[:50]!r}')

    # ── A4 读不到设定集 ⇒ **照实为空**（不编一句顶上）──
    # [EN] -- A4 Setting bible unreadable => **empty, as is** (don't make up a line to fill in) --
    empty = R.start_recap(p_fresh, worldview_text='')
    ok('A4 ★★ 读不到设定集时：前情提要**是空的**（不编、也不抛）'
       '—— 空着比"用错的东西充数"诚实',
       empty == '', repr(empty))

    # ── A5 对话框里显示的**就是**这段（静态接线）──
    # [EN] -- A5 What's displayed in the dialog is **exactly** this text (static wiring) --
    g = read('gui/app_flet.py')
    dlg = between(g, 'def show_start_story_dialog', 'def _latest_run_folder')
    ok('A5 ★★★ 起笔对话框真的**把这段显示出来**了（`start_recap()` 的结果进了控件）',
       'R.start_recap(resume_plan, worldview_text=' in dlg
       and dlg.count('recap') >= 3,
       f'start_recap 出现={dlg.count("start_recap(")} 次')
    ok('A5b ★★ 对话框算前情提要用的**是同一个 plan**（`resume_plan`）'
       '—— 换一个 plan 算就会答出另一天的前情',
       'resume_plan = self._resume_plan(proj)' in dlg
       and 'self._pending_resume = resume_plan' in dlg
       and "'_pending_resume', None) or self._resume_plan(proj)" in g,
       '')


# ══════════════════════════════════════════════════════════════════════
#  B —— 建议真的进了提示词（行为级：抓真发出去的 messages）
# [EN] B -- The suggestion actually made it into the prompt (behavioral: capture the messages really
# [EN] sent)
# ══════════════════════════════════════════════════════════════════════
NOTE = '这三天先埋一个误会，别急着解释'


def note_in_prompt_checks(tmp: Path) -> None:
    print('\n── B 建议真的进提示词（行为级）──')
    from crew import agents as A
    from sim import directive as D
    from agent.core import Agent
    import llm.router as R

    _proj, _run, _loop, world, db = _real_round(tmp, 'note', user_directive=NOTE)

    # ── B1 剧组那一路：`craft_block`（14 个职位 + 演员 + 导演的唯一拼装口）──
    # [EN] -- B1 The crew path: `craft_block` (the sole assembly point for 14 roles + actors + director) --
    A.bind_world(world)
    blk = A.craft_block('screenwriter', '悬疑灵异', '单元剧')
    ok('B1 ★★★ 剧组职位读得到的"手艺块"里**真的有作者那句话**'
       '（`craft_block` 是全剧组唯一的拼装口 —— 接在这里就一个都漏不掉）',
       D.PROMPT_HEAD in blk and NOTE in blk, blk[-160:].replace('\n', ' | '))
    ok('B1b ★★ 它排在**最后**（顺序就是优先级：这一轮作者的要求压过通用手艺）'
       '—— 抬头还写明了"它是意图、不是设定，人物与世界照旧不能违背"',
       blk.rfind(D.PROMPT_HEAD) > blk.find('这本书的特别要求')
       and '一条都不能违背' in blk,
       f'位置={blk.rfind(D.PROMPT_HEAD)} 项目档={blk.find("这本书的特别要求")}')

    # ── B2 **不填时逐字退回**（不能因为多了这个功能，没填也变一句提示词）──
    # [EN] -- B2 **When not filled in, verbatim fallback** (adding this feature must not turn an empty
    # [EN] field into a prompt line) --
    _saved = D.of(world)
    blk_with = A.craft_block('screenwriter', '悬疑灵异', '单元剧')
    D.attach(world, '')                       # 填了空白
    # [EN] filled with whitespace
    blk_blank = A.craft_block('screenwriter', '悬疑灵异', '单元剧')
    delattr(world, D.ATTR)                    # 连属性都拿掉 = "没有这个功能"时的样子
    # [EN] even the attribute is removed = what it looks like when "this feature doesn't exist"
    blk_absent = A.craft_block('screenwriter', '悬疑灵异', '单元剧')
    ok('B2 ★★★ **不填**（或填了空白）时：拼出来的手艺块与"没有这个功能"时'
       '**逐字相同**（一个字都不多加）',
       D.PROMPT_HEAD not in blk_blank and blk_blank == blk_absent
       and len(blk_blank) < len(blk_with),
       f'空白={len(blk_blank)} 无属性={len(blk_absent)} 有建议={len(blk_with)}')
    D.attach(world, _saved)

    # ── B3 抓**真发出去的 messages**（演员决策）──
    # [EN] -- B3 Capture the **messages really sent** (actor decision) --
    seen: list = []
    _orig = R.llm.chat

    async def fake(tier, messages, **kw):
        if kw.get('purpose') in ('agent_decide',):
            seen.append([dict(m) for m in messages])
        return await _orig(tier, messages, **kw)
    R.llm.chat = fake
    try:
        name = next(iter(world.people))
        ag = Agent(world.people[name], db, world)
        asyncio.run(ag.decide(''))
    finally:
        R.llm.chat = _orig
    txt = ' '.join(str(m.get('content') or '') for m in (seen[-1] if seen else []))
    ok('B3 ★★★ 演员决策**真发出去的提示词**里有作者那句话'
       '（不是"函数里拼了但没发出去"）',
       bool(seen) and D.PROMPT_HEAD in txt and NOTE in txt,
       f'采到 {len(seen)} 次调用，长度 {len(txt)}')

    # ── B3b 对照：不填时那条决策提示词里一个字都没有 ──
    # [EN] -- B3b Control: when not filled in, that decision prompt contains not a single word --
    seen2: list = []
    _orig2 = R.llm.chat

    async def fake2(tier, messages, **kw):
        if kw.get('purpose') == 'agent_decide':
            seen2.append([dict(m) for m in messages])
        return await _orig2(tier, messages, **kw)
    R.llm.chat = fake2
    try:
        D.attach(world, '')
        A.bind_world(world)
        ag2 = Agent(world.people[name], db, world)
        asyncio.run(ag2.decide(''))
    finally:
        R.llm.chat = _orig2
        D.attach(world, _saved)
        A.bind_world(world)
    txt2 = ' '.join(str(m.get('content') or '') for m in (seen2[-1] if seen2 else []))
    ok('B3b ★★★ 对照组：**不填**时这篇决策提示词里连抬头都没有'
       '（"没人填就别加戏"）',
       bool(seen2) and D.PROMPT_HEAD not in txt2 and NOTE not in txt2, '')

    # ── B4 不许并进设定（用户明令：设定不许被这些沾上）──
    # [EN] -- B4 Must not be merged into the settings (user's explicit order: settings must not be touched
    # [EN] by these) --
    before = str(getattr(world, 'worldview_text', '') or '')
    D.attach(world, NOTE)
    ok('B4 ★★★ 建议**没有并进 `worldview_text`**（那是"这本书是什么样"，'
       '混进去下一轮 / 下一次开卷都会带着上一轮的建议 —— 静默的错误）',
       NOTE not in str(getattr(world, 'worldview_text', '') or '')
       and str(getattr(world, 'worldview_text', '') or '') == before, '')
    D.attach(world, _saved)

    # ── B5 规范化：截断 / 折叠 ──
    # [EN] -- B5 Normalization: truncate / collapse --
    long_note = '往东走。' * 400
    v = D.norm(long_note)
    ok('B5 ★★ 超长会**截断到上限**并留一个省略号（提示词要塞进每一拍每个人的调用里）',
       len(v) <= D.MAX_CHARS and v.endswith('…'), f'{len(v)} 字')
    multi = D.norm('第一句。\n\n第二句。\n   第三句。')
    ok('B5b ★★ 多行输入**折成一段**（换行多了会把后面的材料挤散）',
       '\n' not in multi and '第一句。 第二句。 第三句。' == multi, repr(multi))
    ok('B5c ★★ 空白输入 → 空串（调用方按空串判"没填"）',
       D.norm('   \n \t ') == '' and D.norm(None) == '', '')


# ══════════════════════════════════════════════════════════════════════
#  C —— 接线：从对话框到 world，一条都不能断
# [EN] C -- Wiring: from dialog to world, not a single link may be broken
# ══════════════════════════════════════════════════════════════════════
def wiring_checks(tmp: Path) -> None:
    print('\n── C 接线（真装配 + 源码）──')
    from sim import directive as D
    from sim import setup as SU

    # ── C1 真装配：传进去 → 挂在 world 上 ──
    # [EN] -- C1 Real assembly: pass it in -> it's attached to world --
    _p, _r, _l, world, _db = _real_round(tmp, 'wire', user_directive=NOTE)
    ok('C1 ★★★ `assemble(user_directive=…)` 真的把它挂到了这一轮的 world 上'
       '（不是只加了个参数没人用）',
       D.of(world) == NOTE, repr(D.of(world)))

    # ── C2 不传 ⇒ 空串（不残留上一次的）──
    # [EN] -- C2 Not passed => empty string (no leftover from last time) --
    _p2, _r2, _l2, world0, _db2 = _real_round(tmp, 'wire_empty')
    ok('C2 ★★★ 不传（没填）时是**空串** —— 上一轮那句不会残留到这一轮',
       D.of(world0) == '', repr(D.of(world0)))
    # 反向：先设一句，再装配一个没传的 ⇒ 必须还是空
    # [EN] Reverse: set a line first, then assemble with none passed => must still be empty
    D.attach(world, '上一轮那句')
    _p3, _r3, _l3, world3, _db3 = _real_round(tmp, 'wire_clear')
    ok('C2b ★★★ 先给一轮填过建议，**下一轮不填** ⇒ 下一轮的 world 上**没有**它',
       D.of(world3) == '' and D.of(world) == '上一轮那句', repr(D.of(world3)))

    # ── C3 界面接线（静态）──
    # [EN] -- C3 UI wiring (static) --
    g = read('gui/app_flet.py')
    dlg = between(g, 'def show_start_story_dialog', 'def _latest_run_folder')
    start = between(g, 'async def _start_round', 'def _show_opening_card')
    ok('C3 ★★★ 「开始推演」时把那一栏的值交给这一轮（`_pending_directive`）',
       'self._pending_directive = str(note_field.value or '
       "'').strip()" in dlg, '')
    ok('C4 ★★★ `_start_round` 把它交给装配 `assemble(user_directive=…)`',
       'user_directive=_directive' in start
       and "getattr(self, '_pending_directive', '')" in start, '')
    ok('C4b ★★★ 而且**取一次就清**（不清 = 下一轮没填也照样生效：'
       '"静默复活"，用户永远发现不了）',
       "self._pending_directive = ''" in start
       and start.find("self._pending_directive = ''")
       < start.find('user_directive=_directive'), '')
    ok('C5 ★★★ 那一栏**刻意不预填、不进 CFG**（它不是长期设置，是这一轮的内容）',
       "value=''," in between(dlg, 'note_field = ft.TextField(', 'multiline=True')
       and 'CFG.set' not in between(dlg, 'note_field = ft.TextField(',
                                    'body = ft.Column'),
       '')
    ok('C5b ★★ 界面上写明了"**只对这一轮有效**"（免得用户以为它会一直生效）',
       '只对这一轮有效' in dlg, '')


# ══════════════════════════════════════════════════════════════════════
#  D —— 开场卡片：填过的要看得见、查得到
# [EN] D -- Opening card: what was filled in must be visible and queryable
# ══════════════════════════════════════════════════════════════════════
def opening_checks(tmp: Path) -> None:
    print('\n── D 开场卡片（这一轮的记录）──')
    from sim import directive as D
    from sim import opening as OP

    _p, _r, _l, world, _db = _real_round(tmp, 'open', user_directive=NOTE)
    op = OP.collect(world, mode='story')
    ok('D1 ★★ 开场要用的料里带着它（`collect()[\'directive\']`）',
       str(op.get('directive') or '') == NOTE, repr(op.get('directive'))[:80])
    md = OP.render_md(op, title='夹具', detail='full', prose='（引子）')
    ok('D1b ★★ 开场卡片**落下来的那一份**里写着它'
       '（事后能查"那一轮我让他往哪走"）',
       t_head() in md and NOTE in md, md[:160].replace('\n', ' | '))
    ok('D1c ★ 用的是**引用块**（它不是这一轮演出来的剧情，别让人误读）',
       f'> {t_head()}' in md, '')

    D.attach(world, '')
    op0 = OP.collect(world, mode='story')
    md0 = OP.render_md(op0, title='夹具', detail='full', prose='（引子）')
    ok('D2 ★★★ **没填** ⇒ 开场卡片里连那一行都不出现（不留一个空壳标题）',
       not op0.get('directive') and t_head() not in md0, md0[:120].replace('\n', ' | '))


def t_head() -> str:
    """开场卡片上那一行的抬头（走 i18n，不写死中文）。
        English:
    The header of that line on the opening card (goes through i18n, no hard-coded Chinese).
    """
    from i18n import t
    from sim import directive as D
    return t(D.LINE_HEAD)


# ══════════════════════════════════════════════════════════════════════
#  E —— 界面结构（静态；真机在 `verify_author_note_ui.py`）
# [EN] E -- UI structure (static; the real machine is in `verify_author_note_ui.py`)
# ══════════════════════════════════════════════════════════════════════
def ui_structure_checks() -> None:
    print('\n── E 界面结构（静态）──')
    g = read('gui/app_flet.py')
    dlg = between(g, 'def show_start_story_dialog', 'def _latest_run_folder')
    ok('E1 ★★★ 对话框里有**前情提要**那一块',
       "mk_section(t('前情提要'))" in dlg and 'recap' in dlg, '')
    ok('E2 ★★★ 对话框里有**「您对接下来剧情发展的建议」**输入框（多行）',
       "mk_section(t('您对接下来剧情发展的建议'))" in dlg
       and 'note_field = ft.TextField(' in dlg
       and 'multiline=True, min_lines=3' in dlg, '')
    i_note = dlg.find("mk_section(t('您对接下来剧情发展的建议'))")
    i_recap = dlg.find("mk_section(t('前情提要'))")
    ok('E3 ★★★ 建议框在**前情提要的下面**（用户指名的那句"在前情提要的下面"）',
       -1 not in (i_recap, i_note) and i_recap < i_note,
       f'前情@{i_recap} 建议@{i_note}')
    ok('E3b ★★ 「从哪儿开始」那块还在（别为了加新块把它挤掉）',
       "mk_section(t('从哪儿开始'))" in dlg
       and dlg.find("mk_section(t('从哪儿开始'))") < i_recap, '')
    i = read('i18n.py')
    ok('E4 ★★ 中英都有（英文界面下不许露中文）',
       "'您对接下来剧情发展的建议':" in i
       and "'作者对本轮走向的要求':" in i
       and "'{head}：{text}':" in i, '')


def single_push_checks() -> None:
    """F —— **那一行只在开头推一次**（静态、确定性）。

    ★ 为什么要用静态判据守这件事：`RunLoop._push_author_note()` 的另一半
      "每个日界也推"要靠**真的跨过一天**才看得出来 —— 而跨天要等着时钟走，
      判据里等不出来（真机上跑十几秒通常还没跨天），那条断言会变成
      "跑得快就绿、跑得慢才红"的**假判据**。
      所以这里守**结构**：调用点只有一个、而且紧跟在开头那句前情提要之后。
      （真机那支也顺带数了一次"只出现一条"，两边一起看。）
    
        English:
    F -- **That line is only pushed once at the start** (static, deterministic).
        ★ Why use a static criterion to guard this: the other half of `RunLoop._push_author_note()`
          "push on every day boundary" can only be observed by **actually crossing a day** — and crossing a day requires waiting for the clock to advance,
          which cannot be waited out in the criterion (on a real machine, running for a dozen seconds usually still hasn't crossed a day), so that assertion becomes
          a **fake criterion** of "green if it runs fast, red only if it runs slow".
          So here we guard the **structure**: there is only one call site, and it immediately follows the recap sentence at the beginning.
          (The real-machine branch also incidentally counted "only one appears", so both sides are checked together.)
    """
    src = read('sim/loop.py')
    calls = src.count('self._push_author_note()')
    ok('F1 ★★★ 那一行只有**一个**调用点（一轮念一次；每个日界都念就成噪音了）',
       calls == 1, f'找到 {calls} 个调用点')
    i_recap = src.find('        self._push_recap()')
    i_note = src.find('        self._push_author_note()')
    ok('F2 ★★ 而且它**紧跟在开头那句前情提要之后**'
       '（顺序："演到哪儿了"在前、"往哪走"在后）',
       -1 not in (i_recap, i_note) and 0 < i_note - i_recap < 1800,
       f'recap@{i_recap} note@{i_note}')
    # ⚠ 这里**刻意不写**"它没挂在 `SHOW_OPENING` 上"那条静态断言 ——
    #   那条已有**行为级**的证明：真机判据 E4 跑在本机 `.env`
    #   （`SHOW_OPENING=false`，探针实测）下照样绿。静态再写一遍只是重复，
    #   而且很容易写成 `or True` 那种**装饰品**（第一版就写成了那样，删掉）。
    # [EN] WARNING: here we **deliberately do not write** the static assertion "it's not hooked onto
    # [EN] `SHOW_OPENING`" --
    # [EN] That one already has a **behavioral** proof: the real-machine criterion E4 runs against the
    # [EN] local `.env`
    # [EN] (`SHOW_OPENING=false`, probe-verified) and still passes. Writing it again statically is just
    # [EN] repetition,
    # [EN] and it's very easy to write it as an `or True` **decoration** (the first version was written
    # [EN] that way; deleted).


def _finish() -> int:
    out = APP / 'assets' / 'screenshots' / 'author_note_report.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2),
                   encoding='utf-8')
    bad = [c for c in REPORT['checks'] if not c['ok']]
    n = len(REPORT['checks'])
    print(f'\n作者走向建议 · 验证：{n - len(bad)}/{n}')
    for c in bad:
        print(f'  ✗ {c["name"]}\n        {c["detail"][:200]}')
    return 0 if not bad else 2


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='nws_note_'))
    # ★★ **用量台账指到临时库**（2026-10-11）：B 组真的调了一次 `agent.decide`
    #   （MOCK 也会记账），而 `llm/usage.db_path()` 指向**软件根目录**那份 ——
    #   不打桩就会往用户真实的用量报表里塞几笔"夹具项目"的账。
    # [EN] **Usage ledger points to a temp DB** (2026-10-11): group B really called `agent.decide` once
    # [EN] (MOCK also records usage), and `llm/usage.db_path()` points to the one in the **software root
    # [EN] directory** --
    # [EN] without stubbing, it would stuff a few "fixture project" entries into the user's real usage
    # [EN] report.
    from llm import usage as _U
    _U.db_path = lambda: tmp / 'usage.db'
    groups = [('前情提要两边一样', lambda: recap_same_checks(tmp)),
              ('建议进提示词', lambda: note_in_prompt_checks(tmp)),
              ('接线', lambda: wiring_checks(tmp)),
              ('开场卡片', lambda: opening_checks(tmp)),
              ('只推一次', single_push_checks),
              ('界面结构', ui_structure_checks)]
    for name, fn in groups:
        try:
            fn()
        except Exception:                                        # noqa: BLE001
            # ★ 崩了必须自己留一条红 —— 否则"全绿"和"崩了"在汇总里长得一样。
            # [EN] WARNING: a crash must leave its own red -- otherwise "all green" and "crashed" look the same in
            # [EN] the summary.
            REPORT['checks'].append({'name': f'{name} 组崩了（自己留一条红）',
                                     'ok': False,
                                     'detail': traceback.format_exc()[-900:]})
    return _finish()


if __name__ == '__main__':
    sys.exit(main())
