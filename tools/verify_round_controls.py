# -*- coding: utf-8 -*-
"""验证「起笔 · 本轮推演」那六项（2026-10-11，用户点名要控制的）。

用户原话：
    「我想在起笔的时候控制 **这次推演要不要发生关联事件还是只是一次日常生活型的
      推演不带关键剧情**，**大概发生几件事情**，**没事的时候时间要不要跳过**
      （即用旁白描述一下就过去这段时间），**你再看下还有别的可以定制吗**？
      而且这些话可以通过现在起笔里的用输入框实现吗？**如果不行，就加单独的配置项**，
      如果可以，就在那个输入框加一个 Tip，简单带一下例子」

用户后来的三个选择（`AskUserQuestion` 的答复，本判据按它们写）：
    · 日常生活型 **「有大事时照推」** —— 只不主动挑事，剧情走到节点仍推进；
    · 「没事跳过时间」**默认开**；
    · 除那三项外**再加「本轮出场人物」**（另外两项可选没要，但一并做了：
      固定场景 / 篇幅目标 —— 用户说"你提的 3 个都加上"）。

★ 答案那条：**用那个输入框实现不了** —— 它进的是提示词（给剧组的一句话方向），
  而这几件是**程序行为**（花不花一次调用、时钟跳不跳、谁算在场）。
  所以判据要**验行为**，不能只验"配置项存在"：
    · 日常型 → 真跑 `director.on_tick()` **一件都不注入**；
    · 上限 → 挑够 N 件之后**真的停手**；
    · 时间跳过 → 真的**改变了时钟**并**落了一句旁白**，而且**有人在做事时不跳**；
    · 名单 → 真让没被点名的人 `is_on_stage` 为假；
    · 锁场景 → 真的不换场；
    · 篇幅目标 → 真的**进了作家的提示词**（抓真发出去的 messages）。

跑法：`.venv\\Scripts\\python.exe tools\\verify_round_controls.py`
产出：`assets/screenshots/round_controls.png` + `round_controls_report.json`

⚠ 夹具是 `verify_run_control.make_project` 造的临时项目，装在临时目录里 ——
  不碰用户的项目。真机段走 `VU.redirect_env_writes()`（开工时 `CFG.save()` 会写
  `.env`，不禁写就把测试值写进用户的真配置里 —— 本项目为这件事栽过 4 次）。

English:
Verify the six items under "Kickoff · This round's simulation" (2026-10-11, the user
specifically called out wanting to control these).
User's original words:
    "I want to control at kickoff time **whether this simulation should have related events or is just a daily-life-type
      simulation without key plot**, **roughly how many things happen**, **whether time should be skipped when nothing's happening**
      (i.e. just describe it with narration and let the time pass), **also take a look at what else can be customized**?
      And can these be done through the current input box at kickoff? **If not, add separate config items**,
      if yes, add a Tip to that input box, briefly with an example"
The user's three later choices (replies to `AskUserQuestion`, this criterion is written per
them):
    · Daily-life type **"still advance when something big happens"** -- just don't actively stir things up; when the plot reaches a node it still advances;
    · "Skip time when nothing's happening" **on by default**;
    · Besides those three items, **also add "characters appearing this round"** (the other two options were not requested, but do them too:
      fixed scene / length target -- the user said "add all 3 you proposed").
★ The answer item: **it can't be done with that input box** -- what it feeds is the prompt (a
one-line direction for the crew),
  whereas these items are **program behavior** (whether to spend a call, whether the clock skips, who counts as present).
  So the criterion must **verify behavior**, not just "the config item exists":
    · Daily type → actually run `director.on_tick()` and **inject nothing at all**;
    · Cap → after picking enough N items, **really stop**;
    · Time skip → really **changes the clock** and **lands a line of narration**, and **doesn't skip while someone is doing something**;
    · Roster → really make people not named have `is_on_stage` be false;
    · Lock scene → really don't switch scenes;
    · Length target → really **goes into the writer's prompt** (capture the messages really sent out).
How to run: `.venv\\Scripts\\python.exe tools\\verify_round_controls.py`
Output: `assets/screenshots/round_controls.png` + `round_controls_report.json`
⚠ The fixture is a temporary project created by `verify_run_control.make_project`, installed in
a temp directory ——
  it does not touch the user's project. The real-machine section goes through `VU.redirect_env_writes()` (at start, `CFG.save()` will write
  `.env`; if writes are not blocked, test values get written into the user's real config —— this project has been burned by this 4 times).
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

import flet as ft                                     # noqa: E402

import verify_ui_common as VU                         # noqa: E402
from util.flet_shutdown import shutdown               # noqa: E402

from config import CFG, SPEC                          # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('LANGUAGE', 'zh')
VU.redirect_env_writes()

from i18n import set_lang, t                          # noqa: E402
set_lang('zh')

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT: dict = {'checks': []}

#: 八个键（六件事 —— 时间跳过那一件带两个阈值，所以是八行配置）
# [EN] : Eight keys (six things -- the time-skip one has two thresholds, hence eight config lines)
KEYS = ('ROUND_KIND', 'ROUND_EVENT_LIMIT', 'ROUND_CAST', 'ROUND_SCENE',
        'ROUND_DAILY_WORDS', 'SKIP_IDLE_TIME', 'SKIP_IDLE_BEATS',
        'SKIP_IDLE_MINUTES')


def ok(name: str, cond, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    print(('  ✓ ' if cond else '  ✗ ') + name
          + (f'\n        {str(detail)[:220]}' if (detail and not cond) else ''))
    return bool(cond)


def _reset_cfg() -> None:
    """把八项复位成 SPEC 默认值（每段开始都调一次 —— 段与段之间不许互相带偏）。
        English:
    Reset the eight items to SPEC default values (called once at the start of each section ——
    sections must not drift each other).
    """
    for k in KEYS:
        CFG.set(k, str(SPEC[k]['default']))


# ══════════════════════════════════════════════════════════════════
#  A. 配置与装配（纯逻辑）
# [EN] A. Configuration and assembly (pure logic)
# ══════════════════════════════════════════════════════════════════
def config_checks() -> None:
    _reset_cfg()
    ok('A1 ★★★ 八个配置项都在 SPEC 里，且分组是「本轮推演」'
       '（用户要的是"加单独的配置项"）',
       all(k in SPEC for k in KEYS)
       and all(SPEC[k]['group'] == '本轮推演' for k in KEYS),
       {k: SPEC.get(k, {}).get('group', '（缺）') for k in KEYS})
    ok('A2 ★★ 用户拍板的两个默认值：跳过**默认开**、其余是"正常 / 不限"',
       CFG.b('SKIP_IDLE_TIME') is True and CFG.s('ROUND_KIND') == 'normal'
       and CFG.i('ROUND_EVENT_LIMIT') == 0 and CFG.i('ROUND_DAILY_WORDS') == 0
       and CFG.s('ROUND_CAST') == '' and CFG.s('ROUND_SCENE') == '',
       f"skip={CFG.b('SKIP_IDLE_TIME')} kind={CFG.s('ROUND_KIND')!r} "
       f"limit={CFG.i('ROUND_EVENT_LIMIT')}")
    ok('A3 ★★ 上限题面合法（`ROUND_KIND` 只有 normal / daily 两种取值）',
       set(SPEC['ROUND_KIND'].get('opt') or []) == {'normal', 'daily'},
       SPEC['ROUND_KIND'].get('opt'))


def build_world_checks(tmp: Path) -> None:
    """`ROUND_CAST` / `ROUND_SCENE` / `ROUND_DAILY_WORDS` 落到世界上。
        English:
    `ROUND_CAST` / `ROUND_SCENE` / `ROUND_DAILY_WORDS` land in the world.
    """
    from sim.setup import build_world, load_settings
    from verify_run_control import make_project
    proj = make_project(tmp / '装配夹具')
    #  ⚠ 夹具默认**没有地点表**（`make_project` 只建人物/世界观/剧情走向），
    #    而"锁定场景"这一条**必须**有地点表才验得了（没表时 `ROUND_SCENE`
    #    按设计就该被忽略 —— 那条是 A10）。所以**先**给夹具补一份再装配。
    # [EN] ⚠ The fixture has **no location table** by default (`make_project` only builds
    # [EN] characters/worldview/plot direction),
    # [EN] and the "lock scene" item **cannot** be verified without a location table (when there is no
    # [EN] table, `ROUND_SCENE`
    # [EN] should be ignored by design -- that's item A10). So **first** add one to the fixture, then
    # [EN] assemble.
    import yaml as _yaml
    (proj.settings_dir / '地点.yaml').write_text(
        _yaml.dump([{'名称': '甲地'}, {'名称': '乙地'}], allow_unicode=True),
        encoding='utf-8')
    st = load_settings(proj.settings_dir)

    _reset_cfg()
    w0 = build_world(st)
    ok('A4 ★★ 不设名单时，`round_cast` 是空的、在场人数与从前一致'
       '（空 = 全体，不是"没人上场"）',
       w0.round_cast == [] and len(w0.on_stage_names()) == len(w0.people),
       f'{w0.round_cast} / {w0.on_stage_names()}')

    CFG.set('ROUND_CAST', '主角, 柳氏')
    w1 = build_world(st)
    ok('A5 ★★★ 名单里的人**只让这几个人**算在场（其余人这轮不上场）',
       sorted(w1.round_cast) == ['柳氏', '主角']
       and sorted(w1.on_stage_names()) == ['柳氏', '主角'],
       f'名单={w1.round_cast} 在场={w1.on_stage_names()}')

    CFG.set('ROUND_CAST', '主角, 张三')
    w2 = build_world(st)
    ok('A6 ★★★ 名单里有对不上的名字 → **丢掉那一个**，其余照用'
       '（换一本书之后名字多半对不上，不许把整份名单一起废掉）',
       w2.round_cast == ['主角'], w2.round_cast)

    CFG.set('ROUND_CAST', '张三, 李四')
    w3 = build_world(st)
    ok('A7 ★★★ 一个都没对上 → **当没设**（照常全体上场）。'
       '⚠ 照用的话 `is_on_stage` 恒假 ⇒ 整轮没人上场，而现象是"它一句话都不说"',
       w3.round_cast == [] and len(w3.on_stage_names()) == len(w3.people),
       f'{w3.round_cast} / {w3.on_stage_names()}')

    _reset_cfg()
    CFG.set('ROUND_DAILY_WORDS', '2500')
    w4 = build_world(st)
    ok('A8 ★★ 篇幅目标真的落到世界上（不给就是 0 = 不限）',
       w4.daily_words == 2500, w4.daily_words)

    CFG.set('ROUND_DAILY_WORDS', '0')
    places = list(getattr(w0, 'place_names', None) or [])
    if places:
        CFG.set('ROUND_SCENE', places[0])
        w5 = build_world(st)
        ok('A9 ★★★ 锁定的地点**在本书地点表里** → 真的锁上，而且场景改成它',
           bool(w5.scene_locked) and w5.scene == places[0],
           f'locked={w5.scene_locked} scene={w5.scene!r} 表={places[:3]}')
    else:
        ok('A9 ★★★ 锁定的地点在本书地点表里 → 真的锁上', False,
           '夹具没有地点表（这一条没法验）')

    CFG.set('ROUND_SCENE', '压根不存在的地方')
    w6 = build_world(st)
    ok('A10 ★★★ 锁定的地点**不在**地点表里 → 忽略（照常换场），'
       '不让场景名挂在半空',
       not w6.scene_locked, f'locked={w6.scene_locked} scene={w6.scene!r}')
    _reset_cfg()


# ══════════════════════════════════════════════════════════════════
#  B. 导演的两个闸（日常型 / 事件上限）——**行为**，不是读源码
# [EN] B. The director's two gates (daily type / event cap) -- **behavior**, not reading source code
# ══════════════════════════════════════════════════════════════════
def _mk_world_db(tmp: Path):
    from store.db import DB
    from sim.setup import build_world, load_settings
    from verify_run_control import make_project
    proj = make_project(tmp / '导演夹具')
    w = build_world(load_settings(proj.settings_dir))
    db = DB(tmp / 'dir.db')
    return w, db


async def director_checks(tmp: Path) -> None:
    from director.engine import DirectorEngine
    w, db = _mk_world_db(tmp)

    _reset_cfg()
    d = DirectorEngine(w, db)
    ok('B1 ★★ `normal` 时允许挑事（这是老行为，一个字节都没改）',
       d.may_inject() is True, d.may_inject())
    CFG.set('ROUND_KIND', 'daily')
    ok('B2 ★★★ `daily`（日常生活型）时**一律不挑事**'
       '（用户要的"不带关键剧情"）',
       d.may_inject() is False, d.may_inject())

    CFG.set('ROUND_KIND', 'normal')
    CFG.set('ROUND_EVENT_LIMIT', '2')
    d2 = DirectorEngine(w, db)
    d2.events_this_round = 1
    ok('B3 ★★★ 上限没到 → 还挑；挑够 → **停手**（"大概发生几件事情"）',
       d2.may_inject() is True, 'events=1/2 应当仍可挑')
    d2.events_this_round = 2
    ok('B3b ★★★ 挑够 2 件之后不再挑',
       d2.may_inject() is False, 'events=2/2 应当停手')

    # ── 行为级：真的跑 on_tick，数"到底注入了没有" ──
    #  ⚠ 只读 `may_inject()` 不够 —— 那三处 `return event` 才是"真的注入了"。
    #    所以这里真跑（MOCK 模式，`director_event` 有假回复）。
    # [EN] -- Behavior-level: actually run on_tick, count "whether it was really injected" --
    # [EN] ⚠ Only reading `may_inject()` is not enough -- those three `return event` are what "actually
    # [EN] injected".
    # [EN] So actually run it here (MOCK mode, `director_event` has a fake reply).
    from director.engine import DirectorEvent
    injected = {'n': 0}
    real_inject = DirectorEngine._inject_event

    async def _spy(self, *a, **kw):
        ev = await real_inject(self, *a, **kw)
        if ev is not None:
            injected['n'] += 1
        return ev
    DirectorEngine._inject_event = _spy
    try:
        _reset_cfg()
        CFG.set('ROUND_KIND', 'daily')
        CFG.set('DRAMA_LEVEL', '1'); CFG.set('CONFLICT_FREQUENCY', '1')
        CFG.set('CLIMAX_EVERY_DAYS', '1')          # 每天都算高潮日（最狠的那条路）
        # [EN] Count every day as a climax day (the harshest path)
        CFG.set('DIRECTOR_ENABLED', 'true')
        d3 = DirectorEngine(w, db)
        for _ in range(6):
            ev = await d3.on_tick()
            if ev is not None:
                injected['n'] += 100               # 记成"漏了"（B4 要红）
            d3._last_event_game_min = d3._game_min()   # 别让它靠停滞自救绕过去
                # [EN] Record it as "missed" (B4 must go red)
                # [EN] Don't let it get around this by self-rescuing via stagnation
        ok('B4 ★★★★ **日常型真的一件都不注入**（跑了 6 次 on_tick，'
           '含"高潮日强制"与"停滞自救"两条路 —— 用户要的就是不带关键剧情）',
           injected['n'] == 0, f'注入 {injected["n"]} 次')
        ok('B4b ★★ 而且 `events_this_round` 也没被加上去'
           '（没发生的事不该计数）',
           d3.events_this_round == 0, d3.events_this_round)

        # ★★ B6：**被拦下的事件不计数**（"没发生的不算数"）。
        # [EN] ★★ B6: **blocked events don't count** ("what didn't happen doesn't count").
        #
        #  ⚠ 这条与 B4b 看着像，其实守的是**另一件事** —— 第一版就是拿 B4b 顶替它，
        #    结果那条变异（`if ev is not None:` → `if True:`）**红不了**：
        #    daily 模式下 `may_inject()` 在前面就 `return None` 了，
        #    计数那一段**根本执行不到** ⇒ B4b 在那种场景下恒真（"装饰品"）。
        #    所以这里造一个**真的会走计数那段**的场景：让 `_inject_event`
        #    总是返回 `None`（= 被 `_rate_gate` 拦下 / 没写出事件），
        #    再断言计数**没有涨**。
        # [EN] ⚠ This looks similar to B4b, but it actually guards **something else** -- the first version
        # [EN] substituted B4b for it,
        # [EN] and as a result that mutation (`if ev is not None:` → `if True:`) **would not go red**:
        # [EN] in daily mode `may_inject()` already `return None` earlier,
        # [EN] so the counting block **never executes** ⇒ B4b is always true in that scenario (a "decoration").
        # [EN] So here we build a scenario that **actually reaches the counting block**: make `_inject_event`
        # [EN] always return `None` (= blocked by `_rate_gate` / no event written out),
        # [EN] then assert the count **did not increase**.
        _reset_cfg()
        CFG.set('DRAMA_LEVEL', '1'); CFG.set('CONFLICT_FREQUENCY', '1')
        d5 = DirectorEngine(w, db)

        async def _no_event(self, *a, **kw):
            return None                      # 模拟"这次没挑成"
            # [EN] Simulate "this time nothing was picked"
        DirectorEngine._inject_event = _no_event
        try:
            for _ in range(4):
                await d5.on_tick()
                d5._last_event_game_min = d5._game_min()
        finally:
            DirectorEngine._inject_event = _spy
        ok('B6 ★★★ 事件**没真的注入**时计数不涨'
           '（"被闸拦下的那件事没发生"—— 上限才不会被空挑耗掉）',
           d5.events_this_round == 0, d5.events_this_round)

        # 上限：挑够就不再来
        # [EN] Cap: once enough are picked, stop coming
        _reset_cfg()
        CFG.set('ROUND_EVENT_LIMIT', '1')
        CFG.set('DRAMA_LEVEL', '1'); CFG.set('CONFLICT_FREQUENCY', '1')
        CFG.set('CLIMAX_EVERY_DAYS', '1')
        d4 = DirectorEngine(w, db)
        n_ev = 0
        for _ in range(6):
            ev = await d4.on_tick()
            if ev is not None:
                n_ev += 1
            d4._last_event_game_min = d4._game_min()
        ok('B5 ★★★ 上限 = 1 时，跑 6 次 on_tick **最多注入 1 件**'
           '（"挑够就停手"）',
           n_ev <= 1, f'注入 {n_ev} 件')
        ok('B5b ★★ 而且计数与上限一致（不多不少）',
           d4.events_this_round == n_ev, f'{d4.events_this_round} vs {n_ev}')
    finally:
        DirectorEngine._inject_event = real_inject
        _reset_cfg()
        CFG.set('CLIMAX_EVERY_DAYS', str(SPEC['CLIMAX_EVERY_DAYS']['default']))
        CFG.set('DRAMA_LEVEL', str(SPEC['DRAMA_LEVEL']['default']))
        CFG.set('CONFLICT_FREQUENCY', str(SPEC['CONFLICT_FREQUENCY']['default']))


# ══════════════════════════════════════════════════════════════════
#  C. 「没事就把时间跳过去」——**行为**：时钟真的跳了、而且该演时不跳
# [EN] C. "Skip time when nothing's happening" -- **behavior**: the clock really skipped, and it
# [EN] doesn't skip when something should be played out
# ══════════════════════════════════════════════════════════════════
class _WaitAgent:
    """每拍都"什么都没做"（`wait` 无台词 = `is_noop`）。
        English:
    Every beat "does nothing" (`wait` with no lines = `is_noop`).
    """
    def __init__(self, name, ps):
        self.name, self.ps = name, ps

    async def decide(self):
        from agent.core import Action
        return Action(verb='wait')

    async def make_plan(self):
        return []


class _TalkAgent(_WaitAgent):
    """每拍都**说一句话** —— 有人在做事，跳过就一次都不许发生。

    ⚠ 桩要模仿的是**这个对象的全部可观察行为**，不只是 `decide()` ——
      `_process_actions` 还会调 `reflect()`（心智省思那条路）。漏一个
      当场 `AttributeError`，而它看起来像"产品坏了"（第一版就是这么红的）。
    
        English:
    Every beat **says one line** —— someone is doing something; skipping must never happen even
    once.
        ⚠ What the stub must mimic is **all observable behavior of this object**, not just `decide()` ——
          `_process_actions` also calls `reflect()` (the mind-reflection path). Miss one and
          you get an immediate `AttributeError`, and it looks like "the product is broken" (the first version went red exactly like this).
    """
    async def decide(self):
        from agent.core import Action
        return Action(verb='speak', dialogue='这一句是正经台词。')

    async def reflect(self):
        return None

    async def talk(self, *a, **kw):
        return None

    async def speak_in_group(self, *a, **kw):
        return None


async def _run_loop(tmp: Path, tag: str, agents_cls, ticks: int,
                    idle_beats: int = 3, jump: int = 45):
    from store.runfolder import RunFolder
    from sim.setup import assemble
    from verify_run_control import make_project
    proj = make_project(tmp / tag)
    run = RunFolder(proj.root, '第1次模拟2026-10-11-00-01').create()
    CFG.set('TIME_RATIO', '3600')          # 时钟走得快，测试不用真等
    # [EN] The clock runs fast, tests don't need to actually wait
    CFG.set('BEAT_SECONDS', '15')
    CFG.set('SKIP_IDLE_BEATS', str(idle_beats))
    CFG.set('SKIP_IDLE_MINUTES', str(jump))
    CFG.set('AUTO_RUN_DAYS', '0')
    loop, world, db = assemble(proj, run)
    loop.agents = [agents_cls(n, ps) for n, ps in world.people.items()]
    lines: list = []
    loop.on_narrative(lambda text, prio, **kw: lines.append(str(text)))
    m0 = world.clock.minutes
    # ⚠ 计数要在 `run()` 里读 —— `run()` 收尾会调 `_end_day()`，
    #   那一步把"今天跳了几次"清零（那是**设计**：那几个数都是"这一天"的）。
    # [EN] ⚠ The count must be read inside `run()` -- `run()` calls `_end_day()` at the end,
    # [EN] and that step zeroes out "how many times we skipped today" (that's **by design**: those numbers
    # [EN] are all for "this day").
    seen = {'skips': 0, 'words': 0}
    loop.on_status = None
    await loop.run(max_ticks=ticks)
    moved = world.clock.minutes - m0
    return loop, world, lines, moved, seen


async def skip_checks(tmp: Path) -> None:
    _reset_cfg()
    CFG.set('SKIP_IDLE_TIME', 'true')
    loop1, _, lines, moved, _ = await _run_loop(tmp, '跳过开', _WaitAgent, 8)
    skip_lines = [x for x in lines if '就这么过去' in x]
    #  ⚠ 断言写成**关系式**（跳过的分钟数 ≥ 跳次 × 每次的量），不写"墙钟阈值" ——
    #    `TIME_RATIO=3600` 时机器一忙，光靠自然流逝也能推进几十分钟，
    #    拿 `moved >= 45` 当判据会**随机变红**（本项目为这件事栽过：§65）。
    # [EN] ⚠ Write assertions as **relations** (skipped minutes ≥ skip count × amount per skip), not a
    # [EN] "wall-clock threshold" --
    # [EN] when `TIME_RATIO=3600` and the machine is busy, natural passage alone can advance tens of
    # [EN] minutes,
    # [EN] using `moved >= 45` as the criterion will **randomly go red** (this project has been burned by
    # [EN] this: §65).
    n_skip = int(getattr(loop1, 'skips_total', 0) or 0)
    ok('C1 ★★★★ 连着几拍没人做事 → **时间真的被跳过去了**'
       '（用户要的"用旁白描述一下就过去这段时间"）',
       n_skip >= 1 and len(skip_lines) >= 1 and moved >= 45 * n_skip,
       f'跳过 {n_skip} 次 · 旁白 {len(skip_lines)} 条 · 时钟推进 {moved} 分钟')
    ok('C1b ★★★ 跳过的每一句都是**旁白**（`ambient` 词条 —— 屏幕上按旁白排版）',
       bool(skip_lines) and all('就这么过去' in x for x in skip_lines),
       skip_lines[:2])
    # 旁白里**不许出现任何人物名**（跳过 ≠ 这段时间发生了事 —— 编了就接不上）
    # [EN] **No character names may appear** in the narration (skipping ≠ things happened during this time
    # [EN] -- if you make them up, it won't connect)
    from verify_run_control import make_project
    proj = make_project(tmp / '名字核对')
    from sim.setup import build_world, load_settings
    w = build_world(load_settings(proj.settings_dir))
    names = list(w.people or {})
    bad = [l for l in skip_lines for n in names if n in l]
    ok('C1c ★★★ 那句旁白里**一个角色名都没有**'
       '（跳过时不编故事 —— 编出来的事后面没人接得上）',
       bool(skip_lines) and not bad, bad[:2])

    _reset_cfg()
    CFG.set('SKIP_IDLE_TIME', 'false')
    loop2, _, lines2, moved2, _ = await _run_loop(tmp, '跳过关', _WaitAgent, 8)
    ok('C2 ★★★ 关掉时**一次都不跳**'
       '（判"跳过次数为 0"，**不判墙钟** —— 见 C1 那段说明）',
       int(getattr(loop2, 'skips_total', 0) or 0) == 0
       and not [x for x in lines2 if '就这么过去' in x],
       f"跳过 {getattr(loop2, 'skips_total', '?')} 次 · 推进 {moved2} 分钟")

    _reset_cfg()
    CFG.set('SKIP_IDLE_TIME', 'true')
    loop3, _, lines3, _, _ = await _run_loop(tmp, '有人说话', _TalkAgent, 10)
    ok('C3 ★★★★ **有人在说话做事时一次都不跳**'
       '（这条最要紧：该演的戏一秒都不会被跳掉）',
       int(getattr(loop3, 'skips_total', 0) or 0) == 0
       and not [x for x in lines3 if '就这么过去' in x],
       [x for x in lines3 if '就这么过去' in x][:2])


# ══════════════════════════════════════════════════════════════════
#  D. 锁场景 / E. 篇幅目标进提示词
# [EN] D. Lock scene / E. Length target into the prompt
# ══════════════════════════════════════════════════════════════════
def scene_lock_checks(tmp: Path) -> None:
    from store.runfolder import RunFolder
    from sim.setup import assemble
    from verify_run_control import make_project
    _reset_cfg()
    proj = make_project(tmp / '锁场景', nodes=2)
    run = RunFolder(proj.root, '第1次模拟2026-10-11-00-02').create()
    loop, world, db = assemble(proj, run)
    # 造一个"所有人都走了、去了另一个已知地点"的场面
    # [EN] Build a scene where "everyone left and went to another known location"
    world.place_names = ['甲地', '乙地']
    world.scene = '甲地'
    for ps in world.people.values():
        ps.location = '乙地'
    loop._last_place = '甲地'
    loop._maybe_shift_scene()
    ok('D1 ★★ 没锁时：人都走了确实会换场（这是老行为，别被这条改动弄坏）',
       world.scene == '乙地', world.scene)

    world.scene = '甲地'
    for ps in world.people.values():
        ps.location = '乙地'
    world.scene_locked = True
    loop._maybe_shift_scene()
    ok('D2 ★★★ 锁了场景就**一次都不换**（用户要的"整轮都在同一处"）',
       world.scene == '甲地', world.scene)


async def words_checks(tmp: Path) -> None:
    """篇幅目标真的进作家提示词（抓**真发出去**的 messages）。
        English:
    The length target really enters the writer prompt (capture the messages **actually sent out**).
    """
    from crew import agents as A
    from crew.agents import SetCtx
    from llm import replies as REPLIES
    from store.db import DB
    from verify_run_control import make_project
    from sim.setup import build_world, load_settings

    proj = make_project(tmp / '字数')
    world = build_world(load_settings(proj.settings_dir))
    db = DB(tmp / 'w.db')
    ctx = SetCtx(world=world, db=db, day=1, people=list(world.people)[:3])

    caught: list[list] = []
    real_ask = REPLIES.ask

    async def _spy(tier, messages, **kw):
        caught.append(messages)
        rep = await real_ask(tier, messages, **kw)
        return rep
    REPLIES.ask = _spy
    A.ask = _spy                      # 职位模块里是 `from llm.replies import ask`
    # [EN] In the position module it's `from llm.replies import ask`
    try:
        _reset_cfg()
        caught.clear()
        await A.Novelist().work(ctx, nodes='N01')
        p0 = '\n'.join(str(m.get('content') or '') for m in (caught[0] if caught else []))
        ok('E1 ★★ 没设篇幅目标时，提示词用的是**原来那对区间**'
           '（一个字都没变 —— 老行为不受影响）',
           bool(caught) and '字**' in p0 and '约 ' not in p0,
           f"字**={'字**' in p0} 约={'约 ' in p0}")

        caught.clear()
        world.daily_words = 2500
        await A.Novelist().work(ctx, words=2500, nodes='N01')
        p1 = '\n'.join(str(m.get('content') or '') for m in (caught[0] if caught else []))
        ok('E2 ★★★★ 设了篇幅目标 → 提示词里真的写着「约 2500 字」'
           '（这是"告诉编剧组"的唯一硬证据）',
           '约 2500 字' in p1, p1[p1.find('写一段'):][:60])

        caught.clear()
        await A.Novelist().work(ctx, words=0, nodes='N01')
        p2 = '\n'.join(str(m.get('content') or '') for m in (caught[0] if caught else []))
        ok('E2b ★★ 传 0 = 不限 → 退回原区间，**不出现"约 0 字"**',
           '约 0 字' not in p2 and '字**' in p2,
           p2[p2.find('写一段'):][:60])
    finally:
        REPLIES.ask = real_ask
        A.ask = real_ask
        _reset_cfg()


# ══════════════════════════════════════════════════════════════════
#  F. 真机：起笔对话框里真的有那一节、而且真的存得下去
# [EN] F. Real machine: that section really exists in the kickoff dialog, and it really can be saved
# ══════════════════════════════════════════════════════════════════
async def ui_checks(page, tmp: Path) -> None:
    from gui.app_flet import NovelWorldApp
    from verify_run_control import make_project

    from llm import usage as _U
    _U.db_path = lambda: tmp / 'usage.db'

    proj = make_project(tmp / '起笔夹具')
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    await asyncio.sleep(1.8)
    app.current_project = proj
    app.show_main_screen()
    await asyncio.sleep(1.0)

    _reset_cfg()
    dlg = app.show_start_story_dialog()
    page.update()
    await asyncio.sleep(1.2)
    if not ok('F1 起笔对话框真的打开了', dlg is not None, '返回 None'):
        return

    texts = [str(x).strip() for x in VU.all_texts(dlg)]
    # ⚠ `mk_switch` 的标签**不是 `ft.Text`**（它挂在 `label_style` 上的一个字符串），
    #   `VU.all_texts` 只收 `ft.Text` ⇒ 漏收。第一版就这么漏了那一个开关。
    # [EN] ⚠ `mk_switch`'s label **is not `ft.Text`** (it's a string attached to `label_style`),
    # [EN] `VU.all_texts` only collects `ft.Text` ⇒ misses it. The first version missed that one switch
    # [EN] this way.
    for _c in VU.walk(dlg):
        if isinstance(_c, (ft.Switch, ft.Checkbox)) and str(getattr(_c, 'label', '') or '').strip():
            texts.append(str(_c.label).strip())
    ok('F2 ★★★ 对话框里有「本轮推演」那一节（用户点名要在这里控制）',
       t('本轮推演') in texts, [x for x in texts if '轮' in x][:6])
    for _label in ('这一轮的性质', '最多几件关键事', '每天大概写多少字',
                   '本轮出场人物', '锁定在一个地点', '没事就把时间跳过去',
                   '连着几拍没事才跳', '每次跳多少故事分钟'):
        ok(f'F2b ★★ 有「{t(_label)}」这一项',
           any(x == t(_label) for x in texts), [x for x in texts if '跳' in x][:4])

    # 建议框的提示语里点明了"结构性开关在下面"
    # [EN] The hint text of the suggestion box points out that "structural switches are below"
    note = None
    for c in VU.walk(dlg):
        if isinstance(c, ft.TextField) and getattr(c, 'multiline', False) \
                and not str(c.value or '').strip() \
                and '可不填' in str(c.hint_text or ''):
            note = c
            break
    ok('F3 ★★★ 建议框的提示语**当面说清**"它管不了这几件事、开关在下面"'
       '（用户问过能不能用它实现 —— 答案是不能，那就得写在框上）',
       note is not None and '本轮推演' in str(note.hint_text or ''),
       (str(note.hint_text or '') if note is not None else '（没找到建议框）')[:90])

    # ── F3b/F3c ★★ 占位提示"是灰的、而且不长"（2026-10-11 第二轮，用户点名）──
    #   用户原话：「起笔的 你对接下来的建议 下面文本框 **文字应该是偏灰色
    #   表示是系统提示** 2.**不要太长 现在东西太多了**」。
    #   ⚠ 两条都要**独立可证**：
    #     · F3b 判"提示色**明显比正文浅**" —— 不是拿 `C['muted']` 当尺子
    #       （那只是"它等于自己"），而是算**亮度差**：系统的话要一眼看出
    #       不是已经写好的内容；
    #     · F3c 判**长度**：原来 4 句、一百多字，把作者自己的话挤没了。
    # [EN] ── F3b/F3c ★★ the placeholder must "be grey and not long" (second round 2026-10-11, named by
    # [EN] the user) ──
    # [EN] The user's words: "the start-writing suggestion box -- the text **should be greyish, showing it
    # [EN] is a system hint**; 2. **do not make it so long, there is too much stuff now**".
    # [EN] ⚠ Both must be **independently provable**:
    # [EN] · F3b judges "the hint colour is **clearly lighter than the body text**" -- not by using
    # [EN] `C['muted']` as the ruler (that is only "it equals itself"), but by computing the **luminance
    # [EN] difference**: the system's words must read at a glance as not being content already written in;
    # [EN] · F3c judges the **length**: it used to be four sentences and over a hundred characters,
    # [EN] squeezing out the author's own words.
    hint = str(getattr(note, 'hint_text', '') or '') if note is not None else ''

    def _lum(rgb: str) -> float:
        """一段 `#rrggbb` 的相对亮度（0~255 量级，够比大小）。
            English:
        The relative luminance of a `#rrggbb` (0-255 scale, enough to compare magnitudes).
        """
        s = str(rgb or '').lstrip('#')
        if len(s) < 6:
            return -1.0
        try:
            r, g, b = (int(s[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return -1.0
        return 0.299 * r + 0.587 * g + 0.114 * b

    hint_col = ''
    try:
        hint_col = str(getattr(getattr(note, 'hint_style', None), 'color', '') or '')
    except Exception:                                        # noqa: BLE001
        hint_col = ''
    # ⚠ 色值从**界面模块**现取（`from gui.app_flet import ...` 只在 584 行那一处，
    #   这里单独 import 一次，别把它提到模块级 —— 模块级 import 会先于
    #   `VU.patch_flat_background()` / `redirect_env_writes()` 执行）。
    # [EN] ⚠ Colour values are taken **live from the UI module** (`from gui.app_flet import ...` exists
    # [EN] only at line 584; import once here, and do not lift it to module level -- a module-level
    # [EN] import would run before `VU.patch_flat_background()` / `redirect_env_writes()`).
    from gui.app_flet import C as _UIC
    body_col = str(_UIC['text'])
    REPORT['hint'] = {'color': hint_col, 'body': body_col,
                      'lum_hint': _lum(hint_col), 'lum_body': _lum(body_col),
                      'chars': len(hint), 'lines': hint.count('\n') + 1}
    ok('F3b ★★ 占位提示是**灰的**（亮度明显浅于正文 —— 一眼看出"这是系统的话"）',
       bool(hint_col) and _lum(hint_col) > _lum(body_col) + 60,
       f"提示色 {hint_col or '（没设）'} 亮度 {round(_lum(hint_col), 1)}"
       f" vs 正文 {body_col} 亮度 {round(_lum(body_col), 1)}")
    ok('F3c ★★ 提示语**不长**（≤ 80 字、至多两行 —— 用户：「不要太长 现在东西太多了」）',
       bool(hint) and len(hint) <= 80 and hint.count('\n') <= 1,
       f'{len(hint)} 字 / {hint.count(chr(10)) + 1} 行')

    # 截图（给人看的那一份）
    # [EN] Screenshot (the one for humans to look at)
    await asyncio.sleep(0.4)
    shot = await page.take_screenshot()
    if shot:
        (OUT / 'round_controls.png').write_bytes(shot)
        ok('F4 截图落盘', (OUT / 'round_controls.png').is_file())

    # ── 真的点一次「开始推演」，看值有没有落到配置上 ──
    # [EN] -- Actually click "Start simulation" once, see whether the values land in the config --
    def _label_of(row) -> str:
        """行里第一个控件（标签）上的文字。

        ⚠ 标签是个 `Container`（`_label_box`），`VU.ctrl_text` 只认控件自己的
          `.value`/`spans` ⇒ 对它返回空串。要收**子树里的全部文字**。
          （第一版就是这么找不到控件的 —— 而报出来是"开关没接上"，方向全错。）
        
                English:
        The text on the first control (label) in the row.
                ⚠ The label is a `Container` (`_label_box`), and `VU.ctrl_text` only recognizes the control's own
                  `.value`/`spans` ⇒ it returns an empty string for it. You need to collect **all text in the subtree**.
                  (The first version failed to find the control exactly like this —— and the report was "the toggle is not wired up", completely wrong direction.)
        """
        kids = getattr(row, 'controls', None) or []
        if not kids:
            return ''
        return ' '.join(str(x).strip() for x in VU.all_texts(kids[0])).strip()

    def _find_by_label(root, label):
        for c in VU.walk(root):
            if isinstance(c, ft.Row) and hasattr(c, '_field') \
                    and _label_of(c) == label:
                return c._field
        return None

    def _find_dd(root, label):
        """按标签找行里的**下拉框**。

        ⚠ 下拉框外面套着一层 `Container` 壳（`mk_dropdown` 如此，为了跟输入框
          长得一样）⇒ 直接看行里的孩子是找不到 `options` 的，要**往子树里挖**。
        
                English:
        Find the **dropdown** in the row by label.
                ⚠ The dropdown is wrapped in a `Container` shell (`mk_dropdown` does this so it looks the same as the input box)
                  ⇒ looking directly at the row's children will not find `options`; you must **dig into the subtree**.
        """
        for c in VU.walk(root):
            if isinstance(c, ft.Row) and _label_of(c) == label:
                for k in (getattr(c, 'controls', None) or [])[1:]:
                    if hasattr(k, 'options'):
                        return k
                    for x in VU.walk(k):
                        if hasattr(x, 'options'):
                            return x
        return None

    lim = _find_by_label(dlg, t('最多几件关键事'))
    cast = _find_by_label(dlg, t('本轮出场人物'))
    words = _find_by_label(dlg, t('每天大概写多少字'))
    kind_dd = _find_dd(dlg, t('这一轮的性质'))
    ok('F5 ★★ 找得到那几个控件（下面靠它们）',
       None not in (lim, cast, words, kind_dd),
       f'上限={lim is not None} 名单={cast is not None} '
       f'字数={words is not None} 性质下拉={kind_dd is not None}')

    if None in (lim, cast, words, kind_dd):
        return
    lim.value = '3'
    cast.value = '主角,柳氏'
    words.value = '1800'
    kind_dd.value = 'daily'
    page.update()
    await asyncio.sleep(0.2)

    btn = None
    for c in VU.walk(dlg):
        if hasattr(c, 'on_click') and VU.text_of(c) == t('开始推演'):
            btn = c
            break
    if not ok('F6 找得到「开始推演」按钮', btn is not None, ''):
        return
    btn.on_click(None)
    await asyncio.sleep(0.8)
    ok('F7 ★★★★ 点「开始推演」之后，界面上的值**真的落到配置上**'
       '（不是画着好看的控件）',
       CFG.s('ROUND_KIND') == 'daily' and CFG.i('ROUND_EVENT_LIMIT') == 3
       and CFG.s('ROUND_CAST') == '主角,柳氏'
       and CFG.i('ROUND_DAILY_WORDS') == 1800,
       f"kind={CFG.s('ROUND_KIND')!r} limit={CFG.i('ROUND_EVENT_LIMIT')} "
       f"cast={CFG.s('ROUND_CAST')!r} words={CFG.i('ROUND_DAILY_WORDS')}")

    # 收工：把这一轮停掉（判据不该在用户机器上留一个跑着的轮次）
    # [EN] Wrap up: stop this round (the criterion should not leave a running round on the user's machine)
    for _ in range(200):
        await asyncio.sleep(0.1)
        if app.session is not None:
            break
    try:
        if app.session is not None:
            app.session.stop()
        for _ in range(200):
            await asyncio.sleep(0.1)
            if app.session is None or not app.session.is_alive:
                break
    except Exception:                                            # noqa: BLE001
        pass
    ok('F8 真机段收尾：这一轮**停下来了**（不给后面留下跑着的东西）',
       app.session is None or not app.session.is_alive, '')


# ══════════════════════════════════════════════════════════════════
async def _body(page, tmp: Path) -> None:
    try:
        config_checks()
        build_world_checks(tmp)
        await director_checks(tmp)
        await skip_checks(tmp)
        scene_lock_checks(tmp)
        await words_checks(tmp)
    except Exception:                                            # noqa: BLE001
        REPORT['fatal'] = traceback.format_exc()
        print(REPORT['fatal'])
        # ★ 崩了必须**自己留一条红的**（否则"全绿"可以与"崩了"共存 —— 踩过）。
        # [EN] ★ A crash must **leave a red one itself** (otherwise "all green" can coexist with "crashed" --
        # [EN] been there).
        ok('★ 逻辑段没有抛异常（抛了下面的结论不可信）', False,
           REPORT['fatal'].splitlines()[-1] if REPORT['fatal'] else '')
    try:
        await ui_checks(page, tmp)
    except Exception:                                            # noqa: BLE001
        REPORT['fatal_ui'] = traceback.format_exc()
        print(REPORT['fatal_ui'])
        ok('★ 真机段没有抛异常', False,
           REPORT['fatal_ui'].splitlines()[-1] if REPORT['fatal_ui'] else '')


async def main(page: ft.Page):
    VU.patch_flat_background()      # 必须在 app.main(page) 之前
    # [EN] Must be before app.main(page)
    tmp = Path(tempfile.mkdtemp(prefix='nws_round_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    try:
        await _body(page, tmp)
    finally:
        n_ok = sum(1 for c in REPORT['checks'] if c['ok'])
        REPORT['n_ok'], REPORT['n_all'] = n_ok, len(REPORT['checks'])
        REPORT['ok'] = n_ok == len(REPORT['checks'])
        (OUT / 'round_controls_report.json').write_text(
            json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n本轮推演设置验证：{n_ok}/{len(REPORT["checks"])}')
        print('→', '全部通过' if REPORT['ok'] else '有失败')
        VU.safe_rmtree(tmp)
        await shutdown(page, code=0 if REPORT['ok'] else 2)


if __name__ == '__main__':
    try:
        ft.run(main)
    except Exception:
        REPORT['fatal_run'] = traceback.format_exc()
        REPORT['ok'] = False
        try:
            (OUT / 'round_controls_report.json').write_text(
                json.dumps(REPORT, ensure_ascii=False, indent=2),
                encoding='utf-8')
        except Exception:                                        # noqa: BLE001
            pass
        print(REPORT['fatal_run'])
        sys.exit(2)
