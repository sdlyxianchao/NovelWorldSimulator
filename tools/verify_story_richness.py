# -*- coding: utf-8 -*-
"""判据：**推演产出要像小说，不能只有对话**（2026-10-14 用户点名）。

用户原话（verbatim）：
    「我看现在的推演结果 是大量的对话 正常小说的话应该是有任务的各种动作
      大量的环境 故事情节 人物做的事情 心理活动 等等不同的内容的（可能不全，
      你补充小说的其他要素） 而不应该只有对话 你按照这个方向优化一下
      整个流程 以及推演的内容和最终的输出」

★ 调研出来的**四层原因**（本判据按这四层各钉一条）：
    ① **输入层**：`[刚才]`（`world.recent_text`）里原来只有台词 ——
       因为 `_note_stage_line` 只记 `speak` / `move`，
       `interact` / `emote`（在场的人都看得见）**不记** ⇒
       每个人下一拍都在"接别人的话"，没人接别人的**动作**；
    ② **决策层**：`Action` **没有地方放动作描写** ⇒
       `emote` / `interact` / `move` 无论模型多想写，都只能落成
       `_action_text` / `_verb_desc` 的**骨架**（`神色变了变` / `转向X`）；
       提示词也没要求"只给一句台词是最差的一拍"；
    ③ **产出层**：`_entries_for` 里 `inner`（内心）**只在 `verb=='think'` 时**
       才被用 ⇒ 说话/做事时给的"内心"**被整段丢掉** ⇒ 心声几乎不见；
       环境**只在"全场都没动"时**才写 ⇒ 有动静就是"一屏台词"；
    ④ **放大层**：`Agent.talk()` **无条件产满** `DIALOGUE_MAX_TURNS` 句
       （调用方不传 `max_turns` ⇒ 取 8 句），说不出话也要塞 8 句"沉默了"。

★ 每一节都配了**反例**（成对判据）：例如"动作要带描写"之外，
  还要判"没给描写时**不编造**、照旧落骨架"。

产出：assets/screenshots/story_richness_report.json
用法：.venv/Scripts/python.exe tools/verify_story_richness.py

English:
Criterion: **the deduction output must read like a novel, not only dialogue** (named by the user
on 2026-10-14).

User's words (verbatim):
    "I see the deduction output is mostly dialogue; a normal novel should have the characters'
    various actions, **a lot of environment**, plot, things the characters do, inner activity and
    so on (possibly incomplete, you fill in the other elements of a novel) ... it should not be
    only dialogue. Optimize the whole flow along this direction, plus the deduction content and the
    final output."

★ The **four-layer cause** found by investigation (one check per layer here):
    ① **Input layer**: `[刚才]` (`world.recent_text`) contained only dialogue -- because
       `_note_stage_line` only recorded `speak` / `move`, while `interact` / `emote` (visible to
       everyone on stage) were **not recorded** => on the next beat everyone was "picking up the
       other's words" and nobody picked up anyone's **actions**;
    ② **Decision layer**: `Action` had **nowhere to put an action description** => `emote` /
       `interact` / `move` could only become the **skeleton** of `_action_text` / `_verb_desc`
       (`expression shifted` / `turns toward X`) no matter what the model wanted; and the prompt
       never said "only giving one line of dialogue is the worst beat";
    ③ **Production layer**: inside `_entries_for`, `inner` was used **only when `verb=='think'`** =>
       the "inner" given while speaking/acting was **dropped wholesale** => inner voice was almost
       never seen; and environment was written **only when "nobody moved at all"** => any movement
       meant "a screen of dialogue";
    ④ **Amplification layer**: `Agent.talk()` **unconditionally produced the full**
       `DIALOGUE_MAX_TURNS` count (the caller passes no `max_turns` => 8 lines), stuffing 8 "fell
       silent" lines even when nothing could be said.

★ Every section has **paired** checks: e.g. besides "actions must carry a description", it also
  checks "when no description is given, **nothing is fabricated** and the skeleton is used as
  before".

Output: assets/screenshots/story_richness_report.json
Usage: .venv/Scripts/python.exe tools/verify_story_richness.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault('NWS_LANG', 'zh')
from config import CFG, SPEC                                  # noqa: E402
CFG.set('MOCK_LLM', 'true')

from agent.core import Action                                # noqa: E402
from display import script as S                              # noqa: E402
from display.scene_builder import SceneBuilder               # noqa: E402
from sim.loop import RunLoop, _verb_desc                     # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:300]})
    if not cond:
        report['ok'] = False
    print(('  ✓ ' if cond else '  ✗ ') + name
          + (f'  | {str(detail)[:120]}' if detail and not cond else ''), flush=True)
    return bool(cond)


# ══════════════════════════════════════════════════════════════
#  假对象（不碰真世界、不起窗口）
# ══════════════════════════════════════════════════════════════
# [EN] ═══ Fake objects (no real world, no window) ═══
class _Clock:
    """假的时钟（`begin_scene` 会读 `shichen` / `hhmm()`）。"""

    def segment(self) -> str:
        return '上午'

    def shichen(self) -> str:
        return '午时'

    def hhmm(self) -> str:
        return '12:00'


class _World:
    scene = '城东渡口'
    weather = '晴'
    game_day = 1
    clock = _Clock()
    sound_design = ''
    on_stage: list = []
    sound = ''

    def on_stage_names(self) -> list:
        return []


class _Agent:
    name = '主角'
    ps = None

    def __init__(self, name: str = '主角') -> None:
        self.name = name


def _b():
    return SceneBuilder(_World(), day=1)


# ══════════════════════════════════════════════════════════════
#  A. 动作要**有描写**（用户：「人物做的事情」）
# ══════════════════════════════════════════════════════════════
# [EN] ═══ A. Actions must **carry a description** (user: "things the characters do") ═══
def section_a() -> None:
    print('\n── A 动作有描写（不是骨架）──')
    b = _b()
    _D = '他把茶碗端起来又放下，指节发白'

    # A1 · `_action_text`（剧本模式那条路）
    got = b._action_text(Action(verb='emote', detail=_D))
    ok('A1 ★★★ 给了「细节」⇒ 动作就用**那句描写**（不再落成「神色变了变」）',
       got == _D, f'实际={got!r}')
    # A2 · 没给 ⇒ 照旧落骨架（**成对**：别为了"有描写"就编一句出来）
    got2 = b._action_text(Action(verb='emote'))
    ok('A2 ★★ 没给「细节」⇒ **照旧落骨架**（`emote` = 「神色变了变」，不编造）',
       got2 == '神色变了变', f'实际={got2!r}')
    # A3 · `_verb_desc`（prose 模式那条路）—— **两处都要改**，否则换个模式描写就没了
    got3 = _verb_desc(Action(verb='interact', target='阿福', detail=_D))
    ok('A3 ★★★ prose 模式那条路（`_verb_desc`）**同样**用「细节」'
       '（两处都改，否则"换个运行模式描写就没了"）',
       got3 == _D, f'实际={got3!r}')
    got4 = _verb_desc(Action(verb='interact', target='阿福'))
    ok('A4 ★★ prose 骨架仍在（`interact` 无细节 = 「和阿福互动」）',
       got4 == '和阿福互动', f'实际={got4!r}')

    # A5 · 走完整条产出链：`_entries_for` 产出的词条正文就是那句描写
    ents = b._entries_for(_Agent(), Action(verb='emote', detail=_D), 'public', '城东渡口')
    ok('A5 ★★★ 从 `_entries_for` 出来就是 `ACTION` 词条，正文 = 那句描写',
       len(ents) == 1 and ents[0].kind == S.ACTION and ents[0].text == _D,
       f'{[(e.kind, e.text[:26]) for e in ents]}')


# ══════════════════════════════════════════════════════════════
#  B. 心理活动（用户：「心理活动」）—— 任何动作都能带
# ══════════════════════════════════════════════════════════════
# [EN] ═══ B. Inner activity (user: "inner activity") -- any action can carry it ═══
def section_b() -> None:
    print('\n── B 心理活动：任何动作都能带心声 ──')
    b = _b()
    _I = '他到底想查什么'

    # B1 · 说话 + 内心 ⇒ 台词 + 心声（**这是改动的核心**：以前整段丢掉）
    ents = b._entries_for(_Agent(), Action(verb='speak', dialogue='我不接。',
                                           inner_thought=_I),
                          'public', '城东渡口')
    kinds = [e.kind for e in ents]
    ok('B1 ★★★ **说话也能带心声**（`speak` + `内心` ⇒ DIALOGUE + ASIDE）'
       '—— 改之前 `inner` 只在 `verb==think` 时才用，说话时给的内心被整段丢掉',
       kinds == [S.DIALOGUE, S.ASIDE], f'{kinds}')

    # B2 · 做事 + 内心 ⇒ 动作 + 心声
    ents2 = b._entries_for(_Agent(), Action(verb='emote', detail='把碗推远了一点',
                                            inner_thought=_I),
                           'public', '城东渡口')
    kinds2 = [e.kind for e in ents2]
    ok('B2 ★★★ **做事也能带心声**（`emote` + `内心` ⇒ ACTION + ASIDE）',
       kinds2 == [S.ACTION, S.ASIDE], f'{kinds2}')

    # B3 · 顺序：动作在前、心声在后（反了因果就是倒的）
    ok('B3 ★★ 顺序是**动作在前、心声在后**（反了读者会先看到"他想…"再看到"他做了…"）',
       kinds2 and kinds2[0] == S.ACTION and kinds2[-1] == S.ASIDE, f'{kinds2}')

    # B4 · `think` 仍然只产心声（老行为没被改坏）
    ents3 = b._entries_for(_Agent(), Action(verb='think', inner_thought=_I),
                           'public', '城东渡口')
    ok('B4 ★★ `think` + 内心 ⇒ 只产一条 ASIDE（老行为原样保留）',
       [e.kind for e in ents3] == [S.ASIDE], f'{[e.kind for e in ents3]}')

    # B5 · 成对：没给内心就**不许凭空造**一条心声
    ents4 = b._entries_for(_Agent(), Action(verb='speak', dialogue='嗯。'),
                           'public', '城东渡口')
    ok('B5 ★★ 成对：**没给内心就不产心声**（不凭空编一句"他心里想…"）',
       [e.kind for e in ents4] == [S.DIALOGUE], f'{[e.kind for e in ents4]}')
    # ⚠ B6（"心声不进场上缓冲"）**刻意不在这里做源码串检查** ——
    #   那违反本项目纪律（"别用源码含字符串当判据"：注释里提到 `ASIDE`
    #   也会命中，实测就是这么假红的）。这件事由 **D3 的行为判**钉住
    #   （`think` 传进 `_note_stage_line` 之后，缓冲里一行都不能多）。
    # [EN] ⚠ B6 ("inner voice must not enter the on-stage buffer") is **deliberately not a source
    # [EN] string check** -- that violates this project's discipline ("never use 'the source
    # [EN] contains a string' as a criterion": a mention of `ASIDE` in a comment would hit too, which
    # [EN] is exactly how it falsely reddened in practice). That is pinned by the **behavioral check
    # [EN] D3** instead (after passing `think` into `_note_stage_line`, not a single row may be
    # [EN] added to the buffer).


# ══════════════════════════════════════════════════════════════
#  C. 环境（用户：「大量的环境」）
# ══════════════════════════════════════════════════════════════
# [EN] ═══ C. Environment (user: "a lot of environment") ═══
def section_c() -> None:
    print('\n── C 环境：与"有没有人在动"无关 ──')
    b = _b()
    # ⚠ `begin_scene()` **不收 place**（场景从 `world` 取）—— 判据早先传了
    #   `place=` 当场 TypeError。这类"判据自己崩了"要和"判据变红"分开。
    # [EN] ⚠ `begin_scene()` takes **no place** (the scene comes from `world`) -- the criterion
    # [EN] passed `place=` earlier and hit a TypeError on the spot. "The criterion itself crashed"
    # [EN] must be kept apart from "the criterion went red".
    b.begin_scene()
    # ⚠ **先给这一场一点内容**：`observe_ambient` / `observe_quiet` 都有一条
    #   护栏 —— "这一场还没有内容"（只有幕首的 `SCENE` / `NOTE`）时**不写环境**。
    #   那是产品设计（一场戏还没开演，先别急着写雨声），不是 bug。
    #   判据要量的是"有动静时也能有环境"，所以这里得先真的演一点。
    # [EN] ⚠ **Give the scene some content first**: both `observe_ambient` and `observe_quiet`
    # [EN] have a guardrail -- when "this scene has no content yet" (only the opening
    # [EN] `SCENE` / `NOTE`), they **do not write environment**. That is by design (the scene has not
    # [EN] started; don't rush to write rain sounds), not a bug. What this criterion measures is
    # [EN] "environment exists even when something is happening", so something must actually happen.
    b._ensure_scene().add(S.action('主角', '把账本翻到昨夜那一页'))
    SCRIPT_AMBIENT = CFG.b('SCRIPT_AMBIENT')
    try:
        CFG.set('SCRIPT_AMBIENT', 'true')
        n0 = len([e for e in b._ensure_scene().entries if e.kind == S.AMBIENT])
        b.observe_ambient()
        n1 = len([e for e in b._ensure_scene().entries if e.kind == S.AMBIENT])
        ok('C1 ★★★ `observe_ambient()` **真的补了一条环境**（`AMBIENT`）'
           '—— 这是"有动静时也能有环境"的那条新通路',
           n1 > n0, f'{n0} → {n1}')
        # C2 · 连着调不刷屏（上一条已是环境就跳过）
        b.observe_ambient()
        n2 = len([e for e in b._ensure_scene().entries if e.kind == S.AMBIENT])
        ok('C2 ★★ 连着调**不刷屏**（上一条已经是 `AMBIENT` ⇒ 跳过）',
           n2 == n1, f'{n1} → {n2}')
        # C3 · 它**不产 `BEAT`**（有人做事时写"片刻无话"是错的）
        n_beat = len([e for e in b._ensure_scene().entries if e.kind == S.BEAT])
        ok('C3 ★★ `observe_ambient()` **不写「片刻无话」**'
           '（那是空场专属的；有人正在做事时写它是错的）',
           n_beat == 0, f'BEAT {n_beat} 条')
        # C4 · 关得掉
        CFG.set('SCRIPT_AMBIENT', 'false')
        before = len(b._ensure_scene().entries)
        b.observe_ambient()
        ok('C4 ★★ `SCRIPT_AMBIENT=false` ⇒ **一句都不产**（用户要能自己关）',
           len(b._ensure_scene().entries) == before,
           f'{before} → {len(b._ensure_scene().entries)}')
    finally:
        CFG.set('SCRIPT_AMBIENT', 'true' if SCRIPT_AMBIENT else 'false')

    # C5 · 节流器：按**故事分钟**，且能关
    spec = SPEC.get('AMBIENT_MINUTES')
    ok('C5 ★★ 新旋钮 `AMBIENT_MINUTES` 在 SPEC 里，而且**能设 0 关掉**'
       '（用户要能自己调密度）',
       spec is not None and int(spec.get('min', -1)) == 0,
       str(spec))

    loop = RunLoop.__new__(RunLoop)
    loop._game_min = 100.0
    loop._last_ambient_min = -10 ** 9
    calls: list = []

    class _B:
        def observe_ambient(self) -> None:
            calls.append(1)

    loop._ensure_builder = lambda: _B()
    CFG.set('AMBIENT_MINUTES', '5')
    loop._maybe_ambient()
    ok('C6 ★★★ 到点就补一次（故事分钟够 `AMBIENT_MINUTES`）', len(calls) == 1,
       f'{len(calls)} 次')
    loop._game_min = 101.0
    loop._maybe_ambient()
    ok('C7 ★★★ 没到点**不再补**（按故事分钟节流，不是按拍数 —— 否则'
       '"今天拍得多"会变成"今天环境多"，那是假密度）',
       len(calls) == 1, f'{len(calls)} 次（期望 1）')
    loop._game_min = 200.0
    loop._maybe_ambient()
    ok('C8 ★★ 又到点 ⇒ 再补一次', len(calls) == 2, f'{len(calls)} 次')
    CFG.set('AMBIENT_MINUTES', '0')
    loop._game_min = 999.0
    loop._maybe_ambient()
    ok('C9 ★★ 设成 0 ⇒ **整条通路关掉**（回到老行为）', len(calls) == 2,
       f'{len(calls)} 次（期望仍是 2）')
    CFG.set('AMBIENT_MINUTES', '1')


# ══════════════════════════════════════════════════════════════
#  D. 输入层：看得见的动作要进「场上刚发生」
# ══════════════════════════════════════════════════════════════
# [EN] ═══ D. Input layer: visible actions must enter "just happened on stage" ═══
def section_d() -> None:
    print('\n── D 输入层：动作进「刚才」，不再只有台词 ──')
    loop = RunLoop.__new__(RunLoop)
    rows: list = []

    class _W:
        def note_line(self, who, text, **kw) -> None:
            rows.append((who, text, kw.get('kind')))

    loop.world = _W()
    loop._warn_once = lambda *a, **k: None

    loop._note_stage_line(_Agent('主角'),
                          Action(verb='emote', detail='指节发白'))
    ok('D1 ★★★ `emote`（在场的人都看得见）**进了「刚才」**'
       '—— 改之前只记 speak / move，`emote` / `interact` 都不记，'
       '于是下一拍人人只接别人的**话**，没人接别人的**动作**',
       len(rows) == 1 and rows[-1][2] == 'act' and rows[-1][1] == '指节发白',
       f'{rows}')

    loop._note_stage_line(_Agent('柳氏'), Action(verb='interact', target='阿福'))
    ok('D2 ★★★ `interact` 也进（跟谁打交道，别人看得见）',
       len(rows) == 2 and rows[-1][2] == 'act', f'{rows}')

    n = len(rows)
    loop._note_stage_line(_Agent('阿福'), Action(verb='wait', target=''))
    loop._note_stage_line(_Agent('阿福'), Action(verb='think',
                                                inner_thought='他在算什么'))
    ok('D3 ★★★ 成对：`wait`（干等）与 `think`（心声）**都不进**'
       '（别人看不出来；心声进去更是人设崩）',
       len(rows) == n, f'{n} → {len(rows)}')

    n2 = len(rows)
    loop._note_stage_line(_Agent('阿福'), Action(verb='move', target=''))
    ok('D4 ★★ 无对象、也无「细节」的 `move` **不记**（否则得到半句「去了」）',
       len(rows) == n2, f'{n2} → {len(rows)}')

    # D5 · 台词走的是**另一条**（`spoken=True` 才记；其余由 `_note_entry` 从真词条记）
    loop._note_stage_line(_Agent('主角'), Action(verb='speak', dialogue='我不接。'))
    ok('D5 ★★★ 成对：`speak` 且 `spoken=False` **不在这里记**'
       '（台词由 `_note_entry` 从**真进剧本的词条**记，免得记到被去重滤掉的句子）',
       len(rows) == n2, f'{n2} → {len(rows)}')
    loop._note_stage_line(_Agent('主角'), Action(verb='speak', dialogue='我不接。'),
                          spoken=True)
    ok('D6 ★★ 领说者（`spoken=True`）那句**照旧记**（老行为没改坏）',
       len(rows) == n2 + 1 and rows[-1][2] == 'speak', f'{rows[-1:]}')


# ══════════════════════════════════════════════════════════════
#  E. 放大层：对话不再硬凑满轮数
# ══════════════════════════════════════════════════════════════
# [EN] ═══ E. Amplification: dialogue no longer padded to full turns ═══
def section_e() -> None:
    print('\n── E 对话不再硬凑满轮数 ──')
    spec = SPEC.get('DIALOGUE_MAX_TURNS')
    ok('E1 ★★★ `DIALOGUE_MAX_TURNS` 的默认值 ≤ 4（原来 8）'
       '—— `talk()` 每触发一次就产这么多句台词，是"对话刷屏"的最大来源',
       spec is not None and int(spec.get('default', 99)) <= 4, str(spec))

    # E2 · 说不出话就收尾（行为判：让 LLM 返回空）
    from llm import router as _R
    real = _R.llm.chat
    calls = {'n': 0}

    async def _empty(*a, **kw):
        calls['n'] += 1
        return ''

    class _P:
        name = '阿福'
        is_active = staticmethod(lambda: True)

    class _W2:
        scene = '城东渡口'
        clock = _Clock()
        sound_design = ''

        def get_person(self, n):
            return _P()

        def clock_display(self) -> str:
            return '第1天 午时'

        def world_prefix(self) -> str:
            return ''

    from agent.core import Agent
    class _PS:
        name = '主角'

    ag = Agent.__new__(Agent)
    # ⚠ `Agent.name` 是 **property**（`return self.ps.name`，没有 setter）——
    #   早先直接 `ag.name = …` 当场 AttributeError。给它一个假的 `ps`。
    # [EN] ⚠ `Agent.name` is a **property** (`return self.ps.name`, no setter) -- assigning
    # [EN] `ag.name = ...` earlier raised AttributeError. Give it a fake `ps`.
    ag.ps = _PS()
    ag.world = _W2()
    ag._persona_prompt = lambda: ''
    ag._other_persona_prompt = lambda ps: ''
    ag._rules_line = lambda: ''
    ag._add_memory = lambda *a, **k: None
    _R.llm.chat = _empty
    try:
        CFG.set('DIALOGUE_MAX_TURNS', '8')       # 就算配成 8
        lines = asyncio.run(ag.talk('阿福', topic='问路'))
    finally:
        _R.llm.chat = real
    ok('E2 ★★★ 模型**一句都答不出来** ⇒ 对话立刻收尾（只留一句「沉默了」），'
       '**不再硬凑 8 句**',
       len(lines) == 1 and calls['n'] == 1, f'{len(lines)} 句 / LLM 调了 {calls["n"]} 次')

    # E3 · 成对：句子正常时仍然按轮数产（别把功能改没了）
    async def _line(*a, **kw):
        return '我知道了。'

    _R.llm.chat = _line
    try:
        CFG.set('DIALOGUE_MAX_TURNS', '4')
        lines2 = asyncio.run(ag.talk('阿福', topic='问路'))
    finally:
        _R.llm.chat = real
    ok('E3 ★★ 成对：句子正常时**照旧按轮数产**（4 句，功能没被改没）',
       len(lines2) == 4, f'{len(lines2)} 句')


# ══════════════════════════════════════════════════════════════
#  F. 提示词（两份！）—— 用户诉求的"总闸"
# ══════════════════════════════════════════════════════════════
# [EN] ═══ F. Prompts (**two copies!**) -- the "master switch" for this request ═══
def section_f() -> None:
    print('\n── F 提示词：两份都要改 ──')
    # 提示词可以按名字替换模块作用域里的常量（`catalog.PROMPTS.set`）→
    # 这里统计"模块作用域"的引用数 + "函数体内"的引用数，两半都要钉
    # （函数体里的那份才是**真的生效**那半）。
    # [EN] Prompt constants at module scope are aliased to locals on import. What we assert is
    # [EN] *module-scope* references at each of: time / fade / postcondition; the loop body ends
    # [EN] with while from (i) for each identifier.
    from util import prompts as P
    text, src = P.template('agent_decide_tail', '')
    # ★ 判的是 **JSON 那一行里有没有 `"细节"` 这个字段** ——
    #   不是"整段文本里出现过『细节』两个字"。
    #   ⚠ 第一版写的就是后者，结果**变异"删掉 JSON 里的细节字段"照样绿**
    #     （说明段落里反复提到「细节」二字）⇒ 反例法实测抓出来的假绿。
    #     这与本项目那条纪律同源：判**本体**，不判"字符串出现过"。
    # [EN] ★ What is checked is **whether the JSON line carries the `"细节"` field** -- not "the
    # [EN] whole text mentions 『细节』 somewhere".
    # [EN] ⚠ The first version did the latter, and the mutation "delete the detail field from the
    # [EN] JSON" **stayed green** (the explanatory paragraphs mention 「细节」 repeatedly) => a false
    # [EN] green caught by the counterexample method. Same root as the project rule: judge the
    # [EN] **thing itself**, not "a string appears".
    _json_line = next((ln.strip() for ln in text.split('\n') if '"动作"' in ln), '')
    ok('F1 ★★★ 生效的那份「人物决策」提示词的 **JSON 行里真有 `"细节"` 字段**'
       '（模型没地方写描写，"动作干瘪"就治不了）',
       '"细节"' in _json_line and '最差的一拍' in text,
       f'JSON 行={_json_line[:80]!r} 来源={src}')
    ok('F2 ★★ 里面明确写着"**只给一句台词、别的什么都不给，是最差的一拍**"'
       '（这是"不要只有对话"的正面口径）',
       '最差的一拍' in text, '')
    ok('F3 ★★ 里面说了「内心」**任何时候都能填**（不只在"想事情"那一档）',
       '任何时候都能填' in text, '')

    builtin = (APP_DIR / 'agent' / 'core.py').read_text(encoding='utf-8')
    ok('F4 ★★★ **内置那份 `_tail` 也改了**（`agent/core.py`）'
       '—— 两份不一致时，外置那份一旦被删/改名，口径会**悄悄退回旧版**',
       '"细节": "你**怎么**做的' in builtin and '最差的一拍' in builtin, '')
    ok('F5 ★★ 内置那份同样含「任何时候都能填」',
       '任何时候都能填' in builtin, '')

    crew = (APP_DIR / 'crew' / 'agents.py').read_text(encoding='utf-8')
    ok('F6 ★★★ `FILMABLE_RULES` **不再"禁止心理活动"**'
       '（原来写着"不写他心里其实在想……"，于是心理活动在写作层就被掐掉了）',
       '不写"他心里其实在想' not in crew, '那句禁令还在')
    ok('F7 ★★ `FILMABLE_RULES` 明确说了"心里那一层也要给，只是要装在它自己的地方"',
       '心里那一层也要给' in crew, '')
    # ⚠ 不能写成"旧句子不在 crew 里"—— 新文本**引用了**那句旧话做对比
    #   （"原来这一条写的是…"）⇒ 那样写会**假红**（实测一次）。
    #   判"改了没有"要看**新的那条在不在**。F6 同理。
    # [EN] ⚠ Must not be written as "the old sentence is not in crew" -- the new text **quotes** that
    # [EN] old wording for contrast ("this rule used to say...") => that form would **falsely
    # [EN] redden** (measured once). Judging "was it changed" means checking **whether the new
    # [EN] version is there**. Same for F6.
    ok('F8 ★★ `SCREEN_HARD_RULES` ① 改成了"**镜头里的东西要写具体**"'
       '（并说明"心里那层要写进心声"，而不是"不许写"）',
       '镜头里的东西要写具体' in crew and '要写进"心声"' in crew, '')
    # ⚠ **只看 `FILMABLE_RULES` 那段字符串本体**，不看整个文件 ——
    #   文件里第 747 行有一句**注释**也写着"只写拍得到的"，
    #   拿整个文件查会命中那句注释 ⇒ **假红**（实测踩了一次）。
    #   这正是本项目那条纪律：别用"源码含某字符串"当判据。
    # [EN] ⚠ **Look only at the `FILMABLE_RULES` string itself**, not the whole file -- line 747 has
    # [EN] a **comment** that also says "只写拍得到的", so checking the whole file hits that comment
    # [EN] => **false red** (stepped on once). This is exactly the project rule: never use "the
    # [EN] source contains some string" as a criterion.
    _f = crew[crew.find('FILMABLE_RULES = """'):]
    _f = _f[:_f.find('"""', _f.find('"""') + 3)]
    ok('F9 ★★ `FILMABLE_RULES` 里"只写拍得到的"换成了"**露在外面的要写足**"'
       '（判的是**规则本体**，不是整个文件里有这几个字）',
       '露在外面的要写足' in _f and '只写拍得到的' not in _f,
       f'规则本体 {len(_f)} 字')


def main() -> int:
    report['ok'] = True
    print('=' * 66)
    print('  推演产出要像小说，不能只有对话（2026-10-14 用户点名）')
    print('=' * 66)
    for fn in (section_a, section_b, section_c, section_d, section_e, section_f):
        try:
            fn()
        except Exception as e:                               # noqa: BLE001
            import traceback
            traceback.print_exc()
            ok(f'{fn.__name__} 自己跑通', False, repr(e)[:160])
    n_ok = sum(1 for i in report['checks'] if i['ok'])
    report['n_ok'] = n_ok
    report['n_all'] = len(report['checks'])
    (OUT / 'story_richness_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n推演内容要素（像小说，不只有对话）：{n_ok}/{len(report["checks"])}')
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
