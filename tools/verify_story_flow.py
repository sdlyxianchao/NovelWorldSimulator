# -*- coding: utf-8 -*-
"""验证：**中栏的故事体**（`display/story_render.py`，运行窗口的阅读感）。

起因（用户 2026-10-06）：「运行窗口的对话窗口有点过于倾向于剧本了，
优化一下让他更像一点故事」。

"剧本感"原来来自三处，这个脚本一条条钉：

  ① **场记标记**：`〔心声·阿枝〕`、`〔环境〕`、`〔出场〕`、`· 动作`
  ② **场记式台词**：`主角（压低声音）对阿枝：今夜别出门。`
  ③ **一行一条**：一句一控件，屏幕上碎成几十行

要证的四件事（每条都要能红）：

  ① **句子说的是小说话**：台词给了叙述动词、动作写成人名+动作、
     心声/回想是人话（`阿枝心想：…` / `主角想起，…`）；
  ② **屏幕上不再出现场记标记**（`※` 与 `〔切至〕` 这类**结构**标记除外 ——
     它们本来就不是故事）；
  ③ **分段**：叙述并成段落、台词独立成段、段不过长；
  ④ **实时追加与整屏重建得到同样的分段**（两处走同一个纯函数）——
     不然"跑着看的"和"重进界面看的"会长得不一样。

用法：.venv\\Scripts\\python.exe tools/verify_story_flow.py [--logic-only]
产出：assets/screenshots/story_flow_report.json

English:
Verify: **the story body of the middle column** (`display/story_render.py`, the reading feel of
the running window).
Cause (user 2026-10-06): "the dialogue window of the running window leans a bit too much toward
script,
optimize it to be a bit more like a story".
"Script feel" originally came from three places; this script pins them one by one:
  ③ **One item per line**: one widget per sentence, shattered into dozens of lines on screen
Four things to prove (each one must be able to fail):
  ① **Sentences speak novel language**: dialogue carries narrative verbs, actions are written as name+action,
  ② **Stage-direction markers no longer appear on screen** (except **structural** markers like `※` and `〔切至〕` ——
     they were never story to begin with);
  ③ **Segmentation**: narration merges into paragraphs, dialogue stands as its own paragraph, paragraphs are not too long;
  ④ **Live append and full-screen rebuild yield the same segmentation** (both go through the same pure function) ——
     otherwise "watching it run" and "reopening the interface to watch" would look different.
Usage: .venv\\Scripts\\python.exe tools/verify_story_flow.py [--logic-only]
Output: assets/screenshots/story_flow_report.json
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
CFG.set('BEAT_SECONDS', '2')
CFG.set('SHOW_OPENING', 'false')       # 本脚本验中栏正文，不需要开场卡干扰
# [EN] This script verifies the middle-column body text; no opening card interference is needed

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

from display import script as S                                # noqa: E402
from display import story_render as STR                        # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
report: dict = {'checks': []}


def ok(name: str, cond: bool, detail='') -> None:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''))


def _sample() -> list:
    """一段有代表性的**原始词条**（模拟一拍里会出些什么）。

    刻意把"最容易写歪"的都放进来：带语气带对象的台词、单独一声"为什么"、
    动作、心声、回想、环境、旁白、停顿、出场、已在场、事件、机制标注。
    
        English:
    A representative **raw entry** (simulating what might appear in one beat).
        Deliberately include everything "most prone to being written wrong": lines with tone and an addressee, a standalone "why",
        actions, inner thoughts, recollections, environment, narration, pauses, entrances, already-present, events, mechanic annotations.
    """
    sc = S.SceneScript(time_label='戌时', place='临河茶肆')
    for e in (
        S.narration('灶上温着水，白灯笼还没点。'),
        S.ambient('雨脚敲着檐瓦。'),
        S.enter('主角', '入画'),
        S.enter('阿九', '已在场'),
        S.dialogue('主角', '今夜别出门。', to='阿枝', tone='压低声音'),
        S.dialogue('阿枝', '为什么？'),
        S.action('主角', '把壶放下'),
        S.aside('阿枝', '他今天不对劲。'),
        S.recall('主角', '那年也是这样的雨。'),
        S.beat('片刻无话'),
        S.action('阿福', '去了后院'),
        S.event('【外部刺激】后巷传来一声闷响。'),
        S.note('节点完成：门口醒来'),
    ):
        sc.add(e)
    return [(e.priority, STR.sentence(e), e.kind) for e in sc.entries]


def _entries() -> list:
    sc = S.SceneScript(time_label='戌时', place='临河茶肆')
    for e in (S.narration('灶上温着水。'), S.dialogue('主角', '走。'),
              S.action('主角', '把壶放下'), S.aside('阿枝', '不对劲。')):
        sc.add(e)
    return list(sc.entries)


# ══════════════════════════════════════════════════════════════
#  A. 纯逻辑：句子化 + 分段
# [EN] A. Pure logic: sentence-ization + segmentation
# ══════════════════════════════════════════════════════════════
def logic_checks() -> None:
    es = _entries()
    say = STR.sentence(es[1])
    act = STR.sentence(es[2])
    aside = STR.sentence(es[3])

    # ── A1 台词（★★ 2026-10-07 口径翻转：改剧本体）──
    # [EN] ── A1 dialogue (★★ 2026-10-07 spec reversal: change the script body) ──
    #
    # ★★ 这一组原来是**反着钉的**：那时把 `人名：` 当"场记写法"，要求避免；
    #   台词要写成小说体 `主角压低声音，对阿枝说：「…」`。
    #   用户 2026-10-07 明确改了口径：「正文的格式你参考 老舍的茶馆 进行深度优化」
    #   —— 《茶馆》是话剧剧本，台词的样子就是「**人物名：**台词」，
    #   舞台提示写在小括号里（`王利发：（向李三）…`），**不用"他说"**。
    #   所以这里整体翻过来：**要 `人名：`，不要叙述动词**。
    # [EN] ★★ This group was originally **pinned the opposite way**: back then `name:` was treated as a
    # [EN] "stage-direction style" and required to be avoided;
    # [EN] On 2026-10-07 the user explicitly reversed the spec: "For the format of the body text, refer to [EN] 老舍的茶馆 and optimize deeply"
    # [EN] —— 《茶馆》 is a stage play script; the way dialogue looks is "**character name:**lines",
    # [EN] So here it is flipped entirely: **use `name:`, do not use narrative verbs**.
    sc = S.SceneScript(time_label='戌时', place='楼')
    sc.add(S.dialogue('主角', '今夜别出门。', to='阿枝', tone='压低声音'))
    sc.add(S.dialogue('阿枝', '为什么？'))
    sc.add(S.dialogue('主角', '「已经带引号了」'))
    d1, d2, d3 = (STR.sentence(e) for e in sc.entries)
    ok('A1 ★ 台词是**剧本体**：`人名：` 直接引出'
       '（老舍《茶馆》的写法；不再用"X说：「…」"那套叙述动词）',
       d1.startswith('主角：') and '说：' not in d1 and '今夜别出门' in d1, d1)
    ok('A1b 有语气与对象时写成括注：`人名：（语气，向谁）台词`',
       d1 == '主角：（压低声音，向阿枝）今夜别出门。', d1)
    ok('A1c 没有语气也没有对象时，退化成最简单的 `人名：台词`',
       d2 == '阿枝：为什么？', d2)
    ok('A1d 台词自带引号会被剥掉（剧本体靠 `谁：` 分，不用引号）',
       d3 == '主角：已经带引号了', d3)

    # ── A2 动作 / 心声 / 回想 ──
    # [EN] ── A2 action / inner thoughts / recollection ──
    ok('A2 动作写成**舞台提示**：整条包在括号里'
       '（剧本里"人在做什么"就是这么标的，一眼能跟台词分开）',
       act.startswith('（') and act.endswith('）') and '主角' in act, act)
    ok('A2b 心声是人话：`X心想：…`', aside == '阿枝心想：不对劲。', aside)
    sc2 = S.SceneScript(time_label='戌时', place='楼')
    sc2.add(S.recall('主角', '那年也是这样的雨。'))
    ok('A2c 回想是人话：`X想起，…`',
       STR.sentence(sc2.entries[0]) == '主角想起，那年也是这样的雨。',
       STR.sentence(sc2.entries[0]))

    # ── A3 出场退场 ──
    # [EN] ── A3 entrance and exit ──
    ok('A3 ★ 出场写成叙述（`主角走了进来。`），不再打 `〔出场〕` 标记',
       STR.sentence(S.enter('主角', '入画')) == '主角走了进来。',
       STR.sentence(S.enter('主角', '入画')))
    ok('A3b `已在场` 的人**不出句子**（他本来就在，说了是废话）',
       STR.sentence(S.enter('阿九', '已在场')) == '',
       repr(STR.sentence(S.enter('阿九', '已在场'))))
    ok('A3c 退场同理', STR.sentence(S.exit_('阿九', '退场')) == '阿九走了出去。',
       STR.sentence(S.exit_('阿九', '退场')))

    # ── A4 事件 / 停顿 ──
    # [EN] ── A4 events / pauses ──
    ev = STR.sentence(S.event('【外部刺激】后巷传来一声闷响。'))
    ok('A4 ★ 导演事件写进故事，且**剥掉事件类型**（那是给作者看的分类）',
       ev == '就在这时，后巷传来一声闷响。' and '外部刺激' not in ev, ev)
    ok('A4b 停顿写成句子（`片刻无话。`），不再是 `〔片刻无话〕`',
       STR.sentence(S.beat('片刻无话')) == '片刻无话。',
       STR.sentence(S.beat('片刻无话')))

    # ── A5 机制标注与结构标记**保持原样** ──
    # [EN] ── A5 mechanism annotations and structural markers **kept as-is** ──
    note = STR.sentence(S.note('节点完成：门口醒来'))
    ok('A5 ★ 机制标注（※）**不进故事正文**，而且留着 `※` 那个信号'
       '（去掉它，「进度：节点完成」跟正文长得一模一样）',
       note.startswith('※') and '节点完成' in note, note)
    cut = STR.sentence(S.cut('后巷', '同一时刻'))   # 签名是 (place, note)
    # [EN] The signature is (place, note)
    ok('A5b ★ 结构标记（〔切至〕）保持原样，**而且要带着地点**'
       '（只取 entry.text 会把"切到哪儿去了"丢掉）',
       '〔' in cut and '切至' in cut and '后巷' in cut, cut)

    # ── A6 屏幕上不再有场记标记 ──
    # [EN] ── A6 no more stage-direction markers on screen ──
    rows = _sample()
    # ⚠ 只查**故事类**的词条：机制标注（`※`）与结构标记（`〔切至〕`）
    #   是**刻意保留**的（A5/A5b），把它们算进"该消失的标记"就自相矛盾了
    #   —— 第一版就是这么红的。
    # [EN] ⚠ Only check **story-type** entries: mechanism annotations (`※`) and structural markers (`〔切至〕`)
    # [EN] are **intentionally retained** (A5/A5b); counting them as "markers that should disappear" would
    # [EN] be self-contradictory
    # [EN] —— this is exactly why the first version failed.
    story_rows = [r for r in rows if r[2] not in (S.NOTE, S.CUT, S.CUT_BACK)]
    blob = ' '.join(r[1] for r in story_rows)
    banned = ['〔心声', '〔环境', '〔回想', '〔出场', '〔退场', '· 动作', '〔事件']
    hit = [b for b in banned if b in blob]
    ok('A6 ★★ 故事正文里**一个场记标记都没有**（"更像故事"的硬指标）',
       not hit, f'残留: {hit}' if hit else f'{len(story_rows)} 条故事词条')

    # ── A7 分段 ──
    # [EN] ── A7 segmentation ──
    grps = STR.group(rows)
    kinds_of = [{(rows[i][2]) for i in g} for g in grps]
    ok('A7 ★ 连续叙述**并成一段**（不再一句一控件）',
       any(len(g) >= 3 for g in grps),
       [len(g) for g in grps])
    ok('A7b 台词**独立成段**（中文小说的排版规矩）',
       all(len(g) == 1 for g in grps if S.DIALOGUE in kinds_of[grps.index(g)]),
       [sorted(k) for k in kinds_of])
    ok('A7c 导演事件独立成段（转折点要有顿挫，不并进叙述里）',
       all(len(g) == 1 for g in grps if S.EVENT in kinds_of[grps.index(g)]),
       '')
    ok('A7d 段不过长（`PARA_MAX_SENTENCES`，一路并下去会变成一整屏一大坨）',
       all(len(g) <= STR.PARA_MAX_SENTENCES for g in grps),
       f'上限 {STR.PARA_MAX_SENTENCES}，实际 {[len(g) for g in grps]}')

    # ── A8 缩进 ──
    # [EN] ── A8 indentation ──
    def first_of(kind_: str) -> str:
        for g in grps:
            if rows[g[0]][2] == kind_:
                return STR.join_text(rows, g)
        return ''
    ok('A8 叙述段缩两格（中文排版首行缩进）',
       first_of(S.NARRATION).startswith(STR.PARA_INDENT), repr(first_of(S.NARRATION)[:14]))
    ok('A8b 台词**不缩**（对话顶格是小说排版）',
       not first_of(S.DIALOGUE).startswith(STR.PARA_INDENT),
       repr(first_of(S.DIALOGUE)[:14]))
    ok('A8c 机制标注**不缩**（它不是故事，缩进会让人以为也是正文）',
       not first_of(S.NOTE).startswith(STR.PARA_INDENT), repr(first_of(S.NOTE)[:14]))

    # ── A9 纯函数 ──
    # [EN] ── A9 pure functions ──
    ok('A9 ★★ `group()` 是**纯函数**（同样的输入两次结果一样 —— 实时追加重建靠它）',
       STR.group(rows) == STR.group(list(rows)), '')

    # ── A10 样式表与并段表严格对应 ──
    # [EN] ── A10 style sheet and paragraph-merge sheet must correspond strictly ──
    ok('A10 段内样式表的键**恰好**等于能并段的类型（少配就是默默用默认色）',
       set(STR.SPAN_STYLE) == set(STR.JOINABLE),
       f'差集 {set(STR.SPAN_STYLE) ^ set(STR.JOINABLE)}')

    # ── A11 英文界面的连接符 ──
    # [EN] ── A11 connectors in the English UI ──
    set_lang('en')
    ok('A11 英文界面句子间要有空格（否则 `He...She...` 会粘在一起）',
       STR.sent_sep() == ' ', repr(STR.sent_sep()))
    ok('A11b ★ 台词抬头在英文界面下同样是剧本体（人名不翻译，`人名：` 直接接）',
       STR.sentence(S.dialogue('主角', 'Go.')) == '主角：Go.',
       STR.sentence(S.dialogue('主角', 'Go.')))
    set_lang('zh')

    # ── A12 前情提要（用户 2026-10-07：「每次推演开始一开始应该有一小段
    #        前情提要 你这个也没有」）──
    # [EN] ── A12 recap (user 2026-10-07: "at the start of every simulation run there should be a short
    # [EN] recap  and you don't have this either") ──
    from display import script_render as SR
    from gui.app_flet import _LIVE_STYLE, NovelWorldApp
    rc = STR.sentence(S.recap('镇上来了生面孔，四处打听三年前那桩事。'))
    ok('A12 ★ 前情提要有自己的样子（`§ 前情提要：…`）'
       '—— 不是 `※` 那套机制标注（那是体检报告，不是故事）',
       rc.startswith('§') and '前情提要' in rc and not rc.startswith('※'), rc)
    ok('A12b 前情提要**不缩进**（缩两格会被当成正文的第一句）',
       not STR.should_indent({S.RECAP}), '')
    ok('A12c 前情提要**不并进段落**（它是一整块，不属于正文的段落流）',
       not STR.is_joinable(S.RECAP), '')
    ok('A12d 界面上它有**自己的一档样式**（底色 + 边框方块，与台词/标注分开）',
       S.RECAP in _LIVE_STYLE and 'recap' in NovelWorldApp.NARR_BLOCK_STYLE, '')
    ok('A12e 剧本渲染器认这个新类型（不会因为多一个类型就 KeyError）',
       SR.KIND_LABEL.get(S.RECAP) == '前情提要'
       and bool(SR.one_line(S.recap('x'))), SR.one_line(S.recap('x')))

    # ── A13 「同一句话不被讲两遍」（用户 2026-10-07：「这个故事线里把人物
    #        说的话讲一遍 然后人物自己再说一遍 很诡异 这个毛病要修掉」）──
    # [EN] ── A13 "the same sentence must not be told twice" (user 2026-10-07: "in this storyline, saying
    # [EN] what the character
    # [EN] says once, then the character says it again themselves is very bizarre; this defect must be
    # [EN] fixed") ──
    from sim.loop import _verb_desc
    from agent.core import Action
    said = _verb_desc(Action(verb='speak', target='阿枝', dialogue='今夜别出门。'))
    ok('A13 ★ 动作描述里**不再复述台词**'
       '（以前拼的是"对阿枝说：今夜别出门。"，于是同一句话被旁白讲一遍、'
       '角色自己再说一遍）',
       '今夜别出门' not in said, said)

    class _PS:
        def __init__(self, n):
            self.name, self.status, self.location = n, '在场', ''

    class _W:
        scene, weather, game_day = '临河茶肆', '雨', 1
        people = {'主角': _PS('主角')}

        def on_stage_names(self):
            return ['主角']

    from display.scene_builder import SceneBuilder
    b = SceneBuilder(_W(), day=1)
    e1 = b.observe_speech('主角', '今夜别出门。')
    e2 = b.observe_speech('主角', '今夜别出门。')
    ok('A13b ★ 群聊台词与前台步进**同一个出口**：台词就是 `DIALOGUE` 词条'
       '（以前它拼成 `X说：「…」` 那种旁白复述，而且只在中栏有、落盘里没有）',
       e1 is not None and e1.kind == S.DIALOGUE, '')
    ok('A13c ★★ 同一句话不会被讲第二遍（第二次返回 None，调用方据此不推）',
       e2 is None and '说：「' not in (STR.sentence(e1) or ''), STR.sentence(e1))


# ══════════════════════════════════════════════════════════════
#  B. 真机：中栏真的是一段一段的
# [EN] B. Real machine: the middle column really is paragraph by paragraph
# ══════════════════════════════════════════════════════════════
def _para_texts(col) -> list[str]:
    """中栏里所有**段落控件**的纯文本（`ft.Text` + spans）。

    ⚠ 必须用 `VU.walk` **穿透**外层的方块容器（2026-10-07）：中栏现在会给
      台词/事件套一层 `ft.Container`（左侧色条 + 边框 —— 用户要的"很明显"的
      区分），段落控件**不再是 `col.controls` 的直接子项**。
      按顶层找会漏掉它们 —— 实测：期望 5 段只找到 3 个，带方块的台词段整个不见了。
    
        English:
    The plain text of all **paragraph controls** in the middle column (`ft.Text` + spans).
        ⚠ Must use `VU.walk` to **penetrate** the outer block container (2026-10-07): the middle column now wraps
          lines/events in an `ft.Container` (left color bar + border -- the "very obvious" distinction the user wanted),
          and paragraph controls are **no longer direct children of `col.controls`**.
          Searching at the top level will miss them -- measured: expected 5 paragraphs but found only 3, the entire line paragraph with the block was missing.
    """
    out = []
    for c in VU.walk(col):
        if isinstance(c, ft.Text) and getattr(c, 'spans', None):
            out.append(''.join(str(getattr(s, 'text', '') or '') for s in c.spans))
    return out


def _find_btn(root, label: str):
    """在控件树里找按钮（文本精确相等）。
        English:
    Find a button in the control tree (exact text equality).
    """
    for c in (VU.walk(root) if root is not None else []):
        if (hasattr(c, 'on_click') and getattr(c, 'on_click', None)
                and VU.text_of(c) == label):
            return c
    return None


async def gui_checks(page: ft.Page, app, tmp: Path) -> None:
    from verify_run_control import make_project
    proj = make_project(tmp / '小说体')
    app.current_project = proj
    app.show_main_screen()
    await asyncio.sleep(1.0)

    # ⚠ **必须先真开跑**：中栏只有在"正在跑"（`session.is_alive`）时才渲染
    #   实时流；停跑后它会回落到**落盘剧本**那条分支，`_live_lines` 根本不参与
    #   渲染 —— 那时候量到的是 0 段（第一版就是这么红的，和上一轮开场卡片同一个坑）。
    # [EN] ⚠ **Must actually run it first**: the middle column renders only when "running"
    # [EN] (`session.is_alive`)
    # [EN] as a live stream; after stopping, it falls back to the **persisted script** branch, and
    # [EN] `_live_lines` does not participate at all
    # [EN] in rendering —— at that point what you measure is 0 paragraphs (this is exactly why the first
    # [EN] version failed, same pitfall as the opening card last round).
    dlg = app.show_start_story_dialog()
    page.update()
    await asyncio.sleep(0.6)
    btn = _find_btn(dlg, t('开始推演'))
    ok('B0 找得到「开始推演」', btn is not None, '')
    if btn is not None:
        btn.on_click(None)
    for _ in range(200):
        await asyncio.sleep(0.1)
        if app.session is not None and app.session.is_alive:
            break
    await asyncio.sleep(1.5)
    ok('B0b 会话真的起来了（下面的取证要在"正在跑"状态下做）',
       app.session is not None and app.session.is_alive,
       getattr(app.session, 'status', None))

    # ── B4 「每次推演开始」先给一小段前情提要 ──
    #   用户 2026-10-07：「而且说了 每次推演开始一开始应该有一小段前情提要
    #   你这个也没有」—— 以前这段字**只写进落盘文件**，屏幕上一条都没有。
    #   ⚠ 必须放在下面 `_live_lines.clear()` **之前**：紧接着几行会把实时流换成
    #     一组受控样本（那是 B1 的事），量不到这一轮真实的开头。
    # [EN] ── B4 "every simulation run" first gives a short recap ──
    # [EN] User 2026-10-07: "and I said at the start of every simulation run there should be a short recap
    # [EN] and you don't have this either" —— previously this text was **only written to the persisted
    # [EN] file**, not a single line on screen.
    # [EN] ⚠ Must be placed **before** the `_live_lines.clear()` below: the next few lines will replace the
    # [EN] live stream with
    # [EN] a set of controlled samples (that's B1's business), and the real beginning of this run cannot be
    # [EN] measured.
    kinds_all = [it[2] for it in app._live_lines]
    recap_rows = [it for it in app._live_lines if it[2] == S.RECAP]
    ok('B4 ★ 开跑后屏幕上真的先出现「前情提要」（不是只写进文件）',
       bool(recap_rows), f'词条类型：{kinds_all[:7]}')
    ok('B4b 它排在**正文之前**（前情 → 场景 → 人物开口，是用户要的顺序）',
       bool(recap_rows) and kinds_all.index(S.RECAP) < max(1, len(kinds_all) - 1),
       f'位置 {kinds_all.index(S.RECAP) if recap_rows else -1} / 共 {len(kinds_all)} 条')
    ok('B4c 屏幕上那段字是"给人读的一句"，不是空壳',
       bool(recap_rows) and len(str(recap_rows[0][1])) > 8,
       (str(recap_rows[0][1])[:60] if recap_rows else '（没有）'))

    # 暂停推演，再把流换成一组**受控样本**：验的是渲染规则，
    # 不该被"这一拍恰好出了什么"左右（真实叙事继续进来也无所谓 ——
    # 检查只取我喂进去的那一段）。
    # [EN] Pause the simulation, then replace the stream with a set of **controlled samples**: what is
    # [EN] verified is the rendering rule,
    # [EN] which should not be swayed by "what exactly happened at this beat" (it doesn't matter if real
    # [EN] narrative keeps coming in ——
    # [EN] the check only takes the segment I fed in).
    try:
        app.session.pause()
    except Exception:                                          # noqa: BLE001
        pass
    await asyncio.sleep(0.8)
    col = app._ui_run.get('narrative')
    col.controls.clear()
    app._live_lines.clear()
    base = len(app._live_lines)

    rows = _sample()
    for pr, tx, kd in rows:
        app._on_narrative(tx, pr, kd)
        await asyncio.sleep(0.02)
    mine = app._live_lines[base:]
    n_sent = len([r for r in mine if r[1]])
    paras = _para_texts(col)
    report['sentences'] = n_sent
    report['paragraph_controls'] = len(paras)
    report['paragraph_texts'] = paras[:8]

    ctl_paras = [c for c in VU.walk(col)
                 if isinstance(c, ft.Text) and getattr(c, 'spans', None)]
    # ⚠ 判据要**精确**：段落控件数必须等于 `group()` 算出来的段数（不多不少）。
    #   第一版写的是 `len(paras) < n_sent`（拿总句数当分母）—— 那样"重复渲染"
    #   这种退化抓不到（13 句渲染成 7 个控件，仍然 < 13，判据照样绿）。
    #   只有"叙述 + 台词"才渲染成段落（事件走卡片、机制标注走单行），
    #   所以期望值只数**那两种**的段数。
    # [EN] ⚠ The criterion must be **precise**: the number of paragraph widgets must equal the paragraph
    # [EN] count computed by `group()` (no more, no less).
    # [EN] The first version wrote `len(paras) < n_sent` (using the total sentence count as denominator) ——
    # [EN] that way "duplicate rendering"
    # [EN] degeneration cannot be caught (13 sentences rendered as 7 widgets, still < 13, the criterion
    # [EN] still passes).
    # [EN] Only "narration + dialogue" renders as paragraphs (events go to cards, mechanism annotations go
    # [EN] to single lines),
    # [EN] so the expected value only counts the paragraph count of **those two** kinds.
    want_kinds = set(STR.JOINABLE) | {S.DIALOGUE}
    expect = len([g for g in STR.group(mine) if mine[g[0]][2] in want_kinds])
    ok('B1 ★★ 中栏的段落控件数 **＝** `group()` 算出的段数（不多不少）',
       len(ctl_paras) == expect and expect > 0,
       f'{n_sent} 句 → 期望 {expect} 段，实际 {len(ctl_paras)} 个控件')
    multi = [c for c in ctl_paras if len(c.spans) >= 2]
    ok('B1b ★★ 至少一段里装了**多句**（真的并起来了；退回一行一条时这恒为 1）',
       len(multi) >= 1, f'各段 span 数 {[len(c.spans) for c in ctl_paras]}')
    ok('B2 ★★ 屏幕上**没有场记标记**（`〔心声〕`/`〔出场〕`/`· 动作`）',
       not any(mark in p for p in paras
               for mark in ('〔心声', '〔环境', '〔出场', '· 动作')),
       [p[:26] for p in paras[:3]])
    ok('B2b 台词那段是**剧本体**（`主角：…` 顶格，不再用引号包起来）',
       any('：' in p[:14] and not p.startswith(STR.PARA_INDENT) for p in paras),
       [p[:30] for p in paras if '：' in p][:2])
    ok('B2c 叙述段缩两格（段首是两个全角空格）',
       any(p.startswith(STR.PARA_INDENT) for p in paras),
       [repr(p[:8]) for p in paras[:3]])

    # ── B3 实时追加 与 整屏重建 的分段必须一样 ──
    # [EN] ── B3 live append and full-screen rebuild must have identical segmentation ──
    live_paras = list(paras)
    app.show_main_screen()              # 重建界面（走 `_render_live` 全量渲染）
    # [EN] Rebuild the interface (goes through `_render_live` full rendering)
    await asyncio.sleep(0.6)
    col2 = app._ui_run.get('narrative')
    rebuilt = _para_texts(col2)
    report['rebuilt_texts'] = rebuilt[:8]
    ok('B3 ★★ 重进界面后**段落切分完全一样**（实时增量与整屏重建同源）',
       rebuilt[:len(live_paras)] == live_paras,
       f'实时 {len(live_paras)} 段 / 重建 {len(rebuilt)} 段')

    png = await page.take_screenshot()
    (OUT / 'story_flow_chat.png').write_bytes(png or b'')


async def entry(page: ft.Page) -> None:
    from gui.app_flet import NovelWorldApp
    env_path = APP_DIR / '.env'
    env_backup = env_path.read_text(encoding='utf-8') if env_path.exists() else None
    tmp = Path(tempfile.mkdtemp(prefix='nws_flowroot_'))
    VU.isolate_projects_dir(tmp / 'Projects')
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
        VU.safe_rmtree(tmp, ignore_errors=True)
    await shutdown(page, code=finish())


def finish() -> int:
    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    (OUT / 'story_flow_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"\n故事体验证：{len(report['checks']) - len(bad)}/{len(report['checks'])}")
    for c in bad:
        print('  ✗', c['name'], '|', c['detail'])
    if report.get('fatal'):
        print(report['fatal'][-1500:])
    print('报告：assets/screenshots/story_flow_report.json')
    return 0 if report['ok'] else 2


def main() -> int:
    if '--logic-only' in sys.argv:
        try:
            logic_checks()
        except BaseException:                                  # noqa: BLE001
            report['fatal'] = traceback.format_exc()
        return finish()
    try:
        logic_checks()
    except BaseException:                                      # noqa: BLE001
        report['fatal'] = traceback.format_exc()
    if not report.get('fatal'):
        ft.run(entry)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
