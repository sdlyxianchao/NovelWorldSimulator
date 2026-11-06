# -*- coding: utf-8 -*-
"""主循环（设计稿 §2.2 + §六）：GameClock → 导演 → 前台 → 后台 → 边界 → 落盘。

**时间怎么走（2026-10-05 重写）**
---------------------------------
`TIME_RATIO` 的语义是「1 真实秒 = N 故事秒」。老实现把它换算成
`minutes_per_tick = max(1, TIME_RATIO // 60)`，也就是**每跑一圈固定走 1 故事分钟**，
再叠上软时钟那句 `sleep(0.01)` —— 一圈只要 10 毫秒，于是
**8 秒真实时间跑掉了 2 小时 20 分故事时间（≈1000×）**，屏幕上是一屏
「〔同时〕没动，也没出声」。用户原话：「时间比例太夸张了」。

现在两件事分开，各管各的：
  · **时钟**跟真实时间走：`故事秒 += 真实流逝 × TIME_RATIO`（`_advance_clock`）。
    TIME_RATIO=1 就是字面意义的实时；写多少就是多少，软时钟也不会偷偷加速。
  · **决策**按"拍"走：攒够 `BEAT_SECONDS` 故事秒才做一次前台决策。
    拍是**花钱的节拍器**（一次决策 = 1~2 次 LLM 调用），也是"人说话的密度"：
    15 故事秒一个念头，大致是正常人开口的节奏。

English:
Main loop (design doc §2.2 + §六): GameClock → director → foreground → background → boundary →
persist.
**How time advances (rewritten 2026-10-05)**
---------------------------------
The semantics of `TIME_RATIO` is "1 real second = N story seconds". The old implementation
converted it to
`minutes_per_tick = max(1, TIME_RATIO // 60)`, i.e. **a fixed 1 story minute per loop**,
and then stacked the soft clock's `sleep(0.01)` on top — one loop only takes 10 ms, so
**8 seconds of real time ran through 2 hours 20 minutes of story time (≈1000×)**, and on screen
it was a whole screen of
"〔simultaneous〕did not move, made no sound". The user's exact words: "the time ratio is too
exaggerated".
Now the two things are separated and each minds its own business:
  · **Clock** follows real time: `story seconds += real elapsed × TIME_RATIO` (`_advance_clock`).
    TIME_RATIO=1 is literally real time; it does exactly what you write, and the soft clock won't secretly speed up.
  · **Decision** advances by "beat": only make a foreground decision after accumulating `BEAT_SECONDS` story seconds.
    A beat is **a metronome that costs money** (one decision = 1~2 LLM calls), and also "the density of people speaking":
    one thought per 15 story seconds, roughly the rhythm of a normal person speaking up.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from llm.router import llm
from llm import models as MODELS
# ★★★ 「这一家没钱了」的登记表（2026-10-25，用户点名）：主循环靠它决定暂停，
#   而不是靠异常一路往上抛 —— 因为这条路上有十几处 `except Exception`
#   会把它降级成"这一拍什么都没做"，那时候屏幕上就是哑掉的。
# [EN] ★★★ The registry of "this provider is out of money" (2026-10-25, requested by the user):
# [EN] the main loop pauses on it rather than relying on the exception to bubble up -- a dozen
# [EN] `except Exception` along the way would degrade it into "this beat did nothing", and the
# [EN] screen goes silent.
from llm import credit as CREDIT
from world.state import WorldState, PersonState
from world.atlas import Atlas
from agent.core import Agent, Action
from crew import studio as CREWSTUDIO
from crew import agents as CREWAGENTS
from crew import review as REVIEW
from director.engine import DirectorEngine, DirectorEvent, assignment_shared
from director import day_plan as DAYPLAN
from sim.backstage import BackstageBatcher
from store.db import DB
from store.runfolder import RunFolder
from display.rhythm import DisplayRhythm, Priority, display_rhythm
from display.scene_builder import SceneBuilder
from display import dividers as D
from display import script as S
from display import script_render as SR
from display import story_render as STR
from config import CFG
# ★ 2026-10-12 补上：**本模块一直在用 `t()`，却从来没 import 过它**。
#   触发它的是两处用 `t(...)` 拼词的地方：
#     · `_maybe_replay_day` 里那条"回档重演"（2026-10-11 加的，默认关
#       `DAY_REVIEW_REPLAY` ⇒ 平时走不到，所以一直没暴露）；
#     · 收工时语言审校那条小消息的指向（2026-10-12 加的）。
#   两条都包在 `except Exception` 里 ⇒ 表现是**静默**的：那条叙事压根没上屏，
#   日志里只有一句 `剧组播报失败…NameError`。是本轮新加的判据 F6 当场抓到的。
#   ⚠ 这类"用了没导入"的坑在动态语言里只有**真跑那条路**才会现形 ——
#     也就是说"默认关的功能"最容易藏这种雷。
# [EN] ★ Added 2026-10-12: **this module has always used `t()` but never imported it**.
# [EN] Two places that build strings with `t(...)` are what trigger it:
# [EN] · the "roll back and replay" line in `_maybe_replay_day` (added 2026-10-11, off by default via
# [EN] `DAY_REVIEW_REPLAY` ⇒ normally unreachable, which is why it never showed up);
# [EN] · the language review's middle-column pointer at wrap-up (added 2026-10-12).
# [EN] Both are wrapped in `except Exception` ⇒ the symptom is **silent**: that narrative never reaches
# [EN] the screen, with only a `剧组播报失败...NameError` in the log. The new criterion F6 added this
# [EN] round caught it on the spot.
# [EN] ⚠ In a dynamic language this "used but never imported" trap only surfaces by **really running that
# [EN] path** -- i.e. "features that are off by default" are where such mines hide most easily.
from i18n import t
from util.text import now_str, bare_detail
from util.io import atomic_write_text
from logger import log_dir

_LOG = __import__("logging").getLogger("nws.sim")


def _day_ends_on_budget() -> bool:
    """日界是否按"这一站的拍演完"判（用户 2026-10-26 选的 A）。

    ★ 为什么做成**模块级函数**而不是 `CFG.b(...)` 直调：这条开关决定
      "故事时间由谁推"（`_tick` vs `_advance_clock_legacy`），
      两处必须读**同一个答案**。分散写 `CFG.b(...)` 两遍，
      以后改默认值/改名就会一处改了一处没改 —— 而症状是"时钟按新口径走、
      日界按旧口径判"，时钟一天跳 90 天却永远不换天。
    ⚠ 读配置失败时返回 `True`（新口径）：新口径是默认行为，
      读不到配置不该让程序退回一个已经证明有问题的旧行为。
    [EN] Whether the day boundary follows "this station's beats are played" (the user's choice A on
    [EN] 2026-10-26). ★ A module-level function rather than inline `CFG.b(...)` because this switch
    [EN] decides **who advances story time** (`_tick` vs `_advance_clock_legacy`), and both sites
    [EN] must read the same answer. Written twice, a future default change or rename would be applied
    [EN] in one place only -- symptom: the clock runs on the new rule while the day boundary stays on
    [EN] the old one, so the clock jumps 90 days and the day never rolls. ⚠ On a config read failure
    [EN] it returns `True`: the new rule is the default, and a failed read must not fall back to a
    [EN] behaviour already shown to be wrong.
    """
    try:
        return bool(CFG.b('DAY_ENDS_ON_BEAT_BUDGET'))
    except Exception:                                            # noqa: BLE001
        return True


def is_noop(action: Any) -> bool:
    """这个动作"什么都没发生"吗？

    `wait`（还没台词）与空 `think` 属于此类。**它们不该出现在叙事里** ——
    以前每个 tick 都给全场每个不出声的人写一条「没动，也没出声」，
    8 秒写出了 550 条，整屏都是废话（用户报的就是这个）。
    判定放在**显示层之外**（这里），是因为"值不值得写出来"是叙事决策，
    不是渲染细节。
    
        English:
    Is this action "nothing happened"?
        `wait` (no line yet) and empty `think` belong to this category. **They should not appear in the narrative** —
        previously every tick wrote one "did not move, made no sound" for every silent person on stage,
        8 seconds produced 550 entries, a whole screen of nonsense (this is exactly what the user reported).
        The decision is placed **outside the display layer** (here), because "whether it is worth writing out" is a narrative decision,
        not a rendering detail.
    """
    verb = (getattr(action, 'verb', '') or '').strip()
    if verb == 'wait':
        return not (getattr(action, 'dialogue', '') or '').strip()
    if verb == 'think':
        return not (getattr(action, 'inner_thought', '') or '').strip()
    return False


#: **口语应答**（"嗯""……""好"）—— 这些话重复说在对话里很自然。
#: ⚠ 判据要**窄**：按长度猜会把「账差七文」（4 个字，但那是一句真台词）
#:   当成应答放过去，护栏就等于白设。所以只认下面这张表。
# [EN] : **Spoken acknowledgments** ("嗯" "……" "好") — repeating these in dialogue is natural.
# [EN] : ⚠ The criterion must be **narrow**: guessing by length would let "账差七文" (4 characters, but a
# [EN] real line of dialogue)
# [EN] : pass as an acknowledgment, and the guardrail would be pointless. So only the table below is
# [EN] recognized.
_REPLY_WORDS = frozenset({
    '嗯', '哦', '噢', '唔', '唉', '哎', '啊', '呀', '哈', '嘿', '嗨',
    '好', '是', '对', '行', '成', '在', '有', '没', '不', '别', '来',
    '知道', '明白', '懂了', '知道了', '晓得了', '是了', '好罢', '也罢',
    '嗯嗯', '好好', '是的', '对的', '行了', '成了', '来了', '走吧',
})


def _self_review_budget() -> int:
    """这一拍给几次**台词自省**（`crew/cognition` 的反思链）。

    **关掉总闸或关掉自省时返回 0** —— 那一档一次都不会走（"关掉 = 老行为"
    是结构保证，不靠下游各写一个 `if`）。

    为什么抽成一个函数而不是写在 `_tick` 里：这段判据（总闸 ∧ 分闸 → 额度）
    是"关掉就逐字退回"那句话的**唯一落点**，判据要能量到它本人；
    埋在 `_tick` 中间的话，判据只能自己去重算一遍表达式 —— 那就成了
    "测自己写的式子"，产品改了它照样绿（见 `verify_cognition` 的 E6）。
    
        English:
    How many **line introspections** to give this beat (the reflection chain of `crew/cognition`).
        **Return 0 when the master switch is off or introspection is off** — that tier will not run a single time ("off = old behavior"
        is a structural guarantee, not relying on each downstream writing its own `if`).
        Why extract it into a function instead of writing it inside `_tick`: this criterion (master switch ∧ sub switch → quota)
        is the **single landing point** for the saying "when off, fall back verbatim"; the criterion must be able to measure it itself;
        if buried in the middle of `_tick`, the criterion can only recompute the expression itself — which becomes
        "testing a formula you wrote yourself", and it stays green even if the product changes (see E6 of `verify_cognition`).
    """
    try:
        if not (CFG.b('COGNITION') and CFG.b('ACTOR_SELF_REVIEW')):
            return 0
        return max(0, CFG.i('ACTOR_SELF_REVIEW_MAX'))
    except Exception:                                            # noqa: BLE001
        return 0


def is_short_reply(line: str) -> bool:
    """这句是不是"口语应答"（重复说它不算复读，不值得多问一次模型）。

    用户 2026-10-07：「如果说了一样的话，你要看下是不是必须，如果不是必须
    重复，就让人物重新想清楚当前情况，重新说话」——
    但"必须重复"里有一大类是**应答语**：人本来就会连着说"嗯""……""好"，
    那不是复读，是口语。为它多花一次调用不划算，这里直接放行。
    
        English:
    Is this line a "colloquial response" (repeating it does not count as parroting, not worth asking
    the model an extra time).
        User 2026-10-07: "if the same thing was said, you should check whether it is necessary; if it is not a necessary
        repetition, then have the character rethink the current situation and speak again" —
        but a large class of "necessary repetition" is **response words**: people naturally say "mm" "..." "ok" in a row,
        that is not parroting, it is colloquial speech. Spending an extra call on it is not worth it; let it pass directly here.
    """
    t = ' '.join(str(line or '').split()).strip()
    if not t:
        return True                       # 空台词归 `is_noop` 管
        # [EN] Empty lines are handled by `is_noop`
    core = t.strip('。，、！？；：…~～!?., ')
    if not core:
        return True                       # 整句只有标点 / 省略号
        # [EN] The whole line is only punctuation / ellipsis
    return core in _REPLY_WORDS


#: **不是地点的 move 目标**：代词与称呼。
#: 模型偶尔把"对话对象"当成目的地（`move` 的目标写成"对方"/"他"），
#: 于是人物的位置变成一个不存在的地方 —— 后果见 `_apply_action` 里那段注释
#: （被踢出在场名单 + 屏幕上出现「切至 · 对方」）。
#: ⚠ 故意**只收明确不是地点的词**：「楼上」「门外」「后院」这类是真地方，
#:   不在表里；收进去会让"人物上楼"这种正常动作失效。
# [EN] : **Not a location: move targets** — pronouns and forms of address.
# [EN] : The model occasionally treats the "conversation partner" as a destination (`move`'s target
# [EN] written as "对方"/"他"),
# [EN] : so the character's position becomes a place that doesn't exist — see the comment in
# [EN] `_apply_action` for the consequences
# [EN] : (removed from the present list + "切至 · 对方" appears on screen).
# [EN] : ⚠ Deliberately **only includes words that clearly are not locations**: things like "楼上" "门外"
# [EN] "后院" are real places,
# [EN] : not in the table; including them would break normal actions like "the character goes
# [EN] upstairs".
_NOT_A_PLACE = frozenset({
    '对方', '他', '她', '它', '他们', '她们', '自己', '本人',
    '这边', '那边', '此处', '彼处', '这里', '那里',
    '某人', '那人', '这个人', '那个人', '所有人', '大家', '众人',
})


def target_is_not_a_place(world, target: str) -> bool:
    """这个 `move` 目标是不是"压根不是个地方"（代词 / 人名）。

    做成**模块级纯函数**是为了能单独测：`_apply_action` 藏在 RunLoop 里，
    只能"跑一个 tick 再回头查位置"，而这条判定本身值得一条直接的判据。

    规则**从宽**（宁可放过，也别让正常走动失效）：
      · 空 → 算"不是地方"（没有目标就不该动）；
      · 在 `_NOT_A_PLACE` 里 → 是；
      · 是某个**人物的名字** → 是（"去了阿枝"意思是我去找阿枝，不是地点）；
      · 其余一律当**是地方**（地点表可能本来就没写全）。
    
        English:
    Is this `move` target "not a place at all" (pronoun / person name).
        Making it a **module-level pure function** is for standalone testing: `_apply_action` is hidden inside RunLoop,
        so one can only "run a tick and then look back at the position", whereas this decision itself deserves a direct criterion.
        The rule is **lenient** (better to let it pass than to break normal movement):
          · empty → treated as "not a place" (no target means it should not move);
          · in `_NOT_A_PLACE` → yes;
          · is the **name of some character** → yes ("went to A-Zhi" means I went to find A-Zhi, not a location);
          · everything else is treated as **a place** (the location table may simply be incomplete).
    """
    t = str(target or '').strip()
    if not t:
        return True
    if t in _NOT_A_PLACE:
        return True
    try:
        if t in (getattr(world, 'people', {}) or {}):
            return True
    except Exception:                                           # noqa: BLE001
        pass
    return False


def stall_beats(prev: int, actions: Any, *, need: int = 3,
                stuck: int = 0) -> tuple[int, bool]:
    """这一拍算不算**僵局**，以及要不要请导演结算。**纯函数，可单测。**

    ★★★ 为什么要把这段从 `_process_actions` 里抠出来（2026-10-19）
    ------------------------------------------------------------
    用户原话：「剧情要尽快推进」。
    实测（《雪国》34 拍）：14 次决策里 **7 次是 `wait`**，理由全是"等脚步声" ——
    三个人在等同一件事，那件事一直没结果，整场戏停在原地。

    抠出来只为**可测**：写进 `_process_actions` 里就只能靠"源码里有没有这个词"
    来判（那种判据拦不住"变量改了但没接线"——反例法里 M11 就是这么漏的）。
    纯函数配上判据，才测得了"多数人在等 ⇒ 该结算"这个行为本身。

    ★★★ `stuck`：僵局的**第二种形状**（2026-10-19 当天复测加）
    ----------------------------------------------------------
    第一版只认 `wait`，而当天那次真跑没人连等三拍，却照样卡住了 ——
    因为卡法变成了"**来回说同一句话**"：岛村一句「嗯，你是个好人。」
    一字不差说了 **5 次**，「你是个好人」这个话题被追问了 8 轮。
    那不是等，是**没别的话可说**，戏一样不往前走。

    ⇒ `stuck` = 上一拍"说了已经说过的话"的人次（由 `_maybe_retry_repeat` 累加）。
      两人以上在同拍撞上，就算僵局。两种形状**同一条出口**（结算），
      因为要的东西是一样的：给这场戏一个新的事实。

    判据：**多数人**在等（>= 2 人 且 占比 >= 60%），不是"有人等"：
      一个人等着、另一个人在做事，那是正常场面（真跑里也大量存在），不该被打断。

    ⚠ 归零规则：只要这一拍不满足"僵局"就归零 —— 有人动了、有人说了新话，
      僵局就解了，下一次要重新攒。这样"结算"最多每 `need` 拍一次，不会变成连环事故。
    [EN] Is this beat a **deadlock**, and should we ask the director to settle it? **Pure
    [EN] function, unit-testable.** Extracted from `_process_actions` purely so it can be tested
    [EN] behaviourally (a criterion reading source text cannot catch "the variable changed but was
    [EN] never wired in"). ★★★ `stuck` is the **second shape** of deadlock: the first version only
    [EN] recognised `wait`, yet that same run got stuck without anyone waiting three beats in a row --
    [EN] the shape had changed to "saying the same line back and forth" (one line said verbatim five
    [EN] times, one topic pressed for eight rounds). Not waiting, but having nothing else to say.
    [EN] Both shapes share one exit (settlement) because they need the same thing: a new fact.
    """
    try:
        prev = max(0, int(prev))
    except Exception:                                           # noqa: BLE001
        prev = 0
    acts = list(actions or [])
    try:
        need = int(need)
        stuck = max(0, int(stuck))
    except Exception:                                           # noqa: BLE001
        need, stuck = 0, 0
    if need <= 0 or not acts:
        return 0, False
    waiters = sum(1 for _a, act in acts
                  if str(getattr(act, 'verb', '') or '') == 'wait')
    majority_wait = waiters >= 2 and waiters >= int(len(acts) * 0.6)
    # 重复台词：两人以上撞上"已经说过的话" = 这场戏在原地打转。
    # [EN] Repeated lines: two or more people colliding with an already-said line means the scene
    # [EN] is spinning in place.
    majority_stuck = stuck >= 2
    majority = majority_wait or majority_stuck
    cur = prev + 1 if majority else 0
    return cur, cur >= need


def stuck_mission_release(rounds: int, cap: int) -> bool:
    """同一件派活被「还在办」连续拦下 `rounds` 轮 ⇒ 判**卡住**，必须放行重派。

    **纯函数，可单测。**（2026-10-19 第十二轮）

    ★★★ 修的是什么（v11 真跑诊断出的第二个字数暴跌原因）
    ---------------------------------------------------
    `_mission_still_running` 的注释当年写的是：
      "⚠ 不能永远跳过：如果他自己卡住了（**关键词一直不出现**），下一轮就会重新派。"
    那一句防的是**反方向**的卡住 —— "人停了不干"。而真跑里发生的卡住是
    **另一种形状**：关键词**一直在**、事**一直没办成**。
    剧本审读连续抓到同一个人"位置倒退""把上一拍已完成的动作又说一遍"
    "未按派活要求把那件事办成"—— 全是同一件派活在打转。

    为什么原逻辑在这一形状下会**永真**：
      `_maybe_dispatch` 拦下一个人时只做 `missions.pop(name)`，
      **`ps.mission` 一个字节都没动**。于是下一轮
      `_mission_still_running(name, ps.mission)` 拿到的是**同一串派活**
      + 同一个"最近 6 条自己言行"窗口 ⇒ 同一个 True ⇒ 再拦。
      每拦一次，这个人就离"拿到新目标"更远一步 —— **越卡住越永远派不到活**。
    日志实证（snow_v11）：第 16 拍、第 24 拍连续两次
      「派活：1 人的上一件还在办，这一轮不换」。

    ⇒ 判据必须是**可数的**（不猜语义、不再问一次模型）：
      连续被拦的轮数。攒到 `cap` 轮还在"办"，就不是"在办"，
      是**卡死在同一件没办成的事上** —— 换新的。

    ⚠ `cap <= 0` = 关掉这道放行闸（回归到"只看关键词"的老行为）。
      **不默认关**：老行为已实测会把人锁死一整晚。
    ⚠ 轮数是随手就有的量（每轮派活都过一遍这个循环），不额外花调用。
    [EN] The same assignment has been blocked by "still working on it" `rounds` times in a
    [EN] row ⇒ judge it **stuck** and release it for a new one. **Pure, unit-testable.**
    [EN] The original comment claimed "if he gets stuck (keywords never appear), he gets a new
    [EN] one next round" -- that guards the *opposite* shape. The shape that actually occurs is
    [EN] keywords *keep* appearing while the thing never gets done. And in that shape the old
    [EN] logic is **eternally true**: skipping only does `missions.pop(name)` and leaves
    [EN] `ps.mission` untouched, so the next round re-evaluates the same string against the
    [EN] same recent-actions window and gets the same True. ⚠ `cap <= 0` disables this release.
    """
    try:
        rounds = max(0, int(rounds))
    except Exception:                                           # noqa: BLE001
        rounds = 0
    try:
        cap = int(cap)
    except Exception:                                           # noqa: BLE001
        cap = 0
    if cap <= 0:
        return False
    return rounds >= cap


class RunLoop:
    """一次模拟的主循环控制器。
        English:
    Main loop controller for one simulation.
    """

    def __init__(self, world: WorldState, agents: list[Agent],
                 director: DirectorEngine, db: DB, run: RunFolder,
                 atlas: 'Atlas | None' = None,
                 image_hook: Callable[[str, str], str | None] | None = None,
                 compliance: Any | None = None,
                 resume_scenes: list | None = None,
                 resume_recap: str = "",
                 start_day: int = 1):
        self.world = world
        self.agents = agents
        self.director = director
        self.db = db
        # 属性叫 `runfolder` 而不是 `run`：类里有一个 `async def run()` 方法，
        # 以前这里写 `self.run = run`，**实例属性把方法本身覆盖了** ——
        # 于是 `await loop.run()` 变成"调用一个 RunFolder 对象"，
        # 报 `'RunFolder' object is not callable`。
        # 因为循环从没被真正跑过，这个 bug 一直潜伏着，接 GUI 时才炸出来。
        # [EN] The attribute is called `runfolder` rather than `run`: the class has an `async def run()`
        # [EN] method,
        # [EN] previously this was written `self.run = run`, and **the instance attribute overrode the method
        # [EN] itself** —
        # [EN] so `await loop.run()` became "calling a RunFolder object",
        # [EN] raising `'RunFolder' object is not callable`.
        # [EN] Because the loop was never actually run, this bug lay dormant until the GUI was connected, when
        # [EN] it blew up.
        self.runfolder = run
        # ★ 三级底图（2026-10-08）：开卷时定下来的空间事实（见 `world/atlas.py`）。
        #   ⚠ 它顶掉的是一个**从没被读过**的旧字段 `game_map`（`world/map.GameMap`）：
        #     那个类一直在、`build_map()` 也一直在调，但读的是设定集里
        #     `{"名称":"待生成","地点":[]}` 这个**空占位** → 永远返回 None，
        #     挂上来之后**没有任何地方读它**。一条完整但死的链路。
        #     `None` = 这本书没有底图 → 每天照旧现摆位（不是故障）。
        # [EN] ★ Third-level base map (2026-10-08): the spatial facts fixed when the book is opened (see
        # [EN] `world/atlas.py`).
        # [EN] ⚠ What it replaces is a legacy field `game_map` (`world/map.GameMap`) that was **never read**:
        # [EN] that class was always there and `build_map()` was always called, but what was read was the
        # [EN] setting collection's
        # [EN] and after being hooked up, **nothing reads it**. A complete but dead chain.
        # [EN] `None` = this book has no base map → each day is laid out on the fly as before (not a failure).
        self.atlas = atlas
        # 插图钩子：`(kind, key) -> 路径`。由外层注入（GUI 传 Pillow 生成器，
        # 测试传桩），这样 sim/ 不必依赖 image_gen，也方便关掉。
        self.image_hook = image_hook          # 下面会被剧组那层包一遍（见后）
        # ★ 合规 Agent（设计稿 §16.1「独立专职」）。
        #   ⚠ 2026-10-06 查出来的事实：**全项目没有一个地方实例化过它** ——
        #   `COMPLIANCE_ENABLED` 在界面上摆着、`compliance/agent.py` 写着，
        #   但推演路径上一次都没调用过。"独立"变成了"不存在"。
        #   现在由 `sim/setup.assemble` 造一份、这里拿着，在 CP6（落盘前）真的查。
        # [EN] Illustration hook: `(kind, key) -> path`. Injected by the outer layer (GUI passes a Pillow
        # [EN] generator,
        # [EN] tests pass a stub), so sim/ need not depend on image_gen and it's easy to turn off.
        # [EN] Below it will be wrapped once by that layer of the cast/crew (see later)
        # [EN] ★ Compliance Agent (design doc §16.1 "independent, dedicated").
        # [EN] ⚠ Fact discovered on 2026-10-06: **nowhere in the whole project is it ever instantiated** —
        # [EN] `COMPLIANCE_ENABLED` sits in the UI, `compliance/agent.py` is written,
        # [EN] but it was never called once on the simulation path. "Independent" became "nonexistent".
        # [EN] Now `sim/setup.assemble` creates one, this holds it, and it really checks at CP6 (before writing
        # [EN] to disk).
        self.compliance = compliance
        # ★ **续跑**：上一轮同一天已经写好的那几幕（2026-10-08）。
        #   这一轮接着写同一天时，它们排在新幕前面 —— 收工落盘就是完整的
        #   这一天（不覆盖掉前半段）。见 `sim/resume.py` 与
        # [EN] ★ **Resume**: the scenes already written earlier in the same day (2026-10-08).
        # [EN] When this round continues writing the same day, they are placed before the new scenes — writing
        # [EN] to disk at the end gives the complete
        # [EN] day (without overwriting the earlier half). See `sim/resume.py` and
        #   `SceneBuilder(initial_scenes=…)`。
        #   ⚠ 只在**当天第一幕**用一次（`_ensure_builder`），用掉就清 ——
        #     不然跨天之后新的一天会又把昨天那几幕挂上去。
        # [EN] ⚠ used only once on **the first scene of the day** (`_ensure_builder`), cleared after use —
        # [EN] otherwise after crossing days, the new day would again hang yesterday's scenes on.
        self._resume_scenes: list = list(resume_scenes or [])
        # ★★ **续跑时的"上一回说到"**（2026-10-11，用户报的"每次前情提要都一样"）。
        # [EN] ★★ **"Previously on" during resume** (2026-10-11, the user-reported "the recap is the same every
        # [EN] time").
        # 为什么必须有它：本轮是**新开的一轮**，`state.db` 是新的空库 ⇒
        # `recap_text()` 读不到摘要、也读不到事件，一路退到设定集里的
        # `_opening_context`（"这个世界是什么样"）—— 于是作者**每一轮都看到
        # 同一句开场白**，看起来就像"进度什么都没记住"（其实都在，
        # 停点里 `day/minutes/ticks_today` 一条不缺，续跑也确实接上了）。
        # [EN] Why it is necessary: this round is a **newly opened round**, `state.db` is a new empty database
        # [EN] ⇒
        # [EN] `recap_text()` reads no summary and no events, falling all the way back to the setting
        # [EN] collection's
        # [EN] `_opening_context` ("what this world is like") — so the author **sees the same opening
        # [EN] line every round**, which looks like "nothing about progress was remembered" (in fact it's all
        # [EN] there,
        # [EN] the checkpoint has every one of `day/minutes/ticks_today`, and resume really did connect).
        # 由「起笔」按上一轮的停点算好传进来（`sim/resume.resume_recap`）。
        # ⚠ **只在本轮开头用一次**（`_push_recap` 用完就清）——
        #   不清的话每个日界又会把"上一回说到…"念一遍。
        # [EN] The "opening stroke" computes it from the previous round's checkpoint and passes it in
        # [EN] (`sim/resume.resume_recap`).
        # [EN] ⚠ **Used only once at the start of this round** (`_push_recap` clears it after use) —
        # [EN] if not cleared, every day boundary would recite "previously on…" again.
        self._resume_recap: str = str(resume_recap or "")

        # ★★ **作者对本轮走向的要求**（2026-10-11，`sim/directive.py`）——
        #   从**这一轮的 world** 上取（装配时 `assemble(user_directive=…)` 挂上去的）。
        #   取一次、存成**已经拼好的那一行**（要带 i18n 抬头），
        #   `_push_author_note` 在开头推它；提示词那边由 `craft_block` 各自取。
        #   ⚠ 它**不是**从 `RunLoop` 的入参走：`craft_block` 要的是"世界上挂着的那份"，
        #     两处各存一份就会分叉（一处改了另一处没改）。
        # ⚠ 空串 = 作者没填 = 屏幕上**一个字都不多**。
        # [EN] ★★ **The author's requirements for this round's direction** (2026-10-11, `sim/directive.py`) —
        # [EN] taken from **this round's world** (attached at assembly time via `assemble(user_directive=…)`).
        # [EN] Fetched once, stored as **the already-assembled line** (must carry the i18n heading),
        # [EN] `_push_author_note` pushes it at the start; on the prompt side, `craft_block` each fetches it.
        # [EN] ⚠ It does **not** go through `RunLoop`'s parameters: what `craft_block` wants is "the copy
        # [EN] hanging on the world",
        # [EN] storing one copy in two places would diverge (one changed, the other not).
        # [EN] ⚠ Empty string = the author left it blank = **not a single extra character** on screen.
        self._author_note: str = ""
        try:
            from sim import directive as _DIR
            self._author_note = _DIR.line(world)
        except Exception as e:                                  # noqa: BLE001
            _LOG.debug('取作者走向要求失败（当没填）：%r', e)

        self._running = False
        self._paused = False
        #: ★★★ 「因为某家模型服务没钱而暂停」的标志（2026-10-25）。
        #:   `resume()` 见到它就清掉欠费登记 —— 于是"充值后点继续"是**真的会重试**，
        #:   而"没充就点继续"会再撞一次、再停一次、再报一次（用户要的正是这个语义）。
        # [EN] ★★★ "Paused because a model provider is out of money" (2026-10-25).
        # [EN] `resume()` sees it and clears the credit registry -- so "top up then resume" really
        # [EN] retries, while "resume without topping up" hits it again, stops again, reports again.
        self._credit_paused = False
        #: 登记给 `llm.credit` 的回调（**存成同一个对象**，否则撤不掉 —— 绑定方法每次取都不同）。
        # [EN] Callback registered with `llm.credit` (**stored as one object**; a bound method is a
        # [EN] fresh object on each access, so it could never be removed).
        self._credit_cb: Callable | None = None
        self._daily_narrative: list[str] = []     # prose 模式用
        # [EN] Used in prose mode
        #: ★ **哪几天的章节已经推到窗口了**（`_day_novel` 推送成功后记一笔）。
        #: 为什么要有它（2026-10-21，用户：「点停止的时候也要出一章」）：
        #:   停止时 `_finish` 会先 `_end_day()`（里面就有 `_day_novel` 整理+推送），
        #:   然后还有一道**兜底** `_flush_novel_on_stop()`（防止 `_end_day` 崩了、
        #:   或者"每日整理"被关掉时窗口一片空白）。两道都有推送入口，
        #:   没有这个集合就会**同一天推两章**（窗口里出现两份几乎一样的正文）。
        #: ⚠ 用 `set` 而不是"最后一次的 day"：中途停止可能跨天补落两次。
        # [EN] : ★ **Which days' chapters have been pushed to the window** (recorded after `_day_novel`
        # [EN] succeeds). Why it exists (2026-10-21, user: "hitting stop should also produce a chapter"):
        # [EN] on stop, `_finish` first calls `_end_day()` (which already runs `_day_novel` = organize +
        # [EN] push), and then a **fallback** `_flush_novel_on_stop()` (in case `_end_day` crashed, or the
        # [EN] daily-organization switch is off). Two push sites without this set would push the **same day
        # [EN] twice** (two near-identical chapters in the window).
        # [EN] ⚠ A `set`, not "the last day": a mid-run stop can flush across a day boundary twice.
        self._novel_pushed_days: set[int] = set()
        # ★★★ 2026-10-31（用户：「运行窗口左上角时间和对话窗口的时间对不上，
        #   左上角说是第4天但是运行窗口是第2天刚结束，正准备第三天」）：
        #   **写作天必须从续跑的起点接上**，不能再写死 1。
        #   以前这一行是 `self._current_day = 1`，于是"第二轮"永远从第 1 天开始编号：
        #   · 世界时钟由 `start_clock_of(plan)` 接着上一轮的停点（第 3 天），
        #   · 写作天却从 1 起 ⇒ 两条线从开演那一刻就差了 N 天，
        #     而且 `第003天.md`/中栏幕头/停点 `day` 全跟着写作天走 ——
        #     用户看到"左上角第 4 天 / 稿子是第 3 天"，就是这两条线。
        #   ⚠ 这是**接线**不是"算法"：起点由 `resume.plan()` 算，这里只负责接住。
        # [EN] ★★★ 2026-10-31 (user: "the top-left clock and the dialogue window disagree --
        # [EN] top-left says day 4 while the run window says day 2 just ended, about to start day 3"):
        # [EN] **the writing day must continue from the resume point**, it can no longer be hard-coded
        # [EN] to 1. This line used to be `self._current_day = 1`, so "round two" always numbered from
        # [EN] day 1 while the world clock (via `start_clock_of(plan)`) continued at day 3 -- the two
        # [EN] lines diverged from the first beat, and `第003天.md`, the centre-column header and the
        # [EN] stop point's `day` all follow the writing day. That is exactly the mismatch the user saw.
        # [EN] ⚠ This is **wiring**, not an algorithm: the start comes from `resume.plan()`.
        self._current_day = max(1, int(start_day or 1))
        #: ★★★ **这一天开演时的"故事天"**（日界兜底比较的基准，2026-10-30）。
        #:   ⚠ 这是本轮修的一个真 bug：兜底那条以前拿 `world.game_day != self._current_day`
        #:     比 —— 左边是**故事天**、右边是**写作天**（第几份稿）。第一天两者都是 1，
        #:     所以第一天正常；到了第二天写作天变 2，而故事天才走到 1（拍预算先演完了，
        #:     钟还没跨 24 点）⇒ `1 != 2` **立刻成立**，于是**从第二天起每天都在第一拍就收工**。
        #:     实测（`第一部_聊斋夜客_设定集`）：第 1 天 9 幕 4,949 汉字，第 2 天 **1 幕 267 字**、
        #:     第 3 天 1 幕 433 字 —— 用户看到的"每天给不了多少字"就是它。
        #:   ⇒ 基准必须是**这一天开演时的故事天**，与写作天（`_current_day`）彻底分开。
        # [EN] ★★★ **The story day at the start of this writing day** (the baseline for the day-boundary
        # [EN] fallback). ⚠ Real bug fixed here: the fallback compared `world.game_day` (story day)
        # [EN] against `self._current_day` (writing day). Both are 1 on day one, so day one was fine;
        # [EN] on day two the writing day is 2 while the story clock never crossed midnight (the beat
        # [EN] budget ended the day first) => `1 != 2` fires **immediately**, so **every day after the
        # [EN] first wrapped up after a single beat**. Measured: day 1 = 9 scenes / 4,949 chars,
        # [EN] day 2 = **1 scene / 267**, day 3 = 1 / 433. That is exactly the user's "a day barely
        # [EN] produces anything". The baseline must be the story day at day start.
        self._story_day_at_day_start = int(getattr(self.world, 'game_day', 1) or 1)
        #: ★★ **当前这一站已经演了几个写作天**（2026-10-27：给「章数下限」用）。
        #:   一章 = 一个写作天 = 一份整理稿，所以它就是"这一站已经写了几章"。
        #:   ⚠ 必须与"站 id"配一对记（`_node_days_id`）：只记数字不记是哪一站，
        #:     过站之后这个数字会对着**新的站**继续用 —— 于是新站一上来就"已经演了 5 章"，
        #:     章数下限当场失效（而且**完全静默**：看起来只是"这一站走得快"）。
        # [EN] ★★ **How many writing days the current station has run** (2026-10-27, for the
        # [EN] "minimum chapters" gate). One chapter = one writing day = one organized draft, so this
        # [EN] is "how many chapters this station has produced". ⚠ It must be paired with the station
        # [EN] id (`_node_days_id`): a bare counter would keep counting into the **next** station, so
        # [EN] the new station would start at "already 5 chapters" and the gate would silently fail
        # [EN] (looking merely like "this station went fast").
        self._node_days = 0
        self._node_days_id = ''
        #: 「章数还没演够、先不往前走」那句提醒**今天已经说过没有**（一天只说一次，
        #:   否则每一次进度评估都会重复同一句，把正文冲淡）。
        # [EN] Whether the "not enough chapters yet" reminder has been said today (once per day --
        # [EN] otherwise every progress evaluation repeats it and dilutes the prose).
        self._hold_note_day = -1
        #: ★ **这一天的开场走过没有**（`_open_day()` 的幂等标记，2026-10-07 第八轮）。
        # [EN] : ★ **Has this day's opening been walked through** (`_open_day()`'s idempotency flag, 2026-10-07
        # [EN] eighth round).
        #: 为什么它必须与 `_current_day` **分开**：判断"要不要开场"不能用
        #: `game_day != _current_day` —— 两者初值都是 1，第一天的开场于是**永不执行**
        #: （编剧室/剧本/今日简介/场景介绍/派活/地图/声音全缺）。
        #: `0` = 还没开过场（初值刻意用 0，让第一天必然走到）。
        # [EN] : Why it must be **separate** from `_current_day`: deciding "whether to open the day" cannot use
        # [EN] : `game_day != _current_day` — both have initial value 1, so the first day's opening would
        # [EN] **never execute**
        # [EN] : (the writers' room / script / today's brief / scene intro / assignments / map / sound all
        # [EN] missing).
        # [EN] : `0` = opening not yet done (initial value deliberately 0, so the first day necessarily gets
        # [EN] there).
        self._day_opened_for = 0
        #: ★ **有人点了停止**（2026-10-07 第八轮）。
        # [EN] : ★ **Someone clicked stop** (2026-10-07 eighth round).
        #: 为什么不能直接读 `_running`：`_running` 是"主循环还在不在转"，
        #: 它的**初值是 False**（`run()` 一开始才置 True）——
        #: 而探针与判据大量直接调 `loop._tick(i)` / `_compose_day()`（不经过 `run()`）。
        #: 拿 `_running` 当"该不该提前收手"的判据，那些路径会**一拍都不跑**
        #: （实测：`verify_dialogue_repeat` 从 39/39 掉到 29/39）。
        #: 这一个字段只表"请求过停止"，初值 False、只有 `stop()` 会置 True。
        # [EN] : Why we can't just read `_running`: `_running` is "is the main loop still turning",
        # [EN] : its **initial value is False** (only set True when `run()` begins) —
        # [EN] : while probes and criteria largely call `loop._tick(i)` / `_compose_day()` directly (not going
        # [EN] through `run()`).
        # [EN] : Using `_running` as the criterion for "should we stop early", those paths would **not run a
        # [EN] single tick**
        # [EN] : (measured: `verify_dialogue_repeat` dropped from 39/39 to 29/39).
        # [EN] : This single field only indicates "a stop was requested", initial value False, only `stop()`
        # [EN] sets it True.
        self._stop_requested = False
        #: ★ **这一天拍了几拍**（2026-10-07 第八轮）。
        # [EN] : ★ **How many ticks this day has played** (2026-10-07 eighth round).
        #: 为什么不用 `_tick_no`：那个是**整轮**的，而收尾要判的是
        #: "**这一天**有没有东西可落"。差别出现在一种真机上会遇到的情况：
        #: 跨天那一刻点了停止 —— 第 N 天已经落过盘、总结也写过，
        #: 而第 N+1 天一拍都没跑。这时用 `_tick_no > 0` 判，会**再落一天空稿、
        #: 再写一份重复的今日总结**；用这个字段判就知道"今天什么都没发生"。
        # [EN] : Why not use `_tick_no`: that one is for the **whole round**, while the wrap-up needs to judge
        # [EN] : "does **this day** have anything to write to disk". The difference shows up in a situation
        # [EN] that occurs on a real device:
        # [EN] : stop was clicked at the moment of crossing days — day N already wrote to disk and wrote its
        # [EN] summary,
        # [EN] : while day N+1 didn't run a single tick. In this case judging by `_tick_no > 0` would **write
        # [EN] another empty day
        # [EN] : and write another duplicate today's summary**; judging by this field tells you "nothing
        # [EN] happened today".
        self._ticks_today = 0
        # 剧本式输出（OUTPUT_FORMAT=script 时启用）
        # [EN] Script-style output (enabled when OUTPUT_FORMAT=script)
        self._builder: SceneBuilder | None = None
        self._last_clock = None
        self._last_place = ''
        self._tick_no = 0
        #: 这一拍还剩几次"重说"的预算（`DIALOGUE_RETRY_MAX`，见 `_review_repeat`）。
        #: **每拍重置**：重说要额外花一次调用，得有个上限兜着。
        # [EN] : How many "resay" budget remain for this beat (`DIALOGUE_RETRY_MAX`, see `_review_repeat`).
        # [EN] : **Reset every beat**: a resay costs an extra call, so there has to be a cap on it.
        self._retry_left = 0
        #: ★ 这一拍还剩几次**台词自省**的预算（`ACTOR_SELF_REVIEW_MAX`，
        #: 见 `_self_review`）。与 `_retry_left` **分开记**：
        #: 两者是两种不同的重说（一个是"你刚说过这句"，一个是"这句不像人话"），
        #: 合成一个计数器的话，一句话重复又不像人话时，第二次就没额度了。
        # [EN] : ★ How many **line self-review** budget remain for this beat (`ACTOR_SELF_REVIEW_MAX`,
        # [EN] : see `_self_review`). Tracked **separately** from `_retry_left`:
        # [EN] : the two are different kinds of resay (one is "you just said this line", the other is "this
        # [EN] line doesn't sound human"),
        # [EN] : if merged into one counter, a line that is both repetitive and unnatural would have no
        # [EN] allowance left the second time.
        self._review_left = 0
        # ★ 去 AI 味审计的**当日累积**（2026-10-07）：上屏词条的命中 + 被删掉的
        #   套话词。日界取走落盘（见 `deai_take`）。
        # [EN] ★ **Daily cumulative** de-AI audit (2026-10-07): hits of on-screen entries + deleted
        # [EN] cliche words. The day boundary is taken at persistence time (see `deai_take`).
        self._deai_hits: list = []
        self._deai_stripped: list[str] = []
        self._deai_checked: int = 0
        # ★ 导演盯戏（2026-10-07）的当日累积：查出来的问题（见 `_director_watch`）。
        # [EN] ★ Daily cumulative of director watch (2026-10-07): issues found (see `_director_watch`).
        self._watch_notes: list[str] = []
        self._rollback_total: int = 0
        #: 这一天复盘有没有"回档重演"过（一天最多一次，见 `DAY_REVIEW_REPLAY`）
        # [EN] : Whether this day's review has "replayed/rolled back" (at most once a day, see
        # [EN] `DAY_REVIEW_REPLAY`).
        self._replayed_today: bool = False
        #: 这一拍往剧本里真正加了**几条**（回档时用它决定删多少，见 `_rollback`）
        # [EN] : How many entries were **actually added** to the script this beat (used on rollback to decide
        # [EN] how many to delete, see `_rollback`).
        self._last_chunk_n: int = 0
        #: 回档回调 `cb(n)` —— 界面用它把中栏那几条撤掉（见 `on_rollback`）
        # [EN] : Rollback callback `cb(n)` -- the UI uses it to remove those entries from the middle column
        # [EN] (see `on_rollback`).
        self._on_rollback: Callable[[int], None] | None = None
        #: 当天剧本（`director.day_plan.DayScript`）；None = 这一天没有框架
        #: （关掉了 `DAY_PLAN` / 模型没写出来）。决策提示词据此决定要不要带〔今日剧本〕。
        # [EN] : Today's script (`director.day_plan.DayScript`); None = no framework for this day
        # [EN] : (either `DAY_PLAN` is off / model failed to write it). The decision prompt uses this to decide
        # [EN] whether to include 〔Today's Script〕.
        self._day_script = None
        #: ★★ **今天的场次编排**（`director.stage.StagePlan`，2026-10-11）——
        #: 把剧作家的分拍表变成"现在第几拍、这场戏演完了没有"的状态。
        #: 演员的提示词读它、导演的收场与换场按它走。
        #: `None` = 这一天没有分拍（或这一层关着）⇒ 行为与加它之前**逐字相同**。
        # [EN] : ★★ **Today's stage schedule** (`director.stage.StagePlan`, 2026-10-11) --
        # [EN] : turns the playwright's beat sheet into the state "which beat we are on, is this scene
        # [EN] : finished". The actors' prompts read it, and the director wraps up / changes scene by
        # [EN] : it. `None` = no beat breakdown today (or this layer is off) ⇒ behavior is
        # [EN] : **byte-for-byte identical** to before it existed.
        self._stage_plan = None
        # ★ **当天这张小地图**（`Layout`）：由剧组美术在**当天剧本写完之后**画，
        #   取景范围 = 今天这几场戏涉及到的地点。界面读它画左栏小地图
        #   （见 `gui/app_flet._draw_minimap`）。`None` = 今天还没有图，界面退回旧做法。
        # [EN] ★ **Today's little map** (`Layout`): drawn by the crew artist **after today's script is
        # [EN] written**,
        # [EN] The framing scope = the locations involved in today's scenes. The UI reads it to draw the
        # [EN] left-column minimap
        # [EN] (see `gui/app_flet._draw_minimap`). `None` = no map for today yet, the UI falls back to the old
        # [EN] behavior.
        self.day_map = None
        # (text, priority, kind='') -> None；`kind` 是词条类型，让界面按类型分样式
        # [EN] (text, priority, kind='') -> None; `kind` is the entry type, letting the UI style by type.
        self._on_narrative: Callable[..., None] | None = None
        # ★ 2026-10-06 新增两条通道（用户要求底部状态条与分隔符）：
        #   `_on_divider(Divider)` —— 日 / 幕 / 故事 / 模块的分界符
        #   `_on_status(key, **kw)` —— 细粒度运行状态（正在生成 / 等着下一拍 / 已暂停…）
        #   两条都**只是播报**：回调抛异常绝不影响推演本身。
        # [EN] ★ 2026-10-06 added two channels (user requested bottom status bar and dividers):
        # [EN] `_on_divider(Divider)` -- divider for day / act / story / module
        # [EN] `_on_status(key, **kw)` -- fine-grained run status (generating / waiting for next beat /
        # [EN] paused...)
        # [EN] Both are **broadcast only**: a callback raising an exception never affects the simulation
        # [EN] itself.
        self._on_divider: Callable[..., None] | None = None
        self._on_status: Callable[..., None] | None = None
        # `_on_self_pause(why)` —— **主循环自己开的暂停**（2026-10-10 加）。
        # [EN] `_on_self_pause(why)` -- **pauses initiated by the main loop itself** (added 2026-10-10).
        # ★★ 为什么必须有这一条（用户真机报的「核对故事进度进行了 2000 多秒」）：
        #   暂停有**两个来源**，而以前只有一个能通知界面：
        #     · 用户点「暂停/继续」→ `RunSession.pause()` → 会话状态变 `paused` ✅
        #     · 主循环自己停（日界检查点 `STORY_DAY_EVERY_DAYS` / open 模式存档点 /
        #       岔路口 / 导演介入 `pause` 策略）→ 只置了 `self._paused = True` ❌
        #   后者**不经过会话层**，于是界面完全不知道它停了：
        #     · `session.status` 还是 `running` ⇒ 暂停按钮仍写着「⏸ 暂停」，
        #       **没有「▶ 继续」可点**（用户根本没法把它放走）；
        #     · 状态条停在**最后一次上报的 key**上 —— 那天正好是 `evaluating`
        #       ⇒ 屏幕上写着「正在核对故事进度 · 已 2019 秒」，一直涨到用户手点暂停。
        #       实测：23:06:55 日界暂停 → 23:40:34 用户按暂停，中间 **0 次 LLM 调用**
        #       （`llm_calls.jsonl` 末条停在 23:06:55）—— **没有任何东西在跑**，
        #       它就是在等人点「继续」，而屏幕上一个字都没说。
        #   ⇒ 内部暂停必须**通知会话层**，这条通道就为此而设。
        # [EN] ★★ Why this is mandatory (user-reported on real machine: "checking story progress ran for over
        # [EN] 2000 seconds"):
        # [EN] Pauses have **two sources**, and previously only one could notify the UI:
        # [EN] · User clicks "Pause/Resume" -> `RunSession.pause()` -> session status becomes `paused` ✅
        # [EN] · The main loop stops itself (day-boundary checkpoint `STORY_DAY_EVERY_DAYS` / open-mode save
        # [EN] point /
        # [EN] fork in the road / director intervention `pause` policy) -> only set `self._paused = True` ❌
        # [EN] The latter **does not go through the session layer**, so the UI has no idea it stopped:
        # [EN] · `session.status` is still `running` => the pause button still says "⏸ Pause",
        # [EN] **there is no "▶ Resume" to click** (the user cannot let it go at all);
        # [EN] · The status bar stays on **the last reported key** -- that day it happened to be `evaluating`
        # [EN] => the screen reads "Checking story progress · 2019s", climbing until the user manually clicks
        # [EN] pause.
        # [EN] Measured: 23:06:55 day-boundary pause -> 23:40:34 user pressed pause, with **0 LLM calls** in
        # [EN] between
        # [EN] (`llm_calls.jsonl` last entry stays at 23:06:55) -- **nothing was running**,
        # [EN] it was just waiting for someone to click "Resume", and the screen said not a single word.
        # [EN] => Internal pauses must **notify the session layer**, and this channel exists for that.
        self._on_self_pause: Callable[[str], None] | None = None
        # `_on_scene(dict)` —— 「换地方了」（地点/时段变了）。
        #   界面拿它重画小地图：**每次切场景重画一次**（用户 2026-10-06 要的）。
        #   传的是数据（place/segment/cast/day），不是给人看的句子。
        # [EN] `_on_scene(dict)` -- "location changed" (place/time-of-day changed).
        # [EN] The UI uses it to redraw the minimap: **redraw once per scene switch** (user request
        # [EN] 2026-10-06).
        # [EN] It passes data (place/segment/cast/day), not human-readable sentences.
        self._on_scene: Callable[[dict], None] | None = None
        # `_on_work(key, state)` —— **某个职位开始/结束出工**（2026-10-08）。
        #   界面拿它把"正在干活的那一位"高亮出来（用户：「谁在干活请高亮显示
        #   等不干活了再恢复普通样式」）。
        #   ⚠ 与 `_on_scene` 一样只传数据（职位 key + 状态词），**不传产出** ——
        #     "谁在忙"的播报和"交了什么活"是两条通道（后者走 `_on_crew_note`）。
        # [EN] `_on_work(key, state)` -- **a role starts/ends work** (2026-10-08).
        # [EN] The UI uses it to highlight "the one currently working" (user: "whoever is working, please
        # [EN] highlight
        # [EN] and restore normal styling when they stop").
        # [EN] ⚠ Like `_on_scene`, only passes data (job key + state word), **does not pass output** --
        # [EN] "who is busy" broadcasts and "what work was delivered" are two channels (the latter goes through
        # [EN] `_on_crew_note`).
        self._on_work: Callable[[str, str], None] | None = None
        #: 剧组消息的"起一条/改一条"（2026-10-23）。与 `_on_work` 分开：那条只管
        #: "谁在忙"（右侧面板高亮），这条管"中栏那一行字写成什么"。
        #: [EN] "Open/rewrite a crew message" (2026-10-23). Separate from `_on_work`:
        #: that one only covers "who is busy" (right panel highlight), this one covers
        #: "what that line in the middle column says".
        self._on_crew_line: Callable[[str, str, dict], None] | None = None
        # 播报类故障的「已记过」标记（见 `_warn_once`）
        # [EN] "Already recorded" marker for broadcast-type faults (see `_warn_once`)
        self._cb_warned: set[str] = set()
        self._on_event: Callable[[DirectorEvent], None] | None = None
        self._on_branch: Callable[[list[dict]], None] | None = None
        # ★★ **统一的"问作者一个问题"通道**（2026-10-11）。
        # [EN] ★★ **Unified "ask the author a question" channel** (2026-10-11).
        # 用户原话：「2.如果确实需要用户干预 使用之前的方式（弹出一个对话框，
        # 带有背景描述（当前故事发展的简单概述） 为何需要我选择（要问的问题）
        # 然后是几个选项（单选） 最后一定多一个可输入的输入框单选 表示用户不选择
        # 软件提供的选项 要用自己的选项 选择之后下面有确定和取消
        # 如果选择取消则推演变成暂停 用户点继续的时候 继续弹出相关对话框」。
        # [EN] User's exact words: "2. If user intervention is truly needed, use the previous approach (pop up
        # [EN] a dialog,
        # [EN] with background description (a brief overview of current story development), why I need to
        # [EN] choose (the question to ask)
        # [EN] then several options (single-select), and finally always one more input box single-select,
        # [EN] meaning the user does not choose
        # [EN] the software-provided options but uses their own option. After choosing, below are Confirm and
        # [EN] Cancel.
        # [EN] If Cancel is chosen, the simulation becomes paused; when the user clicks Resume, the relevant
        # [EN] dialog pops up again."
        # 以前**只有岔路口**有这套对话框（`on_branch`），而另外两处真正需要
        # 作者拍板的地方 —— 导演介入待确认、预算耗尽 —— 是**裸暂停**：
        # 中栏一句话、按钮还是「暂停」，作者连"继续"都点不到。
        # 现在三处统一走这里：`_ask()` 出题 → 界面弹对话框 → `answer_ask()`
        # 或 `cancel_ask()` 回话。
        # [EN] Previously **only the fork in the road** had this kind of dialog (`on_branch`), while the other
        # [EN] two places that truly need
        # [EN] author decision -- director intervention pending confirmation, budget exhaustion -- were **naked
        # [EN] pauses**:
        # [EN] one sentence in the middle column, button still "Pause", the author cannot even click "Resume".
        # [EN] Now all three go through here: `_ask()` asks -> UI pops the dialog -> `answer_ask()`
        # [EN] or `cancel_ask()` replies.
        self._on_ask: Callable[[dict], None] | None = None
        #: 作者的回答（`answer_ask` 写入，`_ask` 轮询读走）
        # [EN] : The author's answer (`answer_ask` writes it, `_ask` polls and reads it)
        self._ask_answer: dict | None = None
        #: **还没答完的那道题**。取消（→暂停）之后它留着，
        #: 作者点「继续」时由 `resume()` 重新弹出来（用户点名要的行为）。
        # [EN] : **The question not yet answered**. After cancel (-> pause) it stays,
        # [EN] : and when the author clicks "Resume", `resume()` pops it up again (behavior the user explicitly
        # [EN] asked for).
        self._ask_pending: dict | None = None
        #: 预算耗尽那一题**问过哪一天了**（同一题一天只问一次，见 `_maybe_ask_budget`）
        # [EN] : For the budget-exhaustion question, **which day has been asked** (the same question is asked
        # [EN] only once a day, see `_maybe_ask_budget`)
        self._budget_asked_day: int | None = None
        #: 用户在岔路口挑的候选 id（`choose_branch`）；与 `_branch_custom` 互斥。
        # [EN] : The candidate id chosen by the user at the fork (`choose_branch`); mutually exclusive with
        # [EN] `_branch_custom`.
        self._branch_choice: str | None = None
        #: 用户在岔路口**自己写的**走向（`choose_branch_custom`）—— 2026-10-07 加。
        #: 与「挑候选」是两条并列的路：候选是导演给的，自己写的是作者给的。
        #: 空串 = 没写（**不是 None**：要与"还没回话"区分开，见 `choose_branch_custom`）。
        # [EN] : The direction the user **wrote themselves** at the fork (`choose_branch_custom`) -- added
        # [EN] 2026-10-07.
        # [EN] : It is a parallel path to "pick a candidate": candidates are given by the director, the
        # [EN] self-written one is given by the author.
        # [EN] : Empty string = not written (**not None**: must be distinguished from "not yet replied", see
        # [EN] `choose_branch_custom`).
        self._branch_custom: str = ""
        # 岔路口的状态（2026-10-06 接分支时加）：
        #   · `_branch_pending`：节点刚走完 → 下一拍问一次"往哪走"
        #   · `_last_branch_day`：同一天只弹一次（否则每拍都弹，烦死）
        #   · `_branch_hint`：用户挑的那条，带进下一拍的挑事提示词
        # [EN] State of the fork in the road (added 2026-10-06 when branches were wired in):
        # [EN] · `_branch_pending`: the node just finished -> ask "where to go" once next beat
        # [EN] · `_last_branch_day`: pop up only once per day (otherwise it pops every beat, maddening)
        # [EN] · `_branch_hint`: the one the user picked, carried into the next beat's troublemaking prompt
        self._branch_pending = False
        self._last_branch_day = -1
        self._branch_hint = ""
        #: 这一站自带的**结局选项**（作者写在节点上的 `选项`；用完即清）。
        #: ⚠ 一次性提示：写完就必须有地方读掉，否则永久锁死在一个方向。
        # [EN] This station's own **ending options** (the author's `选项` on the node; cleared once
        # [EN] used). ⚠ One-shot hint: once written, something must read it, or the run is locked
        # [EN] into one direction forever.
        self._pending_options: list[str] | None = None
        #: ★ **上一次为哪一天停过**（story_day 日界检查点的幂等标记，2026-10-10 重写）。
        # [EN] : ★ **Which day the last pause was for** (idempotency marker for the story_day day-boundary
        # [EN] checkpoint, rewritten 2026-10-10).
        #: 以前这里是 `hasattr(self, '_last_story_day_pause')` 判断 ——
        #: 属性**只在第一次暂停时才被创建**，于是"开跑后的第一拍"必然满足
        #: `not hasattr(...)` ⇒ **每逢开跑/续跑都白停一次**。真机上的样子：
        #: 用户 23:01 点了「开始推演」（第 1 天已经写好 29 幕、本来就在这一天
        #: 当中），跑了一拍、23:06:55 就停了。而按旋钮的本意
        #: （「每隔 N 虚拟日暂停」，说明书写着「避免一口气跑完」）——
        #: 我们**并没有**进入新的一天，不该停。
        # [EN] : This used to be a `hasattr(self, '_last_story_day_pause')` check --
        # [EN] : the attribute **is only created on the first pause**, so "the first beat after starting"必然
        # [EN] satisfies
        # [EN] : `not hasattr(...)` => **wastes a pause on every start/resume**. On a real machine it looked
        # [EN] like this:
        # [EN] : user clicked "Start Simulation" at 23:01 (day 1 already had 29 scenes written, and was already
        # [EN] on this day
        # [EN] : in the middle of it), ran one beat, and at 23:06:55 it stopped. But by the knob's intent
        # [EN] : ("pause every N virtual days", the manual says "avoid running it all in one go") --
        # [EN] : we had **not** entered a new day, so it should not have stopped.
        #: 现在由 `run()` 在开跑时把它设成**当前那一天**：中间的这一天先跑完，
        #: 到下一个日界（`game_day` 变了）才停。`None` = 还没开跑过
        #: （探针/判据直接调 `_tick()` 会走这条路，行为与以前一致）。
        # [EN] : Now `run()` sets it to **the current day** on start: finish out the middle of this day first,
        # [EN] : and only stop at the next day boundary (`game_day` changed). `None` = never started yet
        # [EN] : (probes/criteria that call `_tick()` directly take this path, behavior same as before).
        self._last_story_day_pause: int | None = None

        # ── 时间与节拍（见模块 docstring）──
        self._last_mono: float | None = None   # 上一圈的真实时刻
        # **第一拍立刻就来**：否则点了「开始推演」要干等一个拍长才有动静
        # （TIME_RATIO=1、一拍 15 故事秒 = 15 秒空白），看着像卡住了。
        # 之后才按节拍走。
        # [EN] -- Time and beats (see module docstring) --
        # [EN] Real timestamp of the previous loop
        # [EN] Story seconds not yet accumulated into a full minute
        # [EN] **The first beat comes immediately**: otherwise clicking "Start Simulation" means waiting a full
        # [EN] beat length before anything happens
        # [EN] (TIME_RATIO=1, one beat is 15 story seconds = 15 seconds of blank), looks like it's stuck.
        # [EN] Only after that does it follow the beat cadence.
        self._beat_acc = float(max(1, CFG.i("BEAT_SECONDS")))
        self._game_sec = 0.0                   # 本轮的累计故事秒（给节拍器用）
        self._game_min = 0.0                   # 本轮的累计故事分钟（给"安静门槛"用）
        #: ★★★ 2026-10-26：故事时间的**分钟累加器**（不足一分钟的零头攒在这里）。
        #:
        #: 为什么用分钟而不是秒：一拍推多久是**分钟**量级（2.4 / 29 / 30），
        #: 用秒做累加器就得到处 ×60 ÷60，而"单位混用"是这类错的老来源。
        #: ⚠ 原来叫 `_sec_acc`（秒），现在语义变了 —— 改名是为了让"还按秒算"的
        #:   旧代码一眼报 AttributeError，而不是静默算出 60 倍。
        # [EN] ★★★ 2026-10-26: the story-time **minute accumulator** (fractions of a minute live
        # [EN] here). Minutes rather than seconds because a beat's duration is measured in minutes
        # [EN] (2.4 / 29 / 30); a seconds accumulator would need x60/÷60 everywhere, and mixed units
        # [EN] are the classic source of this bug. ⚠ It used to be `_sec_acc` (seconds); renaming
        # [EN] makes any leftover "still in seconds" code fail loudly with AttributeError instead of
        # [EN] silently computing 60x.
        self._min_acc = 0.0
        #: ★★★ 2026-10-26：**这一站（这一天）已经走了多少故事分钟**。
        #:
        #: 干什么用：过天时要把这一站剩下的故事时间**一次跳掉**（"此后三个月无事"），
        #: 所以要记"已经走了多少、还差多少"。
        #: ⚠ 只记**站内**的流逝：过天时清零（新的一天是新的站）。
        #: ⚠ `_maybe_skip_idle` 跳掉的分钟**也要计进来** —— 否则"跳过的时间不算数"，
        #:   这一站的故事时长会超出跨度档（跳 3 次 30 分钟就多出一个半小时）。
        # [EN] ★★★ 2026-10-26: **how many story minutes this station (this day) has walked**.
        # [EN] Used at the day boundary to jump the station's remaining story time in one go
        # [EN] ("nothing happened for three months"). ⚠ Only intra-station time counts; reset at
        # [EN] the day boundary. ⚠ Minutes skipped by `_maybe_skip_idle` **must count too** --
        # [EN] otherwise skipped time is free and the station overshoots its span tier.
        self._walked_min = 0
        self._last_quiet_min = -10 ** 9        # 上次写「片刻无话」时的故事分钟
        #: ★ 2026-10-14：上次补**环境白描**时的故事分钟（`AMBIENT_MINUTES` 那条通路）。
        #: 用 `-10**9` 而不是 0 —— 0 意味着"开局要等到第一分钟才给第一句环境"；
        #: 负无穷让它**开场就来一句**（换到新场景时读者第一眼就该看见环境）。
        # [EN] : ★ 2026-10-14: the story minute when the **environmental line** was last emitted
        # [EN] (the `AMBIENT_MINUTES` path). Use `-10**9` rather than 0 -- 0 would mean "wait until
        # [EN] minute one for the first environmental line"; negative infinity lets it **fire at the
        # [EN] very start** (on entering a new scene the reader should see the environment first).
        self._last_ambient_min = -10 ** 9
        # ★★ 「没事就把时间跳过去」（2026-10-11，用户点名）——
        #   `_idle_beats` = 连着几拍**谁都没做事**（`is_noop` 那种空拍）。
        #   攒够 `SKIP_IDLE_BEATS` 就在下一拍开头把时钟一口气推走一段，
        #   并用一句旁白带过（`_maybe_skip_idle`）。
        # [EN] Cumulative story seconds this round (for the metronome)
        # [EN] Cumulative story minutes this round (for the "quiet threshold")
        # [EN] Story minute of the last written "a moment of silence"
        # [EN] ★★ "When nothing's happening, skip the time" (2026-10-11, user-specified) --
        # [EN] `_idle_beats` = how many consecutive beats **nobody did anything** (the `is_noop` kind of empty
        # [EN] beat).
        # [EN] Once `SKIP_IDLE_BEATS` accumulate, at the start of the next beat push the clock forward all at
        # [EN] once,
        # [EN] and gloss over it with a narration line (`_maybe_skip_idle`).
        self._idle_beats = 0
        #: **僵局计数**（2026-10-19）：连着几拍"大多数人在等同一件事"。
        #: 攒够 `STALL_BREAK_BEATS` 就请导演给那个悬置一个结果（`director.request_settle`）。
        #: ⚠ 与 `_idle_beats` 是**两件事**：那个数的是"谁都没动"（用来跳时间），
        #:   这个数的是"大家都在等、但等不出结果"（要动手破局）。混成一个会两头都做不好。
        # [EN] **Deadlock counter** (2026-10-19): beats in a row where most people are waiting for
        # [EN] the same thing. ⚠ Distinct from `_idle_beats`: that counts "nobody did anything" (for
        # [EN] time skipping); this counts "everyone is waiting and nothing comes of it".
        self._stall_beats = 0
        #: 上一拍"说了已经说过的话"的**人次**（`_maybe_retry_repeat` 累加）。
        #: 两人以上同拍撞上 ⇒ 这场戏没新话可说，也算僵局（见 `stall_beats` 的 `stuck`）。
        # [EN] Duplicate-line count of the previous beat (accumulated by `_maybe_retry_repeat`).
        # [EN] Two or more in one beat => the scene has nothing new to say => also a deadlock.
        self._dup_speaks = 0
        #: 这一天跳过几次（状态条上要看得见；日界清零）
        # [EN] : How many times this day has been skipped (must be visible on the status bar; cleared at day
        # [EN] boundary)
        self._skips_today = 0
        #: **整轮**跳过几次（不清零）—— 日界会清零上面那个，而"这一轮到底跳没跳"
        #: 这件事不该跟着日期走（收尾/判据都读得到）。
        # [EN] : How many times the **entire round** has been skipped (not cleared) -- the day boundary clears
        # [EN] the one above, but "did this round skip or not"
        # [EN] : is not something that should follow the date (both wrapping up and criteria can read it).
        self.skips_total = 0
        #: 这一天已经写了多少字（对着 `ROUND_DAILY_WORDS` 的目标显示）
        # [EN] : How many words have been written this day (displayed against the `ROUND_DAILY_WORDS` target)
        self._day_words = 0
        self._fail_streak = 0                  # 连续决策失败次数（要能让用户看见）
        # 连续几拍「进度评估没拿到结论」（`ProgressVerdict.ok=False`）。
        # ⚠ 与 `_fail_streak` **分开计**：一个是人物决策失败，一个是导演评估失败，
        #   混在一起会把"到底哪一步坏了"糊掉。
        # [EN] Consecutive decision failure count (must be visible to the user)
        # [EN] How many consecutive beats "progress assessment got no conclusion" (`ProgressVerdict.ok=False`).
        # [EN] ⚠ Counted **separately** from `_fail_streak`: one is character decision failure, the other is
        # [EN] director assessment failure,
        # [EN] mixing them blurs "which step is actually broken".
        self._progress_fail_streak = 0
        #: 上一次**真的问过**进度评估时的输入签名（当前节点 + 最近事件）。
        #: 输入一个字都没变就不再问第二遍 —— 见 `_check_progress` 里那段说明。
        # [EN] : Input signature of the last time progress assessment was **actually asked** (current node +
        # [EN] recent events).
        # [EN] : If the input hasn't changed a single character, don't ask a second time -- see the explanation
        # [EN] in `_check_progress`.
        self._progress_sig: tuple | None = None

        # ── 客流与群演（2026-10-06）──
        # 自己的随机源：群演用哪个"一行"、造不造，都要**可复现**（验证脚本靠它）。
        # [EN] -- Foot traffic and extras (2026-10-06) --
        # [EN] Its own random source: which "line" an extra uses, whether to spawn them, must all be
        # [EN] **reproducible** (validation scripts depend on it).
        self._rng = random.Random()
        self._idle_streak = 0                  # 连续几拍"全员原地打转"（反空转闸用）
        # [EN] Consecutive beats of "everyone spinning in place" (for the anti-idle gate)

        # ── 后台批次器（`BACKGROUND_MODE`，设计稿 §五「前台/后台双制」）──
        # 2026-10-06 之前这四个旋钮（`BACKGROUND_MODE` / `BACKGROUND_TICK_MINUTES`
        # / `PROMOTE_ON_STAGE` / `BACKGROUND_EVENT_RATE`）**一个都没人读** ——
        # "后台人物"只是装配时贴的一个 `role` 标签，既不行动也不留记忆。
        # 现在真有批次器在跑（见 `sim/backstage.py`）。**必须建在 `_rng` 之后**：
        # 它拿的是同一个随机源，否则群演与后台的随机序列会互相错位。
        # [EN] -- Background batcher (`BACKGROUND_MODE`, design doc §5 "foreground/background dual system") --
        # [EN] Before 2026-10-06 these four knobs (`BACKGROUND_MODE` / `BACKGROUND_TICK_MINUTES`
        # [EN] / `PROMOTE_ON_STAGE` / `BACKGROUND_EVENT_RATE`) **were read by nobody** --
        # [EN] "background characters" were just a `role` tag stuck on at assembly time, neither acting nor
        # [EN] retaining memory.
        # [EN] Now there's an actual batcher running (see `sim/backstage.py`). **Must be created after
        # [EN] `_rng`**:
        # [EN] it uses the same random source, otherwise the extras' and background's random sequences will
        # [EN] desync.
        self._backstage = BackstageBatcher(
            world, agents, db, self._rng,
            on_warn=lambda tag, msg: self._push_narrative(msg, 0, kind=S.NOTE))
        # 这一拍的动作里被点到名的**后台**人物（下一批后台批次会把他们拉上台）。
        # [EN] **background** characters named in this beat's actions (the next background batch will bring
        # [EN] them on stage).
        self._pending_mention: set[str] = set()
        # ★ 影视镜头卡（`FILM_MODE` / `DISPLAY_FILM_CARDS`，2026-10-06 接）——
        #   以前这两个旋钮零读取，"以后拿去拍剧"这件事在程序里不存在。
        #   这里只收集；落盘在 `_end_day`（`分镜表.md` + 段首）。
        # [EN] ★ Film shot cards (`FILM_MODE` / `DISPLAY_FILM_CARDS`, hooked up 2026-10-06) --
        # [EN] Previously these two knobs had zero reads, and "shoot a drama with it later" didn't exist in the
        # [EN] program.
        # [EN] Here it only collects; persistence happens in `_end_day` (`分镜表.md` + section header).
        self._film_cards: list[dict] = []

        # ★★ 剧组（`crew/`，2026-10-07）——**这一班人怎么排班见 `crew/studio.py`**。
        #   为什么建在 `RunLoop` 里：它是"一天的班次"的编排者，而一天的边界
        #   正是这个类在管的（`_compose_day` / `_end_day`）。
        #   `on_note` 走 `_push_narrative`，与其它播报通道同一个落点。
        #   ★ `on_stage` 是**另一条**：它报的是"某段流程走完了"（只有阶段名与
        #     用时），而 `on_note` 报的是"某个职位交了一份活"。用户要的
        #     「过程用小的消息（只显示阶段名和用时，不真实输出内部细节）」
        #     走的就是 `on_stage` 这条 —— 它**结构上拿不到产出内容**。
        # [EN] ★★ Crew (`crew/`, 2026-10-07) -- **see `crew/studio.py` for how this crew is scheduled**.
        # [EN] Why it's built in `RunLoop`: it is the orchestrator of "a day's shift", and the day boundary
        # [EN] is exactly what this class manages (`_compose_day` / `_end_day`).
        # [EN] `on_note` goes through `_push_narrative`, same endpoint as the other broadcast channels.
        # [EN] ★ `on_stage` is **a different** one: it reports "a certain process has finished" (only stage
        # [EN] name and
        # [EN] duration), whereas `on_note` reports "a certain role delivered a piece of work". What the user
        # [EN] wanted,
        # [EN] "use small messages for the process (only show stage name and duration, don't actually output
        # [EN] internal details)"
        # [EN] is exactly the `on_stage` path -- it **structurally cannot access the output content**.
        self.studio = CREWSTUDIO.Studio(world, db, run,
                                        on_note=self._on_crew_note,
                                        on_stage=self._stage_push,
                                        on_work=self._work_push,
                                        # ★ 中栏那条"出工中…"由 `call()` 明确触发
                                        #   （`audit` 不发中栏消息，见 `_work_push`）
                                        # [EN] The "working..." line is triggered explicitly by
                                        # `call()` (`audit` sends no middle-column message)
                                        on_line=self._crew_line_begin)
        # ★★ **剧本审读**（2026-10-08）—— 两件事同一个人管：
        #   ① **记**：`self.script_log` 把**一切上屏的东西**按顺序记下来
        #      （动作 / 对话 / 旁白 / 场景切换 / 伏笔激活 / 导演动作 / 阶段…）。
        #      零成本，所以每一拍都记。
        #   ② **审**：`_script_review()` 在**上屏之前**把新生成的东西
        #      放到上面那份台账里过一遍，不通过就改写或拦下。
        #   它是**独立的一个职位**（名册里的 `script_doctor`，见 `crew/roster.py`），
        #   **不是导演兼职** —— 用户原话：「你看是否有独立的Agent 而不是导演在
        #   盯着演员说的每一句话 没有就做一个」。
        # [EN] ★★ **Script review** (2026-10-08) -- two things handled by the same person:
        # [EN] ① **Record**: `self.script_log` records **everything put on screen** in order
        # [EN] (actions / dialogue / narration / scene changes / foreshadow activation / director actions /
        # [EN] stages...).
        # [EN] Zero cost, so it records every beat.
        # [EN] ② **Review**: `_script_review()` runs newly generated content through the ledger above
        # [EN] **before it goes on screen**, and rewrites or blocks it if it doesn't pass.
        # [EN] It is **an independent role** (the `script_doctor` in the roster, see `crew/roster.py`),
        # [EN] **not a director side job** -- user's exact words: "see whether there's an independent Agent
        # [EN] rather than the director
        # [EN] staring at every line an actor says; if not, make one".
        self.script_log = REVIEW.ScriptLog()
        #: 被审读**改写**过的句子：`新文本 → 原文`（上屏时顺手记进台账的 `原文`）。
        #: ⚠ 只留最近几十条：它是"给人查为什么改了"的，不是长期存储。
        # [EN] : Sentences that were **rewritten** by review: `new text -> original` (recorded into the
        # [EN] ledger's `原文` when going on screen).
        # [EN] : ⚠ Keep only the most recent few dozen entries: it's for "letting a human check why it was
        # [EN] changed", not long-term storage.
        self._review_rewrites: dict[str, str] = {}
        #: 上一次把台账落盘时写到第几条（一天落一次，只写增量）
        # [EN] : Which entry number the ledger was written up to on the last persist (persist once a day, write
        # [EN] only the delta)
        self._review_flushed = 0
        self._review_blocked_today = 0
        #: 审读给"这一批合起来在说一件什么事"的一句话（当天小结里用）
        # [EN] : Review's one-liner for "what this batch as a whole is talking about" (used in the day's
        # [EN] summary)
        self._review_themes: list[str] = []
        # ★ 按**类别**记的修复数（重复 / 越界 / 其他）—— 2016-10-18 加。
        #   为什么要分：这三类的处置不同（重复改不动就放行，越界可以拦），
        #   而"今天到底修了什么"只能靠这份计数回答（《剧本审读.md》与日志都用它）。
        # [EN] Fix counts **by category** (repetition / out of bounds / other), added 2026-10-18.
        # [EN] Why split: the three are handled differently, and only this counter can answer
        # [EN] "what was actually fixed today" (used by the review report and the log).
        self._review_cat_rewrite: dict[str, int] = {}
        self._review_cat_pass: dict[str, int] = {}
        # ★ 插图钩子包一层：把**美术指导 + 这一场的道具**塞进 ctx。
        #   这是"道具/美术接到工具上"的那一步 —— 只把产出写成一份 MD，
        #   画面一点都不会变（那种"接线"是装饰）。
        #   ⚠ 包在**唯一的注入点**上（`self.image_hook`）：三条出图路径
        #     （ascii / ai / png）都从 `ctx` 取，包在这里不可能漏掉某一条。
        # [EN] ★ Illustration hook wrapped in a layer: stuff **art director + this scene's props** into ctx.
        # [EN] This is the step of "props/art hooked up to tools" -- only write the output as one MD,
        # [EN] The screen won't change at all (that kind of "wiring" is decorative).
        # [EN] ⚠ Wrap it at the **single injection point** (`self.image_hook`): all three image-output paths
        # [EN] (ascii / ai / png) read from `ctx`, so wrapping here cannot miss any of them.
        self._raw_image_hook = image_hook
        if image_hook is not None:
            self.image_hook = self._crew_image_hook(image_hook)

        # 使用阅读节奏器
        # [EN] Use the reading-pace meter
        self.display = display_rhythm

    def _crew_image_hook(self, inner):
        """把内层出图钩子包一层，替它补上剧组的两样东西。

        `takes_ctx` 必须**照抄**内层的值：`SceneBuilder` 靠它决定传两个还是三个
        参数（两参的老钩子在测试里到处都是）。抄错的表现是"插图全没了"。
        
                English:
        Wrap the inner image-generation hook to supply the two things the crew needs for it.
                `takes_ctx` must **copy verbatim** the inner value: `SceneBuilder` uses it to decide whether to pass two or three
                args (two-arg old hooks are everywhere in tests). Getting it wrong shows up as "all illustrations gone".
        """
        took = bool(getattr(inner, 'takes_ctx', False))

        def _hook(kind, key, ctx=None):
            ctx = dict(ctx or {})
            try:
                ctx.setdefault('crew', self.studio.image_prefix())
                p = self.studio.note_of('props')
                names = [str(x.get('名称') or '')
                         for x in ((p.data or {}).get('道具') or [])
                         if isinstance(x, dict)] if (p is not None and p.ok) else []
                ctx.setdefault('crew_props', [n for n in names if n])
                # ★ 视觉参考图（P3，2026-10-15）：当前这一场若有视觉参考图，
                #   作为 image-to-image 锚点注入给内层钩子（内层 scene 分支会
                #   把它传给 generate_ai_image）。没有就不注入（不塞假的）。
                # [EN] Visual reference (P3): inject the current scene's reference for image-to-image.
                if kind == 'scene':
                    try:
                        _ds = getattr(self.world, 'day_script', None)
                        _refs = getattr(_ds, 'refs', None) if _ds is not None else None
                        if _refs:
                            _r = _match_visref_scene(_refs, ctx.get('place') or str(key))
                            if _r:
                                ctx['visref'] = _r
                    except Exception:                            # noqa: BLE001
                        pass
            except Exception:                                    # noqa: BLE001
                pass                    # 剧组没出活 → 老路子照常（不塞假的）
                # [EN] The crew produced nothing → fall back to the old path (don't inject anything fake)
            try:
                return inner(kind, key, ctx) if took else inner(kind, key)
            except TypeError:
                # 内层其实只收两个参数（`takes_ctx` 标记失真）→ 退回两参，
                # 别因为一层包装把插图整条弄没。
                # [EN] The inner layer actually only accepts two arguments (`takes_ctx` flag is unreliable) → fall back
                # [EN] to two args,
                # [EN] don't let one layer of wrapping wipe out the entire illustration.
                return inner(kind, key)

        _hook.takes_ctx = True
        return _hook

    # ── 剧组播报（`crew/studio.Studio` 的 on_note 落点）──────────────
    # [EN] ── crew broadcast (`crew/studio.Studio`'s on_note landing point) ──────────────
    def _on_crew_note(self, note) -> None:
        """把一份剧组产出报成**一条状态**（唯一例外：复盘给的是内容）。

        ★★ 2026-10-07 改口径。用户：「窗口输出的内容你把作者写小说 剧作家创作剧本
        剧组排练 然后重新修改 再排练 再修改等过程用**小的消息**（只显示阶段名和用时，
        **不真实输出内部细节**，但细节写入日志）…… 别的不要加到运行界面中间窗口」。

        改之前这里是"（剧组 · 美术）水墨淡彩、纸本质感，低饱和…"——**整段产出**
        推到读者眼前。读小说读到一个美术指导，那是拍摄现场的花絮。

        现在按**这份产出是什么**分四种去处（判据盯着这四条）：

        | 这份产出 | 上屏成什么 | 为什么 |
        |---|---|---|
        | **没出活** | `NOTE` + 原因 | 那是**故障信号**，不是内容。压成"没出活"会让作者不知道是关掉了、模型挂了、还是没有可查的正文 |
        | **复盘**（今日总结） | `SUMMARY` + **正文** | 用户白名单里点名的"一天结束后的总结"——**唯一**以内容上屏的剧组产出 |
        | **语言审校 / 去 AI 命中** | `NOTE` + 一句话 | 那是"要作者动手改"的信号，正文在 `语言审校.md` 里 |
        | 其余 | `CREW` **只有状态** | 「只显示状态和已经操作的时间，不显示细节」 |

        ⚠ 产出一个字没少：它照旧落进各自的 `.md`、照旧进日志
          （`crew/studio._save_note` + `Studio.call` 的 `_LOG`），也照旧进台账。
        
                English:
        Report one crew output as **a single status** (the only exception: a retrospective is given as
        content).
                ★★ 2026-10-07 changed the policy. User: "For the content output in the window, take the author writing the novel, the playwright writing the script,
                the crew rehearsing, then revising, rehearsing again, revising again, etc. -- use **small messages** (show only the stage name and elapsed time,
                **do not actually output internal details**, but write details to the log)... don't add anything else to the middle window of the running UI".
                Before the change this was "(crew · art) ink wash, paper texture, low saturation..." -- **the entire output**
                pushed in front of the reader. Reading a novel and hitting an art director is like behind-the-scenes footage from a shoot.
                Now split into four destinations by **what this output is** (the criteria track these four):
                | this output | what goes on screen | why |
                |---|---|---|
                | **produced nothing** | `NOTE` + reason | that is a **failure signal**, not content. Squashing it to "produced nothing" leaves the author unsure whether it was turned off, the model crashed, or there was no body text to check |
                | **retrospective** (end-of-day summary) | `SUMMARY` + **body text** | the "summary after a day ends" named in the user's whitelist -- the **only** crew output shown on screen as content |
                | **language review / de-AI hit** | `NOTE` + one sentence | that is a "author must take action" signal; body text is in `语言审校.md` |
                | the rest | `CREW` **status only** | "show only the status and the time already operated, not the details" |
                ⚠ Not one word of output is lost: it still goes into the respective `.md`, still into the log
                  (`crew/studio._save_note` + `_LOG` of `Studio.call`), and still into the ledger.
        """
        try:
            role = CREWSTUDIO.ROSTER.role(note.role)
            secs = float((note.data or {}).get('用时') or 0.0)
            # ★★★ 2026-10-23（用户点名）：这一条带着**展开内容**与**要改哪一条**。
            #   `update_key=note.role` = "把这一位那条『出工中…』原地改成现在这句"，
            #   于是界面上一件事只有一行字：先在跑、然后变成已交活。
            #   `detail` 里放**整份产出**：用户点开就是要看"这一步到底产出了什么"，
            #   它本来就落在各自的 `.md` 里，这里只是给同一份内容开第二个出口。
            #   ⚠ `detail` 与 `update_key` 都只在 `CREW_EXPAND` 开着时才给 ——
            #     关掉这个开关要回到"一行状态、点不开"的旧样子，
            #     否则界面上会留着一堆能点但"不该点"的箭头。
            # [EN] ★★★ 2026-10-23 (named by the user): this entry carries **what to show
            # [EN] when expanded** and **which entry to rewrite**. `update_key=note.role`
            # [EN] means "rewrite this role's 'working...' line into this sentence in place",
            # [EN] so one event is one line on screen: running, then handed in.
            # [EN] `detail` holds **the whole output**: expanding is exactly "what did this
            # [EN] step produce", and that content already goes into its own `.md`; this just
            # [EN] adds a second outlet for the same content.
            # [EN] ⚠ Both `detail` and `update_key` are only supplied when `CREW_EXPAND` is
            # [EN] on -- turning the switch off must restore the old "one status line, not
            # [EN] clickable" look, otherwise the UI keeps a pile of arrows that should not
            # [EN] be there.
            try:
                _expand = CFG.b('CREW_EXPAND')
            except Exception:                                    # noqa: BLE001
                _expand = True
            _det = ({'state': 'done' if note.ok else 'error',
                     'role': str(note.role or ''), 'name': role.name,
                     'body': str(note.body or ''),
                     'why': str(note.why or ''),
                     'secs': secs} if _expand else None)
            _uk = str(note.role or '') if _expand else ''
            if not note.ok:
                self._push_narrative(
                    f'（剧组 · {role.name}）这次没出活：{note.why}', 3, kind=S.NOTE,
                    detail=_det, update_key=_uk)
                return
            if note.role == 'reviewer':
                # ★ **唯一的例外**：复盘给的是一份给人读的结论。
                #   用户白名单里那句「一天自动停止之后的总结」就是它。
                # [EN] ★ **The only exception**: the retrospective gives a conclusion meant for humans to read.
                # [EN] In the user whitelist, that line "a summary after one day's auto-stop" is exactly this.
                self._push_narrative(
                    STR.summary_block('今日总结', note.body or note.title),
                    1, kind=S.SUMMARY, detail=_det, update_key=_uk)
                return
            if note.role == 'polisher':
                # ★ 这一句指向哪儿，看**复盘开没开**（2026-10-12 用户要求
                #   「语言审校并进今日总结」）：开着的话，正文就在**紧随其后**的
                #   那条「今日总结」里（用户就看得见了），指向文件反而让他去翻磁盘；
                #   关着的话总结不存在，只能照旧指向那份 md。
                #   ⚠ 措辞要与 `crew/studio.wrap()` 的实际行为一致 ——
                #    那份 md **照旧在写**（一句话都没少），只是多了一个出口。
                # [EN] Where this line points depends on **whether the retrospective is on** (user
                # [EN] request 2026-10-12: "merge the language review into today's summary"): when it is
                # [EN] on, the body is in the "today's summary" entry **right after this one** (so the
                # [EN] user can see it), and pointing at the file would just send him digging through
                # [EN] disk; when it is off there is no summary, so it can only point at that md.
                # [EN] ⚠ The wording must match what `crew/studio.wrap()` actually does -- that md is
                # [EN] **still being written** (not one word less); this just adds an outlet.
                _tail = (t(' —— 细节并进了下面的「今日总结」')
                         if CFG.b('CREW_REVIEW')
                         else t(' —— 细节在「语言审校.md」'))
                self._push_narrative(
                    f'（剧组 · {role.name}）{note.title}{_tail}', 3, kind=S.NOTE,
                    detail=_det, update_key=_uk)
                return
            # ★ `full` 档多给一句**标题**（"今天 2 处"）——仍然不是产出全文。
            #   这是三档里"多一点信息"的那一档，用来对照排查。
            # [EN] ★ The `full` tier adds one more line: the **title** ("2 spots today") — still not the full
            # [EN] output text.
            # [EN] This is the "a bit more information" tier of the three, used for cross-checking.
            detail = (note.title or '') if (
                str(CFG.s('CREW_SCREEN') or '').strip().lower() == 'full') else ''
            self._push_narrative(
                STR.crew_line(role.name, '已交活', secs, detail=detail),
                3, kind=S.CREW, detail=_det, update_key=_uk)
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('crew_note', f'剧组播报失败（不影响推演）：{e!r}')

    # ── 剧组阶段（2026-10-07）──────────────────────────────────────────
    # [EN] ── crew phase (2026-10-07) ──────────────────────────────────────────
    def _stage(self, key: str):
        """量一段流程的用时，推一条**阶段小消息**（`▸ 剧组排练 · 3.2s`）。

        实现只有一处：`crew/studio.Studio.stage` —— 这里只是代转（循环与制片厂
        都能打阶段标记，但计时的代码不该有两份）。
        没有制片厂时退化成"什么都不报"。

        ⚠ **要 `getattr` 取 `studio`**：`RunLoop` 有几条**不走 `__init__`** 的
          构造路径（`RunLoop.__new__` + 手工填几个属性 —— 单测与老夹具都用它）。
          写死 `self.studio` 会让那些路径上的 `pause()` / `_stage()`
          直接 `AttributeError`（`verify_branch` 当场抓到：它建 loop 时没有 studio，
          一 `pause()` 就炸）。阶段播报是**附加信息**，不该成为硬依赖。
        
                English:
        Measure the elapsed time of a process stage, emit a **stage small message** (`▸ 剧组排练 · 3.2s`).
                Only one implementation: `crew/studio.Studio.stage` -- here it just forwards (both the loop and the studio
                can emit stage markers, but the timing code should not exist twice).
                With no studio it degrades to "report nothing".
                ⚠ **Use `getattr` to get `studio`**: `RunLoop` has several construction paths that **do not go through `__init__`**
                  (`RunLoop.__new__` + manually filling a few attributes -- used by unit tests and old fixtures).
                  Hard-coding `self.studio` makes `pause()` / `_stage()` on those paths
                  throw `AttributeError` directly (`verify_branch` catches it on the spot: it creates a loop without a studio,
                  and as soon as it `pause()`s it blows up). Stage reporting is **extra information** and should not become a hard dependency.
        """
        st = getattr(self, 'studio', None)
        return st.stage(key) if st is not None else contextlib.nullcontext()

    def _stage_push(self, key: str, secs: float = 0.0, ok: bool = True) -> None:
        """**制片厂那一侧的阶段回调**（`Studio.stage` → 这里 → 界面）。

        用户：「把作者写小说 剧作家创作剧本 剧组排练 然后重新修改 再排练 再修改
        等过程用**小的消息**（只显示阶段名和用时，不真实输出内部细节，
        但细节写入日志）」。

        ⚠ 这里只拿得到 `(阶段名, 用时, 成败)` —— **产出内容根本没有传进来**，
          想推也推不出去。这是"只报状态"在**结构上**的保证，不是靠自觉
          （与 `Studio.stage` 的 `yield` 不回传东西是同一条）。
        
                English:
        **The studio-side stage callback** (`Studio.stage` → here → UI).
                User: "Take the author writing the novel, the playwright writing the script, the crew rehearsing, then revising, rehearsing again, revising again,
                etc. -- use **small messages** (show only the stage name and elapsed time, do not actually output internal details,
                but write details to the log)".
                ⚠ Here we only get `(stage_name, elapsed_time, success_or_failure)` -- **output content is not passed in at all**,
                  so it cannot be pushed out even if we wanted to. This is the **structural** guarantee of "report status only", not relying on self-discipline
                  (same as `Studio.stage`'s `yield` not returning anything).
        """
        try:
            self._push_narrative(
                STR.stage_line(key, secs, ok=ok), 3, kind=S.STAGE)
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('stage', f'阶段播报失败（不影响推演）：{e!r}')

    def _stage_start(self, key: str) -> None:
        """**没有耗时可言**的那种阶段（开演 / 暂停 / 继续）。

        与 `_stage()` 共用同一条播报通道（转到 `Studio.stage_now`）——
        两处各报一处的话，"谁在报阶段"就有两个入口，探针与判据只能看到一个
        （反例法第一次跑就是这么栽的：`wrap_meeting` 报了，但探针收不到）。
        `studio` 缺失时**静默跳过**（见 `_stage` 那条说明）。
        
                English:
        **Stages with no elapsed time to speak of** (start / pause / resume).
                Shares the same reporting channel as `_stage()` (forwards to `Studio.stage_now`) --
                if the two each reported separately, "who reports the stage" would have two entry points, and probes and criteria could see only one
                (that's exactly how the first run of the counterexample method failed: `wrap_meeting` reported, but the probe got nothing).
                When `studio` is missing, **silently skip** (see the note on `_stage`).
        """
        st = getattr(self, 'studio', None)
        if st is not None:
            st.stage_now(key)

    # ── 回调注册（TUI 连接点）──────────────────────────────────────────
    # [EN] ── callback registration (TUI connection points) ──────────────────────────────────────────
    def on_rollback(self, cb: Callable[[int], None]) -> None:
        """注册**回档**回调：`cb(n)` = "从屏幕上撤掉最近 n 条"。

        与 `on_narrative` 是**逆操作**（一个加一个减）——
        导演回档时两处必须一起动，不然屏幕与文件会对不上。
        界面没接（脚本/无头）时就是 `None`，回档照常只作用于剧本。
        
                English:
        Register the **rollback** callback: `cb(n)` = "remove the most recent n items from the screen".
                It is the **inverse operation** of `on_narrative` (one adds, one removes) --
                when the director rolls back, both must move together, otherwise the screen and the file will not match.
                When the UI is not attached (script / headless) it is `None`, and rollback still only affects the script.
        """
        self._on_rollback = cb

    def on_narrative(self, cb: Callable[..., None]) -> None:
        """`cb(text, priority, kind='')` —— `kind` 是词条类型（见 `display.script`），
        界面靠它决定这一行用哪种样式（对白 / 旁白 / 环境 / 回想…）。
                English:
        `cb(text, priority, kind='')` -- `kind` is the entry type (see `display.script`),
                the UI uses it to decide which style this line uses (dialogue / narration / setting / recollection...).
        """
        self._on_narrative = cb

    def on_divider(self, cb: Callable[..., None]) -> None:
        """`cb(divider)` —— 日 / 幕 / 故事 / 模块的分界符（`display.dividers`）。
                English:
        `cb(divider)` —— divider for day / act / story / module (`display.dividers`).
        """
        self._on_divider = cb

    def on_status(self, cb: Callable[..., None]) -> None:
        """`cb(key, **kw)` —— 细粒度运行状态，界面拿它渲染底部那条状态提示。
                English:
        `cb(key, **kw)` —— fine-grained run status; the UI uses it to render the status hint at the
        bottom.
        """
        self._on_status = cb

    def on_self_pause(self, cb: Callable[[str], None]) -> None:
        """`cb(why)` —— **主循环自己开的暂停**（日界检查点 / 存档点 / 岔路口 / 导演介入）。

        ⚠ 与 `on_status` 是**两件事**，不能合并：`on_status` 说的是"这一步在干什么"
          （正在生成 / 正在核对进度），它**每拍都会被覆盖**；而"我停了、在等人"
          是一个**状态**，一旦报出去就不能被后面的细粒度状态盖掉
          —— 真机上的表现就是"停了 33 分钟，屏幕还写着正在核对进度"。
          所以这条走会话层（`RunSession._on_loop_pause`），由它去改 `session.status`，
          界面再从会话状态推出「已暂停 —— 等你点「继续」」。
        
                English:
        `cb(why)` —— **a pause initiated by the main loop itself** (day-boundary checkpoint / save point
        / fork / director intervention).
                ⚠ This is **two separate things** from `on_status` and must not be merged: `on_status` says "what this step is doing"
                  (generating / checking progress), and it **gets overwritten every beat**; whereas "I've stopped and am waiting for someone"
                  is a **state** that, once reported, must not be overwritten by later fine-grained status
                  —— on the real machine this shows up as "stopped for 33 minutes, screen still says checking progress".
                  So this one goes through the session layer (`RunSession._on_loop_pause`), which updates `session.status`,
                  and the UI then derives "Paused —— click Resume to continue" from the session state.
        """
        self._on_self_pause = cb

    def on_scene(self, cb: Callable[[dict], None]) -> None:
        """`cb({'place','segment','cast','day'})` —— **换地方了**。

        界面据此重画小地图（矢量、零成本）。与其它播报通道一样：
        回调出错不影响推演。
        
                English:
        `cb({'place','segment','cast','day'})` —— **changed location**.
                The UI redraws the minimap based on this (vector, zero cost). Same as other broadcast channels:
                a callback error does not affect the simulation.
        """
        self._on_scene = cb

    def on_work(self, cb: Callable[[str, str], None]) -> None:
        """`cb(职位key, state)` —— **某位剧组成员开始/结束出工**（2026-10-08）。

        用户：「右侧的剧组成员 谁在干活请高亮显示 等不干活了再恢复普通样式
        以让用户知道谁在干活」。

        `state` 就是台账里的那四个词：`working`（刚开始出工）/ `done`（交活了）
        / `idle`（这一趟没成，落回待命）/ `off`（这个职位没启用）。

        ⚠ 签名里**没有产出** —— 这是"谁在忙"的通道，产出走 `on_note`。
          与 `on_stage` 同一条结构上的纪律（见 `_stage_push`）。
        ⚠ 界面是**事件驱动**重画那一栏的，不靠轮询：出工是一阵一阵的，
          0.5 秒一轮的定时刷新天然会漏掉短出工（演示模式下几十毫秒就出完了）。
        
                English:
        `cb(role key, state)` —— **a crew member starts/ends work** (2026-10-08).
                User: "Highlight which of the crew members on the right are working, and restore normal style when they stop
                so the user knows who is working".
                `state` is exactly the four words in the ledger: `working` (just started work) / `done` (handed in the work)
                / `idle` (this run failed, back to standby) / `off` (this role is not enabled).
                ⚠ There is **no output** in the signature —— this is the "who is busy" channel; output goes through `on_note`.
                  Same structural discipline as `on_stage` (see `_stage_push`).
                ⚠ The UI redraws that column **event-driven**, not by polling: work comes in bursts,
                  a 0.5-second periodic refresh will naturally miss short work stints (in demo mode they finish in tens of milliseconds).
        """
        self._on_work = cb

    def _work_push(self, key: str, state: str) -> None:
        """**制片厂那一侧的出工状态回调**（`Studio.call` → 这里 → 界面）。
                English:
        **The studio-side work status callback** (`Studio.call` → here → UI).
        ★★★ 2026-10-23（用户点名）：`working` 那一刻**在中栏起一条消息**，
          它之后会被"已交活"那一条**原地改掉**（`update_key`），
          于是"正在执行"与"已完成"是同一条消息的两个状态 —— 用户要的正是这个。

        ★ 为什么**不**走 `_push_narrative`：那条路会过**审读闸**并**计字数**。
          「出工中…」不是内容，让它进审读闸等于拿一句状态去撞规则表；
          让它计字数则会把"今天写了多少字"悄悄抬高（每条十来个字，一天几十条）。
          ⇒ 它是**过程信号**，走 `on_crew_line` 这条轻通道；真正的产出那条
          （"已交活"）照旧走 `_push_narrative`，一个字都不少。

        ★ 为什么这条要**先于**任何子步骤发出：这几十秒里界面得有"东西可点"，
          否则用户看到的还是"什么都不动"（而他刚要求的就是**看着它在想**）。

            English:
        ★★★ 2026-10-23 (named by the user): at `working`, **open a message in the middle
        column**, which the "handed in" line later **rewrites in place** (`update_key`), so
        "executing" and "finished" are two states of one message -- exactly what was asked.
        ★ Why it does **not** go through `_push_narrative`: that path runs the **review
        gate** and **counts words**. "Working..." is not content; sending it through the
        gate means hitting the rule table with a status string, and counting it quietly
        inflates "how many words were written today" (a dozen characters per call, dozens
        of calls a day). So it is a **process signal** on the light `on_crew_line` channel;
        the real output line ("handed in") still goes through `_push_narrative`, not one
        word less.
        ★ Why this line must go out **before** any sub-step: the UI needs "something to
        click" during those tens of seconds, otherwise the user still sees "nothing
        happening" -- right after asking to **watch it think**.
        """
        if str(state) == 'working':
            # （这里**不再**起中栏那条消息：它由 `Studio.call` 通过 `on_line` 明确触发。
            #   挂在这里的话 `audit()`（每拍一次的审读闸）也会起一条，
            #   而它按设计**不发**中栏消息 —— 每拍一行会把正文淹掉。）
            # [EN] (No longer opening the middle-column message here: `Studio.call` triggers
            # it explicitly through `on_line`. Hung here, `audit()` (the per-beat review
            # gate) would open one too, and it deliberately sends **no** middle-column
            # message -- one row per beat would drown the prose.)
            pass
        cb = self._on_work
        if cb is None:
            return
        try:
            cb(str(key), str(state))
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('work', f'出工状态播报失败（不影响推演）：{e!r}')

    def on_crew_line(self, cb: Callable[[str, str, dict], None]) -> None:
        """`cb(职位key, 文本, detail)` —— **一条剧组消息的"起一条 / 改一条"**（2026-10-23）。

        与 `on_narrative` 的区别只有一点：这条路**只给剧组消息用**，
        而且**不过审读闸、不计字数**（理由见 `_work_push`）。
        收到的界面按 `detail['state']` 决定画法：
          · `running` —— 先起一条（可能已有一行"出工中…"），点开看实时思考；
          · `done` / `error` —— 就把那一条**原地改掉**，点开看执行结果。

        ⚠ 没有界面（CLI / 无头判据）时 `_on_crew_line` 是 `None`：这时
          **什么都不做**是对的 —— "出工中"本来就不该进叙事流（它不是内容），
          而"已交活"那条照旧由 `_push_narrative` 发出去，一个字都没丢。

            English:
        `cb(role key, text, detail)` -- **open / rewrite one crew message** (2026-10-23).
        The only difference from `on_narrative`: this channel is **crew messages only** and
        **skips the review gate and word counting** (see `_work_push`). The UI draws by
        `detail['state']`: `running` = open a line (maybe "working..."), expand for live
        thinking; `done` / `error` = rewrite that line in place, expand for the result.
        ⚠ Without a UI (CLI / headless criteria) `_on_crew_line` is `None` and doing
        **nothing** is correct -- "working..." is not content and must not enter the
        narrative stream, while the "handed in" line still goes through `_push_narrative`.
        """
        self._on_crew_line = cb

    def _crew_line_begin(self, key: str) -> None:
        """某位**开始出工** → 中栏起一条「X · 出工中…」（带展开箭头）。

        ★ 入口是 `Studio.call` 的 `on_line`（**不是** `_work_push`）：只有真正会
          交活的那条路才该起这一行，见 `_work_push` 里的说明。

        ⚠ 名字解析失败**不影响**：退回用 key 本身（界面上显示成 `art · 出工中…`，
          不好看但可用）。宁可用 key，也不要因为"查不到中文名"整条消息不发 ——
          用户会以为"这一位没干活"。
        ⚠ `CREW_EXPAND=false` 时**连这条都不起**：那是"回到旧样子"，
          而旧样子里根本没有"出工中…"这一行。只关 `detail` 不关起头，
          会留下一行点不动的"出工中…"。
        [EN] A role **starts working** -> open "X · working..." in the middle column (with
        the expand arrow).
        ★ The entry point is `Studio.call`'s `on_line` (**not** `_work_push`): only the path
        that really hands work in should open this line (see `_work_push`).
        ⚠ A failed name lookup must not matter: fall back to the key (shows as
        `art · working...`, ugly but usable). Better the key than no message -- the user
        would think the role did nothing.
        ⚠ With `CREW_EXPAND=false` **not even this line** is opened: that switch means "back
        to the old look", which never had a "working..." row. Gating `detail` alone would
        leave an unclickable "working..." row behind.
        """
        cb = getattr(self, '_on_crew_line', None)
        if cb is None:
            return
        try:
            if not CFG.b('CREW_EXPAND'):
                return
        except Exception:                                        # noqa: BLE001
            pass
        name = str(key)
        try:
            name = CREWSTUDIO.ROSTER.role(key).name or name
        except Exception:                                        # noqa: BLE001
            pass
        try:
            cb(str(key), t('{name} · 出工中…', name=name),
               {'state': 'running', 'role': str(key), 'name': name})
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('crew_line', f'剧组消息起头失败（不影响推演）：{e!r}')

    def on_event(self, cb: Callable[[DirectorEvent], None]) -> None:
        self._on_event = cb

    def on_branch(self, cb: Callable[[list[dict]], None]) -> None:
        self._on_branch = cb

    def on_ask(self, cb: Callable[[dict], None]) -> None:
        """`cb(question)` —— **问作者一个问题**（2026-10-11）。

        `question` 的结构（界面照它画对话框，一处定义）：

        | 键 | 含义 |
        |---|---|
        | `kind` | `branch` / `intervention` / `budget` / `checkpoint` —— 决定标题与图标 |
        | `title` | 对话框标题（如「岔路口 · 往哪走」） |
        | `why` | **为什么要问你**（一行问题，用户点名要的一块） |
        | `options` | `[{'id','标题','后果'}]` —— 单选钮 |
        | `allow_custom` | 允不允许"我自己写一句"（用户点名：**一定**要有） |
        | `wait` | 等多少秒（0 = 一直等，直到回答或用户停止） |
        | `brief` | 可选的「当前故事发展」补充行（不给就由界面自己拼） |

        ⚠ 与 `on_branch` **并存**：`on_branch` 是"走向候选"这条老路的专用快递，
          判据与探针都在用它，不动它。这条是**通用的**那条。
        
                English:
        `cb(question)` —— **ask the author a question** (2026-10-11).
                Structure of `question` (the UI draws the dialog based on it, defined in one place):
                | key | meaning |
                |---|---|
                | `kind` | `branch` / `intervention` / `budget` / `checkpoint` —— determines title and icon |
                | `title` | dialog title (e.g. "Fork · Which way to go") |
                | `why` | **why it is asking you** (one-line question, a piece the user explicitly requested) |
                | `options` | `[{'id','title','consequence'}]` —— radio buttons |
                | `allow_custom` | whether to allow "I'll write my own line" (user explicitly requested: **must** have it) |
                | `wait` | how many seconds to wait (0 = wait forever, until answered or the user stops) |
                | `brief` | optional "current story development" supplementary line (if absent, the UI assembles it itself) |
                ⚠ **Coexists** with `on_branch`: `on_branch` is the dedicated express for the old "heading candidates" path,
                  and criteria and probes are all using it, so leave it alone. This one is the **general-purpose** one.
        """
        self._on_ask = cb

    def answer_ask(self, option_id: str, custom: str = "") -> None:
        """作者点了「确定」。`custom` 非空 ⇒ **以它为准**（作者亲口说的最硬）。
                English:
        The author clicked "OK". If `custom` is non-empty ⇒ **it takes precedence** (the author's own
        words are the hardest).
        """
        self._ask_answer = {'id': str(option_id or ''), 'custom': str(custom or '')}

    def cancel_ask(self) -> None:
        """作者点了「取消」⇒ **推演变成暂停**，但题留着。

        用户点名：「如果选择取消则推演变成暂停 用户点继续的时候
        继续弹出相关对话框」。所以这里**不清 `_ask_pending`** ——
        那道题还在等回答，`resume()` 会把它重新弹出来。
        
                English:
        The author clicked "Cancel" ⇒ **the simulation becomes paused**, but the question remains.
                User explicitly requested: "If cancel is chosen then the simulation becomes paused, and when the user clicks resume
                the relevant dialog should pop up again". So here we **do not clear `_ask_pending`** ——
                that question is still waiting for an answer, and `resume()` will pop it back up.
        """
        self.pause("等你回答「%s」" % str((self._ask_pending or {}).get('title') or ''))

    async def _ask(self, *, kind: str, title: str, why: str,
                   options: list[dict], allow_custom: bool = True,
                   wait: int = 0, brief: str = "",
                   data: dict | None = None,
                   notify: Callable[[dict], None] | None = None) -> dict | None:
        """出题 → 等回答。返回 `{'id','custom'}`（`custom` 非空表示作者自己写的）。

        返回 `None` 有三种情况，**调用方自己决定怎么办**（本项目一贯的分法：
        "没拿到"与"拿到了一个否"是两件事）：
          ① **没有界面**（脚本 / 无头跑）—— 不等，立刻返回（干等纯属浪费）；
          ② `wait > 0` 且到点还没答 —— 交给上层的兜底策略；
          ③ 作者点了「停止」—— `_running` 变 False。

        `notify`：**没有 `on_ask` 时的退路**。岔路口那条路还有一批老的
        判据/探针在用 `on_branch`（只吃一个 branches 列表），所以允许调用方
        塞一个"用它弹"的回调进来 —— 这样"弹问答"只有本方法一处实现，
        而老通道照样能用。

        ★★ 两种"停下"的区别（这是这套东西最容易写错的地方）

          · **取消按钮** ⇒ `cancel_ask()` 只置暂停、**不清题** ——
            本方法**继续等**。等作者点「继续」，`resume()` 把题重新弹出来，
            他答完，本方法才返回、这一拍才往下走。
            ⚠ **不能一取消就 return**：这一拍一旦返回，`_maybe_branch` 那边
              `_last_branch_day` 已经写上了，下一拍**不会再弹** ——
              题就永远丢了（用户会看到"点了继续，对话框再也不出来"）。
          · **`wait` 到点** ⇒ 真的返回 `None`，上层按策略兜底。

        ★ 老通道兼容（`kind == 'branch'` 时额外认这两个字段）：
          `_branch_choice`（挑候选）/ `_branch_custom`（自己写）。
          `verify_branch` 与 `verify_branch_dialog` 直接调
          `loop.choose_branch()`，不看本方法。
        
                English:
        Ask question → wait for answer. Returns `{'id','custom'}` (`custom` non-empty means the author
        wrote it themselves).
                There are three cases where it returns `None`, **the caller decides what to do** (the project's consistent distinction:
                "didn't get it" and "got a no" are two different things):
                  ① **No UI** (script / headless run) —— don't wait, return immediately (waiting is pure waste);
                  ② `wait > 0` and not answered by the deadline —— hand off to the upper layer's fallback strategy;
                  ③ The author clicked "Stop" —— `_running` becomes False.
                `notify`: **the fallback when there is no `on_ask`**. The fork path still has a batch of old
                criteria/probes using `on_branch` (which only takes a branches list), so the caller is allowed
                to pass in a "use this to pop up" callback —— this way "pop up Q&A" is implemented in only this one method,
                and the old channel still works.
                ★★ The difference between the two kinds of "stop" (this is the easiest thing to get wrong in this whole system)
                  · **Cancel button** ⇒ `cancel_ask()` only sets paused, **does not clear the question** ——
                    This method **keeps waiting**. It waits for the author to click "Continue"; `resume()` pops the question back up,
                    and only after they answer does this method return and this beat proceed.
                    ⚠ **Must not return immediately upon cancel**: once this beat returns, over in `_maybe_branch`
                      `_last_branch_day` has already been written, so the next beat **will not pop it up again** ——
                      the question is lost forever (the user will see "clicked Continue, but the dialog never appears again").
                  · **`wait` reaches its deadline** ⇒ genuinely returns `None`, and the upper layer falls back per policy.
                ★ Legacy channel compatibility (when `kind == 'branch'`, additionally recognizes these two fields):
                  `_branch_choice` (pick a candidate) / `_branch_custom` (write your own).
                  `verify_branch` and `verify_branch_dialog` directly call
                  `loop.choose_branch()` and do not look at this method.
        """
        q = {'kind': str(kind), 'title': str(title), 'why': str(why),
             'options': [dict(o) for o in (options or [])],
             'allow_custom': bool(allow_custom), 'wait': int(max(0, wait)),
             'brief': str(brief or ''),
             #: 题干里的**数字**（界面按当前语言重新拼句子时要用）。
             #  为什么不直接把数字写进 `why`：`why` 是中文兜底（界面在
             #  "同一个 kind 的英文版"里要用自己的句式，位置可能不一样）。
             # [EN] : the **number** in the question text (the UI needs it to reassemble the sentence in the current
             # [EN] language).
             # [EN] Why not write the number directly into `why`: `why` is the Chinese fallback (the UI
             # [EN] in "the English version of the same kind" uses its own phrasing, and the position may differ).
             'data': dict(data or {})}
        cb = getattr(self, '_on_ask', None)
        if cb is None:
            cb = notify
        if cb is None:
            return None                      # ① 没有界面：不等
            # [EN] ① No UI: don't wait
        self._ask_answer = None
        self._ask_pending = q
        try:
            cb(dict(q))
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('ask_cb', f"提问回调失败（不影响推演）：{e!r}")
            self._ask_pending = None
            return None
        legacy = str(kind) == 'branch'
        step = 0.25
        waited = 0.0
        try:
            while self._running:
                ans = self._ask_answer
                if ans is not None:
                    self._ask_answer = None
                    self._ask_pending = None
                    return ans
                if legacy:
                    # 老通道：有人调了 `choose_branch*` 就等于答了
                    # [EN] Old channel: if someone called `choose_branch*`, that counts as answered
                    if self._branch_custom:
                        self._ask_pending = None
                        return {'id': '', 'custom': self._branch_custom}
                    if self._branch_choice:
                        self._ask_pending = None
                        return {'id': str(self._branch_choice), 'custom': ''}
                if wait > 0 and waited >= wait:
                    # ② 到点：收起待答题（界面那边自己也有关表的倒计时）
                    # [EN] ② Time's up: retract the pending question (the UI side also has its own countdown for closing
                    # [EN] the table)
                    self._ask_pending = None
                    return None
                await asyncio.sleep(step)
                waited += step
            # ③ 被停止
            # [EN] ③ Stopped
            return None
        finally:
            if self._ask_pending is not None and not self._running:
                self._ask_pending = None

    def choose_branch(self, branch_id: str) -> None:
        """用户在岔路口**挑中了某个候选**（界面上点「确定」时调）。
                English:
        The user **picked one of the candidates** at the fork (called when "Confirm" is clicked in the
        UI).
        """
        self._branch_choice = branch_id
        # 两条路互斥：挑了候选就把"自己写的"清掉，否则下一拍会拿旧文本行事。
        # [EN] The two paths are mutually exclusive: once a candidate is picked, clear the "self-written" one,
        # [EN] otherwise the next tick will act on stale text.
        self._branch_custom = ""

    def choose_branch_custom(self, text: str) -> None:
        """用户在岔路口**自己写了一个走向**（不是从候选里挑的）—— 2026-10-07 加。

        用户要的是「最下面有一个文本框，用户可以自己输入内容**替代**几个选项」，
        所以他写下的这句话就**等价于**选中一个候选，只是作者是他而不是导演。

        ⚠ 落库口径与「挑候选」完全一致（写事件流 + `director.branch_hint`）——
          两处各写一套的话，"自己写的走向"就会变成只记日志、对故事毫无影响，
          那正是本项目最不想看到的"假功能"。

        ⚠ 空白输入**当作没写**（不清空上一次：清了就等于"你写了但不算数"）。
        
                English:
        The user **wrote a direction themselves** at the fork (not chosen from candidates) —— added
        2026-10-07.
                What the user wants is "a text box at the bottom where the user can type content to **replace** the options",
                so the sentence they write is **equivalent to** selecting a candidate, except the author is them rather than the director.
                ⚠ The persistence semantics are exactly the same as "picking a candidate" (write event stream + `director.branch_hint`) ——
                  if each place wrote its own separate set, "a self-written direction" would become log-only with no effect on the story,
                  which is exactly the "fake feature" this project least wants to see.
                ⚠ Blank input is **treated as nothing written** (does not clear the previous one: clearing would amount to "you wrote it but it doesn't count").
        """
        t = " ".join(str(text or "").split())
        if not t:
            return
        # 长度上限：这句话会进挑事提示词与事件流，太长会挤掉别的上下文。
        # [EN] Length cap: this line goes into the instigation prompt and the event stream; if too long it will
        # [EN] crowd out other context.
        self._branch_custom = t[:200]
        self._branch_choice = None

    def _on_credit_block(self, exc) -> None:
        """路由器刚发现**某家模型服务没钱了** → 立刻暂停，并把话说清楚。

        为什么挂成回调而不是"等异常飘上去"：
          这条路上有 `llm.replies.ask`（把它降级成"没拿到"）、`Agent.decide`
          （降级成"这一拍什么都没做"）、以及剧组那十几个 `except Exception`。
          异常一路被吞，屏幕上是**哑掉**的 —— 而用户要的是"明确的报信息"。
          登记表 + 回调绕开了整条异常链：谁说无所谓，**账在，就停**。

        ⚠ 幂等：同一家没钱会被登记表只回调一次，但保险起见再判一次 `_credit_paused`。
        ⚠ 绝不让它抛：它是从 LLM 调用栈里被同步调起的，抛了会盖掉欠费这件事本身。
        [EN] The router just found **a provider out of money** -> pause immediately and say it
        [EN] clearly. Why a callback instead of letting the exception bubble: `llm.replies.ask`
        [EN] degrades it to "got nothing", `Agent.decide` to "this beat did nothing", and the crew's
        [EN] dozen `except Exception` swallow it -- the screen goes silent, while the user asked for
        [EN] **a clear message**. The registry + callback bypasses the whole chain: whoever swallows
        [EN] it does not matter; if the ledger says so, we stop.
        [EN] ⚠ Idempotent. ⚠ Must never raise: it is invoked synchronously from inside the LLM call
        [EN] stack, and raising would mask the out-of-credit fact itself.
        """
        try:
            if getattr(self, '_credit_paused', False):
                return
            # ⚠ 已经点了停止就别暂停了（见 `stop()` 里那段说明）。
            # [EN] ⚠ Once a stop has been requested, do not pause (see the note in `stop()`).
            if self.stopping:
                return
            self._credit_paused = True
            try:
                self._push_narrative(exc.describe(), 1, kind=S.NOTE)
            except Exception as e:                               # noqa: BLE001
                _LOG.warning('欠费提示没推上屏（不影响暂停）：%r', e)
            # `pause(reason)` 里的 reason 会走 `_on_self_pause` → 会话层把按钮换成「继续」。
            # ⚠ 用 `headline()` 这种**一行**的，别把整段 describe 塞进状态条。
            # [EN] `pause(reason)` goes through `_on_self_pause` -> the session swaps the button to
            # [EN] "Resume". ⚠ Use the one-line `headline()`; do not cram the whole `describe()` into
            # [EN] the status bar.
            self.pause(exc.headline())
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('欠费暂停失败（欠费仍已登记）：%r', e)

    def pause(self, reason: str = "") -> None:
        """暂停。

        `reason` 非空 ⇒ **这是主循环自己开的暂停**（日界检查点 / 存档点 /
        岔路口 / 导演介入），会通过 `_on_self_pause` 通知会话层。
        `reason` 为空 ⇒ 用户在界面上点「暂停」，会话层**自己**已经知道
        （`RunSession.pause()` 就在调用链上），不需要、也不该再报一次
        —— 报两次会让"谁停的"这件事糊掉。

        ★ **中间临时暂停**（用户 2026-10-07 点名要显示的一条）。
          只报状态、不报原因 —— 原因照旧由各条挂起消息自己说
          （导演待确认 / 岔路口 / 定期存档），这里给的是**时间线**上的一个点。
        
                English:
        Pause.
                Non-empty `reason` ⇒ **this is a pause initiated by the main loop itself** (day-boundary checkpoint / save point /
                fork / director intervention), which notifies the session layer via `_on_self_pause`.
                Empty `reason` ⇒ the user clicked "Pause" in the UI, and the session layer **already** knows
                (`RunSession.pause()` is right there on the call chain), so it does not need to and should not report again
                —— reporting twice muddies "who paused it".
                ★ **Intermediate temporary pause** (an item the user specifically asked to display on 2026-10-07).
                  Reports only the state, not the reason —— the reason is still stated by each pending message itself
                  (director pending confirmation / fork / periodic save); what is given here is a **point** on the **timeline**.
        """
        self._paused = True
        self._stage_start('pause')
        if reason:
            cb = getattr(self, '_on_self_pause', None)
            if cb is not None:
                try:
                    cb(str(reason))
                except Exception as e:                           # noqa: BLE001
                    self._warn_once('self_pause',
                                    f'暂停状态没报给界面（不影响推演）：{e!r}')

    def resume(self) -> None:
        self._paused = False
        self._stage_start('resume')
        # ★★★ **"继续"= 我已经处理过了**（2026-10-25）：清掉欠费登记，让下一次请求**真的发出去**。
        #   不清的话，路由器那条 fail-fast 会在第一发就把人挡回来 —— 用户充了钱
        #   点继续，屏幕上还是"余额不足"，而实际上钱已经到账了。
        #   ⚠ 反过来也要成立：**没充就点继续** ⇒ 第一发照常发出去、照常被拒 ⇒
        #     再登记一次、再停一次、再把同一句话报一遍。这正是用户要的语义。
        #   ⚠ 顺带清 `_credit_paused`：不这么写，第二次撞上时回调会被它挡住不再暂停。
        # [EN] ★★★ **"Resume" means "I've dealt with it"** (2026-10-25): clear the credit registry so
        # [EN] the next request is **actually sent**. Without clearing, the router's fail-fast blocks
        # [EN] the very first request -- the user tops up, clicks resume, and the screen still says
        # [EN] "out of credit" while the money has in fact arrived.
        # [EN] ⚠ The other direction must hold too: **resume without topping up** => the first request
        # [EN] goes out, gets rejected, is noted again, stops again, says the same thing again --
        # [EN] exactly the semantics the user asked for.
        # [EN] ⚠ Also reset `_credit_paused`; otherwise the second hit is swallowed by the callback's
        # [EN] idempotence guard and never pauses.
        if getattr(self, '_credit_paused', False):
            self._credit_paused = False
            CREDIT.clear()
            try:
                self._push_narrative('收到 —— 正在重试刚才那一步（如果那边还没到账，会再停一次）。',
                                     1, kind=S.NOTE)
            except Exception as e:                               # noqa: BLE001
                _LOG.debug('重试提示没推上屏：%r', e)
        # 作者点「继续」= 认可导演刚才那个介入方案（`INTERVENTION_POLICY=pause`
        # 挂起的那条）。**要在这里落实**：不落实的话下一拍又会被同一个停滞条件
        # 拦住，永远问下去。
        # [EN] The author clicks "continue" = approving the intervention plan the director just proposed
        # [EN] (`INTERVENTION_POLICY=pause`
        # [EN] the suspended one). **Must be applied here**: if not applied, the next tick will be blocked
        # [EN] again by the same stagnation condition
        # [EN] and it will keep asking forever.
        # ⚠ 2026-10-11 起，介入那条改走**提问对话框**（`_ask`）—— 它的落点
        #   是 `director.confirm_intervention()` / `skip_intervention()`。
        #   这里保留老口径只做一件事：**没有界面在问**（`_ask_pending` 为空）
        #   而又挂着待确认介入时，点「继续」仍旧算"同意"。
        #   有界面在问的时候**不抢答**（抢了就变成"继续 = 同意"，
        #   而对话框上明明写着"这次不用"那个选项 —— 那是自相矛盾）。
        # [EN] ⚠ As of 2026-10-11, the intervention line goes through the **question dialog** (`_ask`) — its
        # [EN] landing point
        # [EN] is `director.confirm_intervention()` / `skip_intervention()`.
        # [EN] Here we keep the old semantics for one purpose only: **when no UI is asking** (`_ask_pending` is
        # [EN] empty)
        # [EN] and there is still a pending intervention, clicking "continue" still counts as "agree".
        # [EN] When a UI is asking, **do not answer on its behalf** (doing so turns it into "continue = agree",
        # [EN] while the dialog clearly shows the "not this time" option — that's self-contradictory).
        if getattr(self, '_ask_pending', None) is None:
            if getattr(self.director, "_pending_intervention", None):
                self.director._intervention_confirmed = True
        # ★★ **还没答完的题，点「继续」要重新弹出来**（2026-10-11，用户点名：
        #   「如果选择取消则推演变成暂停 用户点继续的时候 继续弹出相关对话框」）。
        #   题在 `_ask` 那边还等着（取消**不会**把它丢掉），这里只是把它
        #   重新画到屏幕上 —— 不重画的话作者会看到一个"已经关掉、再也回不来"
        #   的对话框，而推演停在那儿等一个他答不了的题。
        # [EN] ★★ **If the question hasn't been fully answered, clicking "continue" should bring it back up**
        # [EN] (2026-10-11, user specifically called this out:
        # [EN] "if cancel is chosen, the simulation turns into paused; when the user clicks continue, the
        # [EN] relevant dialog should pop up again").
        # [EN] The question is still waiting on the `_ask` side (cancel does **not** discard it); here we just
        # [EN] redraw it to the screen — without redrawing, the author would see a dialog that has "already
        # [EN] been closed and can never come back",
        # [EN] while the simulation sits there waiting for a question he can't answer.
        pend = getattr(self, '_ask_pending', None)
        cb = getattr(self, '_on_ask', None)
        if pend is not None and cb is not None:
            try:
                cb(dict(pend))
            except Exception as e:                              # noqa: BLE001
                self._warn_once('ask_reopen', f"重新弹出提问失败（不影响推演）：{e!r}")

    def stop(self) -> None:
        """请求停止：主循环退出，收尾（补落最后一天 + 自动导出）由 `_finish` 做。

        **必须同时解除暂停**：暂停时循环卡在 `while self._paused` 里，
        只把 `_running` 置 False 是出不来的 —— 那会变成"点了停止却一直挂着"。

        ★★ 2026-10-07 第八轮：**点了要立刻看得见**（用户报「停止按钮点了没反应」）。

        为什么以前像"没反应"：`stop()` 只是一次**置标志**，真正的退出要等
        当前这一步做完；而退出时 `_finish` 还要跑一整套收工
        （场记 / 宣发 / 语言审校 / 复盘 + 整理当天这一章 + 自动导出）——
        真机下那是**好几次 LLM 调用**，几十秒到几分钟。这段时间里
        中栏**一条消息都没有**、状态行只有一小句"正在停止…"，
        所以看起来就是按钮坏了。

        现在两件事一起做：
          · **立刻推一条**到中栏（`_push_stop_notice`），说清"在收尾、要等什么、
            等多久量级" —— 用户马上知道点到了；
          · 下面那些长流程（`_open_day` / `_tick`）里加了 `_running` 检查，
            **尽快**跳出，不再把这一天的编剧组/排练/验算全跑完。
        
                English:
        Request stop: the main loop exits, and finalization (writing the last day + auto export) is done
        by `_finish`.
                **Must also lift the pause at the same time**: when paused, the loop is stuck in `while self._paused`,
                and merely setting `_running` to False cannot get it out —— that would become "clicked stop but it stays hung".
                ★★ 2026-10-07 round eight: **clicking must be immediately visible** (user reported "clicking the stop button does nothing").
                Why it used to look like "nothing happened": `stop()` is just a one-time **flag set**, and the actual exit must wait
                for the current step to finish; and on exit `_finish` still has to run a whole set of wrap-up work
                (continuity / publicity / language review / retrospective + organizing the day's chapter + auto export) ——
                on a real machine that is **several LLM calls**, tens of seconds to several minutes. During this time
                the middle column has **not a single message**, and the status line has only a short "stopping…",
                so it looks like the button is broken.
                Now two things are done together:
                  · **Immediately push one** to the middle column (`_push_stop_notice`), stating clearly "wrapping up, what to wait for,
                    and roughly how long" —— the user immediately knows the click registered;
                  · The long flows below (`_open_day` / `_tick`) have an added `_running` check,
                    so they **bail out as soon as possible** and no longer run the whole day's writers' room / rehearsal / verification to completion.
        """
        self._paused = False
        # ★ 停止之后**不再为欠费暂停**（2026-10-25）：收工那一段（场记/复盘/整理稿）
        #   本来就会再调模型，若这中间发现没钱，回调一暂停就会把"正在停止"
        #   顶成"已暂停" —— 用户点了停止，屏幕反而说"等你点继续"。
        # [EN] ★ **No credit pause after a stop request** (2026-10-25): the wrap-up (continuity /
        # [EN] retrospective / organizer) calls models again, and a pause here would flip "stopping"
        # [EN] into "paused" -- the user pressed stop and the screen says "waiting for resume".
        if getattr(self, '_credit_cb', None) is not None:
            CREDIT.off_block(self._credit_cb)
        # 只报一次：连点几下不该刷出一排「正在停止」
        # [EN] Report only once: rapid repeated clicks should not spew out a row of "stopping".
        if not self.stopping:
            self._push_stop_notice()
        self._stop_requested = True
        self._running = False

    @property
    def stopping(self) -> bool:
        """**有人请求过停止**吗（`_tick` / `_open_day` 靠它提前收手）。

        ⚠ 用 `getattr` 取：`RunLoop` 有几条**不走 `__init__`** 的构造路径
          （`RunLoop.__new__` + 手工填几个属性 —— 老夹具在用），
          写死 `self._stop_requested` 会让那些路径直接 `AttributeError`。
          与 `_stage()` 里那句 `getattr(self, 'studio', None)` 同一条理由：
          这是**附加**的提前退出，不该成为硬依赖。
        
                English:
        Has **anyone requested stop** (`_tick` / `_open_day` rely on this to wrap up early).
                ⚠ Use `getattr` to fetch it: `RunLoop` has several construction paths that **do not go through `__init__`**
                  (`RunLoop.__new__` + manually filling a few attributes —— old fixtures use this),
                  and hardcoding `self._stop_requested` would make those paths hit `AttributeError` directly.
                  Same reasoning as the `getattr(self, 'studio', None)` line in `_stage()`:
                  this is an **additional** early exit and should not become a hard dependency.
        """
        return bool(getattr(self, '_stop_requested', False))

    def _push_stop_notice(self) -> None:
        """停下来的**即时反馈**（中栏那条）。独立成方法是为了让判据能直接调它。

        ⚠ **用 `NOTE` 而不是 `SUMMARY`**：`SUMMARY` 这个 kind 的含义是
          「收工**结论**（给人读的那一份）」——复盘给的东西。一条"正在停止"
          不是结论，借用那个 kind 会让"今天出了几份总结"这种数量对不上
          （而且屏幕上会多出一张长得像总结的卡）。它就是一条**状态**，
          归 `NOTE`（与"（进度）节点完成"同一路）。
          时间线上那一条另有 `▸ 收尾（落盘 + 总结）`（`_stage_start`）。
        
                English:
        The **instant feedback** for stopping (that middle-column entry). Made a separate method so the
        criterion can call it directly.
                ⚠ **Use `NOTE` rather than `SUMMARY`**: the meaning of the `SUMMARY` kind is
                  "the wrap-up **conclusion** (the copy for humans to read)" —— what the retrospective gives. A "stopping"
                  is not a conclusion, and borrowing that kind would make counts like "how many summaries were produced today" not add up
                  (and an extra card that looks like a summary would appear on screen). It is just a **status**,
                  Attributed to `NOTE` (same path as "(progress) node complete").
                  The one on the timeline is separate: `▸ wrap-up (persist + summarize)` (`_stage_start`).
        """
        try:
            self._stage_start('stopping')
        except Exception:                                        # noqa: BLE001
            pass
        try:
            self._push_narrative(
                '正在停止 —— 先补落这一天，再写「今日总结」，然后按设置自动导出。'
                '这几步会各调一次模型，可能要等一会儿；下面会接着出总结那一段。',
                1, kind=S.NOTE)
        except Exception:                                        # noqa: BLE001
            pass

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def running(self) -> bool:
        return self._running

    # ── 主循环 ──────────────────────────────────────────────────────
    # [EN] ── main loop ─────────────────────────────────────────────────────
    async def run(self, max_ticks: int = 0) -> str:
        """运行模拟。返回结束原因。max_ticks=0 表示不限（由 boundary 控制）。
                English:
        Run the simulation. Returns the end reason. max_ticks=0 means unlimited (controlled by
        boundary).
        """
        self._running = True
        self._paused = False
        # ★★★ 每一轮开跑前**清空欠费登记**（2026-10-25）。
        #   登记表是模块级的（一个进程只有一个），不清的话：
        #     · 上一轮欠过费、这一轮已经充值了，第一次请求就会被 fail-fast 挡住 ——
        #       用户看到的正是"充了钱还是不动"；
        #     · 而且那条提示会一直挂在状态条上。
        #   清的前提是"用户重新点了开始/继续"，那本来就是一次"我处理过了"的表态。
        # [EN] ★★★ **Clear the credit registry before each round** (2026-10-25). The registry is
        # [EN] module-level (one per process); without clearing: the previous round ran out, this
        # [EN] round is topped up, yet the very first request is blocked by fail-fast -- the user sees
        # [EN] "I paid and it still won't move", and the hint stays on the status bar forever.
        # [EN] Clearing assumes the user just pressed start/resume, which is itself "I dealt with it".
        CREDIT.clear()
        self._credit_paused = False
        # ★ 把"没钱了"这条通道接上：路由器一登记就**立刻**暂停（不用等这一拍跑完）。
        #   ⚠ 存成同一个对象再注册，`finally` 里才撤得掉。
        # [EN] ★ Wire the "out of money" channel: the router noting it pauses **immediately**
        # [EN] (no need to wait for the beat to finish). ⚠ Store one object, so `finally` can
        # [EN] remove it.
        if self._credit_cb is None:
            self._credit_cb = self._on_credit_block
        CREDIT.on_block(self._credit_cb)
        # ★ 开跑时把"日界检查点"的标记对到**当前这一天**（2026-10-10）。
        #   为什么：`STORY_DAY_EVERY_DAYS` 的本意是「每隔 N 虚拟日暂停」——
        #   停的是**日界**。而续跑通常从某一天的**当中**开始，第一拍就停等于
        #   "一按开始就卡住"，用户看到的正是那句「正在核对故事进度 · 已 2019 秒」。
        #   设成当前日后：这一天照跑，跨到下一天时才停。
        #   （`_last_story_day_pause` 的初值是 None，所以不走 `run()` 的探针
        #     行为不变 —— 见 `__init__` 里那段说明。）
        # [EN] ★ At startup, align the "day boundary checkpoint" marker to **the current day** (2026-10-10).
        # [EN] Why: the intent of `STORY_DAY_EVERY_DAYS` is "pause every N virtual days" —
        # [EN] what pauses is the **day boundary**. And a resume usually starts from **the middle** of some
        # [EN] day; pausing on the first tick means
        # [EN] "stuck the moment you press start", and what the user sees is exactly that line "verifying story
        # [EN] progress · 2019 seconds elapsed".
        # [EN] After setting it to the current day: this day runs normally, and it only pauses when crossing
        # [EN] into the next day.
        # [EN] (`_last_story_day_pause`'s initial value is None, so the probe in `run()` is not used
        # [EN] and behavior is unchanged — see the explanation in `__init__`.)
        self._last_story_day_pause = self.world.game_day
        # ★ 清掉上一轮留下的"停止请求"（同一个 loop 对象被复用跑第二轮时——
        #   不清的话新一轮会在第一拍就自己退出，而且**没有任何报错**）。
        # [EN] ★ Clear the "stop request" left over from the previous round (when the same loop object is
        # [EN] reused to run a second round —
        # [EN] if not cleared, the new round will exit by itself on the first tick, and with **no error at
        # [EN] all**).
        self._stop_requested = False
        tick = 0
        # 记下账本水位：结束时只统计**本次运行**消耗的 token，
        # 否则会把上一次运行的账记到这一次头上（进程内账本是累计的）。
        # [EN] Record the ledger watermark: at the end, count only the tokens consumed by **this run**,
        # [EN] otherwise the previous run's account gets charged to this one (the in-process ledger is
        # [EN] cumulative).
        self._ledger_mark = len(llm.ledger.records)
        # ⚠ **推演路径必须自己把 LLM 客户端建起来。** 以前只有开卷摄取那条路调
        # `ensure_started`，从这里进去时 `_client` 是 None —— 每次决策都在
        # `_real_call` 的 assert 上炸掉、被 `decide` 吞掉，屏幕上满屏「没动，也没出声」。
        # [EN] ⚠ **The simulation path must build the LLM client itself.** Previously only the open-book
        # [EN] ingestion path called
        # [EN] `ensure_started`; when entering from here, `_client` is None — every decision blows up on
        # [EN] the assert in `_real_call`, gets swallowed by `decide`, and the screen is full of "nothing
        # [EN] moved, nothing was said".
        try:
            await llm.ensure_started(log_dir())
        except Exception as e:                              # noqa: BLE001
            _LOG.warning("LLM 客户端初始化失败：%r（人物将无法决策）", e)
        self._last_mono = time.monotonic()
        _LOG.info("主循环启动: %d 人物，模式 %s，时间倍率 %d×，一拍 %d 故事秒",
                  len(self.agents), CFG.s("RUN_MODE"), CFG.i("TIME_RATIO"),
                  CFG.i("BEAT_SECONDS"))

        # ★ 「每次推演开始一开始，先给一小段前情提要」（用户 2026-10-07）。
        #   续跑（从存档接上第 N 天）时 db 里已经有摘要，这里就能讲清"上一回
        #   说到哪儿"；第一次跑则取设定集的【世界观】那一段（没有就不推）。
        #   放在**主循环之前**：它必须出现在这一轮的第一条叙事之前。
        # [EN] ★ "At the very start of each simulation run, give a short recap first" (user, 2026-10-07).
        # [EN] When resuming (continuing from day N of a save), the db already has a summary, so here it can
        # [EN] clearly say "where we left off last time";
        # [EN] on the first run, take the 【Worldview】 section of the setting collection (if absent, don't push
        # [EN] it).
        # [EN] Place it **before the main loop**: it must appear before the first narrative line of this round.
        self._push_recap()
        # ★★ **作者对本轮走向的要求**（2026-10-11）—— 紧跟在开头那句前情提要后面。
        # [EN] ★★ **The author's direction for this round's course** (2026-10-11) — right after the opening
        # [EN] recap line.
        #   为什么不塞进前情提要那一句里：用户点名要求"起笔对话框里的前情提要
        #   与运行窗口里的**一样**"，而这一句是**另一件事**（前者是"演到哪儿了"，
        #   后者是"往哪走"）。分开两条，两边的前情提要才能保持逐字相同。
        # [EN] Why not stuff it into the recap line: the user specifically required "the recap in the
        # [EN] start-writing dialog
        # [EN] is **identical** to the one in the run window", and this line is **a different thing** (the
        # [EN] former is "where we are in the story",
        # [EN] the latter is "where we're heading"). Keeping them as two separate lines is what keeps the
        # [EN] recaps on both sides byte-for-byte identical.
        #   ⚠ **只在这一轮开头推一次**（不进日界那一支）：它是一整轮的方针，
        #     每个日界都念一遍就成噪音了（与 `_resume_recap` 那条一次性的同理）。
        #   ⚠ 刻意**不挂在「每轮开场」那个开关上**（`SHOW_OPENING`）：关掉开场
        #     卡片的人，照样该看得见自己填过的要求 —— 否则就是"填了但没回音"。
        # [EN] ⚠ **Push it only once at the start of this round** (not in the day-boundary branch): it's a
        # [EN] policy for the whole round,
        # [EN] and reading it aloud at every day boundary would just be noise (same reasoning as the one-shot
        # [EN] `_resume_recap`).
        # [EN] ⚠ Deliberately **not tied to the "every round opening" toggle** (`SHOW_OPENING`): people who
        # [EN] turn off the opening
        # [EN] card should still see the request they filled in — otherwise it's "filled in but no response".
        self._push_author_note()

        while self._running:
            # 暂停等待。**这里也要看 `_running`** —— 否则暂停状态下点「停止」
            # 会一直卡在这个 while 里出不去（`_running` 只在主循环条件上检查）。
            # [EN] Pause and wait. **Also check `_running` here** — otherwise clicking "stop" while paused
            # [EN] will stay stuck in this while forever (`_running` is only checked in the main loop condition).
            while self._paused and self._running:
                await asyncio.sleep(0.1)
            if not self._running:
                break
            # ★★★ **兜底：登记表里挂着欠费就停**（2026-10-25）。
            #   为什么回调之外还要这一道：回调是"顺手通知"，它自己如果抛了（或者某个
            #   替身主循环没接），异常又刚好被某处 `except Exception` 吞掉 ——
            #   那就没有任何人会停下来，而钱确实已经没了。这里按**账**再判一次，
            #   与"谁吞了异常"无关。
            # [EN] ★★★ **Safety net: stop when the registry says out of credit** (2026-10-25).
            # [EN] Why in addition to the callback: the callback is a courtesy notification; if it
            # [EN] throws (or a stand-in loop never wired it) and the exception happens to be
            # [EN] swallowed somewhere, nobody stops -- while the money really is gone. This checks
            # [EN] the **ledger** again, independent of who swallowed what.
            _ooc = CREDIT.first()
            if _ooc is not None and not self._paused:
                self._on_credit_block(_ooc)
                continue

            # ① 节拍：**只决定该不该起下一拍**（2026-10-26 起不再推故事钟）
            # ★ 故事时间现在在 `_tick` 里按"这一站剩余时长 ÷ 剩余拍数"推（`_walk_beat_time`），
            #   因为一拍推多久取决于"这一站"—— 而那一圈还没到 `_tick` 时不知道这一站是谁。
            #   ⚠ `DAY_ENDS_ON_BEAT_BUDGET=false`（老口径）才用 `_advance_clock_legacy`，
            #     那时时钟仍是"真实流逝 × TIME_RATIO"，日界仍是"跨 24 点"。
            # [EN] ① Beat: **only decides whether the next beat starts** (no longer advances the story
            # [EN] clock since 2026-10-26). Story time now advances inside `_tick` by "this station's
            # [EN] remaining duration / remaining beats" (`_walk_beat_time`), because how long a beat
            # [EN] lasts depends on the station -- unknown before `_tick` runs. ⚠ The legacy path
            # [EN] (`DAY_ENDS_ON_BEAT_BUDGET=false`) still uses `_advance_clock_legacy`, with the clock
            # [EN] on "real elapsed × TIME_RATIO" and the day boundary on midnight.
            if _day_ends_on_budget():
                self._advance_clock()
            else:
                self._advance_clock_legacy()

            # ② 跨天就落盘（哪怕这一圈还没到一拍 —— 否则一天的最后一段会悬着）
            # [EN] ② Persist on day cross (even if this lap hasn't reached a tick yet — otherwise the last stretch
            # [EN] of the day hangs)
            #
            # ★★★ 2026-10-26：日界现在有**两个来源**（用户选 A：日界 = 拍预算用完）。
            #   `_day_boundary_due()` 一处判两件事：
            #     a. **这一站的拍预算演完了**（新：小说的"一天"＝这一天写出来的那些事）；
            #     b. **故事钟跨了 24 点**（旧：兜底 —— 一拍推得很长时不能一直不换天）。
            #   ⚠ 判据集中在一个方法里，是因为它要读 4 个状态（拍数/预算/时钟/写作天），
            #     分散在 `run()` 里写就会漏掉一个（"少判一个条件"这种错不报错、只是不换天）。
            # [EN] ★★★ 2026-10-26: the day boundary now has **two sources** (the user chose A: the
            # [EN] day ends when the beat budget runs out). `_day_boundary_due()` decides both in one
            # [EN] place: (a) this station's beat budget is used up -- the new rule, where a novel's
            # [EN] "day" is the things written that day; (b) the story clock crossed midnight -- the
            # [EN] old rule, kept as a fallback so a long beat can't stall the day forever.
            if self._day_boundary_due():
                await self._end_day()          # 内部会推「一天结束」那条分隔符
                # [EN] Internally it will push the "end of day" separator
                # ⚠ 写作天必须以 `_current_day + 1` 推进，**不能用 `world.game_day`**：
                #   现在故事日可能一次跳 90 天（"数月+带过"），而写作天是"第几份稿"。
                #   两者用同一个号会让"第 3 天"的稿子里写着故事第 90 天的事，
                #   而文件名/导出标题全按写作天走 ⇒ 读者看到"第 3 天"却是三个月后。
                # [EN] ⚠ The writing day must advance as `_current_day + 1`, **never
                # [EN] `world.game_day`**: story days can now jump 90 at once ("months + in
                # [EN] passing"), while the writing day counts drafts. Sharing one number would put
                # [EN] story-day 90 into a file named "day 3", and file names and export titles
                # [EN] follow the writing day.
                self._current_day = self._advance_writing_day()
                # ★★★ 新的一天：把"故事天"的基准重新钉在此刻（见 `_story_day_at_day_start`）。
                #   ⚠ 必须在**收工之后**取 —— 站末可能刚把剩余时间一次跳掉（`_flush_station_gap`），
                #     那一下会跨好几天；钉在跳之前，新的一天一开演就"已经跨过 24 点"。
                # [EN] ★★★ New day: re-pin the **story day** baseline at this moment. ⚠ Take it
                # [EN] **after** the wrap-up: the station gap flush may have jumped days forward, and
                # [EN] pinning before that would make the new day look "already past midnight".
                self._story_day_at_day_start = int(self.world.game_day or 0)
                self._count_node_day()
                # ★ 2026-10-22：场次计数**按天重置**。不重置的话第 2 天第一场会被记成
                #   「第 5 场」，清单里按天取就只剩后半截（导出时会漏掉前面几场）。
                # [EN] ★ 2026-10-22: the scene counter **resets each day**. Without it the first scene
                # [EN] of day 2 is recorded as "scene 5" and per-day lookups in the manifest only see
                # [EN] the tail (the export would silently drop the first scenes).
                self._scene_no = 0
                # 新的一天：推一条 DAY_START，带上天数与**小说里的时辰**
                # ★ 2026-10-31：天数用**写作天**（`_current_day`），不再用 `world.game_day`。
                #   同一条分隔符上"天数"与"收工"那条（`day_end(_current_day)`）、落盘文件名、
                #   左上角时间面板必须同源，否则用户会看到"这天开头是第 4 天、结尾是第 3 天"
                #   （他就是这么报的）。故事时钟继续只提供**时辰**。
                # [EN] New day: push a DAY_START carrying the day number and the **in-story hour**.
                # ★ 2026-10-31: the day number is the **writing day** (`_current_day`), no longer
                #   `world.game_day`. This separator's day, the `day_end(_current_day)` separator,
                #   the persisted file name and the top-left clock panel must share one source.
                self._push_divider(D.day_start(self._current_day,
                                               self.world.clock_display()))
                # ★ 新的一天先回顾一下「到这儿为止发生了什么」（用户 2026-10-07：
                #   「每次推演开始一开始应该有一小段前情提要」）。顺序是
                #   前情提要 → 场景介绍 → 人物开口 —— 正是用户要的那个顺序。
                #   ⚠ 必须排在**上一句 `_end_day()` 之后**：那边的
                #     `_summarize_day()` 刚把昨天压成摘要，这里才读得到。
                # [EN] ★ On a new day, first recap "what happened up to here" (user 2026-10-07:
                # [EN] "each simulation start should begin with a short recap"). The order is
                # [EN] recap → scene introduction → characters speak —— exactly the order the user wants.
                # [EN] ⚠ Must come **after the previous `_end_day()`**: there,
                # [EN] `_summarize_day()` just compressed yesterday into a summary, which is only readable now.
                self._push_recap()
                # ★ 新的一天还要做两件事（2026-10-06）：
                #   ① 张力按曲线回落 —— 不回落的话，事件注入那条路
                #      会在张力越过 0.4 之后**永久关闭**（详见 `director/engine.py`
                #      的 `_TENSION_CURVE`）；
                #   ② 给前台人物排今日计划 —— 让行动有内在动力，
                #      而不是全靠导演随机戳（`Agent.make_plan` 以前没人调用）。
                # [EN] ★ A new day also needs to do two things (2026-10-06):
                # [EN] ① Tension falls back along the curve —— if it doesn't fall back, the event injection path
                # [EN] will be **permanently closed** once tension crosses 0.4 (see `director/engine.py`
                # [EN] `_TENSION_CURVE`);
                # [EN] ② Schedule today's plan for the foreground characters —— give actions inner motivation,
                # [EN] instead of relying entirely on the director poking randomly (`Agent.make_plan` had no callers
                # [EN] before).
                try:
                    self.director.on_day_start()
                except Exception as e:                      # noqa: BLE001
                    _LOG.warning("张力回落失败（不影响推演）：%r", e)
                # ★ 顺序**不能反**：先导演定框架（写故事 → 剧本 → 分派），
                #   再让各人排计划 —— 各人的计划要**在框架之内**。
                #   反过来（各自先排完）就等于"十二个人各排各的"，
                #   合起来不构成一个故事（用户 2026-10-07 报的就是这个）。
                # [EN] ★ The order **must not be reversed**: first the director sets the framework (write story →
                # [EN] script → assign),
                # [EN] then each person makes a plan —— each person's plan must be **within the framework**.
                # [EN] The reverse (each makes their own plan first) amounts to "twelve people each making their own
                # [EN] plan",
                # [EN] which together does not constitute a story (this is exactly what the user reported on
                # [EN] 2026-10-07).
                # ★ 剧组：**开拍前先出美术与道具**（`_crew_prep`）——
                #   再往前一步都不能挪（道具单要按"还没写出来的戏"来定，
                #   见 `crew/studio.py` 的班次说明），再往后就成了事后记录。
                # [EN] ★ Crew: **art and props come out before shooting starts** (`_crew_prep`) ——
                # [EN] not one step earlier can it move (the prop list must be determined by "the scene not yet
                # [EN] written",
                # [EN] see the shift description in `crew/studio.py`), and any later it becomes an after-the-fact
                # [EN] record.
                await self._open_day()
                # ★ 开拍即把常驻岗（导演/演员/群众演员）标「在岗」——
                #   它们整场不经 `Studio.call`，不标的话界面那三行永远是「待命」
                #   （用户 2026-10-15 报的"都登场了状态还显示没开工"）。收工仍由
                #   `report_onduty` 把它们走到 `done`，所以 `onduty` 只在"开拍→收工"区间。
                if getattr(self, 'studio', None) is not None:
                    self.studio.mark_onduty()
                self._day_opened_for = self._current_day
            elif self._day_opened_for != self.world.game_day:
                # ★★ **第一天的开场**（2026-10-07 第八轮修的一个真 bug）。
                # [EN] ★★ **The opening of the first day** (a real bug fixed in the eighth round on 2026-10-07).
                # 上面那个 `if` 判的是"**跨天**"（`game_day != _current_day`），
                # 而两者的初值**都是 1** —— 于是**每一轮的第一天从来不执行
                # `_open_day()`**。后果不是小事：第一天**没有编剧室、没有样章、
                # 没有剧本、没有分拍、没有派活、没有今日剧情简介、没有场景介绍、
                # 没有当天地图、没有声音设计** —— 而且`ps.day_plan` 是空的，
                # 人物的〔今日剧本〕与〔今日计划〕两层都不存在。
                # [EN] The `if` above tests "**across days**" (`game_day != _current_day`),
                # [EN] and the initial values of both **are 1** —— thus **the first day of every round never executes
                # [EN] `_open_day()`**. The consequences are not trivial: the first day **has no writers' room, no
                # [EN] sample chapter,
                # [EN] no script, no shot breakdown, no task assignments, no today's plot synopsis, no scene
                # [EN] introduction,
                # [EN] no map of the day, no sound design** —— and `ps.day_plan` is empty,
                # [EN] the characters' [today's script] and [today's plan] layers both do not exist.
                # 表现就是用户报的：「每次推演开始时候的今日剧情介绍卡片、
                # 场景介绍卡片都没了」。实测（`developers/probe_run_cards.py`，
                # 连跑两天）：`brief` **0 次**、`ambient`（场景介绍）只在第 2 天
                # 出过 1 次 —— 第一天整块开场是空的。
                # [EN] The symptom is exactly what the user reported: "the today's plot introduction card at the start
                # [EN] of each simulation,
                # [EN] the scene introduction card are both gone". Measured (`developers/probe_run_cards.py`,
                # [EN] running two days consecutively): `brief` **0 times**, `ambient` (scene introduction) only on day
                # [EN] 2
                # [EN] appeared 1 time —— the entire opening block of the first day was empty.
                # ⚠ 为什么用 `_day_opened_for` 而不是把 `_current_day` 初值改成 0：
                #   改初值会连带影响 `_end_day()` / 落盘文件名 / 场记那些
                #   "第 N 天"的计算（它们都读 `_current_day`），
                #   而这里要的只是"这一天开过场没有"这一件事 ——
                #   多一个只表这一个意思的字段，比借一个别处在用的字段安全。
                # [EN] ⚠ Why use `_day_opened_for` instead of changing `_current_day`'s initial value to 0:
                # [EN] changing the initial value would also affect `_end_day()` / the save file name / the scene log's
                # [EN] "day N" calculations (they all read `_current_day`),
                # [EN] whereas what is wanted here is only the single fact "whether this day has opened" ——
                # [EN] an extra field expressing only this one meaning is safer than borrowing a field used elsewhere.
                await self._open_day()
                # ★ 第一天开场同样要把常驻岗标「在岗」（见上面的跨天分支注释）。
                if getattr(self, 'studio', None) is not None:
                    self.studio.mark_onduty()
                self._day_opened_for = self.world.game_day
            # ③ 攒够一拍才决策；没到就睡到该到的时候（别空转烧 CPU / 烧 token）
            # [EN] ③ Only decide when a beat has accumulated; if not reached, sleep until it is (don't idle-spin
            # [EN] burning CPU / burning tokens)
            beat = max(1, CFG.i("BEAT_SECONDS"))
            if self._beat_acc < beat:
                ratio = max(1, CFG.i("TIME_RATIO"))
                need = (beat - self._beat_acc) / ratio
                await asyncio.sleep(max(0.02, min(0.25, need)))
                continue
            self._beat_acc %= beat          # 落后太多时只补一拍，别追着补（时间会自己走过去）
            # [EN] when too far behind, only make up one beat, don't chase and catch up (time will pass on its own)

            tick += 1
            reason = await self._tick(tick)
            if reason:
                _LOG.info("主循环结束: %s (tick %d)", reason, tick)
                self._running = False
                await self._finish(reason)
                return reason

            if max_ticks and tick >= max_ticks:
                _LOG.info("达到最大 tick 数: %d", max_ticks)
                self._running = False
                await self._finish("达到最大 tick 数")
                return "达到最大 tick 数"

        # 外部直接置 `_running = False` 停下的路径
        # [EN] the path where an external party directly sets `_running = False` to stop
        await self._finish("手动停止")
        return "手动停止"

    async def _open_day(self) -> None:
        """**一天的开场**：开拍前准备 → 编剧组定框架 → 各人排计划 → 开演。

        ★ 2026-10-07 抽出来：`run()` 与探针/判据都要跑"开场这一段"，
          两处各写一遍的话（少调一步、顺序不同）就会变成
          "探针里好好的、真机上少一段"。**一处实现**是本项目的老规矩
          （§「位置判定只能有一处」同源）。

        ★★ 2026-10-07 第八轮：**每一步前都查一次 `_running`**。
        这一段是整轮里最贵的一串调用（编剧室 + 写样章 + 改剧本 + 验算
        + 排练 + 美术 + 声音，真机下十来次请求）。以前点了「停止」它照样
        从头跑到尾，用户等于**白等一整天的工作量**——那正是"点了没反应"
        的另一半原因。现在一旦请求停止就**就地收手**：
        这一天没有框架而已（`_day_script` 保持 None，与"模型没写出故事"
        是同一种状态，下游本来就处理得干干净净）。
        
                English:
        **The opening of a day**: pre-shoot preparation → writers' room sets the frame → each person
        lays out their plan → showtime.
                ★ Extracted 2026-10-07: both `run()` and the probes/criteria need to run "this opening segment";
                  if written twice (a step missed, different order) it becomes
                  "fine in the probe, a segment missing on the real machine". **One implementation** is this project's old rule
                  (same origin as §"position determination may only exist in one place").
                ★★ 2026-10-07 eighth round: **check `_running` once before every step**.
                This segment is the most expensive chain of calls in the whole round (writers' room + sample chapter + script revision + verification
                + rehearsal + art + sound, a dozen-odd requests on the real machine). Previously, clicking "stop" still had it run
                from start to finish — the user effectively **waited in vain for a whole day's work** — that is exactly the other half of the
                "clicked and nothing happened" reason. Now, once a stop is requested it **stops on the spot**:
                this day just has no frame (`_day_script` stays None, the same state as "the model didn't write a story",
                which the downstream already handles cleanly).
        """
        with self._stage('prep'):
            await self._crew_prep()
        if self.stopping:
            return
        await self._compose_day()
        if self.stopping:
            return
        await self._plan_day()
        # ★ **开演**：框架、剧本、排练、派活都就位了，接下来才是人物登场。
        #   用户 2026-10-07 点名要这一条（「开演」）。
        # [EN] ★ **Curtain up**: framework, script, rehearsal, assignments are all in place, only then do
        # [EN] characters take the stage.
        # [EN] The user specifically asked for this one on 2026-10-07 ("curtain up").
        self._stage_start('shooting')

    # ── 时间推进 ────────────────────────────────────────────────────
    # ── 「没事就把时间跳过去」（2026-10-11，用户点名）──────────────────
    # [EN] ── Time advance ────────────────────────────────────────────────────
    # [EN] ── "if nothing's happening just skip time forward" (2026-10-11,
    # [EN] user-specified)──────────────────
    def _track_idle(self, idle: bool) -> None:
        """这一拍"有没有新东西"记一笔（连着多少拍没事，`_maybe_skip_idle` 要用）。

        调用点就是原来那三处 `_maybe_quiet()`（都没事才调它）—— 分两个方法
        是为了让"计数"和"限流写一句"各管各的（后者有 `QUIET_MINUTES` 门槛，
        前者不该受它影响：`QUIET_MINUTES=0` 是"不写那句"，不是"不数了"）。
        
                English:
        Note down whether this beat "has anything new" (how many beats in a row with nothing, used by
        `_maybe_skip_idle`).
                The call sites are the original three `_maybe_quiet()` (only called when nothing is happening) — split into two methods
                so that "counting" and "rate-limited writing of one line" are managed separately (the latter has the `QUIET_MINUTES` threshold,
                the former should not be affected by it: `QUIET_MINUTES=0` is "don't write that line", not "stop counting").
        """
        self._idle_beats = (self._idle_beats + 1) if idle else 0

    def _maybe_skip_idle(self) -> bool:
        """连着几拍谁都没做事 → **把时间跳过去**（返回 True = 这一拍已跳过）。

        ★★ 用户 2026-10-11：「没事的时候时间要不要跳过（即用旁白描述一下就
        过去这段时间）」。默认**开**（同一天用户拍板）。

        为什么要它：一拍 = 1~2 次 LLM 调用。人物连着发呆的时候，那些调用买到的
        是"他还在发呆"——钱花了、屏幕上什么都没多。跳过是**把它们一次省掉**，
        再补一句旁白，作者看到的是"这段时间过去了"，而不是"程序卡住了"。

        三条设计：
          · **只在真没事的时候跳** —— 判据是连着 N 拍空拍（`is_noop` 那种），
            只要有人说话/做事就重新数。所以该演的戏一秒都不会被跳掉。
          · **跳完要重新计时**（`director.note_time_skipped()`）：不重置的话，
            时钟一口气前进几十分钟，`_is_stalling()` 反而更容易成立 ⇒
            导演在"没事"的时候跳出来介入，正好跟"别打扰我"相反。
          · **跨天交给主循环**（这里只改时钟与 `game_day`，`run()` 的跨天分支
            照旧落盘 + 开场）—— 在这儿顺手 `_end_day()` 会把"日界"这件事
            写第二遍，两处迟早不一致。

        `SKIP_IDLE_TIME=false` 时一次都不跳（计数照记，用户中途打开就立刻能生效）。
        
                English:
        Several beats in a row with nobody doing anything → **skip the time forward** (returns True =
        this beat has been skipped).
                ★★ User 2026-10-11: "when nothing is happening, should time be skipped (i.e. describe it with narration then have this stretch pass)".
                Default **on** (decided by the user the same day).
                Why it's needed: one beat = 1~2 LLM calls. When characters sit idle for several beats in a row, those calls buy you
                "he's still idling" — money spent, nothing more on screen. Skipping is **saving them all in one go**,
                plus one line of narration; what the author sees is "this stretch of time has passed" rather than "the program is stuck".
                Three design points:
                  · **Only skip when truly nothing is happening** — the criterion is N beats in a row empty (the `is_noop` kind),
                    and as soon as someone speaks/acts the count restarts. So not a second of scene that should be played gets skipped.
                  · **Restart the timing after a skip** (`director.note_time_skipped()`): without a reset,
                    the clock advances several tens of minutes in one go, and `_is_stalling()` becomes more likely to hold ⇒
                    the director stepping in when "nothing is happening" is exactly the opposite of "don't disturb me".
                  · **Cross-day is left to the main loop** (here only the clock and `game_day` are changed; `run()`'s cross-day branch
                    persists + opens as before) — calling `_end_day()` here in passing would write the "day boundary" thing
                    a second time, and the two would inevitably diverge.
                When `SKIP_IDLE_TIME=false`, it never skips (counting still happens, so if the user turns it on mid-run it takes effect immediately).
        """
        if not CFG.b("SKIP_IDLE_TIME"):
            return False
        try:
            need = max(1, CFG.i("SKIP_IDLE_BEATS"))
            jump = max(5, CFG.i("SKIP_IDLE_MINUTES"))
        except Exception:                                        # noqa: BLE001
            return False
        if self._idle_beats < need:
            return False

        where = str(getattr(self.world, 'scene', '') or '')
        line = STR.time_skip_line(
            jump, where=where, segment=self._clock_segment(),
            weather=str(getattr(self.world, 'weather', '') or ''),
            seed=self._ticks_today)
        # ★ 2026-10-26：走 `_world_walk`（唯一实现）并把跳掉的分钟**计进 `_walked_min`**。
        #   不计的话"跳过的时间不算数"⇒ 这一站的故事时长会超出跨度档
        #   （跳 3 次 30 分钟就多出一个半小时，而 `_beat_minutes_now` 还以为余量没动）。
        # [EN] 2026-10-26: go through `_world_walk` (single implementation) and **count the skipped
        # [EN] minutes into `_walked_min`**. Otherwise skipped time is free and the station overshoots
        # [EN] its span tier while `_beat_minutes_now` still thinks the remainder is untouched.
        self._world_walk(float(jump))
        self._walked_min = int(self._walked_min or 0) + int(jump)
        self._idle_beats = 0
        self._skips_today += 1
        self.skips_total += 1
        try:
            self.director.note_time_skipped()
        except Exception:                                        # noqa: BLE001
            pass
        self._push_narrative(line, 0, kind=S.AMBIENT)
        _LOG.info("时间跳过：连着 %d 拍没人做事 → 推进 %d 故事分钟（现在是 第%d天 %s）",
                  need, jump, self.world.clock.day, self.world.clock_display())
        return True

    def _advance_clock(self) -> None:
        """**只安排"该不该起下一拍"**（不再推进故事钟）。

        ★★★ 2026-10-26 语义拆开（用户选 A：日界 = 拍预算用完）：

        以前这个方法是**两件事**：①攒真实时间决定起不起下一拍；②按
        `真实流逝 × TIME_RATIO` 推进故事钟。第二件事就是"时钟匀速"的根 ——
        一拍恒定吃 `BEAT_SECONDS` 故事秒，于是"一场审讯"和"三个月赶路"
        占用一样长的故事时间。

        现在：
          · **这里只做 ①**：`_beat_acc` 攒够 `BEAT_SECONDS` 就起一拍，
            `TIME_RATIO` 只影响"等多久真实秒"⇒ 它从此**只控观看速度**；
          · 故事钟由 `_walk_beat_time()` 在**每拍里**推，推多少由
            "这一站的故事跨度 ÷ 这一站的拍数"决定（`director.day_plan.beat_minutes_for`）。

        ⚠ 老行为保留在 `_advance_clock_legacy()`（`DAY_ENDS_ON_BEAT_BUDGET=false` 时用它），
          判据 `verify_beat_time` 钉着"两条都还在"。

                English:
        **Only schedules whether the next beat starts** (no longer advances the story clock).
                ★★★ 2026-10-26, semantics split (the user chose A: the day ends when the beat budget
                runs out). This method used to do two things: (1) accumulate real time to decide the beat,
                (2) advance the story clock by `real elapsed × TIME_RATIO`. The second one was the root of
                "uniform time": a beat ate a constant `BEAT_SECONDS`, so "one interrogation" and "three
                months on the road" occupied the same story time. Now (1) stays here -- `TIME_RATIO` only
                decides how many real seconds to wait, so it **only controls watching speed** -- and the
                story clock is advanced by `_walk_beat_time()` inside each beat, by "the station's span
                divided by its beat count". ⚠ The old behaviour is kept in `_advance_clock_legacy()`,
                used when `DAY_ENDS_ON_BEAT_BUDGET=false`; `verify_beat_time` pins that both exist.
        """
        now = time.monotonic()
        dt = max(0.0, now - (self._last_mono if self._last_mono else now))
        self._last_mono = now
        # ⚠ `_beat_acc` 仍按 `真实秒 × TIME_RATIO` 攒 —— 这是"演出速度"，
        #   与故事时间再无关系（TIME_RATIO 唯一剩下的用途）。
        # [EN] `_beat_acc` still accumulates `real seconds × TIME_RATIO` -- that is "show speed",
        # [EN] now unrelated to story time (TIME_RATIO's only remaining job).
        self._beat_acc += dt * max(1, CFG.i("TIME_RATIO"))

    def _advance_clock_legacy(self) -> None:
        """**旧行为逐字保留**：真实流逝 × TIME_RATIO 直接推故事钟。

        `DAY_ENDS_ON_BEAT_BUDGET=false` 时用它 —— 那样日界回到"跨 24 点"，
        一拍回到"恒定 `BEAT_SECONDS` 故事秒"。
        [EN] **The old behaviour, kept byte for byte**: real elapsed × TIME_RATIO advances the story
        [EN] clock directly. Used when `DAY_ENDS_ON_BEAT_BUDGET=false`, which puts the day boundary
        [EN] back on "crossing midnight" and the beat back on a constant `BEAT_SECONDS`.
        """
        now = time.monotonic()
        dt = max(0.0, now - (self._last_mono if self._last_mono else now))
        self._last_mono = now
        game_dt = dt * max(1, CFG.i("TIME_RATIO"))
        self._beat_acc += game_dt
        self._world_walk(game_dt / 60.0)

    def _world_walk(self, minutes: float) -> None:
        """**把故事钟往前推** `minutes` 分钟（唯一实现：`world.tick` + `game_day` + 后台）。

        ★ 两个调用方合用这一处：`_walk_beat_time`（新路径，一拍推一次）与
          `_advance_clock_legacy`（旧路径）。两处各写一遍必然漂 —— 而漂的后果是
          "后台节拍与时钟不同源"，那种错查不出来（数字都合理）。
        ⚠ 单位是**分钟**（可以是小数，如一拍 2.4 分钟）。`world.tick` 只吃整分钟，
          零头由 `_min_acc` 攒着 —— 用分钟做累加器而不是秒，是因为 `beat_minutes`
          本来就是分钟，两套单位混用是这类错的老来源。
        [EN] **Advance the story clock** by `minutes` (single implementation: `world.tick` +
        [EN] `game_day` + backstage). Both callers share it: `_walk_beat_time` (new path) and
        [EN] `_advance_clock_legacy` (old path). Two copies would inevitably drift, and a drifted
        [EN] backstage tempo is untraceable -- every number still looks plausible.
        [EN] ⚠ The unit is **minutes** (may be fractional). `world.tick` takes whole minutes only and
        [EN] the remainder accumulates in `_min_acc`; a minute accumulator (not seconds) because
        [EN] `beat_minutes` is in minutes, and mixing the two units is the classic source of this bug.
        """
        self._min_acc += float(minutes)
        whole = int(self._min_acc)
        if whole <= 0:
            return
        self._min_acc -= whole
        self._game_sec += whole * 60
        self._game_min += whole
        self.world.tick(whole)
        self.world.game_day = self.world.clock.day
        # 后台按**一天**限幅：一次跳 90 天时不该给后台塞 129600 分钟
        # （它的节拍是 `BACKGROUND_TICK_MINUTES`，塞一次就是把节拍打爆）。
        # 限幅的含义也说得通：那三个月后台确实没什么新鲜事。
        # [EN] Clamp the backstage to **one day**: a 90-day jump must not hand it 129,600 minutes
        # [EN] (its tempo is `BACKGROUND_TICK_MINUTES`; one such delivery blows it up). The clamp
        # [EN] also says something true: nothing new happened backstage in those three months.
        try:
            self._backstage.advance(min(whole, 24 * 60))
        except Exception:                                        # noqa: BLE001
            pass

    def _beat_minutes_now(self) -> int:
        """**这一拍推多少故事分钟**（按剩余时间 / 剩余拍数**动态**算）。

        ★ 为什么动态：跨度 120 分钟的"一场"，60 拍本该一拍 2 分钟；但若中途
          `_maybe_skip_idle` 跳掉了 30 分钟，剩下 54 拍就只有 90 分钟可分 ⇒
          一拍 1.67 分钟。**静态值算不出来这件事** —— 静态会在站末超支或欠支。
        ⚠ 剩余拍数为 0 时按 1 拍算（最后一拍把余量吃完）。
        ⚠ 返回 0 表示"这一站的故事时间已经走完了"（跨度用尽）—— 调用方据此**不再推钟**，
          但拍照演（戏还没演完，只是时间不再往前走）。
        [EN] **How many story minutes this beat advances**, computed **dynamically** from the
        [EN] remaining time over the remaining beats. Static values cannot express this: if
        [EN] `_maybe_skip_idle` already jumped 30 of a 120-minute scene, 54 remaining beats share 90
        [EN] minutes (1.67 each). ⚠ Zero remaining beats counts as 1 (the last beat takes the rest).
        [EN] ⚠ Returning 0 means the station's story time is used up: don't advance the clock, but
        [EN] keep playing -- the scene is not over, time simply stops moving.
        """
        span = 0
        try:
            from director import day_plan as _DP
            span = _DP.span_minutes_for(self.world, self.db)
        except Exception:                                        # noqa: BLE001
            span = 0
        if span <= 0:
            # 取不到跨度 ⇒ 退回"恒定一拍"（旧行为），绝不因为查不到就不走时间。
            # [EN] No span available => fall back to the constant beat (old behaviour). Never let a
            # [EN] failed lookup freeze time.
            return max(1, int(CFG.i("BEAT_SECONDS") // 60) or 1)
        left = max(0, int(span) - int(self._walked_min or 0))
        if left <= 0:
            return 0
        hi = 999
        try:
            from director import day_plan as _DP
            _lo, hi, _why = _DP._beat_budget_cached(self.world, self.db)
        except Exception:                                        # noqa: BLE001
            hi = 25
        remain = max(1, int(hi) - int(self._ticks_today or 0))
        mins = int(round(left / remain))
        # 上限：一拍最多 `BEAT_MAX_MINUTES`（"一拍"这个概念本身的边界，见那个常量）。
        # ⚠ 从配置读而不是写死：用户可能想把"一个节拍"调更长（比如舞台剧式的长镜头）。
        # [EN] Ceiling: `BEAT_MAX_MINUTES` per beat (the bound of the concept "one beat"). Read from
        # [EN] config rather than hardcoded, in case someone wants longer pulses.
        try:
            cap = max(1, CFG.i("BEAT_MAX_MINUTES"))
        except Exception:                                        # noqa: BLE001
            cap = 30
        return max(1, min(cap, mins))

    def _walk_beat_time(self) -> None:
        """**这一拍该往前走多少故事时间**（新路径的唯一入口）。

        顺序：先算这一拍推多久 → 推钟 → 记账（`_walked_min`）。
        ⚠ 走完 `_walked_min` 就记账，**不看拍是否成功** —— 时间是流逝的，
          一盘戏没演好也不该让时钟倒回去。
        [EN] **How much story time this beat advances** (the new path's only entry): compute the
        [EN] duration, advance the clock, record it. ⚠ Record even if the beat fails -- time passes,
        [EN] and a badly played beat must not rewind the clock.
        """
        mins = self._beat_minutes_now()
        if mins <= 0:
            return
        self._world_walk(float(mins))
        self._walked_min = int(self._walked_min or 0) + int(mins)
        # 会计入 `_game_min`（`_world_walk` 里做了）—— 那些"每隔 N 故事分钟"的节拍靠它。
        # [EN] `_game_min` is updated inside `_world_walk`; the "every N story minutes" tempos read it.

    def _advance_clock_legacy_unused_marker(self) -> None:
        """占位（保留方法名以免外部按名字反射的地方崩）。不做任何事。"""

    def _day_boundary_due(self) -> bool:
        """**这一天该收工了吗**（日界的唯一判定）。

        ★★★ 2026-10-26（用户选 A：日界 = 拍预算用完）：

        改之前只有一条：`world.game_day != self._current_day`（故事钟跨 24 点）。
        那一条的后果是 **一天必须填满 24 小时** ⇒ 实测一天演 133 幕 / 21.3 万字，
        而同一站的内容在第二天又被"重新规划"一遍。

        现在两条**任一成立**就收工：

        | 条件 | 什么时候成立 | 为什么 |
        |---|---|---|
        | 拍预算演完 | `_ticks_today >= 这一站的拍数上限` | 小说的"一天"＝**这一天写出来的那些事**。详的站 60 拍、带过 1 拍，演完就过天 |
        | 钟跨 24 点 | `world.game_day != 写作天起点` | 兜底：一拍推 30 分钟而拍很多时，不能一天演几百小时 |

        ⚠ 第二条**不能删**：`一场 + 详` 是一拍 2 分钟、60 拍 2 小时，永远不跨 24 点，
          那样第一条会正常收工；但 `数日 + 略`（8 拍 × 540 分钟 = 3 天）会在
          第 3 拍就跨天 —— 那时第一条还没满足（3 < 8），得靠第二条收工。
        ⚠ 关掉新口径（`DAY_ENDS_ON_BEAT_BUDGET=false`）⇒ 逐字回到旧行为（只有第二条）。
        [EN] **Should this day wrap up?** (the single day-boundary decision.)
        [EN] ★★★ 2026-10-26 (the user chose A): there used to be one rule only --
        [EN] `world.game_day != self._current_day` (the clock crossed midnight) -- which forced a day
        [EN] to fill 24 hours (measured: 133 acts / 213k characters a day, with the same station
        [EN] re-planned on the next day). Now either rule fires: (a) the station's beat budget is
        [EN] used up -- a novel's "day" is what got written that day; (b) the clock crossed midnight
        [EN] -- a fallback so a long beat cannot make one day span hundreds of hours.
        [EN] ⚠ (b) cannot be removed: `数日 + 略` (8 beats x 540 min = 3 days) crosses midnight on
        [EN] beat 3, before the budget is spent (3 < 8), so it needs (b). ⚠ Turning the new rule off
        [EN] (`DAY_ENDS_ON_BEAT_BUDGET=false`) reverts to (b) only, byte for byte.
        """
        try:
            if not _day_ends_on_budget():
                return self.world.game_day != self._current_day
        except Exception:                                        # noqa: BLE001
            pass
        # ① 拍预算演完（新口径）
        # [EN] (1) the beat budget is spent (the new rule)
        try:
            from director import day_plan as _DP
            _lo, hi, _why = _DP._beat_budget_cached(self.world, self.db)
            if hi > 0 and int(self._ticks_today or 0) >= int(hi):
                _LOG.info('日界：这一站的拍预算演完了（%d/%d 拍）→ 收工',
                          int(self._ticks_today or 0), int(hi))
                return True
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('拍预算判定失败（只按跨天收工）：%r', e)
        # ② 钟跨了 24 点（兜底）
        # ★★★ 2026-10-30：比的是**这一天开演时的故事天**，不是写作天。
        #   以前写 `game_day != self._current_day` —— 写作天一到 2，这条**从第二天起就恒真**，
        #   于是第二天开始每天只演一拍（实测 267 字/天，而第一天 4,949 字）。
        # ⚠ 老构造路径（判据里 `RunLoop.__new__`，没有这个字段）当作"今天还没跨天"，
        #   不要让缺字段变成"立刻收工"。
        # [EN] (2) the clock crossed midnight (fallback). ★★★ 2026-10-30: compare against **the story
        # [EN] day at day start**, never the writing day -- the old form was true from day two onward,
        # [EN] so every day after the first ended after a single beat (267 chars vs 4,949 on day one).
        # [EN] ⚠ On the legacy test path (`RunLoop.__new__`, attribute absent) assume "not crossed yet"
        # [EN] rather than "wrap up now".
        _base = int(getattr(self, '_story_day_at_day_start', 0) or 0)
        if _base <= 0:
            _base = int(getattr(self.world, 'game_day', 0) or 0)
        return int(self.world.game_day or 0) != _base

    def _flush_station_gap(self) -> None:
        """站演完了 ⇒ **把这一站还剩的故事时间一次跳掉**（并推一句旁白）。

        ★★★ 2026-10-26（用户选 A：日界 = 拍预算用完）。

        一拍最多推 `BEAT_MAX_MINUTES`（30 分钟）—— 那是"一拍"这个概念本身的边界
        （一个人做一件事、说一两句）。而"这一站占多少故事时间"由**跨度档**决定：
        `数月 + 带过` 是"90 天、1 拍"，那 1 拍只走了 30 分钟。

        剩下的 89 天 23.5 小时不跳掉的后果是**幕头时间自相矛盾**：
        读者被告知"此后三个月无事"，可下一站的幕头还写着同一夜 ——
        "时序混乱"正是用户点名过的第一条。

        ⚠ **只在站真的演完时跳**。判据是 `self._event_carry`（`_carry_unplayed_beats`
          给的结果）：非空 = 这一站还剩拍，明天接着演 ⇒ 那时补时间会把"三个月"在
          第一天吃掉，后面几天一秒钟都走不动（幕头全一样）。
        ⚠ 上限**一年**：跨度档最大 90 天，跳过这个数说明 `_walked_min` 没记上
          （那是 bug，不该在这里悄悄兜住十年）。
        ⚠ 跳完推一句旁白（`STR.time_skip_line` 那套）—— 时间流逝必须**让人看得见**，
          否则读者只觉得"怎么突然到了别处"。
        [EN] When the station ends, **jump its remaining story time in one go** and narrate it.
        [EN] ★★★ 2026-10-26. A beat advances at most `BEAT_MAX_MINUTES` (30 minutes) -- the bound of
        [EN] the *concept* "one beat". How much story time the station occupies is the **span tier**:
        [EN] `months + in passing` is 90 days in one beat. Not jumping the remaining 89 days 23.5
        [EN] hours makes the act headers contradict themselves -- the reader is told three months
        [EN] passed while the next station still says the same night, and "scrambled chronology" is
        [EN] the first thing the user named. ⚠ Jump **only when the station is really over**: the test
        [EN] is `self._event_carry` (the result of `_carry_unplayed_beats`); non-empty means beats
        [EN] remain, and topping up then would eat the three months on day one. ⚠ Capped at one year:
        [EN] the largest tier is 90 days, so more means `_walked_min` was not recorded (a bug -- do
        [EN] not paper over ten years here). ⚠ Narrate the jump, so the passage of time is visible.
        """
        if self._event_carry:
            return
        try:
            from director import day_plan as _DP
            span = int(_DP.span_minutes_for(self.world, self.db))
        except Exception:                                        # noqa: BLE001
            return
        gap = span - int(self._walked_min or 0)
        if gap < 30:                                             # 半小时以内不算"一段时间"
            return
        gap = min(gap, 366 * 24 * 60)
        try:
            where = str(getattr(self.world, 'scene', '') or '')
        except Exception:                                        # noqa: BLE001
            where = ''
        try:
            # ⚠ 用 `time_pass_line` 而不是 `time_skip_line`：前者是"这一段到此为止"，
            #   后者是"这会儿没人做事"。两者观感一样、语义不同，而且判据靠
            #   「'就这么过去' 出现 0 次」证明"空闲跳过真的关掉了 / 有人在说话时没跳"——
            #   共用一句会让那两条误红（而红的原因与"该不该跳"毫无关系）。
            # [EN] `time_pass_line`, not `time_skip_line`: the former is "this stretch ends here",
            # [EN] the latter "nobody is doing anything right now". They read alike but mean
            # [EN] different things, and criteria prove "idle skip is off / nobody was skipped while
            # [EN] talking" by "'就这么过去' appears 0 times" -- sharing one sentence makes those two
            # [EN] misfire for reasons unrelated to whether skipping was right.
            line = STR.time_pass_line(
                gap, where=where, segment=self._clock_segment(),
                weather=str(getattr(self.world, 'weather', '') or ''),
                seed=self._writing_seed())
            self._push_narrative(line, 0, kind=S.AMBIENT)
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('站末时间跳过的旁白没写成（不影响时间推进）：%r', e)
        self._world_walk(float(gap))
        self._walked_min = int(self._walked_min or 0) + gap
        _LOG.info('站末补时间：这一站跨度 %d 分钟，站内只走了 %d 分钟 → 跳 %d 分钟'
                  '（现在 第%d天 %s）',
                  span, span - gap, gap, self.world.clock.day, self.world.clock_display())

    def _writing_seed(self) -> int:
        """给"时间跳过"那句旁白用的种子（同一天同一站要稳定 ⇒ 重跑同一场景不换说法）。

        ⚠ 用**写作天**而不是 `game_day`：故事日可能一次跳 90 天，用它做种子会让
          "同一天的同一个场景"每次都挑到不同句式（重跑/续跑时台词对不上）。
        [EN] Seed for the time-skip narration, so re-running the same day/scene picks the same
        [EN] wording. ⚠ Use the **writing day**, not `game_day`: story days can jump by 90 and using
        [EN] them would change the wording between reruns of the same scene.
        """
        return int(self._current_day or 0) * 1000 + int(self._ticks_today or 0)

    def _count_node_day(self) -> None:
        """新的一天开始 ⇒ **当前这一站已经演了几个写作天**这个数 +1。

        ★ 记的是"**已经跨过几个日界**"，不是"这是第几章" —— `+1`（今天那一份）
          由 `_days_in_node()` 加。所以换站时**归 0**：新站一天都还没过完。
          ⚠ 换站时归 1 会让新站一上来就算成"已经 2 章"（off-by-one），
             而它看起来只是"这一站走得快一点" —— 反例法第 ⑭ 刀就是这么抓到的。
        [EN] It counts "**how many day boundaries have been crossed**", not "which chapter this is"
        [EN] -- the `+1` for today is added by `_days_in_node()`. So a station change resets to
        [EN] **0**: the new station has not finished a single day yet.
        [EN] ⚠ Resetting to 1 would make a new station start at "already 2 chapters" (off-by-one),
        [EN] and it only looks like "this station moved fast" -- knife ⑭ of the mutation suite is
        [EN] exactly what caught it.
        """
        # ⚠ 一律用 `getattr` 取这两个计数：判据与探针里有不少用 `RunLoop.__new__`
        #   造对象、**绕过 `__init__`** 的夹具（`verify_branch` 就是），
        #   直接取属性会 `AttributeError` —— 而那看起来像"产品代码坏了"，
        #   其实是夹具没走构造。（与上面 `_progress_sig` 同一个坑，别再踩第二次。）
        # [EN] ⚠ Always `getattr` these two counters: many assertions and probes build objects with
        # [EN] `RunLoop.__new__`, **bypassing `__init__`** (`verify_branch` does), so a direct
        # [EN] attribute access raises `AttributeError` -- which looks like "the product code broke"
        # [EN] when in fact the fixture skipped the constructor. Same trap as `_progress_sig`.
        cur = str(getattr(self.world, 'current_node', '') or '')
        if cur and cur == getattr(self, '_node_days_id', ''):
            self._node_days = int(getattr(self, '_node_days', 0) or 0) + 1
        else:
            self._node_days_id = cur
            self._node_days = 0

    def _days_in_node(self) -> int:
        """**当前这一站已经演了几章**（= 几个写作天，含今天这一章）。

        ⚠ 含"今天"：日界只在新的一天**开始**时才 +1，所以还在演的那一天
          不在计数里 —— 不含它就会让每一站都多演一天（章数下限整体 +1）。
        [EN] **How many chapters the current station has produced** (writing days, including today's).
        [EN] ⚠ Including today: the counter only increments when a new day **starts**, so the day
        [EN] currently being played is not counted -- excluding it would add a day to every station
        [EN] (the chapter minimum would be off by one, everywhere).
        """
        cur = str(getattr(self.world, 'current_node', '') or '')
        if not cur or cur != getattr(self, '_node_days_id', ''):
            return 1
        return int(getattr(self, '_node_days', 0) or 0) + 1

    def _advance_writing_day(self) -> int:
        """**写作天** +1（不是故事天！）。

        ★★★ 2026-10-26：两个"天"从此分开：
          · **故事天**（`world.game_day`）—— 故事里过了几天，可能一次跳 90 天；
          · **写作天**（`_current_day`）—— 这是第几份稿（文件名 `第003天.md`、导出标题）。
        以前它们共用 `world.game_day`。一旦"数月+带过"一拍推 90 天，
        共用就会让"第 3 天的稿子"里写着故事第 90 天的事 —— 文件名与内容对不上。
        ⚠ 写作天**必须严格 +1**：它决定文件名，跳号会让导出按天取时出现空洞。
        [EN] **Writing day** +1 (not the story day). ★★★ 2026-10-26: the two "days" separate from
        [EN] here. The **story day** (`world.game_day`) is how many days passed in the story, which
        [EN] can jump by 90; the **writing day** (`_current_day`) is which draft this is -- the file
        [EN] name `第003天.md` and the export title. They used to share `world.game_day`, and once a
        [EN] "months + in passing" beat jumps 90 days that sharing puts story-day 90 inside a file
        [EN] named "day 3". ⚠ The writing day **must be strictly +1**: it names files, and a gap
        [EN] makes per-day export lookups miss days.
        """
        return int(self._current_day or 0) + 1


    # ── 收尾与自动导出（§10.10）──────────────────────────────────────
    # [EN] ── Wrap-up and auto-export (§10.10)──────────────────────────────────────
    def _refresh_story_flow(self, *, force: bool = True) -> None:
        """重算这一次推演的「剧情总览」（`剧情总览.json`）—— **零 LLM**。

        ★ 为什么在程序这一侧算、而不是"打开对话框时让模型总结一遍"：
          ① 对话框是**查看**入口，不是付费动作；
          ② 它要的是"我演过什么"，那个事实在 `故事进度.yaml` + 每天的 json 里，
             本来就有（每站三十来字的概要），让模型再写一遍只会引入偏差；
          ③ 日界刷新如果花钱，"跑一夜"的账会翻倍。
        ★ 为什么挂在日界与收工两处：
          · 日界 —— 一天演完了，情节推进了，这时算最自然（和落盘、前情提要同一处）；
          · 收工 —— 最后那半天可能没到日界（`_ticks_today > 0` 的那天不落盘），
            不补这一下，用户停下后打开总览会看到"少了今天"。
        ⚠ 失败只记日志：**剧情总览坏了不许影响推演**（它是查看用的派生数据）。
        [EN] Recompute this run's story overview -- **no LLM involved**. ★ Why compute it here rather
        [EN] than "let a model summarise when the dialog opens": (1) the dialog is a **viewing** entry,
        [EN] not a paid action; (2) what it needs is "what did I play", which already exists in
        [EN] `故事进度.yaml` + the daily json (30-odd characters per station) -- a model rewrite would
        [EN] only add drift; (3) a refresh that costs money doubles the bill of an overnight run.
        [EN] ★ Hooks at two places: the day boundary (the plot advanced, same spot as persisting) and
        [EN] wrap-up (the last half-day may never reach a boundary, and without this the overview would
        [EN] be missing today). ⚠ Failures are logged only: derived viewing data must never break a run.
        """
        rf = getattr(self, 'runfolder', None)
        if rf is None:
            return
        try:
            from plot import flow as PF
            data = PF.ensure_flow(rf.project_dir, rf.root, force=force)
            _LOG.info('剧情总览已刷新：%d 站 / 演过 %d 站 / %d 天',
                      int((data.get('stats') or {}).get('points') or 0),
                      int((data.get('stats') or {}).get('played') or 0),
                      int((data.get('stats') or {}).get('days') or 0))
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning('剧情总览刷新失败（不影响推演）：%r', e)

    def _write_stop_point(self, reason: str, *, started: bool | None = None) -> None:
        """收尾时记下**停在哪儿**（下一轮「起笔」靠它决定从哪继续）。

        用户 2026-10-08：「点击之后如果检查发现**一天的时间还没结束**
        （之前在一天没结束的时候点的停止）则提示从某一天某个时间继续，
        如果一天已经结束了，则开启新一天」。

        ★ **必须在 `_end_day()` 之前调**：那一步会把 `_ticks_today` 清零，
          而下面那张表用的就是它。顺序反了，永远判成"这一天演完了"。

        | 这一刻 | 说明 | `day_done` |
        |---|---|---|
        | `_ticks_today > 0` | 这一天**演了一半**就停了（用户点名的那种） | `False` |
        | `_ticks_today == 0` | 这一天**还没开演**（上一次跨天已经收过工） | `True` |

        ★ `started`（2026-10-23 加，**只有中途落盘会传**）：显式说明"这一天开演了没有"。
          为什么需要它 —— **`_ticks_today` 是拍末才 +1 的**，于是
          "第一拍正在写、正文已经出来半幕"与"一拍还没跑"在这个计数上**长得一样**。
          中途落盘（`persist_partial`）看得见正文，所以它能给出更准的答案：
          有内容就算开演 ⇒ `day_done=False` ⇒ 下次从这一刻接着写，
          而不是退回 08:00 把已经写出来的半幕重写一遍。
          `None`（默认）= 按 `_ticks_today` 判，**收尾那条路一个字都没变**。

        ⚠ 失败只记日志（`write_stop_point` 自己吞）：停点是给下一轮的便条，
          写不出来最多下次当"第一次"处理，**绝不能影响收尾**。
        
                English:
        At wrap-up, record **where it stopped** (the next round's "start writing" uses it to decide
        where to continue).
                User 2026-10-08: "after clicking, if the check finds **the day hasn't finished yet**
                (stop was clicked earlier while the day wasn't over), then prompt to continue from some time on some day;
                if the day is already over, then start a new day".
                ★ **Must be called before `_end_day()`**: that step clears `_ticks_today`,
                  and the table below uses it. If the order is reversed, it will always judge "this day is finished".
                | This moment | Description | `day_done` |
                |---|---|---|
                | `_ticks_today > 0` | This day stopped **halfway through** (the case the user pointed out) | `False` |
                | `_ticks_today == 0` | This day **hasn't started** (the last cross-day already wrapped up) | `True` |
                ★ `started` (added 2026-10-23, **only the mid-progress flush passes it**): states
                  explicitly whether this day has begun. Why it is needed -- **`_ticks_today` is only
                  incremented at the end of a beat**, so "the first beat is being written, half an act is
                  already out" and "not a single beat has run" look identical to that counter. The
                  mid-progress flush (`persist_partial`) can see the body, so it gives a more accurate
                  answer: content means started => `day_done=False` => resume from this moment instead of
                  rewriting the half act that already exists.
                  `None` (default) = judge by `_ticks_today`, so **the wrap-up path is unchanged**.
                ⚠ Failures are only logged (`write_stop_point` swallows them itself): the stop point is a note for the next round,
                  If it can't be written, treat it as a "first time" next time at worst, **must never affect the wrap-up**.
        """
        try:
            from sim import resume as RESUME
            day = int(self._current_day or 0) or int(
                getattr(self.world, 'game_day', 0) or 1)
            clock = getattr(self.world, 'clock', None)
            # `started is None` ⇒ 老口径（按 `_ticks_today`）；中途落盘传的是"有没有正文"。
            # ★★★ 2026-10-31：老口径**再加一条** `_day_opened_for == _current_day`。
            #   只用 `_ticks_today > 0` 会把"这一天**开了场**、剧本正在生成、一拍还没跑完"
            #   判成"这一天还没开演"（`day_done=True`）—— 于是下一轮从**同一天 08:00
            #   重演一遍**，把这一天已经写出来的稿子覆盖掉。
            #   实测（`第一部_聊斋夜客` 第2次模拟）：停点里 `day=3 / 今天跑了 0 拍 /
            #   这一天演完了`，而 `第003天.md` 早已有正文 —— 两个事实互相矛盾。
            #   `_day_opened_for` 在 `_open_day()` 成功后钉成当天的写作天，它才是
            #   "今天开过场没有"的权威字段（`_ticks_today` 只数演完的拍）。
            # [EN] `started is None` => old rule (by `_ticks_today`); the mid-progress flush passes
            # [EN] "is there any body text".
            # ★★★ 2026-10-31: the old rule gains one more clause: `_day_opened_for == _current_day`.
            #   Judging by `_ticks_today > 0` alone marks "this day **opened**, its script is still
            #   being generated, not one beat has finished" as "this day has not started"
            #   (`day_done=True`) -- so the next round **replays the same day from 08:00** and
            #   overwrites the prose already written for it. Measured in the second run of
            #   `第一部_聊斋夜客`: the stop point says `day=3 / 0 beats / this day is over` while
            #   `第003天.md` already has a body -- two contradictory facts.
            _begun = ((self._ticks_today > 0
                       or int(getattr(self, '_day_opened_for', 0) or 0) == int(day))
                      if started is None else bool(started))
            RESUME.write_stop_point(
                self.runfolder,
                day=day,
                # ★ 故事天单列一份：`day` 是**写作天**（第几份稿），故事钟可能因为
                #   "站末补时间"跑在前面。续跑建时钟要用**故事天**，拿 `day` 去建会倒退。
                # [EN] The story day gets its own field: `day` is the **writing day** (which draft),
                #   and the story clock can run ahead after a station-gap jump. Resuming must build
                #   the clock from **the story day**; using `day` would move time backwards.
                story_day=int(getattr(self.world, 'game_day', 0) or day),
                minutes=int(getattr(clock, 'minutes', 0) or 0),
                calendar=self.world.clock_display(),
                # 纯时辰（`clock_display()` 是「第3天·戌时」那种整串，
                # 拼「第 N 天 · X」时会重复天数）
                # [EN] pure hour (``clock_display()` is a whole string like "Day 3·Xu hour",
                # [EN] concatenating "Day N · X" would duplicate the day count)
                shichen=str(getattr(clock, 'shichen', '') or ''),
                day_done=(not _begun),
                ticks_today=int(self._ticks_today or 0),
                scene=str(getattr(self.world, 'scene', '') or ''),
                reason=str(reason or ''),
                # 演了一半的那一天才是"半截稿"；演完了的那天不记。
                # [EN] a day that was performed halfway is a "half-draft"; a day fully performed is not recorded.
                partial_day=(day if _begun else None),
            )
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('停点记录失败（不影响收尾）：%r', e)

    def persist_partial(self, reason: str = 'timer') -> dict:
        """**把"现在演到哪儿"落成一份可续跑的半截稿**（定时落盘调它）。

        ★★★ 2026-10-23 用户原话（这条就是本次改动的全部规格）：

            「有时候电脑会突然关机 或者可能随手关闭程序……我想随时软件或者电脑突然
              退出的时候 我下一次打开拾卷里的存档 可以拿到最近的记录（最多损失 30 秒）」

        ## 改之前是什么样（用户问的那个问题的答案）

        | 落什么 | 改之前 | 断电后后果 |
        |---|---|---|
        | `自动落盘/进度.md` | 每 30 秒 | **只有人能看**，续跑/拾卷都不读它 |
        | `每天的生活/第NNN天.md(.json)` | 只在日界 / 收工 | 丢**整天**正文 |
        | `停点.json` | 只在收工 | 续跑从**上一次收工**的位置起，丢整轮 |

        也就是说：用户问"是起笔就创建、每 30 秒更新，还是停止时才更新" ——
        **实质是后者**（就"能不能接着上次继续"而言）。这份方法就是把它改成前者。

        ## 落两份，缺一不可

        1. **当天正文** → `每天的生活/第NNN天.md` + `.json`（带 `⏳ 定时落盘` 标记）。
           为什么必须是这两个文件：`read_daily_script()` 只认它们，
           而 `load_resume_scenes()` 续跑时正是靠它把**那一天的半截正文**读回来
           —— 只写 `自动落盘/进度.md` 的话，位置接上了、内容却是空的。
        2. **停点** → `停点.json`（`day_done=False`、`partial_day=当天`）。
           复用 `_write_stop_point`：它的 `day_done` 判定（`_ticks_today <= 0`）
           对"中途"同样成立（今天一拍没跑 ⇒ 这一天没开演 ⇒ 下一轮开新的一天）。

        ## 三条纪律

        · **绝不改世界状态**：不 `builder.flush()`（那会清空当前幕）、不 `reset_topic`、
          不动 `_ticks_today`、不跑任何 LLM。它只"读现在"然后写盘。
        · **绝不抛**：落盘是保险（见 `sim/autosave.py` 的三条纪律）。
        · **绝不写空**：一幕都没有（刚起笔、或纯文本模式还没内容）时**跳过正文**，
          只更新停点 —— 写一份空稿会把已有的内容盖掉，比不写更坏。

        返回一份结果（`ok` / `wrote` / `day` / `lines`），供日志与判据看。
        """
        if self.runfolder is None:
            return {'ok': False, 'error': 'no-runfolder', 'reason': reason}
        day = int(self._current_day or 0) or int(
            getattr(self.world, 'game_day', 0) or 1)
        stamp = now_str('%H:%M:%S')
        wrote = ''
        lines = 0
        # ★ "这一天开演了没有" —— **看正文，不看 `_ticks_today`**。
        #   `_ticks_today` 是拍末才 +1 的，于是"第一拍正在写"和"一拍还没跑"在那上面一样；
        #   而决定"下次从哪起"的恰恰是"有没有已经写出来的东西"。
        # [EN] ★ "Has this day begun" -- look at the **body**, not `_ticks_today` (incremented only at
        # [EN] the end of a beat, so "first beat in progress" and "no beat yet" look the same there).
        begun = bool(int(self._ticks_today or 0) > 0)
        try:
            # ★★★ 2026-10-26：**脚本模式下绝不许落到纯文本分支**。
            #
            #   以前的条件是 `if self._script_mode and self._builder is not None:`，
            #   于是 `_builder is None`（收工落盘后它被置 None，见 `_end_day`）
            #   会掉进 `else` 的纯文本分支 ⇒ 用 `_daily_narrative`（那一刻只剩十几句）
            #   **覆盖掉** `第NNN天.md` 里那份完整剧本，而 `.json` 边车还是完整的。
            #
            #   实测后果（望江楼第 5 次）：第 1 天 `.json` 有 133 幕 / 21.3 万字，
            #   而 `.md` 被盖成 **381 字**；导出读 `.md` ⇒ 用户看到「完全不是一个故事」。
            #
            #   ⇒ 现在：脚本模式但 builder 已没了 = 这一天**已经收尾落过盘**，
            #     正文**一个字都不动**（只更新停点，那是另一件事）。
            #     要补写正文可以，但必须走 `flush_daily_script`（保持同一格式）。
            # [EN] ★★★ 2026-10-26: **script mode must never fall into the plain-text branch.**
            # [EN] The old condition let `_builder is None` (set at `_end_day`) drop into `else`,
            # [EN] overwriting the full script `第NNN天.md` with `_daily_narrative` (a dozen lines
            # [EN] at that point) while the `.json` sidecar stayed complete. Measured: day 1 `.json`
            # [EN] had 133 acts / 213k chars while `.md` was down to **381 chars**, and exports read
            # [EN] `.md`. Now: script mode with no builder means the day is already flushed --
            # [EN] **touch no body text** (only the stop point, which is a separate concern).
            if self._script_mode:
                if self._builder is None:
                    _LOG.debug('中途落盘：脚本模式但这一天的幕已收（builder=None），'
                               '正文不动，只更新停点')
                else:
                    groups = [sc for sc in (list(self._builder.scenes) or []) if sc is not None]
                    cur = getattr(self._builder, 'current', None)
                    if cur is not None and cur not in groups:
                        groups.append(cur)
                    # ⚠ 过滤空幕：刚开一幕还没落任何条目时，`to_markdown` 会给空块，
                    #   写进去就是一行莫名的空段落。
                    # [EN] ⚠ Filter empty acts: an act just opened with no entries yields an empty block
                    # [EN] from `to_markdown`, which lands as a stray blank paragraph.
                    groups = [sc for sc in groups
                              if (getattr(sc, 'entries', None) or [])]
                    if groups:
                        self.runfolder.flush_daily_script(
                            day, groups,
                            calendar_str=self.world.clock_display(),
                            weather=str(getattr(self.world, 'weather', '') or ''),
                            cast=self.world.on_stage_names(),
                            tension=f'{float(getattr(self.world, "tension", 0.0) or 0.0):.2f}',
                            recap=self._recap_text(),
                            scene_intro=str(getattr(self._day_script, 'scene_intro', '') or ''),
                            day_brief=str(getattr(self._day_script, 'day_brief', '') or ''),
                            partial_at=stamp)
                        wrote = 'script'
                        lines = sum(len(getattr(sc, 'entries', None) or []) for sc in groups)
                        begun = True
            else:
                body = "\n\n".join(str(x) for x in (self._daily_narrative or [])
                                   if str(x).strip())
                if body:
                    self.runfolder.flush_daily(
                        day, body, calendar_str=self.world.clock_display(),
                        partial_at=stamp)
                    wrote = 'text'
                    lines = len([x for x in (self._daily_narrative or []) if str(x).strip()])
                    begun = True
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('中途落盘：写当天正文失败（不影响推演）：%r', e)
        # ★ 停点**无论正文写没写都要更新**：它决定"下次从哪起"，
        #   而"从哪起"和"有没有正文"是两件事（正文为空时至少位置是对的）。
        # [EN] ★ The stop point is updated **whether or not the body was written**: it decides "where
        # [EN] to resume from", which is a different thing from "is there a body".
        try:
            self._write_stop_point(f'autosave:{reason}', started=begun)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('中途落盘：写停点失败（不影响推演）：%r', e)
        # ★ 每次落盘记一条（含"写成了什么"）——「断电能不能接上」这类问题，
        #   事后只能靠这行日志分辨"没写"还是"写了但别处坏了"。
        # [EN] ★ Log every flush, including **what was written** -- for "can it resume after a power
        # [EN] cut", this line is how you later tell "not written" from "written but broken elsewhere".
        _LOG.info('中途落盘（%s）：第 %d 天 · 正文=%s · %d 条 · 开演=%s',
                  reason, day, wrote or '（无内容，跳过）', lines, '是' if begun else '否')
        return {'ok': True, 'day': day, 'wrote': wrote, 'lines': lines,
                'at': stamp, 'reason': reason}
    async def _finish(self, reason: str) -> None:
        """收尾：先把最后一天落盘，再按开关自动导出。

        为什么要单独一步？循环只在「天数变化」时才落盘，
        跑到一半停下时**当天还没落盘**——不补这一步，最后一天就白跑了，
        导出出来的稿子也会少一天。

        ★ **第一步先记「停点」**（2026-10-08，用户要的"下次起笔知道从哪儿继续"）：
          必须排在 `_end_day()` **之前** —— 那一步会把 `_ticks_today` 清零，
          而"这一天演完没有"的判据正是它（见 `sim/resume.py` 模块说明）。
        
                English:
        Wrap-up: first persist the final day to disk, then auto-export according to the switch.
                Why is this a separate step? The loop only persists to disk when the "day changes",
                and when it stops midway, **the current day hasn't been persisted yet** -- without this extra step, the final day is wasted,
                and the exported manuscript will also be missing a day.
                ★ **The first step is to record the "stop point"** (2026-10-08, what the user asked for: "next time I start writing, know where to continue from"):
                  It must come **before** `_end_day()` -- that step clears `_ticks_today` to zero,
                  and the criterion for "whether this day has finished playing out" is exactly that (see the `sim/resume.py` module docstring).
        """
        # ★★★ 2026-10-21（用户点名「状态条要一直显示当前正在做什么以及做了多久」）：
        #   **把整段收尾包成一个有始有终的登记**，这样从"点了停止"到"全部结束"，
        #   状态条上永远有东西：
        #     · 收尾各步自己的阶段/职位会盖在它上面（`场记 · 连戏检查` / `整理当天这一章`）；
        #     · 任何一步没登记的时候，回落到这条「收尾（落盘 + 总结）」。
        #   ⚠ 用 push/pop（不是 `_stage`）的原因：`_stage` 会在结束时**再推一条中栏消息**
        #     （「▸ 收尾 · 120s」），而那条 `stop()` 已经推过一次（`_stage_start('stopping')`），
        #     重复推会让用户以为停了两次。
        #   ⚠ 必须 `try/finally`：收尾里任何一步抛异常都不能把这条留在栈上
        #     （那会让状态条一直写着"收尾"，而实际上已经结束了）。
        # [EN] ★★★ 2026-10-21 (user: "the status bar must always show what is being done and for how
        # [EN] long"): **wrap the whole wrap-up in a start/end registration**, so from "stop clicked" to
        # [EN] "everything done" the bar always has something: each step's own stage/role covers it,
        # [EN] and when nothing else is registered it falls back to "wrapping up".
        # [EN] ⚠ push/pop rather than `_stage`: `_stage` would also push a second middle-column message
        # [EN] ("▸ 收尾 · 120s") while `stop()` already pushed one (`_stage_start('stopping')`), and a
        # [EN] duplicate makes the user think it stopped twice.
        # [EN] ⚠ Must be `try/finally`: any failing step must not leave the label on the stack, or the
        # [EN] bar keeps saying "wrapping up" after it has finished.
        from crew import doing as _DOING
        # ★★★ 收尾一开始就**摘掉欠费回调**（2026-10-25）。
        #   "没钱了"只在**推演进行中**有意义；收尾这一段（补落 → 场记/复盘 →
        #   整理稿 → 导出）本来就会再调模型，而这一轮已经在结束了 ——
        #   此时暂停会把「正在停止 / 正在收尾」顶成「等你点继续」，
        #   而用户其实什么都没点。收尾里撞上欠费该怎么表现（跳过那一步、如实说缺什么）
        #   另有各步自己的兜底。
        #   ⚠ 摘之前记下来：`stop()` 也摘过一次，重复摘是安全的（`off_block` 容错）。
        # [EN] ★★★ **Drop the credit callback the moment wrap-up starts** (2026-10-25). "Out of money"
        # [EN] only matters **while the simulation is running**; the wrap-up (persist -> continuity /
        # [EN] retrospective -> organizer -> export) calls models again, but this round is already
        # [EN] ending -- pausing here would flip "stopping / wrapping up" into "waiting for resume"
        # [EN] when the user pressed nothing. What a credit failure should do during wrap-up (skip that
        # [EN] step, say honestly what is missing) is each step's own fallback.
        # [EN] ⚠ `stop()` also drops it; dropping twice is safe (`off_block` tolerates it).
        if getattr(self, '_credit_cb', None) is not None:
            CREDIT.off_block(self._credit_cb)
        _wrap_tok = _DOING.push(_DOING.stage_label('stopping'))
        try:
            await self._finish_steps(reason)
        finally:
            _DOING.pop(_wrap_tok)

    async def _finish_steps(self, reason: str) -> None:
        """收尾**实际做的事**（`_finish` 只负责把它包进"收尾"这个登记里）。

        ⚠ 拆成两个方法不是为了好看：`_finish` 外面多了 `try/finally`，
          整个函数体再缩进一层会动到 100 多行（本项目刚吃过"切代码切错整段"的亏）。
          `_finish_steps` 的正文与原 `_finish` 完全一致。
        [EN] The **actual work** of wrap-up (`_finish` only wraps it in the "wrapping up" registration).
        [EN] ⚠ Split not for beauty: `_finish` gained a `try/finally` and re-indenting 100+ lines would
        [EN] touch them all (this project just got burned by cutting a block wrong).
        """
        self._write_stop_point(reason)
        if self._tick_no > 0 and self._ticks_today > 0:
            try:
                await self._end_day()
            except Exception as e:                      # noqa: BLE001
                _LOG.warning("收尾落盘失败: %s", e)
        elif self._tick_no > 0:
            # 跑到这儿说明：跑到中途被停，而**这一天还没跑过任何一拍**
            # （典型：跨天那一刻点了停止，上一天已经落过盘）。
            # 那就**不要再落一天空稿、再写一份重复的今日总结** —— 见 `_ticks_today`。
            # [EN] Getting here means: it was stopped midway, and **this day has not run a single beat**
            # [EN] (typical: stop was clicked at the moment of crossing days, the previous day had already been
            # [EN] saved).
            # [EN] Then **do not save another empty day's draft, nor write another duplicate today's summary** ——
            # [EN] see `_ticks_today`.
            _LOG.info('收尾：第 %d 天还没跑过一拍，跳过落盘与总结'
                      '（上一天已经收过）', int(self._current_day or 0))
        # ★★★ 2026-10-21：**停止时兜底把今天这一章推到窗口**（用户点名两次）。
        #   正常路径上 `_end_day()` → `_day_novel()` 已经推过一次，这里会看到"已推过"就跳过；
        #   真正被它救下的是两种：`_end_day()` 抛异常（整理没跑）、
        #   以及「每日整理」关掉时 `_day_novel` 第一行就 return（窗口永远空）。
        #   ⚠ 位置有意排在 `_end_day()` **之后**：先让正常路径去整理（质量好、会落盘），
        #     这里只补它没做到的；排前面就会变成"先推原文、再推整理稿"两章。
        #   [EN] ★★★ 2026-10-21: **stop-time fallback that pushes today's chapter to the window**
        #   [EN] (named twice by the user). On the normal path `_end_day()` -> `_day_novel()` already
        #   [EN] pushed once and this sees "already pushed" and skips; what it actually rescues are two
        #   [EN] cases: `_end_day()` raised (organizing never ran), and "daily organization" off (where
        #   [EN] `_day_novel` returns on its first line and the window stays empty forever).
        #   [EN] ⚠ Deliberately placed **after** `_end_day()`: let the normal path organize first (better
        #   [EN] quality, saves to disk) and only fill in what it missed; placed earlier it would push the
        #   [EN] raw text and then the polished draft -- two chapters.
        await self._flush_novel_on_stop(reason)
        # ★ 收工时把「剧情总览」补一遍（见 `_refresh_story_flow`）：最后那半天可能
        #   没到日界（`_ticks_today > 0` 的那一天不落盘），不补就会看到"少了今天"。
        #   排在导出**之前**：导出/交付目录里那份总览才是最新的。
        # [EN] Refresh the story overview at wrap-up (see `_refresh_story_flow`): the last half-day may
        # [EN] never reach a day boundary, and without this it looks like "today is missing". Placed
        # [EN] **before** the export so the copy in the deliverable is current.
        self._refresh_story_flow(force=False)   # 上面 `_end_day` 刚写过就不用重算
        # ★「一个故事结束」的分隔符（用户要的第三类）
        # [EN] ★ The "one story ends" separator (the third category the user wanted)
        try:
            self._push_divider(D.story_end(
                day=int(self._current_day or 0)
                or int(getattr(self.world, 'game_day', 0) or 0),
                note=str(reason or '')[:24]))
        except Exception:                                   # noqa: BLE001
            pass
        # ★ `ENDING_SCENE`（以前零读取）：收尾时在运行文件夹里留一节「结局」——
        #   把最后一天的收束写清楚（谁在哪儿、事情了结到什么程度）。
        #   它是**给作者看的小结**，不改正文（正文在「每天的生活」里）。
        # [EN] ★ `ENDING_SCENE` (previously zero readers): at wrap-up, leave a section "ending" in the run
        # [EN] folder ——
        # [EN] write clearly the conclusion of the last day (who is where, to what degree things are resolved).
        # [EN] It is a **little summary for the author**, does not change the main text (the main text is in
        # [EN] "daily life").
        if CFG.b("ENDING_SCENE"):
            try:
                await self._write_ending(reason)
            except Exception as e:                              # noqa: BLE001
                _LOG.warning("结局小节生成失败（不影响推演）：%r", e)

        if self._will_auto_export():
            # 「模块开始」也用分隔符划一道（用户："分隔符还可以用于某个模块开始"）
            # [EN] "Module start" is also marked with a separator (user: "separators can also be used at the start
            # [EN] of a module")
            self._push_divider(D.module_start('导出', ''))
        await self._auto_export(reason)

    async def _flush_novel_on_stop(self, reason: str) -> None:
        """**停止时兜底**：确保「今天这一章」真的出现在推演窗口里。

        ★★★ 2026-10-21（用户点名，两次）：
          「点击停止的时候、或者某次推演结束的时候，可以自动把根据推演生成的小说
           输出到推演窗口里（默认可以是收起来的，用户点了才展开，或者这个是收还是展开
           用户可以配置）」。

        正常路径本来就有：`_finish` → `_end_day()` → `_day_novel()`（整理 + 落盘 + 推送）。
        但有**两个真实缺口**，都会让窗口一片空白、而用户以为"点了停止就该有一章"：

          ① `_end_day()` 抛异常 —— 收尾那一步只 `_LOG.warning` 就往下走了，
             整理那一步根本没执行；
          ② `CREW_DAY_NOVEL`（每日整理）被关掉时，`_day_novel` **第一行就 return**，
             于是窗口永远是空的。

        ★★★ **这里绝不调 LLM**（2026-10-21 判据当场抓到过一版这么写的）：
          第一版在"整理开着"时补调了一次 `_day_novel`，本意是"补它没做到的"，
          结果 `verify_run_control` 从 68 项掉到 55 项 —— **整条收尾链卡死在这次整理上**，
          停止后的落盘、状态置 stopped、自动导出全没跑。
          那不是判据脆弱，是**产品错了**：用户点停止要的是"快点停、然后让我看看稿子"，
          收尾里再插一次几十秒到几分钟的 LLM 整理，等于"点了停止还要再等一通"。
          ⇒ 所以这里只做**搬运**：
            · 今天的整理稿**已经存在**（`当天故事.md` 里那一天的章节）→ 直接推它；
            · 没有 → 推当天原文（标明"未整理"）；
            · 连原文都没有 → 安静跳过。
          整理本身仍然是 `_day_novel` 的活，只在收工那一刻跑一次。

        ⚠ 三道防重复 / 防误触：
          1. **同一天推过就不再推**（`_novel_pushed_days`，`_day_novel` 推送成功后记的）
             —— 否则一次停止会在窗口里留下两份几乎一样的正文；
          2. `SHOW_NOVEL_IN_WINDOW` 关着就一步都不做（用户明确不要）；
          3. 今天一个字都没有就**安静跳过**（不为了"有反馈"硬推一条空章节）。

        ⚠ 整个方法**不许抛**：它挂在收尾链上，抛出去会吃掉后面的自动导出。
        
                English:
        **Stop-time fallback**: make sure "today's chapter" really shows up in the simulation window.
                ★★★ 2026-10-21 (named twice by the user): on stop, or when a run finishes, the novel written
                from the simulation should appear in the window by itself (collapsed by default, expandable,
                configurable).
                The normal path already exists: `_finish` -> `_end_day()` -> `_day_novel()` (organize + save +
                push). But there are **two real gaps** that leave the window blank while the user believes
                "hitting stop should give me a chapter":
                  ① `_end_day()` raises -- the wrap step only logs a warning and moves on, so organizing never ran;
                  ② with `CREW_DAY_NOVEL` off, `_day_novel` **returns on its first line**, so the window stays empty.
                ★★★ **This method never calls an LLM** (a first version did, and the criteria caught it
                immediately): that version re-ran `_day_novel` when organization was on, meaning to "fill in
                what it missed", and `verify_run_control` dropped from 68 to 55 -- **the whole wrap-up chain
                stalled on that call**, so persistence, the stopped status and the auto export never ran.
                That was not a brittle criterion, it was a **product bug**: hitting stop means "stop quickly,
                then show me the draft", and inserting another tens-of-seconds-to-minutes LLM pass into the
                wrap-up means "hit stop and wait all over again".
                => So this only **relocates text**: if today's organized chapter already exists (in
                `当天故事.md`), push that; otherwise push the day's raw text marked "unpolished"; otherwise
                skip quietly. Organizing remains `_day_novel`'s job, run once at wrap time.
                ⚠ Three guards: 1) never push the same day twice; 2) do nothing when
                `SHOW_NOVEL_IN_WINDOW` is off; 3) skip quietly when the day has no text.
                ⚠ Must never raise: it sits on the wrap-up chain and would swallow the auto export.
        """
        try:
            if not CFG.b('SHOW_NOVEL_IN_WINDOW'):
                return
            day = int(self._current_day or 0)
            seen = getattr(self, '_novel_pushed_days', None)
            if seen is None:
                seen = set()
                self._novel_pushed_days = seen
            if day and day in seen:
                _LOG.info('停止时补推：第 %d 天已经推过这一章了（不重复推）', day)
                return
            raw = list(self._daily_narrative or [])
            lines = self._day_lines(raw)
            body = '\n'.join([str(x) for x in (lines or []) if str(x).strip()]).strip()
            # ① 今天的整理稿如果已经落盘了，直接搬它（质量最好，且零成本）
            done = self._organized_chapter_of_day(day)
            if done:
                self._push_narrative(done, 2, kind=S.NOVEL)
                seen.add(day)
                _LOG.info('停止时补推：第 %d 天用已落盘的整理稿（%d 字）', day, len(done))
                return
            if not body:
                _LOG.info('停止时补推：第 %d 天没有可推的正文（安静跳过）', day)
                return
            # ② 没有整理稿：推原文，并说清楚「这不是整理稿」
            self._push_narrative(
                '（**未整理**：这一章还没经过整理，下面是今天已经写出来的正文原文。'
                '如果「每日整理」是开着的，收工时会整理成章节并再推一次。）\n\n' + body,
                2, kind=S.NOVEL)
            seen.add(day)
            _LOG.info('停止时补推：第 %d 天按原文直推（%d 字，无整理稿）', day, len(body))
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning('停止时补推当天这一章失败（不影响推演与导出）：%r', e)

    def _organized_chapter_of_day(self, day: int) -> str:
        """从 `当天故事.md` 里取**第 day 天**那一节的正文（没有就空串）。

        ⚠ 只读、不调 LLM：这是停止兜底用的"现成稿"。
        ⚠ 解析按 `## 第 N 天` 开头切节（`_day_novel` 写进去的就是这个格式）。
        [EN] Take day N's section body out of `当天故事.md` (empty string if absent).
        [EN] ⚠ Read-only, no LLM: this is the "ready-made draft" for the stop fallback.
        [EN] ⚠ Sections are cut on a `## 第 N 天` heading (the format `_day_novel` writes).
        """
        if not day or self.runfolder is None:
            return ''
        try:
            f = Path(self.runfolder.root) / CREWSTUDIO.FILE_DAY_NOVEL
            if not f.is_file():
                return ''
            txt = f.read_text(encoding='utf-8')
        except Exception:                                       # noqa: BLE001
            return ''
        head = f'## 第 {int(day)} 天'
        i = txt.find(head)
        if i < 0:
            return ''
        # ⚠ 必须**跳到这一行的行尾**再开始：标题是 `## 第 1 天 · 第1天·辰时`
        #   （`_day_novel` 写的是 `## 第 N 天 · {clock_display}`），
        #   只切掉 `## 第 1 天` 会把「 · 第1天·辰时」这条**幕头**留在正文开头，
        #   推给用户就是"小说正文以一行时间戳开头"（实测如此）。
        # [EN] ⚠ Jump to the **end of that line** before starting: the heading is
        # [EN] `## 第 1 天 · 第1天·辰时` (what `_day_novel` writes), and cutting only `## 第 1 天`
        # [EN] leaves the " · 第1天·辰时" act header at the top of the body -- the reader then gets
        # [EN] "a novel that starts with a timestamp line" (measured exactly that).
        eol = txt.find('\n', i)
        if eol < 0:
            return ''
        rest = txt[eol + 1:]
        # 到下一个 `## 第 ` 或文件末尾为止
        j = rest.find('\n## 第 ')
        return rest[:j].strip() if j >= 0 else rest.strip()

    async def _write_ending(self, reason: str) -> None:
        """写 `<运行文件夹>/结局.md`（`ENDING_SCENE`）。

        内容三样：结束原因、最后那天的收束、以及**还没了结的线**
        （未完成节点 / 未激活的伏笔 / 还活着的钩子群演）——
        最后一样是给"以后接着写"用的，没有它下次开写要想半天。
        
                English:
        Write `<run folder>/结局.md` (`ENDING_SCENE`).
                Three things in the content: the reason for ending, the closing of the final day, and **the threads not yet resolved**
                (unfinished nodes / unactivated foreshadowing / still-alive hook extras) --
                the last one is for "continuing to write later"; without it, the next writing session takes ages to figure out.
        """
        if not self.runfolder:
            return
        open_lines = [str(x) for x in (self.world.active_lines or []) if str(x).strip()]
        pending = [str(nd.get("名称") or nd.get("id") or "")
                   for nd in (self.world.progress_nodes or [])
                   if nd.get("状态") != "已完成"]
        hooks = [str(h.get("称呼") or "") for h in (self.world.hooks or [])][:8]
        tail = list(self._daily_narrative)[-6:]
        parts = [f"# 结局（第 {self.world.game_day} 天）", "",
                 f"> 本轮结束原因：{reason or '（未标注）'}",
                 f"> 时间：{self.world.clock_display()}　地点：{self.world.scene}", ""]
        if tail:
            parts += ["## 最后一段", ""] + tail + [""]
        if open_lines:
            parts += ["## 还没了结的线", ""] + [f"- {x}" for x in open_lines] + [""]
        if pending:
            parts += ["## 没走完的进度节点", ""] + [f"- {x}" for x in pending] + [""]
        if hooks:
            parts += ["## 还认得的临演（以后可以叫回来）", ""] + hooks + [""]
        atomic_write_text(self.runfolder.root / '结局.md', "\n".join(parts))
        _LOG.info("结局小节已写：结局.md（未完成节点 %d 个）", len(pending))

    def _will_auto_export(self) -> bool:
        """这一轮结束时会不会真的自动导出？**只是想给界面一句准话**，
        拿不准就说不会（宁可少画一条分隔符，也别画一条骗人的）。
                English:
        Will this round actually auto-export when it ends? **Just want to give the UI a definitive
        answer**,
                if unsure, say it won't (better to draw one fewer separator than to draw a lying one).
        """
        try:
            from export import bundle
            return bool(bundle.auto_kinds())
        except Exception:                                   # noqa: BLE001
            return False

    async def _auto_export(self, reason: str) -> None:
        """按配置自动导出。**失败只记日志，绝不改变运行结果。**
                English:
        Auto-export according to config. **On failure, only log; never change the run result.**
        """
        try:
            from export import bundle
        except Exception as e:                          # noqa: BLE001
            _LOG.warning("导出模块不可用: %s", e)
            return
        kinds = bundle.auto_kinds()
        if not kinds:
            _LOG.info("运行结束（%s）：自动导出全关，跳过", reason)
            return
        try:
            res = await bundle.export_on_end(self.runfolder, world=self.world,
                                             db=self.db, ledger_cost=self._ledger_cost())
        except Exception as e:                          # noqa: BLE001
            _LOG.warning("自动导出失败（不影响运行结果）: %s", e)
            return
        if res:
            shown = "、".join(f"{i['label']}{'✓' if i['ok'] else '✗'}"
                              for i in res["items"])
            _LOG.info("自动导出完成（%s）: %s", reason, shown)

    def _ledger_cost(self) -> dict | None:
        """本次运行的 token 账单（从启动水位切起）。
                English:
        The token bill for this run (measured from the starting watermark).
        """
        recs = llm.ledger.records[getattr(self, "_ledger_mark", 0):]
        if not recs:
            return None
        out: dict = {"calls": len(recs), "in": 0, "out": 0,
                     "by_purpose": {}, "by_model": {}}
        for r in recs:
            out["in"] += r.in_tok
            out["out"] += r.out_tok
            for bucket, key in (("by_purpose", r.purpose), ("by_model", r.model)):
                slot = out[bucket].setdefault(key or "未标注",
                                              {"calls": 0, "in": 0, "out": 0})
                slot["calls"] += 1
                slot["in"] += r.in_tok
                slot["out"] += r.out_tok
        return out

    async def _tick(self, tick_num: int) -> str | None:
        """单次 tick（**一拍**）。返回结束原因（None=继续）。

        时钟已经在 `run()` 的 `_advance_clock()` 里推进过了 —— 这里不再碰时间，
        只做"这一拍发生了什么"。

        ★ 2026-10-07 第八轮：**请求停止就立刻收手，不再往下做这一拍**。
          这一拍后面的每一步都可能花钱（导演挑事 / 派活 / 每人的决策 /
          群聊 / 后台批次），而用户已经点了停止 —— 继续做只是让他多等。
          ⚠ 返回值保持 `None`：结束由 `run()` 的循环条件负责，
            **不要在这里返回"手动停止"** —— 那会让 `_finish` 少走
            `_end_day` 那条路（收尾与总结都在那儿）。
        
                English:
        A single tick (**one beat**). Returns the end reason (None = continue).
                The clock has already been advanced in `run()`'s `_advance_clock()` -- don't touch time here,
                only do "what happened in this beat".
                ★ 2026-10-07 eighth round: **on a stop request, stop immediately and don't do the rest of this beat**.
                  Every subsequent step of this beat may cost money (director stirring things up / assigning tasks / each person's decision /
                  group chat / background batch), and the user has already clicked stop -- continuing just makes him wait longer.
                  ⚠ Keep the return value as `None`: ending is handled by `run()`'s loop condition,
                    **do not return "manual stop" here** -- that would make `_finish` skip the
                    `_end_day` path (the wrap-up and summary are both there).
        """
        if self.stopping:
            return None

        # 这一拍算数了（收尾时要判"今天有没有东西可落"，见 `_ticks_today`）
        # [EN] This beat counted (at wrap-up it is judged "is there anything to save today", see
        # [EN] `_ticks_today`)
        self._ticks_today += 1

        # ★★★ 2026-10-26：**故事时间在这里往前走**（用户选 A：日界 = 拍预算用完）。
        #
        #   改之前时间是在 `_advance_clock()` 里按"真实流逝 × TIME_RATIO"推的 ——
        #   一拍恒定吃 `BEAT_SECONDS` 故事秒，于是"一场审讯"和"三个月赶路"
        #   占用一样长的故事时间，而"一天"必须填满 24 小时 ⇒ 一天演 133 幕。
        #
        #   现在：一拍推多久 = 这一站的**剩余故事时长 ÷ 剩余拍数**
        #   （`_beat_minutes_now`），于是
        #     · `一场 + 详`  ⇒ 一拍 2 分钟，60 拍刚好 2 小时；
        #     · `数月 + 带过` ⇒ 一拍 30 分钟（上限），站末再跳 89 天 23.5 小时。
        #   ⚠ 放在 `_ticks_today += 1` **之后**：`_beat_minutes_now` 要读剩余拍数，
        #     而"这一拍"是算进去的（否则每拍都会多算一次余量）。
        # [EN] ★★★ 2026-10-26: **story time advances here** (the user chose A: the day ends when the
        # [EN] beat budget runs out). It used to advance inside `_advance_clock()` by "real elapsed x
        # [EN] TIME_RATIO", so every beat ate a constant `BEAT_SECONDS` and "one interrogation"
        # [EN] occupied the same story time as "three months on the road"; and a day had to fill 24
        # [EN] hours, hence 133 acts per day. Now a beat advances "the station's remaining story time
        # [EN] / remaining beats" (`_beat_minutes_now`): `one scene + full` gives 2 minutes per beat
        # [EN] (60 beats = 2 hours) and `months + in passing` gives 30 minutes per beat plus an 89-day
        # [EN] jump at the station's end. ⚠ Placed **after** `_ticks_today += 1` because
        # [EN] `_beat_minutes_now` reads the remaining beats, and this beat counts.
        self._walk_beat_time()

        # AUTO_RUN_DAYS 检查
        # ★★★ 2026-10-26：**按写作天数**，不按 `world.game_day`。
        #   两个"天"现在分开了（见 `_advance_writing_day`）：故事日可能一次跳 90 天
        #   （"数月 + 带过"），而用户填"跑 3 天"想的是**出 3 天的稿**。
        #   用 `game_day` 判的话，第 2 天一拍跳完三个月 ⇒ 3 天限制当场触发 ⇒ 只出了 2 天稿，
        #   而界面写着"已跑 91 天"。
        #   ⚠ 关掉新口径（`DAY_ENDS_ON_BEAT_BUDGET=false`）时两者相等，这条改动不影响旧行为。
        # [EN] AUTO_RUN_DAYS check -- **by writing days**, not `world.game_day`. The two "days" are
        # [EN] separate now (see `_advance_writing_day`): a story day can jump 90 at once for
        # [EN] "months + in passing", while the user filling in "run 3 days" means **3 drafts**.
        # [EN] Judging by `game_day` would fire the limit on day 2 when a beat jumps three months,
        # [EN] producing 2 drafts while the UI says "91 days run". ⚠ Under the legacy rule the two
        # [EN] are equal, so this change does not affect it.
        auto_days = CFG.i("AUTO_RUN_DAYS")
        if auto_days > 0 and int(self._current_day or 0) > auto_days:
            return f"达到设定天数 {auto_days}"

        # 暂停检查（PAUSE_AT_NIGHT）
        # [EN] pause check (PAUSE_AT_NIGHT)
        if CFG.b("PAUSE_AT_NIGHT") and self.world.clock.is_night:
            # ★ 走 pause(reason)：中栏会留下「临时暂停」那一条，**并且**告诉会话层
            #   "这是主循环停的" —— 不报的话界面还写着「运行中」，用户以为它还在演。
            #   ⚠ 这里**刻意不推中栏消息**：入夜是个持续状态，用户点一次「继续」
            #     只放行一拍，下一拍又是夜里、又停 —— 推消息会变成刷屏。
            #     状态条已经说得够清楚（「已暂停 —— 等你点「继续」」）。
            # [EN] ★ go through pause(reason): the middle column will leave that "temporary pause" entry, **and**
            # [EN] tell the session layer
            # [EN] "this is the main loop stopping" —— if not reported the UI still says "running", the user thinks
            # [EN] it's still performing.
            # [EN] ⚠ here **deliberately do not push a middle-column message**: nightfall is a persistent state,
            # [EN] the user clicks "continue" once
            # [EN] Only let one beat through; the next beat it's night again and stops again -- pushing messages
            # [EN] would turn into spam.
            # [EN] The status bar already says it clearly enough ("Paused -- waiting for you to click "Continue"").
            self.pause(f"入夜（{self.world.clock_display()}）—— 按「夜间暂停」设置停一下")
            return None

        # ── ① ★★ 「没事就把时间跳过去」（`SKIP_IDLE_TIME`，2026-10-11）──
        #   放在**所有会花钱的步骤之前**：这一拍一跳过，导演 / 派活 / 决策 /
        #   群聊 / 后台**一个都不跑**（那正是跳过的意义 —— 省下空转的调用）。
        #   判据是"连着几拍空拍"，所以只要有人在说话做事就一次都不会跳。
        # [EN] ── ① ★★ "Skip time when nothing is happening" (`SKIP_IDLE_TIME`, 2026-10-11) ──
        # [EN] Placed **before all steps that cost money**: once this beat is skipped, director / dispatch /
        # [EN] decision /
        # [EN] group chat / background **none of them run** (that is exactly the point of skipping -- saving
        # [EN] idle calls).
        # [EN] The criterion is "several consecutive idle beats", so as long as someone is talking or acting,
        # [EN] it will never skip even once.
        if self._maybe_skip_idle():
            return None

        # ── 导演 tick ──
        # [EN] ── director tick ──
        self._status('directing')
        # 客流与群演：**先让门外有人**，导演和人物才有"外部输入"可用。
        # [EN] Traffic and extras: **first make sure there's someone outside the door**, so the director and
        # [EN] characters have "external input" available.
        await self._sync_crowd(tick_num)
        director_event = await self.director.on_tick()
        # ★★ 导演按 `INTERVENTION_POLICY=pause` 挂起的"待确认介入"：
        #   **弹对话框问作者**（2026-10-11 改）。
        # [EN] ★★ Director's "pending confirmation intervention" suspended by `INTERVENTION_POLICY=pause`:
        # [EN] **Pop up a dialog to ask the author** (changed 2026-10-11).
        #   以前是**裸暂停**：中栏一句「（导演待确认）…」，然后 `self.pause()`。
        #   问题有两个 ——
        #     ① 那三行说明塞在中栏的叙事流里，作者不一定读得到"要干什么"；
        #     ② 主循环自己开的暂停**不经过会话层**（见 `pause()` 的说明），
        #        于是按钮还写着「暂停」、状态条也不说"已暂停"，作者连
        #        「继续」都点不到。用户点名的那套对话框就是为这两条来的。
        # [EN] Previously it was a **bare pause**: a line in the middle column "(director pending
        # [EN] confirmation)...", then `self.pause()`.
        # [EN] There were two problems --
        # [EN] ① Those three lines of explanation were stuffed into the middle column's narrative stream, so
        # [EN] the author might not read "what to do";
        # [EN] ② The pause opened by the main loop itself **does not go through the session layer** (see the
        # [EN] note on `pause()`),
        # [EN] so the button still said "Pause", the status bar didn't say "Paused" either, and the author
        # [EN] couldn't even
        # [EN] click "Continue". The set of dialogs the user specifically named were made for these two
        # [EN] problems.
        _pend = getattr(self.director, "_pending_intervention", None)
        if _pend:
            self._status('idle', words=self._day_words,
                         target=int(getattr(self.world, 'daily_words', 0) or 0),
                         skips=self._skips_today)
            # ★★★ 2026-10-26（用户报的两个问题，改的就是这一段）：
            #
            #   ① 「按道理不应该只有这几个选项，而是 AI 会给出多个不同的方向，
            #      让用户选择，而不是只有接受导演建议或者跳过」
            #   ② 「为何导演的建议每次都是有人敲门把僵局打断」
            #
            #   原来这里硬编码两个选项：accept（"听导演的"，后果写着"有人敲门把僵局打断"）
            #   与 skip。而**方案本身还没生成** —— 它在作者点了"听导演的"之后才由
            #   `_inject_rescue_event()` 现生成。也就是说作者面对的是一个
            #   "要不要接受一个还不存在、但文案写着有人敲门的方案"的选择题。
            #
            #   ⇒ 现在：停滞挂起时导演已经用 `propose_branches('stall')` 出好方向
            #     （`_pending_branches`），这里把每一个方向摆成一个选项，
            #     另加「这次不用」。选项里的「后果」是模型给的那句话，不是硬编码。
            #   ⚠ 拿不到方向（模型失败/空表）就**只给「这次不用」+ 自定义输入** ——
            #     不编造方向，也不退回去显示"有人敲门"。
            # [EN] ★★★ 2026-10-26 (this is exactly the block the user complained about):
            # [EN] (1) "there should be several different directions from the AI, not just accept /
            # [EN] skip"; (2) "why is it always someone knocking". It used to hardcode `accept`
            # [EN] ("follow the director", consequence "someone knocks") and `skip` while **the plan
            # [EN] did not exist yet** -- it was generated after clicking accept. So the author was
            # [EN] choosing whether to accept a plan that had not been written but whose label said
            # [EN] "someone knocks". => Now the director has already produced directions via
            # [EN] `propose_branches('stall')` (`_pending_branches`); each becomes an option, plus
            # [EN] "not this time". ⚠ With no directions (model failed / empty), offer **only**
            # [EN] "not this time" + the custom box -- never invent, never fall back to "someone knocks".
            _dirs = [d for d in (getattr(self.director, '_pending_branches', None) or [])
                     if isinstance(d, dict) and str(d.get('标题') or '').strip()]
            _opts: list[dict] = []
            for i, d in enumerate(_dirs, 1):
                _opts.append({
                    # ⚠ id 必须和导演给的**同一套**：后面按 id 找回被选中的那一条，
                    #   自己另编一套编号会让"选 B2"对不上任何方向。
                    # [EN] The id must match the director's own set: we look the chosen one up by id.
                    'id': str(d.get('id') or f'B{i}'),
                    '标题': str(d.get('标题') or '').strip(),
                    '后果': str(d.get('后果') or '').strip(),
                })
            _opts.append({'id': 'skip', '标题': '这次不用',
                          '后果': '照现在的方向接着演，别再问这件事'})
            ans = await self._ask(
                kind='intervention',
                title='导演想介入',
                why=('剧情停滞太久，导演提了几个能破局的方向 —— 挑一个，'
                     '或者自己写一件要发生的事。'
                     if _dirs else
                     '剧情停滞太久，但这次没提出方向 —— 你可以自己写一件要发生的事，'
                     '或者让它接着演。'),
                options=_opts,
                allow_custom=True,
                brief=str(_pend),
                # ★ 2026-10-26：把"这次有没有提出方向"告诉界面 ——
                #   界面按它选问句（"挑一个" vs "这次没提出来，你自己写"），
                #   而不是拿一句固定文案硬套两种情形。
                # [EN] Tell the UI whether directions were produced this time; it picks the wording
                # [EN] accordingly instead of forcing one sentence onto two different situations.
                data={'n_dirs': len(_dirs)},
            )
            pick = str((ans or {}).get('id') or '')
            written = str((ans or {}).get('custom') or '').strip()
            # 被选中的那个方向（`skip` 或空 ⇒ None）
            _chosen = next((d for d in _dirs
                            if str(d.get('id') or '') == pick), None)
            if written:
                # 作者自己写了一件"要发生的事" ⇒ 最硬：当走向交下去
                # [EN] The author himself wrote "something that is going to happen" ⇒ hardest: yield the direction
                self._branch_custom = written
                self._branch_pending = False
                self._push_narrative(f"（你自己定的）{written}", 0, kind=S.NOTE)
                try:
                    self.db.add_event(f"U{tick_num:04d}", f"（作者定）{written}",
                                      "作者介入", self.world.game_day,
                                      self.world.on_stage_names()[:2],
                                      self.world.current_node)
                except Exception:                                # noqa: BLE001
                    pass
                try:
                    # ★ 2026-10-26：方向**交给 `confirm_intervention`** 写进 branch_hint
                    #   （它同时负责重置停滞计时 —— 以前这里只置标志，拍数一点没减，
                    #     于是过 50 拍又来问一遍，正是用户说的"过一会又回到这个循环"）。
                    # [EN] ★ Hand the direction to `confirm_intervention` (it also resets the stall
                    # [EN] counters -- this used to set only a flag, so 50 beats later it asked again).
                    self.director.confirm_intervention(direction=written)
                except Exception:                                # noqa: BLE001
                    pass
            elif _chosen is not None:
                # ★ 2026-10-26 新增：作者挑中了导演提的某个方向。
                #   落点与"岔路口选候选"**完全一致**（写事件流 + branch_hint）——
                #   两处各写一套的话，"挑方向"就只剩屏幕上那句话，对故事毫无影响，
                #   那正是本项目最不想看到的"假功能"。
                # [EN] ★ Added 2026-10-26: the author picked one of the director's directions.
                # [EN] Landing spot is **identical** to "picking a candidate at a fork" (write the
                # [EN] event stream + branch_hint) -- separate implementations would reduce
                # [EN] "picking a direction" to one line on screen, i.e. a fake feature.
                _ttl = str(_chosen.get('标题') or '')
                self._push_narrative(
                    f"（导演介入）你挑了「{_ttl}」"
                    + (f" —— {_chosen.get('后果')}" if _chosen.get('后果') else ""),
                    0, kind=S.NOTE)
                try:
                    self.db.add_event(f"B{tick_num:04d}", f"（走向）{_ttl}",
                                      "走向选择", self.world.game_day,
                                      self.world.on_stage_names()[:2],
                                      self.world.current_node)
                except Exception:                                # noqa: BLE001
                    pass
                self._branch_hint = _ttl
                self._branch_custom = ""
                try:
                    self.director.confirm_intervention(direction=_ttl)
                except Exception:                                # noqa: BLE001
                    pass
            elif pick == 'skip':
                self._push_narrative("（导演介入）这次不用 —— 照现在的方向接着演。",
                                     0, kind=S.NOTE)
                try:
                    self.director.skip_intervention()
                except Exception:                                # noqa: BLE001
                    pass
            else:
                # 到点 / 无界面：**退回老行为**（点「继续」= 按导演的方案）。
                # ⚠ 不能什么都不做就往下走 —— `_pending_intervention` 还在，
                #   下一拍又会挂起，变成原地打转。
                # [EN] Timeout / no UI: **fall back to old behavior** (clicking "Continue" = follow the director's
                # [EN] plan).
                # [EN] ⚠ Cannot just do nothing and move on -- `_pending_intervention` is still there,
                # [EN] and the next beat will suspend again, turning into spinning in place.
                _LOG.info("导演介入没人回答（到点或无界面），按老行为继续")
                try:
                    self.director.confirm_intervention()
                except Exception:                                # noqa: BLE001
                    pass
        if director_event:
            self._push_narrative(
                f"【{director_event.event_type}】{director_event.description}", 0,
                kind=S.EVENT)
            if self._script_mode:
                self._ensure_builder().observe_event(director_event)
            if self._on_event:
                self._on_event(director_event)

        # ── 岔路口：要不要让用户挑一个走向 ──
        # 放在派活之前：走向定了，派活才派得对（否则派的是"旧方向"的活）。
        # [EN] ── fork in the road: should the user pick a direction ──
        # [EN] Placed before dispatch: once the direction is set, dispatch can dispatch correctly (otherwise it
        # [EN] dispatches work for the "old direction").
        try:
            await self._maybe_branch(tick_num)
        except Exception as e:                                  # noqa: BLE001
            self._warn_once('branch_tick', f"岔路口处理失败（不影响推演）：{e!r}")

        # ── 导演派活（`DISPATCH_EVERY_TICKS`）──
        # 放在**决策之前**：派活是目标金字塔最内层（〔此刻〕）的来源，
        # 这一拍人物读到的 prompt 就该带上它。
        # [EN] ── director dispatch (`DISPATCH_EVERY_TICKS`) ──
        # [EN] Placed **before decision**: dispatch is the source of the innermost layer of the goal pyramid
        # [EN] (〔this moment〕),
        # [EN] and the prompt the character reads this beat should already include it.
        await self._maybe_dispatch(tick_num)

        # ── ★★★ 导演给**这一拍**定品级（2026-10-18）──
        #   必须放在**决策之前**：14 个职位的提示词里那一段手艺条目是按
        #   （时机 × 品级）挑的（`craft/dispatch.pick`），品级晚一步算，
        #   这一拍读到的就还是上一拍的档 —— 等于没接上。
        #   ⚠ 零成本（纯规则，不调模型）⇒ 每拍都算得起。
        #   ⚠ 失败**不许影响推演**：沿用上一拍的值（默认 `日常`/`中`），
        #     最坏只是"这一拍多读或少读两条手艺"。
        # [EN] ── ★★★ The director grades **this beat** (2026-10-18) ──
        # [EN] It must run **before decisions**: the craft entries in 14 roles' prompts are chosen by
        # [EN] (moment x grade) via `craft/dispatch.pick`; grading one step late means this beat still
        # [EN] reads the previous beat's grade. ⚠ Zero cost (pure rules) so it can run every beat.
        # [EN] ⚠ Failure must not affect the run: keep the previous values (default 日常/中); worst
        # [EN] case is "two entries more or less this beat".
        self._grade_beat()

        # ── 前台步进（并发限流）────
        # 时段/地点变了就分幕（分幕点决定屏幕上「场景」行的位置）
        # ⚠ 分幕**之前**先把上一幕的口径记下来：`_maybe_break_scene()` 内部
        #   会把 `_last_place` 覆盖成**新**地点，等它返回后再读就是新地点了
        #   —— 幕终分隔符会标错地方（原来就是这么写的），镜头卡也会跟着错。
        # [EN] ── foreground stepping (concurrency throttling) ────
        # [EN] When the time slot/location changes, break the scene (the scene break point determines the
        # [EN] position of the "scene" line on screen)
        # [EN] ⚠ Before breaking the scene, first record the previous scene's state: inside
        # [EN] `_maybe_break_scene()`
        # [EN] `_last_place` will be overwritten with the **new** location; reading it after it returns gives
        # [EN] the new location
        # [EN] -- the scene-end separator would be marked in the wrong place (that's how it was originally
        # [EN] written), and the camera card would be wrong too.
        _prev_place = self._last_place
        _prev_seg = self._clock_segment()
        if self._maybe_break_scene():
            # **上一幕到此结束** —— 用户要的「一个场景结束给一个明显的分隔符」
            # [EN] **The previous scene ends here** -- the user's request: "when a scene ends, give an obvious
            # [EN] separator"
            self._push_divider(D.scene_end(_prev_seg, _prev_place))
            self._emit_film_card(place=_prev_place)
            # ★ 小地图重画（2026-10-06）：**新**地点才是"我现在在哪"。
            #   注意用 `self._last_place`（`_maybe_break_scene` 里刚更新成新地点），
            #   不是 `_prev_place`（那是上一幕的）—— 这两个搞反过一次，见分幕那段注释。
            # [EN] ★ Minimap redraw (2026-10-06): the **new** location is "where I am now".
            # [EN] Note to use `self._last_place` (`_maybe_break_scene` just updated it to the new location),
            # [EN] not `_prev_place` (that's the previous scene's) -- these two were once swapped, see the note in
            # [EN] the scene-breaking section.
            self._push_scene(place=self._last_place, segment=self._clock_segment())
        self._tick_no = tick_num
        # ★ 「在场」= **就在这场戏里的人**（`world.is_on_stage`：在场 + 前台 + 地点对得上）。
        #   以前这里是 `a.ps.is_active()`，只看 `status` + `role`（`role` 是装配时定死的）
        #   —— 于是"在场人物"永远是同一份前台名册（真机日志 126 次一模一样，
        #   连终局才登场的角色都在场）。
        # [EN] ★ "On stage" = **the people in this scene right now** (`world.is_on_stage`: on stage +
        # [EN] foreground + location matches).
        # [EN] Previously this was `a.ps.is_active()`, which only looked at `status` + `role` (`role` is fixed
        # [EN] at assembly time)
        # [EN] -- so "on-stage characters" were always the same foreground roster (126 identical entries in the
        # [EN] real machine log,
        # [EN] even characters who only appear at the finale were on stage).
        on_stage = [a for a in self.agents if self.world.is_on_stage(a.ps)]
        if on_stage:
            # ★★ 挑人（2026-10-07 改）——**"该接话的人"优先**。
            # [EN] ★★ Picking people (changed 2026-10-07) -- **"the person who should respond" takes priority**.
            # 用户报：「所有人说话都给我一种一直在自说自话的感觉……正常应该是
            # 有一个事情大家都对这个事情进行讨论，互相针对别人说的话回应」。
            # 原来这里是 `random.sample(on_stage, min(2, len(on_stage)))` ——
            # 纯随机。于是"阿枝问主角"之后，主角可能好几拍才被抽中，
            # 那时插进来三四件别的事，看起来就是各说各的。
            # [EN] User reported: "When everyone talks, it gives me the feeling that they're always talking to
            # [EN] themselves... normally it should be
            # [EN] that there's a topic and everyone discusses it, responding to what others said".
            # [EN] Previously this was `random.sample(on_stage, min(2, len(on_stage)))` --
            # [EN] purely random. So after "A Zhi asks Shen Yan", Shen Yan might only be picked several beats
            # [EN] later,
            # [EN] and by then three or four other things have been inserted, so it looks like everyone is talking
            # [EN] about their own thing.
            # 现在：**先挑刚被点名的人**（`_reply_candidates`），再随便补一个。
            # 这不会让对话变"整齐"，只是让"被问到的人"有优先答话的机会 ——
            # 有来有回，才有对话。
            # [EN] Now: **first pick the person just called on** (`_reply_candidates`), then randomly fill in one
            # [EN] more.
            # [EN] This won't make the dialogue "tidy", it just gives "the person asked" a chance to answer first
            # [EN] --
            # [EN] only with back-and-forth is there dialogue.
            lead: Agent | None = None
            selected: list[Agent] = []
            candidates = self._reply_candidates(on_stage)
            # ★★★ 2026-10-18：**欠一句的人必须占满名额**，不是"挑一个当领说"。
            #   用户原话：「一个人说的话 另外一个人不去接 两个人各说各话的现象到处存在…
            #   中间应该有协调者 特别是导演 应该消除这种自说自话的问题」。
            #   旧写法只挑**一个**（`_rng.choice`），然后**随机补一个人** ——
            #   被补进来的那位没有人跟他说话，他只能自己开一个话题，
            #   于是每拍都有一个"新话题"（实测雪国接话率 0.27，三个话题并行）。
            #   ⇒ 有人在等回答时，**这一拍的坑位先给他**；还有空位才随机补。
            #   ⚠ 名额只有 2 个：欠答的人先占，最多占满；这样"自说自话"的位子就没有了。
            # [EN] ★★★ 2026-10-18: **the people who owe an answer take the slots**, not "one of them
            # [EN] becomes the lead". The old version picked **one** (`_rng.choice`) and then filled
            # [EN] the rest **randomly** -- the filler had nobody addressing him, so he could only
            # [EN] open a topic of his own, and every beat got a fresh topic (measured: 0.27 reply
            # [EN] rate, three parallel topics). => when someone is owed an answer, he takes the
            # [EN] slot first; only leftover slots are filled randomly. With two slots, the
            # [EN] "talking to himself" seat simply does not exist.
            slots = max(1, min(2, len(on_stage)))
            if candidates:
                # 顺序也要稳：先按在场顺序（人多的场合不摇骰子，可复现）
                # [EN] Keep the order stable: in-stage order (no dice when there are many, so it
                # [EN] reproduces).
                ordered = [a for a in on_stage if a in candidates]
                selected += ordered[:slots]
            pool = [a for a in on_stage if a not in selected]
            need = slots - len(selected)
            if need > 0 and pool:
                selected += random.sample(pool, min(need, len(pool)))
            lead = selected[0] if selected else None
            self._status('deciding', n=len(selected))
            # ★ 这一拍的重说预算（见 `_review_repeat`）：人物说了已说过的话时，
            #   会先让他"重新想清楚、换一句"。重说要**多花一次调用**，
            #   所以每拍有上限（`DIALOGUE_RETRY_MAX`），用完就退回老行为。
            # [EN] ★ This beat's repeat budget (see `_review_repeat`): when a character says something already
            # [EN] said,
            # [EN] he is first made to "think it through again and use a different line". Repeat review **costs one
            # [EN] extra call**,
            # [EN] so each beat has a cap (`DIALOGUE_RETRY_MAX`), and once used up it falls back to old behavior.
            try:
                self._retry_left = CFG.i('DIALOGUE_RETRY_MAX')
            except Exception:                                    # noqa: BLE001
                self._retry_left = 2
            # ★ 台词自省的预算（见 `_self_review_budget` / `_self_review`）：与重说
            #   **分开记**（理由见 `__init__` 里那段）。关掉总闸 / 关掉自省时是 0 ——
            #   那一档就一次都不会走。
            # [EN] ★ Line self-reflection budget (see `_self_review_budget` / `_self_review`): recorded
            # [EN] **separately** from repeat
            # [EN] review (reason in the paragraph in `__init__`). When the main switch / self-reflection is off it
            # [EN] is 0 --
            # [EN] so that tier will never run even once.
            self._review_left = _self_review_budget()
            # ★ 决策（2026-10-07 改）：**领说者先单独说完，其余人再动**。
            # [EN] ★ Decision (changed 2026-10-07): **the lead speaker finishes alone first, then the others
            # [EN] move**.
            # 原来全部 `gather` 并行（2026-10-06 改的，为省时间）—— 但那样
            # 同一拍的两个人**互相看不见对方要说什么**，于是屏幕上出现
            # "两个人各说一句不相干的话"。这一条正是"割裂感"的另一半来源。
            # [EN] Previously all were `gather`ed in parallel (changed 2026-10-06, to save time) -- but that way
            # [EN] two people in the same beat **cannot see what the other is about to say**, so on screen you get
            # [EN] "two people each saying one unrelated line". This is exactly the other half of the source of the
            # [EN] "sense of fragmentation".
            # 折中：只在**有人被点名**（也就是对话正在发生）时才分两步走 ——
            # 领说者先决策并**立刻记进 `[刚才]`**，其余人再并行决策（他们就读得到）。
            # 没人被点名时保持全并行：那种场合本来就不是对话，
            # 没有理由为它付"串行"的时间。
            # [EN] Compromise: only when **someone is called on** (that is, a dialogue is happening) does it split
            # [EN] into two steps --
            # [EN] the lead speaker decides first and **immediately records it into `[just now]`**, then the others
            # [EN] decide in parallel (they can read it).
            # [EN] When no one is called on, keep full parallelism: that kind of occasion is not a dialogue anyway,
            # [EN] and there's no reason to pay the "serial" time cost for it.
            # `return_exceptions=True`：一个人出错不该拖垮这一拍 ——
            # 把异常就地降级成 wait，并留一条日志。
            # [EN] `return_exceptions=True`: one person erroring should not drag down this beat --
            # [EN] degrade the exception in place to wait, and leave a log line.
            actions: list[tuple[Agent, Action]] = []
            if lead is not None:
                try:
                    act = await lead.decide()
                except Exception as e:                          # noqa: BLE001
                    _LOG.warning("「%s」决策抛异常，降级为 wait：%r", lead.name, e)
                    act = Action(verb="wait", reason=f"（决策异常：{e}）")
                # ★★ **台词自省**（反思链，2026-10-07 第七轮）：这一句明显不像
                #   人在场上说的（书面连接词 / 情绪直说 / 长得像作文）时，
                #   让他在说出口之前再审一遍自己这句 —— 可以改，也可以坚持原话。
                #   ⚠ 排在 `_review_repeat` **之前**：先修"这句像不像人话"，
                #     再修"这句是不是说过"（前者改完可能就不再重复了）。
                # [EN] ★★ **Line self-reflection** (reflection chain, 2026-10-07 seventh round): when this line clearly
                # [EN] does not sound like
                # [EN] something a person would say on stage (written connectives / directly stating emotions / reads
                # [EN] like an essay),
                # [EN] have him review his own line again before speaking it -- he can change it, or stick with the
                # [EN] original.
                # [EN] ⚠ Placed **before** `_review_repeat`: first fix "does this line sound human",
                # [EN] then fix "has this line been said" (the former may already remove the repetition).
                act = await self._self_review(lead, act)
                # ★ 他说的是不是已经说过的话？——**在他开口之前**问清楚
                #   （2026-10-07）。这一步是**内部盘算**：`decide()` 不写库、
                #   不推屏幕、不记缓冲，所以第一遍那句话在人开口之前就被丢掉了，
                #   外面（别的角色、观众）只看得见最终那一句。
                # [EN] ★ Is what he's saying something already said? -- **ask clearly before he speaks**
                # [EN] (2026-10-07). This step is **internal deliberation**: `decide()` writes no DB,
                # [EN] doesn't push to screen, doesn't log to buffer, so that first-pass line is discarded before the
                # [EN] person speaks,
                # [EN] the outside (other characters, the audience) only sees the final line.
                act = await self._review_repeat(lead, act)
                actions.append((lead, act))
                # ⚠ 这里就记进缓冲（**不是**等 `_process_actions`）：
                #   其余人的提示词要在**这一刻**读得到他刚说的话。
                #   `note_line` 自带相邻去重，所以下面统一记那次不会记成两遍。
                #   ⚠ 必须在 `_review_repeat` **之后** —— 记的要是他最终说的那句。
                # [EN] ⚠ This is where it gets logged into the buffer (**not** waiting for `_process_actions`):
                # [EN] everyone else's prompt needs to see what he just said **at this moment**.
                # [EN] `note_line` has built-in adjacent dedup, so logging it uniformly below won't log it twice.
                # [EN] ⚠ Must be **after** `_review_repeat` -- what gets logged must be the line he finally said.
                self._note_stage_line(lead, act, spoken=True)
            rest = [a for a in selected if a is not lead]
            if rest:
                results = await asyncio.gather(*(a.decide() for a in rest),
                                               return_exceptions=True)
                for agent, res in zip(rest, results):
                    if isinstance(res, BaseException):
                        _LOG.warning("「%s」决策抛异常，降级为 wait：%r",
                                     agent.name, res)
                        res = Action(verb="wait", reason=f"（决策异常：{res}）")
                    # 同前：先审"这句像不像人话"，再问清"是不是非说不可"。
                    # [EN] Same as before: first review "does this sound like human speech", then clarify "is it really
                    # [EN] necessary to say it".
                    res = await self._self_review(agent, res)
                    res = await self._review_repeat(agent, res)
                    actions.append((agent, res))
            # 顺序：领说者**在前**（他的话先落地，叙事顺序才与因果一致）
            # **整组交出去**：同时性只有在拿到一个 tick 的全部动作时才看得出来。
            # 以前是逐个 append 成字符串，于是"同时"被写成了"先后"。
            # [EN] Order: the proposer is **first** (his words land first, so narrative order matches causality)
            # [EN] **Hand the whole group over**: simultaneity is only visible when you have all the actions of one
            # [EN] tick.
            # [EN] Previously it was appended one by one into a string, so "simultaneous" got written as
            # [EN] "sequential".
            # ★★ **把这一拍发生的记进本场戏的账**（2026-10-11）——
            #   用**动作本身**记，不用"跑了几拍"：全场发呆也在烧 tick，
            #   但那不该算"这场戏演过了"（见 `StagePlan.done_reason`）。
            # [EN] ★★ **Record what happened this beat into the current scene's ledger** (2026-10-11) --
            # [EN] recorded from **the actions themselves**, not from "how many ticks ran": the whole cast
            # [EN] spacing out still burns ticks, but that should not count as "this scene was performed"
            # [EN] (see `StagePlan.done_reason`).
            self._stage_observe(actions)
            await self._process_actions(actions)
            # ★ **上下文主动压缩要讲给作者听**（2026-10-10，用户点名要"提示我"）。
            #   Agent 自己没有向界面说话的路子（它不持有叙事通道），
            #   所以 `_compact_if_needed` 把说明记在 `agent.last_compaction` 上，
            #   在这里收口播报 —— 一处，不是每个人各写一遍。
            # [EN] ★ **Context auto-compaction must be told to the author** (2026-10-10, user explicitly asked to
            # [EN] "notify me").
            # [EN] The Agent itself has no way to speak to the UI (it doesn't hold the narrative channel),
            # [EN] so `_compact_if_needed` records the explanation on `agent.last_compaction`,
            # [EN] and the announcement is consolidated here -- one place, not each person writing it once.
            self._announce_compaction(actions)
            # ★★ **这一场戏演完了没有**（2026-10-11）—— 演完就收场、换地方、进下一拍。
            #   放在这一拍的播报**都做完之后**：收场自己要推分隔符与幕首，
            #   顺序反了会让作者先看到"第 2 拍开始"再看到"第 1 拍结束"。
            # [EN] ★★ **Is this scene finished** (2026-10-11) -- if so, wrap up, change place, move on.
            # [EN] Placed **after** this beat's announcements: wrapping up pushes a separator and an act
            # [EN] header, and reversing the order would show the author "beat 2 begins" before
            # [EN] "beat 1 ends".
            self._maybe_close_beat()
            # 戏份账：上了台的人记一笔（后台降格队列按「戏份权重 × 最近出场」排）
            # [EN] Screen-time ledger: anyone who went on stage gets a mark (the backstage demotion queue sorts by
            # [EN] "screen-time weight x most recent appearance")
            for agent, _act in actions:
                self._backstage.note_on_screen(agent.name)
            # 「被点到名」的人要从后台拉上台 —— 剧情点名比地点匹配更该优先。
            # `mentioned` 从这一拍的动作文本里取（台词/目标里出现的**在场人物之外**的名字）。
            # [EN] Those "called by name" must be pulled from backstage to the stage -- plot roll-call should take
            # [EN] priority over location matching.
            # [EN] `mentioned` is taken from this beat's action text (names appearing in lines/goals that are
            # [EN] **outside the on-scene characters**).
            self._pending_mention = self._mentioned_names(actions)

        # ── 群聊轮转（`GROUP_CHAT_MAX`，设计稿 §五「3 人及以上同场」）──
        #   放在前台步进之后：这一拍该做的动作先做完，再让多出来的人插一句。
        # [EN] ── Group chat rotation (`GROUP_CHAT_MAX`, design doc §5 "3 or more present together") ──
        # [EN] Placed after the foreground step: finish this beat's actions first, then let the extra people
        # [EN] interject a line.
        try:
            await self._maybe_group_chat()
        except Exception as e:                                  # noqa: BLE001
            self._warn_once('group_chat', f"群聊轮转失败（不影响推演）：{e!r}")

        # ── 后台批次（`BACKGROUND_MODE` / `BACKGROUND_TICK_MINUTES`）──
        # 顺序照设计稿：前台步进 → **后台批次** → 边界看守。
        # [EN] ── Background batch (`BACKGROUND_MODE` / `BACKGROUND_TICK_MINUTES`) ──
        # [EN] Order per design doc: foreground step → **background batch** → boundary guard.
        await self._run_backstage()

        # ══════════════════════════════════════════════════════════════
        # **状态停滞检测**（2026-10-20，`director/stall.py`）
        # ══════════════════════════════════════════════════════════════
        # ★★★ 位置在这里不是随手的：它必须在**这一拍的所有动作都落完**
        #   （前台步进 / 群聊 / 后台批次）之后、进度评估之前 ——
        #   早了会拿"还没走完的状态"去算指纹，晚了就没机会影响这一拍的收尾。
        #
        #   为什么需要它（三次失败的测量记在 `director/stall.py` 顶部）：
        #   句子层、派活文本层都分不开"有意复现"与"卡住"。换到世界状态层就分开了 ——
        #   四样（空间 / 在场人 / 手上事 / 话题）全同，与措辞无关，下一拍必然重复。
        #
        #   三档处置：`vary` 在 `director.engine._inject_event` 里（换事件类型），
        #   `shift` 在这里写 `watch_note`（下一拍必须有人进出），
        #   `settle` 交给已有的僵局结算通道（`STALL_BREAK_BEATS` 那条）。
        # ⚠ 整段包在 try 里：它是**观察器**，任何失败都不许影响推演。
        # [EN] Stall detection. Positioned after everything this beat did and before progress
        # [EN] assessment. Tiers: `vary` lives in `_inject_event`, `shift` writes `watch_note`
        # [EN] here, `settle` reuses the existing deadlock-settlement channel.
        try:
            from director import stall as _STALL
            _n, _lvl = _STALL.note_and_hint(self.world)
            if _lvl:
                _LOG.info('状态停滞（连续 %d 拍）：%s', _n, _STALL.why(_n))
            if _lvl == 'settle':
                # 超出一整场戏还是什么都没变 ⇒ 走**已有的**结算通道，
                # 不新造机制（新造的东西没人维护）。
                try:
                    # ⚠ 必须传**连拍数**：`request_settle(beats)` 的语义是
                    #   "下一拍走结算通道，理由是一场僵局已经持续了 beats 拍"。
                    #   第一版漏了参数 —— 而 `int(None)` 会在函数里被兜成 0，
                    #   于是 `n > 0` 不成立 ⇒ **静默什么都不做**，
                    #   界面上看不出任何异常（这类"兜底把错误吃掉"的坑本项目踩过多次）。
                    self.director.request_settle(_n)
                except Exception as _e:                          # noqa: BLE001
                    _LOG.debug('僵局结算请求失败（不影响推演）：%r', _e)
        except Exception as _e:                                  # noqa: BLE001
            _LOG.debug('状态停滞检测失败（不影响推演）：%r', _e)

        # ── 导演进度评估 ──
        # [EN] ── Director progress assessment ──
        if await self._check_progress():
            return "到达故事终点"

        # ── 边界看守 ──
        # [EN] ── Boundary guard ──
        run_mode = CFG.s("RUN_MODE")

        # story 模式：到达终点自动收尾
        # [EN] story mode: automatically wrap up upon reaching the end
        if run_mode == "story" and self.director.is_at_end():
            all_done = all(nd.get("状态") == "已完成" for nd in self.world.progress_nodes)
            if all_done:
                return "story 模式终点完成"

        # open 模式：不限期限，但每 N 天打一次存档点（`OPEN_CHECKPOINT_EVERY_DAYS`）
        # ⚠ 以前这个旋钮零读取 —— "不限期限一直续写"会连着跑几天不落盘，
        #   中途断电就丢一整段。停一下的意义是**存档点**，不是限制长度。
        # [EN] open mode: no time limit, but write a checkpoint every N days (`OPEN_CHECKPOINT_EVERY_DAYS`)
        # [EN] ⚠ This knob was previously read zero times -- "keep writing indefinitely with no time limit"
        # [EN] would run for days without saving,
        # [EN] a mid-run power outage would lose a whole stretch. The point of stopping is a **checkpoint**,
        # [EN] not limiting length.
        # ★★ 2026-10-11：**默认不再停下来等确认**（见 `CHECKPOINT_PAUSE`）。
        #    存档点回答的是"我存了没有"，**不需要作者做任何决定** ——
        #    那就不该打断推演。作者的原话是「1.尽可能想办法不要让用户干预」，
        #    以及「这个时候实在推演中的 我没点暂停」——
        #    那次就是日界检查点自己停住、而他根本没想停。
        # [EN] ★★ 2026-10-11: **no longer stops by default to wait for confirmation** (see `CHECKPOINT_PAUSE`).
        # [EN] A checkpoint answers "did I save" -- **requires no decision from the author** --
        # [EN] so it shouldn't interrupt the simulation. The author's exact words were "1. try as much as
        # [EN] possible not to require user intervention",
        # [EN] and "this is right in the middle of the simulation, I didn't click pause" --
        # [EN] that time the day-boundary checkpoint just stopped by itself, and he had no intention of
        # [EN] stopping.
        elif run_mode == "open":
            if self._open_checkpoint_due():
                every_days = CFG.i("OPEN_CHECKPOINT_EVERY_DAYS")
                self._last_open_ckpt = self.world.game_day
                _LOG.info("open 模式：第 %d 天存档点（每 %d 天）",
                          self.world.game_day, every_days)
                if not CFG.b("CHECKPOINT_PAUSE"):
                    # 只落盘 + 说一句，接着演
                    # [EN] Just save + say one line, then keep going
                    self._push_narrative(
                        f"（第 {self.world.game_day} 天 —— 已按设置存档"
                        f"（每 {every_days} 天一次），接着往下写。）", 0, kind=S.NOTE)
                else:
                    await self._ask_checkpoint(every_days)
                    if self._paused:
                        return None

        # story_day 模式：按进度表推演，但每隔 N 天打一次存档点
        # [EN] story_day mode: simulate per the progress table, but write a checkpoint every N days
        elif run_mode == "story_day":
            # 检查是否到达终点
            # [EN] Check whether the end has been reached
            if self.director.is_at_end():
                all_done = all(nd.get("状态") == "已完成" for nd in self.world.progress_nodes)
                if all_done:
                    return "story_day 模式终点完成"

            # 检查是否需要打存档点
            # [EN] Check whether a checkpoint needs to be written
            every_days = CFG.i("STORY_DAY_EVERY_DAYS")
            if every_days > 0 and self.world.game_day % every_days == 0:
                # 避免重复记账（只在进入新的一天时记一次）
                # [EN] Avoid double-accounting (only record once when entering a new day)
                if self._last_story_day_pause != self.world.game_day:
                    self._last_story_day_pause = self.world.game_day
                    _LOG.info("story_day 模式：第 %d 天存档点（每 %d 天一次）", 
                             self.world.game_day, every_days)
                    if not CFG.b("CHECKPOINT_PAUSE"):
                        # ★★ 默认这条路：**不打断**。
                        # [EN] ★★ Default path: **no interruption**.
                        # 2026-10-10 真机事故的现场就是这里 —— 它 `pause()` 了一下，
                        # 于是作者看到的是一条凭空冒出来的「临时暂停」，而状态条
                        # 还写着「正在核对故事进度 · 已 2019 秒」（那 33 分钟里
                        # **0 次 LLM 调用**，只是没人点「继续」）。
                        # 修完"暂停要通知界面"之后它不再是"卡住"了，
                        # 但**还是多了一次毫无必要的打断** —— 这一版把它去掉：
                        # 落盘照做，话说一句，戏接着演。
                        # [EN] The scene of the 2026-10-10 real-machine incident is right here -- it called `pause()`,
                        # [EN] so what the author saw was an out-of-nowhere "temporary pause", while the status bar
                        # [EN] still said "verifying story progress · 2019 seconds elapsed" (in those 33 minutes)
                        # [EN] **0 LLM calls**, just nobody clicked "continue").
                        # [EN] After fixing "pause must notify the UI" it's no longer "stuck",
                        # [EN] but it **still was one unnecessary interruption** -- this version removes it:
                        # [EN] save as usual, say a line, keep going.
                        self._push_narrative(
                            f"（第 {self.world.game_day} 天 —— 已按设置存档"
                            f"（每 {every_days} 天一次），接着往下写。）",
                            0, kind=S.NOTE)
                    else:
                        # 作者明确要"停下等确认"（`CHECKPOINT_PAUSE=true`）
                        # → 走提问对话框，而不是裸暂停
                        # [EN] The author explicitly wants "stop and wait for confirmation" (`CHECKPOINT_PAUSE=true`)
                        # [EN] → go through the question dialog, not a bare pause
                        await self._ask_checkpoint(every_days)
                        if self._paused:
                            return None  # 暂停但不结束
                            # [EN] Pause but don't end

        # ★ 导演提示**只活一拍**：这一拍的人已经决策完了（上面 `_process_actions`
        #   之前就决策过），所以到这里它已经完成使命 —— 清掉，
        #   交给下面的盯戏决定要不要设一条**新的**。
        # [EN] ★ The director hint **only lives for one beat**: this beat's people have already finished
        # [EN] deciding (decided earlier
        # [EN] before `_process_actions` above), so by now it has fulfilled its mission -- clear it,
        # [EN] and hand off to the watch below to decide whether to set a **new** one.
        try:
            self.world.watch_note = ''
        except Exception:                                        # noqa: BLE001
            pass

        # ── 落盘 ──
        # ★ 导演盯戏（2026-10-07）：**排在落盘之前** —— 回档要真的生效，
        #   就不能等这一拍已经写进文件之后再删（那样文件和屏幕会对不上）。
        # [EN] ── Save to disk ──
        # [EN] ★ Director watch (2026-10-07): **placed before saving** -- for rollback to truly take effect,
        # [EN] you can't wait until this beat has already been written to the file and then delete it (that way
        # [EN] file and screen would disagree).
        await self._director_watch()
        # ★ **剧本审读的跨拍观察**（2026-10-08）：「进了场却没人搭上话的人」
        #   → 下一拍的决策提示词里会带一句"谁在场谁接住他"。
        #   放在 `_director_watch` **之后**是有意的：它是**追加**（不覆盖导演
        #   刚设那条提示），两条提示可以同时存在于下一拍。
        # [EN] ★ **Script review's cross-beat observation** (2026-10-08): "people who entered the scene but
        # [EN] nobody connected with"
        # [EN] → next beat's decision prompt will carry a line "whoever's present, catch him".
        # [EN] Placing this **after** `_director_watch` is intentional: it is **appended** (doesn't overwrite
        # [EN] what the director
        # [EN] just set), so both hints can coexist in the next beat.
        self._note_idle_newcomers()
        # ★ 预算耗尽：**问作者一句**（2026-10-11 从"裸暂停"改过来）。
        #   放在落盘之前：真收工的话，`_flush_tick` 那一拍的内容也要落下去。
        # [EN] ★ Budget exhausted: **ask the author once** (changed from "bare pause" on 2026-10-11).
        # [EN] Placed before saving: if actually wrapping up, the content of that `_flush_tick` beat must also
        # [EN] be saved.
        _budget_reason = await self._maybe_ask_budget()
        if _budget_reason:
            return _budget_reason
        self._flush_tick(tick_num)
        self._status('idle', words=self._day_words,
                     target=int(getattr(self.world, 'daily_words', 0) or 0),
                     skips=self._skips_today)

        return None

    # ── 剧本式输出 ──────────────────────────────────────────────────
    # [EN] ── Scripted output ──────────────────────────────────────────────────
    @property
    def _script_mode(self) -> bool:
        return (CFG.s('OUTPUT_FORMAT') or 'script').strip().lower() == 'script'

    def _ensure_builder(self) -> SceneBuilder:
        if self._builder is None:
            # ★ 续跑：这一天的**前半截**先放进幕列表（只在这一天第一幕用一次）。
            #   不给的话收工落盘会**整个覆盖**上一轮那份半截稿。
            # [EN] ★ Resume run: this day's **first half** goes into the act list first (used only once, for that
            # [EN] day's first act).
            # [EN] Without it, wrapping up and saving would **completely overwrite** the previous round's
            # [EN] half-finished draft.
            seed = self._resume_scenes
            self._resume_scenes = []
            self._builder = SceneBuilder(self.world, day=self._current_day,
                                         image_hook=self.image_hook,
                                         initial_scenes=seed)
            # 新的一天的第一幕：把当前时段/地点记下来，供后面的分幕比较
            # [EN] First act of a new day: record the current time slot/location, for later act comparison
            self._last_clock = getattr(self.world, 'clock', None)
            self._last_place = (getattr(self.world, 'scene', '') or '').strip()
        return self._builder

    def _maybe_break_scene(self) -> bool:
        """时段或地点变了 → 分幕。返回 True 表示**刚刚分过幕**。

        分幕意味着"上一幕结束了" —— 调用方据此推一条「幕终」分隔符。
        
                English:
        Time period or location changed -> scene break. Returns True meaning **a scene break just
        happened**.
                A scene break means "the previous scene ended" -- the caller uses this to push a "scene end" separator.
        """
        if not self._script_mode or self._builder is None:
            return False
        place = (getattr(self.world, 'scene', '') or '').strip()
        if self._builder.maybe_break(prev_clock=self._last_clock,
                                     prev_place=self._last_place):
            # ★★★ 2026-10-18：**上一场的余波**（专业论述 #7，Swain: scene → sequel）。
            #   在本场"关掉"之前把它记下来 —— 关掉之后 `recent_lines` 就清空了，
            #   那时再想"上一场最后发生了什么"就只能靠模型回忆（会歪）。
            # [EN] ★★★ 2026-10-18: **the previous scene's aftermath** (#7, Swain: scene -> sequel).
            # [EN] Recorded before this scene is closed -- after closing, `recent_lines` is cleared and
            # [EN] "what happened at the end" can only be recalled by a model (and it drifts).
            self._note_aftermath()
            # ⚠ 先把**旧的地点**留给分隔符用（下面马上就覆盖了）
            # [EN] ⚠ First leave the **old location** for the separator to use (it gets overwritten right below)
            self._last_clock = getattr(self.world, 'clock', None)
            self._last_place = place
            return True
        return False

    def _note_aftermath(self) -> None:
        """把**这一场留下的东西**记进 `world.aftermath`（Swain 的 sequel 三拍）。

        ★★★ 2026-10-18 用户：「生成的小说… 过于追求故事推进… 不像正常人写的小说」，
          以及评委反复说的"戏没有落点 / 停住"。根因是**变化之后没有一个位置承载
          "他态度怎么变、下一步为什么改主意"** —— 每拍只有"要有一处变化"。

        Swain 的 sequel 有三拍：**反应**（先被打懵）→ **困境**（路都不好走）→
        **决定**（挑了一条，下一个场景的目标从这里长出来）。

        这里只算前两拍，**决定故意留空**：
          · `反应` = 本场最后一条动作/台词的原样引文（**事实**，不是概括）；
          · `困境` = 还欠着一句的人 / 悬着的那件事（也是事实）；
          · `决定` = 空 —— 由**下一场第一拍**自己长出来。
        ⚠ 为什么不去调模型"总结他决定了什么"：一是钱（每场一次也不便宜），
          二是**编出来的决定会被下一场当既定事实**（那比没有更糟）。
          正确的做法是把它写成"他还没拿定主意"，让戏自己走。
        ⚠ 算不出来（这一场没东西）⇒ **不留**（不编）。空 aftermath 是常态。
        [EN] Record what this scene left behind into `world.aftermath` (#7 Swain's sequel).
        [EN] Only the first two beats are computed; **the decision is deliberately left empty**:
        [EN] `reaction` is the verbatim last line/action (a fact, not a summary), `dilemma` is who still
        [EN] owes an answer (also a fact), and `decision` is empty -- the next scene's first beat grows it.
        [EN] ⚠ Why not ask a model "what did he decide": it costs money, and an invented decision would be
        [EN] treated as established fact next scene (worse than nothing). ⚠ Nothing to record => record
        [EN] nothing; an empty aftermath is normal.
        """
        try:
            w = self.world
            lines = list(getattr(w, 'recent_lines', None) or [])
            reaction = ''
            for r in reversed(lines):
                txt = str((r or {}).get('text') or '').strip()
                if txt and len(txt) >= 4:
                    reaction = txt[:60]
                    break
            # ★★★ 兜底：换场时 `recent_lines` **已经被清空**（`_apply_stage_move` 先清再换），
            #   所以上面那个循环通常取不到东西 —— 实测"余波里只剩困境、没有反应"。
            #   改用 `clear_lines` 清场前记下的那一条（`world.last_beat_text`）。
            #   ⚠ 顺序是"先 recent_lines，再 last_beat_text"：前者只在同一拍里换场、
            #     还没清的情况下有值；后者是常态路径。
            # [EN] ★★★ Fallback: on a scene change `recent_lines` is **already cleared** (the move path
            # [EN] clears before switching), so the loop above usually finds nothing -- measured: the
            # [EN] aftermath had only the dilemma and no reaction. Use the line kept by `clear_lines`
            # [EN] (`world.last_beat_text`). ⚠ Order: recent_lines first, then last_beat_text -- the
            # [EN] former only has a value when the scene changes within the same beat; the latter is
            # [EN] the normal path.
            if not reaction:
                txt = str(getattr(w, 'last_beat_text', '') or '').strip()
                if len(txt) >= 4:
                    reaction = txt[:60]
            owe = str(getattr(w, 'topic_open_with', '') or '').strip()
            topic = str(getattr(w, 'topic') or '').strip()
            dilemma = ''
            if owe:
                dilemma = f'{owe} 那句话还没答'
            elif topic:
                dilemma = f'「{topic}」还没说完'
            if not (reaction or dilemma):
                return                       # 这一场什么也没留下 ⇒ 不留（不编）
            w.aftermath = {'反应': reaction, '困境': dilemma, '决定': ''}
            _LOG.info('换场：上一场留下的余波 = 反应「%s」/ 困境「%s」',
                      reaction[:20], dilemma[:20])
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('aftermath', f'余波记录失败（不影响推演）：{e!r}')

    def _clock_segment(self) -> str:
        """小说里的时段（"戌时"这种）。拿不到就空串 —— 分隔符标签容得下空。
                English:
        The time period in the novel (like "戌时"). If unavailable, empty string -- the separator label
        can accommodate empty.
        """
        clock = getattr(self.world, 'clock', None)
        try:
            return str(clock.segment() if clock is not None else '')
        except Exception:                                   # noqa: BLE001
            return ''

    def _note_think(self, actions: list[tuple[Agent, Action]]) -> None:
        """把这一拍各人的**思维链**记进 `world.actor_think`（最近一条，滚动覆盖）。

        消费方是**剧组台账里「演员」那一行**（`crew/agents.OnDuty`）——
        作者一眼能看到"这个人开口之前在想什么"，那是"这句话为什么这么说"
        最直接的一条线索。零成本（只是搬字符串）。

        ⚠ **只留最近一条**：台账是"这一班人的近况"，不是逐拍日志 ——
          逐拍累积会把它撑成第二份叙事。逐拍的原话在 DEBUG 日志里（见
          `agent/core` 决策那一段）。
        ⚠ **绝不进 `world.recent_lines`**：那是"场上刚发生"（公开的），
          而盘算是私下的（他并没有把它说出口）。
        
                English:
        Record each person's **chain of thought** for this beat into `world.actor_think` (most recent
        one, rolling overwrite).
                The consumer is **the "actors" row in the crew ledger** (`crew/agents.OnDuty`) --
                the author can see at a glance "what this person was thinking before speaking", which is the
                most direct clue to "why this line was said this way". Zero cost (just moving strings).
                ⚠ **Keep only the most recent one**: the ledger is "the recent status of this shift", not a per-beat log --
                  accumulating per beat would bloat it into a second narrative. Per-beat raw lines are in the DEBUG log (see
                  the decision section in `agent/core`).
                ⚠ **Never enter `world.recent_lines`**: that is "what just happened on stage" (public),
                  while the deliberation is private (he did not say it out loud).
        """
        try:
            store = getattr(self.world, 'actor_think', None)
            if not isinstance(store, dict):
                return
            # ★ 同时记「决策完成时间戳」（`actor_think_at`）—— 账台据此在
            #   最近 `CHAR_BUSY_WINDOW` 秒内把这一行标 `busy=True` → 暖金高亮，
            #   让界面"实时看到谁这一拍在动"（见 `crew/studio.ledger`）。
            # [EN] Also record the "decision-completion timestamp" (`actor_think_at`) --
            # [EN] the ledger uses it to flag this row `busy=True` within `CHAR_BUSY_WINDOW`
            # [EN] -> warm-gold highlight, so the UI sees who moved this beat.
            store_at = getattr(self.world, 'actor_think_at', None)
            _now = time.monotonic()
            for agent, act in actions:
                tr = str(getattr(act, 'think_trace', '') or '').strip()
                nm = str(getattr(agent, 'name', '') or '').strip()
                if tr and nm:
                    store[nm] = tr[:80]
                    if isinstance(store_at, dict):
                        store_at[nm] = _now
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('think', f'记演员思维链失败（不影响推演）：{e!r}')

    async def _process_actions(self, actions: list[tuple[Agent, Action]]) -> None:
        """处理一拍的**全部**动作。

        剧本模式：整组交给 `SceneBuilder`（它负责把"同时"归成并行轨、
        把异地的人切成「切至」）；prose 模式：退回逐个处理的老行为。

        ⚠ **"什么都没发生"的动作不进叙事**（`is_noop`）。以前每个 tick 都给
        每个不出声的人写一条「没动，也没出声」，用户那次运行里 8 秒写出了 550 条。
        全场都没动作时才走 `observe_quiet`，而且受 `QUIET_MINUTES` 限流 ——
        安静本身是要写的，但不能刷版。
        
                English:
        Handle **all** actions of one beat.
                Script mode: hand the whole group to `SceneBuilder` (it handles grouping "simultaneous" into parallel tracks and
                cutting people in different places into "cut to"); prose mode: fall back to the old per-item behavior.
                ⚠ **Actions where "nothing happened" do not enter the narrative** (`is_noop`). Previously each tick wrote
                a "didn't move, didn't speak" line for everyone silent; in that user's run, 8 seconds produced 550 lines.
                Only when the whole scene has no actions does it go through `observe_quiet`, and it's rate-limited by `QUIET_MINUTES` --
                quietness itself is worth writing, but it must not flood the page.
        """
        # 决策失败要**看得见**：连续失败说明模型/网络有问题，别让用户
        # 对着一屏"沉默"猜（那次是客户端根本没初始化）。
        # [EN] Decision failure must be **visible**: consecutive failures indicate a model/network problem,
        # [EN] don't let the user
        # [EN] guess at a screen of "silence" (that time the client simply wasn't initialized at all).
        for agent, act in actions:
            reason = str(getattr(act, 'reason', '') or '')
            if '（决策失败' in reason or '（解析失败' in reason:
                self._fail_streak += 1
            else:
                self._fail_streak = 0
        # ★ 这一拍各人的**思维链**（2026-10-07 第七轮）：记进 `world.actor_think`
        #   —— 剧组台账里「演员」那一行要读它（作者能看到人物开口前在想什么）。
        # [EN] ★ This beat's per-person **chain of thought** (2026-10-07 seventh round): recorded into
        # [EN] `world.actor_think`
        # [EN] -- the "actor" row in the crew ledger reads it (the author can see what a character is thinking
        # [EN] before speaking).
        self._note_think(actions)

        # ★★★ **僵局计数**（2026-10-19）—— 用户原话：「剧情要尽快推进」。
        #
        #   实测（《雪国》34 拍）：14 次决策里 **7 次是 `wait`**，理由全是"等脚步声"，
        #   三个人在等同一件事，那件事一直没结果，整场戏停在原地。
        #   提示词里"`wait` 不算往前走一步"早就写着，模型照样等
        #   ⇒ 只能由**外面**推它一下。
        #
        #   判据是"**多数人**在等"（>= 2 人 且 占比 >= 0.6），不是"有人等"：
        #   一个人等着、另一个人在做事，那是正常场面，不该被打断。
        #   攒够 `STALL_BREAK_BEATS` 就请导演走**结算通道**
        #   （见 `director.request_settle` / `_inject_event(settle=…)`）。
        #
        #   ⚠ 为什么在**这里**数：这是唯一同时看见"这一拍全部 Action"的地方。
        #     从 `world.recent_lines` 数不到 —— `wait` 按设计**不进**那张桌面
        #     （别人看不见他在等），读了必然是 0。
        # [EN] ★★★ **Deadlock counting** (2026-10-19) -- user: "push the plot forward".
        # [EN] Measured (Snow Country, 34 beats): 7 of 14 decisions were `wait`, all "waiting for
        # [EN] footsteps" -- three people waiting for the same thing that never resolves. The prompt
        # [EN] already says "`wait` is not a step forward" and the model waits anyway => only an
        # [EN] outside push helps. The test is **most** people waiting (>= 2 and >= 60%), not "someone
        # [EN] waiting": one person waiting while another works is a normal scene.
        # [EN] ⚠ Counted **here** because this is the only place that sees all of a beat's Actions;
        # [EN] `world.recent_lines` cannot see them -- `wait` deliberately does not enter that table.
        try:
            _stall_need = int(CFG.i('STALL_BREAK_BEATS'))
        except Exception:                                        # noqa: BLE001
            _stall_need = 0
        self._stall_beats, _do_settle = stall_beats(
            self._stall_beats, actions, need=_stall_need, stuck=self._dup_speaks)
        # ⚠ 读完之后**减一**（不是清零）：同一句台词会**跨拍**反复出现 ——
        #   第三次真跑里岛村「你刚说什么？我没听清。」散在三拍里，每拍只撞一次，
        #   `stuck` 永远到不了 2，僵局一次都没触发，而整场戏就在"没听清"上打转。
        #   改成"没人重复时每拍衰减 1"⇒ 连续复读会**攒起来**，有人说了新话才降下去。
        # [EN] Decrement by one after reading (do not reset): the same line repeats **across
        # [EN] beats** -- in the third run one line appeared once per beat over three beats, so
        # [EN] `stuck` never reached 2 and the deadlock never fired while the scene circled
        # [EN] "I didn't catch that". Decaying by 1 per quiet beat lets repeats accumulate.
        self._dup_speaks = max(0, self._dup_speaks - 1)
        if _do_settle:
            _waiters = sum(1 for _a, _act in actions
                           if str(getattr(_act, 'verb', '') or '') == 'wait')
            _LOG.info('僵局：连着 %d 拍多数人在等（%d/%d），请导演结算',
                      self._stall_beats, _waiters, len(actions))
            try:
                self.director.request_settle(self._stall_beats)
            except Exception as e:                               # noqa: BLE001
                _LOG.warning('请导演结算失败（不影响出片）：%r', e)
            self._stall_beats = 0
        if self._fail_streak == 3:
            msg = f"（人物决策连续失败 {self._fail_streak} 次：{reason}）"
            _LOG.warning(msg)
            self._push_narrative(msg, 0, kind=S.NOTE)

        meaningful = [(a, act) for a, act in actions if not is_noop(act)]
        # ★ 「没事就把时间跳过去」的计数（2026-10-11）：这一拍**有没有新东西**。
        #   与 `_maybe_quiet()` 同一个判据、同一个位置，但两件事分开做 ——
        #   那个是"要不要写一句「片刻无话」"（有限流），这个是"连着几拍空了"
        #   （纯计数，一次都不能漏）。
        # [EN] ★ "If nothing's happening, just skip the time" counter (2026-10-11): whether this beat **has
        # [EN] anything new**.
        # [EN] Same criterion and same location as `_maybe_quiet()`, but two separate things ——
        # [EN] that one is "should we write a line of 'a moment of silence'" (rate-limited), this one is
        # [EN] "several beats in a row have been empty"
        # [EN] (pure count, not a single one can be missed).
        self._track_idle(not meaningful)

        # ★ 2026-10-14：**每拍都问一次"该补环境了吗"**（与有没有人在动无关）。
        #   放在这个位置（两支之前）是刻意的 —— 下面两支各有一个
        #   `return`，写在任何一支里面都会让**另一支**拿不到环境。
        #   ⚠ 它自己不产 `BEAT`（有人做事时写"片刻无话"是错的），
        #     到点且符合护栏才真产一条 `AMBIENT`（见 `_maybe_ambient`）。
        # [EN] ★ 2026-10-14: **ask once per beat whether to add environment** (independent of
        # [EN] whether anyone is moving). Placing it here (before both branches) is deliberate --
        # [EN] each branch below has a `return`, so putting it inside either one would starve the
        # [EN] **other** branch of environment.
        # [EN] ⚠ It does not itself emit `BEAT` (writing "a moment of silence" while someone is
        # [EN] working is wrong); it only emits a real `AMBIENT` when due and past the guardrail
        # [EN] (see `_maybe_ambient`).
        self._maybe_ambient()
        self._audit_talk()

        if not self._script_mode:
            for agent, action in meaningful:
                self._note_stage_line(agent, action)
                await self._process_action(agent, action)
            if not meaningful:
                self._maybe_quiet()
            return

        if not meaningful:
            self._maybe_quiet()
            return

        # ★★ 动作**真正落到世界状态上**（2026-10-06 补）。
        # [EN] ★★ Actions **actually land on world state** (added 2026-10-06).
        # 以前动作只进叙事流、不碰世界：`move` 是空操作、`world.scene` 从装配那
        # 一刻起再没变过、`emotion` 永远是空的。后果是一串连锁的：
        #   · 场景永不切换 → 分幕几乎不触发 → 屏幕上从来看不到一次真正的「换场」；
        #   · 情绪线索永远取不到值（`_tone_of` 依赖 `ps.emotion`）；
        #   · "人物在世界里活动"退化成"在原地发声"。
        # [EN] Previously actions only entered the narrative stream and didn't touch the world: `move` was a
        # [EN] no-op, `world.scene` never changed from the moment of assembly,
        # [EN] `emotion` was always empty. The consequences were a chain of them:
        # [EN] · Scenes never switch → act breaks almost never trigger → a real "scene change" is never once
        # [EN] seen on screen;
        # [EN] · Emotion cues can never be read (`_tone_of` depends on `ps.emotion`);
        # [EN] · "Characters acting in the world" degrades into "speaking in place".
        for agent, action in meaningful:
            # ★ 「场上刚发生」要在动作生效**之前**记（2026-10-07）：
            #   `move` 会改场景，而这个动作发生在**原来的地点** ——
            #   先落地再记，会把它记到新地点去（站在屋里挪的一步
            #   被记成"在渡口挪的"，换回来的那一刻就对不上了）。
            #   ⚠ 这一处**只记移动**（`spoken` 默认 False）：台词由下面的
            #     `_note_entry(entry)` 从真词条记，免得记到被去重滤掉的重复句。
            # [EN] ★ "Just happened on stage" must be recorded **before** the action takes effect (2026-10-07):
            # [EN] `move` changes the scene, and this action happens at the **original location** ——
            # [EN] if you land it first and then record, it gets recorded at the new location (a step taken while
            # [EN] standing in the room
            # [EN] gets recorded as "taken at the ferry crossing", and the moment you switch back it no longer
            # [EN] matches).
            # [EN] ⚠ This spot **records only movement** (`spoken` defaults to False): dialogue is recorded by the
            # [EN] `_note_entry(entry)`
            # [EN] below from the real entry, so it doesn't get recorded for a duplicate line filtered out by
            # [EN] dedup.
            self._note_stage_line(agent, action)
            self._apply_action(agent, action)

        # ★ 去 AI 味**事后那半**（2026-10-07）：台词里偶发的**套话词**
        #   （"首先""五味杂陈"）直接删掉。放在这里是因为这是**进剧本之前**
        #   最后一个能改的时机 —— 再往后它就变成词条了。
        #   ⚠ 只删词，**句式与修辞一概不动**（删了会把句子弄坏）；
        #     删了什么会记进日志与 `去AI审计.md`（静默改写是本项目明令禁止的）。
        # [EN] ★ The **post-hoc half** of de-AI-ifying (2026-10-07): occasional **boilerplate words** in
        # [EN] dialogue
        # [EN] ("first of all", "a mix of five flavors") are simply deleted. It's here because this is **before
        # [EN] entering the script**,
        # [EN] the last moment it can still be changed —— any later and it becomes an entry.
        # [EN] ⚠ Delete words only, **leave sentence structure and rhetoric completely untouched** (deleting
        # [EN] them would break the sentence);
        # [EN] what was deleted gets logged and written to `去AI审计.md` (silent rewriting is explicitly forbidden
        # [EN] in this project).
        self._deai_clean(meaningful)

        builder = self._ensure_builder()
        scene_before = builder.current
        start = len(scene_before.entries) if scene_before else 0
        builder.observe_tick(meaningful, tick_num=self._tick_no)

        # 反思（概率触发）——「人物不是一直说话」里"在想事"的那一半
        # [EN] Reflection (probabilistically triggered) —— the "thinking about things" half of "characters
        # [EN] aren't always talking"
        for agent, action in meaningful:
            if random.random() < 0.05:
                reflection = await agent.reflect()
                if reflection:
                    builder.observe_reflection(agent.name, reflection)

        scene_now = builder.current
        if scene_now is None:
            return
        # ── 分幕了就是新幕，从头读；否则只读这一拍新加的 ──
        # [EN] ── if there's an act break it's a new act, read from the start; otherwise read only what this
        # [EN] beat newly added ──
        chunk = scene_now.entries if scene_now is not scene_before \
            else scene_now.entries[start:]
        # ★★★ **上屏之前过一遍**（2026-10-08，用户点名的那个闸门）
        # [EN] ★★★ **Run through once before going on screen** (2026-10-08, the gate the user called out by
        # [EN] name)
        # 位置是**唯一正确**的那一处，三条理由：
        #   · 一条词条从"模型生成"到"读者看见"之间，这里是一夫当关的那一点
        #     （`observe_tick` 已经把动作/台词/环境/旁白/进场退场都摊成词条了）；
        #   · 它拿得到 `builder` 里的**整场**上下文（不只是这一拍的两三条）
        #     —— 判"接不接上文"要靠它；
        #   · 它在 `_note_entry`（记进"场上刚发生"）与 `_push_narrative`
        #     （真上屏）**之前** —— 拦下的东西两头都不进，
        #     不会出现"读者没看见、下一个说话的人却听见了"。
        # [EN] The location is the **only correct** one, for three reasons:
        # [EN] · Between an entry being "generated by the model" and "seen by the reader", this is the one
        # [EN] point where it's guarded by a single pass
        # [EN] (`observe_tick` has already laid out actions/dialogue/environment/narration/entrances and exits
        # [EN] as entries);
        # [EN] · It can get the **whole scene** context from `builder` (not just the two or three lines of this
        # [EN] beat)
        # [EN] —— judging "does it connect with the preceding text" depends on it;
        # [EN] · It's before `_note_entry` (recording into "just happened on stage") and `_push_narrative`
        # [EN] (actually going on screen) —— what gets blocked enters neither,
        # [EN] so you never get "the reader didn't see it, but the next person to speak heard it".
        chunk = await self._script_review(chunk)
        # 记下这一拍**真正上屏**了几条（回档要用；审读拦下的不算）
        # [EN] Record how many of this beat **actually went on screen** (needed for rollback; those blocked by
        # [EN] review don't count)
        try:
            self._last_chunk_n = len(chunk)
            if not chunk:
                # 全被拦下 = 这一拍**确实没有新东西**（与"被去重滤掉"同一条口径：
                # 不拿兜底把内容硬塞回去 —— 那正是上一版去重失效的原因）。
                # [EN] Everything blocked = this beat **really has nothing new** (same criterion as "filtered out by
                # [EN] dedup":
                # [EN] don't force content back in with a fallback —— that's exactly why the previous version's dedup
                # [EN] failed).
                self._track_idle(True)
                self._maybe_quiet()
        except Exception:                                        # noqa: BLE001
            self._last_chunk_n = 0
        for entry in chunk:
            # ★ 记进「场上刚发生」——用**真进剧本的词条**（2026-10-07）。
            #   台词可能被去重护栏挡下，那样它没上屏，就不该进缓冲。
            # [EN] ★ Record into "just happened on stage" —— using the **entry that actually entered the script**
            # [EN] (2026-10-07).
            # [EN] A line may be blocked by the dedup guard; in that case it didn't go on screen, so it shouldn't
            # [EN] enter the buffer.
            self._note_entry(entry)
            # ★ 去 AI 味**审计**（2026-10-07）：用户要求"所有产出都过一遍审计"。
            #   在这里而不是 `decide` 那边，是因为**只有这一处知道"什么真的上屏了"**
            #   （被去重挡下的那句、被 `_deai_clean` 清掉的那几个词，
            #    都不该再被报成"AI 味"）—— 报一份"你写了但没上屏的东西"是噪音。
            # [EN] ★ De-AI-ify **audit** (2026-10-07): the user requires "all output goes through the audit".
            # [EN] It's here rather than on the `decide` side because **only this spot knows "what actually went on
            # [EN] screen"**
            # [EN] (the line blocked by dedup, the few words cleared by `_deai_clean`,
            # [EN] should no longer be reported as "AI-ified") —— reporting "things you wrote but that didn't go on
            # [EN] screen" is noise.
            self._deai_audit(entry)
            # ★ 屏幕上是**小说体**（`story_render.sentence`），不是剧本体
            #   （`script_render.one_line` 那套 `〔心声·阿枝〕`/`主角：…` 是给
            #   落盘的剧本用的，读起来像场记单）。用户 2026-10-06：
            #   「有点过于倾向于剧本了，优化一下让他更像一点故事」。
            #   ⚠ 落盘一个字都没动 —— `to_markdown` 仍是剧本格式（反解锚点）。
            # [EN] ★ On screen it's **novel style** (`story_render.sentence`), not script style
            # [EN] the script written to disk, and reads like a continuity sheet). User 2026-10-06:
            # [EN] "It leans a bit too much toward script, optimize it so it's a bit more like a story".
            # [EN] ⚠ Not a single character of what's written to disk has changed —— `to_markdown` is still script
            # [EN] format (the reverse-parse anchor).
            line = STR.sentence(entry)
            if line:
                # ⚠ `kind` 一定要传：界面靠它决定"能不能并进上一段"、
                #   以及段内的样式（心声斜体/环境淡色）。
                # [EN] ⚠ `kind` must be passed: the UI uses it to decide "whether it can merge into the previous
                # [EN] paragraph",
                # [EN] and the style within the paragraph (inner voice italic / environment light color).
                self._push_narrative(
                    line, entry.priority,
                    is_key_event=(entry.kind == S.EVENT and entry.priority == 0),
                    kind=entry.kind,
                    # ★ 把**说话人/对谁说**一路带下去（2026-10-08）：台账要它，
                    #   "谁进了场还没人接他的话"这一条靠的就是这两栏。
                    #   ⚠ 只从**词条**取，不从渲染后的那句里抠（那是正则解字，
                    #     改个渲染格式就崩）。
                    # [EN] ★ Carry **speaker / who it's spoken to** all the way down (2026-10-08): the ledger needs it,
                    # [EN] "who's entered the scene and no one has picked up their line yet" is exactly what these two
                    # [EN] columns are for.
                    # [EN] ⚠ Only take from the **entry**, don't fish it out of the rendered sentence (that's regex
                    # [EN] character parsing,
                    # [EN] and it breaks the moment the render format changes).
                    who=str(getattr(entry, 'speaker', '') or ''),
                    to=str(getattr(entry, 'to', '') or ''),
                    raw=str(getattr(entry, 'text', '') or ''))

    #: 审读要过的词条类型 = **剧情类**。
    # [EN] : entry types that review must cover = **plot types**.
    #: 结构性的一律放行（阶段名 / 剧组状态 / 时间 / 镜头切换 / 分镜卡）——
    #: 它们是程序拼出来的骨架，不是谁"说"的话，拿去问"是不是人话"只会误报。
    # [EN] : Structural ones are all let through (stage names / troupe status / time / shot switches /
    # [EN] storyboard cards) ——
    # [EN] : they're the skeleton assembled by the program, not words anyone "said"; asking "is this human
    # [EN] speech" of them only produces false positives.
    _REVIEW_KINDS = frozenset({
        S.DIALOGUE, S.ACTION, S.NARRATION, S.ASIDE, S.AMBIENT, S.RECALL,
        S.EVENT, S.NOTE, S.ENTER, S.EXIT, S.BEAT, S.SCENE, S.BRIEF, S.TASK,
        S.RECAP, S.SUMMARY,
    })

    #: **要送去问模型的那一批**（`_REVIEW_KINDS` 去掉程序自己写的舞台指示）。
    # [EN] : **The batch to send to the model for review** (`_REVIEW_KINDS` minus stage directions written
    # [EN] by the program itself).
    #: ⚠ 为什么进场/退场/停顿不送模型：它们的正文是程序拼的（`入画` / `已在场` /
    #:   `离场`），不是谁说的话。送过去有两个坏处，都实测过：
    #:     · 白占额度（每换一幕就多几条）；
    #:     · 更要命的是**它会替演员挨刀** —— 桩里给"序号 1"判了个"不是人话"，
    #:       结果被改写的是「已在场」那条进场标记（`verify_script_review` 的
    #:       C2 就是这么红的）。模型本来也不该对这个有意见。
    #:   它们照旧**进台账**（"谁进了场、有没有人接住他"靠的就是它）。
    # [EN] : ⚠ Why entrances/exits/pauses aren't sent to the model: their body text is assembled by the [EN] program (`入画` / `已在场` /
    # [EN] : `离场`), not words anyone said. Sending them over has two downsides, both empirically observed:
    # [EN] :     · Wastes quota (a few more lines each act change);
    # [EN] : · Worse, **it takes the knife meant for the actor** —— in the stub "serial number 1" was
    # [EN] judged "not human speech",
    # [EN] :       and what got rewritten was the entrance marker line 「已在场」 (`verify_script_review`'s
    # [EN] : C2 went red exactly like this). The model shouldn't have an opinion on this in the first
    # [EN] place.
    # [EN] : They still **enter the ledger** as before ("who entered the scene, whether anyone caught him"
    # [EN] depends on it).
    _MODEL_KINDS = _REVIEW_KINDS - {S.ENTER, S.EXIT, S.BEAT}

    async def _script_review(self, entries: list) -> list:
        """**上屏之前过一遍**（`script_doctor`）—— 返回**可以放出去**的那一份。

        用户 2026-10-08（这是本方法存在的全部理由）：
        「在演员真的说出来之前，把新生成的话放到已经出现的话里过一遍，
          看是否通顺 … 任何一个新出现的东西，不管来自哪个Agent或者来源，
          都需要这个 Agent 放到已有历史里看下是否是一个合理的 正确的好看的故事
          和剧本 **不是就不要放出来**」

        四步，顺序不能反：

        1. **规则层**（零成本）—— 形式上的问题（残留 JSON / 占位话 / 出戏词 /
           标点乱敲 / 半截话）。**逐条、每一拍都跑**。
        2. **模型层**（`SCRIPT_REVIEW_MODEL`，每 `SCRIPT_REVIEW_EVERY_TICKS` 拍一次）
           —— 语感与上下文（是不是人话 / 像不像这个人 / 接不接上文 /
           是不是一个主题）。上面那份台账当"已经出现的话"递进去。
        3. **应用**：能改就**改写**（改写稿自己也要过规则层 —— 别把一个问题
           换成另一个），改不动就**拦下**。
        4. **留痕**：拦下/改写都记进台账与日志。

        ⚠ **判不准时一律放行**（模型漏答一条裁决、裁决里字段名写歪了…）：
          审读是"宁可漏，不可误杀"的岗 —— 把好句子拦下来的代价，
          比偶尔漏一句大得多（误杀了读者就少看一段，而且没人查得出来）。
        
                English:
        **Run through this before putting on screen** (`script_doctor`) -- returns the version **that
        can be released**.
                User 2026-10-08 (this is the entire reason this method exists):
                "Before the actor actually says it, run the newly generated line through the lines that have already appeared,
                  and see whether it reads smoothly ... anything newly appearing, no matter which Agent or source it comes from,
                  needs this Agent to put it into the existing history and check whether it is a reasonable, correct, good-looking story
                  and script. **If not, don't release it.**"
                Four steps, order cannot be reversed:
                1. **Rule layer** (zero cost) —— formal issues (residual JSON / placeholder talk / out-of-character words /
                   random punctuation / half-finished sentences). **Run per-item, every beat**.
                2. **Model layer** (`SCRIPT_REVIEW_MODEL`, once every `SCRIPT_REVIEW_EVERY_TICKS` ticks)
                   —— language sense and context (does it sound human / does it sound like this person / does it connect to the previous text /
                   is it one topic). The ledger above is passed in as "what has already been said".
                3. **Apply**: if it can be fixed, **rewrite** it (the rewritten draft must itself pass the rule layer —— don't replace
                   one problem with another); if it can't be fixed, **block** it.
                4. **Leave a trace**: blocks/rewrites are all recorded in the ledger and logs.
                ⚠ **When in doubt, always let it through** (model misses a verdict, field names in the verdict are misspelled...):
                  review is a post that "would rather miss than wrongly kill" —— the cost of blocking a good line
                  is far greater than occasionally missing one (a wrongful kill means the reader sees one less passage, and no one can even detect it).
        """
        if not CFG.b('SCRIPT_REVIEW') or not entries:
            return entries
        try:
            from crew import review as R
        except Exception:                                        # noqa: BLE001
            return entries
        rows = [e for e in entries
                if str(getattr(e, 'kind', '')) in self._MODEL_KINDS]
        if not rows:
            return entries
        items: list[dict] = []
        for i, e in enumerate(rows, 1):
            items.append({
                '序号': i,
                # ★★★ 2026-10-18：**心声要如实标出来**（`aside`）。
                #   以前这里只有两档（台词 / 动作），心声被压成"动作" ⇒
                #   审读根本看不出"这是心里话"，于是**第一人称那条铁律它永远判不了**：
                #   实测 sg-01 里出现「司马昭心想：司马昭一夹马腹向前半步…」（把旁白
                #   塞进了心里话），审读放过了 —— 因为它看到的是一条动作。
                #   ⚠ `rule_check` 只对 `'dialogue'` 加"半截话"那条，传 `'aside'`
                #     就是走通用规则，正合心意声不是台词。
                # [EN] ★★★ 2026-10-18: **label the inner voice honestly** (`aside`).
                # [EN] There used to be only two slots (dialogue / action), so inner voice was
                # [EN] flattened into "action" and the reviewer could never see "this is a thought",
                # [EN] which means it could never judge the first-person rule -- measured in sg-01,
                # [EN] a narration line was smuggled into the inner voice and review let it pass.
                # [EN] ⚠ `rule_check` only adds the half-sentence rule for `'dialogue'`, so
                # [EN] `'aside'` takes the generic rules, which is right (a thought is not a line).
                '类型': ('dialogue' if e.kind == S.DIALOGUE
                         else ('aside' if e.kind == S.ASIDE else 'action')),
                '谁': str(getattr(e, 'speaker', '') or ''),
                '对': str(getattr(e, 'to', '') or ''),
                '文本': str(getattr(e, 'text', '') or ''),
            })
        # ① 规则层：**逐条、零成本、每一拍都跑**
        # [EN] ① Rule layer: **one by one, zero cost, runs every beat**
        rule_bad: dict[int, str] = {}
        for it in items:
            why = R.rule_check(it['文本'], kind=it['类型'])
            if why:
                rule_bad[int(it['序号'])] = why
        # ② 模型层：每 N 拍一次（默认每拍）
        # [EN] ② Model layer: once every N beats (default every beat)
        verdicts: dict[int, dict] = {}
        every = max(1, CFG.i('SCRIPT_REVIEW_EVERY_TICKS'))
        if CFG.b('SCRIPT_REVIEW_MODEL') and (self._tick_no % every == 0):
            try:
                ctx = self._crew_ctx()
                hist = (getattr(self, 'script_log', None) or
                        REVIEW.ScriptLog()).recent_lines(
                            CFG.i('SCRIPT_REVIEW_HISTORY'))
                note = await self.studio.audit(ctx, items=items, history=hist)
                verdicts = R.verdicts_of(note)
                # 那批内容"合起来在说什么"（模型给的一句话）—— 进当天小结，
                # 不进正文（它是读稿意见）。
                # [EN] what that batch of content is "saying collectively" (the one-line summary the model gives) ——
                # [EN] goes into the day's summary,
                # [EN] not into the main text (it's a reading opinion).
                theme = str((note.data or {}).get('主题') or '').strip()
                if theme:
                    self._review_themes.append(theme)
            except Exception as e:                               # noqa: BLE001
                # ⚠ 审读本身坏掉**不影响推演**：这一批全按"过"处理，
                #   但**留一条日志**（静默降级是本项目明令禁止的）。
                # [EN] ⚠ If the review itself breaks, **it doesn't affect the simulation**: this batch is all treated
                # [EN] as "pass",
                # [EN] but **leave a log entry** (silent degradation is explicitly forbidden in this project).
                _LOG.warning('剧本审读没跑成（这一批按放行处理）：%r', e)
        # ③ 应用
        # [EN] ③ Apply
        strict = CFG.b('SCRIPT_REVIEW_STRICT')
        out: list = []
        blocked: list = []
        #: 只被**规则层**判坏的词条（残留 JSON / 占位话 / 出戏词…）。
        #: ★ 这些**不许被"整拍不许删空"那条救回来** —— 垃圾句子上屏比空白糟得多
        #:   （实测：残留 JSON `{"动作": "speak"…}` 被救回来后直接印进了正文）。
        # [EN] Entries rejected **only by the rule layer** (leftover JSON / placeholder talk /
        # [EN] out-of-play words). ★ These must **not** be rescued by "never empty a beat" --
        # [EN] junk on screen is far worse than a blank (measured: leftover JSON was rescued and
        # [EN] printed into the body).
        rule_only: set[int] = set()
        n_fix = n_block = n_dup_pass = 0
        for it in items:
            e = rows[int(it['序号']) - 1]
            _no = int(it['序号'])
            why = rule_bad.get(_no, '')
            row = verdicts.get(_no)
            if row is not None and not R.is_pass(row):
                why = why or (R.why_of(row) or '审读没通过')
            if not why:
                out.append(e)
                continue
            # ★★★ 2026-10-18：**按类别处置**（语义级重复 / 越界 / 其他）。
            #   见 `crew.review.category_of` 的说明：三类不能一刀切。
            #   最关键的一条 —— **重复改不动就放行**：把它删掉会让这一拍变成空白，
            #   而"空白"比"重复"更伤（第三轮实测：只禁不推 ⇒ 全员 `wait` 12 次）。
            # [EN] ★★★ 2026-10-18: **handle by category** (semantic repetition / out of bounds /
            # [EN] other). See `crew.review.category_of`: the three cannot share one rule. The key
            # [EN] one -- **let repetition through when it cannot be rewritten**: deleting it
            # [EN] empties the beat, and blank hurts more than repetition (measured round 3).
            cat = R.category_of(row) if row is not None else R.CAT_OTHER
            fix = R.fix_of(row) if row is not None else ''
            if fix and fix != str(getattr(e, 'text', '') or ''):
                fwhy = R.rule_check(fix, kind=it['类型'])
                if not fwhy:
                    self._review_rewrite(e, fix, why, cat=cat)
                    n_fix += 1
                    out.append(e)
                    continue
            if not strict or cat == R.CAT_DUP:
                # 只记不改那一档（`strict=false`），以及**重复**这一类：
                # 照样上屏，但台账里留一笔（写明是哪一类）。
                # [EN] The record-only tier (`strict=false`), plus **repetition**: it still goes on
                # screen, but the ledger notes it (with the category).
                self._review_log_blocked(e, f'[{cat}] {why}', blocked=False)
                if cat == R.CAT_DUP:
                    n_dup_pass += 1
                    self._review_cat_pass[cat] = self._review_cat_pass.get(cat, 0) + 1
                out.append(e)
                continue
            self._review_log_blocked(e, f'[{cat}] {why}', blocked=True)
            blocked.append(e)
            if row is None or R.is_pass(row):
                rule_only.add(id(e))
            n_block += 1
        # ⚠ **不许把一整拍删空**：全被拦下就全部放行（宁可重复，也不要空白）。
        #   这是本条链路上最容易写歪的地方 —— 删干净了，那一拍就是"什么都没发生"。
        #   ★ 但**规则层判坏的除外**：残留 JSON / 占位话这类"根本不是句子"的东西，
        #     上屏比空白糟（`verify_script_review` 的 C1 就是守这个的）。
        # [EN] ⚠ **Never empty a whole beat**: if everything got blocked, let it all through
        # [EN] (repetition beats blank). ★ Except what the **rule layer** rejected: leftover JSON
        # [EN] and placeholder talk are not sentences at all, and printing them is worse than a
        # [EN] blank (that is what C1 of `verify_script_review` guards).
        if blocked and not out and not rule_only:
            _LOG.warning('审读把这一拍全拦下了（%d 条）—— 全部放行，不许留空白',
                         len(blocked))
            for e in blocked:
                self._review_log_blocked(e, '整拍会被删空 ⇒ 放行', blocked=False)
            out = list(blocked)
            n_block = 0
        elif blocked:
            try:
                self._drop_entries(blocked)
            except Exception as e:                               # noqa: BLE001
                _LOG.warning('审读拦下的词条没能从剧本里撤下：%r', e)
        if n_fix or n_block or n_dup_pass:
            _LOG.info('剧本审读：改写 %d 条 · 拦下 %d 条 · 重复放行 %d 条'
                      '（这一拍新生成 %d 条）',
                      n_fix, n_block, n_dup_pass, len(rows))
        # 剩下的（非剧情类）原样跟在后面 —— 顺序不能乱
        # [EN] The rest (non-narrative) follow after in original form -- order must not be scrambled
        if len(out) == len(rows):
            return entries
        keep = {id(e) for e in out}
        return [e for e in entries if (e not in rows) or (id(e) in keep)]

    def _review_rewrite(self, entry: Any, new_text: str, why: str,
                        *, cat: str = '') -> None:
        """把审读给的改写**落实到词条上**（并同步"场上刚发生"缓冲）。

        ⚠ 缓冲要同步：`_note_stage_line` 在这之前已经把**原句**记进去了
          （领说者那一句要让他同拍的人看得到）。不同步的话，
          下一个人会去回应一句**读者根本没看见**的话 —— 那正是用户报的"割裂感"。
        
                English:
        Apply the rewrite given by review **onto the entry** (and sync the "just happened on stage"
        buffer).
                ⚠ The buffer must be synced: `_note_stage_line` has already recorded the **original line** before this
                  (the lead speaker's line must be visible to those in the same beat). If not synced,
                  the next person will respond to a line **the reader never saw** —— that is exactly the "disconnect" users reported.
        """
        old = str(getattr(entry, 'text', '') or '')
        try:
            # ★★★ 2026-10-18：改写串**也要过一遍元标记清洗**。
            #   `Entry.__post_init__` 只在**构造**时洗，而这里是直接改 `entry.text`
            #   （构造早就发生过了）⇒ 审读自己加的 `〔改动作〕` 会原样进正文。
            #   实测某一轮续写就这么印出来了一次。
            # [EN] ★★★ 2026-10-18: the rewrite string **must be washed too**.
            # [EN] `Entry.__post_init__` only washes at construction, while this assigns
            # [EN] `entry.text` directly (construction happened long ago) => the reviewer's own
            # [EN] `[改动作]` label goes straight into the body. Measured once in the Mowen run.
            from display.script import strip_meta_marks as _wash
            entry.text = _wash(str(new_text or '').strip())
        except Exception:                                        # noqa: BLE001
            return
        if len(self._review_rewrites) > 200:
            self._review_rewrites.clear()
        self._review_rewrites[entry.text] = old
        # ★★★ 2026-10-18：改写**也要进台账**（`原文` 一并记）。
        #   此前只有"拦下/标记"进 `审读台账.jsonl`，改写只留一句日志 ——
        #   于是《审读台账》里查不到"这句原来是什么、被改成了什么"，
        #   而用户要的是「一直记录生成的所有信息」。实测暴露：samples 那一轮
        #   日志里有 3 次改写，台账里一条都没有。
        # [EN] ★★★ 2026-10-18: rewrites **must enter the ledger too** (with `原文`). Previously only
        # [EN] blocks/flags went into `审读台账.jsonl`, so the ledger could not answer "what was this
        # [EN] line before, and what did it become" -- and the user asked for "always record
        # [EN] everything generated". Measured: the samples run logged 3 rewrites, the ledger had 0.
        self._review_log_blocked(entry, f'[{cat}] {why}' if cat else why,
                                 blocked=False, was=old, archived=True)
        # 同步缓冲（从尾部往前找那一句，找到就改）
        # [EN] Synchronous buffer (search backward from the tail for that line; modify it if found)
        try:
            name = str(getattr(entry, 'speaker', '') or '')
            for row in reversed(list(getattr(self.world, 'recent_lines', []) or [])):
                if (str(row.get('who') or '') == name
                        and str(row.get('text') or '') == ' '.join(old.split())[:120]):
                    row['text'] = ' '.join(entry.text.split())[:120]
                    break
        except Exception:                                        # noqa: BLE001
            pass
        if cat:
            self._review_cat_rewrite[cat] = self._review_cat_rewrite.get(cat, 0) + 1
        _LOG.info('剧本审读：改写「%s」→「%s」（%s%s）', old[:40], entry.text[:40],
                  f'{cat}·' if cat else '', why)

    def _review_log_blocked(self, entry: Any, why: str, *, blocked: bool,
                            was: str = '', archived: bool = False) -> None:
        """拦下/标记/改写一条 —— **只记，不说话**（它是闸门，不该往中栏喊）。

        `was` = 改写前的原文；`archived=True` = 这是**改写记录**（进流水，
        不进"读者看过的那一份"，否则同一句话会在 `recent()` 里出现两次）。
        [EN] Block/flag/rewrite one entry -- **record only, don't speak** (it's a gate, it
        shouldn't shout into the center column). `was` = the original text before a rewrite;
        `archived=True` = a **rewrite record** (goes into the stream, not into "the copy the reader
        saw", otherwise the same line would appear twice in `recent()`).
        """
        log = getattr(self, 'script_log', None)
        if log is None:
            return
        try:
            log.add(kind=str(getattr(entry, 'kind', '') or ''),
                                text=str(getattr(entry, 'text', '') or ''),
                                who=str(getattr(entry, 'speaker', '') or ''),
                                to=str(getattr(entry, 'to', '') or ''),
                                day=int(self._current_day or 0),
                                tick=int(self._tick_no or 0),
                                source='script_doctor', place=str(self.world.scene or ''),
                                blocked=bool(blocked), why=str(why or ''),
                                was=str(was or ''), archived=bool(archived))
        except Exception:                                        # noqa: BLE001
            pass
        if blocked:
            self._review_blocked_today += 1
            _LOG.info('剧本审读：拦下一条（%s）—— %s', why,
                      ' '.join(str(getattr(entry, 'text', '') or '').split())[:60])

    def _drop_entries(self, entries: list) -> int:
        """把审读拦下的词条**从剧本里撤掉**（屏幕与落盘的稿子必须一致）。
                English:
        **Remove the entry blocked by review from the script** (what's on screen and what's saved to
        disk must match).
        """
        builder = getattr(self, '_builder', None)
        if builder is None or not entries:
            return 0
        fn = getattr(builder, 'drop_entries', None)
        if fn is None:
            return 0
        return int(fn(entries) or 0)

    def _note_idle_newcomers(self) -> None:
        """**进了场却没人跟他说上话的人** → 下一拍提醒场上的人去接他。

        用户原话：「人物进场了肯定是有用的 大家要去跟他沟通（动作 对话 事情等等）
        不然不要突然来一个人」。

        ⚠ 这是**提醒**（进 `world.watch_note`，下一拍的决策提示词会带上），
          不是拦 —— 人已经上场了，拦不住；能做的只是让戏**跟上他**。
          零成本（只在台账里数三个数），所以每拍都能问一次。
        
                English:
        **People who entered the scene but no one has spoken to** → next beat, remind people on stage to
        engage them.
                User's exact words: "If a character enters, they must be useful; everyone should go communicate with them (actions, dialogue, events, etc.)
                otherwise don't suddenly bring someone in."
                ⚠ This is a **reminder** (goes into `world.watch_note`, the next beat's decision prompt will include it),
                  not a block —— the person is already on stage, can't be blocked; all we can do is make the scene **keep up with them**.
                  Zero cost (just count three numbers in the ledger), so it can be asked once every beat.
        """
        try:
            log = getattr(self, 'script_log', None)
            if log is None:
                return
            win = max(2, CFG.i('SCRIPT_REVIEW_NEWCOMER_TICKS'))
            idle = log.idle_newcomers(int(self._tick_no or 0), window=win)
            if not idle:
                return
            hint = ('（' + '、'.join(idle) + '刚上场，到现在还没人跟他说上一句话 '
                    '—— 谁在场谁就**接住他**：问一句、递个东西、给个动作都算）')
            cur = str(getattr(self.world, 'watch_note', '') or '').strip()
            self.world.watch_note = (cur + '；' + hint) if cur else hint
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('newcomer', f'新上场提示失败（不影响推演）：{e!r}')

    def _apply_action(self, agent: Agent, action: Action) -> None:
        """把一条动作写进世界状态（本轮的"动作落地"）。

        **只做有确定语义的三件事**，不猜模型的意思：
          · `move`  → `ps.location = 目标`，并检查要不要跟着换场
          · `emote` → 把情绪词记进 `ps.emotion`
          · `interact` → 只是"在忙什么"，不进状态（它没有可落地的字段）
        其余（speak / wait / think）本来就不改世界。
        
                English:
        Write an action into the world state (this round's "action landing").
                **Only do the three things with definite semantics**, don't guess the model's intent:
                  · `move`  → `ps.location = target`, and check whether to follow with a scene change
                  · `emote` → record the emotion word into `ps.emotion`
                  · `interact` → only "what they're busy with", doesn't enter state (it has no landable field)
                The rest (speak / wait / think) don't change the world anyway.
        """
        ps = getattr(agent, 'ps', None)
        if ps is None:
            return
        verb = str(getattr(action, 'verb', '') or '')
        target = str(getattr(action, 'target', '') or '').strip()
        if verb == 'move' and target:
            if target_is_not_a_place(self.world, target):
                # ★ 不当地点 → **当作没动**（2026-10-07）。
                #   模型偶尔会把"对话对象"或多代词当成目的地（演示语料里就有
                #   "去了对方"）。照单全收的后果有三样，都很显眼：
                #     · 这个人被踢出"在场名单"（位置跟当前场景对不上了）；
                #     · 屏幕上出现「〔切至 · 对方〕」—— 一个不存在的地方；
                #     · 当天的地图/分幕跟着跑偏。
                #   留一条 INFO：这是**模型的毛病**，不是世界的一部分。
                # [EN] ★ Not a valid location → **treat as if nothing happened** (2026-10-07).
                # [EN] The model occasionally treats the "conversation partner" or a multi-pronoun as the destination
                # [EN] (the demo corpus has
                # [EN] "went to the other party"). Accepting it wholesale has three consequences, all very visible:
                # [EN] · This person gets kicked out of the "present roster" (their position no longer matches the
                # [EN] current scene);
                # [EN] · The screen shows "〔cut to · other party〕" -- a location that doesn't exist;
                # [EN] · That day's map/act breakdown then goes off track.
                # [EN] Leave an INFO: this is a **model bug**, not part of the world.
                _LOG.info('「%s」的 move 目标是「%s」，不像一个地点 —— 位置不动',
                          ps.name, target[:12])
                return
            ps.location = target
            self._maybe_shift_scene()
        elif verb == 'emote' and target:
            # ⚠ **别往 `ps.emotion` 里塞**：它是 `dict[str, float]`（happiness /
            #   anger / fear / sadness / surprise 五个**数值**维度）。塞一个字符串
            #   进去，下一次 `_emotion_str` 做 `v > 0.5` 比较就当场
            # [EN] ⚠ **Don't stuff it into `ps.emotion`**: it's a `dict[str, float]` (happiness /
            # [EN] anger / fear / sadness / surprise, five **numeric** dimensions). Stuff a string
            # [EN] in, and the next time `_emotion_str` does a `v > 0.5` comparison it will on the spot
            #   `TypeError: '>' not supported between 'str' and 'float'` ——
            #   整个 RunLoop 停摆（被 `verify_script_output` 的「跑 8 个 tick
            #   不报错」当场抓住）。模型给的「强作镇定」是**自然语言神态**，
            #   另存一个动态属性，由 persona 读给下一个 prompt 用。
            # [EN] stall the whole RunLoop (caught by `verify_script_output`'s "run 8 ticks
            # [EN] without error" check). The model's "forcing composure" is a **natural-language demeanor**;
            # [EN] store it separately as a dynamic attribute, for persona to read into the next prompt.
            ps.mood_note = target[:12]

    # ══════════════════════════════════════════════════════════
    #  场次编排（2026-10-11）：一场戏接一场戏
    # [EN] Stage scheduling (2026-10-11): one scene after another
    # ══════════════════════════════════════════════════════════
    #  为什么补这一层：作者看了运行记录后说「东一句西一句、小的场景没交代清楚
    #  就跳到新场景」「场景反复切换却没有任何人物出场、动作、情节」。
    #  查下来是**剧作家分了拍、那张表却没下达，运行时也没有"场"这个单位** ——
    #  详见 `director/stage.py` 的文件头。
    # [EN] Why this layer exists: after reading a run log the author said "all over the place, small
    # [EN] scenes never explained before jumping to new ones" and "scenes switching with no character
    # [EN] entering, no action, no plot". The investigation found the playwright **did** split beats,
    # [EN] but **the sheet was never handed down and the runtime had no notion of a "scene"** --
    # [EN] see the header of `director/stage.py`.
    def _stage_observe(self, actions) -> None:
        """把这一拍发生的，记进**本场戏**的账。

        `acted` = **实动作条数**（`is_noop` 的不算 —— 那正是"全场发呆"）；
        `present` = 这一拍**真做过动作的人**（不管他当时在哪个地点）。
        ⚠⚠ **绝不能拿"当前在场名单"当露面**：装配时**全体都在场**，于是
          "该出场的都到齐了"会恒成立 —— 收场条件形同虚设，第一拍就收
          （第一版就是这么写的，判据 B1 当场打红）。
          只认"这一拍真的做过决策的人"：他真在这一拍活过，才算露了面。

            English:
        Record what happened this beat into **this scene's** ledger.
            `acted` = **number of real actions** (`is_noop` ones don't count -- that is exactly "the
            whole cast spacing out");
            `present` = **people who really acted this beat** (regardless of where they were).
            ⚠⚠ **The "current on-stage roster" must NOT count as showing up**: at assembly time
              **everyone is on stage**, so "everyone who should appear has appeared" would always
              hold -- the wrap-up condition becomes vacuous and the very first beat wraps (the first
              version did exactly this and criterion B1 caught it on the spot).
              Only "people who really made a decision this beat" count: only then did he live a beat
              in this scene.
        """
        plan = self._stage_plan
        if plan is None or not plan.enabled:
            return
        try:
            acted = 0
            spoke: list[str] = []
            names: list[str] = []
            for agent, act in (actions or []):
                nm = str(getattr(agent, 'name', '') or '')
                if nm:
                    names.append(nm)
                if is_noop(act):
                    continue
                acted += 1
                if str(getattr(act, 'verb', '') or '') == 'speak' and nm:
                    spoke.append(nm)
            plan.observe(acted=acted, present=names, spoke=spoke)
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('stage_observe', f'场次记账失败（不影响推演）：{e!r}')

    def _maybe_close_beat(self) -> None:
        """这一场戏演完了就收，换地方，进下一拍。

        ★★ 这里是"一场戏接一场戏"的**落点** —— 剧作家的表在这一点被真正执行。
        四件事，顺序不能反：
          ① 推分隔符（这一场到此结束，`note` 就是"为什么收"）；
          ② 剧本文档那边收幕 / 开新幕（`SceneBuilder`）；
          ③ 换到**这一拍指定的地方**（`_stage_place_to`，导演顺手调人）；
          ④ 推幕首那一行〔第 N 拍 · 场 · 主题〕。

        ⚠ 全部演完（表走到底）时只推一条 `NOTE`，**不推第 ④ 条** ——
          没有"下一拍"却推它的幕首，是在报一件没发生的事。

            English:
        When this scene is finished, wrap it up, change place, and move to the next beat.

        ★★ This is the **landing point** of "one scene after another" -- the playwright's sheet is
        actually executed right here. Four things, and the order matters:
          ① push a separator (this scene ends here; its `note` is the "why");
          ② close / reopen the act on the script side (`SceneBuilder`);
          ③ change to **the place this beat specifies** (`_stage_place_to`, the director also moves
             the people over);
          ④ push the act-header line 〔beat N · place · topic〕.

        ⚠ When everything is done (the sheet ran out) only a `NOTE` is pushed, **not item ④** --
          pushing an act header for a "next beat" that doesn't exist would be announcing something
          that never happened.
        """
        plan = self._stage_plan
        if plan is None or not plan.enabled:
            return
        try:
            why = plan.done_reason()
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('stage_done', f'收场判定失败（不影响推演）：{e!r}')
            return
        if not why:
            return
        old_place = (getattr(self.world, 'scene', '') or '').strip()
        plan.advance()
        # 进度挂到世界上：续跑时要接着走，不能从第 1 拍重来
        # [EN] Hang the progress on the world: a resume must continue, not restart at beat 1
        try:
            self.world.stage_index = int(plan.index) - 1
        except Exception:                                        # noqa: BLE001
            pass
        _LOG.info('场次收场：%s ｜ %s', why, plan.ledger_line() or '全部演完')
        # ① 分隔符（这一场到此结束）
        # [EN] (1) separator (this scene ends here)
        try:
            self._push_divider(D.Divider(
                D.SCENE_END,
                {'clock': self._clock_segment(), 'place': old_place},
                note=why[:60]))
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('stage_div', f'收场分隔符失败：{e!r}')
        # ② 剧本文档那边收幕 / 开新幕
        # [EN] (2) close the act / open a new one on the script side
        if self._script_mode and self._builder is not None:
            try:
                self._builder.close_scene()
                self._builder.begin_scene(force=True)
            except Exception as e:                               # noqa: BLE001
                self._warn_once('stage_scene', f'收幕失败（不影响推演）：{e!r}')
            # ⚠ `_last_place` / `_last_clock` 要跟着走：不跟的话，下一拍开头
            #   `_maybe_break_scene` 会拿**旧口径**比一次，把同一处地方当成
            #   "地点变了"再切一刀（白切，屏幕上多一条分隔符）。
            # [EN] ⚠ `_last_place` / `_last_clock` must follow along: otherwise the next beat's
            # [EN] `_maybe_break_scene` compares against the **old** values, treats the same place as
            # [EN] "the location changed" and cuts once more (a pointless extra separator on screen).
            self._last_place = (getattr(self.world, 'scene', '') or '').strip()
            self._last_clock = getattr(self.world, 'clock', None)
        nxt = plan.current
        if nxt is None:
            self._push_narrative(f'〔{plan.ledger_line()}〕', 0, kind=S.NOTE)
            return
        # ③ 换到这一拍指定的地方
        # [EN] (3) change to the place this beat specifies
        moved = self._stage_place_to(nxt.place)
        if moved:
            self._push_scene(place=moved, segment=self._clock_segment())
        # ④ 幕首那一行（作者看得见「现在是第几拍」）
        # [EN] (4) the act-header line (the author can see "which beat we are on")
        try:
            self._push_narrative(f'〔{plan.header()}〕', 0, kind=S.SCENE)
        except Exception:                                        # noqa: BLE001
            pass

    def _stage_place_to(self, place: str) -> str:
        """把"这一拍该在哪"落到 `world.scene` 上，并把该出场的人**调过去**。

        返回**实际切过去的地点**（没切 = 空串）。

        ★ 这是"导演按安排好的内容进行编排"的落点：剧作家写了这一拍在哪，
          导演就把场子摆到那儿、把人叫到那儿 —— 而不是等着"人都走光"
          再看谁留下了（那是老逻辑，也正是"场景乱跳却没人"的成因）。
        ⚠ 尊重 `ROUND_SCENE`（本轮锁场景）：锁着就不换。
        ⚠ 必须是**地点表里的地方**才换（与 `_maybe_shift_scene` 同一条纪律：
          宁可少切，也别把"门外""对面"这种场面话当地名）。
          剧作家写的常比地点表细（"茶肆·堂内" vs "茶肆"），所以用
          **包含关系**认（与 `world.is_on_stage` 同一口径）。

            English:
        Land "where this beat happens" onto `world.scene` and **move the people over**.

        Returns **the place actually switched to** (empty string when nothing switched).

        ★ This is where "the director arranges things according to the plan" lands: the playwright
          wrote where this beat happens, so the director sets the stage there and calls the people
          over -- instead of waiting for "everyone to leave" and seeing who stayed (that was the old
          logic, and it is exactly what produces "scenes jumping around with nobody in them").
        ⚠ Respects `ROUND_SCENE` (this round's locked scene): when locked, don't switch.
        ⚠ It must be **a place in the location table** (same discipline as `_maybe_shift_scene`:
          better to switch less than to treat stage talk like "outside the door" or "the other side"
          as a place name). What the playwright writes is often finer than the location table
          ("the hall · daytime" vs "Mowen Tower"), so **containment** is used (same convention as
          `world.is_on_stage`).
        """
        place = str(place or '').strip()
        if not place:
            return ''
        if bool(getattr(self.world, 'scene_locked', False)):
            return ''
        try:
            known = {str(x).strip() for x in
                     (getattr(self.world, 'place_names', None) or []) if str(x).strip()}
        except Exception:                                        # noqa: BLE001
            known = set()
        if not known:
            return ''
        target = place if place in known else ''
        if not target:
            # 长的先试（"茶肆后厨"比"茶肆"更贴合）
            # [EN] Try the longer ones first ("Mowen Tower hall" fits better than "Mowen Tower")
            for k in sorted(known, key=len, reverse=True):
                if k and (k in place or place in k):
                    target = k
                    break
        if not target:
            return ''
        if not target:
            # ★★★ 2026-10-22（用户：「小说提到了府城和大柳树 你确认下后续会出现…地图吗？」）：
            #   剧作家写的「河岸柳树下」「府城」不在地点表里 ⇒ 以前这里**静默返回空**，
            #   于是 `world.scene` 一直不动、三场戏的地点全记成「望江楼」、地图永远是那一张。
            #   现在**把它登记成本轮的新地点**（有门槛，见 `_register_place`），然后照常切。
            #   ⚠ 只走这一条路（剧作家明确写进「场」里的地点）；`_maybe_shift_scene` 那条
            #     "谁最后走就换成谁的目标"仍然**只认地点表** —— 那是场面话污染的主要来源。
            # [EN] ★★★ 2026-10-22 (user: "the novel mentions the prefecture city and the big willow --
            # [EN] will those maps appear?"): what the playwright writes is not in the location table,
            # [EN] so this used to **silently return empty** -- `world.scene` never moved, all three
            # [EN] scenes recorded "Mowen Tower" and the map stayed that one map. Now it is **registered
            # [EN] as a new place for this round** (gated, see `_register_place`) and the switch proceeds.
            # [EN] ⚠ Only this path (a place the playwright wrote into the beat); `_maybe_shift_scene`'s
            # [EN] "switch to wherever the last leaver went" still honours the table only.
            target = self._register_place(place)
            if not target:
                return ''
        cur = (getattr(self.world, 'scene', '') or '').strip()
        if target == cur:
            return ''
        self.world.scene = target
        try:
            self.world.clear_lines()
        except Exception:                                        # noqa: BLE001
            pass
        # ★ **导演调人**：这一拍该出场的人，从这一拍起就**在这个场**——
        #   不指望演员自己走过去，那正是"场景切了却没人"的老毛病。
        # [EN] ★ **The director moves the people**: those who should appear in this beat are **in this
        # [EN] place** from this beat on -- don't count on the actors walking over themselves, which is
        # [EN] exactly the old "scene switched but nobody is there" problem.
        plan = self._stage_plan
        beat = plan.current if plan is not None else None
        if beat is not None:
            room = getattr(self.world, 'people', {}) or {}
            for n in beat.cast:
                ps = room.get(n)
                if ps is None:
                    continue
                if callable(getattr(ps, 'is_active', None)) and not ps.is_active():
                    continue
                try:
                    ps.location = target
                except Exception:                                # noqa: BLE001
                    pass
        _LOG.info('按拍换场：%s → %s', cur or '（未命名）', target)
        return target

    def _maybe_shift_scene(self) -> None:
        """在场的前台人物**都走了** → 场景跟着走。

        换场是分幕的主要触发之一（`SceneBuilder.maybe_break` 看的就是
        `world.scene` 变化）。以前这一步不存在，`world.scene` 永远是装配时那个
        名字，于是"换场"这件事在整轮推演里一次都不会发生。

        保守起见只在**一个人都不剩**时才换 —— 有人还在原地，这一场戏就没完。
        
                English:
        All present foreground characters **have left** → the scene follows.
                Scene change is one of the main triggers for act breaks (`SceneBuilder.maybe_break` looks at
                `world.scene` changes). Previously this step didn't exist, `world.scene` was always the name from assembly time,
                so "scene change" never happened once in the entire simulation run.
                To be conservative, only change when **not a single person remains** —— if anyone is still there, this scene isn't over.
        """
        # ★ 本轮锁定了场景就不换（`ROUND_SCENE`，2026-10-11）——
        #   用户要的是"整轮都在同一处"。判在**最前面**：下面的地点表核对、
        #   清空"场上刚发生"那一步都不该发生（换都没换，凭什么清）。
        # [EN] ★ Once the scene is locked this round, don't switch (`ROUND_SCENE`, 2026-10-11) --
        # [EN] what the user wants is "the whole round in the same place". Judge at the **very front**: the
        # [EN] location table check below,
        # [EN] and the step clearing "just happened on stage" should not happen (no switch occurred, so why
        # [EN] clear).
        if bool(getattr(self.world, 'scene_locked', False)):
            return
        # ★★ **有场次编排时，这里不换场**（2026-10-11）—— 换场归 `_maybe_close_beat`
        #   按"这一拍的「场」"来定。
        #   这套「人都走光就换成最后离开那个人的目标」的老逻辑会跟表**打架**：
        #   演员中途离开本场去拿个东西，这一场戏在表里**还没演完**就先换了地方 ——
        #   作者看到的"场景反复切换"有一半就是这么来的。
        # [EN] ★★ **With a stage schedule in place, don't switch scenes here** (2026-10-11) --
        # [EN] switching belongs to `_maybe_close_beat`, keyed on "this beat's location".
        # [EN] The old "everyone left, so switch to the last leaver's target" logic **fights** the
        # [EN] sheet: an actor ducks out mid-scene for something and the place changes before the scene
        # [EN] is actually finished -- half of the author's "scenes switching back and forth" comes from
        # [EN] exactly this.
        if (self._stage_plan is not None and self._stage_plan.enabled
                and self._stage_plan.current is not None):
            return
        cur = (getattr(self.world, 'scene', '') or '').strip()
        on_stage = [a for a in self.agents if a.ps.is_active()]
        if not on_stage:
            return
        # ⚠ **必须命中设定里的地点表**才换场。
        #   第一版是"谁最后走就换成谁的目标" —— 结果模型随口给的
        #   「门外」「对方」「账台」都成了场景名，一场戏被切得七零八落，
        #   `verify_run_control` / `verify_script_output` 当场被抓红。
        #   没有地点表就**不换场**（宁可少换，也别把场面话当地名）。
        # [EN] ⚠ **Must match a location in the settings' location table** to switch scenes.
        # [EN] The first version was "whoever leaves last switches to their target" -- as a result, whatever
        # [EN] the model blurted out,
        # [EN] "outside the door", "other party", "the counter" all became scene names, and one play got
        # [EN] chopped to pieces,
        # [EN] with `verify_run_control` / `verify_script_output` caught red on the spot.
        # [EN] Without a location table, **don't switch scenes** (better to switch less than to treat
        # [EN] pleasantries as place names).
        known = {str(x).strip() for x in
                 (getattr(self.world, 'place_names', None) or [])
                 if str(x).strip()}
        if not known:
            return
        if any(not a.ps.location or a.ps.location == cur for a in on_stage):
            return                      # 还有人在这儿 → 这一场继续
            # [EN] Someone's still here → this scene continues
        for a in reversed(on_stage):
            loc = (a.ps.location or '').strip()
            if loc and loc != cur and loc in known:
                self.world.scene = loc
                # ★ 换场了 —— 上一场说的话不该再挂在眼前（2026-10-07）。
                #   `recent_text` 本来就按地点过滤，所以这不是"必须"；
                #   但清一下更省、也更不容易出意外（比如地点名相近时）。
                # [EN] ★ Scene switched -- what was said on the previous scene should not still hang in view
                # [EN] (2026-10-07).
                # [EN] `recent_text` already filters by location anyway, so this isn't "mandatory";
                # [EN] but clearing saves more and is less prone to surprises (e.g. when location names are similar).
                try:
                    self.world.clear_lines()
                except Exception:                                # noqa: BLE001
                    pass
                _LOG.info("换场：%s → %s", cur or '（未命名）', loc)
                return

    def _maybe_quiet(self) -> None:
        """这一拍全场都没动 —— 但「片刻无话」**每 `QUIET_MINUTES` 故事分钟只写一次**。

        没有这个门槛，安静的时刻会把版面刷满（跟「没动，也没出声」是同一个病）。
        
                English:
        This beat nobody moved at all —— but "a moment of silence" is written **only once per
        `QUIET_MINUTES` story minutes**.
                Without this threshold, quiet moments would flood the layout (same disease as "didn't move, didn't speak").
        """
        gap = CFG.i('QUIET_MINUTES')
        if gap <= 0:
            return
        if self._game_min - self._last_quiet_min < gap:
            return
        self._last_quiet_min = self._game_min
        self._ensure_builder().observe_quiet()

    def _maybe_ambient(self) -> None:
        """每 `AMBIENT_MINUTES` 故事分钟补一条**环境白描**（与有没有人在动无关）。

        ★★★ 2026-10-14（用户）：「我看现在的推演结果 是大量的对话 正常小说的话
        应该有…**大量的环境**…不应该只有对话」。

        ⚠ 为什么必须新增这条通路：环境原来**只在"全场都没动"时才写**
          （`_maybe_quiet()` ← `observe_quiet()`），而推演里"有动静"是常态
          ⇒ **环境几乎不出现**，读者看到的是一屏台词。
        ⚠ 按**故事分钟**节流（不是按拍数）：故事时间才是读者感知的节奏 ——
          按拍数会让"今天拍得多"变成"今天环境多"，那是假密度。
        ⚠ `AMBIENT_MINUTES <= 0` = 关掉这条通路（回到老行为），
          用户要能自己关（见 `config.py` 那一项）。
        ⚠ 真正的护栏在 `SceneBuilder.observe_ambient()`：它会在
          "上一条已经是 `AMBIENT`"时**跳过** ⇒ 不会连着刷同一句；
          素材取自 `world.sound_design` / "时段 × 天气"罐头池 ⇒ **不编造**。
        ⚠ 它与 `_maybe_quiet()` **互不干扰**：那条只在空场走，这条每拍都问一次
          （但到点才真产），两条共用一个产出函数（`_emit_ambient`），
          所以"环境怎么写"只有一份实现。
        [EN] ★★★ 2026-10-14 (user): "I see the deduction output is mostly dialogue; a normal novel
        [EN] should have ... **a lot of environment** ... it should not be only dialogue".

        [EN] ⚠ Why this path must be added: environment used to be written **only when "nobody moved
        [EN] at all"** (`_maybe_quiet()` <- `observe_quiet()`), while "something is happening" is the
        [EN] norm in a deduction => **environment almost never appeared**, and the reader saw a screen
        [EN] of dialogue.
        [EN] ⚠ Throttled by **story minutes** (not by beat count): story time is the rhythm the reader
        [EN] perceives -- throttling by beats would turn "many beats today" into "much environment
        [EN] today", which is fake density.
        [EN] ⚠ `AMBIENT_MINUTES <= 0` = turn this path off (back to the old behavior); the user must
        [EN] be able to switch it off (see that entry in `config.py`).
        [EN] ⚠ The real guardrail is in `SceneBuilder.observe_ambient()`: it **skips** when "the
        [EN] previous entry is already `AMBIENT`" => it will not spam the same line; and its material
        [EN] comes from `world.sound_design` / the "time period x weather" canned pool => **nothing is
        [EN] fabricated**.
        [EN] ⚠ It and `_maybe_quiet()` **do not interfere**: that one only runs when the scene is
        [EN] empty, this one is asked every beat (but only produces when due), and both share one
        [EN] producer (`_emit_ambient`), so "how environment is written" has a single implementation.
        """
        gap = CFG.i('AMBIENT_MINUTES')
        if gap <= 0:
            return
        if self._game_min - self._last_ambient_min < gap:
            return
        self._last_ambient_min = self._game_min
        self._ensure_builder().observe_ambient()

    def _grade_beat(self) -> None:
        """让**导演**给这一拍定品级，写进世界（提示词动态拼接的两个开关之一）。

        ★★★ 2026-10-18 用户：「很多Agent的提示词请动态拼接 而不是固定的
          根据需要由特定Agent负责品级」。

        "品级"不是一个质量分，是**这一拍该给多少约束**：

        | 品级 | 触发 | 这一拍读到几条手艺 |
        |---|---|---|
        | `重` | 开场 / 转折 / 收束 / 冲突 / 查稿 / 成稿 | 读满（`READ_LIMIT`） |
        | `中` | 其余，且有事在发生 | 读满 |
        | `轻` | 日常 + 张力低 + 没人欠话 | 只读一半 |

        为什么"轻"这一档必须存在：日常戏塞十条例规，写出来是匠气
        （2026-10-18 实测：句长掉到 5–6 字、动作归零；加上"空气要挂在人身上"
        才回到 12 字）。**不是每一拍都该被同样的力度捏。**

        ⚠ 判在**决策之前**（调用点见 `_tick`，紧接 `_maybe_dispatch`）：
          品级迟一拍，等于这一拍读的是上一拍的档。
        ⚠ 失败沿用旧值 —— 这只是调度，不该让推演停。
        [EN] Let the **director** grade this beat and write it into the world (one of the two
        [EN] switches for dynamic prompt assembly). Grade is not a quality score, it is **how much
        [EN] constraint this beat gets** (table above). The `light` grade must exist: piling ten rules
        [EN] on a daily beat reads mannered (measured: sentence length fell to 5-6 chars, zero
        [EN] actions). ⚠ Graded **before decisions**; on failure keep the old values -- this is only
        [EN] scheduling and must never stop the run.
        """
        try:
            from director import supervisor as SUP
            left = None
            try:
                per_day = int(86400 // max(1, CFG.i('BEAT_SECONDS')))
            except Exception:                                    # noqa: BLE001
                per_day = 0
            if per_day > 0:
                left = max(0, per_day - int(getattr(self, '_ticks_today', 0) or 0))
            # 这一拍要不要跑模型审读 —— 与 `_review_batch` 里的判法**同一口径**
            # （`SCRIPT_REVIEW_MODEL` 且拍到 `SCRIPT_REVIEW_EVERY_TICKS` 的整数倍）。
            # ⚠ 不另立一套：两处判"该不该审"是万恶之源。
            # [EN] Whether this beat runs the model review -- the **same rule** as in `_review_batch`
            # [EN] (`SCRIPT_REVIEW_MODEL` and tick is a multiple of `SCRIPT_REVIEW_EVERY_TICKS`).
            # [EN] ⚠ No second implementation.
            reviewing = False
            try:
                every = max(1, CFG.i('SCRIPT_REVIEW_EVERY_TICKS'))
                reviewing = bool(CFG.b('SCRIPT_REVIEW_MODEL')
                                 and int(getattr(self, '_tick_no', 0) or 0) % every == 0)
            except Exception:                                    # noqa: BLE001
                reviewing = False
            mom, lvl = SUP.grade_beat(
                self.world,
                is_new_scene=not (getattr(self.world, 'recent_lines', None) or []),
                beats_left_today=left,
                reviewing=reviewing,
            )
            self.world.beat_moment = mom
            self.world.craft_level = lvl
            # ★★ 第几拍也要写：调度器靠它做环形轮换（`craft/dispatch.pick` 的 `tick`）。
            #   ⚠ 这一行是**补 bug**：字段原来根本不存在，`getattr(…, 0)` 恒 0 ⇒
            #     每拍挑到的完全是同一批，而"直接传 tick"的判据是绿的。
            # [EN] ★★ Also write the beat number: the dispatcher's ring depends on it. ⚠ This line
            # [EN] **fixes a bug**: the field did not exist, `getattr(..., 0)` was always 0 => every
            # [EN] beat picked the same batch, while the criterion passing `tick` directly was green.
            self.world.beat_tick = int(getattr(self, '_tick_no', 0) or 0)
            # ★★ 心理距离（#10 Cohn）：与品级**同一次判定**里算，因为它们用的是同一个
            #   `mom`（"这一拍是冲突还是收束"）—— 分两处算就会有两份真相。
            #   ⚠ 传 `prev` 是为了"不许连着两拍都贴着"（否则满篇心声）。
            # [EN] ★★ Psychological distance (#10 Cohn): computed in the **same judgement** as the
            # [EN] grade because both use the same `mom`. Computing it in two places means two truths.
            # [EN] ⚠ `prev` prevents two close beats in a row (walls of inner voice).
            self.world.narrative_distance = SUP.distance_for(
                mom, prev=str(getattr(self.world, 'narrative_distance', '') or ''))
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('grade_beat', f'品级判定失败（沿用上一拍）：{e!r}')

    def _audit_talk(self) -> None:
        """每拍算一次**这一段是不是各说各话**，并把"话题锚 / 谁欠一句"写进世界。

        ★★★ 2026-10-18 用户原话：
          「好几次人物说的话互相不对应 就是一个人说的话 另外一个人不去接…
            在很短的一段时间内 出场人物应该是按照**一个主题**展开对话的
            而不是每个人自己一个主题 中间应该有协调者 特别是导演
            应该消除这种自说自话的问题」

        **零成本**：`supervisor.talk_audit()` 只解析已经上屏的台词行（二元组重合 +
        `对` 字段），不调模型 ⇒ 可以**每拍都算**（不必像盯戏那样降频）。

        产出三样，全部由 `agent/core.py` 的 `[这一段在谈的]` 消费：
          · `world.topic`            —— 最近一组**真问答**里"答"的那句（原样引文）；
          · `world.topic_open_with`  —— 被点名、还没回的那个人；
          · `world.topic_run`        —— 连续几句没人接（≥3 会在下拍提示词里点名批评）。

        ⚠ **只算不拦**：不在这一层删任何词条。理由和大家闺秀那条一样 ——
          渲染层删句会留下空白，而空白比"各说各话"更伤（见 `_review_repeat` 的说明）。
          真正拦的地方是审读（它看得懂意思）。
        ⚠ 算不出来（条目太少 / 整段没台词）时**保持原值**，不要清零 ——
          清零会让"上一场欠的那一句"凭空消失（那正是用户要的延续性）。
        [EN] Compute once per beat **whether this stretch is everyone-talking-to-themselves**,
        [EN] and write the topic anchor / who-owes-an-answer into the world.
        [EN] **Zero cost**: `talk_audit()` only parses already-rendered dialogue lines (bigram
        [EN] overlap + the `to` field), no model call => it can run **every beat**.
        [EN] ⚠ **Compute only, never block**: nothing is removed here. Deleting lines at this layer
        [EN] leaves blanks, and a blank hurts more than talk-drift (see `_review_repeat`). Real
        [EN] blocking happens in the script review, which can read meaning.
        [EN] ⚠ When it cannot compute (too few entries / no dialogue), **keep the old values** --
        [EN] clearing them would make "the line still owed from the previous scene" vanish, which is
        [EN] exactly the continuity the user asked for.
        """
        if not CFG.b('CREW'):
            return
        builder = self._builder
        if builder is None:
            return
        try:
            from director import supervisor as SUP
            from display import script_render as _SR
            entries = builder.recent_entries(24)
            lines: list[str] = []
            for e in entries:
                one = _SR.one_line(e)
                if one and '※' not in one[:2] and '▷' not in one[:2]:
                    lines.append(one)
            issue, led = SUP.talk_audit(lines)
            if led.get('topic'):
                self.world.topic = str(led['topic'])
            if led.get('open_with'):
                self.world.topic_open_with = str(led['open_with'])
            self.world.topic_run = int(led.get('run') or 0)
            if issue is not None and issue.line() != getattr(self, '_talk_last', ''):
                self._talk_last = issue.line()
                _LOG.info('导演盯对话：%s（欠一句的是 %s）',
                          issue.line(), self.world.topic_open_with or '—')
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('talk_audit', f'对话接续审计失败（不影响推演）：{e!r}')

    def _note_stage_line(self, agent: Agent, action: Action, *,
                         spoken: bool = False) -> None:
        """把一条动作记进「场上刚发生」缓冲（`world.recent_lines`）。

        这是"接话"的地基（用户 2026-10-07 报「所有人都在自说自话」）：
        决策 prompt 里多出的 `[刚才]` 那一段，内容就是这里攒的。

        **只记"别人能听见/看见的"**（说出来的话、挪了地方）：
        `wait` / `think` / `emote` 别人看不出来，记了只会把这张桌面弄脏 ——
        而桌面只有 8 条，脏一条就少看见一条别人的话。

        ★★ 2026-10-14（用户）：「我看现在的推演结果 是大量的对话 正常小说的话
        应该有…人物做的事情…故事情节…不应该只有对话」——
        **看得见的动作也要进这张桌面**。改之前只有 `speak` 与 `move` 进，
        `interact`（跟谁打交道）与 `emote`（神情变化）**都不进** ——
        而那两样**在场的人都看得见**，正是这段注释开头写的"只记别人能看见的"
        本来该覆盖的。后果是每个人的 `[刚才]` 里只剩台词，
        于是下一拍人人都在"接别人的话"，没人接别人的**动作** ——
        这是"推演结果只有对话"的**输入层**原因。

        ⚠ 三条界限（照旧，不能越）：
          1. `wait` **不记** —— 干等别人看不出来（注释原话就是它）；
          2. `think` **不记** —— 那是 `ASIDE`（心声，不外泄），
             进了桌面就等于全场都听见他心里那本账（人设当场崩）；
          3. `speak` 且 `spoken=False` **不记** —— 台词由 `_note_entry()`
             从**真进剧本的词条**记（见下面那段说明）。
        ⚠ 记的是 `_verb_desc(action)`（**带 `detail` 的真实描写**），
          不是硬编码的"去了X" —— 见 `_verb_desc` 2026-10-14 那条注释。

                English:
        **Only record what "others can hear/see"** (spoken lines, moved location):
        `wait` / `think` / `emote` aren't visible to others; recording them only dirties this table ——
        and the table only holds 8 entries, so one dirty entry means one less of someone else's line seen.

        ★★ 2026-10-14 (user): "I see the deduction output is mostly dialogue; a normal novel should
        have ... things the characters do ... plot ... should not be only dialogue" --
        **visible actions must also enter this table**. Before, only `speak` and `move` went in;
        `interact` (dealing with whom) and `emote` (expression change) **did not** -- yet both are
        **visible to everyone on stage**, which is exactly what the opening sentence of this very
        docstring ("only record what others can see") was supposed to cover. The result was that
        everyone's `[刚才]` contained only dialogue, so on the next beat everyone was "picking up
        the other's words" and nobody picked up anyone's **actions** -- the **input-layer** reason
        "the deduction output is all dialogue".

        ⚠ Three boundaries (unchanged, must not be crossed):
          1. `wait` is **not recorded** -- idling is invisible to others (that is literally what the
             docstring says about it);
          2. `think` is **not recorded** -- that is `ASIDE` (inner voice, not leaked), and putting it
             in the table means the whole cast hears his private ledger (the character collapses);
          3. `speak` with `spoken=False` is **not recorded** -- dialogue is recorded by `_note_entry()`
             from **entries that actually entered the script** (see the passage below).
        ⚠ What is recorded is `_verb_desc(action)` (**the real description carrying `detail`**),
          not the hardcoded "went to X" -- see the 2026-10-14 note in `_verb_desc`.
        """
        name = str(getattr(agent, 'name', '') or '')
        if not name:
            return
        verb = str(getattr(action, 'verb', '') or '')
        target = str(getattr(action, 'target', '') or '').strip()
        try:
            if verb == 'speak':
                # 台词只在 `spoken=True`（领说者当场那句）时记；其余由 `_note_entry` 记。
                # [EN] Dialogue is recorded only when `spoken=True` (the lead speaker's live line);
                # [EN] the rest is recorded by `_note_entry`.
                if not spoken:
                    return
                line = str(getattr(action, 'dialogue', '') or '').strip()
                if line:
                    self.world.note_line(name, line, kind='speak', to=target)
                return
            # ★ 看得见的动作（move / interact / emote）都进桌面。
            #   `wait`（干等）与 `think`（心声）除外 —— 别人看不出来。
            #   ⚠ `move` / `interact` **没有对象、也没有 `细节`** 时跳过：
            #     那种情况下 `_verb_desc` 会给出 `去了` / `和互动` 这种半句，
            #     记进去只是噪声（原来那句 `and target` 守的就是这件事）。
            # [EN] ★ Visible actions (move / interact / emote) all enter the table.
            # [EN] `wait` (idling) and `think` (inner voice) are excluded -- invisible to others.
            # [EN] ⚠ `move` / `interact` are skipped when they have **neither a target nor a
            # [EN] `细节`**: `_verb_desc` would then yield half a sentence like `去了` / `和互动`,
            # [EN] and recording that is pure noise (the original `and target` guarded exactly
            # [EN] this).
            _has_detail = bool(str(getattr(action, 'detail', '') or '').strip())
            _ok = True
            if verb in ('move', 'interact'):
                _ok = bool(target) or _has_detail
            elif verb not in ('emote',):
                _ok = False
            if _ok:
                desc = _verb_desc(action)
                if desc:
                    self.world.note_line(name, desc, kind='act')
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('stage_line', f"记录场上对话失败（不影响推演）：{e!r}")

    # ══════════════════════════════════════════════════════════
    #  去 AI 味（2026-10-07）—— 库在 `style/deai.py`
    # [EN] De-AI (2026-10-07) -- library is in `style/deai.py`
    # ══════════════════════════════════════════════════════════
    # 用户原话：「有时候演员说话会有 AI 味道，你收集整理 AI 味道表达方式相关
    # 词语之类的，做一个去 AI 库，所有演员说话之前，所有工作人员产出任何内容
    # 之前，都做去 AI 味道审计处理。」
    # [EN] User's exact words: "Sometimes actors' speech has an AI flavor, you collect and organize
    # [EN] AI-flavor expression-related
    # [EN] words and such, make a de-AI library, before all actors speak, before all staff produce any
    # [EN] content
    # [EN] do de-AI flavor audit processing."
    # 三个落点，各管一段（**别把它们并成一件事**）：
    #   · 说话**之前** → `agent/core.py` 把清单塞进决策提示词（事前那半）
    #   · 进剧本**之前** → 这里 `_deai_clean`（只删套话**词**）
    #   · 上屏**之后** → 这里 `_deai_audit`（记命中，日界落盘一份）
    # 剧组那 15 个职位的产出走 `crew/studio.Studio._deai_check`（同一个库）。
    # [EN] Three landing points, each handling a stage (**don't merge them into one thing**):
    # [EN] · **Before** speaking → `agent/core.py` injects the list into the decision prompt (the pre half)
    # [EN] · **Before** entering the script → here `_deai_clean` (only removes boilerplate **words**)
    # [EN] · **After** going on screen → here `_deai_audit` (records hits, dumps a copy at the day
    # [EN] boundary)
    # [EN] The 15 crew positions' output goes through `crew/studio.Studio._deai_check` (same library).

    def _deai_clean(self, actions: list[tuple[Agent, Action]]) -> None:
        """把台词里的**套话词**删掉（只删词，不碰句式）。

        ⚠ 这是一次**真的改写**，所以要守三条：
          ① 只删 `style.deai` 里那批**确定的套话词** —— "首先""五味杂陈"这种，
             删掉之后句子仍然成立；句式（"不是A而是B"）**一律不动**。
          ② 删了**要记一笔**（日志 + 当天审计页）—— 静默改写是禁止的。
          ③ 开关是 `DEAI_STRIP`，关掉就只审计、不改写。
        
                English:
        Delete the **boilerplate words** from the dialogue (delete only words, don't touch sentence
        structure).
                ⚠ This is a **real rewrite**, so three rules must be followed:
                  ① Only delete the batch of **clearly boilerplate words** in `style.deai` -- things like "首先" and "五味杂陈",
                     the sentence still holds after deletion; sentence patterns ("不是A而是B") are **left untouched**.
                  ② Deletions **must be logged** (log + same-day audit page) -- silent rewriting is forbidden.
                  ③ The switch is `DEAI_STRIP`; when off, only audit, do not rewrite.
        """
        if not CFG.b('DEAI') or not CFG.b('DEAI_STRIP'):
            return
        try:
            from style import deai
        except Exception:                                        # noqa: BLE001
            return
        for agent, act in actions:
            if str(getattr(act, 'verb', '') or '') != 'speak':
                continue
            line = str(getattr(act, 'dialogue', '') or '')
            if not line.strip():
                continue
            new, removed = deai.strip_hard(line)
            if removed and new.strip():
                try:
                    act.dialogue = new
                except Exception:                                # noqa: BLE001
                    continue
                self._deai_stripped.extend(removed)
                _LOG.info('去 AI 味：「%s」的台词里删掉了套话词 %s',
                          agent.name, '、'.join(removed))

    def _deai_audit(self, entry) -> None:
        """查一条**真的上屏了**的词条，命中就攒起来（日界统一落盘）。
                English:
        Check an entry that **actually made it on screen**; accumulate hits (flushed to disk at day
        boundary).
        """
        if not CFG.b('DEAI'):
            return
        try:
            from style import deai
            kind = str(getattr(entry, 'kind', '') or '')
            if kind not in (S.DIALOGUE, S.ASIDE, S.AMBIENT, S.ACTION,
                            S.NARRATION, S.RECALL):
                return
            who = str(getattr(entry, 'speaker', '') or '') or '旁白'
            text = str(getattr(entry, 'text', '') or '')
            if not text.strip():
                return
            res = deai.audit_text(text, who=who)
            if res.hits:
                self._deai_hits.extend(res.hits)
            self._deai_checked += 1
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('deai_audit', f'去 AI 审计失败（不影响推演）：{e!r}')

    # ══════════════════════════════════════════════════════════
    #  收工：复盘重演 · 去 AI 审计落盘（2026-10-07）
    # [EN] Wrap-up: review replay · de-AI audit dump (2026-10-07)
    # ══════════════════════════════════════════════════════════
    async def _maybe_replay_day(self, scenes) -> None:
        """复盘标了「需要重演」时，回档当天最后一段重排。

        **默认关**（`DAY_REVIEW_REPLAY`）—— 理由：重演要重排那一幕（花钱），
        而且回档会把已经写好的东西删掉。开着就等于授权程序自己动作者的稿子，
        这件事必须由作者明确点头。

        ⚠ 一天最多一次：反复"复盘说不行 → 重演 → 又不行"是死循环，
          而每一圈都花钱。第二次复盘再说不行就**只报不改**。
        
                English:
        When the review is marked "needs replay", roll back to the last segment of the day and
        re-arrange.
                **Off by default** (`DAY_REVIEW_REPLAY`) -- reason: replay requires re-arranging that scene (costs money),
                and rollback deletes what has already been written. Leaving it on is authorizing the program to touch the author's manuscript by itself,
                and this must be explicitly approved by the author.
                ⚠ At most once per day: repeatedly "review says no → replay → still no" is an infinite loop,
                  and each round costs money. If the second review still says no, **report only, do not modify**.
        """
        if not CFG.b('CREW') or not CFG.b('DAY_REVIEW_REPLAY'):
            return
        if self._replayed_today:
            return
        note = None
        try:
            note = self.studio.note_of('reviewer')
        except Exception:                                        # noqa: BLE001
            return
        if note is None or not note.ok:
            return
        if not bool((note.data or {}).get('需要重演')):
            return
        cap = int(CFG.i('DIRECTOR_ROLLBACK_MAX'))
        if cap <= 0:
            return
        # 回档**最后一幕**（不是整个一天）—— 一天的戏往往只有一段立不住，
        # 整天重来会把好的部分一起扔掉，而且很贵。
        # [EN] Roll back **the last act** (not the whole day) -- a day's play often has only one segment that
        # [EN] doesn't hold up,
        # [EN] and redoing the whole day throws away the good parts too, and is expensive.
        n = cap
        done = self._rollback(n)
        if not done:
            return
        self._replayed_today = True
        _LOG.info('复盘判定"这一天立不住"→ 回档重演：删掉最近 %d 条', done)
        self._push_narrative(
            t('（复盘 · 判定这一天立不住）回档重演：撤掉了最近 {n} 条，'
              '后半段重新来过。', n=done), 0, kind=S.NOTE)
        # 回档之后**重写当天的落盘** —— 不重写的话，文件里留着的是
        # 已经"不算数"的那一版（屏幕与文件又对不上了）。
        # [EN] After rollback, **rewrite that day's dump** -- without rewriting, the file keeps the
        # [EN] version that already "doesn't count" (screen and file disagree again).
        try:
            groups = list(self._builder.scenes) if self._builder is not None else []
            if self._builder is not None and self._builder.current is not None:
                groups.append(self._builder.current)
            if groups and self.runfolder is not None:
                self.runfolder.flush_daily_script(
                    self._current_day, groups,
                    calendar_str=self.world.clock_display(),
                    weather=self.world.weather,
                    cast=self.world.on_stage_names(),
                    tension=f'{self.world.tension:.2f}',
                    recap=self._recap_text(),
                    scene_intro=str(getattr(self._day_script, 'scene_intro', '') or ''))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('重演后重写落盘失败：%r', e)

    def _flush_review_report(self) -> None:
        """把**剧本审读**这一天记账与裁决落盘（用户点名要的"一直记录"）。

        两份，分工不同（**别合成一份**）：
          · `审读台账.jsonl` —— **流水**，只写增量（`_review_flushed` 之后那些），
            一轮一份、追加写。给程序读、给人事后查（"第 3 天第 17 拍到底上屏过
            哪几条、谁拦的、为什么"）。
          · `剧本审读.md` —— **小结**，每天覆盖写。给人读：记了多少、拦了几条、
            拦的是什么、谁进了场却没搭上话、这一批合起来在说什么。

        ⚠ 一条都没记过就不写 `剧本审读.md`（一天一份空文件没意义，
          还会把运行文件夹塞满）—— 与 `_flush_deai_report` 同一条口径。
          但 **`.jsonl` 照样按增量写**（它是流水，不是报告）。
        
                English:
        Flush this day's accounting and verdict of **script review** to disk (the "always recording" the
        user explicitly asked for).
                Two files, different roles (**do not merge into one**):
                  · `审读台账.jsonl` -- **stream**, writes only increments (those after `_review_flushed`),
                    one per round, append-only. For programs to read, for humans to look up afterwards ("on day 3, shot 17, exactly
                    which entries made it on screen, who blocked them, and why").
                  · `剧本审读.md` -- **summary**, overwritten daily. For humans: how many recorded, how many blocked,
                    what was blocked, who entered the scene but did not get to speak, and what this batch is saying collectively.
                ⚠ If nothing was ever recorded, do not write `剧本审读.md` (an empty file per day is meaningless,
                  and will also fill up the run folder) -- same criterion as `_flush_deai_report`.
                  But **`.jsonl` is still written incrementally** (it is a stream, not a report).
        """
        if not CFG.b('SCRIPT_REVIEW'):
            return
        log = getattr(self, 'script_log', None)
        if log is None:
            return
        try:
            rows = log.rows
            # ★ 流水里**上屏的与被拦下的都要**（按流水号增量写）——
            #   只写上屏的，这份台账就退化成"正文的副本"了，
            #   而"这句为什么没上屏"恰恰是它最该答的问题。
            # [EN] ★ In the stream, **both what went on screen and what was blocked** are needed (write
            # [EN] incrementally by stream number) --
            # [EN] writing only what went on screen degrades this ledger into "a copy of the main text",
            # [EN] whereas "why didn't this line go on screen" is exactly the question it should answer most.
            fresh = log.everything(after_seq=int(getattr(self, '_review_flushed', 0)))
            if fresh:
                log.append_jsonl(self.runfolder.root / REVIEW.FILE_LOG, fresh)
                self._review_flushed = max(r.seq for r in fresh)
            if not rows and not log.blocked:
                return
            md = log.report_md()
            themes: list[str] = []
            for t in list(getattr(self, '_review_themes', []))[-6:]:
                if t and t not in themes:
                    themes.append(t)
            if themes:
                md += ('\n## 审读给每批内容概括的「在说一件什么事」\n\n'
                       + '\n'.join(f'- {t}' for t in themes) + '\n')
            # ★★★ **按类别记账**（2026-10-18）：「今天修掉了几处重复 / 几处越界」。
            #   不给这一节，作者只看得到"改写了 N 条"，分不清是修复读还是修越界；
            #   而这两件事的处置规则不同，混在一起就没法判断审读到底在干什么。
            # [EN] ★★★ **Accounting by category** (2026-10-18): "how many repetitions / how many
            # [EN] out-of-bounds lines were fixed today". Without this section the author only sees
            # [EN] "N rewrites" and cannot tell which kind; the two are handled differently, so
            # [EN] mixing them makes the review's actual behaviour unreadable.
            _cr = dict(getattr(self, '_review_cat_rewrite', {}) or {})
            _cp = dict(getattr(self, '_review_cat_pass', {}) or {})
            if _cr or _cp or self._review_blocked_today:
                # ⚠ `md` 是**字符串**，别 `+= [列表]` —— 那样会 TypeError，
                #   而这行在 `except` 里被吞掉，表现成"报告里就是没有那一节"（不留痕）。
                # [EN] ⚠ `md` is a **string**: `+= [list]` raises TypeError, and it gets swallowed
                # [EN] by the except below, showing up only as "that section is missing".
                _rows = ['\n## 这一天审读按类别的处置\n',
                         '', '| 类别 | 改写 | 放行（改不动） |', '|---|---|---|']
                for _k in (REVIEW.CAT_DUP, REVIEW.CAT_BOUND, REVIEW.CAT_OTHER):
                    if _cr.get(_k) or _cp.get(_k):
                        _rows.append(f'| {_k} | {_cr.get(_k, 0)} | {_cp.get(_k, 0)} |')
                _rows += ['',
                          '> 「重复」改不动时**放行而不是删掉** —— 删掉会让这一拍变成空白，'
                          '而空白比重复更伤读者。', '']
                md = md + '\n'.join(_rows)
            self.runfolder.write_report(REVIEW.FILE_MD, md)
            _LOG.info('第 %d 天剧本审读：上屏 %d 条、拦下 %d 条（累计拦 %d）',
                      self._current_day, len(rows), len(log.blocked),
                      self._review_blocked_today)
            # 换天：裁决已经落进小结，台上的两个计数清零（台账留着，
            # 它是"读者看过的那一份"，跨天也要能当上文用）
            # [EN] Day switch: the verdict has already landed in the summary, the two counters on stage reset to
            # [EN] zero (the ledger stays,
            # [EN] it is "the copy the reader saw", and must still work as prior context across days)
            self._review_themes = []
            self._review_blocked_today = 0
            # 类别计数也是"按天"的（小结已经写进去了）—— 一起清
            # [EN] Category counters are per-day too (the summary already has them) -- clear together
            self._review_cat_rewrite = {}
            self._review_cat_pass = {}
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('剧本审读落盘失败（不影响推演）：%r', e)

    def _flush_deai_report(self) -> None:
        """把今天（演员上屏的词条 + 剧组 15 个职位的产出）的去 AI 命中写成一份页。

        数据有两个来源，**必须合起来看**（分开看会得到两个都偏窄的结论）：
          · `self.deai_take()`     —— 剧情里上屏的词条（演员说的话）；
          · `studio.take_deai_hits()` —— 剧组各职位的产出。
        
                English:
        Write today's (actor on-screen entries + outputs of the 15 crew positions) de-AI hits into one
        page.
                There are two data sources, **must be viewed together** (viewed separately you get two conclusions that are both too narrow):
                  · `self.deai_take()`     -- entries that made it on screen in the plot (what actors said);
                  · `studio.take_deai_hits()` -- outputs of each crew position.
        """
        if not CFG.b('DEAI'):
            return
        try:
            from style import deai
            hits, stripped = self.deai_take()
            try:
                hits = list(hits) + list(self.studio.take_deai_hits())
            except Exception:                                    # noqa: BLE001
                pass
            # 没命中、也没删过词 → **不写空报告**（一天一份空文件没意义，
            # 还会把运行文件夹塞满）
            # [EN] No hits and no words removed → **don't write an empty report** (an empty file a day is
            # [EN] meaningless,
            # [EN] and it also stuffs the run folder full)
            if not hits and not stripped:
                return
            res = deai.AuditResult(hits=list(hits), checked=int(self._deai_checked))
            extra = ''
            if stripped:
                cnt: dict[str, int] = {}
                for w in stripped:
                    cnt[w] = cnt.get(w, 0) + 1
                extra = ('**被删掉的套话词**（`DEAI_STRIP`，只删词、不动句式）：'
                         + '、'.join(f'{w}×{n}' for w, n in
                                     sorted(cnt.items(), key=lambda kv: -kv[1])))
            md = deai.render_report(
                res, title=f'去 AI 味审计 · 第 {self._current_day} 天',
                extra=f'> 第 {self._current_day} 天 · '
                      f'查了 {self._deai_checked} 段（演员台词 + 剧组产出）\n\n{extra}')
            self.runfolder.write_report('去AI审计.md', md)
            _LOG.info('第 %d 天去 AI 审计：硬禁 %d 处、提醒 %d 处%s',
                      self._current_day, len(res.hard), len(res.soft),
                      f'，另删掉套话词 {len(stripped)} 处' if stripped else '')
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('去 AI 审计落盘失败（不影响推演）：%r', e)

    def deai_take(self) -> tuple[list, list]:
        """取走并清空当天的审计结果 —— `(命中, 被删掉的套话词)`。

        与 `crew/studio.take_deai_hits()` 是**一对**（那边管剧组产出，
        这边管上屏的词条），日界一起落盘 `去AI审计.md`。
        
                English:
        Take and clear the day's audit results -- `(hits, deleted boilerplate words)`.
                Forms a **pair** with `crew/studio.take_deai_hits()` (that side handles crew outputs,
                this side handles on-screen entries), flushed to disk together at day boundary as `去AI审计.md`.
        """
        hits, stripped = list(self._deai_hits), list(self._deai_stripped)
        self._deai_hits.clear()
        self._deai_stripped.clear()
        return hits, stripped

    # ══════════════════════════════════════════════════════════
    #  导演盯戏（2026-10-07）—— 规则在 `director/supervisor.py`
    # [EN] Director watching the play (2026-10-07) -- rules in `director/supervisor.py`
    # ══════════════════════════════════════════════════════════
    # 用户原话：「演员演绎过程中 导演要一直盯着 如果有演员演的台词和动作不对
    # 要及时提出来 导演随时可以要求回档 即删除最近生成的一段戏 然后导演可以
    # 要求暂停表演 自己想一下刚才的戏 要求演员修改 如果必要的话 可能会找
    # 剧作家 小说作者 临时开会 修改剧本和小说故事之后重新开始
    # 导演要一直心里有一个大纲 从顶层到细节一直把控剧情进展」
    # [EN] User's exact words: "During the actor's performance the director must keep watching, if any
    # [EN] actor's lines and actions are wrong
    # [EN] point it out in time, the director can request rollback at any time, i.e. delete the most
    # [EN] recently generated segment of the play, then the director can
    # [EN] request pausing the performance, think for a moment about the play just now, require the actors
    # [EN] to revise, if necessary may call
    # [EN] the playwright, novelist for an ad-hoc meeting, revise the script and novel story then restart
    # [EN] the director must always keep an outline in mind, controlling the plot progress from top level
    # [EN] down to details"
    # 三级处理，**从轻到重**（默认只做前两级；"开会"要人拍板）：
    #   ① 提醒（`world.watch_note`）→ 下一拍的决策提示词里带 `[导演提示]`；
    #      这是"要求演员修改"最省的做法：不额外调用，他下一次决策自己就会绕开。
    #   ② 回档（`_rollback`）→ 删掉刚生成的那几条戏，同时把屏幕上那几条撤掉。
    #      服从 `DIRECTOR_ROLLBACK_MAX`（一次最多删几条）。
    #   ③ 开会（写进 `_watch_notes`，由复盘/日志带出去）——
    #      **不自动做**：它要重写剧本甚至改小说故事，那是作者的权限。
    # [EN] Three tiers of handling, **from light to heavy** (by default only the first two tiers; "meeting"
    # [EN] requires a human to sign off):
    # [EN] ① Remind (`world.watch_note`) → the next beat's decision prompt carries `[director note]`;
    # [EN] this is the most economical way to "require actors to revise": no extra calls, and on his next
    # [EN] decision he'll naturally avoid it himself.
    # [EN] ② Rollback (`_rollback`) → delete the lines just generated, and simultaneously retract those
    # [EN] lines from the screen.
    # [EN] Obeys `DIRECTOR_ROLLBACK_MAX` (max lines deleted at once).
    # [EN] ③ Meeting (written into `_watch_notes`, carried out by review/log) --
    # [EN] **not done automatically**: it requires rewriting the script and even changing the novel story,
    # [EN] which is the author's authority.

    async def _director_watch(self) -> None:
        """每 N 拍盯一次戏（`DIRECTOR_WATCH_EVERY`）。

        **零 LLM 成本**：查重用的是 `store.db.similarity`（二元组打分），
        所以"一直盯着"这件事才做得起。
        
                English:
        Watch the play every N shots (`DIRECTOR_WATCH_EVERY`).
                **Zero LLM cost**: duplicate checking uses `store.db.similarity` (bigram scoring),
                which is why "always watching" is affordable.
        """
        if not CFG.b('CREW') or not CFG.b('DIRECTOR_WATCH'):
            return
        every = max(1, CFG.i('DIRECTOR_WATCH_EVERY'))
        if self._tick_no % every:
            return
        builder = self._builder
        if builder is None:
            return
        try:
            from director import supervisor as SUP
            from display import script_render as _SR
            # ★★ **导演心里那个大纲**（2026-10-07 审计补上）。
            # [EN] ★★ **That outline in the director's mind** (added in the 2026-10-07 audit).
            # 用户：「导演要一直心里有一个大纲 从顶层到细节一直把控剧情进展」。
            # `supervisor.outline_check()` 就是干这个的 —— 而它此前**零调用**：
            # 函数写好了、docstring 写得清楚，大纲只活在文档里。
            # [EN] User: "the director must always keep an outline in mind, controlling the plot progress from top
            # [EN] level down to details".
            # [EN] `supervisor.outline_check()` is exactly for this -- and it previously had **zero calls**:
            # [EN] the function was written, the docstring was clearly written, but the outline lived only in the
            # [EN] docs.
            # 为什么放在盯戏这一步：两者都是"导演**一直在看**的东西"
            # （`supervisor` 模块头就是这么分的：盯戏盯重复、大纲盯进度）。
            # 频率跟着 `DIRECTOR_WATCH_EVERY`（默认 2 拍一次，零成本）。
            # 写进 `world.outline_note`：进日志、进导演提示、也进复盘的材料。
            # [EN] Why put it in the watching-the-play step: both are things "the director is **always watching**"
            # [EN] (that's how the `supervisor` module header divides it: watching watches for repetition, outline
            # [EN] watches for progress).
            # [EN] Frequency follows `DIRECTOR_WATCH_EVERY` (default once every 2 beats, zero cost).
            # [EN] Write into `world.outline_note`: goes into the log, into the director note, and also into the
            # [EN] review material.
            try:
                _beats = len(getattr(getattr(self, '_day_script', None),
                                     'beats', None) or [])
                outline = SUP.outline_check(self.world, today_beats=_beats)
                self.world.outline_note = outline
                if outline and outline != getattr(self, '_outline_last', ''):
                    _LOG.info('导演大纲：%s', outline)
                    self._outline_last = outline
            except Exception as e:                               # noqa: BLE001
                self._warn_once('outline', f'大纲自查失败（不影响推演）：{e!r}')
            entries = builder.recent_entries(24)
            lines = []
            for e in entries:
                one = _SR.one_line(e)
                if one and '※' not in one[:2] and '▷' not in one[:2]:
                    lines.append(one)
            people = [a.name for a in self.agents]
            issues = SUP.scan_repetition(
                lines, people=people,
                min_people=max(2, CFG.i('DIRECTOR_WATCH_MIN_PEOPLE')))
            idle = SUP.idle_issue(lines)
            if idle is not None:
                issues.append(idle)
            if not issues:
                return

            # ── ① 提醒：写进世界，下一拍的决策提示词会带 `[导演提示]` ──
            # [EN] ── ① Reminder: write to the world; the decision prompt for the next beat will carry `[Director
            # [EN] Hint]` ──
            worst = max(x.severity for x in issues)
            for x in issues:
                self._watch_notes.append(x.line())
            # ★ 大纲**总是**捎在提示里（2026-10-07）：用户要的是"导演一直心里
            #   有一个大纲" —— 提醒演员别重复的同时，也把"现在走到哪儿了"
            #   一并给他们看一眼（这是导演当场能给的唯一坐标）。
            # [EN] ★ The outline is **always** attached to the prompt (2026-10-07): what the user wants is "the
            # [EN] director always has
            # [EN] an outline in mind" —— while reminding the actors not to repeat, also show them "where we are
            # [EN] now"
            # [EN] so they can see it too (this is the only coordinate the director can give on the spot).
            _ol = str(getattr(self.world, 'outline_note', '') or '').strip()
            self.world.watch_note = (
                (f'（现在走到：{_ol}）' if _ol else '')
                + '；'.join(x.line() for x in issues[:3])
                + '（**换一件事做、换一个说法** —— 别让不同的人各说各的同一句）')
            for x in issues:
                _LOG.info('导演盯戏：%s', x.line())

            # ── ② 回档：删掉**刚生成的这一拍**（有上限）──
            # [EN] ── ② Rollback: delete **the beat just generated** (has an upper limit) ──
            cap = int(CFG.i('DIRECTOR_ROLLBACK_MAX'))
            last_n = int(getattr(self, '_last_chunk_n', 0) or 0)
            if worst >= 2 and cap > 0 and last_n > 0:
                n = min(cap, last_n)
                done = self._rollback(n)
                if done:
                    self._watch_notes.append(
                        f'回档：删掉了刚生成的 {done} 条戏，重演这一拍')
                    _LOG.info('导演回档：删掉最近 %d 条戏（这一拍共 %d 条）',
                              done, last_n)

            # ── ③ 开会：只**记下来**，不自动做（见方法头那段）──
            # [EN] ── ③ Meeting: only **note it down**, do not do it automatically (see the method header) ──
            if worst >= 2 and len(self._watch_notes) >= 6:
                self._watch_notes.append(
                    '（提醒：同一天里重复问题已多次出现 —— 建议收工时让复盘'
                    '仔细看一遍，必要时回档重排这一段。）')
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('director_watch', f'导演盯戏失败（不影响推演）：{e!r}')

    def _rollback(self, n: int) -> int:
        """**回档**：从剧本里删掉最近 n 条，并让屏幕同步撤掉。

        返回真的删掉了几条。三件事必须**一起**做，少一件就会出现
        "文件里删了、屏幕上还在"（或反过来）——
        那比不回档更让人糊涂。
        
                English:
        **Rollback**: delete the most recent n entries from the script, and make the screen withdraw
        them in sync.
                Returns how many were actually deleted. Three things must be done **together**; missing one produces
                "deleted in file, still on screen" (or the reverse) --
                that is more confusing than not rolling back at all.
        """
        builder = self._builder
        if builder is None:
            return 0
        try:
            done = int(builder.rollback(n) or 0)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('回档失败（不影响推演）：%r', e)
            return 0
        if not done:
            return 0
        # ② 屏幕上那几条也要撤掉
        # [EN] ② The few lines on screen also need to be removed
        try:
            if self._on_rollback is not None:
                self._on_rollback(done)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('回档后同步屏幕失败（不影响推演）：%r', e)
        # ③ 「场上刚发生」缓冲也要退 —— 否则下一拍的人会看到"一句已经被删掉的话"
        #   ⚠ 要**就地删**。第一版写成 `rows = list(...)` 再 `del rows[-done:]`
        #     —— 删的是那份**拷贝**，缓冲一条都没少（`verify_studio_v2` 的 D10
        #     用行为判据抓住了它：「删了 2；缓冲 2→2」）。
        #     这类"复制之后改副本"的错读代码看不出来，只有真跑一遍才现形。
        # [EN] ③ The "just happened on stage" buffer also needs to roll back —— otherwise the next beat's
        # [EN] people will see "a line that has already been deleted"
        # [EN] ⚠ Must **delete in place**. The first version was written as `rows = list(...)` then `del
        # [EN] rows[-done:]`
        # [EN] —— what got deleted was that **copy**, the buffer lost not a single line (`verify_studio_v2`'s
        # [EN] D10
        # [EN] caught it with a behavioral criterion: "deleted 2; buffer 2→2").
        # [EN] This kind of "modify the copy after copying" error cannot be seen by reading the code, it only
        # [EN] shows up when you actually run it.
        try:
            rows = getattr(self.world, 'recent_lines', None)
            if isinstance(rows, list) and rows:
                del rows[-done:]
        except Exception:                                        # noqa: BLE001
            pass
        self._rollback_total += done
        return done

    def _note_entry(self, entry) -> None:
        """从**真实产生的词条**记「场上刚发生」（剧本模式的唯一来源）。

        与 `_note_stage_line` 的分工：
          · 那一处从 `Action` 记（意图），管 `move` 这类**不会被加工**的动作；
          · 这里从 `Entry` 记（成品），管台词 —— 因为台词会经过去重护栏
            （`SceneBuilder._said`：同一句不说第二遍），被挡下的那句
            **读者看不到**，就不该进缓冲。
        
                English:
        Record "what just happened on stage" from **entries actually produced** (the sole source in
        script mode).
                Division of labor with `_note_stage_line`:
                  · That one records from `Action` (intent), handles actions like `move` that **will not be processed**;
                  · Here records from `Entry` (finished product), handles dialogue -- because dialogue passes through the dedup guardrail
                    (`SceneBuilder._said`: the same sentence is not said twice), and the blocked sentence
                    **is not visible to readers**, so it should not enter the buffer.
        """
        kind = str(getattr(entry, 'kind', '') or '')
        who = str(getattr(entry, 'speaker', '') or '').strip()
        text = ' '.join(str(getattr(entry, 'text', '') or '').split())
        if not (who and text):
            return
        if kind == S.DIALOGUE:
            self.world.note_line(who, text, kind='speak',
                                 to=str(getattr(entry, 'to', '') or ''))

    def _reply_candidates(self, on_stage: list[Agent]) -> list[Agent]:
        """**谁最该接话**：刚有人冲着他说话、而他还没答。

        为什么要有这一步（用户 2026-10-07 报「对话很割裂」）：
        每拍只挑 1~2 个人决策，而挑法是**纯随机** —— 于是
        「阿枝问主角一句话」之后，答话的主角可能**要等好几拍才被抽中**，
        那时前面已经插进来三四件不相干的事，屏幕上就成了"各说各的"。

        判据取 `recent_lines` 里最近几条：谁的话**明确冲着在场的某个人说**
        （`to` 命中），那个人就是最该开口的人。从**最新往回**找，
        找到就返回（近的比远的急）。

        ⚠ 说话人自己**不算**候选：他刚说完，该轮到别人接；
          否则会出现"一个人连着说三拍"（那也是一种自说自话）。
        
                English:
        **Who most should respond**: someone was just spoken to, and he has not answered yet.
                Why this step exists (user reported "dialogue is very disjointed" on 2026-10-07):
                Each shot only picks 1~2 people to decide, and the picking method is **purely random** -- so
                after "A-Zhi asks Shen Yan a question", Shen Yan who answers may **have to wait several shots before being picked**,
                by then three or four unrelated things have been inserted in front, and on screen it becomes "each speaking their own".
                The criterion takes the most recent few in `recent_lines`: whoever's words are **clearly directed at someone present**
                (`to` hits), that person is the one who most should speak. Search from **newest backward**,
                return when found (near is more urgent than far).
                ⚠ The speaker himself **does not count** as a candidate: he just finished speaking, it should be someone else's turn;
                  otherwise there would be "one person speaking three beats in a row" (that is also a form of talking to oneself).
        """
        names = {str(getattr(a, 'name', '') or '') for a in on_stage}
        if not names:
            return []
        if not CFG.b('DIALOGUE_CONTEXT'):
            # 关掉对话衔接 → 挑人回到纯随机（与从前一字不差）
            # [EN] Turn off dialogue continuity → picking people returns to pure random (identical to before,
            # [EN] character for character)
            return []
        rows = list(getattr(self.world, 'recent_lines', None) or [])
        for r in reversed(rows[-3:]):                # 只看最近三条
        # [EN] Only look at the most recent three
            if str(r.get('kind') or '') != 'speak':
                continue
            who = str(r.get('who') or '').strip()
            to = str(r.get('to') or '').strip()
            if not to or to not in names or to == who:
                continue
            # `to` 也可能不是人名（"门外""大家"）—— 只有真的是在场的人才算
            # [EN] `to` may also not be a person's name ("outside the door", "everyone") —— only count it if it is
            # [EN] really someone present
            return [a for a in on_stage
                    if str(getattr(a, 'name', '') or '') == to]
        return []

    # ══════════════════════════════════════════════════════════
    #  「说了一样的话」→ 先问他是不是非说不可（2026-10-07）
    # [EN] "Said the same thing" → first ask whether he really has to say it (2026-10-07)
    # ══════════════════════════════════════════════════════════
    def _repeat_hit(self, name: str, line: str) -> bool:
        """这句话他说过了吗 —— 两种模式用**同一个问法**。

        · 剧本模式：问 `SceneBuilder`（**与去重护栏同源**）；
        · prose 模式：翻「场上刚发生」缓冲（那一支没有护栏，缓冲就是它的账）。

        ⚠ 剧本模式下**不能**退回缓冲：那本账只有 8 条，隔几拍说的重复句
          早就滚出去了 —— 那样"必须重复"永远判不出来，护栏照样一句不留地丢。
        
                English:
        Has he said this line before -- both modes use the **same question**.
                · Script mode: ask `SceneBuilder` (**same source as the dedup guardrail**);
                · prose mode: look through the "just happened on stage" buffer (that branch has no guardrail, the buffer is its ledger).
                ⚠ In script mode, **cannot** fall back to the buffer: that ledger only has 8 entries, and after a few beats the repeated lines
                  have long since rolled out -- that way "must repeat" can never be determined, and the guardrail still drops every single line.
        """
        n = str(name or '').strip()
        t = str(line or '').strip()
        if not (n and t):
            return False
        b = getattr(self, '_builder', None)
        if b is not None and hasattr(b, 'already_said'):
            try:
                return bool(b.already_said(n, t))
            except Exception:                                    # noqa: BLE001
                return False
        if self._script_mode:
            # 剧本模式、但台账还没建 —— 只可能是**第一拍**（`_said` 是在第一拍的
            # `_process_actions` 里写进去的）。那时他不可能"说过"任何话。
            # ⚠ **不要在这里 `_ensure_builder()`**：那会让 `_last_clock` /
            #   `_last_place` 提前一拍定基准，分幕跟着偏（2026-10-07 实测：
            #   这么写之后 `verify_script_output` 的端到端那条判据开始偶发变红）。
            # [EN] Script mode, but the ledger has not been created yet —— it can only be the **first beat**
            # [EN] (`_said` is in the first beat's
            # [EN] `_process_actions`). At that point he cannot have "said" anything.
            # [EN] ⚠ **Do not `_ensure_builder()` here**: that would make `_last_clock` /
            # [EN] `_last_place` set their baseline one beat early, and the act division shifts along with it
            # [EN] (2026-10-07 measured:
            # [EN] after writing it this way, the end-to-end criterion of `verify_script_output` started
            # [EN] intermittently turning red).
            return False
        # prose 模式：翻「场上刚发生」缓冲（那一支没有护栏，缓冲就是它的账）
        # [EN] prose mode: flip through the "just happened on stage" buffer (that branch has no guardrail, the
        # [EN] buffer is its ledger)
        # ★ 2026-10-18：判**近似**，不只判一字不差 —— 用的是剧本模式那同一个
        #   `near_same`（两处各写一套"像不像同一句"，迟早一边松一边紧）。
        # [EN] ★ 2026-10-18: judge **near** duplicates, not only verbatim -- using the same
        # [EN] `near_same` as script mode (two hand-rolled similarity rules will drift apart).
        try:
            from display.scene_builder import near_same as _near_same
        except Exception:                                        # noqa: BLE001
            _near_same = None
        for r in reversed(list(getattr(self.world, 'recent_lines', None) or [])):
            if str(r.get('kind') or '') != 'speak':
                continue
            if str(r.get('who') or '').strip() != n:
                continue
            prev = str(r.get('text') or '').strip()
            if prev == t or (_near_same is not None and _near_same(prev, t)):
                return True
        return False

    def _must_repeat_reason(self, name: str, line: str) -> str:
        """这句"原样再说一遍"算不算**非说不可**；算就返回理由，不算返回空串。

        `_REPEAT_CTX` 给模型的三条标准，这里**逐条落到代码上**：
          ① **对方没听见**：他说完这句之后，有人问过"你说什么 / 没听清 / 再说一遍"；
          ② **在追问**：他说完这句之后，对方（或同一场景里的人）抛了一个问句；
          ③ **只有这一种说法**：不判 —— 判不了就不许拿它当放行理由。
        ⚠ 三条都查不到 ⇒ 返回空串（**不许无条件放行**）。
          实测代价：`snow_thread3` 里同一句隔十句原样重现，读者一眼看出是没话找话。

        ⚠ 只看**这句之后**的行（之前的追问跟"再说一遍"没关系）。
        ⚠ 三条都读 `world.recent_lines`（场上公开的那本账），不另立数据源。
        [EN] Does repeating this line verbatim count as **must say**? Return the reason, else "".
        [EN] The three criteria in `_REPEAT_CTX` are implemented here one by one: ① they did not
        [EN] hear (someone asked "what did you say / didn't catch that" after this line); ② they are
        [EN] pressing (a question was thrown after it); ③ "only one way to say it" -- **not judged**;
        [EN] if it cannot be judged it cannot justify a pass. Empty result = **no unconditional
        [EN] pass** (measured cost: the same line resurfacing ten lines later reads as filler).
        """
        me = str(name or '').strip()
        t = str(line or '').strip()
        if not me or not t:
            return ''
        rows = list(getattr(self.world, 'recent_lines', None) or [])
        # 从**最后**往里找这句自己，只看它之后的行（最多 4 条，太远就不算）
        start = -1
        for i in range(len(rows) - 1, -1, -1):
            r = rows[i]
            if str(r.get('kind') or '') != 'speak':
                continue
            if str(r.get('who') or '').split('（', 1)[0].strip() != me:
                continue
            if str(r.get('text') or '').strip() == t:
                start = i
                break
        if start < 0:
            return ''
        after = [r for r in rows[start + 1:] if str(r.get('kind') or '') == 'speak'][:4]
        _DEAF = ('没听清', '听不清', '你说什么', '什么？', '什么?', '再说一遍',
                 '再说一次', '大点声', '没听见')
        for r in after:
            who = str(r.get('who') or '').split('（', 1)[0].strip()
            txt = str(r.get('text') or '').strip()
            if who == me:
                continue
            if any(k in txt for k in _DEAF):
                return f'{who} 没听清'
            if txt.endswith('？') or txt.endswith('?') or any(
                    k in txt for k in ('吗', '呢', '什么', '怎么', '为什么')):
                return f'{who} 在追问'
        return ''

    def _free_repeat(self, name: str, line: str) -> None:
        """放行一句"必须重复"的台词（登记进护栏的放行名单 `_forced`）。

        prose 模式没有护栏 → 什么都不用做（它本来就不会丢）。
        
                English:
        Allow a "must repeat" line through (register it in the guardrail's allow list `_forced`).
                prose mode has no guardrail -> nothing to do (it never drops anything anyway).
        """
        b = getattr(self, '_builder', None)
        if b is None or not hasattr(b, 'allow_repeat'):
            return
        try:
            b.allow_repeat(name, line)
        except Exception as e:                                   # noqa: BLE001
            self._warn_once('allow_repeat', f"放行重复台词失败（不影响推演）：{e!r}")

    #: 重说时给的那句话 —— 会进提示词的「当前情况」那一格（`Agent.decide(context)`）。
    #: 重点是**先让他重新想清楚场上的情况**（用户原话），而不是简单地下禁令；
    #: 并且**明确给出"非说不可"的判定标准**，这样"必须"是他自己认下来的。
    #: 开头点明这是**开口之前的又一次盘算** —— 用户要的是"重说，但别真的说出来"：
    #: 这一趟只在脑子里过，外面（别的角色、观众）只看得见最后那一句。
    # [EN] : The line given on re-say —— will go into the "current situation" slot of the prompt
    # [EN] (`Agent.decide(context)`).
    # [EN] : The point is **first make him rethink the situation on stage clearly** (the user's own words),
    # [EN] not simply issue a prohibition;
    # [EN] : and **explicitly give the criterion for "must say it"**, so that the "must" is something he
    # [EN] acknowledges himself.
    # [EN] : Open by making clear this is **another deliberation before speaking** —— what the user wants
    # [EN] is "re-say, but do not actually say it out":
    # [EN] : This round only runs through his head, the outside (other characters, the audience) only sees
    # [EN] the final line.
    _REPEAT_CTX = (
        "（这是你开口之前的又一次盘算，别人听不见。）你刚说过「{line}」—— "
        "先重新想清楚现在场上的情况：这句话是不是非说不可？"
        "（对方没听见、你在追问、或这话只有这一种说法 —— 那就算非说不可。）"
        "**如果不是非说不可，就换一句真正接得上眼前这场戏的话**；"
        "如果确实必须再说一遍，就还按这一句说。"
    )

    async def _self_review(self, agent: Agent, action: Action) -> Action:
        """**台词自省**（反思链的"执行 → 反思 → 优化"落在台词上）。

        用户 2026-10-07：「让整个演戏流程更加接近真实世界的句子」。

        与 `_review_repeat` 的分工（两者都是"说出口之前先问一遍"，
        但问的**不是同一件事**）：

        | | `_review_repeat` | 本方法 |
        |---|---|---|
        | 什么时候问 | 这一句**和他说过的话重复**了 | 这一句**明显不像人在场上说的** |
        | 判据 | `_repeat_hit`（历史台词比对） | `cognition.unnatural_reason`（规则）|
        | 问什么 | "是不是非说不可？" | "这真是他会从嘴里说出来的话吗？" |
        | 开关 | `DIALOGUE_RETRY_DUP` | `ACTOR_SELF_REVIEW`（总闸 `COGNITION`）|
        | 预算 | `_retry_left` | `_review_left` |

        为什么不合成一个方法：两条判据的触发面完全不同（重复 vs 不像人话），
        合成之后任一条的开关都会连带管住另一条 —— 那正是"两个开关共用一个
        计数器"那类踩过的坑（见 `director/day_plan.compose` 里那段说明）。

        ⚠ **保持原话是对的**：真有非说不可的理由就原样说。所以这里和后一条一样，
          只在"改了"时记 INFO，"坚持"时**什么都不做**（他有权坚持）。

        ⚠ **判据在规则里先粗筛**（`unnatural_reason`）：演出一拍里 1~2 个人说话，
          每句都问一次模型 = 每拍多一次调用。只把**规则挑出来的那一小撮**送去自省，
          所以正常对白**一次额外调用都不花**（这也是"关掉就逐字退回"的事实基础）。
        
                English:
        **Line self-review** (the reflection chain's "execute -> reflect -> optimize" applied to lines).
                User 2026-10-07: "Make the whole acting flow closer to real-world sentences."
                Division of labor with `_review_repeat` (both are "ask once before saying it out loud",
                but they are **not asking the same thing**):
                | | `_review_repeat` | this method |
                |---|---|---|
                | When to ask | this line **duplicates what he has said** | this line **clearly doesn't sound like something said on stage** |
                | Criterion | `_repeat_hit` (historical line comparison) | `cognition.unnatural_reason` (rules) |
                | What is asked | "Must it be said?" | "Is this really something he would say?" |
                | Switch | `DIALOGUE_RETRY_DUP` | `ACTOR_SELF_REVIEW` (master switch `COGNITION`) |
                | Budget | `_retry_left` | `_review_left` |
                Why not merge into one method: the two criteria have completely different trigger surfaces (duplicate vs unnatural),
                and after merging, either one's switch would also govern the other -- that is exactly the kind of pitfall
                of "two switches sharing one counter" that has been hit before (see the explanation in `director/day_plan.compose`).
                ⚠ **Keeping the original line is correct**: if there really is a reason it must be said, say it as-is. So here, same as the next item,
                  only log INFO when "changed", and **do nothing** when "insisting" (he has the right to insist).
                ⚠ **The criterion is first coarsely filtered by rules** (`unnatural_reason`): in one beat of performance, 1~2 people speak,
                  and asking the model about every line = one extra call per beat. Only the **small handful picked out by the rules** is sent to self-review,
                  so normal dialogue **costs not a single extra call** (this is also the factual basis for "turn it off and it reverts word for word").
        """
        if self._review_left <= 0:
            return action
        if str(getattr(action, 'verb', '') or '') != 'speak':
            return action
        line = str(getattr(action, 'dialogue', '') or '').strip()
        name = str(getattr(agent, 'name', '') or '').strip()
        if not (name and line):
            return action
        try:
            from crew import cognition as COG
            why = COG.unnatural_reason(line)
        except Exception:                                        # noqa: BLE001
            return action
        if not why:
            return action                    # 这句没问题 → 一次调用都不花
            # [EN] This line is fine → spends not a single call
        self._review_left -= 1
        ctx = (COG.ACTOR_REVIEW_CTX.format(line=line, name=name)
               + f'\n（具体是：{why}。）')
        # ★ 把他**刚才的盘算**一并递回去（思维链的二次利用）：
        #   不带这一段的话，他"重新想一遍"往往还是绕回同一个说法 ——
        #   带上之后他看得见自己上一遍是怎么想的，才改得动。
        # [EN] ★ Pass back his **just-now deliberation** along with it (second use of the chain of thought):
        # [EN] Without this passage, his "rethink it" often still loops back to the same phrasing ——
        # [EN] with it he can see how he thought last time, and only then can he change it.
        trace = str(getattr(action, 'think_trace', '') or '').strip()
        if trace:
            ctx += f'\n（你刚才的盘算是：「{trace[:80]}」—— 现在重新想一遍，别照抄。）'
        try:
            again = await agent.decide(ctx)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning("「%s」自省时决策失败，保留原句：%r", name, e)
            return action
        new_verb = str(getattr(again, 'verb', '') or '')
        new_line = str(getattr(again, 'dialogue', '') or '').strip()
        if new_verb == 'speak' and new_line:
            if new_line != line:
                _LOG.info('「%s」这句不像人话（%s）→ 自省后改成：%s',
                          name, why, new_line[:24])
            return again
        if new_verb == 'speak':
            # 说"要说"却没给台词 —— 当成"想了之后不说了"。别把原来那句塞回去。
            # [EN] Says "will say" but gives no line —— treat as "thought about it and then did not say it". Do not
            # [EN] stuff the original line back.
            return Action(verb='wait', reason='（自省后决定不说）')
        # 他换了**别的动作**（干脆不说了 / 去做别的事）—— 尊重这一遍
        # [EN] He switched to **another action** (simply stopped saying it / went to do something else) ——
        # [EN] respect this round
        _LOG.info('「%s」这句不像人话（%s）→ 自省后改成：%s', name, why, new_verb)
        return again

    async def _review_repeat(self, agent: Agent, action: Action) -> Action:
        """他说的这句已经说过 —— 先问他是不是非说不可。

        用户 2026-10-07：「如果说了一样的话，你要看下是不是必须，如果不是
        必须重复，就让人物重新想清楚当前情况，重新说话」。

        以前这里只有"丢"：重复句被护栏拦下，那一拍于是可能**整拍空白**
        （对照探针里就是这样 —— 桩反复说同一句，A 段第 3 拍起全空）。

        现在分三步：
          ① **口语应答**（"嗯""……"）→ 直接放行（人本来就会重复这些）；
          ② 其余 → 带上"你刚才说过这句"**重新决策一次**：
             · 换了话 → 用新话（这就是"重新想清楚、重新说话"）；
             · **仍坚持原话 → 那就是"必须重复"**，登记放行；
          ③ 开关关掉 / 这一拍的预算用完 / 重说抛异常 → 退回老行为（丢弃）。

        返回**这一拍真正要用**的动作（重说成功就是新的那条）。
        
                English:
        This line he said has already been said -- first ask him whether it must be said.
                User 2026-10-07: "If the same thing is said, you need to check whether it is necessary; if it is not
                a necessary repetition, have the character rethink the current situation and speak again."
                Previously there was only "drop" here: repeated lines were stopped by the guardrail, and that beat could then be **entirely blank**
                (this is how it is in the comparison probe -- the stub repeatedly says the same line, and from beat 3 onward section A is all blank).
                Now it is split into three steps:
                  ① **Conversational responses** ("mm", "...") -> let through directly (people repeat these anyway);
                  ② the rest -> with "you just said this line" **make the decision again**:
                     · changed the line -> use the new line (this is "rethink and speak again");
                     · **still insists on the original line -> then it is a "must repeat"**, register and let through;
                  ③ switch off / budget for this beat used up / re-say throws an exception -> fall back to old behavior (drop).
                Return the action **this beat will actually use** (if the re-say succeeded, it is the new one).
        """
        if not CFG.b('DIALOGUE_RETRY_DUP'):
            return action
        if str(getattr(action, 'verb', '') or '') != 'speak':
            return action
        line = str(getattr(action, 'dialogue', '') or '').strip()
        name = str(getattr(agent, 'name', '') or '').strip()
        if not (name and line):
            return action
        if is_short_reply(line):
            return action                    # ① 口语应答，重复说没关系
            # [EN] ① Spoken reply, repeating it does not matter
        if not self._repeat_hit(name, line):
            return action                    # 没重复 → 什么都不用做
            # [EN] Not repeated → nothing to do
        # ★★ **重复台词也是僵局的一种**（2026-10-19 真跑实证）：
        #   岛村一句「嗯，你是个好人。」一字不差说了 **5 次** —— 每一次都被
        #   "重说 → 还是这句 → 非说不可，放行"，于是整场戏在这个话题上打转。
        #   光看 `wait` 判不出这种卡法，所以在这里**记一笔**，由 `stall_beats` 汇总。
        #   ⚠ 记的是"撞上已说过的话"的人次（不是次数）：同一拍三个人都说老话 = 3，
        #     那才说明这场戏没新话可说。
        # [EN] ★★ **Repeated dialogue is also a deadlock** (measured 2026-10-19): one line said
        # [EN] verbatim five times -- each time "rethink -> still the same -> let it pass as
        # [EN] unavoidable", so the scene circled one topic. Counting `wait` alone cannot see this.
        self._dup_speaks += 1
        budget = int(getattr(self, '_retry_left', 0) or 0)
        if budget <= 0:
            # 预算用完（这一拍已经有别人重说过）→ 老行为：让它被护栏丢掉。
            # ⚠ 留一条 INFO：不然"某个人又被丢了"这件事没有任何痕迹。
            # [EN] Budget exhausted (someone else already re-said in this beat) → old behavior: let it be dropped
            # [EN] by the guardrail.
            # [EN] ⚠ Keep one INFO line: otherwise "someone was dropped again" leaves no trace at all.
            _LOG.info('「%s」这句已经说过，本拍重说预算用完 —— 照旧不重复上屏',
                      name)
            return action
        self._retry_left = budget - 1
        # ★ 把他**开口之前那几句盘算**一并递回去（2026-10-07 第七轮）：
        #   他"重新想清楚情况"时看得见自己上一遍是怎么想的，才改得动；
        #   不然多数情况只是把同一句换个语气说一遍。拿不到盘算就不加这一段。
        # [EN] ★ Pass back his **deliberation before speaking** along with it (2026-10-07 seventh round):
        # [EN] When he "rethinks the situation clearly" he can see how he thought last time, and only then can
        # [EN] he change it;
        # [EN] otherwise in most cases he just says the same line in a different tone. If the deliberation is
        # [EN] unavailable, do not add this passage.
        _ctx = self._REPEAT_CTX.format(line=line)
        _trace = str(getattr(action, 'think_trace', '') or '').strip()
        if _trace:
            _ctx += (f'\n（你开口前的盘算是：「{_trace[:80]}」—— '
                     f'现在重新盘算一遍，别照抄上一遍。）')
        try:
            again = await agent.decide(_ctx)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning("「%s」重说时决策失败，保留原句：%r", name, e)
            return action
        new_verb = str(getattr(again, 'verb', '') or '')
        new_line = str(getattr(again, 'dialogue', '') or '').strip()
        if new_verb == 'speak' and new_line:
            if new_line != line:
                _LOG.info('「%s」同一句说了两遍 → 重新想过，改成：%s',
                          name, new_line[:24])
            # ⚠ 他"想清楚之后"给的这句**也可能是一句说过的话**（台词池小的场合
            #   很容易：他只有那么几句话，绕一圈又说回来了）。这一段
            #   就是**必须重复**的判定 —— 已经问过一遍了，不再问第二遍
            #   （再问就是循环），登记放行。
            #   · 新句 == 原句 → 他坚持，放行（"非说不可"）
            #   · 新句是**别的**说过的句 → 他换过了，只是还是老话，同样放行
            # [EN] ⚠ The line he gives "after thinking it through" **may also be a line already said** (in cases
            # [EN] with a small line pool
            # [EN] it is very easy: he only has those few lines, and after going around he comes back to it). This
            # [EN] passage
            # [EN] is the criterion for **must repeat** —— it has already been asked once, do not ask a second time
            # [EN] (asking again is a loop), register and let it pass.
            # [EN] · New line == original line → he insists, let it pass ("must say it")
            # [EN] · New line is a **different** already-said line → he has changed it, just still an old phrase,
            # [EN] likewise let it pass
            if new_line == line or self._repeat_hit(name, new_line):
                # ★★★ 2026-10-19 第五轮：**先核对"非说不可"的三个条件，再放行**。
                #
                #   改之前是**无条件放行**：只要"重问一次还是这句"就当作用户说的
                #   "非说不可"。实测（《雪国》`snow_thread3`，24 拍）：
                #   驹子的「你就不能……多留些日子吗？」原样说了 **两次**，
                #   中间隔了十句 —— 那不是"非说不可"，是**模型没别的话可说**。
                #   而 `_REPEAT_CTX` 里给模型的三条标准（对方没听见 / 在追问 /
                #   只有这一种说法）**代码一条都没查**：prompt 里写了 ≠ 生效。
                #
                #   ⇒ 现在改成：满足三条之一才放行，否则**这一句丢掉**，
                #     退回"做点别的"。这是本项目记过的处置方式 ——
                #     可数的事实能判就判，判不了就不许无条件放行。
                # [EN] ★★★ Round five: **check the three "must say" conditions before letting it
                # [EN] through**. Before, it was unconditional: "asked again, still the same" counted
                # [EN] as the user's "must say it". Measured (`snow_thread3`, 24 beats): one line was
                # [EN] said **twice**, ten lines apart -- that is not "must say", it is "nothing else
                # [EN] to say". And the three criteria in `_REPEAT_CTX` (they did not hear / they are
                # [EN] pressing / there is only one way to say it) were **never checked in code**.
                # [EN] Now: let it through only if one of the three holds; otherwise drop the line
                # [EN] and fall back to doing something.
                _why = self._must_repeat_reason(name, line)
                if _why:
                    self._free_repeat(name, new_line)
                    _LOG.info('「%s」重说之后仍是这句，且符合「非说不可」（%s）—— 放行',
                              name, _why)
                else:
                    _LOG.info('「%s」重说之后仍是这句，但**对方既没追问也没说没听清**'
                              '—— 不算非说不可，这一句丢掉', name)
                    return Action(verb='wait', reason='（这句说过，对方也没追问 —— 不说了）')
            return again
        if new_verb == 'speak':
            # 说"要说"却没给台词 —— 当成"想了之后不说了"。别把原来那句塞回去。
            # [EN] Says "will say" but gives no line —— treat as "thought about it and then did not say it". Do not
            # [EN] stuff the original line back.
            return Action(verb='wait', reason='（重说后决定不说）')
        # 他换了**别的动作**（干脆不说了 / 改成做别的事）——
        # 这就是"重新想清楚当前情况"的结果，尊重这一遍。
        # ⚠ 返回 `again` 而不是原句：第一遍那句**从此不存在**（没上屏、没进缓冲
        #   —— 这一步是内部盘算，见 `_tick` 里的注释）。
        # [EN] He switched to **another action** (simply stopped saying it / changed to doing something else)
        # [EN] ——
        # [EN] this is the result of "rethinking the current situation clearly", respect this round.
        # [EN] ⚠ Return `again` instead of the original line: the first-round line **ceases to exist** from
        # [EN] then on (not shown on screen, not entered into the buffer
        # [EN] —— this step is internal deliberation, see the comment in `_tick`).
        _LOG.info('「%s」同一句说了两遍 → 重新想过，改成：%s', name, new_verb)
        return again

    async def _process_action(self, agent: Agent, action: Action) -> None:
        """处理一个 Agent 的行动（prose 模式）。

        ★ 2026-10-07：**说话不在这一层复述台词**。
          以前这里是 `desc = f"{agent.name}{_verb_desc(action)}"`，`_verb_desc`
          对 speak 给的是 `对阿枝说：今夜别出门。` —— 旁白先把台词讲了一遍，
          紧接着下面的 `talk()` 又让角色自己把同一句说了一遍（用户报的
          「把人物说的话讲一遍，然后人物自己再说一遍，很诡异」就是这个）。
          现在：有对话对象 → 台词只由 `talk()` 给；没有对象（对方不在场）
          → 用**台词的样子**写出来，也不复述。
        
                English:
        Handle one Agent's action (prose mode).
                ★ 2026-10-07: **speaking does not restate the line at this layer**.
                  Previously this was `desc = f"{agent.name}{_verb_desc(action)}"`, and `_verb_desc`
                  for speak gave `say to Azhi: don't go out tonight.` -- the narration first told the line once,
                  and then the `talk()` below had the character say the same line again himself (what the user reported
                  as "it tells what the character said, then the character says it again himself, very weird" is exactly this).
                  Now: if there is a dialogue target -> the line is given only by `talk()`; if there is no target (the other party is not present)
                  -> write it **in the form of a line**, also without restating.
        """
        other = None
        if action.verb == "speak" and action.target:
            p = self.world.get_person(action.target)
            if p is not None and p.is_active():
                other = p

        if action.verb == "speak" and action.dialogue:
            if other is None:
                # 没有能接话的人 → 这句话只有这一个出口
                # [EN] No one who can pick up the conversation → this line has only this one outlet
                said = f"{agent.name}：{action.dialogue}"
                self._push_narrative(said, 1, kind=S.DIALOGUE)
                self._daily_narrative.append(said)
                # prose 模式没有剧本词条可读（`_note_entry` 是剧本模式那条路），
                # 所以这一句要**在这里**记 —— 它是真的说出口了的。
                # [EN] prose mode has no script entry to read (`_note_entry` is the script-mode path),
                # [EN] so this line must be recorded **here** —— it was really spoken out loud.
                self.world.note_line(agent.name, action.dialogue,
                                     kind='speak', to=action.target or '')
        else:
            desc = f"{agent.name}{_verb_desc(action)}"
            self._push_narrative(desc, 3, kind=S.ACTION)
            self._daily_narrative.append(desc)
            # ⚠ **不要在这里记 `world.note_line`**（2026-10-14 试过，又撤了）：
            #   调用方 `_process_actions` 在进这个函数**之前**已经调过
            #   `_note_stage_line(agent, action)`（那是"场上刚发生"的**唯一汇聚点**），
            #   在这里再记一次会把同一个动作写两遍 ——
            #   而那张桌面只有 6 条，写重一条就挤掉一条别人的信息。
            #   ⇒ "让动作进桌面"这件事要改**汇聚点**，不是在这里加一处
            #     （见 `_note_stage_line`）。
            # [EN] ⚠ **Do not record `world.note_line` here** (tried on 2026-10-14, then reverted):
            # [EN] the caller `_process_actions` already calls `_note_stage_line(agent, action)`
            # [EN] **before** entering this function (that is the **single convergence point** for
            # [EN] "just happened on stage"); recording again here would write the same action twice
            # [EN] -- and that table only holds 6 entries, so a duplicate squeezes out someone else's
            # [EN] information. => "Let actions into the table" must change the **convergence point**,
            # [EN] not add a second spot here (see `_note_stage_line`).

        # 对话触发
        # [EN] Dialogue trigger
        if other is not None:
            lines = await agent.talk(action.target, topic=action.dialogue)
            # ⚠ 轮流归属用 `enumerate`，不用 `lines.index(line)`
            #   （同一句话出现两次时 `index` 永远返回第一个的下标，
            #    两句会都算在开口那一方头上）。
            # [EN] ⚠ Use `enumerate` for turn attribution, not `lines.index(line)`
            # [EN] (when the same line appears twice `index` always returns the subscript of the first,
            # [EN] and both lines would be counted against the side that spoke).
            for i, line in enumerate(lines):
                who = action.target if i % 2 else agent.name
                self._push_narrative(f"{who}：{line}", 1, kind=S.DIALOGUE)
                self._daily_narrative.append(f"{who}：{line}")
                # ★ 多轮对话的每一句都要进「场上刚发生」（2026-10-07）：
                #   这一段是**往来**，只记第一句的话，后面的人接话时会
                #   缺掉一半上下文（而且 `talk()` 产出的台词在 prose 模式下
                #   不经过 `_note_stage_line`，那里只看得见 `Action.dialogue`）。
                # [EN] ★ Every line of a multi-turn dialogue must enter "just happened on stage" (2026-10-07):
                # [EN] This passage is **back-and-forth**; recording only the first line means when later people pick
                # [EN] up the conversation they will
                # [EN] be missing half the context (and moreover the lines produced by `talk()` in prose mode
                # [EN] do not pass through `_note_stage_line`, which can only see `Action.dialogue`).
                self.world.note_line(
                    who, str(line).strip().strip('「」'), kind='speak',
                    to=(action.target if i % 2 == 0 else agent.name))

        # 反思（概率触发）
        # [EN] Reflection (probability-triggered)
        if random.random() < 0.05:
            reflection = await agent.reflect()
            if reflection:
                self._push_narrative(f"【内心·{agent.name}】{reflection}", 2,
                                     kind=S.ASIDE)
                self._daily_narrative.append(f"【内心·{agent.name}】{reflection}")

    # ── 后台批次（`BACKGROUND_MODE`，2026-10-06）──────────────────────
    # [EN] ── Background batch (`BACKGROUND_MODE`, 2026-10-06) ──────────────────────
    def _mentioned_names(self, actions: list[tuple[Agent, Action]]) -> set[str]:
        """这一拍的动作里**提到了哪些后台人物**（台词 / 目标 / 理由里出现名字）。

        为什么要它：升格的两条路里，"被点名"比"地点对得上"更准 ——
        剧情里有人喊「去把掌柜请来」，那就是真的需要他上台；
        而"地点对得上"只是地理巧合。判据取**子串命中**（中文没词边界），
        但只在**后台名册**里找，所以不会把常见词误当成名字。
        
                English:
        Which background characters are **mentioned** in this beat's action (names appear in the line /
        goal / reason).
                Why we need this: of the two paths to promotion, "being named" is more accurate than "location matching" --
                if someone in the story calls out "go bring the shopkeeper here", then he really is needed on stage;
                whereas "location matching" is just geographic coincidence. The criterion uses **substring hits** (Chinese has no word boundaries),
                but only searches the **backstage roster**, so common words won't be mistaken for names.
        """
        names = {a.name for a in self._backstage.backstage_people()}
        if not names:
            return set()
        blob = ""
        for _agent, act in actions:
            blob += " ".join(str(getattr(act, k, "") or "")
                             for k in ("target", "dialogue", "inner_thought", "reason"))
        return {n for n in names if n and n in blob}

    async def _maybe_group_chat(self) -> None:
        """三人以上同场时的**群聊轮转**（设计稿 §五）。

        为什么需要它：前台步进每拍只挑 1~2 个人决策 —— 三个人在屋里时，
        第三个人**永远轮不上**（表现成"他在场但像个摆设"）。这里补的正是那一档：
        按 `GROUP_CHAT_MAX` 封顶叫人，每人**一句**，最多两轮。

        成本闸门（三个都过才跑，别让它变成隐形烧钱）：
          · 在场 ≥ 3 人；· `GROUP_CHAT_MAX ≥ 3`；· 概率 0.06。
        
                English:
        **Group chat rotation** when three or more people are in the same scene (design doc §5).
                Why we need this: the foreground step picks only 1~2 people to decide each beat -- when three people are in the room,
                the third person **never gets a turn** (manifesting as "he's present but just decoration"). This fills exactly that gap:
                cap the call-ups by `GROUP_CHAT_MAX`, each person gets **one line**, at most two rounds.
                Cost gates (all three must pass to run, don't let it become invisible money burn):
                  · present >= 3 people; · `GROUP_CHAT_MAX >= 3`; · probability 0.06.
        """
        limit = CFG.i('GROUP_CHAT_MAX')
        if limit < 3:
            return
        on_stage = [a for a in self.agents if self.world.is_on_stage(a.ps)]
        if len(on_stage) < 3:
            return
        if self._rng.random() >= 0.06:
            return
        picked = self._rng.sample(on_stage, min(limit, len(on_stage)))
        heard: list[str] = []
        self._status('group_chat', n=len(picked))
        from display import story_render as _STR
        for a in picked:
            others = [x.name for x in picked if x is not a]
            line = await a.speak_in_group(others, heard, topic=self.world.scene)
            if not line:
                continue
            heard.append(f"{a.name}：{line}")
            # ★ 群聊也是"场上刚发生"的一部分（2026-10-07）：不记的话，
            #   群聊轮转里说的话在下一拍的决策 prompt 里看不到 ——
            #   而群聊正是"多人在场、该互相接话"的场合。
            #   `to` 留空 = 说给场上的大家听（`recent_text` 会写成「X：…」）。
            # [EN] ★ Group chat is also part of "just happened on stage" (2026-10-07): if not recorded,
            # [EN] things said in the group chat rotation are invisible in the next beat's decision prompt ——
            # [EN] and group chat is exactly the occasion where "multiple people are present and should pick up
            # [EN] each other's conversation".
            # [EN] `to` left empty = said to everyone on stage (`recent_text` will be written as "X: ...").
            self.world.note_line(a.name, str(line).strip(), kind='speak')
            # ★ 台词就是台词 —— **不再拼成"某某说：「…」"那种旁白复述**
            #   （用户 2026-10-07：「把人物说的话讲一遍，然后人物自己再说一遍，
            #   很诡异」）。剧本模式下走 `SceneBuilder.observe_speech()`：
            #   与前台步进同一个出口，因此那条去重护栏（同一句只说一次）
            #   对它同样生效，而且**落盘的剧本里也有这一句**（以前只在中栏）。
            # [EN] ★ A line is a line —— **no longer assembled into narration retelling like "so-and-so said:
            # [EN] '...'"**
            # [EN] (user 2026-10-07: "repeat what the character said, then the character says it again himself,
            # [EN] Very strange"). In script mode it goes through `SceneBuilder.observe_speech()`:
            # [EN] It shares the same exit as the foreground step, so that dedup guardrail (say the same line only
            # [EN] once)
            # [EN] also applies to it, and **the line is also in the persisted script** (previously only in the
            # [EN] middle column).
            if self._script_mode:
                entry = self._ensure_builder().observe_speech(a.name, line)
                if entry is None:          # 同一句已经说过了 → 不重复推
                # [EN] The same line has already been said -> do not push it again
                    continue
            else:
                entry = S.dialogue(a.name, line)
            self._push_narrative(_STR.sentence(entry), 1, kind=S.DIALOGUE)
            self._daily_narrative.append(f"{a.name}：{line}")

    async def _run_backstage(self) -> None:
        """后台批次到点就跑一批（`sim/backstage.py`）。

        ⚠ 整段包 try：**后台是加分项，不是主流程** —— 它出岔子不该让推演停下。
        但失败要说一声（批次器自己会 `_warn` 一次，走 `on_warn` 通道推给界面），
        不许悄悄没有。
        
                English:
        The backstage batch runs once when its time comes (`sim/backstage.py`).
                ⚠ Wrap the whole thing in try: **backstage is a bonus, not the main flow** -- its failure shouldn't stop the simulation.
                But failures must be reported (the batcher itself calls `_warn` once, pushed to the UI via the `on_warn` channel),
                they must not silently vanish.
        """
        mention = set(self._pending_mention)
        self._pending_mention = set()
        try:
            if not self._backstage.due():
                return
            self._status('backstage', n=len(self._backstage.backstage_people()))
            news = await self._backstage.run_batch(mention)
            for line in news:
                self._push_narrative(line, 2, kind=S.NOTE)
        except Exception as e:                                  # noqa: BLE001
            self._warn_once('backstage', f"后台批次出错（不影响推演）：{e!r}")

    # ── 客流与群演（外部输入，2026-10-06）────────────────────────────
    # [EN] -- Foot traffic and extras (external input, 2026-10-06) --------------------
    async def _sync_crowd(self, tick_num: int = 0) -> None:
        """每拍对一次「门外行情」：补/减背景群演 · 按缺口造功能群演 · 到期回收。

        为什么要有这一步：**空转的根因是"没有外部输入"**。真机跑《临河茶肆》的日志里
        「买 0、顾客 0、客人 20」，茶楼没生意，人物只能互相内循环
        （看 627 次、擦 565 次）。有客人，才有事；有事，人物才有得选。

        ★★ 2026-10-07：功能群演**改由剧组里「群众演员」那一职位投人**
          （`crew/agents.ExtraCasting`）。以前是从一张写死的池子里抽的 ——
          同一个茶楼里每一个讨债的人说同一句话，输入很快就成了**罐头**
          （人物学会无视它们，等于没有输入）。
          规则池留着当兜底：拿不到 AI 就照旧抽一个（门外不能空着）。

        ⚠ 整段包在 try 里：**客流是加分项，不是主流程** —— 它出岔子不该让推演停下，
        但**要说一声**（`_warn_once`），不能悄悄没了。

        ⚠ `tick_num` 是**必传**的（`exit_notice` 的冷却要按拍算）。
        以前这里引用了一个不存在的 `tick_num` → 每拍都抛 `NameError`、
        被下面那个 `except` 吞成一行 warning —— 于是**退场播报整段是死代码**
        （而它正是用户 2026-10-07 报的"对话又死循环"的修复）。教训同 `_warn_once`：
        **宽 except 会把"完全没跑"伪装成"跑过了"**，所以这条链要有判据看着。
        
                English:
        Each beat, sync the "market outside the door": add/remove background extras · spawn functional
        extras by shortfall · recycle on expiry.
                Why this step is needed: **the root cause of idle spinning is "no external input"**. In the real-device log of running "临河茶肆",
                "buy 0, customer 0, guest 20" -- the teahouse has no business, so the characters can only loop among themselves
                (look 627 times, wipe 565 times). With guests, there is business; with business, the characters have choices.
                ★★ 2026-10-07: functional extras are now **cast by the "群众演员" role in the crew**
                  (`crew/agents.ExtraCasting`). Previously they were drawn from a hardcoded pool --
                  every debt collector in the same teahouse said the same line, and the input quickly became **canned**
                  (characters learned to ignore them, equivalent to no input at all).
                  The rule pool stays as a fallback: if AI is unavailable, draw one as before (the door can't be empty).
                ⚠ Wrap the whole thing in try: **customer flow is a bonus, not the main flow** -- its failure shouldn't stop the simulation,
                but it **must be reported** (`_warn_once`), it must not silently vanish.
                ⚠ `tick_num` is **required** (the `exit_notice` cooldown is counted per beat).
                Previously this referenced a nonexistent `tick_num` -> it threw `NameError` every beat,
                swallowed by the `except` below into a single warning line -- so **the entire exit broadcast was dead code**
                (and it was precisely the fix for the "dialogue loops forever again" reported by the user on 2026-10-07). Same lesson as `_warn_once`:
                **a broad except disguises "never ran" as "ran"**, so this chain needs a criterion watching it.
        """
        try:
            from world import crowd as _crowd
            _crowd.sync_crowd(self.world, self._rng)
            # 功能群演（"有事的那个"）：来的人多时**偶尔**来一个。
            # 频率交给随机 + 预算闸门（`EXTRAS_DAILY_BUDGET`），不按固定拍数 ——
            # 固定拍数会让"每 4 拍必有人讨债"这种机械节奏出现。
            # [EN] Functional extras ("the one with business"): when many people come, **occasionally** one shows
            # [EN] up.
            # [EN] Frequency is left to randomness + a budget gate (`EXTRAS_DAILY_BUDGET`), not a fixed beat count
            # [EN] --
            # [EN] a fixed beat count would produce mechanical rhythms like "someone comes to collect debt every 4
            # [EN] beats".
            if _crowd.crowd_size(self.world) >= 3 and self._rng.random() < 0.2:
                ev = None
                # ★ 先看**有没有老熟人该回来**（钩子群演）——
                #   "反复出现、像有故事的客人"只能这样长出来：先记名册，再回访。
                #   ⚠ 它排在新面孔**之前**：老熟人的戏份永远比新路人值钱。
                # [EN] * First check **whether an old acquaintance should return** (hook extras) --
                # [EN] "A recurring guest who seems to have a story" can only grow this way: first record the roster,
                # [EN] then revisit.
                # [EN] ! It ranks **before** new faces: an old acquaintance's screen time is always worth more than a
                # [EN] new passerby's.
                ev = _crowd.recall_hook(self.world, self._rng)
                if ev is None:
                    # 新面孔：交给「群众演员」投人（AI），拿不到就走规则池
                    # [EN] New faces: delegate casting to the "extras" (AI); if it fails, fall back to the rule pool
                    ev = await self._cast_extra()
                if ev:
                    tag = "又来了" if ev.get("钩子") else "来人"
                    self._push_narrative(
                        f"【{tag}】{ev.get('称呼', '有人')}——{ev.get('诉求', '')}",
                        1, kind=S.EVENT)
                    # ★★★ **进门这一拍就有人被要求去理他**（2026-10-21）。
                    #   为什么不能只靠 `dispatch`：它每 `DISPATCH_EVERY_TICKS`(=8) 拍一次，
                    #   而群演的耐心是 `FUNC_PATIENCE`(=8) 拍 —— 卡在边界上，
                    #   常常"他等满了，派活还没轮到"。实测 mwl_v5 一次都没赶上。
                    #   ⇒ 投人成功**当场**给一个最相关的人派"了结门口那件事"。
                    #   ⚠ 他手上有在办的事就不动（不打断正在推进的活，
                    #     那条留给下一轮 `dispatch` 的兜底去处理）。
                    # [EN] ★★★ **Someone is asked to deal with him the beat he walks in**
                    # [EN] (2026-10-21). Why not rely on `dispatch`: it runs every
                    # [EN] `DISPATCH_EVERY_TICKS` (=8) beats and an extra's patience is
                    # [EN] `FUNC_PATIENCE` (=8) -- the collision sits exactly on the boundary, so
                    # [EN] often "he waits it out and dispatch never came round". Measured in
                    # [EN] mwl_v5: it never once caught up.
                    # [EN] => on a successful cast, assign "settle the matter at the door" on the
                    # [EN] spot to the most related person. ⚠ If he is already working on something,
                    # [EN] leave it alone (don't interrupt real progress; that case is left to the
                    # [EN] next `dispatch` fallback).
                    self._handoff_extra(ev)
            gone = _crowd.tick_extras(self.world)
            # ★ 退场播报：**由 `crowd.exit_notice()` 决定说不说、说什么**
            #   （判断在那边，因为它和"谁在门外"是同一件事的两面，且要能脱离
            #   主循环单测）。这里只说三句话以内的结果：
            #   · 功能/钩子群演（"有事的那个"）→ 点名叫出来；
            #   · 背景群演 → 最多每 `BG_NOTICE_EVERY` 拍一句"换过一拨"。
            #   ⚠ 以前是 `for who in gone[:2]: push(f"（{who}走了）")`：
            #     背景也逐条报 → 每 3 拍一条、同一句反复出现（用户 2026-10-07
            #     报的"对话又死循环"）；而且 `who` 是整句场面描写，句尾本来
            #     就有动作，再拼"走了"会得到"走了走了"那个重词。
            # [EN] * Exit announcement: **`crowd.exit_notice()` decides whether to say it and what to say**
            # [EN] (the judgment is over there, because it and "who is outside the door" are two sides of the same
            # [EN] thing, and it must be able to work without
            # [EN] the main loop unit test). Here we only say the result in three sentences or fewer:
            # [EN] * Functional/hook extras ("the one with business") -> call them out by name;
            # [EN] * Background extras -> at most one "a new batch swapped in" line every `BG_NOTICE_EVERY` beats.
            # [EN] ! Previously it was `for who in gone[:2]: push(f"({who} left)")`:
            # [EN] background was also reported line by line -> one line every 3 beats, the same line repeating
            # [EN] (user 2026-10-07
            # [EN] reported "dialogue is looping again"); and `who` was a whole scene description, whose end
            # [EN] already had an action, so appending "left" produced the redundant "left left".
            notice = _crowd.exit_notice(self.world, gone, tick=int(tick_num or 0))
            if notice:
                self._push_narrative(notice, 3, kind=S.NOTE)
        except Exception as e:                                  # noqa: BLE001
            self._warn_once('crowd', f"客流/群演出错（不影响推演）：{e!r}")

    async def _cast_extra(self) -> dict | None:
        """叫「群众演员」投一个人；闸门不过或 AI 拿不到 → 退回规则池。

        闸门**照旧**（`EXTRAS_ENABLED` / 同场上限 / 当日预算）—— AI 不绕预算：
        这一层只决定"投成谁"，"能不能投"仍由 `world/crowd` 说了算。
        
                English:
        Call "群众演员" to cast one person; if the gate fails or AI is unavailable -> fall back to the rule
        pool.
                The gates are **unchanged** (`EXTRAS_ENABLED` / same-scene cap / daily budget) -- AI does not bypass the budget:
                this layer only decides "who gets cast"; "whether casting is allowed" is still up to `world/crowd`.
        """
        from world import crowd as _crowd
        if CFG.b('CREW') and CFG.b('CREW_EXTRA_CASTING'):
            try:
                if not _crowd.can_cast(self.world):
                    return None
                got = await self.studio.cast_extra(self._crew_ctx())
                if got:
                    # 登记走 `crowd.add_extra`：外面不必知道那条记录的字段长什么样
                    # [EN] Registering goes through `crowd.add_extra`: the outside does not need to know what that record's
                    # [EN] fields look like
                    e = _crowd.add_extra(self.world, got, self._rng)
                    if e is not None:
                        return e
                    # ★ 投出来的人**挂不上主线**（`add_extra` 那道闸拦了）：这不是
                    #   "投得不好"，是"他不该来"。落到规则兜底再看有没有搭得上的，
                    #   两个都不行就这一拍没人来 —— 门口空着比白来一个强。
                    # [EN] ★ The cast person **cannot be anchored to the main line** (blocked by
                    # [EN] `add_extra`): that is not "bad casting", it is "he should not come".
                    # [EN] Fall through to the rule pool; if neither works, nobody comes this beat
                    # [EN] -- an empty door beats a pointless visit.
            except Exception as e:                               # noqa: BLE001
                self._warn_once('cast_extra', f"群演投人出错（走规则兜底）：{e!r}")
        # 兜底：老规矩（固定池抽一个）
        # [EN] Fallback: the old rule (draw one from the fixed pool)
        return _crowd.new_extra(self.world, self._rng)

    def _handoff_extra(self, ev: dict) -> str:
        """门口刚来一位：当场给一个在场的人派"了结这件事"（返回派给了谁，没人可派就空串）。

        与 `director.dispatch` 的分工：
          · 这里管**进门那一拍**（时效性，等不起 8 拍）；
          · `dispatch` 兜底管**之后仍然没人理**的情况（他会一直等到 `FUNC_PATIENCE`）。
        两处用同一个判据选人（`crowd.pick_handler`）和同一句话（`crowd.handoff_line`）——
        一条判据、两个时机，不各写一遍。

        ⚠ **不打断正在办的活**：那个人若"还在办上一件"（`_mission_still_running`），
          这里什么都不做。硬塞会让目标漂移（那是 2026-10-19 花了一整轮修的病）。
        
                English:
        Someone just arrived at the door: assign "settle this matter" on the spot to a person
        present (returns who got it; empty string if nobody can take it).
        Division of labor with `director.dispatch`:
          · this one handles **the beat they walk in** (timeliness; it cannot wait 8 beats);
          · the `dispatch` fallback handles **still ignored later on** (he waits until
            `FUNC_PATIENCE`).
        Both use the same selector (`crowd.pick_handler`) and the same sentence
        (`crowd.handoff_line`) -- one criterion, two moments, not written twice.
        ⚠ **Never interrupt work in progress**: if that person is "still working on the previous
        one" (`_mission_still_running`), do nothing here. Shoving it in causes goal drift (the
        disease that took a whole round to fix on 2026-10-19).
        """
        try:
            from world import crowd as _crowd
            people = [a.name for a in self.agents if self.world.is_on_stage(a.ps)]
            who = _crowd.pick_handler(self.world, ev, people)
            if not who:
                return ''
            ps = self.world.people.get(who)
            if ps is None:
                return ''
            if ps.mission and self._mission_still_running(who, ps.mission):
                return ''
            ps.mission = _crowd.handoff_line(ev)
            ps.mission_stuck = 0
            _LOG.info('群演进门即派活：门口「%s」→ %s（%s）',
                      str(ev.get('称呼') or ''), who, ps.mission)
            return who
        except Exception as e:                                  # noqa: BLE001
            self._warn_once('handoff', f"群演进门派活出错（不影响推演）：{e!r}")
            return ''

    async def _end_day(self) -> None:
        """每日收尾：落盘「第N天的生活」，重置日计数。
                English:
        Daily wrap-up: persist "day N's life", reset the day counter.
        """
        cal = self.world.clock_display()
        # ★ 一天结束了 ⇒ "这一段在谈什么"才是真的结束（换场**不清**，见 `WorldState.clear_lines`）。
        # [EN] The day is over => "what this stretch was about" really ends (a scene change does
        # [EN] **not** clear it; see `WorldState.clear_lines`).
        try:
            self.world.reset_topic()
        except Exception:                                        # noqa: BLE001
            pass
        # ★ 今天落盘的幕（剧本模式才有）。**要在下面递给它 `_crew_wrap`** ——
        #   那边不能用 `self._builder`，因为这一支走完就把 `_builder` 置 None 了
        #   （顺序错位曾经让场记天天报"没有可查的正文"，见 `_crew_wrap` 的说明）。
        # [EN] * The act persisted today (only in script mode). **Must hand `_crew_wrap` to it below** --
        # [EN] it cannot use `self._builder` there, because once this branch finishes it sets `_builder` to
        # [EN] None
        # [EN] (a wrong order once made the continuity script report "no queryable body text" every day; see
        # [EN] the note in `_crew_wrap`).
        scenes = None
        if self._script_mode and self._builder is not None:
            scenes = self._builder.flush()
            if not scenes:                      # 一天什么都没发生也要留个交代
            # [EN] Even if nothing happened all day, leave an account
                b = self._ensure_builder()
                b.observe_quiet()
                scenes = b.flush()
            # ★「一天结束」分隔符：天数 + 当天几幕（用户要的"关键信息，不能太长"）
            # [EN] * "End of day" separator: day number + how many acts that day (the "key info, not too long" the
            # [EN] user asked for)
            self._push_divider(D.day_end(int(self._current_day or 0),
                                         scenes=len(scenes)))
            cast = self.world.on_stage_names()
            key_events = [f"{k.get('id', '')}".strip()
                          for k in (self.world.progress_nodes or [])
                          if k.get('状态') == '已完成'][:6]
            self.runfolder.flush_daily_script(
                self._current_day, scenes, calendar_str=cal,
                weather=self.world.weather, cast=cast,
                tension=f"{self.world.tension:.2f}", key_events=key_events,
                film_header=self._film_header_of_day(scenes),
                recap=self._recap_text(),
                # ★ 剧作者写的那一小段场景介绍（用户上轮遗留：不能只有三行元数据）
                # [EN] * The short scene introduction written by the playwright (left over from the user's last round:
                # [EN] cannot be just three lines of metadata)
                scene_intro=str(getattr(self._day_script, 'scene_intro', '') or ''),
                day_brief=str(getattr(self._day_script, 'day_brief', '') or ''))
            from display import script_render as _SR
            st = _SR.stats(scenes)
            _LOG.info("第 %d 天落盘（剧本）：%s", self._current_day, st)
            self._builder = None                # 新的一天重新起幕
            # [EN] A new day starts a new act
            # ★★★ 2026-10-26：**在重置之前，先看这一站的戏演完了没有**。
            #   没演完就把剩余分拍交给下一天（`_compose_day` 会接着演，不重新规划）。
            #   ⚠ 必须排在 `_builder = None` **之后**也能工作 —— 它读的是 `self._day_script`
            #     与 `_ticks_today`，与 builder 无关；放这儿是为了"落盘已经发生"之后
            #     再决定要不要续，避免"没落盘就先续上"导致两天都缺内容。
            # [EN] ★★★ 2026-10-26: **before resetting, check whether this station's beats are done.**
            # [EN] If not, hand the remaining beats to the next day (`_compose_day` keeps playing them).
            # [EN] Ordering note: it reads `_day_script` and `_ticks_today`, not the builder, so it
            # [EN] works either way; it sits after the flush so we decide on continuation only once
            # [EN] the day's content is safely on disk.
            self._event_carry = self._carry_unplayed_beats()
        else:
            content = "\n\n".join(self._daily_narrative)
            if not content:
                content = "（这一天没有什么特别的事发生。）"
            # ★ CP6：落盘前过合规（设计稿 §16.2「叙事整理落盘前」）——
            #   放在这里而不是每句台词那里：一句一查是**每句话一次 LLM**，
            #   而落盘这一天只有一次。词表层零成本、LLM 层 hybrid 按需。
            # [EN] * CP6: compliance check before persistence (design doc §16.2 "before narrative cleanup
            # [EN] persistence") --
            # [EN] placed here rather than at every line of dialogue: checking per sentence is **one LLM per
            # [EN] sentence**,
            # [EN] whereas persisting this day happens only once. The word-surface layer is zero-cost, the LLM
            # [EN] layer is hybrid on demand.
            content = await self._compliance_gate(content, 'CP6')
            self.runfolder.flush_daily(self._current_day, content, cal,
                                       film_header=self._film_header_of_day([]))
            _LOG.info("第 %d 天落盘：%d 段叙事", self._current_day,
                      len(self._daily_narrative))

        # ★ 前情提要（长期记忆）—— 2026-10-06 加。
        #   素材要在**清空之前**抓一份：普通模式的叙事就在 `_daily_narrative` 里；
        #   剧本模式走的是 builder 的 scenes（已经落成结构化剧本了），
        #   那种情况下摘要以 db 里当天的事件为准。
        # [EN] * Recap (long-term memory) -- added 2026-10-06.
        # [EN] The material must be captured **before clearing**: in normal mode the narrative is in
        # [EN] `_daily_narrative`;
        # [EN] script mode goes through the builder's scenes (already persisted as a structured script),
        # [EN] in that case the summary is based on the day's events in the db.
        day_lines = list(self._daily_narrative)
        # ★★ 剧组收工（2026-10-07）：**场记连戏检查 + 宣发一句话**。
        #   顺序有意放在"落盘之前、清空之前"：
        #     · 在落盘前 —— 场记要读的是**今天真正的稿子**（`_daily_narrative`
        #       与 `scenes` 都还在手上）；
        #     · 在清空前 —— `day_lines` 就是当天叙事行，清掉就没得查了。
        #   ⚠ 这一步**只报不改**（`crew/agents.Continuity` 的说明）：
        #     连戏的错误分两种（真错 / 有意的破例），机器分不出来，所以产出
        #     只是一份"提请作者注意"的清单。
        # [EN] ** Crew wrap (2026-10-07): **continuity script continuity check + one-line publicity**.
        # [EN] The order is intentionally "before persistence, before clearing":
        # [EN] * Before persistence -- what the continuity script reads is **today's actual draft**
        # [EN] (`_daily_narrative`
        # [EN] and `scenes` are both still in hand);
        # [EN] * Before clearing -- `day_lines` is the day's narrative lines, and once cleared there is nothing
        # [EN] to check.
        # [EN] ! This step **only reports, does not fix** (see the note in `crew/agents.Continuity`):
        # [EN] continuity errors come in two kinds (real errors / intentional exceptions), and a machine cannot
        # [EN] tell them apart, so the output
        # [EN] is only a list "drawing the author's attention".
        await self._crew_wrap(day_lines, scenes=scenes)
        # ★★ **总结会**（用户点名要显示的一条阶段消息）+ **整理当天这一章**。
        #   顺序有意放在收工**之后**：整理稿要"今天实际演成什么样"，
        #   而那要等场记/语言审校/复盘都看过一遍（它们会把问题写进今日总结）。
        #   ⚠ 整理稿会**追加**进「今日总结.md」——所以必须排在复盘写完之后，
        #     否则复盘那次写入会把刚追加的那一节覆盖掉。
        # [EN] ** **Summary meeting** (a stage message the user explicitly asked to display) + **organize
        # [EN] today's chapter**.
        # [EN] The order is intentionally **after wrap**: the cleanup draft needs "how today actually played
        # [EN] out",
        # [EN] and that requires the continuity script/language review/retrospective to have all looked at it
        # [EN] (they write issues into today's summary).
        # [EN] ! The cleanup draft is **appended** to "今日总结.md" -- so it must come after the retrospective is
        # [EN] written,
        # [EN] otherwise that retrospective write would overwrite the section just appended.
        self._stage_start('wrap_meeting')
        await self._day_novel(day_lines, scenes=scenes)
        # ★ 复盘说"这一天立不住"时，**回档重演**（默认关，见 `DAY_REVIEW_REPLAY`）。
        #   顺序放在 `_crew_wrap` 之后：复盘要先读到完整的一天，才有资格说这话。
        #   ⚠ 一天最多一次 —— 否则"复盘又说不行 → 又重演"会变成死循环
        #     （而每次重演都要花钱重排那一幕）。
        # [EN] * When the retrospective says "this day does not hold up", **roll back and replay** (off by
        # [EN] default, see `DAY_REVIEW_REPLAY`).
        # [EN] The order is after `_crew_wrap`: the retrospective must first read a complete day before it is
        # [EN] qualified to say this.
        # [EN] ! At most once a day -- otherwise "retrospective says no again -> replay again" becomes an
        # [EN] infinite loop
        # [EN] (and each replay costs money to re-stage that act).
        await self._maybe_replay_day(scenes)
        # ★ **去 AI 审计落盘**（2026-10-07）：把今天攒下的命中写成一份给人看的页。
        #   放在这里（清空之前、收工之后）——它是"今天的体检报告"，
        #   与 `今日总结.md`（内容层面）互补：那份说"戏怎么样"，这份说"话怎么样"。
        # [EN] * **De-AI audit persistence** (2026-10-07): write the hits accumulated today into a
        # [EN] human-readable page.
        # [EN] Placed here (before clearing, after wrap) -- it is "today's health report",
        # [EN] complementary to `今日总结.md` (content level): that one says "how the play was", this one says "how
        # [EN] the words were".
        self._flush_deai_report()
        # ★ **剧本审读落盘**（2026-10-08）：台账写增量（`审读台账.jsonl`，
        #   一轮一份、追加）、小结覆盖写（`剧本审读.md`，一天一份）。
        #   位置与去 AI 审计同一档：都是"今天的体检报告"，一个是内容层面
        #   （这一批合起来在说什么、谁没搭上话），一个是字词层面。
        # [EN] * **Script review persistence** (2026-10-08): the ledger writes incrementally (`审读台账.jsonl`,
        # [EN] one per round, appended), the summary is overwrite-written (`剧本审读.md`, one per day).
        # [EN] Its position is the same tier as the de-AI audit: both are "today's health report", one at the
        # [EN] content level
        # [EN] (what this batch as a whole is saying, who did not get to speak), one at the word level.
        self._flush_review_report()
        self._daily_narrative.clear()
        # ★ 这一天到此为止：把"今天跑过几拍"清零（收尾时判"这一天有没有东西可落"，
        #   见 `_ticks_today` 的说明 —— 不清零的话，跨天点停止会重复落一天空稿）。
        # [EN] * This day ends here: reset "how many beats ran today" to zero (at wrap-up it judges "whether
        # [EN] this day has anything to persist",
        # [EN] see the note on `_ticks_today` -- without resetting, stopping at a day boundary would persist an
        # [EN] extra empty day).
        self._ticks_today = 0
        # ★★★ 2026-10-26：**把这一站剩下的故事时间一次跳掉**（"此后三个月无事"）。
        #
        #   来历：一拍最多推 `BEAT_MAX_MINUTES`（30 分钟）—— 那是"一拍"这个概念本身的
        #   边界（一个人做一件事），不是"这一站的故事时长"。`数月 + 带过` 是
        #   "跨度 90 天、1 拍"，那 1 拍只走了 30 分钟，剩下 89 天 23.5 小时**必须有人跳掉**，
        #   否则读者看到"三个月过去了"却还是同一夜 —— 幕头时间自相矛盾，
        #   而"时序混乱"正是用户点名过的第一条。
        #   ⇒ 站演完的那次收工，把 `跨度 - 已走` 补齐，并推一句旁白让人看见时间过去了。
        #   ⚠ 只在**站真的演完了**时补（`_event_carry` 为空）。一站跨多天时第一天就补，
        #     会把"三个月"在第一天吃掉，后面几天没时间可走。
        # [EN] ★★★ 2026-10-26: **jump this station's remaining story time in one go**. A beat
        # [EN] advances at most `BEAT_MAX_MINUTES` (30 minutes) -- the bound of the *concept* "one
        # [EN] beat", not of the station's story duration. `months + in passing` is "90 days, one
        # [EN] beat": that beat walks 30 minutes and the remaining 89 days 23.5 hours **must be
        # [EN] jumped by someone**, or the reader is told three months passed while it is still the
        # [EN] same night, and the act headers contradict each other -- and "scrambled chronology" is
        # [EN] the very first thing the user named. So at the wrap-up that ends the station, top up
        # [EN] `span - walked` and narrate it. ⚠ Only when the station is really over (`_event_carry`
        # [EN] empty): a station spanning several days would otherwise eat the three months on day one.
        self._flush_station_gap()
        # 新的一天是**新的站** ⇒ 站内流逝归零（不清零的话第二站一开场就"已经走了两小时"）。
        # [EN] A new day is a **new station** => intra-station elapsed resets.
        self._walked_min = 0
        # ★ 同一天的两个计数器也一起清零（2026-10-11）：
        #   `_skips_today` = 今天跳了几次时间（状态条可见）；`_day_words` = 今天写了多少字
        #   （对着 `ROUND_DAILY_WORDS` 那个软目标）。跟 `_ticks_today` 同一个道理 ——
        #   它们量的都是"**这一天**"，跨天不清就会一路累加下去。
        # [EN] * The same day's two other counters are also reset together (2026-10-11):
        # [EN] `_skips_today` = how many times time was skipped today (visible in the status bar); `_day_words`
        # [EN] = how many words were written today
        # [EN] (against the soft target `ROUND_DAILY_WORDS`). Same reasoning as `_ticks_today` --
        # [EN] they all measure "**this day**", and without resetting across days they would keep accumulating.
        self._skips_today = 0
        self._day_words = 0
        await self._summarize_day(day_lines)

        # ★ 跨天要做的两件事（2026-10-06「治空转」）——
        #   ① **到日子的人登场**：`debut_day` 不推进就只是个摆设，人物永不自己出场；
        #   ② **群演换一批**：昨天来的客人不该今天还杵在那儿（背景群演留 2 个意思一下）。
        # [EN] * Two things to do across days (2026-10-06 "cure idling") --
        # [EN] 1. **Characters due to debut appear**: if `debut_day` does not advance it is just decoration,
        # [EN] and characters never appear on their own;
        # [EN] 2. **Extras swap in a new batch**: yesterday's guests should not still be standing there today
        # [EN] (keep 2 background extras to make the point).
        try:
            new_faces = self.world.promote_debuts()
            if new_faces:
                _LOG.info("今日登场：%s", "、".join(new_faces))
                self._push_narrative(
                    "（今日又有生面孔。）" if len(new_faces) == 1
                    else f"（今日来了 {len(new_faces)} 个生面孔。）", 3, kind=S.NOTE)
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning("登场推进失败（不影响推演）：%r", e)
        try:
            from world import crowd as _crowd
            self.world.extras = [e for e in self.world.extras
                                 if e.get("kind") == "背景"][:2]
            self.world.extras_today = 0
            # ★ 日界清「今天被理过的群演」——它只描述今天（整理稿用它开例外）。
            # [EN] Clear "extras dealt with today" at the day boundary -- it only describes today
            # [EN] (the organizing pass uses it to carve the exception).
            self.world.extras_engaged = []
            _crowd.sync_crowd(self.world, self._rng)
            if self.runfolder:
                (self.runfolder.root / '群演台账.md').write_text(
                    _crowd.ledger_md(self.world), encoding='utf-8')
                # ★ 钩子群演名册（跨场记忆的落盘）+ 转正建议 ——
                #   **只是建议**：程序绝不自动把临演写进设定集（那是作者的判断）。
                # [EN] ★ Hook extras roster (persisting cross-scene memory) + promotion suggestions ——
                # [EN] **Suggestions only**: the program never automatically writes extras into the setting bible (that
                # [EN] is the author's call).
                (self.runfolder.root / '可转正群演.md').write_text(
                    _crowd.hooks_md(self.world), encoding='utf-8')
            hot = _crowd.hook_suggestions(self.world)
            if hot:
                names = "、".join(str(r.get('称呼') or '') for r in hot[:3])
                self._push_narrative(
                    f"（这几个临演已经反复出现，像是有故事的人：{names}"
                    f"—— 要不要给他们一张人物卡由你定。）", 3, kind=S.NOTE)
                self.world.hooks_promoted = list(
                    getattr(self.world, 'hooks_promoted', None) or []) + \
                    [str(r.get('key') or '') for r in hot]
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning("群演收尾失败（不影响推演）：%r", e)

        # ★ 记忆压缩（`SUMMARIZE_MEMORY_AFTER`，设计稿 §2.4）——
        #   放在**日界**：一天一次，节拍稳定、和"落盘"同一处，
        #   而且刚过去的这一天已经在上面压成前情提要了，时序上顺。
        # [EN] ★ Memory compression (`SUMMARIZE_MEMORY_AFTER`, design doc §2.4) ——
        # [EN] Placed at the **day boundary**: once a day, stable cadence, at the same spot as "persisting",
        # [EN] and the day just past has already been compressed into the recap above, so the timing works out.
        await self._compact_memories()

        # 自动存档（每天结束时）
        # [EN] Auto-save (at the end of each day)
        if self.runfolder:
            from store.save import auto_save_on_day_end
            world_state = {
                "game_day": self.world.game_day,
                "clock_display": self.world.clock_display(),
                "current_node": self.world.current_node,
                "tension": self.world.tension,
                "event_count": self.world.event_count,
                "weather": self.world.weather,
                "scene": self.world.scene,
                "scene_desc": self.world.scene_desc,
                "on_stage": self.world.on_stage_names(),
                "off_stage": self.world.off_stage_names(),
                "active_lines": self.world.active_lines,
                "activated_foreshadows": self.world.activated_foreshadows,
            }
            auto_save_on_day_end(self.runfolder.project_dir, self.runfolder.root, world_state)

        # ★ 「剧情总览」：这一天演完了，情节推进了 ⇒ 重算一次（纯读盘，不花钱）。
        #   位置在日界**最后一件事**：上面那些落盘都做完了，它读到的才是完整的这一天。
        # [EN] Story overview: the day is done and the plot advanced => recompute (pure disk reads,
        # [EN] free). Placed as the **last** thing at the day boundary so everything above has been
        # [EN] persisted and it reads a complete day.
        self._refresh_story_flow()

    # ── 影视镜头卡（`FILM_MODE` / `DISPLAY_FILM_CARDS`，设计稿 §10.8）──────
    # [EN] ── Film shot cards (`FILM_MODE` / `DISPLAY_FILM_CARDS`, design doc §10.8) ──────
    def _emit_film_card(self, place: str = '') -> None:
        """幕终时把**刚刚结束那一幕**的镜头卡推给界面（`DISPLAY_FILM_CARDS`）。

        ⚠ 这里**只负责"屏幕上看得到"**；`分镜表.md` 由 `_end_day` 统一落盘 ——
        两处都写会重复，而"重复"这件事比"少一条"更难发现。
        
                English:
        At act end, push the storyboard cards of **the act that just ended** to the UI
        (`DISPLAY_FILM_CARDS`).
                ⚠ This is **only responsible for "what's visible on screen"**; `分镜表.md` is persisted uniformly by `_end_day` --
                writing in both places duplicates, and "duplication" is harder to spot than "a missing line".
        """
        try:
            from display import film as F
            if not F.should_show():
                return
            cur = self._builder.current if self._builder else None
            entries = getattr(cur, 'entries', None) or []
            if not entries:
                return
            card = F.shot_card(entries, self.world, place=place)
            # 用 `EVENT` 之外的中性样式（NOTE），免得镜头卡被当成剧情事件
            # [EN] Use a neutral style (NOTE) other than `EVENT`, so shot cards aren't treated as story events
            self._push_narrative(card, 3, kind=S.NOTE)
        except Exception as e:                                  # noqa: BLE001
            self._warn_once('film_card', f"镜头卡生成失败（不影响推演）：{e!r}")

    def _film_cards_of_day(self, scenes: list | None = None) -> list[dict]:
        """当天每一幕一张卡（`分镜表.md` 的素材）。每条都带 `card` 原文。
                English:
        One card per act of the day (the source material for `分镜表.md`). Each carries the `card` raw
        text.
        """
        from display import film as F
        out: list[dict] = []
        if scenes is None:
            scenes = list(getattr(self._builder, 'scenes', None) or []) \
                if self._builder else []
        for sc in list(scenes or []):
            entries = getattr(sc, 'entries', None) or []
            place = str(getattr(sc, 'place', '') or '') or self.world.scene
            card = F.shot_card(entries, self.world, place=place)
            row = F.parse_card(card)
            row['card'] = card
            row['day'] = int(getattr(sc, 'day', self.world.game_day) or 0)
            row['clock'] = str(getattr(sc, 'clock', '') or '')
            first = next((str(getattr(e, 'text', '') or '') for e in entries
                          if str(getattr(e, 'text', '') or '').strip()), '')
            row['line'] = first
            out.append(row)
        if not out:
            # prose 模式没有分幕 → 一天给一条（**不假装有分幕**）
            # [EN] prose mode has no acts → one per day (**don't pretend there are acts**)
            text = ' '.join(self._daily_narrative)[:200]
            card = F.shot_card([], self.world, place=self.world.scene)
            row = F.parse_card(card)
            row.update({'card': card, 'day': int(self.world.game_day or 0),
                        'clock': self.world.clock_display(), 'line': text})
            out.append(row)
        return out

    def _open_checkpoint_due(self) -> bool:
        """open 模式下这一拍该不该**停下来存档**（`OPEN_CHECKPOINT_EVERY_DAYS`）。

        ⚠ 抽成独立方法不是为了好看：整段写死在 `_tick` 里时，
        验证脚本**只能读源码文本**（`'OPEN_CHECKPOINT_EVERY_DAYS' in src`），
        于是"把条件改成 `if False`"这种变异一条都不会红
        （反例法抓到的 —— 源码哨兵抓不住条件被掏空）。
        
                English:
        Whether this beat should **stop and save** in open mode (`OPEN_CHECKPOINT_EVERY_DAYS`).
                ⚠ Extracting this into its own method isn't for looks: when it was inlined in `_tick`,
                the verification script **could only read the source text** (`'OPEN_CHECKPOINT_EVERY_DAYS' in src`),
                so mutations like "change the condition to `if False`" would never go red
                (caught by the counterexample method -- the source sentinel can't catch a hollowed-out condition).
        """
        if (CFG.s("RUN_MODE") or "").strip() != "open":
            return False
        every = CFG.i("OPEN_CHECKPOINT_EVERY_DAYS")
        if every <= 0:
            return False
        day = int(getattr(self.world, "game_day", 0) or 0)
        if day <= 0 or day % every != 0:
            return False
        # 同一天只停一次（否则会反复停在同一格上出不去）
        # [EN] Stop only once per day (otherwise it repeatedly stops on the same cell and can't get out)
        return getattr(self, "_last_open_ckpt", None) != day

    # ── 合规（设计稿 §16.2 的 CP6：叙事整理落盘前）────────────────────
    # [EN] ── Compliance (CP6 of design doc §16.2: before narrative organization is persisted)
    # [EN] ────────────────────
    async def _compliance_gate(self, text: str, checkpoint: str = 'CP6') -> str:
        """落盘前过一道合规，返回**该用的正文**。

        三档结果：
          · 通过（pass / rewrite）→ 原样或改写后的文本；
          · 拦下（block / hold）→ **不出原文**，换一句安全替身，并播报原因；
          · 合规关着 / 没接上 → 原样（但**只在真的关着时**才静默）。

        ★ `hold` 是 2026-10-06 加的一档：「复核没拿到结论」。
        旧实现把它当成 `pass` 放行（`fail-open`）—— 合规是生死线，
        「模型没答」绝不等于「内容没问题」，所以那一档**也不放行**。
        
                English:
        Run a compliance pass before persisting, return **the body that should be used**.
                Three tiers of results:
                  · pass (pass / rewrite) -> the original or rewritten text;
                  · block (block / hold) -> **do not emit the original**, swap in a safe substitute, and broadcast the reason;
                  · compliance off / not wired up -> as-is (but silent **only when it's genuinely off**).
                ★ `hold` is a tier added on 2026-10-06: "review returned no conclusion".
                The old implementation treated it as `pass` and let it through (`fail-open`) -- compliance is a lifeline,
                and "the model didn't answer" never equals "the content is fine", so that tier **is not let through either**.
        """
        if self.compliance is None or not text.strip():
            return text
        try:
            res = await self.compliance.check(text, checkpoint)
        except Exception as e:                                  # noqa: BLE001
            self._warn_once('compliance', f"合规检查出错 → **不放行**：{e!r}")
            from compliance.agent import fallback_line
            return fallback_line()
        if res.passed:
            if res.action == 'rewrite':
                self._push_narrative(
                    f"（合规·{checkpoint}）有内容按 {res.level} 降了尺度：{res.reason}",
                    0, kind=S.NOTE)
            return res.apply(text)
        from compliance.agent import fallback_line
        self._push_narrative(
            f"（合规·{checkpoint}）{res.level} {res.action}：{res.reason}"
            f" —— 这段已按设定略去，不写入正文。", 0, kind=S.NOTE)
        _LOG.warning("合规拦截 [%s] %s/%s：%s", checkpoint, res.level,
                     res.action, res.reason)
        return fallback_line(res.level)

    def _film_header_of_day(self, scenes: list) -> str:
        """当天镜头卡的落盘头（`FILM_MODE` 关着就空串；`DISPLAY_FILM_CARDS`
        关着**也不写进正文**，但 `分镜表.md` 照旧汇总 —— 两个开关是两件事：
        一个管"屏幕上显不显"，一个管"给不给拍剧的人留底"）。

        ⚠ 这里**顺便**把当天的卡收进 `self._film_cards`（`分镜表.md` 的来源）。
        只在这一个地方收，避免"屏幕上一份、落盘一份、汇总里又一份"的三份重复。
        
                English:
        The landing header of the day's film card (`FILM_MODE` off means empty string;
        `DISPLAY_FILM_CARDS`
                off means it is **also not written into the body**, but `分镜表.md` still summarizes as usual -- the two switches are two different things:
                one controls "whether it shows on screen", the other controls "whether to leave a record for the person shooting the drama").
                ⚠ Here **by the way** the day's cards are collected into `self._film_cards` (the source of `分镜表.md`).
                Collect only in this one place, to avoid the triple duplication of "one copy on screen, one copy on disk, and another in the summary".
        """
        if not CFG.b('FILM_MODE'):
            return ''
        try:
            cards = self._film_cards_of_day(scenes)
            self._film_cards.extend(cards)
            if self.runfolder:
                from display import film as _F
                (self.runfolder.root / '分镜表.md').write_text(
                    _F.storyboard_md(self._film_cards), encoding='utf-8')
            if not CFG.b('DISPLAY_FILM_CARDS'):
                return ''
            return '\n'.join(str(c.get('card') or '') for c in cards if c.get('card'))
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning("分镜表生成失败（不影响推演）：%r", e)
            return ''

    def _announce_compaction(self, actions: list) -> None:
        """把这一拍里发生过的**上下文主动压缩**讲给作者听（一次一拍一条）。

        ★★ 2026-10-10（用户点名）：「系统要提示我并且进行主动压缩」。
          压缩这件事必须在**中栏看得见** —— 否则它和"模型今天忽然变笨了"
          长得一模一样：人物忘掉前因、说话变浅，而屏幕上什么解释都没有。

        ⚠ 只播一次（读完就清）。一次压缩会命中好几个人（同一拍的上下文长度
          差不多），逐人播报会变成刷屏 —— 这正是本项目以前被 550 条
          "没动也没出声"刷过的那个坑。
        
                English:
        Tell the author about the **proactive context compaction** that happened in this beat (one item
        per beat).
                ★★ 2026-10-10 (user called out): "The system should prompt me and perform proactive compaction."
                  This compaction must be **visible in the middle column** -- otherwise it looks
                  exactly like "the model suddenly got dumber today": characters forget prior context, speech becomes shallow, and there is no explanation on screen.
                ⚠ Play only once (clear after reading). One compaction can hit several people (context lengths in the same beat
                  are similar), and announcing per person would become screen spam -- this is exactly the pit this project
                  previously fell into with 550 "no action, no sound" spam.
        """
        notes: list[str] = []
        for agent, _act in actions:
            info = getattr(agent, 'last_compaction', None)
            if not info:
                continue
            notes.append(f"{agent.name}：{info.get('note', '')}")
            agent.last_compaction = None          # 读完就清，别反复播
            # [EN] Clear after reading, don't replay repeatedly
        if not notes:
            return
        self._push_narrative(
            "（上下文已主动压缩 —— 最近的一批记忆折成了摘要，"
            "为的是不撞上下文上限）" + "；".join(notes[:3]),
            0, kind=S.NOTE)

    async def _compact_memories(self) -> None:
        """日界压缩记忆（`SUMMARIZE_MEMORY_AFTER`）。

        一天一次、**并发**跑（一个人一次 cheap 调用；12 个人串行就是 12 次往返）。
        阈值没到的人 `compact_memory()` 会直接返回 `skipped`，一次请求都不发 ——
        所以正常情况下这里几乎不花钱。
        
                English:
        Day-boundary compression memory (`SUMMARIZE_MEMORY_AFTER`).
                Once a day, run **concurrently** (one cheap call per person; 12 people serial would be 12 round trips).
                For people below the threshold, `compact_memory()` returns `skipped` directly, without sending a single request --
                so normally this costs almost nothing.
        """
        threshold = CFG.i("SUMMARIZE_MEMORY_AFTER")
        if threshold <= 0:
            return
        targets = list(self.agents)
        if not targets:
            return
        try:
            results = await asyncio.gather(
                *(a.compact_memory() for a in targets), return_exceptions=True)
        except Exception as e:                                  # noqa: BLE001
            self._warn_once('compact', f"记忆压缩失败（不影响推演）：{e!r}")
            return
        folded = sum(int(r.get("folded", 0) or 0) for r in results
                     if isinstance(r, dict))
        errs = [r for r in results if isinstance(r, BaseException)]
        if folded:
            _LOG.info("第 %d 天记忆压缩：共折起 %d 条", self.world.game_day, folded)
        if errs:
            self._warn_once('compact_err', f"记忆压缩出错 {len(errs)} 人：{errs[0]!r}")

    # ── 双记忆：前情提要（长期）与今日计划 ─────────────────────────────
    # [EN] ── Dual memory: recap (long-term) and today's plan ─────────────────────────────
    @MODELS.agent('memory')
    async def _summarize_day(self, lines: list[str]) -> None:
        """把刚过去的一天压成一条前情提要（长期记忆）。

        素材：当天的导演事件 + 当天的叙事行。开销：**一天一次** cheap 调用 ——
        这是"双记忆"里长期那一半的全部成本。

        为什么值这个钱：没有它，推到第十天的人物只剩下"最近五条记忆"，
        前九天等于没发生过 —— 表现就是人物把早已了结的事当新闻、
        反复重新决定已经决定过的事。短期记忆（最近 K 条）解决不了这个，
        因为窗口一滑，旧的就永远出局了。
        
                English:
        Compress the day just past into a single recap (long-term memory).
                Source: the day's director events + the day's narrative lines. Cost: **once a day** cheap call --
                this is the entire cost of the long-term half of "dual memory".
                Why it is worth the money: without it, a character pushed to day ten only has "the most recent five memories",
                and the previous nine days might as well not have happened -- the symptom is that characters treat long-settled matters as news
                and repeatedly re-decide things already decided. Short-term memory (the most recent K items) cannot solve this,
                because once the window slides, the old ones are out forever.
        """
        day = int(self._current_day or self.world.game_day)
        try:
            events = [str(e.get("content") or "").strip()
                      for e in self.db.recent_events(30, game_day=day)]
        except Exception:                                    # noqa: BLE001
            events = []
        events = [e for e in events if e]
        narr = "\n".join(str(x) for x in lines if str(x).strip())
        if not events and not narr:
            return
        prompt = (f"下面是小说里第 {day} 天发生的事。请压成 **2~3 句前情提要**"
                  f"（总计 ≤ 80 字），用过去时叙述，只留对后文还有影响的；"
                  f"琐碎的动作和寒暄一律丢掉。\n\n"
                  f"【当天的事件】\n"
                  + ("\n".join(f"- {x}" for x in events[:12]) or "（无）")
                  + f"\n\n【当天的叙述】\n{narr[:1500] or '（无）'}\n\n"
                  f"只输出那 2~3 句话本身：不要标题、不要编号、不要解释。")
        try:
            # `SUMMARY_MODEL`（以前零读取）：日简摘要走哪一档。
            # 值是**模型角色名**（`MODEL_FRONT` / `MODEL_DAILY`），换算成档位。
            # [EN] `SUMMARY_MODEL` (previously never read): which tier the daily short summary uses.
            # [EN] The value is a **model role name** (`MODEL_FRONT` / `MODEL_DAILY`), converted to a tier.
            _key = (CFG.s("SUMMARY_MODEL") or "MODEL_FRONT").strip()
            _tier = "front" if _key == "MODEL_FRONT" else "daily"
            text = await llm.chat(_tier, [{"role": "user", "content": prompt}],
                                  purpose="day_summary", temperature=0.3)
        except Exception as e:                               # noqa: BLE001
            _LOG.warning("第 %d 天的前情提要生成失败（不影响推演）：%r", day, e)
            return
        # ⚠ 不许假设它一定是 str：MOCK 那边一度返回了 list，
        #   而 `list.strip()` 抛的异常正好被上面那句 except 吞掉 ——
        #   表现成"摘要从来没生成过"，日志里只有一行轻描淡写的 warning。
        # [EN] ⚠ Don't assume it's always a str: the MOCK side once returned a list,
        # [EN] and the exception thrown by `list.strip()` happened to be swallowed by the except above ——
        # [EN] manifesting as "summaries were never generated", with only a mild warning in the log.
        if isinstance(text, (list, tuple)):
            text = " ".join(str(x) for x in text if str(x).strip())
        text = str(text or "").strip()
        if text:
            self.db.add_summary(day, text)
            _LOG.info("第 %d 天前情提要：%s", day, text[:70])

    def _recap_text(self) -> str:
        """当天的「前情提要」（屏幕与日档共用同一个串）。

        ★ 用户 2026-10-07：「前情提要和场景介绍不能够丢」—— 以前它**只是喂给模型的
          上下文**（`agent._story_so_far` / 长期记忆），正文里一个字都没有
          （实测日档开头从 `> 在场：…` 直接进正文）。

        ★★ 2026-10-11：**续跑第一轮优先用「上一回说到」**（`self._resume_recap`）。
          用户报的「每次点起笔前情提要都一样」就是这个 —— 本轮 db 是新的空库，
          下面那三级全落空，只能退到设定集的开场白，于是每一轮念同一句。
          `_resume_recap` 用完即清（`_push_recap` 里），不让它污染每个日界。

        内容优先取**跨天摘要**（`summary` 表：粗颗粒、跨天累积）；没有就退到最近事件；
        **故事刚开始**（第一天 / 刚续上）则取设定集里的【世界观】那一段
        —— 用户 2026-10-07 又说：「每次推演开始一开始应该有一小段前情提要
        你这个也没有」（屏幕上确实一条都没有）。
        三样都没有 → **空串**（别写"这是第一天"这种废话充数）。
        复用 `director.day_plan` 那份实现（一份实现两处用）。
        
                English:
        The day's "recap" (screen and daily archive share the same string).
                ★ User 2026-10-07: "The recap and scene introduction must not be lost" -- previously it was **only context fed to the model**
                  (`agent._story_so_far` / long-term memory), with not a single word in the body
                  (measured: the daily archive start goes from `> 在场：…` straight into the body).
                ★★ 2026-10-11: **The first round of a resumed run prioritizes "previously on"** (`self._resume_recap`).
                  The user-reported "every time I click start, the recap is the same" is this -- this round's db is a new empty database,
                  all three fallback levels below miss, and it can only fall back to the setting collection's opening, so every round recites the same line.
                  `_resume_recap` is cleared after use (inside `_push_recap`), so it does not pollute every day boundary.
                Content prioritizes the **cross-day summary** (`summary` table: coarse-grained, accumulated across days); if absent, fall back to the most recent event;
                **at the very start of the story** (day one / just resumed), take the 【世界观】 passage from the setting collection
                -- user 2026-10-07 also said: "Every simulation should have a short recap at the start
                and you don't have this either" (indeed there was not a single line on screen).
                If all three are absent -> **empty string** (don't pad it with nonsense like "this is day one").
                Reuse the implementation in `director.day_plan` (one implementation used in two places).
        """
        if self._resume_recap.strip():
            return self._resume_recap
        try:
            return DAYPLAN.recap_text(self.db, world=self.world)
        except Exception:                                       # noqa: BLE001
            return ''

    def _push_recap(self) -> None:
        """把「前情提要」推到屏幕上（**每轮开头 + 每个日界**各一次）。

        用户 2026-10-07：「每次推演开始一开始应该有一小段前情提要 你这个
        也没有」—— 以前这段文字**只写进落盘文件**（`flush_daily_script`），
        屏幕上（中栏）一个字都没有。而作者是盯着屏幕读的。

        没有内容就**不推**（不写"这是第一天，前面还没发生什么"充数）。

        ⚠ 「上一回说到」是**一次性**的：推出去就清掉（见 `_recap_text`）——
          留着的话每个日界都念一遍上一轮的事，比念设定集还离谱。
        
                English:
        Push the "recap" to the screen (**once at the start of each round + once at each day
        boundary**).
                User 2026-10-07: "Every simulation should have a short recap at the start, and you
                don't have this either" -- previously this text was **only written to the disk file** (`flush_daily_script`),
                with not a single word on screen (middle column). And the author reads by staring at the screen.
                If there is no content, **do not push** (don't pad with "this is day one, nothing has happened yet").
                ⚠ "Previously on" is **one-shot**: once pushed it is cleared (see `_recap_text`) --
                  if kept, every day boundary would recite the previous round's events, which is even more absurd than reciting the setting collection.
        """
        text = self._recap_text()
        self._resume_recap = ""            # 一次性，用完即清
        # [EN] One-shot, cleared after use
        if not text.strip():
            return
        from display import story_render as _STR
        self._push_narrative(_STR.sentence(S.recap(text)), 1, kind=S.RECAP)
        _LOG.info('前情提要上屏：%s', ' '.join(text.split())[:60])

    def _push_author_note(self) -> None:
        """把**作者对本轮走向的要求**推到屏幕上（只在一轮开头推一次）。

        用户 2026-10-11：「我希望在起笔的时候，可以有一个地方加上用户自己对于
        故事接下来走向的建议。」—— 填在「起笔」对话框里那一栏，这里让它**看得见**。

        ★ 为什么"看得见"这一步不能省：填了话却没有任何回音，用户没法判断它到底
          生效了没有 —— 那种功能在本项目的说法叫"假按钮"。
          （实际的生效路径是 `crew/agents.craft_block()`：全剧组 14 个职位 ＋
          演员 ＋ 导演的提示词里都带着它，见 `sim/directive.py`。）

        ⚠ 没填就**什么都不推**（不留一行"（本轮没有作者要求）"那种废话）。
        ⚠ 不走 `display.script.recap`：那是"开演前的回顾"，语义不同；
          用 `NOTE`（机制标注那一类）——它同样不过剧情类的规则闸
          （见 `_REVIEW_KINDS` 的说明与 `_review_gate`）。
        
                English:
        Push **the author's requirements for this round's direction** to the screen (only once at the
        start of a round).
                User 2026-10-11: "I hope that when starting, there can be a place to add the user's own
                suggestions for where the story goes next." -- the field filled in the "start" dialog, here we make it **visible**.
                ★ Why the "visible" step cannot be skipped: if you fill in words but get no echo, the user cannot tell whether it
                  actually took effect -- that kind of feature is called a "fake button" in this project's terms.
                  (The actual effective path is `crew/agents.craft_block()`: all 14 positions in the crew +
                  actors + director have it in their prompts, see `sim/directive.py`.)
                ⚠ If not filled in, **push nothing at all** (no leaving a useless line like "(no author request this round)").
                ⚠ Do not use `display.script.recap`: that is a "pre-show recap", different semantics;
                  use `NOTE` (the mechanism-annotation category) -- it likewise bypasses the plot-type rule gate
                  (see the description in `_REVIEW_KINDS` and `_review_gate`).
        """
        line = str(getattr(self, '_author_note', '') or '')
        if not line:
            return
        from display import script as S
        from display import story_render as _STR
        self._push_narrative(_STR.sentence(S.note(line)), 0, kind=S.NOTE)
        _LOG.info('作者走向要求上屏：%s', ' '.join(line.split())[:60])

    def _crew_ctx(self, **kw):
        """当下这一刻的「拍摄现场」（剧组各职位都拿它当输入）。

        一份实现，所有职位共用 —— 免得每个职位各拼一遍材料、各漏一样
        （"某个人看不到前情"这种毛病最难查）。
        
                English:
        The "shooting scene" at this very moment (all crew positions take it as input).
                One implementation, shared by all positions -- so each position doesn't reassemble the material itself and miss something
                ("some person can't see the prior context" is the hardest kind of bug to track down).
        """
        from crew.agents import SetCtx
        return SetCtx(
            world=self.world, db=self.db,
            day=int(self._current_day or self.world.game_day or 1),
            people=[a.name for a in self.agents if a.ps.is_active()],
            # ★ 2026-10-21：把**自己**递进去，好让「要不要停」这件事传得到写稿那一侧
            #   （`write_check_retry(..., should_stop=...)`）。
            #   不传的话停止只作用于主循环，写稿那一侧会继续跑完两遍（实测 3 分钟）。
            # [EN] ★ 2026-10-21: hand **ourselves** in so 'should we stop' reaches the writing side
            # [EN] (`write_check_retry(..., should_stop=...)`). Without it, stop only affects the main
            # [EN] loop and the writing side keeps running two more passes (3 minutes measured).
            loop=self, **kw)

    def _day_lines(self, day_lines: list[str], scenes=None) -> list[str]:
        """当天真正上屏的那些行（收工后几个职位共用的材料）。

        ⚠ **一处实现**：`_crew_wrap`（场记/宣发/复盘）与 `_day_novel`（整理成小说）
          读的必须是同一份稿 —— 两处各拼一遍，迟早出现"复盘说今天有这场戏、
          整理稿里却没有"。

        剧本模式下 `_daily_narrative` 往往是空的（叙事走 builder 的 scenes），
        所以要把幕里的词条摊成行（用**剧本体**，那是落盘的真格式）。
        
                English:
        The lines actually shown on screen that day (material shared by several positions after wrap).
                ⚠ **Single implementation**: `_crew_wrap` (script supervisor/promotion/retrospective) and `_day_novel` (organizing into a novel)
                  must read the same draft -- assembling it twice separately will eventually produce "the retrospective says there was this scene today,
                  but the organized draft doesn't have it".
                In script mode `_daily_narrative` is often empty (narrative goes through builder's scenes),
                so the entries in the acts must be spread into lines (using **script form**, which is the real on-disk format).
        """
        lines = [str(x) for x in (day_lines or []) if str(x).strip()]
        groups = list(scenes or [])
        if not groups and self._builder is not None:
            groups = list(getattr(self._builder, 'scenes', None) or [])
            cur = getattr(self._builder, 'current', None)
            if cur is not None and cur not in groups:
                groups.append(cur)
        # ★★★ **以「这一幕一幕摊开」为准，`_daily_narrative` 只用来补漏**（2026-10-17 修）。
        #   以前是 `if not lines and groups:` —— 只要 `_daily_narrative` **有一行**，
        #   就完全不去看 `scenes`。而剧本模式下叙事走 builder 的 scenes，
        #   `_daily_narrative` 里往往只剩几位"出场"和一个事件（实测：**5 行**）：
        #
        #     〔出场〕主角（已在场）／〔出场〕柳氏（已在场）／〔出场〕阿福（已在场）
        #     〔事件 · 外部刺激〕门外有人驻足不走…／〔环境〕檐水一滴一滴…
        #
        #   后果是**整条下游全部塌掉**：
        #     · `_day_novel`（整理成小说）只拿到这 5 行 ⇒ 模型输出 **79 token**
        #       （实测日志 `crew_day_novel · 2153+79 token`），一天 4.4 万字的戏
        #       被整理成 900 字；
        #     · 导出时那份 900 字又**整份替换**掉 4.3 万字的可读稿 ⇒
        #       用户看到的《小说版本》只有 1,185 字（"为何导出的内容非常少"）；
        #     · `_crew_wrap`（场记连戏检查）也只看到这 5 行 ⇒ 它当然查不出连戏错误。
        #   ⇒ 现在改成：**先把 scenes 摊成行**（那是完整的、按时间顺序的、
        #     也正是落盘 `每天的生活/第NNN天.md` 用的那一份），
        #     再把 `_daily_narrative` 里**不在其中**的行补进去（去重保序）。
        #   ⚠ 补漏这一步不能省：非剧本模式下 `scenes` 是空的，全靠 `lines`；
        #     而剧本模式下 `_daily_narrative` 也可能含 scenes 里没有的旁白行。
        # [EN] ★★★ **Take "spread every scene" as the source of truth; `_daily_narrative` only fills
        # [EN] gaps** (fixed 2026-10-17).
        # [EN] It used to be `if not lines and groups:` -- as long as `_daily_narrative` had **one
        # [EN] line**, `scenes` was never consulted. But in script mode the narrative goes through the
        # [EN] builder's scenes, and `_daily_narrative` often retains only a few "entrances" plus one
        # [EN] event (measured: **5 lines**):
        # [EN]   〔entrance〕Shen Yan / 〔entrance〕Liu-shi / 〔entrance〕A-Fu
        # [EN]   〔event〕someone lingers outside the door / 〔environment〕eaves drip...
        # [EN] The consequence is that **the whole downstream collapses**:
        # [EN]   · `_day_novel` (organize into a novel) receives only those 5 lines => the model emits
        # [EN]     **79 tokens** (measured log `crew_day_novel · 2153+79 token`); a day of 44k characters
        # [EN]     becomes 900 characters;
        # [EN]   · at export that 900 characters **replaces the whole** 43k readable draft => the
        # [EN]     "小说版本" the user sees is only 1,185 characters ("why is the export so thin?");
        # [EN]   · `_crew_wrap` (continuity check) also sees only those 5 lines => of course it can never
        # [EN]     find a continuity error.
        # [EN] => Now: **first spread scenes into lines** (that's the complete, chronological copy,
        # [EN]    and exactly the one used to persist `每天的生活/第NNN天.md`), then append the lines in
        # [EN]    `_daily_narrative` that are **not already there** (dedupe, keep order).
        # [EN] ⚠ The gap-filling step must not be removed: in non-script mode `scenes` is empty and
        # [EN]   everything relies on `lines`; and even in script mode `_daily_narrative` may carry
        # [EN]   narration that scenes don't have.
        out: list[str] = []
        if groups:
            from display import script_render as _SR
            for _i, sc in enumerate(groups, 1):
                # ★★★ **每一幕先给一行幕头**（2026-10-19 第六轮）。
                #
                #   用户贴出的分析第一条就是「时序与因果关系的混乱（最严重的问题）」：
                #   「岛村两次说"终于到了，先休息一下吧"…整个时间线像是被打乱的拼图」。
                #   查下来根因在**这里**：`SceneScript` 明明带 `time_label`
                #   （"子时 23:40"），但摊成行时**把它丢了** —— 整理层拿到的是一串
                #   "谁说了什么"，**完全不含时间**。没有时间，模型只能自己编
                #   "夜深了""终于到了"，于是同一句"夜深了"出现在三个不该出现的地方。
                #   ⇒ 幕头这一行是**唯一的时间真相**，必须进材料。
                #   ⚠ 只加幕头、不改任何一条正文行的格式：下游按"行"读的地方
                #     （场记连戏检查等）看到的仍是同样的行，只是多了边界。
                # [EN] ★★★ **One header line per act** (round six). The user's own analysis puts
                # [EN] "scrambled chronology" first: "Island Village says 'finally arrived, rest a
                # [EN] bit' twice ... the timeline is a shuffled puzzle". The root cause is here:
                # [EN] `SceneScript` carries `time_label` ("子时 23:40") but spreading it into lines
                # [EN] **dropped it** -- the organizer received "who said what" with **no time at
                # [EN] all**, so the model could only invent "it is late" and "finally arrived",
                # [EN] landing the same phrase in three wrong places. The header is the **single
                # [EN] source of time** and must reach the material.
                _tl = str(getattr(sc, 'time_label', '') or '').strip()
                _pl = str(getattr(sc, 'place', '') or '').strip()
                _nm = str(getattr(sc, 'node_name', '') or '').strip()
                _bits = [f'第 {_i} 幕']
                if _tl:
                    _bits.append(_tl)
                if _pl:
                    _bits.append(_pl)
                if _nm:
                    _bits.append(_nm)
                out.append('〔' + ' · '.join(_bits) + '〕')
                for e in (getattr(sc, 'entries', None) or []):
                    one = _SR.one_line(e)
                    if one:
                        out.append(one)
        if out:
            seen = set(out)
            for ln in lines:
                if ln not in seen:
                    seen.add(ln)
                    out.append(ln)
            return out
        return lines

    async def _day_novel(self, day_lines: list[str], scenes=None) -> None:
        """**整理当天这一章**（用户 2026-10-07）。

        「每天总结你看下包含当天故事整理吗(整理成小说形式)」——
        收工时让**小说作家**把今天实际发生的写成小说形式，两处用得起：

          · `当天故事.md` —— **按天累积**的一份可读稿（第二天早上还在）；
          · `今日总结.md` —— 追加一节「今天这一章（整理稿）」，与复盘并列。

        ⚠ 为什么另起一份 `当天故事.md` 而不是只塞进「今日总结」：
          后者**每天被复盘覆盖**（那是"今天的体检报告"），三天后回头看
          就只剩第三天了；而"把每天整理成小说"这件事的价值恰恰在**能连着读**。
        
                English:
        **Organize today's chapter** (user 2026-10-07).
                "For the daily summary, check whether it includes organizing that day's story (organized into novel form)" --
                at wrap time let the **novelist** write what actually happened today in novel form; it's usable in two places:
                  · `当天故事.md` -- a readable draft **accumulated by day** (still there the next morning);
                  · `今日总结.md` -- append a section "Today's chapter (organized draft)", alongside the retrospective.
                ⚠ Why start a separate `当天故事.md` instead of just stuffing it into "today's summary":
                  the latter is **overwritten by the retrospective every day** (that's "today's health report"), so looking back after three days
                  only the third day remains; whereas the value of "organizing each day into a novel" is precisely that it **can be read continuously**.
        """
        if not (CFG.b('CREW') and CFG.b('CREW_DAY_NOVEL')):
            return
        if self.runfolder is None:
            return
        try:
            lines = self._day_lines(day_lines, scenes)
            if not lines:
                _LOG.info('第 %d 天：今天没有可整理的正文（跳过整理）',
                          int(self._current_day or 0))
                return
            ctx = self._crew_ctx(story=str(getattr(self._day_script, 'story', '') or ''))
            with self._stage('novelize'):
                note = await self.studio.day_novel(ctx, raw='\n'.join(lines))
            if note is None or not note.ok:
                _LOG.info('第 %d 天：当天这一章没整理出来（%s）',
                          int(self._current_day or 0),
                          str(getattr(note, 'why', '') or '没有产出')[:80])
                return
            text = str(note.body or '').strip()
            if not text:
                return
            day = int(self._current_day or 0)
            head = (f'## 第 {day} 天 · {self.world.clock_display(with_day=False)}'
                    if day else '## 这一天')
            book = Path(self.runfolder.root) / CREWSTUDIO.FILE_DAY_NOVEL
            old = book.read_text(encoding='utf-8') if book.is_file() else ''
            if not old.strip():
                old = ('# 当天故事\n\n> 每天收工后，由剧组的小说作家把这一天实际发生的'
                       '整理成小说。\n> 它是**过程稿**（供作者回头读、对照与改写），'
                       '与导出的「小说版本」是两件事：\n'
                       '> 那份是**装订成书**的，这份是**按天累积**的工作本。\n')
            atomic_write_text(book, old.rstrip() + f'\n\n{head}\n\n{text}\n')
            # 并进「今日总结」（用户点名：总结里要有当天故事整理）
            # [EN] Merge into "Today's Summary" (user explicitly asked: the summary must include the day's story
            # [EN] organization)
            review = Path(self.runfolder.root) / CREWSTUDIO.FILE_REVIEW
            base = review.read_text(encoding='utf-8') if review.is_file() else ''
            atomic_write_text(
                review, base.rstrip()
                + f'\n\n---\n\n## 今天这一章（整理稿）\n\n{text}\n')
            _LOG.info('第 %d 天：当天这一章已整理（%d 字）', day, len(text))
            # ★★★ 2026-10-21（用户点名）：「点击停止的时候、或者某次推演结束的时候，
            #   可以自动把根据推演生成的小说输出到推演窗口里（默认可以是收起来的，
            #   用户点了才展开，或者这个是收还是展开用户可以配置）」。
            #
            #   ⚠ 这里写的是**收工那一处**（每天收工都整理一章）；"点停止"那一处
            #     在 `_end_day` 的调用链上共用同一条路，所以只加这一处不会漏。
            #   ⚠ 用 `S.NOVEL` 而不是 `S.NOTE`：几百到几千字的成篇正文混进 NOTE
            #     会被"一行一条"的排版压扁，读者没法读（见 `display/script.NOVEL`）。
            #   ⚠ 推送**失败不许影响推演**：它只是展示，落盘已经完成了。
            # [EN] ★★★ 2026-10-21 (named by the user): on stop, or when a run finishes, the novel
            # [EN] generated from the simulation should appear in the simulation window by itself --
            # [EN] collapsed by default, expandable on click, and configurable.
            # [EN] ⚠ This is the **wrap-time** site (one chapter per day); the "hit stop" path shares
            # [EN] the same call chain, so this single addition covers both.
            # [EN] ⚠ Use `S.NOVEL`, not `S.NOTE`: a multi-thousand-character finished text squashed
            # [EN] into a one-line-per-entry layout is unreadable (see `display/script.NOVEL`).
            # [EN] ⚠ A push failure must never affect the simulation -- it is display only, and the
            # [EN] file has already been written.
            try:
                if CFG.b('SHOW_NOVEL_IN_WINDOW'):
                    self._push_narrative(text, 2, kind=S.NOVEL)
                    # 记一笔：停止时那道兜底（`_flush_novel_on_stop`）靠它避开"同一天推两章"。
                    # ⚠ 惰性取：`RunLoop` 有几条不走 `__init__` 的构造路径（老夹具在用），
                    #   直接 `self._novel_pushed_days.add()` 会让那些路径 `AttributeError`。
                    # [EN] Record it: the stop-time fallback (`_flush_novel_on_stop`) uses this to avoid
                    # [EN] pushing the same day twice. ⚠ Fetch lazily: some `RunLoop` construction paths
                    # [EN] skip `__init__` (old fixtures), and a bare attribute access would raise.
                    _seen = getattr(self, '_novel_pushed_days', None)
                    if _seen is None:
                        _seen = set()
                        self._novel_pushed_days = _seen
                    _seen.add(int(day or 0))
            except Exception as _pe:                          # noqa: BLE001
                _LOG.warning('把这一章推到窗口失败（不影响落盘）：%r', _pe)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('整理当天这一章失败（不影响推演）：%r', e)

    async def _crew_wrap(self, day_lines: list[str], scenes=None) -> None:
        """**收工后**：场记连戏检查 + 宣发一句话（见 `crew/studio.py`）。

        `day_lines` = 当天推给屏幕的叙事行（**清空之前**抓的那一份）。
        剧本模式下 `_daily_narrative` 往往是空的（叙事走 builder 的 scenes），
        所以这里还要把幕里的词条补上 —— 不然场记手上会是一份空白稿。

        ★ `scenes` = **今天落盘的那几幕**（`_end_day` 手里有，直接递进来）。
        ⚠ 2026-10-07 修：以前这里**只从 `self._builder` 取**，而 `_end_day`
          里 `self._builder = None` 排在调本方法**之前** —— 于是正式流程下
          这条路**永远走不通**，场记每次都报"今天没有可查的正文"、
          宣发报"还没有可宣的内容"。表现是「剧组那两位天天不出活」，
          而它们在探针里（直接调 `_crew_wrap`、没走 `_end_day`）却是好的
          —— 最难查的那种"只在真机上坏"。`_builder` 那条退路留着，
          给测试/探针用（那时手上的幕可能还在 `current` 上）。
        
                English:
        **After wrap**: script supervisor continuity check + promotion one-liner (see `crew/studio.py`).
                `day_lines` = the narrative lines pushed to the screen that day (the copy captured **before clearing**).
                In script mode `_daily_narrative` is often empty (narrative goes through builder's scenes),
                so here the entries in the acts must also be added -- otherwise the script supervisor ends up with a blank draft.
                ★ `scenes` = **the acts saved to disk today** (`_end_day` has them; passed in directly).
                ⚠ 2026-10-07 fix: previously here it **only took from `self._builder`**, while in `_end_day`
                  `self._builder = None` was placed **before** calling this method -- so under the normal flow
                  this path **never worked**, the script supervisor reported "no main text to check today" every time,
                  and promotion reported "no content to promote yet". The symptom was "those two crew members never produce anything",
                  yet in probes (calling `_crew_wrap` directly, not going through `_end_day`) they were fine
                  -- the hardest kind of "only breaks on the real thing". The `_builder` fallback is kept,
                  for tests/probes (at that time the acts in hand may still be on `current`).
        """
        if not CFG.b('CREW'):
            return
        try:
            # ★ 当天那份稿只取一次（`_day_lines`）—— 场记/宣发/复盘与
            #   `_day_novel`（整理成小说）读的必须是**同一份**。
            # [EN] ★ Today's script is read only once (`_day_lines`) —— script supervisor/publicity/retrospective
            # [EN] and
            # [EN] `_day_novel` (organized into a novel) must read the **same copy**.
            lines = self._day_lines(day_lines, scenes)
            ctx = self._crew_ctx(story=str(getattr(self._day_script, 'story', '') or ''),
                                 beats=list(getattr(self._day_script, 'beats', None)
                                            or []))
            # ★ **一天结束后讨论**（用户点名要显示的一条阶段消息）。
            #   它盖住的是"收工这一整段"（场记 → 宣发 → 语言审校 → 复盘），
            #   里面每一步各自的产出照旧只进日志与落盘。
            # [EN] ★ **End-of-day discussion** (a stage message the user explicitly asked to display).
            # [EN] It covers the whole "wrapping up" stretch (script supervisor → publicity → language review →
            # [EN] retrospective),
            # [EN] and each step's own output still only goes to the log and to disk as before.
            with self._stage('day_review'):
                notes = await self.studio.wrap(ctx, lines=lines)
            # 台账另存一份 JSON（界面/验证脚本读它，不用解析 Markdown）
            # [EN] Save the ledger as a separate JSON (the UI/verification scripts read it, no need to parse
            # [EN] Markdown)
            self.studio.save_sidecar()
            hit = [CREWSTUDIO.ROSTER.role(n.role).name for n in notes if n.ok]
            if hit:
                _LOG.info('第 %d 天收工：%s', self._current_day, '、'.join(hit))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('剧组收工失败（不影响推演）：%r', e)

    async def _crew_prep(self) -> None:
        """**开拍前**：美术 + 道具先出工（见 `crew/studio.py` 的班次说明）。

        顺序有意：**先定画面再写本子**。反了的话道具单只是照着已成稿的戏
        凑出来的，它就不再是创作决定、而只是事后记录。
        
                English:
        **Before shooting starts**: art + props go to work first (see the shift description in
        `crew/studio.py`).
                The order is intentional: **decide the visuals first, then write the script**. If reversed, the prop list is merely
                assembled to match an already-finished play, and it is no longer a creative decision but only an after-the-fact record.
        """
        if not CFG.b('CREW'):
            return
        try:
            ctx = self._crew_ctx()
            got = await self.studio.preproduction(ctx)
            names = '、'.join(CREWSTUDIO.ROSTER.role(k).name
                              for k, v in got.items() if v.ok)
            if names:
                _LOG.info('第 %d 天开拍前：%s已出工', ctx.day, names)
            # ★★ **造型 → 演员**（2026-10-07 审计补上）。
            # [EN] ★★ **Styling → Actor** (added in the 2026-10-07 audit).
            # 名册里写着 `stylist.feeds='actor'`，而这行调用以前不存在 ——
            # 造型每天都出工、每天都落一份 `造型表.md`，演员却**一个字都看不到**。
            # 于是"同一件旧布衫三天三种写法"照旧发生（那正是造型存在的理由）。
            # [EN] The roster says `stylist.feeds='actor'`, yet this line of the call didn't exist before ——
            # [EN] styling worked every day and persisted a `造型表.md` daily, yet the actor **couldn't see a single
            # [EN] word**.
            # [EN] So "the same old cloth shirt written three different ways across three days" kept happening
            # [EN] (that's exactly why styling exists).
            # 送法：写进 `world.stylist_brief`，由 `agent/core._semi` 拼成
            # `[你身上]` 那一段 —— 它是**规定情境**的一部分（我穿着什么、
            # 身上带着什么），不是目标，所以不走目标金字塔。
            # [EN] Delivery: write into `world.stylist_brief`, which `agent/core._semi` assembles into
            # [EN] the `[你身上]` section —— it's part of the **given circumstances** (what I'm wearing,
            # [EN] what I'm carrying), not a goal, so it doesn't go through the goal pyramid.
            try:
                brief = self.studio.stylist_brief(got.get('stylist'))
                if brief:
                    self.world.stylist_brief = brief
                    _LOG.info('第 %d 天造型已交给演员：%d 字', ctx.day, len(brief))
            except Exception as e:                               # noqa: BLE001
                _LOG.warning('造型材料装配失败（不影响推演）：%r', e)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('开拍前的美术/道具出工失败（不影响推演）：%r', e)

    async def _setting_room(self) -> None:
        """**开拍前的编剧室会审**：导演 · 小说作家 · 剧作者 补**局部**设定。

        用户 2026-10-07：「有些时候需要导演 和 小说作者 以及 剧作家 讨论生成
        一些新的设定 这些都要进行推演 以便方便故事推进 同时不能够影响总体设定」

        三件事各自的位置：

        | 要求 | 落在哪 |
        |---|---|
        | 三方讨论生成新设定 | `crew/agents.SettingsRoom`（一次调用演三方会审） |
        | **要进行推演** | 收下的设定进 `world.local_settings` → `world_prefix()` 按层渲染，作家/剧作者/演员都看得到 |
        | **不能够影响总体设定** | `world/layers.admit_new` 两道闸门（只许场景层/细节层 + 必须有作用范围），且与设定集**物理隔离** |

        ⚠ 调用点在 `_compose_day()` 里、`DAYPLAN.compose()` **之前** ——
          先补设定再动笔。反过来的话新设定对这一天就没有影响了，
          而用户要的正是"以便方便故事推进"。

        `CREW_SETTING_EVERY_DAYS` 控制频率（默认隔天一次）；模型没有需要时
        会返回空数组，那时**照样算一次合格的出工**（"不用补"也是结论）。
        
                English:
        **Writers' room review before shooting starts**: director · novelist · playwright supplement
        **local** settings.
                User 2026-10-07: "Sometimes the director and the novelist and the playwright need to discuss and generate
                some new settings, all of these must be simulated/inferred so as to facilitate story advancement, while also not being able to affect the overall settings"
                The position of each of the three things:
                | Requirement | Where it lands |
                |---|---|
                | Three-way discussion generating new settings | `crew/agents.SettingsRoom` (one call stages a three-way review) |
                | **Must be simulated/inferred** | accepted settings enter `world.local_settings` → `world_prefix()` renders by layer, visible to novelist/playwright/actors |
                | **Must not affect the overall settings** | two gates in `world/layers.admit_new` (only scene layer/detail layer allowed + must have a scope of effect), and **physically isolated** from the settings collection |
                ⚠ The call site is in `_compose_day()`, **before** `DAYPLAN.compose()` --
                  supplement the settings first, then start writing. Otherwise the new settings would have no effect on that day,
                  and what the user wants is precisely "so as to facilitate story advancement".
                `CREW_SETTING_EVERY_DAYS` controls the frequency (default: every other day); when the model doesn't need it
                it returns an empty array, and that still **counts as a valid day's work** ("no need to fill in" is also a conclusion).
        """
        if not (CFG.b('CREW') and CFG.b('CREW_SETTING_TALK') and CFG.b('SETTING_LAYERS')):
            return
        day = int(self._current_day or self.world.game_day or 1)
        every = max(1, CFG.i('CREW_SETTING_EVERY_DAYS'))
        if (day - 1) % every:
            return
        try:
            before = len(getattr(self.world, 'local_settings', None) or [])
            ctx = self._crew_ctx()
            note = await self.studio.setting_room(ctx)
            after = len(getattr(self.world, 'local_settings', None) or [])
            if after > before:
                # 落一份给人看的（`临时设定.md` / `.json`）——
                # 这个文件**只有一个写入方**（见 `crew/studio.ARTIFACT` 的注释）。
                # [EN] this file has **only one writer** (see the comment in `crew/studio.ARTIFACT`).
                try:
                    from world import layers as _L
                    _L.save_local(self.runfolder.root, self.world)
                except Exception as e:                           # noqa: BLE001
                    _LOG.warning('临时设定落盘失败（不影响推演）：%r', e)
                _LOG.info('第 %d 天编剧室：新增 %d 条局部设定', day, after - before)
                self._push_narrative(f'（编剧室 · 第 {day} 天）{note.one_line()}', 1,
                                     kind=S.NOTE)
            elif note is not None and note.ok:
                _LOG.info('第 %d 天编剧室：不需要补设定', day)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('编剧室会审失败（不影响推演）：%r', e)

    def _carry_unplayed_beats(self) -> dict | None:
        """**跨天事件**：把这一站还没演完的分拍打包，交给下一天接着演（2026-10-26）。

        用户：「注意 一个事件可能跨天」。

        以前日界**无条件**重新规划一整天：第 2 天早上又写一份新故事、新分拍，
        于是一个本该跨三天的事件被切成三件互不相干的事 —— 而且每天从 08:00 重新开场。

        现在的口径：
          · 这一站的**跨度是 `数日` / `一旬` / `数月`**（作者写了，或程序推的）⇒ 它本来就要跨天；
          · 而且**还有没演的拍**（`_ticks_today` 少于分拍总数）⇒ 打包带走。
          两条都满足才带；否则返回 `None`，下一天照常规划（= 旧行为，逐字不动）。

        ⚠ 「演了几拍」的算法是 `min(_ticks_today, 分拍数)` —— 用拍数是**保守**的：
          一拍没演完时宁可多带一拍（重演一点），也不要少带（丢戏）。
        ⚠ 带上的是**还没演的那几拍**，不是全部：全部带走会让进度原地踏步（同一批戏演两遍）。
        ⚠ 打包里带上 `from_day` 与 `budget`：日志与界面要能说清"这几天是在演同一站"。
        [EN] **Cross-day event**: pack this station's un-played beats so the next day continues them.
        [EN] An event meant to span three days used to be re-planned into three unrelated ones, each
        [EN] reopening at 08:00. Now: carry only when the station's span is `数日`/`一旬`/`数月`
        [EN] **and** beats genuinely remain; otherwise return `None` (old behaviour, byte-identical).
        [EN] ⚠ "how many played" is `min(_ticks_today, len(beats))` -- deliberately conservative: one
        [EN] extra beat replayed is better than one lost. ⚠ It carries only the **remainder**, not all
        [EN] beats, or the same stretch would replay forever. ⚠ `from_day` / `budget` ride along so
        [EN] logs and UI can say "these days are still the same station".
        """
        ds = getattr(self, '_day_script', None)
        if ds is None:
            return None
        beats = list(getattr(ds, 'beats', None) or [])
        if not beats:
            return None
        # ① 这一站是不是"本来就跨天"的那一档
        span = ''
        try:
            node = DAYPLAN.current_node_of(self.world, self.db)
            if node:
                span = str(node.get('跨度') or '').strip()
                if not span:
                    from ingest.progress import ProgressNode, infer_span
                    span = infer_span(ProgressNode(
                        id=str(node.get('id') or ''),
                        name=str(node.get('名称') or ''),
                        summary=str(node.get('概要') or ''),
                        criteria=''))
        except Exception:                                        # noqa: BLE001
            span = ''
        if span not in ('数日', '一旬', '数月'):
            return None
        # ② 还有没有没演的拍
        played = min(int(self._ticks_today or 0), len(beats))
        left = beats[played:]
        if not left:
            return None
        return {
            'story': str(getattr(ds, 'story', '') or ''),
            'beats': left,
            'roles': dict(getattr(ds, 'roles', None) or {}),
            'budget': tuple(getattr(ds, 'budget', ()) or ()),
            'from_day': int(self._current_day or 0),
            'played': played,
        }

    async def _compose_day(self) -> None:
        """跨天时**编剧组先定框架**：写当天样章 → 改写成剧本 → 分派到人。

        用户 2026-10-07：「在一天开始之前 导演自己心里要根据前后背景以及小说整体设定
        把当天要演的故事写好 切记要贴合故事发展 然后在根据人物改写成剧本 然后分配给
        不同的角色 然后再开眼 每个角色可以有自己适当的返回 但是总体框架不能够超过
        导演写的故事 而且导演写故事和剧本之后要反复验算下是否跟整个故事是顺起来的」

        ★ 2026-10-07 再改：这两步**由剧组的专业人士做** ——
          小说作家写原著样章（读叙事章法），剧作者把它改成能拍的剧本
          （读剧作与舞台 / 编剧正典），导演验算。见 `crew/agents.py`。

        以前这里只有 `_plan_day()` —— 那是**每个角色各自**排计划，十二个人各排各的、
        谁也不管谁，合起来不构成一个故事（屏幕上就是"大家都在做自己的小事"）。
        `_plan_day()` 仍排在它**之后**，各人的计划落在框架之内。

        ⚠ 拿不到（模型失败 / 关掉 / 空返回）就**照旧跑**，只是这一天没有框架
          —— `_day_script` 保持 None，提示词里就不出现〔今日剧本〕。
          **不许假装有**（编一段假的比没有更坏）。
        
                English:
        Across days, **the writers' room sets the framework first**: write the day's sample chapter →
        adapt it into a script → assign to individuals.
                User 2026-10-07: "Before a day begins, the director must, based on the surrounding context and the novel's overall setting,
                write out the story to be performed that day — remember to stay true to the story's development — then adapt it into a script according to the characters, then assign it to
                the different characters, then open the eyes. Each character may give their own appropriate response, but the overall framework must not exceed
                the story the director wrote. And after writing the story and the script, the director must repeatedly verify whether it is consistent with the whole story."
                ★ 2026-10-07 revised again: these two steps are **done by the crew's professionals** ——
                  the novelist writes the original sample chapter (reading narrative craft), the playwright adapts it into a shootable script
                  (reading drama and stage / screenwriting canon), the director verifies. See `crew/agents.py`.
                Previously there was only `_plan_day()` here —— that was **each character scheduling their own** plan, twelve people each doing their own,
                nobody minding anybody, together not forming a story (on screen it's just "everyone doing their own little thing").
                `_plan_day()` still runs **after** it, and each person's plan falls within the framework.
                ⚠ If unavailable (model failure / turned off / empty return), **just run as usual**; it's only that this day has no framework
                  —— `_day_script` stays None, and 〔今日剧本〕 won't appear in the prompt.
                  **Do not pretend there is one** (making up a fake one is worse than none).
        """
        self._day_script = None
        #: ★★ **今天的场次编排**（`director.stage.StagePlan`，2026-10-11）——
        #: 把剧作家的分拍表变成"现在第几拍、这场戏演完了没有"的状态。
        #: 演员的提示词读它、导演的收场与换场按它走。
        #: `None` = 这一天没有分拍（或这一层关着）⇒ 行为与加它之前**逐字相同**。
        # [EN] : ★★ **Today's stage schedule** (`director.stage.StagePlan`, 2026-10-11) --
        # [EN] : turns the playwright's beat sheet into the state "which beat we are on, is this scene
        # [EN] : finished". The actors' prompts read it, and the director wraps up / changes scene by
        # [EN] : it. `None` = no beat breakdown today (or this layer is off) ⇒ behavior is
        # [EN] : **byte-for-byte identical** to before it existed.
        self._stage_plan = None
        # ★ **当天这张小地图**（`Layout`）：由剧组美术在**当天剧本写完之后**画，
        #   取景范围 = 今天这几场戏涉及到的地点。界面读它画左栏小地图
        #   （见 `gui/app_flet._draw_minimap`）。`None` = 今天还没有图，界面退回旧做法。
        # [EN] ★ **Today's little map** (`Layout`): drawn by the crew's art department **after today's script
        # [EN] is written**,
        # [EN] coverage = the locations involved in today's scenes. The UI reads it to draw the left-column
        # [EN] minimap
        # [EN] (see `gui/app_flet._draw_minimap`). `None` = no map for today yet, the UI falls back to the old
        # [EN] approach.
        self.day_map = None
        if not CFG.b('DAY_PLAN'):
            return
        people = [a.name for a in self.agents if a.ps.is_active()]
        if not people:
            return
        self._status('planning', n=len(people))
        # ★★ **先开编剧室**（导演·作家·剧作者会审，补局部设定）——
        #   用户 2026-10-07：「有些时候需要导演 和 小说作者 以及 剧作家 讨论生成
        #   一些新的设定 这些都要进行推演 以便方便故事推进 同时不能够影响总体设定」。
        #   顺序是要求的一部分：**先补设定、再写样章**（新设定才进得了这一天的戏）。
        # [EN] ★★ **Open the writers' room first** (director · novelist · playwright review, fill in local
        # [EN] settings) ——
        # [EN] User 2026-10-07: "Sometimes the director and the novelist and the playwright need to discuss and
        # [EN] generate
        # [EN] some new settings, all of which need to be reasoned through to facilitate story progression,
        # [EN] while not affecting the overall setting."
        # [EN] The order is part of the requirement: **fill in settings first, then write the sample chapter**
        # [EN] (only new settings can make it into this day's scenes).
        with self._stage('setting_room'):
            await self._setting_room()
        # ★ 请求停止就别再往下写了（见 `_open_day` 那段说明）——
        #   这一天没有框架，下游照旧跑得下去。
        # [EN] ★ If a stop is requested, don't keep writing (see the explanation in `_open_day`) ——
        # [EN] this day has no framework, and downstream can still run as before.
        if self.stopping:
            _LOG.info('收到停止请求，第 %d 天不再写剧本', self.world.game_day)
            return
        # ★★★ 2026-10-26（用户：「注意 一个事件可能跨天」）：
        #   **先看上一站的戏演完了没有**。没演完就接着演，**不再重新规划一整天**。
        #
        #   以前这里无条件调 `DAYPLAN.compose` 写一份全新的当天故事 + 全新分拍 —— 于是
        #   一个本该跨三天的事件，第二天早上会被"重新规划"成另一件事，线就断了
        #   （这也是"每天都从早上八点重新开场"的由来）。
        #   ⇒ 现在：跨天事件（跨度=数日/一旬/数月）把手上的**剩余分拍**带到下一天，
        #     既不断线，也省掉一整套编剧室调用（样章+剧本+验算+排练）。
        #
        #   ⚠ 只在**真的有剩拍**时才带；分拍演完了就照常规划新的一天。
        #   ⚠ 带过来的那一天**仍按原预算收束**（预算是那一站的，不按天数重算）。
        # [EN] ★★★ 2026-10-26 (user: "note, one event may span days"): **first check whether the
        # [EN] current station's beats are finished.** If not, keep playing them instead of re-planning
        # [EN] a whole new day. Previously this unconditionally called `DAYPLAN.compose`, so an event
        # [EN] meant to span three days got re-planned into something else on the morning of day two --
        # [EN] the thread broke (and every day reopened at 08:00 from scratch). Now a cross-day event
        # [EN] carries its **remaining beats** into the next day, saving a whole writers'-room round too.
        # [EN] ⚠ Only when beats genuinely remain; the same budget still governs that day.
        _carry = getattr(self, '_event_carry', None)
        _carried = False
        if _carry:
            self._event_carry = None
            try:
                ds = DAYPLAN.DayScript(
                    day=int(getattr(self.world, 'game_day', 1) or 1),
                    story=str(_carry.get('story') or ''),
                    beats=list(_carry.get('beats') or []),
                    roles=dict(_carry.get('roles') or {}),
                    budget=tuple(_carry.get('budget') or ()),
                )
                ds.source = 'carry'
                # 场次索引从 0 起：带过来的是"这一站还没演的那几拍"，对它们而言就是第 0 拍
                # [EN] Stage index starts at 0: what was carried over is the un-played remainder.
                self.world.stage_index = 0
                _LOG.info('第 %d 天：接着演上一站没演完的戏（%d 拍，来自第 %d 天，预算 %s）',
                          ds.day, len(ds.beats), int(_carry.get('from_day') or 0),
                          ds.budget or '未记')
                _carried = True
            except Exception as e:                              # noqa: BLE001
                _LOG.warning('跨天事件续演失败，改为正常规划这一天：%r', e)
                _carried = False
        if not _carried:
            try:
                ds = await DAYPLAN.compose(self.world, self.db, people=people,
                                           studio=self.studio)
            except Exception as e:                              # noqa: BLE001
                _LOG.warning("当日剧本生成失败（按无框架继续推演）：%r", e)
                return
        # ⚠ 判据是"**两样都没有**"，不是"没有 story"（2026-10-11）：
        #   模型偶尔写得出分拍、却没给当天梗概 —— 那种日子照样该按拍演
        #   （`_frame_line` 的「本场戏」那段与 `story` 无关，见 `Agent._stage_line`）。
        # [EN] ⚠ The criterion is "**neither of the two exists**", not "no story" (2026-10-11):
        # [EN] occasionally the model produces beats but no synopsis for the day -- such a day should
        # [EN] still be played beat by beat (the "this scene" block in `_frame_line` has nothing to do
        # [EN] with `story`, see `Agent._stage_line`).
        if not ds.story and not (getattr(ds, 'beats', None) or []):
            return
        self._day_script = ds
        # ★★ **建今天的场次状态机**（2026-10-11）—— 剧作家的分拍表**从这一刻起才
        #   算真的下达**：演员的提示词读它（`Agent._frame_line`），导演的收场与
        #   换场按它走（`_maybe_close_beat` / `_stage_place_to`）。
        #   ⚠ 底线：**没有分拍就不建**（`beats` 空 ⇒ `self._stage_plan is None`），
        #     这一天的推演与加这一层之前**逐字相同**。
        #   ⚠ 续跑时从 `world.stage_index` 接着走 —— 不然会从第 1 拍重来
        #     （"昨天已经演到第 4 拍了"会被忘掉）。
        # [EN] ★★ **Build today's stage state machine** (2026-10-11) -- only from this moment is the
        # [EN] playwright's beat sheet really handed down: the actors' prompts read it
        # [EN] (`Agent._frame_line`), and the director wraps up / changes scene by it
        # [EN] (`_maybe_close_beat` / `_stage_place_to`).
        # [EN] ⚠ Bottom line: **no beats, no machine** (empty `beats` ⇒ `self._stage_plan is None`), and that
        # [EN] day's simulation is **byte-for-byte identical** to before this layer.
        # [EN] ⚠ On a resume it continues from `world.stage_index` -- otherwise it restarts at beat 1
        # [EN] (forgetting "we were already on beat 4").
        try:
            from director import stage as STAGE
            _built = STAGE.StagePlan(
                list(getattr(ds, 'beats', None) or []),
                day=int(getattr(self.world, 'game_day', 1) or 1),
                start_index=int(getattr(self.world, 'stage_index', 0) or 0))
            self._stage_plan = _built if _built.beats else None
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning("场次编排没建起来（按无分拍继续）：%r", e)
            self._stage_plan = None
        if self._stage_plan is not None:
            _LOG.info('场次编排就绪：%d 拍，从第 %d 拍起', self._stage_plan.total,
                      self._stage_plan.index)
        # 挂到世界上：人物的决策提示词要从这里取〔今日剧本〕（`Agent._frame_line`）。
        # [EN] Hang it on the world: characters' decision prompts read 〔今日剧本〕 from here (`Agent._frame_line`).
        try:
            self.world.day_script = ds
            self.world.stage_plan = self._stage_plan
        except Exception:                                       # noqa: BLE001
            pass
        try:
            DAYPLAN.save_cached(self.runfolder.root, ds)
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning("当日剧本落盘失败（不影响推演）：%r", e)
        # ★ 分镜脚本（P2，2026-10-15）：把分镜师产出的镜头清单落盘，给人/下游
        #   当拍摄说明书。与 分镜表.md（影视镜头卡，FILM_MODE 那条）是两件事：
        #   这里是分镜师按分拍拆的 ds.shots。
        # [EN] Storyboard script (P2): persist the storyboard artist's shot list (ds.shots).
        try:
            if ds.shots and self.runfolder is not None:
                from display import film as _F
                _sb = _F.storyboard_plan_md(ds.shots)
                _ddir = self.runfolder.daily_dir
                _ddir.mkdir(parents=True, exist_ok=True)
                (_ddir / f'第{ds.day:03d}天_分镜脚本.md').write_text(
                    _sb, encoding='utf-8')
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning('分镜脚本落盘失败（不影响推演）：%r', e)
        # ★ 分派写进各人的 `day_plan`：`_plan_day()` 看到有值就不会再去问一次模型
        #   （派活优先于"自己排"），决策提示词里的〔今日计划〕于是就是导演派的那几件事。
        # [EN] ★ Dispatch is written into each person's `day_plan`: when `_plan_day()` sees a value it won't
        # [EN] ask the model again
        # [EN] (assignment takes priority over "self-scheduling"), so 〔今日计划〕 in the decision prompt is exactly
        # [EN] what the director assigned.
        hit = 0
        for name, tasks in (ds.roles or {}).items():
            ps = (getattr(self.world, 'people', {}) or {}).get(name)
            if ps is None or not tasks:
                continue
            ps.day_plan = '；'.join(tasks)
            hit += 1
        # ★ 这里**只留一行"定稿"提示，不再推样章全文**（2026-10-07 真跑推演改）。
        # [EN] ★ Here **only a one-line "finalized" notice is kept, no more full sample-chapter text** (changed
        # [EN] 2026-10-07 after a real run of the deliberation).
        # 为什么：`ds.story` 就是上面「（剧组 · 小说作家）当天样章（原著）」那一次
        # 推的同一份文本，**一字不差**。两处都推全文，屏幕上同一段小说就出现两遍
        # —— 2026-10-07 拿 `samples/01` 真跑两天，对照
        # `developers/_run/01/screen.txt` 的 175 行与 196 行，两段逐字相同。
        # 这类"同一段内容讲两遍"正是用户反复报过的体感毛病（人物介绍讲两遍、
        # 台词讲一遍再说一遍），所以按同一条原则处理：**内容只出一次，另一处只报状态**。
        # 样章正文由剧组播报那次展示；这里让作者知道"当天这一章定了、多长、几拍"。
        # ★ **今日剧情简介**（2026-10-07 用户要的）：顺序是
        #   「前情提要 → **今日剧情简介** → 正式剧情」。
        #   前情提要在跨天那一步已经推过了（见 `run()` 的跨天分支），
        #   所以这里接着推简介；简介之后才是场景介绍与人物开口 —— 正是用户要的序。
        #   ⚠ 拿不到就**不推**（不拿前情凑数：简介写成前情的复述比没有更糟）。
        # [EN] Why: `ds.story` is exactly the text reasoned in the above "(crew · novelist) today's sample
        # [EN] chapter (original)"
        # [EN] **word for word**. If both places render the full text, the same passage of the novel appears
        # [EN] twice on screen
        # [EN] —— on 2026-10-07 ran `samples/01` for two real days, comparing
        # [EN] lines 175 and 196 of `developers/_run/01/screen.txt`, the two passages are identical verbatim.
        # [EN] This kind of "same content said twice" is exactly the experiential flaw the user repeatedly
        # [EN] reported (character intro said twice,
        # [EN] a line said once then said again), so handle it by the same principle: **content appears only
        # [EN] once, the other place only reports status**.
        # [EN] The sample chapter body is shown by the crew's broadcast; here let the author know "today's
        # [EN] chapter is finalized, how long, how many beats".
        # [EN] ★ **Today's plot synopsis** (what the user asked for on 2026-10-07): the order is
        # [EN] "recap → **today's plot synopsis** → actual story".
        # [EN] The recap has already been reasoned in the cross-day step (see the cross-day branch of `run()`),
        # [EN] so here we continue with the synopsis; only after the synopsis come the scene introduction and
        # [EN] characters speaking —— exactly the order the user wanted.
        # [EN] ⚠ If it can't be obtained, **don't reason it** (don't pad with the recap: a synopsis written as
        # [EN] a retelling of the recap is worse than none).
        if CFG.b('DAY_BRIEF'):
            _brief = str(getattr(ds, 'day_brief', '') or '').strip()
            if _brief:
                try:
                    from display import story_render as _STR
                    self._push_narrative(_STR.sentence(S.brief(_brief)), 1,
                                         kind=S.BRIEF)
                    _LOG.info('今日剧情简介上屏：%s', _brief[:60])
                except Exception as e:                           # noqa: BLE001
                    self._warn_once('day_brief', f'今日简介上屏失败：{e!r}')
        # ★★ **今日任务分配**（2026-10-07 第八轮，用户白名单里的「导演工作分配」）。
        # [EN] ★★ **Today's task assignment** (2026-10-07 eighth round, "director's work assignment" from the
        # [EN] user's whitelist).
        # 位置**卡在中间**：前情提要（跨天那一步已推）→ 今日剧情简介 →
        # **今日任务** → 场景介绍 → 人物开口。理由：先知道"前面发生了什么"、
        # 再知道"今天要演什么"，然后才关心"谁负责哪一件"，
        # 最后才是"这是什么地方"—— 读者是按这个顺序进入一天的。
        # [EN] The position is **stuck in the middle**: recap (already reasoned in the cross-day step) →
        # [EN] today's plot synopsis →
        # [EN] **today's tasks** → scene introduction → characters speaking. Rationale: first know "what
        # [EN] happened before",
        # [EN] then know "what to perform today", then care about "who's responsible for which item",
        # [EN] and only last "what place is this" —— this is the order in which a reader enters a day.
        # ⚠ 数据来自 `ds.roles`（剧作者在剧本里分的活），**不是** `director.dispatch`
        #   那条每 N 拍的临时派活 —— 两件事，别合并（见 `display/script.TASK` 的说明）。
        # ⚠ 空表**不推**：没派活就少一张卡，不要推一个空框出来
        #   （`task_block` 对空表返回空串，这里再判一次是因为推送前还要拼文本）。
        # [EN] ⚠ The data comes from `ds.roles` (the work assigned by the playwright in the script), **not**
        # [EN] `director.dispatch`
        # [EN] that temporary every-N-beats assignment —— two different things, don't merge them (see the
        # [EN] explanation in `display/script.TASK`).
        # [EN] ⚠ An empty table is **not rendered**: no assignment means one fewer card, don't render an empty
        # [EN] box
        # [EN] ( `task_block` returns an empty string for an empty table; we check again here because text must
        # [EN] be assembled before pushing).
        if CFG.b('DAY_TASKS'):
            try:
                from display import story_render as _STR
                _rows = [(str(n), list(v)) for n, v in (ds.roles or {}).items()]
                _blk = _STR.task_block(_rows)
                if _blk:
                    self._push_narrative(_blk, 1, kind=S.TASK)
                    _LOG.info('今日任务上屏：%d 人分到活', len(_rows))
            except Exception as e:                               # noqa: BLE001
                self._warn_once('day_tasks', f'今日任务上屏失败：{e!r}')
        # ⚠ 剧组那句"定稿"元信息**只在 `CREW_SCREEN=full` 时推**（2026-10-07）。
        #   用户：「中间剧情对话窗口尽可能少出现演职人员 除非必要」——
        #   它是**拍摄进度**，不是故事。默认档（`key`）里它不出现；
        #   要它回来就设 `CREW_SCREEN=full`。产出照旧落盘（`当日剧本.json`）。
        # ★★ 2026-10-10：**样章一写好就落一份原文**（用户：「保留小说原文」）。
        #   放在这里（定稿之后、分派之前）而不是收工：
        #   收工那次落的是"当天的呈现"（剧本 / 整理稿），而这一份是**当初写的那一篇**。
        #   ⚠ 必须**在 `CREW_SCREEN` 判断之外** —— 它是产物，不是上屏开关的附属品。
        # [EN] ⚠ The crew's "finalized" meta line is **only rendered when `CREW_SCREEN=full`** (2026-10-07).
        # [EN] User: "In the middle, the story/dialogue window should show cast and crew as little as possible
        # [EN] unless necessary" --
        # [EN] It is **shooting progress**, not the story. In the default profile (`key`) it does not appear;
        # [EN] to bring it back, set `CREW_SCREEN=full`. Output is written to disk as usual (`当日剧本.json`).
        # [EN] ★★ 2026-10-10: **as soon as the sample chapter is written, save a copy of the raw text** (user:
        # [EN] "keep the novel's original text").
        # [EN] Placed here (after finalization, before dispatch) rather than at wrap-up:
        # [EN] the wrap-up pass saves "the day's presentation" (script / cleaned transcript), whereas this one
        # [EN] is **the piece as originally written**.
        # [EN] ⚠ Must be **outside the `CREW_SCREEN` check** -- it is an artifact, not an appendage of the
        # [EN] screen on/off switch.
        try:
            _story_txt = str(getattr(ds, 'story', '') or '')
            if _story_txt.strip():
                self.runfolder.flush_day_story(int(ds.day or 0), _story_txt)
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning('原文落盘失败（不影响推演）：%r', e)

        if CFG.s('CREW_SCREEN').strip().lower() == 'full':
            try:
                n_beats = len(getattr(ds, 'beats', None) or [])
                n_chars = len(str(getattr(ds, 'story', '') or '').strip())
                self._push_narrative(
                    f"（当日剧本 · 第 {ds.day} 天 · 定稿）{n_chars} 字样章 · "
                    f"{n_beats} 拍 · "
                    + ('验算通过' if not getattr(ds, 'problems', None) else
                       f"验算留了 {len(ds.problems)} 条意见"),
                    0, kind=S.NOTE)
            except Exception:                                    # noqa: BLE001
                pass
        # ★ 场景介绍上屏（用户要的顺序：**前情提要 → 场景介绍 → 人物开口**）。
        #   前情提要在跨天那一步已经推过，这里接在它后面。
        #   它**不是** `RECAP`（那是"前情回顾"）—— 用 `AMBIENT`：
        #   它就是环境白描那一类"让读者先站进场面里"的话。
        # [EN] ★ Scene introduction on screen (order the user asked for: **previously on → scene introduction →
        # [EN] characters speak**).
        # [EN] Previously-on was already pushed at the cross-day step; this is attached after it.
        # [EN] It is **not** `RECAP` (that is "previously on") -- use `AMBIENT`:
        # [EN] it is that class of environmental descriptive prose that "lets the reader step into the scene
        # [EN] first".
        intro = str(getattr(ds, 'scene_intro', '') or '').strip()
        if intro:
            try:
                # ⚠ `to_ledger=False`：它是**场记单**（照着能画平面），不是小说正文。
                # [EN] ⚠ `to_ledger=False`: it is a **stage note** (detailed enough to draw a floor
                # [EN] plan), not novel prose.
                self._push_narrative(intro, 2, kind=S.AMBIENT, to_ledger=False)
            except Exception:                                   # noqa: BLE001
                pass
        # ★★ **导演写完当天剧本之后**，美术按今天的戏画当天那张小地图。
        #   用户 2026-10-07：「请把绘制地图改到**导演写完当前的小说之后**
        #   有剧组**美术**根据**当天剧情涉及到的地点**进行绘制」。
        #   ⚠ 顺序是要求的一部分：**先有剧本（分拍里有地点），才有图**。
        #     放在开卷时（旧做法）拿不到"今天演哪儿"这个信息，只能画全书总图
        #     —— 那正是用户报的"周围都是小说"。
        # [EN] ★★ **after the director finishes writing the day's script**, art draws the day's small map based
        # [EN] on today's scene.
        # [EN] User 2026-10-07: "please move map drawing to **after the director finishes writing the current
        # [EN] novel
        # [EN] and have the crew's **art** draw it based on **the locations involved in the day's plot**".
        # [EN] ⚠ The order is part of the requirement: **the script comes first (the shot breakdown has
        # [EN] locations), then the map**.
        # [EN] Doing it at book-opening time (the old approach) cannot obtain the "where are we performing
        # [EN] today" information, so it can only draw the whole-book overview map
        with self._stage('day_map'):
            await self._draw_day_map(ds)
        # ★★ **声音**（2026-10-07 审计补上）：这一场听得见什么。
        #   位置与当天地图**同级**（也在 `DAYPLAN.compose()` 之后）——
        #   声音设计要读当天的分拍（"今天要拍的几件事"），没有分拍它只能猜。
        #   以前它**一天都没出工过**（`Studio.sound_note` 零调用点），
        #   而 `CREW_SOUND` 默认是开的、名册上写着它的职责、`声音设计.md`
        #   也在落盘表里 —— 界面上的一个「假按钮」。
        # [EN] ★★ **Sound** (added in the 2026-10-07 audit): what can be heard in this scene.
        # [EN] Position is **sibling-level** to the map for that day (also after `DAYPLAN.compose()`) —
        # [EN] Sound design needs to read that day's beats ("the few things to shoot today"); without beats it
        # [EN] can only guess.
        # [EN] Previously it **never shipped a single day** (`Studio.sound_note` had zero call sites),
        # [EN] yet `CREW_SOUND` defaults to on, its duties are listed on the roster, `声音设计.md`
        # [EN] is also in the persistence table — a "fake button" in the UI.
        await self._sound(ds)

        _LOG.info("第 %d 天当日剧本：%d 拍 / %d 人派活 / %d 轮验算 · %s",
                  ds.day, len(ds.beats), hit, ds.rounds, ds.verdict[:60])
        # ★ **「一场一转变」验收**（2026-10-07，麦基/贝克那条）。
        #   剧作者的 `推进` 字段就是"这一拍变了什么"。有几拍没写＝那几拍
        #   没有价值转变 —— 按剧作法它们**可以删**。
        #   这里**只报不删**：删哪一拍是作者的判断（与场记"只报不改"同源）。
        # [EN] ★ **"One scene, one turn" acceptance** (2026-10-07, the McKee/Baker thread).
        # [EN] The playwright's `推进` field is exactly "what changed in this beat". Beats that don't write it =
        # [EN] those beats
        # [EN] have no value turn — per dramaturgy they **can be deleted**.
        # [EN] Here we **only report, never delete**: which beat to delete is the author's call (same lineage
        # [EN] as the script supervisor's "report only, don't change").
        try:
            flat = ds.flat_beats()
            if flat:
                _LOG.warning('第 %d 天：第 %s 拍没有写出「推进」（没有价值转变，'
                             '按剧作法这几拍可以删）', ds.day,
                             '、'.join(str(x) for x in flat))
            else:
                _LOG.info('第 %d 天：每一拍都有价值转变 ✓', ds.day)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('分拍转变自查失败（不影响推演）：%r', e)

    async def _sound(self, ds) -> None:
        """叫**声音**定今天听得见的东西（在剧本写完之后；见 `_compose_day`）。

        产出两处用得起：
          · 落盘 `声音设计.md`（`Studio._save_note`，走 `ARTIFACT` 表）；
          · 写进 `world.sound_design` → `SceneBuilder` 在**全场无事的那些片刻**
            用它写环境白描（`observe_quiet`），也就是名册里写的
            "喂给场景的环境句"。

        ⚠ 拿不到就**保持空**（不编一句假的氛围）—— 环境句退回原来的天气/时段池，
          那一池本来就是按场景写好的，不会因此空场。
        
                English:
        Call **sound** to decide what is audible today (after the script is written; see
        `_compose_day`).
                Produces two usable outputs:
                  · Persist `声音设计.md` (`Studio._save_note`, going through the `ARTIFACT` table);
                  · Write into `world.sound_design` → `SceneBuilder` uses it during **those moments when the whole scene is quiet**
                    to write environmental description (`observe_quiet`), i.e. what the roster calls
                    "the environmental sentence fed to the scene".
                ⚠ If unavailable, **keep it empty** (don't fabricate a fake ambiance) —— the environmental sentence falls back to the original weather/time-of-day pool,
                  and that pool was already written per scene, so the scene won't go empty because of this.
        """
        try:
            ctx = self._crew_ctx(story=str(getattr(ds, 'story', '') or ''),
                                 beats=list(getattr(ds, 'beats', None) or []))
            note = await self.studio.sound_note(
                ctx, beats=list(getattr(ds, 'beats', None) or []))
        except Exception as e:                                       # noqa: BLE001
            _LOG.warning('声音设计失败（环境句退回默认池）：%r', e)
            return
        if note is None or not note.ok:
            _LOG.info('第 %d 天：声音没给出设计（%s）—— 环境句用默认池',
                      int(getattr(ds, 'day', 0) or 0),
                      str(getattr(note, 'why', '') or '没有产出')[:80])
            return
        data = dict(note.data or {})
        self.world.sound_design = data
        line = self.studio.sound_brief(note)
        if line:
            _LOG.info('第 %d 天声音设计：%s', int(getattr(ds, 'day', 0) or 0),
                      line[:80])

    async def _draw_day_map(self, ds) -> None:
        """叫**美术**画当天这张小地图（在导演写完之后；见 `_compose_day`）。

        ★★ 取景范围 = **当天剧本里真的出现过、且设定里真实存在**的几处
        （`map_layout.places_in_day()`）。用户 2026-10-08 第二次点名这处：
        小地图上主角所在的那一处旁边画着一串**世界层级**的名字（各界、各域），
        用户说「**这些不是真实的地名**」，要求「**只根据当前发生的故事所在的
        地点画图**，而不是根据整本小说设定画图」。

        | | 旧做法（就是用户报的毛病） | 现在 |
        |---|---|---|
        | 范围 | 整本设定的地点表（含一批世界层级名） | 拿设定名去**当天分拍**里匹配 |
        | 「场」 | 直接当地名（长串被丢、楼内位置被当成地点） | 只当**文本**，找出真出现过的地名 |
        | 图 | 进界面时一张全书总图 | 今天戏在哪几处就画哪几处（**一处也画**） |
        | 美术的输入 | **整份地点表**（诱导它把"界"也画上） | **只给今天这几处** |

        ⚠ 拿不到（模型失败 / 名字全越界）就**保持 None**：
          界面退回 `here_only()`（只画当前这一处）——
          **宁可画一张小的，也不画一张错的**（旧做法是退回全书局部取景，
          而那条路按设定通路取景，照样会把"界"拉出来）。
        
                English:
        Call **art** to draw today's minimap (after the director finishes writing; see `_compose_day`).
                ★★ Framing scope = the few places that **actually appeared in today's script and truly exist in the setting**
                (`map_layout.places_in_day()`). User 2026-10-08 called this out for the second time:
                on the minimap, next to the place where the protagonist is, was drawn a string of **world-hierarchy** names (each realm, each domain),
                and the user said "**these are not real place names**", demanding "**draw the map only based on the
                locations where the currently unfolding story takes place**, not based on the whole novel's setting".
                | | Old approach (exactly the problem the user reported) | Now |
                |---|---|---|
                | Scope | The whole setting's place table (including a batch of world-hierarchy names) | Take setting names and **match against today's shot breakdown** |
                | "Place" | Treated directly as place names (long strings dropped, in-building positions treated as places) | Treat only as **text**, find the place names that actually appeared |
                | Map | One whole-book master map on entering the UI | Draw only the few places where today's scenes are (**even if just one**) |
                | Art's input | **The entire place table** (inducing it to also draw "realms") | **Only give today's few places** |
                ⚠ If unavailable (model failure / all names out of bounds), **keep it None**:
                  the UI falls back to `here_only()` (draw only the current place) ——
                  **better to draw a small one than a wrong one** (the old approach fell back to a whole-book local framing,
                  and that path frames by setting pathways, so it would still pull out "realms").
        """
        self.day_map = None
        try:
            from image_gen import map_layout as ML
        except Exception:                                       # noqa: BLE001
            return
        here = str(getattr(self.world, 'scene', '') or '').strip()
        # ★ 用**设定地点表**当词典，去**当天剧本**里找 —— 两个来源缺一不可：
        #   只有剧本 → 会拿"茶堂檐下"这种楼内位置当地名；
        #   只有设定 → 就是那张全书总图（用户报的毛病）。
        # [EN] ★ Use the **setting location table** as the dictionary, and search **that day's script** — both
        # [EN] sources are indispensable:
        # [EN] Script only → you'll treat in-building positions like "茶堂檐下" as place names;
        # [EN] Setting only → that's just the book-wide master map (the malady the user reported).
        known = self._known_places()
        names = ML.places_in_day(list(getattr(ds, 'beats', None) or []),
                                 known, extra=here)
        if not names:
            # 连"人在哪儿"都不知道 —— 没有范围可言，不硬画（界面自己会兜底）。
            # [EN] If you don't even know "where the people are" — there's no scope to speak of, don't force a
            # [EN] drawing (the UI will fall back on its own).
            _LOG.info('第 %d 天：当天剧本里没对上任何设定地点，不画当天地图',
                      int(getattr(ds, 'day', 0) or 0))
            return
        # ★ **一处也画**（2026-10-08）。以前这里 `len(names) <= 1` 直接 return，
        #   理由是"一张只有一个点的图没意义"—— 但那条判断与用户的期望正好相反：
        #   今天戏就在这一处，那张图**就该只有这一处**；退回"附近取景"反而会
        #   把设定里的邻居（"界"）拉上屏。宁可小，不要错。
        allowed = list(names)              # 只有今天这几处 —— 校验与提示词共用
        # [EN] ★ **Draw even a single spot** (2026-10-08). Previously this returned early on `len(names) <= 1`,
        # [EN] on the grounds of "a map with only one point is meaningless" — but that judgment is exactly the
        # [EN] opposite of the user's expectation:
        # [EN] today's drama is at this one spot, so that map **should have only this one spot**; falling back
        # [EN] to "shoot from nearby" instead
        # [EN] drags the setting's neighbors ("界") onto the screen. Better small than wrong.
        # [EN] Only today's few spots — shared by validation and the prompt

        # ★★ 三级底图（2026-10-08）：**从底图里取景**，不再让美术凭空摆位。
        #   用户：「在开卷的时候把一些整体地图 局部地图(房屋附近 房屋内部)
        #   提前画好，需要的时候基于这些地图让美术加细节」。
        #   `layers_for()` 定"今天最细的那一层说了算"：只在一处 → 室内或局部；
        #   跨了地方 → 整体。空 = 这本书没底图（没生成/生成失败/开关关着）
        #   → 退回从前的行为（照常能画，只是位置每天重编）。
        # [EN] ★★ Three-tier base maps (2026-10-08): **frame from the base map**, no longer letting the art put
        # [EN] things in place from nothing.
        # [EN] User: "At open-book time, get some overall maps and local maps (near houses, house interiors)
        # [EN] drawn ahead of time, and when needed let the art add detail based on these maps".
        # [EN] `layers_for()` decides "the finest layer today has the final say": only one spot → indoor or
        # [EN] local;
        # [EN] crossed places → overall. Empty = this book has no base map (not generated / generation failed /
        # [EN] switch off)
        # [EN] → fall back to the previous behavior (still draws as usual, just re-lays-out positions each
        # [EN] day).
        layers: list = []
        allow_extra: list[str] = []
        try:
            # ⚠ 用 `getattr` 而不是 `self.atlas`：用 `RunLoop.__new__` 手工装的
            #   夹具（判据里就是这么造的）不会有这个属性，直接访问会 AttributeError
            #   —— 那会被下面那层 `except` 吞掉，表现成"这本书没底图"，
            #   于是判据永远走不到底图那条路（**假绿**，最难查的一种）。
            # [EN] ⚠ Use `getattr` rather than `self.atlas`: fixtures built by hand with `RunLoop.__new__`
            # [EN] (which is how they're made in the criteria) won't have this attribute, and direct access would
            # [EN] raise AttributeError
            # [EN] — which would then be swallowed by the `except` below, manifesting as "this book has no base
            # [EN] map",
            # [EN] so the criteria would never reach the base-map path (**false green**, the hardest kind to track
            # [EN] down).
            _atlas = getattr(self, 'atlas', None)
            if _atlas is not None:
                layers = _atlas.layers_for(names, here)
                # ⚠ 选中室内层时上屏的是**房间名**（"堂屋"/"后院"），
                #   它们不在 `地点.yaml` 里 —— 不并进白名单的话，
                #   模型照底图抄回来的房间会被全部滤掉（室内图永远是空的）。
                # [EN] ⚠ When the indoor layer is selected, what goes on screen is the **room name** ("堂屋"/"后院"),
                # [EN] and they aren't in `地点.yaml` — if not merged into the whitelist,
                # [EN] every room the model copies back from the base map gets filtered out (the indoor map stays
                # [EN] forever empty).
                for _k, _n, _lay in layers:
                    allow_extra += [p.name for p in _lay.places]
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning('底图取景失败（退回每天现摆位）：%r', e)
            layers, allow_extra = [], []

        # `MINIMAP_AI=false`：不叫模型，直接按剧情顺序沿一条主路铺开
        # （零成本；小字会照实说"简化排布（没调用模型）"）。
        # [EN] `MINIMAP_AI=false`: don't call the model, just lay out along one main road in plot order
        # [EN] (zero cost; the small print will honestly say "simplified layout (model not called)").
        if not CFG.b('MINIMAP_AI'):
            lay0 = ML.simple_layout(allowed)
            self.day_map = lay0
            self.world.day_map = lay0          # 演员/导演的提示词要读它（见 Agent._stage_line）
            # [EN] The actor/director prompts read it (see `Agent._stage_line`)
            self._log_day_map(ds, lay0, why='MINIMAP_AI 关着')
            return

        # ★★★ **本地存档复用**（2026-10-12 用户点名的第二件事）：
        #   「所有的地图**保存在本地**，如果后续场景**能够复用的话则直接复用**」。
        #   为什么卡在**这里**（问模型之前，而不是画的时候）：
        #     下面那一步 `day_map_note()` 是**一次真金白银的模型调用**。
        #     故事回到同一处地方（茶肆今天又来了一趟、或者换了一轮还是这几处）
        #     时，那一趟问出来的是一模一样的东西 —— 复用省下的是**整次调用**，
        #     不是"省一次画"。所以这一步必须在**调用之前**。
        #   ⚠ 复用判据是**输入**（`basis_of`：细致程度 + 今天的地点集合 + 人在哪儿），
        #     不是"画出来的东西" —— 那时候还没有布局可指纹。
        #   ⚠ 存档目录在**项目**下（`<项目>/地图/`），所以**换轮次也还在**
        #     （这正是"后续场景能够复用"的意思）。
        #   ⚠ 存不下来 / 读不出来一律**当作没有**（`mapstore` 里失败只记日志）——
        #     这条旁路不该让推演失败，最坏的结果就是"这次又问了一遍"。
        # [EN] ★★★ **Local archive reuse** (the second thing the user named on 2026-10-12):
        # [EN]   "all maps are **saved locally**; if a later scene **can reuse** one, just reuse it".
        # [EN]   Why it is placed **here** (before asking the model, not at drawing time):
        # [EN]     the next step, `day_map_note()`, is **one real paid model call**. When the story
        # [EN]     returns to the same place (the teahouse today again, or another round with the same few
        # [EN]     places), that call asks exactly the same thing -- what is saved is **the whole call**,
        # [EN]     not "one drawing". So this must come **before** the call.
        # [EN]   ⚠ The reuse criterion is the **inputs** (`basis_of`: level of detail + today's set of
        # [EN]     places + where the person is), not "what was drawn" -- no layout exists yet to
        # [EN]     fingerprint.
        # [EN]   ⚠ The archive lives under the **project** (`<project>/地图/`), so it **survives across
        # [EN]     rounds** (which is exactly what "a later scene can reuse it" means).
        # [EN]   ⚠ Anything unsavable/unreadable counts as **absent** (`mapstore` only logs on failure) --
        # [EN]     this bypass must not fail the simulation; the worst outcome is "we asked again this
        # [EN]     time".
        _reuse = self._day_map_reuse(layers, allowed, here, ds)
        if _reuse is not None:
            return

        try:
            ctx = self._crew_ctx(story=str(getattr(ds, 'story', '') or ''),
                                 beats=list(getattr(ds, 'beats', None) or []))
            note = await self.studio.day_map_note(ctx, here=here, places=allowed,
                                                  layers=layers)
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning('当天地图生成失败（小地图退回"只画当前一处"）：%r', e)
            return
        if note is None or not note.ok:
            _LOG.info('第 %d 天：美术没给出当天地图（%s）—— 小地图只画当前一处',
                      int(getattr(ds, 'day', 0) or 0),
                      str(getattr(note, 'why', '') or '没有产出')[:80])
            return
        lay = ML.day_layout(note.data or {}, names, here=here,
                            allow_extra=allow_extra,
                            # ★ 档位以**取景层**为准（与存档键、锚定键同源）——
                            #   见 `day_layout` 里 `kind_hint` 那一段。
                            # [EN] The tier follows the **framing layer** (same source as the
                            # [EN] archive and anchor keys) -- see `kind_hint` in `day_layout`.
                            kind_hint=(str(layers[0][0]) if layers else ''))
        if lay is None or not lay.places:
            return
        self.day_map = lay
        # ★★★ 2026-10-26：**新画的这张也要过一遍锚定**（用户要的"整个推演里一致"）。
        #   不做的后果：每换一层/换一处主地点就得重画一张，而重画出来的位置
        #   与以前那张毫无关系 —— 用户看到的就是"每次都有区别"。
        #   贴上锚定后，同一处地方在**所有**图上都落在同一块位置。
        # [EN] ★★★ 2026-10-26: **a freshly drawn map goes through the anchors too** (the user wants
        # [EN] consistency across the whole simulation). Without it, every layer/place change draws
        # [EN] anew with positions unrelated to the previous map -- exactly the "different every time"
        # [EN] the user saw. With anchors, a place sits in the same spot on **every** map.
        _detail, _key = self._day_map_keys(layers, here)
        lay, _anchors, _why = self._day_map_anchor(
            lay, _detail, _key,
            wanted=[str(n) for n in (allowed or []) if str(n).strip()], here=here)
        # ★ 顺手挂到世界上：演员与导演的提示词靠它算"怎么走"（world.spatial.route）
        # [EN] Also hang it on the world: the actor and director prompts use it to compute "how to walk"
        # [EN] (world.spatial.route).
        self.world.day_map = lay
        self._log_day_map(ds, lay, why=('底图取景：' + '/'.join(
            f'{k}{"·" + n if n else ""}' for k, n, _ in layers)) if layers else '')
        try:
            ML.save_cached(self.runfolder.root, lay, name='当天地图.json')
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning('当天地图落盘失败（不影响推演）：%r', e)
        # ★★ **顺手存进项目级的地图存档**（2026-10-12）—— 下次同一局面直接复用
        #   （见上面 ③ 那一段）。放在最后：**只有真的画出来了才存**，
        #   半路失败的那些不该进存档（存进去的话以后每次都复用一张半成品）。
        # [EN] ★★ **Also store it in the project-level map archive** (2026-10-12) -- the same
        # [EN] situation next time reuses it directly (see section ③ above). Placed last: **store only
        # [EN] what was really drawn**; a half-failed one must not enter the archive (otherwise every
        # [EN] later run reuses a half-finished map).
        self._day_map_save(layers, allowed, here, lay)
        # ★★★ 2026-10-26（用户：「各种类型的故事…如果某些情况下缺少信息 最好是美术Agent
        #   可以让LLM去查资料 回来绘制 绘制之后相关数据资料还需要落地到skills作为SKILL
        #   提供后续参考」）：
        #   放在**落盘之后**，因为它要读的正是这份刚写下去的 `lay.program`。
        #
        #   ⚠ 为什么是 `await` 而不是"后台跑"：后台任务的异常没人接，而这个模块的
        #     失败必须只能**记日志**（出图不能因为它失败）。顺序也没有问题 ——
        #     这一步不产出图，只补资料，下一张图才开始受益。
        #   ⚠ 不阻塞的风险已经用 `ensure()` 的"查到过就不再查"兜住了：
        #     一本书里每类建筑最多一次，之后都是读盘（零网络、零成本）。
        # [EN] ★★★ 2026-10-26 (the user: "stories of all kinds ... when information is missing,
        # [EN] the art agent should be able to have the LLM research it, then draw from that, and the
        # [EN] data should land in skills as a SKILL for later reference"): placed **after saving**
        # [EN] because it reads exactly the `lay.program` just written. ⚠ `await`, not fire-and-forget,
        # [EN] since a detached task's exception has no handler and this module may only **log** its
        # [EN] failures (the drawing must not fail with it). Order is fine: this step produces no map,
        # [EN] it only gathers material, and the *next* map benefits. ⚠ The blocking risk is covered by
        # [EN] `ensure()`'s "already researched => reuse": once per building type per book, then pure
        # [EN] disk reads (no network, no cost).
        await self._maybe_art_research(lay)

    async def _maybe_art_research(self, lay) -> None:
        """把「这类建筑我们还缺什么」交给美术去查，结果落进 `skills/地图-<类型>/`。

        ★ 三条守卫，每条都对应一个真实风险：
          ① `MAP_ART_RESEARCH` 关 ⇒ 一次网络都不发（默认开的理由见配置说明）；
          ② 没有任务书 ⇒ 跳过（`program` 是判建筑类型的唯一依据）；
          ③ 已经有资料 ⇒ 跳过（`ensure` 内部读盘，这里提前返回省一次 IO）。
        ★ **任何异常都只记日志**：这是增强通道，它挂了不该让这一轮推演失败。
        [EN] Hand "what are we still missing for this kind of building" to art research, saving into
        [EN] `skills/map-<style>/`. ★ Three guards, each against a real risk: (1) switch off => no
        [EN] network at all; (2) no program => skip (the program is the only basis for the style);
        [EN] (3) already researched => skip. ★ **Every exception is logged only**: this is an
        [EN] enhancement path and must not fail the round.
        """
        try:
            if not CFG.b('MAP_ART_RESEARCH'):
                return
            prog_d = dict(getattr(lay, 'program', None) or {})
            if not prog_d:
                return
            from image_gen import worldstyle as WS
            from image_gen import artresearch as AR
            st = WS.BY_KEY.get(str(prog_d.get('风格') or ''))
            if st is None:
                return
            root = CFG.resolved('SKILLS_DIR')
            if AR.load(st, root) is not None:
                return
            # 判成兜底的要**说清是兜底**：那条"这属于哪种建筑传统"是根上的问题，
            # `needs_research` 会把它排在第一个。
            _why = str(prog_d.get('风格依据') or '')
            m = WS.Match(style=st, score=(0.0 if '判不出' in _why else 1.0),
                         是兜底=('判不出' in _why))
            from llm.replies import ask as _ask
            f = await AR.ensure(m, root=root, ask=_ask,
                                setting=self._day_map_setting_text(),
                                genre=self._day_map_genre())
            if f is not None and f.usable_answers():
                _LOG.info('美术查到了 %d 条「%s」的建筑常识（已落盘 skills，以后不再查）',
                          len(f.usable_answers()), st.名)
            # 顺手把这一轮**实际画成什么样**也沉下来（用户要的"落地到 skills"）
            try:
                prog = __import__('image_gen.roomplan', fromlist=['Program']).Program.from_dict(prog_d)
                if prog is not None:
                    AR.save_precedent(prog, root)
            except Exception:                                 # noqa: BLE001
                pass
        except Exception as e:                                # noqa: BLE001
            _LOG.warning('建筑资料查询失败（不影响出图）：%r', e)

    def _day_map_setting_text(self) -> str:
        """给查资料用的"这本书的建筑线索"（地点名 + 说明，**只取有信息量的**）。

        ★ 为什么不是把整个设定集喂进去：查资料问的是"这种建筑怎么盖"，
          地点列表已经足够定位；整本设定集是几万字，成本高且噪声大。
        [EN] The building clues for research: place names plus notes, informative ones only. ★ Why
        [EN] not the whole setting: the question is "how is this kind of building built", and the place
        [EN] list already locates it; a whole setting is tens of thousands of characters of costly,
        [EN] noisy input.
        """
        try:
            places = list(getattr(self.day_map, 'places', None) or [])
            rows = [f"{p.name}：{str(p.note or '')[:40]}" for p in places[:12] if p.name]
            if places:
                return '地点：' + '；'.join(rows)
        except Exception:                                     # noqa: BLE001
            pass
        return ''

    def _day_map_genre(self) -> str:
        """当前这本书的题材（`genre_card['主题材']`），**只作弱提示**，取不到就是空串。
            English: The book's genre (weak hint only); empty when unavailable.
        """
        try:
            g = getattr(self.world, 'genre_card', None) or {}
            return str(g.get('主题材') or '')
        except Exception:                                     # noqa: BLE001
            return ''

    def _day_map_reuse(self, layers: list, allowed: list[str], here: str, ds):
        """**问模型之前**先看一眼本地存档（命中就把它当今天的图，返回 True）。

        ⚠ 返回 `None` 有两种意思，**调用方不必分**：没存过 / 存过但对不上
          （都该去问模型）。真正的"出错"在这里被吞掉 —— 存档是旁路。
        [EN] Glance at the local archive **before asking the model** (on a hit, use it as today's map
        [EN] and return True).
        [EN] ⚠ `None` means either "never archived" or "archived but mismatched" and **the caller need
        [EN] not distinguish them** (both should ask the model). A real error is swallowed here -- the
        [EN] archive is a bypass.
        """
        try:
            from image_gen import mapstore as MSTORE
            detail, key = self._day_map_keys(layers, here)
            basis = MSTORE.basis_of(detail, allowed, here)
            lay = MSTORE.reuse(getattr(self.runfolder, 'project_dir', None),
                               detail, key, basis)
            if lay is None:
                return None
            # ★★★ 2026-10-26（用户：「每次生成的感觉都有一些区别 有办法在整个小说推演
            #   过程中维持相同场景地图的一致性吗」）：复用命中只是**底子**，
            #   还要补两件事 —— 否则"复用"会变成"图缺东西"或"位置漂"：
            #     ① `fill`：今天该有、这张图上还没有的地点**补进来**（用空位）；
            #     ② `apply`：把**项目级锚定**贴上去 ⇒ 同一处地点永远是同一块位置，
            #        今天新出现的那些顺手记进锚定（它们以后也不再动）。
            #   ⚠ 顺序不能反：先补、后贴锚定。反了的话"补进来的点"会绕过锚定检查，
            #     可能正好压在已锚定的地点上（图上两个方块叠住，且不报错）。
            # [EN] ★★★ 2026-10-26 (the user: "it feels a bit different every time; can we keep
            # [EN] scene maps consistent across the whole simulation?"): a reuse hit is only the
            # [EN] **base**; two more things must happen or "reuse" turns into "the map is missing
            # [EN] things" or "positions drift": ① `fill` adds places today should have but this map
            # [EN] lacks (using spare slots); ② `apply` stamps the **project-level anchors** so a
            # [EN] place always occupies the same spot, and records today's newcomers (which then
            # [EN] never move either). ⚠ Order matters: fill first, anchor second -- reversed, a
            # [EN] added point bypasses the anchor check and can land right on top of an anchored
            # [EN] place (two blocks overlapping, silently).
            _want = [str(n) for n in (allowed or []) if str(n).strip()]
            lay, _anchors, _why = self._day_map_anchor(lay, detail, key,
                                                      wanted=_want, here=here)
            self.day_map = lay
            self.world.day_map = lay
            _LOG.info('第 %d 天当天地图：复用本地存档「%s」（没花模型调用）· %s',
                      int(getattr(ds, 'day', 0) or 0), f'{detail}_{key}',
                      '；'.join(_why) or '无需调整')
            self._log_day_map(ds, lay, why='本地存档复用（没调模型）'
                             + ((' · ' + '；'.join(_why)) if _why else ''))
            # 补进来的地点要**存回存档**，否则下次复用又把它们忘了（每天补一遍）。
            # [EN] Persist the added places, or the next reuse forgets them and re-adds daily.
            _n_before = len(MSTORE.saved(getattr(self.runfolder, 'project_dir', None)))
            MSTORE.save(getattr(self.runfolder, 'project_dir', None), detail, key, lay,
                        basis=basis)
            _ = _n_before
            return True
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning('地图存档复用失败（照常去问模型）：%r', e)
            return None

    def _day_map_anchor(self, lay, detail: str, key: str, *, wanted=None,
                        here: str = ''):
        """**补齐 + 贴锚定**：把这张图变成"同一处地方永远同一块位置、东西一个不少"的样子。

        `MAP_ANCHOR` 关掉就原样返回 `(lay, {}, [])`（逐字回到从前的行为）。

        两件事，**顺序要紧**：

        ① `fill` 补齐 —— 补两类：
           · 今天该有、图上没有的（`wanted`）；
           · **锚定里已经有、而这次模型漏了**的（模型明天忘了画灶房，图上就凭空少一样）。
           先补、后贴，是因为"补进来的点"必须先有坐标才谈得上贴。
        ② `apply` 贴锚定 —— 每个已锚定的地点一律用锚定值（坐标/形状/尺寸/署名/所属房间），
           新见到的记下来（它们从此也不再动）。

        返回 `(布局, 锚定表, 说明行)`；说明行进日志，回答"今天这张为什么和昨天不一样"。

        ★ 为什么锚定按 `(细致程度, 地点)` 分槽：室内平面图与整体方位图**本来就该不同**，
          混在一份里，从楼里走到街上（切层）时所有坐标会互相污染。
        ★ 失败只记日志：它是旁路（见 `image_gen/mapanchor` 的铁律）。
        [EN] **Fill the gaps, then stamp the anchors**: make this map the one where a place always
        [EN] occupies the same spot and nothing is missing. With `MAP_ANCHOR` off it returns
        [EN] `(lay, {}, [])` unchanged (the old behaviour, character for character).
        [EN] Two steps, **order matters**: ① `fill` adds both what today needs and what the **anchors
        [EN] already have but the model omitted this time** (it forgot the kitchen, so the map would
        [EN] drop it out of thin air); ② `apply` stamps the anchors, so every anchored place takes the
        [EN] anchored values and newcomers are recorded (and then never move either).
        [EN] ★ Anchors are keyed by `(detail, place)` because an interior plan and an overall bearing
        [EN] map legitimately differ -- mixing them would poison every coordinate when the layer
        [EN] switches as the story walks from indoors to the street.
        [EN] ★ Log only on failure: it is a bypass (see the iron rule in `image_gen/mapanchor`).
        """
        try:
            if not CFG.b('MAP_ANCHOR'):
                return lay, {}, []
            from image_gen import mapanchor as MAPA
            proj = getattr(self.runfolder, 'project_dir', None)
            layers = MAPA.load(proj)
            slot = MAPA.slot_of(layers, detail, key)
            known = [k for k in slot if not str(k).startswith('_')]
            lay, added = MAPA.fill(lay, list(wanted or []), here=here, also=known)
            lay, layers, why = MAPA.apply(lay, detail, key, layers)
            if added:
                why.append('补齐 ' + '/'.join(added[:3]) + ('…' if len(added) > 3 else ''))
            MAPA.save(proj, layers)
            _LOG.info('地图锚定「%s」：%s', f'{detail}·{key}', '；'.join(why) or '无变化')
            return lay, layers, why
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning('地图锚定失败（图照原样用，位置可能变化）：%r', e)
            return lay, {}, []

    def _day_map_save(self, layers: list, allowed: list[str], here: str, lay) -> None:
        """把刚画好的这张存进项目级存档（失败只记日志）。
        [EN] Store the map just drawn into the project-level archive (log only on failure)."""
        try:
            from image_gen import mapstore as MSTORE
            detail, key = self._day_map_keys(layers, here)
            MSTORE.save(getattr(self.runfolder, 'project_dir', None), detail, key, lay,
                        basis=MSTORE.basis_of(detail, allowed, here))
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning('地图存档失败（不影响推演）：%r', e)

    @staticmethod
    def _day_map_keys(layers: list, here: str) -> tuple[str, str]:
        """存档的键：`(细致程度, 地点名)`。

        ★ 细致程度**取自底图取景那一层**（`layers[0][0]` 就是 `整体/局部/室内`），
          与渲染那边 `minimap.detail_of()` 同一套说法 —— 两处都用"哪一层"当档位，
          不另立一套名词（两套迟早会漂）。
        ★ 没有底图（`layers` 空）= 每天现摆位那种 → 按"局部"存，地点用 `here`。
        [EN] The archive key: `(level of detail, place name)`.
        [EN] ★ The level of detail **comes from the framed base-map layer** (`layers[0][0]` is
        [EN] `整体/局部/室内`), the same vocabulary as `minimap.detail_of()` on the rendering side --
        [EN] both use "which layer" as the tier instead of inventing a second set of terms (two sets
        [EN] will drift eventually).
        [EN] ★ No base map (empty `layers`) = the "re-lay-out daily" case -> archive as "局部" with
        [EN] `here` as the place.
        """
        kind = str(layers[0][0]) if layers else '局部'
        key = (str(layers[0][1]) if layers else '') or str(here or '') or '未命名'
        return kind, key

    def _log_day_map(self, ds, lay, *, why: str = '') -> None:
        """当天地图定下来之后：**上屏一行 + 记日志 + 叫界面重画**（两条路共用一份）。
                English:
        Once today's map is settled: **display one line on screen + log it + tell the UI to redraw**
        (both paths share one copy).
        """
        try:
            trip = ' → '.join(p.name for p in lay.places[:4])
            self._push_narrative(f'（当天地图 · 今日 {len(lay.places)} 处）{trip}',
                                 2, kind=S.NOTE)
        except Exception:                                       # noqa: BLE001
            pass
        # ★★ **图画好了就立刻叫界面重画一次**（2026-10-08 用户报的一处）。
        # [EN] ★★ **Once the map is drawn, immediately make the UI redraw once** (a spot the user reported on
        # [EN] 2026-10-08).
        #   界面重画小地图原本**只挂在"换场景"上**（`_push_scene` → `_on_scene`），
        #   而一天里完全可能**自始至终是同一处** —— 那样 `_maybe_break_scene()`
        #   永远不返回 True，界面就一次都收不到重画通知，左栏一直停在
        #   早先那句「今天这张图还没出来（导演写完当天剧本、美术出工才有）」。
        #   用户看到的就是「**小地图一直没画 好像美术一直没参与进来 故事都
        #   开始了 美术也没被调用绘制小地图**」—— 其实美术出工了、图也在盘上，
        #   只是**没人叫界面重画**。
        # [EN] The UI's minimap redraw was originally **only hooked to "scene change"** (`_push_scene` →
        # [EN] `_on_scene`),
        # [EN] yet a whole day may well be **the same spot from start to finish** — in that case
        # [EN] `_maybe_break_scene()`
        # [EN] never returns True, so the UI never receives a redraw notification even once, and the left
        # [EN] column stays stuck on
        # [EN] the old line "today's map isn't out yet (only after the director writes the day's script and the
        # [EN] art ships)".
        # [EN] What the user saw was "**the minimap was never drawn; it's like the art never got involved; the
        # [EN] story has
        # [EN] already started and the art still wasn't called to draw the minimap**" — when in fact the art
        # [EN] shipped and the map was on disk,
        # [EN] it's just that **no one told the UI to redraw**.
        #   ⚠ `record=False`：这一条是给界面的**重画通知**，不是剧情里的
        #     "换场景"（那时并没有换地方，只是图变了），不该往审读台账里多塞一行。
        # [EN] ⚠ `record=False`: this entry is a **redraw notification** for the UI, not a plot-level
        # [EN] "scene change" (no place changed at that point, only the map), so it shouldn't stuff an extra
        # [EN] row into the review ledger.
        try:
            here = str(getattr(self, '_last_place', '')
                       or getattr(self.world, 'scene', '') or '')
            self._push_scene(place=here, segment=self._clock_segment(),
                             record=False)
        except Exception as e:                                  # noqa: BLE001
            # ⚠ 这里**不能再调 `self._warn_once`**：它本身也是可缺的
            #   （`RunLoop.__new__` 造的夹具就没这一项），那样 except 里再抛一次
            #   就把"图画好了"这件事整个带崩 —— `verify_minimap` 的 G 组
            #   第一版就是这么红的。播报失败只用模块日志说一声。
            # [EN] ⚠ Here you **must not call `self._warn_once` again**: it itself is also optional
            # [EN] (fixtures made by `RunLoop.__new__` don't have this entry), so throwing again inside the except
            # [EN] would crash the whole "map is drawn" thing — `verify_minimap`'s group G
            # [EN] went red exactly this way in its first version. Announcement failures only get a word in the
            # [EN] module log.
            _LOG.warning('当天地图重画通知失败（不影响推演）：%r', e)
        _LOG.info('第 %d 天当天地图：%d 处 —— %s%s',
                  int(getattr(ds, 'day', 0) or 0), len(lay.places),
                  '、'.join(p.name for p in lay.places[:6]),
                  f'（{why}）' if why else '')

    def _known_places(self) -> list[str]:
        """设定里**真实存在**的地点名（给美术当白名单）。

        从 `world.worldview_text` 的 `【地点】` 那一段取 —— 那是装配时按
        `地点.yaml` 拼进去的（`sim/setup._worldview_text`），和界面上
        `MAPLAYOUT.places_from_settings()` 用的是同一批名字。
        取不到就返回空（美术那边会退成"用剧情里出现的名字"）。
        
                English:
        Place names that **truly exist** in the setting (as a whitelist for art).
                Taken from the `【地点】` section of `world.worldview_text` —— that was assembled at setup time per
                `地点.yaml` (`sim/setup._worldview_text`), and it uses the same batch of names as the UI's
                `MAPLAYOUT.places_from_settings()`.
                If unavailable, return empty (art will fall back to "use the names that appeared in the plot").
        """
        try:
            from director.day_plan import _section            # noqa: SLF001
            body = _section(str(getattr(self.world, 'worldview_text', '') or ''),
                            '地点')
            names = [x.strip() for x in re.split(r'[、,，;；]', body) if x.strip()]
        except Exception:                                       # noqa: BLE001
            names = []
        # ★★★ 2026-10-22：**加上这一轮现场登记的新地点**。
        #   用户：「小说提到了府城和大柳树 你确认下后续会出现当前城市到府城的地图
        #   以及大柳树附近的地图吗？」—— 查下来**不会**：`世界观` 里 `【地点】` 只有
        #   `望江楼` 一处，而剧作家写的 `河岸柳树下` / `府城` 既不在设定表里、
        #   也没有任何东西会把它加进去 ⇒ 换场被静默拒绝、当天地图也取不到那一处，
        #   于是"故事去了柳树底下，地图还是望江楼"。
        #   现在换场时会把**不像场面话**的新地名登记进 `world.place_names`
        #   （见 `_register_place`），这里把它并进白名单 —— 地图与换场用**同一份**名单。
        # [EN] ★★★ 2026-10-22: **include the new places registered on the spot this round**.
        # [EN] User: "the novel mentions the prefecture city and the big willow; will maps for
        # [EN] city->prefecture and around the willow appear later?" -- investigated: **no**. The
        # [EN] `【地点】` section in the worldview holds only `望江楼`, and what the playwright writes
        # [EN] (`河岸柳树下` / `府城`) is neither in the table nor added by anything => the scene switch
        # [EN] is silently refused and the day map cannot frame it either, so "the story went to the
        # [EN] willow but the map still says Mowen Tower".
        # [EN] Now a scene switch registers a plausible new name into `world.place_names` (see
        # [EN] `_register_place`) and this method unions it into the whitelist -- the map and the scene
        # [EN] switch share **one** list.
        for extra_name in (getattr(self.world, 'place_names', None) or []):
            n = str(extra_name or '').strip()
            if n and n not in names:
                names.append(n)
        return names[:40]

    async def _plan_day(self) -> None:
        """新的一天：**并发**给前台人物算今日计划（`Agent.make_plan`）。

        `make_plan` 写好很久了，但**从来没有人调用** —— 人物的 `current_goal`
        永远停在设定里那句静态的话上，于是行动全靠导演随机戳
        （"人物在世界里空转"的另一半原因）。现在每天开一次计划，
        决策 prompt 里带上，人物才有"我今天打算干什么"。

        并发是有意的：串行的话 12 个人就是 12 次往返，每次十几秒。
        
                English:
        New day: **concurrently** compute today's plan for the foreground characters
        (`Agent.make_plan`).
                `make_plan` was written long ago, but **it was never called** —— a character's `current_goal`
                stays forever on the static sentence in the setting, so actions rely entirely on the director randomly poking
                (the other half of the reason "characters idle in the world"). Now a plan opens once each day,
                included in the decision prompt, so characters have "what I plan to do today".
                Concurrency is intentional: if serial, 12 people would be 12 round trips, each taking a dozen-plus seconds.
        """
        if not CFG.b("PLANNING_ENABLED"):
            return
        # ★ **导演已经派过活的人不再问一次模型**（2026-10-07）：派活是框架的一部分，
        #   再让模型自己排一遍不但多花一次调用，还可能把导演派的那几件事覆盖掉。
        # [EN] ★ **People the director already assigned work to aren't asked of the model again** (2026-10-07):
        # [EN] assigning work is part of the framework,
        # [EN] making the model re-schedule it not only costs one more call but may also overwrite the few
        # [EN] things the director assigned.
        people = [a for a in self.agents
                  if a.ps.is_active() and not str(getattr(a.ps, 'day_plan', '') or '')]
        if not people:
            return
        self._status('planning', n=len(people))
        try:
            await asyncio.gather(*(a.make_plan() for a in people),
                                 return_exceptions=True)
        except Exception as e:                               # noqa: BLE001
            _LOG.warning("今日计划生成失败（不影响推演）：%r", e)
            return
        done = sum(1 for a in people if getattr(a.ps, "day_plan", None))
        _LOG.info("第 %d 天：%d/%d 位人物排好了今日计划", self.world.game_day, done,
                  len(people))

    async def _maybe_branch(self, tick_num: int) -> bool:
        """岔路口：向导演要几个走向候选，**等用户挑**（或按策略自动挑）。返回是否挑过。

        以前这条链路是**全死的**：`director.propose_branches()` 写好了但没有任何
        调用点，`RunLoop` 的 `on_branch` / `choose_branch` / `_branch_choice`
        三个成员也从没被用过 —— `BRANCH_WAIT_SECONDS`（等多久）、
        `BRANCH_AUTO_POLICY`（等不到怎么办）自然全是零读取。

        三个触发点（都不频繁，一次运行几次量级）：

        * **节点刚走完**（`self._branch_pending` 由 `_check_progress` 置位）——
          这是最自然的分岔：一站完了，往哪走？
        * **高潮日** —— 该有大选择的日子。
        * **停滞自救** —— 故事卡住了，换个方向比硬推更聪明。

        ⚠ **没有界面监听时不要空等**：`_on_branch` 是 None（无 GUI / 脚本跑）
        就直接走自动策略 —— 干等 `BRANCH_WAIT_SECONDS` 秒是纯粹的浪费。
        
                English:
        Fork: ask the director for several direction candidates, **wait for the user to pick** (or
        auto-pick per policy). Returns whether a pick was made.
                Previously this chain was **completely dead**: `director.propose_branches()` was written but had no
                call site, and `RunLoop`'s `on_branch` / `choose_branch` / `_branch_choice`
                three members were never used either -- `BRANCH_WAIT_SECONDS` (how long to wait),
                `BRANCH_AUTO_POLICY` (what to do if it can't wait) were naturally all zero reads.
                Three trigger points (all infrequent, on the order of a few times per run):
                * **Node just finished** (`self._branch_pending` set by `_check_progress`) --
                  this is the most natural fork: one stop is done, where to go?
                * **Climax day** -- the day that should have a big choice.
                * **Stagnation self-rescue** -- the story is stuck; changing direction is smarter than forcing it.
                ⚠ **Don't wait idly when there's no UI listener**: if `_on_branch` is None (no GUI / script run)
                go straight to the auto policy -- idly waiting `BRANCH_WAIT_SECONDS` seconds is pure waste.
        """
        due = bool(self._branch_pending) or self.director.is_climax_day()
        if not due:
            return False
        self._branch_pending = False
        # 同一拍只挑一次；也避免连着几拍反复弹
        # [EN] Pick only once per beat; this also avoids popping up repeatedly across consecutive beats.
        if self._last_branch_day == self.world.game_day and not self._branch_pending:
            due = False
        if not due:
            return False
        self._last_branch_day = self.world.game_day
        self._status('branching')
        # ★ 2026-10-27：这一站若有作者写的**结局选项**，这次不是"往哪走"、
        #   而是**挑结局** —— 候选必须原样就是那几个（别让模型自己另编）。
        #   ⚠ 读完就清（一次性提示的老规矩）。
        # [EN] ★ 2026-10-27: if this station carries the author's **ending options**, this fork is not
        # [EN] "which way next" but **picking the ending** -- the candidates must be exactly those
        # [EN] (don't let the model invent others). ⚠ Cleared once read (one-shot rule).
        _ending_opts = list(getattr(self, '_pending_options', None) or [])
        self._pending_options = None
        try:
            branches = await self.director.propose_branches(
                options=_ending_opts or None)
        except Exception as e:                                  # noqa: BLE001
            self._warn_once('branch', f"分支提案失败（不影响推演）：{e!r}")
            return False
        if not branches:
            return False

        chosen: dict | None = None
        custom = ""
        # ⚠ 一律用 `getattr` 取这两个回调：判据与探针里有不少用
        #   `RunLoop.__new__` 造对象、**绕过 `__init__`** 的夹具
        #   （`verify_branch` / `verify_branch_dialog` 都是），
        #   直接取属性会 `AttributeError` —— 那看起来像产品代码坏了。
        # [EN] (`verify_branch` / `verify_branch_dialog` are both),
        # [EN] accessing the attribute directly raises `AttributeError` — which looks like the product code is
        # [EN] broken.
        _on_ask = getattr(self, '_on_ask', None)
        _on_branch = getattr(self, '_on_branch', None)
        if _on_branch or _on_ask:
            # ⚠ **先清空上一次的选择，再交界面**。反了就会把用户这次的选择擦掉：
            #   界面如果是**同步**回调（或者点得够快），`choose_branch` 在
            #   `_on_branch` 返回前就已经写好了，之后再清空等于白选
            #   （`verify_branch` 的 C1 抓到过这一条）。
            # [EN] ⚠ **Clear the previous selection first, then hand over to the UI**. Reverse the order and the
            # [EN] user's current selection gets wiped:
            # [EN] if the UI is a **synchronous** callback (or the click is fast enough), `choose_branch` has
            # [EN] already been written before `_on_branch` returns, so clearing afterwards means the choice was in
            # [EN] vain
            # [EN] (`verify_branch`'s C1 caught this one).
            self._branch_choice = None
            self._branch_custom = ""
            # ★★ 2026-10-11：岔路口改走**统一的提问对话框**（`_ask`）。
            #   以前这里是一段**自己写的等待循环** —— 于是"弹出问答"这件事
            #   在这一个项目里有**两套实现**（岔路口一套、新加的介入问答一套），
            #   而用户这轮点名要的第二条（取消 → 暂停 → 点继续重新弹）只要
            #   落在其中一套上，另一套就没有。现在只有一套。
            # [EN] ★★ 2026-10-11: the fork now goes through the **unified ask dialog** (`_ask`).
            # [EN] this used to be a **hand-written wait loop** — so the act of "popping a question" had
            # [EN] **two implementations** in this one project (one for the fork, one for the newly added
            # [EN] intervention ask),
            # [EN] and the second item the user called out this round (cancel → pause → click continue to re-pop)
            # [EN] only
            # [EN] landed in one of them; the other didn't have it. Now there is only one.
            # ⚠ **老通道仍然认**：`on_branch` 那批判据/探针（`verify_branch`、
            # [EN] ⚠ **The old channel is still honored**: the batch of assertions/probes on `on_branch`
            # [EN] (`verify_branch`,
            #   `verify_branch_dialog`、`developers/probe_branch_dialog.py`）
            #   直接调 `loop.choose_branch()` / `choose_branch_custom()`，
            #   它们不看 `_ask`。所以 `_ask` 那边**同时轮询**这两个老字段
            #   （见那边的 `kind == 'branch'` 分支）—— 两条入口、一个落点。
            # [EN] call `loop.choose_branch()` / `choose_branch_custom()` directly,
            # [EN] they don't look at `_ask`. So the `_ask` side **also polls** these two old fields
            # [EN] (see the `kind == 'branch'` branch over there) — two entry points, one landing spot.
            ans = await self._ask(
                kind='branch',
                title=('结局 · 挑一个' if _ending_opts else '岔路口 · 往哪走'),
                why=('**这一站的事已经了了，故事停在一个选择上** —— '
                     '这是作者写好的几个结局，挑一个（或自己写一个），'
                     '后面就照它收束。'
                     if _ending_opts else
                     '故事走到一个分岔口：挑一个走向，导演会顺着它安排后面的戏；'
                     '都不合意就自己写一句。'),
                # ⚠ 原样带上候选（**整块 copy，不要只挑三个字段**）：
                #   `verify_branch` 的 C1 量的是 `seen[0] == rows`（交给界面的
                #   就是导演给的那一份），只挑 id/标题/后果 会少掉 `权重`，
                #   那条断言当场变红 —— 而且它红得有道理（少字段 = 信息丢了）。
                # [EN] ⚠ Carry the candidates through verbatim (**copy the whole block, don't just pick three
                # [EN] fields**):
                # [EN] `verify_branch`'s C1 measures `seen[0] == rows` (exactly the copy handed to the UI
                # [EN] by the director); picking only id/title/consequence drops `weight`,
                # [EN] and that assertion goes red on the spot — and rightly so (missing fields = information lost).
                options=[dict(b) for b in branches],
                allow_custom=True,
                wait=max(0, CFG.i("BRANCH_WAIT_SECONDS")),
                # 没有 `on_ask` 时退回老通道（`on_branch` 只吃 branches 列表）
                # [EN] With no `on_ask`, fall back to the old channel (`on_branch` only takes a branches list)
                notify=(None if _on_ask is not None or _on_branch is None
                        else (lambda q: _on_branch(q.get('options') or []))),
            )
            custom = str((ans or {}).get('custom') or '').strip()
            pick = str((ans or {}).get('id') or '').strip()
            if pick:
                chosen = next((b for b in branches
                               if str(b.get("id")) == pick), None)
        # ★ 自己写的走向**优先于一切**：它是作者亲口说的，比策略和候选都硬。
        #   包成一个和候选同形的 dict，好让下面"写事件流 + branch_hint"那段
        #   一行都不用改（**一处实现**：两条路必须落到同一个地方）。
        # [EN] ★ A hand-written direction **takes priority over everything**: it is what the author said in
        # [EN] person, harder than both policy and candidates.
        # [EN] Wrap it into a dict shaped the same as the candidates, so that the "write event stream +
        # [EN] branch_hint" section below
        # [EN] needs no changes at all (**one implementation**: both paths must land in the same place).
        if custom:
            chosen = {"id": "自定", "标题": custom, "后果": "", "权重": 1.0}
        if chosen is None:
            chosen = self.director.pick_branch(branches)
        if chosen is None:
            # `BRANCH_AUTO_POLICY=pause`：不替用户做决定，**挂住等**
            # [EN] `BRANCH_AUTO_POLICY=pause`: don't decide for the user, **hang and wait**
            _LOG.info("分支策略=pause，等用户在界面上选（推演暂停）")
            self.pause("岔路口：BRANCH_AUTO_POLICY=pause，等作者挑走向")
            self._push_narrative(
                "（岔路口）等你挑一个走向 —— 已暂停。"
                + "；".join(f"{b.get('id')}：{b.get('标题')}" for b in branches)
                + "。也可以自己写一个走向（对话框最下面那个框）。",
                0, kind=S.NOTE)
            return False

        title = str(chosen.get("标题") or "")
        _LOG.info("分支选定：%s（%s）", chosen.get("id"), title)
        # 自己写的走向单独一句 —— 屏幕上要能一眼看出"这次是人定的，不是导演挑的"。
        # [EN] The hand-written direction gets its own sentence — on screen it must be obvious at a glance that
        # [EN] "this was set by a human, not picked by the director".
        self._push_narrative(
            (f"（岔路口）你自己定了走向：「{title}」" if custom else
             f"（岔路口）选了「{title}」"
             + (f" —— {chosen.get('后果')}" if chosen.get("后果") else "")),
            0, kind=S.NOTE)
        # ★ **让选择真的影响故事**：把它当成一次导演介入写进事件流，
        #   下一拍的挑事提示词会读到它（"最近发生的事"），人物也会从派活里收到它。
        #   ⚠ 自己写的走向走**同一个落点** —— 两条路各写一套的话，
        #     "自己写"就只剩屏幕上那句话，对故事没有任何影响。
        # [EN] ★ **Make the choice actually affect the story**: write it into the event stream as a director
        # [EN] intervention,
        # [EN] the next beat's incident prompt will read it ("what happened recently"), and characters will
        # [EN] also receive it from the assignment.
        # [EN] ⚠ Hand-written directions go to the **same landing spot** — if each of the two paths wrote its
        # [EN] own,
        # [EN] "hand-written" would be reduced to that one line on screen, with no effect on the story at all.
        try:
            self.db.add_event(f"B{tick_num:04d}", f"（走向）{title}",
                              "走向选择", self.world.game_day,
                              self.world.on_stage_names()[:2], self.world.current_node)
        except Exception:                                       # noqa: BLE001
            pass
        self._branch_hint = title
        self.director.branch_hint = title          # 让导演在挑事时读得到
        # 清掉 run loop 自己那份（同一天只弹一次，但跨天还会弹 ——
        # 不清的话下一次会自动选回这一句）。
        # [EN] Clear the run loop's own copy (it pops once per day but again across days; if not
        # [EN] cleared, the next time it auto-selects this same sentence).
        #
        # ★★★ 2026-10-26：**导演那一份由 `_inject_event` 清**（`clear_branch_hint`）。
        #   这里原来只清 `_branch_custom`，注释却写着"用掉了就清掉" ——
        #   于是 `director.branch_hint` 永久残留，之后**每一个**挑事提示词都被要求
        #   "顺着这一句挑事"，故事锁死在一个方向上。用户报的
        #   「自己定一个，过一会又回到这个循环」有一半是这个原因。
        #   ⚠ 不要在**这里**清 `director.branch_hint`：这一拍之后才真正挑事，
        #     清早了那句话就白选了（选择必须真的落地）。
        # [EN] ★★★ 2026-10-26: **the director's copy is cleared by `_inject_event`**
        # [EN] (`clear_branch_hint`). This used to clear only `_branch_custom` while the comment
        # [EN] claimed "clear it once used" -- so `director.branch_hint` leaked forever and every
        # [EN] subsequent stirring prompt was told to "follow that line", locking the story onto one
        # [EN] direction. Half of the user's "I set my own and it comes back".
        # [EN] ⚠ Do not clear `director.branch_hint` **here**: the actual stirring happens after
        # [EN] this point; clearing early throws the choice away.
        self._branch_custom = ""
        return True

    def _mission_still_running(self, name: str, mission: str, limit: int = 6) -> bool:
        """这个人**还在办**上一件派活吗 —— 判据：上一件的关键词有没有出现在他最近的言行里。

        **纯逻辑，可单测。** 见 `_maybe_dispatch` 里那段说明。

        ⚠ "关键词"取法：把派活那句话切成 2 字片段，**去掉人名与虚词开头**，
          然后看他最近 `limit` 条自己的行动/台词里有没有命中 **任意 2 个**。
          阈值取 2 而不是 1：一个字撞上是常事（"的""他"），两个字同时撞上才像"在办那件事"。
        [EN] Is this person **still working on** the previous assignment? Test: do its keywords appear
        [EN] in his recent own actions/lines. ⚠ Keywords are 2-char slices with names and function-word
        [EN] heads removed; **at least two** hits are required (one hit is usually coincidence).
        [EN] ⚠ **This function alone can be eternally true**: if the person keeps mentioning the thing
        [EN] without ever finishing it, every round returns True. The release valve is
        [EN] `stuck_mission_release` in `_maybe_dispatch` -- do not assume this is self-healing.
        """
        m = str(mission or '').strip()
        if not m:
            return False
        try:
            texts = list(self.world.own_actions(name, int(limit)) or [])
            texts += list(self.world.last_own_lines(name, int(limit)) or [])
        except Exception:                                        # noqa: BLE001
            return False
        body = '\n'.join(str(x) for x in texts)
        if not body:
            return False
        skip = set('的了着过是在和与就都也还很太更最把被将给让对向为从一这那他她我你')
        hits = set()
        z = ''.join(ch for ch in m if '\u4e00' <= ch <= '\u9fff')
        for i in range(len(z) - 1):
            w = z[i:i + 2]
            if w[0] in skip:
                continue
            if w in body:
                hits.add(w)
        return len(hits) >= 2

    def _mission_stuck(self, rounds: int, cap: int) -> bool:
        """这个人的上一件派活是不是**卡死了** —— 已被"还在办"连续拦下 `rounds` 轮。

        **纯逻辑，可单测**（逻辑本体在 `stuck_mission_release`；这里只做转发，
        为的是让调用点读起来是"问一句"，且判据能钉到 `RunLoop` 的方法上）。

        ★★★ 为什么必须有这道放行闸（2026-10-19 第十二轮）
        --------------------------------------------------
        `_mission_still_running` 只回答"他还在办吗"。它答 True 有两种成因：
          ① 真在办（正常，该留着旧目标）；
          ② **卡死** —— 关键词一直在嘴里、事一直没办成。
        两者用同一个 True 表达，而调用方原来只会"跳过"⇒ 第 ② 种人被永久锁在
        同一件没办成的事上（snow_v11 实录：同一个人被连拦两轮，第三轮起再无新目标）。
        ⇒ 分辨法是**可数的**：**已经被**连续拦下几轮。攒到 `cap` 轮还在"办"，
          就不是在办，是卡死 —— 该换新的了。

        ⚠ 口径：`rounds` 是**本轮之前**已经攒下的轮数（不含本轮）。所以
          `cap=2` = "让他空转两轮，第三轮强制换"，`cap=1` = "空转一轮就换"。
        ⚠ 轮数**只在被拦时 +1，派到新活就归零**（`_maybe_dispatch` 里成对写）。
        ⚠ `cap <= 0` = 关闸（老行为：可能把人锁死一整晚）。
        ⚠ 字段在 `PersonState` 上、由调用方**直接属性读**。用"带默认值的取属性"
          会把"字段根本没接上"这件事藏起来，那是本项目踩过的坑。
        [EN] Is this person's previous assignment **dead-stuck** -- already blocked "still
        [EN] working on it" `rounds` rounds in a row? **Pure, unit-testable** (logic lives in
        [EN] `stuck_mission_release`; this only forwards it, so the call site reads as a question
        [EN] and the criterion can pin a `RunLoop` method). ⚠ `rounds` excludes the current
        [EN] round. ⚠ No defaulted attribute reads -- that hides a missing field.
        """
        return stuck_mission_release(rounds, cap)

    async def _maybe_dispatch(self, tick_num: int) -> dict[str, str]:
        """每 `DISPATCH_EVERY_TICKS` 拍给在场人物派一次活（`0` = 关闭）。

        **派"要什么"，从不派"怎么做"** —— 详见 `director.engine.dispatch`。
        派完推一条 `S.NOTE` 让用户看得见（导演在做的事不该是隐形的）。

        拿不到就**不写**（不编、也不清空上一条）：
        上一条派活还没被做完时，硬塞一条新的只会让人物来回换目标。
        
                English:
        Every `DISPATCH_EVERY_TICKS` ticks, assign a task once to the characters present (`0` = off).
                **Dispatch "what is wanted", never "how to do it"** -- see `director.engine.dispatch`.
                After dispatching, push a `S.NOTE` so the user can see it (what the director is doing should not be invisible).
                If it can't be obtained, **don't write** (don't make it up, and don't clear the previous one):
                when the previous dispatched task hasn't been finished yet, cramming in a new one only makes the character switch goals back and forth.
        """
        every = CFG.i("DISPATCH_EVERY_TICKS")
        if every <= 0 or tick_num % every != 0:
            return {}
        people = [a.name for a in self.agents if self.world.is_on_stage(a.ps)]
        if not people:
            return {}
        self._status('dispatching', n=len(people))
        try:
            missions = await self.director.dispatch(people)
        except Exception as e:                                  # noqa: BLE001
            self._warn_once('dispatch', f"派活失败（不影响推演）：{e!r}")
            return {}
        if not missions:
            return {}
        # ★★★ **上一件还在办，就不派新的**（2026-10-19 第十一轮：目标漂移的**硬机制**）
        # ------------------------------------------------------------------
        #   用户报的现象：同一个人一晚上被派了三件毫无关系的事
        #   （说定消磨几日 → 静看不插一言 → 把自语当风景照旧消磨）。
        #   根因就在下面那一行 `ps.mission = what` —— **无条件覆盖**。
        #   以前只有一句提示词"新派的一件必须是上面那件的下一步"，
        #   而提示词治不了这个（本项目最高频的失效模式）。
        #
        #   ⇒ 现在按"**他还在办吗**"决定要不要覆盖：
        #     · 上一件的关键词，出现在他最近 6 条**自己的**动作/台词里 ⇒ 他还在办
        #       ⇒ **跳过这个人**（保留旧目标，不覆盖）；
        #     · 一条都找不到 ⇒ 那件事已经停了 ⇒ 可以派新的。
        #   这条判据与 `world.open_asks`（"问了没人答"）是同一个思路：
        #   **"派了没人办"也是可数的**，不必去猜语义。
        #
        #   ⚠ 用关键词而不是"语义是否办成"：语义判断要再花一次模型调用，
        #     而且会退化成"你说他办完没"（本项目反复踩的坑）。
        #   ⚠ 跳过**不阻断**：跳过的人保留旧目标继续演，其余人正常派活。
        #   ⚠ 不能永远跳过：如果他自己卡住了（关键词一直不出现），下一轮就会重新派。
        #   ★★★ **但那只治了反方向的卡住**（2026-10-19 第十二轮，v11 真跑诊断出的
        #     第二个字数暴跌原因）：实测的卡住形状是"**关键词一直在、事一直没办成**"
        #     （剧本审读连续抓到同一个人"位置倒退""把上一拍已完成的动作又说一遍"
        #     "未按派活要求把那件事办成"）。这一形状下老逻辑会**永真**：拦下时只
        #     `missions.pop(name)`、**`ps.mission` 一个字节都没动** ⇒ 下一轮同一串派活
        #     + 同一个"最近 6 条自己言行"窗口 ⇒ 同一个 True ⇒ 再拦。**越卡住越永远派不到活**。
        #     日志实证（snow_v11）：第 16 拍、第 24 拍连续两次「这一轮不换（同一个人）」。
        #     ⇒ 现在按 `stuck_mission_release` 放行：连续被拦 `DISPATCH_STUCK_ROUNDS` 轮
        #       还在"办"，就判卡死、**强制换新的**（轮数是顺手就有的量，不额外花调用）。
        # [EN] ⚠ Skipping is non-blocking.
        # [EN] ⚠ Not forever: if he gets stuck (keywords never appear), he gets a new one next round.
        # [EN] ★★★ **But that only guards the opposite shape** (2026-10-19 round 12, the second
        # [EN] word-count-collapse cause diagnosed from a real run): the shape that actually occurs
        # [EN] is "keywords keep appearing while the thing never gets done". In that shape the old
        # [EN] logic is **eternally true** -- skipping only does `missions.pop(name)` and leaves
        # [EN] `ps.mission` untouched, so the next round re-evaluates the same string against the
        # [EN] same window and gets the same True. The more stuck he is, the more surely he never
        # [EN] gets new work. ⇒ Now released via `stuck_mission_release`: still "working on it"
        # [EN] after `DISPATCH_STUCK_ROUNDS` consecutive blocks ⇒ judged dead-stuck, **forced new**.
        # ★★★ **门口那位不适用"上一件还在办就不换"**（2026-10-21）。
        #   那一行防的是"目标漂移"（人被派了三件不相干的事）；而"门口有人等着、
        #   没人管"是**当下就漏出去**的东西 —— 它等不起 8 拍。两者不冲突：
        #   兜底只在"这一批派活里没有任何一条提到门口那位"时才出现，
        #   也就是**这一轮所有人都没被派去理他**时才触发一位，防漂移仍然管其他人。
        # [EN] ★★★ **The one at the door is exempt from "don't switch while busy"**
        # [EN] (2026-10-21). That guard prevents goal drift (a person assigned three unrelated
        # [EN] things); "someone is waiting at the door and nobody minds them" leaks **right now**
        # [EN] and cannot wait 8 beats. The two do not conflict: the fallback only appears when **no**
        # [EN] assignment in this batch mentions that person, i.e. when nobody was asked to deal
        # [EN] with him; drift prevention still governs everyone else.
        missions = self._apply_missions(missions, people)
        if not missions:
            return {}
        self._push_narrative("（导演派活）" + "；".join(
            f"{n}：{w}" for n, w in missions.items()), 0, kind=S.NOTE)
        _LOG.info("第 %d 拍派活：%s", tick_num,
                  "；".join(f"{n}→{w}" for n, w in missions.items()))
        return missions

    def _apply_missions(self, missions: dict, people: list[str]) -> dict:
        """把派活写进人物状态。返回**真正生效**的那部分（被"还在办"拦下的已剔除）。

        两条规则，顺序不能反：
          1. **门口兜底的那一条先放行**（`_forced_names`）—— 它等不起，
             而"上一件还在办"防的是目标漂移，两者不冲突（兜底只在没人管门口时出现）；
          2. 其余的人按"上一件还在办就不换"处理（2026-10-19 第十一轮防漂移的硬机制）。

        ★ 抽成独立方法的理由：**判据要能测行为**。原来这段嵌在 `_maybe_branch` 里，
          只能拿源码字符串当判据 —— 而"判据测字符串"是假判据（把 `if` 改成 `False`
          之后名字还在，永远绿）。抽出来之后可以真的拿一份 missions 跑一遍，
          看那个人物的 `mission` 到底有没有被改写。
        
                English:
        Write assignments into the character states. Returns the part that **actually took
        effect** (those blocked by "still working on the previous one" are removed).
        Two rules, and the order must not be reversed:
          1. **The door fallback goes through first** (`_forced_names`) -- it cannot wait, while
             "still working on the previous one" guards against goal drift; they do not conflict
             (the fallback only appears when nobody is minding the door);
          2. Everyone else follows "don't switch while the previous one is still running"
             (the hard anti-drift mechanism from round eleven, 2026-10-19).
        ★ Why extract it into a method: **criteria must be able to test behaviour**. This block
          used to sit inside `_maybe_branch`, so the only available criterion was a source-string
          match -- and "a criterion that matches strings" is a false criterion (rename `if` to
          `False` and the name is still there, permanently green). Extracted, a real set of
          missions can be run through it to see whether that character's `mission` was rewritten.
        """
        cap = CFG.i("DISPATCH_STUCK_ROUNDS")
        forced_door = set(getattr(self.director, '_forced_names', None) or ())
        forced: list[str] = []
        kept: list[str] = []
        for name, what in list(missions.items()):
            ps = self.world.people.get(name)
            if ps is None:
                continue
            if name in forced_door:
                ps.mission = what
                ps.mission_stuck = 0
                continue
            if self._mission_still_running(name, ps.mission):
                if self._mission_stuck(ps.mission_stuck, cap):
                    forced.append(name)                     # 卡死 → 放行换新的
                    ps.mission_stuck = 0
                else:
                    ps.mission_stuck = ps.mission_stuck + 1
                    kept.append(name)
                    continue
            if ps.mission:
                # 记下上一件，给"漂移率"诊断用（`director.assignment_shared`）
                try:
                    prev = str(ps.mission)
                    if assignment_shared(prev, what, tuple(people)) == 0:
                        _LOG.info('派活断裂：%s 上一件「%s」→ 这一件「%s」', name, prev[:24], what[:24])
                except Exception:                                # noqa: BLE001
                    pass
            ps.mission = what
            ps.mission_stuck = 0
        for name in kept:
            missions.pop(name, None)
        if kept:
            _LOG.info('派活：%d 人的上一件还在办，这一轮不换（%s）', len(kept), '、'.join(kept))
        if forced:
            # 单独一行：这是**兜底放行**，不是"换目标很随便"。
            # 作者在日志里看到它，就该知道那个人卡了很久。
            # [EN] A line of its own: this is the **fallback release**, not "switching goals at
            # [EN] will". Seeing it in the log means that person was stuck for a long time.
            _LOG.info('派活放行：%d 人的上一件连续 %d 轮还在办却办不完，判卡死，强制换新的（%s）',
                      len(forced), cap, '、'.join(forced))
        return missions

    async def _check_progress(self) -> bool:
        """导演进度评估 + 失败播报。返回 `True` = 已到故事终点（主循环该收尾）。

        ★ 「拿不到结论」与「判据确实没满足」是**两回事**（2026-10-06 修）。
        以前 `evaluate_progress` 把两者都返回成 `(False, "")`，于是
        "模型把额度花在思考上、一个字没答"表现成"故事还没走到那儿"：
        **节点永远不推进，而界面上一个字都没有**。
        现在失败会累计，连续 3 拍就讲给用户听 —— 和 `_fail_streak` 同一套做法、
        同一个道理：连着一屏"没进展"，人是看不出故障的。
        
                English:
        Director progress evaluation + failure broadcast. Returns `True` = story endpoint reached (main
        loop should wrap up).
                ★ "Can't get a conclusion" and "the criteria truly aren't met" are **two different things** (fixed 2026-10-06).
                Previously `evaluate_progress` returned both as `(False, "")`, so
                "the model spends its budget on thinking, answers not a single word" showed up as "the story hasn't reached there yet":
                **the node never advances, and there isn't a single word on the UI**.
                Now failures accumulate, and after 3 consecutive ticks it's told to the user -- same approach as `_fail_streak`,
                same principle: with a whole screen of "no progress", a person can't tell there's a fault.
        """
        self._status('evaluating')
        recent_events = self.db.recent_events(5)
        if not recent_events:
            return False
        # ★★ **同一个问题不重复问第二遍**（2026-10-10，真机日志量出来的浪费）
        # [EN] ★★ **Never ask the same question twice** (2026-10-10, waste measured from real-device logs)
        # ---------------------------------------------------------------
        # 进度评估的输入 = 「当前节点 + 最近 5 条事件」。而事件表**只在有值得记的
        # 事情时才写**（导演注入 / 走向选择 / 后台批次）—— 实测那一天里它一共
        # 只有 **2 行**，19:32 之后再没变过。于是接下来的 45 分钟里，
        # 每次问的都是**一模一样的问题**：
        # [EN] Progress eval input = "current node + last 5 events". And the event table **is only written when
        # [EN] there is something worth
        # [EN] recording** (director injection / direction choice / background batch) — measured, that day it
        # [EN] had only
        # [EN] **2 rows** in total, and never changed after 19:32. So for the next 45 minutes,
        # [EN] every ask was **exactly the same question**:
        #     `progress_eval` 共 385 次，其中 **326 次的输入完全相同**
        #     （`in=239` 那一种形状问了 326 遍）。
        # [EN] `progress_eval` ran 385 times, of which **326 had identical input**
        # [EN] (the `in=239` shape was asked 326 times).
        # 那是纯浪费：输入一个字都没变 ⇒ 再问一遍只会得到同一个结论。
        # 而它又是全项目调用最密的"结论型"用途（主循环里每一拍一次）。
        # [EN] That is pure waste: not a single character of input changed ⇒ asking again only yields the same
        # [EN] conclusion.
        # [EN] And it is the most frequently called "conclusion-type" use in the whole project (once per beat
        # [EN] in the main loop).
        # ⚠ 只在**真拿到结论**（`verdict.ok`）时才记下签名：失败要允许重问
        #   （那是"没拿到"，不是"拿到了一个否"——两件事在这个项目里一直是分开的）。
        # ⚠ 节点一推进，签名里的 `current_node` 就变了 ⇒ 下一拍自然会重新问。
        # ⚠ **代价说明白**：模型在**完全相同的输入**上偶尔会给出不同的答案
        #   （实测同一份输入既出现过「满足」也出现过「不满足」）。去掉重复提问
        #   等于去掉了那份"运气"——这是**故意的**：靠运气推进节点本来就是错的，
        #   该让判据在**信息真的变了**的时候再判一次。而"信息会变"由
        #   `DIRECTOR_QUIET_MINUTES`（安静太久也照常挑事）兜着，所以空窗有上界。
        # [EN] ⚠ Only record the signature when **a conclusion was actually obtained** (`verdict.ok`): failures
        # [EN] must be allowed to re-ask
        # [EN] (that is "didn't get one", not "got a no" — the two have always been kept separate in this
        # [EN] project).
        # [EN] ⚠ Once the node advances, `current_node` in the signature changes ⇒ the next beat naturally
        # [EN] re-asks.
        # [EN] ⚠ **Spell out the cost**: the model occasionally gives different answers on **completely
        # [EN] identical input**
        # [EN] (measured, the same input produced both "met" and "not met"). Removing duplicate asks
        # [EN] removes that bit of "luck" — this is **intentional**: advancing nodes by luck was wrong to begin
        # [EN] with,
        # [EN] the criteria should be judged again when **the information really changed**. And "information
        # [EN] will change" is covered by
        # [EN] `DIRECTOR_QUIET_MINUTES` (picks an incident as usual when quiet too long), so the empty window
        # [EN] has an upper bound.
        sig = (str(getattr(self.world, 'current_node', '') or ''),
               tuple((str(e.get('id') or ''), str(e.get('content') or ''))
                     for e in recent_events))
        # ⚠ 用 `getattr` 取，不要直接 `self._progress_sig`：
        #   判据与探针里有不少用 `RunLoop.__new__` 造对象、**绕过 `__init__`** 的
        #   夹具（`verify_branch` 就是），直接取属性会 `AttributeError` ——
        #   而那看起来像"产品代码坏了"，其实是夹具没走构造。
        # [EN] ⚠ Use `getattr` to read it, don't access `self._progress_sig` directly:
        # [EN] many assertions and probes build objects with `RunLoop.__new__`, **bypassing `__init__`**
        # [EN] (that includes `verify_branch`); accessing the attribute directly raises `AttributeError` —
        # [EN] and that looks like "the product code is broken", when in fact the fixture skipped the
        # [EN] constructor.
        if sig == getattr(self, '_progress_sig', None):
            return False
        verdict = await self.director.evaluate_progress(recent_events)
        if not verdict.ok:
            self._progress_fail_streak += 1
            if self._progress_fail_streak == 3:
                msg = (f"（进度评估连续 {self._progress_fail_streak} 拍没拿到结论："
                       f"{verdict.why}）节点不会推进 —— 已继续推演，"
                       "可到「天机 · 日志」查看原始回复。")
                _LOG.warning(msg)
                self._push_narrative(msg, 0, kind=S.NOTE)
            return False
        self._progress_fail_streak = 0
        self._progress_sig = sig          # 真拿到结论才记住（见上面那段说明）
        # [EN] Only remember it when a conclusion was actually obtained (see the note above)
        # ★★★ 2026-10-21（用户：「剧情的进度表一直不动」）：**不管满足与否，先记下「走到哪儿了」**。
        #   旧写法只在 `verdict.done` 时才用 `verdict.desc`（下面那行 `节点完成`），
        #   于是"还没满足"的那些评估里，模型附的进展描述**整句被丢掉** ——
        #   界面上只剩一个不动的 `0/4`，用户只能得出"它卡住了"。
        #   实测（望江楼 2026-10-21 21:34→22:18）：14 次评估、7 次结论全是 false，
        #   每次都带着一句"线索初现"这种话 —— 全被扔了。
        #   ⚠ 空串不覆盖：模型偶尔不给这一项，别把上一次的进展擦掉。
        # [EN] ★★★ 2026-10-21 (user: "the plot progress table never moves"): **record "where we are"
        # [EN] whether or not the criteria are met**. The old code used `verdict.desc` only when
        # [EN] `verdict.done` (the "node complete" line below), so on every not-yet-met evaluation the
        # [EN] model's progress line was **discarded whole** -- leaving an unchanging `0/4` and the
        # [EN] conclusion "it is stuck". Measured (Mowenlou, 2026-10-21 21:34->22:18): 14 evaluations,
        # [EN] 7 verdicts all false, each carrying a line like "first clue appears" -- all thrown away.
        # [EN] ⚠ An empty string must not overwrite: the model sometimes omits this field, and that
        # [EN] must not erase the previous note.
        _desc = str(getattr(verdict, 'desc', '') or '').strip()
        if _desc:
            self.world.progress_note = _desc
        if not verdict.done:
            return False
        # ★★★ 2026-10-27：**章数下限** —— 判据满足了，但这一站还没写够章数 ⇒ **先不往前走**。
        #
        #   为什么要这一道闸（用户原话：「每个地方至少有若干章节」）：
        #   以前"这一站的事成了没有"是**唯一**的过站条件，而模型判得很快 ——
        #   实测一站一天就过 ⇒ 八个地点跑完只有八章，每个地点连起承转合都摊不开。
        #   `篇幅` 管的是**一天写多厚**（拍预算），挡不住"一天就走"。
        #
        #   ⚠ 卡住时**必须说一句人话、并且告诉它接着写什么**：只卡住不给活干，
        #     导演会拿一个"已经完成"的判据反复派活 —— 那就是空转（本项目记过的坑）。
        #   ⚠ 不需要"防死锁"兜底：`_have` 每过一天必然 +1，所以一定到得了 `_need`。
        #     （第一版写了 `_have < _need * 2` 那条，它是**死代码** ——
        #      `_have >= _need*2` 时 `_have < _need` 早已为假；反例法第 ⑬ 刀打上去
        #      判据照样绿，就是这么露出来的。）
        # [EN] ★★★ 2026-10-27: **minimum chapters** -- the criterion is met but the station has not
        # [EN] produced enough chapters, so **do not advance yet**. Why (user: "each place should have
        # [EN] at least a few chapters"): "is this station's business finished" used to be the **only**
        # [EN] condition for advancing, and the model answers that fast -- a station advanced in one
        # [EN] day, so eight places produced eight chapters, too few to lay out a beginning/middle/end.
        # [EN] `篇幅` only controls **how thick a single day is**; it cannot stop "leaving in a day".
        # [EN] ⚠ When holding, **say a human line that also says what to write next**: holding without
        # [EN] giving work makes the director keep dispatching an already-met criterion -- idling.
        # [EN] ⚠ The `_need * 2` ceiling is **deadlock insurance**: if a station genuinely cannot fill
        # [EN] its chapters, release it and log, never strand a run on one station forever.
        _need = 0
        try:
            from ingest.progress import min_chapters_for
            _need = int(min_chapters_for(self.world.current_node_info() or {}) or 0)
        except Exception:                                    # noqa: BLE001
            _need = 0
        _have = self._days_in_node()
        if _need > 0 and _have < _need:
            if getattr(self, '_hold_note_day', -1) != _have:
                self._hold_note_day = _have
                self._push_narrative(
                    f"（进度）这一站的事已经成了：{verdict.desc}。"
                    f"但设定里这一站要写 {_need} 章，现在才 {_have} 章 —— "
                    f"接着写这件事的**余波**：谁因此改变了什么、谁还欠着什么、"
                    f"桌上多出来的那样东西。写够了才往下一站走。", 0, kind=S.NOTE)
                _LOG.info("章数下限：当前站要 %d 章、已演 %d 章 ⇒ 先不推进", _need, _have)
            return False
        if _need > 0 and _have >= _need:
            _LOG.info("章数下限：当前站要 %d 章、已演 %d 章 ⇒ 放行", _need, _have)
        self._push_narrative(f"（进度）节点完成：{verdict.desc}", 0, kind=S.NOTE)
        # 一站刚走完 = 最自然的分岔口 → 下一拍问一次"往哪走"
        # [EN] A station just finished = the most natural fork → the next beat asks once "which way to go"
        self._branch_pending = True
        # ★★ 2026-10-27：**这一站自带"结局选项"**（作者写在节点上的 `选项`）
        #   ⇒ 这次岔路口不是"往哪走"，而是**让作者挑结局**。
        #   ⚠ 它是一次性提示：读完（`_maybe_branch` 用掉）就清 —— 全项目只写不清
        #   = 永久锁死在一个方向，而作者看到的只是"我定了，没变化"（本项目的老教训）。
        # [EN] ★★ 2026-10-27: **this station carries its own ending options** (the author's `选项` on
        # [EN] the node) => this fork is not "which way next" but **let the author pick the ending**.
        # [EN] ⚠ It is a one-shot hint: cleared as soon as it is read (used by `_maybe_branch`) --
        # [EN] writing without clearing locks the run into one direction forever, while the author
        # [EN] only sees "I chose, nothing changed" (a lesson already recorded here).
        _opts = [str(x).strip() for x in
                 ((self.world.current_node_info() or {}).get('选项') or [])
                 if str(x or '').strip()]
        self._pending_options = _opts or None
        if _opts:
            _LOG.info("这一站有作者写的结局选项 %s ⇒ 岔路口改成挑结局", '、'.join(_opts))
        if self.director.advance_node() is None and self.director.is_at_end():
            return True
        return False

    def _review_record_only(self, kind: str, text: str) -> None:
        """只记账、**不判**（结构性的东西：分隔符 / 镜头切换 / 换场景）。

        用途见 `_push_divider` 与 `_push_scene` —— 用户要的"**场景切换**也要
        记下来"就是这一类。它们不是谁说的话，拿去问"是不是人话"只会误报，
        所以规则闸对它们不生效（`_REVIEW_KINDS` 之外）。
        
                English:
        Only record, **don't judge** (structural things: separators / shot switches / scene changes).
                For usage see `_push_divider` and `_push_scene` -- what the user wants, "**scene switches** should also
                be recorded", is this category. They aren't what anyone said; taking them and asking "is this human speech" only produces false positives,
                so the rule gate doesn't apply to them (outside `_REVIEW_KINDS`).
        """
        if not CFG.b('SCRIPT_REVIEW'):
            return
        log = getattr(self, 'script_log', None)
        if log is None:
            return
        try:
            log.add(kind=str(kind or 'note'), text=str(text or ''),
                                day=int(self._current_day or 0),
                                tick=int(self._tick_no or 0), source='window',
                                place=str(getattr(self.world, 'scene', '') or ''))
        except Exception:                                        # noqa: BLE001
            pass

    def _review_gate(self, text: str, kind: str, who: str = '',
                     to: str = '', raw: str = '',
                     to_ledger: bool = True) -> str | None:
        """**剧本审读的第二道关**：凡是往窗口去的东西都在这里**过一遍并记账**。

        两道关的分工（都是同一个职位 `script_doctor`）：
          · 第一道在 `_script_review`（`_process_actions` 里）—— 管**剧情类词条**，
            拿得到整场上下文，能**改写**；
          · 第二道就是这里 —— 它是**唯一**能看见"所有往窗口去的东西"的地方
            （前情提要 / 今日简介 / 今日任务 / 导演事件（伏笔激活）/ 阶段 /
            剧组状态 / 收工总结 / 分镜卡…），所以：

        | 干什么 | 为什么在这一处 |
        |---|---|
        | **记账**（一切上屏的东西按顺序记下来） | 用户要的"所有输出到窗口的东西…都要让这个Agent记录下来"；过了这个门就是读者看得到的 |
        | **规则闸**（零成本） | 剧情类的内容（不只是演员台词）在这里再筛一遍形式问题 |

        ⚠ 这里**只跑规则层、不调模型**：每拍几十次调用下不起；
          语感与上下文那一层在第一道关（每拍一次）已经做了。
        ⚠ 拦下**不是静默**：台账、日志、《剧本审读.md》三处都留痕；
          再回一句 `None` 让调用方别推。
        
                English:
        **The second gate of script review**: everything heading to the window is **passed through and
        recorded** here.
                Division of labor between the two gates (both are the same role `script_doctor`):
                  · The first gate is in `_script_review` (inside `_process_actions`) -- handles **plot-type entries**,
                    gets the whole scene context, can **rewrite**;
                  · The second gate is here -- it is the **only** place that can see "everything heading to the window"
                    (recap / today's intro / today's tasks / director events (foreshadow activation) / phase /
                    crew status / wrap-up summary / storyboard cards...), so:
                | What it does | Why at this one place |
                |---|---|
                | **Record** (record everything that goes on screen in order) | what the user wants: "everything output to the window... must be recorded by this Agent"; once past this gate it's what the reader sees |
                | **Rule gate** (zero cost) | plot-type content (not just actor lines) gets its formal issues filtered once more here |
                ⚠ Here **only the rule layer runs, no model calls**: dozens of calls per tick is unaffordable;
                  the language-sense and context layer was already done at the first gate (once per tick).
                ⚠ Blocking is **not silent**: the ledger, the log, and 《剧本审读.md》 all leave a trace;
                  then return `None` so the caller doesn't push.
        """
        if not CFG.b('SCRIPT_REVIEW'):
            return text
        t = str(text or '')
        k = str(kind or '')
        why = ''
        if k in self._REVIEW_KINDS and t.strip():
            why = REVIEW.rule_check(t, kind=('dialogue' if k == S.DIALOGUE else 'action'))
            # ★★★ 2026-10-18：**说出别人的秘密**（信息差那一层）。
            #   为什么放在这里：这是"所有上屏的东西"唯一的门口，而且零成本
            #   （`world.leaks` 只是最长公共片段）。
            #   ⚠ 演员提示词里也写了"不许替他们说破"，但提示词写了 ≠ 生效 ——
            #     这一条是**兜底**，不是替代。
            # [EN] ★★★ 2026-10-18: **stating someone else's secret** (the information-asymmetry
            # [EN] layer). Why here: this is the single doorway for everything going on screen, and
            # [EN] it is free (`world.leaks` is just a longest-common-run check).
            # [EN] ⚠ The actor prompt also says "never tell their secret for them", but written in a
            # [EN] prompt != in effect -- this is a **backstop**, not a replacement.
            if not why and getattr(self, 'world', None) is not None:
                # ⚠⚠ `self.world` 必须用 getattr 探一下：这扇门是"所有上屏"的第一个入口，
                #   而 `stop()` 会在 `world` 还没就绪时推那条"正在停止"（判据用
                #   `RunLoop.__new__` 造的裸对象正是这个形状）。第一版直接 `self.world`
                #   ⇒ AttributeError 从 `_push_narrative` 冒出去 ⇒ **中栏那条发不出来**，
                #   表现成用户报过的"点了停止没反应"（`verify_day_start` C1 抓出来的）。
                # [EN] ⚠⚠ `self.world` must be probed with getattr: this gate is the first entrance
                # [EN] for **everything** on screen, and `stop()` pushes the "stopping" line while
                # [EN] `world` may not be ready (bare objects from `RunLoop.__new__` have exactly that
                # [EN] shape). The first version used `self.world` directly => AttributeError escaped
                # [EN] from `_push_narrative` => **the middle-column line was never sent**, which is the
                # [EN] user-reported "clicked stop, nothing happened" (caught by `verify_day_start` C1).
                why = REVIEW.leak_check(t, self.world, who)
            # ★★★ 2026-10-18：**把自己的「需求」说破**（专业论述 #4 欲望 vs 需求）。
            #   演员提示词里已经明写"不许说出口"，但提示词写了 ≠ 生效；
            #   而"把动机总结成一句漂亮话"正是模型的默认行为。
            #   ⚠ 只判台词（`k == DIALOGUE`）：动作句里不可能说破需求。
            #   ⚠⚠ `self.world` **用 getattr 取**：这条闸门是"所有上屏"的第一个门口，
            #     而 `stop()` 那条路会在 `world` 还没就绪时推消息（判据用 `RunLoop.__new__`
            #     造的裸对象就是这样）。第一版直接 `self.world` ⇒ AttributeError 从
            #     `_push_narrative` 抛出去 ⇒ **中栏那条"正在停止"根本发不出来**
            #     （表现成"点了停止没反应"，正是这条闸门最不该造成的故障）。
            # [EN] ★★★ 2026-10-18: **saying his own need out loud** (#4 want vs need). The actor
            # [EN] prompt already says "never say it", but written in a prompt != in effect, and
            # [EN] "summarise the motive into a nice line" is exactly the model's default.
            # [EN] ⚠ Dialogue only. ⚠⚠ `self.world` is read via **getattr**: this gate is the first
            # [EN] doorway for **everything** on screen, and `stop()` pushes a message when `world`
            # [EN] may not exist yet (bare objects made with `RunLoop.__new__`). The first version
            # [EN] used `self.world` directly => AttributeError escaped from `_push_narrative` => the
            # [EN] "stopping" line never reached the middle column ("clicked stop, nothing happened").
            if not why and k == S.DIALOGUE and getattr(self, 'world', None) is not None:
                why = REVIEW.need_check(t, self.world, who)
        blocked = bool(why) and CFG.b('SCRIPT_REVIEW_STRICT')
        log = getattr(self, 'script_log', None)
        try:
            log.add(
                # ★ 记**词条原文**（`raw`）而不是渲染后那句：渲染那句里带着
                #   "某人：" 这样的说话人前缀，记进去之后台账里就是
                #   「〔对话·某人〕某人：…」—— 递给模型的"已经出现的话"
                #   会重复一遍名字（模型照样能读，但那是白占额度）。
                #   `raw` 只有词条那一条路会传（`_process_actions`）。
                # [EN] ★ Record the **raw entry text** (`raw`), not the rendered sentence: the rendered sentence
                # [EN] carries
                # [EN] a speaker prefix like "Someone:", and once recorded, the ledger shows
                # [EN] "〔Dialogue·Someone〕Someone: …" — the "already appeared words" handed to the model
                # [EN] will repeat the name (the model can still read it, but it wastes quota for nothing).
                # [EN] `raw` is only passed by the entry path (`_process_actions`).
                kind=k or 'text', text=(raw or t), who=who, to=to,
                day=int(self._current_day or 0), tick=int(self._tick_no or 0),
                source='window', place=str(getattr(self.world, 'scene', '') or ''),
                blocked=blocked, why=why,
                # ⚠ 按**词条原文**找那一笔（`_review_rewrite` 存的就是词条原文）；
                #   拿渲染后那句去找永远找不到（渲染句带着"某人："前缀）——
                #   第一版就是这么把"原文"丢了的。
                # [EN] ⚠ Find that entry by **raw entry text** (`_review_rewrite` stores the raw entry text);
                # [EN] searching with the rendered sentence will never find it (the rendered sentence carries a
                # [EN] "Someone:" prefix) —
                # [EN] that is how the first version lost the "raw text".
                was=(self._review_rewrites.pop(str(raw or '').strip(), '')
                     or self._review_rewrites.pop(t, '')),
                # ★★★ 2026-10-18：`to_ledger=False` ⇒ **只上屏、不进"读者看过的那一份"**。
                #   场景介绍（`scene_intro`）就是这一类：它是**给美术画平面用的场记单**
                #   （"纸门向西开 / 北墙摆火钵 / 南边岛村坐"），用户 2026-10-12 明确要求
                #   它"照着就能画出平面" ⇒ 天生是工具化的。可它原来进了台账，
                #   小说作家整理正文时把它当**第一段**原样上屏，读者看到的是场记单
                #   （实测：雪国那篇第一段就是"温泉旅馆岛村客房：纸门向西开…"）。
                #   ⚠ 用 `archived` 而不是"不上屏"：那一屏是用户点名要的，
                #     只是它不属于小说正文。语义与"审读改写记录"完全一致
                #     （进 `everything()`、不进 `recent()`）。
                # [EN] ★★★ 2026-10-18: `to_ledger=False` => **on screen only, not in "the copy the
                # [EN] reader has seen"**. The scene intro is exactly this: a **stage note for the art
                # [EN] department to draw the floor plan** ("paper door opens west / brazier on the
                # [EN] north wall / Shimamura sits south"), which the user explicitly asked to be
                # [EN] detailed enough to draw a plan => tool-shaped by design. It used to enter the
                # [EN] ledger, so the writer took it as the **first paragraph** of the novel and the
                # [EN] reader saw a stage note (measured: Snow Country's opening paragraph was
                # [EN] "Onsen inn, Shimamura's room: the paper door opens west...").
                # [EN] ⚠ Use `archived`, not "don't show": that screen was explicitly requested; it
                # [EN] just is not part of the novel. Same semantics as the rewrite records
                # [EN] (goes into `everything()`, not into `recent()`).
                archived=not to_ledger)
        except Exception:                                        # noqa: BLE001
            pass
        if not blocked:
            return t
        self._review_blocked_today += 1
        _LOG.info('剧本审读：拦下一条（%s）—— %s', why, ' '.join(t.split())[:60])
        return None

    def _push_narrative(self, text: str, priority: int, is_key_event: bool = False,
                        kind: str = '', who: str = '', to: str = '',
                        raw: str = '', to_ledger: bool = True,
                        detail: dict | None = None, update_key: str = '') -> None:
        """将叙事文本推入显示队列。

        `kind` 是词条类型（`display.script` 那套常量）—— 界面拿它决定
        这一行用哪种样式（对白 / 旁白 / 动作 / 环境 / 回想…）。

        ★★ 2026-10-07：**先喊人、再排队**。
        原来是反的（先 `create_task(display.enqueue_narrative(...))`，再调
        `_on_narrative`）—— 于是那条 `create_task` 一旦抛（最典型：
        **当前没有事件循环**，比如在协程外按暂停；或哪些夹具路径上
        `self.display` 根本没建），异常会先冒出来，**后面那句回调再也执行不到**。
        屏幕上表现就是"这条消息凭空没了"，而日志里只有一句 `warn_once`
        —— 最难查的一类 bug（用户点名要显示的几条：开演 / 临时暂停 /
        总结会，全走这条路）。

        现在：**中栏那份先发**（它是判据与读者看的那个），
        显示队列只是"顺带再排一次"，它坏了自己吞掉，不许连累中栏。

        ★★ 2026-10-08 **在这之前多了剧本审读那一关**（`_review_gate`）：
        它就是"所有输出到窗口的东西"的**唯一**门口 —— 记账与规则闸都在那儿。
        被拦下的**直接 `return`**（不播报、也不进显示队列）。
        
                English:
        Push narrative text into the display queue.
                `kind` is the entry type (the `display.script` constant set) -- the UI uses it to decide
                which style this line uses (dialogue / narration / action / environment / flashback...).
                ★★ 2026-10-07: **Call the person first, then enqueue**.
                It used to be the reverse (first `create_task(display.enqueue_narrative(...))`, then call
                `_on_narrative`) -- so once that `create_task` throws (most typically:
                **there's currently no event loop**, e.g. pausing outside a coroutine; or on some fixture paths
                `self.display` was never created at all), the exception surfaces first, **and the following callback line can never be executed**.
                On screen this looks like "this message vanished into thin air", while the log only has one `warn_once`
                -- the hardest class of bug to track down (the few the user explicitly asked to display: show start / temporary pause /
                summary meeting, all go through this path).
                Now: **the middle-column copy is sent first** (it is the criterion and the one the reader sees),
                the display queue just "happens to enqueue it again"; if it breaks it swallows the error itself and must not drag the middle column down.
                ★★ 2026-10-08 **before this there is an extra script review gate** (`_review_gate`):
                it is the **sole** doorway for "everything output to the window" -- both the bookkeeping and the rule gate live there.
                Blocked items **`return` directly** (no broadcast, and not pushed to the display queue).
        `detail` / `update_key`（2026-10-23 加）：剧组消息前面那个折叠箭头要的两样东西。
          · `detail`  这一条**点开以后看什么**（`{'state','body','role'}` 这类小字典，
                      界面自己决定怎么画；这里不做任何排版）；
          · `update_key` 这一条**是在更新哪一位已有的那一条**（职位 key）。
                      界面收到它就把那条**原地改掉**（不新增一行）—— 用户要的
                      「正在执行 → 已完成」是同一条消息的两个状态，不是两条。
          ⚠ 两者都只是**透传**：`_push_Narrative` 不解释它们，也不根据它们改变
            审读/记账的行为（记账照旧只数 `text`）—— 那是"数据"不是"策略"。
        [EN] `detail` / `update_key` (added 2026-10-23): the two things the collapsible
        arrow in front of crew messages needs.
        · `detail` -- what this entry shows when expanded (a small dict like
          `{'state','body','role'}`; the UI decides how to draw it, no layout here).
        · `update_key` -- which role's existing entry this one **updates**. The UI rewrites
          that entry **in place** instead of adding a row: the user wants "executing ->
          finished" as two states of the same message, not two messages.
        ⚠ Both are **pass-through only**: `_push_narrative` neither interprets them nor
          changes review/ledger behaviour (the ledger still counts only `text`) -- they are
          data, not policy.
        """
        text = self._review_gate(text, kind, who=who, to=to, raw=raw,
                                 to_ledger=to_ledger)
        if text is None:
            return
        # ★ 今天写了多少字（2026-10-11）—— 对着 `ROUND_DAILY_WORDS` 的软目标显示。
        #   数在**这里**（所有上屏叙事唯一的漏斗）：数在别处就会出现
        #   "屏幕上有的没算、算了的没上屏"，而那个数字是给人当进度看的，
        #   差一截比没有更误导。
        # [EN] ★ How many words written today (2026-10-11) — displayed against the soft target
        # [EN] `ROUND_DAILY_WORDS`.
        # [EN] Count **here** (the only funnel for all on-screen narrative): counting elsewhere produces
        # [EN] "what's on screen wasn't counted, what was counted isn't on screen", and that number is meant as
        # [EN] progress for a human,
        # [EN] being off by a chunk is more misleading than not having it.
        try:
            self._day_words += len(str(text))
        except Exception:                                        # noqa: BLE001
            pass
        if self._on_narrative:
            try:
                self._on_narrative(text, priority, kind=kind,
                                   detail=detail, update_key=update_key)
            except TypeError as e:
                # 老回调只收两个位置参数 —— **退回两参，但要说一声**。
                # ⚠ 这里第一版写的是 `except Exception: pass`，结果「回调签名不匹配」
                #   把整条叙事流吞成了空白（`verify_run_control` 当场抓到）。
                #   播报失败可以不影响推演，但**不许不留痕**。
                # [EN] The old callback only takes two positional args — **fall back to two args, but say something**.
                # [EN] ⚠ The first version here wrote `except Exception: pass`, and as a result "callback signature
                # [EN] mismatch"
                # [EN] swallowed the entire narrative stream into blank (caught on the spot by `verify_run_control`).
                # [EN] Broadcast failures may not affect the simulation, but **no failure may go unrecorded**.
                self._warn_once('narrative', f"叙事回调不收 kind 参数（{e}）"
                                            "—— 已退回两参调用，界面拿不到词条类型")
                try:
                    self._on_narrative(text, priority)
                except Exception:                           # noqa: BLE001
                    pass
            except Exception as e:                          # noqa: BLE001
                self._warn_once('narrative_err', f"叙事回调失败：{e!r}")
        # 显示队列（CLI / 其它消费者读它）：**排在后面，且自己吞异常**。
        # [EN] Display queue (read by CLI / other consumers): **placed after, and swallows its own
        # [EN] exceptions**.
        try:
            import asyncio
            asyncio.create_task(self.display.enqueue_narrative(
                text, priority, self.world.clock_display(), is_key_event))
        except Exception:                                   # noqa: BLE001
            pass

    def _push_divider(self, divider: 'D.Divider') -> None:
        """推一条分隔符到界面（中栏那条「左右细线 + 中间标签」）。

        ★ 2026-10-08：**顺手记进审读台账**（用户点名的"场景切换"就在这一类里）
        —— 它不是"话"，不过规则闸（规则层只管剧情类），只记一笔。
        
                English:
        Push a separator to the UI (the middle-column one, "thin lines on both sides + a label in the
        middle").
                ★ 2026-10-08: **conveniently record it into the review ledger** (the "scene switch" the user named falls in this category)
                -- it is not "speech", it does not pass the rule gate (the rule layer only handles plot-type things), just log an entry.
        """
        self._review_record_only('divider', str(getattr(divider, 'label', lambda: '')()
                                                or ''))
        if self._on_divider:
            try:
                self._on_divider(divider)
            except Exception as e:                          # noqa: BLE001
                self._warn_once('divider', f"分隔符回调失败：{e!r}")

    # ══════════════════════════════════════════════════════════════════
    #  **场景切换 = 一个明确的动作**（2026-10-22，用户点名）
    # [EN] **A scene change is an explicit action** (user, 2026-10-22)
    # ══════════════════════════════════════════════════════════════════
    #: 不像"地名"、更像"场面话"的字 —— 出现了就不登记成新地点。
    #: ⚠ 这不是多余的谨慎：`_maybe_shift_scene` 的注释里记着一次事故 ——
    #:   模型随口给的「门外」「对方」「账台」全成了场景名，一场戏被切得七零八落，
    #:   两条判据当场变红。所以"登记新地点"必须有门槛。
    # [EN] Words that read as stage talk rather than a place name -- never registered.
    # [EN] ⚠ This is not gratuitous caution: `_maybe_shift_scene` records an incident where the model's
    # [EN] casual "outside the door" / "the other party" / "the counter" all became scene names, one play
    # [EN] was chopped to pieces and two criteria went red. So "register a new place" needs a gate.
    _PLACE_STOPWORDS = ('门口', '门外', '门外边', '外面', '对面', '旁边', '身边', '面前',
                        '身后', '屋里', '屋内', '楼上', '楼下', '那边', '这边', '这里',
                        '那里', '原处', '远处', '暗处', '半路', '路上', '身后边')

    def _persist_place(self, name: str) -> bool:
        """把一个新地点**补进 `<项目>/设定集/地点.yaml`**（长期保留）。成功返回 True。

        ★★★ 用户 2026-10-22：「改成长期用」。不写盘的话，下一轮开卷重新装配，
          这个地点又变成不认识 —— 换场被静默拒绝、地图又卡在开头那一张。

        ★ 三条纪律（都在下面落实）：
          ① **只追加、绝不重写**：先 `yaml.safe_load` 一遍，确认它是"块列表"（或空），
             才在末尾追加一段 `- 名称: …`。如果是别的结构（作者手写成字典等），
             **一个字节都不动**，只记日志说明"格式不认识、没敢写"。
             为什么不用 `yaml.safe_dump` 整体重写：那会把作者的注释、引号风格、空行全冲掉。
          ② **写之前留备份**（`地点.yaml.bak-新地点-<时间戳>`）—— 这是动用户的创作文件。
          ③ **失败只记日志**：设定集可能是只读的、可能被编辑器占着，
             写不进去也只是"这一轮临时用"，推演不能因此挂掉。

            English:
        Append a new place to `<project>/设定集/地点.yaml` (permanent). Returns True on success.
        ★★★ The user on 2026-10-22: "make it permanent". Without writing, the next book-opening
          re-assembles and the name is unknown again -- the switch is refused and the map sticks.
        ★ Three rules, all enforced below: ① **append only, never rewrite** -- load the YAML first and
          confirm it is a block sequence (or empty) before appending; on any other structure **not a
          single byte changes**, just a log line saying the format was not understood. Not using
          `yaml.safe_dump` because that would wipe the author's comments, quote style and blank
          lines. ② **back up first** (`地点.yaml.bak-newplace-<ts>`) -- this is the author's creative
          file. ③ **log on failure only**: the settings may be read-only or locked by an editor, and
          then it simply stays in-memory for this round; the run must not die for that.
        """
        try:
            project_dir = getattr(self.runfolder, 'project_dir', None)
            if project_dir is None:
                return False
            path = Path(project_dir) / '设定集' / '地点.yaml'
            if not path.is_file():
                # 文件不存在 = 这本书压根没写地点表。**不替作者建一份**：
                # 建了之后 `_known_places` 会从"空"变成"只有这个名字"，
                # 那是另一种静默改动（而且第一次开卷就会发生）。
                # [EN] No file means the book has no place table at all. **Do not create one**: that
                # [EN] would silently change `_known_places` from "empty" to "only this name".
                _LOG.info('新地点「%s」没写进设定集：这本书还没有「设定集/地点.yaml」', name)
                return False
            raw = path.read_text(encoding='utf-8')
            # ① 认格式：块列表 或 空
            import yaml as _yaml
            try:
                data = _yaml.safe_load(raw)
            except Exception as e:                          # noqa: BLE001
                _LOG.warning('「地点.yaml」解析不了（不敢写，怕破坏你的文件）：%r', e)
                return False
            if data is not None and not isinstance(data, list):
                _LOG.warning('「地点.yaml」不是"- 名称:"那种列表结构（不敢写）；'
                             '新地点「%s」这一轮只在内存里认', name)
                return False
            names = set()
            for it in (data or []):
                if isinstance(it, dict):
                    names.add(str(it.get('名称') or '').strip())
                elif isinstance(it, str):
                    names.add(it.strip())
            if name in names:
                return True                                 # 已经有了（作者自己补过）
            # ② 备份
            import time as _t
            bak = path.with_name(f'{path.name}.bak-新地点-'
                                 f'{_t.strftime("%Y%m%d-%H%M%S")}')
            bak.write_text(raw, encoding='utf-8')
            # ③ 追加（保持作者原有格式，只加一段）
            body = raw if raw.endswith('\n') or not raw else raw + '\n'
            if body and not body.endswith('\n'):
                body += '\n'
            block = (f'- 名称: {name}\n'
                     f'  说明: 本轮剧情里出现的地点（自动登记，可自行改写）\n'
                     f"  方位: ''\n"
                     f'  内里: []\n')
            atomic_write_text(path, body + ('\n' if body.strip() else '') + block)
            _LOG.info('新地点「%s」已补进「设定集/地点.yaml」（备份：%s）', name, bak.name)
            return True
        except Exception as e:                              # noqa: BLE001
            _LOG.warning('新地点「%s」没写进设定集（这一轮临时用）：%r', name, e)
            return False

    def _register_place(self, raw: str) -> str:
        """把一个**设定集里没有、但剧作家/导演写成地点**的名字登记成本轮的新地点。

        返回登记后的名字（没登记返回空串）。

        ★★★ 为什么要做这件事（2026-10-22，用户的第 3 问）
          用户：「小说提到了府城和大柳树 你确认下后续会出现当前城市到府城的地图
          以及大柳树附近的地图吗？」
          查下来：`世界观` 的 `【地点】` 只有「望江楼」一处，而剧作家写的
          「河岸柳树下」「府城」谁都不认识 —— `_stage_place_to` 匹配不上就**静默返回空**，
          于是 `world.scene` 不动、场景记录里三场戏的地点全是「望江楼」，
          地图自然也永远是那一张。**用户的观察是对的，而且不是"还没画到"，
          是"永远不会画到"。**

        ★ 门槛（宁可少登记，也别把场面话当地名）：
          · 去掉 `·` 之后那段（"河岸柳树下·夜" → "河岸柳树下"）；
          · 2~8 个字（再长多半是句子）；
          · 不含 `_PLACE_STOPWORDS`（门外/对面/原处…）；
          · 本轮最多登记 12 个（失控时宁可停，也别把地点表灌满）。

        ★ 登记之后**同一份名单**同时给三处用：换场判定、当天取景白名单、场景地图。
          "三处各认一份名单"就是本项目反复踩的那个坑。

            English:
        Register a name that is **not in the setting** but that the playwright/director wrote as a
        place. Returns the registered name (empty when not registered).
        ★★★ Why (the user's third question, 2026-10-22): the `【地点】` section holds only "Mowen
          Tower", and what the playwright writes ("riverbank under the willow", "the prefecture city")
          is known to nobody -- `_stage_place_to` cannot match it and **silently returns empty**, so
          `world.scene` never moves, all three scenes of the day record "Mowen Tower", and the map
          stays that one map forever. **The user's observation was right, and it is not "not drawn
          yet" but "never will be drawn".**
        ★ The gate (register less rather than treat stage talk as place names): take the segment
          before `·`; 2-8 characters; no stopword (outside the door / the other side / the same
          spot...); at most 12 registrations per round.
        ★ After registering, **one list** feeds three places: scene switching, the day's framing
          whitelist, and the scene map. "Three places each keeping their own list" is the trap this
          project keeps falling into.
        """
        name = str(raw or '').strip()
        if not name:
            return ''
        for sep in ('·', '・', '·', '|'):
            if sep in name:
                name = name.split(sep)[0].strip()
                break
        name = name.strip(' 　.。,，;；:：')
        if not (2 <= len(name) <= 8):
            return ''
        if any(w in name for w in self._PLACE_STOPWORDS):
            return ''
        known = [str(x).strip() for x in
                 (getattr(self.world, 'place_names', None) or []) if str(x).strip()]
        if name in known:
            return name
        if len(getattr(self, '_new_places', None) or []) >= 12:
            self._warn_once('place_cap', '本轮新地点已登记 12 个，后面的不再登记'
                                         '（地点表被场面话灌满比少画一张图更糟）')
            return ''
        try:
            self.world.place_names = known + [name]
        except Exception:                                   # noqa: BLE001
            return ''
        self._new_places = list(getattr(self, '_new_places', None) or []) + [name]
        # ★★★ 2026-10-22（用户：「改成长期用」）：**写进设定集**，而不是只在内存里认它一轮。
        #   为什么必须写盘：只在内存里登记 ⇒ 下一轮开卷从 `地点.yaml` 重新装配，
        #   这个地点又变成"不认识"，换场被静默拒绝、地图又卡在开头那一张 ——
        #   用户看到的还是"地图永远不变"。
        #   `PLACE_PERSIST` 关掉就退回"只在内存里"，那是给"不想让程序动我的设定集"的人留的。
        # [EN] ★★★ 2026-10-22 (user: "make it permanent"): **write it into the settings**, not just
        # [EN] recognise it in memory for one round. Why writing is required: an in-memory only
        # [EN] registration disappears at the next book-opening (which re-assembles from
        # [EN] `地点.yaml`), the scene switch is silently refused again and the map sticks at the
        # [EN] first one -- the user would still see "the map never changes".
        # [EN] With `PLACE_PERSIST` off it falls back to memory-only, for people who do not want the
        # [EN] program touching their settings.
        saved = False
        if CFG.b('PLACE_PERSIST'):
            saved = self._persist_place(name)
        _LOG.info('新地点登记：「%s」（%s）', name,
                  '已补进设定集，长期有效' if saved else '本轮临时登记（没写进设定集）')
        try:
            self._push_narrative(
                (f'〔新地点〕{name} —— 已补进「设定集/地点」长期保留'
                 f'（写之前留了备份；不想要就从那里删掉这一条）')
                if saved else
                (f'〔新地点〕{name} —— 设定集「地点」里没有它，本轮临时登记'
                 f'（打开了「新地点写进设定集」才会长期保留）'),
                0, kind=S.NOTE)
        except Exception:                                   # noqa: BLE001
            pass
        try:
            if self.runfolder is not None:
                f = Path(self.runfolder.root) / '新地点.md'
                old = f.read_text(encoding='utf-8') if f.is_file() else (
                    '# 本轮新登记的地点\n\n> 这些名字是剧作家/导演写进「场」里的，'
                    '设定集「地点」里没有。\n> 想让它们长期可用，把它们补进'
                    '「设定集/地点.yaml」。\n')
                atomic_write_text(f, old.rstrip() + f'\n\n- 第 {int(getattr(self.world, "game_day", 0) or 0)} 天 · '
                                                   f'{name}\n')
        except Exception:                                   # noqa: BLE001
            pass
        return name

    def _save_scene_plate(self, place: str, when: str) -> None:
        """给**刚切过去的那一场**存一张大地图（`<运行文件夹>/场景地图/`）。

        用户 2026-10-22：「场景切换应该是一个明确的动作并引发地图重绘」
        「所有地图（小地图和大地图）都需要按照场景保存下来」。

        ★ 取图顺序（与界面同一套口径）：
          ① 当天地图里有这一处 → 用它（多处取景，更有信息量）；
          ② 没有 → `map_layout.here_only(place)`（只画这一处，并在描述里**说明是简化排布**）。
             **宁可一张小图，也不画一张错的图**（与 2026-10-08 那条纪律一致）。
        ★ 场次按 `(天, 本轮第几场)` 记：同一天两次回到同一处是**两个场景**。

        ⚠ 失败只记日志：存图是旁路，不许把推演弄挂。
            English:
        Save one big map for the scene just entered (`<run>/场景地图/`).
        ★ Layout order (same convention as the UI): ① use the day map if it contains this place
          (multi-place framing carries more information); ② otherwise `here_only(place)` (a single
          place, and the description **says it is a simplified layout**). **Better a small map than a
          wrong one** (consistent with the 2026-10-08 rule).
        ★ The scene index is keyed on `(day, nth scene today)`: returning to the same place twice in
          one day is **two scenes**. ⚠ Log only on failure -- saving is a bypass.
        """
        try:
            entry = _scene_plate_spec(self, place, when)
            if entry is None:
                return
            svg, detail, note, source = entry
            from image_gen import scenemap as SM
            day = int(getattr(self.world, 'game_day', 0) or 0)
            idx = int(getattr(self, '_scene_no', 0) or 0) + 1
            self._scene_no = idx
            path = SM.record(self.runfolder, day=day, index=idx, place=place,
                             when=when, svg=svg, note=note, detail=detail,
                             source=source)
            if path is not None:
                _LOG.info('场景地图：第 %d 天第 %d 场「%s」→ %s', day, idx, place,
                          Path(path).name)
        except Exception as e:                              # noqa: BLE001
            _LOG.warning('场景地图保存失败（不影响推演）：%r', e)

    def _push_scene(self, *, place: str = '', segment: str = '',
                    record: bool = True) -> None:
        """「换地方了」—— 界面拿它重画小地图（2026-10-06）。

        `place` = **新**地点（小地图上那个朱砂点移到哪），
        `segment` = 当前时段（"戌时"），图上的时间感靠它。

        为什么单开一条通道而不是让界面去解析分隔符：分隔符是**给人看的字**，
        界面去正则里抠地点名，早晚会抠错（而且改个文案就崩）。
        这条传的是**数据**。

        `record=False` = **只当重画通知，不当剧情里的"换场景"**。
        用在"当天的图画好了"那一次（见 `_log_day_map`）：那时并没有换地方，
        只是图变了 —— 往审读台账里塞一行假的"换场景"会污染"这一场戏在哪几处"
        那类判断。

        ⚠ 同 `_push_divider`：**只是播报**，回调抛异常绝不影响推演。
        
                English:
        "changed location" -- the UI uses it to redraw the mini-map (2026-10-06).
                `place` = the **new** location (where the cinnabar dot on the mini-map moves to),
                `segment` = the current time period ("xu hour"), the sense of time on the map depends on it.
                Why open a separate channel instead of having the UI parse the separator: the separator is **text for humans to read**;
                if the UI digs the location name out with regex, sooner or later it will get it wrong (and it breaks as soon as you change the copy).
                This channel transmits **data**.
                `record=False` = **treat it only as a redraw notification, not as a plot "scene switch"**.
                Used for the "today's map is drawn" instance (see `_log_day_map`): at that time the location did not actually change,
                only the map changed -- stuffing a fake "scene switch" line into the review ledger would pollute judgments like "which places this scene takes place in".
                that class of judgment.
                ⚠ same as `_push_divider`: **broadcast only**, a callback throwing an exception must never affect the simulation.
        """
        # ★ 记进审读台账（用户点名的"场景切换"；只记不判，见 `_review_record_only`）
        # [EN] ★ Record into the review ledger (the "scene switch" the user named; record only, do not judge,
        # [EN] see `_review_record_only`)
        if record:
            self._review_record_only(
                'scene',
                ' → '.join(x for x in (str(place or ''), str(segment or '')) if x))
            # ★★★ 2026-10-22：**换场就把这一场的大地图存下来**（用户：「场景切换应该是一个
            #   明确的动作并引发地图重绘」「所有地图都需要按照场景保存下来」）。
            #   ⚠ 只挂在 `record=True` 上：`record=False` 那一次是"当天的图画好了"的重画通知，
            #     并没有换场 —— 在那里存图会把同一场记两遍（"场景 1"、"场景 2" 都是望江楼）。
            # [EN] ★★★ 2026-10-22: **a scene change saves that scene's big map** (user: "a scene change
            # [EN] should be an explicit action and trigger a map redraw", "all maps must be saved per
            # [EN] scene"). ⚠ Only on `record=True`: `record=False` is the "today's map is ready" redraw
            # [EN] notice, not a scene change -- saving there would record the same scene twice.
            try:
                self._save_scene_plate(str(place or ''), str(segment or ''))
            except Exception as e:                          # noqa: BLE001
                self._warn_once('scene_plate', f'场景地图保存失败：{e!r}')
        if not self._on_scene:
            return
        try:
            cast: list[str] = []
            try:
                cast = [a.name for a in self.agents
                        if self.world.is_on_stage(a.ps)]
            except Exception:                               # noqa: BLE001
                cast = []
            self._on_scene({
                'place': str(place or ''),
                'segment': str(segment or ''),
                'cast': cast,
                'day': int(getattr(self.world, 'game_day', 0) or 0),
            })
        except Exception as e:                              # noqa: BLE001
            self._warn_once('scene', f"换场景回调失败：{e!r}")

    def _status(self, key: str, **kw) -> None:
        """上报细粒度运行状态。**只是播报**：出错就丢，绝不影响推演。

        `key` 是稳定标识（界面自己翻译成句子），`kw` 只放**数据**
        （正在决策几个人…）—— sim 层不拼给人看的句子。
        
                English:
        Report fine-grained runtime status. **Broadcast only**: drop it on error, never affect the
        simulation.
                `key` is a stable identifier (the UI translates it into a sentence itself), `kw` only holds **data**
                (how many people are being decided... ) -- the sim layer does not assemble human-readable sentences.
        """
        if self._on_status:
            try:
                self._on_status(key, **kw)
            except Exception as e:                          # noqa: BLE001
                self._warn_once('status', f"状态回调失败：{e!r}")

    def _warn_once(self, tag: str, msg: str) -> None:
        """同一种播报故障只记一条日志（每拍都调，不节流会被刷屏）。
                English:
        The same broadcast failure logs only one entry (called every tick; without throttling it would
        flood the screen).
        """
        if tag in self._cb_warned:
            return
        self._cb_warned.add(tag)
        _LOG.warning("%s（后续同类问题不再重复记）", msg)

    def _flush_tick(self, tick_num: int) -> None:
        if tick_num % 10 != 0:
            return
        # 快照（每 10 tick）
        # [EN] Snapshot (every 10 ticks)
        if tick_num % 50 == 0:
            sid = f"snap_{tick_num:06d}"
            self.db.add_snapshot(sid, f"tick {tick_num}", self.world.game_day, "")
            # `SNAPSHOT_KEEP`（以前零读取）：只留最近 N 张。
            # **不删文件、只清登记**——快照文件是用户的回溯素材，
            # 删登记只是让列表不无限长（`SNAPSHOT_KEEP=0` = 不限）。
            # [EN] `SNAPSHOT_KEEP` (previously read nowhere): keep only the most recent N.
            # [EN] **Do not delete files, only clear the registry** — snapshot files are the user's retrospection
            # [EN] material,
            # [EN] deleting the registry only keeps the list from growing unboundedly (`SNAPSHOT_KEEP=0` =
            # [EN] unlimited).
            keep = CFG.i("SNAPSHOT_KEEP")
            if keep > 0:
                try:
                    rows = self.db.snapshots(limit=keep + 50)
                    for row in rows[keep:]:
                        self.db.drop_snapshot(str(row.get("id") or ""))
                except Exception as e:                          # noqa: BLE001
                    self._warn_once('snapshot_keep', f"快照清理失败：{e!r}")
        # 预算检查**不在这里**了（2026-10-11）：以前这里 `pause()` 一下就走，
        # 而主循环自己开的暂停不经过会话层 ⇒ 作者连「继续」都点不到。
        # 现在由 `_maybe_ask_budget()`（`_tick` 里调）**问一句**再决定，
        # 所以这一处彻底留空 —— 留着旧的 `pause` 会和那边打架。
        # [EN] The budget check is **no longer here** (2026-10-11): previously it just `pause()`d once and
        # [EN] left,
        # [EN] but a pause opened by the main loop itself does not go through the session layer => the author
        # [EN] cannot even click "resume".
        # [EN] Now it is handled by `_maybe_ask_budget()` (called in `_tick`), which **asks once** before
        # [EN] deciding,
        # [EN] so this spot is left completely empty — keeping the old `pause` here would fight with that.

    async def _ask_checkpoint(self, every_days: int) -> None:
        """存档点问一句（只在 `CHECKPOINT_PAUSE=true` 时走到）。

        选项设计成**不打断也能用**：默认那条「接着写」就是"把这次存档点
        当已确认"，所以想让它停的人才会打开那个开关。
        
                English:
        The checkpoint asks one question (only reached when `CHECKPOINT_PAUSE=true`).
                The options are designed to be **usable without interrupting**: the default "keep writing" effectively means "treat this checkpoint
                as already confirmed", so only people who want it to stop will turn that switch on.
        """
        day = self.world.game_day
        ans = await self._ask(
            kind='checkpoint',
            title=f'第 {day} 天 · 存档点',
            why=f'按设置每 {every_days} 天在这里停一下（已落盘）—— 接着写吗？',
            options=[
                {'id': 'go', '标题': '接着写', '后果': '什么都不改，直接往下推演'},
                {'id': 'hold', '标题': '停在这儿',
                 '后果': '推演暂停，你可以在「天机」里改参数，回头点「继续」接着跑'},
            ],
            allow_custom=True,
            brief=f'现在是第 {day} 天 · {self.world.clock_display()} · '
                  f'{self.world.scene}',
            data={'day': day, 'every': int(every_days)},
        )
        pick = str((ans or {}).get('id') or '')
        if pick == 'hold':
            self.pause(f"存档点（第 {day} 天）—— 你选了停在这儿")
            self._push_narrative(
                f'（第 {day} 天 · 存档点）按你说的停一下 —— 改完参数点「继续」接着写。',
                0, kind=S.NOTE)
            return
        written = str((ans or {}).get('custom') or '').strip()
        if written:
            # 作者自己写的：交给走向那条路（和岔路口同一个落点，免得两套）
            # [EN] Author-written: hand it to the direction path (same landing point as the fork, to avoid two
            # [EN] implementations)
            self._branch_custom = written
            self._push_narrative(f'（你自己定的）{written}', 0, kind=S.NOTE)
            return
        self._push_narrative(
            f'（第 {day} 天 · 存档点）接着往下写。', 0, kind=S.NOTE)

    async def _maybe_ask_budget(self) -> str | None:
        """token 预算用完了：问作者**接着跑还是收工**。返回结束原因（None = 继续跑）。

        以前是 `pause()` 一声不响地停下（`BUDGET_EXHAUST_POLICY=pause`），
        默认值 `degrade` 下则什么都不做。两者都不好：
          · `pause` 那条**作者点不到「继续」**（主循环自己开的暂停不经过会话层）；
          · `degrade` 那条是"悄悄降级"，作者只会觉得"后面怎么变笨了"。

        现在两档都在同一条路上：
          · `degrade`（默认）—— 不打断、也不问（保持老语义：降级继续跑）；
          · `pause` —— 弹对话框问："预算用完了，接着跑还是收工？"
        
                English:
        Token budget exhausted: ask the author **keep running or call it a day**. Returns the end reason
        (None = keep running).
                Previously `pause()` stopped silently (`BUDGET_EXHAUST_POLICY=pause`),
                and under the default `degrade` it did nothing. Neither is good:
                  · With `pause` the **author cannot click "continue"** (a pause opened by the main loop itself does not go through the session layer);
                  · With `degrade` it is a "silent degradation"; the author just feels "why did it get dumber later".
                Now both tiers are on the same path:
                  · `degrade` (default) -- no interruption, no question (keeps the old semantics: degrade and keep running);
                  · `pause` -- pops a dialog asking: "budget exhausted, keep running or call it a day?"
        """
        try:
            if not llm.budget_exceeded():
                return None
        except Exception:                                        # noqa: BLE001
            return None
        policy = (CFG.s("BUDGET_EXHAUST_POLICY") or "degrade").strip()
        if policy != "pause":
            return None
        # 只在**真的越线的那一刻**问一次（否则每一拍都问，烦死）
        # [EN] Only ask once at **the moment it actually crosses the line** (otherwise it asks every beat,
        # [EN] which is maddening)
        if getattr(self, '_budget_asked_day', None) == self.world.game_day:
            return None
        self._budget_asked_day = self.world.game_day
        used = int(getattr(llm.ledger, 'today_tokens', 0) or 0)
        cap = CFG.i("TOKEN_BUDGET_PER_DAY")
        _LOG.warning("token 预算耗尽（本日已用 %d / 上限 %d），问作者怎么办", used, cap)
        ans = await self._ask(
            kind='budget',
            title='今天的 token 用完了',
            why=f'本日已用 {used:,} / 上限 {cap:,} token —— 接着往下写，还是收工？',
            options=[
                {'id': 'extend', '标题': '接着写（预算翻一倍）',
                 '后果': f'把本日上限抬到 {cap * 2:,}，继续往下推演'},
                {'id': 'stop', '标题': '今天先到这儿',
                 '后果': '停下这一轮，补落今天的稿子、写今日总结，然后按设置导出'},
            ],
            allow_custom=True,
            brief='（也可以自己写一个新上限的**数字**，比如 1500000）',
            data={'used': f'{used:,}', 'cap': f'{cap:,}',
                  'cap2': f'{max(1, cap) * 2:,}'},
        )
        pick = str((ans or {}).get('id') or '')
        written = str((ans or {}).get('custom') or '').strip()
        # 自定义里如果写了数字，就把它当新上限（这是这一题最自然的"自己写"）
        # [EN] If the custom field contains a number, treat it as the new upper limit (this is the most natural
        # [EN] "write it yourself" for this problem)
        new_cap = 0
        for tok in written.replace('，', ',').replace(',', ' ').split():
            digits = ''.join(ch for ch in tok if ch.isdigit())
            if len(digits) >= 3:
                new_cap = int(digits)
                break
        if written and new_cap > 0:
            CFG.set('TOKEN_BUDGET_PER_DAY', str(new_cap))
            self._push_narrative(f'（预算）本日上限改成 {new_cap:,} —— 接着写。',
                                 0, kind=S.NOTE)
            return None
        if pick == 'extend':
            CFG.set('TOKEN_BUDGET_PER_DAY', str(max(1, cap) * 2))
            self._push_narrative(f'（预算）上限翻倍到 {max(1, cap) * 2:,} —— 接着写。',
                                 0, kind=S.NOTE)
            return None
        if pick == 'stop':
            self._push_narrative('（预算）按你说的收工 —— 先补落今天，再写总结。',
                                 0, kind=S.NOTE)
            return f"token 预算用尽（作者选择收工）"
        # 到点 / 无界面 / 作者写了别的：**照老语义降级继续跑**，
        # 不偷偷停 —— 停的判断必须来自人，不能来自一次超时。
        # [EN] On timeout / no GUI / author wrote something else: **degrade and keep running per the old
        # [EN] semantics**,
        # [EN] do not silently stop — a stop decision must come from a human, not from a timeout.
        _LOG.info("预算耗尽这题没人回答，按降级继续跑（不擅自停止）")
        self._push_narrative('（预算）本日预算已用完 —— 继续推演，'
                             '后面的调用会按降级策略走。', 0, kind=S.NOTE)
        return None

    # ── 结束处理 ──────────────────────────────────────────────────────
    # [EN] ── End handling ──────────────────────────────────────────────────────
    async def get_display_queue(self):
        """获取显示队列所有条目。
                English:
        Get all entries in the display queue.
        """
        return await self.display.dequeue_all()

    async def clear_display_queue(self) -> None:
        """清空显示队列。
                English:
        Clear the display queue.
        """
        await self.display.catchup()

def _match_visref_scene(refs: list, place: str) -> str | None:
    """从视觉参考清单里挑出「当前这场」的参考图路径（种类=场景）。

    匹配放宽：名相等 / 互相包含都算，避免"场名写法略有出入"就对不上。
        English:
    Pick the current scene's reference image path (kind=scene) from the refs list.
    """
    if not place:
        return None
    _place = str(place).strip()
    for r in refs or []:
        if not isinstance(r, dict):
            continue
        if r.get('种类') != '场景':
            continue
        img = r.get('图') or ''
        if not img:
            continue
        name = str(r.get('名') or '').strip()
        if not name:
            continue
        if name == _place or name in _place or _place in name:
            return str(img)
    return None

def _verb_desc(act: Action) -> str:
    """动作的一句话描述（**不含台词**）。

    ⚠ `speak` 这一档刻意**不复述台词**（2026-10-07）：以前它是
    `对阿枝说：今夜别出门。`，于是同一句话会被"旁白讲一遍 + 角色自己
    再说一遍"（用户报的毛病）。台词由台词那条路走，这里只说"他开口了"。

    ★★ 2026-10-14（用户）：「正常小说…应该有…人物做的事情」——
    **模型给了描写就用描写**（`Action.detail`），没给才落回下面的骨架表。
    ⚠ 这是**第二处**需要 `detail` 的地方（第一处是
      `SceneBuilder._action_text`，走剧本模式那条路；`_verb_desc` 走 prose 模式）。
      两处都改，否则"换了运行模式，描写就没了"。
    ⚠ 骨架表本身**保留**：它是"模型没给细节"时的兜底，
      保证结构完整、不出现空槽（那正是它存在的理由）。

        English:
    One-line description of the action (**excluding dialogue**).
        ⚠ The `speak` tier deliberately **does not repeat the dialogue** (2026-10-07): it used to be
        `say to Azhi: don't go out tonight.`, so the same line was told once by the narration and
        then said again by the character himself (the bug the user reported). Dialogue goes through
        the dialogue path; here we only say "he spoke".

    ★★ 2026-10-14 (user): "a normal novel should have ... things the characters do" --
    **if the model gave a description, use it** (`Action.detail`); only when it did not, fall back to
    the skeleton table below.
    ⚠ This is the **second** place that needs `detail` (the first is
      `SceneBuilder._action_text`, on the script-mode path; `_verb_desc` is the prose-mode path).
      Both must change, otherwise "switch the run mode and the description disappears".
    ⚠ The skeleton table itself is **kept**: it is the fallback when the model gave no detail,
      guaranteeing structural completeness with no empty slots (which is exactly why it exists).
    """
    detail = str(getattr(act, 'detail', '') or '').strip()
    if detail:
        # ★★★ 2026-10-28：**剥掉开头的"我"** —— 上一行拼的是 `f"{agent.name}{detail}"`，
        #   演员写"我把壶搁在柜面上"，正文就成了「张三我把壶搁在柜面上」。
        #   三个演员各写各的"我" ⇒ 一篇里三个第一人称（这本书是第一人称，
        #   读者会读成李四一个人做了三件事）。见 `util.text.bare_detail`。
        # [EN] ★★★ 2026-10-28: **strip the leading 我** -- the caller prefixes `f"{agent.name}{detail}"`,
        # [EN] so an actor writing "我把壶搁在柜面上" yields "张三我把壶搁在柜面上". Three actors each
        # [EN] writing 我 means three first persons on one page. See `util.text.bare_detail`.
        return bare_detail(detail)
    descs = {"move": f"去了{act.target}", "speak": (
        f"开口，叫住{act.target}" if act.target else "开口"),
        "interact": f"和{act.target}互动", "emote": "有了情绪变化",
        "wait": "等了等", "think": f"想：{act.inner_thought[:30]}"}
    return descs.get(act.verb, act.verb)


# ══════════════════════════════════════════════════════════════════════
#  场景地图：把"这一场在哪"算成一张 SVG（产品与判据共用同一份）
# [EN] Scene map: turn "where this scene is" into an SVG (shared by the product and the criteria)
# ══════════════════════════════════════════════════════════════════════
#: 场景地图的尺寸：与大地图对话框同一个画布（同一份几何 ⇒ 同一张图，只是被写进文件）。
# [EN] Scene-map size: the same canvas as the big-map dialog (one geometry => one image, just written
# [EN] to a file).
PLATE_W, PLATE_H = 940, 600


def _scene_plate_spec(loop, place: str, when: str):
    """算出一张场景图：`(svg, 细致程度, 一句话描述, 取图来源)`；算不出返回 `None`。

    ★ 取图顺序与小地图/大地图**同一套口径**（`day_map` 优先，退 `here_only`）——
      三处一旦不一致，就会出现"屏幕上在柳树、导出里是望江楼"，
      而那种错**不报错**，只是让人以为软件坏了。
    ★ 一句话描述**照实写取图来源**：简化排布就写"简化排布"，
      不许让读者以为那是一张量过的实测图。
    [EN] Compute one scene image: `(svg, detail, one-line description, source)`; None when it cannot
    [EN] be computed. ★ The layout order is the **same convention** as the minimap/big map (`day_map`
    [EN] first, `here_only` fallback) -- inconsistency produces "the willow on screen, Mowen Tower in
    [EN] the export", an error that **reports nothing** and just looks broken.
    [EN] ★ The one-line description **states the source truthfully**: a simplified layout says so; the
    [EN] reader must not think it is a surveyed map.
    """
    name = str(place or '').strip()
    if not name:
        return None
    try:
        from image_gen import floorplan as FP
        from image_gen import map_layout as ML
        from image_gen import minimap as MM
        from image_gen import scenemap as SM
    except Exception:                                       # noqa: BLE001
        return None
    lay = getattr(loop, 'day_map', None)
    source = '当天地图取景'
    has_it = any(str(getattr(p, 'name', '') or '') == name
                 for p in (getattr(lay, 'places', None) or []))
    if not has_it:
        lay = ML.here_only(name)
        source = '只画这一处（简化排布）'
    if lay is None:
        return None
    detail = MM.detail_of(lay)
    desc = str(getattr(getattr(loop, 'world', None), 'scene_desc', '') or '').strip()
    try:
        shapes = FP.build_detail_shapes(
            lay, width=PLATE_W, height=PLATE_H, current=name, detail=detail,
            place=name, when=when)
        svg = SM.svg_of(shapes, PLATE_W, PLATE_H,
                        background=str(FP.PALETTE.get('paper', '#ffffff')))
    except Exception:                                       # noqa: BLE001
        return None
    # 描述里**只放这一场"看见什么"**（时辰 / 地点在清单里另有字段，导出时自己拼）——
    # 两处都写一遍，读者会以为那句话是场景描写的一部分。
    # [EN] The description carries **only what this scene looks like** (time and place have their own
    # [EN] manifest fields and are composed at export time) -- duplicating them makes the reader think
    # [EN] the sentence is part of the scene description.
    note = desc[:60] or f'{name}这一场'
    return svg, detail, note, source
