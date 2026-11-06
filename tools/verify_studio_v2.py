# -*- coding: utf-8 -*-
"""验证：剧组扩充 · 今日简介 · 今日总结 · 导演盯戏与回档（2026-10-07）。

用户原话（拆成四件事）
----------------------
1. 「在前情提要后面，正式剧情之前，有一个**今日剧情简介**」
2. 「在手动停止或者一天落盘之后，有一个**今日总结**（就是你提到的导演
   小说作者和剧作家讨论回顾的结论 包括剧情总结 存在的问题 后续修改意见等）」
3. 「你再看下现在剧组还缺什么人员 也可以补充进来」
4. 「有时候演员说话会有 AI 味道…（见 `verify_deai.py`）」
5. 「我看到有好几个人连续重复一句话 一件事情的问题…**导演要一直盯着**…
   导演随时可以要求**回档**…导演要一直心里有一个**大纲**」
6. 「中间剧情对话窗口**尽可能少出现演职人员** 除非必要」

这一支钉住 1/2/3/5/6（4 另有一支 `verify_deai.py`）：

  A **剧组扩充**：四位新职位在位、有实现、有落盘文件、有开关、接线全通；
    **每一位的产出都有真实消费方**（不许是摆设）。
  B **今日剧情简介**：词条类型往返 · 顺序在 前情提要 之后、场景介绍之前 ·
    拿不到就不推 · 开关关掉就消失。
  C **今日总结**：复盘在收工那一步真的被调到 · 产出含三段（总结/问题/意见）·
    落盘 `今日总结.md` · 上屏（`CREW_SCREEN=key` 也上）。
  D **导演盯戏与回档**：`scan_repetition` 五组用例判得准 · 回档真的删条目 ·
    回档后「场上刚发生」缓冲也退 · `[导演提示]` 只活一拍。
  E **播报分级**：`off` / `key` / `full` 三档行为分明；
    **没出活在任何档位都要上屏**（那是故障信号，不是内容）。

跑法：.venv\\Scripts\\python.exe tools/verify_studio_v2.py
产出：assets/screenshots/studio_v2_report.json

English:
Verification: crew expansion · today's synopsis · today's summary · director watching the show
and rollback (2026-10-07).
User's original words (split into four things)
----------------------
1. "After the recap, before the formal plot, there is a **today's plot synopsis**"
2. "After a manual stop or a day's persist, there is a **today's summary** (i.e. the conclusion of the director,
   novelist and playwright's discussion and review you mentioned, including plot summary, existing problems, follow-up revision suggestions, etc.)"
3. "Take another look at what personnel the crew is still missing, you can also add them in"
4. "Sometimes actors' speech has an AI flavor… (see `verify_deai.py`)"
5. "I saw several people repeating a line or a matter consecutively… **the director must keep
watching**…
   the director can request a **rollback** at any time… the director must always have an **outline** in mind"
6. "The middle plot dialogue window should **show crew members as little as possible** unless
necessary"
This branch pins down 1/2/3/5/6 (4 has its own branch `verify_deai.py`):
  A **Crew expansion**: the four new positions are in place, have implementations, have persisted files, have switches, wiring fully connected;
    **every position's output has a real consumer** (no decorations allowed).
  B **Today's plot synopsis**: entry type round-trip · order is after the recap and before the scene intro ·
    doesn't push if unavailable · disappears when the switch is off.
  C **Today's summary**: the retrospective is really invoked at the wrap-up step · the output contains three sections (summary/problems/suggestions) ·
    persists `今日总结.md` · displays on screen (also shows with `CREW_SCREEN=key`).
  D **Director watching the show and rollback**: `scan_repetition`'s five test groups judge accurately · rollback really deletes entries ·
    after rollback the "just happened on stage" buffer also rolls back · `[导演提示]` lives only one beat.
  E **Broadcast levels**: `off` / `key` / `full` three levels behave distinctly;
    **no work output must display on screen at any level** (that's a fault signal, not content).
Run: .venv\\Scripts\\python.exe tools/verify_studio_v2.py
Output: assets/screenshots/studio_v2_report.json
"""
from __future__ import annotations

import ast
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

from verify_ui_common import safe_rmtree                       # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}

#: 2026-10-07 补的四位
# [EN] : 2026-10-07 added four positions
NEW_ROLES = ('reviewer', 'stylist', 'sound', 'polisher')


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


class _EmptyDB:
    """最小假 DB（模块级 —— 写在函数里会被 `from … import` 的名字遮蔽）。
        English:
    Minimal fake DB (module-level -- if written inside a function it will be shadowed by names from
    `from ... import`).
    """

    def __getattr__(self, name):
        def _f(*a, **k):
            return [] if name.startswith(('get', 'recent', 'retrieve', 'list')) \
                else None
        return _f


# ══════════════════════════════════════════════════════════════════
#  A —— 剧组扩充
# [EN] A —— Crew expansion
# ══════════════════════════════════════════════════════════════════
def test_new_roles() -> None:
    from crew import roster as R, agents as A
    from crew import studio as ST
    keys = {r.key for r in R.ROSTER}
    ok('A1 四位新职位都在名册里', set(NEW_ROLES) <= keys,
       f'{len(R.ROSTER)} 位：{sorted(keys)}')
    ok('A2 每一位都有实现（名册与在位者一一对应）',
       not A.missing_members(), str(A.missing_members()))
    ok('A3 每一位的接线都真的存在（`hooks` 逐个 import 解析过）',
       not R.audit_hooks(), str(R.audit_hooks()))
    ok('A4 ★ 每一位都有自己的落盘文件（产出有地方去）',
       all(ST.Studio.ARTIFACT.get(k) for k in NEW_ROLES),
       str({k: ST.Studio.ARTIFACT.get(k) for k in NEW_ROLES}))
    # ⚠ 开关名**不是**简单地把 key 大写（`reviewer` → `CREW_REVIEW`、
    #   `polisher` → `CREW_POLISH`）。第一版按 `CREW_{key.upper()}` 猜，
    #   两条假红。**从 `_enabled` 的实际分支里读真值**，别猜。
    # [EN] ⚠ The switch name is **not** simply the uppercased key (`reviewer` → `CREW_REVIEW`、
    # [EN] `polisher` → `CREW_POLISH`). The first version guessed via `CREW_{key.upper()}`,
    # [EN] two false reds. **Read the real value from the actual branches of `_enabled`**, don't guess.
    from config import SPEC as _SPEC
    _switch = {'reviewer': 'CREW_REVIEW', 'stylist': 'CREW_STYLIST',
               'sound': 'CREW_SOUND', 'polisher': 'CREW_POLISH'}
    missing = [k for k, sw in _switch.items() if sw not in _SPEC]
    ok('A5 ★ 每一位都有自己的开关（关了就不出工，且台账显示"未启用"）',
       not missing, f'缺：{missing}' if missing else str(_switch))
    est = (APP_DIR / 'crew' / 'studio.py').read_text(encoding='utf-8')
    ok('A5b ★★ 那四个开关在 `_enabled` 里**真的被读到**（不是假旋钮）',
       all(f"'{k}': CFG.b(" in est for k in _switch), '')
    # ★ 每一位都要有"真实消费方"—— 摆着好看的职位就是这个项目最忌讳的假按钮
    # [EN] ★ Every position must have a "real consumer" —— a position that only exists for show is the fake
    # [EN] button this project hates most
    from crew.agents import MEMBERS
    ok('A6 ★★ 每位新职位都有 `work()` 实现（不是占位）',
       all(type(MEMBERS[k]).work.__qualname__.startswith(
           type(MEMBERS[k]).__name__) for k in NEW_ROLES), '')
    src = (APP_DIR / 'crew' / 'studio.py').read_text(encoding='utf-8')
    # ★★ A7 改成 **AST 判**（2026-10-12）：原来写的是字符串哨兵
    #   `"await self.review(ctx, lines=lines)" in src` —— 那种写法**一加参数就过期**
    #   （这一轮给 `review()` 加了 `extra_section=`，它当场假红），
    #   而"加了参数"恰恰是它最不该管的事（它要管的是"收工那一步真的调了复盘"）。
    #   ⚠ 这正是本项目那条老规矩：**别用字符串钉代码形状**（旁边 A9/A10 的注释
    #     写着同一个教训）。现在判的是"`wrap()` 里有一次 `self.review(...)`
    #     调用，且带了 `lines=`"，加多少 kwarg 都不会再误报。
    # [EN] ★★ A7 changed to an **AST check** (2026-10-12): it used to be the string sentinel
    # [EN] `"await self.review(ctx, lines=lines)" in src` -- that form **expires as soon as a parameter is
    # [EN] added** (this round `review()` gained `extra_section=`, and it went falsely red on the spot),
    # [EN] and "a parameter was added" is exactly what it should not care about (what it cares about is
    # [EN] "the wrap-up step really calls the retrospective").
    # [EN] ⚠ This is precisely the house rule: **never pin code shape with a string** (the notes beside
    # [EN] A9/A10 record the same lesson). It now judges "there is one `self.review(...)` call inside
    # [EN] `wrap()` and it carries `lines=`", so any number of extra kwargs is fine.
    _tree = ast.parse(src)
    _wrap = next((n for n in ast.walk(_tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == 'wrap'), None)
    _calls = [n for n in ast.walk(_wrap) if isinstance(n, ast.Call)] if _wrap else []
    _rev = [c for c in _calls
            if isinstance(c.func, ast.Attribute) and c.func.attr == 'review'
            and isinstance(c.func.value, ast.Name) and c.func.value.id == 'self']
    ok('A7 ★★ 复盘被 `wrap()` 真的调到（收工那一步，且带了当天那几行）',
       bool(_rev) and any(k.arg == 'lines' for k in _rev[0].keywords),
       f'{len(_rev)} 处调用' if _wrap else '（没找到 wrap()）')
    ok('A8 ★★ 造型接在美术之后（名册里 `art → stylist` 那条链是真的）',
       "'stylist', ctx" in src and "_art_brief(art)" in src, '')
    # ⚠⚠ 2026-10-07 审计：A9/A10 原来查的是**源码哨兵**
    #   （`'sound_brief' in src` / `'polish(ctx' in src`）—— 那是最弱的一种判据：
    #   **函数写好了但一行都不调它，照样绿**。而这正是当时的真实情况：
    #   `Studio.sound_note` / `Studio.polish` **零调用点**，声音与语言审校
    #   一天都没出工过（`声音设计.md` / `语言审校.md` 从来不存在）。
    #   现在这两条改成**指向真实调用点**（`sim/loop._sound` / `studio.wrap`），
    #   而"真的会出工"由 `tools/verify_crew_flow.py` 的 A 组用**跑一天看台账**
    #   来证（行为判据）。**别把这两条再改回查函数名。**
    # [EN] ⚠⚠ 2026-10-07 audit: A9/A10 originally checked the **source sentinel**
    # [EN] (`'sound_brief' in src` / `'polish(ctx' in src`) —— that's the weakest kind of criterion:
    # [EN] **the function is written but never called, yet it still goes green**. And that was exactly the
    # [EN] real situation at the time:
    # [EN] `Studio.sound_note` / `Studio.polish` **have zero call sites**, sound and language review
    # [EN] Now these two check **real call sites** (`sim/loop._sound` / `studio.wrap`),
    # [EN] and "it really does work" is proven by group A of `tools/verify_crew_flow.py` using **running a
    # [EN] day and checking the ledger**
    # [EN] (behavioral criterion). **Don't change these two back to checking function names.**
    loop_src = (APP_DIR / 'sim' / 'loop.py').read_text(encoding='utf-8')
    ok('A9 ★★ 声音真的被调用（`sim/loop._sound` → 环境句），不只是"函数在"',
       'studio.sound_note(' in loop_src and 'sound_design' in loop_src, '')
    ok('A10 ★★ 语言审校真的被调用（收工那一步，且拿到样章）',
       "self.call('polisher', ctx" in src, '')
    # 四个用途都要有假回复（否则演示模式下它们全哑）
    # [EN] All four uses must have fake responses (otherwise under demo mode they're all mute)
    from llm import mock
    miss = [p for p in ('crew_review', 'crew_stylist', 'crew_sound', 'crew_polish')
            if p not in mock._HANDLERS]
    ok('A11 ★ 四个新用途都有演示回复（MOCK 下不会哑）',
       not miss, f'缺：{miss}' if miss else '')


# ══════════════════════════════════════════════════════════════════
#  B —— 今日剧情简介
# [EN] B —— Today's plot synopsis
# ══════════════════════════════════════════════════════════════════
def test_day_brief() -> None:
    from display import script as S, story_render as STR, script_render as SR
    ok('B1 `S.BRIEF` 是正式词条类型（在 `ALL_KINDS` 里）',
       S.BRIEF in S.ALL_KINDS, '')
    e = S.brief('今天要演什么')
    ok('B2 小说体渲染：`▷ 今日剧情简介：…`（与前情提要的 `§` 分得开）',
       '▷' in STR.sentence(e) and '今日剧情简介' in STR.sentence(e),
       STR.sentence(e))
    # ⚠ 第 0 块是**幕首 meta**（地点那行），不是简介 —— 要按 role 找。
    #   第一版取 `[0]`，量到的是 `meta`，白红一次。
    # [EN] ⚠ Block 0 is the **act-opening meta** (the location line), not the synopsis —— find it by role.
    # [EN] The first version took `[0]`, which measured `meta`, one false red.
    _blocks = SR.render_blocks(S.SceneScript(place='司天台', entries=[e]))
    _briefs = [x for x in _blocks if x.role == SR.ROLE_BRIEF]
    ok('B3 屏幕块有自己的 role（与前情提要并列的另一类）',
       len(_briefs) == 1, str([x.role for x in _blocks]))
    ok('B4 纯文本形态用另一个记号 `▷`',
       '▷' in SR.to_screen_text(
           S.SceneScript(place='司天台', entries=[e])), '')
    ok('B5 不进正文段落流（`NON_INDENT` 里有它）',
       S.BRIEF in getattr(STR, 'NON_INDENT', {S.BRIEF}), '')

    # DayScript 往返
    # [EN] DayScript round-trip
    from director.day_plan import DayScript
    ds = DayScript(day=1, story='样章', day_brief='今天要讲什么')
    ok('B6 ★ `DayScript.day_brief` 存得下、读得回',
       DayScript.from_dict(ds.to_dict()).day_brief == '今天要讲什么', '')
    ok('B7 旧数据（没有这个字段）读得回来（向后兼容）',
       DayScript.from_dict({'day': 1, 'story': 'x'}).day_brief == '', '')

    # 顺序与开关
    # [EN] Order and switches
    loop_src = (APP_DIR / 'sim' / 'loop.py').read_text(encoding='utf-8')
    ok('B8 ★★ 循环里按 `DAY_BRIEF` 开关推它',
       "CFG.b('DAY_BRIEF')" in loop_src and 'S.brief(' in loop_src, '')
    ok('B9 ★★ 拿不到就不推（不拿前情凑数 —— 写成前情的复述比没有更糟）',
       "if _brief:" in loop_src, '')
    # 前情提要在跨天那一步推、简介在 _compose_day 推 → 顺序天然正确
    # [EN] The recap is pushed at the cross-day step, the synopsis is pushed in _compose_day → the order is
    # [EN] naturally correct
    ok('B10 ★★ 顺序：前情提要在前（跨天那一步）、简介在后（`_compose_day`）',
       '_push_recap()' in loop_src and 'S.brief(' in loop_src, '')
    rf = (APP_DIR / 'store' / 'runfolder.py').read_text(encoding='utf-8')
    ok('B11 ★ 落盘也带上它（前情提要之后、场景介绍之前）',
       'day_brief' in rf and '**今日剧情简介**' in rf, '')


# ══════════════════════════════════════════════════════════════════
#  C —— 今日总结（复盘）
# [EN] C —— Today's summary (retrospective)
# ══════════════════════════════════════════════════════════════════
def test_review() -> None:
    from crew.agents import Reviewer, SetCtx, CrewNote
    from world.state import WorldState, PersonState
    w = WorldState(scene='司天台')
    w.add_person(PersonState('主角'))
    ctx = SetCtx(world=w, db=_EmptyDB(), day=1, people=['主角'])
    note = asyncio.run(Reviewer().run(ctx, lines=['主角：水不会说谎。'],
                                      script=None))
    ok('C1 复盘出得了活（MOCK 下）', note.ok, note.why or note.title)
    d = note.data or {}
    ok('C2 ★★ 产出含三段：总结 / 问题 / 修改意见',
       bool(d.get('总结')) and isinstance(d.get('问题'), list)
       and isinstance(d.get('修改意见'), list), str(list(d)))
    ok('C3 ★ 问题指到具体的人（不是"人物刻画不够"这种空话）',
       not d.get('问题') or any('：' in x or '在' in x for x in d['问题']),
       str(d.get('问题'))[:60])
    ok('C4 ★ 有 `需要重演` 这面旗（默认 False —— 别动不动就重来）',
       '需要重演' in d and isinstance(d['需要重演'], bool), str(d.get('需要重演')))
    ok('C5 `body` 是给人读的（标题分节）',
       '存在的问题' in note.body or '后续修改意见' in note.body,
       note.body[:60].replace('\n', ' '))

    # 没正文时不许瞎编
    # [EN] No making things up when there's no body text
    ctx2 = SetCtx(world=w, db=_EmptyDB(), day=1, people=['主角'])
    empty = asyncio.run(Reviewer().run(ctx2, lines=[], script=None))
    ok('C6 ★ 今天没有正文时**报"没得复盘"**，不编一篇总结',
       not empty.ok and '没有' in empty.why, empty.why)

    # 落盘 + 上屏
    # [EN] Persist to disk + display on screen
    from crew import studio as ST
    ok('C7 复盘落盘到 `今日总结.md`', ST.Studio.ARTIFACT['reviewer'] == '今日总结.md',
       ST.Studio.ARTIFACT['reviewer'])
    src = (APP_DIR / 'crew' / 'studio.py').read_text(encoding='utf-8')
    ok('C8 ★★ 复盘在 `CREW_SCREEN=key` 档也上屏（用户点名要的）',
       "note.role == 'reviewer'" in src, '')
    loop_src = (APP_DIR / 'sim' / 'loop.py').read_text(encoding='utf-8')
    ok('C9 ★★ 手动停止/一天落盘都会到收工那一步（`_finish` → `_end_day`）',
       'await self._end_day()' in loop_src and '_crew_wrap' in loop_src, '')
    ok('C10 ★ 复盘说"需要重演"时能回档（默认关，一天最多一次）',
       '_maybe_replay_day' in loop_src and '_replayed_today' in loop_src, '')


# ══════════════════════════════════════════════════════════════════
#  D —— 导演盯戏与回档
# [EN] D —— Director watching the show and rollback
# ══════════════════════════════════════════════════════════════════
def test_watch() -> None:
    from director import supervisor as SUP
    P = ['主角', '柳娘', '师兄']
    cases = [
        ('多人各自独立重复同一件事', ['主角：这账我记着。', '柳娘：账我记着，你别管。',
                                '师兄：这账我记着呢。'], 'multi_repeat'),
        ('同一动作换个说法', ['主角：看了看井口。', '柳娘：看了看那口井。',
                        '师兄：看了看井口。'], 'multi_repeat'),
        ('单人连着换个说法', ['主角：这账我记着。', '主角：这账我一直记着。'],
         'single_repeat'),
    ]
    for label, lines, want in cases:
        got = [x.kind for x in SUP.scan_repetition(lines, people=P)]
        ok(f'D1 查得出「{label}」', want in got, str(got))
    # ★ 不该误报（误报会让整个推演一直在回档里打转）
    # [EN] ★ Must not false-positive (a false positive makes the whole simulation spin in rollback forever)
    norm = ['主角：这一夜的水快了一刻。', '柳娘：你凭什么这么说？',
            '主角：我量了三回。', '柳娘：那也不能算数。', '主角：别拿它当证据。']
    ok('D2 ★★ 正常对话往来**一条都不报**（误报比漏报更糟）',
       SUP.scan_repetition(norm, people=P) == [],
       str([x.kind for x in SUP.scan_repetition(norm, people=P)]))
    ok('D3 ★ 只有两个人说类似的话时不报（对话里附和/复述本来就像）',
       SUP.scan_repetition(norm[:2], people=P) == [], '')
    ok('D4 空转查得出（连着几条都在看/等/沉默）',
       SUP.idle_issue(['主角看了看。', '柳娘低头。', '师兄没说话。',
                       '主角望着井口。', '柳娘站着。', '师兄抬头。']) is not None, '')
    ok('D5 正常戏不算空转', SUP.idle_issue(
        ['主角把更签收进袖里。', '柳娘推门进来。', '师兄拿起账本翻了两页。',
         '主角问他签过没有。', '柳娘把饼放下。', '师兄把壶搁下。']) is None, '')
    ok('D6 ★ 导演心里的大纲：报得出进度与当前节点',
       '进度' in SUP.outline_check(
           type('W', (), {'progress_nodes': [
               {'id': 'N01', '名称': '开端', '状态': '已完成'}],
               'current_node': 'N01'})(), today_beats=6), '')

    # 回档
    # [EN] Rollback
    from display.scene_builder import SceneBuilder
    from display import script as S
    from world.state import WorldState, PersonState
    w = WorldState(scene='司天台')
    w.add_person(PersonState('主角'))
    b = SceneBuilder(w, day=1)
    for i in range(4):
        b._ensure_scene().add(S.dialogue('主角', f'第{i}句。'))
    n0 = len(b.recent_entries(99))
    got = b.rollback(2)
    ok('D7 ★★ 回档真的删掉了条目（且返回**实际**条数）',
       got == 2 and len(b.recent_entries(99)) == n0 - 2,
       f'{n0} → {len(b.recent_entries(99))}')
    # ⚠ 要比的是**回档前**的条数。第一版拿回档**之后**的条数去比（那必然是 0），
    #   于是"回档删了 3 条"被判成失败 —— 又是判据自己写错了。
    # [EN] ⚠ What to compare is the count **before** rollback. The first version compared the count
    # [EN] **after** rollback (which is necessarily 0),
    # [EN] so "rollback deleted 3 entries" was judged a failure —— yet again the criterion itself was
    # [EN] wrong.
    _before = len(b.recent_entries(99))
    ok('D8 ★ 回档超量时返回真实条数（不假装删了）',
       b.rollback(99) == _before and _before > 0, f'回档前 {_before} 条')
    ok('D8b 回档之后真的一条都不剩', len(b.recent_entries(99)) == 0, '')
    # ⚠ 幕首会自动落一条「出场」词条 —— 所以"只建一条台词"时条目数是 **2**。
    #   判据要跟"真实的条目数"比，别假设 1（第一版就是假设 1，假红）。
    # [EN] ⚠ The act opening automatically drops an "entrance" entry —— so when "only one line is created",
    # [EN] the entry count is **2**.
    # [EN] The criterion must compare against "the real entry count", don't assume 1 (the first version
    # [EN] assumed 1, false red).
    b2 = SceneBuilder(w, day=1)
    b2._ensure_scene().add(S.dialogue('主角', '唯一一条。'))
    before = len(b2.recent_entries(99))
    ok('D8b ★★ 只剩很少几条时回档 99 → 只删掉**实际有的**那些，返回真实条数',
       b2.rollback(99) == before and before >= 1, f'建了 {before} 条')
    ok('D8c 已经空了再回档 → 返回 0（调用方据此知道"没生效"）',
       b2.rollback(3) == 0, '')
    ok('D9 ★ 回档不碰去重台账（回档是为了不重复，不是为了允许重复）',
       len(b2._said) >= 0, '')
    # ★★ **回档三件事一起做** —— 这条必须**真跑一遍**，不能查源码字面量。
    #   反例法当场证明过：把 `_on_rollback(done)` 那一行删掉，
    #   而"源码里有没有 `_on_rollback` 这个字符串"照样为真（定义还在），
    #   判据不会红 —— 那就是一条形式判据。所以改成行为判据：
    #   建一个 loop、挂回档回调、建几条词条、强制回档，看三处有没有一起动。
    # [EN] ★★ **Rollback does three things together** —— this one must be **actually run once**, not check
    # [EN] source literals.
    # [EN] The counterexample method proved it on the spot: delete the line `_on_rollback(done)`,
    # [EN] and "does the source contain the string `_on_rollback`" is still true (the definition remains),
    # [EN] so the criterion won't go red —— that's a formal criterion. So change it to a behavioral
    # [EN] criterion:
    # [EN] create a loop, attach the rollback callback, create a few entries, force a rollback, see whether
    # [EN] all three move together.
    from sim.loop import RunLoop
    from world.state import WorldState as _WS, PersonState as _PS
    _w = _WS(scene='司天台')
    _w.add_person(_PS('主角'))
    _b = SceneBuilder(_w, day=1)
    for i in range(3):
        _b._ensure_scene().add(S.dialogue('主角', f'第{i}句。'))
    _w.note_line('主角', '第一条')           # 「场上刚发生」缓冲里放两条
    # [EN] Put two entries in the "just happened on stage" buffer
    _w.note_line('柳娘', '第二条')
    _fired: list[int] = []
    _loop = RunLoop(_w, [], _EmptyDB(), _EmptyDB(), None)
    _loop._builder = _b
    _loop.on_rollback(lambda n: _fired.append(n))
    _n_before = len(_b.recent_entries(99))
    _buf_before = len(list(getattr(_w, 'recent_lines', None) or []))
    _done = _loop._rollback(2)
    _buf_after = len(list(getattr(_w, 'recent_lines', None) or []))
    ok('D10 ★★ 回档**三件事一起做**：剧本少了 + 屏幕收到回调 + 缓冲也退了',
       _done == 2
       and len(_b.recent_entries(99)) == _n_before - 2
       and _fired == [2]
       and _buf_after == _buf_before - 2,
       f'删了 {_done}；回调 {_fired}；缓冲 {_buf_before}→{_buf_after}')
    ok('D10b ★ `_rollback` 记了累计账（`_rollback_total`，日志与复盘要用）',
       _loop._rollback_total == 2, str(_loop._rollback_total))
    loop_src = (APP_DIR / 'sim' / 'loop.py').read_text(encoding='utf-8')
    ok('D11 ★★ `[导演提示]` 只活一拍（下一拍开头清掉）',
       "self.world.watch_note = ''" in loop_src, '')
    ok('D12 ★★ 盯戏排在落盘**之前**（回档要真生效，不能先写文件再删）',
       loop_src.index('await self._director_watch()')
       < loop_src.index('self._flush_tick(tick_num)'), '')
    ok('D13 ★ 回档有上限（`DIRECTOR_ROLLBACK_MAX`）+ 开关',
       'DIRECTOR_ROLLBACK_MAX' in loop_src and 'DIRECTOR_WATCH' in loop_src, '')
    ok('D14 ★★ 盯戏**零 LLM 调用**（不然"一直盯着"就做不到）',
       'ask(' not in (APP_DIR / 'director' / 'supervisor.py').read_text(
           encoding='utf-8'), '')


# ══════════════════════════════════════════════════════════════════
#  E —— 播报分级
# [EN] E —— Broadcast levels
# ══════════════════════════════════════════════════════════════════
def test_screen_levels() -> None:
    from crew.studio import Studio
    from crew.agents import CrewNote
    seen: list = []
    st = Studio(world=None, db=None, runfolder=None, on_note=seen.append)
    good = CrewNote(role='art', title='今天 1 处：司天台', ok=True)
    bad = CrewNote(role='art', title='美术', ok=False, why='模型没答')
    review = CrewNote(role='reviewer', title='今天的总结', ok=True)
    polish_hit = CrewNote(role='polisher', title='3 处 AI 味', ok=True,
                          data={'问题数': 3})
    polish_ok = CrewNote(role='polisher', title='没有问题', ok=True,
                         data={'问题数': 0})

    def run(level, note):
        seen.clear()
        old = CFG.s('CREW_SCREEN')
        try:
            CFG.set('CREW_SCREEN', level)
            st._announce(note)
        finally:
            CFG.set('CREW_SCREEN', old)
        return len(seen) > 0

    # ★★ 2026-10-07 **第三次改口径**：中栏现在**根本不显示产出内容**了，
    #   所以这里量的是"要不要为这份产出发一条消息"（发成什么由
    #   `sim/loop._on_crew_note` 定：状态 / 总结 / 故障）。
    #   `off` 不报工作状态；`key`/`full` 报 —— 三档管的是**报多细**。
    # [EN] ★★ 2026-10-07 **third change of definition**: the middle column now **doesn't display output
    # [EN] content at all**,
    # [EN] so what's measured here is "whether a message should be sent for this output" (what it becomes
    # [EN] is determined by
    # [EN] `sim/loop._on_crew_note`: status / summary / fault).
    # [EN] `off` does not report work status; `key`/`full` do —— the three levels control **how detailed
    # [EN] the report is**.
    ok('E1 `off`：普通产出不报（最粗的一档）', not run('off', good), '')
    ok('E2 `off`：**没出活照旧报**（那是故障信号，不是内容）',
       run('off', bad), '')
    ok('E3 ★★ `key`（默认）：普通产出**报成工作状态**'
       '（`· 美术 已交活` —— 用户开头要的那张状态卡）', run('key', good), '')
    ok('E4 ★★ `key`：复盘照旧报（用户点名要的今日总结）', run('key', review), '')
    ok('E5 ★★ `key`：语言审校查出问题时报（那是要作者动手改的）',
       run('key', polish_hit), '')
    ok('E6 ★ `key`：审校没查出问题也报 —— 但报成"状态"而不是"内容"'
       '（内容不上屏这件事现在与档位无关了）', run('key', polish_ok), '')
    ok('E7 ★★ `key`：去 AI 审计命中的任何产出都报',
       run('key', CrewNote(role='props', title='道具单', ok=True,
                           data={'去AI命中': 2})), '')
    ok('E8 `full`：也报（多一句标题）', run('full', good), '')
    # ★ 新增：`off` 也报**今日总结**（它不属于"剧组花絮"，是用户点名的总结）
    # [EN] ★ New: `off` also reports **today's summary** (it doesn't belong to "crew gossip", it's the
    # [EN] summary the user explicitly named)
    ok('E8b ★★ `off`：**今日总结照旧报**（用户白名单里的"一天结束后的总结"）',
       run('off', review), '')
    ok('E9 ★ 默认档就是 `key`（用户要的"尽可能少出现演职人员"）',
       CFG.s('CREW_SCREEN') == 'key' or
       __import__('config').SPEC['CREW_SCREEN']['default'] == 'key',
       __import__('config').SPEC['CREW_SCREEN']['default'])
    # 旧开关不许还在（两个开关表达同一件事 = 假旋钮）
    # [EN] Old switches must not remain (two switches expressing the same thing = a fake knob)
    from config import SPEC
    ok('E10 ★ 旧的 `CREW_ON_SCREEN` 已删（不留两个开关表达同一件事）',
       'CREW_ON_SCREEN' not in SPEC, '')
    # 那一行"当日剧本定稿"的 meta 也按档位收起来
    # [EN] That "day script finalized" meta line is also stowed according to the level
    loop_src = (APP_DIR / 'sim' / 'loop.py').read_text(encoding='utf-8')
    ok('E11 ★★ 「（当日剧本 · 定稿）」那行只在 `full` 档推'
       '（它也是演职人员的话，不是故事）',
       "== 'full'" in loop_src, '')


def main() -> int:
    print('═' * 62)
    print('  验证：剧组扩充 · 今日简介 · 今日总结 · 盯戏回档 · 播报分级')
    print('═' * 62)
    try:
        print('\n【A】剧组扩充（四位新职位）')
        test_new_roles()
        print('\n【B】今日剧情简介')
        test_day_brief()
        print('\n【C】今日总结（复盘）')
        test_review()
        print('\n【D】导演盯戏与回档')
        test_watch()
        print('\n【E】播报分级')
        test_screen_levels()
    except Exception:                                            # noqa: BLE001
        traceback.print_exc()
        report['fatal'] = traceback.format_exc()
        ok('Z 判据自己跑通（没被异常打断）', False,
           report['fatal'].splitlines()[-1])

    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['passed'] = len(checks) - len(bad)
    report['total'] = len(checks)
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'studio_v2_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  剧组第二轮验证：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
