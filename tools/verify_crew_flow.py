# -*- coding: utf-8 -*-
"""验证：剧组工作流程审计（2026-10-07 第二次全面审计）—— 接线、书目、下游。

用户原话：「再次全面审计剧组工作流程，从顶到底，从开头到戏剧结束。
你可以再去学习下戏剧学院的相关理论 包括且不限于 导演 编剧 小说创作的专业课」

审计查出来的东西分两类，这一支把它们逐条钉住：

  A **接线断了**（真 bug）：名册上写着、开关默认开着、落盘表里有文件名，
    而**那一行调用根本不存在**。查出来的三处：
      · 声音（`Studio.sound_note` 零调用）→ `声音设计.md` 从来不存在；
      · 语言审校（`Studio.polish` 零调用）→ `语言审校.md` 从来不存在；
      · 造型（`Studio.stylist_brief` 零调用）→ 定了穿什么，演员与出图都收不到。
    A 组的判据一律是**行为**的：真跑一天，看**台账里是不是真的出了工**。
    ⚠ 旧判据（`verify_studio_v2` 的 A9/A10）用的是**源码哨兵**
      （`'sound_brief' in src`）—— 那抓不住"函数在、没人调"，已一并改掉。

  B **理论缺位**（结构缺失）：戏校那套课里明写、而流程里没有的东西：
      · 类型卡失效（界面题材名与工艺库卡名对不上）→ 全体职位的"手艺"退化成
        **货架里文件顺序前三条**；
      · 每个职位读的书不对口（场记读到的是剧作者的写作提示）；
      · 麦基／贝克的「一场一转变」只有提示词、**没有人验收**；
      · 斯坦尼的"导演心里那个大纲"（`outline_check`）**写好了零调用**。

  C **没有出口**：剧组各职位的产出以前不进任何导出物（`宣发文案.md` 名册上
    写着 `feeds='export'`，而 `export/*` 一处都没读它）。

跑法：.venv\\Scripts\\python.exe tools/verify_crew_flow.py
产出：assets/screenshots/crew_flow_report.json

English:
Verification: crew workflow audit (2026-10-07 second full audit) —— wiring, bibliography,
downstream.
User's exact words: "Audit the crew workflow again comprehensively, from top to bottom, from the
beginning to the end of the drama.
You can also go study relevant theories from drama academies, including but not limited to the
specialized courses on directing, screenwriting, and novel writing"
The things the audit found fall into two categories; this script pins them down one by one:
  A **wiring broken** (real bug): listed in the roster, switch enabled by default, filename present in the write-to-disk table,
    and yet **that call line simply does not exist**. The three places found:
      · sound (`Studio.sound_note` zero calls) → `声音设计.md` never exists;
      · language review (`Studio.polish` zero calls) → `语言审校.md` never exists;
      · styling (`Studio.stylist_brief` zero calls) → what to wear is decided, but neither the actor nor image generation receives it.
    Group A's criteria are all **behavioral**: really run a day, check **whether the ledger really shows work done**.
    ⚠ The old criteria (`verify_studio_v2` A9/A10) used **source sentinels**
      (`'sound_brief' in src`) —— those cannot catch "the function exists, nobody calls it", and have been changed along with it.
  B **theory absent** (structural gap): things explicitly written in the drama academy curriculum but missing from the flow:
      · genre card invalid (UI genre name does not match craft library card name) → the "craft" of all roles degrades to
        **the first three items in shelf-file order**;
      · each role reads the wrong books (the script supervisor gets the playwright's writing hints);
      · McKee/Baker's "one scene one turn" only exists in the prompt, **nobody verifies it**;
      · Stanislavski's "the outline in the director's head" (`outline_check`) **was written but has zero calls**.
  C **no outlet**: crew roles' output previously went into no export artifact (`宣发文案.md` is listed in the roster
    as `feeds='export'`, yet nowhere under `export/*` reads it).
How to run: .venv\\Scripts\\python.exe tools/verify_crew_flow.py
Output: assets/screenshots/crew_flow_report.json
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

from verify_ui_common import safe_rmtree                        # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}

#: 一天跑完之后，**每位启用中的职位都应该有产物**（这几份必须落盘）
# [EN] : After a day's run, **every enabled role should have artifacts** (these must be written to
# [EN] disk).
MUST_FILES = ('剧组台账.md', '美术指导.md', '道具单.md', '造型表.md',
              '声音设计.md', '考据笔记.md', '场记报告.md', '语言审校.md',
              '今日总结.md', '宣发文案.md', '当天地图.md', '当日剧本.json',
              # 2026-10-07 新的两位/两件事
              # [EN] 2026-10-07 two new roles / two new things
              '排练记录.md', '当天故事.md')


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


class _EmptyDB:
    """最小假 DB（**模块级** —— 写在函数里会被 `from … import` 的名字遮蔽）。
        English:
    Minimal fake DB (**module-level** —— written inside a function it gets shadowed by names from
    `from … import`).
    """

    def __getattr__(self, name):
        def _f(*a, **k):
            return [] if name.startswith(('get', 'recent', 'retrieve', 'list')) \
                else None
        return _f


class _CaptureLLM:
    """抓包用的假 router：记下**真正发出去的 messages**。

    ⚠ 桩要模仿的是"这个函数的**全部可观察行为**"，不只是返回值 ——
      `decide()` 用的是 `return_meta=True`，所以这里必须回 `(text, meta)` 二元组。
    
        English:
    Fake router for capturing packets: records the **messages actually sent out**.
        ⚠ What the stub must imitate is "the **full observable behavior** of this function", not just the return value ——
          `decide()` uses `return_meta=True`, so here it must return a `(text, meta)` 2-tuple.
    """

    def __init__(self, reply: str = '{"动作": "wait", "理由": "看看"}'):
        self.reply = reply
        self.seen: list[str] = []

    async def chat(self, tier, messages, **kw):
        self.seen.append('\n'.join(str(m.get('content') or '') for m in messages))
        return self.reply, {'truncated': False, 'max_tokens': 8000,
                            'tin': 1, 'tout': 1}


# ══════════════════════════════════════════════════════════════════
#  一天的真实夹具（跑一遍 _crew_prep → _compose_day → 若干拍 → _crew_wrap）
# [EN] A day's real fixture (run _crew_prep → _compose_day → several beats → _crew_wrap)
# ══════════════════════════════════════════════════════════════════
def _run_one_day(tmp: Path):
    """跑一天，返回 `(loop, world, db, run, tmp)`。**真的跑**，不是读源码。
        English:
    Run a day, return `(loop, world, db, run, tmp)`. **Really run**, do not read the source.
    """
    from verify_run_control import make_project
    from store.runfolder import RunFolder
    from sim import setup as SU
    proj = make_project(tmp / '审计剧组', nodes=3)
    run = RunFolder(proj.root, '第1次模拟2026-10-07-12-00').create()
    loop, world, db = SU.assemble(proj, run, image_hook=lambda *a, **k: None)
    lines: list[str] = []
    loop.on_narrative(lambda t, p, **kw: lines.append(str(t)))
    loop._current_day = 1
    # ⚠ **这里原来有一句光秃秃的 `asyncio.get_event_loop()`** —— 那是个没用完的
    #   遗留（没有赋值、也不返回给任何地方），却是个**定时炸弹**：
    #   Python 3.13 里 `asyncio.run()` 跑完会把当前 loop 置空，于是**第二次**
    #   调本夹具就 `RuntimeError: There is no current event loop`。
    #   A 组是第一次调（那时还没 run 过）所以一直没炸；F 组第二次调就炸在这儿。
    #   ⇒ 删掉它（真要预检也该用 `asyncio.new_event_loop()`）。
    # [EN] ⚠ There used to be a bare `asyncio.get_event_loop()` here -- an unfinished leftover (no
    # [EN] assignment, not returned anywhere), and a **time bomb**: in Python 3.13, `asyncio.run()` clears
    # [EN] the current loop when it finishes, so the **second** call to this fixture raises
    # [EN] `RuntimeError: There is no current event loop`. Group A was the first call (nothing had run
    # [EN] yet) so it never blew up; group F, the second call, blew up right here.
    # [EN] ⇒ Delete it (a real pre-check should use `asyncio.new_event_loop()` anyway).
    return proj, run, loop, world, db, lines


async def _drive_day(loop, ticks: int = 12) -> None:
    """跑一天：**走 `_open_day()` + `_end_day()`**（与 `run()` 同一条路）。

    ⚠ 别自己把 `_crew_prep`/`_compose_day`/`_crew_wrap` 抄一遍：
      抄一遍的话，`run()` 里新加的一步（这一轮加的"排练"、"当天这一章"）
      在判据里量不到 —— A6 就是这么红的（少了 `当天故事.md`）。
    
        English:
    Run a day: **go through `_open_day()` + `_end_day()`** (the same path as `run()`).
        ⚠ Don't copy `_crew_prep`/`_compose_day`/`_crew_wrap` yourself:
          If you copy them, a newly added step in `run()` (the "rehearsal", "that day's chapter" added this round)
          won't be measured by the criteria —— that's exactly how A6 went red (missing `当天故事.md`).
    """
    await loop._open_day()
    for i in range(1, ticks + 1):
        await loop._tick(i)
    await loop._end_day()


# ══════════════════════════════════════════════════════════════════
#  A —— 接线：每人每天都真的出工吗
# [EN] A —— wiring: does everyone really go to work every day
# ══════════════════════════════════════════════════════════════════
def test_wiring(tmp: Path) -> None:
    from crew import roster as R
    from crew import agents as A
    from crew import studio as ST

    ok('A1 名册与在位者一一对应（15 位，没有"名册上有人、程序里没有"）',
       not A.missing_members(),
       f'{len(R.ROSTER)} 位 · 缺 {A.missing_members() or "无"}')
    ok('A2 每条 hook 都解析得到（对接到软件架构的唯一凭据）',
       not R.audit_hooks(), str(R.audit_hooks() or '全部命中'))

    proj, run, loop, world, db, lines = _run_one_day(tmp)
    asyncio.run(_drive_day(loop))

    led = {r['key']: r for r in loop.studio.ledger()}
    # ★ 2026-10-16：台账现在会把「演员」按在场角色展开成**角色子 Agent**
    #   （`actor::{角色名}` 子条目），所以台账键**不止**名册那几位。这里把
    #   判据改成"名册上的每一位都**在**台账里"（子集），不再要求"只有"名册几位。
    # [EN] ★ 2026-10-16: the ledger now expands "actor" into per-character sub-agents
    # [EN] (`actor::{name}` sub-entries), so ledger keys are **more than** just the roster. Change the
    # [EN] criterion to "every roster member is **in** the ledger" (subset), not "only the roster".
    ok('A3 台账列全了名册上的每一位（角色级；角色子 Agent 会额外挂上，'
       '所以用子集判而非全等）',
       {r.key for r in R.ROSTER} <= set(led),
       f'台账 {len(led)} 行 · 名册 {len(R.ROSTER)} 位')

    # ★★ 这一条是整支脚本的核心：**每位启用中的职位都必须真的出过工**。
    #    "声音 0/0、语言审校 0/0" 就是审计发现的原样。
    # [EN] ★★ This is the core of the whole script: **every enabled role must have actually worked**.
    # [EN] "sound 0/0, language review 0/0" is exactly as the audit found it.
    # ⚠ 2026-10-16：角色子 Agent（`is_sub`）**不走 `studio.call`**，没有 runs 计数，
    #   不算"没出工"——它们是演员每拍驱动的角色，本来就不在出工台账里记次。
    # [EN] ⚠ 2026-10-16: character sub-agents (`is_sub`) do **not** go through `studio.call`,
    # [EN] so they have no run count and must not be flagged "didn't work" -- they are characters
    # [EN] driven by the actor each beat and simply aren't counted in the work ledger.
    silent = [k for k, r in led.items()
              if not r.get('is_sub') and r['state'] != 'off'
              and int(r.get('runs') or 0) <= 0]
    ok('A4 ★★ 每位启用中的职位都真的出工了（不是"待命 0/0"）',
       not silent,
       '没出工的：' + '、'.join(f"{led[k]['name']}({k})" for k in silent)
       if silent else f'{len([r for r in led.values() if r["state"] != "off"])} 位全部出工')

    failed = [k for k, r in led.items() if int(r.get('fails') or 0) > 0]
    ok('A5 没有职位在"报错出工"（fails 全 0）',
       not failed, str([(led[k]['name'], led[k]['fails']) for k in failed]))

    got = {(run.root / f).name for f in MUST_FILES if (run.root / f).is_file()}
    miss = [f for f in MUST_FILES if f not in got]
    ok('A6 ★★ 各职位的产物都真的落盘了（14 份，一份不漏）',
       not miss, f'缺：{miss}' if miss else f'{len(got)} 份')

    # 关掉几位 → 台账必须说"未启用"，而不是"待命"（两者是两件事）
    # [EN] Turn off a few roles → the ledger must say "not enabled", not "standby" (the two are different
    # [EN] things)
    CFG.set('CREW_SOUND', 'false')
    CFG.set('CREW_POLISH', 'false')
    off = {r['key']: r['state'] for r in loop.studio.ledger()}
    CFG.set('CREW_SOUND', 'true')
    CFG.set('CREW_POLISH', 'true')
    ok('A7 关掉的职位显示"未启用"（与"待命"分得开）',
       off.get('sound') == 'off' and off.get('polisher') == 'off',
       f'sound={off.get("sound")} polisher={off.get("polisher")}')

    # 造型/声音的下游：算出来了还得**送得到**
    # [EN] Styling/sound downstream: once computed, it must still be **delivered**
    ok('A8 ★★ 造型真的交到了演员手上（`world.stylist_brief` 非空）',
       bool(str(getattr(world, 'stylist_brief', '') or '').strip()),
       str(getattr(world, 'stylist_brief', ''))[:60].replace('\n', ' '))
    ok('A9 ★★ 声音真的进了场景（`world.sound_design` 有底噪）',
       bool((world.sound_design or {}).get('底噪')),
       str(world.sound_design or {})[:70])
    ok('A10 ★★ 造型进了出图提示词（`image_prefix` 含「人物形象」）',
       '人物形象' in loop.studio.image_prefix(),
       loop.studio.image_prefix()[:70])
    ok('A11 ★ 导演大纲被真的算过（`outline_note` 非空）',
       '进度' in str(getattr(world, 'outline_note', '') or ''),
       str(getattr(world, 'outline_note', '')))

    safe_rmtree(tmp / '审计剧组', ignore_errors=True)


# ══════════════════════════════════════════════════════════════════
#  B —— 类型卡：界面上的题材名必须找得到工艺库那张卡
# [EN] B —— genre card: the genre name in the UI must find that card in the craft library
# ══════════════════════════════════════════════════════════════════
def test_genre_card() -> None:
    from craft import craftmix
    from gui import app_flet as G

    choices = [v for v in getattr(G, 'GENRE_CHOICES', ()) if v and v != 'auto']
    dead = [v for v in choices if craftmix.card(v) is None]
    ok('B1 ★★ 开卷向导里**每一个**题材都找得到类型卡（不是返回 None）',
       not dead, f'找不到卡的：{dead}' if dead else f'{len(choices)} 个题材全命中')

    c = craftmix.card('悬疑·单元') or {}
    ok('B2 ★★ 「悬疑·单元」命中 `悬疑灵异` 卡（别名表生效）',
       c.get('类型') == '悬疑灵异', str(c.get('类型')))

    genres = set(craftmix.load()['genres'])
    bad_alias = {k: v for k, v in craftmix.GENRE_ALIAS.items() if v not in genres}
    ok('B3 别名表里每条都指向真实存在的类型卡（不是指向空气）',
       not bad_alias, str(bad_alias or craftmix.GENRE_ALIAS))

    # 别名只救 `card()` 是不够的 —— 曲线 / 高潮间隔 / 映射都得跟着活过来
    # [EN] Aliasing only `card()` is not enough —— curve / climax interval / mapping must all come alive
    # [EN] too
    ok('B4 ★★ 别名一命中，张力曲线与高潮间隔也回来了（不只是 card 非空）',
       bool(craftmix.card_curve('悬疑·单元'))
       and craftmix.card_climax_days('悬疑·单元') > 0,
       f"curve={craftmix.card_curve('悬疑·单元')} "
       f"climax={craftmix.card_climax_days('悬疑·单元')}")

    ok('B5 ★ 类型卡里的 `playbook映射` 能落到这个题材上（不再是空映射）',
       bool((c.get('playbook映射') or [])),
       str(c.get('playbook映射')))


# ══════════════════════════════════════════════════════════════════
#  C —— 工艺：每个职位读的书要对口
# [EN] C —— craft: each role must read the right books
# ══════════════════════════════════════════════════════════════════
def test_craft_by_role() -> None:
    from crew import agents as A
    from craft import craftmix
    entries = craftmix.load()['entries']

    bad: list[str] = []
    for key, names in A.READS.items():
        shelves = A.SHELVES.get(key, ())
        for n in names:
            e = entries.get(n)
            if e is None:
                bad.append(f'{key}→{n}（条目不存在）')
            elif str(e.get('_货架') or '') not in shelves:
                bad.append(f'{key}→{n}（不属于它声明的货架）')
    ok('C1 ★★ `READS` 点名的条目都存在、且**属于该职位声明的货架**（不许跨架点名）',
       not bad, '；'.join(bad) if bad else f'{len(A.READS)} 个职位')

    all_shelved = [k for k in A.SHELVES]
    ok('C2 每个有货架的职位都点名了要读哪几条（不留"随手抽三本"的位子）',
       all(k in A.READS for k in all_shelved),
       str([k for k in all_shelved if k not in A.READS]))

    # ★ 场记：它的活儿是"每场有没有落点、谁在场上"，该读「一场一转变」。
    #   审计前它拿到的是**货架文件顺序前三条**（剧作者的写作提示）。
    # [EN] ★ Script supervisor: its job is "does each scene have a beat, who is on stage", so it should
    # [EN] read "one scene one turn".
    # [EN] Before the audit it got the **first three items in shelf-file order** (the playwright's writing
    # [EN] hints).
    # ★★★ 2026-10-18 晚：C3–C8 **全部改成"可达并集"**（口径跟着动态映射改）。
    #   原来每条都判「**一次** `craft_block` 里必须出现某条目」—— 调度器按
    #   （时机 × 品级 × 拍数）挑之后，任何一条都可能这一拍不被选中 ⇒ 必然假红。
    #   ⚠ 守的事没变：**这个职位在这本书里读得到那一行的手艺**。
    #     判"5 个时机 × 12 拍并集里出现过"，比原来更强（原来只证明某一次拼装里有）。
    #   ⚠ 成对：C4 守"仍然限流"（单次只给额度内几条），防"为了过这些而一次全给"。
    # [EN] ★★★ 2026-10-18 evening: C3-C8 **all switched to the reachable union** (the rule follows
    # [EN] dynamic dispatch). Each used to require an entry in **one** `craft_block` call; after the
    # [EN] dispatcher picks by (moment x grade x tick), any entry may be skipped that beat (inevitable
    # [EN] false red). ⚠ What they guard is unchanged: **this role can read that line of craft in this
    # [EN] book.** ⚠ Paired with C4, which now guards "still rate-limited".
    def _reach(k: str, genre: str = '悬疑·单元') -> set[str]:
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
                    blk = A.craft_block(k, genre)
                finally:
                    A._reset_world()
                out |= {ln[1:ln.index('〕')] for ln in blk.splitlines()
                        if ln.startswith('〔')}
        return out

    _r = {k: _reach(k) for k in ('continuity', 'sound', 'polisher', 'screenwriter')}
    ok('C3 ★★ 场记读到的是连戏/落点那几条（含「一场一转变」）',
       '一场一转变' in _r['continuity'], f"可达 {len(_r['continuity'])} 条")

    # C4 换成"仍然限流"（原来那句"不是货架前三条"在动态映射下已经没有意义：
    #   调度器本来就不按文件顺序取）。
    # [EN] C4 now guards "still rate-limited"; the old "not the first three in shelf order" phrase is
    # [EN] meaningless under dynamic dispatch (it never picks by file order).
    from world.state import WorldState as _WQ

    _wq = _WQ()
    _wq.beat_tick = 5
    _wq.beat_moment = '冲突'
    _wq.craft_level = '重'
    A.bind_world(_wq)
    try:
        _n_one = sum(1 for ln in A.craft_block('continuity', '悬疑·单元').splitlines()
                     if ln.startswith('〔'))
    finally:
        A._reset_world()
    ok('C4 ★★ 场记单次**只给额度内几条**（限流还在，不是把整架书摊开）',
       1 <= _n_one <= 8, f'{_n_one} 条')

    ok('C5 ★ 声音读到「以声写静」（它这一行的手艺）',
       '以声写静' in _r['sound'], '')
    ok('C6 ★ 语言审校读到「文气」（字法那一条）',
       '文气' in _r['polisher'], '')
    ok('C7 ★ 剧作者读到「可拍性检查」与「一场一转变」（可拍与转变是他这一行的底线）',
       '可拍性检查' in _r['screenwriter'] and '一场一转变' in _r['screenwriter'], '')

    # 没有类型卡时手艺也不能缺位（老项目 / 分类失败时）
    # [EN] Craft must not be absent when there is no genre card (old projects / classification failure)
    ok('C8 没有类型卡时照样读得到点名的那几条（手艺不缺位）',
       '一场一转变' in _reach('continuity', ''), '')

    # ★ 这两条新条目真的进了库（不是只写在注释里）
    # [EN] ★ These two new entries really made it into the library (not just written in comments)
    ok('C9 ★ 新加的两条手艺真的在库里（`以声写静` / `文气`）',
       '以声写静' in entries and '文气' in entries,
       f"{entries.get('以声写静', {}).get('_货架')} / "
       f"{entries.get('文气', {}).get('_货架')}")


# ══════════════════════════════════════════════════════════════════
#  D —— 下游：算出来了，还得真的用上（全部走行为）
# [EN] D —— downstream: once computed, it must really be used (all via behavior)
# ══════════════════════════════════════════════════════════════════
def test_downstream(tmp: Path) -> None:
    from crew import studio as ST
    from crew.agents import CrewNote, SetCtx
    from world.state import WorldState, PersonState

    # D1 造型 → 演员的提示词里真的出现 `[你身上]`
    # [EN] D1 styling → `[你身上]` really appears in the actor's prompt
    w = WorldState(scene='临河茶肆')
    w.add_person(PersonState('主角'))
    w.stylist_brief = '【你身上（造型定的，别改）】\n- 主角：洗得发白的靛布短褂'
    from agent.core import Agent
    # ⚠ 构造签名是 `(ps, db, world)` —— 顺序容易记反（第一版写成
    #   `(world, db, ps)`，跑到 `self.db.retrieve_memory` 才炸）。
    # [EN] ⚠ The constructor signature is `(ps, db, world)` —— easy to remember the order backwards (the
    # [EN] first version wrote
    # [EN] `(world, db, ps)`, and only blew up at `self.db.retrieve_memory`).
    ag = Agent(_person('主角'), _EmptyDB(), w)
    cap = _CaptureLLM()
    import agent.core as AC
    old = AC.llm
    AC.llm = cap
    try:
        asyncio.run(ag.decide())
    finally:
        AC.llm = old
    prompt = cap.seen[-1] if cap.seen else ''
    ok('D1 ★★ 造型进了人物的决策提示词（`[你身上]` 真的出现在发出去的请求里）',
       '[你身上]' in prompt and '靛布短褂' in prompt,
       f'{len(prompt)} 字' if prompt else '（没抓到请求）')

    # D2 声音 → 全场无事时写的是**今天那一声**，不是罐头池
    # [EN] D2 sound → when the whole scene is uneventful, what is written is **today's sound**, not the
    # [EN] canned pool
    from display import scene_builder as SB
    from display import script as S
    w2 = WorldState(scene='临河茶肆')
    w2.sound_design = {'底噪': '檐水一滴一滴落在石窝里',
                       '事件声': ['算盘被手肘碰了一下'], '静默': ''}
    b = SB.SceneBuilder(w2, day=1)
    # ⚠ 先给这一幕一条**真正的戏**（台词）—— `observe_quiet` 有前置条件：
    #   全是机制标注（NOTE）的幕它直接返回（"幕里什么都没发生"不值得写氛围）。
    #   第一版只丢了一条 `note`，于是 D2/D3 两条一起假红。
    # [EN] ⚠ First give this scene a **real piece of drama** (dialogue) —— `observe_quiet` has a
    # [EN] precondition:
    # [EN] A scene that is all mechanical annotations (NOTE) makes it return directly ("nothing happened in
    # [EN] the scene" is not worth writing ambience for).
    # [EN] The first version dropped only one `note`, so both D2/D3 falsely went red together.
    b.observe_speech('主角', '这账不对。')
    b.observe_quiet()
    ents = b.recent_entries(99)
    amb = [e for e in ents if getattr(e, 'kind', '') == S.AMBIENT]
    # ★★ 2026-10-18 晚：判"**声音设计被用上了**"，不是"**必须抽到底噪**"。
    #   上一轮把声音层从"底噪+事件声+静默捆成一条"改成"三样各自成句、轮换、不重复"，
    #   于是这一拍可能抽到事件声（实测就是"算盘被手肘碰了一下"）——
    #   原来那条"必须出现底噪那句话"就成了对**旧实现**的断言（必然假红）。
    #   ⚠ 守的事没变：这一句是**今天这一场的声音设计**，不是罐头池里那句通用氛围。
    #   ⚠ 成对：下面同时判"不是默认池里的句子"，防"随便写一句也算用上了"。
    # [EN] ★★ 2026-10-18 evening: judge "**the sound design was used**", not "**the room tone must be
    # [EN] drawn**". The previous round split the sound layer from "room tone + event + silence as one
    # [EN] line" into "three separate phrases, rotated, non-repeating", so this beat may draw the event
    # [EN] sound (measured: "the abacus knocked by an elbow") -- the old check asserted the **previous
    # [EN] implementation** and therefore went red by construction. ⚠ What it guards is unchanged: this
    # [EN] sentence comes from **today's sound design**, not from the canned ambient pool. ⚠ Paired below
    # [EN] with "not a default-pool sentence".
    _amb_txt = str(getattr(amb[-1], 'text', '')) if amb else ''
    _design_hit = ('檐水' in _amb_txt) or ('算盘' in _amb_txt)
    _canned_hit = any(s in _amb_txt for v in SB._AMBIENT.values() for s in v[:2])
    ok('D2 ★★ 声音设计真的被用来写环境句（这一句来自**今天这一场的声音设计**：'
       '底噪或事件声都算）',
       bool(amb) and _design_hit, _amb_txt[:50] if amb else '（没有环境句）')
    ok('D2b ★★ 成对：这一句**不是默认池**里那句罐头氛围'
       '（否则"用上了声音设计"这句话就证明不了什么）',
       bool(amb) and not _canned_hit, _amb_txt[:50])

    # D3 拿不到声音设计 → 退回默认池（**不许因此空场**）
    # [EN] D3 cannot get the sound design → fall back to the default pool (**must not go silent because of
    # [EN] this**)
    w3 = WorldState(scene='临河茶肆')
    b3 = SB.SceneBuilder(w3, day=1)
    b3.observe_speech('主角', '这账不对。')
    b3.observe_quiet()
    amb3 = [e for e in b3.recent_entries(99) if getattr(e, 'kind', '') == S.AMBIENT]
    ok('D3 没有声音设计时退回默认环境池（仍然出环境句，不空场）',
       bool(amb3), str(getattr(amb3[-1], 'text', ''))[:40] if amb3 else '（空）')

    # D4 宣发/剧组产出有了出口：运行报告里能列出它们
    # ⚠ 要走**真实路径** `overview_block()`，不能直接调 `crew_archive_block()` ——
    #   直接调的话，把 `overview_block` 里那行接线删掉这条判据照样绿
    #   （反例法第一次跑就是这么栽的：变异⑩ "没红"）。
    # [EN] D4 promotion/crew output has an outlet: the run report can list them
    # [EN] ⚠ Must go through the **real path** `overview_block()`, cannot call `crew_archive_block()`
    # [EN] directly ——
    # [EN] If called directly, deleting that line of wiring in `overview_block` would still leave this
    # [EN] criterion green
    # [EN] (This is how the counterexample approach failed the first time: mutation ⑩ "did not go red").
    from export import outputs as O
    run = _fake_run(tmp)
    (run.root / '宣发文案.md').write_text(
        '# 宣发\n\n> 第 1 天 · 已出工\n\n**账上少了七文**\n', encoding='utf-8')
    (run.root / '声音设计.md').write_text(
        '# 声音\n\n> 第 1 天 · 已出工\n\n**底噪** 檐水不断\n', encoding='utf-8')
    facts = {'days': 1, 'last_day': 1, 'chars': 10, 'cast': [], 'events': [],
             'cost': {}}
    blk = O.overview_block(run, facts, None, None)
    ok('D4 ★★ 剧组产出进了运行报告（「1.5 剧组档案」列出宣发文案与声音设计）',
       '剧组档案' in blk and '宣发文案.md' in blk and '声音设计.md' in blk,
       blk.replace('\n', ' ')[:90])
    ok('D5 那一节能认出"谁写的"（职位名，不是 key）',
       '宣发' in blk and '声音' in blk, '')
    ok('D6 没有剧组产物时这一节明说"没有"，不留空白表头',
       '没有留下剧组档案' in O.overview_block(_fake_run(tmp / '空'), facts,
                                              None, None))

    # D7 复盘的提示词里带上了导演大纲
    # [EN] D7 the retrospective prompt includes the director's outline
    w4 = WorldState(scene='临河茶肆')
    w4.outline_note = '进度 1/3；当前站在「节点2」'
    cap2 = _capture_crew_prompt(lambda: asyncio.run(_review_prompt(w4)))
    ok('D7 ★ 复盘拿到了导演大纲（它会照着"现在走到哪"评这一天）',
       '进度 1/3' in cap2 and '大纲' in cap2, cap2[:0] or f'{len(cap2)} 字')

    safe_rmtree(tmp / '空', ignore_errors=True)


def _person(name: str):
    from world.state import PersonState
    ps = PersonState(name)
    ps.role = '前台'
    ps.status = '在场'
    ps.identity = '沈家长子'
    ps.personality = '沉稳'
    ps.catchphrase = '且慢'
    ps.goal = '把事办成'
    ps.secret = '压着一件旧事'
    ps.current_goal = '把事办成'
    return ps


def _fake_run(tmp: Path):
    from store.runfolder import RunFolder
    from store.project import Project
    root = tmp / '报告夹具'
    root.mkdir(parents=True, exist_ok=True)
    proj = Project(root, '报告夹具')
    run = RunFolder(root, '第1次模拟2026-10-07-12-01')
    run.root.mkdir(parents=True, exist_ok=True)
    return run


async def _review_prompt(w) -> None:
    from crew.agents import Reviewer, SetCtx
    await Reviewer().run(SetCtx(world=w, db=_EmptyDB(), day=1, people=['主角']),
                         lines=['主角：水不会说谎。'])


def _capture_crew_prompt(fn) -> str:
    """打桩 `crew.agents.ask`，把它收到的提示词抓回来。

    ⚠ 要打**调用方模块里的那个名字**（`crew.agents.ask`）——
      改 `llm.replies.ask` 对已经 `from … import ask` 过的模块没用。
    
        English:
    Stub `crew.agents.ask` and capture the prompt it receives.
        ⚠ Stub **the name in the caller's module** (`crew.agents.ask`) ——
          changing `llm.replies.ask` has no effect on modules that already did `from … import ask`.
    """
    import crew.agents as CA
    from llm.replies import Reply

    seen: list[str] = []

    async def _fake(tier, messages, **kw):
        seen.append('\n'.join(str(m.get('content') or '') for m in messages))
        return Reply(ok=True, value={'总结': 'x', '问题': [], '修改意见': []},
                     raw='{}', meta={})

    old = CA.ask
    CA.ask = _fake
    try:
        fn()
    finally:
        CA.ask = old
    return seen[-1] if seen else ''


# ══════════════════════════════════════════════════════════════════
#  E —— 理论落地：一场一转变 与 导演大纲
# [EN] E —— theory landing: one scene one turn and the director's outline
# ══════════════════════════════════════════════════════════════════
def test_theory() -> None:
    from director.day_plan import DayScript

    ds = DayScript(day=1, beats=[
        {'拍': 1, '场': '堂内', '发生': '账本对不上', '推进': '从没事到起疑'},
        {'拍': 2, '场': '堂内', '发生': '有人来敲门', '推进': ''},
        {'拍': 3, '场': '门口', '发生': '伞不见了', '推进': '从起疑到确认'},
    ])
    ok('E1 ★★ 「一场一转变」验收：没写 `推进` 的拍被点出来（第 2 拍）',
       ds.flat_beats() == [2], str(ds.flat_beats()))
    ok('E2 每一拍都有转变时报空表（不是恒报）',
       DayScript(day=1, beats=[{'拍': 1, '发生': 'x', '推进': 'y'}]).flat_beats() == [],
       '')
    ok('E3 没有分拍时也安全（空表，不抛）',
       DayScript(day=1).flat_beats() == [], '')

    # 导演验算的自审清单里必须有这一条（打桩抓提示词，别查源码）
    # [EN] The director's self-check list must include this item (stub and capture the prompt, do not
    # [EN] inspect the source)
    prompt = _capture_dayplan_prompt()
    ok('E4 ★★ 导演验算的自审里带着「一场一转变」这一问',
       '一场一转变' in prompt, f'{len(prompt)} 字')
    ok('E5 ★ 验算提示词里也点明了"点名那一拍"（删不删交给作者）',
       '可以删' in prompt or '点名' in prompt, '')

    # 大纲：内容与场景都真的取得到
    # [EN] Outline: both content and scenes are really retrievable
    from director import supervisor as SUP
    from world.state import WorldState
    w = WorldState()
    w.progress_nodes = [{'id': 'N01', '名称': '开局', '状态': '已完成'},
                        {'id': 'N02', '名称': '旧案浮出', '状态': '未开始'}]
    w.current_node = 'N02'
    line = SUP.outline_check(w, today_beats=4)
    ok('E6 ★★ `outline_check` 给得出"现在走到哪、今天排几拍"',
       '进度' in line and '旧案浮出' in line and '4 拍' in line,
       line)


def _capture_dayplan_prompt() -> str:
    """打桩 `director.day_plan.ask`，抓 `_verify` 那次自审的提示词。
        English:
    Stub `director.day_plan.ask` and capture the prompt from that `_verify` self-review.
    """
    import director.day_plan as DP
    from llm.replies import Reply

    seen: list[str] = []

    async def _fake(tier, messages, **kw):
        seen.append('\n'.join(str(m.get('content') or '') for m in messages))
        return Reply(ok=True, value={'通过': True, '问题': [], '修改意见': ''},
                     raw='{}', meta={})

    class _W:
        game_day = 1
        current_node = 'N01'
        worldview_text = '临河小城'
        progress_nodes: list = []

        def clock(self):
            return None

    old = DP.ask
    DP.ask = _fake
    try:
        asyncio.run(DP._verify(_W(), _EmptyDB(), '今天的样章',
                              [{'拍': 1, '场': '堂内', '发生': 'a', '推进': 'b'}],
                              {}))
    finally:
        DP.ask = old
    return seen[-1] if seen else ''


# ══════════════════════════════════════════════════════════════════
#  F —— 语言审校的**出口**与**下游**（2026-10-12）
# [EN] F —— the language review's **outlet** and **downstream** (2026-10-12)
# ══════════════════════════════════════════════════════════════════
class _CaptureRouter:
    """包住真 router：记下**发出去的 messages**，再把调用原样转发过去。

    ⚠ 桩要模仿"这个函数的**全部可观察行为**"（本项目的规矩）：
      所以不是"返回一个假应答"，而是**转发给真的那个**、只顺手抄一份 ——
      这样 `tier` / `json_mode` / `max_tokens` 这些参数一个都不用我编。
    
        English:
    Wrap the real router: record the **messages sent out**, then forward the call unchanged.
        ⚠ A stub must imitate "the **full observable behavior** of this function" (the house rule):
          so it does not "return a fake reply" but **forwards to the real one** and just copies a record
          —— this way none of `tier` / `json_mode` / `max_tokens` has to be invented.
    """

    def __init__(self, real):
        self.real = real
        self.seen: list[str] = []

    async def chat(self, tier, messages, **kw):
        self.seen.append('\n'.join(str(m.get('content') or '') for m in messages))
        return await self.real.chat(tier, messages, **kw)

    def __getattr__(self, name):
        return getattr(self.real, name)


def test_polish_outlet(tmp: Path) -> None:
    """F 组：语言审校**并进今日总结** + **喂给下一天的剧作者**。

    用户 2026-10-12 的原话：「每天最后的语言审校**为何都是放到一个 md**，
    而不是输出出来」。查下来：正文只在 `语言审校.md` 里，中栏只有一句
    "细节在「语言审校.md」"，全软件只有**复盘**一份以正文上屏。
    用户拍板：**并进今日总结** + **把下游（下一天的剧作者）真的接上**。

    [EN] Group F: the language review **merged into today's summary** + **fed to the next day's
    [EN] screenwriter**.
    [EN] The user's words on 2026-10-12: "why is the day's final language review **always put into an
    [EN] md** instead of being output". What we found: the body only lived in `语言审校.md`, the middle
    [EN] column only said "details in 语言审校.md", and in the whole app only **the retrospective**
    [EN] reaches the screen as content. The user decided: **merge into today's summary** + **really wire
    [EN] up the downstream (next day's screenwriter)**.
    """
    from crew import studio as ST
    from crew.agents import CrewNote

    # MOCK 的语言审校会给出这两句（见 `llm/mock._crew_polish`）——
    # 用它们当"内容真的到了"的证据：**在原文里找得到的片段**。
    # [EN] The MOCK language review gives these two sentences (see `llm/mock._crew_polish`) --
    # [EN] use them as evidence that "the content really arrived": fragments **findable in the original**.
    FRAG = '他深深地叹了一口气'

    proj, run, loop, world, db, lines = _run_one_day(tmp / '出口')
    asyncio.run(_drive_day(loop, ticks=8))

    # ── F1 ★★★ 正文并进了今日总结（中栏那条 + 盘上那份）──
    # [EN] -- F1 ★★★ the body is merged into today's summary (the middle-column entry + the file on disk)
    # [EN] --
    joined = '\n'.join(str(x) for x in lines)
    sum_idx = [i for i, x in enumerate(lines) if '今日总结' in str(x)]
    summary_entry = str(lines[sum_idx[-1]]) if sum_idx else ''
    ok('F1 ★★★ 语言审校点出的原句**并进了中栏那条「今日总结」**'
       '（用户要的"输出出来" —— 光在 md 里他看不见）',
       bool(summary_entry) and FRAG in summary_entry
       and '语言审校' in summary_entry,
       f'{len(summary_entry)} 字' if summary_entry else '（中栏里没有今日总结）')
    daily = (run.root / '今日总结.md')
    dtext = daily.read_text(encoding='utf-8') if daily.is_file() else ''
    ok('F1b ★★ 盘上那份「今日总结.md」里也有（落盘与上屏**同一份正文**，'
       '不是"只在屏幕上改了一下"）',
       FRAG in dtext and '语言审校' in dtext, f'{len(dtext)} 字')

    # ── F2 ★★ 语言审校自己的那份 md 照旧在写（**是加出口，不是改道**）──
    # [EN] -- F2 ★★ the language review's own md is still written (**this adds an outlet, it does not
    # [EN] divert**) --
    pol_md = run.root / '语言审校.md'
    ptext = pol_md.read_text(encoding='utf-8') if pol_md.is_file() else ''
    ok('F2 ★★ 语言审校自己的 `语言审校.md` **照旧在写**（一个字都没少 —— '
       '它是"这份产出自己的档案"，别为了并进总结就把它停了）',
       pol_md.is_file() and FRAG in ptext, f'{len(ptext)} 字')

    # ── F3 ★★★ 下游：**上一天**的意见真的递到了下一天的剧作者 ──
    # [EN] -- F3 ★★★ downstream: **yesterday's** items really reach the next day's screenwriter --
    from director import day_plan as DP
    import llm.replies as _R
    world.game_day = 2                     # 第二天
    # [EN] day two
    old_router = _R.llm
    cap = _CaptureRouter(old_router)
    _R.llm = cap
    try:
        asyncio.run(DP.compose(world, db, people=world.on_stage_names()[:2],
                               studio=loop.studio))
    finally:
        _R.llm = old_router
    hit = [s for s in cap.seen if '昨天语言审校点出的问题' in s]
    ok('F3 ★★★ 上一天语言审校的意见**真的出现在下一天剧作者收到的请求里**'
       '（名册里写着 `feeds="screenwriter"`，而此前**代码里没人读回它**）',
       bool(hit) and FRAG in hit[0],
       f'{len(hit)} 条请求命中 · 共 {len(cap.seen)} 条请求')

    # ── F4 ★★ 不会把"今天自己的"当成"昨天的" ──
    #   `语言审校.md` 每天**覆盖写**，头里那行 `> 第 N 天` 是唯一的凭据。
    # [EN] -- F4 ★★ "today's own" is never mistaken for "yesterday's" --
    # [EN] `语言审校.md` is **overwrite-written** daily; the `> 第 N 天` line in its header is the only
    # [EN] evidence.
    ok('F4 ★★ 读的是**上一天**那一份：`polish_brief(2)` 有货、'
       '`polish_brief(1)`（同一天 ⇒ 那是自己刚写的）**返回空**',
       bool(loop.studio.polish_brief(2)) and not loop.studio.polish_brief(1),
       f"第2天={len(loop.studio.polish_brief(2))} 字 · "
       f"第1天={len(loop.studio.polish_brief(1))} 字")

    # ── F5 ★★ 没查出问题时**不并**（"今天很干净"不该让总结多一节空段）──
    # [EN] -- F5 ★★ when nothing was found it is **not merged** ("today was clean" should not add an
    # [EN] empty section to the summary) --
    clean = CrewNote(role='polisher', ok=True, title='这一稿没有 AI 味',
                     body='> 词表没命中，读下来也没发现机器腔。', data={'核查': ''})
    found = CrewNote(role='polisher', ok=True, title='2 处 AI 味',
                     body='**AI 味重的地方**\n\n- 原句「他缓缓地」\n  改：写动作',
                     data={'问题数': 2})
    failed = CrewNote(role='polisher', ok=False, title='语言审校', why='模型没给结论')
    ok('F5 ★★ 零命中 / 没出活 ⇒ **不并**（`polish_section` 给空串）；'
       '查出问题 ⇒ 并（带一节标题）',
       ST.Studio.polish_section(clean) == ''
       and ST.Studio.polish_section(failed) == ''
       and '语言审校' in ST.Studio.polish_section(found),
       f"clean={len(ST.Studio.polish_section(clean))} · "
       f"found={len(ST.Studio.polish_section(found))}")

    # ── F6 ★★ 中栏那句小消息的指向**随复盘开关走** ──
    #   复盘开着 → 指"下面的今日总结"（作者抬头就能看见）；
    #   复盘关着 → 那份总结根本不存在，只能照旧指 md。
    # [EN] -- F6 ★★ where that middle-column line points **follows the retrospective switch** --
    # [EN] Retrospective on -> points to "today's summary below" (the author sees it right away);
    # [EN] Retrospective off -> there is no summary at all, so it can only point at the md as before.
    note_pol = CrewNote(role='polisher', ok=True, title='2 处 AI 味', body='x',
                        data={'问题数': 2})
    was = CFG.b('CREW_REVIEW')
    got: dict[str, str] = {}
    try:
        for flag, tag in ((True, 'on'), (False, 'off')):
            CFG.set('CREW_REVIEW', 'true' if flag else 'false')
            lines.clear()
            loop._on_crew_note(note_pol)
            got[tag] = '\n'.join(str(x) for x in lines)
    finally:
        CFG.set('CREW_REVIEW', 'true' if was else 'false')
    ok('F6 ★★ 中栏那句"细节在哪儿"**随复盘开关走**'
       '（开着 ⇒ 指向下面的「今日总结」；关着 ⇒ 指向那份 md）',
       '今日总结' in got['on'] and '语言审校.md' not in got['on']
       and '语言审校.md' in got['off'],
       f"开={got['on'][-40:]!r} 关={got['off'][-40:]!r}")


# ══════════════════════════════════════════════════════════════════
def test_stage_budget() -> None:
    """G 组：非阻塞 Agent 的**总预算**制（2026-10-15，用户改过两次口径）。

    背景（两次口径变更，都要钉住）：
      · v1「设个超时比如 300 秒，超时跳过」；
      · v2「我希望加入超时重试」；
      · **v3（本轮）**：用户实测「美术还是 400 多秒没结束」——
        v1+v2 加起来是"每次 300s × 2 次 = 600s"，而用户说的 300 秒是**总共**。
        实据 `logs/nws_临街楼模拟项目_2026_10_15_11_07_52.log`：
        11:08:15 发请求 → 11:13:15 第 1 次超时（**300s，机制本来就是对的**）
        → 11:17:09 **用户手动停止**（534s，他在重试窗口里失去了耐心）。
      ⇒ 现在 `CREW_STAGE_TIMEOUT` = **总预算**，每次窗口 = 剩余预算 ÷ 剩余次数。

    ★ 这一组**用假 member 直接量总耗时**（不猜、不看源码字符串）：
      · G1 钉"总共不超过预算"（这是 v3 的核心，v1/v2 会红）
      · G2 钉"重试真的发生了"（防止为了 G1 把重试去掉）
      · G3 钉"预算内成功就用它"（防止一刀切变成"必然跳过"）
    ⚠ 容差必须**小于**变异幅度：v1/v2 的总耗时是 **6s**（3s×2），
      G1 上界取 **4.5s** —— 差 1.5s，远大于调度误差，所以那条变异必然红。
    [EN] Section G: the non-blocking agents' **total-budget** model (2026-10-15; the user changed the
    [EN] spec twice). v1 "timeout like 300s, then skip"; v2 "add retries"; **v3 (this round)**: the user
    [EN] found "art still isn't finishing after 400+ seconds" because v1+v2 meant "300s x 2 = 600s",
    [EN] while his "300 seconds" meant **total**.
    [EN] ⇒ `CREW_STAGE_TIMEOUT` is now the **total budget**; each window = remaining budget / remaining
    [EN] attempts.
    [EN] ★ This section **measures elapsed time with a fake member** (no guessing, no source-string
    [EN] checks): G1 pins "never exceeds the budget" (the core of v3; v1/v2 go red), G2 pins "retries
    [EN] really happened" (so G1 can't be satisfied by deleting retries), G3 pins "use it if it succeeds
    [EN] within budget" (so it can't degrade into "always skip").
    [EN] ⚠ Tolerance must be **smaller than the mutation effect**: v1/v2 total 6s (3s x 2), so G1's upper
    [EN] bound is 4.5s -- a 1.5s margin, far above scheduling noise, so that mutation must go red.
    """
    import time as _time
    import types

    from crew import agents as A
    from crew import studio as ST

    _BUDGET, _RETRIES = 3, 1          # 3 秒预算 + 重试 1 次（共 2 次尝试）

    class _FakeMember:
        """假职位：`delays` 是每次调用 sleep 多少秒（超预算就必然超时）。"""

        def __init__(self, delays):
            self.delays = list(delays)
            self.calls = 0
            self.role = types.SimpleNamespace(name='美术')

        async def run(self, ctx, **kw):
            self.calls += 1
            d = self.delays[min(self.calls - 1, len(self.delays) - 1)]
            if d > 0:
                await asyncio.sleep(d)
            return A.CrewNote(role='art', ok=True, title='美术', body='（假产出）')

    orig_member = A.member
    orig_t, orig_r = CFG.raw('CREW_STAGE_TIMEOUT'), CFG.raw('CREW_STAGE_RETRIES')
    ctx = types.SimpleNamespace(day=1)
    try:
        CFG.set('CREW_STAGE_TIMEOUT', str(_BUDGET))
        CFG.set('CREW_STAGE_RETRIES', str(_RETRIES))

        async def _run(delays):
            fm = _FakeMember(delays)
            A.member = lambda k: fm             # `ST.A` 与 `A` 是同一个模块对象
            st = ST.Studio(types.SimpleNamespace(), None)
            t0 = _time.monotonic()
            note = None
            try:
                note = await st.call('art', ctx)
            except Exception:                   # noqa: BLE001
                pass                            # 尾部落盘等的异常不影响"耗时"这个判据
            return fm, note, _time.monotonic() - t0

        # ① 每次调用都超预算 ⇒ 总耗时必须在**预算内**
        fm1, note1, dt1 = asyncio.run(_run([99.0]))
        report['stage_budget'] = {
            'budget': _BUDGET, 'retries': _RETRIES,
            'worst_total': round(dt1, 2), 'calls': fm1.calls,
            'skipped': (note1 is not None and not note1.ok),
        }
        ok('G1 ★★★ 非阻塞 Agent 的**总耗时不超过预算**'
           f'（{_BUDGET}s 预算 + 重试 {_RETRIES} 次 ⇒ 必须 ≈{_BUDGET}s，'
           '而不是"每次窗口"的 6s —— 用户实测"400 多秒没结束"就是这个）',
           dt1 <= _BUDGET + 1.5,
           f'实际 {dt1:.2f}s（上界 {_BUDGET + 1.5}s；"每次窗口"会是 '
           f'{( _RETRIES + 1) * _BUDGET}s）')

        ok('G2 ★★★ 重试**真的发生了**（不是靠"去掉重试"换来 G1 变绿）',
           fm1.calls == _RETRIES + 1,
           f'尝试了 {fm1.calls} 次（应为 {_RETRIES + 1} 次）')

        ok('G3 ★★ 预算内全部失败 ⇒ **标记为跳过**（不是抛异常、不是空产出）',
           note1 is not None and not note1.ok,
           f'note.ok={getattr(note1, "ok", None)} why={getattr(note1, "why", "")[:40]!r}')

        # ② 第一次超时、第二次立刻成功 ⇒ **用第二次的结果**，且总耗时 < 预算
        fm2, note2, dt2 = asyncio.run(_run([99.0, 0.0]))
        ok('G4 ★★ 预算内**重试成功就用它**（不能一刀切变成"必然跳过"）',
           fm2.calls == 2 and dt2 < _BUDGET + 0.5
           and note2 is not None and note2.ok,
           f'尝试 {fm2.calls} 次 / 耗时 {dt2:.2f}s / ok={getattr(note2, "ok", None)}')

        # ③ 一次就成功 ⇒ **不该重试**（重试是有代价的，不能白烧）
        fm3, note3, dt3 = asyncio.run(_run([0.0]))
        ok('G5 ★★ 一次就成功 ⇒ **不重试**（白烧调用是有代价的）',
           fm3.calls == 1 and dt3 < 2.0
           and note3 is not None and note3.ok,
           f'尝试 {fm3.calls} 次 / 耗时 {dt3:.2f}s')
    finally:
        A.member = orig_member
        for _k, _v in (('CREW_STAGE_TIMEOUT', orig_t),
                       ('CREW_STAGE_RETRIES', orig_r)):
            try:
                CFG.set(_k, '' if _v is None else str(_v))
            except Exception:                                    # noqa: BLE001
                pass


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='nws_crew_flow_'))
    try:
        from verify_ui_common import isolate_projects_dir
        isolate_projects_dir(tmp / 'Projects')
    except Exception:                                            # noqa: BLE001
        pass
    print('\n【A】接线：每位职位都真的出工吗（跑一天看台账）')
    print('\n【B】类型卡：界面题材名找得到工艺库那张卡吗')
    print('\n【C】工艺：每个职位读的书对口吗')
    print('\n【D】下游：算出来了，真的用上了吗')
    print('\n【E】理论：一场一转变 与 导演大纲')
    try:
        print('\n【A】接线' + '─' * 40)
        test_wiring(tmp)
        print('\n【B】类型卡' + '─' * 40)
        test_genre_card()
        print('\n【C】工艺书目' + '─' * 40)
        test_craft_by_role()
        print('\n【D】下游' + '─' * 40)
        test_downstream(tmp)
        print('\n【E】理论落地' + '─' * 40)
        test_theory()
        print('\n【F】语言审校的出口与下游' + '─' * 40)
        test_polish_outlet(tmp)
        print('\n【G】非阻塞 Agent 的总预算超时' + '─' * 40)
        test_stage_budget()
    except Exception:                                            # noqa: BLE001
        traceback.print_exc()
        report['fatal'] = traceback.format_exc()
        # ⚠ 崩溃必须**自己留一条红的** —— 否则"全绿"会和"崩了"共存。
        # [EN] ⚠ A crash must **leave a red of its own** —— otherwise "all green" and "crashed" can coexist.
        ok('Z 判据自己跑通（没被异常打断）', False,
           report['fatal'].splitlines()[-1])
    finally:
        safe_rmtree(tmp, ignore_errors=True)

    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['passed'] = len(checks) - len(bad)
    report['total'] = len(checks)
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'crew_flow_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  剧组流程审计：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
