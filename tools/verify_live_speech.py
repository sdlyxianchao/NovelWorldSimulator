# -*- coding: utf-8 -*-
"""验证：**台词要像活人说的**（犹豫 / 漏接 / 音量 / 长度 / 停顿 / 对谁换样子）。

用户 2026-10-12 原话（这一段就是规格）
------------------------------------
    「正常人对话的时候 很多时候会有犹豫 而且对于别人说的话 不是每一句话都有回应的
      而且说话速度不会太快 而且每个人都会根据自己的性格决定自己的说话习惯
      但是很多AI 生成的视频 人物说话没有任何卡顿 速度很快 而且从不犹豫 根本不想真人
      而且很容易吼 而不是正常说话 所以请在剧本生成 小说编写 演员表演的时候
      对这些方面进行优化 让他们更有真人感觉 而不是AI」

拆开是**六个要求**，逐条落成了一个货架条目（都在「人物与对话」架上）
------------------------------------------------------------------
  · 会犹豫、有卡顿 ............「**话不是一条直线**」
  · 不是每句都回应 ............「**不是每句都得接**」
  · 很容易吼、不正常说话 ......「**音量是稀缺的**」
  · 速度不会太快 ..............「**一次说一件事**」
  · 停顿要留下来（给下游）....「**停顿要落在纸上**」
  · 说话习惯由性格决定 ........「**对谁说话就换个样子**」

判据分五组
----------
  A **货架与点名**：六条都在架上、字段齐全，且**每条都有人读**
     （⚠ "都有人读"是这一组的重点 —— 货架上摆着没人拿的书 = 摆着等于没有）
  B **三条线真的接上了**：小说作家 / 剧作家 / 演员各一处，且**开关关掉就不出现**
     （⚠ 演员那条线有**两份文本**：外置模板 `prompts/agent_decide_tail.txt` 与
       `agent/core.py` 的内置 `_tail` —— 只改一份，外置那份会把它盖掉）
  C **审读能查出来**：剧本审读的清单从五件加到六件，第⑥件专查"像不像活人在说话"
  D **去 AI 清单里也有它**：把"吼"做成**可机械审计**的一条
     （⚠ 它必须进**软提示**而不是硬词表 —— 硬词表会被 `strip_hard()` 真删掉，
       而"吼道"一删句子就残了）
  E **开关与幂等**：开关真管用、条目不重名

跑法：
    .venv\\Scripts\\python.exe tools/verify_live_speech.py
产出：assets/screenshots/live_speech_report.json

English:
Verification: **dialogue must sound like a live person says it** (hesitation / missed connections /
volume / length / pauses / changing shape by audience).

The user's exact words on 2026-10-12 (this passage is the spec)
------------------------------------
    "When normal people talk, there is often hesitation, and as for what the other person says, not
     every sentence gets a response, and the speaking speed is not too fast, and everyone decides
     their own speech habits according to their own character. But many AI-generated videos have
     characters who speak with no stumbles at all, very fast, never hesitating -- not like real people
     at all -- and they shout easily instead of speaking normally. So please optimize these aspects
     when generating scripts, writing novels, and performing as actors, to make them feel more like
     real people and not like AI."

Broken down it is **six requirements**, each landed as one shelf entry (all on the "characters and
dialogue" shelf)
------------------------------------------------------------------
  · hesitates, has stumbles .... "**speech is not a straight line**"
  · not every line gets an answer "**not every line needs an answer**"
  · shouts easily, not normal ... "**volume is scarce**"
  · speed is not too fast ....... "**one thing at a time**"
  · pauses must be recorded (for downstream) "**pauses must land on paper**"
  · habits follow character ..... "**change shape by whom you speak to**"

Criteria are in five groups
----------
  A **shelf and naming**: all six are on the shelf with complete fields, and **every one of them is
    read by someone** (⚠ "read by someone" is the point of this group -- a book on the shelf that
    nobody picks up is as good as absent)
  B **the three lines are really wired up**: one spot each for novelist / playwright / actor, and
    **turning the switch off makes it disappear** (⚠ the actor's line has **two texts**: the external
    template `prompts/agent_decide_tail.txt` and the built-in `_tail` in `agent/core.py` -- editing
    only one means the external one overrides it)
  C **the review can catch it**: script review's checklist grows from five items to six, the sixth
    checking "does this sound like live people talking"
  D **the de-AI list has it too**: making "shouting" a **mechanically auditable** item (⚠ it must go
    into the **soft hints**, not the hard word list -- the hard list gets **actually deleted** by
    `strip_hard()`, and deleting "shouted" maims the sentence)
  E **switch and idempotency**: the switch really works, and the entries have no duplicate names
Usage:
    .venv\\Scripts\\python.exe tools/verify_live_speech.py
Output: assets/screenshots/live_speech_report.json
"""
from __future__ import annotations

import ast
import json
import sys
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

import verify_ui_common as VU                               # noqa: E402
VU.redirect_env_writes()

from config import CFG                                      # noqa: E402
from craft import craftmix as cm                            # noqa: E402
from crew import agents as A                                # noqa: E402
from crew import cognition as COG                           # noqa: E402
from style import deai                                      # noqa: E402

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

#: 这一轮加的**六条**手艺（货架上、以及谁读它们）。
# [EN] : the **six** craft entries added this round (on the shelf, and who reads them).
NEW_ENTRIES = ('话不是一条直线', '不是每句都得接', '音量是稀缺的', '一次说一件事',
               '停顿要落在纸上', '对谁说话就换个样子')

#: `职位 → 必须读到的那几条`。★ 写死它，免得以后有人悄悄改掉点名（那六条就成了摆设）。
# [EN] : `position -> the entries it must read`. ★ Hard-coded so nobody can silently change the naming
# [EN] later (which would turn those six into decoration).
WANT = {
    'actor': ('话不是一条直线', '音量是稀缺的'),
    'novelist': ('不是每句都得接',),
    'screenwriter': ('一次说一件事', '停顿要落在纸上'),
    'script_doctor': ('音量是稀缺的',),
    'polisher': ('话不是一条直线',),
    'reviewer': ('对谁说话就换个样子',),
}

#: 演员手艺块里**必须还在**的六条老条目 —— 新点名不许把老条目挤出去。
# [EN] : the six old entries that **must still be present** in the actor's craft block -- the new naming
# [EN] must not push the old ones out.
ACTOR_KEEP = ('说话方式就是身份', '停顿与不答也是台词', '话长短由处境定',
              '口癖来自职业与处境', '弱者用对方的逻辑反打', '性格靠对外部规则的态度')

#: 规则块要覆盖的五个要点（拿关键词认，不认整段文字）。
# [EN] : the five points the rules block must cover (recognised by keywords, not by the whole text).
RULE_KEYS = (
    ('卡顿 / 改口', '找词'),
    ('漏接', '不是每句都得接'),
    ('音量', '音量是稀缺的'),
    ('一次一件事', '一次说一件事'),
    ('停顿写在纸上', '停顿与口气要写在纸上'),
)

report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _txt(rel: str) -> str:
    return (APP / rel).read_text(encoding='utf-8')


def _func_src(src: str, pred) -> str:
    """把所有**满足 `pred(函数源码)`** 的函数源码拼起来（AST 级，不看整体字符串）。
    [EN] Concatenate the source of every function whose source satisfies `pred` (AST level, not whole-file
    [EN] string matching).
    """
    out = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return ''
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seg = ast.get_source_segment(src, node) or ''
            if pred(node.name, seg):
                out.append(seg)
    return '\n'.join(out)


def _fstring_const(src: str, func: str, var: str) -> str:
    """取某个函数里 `var = f"..."` 那个 f-string 的**恒定部分**（`{…}` 那几段跳过）。
    [EN] Take the **constant parts** of the `var = f"..."` f-string inside a given function (skipping the
    [EN] `{...}` segments).
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return ''
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != func:
            continue
        for sub in ast.walk(node):
            if (isinstance(sub, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == var
                            for t in sub.targets)
                    and isinstance(sub.value, ast.JoinedStr)):
                return ''.join(v.value for v in sub.value.values
                               if isinstance(v, ast.Constant)
                               and isinstance(v.value, str))
    return ''


# ══════════════════════════════════════════════════════════════════════
#  A. 货架与点名
# [EN] A. Shelf and naming
# ══════════════════════════════════════════════════════════════════════
def test_shelf() -> None:
    d = cm.load(force=True)
    entries = d['entries']

    missing = [n for n in NEW_ENTRIES if n not in entries]
    ok('A1 ★★ 六条新条目都在工艺库里（一条对应用户的一个要求）',
       not missing, '缺：' + '、'.join(missing) if missing else '六条齐全')

    bad_field = []
    for n in NEW_ENTRIES:
        e = entries.get(n) or {}
        if str(e.get('_货架') or '') != '人物与对话':
            bad_field.append(f'{n}:货架={e.get("_货架")!r}')
            continue
        if not str(e.get('原理') or '').strip():
            bad_field.append(f'{n}:无原理')
        if not str(e.get('提示词') or '').strip():
            bad_field.append(f'{n}:无提示词')
        if not str(e.get('适用') or '').strip():
            bad_field.append(f'{n}:无适用')
    ok('A1 ★★ 六条都挂在「人物与对话」架上，且 原理/适用/提示词 三样齐全'
       '（缺一项就等于没落地，因为提示词那段才是进模型的东西）',
       not bad_field, str(bad_field[:4]))

    # ★★ 「都有人读」—— 货架上摆着没人拿的书，等于没摆
    # [EN] ★★ "Read by someone" -- a book nobody picks up is as good as not shelved
    # ★★★ 2026-10-18 晚：**口径跟着"动态映射"改**。
    #   原来判「**一次** `craft_block` 里必须出现某条目」—— 调度器按
    #   （时机 × 品级 × 拍数）挑之后，任何一条都可能这一拍不被选中（必然假红）。
    #   ⚠ 守的事没变，而且判得更实：这本书跑起来**能不能真的读到它**。
    #   ⇒ 取"5 个时机 × 12 拍"的并集，只要出现过就算到得了。
    #   ⚠ 成对：A3c 守"单次仍然只给额度内几条"，不许为了过这条改成一次全给。
    # [EN] ★★★ 2026-10-18 evening: the rule follows dynamic dispatch. It used to require an entry in
    # [EN] **one** `craft_block` call; after the dispatcher picks by (moment x grade x tick), any entry
    # [EN] may be skipped that beat (inevitable false red). ⚠ What it guards is unchanged and now
    # [EN] judged more concretely: **can this book actually read it**. => union over 5 moments x 12
    # [EN] ticks. ⚠ Paired with A3c: one assembly still yields only the quota.

    def _reachable(who: str) -> set[str]:
        from world.state import WorldState as _W

        out: set[str] = set()
        for mom in ('日常', '开场', '冲突', '转折', '收束'):
            for tk in range(12):
                w = _W()
                w.beat_tick = tk
                w.beat_moment = mom
                w.craft_level = '重'
                A.bind_world(w)
                try:
                    blk = A.craft_block(who, '', '')
                finally:
                    A._reset_world()
                out |= {ln[1:ln.index('〕')] for ln in blk.splitlines()
                        if ln.startswith('〔')}
        return out

    _reach = {who: _reachable(who) for who in WANT}
    not_read = []
    for who, want in WANT.items():
        for n in want:
            if n not in _reach[who]:
                not_read.append(f'{who}←{n}')
    ok('A2 ★★★ 六条**都真的有人读**（5 个时机 × 12 拍的并集里出现过 —— '
       '判"这本书里能不能读到"，不是"某一次必须出现"）'
       '—— 用户点的是"剧本生成 / 小说编写 / 演员表演"三条线，'
       '所以一条都不许是货架上的摆设',
       not not_read, '、'.join(not_read) if not_read else str(len(WANT)) + ' 个职位都读到了')

    # ★★★ 下面两条是**回归面**，也是这一轮反例法当场纠正过的地方：
    #   A3 原来写成"拿手艺块看六条老条目在不在" —— 结果**永远绿**（不会红），
    #   因为 `craft_block` 收尾是 `picked[:max(limit, len(prefer))]`，
    #   prefer 根本截不掉；真正会把老条目弄丢的只有**点名表被改**。
    # [EN] ★★★ The two below are the **regression surface**, and exactly what the counterexample
    # [EN] method corrected this round: A3 was originally written as "look at the craft block to see
    # [EN] whether the six old entries are present" -- and it was **always green** (could never go
    # [EN] red), because `craft_block` ends with `picked[:max(limit, len(prefer))]` and `prefer` can
    # [EN] never be cut; what really loses an old entry is **editing the named list**.
    prefer = A.READS.get('actor', ())
    lost = [n for n in ACTOR_KEEP if n not in prefer]
    ok('A3 ★★★ 演员的**点名表**里六条老的**一条不少**'
       '（为了塞新条目而把老条目从 `READS` 里删掉 = 拆东墙补西墙）',
       not lost, '被删掉：' + '、'.join(lost) if lost else f'八条点名都在：{len(prefer)} 条')

    # ★★★ 行为级：**点名条目没有被新增条目挤掉**（2026-10-18 晚重写这一条）。
    #   原来是"`prefer` 不受额度截断"—— 那个机制已经换成"品级排序"
    #   （`craft/dispatch.tier`：点名的算 `重`，排在前面）。再判"prefer 无上限"
    #   就是在**为一个不存在的设计作证**（本项目最难过的一种红）。
    #   ⚠ 但它守的事仍然成立：**用户点名的八条老的，不许因为塞了新条目就读不到。**
    #   ⇒ 判法：八条老点名在"5 时机 × 12 拍"的并集里**全部出现**。
    #   ⚠ 成对：A3c 守"单次只给额度内几条"，防的是"为了让 A3b 绿而一次全给"。
    # [EN] ★★★ Behavioural: **the named entries were not squeezed out by the new ones** (rewritten
    # [EN] 2026-10-18 evening). It used to be "`prefer` is not truncated by the quota" -- that
    # [EN] mechanism is now "grade ordering" (`craft/dispatch.tier` marks named ones heavy and sorts
    # [EN] them first). Testing "prefer has no cap" would be **testifying for a design that no longer
    # [EN] exists**, the hardest kind of red to notice. ⚠ What it guards still holds: **the eight
    # [EN] entries the user named must remain readable** after new ones were added. => all eight appear
    # [EN] in the union over 5 moments x 12 ticks. ⚠ Paired with A3c against "feed everything".
    _actor_reach = _reach['actor']
    lost_beh = [n for n in ACTOR_KEEP if n not in _actor_reach]
    ok('A3b ★★★ 行为级：**八条老点名全都还读得到**'
       '（塞了新条目之后没被挤掉；判可达并集，不是判某一次）',
       not lost_beh, '读不到：' + '、'.join(lost_beh) if lost_beh else
       f'八条都在（可达 {len(_actor_reach)} 条）')
    # ★ 成对：不许为了过上面两条就把整架书一次摊开
    from world.state import WorldState as _WS

    _wq = _WS()
    _wq.beat_tick = 3
    _wq.beat_moment = '冲突'
    _wq.craft_level = '重'
    A.bind_world(_wq)
    try:
        _one = [ln for ln in A.craft_block('actor', '', '').splitlines()
                if ln.startswith('〔')]
    finally:
        A._reset_world()
    ok('A3c ★★ 成对：**单次只给额度内几条**（演员上限 8 条），不是"把整架书摊开"'
       '（全给的话每拍多付几百 token）',
       1 <= len(_one) <= 8, f'{len(_one)} 条')


# ══════════════════════════════════════════════════════════════════════
#  A9. 口癖配额：**只写"一场最多一次"没用**，要给可数的数字
# [EN] A9. Tic quota: "once per scene" alone does not work -- give a number
# ══════════════════════════════════════════════════════════════════════
def test_tic_quota() -> None:
    """2026-10-19 雪国 34 拍实测：提示词里连"实测被套了 5 次"都写着，
    驹子的「你这个人哪」照样用了 **6 次**（`metrics.json` `repeat_top`：8 次）。

    ⇒ 这一条守的是"**可数的事实**"：真实 prompt 里必须出现"这一场已经用了 N 次"，
      而且 N 要跟着实际次数走。
    ⚠ 判的是**真发出去的 prompt**（拦 `llm.chat`），不是 `_tic_quota_line()` 的返回值 ——
      后者只能证明函数会算，证明不了它被挂上了。
    [EN] Measured on a 34-beat Snow Country run (2026-10-19): the prompt even said "measured 5
    [EN] times last run", yet 「你这个人哪」appeared **6 times**. => This guards the **countable
    [EN] fact**: the real prompt must contain "used N times this scene", with N tracking reality.
    [EN] ⚠ Judges the **prompt actually sent**, not the helper's return value.
    """
    import asyncio
    import json

    from agent import core as AC
    from agent.core import Agent
    from world.state import GameTime, PersonState, WorldState

    class _DB:
        def retrieve_memory(self, *a, **k):
            return []

        def add_memory(self, *a, **k):
            pass

        def count_memories(self, *a, **k):
            return 0

        def get_summaries(self, *a, **k):
            return []

        def recent_events(self, *a, **k):
            return []

    w = WorldState()
    w.scene = '温泉旅馆'
    w.clock = GameTime()
    w.people['驹子'] = PersonState(name='驹子', identity='艺伎', location='温泉旅馆',
                                   catchphrase='你这个人哪')
    w.people['岛村'] = PersonState(name='岛村', identity='客人', location='温泉旅馆')
    a = Agent(w.people['驹子'], _DB(), w)
    ps: list[str] = []
    real = AC.llm.chat

    async def spy(tier, messages, **kw):
        ps.append(messages[-1]['content'] if messages else '')
        return (json.dumps({'动作': 'wait', '参数': {'目标': ''}, '台词': '',
                            '内心': '', '理由': '判据'}, ensure_ascii=False), {})

    AC.llm.chat = spy
    try:
        asyncio.run(a.decide())                       # 还没用过
        w.note_line('驹子', '你这个人哪，倒是说句话呀', kind='speak')
        asyncio.run(a.decide())                       # 用过 1 次
        w.note_line('驹子', '你这个人哪，别敲了', kind='speak')
        asyncio.run(a.decide())                       # 用过 2 次
    finally:
        AC.llm.chat = real

    ok('A9a ★★ 第一次还没用过时**不挂**这一段（第一次就啰嗦会让模型当噪声）',
       len(ps) == 3 and '你的口头禅：这一场已经用了' not in ps[0],
       f'{len(ps)} 拍')
    ok('A9b ★★★ 用过之后**真的挂上了可数的事实**（"已经用了 1 次" / "2 次"），'
       '而不是只写一句"一场最多一次"',
       len(ps) == 3 and '这一场已经用了 1 次' in ps[1]
       and '这一场已经用了 2 次' in ps[2],
       ' / '.join('有' if '你的口头禅' in x else '无' for x in ps))
    ok('A9c ★★★ 成对：**给了禁令**（"不许再带它"）—— 只报数字不给禁令，模型只会觉得"知道了"',
       len(ps) == 3 and '不许再带它' in ps[2], '')


# ══════════════════════════════════════════════════════════════════════
#  B. 三条线真的接上了
# [EN] B. The three lines are really wired up
# ══════════════════════════════════════════════════════════════════════
def test_wiring() -> None:
    ok('B1 ★★ `LIVE_SPEECH_RULES` 那一块**五个要点齐全**（卡顿/漏接/音量/一次一件事/'
       '停顿写在纸上）—— 少一条就等于用户的一个要求没接住',
       all(k in A.LIVE_SPEECH_RULES for _label, k in RULE_KEYS),
       str([label for label, k in RULE_KEYS
            if k not in A.LIVE_SPEECH_RULES]) or '五条齐全')

    # ★★★ 演员那条线是**两份文本**：外置模板 + 内置 `_tail`
    # [EN] ★★★ The actor's line has **two texts**: the external template + the built-in `_tail`
    tpl = ''
    tpl_p = APP / 'prompts' / 'agent_decide_tail.txt'
    if tpl_p.is_file():
        tpl = tpl_p.read_text(encoding='utf-8')
    built_in = _fstring_const(_txt('agent/core.py'), 'decide', '_tail')
    need = ('开口前先定音量', '允许带毛边')
    ok('B2 ★★★ 演员那份**两份文本都有**（外置模板 + `agent/core.py` 的内置 `_tail`）'
       '—— 外置模板优先，只改内置那份会被它整个盖掉（改动**看起来生效了、其实没有**，'
       '这一轮差点踩到）',
       all(k in tpl for k in need) and all(k in built_in for k in need),
       f'外置模板={[k in tpl for k in need]} 内置={[k in built_in for k in need]}')

    # ⚠ 那三个占位符**只在外置模板里**：内置的 `_tail` 是 Python f-string，
    #   构造时就已经求值了，所以它里面**没有** `{n_layers}` 这种名字
    #   （第一版判据就是查错了对象 —— 查内置那份，永远查不到）。
    # ⚠⚠ 而且**要跳过注释行**：模板头部的"可用占位符"说明里也写着这三个名字，
    #   只查整份文本的话，正文里的占位符被删掉判据照样绿（反例法当场抓到）。
    # [EN] ⚠ Those three placeholders exist **only in the external template**: the built-in `_tail` is a
    # [EN] Python f-string, already evaluated at construction time, so it contains **no** names like
    # [EN] `{n_layers}` (the first version of this criterion checked the wrong object -- the built-in one
    # [EN] -- and could never find them).
    # [EN] ⚠⚠ And it must **skip comment lines**: the template's header explains the placeholders and
    # [EN] also contains those three names, so checking the whole text let the criterion stay green even
    # [EN] after the placeholders were deleted from the body (caught by the counterexample method).
    tpl_body = '\n'.join(ln for ln in tpl.splitlines()
                         if not ln.lstrip().startswith('#'))
    core_src = _txt('agent/core.py')
    core_code = '\n'.join(ln for ln in core_src.splitlines()
                          if not ln.lstrip().startswith('#'))
    ok('B2b ★★ 外置模板**正文**里的三个占位符一个没丢'
       '（`n_layers` / `layers` / `think_field`），且内置那条路**照旧填它们**'
       '—— 加纪律时把占位符弄丢，模板就成了死字。'
       '（⚠ 注释行不算：模板头部那段说明里也写着这三个名字）',
       all('{' + k + '}' in tpl_body
           for k in ('n_layers', 'layers', 'think_field'))
       and all(f'{k}=' in core_code
               for k in ('n_layers', 'layers', 'think_field')),
       str([k for k in ('n_layers', 'layers', 'think_field')
            if '{' + k + '}' not in tpl_body]))

    src = _txt('crew/agents.py')
    sites = _func_src(src, lambda name, seg: 'live_speech_block()' in seg)
    ok('B3 ★★ 小说作家那条线上挂了（AST：调 `live_speech_block()` 的那个函数里'
       '同时在拼 `ChapterTask` 的细纲）—— 用户点名"**小说编写**"也要改',
       bool(sites) and 'ChapterTask(' in sites,
       '' if sites else '没有任何函数调用它')

    ok('B4 ★★ 剧作家那条线上挂了（AST：同一批调用点里，有一个在拼 `_rules` 的'
       '那个函数里）—— 用户点名"**剧本生成**"也要改',
       bool(sites) and '_rules' in sites,
       f'挂载点函数数={len(sites.split(chr(10)))}')

    ok('B4b ★★ 两处挂载用的是**同一个开关入口**（`live_speech_block()`）'
       '—— 不是各写一遍 `if CFG.b(...)`：那样判据只能去会话源码，'
       '而"字符串哨兵"是本项目一直在防的假绿',
       src.count('live_speech_block()') >= 2, str(src.count('live_speech_block()')))

    # 行为：开关真的管用
    # [EN] Behaviour: the switch really works
    was = CFG.b('CREW_LIVE_SPEECH')
    try:
        CFG.set('CREW_LIVE_SPEECH', 'false')
        off = A.live_speech_block()
        CFG.set('CREW_LIVE_SPEECH', 'true')
        on = A.live_speech_block()
    finally:
        CFG.set('CREW_LIVE_SPEECH', 'true' if was else 'false')
    ok('B5 ★★★ 行为级：开关**开着有内容、关掉是空串**'
       '（"关掉则回到从前"这句话得真成立，不然这个开关就是装饰）',
       bool(on) and off == '', f'开={len(on)}字符 关={off!r}')


# ══════════════════════════════════════════════════════════════════════
#  C. 审读能查出来
# [EN] C. The review can catch it
# ══════════════════════════════════════════════════════════════════════
def test_review() -> None:
    src = _txt('crew/agents.py')
    rev = _func_src(src, lambda name, seg: '剧本审读' in seg)
    # ★★★ 2026-10-18：这一段原来**写死了"六件事"**，而判据自己的注释就写着
    #   "加了第⑥件却忘了改，清单就会自相矛盾" —— 结果加了⑦⑧之后果然红了。
    #   ⇒ 改成**数出来的**：把中文数字读出来、把正文里真实的 ①②③… 数出来，两者必须相等，
    #     并且等于 `EXPECT_ITEMS`。这样"加了一条忘了改那句话"和"改了那句话没加条目"都会红。
    # [EN] ★★★ 2026-10-18: this used to **hardcode "six things"**, and its own comment said
    # [EN] "add the 6th item and forget the sentence, and the list contradicts itself" -- adding
    # [EN] ⑦⑧ made it red exactly as predicted. Now it is **counted**: read the Chinese numeral,
    # [EN] count the real ①②③... markers, require them equal and equal to `EXPECT_ITEMS`, so both
    # [EN] "added an item, forgot the sentence" and "changed the sentence, forgot the item" go red.
    CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
          '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
    EXPECT_ITEMS = 8
    import re as _re
    m = _re.search(r'逐条看这([一二三四五六七八九十])件事', rev)
    said = CN.get(m.group(1), 0) if m else 0
    # ⚠ 只数**行首**的圆圈序号：正文里还会**引用**它们（"（⑦那种）·（⑧那种）"），
    #   按出现次数数会多算成 10（本条判据第一版就是这么红的）。
    # [EN] ⚠ Count only markers **at line start**: the text also **references** them
    # [EN] ("(the ⑦ kind) · (the ⑧ kind)"), and counting occurrences yields 10.
    marked = len(set(_re.findall(r'(?m)^[①②③④⑤⑥⑦⑧⑨⑩]', rev)))
    ok('C1 ★★★ 审读清单的**件数与条目数对得上**'
       '（"逐条看这 N 件事"里的 N == 正文里真实出现的 ①②③… 个数 == 8）',
       said > 0 and said == marked == EXPECT_ITEMS,
       f'说的是 {said} 件 / 实际标了 {marked} 条 / 应为 {EXPECT_ITEMS}')

    sixth = rev[rev.find('⑥'):] if '⑥' in rev else ''
    ok('C2 ★★★ 第⑥件专查"像不像活人在说话"，四条自查都在：'
       '（漏接 / 吼 / 一口气说三件事 / 一处停顿都没有）',
       all(k in sixth for k in ('漏接', '吼道', '好几件事', '停顿')),
       str([k for k in ('漏接', '吼道', '好几件事', '停顿')
            if k not in sixth]) or '四条齐全')

    steps = [ref for _a, ref in COG.THINK_STEPS.get('script_doctor', ())]
    ok('C3 ★★ 审读的"先想后答"里也多了这一步（出处写着「音量是稀缺的」）'
       '—— 提示词里的清单负责"判",思维链负责"判之前先问一遍"',
       '音量是稀缺的' in steps and any(
           '活人' in a for a, _r in COG.THINK_STEPS.get('script_doctor', ())),
       str(steps))

    ok('C3b ★★ 演员开口前的**最后一个念头**是音量那一条'
       '—— 位置是刻意的：紧挨台词的那一问才管得住"动不动就吼"',
       [r for _a, r in COG.THINK_STEPS.get('actor', ())][-1:] == ['音量是稀缺的'],
       str([r for _a, r in COG.THINK_STEPS.get('actor', ())]))


# ══════════════════════════════════════════════════════════════════════
#  D. 去 AI 清单里也有它（可机械审计的那一半）
# [EN] D. The de-AI list has it too (the mechanically auditable half)
# ══════════════════════════════════════════════════════════════════════
def test_deai_voice() -> None:
    soft_kinds = [k for k, _p, _n in deai.SOFT]
    ok('D1 ★★ 「喊叫滥用」进了**软提示**（正则，命中就记一笔）',
       '喊叫滥用' in soft_kinds, str(soft_kinds[-3:]))

    # ★★★ 它**不许**进硬词表：硬词表会被 `strip_hard()` 真删掉
    # [EN] ★★★ It **must not** go into the hard list: the hard list gets **actually deleted** by
    # [EN] `strip_hard()`
    hard_words = [w for ws in deai.HARD.values() for w in ws]
    ok('D2 ★★★ 音量词**不在硬词表里**（`HARD` 里一个"吼"字头都没有）'
       '—— 硬词表会被 `strip_hard()` **真的删掉**，'
       '而"他吼道：…"一删就成了"他：…"（句子残了）。'
       '硬词表里的既有成员（"首先""深深地"）都是**删了不伤句意**的修饰词，'
       '音量词不是这一类',
       not any('吼' in w for w in hard_words),
       str([w for w in hard_words if '吼' in w]))

    line = '他吼道："你走。"'
    new, removed = deai.strip_hard(line)
    ok('D3 ★★★ 行为级：`strip_hard()` 遇到这句话**一个字都不删**'
       '（证明 D2 不是嘴上说说 —— 清理那一步真的没碰它）',
       new == line and not removed, f'新={new!r} 删={removed}')

    res = deai.audit_text('他吼道："你走。" 她又尖叫起来。')
    hit = [h for h in res.hits if h.kind == '喊叫滥用']
    ok('D4 ★★ 行为级：审计**真的报出来**（不是词表里躺着没人用）',
       bool(hit), f'命中 {len(hit)} 处：' + '、'.join(h.what for h in hit[:4]))

    blk = deai.prompt_block()
    ok('D5 ★★ 它也进了**事前**那段提示词（"别写成 AI 腔"那份清单）'
       '—— 事后审计是兜底，事前告知才是省钱的（写对了就不用改）',
       '喊叫滥用' in blk, blk[:60].replace('\n', ' | '))


# ══════════════════════════════════════════════════════════════════════
#  E. 开关与幂等
# [EN] E. Switch and idempotency
# ══════════════════════════════════════════════════════════════════════
def test_misc() -> None:
    ok('E1 ★ 六条条目名**互不重复**，也不与既有条目撞名'
       '（撞名会让 `craftmix` 静默丢掉一条）',
       len(set(NEW_ENTRIES)) == len(NEW_ENTRIES)
       and all(cm.resolve_entry(n) for n in NEW_ENTRIES),
       str([n for n in NEW_ENTRIES if not cm.resolve_entry(n)]))

    ok('E2 ★ 配置面板上**有**这个开关，且默认开'
       '（用户没点名要开关，但"关掉回到从前"是本项目对每一个新规则的统一承诺）',
       CFG.b('CREW_LIVE_SPEECH') is True, str(CFG.b('CREW_LIVE_SPEECH')))

    ok('E3 ★ 规则块写的都是**做得到的动作**（找词 / 压低声音 / 说一句、停、再说一句 / '
       '省略号与圆括号里的动作），不是"更有代入感"这类没法执行的形容词',
       all(k in A.LIVE_SPEECH_RULES
           for k in ('找词', '压低声音', '说一句、停、再说一句'))
       and not any(k in A.LIVE_SPEECH_RULES
                   for k in ('更有代入感', '充满张力', '写得生动')),
       '')


# ══════════════════════════════════════════════════════════════════════
def main() -> int:
    print('═' * 62)
    print('  验证：台词像活人说的（犹豫 / 漏接 / 音量 / 长度 / 停顿 / 换样子）')
    print('═' * 62)
    try:
        print('\n【A】货架与点名')
        test_shelf()
        print('\n【A9】口癖配额（可数的事实，不只是规则）')
        test_tic_quota()
        print('\n【B】三条线真的接上了')
        test_wiring()
        print('\n【C】审读能查出来')
        test_review()
        print('\n【D】去 AI 清单里也有它')
        test_deai_voice()
        print('\n【E】开关与幂等')
        test_misc()
    except Exception:                                            # noqa: BLE001
        report['fatal'] = traceback.format_exc()
        print(traceback.format_exc(), flush=True)

    bad = [c for c in report['checks'] if not c['ok']]
    report['passed'] = len(report['checks']) - len(bad)
    report['total'] = len(report['checks'])
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'live_speech_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  真人感（怎么说才像活人）验证：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62, flush=True)
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
