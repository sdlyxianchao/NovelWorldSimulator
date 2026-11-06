# -*- coding: utf-8 -*-
"""验证：**对话接得上**（用户 2026-10-07 报「所有人都在自说自话」）。

用户原话
--------
「所有人说话都给我一种一直在自说自话的感觉，正常应该是有一个事情大家都对这个
  事情进行讨论，互相针对别人说的话回应，然后做动作和说话一起推进剧情，
  现在给我的感觉就是每个人知道有一个主题，但是大家互相不沟通，自己说自己的话
  做自己的事情，但好像是针对一个事情，实际每个人说的话做的事情是互相没关联的，
  造成的结果就是看对话很割裂」

查出来的根因（三条，都在"人物听不见别人"这一点上）
--------------------------------------------------
1. **决策输入里根本没有"别人刚说了什么"** —— `_semi` 只有场景 / 在场名单 / 门外，
   `_dyn` 只有他自己的记忆（而记忆里只有**他自己**做过的事）。
   所以"针对别人的话回应"在物理上不可能发生：他不是不想接，是没听见。
2. **挑人是纯随机** —— 每拍只挑 1~2 人，被问的人可能好几拍才被抽中，
   那时中间已经插进来三四件不相干的事。有来无回，对话就断了。
3. **同拍两人并行且互不可见** —— 于是屏幕上出现"两个人各说一句不相干的话"。

这一支钉住修好之后的行为，**每条都要能红**：

  A **听得见**：决策提示词里有 `[刚才]`，内容是别人刚说的话（不是自己的）。
  B **分得清**：有人冲你说 → 「X 对你说」；自己刚说的 → 「你刚说」。
  C **接得上**：被点名的那个**下一拍优先被选去决策**（`_reply_candidates`）。
  D **同拍看得见**：领说者先决策并立刻进缓冲 → 同拍第二人的提示词里
    **有领说者刚说的那句话**（这是最要紧的一条：它治的是"同一拍各说各的"）。
  E **听不见隔墙的话**：换到别处去的人，看不到这一场的话。
  F **退回得干净**：`DIALOGUE_CONTEXT=false` → 那段不出现，挑人回到纯随机。
  G **提示词干净**：模板头部那些给人看的注释**不进提示词**。
  H **边说边做**：台词里带圆括号动作能原样通过（不被打断、不被清洗）。

跑法：.venv\\Scripts\\python.exe tools/verify_dialogue_thread.py
产出：assets/screenshots/dialogue_thread_report.json

English:
Verification: **the conversation connects** (user reported on 2026-10-07: "everyone is talking
to themselves").
User's original words
--------
"Everyone's speech gives me the feeling that they are always talking to themselves. Normally
there should be one matter that everyone
  discusses, responding to what others say, and then actions and speech advance the plot together.
  Right now it feels like everyone knows there is a topic, but they do not communicate with each other, each saying their own words
  and doing their own things, though it seems to be about one matter, in fact what each person says and does is unrelated to the others,
  and the result is that the conversation looks very disjointed"
Root causes found (three, all on the point that "characters cannot hear others")
--------------------------------------------------
1. **The decision input simply has no "what others just said"** -- `_semi` only has scene / present list / outside the door,
   `_dyn` only has his own memory (and the memory only contains things **he himself** did).
   So "responding to others' words" is physically impossible: it is not that he does not want to respond, it is that he did not hear it.
2. **Picking people is purely random** -- each tick only 1~2 people are picked, and the person asked may only be drawn after several ticks,
   by which time three or four unrelated things have already been inserted in between. With no return, the conversation breaks off.
3. **The two people in the same tick act in parallel and cannot see each other** -- so on screen there appear "two people each saying an unrelated sentence".
This branch pins down the behavior after the fix, **every item must be able to go red**:
  A **Can hear**: the decision prompt contains `[just now]`, and the content is what others just said (not one's own).
  B **Can distinguish**: someone speaks to you -> "X says to you"; what you just said -> "you just said".
  C **Connects properly**: the named person is **prioritized for selection in the next tick** (`_reply_candidates`).
  D **Visible within the same tick**: the lead speaker decides first and immediately enters the buffer → in the same tick, the second person's prompt
    **contains what the lead speaker just said** (this is the most important point: it fixes "everyone speaking independently in the same tick").
  E **Can't hear words through walls**: someone who moves elsewhere cannot see what was said in this scene.
  F **Falls back cleanly**: `DIALOGUE_CONTEXT=false` → that segment doesn't appear, selection reverts to pure random.
  G **Prompt is clean**: those human-facing comments at the top of the template **do not enter the prompt**.
  H **Speak while acting**: parenthesized actions within dialogue pass through as-is (not interrupted, not sanitized).
How to run: .venv\\Scripts\\python.exe tools/verify_dialogue_thread.py
Output: assets/screenshots/dialogue_thread_report.json
"""
from __future__ import annotations

import asyncio
import json
import random
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
PROMPTS_SEEN: list[str] = []


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


# ══════════════════════════════════════════════════════════════════
#  夹具：一个最小世界 + 一个能记录 prompt 的桩
# [EN] Fixture: a minimal world + a stub that can record prompts
# ══════════════════════════════════════════════════════════════════
def make_world(names=('主角', '柳娘', '更夫')):
    from world.state import WorldState, PersonState
    w = WorldState(scene='司天台', weather='雨')
    for n in names:
        w.add_person(PersonState(n, identity=f'{n}的身份', personality='话少'))
    w.place_names = ['司天台', '西市']
    w.worldview_text = '唐，长安。城里的时辰不是听天，是听更鼓。'
    return w


def make_loop(w, *, script_mode=True):
    """造一个**只够跑 `_tick` 的** RunLoop（不装配项目、不连数据库）。
        English:
    Build a RunLoop that is **just enough to run `_tick`** (no project assembly, no database
    connection).
    """
    from sim.loop import RunLoop
    from agent.core import Agent

    class _DB:
        def get_summaries(self, k=6, scope='故事'):
            return []

        def recent_events(self, n=20, game_day=0):
            return []

        def retrieve_memory(self, *a, **k):
            return []

        def add_memory(self, *a, **k):
            pass

        def add_event(self, *a, **k):
            pass

        def count_memories(self, *a, **k):
            return 0

    db = _DB()
    agents = [Agent(w.people[n], db, w) for n in w.people]
    loop = RunLoop(w, agents, _StubDirector(), db, None)   # run=None：不落盘
    # [EN] run=None: do not persist to disk
    loop._rng = random.Random(7)
    # 打桩：不要真的落盘 / 不要界面
    # [EN] Stub it out: do not actually persist to disk / no UI
    loop._push_narrative = lambda *a, **k: None
    loop._status = lambda *a, **k: None
    loop._maybe_branch = _noop
    loop._maybe_dispatch = _noop
    loop._run_backstage = _noop
    loop._check_progress = _false
    loop._maybe_group_chat = _noop
    loop._sync_crowd = _noop
    loop._flush_tick = lambda *a, **k: None
    loop._maybe_quiet = lambda: None
    return loop


async def _noop(*a, **k):
    return None


async def _false(*a, **k):
    return False


class _StubDirector:
    """只回答"这一拍不挑事、不到终点"。
        English:
    Only answers "this tick doesn't stir things up, and hasn't reached the end".
    """

    def __init__(self):
        self._pending_intervention = None

    async def on_tick(self):
        return None

    async def on_day_start(self):
        return 0.0

    def is_at_end(self):
        return False

    def current_node_info(self):
        return None

    def evaluate_progress(self, events):
        raise AssertionError('不该走到进度评估')


def patch_decide(replies: list[str]):
    """把 `Agent.decide` 换成桩：记录 prompt，按顺序回预设动作。

    返回 (prompts, restore)。`prompts` 每次调用追加一份提示词全文 ——
    判据全靠它（"他到底看见什么"只有这里能看）。
    
        English:
    Replace `Agent.decide` with a stub: record the prompt, return preset actions in order.
        Returns (prompts, restore). `prompts` appends a full copy of the prompt text on each call —
        the criteria depend entirely on it ("what he actually saw" can only be seen here).
    """
    from agent.core import Agent, Action
    real = Agent.decide
    prompts: list[str] = []
    names: list[str] = []
    idx = {'i': 0}

    async def _decide(self, context: str = ''):
        # 走真实现去**拼提示词**，但把最后那次 llm 调用截住 ——
        # 直接重跑一遍 `decide` 的拼装段太长，这里用最小侵入的办法：
        # 临时把 `llm.chat` 换掉，让它把 prompt 记下来并回一句我们给的话。
        # [EN] Go through the real implementation to **assemble the prompt**, but intercept the last llm call
        # [EN] --
        # [EN] Re-running the assembly section of `decide` directly is too long, so use the least invasive
        # [EN] approach here:
        # [EN] Temporarily replace `llm.chat` so it records the prompt and replies with a line we provide.
        from llm import router as R
        real_chat = R.llm.chat

        async def _fake_chat(tier, messages, **kw):
            prompts.append(str(messages[0]['content']))
            body = replies[min(idx['i'], len(replies) - 1)]
            idx['i'] += 1
            return (body, {}) if kw.get('return_meta') else body

        R.llm.chat = _fake_chat
        try:
            # ⚠ **记"谁在决策"要在这里**：领说者走的是 `self._rng.choice`，
            #   不是 `random.sample` —— 只 spy `random.sample` 会漏掉他，
            #   判据于是假红（第一版就是这么红的）。
            # [EN] ⚠ **Recording "who is deciding" must happen here**: the lead speaker goes through
            # [EN] `self._rng.choice`,
            # [EN] not `random.sample` -- spying only on `random.sample` will miss him,
            # [EN] and the criterion then falsely goes red (that is how the first version went red).
            names.append(str(self.name))
            return await real(self, context)
        finally:
            R.llm.chat = real_chat

    Agent.decide = _decide
    return prompts, names, lambda: setattr(Agent, 'decide', real)


def say(who: str, line: str, to: str = '') -> str:
    return json.dumps({'动作': 'speak', '参数': {'目标': to}, '台词': line,
                       '内心': '', '理由': '接话'}, ensure_ascii=False)


def act(verb: str, target: str = '') -> str:
    return json.dumps({'动作': verb, '参数': {'目标': target}, '台词': '',
                       '内心': '', '理由': '动作'}, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════
#  A/B/C/D/E —— 真跑 tick
# [EN] A/B/C/D/E -- actually run ticks
# ══════════════════════════════════════════════════════════════════
def test_dialogue_thread(tmp: Path) -> None:
    w = make_world()
    loop = make_loop(w)

    # ── A/B：`[刚才]` 出现在提示词里、且标法分得清 ──
    # [EN] -- A/B: `[just now]` appears in the prompt, and the labeling is distinguishable --
    w.note_line('柳娘', '水不会说谎，人会。', to='主角')
    w.note_line('主角', '漏刻只许校，不许改。', to='柳娘')
    w.note_line('更夫', '去了司天台漏刻科', kind='act')
    sh = w.recent_text(speaker='主角')
    ok('A1 ★ 决策前那段 `[刚才]` 里能看到别人刚说的话',
       '柳娘对你说：「水不会说谎，人会。」' in sh, sh.replace('\n', ' | '))
    ok('A2 ★ 自己刚说的标成「你刚说」（他就知道自己已经说过什么，不会重复）',
       '你刚说：「漏刻只许校，不许改。」' in sh, '')
    ok('A3 别人之间的对话也标出对象（谁对谁说，一眼看得出）',
       w.recent_text(speaker='更夫').count('对') >= 2,
       w.recent_text(speaker='更夫').replace('\n', ' | '))
    ok('A4 动作写成括号旁白（与台词分得开）', '（更夫去了司天台漏刻科）' in sh, '')
    ok('A5 空缓冲 → 空串（不写一个空标题）', w.recent_text(speaker='某人') != ''
       and make_world().recent_text() == '', '')

    # ── 提示词里真的带上了（走完 `decide` 的拼装）──
    # [EN] -- it is really included in the prompt (after going through `decide`'s assembly) --
    prompts, decided, restore = patch_decide([act('wait')])
    try:
        asyncio.run(loop.agents[0].decide())
    finally:
        restore()
    # ★ 反例法抓出来的缺口：A1~A5 是**手写 `note_line`** 之后测渲染的，
    #   所以"主循环到底有没有把台词记进缓冲"这条**没人守**（把
    #   `_note_stage_line` 的 speak 分支整段删掉，A1 照样绿）。
    # [EN] ★ The gap caught by the counterexample method: A1~A5 tested rendering after **hand-writing
    # [EN] `note_line`**,
    # [EN] so "does the main loop actually record the dialogue into the buffer" is **unguarded** (deleting
    # [EN] the whole speak branch of `_note_stage_line` still leaves A1 green).
    #
    #   ⚠ 别用"跑一拍、桩让它说话"来测这一环 —— 那会依赖**随机抽到谁**
    #   （第一版就这么写的：桩让被抽中的两个人各回一句，而被点名的人不在
    #   选中名单里 → 判据假红，看着像产品坏了）。这一环要**直接测**。
    # [EN] ⚠ Do not test this link by "running one tick and having the stub make it speak" -- that depends
    # [EN] on **who gets randomly picked**
    # [EN] (the first version was written that way: the stub made the two picked people each reply, and the
    # [EN] named person was not in
    # [EN] the selected list -> the criterion falsely went red, looking like the product was broken). This
    # [EN] link must be **tested directly**.
    from agent.core import Action as _Act
    w_say = make_world()
    loop_say = make_loop(w_say)
    a_azhi = next(a for a in loop_say.agents if a.name == '柳娘')
    loop_say._note_stage_line(
        a_azhi, _Act(verb='move', target='司天台漏刻科'))
    loop_say._note_stage_line(
        a_azhi, _Act(verb='wait'))                 # 别人看不出来的，不该记
    # ★ 台词要有 `spoken=True` 才记 —— **默认不记**（2026-10-07 改的口径）：
    #   台词由 `_note_entry` 从**真进剧本的词条**记，因为台词可能被去重护栏
    #   挡下（同一句不说两遍），那样它没上屏，就不该进缓冲。
        # [EN] What others cannot see should not be recorded
        # [EN] ★ A dialogue line must have `spoken=True` to be recorded -- **not recorded by default** (the
        # [EN] convention changed on 2026-10-07):
        # [EN] Dialogue lines are recorded by `_note_entry` from **entries that actually enter the script**,
        # [EN] because a dialogue line may be blocked by the deduplication guard
        # [EN] (the same sentence is not said twice), and in that case it did not appear on screen, so it
        # [EN] should not enter the buffer.
    loop_say._note_stage_line(
        a_azhi, _Act(verb='speak', target='主角', dialogue='随手说的一句'))
    ok('A7 ★★ 台词**默认不在这里记**（改由真词条记，免得记到被去重的）',
       not any(r.get('text') == '随手说的一句' for r in w_say.recent_lines),
       str([(r.get('who'), r.get('text')) for r in w_say.recent_lines]))
    loop_say._note_stage_line(
        a_azhi, _Act(verb='speak', target='主角', dialogue='水不会说谎，人会。'),
        spoken=True)
    kinds = [(r.get('who'), r.get('kind'), r.get('text'))
             for r in w_say.recent_lines]
    ok('A7b ★ 领说者那条路（`spoken=True`）把台词记进缓冲（带"对谁说"）',
       any(k == ('柳娘', 'speak', '水不会说谎，人会。') for k in kinds)
       and any(r.get('to') == '主角' for r in w_say.recent_lines),
       str(kinds))
    ok('A7c `move` 也记（别人看得见他走了）', any(
        k == ('柳娘', 'act', '去了司天台漏刻科') for k in kinds), str(kinds))
    ok('A7d `wait` **不记**（别人看不出来；桌面只有 8 条，别拿它弄脏）',
       not any(k[2] in ('', '等了等') for k in kinds), str(kinds))

    # ── `_note_entry`：从**真词条**记（剧本模式唯一的台词来源）──
    # [EN] -- `_note_entry`: record from **real entries** (the only source of dialogue lines in script
    # [EN] mode) --
    from display import script as _S
    w_e = make_world()
    loop_e = make_loop(w_e)
    loop_e._note_entry(_S.dialogue('主角', '漏刻只许校，不许改。', to='柳娘'))
    loop_e._note_entry(_S.exit_('更夫', '离场'))
    ok('A7e ★ `_note_entry` 从真词条记台词（带 to）',
       any(r.get('who') == '主角' and r.get('text') == '漏刻只许校，不许改。'
           and r.get('to') == '柳娘' for r in w_e.recent_lines),
       str([(r.get('who'), r.get('text')) for r in w_e.recent_lines]))
    ok('A7f 非台词词条不进缓冲（出场/退场那些不算"说了话"）',
       not any(r.get('who') == '更夫' for r in w_e.recent_lines),
       str([r.get('who') for r in w_e.recent_lines]))

    # 接线：`_process_actions` 真的调了它 —— 用一个"两个人都在场"的世界，
    # 这样 `min(2, len)` 必然把两个人都选中，桩说一句就必然进缓冲。
    # [EN] Wiring: `_process_actions` actually calls it -- use a world where "both people are present",
    # [EN] so `min(2, len)` necessarily selects both people, and one line from the stub necessarily enters
    # [EN] the buffer.
    w8 = make_world(('主角', '柳娘'))
    loop8 = make_loop(w8)
    _p8, _d8, _r8 = patch_decide([say('主角', '漏刻只许校，不许改。')])
    try:
        asyncio.run(loop8._tick(1))
    finally:
        _r8()
    ok('A8 ★★ 跑一拍：`_process_actions` 真的把它接到了主循环上',
       any(r.get('kind') == 'speak' and '漏刻只许校' in str(r.get('text'))
           for r in w8.recent_lines),
       str([(r.get('who'), r.get('text')) for r in w8.recent_lines]))

    ok('A6 ★★ 那一整段**真的进了人物决策提示词**（不是只存在 world 上）',
       PROMPTS_SEEN_from(prompts) and '[刚才]' in prompts[-1]
       and '柳娘对你说' in prompts[-1],
       (prompts[-1].rsplit('[刚才]', 1)[-1][:60].replace(chr(10), ' / ')
        if prompts and '[刚才]' in prompts[-1] else f'{len(prompts)} 份提示词'))

    # ── C：被点名的人下一拍优先被选 ──
    # [EN] -- C: the named person is preferentially selected on the next tick --
    w2 = make_world()
    loop2 = make_loop(w2)
    # 让"柳娘对主角说话"，然后看下一拍选中的是不是主角
    # [EN] Have "Liu Niang speak to Shen Yan", then check whether the next tick selects Shen Yan
    w2.note_line('柳娘', '那一夜的水怎么说？', to='主角')
    picked: list[str] = []
    real_sample = random.sample

    def _spy_sample(pop, k):
        """把"被点名的那个人"**排到最后**再取前 k 个（确定性桩）。

        ⚠ 为什么不用真 `random.sample`：场上 3 人抽 2 个，"主角第一个被决策"
          本来就有 1/3 概率**碰巧**成立 —— 反例法当场抓出来过（判据概率性通过＝
          假绿）。把这个桩换成"随机一定会**漏掉**主角"，判据就变成确定性的：
            · 代码按 `_reply_candidates` 挑人 → 主角仍会第一个被决策 → 绿；
            · 那条接线被删（变异）→ 主角根本不在选中名单里 → 必红。
        
                English:
        Put "the named person" **at the very end**, then take the first k (deterministic stub).
                ⚠ Why not use real `random.sample`: with 3 people on the field drawing 2, "Shen Yan is decided first"
                  already has a 1/3 chance of **coincidentally** holding — the counterexample method caught it on the spot (probabilistic criteria passing =
                  false green). Replace this stub with one where "random will definitely **miss** Shen Yan", and the criterion becomes deterministic:
                    · Code selects people via `_reply_candidates` → Shen Yan is still decided first → green;
                    · That wiring is deleted (mutation) → Shen Yan isn't in the selected list at all → must be red.
        """
        ordered = ([x for x in pop if getattr(x, 'name', '') != '主角']
                   + [x for x in pop if getattr(x, 'name', '') == '主角'])
        got = ordered[:k]
        picked.extend(getattr(x, 'name', '') for x in got)
        return got

    # ★ 先来一条**纯函数级**的（不受随机影响）：
    #   反例法当场证明了只靠"名单里有他"不够 —— 场上 3 人、随机抽 2 个，
    #   主角本来就有 2/3 概率被抽中，判据**概率性通过**（那是假绿）。
    # [EN] ★ First add a **pure function-level** one (unaffected by randomness):
    # [EN] The counterexample method proved on the spot that having him "in the list" is not enough -- with
    # [EN] 3 people on scene and 2 randomly drawn,
    # [EN] Shen Yan already had a 2/3 chance of being selected, so the criterion **passes
    # [EN] probabilistically** (that is a false green).
    cand = loop2._reply_candidates(loop2.agents)
    ok('C0 ★★ `_reply_candidates` 认得出"刚被点名的那个人"（纯函数级）',
       [a.name for a in cand] == ['主角'], str([a.name for a in cand]))
    # 而且他**必须是第一个开口的**（领说者排在 `actions[0]`）
    # [EN] Moreover he **must be the first to speak** (the lead speaker is placed at `actions[0]`)
    prompts2, decided2, restore2 = patch_decide([act('wait')])
    try:
        random.sample = _spy_sample
        asyncio.run(loop2._tick(1))
    finally:
        random.sample = real_sample
        restore2()
    ok('C1 ★★ 被点名的人**第一个**被决策（有来有回才叫对话）',
       decided2[:1] == ['主角'], f'这一拍决策顺序：{decided2}')

    # 没点名时不该偏心
    # [EN] When no one is named, there should be no bias
    w3 = make_world()
    loop3 = make_loop(w3)
    picked.clear()
    prompts3, decided3, restore3 = patch_decide([act('wait')])
    try:
        random.sample = _spy_sample
        asyncio.run(loop3._tick(1))
    finally:
        random.sample = real_sample
        restore3()
    # ★ C2 原来写的是 `... or True` —— **永远绿**，等于没有这条判据
    #   （2026-10-07 顺手修掉：一个恒真的判据比没有更坏，它让人以为有人在守）。
    #   现在它真的能红：没人被点名的场合**不该偏心** —— 挑人交给随机，
    #   而这里的"随机"是一个**故意排除主角**的桩，他就确实不该被选中。
    # [EN] ★ C2 originally said `... or True` -- **always green**, equivalent to not having this criterion
    # [EN] (fixed incidentally on 2026-10-07: an always-true criterion is worse than none, because it makes
    # [EN] people think someone is guarding it).
    # [EN] Now it can really go red: when no one is named, there **should be no bias** -- picking people is
    # [EN] left to randomness,
    # [EN] and here "randomness" is a stub that **deliberately excludes Shen Yan**, so he really should not
    # [EN] be selected.
    ok('C2 ★ 没人被点名时不偏心（挑人交给随机 —— 别把所有场合都变成对话）',
       loop3._reply_candidates(loop3.agents) == []
       and bool(decided3) and '主角' not in decided3,
       f'候选={[a.name for a in loop3._reply_candidates(loop3.agents)]}'
       f' 决策={decided3} 选中={picked}')

    # ── E：隔墙听不见 ──
    # [EN] -- E: cannot be heard through a wall --
    w4 = make_world()
    w4.note_line('柳娘', '这边说的话', place='司天台')
    w4.note_line('路人', '西市那边的话', place='西市')
    w4.scene = '西市'
    ok('E1 ★ 换到别处之后，**听不见**原来那个地点的话（不然像穿帮）',
       '这边说的话' not in w4.recent_text(speaker='主角')
       and '西市那边的话' in w4.recent_text(speaker='主角'),
       w4.recent_text(speaker='主角'))
    w4.clear_lines()
    ok('E2 缓冲上限封顶（是一张"桌面"，不是记事本）',
       len(w4.recent_lines) == 0, '')
    for i in range(30):
        w4.note_line('某人', f'第 {i} 句')
    from world.state import WorldState
    ok(f'E3 最多留 {WorldState.RECENT_LINES_MAX} 条（最老的先走）',
       len(w4.recent_lines) == WorldState.RECENT_LINES_MAX
       and w4.recent_lines[-1]['text'] == '第 29 句', str(len(w4.recent_lines)))


def PROMPTS_SEEN_from(prompts: list[str]) -> bool:
    return bool(prompts)


# ══════════════════════════════════════════════════════════════════
#  D —— 同拍第二人看得到领说者的话（最要紧的一条）
# [EN] D -- the second person in the same tick can see the lead speaker's words (the most important
# [EN] one)
# ══════════════════════════════════════════════════════════════════
def test_same_tick(tmp: Path) -> None:
    from agent.core import Agent
    w = make_world()
    loop = make_loop(w)
    # 让"柳娘对主角说" → 下一拍主角是领说者，另一个人是"补的"
    # [EN] Have "Liu Niang speak to Shen Yan" -> on the next tick Shen Yan is the lead speaker, and the
    # [EN] other person is a "fill-in"
    w.note_line('柳娘', '博士，那一夜的水怎么说？', to='主角')

    prompts, decided, restore = patch_decide([
        say('主角', '（放下浮箭）先看水。', to='柳娘'),
        act('wait'),
        act('wait'),
    ])
    try:
        asyncio.run(loop._tick(1))
    finally:
        restore()

    ok('D1 ★ 领说者（被点名的人）**先单独决策**（他先开口，别人才有的可接）',
       len(prompts) >= 2, f'这一拍共 {len(prompts)} 次决策')
    first = prompts[0] if prompts else ''
    ok('D2 领说者的提示词里有那句等着他接的话',
       '博士，那一夜的水怎么说？' in first, '')
    # 关键：第二人的提示词里必须有领说者**刚说的那句**
    # [EN] Key point: the second person's prompt must contain **the line the lead speaker just said**
    second = prompts[1] if len(prompts) > 1 else ''
    ok('D3 ★★ 同拍的第二个人的提示词里，**已经有领说者刚说的那句话**'
       '（这一条治的是"同一拍各说各的"）',
       '先看水' in second,
       (second.rsplit('[刚才]', 1)[-1][:70].replace(chr(10), ' / ')
        if '[刚才]' in second else '没有 [刚才] 段'))
    ok('D4 而且标成「对你说」（第二个接得住"他在跟我说话"这层意思）',
       '对你说' in second or '主角' in second, '')


# ══════════════════════════════════════════════════════════════════
#  F —— 开关关掉要**退得干净**
# [EN] F -- when the switch is turned off it must **retreat cleanly**
# ══════════════════════════════════════════════════════════════════
def test_switch_off() -> None:
    saved = CFG.raw('DIALOGUE_CONTEXT')
    try:
        CFG.set('DIALOGUE_CONTEXT', 'false')
        w = make_world()
        loop = make_loop(w)
        w.note_line('柳娘', '水不会说谎，人会。', to='主角')
        ok('F1 ★ 关掉后 `_reply_candidates` 不再偏心（挑人回到纯随机）',
           loop._reply_candidates(loop.agents) == [], '')
        prompts, decided, restore = patch_decide([act('wait')])
        try:
            asyncio.run(loop.agents[0].decide())
        finally:
            restore()
        # ⚠ 判据**不能查字面量 `[刚才]`** —— 模板的引导语里就有这三个字
        #   （"先看 `[刚才]` 那一段"），那样查必然假红。要查的是**那段数据**
        #   在不在：用刚写进去的那句话当哨兵。
        # [EN] ⚠ The criterion **must not check the literal `[just now]`** -- those three characters are in the
        # [EN] template's guidance text
        # [EN] ("first look at that `[just now]` section"), so checking that necessarily falsely goes red. What
        # [EN] must be checked is whether **that piece of data**
        # [EN] is present: use the sentence just written in as a sentinel.
        ok('F2 ★★ 关掉后提示词里**没有那段数据**（与从前一字不差）',
           prompts and '水不会说谎' not in prompts[-1],
           f'{len(prompts)} 份提示词')
        # 缓冲本身照旧记（它不影响提示词，留着也无害）
        # [EN] The buffer itself is still recorded as before (it does not affect the prompt, so keeping it is
        # [EN] harmless)
        ok('F3 关掉后缓冲照旧在记（开关管的是"看不看得见"，不是"记不记"）',
           len(w.recent_lines) >= 1, str(len(w.recent_lines)))
    finally:
        CFG.set('DIALOGUE_CONTEXT', saved)


# ══════════════════════════════════════════════════════════════════
#  G/H —— 提示词干净 + 边说边做
# [EN] G/H -- prompt is clean + speak while acting
# ══════════════════════════════════════════════════════════════════
def test_prompt_hygiene() -> None:
    from util import prompts as P

    raw, src = P.template('agent_decide_tail', '兜底')
    ok('G1 模板文件本身带着给人看的注释（那是给维护者的）',
       raw.lstrip().startswith('#') or '#' in raw[:400], src)
    clean = P.strip_comments(raw)
    ok('G2 ★ 剥注释之后，提示词里**没有那种行**了'
       '（以前每一拍、每个人物都收到一段"想改就改这个文件"）',
       not any(l.lstrip().startswith('#') for l in clean.splitlines())
       and len(clean) < len(raw), f'{len(raw)} → {len(clean)} 字符')
    ok('G3 剥注释**不伤正文**：那几条行动纪律还在',
       '不是独角戏' in clean and 'JSON' in clean and '{n_layers}' in clean, '')
    ok('G4 剥完只剩空白时调用方会退回兜底（不会发出一段空指令）',
       P.strip_comments('# 只有注释\n#\n') == '', '')

    # H：台词里带圆括号动作 —— 决策解析这一层要原样收下
    # [EN] H: dialogue lines contain parenthesized actions -- the decision-parsing layer must accept them
    # [EN] as-is
    from agent.core import Agent, Action
    import json as _json
    body = say('主角', '（把壶挪了挪）这事我不接。')
    obj = _json.loads(body)
    act_obj = Action(verb=obj['动作'], target=obj['参数']['目标'],
                     dialogue=obj['台词'], inner_thought=obj['内心'],
                     reason=obj['理由'])
    ok('H1 ★ 台词里带圆括号小动作能原样通过（"边说边做"不靠两拍）',
       '（把壶挪了挪）' in act_obj.dialogue and act_obj.is_valid(), act_obj.dialogue)
    ok('H2 那句台词进「场上刚发生」时也不被清洗',
       (lambda w: (w.note_line('主角', act_obj.dialogue, to='柳娘'),
                   '（把壶挪了挪）' in w.recent_text(speaker='柳娘'))[1])(make_world()),
       '')


# ══════════════════════════════════════════════════════════════════
def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='nws_dlg_'))
    try:
        print('\n── A/B/C/E 听得见 · 分得清 · 接得上 ──')
        test_dialogue_thread(tmp)
        print('\n── D 同一拍：后者看得见前者 ──')
        test_same_tick(tmp)
        print('\n── F 开关关掉要退得干净 ──')
        test_switch_off()
        print('\n── G/H 提示词干净 · 边说边做 ──')
        test_prompt_hygiene()
    except BaseException:                                        # noqa: BLE001
        report['fatal'] = traceback.format_exc()
        print(report['fatal'])
    finally:
        safe_rmtree(tmp, ignore_errors=True)

    bad = [c for c in report['checks'] if not c['ok']]
    report['ok'] = not bad and not report.get('fatal')
    report['failed'] = [c['name'] for c in bad]
    report['passed'] = len(report['checks']) - len(bad)
    report['total'] = len(report['checks'])
    (OUT / 'dialogue_thread_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n对话衔接验证：{report['passed']}/{report['total']}")
    for c in bad:
        print(f"  ! {c['name']} | {c['detail'][:110]}")
    return 0 if not bad and not report.get('fatal') else 2


if __name__ == '__main__':
    sys.exit(main())
