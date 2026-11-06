# -*- coding: utf-8 -*-
"""小世界状态（设计稿 §四）：动态层，运行时更新。

总世界观（静态层）是冻结的设定集，system prompt 前缀。
小世界 = 故事时间 + 天气 + 场景 + 在场人物 + 张力值 + 当前故事节点。

English:
Small-world state (design doc §4): dynamic layer, updated at runtime.
The overall worldview (static layer) is the frozen setting set, the system prompt prefix.
Small world = story time + weather + scene + present characters + tension value + current story
node.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from util.timefmt import GameTime, format_game_clock


#: 判"泄露"的最短公共片段（字）。★ 5 是量出来的：
#:   3 字会把 `三百年` 这种**两份秘密里都有**的片段当成泄露（实测误判成另一个人）；
#:   7 字又太严（"器灵守楼三百年" 一句话只泄露一半就漏了）。
#: ⚠ 这是**召回**门槛（宁可漏不可误报）—— 真泄露但措辞改了很多的，交给审读。
# [EN] Shortest shared run (characters) that counts as a leak. ★ 5 is measured: 3 lets `三百年`
# [EN] -- present in two different secrets -- count as a leak (measured: misattributed to the wrong
# [EN] person); 7 is too strict. ⚠ This is a **recall** threshold (prefer misses over false
# [EN] positives); real leaks worded very differently are left to the script review.
_LEAK_MIN = 5


def _shared_run(a: str, b: str) -> int:
    """两段文字里**最长的公共连续片段**有多长（字）。

    为什么要它而不是集合交集：秘密是自然语言，**同样的词在不同秘密里重复出现**
    （"三百年"同时出现在两条秘密里）—— 按"有没有共同片段"判会张冠李戴。
    [EN] The length of the **longest common contiguous run**. Why not set intersection: secrets are
    [EN] natural language and the same word recurs across them ("three hundred years" appears in
    [EN] two), so "any shared fragment" misattributes the leak.
    """
    if not a or not b:
        return 0
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


@dataclass
class PersonState:
    """单个人物的运行时状态。
        English:
    Runtime state of a single character.
    """
    name: str
    identity: str = ""
    personality: str = ""
    catchphrase: str = ""
    #: **说话指纹** —— 这个人一开口就躲不掉的四件事：句子多长、嘴上的抓手、
    #: 心虚时手上干什么、对不同的人怎么称呼。
    #: ★★★ 2026-10-28 新增（作者点名，来源：一篇被编辑圈了三段对话的退稿复盘）：
    #:   编辑的原话是「你这两个人说话，像在互相念说明书」。他的判法极简单 ——
    #:   **把人名遮住，如果所有人都一个味，那就是机器写的**。
    #:   而"一个味"的根因不在句子上（每句都通顺），在**没有给人物定说话的方式**：
    #:   七十岁的老头和二十岁的徒弟，说话一样客气、一样完整、一样有礼貌。
    #:   ⇒ 动笔前先定"说话指纹"，从源头避免所有角色一个腔调。
    #: ⚠ 写法要**可执行**（这是硬要求）：写"句子不超过十个字""心虚就摸烟袋"
    #:   "叫她'阿六'、叫他'你'"；**不要**写"说话冷淡""语气温和"这种形容词 ——
    #:   形容词没法照着做，模型只会把它翻译回"客气、完整、有礼貌"。
    #: ⚠ 与 `catchphrase` 的分工：口癖是**一句话**（「喝茶。」），指纹是**怎么说话**
    #:   （长短、节奏、躲闪方式、称呼差）。两个都写不重复：口癖是能听见的那一下，
    #:   指纹是听不见但一直在的那层。
    # [EN] **Speech fingerprint** -- the four things this person cannot escape once he opens his
    # [EN] mouth: how long his sentences run, his verbal handhold, what his hands do when he is
    # [EN] lying, and how he addresses different people.
    # [EN] ★★★ Added 2026-10-28 (author's call; source: a rejected-manuscript post-mortem where the
    # [EN] editor circled three passages of dialogue). The editor's test was crude: **cover the names;
    # [EN] if everyone sounds the same, a machine wrote it.** The cause is not the sentences (each one
    # [EN] is grammatical) but that nobody decided **how** the character speaks.
    # [EN] ⚠ Write it **executably** ("sentences under ten characters", "touches the pipe when lying",
    # [EN] "calls her Xiao Liuzi, calls Chen Wang 'you'"), never as adjectives like "cold tone".
    # [EN] ⚠ Division of labour with `catchphrase`: the tic is **one line**; the fingerprint is **how
    # [EN] he talks** (length, rhythm, evasion, forms of address).
    speech_fp: str = ""
    secret: str = ""
    #: **这条秘密，圈里谁知道**（空 = 只有他自己知道）。
    #: ★★★ 2026-10-18 新增（专业论述：#8 信息差 / 戏剧反讽，希区柯克"桌下炸弹"）。
    #:   在此之前 `secret` **只出现在这个人自己的人格卡里** ⇒ 别人在提示词里看不到它，
    #:   于是"秘密"只影响"他自己怎么说"，**完全不影响别人怎么对他** ——
    #:   而好戏恰恰在"两人各知一半"。修之前的三处实测毛病：
    #:     ① 秘密形同公开（别人也不会绕着它说话，但也不会被它牵动）；
    #:     ② 冲突只能靠性格不同，写出来就是各说各话；
    #:     ③ 审读判"越界"时手上没有"他不该知道"这张表。
    #: ⚠ 写法：设定里写 `知情者: 甲、乙`（同一条秘密知道的人）。**不写 = 只有他自己**。
    #: ⚠ 它**不是**"谁知道内容"的白名单，而是"内容被允许知道的人"——
    #:   不在名单里的人，写出来就是越界（见 `crew/review` 的 `leak` 规则）。
    # [EN] **Who in the circle knows this secret** (empty = only he knows).
    # [EN] ★★★ Added 2026-10-18 (professional reference: #8 information asymmetry / dramatic irony,
    # [EN] Hitchcock's bomb under the table). Before this, `secret` appeared **only in that person's
    # [EN] own persona card**, so a secret influenced only "how he speaks", **never how others treat
    # [EN] him** -- and good drama lives in "each knows half". Three measured defects before the fix:
    # [EN] ① secrets were effectively public (nobody was moved by them); ② conflict could only come
    # [EN] from differing personalities, which reads as everyone-talking-to-themselves; ③ the review
    # [EN] had no table of "he must not know this" when judging out-of-bounds.
    # [EN] ⚠ Spelling: in the settings write `知情者: A、B`. **Omitted = only he knows.**
    # [EN] ⚠ It is a whitelist of "who may know", not "who has been told": anyone outside it who
    # [EN] states the content is out of bounds (see the `leak` rule in `crew/review`).
    knows: list[str] = field(default_factory=list)
    goal: str = ""
    #: **他真正缺的东西**（不是他嘴上要的）——「欲望 vs 需求」（Truby《故事写作大师班》）。
    #: ★★★ 2026-10-18 新增。在此之前只有 `goal`（欲望），于是人物从头到尾
    #:   "想要同一件东西"，弧光只能靠剧情硬推 —— 检查表把这一条列为缺口 #4。
    #:   两者的差别是**弧光唯一的地基**：他每拿到一点 `goal`，就要在 `need` 上付一次代价。
    #: ⚠ 写法：设定里写 `需求: 想被人当成一个人看`。**不写 = 这一维不参与**（不编）。
    #: ⚠ 它 **绝不进别人的人物卡**，只进他自己的提示词，而且**明写"不许说出口"** ——
    #:   说破了就是作者替人物做总结（这条在 `agent/core` 与审读两处都拦）。
    # [EN] **What he actually lacks** (not what he says he wants) -- "want vs need" (Truby).
    # [EN] ★★★ Added 2026-10-18. Before this there was only `goal` (want), so a character wanted
    # [EN] the same thing from beginning to end and the arc could only be pushed by plot -- checklist
    # [EN] gap #4. The distance between the two is the **only foundation of an arc**: every step
    # [EN] toward `goal` costs him something on `need`.
    # [EN] ⚠ Spelling: `需求: wants to be treated as a person`. **Omitted = this dimension is not in
    # [EN] play** (never invented). ⚠ It **never enters anyone else's card**, only his own prompt,
    # [EN] and it is **explicitly marked "must not be spoken aloud"** -- saying it is the author
    # [EN] summarising on the character's behalf (blocked in `agent/core` and in the script review).
    need: str = ""
    redline: str = ""

    # ★★ **选角**（2026-10-07，见 `actors/`）——
    #    演员提示词分两层：**预设**（这一类演员怎么演，随人不随书）＋
    #    **定制**（在这个本子里演谁，随书不随人），冲突时以定制为准。
    #    这四个字段是预设层与它的分流；定制层的料仍走上面那几个字段。
    #: 演员类型键（如 `青年·高冷`）—— 开卷时按人物卡配出来的
    # [EN] ★★ **Casting** (2026-10-07, see `actors/`) --
    # [EN] Actor prompts are split into two layers: **preset** (how this type of actor performs, follows
    # [EN] the person not the book) +
    # [EN] **custom** (who they play in this book, follows the book not the person); on conflict, custom
    # [EN] wins.
    # [EN] These four fields are the preset layer and its routing; the custom layer's material still goes
    # [EN] through the fields above.
    # [EN] : actor type key (e.g. `青年·高冷`) -- cast from the character card at book open
    archetype: str = ""
    #: 同一类型有多个演员时的**变奏轴**（"你这一份是哪一种冷"）
    # [EN] : when one type has multiple actors, the **variation axis** ("which kind of cold is this one of
    # [EN] yours")
    variant: str = ""
    #: 定制层的一句"这一份怎么演"（人物卡写了才有；**没写就不编**）
    # [EN] : a one-liner in the custom layer for "how this one performs" (only if the character card wrote
    # [EN] it; **if not written, don't make it up**)
    casting_note: str = ""
    #: 显式**打破类型**的那一处（两层冲突时唯一能压过定制的例外）
    # [EN] : the one place that explicitly **breaks the type** (the only exception that can override custom
    # [EN] on a two-layer conflict)
    break_type: str = ""
    #: 类型是**配出来的**还是**兜底的** —— 落盘要照实说，不许把兜的说成配的
    # [EN] : whether the type was **cast** or **fell back** -- when persisted, state it truthfully; don't
    # [EN] pass a fallback off as a cast
    cast_matched: bool = True

    # 运行时
    # [EN] Runtime
    emotion: dict[str, float] = field(default_factory=lambda: {
        "happiness": 0.5, "anger": 0.0, "fear": 0.0, "sadness": 0.0, "surprise": 0.0})
    stamina: float = 1.0
    location: str = ""
    status: str = "在场"     # 在场 / 离场 / 死亡
    role: str = "前台"       # 前台 / 后台
    # [EN] present / offstage / dead
    # [EN] foreground / background
    current_goal: str = ""
    catchphrase_count: int = 0  # 统计口癖出现次数
    # ★ 今日计划（2026-10-06）：跨天时由 `Agent.make_plan()` 算一次写进来，
    #   决策 prompt 里带上 —— 人物有"今天打算干什么"，行动才有内在动力。
    #   ⚠ **两种形态**：导演派过活的人是**字符串**（`sim/loop._compose_day` 里
    #     `'；'.join(tasks)`），自己排计划的人是**列表**（`Agent.make_plan`）。
    #     读它的人必须两种都认（`Agent._plan_line` 逐字拆字符串的 bug 就出在这）。
    # [EN] count tic occurrences
    # [EN] ★ Today's plan (2026-10-06): computed once across days by `Agent.make_plan()` and written in,
    # [EN] included in the decision prompt -- characters having "what they plan to do today" gives actions
    # [EN] inner drive.
    # [EN] ⚠ **Two forms**: a person the director assigned work to is a **string** (in
    # [EN] `sim/loop._compose_day`,
    # [EN] `'；'.join(tasks)`), a person who schedules their own plan is a **list** (`Agent.make_plan`).
    # [EN] Readers must accept both (`Agent._plan_line` splitting the string character-by-character is
    # [EN] exactly this bug).
    day_plan: list[str] | str = field(default_factory=list)

    # ★ 登场与派活（2026-10-06 治「空转」）——
    #   · `debut_day`：第几个故事日登场。装配时若 >1，`status` 直接置「未登场」。
    #     真机日志里「连终局才登场的柳娘都 126 次在场」，根因就是**没有登场概念**：
    #     场景没有边界，谁也不必对"此刻谁在这儿"负责（秘密形同公开）。
    #     作者在人物卡里写「登场：第3天 / K09 / 未登场」即可，不写默认第 1 天。
    #   · `met`：露过面没有（开场介绍、续跑时的"前情"要用）。
    #   · `mission`：导演派给他的任务。**派"要什么"，从不派"怎么做"**。
    # [EN] ★ Debut and assigning work (2026-10-06, fixes "spinning in place") --
    # [EN] · `debut_day`: which story day they debut on. At assembly time, if >1, `status` is set directly
    # [EN] to "未登场".
    # [EN] In real-machine logs, "even Liu Niang, who only debuts at the finale, is present 126 times" --
    # [EN] the root cause is **having no concept of debut**:
    # [EN] scenes have no boundaries, so nobody is responsible for "who is here right now" (secrets are
    # [EN] effectively public).
    # [EN] The author writes "debut: day 3 / K09 / 未登场" in the character card; if unwritten, defaults to
    # [EN] day 1.
    # [EN] · `met`: whether they've appeared (used for the opening intro and the "previously" on resume).
    # [EN] · `mission`: the task the director assigned them. **Assign "what is wanted", never "how to do
    # [EN] it"**.
    debut_day: int = 1
    met: bool = False
    mission: str = ""

    # ★ 派活卡死的**可数证据**（2026-10-19 第十二轮）——
    #   `mission` 派了却没办成时，`sim/loop._mission_still_running` 每一轮都答"还在办"，
    #   于是老逻辑把这个人**永久**锁在同一件没办成的事上（snow_v11 实录：同一个人
    #   被连拦两轮，第三轮起再无新目标，正文条目跟着少三分之一）。
    #   根治办法是数"被连续拦了几轮"：只在被拦时 +1，派到新活就归零。
    #   ⚠ 必须配 `DISPATCH_STUCK_ROUNDS`（<=0 = 关闸）才有意义；
    #      关闸时这个字段照样记账，打开闸当天就能用。
    #   ⚠ 与 `mission` **同生同灭**：`mission` 换了它就归零，没有别的地方写它。
    # [EN] ★ The **countable evidence** of a dead-stuck assignment -- the consecutive number of
    # [EN] rounds this person was blocked by "still working on it". When an assignment is given
    # [EN] but never finished, `_mission_still_running` answers True every round, so the old
    # [EN] logic locked the person onto that one unfinished thing **forever**. +1 only when
    # [EN] blocked, zeroed whenever a new assignment lands. ⚠ Lives and dies with `mission`.
    mission_stuck: int = 0

    def is_active(self) -> bool:
        return self.status == "在场" and self.role == "前台"


@dataclass
class WorldState:
    """小世界完整状态快照（§四）。
        English:
    Complete state snapshot of the small world (§4).
    """
    # 时间
    # [EN] Time
    clock: GameTime = field(default_factory=GameTime)
    calendar: str = "auto"
    weather: str = "晴"

    # 场景
    # [EN] Scene
    scene: str = "默认场景"
    scene_desc: str = ""

    # 人物
    # [EN] Characters
    people: dict[str, PersonState] = field(default_factory=dict)
    background_people: list[str] = field(default_factory=list)

    # ★★ **导演盯戏的提示**（2026-10-07）：导演查出"好几个人各自独立重复
    #   同一件事"时，把结论放这儿；**下一拍**的决策提示词会带 `[导演提示]`，
    #   然后由 `agent/core.py` 消费掉（读完即清，是一次性的）。
    #   为什么用世界上的一个字段而不是直接改提示词：决策提示词是在
    #   `Agent.decide` 里现拼的，而盯戏发生在 `_tick` 的末尾 ——
    #   中间隔着"下一拍才决策"这件事，需要一个**跨拍传递**的地方。
    # [EN] ★★ **Director's watch-the-scene hints** (2026-10-07): when the director detects "several people
    # [EN] each independently repeating
    # [EN] the same thing", put the conclusion here; **next beat**'s decision prompt will carry `[导演提示]`,
    # [EN] then `agent/core.py` consumes it (cleared upon read, one-shot).
    # [EN] Why use a world field instead of directly editing the prompt: the decision prompt is assembled
    # [EN] on the fly in `Agent.decide`, while the watching happens at the end of `_tick` --
    # [EN] in between lies "only decide on the next beat", requiring a place for **cross-beat transfer**.
    watch_note: str = ""

    # ★★★ 这一段在谈什么 / 谁还欠一句（2026-10-18）
    #   用户原话：「好几次人物说的话互相不对应 就是一个人说的话 另外一个人不去接…
    #   在很短的一段时间内 出场人物应该是按照**一个主题**展开对话的 而不是每个人
    #   自己一个主题 中间应该有协调者 特别是导演 应该消除这种自说自话的问题」。
    #
    #   ⚠ 这两个值**不是模型概括的**，是 `director.supervisor.talk_audit()`
    #     **算出来**的（从最近几条台词里找"最近一组真问答"与"谁被点名没回"）。
    #     概括要调模型（贵、会歪）；引文是事实（免费、准确）。
    #   ⚠ `topic` 是**原样引文**，不是"这一段在讨论 X"这种总结 —— 见上面那条理由。
    #   ⚠ 换场时**不清空**：上一场没谈完的那句正是下一场要接的东西
    #     （用户要的"场景之间的主题延续"）。只在收工时清。
    # [EN] ★★★ What this stretch is about / who still owes an answer (2026-10-18).
    # [EN] User: "characters' lines don't answer each other... within a short stretch the cast
    # [EN] should unfold **one topic**, not one topic each; there should be a coordinator,
    # [EN] especially the director, to remove the each-talking-to-himself problem".
    # [EN] ⚠ These two are **computed** by `director.supervisor.talk_audit()`, not summarised by a
    # [EN] model (a summary costs money and can be wrong; a quotation is a fact, free and accurate).
    # [EN] ⚠ `topic` is a **verbatim quote**, not a summary.
    # [EN] ⚠ It is **not cleared on a scene change**: the unfinished line of the previous scene is
    # [EN] exactly what the next scene should pick up (the continuity the user asked for). Only
    # [EN] cleared at wrap-up.
    topic: str = ""
    #: 被点名、还没回的那个人（下一拍**必须**让他先开口）
    # [EN] The person who was addressed and has not replied (he **must** speak first next beat).
    topic_open_with: str = ""
    #: 连续几句没人接（`talk_audit` 量的；≥3 才算"各说各话"）
    # [EN] How many consecutive lines nobody picked up (measured; >= 3 counts as talk-drift).
    topic_run: int = 0

    # ★★★ **状态指纹 / 连续几拍没变**（2026-10-20，`director/stall.py`）。
    #   为什么要有：`topic_run` 量的是**对话层**（有没有人接话），而"剧情卡住"
    #   可以发生在话都接得很顺的时候 —— 望江楼那篇就是这样：一问一答都对得上，
    #   但问的是同一件事、答的也是同一件事，连着四场戏没有一件新事实。
    #   所以在**世界状态**这一层再量一次：空间 / 在场人 / 每人手上那件事 / 这一段谈什么。
    #   四样全同 ⇒ 下一拍必然重复上一拍，与措辞无关。
    # ⚠ 这两个字段是**观察器**，不参与决策以外的任何计算；读不到就当没动过。
    # [EN] **State fingerprint / beats without any change** (`director/stall.py`). `topic_run`
    # [EN] measures the dialogue layer, while a story can stall with every line properly
    # [EN] answered -- measured: four scenes of asking the same thing and answering the same
    # [EN] thing. So measure at the world-state layer instead: scene / cast / mission / topic.
    beat_fingerprint: str = ""
    stall_beats: int = 0

    # ★★★ **这一拍的时机与品级**（2026-10-18）—— 提示词动态拼接的两个开关。
    #
    #   用户：「很多Agent的提示词请动态拼接 而不是固定的 根据需要由特定Agent负责品级」。
    #
    #   · `beat_moment`：这一拍处在故事的哪个位置（开场/日常/冲突/转折/收束/查稿/成稿）。
    #     `sim/loop` 每拍算一次写进来；`craft/dispatch.pick` 按它挑"该读哪几条手艺" ——
    #     开场那一拍读「三幕结构 / 黄金三章」，收束那一拍读「起承转合 / 章回钩子」。
    #     ⚠ 改造之前这件事**根本不存在**：每个职位每一拍读到的都是同一批前几条。
    #   · `craft_level`：品级（重/中/轻），由**导演**判（`director.supervisor.grade_beat`）。
    #     它决定这一拍**读几条**：重/中读满，轻只读一半（日常戏塞十条规矩会写匠气）。
    #   · `craft_read`：最近几拍已经读过的条目（调度器用它把新条目排前面，读过的不硬删）。
    #     ⚠ 有上限（`_CRAFT_READ_MAX`）：无上限会一路涨，存档变大且判据读不动。
    #
    #   ⚠ 三个都是**纯状态**，不参与剧情判定；缺省值（`日常`/`中`/空）与改造前行为一致。
    # [EN] ★★★ **This beat's moment and grade** (2026-10-18) -- the two switches for dynamic
    # [EN] prompt assembly. `beat_moment`: where this beat sits (computed by `sim/loop` each beat);
    # [EN] `craft/dispatch.pick` uses it to choose craft. `craft_level`: grade (heavy/medium/light)
    # [EN] judged by the **director** (`director.supervisor.grade_beat`); it decides **how many**
    # [EN] entries this beat reads. `craft_read`: recently-read entries (the dispatcher ranks fresh
    # [EN] ones first, never hard-deletes). ⚠ All three are pure state, not plot decisions; the
    # [EN] defaults (日常/中/empty) behave exactly as before the change.
    beat_moment: str = "日常"
    craft_level: str = "中"
    craft_read: list[str] = field(default_factory=list)
    #: **这是第几拍**（`sim/loop` 每拍写）。调度器用它做环形轮换 ——
    #: 没有它，每拍挑到的永远是同一批（2026-10-18 晚实测：`getattr(w,'beat_tick',0)`
    #: 读的是一个**根本不存在的字段** ⇒ 恒 0 ⇒ 轮换在生产路径上从没生效过，
    #: 而直接调 `pick(tick=...)` 的判据是绿的）。
    #: ⚠ "从世界上读"这件事要配一条**走生产路径**的判据（`C7`），
    #:   否则又会变成"字段有、没人写、没人读"。
    # [EN] **Which beat this is** (written by `sim/loop` each beat). The dispatcher uses it for ring
    # [EN] rotation -- without it every beat picks the same batch (measured 2026-10-18 evening:
    # [EN] `getattr(w, 'beat_tick', 0)` read a field that **did not exist** => constant 0 => rotation
    # [EN] never worked on the production path, while the criterion calling `pick(tick=...)` directly
    # [EN] was green). ⚠ Reading "off the world" needs a criterion that goes **through the production
    # [EN] path** (`C7`), otherwise it becomes "field exists, nobody writes it, nobody reads it".
    beat_tick: int = 0

    #: **这一拍的心理距离**（`贴近` / `中间` / `拉远`）—— 专业论述 #10，Cohn《透明的心灵》。
    #: 由导演每拍定（`director.supervisor.distance_for`），`agent/core` 据此换写法：
    #: 贴近=他的原话短句、中间=他的判断词不加引号、拉远=只写别人看得见的。
    #: ⚠ 它**只换写法，不换事实**（说什么、做什么一概不变）。
    #: ⚠ 空串 = 不定档（老存档）⇒ 提示词里一个字都不挂，行为退回改造前。
    # [EN] **This beat's psychological distance** (close / middle / far) -- #10, Cohn. Set by the
    # [EN] director each beat; `agent/core` swaps the writing accordingly. ⚠ Changes only the writing,
    # [EN] never the facts. ⚠ Empty = ungraded (old saves) => nothing is added to the prompt.
    narrative_distance: str = ""

    #: **刚才那一场最后一条看得见的东西**（台词或动作的原样，`clear_lines` 清场前记下）。
    #: 为什么单独存一条：`_note_aftermath` 在换场**之后**才跑，那时 `recent_lines`
    #: 已经空了 —— 于是"反应"永远取不到（2026-10-18 实测：余波里只剩"困境"）。
    #: ⚠ 只留最后一条、只在这里写；"拼成 sequel 三拍"仍是 `sim/loop._note_aftermath` 的事
    #:   （各管一件事，不合并）。
    # [EN] **The last visible thing of the previous scene** (verbatim line or action, recorded by
    # [EN] `clear_lines` before clearing). Why stored separately: `_note_aftermath` runs **after** the
    # [EN] scene change, when `recent_lines` is already empty -- so the "reaction" was never available
    # [EN] (measured 2026-10-18: only the "dilemma" survived). ⚠ One line only, written only here;
    # [EN] assembling the sequel beats stays in `sim/loop._note_aftermath` (one job each).
    last_beat_text: str = ""

    # ★★★ **上一场留下的余波**（2026-10-18，专业论述 #7 Swain: scene → sequel）——
    #   `{'反应': …, '困境': …, '决定': …}`，三样对应 sequel 的三拍。
    #   为什么需要它：本项目此前只有"每一拍要有一处变化"，而**变化之后人物的态度
    #   怎么变、下一步为什么改主意**没有任何位置承载 —— 评委反复说的
    #   "戏没有落点 / 停住"就是这个。
    #   ⚠ 只在**换场/换天**时由 `sim/loop._end_scene` 填，`[上一场没说完的]` 与
    #     `[这一段在谈的]` 一起递给下一场的演员；收工时由 `reset_topic()` 清。
    #   ⚠ **不填也是常态**：没有余波就不挂这一段（不要为了凑字段编一句）。
    # [EN] ★★★ **The aftermath the last scene left** (2026-10-18, #7 Swain: scene -> sequel) --
    # [EN] `{'反应': ..., '困境': ..., '决定': ...}`, the three beats of a sequel. Why needed: the
    # [EN] project only had "each beat needs one change", with no place for **how the character's
    # [EN] attitude changed and why he changes his mind next** -- exactly the "no landing point"
    # [EN] the judge kept reporting. ⚠ Filled only on scene/day change; an empty dict is normal --
    # [EN] never invent one just to fill the field.
    aftermath: dict = field(default_factory=dict)

    # ★ 群演（临演池，2026-10-06）：`{'姓名','身份','一行','诉求','标志','寿命','剩余'}`
    #   背景群演只进"一行"（不跑模型）· 功能群演带一个诉求（cheap 档）。
    #   由 `world/crowd.py` 生成与回收。**群演不是装饰，是"外部输入"** ——
    #   真机日志里「买 0、顾客 0、客人 20」：茶楼没客人，人物只能内循环
    #   （627 次"看"、565 次"擦"）。有生意，才有日常事件。
    # [EN] Background extras only enter "one line" (no model run) · functional extras carry one want (cheap
    # [EN] tier).
    # [EN] Generated and recycled by `world/crowd.py`. **Extras aren't decoration, they're "external
    # [EN] input"** --
    # [EN] In real-machine logs, "buy 0, customers 0, guests 20": the teahouse has no customers, so
    # [EN] characters can only loop internally
    # [EN] (627 "look"s, 565 "wipe"s). Business brings daily events.
    extras: list[dict] = field(default_factory=list)
    extras_today: int = 0             # 今天新生成过几个（对着 EXTRAS_DAILY_BUDGET）
    # ★★ 场上最近说过的话与做过的事（2026-10-07）——
    #   用户报「所有人说话都给我一种一直在自说自话的感觉……每个人说的话做的事情
    #   是互相没关联的」：根因是**人物决策时根本看不到别人刚说了什么**。
    #   每拍挑 1~2 人**并行**决策，而决策 prompt 里只有"场景 + 在场名单 + 我自己的记忆"
    #   —— 别人那句话从来没进过任何人的输入，所以只能各说各的。
    # [EN] How many were newly generated today (against EXTRAS_DAILY_BUDGET)
    # [EN] ★★ The most recent words and deeds on set (2026-10-07) --
    # [EN] User reported "everyone's speech gives me the feeling they're talking to themselves the whole
    # [EN] time... each person's words and deeds
    # [EN] are unrelated to each other": the root cause is that **characters simply can't see what others
    # [EN] just said when deciding**.
    # [EN] Each beat picks 1~2 people to decide **in parallel**, and the decision prompt has only "scene +
    # [EN] present roster + my own memory"
    # [EN] -- someone else's line never entered anyone's input, so each can only say their own thing.
    #
    #   这一份是**当场听得见的**（只有在这个地点的记录才进提示词）：
    #   `{'who': 人名, 'text': 那句话/那个动作, 'kind': 'speak'|'act', 'place': 地点}`
    #   最新的在**最后**。写入见 `RunLoop._process_actions`，读见 `recent_text()`
    #   （拼成决策提示词里的 `[刚才]` 那一段）。
    # [EN] This one is **audible on the spot** (only records at this location enter the prompt):
    # [EN] `{'who': name, 'text': that line/that action, 'kind': 'speak'|'act', 'place': location}`
    # [EN] Newest is at the **end**. Written in `RunLoop._process_actions`, read via `recent_text()`
    # [EN] (assembled into the `[刚才]` section of the decision prompt).
    #
    #   ⚠ 与"记忆"的分工：这里是**这一刻的桌面**（几拍就过），
    #     记忆是"我经历过的事"（跨天累积）。两者都要，别合并 ——
    #     合并的后果是"刚说完的话要等检索才想起"，那正是割裂感的来源之一。
    # [EN] ⚠ Division of labor with "memory": this is **this moment's desktop** (gone in a few beats),
    # [EN] memory is "things I've experienced" (accumulated across days). Both are needed, don't merge them
    # [EN] --
    # [EN] the consequence of merging is "a line just said waits for retrieval to be recalled", which is
    # [EN] one source of that disjointed feeling.
    recent_lines: list[dict] = field(default_factory=list)
    # ★ 钩子群演名册（2026-10-06）：**跨场记忆**就活在这张表里 ——
    #   `{称呼, 身份, 标志, 诉求, 见面次数, 上次第几天, 前情[], 已转正}`。
    #   与 `extras` 的分工：`extras` 是**此刻在场**的临演，
    #   `hooks` 是**来过的人的名册**（走了也留着，下次能认出来）。
    # [EN] ★ Hook extras roster (2026-10-06): **cross-scene memory** lives in this table --
    # [EN] Division of labor with `extras`: `extras` are the temp actors **present right now**,
    # [EN] `hooks` is the **roster of people who've been here** (kept after they leave, recognizable next
    # [EN] time).
    hooks: list[dict] = field(default_factory=list)
    hooks_promoted: list[str] = field(default_factory=list)   # 已建议转正的
    # [EN] Recommended for promotion to regular
    # ★★★ **今天真的被人理过的群演**（2026-10-21，收工整理要用）。
    #
    #   为什么必须单独记这一笔：整理稿的提示词里有一条硬禁令 ——
    #     「今天真正上场的人（正文里**不许出现**名单外的任何人）…… 一个字都不许写」
    #   而那份名单取自 `on_stage_names()`，**群演永远不在上面**（他们在 `extras` 里）。
    #   于是"门口来了一位、阿九问了他两句"这件事**在台本里真实发生了**，
    #   却因为这条禁令一个字都进不了正文（实测 mwl v4/v5/v6 三版：群演正文 0 次，
    #   而 run_mwl_v6 的日志里阿九明明问了「那掏井的，是来讨工钱的么？」）。
    #
    #   ⇒ 收工时把"被叫到名字/被人对着说话"的群演记在这里，整理稿据此
    #     **在禁令上开一个例外**（是他，就必须写）。
    #   ⚠ 只记**被理过的**：没人理的群演仍然不许进正文（那才是"白来一趟"），
    #     这一条与 `crowd.waiting` 是同一件事的两面。
    #   ⚠ 日界清空（`_end_day`），它只描述"今天"。
    # [EN] ★★★ **Extras someone actually dealt with today** (2026-10-21, needed by the wrap-up).
    # [EN] Why this must be recorded separately: the organizing prompt carries a hard ban --
    # [EN] "who actually took the stage today (nobody outside the list may appear in the prose) ...
    # [EN] not a single word", and that list comes from `on_stage_names()`, **which never includes
    # [EN] extras** (they live in `extras`). So "someone at the door and Chen Wang asked him two
    # [EN] questions" **really happened in the transcript** yet could not enter the prose at all
    # [EN] (measured across mwl v4/v5/v6: extras appear 0 times, while run_mwl_v6's log shows Chen
    # [EN] Wang asking "is that well-digger here for his wages?").
    # [EN] => At wrap-up, record the extras who were named / spoken to, and let the organizing pass
    # [EN] carve an **exception** in that ban (if it is him, it must be written).
    # [EN] ⚠ Only those **dealt with**: an ignored extra still may not enter the prose (that is
    # [EN] exactly "a wasted visit"), which is the other side of `crowd.waiting`.
    # [EN] ⚠ Cleared at the day boundary (`_end_day`); it only describes "today".
    extras_engaged: list[str] = field(default_factory=list)

    # 剧情
    # [EN] Plot
    tension: float = 0.3
    current_node: str = "N01"
    active_lines: list[str] = field(default_factory=list)
    activated_foreshadows: list[str] = field(default_factory=list)

    # 风格控制（网文参数）
    angst_level: float = 0.3          # 虐心程度：0=纯甜，1=虐到极致
    humor_level: float = 0.3          # 幽默度：0=纯正剧，1=纯喜剧
    satisfaction_density: float = 0.5 # 爽点密度：0=无，1=爽到飞起
    romance_ratio: float = 0.3        # 感情线占比：0=无，1=纯言情
    suspense_density: float = 0.5     # 悬念密度：0=无，1=悬念不断
    worldbuilding_pace: float = 0.5   # 世界观展开速度：0=缓慢，1=快速
    character_iq: float = 0.5         # 人物智商：0=降智，1=天才
    pacing_style: str = "medium"      # 节奏感：slow/medium/fast/roller
    # [EN] Style control (web-novel params)
    # [EN] Angst level: 0=pure sweet, 1=max angst
    # [EN] Humor: 0=pure drama, 1=pure comedy
    # [EN] Payoff density: 0=none, 1=flying high
    # [EN] Romance-line share: 0=none, 1=pure romance
    # [EN] Suspense density: 0=none, 1=relentless suspense
    # [EN] Worldbuilding reveal speed: 0=slow, 1=fast
    # [EN] Character IQ: 0=dumbed down, 1=genius
    # [EN] Pacing: slow/medium/fast/roller

    # ★★ 本轮推演的三样（2026-10-11，用户在「起笔」里点名要控制的）──
    # [EN] ★★ The three things this round of simulation (2026-10-11, the user named them in "起笔" as needing
    # [EN] control) --
    #
    #   · `round_cast`：**本轮只让这几个人上场**（空 = 全体）。装配时从
    #     `ROUND_CAST` 解析、并**跟本书人物表核对**（认不出来的丢掉，见
    #     `sim/setup.build_world`）—— 名单是人写的，换一本书之后名字多半对不上，
    #     不核对就会"名单里的人一个都不在这本书里 ⇒ 没人上场 ⇒ 整轮空转"。
    #   · `scene_locked`：本轮**锁在这个地点**、不发生换场（`ROUND_SCENE`）。
    #   · `daily_words`：每个故事日的**篇幅软目标**（0 = 不限）。它不改行为，
    #     只进提示词 + 状态条 —— 所以是"软"的，判据也只验"真的传下去了"。
    # [EN] · `round_cast`: **only let these people take the stage this round** (empty = everyone). At
    # [EN] assembly, parsed from
    # [EN] `ROUND_CAST` and **checked against this book's character table** (unrecognized ones dropped, see
    # [EN] `sim/setup.build_world`) -- the roster is written by hand; after switching to another book, the
    # [EN] names mostly won't match,
    # [EN] and if you don't verify, you get "none of the people on the roster are in this book => nobody
    # [EN] takes the stage => the whole round spins idle".
    # [EN] · `scene_locked`: this round is **locked to this location**, no scene change (`ROUND_SCENE`).
    # [EN] · `daily_words`: the **soft length target** for each story day (0 = unlimited). It doesn't
    # [EN] change behavior,
    # [EN] it only goes into the prompt + status bar -- so it's "soft"; the criterion only verifies that
    # [EN] "it really got passed down".
    round_cast: list[str] = field(default_factory=list)
    scene_locked: bool = False
    daily_words: int = 0

    # ★★ **今天的场次编排**（`director.stage.StagePlan`，2026-10-11）──
    #   由 `sim/loop` 在当天剧本写完之后挂上来。演员的决策提示词读它
    #   （`Agent._stage_line`），作者看到的"本场"那一段就是从这里来的。
    #   `None` = 这一天没有分拍 ⇒ 提示词里不出现这一段（行为与从前一样）。
    # ★★ **已经演到第几拍**（0 起算）—— **续跑时靠它接着走**，
    #   否则从第 1 拍重来（"昨天已经演到第 4 拍了"会被忘掉）。
    # [EN] ★★ **Today's stage schedule** (`director.stage.StagePlan`, 2026-10-11) --
    # [EN] hung here by `sim/loop` after the day's script is written. The actors' decision prompts read
    # [EN] it (`Agent._stage_line`); the "this scene" block the author sees comes from here.
    # [EN] `None` = no beat breakdown today ⇒ the block does not appear (behavior as before).
    # [EN] ★★ **Which beat we are on** (0-based) -- **a resume continues from this**, otherwise it
    # [EN] restarts at beat 1 (forgetting "we were already on beat 4").
    stage_plan: Any = None
    stage_index: int = 0
    #: ★★ **今天这张地图**（`image_gen.map_layout.Layout`，2026-10-12）。
    #: 用户：「**导演和剧作家在设计人物动作的时候 要时时刻刻参考地图作为人物移动的依据**」。
    #: 地图光画出来没用（那是给眼睛看的），**得有人读它**：演员与导演的提示词里
    #: 现在会带一句"你在哪儿、要去哪儿、**怎么走**"（`Agent._stage_line` 用
    #: `world.spatial.route()` 在**这张图**上算出来）。
    #: `None` = 今天没有图（没生成 / 关着）⇒ 那一句不出现（行为与从前一样）。
    # [EN] ★★ **Today's map** (`image_gen.map_layout.Layout`, 2026-10-12).
    # [EN] User: "**the director and playwright must constantly consult the map as the basis for character
    # [EN] movement** when designing character actions".
    # [EN] Drawing the map alone is useless (that is for the eyes); **somebody has to read it**: the actor
    # [EN] and director prompts now carry a line "where you are, where you are going, **how to walk**"
    # [EN] (computed by `Agent._stage_line` with `world.spatial.route()` **on this map**).
    # [EN] `None` = no map today (not generated / switched off) ⇒ that line does not appear (behavior as
    # [EN] before).
    day_map: Any = None

    # 系统
    # [EN] system
    game_day: int = 1
    event_count: int = 0
    branch_proposals: list[dict] = field(default_factory=list)

    # 背景
    # [EN] background
    worldview_text: str = ""
    # ★★ 分层设定（2026-10-07）——见 `world/layers.py`。
    #   `layer_index`：设定集编成的**分层条目**（世界/主线/场景/细节四层，
    #   每条带生效时机·场合·影响谁·权重）。
    #   `local_settings`：**推演中由剧组讨论出来的**局部设定（只进这两层）。
    #   ⚠ 两者都不参与快照序列化（快照拷目录，不做 dataclass dump），
    #     所以加字段不会牵动存盘格式。
    # [EN] ★★ Layered settings (2026-10-07) -- see `world/layers.py`.
    # [EN] `layer_index`: **layered entries** compiled from the settings collection
    # [EN] (world/mainline/scene/detail, four layers,
    # [EN] each carrying effective timing · occasion · who it affects · weight).
    # [EN] `local_settings`: local settings **hashed out by the crew during simulation** (only these two
    # [EN] layers go in).
    # [EN] ⚠ Neither participates in snapshot serialization (snapshots copy directories, no dataclass
    # [EN] dump),
    # [EN] so adding fields won't touch the save format.
    layer_index: list = field(default_factory=list)
    local_settings: list = field(default_factory=list)
    # ★ 顶级规则（2026-10-06）：作者写死的硬约束（世界铁律 / 禁忌 / 写作守则）。
    #   与 `worldview_text` 分开存，是为了**不被压缩** —— 世界观在 prompt 里
    #   只取前 500 字，而规则是判据，截了就等于改了。来源见 `ingest/pipeline.collect_rules`。
    # [EN] ★ Top-level rules (2026-10-06): hard constraints written by the author (world iron laws / taboos
    # [EN] / writing guidelines).
    # [EN] Stored separately from `worldview_text` so as **not to be compressed** -- the worldview in the
    # [EN] prompt
    # [EN] only takes the first 500 chars, while rules are criteria; truncating them is equivalent to
    # [EN] changing them. Source: see `ingest/pipeline.collect_rules`.
    rules_text: str = ""
    #: **只给写作层**的约束（`style.notes`）：作家读，演员**不读**。
    #: ⚠ 与 `rules_text` 分开存放，因为 `rules_text` 会原样进每个演员的提示词；
    #:   而「每样最多复位三次」这类成品要求，演员在一拍里没法执行，只会让他不敢动。
    # [EN] Constraints for the **writing layer only** (`style.notes`): the writer reads them,
    # [EN] actors do **not**. Kept apart from `rules_text`, which goes verbatim into every actor
    # [EN] prompt; "each prop resets at most three times" is not executable within one beat and
    # [EN] only makes the actor avoid the prop.
    writer_notes: str = ""
    #: **给演员**的表演备注（`style.actor_notes`）：会进演员前缀。
    #: 判据只有一条：**这是演员在一拍里能做/能不做的事吗？**
    # [EN] Performance notes that **do** reach actors. One test: can an actor do or not do
    # [EN] this inside one beat?
    actor_notes: str = ""
    style_card: dict = field(default_factory=dict)
    # ★ 风格来源（`NOVEL_STYLE` / 书斋的「风格来源」，2026-10-06 接）——
    #   以前这两项**只读展示、从不落盘、也从不进 prompt**：
    #   作者在书斋里挑「冷笔白描」，推演时一个字都没变。
    #   `auto`=用抽出来的风格卡；`plain`=不用风格卡（朴素直叙）；
    #   `custom`=用作者手写的 `style_custom`；其余取值按"风格名"直接进 prompt。
    # [EN] ★ Style source (`NOVEL_STYLE` / the study's "style source", wired in 2026-10-06) --
    # [EN] previously these two were **display-only, never persisted, never entered the prompt**:
    # [EN] the author picks "cold sparse description" in the study, and during simulation not a single
    # [EN] character changes.
    # [EN] `auto` = use the extracted style card; `plain` = don't use a style card (plain direct
    # [EN] narration);
    # [EN] `custom` = use the author's hand-written `style_custom`; other values enter the prompt directly
    # [EN] as the "style name".
    style_source: str = "auto"
    style_custom: str = ""
    # ★ 本幕提示（`SCENE_START_HINT`）：每场戏开始时给模型的一句指引。
    # [EN] ★ This-act hint (`SCENE_START_HINT`): a one-line guidance given to the model at the start of
    # [EN] each scene.
    scene_hint: str = ""
    # ★★ 剧组给演员的「规定情境」三样（2026-10-07 审计补上）。
    # [EN] ★★ The three things of the "given circumstances" the crew gives the actor (added in the
    # [EN] 2026-10-07 audit).
    #
    # 斯坦尼体系里，演员上场前必须握有三样：**我是谁 · 我在什么地方 ·
    # 我身上/身边有什么**。前两样本项目一直有（`persona` + `scene`），
    # 后两样是这轮补的 —— 而它们此前**算出来了却没送到演员手上**：
    #   · `stylist_brief` ← 造型（衣着/随身物/仪态）。名册写着它 `feeds='actor'`，
    #     实际产出只落了一份 `造型表.md`，演员一个字都看不到。
    #   · `sound_design` ← 声音（底噪/事件声/该响而没响的）。它喂的是
    #     **场景的环境句**（`SceneBuilder`），不是台词 —— "听得见什么"是
    #     场面的一部分，不该由人物自己说出来。
    # 两者都由 `sim/loop` 在开拍前写进来；取不到就是空（**不许编**）。
    # [EN] In the Stanislavski system, an actor must hold three things before going on stage: **who I am ·
    # [EN] where I am ·
    # [EN] what is on me/beside me**. The first two this project always had (`persona` + `scene`),
    # [EN] the latter two were added this round -- and previously they were **computed but never delivered
    # [EN] to the actor**:
    # [EN] · `stylist_brief` <- styling (clothing/carried items/demeanor). The roster says it
    # [EN] `feeds='actor'`,
    # [EN] but the actual output only landed as a `造型表.md`, and the actor sees not a single character of
    # [EN] it.
    # [EN] · `sound_design` <- sound (background noise/event sounds/things that should sound but don't). It
    # [EN] feeds
    # [EN] **the scene's ambient sentences** (`SceneBuilder`), not dialogue -- "what can be heard" is
    # [EN] part of the scene, and shouldn't be spoken by the character himself.
    # [EN] Both are written in by `sim/loop` before the shoot; if unavailable, they're empty (**no making
    # [EN] things up**).
    stylist_brief: str = ""
    sound_design: dict = field(default_factory=dict)
    # ★ **导演心里那个大纲**（`director/supervisor.outline_check` 的产出）：
    #   现在走到哪了、今天排了几拍。用户 2026-10-07：「导演要一直心里有一个大纲
    #   从顶层到细节一直把控剧情进展」。以前这个函数写好了**零调用**，
    #   大纲只活在 docstring 里。现在每 `DIRECTOR_WATCH_EVERY` 拍刷一次，
    #   进日志、进导演提示、也进复盘的材料。
    # [EN] ★ **The outline in the director's head** (the output of `director/supervisor.outline_check`):
    # [EN] where we are now, how many beats were scheduled today. User 2026-10-07: "the director must
    # [EN] always have an outline in his head,
    # [EN] controlling plot progress from top level down to detail". Previously this function was written
    # [EN] but **had zero calls**,
    # [EN] the outline lived only in the docstring. Now it refreshes every `DIRECTOR_WATCH_EVERY` beats,
    # [EN] entering the log, the director prompt, and the review material.
    outline_note: str = ""
    # ★★ **演员开口之前的盘算**（2026-10-07 第七轮，思维链的落点）：
    #   `{人名: 最近一条推演}`，由 `sim/loop._note_think` 每拍刷新。
    #   消费方是**剧组台账里「演员」那一行** —— 作者能看到"这句话为什么这么说"。
    #   ⚠ 它**不进叙事、不进 `recent_lines`**：盘算是私下的，他没说出口。
    # [EN] ★★ **The reckoning before the actor speaks** (2026-10-07 round seven, the landing point of the
    # [EN] chain of thought):
    # [EN] `{person name: latest simulation note}`, refreshed every beat by `sim/loop._note_think`.
    # [EN] The consumer is **the "actor" row in the crew ledger** -- the author can see "why this line is
    # [EN] said this way".
    # [EN] ⚠ It **does not enter the narrative, does not enter `recent_lines`**: the reckoning is private,
    # [EN] he didn't say it aloud.
    actor_think: dict = field(default_factory=dict)
    #: ★ 每个在场角色**最近一次决策完成**的单调时钟时间戳（秒）。
    #:   剧组台账据此把这行在 `CHAR_BUSY_WINDOW` 秒内标 `busy=True` → 暖金高亮，
    #:   让界面"实时看到谁这一拍在动"（`actor_think` 只记文本、不带时间，
    #:   所以另存一份时间戳；见 `sim/loop._note_think` 与 `crew/studio.ledger`）。
    # [EN] monotonic timestamp (sec) of each on-stage character's **latest decision completion**.
    # [EN] The crew ledger uses it to flag the row `busy=True` within `CHAR_BUSY_WINDOW`
    # [EN] -> warm-gold highlight, so the UI "sees in real time who is moving this beat"
    # [EN] (`actor_think` stores only text, no time, so a separate timestamp is kept;
    # [EN] see `sim/loop._note_think` and `crew/studio.ledger`).
    actor_think_at: dict = field(default_factory=dict)
    genre_card: dict = field(default_factory=dict)
    progress_nodes: list[dict] = field(default_factory=list)
    #: 最近一次进度评估说的**「走到哪儿了」**（`进展描述`，模型每次都会给）。
    #:
    #: ★★★ 2026-10-21（用户：「运行界面右上角的剧情的进度表一直不动」）：
    #:   查下来**不是没在跑** —— 那天 21:34→22:18 评估了 14 次、模型每次都答了，
    #:   7 次结论全是 `满足: false`（理由一致：「多站委托未完成」）。也就是说
    #:   **确实是判据没满足**，数字不该动。
    #:
    #:   但界面因此**看不出来它在动**：模型每次都附了一句进展描述
    #:   （「阿九见旧账落款笔锋与执壶手势暗合，线索初现」），而旧代码只在
    #:   `done=True` 时才用它（`（进度）节点完成：…`）⇒ 没完成时**整句丢掉**，
    #:   界面上只剩一个不变的 `0/4`。用户看到的"一直不动"就是这个：
    #:   **故事在推进，而唯一能证明它推进的那句话被扔了**。
    #:   ⇒ 记在这里，由右上「剧情」面板照读（界面不自己算、也不自己存）。
    #: ⚠ 只在**真拿到结论**时写（`ok=True`）；失败时保留上一次的，
    #:   否则一次网络抖动就会把"走到哪了"擦成空白。
    # [EN] ★★★ 2026-10-21 (user: "the plot progress table in the top-right never moves"): measured --
    # [EN] it **was** running: 14 evaluations between 21:34 and 22:18, the model answered every time,
    # [EN] and all 7 verdicts were `满足: false` (same reason: "the multi-station commission is not
    # [EN] done"). So the criteria genuinely were not met; the number should not move.
    # [EN] But the UI therefore **cannot show that anything is happening**: every verdict carried a
    # [EN] progress line ("阿九 sees the ledger's signature match his teapot gesture, first clue"), yet
    # [EN] the old code used it only when `done=True` (`（进度）节点完成：…`) => on a non-done verdict the
    # [EN] whole sentence was **discarded**, leaving just an unchanging `0/4`. That discard *is* the
    # [EN] "never moves" the user saw: **the story advances while the only evidence is thrown away**.
    # [EN] => Stored here and read straight out by the top-right Plot panel (the UI computes nothing).
    # [EN] ⚠ Only written when a conclusion was really obtained (`ok=True`); on failure keep the previous
    # [EN] one, or a single network hiccup would erase "where we are" into a blank.
    progress_note: str = ""

    # 快照
    # [EN] snapshot
    _snapshot_counter: int = 0

    def clock_display(self, *, with_day: bool = True) -> str:
        """这一刻的显示文本。

        `with_day=False` 只给**时段**（"子时"）—— 用在**已经有了"第 N 天"的标题**里。
        为什么要有它（2026-10-18《雪国》复测，评委点名的第 5 条缺陷）：
        `当天故事.md` 的章节头写成 `## 第 {day} 天 · {clock_display()}`，
        而默认 `auto` 日历的 `clock_display()` **自带"第N天·"** ⇒ 成了
        `## 第 1 天 · 第1天·子时`，读者一眼就看出来是程序拼的。
        [EN] The display text of this moment. `with_day=False` gives **only the time of day**
        [EN] ("zi hour") -- for headings that already say "day N". Why it exists (measured in the
        [EN] 2026-10-18 Snow Country re-run, the judge's 5th defect): the `当天故事.md` chapter head
        [EN] was `## 第 {day} 天 · {clock_display()}`, while the default `auto` calendar already
        [EN] prefixes "day N" => `## 第 1 天 · 第1天·子时`, obviously machine-assembled.
        """
        return format_game_clock(self.clock, self.calendar, with_day=with_day)

    def _loc_matches(self, ps: PersonState) -> bool:
        """他是不是就**在这场戏的地点**。

        规则**从宽**（宁可多算在场，也别把该在的人滤掉）：
          · 没定位（`location` 空）→ 算在场（多数人物装配时没有初始位置）；
          · `location` 与 `scene` 有包含关系（「临河茶肆」vs「临河茶肆后厨」）→ 算在场；
          · ★ **他不去任何"别的地方"**（2026-10-07 加）→ 算在场。
            人物常常 move 到**同一场戏里的某个角落**（「柜台后」「后院」
            「楼上」「门外」），这些名字跟场景名没有包含关系，也不是设定里
            单列的地点 —— 照老规矩会被判成"他走了"，于是他**从在场名单里消失**，
            屏幕上打出「离场」，下一拍这个人就不再决策（演示里跑一遍就能看到）。
            判据就是：**只要有地点表，而他去的那个地方不在表里**，
            那更像是"在这一场里挪了挪"。
            ⚠ 必须**有地点表**才启用：表空的话所有 location 都"不在表里"，
              那等于把"在场"放宽成整份前台名册（老毛病，见 `is_on_stage` 的说明）。
          · 都不沾边（他去了表里**另一个真地点**，比如「城东渡口」）→ 不在场。
        
                English:
        Whether he is **at this scene's location**.
                Rule is **lenient** (better to over-count presence than to filter out someone who should be there):
                  · No location (`location` empty) → count as present (most characters have no initial position when assembled);
                  · ★ **He doesn't go to any "other place"** (added 2026-10-07) → count as present.
                    Characters often move to **some corner within the same scene** ("柜台后", "后院",
                    "楼上", "门外"); these names have no containment relationship with the scene name, nor are they
                    locations listed separately in the settings —— by the old rule they'd be judged as "he left", so he **disappears from the present list**,
                    the screen prints "离场", and in the next beat this person no longer makes decisions (you can see it by running the demo once).
                    The criterion is: **as long as there is a location table, and the place he goes to is not in the table**,
                    that's more like "he shifted a bit within this scene".
                    ⚠ Must **have a location table** to enable: if the table is empty, all locations are "not in the table",
                      which is equivalent to loosening "present" to the entire front-stage roster (the old problem, see the note on `is_on_stage`).
                  · Neither applies (he went to **another real location** in the table, e.g. "城东渡口") → not present.
        """
        loc = str(getattr(ps, "location", "") or "").strip()
        scene = str(self.scene or "").strip()
        if not loc or not scene:
            return True
        if loc in scene or scene in loc:
            return True
        known = {str(x).strip() for x in
                 (getattr(self, "place_names", None) or []) if str(x).strip()}
        if known and loc not in known:
            return True
        return False

    def is_on_stage(self, ps: PersonState) -> bool:
        """这一刻他在不在场上：**活着在场 · 前台 · 就在这个地点**
        （＋ 本轮名单里点名要他上场）。

        ⚠ 别再退回 `ps.is_active()`（那只看 `status`+`role`，而 `role` 是装配时
        定死的）—— 那正是「在场 = 整份前台名册」的来源：真机日志里 126 次决策
        在场名单**一模一样**，连终局才登场的角色都天天在场。

        ★ 2026-10-11 加**本轮名单**那一档（用户：「起笔时可以控制……本轮出场人物」）：
        `round_cast` 非空时，没被点到的人这轮不算在场（不参与决策）。
        这是**硬限制**，不是"优先"——用户要的就是"只想看他俩的戏"。
        ⚠ 空列表 = 全体（不是"没人上场"）：没设这一项时行为与以前逐字一致。
        
                English:
        Whether he is on stage at this moment: **alive and present · front stage · at this very
        location**
                (+ this round's roster explicitly names him to appear).
                ⚠ Don't fall back to `ps.is_active()` (that only looks at `status`+`role`, and `role` is fixed
                at assembly time) —— that is precisely the source of "present = the entire front-stage roster": in real-machine logs, across 126 decisions
                the present list was **identical**, even characters who only debut at the finale were present every day.
                ★ 2026-10-11 added the **this round's roster** tier (user: "at the start of writing you can control... this round's appearing characters"):
                When `round_cast` is non-empty, those not named do not count as present this round (don't participate in decisions).
                This is a **hard limit**, not a "priority" —— what the user wants is exactly "only want to watch the scene with just those two".
                ⚠ Empty list = everyone (not "nobody appears"): when this item is unset, behavior is verbatim identical to before.
        """
        if self.round_cast and ps.name not in self.round_cast:
            return False
        return ps.is_active() and self._loc_matches(ps)

    def on_stage_names(self) -> list[str]:
        return [p.name for p in self.people.values() if self.is_on_stage(p)]

    def off_stage_names(self) -> list[str]:
        return [p.name for p in self.people.values()
                if not self.is_on_stage(p) and p.status == "在场"]

    def pending_names(self) -> list[str]:
        """还没登场的人（开场那句「未登场：…」用它）。
                English:
        Characters who have not yet appeared (the opening line "未登场：..." uses it).
        """
        return [p.name for p in self.people.values() if p.status == "未登场"]

    def promote_debuts(self, day: int | None = None) -> list[str]:
        """到日子的人登场：`未登场` → `在场`。返回这一批登场的人。

        跨天时调一次（`sim/loop.py` 的 `_end_day`）—— 不这样做的话，
        `debut_day` 就只是个摆设，人物永远不会自己出场。
        
                English:
        Characters whose day has come appear: `未登场` → `在场`. Return this batch of characters who
        appeared.
                Call once when crossing days (`sim/loop.py`'s `_end_day`) —— if not done,
                `debut_day` is just a decoration, and characters will never appear on their own.
        """
        d = int(day if day is not None else self.game_day)
        out: list[str] = []
        for p in self.people.values():
            if p.status == "未登场" and d >= max(1, int(p.debut_day or 1)):
                p.status = "在场"
                p.met = True
                out.append(p.name)
        return out

    def extras_line(self) -> str:
        """群演合成的一句话（拼进场景句；没有群演就返回空串）。
                English:
        A single sentence synthesized from extras (spliced into the scene sentence; returns empty string
        if no extras).
        """
        bits = [str(e.get("一行") or "").strip() for e in self.extras]
        return "；".join(b for b in bits if b)

    # ── 场上对话缓冲（"接话"的地基，2026-10-07）────────────────────────
    #: 最多留几条。**这是一张"桌面"，不是记事本** —— 留太多会让
    #: 提示词变成一段流水账，而且越早的话越没人在意。
    #: ★ 2026-10-18 从 8 调到 24：这张桌面现在还要供**防重演**取数
    #:   （`last_own_action` / `last_own_line`）—— 一拍七个人各说一句，
    #:   8 条里根本活不过一拍，取数口子等于永远拿不到东西。
    #:   ⚠ 拼进提示词的条数**不受影响**（由 `RECENT_LINES_SHOW` 管），
    #:     所以加大缓冲不多花一个 token。
    # [EN] -- On-stage dialogue buffer (the foundation of "picking up lines", 2026-10-07)
    # [EN] ------------------------
    # [EN] : max number kept. **This is a "desktop", not a notepad** -- keeping too many will make
    # [EN] : the prompt become a running account, and the earlier the line, the less anyone cares.
    # [EN] ★ 2026-10-18 raised from 8 to 24: this desktop now also feeds **anti-replay**
    # [EN]   (`last_own_action` / `last_own_line`) -- with seven people speaking one line each per
    # [EN]   beat, an entry does not survive a single beat inside 8, so the accessor always came up
    # [EN]   empty. ⚠ The number spliced into the prompt is **unaffected** (governed by
    # [EN]   `RECENT_LINES_SHOW`), so a bigger buffer costs not one extra token.
    RECENT_LINES_MAX = 24
    #: 拼进提示词时最多给几条（最新几条优先）
    # [EN] : max number given when concatenated into the prompt (latest ones prioritized)
    RECENT_LINES_SHOW = 6
    #: `kind` 的两族。**这两张表必须与"真正往缓冲里写的人"一致** ——
    #: 2026-10-18 的血：`sim/loop._note_stage_line` 写的是 `kind='act'`，
    #: 而 `last_own_action` 只认 `'action'` ⇒ 防重演块整整一个版本没有生效，
    #: 判据却全绿（夹具自己编了一个产品从不写的 kind）。
    #: ⇒ 改 kind 时**两边一起改**；`verify_repetition_guards` 的 A 组会扫生产侧核对。
    # [EN] The two families of `kind`. **These two tables must match whoever actually writes into
    # [EN] the buffer** -- the 2026-10-18 lesson: `sim/loop._note_stage_line` writes
    # [EN] `kind='act'`, while `last_own_action` only accepted `'action'` => the anti-replay
    # [EN] block never ran for a whole version, yet every criterion was green (the fixture invented
    # [EN] a kind the product never writes).
    # [EN] => change both sides together; group A of `verify_repetition_guards` scans the
    # [EN] production side to check.
    SPEAK_KINDS = ('speak',)
    ACT_KINDS = ('act', 'action', 'move', 'enter', 'exit', 'gesture')

    def note_line(self, who: str, text: str, *, kind: str = 'speak',
                  to: str = '', place: str = '') -> None:
        """记一句"场上刚发生的话/事"（给后面的人接话用）。

        `place` 不传就取当前场景 —— 调用方（主循环）手上那份可能已经变了
        （人物 `move` 之后场景会跟着换），所以显式传更准。
        `kind`：`speak` 台词 · `act` 动作。
        `to`：这句话**是对谁说的**（空 = 说给场上的大家听）。
        ⚠ 别省 `to`：人物要判断"这句是不是冲我来的"，靠的就是它 ——
          没有它，"阿枝对主角说话"和"阿枝自言自语"在纸上长得一样。
        
                English:
        Record a sentence of "what just happened/was said on stage" (for later characters to respond
        to).
                If `place` is not passed, take the current scene —— the caller (main loop) may already have a changed copy
                (the scene changes after a character `move`s), so passing it explicitly is more accurate.
                `kind`: `speak` dialogue · `act` action.
                `to`: **whom this sentence is said to** (empty = said to everyone on stage).
                ⚠ Don't omit `to`: a character judging "is this sentence aimed at me" relies on it ——
        """
        w = str(who or '').strip()
        t = ' '.join(str(text or '').split())
        if not t:
            return
        # ★ **相邻去重**：同一人紧接着说同一句话就不要记第二遍。
        #   为什么需要：主循环里有两处会记同一句话 ——
        #   ① 领说者决策完立刻记一次（好让同拍的其他人看得到），
        #   ② 动作落地时统一记一次。少了这道去重，同一句会在
        #   `[刚才]` 里出现两遍（读起来像他又说了一次）。
        # [EN] ★ **Adjacent dedup**: if the same person says the same sentence right after, don't record it a
        # [EN] second time.
        # [EN] Why it's needed: in the main loop there are two places that record the same sentence --
        # [EN] ① the lead speaker records once right after deciding (so others in the same beat can see it),
        # [EN] ② the action records once uniformly when it lands. Without this dedup, the same sentence appears
        # [EN] twice in `[刚才]` (reads like he said it again).
        if self.recent_lines:
            last = self.recent_lines[-1]
            if (str(last.get('who') or '') == w
                    and str(last.get('text') or '') == t[:120]):
                return
        place = str(place or self.scene or '').strip()
        self.recent_lines.append({'who': w, 'text': t[:120],
                                  'kind': str(kind or 'speak'),
                                  'to': str(to or '').strip()[:24],
                                  'place': place})
        if len(self.recent_lines) > self.RECENT_LINES_MAX:
            # 从**头部**丢（最老的先走）—— 头部最远、最不重要
            # [EN] Drop from the **head** (oldest goes first) -- the head is farthest and least important
            del self.recent_lines[:-self.RECENT_LINES_MAX]

    def open_asks(self, speaker: str, limit: int = 3) -> list[dict]:
        """这个人**问了、但一直没被正面回答**的事。返回 `[{ask, times, last, dodged}]`。

        ★★★ 为什么要它（2026-10-19 第五轮，用户第二次报同一个毛病）
        ------------------------------------------
        「一个人从头到尾说的话之间没有任何关系，不是一系列有关联的事件连续下来，
        还是不同的事情胡乱跳」。

        前一次修法给的是一块"你在这场说过的话 + 你要有自己的一条线"。
        实测两次真跑：一次承接 50%，一次又退回 35% —— **时灵时不灵**。
        看材料才看清是结构问题：每一拍场上都有人在说话，他**每拍都在回答
        别人刚提的问题**（问他"你觉得叶子什么样"→他答叶子；问他"要准备什么"→
        他答"您刚到辛苦了吧"）⇒ 自己那件事被挤掉，三句就断。

        ⇒ 光有"我说过什么"不够，还得有"**我这件事还没办成**"。
          而"没办成"最可数的形状是：**同一个问题问了 N 次，对方每次都没正面答**。
          这不是抽象评价，是账本 —— 与 `_tic_quota_line` 同一条纪律：
          给可数的事实，模型没法忽视。

        ⚠ 判"没答"用**共享实词**（>= 2 个二元组），不做语义判断：
          语义判断要一次模型调用，而那次调用会立刻退化成"你判断他答没答"。
          粗一点没关系 —— 误判的后果只是某一条没被算进来。
        ⚠ 只看当前这一幕（换场本来就该重新开始，`clear_lines` 会清）。
        [EN] What this person **asked but never got a straight answer to**.
        [EN] Why: the previous fix gave "what you said" + "you need your own thread", which measured
        [EN] 50% then back to 35% -- it works only sometimes. The structure is that every beat
        [EN] someone else asks something and he answers **that**, pushing his own matter out after
        [EN] three lines. So "what I said" is not enough; he needs "**my thing is still not done**",
        [EN] and the countable shape of that is "I asked N times and never got a straight answer".
        [EN] ⚠ "Not answered" is judged by **shared bigrams** (>= 2) rather than semantics: a semantic
        [EN] judgement costs a model call and immediately degrades into "you decide if he answered".
        """
        me = str(speaker or '').strip()
        if not me:
            return []
        n = int(limit or 3)
        if n <= 0:
            return []
        rows = list(self.recent_lines or [])
        asks: list[dict] = []

        def _plain(w: str) -> str:
            return str(w or '').split('（', 1)[0].split('(', 1)[0].strip()

        def _bigrams(t: str) -> set[str]:
            z = ''.join(re.findall(r'[\u4e00-\u9fff]', t))
            return {z[i:i + 2] for i in range(len(z) - 1)}

        for i, r in enumerate(rows):
            if _plain(r.get('who')) != me:
                continue
            if str(r.get('kind') or '') not in self.SPEAK_KINDS:
                continue
            t = str(r.get('text') or '').strip()
            # "提问"的判据：问号结尾，或者带疑问词（中文里大量问句不带问号）
            if not (t.endswith('？') or t.endswith('?')
                    or any(k in t for k in ('吗', '呢', '什么', '怎么', '为什么',
                                            '是不是', '会不会', '要不要', '哪'))):
                continue
            core = _bigrams(t)
            if len(core) < 2:
                continue
            # 往后看接下来的两句别人的话：只要有一句共享 >= 2 个二元组，就算答了
            answered = False
            dodge: list[str] = []
            seen_other = 0
            for r2 in rows[i + 1:]:
                if _plain(r2.get('who')) == me:
                    break
                if str(r2.get('kind') or '') not in self.SPEAK_KINDS:
                    continue
                t2 = str(r2.get('text') or '').strip()
                # ⚠ 门槛取 **1**（不是 2）：实测 `账本你见过吗？` → `账本在柜子里。`
                #   只共享「账本」一个二元组，按 2 判会把**真答了的**算成没答。
                #   误判方向要选"宁可不报"：多报一条假"没答"，模型会去追问一件
                #   其实已经答过的事 —— 那比少报更糟。
                if len(core & _bigrams(t2)) >= 1:
                    answered = True
                    break
                dodge.append(t2)
                seen_other += 1
                if seen_other >= 2:
                    break
            if answered or not dodge:
                continue
            asks.append({'ask': t, 'dodged': dodge[-1] if dodge else ''})
        if not asks:
            return []
        # 同一件事重复问的，合成一条并计数（"问了三遍"才是那股劲儿）
        merged: list[dict] = []
        for a in asks:
            hit = None
            for m in merged:
                if len(_bigrams(a['ask']) & _bigrams(m['ask'])) >= 1:
                    hit = m
                    break
            if hit is None:
                merged.append({'ask': a['ask'], 'times': 1, 'dodged': a['dodged']})
            else:
                hit['times'] += 1
                hit['ask'] = a['ask']          # 用最后一次的说法（通常是更急的那个）
                hit['dodged'] = a['dodged']
        merged.sort(key=lambda m: -m['times'])
        return merged[:n]

    #: **回避性回应**（被问到却不肯正面答的说话方式）。
    #: ⚠ 与 `DIALOGUE` 的"重复"判据不是一回事：那个判"同一句说了两遍"，
    #:   这个判"**一直用同一种方式躲**"——句子可以每次都不一样。
    # [EN] **Evasive replies** (answering a question without answering it). Not the same as the
    # [EN] repetition criterion: that one judges "the same line twice", this one judges "always
    # [EN] dodging the same way" -- the wording can differ every time.
    DODGE_MARKS = ('没听清', '没听见', '听不清', '你说什么', '什么？', '什么?',
                   '不知道', '说不好', '说不清', '算了', '不提这个', '别说这个',
                   '困了', '改天', '以后再说', '夜深了', '喝酒')

    def dodge_count(self, speaker: str, limit: int = 12) -> tuple[int, list[str]]:
        """这个人**最近几次被问到时的回应里，有几次是在躲**。返回 `(次数, 那几句原文)`。

        ★★★ 为什么要它（2026-10-19 第六轮，用户贴的分析第二条）
        ------------------------------------------------
        用户原话：「岛村的"没听清"：反复表现出"没听清"（至少三次），这是塑造疏离
        性格的手法。但当他说"你刚说的话，我好像……捕捉到了一点"时，**这个转变
        缺乏铺垫**。他之前的行为模式是"完全没听进去"，这里突然变成了"捕捉到一点"，
        动机不明，显得突兀。」

        这是"态度要有轨迹"的问题，而它的**可数形状**是：
        **同一个人用同一种方式躲了 N 次，第 N+1 次突然变了** —— 中间没有台阶。
        ⇒ 账本记"躲了几次、每次都怎么躲的"，然后要求：**躲到第 3 次，必须给一个
          明确的态度**（承认 / 拒绝 / 改口），不许再躲第 4 次。这样"转变"就落在
          第 3 次之后，读者看得见那个台阶；而"一直躲"也不会无限循环。

        ⚠ 只看 `speak`（心声里的"我不想答"不是回应，没人听见）。
        ⚠ 判"躲"用词表（`DODGE_MARKS`），不做语义判断 —— 语义判断要一次模型调用，
          而且会退化成"你判断他躲没躲"（本项目反复踩过的那个坑）。
        [EN] How many of this person's recent replies were **dodges**, plus the actual lines.
        [EN] The user's words: "he says 'I didn't catch that' at least three times ... but then
        [EN] suddenly says 'I caught a bit of it' -- **that shift has no setup**". The countable
        [EN] shape is: **he dodged N times the same way, then changed** with no step in between. So
        [EN] keep a ledger and require: **by the third dodge he must take a clear stance** (admit /
        [EN] refuse / change his words) -- then the shift lands after a visible step, and dodging
        [EN] cannot loop forever. ⚠ `speak` only (a thought nobody heard is not a reply).
        """
        me = str(speaker or '').strip()
        if not me:
            return 0, []
        n_max = int(limit or 12)
        hits: list[str] = []
        for r in reversed(list(self.recent_lines or [])):
            if str(r.get('kind') or '') not in self.SPEAK_KINDS:
                continue
            if str(r.get('who') or '').split('（', 1)[0].split('(', 1)[0].strip() != me:
                continue
            t = str(r.get('text') or '').strip()
            if not t:
                continue
            if any(m in t for m in self.DODGE_MARKS):
                hits.append(t)
            if len(hits) >= n_max:
                break
        return len(hits), list(reversed(hits))

    #: **称呼词** —— 当面叫人时用的那类词（不是名字本身）。
    #: ⚠ 只收"一看就是称呼"的：带第二人称（您/你）或明确的职业/亲属称谓。
    #:   不收"喂""嘿"这种语气词（那不是称呼，是语气）。
    # [EN] **Terms of address** -- what a character calls another to their face. Only clear cases:
    # [EN] second person (您/你) or a definite occupational/kinship term. Interjections are excluded.
    ADDRESS_WORDS = (
        '客人', '先生', '小姐', '太太', '夫人', '掌柜', '老板', '师傅', '大夫', '老师',
        '大哥', '大姐', '少爷', '姑娘', '娘子', '老爷', '奶奶', '夫人', '公子',
        'boss', 'sir', 'madam',
    )

    @classmethod
    def detect_address(cls, text: str, names: Iterable[str] = ()) -> str:
        """这一句里**最先出现的那个称呼**（空串 = 没叫称呼）。**纯函数，可单测。**

        ★★★ 为什么"名字 + 称谓"要算**一个**称呼（2026-10-19 实测两次才定下来）
        ------------------------------------------------------------------
        用户点名的现象是「驹子从称'客人'改口称'**岛村先生**'」——
        也就是说 `客人` 和 `岛村先生` 是**两个不同的称呼**，它们的切换正是要检测的东西。

        而词表里只有单字称谓（`先生` / `太太`），于是：
          · 第一版按词表顺序挑 ⇒ 「岛村先生，您还没休息呀？」被记成 `先生`；
          · 第二版改成"位置最靠前" ⇒ 还是 `先生`（`岛村` 不在词表里）。
        两次都把 `客人 → 岛村先生` 记成 `客人 → 先生` —— **改口这件事本身被抹掉了**。
        ⇒ 现在：称谓前面**紧挨着**人名时，拼成「人名+称谓」整体算一个称呼。

        ⚠ `names` 不传就只认裸称谓（那是已知的漏，调用方应该传）。
        ⚠ 同一句里出现多个称呼时取**最靠前**的（人开口只会先叫一声）。
        [EN] The first term of address in this line ('' = none). **Pure function.** Why "name + term"
        [EN] must count as **one** term: the phenomenon being tested is 「客人 → 岛村先生」, so those
        [EN] are two different terms and the switch between them is the signal. Both earlier versions
        [EN] recorded 「岛村先生」 as plain 「先生」 (the name is not in the word list), which **erased
        [EN] the re-addressing itself**. So when a name sits immediately before the term, the two are
        [EN] joined into one address. ⚠ Without `names` only bare terms are recognised (a known gap;
        [EN] callers should pass names). ⚠ Take the earliest when several appear.
        """
        t = str(text or '')
        if not t:
            return ''
        nm = tuple(str(x) for x in (names or ()) if x)
        best: tuple[int, int, str] | None = None      # (位置, 负长度, 称呼)
        for w in cls.ADDRESS_WORDS:
            pos = t.find(w)
            while pos >= 0:
                # 称谓前面紧挨着人名 ⇒ 整体算一个称呼
                head = ''
                for n in nm:
                    if pos >= len(n) and t[pos - len(n):pos] == n:
                        if len(n) > len(head):
                            head = n
                full = head + w
                key = (pos - len(head), -len(full), full)
                if best is None or key[:2] < best[:2]:
                    best = key
                pos = t.find(w, pos + 1)
        return best[2] if best else ''

    def address_ledger(self, speaker: str, limit: int = 40) -> list[tuple[str, str, int]]:
        """这个人**这一场分别用哪些称呼叫过谁**：`[(对象, 称呼, 次数)]`，按次数降序。

        ★★★ 为什么要它（2026-10-19 第十一轮，用户报的第一条：「称呼系统的混乱与断裂」）
        -------------------------------------------------------------------
        用户原话：「岛村称'你'，驹子称'客人'…驹子突然改口称'岛村先生'——
        这个转变**没有心理或事件上的铺垫**，显得突兀。称呼是人际关系最直接的反映。
        它的变化**必须有情感逻辑支撑**，否则就是机械的文字游戏。」

        这是"关系推进没有台阶"的问题，而它的**可数形状**是：
        **同一个人对同一个对象，用了 N 种称呼，中间没有任何事件。**
        ⇒ 账本记"你叫过他什么、各几次"；提示词据此要求:
          · 已经有了固定称呼时，**换称呼必须有一次事件垫着**（他做了什么 / 说了什么）；
          · 没事件就维持原来那个 —— 读者会把它读成"关系变了"，而关系没变。

        ⚠ 认"对象"用 `to` 字段（主循环记的"这句话对谁说"）。没有 `to` 的句子
          （自言自语 / 对全场说）**不计** —— 那本来就没有称呼的对象。
        ⚠ 同一句里出现多个称呼词时取**第一个**（人开口只会先叫一声）。
        [EN] Which terms of address this person used for whom, with counts, sorted by count. The
        [EN] user's first complaint: "Jouji suddenly switches from 客人 to 岛村先生 -- **no setup at
        [EN] all**; a change of address must have emotional logic behind it". The countable shape is:
        [EN] **one speaker, one addressee, N different terms, and no event in between.** ⚠ "Addressee"
        [EN] comes from the `to` field; lines without `to` (soliloquy / to the room) are not counted,
        [EN] because there is no addressee to address. ⚠ Take the **first** term when several appear.
        """
        me = str(speaker or '').strip()
        if not me:
            return []
        # 人名来源：世界的人物表 **∪** 本场说过话的人。
        # ⚠ 只用 `people` 不够：整理/审读路径上可能拿到一个没有人物表的世界
        #   （夹具、回放、单元测试），那时 `岛村先生` 会被切成 `先生`，
        #   改口这件事就看不见了 —— 而判据仍然是绿的。
        # [EN] Names come from the world's cast **∪** everyone who spoke this scene. Using `people`
        # [EN] alone is not enough: fixture / replay / unit-test paths may have no cast table, and
        # [EN] then 「岛村先生」 is cut to 「先生」 -- the re-addressing disappears while the criterion
        # [EN] stays green.
        # ⚠ `who` **和 `to` 都要收**：`to` 是"这句话对谁说"，被称呼的人往往只出现在那里
        #   （他可能整场没开过口，所以从 `who` 收不到他）。
        # [EN] Collect **both** `who` and `to`: `to` says who was addressed, and that person may
        # [EN] never have spoken all scene, so `who` alone misses him.
        _names = set(getattr(self, 'people', {}) or {})
        for _r in (self.recent_lines or []):
            for _k in ('who', 'to'):
                _w = str(_r.get(_k) or '').split('（', 1)[0].split('(', 1)[0].strip()
                if _w:
                    _names.add(_w)
        counts: dict[tuple[str, str], int] = {}
        order: list[tuple[str, str]] = []
        for r in reversed(list(self.recent_lines or [])):
            if str(r.get('kind') or '') not in self.SPEAK_KINDS:
                continue
            who = str(r.get('who') or '').split('（', 1)[0].split('(', 1)[0].strip()
            if who != me:
                continue
            to = str(r.get('to') or '').strip()
            to = to.split('（', 1)[0].split('(', 1)[0].strip()
            if not to or to == me:
                continue
            t = str(r.get('text') or '')
            # ⚠ **按"出现位置最靠前"挑，同位置时取更长的那个**（2026-10-19 实测）。
            #   第一版按词表顺序挑，而「先生」在词表里排在「客人」后面却位置更靠前
            #   ⇒ 「岛村先生，您还没休息呀？」被记成称呼「先生」，
            #   于是"客人 → 先生"看起来像一次无理由改口，而实际是同一个称呼被切断了。
            #   同位置取更长：`岛村先生` 里的 `先生` 与 `岛村`（若也在表里）不能各算一个。
            # [EN] Pick the term that appears **earliest**, and the longer one on a tie. The first
            # [EN] version walked the word list, so 「先生」 (later in the list, earlier in the text)
            # [EN] won over 「客人」 -- "岛村先生" got recorded as a switch to 「先生」, i.e. an
            # [EN] unexplained re-address that never happened.
            hit = self.detect_address(t, tuple(_names))
            if not hit:
                continue
            key = (to, hit)
            if key not in counts:
                order.append(key)
            counts[key] = counts.get(key, 0) + 1
            if sum(counts.values()) >= int(limit or 40):
                break
        if not counts:
            return []
        # 同一个对象的称呼**按次数降序**；次数相同的按出现顺序
        out = sorted(((to, w, n) for (to, w), n in counts.items()),
                     key=lambda x: (-x[2], order.index((x[0], x[1]))))
        return out

    def last_own_action(self, speaker: str) -> str:
        """这个人**最近一条动作**的原文（不含台词；只看当前这一幕的缓冲）。没有就返回空串。

        为什么需要它（2026-10-17 实测）
        ------------------------------
        拿真材料量出来的：**同一个角色会连着好几拍重演同一段动作**。
        「悬疑·更漏子」那一轮头三拍，主角把"拎桶进屋 → 倒水进铜壶 → 手指划过
        铜标尺 → 水面高了一截"演了三遍（相似度 87% / 83%），只是每遍换几个字。
        「某楼」那边也一样（乙"靠在墙根蹭墨盒"两拍重复，65%）。

        `[刚才]` 那一段里其实**有**他自己的动作（`- （你做了X）`），但它只给
        `DIALOGUE_CONTEXT_LINES`（默认 6）条，一拍里七个人各说一句就把它挤出去了 ——
        于是下一拍他手上只剩"我的目标"，又把刚做过的事做了一遍。

        所以单独取一条、"指名道姓"地摆在提示词里，并明写**别重演**
        （见 `agent/core.py` 里拼 `[你上一拍做的]` 那段）。
        `who` 可能带后缀（`阿九（别处）`），这里先剥掉括号再比，否则"在别处"
        做的动作就查不到、照样重演。

            English:
        This person's **most recent action** text (no dialogue, any scene). Empty if none.
            Why (measured 2026-10-17)
            ------------------------------
            Measured on real material: **the same character replays the same action across
            consecutive beats**. In the "mystery / water clock" run, the first three beats had
            Shen Yan perform "carry the bucket in -> pour into the bronze vessel -> run a finger
            along the scale -> the water is a notch high" three times (similarity 87% / 83%),
            only rewording slightly. The "Mowen Tower" run showed the same (Zhu Bi leaning on the
            wall rubbing his ink box twice, 65%).
            That segment **does** contain his own action (`- (you did X)`), but it only yields
            `DIALOGUE_CONTEXT_LINES` (default 6) entries -- seven people speaking one line each in
            a beat pushes it out, so next beat he only has "my goal" and redoes what he just did.
            Hence a dedicated single line, addressed to him, plus an explicit "don't replay it"
            (see the `[你上一拍做的]` block in `agent/core.py`).
            `who` may carry a suffix (`阿九（别处）`); strip the parentheses before comparing,
            otherwise actions performed "elsewhere" are not found and the replay continues.
        """
        me = str(speaker or '').strip()
        if not me:
            return ''
        # ⚠ **只认动作型**（不是"跳过 speak"）。第一版写成"kind != speak 就算"，
        #   实测把 `aside`（心声）也取了回来 —— 心声是**没人看见的内心活动**，
        #   拿它去防"动作重演"没有意义，还会把"我刚想过什么"当成"我刚做过什么"
        #   喂回去（模型就会以为那件事已经发生）。
        # ★★ 2026-10-18：动作型这一族改成**类属性** `ACT_KINDS`，并补上生产侧真写的
        #   `'act'`。原来这里写的是 `'action'`（产品从不写这个字符串），
        #   于是这道"防重演"从来没取到过东西 —— 见 `ACT_KINDS` 上面那段。
        # [EN] ⚠ **Only action-type kinds** (not "skip speak"). The first version took anything with
        # [EN] `kind != speak`, and measured it grabbed `aside` (inner voice) too -- that is unseen
        # [EN] inner activity, useless for anti-replay, and feeding "what I just thought" back as
        # [EN] "what I just did" makes the model believe it already happened.
        # [EN] ★★ 2026-10-18: the action family became the **class attribute** `ACT_KINDS`, with the
        # [EN] `'act'` the production side actually writes added. It used to say `'action'` (a string
        # [EN] the product never writes), so this anti-replay path never fetched anything -- see the
        # [EN] note above `ACT_KINDS`.
        act_kinds = self.ACT_KINDS
        for r in reversed(self.recent_lines or []):
            who = str(r.get('who') or '').strip()
            # 剥掉「（别处）」这类后缀再比 —— 见上面那段说明
            # [EN] Strip a "（elsewhere）"-style suffix before comparing -- see the note above
            plain = who.split('（', 1)[0].split('(', 1)[0].strip()
            if who != me and plain != me:
                continue
            if str(r.get('kind') or '') not in act_kinds:
                continue
            t = str(r.get('text') or '').strip()
            if t:
                return t
        return ''

    def last_own_lines(self, speaker: str, limit: int = 2) -> list[str]:
        """这个人**最近说过的几句台词**（旧→新，最多 `limit` 句）。没有就返回空列表。

        为什么必须单独取（2026-10-18，与 `last_own_action` 同源同因）
        ----------------------------------------------------------
        防重演原来只管"动作"：`last_own_action` 只成对取动作型 kind。
        于是**跨拍复读台词**没人管 —— 实测（`ltxz-01`，豆包当演员）：
        6 次决策里有 **4 次是同一句台词**「祥子，你那车份儿打算拖到什么时候？」。
        豆包单次输出只有 100–160 token，不会自己换花样；hy3 输出 2900+ token
        把这道缝遮住了 —— 所以这是**模型无关**的缺陷，只是短输出的模型先露出来。

        交给提示词时明写"别再说一遍、也别换个说法说同一件事"
        （见 `agent/core.py` 里拼 `[你上一拍说的]` 那段）。

        ⚠ **只取 `speak`**：`aside`（心声）不是"说出口的话"，喂回去会让模型
          以为"我心里那句话已经讲出来了"。
        ⚠ 名字可能带后缀（`阿九（别处）`）—— 与 `last_own_action` 同一套剥法。

            English:
        The few lines this person **said most recently** (old -> new, at most `limit`). Empty list
        if none.
            Why this needs its own accessor (2026-10-18, same origin and cause as
            `last_own_action`)
            ----------------------------------------------------------
            Anti-replay only covered "actions": `last_own_action` takes action-type kinds only.
            So **cross-beat dialogue repetition** was nobody's job -- measured (`ltxz-01`, Doubao as
            actor): **4 of 6 decisions were the same line** ("Xiangzi, when are you going to pay the
            cart rent?"). Doubao emits only 100-160 tokens and will not vary on its own; hy3 emits
            2900+ and hid the seam -- so this is a **model-independent** defect, the short-output
            model just exposes it first.
            When handed to the prompt it says "don't say it again, and don't reword the same thing"
            (see the `[你上一拍说的]` block in `agent/core.py`).
            ⚠ **`speak` only**: `aside` (inner voice) is not something "said out loud"; feeding it
            back makes the model believe "that line in my head has already been spoken".
            ⚠ The name may carry a suffix (`阿九（别处）`) -- same stripping as `last_own_action`.
        """
        me = str(speaker or '').strip()
        if not me:
            return []
        n = int(limit or 2)
        if n <= 0:
            return []
        out: list[str] = []
        for r in reversed(self.recent_lines or []):
            who = str(r.get('who') or '').strip()
            plain = who.split('（', 1)[0].split('(', 1)[0].strip()
            if who != me and plain != me:
                continue
            if str(r.get('kind') or '') not in self.SPEAK_KINDS:
                continue
            t = str(r.get('text') or '').strip()
            if t and t not in out:
                out.append(t)
            if len(out) >= n:
                break
        return list(reversed(out))

    def own_actions(self, speaker: str, limit: int = 4) -> list[str]:
        """这个人**在这一场里已经做过的几件事**（旧→新，最多 `limit` 条）。

        为什么还要它（`last_own_action` 已经有了，2026-10-18 实测）
        --------------------------------------------------------
        `last_own_action` 只给**上一拍那一条**。可是《雪国》复测里，
        同一个"招牌动作"是隔一拍又来的：

          · 叶子第三次"端酒壶过来"（前两次换了说法）；
          · 驹子第二次"脸埋进臂弯"（第二句只多了一个"又"字）。

        这种重复**换了个说法**，文字相似度只有 0.5 上下，`near_same` 抓不到；
        但人一眼就看出来"她刚才做过这个"。所以把**这一场他做过的几件事**
        一起摆出来 —— 模型看得见"这场我已经端过两次酒了"。

        ⚠ 只看当前这一幕：换场之后本来就该从头来过（`clear_lines` 会清）。
        ⚠ 只取动作，不取台词/心声（台词走 `last_own_lines`）。
        [EN] The few things this person **has already done in this scene** (old -> new, at most
        [EN] `limit`). Why, when `last_own_action` exists (measured 2026-10-18): that one only returns
        [EN] **the previous beat's single entry**, while in the Snow Country re-run the "signature
        [EN] action" came back one beat later, reworded -- Yoko carrying the wine flask for a third
        [EN] time, Jouji burying her face in the crook of her arm for a second time with "again".
        [EN] Text similarity is only around 0.5 there, so `near_same` cannot catch it, yet a human
        [EN] spots "she did that a moment ago" instantly. So lay out **the things he did this scene**
        [EN] and let the model see "I have already carried the wine twice".
        [EN] ⚠ Current scene only (a new scene starts fresh; `clear_lines` empties the buffer).
        [EN] ⚠ Actions only, no dialogue or inner voice (dialogue goes through `last_own_lines`).
        """
        me = str(speaker or '').strip()
        n = int(limit or 4)
        if not me or n <= 0:
            return []
        out: list[str] = []
        for r in reversed(self.recent_lines or []):
            who = str(r.get('who') or '').strip()
            plain = who.split('（', 1)[0].split('(', 1)[0].strip()
            if who != me and plain != me:
                continue
            if str(r.get('kind') or '') not in self.ACT_KINDS:
                continue
            t = str(r.get('text') or '').strip()
            if t and t not in out:
                out.append(t)
            if len(out) >= n:
                break
        return list(reversed(out))

    def recent_text(self, *, speaker: str = '', limit: int = 0,
                    here_only: bool = True) -> str:
        """拼成决策提示词里的 `[刚才]` 那一段（没有内容就返回空串）。

        · `here_only=True`（默认）**只取当前场景的** —— 隔壁地点说的话，
          站在这里的人听不见。这条不加的话，换场之后人物会"记得"他没听见的话，
          那比"看不到"更坏（像穿帮）。
        · 说话人是自己 → 写「你刚说」；有人**冲着你说** → 写「X 对你说」。
          这两种标法是有用的：前者让他别重复自己刚说过的话，
          后者告诉他**这句是在等你回话**。
        · 最新的在最后（读起来是时间顺序）。
        
                English:
        Splice into the `[刚才]` section of the decision prompt (returns empty string if no content).
                · `here_only=True` (default) **only takes the current scene's** —— words spoken at a neighboring location
                  cannot be heard by those standing here. If this is not added, after switching scenes a character will "remember" words he didn't hear,
                  which is worse than "not seeing" (like a continuity error).
                  These two notations are useful: the former keeps him from repeating what he just said,
                  the latter tells him **this sentence is waiting for your reply**.
                · The latest is last (reads in chronological order).
        """
        limit = int(limit or self.RECENT_LINES_SHOW)
        here = str(self.scene or '').strip()
        rows = []
        for r in (self.recent_lines or []):
            if here_only and str(r.get('place') or '').strip() != here:
                continue
            rows.append(r)
        rows = rows[-limit:]
        if not rows:
            return ''
        me = str(speaker or '').strip()
        out: list[str] = []
        for r in rows:
            who = str(r.get('who') or '').strip()
            text = str(r.get('text') or '').strip()
            mine = bool(me) and who == me
            if str(r.get('kind') or '') != 'speak':
                out.append(f'- （{"你" if mine else (who or "有人")}{text}）')
                continue
            if mine:
                out.append(f'- 你刚说：「{text}」')
            elif me and str(r.get('to') or '').strip() == me:
                out.append(f'- {who or "有人"}对你说：「{text}」')
            else:
                to = str(r.get('to') or '').strip()
                out.append(f'- {who or "有人"}对{to}说：「{text}」' if to
                           else f'- {who or "有人"}：「{text}」')
        return '\n'.join(out)

    def clear_lines(self) -> None:
        """清空（换场时调）—— 换了地方，上一场的话就不该再挂在眼前了。

        ★★★ 2026-10-18：**清掉 `[刚才]` 之前，先把"没谈完的那件事"留下来**。
          用户原话：「出场人物应该是在一个场景里 围绕一个事情或者主题对话
          而且场景本身的迁移和场景之间的话题主题之间的延续性也是必须要注意的
          大的故事应该有一个接一个的小故事组成 小故事则有一个接一个的场景组成
          这之间除非有特殊的安排 比如剧情跳跃或者故意简略 否则应该都是有连续性的」。

          ⚠ 为什么这是必需的：`recent_text()` **按地点过滤**，换场后本来就是空 ——
            于是新场的第一拍，演员**什么上下文都没有**，只能自己开一个话题。
            那不是"新场开始"，那是"三条线从头再来一遍"（实测雪国接话率 0.27）。
          ⇒ 清空时把 `topic` / `topic_open_with` 留成"上一场留下的"，
            由 `agent/core.py` 的 `[这一段在谈的]` 在**新场的第一拍**递给演员，
            写成"上一场还没说完的是……"，让他们接着往下谈。
          ⚠ 只在**换场**这条路上留；收工时由 `reset_topic()` 清（那才是真的结束）。
        [EN] ★★★ 2026-10-18: **before clearing `[just now]`, keep "the unfinished thing"**.
        [EN] User: "the cast should be in one scene, talking around one matter or topic; and the
        [EN] migration of scenes and the continuity of topics between scenes must be handled; a big
        [EN] story is made of small stories, a small story of scenes, and unless there is a special
        [EN] arrangement (a jump, a deliberate elision) they should be continuous".
        [EN] ⚠ Why mandatory: `recent_text()` **filters by place**, so after a scene change it is
        [EN] already empty -- the first beat of the new scene has **no context at all**, and the
        [EN] actors can only open a topic of their own. That is not "a new scene", it is "three
        [EN] storylines starting over" (measured 0.27 reply rate).
        [EN] => On clearing, keep `topic` / `topic_open_with` as "left over from the previous
        [EN] scene", and `[这一段在谈的]` hands it to the actors **on the first beat of the new
        [EN] scene** as "what the previous scene had not finished". Only kept on the **scene
        [EN] change** path; `reset_topic()` clears it at wrap-up (that is the real end).
        [EN] ★★★ 2026-10-18 evening: **also remember the last visible line** (`last_beat_text`).
        [EN] Why: the aftermath (#7 Swain) needs "the last thing that happened", but
        [EN] `_note_aftermath` runs *after* the scene change, when `recent_lines` is **already
        [EN] empty** => the "reaction" was always missing (measured: only the "dilemma" survived).
        [EN] `clear_lines` is exactly the place that still has the data, so it keeps one string;
        [EN] assembling the sequel beats stays in `sim/loop._note_aftermath` (one responsibility each).
        """
        # ★★★ 清之前**记住最后一条看得见的**（台词或动作的原样），给"上一场的余波"用。
        #   ⚠ 只记一条、只在这里记：余波要的是"最后那一下"，不是这一场的全文。
        # [EN] ★★★ Before clearing, **remember the last visible line** (verbatim) for the aftermath.
        # [EN] ⚠ One line only, recorded here only: the aftermath needs "the last beat", not the whole
        # [EN] scene.
        try:
            for r in reversed(list(self.recent_lines or [])):
                txt = str((r or {}).get('text') or '').strip()
                if txt:
                    self.last_beat_text = txt[:120]
                    break
        except Exception:                                        # noqa: BLE001
            pass
        self.recent_lines = []



    # ══════════════════════════════════════════════════════════
    #  ★★★ 信息差：这个人**不知道**什么（2026-10-18）
    # [EN] ★★★ Information asymmetry: what this person does **not** know (2026-10-18)
    # ══════════════════════════════════════════════════════════
    #  专业论述：戏剧反讽 / 希区柯克"桌下炸弹" —— 读者比人物多知道一点，
    #  同一句闲话才变得可怕。反过来用：**人物之间各知一半**，对话才有试探与闪躲。
    #
    #  为什么"算"而不是"写"：每个人的秘密已经在设定里了（`secret`），
    #  "谁知道"只需一条规则（`knows` 列了才算知道，否则只有本人）。
    #  再让模型去填一张"信息矩阵"是白花钱，而且会漂。
    def blind_spots(self, me: str) -> list[str]:
        """这个人**还不知道**的事（别人的秘密里，他不在知情名单中的那些）。

        返回的是**当事人的名字**，不是秘密内容 ——
        ⚠ 这一点是有意的：他知道"某人瞒着事"，但**不知道瞒的是什么**。
          把内容递给他，等于让所有秘密当场公开（那比"不知道"更糟）。
        [EN] What this person does **not** yet know (other people's secrets where he is not on the
        [EN] knower list). Returns the **owner names**, not the content.
        [EN] ⚠ Deliberate: he knows "someone is hiding something" but **not what** -- handing him the
        [EN] content would publish every secret on the spot, which is worse than not knowing.
        """
        out: list[str] = []
        for name, ps in (self.people or {}).items():
            if name == me:
                continue
            if not str(getattr(ps, 'secret', '') or '').strip():
                continue
            knowers = [str(x) for x in (getattr(ps, 'knows', None) or [])]
            if me not in knowers:
                out.append(name)
        return out

    def secret_of(self, name: str) -> str:
        """某个人的秘密**内容**（只给审读用，不给别的演员）。"""
        ps = (self.people or {}).get(name)
        return str(getattr(ps, 'secret', '') or '') if ps else ''

    def leaks(self, text: str, me: str) -> str:
        """这句话里**泄露了谁的秘密**：返回那个人的名字，没有就返回空串。

        ⚠ 判法保守（宁可漏，不可误报）：只认"秘密里那些**少见的实词**"出现在话里。
          常见的虚词/人名一律不认（否则每句话都在"泄露"）。
        [EN] Whose secret does this line leak: returns the name, or '' if none.
        [EN] ⚠ Conservative: only **distinctive content words** from the secret count; common
        [EN] function words and names never do (otherwise every line "leaks" something).
        """
        t = str(text or '')
        if not t:
            return ''
        for name, ps in (self.people or {}).items():
            if name == me:
                continue
            sec = str(getattr(ps, 'secret', '') or '').strip()
            if len(sec) < 4:
                continue
            knowers = [str(x) for x in (getattr(ps, 'knows', None) or [])]
            if me in knowers:
                continue          # 他知道，说了不算泄露
            if _shared_run(sec, t) >= _LEAK_MIN:
                return name
        return ''

    def reset_topic(self) -> None:
        """收工时清掉"这一段在谈什么"（换场**不**清，见 `clear_lines` 的说明）。"""
        self.topic = ""
        self.topic_open_with = ""
        self.topic_run = 0
        # 余波也是"这一场的事" —— 收工才算真的结束（与 topic 同一个口径）。
        # [EN] The aftermath belongs to "this scene" too -- cleared only at wrap-up (same rule).
        self.aftermath = {}

    def note_craft(self, names) -> None:
        """记下"这一拍读了哪几条手艺"（调度器用它把新条目排前面）。

        ⚠ 有上限：`craft_read` 无上限会一路涨（存档变大、判据读不动）。
          超了就丢最老的 —— 那些早就不在"最近几拍"的范围里了。
        [EN] Record which craft entries were read this beat. ⚠ Capped: unbounded growth bloats the
        [EN] save and slows criteria; the oldest are dropped.
        """
        maxn = 40
        cur = list(getattr(self, 'craft_read', None) or [])
        for n in (names or ()):
            s = str(n or '').strip()
            if s and s not in cur:
                cur.append(s)
        if len(cur) > maxn:
            cur = cur[-maxn:]
        self.craft_read = cur

    def get_person(self, name: str) -> PersonState | None:
        return self.people.get(name)

    def add_person(self, ps: PersonState) -> None:
        self.people[ps.name] = ps

    def tick(self, minutes: int = 1) -> None:
        self.clock = self.clock.add(minutes)

    def world_prefix_stable(self) -> str:
        """**整轮不变**的那一段：顶级规则 + 类型卡 + 风格。

        ★★ 2026-10-07 第八轮拆出来的（为了**前缀缓存**）。

        为什么要拆：`world_prefix()` 的输出里有**每天/每场都在变**的东西
        （分层设定按天/场景/在场名单筛、本幕提示按场变），而它在提示词里
        排在**最前面**。前缀缓存是"逐 token 比对最长公共前缀、从第一个不同的
        token 起后面全部按未缓存价重算"—— 也就是说：前缀里有一个会变的字，
        后面几千 token 就全部按全价付。参考《AI Agent 从入门到精通》第九章
        §9.10「缓存友好：把前缀钉死，把要紧的话放在两端」：
        里面量过"系统提示开头放一个精确到秒的时间戳"会让命中率从 52% 掉到 **0%**。

        这一段的三个部分都**只跟这本书有关**（作者写死的规则、类型卡、
        风格卡），一轮里一个字节都不变 —— 所以它可以是真正的前缀，
        而且**十二个人物共用同一段**（cache 命中一次、全员复用）。

        ⚠ `world_prefix()` 的行为**一个字都没变**（它返回 `stable + live`）——
          这个方法是**新增的另一条路**，旧调用方与旧判据一概不受影响。
        
                English:
        The section that is **invariant across the whole round**: top-level rules + type cards + style.
                ★★ Split out in the eighth round on 2026-10-07 (for **prefix caching**).
                Why split: the output of `world_prefix()` contains things that **change every day/every scene**
                (tiered settings filtered by day/scene/present list, this act's hints change per scene), and it is placed
                **at the very front** of the prompt. Prefix caching is "compare token by token for the longest common prefix, and from the first differing
                token onward everything is recomputed at the uncached price" —— that is: if there's one changing character in the prefix,
                the following several thousand tokens are all paid at full price. Reference《AI Agent 从入门到精通》Chapter 9
                §9.10 "Cache-friendly: pin down the prefix, put the important words at both ends":
                Measured inside: "putting a timestamp precise to the second at the start of the system prompt" drops the hit rate from 52% to **0%**.
                All three parts of this section are **only related to this book** (author-hardcoded rules, genre card,
                style card); not a single byte changes within a round -- so it can be a true prefix,
                and **all twelve characters share the same section** (cache hit once, reused by everyone).
                ⚠ The behavior of `world_prefix()` **has not changed one bit** (it returns `stable + live`) --
                  this method is **a newly added separate path**; old callers and old criteria are entirely unaffected.
        """
        parts: list[str] = []
        if self.rules_text:
            parts.append(f"[顶级规则·不可违背]\n{self.rules_text[:2000]}")
        canon = self._prefix_canon()
        if canon:
            parts.append(canon)
        g = self.genre_card
        if g:
            parts.append(f"[类型] {g.get('主题材', '')}·{g.get('结构', '')}·{g.get('频道', '')}")
        parts.extend(self._style_lines())
        # ★ 2026-10-21：**表演备注进演员前缀**（写作层规则**不**进，见 `writer_notes`）。
        #   两份文件分开存，就是为了让「成品要求」与「动作要求」各走各的路。
        # [EN] ★ 2026-10-21: **performance notes go into the actor prefix** (writing-layer rules
        # [EN] do **not**, see `writer_notes`). Two separate files so that "finished-form" and
        # [EN] "actionable" requirements take separate paths.
        if str(self.actor_notes or '').strip():
            parts.append(str(self.actor_notes).strip()[:1500])
        return "\n".join(parts)

    def world_prefix_live(self) -> str:
        """**每场戏都可能变**的那一段：主线 / 此处 / 小事（按天·场景·在场筛）+ 本幕提示。

        它必须排在稳定前缀**之后**（见 `world_prefix_stable` 的说明）——
        排在前面前缀缓存就废了。
        
                English:
        The section that **can change every scene**: mainline / here / small matters (filtered by
        day·scene·presence) + current act hints.
                It must be placed **after** the stable prefix (see the note on `world_prefix_stable`) --
                if placed before, the prefix cache is ruined.
        """
        parts: list[str] = []
        rest = self._prefix_rest_layers()
        if rest:
            parts.append(rest)
        if self.scene_hint:
            # 本幕提示（`SCENE_START_HINT`）：作者对"这场戏该怎么起"的一句话交代。
            # [EN] This-act hint (`SCENE_START_HINT`): the author's one-line instruction on "how this scene should
            # [EN] start".
            parts.append(f"[本幕提示] {self.scene_hint[:300]}")
        return "\n".join(parts)

    # ── 稳定 / 在变 的两半（给前缀缓存用，见 `world_prefix_stable`）──
    # [EN] -- The two halves of stable / changing (for prefix caching, see `world_prefix_stable`) --
    def _layers_on(self) -> bool:
        """分层渲染这一轮开不开（没有索引、或作者关掉了，就返回 False）。
                English:
        Whether layered rendering is enabled this round (if no index, or the author turned it off,
        return False).
        """
        if not getattr(self, "layer_index", None):
            return False
        try:
            from config import CFG as _CFG
            return bool(_CFG.b("SETTING_LAYERS"))
        except Exception:                                       # noqa: BLE001
            return True

    def _prefix_canon(self) -> str:
        """**`[世界观]` 那一段** —— 它属于"稳定"那一半，理由要写清楚：

        | 情况 | 它变不变 |
        |---|---|
        | 没开分层（老做法 / 夹具） | 就是 `worldview_text[:500]`，**整轮一个字都不变** |
        | 开了分层 | 只有"展开日"（开篇 / 高潮日 / 每 3 天）才会从"一句气候"变成全量 —— **按天变，不按场变** |

        也就是说它比"主线 / 此处 / 小事"（按场景与在场名单筛，**每场都在动**）
        稳定得多。所以它跟规则、类型、风格一起放最前面当受保护的前缀，
        而后者排到它后面去。

        ⚠ 为什么不能干脆把它也挪去"在变"那一半（试过，被判据当场抓住）：
          `verify_context` 的 C2 盯着"**裁过之后，人格 / 世界观 / 顶级规则仍然在**"
          —— 那是设计稿 §2.4 定的契约（固定前缀永不裁）。
          世界观一旦进可裁层，额度紧的时候它就会**先被丢掉**，
          而那正是"人物开始出戏"的老毛病。
        
                English:
        **The `[世界观]` section** -- it belongs to the "stable" half; the reason must be stated clearly:
                | Case | Does it change |
                |---|---|
                | No layering (old approach / fixtures) | just `worldview_text[:500]`, **unchanged for the whole round** |
                | Layering on | only on "expansion days" (opening / climax day / every 3 days) does it change from "one-line climate" to full content -- **changes by day, not by scene** |
                That is, it is far more stable than "mainline / here / small matters" (filtered by scene and presence list, **moving every scene**).
                So it goes together with rules, genre, style at the very front as a protected prefix,
                and the latter are placed after it.
                ⚠ Why not just move it to the "changing" half as well (tried, caught on the spot by the criteria):
                  C2 of `verify_context` watches for "**after trimming, persona / worldview / top-level rules are still present**"
                  -- that is the contract set by design doc §2.4 (fixed prefix is never trimmed).
                  Once worldview enters the trimmable layer, it will be **dropped first** when budget is tight,
                  and that is exactly the old problem of "characters starting to break character".
        """
        if self._layers_on():
            try:
                from world import layers as _L
                return _L.render(self.layer_view(), include=('canon',)) or ''
            except Exception:                                   # noqa: BLE001
                return ''
        return f"[世界观] {self.worldview_text[:500]}" if self.worldview_text else ''

    def _prefix_rest_layers(self) -> str:
        """主线 / 此处 / 小事 —— 按天·场景·在场筛出来的那几层（**在变**的那半）。
                English:
        Mainline / here / small matters -- the layers filtered by day·scene·presence (**the changing
        half**).
        """
        if not self._layers_on():
            return ''
        try:
            from world import layers as _L
            return _L.render(self.layer_view(),
                             include=('arc', 'scene', 'detail')) or ''
        except Exception:                                       # noqa: BLE001
            return ''

    def world_prefix(self) -> str:
        """固定前缀（可缓存）：顶级规则 + 分层设定 + 当前类型卡 + 风格卡摘要。

        ★★ 2026-10-07 起改成**分层渲染**（见 `world/layers.py`）：
        以前这里是把 `worldview_text`（世界观 + 剧情参考线 + 地点 + 关系 + 伏笔
        拼成的一大坨）取**前 500 字**发出去 —— 于是

          · **大背景把小细节挤掉了**：世界铁律排在前面吃掉额度，而"东家那把壶
            缺个角"这种真正影响今天这场戏的东西根本排不上；
          · **每拍都重发一遍**：第 9 天的人物还在读第 1 页的世界观。

        现在：大背景平时只给 `CANON_BRIEF`（一句"气候"），只在
        **开篇 / 高潮日 / 每 3 天**这些特定时候展开（`should_expand`）；
        主线、此处（地点/关系）、小事（细节层）各自按**场合/在場的人/时间**
        筛完再给。标签保持 `[世界观]` 不变（五支验证脚本靠它做断言）。

        ⚠ **索引为空就退回老行为**（`worldview_text[:500]`）——
          直接 `WorldState()` 造出来的夹具不受影响；`SETTING_LAYERS=false`
          也是这条退路（作者想关掉分层时，行为与从前一模一样）。

        带内容指纹缓存（2026-10-06）：一轮里这些字段基本是静态的，而它每拍、
        每个人物都要被拼一次。按内容判等而不是按"改没改过"，所以就算有人直接
        赋值也能立刻反映。

        ★ 缓存由 **`CONTEXT_CACHE`** 开关（设计稿 §2.4 说的"固定前缀可缓存"）——
        2026-10-06 之前这个旋钮零读取，缓存在代码里是**无条件**开的。
        关掉它的正经理由只有一个：调试"到底哪一段进了 prompt"时想要每次现拼。
        
                English:
        Fixed prefix (cacheable): top-level rules + layered settings + current genre card + style card
        summary.
                ★★ Changed to **layered rendering** as of 2026-10-07 (see `world/layers.py`):
                Previously this took `worldview_text` (a big blob of worldview + plot reference lines + locations + relationships + foreshadowing)
                and sent the **first 500 chars** -- so
                  · **Big background squeezed out small details**: world iron rules came first and ate the budget, while things like "the boss's teapot
                    is missing a corner" that actually affect today's scene could not fit at all;
                  · **Resent every beat**: day 9 characters were still reading the day 1 worldview.
                Now: normally the big background only gives `CANON_BRIEF` (a one-line "climate"), and only expands
                at specific times like **opening / climax day / every 3 days** (`should_expand`);
                mainline, here (location/relationship), small matters (detail layer) are each filtered by **occasion/people present/time**
                before being given. The label stays `[世界观]` unchanged (five verification scripts rely on it for assertions).
                ⚠ **If the index is empty, fall back to old behavior** (`worldview_text[:500]`) --
                  fixtures constructed directly with `WorldState()` are unaffected; `SETTING_LAYERS=false`
                  is also this fallback (when the author wants to turn off layering, behavior is exactly as before).
                Content-fingerprint caching (2026-10-06): within a round these fields are basically static, yet they are assembled once per beat
                and per character. Equality is judged by content rather than "was it modified", so even direct
                assignment is reflected immediately.
                ★ The cache is controlled by the **`CONTEXT_CACHE`** switch (the "fixed prefix is cacheable" from design doc §2.4) --
                before 2026-10-06 this knob was never read; caching was **unconditionally** on in the code.
                There is only one legitimate reason to turn it off: when debugging "which section actually entered the prompt" and wanting it freshly assembled each time.
        """
        key = self._prefix_key()
        cache_on = True
        try:
            from config import CFG as _CFG
            cache_on = _CFG.b("CONTEXT_CACHE")
        except Exception:                                       # noqa: BLE001
            cache_on = True
        cache = getattr(self, "_prefix_cache", None)
        if cache_on and cache is not None and cache[0] == key:
            return cache[1]

        # ★ 2026-10-07 第八轮：改成由 `stable + live` 两段拼出来 ——
        #   两段的划分见 `world_prefix_stable` / `world_prefix_live`。
        #   **输出与从前逐字相同**（只是内部换了写法），
        #   所以所有旧调用方与靠 `[世界观]`/`[顶级规则` 标签做断言的判据都不受影响。
        # [EN] ★ 2026-10-07 round eight: changed to be assembled from two segments `stable + live` --
        # [EN] the division of the two segments is in `world_prefix_stable` / `world_prefix_live`.
        # [EN] **Output is verbatim identical to before** (only the internal writing changed),
        text = "\n".join(x for x in (self.world_prefix_stable(),
                                     self.world_prefix_live()) if x)
        self._prefix_cache = (key, text)
        return text

    # ── 分层设定（`world/layers.py`，2026-10-07）─────────────────────────
    # [EN] -- Layered settings (`world/layers.py`, 2026-10-07) -------------------------
    def _prefix_key(self) -> tuple:
        """前缀的内容指纹。**多一样东西就要多一个字段** —— 漏一个就是
        "改了没反应"（缓存开关默认是开的）。
                English:
        Content fingerprint of the prefix. **One more item means one more field** -- miss one and it
        becomes
                "changed but no response" (the cache switch is on by default).
        """
        try:
            day = int(getattr(self, "game_day", 1) or 1)
        except (TypeError, ValueError):
            day = 1
        try:
            tension = float(getattr(self, "tension", 0.0) or 0.0)
        except (TypeError, ValueError):
            tension = 0.0
        crossed = False
        on_flag = True
        try:
            from world import layers as _L
            crossed = tension >= _L.EXPAND_TENSION
        except Exception:                                       # noqa: BLE001
            crossed = tension >= 0.7
        try:
            from config import CFG as _CFG
            # ⚠ **开关本身也是一个输入**：不把它算进指纹的话，关掉
            #   `SETTING_LAYERS` 之后还会命中缓存里那份**分层过的**文本
            #   —— 表现成"开关拨了没反应"。
            # [EN] ⚠ **The switch itself is also an input**: if you don't count it into the fingerprint, turning
            # [EN] off
            # [EN] `SETTING_LAYERS` will still hit the **layered** text in the cache
            # [EN] -- manifesting as "flipping the switch has no effect".
            on_flag = _CFG.b("SETTING_LAYERS")
        except Exception:                                       # noqa: BLE001
            on_flag = True
        return (self.rules_text, self.worldview_text,
                repr(self.genre_card), repr(self.style_card),
                self.style_source, self.style_custom, self.scene_hint,
                day, str(self.scene or ""), crossed, on_flag,
                tuple(self.on_stage_names()),
                len(getattr(self, "layer_index", None) or []),
                int(getattr(self, "_layer_stamp", 0) or 0))

    def _layer_prefix(self) -> str | None:
        """分层渲染那一段；**没有索引就返回 `None`**（调用方退回老做法）。
                English:
        The layered rendering section; **returns `None` if there is no index** (caller falls back to the
        old approach).
        """
        idx = getattr(self, "layer_index", None)
        if not idx:
            return None
        try:
            from config import CFG as _CFG
            if not _CFG.b("SETTING_LAYERS"):
                return None
        except Exception:                                       # noqa: BLE001
            pass
        from world import layers as L
        day = int(getattr(self, "game_day", 1) or 1)
        text, _view = L.prefix_block(
            idx, day=day, scene=str(self.scene or ""),
            people=self.on_stage_names(),
            tension=float(getattr(self, "tension", 0.0) or 0.0),
            first=day <= 1)
        return text

    def layer_view(self):
        """这一刻生效的分层条目（`LayerView`）。界面/验证脚本用它。
                English:
        The layered entries in effect at this moment (`LayerView`). Used by UI/verification scripts.
        """
        from world import layers as L
        idx = getattr(self, "layer_index", None) or []
        day = int(getattr(self, "game_day", 1) or 1)
        return L.select(idx, day=day, scene=str(self.scene or ""),
                        people=self.on_stage_names(),
                        tension=float(getattr(self, "tension", 0.0) or 0.0),
                        first=day <= 1)

    def canon_expanded(self) -> bool:
        """这一刻大背景是不是展开状态（界面可以用来解释"今天为什么长"）。
                English:
        Whether the big background is expanded at this moment (UI can use it to explain "why today is
        long").
        """
        from world import layers as L
        day = int(getattr(self, "game_day", 1) or 1)
        return L.should_expand(day=day,
                               tension=float(getattr(self, "tension", 0.0) or 0.0))

    def rebuild_layers(self) -> list:
        """按当前设定集 + 剧组新增的局部设定，重编分层索引。

        调用点：装配时一次 · 剧组会审收下新设定之后（`layers.add_local`）。
        **每次都要让缓存失效** —— 不然新设定要等到下一次缓存自然过期才生效，
        表现成"剧组说了，人物当没听见"。
        
                English:
        Rebuild the layered index from the current setting set + locally added settings from the crew.
                Call sites: once at assembly time · after the crew review accepts new settings (`layers.add_local`).
                **The cache must be invalidated every time** -- otherwise new settings only take effect after the next natural cache expiry,
                manifesting as "the crew said it, but the characters acted as if they did not hear it".
        """
        from world import layers as L
        settings = getattr(self, "_layer_settings", None)
        local = [i for i in (getattr(self, "local_settings", None) or [])]
        self.layer_index = L.build_index(settings or {}, local=local)
        self._layer_stamp = int(getattr(self, "_layer_stamp", 0) or 0) + 1
        self._prefix_cache = None
        return self.layer_index

    def _style_lines(self) -> list[str]:
        """风格那一行（按 `style_source` 分三种情况）。

        ★ 三档的语义（`NOVEL_STYLE`，设计稿 §3.4）：
          · `auto`   —— 用抽出来的**风格卡**（正文统计 + LLM 归纳的那张）；
          · `plain`  —— **不写风格那一段**（朴素直叙）。别写成"style_card=''"
                        之外的东西，`plain` 的意思就是"别管我，照常说话"；
          · `custom` —— 用作者**手写**的 `style_custom`；
          · 其它取值（「冷笔白描」「华丽辞藻」这类风格名）→ 直接当风格名用，
            风格卡里那些统计值仍然附在后面（两个都要，不互相顶掉）。
        
                English:
        The style line (handled in three cases based on `style_source`).
                ★ Semantics of the three options (`NOVEL_STYLE`, design doc §3.4):
                  · `auto`   —— use the extracted **style card** (the one from text statistics + LLM summarization);
                  · `plain`  —— **do not write the style paragraph** (plain narration). Don't write it as anything other than "style_card=''"
                                , the meaning of `plain` is "don't mind me, speak as usual";
                  · `custom` —— use the author's **hand-written** `style_custom`;
                    the statistics from the style card are still appended afterwards (both are kept, they don't override each other).
        """
        src = (self.style_source or "auto").strip()
        s = self.style_card if isinstance(self.style_card, dict) else {}
        if src == "plain":
            return []
        if src == "custom":
            txt = (self.style_custom or "").strip()
            return [f"[风格] {txt[:600]}"] if txt else (
                ["[风格] （作者选了自定义风格，但自定义内容还没填）"])
        base = ""
        if s:
            base = (f"句长={s.get('句长', '')}，距离={s.get('叙事距离', '')}，"
                    f"禁词={','.join(str(x) for x in (s.get('AI腔禁词表') or [])[:5])}")
        if src and src != "auto":
            return [f"[风格] {src}" + (f"（{base}）" if base else "")]
        return [f"[风格] {base}"] if base else []

    def current_node_info(self) -> dict | None:
        for nd in self.progress_nodes:
            if nd.get("id") == self.current_node:
                return nd
        return None

    def style_control_summary(self) -> str:
        """风格控制摘要（用于主界面显示）。
                English:
        Style control summary (used for main UI display).
        """
        parts = []
        # 虐心程度
        # [EN] angst level
        if self.angst_level < 0.3:
            parts.append("甜")
        elif self.angst_level < 0.6:
            parts.append("小虐")
        elif self.angst_level < 0.8:
            parts.append("虐心")
        else:
            parts.append("大虐")

        # 幽默度
        # [EN] humor level
        if self.humor_level > 0.7:
            parts.append("搞笑")
        elif self.humor_level > 0.4:
            parts.append("轻松")

        # 爽点密度
        # [EN] payoff density
        if self.satisfaction_density > 0.7:
            parts.append("高爽")
        elif self.satisfaction_density < 0.3:
            parts.append("平淡")

        # 感情线
        # [EN] romance line
        if self.romance_ratio > 0.7:
            parts.append("言情")
        elif self.romance_ratio < 0.2:
            parts.append("无CP")

        # 悬念
        # [EN] suspense
        if self.suspense_density > 0.7:
            parts.append("悬疑")

        # 节奏
        # [EN] pacing
        if self.pacing_style == "fast":
            parts.append("快节奏")
        elif self.pacing_style == "slow":
            parts.append("慢热")
        elif self.pacing_style == "roller":
            parts.append("过山车")

        return "·".join(parts) if parts else "适中"

    def style_control_dict(self) -> dict:
        """风格控制参数字典。
                English:
        Style control parameter dictionary.
        """
        return {
            "虐心": f"{self.angst_level:.0%}",
            "幽默": f"{self.humor_level:.0%}",
            "爽点": f"{self.satisfaction_density:.0%}",
            "感情": f"{self.romance_ratio:.0%}",
            "悬念": f"{self.suspense_density:.0%}",
            "世界观": f"{self.worldbuilding_pace:.0%}",
            "智商": f"{self.character_iq:.0%}",
            "节奏": self.pacing_style,
        }