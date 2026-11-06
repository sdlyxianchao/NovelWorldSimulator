# -*- coding: utf-8 -*-
"""导演引擎（设计稿 §七）：看·挑·问·拦·收。

看：订阅总线，维护张力/伏笔/进度。
挑：按旋钮 × 类型工艺挑事。
问：分支提案。
拦：停滞/循环/违规报警。
收：到终点收尾出小结。

English:
Director engine (design doc §7): watch, pick, ask, block, wrap up.
Watch: subscribe to the bus, maintain tension/foreshadowing/progress.
Pick: stir things up by knobs × genre craft.
Ask: branch proposal.
Block: stall/loop/violation alerts.
Wrap up: finalize at the endpoint and produce a summary.
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import Any

from llm.router import llm
from llm.replies import ask
from llm import models as MODELS
from craft import craftmix
from crew.prose_flow import has_quoted_speech
from world.state import WorldState
from store.db import DB, similarity
from util.jsonio import extract_json, extract_json_lenient
from util.text import fill
from config import CFG

_LOG = __import__("logging").getLogger("nws.director")

# ── 张力曲线（`TENSION_CURVE`）───────────────────────────────────────────
#   每档三件事：**每故事日的衰减系数**、**事件抬升系数**、**高潮日的目标张力**。
# [EN] ── Tension curve (`TENSION_CURVE`) ───────────────────────────────────────
# [EN] Three things per tier: **decay coefficient per story day**, **event lift coefficient**, **target
# [EN] tension on climax day**.
#
#   ⚠ 为什么必须做这个（2026-10-06）：原来张力**只增不减**
#     （`tension += intensity * 0.3`，全文件没有任何一处让它回落），
#     而事件注入的门槛是 `tension < 0.4` —— 于是张力一旦越过 0.4，
#     **那条路就永久关闭了**：导演再也不主动挑事，只剩"停滞自救"兜底
#     （而它判的还是真实时间）。表现就是：开头热闹，越跑越平，最后没人动。
# [EN] ⚠ Why this is mandatory (2026-10-06): tension used to **only increase, never decrease**
# [EN] (`tension += intensity * 0.3`, nowhere in the whole file does it fall back),
# [EN] and the event injection threshold is `tension < 0.4` -- so once tension crosses 0.4,
# [EN] **that path is permanently closed**: the director no longer proactively stirs things up, only
# [EN] "stagnation self-rescue" remains as a fallback
# [EN] (and that judges real time). The symptom: lively at the start, flatter and flatter as it runs,
# [EN] and finally nobody moves.
_TENSION_CURVE: dict[str, tuple[float, float, float]] = {
    #    日衰减   事件抬升   高潮日目标
    "flat":   (1.00, 0.15, 0.45),   # 平：不落也不冲（日常流）
    "medium": (0.85, 0.30, 0.62),   # 中：缓落缓起
    "roller": (0.60, 0.55, 0.80),   # 过山车：大落大起
    # [EN] Daily decay   Event lift   Climax-day target
    # [EN] Flat: neither falls nor surges (slice-of-life flow)
    # [EN] Medium: slow fall, slow rise
    # [EN] Rollercoaster: big fall, big rise
}

# `auto` 跟着风格控制的「节奏感」（PACING_STYLE）走 —— 用户在书斋里
# 选"过山车"，导演这边的张力曲线就该跟着变成过山车，而不是两套说法。
# [EN] `auto` follows the "sense of rhythm" (PACING_STYLE) set by style control -- when the user in the
# [EN] study
# [EN] picks "rollercoaster", the director's tension curve should also become a rollercoaster, not two
# [EN] different stories.
_AUTO_BY_PACING = {"slow": "flat", "medium": "medium",
                   "fast": "medium", "roller": "roller"}

# 事件重复度：低于这个相似度才算"新的事"。
# `REPETITION_SIMILARITY` 默认 0.85（Jaccard，二元组）。
# [EN] Event repetition: only below this similarity counts as "something new".
# [EN] `REPETITION_SIMILARITY` defaults to 0.85 (Jaccard, bigrams).
_REPEAT_RETRY_HINT = ("刚才那个事件和最近发生过的太像了。"
                     "请换一个**完全不同的角度**再说一件事 —— "
                     "不要重复上面列出的任何一件。")

# ★★★ 事件里**不许出现引语**（2026-10-19 第十一轮）。
#
# 为什么是一条硬规矩而不是"建议别这么写"：真跑六次、五次注入同一句
# `驹子忽然安静，说"她恨我"，又笑着说"算了"` —— 那句"她恨我"在正文里
# **全文找不到"她"是谁**，情感分量很重却毫无承接（用户点名"最致命"）。
# 根因是：**事件是"发生的事"，引语是"某人说的一句话"**。让事件里带引语，
# 等于让导演替某个角色写好了一句他自己从没决定过要说的台词 ——
# 那句话没有动机、没有铺垫、没有前后文，直接落进正文。
#
# 真要有人开口，那该由**人物在自己的那一拍**里决定；事件只负责把局面
# 推到那一步（"门被推开""东西掉了""有人把秘密说了出去"）。
#
# 实测这条规矩的安全性：18 个真跑的 4,959 行材料里，除这句反复出现的
# "她恨我"之外**没有一行**命中 —— 不是靠阉割事件换来的。
# [EN] ★★★ **No quoted speech inside an injected event** (round eleven). Six real runs, five of
# [EN] them injected 「驹子忽然安静，说"她恨我"，又笑着说"算了"」 -- and in the prose there is
# [EN] **nothing anywhere saying who "she" is**: heavy emotional weight, zero setup (the user called it
# [EN] "the most fatal"). Root cause: **an event is something that happened; a quotation is something
# [EN] someone said**. Letting an event carry a quotation lets the director write a line for a
# [EN] character who never decided to say it -- no motive, no setup, no context, straight into the prose.
# [EN] If someone must speak, that is the **character's own beat** to decide; the event only pushes the
# [EN] situation to that point ("the door was pushed open", "the thing fell", "someone let the secret
# [EN] out"). Measured safety: across 18 real runs and 4,959 material lines, **not one line** besides
# [EN] that recurring "she hates me" was flagged -- this is not bought by castrating events.
_NO_QUOTE_RETRY_HINT = ("刚才那个事件**里带了一句引语**（直接写了某人说“……”）。"
                        "事件是**发生的事**，不是**某人说的一句话** —— "
                        "请把那句话改成一件**物理上或信息上真发生了的事**，"
                        "一个字引号都不要用。")


# ── 认知模式（2026-10-07 第七轮）──────────────────────────────────────
# 导演是全项目**判断最密**的职位（挑事 / 派活 / 验算 / 盯戏），也是最容易
# "凭直觉就下手"的那个。这里给它两处**思维链**（一次调用内先想后答，零额外成本）：
#   · 派活之前先看清"谁卡在哪儿"（`dispatch`）；
#   · 挑事之前先想清"这一拍最缺什么"（`_inject_event`）。
# 模式表与骨架在 `crew/cognition.py` 一处；这两个转发只是省掉两处 try/except。
# ⚠ **`evaluate_progress` 故意不装**：它是"判据满足了没有"的结论型用途，
#   提示词里明写"不要写任何思考"（思考会把 max_tokens 吃光，见上面那段实测），
#   再给它套一层"先想后答"等于把踩过的坑重新踩一遍。
# [EN] ── Cognition mode (2026-10-07, seventh round) ──────────────────────────
# [EN] The director is the position with the **densest judgment** in the whole project (stir things up
# [EN] / assign work / verify / watch the drama), and also the one most prone to
# [EN] "acting on pure instinct". Here it gets two **chains of thought** (think first then answer
# [EN] within one call, zero extra cost):
# [EN] · before assigning work, first see clearly "who is stuck where" (`dispatch`);
# [EN] · before stirring things up, first think clearly "what this beat most lacks" (`_inject_event`).
# [EN] The mode table and skeleton live in one place in `crew/cognition.py`; these two forwarders just
# [EN] save two try/except blocks.
# [EN] ⚠ **`evaluate_progress` deliberately does not get one**: it is a conclusion-type use of "is the
# [EN] criterion satisfied",
# [EN] the prompt explicitly says "do not write any thinking" (thinking eats up max_tokens, see the
# [EN] measured data above),
# [EN] wrapping another "think first then answer" layer around it is stepping in the same pit again.
def _cot_block() -> str:
    """导演的思考骨架（拿不到返回空串 —— 开关关掉时提示词与从前一字不差）。
        English:
    The director's thinking skeleton (returns an empty string when unavailable —— when the switch is
    off the prompt is word-for-word as before).
    """
    try:
        from crew import cognition as _COG
        return _COG.cot_block('director')
    except Exception:                                            # noqa: BLE001
        return ''


def _name_list(raw) -> list[str]:
    """把模型返回的一栏洗成**名字列表**（只收非空字符串，顺序不变、不去重）。

    ⚠ 只清洗、不校验：校验要"这一幕的在场名单"，那在
      `scene_builder.observe_event` 手上。这里判一遍就是两处实现。
    ⚠ 只收字符串：模型有时把整句话塞进来（`"叶子低头退下了"`），
      留着它，让护栏按"必须在场名单里"剔掉 —— 这里猜哪几个字是名字
      反而会把 `["叶子", "驹子"]` 这种正确输入切开。
    [EN] Wash one field into a **name list** (non-empty strings only, order kept,
    [EN] no dedupe). Validation lives in `scene_builder.observe_event`; guessing
    [EN] which characters form a name here would cut correct lists apart.
    """
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _note_cot(data, *, what: str) -> None:
    """把导演这一步的盘算记一条日志（**它的消费方**：日志与可读性）。

    ⚠ 导演不产出"给人看的稿件"，所以它的 `推演` 没有落盘口 —— 那就不假装有：
      取出来记进日志，事后查"导演当时为什么这么派"就有据可依。
    
        English:
    Log one entry for the director's calculation at this step (**its consumers**: logging and
    readability).
        ⚠ The director does not produce "a manuscript for people to read", so its `推演` has no persistence slot —— then do not pretend it does:
          retrieve it and write it to the log, so that later, when checking "why the director assigned things this way at the time", there is evidence.
    """
    try:
        from crew import cognition as _COG
        tr = _COG.take_think(data, 'director')
        if tr:
            _LOG.info('导演%s前想过：%s', what, tr[:100])
    except Exception:                                            # noqa: BLE001
        pass


def _think_sch() -> str:
    """`推演` 在 JSON 格式说明里那一小段（**关掉时是空串**，见 `cognition.think_schema`）。
        English:
    The small segment of `推演` in the JSON format description (**empty string when off**, see
    `cognition.think_schema`).
    """
    try:
        from crew import cognition as _COG
        return _COG.think_schema_of('director')
    except Exception:                                            # noqa: BLE001
        return ''


@dataclass
class DirectorEvent:
    """导演注入的一个事件。
        English:
    One event injected by the director.
    """
    event_type: str       # 外部刺激 / 人物冲突 / 巧合 / 秘密泄露 / 伏笔激活
    # [EN] External stimulus / character conflict / coincidence / secret leak / foreshadowing activation
    description: str
    involved: list[str]
    intensity: float      # 0~1
    node_relevant: str    # 关联进度节点
    # [EN] Associated progress node
    #: ★★★ 这件事让谁**离开**场面、谁**回到 / 进入**场面（2026-10-19 第十二轮）。
    #: 为什么必须有这两栏：以前"有人走了"只活在 `description` 那句自由文本里，
    #: 落在长句中间、与后面的动作隔了好几行 —— 整理成小说的小说作家看不到
    #: 这条链，于是写出"叶子低头退下 … 她把壶往驹子手边推了推"这种
    #: **人在门外却伸手进屋**的断链（用户点名的第四条）。
    #: ⇒ 让它成为**结构化的一栏**，`scene_builder.observe_event` 据此往材料里
    #:    补 `〔退场〕X` / `〔出场〕X` 两个标记，判据才有东西可判。
    # [EN] ★★★ Who this event makes **leave** the scene, and who **returns / enters** it.
    # [EN] Why these two lists: "someone left" used to live only inside the free-text
    # [EN] `description`, buried mid-sentence and several lines away from the later
    # [EN] action -- the novelist never saw the chain and produced a break like
    # [EN] "she bowed out … she pushed the pot toward her" (the user's fourth complaint).
    # [EN] Making it structured lets `scene_builder.observe_event` add real
    # [EN] `〔退场〕X` / `〔出场〕X` marks for a criterion to watch.
    # ⚠ 放在最后：dataclass 里**有默认值的字段不许排在没默认值的前面**
    #   （实测 `TypeError: non-default argument 'intensity' follows default
    #   argument 'entering'`，而且它在 import 期就炸，一跑全红）。
    # [EN] ⚠ Kept last: in a dataclass, a field with a default may **not** precede
    # [EN] one without (measured: that TypeError fires at import time, so every
    # [EN] check goes red at once).
    leaving: list[str] = field(default_factory=list)
    entering: list[str] = field(default_factory=list)
    reason: str = ""


# ── 进度评估（`progress_eval`）────────────────────────────────────────
# [EN] ── Progress evaluation (`progress_eval`) ────────────────────────────────
#
# 它是全项目**调用最密的"结论型"用途**：主循环里**每一拍都问一次**
# （2026-10-06 那轮 7 分钟跑了 63 次，是 `agent_decide` 的一半）。
# 三条踩出来的规矩：
# [EN] It is the **most frequently called "conclusion-type" use in the whole project**: in the main
# [EN] loop **it is asked once every beat**
# [EN] (in the 2026-10-06 round it ran 63 times in 7 minutes, half of `agent_decide`).
# [EN] Three rules learned the hard way:
#
# 1. **关掉思考**。它问的是"判据满足了没有"，输出主体是一个布尔值。
#    那轮日志里 63 次有 8 次把 2000 token **整份花在思考上**，正文为空、
#    `finish_reason=length` —— 一个 6 行的判定问题，模型想了 3000 多 token。
#    直连复现过：`deepseek-flash` 思考 3233 token、正文 0 字；
#    加上 `thinking:{"type":"disabled"}` 之后 61 token 就答完了，快 50 倍。
#    （策略表在 `llm/router.NO_THINK_PURPOSES`，这里不用重复声明。）
# 2. **提示词要限字数**。「理由」「进展描述」原来都是**不限长的自由文本**，
#    形状上就在鼓励写长 —— 现在各限 40 字，只要结论 + 一句说明。
#    `_PROGRESS_TOKENS` 是安全网（关思考后实测 60~90 token，1500 够厚）。
# 3. **"没拿到" ≠ "判据没满足"**。原来两件事都返回 `(False, "")`，于是
#    "模型把额度吃光了"表现成"故事还没走到那儿"：**节点永远不推进，
#    界面上一个字都没有**（正是本项目一直在打击的沉默降级）。
#    现在分开报（`ProgressVerdict.ok`），由调用方决定怎么讲给用户听。
# [EN] 1. **Turn off thinking**. What it asks is "is the criterion satisfied", and the main output is a boolean.
# [EN] In that round's logs, 8 out of 63 times spent the entire 2000 tokens **on thinking**, with empty
# [EN] body text,
# [EN] `finish_reason=length` -- for a 6-line judgment question, the model thought for over 3000
# [EN] tokens.
# [EN] Reproduced on direct connection: `deepseek-flash` thought 3233 tokens, body 0 characters;
# [EN] after adding `thinking:{"type":"disabled"}` it answered in 61 tokens, 50 times faster.
# [EN] (The policy table is in `llm/router.NO_THINK_PURPOSES`, no need to redeclare here.)
# [EN] 2. **The prompt must limit word count**. "Reason" and "progress description" used to be **length-unlimited free text**,
# [EN] which in shape encourages long writing -- now each is limited to 40 characters, only the
# [EN] conclusion + one sentence of explanation.
# [EN] `_PROGRESS_TOKENS` is the safety net (measured 60~90 tokens after disabling thinking, 1500 is
# [EN] thick enough).
# [EN] 3. **"Did not get it" ≠ "criterion not satisfied"**. Originally both things returned `(False, "")`, so
# [EN] "the model used up its quota" showed up as "the story has not gotten there yet": **the node
# [EN] never advances,
# [EN] not a single character on the UI** (exactly the silent degradation this project has been
# [EN] fighting).
# [EN] Now they are reported separately (`ProgressVerdict.ok`), and the caller decides how to tell the
# [EN] user.
_PROGRESS_TOKENS = 1500

_PROGRESS_PROMPT = """当前进度节点：{name}（判据：{criteria}）
最近发生的事：
{events}

请判断**判据**是否满足。

★★ 判定口径（2026-10-14 补 —— 用户：「推演感觉故事线推进的特别快 …… 第一天就想把谜底解开，
这个节奏是不对的」）：
下面这些**都算"没满足"**，不要因为"沾到了判据里的词"就给 true：
- 只是**提到 / 暗示 / 说起**了判据里的事物（提到不等于做到）；
- 人物只是**打算**去做、说了句"我要去查" —— 意图不算完成；
- 判据里说的要是**一串**事（例："完成多站委托 + 发现线索 + 听讲古"），
  **只做到其中一件就是没满足** —— 必须**全部**做到；
- 判据里的动作**发生在别人身上**、或只是旁白交代，不算这个节点完成。
反过来，只有**这一趟真的走完了、结果明确落在纸上**，才算 true。
⚠ 拿不准就判 false —— **慢一点没关系，提前把后面的戏演掉才是坏事。**

**只输出 JSON，不要写任何思考或解释**：
{"满足": true|false, "理由": "不超过 40 字", "进展描述": "不超过 40 字"}"""


@dataclass
class ProgressVerdict:
    """一次进度评估的结果。

    ★ `ok=False` 只表示**这次没拿到结论**（模型没回答 / 被截断 / 解析不出来），
      **不等于"判据没满足"** —— 调用方必须区别对待，别让它冒充"故事还没到"。
    
        English:
    Result of a progress assessment.
        ★ `ok=False` only means **this time no conclusion was reached** (model did not answer / was truncated / could not be parsed),
          **it does not equal "the criteria were not met"** —— the caller must treat them differently, do not let it masquerade as "the story has not arrived yet".
    """

    ok: bool
    done: bool = False
    desc: str = ""
    why: str = ""          # `ok=False` 时：为什么没拿到（已经是给人看的一句话）
    # [EN] When `ok=False`: why it was not obtained (already a human-readable sentence)

    @staticmethod
    def failed(why: str) -> "ProgressVerdict":
        return ProgressVerdict(ok=False, why=why)


def assignment_shared(prev: str, new: str, names: tuple[str, ...] = ()) -> int:
    """两件派活**去掉人名之后**共享几个二元组。**纯函数，可单测。**

    ★★★ 为什么派活要有"硬机制"，而不只是提示词（2026-10-19 第十一轮）
    ----------------------------------------------------------------
    实测 `snow_v10` 同一晚三次派给岛村的活：
      ① 说定在此地再消磨几日 → ② 静看驹子接酒不插一言 → ③ 把驹子自语当风景照旧消磨
    三件**共享 0 个二元组** —— 既不是"重复派同一件"（那是另一条判据），
    也**不是"下一步"**。人物的线每 8 拍被剪断一次，下游怎么改都接不上。

    而当时的防护只有一句提示词「新派的这一件必须是上面那件的下一步」。
    **提示词治不了这个**（本项目最高频的失效模式：prompt 里写了 ≠ 生效）。
    ⚠⚠ **这条只用于诊断（记日志），不用于强制纠正 —— 它判不了"方向对不对"。**
      实测：真正的漂移（说定消磨几日 → 静看不插一言）共享 **0**；
      但正常的下一步（说定消磨几日 → 把这话说给驹子听）**也是 0**
      （"这话"是代词，字面上没有任何重合）。
      拿它当"漂移就重派"的闸，会把大量正常的推进当成漂移、逼导演改成模板。
      ⇒ 硬机制做在**结构**上（`sim/loop._maybe_dispatch`：上一件没办就不派新的），
        这个函数只负责**把漂移率报出来**，让人看见。

    ⚠ **人名不算证据**（与连派检测同一条）：每句都有"让某甲…"，共享了也说明不了什么。
    [EN] How many name-stripped bigrams two assignments share. **Pure function, for diagnostics
    [EN] only -- it cannot judge direction.** Measured: a real drift shares **0**, but a normal next
    [EN] step ("decide how many days to stay" -> "say that to her") is **also 0**, because "that" is a
    [EN] pronoun. Using it as a "drift => re-dispatch" gate would treat most real progress as drift
    [EN] and push the director into templates. So the hard mechanism lives in **structure**
    [EN] (`sim/loop._maybe_dispatch`: do not assign a new task while the previous one is being
    [EN] worked on); this function only **reports the drift rate** so a human can see it. ⚠ Names are
    [EN] not evidence.
    """
    def _bg(x: str) -> set[str]:
        z = ''.join(ch for ch in str(x) if '\u4e00' <= ch <= '\u9fff')
        grams = {z[i:i + 2] for i in range(len(z) - 1)}
        name_chars = set(''.join(names or ())) | {'让', '请', '叫', '使'}
        return {g for g in grams if not (g[0] in name_chars and g[1] in name_chars)
                and not (g[0] in name_chars and g[1] in name_chars)}

    return len(_bg(prev) & _bg(new))


class DirectorEngine:
    """导演引擎：故事进度跟踪 + 戏剧事件注入 + 终点判定。
        English:
    Director engine: story progress tracking + dramatic event injection + endpoint determination.
    """

    def __init__(self, world: WorldState, db: DB):
        self.world = world
        self.db = db
        self._events_since_stall: int = 0
        #: **僵局计数**（2026-10-19）：`sim/loop` 每拍算出"大多数人在等"就 +1，
        #: 攒到 `STALL_BREAK_BEATS` 时由 `request_settle()` 写进来一个正数，
        #: `on_tick` 读到就跳**结算通道**（不按压力分类型，强制给这个悬置一个结果）。
        #: 为什么不放进 `world`：它是导演自己的节流状态，落盘没有意义，
        #: 而"两处实现"（world 上一份、这里一份）迟早对不上。
        # [EN] **Deadlock counter** (2026-10-19): incremented by `sim/loop` when most people are
        # [EN] waiting; once it reaches `STALL_BREAK_BEATS`, `request_settle()` writes a positive
        # [EN] number here and `on_tick` takes the **settlement channel**.
        self._settle_beats: int = 0
        #: **上一次派给每个人的活**（`dispatch` 写，下一轮派活时递回去）。
        #: ★★★ 没有这一份，目标每 8 拍漂移一次 —— 实测同一晚三次派给同一个人的活
        #: 三件毫无关系，人物的线就每 8 拍被剪断一次（见 `dispatch` 里那段长注释）。
        # [EN] **Last assignment per person** (written by `dispatch`, handed back next round).
        # [EN] Without it the goal drifts every 8 beats -- measured: three unrelated assignments to
        # [EN] the same person in one night, cutting his thread every 8 beats.
        self._last_dispatch: dict[str, str] = {}
        #: **每个人最近 6 次派活**（`dispatch` 写）。★ 用来判"连着 3 次派了同一件事" ——
        #: 只看 `_last_dispatch` 判不出"连着"，而那正是配角被写成 NPC 的机制（见 `dispatch`）。
        # [EN] Last six assignments per person (written by `dispatch`). Used to detect "the same
        # [EN] assignment three times in a row": `_last_dispatch` alone cannot see a streak, and a
        # [EN] streak is exactly the mechanism that turns a supporting role into an NPC.
        self._dispatch_history: dict[str, list[str]] = {}
        # 用户/策略刚挑的剧情走向（`sim/loop._maybe_branch` 写进来）。
        # 它会被拼进下一次挑事的提示词 —— 让"选了往哪走"真的影响后面的事。
        # [EN] The plot direction the user/policy just chose (written in by `sim/loop._maybe_branch`).
        # [EN] It gets spliced into the next stirring-up prompt -- so that "choosing where to go" really
        # [EN] affects what happens next.
        self.branch_hint: str = ""
        # `INTERVENTION_POLICY=pause` 时挂在这里的一条"等作者确认的介入说明"；
        # `None` = 没有待确认的介入。由 `sim/loop` 读走并推给界面。
        # [EN] When `INTERVENTION_POLICY=pause`, an "intervention note awaiting author confirmation" hung here;
        # [EN] `None` = no intervention pending confirmation. Read by `sim/loop` and pushed to the UI.
        self._pending_intervention: str | None = None
        #: 挂起时**已经生成好的方向候选**（2026-10-26 新增）。
        #:
        #: ★★★ 与 `_pending_intervention` 是**一件事的两半**，必须一起看：
        #:   `_pending_intervention` 只是那句话（给中栏/日志），真正的选项在这里。
        #:   为什么不合成一个 dict：`_pending_intervention` 已经被 `sim/loop` 当
        #:   **字符串**读（`brief=str(_pend)`），改成 dict 会把那段说明变成
        #:   `{'why': ...}` 这种丑东西；而选项是结构化数据、要单独传。
        #: ⚠ 三个出口都要把它清掉：`confirm_intervention` / `skip_intervention` /
        #:   `_inject_rescue_event`。留着它，下一次挂起会拿到**上一轮**的方向。
        # [EN] **Direction candidates already generated** when hanging (added 2026-10-26).
        # [EN] ★★★ Two halves of one thing: `_pending_intervention` is just the sentence (middle
        # [EN] column / logs); the real options live here. Not merged into one dict because
        # [EN] `sim/loop` reads `_pending_intervention` as a **string** (`brief=str(_pend)`).
        # [EN] ⚠ All three exits must clear it, or the next hang reuses **stale** directions.
        self._pending_branches: list[dict] = []
        # 作者点了「继续」= 认可导演的介入方案 → 下一次停滞不再挂住，直接执行。
        # [EN] The author clicks "continue" = approves the director's intervention plan → the next stagnation
        # [EN] no longer hangs, it executes directly.
        self._intervention_confirmed = False
        # 停顿时钟走**故事时间**（分钟）—— 原来是 `time.time()`：
        # 一轮推演真实世界只过十几分钟，故事里可能过了三十天，
        # 于是"180 分钟没事件"这个判据在真实时间里几乎永远不成立。
        # 起点取**开局那一刻**（不是 -inf）：否则第一条日志会写
        # "已过 1000001920 分钟没有事件"这种看不懂的数。
        # [EN] Stagnation clock runs on **story time** (minutes) -- it used to be `time.time()`:
        # [EN] one round of simulation only passes a dozen or so minutes in the real world, but thirty days may
        # [EN] pass in the story,
        # [EN] so the criterion "180 minutes with no event" almost never holds in real time.
        # [EN] The starting point is **the moment the game begins** (not -inf): otherwise the first log entry
        # [EN] would say
        # [EN] "already 1000001920 minutes with no event", a number nobody can understand.
        self._last_event_game_min: float = self._game_min()
        #: **距上次事件过了多少拍**（2026-10-26 新增，停滞检测的主判据）。
        #:
        #: ★★★ 为什么改成数拍、不再只数故事分钟：
        #:   "一拍推多少分钟"由 `跨度 ÷ 拍数` 定（见 `ingest/progress.py`），
        #:   实测 20 个「跨度 × 篇幅」组合里 **15 个是一拍 30 分钟** ⇒ 旧口径
        #:   `180 分钟` 等于"6 拍就判停滞"。用户报的「过一会又回到这个循环」
        #:   就是这么来的：演 6 拍弹一次、弹出来还是同样两个选项。
        #:   拍数才是"演了多久"的正确单位 —— 一拍 = 一次人物决策。
        #: ⚠ `on_tick` 每拍 +1；凡"真的发生了一件事"的地方一律归零
        #:   （与 `_last_event_game_min` **成对**维护，只清一个是老坑）。
        # [EN] **Beats since the last event** (added 2026-10-26; the primary stall criterion).
        # [EN] "Minutes per beat" = span / beats, and measured **15 of 20** combinations are
        # [EN] 30 min/beat, so the old `180 minutes` meant "stall after 6 beats" -- that is exactly
        # [EN] the loop the user reported. Beats are the right unit: one beat = one character
        # [EN] decision. ⚠ Incremented in `on_tick`; zeroed wherever an event really happens,
        # [EN] **paired** with `_last_event_game_min` (clearing only one is a known pit).
        self._beats_since_event: int = 0
        self._climax_fired_day: int = 0
        # ★★ **这一轮已经注入过几件关键事件**（2026-10-11）——
        #   对着 `ROUND_EVENT_LIMIT` 用（0 = 不限）。只数"真的注入了"的，
        #   被 `_rate_gate` 拦下的不算（那件事没发生）。
        # [EN] ★★ **how many key events have already been injected this round** (2026-10-11) --
        # [EN] use against `ROUND_EVENT_LIMIT` (0 = unlimited). Only count ones "that were actually injected",
        # [EN] ones blocked by `_rate_gate` do not count (that thing never happened).
        self.events_this_round: int = 0
        #: 「上限已到」那句话只说一次（`may_inject` 用）
        # [EN] : the sentence "limit reached" is only said once (used by `may_inject`)
        self._limit_noticed: bool = False

    # ── 本轮的两个闸：要不要挑事（一处判，别在三处各写一遍）────────────
    # [EN] ── The two gates of this round: whether to stir things up (judge in one place, don't write it
    # [EN] three times) ────────
    def may_inject(self) -> bool:
        """这一轮**还允不允许导演主动挑事**。

        ★ 2026-10-11（用户：「起笔时控制……要不要发生关联事件还是只是一次
          日常生活型的推演不带关键剧情，大概发生几件事情」）。

        `on_tick()` 里有**三条**都会注入事件的路（高潮日强制 / 停滞自救 /
        张力低或安静够久的常规注入）。所以这个闸必须**在这里判一次**、
        由 `on_tick` 在开头统一拦 —— 在三条路上各写一遍，改一处就会漏两处。

        两条规则：
          · `ROUND_KIND=daily`（日常生活型）→ **一件都不挑**。
            这就是"不带关键剧情"：人物自己过日子，导演不插手。
            ⚠ **只关"注入事件"这一件事**，`_check_progress`（节点推进）照旧 ——
              用户选的是「有大事时照推」：剧情自然走到节点该满足时仍然推进。
          · `ROUND_EVENT_LIMIT`（>0 时）→ 挑够这个数就停手。

        返回 `False` = 这一轮导演不再主动挑事（`on_tick` 直接返回 None）。
        
                English:
        Whether this round **still allows the director to actively stir things up**.
                ★ 2026-10-11 (user: "control at the start of writing... whether to have a related event or just a
                  daily-life-style simulation without key plot, roughly a few things happen").
                `on_tick()` has **three** paths that all inject events (climax day forced / stagnation self-rescue /
                low tension or quiet long enough regular injection). So this gate must be judged **once here**,
                uniformly intercepted by `on_tick` at the start —— writing it once on each of the three paths means changing one place will miss two.
                Two rules:
                  · `ROUND_KIND=daily` (daily-life type) → **do not stir up a single thing**.
                    This is "no key plot": the characters live their own lives, the director does not interfere.
                    ⚠ **Only closes "event injection", this one thing**; `_check_progress` (node advancement) stays as before ——
                      what the user chose is "advance when there is a big event": when the plot naturally reaches a point where a node should be satisfied, still advance.
                  · `ROUND_EVENT_LIMIT` (when >0) → stop once this many have been picked.
                Returning `False` = this round the director no longer actively stirs things up (`on_tick` directly returns None).
        """
        try:
            kind = (CFG.s("ROUND_KIND") or "normal").strip().lower()
            if kind == "daily":
                return False
            limit = CFG.i("ROUND_EVENT_LIMIT")
        except Exception:                                        # noqa: BLE001
            return True
        if limit > 0 and self.events_this_round >= limit:
            if not self._limit_noticed:
                self._limit_noticed = True      # 只说一次（每拍都说就成刷屏了）
                # [EN] Only said once (saying it every beat becomes screen spam)
                _LOG.info("本轮事件上限（%d 件）已到 —— 导演不再主动挑事，"
                          "接下来靠人物自己走", limit)
            return False
        return True

    # ── 曲线与时间 ────────────────────────────────────────────────────
    # [EN] ── Curve and time ────────────────────────────────────────────────
    def _card_name(self) -> tuple[str, str]:
        """本作的（主题材, 结构轴）—— 来自 `类型卡.yaml`（`sim/setup` 灌进 `genre_card`）。
                English:
        This work's (theme genre, structural axis) —— from `类型卡.yaml` (`sim/setup` injects into
        `genre_card`).
        """
        g = getattr(self.world, "genre_card", None) or {}
        return (str(g.get("主题材") or "").strip(),
                str(g.get("结构") or "").strip())

    def _curve(self) -> tuple[float, float, float]:
        """当前生效的 (日衰减, 事件抬升, 高潮目标)。

        ★ `TENSION_CURVE=auto` 时的取值顺序 —— **张力目标 = 类型节奏模板 × 用户旋钮**
        （设计稿 §8.4），所以先看类型卡、再看节奏感：

        ① **类型卡写了张力曲线就用它**（悬疑灵异 medium、玄幻修仙 roller…）——
           工艺库存在的意义就是这个：不同题材该有不同的起伏形状；
        ② 类型卡没写 / 这本小说认不出类型 → 退回跟着 `PACING_STYLE` 走（老行为）。

        ⚠ 用户**显式**选了某一档时一律听用户的 —— 类型卡只补 `auto` 这个空。
        他在书斋里选了"过山车"，不该因为类型卡写着 medium 而变平。
        
                English:
        Currently effective (daily decay, event boost, climax target).
                ★ Value order when `TENSION_CURVE=auto` —— **tension target = genre rhythm template × user knob**
                (design doc §8.4), so look at the genre card first, then the pacing feel:
                ① **if the genre card specifies a tension curve, use it** (suspense-supernatural medium, xianxia-cultivation roller...) ——
                   this is the point of the craft library existing: different genres should have different ups and downs;
                ② genre card does not specify / this novel's genre cannot be recognized → fall back to following `PACING_STYLE` (old behavior).
                ⚠ when the user **explicitly** picks one tier, always defer to the user —— the genre card only fills the `auto` gap.
                He picked "roller coaster" in the study, it should not flatten out just because the genre card says medium.
        """
        name = (CFG.s("TENSION_CURVE") or "auto").strip()
        if name == "auto":
            name = (craftmix.card_curve(*self._card_name())
                    or _AUTO_BY_PACING.get(
                        (CFG.s("PACING_STYLE") or "medium").strip(), "medium"))
        return _TENSION_CURVE.get(name, _TENSION_CURVE["medium"])

    def _game_min(self) -> float:
        return float(self.world.clock.minutes + self.world.clock.day * 1440)

    def is_climax_day(self) -> bool:
        """今天是不是高潮日（每 `CLIMAX_EVERY_DAYS` 天一次）。
                English:
        Whether today is a climax day (once every `CLIMAX_EVERY_DAYS` days).
        """
        n = max(1, CFG.i("CLIMAX_EVERY_DAYS"))
        return self.world.game_day % n == 0

    def on_day_start(self) -> float:
        """跨天时调一次：**张力按曲线回落**。

        不回落，事件注入那条路就会在第一天之后永久关闭（见 `_TENSION_CURVE` 的说明）。
        返回回落后的张力。
        
                English:
        Called once on day rollover: **tension falls back along the curve**.
                Without fallback, the event injection path would be permanently closed after the first day (see the note on `_TENSION_CURVE`).
                Returns the tension after fallback.
        """
        decay, _rise, _target = self._curve()
        before = float(self.world.tension)
        self.world.tension = max(0.0, min(1.0, before * decay))
        if abs(before - self.world.tension) > 0.01:
            _LOG.info("张力回落（%s 曲线）：%.2f → %.2f",
                      CFG.s("TENSION_CURVE"), before, self.world.tension)
        return self.world.tension

    def tension_rise(self, intensity: float) -> float:
        """事件注入后抬升张力（系数来自曲线，不再是写死的 0.3）。
                English:
        Raise tension after event injection (coefficient comes from the curve, no longer a hardcoded
        0.3).
        """
        _decay, rise, _target = self._curve()
        self.world.tension = max(0.0, min(1.0, self.world.tension + intensity * rise))
        return self.world.tension

    # ── tick 入口（每 tick 调用一次）──────────────────────────────────
    # [EN] ── tick entry (called once per tick) ──────────────────────────────
    async def on_tick(self) -> DirectorEvent | None:
        """每 tick 调用：监测停滞、评估进度、可能注入事件。返回 None 表示本轮不介入。
                English:
        Called every tick: monitor stagnation, evaluate progress, possibly inject events. Returning None
        means no intervention this round.
        """
        if not CFG.b("DIRECTOR_ENABLED"):
            return None
        # ★ 2026-10-26：**每拍先记一拍**（停滞检测的主判据是"连续多少拍没事件"）。
        #   ⚠ 放在 `may_inject()` 之前：即使本轮被闸拦下（不挑事），这一拍也确实演过了 ——
        #     拍数该涨。放在后面的话，"日常生活型"永远攒不满，停滞判据形同虚设。
        # [EN] ★ Count the beat first (the primary stall criterion is "beats without an event").
        # [EN] ⚠ Before `may_inject()`: even when the gate blocks this beat, it still happened, so the
        # [EN] count must advance -- otherwise "daily-life type" never accumulates and the stall
        # [EN] criterion is dead.
        self._beats_since_event += 1
        # ★★ **本轮的两个闸**（2026-10-11，一处判，见 `may_inject` 的说明）。
        #   必须在**三条注入路之前**拦：高潮日强制 / 停滞自救 / 常规注入
        #   都会注入事件，漏掉任何一条，"日常生活型"就不成立
        #   （高潮日那条尤其隐蔽：它**不受张力门槛限制**，一定会挑事）。
        # [EN] ★★ **The two gates of this round** (2026-10-11, judged in one place, see the note on
        # [EN] `may_inject`).
        # [EN] Must block **before the three injection paths**: climax-day forced / stagnation self-rescue /
        # [EN] regular injection
        # [EN] all inject events; miss any one of them and "daily-life type" does not hold
        # [EN] (the climax-day one is especially hidden: it is **not subject to the tension threshold**, and
        # [EN] will definitely stir things up).
        if not self.may_inject():
            return None

        ev = await self._on_tick_enabled()
        if ev is not None:
            # 只数"真的注入了"的 —— 被 `_rate_gate` 拦下的那件事没发生。
            # [EN] Only count ones "that were actually injected" -- the thing blocked by `_rate_gate` never
            # [EN] happened.
            self.events_this_round += 1
        return ev

    def _mark_event(self) -> None:
        """**记一次"真的有事件发生"**：拨时钟 + 拍数归零，两件事永远一起做。

        ★★★ 2026-10-26：为什么必须合成一个方法 ——
          "距上次事件"现在有**两个**度量（故事分钟 / 拍数），它们**必须同时**归零。
          分开写就是本项目反复栽的那个坑："一处改了、另一处忘了" ⇒ 停滞检测
          用其中一个判，另一个永远停在旧值 ⇒ 要么永不触发，要么每拍都触发。
          ⇒ 谁要说"这件事发生了"，就调这一个方法，别自己去戳两个字段。

        ⚠ "跳过时间"（`note_time_skipped`）与"作者说这次不用"（`skip_intervention`）
          语义上也算"这一段过去了"，同样走这里 —— 否则跳过之后会立刻判停滞。

        English:
        **Record that an event really happened**: bump the clock and zero the beat counter, always
        together. ★★★ 2026-10-26: "time since last event" now has **two** measures (story minutes and
        beats) and they must be reset **together**; writing them apart is this project's recurring
        pit ("one place changed, the other forgotten"), leaving one stuck at an old value so the
        detector either never fires or fires every beat. ⚠ "Time skipped" and "author said not this
        time" also count as "this span has passed" -- otherwise a stall fires right after a skip.
        """
        self._last_event_game_min = self._game_min()
        self._events_since_stall = 0
        self._beats_since_event = 0

    async def _on_tick_enabled(self) -> DirectorEvent | None:
        """`on_tick` 的实体（闸门在调用方 —— 见 `may_inject`）。
                English:
        The entity of `on_tick` (the gate is on the caller side —— see `may_inject`).
        """
        tension = self.world.tension
        if CFG.b("DEBUG_MODE"):
            _LOG.debug("导演 tick: 张力=%.2f, 曲线=%s, 高潮日=%s, 当前节点=%s",
                       tension, CFG.s("TENSION_CURVE"), self.is_climax_day(),
                       self.world.current_node)

        # ① 高潮日：先把张力抬到曲线目标，再**强制**挑事一次
        #    （不受 `tension < 0.4` 那个门槛限制 —— 那正是"越跑越平"的根源）
        # [EN] ① Climax day: first raise tension to the curve target, then **force** stirring things up once
        # [EN] (not subject to the `tension < 0.4` threshold -- that is exactly the root of "flatter and
        # [EN] flatter as it runs")
        if self.is_climax_day() and self._climax_fired_day != self.world.game_day:
            self._climax_fired_day = self.world.game_day
            _decay, _rise, target = self._curve()
            if self.world.tension < target:
                _LOG.info("高潮日（第 %d 天）：张力 %.2f → %.2f",
                          self.world.game_day, self.world.tension, target)
                self.world.tension = target
            event = await self._inject_event(reason_hint="今天是这一轮的高潮日")
            if event:
                return event

        # ①.5 ★★★ **僵局结算**（2026-10-19）—— 排在停滞检测**前面**。
        #
        #   为什么必须先：停滞检测走**故事时间**（`STALL_WINDOW_MINUTES`），
        #   而僵局走**拍数**。真跑实证（《雪国》34 拍）：三个人的戏在同一间屋里
        #   等了 7 拍 "门外脚步"，故事时间还没到停滞窗口 ⇒ 一次都没被介入；
        #   等真到了窗口，注入的又是「外部刺激」（再添一个悬念）⇒ 越等越死。
        #   ⇒ 按拍计数、按"结算"出手，这一条才有救。
        # [EN] ★★★ Deadlock settlement (2026-10-19) -- placed **before** stagnation detection.
        # [EN] Stagnation runs on story time, deadlock on beat count. Measured (Snow Country, 34
        # [EN] beats): three people waited 7 beats for the footsteps outside, story time never reached
        # [EN] the stall window; and when it did, the injected event was "external stimulus" (one more
        # [EN] suspense), so it only got deader. Count by beats, act by settlement.
        if self._settle_beats > 0:
            _n = int(self._settle_beats)
            self._settle_beats = 0
            _LOG.info('僵局结算：连着 %d 拍大多数人都在等 ⇒ 给那个悬置一个结果', _n)
            event = await self._inject_event(settle=_n)
            if event:
                # ⚠ 结算也是一次"事件"：不拨这个时刻，停滞检测下一拍立刻又触发
                #   （`_is_stalling` 看的就是"距上次事件多久"）。
                # [EN] ⚠ A settlement is still an event: without bumping this timestamp the stall
                # [EN] detector fires again next beat.
                self._mark_event()
                return event

        # ② 停滞检测 —— **按拍数**判（`STALL_WINDOW_BEATS`），故事时间只做保护下限
        # [EN] ② Stagnation detection -- counted in **beats** (`STALL_WINDOW_BEATS`); story time is
        # [EN] only a floor
        if self._is_stalling():
            _LOG.info("检测到剧情停滞（连续 %d 拍、故事时间已过 %.0f 分钟没有事件），导演介入",
                      self._beats_since_event,
                      self._game_min() - self._last_event_game_min)
            # ⚠ 这里**不再**清 `_events_since_stall`：它原先是"本轮别再问一遍"的标记，
            #   而 `_is_stalling` 已经不看它了（那个字段全文件只有清零、没有自增，
            #   所以一直是 0 —— 留着只会让人以为"还有一层保护"）。
            #   "别马上又问一遍"现在由两个出口负责：`confirm_intervention()`（真去做了）
            #   与 `skip_intervention()`（作者说不用）—— 两者都调 `_mark_event()`。
            # [EN] ⚠ No longer clears `_events_since_stall`: it was a "don't ask again this round"
            # [EN] flag, and `_is_stalling` no longer reads it (that field is only ever zeroed,
            # [EN] never incremented, so it was always 0 -- keeping it would suggest a second safety
            # [EN] layer that does not exist). The two exits handle "don't ask again": 
            # [EN] `confirm_intervention()` and `skip_intervention()`, both via `_mark_event()`.
            # ★ `INTERVENTION_POLICY`（2026-10-06 接线）：导演**主动改变方向**
            #   （停滞自救属于这类）时要不要先问作者。
            #   `pause`（默认）= 挂住等作者拍板；`auto_resolve` = 导演自己定、继续跑。
            #   ⚠ 只管"改变方向"的介入，**不管每一次普通事件注入** ——
            #     后者每几拍就一次，拿它去 pause 等于把推演卡死。
            # [EN] ★ `INTERVENTION_POLICY` (wired 2026-10-06): whether the director, when it **proactively changes
            # [EN] direction**
            # [EN] (stall self-rescue falls in this category), should ask the author first.
            # [EN] `pause` (default) = hang and wait for the author to decide; `auto_resolve` = the director
            # [EN] decides on its own and keeps running.
            # [EN] ⚠ Only covers "change of direction" interventions, **not every ordinary event injection** ——
            # [EN] the latter happens every few beats; using it to pause would deadlock the simulation.
            if ((CFG.s("INTERVENTION_POLICY") or "pause").strip() != "auto_resolve"
                    and not self._intervention_confirmed):
                # ★★★ 2026-10-26：**挂起前先把方向真的生成出来**。
                #
                #   用户报的两个问题都在这一段：
                #     ① 「只有两个选项（听导演的 / 这次不用），不该只有这几个」；
                #     ② 「为何导演的建议每次都是有人敲门」。
                #   原来这里只写一段**硬编码文字**就 return，方案要等作者点了
                #   「听导演的」之后才由 `_inject_rescue_event()` 生成 ——
                #   也就是说，**做选择的时候方案根本还不存在**，
                #   作者在对话框里看到的"方案"就是那句写死的「有人敲门打断僵局」。
                #   ⇒ 现在先调 `propose_branches('stall')` 拿到 2~4 个具体方向，
                #     放进 `_pending_branches`，由 `sim/loop` 摆成选项。
                #   ⚠ 拿不到候选（模型失败/空表）就**退回老行为**（只给"这次不用"），
                #     绝不编造方向 —— 宁可少几个选项，也不要喂假方案。
                # [EN] ★★★ 2026-10-26: **generate the directions before hanging**.
                # [EN] Both user complaints live here: (1) "only two options", (2) "why always
                # [EN] someone knocking". This used to write one **hardcoded string** and return;
                # [EN] the plan was only produced by `_inject_rescue_event()` *after* the author
                # [EN] clicked "follow the director" -- i.e. **no plan existed at decision time**,
                # [EN] so what the dialog showed as "the plan" was that fixed sentence.
                # [EN] => Call `propose_branches('stall')` first, stash it in `_pending_branches`,
                # [EN] and let `sim/loop` build the options. ⚠ If it yields nothing, fall back to
                # [EN] the old behaviour ("not this time" only) -- never invent directions.
                try:
                    self._pending_branches = await self.propose_branches(reason='stall')
                except Exception as e:                            # noqa: BLE001
                    _LOG.warning("停滞时提方向失败（退回只给「这次不用」）：%r", e)
                    self._pending_branches = []
                _n_opt = len(self._pending_branches or [])
                self._pending_intervention = (
                    "剧情停滞太久（连续 %d 拍没有事件）。"
                    % max(0, self._beats_since_event)
                    + (f"导演提了 {_n_opt} 个方向，你挑一个；"
                       if _n_opt else "这次没提出方向，")
                    + "也可以自己写一件要发生的事，或者说「这次不用」。")
                _LOG.info("停滞介入按 pause 挂住，等作者确认（方向 %d 个）", _n_opt)
                return None
            return await self._inject_rescue_event()

        # ③ 张力低 **或** 安静得够久 → 注入事件（判据见 `should_intervene`）。
        # [EN] ③ Low tension **or** quiet for long enough → inject an event (criteria in `should_intervene`).
        if self.should_intervene():
            return await self._inject_event()

        return None

    def should_intervene(self) -> bool:
        """该不该挑事（`on_tick` 的第 ③ 步用的就是它）。

        ★★ 2026-10-10 实测出来的一个**设计缺陷**（用户第一次真跑一天之后报的
           「五人台词几乎原地循环、掌柜该给的坦白拍没有落地」）：

           原来这条路只有 `tension < 0.4` 一个闸。而张力**在一天之内只升不降**
           —— 唯一回落的地方是 `on_day_start()`（跨天那一刻）。于是一次事件
           抬升 ~0.10 之后（0.30 → 0.41），这个闸**当天就再也打不开了**。

           而"一天"有多长？那次实测：`停点.json` 写着 **ticks_today = 391**。
           日志侧的证据完全吻合：391 拍里 `director_event` 只被问过 **3 次**
           （19:25:36 / 19:26:09 / 19:27:04，强度 0.35/0.35/0.4 ⇒ 张力 0.30→0.63），
           **之后 49 分钟一个事件都没有**。也就是说这一天 89% 的时间里，
           舞台上没有任何外部刺激 —— 人物只能自己跟自己重复。

           为什么会这样：`drama_level × conflict_freq = 0.24/拍` 明显是**想要
           常有事件**的（24% 的拍都该挑事），而绝对阈值的闸把它压成了"一天 1 个"。
           ⇒ 绝对阈值不能是唯一判据：**还得看"安静了多久"**。

        ⇒ 两个信号**任一成立**就算"该挑"：
             · `tension < 0.4` —— 原来的口径，一个字没改；
             · 或距上次事件已过 `DIRECTOR_QUIET_MINUTES` 故事分钟 —— 兜底，
               保证这一天剩下的几百拍里总还有东西发生。
          概率那一层（`drama_level * conflict_freq`）照旧，所以事件的**密度**
          仍然由用户那两个旋钮说了算；这里只是不让它掉到零。

        ⚠ **没有**改成"让张力按故事时间衰减"：那会把 `world.tension` 长期压在低位，
          而它还被别处读（`crowd.py` 的群演反应阈值、`layers.should_expand` 的
          展开门、存档快照）。动一个信号去修另一处的闸，会把那三处一起改掉。

        ⚠ 抽成一个**同步**方法的第二个理由：`on_tick` 是 async，而判据里为了一条
          断言去起事件循环不值当 —— 判据可以直接调这个（`verify_sim_depth` A12c）。
        
                English:
        Whether to stir things up (step ③ of `on_tick` uses exactly this).
                ★★ A **design flaw** found in real testing on 2026-10-10 (reported by the user after actually running a day for the first time
                   "the five people's lines almost loop in place, the shopkeeper's overdue confession beat never lands"):
                   Originally this path had only one gate: `tension < 0.4`. And tension **only rises within a day, never falls**
                   —— the only place it falls is `on_day_start()` (the moment of day rollover). So after one event
                   raises it ~0.10 (0.30 → 0.41), this gate **can no longer open for the rest of the day**.
                   And how long is "a day"? That test run: `停点.json` said **ticks_today = 391**.
                   The log-side evidence matches perfectly: out of 391 beats, `director_event` was asked only **3 times**
                   (19:25:36 / 19:26:09 / 19:27:04, intensity 0.35/0.35/0.4 ⇒ tension 0.30→0.63),
                   **then for 49 minutes not a single event**. That is, for 89% of this day,
                   there was no external stimulus on stage —— the characters could only repeat themselves.
                   Why this happens: `drama_level × conflict_freq = 0.24/beat` clearly **wants
                   frequent events** (24% of beats should stir things up), but the absolute-threshold gate squeezed it into "1 per day".
                   ⇒ An absolute threshold cannot be the sole criterion: **must also look at "how long it has been quiet"**.
                ⇒ If **either** of the two signals holds, it counts as "should stir":
                     · `tension < 0.4` —— the original criterion, not one word changed;
                     · or it has been `DIRECTOR_QUIET_MINUTES` story minutes since the last event —— a fallback,
                       ensuring that in the remaining several hundred beats of the day something still happens.
                  The probability layer (`drama_level * conflict_freq`) stays as before, so the **density** of events
                  is still up to the user's two knobs; this just keeps it from dropping to zero.
                ⚠ **Not** changed to "let tension decay with story time": that would keep `world.tension` pinned low long-term,
                  and it is read elsewhere (`crowd.py` extras' reaction thresholds, `layers.should_expand`'s
                  expansion gate, save snapshots). Moving one signal to fix another gate would change all three at once.
                ⚠ Second reason to extract it into a **synchronous** method: `on_tick` is async, and in the criteria spinning up an event loop just for one
                  assertion is not worth it — the criteria can call this directly (`verify_sim_depth` A12c).
        """
        tension = float(getattr(self.world, 'tension', 0.0) or 0.0)
        quiet = self._game_min() - self._last_event_game_min
        quiet_enough = quiet >= max(1, CFG.i("DIRECTOR_QUIET_MINUTES"))
        if not (tension < 0.4 or quiet_enough):
            return False
        if quiet_enough and tension >= 0.4:
            _LOG.info("安静了 %.0f 故事分钟（张力 %.2f 还高着）→ 照常挑事",
                      quiet, tension)
        return random.random() < CFG.f("DRAMA_LEVEL") * CFG.f("CONFLICT_FREQUENCY")

    # ── 事件注入 ──────────────────────────────────────────────────────
    # [EN] ── Event injection ──────────────────────────────────────────────────────
    def _rate_gate(self, event: DirectorEvent) -> DirectorEvent | None:
        """按 `REVEAL_PACING` / `COINCIDENCE_RATE` / `NEW_FACE_RATE` 放行或拦下。

        三个旋钮**各管一件事**，别混：

        | 旋钮 | 管什么 | 拦下来的表现 |
        |---|---|---|
        | `COINCIDENCE_RATE` | "巧合"这一**类事件**还允不允许出现 | 0 = 这世界没有巧合，整件事丢掉 |
        | `NEW_FACE_RATE` | 事件里**凭空造的新人物** | 0 = 只用在场的人，新名字就地剔除 |
        | `REVEAL_PACING` | **揭示型**（秘密泄露 / 伏笔激活）的节奏 | 0 = 一直不揭，攒着 |

        ★ 为什么新面孔是"剔除名字"而不是"丢掉整件事"：事件本身（"门口有人敲门"）
          可能是有用的，不该因为多带了一个名字就整条扔掉 —— 那是把好事一起毙掉。
          而巧合是**类型**问题（这个世界允不允许巧合），只能整条丢。

        返回 `None` = 这件事这一轮不注入；否则返回（可能改过 `involved` 的）事件。
        
                English:
        Allow or block based on `REVEAL_PACING` / `COINCIDENCE_RATE` / `NEW_FACE_RATE`.
                The three knobs **each govern one thing**, do not mix them up:
                | Knob | Governs | Behavior when blocked |
                |---|---|---|
                | `COINCIDENCE_RATE` | whether the **class of events** called "coincidence" is still allowed to occur | 0 = this world has no coincidences, drop the whole event |
                | `NEW_FACE_RATE` | **new characters conjured out of thin air** within an event | 0 = use only people present, strip new names on the spot |
                | `REVEAL_PACING` | pacing of **revelation-type** (secret leak / foreshadow activation) | 0 = never reveal, keep it banked |
                ★ Why new faces are "strip the name" rather than "drop the whole event": the event itself ("someone knocks at the door")
                  may be useful, and shouldn't be thrown away entirely just because it brought an extra name — that kills the good along with it.
                  Whereas coincidence is a **type** problem (whether this world allows coincidences at all), and can only be dropped whole.
                Return `None` = do not inject this event this round; otherwise return the event (possibly with modified `involved`).
        """
        known = set(getattr(self.world, "people", {}) or {})
        # 新面孔：把不在名册里、也不是群演的名字剔掉（群演走 `world/crowd.py`）
        # [EN] New faces: strip out names not in the roster and not extras (extras go through `world/crowd.py`)
        rate_new = max(0.0, min(1.0, CFG.f("NEW_FACE_RATE")))
        if event.involved:
            fresh = [n for n in event.involved if n and n not in known]
            keep = [n for n in event.involved if not n or n in known]
            for name in fresh:
                if random.random() < rate_new:
                    keep.append(name)
            if fresh and len(keep) < len(event.involved):
                _LOG.info("新面孔闸（%.2f）：从「%s」里剔除 %s",
                          rate_new, event.description[:24],
                          "、".join(n for n in fresh if n not in keep))
            event.involved = keep

        etype = str(event.event_type or "")
        if "巧合" in etype:
            rate = max(0.0, min(1.0, CFG.f("COINCIDENCE_RATE")))
            if random.random() >= rate:
                _LOG.info("巧合闸（%.2f）：本轮不注入「%s」", rate,
                          event.description[:30])
                return None
        elif "秘密" in etype or "伏笔" in etype:
            rate = max(0.0, min(1.0, CFG.f("REVEAL_PACING")))
            if random.random() >= rate:
                _LOG.info("揭示节奏闸（%.2f）：本轮先不揭「%s」", rate,
                          event.description[:30])
                return None
        return event

    @MODELS.agent('director')
    async def _inject_event(self, reason_hint: str = "", settle: int = 0) -> DirectorEvent | None:
        """注入一件外部事件。

        `settle` > 0 表示**僵局结算通道**（2026-10-19）：场面已经连着这么多拍
        没人动，大多数人在等同一件事。这时不按压力分类型 —— 因为压力算出来的
        "外部刺激"恰恰是**再添一个悬念**（真跑实证：《雪国》34 拍里连出三个
        "门外有脚步声"，全员在等，谁都没动）。僵局要的是**结算**，不是新悬念。
        """
        node_info = self.world.current_node_info()
        node_name = node_info.get("名称", "未知") if node_info else "未知"
        node_summary = node_info.get("概要", "") if node_info else ""
        on_stage = ", ".join(self.world.on_stage_names()[:4])
        # ★ 2026-10-19 第十二轮：把**不在场**的人也递过去。
        #   `离场人物` / `进场人物` 两栏必须从两个名单里挑；只给在场名单
        #   ⇒"这件事让谁回来了"无处可填（那一栏只能空着，等于没这个字段）。
        # [EN] Round twelve: pass the **off-stage** names too. The two new fields must
        # [EN] pick from both lists; on-stage alone leaves "who does this bring back"
        # [EN] unanswerable (that field could only stay empty, i.e. not exist).
        _off = [n for n in self.world.off_stage_names()
                if n not in on_stage][:4]
        off_line = (f"\n不在场（可被这件事带回来）：{', '.join(_off)}"
                    if _off else '')

        # ★★★ 2026-10-19：**世界法则** —— 先算压力，再让压力最大的那条自己破掉。
        #
        #   改之前：这里直接问模型「请设计一个戏剧事件」。那是**编剧**的活：
        #   他想"这里该有个转折"，然后编一个。两个后果都量到过：
        #     ① **收敛**：同一部《雪国》跑两次，文字重合 9.7%，**骨架重合 62.5%** ——
        #        因为"设计一个事件"这个问题本身就把答案收窄了（模型会挑最安全的那类）；
        #     ② **不可解释**：读者说不出"这件事为什么现在发生"。
        #
        #   改之后：类型由 `director.pressure` 从世界状态**算**出来（四个连续量，
        #   纯代码、零模型调用）。模型只负责把它**写具体** —— 写成一件事，
        #   而不是挑一类事。这是"写作"与"推演"的分界：
        #     写作 = 我要这个效果，所以安排这个事件；
        #     推演 = 这个局面必然导致这个事件。
        #
        #   ⚠ `reason_hint` 非空（高潮日 / 停滞自救）时**即使四条压力全低也要出事** ——
        #     那两条路本来就是"不能再等"的强制通道，让它们被压力门槛拦掉等于
        #     把它们废掉（而"越跑越平"正是这样来的）。这时取最高的一条，
        #     哪怕它低于 `MIN_PRESSURE`；四条全为 0 时退回"外部刺激"。
        # [EN] ★★★ 2026-10-19: **world law** -- compute pressure first, then let the strongest
        # [EN] pressure break itself open. Before: the model was asked to "design a dramatic event",
        # [EN] which is a **screenwriter's** job. Two measured consequences: convergence (two Snow
        # [EN] Country runs shared 9.7% of text but **62.5% of skeleton** -- the question itself
        # [EN] narrows the answer), and unexplainability. After: the type is **computed** from world
        # [EN] state (four continuous values, pure code, zero model calls); the model only writes it
        # [EN] concretely. ⚠ When `reason_hint` is set (climax day / stagnation rescue) an event must
        # [EN] happen **even if all four pressures are low** -- those are the "cannot wait" channels,
        # [EN] and letting the threshold block them is exactly how "flatter and flatter" happens.
        try:
            from director import pressure as PRESS
            _left = None
            try:
                _per_day = int(86400 // max(1, CFG.i('BEAT_SECONDS')))
                _left = max(0, _per_day - int(getattr(self, '_beats_today', 0) or 0))
            except Exception:                                    # noqa: BLE001
                _left = None
            _pkey, _ev_type, _pval, _pr = PRESS.decide(self.world, beats_left_today=_left)
            _pr_why = str((_pr.why or {}).get(_pkey, '') or '').strip()
            # ★★★ **状态停滞时就换一类事**（2026-10-20，`director/stall.py` 的 `vary` 档）。
            #
            #   实测（望江楼那篇）：24 拍里 5 个事件全是同一个形态 —— 又有人上门
            #   （送油的、讨布钱的、找弟弟的、送药的）。根因不是模型偷懒，是**结构**：
            #   四条压力里 `time`（时间压力）随拍数**单调上升**（`0.55*一天过去 + 0.45*快收工`），
            #   而另外三条是状态量。在"取最大"的比较里，单调量**长期必然赢** ⇒
            #   越到一天的末尾越是"外部刺激" ⇒ 模型把它具体化成"来个陌生人"。
            #
            #   ⚠ 这里**不改** `PRESS.decide` 的算法（那是十几轮真跑调出来的），
            #     只在它给出同一类事的**连续第二拍起**，换成压力次大的那一类。
            #     换不动（只有一类够门槛）就照旧 —— 宁可连着同类，
            #     也不能凭空造一个低压力的事（那会让推演不可解释）。
            # [EN] When the world state has not changed for several beats, switch to a
            # [EN] different event type than the previous beat (the `vary` tier). Measured: all
            # [EN] five injected events in one run were "someone new walks in" -- because the
            # [EN] `time` pressure rises monotonically and therefore always wins in the end.
            # [EN] The algorithm itself is untouched; only a repeat of the *same* type is
            # [EN] swapped for the runner-up, and only when another candidate clears the bar.
            try:
                from director import stall as _STALL
                _last = str(getattr(self, '_last_ev_type', '') or '')
                if _last and int(getattr(self.world, 'stall_beats', 0) or 0) >= _STALL.VARY_AT:
                    _swapped = _STALL.pick_type(_pr, _last)
                    if _swapped and _swapped != _ev_type:
                        _ev_type = _swapped
                self._last_ev_type = _ev_type
            except Exception as e:                               # noqa: BLE001
                _LOG.debug('停滞换类失败（照常用原类型）：%r', e)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('压力计算失败，退回"外部刺激"（不影响出片）：%r', e)
            _pkey, _ev_type, _pval, _pr, _pr_why = '', '外部刺激', 0.0, None, ''

        if not _ev_type:
            if not reason_hint and not settle:
                # 四条压力全低 ⇒ **这一拍本就不该出事**。让世界自己安静地往前走，
                # 那正是"日常生活型"该有的样子（而不是每 8 拍硬凑一件事）。
                # [EN] All four pressures low => **nothing should happen this beat**. Let the world
                # [EN] move quietly -- that is what a slice-of-life stretch looks like.
                _LOG.info('世界法则：四条压力都低（%s），这一拍不安排事件',
                          _pr.line() if _pr is not None else '—')
                return None
            _ev_type = '外部刺激'
            # ⚠ 压力全低时没有"证据"可说 —— 但**不许空着**，也**不许编一个**。
            #   诚实的说法是："这一拍是被强制推的，不是因为局面逼到了这一步"。
            #   这条理由会进日志与事件表，事后看得出"这一次不是自然发生的"。
            # [EN] With all pressures low there is no evidence to cite -- but do not leave it empty
            # [EN] and do not invent one. The honest line is: "forced through, not because the
            # [EN] situation demanded it". It goes into the log and the event table, so a later
            # [EN] review can tell "this one did not happen naturally".
            _pr_why = _pr_why or f'四股压力都低，这一拍是被强制推的（{reason_hint or "僵局结算"}）'
            _LOG.info('世界法则：压力全低，但这次是强制通道（%s）⇒ 仍出一件事',
                      reason_hint or '僵局结算')

        # ★★★ **僵局结算通道**（2026-10-19）：连 N 拍全员在等同一件事 ⇒ **不按压力分类型**。
        #   为什么不能按压力：僵局时"时间压力"往往最高 ⇒ 算出「外部刺激」⇒
        #   模型写"门外又传来脚步声" ⇒ **悬念再加一层，人更不动**。
        #   真跑实证：《雪国》34 拍里连着三次"廊下有脚步"，7/14 拍是 `wait`。
        #   ⇒ 僵局要的是**结算**：用「巧合」（外物先撑不住）逼在场的人动 ——
        #     它不需要人物动机，是唯一能打破"全员干等"的类型。
        #   ⚠ 类型由代码定死，模型只负责写具体（与压力通道同一条纪律）。
        _settle_seg = ''
        if settle:
            _ev_type = '巧合'
            _pr_why = (f'场面连着 {int(settle)} 拍没人动（大多数人在等同一件事，'
                       f'那件事一直没结果）')
            _settle_seg = (
                f'\n\n[这一场僵住了]\n'
                f'- 已经连着 {int(settle)} 拍：场上**没有出现新的事实** —— '
                f'要么都在等同一件事，要么在来回说同一类话（同一句台词、同一个问题反复问）。\n'
                f'- 这一拍**必须给出一个新事实**，**不是**再挂一层悬念，**也不是**把刚才的话再说一遍。\n'
                f'- 新事实的样子：门真的开了 / 人真的进来了 / 人真的走了 / '
                f'手里的东西掉了、洒了、断了 / **有人说出了一件此前没人知道的事**'
                f'（一句实话、一个决定、一句拒绝）。\n'
                f'- ❌ 不许写"门外又传来脚步声""远处又有人喊""好像有什么在动"'
                f'这类**再挂一层**的写法（读者会以为又要等一轮）。\n'
                f'- ❌ 也不许让同一个人把刚才那句话再说一遍 —— 换个语气、换几个字，都还是同一句。\n'
                f'- 事件必须是**物理上或信息上真发生的**，逼在场的人不得不动一下、或者不得不改口。\n')
        # ⚠ 僵局时**不用**压力那段：那段写着"四股压力：… / 不要换类型"，
        #   而僵局通道**正是**绕开了压力去改类型 —— 两段并排会把模型搞糊涂。
        # [EN] ⚠ In a deadlock the pressure block is **not** used: it says "four pressures: ... /
        # [EN] do not change the type", while the deadlock channel **does** bypass pressure to change
        # [EN] the type -- putting both side by side would confuse the model.
        _pressure_seg = (f'\n\n[局面推到了这一步]\n- {_pr_why or "四股压力里这一股最大"}\n'
                         f'- 四股压力：{_pr.line() if _pr is not None else "—"}\n'
                         f'- ⚠ 不要换类型，也不要写"什么都没发生" —— 这一类事**已经**在发生了。'
                         ) if (_pr is not None and not settle) else ''
        if settle:
            _pressure_seg = _settle_seg

        # ★ 导演原先只知道"当前节点 + 张力 + 在场" —— 不知道这个世界是什么样子，
        #   于是注入的事件可以是任何一本小说的（"更夫报说后巷出了事"放进科幻里
        #   也能用）。接上世界前缀，事件才贴得住这本小说。
        # [EN] ★ The director previously only knew "current node + tension + present" —— it did not know what
        # [EN] this world looks like,
        # [EN] so the injected event could be from any novel ("the watchman reports trouble in the back alley"
        # [EN] dropped into sci-fi
        # [EN] still works). Only by prefixing the world does the event stick to this novel.
        world_line = self.world.world_prefix()

        # ★★ 叙事工艺库（设计稿 §8.4）：按类型取**冲突偏好 + 钩子 + 爽点 +
        #   playbook 片段**（≤2 条、每条 ≤80 token 限流，在 `craftmix.brief` 里
        #   用代码截断，不靠人自觉）。没有类型卡时返回空串，这段就是空的。
        # [EN] ★★ Narrative craft library (design doc §8.4): by genre, fetch **conflict preference + hooks +
        # [EN] payoff +
        # [EN] playbook fragments** (≤2 items, each ≤80 tokens throttled, truncated in code in
        # [EN] `craftmix.brief`,
        # [EN] not relying on human self-discipline). Returns an empty string when there is no genre card, so
        # [EN] this section is empty.
        # ★★★ 2026-10-18：**传 offset 让它轮换**。
        #   老写法不传 ⇒ 永远取映射列表前 2 条 ⇒ 第 3、4 条一辈子进不了提示词
        #   （实测 6 张类型卡共 8 条手艺被永久淘汰，见 `entries_for` 的说明）。
        #   offset 用"天 + 拍"：同一天不同拍读不同手艺，跨天也错开；可复现。
        # [EN] ★★★ 2026-10-18: **pass offset so it rotates**. Not passing it meant always taking the
        # [EN] first 2 of the mapping, so items 3-4 could never reach a prompt (measured: 8 techniques
        # [EN] permanently eliminated across 6 genre cards; see `entries_for`). offset = day + beat:
        # [EN] different beats of a day read different techniques, days offset too, and reproducible.
        _craft_off = 0
        try:
            _craft_off = (int(getattr(self.world, 'day', 0) or 0) * 3
                          + int(getattr(self, '_tick_no', 0) or 0))
        except Exception:                                        # noqa: BLE001
            _craft_off = 0
        craft_block = craftmix.brief(*self._card_name(), offset=_craft_off)
        # ★★ **拆书库里匹配上的同类书写法**（2026-10-07 第六轮）——
        #   挑事是导演"把故事往哪儿带"的那一刻，属于用户说的"优化故事"。
        #   这里给的是**完整版**（节奏/立人/文风/**不要照搬什么**）——
        #   挑事要的正是"这一步该压还是该爆"，那恰好是"节奏"那一条。
        #   ⚠ 只在类型卡命中时才取得到（`store.match` 不硬塞），
        #     拿不到就是空串：没有拆书经验**不是故障**。
        # [EN] ★★ **Matched same-genre writing methods from the book-breakdown library** (2026-10-07, round
        # [EN] six) ——
        # [EN] Stirring things up is the moment the director "decides where to take the story", which is what
        # [EN] the user calls "optimizing the story".
        # [EN] What is given here is the **full version** (pacing/character-building/writing style/**what not
        # [EN] to copy**) ——
        # [EN] what stirring things up needs is exactly "should this step compress or explode", and that is
        # [EN] precisely the "pacing" item.
        # [EN] ⚠ Only retrievable when a genre card hits (`store.match` does not force it in),
        # [EN] and if unavailable it is an empty string: having no book-breakdown experience **is not a
        # [EN] fault**.
        try:
            from booklab import store as _BL
            card = getattr(self.world, 'genre_card', None) or {}
            _lesson = _BL.for_writers(card)
            if _lesson:
                craft_block = (craft_block + '\n' + _lesson) if craft_block else _lesson
        except Exception:                                        # noqa: BLE001
            pass
        craft_line = f"\n{craft_block}\n" if craft_block else ""

        # ★ 三个"率"旋钮（`REVEAL_PACING` / `COINCIDENCE_RATE` / `NEW_FACE_RATE`）：
        #   既要**告诉模型**当前的倾向，也要在它给出事件之后**按概率放行**
        #   （见 `_rate_gate`）—— 只写在提示词里等于没接线。
        # [EN] ★ Three "rate" knobs (`REVEAL_PACING` / `COINCIDENCE_RATE` / `NEW_FACE_RATE`):
        # [EN] both **tell the model** the current tendency, and **let it through by probability** after it
        # [EN] produces an event
        # [EN] (see `_rate_gate`) —— writing it only in the prompt equals not being wired up.
        rate_line = (
            "\n本作当前偏好："
            f"巧合型事件出现频率约 {CFG.f('COINCIDENCE_RATE'):.2f}"
            f"（0=这个世界没有巧合，别用）；"
            f"新面孔出现频率约 {CFG.f('NEW_FACE_RATE'):.2f}"
            "（低频时**只用在场的人**，别凭空造人）；"
            f"揭示型（秘密泄露/伏笔激活）频率约 {CFG.f('REVEAL_PACING'):.2f}")

        # 最近发生过什么 —— 给模型看，也用来做**重复度**判据
        # [EN] What happened recently —— shown to the model, and also used as the **repetition** criterion
        recent = [str(e.get("content") or "").strip()
                  for e in self.db.recent_events(12)]
        recent = [x for x in recent if x]
        recent_block = ("\n最近已经发生过的事（**从新到旧**，不要重复）：\n"
                        + "\n".join(f"- {x}" for x in recent)) if recent else ""
        # ★★★ **事件必须接着上一件**（2026-10-19 第五轮）
        #
        # 用户原话：「不是一系列有关联的事件连续下来，还是不同的事情胡乱跳」。
        # 改之前这里只有一句"不要重复"，于是模型的正解是**换一件不一样的事**——
        # 结果一晚上四个事件是「送酒 → 送茶 → 送水 → 送酒壶」：
        # 每一件都"没重复"，连起来却在**同一格上原地转**（《雪国》第 3 轮实测）。
        # ⇒ 必须成对：**不许重复** ＋ **不许另开一件无关的**，这一件要是上一件的
        #   后果 / 下一步 / 代价。这才叫"一系列有关联的事件"。
        # [EN] ★★★ **An event must continue the previous one** (2026-10-19, round five).
        # [EN] Before, the only instruction was "do not repeat", so the model's optimal move was
        # [EN] **to change to something different** -- and one night produced
        # [EN] "wine -> tea -> water -> wine flask": each one non-repeating, yet all circling the
        # [EN] same spot (Snow Country round 3). So it must be paired: no repeats **and** no
        # [EN] unrelated new thread; the new one is the previous one's consequence / next step.
        if recent:
            recent_block += (
                "\n⚠ **但也不许另开一件无关的事**：这一件必须是上面**第一条**"
                "（最近那一件）的**后果 / 下一步 / 代价** —— 有人为它付了什么、"
                "它把谁逼到了哪一步。\n"
                "   · 最近那件若只是「有人送了什么来」，这一件就该是"
                "「那东西被接下 / 被拒绝 / 被发现不对 / 送的人多说了半句」，"
                "**不是**「又有人送了一样东西来」（同一件事换个宾语重来一遍）；\n"
                "   · 只有当最近那件**真的了结了**（人走了、东西收下了、话说开了），"
                "才可以开新事 —— 而且新事也要从**它留下的后果**长出来，不许凭空另起一头。\n")
        hint_block = f"\n（{reason_hint}）" if reason_hint else ""
        # 用户刚挑的走向也要让导演看见 —— 选择必须真的落地，不能只写进日志。
        # （`sim/loop` 在介入出口与 `_maybe_branch` 里写 `director.branch_hint`。）
        # [EN] The direction the user just picked must also be visible to the director —— the choice must
        # [EN] actually land, not just be written to the log.
        # [EN] (in `sim/loop`, both the intervention exits and `_maybe_branch` write `director.branch_hint`.)
        #
        # ★★★ 2026-10-26：**读一次就清**（`clear_branch_hint`）。
        #   这里原来是"读了就永远留着" —— 全项目没有任何一处清空它，
        #   于是作者选过一次走向之后，这条「请顺着 X 挑事」会拼进**此后每一个**
        #   挑事提示词，故事被永久锁死在那一句上。用户说的
        #   「自己定一个，过一会又回到这个循环」里，有一半是这个原因。
        #   ⚠ 在**这里**清（而不是在 `sim/loop` 的调用点）：一次挑事可能走
        #     重生成分支（`_regen_event`），那条分支也会读 hint —— 调用方清早了会丢。
        # [EN] ★★★ 2026-10-26: **read once, then clear** (`clear_branch_hint`). It used to be
        # [EN] "read and kept forever" -- nothing in the project ever cleared it, so after one choice
        # [EN] the line "follow X" was spliced into **every** subsequent stirring prompt, locking the
        # [EN] story onto that one sentence. That is half of the user's "I set my own direction and it
        # [EN] comes back". ⚠ Clear **here**, not at the caller: one stirring may go through the
        # [EN] regeneration branch (`_regen_event`), which also reads the hint.
        if getattr(self, "branch_hint", ""):
            hint_block += f"\n（作者已经选了走向：{self.branch_hint}，请顺着它挑事）"
            self.branch_hint = ""

        _cot = _cot_block()
        _cot_seg = f'\n{_cot}\n' if _cot else ''
        prompt = f"""你是一位故事导演，正在观察一个小说世界的运行。

{world_line}
{craft_line}
当前节点：{node_name}（{node_summary}）
在场人物：{on_stage}{off_line}
张力：{self.world.tension:.1f}
场景：{self.world.scene}
时间：{self.world.clock_display()}{rate_line}{recent_block}{hint_block}
{_cot_seg}{_pressure_seg}
**这一次发生的是「{_ev_type}」这一类事**（不是让你挑一类 —— 类型已经由局面定下了）。
把 JSON 里的 `类型` 照抄成 "{_ev_type}"，其余由你写：
{{{_think_sch()}"是否介入": true, "类型": "{_ev_type}",
  "事件": "具体是什么事（一句话，要贴得住上面那个理由）", "涉及人物": ["..."],
  "离场人物": ["..."], "进场人物": ["..."],
  "强度": 0.0~1.0, "理由": "一句话"}}
⚠ `事件` 里**一个引号都不要出现**：事件是**发生的事**，不是**某人说的一句话**。
  真要有人开口，写"有人把秘密说了出去""他喊了一声"这种**事实**，
  人物的原话由他自己在那一拍里说。

⚠ `离场人物` / `进场人物`：这件事让**在场的谁走了**、让**不在场的谁回来了**。
  只填**名字**，从上面那份在场/不在场名单里挑；**没有就留空数组**，
  拿不准也留空 —— 空数组完全合法，填错比空更糟（会把一个还在屋里的人
  标成退场，后面他的戏就接不上了）。"""

        messages = [{"role": "user", "content": prompt}]
        try:
            raw = await llm.chat("daily", messages, purpose="director_event", json_mode=True)
        except Exception:
            return None
        result = extract_json_lenient(raw, {})
        if not result or not result.get("是否介入"):
            return None
        _note_cot(result, what='挑事')

        event = DirectorEvent(
            # ★★★ 2026-10-19：**类型由压力定，不采信模型返回的那个**。
            #   为什么必须覆盖而不是"提示它照抄"：提示是软的 —— 而"让模型挑类型"
            #   正是这件事从"推演"退化成"写作"的那一步（它会挑最好看/最安全的那类，
            #   实测两次跑出来事件骨架 62.5% 相同）。`verify_world_law` 有一条
            #   专门判"模型返回别的类型时，最终类型仍是压力定的那一类"。
            # [EN] ★★★ 2026-10-19: **the type comes from pressure; the model's answer is
            # [EN] overridden**. Why override rather than "tell it to copy": prompts are soft, and
            # [EN] "letting the model pick the type" is exactly where simulation degrades into
            # [EN] writing (it picks the safest/most presentable kind; measured 62.5% skeleton
            # [EN] overlap across two runs). A check judges "a different answer still yields the
            # [EN] pressure-decided type".
            event_type=_ev_type,
            description=result.get("事件", "无"),
            involved=result.get("涉及人物", []),
            # ★★★ 进出场两栏（2026-10-19 第十二轮）：**只做清洗，不做校验**。
            #   校验放在 `scene_builder.observe_event`（它才知道这一幕的在场名单
            #   和事件描述）。这里若也判一遍，就是"同一件事两处实现"。
            # ⚠ 只收**字符串**：模型有时把整句话塞进这一栏（"叶子走了"），
            #   那不是名字，交给护栏按"必须在场名单里"剔掉即可。
            # [EN] ★★ The two presence fields (round twelve): **clean here, validate in
            # [EN] `scene_builder.observe_event`** (it knows this act's cast and the
            # [EN] event description) -- validating in both places is two implementations.
            # [EN] ⚠ Keep **strings only**: the model sometimes stuffs a whole sentence
            # [EN] ("Yoko left") into the field; the guards strip it as not-a-name.
            leaving=_name_list(result.get("离场人物")),
            entering=_name_list(result.get("进场人物")),
            intensity=max(0, min(1, result.get("强度", 0.5))),
            node_relevant=self.world.current_node,
            # ⚠ 理由**一律用压力给的证据**，不采信模型的"理由"：
            #   模型那句通常只是把描述复述一遍（实测："猫"），而这里要回答的是
            #   **"这件事为什么现在发生"** —— 那是压力的答案，不是模型的。
            # [EN] ⚠ The reason always comes from the **pressure evidence**, never the model's:
            # [EN] the model's line usually restates the description ("the cat"), while what is
            # [EN] needed here is **why this happens now** -- the pressure's answer.
            reason=_pr_why or (result.get("理由", "") or '').strip(),
        )

        # ── ★★★ **事件里不许有引语**（2026-10-19 第十一轮，硬闸）──
        #   `_NO_QUOTE_RETRY_HINT` 上面写着为什么。提示词里也已经写了同一句
        #   禁令（见下面 prompt 里那行）—— 而"prompt 里写了 ≠ 生效"是这个项目
        #   最高频的失效模式（实测过太多次），所以这里必须配一道**真的拦**。
        #   拦下来给模型**一次**重写机会；再犯就**放弃这次注入**
        #   （返回 None）—— 宁缺毋滥，一个没有铺垫的"她恨我"比没有事件更伤口碑。
        # [EN] ── ★★★ **No quoted speech in an event** (round eleven, hard gate) ──
        # [EN] The prompt already says "not a single quote mark" -- and "written in a prompt != in
        # [EN] effect" is this project's most frequent failure mode, so a real gate is mandatory here.
        # [EN] Give the model **one** retry; if it offends again, **abandon this injection** (return
        # [EN] None). Better none than a setup-free "she hates me".
        if has_quoted_speech(event.description):
            _LOG.info("事件里带了引语（%s），让导演重写一次", event.description[:40])
            try:
                raw2 = await llm.chat(
                    "daily",
                    messages + [{"role": "user", "content": _NO_QUOTE_RETRY_HINT}],
                    purpose="director_event", json_mode=True)
            except Exception:                                    # noqa: BLE001
                raw2 = ""
            r2 = extract_json_lenient(raw2, {}) if raw2 else {}
            desc2 = str((r2 or {}).get("事件") or "").strip()
            if not desc2 or has_quoted_speech(desc2):
                _LOG.info("重写后仍带引语（%s），本轮不注入（宁缺毋滥）", desc2[:40])
                return None
            event.description = desc2
            _LOG.info("事件已重写为无引语版：%s", desc2[:50])

        # ── 三个"率"旋钮的**放行闸**（`REVEAL_PACING` / `COINCIDENCE_RATE` /
        # [EN] ── The **release gate** for the three "rate" knobs (`REVEAL_PACING` / `COINCIDENCE_RATE` /
        #    `NEW_FACE_RATE`）──
        # ⚠ 只把这些率写进提示词是**没接线**：模型答什么还是什么，旋钮等于装饰。
        #   这里按概率真的拦一道 —— 拦下来的就是"宁缺毋滥"（导演本来就不该硬凑）。
        # [EN] ⚠ Writing these rates only into the prompt is **not wired up**: whatever the model answers still
        # [EN] goes through, and the knobs are mere decoration.
        # [EN] Here we actually block by probability —— what gets blocked is "better to have less than to have
        # [EN] junk" (the director should not force it anyway).
        event = self._rate_gate(event)
        if event is None:
            return None

        # ── 重复度检测（`REPETITION_SIMILARITY`）──
        # 判据是"和最近任何一件事的相似度都低于阈值"。相似度用二元组 Jaccard
        # （`store.db.similarity`）—— 因为模型换个说法讲同一件事时，
        # 字面有重合、语义完全相同，光比字符串相等是抓不住的。
        # [EN] ── Repetition detection (`REPETITION_SIMILARITY`) ──
        # [EN] The criterion is "similarity to any recent event is below the threshold". Similarity uses bigram
        # [EN] Jaccard
        # [EN] (`store.db.similarity`) —— because when the model rephrases the same thing,
        # [EN] there is literal overlap while the meaning is identical, and comparing string equality alone
        # [EN] cannot catch it.
        thr = CFG.f("REPETITION_SIMILARITY")
        if recent and thr < 1.0:
            top = max(similarity(event.description, x) for x in recent)
            if top >= thr:
                _LOG.info("事件与最近发生过的太像（相似度 %.2f ≥ %.2f），重生成一次",
                          top, thr)
                event = await self._regen_event(messages, event, recent, thr)
                if event is None:
                    return None

        # 更新张力（系数来自曲线）
        # [EN] Update tension (coefficient comes from the curve)
        self.tension_rise(event.intensity)
        # 记录事件
        # [EN] Record event
        self.db.add_event(f"E{self.world.event_count:03d}", event.description,
                          event.event_type, self.world.game_day, event.involved,
                          self.world.current_node)
        self.world.event_count += 1
        self._mark_event()
        _LOG.info("导演注入事件 [%s]: %s", event.event_type, event.description[:50])
        return event

    @MODELS.agent('director')
    async def _regen_event(self, messages: list[dict], event: DirectorEvent,
                           recent: list[str], thr: float) -> DirectorEvent | None:
        """事件与最近发生过的太像 → 让模型换个角度重来一次。

        再像就**放弃这次注入**（返回 None）—— 宁缺毋滥：
        把"换个说法的同一件事"再演一遍，比什么都不发生更伤口碑
        （读者一眼就看出在原地打转）。
        
                English:
        Event too similar to the most recent one → have the model retry from a different angle.
                If still similar, **abandon this injection** (return None) — better none than a bad one:
                replaying "the same thing said differently" hurts reputation more than nothing happening
                (readers spot the going-in-circles at a glance).
        """
        try:
            raw2 = await llm.chat(
                "daily", messages + [{"role": "user", "content": _REPEAT_RETRY_HINT}],
                purpose="director_event", json_mode=True)
        except Exception:                                    # noqa: BLE001
            return event          # 重生成失败就用手上这个（不为难用户）
            # [EN] If regeneration fails, use the one on hand (do not make it hard on the user)
        r2 = extract_json_lenient(raw2, {})
        if not isinstance(r2, dict):
            return event
        desc2 = str(r2.get("事件") or "").strip()
        if not desc2:
            return event
        if recent and max(similarity(desc2, x) for x in recent) >= thr:
            _LOG.info("重生成后仍然重复，本轮不注入（宁缺毋滥）")
            return None
        event.description = desc2
        # ★★★ 2026-10-19：**重生成只改"写成什么"，绝不改"是哪一类"**。
        #
        #   这里原来有一行 `event.event_type = str(r2.get("类型") or event.event_type)` ——
        #   而压力已经在 `_inject_event` 里把类型定死了。留着这一行，等于
        #   **在重生成这条支路上又把选择权交回给模型**：只要第一次的描述撞了重复，
        #   类型就会被模型改回它自己喜欢的那类（通常是"巧合/外部刺激"这类最安全的）。
        #   这是"同一件事两处实现"的典型 —— 主路改对了，支路忘了改，判据要覆盖
        #   两条路才抓得到（`verify_world_law` 的 D 组）。
        #   ⚠ 理由同理：可解释性来自**压力**（"甲藏的事已经压到 1.00"），
        #     不是来自模型的自我复述（"猫"）。所以理由也不采信模型的。
        # [EN] ★★★ 2026-10-19: **regeneration changes the wording, never the category.** The line
        # [EN] `event.event_type = str(r2.get("类型") or ...)` used to hand the choice back to the
        # [EN] model on the regeneration branch -- so as soon as the first description looked like a
        # [EN] repeat, the category reverted to whatever the model prefers (usually the safest kind).
        # [EN] Textbook "one thing implemented twice": fixed on the main path, missed on the branch.
        # [EN] ⚠ Same for the reason: explainability comes from **pressure**, not the model's retelling.
        if isinstance(r2.get("涉及人物"), list) and r2["涉及人物"]:
            event.involved = r2["涉及人物"]
        event.intensity = max(0, min(1, r2.get("强度", event.intensity)))
        return event

    async def _inject_rescue_event(self) -> DirectorEvent:
        """停滞时的自救事件：**让模型按这部小说挑一件事**（拿不到才用写死那句）。

        ★ 2026-10-07 修（审计发现）：这里以前是**写死的一句话** ——
          「（导演介入）有人敲门，打断了僵局。」

          后果：所有走到停滞的戏，破局方式都是"有人敲门"。同一个茶楼里
          第三次出现这句话时，读者已经知道接下来要发生什么了 ——
          而**破局这件事恰恰最不能套路**（它承担的是"把故事推回正轨"）。

          "为什么当初写死"也说得通：这是**兜底路径**（正常挑事走
          `_inject_event`，那条是 LLM 生成的），兜底里再调一次模型像是有风险。
          但这条路径**不是罕见的**：停滞检测每 `STALL_WINDOW_MINUTES` 就触发一次，
          真机上它比 `_inject_event` 出镜还多。所以它值得一次调用。

          两档都在：
            · 走 `_inject_event` 同一条路（世界前缀 + 工艺库 + 反复度检查）；
            · 拿不到就回退到那句写死的（**不在兜底里再失败一次**）。
        
                English:
        Self-rescue event on stall: **let the model pick an event for this novel** (fall back to the
        hardcoded line only if that fails).
                ★ 2026-10-07 fix (audit finding): this used to be a **hardcoded single sentence** —
                  "(Director intervention) Someone knocks, interrupting the deadlock."
                  Consequence: every scene that reached a stall broke the deadlock with "someone knocks". By the third time
                  this line appeared in the same teahouse, readers already knew what would happen next —
                  and **breaking a deadlock is exactly the thing that must not be formulaic** (it carries "push the story back on track").
                  "Why it was hardcoded back then" also makes sense: this is the **fallback path** (normal event-picking goes through
                  `_inject_event`, which is LLM-generated), and calling the model again inside the fallback seemed risky.
                  But this path is **not rare**: stall detection fires every `STALL_WINDOW_MINUTES`,
                  and on real machines it appears more often than `_inject_event`. So it deserves a call.
                  Both tiers present:
                    · Go the same route as `_inject_event` (world prefix + craft library + repetition check);
                    · If that fails, fall back to the hardcoded line (**do not fail a second time inside the fallback**).
        """
        self._mark_event()
        # 执行过了就把"已确认"清掉：下次再停滞还要重新问一次（不能永久免检）
        # [EN] Once executed, clear "confirmed": the next stall must ask again (no permanent exemption)
        self._intervention_confirmed = False
        self._pending_intervention = None
        self._pending_branches = []
        ev = await self._inject_event(
            reason_hint="剧情停滞太久，需要一件事把局面推回正轨"
                         "（**必须是这部小说里会长出来的事**，不要写'有人敲门'这种套话）")
        if ev is not None:
            ev.event_type = '导演自救'
            ev.reason = '停滞自救'
            return ev
        _LOG.info('停滞自救没拿到模型结果，回退到通用那一句')
        return DirectorEvent(
            event_type="导演自救",
            description="（导演介入）有人敲门，打断了僵局。",
            involved=self.world.on_stage_names()[:2],
            intensity=0.6,
            node_relevant=self.world.current_node,
            reason="停滞自救（回退）",
        )

    # ── 派活（`DISPATCH_EVERY_TICKS`）────────────────────────────────
    # [EN] ── Dispatch work (`DISPATCH_EVERY_TICKS`) ────────────────────────────────
    @MODELS.agent('director')
    async def dispatch(self, people: list[str]) -> dict[str, str]:
        """每 N 拍给在场人物各派一件**此刻该推进的事**。返回 `{人名: 一句话}`。

        ★ **派「要什么」，从不派「怎么做」。** 这是设计上的一条硬线：
          派"把账房夜里的事弄清楚"可以；派"去账房翻第三本册子"就变成了**替人物
          做决定**——他就不再是人物，而是提线木偶（本项目要的恰恰不是这个）。
          提示词里那句"不要写动作步骤"就是这个意思，而验收也在判它。

        为什么需要它：`GOAL_LADDER` 的金字塔最内层（〔此刻〕）总得有个来源。
        人物的「这一站」（进度节点）和「今日计划」（自己排的）都偏中远期，
        缺的正是**这一拍到底该往哪儿使劲** —— 真机日志里 126 次决策
        全是"擦、看、账"，缺的就是这一层。

        拿不到结果时返回空 dict（**不编**）：那一层就空着，人物照旧靠自己驱动。
        
                English:
        Every N beats, assign each character present one **thing that should be advanced right now**.
        Return `{name: one sentence}`.
                ★ **Assign "what they want", never "how to do it".** This is a hard line in the design:
                  assigning "figure out what happened in the counting house at night" is fine; assigning "go to the counting house and flip through the third ledger" becomes **making the decision
                  for the character** — he stops being a character and becomes a marionette (which is precisely what this project does not want).
                  The line in the prompt "do not write action steps" means exactly this, and acceptance tests check it too.
                Why it is needed: the innermost layer of the `GOAL_LADDER` pyramid (〔right now〕) must have a source.
                A character's "this stop" (progress node) and "today's plan" (self-scheduled) both lean mid-to-long-term,
                and what's missing is exactly **where this beat should push** — in real-machine logs, all 126 decisions
                were "wipe, look, ledger", and this layer is what was missing.
                When no result is obtained, return an empty dict (**do not fabricate**): that layer stays empty, and characters keep driving themselves as before.
        """
        names = [n for n in (people or []) if n]
        if not names:
            return {}
        # 每次派活重算：这是"这一批里哪几条必须放行"，不是历史。
        # [EN] Recomputed per dispatch: "which lines of this batch must go through", not history.
        self._forced_names = set()
        info = self.world.current_node_info() or {}
        recent = [str(e.get("content") or "").strip()
                  for e in self.db.recent_events(8)]
        recent = [x for x in recent if x]
        # ★★★ **上一次派给他的活**（2026-10-19 第五轮）
        #
        #   用户原话：「一个人从头到尾说的话之间没有任何关系，不是一系列有关联的事件
        #   连续下来，还是不同的事情胡乱跳」。
        #   查到这里才发现是**结构性的**：`dispatch` 每 8 拍派一次，
        #   而提示词里**没有一个字**提到"上次派了什么"。于是每次都是从零想，
        #   实测同一晚三次派给驹子的活：
        #     第 8 拍「要让此刻对岛村的陪伴显得自然妥帖」
        #     第 16 拍「要护住房内未散的谈笑余温」
        #     第 24 拍「要达成对那声姐与粗陶壶的安然受用」
        #   三件毫无关系 —— 人物当然每 8 拍重新开始，**话当然连不起来**。
        #   提示词里管人物"要有自己的线"，而给他定"此刻要办什么"的这一层
        #   每 8 拍把线剪断一次，上游剪、下游怎么接都没用。
        # [EN] ★★★ **What was assigned to him last time** (round five). The user's words: "the
        # [EN] things one person says from beginning to end have nothing to do with each other".
        # [EN] It turned out to be **structural**: `dispatch` runs every 8 beats and the prompt
        # [EN] never mentions "what was assigned last time", so it starts from scratch each time.
        # [EN] Measured, three assignments to the same character in one night: "make the company
        # [EN] feel natural" / "guard the lingering warmth of the talk" / "settle the unease of
        # [EN] standing outside" -- unrelated. Characters restart every 8 beats, so their words
        # [EN] cannot connect. The prompt tells characters to keep a thread while this layer cuts
        # [EN] it every 8 beats; fixing downstream is useless.
        _prev = {n: str((getattr(self, '_last_dispatch', {}) or {}).get(n) or '').strip()
                 for n in names}
        _prev = {n: v for n, v in _prev.items() if v}
        # ★★★ **每个人是谁**（2026-10-19 第七轮，治"配角像 NPC"）
        #
        #   用户原话：「叶子几乎只在做两件事：送东西和提醒…更像一个推动场景转换的"NPC"」。
        #   查日志发现根因在这里：派活时导演**只拿到一个名字**（`names`），
        #   不知道她是谁、想要什么、是什么性子 ⇒ 只能派"送东西/退下/歇着"这种
        #   功能动作。实测三次派给叶子的活：
        #     「把酒壶递给驹子退下」/「回自己房间歇着」/「送酒后回自己房间歇着」
        #   —— 她不是被写成了 NPC，是**导演根本不知道她是个什么人**。
        #   ⇒ 把人设（身份/性子/她自己想要什么）一并递进去。
        # [EN] ★★★ **Who each person is** (round seven, fixing "the supporting role reads as an
        # [EN] NPC"). The user: "Yoko only does two things: bring things and remind people". The log
        # [EN] shows why: dispatch receives **only a name**, not who she is or what she wants, so it
        # [EN] can only assign "hand it over / step out / go rest". Measured, three assignments to
        # [EN] Yoko: "hand the flask to Jouji and withdraw" / "go back to your room and rest" /
        # [EN] "after delivering the wine, go back and rest". She was not written as an NPC -- the
        # [EN] director simply had no idea who she was. So pass the persona in.
        _who_lines: list[str] = []
        for _n in names:
            try:
                _ps = (getattr(self.world, 'people', {}) or {}).get(_n)
            except Exception:                                    # noqa: BLE001
                _ps = None
            if _ps is None:
                continue
            _bits = []
            _id = str(getattr(_ps, 'identity', '') or '').strip()
            _pe = str(getattr(_ps, 'personality', '') or '').strip()
            _go = str(getattr(_ps, 'goal', '') or '').strip()
            if _id:
                _bits.append(_id)
            if _pe:
                _bits.append(f'性子{_pe}')
            if _go:
                _bits.append(f'自己想要{_go}')
            if _bits:
                _who_lines.append(f'- {_n}：' + '；'.join(_bits))
        _who_block = ('\n**他们各是谁**（派活要贴着他的性子与想要的，'
                      '不要只按"送东西/传话/退下"派）：\n' + '\n'.join(_who_lines) + '\n'
                      ) if _who_lines else ''
        # ★★★ **门口等着的人**（2026-10-21，真跑判决逼出来的）
        #
        #   实测 mwl_v5：一晚来了 6 个群演，**正文出现 0 次**。打更人进门那一拍，
        #   派出去的三条活是「回屋歇下不露异样」「吩咐给柳氏续茶」「低念一句」——
        #   **没有一条与他有关**。于是门口那位站了几拍、等不到人、走掉。
        #   用户说的"突然出来一个，没有任何作用就又退场了"，根因就在这一层：
        #   **没人被要求去理他**。
        #
        #   ⇒ 派活时把这张单子摊出来，并要求"至少有一条是与他有关的"；
        #     解析层还有一道硬兜底（见下面的 `_extras_left`），因为提示词不总被遵守。
        # [EN] ★★★ **Who is waiting at the door** (2026-10-21, forced by a real-run verdict).
        # [EN] Measured in mwl_v5: six extras came in one night and appeared **zero times** in the
        # [EN] prose. On the beat the night watchman arrived, the three assignments were "go back and
        # [EN] rest without showing anything", "tell him to pour tea for Lady Liu", "murmur a line" --
        # [EN] **none about him**. So he stood a few beats, got no response, and left. That is exactly
        # [EN] the user's "someone suddenly appears and leaves with no function", and its root cause
        # [EN] is this layer: **nobody was asked to deal with him**.
        # [EN] => Lay the list out at dispatch time and require "at least one assignment about him";
        # [EN] the parser also has a hard fallback (see `_extras_left` below), because prompts are
        # [EN] not always obeyed.
        _extras_waiting: list[dict] = []
        _extras_block = ''
        try:
            from world import crowd as _crowd
            _extras_waiting = _crowd.waiting(self.world)
            if _extras_waiting:
                _extras_block = (
                    '\n**门口此刻等着的人**（他们是"为某件事来的"，**必须至少有一个人被派去理他**）：\n'
                    + '\n'.join(f'- {x}' for x in _crowd.waiting_line(self.world))
                    + '\n  派法：写「把门口那件事了结/问明白」，**不要**写"走过去对他说什么"。\n')
        except Exception:                                        # noqa: BLE001
            _extras_waiting = []
            _extras_block = ''
        # ★★ **谁被派了同一件事太多次**（同上）：连派三次同一类活，那个人就废了。
        # [EN] ★★ **Who got the same assignment too many times**: three in a row kills the role.
        _rep_block = ''
        try:
            _hist = getattr(self, '_dispatch_history', {}) or {}
            # ⚠ 门槛是**前两次相同**，不是三次：这一次还没派出去，历史里最多只有前两次
            #   （第一版写 `len(h) >= 3` —— 那要等到第 4 次才触发，正好错过"第三次该换了"）。
            # [EN] The trigger is **the previous two being identical**, not three: this round has
            # [EN] not been dispatched yet, so history holds at most two (the first version required
            # [EN] three, which fires on the fourth round -- exactly past when it should).
            # ⚠ **按相似度判，不按字面相等**（第七轮真跑实证）：三次派给叶子的是
            #   「送罢酒候在廊下守着那人」/「在廊下守着那人，任房内言语飘过」/
            #   「廊下守着，任那句恨语飘过耳」—— 一个字符串都不相等，而**是同一件事**。
            #   字面判据一次都没触发，她就在廊下守了整场。
            # [EN] Judge by **similarity**, not literal equality: the three assignments to Yoko
            # [EN] were "wait in the corridor after delivering the wine" / "wait in the corridor,
            # [EN] let the words drift past" / "wait in the corridor, let that resentful line drift
            # [EN] past" -- not one string equal, yet **the same thing**. A literal test never
            # [EN] fired and she stood in that corridor for the whole scene.
            # ★★★ **人名不是"同一件事"的证据**（2026-10-19 第十轮，真跑校准）
            # -----------------------------------------------------------------
            # 上一版按"共享二元组 >= 5"判，实测漏掉了 `snow_v10` 里叶子的
            # **三次「廊下守着」**：那三句只共享 4 个（`让叶` `叶子` `廊下` `守着`），
            # 其中两个还只是人名。于是她在廊下守了整场，检测一声不响。
            #
            # 把"由人名字符构成的二元组"剔掉之后，两种情况分得极干净
            # （`snow_v10` 与夹具共 10 对实测）：
            #   同一件事的换说法：**2–3**（`廊下` `守着` / `正经` …）
            #   不同的事、以及"派活了但没接着上一件"：**全是 0**
            # ⇒ 门槛取 **2**。名字是每句都有的，不构成证据。
            # [EN] ★★★ **Names are not evidence of "the same task"** (round ten, calibrated on a real
            # [EN] run). The previous rule (shared bigrams >= 5) **missed** Yoko's three consecutive
            # [EN] 「waiting in the corridor」 assignments in `snow_v10`: they shared only 4, two of
            # [EN] which were just the name. Dropping bigrams made of name characters separates the
            # [EN] two cases cleanly (10 pairs measured): the same task reworded scores **2-3**;
            # [EN] different tasks, and "assigned something that does not continue the last one",
            # [EN] all score **0**. Threshold 2. Names appear in every line and prove nothing.
            _name_chars = set(''.join(names or ())) | {'让', '请', '叫', '使'}

            def _bg(x: str) -> set[str]:
                z = ''.join(ch for ch in str(x) if '\u4e00' <= ch <= '\u9fff')
                grams = {z[i:i + 2] for i in range(len(z) - 1)}
                return {g for g in grams
                        if not (g[0] in _name_chars and g[1] in _name_chars)}

            _stale = {}
            for n, h in _hist.items():
                if n not in names or len(h) < 2:
                    continue
                # ⚠ 判"共享二元组**个数**"，不判相似率，也不判字面相等：
                #   实测同一个人的两次派活 ——
                #     同一件事（换个说法）：共享 **7–8** 个（廊下/守着/着那…）
                #     不同的事（只是同样那两个人）：共享 **3** 个（全是人名）
                #   相似率在这种"同义换说法"上只有 0.33–0.40，判不出来；
                #   而共享个数把两者分得很开，门槛取 5 就够。
                # [EN] Count **shared bigrams**, not a ratio and not equality: measured on one
                # [EN] person's consecutive assignments -- the same thing reworded shares **7-8**
                # [EN] bigrams, a different thing involving the same two people shares **3** (all
                # [EN] names). The ratio sits at 0.33-0.40 for rewordings and cannot separate them;
                # [EN] the count separates them cleanly, and a threshold of 5 is enough.
                if len(_bg(h[-1]) & _bg(h[-2])) >= 2:
                    _stale[n] = h[-2:]
            if _stale:
                _rep_block = ('\n⚠ **这几个人已经连着 2 次被派了同一件事（换个说法也还是同一件），这一轮是第 3 次**：\n'
                              + '\n'.join(f'- {n}：{h[0]}' for n, h in _stale.items())
                              + '\n  · 这一轮**必须换**，而且不许换个说法重说一遍；\n'
                              '  · 换的时候要贴着他**自己想要的**（见上面"他们各是谁"），'
                              '不是接着当跑腿的；\n'
                              '  · 如果那件事本来就该结束了，就派**它办完之后他想要什么** ——'
                              '一个人送完东西总还有点自己的打算。\n')
        except Exception:                                        # noqa: BLE001
            _rep_block = ''
        _prev_block = ''
        if _prev:
            _prev_block = ("\n**上一次你派给他们的活**（8 拍之前）：\n"
                           + "\n".join(f"- {n}：{v}" for n, v in _prev.items())
                           + "\n⚠ **新派的这一件，必须是上面那件的下一步** —— "
                             "他往那件事上又走近了一步（或者撞了墙、改了主意）。\n"
                             "  · 只有当他**真的办成了 / 真的放下了**，才可以换一件新的，"
                             "而且新的一件要从那件的**结果**长出来（他没办成，留下了什么麻烦）；\n"
                             "  · ❌ 不许无缘无故换一件不相干的事 —— 那读起来就是"
                             "「这个人一会儿想这个、一会儿想那个」。\n"
                             "  · 如果同一件事已经推了 3 次还没结果，**不要**再换一个说法重复派，"
                             "改派**能把它逼出结果的那一步**（摊牌、让步、失手）。\n")
        _cot = _cot_block()
        prompt = (
            "你是一位故事导演。请给在场人物各派一件**此刻该推进的事**。\n\n"
            f"当前节点：{info.get('名称', '')}（判据：{info.get('完成判据', '')}）\n"
            f"在场人物：{'、'.join(names)}\n"
            + ("最近发生的事：\n" + "\n".join(f"- {x}" for x in recent) + "\n"
               if recent else "")
            + _who_block
            + _rep_block
            + _prev_block
            + _extras_block
            + (f'\n{_cot}\n' if _cot else "")
            + "\n要求：\n"
            "- **只写「要达成什么」，绝不写「怎么做」** —— 不要说去哪个房间、"
            "翻哪本书、说哪句话，那是人物自己的事。\n"
            # ★★★ 2026-10-19 第五轮：**必须是"一件事"，不是"一种气氛"**。
            #   实测派出来的三条全是描写（"要达成对门外静立的毫不刻意的好奇"），
            #   那种话**人物演不出来**：它没法"办"，只能每拍换个姿势。
            #   而人物一旦没有可办的事，他的话就只能跟着别人的话跑 —— 这才是
            #   "不同的事情胡乱跳"的最后一块拼图。
            # [EN] ★★★ Round five: **it must be "a thing", not "a mood"**. All three measured
            # [EN] assignments were descriptions ("achieve an unforced curiosity about the quiet
            # [EN] outside the door"), which a character **cannot act on**: there is nothing to do,
            # [EN] so every beat is a new pose. Without something to do, his lines can only follow
            # [EN] other people's -- the last piece of "unrelated things jumping around".
            "- ★★★ **必须是「他要办成的一件事」**，不是场景气氛、不是心理状态。\n"
            "  写法是「让某人做某事」「让他自己弄明白某事」「把某件事办成/办砸」。\n"
            "  ❌ 反例（实测派出来过，人物演不出来）：「要达成对门外静立的毫不刻意的好奇」\n"
            "     「要让此刻的陪伴显得自然妥帖」「要护住房内未散的谈笑余温」\n"
            "  ✅ 正例：「让他说出能留几天」「把酒给他满上，等他先开口」"
            "「问出她今晚为什么来」\n"
            "- 一人一句，不超过 25 字。\n"
            # ★★★ 2026-10-14（用户：「第一天就想把谜底解开 这个节奏是不对的」）——
            #   刻意**去掉了**原来那句「要具体到能推动当前节点」：它和判据叠在一起，
            #   等于叫每个人都直奔判据里的关键词，一拍就把整条主线冲到终点。
            #   改成"与这一天的日子相称的一小步"，并明文禁止提前揭底。
            # [EN] ★★★ 2026-10-14 (user: "it wants to crack the mystery on day one; that pacing is
            # [EN] wrong") -- deliberately **dropped** the old "be specific enough to push the current
            # [EN] node" line: stacked on top of the criterion, it told everyone to charge straight at
            # [EN] the criterion's keywords, reaching the end of the mainline within a beat or two.
            # [EN] Replaced with "a small step befitting the day", plus an explicit ban on early reveals.
            "- 这一件要**跟这一天的日子相称**：多是些身边小事（看店、收拾、待客、"
            "出门买办），**不要**让谁一天之内就把大疑团解开。\n"
            "- **不许**派「去揭开真相 / 去问出秘密 / 去找到答案」这类活；"
            "要的是**离答案近了一步**，不是拿到答案。\n"
            "- 不要派已经做到的事，也不要给所有人派同一件。\n\n"
            '以 JSON 回答：{' + _think_sch()
            + '"派活": [{"人物": "名字", "要什么": "一句话"}]}'
        )
        rep = await ask("cheap", [{"role": "user", "content": prompt}],
                        purpose="dispatch", want=dict, json_mode=True,
                        temperature=0.7, max_tokens=800)
        for _n in rep.notes:
            _LOG.warning("派活：%s", _n)
        _note_cot(rep.value, what='派活')
        rows = (rep.value or {}).get("派活") if isinstance(rep.value, dict) else None
        out: dict[str, str] = {}
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            who = str(r.get("人物") or "").strip()
            what = str(r.get("要什么") or "").strip()
            # 只认在场的人 —— 模型偶尔会派给一个不在场（甚至不存在）的名字
            # [EN] Only recognize people who are present —— the model occasionally assigns to a name that is not
            # [EN] present (or does not exist)
            if who in names and what:
                out[who] = what[:60]
        # ★★★ **硬兜底：门口那位不能没人管**（2026-10-21）。
        #
        #   为什么必须在这里做、而不能只靠提示词：MEMORY 里的实测是"写进 prompt ≠ 生效"
        #   （40%~74% 不遵守）。这一条又特别容易被绕过 —— 导演可以完全"正经地"
        #   给每个人派一件与门口无关的活（实测就是这么干的），提示词一点没被违反，
        #   而群演照样白来一趟。
        #
        #   判据（可数）：这批派活里**没有任何一条**提到等着的人的称呼或他那件事
        #   ⇒ 由**代码**补一条，派给与他最相关的在场人（`crowd.pick_handler`）。
        #   ⚠ 补的是"要什么"（`handoff_line`），不是"怎么做" —— 不越设计的那条线。
        #   ⚠ 那个人原来有活就**留在后面**，不丢（"先了结门口…；{原来的活}"）。
        # [EN] ★★★ **Hard fallback: the one at the door must not be left to nobody**
        # [EN] (2026-10-21).
        # [EN] Why it has to be here and not just in the prompt: MEMORY's measurement is
        # [EN] "written in the prompt != obeyed" (40%-74% non-compliance). This one is especially
        # [EN] easy to bypass -- the director can give everyone a perfectly legitimate assignment
        # [EN] unrelated to the door (that is exactly what it did), violating nothing in the prompt,
        # [EN] while the extra still wastes a visit.
        # [EN] Criterion (countable): if **no** assignment mentions the waiting person's appellation
        # [EN] or his matter => **code** adds one, assigned to the most related character present
        # [EN] (`crowd.pick_handler`).
        # [EN] ⚠ It adds "what is wanted" (`handoff_line`), never "how" -- staying on the right side
        # [EN] of that design line.
        # [EN] ⚠ If that person already has work, it is **kept after** it, not dropped
        # [EN] ("settle the one at the door first; {previous work}").
        if _extras_waiting:
            from world import crowd as _crowd
            for _e in _crowd.unhandled(self.world, out):
                _to = _crowd.pick_handler(self.world, _e, names)
                if not _to:
                    break
                _new = _crowd.handoff_line(_e)
                _old = str(out.get(_to) or '').strip()
                out[_to] = (f"{_new}；{_old}" if _old else _new)[:60]
                # ★ 记下"这条必须放行"：`sim/loop._apply_missions` 有一道
                #   "上一件还在办就不换"的拦截，会把这一条悄悄丢掉 —— 而它正是
                #   唯一能救门口那位的一条。同一次派活里，兜底优先于防漂移。
                # [EN] ★ Mark "this one must go through": `sim/loop._apply_missions` has a
                # [EN] "don't switch while the previous one is still running" guard that would
                # [EN] silently drop this line -- the only one that can save the person at the
                # [EN] door. Within one dispatch, the fallback outranks drift prevention.
                self._forced_names.add(_to)
                _LOG.info('派活兜底：门口「%s」没人管 → 派给 %s（%s）',
                          str(_e.get('称呼') or ''), _to, _new)
                # 只兜一位：多了就成了"全体去应门"，把这一拍变成接客流水线。
                # [EN] Only one: more would turn this beat into a reception conveyor.
                break
        # ★ 记下来，下一轮派活时作为"上一次派的"递回去（见上面那段 `_prev_block`）。
        #   ⚠ 只记**这一轮真的派出去**的（模型给的名字不在场时会被丢掉，
        #     那种不该算"派过"）。
        # [EN] Remember it and hand it back as "last time's assignment" next round.
        # [EN] ⚠ Only what actually went out (names not on stage are dropped above).
        if out:
            self._last_dispatch = dict(out)
            # ★ 连着派同一件事的检测要用**历史**，不能只看上一次（见上面 `_rep_block`）。
            # [EN] Detecting "assigned the same thing three times" needs **history**, not just the
            # [EN] previous round (see `_rep_block`).
            hist = dict(getattr(self, '_dispatch_history', {}) or {})
            for _n, _v in out.items():
                hist[_n] = (list(hist.get(_n, [])) + [_v])[-6:]
            self._dispatch_history = hist
        return out

    # ── 进度评估 ──────────────────────────────────────────────────────
    # [EN] ── Progress assessment ──────────────────────────────────────────────────────
    @MODELS.agent('progress')
    async def evaluate_progress(self, recent_events: list[dict]) -> ProgressVerdict:
        """评估当前节点是否完成。返回 `ProgressVerdict`（见它的说明）。

        ⚠ 返回值**不再是 `(bool, str)` 二元组**。那对写法把"模型没答上来"和
        "判据确实没满足"压成同一个值，任何降级都看不出来 —— 改成结果对象之后
        调用方必须显式处理 `ok=False`（`sim/loop.py` 会把连续失败讲给用户听）。
        
                English:
        Evaluate whether the current node is complete. Return `ProgressVerdict` (see its documentation).
                ⚠ The return value is **no longer a `(bool, str)` tuple**. That pairing squashed "the model didn't answer" and
                "the criterion genuinely wasn't met" into the same value, so any degradation was invisible — after switching to a result object,
                callers must explicitly handle `ok=False` (`sim/loop.py` will narrate consecutive failures to the user).
        """
        node_info = self.world.current_node_info()
        if not node_info:
            # 这个项目压根没有进度表 —— 不是"没拿到"，是**没得评**。
            # 按"判据不满足"处理（与旧行为一致），而且不该报故障。
            # [EN] This project has no progress table at all —— it is not "could not get it", it is **nothing to
            # [EN] assess**.
            # [EN] Handled as "criterion not satisfied" (consistent with old behavior), and it should not report a
            # [EN] fault.
            return ProgressVerdict(ok=True, done=False)
        events_text = "\n".join(f"- {e.get('content', '')}" for e in recent_events[-10:])
        prompt = fill(_PROGRESS_PROMPT,
                      name=node_info.get('名称', ''),
                      criteria=node_info.get('完成判据', ''),
                      events=events_text or '（暂无）')
        rep = await ask("cheap", [{"role": "user", "content": prompt}],
                        purpose="progress_eval", want=dict, json_mode=True,
                        temperature=0.2, max_tokens=_PROGRESS_TOKENS)
        for _n in rep.notes:
            _LOG.warning("进度评估：%s", _n)
        if not rep.ok or not isinstance(rep.value, dict):
            return ProgressVerdict.failed(
                rep.notes[-1] if rep.notes else "模型没有返回可用的结论")
        return ProgressVerdict(ok=True,
                               done=bool(rep.value.get("满足", False)),
                               desc=str(rep.value.get("进展描述") or ""))

    def advance_node(self) -> str | None:
        """当前节点完成，前进到下一个节点。返回新节点 ID。

        ★★ 2026-10-10 补：**推进时要把它记下来**（`状态`）。

        原来这里只改 `current_node`，`状态` 一个字都不写 —— 而 `状态` 有**四处**
        在读，于是三件看得见的后果全是错的：

          1. `结局.md` 的「没走完的进度节点」列出**每一个**节点 ——
             用户第一次真跑完那一天，那份文件里 6 个节点**一个不少地列着**，
             包括早就走完的（等于告诉作者"你什么都没推进"）；
          2. 当天落盘的「关键事件」永远是空的（`状态 == '已完成'` 挑不出来）；
          3. `RUN_MODE=story` 的自动收尾判据 `all(状态 == '已完成')` **永远为假** ——
             那条路从来没走通过。

        ⇒ 在这里把走完的那个标成 `已完成`、下一个标成 `进行中`。
          （`状态` 的取值沿用装订期的口径，见 `ingest/progress.py`：
            未开始 / 进行中 / 已完成 / 已偏离 —— 别自造第五种。）
        
                English:
        Current node complete, advance to the next node. Return the new node ID.
                ★★ 2026-10-10 addendum: **when advancing, record it** (`状态`).
                Originally only `current_node` was changed here, `状态` was not written at all -- yet `状态` is
                read in **four places**, so three visible consequences were all wrong:
                  1. `结局.md`'s "unfinished progress nodes" lists **every** node --
                     on the day the user first actually finishes, that file lists all 6 nodes, **not one missing**,
                     including ones long since finished (equivalent to telling the author "you advanced nothing");
                  2. The day's persisted "key events" is always empty (`状态 == '已完成'` selects nothing);
                  3. The auto-finalize predicate `all(状态 == '已完成')` for `RUN_MODE=story` is **always false** --
                     that path has never worked.
                  (Values of `状态` follow the binding-period convention, see `ingest/progress.py`:
        """
        current_idx = next((i for i, nd in enumerate(self.world.progress_nodes)
                           if nd.get("id") == self.world.current_node), -1)
        if current_idx < 0 or current_idx >= len(self.world.progress_nodes) - 1:
            return None  # 到达终点
            # [EN] Reached the endpoint
        done_node = self.world.progress_nodes[current_idx]
        next_node = self.world.progress_nodes[current_idx + 1]
        done_node["状态"] = "已完成"
        next_node["状态"] = "进行中"
        self.world.current_node = next_node["id"]
        _LOG.info("进度推进：%s → %s", done_node.get("名称", ""),
                  next_node.get("名称", ""))
        return next_node["id"]

    def is_at_end(self) -> bool:
        """是否到达故事终点。
                English:
        Whether the story endpoint has been reached.
        """
        if not self.world.progress_nodes:
            return False
        return self.world.current_node == self.world.progress_nodes[-1].get("id")

    # ── 待确认介入的**两个显式出口**（2026-10-11）────────────────────────
    # [EN] ── The **two explicit exits** for a pending intervention (2026-10-11) ────────────────────────
    #
    # 以前只有一个隐式出口：作者点「继续」→ `RunLoop.resume()` 把
    # `_intervention_confirmed` 置 True → 下一拍走 `_inject_rescue_event()`。
    # 那是"继续 = 同意"的老口径，而作者**没有别的选择**。
    # 2026-10-11 把待确认那条改成了提问对话框（两个选项 + 自定义输入），
    # 于是需要两个明确的落点 —— 一处说了算，别让 run loop 自己去戳
    # `_intervention_confirmed` 和 `_last_event_game_min`（那两个字段的
    # 语义只有这里清楚，写在外面迟早会漂）。
    # [EN] Previously there was only one implicit exit: the author clicks "continue" → `RunLoop.resume()`
    # [EN] sets
    # [EN] `_intervention_confirmed` to True → the next beat runs `_inject_rescue_event()`.
    # [EN] That was the old convention of "continue = agree", and the author **had no other choice**.
    # [EN] On 2026-10-11 the pending-intervention one was changed into a question dialog (two options +
    # [EN] custom input),
    # [EN] so two explicit landing points are needed —— one place has the final say, do not let the run
    # [EN] loop poke at it itself,
    # [EN] `_intervention_confirmed` and `_last_event_game_min` (the semantics of these two fields
    # [EN] are only clear here; written elsewhere they will drift sooner or later).
    def confirm_intervention(self, direction: str = "") -> None:
        """作者同意这次介入 ⇒ 下一拍照导演的方案注入（置"已确认"）。

        ★★★ 2026-10-26 修（用户报的「自己定一个，过一会又回到这个循环」）：
          这里原来**只置了一个标志**，`_last_event_game_min` / `_beats_since_event`
          一个都没动。于是：
            · `_is_stalling()` 下一拍**仍然成立**（拍数一点没减）；
            · 只因为 `_intervention_confirmed` 是 True，这一拍侥幸没再挂起；
            · 真正把计时归零的是 `_inject_rescue_event()` —— 而那一路要等模型给出事件，
              给不出就回退硬编码、**并且已经先把拍数清零了**。
          ⇒ 现在两条出口（真去做 / 说不用）**都**调 `_mark_event()`，
            语义统一成"这次介入就当它发生过了，从这里重新计时"（与
            `skip_intervention` 原有的注释一致）。
          ⚠ 少了这一步，"我点了、也选了方向，可过 50 拍又来问我" 就是必然的。

        `direction`：作者挑的那个方向（空 = 只是"同意，让导演自己来"）。
        写进 `branch_hint` 让下一次挑事读得到 —— **并且只生效一次**
        （`_inject_event` 用完后由 `clear_branch_hint()` 清掉，见那里的说明）。

                English:
        The author agrees to this intervention ⇒ inject the director's plan next beat.
        ★★★ Fixed 2026-10-26 (user: "I set my own direction, and after a while it comes back"):
        this used to set **only a flag** and touch neither `_last_event_game_min` nor
        `_beats_since_event`. So `_is_stalling()` still held next beat; only the flag kept it from
        hanging again, and the real reset happened inside `_inject_rescue_event()` -- which needs the
        model to produce an event. => Both exits now call `_mark_event()`, unified as "this
        intervention counts as having happened; restart the timer from here".
        `direction`: the direction the author picked (empty = "go ahead, director's choice").
        """
        d = " ".join(str(direction or "").split())
        if d:
            # ⚠ 长度上限与 `choose_branch_custom` 一致：这句话进提示词与事件流，太长会挤掉别的上下文。
            # [EN] Same cap as `choose_branch_custom`: this line goes into the prompt and the event
            # [EN] stream; too long and it crowds out other context.
            self.branch_hint = d[:200]
        self._intervention_confirmed = True
        self._pending_intervention = None
        self._pending_branches = []
        self._mark_event()

    def clear_branch_hint(self) -> None:
        """**用掉一次就清掉**作者选的走向。

        ★★★ 2026-10-26 修（用户第三个问题的直接元凶之一）：
          `branch_hint` 原来**只有赋值、全项目没有一处清空**
          （写点在 `sim/loop.py` 的介入出口与 `_maybe_branch`）。于是作者选过一次走向之后，
          这条提示会**永久**拼进此后每一个挑事提示词 ——
          「（作者已经选了走向：X，请顺着它挑事）」，故事被锁死在那一句上。
          作者看到的现象就是"我定了，可看起来没变化，过一会还是那个循环"。

          `sim/loop._maybe_branch` 的注释本来就写着"用掉了就清掉"，但那一行只清了
          `_branch_custom`（run loop 自己的字段），**没清导演这一份** ——
          典型的"同一件事两处实现，改了一处"。

        ⚠ 谁 "用掉了"：`_inject_event` —— 它把 hint 拼进提示词之后就该清。
          放在调用方清（`sim/loop`）不行：一次挑事可能走重生成分支，
          那个分支也会读 hint。

        English:
        **Clear the author's chosen direction once it has been used.**
        ★★★ Fixed 2026-10-26 (a direct culprit of the user's third complaint): `branch_hint` was
        **only ever assigned, never cleared anywhere in the project**. After one choice, this line
        was spliced into *every* subsequent stirring prompt forever --
        "(the author already chose: X, follow it)" -- locking the story onto that one sentence.
        `_maybe_branch`'s comment already said "clear it once used", but that line only cleared
        `_branch_custom` (the run loop's own field), **not the director's copy** -- the classic
        "same thing implemented twice, one place fixed".
        ⚠ `_inject_event` owns the clearing: it is what splices the hint into the prompt. Clearing
        in the caller is wrong because the regeneration branch reads the hint too.
        """
        self.branch_hint = ""

    def request_settle(self, beats: int) -> None:
        """**请求下一拍走结算通道**（`sim/loop` 判定"连着几拍大多数人在等"时调）。

        为什么由 `sim/loop` 判定而不是导演自己算：**它看得见每一拍的 verb**
        （`_process_actions` 手上就是全部 `Action`），而导演只拿得到世界状态，
        从世界里读不出"这一拍几个人选了 wait"。这是"数据的唯一来源"那条：
        谁手上有，谁算；不要为了对称在导演里再维护一份。

        ⚠ 不清零：连续僵局时每一拍都该结算一次，直到有人真的动了
          （`sim/loop` 那边一旦有人做事就把计数归零，不会再调进来）。
        [EN] **Ask the next beat to take the settlement channel.** Why `sim/loop` decides: it is the
        [EN] place that sees every beat's verb, while the director only sees world state and cannot
        [EN] tell how many people chose `wait`. Single source of truth: whoever holds the data
        [EN] computes it.
        """
        try:
            n = int(beats)
        except Exception:                                        # noqa: BLE001
            n = 0
        if n > 0:
            self._settle_beats = n

    def note_time_skipped(self) -> None:
        """「没事跳过时间」跳完一次之后调这个 —— **把"距上次事件"重新计时**。

        ⚠ 不重置的话，一次跳过会让故事时间一口气前进几十分钟，
          `_is_stalling()` 于是更容易成立 ⇒ **导演反而在"没事"的时候跳出来介入**，
          正好跟"跳过"的意图相反（用户要的是"没事就别来打扰"）。
          语义与 `skip_intervention()` 里那一句相同："这段时间就当过了"。
        
                English:
        Call this after "skip time when nothing's happening" completes once -- **restart the "time since
        last event" timer**.
                ⚠ Without resetting, one skip advances story time by tens of minutes in one go,
                  making `_is_stalling()` easier to satisfy ⇒ **the director instead pops up to intervene when "nothing's happening"**,
                  exactly the opposite of the "skip" intent (the user wants "when nothing's happening, don't bother me").
                  Semantics same as the line in `skip_intervention()`: "treat this span as having passed".
        """
        self._mark_event()

    def skip_intervention(self) -> None:
        """作者说这次不用 ⇒ **跳过这一轮介入，也从现在重新计时**。

        ⚠ 光清 `_pending_intervention` 是不够的：`_is_stalling()` 看的是
          "距上次事件过了多久"，那个时刻没动过 ⇒ 下一拍**立刻**又判停滞、
          又问一遍（作者点了"不用"却每隔一拍被问一次，比不问更烦）。
          所以这里顺手把 `_last_event_game_min` 拨到当前 —— 等于
          "这次介入就当它发生过了，从这里重新开始计时"。
        
                English:
        Author says not this time ⇒ **skip this intervention round, and restart the timer from now**.
                ⚠ Just clearing `_pending_intervention` is not enough: `_is_stalling()` looks at
                  "how long since the last event", and that timestamp hasn't moved ⇒ the next shot **immediately** judges stall again
                  and asks again (the author clicked "no" yet gets asked every other shot, more annoying than not asking at all).
                  So here also bump `_last_event_game_min` to the current value -- equivalent to
                  "treat this intervention as having happened, restart the timer from here".
        """
        self._pending_intervention = None
        # ★ 2026-10-26：挂起时生成的方向候选也要清 —— 留着它，下一次挂起会拿到上一轮的方向。
        # [EN] Also clear the candidates generated while hanging; otherwise the next hang reuses them.
        self._pending_branches = []
        self._intervention_confirmed = True        # 这一轮不再问
        # [EN] No more asking this round
        self._mark_event()
        _LOG.info("作者说这次介入不用 —— 跳过，并从当前时刻重新计时")

    # ── 分支提案 ──────────────────────────────────────────────────────
    # [EN] ── Branch proposal ──────────────────────────────────────────────────────
    @MODELS.agent('director')
    async def propose_branches(self, reason: str = '',
                               options: list[str] | None = None) -> list[dict]:
        """生成 2~4 个剧情走向候选（供用户/策略挑选）。

        ★ 2026-10-06 接线：这个方法**写在那儿很久了，但从来没有任何调用点**
        （`BRANCH_PROPOSALS` 因此也是死的）。现在由 `sim/loop._maybe_branch` 在
        「节点走完 / 高潮日」调它，**并且**由 `on_tick` 在「停滞」时调（2026-10-26）。

        ★★★ `reason`（2026-10-26 新增）：**同一次提案，两种语境不能用同一段提示词**。
          · `''`（岔路口）：一站演完了，往哪走 —— 该往"下一段"看；
          · `'stall'`（停滞）：**这一幕卡住了**，需要的是"能破局的具体一件事"，
            不是"下一步的方向"。而且这里必须点名"不要套话" ——
            实测所有走到停滞的戏，破局方式都是"有人敲门"，同一个茶楼第三次出现时
            读者已经知道接下来要发生什么了（`engine.py` 自己那条注释就是为此写的）。
          用户 2026-10-26 报的「为何导演的建议每次都是有人敲门」：根因不是模型偷懒，
          而是**挂起时压根没调这个方法** —— 对话框里显示的"方案"是三处硬编码文案。
          现在它会被真的调一次，产出直接摆在对话框里让作者挑。

        走 `ask()`（截断/空 → 上限翻倍重试 → 抢救），别再裸调 `llm.chat()` ——
        数组类输出被截断会**静默变空表**，那样"提不出候选"和"模型不给"就分不清了。

                English:
        Generate 2~4 plot direction candidates (for user/strategy selection).
                ★ 2026-10-06 wiring: this method **has sat there for a long time, but has never had any call site**
                (`BRANCH_PROPOSALS` was therefore also dead). Now `sim/loop._maybe_branch` calls it
                at "node finished / climax day", and `on_tick` calls it **on stall** (2026-10-26).
                ★★★ `reason` (added 2026-10-26): **one proposal, two contexts, two prompts**.
                  · `''` (fork): a stop finished, where next -- look at "the next stretch";
                  · `'stall'`: **this scene is stuck**; what is needed is "one concrete thing that
                    breaks the deadlock", not "the next direction", and it must call out clichés --
                    measured, every stalled scene broke with "someone knocks", and by the third time
                    in the same teahouse the reader knows what comes next (the comment in this file
                    was written for exactly that). The user's 2026-10-26 report "why is it always
                    someone knocking" was **not** model laziness: the hang path never called this
                    method at all -- the dialog showed three hardcoded strings. Now it is really
                    called once, and its output is what the author picks from.
                Go through `ask()` (truncate/empty → double the limit and retry → salvage), stop calling `llm.chat()` raw --
                an array-type output that gets truncated will **silently become an empty list**, and then "no candidates proposed" and "model gave none" are indistinguishable.
        """
        node = self.world.current_node_info() or {}
        _stall = str(reason or '') == 'stall'
        _opts = [str(x).strip() for x in (options or []) if str(x or '').strip()]
        if _opts:
            # ★★★ 2026-10-27：**作者在设定集里写好了结局选项**（节点上的 `选项`）。
            #   这时候选**必须原样就是那几个** —— 让模型自由发挥，它多半会给出
            #   三个"方向"而不是作者那三个结局，作者挑完发现"我写的没出现"。
            #   ⚠ 只让模型补"后果"（一句话），标题不许改。
            # [EN] ★★★ 2026-10-27: **the author wrote the ending options in the settings** (the node's
            # [EN] `选项`). The candidates **must be exactly those** -- left free, the model usually
            # returns three "directions" instead of the author's three endings, and the author picks
            # and finds "mine weren't there". ⚠ Only the consequence is filled in; titles are fixed.
            _ask_line = (
                "★★★ 作者已经在设定集里写好了**这一站的结局选项**，"
                "候选必须**一个不落、原样使用**这几个（标题不许改写、不许新增、"
                "不许合并）：\n"
                + '\n'.join(f'  {i}. {o}' for i, o in enumerate(_opts, 1))
                + "\n给每个选项补一句「后果」（一句话，写清选了它之后世界变成什么样）。"
                  "id 依次用 E1、E2、E3……\n")
        elif _stall:
            _ask_line = (
                f"⚠ 这场戏**卡住了**：连续 {self._beats_since_event} 拍没有任何事件发生，"
                "人物在原地打转。\n"
                "请提出几个**能把局面推出去的具体方向** —— 每个都要是"
                "「一件会真的发生的事」，而不是「接下来该往哪儿发展」这种说法。\n"
                "★ 硬要求：**不许写「有人敲门」「有人来访」这类套话** —— 破局方式最不能套路。"
                "要贴着上面那个节点与在场人物，从**他们各自正在争的东西**里长出来。\n")
        else:
            _ask_line = ""
        prompt = (
            f"故事当前节点：{node.get('名称', '')}（{node.get('概要', '')}）。\n"
            f"张力：{self.world.tension:.1f}\n"
            + (f"在场人物：{'、'.join(self.world.on_stage_names()[:8])}\n"
               if _stall else "")
            + f"最近发生的事：\n"
            + "\n".join(f"- {str(e.get('content') or '')[:60]}"
                        for e in self.db.recent_events(6))
            + "\n\n" + _ask_line
            + f"请提出 {CFG.i('BRANCH_PROPOSALS')} 个**互不相似**的"
              + ("破局方向" if _stall else "剧情走向候选") + "。"
              "\n★ 硬要求：每个字段都不超过 20 字；只输出 JSON 数组本身。\n"
              '以 JSON 数组回答：\n'
              '[{"id": "B1", "标题": "...", "后果": "一句话描述戏剧后果", '
              '"权重": 0.0~1.0}]'
        )
        rep = await ask("daily", [{"role": "user", "content": prompt}],
                        purpose="branch", want=list, json_mode=True,
                        temperature=0.8, max_tokens=1200)
        for _n in rep.notes:
            _LOG.warning("分支提案：%s", _n)
        rows = rep.value if isinstance(rep.value, list) else []
        return shape_branches(rows, _opts or None)

    @staticmethod
    def pick_branch(branches: list[dict], policy: str = None) -> dict | None:
        """没等到用户选择时按 `BRANCH_AUTO_POLICY` 自己挑一个。

        | 策略 | 行为 |
        |---|---|
        | `weighted` | 按模型给的权重掷骰（**默认** —— 让"更可能发生的那条"更容易被选中） |
        | `first` | 就选第一条（模型通常把最自然的放最前） |
        | `random` | 等概率随机 |
        | `pause` | **不挑**：返回 `None`，让主循环停下来等用户（`INTERVENTION_POLICY` 那套） |

        ⚠ `pause` 是"宁可停着也不替用户做决定" —— 它会真的把推演挂住，
        所以只在用户明确选了它时才这么干。
        
                English:
        When no user selection arrives, pick one yourself per `BRANCH_AUTO_POLICY`.
                | Strategy | Behavior |
                |---|---|
                | `weighted` | Roll dice by the model-provided weights (**default** -- make "the more likely one" more likely to be chosen) |
                | `first` | Just pick the first (the model usually puts the most natural first) |
                | `random` | Uniform random |
                | `pause` | **Pick nothing**: return `None`, let the main loop stop and wait for the user (the `INTERVENTION_POLICY` set) |
                ⚠ `pause` means "rather halt than decide for the user" -- it will really hang the simulation,
                so only do it when the user explicitly chose it.
        """
        rows = [b for b in (branches or []) if isinstance(b, dict)]
        if not rows:
            return None
        pol = (policy or CFG.s("BRANCH_AUTO_POLICY") or "weighted").strip()
        if pol == "pause":
            return None
        if pol == "first":
            return rows[0]
        if pol == "random":
            return random.choice(rows)
        total = sum(float(b.get("权重") or 0.0) for b in rows)
        if total <= 0:
            return random.choice(rows)
        r = random.random() * total
        acc = 0.0
        for b in rows:
            acc += float(b.get("权重") or 0.0)
            if r <= acc:
                return b
        return rows[-1]

    # ── 停滞检测 ──────────────────────────────────────────────────────
    # [EN] ── Stall detection ──────────────────────────────────────────────────────
    def _is_stalling(self) -> bool:
        """**连续多少拍**没有事件超过 `STALL_WINDOW_BEATS`（且故事时间也过了保护下限）。

        ★★★ 2026-10-26 改口径（用户报「过一会又回到这个循环」）：

          原来只有 `故事分钟 > STALL_WINDOW_MINUTES(180)` 一个条件。而"一拍推多少分钟"
          由 `跨度 ÷ 拍数` 决定 —— 实测 20 个「跨度 × 篇幅」组合里 **15 个是一拍 30 分钟**
          （任一跨度 + 略/带过、当日+中/略/带过），于是 **6 拍就判一次停滞**。
          一拍 = 一次人物决策，6 次决策根本不够推进一步，作者看到的就是
          "还没演什么又来问一遍，而且每次都是同样两个选项"。

          ⇒ 主判据换成**拍数**（`STALL_WINDOW_BEATS`，默认 50）：不管一拍推 2 分钟
            还是 30 分钟，"连续 50 拍没事件"才问。这样各档的频率一致。
          ⇒ `STALL_WINDOW_MINUTES` 降级为**保护下限**（默认 60），防的是反方向：
            跨天跳 90 天、一拍 30 分钟时，两拍就上千分钟，光看时间会立刻判停滞。
            两个条件**都要满足**。

        ⚠ 旧的那句 `and self._events_since_stall == 0` 已删：那个字段**只有清零、从没自增**
          （全文件搜不到 `+= 1`），恒为 0 ⇒ 那个条件是恒真的死代码。留着它会让人
          以为"还有一层保护"，其实没有。

        English:
        **How many beats** without an event, over `STALL_WINDOW_BEATS` (and story time past the floor).
        ★★★ Contract changed 2026-10-26 (user: "it comes back to the same loop after a while"):
        the old criterion was story-minutes only, and "minutes per beat" = span / beats, so with
        **15 of 20** combinations at 30 min/beat a stall was judged every **6 beats**. One beat is
        one character decision; six of them cannot advance anything, so the author saw "it asks
        again before anything happened, always with the same two options". Beats are now primary
        (default 50); `STALL_WINDOW_MINUTES` is demoted to a **floor** (default 60) that only stops
        fast clocks from judging a stall too early. Both must hold.
        ⚠ Dropped `and self._events_since_stall == 0`: that field is **only ever zeroed, never
        incremented**, so the condition was permanently true dead code -- it looked like a second
        safety layer while providing none.
        """
        beats = CFG.i("STALL_WINDOW_BEATS")
        if self._beats_since_event < max(1, beats):
            return False
        floor = CFG.i("STALL_WINDOW_MINUTES")
        if floor > 0:
            since = self._game_min() - self._last_event_game_min
            if since <= floor:
                return False
        return True


# ⚠⚠ 2026-10-27 事故复盘的警示：**把方法抽成模块级函数时，后面的方法会被吞掉**。
#   当时只把 `def shape_branches` 这行顶格，而下面 `pick_branch` / `_is_stalling`
#   仍是 4 空格缩进 ⇒ Python 认为它们还在**这个新函数的函数体里**（语法合法、
#   只是永远执行不到）⇒ 类上这两个方法直接消失，而 `sim/loop.py` 的
#   `self.director.pick_branch(...)` 要到真跑才 AttributeError。
#   ⇒ 以后再抽函数：**抽完必须确认后面的方法还在类上**（`verify_station_plan` H 组守着）。
# [EN] ⚠⚠ 2026-10-27 incident: **extracting a method to module level swallows the methods after
#   it**. Only the `def shape_branches` line was dedented, while `pick_branch` / `_is_stalling`
#   below kept their 4-space indent => Python reads them as still **inside this new function's body**
#   (legal syntax, just never reachable) => the class lost both methods outright, and
#   `self.director.pick_branch(...)` in `sim/loop.py` only blows up on a real run.
#   => Next time: **after extracting, confirm the following methods are still on the class**
#   (group H of `verify_station_plan` guards it).
def shape_branches(rows, author_options: list[str] | None = None) -> list[dict]:
    """把模型给的原始候选整理成标准形状；`author_options` 非空时**作者写的结局一个都不能少**。

    ★ 2026-10-27 抽成模块级函数：这一段的规矩（作者选项必须在、且必须在最前、
    id 统一重排）以前埋在 `propose_branches` 里 ⇒ 判据只能靠真调 LLM 才测得到。
    抽出来之后 `verify_station_plan` 直接喂几组 rows 就能验。

    ⚠ 解析层兜底的理由：**提示词只能挡住 40~74%**（本项目的实测），
    作者写的选项被模型漏掉/改写时必须由代码补回来。

        English:
    Shape the model's raw candidates; when `author_options` is non-empty, **not one of the author's
    endings may go missing**. ★ 2026-10-27 extracted to module level: these rules (author options
    must be present, must come first, ids renumbered) used to be buried in `propose_branches`, so
    assertions could only reach them by really calling an LLM. Extracted, `verify_station_plan`
    feeds a few `rows` directly. ⚠ Why a parsing-layer backstop at all: **prompts only hold 40~74%**
    (measured here), so options the model dropped or reworded must be restored by code.
    """
    _opts = [str(x).strip() for x in (author_options or []) if str(x or '').strip()]
    out: list[dict] = []
    for i, r in enumerate(rows or []):
        if not isinstance(r, dict):
            continue
        title = str(r.get("标题") or "").strip()
        if not title:
            continue
        try:
            w = float(r.get("权重", 0.5))
        except (TypeError, ValueError):
            w = 0.5
        out.append({"id": str(r.get("id") or f"B{i + 1}"),
                    "标题": title,
                    "后果": str(r.get("后果") or "").strip()[:60],
                    "权重": max(0.0, min(1.0, w))})
    if not _opts:
        return out
    _ordered: list[dict] = []
    # ⚠ 按**索引**记"哪几行已经被配走"：改写过的标题（「归籍」→「归籍2」）在
    #   下面按双向包含配给了作者那条，若这里再按"标题不等于作者原词"筛一遍，
    #   它又会以"模型多编的候选"身份**再出现一次**（界面上同一个结局出两遍）。
    # [EN] ⚠ Track by **index** which rows are taken: a reworded title ("归籍" -> "归籍2") is matched
    #   to the author's option by two-way containment below, so filtering again by "title != author's
    #   word" would let it **appear twice** (the same ending listed twice in the UI).
    _used: set[int] = set()
    for _o in _opts:
        _hit: tuple[int, dict] | None = None
        for _i, b in enumerate(out):
            if _i in _used:
                continue
            _t = str(b.get("标题") or "").strip()
            # ★★★ 双向包含（与站表 `match_station` 同一条规矩）：模型会把作者写的
            #   结局**改写**（「归籍」→「归籍（回宗族）」、「留门」→「留门不走」）。
            #   ⚠ 只认全等的话，下面那句"以作者的原词为准"是**永远执行不到的死代码**
            #   —— 全等的时候本来就没什么可改的（2026-10-27 反例法 ㉔ 实测：把那句
            #   改成 `pass` 判据照样绿）。
            # [EN] ★★★ Two-way containment (same rule as `match_station`): the model **rewords** the
            #   author's endings. ⚠ With equality only, the "use the author's wording" line below is
            #   **dead code that can never run** -- when titles are equal there is nothing to correct
            #   (measured 2026-10-27 by mutation knife ㉔: replacing it with `pass` left the criterion
            #   green).
            if _t and (_t == _o or _t in _o or _o in _t):
                _hit = (_i, b)
                break
        if _hit is not None:
            _used.add(_hit[0])
            _c = dict(_hit[1])
            _c["标题"] = _o              # 模型改写过就以作者的原词为准
            _ordered.append(_c)
        else:
            _ordered.append({"id": "", "标题": _o, "后果": "", "权重": 0.5})
    _extra = [b for _i, b in enumerate(out) if _i not in _used]
    out = _ordered + _extra
    for i, b in enumerate(out):
        b["id"] = f"E{i + 1}"
    return out

