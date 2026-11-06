# -*- coding: utf-8 -*-
"""验证：**排练** + **中栏白名单** + **剧组状态小消息** + **当天这一章**（2026-10-07）。

用户原话（拆成四件事）
----------------------
1. 「排练你是说剧本出来所有人先快速走一遍但是不出现结果在窗口里吗？
   如果是的话可以加排练这个阶段。」
2. 「窗口输出的内容你把作者写小说 剧作家创作剧本 剧组排练 然后重新修改
   再排练 再修改等过程用**小的消息**(只显示阶段名和用时，不真实输出内部细节，
   但细节写入日志) 开演 中间临时暂停 剧组重新修改细节 一天结束后讨论 总结会
   等都显示出来 但是只显示状态和已经操作的时间 不显示细节」
3. 「除了我已经说的人物场景介绍 前情提要 今日故事简介 旁白 人物动作
   人物台词对话 场景切换 外部环境变化 关键变量 冲突提示 导演工作分配
   手动停止以及一天自动停止之后的总结 …… **别的不要加到运行界面中间窗口**
   (一开始提的几个工作人员工作状态卡片也要加)」
4. 「每天总结你看下包含当天故事整理吗(整理成小说形式) 手动导出也要看下是否
   包含导出小说形式内容 没有这两个地方都加上」

判据分五层：

  A **白名单**：`S.on_window()` 的语义（用户点名的那几类通过、其余挡掉），
    以及界面上真的走它。
  B **阶段小消息**：形态（只报名字与用时 / 未知 key 原样 / 失败也报）；
    跑一天，阶段序列里得出现用户点的那些个。
  C **工作状态**：只写状态不写产出；**没出活**照旧带原因上屏。
  D **排练**：真的排了 · 产出落 `排练记录.md` · **不进中栏** ·
    排出问题 → 带意见重写（阶段序列里出现 `rewrite` → `rehearsal`）。
  E **当天这一章**：`当天故事.md` 按天累积 · `今日总结.md` 带「整理稿」·
    关掉开关就不写。
  G **该出现时真的出现**：用户点名的五条阶段消息（开演 / 剧组重新修改细节 /
    一天结束后讨论 / 总结会 / 整理当天这一章）· 「一天自动停止」与
    「**手动停止**」两条路上的今日总结 · 中途临时暂停与继续。
    ⚠ 这一组与 B 组**不是一回事**：B 查标签表，G 查"事件发生时屏幕上多了一条"。

另有一条**真机**判据（`--gui`，默认跑）：真的开一个窗口跑 MOCK 一天，
读中栏控件的文字 —— 剧组产出的**正文**不许出现，阶段/状态/今日总结**必须**在。

用法：.venv\\Scripts\\python.exe tools/verify_crew_stage.py [--logic-only]
产出：assets/screenshots/crew_stage_report.json

English:
Verification: **rehearsal** + **middle-column whitelist** + **crew status small messages** +
**today's chapter** (2026-10-07).
User's exact words (split into four things)
----------------------
1. "Rehearsal, do you mean that after the script comes out everyone quickly walks through it once but the results do not appear in the window?
   If so, you can add a rehearsal stage."
2. "For the window output, take the author writing the novel, the playwright creating the script, the crew rehearsing, then revising
   and rehearsing again, then revising again, etc., and use **small messages** (showing only the stage name and elapsed time, not actually outputting internal details,
   but writing the details to the log) for start of show, mid-way temporary pause, crew revising details, discussion after the day ends, summary meeting,
   etc., display them all, but only show the status and the elapsed time already operated, not the details"
3. "Besides the character and scene introductions, previous-story recap, today's story synopsis, narration, character actions,
   character dialogue, scene switches, external environment changes, key variables, conflict prompts, director work assignments,
   manual stop and the summary after the day's automatic stop that I have already mentioned ... **do not add anything else to the middle window of the running UI**
   (the several staff work-status cards mentioned at the beginning also need to be added)"
4. "For the daily summary, check whether it includes today's story organization (organized into
novel form). For manual export, also check whether
   it includes export novel-form content. If neither of these two places has it, add it."
The criteria are in five layers:
  A **whitelist**: the semantics of `S.on_window()` (the categories the user named pass, the rest are blocked),
    and the UI actually goes through it.
  B **stage small messages**: form (only name and elapsed time reported / unknown key passed through as-is / failures also reported);
    run a day, and the stages the user named must appear in the stage sequence.
  C **work status**: only write status, not output; **no work produced** still goes on screen with the reason.
  D **rehearsal**: it actually rehearsed · output lands in `排练记录.md` · **does not go into the middle column** ·
    problems found → rewrite with comments (the stage sequence shows `rewrite` → `rehearsal`).
    turn the switch off and it is not written.
  G **it really appears when it should**: the five stage messages the user named (start of show / crew revises details /
    discussion after the day ends / summary meeting / organize today's chapter) · today's summary on the two paths
    "day automatic stop" and "**manual stop**" · mid-way temporary pause and resume.
    ⚠ This group and group B **are not the same thing**: B checks the label table, G checks "when the event happens, an extra line shows up on screen".
There is also a **real-device** criterion (`--gui`, run by default): actually open a window and
run MOCK for a day,
read the text of the middle-column widget —— the crew's **body text** output must not appear,
while stages/status/today's summary **must** be present.
Usage: .venv\\Scripts\\python.exe tools/verify_crew_stage.py [--logic-only]
Output: assets/screenshots/crew_stage_report.json
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

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')

from i18n import set_lang                                      # noqa: E402
set_lang('zh')

from display import script as S                                # noqa: E402
from display import story_render as STR                        # noqa: E402

from verify_ui_common import safe_rmtree                       # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


# ══════════════════════════════════════════════════════════════════
#  A —— 中栏白名单
# [EN] A —— middle column whitelist
# ══════════════════════════════════════════════════════════════════
#: 用户**逐条点名**要显示的（这一条判据就是他的原话清单）
# [EN] : what the user **names one by one** to be displayed (this criterion is exactly his verbatim
# [EN] list)
ALLOWED_BY_USER = {
    S.RECAP: '前情提要',
    S.BRIEF: '今日故事简介',
    S.NARRATION: '旁白',
    S.ACTION: '人物动作',
    S.DIALOGUE: '人物台词对话',
    S.SCENE: '场景切换',
    S.AMBIENT: '人物场景介绍 / 外部环境变化',
    S.ENTER: '外部环境变化（有人进来）',
    S.EXIT: '外部环境变化（有人走了）',
    S.EVENT: '冲突提示',
    S.NOTE: '关键变量 / 导演工作分配 / 故障',
    S.STAGE: '剧组阶段小消息',
    S.CREW: '工作人员工作状态卡片',
    S.SUMMARY: '一天停止之后的总结',
    S.CUT: '场景切换',
    S.CUT_BACK: '场景切换',
    S.ASIDE: '旁白（心声）',
    S.RECALL: '旁白（回想）',
    S.PARALLEL: '场景切换（同时）',
    S.TIME: '场景切换（时间行）',
}


def test_whitelist() -> None:
    bad = [k for k in ALLOWED_BY_USER if not S.on_window(k)]
    ok('A1 ★★ 用户点名的每一类都**在**白名单里（逐条对照他的原话）',
       not bad, f'被挡掉的：{[(k, ALLOWED_BY_USER[k]) for k in bad]}' if bad
       else f'{len(ALLOWED_BY_USER)} 类')

    # 名单外的一律挡掉 —— 尤其 `BEAT`（"片刻无话"是画面感，不是用户列的任何一条）
    # [EN] Anything outside the list is blocked —— especially `BEAT` ("a moment of silence" is visual
    # [EN] texture, not any item the user listed)
    out = [k for k in (S.BEAT, S.IMAGE) if S.on_window(k)]
    ok('A2 ★★ 用户没列的**挡掉**（`BEAT` / `IMAGE` 这类不上中栏）',
       not out, f'漏出去的：{out}')

    ok('A3 `kind` 为空时放行（历史路径不传类型 → 一律挡掉会让整条流静默消失）',
       S.on_window('') and S.on_window(None), '')
    ok('A3b ★ 分隔符（`divider:day_end` 这类）放行 —— 它走另一条通道，'
       '而且是用户要的"场景切换"路标，不属于剧组花絮',
       S.on_window('divider:day_end') and S.on_window('divider:scene_end'), '')

    # 界面真的走这个纯函数（不是自己又写了一份判断）
    # [EN] The UI really goes through this pure function (it doesn't write its own separate copy of the
    # [EN] judgment)
    src = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    ok('A4 ★★ 界面的中栏闸门走的是 `S.on_window()`（不是就地又写一个 `in`）',
       'S.on_window(kind)' in src, '')
    # ⚠ 判据要**看语义**不是看字符串：界面里不许自己造一份 kind 白名单。
    #   （第一版写的是"文件名里不许出现 WINDOW_KINDS" —— 而那正是注释里会写的
    #    东西，一条真判据被自己的文档说明弄红了。）
    # [EN] ⚠ The criterion must **look at semantics**, not at strings: the UI must not create its own kind
    # [EN] whitelist.
    # [EN] (The first version said "the string WINDOW_KINDS must not appear in the file name" —— and that
    # [EN] is exactly what appears in comments,
    # [EN] so a real criterion was turned red by its own documentation.)
    ok('A5 ★ 白名单是**唯一出处**（界面不自己造一份 kind 集合）',
       'frozenset({S.' not in src and 'WINDOW_KINDS = ' not in src, '')


# ══════════════════════════════════════════════════════════════════
#  B —— 阶段小消息
# [EN] B —— stage mini-messages
# ══════════════════════════════════════════════════════════════════
def test_stage_lines() -> None:
    s = STR.stage_line('rehearsal', 3.24)
    ok('B1 ★★ 阶段消息＝「记号 + 阶段名 + 用时」',
       s == '▸ 剧组排练 · 3.2s', s)
    ok('B2 ★ 用时不足 0.1 秒就不写那一截（演示模式下全在毫秒级，'
       '写 `0.0s` 会像卡住了）',
       STR.stage_line('shooting', 0.0) == '▸ 开演'
       and STR.stage_line('shooting', 0.05) == '▸ 开演',
       STR.stage_line('shooting', 0.05))
    ok('B3 ★ 十秒以上只写整秒（不给假精度）',
       STR.stage_line('rewrite', 12.7) == '▸ 带意见重新修改 · 13s',
       STR.stage_line('rewrite', 12.7))
    ok('B4 ★ 失败照样报（"卡在哪儿"比什么都重要）',
       STR.stage_line('rehearsal', 2.0, ok=False).endswith('（失败）'),
       STR.stage_line('rehearsal', 2.0, ok=False))
    ok('B5 ★ 认不出的 key **原样显示**（不猜、不编一个好听的名字）',
       STR.stage_line('xyz', 1.0) == '▸ xyz · 1.0s', STR.stage_line('xyz', 1.0))

    # ★ 结构性保证：上下文管理器**拿不到产出**
    # [EN] ★ Structural guarantee: the context manager **cannot get the output**
    import ast as _ast
    import inspect

    from crew import studio as CS
    sig = inspect.signature(CS.Studio.stage)
    ok('B6 ★★ `Studio.stage()` 只收一个阶段名（想推产出的内容也推不出去）',
       list(sig.parameters) == ['self', 'key'], str(list(sig.parameters)))
    # ⚠ 用 AST 看"那一句 `yield` 到底有没有带值" —— 查字符串会被自己的
    #   注释/docstring 弄红（第一版就是这么错的）。
    #   ⚠ 源码要先 `dedent`（`getsource` 带的是方法体的**原始缩进**，
    #     只 `lstrip()` 第一行会让后面几行保持缩进 → IndentationError）。
    # [EN] ⚠ Use AST to check "whether that `yield` actually carries a value" —— checking strings will be
    # [EN] turned red by its own
    # [EN] comments/docstrings (the first version got it wrong exactly this way).
    # [EN] ⚠ The source must first be `dedent`ed (`getsource` carries the **original indentation** of the
    # [EN] method body,
    # [EN] and only `lstrip()`ing the first line leaves the following lines indented → IndentationError).
    import textwrap
    tree = _ast.parse(textwrap.dedent(inspect.getsource(CS.Studio.stage)))
    yields = [n for n in _ast.walk(tree)
              if isinstance(n, (_ast.Yield, _ast.YieldFrom))]
    ok('B7 ★★ 那个 `yield` **不带值**（"只报状态"的结构保证）',
       bool(yields) and all(getattr(n, 'value', None) is None for n in yields),
       f'{len(yields)} 处 yield，带值的 {[type(n).__name__ for n in yields if getattr(n, "value", None) is not None]}')

    # 阶段名与 i18n：表里的每个 key 都翻得出来
    # [EN] Stage names and i18n: every key in the table is translatable
    labels = ['prep', 'novelist', 'screenwriter', 'rehearsal', 'rewrite',
              'shooting', 'pause', 'resume', 'setting_room', 'day_map',
              'day_review', 'wrap_meeting', 'novelize', 'export']
    miss = [k for k in labels if STR.stage_line(k, 1.0) == f'▸ {k} · 1.0s']
    ok('B8 ★ 每个阶段 key 都有中文名（不许原样漏出来）', not miss, str(miss))


# ══════════════════════════════════════════════════════════════════
#  C —— 工作状态（只写状态）
# [EN] C —— working status (status only)
# ══════════════════════════════════════════════════════════════════
def test_crew_line() -> None:
    from crew import studio as CS
    from crew.agents import CrewNote

    line = STR.crew_line('美术', '已交活', 1.2)
    ok('C1 ★★ 工作状态＝「谁 + 什么状态」', line == '· 美术 已交活 · 1.2s', line)
    ok('C2 ★ 没有用时就不写那一截', STR.crew_line('声音', '已交活', 0.0)
       == '· 声音 已交活', STR.crew_line('声音', '已交活', 0.0))
    ok('C3 ★ `full` 档才补一句标题，而且**仍然不是产出全文**',
       STR.crew_line('美术', '已交活', 1.2, detail='今天 2 处')
       == '· 美术 已交活 · 1.2s —— 今天 2 处', '')

    # ★★ 行为判据：把一份**带正文**的产出喂进去，看界面上收到的是什么
    # [EN] ★★ Behavioral criterion: feed in an output **with body text**, and see what the UI receives
    from sim.loop import RunLoop
    seen: list = []
    loop = RunLoop.__new__(RunLoop)
    loop._warn_once = lambda *a, **k: None
    loop._push_narrative = lambda text, pr, **k: seen.append((pr, text, k.get('kind')))
    note = CrewNote(role='art', ok=True, title='今天 2 处：堂内、门口',
                    body='水墨淡彩、纸本质感，低饱和，不做高光与锐利反光；'
                         '主色 #3B4A52 #C9A24E；避免：高饱和霓虹色',
                    data={'用时': 1.2})
    from config import CFG as _C
    old = _C.s('CREW_SCREEN')
    try:
        _C.set('CREW_SCREEN', 'key')
        RunLoop._on_crew_note(loop, note)
    finally:
        _C.set('CREW_SCREEN', old)
    text = seen[-1][1] if seen else ''
    ok('C4 ★★ 产出**正文**不上屏（"水墨淡彩、纸本质感…"一个字都不出现）',
       '水墨淡彩' not in text and '主色' not in text, text[:80])
    ok('C5 ★★ 上屏的是**状态**（`· 美术 已交活 · 1.2s`）',
       text == '· 美术 已交活 · 1.2s', text)
    ok('C6 ★ 词条类型是 `CREW`（界面才知道该按"状态"渲染）',
       seen and seen[-1][2] == S.CREW, str(seen[-1][2]) if seen else '（没推）')

    # 「没出活」照旧带**原因**上屏（故障信号）
    # [EN] "No output produced" still goes on screen with its **reason** (fault signal)
    seen.clear()
    RunLoop._on_crew_note(loop, CrewNote(role='art', ok=False, why='模型没答'))
    ok('C7 ★★ 没出活照旧上屏，而且**带着原因**（那是故障信号，不是内容）',
       seen and '模型没答' in seen[-1][1] and seen[-1][2] == S.NOTE,
       seen[-1][1] if seen else '（没推）')

    # 复盘给的是**内容**（用户白名单里的"一天结束后的总结"）
    # [EN] The recap gives **content** (the "summary after a day ends" in the user's whitelist)
    seen.clear()
    RunLoop._on_crew_note(loop, CrewNote(role='reviewer', ok=True,
                                         title='今日复盘',
                                         body='今天推进了什么。\n\n**存在的问题**\n- 主角连着三拍打转'))
    ok('C8 ★★ 今日总结是**唯一**以内容上屏的剧组产出（用户点名要的）',
       seen and '存在的问题' in seen[-1][1] and seen[-1][2] == S.SUMMARY,
       str(seen[-1][1])[:80] if seen else '（没推）')
    ok('C9 ★ 它带 `■` 记号（一眼看出是"一天的收束"）',
       seen and seen[-1][1].startswith('■ '), str(seen[-1][1])[:30] if seen else '')

    # 档位：off 也要报总结与故障
    # [EN] Level: off must also report summaries and faults
    seen.clear()
    for lv in ('off', 'key', 'full'):
        _C.set('CREW_SCREEN', lv)
        try:
            CS.Studio(world=None, db=None, on_note=seen.append)._announce(
                CrewNote(role='reviewer', ok=True, title='x'))
            CS.Studio(world=None, db=None, on_note=seen.append)._announce(
                CrewNote(role='art', ok=False, why='挂了'))
        finally:
            _C.set('CREW_SCREEN', old)
    ok('C10 ★★ 「今日总结」与「没出活」在**三档里都报**'
       '（off 也不例外 —— 前者是你点名要的，后者是故障信号）',
       len([x for x in seen if x.role == 'reviewer']) == 3
       and len([x for x in seen if x.role == 'art']) == 3,
       f'复盘 {len([x for x in seen if x.role == "reviewer"])}/3，'
       f'故障 {len([x for x in seen if x.role == "art"])}/3')

    # off 不报**普通**工作状态（那是"报多细"的最粗一档）
    # [EN] off does not report **ordinary** working status (that's the coarsest level of "how detailed to
    # [EN] report")
    seen.clear()
    for lv, want in (('off', 0), ('key', 1), ('full', 1)):
        _C.set('CREW_SCREEN', lv)
        try:
            CS.Studio(world=None, db=None, on_note=seen.append)._announce(
                CrewNote(role='props', ok=True, title='道具单'))
        finally:
            _C.set('CREW_SCREEN', old)
        got = len([x for x in seen if x.role == 'props'])
        seen.clear()
        if got != want:
            ok(f'C11 ★ `{lv}` 档的工作状态 {got} 条（期望 {want}）', False, '')
            break
    else:
        ok('C11 ★ 三档管的是"报多细"：off 不报工作状态 · key/full 报', True,
           'off=0 · key=1 · full=1')


# ══════════════════════════════════════════════════════════════════
#  D/E —— 跑一天（排练 · 当天这一章）
# [EN] D/E —— run one day (rehearsal · this chapter of the day)
# ══════════════════════════════════════════════════════════════════
def _run_one_day(tmp: Path, **env):
    """跑**完整的一天**（含 `_end_day`），返回 `(proj, run, loop, world, db, stages, notes)`。

    ⚠ 不能只调 `_compose_day` + `_tick` —— 那样量不到 `_end_day` 里的
      「一天结束后讨论 / 总结会 / 整理当天这一章」三段（这一轮新加的东西
      有一半在那儿）。

    ⚠ 进度节点给 **30 个**（不是 3 个）：E9 要在同一条会话里跑**两天**，
      3 个节点的故事在第一天就跑完了 —— 第二天 `_tick` 一律"到达故事终点"，
      什么都演不出来（第一版就是这么假红的：`当天故事.md` 里没有第 2 天，
      看着像"累积坏了"，其实是**故事已经结束**）。

    ⚠ `env` 里的开关**在跑完之前不能还原**：第一版把 `finally` 写在
      `_run_one_day` 里（返回前就还原了），于是"关掉开关"那两条判据
      量到的还是默认值 —— **假红**。开关的还原交给调用方（见 `test_day`）。
    
        English:
    Run **a complete day** (including `_end_day`), returning `(proj, run, loop, world, db, stages,
    notes)`.
        ⚠ You cannot just call `_compose_day` + `_tick` —— that way you cannot measure the
          three segments in `_end_day`: "discussion after the day ends / summary meeting / organize today's chapter" (half of the new things
          added this round are in there).
        ⚠ Provide **30** progress nodes (not 3): E9 must run in the same session for **two days**,
          the story for 3 nodes finishes on the first day -- on the second day `_tick` uniformly "reaches the story endpoint",
          nothing can be performed (the first version was fake-red like this: there is no day 2 in `当天故事.md`,
          it looks like "accumulation broke", but actually **the story has already ended**).
        ⚠ The switches in `env` **must not be restored before running finishes**: the first version put `finally` inside
          `_run_one_day` (restored before returning), so the two criteria that "turn off the switch"
          still measured the default value -- **fake red**. Restoring the switches is left to the caller (see `test_day`).
    """
    from verify_run_control import make_project
    from store.runfolder import RunFolder
    from sim import setup as SU

    for k, v in env.items():
        CFG.set(k, v)
    proj = make_project(tmp / '排练夹具', nodes=30)
    run = RunFolder(proj.root, '第1次模拟2026-10-07-13-00').create()
    loop, world, db = SU.assemble(proj, run, image_hook=lambda *a, **k: None)
    stages: list[tuple[str, float, bool]] = []
    notes: list[tuple[str, str]] = []
    # ★ 推给中栏的**每一条**也收下来（G 组要查"该出现的时候真的出现了"）。
    #   ⚠ 这里**不能**把 `on_narrative` 写成丢弃式回调再另找地方量 ——
    #     第一版就是这么写的，于是 G 组只能去看 `stages`（阶段）而量不到
    #     `SUMMARY` / `NOTE` 那几条（本判据的历史版本就是这么漏掉"今日总结
    #     真的上屏了吗"这一件事的）。
    # [EN] ★ Every item pushed to the middle column is also captured (group G needs to check "it really
    # [EN] appeared when it should have").
    # [EN] ⚠ Here you **must not** write `on_narrative` as a discarding callback and then measure somewhere
    # [EN] else ——
    # [EN] the first version was written that way, so group G could only look at `stages` (stages) and
    # [EN] could not measure
    # [EN] the `SUMMARY` / `NOTE` items (the historical version of this criterion missed exactly "did
    # [EN] today's summary",
    # [EN] really go on screen?" this one thing).
    rows: list[tuple[int, str, str]] = []
    # ★★ 监听要**透传**（先记录、再转给原来那个回调）。
    #   ⚠ 这一点是本判据的一次真实教训：原来写成
    # [EN] ★★ The listener must **pass through** (record first, then forward to the original callback).
    # [EN] ⚠ This point is a real lesson from this criterion: it was originally written as
    #     `loop.studio._on_stage = lambda ...: stages.append(...)`
    #     —— 直接把 `RunLoop.__init__` 挂上去的回调**顶掉了**。于是
    #     · 阶段再也走不到 `loop._stage_push` → 那条「▸ 剧组排练 · 3.2s」
    #       **一个字都不进中栏**，而 D 组照样绿（它只看 `stages` 这个旁路列表）；
    #     · 剧组产出也走不到 `loop._on_crew_note` → 「■ 今日总结」同样上不了屏。
    #   夹具把被测的那条线**截断**了，却以为自己量到了 —— 这就是
    #   "判据在量一个错的产品"的典型。透传之后，`rows` 里才是读者真看到的。
    # [EN] —— it directly **displaced** the callback attached by `RunLoop.__init__`. As a result,
    # [EN] · the stage could no longer reach `loop._stage_push` → that line "▸ crew rehearsal · 3.2s"
    # [EN] **did not enter the middle column at all**, yet group D stayed green (it only looked at the
    # [EN] `stages` side-channel list);
    # [EN] · crew output also could not reach `loop._on_crew_note` → "■ today's summary" likewise could not
    # [EN] go on screen.
    # [EN] The fixture **cut off** the very line under test, yet thought it had measured it —— this is
    # [EN] the classic case of "the criterion is measuring the wrong product". After pass-through, `rows`
    # [EN] contains what the reader actually sees.
    _orig_stage = getattr(loop.studio, '_on_stage', None)
    _orig_note = getattr(loop.studio, '_on_note', None)

    def _on_stage(k, s, o):
        stages.append((k, s, o))
        if _orig_stage is not None:
            _orig_stage(k, s, o)

    def _on_note(n):
        notes.append((n.role, n.title or ''))
        if _orig_note is not None:
            _orig_note(n)

    loop.studio._on_stage = _on_stage
    loop.studio._on_note = _on_note
    loop._current_day = 1
    loop.on_narrative(lambda t, p, **k: rows.append((p, t, k.get('kind', ''))))
    loop._probe_rows = rows                    # 夹具侧伸手可取（不改返回值签名）
    # [EN] Accessible from the fixture side (without changing the return-value signature)
    loop._probe_stages = stages
    return proj, run, loop, world, db, stages, notes


def _rewind_story(world, day: int) -> None:
    """把故事"倒回还没演完"的状态（夹具用，**只在判据里**）。

    为什么需要它：`_run_one_day` 造的项目进度节点是有限的，跑完一天可能
    已经把节点走完（`_check_progress` 于是每拍都"到达故事终点"，
    `_tick` 什么都不做）—— 那样第二天**根本不会产生正文**，
    E9「按天累积」就量不出来（它需要**真有第二天**）。

    这里只做三件"让它还能接着演"的事：节点状态清零、当前节点指回第一个、
    把在场的人放回当前场景。**不动产品代码**。
    
        English:
    Rewind the story to the "not yet finished performing" state (for fixtures, **only in
    criteria**).
        Why it's needed: the project progress nodes created by `_run_one_day` are finite; finishing one day may
        already have exhausted the nodes (`_check_progress` then "reaches the story endpoint" on every beat,
        `_tick` does nothing) -- in that case the second day **produces no body text at all**,
        and E9 "accumulate by day" cannot be measured (it needs **a real second day**).
        Here only three things are done to "let it keep performing": zero out node states, point the current node back to the first,
        and put the people present back into the current scene. **Do not touch product code**.
    """
    for nd in (getattr(world, 'progress_nodes', None) or []):
        if isinstance(nd, dict):
            nd['状态'] = '未开始'
    nodes = [nd for nd in (getattr(world, 'progress_nodes', None) or [])
             if isinstance(nd, dict)]
    if nodes:
        world.current_node = str(nodes[0].get('id') or '')
    here = str(getattr(world, 'scene', '') or '')
    for ps in (getattr(world, 'people', None) or {}).values():
        try:
            ps.status = '在场'
            if here:
                ps.location = here
        except Exception:                                      # noqa: BLE001
            pass


async def _drive_full_day(loop) -> None:
    """跑一天：**走 `_open_day()`**（与 `run()` 同一条路）+ 几拍 + 收工。

    ⚠ 开场那一段必须调 `_open_day()`，不能自己把 `_crew_prep`/`_compose_day`
      抄一遍 —— 抄一遍的话，`run()` 里新加的一步（比如"开演"那条阶段）
      在判据里量不到，而判据照样绿。
    
        English:
    Run one day: **go through `_open_day()`** (the same path as `run()`) + a few beats + wrap up.
        ⚠ The opening segment must call `_open_day()`, you cannot copy `_crew_prep`/`_compose_day`
          yourself -- if you copy it, a newly added step in `run()` (such as the "start performing" phase)
          cannot be measured by the criteria, yet the criteria still pass green.
    """
    await loop._open_day()
    for i in range(1, 9):
        await loop._tick(i)
    await loop._end_day()


def test_day(tmp: Path) -> None:
    (proj, run, loop, world, db, stages,
     notes) = _run_one_day(tmp, CREW_REHEARSAL='true', CREW_DAY_NOVEL='true',
                           CREW_REHEARSAL_ROUNDS='1')
    asyncio.run(_drive_full_day(loop))
    keys = [k for k, _s, _o in stages]
    report['stages'] = keys
    # ── D 排练 ──
    # [EN] ── D rehearsal ──
    ok('D1 ★★ 剧本定稿后真的排了一遍（阶段序列里有 `rehearsal`）',
       'rehearsal' in keys, str(keys))
    ok('D2 ★★ 顺序：作者写小说 → 剧作者写剧本 → **排练** → 开演',
       _ordered(keys, ['novelist', 'screenwriter', 'rehearsal', 'shooting']),
       str(keys))
    ds = loop._day_script
    ok('D3 ★★ `DayScript` 记下了排练结果（`rounds_rehearsed` ≥ 1）',
       ds is not None and int(getattr(ds, 'rounds_rehearsed', 0) or 0) >= 1,
       f'rounds_rehearsed={getattr(ds, "rounds_rehearsed", None)}')
    ok('D4 ★★ 排练记录落盘了（`排练记录.md`）',
       (run.root / '排练记录.md').is_file(),
       str(sorted(p.name for p in run.root.glob('*.md'))))
    ok('D5 ★★ 排练**不产生正文**（当天的叙事里没有排练的内容）',
       '一屋子人过了一遍' not in ''.join(loop._daily_narrative), '')

    # ── 排出问题 → 带意见重写 → 再排（这是用户要的"再排练 再修改"）──
    # [EN] ── surface problems → rewrite with feedback → rehearse again (this is the user's "rehearse
    # [EN] again, revise again") ──
    ok('D6 ★★ 排练发现问题时会**带意见重写**（阶段里出现 `rewrite`）',
       _rehearsal_fixworks(tmp), '')

    # ── E 当天这一章 ──
    # [EN] ── E this chapter of the day ──
    ok('E1 ★★ 阶段序列里有「总结会」与「整理当天这一章」',
       'wrap_meeting' in keys and 'novelize' in keys, str(keys[-6:]))
    book = run.root / '当天故事.md'
    ok('E2 ★★ 整理稿落进 `当天故事.md`（**按天累积**的一份可读稿）',
       book.is_file() and '第 1 天' in book.read_text(encoding='utf-8'),
       str(sorted(p.name for p in run.root.glob('*.md'))))
    body = book.read_text(encoding='utf-8') if book.is_file() else ''
    ok('E3 ★★ `当天故事.md` 里装的是**小说**（不是剧本体的词条清单）',
       '这一天的戏收在灯上' in body
       and '〔' not in body.split('## 第 1 天')[-1][:400],
       body.split('## 第 1 天')[-1][:60].replace('\n', ' ') if body else '（空）')
    review = run.root / '今日总结.md'
    rt = review.read_text(encoding='utf-8') if review.is_file() else ''
    ok('E4 ★★ 「今日总结」里带着「今天这一章（整理稿）」（用户点名要的）',
       '今天这一章（整理稿）' in rt, rt[:0] or f'{len(rt)} 字')
    ok('E5 ★ 整理稿与复盘**并存**（不是把复盘覆盖掉）',
       '剧情总结' in rt or '存在的问题' in rt or '■' in rt or '今天推进' in rt,
       rt[-120:].replace('\n', ' '))
    ok('E6 ★ 整理当天这一章**不产生重复上屏**（只有阶段小消息）',
       [k for k in keys if k == 'novelize'] == ['novelize'], '')

    # ── E9：**真的按天累积**（跑第二天，第一天那节必须还在）──
    #   ⚠ 只跑一天量不出这件事：一天时"累积"与"覆盖"的结果一模一样
    #     （反例法第 ⑭ 条当场证明——把 old 恒置空，一条判据都不红）。
    #     要证明累积，必须**跑到第二天再回头看第一天**。
    # [EN] ── E9: **really accumulates by day** (run the second day, the first day's section must still be
    # [EN] there) ──
    # [EN] ⚠ Running only one day cannot measure this: with one day, "accumulate" and "overwrite" produce
    # [EN] identical results
    # [EN] (counterexample method item ⑭ proves it on the spot —— set old permanently empty, and not a
    # [EN] single criterion turns red).
    # [EN] To prove accumulation, you must **run to the second day and then look back at the first day**.
    loop._current_day = 2
    try:
        loop.world.game_day = 2
    except Exception:                                          # noqa: BLE001
        pass
    _rewind_story(loop.world, 2)          # 让故事还能接着演（见它的说明）
    # [EN] Let the story continue to play (see its description)
    asyncio.run(_drive_full_day(loop))
    body2 = book.read_text(encoding='utf-8') if book.is_file() else ''
    ok('E9 ★★ 第二天跑完，`当天故事.md` 里**第一天那一节还在**'
       '（按天累积，不是一天一覆盖）',
       '## 第 1 天' in body2 and '## 第 2 天' in body2,
       [ln for ln in body2.splitlines() if ln.startswith('## ')])
    ok('E10 ★ 第二天的那一节的正文是**第二天新写的**（不是把第一节抄一遍）',
       body2.index('## 第 2 天') > body2.index('## 第 1 天')
       and len(body2.split('## 第 2 天')[-1].strip()) > 10, '')

    safe_rmtree(tmp / '排练夹具', ignore_errors=True)

    # ── 关掉开关 → 两件事都不做（判据不是恒真）──
    # [EN] ── turn off the switch → do neither thing (the criterion is not vacuously true) ──
    t2 = tmp / 'off'
    t2.mkdir(parents=True, exist_ok=True)
    _saved = {k: CFG.raw(k) for k in ('CREW_REHEARSAL', 'CREW_DAY_NOVEL')}
    try:
        (proj2, run2, loop2, _w2, _d2, stages2,
         _n2) = _run_one_day(t2, CREW_REHEARSAL='false', CREW_DAY_NOVEL='false')
        asyncio.run(_drive_full_day(loop2))
    finally:
        for k, v in _saved.items():
            if v is not None:
                CFG.set(k, v)
    k2 = [k for k, _s, _o in stages2]
    ok('E7 ★ 关掉 `CREW_REHEARSAL` / `CREW_DAY_NOVEL` → 两件事都不做',
       'rehearsal' not in k2 and 'novelize' not in k2
       and not (run2.root / '当天故事.md').is_file(), str(k2))
    ok('E8 ★ 但**阶段序列本身**照旧（开演 / 总结会这些不归那两个开关管）',
       'shooting' in k2 and 'day_review' in k2, str(k2))
    safe_rmtree(t2, ignore_errors=True)


def _ordered(keys: list[str], want: list[str]) -> bool:
    """`want` 在 `keys` 里**按这个先后**出现（允许中间夹别的）。
        English:
    `want` appears in `keys` **in this order** (other entries may be interspersed in between).
    """
    i = -1
    for w in want:
        try:
            i = keys.index(w, i + 1)
        except ValueError:
            return False
    return True


def _rehearsal_fixworks(tmp: Path) -> bool:
    """排练报出问题 → 剧本真的被带着意见重写了一遍。

    ★ 打桩的是**排练那一次调用**（`crew.agents.ask`，按 purpose 区分）：
      第一次排练返回两条"走不下去"，第二次返回空 —— 于是序列应当是
      `… → rehearsal（报问题）→ rewrite（改）→ rehearsal（过了）→ shooting`。
    
        English:
    Rehearsal reports problems -> the script really is rewritten with the feedback.
        ★ What is stubbed is **the rehearsal call** (`crew.agents.ask`, distinguished by purpose):
          the first rehearsal returns two "cannot continue", the second returns empty -- so the sequence should be
          `... -> rehearsal (reports problems) -> rewrite (fixes) -> rehearsal (passes) -> shooting`.
    """
    import crew.agents as CA
    from llm.replies import Reply

    t = tmp / 'fix'
    t.mkdir(parents=True, exist_ok=True)
    (proj, run, loop, world, db, stages, _notes) = _run_one_day(t)
    seen_rehearsal = {'n': 0}

    async def _fake(tier, messages, **kw):
        purpose = str(kw.get('purpose') or '')
        if purpose == 'crew_rehearsal':
            seen_rehearsal['n'] += 1
            if seen_rehearsal['n'] == 1:
                return Reply(ok=True, value={
                    '问题': [{'拍': 2, '谁': '主角',
                              '问题': '他这时人不在柜上', '怎么改': '让他从后院走出来'}],
                    '结论': '第二拍没人可演'}, raw='{}', meta={})
            return Reply(ok=True, value={'问题': [], '结论': '改后走得通'},
                         raw='{}', meta={})
        # 其余照旧走演示模式
        # [EN] Everything else still goes through demo mode
        from llm import mock
        want = kw.get('want')
        out = mock.mock_reply(messages, purpose)
        if want is dict:
            try:
                out = json.loads(out) if isinstance(out, str) else out
            except Exception:                                  # noqa: BLE001
                out = {}
        return Reply(ok=True, value=out, raw='', meta={})

    old = CA.ask
    CA.ask = _fake
    try:
        asyncio.run(_drive_full_day(loop))
    finally:
        CA.ask = old
    keys = [k for k, _s, _o in stages]
    # 验证打桩真的生效了（否则这条判据是恒真的）
    # [EN] Verify that the stubbing really took effect (otherwise this criterion is vacuously true)
    if seen_rehearsal['n'] < 2:
        print(f'    ！排练只被调了 {seen_rehearsal["n"]} 次（打桩没生效？）',
              flush=True)
        return False
    good = _ordered(keys, ['rehearsal', 'rewrite', 'rehearsal'])
    ds = loop._day_script
    if not good or ds is None or int(ds.rounds_rehearsed or 0) < 2:
        print(f'    ！阶段序列 {keys} · rounds_rehearsed='
              f'{getattr(ds, "rounds_rehearsed", None)}', flush=True)
        return False
    safe_rmtree(t, ignore_errors=True)
    return True


# ══════════════════════════════════════════════════════════════════
#  F —— 真机：中栏里到底出现了什么
# [EN] F —— real machine: what actually appears in the middle column
# ══════════════════════════════════════════════════════════════════
def _find_btn(root, label: str):
    """控件树里找按钮（有 `on_click` 且文字精确相等）。

    ⚠ 不要按类名找（`ft.Button` / `ft.ElevatedButton`…）—— Flet 版本的
      按钮类名与本项目用的控件构造方式不一定对得上，第一版写了
      `ft.ElevatedButton` 直接 `AttributeError`。**按行为找**（谁接了点击）。
    
        English:
    Find the button in the widget tree (has `on_click` and exact text match).
        ⚠ Do not find by class name (`ft.Button` / `ft.ElevatedButton`...) -- the Flet version's
          button class names do not necessarily match the widget construction method this project uses; the first version wrote
          `ft.ElevatedButton` and got a direct `AttributeError`. **Find by behavior** (whoever has the click handler).
    """
    import verify_ui_common as VU
    for c in (VU.walk(root) if root is not None else []):
        if (hasattr(c, 'on_click') and getattr(c, 'on_click', None)
                and VU.text_of(c) == label):
            return c
    return None


async def test_real_gui(page) -> None:
    import flet as ft

    import verify_ui_common as VU
    from gui.app_flet import NovelWorldApp
    from verify_run_control import make_project

    tmp = Path(tempfile.mkdtemp(prefix='nws_stage_gui_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    # ⚠⚠ **真机段必须自己备份/还原 `.env`**（本项目踩过 5 次的那个坑）：
    #   点「开始推演」会把内存里的配置 `CFG.save()` 写回盘，
    #   于是 `MOCK_LLM` 与 `DEFAULT_PROJECTS_DIR` 被写成测试值。
    #   第一版没做这一步，跑完 `.env` 真的被改了（这一轮第 6 次）。
    # [EN] ⚠⚠ **The real-machine section must back up/restore `.env` itself** (the pit this project has
    # [EN] stepped in 5 times):
    # [EN] clicking "start inference" writes the in-memory config back to disk via `CFG.save()`,
    # [EN] so `MOCK_LLM` and `DEFAULT_PROJECTS_DIR` get written as test values.
    # [EN] The first version did not do this step, and after running, `.env` really was changed (the 6th
    # [EN] time this round).
    env_path = APP_DIR / '.env'
    env_backup = env_path.read_text(encoding='utf-8') if env_path.exists() else None
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(1.8)
    try:
        await _gui_checks(page, app, tmp)
    finally:
        if env_backup is not None:
            try:
                env_path.write_text(env_backup, encoding='utf-8')
                report['env_restored'] = True
            except OSError as e:                               # noqa: BLE001
                report['env_restore_error'] = str(e)
        safe_rmtree(tmp, ignore_errors=True)


async def _gui_checks(page, app, tmp: Path) -> None:
    import verify_ui_common as VU
    from verify_run_control import make_project

    page.enable_screenshots = True
    # ⚠ **必须先真开跑**：中栏只有在"正在跑"时才渲染实时流（停跑后它回落到
    #   落盘剧本那条分支，`_live_lines` 根本不参与渲染）。
    #   步骤照抄 `verify_story_flow.gui_checks`（同一套夹具，别再自创一份 ——
    #   第一版自己找向导输入框，`AttributeError` 之后一路空转到超时）。
    # [EN] ⚠ **It must actually be running first**: the middle column only renders the live stream while
    # [EN] "running" (after stopping it falls back to
    # [EN] the saved-script branch, and `_live_lines` does not participate in rendering at all).
    # [EN] Copy the steps from `verify_story_flow.gui_checks` (same fixture set, do not invent another one
    # [EN] ——
    # [EN] the first version found the wizard input box itself, and after an `AttributeError` it spun all
    # [EN] the way to timeout).
    proj = make_project(tmp / '中栏夹具')
    app.current_project = proj
    app.show_main_screen()
    await asyncio.sleep(1.0)
    dlg = app.show_start_story_dialog()
    page.update()
    await asyncio.sleep(0.6)
    btn = _find_btn(dlg, '开始推演')
    if btn is not None:
        btn.on_click(None)
    for _ in range(300):
        await asyncio.sleep(0.1)
        if app.session is not None and app.session.is_alive:
            break
    ok('F0 会话真的起来了（下面的取证要在"正在跑"状态下做）',
       app.session is not None and app.session.is_alive,
       str(getattr(app.session, 'status', None)))

    # 等"开拍前准备"那一串阶段真的上屏（`_open_day` 一跑就有，很快）
    # [EN] Wait for the string of stages "pre-shoot preparation" to really go on screen (it appears as soon
    # [EN] as `_open_day` runs, very quickly)
    for _ in range(300):
        await asyncio.sleep(0.1)
        if any(it[2] == S.STAGE for it in app._live_lines):
            break
    # ★ 手动把这一天收掉，拿到**真的**收工总结与工作状态
    #   （MOCK 下时钟走得慢，等自然跨天要几分钟 —— 判据不能靠等）。
    #   ⚠ 真正跑推演的是 `session.loop`（`RunSession` 只是个包装），
    #     调 `session._end_day` 会 AttributeError（第一版就是这么错的）。
    # [EN] ★ Manually close out the day, and get the **real** wrap-up summary and working status
    # [EN] (under MOCK the clock runs slowly; waiting for a natural day change takes several minutes —— the
    # [EN] criterion cannot rely on waiting).
    # [EN] ⚠ What actually runs the inference is `session.loop` (`RunSession` is just a wrapper),
    # [EN] calling `session._end_day` will AttributeError (the first version got it wrong exactly this
    # [EN] way).
    try:
        app.session.pause()
        await asyncio.sleep(0.4)
        await app.session.loop._end_day()
    except Exception as e:                                     # noqa: BLE001
        print(f'    ！手动收工失败：{e!r}', flush=True)
    await asyncio.sleep(1.5)

    rows = list(app._live_lines)
    text = '\n'.join(str(r[1]) for r in rows)
    kinds = [r[2] for r in rows]
    report['gui_kinds'] = sorted({k for k in kinds if k})
    report['gui_stage_lines'] = [r[1] for r in rows if r[2] == S.STAGE][:8]
    report['gui_crew_lines'] = [r[1] for r in rows if r[2] == S.CREW][:8]
    report['gui_summary'] = [str(r[1])[:60] for r in rows if r[2] == S.SUMMARY]

    # ⚠ **分隔符不是词条**：它们走的是另一条通道（`on_divider`），
    #   在 `_live_lines` 里长成 `divider:day_end` 这种样子 —— 那是界面的
    #   内部记号，不属于"叙事的一种 kind"，白名单管不着它们。
    #   （第一版把它们算进去，F1 假红一次。）
    # [EN] ⚠ **Dividers are not entries**: they go through another channel (`on_divider`),
    # [EN] and in `_live_lines` they grow into things like `divider:day_end` —— that is the UI's
    # [EN] internal token, not "a kind of narrative", so the whitelist does not govern them.
    # [EN] (The first version counted them in, and F1 falsely went red once.)
    out = [k for k in kinds if k and not k.startswith('divider:')
           and not S.on_window(k)]
    ok('F1 ★★ 真机中栏里的每一条**都在白名单里**（没有漏网的 kind）',
       not out, f'漏出去：{sorted(set(out))}')

    leak = [x for x in ('水墨淡彩', '纸本质感', '主色 #', '场景中可见',
                        '洗得发白的靛布短褂', '底噪', '摊开的账本',
                        '一屋子人过了一遍')
            if x in text]
    ok('F2 ★★ 剧组产出的**正文一个字都没进中栏**'
       '（美术/造型/道具/声音/排练的产出）',
       not leak, f'漏出去的字：{leak}' if leak else '干净')

    ok('F3 ★★ 阶段小消息在（`▸ 开拍前准备` / `▸ 作者写小说` 这类）',
       any(str(r[1]).startswith('▸ ') for r in rows),
       str([r[1] for r in rows if r[2] == S.STAGE][:6]))
    ok('F4 ★★ 工作状态卡片在（`· 美术 已交活` 这类）',
       any(str(r[1]).startswith('· ') for r in rows),
       str([r[1] for r in rows if r[2] == S.CREW][:6]))
    ok('F5 ★★ 今日总结在（`■ 今日总结`，用户点名的"一天结束后的总结"）',
       any(str(r[1]).startswith('■ ') for r in rows),
       str([str(r[1])[:30] for r in rows if r[2] == S.SUMMARY][:2]))

    # ★ 控件树里也真的有（`_live_lines` 是"记下来的"，控件树是"画出来的"）
    # [EN] ★ They really are in the widget tree too (`_live_lines` is "recorded", the widget tree is
    # [EN] "drawn")
    col = app._ui_run.get('narrative')
    shown = '\n'.join((VU.text_of(c) or '') for c in VU.walk(col)) if col else ''
    ok('F6 ★★ 阶段 / 状态 / 总结 真的**画进了中栏控件树**（不只是记在列表里）',
       '▸' in shown and '·' in shown and '■' in shown,
       f'控件树 {len(shown)} 字')

    # ★★★ 开演前那几块（2026-10-07 用户报「都没了」）—— **在真机控件树里**验一遍。
    # [EN] ★★★ The blocks before the show starts (reported by the user on 2026-10-07 as "all gone") ——
    # [EN] verify them once **in the real-machine widget tree**.
    #
    # 为什么必须放在这一层：用户看到的是**画出来的东西**，而"记进了
    # `_live_lines`"不等于"画出来了"（渲染分支、白名单、样式任何一处出问题
    # 都会让它消失）。这三块的记号各不相同，正好可以逐记号点验：
    #   `§` 前情提要 · `▷` 今日剧情简介 · `▤` 今日任务（场景介绍是 AMBIENT，没有记号）。
    # [EN] Why this must be placed at this layer: what the user sees is **the drawn thing**, and "recorded
    # [EN] into
    # [EN] `_live_lines`" does not equal "drawn" (any problem in the render branch, whitelist, or style
    # [EN] will make it disappear). The tokens of these three blocks are all different, which is perfect
    # [EN] for verifying token by token:
    # [EN] `§` previously on · `▷` today's plot summary · `▤` today's tasks (the scene intro is AMBIENT,
    # [EN] with no token).
    ok('F7 ★★★ 开演前的三块真的**画进了中栏**：'
       '§ 前情提要 / ▷ 今日剧情简介 / ▤ 今日任务'
       '（用户报"卡片都没了"就是这三块）',
       '§' in shown and '▷' in shown and '▤' in shown,
       f'有 §={"§" in shown} ▷={"▷" in shown} ▤={"▤" in shown}；'
       f'控件树 {len(shown)} 字')
    ok('F7 ★★ 场景介绍也在（它是 AMBIENT，没有记号 —— 按 kind 查）',
       any(str(it[2]) == S.AMBIENT for it in app._live_lines),
       str([str(it[1])[:30] for it in app._live_lines
            if str(it[2]) == S.AMBIENT][:2]))

    png = await page.take_screenshot()
    (OUT / 'crew_stage_chat.png').write_bytes(png or b'')


# ══════════════════════════════════════════════════════════════════
#  G —— 用户**点名要显示**的那几条：该出现的时候，真的出现了
# [EN] G —— the few that the user **explicitly asked to be displayed**: they actually appear when they
# [EN] should
# ══════════════════════════════════════════════════════════════════
#  ⚠ 为什么单开一组：B 组查的是**标签表**（每个阶段 key 有中文名）——
#    那是"文案对不对"；这一组查的是"**这件事发生时，屏幕上多了一条**"。
#    两者差着整整一层：标签表里有 `pause` 这一条，而 `pause()` 里那句
#    `_stage_start('pause')` 被删掉时，B 组**一条都不会红**。
#    本项目最忌的正是这个（2026-10-07 第一轮审计一次抓到五处"函数在、没人调"）。
# [EN] ⚠ Why a separate group: group B checks the **label table** (each stage key has a Chinese name)
# [EN] ——
# [EN] that is "is the wording right"; this group checks "**when this thing happens, an extra line
# [EN] shows up on screen**".
# [EN] The two differ by a whole layer: the label table has a `pause` entry, but when the line
# [EN] `_stage_start('pause')` inside `pause()` is deleted, group B **will not go red on a single
# [EN] item**.
# [EN] This is exactly what this project dreads most (the first round of audits on 2026-10-07 caught
# [EN] five cases of "function exists, nobody calls it" at once).
#
#  用户逐条点名要显示、且此前**没有行为级判据**的四条：
#    开演 · 剧组重新修改细节 · 一天结束后讨论 · 总结会
#  ＋ 他专门写在前一句的「**手动停止**以及一天自动停止之后的总结」。
# [EN] Four items the user named one by one for display and that previously had **no behavior-level
# [EN] criterion**:
# [EN] start of show · crew revises details · discussion after the day ends · summary meeting
# [EN] + the one he specifically wrote in the preceding sentence: "**manual stop** and the summary
# [EN] after the day's automatic stop".
def test_window_events(tmp: Path) -> None:
    t = tmp / 'events'
    t.mkdir(parents=True, exist_ok=True)
    (_proj, _run, loop, _w, _d, stages, _n) = _run_one_day(t, CREW_REHEARSAL='true')
    asyncio.run(_drive_full_day(loop))
    rows = list(getattr(loop, '_probe_rows', []))
    keys = [k for k, _s, _o in stages]
    kinds = [k for _p, _t, k in rows]
    report['event_stages'] = keys

    # ① 用户逐条点名的五条阶段消息
    # [EN] ① the five stage messages the user named one by one
    want = {'setting_room': '剧组重新修改设定细节',
            'day_review': '一天结束后讨论',
            'wrap_meeting': '总结会',
            'novelize': '整理当天这一章',
            'shooting': '开演'}
    miss = [f'{k}（{v}）' for k, v in want.items() if k not in keys]
    ok('G1 ★★ 用户点名的五条阶段消息都**真的上报了**（开演 · 剧组重新修改设定细节'
       ' · 一天结束后讨论 · 总结会 · 整理当天这一章）',
       not miss, (f'缺：{miss}' if miss else str(keys)))

    # ②「一天自动停止之后的总结」——**逻辑层**也要量到 `SUMMARY`
    #   ⚠ 真机层有 F5；那是另一档证据（"画进控件树了"），
    #     不能拿它顶替这一条（本判据以前就只在真机层量它）。
    # [EN] ② "summary after the day's automatic stop" —— the **logic layer** must also measure `SUMMARY`
    # [EN] ⚠ The real-device layer has F5; that is a different tier of evidence ("it was drawn into the
    # [EN] widget tree"),
    # [EN] it cannot be used to substitute for this item (this criterion previously only measured it at the
    # [EN] real-device layer).
    ok('G2 ★★ 一天走完，「今日总结」真的**推到了中栏**'
       '（不是只落进 `今日总结.md`）',
       S.SUMMARY in kinds,
       str([str(tt)[:24] for _p, tt, kk in rows if kk == S.SUMMARY][:1]))
    ok('G2b ★ 上屏的今日总结**带 `■` 记号**且**带正文**（不是只报"已交活"）',
       any(kk == S.SUMMARY and str(tt).startswith('■ ') and len(str(tt)) > 40
           for _p, tt, kk in rows), '')

    # ③ **手动停止之后的总结**（用户逐条点名里的那半句）
    #   ⚠ 必须**走 `run()`**：它才是"作者按下停止"的真实路径
    #     （`_finish("手动停止")` 由它调）。直接调 `_end_day()` 量不到
    #     "停下之后有没有补收工"这件事。
    # [EN] ③ **summary after manual stop** (that half-sentence in the user's item-by-item list)
    # [EN] ⚠ It must **go through `run()`**: that is the real path for "the author presses stop"
    # [EN] (it calls `_finish("手动停止")`). Calling `_end_day()` directly cannot measure
    # [EN] the question "after stopping, is there a wrap-up".
    reason, kinds2, keys2 = _manual_stop(t)
    report['stop'] = {'reason': reason, 'last_kinds': kinds2[-8:],
                      'last_stages': keys2[-8:]}
    ok('G3 ★★ 手动停止走的是**收尾那条路**（`run()` 返回「手动停止」）',
       reason == '手动停止', str(reason))
    ok('G3b ★★ **手动停止之后照样有「今日总结」**'
       '（用户原话：「手动停止以及一天自动停止之后的总结」）',
       S.SUMMARY in kinds2, f'停止后最后几条 kind：{kinds2[-6:]}')
    ok('G3c ★ 手动停止之后**总结会**也照开（收工那一段没被跳过）',
       'wrap_meeting' in keys2, str([k for k in keys2 if k in
                                     ('day_review', 'wrap_meeting', 'novelize')]))

    # ④ 中间临时暂停 / 继续
    #   ⚠ 这两句**故意写在协程外**：界面按下暂停时就是这个情形，
    #     它顺带把 G5（"显示队列排不上也不许吞掉中栏那条"）一起证了。
    # [EN] ④ mid-way temporary pause / resume
    # [EN] ⚠ These two lines are **deliberately written outside the coroutine**: this is the situation when
    # [EN] pause is pressed in the UI,
    # [EN] and it incidentally also proves G5 ("if the display queue cannot keep up, you still must not
    # [EN] swallow that middle-column line").
    loop.pause()
    loop.resume()
    said = [str(tt) for _p, tt, _k in loop._probe_rows]
    mine = [x for x in said if '临时暂停' in x or x.endswith('继续')]
    ok('G4 ★★ 「中途临时暂停」「继续」真的各推一条（只报状态，不报原因）',
       any('临时暂停' in x for x in said) and any('继续' in x for x in said),
       str(mine[-3:]))
    ok('G4b ★ 暂停那条**不写用时**（`▸ 临时暂停`，而不是 `▸ 临时暂停 · 0.0s`）'
       '—— 那个时刻本来就没有耗时可言，硬写一个 0.0s 会让人以为它卡住了',
       bool(mine) and all('·' not in x for x in mine), str(mine[-2:]))

    # ⑤ 显示队列坏了，也不许把中栏那条一起吞掉
    #   （2026-10-07 的真 bug：`_push_narrative` 先 `create_task` 再喊回调，
    #     `create_task` 在没有事件循环时抛 → 回调再也执行不到 → 那条消息凭空消失）
    # [EN] ⑤ even if the display queue is broken, you still must not swallow that middle-column line
    # [EN] (the real bug from 2026-10-07: `_push_narrative` calls `create_task` first and then the
    # [EN] callback,
    # [EN] `create_task` throws when there is no event loop → the callback can never run → that message
    # [EN] vanishes into thin air)
    got: list[str] = []
    saved_disp = getattr(loop, 'display', None)
    saved_cb = loop._on_narrative
    try:
        loop.on_narrative(lambda tt, pp, **k: got.append(str(tt)))
        loop.display = None                       # 显示队列"坏了"
        # [EN] display queue "broken"
        loop._push_narrative('（夹具）显示队列没了也得喊人', 3, kind=S.NOTE)
    except Exception as e:                                     # noqa: BLE001
        got.append(f'<抛了 {e!r}>')
    finally:
        loop.display = saved_disp
        loop._on_narrative = saved_cb
    ok('G5 ★★ 显示队列排不上（协程外 / `display` 没建）时，**中栏那条照样发**'
       '（不许被它连累吞掉）',
       got == ['（夹具）显示队列没了也得喊人'], str(got))
    safe_rmtree(t, ignore_errors=True)


def _manual_stop(tmp: Path):
    """**真按一次「停止」**：让 `run()` 自己走完收尾，返回
    `(结束原因, 上屏的 kind 序列, 阶段序列)`。

    ⚠ `BEAT_SECONDS=1`：默认值下每拍要等好几分钟，判据不能靠等。
      停之前先等它**真跑起来**（`_tick_no ≥ 2`），否则"停止"停在开场那一段，
      收工那一段根本没机会跑 —— 那样 G3b 会**假红**（看着像"停止后没有总结"）。
    ⚠ 两项配置**跑完必须还原**（同类夹具第一版把还原写在返回前，量到默认值）。
    
        English:
    **Really press "Stop" once**: let `run()` finish its wrap-up on its own, returning
        `(end reason, kind sequence on screen, phase sequence)`.
        ⚠ `BEAT_SECONDS=1`: with the default value each beat waits several minutes, criteria cannot rely on waiting.
          Before stopping, first wait for it to **really start running** (`_tick_no ≥ 2`), otherwise "stop" stops in the opening segment,
          and the wrap-up segment never gets a chance to run -- then G3b will be **fake red** (looks like "no summary after stopping").
        ⚠ Two config items **must be restored after running** (the same kind of fixture in the first version wrote the restore before returning, measuring the default value).
    """
    t = tmp / 'stop'
    t.mkdir(parents=True, exist_ok=True)
    saved = {k: CFG.raw(k) for k in ('BEAT_SECONDS', 'TIME_RATIO')}
    (_proj, _run, loop, _w, _d, stages, _n) = _run_one_day(t)
    CFG.set('BEAT_SECONDS', '1')
    CFG.set('TIME_RATIO', '120')

    async def _drive() -> str:
        task = asyncio.create_task(loop.run())
        for _ in range(300):
            await asyncio.sleep(0.5)
            if int(getattr(loop, '_tick_no', 0) or 0) >= 2:
                break
        loop.stop()
        return await task

    try:
        reason = asyncio.run(_drive())
    finally:
        for k, v in saved.items():
            if v is not None:
                CFG.set(k, v)
    rows = list(getattr(loop, '_probe_rows', []))
    return reason, [k for _p, _t, k in rows], [k for k, _s, _o in stages]


def _logic_main(tmp: Path) -> None:
    print('\n【A】中栏白名单')
    test_whitelist()
    print('\n【B】阶段小消息')
    test_stage_lines()
    print('\n【C】工作状态（只写状态）')
    test_crew_line()
    print('\n【D/E】跑一天（排练 · 当天这一章）')
    test_day(tmp)
    print('\n【G】点名要显示的那几条：该出现时真的出现了')
    test_window_events(tmp)


def finish() -> int:
    """写报告并返回退出码。

    ⚠ **必须在 `shutdown()` 之前求值**：`shutdown` 会把进程送走
      （见项目记忆里那条"验证 → 写报告 → shutdown → exit_now"的硬顺序）。
      第一版把报告写在 `main()` 的尾部 —— 真机段跑完进程已经没了，
      报告还停在上一版（"38/38 全绿"看着像通过，其实是**旧文件**）。
    
        English:
    Write the report and return the exit code.
        ⚠ **Must be evaluated before `shutdown()`**: `shutdown` will send the process away
          (see that hard order in project memory: "verify -> write report -> shutdown -> exit_now").
          The first version wrote the report at the tail of `main()` -- by the time the real machine segment finished the process was already gone,
          and the report was still from the previous version ("38/38 all green" looks like a pass, but it is actually an **old file**).
    """
    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['passed'] = len(checks) - len(bad)
    report['total'] = len(checks)
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'crew_stage_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  排练 / 中栏白名单 / 状态消息：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"][:120]}]')
    if report.get('fatal'):
        print(report['fatal'][-1200:])
    print('─' * 62)
    return 0 if report['ok'] else 1


def main() -> int:
    logic_only = '--logic-only' in sys.argv
    tmp = Path(tempfile.mkdtemp(prefix='nws_crew_stage_'))
    try:
        from verify_ui_common import isolate_projects_dir
        isolate_projects_dir(tmp / 'Projects')
    except Exception:                                          # noqa: BLE001
        pass
    try:
        _logic_main(tmp)
    except BaseException:                                      # noqa: BLE001
        traceback.print_exc()
        report['fatal'] = traceback.format_exc()
        ok('Z 判据自己跑通（没被异常打断）', False,
           report['fatal'].splitlines()[-1])
    finally:
        safe_rmtree(tmp, ignore_errors=True)

    if logic_only or report.get('fatal'):
        return finish()

    import flet as ft
    print('\n【F】真机：中栏里到底出现了什么')

    async def entry(page) -> None:
        from util.flet_shutdown import shutdown
        try:
            await test_real_gui(page)
        except BaseException:                                  # noqa: BLE001
            traceback.print_exc()
            ok('F 真机判据自己跑通', False,
               traceback.format_exc().splitlines()[-1])
        # ★ 顺序硬约束：**先写报告（`finish()`），再 shutdown**
        #   （`shutdown` 之后不会再跑任何一行代码）。
        # [EN] ★ hard ordering constraint: **write the report first (`finish()`), then shutdown**
        # [EN] (after `shutdown` not a single line of code will run again).
        await shutdown(page, code=finish())

    ft.run(entry)
    return 0


if __name__ == '__main__':
    sys.exit(main())
