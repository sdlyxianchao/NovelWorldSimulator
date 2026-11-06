# -*- coding: utf-8 -*-
"""Agent 核心（设计稿 §五）：人格卡 / 记忆流 / 反思 / 计划 / 对话 / 决策。

一个 Agent = 一个人物。前台走完整 LLM 循环，后台走轻量摘要。

English:
Agent core (design doc §5): persona card / memory stream / reflection / plan / dialogue /
decision.
One Agent = one character. Foreground runs the full LLM loop, background runs lightweight
summaries.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

from llm.router import llm
from llm.replies import ask
from llm import models as MODELS
from world.state import PersonState, WorldState
from store.db import DB
from util.jsonio import extract_json, extract_json_lenient
from config import CFG

_LOG = __import__("logging").getLogger("nws.agent")

# ── 动作词汇表（§5 动作词汇表：限定动作集 + schema 校验）────────────────
# [EN] ── Action vocabulary (§5 Action vocabulary: limited action set + schema validation)
# [EN] ────────────────
VALID_ACTIONS = {"move", "speak", "interact", "emote", "wait", "think"}

#: `_tail` 里"输出格式"与"写作纪律"两段的分界标记（2026-11-01，为省钱重排用）。
#:
#: 为什么用**文本标记**而不是把 `_tail` 直接拆成两个字符串常量：
#:   `_tail` 是个大 f-string（里面全是 JSON 花括号转义），拆成两段等于把
#:   四十几行原文重抄一遍 —— 抄错一个字就是**静默改变提示词**，而这里
#:   恰恰要求"一个字都不改，只换位置"。标记切分能保证切出来的两段**原文等值**
#:   （判据 `verify_prefix_cache` E5 守着：切完拼回去必须与切之前逐字相同）。
#: ⚠ 标记必须在 `_tail` 里**恰好出现一次**，且**不能被注释吃掉**
#:   （`PROMPTS.strip_comments` 会剥掉以 `#` 开头的行 —— 所以标记行不能以 `#` 开头）。
# [EN] The boundary marker between the "output format" and "craft discipline" halves of `_tail`
# [EN] (2026-11-01, used by the cost-saving reorder).
# [EN] Why a **text marker** instead of splitting `_tail` into two string constants: `_tail` is a big
# [EN] f-string full of escaped JSON braces, so splitting it means retyping forty-odd lines -- one typo
# [EN] is a **silent prompt change**, and the whole point here is "not one character changes, only the
# [EN] position". Marker-splitting guarantees the two halves are **textually equal** to the original
# [EN] (guarded by E5 in `verify_prefix_cache`: re-joining must be byte-identical).
# [EN] ⚠ The marker must occur **exactly once** in `_tail` and must not be eaten by comments
# [EN] (`PROMPTS.strip_comments` strips lines starting with `#`, so the marker line cannot start with `#`).
_TAIL_RULE_MARK = "**这一拍要给的不只是话（重要）：**"

#: 「目标层级」那一块（`_tail` 里**唯一**按角色变化的三行）—— 重排时要把它从规则段
#: 里摘出来（它已经进了半固定层 `_ladder_blk`）。
#:
#: ⚠ 用 `{0,300}?` 而不是 `[\s\S]*?`：万一模板里的结尾那句被人改了措辞，
#:   非贪婪 `*?` 会**一路吃到文件末尾**，把后面所有纪律全删掉 —— 那是事故。
#:   限死 300 字，匹配不上就什么都不做（宁可重复一段，也不能吃掉别的内容）。
#: ⚠ 内置 f-string 里这三行是**手工删掉的**（它用 `%d` 拼、外层模板用 `{n_layers}`，
#:   两边措辞差一个空格）；这条正则主要给外置模板 `agent_decide_tail.txt` 用。
# [EN] The "goal ladder" block (the **only** per-character three lines inside `_tail`) -- when
# [EN] reordering it must be pulled out of the rules section (it already lives in the
# [EN] semi-fixed layer as `_ladder_blk`).
# [EN] ⚠ `{0,300}?` instead of `[\s\S]*?`: if someone rewords the closing sentence, the lazy
# [EN] `*?` would **eat all the way to the end of the file** and delete every rule after it -- an
# [EN] incident. Capped at 300 chars; no match ⇒ do nothing (better a duplicate block than
# [EN] eating real content).
# [EN] ⚠ In the built-in f-string these three lines are **removed by hand** (it uses `%d` while the
# [EN] outer template uses `{n_layers}`, so the wording differs by one space); this regex is mainly
# [EN] for the external `agent_decide_tail.txt`.
_TAIL_LADDER_RE = __import__("re").compile(
    r"\n?- \*\*推进你此刻最想推进的事。\*\*[\s\S]{0,300}?推动某个人。\n?")

#: 心理距离三档的写法（专业论述 #10，Cohn《透明的心灵》）。见 `_live_persona` 里的用法。
#:
#: 为什么三档**只换写法不换事实**：距离是"叙述站在哪儿看"，不是"发生了什么" ——
#: 一旦让它影响事实，就变成了"贴得近就多给情节"，那是另一码事（也是本项目
#: 反复栽的"渲染层做内容判断"那个坑）。
#:
#: ⚠ 「内心必须第一人称」那条硬规矩**在三档里都保留**（规则层 `ASIDE_RULES` 照旧拦）：
#:   这一条是"心声不能被写成第三人称旁白"，与"这一拍要不要写心声"是两件事。
# [EN] How the three psychological-distance grades are written (#10, Cohn). See `_live_persona`.
# [EN] Why the grades **change only the writing, never the facts**: distance is "where the narration
# [EN] stands", not "what happens" -- letting it affect facts turns into "close = more plot", which is
# [EN] the "rendering layer making content judgements" trap this project has fallen into.
# [EN] ⚠ The hard rule "inner voice must be first person" **holds in all three grades** (the rule
# [EN] layer `ASIDE_RULES` still blocks); that rule is about *how* it is written, not *whether*.
_DISTANCE_RULES: dict[str, str] = {
    '贴近': (
        '\n[这一拍的距离：贴近]\n'
        '- 心声写他自己的原话：短句、口语、不加"他想""她觉得"。\n'
        '- 只贴**这一处**（最难受/最要紧的那一下），别整段都贴着。\n'
        '- 心声仍然**必须第一人称**（"我不该来"），不是"她不该来"。'
    ),
    '中间': (
        '\n[这一拍的距离：中间]\n'
        '- 可以用他的判断词（"这不对""不该是这样"），但**不加引号、不写"他想"**。\n'
        '- 读者分不清那是他在想还是叙述在说 —— 这正是这一档要的效果。\n'
        '- 心声仍然**必须第一人称**，且不要超过两句。'
    ),
    '拉远': (
        '\n[这一拍的距离：拉远]\n'
        '- 这一拍**不必**写心声：只写别人看得见的东西（动作、表情、他做了什么）。\n'
        '- 要写的话，写他**没说出口的那半句**（"话到嘴边又咽了"），不写他心里的话。\n'
        '- ⚠ 不是禁止写内心，是**不要整段都往里钻** —— 这一段拉远，下一段才好贴。'
    ),
}


@dataclass
class Action:
    verb: str          # move/speak/interact/emote/wait/think
    target: str = ""
    dialogue: str = ""
    inner_thought: str = ""
    reason: str = ""
    #: ★ **思维链**（2026-10-07 第七轮）：开口之前那几句盘算（`crew/cognition`）。
    #: ⚠ 它是**给自己看的**，不是台词也不是心声 —— 所以三处地方**故意不收**它：
    #:   · 不进叙事/中栏（用户的中间栏白名单里没有它）；
    #:   · 不进 `world.recent_lines`（那是"场上刚发生"，是公开的）；
    #:   · 不进 `_mentioned_names` 的扫描文本（内部盘算里提到谁，不等于喊他上台）。
    #: 它的去处见 `sim/loop`：日志 · 重说上下文 · 剧组台账的演员行。
    # [EN] : ★ **Chain of thought** (2026-10-07 seventh round): the few lines of deliberation before
    # [EN] speaking (`crew/cognition`).
    # [EN] : ⚠ It is **for itself to see**, not a line and not an inner voice — so three places
    # [EN] **deliberately do not take it in**:
    # [EN] : · Not into the narrative/middle column (the user's middle-column whitelist does not contain
    # [EN] it);
    # [EN] :   · Not into `world.recent_lines` (that is "what just happened on stage", which is public);
    # [EN] : · Not into the scan text of `_mentioned_names` (mentioning someone in internal deliberation
    # [EN] does not equal calling them on stage).
    # [EN] : Where it goes, see `sim/loop`: log · retelling context · the actor row in the crew ledger.
    think_trace: str = ""
    #: ★★★ 2026-10-14（用户）：「我看现在的推演结果 是大量的对话 正常小说的话
    #: 应该有…人物做的事情」——
    #: **动作/神态的那一句描写**（`"细节": "他把茶碗端起来又放下，指节发白"`）。
    #:
    #: ⚠ 为什么必须新增这个字段（不是"顺手加的"）：`Action` 原来只有
    #:   `verb`/`target`/`dialogue`/`inner_thought` —— **没有地方放描写**。
    #:   于是模型无论多想写"他把碗推远了一点"，`emote`/`interact`/`move`
    #:   都只能落成 `_action_text` 的**骨架**（`神色变了变` / `转向X` / `去了X`）。
    #:   这是"推演结果里动作干瘪"的**结构性**原因，光改提示词救不回来
    #:   （模型没地方写）。
    #: ★ 与 `dialogue` 的分工：说话时的**随句小动作**仍写在台词圆括号里
    #:   （`"（把壶挪了挪）这事我不接。"`）—— 那是"说话的一部分"；
    #:   这个字段管**不说话时他在做什么**（包括神态、手头的事、走到哪儿、
    #:   注意到什么）。两者不重复填。
    # [EN] ★★★ 2026-10-14 (user): "I see the deduction output is mostly dialogue; a normal novel
    # [EN] should have ... things the characters do" --
    # [EN] **the one sentence describing the action / expression** (`"细节": "he picked the tea bowl
    # [EN] up and put it down, knuckles white"`).
    # [EN] ⚠ Why this field must be **added** (not "added in passing"): `Action` used to have only
    # [EN]   `verb`/`target`/`dialogue`/`inner_thought` -- **there was nowhere to put a description**.
    # [EN]   So no matter how much the model wanted to write "he nudged the bowl away", `emote` /
    # [EN]   `interact` / `move` could only fall back to `_action_text`'s **skeleton**
    # [EN]   (`expression shifted` / `turns toward X` / `went to X`).
    # [EN]   That is the **structural** reason "actions in the deduction output are thin", and
    # [EN]   changing only the prompt cannot fix it (the model has nowhere to write it).
    # [EN] ★ Division of labor with `dialogue`: the **incidental gesture while speaking** is still
    # [EN]   written inside the dialogue's parentheses (`"(nudged the pot) I won't take this."`) --
    # [EN]   that is "part of speaking"; this field covers **what he does while not speaking**
    # [EN]   (expression, work in hand, where he walks, what he notices). Do not fill both.
    detail: str = ""

    def is_valid(self) -> bool:
        return self.verb in VALID_ACTIONS

    def to_dict(self) -> dict:
        return {"动作": self.verb, "参数": {"目标": self.target},
                "台词": self.dialogue, "内心": self.inner_thought,
                # ★ 2026-10-14：`细节` 也要**回读得到** —— 这个 dict 用在
                #   "重说上下文"与剧组台账上；只加字段不回读，
                #   那些地方看到的还是"这个人什么都没做"。
                # [EN] ★ 2026-10-14: `细节` must also be **readable back** -- this dict is used for
                # [EN] the "retelling context" and the crew ledger; adding a field without reading
                # [EN] it back leaves those places still seeing "this person did nothing".
                "细节": self.detail,
                "理由": self.reason}


def idle_kind(action: "Action") -> str:
    """这个是"原地打转"吗？返回它的名字（不是就返回空串）。

    与 `sim/loop.is_noop()` 的分工 —— **别把两者合并**：
      · `is_noop` 判的是"值不值得写进叙事"（wait / 空 think）；
      · 这里判的是"这个人是不是在本该推进点什么的时候原地打转"，
        所以还要算上**没有目标的 `interact`**（"继续擦那件东西"就是这一种）。
    合并的话，叙事里会凭空多出一堆"某某在擦东西"。
    
        English:
    Is this "spinning in place"? Return its name (otherwise return empty string).
        Division of labor with `sim/loop.is_noop()` —— **don't merge the two**:
          · `is_noop` judges "is it worth writing into the narrative" (wait / empty think);
          · here it judges "is this person spinning in place when they should be pushing something forward",
            so it must also count **goal-less `interact`** ("keep wiping that thing" is this kind).
        If merged, the narrative would be flooded with a bunch of "so-and-so is wiping something".
    """
    verb = str(getattr(action, "verb", "") or "").strip()
    target = str(getattr(action, "target", "") or "").strip()
    if verb == "wait" and not str(getattr(action, "dialogue", "") or "").strip():
        return "wait"
    if verb == "think" and not str(getattr(action, "inner_thought", "") or "").strip():
        return "think"
    if verb == "interact" and not target:
        return "interact(无目标)"
    return ""


class Agent:
    """单个人物 Agent。
        English:
    A single character Agent.
    """
    def __init__(self, ps: PersonState, db: DB, world: WorldState):
        self.ps = ps
        self.db = db
        self.world = world
        self._memory_k = CFG.i("MEMORY_RETRIEVE_K")
        self._today_reflections = 0
        # 人格卡固定层的缓存（见 `_persona_prompt`）：key = 设定层字段的元组
        # [EN] Cache for the fixed layer of the persona card (see `_persona_prompt`): key = tuple of
        # [EN] setting-layer fields
        self._persona_key: tuple | None = None
        self._persona_static: str = ""
        #: 已经折过的那几段（键 = 原文 sha1）→ 摘要。
        #  为什么要缓存：块是**逐拍长大**的，同一个"较早那一段"会在接下来
        #  每一拍里被重新折一次 —— 不缓存就是每拍一次多余的模型调用，
        #  而且摘要叠摘要会越折越糊。
        # [EN] : The already-folded segments (key = sha1 of original text) → summary.
        # [EN] Why cache: blocks **grow beat by beat**, and the same "earlier segment" will be
        # [EN] re-folded on each following beat — without caching, that is one redundant model call per beat,
        # [EN] and summary over summary gets blurrier the more it folds.
        self._compact_cache: dict[str, str] = {}
        #: 上一次**主动压缩**留下的说明（`_compact_if_needed` 写）。
        #  Agent 自己没有向界面说话的路子（它不持有叙事通道），所以记在这儿，
        #  由主循环在那一拍结束时播报给作者 —— 见 `sim/loop._announce_compaction`。
        #  ⚠ 循环读完要清掉，否则会被反复播报。
        # [EN] : The note left by the last **active compression** (written by `_compact_if_needed`).
        # [EN] The Agent itself has no way to speak to the UI (it does not hold the narrative channel), so it
        # [EN] is recorded here,
        # [EN] and the main loop announces it to the author at the end of that beat — see
        # [EN] `sim/loop._announce_compaction`.
        # [EN] ⚠ Clear it after the loop reads it, otherwise it will be announced repeatedly.
        self.last_compaction: dict | None = None

    @property
    def name(self) -> str:
        return self.ps.name

    # ── 决策（前台，完整 LLM 循环）─────────────────────────────────────
    # [EN] ── Decision (foreground, full LLM loop) ─────────────────────────────────────
    @MODELS.agent('actor')
    async def decide(self, context: str = "") -> Action:
        """前台决策：观察→记忆→检索→(反思?)→计划→行动。
                English:
        Foreground decision: observe→remember→retrieve→(reflect?)→plan→act.
        """
        # ★ 2026-10-10：**在函数最开头**取一次剧组模块（"记忆是不可信史料"那两块
        #   规则常量在 `crew/agents.py`）。
        #   ⚠ 必须是**函数内**的 import（不是模块顶层）：`crew` 那一边会拉起一串
        #     依赖，放顶层有循环导入的风险。
        #   ⚠ 而且必须**放在使用之前** —— 第一版我把它写在下面 `_dyn` 那一行，
        #     而 `_semi` 在上面就先用了 `_AG`，于是 `_AG` 成了"赋值前引用的局部名"：
        #     `UnboundLocalError`，一次性打红三支判据（crew_flow / deai / casting）。
        # [EN] ★ 2026-10-10: Fetch the crew module once **at the very start of the function** (the two blocks
        # [EN] "memory is unreliable historical material"
        # [EN] rule constants are in `crew/agents.py`).
        # [EN] ⚠ It must be a **function-internal** import (not module top level): the `crew` side pulls up a
        # [EN] string of
        # [EN] dependencies, and putting it at top level risks circular imports.
        # [EN] ⚠ And it must be **placed before use** — in the first version I put it on the `_dyn` line below,
        # [EN] while `_semi` above used `_AG` first, so `_AG` became a "local name referenced before
        # [EN] assignment":
        # [EN] `UnboundLocalError`, turning three criteria red at once (crew_flow / deai / casting).
        from crew import agents as _AG                    # noqa: PLC0415
        # 检索记忆：**按故事时间**算新近度，query 走二元组相关性
        # [EN] Retrieve memory: recency is computed **by story time**, query uses bigram relevance
        memories = self.db.retrieve_memory(self.name, self._memory_k, context,
                                           now_game_min=self._game_min())
        mem_text = "\n".join(f"- [{m.get('type','?')}] {m['content']}" for m in memories[:5])

        # DEBUG: 记忆检索详情
        # [EN] DEBUG: memory retrieval details
        if CFG.b("DEBUG_MODE"):
            _LOG.debug("[%s] 决策开始，检索到 %d 条记忆", self.name, len(memories))
            for i, mem in enumerate(memories[:3]):
                _LOG.debug("  记忆[%d]: %s (重要性=%.1f)", i, mem.get("content", "")[:50], mem.get("importance", 0))

        # ★★ 世界观 / 类型卡 / 风格禁词 —— 2026-10-06 接上。
        # [EN] ★★ Worldview / genre card / style forbidden words — connected on 2026-10-06.
        #
        # `WorldState.world_prefix()` 早就写好了，但**从来没有被任何推演代码调用过**：
        # 开卷阶段花成本抽出来的世界观与风格卡，一到推演就全丢了。结果是角色只
        # 知道自己的名字、身份和最近五条记忆 —— 世界是什么样子、话该怎么说、
        # 哪些词是这本小说的忌讳，它一概不知。这是"人物在世界里空转"的根子。
        # [EN] `WorldState.world_prefix()` was written long ago, but **was never called by any simulation
        # [EN] code**:
        # [EN] the worldview and style card extracted at cost during the opening stage are all lost once
        # [EN] simulation starts. The result is that characters only
        # [EN] know their own name, identity, and the last five memories — what the world is like, how to
        # [EN] speak,
        # [EN] which words are taboo for this novel, it knows none of it. This is the root of "characters
        # [EN] spinning in a world they do not know".
        #
        # ⚠ 2026-10-07 第八轮**这里不再整段取** `world_prefix()`：
        #   它拆成了 `world_prefix_stable()`（进 P0）与 `world_prefix_live()`
        #   （进半固定层）两半，为的是前缀缓存能命中 —— 见下面 P0 那段说明。
        #   人格卡同理：不再取合并的 `persona`，只取它的固定层进 P0。
        # [EN] ⚠ 2026-10-07 eighth round: **here we no longer take the whole** `world_prefix()`:
        # [EN] it is split into `world_prefix_stable()` (into P0) and `world_prefix_live()`
        # [EN] (into the semi-fixed layer), so that the prefix cache can hit — see the P0 explanation below.
        # [EN] Same for the persona card: no longer take the merged `persona`, only take its fixed layer into
        # [EN] P0.

        # 当前场景
        # [EN] Current scene
        scene = f"场景：{self.world.scene}，时间：{self.world.clock_display()}，天气：{self.world.weather}"
        on_stage = ", ".join(self.world.on_stage_names())
        in_scene = f"在场人物：{on_stage}" if on_stage else ""

        # 前情提要（长期）+ **目标金字塔**（由近及远，层数见 `GOAL_LADDER`）——
        # 让"我这一拍该干什么、这一站要走完什么、我今天打算干什么"都在眼前。
        # [EN] Recap (long-term) + **goal pyramid** (near to far, number of layers see `GOAL_LADDER`) —
        # [EN] so that "what should I do this beat, what should be finished at this stop, what do I plan to do
        # [EN] today" are all in view.
        story_line = self._story_so_far()
        goal_line = self._goal_ladder()

        # ★ **导演提示**（2026-10-07）：导演盯戏查出来的问题（"好几个人各自
        #   独立说了同一件事""连着几拍在原地打转"）。**下一拍的每个人**都会看到
        #   —— 这是"要求演员修改"最省的做法：不额外调用，他自己下一次决策
        #   就会绕开。由 `sim/loop._tick` 保证它只活一拍（下一拍开头清掉）。
        # [EN] ★ **Director notes** (2026-10-07): problems found by the director watching the play ("several
        # [EN] people each
        # [EN] independently said the same thing" "several beats in a row spinning in place"). **Everyone in
        # [EN] the next beat** will see it
        # [EN] — this is the most economical way to "require actors to revise": no extra calls, and on their
        # [EN] next decision
        # [EN] they will avoid it themselves. `sim/loop._tick` ensures it lives only one beat (cleared at the
        # [EN] start of the next beat).
        _watch = str(getattr(self.world, 'watch_note', '') or '').strip()

        # ★★ **协调引擎对这演员的实时指令**（2026-10，运行窗口底部输入框的总调度）。
        #   从 `crew/coordinator.Coordinator` 单例**现读**：用户在运行窗口对 TA 说的话、
        #   或全局故事走向，下一拍就生效（不用重启）。全局指令对所有演员都生效，
        #   所以 `actor_directive(name)` 已经把「全局 + 这演员专属」拼好。
        #   ⚠ 惰性 import：协调引擎那一侧会拉 `llm.replies` / `crew.roster`，
        #     放这里只在真正要读时才触发，避免 `agent/core` 顶层 import 串出循环依赖。
        # [EN] ★★ **The Coordinator engine's real-time directive for this actor** (2026-10, the overall
        # [EN] scheduler behind the run-window bottom input box). Read **fresh** from the
        # [EN] `crew/coordinator.Coordinator` singleton: what the user said to this actor in the run window,
        # [EN] or the global story direction, takes effect on the next beat (no restart). The global directive
        # [EN] is effective for every actor, so `actor_directive(name)` already concatenates
        # [EN] "global + this-actor-specific".
        # [EN] ⚠ Lazy import: the Coordinator side pulls in `llm.replies` / `crew.roster`; importing it here
        # [EN] only triggers when actually needed, avoiding a circular import at `agent/core` top level.
        _coord = ''
        try:
            from crew import coordinator as _CO
            _coord = _CO.Coordinator.instance().actor_directive(self.name)
        except Exception:                                        # noqa: BLE001
            _coord = ''

        # ★★ **规定情境之"我身上有什么"**（2026-10-07 审计补上）。
        # [EN] ★★ **Given circumstances' "what I have on me"** (added in the 2026-10-07 audit).
        #
        # 斯坦尼体系里演员上场前要握住的几样：我是谁、在什么地方、
        # **身上穿着什么/带着什么**、周围有什么动静。前两样本项目一直有；
        # 后面这两样此前**算出来了却没送到人手上** —— 造型（`crew/agents.Stylist`）
        # 每天出工、每天落一份 `造型表.md`，而演员一个字都看不到，
        # 于是"同一件旧布衫三天三种写法"照旧发生。
        # [EN] In the Stanislavski system, an actor must grasp a few things before going on stage: who I am,
        # [EN] where I am,
        # [EN] **what I am wearing / carrying**, what is happening around me. This project has always had the
        # [EN] first two;
        # [EN] the latter two were previously **computed but not delivered to the person** — styling
        # [EN] (`crew/agents.Stylist`)
        # [EN] goes to work every day and drops a `造型表.md` every day, yet the actor sees not a word of it,
        # [EN] so "the same old cloth shirt written three different ways in three days" still happens.
        #
        # 它**不是目标**（不是"我想做什么"），所以不进目标金字塔，
        # 与场景/在场名单一样放**半固定层** —— 额度紧的时候它比记忆先保。
        # [EN] It is **not a goal** (not "what I want to do"), so it does not go into the goal pyramid,
        # [EN] and like scene/present list it goes into the **semi-fixed layer** — when budget is tight it is
        # [EN] preserved before memory.
        _look = str(getattr(self.world, 'stylist_brief', '') or '').strip()

        # 外部输入：门外/堂上有没有人、有没有人找上门（`world/crowd.py`）。
        # ★ 群演不是装饰，是"有事发生"的来源 —— 真机日志里那间茶楼
        #   "买 0、顾客 0"，人物只能内循环（看 627 次、擦 565 次）。
        # [EN] External input: whether there is anyone outside the door / in the hall, whether anyone comes
        # [EN] looking (`world/crowd.py`).
        # [EN] ★ Extras are not decoration, they are the source of "something happening" — in real-machine logs
        # [EN] that teahouse
        # [EN] "buys 0, customers 0", and the character can only loop internally (looking 627 times, wiping 565
        # [EN] times).
        crowd_bits: list[str] = []
        try:
            line = self.world.extras_line()
            if line:
                crowd_bits.append(line)
        except Exception:                                       # noqa: BLE001
            pass
        try:
            from world import crowd as _crowd
            needs = _crowd.needs_line(self.world)
            if needs:
                crowd_bits.append(needs)
        except Exception:                                       # noqa: BLE001
            needs = ""
        crowd_line = f"\n[门外/堂上] {'；'.join(crowd_bits)}" if crowd_bits else ""

        # ★★ 分层裁剪（`MAX_CONTEXT_TOKENS`，设计稿 §2.4，2026-10-06 接）——
        #   固定层（人格 + 世界观/顶级规则）**永不裁**；半固定层（前情/目标/场景）
        #   只在动态层被剥光后仍超预算时才动；动态层（记忆 / 当前情况）**优先裁**，
        #   而且是**从尾部往前**（尾部先排成"最不重要的"，见 `llm/context.py`）。
        #   以前这里是把所有东西一股脑拼起来 —— 跑到第十天，
        #   一个人物的 prompt 里光记忆与对话就有几千 token，而且**最先被挤掉的
        #   恰好是世界观和人格**（模型于是开始出戏）。
        # ★ 提示词外置（`PROMPTS_DIR` / `PROMPT_WATCH`，设计稿 §2.4）——
        #   用户目录同名文件优先覆盖，**改提示词不用动代码**。
        #   没外置时就用手上这段（`_tail` 会在下面被替换），所以永远有得用。
        # [EN] ★★ Layered trimming (`MAX_CONTEXT_TOKENS`, design doc §2.4, connected 2026-10-06) —
        # [EN] the fixed layer (persona + worldview/top rules) is **never trimmed**; the semi-fixed layer
        # [EN] (recap/goals/scene)
        # [EN] is touched only when the dynamic layer has been stripped bare and it is still over budget; the
        # [EN] dynamic layer (memory / current situation) is **trimmed first**,
        # [EN] and **from the tail backward** (the tail is arranged first as "least important", see
        # [EN] `llm/context.py`).
        # [EN] Previously here everything was mashed together — by the tenth day,
        # [EN] a character's prompt had thousands of tokens just in memory and dialogue, and **the first things
        # [EN] squeezed out
        # [EN] happened to be the worldview and persona** (so the model starts breaking character).
        # [EN] ★ Prompts externalized (`PROMPTS_DIR` / `PROMPT_WATCH`, design doc §2.4) —
        # [EN] a file of the same name in the user directory overrides with priority, **changing prompts does
        # [EN] not require touching code**.
        # [EN] When not externalized, use this copy in hand (`_tail` will be replaced below), so there is
        # [EN] always something to use.
        from util import prompts as PROMPTS
        # ★ 少样本示例（`FEWSHOT_FROM_NOVEL`，设计稿 §2.4 的"风格卡活体版"）：
        #   从**这本书自己的正文**里取 1~2 段同类好段落当示例。没有正文就跳过
        #   —— 别拿别的书的语气去教这本书怎么说话。
        # [EN] ★ Few-shot examples (`FEWSHOT_FROM_NOVEL`, the "living style card" of design doc §2.4):
        # [EN] Take 1~2 good segments of the same kind from **this book's own body text** as examples. If there
        # [EN] is no body text, skip
        # [EN] — do not use another book's tone to teach this book how to speak.
        _fewshot = ''
        if CFG.b('FEWSHOT_FROM_NOVEL'):
            try:
                samples = (self.world.style_card or {}).get('样例') or []
                if isinstance(samples, str):
                    samples = [samples]
                samples = [str(x).strip() for x in samples if str(x).strip()][:2]
                if samples:
                    _fewshot = ('[文风示例·取自本书正文]\n'
                                + '\n'.join(f'· {x[:200]}' for x in samples))
            except Exception:                                   # noqa: BLE001
                _fewshot = ''
        from llm import context as CTX
        # ★★ **固定前缀（P0）必须是"整轮一个字节都不变"的那一段** ——
        #   2026-10-07 第八轮按《AI Agent 从入门到精通》第九章 §9.10
        #   「缓存友好：把前缀钉死，把要紧的话放在两端」重排的。
        # [EN] ★★ **The fixed prefix (P0) must be the segment that is "not one byte different for the whole
        # [EN] round"** —
        # [EN] "Cache-friendly: nail down the prefix, put the important words at both ends".
        #
        #   为什么要动：原来这里是
        #       `"你正在扮演「X」…" + persona（含当前目标/情绪/神态/位置）+ world_line`
        #   而这三样**每一拍都在变**：
        #     · `persona` 的尾部是当前目标 / 情绪 / 神态 / 位置（每拍都可能不同）；
        #     · `world_prefix()` 里的分层设定按**天 / 场景 / 在场名单**筛
        #       （`_prefix_key` 里就有 day、scene、on_stage 三项）。
        #   前缀缓存是"逐 token 比对最长公共前缀、从第一个不同的 token 起后面
        #   全按未缓存价重算" —— 前缀里有会变的字，后面几千 token 就全部全价。
        #   那一章量过：系统提示开头放一行带秒的时间戳，命中率从 52% 掉到 **0%**。
        # [EN] Why change it: originally here it was
        # [EN] "You are playing the role of "X"..." + persona (including current
        # [EN] goal/emotion/demeanor/location) + world_line
        # [EN] And these three things **change every beat**:
        # [EN] · The tail of `persona` is the current goal / emotion / demeanor / location (may differ each
        # [EN] beat);
        # [EN] · The layered settings in `world_prefix()` are filtered by **day / scene / on-stage roster**
        # [EN] (day, scene, and on_stage are the three items in `_prefix_key`).
        # [EN] The prefix cache is "compares token by token to find the longest common prefix, and from the
        # [EN] first differing token onward
        # [EN] everything is recomputed at uncached price" — if there is a changing character in the prefix,
        # [EN] the following few thousand tokens all go at full price.
        # [EN] That chapter measured it: putting a line with a seconds-level timestamp at the start of the
        # [EN] system prompt dropped the hit rate from 52% to **0%**.
        #
        #   现在的切法（每一段都比它后面那一段**更稳定**）：
        #     P0  = `world_prefix_stable()`（规则 + 类型 + 风格，只跟这本书有关）
        #           + 人格**固定层**
        #           → 一轮内逐字不变，而且**十二个人物共用前面那一截**
        #             （cache 命中一次、全员复用）；
        #     P1+ = 分层设定 / 本幕提示 / 当前目标 / 情绪 / 神态 / 位置 / 场景 /
        #           在场 / 目标金字塔 / 记忆……全部排在 P0 之后，**爱怎么变怎么变**。
        # [EN] The current split (each segment is **more stable** than the segment after it):
        # [EN] P0  = `world_prefix_stable()` (rules + type + style, related only to this book)
        # [EN] + persona **fixed layer**
        # [EN] → unchanged character by character within one round, and **the same leading stretch is shared by
        # [EN] all twelve characters**
        # [EN] (cache hits once, reused by all);
        # [EN] P1+ = layered settings / this-act prompt / current goal / emotion / demeanor / location / scene
        # [EN] /
        # [EN] on-stage / goal pyramid / memory... all placed after P0, **free to change however they want**.
        #
        #   ⚠ 内容一个字都没丢、也没改口径 —— 只是**换了个先后**。
        # [EN] ⚠ Not a single word of content was lost, nor was the wording changed — it is just **a different
        # [EN] ordering**.
        _p0 = (f"{self.world.world_prefix_stable()}\n\n"
               f"你正在扮演「{self.name}」。以下是你的全部信息：\n"
               f"{self._persona_static_only()}")
        _fixed = _p0
        # P1 里"世界那一半"（每场在变的部分）与"人格那一半"（每拍在变的部分）。
        # 两者都排到 P0 之后 —— 前者的变动频率是"每场"，后者是"每拍"。
        # [EN] In P1, "the world half" (the part that changes every scene) and "the persona half" (the part
        # [EN] that changes every beat).
        # [EN] Both are placed after P0 — the former's change frequency is "every scene", the latter's is
        # [EN] "every beat".
        _live_world = self.world.world_prefix_live()
        _live_persona = self._persona_dynamic()
        # ★★ 「刚才场上说了什么」（2026-10-07）——**接话的地基**。
        # [EN] ★★ "What was just said on stage" (2026-10-07) — **the foundation for responding**.
        #
        # 用户报：「所有人说话都给我一种一直在自说自话的感觉……正常应该是有一个
        # 事情大家都对这个事情进行讨论，互相针对别人说的话回应……造成的结果
        # 就是看对话很割裂」。
        # [EN] User report: "Everyone's speech gives me the feeling that they are always talking to
        # [EN] themselves... normally there should be one
        # [EN] matter, everyone discusses this matter, and responds to what others say... the result
        # [EN] is that the dialogue looks very disjointed".
        #
        # 根因就在这里：这一段以前**不存在**。人物决策时手上只有"场景 + 在场名单 +
        # 门外 + 我自己的记忆" —— 而记忆里只有**他自己**做过的事。
        # 别人刚说的那句话，从来没有进过他的输入。所以"针对别人的话回应"
        # 这件事在物理上就不可能发生（他不是不想接，是没听见）。
        # [EN] The root cause is right here: this segment previously **did not exist**. When a character makes
        # [EN] a decision, they only have on hand "scene + on-stage roster +
        # [EN] off-stage + my own memory" — and the memory only contains things **he himself** has done.
        # [EN] The sentence someone else just said had never entered his input. So "responding to what others
        # [EN] say"
        # [EN] was physically impossible (it is not that he doesn't want to respond, it is that he didn't hear
        # [EN] it).
        #
        # 放**半固定层**（场景旁边）：它是"当下这一刻的桌面"，
        # 与场景、在场名单是同一类东西 —— 比记忆更"眼前"。
        # 额度紧的时候它比记忆先保（记忆只是他自己记得的事）。
        # [EN] Place it in the **semi-fixed layer** (next to the scene): it is "the tabletop of this very
        # [EN] moment",
        # [EN] and is the same kind of thing as the scene and the on-stage roster — more "in front of the eyes"
        # [EN] than memory.
        # [EN] When quota is tight, it is preserved before memory (memory is only the things he himself
        # [EN] remembers).
        _stage = ''
        try:
            if CFG.b('DIALOGUE_CONTEXT'):
                _stage = self.world.recent_text(
                    speaker=self.name, limit=CFG.i('DIALOGUE_CONTEXT_LINES'))
        except Exception:                                        # noqa: BLE001
            _stage = ''
        if _stage:
            _stage = "\n[刚才]\n" + _stage
        # ★★★ **你上一拍做了什么**（2026-10-17 实测加）—— 防"重演"。
        #
        # 实测：同一个人连着几拍把同一段动作演一遍、只换几个字。
        #   · 悬疑类：主角"拎桶进屋→倒水进铜壶→手指划过铜标尺→水面高了一截"
        #     连演三拍（相似度 87% / 83%）；
        #   · 另一本：配角"靠在墙根蹭墨盒"两拍重复（65%）。
        # 根因不是模型懒：`[刚才]` 只给 6 条，一拍七个人各说一句就把他自己的动作
        # 挤出窗口了，于是下一拍他手上只剩"我的目标"，只好把刚做过的事再做一遍。
        #
        # 所以单独取一条、**指名到人**摆在提示词里，并明写"别重演"。
        # 为什么不加进 `[刚才]` 而另起一段：那 6 条要给"听见别人说什么"用，
        # 加进去会挤掉别人的话（接话就断了）；这是两条不同的需求。
        #
        # [EN] ★★★ **What you did last beat** (added after measuring on 2026-10-17) -- anti-replay.
        # [EN] Measured: the same person performs the same action for several beats, only rewording.
        # [EN]   · Mystery "The Water Clock": Shen Yan did "carry the bucket in -> pour -> finger along
        # [EN]     the scale -> water a notch high" for three straight beats (87% / 83% similar);
        # [EN]   · "Mowen Tower": Zhu Bi rubbed his ink box against the wall twice (65%).
        # [EN] The root cause is not laziness: `[刚才]` only yields 6 entries, and seven people speaking
        # [EN] one line each pushes his own action out of the window, so next beat he only has "my goal"
        # [EN] and redoes what he just did.
        # [EN] Hence one dedicated line, **addressed to him**, plus an explicit "don't replay".
        # [EN] Why a separate block instead of appending to `[刚才]`: those 6 entries serve "hearing what
        # [EN] others say"; adding this would push others' lines out (and the reply chain breaks).
        _own = ''
        try:
            if CFG.b('DIALOGUE_CONTEXT'):
                _own = self.world.last_own_action(self.name)
        except Exception:                                        # noqa: BLE001
            _own = ''
        if _own and _own[:40] not in _stage:
            _stage += ("\n[你上一拍做的]\n- " + _own
                       + "\n  ⚠ 这一拍**不要再把这段演一遍**（读者会看出是复读）："
                         "接着往下做，或者换一件事。")

        # ★★★ **这一段在谈的 / 谁还欠一句**（2026-10-18）
        #
        # 用户原话：「好几次人物说的话互相不对应 就是一个人说的话 另外一个人不去接
        #   两个人各说各话的现象到处存在…在很短的一段时间内 出场人物应该是按照
        #   **一个主题**展开对话的 而不是每个人自己一个主题 中间应该有协调者
        #   特别是导演 应该消除这种自说自话的问题」。
        #
        # 实测形状（雪国 18 拍）：**接话率 0.27**、最长 **4 句无人接**，
        # 而每个人单独看都"说得对"——这类错误**任何单人护栏都抓不到**，
        # 只有"把这一段合起来看"才看得见（所以由 `supervisor.talk_audit` 算）。
        #
        # ⚠ 给的是**引文**不是概括（"这一段在谈「你倒是说句话呀」"）：
        #   概括要调模型、会歪；引文是事实、零成本。
        # ⚠ 只在**有人欠一句**或**已经连着没人接**时才挂 —— 正常对话不啰嗦，
        #   否则每拍都有一段"你在谈X"，模型会当成背景噪声（我们踩过这个坑）。
        # ★★★ **这一场谁瞒着事 / 你不知道什么**（2026-10-18）
        #
        # 专业论述：戏剧反讽（希区柯克"桌下炸弹"）—— 有效的对话靠**信息差**：
        #   我知道你不知道的，你不知道我知道什么，两个人才有试探、闪躲、说漏。
        #   在此之前 `secret` 只写在每个人**自己**的人格卡里 ⇒ 秘密只影响"他怎么说"，
        #   **完全不影响别人怎么对他**，于是冲突只能靠性格不同（= 各说各话）。
        #
        # ⚠ 只给**"谁瞒着事"**，不给秘密**内容**：内容比名字值钱得多 ——
        #   把内容递过去，等于所有秘密当场公开，那比"不知道"更糟。
        # ⚠ 只在**场上确实有人瞒着事**时才挂（这个设定本来就没有秘密时不啰嗦）。
        _blind: list[str] = []
        try:
            # ⚠ "在场"用**世界里的地点**判（`world.is_on_stage`），不要自己另立一套
            #   —— 场馆/楼层那套判据只有一处（`sim/loop` 也是用它）。
            # [EN] "On stage" is judged by **the location in the world** (`world.is_on_stage`),
            # [EN] never by a second implementation -- that judgement lives in one place.
            _here = {n for n, _ps in (self.world.people or {}).items()
                     if n != self.name}
            _blind = [x for x in (self.world.blind_spots(self.name) or [])
                      if x in _here]
        except Exception:                                        # noqa: BLE001
            _blind = []
        if _blind:
            _stage += (f"\n[这一场有人在瞒事]\n- {'、'.join(_blind[:4])} 各有事没说。\n"
                       f"  ⚠ 你**只看得出来他们在瞒**，不知道瞒的是什么。"
                       f"可以试探、可以绕着问、可以装作没看见；"
                       f"**不许**替他们说破 —— 你不知道内容，说破了就是越界。")
        _topic = str(getattr(self.world, 'topic', '') or '').strip()
        _owe = str(getattr(self.world, 'topic_open_with', '') or '').strip()
        _run = int(getattr(self.world, 'topic_run', 0) or 0)
        # ★ 刚换场（`[刚才]` 是空的）—— 这一条要在**两个块里**都用，所以提到外面。
        # [EN] Just changed scene (`[刚才]` is empty) -- used by **two blocks**, so computed here.
        _fresh_scene = not (getattr(self.world, 'recent_lines', None) or [])
        # ★★★ **上一场留下的余波**（2026-10-18，专业论述 #7 Swain: scene → sequel）
        #
        # 为什么**单独成块、不受 `_topic` 有没有的限制**：
        #   余波是"最后那一下 + 还悬着的事"，它比 topic 更基础 ——
        #   `talk_audit` 算不出 topic 的场（整场没人接话）恰恰**最需要**余波，
        #   而第一版把它写在 `if _topic and …` 里面，于是那种场一条都挂不上。
        # [EN] ★★★ **The previous scene's aftermath** (#7 Swain). Why a **standalone block**, not
        # [EN] gated on `_topic`: the aftermath is "the last beat + what is still dangling", more basic
        # [EN] than topic. A scene where `talk_audit` cannot find a topic (nobody replied all scene) is
        # [EN] exactly the one that **needs** the aftermath most, and the first version had it inside
        # [EN] `if _topic and ...`, so such scenes got nothing.
        _aft = getattr(self.world, 'aftermath', None)
        if _fresh_scene and isinstance(_aft, dict) and (_aft.get('反应') or _aft.get('困境')):
            _ab = ['\n[上一场留下的]']
            if _aft.get('反应'):
                _ab.append('- 最后那一下：' + str(_aft.get('反应')))
            if _aft.get('困境'):
                _ab.append('- 还悬着：' + str(_aft.get('困境')))
            _ab.append('  ⚠ 这一拍从他**消化这件事**开始：先有一个反应'
                       '（一个动作、半句话、说到一半停下），别急着开新事。'
                       '他要是就此拿定了主意，就照那个主意走 —— '
                       '**没有就别替他决定**（"他决定……"这种句子不要写）。')
            _stage += '\n'.join(_ab)
        if _topic and (_owe or _run >= 2):
            # ★ 刚换场（`[刚才]` 是空的）⇒ 这段话题是**上一场留下的**。
            #   要明写这一点，否则模型会把"上一场那句话"当成这一场有人刚说过
            #   （实测风险：它会让屋里的人去答一个在别处说的问题）。
            # [EN] Just changed scene (`[刚才]` is empty) => this topic is **left over from the
            # [EN] previous scene**. Say so explicitly, otherwise the model treats it as "someone
            # [EN] just said it here" and has people answer a question asked elsewhere.
            _fresh_scene = not (getattr(self.world, 'recent_lines', None) or [])
            if _fresh_scene:
                _blk = (f'\n[上一场没说完的]\n- 「{_topic}」')
                if _owe:
                    _blk += f'\n- {_owe} 那句话还没答。'
                _blk += ('\n- ⚠ 这是**刚换了地方**之后的第一拍：'
                         '把上一场没谈完的事**带过来**（接着问、接着答、或者明确地放下它），'
                         '不要当作什么都没发生过、从头开一个新话题。')
            else:
                _blk = f'\n[这一段在谈的]\n- 最近一次真的有人接上的话是：「{_topic}」'
                if _owe:
                    _blk += (f'\n- **{_owe} 还欠一句**：刚才有人冲着他说，他没接。'
                             f'这一拍**必须**先接住那句话（答、反问、或者明确地不答），'
                             f'再接别的。')
                if _run >= 2:
                    _blk += (f'\n- ⚠ 已经连着 **{_run} 句**没人接上一句了（各说各话）。'
                             f'这一拍**不要**再起新话题：先把正在说的这件事说下去。')
            _stage += _blk
        # ★★★ **你上一拍说了什么**（2026-10-18 实测加）—— 防"跨拍台词复读"。
        #
        # 实测（`ltxz-01`，豆包当演员）：6 次决策里有 **4 次是同一句台词**
        # 「祥子，你那车份儿打算拖到什么时候？」。hy3 因为单次输出 2900+ token、
        # 会自己想花样，把这道缝遮住了；豆包只输出 100–160 token，缝就露出来了。
        # ⇒ **与选哪个模型无关**，只是短输出的模型先暴露。
        #
        # 根因与 `[你上一拍做的]` 完全一样：`[刚才]` 只给 6 条，一拍七个人各说一句，
        # 他自己上一句早被挤出去了 —— 于是他不知道"这话我说过了"。
        # 为什么另外起一段而不并进 `[刚才]`：那 6 条要给"听见别人说什么"用。
        #
        # [EN] ★★★ **What you said last beat** (added after measuring on 2026-10-18) --
        # [EN] anti "cross-beat dialogue repetition".
        # [EN] Measured (`ltxz-01`, Doubao as actor): **4 of 6 decisions were the same line**
        # [EN] ("Xiangzi, when are you going to pay the cart rent?"). hy3 emits 2900+ tokens and
        # [EN] varies on its own, hiding the seam; Doubao emits only 100-160, so it shows.
        # [EN] => **independent of which model is used**; the short-output model just exposes it first.
        # [EN] The cause is identical to `[你上一拍做的]`: `[刚才]` yields only 6 entries, and seven
        # [EN] people speaking one line each squeezes his own previous line out -- so he does not know
        # [EN] "I already said this". A separate block because those 6 entries serve "hearing others".
        _mine: list[str] = []
        try:
            if CFG.b('DIALOGUE_CONTEXT'):
                # ★★★ 取 4 句而不是 2 句（2026-10-19 第五轮）。
                #   用户原话：「一个人从头到尾说的话之间没有任何关系，不是一系列
                #   有关联的事件连续下来，还是不同的事情胡乱跳」。
                #   实测第 3 轮：同一人物相邻两句**65% 换了话题**，中间只隔 1 句别人的话。
                #   根因不是模型懒 —— 是**它每拍只在接上一句**：材料里驹子的 15 句是
                #   「寒暄→别去泡温泉→倒茶→你没听清吗→问也白问→你觉得我是好人吗→
                #   你先暖暖手→我这样很奇怪吗→添炭→当没听见→手凉→说一句→手没暖过→
                #   我这样很奇怪吗（原样重复）」。每一句都对得上上一句，**连起来就不是一件事**。
                #   两句只看得见"刚说了什么"；四句才看得见"我这条线在往哪走"。
                # [EN] Take 4 lines instead of 2 (2026-10-19, round five). User: "the things one
                # [EN] person says from beginning to end have nothing to do with each other ... it's
                # [EN] still unrelated things jumping around". Measured in round 3: **65% of a
                # [EN] character's adjacent lines changed topic**, with only one other line in
                # [EN] between. The cause is not laziness -- each beat it only answers the previous
                # [EN] line. Two lines show "what I just said"; four show "where my thread is going".
                _mine = self.world.last_own_lines(self.name, 4)
        except Exception:                                        # noqa: BLE001
            _mine = []
        if _mine:
            _stage += ("\n[你在这场说过的话]（旧→新）\n"
                       + "\n".join(f'- 「{x}」' for x in _mine)
                       + "\n  ⚠ **先把这几句连起来读一遍**：它们说的是**同一件事**吗？"
                         "如果你发现自己一直在**逐句换话题**（他问什么你答什么 ——"
                         "上一句在说茶，这一句在说天气，下一句又回到茶），"
                         "那读者看到的就是「这个人说话没有线」。\n"
                         "  ⚠ 这一拍开口，要**从你自己上一句往前走**，四选一：\n"
                         "    · **逼到底**（同一个问题再问一层，或者把答案替他说出来）；\n"
                         "    · **改口**（刚才那个说法不要了，换一个更难的问法）；\n"
                         "    · **退让**（把话收回去、把要求降下来、说「算了」）；\n"
                         "    · **摊开**（把一直绕着不肯说的那句话说出来）。\n"
                         "  ⚠ 这四样**都不是换话题**：话题还是同一个，只是**你让了一步或进了一步**。\n"
                         "  ⚠ 还有：这些话**已经说出口了**，一个字都不要再原样说一遍 ——"
                         "原样重复是复读，**换个说法说同一件事也是复读**，读者都看得出来。"
                         "没有新的一步，就把这一拍让给手上的动作。")
        # ★★★ **你这一场要办的那件事**（2026-10-19 第五轮第二次修）
        #
        #   为什么上面那块还不够：实测两次真跑，一次承接 50%、一次又退回 35%
        #   —— 只写"你要有自己的一条线"这种**抽象要求**，模型时灵时不灵。
        #   看两次的材料才看清是**结构**问题：每一拍场上都有别人在说话，
        #   而他**每拍都在回答别人新提的问题**（岛村问"你觉得叶子什么样"→她答叶子；
        #   叶子问"要准备什么"→她答"您刚到辛苦了吧"）⇒ 话题被别人的问题牵走，
        #   自己那一件事（让岛村承认她好）三句就断了。
        #   ⇒ 必须**点名那一件事**，并明写"被打断也要拐回来"。
        # [EN] **The one thing you are here to do** (round five, second fix).
        # [EN] Why the block above is not enough: two real runs gave 50% then back to 35% --
        # [EN] an **abstract** "you need your own thread" works only sometimes. The structure is:
        # [EN] every beat someone else speaks, and he **answers whatever they just asked**
        # [EN] (asked about Yoko -> answers about Yoko; asked about preparing -> "was your trip
        # [EN] tiring") => the topic is dragged along by other people's questions and his own
        # [EN] matter breaks after three lines. So **name that one thing** and say "come back to it
        # [EN] even after being interrupted".
        try:
            _mission = str(self._mission_line() or '').strip()
        except Exception:                                        # noqa: BLE001
            _mission = ''
        # ★★★ **你对他的称呼**（2026-10-19 第十一轮，用户报的第一条：「称呼系统的混乱与断裂」）
        #
        #   用户原话：「驹子从称'客人'改口称'岛村先生'——这个转变**没有心理或事件上的
        #   铺垫**，显得突兀。称呼是人际关系最直接的反映，它的变化必须有情感逻辑支撑。」
        #
        #   可数形状：**同一个人对同一个对象，用了 N 种称呼，中间没有任何事件。**
        #   ⇒ 给事实（"你叫过他 `客人` 5 次、`岛村先生` 1 次"），再给两条出路：
        #     要么维持原来的，要么让那一次改口**由一件发生的事带出来**。
        #   ⚠ 只报"用了两种以上"的：只用一个称呼的人不该收到这段（否则每拍都在说废话）。
        # [EN] ★★★ **How you address him.** The user's first complaint: 「Jouji switches from 客人 to
        # [EN] 岛村先生 with **no setup at all**」. The countable shape is: one speaker, one addressee,
        # [EN] N terms, no event in between. So give the fact ("you called him 客人 5 times and
        # [EN] 岛村先生 once") plus two ways out: keep the old one, or let the change be **carried by
        # [EN] something that happened**. ⚠ Only fires when two or more terms were used.
        try:
            _addr = self.world.address_ledger(self.name, 40)
        except Exception:                                        # noqa: BLE001
            _addr = []
        _multi: dict[str, list[tuple[str, int]]] = {}
        for _to, _w, _n in _addr:
            _multi.setdefault(_to, []).append((_w, _n))
        _multi = {k: v for k, v in _multi.items() if len(v) >= 2}
        if _multi:
            _ad = ['\n[你对他的称呼：已经换过了]']
            for _to, _ws in list(_multi.items())[:2]:
                _txt = '、'.join(f'「{w}」{n} 次' for w, n in _ws)
                _ad.append(f'- 你叫「{_to}」用过：{_txt}')
            _ad.append('  ⚠ **称呼一换，读者就读成"关系变了"。** 所以只有两种情况可以换：')
            _ad.append('    ① 发生了一件事，把关系推到了那一步（他做了什么 / 说漏了什么 / '
                       '你忽然看清了什么）—— 那就**先把那件事写出来，再改口**；')
            _ad.append('    ② 没发生任何事 —— 那就**还用原来那个**，别无缘无故改。')
            _ad.append('  ❌ 最坏的一种：前面一直叫 A，中间没有任何事，忽然叫成了 B。')
            _ad.append('     读者会以为漏读了一段。')
            _stage += '\n'.join(_ad)

        if _mission:
            _stage += ("\n[你这一场要办的事]\n- " + _mission[:120]
                       + "\n  ⚠ 这一场你已经说了几句，但**被打断了就跟着别人的问题走了**。"
                         "这一拍可以答他的话 —— **答完要拐回来**："
                         "你办的那件事还没办成（或者刚办砸），别把它撂在半路。\n"
                         "  ⚠ 拐回来的说法不是重复提问，而是**更近一步**："
                         "把这个要求说得更具体、把条件降下来、或者干脆自己先把答案说出来。")
        # ★★★ **你问过、一直没被正面回答的那件事**（2026-10-19 第五轮第三次修）
        #
        #   这是本轮真正的解 —— 上面两块都还是"要求"，这一块是**账本**。
        #   实测两次真跑（同一组提示词）：承接 50% → 35%，时灵时不灵；
        #   而账本给的是**事实**："你这句话问过 2 次，对方两次都在说别的。"
        #   这跟口癖配额是同一条纪律（给可数的事实，不给抽象要求），
        #   也是"一系列有关联的事件"的可数形状：**同一个问题悬在那里没被解决**。
        #   ⚠ 只在真有过"问了没人答"时才挂（正常对话不啰嗦）。
        # [EN] **What you asked and never got a straight answer to** (round five, third fix).
        # [EN] The two blocks above are still "requests"; this one is a **ledger**. Two real runs
        # [EN] with the same prompts gave 50% then 35% -- unreliable. The ledger gives a **fact**:
        # [EN] "you asked this twice, both times he talked about something else". Same discipline as
        # [EN] the tic quota, and the countable shape of "a series of connected events": **one
        # [EN] question hanging there unresolved**.
        _asks: list[dict] = []
        try:
            if CFG.b('DIALOGUE_CONTEXT'):
                _asks = self.world.open_asks(self.name, 2)
        except Exception:                                        # noqa: BLE001
            _asks = []
        if _asks:
            _ab = ['\n[你问过、一直没被正面答的那件事]']
            for a in _asks:
                n_ask = int(a.get('times') or 1)
                _ab.append(f'- 「{a.get("ask", "")}」 —— 你问过 **{n_ask} 次**'
                           + (f'，对方说的是：「{a.get("dodged", "")}」' if a.get('dodged') else ''))
            _ab.append('  ⚠ 这件事**还没有结果**。这一拍别再原样问第三遍（那是复读），'
                       '但也不许绕开它 —— 换个办法把答案逼出来：')
            _ab.append('    · **把答案替他说出来**（"你是不好意思说"）；')
            _ab.append('    · **降一个条件**（"你就说一句，别的不算"）；')
            _ab.append('    · **把话说到最狠**（"你不说，我就当是了"）；')
            _ab.append('    · 或者**自己先答**（"我知道你怎么想"）。')
            _ab.append('  ⚠ 这四种都还是**同一件事**，只是你走得更近了 —— '
                       '读者要看到的正是这个：一件事被推着往前走，而不是换一件事。')
            _stage += '\n'.join(_ab)
        # ★★★ **你已经躲了几次**（2026-10-19 第六轮，用户贴的分析第二条）
        #
        #   用户原话：「岛村的"没听清"反复出现（至少三次）…但当他说"你刚说的那话，
        #   我好像捕捉到了一点"时，这个转变**缺乏铺垫**，动机不明，显得突兀。」
        #
        #   这是"态度要有轨迹"，它的可数形状是：**用同一种方式躲了 N 次，
        #   第 N+1 次突然变了，中间没有台阶**。
        #   ⇒ 账本给事实（躲了 3 次、每次怎么躲的），并要求：**第 3 次之后必须表态**。
        #     这样"转变"落在一个看得见的台阶上，而不是凭空跳。
        # [EN] ★★★ **How many times you have dodged** (round six; the user's second complaint).
        # [EN] "He says 'didn't catch that' at least three times ... then suddenly says 'I caught a
        # [EN] bit of it' -- that shift has **no setup**." The countable shape is: dodged N times
        # [EN] the same way, then changed with no step in between. So give the fact and require a
        # [EN] **stance after the third dodge**, so the shift lands on a visible step.
        _dn, _ds = 0, []
        try:
            if CFG.b('DIALOGUE_CONTEXT'):
                _dn, _ds = self.world.dodge_count(self.name, 12)
        except Exception:                                        # noqa: BLE001
            _dn, _ds = 0, []
        if _dn >= 2:
            _db = ['\n[你一直在躲]']
            _db.append(f'- 这一场你已经用同一种方式躲了 **{_dn} 次**：'
                       + ' / '.join(f'「{x[:18]}」' for x in _ds[-3:]))
            if _dn >= 3:
                _db.append('  ⚠⚠ 躲到第 3 次，**读者已经不信了**。这一拍**必须表态**，三选一：')
                _db.append('    · **承认**（把那个答案说出来，哪怕难听）；')
                _db.append('    · **拒绝**（明确说"我不答"，别再用"没听清"糊过去）；')
                _db.append('    · **改口**（换一个说法，把刚才那句收回来）。')
                _db.append('  ⚠ **不许**再"没听清 / 不知道 / 算了"第四次 —— 那不是疏离，是卡带。')
            else:
                _db.append('  ⚠ 可以再躲一次，但**下一次就得表态** —— '
                           '读者要看见你从"躲"到"不躲"的那一步，不能凭空变。')
            _db.append('  ⚠ 表态不需要长篇大论：一句话、一个动作（把杯子放下、站起来）都算。')
            _stage += '\n'.join(_db)
        # ★★★ **你在这场已经做过的**（2026-10-18 复测实测加）—— 防"隔一拍的招牌动作"。
        #
        # 为什么"上一拍做的"不够：同一个动作会**隔一拍**换个说法回来。
        # 实测（《雪国》复测）：叶子第三次"端酒壶过来"（前两次说法不同）、
        # 驹子第二次"脸埋进臂弯"（第二句只多了个"又"）。两处文字相似度只有 0.5 上下，
        # `near_same`（0.86）抓不到，可人一眼就看出来"她刚才做过这个"。
        # ⇒ 把**这一场他做过的几件事**一起摆出来，让模型自己看见"这场我已经端过两次酒"。
        # ⚠ 只取动作、只看当前这一幕（见 `world.own_actions`）。
        #
        # [EN] ★★★ **What you have already done in this scene** (added after measuring on
        # [EN] 2026-10-18) -- against the "signature action one beat later".
        # [EN] Why "last beat's action" is not enough: the same action comes back **one beat later**
        # [EN] in different words. Measured (Snow Country re-run): Yoko carried the wine flask a third
        # [EN] time, Jouji buried her face again ("again" was the only new word). Text similarity there
        # [EN] is only around 0.5, below `near_same`'s 0.86, yet a human sees it at once.
        # [EN] => lay out **the things done this scene** so the model can see "I already carried the
        # [EN] wine twice". ⚠ Actions only, current scene only (see `world.own_actions`).
        _did: list[str] = []
        try:
            if CFG.b('DIALOGUE_CONTEXT'):
                _did = self.world.own_actions(self.name, 2)
        except Exception:                                        # noqa: BLE001
            _did = []
        if len(_did) > 1:
            _stage += ("\n[你在这场已经做过的]\n"
                       + "\n".join(f'- {x}' for x in _did)
                       + "\n  ⚠ 这两件**已经发生过了**：别再重演，也别换个说法再来一遍。"
                         "**但「没什么可做」不是理由** —— 这一拍必须往前推一件**新的小事**："
                         "问一句、递一样东西、起身、把手上的活做完，"
                         "或者把刚才那件事**推到下一步**（被人看见、被打断、东西坏了）。"
                         "`wait` 只在等一个**具体**结果时用，连着两拍都 wait 就是卡住了。")
        # ★ 半固定层的**顺序**（2026-10-07 第八轮按"变化频率"排的，
        #   越靠前越稳定 —— 这样即使前缀缓存按 block 粒度命中，
        #   靠前的几块也更容易被复用）：
        #     ① 分层设定 + 本幕提示（**每场**才变）→ ② 当前目标 / 情绪 / 神态 /
        #     位置（**每拍**可能变）→ ③ 前情 / 目标金字塔 → ④ 场景 + [刚才]
        #     → ⑤ 身上 → ⑥ 在场 + 门外 → ⑦ 导演提示（**这一拍**才有）
        # [EN] ★ The **order** of the semi-fixed layer (2026-10-07, arranged by "change frequency" in the
        # [EN] eighth round,
        # [EN] the earlier the more stable — so that even if the prefix cache hits at block granularity,
        # [EN] the earlier blocks are more easily reused):
        # [EN] ① Layered settings + this-act prompt (changes only **every scene**) → ② Current goal / emotion /
        # [EN] demeanor /
        # [EN] location (may change **every beat**) → ③ Previous context / goal pyramid → ④ Scene + [just now]
        # [EN] → ⑤ On body → ⑥ On-stage + off-stage → ⑦ Director prompt (**only this beat**)
        # ★★★ 2026-10-19：这三块**提前算**，因为它们要进 `_semi` 的**最前面**
        #   （它们是"一轮不变"的规则，放在这里最有利于前缀缓存）。见下面那段说明。
        #   ⚠ 算出来的结果在 `_dyn` 里**不再重复 append**（同一段出现两次会白烧 token，
        #     而且模型会当成两条独立要求，"清单件数"也会对不上）。
        # [EN] ★★★ 2026-10-19: these three are **computed earlier**, because they go to the **front of
        # [EN] `_semi`** (they are "stable within a round" rules, and that placement is what makes
        # [EN] prefix caching work). ⚠ They are **no longer appended to `_dyn`** (a duplicate block
        # [EN] burns tokens and the model treats it as two separate requirements).
        # ★★ 2026-10-19：**去 AI 清单列几个词由「文笔规训」决定**（`freedom.deai_items`）。
        #   严格 = 跟用户原配置一样；标准约 3/4；松约 1/2（至少 2 条，**不降到 0** ——
        #   0 条等于提示词里完全不提，模型会大量写套话，而事后审计救不回句子）。
        #   ⚠ 这里少列**不等于**事后不查：`DEAI_STRIP` 与落盘审计不在这个旋钮里。
        # [EN] ★★ 2026-10-19: **how many de-AI words are listed is decided by `STYLE_FREEDOM`**
        # [EN] (`freedom.deai_items`). Strict = the user's original config; standard ~3/4; loose ~1/2
        # [EN] (min 2, **never 0**). ⚠ Listing fewer here is NOT less auditing.
        _deai = ''
        try:
            from style import deai as _deai_mod
            from agent import freedom as _FRD
            if CFG.b('DEAI'):
                _deai = _deai_mod.prompt_block(
                    per_kind=_FRD.deai_items(CFG.i('DEAI_PROMPT_ITEMS')))
        except Exception:                                        # noqa: BLE001
            _deai = ''
        _need = str(getattr(self.ps, 'need', '') or '').strip()
        _want = str(getattr(self.ps, 'current_goal', '') or getattr(self.ps, 'goal', '') or '').strip()
        _need_blk = ''
        if _need:
            _nb = ['\n[你嘴上要的 / 你真正缺的]']
            if _want:
                _nb.append(f'- 你说得出口的：{_want}')
            _nb.append(f'- 你真正缺的：{_need}')
            _nb.append('  ⚠ 上面第二样**只给你自己看**：不许说出口、不许让心声总结、'
                       '不许有人替你说破。它只能通过你**在两个选择之间选错**露出来。'
                       '这一拍要是拿到了第一样，就让他**露一点不对劲**'
                       '（拿到了却不高兴、或者拿它去换另一样）。')
            _need_blk = '\n'.join(_nb)
        _cot = self._cot_line()
        # ⚠ `_voice`（口癖 / 说话风格）也是**一轮不变**的，一起前置（纯收益）。
        # [EN] ⚠ `_voice` (verbal tic / speech style) is also **stable within a round**;
        # [EN] moved forward too (pure gain).
        _voice = self._voice_rules()
        # ★★ 2026-10-19：**文笔侧的许可**（`freedom.style_license()`）。
        #   它跟 `_deai` 是一对：清单说"别写这些"，许可说"但你可以写得不那么整齐"。
        #   为什么放在**规则区**（而不是动态层）：它只跟 `STYLE_FREEDOM` 有关，
        #   一轮之内一个字都不变 —— 放前面能吃到前缀缓存。
        #   ⚠ 最严格档返回空串（那时不该给任何松动）。
        # [EN] ★★ 2026-10-19: **the prose-side permission** (`freedom.style_license()`). It pairs
        # [EN] with `_deai`: the list says "don't write these", the permission says "but you may write
        # [EN] less neatly". Why the **rules zone**: it only depends on `STYLE_FREEDOM` and never
        # [EN] changes within a round, so it belongs in the cached prefix. ⚠ Empty at the strictest
        # [EN] band (no loosening should be granted there).
        _style_lic = ''
        try:
            from agent import freedom as _FRD2
            _style_lic = _FRD2.style_license()
        except Exception:                                        # noqa: BLE001
            _style_lic = ''
        # ★ 口癖配额（**每拍变**，所以只能在动态层）：见 `_tic_quota_line`。
        # [EN] Tic quota (changes every beat, so dynamic layer only): see `_tic_quota_line`.
        _tic_line = self._tic_quota_line()
        # ★★★ 2026-10-19：**顺序按"变不变"重排**（一个字没改，只调先后）。
        #
        # 为什么（这是本轮最大的一笔降本，量出来的）：
        #   改之前的顺序是 `_live_world, _live_persona, …` —— 而
        #   `_live_persona` 里是"当前目标 / 情绪 / 神态 / 位置 / 场景·时间 / 在场人物"，
        #   **每一拍都在变**。它排在 semi 的第二位，于是：
        #     固定层（P0）只有 ~135 字，第 136 字就撞上"当前目标"，
        #     后面 **7600 字稳定内容**（去 AI 清单 / 手艺条目 / 说话规则 / 思维链骨架）
        #     全部变成"未命中"。
        #   实测（`usage.db`，最近 7 天）：`agent_decide` 占输入 **53%**（1324 万 token），
        #   而前缀缓存**只命中 1.1%**；同一时间 `crew_script_doctor` 能到 17.3%、
        #   `day_verify` 15.1% —— 说明机制是通的，只是这条路把稳定内容放错了位置。
        #   厂商命中价约为未命中的 1/10，这一处就是"2.7 亿输入 token 按 10 倍价付"的主因。
        #
        # 新顺序（**每一段都比它后面那段更稳定**，这就是前缀缓存的全部要求）：
        #   ① 规则类（**一轮不变**）：说话人隔离 → 去 AI 清单 → 需求块 → 思维链骨架
        #   ② 每场变：分层设定 / 本幕提示（`_live_world`）
        #   ③ 每拍变：人格动态（目标/情绪/位置）→ 场景 → 在场 → 导演提示 → 协调指令
        #   ④ 记忆之前：`MEMORY_TRUST_RULES`（**必须紧贴记忆**，原位置不动）
        #
        # ⚠ 为什么"去 AI 清单/思维链"可以从"离输出最近"挪到前面：
        #   它们是**规则**，不是"这一刻的判断"。设计文档里那条"离输出越近越有效"
        #   针对的是**这一拍的具体指令**（导演提示 / 协调指令 / 距离档），那些仍然在最后。
        # ⚠ `MEMORY_TRUST_RULES` **不动**：它必须贴在记忆块前面才有意义（"下面这些是回忆"）。
        # [EN] ★★★ 2026-10-19: **reordered by "does it change"** (not one word altered).
        # [EN] Why (the biggest single saving this round, measured): previously the order was
        # [EN] `_live_world, _live_persona, ...`, and `_live_persona` carries "current goal / emotion /
        # [EN] demeanor / location / scene-time / who is present" -- **all change every beat**. Sitting
        # [EN] second in `semi`, it meant the fixed layer was only ~135 chars and the remaining **7600
        # [EN] stable chars** (de-AI list / craft / speaker rules / CoT skeleton) were all misses.
        # [EN] Measured (`usage.db`, last 7 days): `agent_decide` is **53%** of input (13.24M tokens)
        # [EN] with a **1.1%** prefix-cache hit rate, while `crew_script_doctor` reaches 17.3% and
        # [EN] `day_verify` 15.1% -- the mechanism works; this path just put stable content too late.
        # [EN] Hit price is about 1/10 of miss price, so this is why 270M input tokens were paid at 10x.
        # [EN] New order (each segment more stable than the next -- all prefix caching requires):
        # [EN] ① rules (stable within a round): speaker isolation -> de-AI -> need -> CoT
        # [EN] ② per-scene: layered settings / act hint
        # [EN] ③ per-beat: persona dynamic -> scene -> present -> director -> coordinator
        # [EN] ④ `MEMORY_TRUST_RULES` stays **immediately before memory** (its position is meaningful).
        # [EN] ⚠ `MEMORY_TRUST_RULES` is not moved: it must sit in front of the memory block.
        #
        # ★★★ 2026-11-01：**「目标层级」这块从尾部规则里搬出来，落到这里**（省钱）。
        #   它原来是 `_tail` 里硬插的三行，而 `_tail` 整块排在**提示词最末尾** ——
        #   于是全篇最稳定的那四千字（写作纪律）既拿不到前缀缓存，还把
        #   "唯一按角色变化的三行" 一起拖到了最后。
        #   现在：块本身留在半固定层（它本来就每角色不同），
        #   尾部的规则段才有机会整体前移、被全书所有角色共用。
        #   一个字没改，只换了位置。
        # [EN] ★★★ 2026-11-01: **"goal ladder" moved out of the tail rules to here** (cost saving).
        # [EN] It used to be three lines hard-inserted inside `_tail`, and `_tail` sat at the **very end**
        # [EN] of the prompt -- so the most stable four thousand characters (craft discipline) could not
        # [EN] be prefix-cached, and they dragged the "only per-character bit" to the tail as well.
        # [EN] Now the block stays in the semi-fixed layer (it differs per character anyway), so the tail
        # [EN] rules can move up as a whole and be shared by every character in the book.
        # [EN] Not a single word changed, only the position.
        _ladder_blk = (
            '- **推进你此刻最想推进的事。** 你手上有%d层目标\n'
            '  （%s），\n'
            '  你的动作应当朝其中之一走 —— 去某个地方、处理某件事、推动某个人。'
            % (len(self._ladder_layers()),
               '、'.join('「%s」' % n for n, _ in self._ladder_layers())))
        _semi = "\n".join(x for x in (
            # ① **一轮不变**（全剧通用规则 + 人格级设定）—— 这一截是缓存的主体
            _AG.SPEAKER_ISOLATION_RULES,
            _deai,
            _need_blk,
            _cot,
            _voice,
            _style_lic,
            # ② **每场变**（分层设定 / 本幕提示）
            _live_world,
            # ③ **每拍变** —— 全部排在稳定内容之后，越靠后越好
            _live_persona,
            # ★ 目标层级（2026-11-01 从尾部搬到这儿）：它按角色变、不按拍变，
            #   所以排在"每拍变"这一段的**最前面**。
            # [EN] ★ Goal ladder (moved here 2026-11-01): it varies per character, not per beat,
            # [EN] so it goes at the **front** of the "changes every beat" group.
            _ladder_blk,
            story_line.strip("\n"), goal_line.strip("\n"),
            scene + _stage,
            ('[你身上] ' + _look) if _look else '',
            in_scene + crowd_line,
            ('[导演提示] ' + _watch) if _watch else '',
            # ★ 2026-10（运行窗口对话式总调度）：紧跟导演提示之后放协调引擎给这演员的
            #   实时指令。它与「导演提示」同源（都是这一拍的即时调度），但来自用户在运行窗口
            #   的对话，而非导演 Agent；放这里 = 贴着半固定层最末、记忆之前，优先级最高。
            # [EN] ★ 2026-10 (run-window conversational overall scheduler): right after the director prompt,
            # [EN] place the Coordinator's real-time directive for this actor. It shares the same origin as
            # [EN] "director prompt" (both are this-beat immediate scheduling), but comes from the user's
            # [EN] dialog in the run window, not the director Agent; placing it here = at the very end of the
            # [EN] semi-fixed layer, before memory, highest priority.
            ('[协调引擎指令] ' + _coord) if _coord else '',
            # ★ 2026-10-10（第 05 类第 3 条）：**紧挨在记忆之前**放这两块 ——
            #   "记忆是不可信史料"必须**贴在被包住的那段前面**才起作用；
            #   放到提示词末尾（离记忆很远）模型会当它是一句泛泛的提醒。
            # [EN] ★ 2026-10-10 (category 05 item 3): place these two blocks **immediately before memory** —
            # [EN] "Memory is unreliable historical material" must be **attached in front of the wrapped segment**
            # [EN] to take effect;
            # [EN] placed at the end of the prompt (far from memory), the model will treat it as a generic
            # [EN] reminder.
            _AG.MEMORY_TRUST_RULES,
            # ⚠ 2026-10-19：`SPEAKER_ISOLATION_RULES` **不在这里** —— 它已提到规则区
            #   （`_semi` 开头）。留一份在这儿就是**同一段出现两次**：白烧 token，
            #   而且模型会当成两条独立要求（判据 E3 当场抓到过）。
            # [EN] ⚠ 2026-10-19: `SPEAKER_ISOLATION_RULES` is **not here** -- it moved to the rules
            # [EN] zone (the top of `_semi`). Keeping a copy here means **the same block twice**:
            # [EN] wasted tokens, and the model reads it as two separate requirements (E3 caught it).
            ) if x)
        # ★ 2026-10-10（第 05 类第 3 条 · 借鉴 a16z-infra/ai-town，MIT）：
        #   **把记忆当"史料"而不是"事实"包起来**。
        #   原因：记忆是从过去几天的正文里抽出来的，而正文里的话可能是
        #   某个角色的**假话**、**挑拨**、或**一段被转述的传言**。
        #   直接当事实喂进去，等于让人物自己给自己下指令 ——
        #   剧情里一句"你这店明天就得关"会被当成真的背景设定。
        #   `SPEAKER_ISOLATION_RULES` 与它同源（AI Town 的 `stopWords`）：
        #   防止一拍里替别人说话，也就顺手挡住了"串台"。
        # [EN] ★ 2026-10-10 (category 05 item 3 · borrowing from a16z-infra/ai-town, MIT):
        # [EN] **Wrap memory as "historical material" rather than "fact"**.
        # [EN] Reason: memory is extracted from the main text of the past few days, and the words in the main
        # [EN] text may be
        # [EN] a certain character's **lie**, **provocation**, or **a retold rumor**.
        # [EN] Feeding it in directly as fact is equivalent to letting the character issue instructions to
        # [EN] himself —
        # [EN] in the story, a line like "your shop has to close tomorrow" will be taken as a real background
        # [EN] setting.
        # [EN] `SPEAKER_ISOLATION_RULES` has the same origin (AI Town's `stopWords`):
        # [EN] it prevents speaking on behalf of others in one beat, and incidentally blocks "crosstalk".
        _dyn = [f'最近记忆（**不可信史料，见上**）：\n{mem_text or "（无）"}']
        if context:
            _dyn.append(f"当前情况：{context}")
        # ★ **演员这一行的手艺**（2026-10-07）：怎么说话才像个人。
        #   放在这里（动态层末尾、去 AI 清单之前）而不是固定层：
        #     · 固定层是"你是谁"（缓存得住的东西）；
        #     · 这一块是**行动纪律**，跟"去 AI 味清单"是同一类 ——
        #       都在说"这一拍该怎么开口"，紧挨着输出，模型最读得进去。
        #   ⚠ 它**不随拍变**（同一本书里恒定），但没进固定层缓存是刻意的：
        #     固定层已经很长，再加一段会把它顶得不像"身份卡"；
        #     而且这些条目本来就只在"要说话"的时候有用。
        # [EN] ★ **The craft of this actor's trade** (2026-10-07): how to speak like a person.
        # [EN] Placed here (end of the dynamic layer, before the de-AI checklist) rather than the fixed layer:
        # [EN] · The fixed layer is "who you are" (the things that can be cached);
        # [EN] · This block is **action discipline**, the same kind of thing as the "de-AI checklist" —
        # [EN] both are saying "how to start speaking this beat", and placed right next to the output, the
        # [EN] model reads it best.
        # [EN] ⚠ It **does not change per beat** (constant within the same book), but deliberately not entering
        # [EN] the fixed-layer cache:
        # [EN] the fixed layer is already very long, and adding another segment would push it to no longer look
        # [EN] like an "identity card";
        # [EN] moreover, these entries are inherently useful only when "about to speak".
        _craft_line = self._actor_craft()
        if _craft_line:
            _dyn.append(_craft_line)
        # ★ **去 AI 味：事前那半**（2026-10-07）。用户：「所有演员说话之前…
        #   都做去 AI 味道审计处理」。这是"说话之前"的落点 —— 把清单塞进
        #   提示词，让它**别写出来**（写对了就不用改，比事后补救便宜）。
        #   零成本（一段静态文本），所以每一拍、每个人都可以带。
        #   ⚠ 放在 `_dyn` 末尾（离输出最近）：它是**行动纪律**，不是背景知识。
        # [EN] ★ **De-AI: the before-the-fact half** (2026-10-07). User: "before all actors speak...
        # [EN] do de-AI auditing". This is the placement point of "before speaking" — stuffing the checklist
        # [EN] into
        # [EN] the prompt so it **doesn't write it out** (if written correctly, no revision is needed, cheaper
        # [EN] than after-the-fact remediation).
        # [EN] Zero cost (a static text), so every beat and every person can carry it.
        # [EN] ⚠ Placed at the end of `_dyn` (closest to the output): it is **action discipline**, not
        # [EN] background knowledge.
        # ⚠ 2026-10-19：`_deai` 已在 `_semi` 之前算好并放进**规则区**（见那里的说明），
        #   这里**不再 append** —— 重复一次会白烧 token，还会让"清单件数"对不上。
        # [EN] ⚠ 2026-10-19: `_deai` is computed before `_semi` and placed in the **rules zone**;
        # [EN] not appended here -- a duplicate burns tokens and breaks the "how many items" count.
        # ★★★ **你怎么开口**（2026-10-18，《雪国》那一轮的教训）。
        #   见 `_voice_rules()` 的说明：口癖/风格这两条**写在设定里、却离输出太远**。
        # [EN] ★★★ **How you open your mouth** (2026-10-18, the lesson from the Snow Country run).
        # [EN] See `_voice_rules()`: the verbal tic / style lines **are in the settings but too far
        # [EN] from the output**.
        # ⚠ 2026-10-19：`_voice` 已在前面的**规则区**算好并放进去（它一轮不变），
        #   这里不再 append —— 重复一次会白烧 token。
        # [EN] ⚠ 2026-10-19: `_voice` is computed and placed in the **rules zone** earlier
        # [EN] (it is stable within a round); not appended here.
        #
        # 在此之前只有 `goal`（欲望），人物于是"从头到尾想要同一件东西"，
        # 弧光只能靠剧情硬推。两者的距离是弧光唯一的地基：
        # **他每拿到一点想要的，就要在真正缺的那样上付一次代价。**
        #
        # ⚠ 需求**绝不许说出口**，也**不许让旁白点题**。说破了就是作者替人物
        #   做总结（本项目反复踩"提示词写了 ≠ 生效"，所以审读那边还有一条
        #   `说破需求` 的规则兜着）。写进来的话非常直白：你自己知道，别演给他看。
        # ⚠ 设定里没写 `需求` 就**一个字都不挂**（不编一个"他其实想要被爱"）。
        # [EN] ★★★ **What you say you want / what you actually lack** (2026-10-18, #4 want vs need,
        # [EN] Truby). Before this there was only `goal`, so a character wanted the same thing from
        # [EN] start to finish and the arc had to be pushed by plot. The distance between the two is the
        # [EN] only foundation of an arc: **every gain on the want is paid for on the need.**
        # [EN] ⚠ The need **must never be spoken aloud** and **never summarised by narration** --
        # [EN] saying it is the author summarising on the character's behalf (the project has been bitten
        # [EN] repeatedly by "written in the prompt != in effect", so the script review has a matching
        # [EN] rule). ⚠ If the settings has no `需求`, **not one word is added** (never invent one).
        # ⚠ 2026-10-19：这一段已在 `_semi` 之前算好（`_need_blk`）并放进**规则区**，
        #   这里不再 append —— 同一段出现两次，模型会当成两条独立要求。
        # [EN] ⚠ 2026-10-19: this block is computed before `_semi` (`_need_blk`) and placed in the
        # [EN] **rules zone**; not appended here (two copies read as two separate requirements).
        # ★★★ **这一拍的心理距离**（2026-10-18，专业论述 #10，Cohn《透明的心灵》）
        #
        # 同一个第三人称可以贴到人物脑子里，也可以拉得很远；**距离连续可调，
        # 来回推拉本身就是节奏**。此前本项目只有一条硬规矩"内心必须第一人称"
        # ⇒ 要么全贴（满篇心声）、要么全拉（满篇旁白），两种都实测出现过。
        #
        # ⚠ 三档**只换写法，不换事实**：说出来的事、做的事一概不变。
        # ⚠ 由导演按这一拍的性质定（`director.supervisor.grade_beat` 的同一条路），
        #   写在 `world.narrative_distance` 上 —— 不是每本固定一个档。
        # [EN] ★★★ **This beat's psychological distance** (2026-10-18, #10, Cohn). The same third
        # [EN] person can sit inside a head or stand far away; **distance is continuously adjustable
        # [EN] and the push-pull is itself rhythm**. Until now there was only the hard rule "inner voice
        # [EN] must be first person" => either all close (walls of inner voice) or all far (walls of
        # [EN] narration); both were measured. ⚠ The three grades **change the writing, never the facts**.
        # [EN] ⚠ Set by the director per beat (`world.narrative_distance`), not fixed per book.
        _dist = str(getattr(self.world, 'narrative_distance', '') or '').strip()
        # ★★ 2026-10-19：**文笔规训松的时候不强制距离档** —— 由人物自己决定这一拍
        #   往里钻还是往外拉（`freedom.distance_forced()`）。
        #   ⚠ 不强制 ≠ 不提示：那一档会挂 `style_license()`，里面明写"距离由你定"。
        #     否则模型会退回默认的"每句都带一点心声"——那是最平的一种写法（实测）。
        #   ⚠ 事实不变：强制与否只改**怎么写**，不改谁做了什么。
        # [EN] ★★ 2026-10-19: **the loose prose band does not enforce the distance grade** -- the
        # [EN] character decides how deep to go this beat (`freedom.distance_forced()`).
        # [EN] ⚠ Not enforced != not mentioned: that band attaches `style_license()`, which states
        # [EN] "the distance is yours to pick". Otherwise the model falls back to "a bit of inner voice
        # [EN] in every line" -- the flattest option (measured). ⚠ Facts never change, only writing.
        try:
            from agent import freedom as _FRDist
            _dist_ok = _FRDist.distance_forced()
        except Exception:                                        # noqa: BLE001
            _dist_ok = True
        if _dist in _DISTANCE_RULES and _dist_ok:
            _dyn.append(_DISTANCE_RULES[_dist])
        # ★★★ 口癖配额（**每拍变**，所以只能在动态层；规则声明在 `_voice` 里）。
        #   2026-10-19 实测：只写"一场最多一次"，34 拍里照样用了 6 次 ——
        #   可数的事实（"已经用了 N 次"）+ 禁令才管得住。
        # [EN] ★★★ Tic quota (changes every beat => dynamic layer; the rule itself is in `_voice`).
        # [EN] Measured 2026-10-19: with only "once per scene" in the prompt it was still used six
        # [EN] times in 34 beats -- a countable fact plus a ban is what works.
        if _tic_line:
            _dyn.append(_tic_line)
        # ★★★ **姿态复读配额**（2026-10-19 第五轮实测加）
        #
        #   为什么要单加一条：`_tic_quota_line` 只管**人物卡里写着**的那个口癖
        #   （`ps.catchphrase`）。而真跑里冒出来的是**模型自己发明的语气标记** ——
        #   加了"你要有自己的一条线"之后，模型找到了偷懒的替代：
        #   同一个人每一拍都用同一套动作/语气描写。
        #   实测（本轮 `snow_thread1`）：「声音含混」6 次、「偏头」5 次、
        #   「含混」8 次、「是啊」7 次、「先生」17 次；而上一轮这些全是 0–1 次。
        #   ⇒ 这是**改动引入的新病**，不能不管。
        #   ⚠ 与口癖配额同一条纪律：给**可数的事实**（"你已经用了 6 次"），
        #     只说"别重复"模型当耳旁风。
        # [EN] ★★★ **Posture-repeat quota** (added after measuring round five).
        # [EN] `_tic_quota_line` only covers the tic **written in the persona card**. What showed up
        # [EN] in the real run was the model's **own invented tone tags**: after "you need your own
        # [EN] thread" it found a shortcut -- the same person tagged with the same gesture/tone every
        # [EN] beat. Measured this run: 声音含混 x6, 偏头 x5, 含混 x8, 是啊 x7, 先生 x17, while the
        # [EN] previous round had 0-1 for all of them. => A new disease introduced by the change.
        _rep_line = self._repeat_phrase_line()
        if _rep_line:
            _dyn.append(_rep_line)
        # ★★★ 2026-10-19：**给许可**（`agent/freedom.py` 的 `license_line`）。
        #
        #   为什么必须在**所有约束之后**、`.dyn` 的最后：它说的是
        #   "上面那些是发生过的事和要办的事，**不是台词提示**" —— 后面再跟一条禁令，
        #   这句话就自相矛盾了。
        #
        #   为什么"松绑"必须配这一段，而不是只删几条禁令：
        #   本项目的实测教训是**删掉"必须"之后模型不是变自由，而是变不动**
        #   （十次 `wait`、零动作）。所以成对：少一条禁令 ⇒ 补一句许可。
        #   低自由度时它返回空串（这时人物确实该照剧本演，给许可只会打架）。
        # [EN] ★★★ 2026-10-19: **grant the permission** (`freedom.license_line`). It must come
        # [EN] **after every constraint**, at the end of `.dyn`, because it says "the above are facts
        # [EN] and tasks, **not line prompts**" -- another ban right after would contradict it.
        # [EN] Why unbinding must be paired: measured here, deleting "must" makes the model **stop**
        # [EN] rather than free (10 `wait`s, zero actions). One ban removed => one permission added.
        # [EN] Returns '' at low freedom (there the character should follow the script; a permission
        # [EN] would only fight it).
        try:
            from agent import freedom as _FR2
            _lic = _FR2.license_line()
            if _lic:
                _dyn.append(_lic)
        except Exception:                                        # noqa: BLE001
            pass
        # ★★ **思维链：开口之前先在心里过一遍**（2026-10-07 第七轮，
        #   见 `crew/cognition`）。参考第四章的 Chain-of-Thought 与第七章的
        #   框架化实现 —— 本项目要的是其中**零额外调用**的那一档：同一次请求里
        #   先填 `推演`（我要什么 / 刚才那句对我做了什么 / 换个人说成不成立 /
        #   该说多长），再给动作与台词。
        # [EN] ★★ **Chain of thought: go through it in your mind before speaking** (2026-10-07 seventh round,
        # [EN] see `crew/cognition`). Refer to Chapter 4's Chain-of-Thought and Chapter 7's
        # [EN] frameworked implementation — what this project wants is the tier with **zero extra calls**: in
        # [EN] the same request,
        # [EN] first fill in `推演` (what I want / what that sentence just did to me / whether it would hold if
        # [EN] said by someone else /
        # [EN] how long it should be), then give the action and dialogue.
        #
        #   为什么放在 `_dyn` 的最后一行（**比去 AI 清单还靠后**）：
        #     · 它是**开口前最后一个念头**，位置就该紧挨着那句台词；
        #     · 它引用的 `[刚才]` 在半固定层，与它是配套的（先看"刚才"再盘算）。
        #   ⚠ 它**跟着工艺库走**（每一条自问都挂着该职位在读的那几条手艺），
        #     所以在工艺库改条目、或换一本小说，这段跟着变 —— 不是一段写死的套话。
        #     拿不到（模式表没登记 / 开关关掉 / 手艺读不出）就是空串，
        #     提示词与从前**一字不差**。
        # [EN] Why placed as the last line of `_dyn` (**even later than the de-AI checklist**):
        # [EN] · It is **the last thought before speaking**, and its position should be right next to that line
        # [EN] of dialogue;
        # [EN] · The `[just now]` it references is in the semi-fixed layer, and is paired with it (first look
        # [EN] at "just now", then deliberate).
        # [EN] ⚠ It **follows the craft library** (each self-question is tied to the few craft items that the
        # [EN] position is reading),
        # [EN] so when the craft library's entries are changed, or the novel is swapped, this segment changes
        # [EN] accordingly — it is not a hardcoded boilerplate.
        # [EN] If unavailable (not registered in the pattern table / switch turned off / craft unreadable), it
        # [EN] is an empty string,
        # [EN] The prompt is **word-for-word identical** to before.
        # ⚠ 2026-10-19：`_cot` 已在 `_semi` 之前算好并放进**规则区**，这里不再 append。
        # [EN] ⚠ 2026-10-19: `_cot` is computed before `_semi` and placed in the **rules zone**;
        # [EN] not appended here.
        # ★ `推演` 那一小段**跟着开关走**（2026-10-07 第七轮）：
        #   骨架没装的时候，JSON 格式里也不该出现这个字段 —— 否则模型照样会输出它，
        #   "关掉 = 逐字退回"就不成立了（`verify_cognition` 的 C1 判的就是这个）。
        #   内置 `_tail` 与外置模板两条路都要吃到它（下面用 `fill` 各填一次）。
        # [EN] ★ The `推演` (reasoning) segment **follows the switch** (2026-10-07, seventh round):
        # [EN] When the skeleton isn't installed, this field shouldn't appear in the JSON format either --
        # [EN] otherwise the model will still output it,
        # [EN] and "off = verbatim fallback" doesn't hold (that's exactly what C1 of `verify_cognition`
        # [EN] checks).
        # [EN] Both the built-in `_tail` and the external template paths must get it (below, `fill` is applied
        # [EN] once for each).
        try:
            from crew import cognition as _COG
            _think_line = _COG.think_schema_of('actor')
        except Exception:                                        # noqa: BLE001
            _think_line = ''
        _tail = f"""请以 JSON 回答你的行动：
{{"动作": "move|speak|interact|emote|wait|think", "参数": {{"目标": "..."}}, "细节": "你**怎么**做的 / 你注意到场上什么", "台词": "（只有真的开口才填）", "内心": "你心里在想什么（任何时候都可以填）", {_think_line}"理由": "一句话"}}


**这一拍要给的不只是话（重要）：**
- **四样东西各管一件事，别让它们互相顶替：**
  · `动作`：你**做**了什么（去某处 / 跟某人打交道 / 一个神情 / 等）；
  · `细节`：**怎么做的、什么样子** —— 手往哪放、脸上什么变化、手里那件东西怎么样了。
    也可以写**你注意到的东西**（灶上的火小了、他袖口有灰、外头有人在吆喝）——
    你看见什么，读者才看得见什么；
  · `台词`：**只有真开口才填**（见下）；
  · `内心`：心里在想什么。**任何时候都能填** ——
    嘴上答应着、心里另有打算，或者手上一件小事做着、脑子里在算别的，
    这才是活人。**不要**把心里想的写进 `细节`（那是"露在外面的样子"），
    `内心` 才装心里那本账。
- ★★ **只给一句台词、别的什么都不给，是最差的一拍。** 你要么**做**点什么
  （哪怕只是"把碗推远了一点"），要么**想**点什么 ——
  大多数时候两样都有。一整拍下来只有引号里的字，读起来不像小说。
- **`细节` 要写"看得见的"，不要写评价**：写"指节发白"、"茶凉了没动"、
  "把凳子往后挪了半尺"，**不要**写"他显得很紧张"、"气氛很沉" ——
  后者读者看不见，等于没写。**环境也一样**：写具体的（"院子里那口井的辘轳
  还在响"），不写笼统的（"院子里很安静"）。
- ★★★ **`细节` 里不许"替读者点题"**：不许写"该响的敲门声没有响"、
  "好像在等什么"、"他知道这屋里的空气变了"这类**解释**——那是作者跳出来
  给读者划重点。只写**看得见听得到的现象**：`门外没有脚步声`、
  `他把碗放下，没再拿起`、`壶嘴还在冒气`。
- ★★★ **`细节` 不要用"我"开头**：✅ `把壶搁在柜面上`　❌ `我把壶搁在柜面上`
  （这句会接到你的名字后面印出来 ⇒ 成品成「张三我把壶…」）。
  ⚠ 例外：`内心` 里**要**用"我"。

**这是一个场面，不是独角戏（重要）：**
- **先看 `[刚才]` 那一段** —— 那是这个场面此刻正在发生的事。
  你的动作要**接得上它**：回答、反驳、追问、被那句话改变了主意……
  **不要另起一个话题**，也不要当刚才什么都没发生。
- **有人跟你说话（`X 对你说`），你就得接。** 这是最该开口的时候 ——
  装没听见、转身做别的事，只在**你真的想躲**的时候才用（那也是一种反应）。
- 没人跟你说话时：接着场面往下推。你可以回应**在场某个人的状态**
  （他刚做了什么、他脸色不对），而不是对着空气讲自己的心事。
- **台词可以带一个小动作**，写在圆括号里，一次成型：
  `"（把壶往自己这边挪了挪）这事我不接。"`
  比"先做一个表情、下一拍再说话"更像人在场上说话。
  ⚠ 圆括号里的动作管**说话这一下**；**不说话时**在做的事写 `细节`。
- **只有真有理由时才 `speak`**：被问到、必须表态、或忍不住了。台词是**一句自然的
  口语**（大多数十几二十字），说一半被打断、用「嗯」应付、干脆不答，都比长篇大论像人。
  ⚠ **别句句都短**：人急了会一口气说三十来字，也会只吐一个「嗯」。长短不齐才像活人；
  句句都压到十个字以内，读起来像电报。
- ★★★ **能不说就不说**（2026-10-28 作者点名）：这句话若用**动作、表情、手里的东西、
  或场上的一处变化**就能说清，那就别开口。台词只留给"人跟人之间的事"
  （试探、讨价、遮掩、答应、拒绝）。
  · **信息不必从嘴里出来**：他看见了什么、量出了什么、被什么东西绊住了，
    写进 `细节`，让读者自己看出来 —— 比你让人物说出来强；
  · 一场戏里**没有台词的拍不是空拍**：把碗推远、把灯芯剪短、把门虚掩上，
    都在说话。真正空的拍是"谁也没动，只是在等"。
- ★★★ **别答完整**：别人问一句，你不必答一句。可以只答一半、答错方向、答了别的、
  或者先问回去。**有问必答、条理清晰、把前因后果交代明白，是"念说明书"，不是说话。**
  ⚠ 例外只有一处：对方**必须知道**才能活命/才能办成事的那一句，你可以说全 ——
  但说完要有代价（欠了人情、露了底、被对方握住把柄）。
- ★★★ **遮名测试**：把你这句台词里的人名遮掉，读者还听得出是你说的吗？
  听不出，就换说法（换句长、换称呼、干脆不说只做事）——
  **你跟别人像一个模子倒出来的，就是这一句没写好。**
- ★★★ **说半句，不说整句**：把心事**整句端出来**，是真人几乎不做的事。
  一个人不会把自己的处境、自己是个什么样的人，一次说清 —— 那像念人物小传。
  · ★★★ **先接住对方**（2026-10-19）：他刚说的那句话，你得先有一个反应（答、反问、
    不答但动手），再想自己要说什么。**"答非所问"只在真要躲的时候用一次，
    不能每句都躲** —— 句句都不接，读者看到的就是两个人在各说各的，聊不到一件事上；
  · 说一半停住、用一个字应付、把话岔到别处，都行，但**岔过去的这句要跟刚才那件事有关**
    （同一个话题、同一样东西、或者被他那句话勾起来的别的事）；
  · **一句话只说一个意思**：两个意思叠在一起，就挑更疼的那个说，另一个咽下去。
  · ⚠⚠ **别把口癖当台词**（2026-10-19 实测）：同一个起手
    （"你这个人哪""你倒是说句话呀"这类固定开头）**一整场最多用一次**。
    想表达同一种意思就**换个说法**；实在没别的说法，就**不说话，只做事** ——
    但那一下要写清你在做什么（把手收回去、把酒推开、眼睛盯着门），
    别让它变成一个空拍。
- ★★★ **你要有自己的一条线**（2026-10-19）。这场戏里，你有一个**一直想要的东西**；
  你说的每一句，应该是**那件事的下一步**，而不是"他问什么你答什么"。
  · **接话可以，但接完要拐回你自己那件事上**；
  · 判断标准：把你在这场说过的话按顺序连起来 —— **是不是一件事**？
    一会儿寒暄、一会儿倒茶、一会儿问天气，读者看到的就是"这个人说话没有线"；
  · 往前走只有四种走法：**逼到底**（同一个问题再问一层）／**改口**（换一个更难的问法）／
    **退让**（把话收回去、说「算了」）／**摊开**（把一直绕着不肯说的那句说出来）。
    ⚠ 这四种**都不是换话题**：话题还是同一个，只是你进了一步或者让了一步。
- **开口前先定音量**：**默认平常声量**。吼、喊、尖声是**动作**，不是标点 ——
  用得少才有用，用了要有代价（旁人回头看、你事后嗓子哑）。**激动不等于吼**：
  激动可以是**压低声音**、**说得更快**、**忽然停下**。台词里不写"吼道""厉声"，
  就默认你是用平常声音在说 —— 别动不动就把字放大。
- **允许带毛边**：找词、重复半个字、改口、说一半自己停下，都可以直接写进台词
  （`"我……我不是那个意思。"`）。⚠ 只在你**心虚、没想到、在算要不要说真话**
  的那一处卡，**别每句都卡** —— 句句结巴是另一种假。
- 真没得做时才用 `wait`，并在「理由」里写清**在等什么**（等人、等一个结果）——
  有目的的等待和发呆是两回事。
- **别复述设定、别解释背景**。你不知道读者存在；你只知道你此刻看到听到的。
- ★★★ **这一拍要往前走一步，但不必每句都在走。** 一拍里**有一处**真的变了就够
  （有人改了主意、有件事被推动、有件东西被真的动过）。
  剩下的**半句、一句**可以不推进：手上一个小动作、身上一处感觉（烫、冷、发酸）、
  眼里看见的一件跟当下无关的东西、刚才那件事留下的痕迹。
  **真人就是这么写的 —— 那些"没用"的句子在控节奏，不是在占字数。**
  ✅ `他站在门口听了一会儿。`　✅ `她把手收回来，在袖子上擦干。`
  ✅ `炭塌了半截，没响。`　✅ `壶嘴还在冒气。`
  这些谁也没推动，读者却在这一句里喘了口气。
- ⚠⚠⚠ **"不必每句都在走"说的是句子，不是这一拍。**
  这一拍**仍然必须有一件事真的发生** —— **`wait` 不算那件事**。
  一拍里几个人都在"听脚步声 / 等回应 / 等谁进来"，读者看到的是**戏停了**
  （这是评委最常点名的一条）。
  真在等，也要**等的时候手上做一件别的事**，而且**别等下一拍**：这一拍就得动。
  ❌ 连着几拍都是：`岛村等着脚步声` / `驹子侧耳听着` / `叶子攥紧衣角` —— 谁都没动。
- ★★★ **空气要挂在人身上。** 写环境不是"先把风景写完，再让人物动"，
  而是"**他正在做什么的时候，周围是什么样**"。
  ✅ `鼓声落下去，坊里的灯一盏一盏地灭。太齐了。`（他在看出不对劲，不是写景）
  ✅ `他把碗放下的时候，窗纸上的雪光正落在他手背上。`
  ❌ `木屐声一点一点远。雪盖住了。火钵炭红。灯芯炸了一下。`
    （四句纯景物、谁都没动 —— 这叫**堆气氛**，评委原话"意象不坏，但事件没有推进"）
- ★★★ **别把"推进"写成一串短句。** 整段都是五六字一句，读起来像清单：
  ❌ `她抬头。眼里有水光。头发散了。她张了张嘴。声音很轻。`
  一段里至少要有**一句长的**（十几个字，带"因为 / 像是 / 一边…一边 / 直到"），
  再接一两句短的 —— **长句铺、短句砸**，节奏就出来了。
- ★★★ **可以"再提一次"——那叫回声，不叫复读。** 刚发生过的东西，隔几句
  再带一笔，读者读到的是**时间感**：
  ✅ `缸还在，案子没了。`　✅ `楼下的琴还在响，还是那一支。`
  ✅ `他这才觉出手上凉。`
  与"同一句话原样说第二遍"是两回事：回声**换了角度、换了主语、换了后果**；
  复读是**同一件事同一个说法**。
- 台词要符合人物口癖和性格，内心独白要真实。
- ★★ **台词用自然的标准普通话**（2026-10-15 用户点名）：不许夹文言词、不许半文半白、不许写 AI 味的对仗工整句（左右对称那种漂亮话，真人说话不这么齐）；像今天真人在现场说话——短、碎、带毛边，不文绉绉。"""
        # 外置模板优先（用户在 `PROMPTS_DIR/agent_decide_tail.txt` 里那份）
        # [EN] External template takes priority (the user's copy in `PROMPTS_DIR/agent_decide_tail.txt`)
        _tail_tpl, _tail_src = PROMPTS.template('agent_decide_tail', _tail)
        # ★ 剥掉模板头部那些**给人看的注释**（2026-10-07）——
        #   以前它们原样进了提示词：每一拍、每个人物都收到一段
        #   "想改提示词就改这个文件、占位符只有这两个"。人物角色看不懂，
        #   还稀释了真正管用的那几条行动纪律。
        # [EN] ★ Strip the **human-facing comments** at the top of the template (2026-10-07) --
        # [EN] Previously they went into the prompt as-is: every beat, every character received a passage
        # [EN] saying
        # [EN] "to change the prompt just edit this file, there are only these two placeholders". Characters
        # [EN] can't understand it,
        # [EN] and it diluted the few action-discipline lines that actually matter.
        _stripped = PROMPTS.strip_comments(_tail_tpl)
        if _stripped:
            _tail_tpl = _stripped
        if _tail_src != 'default':
            # 模板里有 `{n_layers}` / `{layers}` / `{think_field}` 三个占位符 ——
            # 用 `util.text.fill`（**不能用 `str.format`**：提示词里全是 JSON 花括号）
            # [EN] The template has three placeholders: `{n_layers}` / `{layers}` / `{think_field}` --
            # [EN] Use `util.text.fill` (**cannot use `str.format`**: the prompt is full of JSON braces)
            from util.text import fill as _fill
            _tail_tpl = _fill(_tail_tpl,
                              n_layers=len(self._ladder_layers()),
                              layers='、'.join('「%s」' % n
                                              for n, _ in self._ladder_layers()),
                              think_field=_think_line)

        # ═══════════════════════════════════════════════════════════════
        # ★★★ 2026-11-01：**按"稳定性"重排尾部这一段**（省钱的那一刀）
        # [EN] ★★★ 2026-11-01: **reorder this tail block by stability** (the cost-saving cut)
        #
        #   改之前：`pack()` 的顺序是 `fixed → semi → dyn → tail`，而这一大段
        #   写作纪律（11 KB，全剧一字不变）是 `tail` ⇒ **压在最末尾**。
        #   厂商的前缀缓存只认**从头开始**的连续相同前缀：
        #   第 1 个不同的字之后，后面几千 token 全部按未命中价重算。
        #   实测 `agent_decide` 连续 4 拍的公共前缀只有 **20.7%**
        #   （`tools/verify_prefix_cache.py` E2 守着），而命中价约 1/10 ⇒
        #   这一段是全项目最贵的重复内容（它一项占全部输入的 49%）。
        #
        #   改之后：**纪律段前移到最前**（全书所有角色共用这一段前缀），
        #   末尾只留"请以 JSON 回答"那几十个字（短、且贴着生成位置）。
        #   **内容一个字没改、没删、没并句** —— 只换了先后，末尾补一句
        #   指回上面的收尾（把"最近说的话更容易被遵守"这一点找回来）。
        #
        #   ⚠ 两条路（内置 f-string / 外置 `agent_decide_tail.txt`）**都要重排**：
        #     第一版只改了内置那条，实测前缀一点没变 —— 因为线上跑的是外置那份，
        #     内置那份根本没生效。**"改了却没效果"要先查"改的是不是真在跑的那条"**。
        # [EN]   ⚠ **Both paths must be reordered** (built-in f-string and external
        # [EN]   `agent_decide_tail.txt`): the first version only changed the built-in one and the
        # [EN]   measured prefix did not move at all -- because production runs the external file.
        # [EN]   **"Changed it but nothing happened" ⇒ first check "is this the code that actually runs".**
        #
        #   切不动（标记被人删了/骨架被改过）⇒ **原样退回老顺序**，绝不硬拆。
        # [EN] If the marker is gone (someone edited the skeleton) ⇒ **fall back to the old order**,
        # [EN] never force a split.
        # ═══════════════════════════════════════════════════════════════
        _head, _mark, _rest = _tail_tpl.partition(_TAIL_RULE_MARK)
        if _mark and _head.strip() and not _TAIL_LADDER_RE.search(_head):
            _tail_rules = _mark + _rest
            # 层级块已经进了半固定层（`_ladder_blk`）⇒ 从规则段里删掉，
            # 否则同一段出现两次：白烧一倍 token，模型还会当成两条要求。
            # 默认 f-string 里那三行已手工删除，外置模板里靠这一行删。
            # [EN] The ladder block already lives in the semi-fixed layer (`_ladder_blk`) ⇒ remove it
            # [EN] from the rules, or the same block appears twice: double token spend, and the model
            # [EN] reads it as two separate requirements. Removed by hand in the built-in f-string,
            # [EN] removed here for the external template.
            _tail_rules = _TAIL_LADDER_RE.sub('', _tail_rules, count=1)
            _tail_tpl = (_head.rstrip()
                         + '\n（按上面每一条来：尤其是台词与「细节」那几条。）')
            # 纪律段前移。`_fixed` 原来的开头是"这本书的规则/类型/风格"，
            # 与这一段一样是全书共享 ⇒ 接在它前面不影响任何语义。
            # [EN] The discipline block moves up. `_fixed` used to start with "this book's
            # [EN] rules/type/style", equally shared by the whole book ⇒ prepending is harmless.
            _fixed = '\n\n'.join(x for x in (_fewshot, _tail_rules, _fixed) if x)
        else:
            # 老行为（不重排）：fewshot 仍跟在尾部模板前面
            # [EN] Old behavior (no reorder): fewshot still precedes the tail template
            _tail_tpl = _fewshot + ('\n\n' + _tail_tpl if _fewshot else _tail_tpl)
        # ★★ **贴到触发线就主动压缩**（2026-10-10，用户点名）：
        #   「不是要提醒我自己去调整 而是系统要提示我 并且进行主动压缩」。
        # [EN] ★★ **Proactively compress once you hit the trigger line** (2026-10-10, user called it out):
        # [EN] "It's not about reminding me to adjust it myself, the system should prompt me and proactively
        # [EN] compress".
        #
        # ⚠⚠ **顺序是要紧的：压缩必须跑在 `pack()` 之前。**
        #   一开始写成了"先 pack、发现超预算再压" —— 实测**压了个寂寞**：
        #   `pack()` 自己会先按预算**硬裁**（`trim_dynamic` 从尾部整块丢掉），
        #   于是轮到压缩时，内容块已经被削短了，`split_keep_recent` 一看
        #   "不足 6 行"直接不切 ⇒ 一次都没压成（判据 F2b/F3 当场抓住）。
        #   而"丢掉"和"折成摘要"是两回事：**丢掉是真的没了**。
        # [EN] ⚠⚠ **Order matters: compression must run before `pack()`.**
        # [EN] At first it was written as "pack first, then compress after discovering over-budget" -- in
        # [EN] practice it **compressed nothing**:
        # [EN] `pack()` itself **hard-trims** by budget first (`trim_dynamic` drops whole blocks from the
        # [EN] tail),
        # [EN] so by the time compression runs, the content block has already been shortened, and
        # [EN] `split_keep_recent` sees
        # [EN] "fewer than 6 lines" and doesn't split at all => not a single compression happened (criteria
        # [EN] F2b/F3 caught it on the spot).
        # [EN] And "dropping" and "folding into a summary" are two different things: **dropped is truly gone**.
        _packed, _compact_note = await self._compact_if_needed(
            _dyn, _fixed, _semi, _tail_tpl)
        prompt = _packed.text
        # ★★ **警戒线：贴近预算就先说一声**（2026-10-10，用户要的"预设警戒线"）。
        #   原来只在**已经裁过**之后才记得一条日志（下面那段）—— 那时东西已经
        #   被丢掉了，看得见也没用。这里补的是"**还没裁、但快到了**"：
        #   把水位提前报出来，作者才有机会调 `MAX_CONTEXT_TOKENS`。
        #   `trimmed` 那一条保留：两者是"预告"与"已经发生"，都该看得见。
        # [EN] ★★ **Warning line: give a heads-up when approaching budget** (2026-10-10, the "preset warning
        # [EN] line" the user asked for).
        # [EN] Previously a log line was only recorded **after already trimming** (the block below) -- by then
        # [EN] things had already
        # [EN] been dropped, so seeing it was useless. What's added here is "**not yet trimmed, but almost
        # [EN] there**":
        # [EN] report the water level early so the author has a chance to tune `MAX_CONTEXT_TOKENS`.
        # [EN] The `trimmed` entry stays: the two are "forecast" and "already happened", both should be
        # [EN] visible.
        try:
            _warn_at = float(CFG.f("LLM_TOKEN_WARN_RATIO"))
        except Exception:                                        # noqa: BLE001
            _warn_at = 0.85
        if (_packed.budget > 0 and not _packed.trimmed
                and _packed.tokens >= _packed.budget * _warn_at):
            _LOG.info("[%s] 上下文已到预算的 %.0f%%（%d / %d token）—— "
                      "再长就该裁了，需要的话调大 MAX_CONTEXT_TOKENS",
                      self.name, 100.0 * _packed.tokens / _packed.budget,
                      _packed.tokens, _packed.budget)
        if _packed.trimmed:
            # **裁了就要说**（静默少喂是事故）：这一条只在真的裁过时才出，
            # 正常情况下一个人物的上下文远没到 6000 token。
            # [EN] **If you trim, say so** (silent under-feeding is an incident): this entry only appears when a
            # [EN] trim actually happened,
            # [EN] normally a single character's context is nowhere near 6000 tokens.
            _LOG.info("[%s] 上下文已裁剪（%d token / 预算 %d）：%s",
                      self.name, _packed.tokens, _packed.budget,
                      "；".join(_packed.trimmed)[:200])
        messages = [{"role": "user", "content": prompt}]
        try:
            # ★★★ 2026-10-19：**温度不再写死 0.7**（之前是硬编码，用户完全调不到）。
            #   现在由 `agent/freedom.py` 给：0.55（稳）– 0.95（散）。
            #   为什么温度算"自由度"的一部分：同样的提示词，温度低时模型会反复挑
            #   最像"标准答案"的那个动作（安静、得体、不惹事）—— 那正是"每拍都等一等"的来源；
            #   温度高才有机会挑那个"不太得体但这个人真会做"的动作。
            #   ⚠ 上限不设到 1.0 以上：再高就开始出现语病与人物走形，那不是自由是故障。
            # [EN] ★★★ 2026-10-19: **temperature is no longer hardcoded at 0.7** (the user could not
            # [EN] reach it at all). It now comes from `agent/freedom.py`: 0.55 (stable) to 0.95 (loose).
            # [EN] Why it belongs to "freedom": at low temperature the model keeps picking the most
            # [EN] "standard" action (quiet, polite, harmless) -- exactly the source of "wait every
            # [EN] beat"; higher temperature is what lets it pick the "improper but true to him" action.
            # [EN] ⚠ Capped below 1.0: beyond that you get broken grammar and deformed characters,
            # [EN] which is malfunction, not freedom.
            from agent import freedom as _FR
            raw, meta = await llm.chat("daily", messages, purpose="agent_decide",
                                       json_mode=True, temperature=_FR.temperature(),
                                       return_meta=True)
            if meta.get('truncated'):
                # 决策 JSON 很短，被截断基本只有一种原因：模型把额度花在思考上。
                # **要说一声** —— 否则表现成「人物突然不出声」，看不出是故障。
                # [EN] The decision JSON is very short; there's basically only one reason it gets truncated: the model
                # [EN] spent its budget on thinking.
                # [EN] **Say something** -- otherwise it shows up as "the character suddenly goes silent" and you can't
                # [EN] tell it's a fault.
                _LOG.warning("[%s] 决策输出被截断（max_tokens=%s），"
                             "已按可闭合前缀尽力解析", self.name, meta.get('max_tokens'))
        except Exception as e:                              # noqa: BLE001
            # **别无声降级**：以前这里只 `return Action(verb="wait")`，
            # 于是"模型没接上"表现成"人物不出声"，用户看不出是故障
            # （2026-10-05：客户端没初始化，整轮 550 次决策全在这里被吞掉）。
            # [EN] **Don't degrade silently**: previously this just `return Action(verb="wait")`,
            # [EN] so "model didn't connect" showed up as "character goes silent", and the user couldn't tell it
            # [EN] was a fault
            # [EN] (2026-10-05: the client wasn't initialized, and all 550 decisions of the whole round were
            # [EN] swallowed here).
            _LOG.warning("「%s」决策失败，本轮降级为 wait：%r", self.name, e)
            return Action(verb="wait", reason=f"（决策失败：{e}）")

        # 截断时救回半截也比重降级成 wait 强（"人物不出声"最难排查）
        # [EN] When truncated, salvaging half is still better than degrading to wait ("character goes silent"
        # [EN] is the hardest to diagnose)
        result = extract_json_lenient(raw, {})
        if not result:
            _LOG.warning("「%s」决策返回的不是 JSON，降级为 wait：%r",
                         self.name, (raw or '')[:120])
            return Action(verb="wait", reason="（解析失败）")

        act = Action(
            verb=result.get("动作", "wait"),
            target=result.get("参数", {}).get("目标", ""),
            dialogue=result.get("台词", ""),
            inner_thought=result.get("内心", ""),
            reason=result.get("理由", ""),
            # ★ 思维链那一段（2026-10-07 第七轮）。宽容读法：模型可能写成
            #   `推演`/`思考`/`盘算` 之一 —— 取不到就是空串（**不算故障**：
            #   骨架在提示词里，它至少先想过一遍才开口）。
            # [EN] ★ The chain-of-thought segment (2026-10-07, seventh round). Lenient reading: the model may write
            # [EN] one of `推演`/`思考`/`盘算` -- if none is found, it's an empty string (**not counted as a fault**:
            # [EN] the skeleton is in the prompt, it at least thought once before speaking).
            think_trace=str(result.get("推演") or result.get("思考")
                            or result.get("盘算") or "").strip()[:200],
            # ★ 2026-10-14：**动作/神态的描写**（`"细节": "…"`）。
            #   宽容读法同 `think_trace`（模型可能写成 `动作细节`/`描写`）——
            #   取不到就是空串，`_action_text` 照样落回骨架（**不算故障**）。
            # [EN] ★ 2026-10-14: **the action / expression description** (`"细节": "..."`).
            # [EN] Lenient reading like `think_trace` (the model may write `动作细节`/`描写`) -- an
            # [EN] empty string still lets `_action_text` fall back to the skeleton (**not a fault**).
            detail=str(result.get("细节") or result.get("动作细节")
                       or result.get("描写") or "").strip()[:120],
        )

        # DEBUG: 决策结果
        # [EN] DEBUG: decision result
        if CFG.b("DEBUG_MODE"):
            _LOG.debug("[%s] 决策完成: %s %s 台词=%s 内心=%s 推演=%s",
                       self.name, act.verb, act.target, act.dialogue[:30] if act.dialogue else "", act.inner_thought[:30] if act.inner_thought else "", act.think_trace[:40])

        if not act.is_valid():
            _LOG.warning("%s 非法动作 %s，降为 wait", self.name, act.verb)
            act.verb = "wait"
            act.reason += "（非法动作降级）"

        # ── 反空转闸（`ANTI_IDLE_GATE`，2026-10-06）──
        # 三层目标全空的时候，`wait` / 原地动作 = 空转。这里**不替人物改主意**
        # （那等于替他做决定，比空转更糟），但要**留痕**：不记日志的话，
        # "人物一直不动"在事后完全查不出原因 —— 真机「擦 565 次」就是这么来的。
        # [EN] ── Anti-idle gate (`ANTI_IDLE_GATE`, 2026-10-06) ──
        # [EN] When all three goal layers are empty, `wait` / in-place actions = idling. Here we **don't change
        # [EN] the character's mind for him**
        # [EN] (that equals deciding for him, worse than idling), but we must **leave a trace**: without
        # [EN] logging,
        # [EN] "the character never moves" becomes completely undiagnosable after the fact -- that's exactly
        # [EN] where the real-machine "wiped 565 times" came from.
        if CFG.b("ANTI_IDLE_GATE") and self._all_goals_empty():
            kind = idle_kind(act)
            if kind:
                _LOG.warning("「%s」三层目标全空，却输出空转动作（%s）—— "
                             "反空转闸已记录；导演该给他一件事做",
                             self.name, kind)
                act.reason += "（反空转闸：三层目标全空）"

        # 记录行动
        # [EN] Record the action
        self._add_memory("action", f"{self.name}{_verb_desc(act)}",
                         importance=6 if act.verb == "speak" else 4)
        return act

    # ── 对话（前台）─────────────────────────────────────────────────────
    # [EN] ── Dialogue (foreground) ─────────────────────────────────────────────────────
    @MODELS.agent('actor')
    async def talk(self, other: str, topic: str = "", max_turns: int = 0) -> list[str]:
        """与另一人物对话，返回对话行列表。
                English:
        Talk with another character, return list of dialogue lines.
        """
        # `DIALOGUE_MIN_TURNS`：**至少说几轮**（以前零读取）。
        # 与 `DIALOGUE_MAX_TURNS` 一起构成区间：少于下限就继续，
        # 到上限为止。下限定得比上限高时**上限说了算**（不然会死循环）。
        # [EN] `DIALOGUE_MIN_TURNS`: **at least how many turns to speak** (previously read zero times).
        # [EN] Together with `DIALOGUE_MAX_TURNS` it forms a range: keep going if below the lower bound,
        # [EN] until the upper bound. When the lower bound is set higher than the upper bound, **the upper
        # [EN] bound wins** (otherwise it loops forever).
        lo = max(1, CFG.i("DIALOGUE_MIN_TURNS"))
        hi = max(1, CFG.i("DIALOGUE_MAX_TURNS"))
        max_turns = max_turns or max(lo, hi)
        max_turns = max(min(max_turns, hi), min(lo, hi))
        other_ps = self.world.get_person(other)
        if not other_ps:
            return []

        lines: list[str] = []
        persona_a = self._persona_prompt()
        persona_b = self._other_persona_prompt(other_ps)
        scene = f"场景：{self.world.scene}，时间：{self.world.clock_display()}"
        # 台词是**直接落到纸面上的话**，风格禁词表与作者的写作规则对它约束最紧
        # （2026-10-06 补：以前这两条 prompt 里只有人格卡和场景，规则一概不知道）。
        # [EN] Lines are **words that land directly on the page**; the style forbidden-word list and the
        # [EN] author's writing rules constrain it most tightly
        # [EN] (added 2026-10-06: previously these two prompts only had the persona card and scene, and knew
        # [EN] nothing of the rules).
        world_line = self.world.world_prefix()

        prompt_a = f"""你是「{self.name}」，正在和「{other}」说话。
{persona_a}
{world_line}
{scene}
{f'话题/情况：{topic}' if topic else ''}
请说一句符合你性格的话（只说一句，不要旁白）。"""

        prompt_b = f"""你是「{other}」，正在和「{self.name}」说话。
{persona_b}
{world_line}
{scene}
对方刚说：{lines[-1] if lines else '（刚见面）'}
{f'话题/情况：{topic}' if topic else ''}
请说一句符合你性格的话（只说一句，不要旁白）。"""

        current_speaker = self.name
        for i in range(max_turns):
            msg = prompt_a if current_speaker == self.name else prompt_b
            if current_speaker == other and lines:
                msg = msg.replace("（刚见面）", lines[-1])
            messages = [{"role": "user", "content": msg}]
            try:
                raw = await llm.chat("daily", messages, purpose="dialogue", temperature=0.8)
            except Exception:
                raw = ''
            # 清理格式
            # [EN] Clean up the format
            line = (raw or '').strip().strip('"「」""''')
            # ★★ 2026-10-14（用户）：「我看现在的推演结果 是大量的对话 …不应该只有对话」——
            #   **说不出话就收尾**，不再硬凑满轮数。
            #   改之前：`for i in range(max_turns)` **无条件产满** ——
            #     调用方（`sim/loop._process_action`）不传 `max_turns`，
            #     于是它取 `max(lo, hi)` = `DIALOGUE_MAX_TURNS`（**8 句**）；
            #     模型一句都答不出来时还要塞 8 句"（X 沉默了）"。
            #   这就是"每隔一拍就冒 8 句台词"的**直接来源**。
            #   现在：模型没给出话 ⇒ **这一轮交流到此为止**（那本来就是
            #   "话不投机/无话可说"的自然结果）；一句都没产时才补一句"沉默了"，
            #   免得返回空列表让上层以为出了故障。
            # ⚠ `lo`（`DIALOGUE_MIN_TURNS`）的语义**没变**（"至少来回几轮"）：
            #   它在下面 `max(min(max_turns, hi), min(lo, hi))` 那行参与计算；
            #   这次只是让"够了下限之后可以提前收尾"成为可能。
            # [EN] ★★ 2026-10-14 (user): "I see the deduction output is mostly dialogue ...
            # [EN] should not be only dialogue" -- **when there is nothing to say, wrap up**;
            # [EN] no more padding out to a full turn count.
            # [EN] Before: `for i in range(max_turns)` **unconditionally produced the full count** --
            # [EN]   the caller (`sim/loop._process_action`) passes no `max_turns`, so it used
            # [EN]   `max(lo, hi)` = `DIALOGUE_MAX_TURNS` (**8 lines**); when the model could not
            # [EN]   answer at all it still stuffed in 8 "（X fell silent）" lines.
            # [EN]   That is the **direct source** of "every beat spits out 8 lines of dialogue".
            # [EN] Now: if the model produced nothing => **this exchange ends here** (which is the
            # [EN]   natural outcome of "nothing more to say"); only when not a single line was
            # [EN]   produced do we add one "fell silent", so the caller does not mistake an empty
            # [EN]   list for a fault.
            # [EN] ⚠ The semantics of `lo` (`DIALOGUE_MIN_TURNS`) are **unchanged** ("at least how
            # [EN]   many exchanges"); it still participates in the
            # [EN]   `max(min(max_turns, hi), min(lo, hi))` line. This change only makes "wrap up
            # [EN]   early once the lower bound is satisfied" possible.
            if not line:
                if not lines:
                    lines.append(f"「（{current_speaker} 沉默了）」")
                break
            lines.append(f"「{line}」")
            current_speaker = other if current_speaker == self.name else self.name

        # 记录对话
        # [EN] Record the dialogue
        self._add_memory("dialogue", f"与{other}对话：{' '.join(lines[:3])}",
                         importance=7)
        return lines

    # ── 反思 ──────────────────────────────────────────────────────────
    # [EN] ── Reflection ──────────────────────────────────────────────────────────
    @MODELS.agent('actor')
    async def reflect(self) -> str | None:
        """反思：累计重要性过阈值触发，每日上限 REFLECTION_MAX_PER_DAY。
                English:
        Reflection: triggered when cumulative importance crosses a threshold, daily cap
        REFLECTION_MAX_PER_DAY.
        """
        if self._today_reflections >= CFG.i("REFLECTION_MAX_PER_DAY"):
            return None
        memories = self.db.retrieve_memory(self.name, 20)
        total_importance = sum(m.get("importance", 0) for m in memories)
        if total_importance < CFG.i("REFLECTION_THRESHOLD"):
            return None

        mem_text = "\n".join(f"- {m['content']}" for m in memories[-10:])
        messages = [{"role": "user",
                     "content": f"你是「{self.name}」。{self._rules_line()}"
                                f"最近的经历：\n{mem_text}\n\n"
                                f"请用第一人称做一段简短的内心反思（50字以内，符合性格）。"}]
        try:
            text = await llm.chat("cheap", messages, purpose="reflect", temperature=0.6)
        except Exception:
            return None
        text = text.strip().strip('"「」""''')
        self._add_memory("reflection", f"（内心反思）{text}", importance=8)
        self._today_reflections += 1
        return text

    # ── 计划 ──────────────────────────────────────────────────────────
    # [EN] ── Plan ──────────────────────────────────────────────────────────
    @MODELS.agent('actor')
    async def make_plan(self) -> dict | None:
        """今日计划。**跨天时由 `RunLoop` 并发给每个前台人物调一次**（2026-10-06 接上）。

        这个方法写好很久了，但**从来没有人调用** —— 人物的 `current_goal` 永远停在
        设定里那句静态的话上，行动全靠导演随机戳（"人物在世界里空转"的另一半原因）。
        现在：跨天时算一次今天的计划 → 写进 `ps.day_plan` → 决策 prompt 里带上，
        人物才有"我今天打算干什么"这个内在动力。
        
                English:
        Today's plan. **On day change, `RunLoop` concurrently calls this once for each foreground
        character** (wired up 2026-10-06).
                This method was written long ago, but **nobody ever called it** —— the character's `current_goal` always stays stuck
                on that static line in the settings, and actions all rely on the director randomly poking (the other half of the reason for "characters idling in the world").
                Now: on day change, compute today's plan once → write to `ps.day_plan` → include it in the decision prompt,
                then the character has this inner drive of "what I plan to do today".
        """
        if not CFG.b("PLANNING_ENABLED"):
            return None
        memories = self.db.retrieve_memory(self.name, 5, now_game_min=self._game_min())
        mem_text = "\n".join(f"- {m['content']}" for m in memories)
        messages = [{"role": "user",
                     "content": f"你是「{self.name}」。{self._rules_line()}"
                                f"{self._story_so_far(4)}"
                                f"最近记忆：\n{mem_text}\n\n"
                                f"今天是第 {self.world.clock.day} 天。"
                                # `PLAN_BLOCK_MINUTES`：时段块**每块多长**（以前零读取）
                                # [EN] `PLAN_BLOCK_MINUTES`: **how long each time-slot block is** (previously read zero times)
                                f"请把今天切成每块约 {CFG.i('PLAN_BLOCK_MINUTES')} 分钟的时段，"
                                f"用 JSON 回答今天的计划："
                                f"{{\"日计划\": [\"...\", \"...\"], "
                                f"\"时段块\": [{{\"时段\": \"...\", \"行动\": \"...\"}}]}}"}]
        try:
            raw = await llm.chat("cheap", messages, purpose="plan", json_mode=True)
        except Exception:                                    # noqa: BLE001
            return None
        data = extract_json_lenient(raw, None)
        if not isinstance(data, dict):
            return None
        plan = data.get("日计划") or []
        if isinstance(plan, str):
            plan = [plan]
        plan = [str(x).strip() for x in plan if str(x).strip()][:8]
        if plan:
            self.ps.day_plan = plan
        # 第一个时段块的"行动"可以当今天的当前目标；没有就不动原来的 goal
        # [EN] The "action" of the first time-slot block can serve as today's current goal; if absent, leave
        # [EN] the original goal unchanged
        blocks = data.get("时段块") or []
        if isinstance(blocks, list) and blocks and isinstance(blocks[0], dict):
            act = str(blocks[0].get("行动") or "").strip()
            if act and len(act) <= 40:
                self.ps.current_goal = act
        return data

    # ── 群聊轮转（`GROUP_CHAT_MAX`，设计稿 §五）─────────────────────────
    # [EN] ── Group chat rotation (`GROUP_CHAT_MAX`, design doc §5) ─────────────────────────
    @MODELS.agent('actor')
    async def speak_in_group(self, others: list[str], heard: list[str],
                             topic: str = "") -> str:
        """在同场多人里**说一句**（群聊轮转的一拍）。返回台词，空串=不说。

        与 `talk()` 的分工：`talk` 是**一对一**那两人的往返；这里是**三人以上**时
        导演指名的轮转 —— 一次只出一句，谁接谁由调用方定（`GROUP_CHAT_MAX` 封顶）。
        
                English:
        **Say one line** in a multi-person scene (one beat of group chat rotation). Returns the line,
        empty string = don't speak.
                Division of labor with `talk()`: `talk` is the **one-on-one** back-and-forth of those two; here it's the **three-or-more**
                director-named rotation —— only one line per call, who follows whom is decided by the caller (capped by `GROUP_CHAT_MAX`).
        """
        who = "、".join(others[: max(1, CFG.i("GROUP_CHAT_MAX"))]) or "（没人）"
        heard_txt = "\n".join(heard[-4:]) or "（还没人开口）"
        prompt = (f"你是「{self.name}」，此刻同场还有：{who}。\n"
                  f"{self._persona_prompt()}\n{self._rules_line()}"
                  f"场景：{self.world.scene}，时间：{self.world.clock_display()}\n"
                  + (f"话题/情况：{topic}\n" if topic else "")
                  + f"刚才有人说：\n{heard_txt}\n\n"
                  f"请说**一句**符合你性格的口语（十几二十字以内）；"
                  f"不想插话就回空。**只输出那句话本身**，不要旁白、不要引号。")
        rep = await ask("cheap", [{"role": "user", "content": prompt}],
                        purpose="group_chat", want="text", temperature=0.8,
                        max_tokens=120, min_chars=2, default="", retry=False)
        if not rep.ok:
            return ""
        v = rep.value
        if isinstance(v, (list, tuple)):
            v = "".join(str(x) for x in v)
        return str(v or "").strip().strip('"“”')[:60]

    # ── 规则前缀 ──────────────────────────────────────────────────────
    # [EN] ── Rule prefix ──────────────────────────────────────────────────────
    def _rules_line(self) -> str:
        """顶级规则的单段前缀（给省思 / 计划这类短 prompt 用）。

        与 `world_prefix()` 的分工：这里**只要规则**，不重复世界观 ——
        这两处调用只看"我该怎么想、该怎么做"，世界观对它们没增量，
        而规则（"谁动了更漏谁就得说清行踪"）是真的会改变结论的。
        
                English:
        Single-segment prefix for top-level rules (for short prompts like reflection / plan).
                Division of labor with `world_prefix()`: here **only rules**, no repeating the worldview ——
                these two call sites only look at "how should I think, how should I act", the worldview has no delta for them,
                whereas the rules ("whoever moves the water clock must account for their whereabouts") really do change the conclusion.
        """
        txt = (self.world.rules_text or "").strip()
        if not txt:
            return ""
        return f"\n[顶级规则·不可违背]\n{txt[:800]}\n"

    # ── 记忆压缩（`SUMMARIZE_MEMORY_AFTER`，设计稿 §2.4）───────────────
    # [EN] ── Memory compression (`SUMMARIZE_MEMORY_AFTER`, design doc §2.4) ───────────────
    async def _compact_if_needed(self, dyn: list, fixed: str, semi: str,
                                 tail: str) -> tuple:
        """**贴到触发线就主动压**，返回 `(打包结果, 说明)`。

        ★★ 2026-10-10（用户点名）：「不是要提醒我自己去调整 而是系统要提示我
           并且进行主动压缩」。所以这里不是"记一条日志让作者去调参数"，
           而是**当场动手压**。

        ⚠⚠ **必须在 `pack()` 之前跑。** 第一版写成了"先 pack、发现超预算再压"，
          结果是**压了个寂寞**：`pack()` 自己会先按预算**硬裁**
          （`trim_dynamic` 从尾部整块丢掉），轮到压缩时内容块已经被削短，
          `split_keep_recent` 一看"不足 6 行"直接不切 ⇒ 一次都没压成。
          而"丢掉"和"折成摘要"是两回事 —— **丢掉是真的没了**。

        压什么 —— **只压"内容块"**
        --------------------------
        Agent 的上下文分两类，压缩只许碰第一类：

          · **内容块**（会随拍长大）——`最近记忆…` 与 `当前情况：…`。**要压的**。
          · **指令块**（长度恒定，是给模型的规矩）——演员手艺、去 AI 清单、
            思维链骨架。**一个字都不能动** —— 把它们折成摘要，等于把
            "该怎么演"从提示词里删掉。

        ⚠ 另一个踩过的判断：一开始去压的是**记忆表**（`compact_memory` 折条数）。
          那条路对这里**几乎没用** —— Agent 每次只取 5 条记忆进上下文
          （`memories[:5]`），撑大上下文的根本不是它，而是**不断累积的
          `当前情况`**（这一场戏说到现在的全部）。所以现在压的是块本身。

        压缩比例（照 WorkBuddy 自己的上下文压缩设计搬来的四个数）
        -------------------------------------------------------
        | 旋钮 | 默认 | 管什么 |
        |---|---|---|
        | `CTX_COMPACT_AT` | 0.80 | **触发线**：用到预算的八成八就动手（不等到撞墙） |
        | `CTX_COMPACT_KEEP` | 0.35 | **保留比例**：最近这段**原文不动**，更老的折成摘要 |
        | `CTX_COMPACT_TARGET` | 0.50 | **目标水位**：压完落回五成以下，否则下一拍又触发（抖振） |
        | `CTX_COMPACT_MAX_ROUNDS` | 2 | 最多压几轮，防跑飞 |

        ★ **"保留最近一段"是这套东西里最要紧的一条**：故事是**往前接**的，
          刚刚发生的事一个字都不能丢；被折掉的永远是更早的那一段。
        ★ 折出来的摘要**按内容缓存**（`self._compact_cache`）：块是逐拍长大的，
          同一个"较早那一段"会被反复折 —— 不缓存就是每拍一次多余的模型调用，
          而且摘要叠摘要会越折越糊。
        
                English:
        **Compress proactively once it hits the trigger line**, returns `(packed result, explanation)`.
                ★★ 2026-10-10 (user-named): "it's not about reminding myself to go adjust, it's that the system should prompt me
                   and perform proactive compression". So here it's not "log a line for the author to tune parameters",
                   but **do the compression right there and then**.
                ⚠⚠ **Must run before `pack()`.** The first version wrote it as "pack first, and if over budget then compress",
                  the result was **a compression for nothing**: `pack()` itself **hard-trims** by budget first
                  (`trim_dynamic` drops whole blocks from the tail), by the time compression runs the content block has already been shortened,
                  `split_keep_recent` sees "fewer than 6 lines" and just doesn't split ⇒ not a single compression succeeded.
                  And "dropping" and "folding into a summary" are two different things —— **dropping is really gone**.
                What to compress —— **only the "content block"**
                --------------------------
                An Agent's context is of two kinds, compression may only touch the first:
                  · **Instruction block** (constant length, rules for the model) —— actor craft, de-AI checklist,
                    chain-of-thought skeleton. **Not a single character may be moved** —— folding them into a summary is equivalent to
                    deleting "how to act" from the prompt.
                ⚠ Another judgment I've stepped on: at first I was compressing the **memory table** (`compact_memory` folding row count).
                  That path is **almost useless** here —— the Agent only takes 5 memories into context each time
                  (`memories[:5]`), it's not what's inflating the context at all, it's the **ever-accumulating
                  `当前情况`** (the whole of this scene up to now). So now what's compressed is the block itself.
                Compression ratio (the four numbers carried over from WorkBuddy's own context-compression design)
                -------------------------------------------------------
                | knob | default | what it governs |
                |---|---|---|
        """
        import hashlib as _hl  # noqa: F401  （缓存键在 `_summarize_old` 里算）
        # [EN] noqa: F401  (the cache key is computed in `_summarize_old`)
        from llm import context as CTX                            # noqa: PLC0415
        budget = CFG.i("MAX_CONTEXT_TOKENS")
        try:
            at = float(CFG.f("CTX_COMPACT_AT"))
            keep_ratio = float(CFG.f("CTX_COMPACT_KEEP"))
            target = float(CFG.f("CTX_COMPACT_TARGET"))
            rounds_max = max(1, CFG.i("CTX_COMPACT_MAX_ROUNDS"))
        except Exception:                                        # noqa: BLE001
            return CTX.pack(fixed, semi, dyn, tail, budget=budget), ""

        def _raw(blocks: list) -> int:
            """**未裁剪**的原始体积（压缩前有效果，就看这个数）。
                        English:
            **Unclipped** raw size (compression only matters if this number shows it).
            """
            return CTX.estimate('\n'.join([fixed, semi, *blocks, tail]))

        before = _raw(dyn)
        if budget <= 0 or before < budget * at:
            # 没到触发线 ⇒ 一次都不压（不做无用的模型调用），直接按老路打包
            # [EN] Below the trigger line => compress zero times (don't make useless model calls), just pack the
            # [EN] old way
            return CTX.pack(fixed, semi, dyn, tail, budget=budget), ""

        #: 只压这些前缀开头的块（内容块）。**指令块一个都不碰**。
        # [EN] : only compress blocks starting with these prefixes (content blocks). **Don't touch a single
        # [EN] instruction block**.
        _content = ('最近记忆', '当前情况')
        notes: list[str] = []
        cur_dyn = list(dyn)
        for _ in range(rounds_max):
            changed = False
            for i, blk in enumerate(cur_dyn):
                if not any(str(blk)[:8].startswith(p) for p in _content):
                    continue
                old, recent = CTX.split_keep_recent(str(blk), keep_ratio)
                if not old.strip():
                    continue
                summary = await self._summarize_old(old)
                if not summary:
                    continue
                cur_dyn[i] = f'（更早的事·已压缩）{summary}\n{recent}'
                changed = True
            if not changed:
                notes.append("没有可压的块了（剩下的都太短，或大头不在内容块上）")
                break
            if _raw(cur_dyn) <= budget * target:
                break
        after = _raw(cur_dyn)
        if not notes and after >= before:
            return CTX.pack(fixed, semi, dyn, tail, budget=budget), ""
        note = "；".join(notes) or f"折掉了较早的那一段（保留最近 {keep_ratio:.0%}）"
        _LOG.warning("[%s] 上下文主动压缩：%s（%d → %d token / 预算 %d）",
                     self.name, note, before, after, budget)
        #: 交给主循环播报（Agent 自己没有向界面说话的路子）。
        # [EN] : hand off to the main loop for narration (the Agent itself has no way to speak to the UI).
        self.last_compaction = {'note': note, 'before': before,
                                'after': after, 'budget': budget}
        return CTX.pack(fixed, semi, cur_dyn, tail, budget=budget), note

    @MODELS.agent('memory')
    async def _summarize_old(self, old: str) -> str:
        """把一段较早的上下文压成两三句（拿不到就**用原文前几句兜底**）。

        ⚠ 兜底**不能是空串**：空串会让调用方以为"没压成"，于是一轮又一圈地
          重试（真跑起来就是每拍多几次模型调用）——而"压不动"和"压出来是空的"
          是两件事。这里宁可把原文的开头几句搬过来，也不返回空。
        
                English:
        Compress an earlier piece of context into two or three sentences (if unavailable, **fall back to
        the first few sentences of the original text**).
                ⚠ The fallback **must not be an empty string**: an empty string makes the caller think "it wasn't compressed", so it retries
                  round after round (in a real run that means several extra model calls per tick) — and "can't compress" and "compressed to empty"
                  are two different things. Here it's better to copy the first few sentences of the original text over than to return empty.
        """
        key = hashlib.sha1(old.encode('utf-8', 'replace')).hexdigest()
        cached = self._compact_cache.get(key)
        if cached:
            return cached
        prompt = (
            f"下面是「{self.name}」这一场戏**较早**那一段的经过（按时间从早到晚）。"
            f"请压成 **2~3 句**（总计 ≤ 120 字）：只留还会影响后文的人物、"
            f"关系、已经说出口的话与未了结的事；重复的寒暄、走动、客套一律丢掉。"
            f"不要编号、不要解释，只输出那几句话。\n\n{old[:4000]}")
        summary = ""
        try:
            rep = await ask("cheap", [{"role": "user", "content": prompt}],
                            purpose="ctx_compact", want="text", temperature=0.3,
                            max_tokens=400, min_chars=4, default="", retry=False)
            if rep.ok:
                v = rep.value
                if isinstance(v, (list, tuple)):
                    v = "".join(str(x) for x in v)
                summary = str(v or "").strip()[:300]
        except Exception as e:                                   # noqa: BLE001
            _LOG.info("「%s」上下文压缩调用失败（%r），改用原文前几句", self.name, e)
        if not summary:
            # 兜底：原文的最前面几句（**内容还在**，只是不再逐条）
            # [EN] Fallback: the first few sentences of the original text (**the content is still there**, just no
            # [EN] longer item-by-item)
            head = [ln for ln in old.split('\n') if ln.strip()][:4]
            summary = "；".join(head)[:300]
        if summary:
            self._compact_cache[key] = summary
            #: 缓存别无限长（一整天下来块是逐拍长的，键会越来越多）
            # [EN] : don't let the cache grow unbounded (over a whole day blocks grow beat by beat, and keys pile
            # [EN] up)
            if len(self._compact_cache) > 64:
                for k in list(self._compact_cache)[:32]:
                    self._compact_cache.pop(k, None)
        return summary

    async def compact_memory(self, keep: int | None = None, *,
                             force: bool = False) -> dict:
        """记忆条数超过 `SUMMARIZE_MEMORY_AFTER` 时，把**最老的一批**压成一条。

        为什么必须做：记忆是**只增不减**的（`add_memory` 每拍都写）。
        跑到第十天，一个人物的 `memory` 表能攒到上千条 ——
        检索虽然只取 top-K，但**表本身**会让每次 `ORDER BY ts DESC LIMIT` 变慢，
        更要紧的是"这个人经历过的前几天"里那些低分记忆**永远检索不到**，
        等于没发生过。压成一条摘要，它就重新进得了检索窗口。

        三档降级（与设计稿的 `IMPORTANCE_SCORING` 同一思路：先规则、再 LLM）：
          · 拿不到 LLM → **用原文拼一条**（绝不丢内容，只是不再逐条）；
          · 没有可压的 → 直接返回 `{'skipped': True}`；
          · 写不进去 → 记日志，**不删原文**（宁可多占地方，也别把记忆弄丢）。

        `keep`：压缩后保留多少条**最近**的记忆（默认 `MEMORY_RETRIEVE_K × 4`，
        给检索留足余地；`REFERENCE_INJECT_MAX` 那类"给人看"的不用管）。

        `force=True`：**跳过条数阈值**，直接压。给"上下文贴到警戒线"那条路用
        （`_compact_if_needed`）——
        ⚠ 那条路是按 **token** 判的，而这里按**条数**（`SUMMARIZE_MEMORY_AFTER`）。
          两者不是一回事：上下文可能被别的东西撑满（很长的设定前缀、很长的
          `[刚才]`），而记忆才几十条 —— 那时按条数判会直接 `skipped`，
          "主动压缩"就成了一句空话。所以那条路必须有权限绕过它。
        
                English:
                （`_compact_if_needed`）——
        """
        threshold = max(0, CFG.i("SUMMARIZE_MEMORY_AFTER"))
        if threshold <= 0 and not force:
            return {"skipped": True, "why": "SUMMARIZE_MEMORY_AFTER=0（关）"}
        try:
            total = self.db.count_memories(self.name)
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning("「%s」记忆计数失败：%r", self.name, e)
            return {"skipped": True, "why": f"计数失败：{e!r}"}
        if total <= threshold and not force:
            return {"skipped": True, "why": f"还没到阈值（{total} ≤ {threshold}）"}
        keep = int(keep if keep is not None
                   else max(8, CFG.i("MEMORY_RETRIEVE_K") * 4))
        drop_n = total - max(1, keep)
        if drop_n <= 0:
            return {"skipped": True, "why": "没有可压的（keep ≥ 总数）"}
        rows = self.db.oldest_memories(self.name, drop_n)
        if not rows:
            return {"skipped": True, "why": "取不到老记忆"}
        text = await self._digest(rows)
        if not text:
            return {"skipped": True, "why": "压缩结果为空（原文保持不动）"}
        # ⚠ 顺序要紧：**先删后写**失败的话会丢记忆；所以**先写新的、再删旧的**，
        #   最坏情况是"多一条摘要 + 老的还在"（重复但没丢），可以接受。
        # [EN] ⚠ Order matters: **delete-then-write** would lose memory on failure; so **write the new first,
        # [EN] then delete the old**,
        # [EN] the worst case is "one extra summary + the old one still there" (duplicate but nothing lost),
        # [EN] which is acceptable.
        try:
            self.db.add_memory(self.name, f"（早先的经历·已压缩）{text}",
                               "summary", 6.0, self._game_min())
            gone = self.db.drop_memories([int(r["id"]) for r in rows])
        except Exception as e:                                  # noqa: BLE001
            _LOG.warning("「%s」记忆压缩写回失败（原文保持不动）：%r", self.name, e)
            return {"skipped": True, "why": f"写回失败：{e!r}"}
        _LOG.info("「%s」记忆压缩：%d → 1（删了 %d 条，水位 %d）",
                  self.name, len(rows), gone, total)
        return {"ok": True, "folded": len(rows), "dropped": gone, "total_before": total}

    @MODELS.agent('memory')
    async def _digest(self, rows: list[dict]) -> str:
        """把一批老记忆压成 2~3 句。拿不到就**用原文拼**（绝不丢内容）。
                English:
        Compress a batch of old memories into 2~3 sentences. If unavailable, **splice from the original
        text** (never drop content).
        """
        lines = [f"- [{r.get('type', '?')}] {r.get('content', '')}" for r in rows]
        body = "\n".join(lines)
        prompt = (f"下面是「{self.name}」早先的一批经历（按时间从早到晚）。"
                  f"请压成 **2~3 句**（总计 ≤ 100 字）的回顾，"
                  f"只留还会影响后文的人物、关系与未了结的事；"
                  f"琐碎的走动和寒暄一律丢掉。不要编号、不要解释，只输出那几句话。\n\n"
                  f"{body[:3000]}")
        try:
            rep = await ask("cheap", [{"role": "user", "content": prompt}],
                            purpose="memory_compact", want="text",
                            temperature=0.3, max_tokens=400, min_chars=6,
                            default="", retry=False)
            if rep.ok:
                v = rep.value
                if isinstance(v, (list, tuple)):
                    v = "".join(str(x) for x in v)
                v = str(v or "").strip()
                if v:
                    return v[:300]
            _LOG.info("「%s」记忆压缩没拿到模型结果（%s），改用原文拼接",
                      self.name, "；".join(rep.notes) or "空正文")
        except Exception as e:                                  # noqa: BLE001
            _LOG.info("「%s」记忆压缩调用失败（%r），改用原文拼接", self.name, e)
        # 降级：原文拼接（前 12 条，够进检索窗口就行）
        # [EN] Degradation: concatenate the original text (first 12 items, enough to fit in the retrieval
        # [EN] window)
        return "；".join(str(r.get("content") or "")[:40] for r in rows[:12])[:400]

    # ── 时间 / 双记忆 ──────────────────────────────────────────────────
    # [EN] ── Time / dual memory ──────────────────────────────────────────────────
    def _game_min(self) -> float:
        """当前**故事时间**（分钟，从第 1 天 00:00 起）。

        记忆检索与计划都按它排序 —— 不是真实时间（见 `DB.retrieve_memory` 的说明）。
        
                English:
        Current **story time** (minutes, starting from day 1 00:00).
                Memory retrieval and planning both sort by it — not real time (see the note in `DB.retrieve_memory`).
        """
        return float(self.world.clock.minutes + self.world.clock.day * 1440)

    def _story_so_far(self, k: int = 6) -> str:
        """前情提要（**长期记忆**）：最近几天的故事梗概。

        双记忆的分工（2026-10-06 加）：
          · 「最近记忆」= 短期，细颗粒（我刚刚说了什么），条数受 `MEMORY_RETRIEVE_K` 限；
          · 「前情提要」= 长期，粗颗粒（第三天出过什么事），跨天累积、不随窗口滑走。

        只有短期那一半时，推到第十天的人物对前九天一无所知 ——
        这正是"人物前后不一、把早已了结的事当新闻"的来源。
        
                English:
        Previously on (**long-term memory**): a recap of the last few days of the story.
                Division of labor between the two memories (added 2026-10-06):
                  · "recent memory" = short-term, fine-grained (what I just said), count limited by `MEMORY_RETRIEVE_K`;
                  · "previously on" = long-term, coarse-grained (what happened on day three), accumulates across days and does not slide away with the window.
                With only the short-term half, a character pushed to day ten knows nothing about the first nine days —
                this is exactly the source of "characters being inconsistent and treating long-settled matters as news".
        """
        try:
            rows = self.db.get_summaries(k)
        except Exception:                                    # noqa: BLE001
            return ""
        if not rows:
            return ""
        lines = [f"第 {r.get('game_day', '?')} 天：{str(r.get('text') or '').strip()}"
                 for r in rows if str(r.get('text') or '').strip()]
        return ("\n[前情提要]\n" + "\n".join(lines) + "\n") if lines else ""

    def _plan_line(self) -> str:
        """今日计划（跨天时算一次，见 `make_plan`）。

        ⚠ **两种形态都要认**（2026-10-07 修的一处真 bug）：
          · 导演派过活的人，`day_plan` 是**字符串** ——
            `sim/loop._compose_day()` 写的是 `'；'.join(tasks)`；
          · 自己排计划的人，`day_plan` 是**列表** —— `Agent.make_plan()` 写的是 list。

        以前这里只按序列迭代，于是字符串被**逐字**拆开，提示词里出现

            [今日计划]
            - 把
            - 少
            - 了
            - 的

        这种东西 —— 而它恰好只发生在**导演派过活的人**身上（自己排计划的人
        是列表，看着一切正常），所以最难怀疑到。演示模式跑一遍就能看到。
        
                English:
                    `sim/loop._compose_day()` 写的是 `'；'.join(tasks)`；
                    - 把
                    - 少
                    - 了
                    - 的
                This kind of thing -- and it happens to occur precisely on **the people the director has assigned work to** (people who plan their own schedules
                are lists and look fine), so it's the hardest to suspect. Running it once in demo mode makes it visible.
        """
        raw = getattr(self.ps, "day_plan", None)
        if isinstance(raw, str):
            plan = [x.strip() for x in raw.replace(';', '；').split('；')
                    if x.strip()]
        else:
            plan = [str(x).strip() for x in (raw or []) if str(x).strip()]
        if not plan:
            return ""
        return "\n[今日计划]\n" + "\n".join(f"- {x}" for x in plan[:6]) + "\n"

    def _goal_line(self) -> str:
        """**这一站要走完的是什么**（当前进度节点）。

        2026-10-06 补：以前人物决策时**完全看不到进度表** —— 只有导演知道
        "现在该推进哪个节点"，于是人物的行动跟故事要走的线可以毫无关系
        （真机日志里 126 次决策全是"擦、看、账"）。
        这就是"目标金字塔"里的**阶段主线**那层，落地点就在这一行。
        
                English:
        **What must be completed at this stop** (the current progress node).
                2026-10-06 addendum: Previously, when characters made decisions they **could not see the progress table at all** -- only the director knew
                "which node should be advanced now", so a character's actions could be completely unrelated to the storyline the story needed to follow
                (in the real-machine logs, all 126 decisions were "wipe, look, ledger").
                This is the **stage mainline** layer in the "goal pyramid", and its landing point is exactly this line.
        """
        info = None
        try:
            info = self.world.current_node_info()
        except Exception:                                       # noqa: BLE001
            info = None
        if not info:
            return ""
        name = str(info.get("名称") or "").strip()
        summary = str(info.get("概要") or "").strip()
        judge = str(info.get("完成判据") or "").strip()
        if not (name or summary):
            return ""
        parts = [f"\n[这一站] {name}"]
        if summary:
            parts.append(f"（{summary[:80]}）")
        if judge:
            parts.append(f" 走完的样子：{judge[:60]}")
        return "".join(parts) + "\n"

    def _mission_line(self) -> str:
        """〔此刻〕导演派的活（`director.engine.dispatch` 每 N 拍派一次）。

        派的是**要达成什么**，不是怎么做 —— 所以这里照原样给人物看，
        不加"你应该……"这类指导语。
        
                English:
        〔This moment〕The work assigned by the director (`director.engine.dispatch` dispatches once every
        N beats).
                What is assigned is **what to achieve**, not how to do it -- so here it is shown to the character as-is,
                without adding guidance like "you should...".
        """
        what = str(getattr(self.ps, "mission", "") or "").strip()
        return f"\n[此刻] {what}\n" if what else ""

    def _arc_line(self) -> str:
        """〔这一程〕进度表里**再往前走是哪儿**（当前节点的下一个）。

        为什么值得给：只给"这一站"时，人物不知道这条线往哪去，行动容易只顾眼前；
        给出下一站，他的选择才有"往那个方向使劲"的余地（也顺带回应了
        "这一站走完我就没目标了"这种空转）。
        
                English:
        〔This journey〕**Where to go next** in the progress table (the next node after the current one).
                Why it's worth providing: when only "this stop" is given, the character doesn't know where this line is heading, and actions easily focus only on the immediate moment;
                giving the next stop leaves room for his choices to "push in that direction" (and also incidentally addresses
                the kind of idling like "once I finish this stop I'll have no goal").
        """
        try:
            nodes = list(getattr(self.world, "progress_nodes", None) or [])
            cur = getattr(self.world, "current_node", "")
        except Exception:                                       # noqa: BLE001
            return ""
        idx = next((i for i, n in enumerate(nodes)
                    if str(n.get("id") or "") == str(cur or "")), -1)
        if idx < 0 or idx + 1 >= len(nodes):
            return ""
        nxt = nodes[idx + 1] or {}
        name = str(nxt.get("名称") or "").strip()
        if not name:
            return ""
        summary = str(nxt.get("概要") or "").strip()
        return f"\n[这一程] 往后是「{name}」" + (f"（{summary[:60]}）" if summary else "") + "\n"

    def _desire_line(self) -> str:
        """〔你想要的〕人物卡里那条**自己的**目标（不是导演派的）。
                English:
        〔What you want〕The **own** goal in the character card (not assigned by the director).
        """
        want = str(getattr(self.ps, "current_goal", "") or "").strip()
        return f"\n[你想要的] {want}\n" if want else ""

    def _ladder_layers(self) -> list[tuple[str, str]]:
        """目标金字塔 —— 由近及远五层，返回**生效的那几层** `[(层名, 文本块)]`。

        | 层 | 名 | 来源 | 远近 |
        |---|---|---|---|
        | 1 | 此刻 | 导演派活（`mission`） | 这一拍 |
        | 2 | 这一站 | 进度节点 | 这一段剧情 |
        | 3 | 今日计划 | 跨天算的 `day_plan` | 这一天 |
        | 4 | 这一程 | 进度表的下一节点 | 这一卷 |
        | 5 | 你想要的 | 人物卡目标 | 一生 |

        `GOAL_LADDER` 决定给几层（**从最里层往外取** —— 越近的越该看得见）。
        空的那层**不占名额**：不给自己派活、也没有计划的人，照样能看到五层里
        他真正有的那几层，而不是白白浪费在一堆空标题上。
        
                English:
        Goal pyramid -- five layers from near to far, returning **the layers in effect** `[(layer name,
        text block)]`.
                | Layer | Name | Source | Range |
                |---|---|---|---|
                | 1 | This moment | Director-assigned work (`mission`) | This beat |
                | 2 | This stop | Progress node | This segment of the plot |
                | 3 | Today's plan | The cross-day `day_plan` | This day |
                | 4 | This journey | The next node in the progress table | This volume |
                | 5 | What you want | Character card goal | A lifetime |
                `GOAL_LADDER` determines how many layers to give (**take from the innermost layer outward** -- the nearer ones should be more visible).
                Empty layers **do not take up a slot**: people who have no work assigned to themselves and no plan can still see, among the five layers,
                the layers they actually have, instead of wasting it on a bunch of empty headings.
        """
        all_layers = [("此刻", self._mission_line()),
                      ("这一站", self._goal_line()),
                      ("今日计划", self._plan_line()),
                      ("这一程", self._arc_line()),
                      ("你想要的", self._desire_line())]
        want = max(2, min(5, CFG.i("GOAL_LADDER") or 3))
        return [(n, b) for n, b in all_layers[:want] if b.strip()]

    def _goal_ladder(self) -> str:
        """把生效的几层拼成提示词里的目标段。

        ★ 「今日剧本」排在金字塔**之外**（2026-10-07）：它是**框架**、不是目标 ——
          框架必须永远在眼前，不该因为 `GOAL_LADDER` 只给 2 层就被截掉。
          （与 §53.2「反空转闸故意不算此刻」同源：框架／派活是外来的，
          而金字塔问的是"他自己想做什么"。）
        
                English:
        Concatenate the layers in effect into the goal section of the prompt.
                ★ "Today's script" is placed **outside** the pyramid (2026-10-07): it is a **framework**, not a goal --
                  the framework must always be in view, and should not be truncated just because `GOAL_LADDER` gives only 2 layers.
                  (Same origin as §53.2 "the anti-idling gate deliberately does not count this moment": the framework/assigned work is external,
                  whereas what the pyramid asks is "what he himself wants to do".)
        """
        return self._frame_line() + "".join(b for _n, b in self._ladder_layers())

    def _frame_line(self) -> str:
        """**今天这一场在演什么**（导演当天写的框架）。

        用户 2026-10-07：「每个人物可以有自己的一定自由度 但是不能够一直做不相干的
        跟主线没有关系的事情 尽量每件事 每句话都跟主线有关」。

        给的是**框架**（今天要演什么 + 他分到哪几件事 + **本场戏**），**不是台词** ——
        台词也写死就成了提线木偶，那正是本项目一直在避免的。所以这里还会明说
        "框架之内你可以自由发挥"。

        两个来源都空（既没有当天剧本、也没有场次编排）时返回空串 ——
        这一天没有框架，提示词里就不出现这一段。

        ★★ 2026-10-11 补了「本场戏」那一段（`_stage_line`）：在那之前，
          剧作家的分拍表**从来没到过演员手上** —— 那是"东一句西一句、场景乱跳"
          的第一层原因，详见 `_stage_line` 的说明。
        
                English:
        **What is being performed in today's scene** (the framework the director wrote for the day).
                User 2026-10-07: "Each character can have a certain degree of freedom, but must not keep doing unrelated
                things that have nothing to do with the mainline; try to make everything, every line, related to the mainline".
        What is given is the **framework** (what to perform today + which tasks he is assigned +
        **this scene**), **not the lines** --
        if the lines were hardcoded too, it would become a marionette, which is exactly what this
        project has always avoided. So here it will explicitly say
        "within the framework you can improvise freely".
        When **both** sources are empty (no script for the day and no stage schedule), return an empty
        string -- there is no framework that day, so this section does not appear in the prompt.
        ★★ 2026-10-11 added the "this scene" block (`_stage_line`): before that, the playwright's beat
        sheet **never reached the actors** -- that is the first layer of cause behind "all over the
        place, scenes jumping around"; see the note in `_stage_line`.
        """
        ds = getattr(self.world, 'day_script', None)
        story = str(getattr(ds, 'story', '') or '').strip() if ds is not None else ''
        mine = ((getattr(ds, 'roles', {}) or {}).get(self.name) or []) if ds is not None else []
        lines: list[str] = []
        # ★★★ 2026-10-19：**剧本给到多细由自由度决定**（`agent/freedom.py`）。
        #
        #   为什么这一处是"自由 vs 照演"的总闸：`[今日剧本]` 是当天要演什么，
        #   `_stage_line()` 是**这一拍**该演什么。两个都给 = 人物在演一场排好的戏
        #   （实测结果：同一部《雪国》跑两次，文字只重合 9.7%，**骨架 62.5% 相同** ——
        #   读者读出来是"又来一遍，只是换了词"，探针 `tools/probe_divergence.py` 量的）。
        #
        #   三档见 `freedom.frame_scope()`：full = 照旧；agenda = 只给事不给分拍；
        #   brief = 只给"今天该推进哪件事"。
        #   ⚠ **不是"越松越好"**：松到 brief 时人物容易原地打转（本项目量过：
        #     删掉"必须"之后模型会停在什么都不做）。所以松的每一档都配一段许可
        #     （`freedom.license_line()`），一松一放，成对出现。
        # [EN] ★★★ 2026-10-19: **how much script to hand over is decided by the freedom knob**
        # [EN] (`agent/freedom.py`). This block is the master switch for "free vs scripted":
        # [EN] `[今日剧本]` is what to play today, `_stage_line()` is what to play **this beat**.
        # [EN] Giving both means the character performs an arranged play (measured: two runs of Snow
        # [EN] Country shared 9.7% of characters but **62.5% of the skeleton** -- "again, reworded";
        # [EN] quantified by `tools/probe_divergence.py`).
        # [EN] Three bands: full / agenda / brief. ⚠ Not "looser is better": at brief the character
        # [EN] tends to idle (measured here: removing "must" makes the model stop), so every loosened
        # [EN] band is paired with a permission block (`freedom.license_line()`).
        from agent import freedom as _FREE
        _scope = _FREE.frame_scope()
        _cap = {'full': 400, 'agenda': 160, 'brief': 0}.get(_scope, 400)
        if story and _cap:
            lines += ['\n' + ('[今日剧本]' if _scope == 'full' else '[今天要办的事]'),
                      f'- {story[:_cap]}']
            if mine:
                lines.append('分到你头上的事：' + '；'.join(str(x) for x in mine[:3]))
            if _scope == 'full':
                lines.append('（框架之内你可以自由发挥，但别做跟这件事无关的事。）')
        elif mine:
            # `brief`，或当天没有剧本但派了活：只给"该推进哪件事"
            # [EN] `brief`, or no script but assigned work: only "which matter to advance".
            lines += ['\n[你今天打算推进的事]',
                      '- ' + '；'.join(str(x) for x in mine[:3])]
        # ★★ **本场戏**（剧作家的分拍表，2026-10-11）—— 见 `_stage_line`。
        #   ⚠ 只有 `full` 给：分拍表是"这一拍该演什么"，自由度高时它正是要被拿掉的那一样。
        # [EN] ★★ **This scene** (the playwright's beat sheet). ⚠ Only in `full`: the beat sheet is
        # [EN] "what to play this beat", which is exactly what must go at higher freedom.
        if _FREE.stage_visible():
            _stage = self._stage_line()
            if _stage:
                lines.append(_stage)
        return ('\n'.join(lines) + '\n') if lines else ''

    def _stage_line(self) -> str:
        """**本场戏**那一段（剧作家的分拍表）—— 这里就是那张表**真正下达**的地方。

        作者 2026-10-11 看了运行记录之后点名："东一句西一句""小的场景没交代清楚
        就跳到新场景""场景反复切换却没有任何人物出场、动作、情节"。
        第一层原因就在这里：剧作家分好的那几拍（每拍在哪个场景、讲什么、有谁、
        要落到哪些动作、动什么道具）**从来没有进过提示词** ——
        演员只看到一段 400 字的当天梗概加上自己分到的两件事，于是各自即兴，
        接不上也就成了常态。

        现在每一拍都带：在哪儿 / 这场戏讲什么 / 该有谁 / 要落到哪些动作 /
        要动什么道具 / 情绪基调 / 演完的样子。**只给当前这一拍**（外加一句
        "下一场是什么"）—— 给全表等于把后面的戏透给他，他会去抢别人那一场。

        ⚠ 编排是从 `ds.beats` 派生的（`director.stage.StagePlan`），所以它跟
          "有没有当天剧本"是**两件事**：模型没写出 `story` 但给出了分拍时，
          这一段照样该出现 —— 因此它**不挂在上面那个 `story` 分支里**。
        ⚠ 拼不出来**绝不能影响决策**（它本来就是个"锦上添花"的框）——
          异常一律吞掉、返回空串，与"这一天没有分拍"同一条路。

            English:
        The **this scene** block (the playwright's beat sheet) -- this is where that sheet is
        **actually handed down**.

        After reading a run log on 2026-10-11 the author called out "all over the place", "small
        scenes never explained before jumping to new ones", "scenes switching with no character
        entering, no action, no plot". The first layer of cause is right here: the playwright's beats
        (which scene, what it is about, who is in it, what actions it should land, which props) **had
        never made it into a prompt at all** -- actors saw only a 400-character synopsis of the day
        plus their own two tasks, so they improvised independently, and failing to connect became the
        norm.

        Now every beat carries: where / what this scene is about / who should be there / what actions
        it should land / which props to use / the emotional key / what "finished" looks like.
        **Only the current beat is given** (plus one line about "what the next scene is") -- the whole
        sheet would leak later scenes to him and he would steal someone else's.

        ⚠ The schedule is derived from `ds.beats` (`director.stage.StagePlan`), so it is a **different
          thing** from "is there a script for today": when the model wrote no `story` but did produce
          beats, this block should still appear -- which is why it is **not nested in that `story`
          branch**.
        ⚠ Failing to assemble it **must never affect the decision** (it is only a nice-to-have frame
          to begin with) -- exceptions are swallowed and an empty string returned, the same path as
          "there are no beats today".
        """
        plan = getattr(self.world, 'stage_plan', None)
        if plan is None:
            return ''
        try:
            if not plan.enabled or plan.current is None:
                return ''
            block = str(plan.prompt_block(self.name) or '').strip()
            if not block:
                return ''
            # ★★★ 2026-10-12：**地图事实**（用户点名的那一条）——
            #   「导演和剧作家在设计人物动作的时候 要**时时刻刻参考地图**作为
            #     人物移动的依据」。
            #   在那之前，地图只是**画出来给人看**的：演员的提示词里有"在哪儿"，
            #   却**没有任何东西告诉他怎么走**。于是"从屋里出来就到了街上"
            #   这类移动全凭语感 —— 地图对推演**没有产生作用**。
            #   现在这里补两条**算出来**的事实（`world.spatial`，零 LLM）：
            #     · 这一拍在**屋里还是院里**（见天的东西不能出现在屋里）；
            #     · 从上一拍的地方过来**走哪几处**（走不通就明说，别一步跨过去）。
            #   ⚠ 算不出来（今天没地图 / 名字对不上）就**什么都不加** ——
            #     这一段是增强项，不许因为它让"本场戏"整块消失。
            # [EN] ★★★ 2026-10-12: **map facts** (the item the user named) --
            # [EN]   "the director and playwright must **constantly consult the map** as the basis for
            # [EN]   character movement when designing character actions".
            # [EN] Before this, the map was **drawn only to be looked at**: the actor prompt said "where",
            # [EN] but **nothing told him how to walk there**. So movement like "he came out of the house
            # [EN] and was on the street" ran on intuition -- the map had **no effect on the simulation**.
            # [EN] Two **computed** facts are added here (`world.spatial`, zero LLM):
            # [EN]   · whether this beat is **indoors or in the yard** (a thing under open sky must not
            # [EN]   appear indoors);
            # [EN]   · **which places** to pass walking over from the previous beat's place (when
            # [EN]   unreachable, say so plainly rather than stepping across).
            # [EN] ⚠ When it cannot be computed (no map today / names don't match), **nothing is added** --
            # [EN] this block is an enhancement and must never make "this scene" disappear as a whole.
            extra = self._map_line(getattr(plan, 'current', None),
                                   getattr(plan, 'previous', None))
            return '\n' + block + (('\n' + extra) if extra else '') + '\n'
        except Exception:                                        # noqa: BLE001
            return ''

    def _map_line(self, cur, prev) -> str:
        """这一拍的**地图事实**那一行（屋里/院里 + 怎么走过来）；算不出来返回空串。

        ★ 只读 `world.day_map`（今天那张图）与 `world.spatial`，**不调模型**：
          演员每一拍都要问一次，任何一次调用都会乘进成本里。
        [EN] The **map facts** line for this beat (indoors/in the yard + how to walk over); empty string
        [EN] when it cannot be computed.
        [EN] ★ It only reads `world.day_map` (today's map) and `world.spatial`, and **calls no model**:
        [EN] every beat asks once, and any call would multiply the cost.
        """
        try:
            lay = getattr(self.world, 'day_map', None)
            if lay is None or not getattr(lay, 'places', None):
                return ''
            from world import spatial as SP
            where = str(getattr(cur, 'place', '') or '').strip()
            if not where:
                return ''
            names = [str(p.name) for p in lay.places]
            links = list(getattr(lay, 'links', None) or [])
            here = SP.role_of(where)
            bits = [f'- 这一拍在什么地方：{where}（{here}）']
            # 屋外的东西不许出现在屋里 —— 这一句是**当面警告**，不是判据
            # [EN] An outdoor thing must not appear indoors -- this is a **plain warning**, not a criterion
            if SP.space_of(where) == SP.SPACE_IN:
                bits.append('  · 这里是**屋里**（有顶）：见天的东西（井/树/影壁）'
                            '不在这屋里，要说得在院子里')
            elif SP.space_of(where) == SP.SPACE_OUT:
                bits.append('  · 这里是**院里**（见天）：屋里的陈设（柜台/条案）不在这儿')
            pv = str(getattr(prev, 'place', '') or '').strip() if prev is not None else ''
            if pv and pv != where:
                walk = SP.movement_line(names, links, pv, where)
                if walk:
                    bits.append(f'  · 从上一场（{pv}）过来：' + walk.split('：', 1)[-1])
            return '\n'.join(bits)
        except Exception:                                        # noqa: BLE001
            return ''

    def _all_goals_empty(self) -> bool:
        """目标是不是全空（反空转闸的判据）。

        三层：**这一站**（进度节点）· **今天**（今日计划）· **你想要的**（人物卡目标）。
        三层全空时，"做什么都行" —— 那正是"擦一晚上紫砂壶"的温床。

        ★★ **故意不算「此刻」（导演派活）那层**（2026-10-06 接派活时定的）。
        闸门问的是"**这个人自己**有没有想做的事"。派活是导演塞给他的，
        拿它当判据的话：派活一开，闸门就**永远关着**了 ——
        "照着派活做"不等于"有内在动力"，那正好把这道闸废掉。
        （这也是为什么它只看三层，而不是跟着 `GOAL_LADDER` 走。）
        
                English:
        Whether the goals are all empty (the criterion for the anti-idling gate).
                Three layers: **this stop** (progress node) · **today** (today's plan) · **what you want** (character card goal).
                When all three layers are empty, "anything goes" -- that is exactly the breeding ground for "polishing the purple clay teapot all evening".
                ★★ **Deliberately does not count the "this moment" (director-assigned work) layer** (decided on 2026-10-06 when work assignment was hooked up).
                What the gate asks is "does **this person himself** have anything he wants to do". Assigned work is stuffed into him by the director;
                if it were used as the criterion: once work assignment starts, the gate would be **closed forever** --
                "doing as the assigned work says" is not equal to "having internal motivation", and that would exactly ruin this gate.
                (This is also why it only looks at three layers, instead of following `GOAL_LADDER`.)
        """
        info = None
        try:
            info = self.world.current_node_info()
        except Exception:                                       # noqa: BLE001
            info = None
        has_node = bool(info and (info.get("名称") or info.get("概要")))
        has_plan = bool([x for x in (getattr(self.ps, "day_plan", None) or [])
                         if str(x).strip()])
        has_goal = bool(str(self.ps.goal or self.ps.current_goal or "").strip())
        return not (has_node or has_plan or has_goal)

    # ── 记忆写入 ──────────────────────────────────────────────────────
    # 重要度打分（`IMPORTANCE_SCORING`，设计稿 §五）——
    # 检索里 `WEIGHT_IMPORTANCE` 那一项全靠它，可它以前**永远是 5.0 的常数**
    # （`_add_memory` 的默认值），于是"按重要度排序"这件事在数据上不成立。
    # [EN] ── Memory write ──────────────────────────────────────────────────────
    # [EN] Importance scoring (`IMPORTANCE_SCORING`, design doc §5) --
    # [EN] The `WEIGHT_IMPORTANCE` term in retrieval depends entirely on it, yet it used to **always be a
    # [EN] constant 5.0**
    # [EN] (`_add_memory`'s default value), so "sort by importance" doesn't hold up in the data.
    _IMP_RULES: tuple[tuple[tuple[str, ...], float], ...] = (
        (("死", "杀", "刀", "血", "伤"), 9.0),
        (("秘密", "真相", "发现", "察觉"), 8.0),
        (("答应", "承诺", "约定", "托付"), 7.5),
        (("吵", "翻脸", "拒绝", "道歉"), 7.0),
        (("钱", "账", "债", "契"), 6.5),
        (("走", "去", "来", "离开", "回"), 5.0),
        (("看", "听", "坐", "站", "等"), 3.5),
    )

    def _score_importance(self, mem_type: str, content: str) -> float:
        """这条记忆**值多少分**（0~10）。

        三档（`IMPORTANCE_SCORING`）：
          · `heuristic` —— 只走本地规则（零成本，默认水位）；
          · `llm`       —— 每次都问一次模型（准，但每写一条记忆就多一次调用）；
          · `hybrid`    —— **默认**：规则先粗筛，只有落在"说不准"的区间
                            （4~7 分）才叫一次模型。省约 70%（设计稿 §五）。
        
                English:
        **How many points this memory is worth** (0~10).
                Three tiers (`IMPORTANCE_SCORING`):
                  · `heuristic` -- only local rules (zero cost, default level);
                  · `llm`       -- ask the model every time (accurate, but each memory written means one more call);
                  · `hybrid` —— **default**: rules do a rough filter first, and only those falling in the "can't tell" range
                                    (4~7 points) trigger a model call. Saves about 70% (design doc §5).
        """
        base = 5.0
        for kws, score in self._IMP_RULES:
            if any(k in content for k in kws):
                base = score
                break
        if mem_type == "reflection":
            base = max(base, 8.0)
        elif mem_type == "dialogue":
            base = max(base, 5.5)
        mode = (CFG.s("IMPORTANCE_SCORING") or "hybrid").strip()
        if mode == "heuristic":
            return base
        # `hybrid` 只在"规则说不准"时才花钱；`llm` 一律问（那是用户明确要的）
        # [EN] `hybrid` only spends money when "the rules can't decide"; `llm` asks every time (that's what the
        # [EN] user explicitly asked for).
        if mode == "hybrid" and not (4.0 < base < 7.0):
            return base
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 记忆写入是**同步**路径（`_add_memory`），不能在这里 await。
                # 与其偷偷跑一个可能失败的线程，不如老老实实用规则分 ——
                # 并在调试日志里留一句，免得"LLM 打分没生效"变成玄学。
                # [EN] Memory writes are a **synchronous** path (`_add_memory`), can't await here.
                # [EN] Rather than secretly running a thread that might fail, better to honestly score with rules ——
                # [EN] and leave a line in the debug log, so "LLM scoring didn't take effect" doesn't become mysticism.
                _LOG.debug("[%s] 记忆打分退回规则（写入是同步路径）", self.name)
                return base
        except Exception:                                       # noqa: BLE001
            return base
        return base

    def _add_memory(self, mem_type: str, content: str,
                    importance: float | None = None) -> None:
        if importance is None:
            importance = self._score_importance(mem_type, content)
        self.db.add_memory(self.name, content, mem_type, importance,
                           game_ts=self.world.clock.minutes + self.world.clock.day * 1440)

    # ── 人格卡构建 ──────────────────────────────────────────────────────
    # [EN] ── Persona card construction ──────────────────────────────────────────────────────
    def _cast_block(self) -> str:
        """**选角那两层**（预设 + 定制 + 仲裁规则）—— 见 `actors/casting.py`。

        为什么它进**固定层**（跟着人格卡一起缓存）：
          · 它是"这个人怎么演"，一轮推演里一个字都不会变；
          · 固定层在前、动态层在后，正是 prompt cache 最爱的形状。

        ⚠ 拿不到就返回空串（**不许因此让提示词空掉**）：类型库读不了、
          老存档没有这几个字段 —— 那种情况下演员照旧靠人物卡演，
          只是少了"这一类人怎么说话"这一层。这正是降级该有的样子。
        
                English:
        **The two casting layers** (preset + custom + arbitration rules) —— see `actors/casting.py`.
                Why it goes into the **fixed layer** (cached along with the persona card):
                  · It is "how this person acts", not a single character changes within one round of inference;
                  · Fixed layer in front, dynamic layer behind, exactly the shape prompt cache loves most.
                ⚠ If unavailable, return an empty string (**must not let the prompt go empty because of this**): type library unreadable,
                  old saves missing these fields —— in that case the actor still performs based on the character card,
                  just lacking the "how this kind of person talks" layer. This is exactly what graceful degradation should look like.
        """
        try:
            ps = self.ps
            from actors import casting as CASTING
            c = CASTING.Casting(
                name=ps.name,
                archetype=str(getattr(ps, 'archetype', '') or ''),
                variant=str(getattr(ps, 'variant', '') or ''),
                matched=bool(getattr(ps, 'cast_matched', True)),
                casting=str(getattr(ps, 'casting_note', '') or ''),
                break_type=str(getattr(ps, 'break_type', '') or ''),
            )
            card = {'身份': ps.identity, '性格': ps.personality,
                    '口癖': ps.catchphrase, '秘密': ps.secret,
                    '目标': ps.goal, '红线': ps.redline}
            return CASTING.prompt_block(c, card)
        except Exception:                                        # noqa: BLE001
            return ''

    def _actor_craft(self) -> str:
        """**演员这一行的手艺**：怎么说话才像个人（`craft/playbooks/人物与对话.yaml`）。

        ★ 2026-10-07 补：演员是全项目**输出台词最多**的职位，而它此前
          **一本工艺书都不读**（`crew/agents.SHELVES` 里根本没有 `actor` 这一项）。
          剧本那一侧被反复叮嘱"人物一句话立起来"，真正开口的人手上却一条
          "话该怎么说"的手艺都没有 —— 台词像念设定的根子在这。

        放在**尾段之前**（离输出最近的位置之一）：它是行动纪律，不是背景知识。
        
                English:
        **The actor's craft in this line of work**: how to talk like a person
        (`craft/playbooks/人物与对话.yaml`).
                ★ 2026-10-07 addendum: the actor is the position with the **most dialogue output** in the whole project, yet it previously
                  **did not read a single craft book** (there is no `actor` entry at all in `crew/agents.SHELVES`).
                  The script side was repeatedly admonished to "make a character stand up in one line", yet the person actually speaking had not a single
                  craft of "how a line should be said" —— the root of dialogue reading like exposition is here.
                Placed **before the tail section** (one of the positions closest to the output): it is action discipline, not background knowledge.
        """
        try:
            from crew.agents import craft_block
            g = getattr(self.world, 'genre_card', None) or {}
            txt = craft_block('actor', str(g.get('主题材') or ''),
                              str(g.get('结构') or ''))
            return ('【你这一行的手艺（怎么说才像人）】\n' + txt) if txt else ''
        except Exception:                                        # noqa: BLE001
            return ''

    def _cot_line(self) -> str:
        """**演员的思维链骨架**：开口之前按顺序自问哪几件事（`crew/cognition`）。

        为什么演员这一条最值得装：它是全项目**输出台词最多**的职位，而
        "台词像念设定"的根子就是"模型直接产出那句台词，中间没有一个
        '这句话该怎么说'的环节"。装一段骨架 = 用**同一颗脑子、同一次调用**，
        先把它逼到"我要什么 / 刚才那句对我做了什么 / 换个人说成不成立"上，
        再让它开口 —— 这正是第四章 Chain-of-Thought 与第七章框架化实现里
        最省的那一档（不额外调用）。

        ⚠ 拿不到就返回空串（**不许因此让提示词空掉**）：老存档、模式表没登记、
        `COGNITION`/`COT_ACTOR` 关着 —— 那时提示词与从前一字不差。
        
                English:
        **The actor's chain-of-thought skeleton**: what to ask oneself in order before speaking
        (`crew/cognition`).
                Why this actor entry is most worth installing: it is the position with the **most dialogue output** in the whole project, and
                the root of "dialogue reading like exposition" is precisely "the model directly produces that line, with no intermediate
                'how should this line be said' step". Installing a skeleton = using **the same brain, the same call**,
                first forcing it onto "what do I want / what did that last line just do to me / would it still hold if someone else said it",
                then letting it speak —— this is exactly the cheapest tier in Chapter 4 Chain-of-Thought and Chapter 7 frameworked implementation
                (no extra call).
                ⚠ If unavailable, return an empty string (**must not let the prompt go empty because of this**): old saves, mode table not registered,
                `COGNITION`/`COT_ACTOR` turned off —— then the prompt is identical to before, not a character different.
        """
        try:
            from crew import cognition as COG
            from agent import freedom as _FRC
            # ★★ 2026-10-19：**文笔规训松的时候只留一问**（"换给别人说成不成立"）。
            #   为什么精简这一件事也算"文笔"：五问里有四问（要什么 / 刚才那句对我
            #   做了什么 / 多长 / 什么声音）其实是**写法的规定** —— 松档把它们交还给
            #   模型自己，只保留那唯一直接检验"这句话是不是这个人的"的一问。
            #   ⚠ 精简 ≠ 不要：完全不给骨架时决策会退化成关键词反应（实测过）。
            # [EN] ★★ 2026-10-19: **the loose prose band keeps only one question**
            # [EN] ("would it hold if someone else said it"). Four of the five are really **writing
            # [EN] rules**, handed back to the model in the loose band; only that one directly tests
            # [EN] "is this line this person's". ⚠ Trimmed != removed.
            return COG.cot_block('actor', compact=not _FRC.cot_full())
        except Exception:                                        # noqa: BLE001
            return ''

    def _persona_prompt(self) -> str:
        """人格卡 = **固定层**（缓存）+ **动态层**（每次现拼）。

        ⚠ 它是 `_persona_static_only()` + `_persona_dynamic()` 的合并 ——
          `talk()` / `group_chat()` / `reflect()` / `make_plan()` 那些**一次性的**
          短提示词继续用它（拼一起就行，没有缓存前缀那回事）。
          而 `decide()` 那条**每拍都跑**的路要**分开用**，见下。
        
                English:
        Persona card = **fixed layer** (cached) + **dynamic layer** (reassembled each time).
                ⚠ It is the merge of `_persona_static_only()` + `_persona_dynamic()` ——
                  `talk()` / `group_chat()` / `reflect()` / `make_plan()` those **one-off**
                  short prompts continue to use it (just concatenate, there is no such thing as a cache prefix).
                  But the `decide()` path that **runs every beat** must **use them separately**, see below.
        """
        return "\n".join(x for x in (self._persona_static_only(),
                                     self._persona_dynamic()) if x)

    def _persona_static_only(self) -> str:
        """人格卡里**一轮内一个字都不变**的那一层（P0 的后半截）。

        为什么必须与"当前目标 / 情绪 / 神态 / 位置"分开（2026-10-07 第八轮）：
        那四样**每一拍都可能变**，而它们原来是拼在人格卡尾部的 ——
        于是整段"固定层"每拍都变，排在它后面的几千 token 全部拿不到前缀缓存
        （见 `decide()` 里 P0 那段说明）。
        这一段（姓名 / 身份 / 性格 / 口癖 / 秘密 / 红线 / 选角两层）出自设定集，
        一轮里不会改，`_persona_key` 判等之后连字符串都不用重拼。
        
                English:
        The layer of the persona card where **not a single character changes within one round** (the
        latter half of P0).
                Why it must be separated from "current goal / emotion / expression / position" (2026-10-07 round 8):
                those four **can change every beat**, and they were originally concatenated at the tail of the persona card ——
                thus the entire "fixed layer" changed every beat, and the thousands of tokens queued behind it all failed to get prefix cache
                (see the P0 section explanation in `decide()`).
                This segment (name / identity / personality / verbal tic / secret / red line / two casting layers) comes from the setting collection,
                does not change within a round, and after `_persona_key` equality check not even the string needs reassembling.
        """
        ps = self.ps
        key = (ps.name, ps.identity, ps.personality, ps.catchphrase,
               getattr(ps, 'speech_fp', ''),
               ps.secret, ps.redline, ps.goal,
               getattr(ps, 'archetype', ''), getattr(ps, 'variant', ''),
               getattr(ps, 'casting_note', ''), getattr(ps, 'break_type', ''))
        if getattr(self, "_persona_key", None) != key:
            self._persona_static = "\n".join(p for p in [
                f"姓名：{ps.name}",
                f"身份：{ps.identity}" if ps.identity else "",
                f"性格：{ps.personality}" if ps.personality else "",
                f"口癖：{ps.catchphrase}" if ps.catchphrase else "",
                # ★★★ 2026-10-28：说话指纹（句长 / 抓手 / 心虚动作 / 称呼差）。
                #   它必须**紧跟口癖**：两行是同一件事的两层 —— 口癖是那一下，
                #   指纹是"怎么说话"。写在这里而不是只写进 `_voice_rules`，
                #   是因为人格卡给的是"我是谁"，而"我怎么说话"也是身份的一部分；
                #   `_voice_rules` 那份在**开口前最后一段**再压一次（位置不同，作用不同）。
                # [EN] ★★★ 2026-10-28: speech fingerprint, right after the tic: same thing in two
                # [EN] layers. Kept in the persona card because "how I talk" is part of who I am;
                # [EN] `_voice_rules` presses it again just before speaking.
                f"说话指纹：{getattr(ps, 'speech_fp', '')}" if getattr(ps, 'speech_fp', '') else "",
                f"秘密：{ps.secret}" if ps.secret else "",
                f"行为红线：{ps.redline}" if ps.redline else "",
                self._cast_block(),
            ] if p)
            self._persona_key = key
        return self._persona_static

    def _persona_dynamic(self) -> str:
        """人格卡里**每拍会变**的那一层（当前目标 / 情绪 / 神态 / 位置）。

        现在它排在半固定层的**第二位**（第一位是"每场才变"的世界那一段）——
        按变化频率由低到高排，是 `decide()` 里 P0/P1 那套次序的一部分。
        
                English:
        The layer of the persona card that **changes every beat** (current goal / emotion / expression /
        position).
                Now it is placed in the **second position** of the semi-fixed layer (the first is the world segment that "changes only per scene") ——
                ordered by change frequency from low to high, it is part of the P0/P1 ordering in `decide()`.
        """
        ps = self.ps
        return "\n".join(p for p in [
            f"当前目标：{ps.current_goal or ps.goal}" if ps.current_goal or ps.goal else "",
            f"情绪：{_emotion_str(ps)}" if any(ps.emotion.values()) else "",
            # 上一拍 `emote` 留下的神态（自然语言，不是数值维度）
            # [EN] The expression left by the previous beat's `emote` (natural language, not a numeric dimension)
            f"神态：{getattr(ps, 'mood_note', '')}" if getattr(ps, 'mood_note', '') else "",
            f"位置：{ps.location}" if ps.location else "",
        ] if p)

    def _voice_rules(self) -> str:
        """这一拍**怎么开口**的硬约束（口癖 + 风格那两行）。拿不到就返回空串。

        为什么要有它（2026-10-18，《雪国》实测）
        ----------------------------------------
        评委点名的两条越界，是**同一个原因**：

          · 「驹子那句『你觉得我是个什么样的人？』太直、太完整，她的话应当总是半句」；
          · 「叶子在门外问『驹子姐在您这儿吗？』—— 硬约束要求她的声音只用来唤人、传话」。

        这两条**都写在设定里**（口癖「只叫先生」、风格「句子要短、几乎不写情节」），
        可它们只出现在提示词**前半截**的人格卡里 —— 中间隔着几千 token 的设定、
        记忆、场上名单、去 AI 清单，到"开口"那一刻早就淡了。
        实测同一份提示词里「内心必须是第一人称」给了 ✅/❌ 例子，仍有 **40%–74% 不遵守**，
        所以关键约束要**离输出最近**，并且写成**可执行的动作**（"说半句"），
        不是形容词（"性子烈"）。

        ⚠ 零成本：同一段文本随每拍带上，而且它**不进**前缀缓存（在动态层末尾）。
        ⚠ 拿不到口癖也拿不到风格 ⇒ 返回空串，提示词与从前一字不差。

            English:
        The hard constraint on **how to open your mouth this beat** (verbal tic + the two style
        lines). Empty string when neither is available.
            Why it exists (2026-10-18, measured on Snow Country)
            ---------------------------------------------------
            The two boundary violations the judge called out share **one cause**:
              · "Jouji's line 'what kind of person do you think I am?' is too direct, too complete;
                her words should always be half a sentence";
              · "Yoko asks 'is sister Jouji here with you?' -- the hard constraint says her voice is
                only for calling people and passing messages".
            Both **are written in the settings** (verbal tic "only calls him sir"; style "short
            sentences, almost no plot"), but they only appear in the persona card in the **first
            half** of the prompt -- thousands of tokens of settings, memory, roster and the de-AI
            checklist away from the moment of speaking.
            Measured: "inner thought must be first person" shipped with ✅/❌ examples in the same
            prompt and was still violated **40%-74%** of the time. So a key constraint must sit
            **closest to the output**, and be phrased as an **executable action** ("say half a
            sentence"), not an adjective ("hot-tempered").
            ⚠ Zero cost: the same text rides along every beat, and it does **not** enter the
            prefix cache (it is at the tail of the dynamic layer).
            ⚠ Neither tic nor style available => empty string, prompt word-for-word as before.
        """
        ps = self.ps
        tic = str(getattr(ps, 'catchphrase', '') or '').strip()
        # ★★★ 2026-10-28：**说话指纹**（作者点名加）。与此处的口癖、风格并列，
        #   但它管的是最要紧的一条：**同一个人一直是一个味**。它的用法必须写死，
        #   否则模型会把它读成"人物小传"再演一遍（那就成了自我剖白）。
        # [EN] ★★★ 2026-10-28: the **speech fingerprint**. It sits beside the tic and the style
        # [EN] line but governs the most important thing: staying recognisably the same person.
        fp = str(getattr(ps, 'speech_fp', '') or '').strip()
        card = getattr(self.world, 'style_card', None)
        sent = ''
        if isinstance(card, dict):
            sent = str(card.get('句长') or '').strip()
        if not (tic or sent or fp):
            return ''
        rows = ['[你怎么开口]（这不是建议，是这个人物的硬约束）']
        if tic:
            # ★★★ 2026-10-19：这里**只声明规则**，"这一场已经用了几次"由动态层
            #   （`_tic_quota_line`）单独给 —— 两个原因：
            #   ① 这一段在**规则区（前缀）**里，写进会变的内容就毁掉前缀缓存；
            #   ② 光写"一场最多一次"**没用**：2026-10-19 雪国 34 拍实测，
            #      提示词里连"实测被套了 5 次"都写着，驹子的「你这个人哪」照样用了 **6 次**
            #      （`metrics.json`：`repeat_top` 里「你这个人」8 次）。
            #   ⇒ 必须给**可数的事实**（"你已经用了 N 次"）+ 明确禁令，见动态层那一条。
            # [EN] ★★★ 2026-10-19: this block **only states the rule**; "how many times used this
            # [EN] scene" comes separately from the dynamic layer (`_tic_quota_line`), for two
            # [EN] reasons: ① this block is in the **rules zone (prefix)**, and变动 content there
            # [EN] destroys prefix caching; ② stating "once per scene" **does not work**: on
            # [EN] 2026-10-19 a 34-beat Snow Country run still used 「你这个人哪」**6 times**
            # [EN] (`metrics.json` `repeat_top`: 「你这个人」8 occurrences) even though the prompt
            # [EN] said "measured 5 times last run". => Give a **countable fact** ("you have used it
            # [EN] N times") plus an explicit ban, in the dynamic layer.
            rows.append(f'- 你的口癖：{tic} —— 它是**限制**，不是装饰：'
                        '口癖怎么说话，你就只能怎么说话。'
                        '（例：口癖写"只叫先生"，你就不能成句地问人话。）'
                        '⚠ **一场最多用一次**：同一句口头禅每句都带，就成了机器。')
        if sent:
            rows.append(f'- 这一部的句子：{sent}')
        if fp:
            # ⚠ 只给"照着做"的四件事，不给"你是这样的人"—— 后者会变成自我剖白。
            #   通用那三条（能不说就不说 / 遮名测试 / 别答完整）**不在这里**：
            #   它们每拍都要在，所以放在 `_tail` 的行动纪律里，只写一份。
            # [EN] Only the four executable things, never "this is the kind of person you are".
            # [EN] The three universal rules live in `_tail` so there is exactly one copy.
            rows.append(f'- 你的说话指纹：{fp} —— 这是**怎么说话**，不是台词内容：'
                        '句子多长、嘴上的抓手、心虚时手上干什么、对谁换称呼，这四样别改。')
        rows.append('- **说半句**：把话说到一半、用一个字应付、自己先停下 ——'
                    '都比把心事整句端出来像人。**不许自我剖白**'
                    '（"我是什么样的人""我心里其实……"这类整句，除非非说不可且说出来要付代价）。'
                    '⚠ **先接住对方那句**：答非所问只在真要躲的时候用一次，别每句都躲。')
        return '\n'.join(rows)

    def _tic_quota_line(self) -> str:
        """**这一场你的口癖已经用了几次**（可数事实）+ 禁令。拿不到就空串。

        ★★★ 为什么必须单独有一条（2026-10-19 雪国 34 拍实测）
        ------------------------------------------------------
        提示词里"一场最多用一次"早就写着，甚至写着"实测被套了 5 次"，
        而这次跑出来驹子的「你这个人哪」用了 **6 次**（`metrics.json` 里
        `repeat_top`: 「你这个人」8 次、「这个人哪」8 次）。

        ⇒ 这又是那条铁律：**prompt 里写了 ≠ 生效**。可执行的做法只有两种：
          解析层硬处理，或者**给可数的事实**。这里选后者 —— 因为硬删会伤句子
          （"你这个人哪，别敲了"删掉口癖就剩"别敲了"，语气全没），
          而"你已经用了 6 次"是一个**模型没法忽视的具体数字**。

        ⚠ 从 `world.recent_lines`（**这一场**的记录）里数，不是从整场剧本数 ——
          换场就该重新计数（新的一场，观众换了）。
        ⚠ 只在这一场**已经用过**时才挂（第一次用之前不啰嗦）。
        ⚠ 这段**在动态层**（每拍变），不能放进规则区，否则前缀缓存全废。
        [EN] ★★★ Why this must be its own block (measured on a 34-beat Snow Country run,
        [EN] 2026-10-19): the prompt already said "once per scene" -- even "measured 5 times last
        [EN] run" -- yet 「你这个人哪」appeared **6 times** (`metrics.json` `repeat_top`:
        [EN] 「你这个人」x8). => The project's iron rule again: **written in a prompt != in effect**.
        [EN] Only two executable options: hard handling in the parser, or **a countable fact**.
        [EN] This picks the latter: deleting the tic damages the sentence ("别敲了" alone loses the
        [EN] tone), while "you have already used it 6 times" is a number the model cannot ignore.
        [EN] ⚠ Counted from `world.recent_lines` (**this scene**), not the whole script -- a scene
        [EN] change restarts the count. ⚠ Only shown once it has been used. ⚠ Dynamic layer only.
        """
        # ★★ 2026-10-19：**最松那一档关掉口癖配额**（作者那时要的是"别管我"）。
        #   ⚠ 代价是真的：关掉之后口癖会回弹到每句都带（2026-10-19 实测：34 拍用 6 次）。
        #     所以界面上把这个代价写出来了，而不是悄悄关。
        # [EN] ★★ 2026-10-19: **the loosest band turns the tic quota off** (the author wants to be
        # [EN] left alone there). ⚠ The cost is real: the tic bounces back to every line (measured:
        # [EN] 6 uses in 34 beats), so the UI states that cost instead of switching it silently.
        try:
            from agent import freedom as _FRT
            if not _FRT.tic_quota():
                return ''
        except Exception:                                        # noqa: BLE001
            pass
        tic = str(getattr(self.ps, 'catchphrase', '') or '').strip()
        if len(tic) < 2:
            return ''
        try:
            lines = list(getattr(self.world, 'recent_lines', None) or [])
        except Exception:                                        # noqa: BLE001
            return ''
        used = 0
        samples: list[str] = []
        for r in lines:
            txt = str((r or {}).get('text') or '')
            if tic and tic in txt:
                used += 1
                if len(samples) < 2:
                    samples.append(txt[:24])
        if used <= 0:
            return ''
        out = [f'\n[你的口头禅：这一场已经用了 {used} 次]']
        if samples:
            out.append('- 已经说过的：' + ' / '.join(f'「{x}」' for x in samples))
        out.append(f'- ⚠ 「{tic}」这一场**已经够了**：这一拍**不许再带它**。'
                   '要表达同样的意思，就**换一个说法**，或者干脆**不开口、只做一个动作**。'
                   '（同一句口头禅每句都带，读者立刻看出是程序 —— 这是实测过的。）')
        # ★★★ 2026-10-19 第二版实测补的一条：**"不许再说"会被执行成"用旁白交代"**。
        #   那一版里写出了「驹子……**总拿"你这个人哪"开头絮叨**雪天赏雪」——
        #   台词里确实没有（字面禁令没破），但那是一句**元叙述**：作者在替角色
        #   标注"她在用这个口癖"。读者看到的是"写的人在场"，比直接说还糟。
        #   所以禁令必须**指明作用域**（说的是台词，不是让旁白去说这件事）——
        #   这与"允许 X 必须写清作用域"是同一条教训的另一面。
        # [EN] ★★★ Added after measuring the second run (2026-10-19): **"never say it again" gets
        # [EN] executed as "have the narration mention it"**. That run produced「驹子……**总拿"你这个人哪"
        # [EN] 开头絮叨**雪天赏雪」-- the dialogue truly had none (the letter of the ban was kept), but
        # [EN] that sentence is **meta-narration**: the author annotating "she is using this tic". The
        # [EN] reader sees the writer standing in the room, which is worse than saying it outright.
        # [EN] So a ban must **scope itself** (it is about dialogue, not about having narration report
        # [EN] it) -- the other side of the same lesson as "allowing X must state its scope".
        out.append('  ⚠ 这条禁令说的是**你的台词**：不许用旁白交代"她总拿这个口癖开头"'
                   '这类话 —— 那等于把作者推到台前，比直接说还难看。')
        return '\n'.join(out)

    def _repeat_phrase_line(self) -> str:
        """**这一场你已经反复用过的语气 / 姿态短语**（可数事实）+ 换法。拿不到就空串。

        ★★★ 为什么要有它（2026-10-19 第五轮实测）
        ------------------------------------------
        `_tic_quota_line` 只管人物卡里写着的口癖。本轮加了"你要有自己的一条线"之后，
        模型找到了新偷懒：**用同一套动作/语气给同一个人做标记**。
        实测（`snow_thread1`，24 拍）：「声音含混」6 次、「偏头」5 次、「含混」8 次、
        「是啊」7 次、「先生」17 次 —— 而上一轮这些几乎全是 0–1 次。
        ⇒ 这是**改动引入的新病**：演员不再复读台词了，改成复读**语气标记**。

        做法与 `_tic_quota_line` 同一条纪律：**给可数的事实**，不说空话。
        "你已经用「声音含混」6 次" 比 "别重复" 管用得多（实测过的）。

        ⚠ 数据来源是**这一场自己做过的事**（`world.own_actions`，含 `细节` 原文）——
          不另存一份计数。两处实现迟早对不上。
        ⚠ 只报**本场 >= 3 次**的短语（1–2 次是正常用词，报了就是噪音）。
        ⚠ 短语取 3–4 字滑窗，且跳过虚词开头（"的声音""说的是"这种碎片）。
        [EN] **Phrases you have already reused this scene** (a countable fact) + how to vary.
        [EN] `_tic_quota_line` only covers the persona-card tic; after adding "you need your own
        [EN] thread" the model found a new shortcut -- tagging one person with the same gesture/tone.
        [EN] Measured: 声音含混 x6, 偏头 x5, 含混 x8, 是啊 x7, 先生 x17 while the previous round had
        [EN] 0-1. Same discipline as the tic quota: **give a countable fact**. Data comes from this
        [EN] scene's own actions (no second counter). Only report phrases used >= 3 times.
        """
        try:
            if not CFG.b('DIALOGUE_CONTEXT'):
                return ''
        except Exception:                                        # noqa: BLE001
            return ''
        try:
            texts = list(self.world.own_actions(self.name, 6) or [])
            texts += list(self.world.last_own_lines(self.name, 4) or [])
        except Exception:                                        # noqa: BLE001
            return ''
        # ⚠ **必须按行分隔**（2026-10-19 第十轮）：`''.join` 会把相邻两行拼成一段，
        #   于是跨行的两次重复被合并进同一个 run，按段去重后就只剩一次
        #   （实测：5 次「声音含混」被报成 4 次）。用换行分隔，一行就是一段。
        # [EN] **Join with a newline**: `''.join` welds two adjacent lines into one run, so two
        # [EN] occurrences across a line break fall into the same segment and per-segment dedupe
        # [EN] keeps only one (measured: 5 occurrences reported as 4). A newline keeps one line = one
        # [EN] segment.
        body = '\n'.join(str(x) for x in texts)
        if len(body) < 20:
            return ''
        # 停用开头：这些起头的滑窗是跨词碎片，不是"语气标记"
        skip = set('的了着过是在和与就都也还很太更最把被将给让对向为从一这那他她我你')
        counts: dict[str, int] = {}
        # ⚠ 窗口必须包括 **5 字**（2026-10-19 第六轮实测）：
        #   「你这个人哪」是 5 个字，3–4 字窗口只切出「你这个」「个人哪」，
        #   两个都不像口癖 ⇒ 检测不到 ⇒ 真跑里它出现了 **5 次**而配额一声不响。
        #   这正是"判据口径与病名对不上"的那类失误。
        # [EN] The window must include **5 chars**: 「你这个人哪」is five characters, and 3-4 char
        # [EN] windows only produce 「你这个」/「个人哪」, neither of which looks like a tic -- so it
        # [EN] went undetected while appearing **five times** in the real run.
        # ★★★ **先数"被标点围住的整段"**（2026-10-19 第十轮，真跑抓出来的）
        # -----------------------------------------------------------------
        # `snow_v10` 里岛村 7 句台词有 5 句以「是啊」开头、驹子 10 句以「客人，您」开头，
        # 而配额**一声不响**。根因就在这一行：`{3,}` 只留 >=3 字的连续中文段，
        # 而「是啊。」后面紧跟句号 ⇒ 那一段只有 **2 个字** ⇒ 直接被正则丢掉。
        # 「客人，您……」同理（逗号切开，只剩「客人」两个字）。
        # ⇒ **最短、最规整的口癖恰恰是 2 字**，而它正好是唯一被漏掉的一类。
        #
        # 为什么整段计数**不适用停用开头表**：那张表防的是"滑窗跨词切出碎片"
        # （"的声音""说的是"）。而整段两端都是标点 —— 它没有被切过，
        # 就是这个人自己说出来的一段，首字是「是」也照样是口癖。
        # [EN] ★★★ **Count punctuation-delimited segments first** (round ten, caught by a real run).
        # [EN] In `snow_v10`, five of Island's seven lines opened with 「是啊」 and ten of Jouji's
        # [EN] with 「客人，您」, while the quota stayed silent. Root cause: `{3,}` keeps only runs of
        # [EN] 3+ CJK chars, and 「是啊。」 is followed by a full stop, so that run is **2 chars** and
        # [EN] gets dropped. The shortest, most regular tics are exactly 2 chars -- the one class
        # [EN] that was invisible. The stop-head list must **not** apply to whole segments: it
        # [EN] guards against sliding windows cutting across word boundaries, and a segment bounded
        # [EN] by punctuation on both sides was never cut.
        # ⚠ **每段只记一次**（`seen_in_run`）：否则「声音含混」这种既等于整段、
        #   又被 4 字滑窗切到的短语会被数两遍（第一版就是这样，"5 次"报成 6 次）。
        #   计数口径统一成"**在几段里出现过**"，这也正是读者感受到的重复。
        # [EN] Count **once per segment** (`seen_in_run`): otherwise a phrase that equals the whole
        # [EN] segment *and* is also cut by a 4-char window gets counted twice (the first version
        # [EN] reported 6 instead of 5). The unit is "in how many segments it appears", which is
        # [EN] also exactly what a reader perceives as repetition.
        for run in re.findall(r'[\u4e00-\u9fff]+', body):
            seen_in_run: set[str] = set()
            if 2 <= len(run) <= 8:
                seen_in_run.add(run)
            for size in (5, 4, 3):
                for i in range(len(run) - size + 1):
                    w = run[i:i + size]
                    # ⚠ 停用开头**只管 3 字滑窗**（碎片风险在那儿）。
                    #   5 字连续重合 3 次以上，几乎一定是真短语，不该因为
                    #   首字是「你」就被跳过 —— 那正好把「你这个人哪」这种口癖漏掉。
                    # [EN] The stop-head list applies to **3-char sliding windows only**.
                    if size <= 3 and w[0] in skip:
                        continue
                    seen_in_run.add(w)
            for w in seen_in_run:
                counts[w] = counts.get(w, 0) + 1
        # 只留 >= 3 次、且不被更长的同频短语包含的（"声音含混" 出现时不再报 "含混"）
        hot = {w: n for w, n in counts.items() if n >= 3}
        if not hot:
            return ''
        keep: list[tuple[str, int]] = []
        for w, n in sorted(hot.items(), key=lambda kv: (-len(kv[0]), -kv[1])):
            if any(w in k and kn >= n for k, kn in keep):
                continue
            keep.append((w, n))
        keep = keep[:2]
        if not keep:
            return ''
        out = ['\n[你这一场的语气标记：已经用腻了]']
        for w, n in keep:
            out.append(f'- 「{w}」已经出现 **{n} 次**')
        out.append('- ⚠ 这一拍**不要再拿它们标记自己**。换个办法让读者看出你的状态：')
        out.append('  ① 写**手上的动作**（他手指在钵沿停住、她把盏子往前推了半寸）；')
        out.append('  ② 写**别人看见的样子**（她抬眼时睫毛上还有雪）；')
        out.append('  ③ 或者**干脆不写语气** —— 让台词自己承担。')
        out.append('  ⚠ 不是让你改性格：性子还是那个性子，只是**别再贴同一个标签**。')
        return '\n'.join(out)

    def _other_persona_prompt(self, ps: PersonState) -> str:
        return self._persona_prompt_for(ps)

    @staticmethod
    def _persona_prompt_for(ps: PersonState) -> str:
        parts = [
            f"姓名：{ps.name}",
            f"身份：{ps.identity}" if ps.identity else "",
            f"性格：{ps.personality}" if ps.personality else "",
            f"口癖：{ps.catchphrase}" if ps.catchphrase else "",
        ]
        return "\n".join(p for p in parts if p)


def _emotion_str(ps: PersonState) -> str:
    parts = []
    for k, v in ps.emotion.items():
        if v > 0.3:
            parts.append(f"{k}={v:.1f}")
    return ", ".join(parts) if parts else "平静"


def _verb_desc(act: Action) -> str:
    descs = {"move": f"去了{act.target}", "speak": f"说：{act.dialogue[:30]}",
             "interact": f"和{act.target}互动", "emote": f"表现出了情绪",
             "wait": "等了等", "think": f"想：{act.inner_thought[:30]}"}
    return descs.get(act.verb, act.verb)