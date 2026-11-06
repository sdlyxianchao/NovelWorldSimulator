# -*- coding: utf-8 -*-
"""验证：**群众演员必须挂得住主线**（用户 2026-10-21 报「群众演员出现没道理」）。

用户原话：
  「有些群众演员出现的没道理，群众演员出来也必须跟故事主线有关系才可以，
    最好不要突然出来一个，没有任何作用就又退场了。群众演员临时演员的意思，
    是在主角列表之外，承接剧情需要的演员，而不是没有任何作用，突然出现的人。」

病灶三处，判据就按这三处切：
  A **挂靠清单**（`crowd.open_threads`）—— 只有"真正在推进的事"能进清单，
     空世界里清单必须是空的（不许凭空编），"他真正缺的东西"（`need`）不许进。
  B **投人**（`crew/agents.ExtraCasting.cast`）—— 清单空着**根本不投、也不调模型**；
     模型给的 `挂` 填不出/越界 ⇒ 这个人不投（不是"投得不好"，是"不该来"）；
     `挂` 合法 ⇒ 记录里带着那条线的原文。
  C **登记**（`crowd.add_extra`）—— 没挂 / 挂了不在推进的线 ⇒ **不登记**；
     挂对了 ⇒ 带 `挂`/`候`/`新`。
  D **退场**（`crowd.tick_extras`）—— 有挂靠的人**不按拍数走**：
     有人接住 ⇒ 收尾两拍后走；一直没人搭话 ⇒ 等满 `FUNC_PATIENCE` 拍，
     播报要给出理由（"等不到人，走了"），并记进钩子名册（这趟不白来）。
  E **导出**（`crowd.drop_orphan_casts` / `Source.from_run`）—— 只报了个到、
     全书再没人提的人**不进事实底账**；后文提过的一个都不动；
     拿不到整份台本时**一条都不动**（量错了对象比不判更糟）。
  F **接线** —— 投人失败要能落到规则池；规则池那一步自己也要挂得住。

用法：.venv\\Scripts\\python.exe tools/verify_extras_anchor.py
产出：assets/screenshots/extras_anchor_report.json

English:
Verification: **extras must be anchored to the main line** (user, 2026-10-21: "some extras appear
for no reason").
User's words: "some extras appear for no reason; an extra must be related to the main story, better
not to have someone suddenly appear and leave with no function. An extra means: outside the main
cast, an actor serving what the plot needs -- not a person who shows up for no reason."
Three defects, and the criteria follow them:
  A **Thread list** (`crowd.open_threads`) -- only "matters actually moving" may enter; an empty
     world must give an empty list (no inventing); a person's `need` (what he truly lacks) must not
     enter.
  B **Casting** (`crew/agents.ExtraCasting.cast`) -- with an empty list, **cast nobody and make no
     model call**; a missing/out-of-range `挂` means this person is not cast (not "bad casting",
     but "he should not come"); a valid `挂` means the record carries that thread's text.
  C **Registration** (`crowd.add_extra`) -- unanchored, or anchored to a matter not moving => **not
     registered**; correctly anchored => carries `挂`/`候`/`新`.
  D **Exit** (`crowd.tick_extras`) -- anchored extras **do not leave on a beat count**: taken up =>
     wrap up after two beats; never taken up => leave after `FUNC_PATIENCE` beats with a stated
     reason ("waited in vain, left") and be recorded into the hook roster.
  E **Export** (`crowd.drop_orphan_casts` / `Source.from_run`) -- someone who only reported in and
     is never mentioned again **does not enter the fact ledger**; anyone mentioned later is left
     alone; without the whole transcript, **change nothing**.
  F **Wiring** -- a failed cast must fall through to the rule pool; the rule pool must anchor too.
Usage: .venv\\Scripts\\python.exe tools/verify_extras_anchor.py
Output: assets/screenshots/extras_anchor_report.json
"""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    return bool(cond)


def head(title: str) -> None:
    print(f'\n{"=" * 62}\n{title}', flush=True)


# ══════════════════════════════════════════════════════════════════
#  夹具
# [EN] Fixtures
# ══════════════════════════════════════════════════════════════════
TOPIC = '掌柜欠了钱庄三个月的账'
ANCHOR_CAST = {'称呼': '来讨债的', '诉求': '要见掌柜，说账拖了三个月',
               '标志': '袖口磨得发亮', '挂': TOPIC, '接': '来讨账'}


def make_world(day: int = 1):
    from world.state import PersonState, WorldState
    w = WorldState()
    w.scene = '临河茶肆'
    w.game_day = day
    w.extras_today = 0
    w.topic = TOPIC
    w.people['掌柜'] = PersonState(name='掌柜', mission='凑钱还账',
                                  goal='把茶肆保住', need='想被人当成一个人看')
    return w


def bare_world():
    from world.state import WorldState
    return WorldState()


def _ctx(world):
    from crew.agents import SetCtx
    return SetCtx(world=world, db=None, day=1, people=['掌柜'])


def _stub_ask(payload: dict | None, seen: list[str]):
    """造一个假的 `ask`（⚠ 要打到调用方模块里的那个名字 `crew.agents.ask`）。"""
    from llm.replies import Reply

    async def _fake(tier, messages, **kw):
        seen.append('\n'.join(str(m.get('content') or '') for m in messages))
        if payload is None:
            return Reply(ok=False, value=None, raw='', meta={})
        return Reply(ok=True, value=dict(payload), raw='{}', meta={})

    return _fake


# ══════════════════════════════════════════════════════════════════
#  A. 挂靠清单
# [EN] A. Thread list
# ══════════════════════════════════════════════════════════════════
def test_threads() -> bool:
    good = True
    from world import crowd as C
    w = make_world()
    th = C.open_threads(w)
    good &= ok('A1 ★★ 正在推进的事进了清单（这一段谈的话 / 人物手上的活）',
               TOPIC in th and '凑钱还账' in th, th)
    good &= ok('A1b ★ 清单里**没有**"他真正缺的东西"（那是人物不许说出口的）',
               all('被人当成一个人看' not in x for x in th), th)
    good &= ok('A2 ★★ 空世界 → 清单是空的（不许凭空编一件事出来）',
               C.open_threads(bare_world()) == [], C.open_threads(bare_world()))
    w2 = make_world()
    w2.topic = ''
    w2.people.clear()
    w2.active_lines = ['阿枝要找回她爹的下落']
    good &= ok('A2b ★ 故事线（`active_lines`）也算一条正在推进的事',
               C.open_threads(w2) == ['阿枝要找回她爹的下落'], C.open_threads(w2))
    # ★★★ 2026-10-21 真跑判决：**话题排在事件后面**。
    #   实测 mwl_v5 把「这一段在谈的那句话」排在人物的活前面，AI 从"水底看不见月亮"
    #   里读出的不是一件事而是**氛围**，投出来的六个群演全是背景音（还伞的脚夫、
    #   赶夜路的皮货客），没有一个带压力；而 mwl_v4 规则池投的是「讨账的」——
    #   压力型来客，逼掌柜表态。**顺序就是优先级**，这条必须有判据。
    # [EN] ★★★ Verdict from a real run (2026-10-21): **a topic ranks after an event**.
    # [EN] Measured in mwl_v5: putting "the line they are talking about" ahead of the characters'
    # [EN] work made the model read atmosphere instead of a matter, so all six extras were background
    # [EN] noise, none with pressure; mwl_v4's rule pool cast "the debt collector" -- a pressure
    # [EN] visitor. **Order is priority**, so this needs a criterion.
    w6 = make_world()
    th6 = C.open_threads(w6)
    good &= ok('A1c ★★★ **话题排在人物手上的活后面**（顺序就是优先级）',
               th6.index(TOPIC) > max(th6.index('凑钱还账'), th6.index('把茶肆保住')),
               th6)
    good &= ok('A1d ★ 而且"话题"能单独认出来（`topic_thread`）',
               C.topic_thread(w6) == TOPIC and C.topic_thread(bare_world()) == '',
               C.topic_thread(w6))
    good &= ok('A3 ★ 清单有上限（进提示词的东西不能无限长）',
               len(C.open_threads(make_world(), cap=1)) == 1, '')
    return good


# ══════════════════════════════════════════════════════════════════
#  B. 投人
# [EN] B. Casting
# ══════════════════════════════════════════════════════════════════
def test_casting() -> bool:
    good = True
    import crew.agents as CA
    from crew.agents import ExtraCasting
    from world import crowd as C
    old = CA.ask

    # B1 清单空着 → 不投、也不调模型
    seen: list[str] = []
    try:
        CA.ask = _stub_ask({'称呼': '一个男人', '诉求': '随便看看', '标志': ''}, seen)
        got = asyncio.run(ExtraCasting().cast(_ctx(bare_world())))
    finally:
        CA.ask = old
    good &= ok('B1 ★★ 此刻没有正在推进的事 → **一个人都不投**', got is None, got)
    good &= ok('B1b ★★ 而且**一次模型都没调**（没钱可花）', not seen,
               f'{len(seen)} 次调用')

    # B2 模型没给 `挂` → 不投
    seen2: list[str] = []
    try:
        CA.ask = _stub_ask({'称呼': '一个男人', '诉求': '随便看看', '标志': ''}, seen2)
        got2 = asyncio.run(ExtraCasting().cast(_ctx(make_world()), fallback=False))
    finally:
        CA.ask = old
    good &= ok('B2 ★★ 模型投的人**没挂到任何一件事**上 → 不投（不是"投得不好"，是"不该来"）',
               got2 is None, got2)
    good &= ok('B2b ★ 但提示词里**真的把正在推进的事摊出来了**（否则它无从挂起）',
               bool(seen2) and TOPIC in seen2[-1],
               '提示词里有那件事' if (seen2 and TOPIC in seen2[-1]) else '没出现')

    # B3 `挂` 越界 → 不投
    seen3: list[str] = []
    try:
        CA.ask = _stub_ask({'称呼': '背着筐的', '诉求': '问路', '标志': '', '挂': 99}, seen3)
        got3 = asyncio.run(ExtraCasting().cast(_ctx(make_world()), fallback=False))
    finally:
        CA.ask = old
    good &= ok('B3 ★★ `挂` 填了个不存在的序号 → 不投', got3 is None, got3)

    # B4 合法 → 带那条线的原文
    seen4: list[str] = []
    try:
        CA.ask = _stub_ask({'称呼': '背着筐的', '诉求': '来问掌柜那笔账',
                            '标志': '鞋上全是泥', '挂': 1, '接': '替钱庄跑腿'},
                           seen4)
        got4 = asyncio.run(ExtraCasting().cast(_ctx(make_world()), fallback=False))
    finally:
        CA.ask = old
    good &= ok('B4 ★★ `挂` 合法 → 记录里带着**那条线的原文**（一眼看得出他为什么来）',
               bool(got4) and got4.get('挂') == C.open_threads(make_world())[0],
               got4)
    good &= ok('B4b ★ 还带着"他怎么搭上的"（`接`）',
               bool(got4) and got4.get('接') == '替钱庄跑腿', got4)

    # B5 提示词不再教它"不要推动主线"（那是病灶本身）
    src = inspect.getsource(ExtraCasting.cast)
    good &= ok('B5 ★★ 提示词里**不再有**「不要直接推动主线」（病灶原文）',
               '不要直接推动主线' not in src, '')
    good &= ok('B5b ★ 提示词要求"说不出由头就不要投他"', '说不出由头' in src, '')
    return good


# ══════════════════════════════════════════════════════════════════
#  C. 登记
# [EN] C. Registration
# ══════════════════════════════════════════════════════════════════
def test_add() -> bool:
    good = True
    from world import crowd as C
    good &= ok('C1 ★★ 没挂靠的人**不登记**（三个来源共用的那道闸）',
               C.add_extra(make_world(), {'称呼': '路人甲', '诉求': '看两眼'}) is None, '')
    good &= ok('C1b ★★ 挂了一件**此刻不在推进**的事 → 也不登记',
               C.add_extra(make_world(), dict(ANCHOR_CAST, 挂='隔壁老王要嫁女儿')) is None, '')
    w = make_world()
    e = C.add_extra(w, dict(ANCHOR_CAST))
    good &= ok('C2 ★★ 挂对了 → 登记，且记录里带 `挂`/`候`/`新`',
               bool(e) and e.get('挂') == TOPIC and e.get('候') == 0
               and e.get('新') is True, e)
    good &= ok('C2b ★ 登记后 `needs_line` 会把"他为什么在这儿"讲给人物听',
               '为「' in C.needs_line(w) and TOPIC[:10] in C.needs_line(w),
               C.needs_line(w))
    good &= ok('C2c ★ 同一个门外不站两个（称呼+标志相同 → 第二个不登记）',
               C.add_extra(w, dict(ANCHOR_CAST)) is None, '')
    # ★★★ C2d：**换个称呼不算另一个人**（2026-10-21 第四次真跑）
    #   实测 run_mwl_v7：因为"查夜登记"这条线，一晚投出「保正」「保正手下伙计」
    #   「赵保正」「保正跟班」—— 去重键 `称呼|标志` 上两两不等，全部放行，
    #   读者看到的是"保正怎么又来一次"。这是"同义词是字面判据的后门"的又一例。
    # [EN] ★★★ C2d: **a different appellation is not a different person** (4th real run).
    # [EN] Measured in run_mwl_v7: one evening cast "the constable", "the constable's man",
    # [EN] "Constable Zhao", "the constable's follower" -- pairwise unequal on `appellation|marker`,
    # [EN] so all went through. Another case of "synonyms are the back door of literal criteria".
    w7 = make_world()
    C.add_extra(w7, dict(ANCHOR_CAST))
    # ⚠ 口径只说"**互相包含**"这一层（"保正" ⊂ "保正手下伙计"），
    #   不假装能抓纯同义词（"讨债的" vs "要债的" 一个字都不共用）——
    #   那归字面判据管不到，写进来就是自欺。诚实的边界写在下面 C2f。
    # [EN] ⚠ The criterion claims only the "**mutually contained**" layer ("the constable" inside
    # [EN] "the constable's man"), and does not pretend to catch pure synonyms ("debt collector" vs
    # [EN] "bill chaser" share no character). That is beyond a literal criterion; claiming it would
    # [EN] be self-deception. The honest boundary is recorded in C2f below.
    w7.topic = '查夜登记，问新来人的来处'
    w7.extras = []
    C.add_extra(w7, dict(ANCHOR_CAST, 称呼='保正', 诉求='查夜登记，问新来人的来处',
                         挂=w7.topic))
    dupes = ['保正手下伙计', '赵保正', '保正跟班']
    blocked = [x for x in dupes
               if C.add_extra(w7, dict(ANCHOR_CAST, 称呼=x, 诉求='查夜登记',
                                       标志='', 挂=w7.topic)) is None]
    good &= ok('C2d ★★★ 换个说法投出"同一个人" → **不登记**（否则"他又来了"）',
               len(blocked) == len(dupes) and len(w7.extras) == 1,
               f'拦下 {blocked} / 门外 {[e["称呼"] for e in w7.extras]}')
    good &= ok('C2e ★★★ 成对：**真的是另一个人**照样能进（不是一刀切拦掉）',
               C.add_extra(w7, dict(ANCHOR_CAST, 称呼='掏井匠', 诉求='讨上回掏井的工钱',
                                    标志='裤脚有泥', 挂=w7.topic)) is not None,
               [e['称呼'] for e in w7.extras])
    # C2f ★ 诚实边界：**纯同义词抓不到**（"讨债的" vs "要债的" 零字重合），
    #   这条写出来是为了**不许有人假装它闭环了**。
    # [EN] C2f ★ Honest boundary: **pure synonyms are not caught** (zero shared characters).
    # [EN] Recorded so that nobody pretends it is closed.
    w8 = make_world()
    C.add_extra(w8, dict(ANCHOR_CAST, 称呼='来讨债的'))
    good &= ok('C2f ★ 已知边界：纯同义词（「来讨债的」vs「要债的」）**拦不住**'
               '（字面判据的极限，记在这里免得有人以为它闭环了）',
               C.add_extra(w8, dict(ANCHOR_CAST, 称呼='要债的', 标志='')) is not None,
               [e['称呼'] for e in w8.extras])

    # ★★★ C2g：**同一条线不车轮战**（2026-10-21 第四次真跑）
    #   实测 run_mwl_v7：「查夜登记」一夜来了四个人（保正/保正手下伙计/赵保正/保正跟班），
    #   同一件事、全都等不到人走了，整篇被这条线绑死（茶×8、碎段 4、卫生 73.7，四版最差）。
    # [EN] ★★★ C2g: **no relay race on one thread** (4th real run).
    # [EN] Measured in run_mwl_v7: the night-registration thread got four different people in one
    # [EN] night, same matter, all unaddressed, and the piece got tied to that thread -- the worst of
    # [EN] four versions.
    w9 = make_world()
    w9.topic = '查夜登记，问新来人的来处'
    t9 = w9.topic
    got9 = [C.add_extra(w9, {'称呼': x, '诉求': '查夜登记，问新来人的来处',
                             '标志': '', '挂': t9})
            for x in ('保正', '赵捕头', '更夫')]
    good &= ok('C2g ★★★ 同一条线上一天最多来 `THREAD_CAST_MAX` 个（不车轮战）',
               sum(1 for x in got9 if x) == C.THREAD_CAST_MAX,
               f'登记 {[x["称呼"] for x in got9 if x]} / 限 {C.THREAD_CAST_MAX}')
    good &= ok('C2h ★★ 成对：**钩子群演不受这条限制**（老熟人回来挂的正是他那件事）',
               C.add_extra(w9, {'称呼': '打更人', '诉求': '查夜登记', '标志': '',
                                '挂': t9, '钩子': True}) is not None,
               [e['称呼'] for e in w9.extras])
    good &= ok('C2i ★ 不同的线照旧各自能来（不是"一天的额度用完了"）',
               C.add_extra(w9, {'称呼': '掏井匠', '诉求': '讨上回掏井的工钱',
                                '标志': '', '挂': '凑钱还账'}) is not None,
               [e['称呼'] for e in w9.extras])
    return good


# ══════════════════════════════════════════════════════════════════
#  D. 生命周期：按"事办没办成"走，不按拍数
# [EN] D. Lifecycle: by whether the business got done, not by beat count
# ══════════════════════════════════════════════════════════════════
def test_lifecycle() -> bool:
    good = True
    from world import crowd as C

    # D1 刚进门那一拍不判生死
    w = make_world()
    C.add_extra(w, dict(ANCHOR_CAST))
    g = C.tick_extras(w)
    good &= ok('D1 ★ 刚进门那一拍**不会马上被算"等不到人"**（先让他被看见）',
               not g and len(w.extras) == 1, g)

    # D2 一直没人搭话 → 等满 FUNC_PATIENCE 才走，且要给出理由
    left = None
    for _ in range(C.FUNC_PATIENCE):
        g = C.tick_extras(w)
        if g:
            left = g
            break
    good &= ok(f'D2 ★★ 没人搭话 → 不是三拍就走，而是**等满耐心**（{C.FUNC_PATIENCE} 拍）',
               bool(left), f'剩余 {len(w.extras)}')
    good &= ok('D2b ★★ 等满了才走，而且标记为「空等」（不是"到期"）',
               bool(left) and left[0].get('空等') is True, left)
    notice = C.exit_notice(w, left or [], tick=99)
    good &= ok('D2c ★★ 播报**给出理由**：「等不到人，走了」（不是凭空消失）',
               '等不到人，走了' in (notice or ''), notice)
    good &= ok('D2d ★ 空等的人照样记进钩子名册（下次带着"上回没办完"回来）',
               any(h.get('称呼') == '来讨债的' for h in w.hooks), w.hooks)

    # D3 有人接住 → 不再空等，收尾两拍就走
    w2 = make_world()
    C.add_extra(w2, dict(ANCHOR_CAST))
    C.tick_extras(w2)                       # 进门那一拍
    w2.recent_lines = [{'who': '掌柜', 'text': '你去跟那个来讨债的说，账我认'}]
    g2 = C.tick_extras(w2)
    good &= ok('D3 ★★ 有人搭话了 → 不再按"空等"计时（标记 `已接`）',
               not g2 and bool(w2.extras) and w2.extras[0].get('已接') is True,
               w2.extras)
    left2 = None
    for _ in range(C.ENGAGE_AFTER + 1):
        g2 = C.tick_extras(w2)
        if g2:
            left2 = g2
            break
    good &= ok('D3b ★★ 办完事之后才走（`ENGAGE_AFTER` 拍收尾）',
               bool(left2), f'剩余 {len(w2.extras)}')
    notice2 = C.exit_notice(w2, left2 or [], tick=99)
    good &= ok('D3c ★★ 被接住的人走的时候**不说"等不到人"**（他不是白来的）',
               bool(left2) and not left2[0].get('空等') and '等不到人' not in (notice2 or ''),
               notice2)

    # D4 老存档（没有 `挂`）照旧按拍数走 —— 不能凭空判"他走没走成"
    w3 = make_world()
    w3.extras.append({'kind': '功能', '称呼': '赊账的', '诉求': '说下月一定还',
                      '剩余': 1})
    g3 = C.tick_extras(w3)
    good &= ok('D4 ★ 老存档里的群演（没有挂靠信息）仍按拍数退场（存档兼容）',
               bool(g3) and not g3[0].get('空等'), g3)

    # D5 背景群演不受影响
    w4 = make_world()
    w4.extras.append({'kind': '背景', '一行': '两个夫在门口歇脚', '剩余': 1})
    g4 = C.tick_extras(w4)
    good &= ok('D5 ★ 背景群演照旧按拍数走（场面没有"事办完"这回事）',
               bool(g4) and g4[0]['kind'] == '背景', g4)

    # D6 被理过的要**记账**（收工整理靠它给禁令开例外）
    # ⚠ 这条单独测：`engaged` 判对了不等于**记下来了**（反例法 M17 抓到过）。
    # [EN] ⚠ Tested separately: `engaged` being right does not mean it was **recorded**
    # [EN] (caught by counterexample M17).
    w5 = make_world()
    C.add_extra(w5, dict(ANCHOR_CAST))
    C.tick_extras(w5)                       # 进门那一拍
    w5.recent_lines = [{'who': '掌柜', 'text': '让他进来，我认这笔账', 'to': '来讨债的'}]
    C.tick_extras(w5)
    good &= ok('D6 ★★★ 被理过的群演**记进了"今天被理过"的账**（收工整理靠它）',
               '来讨债的' in (getattr(w5, 'extras_engaged', None) or []),
               getattr(w5, 'extras_engaged', None))
    w6 = make_world()
    C.add_extra(w6, dict(ANCHOR_CAST))
    C.tick_extras(w6)
    C.tick_extras(w6)
    good &= ok('D6b ★ 成对：没人理的**不记账**（否则"白来一趟"也会被写进正文）',
               (getattr(w6, 'extras_engaged', None) or []) == [],
               getattr(w6, 'extras_engaged', None))
    return good


# ══════════════════════════════════════════════════════════════════
#  E. 导出：只报了个到的人不进事实底账
# [EN] E. Export: those who only reported in do not enter the fact ledger
# ══════════════════════════════════════════════════════════════════
def test_export() -> bool:
    good = True
    from world import crowd as C
    rows = [
        {'kind': 'event', 'text': '【来人】来讨债的——要见掌柜，说账拖了三个月'},
        {'kind': 'dialogue', 'who': '掌柜', 'text': '茶凉了，换一壶'},
        {'kind': 'event', 'text': '【来人】挑担的——问这儿是不是临河'},
        {'kind': 'dialogue', 'who': '伙计', 'text': '那挑担的又回来了，说扁担断了'},
    ]
    events = [{'text': r['text']} for r in rows if r['kind'] == 'event']
    kept, n = C.drop_orphan_casts(events, rows)
    kept_texts = [e['text'] for e in kept]
    good &= ok('E1 ★★ 只报了到、后文再没人提的群演 → **从事实底账里摘掉**',
               n == 1 and all('来讨债的' not in t for t in kept_texts),
               (n, kept_texts))
    good &= ok('E2 ★★ 后文有人提过的人**一条都不许动**（否则后文成了凭空出现）',
               any('挑担的' in t for t in kept_texts), kept_texts)
    good &= ok('E3 ★★ 拿不到整份台本时**一条都不动**（量错了对象比不判更糟）',
               C.drop_orphan_casts(events, []) == (events, 0),
               C.drop_orphan_casts(events, [])[1])

    # 端到端：Source 这一层就该摘掉
    from crew.atelier import Source
    src = Source.from_run(None, transcript=rows + [
        {'kind': 'dialogue', 'who': '掌柜', 'text': '账我认，让他明日来'},
    ])
    texts = [e['text'] for e in src.events]
    good &= ok('E4 ★★ `Source.from_run`（导出的事实底账）里没有那个孤儿',
               all('来讨债的' not in t for t in texts), texts)
    good &= ok('E4b ★ 但被提过的人还在', any('挑担的' in t for t in texts), texts)
    good &= ok('E5 ★ `Source.from_run` 真的调了这道过滤',
               'drop_orphan_casts' in inspect.getsource(Source.from_run), '')
    return good


# ══════════════════════════════════════════════════════════════════
#  F. 接线
# [EN] F. Wiring
# ══════════════════════════════════════════════════════════════════
def test_wiring() -> bool:
    good = True
    from sim.loop import RunLoop
    src = inspect.getsource(RunLoop._cast_extra)
    i_add = src.find('add_extra')
    i_new = src.find('new_extra')
    good &= ok('F1 ★★ 投出来的人挂不上主线 → **还能落到规则池**（两道都拦就这拍没人来）',
               i_add >= 0 and i_new > i_add, f'add@{i_add} < new@{i_new}')
    good &= ok('F1b ★ 规则池那一步不再是 `rng.choice`（抽到谁算谁）',
               'rng.choice' not in src, '')
    from world import crowd as C
    good &= ok('F2 ★★ 规则池也必须挂得住那条线（搭不上就返回 None）',
               'pick_from_pool' in inspect.getsource(C.new_extra), '')
    # 反例：一条池子里谁都搭不上的线 ⇒ 一个都不投（"门口空着好过白来一个"）
    w = make_world()
    w.topic = '阿枝要找回她爹的下落'
    w.people.clear()
    good &= ok('F2b ★★ 池子里没有跟这条线搭得上的人 → 一个都不投（不是"抽到谁算谁"）',
               C.pick_from_pool(w) is None, C.pick_from_pool(w))
    return good


# ══════════════════════════════════════════════════════════════════
#  G. 有人被要求去理他（2026-10-21 真跑判决后补的第三条）
# [EN] G. Someone is asked to deal with him (the third fix, after the real-run verdict)
# ══════════════════════════════════════════════════════════════════
def test_handoff() -> bool:
    good = True
    from world import crowd as C

    # G1 门口等着的人，导演派活看得见
    w = make_world()
    e = C.add_extra(w, dict(ANCHOR_CAST))
    e['候'] = 1                                 # 站过一拍（刚进门那一拍不算）
    ok_wait = C.waiting(w)
    good &= ok('G1 ★★★ 门口等着、没人理的人进了派活的单子（导演才知道有人在等）',
               len(ok_wait) == 1 and ok_wait[0].get('称呼') == '来讨债的', ok_wait)
    line = C.waiting_line(w)
    good &= ok('G1b ★ 单子上写清了"他为哪件事来"（否则派不出与他有关的活）',
               bool(line) and '为「' in line[0], line)

    # G2 已经有人接了的人不再占单子（别一直催）
    e['已接'] = True
    good &= ok('G2 ★ 已经有人理过的，不再进单子（不是一直催）',
               C.waiting(w) == [], C.waiting(w))
    e.pop('已接', None)

    # G3 派活里没提到他 ⇒ 判"没人被派去理"
    good &= ok('G3 ★★★ 这一批派活**一条都没提到他** ⇒ 判"没人管门口"',
               len(C.unhandled(w, {'掌柜': '回屋歇下不露异样'})) == 1, '')
    good &= ok('G3b ★ 成对：有一条提到了他 ⇒ **不判**（不是无论如何都要插一条）',
               C.unhandled(w, {'沈砚': f'先了结门口「来讨债的」的事'}) == [], '')

    # G4 选谁去接：与这条线最相关的那个
    # ⚠ 夹具要把差距**拉开**：第一次写的时候掌柜(3) 与伙计(2) 只差 1 个字，
    #   换个措辞就平手（平手取先出现的那个）⇒ 判据会随字面抖动。
    # [EN] ⚠ The fixture must **widen the gap**: the first version had 3 vs 2, one character apart,
    # [EN] so any rewording made it a tie (ties go to whoever comes first) and the criterion wobbled.
    w2 = make_world()
    from world.state import PersonState
    w2.people['掌柜'].mission = '了结钱庄那笔账'
    w2.people['掌柜'].goal = '把钱庄的账平了'
    w2.people['伙计'] = PersonState(name='伙计', mission='擦桌子',
                                   goal='别挨骂')
    e2 = C.add_extra(w2, dict(ANCHOR_CAST))
    got = C.pick_handler(w2, e2, ['伙计', '掌柜'])
    good &= ok('G4 ★★ 派给**与这件事最相关**的人（掌柜管账，不是伙计）',
               got == '掌柜', got)
    good &= ok('G4b ★ 谁都搭不上时也**总要有人管门口**（返回第一个人在场的）',
               C.pick_handler(w2, {'称呼': 'x', '诉求': 'zzz', '挂': 'qqq'},
                              ['伙计', '掌柜']) == '伙计', '')

    # G5 派的话必须是"要什么"，不是"怎么做"
    hl = C.handoff_line(e2)
    good &= ok('G5 ★★★ 派的话是「要什么」不是「怎么做」（不越设计那条线）',
               '先了结门口' in hl and '走过去' not in hl and '说一句' not in hl, hl)
    good &= ok('G5b ★ 而且带着他的诉求（人物知道门口这位要什么）',
               '账拖了三个月' in hl, hl)

    # G6 接线：进门那一拍就派活（等不起 8 拍）
    from sim.loop import RunLoop
    src = inspect.getsource(RunLoop._sync_crowd)
    good &= ok('G6 ★★★ 群演进门那一拍就有人被派去理他（`_handoff_extra`）',
               '_handoff_extra' in src, '')
    good &= ok('G6b ★ 而且不打断正在办的活（硬塞会目标漂移）',
               '_mission_still_running' in inspect.getsource(RunLoop._handoff_extra), '')
    # ── G7：**行为**判据，不是源码字符串 ──
    # ⚠ 第一版这里查的是 `'门口此刻等着的人' in dsrc` —— 反例法当场证明它是假判据：
    #   把 `_extras_waiting = _crowd.waiting(...)` 改成 `= []`（门口等人再也不会
    #   进提示词），那段字符串还在，判据照样绿。**判据测字符串 = 永远绿。**
    # ⇒ 现在真跑一次 dispatch：模型只派了"回屋歇下"这种与门口无关的活，
    #   看返回里**有没有多出一条**关于门口那位的。
    # [EN] -- G7: a **behavioural** criterion, not a source string --
    # [EN] ⚠ The first version checked `'门口此刻等着的人' in dsrc`, and the counterexample method
    # [EN] proved it false on the spot: change `_extras_waiting = _crowd.waiting(...)` to `= []`
    # [EN] (so the waiting person never reaches the prompt) and the string is still there, so the
    # [EN] criterion stayed green. **A criterion matching strings is permanently green.**
    # [EN] => Now actually run dispatch once: the model assigns something unrelated ("go back and
    # [EN] rest"), then check whether the result **gained a line** about the one at the door.
    import director.engine as DE
    from director.engine import DirectorEngine
    w3 = make_world()
    C.add_extra(w3, dict(ANCHOR_CAST))
    w3.extras[-1]['候'] = 1

    class _DB:
        def recent_events(self, n=8):
            return []

    eng = DirectorEngine.__new__(DirectorEngine)
    eng.world = w3
    eng.db = _DB()
    eng._last_dispatch = {}
    eng._dispatch_history = {}
    seen: list[str] = []
    # ⚠ 打桩要打**调用方模块里的那个名字**（`director.engine.ask`）——
    #   改 `crew.agents.ask` 或 `llm.replies.ask` 都没用（第一次就是这么打成
    #   真调用的：日志里出现了"导演派活前想过"，而判据拿到的是真模型的话）。
    # [EN] ⚠ Stub **the name in the caller's module** (`director.engine.ask`) -- patching
    # [EN] `crew.agents.ask` or `llm.replies.ask` does nothing (the first attempt hit the real model:
    # [EN] the log showed a real director CoT while the criterion read the model's own output).
    old_ask = DE.ask
    try:
        DE.ask = _stub_ask({'派活': [{'人物': '掌柜', '要什么': '回屋歇下不露异样'}]},
                           seen)
        got7 = asyncio.run(DirectorEngine.dispatch(eng, ['掌柜']))
    finally:
        DE.ask = old_ask
    good &= ok('G7 ★★★ 导演派活时**真的把门口等着的人摊进了提示词**（行为，不是查字符串）',
               bool(seen) and '门口此刻等着的人' in seen[-1] and '来讨债的' in seen[-1],
               '提示词里有那位' if (seen and '来讨债的' in seen[-1]) else '提示词里没有')
    good &= ok('G7b ★★★ 模型只派了无关的活 ⇒ **代码补一条**给门口那位（写了不等于遵守）',
               any('来讨债的' in str(v) for v in (got7 or {}).values()), got7)
    good &= ok('G7d ★ 补的那一条仍是"要什么"（不是"怎么做"）',
               all('走过去' not in str(v) and '说一句' not in str(v)
                   for v in (got7 or {}).values()), got7)
    good &= ok('G7e ★ 而且记下了"这条必须放行"（否则会被"上一件还在办"悄悄丢掉）',
               '掌柜' in (getattr(eng, '_forced_names', None) or set()),
               getattr(eng, '_forced_names', None))

    # ── G8：放行是真的（行为）──
    # ⚠ 同样不能查字符串：把 `if name in forced_door` 改成 `if False`，名字还在。
    # [EN] ⚠ Likewise no string matching: change `if name in forced_door` to `if False` and the
    # [EN] name is still there.
    loop = RunLoop.__new__(RunLoop)
    loop.world = w3
    loop.director = eng

    class _NoWarn(dict):
        pass
    loop._cb_warned = set()
    loop._warn_once = lambda *a, **k: None
    ps = w3.people['掌柜']
    ps.mission = '把账本理清楚'
    loop._mission_still_running = lambda n, m, limit=6: True      # 假装"还在办"
    loop._mission_stuck = lambda rounds, cap: False
    got8 = loop._apply_missions({'掌柜': '先了结门口「来讨债的」的事'}, ['掌柜'])
    good &= ok('G8 ★★★ 门口兜底那一条**真的写进了人物状态**（不被"还在办"拦掉）',
               ps.mission == '先了结门口「来讨债的」的事' and '掌柜' in got8,
               f'{ps.mission!r} / 生效 {got8}')
    # 成对：普通派活仍然按"还在办就不换"拦下（不是把闸拆了）
    ps2 = w3.people['掌柜']
    ps2.mission = '把账本理清楚'
    eng._forced_names = set()
    got9 = loop._apply_missions({'掌柜': '换个新活'}, ['掌柜'])
    good &= ok('G8b ★★★ 成对：**别的派活照样被"还在办"拦下**（不是把防漂移拆了）',
               ps2.mission == '把账本理清楚' and got9 == {},
               f'{ps2.mission!r} / 生效 {got9}')

    # ── G9：**整理稿那条禁令的例外**（"群演正文 0 次"的真正原因）──
    #   实测三版（mwl v4/v5/v6）群演正文全为 0 次，而 v6 的日志里阿九明明问了
    #   「那掏井的，是来讨工钱的么？」—— 不是被压缩掉的，是整理稿的提示词里
    #   写着"在场名单外的人一个字都不许写"，而群演永远不在 `on_stage_names()` 上。
    # [EN] -- G9: **the exception to the wrap-up ban** (the real reason extras appeared 0 times) --
    # [EN] Measured across three versions: 0 occurrences, while v6's log shows Chen Wang asking
    # [EN] about the well-digger. It was not compressed away -- the organizing prompt says "not a
    # [EN] single word about anyone outside the on-stage roster", and extras are never on it.
    import crew.agents as CA3
    from crew.agents import Novelist
    old3 = CA3.ask

    def _transcribe_prompt(world, body: str = '· 动作 阿九：擦桌子。') -> str:
        """真跑一次整理、把提示词抓回来（**行为**，不查源码字符串）。"""
        got: list[str] = []
        CA3.ask = _stub_ask({'正文': 'x'}, got)
        try:
            asyncio.run(Novelist()._transcribe_once(_ctx(world), body,
                                                   scope='（今天就这一段）'))
        finally:
            CA3.ask = old3
        return got[-1] if got else ''

    w4 = make_world()
    w4.extras_engaged = ['掏井匠']
    p4 = _transcribe_prompt(w4, '· 动作 阿九：问那掏井的工钱。')
    good &= ok('G9 ★★★ 被理过的群演**真的进了整理提示词**（否则他永远进不了正文）',
               '掏井匠' in p4, '在提示词里' if '掏井匠' in p4 else '不在提示词里')
    good &= ok('G9b ★★★ 而且是**作为禁令的例外**写进去的（不是悄悄加一个名字）',
               '例外' in p4 and '必须写进正文' in p4, '')
    good &= ok('G9c ★ 只许写实际发生的那几句（不许补来历/下场/心理）',
               '不要给他补来历' in p4, '')
    w5 = make_world()
    w5.extras_engaged = []
    p5 = _transcribe_prompt(w5)
    good &= ok('G9d ★ 成对：今天没人被理过 ⇒ **一个字都不加**（不稀释别的规则）',
               p5 != '' and '例外' not in p5, '没加' if p5 and '例外' not in p5 else '加了')
    return good


if __name__ == '__main__':
    print('群众演员挂靠主线 —— 验证', flush=True)
    all_good = True
    try:
        head('A. 挂靠清单（只有真正在推进的事能进）')
        all_good &= test_threads()
        head('B. 投人（没有落点的人不投）')
        all_good &= test_casting()
        head('C. 登记（三个来源共用一道闸）')
        all_good &= test_add()
        head('D. 退场（按事办没办成，不按拍数）')
        all_good &= test_lifecycle()
        head('E. 导出（只报了个到的人不进底账）')
        all_good &= test_export()
        head('F. 接线')
        all_good &= test_wiring()
        head('G. 有人被要求去理他（门口那位不能没人管）')
        all_good &= test_handoff()
    except Exception:
        report['fatal'] = traceback.format_exc()
        ok('验证没有中途崩溃（有崩溃就不是全绿）', False, report['fatal'][-300:])
        all_good = False
    report['ok'] = bool(all_good)
    (OUT / 'extras_anchor_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    passed = sum(1 for c in report['checks'] if c['ok'])
    failed = [c['name'] for c in report['checks'] if not c['ok']]
    print(f'\n{"=" * 62}\n通过 {passed}/{len(report["checks"])} 项'
          + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)))
    if report.get('fatal'):
        print('\n⚠ 中途崩溃：\n' + report['fatal'][-1200:])
    sys.exit(0 if report['ok'] else 2)
