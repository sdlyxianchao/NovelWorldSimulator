# -*- coding: utf-8 -*-
"""**开卷打磨 Agent**：一个真的会动手、记得住、还会自查的 Agent。

用户 2026-10-07：「开卷的 AI 打磨部分 **你没有生成一个 Agent**，而且每次我输入新对话，
**你发给 LLM 的内容不包含之前的历史信息**，所以大模型返回的东西是不对的。你按照正常的
**Agent Reflection 模型**结合别的模型来处理优化流程。」

## 上一版错在哪（照着改，别改回去）

| 上一版 | 现在 |
|---|---|
| 一锤子买卖：`apply_instruction` 收一句话 → 回一份完整设定 JSON | **ReAct 循环**：想 → 用工具 → 看结果 → 再想，最多 `POLISH_MAX_STEPS` 步 |
| 历史里只有「作者说了什么 / 我改了什么说明」——**没有"我实际动了什么"**，也没有体检结论 | `self.events` 是**完整事件流**：作者原话 · 工具调用 · **工具真实返回** · 我的结论 · 体检 · 自省意见。每次调用 LLM 都**整条编进 messages** |
| 没有自省 | `_reflect()`：拿"作者原话 + 全过程 + 实际改动"自查**漏改 / 改坏 / 越权**，有问题就带着意见再来一轮 |
| 拿不到东西只能"再试一次同一句话" | 拿不到时**换个手段**（换个工具、换个路径、先读一遍再说）——那是 Agent 相对单次调用最大的优势 |
| 改设定靠"回抄整份 JSON"（越长越容易被截断） | 改成 `改设定` 工具**结构化打补丁**：输出短、可校验 |

## 一轮对话的完整时序

```
author 说什么 ─────────────────────────────────────────────┐
   ↓                                                      │
_step()  →  模型回 {"想","用","参"}  →  工具真的跑  →  观察结果进事件流
   ↑                                                      │
   └── 直到 {"想","终","改了什么"} 或 {"想","问"} ─────────┘
   ↓
_reflect()  →  模型自查（漏改？改坏？越权？）→ 有问题就带回事件流再跑一轮
   ↓
PolishTurn（回话 / 改动 / 调过哪些工具 / 自省意见）
```

⚠ **本模块一次 LLM 请求都不自己发**，全走 `llm.replies.ask` —— 那是全项目唯一的
「解析 → 重试 → 抢救」入口，对话日志、预算台账、输出语言注入都挂在它上面。

English:
**Open-book polishing Agent**: an Agent that actually acts, remembers, and self-checks.
User 2026-10-07: "The **open-book AI polishing part of you did not generate an Agent**, and
every time I input a new conversation,
**the content you send to the LLM does not include prior history information**, so what the
large model returns is wrong. Follow the normal
**Agent Reflection model** combined with other models to handle the optimization flow."
## What the previous version did wrong (fix accordingly, don't revert)
| Previous version | Now |
|---|---|
| One-shot deal: `apply_instruction` takes a sentence → returns a complete settings JSON | **ReAct loop**: think → use tools → see results → think again, up to `POLISH_MAX_STEPS` steps |
| History only has "what the author said / what I said I changed" -- **no "what I actually touched"**, and no checkup conclusion | `self.events` is the **complete event stream**: author's own words · tool calls · **actual tool returns** · my conclusions · checkup · self-reflection opinions. Every LLM call **compiles the whole thing into messages** |
| No self-reflection | `_reflect()`: takes "author's own words + whole process + actual changes" to self-check for **missed changes / broken changes / overreach**, and if there are problems, carries the opinions into another round |
| When it can't get something, all it can do is "retry the same sentence" | When it can't get something, **switch to a different approach** (different tool, different path, read first then talk) -- that is the biggest advantage of an Agent over a single call |
| Changing settings relies on "copying back the whole JSON" (the longer it is, the easier to truncate) | Change to the `改设定` tool doing **structured patching**: short output, verifiable |
## Full sequence of one conversation round
```
author says something ─────────────────────────────────────────────┐
   ↓                                                      │
_step() → model replies {"想","用","参"} → tool actually runs → observation result enters event
stream
   ↑                                                      │
   ↓
_reflect() → model self-checks (missed changes? broken changes? overreach?) → if there are
problems, carries them back into the event stream for another round
   ↓
PolishTurn (reply / changes / which tools were called / self-reflection opinions)
```
⚠ **This module does not send a single LLM request itself**, everything goes through
`llm.replies.ask` -- that is the project's only
"parse → retry → salvage" entry point, and conversation logs, budget ledger, and output language
injection are all hung on it.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from i18n import t
from llm.replies import ask
from polish import codegen
from polish import intent as _intent
from polish.sandbox import Scope
from polish.tools import Toolbox

_LOG = __import__("logging").getLogger("nws.polish.agent")

# ── 预算 ────────────────────────────────────────────────────────
#: 每一步都要输出一个 JSON 对象（不长），但**思考也算 token** —— 给足，
#: 别重演 2026-10-06 那次"额度全被思考吃掉、正文一个字都没有"。
# [EN] ── Budget ────────────────────────────────────────────────────────
# [EN] : Every step must output a JSON object (not long), but **thinking also counts as tokens** --
# [EN] give enough,
# [EN] : don't repeat the 2026-10-06 incident where "the entire quota was eaten by thinking and not a
# [EN] single character of output was produced".
_STEP_TOKENS = 2400
_REFLECT_TOKENS = 2000
#: 事件流编进 messages 时，单条观察结果最多带多少字
# [EN] : When the event stream is compiled into messages, the max number of characters a single
# [EN] observation result can carry
_EVENT_CHARS = 3000
#: 整条历史最多编多少条事件（超了从**最老的**开始丢，但体检与作者原话永远留着）
# [EN] : The max number of events the whole history can compile (drop from the **oldest** when
# [EN] exceeded, but the checkup and the author's own words are always kept)
_MAX_EVENTS = 40


@dataclass
class PolishTurn:
    """一轮对话的结果。
        English:
    The result of one conversation round.
    """

    reply: str = ''                 # 给作者看的话（收尾时）
    question: str = ''              # 反问（停下等作者）
    # [EN] Words for the author (at wrap-up)
    # [EN] Counter-question (stop and wait for the author)
    changes: list[str] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)   # 调过哪些工具
    # [EN] Which tools were called
    reflections: list[str] = field(default_factory=list)
    #: 「我懂你这句的意思了」那种**面向作者**的短句（GUI 把它打进对话栏）。
    #: 2026-10-11 用户报的"我说修复4个问题 但是它不知道我什么意思" —— 光在内部
    #: 理解不够，**得让作者看见它理解对了**，否则他只会以为又没听懂。
    # [EN] Short lines **addressed to the author** like "I understood that" (the GUI prints them into
    # [EN] the chat pane). User report 2026-10-11: "I said fix the 4 problems but it doesn't understand
    # [EN] what I mean" -- understanding internally is not enough, the author **must see that it
    # [EN] understood**, otherwise he will just think it failed again.
    notes: list[str] = field(default_factory=list)
    #: 这一轮之后还剩几轮"别问我"（0 = 不生效；`-1` = 一直不问到作者改主意）
    # [EN] How many "don't ask me" rounds remain after this one (0 = inactive; `-1` = never ask until
    # [EN] the author changes their mind)
    noask_left: int = 0
    steps: int = 0
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return bool(self.reply or self.question)


@dataclass
class PolishOutcome:
    """一整场（可能好几轮）的汇总 —— 交给 GUI 决定落盘与搬进项目。
        English:
    Summary of an entire session (possibly several rounds) — handed to the GUI to decide persistence
    and moving into the project.
    """

    settings: dict[str, Any] = field(default_factory=dict)
    transcript: list[dict] = field(default_factory=list)
    generated_tools: list[str] = field(default_factory=list)
    source_writes: list[str] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)
    actions: list[dict] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════
#  提示词
# [EN] Prompt
# ══════════════════════════════════════════════════════════════
_PROTOCOL = """你每回合**只输出一个 JSON 对象**（不要代码围栏、不要 JSON 以外的任何字）：

· 用工具 → {{"想": "一句话说你打算干什么", "用": "工具名", "参": {{…}}}}
· 收尾   → {{"想": "…", "终": "给作者看的回话", "改了什么": ["…", "…"]}}
· 问作者 → {{"想": "…", "问": "你要作者回答的问题"}}

规矩：
1. **一次只想一件事**。要读就先读，读完看到东西再决定下一步，别一口气把三步都想好。
2. **改设定一律用「改设定」工具**（结构化打补丁），**不要把整份设定抄一遍回来** ——
   抄整份很容易被长度上限截断，一截断这一轮就白干了。
3. 拿不到东西时**换个手段**（换路径、先「列引用文件」、换个说法再调一次），
   别原样重试同一句话。
4. 内置工具不够用时，**用「生成工具」自己写一个**（这是被鼓励的）。
5. 你只能碰两个地方：{scope}。**引用文件夹只能追加，不能覆盖** ——
   作者的原始素材是不可再生的。
6. 做完了就**收尾**，别为了多确认一次而空转。
7. ★★ **作者的指代要看上面那条体检/你上一条回话**（2026-10-11 用户报的：
   他说「处理 1 2」「先改前两个」，而模型听不懂）。所以：
   · 他说的「1」「2」「第 2 条」「前两个」「后面那条」指的是**上面那几条
     编号建议**（体检里「建议优先打磨」那几条是 1. 2. 3. 排下来的）；
   · 先编号对上号再动手；**对不上号就在回话里问一句**是哪一条，
     不要闷头挑一条改（改错地方比不改更费作者的时间）。

★ 用作者的语言说话（见文末的【输出语言】说明）。

你可以用的工具：
{tools}"""

_REFLECT_PROMPT = """你刚刚替作者改完这份小说的设定。现在**换一双眼睛**，回头查一遍自己做的事。

作者的原话是：
---
{instruction}
---

这一轮你做了什么（全过程）：
---
{transcript}
---

改完之后，涉及的这几处现在是：
---
{changed}
---

请逐条自查（**别客气，找出问题比找不出问题有用**）：

① **有没有漏**：作者要求里还有哪一条没做到？
② **有没有改坏**：改动的措辞跟人物原本的口吻/身份对得上吗？
   （比如主角忽然出口成章）人名、伏笔编号有没有被写乱？
③ **有没有越权**：有没有动作者没让动的地方？
④ **有没有编**：有没有写进设定原文里根本没有的信息（那等于给作者埋雷）？

只输出一个 JSON 对象：
{{"有问题": true|false, "问题": ["一句话一条，最多 4 条"], "下一步": "要接着做什么（一句话）"}}

没问题就 `"有问题": false`、`"问题": []`、`"下一步": ""`。**不许为了凑数硬找问题。**"""


def _brief(v: Any, limit: int = 200) -> str:
    if v is None:
        return '（无）'
    s = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
    s = ' '.join(s.split())
    return s[:limit] + ('…' if len(s) > limit else '')


class PolishAgent:
    """打磨 Agent。一个实例 = 一场（可能多轮的）打磨会话。
        English:
    Polish Agent. One instance = one polish session (possibly multi-round).
    """

    def __init__(self, *, settings: dict[str, Any], scope: Scope,
                 name: str = '', tier: str = '', missing: tuple[str, ...] | list[str] = (),
                 allow_codegen: bool = True, max_steps: int = 6,
                 reflect: bool = True, max_reflect: int = 1,
                 on_event: Callable[[str, str], None] | None = None):
        # ⚠ **不要把 `settings` 存成自己的字段**。`Toolbox.改设定` 走的是
        #   `validate_settings()`，而那个函数**返回一个新 dict**（它是"归一化"，
        #   不是原地修改）。于是"Agent 手里的设定"和"工具箱手里的设定"会**各走各的** ——
        #   第二轮之后改的东西 Agent 看不见（判据 C13 当场抓到：自省让改回去，
        #   改是改了，`agent.settings` 还是旧的那份）。
        #   单一事实来源：`self.box.settings`，用属性转发（见下面的 `settings`）。
        # [EN] ⚠ **Do not store `settings` as your own field**. `Toolbox.改设定` goes through
        # [EN] `validate_settings()`, and that function **returns a new dict** (it is "normalization",
        # [EN] not in-place modification). So "the settings in the Agent's hands" and "the settings in the
        # [EN] toolbox's hands" will **diverge** --
        # [EN] after the second round, changes the Agent makes are invisible to itself (criterion C13 caught
        # [EN] this on the spot: self-reflection made it change back,
        # [EN] it did change it, but `agent.settings` was still the old one).
        # [EN] Single source of truth: `self.box.settings`, forwarded via a property (see `settings` below).
        self.scope = scope
        self.name = name or t('（未命名）')
        self.tier = tier
        self.missing = tuple(missing or ())
        self.max_steps = max(1, int(max_steps))
        self.reflect_on = bool(reflect)
        self.max_reflect = max(0, int(max_reflect))
        self._on_event = on_event

        self.box = Toolbox(settings=settings, scope=scope, name=self.name,
                           tier=tier, missing=self.missing,
                           allow_codegen=allow_codegen)
        # ★ **事件流**（本模块的心脏）：所有发生过的都在这儿，
        #   `_compose()` 每次都把它整条编成 messages —— 这就是用户说的"要带上历史"。
        # [EN] ★ **Event stream** (the heart of this module): everything that has happened is here,
        # [EN] `_compose()` compiles the whole thing into messages every time -- this is what the user meant by
        # [EN] "must carry history".
        self.events: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.started = time.time()
        # ── 「作者说的是哪几条」与「要不要问他」（2026-10-11 用户报的两个毛病）──
        #   `polish/intent.py` 负责**认**，这里负责**执行**：
        #     · `last_problems` 自查出来的那几条（编号 1..N，作者刚看到的就是它）；
        #     · `last_review`   体检报告里编号的那几条；
        #     · `noask_left`    "别问我"还剩几轮（`-1` = 一直不问，直到作者说"可以问我了"）。
        # [EN] -- "Which items does the author mean" and "should we ask him" (the two problems
        # [EN] reported by the user on 2026-10-11) --
        # [EN] `polish/intent.py` does the **recognising**; this does the **enforcing**:
        # [EN] · `last_problems` the items found by self-check (numbered 1..N; this is what the author
        # [EN] just saw);
        # [EN] · `last_review` the numbered items in the checkup report;
        # [EN] · `noask_left` how many "don't ask me" rounds remain (`-1` = never ask until the author
        # [EN] says "you can ask me now").
        self.last_problems: list[str] = []
        self.last_review: list[str] = []
        self.noask_left = 0

    #: 当前设定 —— **转发到工具箱**（唯一事实来源）。
    #: `Toolbox.改设定` 会 `validate_settings()` 换一个新 dict，所以"各存一份"
    #: 一定会分叉；转发就没有第二份可以分叉。
    # [EN] : Current settings -- **forwarded to the toolbox** (single source of truth).
    # [EN] : `Toolbox.改设定` will `validate_settings()` to swap in a new dict, so "each storing its own copy"
    # [EN] : will definitely diverge; with forwarding there is no second copy to diverge.
    @property
    def settings(self) -> dict[str, Any]:
        return self.box.settings

    @settings.setter
    def settings(self, value: dict[str, Any]) -> None:
        self.box.settings = value

    # ══════════════════════════════════════════════════════════
    #  对外
    # [EN] External
    # ══════════════════════════════════════════════════════════
    def digest(self, *, max_chars: int = 1400) -> str:
        """当前设定的**紧凑摘要** —— 每一轮都编进 messages（模型永远知道现状）。
                English:
        **Compact summary** of the current settings — compiled into messages every round (the model
        always knows the current state).
        """
        try:
            from ingest.optimize import settings_summary
            return settings_summary(self.settings, max_chars=max_chars)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('渲染设定摘要失败：%r', e)
            return f'（摘要渲染失败：{e}）'

    async def intro(self) -> str:
        """开场：先做一遍**体检**，并把结论记进事件流。

        ★ 这一条进事件流很要紧：作者接下来常说的一句话是"**就按你刚才说的第 2 条改**"。
          上一版体检**没有**进历史，模型看不到自己说过什么 —— 那句指代就成了空话。
        
                English:
        Opening: first do a **health check**, and record the conclusion into the event stream.
                ★ Putting this into the event stream is crucial: the author's next common phrase is "**just change item 2 as you said**".
                  The previous health check was **not** put into history, so the model cannot see what it said — that reference becomes empty words.
        """
        text = ''
        try:
            from ingest.optimize import review_settings
            text = await review_settings(self.settings, name=self.name,
                                         tier=self.tier, missing=list(self.missing))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('体检失败（不影响继续）：%r', e)
            text = ''
        if text:
            self._push('review', text)
            # ★ 把体检报告里**编号的那几条**记下来：作者看完就说「处理 1 2」，
            #   指的就是它们（`polish/intent.py` 用它把编号翻译成条目原文）。
            # [EN] ★ Record the **numbered items** of the checkup report: the author reads it and then
            # [EN] says "process 1 2", meaning exactly those (`polish/intent.py` uses this to translate
            # [EN] numbers into the source text of the items).
            self.last_review = _intent.review_items(text)
        return text

    async def ask(self, instruction: str) -> PolishTurn:
        """作者下一条指令 → 跑完整的一轮（工具循环 + 自省）。

        ★★ **先解析作者这句话的意图，再决定怎么跑**（2026-10-11 用户报的两个毛病）：
          · 「修复4个问题」/「修复所有自查问题」→ 把那几条**展开成编号任务单**下达
            （模型数不清"4 个"是哪四条，但**我们手里就有那份列表**）；
          · 「不要问我」/「至少3轮不要问我」→ 记下来，并在**代码里**拦住这一轮
            之后的反问（见 `_loop`）。
          · 「可以问我了」→ 解除。

        English:
        The author's next instruction -> run a full round (tool loop + self-reflection).
        ★★ **Parse the intent of this sentence first, then decide how to run** (the two problems
          reported by the user on 2026-10-11):
          · "fix the 4 problems" / "fix all the self-check problems" -> **expand those items into a
            numbered work order** and hand it down (the model cannot count which four "4" means, but
            **we hold that list**);
          · "don't ask me" / "don't ask me for at least 3 rounds" -> remember it and block the
            follow-up questions of this round **in code** (see `_loop`);
          · "you can ask me now" -> lift it.
        """
        instruction = str(instruction or '').strip()
        t0 = time.monotonic()
        if not instruction:
            return PolishTurn(reply=t('（空指令，没动任何东西）'))
        self._push('author', instruction)

        turn = PolishTurn()
        # ── 意图：免打扰 / 整批 / 点名 ──
        # [EN] -- Intent: do-not-disturb / whole batch / named items --
        it = _intent.parse(instruction, problems=self.last_problems,
                           review=self.last_review)
        if it.ask_again and not it.noask_all and not it.noask_rounds:
            self.noask_left = 0
        if it.noask_all:
            self.noask_left = -1          # 一直不问，直到作者说"可以问我了"
            # [EN] Never ask until the author says "you can ask me now"
        elif it.noask_rounds:
            self.noask_left = max(self.noask_left if self.noask_left > 0 else 0,
                                  int(it.noask_rounds))
        if it.note:
            turn.notes.append(it.note)
            self._push('note', it.note)
        todo = list(it.work)
        if todo:
            self._push('note', t('这一轮要做的（作者点名）：\n{x}').format(
                x='\n'.join(f'{i}. {w}' for i, w in enumerate(todo, 1))))

        ask_back = ''
        feedback: list[str] = []
        rounds = 0
        while True:
            reply, question, steps = await self._loop(instruction, feedback=feedback,
                                                      todo=todo)
            turn.steps += steps
            rounds += 1
            if question:
                ask_back = question
                break
            # ── Reflection：换个视角查一遍自己做的事 ──
            # [EN] ── Reflection: review what you did from a different angle ──
            if not self.reflect_on or rounds > self.max_reflect:
                turn.reply = reply
                break
            problems, nxt = await self._reflect(instruction)
            # ★★ 自查出来的这几条要**记下来**：作者接下来那句"修复4个问题 /
            #   「第 2 条」指的就是它们（下一轮 `_intent.parse` 用得到）。
            # [EN] ★★ These self-checked items must be **remembered**: the author's next sentence
            # [EN] "fix the 4 problems" / "item 2" refers to exactly them (the next round's
            # [EN] `_intent.parse` needs this).
            if problems:
                self.last_problems = list(problems)
            if not problems:
                if nxt:
                    self._push('note', t('自省：{x}').format(x=nxt))
                turn.reply = reply
                break
            turn.reflections.extend(problems)
            self._push('note', t('自省发现 {n} 个问题，再走一轮：{x}').format(
                n=len(problems), x='；'.join(problems)))
            if rounds >= self.max_reflect + 1:
                turn.reply = (reply + '\n\n' + t('⚠ 我自查时还看出这些问题，'
                                                 '没能在一轮里解决：') + '\n· '
                              + '\n· '.join(problems[:4]))
                break
            feedback = problems

        turn.question = ask_back           # ★ 反问要带上（不然调用方只看到一片空白）
        # [EN] ★ Must include the counter-questions (otherwise the caller only sees a blank)
        # ★ 这一轮过完，免打扰的计数往下走一格（`-1` = 一直不问，不动）。
        #   ⚠ 减到 0 就**恢复会问**：作者说"3 轮不要问我"是**三**轮，
        #   第四轮该问还得问（无限期不问就成了"哑巴"，那比反复问更糟）。
        # [EN] ★ After this round, step the do-not-disturb counter down by one (`-1` = never ask,
        # [EN] unchanged).
        # [EN] ⚠ At 0 it **goes back to asking**: "don't ask me for 3 rounds" means **three** rounds, and
        # [EN] on the fourth it should ask again (never asking turns it into a mute, which is worse than
        # [EN] asking repeatedly).
        if self.noask_left > 0:
            self.noask_left -= 1
        turn.noask_left = self.noask_left
        turn.seconds = time.monotonic() - t0
        turn.changes = self.box.take_changes()
        turn.actions = list(self.actions)
        return turn

    def outcome(self) -> PolishOutcome:
        return PolishOutcome(settings=self.settings,
                             transcript=list(self.events),
                             generated_tools=sorted(self.box.generated),
                             source_writes=list(self.box.source_writes),
                             outputs=dict(self.box.outputs),
                             actions=list(self.actions))

    def load_tools(self) -> list[str]:
        """把盘上已有的生成工具装回来（上一场留下的）。**开工时调一次**。
                English:
        Load back the generation tools already on disk (left over from the previous session). **Call
        once at start of work**.
        """
        loaded = codegen.load_existing(self.box)
        if loaded:
            self._push('note', t('装回了 {n} 个上次生成的工具：{x}').format(
                n=len(loaded), x='、'.join(loaded)))
        return loaded

    # ══════════════════════════════════════════════════════════
    #  主循环
    # [EN] Main loop
    # ══════════════════════════════════════════════════════════
    async def _loop(self, instruction: str, *, feedback: list[str],
                    todo: list[str] | None = None,
                    ) -> tuple[str, str, int]:
        """跑到 Agent 说"收尾"或"问作者"。返回 `(回话, 反问, 步数)`。

        ★★ `todo` 是**作者点名要做的事**（已在 `ask()` 里按编号展开）。
        ★★ **免打扰是硬拦**（2026-10-11 用户报的"必须一轮一问"）：模型这一轮要是
          还想"问作者"，代码**不把它当终点**，而是把"作者说了别问、你自己定"
           作为观察结果喂回去，接着跑 —— 求模型"配合一下"是不牢靠的。

        English:
        Run until the Agent says "wrap up" or "ask the author". Returns `(reply, follow-up question,
        steps)`.
        ★★ `todo` is **what the author named to be done** (already expanded by number in `ask()`).
        ★★ **Do-not-disturb is a hard block** (the user's "it insists on one question per round",
          reported 2026-10-11): if the model still wants to "ask the author" this round, the code
          **does not treat that as the end**, but feeds "the author said don't ask, decide yourself"
          back as an observation and keeps going -- begging the model to "cooperate" is not reliable.
        """
        steps = 0
        for _ in range(self.max_steps):
            steps += 1
            messages = self._compose(instruction, feedback=feedback, step=steps,
                                     todo=todo)
            rep = await ask('daily', messages, purpose='polish_step', want=dict,
                            json_mode=True, max_tokens=_STEP_TOKENS,
                            temperature=0.3, default=None)
            obj = rep.value if isinstance(rep.value, dict) else None
            if not obj:
                why = '；'.join(rep.notes) or t('模型没有给出可用的动作')
                self._push('note', t('这一步没拿到动作：{why}').format(why=why))
                # ★ **不原样重试同一句话**：把"换个手段"作为观察结果喂回去，
                #   下一轮模型自己会换（这是 Agent 相对单次调用最大的优势）。
                # [EN] ★ **Do not retry the same sentence verbatim**: feed "switch to a different approach" back as an
                # [EN] observation result,
                # [EN] and the next round the model will switch on its own (this is the biggest advantage of an Agent
                # [EN] over a single call).
                self._push('observe', t('（上面这次没拿到东西。换个手段：'
                                        '先「列引用文件」或「读设定」看一眼现状，'
                                        '再决定怎么做。）'))
                continue

            used = str(obj.get('用') or '').strip()
            said = str(obj.get('想') or '').strip()
            if used:
                args = obj.get('参') if isinstance(obj.get('参'), dict) else {}
                self._say(said)
                res = await self.box.call(used, args)
                self.actions.append({'工具': used, '参数': args,
                                     '成功': bool(res.ok),
                                     '结果': res.short()})
                self._push('tool', res.text, name=used)
                if res.data:
                    self._push('tool_data', json.dumps(res.data, ensure_ascii=False)[:800],
                               name=used)
                self._emit('tool', f'{used}：{res.short()}')
                continue

            back = str(obj.get('问') or '').strip()
            if back:
                self._say(said)
                if self._noask_on():
                    # ★★ 作者明确说了"别问我" —— **代码里拦住**这次反问。
                    #   不拦的话就是我们教了它一个新说法、它却照旧问。
                    # [EN] ★★ The author explicitly said "don't ask me" -- **block it in code**.
                    # [EN] Not blocking means we taught it a new phrase and it still asks anyway.
                    self._push('observe', t('（作者说了**不要问他** —— 这一句不许用「问」。'
                                            '按你认为最合理的做法**直接做**，'
                                            '把你替他定的那几处，连同理由，写进「终」的回话里。）'))
                    continue
                self._push('agent', back)
                return '', back, steps

            final = str(obj.get('终') or '').strip()
            if final:
                self._say(said)
                self._push('agent', final)
                return final, '', steps

            # 三个键一个都没有 —— 说清该怎么回，让它下一轮改对
            # [EN] None of the three keys is present -- state clearly how to respond, so it can fix it next round
            self._push('observe', t('（你这一轮回的 JSON 里既没有「用」也没有「终」'
                                    '也没有「问」。照着协议回一个。）'))
        self._push('note', t('到了步数上限（{n} 步），先把现状讲清楚').format(n=self.max_steps))
        return (t('（这一轮我先停在这 —— 我做的事都记在上面了。'
                  '你可以说一句"接着做"，也可以直接告诉我下一步要改什么。）')), '', steps

    # ══════════════════════════════════════════════════════════
    #  Reflection
    # ══════════════════════════════════════════════════════════
    async def _reflect(self, instruction: str) -> tuple[list[str], str]:
        """回头查一遍：漏了？改坏了？越权了？编了？
                English:
        Review afterwards: missed anything? broke anything? overstepped? made anything up?
        """
        changed = self._changed_view()
        prompt = _REFLECT_PROMPT.replace('{instruction}', instruction[:1500]) \
                               .replace('{transcript}', self._transcript(detail=900)) \
                               .replace('{changed}', changed or t('（这一轮没有改动）'))
        rep = await ask('daily', [{'role': 'user', 'content': prompt}],
                        purpose='polish_reflect', want=dict, json_mode=True,
                        max_tokens=_REFLECT_TOKENS, temperature=0.2, default=None)
        obj = rep.value if isinstance(rep.value, dict) else None
        if not obj:
            return [], ''
        has = obj.get('有问题')
        probs = obj.get('问题')
        out = [str(x).strip() for x in (probs if isinstance(probs, list) else [])
               if str(x).strip()][:4]
        if not _truthy(has):
            return [], str(obj.get('下一步') or '').strip()
        return out, str(obj.get('下一步') or '').strip()

    # ══════════════════════════════════════════════════════════
    #  事件流 / 消息编排
    # [EN] Event stream / message orchestration
    # ══════════════════════════════════════════════════════════
    def _push(self, kind: str, text: str, **extra: Any) -> None:
        ev = {'kind': kind, 'text': str(text or '')}
        ev.update(extra)
        self.events.append(ev)

    def _say(self, text: str) -> None:
        """把模型这一回合的"想法"记下来（**不进 messages 的正文，只做审计**）。
                English:
        Record the model's "thoughts" for this turn (**not into the body of messages, only for audit**).
        """
        if str(text or '').strip():
            self.events.append({'kind': 'thought', 'text': str(text).strip()})

    def _emit(self, kind: str, text: str) -> None:
        if self._on_event is not None:
            try:
                self._on_event(kind, text)
            except Exception:                                    # noqa: BLE001
                pass

    def _noask_on(self) -> bool:
        """现在是不是"别问我"状态（`-1` = 一直，正数 = 还剩几轮）。
            English:
        Are we in the "don't ask me" state right now (`-1` = forever, positive = rounds left)?
        """
        return bool(self.noask_left != 0)

    def _compose(self, instruction: str, *, feedback: list[str],
                 step: int = 1, todo: list[str] | None = None) -> list[dict]:
        """**把整条历史编成 messages** —— 这就是"带上历史信息"那句话的落点。
                English:
        **Compile the entire history into messages** — this is where the phrase "carry historical
        information" lands.
        """
        msgs: list[dict] = [{'role': 'system', 'content': self._system()}]
        body = self.events
        if len(body) > _MAX_EVENTS:
            # 超长时丢**最老的**，但**体检与作者原话永远留着**（那两样一丢，
            # 后面所有指代都成了空话）。
            # [EN] When too long, drop the **oldest**, but **the checkup and the author's own words are always
            # [EN] kept** (lose those two,
            # [EN] and all later references become empty words).
            keep = [e for e in body if e['kind'] in ('review', 'author')][:6]
            tail = [e for e in body if e not in keep][-(_MAX_EVENTS - len(keep)):]
            body = keep + tail
        for ev in body:
            k = ev.get('kind')
            txt = str(ev.get('text') or '')[:_EVENT_CHARS]
            if not txt:
                continue
            if k == 'author':
                msgs.append({'role': 'user', 'content': t('作者：{x}').format(x=txt)})
            elif k == 'agent':
                msgs.append({'role': 'assistant', 'content': txt})
            elif k == 'review':
                msgs.append({'role': 'assistant',
                             'content': t('（这是我刚看过的体检结论）\n{x}').format(x=txt)})
            elif k == 'tool':
                msgs.append({'role': 'user',
                             'content': t('工具「{n}」返回：\n{x}').format(
                                 n=ev.get('name') or '?', x=txt)})
            elif k == 'tool_data':
                msgs.append({'role': 'user', 'content': t('（结构化的改动明细）{x}').format(
                    x=txt)})
            elif k == 'observe':
                msgs.append({'role': 'user', 'content': txt})
            elif k == 'note':
                msgs.append({'role': 'user', 'content': t('（系统提示）{x}').format(x=txt)})
            # `thought` 不编进去：那是我这一回合的自言自语，连着编会越滚越长
            # [EN] `thought` is not compiled in: that is this round's self-talk of mine, and compiling it in a row
            # [EN] would grow longer and longer
        tail = [t('【现在的设定】'), self.digest()]
        if feedback:
            tail += ['', t('★ 你上一轮交的东西**自查出这些问题**，请在这一轮里改掉：'),
                     '\n'.join(f'· {x}' for x in feedback)]
        if todo:
            # ★★ 作者点名要做的事 —— 编号下达，**一条不落**。
            #   2026-10-11 用户报的"我说修复4个问题 但是它不知道我什么意思"：
            #   模型数不清"4 个"指哪四条，而这份清单是**我们算出来的**。
            # [EN] ★★ What the author named to be done -- handed down with numbers, **not one missed**.
            # [EN] User report 2026-10-11: "I said fix the 4 problems but it doesn't understand what I
            # [EN] mean" -- the model cannot count which four items "4" means, while **we** computed
            # [EN] this list.
            tail += ['', t('★ 作者这一轮**点名**要做的事（全部做完再收尾，一条不落）：'),
                     '\n'.join(f'{i}. {w}' for i, w in enumerate(todo, 1))]
        if self._noask_on():
            # ★★ 免打扰也要**写进提示词**：硬拦（`_loop` 里那段）保证不出反问，
            #   但只硬拦的话，模型会把"想问的"憋成一个含糊的收尾；写清楚之后
            #   它才会**把判断和理由说出来**（那正是作者要的）。
            # [EN] ★★ Do-not-disturb must also **go into the prompt**: the hard block (in `_loop`)
            # [EN] guarantees no question comes out, but with the hard block alone the model would
            # [EN] choke its questions into a vague wrap-up; spelling it out makes it **state its
            # [EN] judgement and reasoning** (which is exactly what the author wants).
            left = (t('从现在起都不要问') if self.noask_left < 0
                    else t('接下来 {n} 轮（含这一轮）都不要问').format(n=self.noask_left))
            tail += ['', t('★★ 作者明确要求：**{x}**。所以：\n'
                           '· 这一轮**不许**用「问」这个动作；\n'
                           '· 拿不准的，按你认为最合理的做法**直接定了**，'
                           '并把你替他做的判断与理由，写进「终」的回话里；\n'
                           '· 清单上的事**全做完**再收尾。').format(x=left)]
        tail += ['', t('【现在请你处理】作者刚说的：{x}').format(x=instruction),
                 # ★ 报个步数。这不只是给模型看的礼貌提示 —— Agent 最典型的失败
                 #   模式是"再查一点、再确认一次"永远收不了尾；知道自己还剩几步，
                 #   它才会在该收的时候收。顺带让 MOCK 能按步数演一段真实的两步流程。
                 # [EN] ★ Report a step count. This is not just a polite hint for the model -- the most typical failure
                 # [EN] mode of an Agent is "check a bit more, confirm once more" and it never wraps up; only by knowing
                 # [EN] how many steps it has left
                 # [EN] will it wrap up when it should. Incidentally, this lets MOCK act out a realistic two-step flow
                 # [EN] by step count.
                 t('（这是本轮第 {n}/{m} 步；步数用完我就会停下来收口）').format(
                     n=int(step), m=self.max_steps)]
        msgs.append({'role': 'user', 'content': '\n'.join(tail)})
        return _merge_consecutive(msgs)

    def _system(self) -> str:
        head = (t('你是这本小说《{n}》的**设定打磨师**，替作者把开卷时自动提取出来的设定'
                  '打磨好。').format(n=self.name) + '\n')
        if self.tier:
            head += t('当前评档：{x}').format(x=self.tier) + '\n'
        if self.missing:
            head += t('离黄金档还缺：{x}').format(x='、'.join(self.missing)) + '\n'
        return head + '\n' + _PROTOCOL.replace('{scope}', self.scope.describe()) \
                                      .replace('{tools}', self.box.describe())

    def _transcript(self, *, detail: int = 900) -> str:
        """给 Reflection 看的"全过程"（工具调用 + 结果 + 结论）。
                English:
        The "full process" for Reflection to see (tool calls + results + conclusions).
        """
        lines: list[str] = []
        for ev in self.events[-24:]:
            k = ev.get('kind')
            txt = ' '.join(str(ev.get('text') or '').split())[:detail]
            if k == 'thought':
                continue
            label = {'author': '作者', 'agent': '我', 'review': '体检',
                     'tool': f'工具·{ev.get("name") or "?"}', 'note': '提示',
                     'observe': '提示'}.get(k, k)
            if txt:
                lines.append(f'[{label}] {txt}')
        return '\n'.join(lines) or t('（还没有过程记录）')

    def _changed_view(self) -> str:
        """Reflection 要看"改完之后那几个地方现在长什么样"。
                English:
        Reflection needs to see "what those places look like now after the changes".
        """
        changes = list(self.box.changes)
        if not changes:
            return ''
        out: list[str] = []
        for line in changes[:12]:
            # `改 人物[0].性格：旧 → 新` —— 取路径再看一眼现在是什么
            # [EN] Change Person[0].personality: old → new — fetch the path and take another look at what it
            # [EN] currently is
            path = line.split('：')[0] if '：' in line else ''
            bits = path.split(' ', 1)
            p = bits[1].strip() if len(bits) > 1 else ''
            now = ''
            if p:
                try:
                    from polish.tools import get_path, parse_path
                    now = _brief(get_path(self.settings, parse_path(p)), 120)
                except Exception:                                # noqa: BLE001
                    now = ''
            out.append(f'{line}' + (f'　（现在：{now}）' if now else ''))
        return '\n'.join(out)


def render_report(agent: 'PolishAgent') -> str:
    """把一场打磨整理成一份**给人读的记录**（项目侧与引用侧写的是同一份）。

    用户 2026-10-07：「最终优化结果需要**同时**写到项目里和原始的设定文件夹里」。
    两处写的**必须是同一份文本** —— 各写各的迟早对不上（本项目为"两处各写一份"
    栽过好几次，见 `SPEC` 那节的"名字写死两处，靠判据钉住一致"）。
    
        English:
    Organize one polish session into a **human-readable record** (the project side and the reference
    side write the same copy).
        User 2026-10-07: "The final optimization result must be written to **both** the project and the original settings folder."
        The two locations **must contain the same text** — writing separately on each side will eventually diverge (this project has been burned
        several times by "writing a separate copy on each side", see the "names hardcoded in two places, pinned consistent via criteria" section in `SPEC`).
    """
    out = agent.outcome()
    lines = [f'# AI 打磨记录 · {agent.name}', '']
    lines.append(t('> 由打磨 Agent 在开卷时生成；**引用文件夹里正文一个字没动**'))
    lines.append('')
    changes = [f'- {x}' for x in agent.box.changes] or [t('- （这一场没有改动设定）')]
    lines += [t('## 改了什么'), ''] + changes + ['']
    if out.generated_tools:
        lines += [t('## 现场生成的工具（在项目的 AI工具/ 里）'), '']
        lines += [f'- `{x}.py`' for x in out.generated_tools] + ['']
    if out.source_writes:
        lines += [t('## 追加回引用文件夹的文件'), '']
        lines += [f'- `{x}`' for x in out.source_writes] + ['']
    # 过程：只记工具调用（作者原话和结论在对话里已经看过一遍了，不必重复贴）
    # [EN] Process: only record tool calls (the author's own words and conclusions have already been seen
    # [EN] once in the conversation, no need to repeat-paste)
    acts = [x for x in out.actions if x.get('工具')]
    if acts:
        lines += [t('## 过程（调过哪些工具）'), '']
        for a in acts[:60]:
            mark = '✓' if a.get('成功') else '×'
            lines.append(f'- {mark} `{a.get("工具")}`　{str(a.get("结果") or "")[:100]}')
        lines.append('')
    return '\n'.join(lines)


def _merge_consecutive(msgs: list[dict]) -> list[dict]:
    """把**连着出现的同角色**消息并成一条。

    为什么非做不可：事件流里"工具返回 / 系统提示 / 新指令"全是 `user`，直接编出来
    会出现三个 `user` 挨在一起。**严格的 OpenAI 兼容服务会因此报 400**
    （本项目在 `LLM_CAP_SYSTEM_ROLE` 那件事上已经吃过一次"协议细节不兼容"的亏）。
    并起来对模型没有损失（就是一段更长的上下文），标题行都还在。
    
        English:
    Merge **consecutive messages from the same role** into one.
        Why this is mandatory: in the event stream, "tool return / system prompt / new instruction" are all `user`, so if compiled directly
        three `user` messages would appear back to back. **Strict OpenAI-compatible services will return 400 because of this**
        (this project already got burned once by "protocol detail incompatibility" with the `LLM_CAP_SYSTEM_ROLE` issue).
        Merging causes no loss to the model (it is just a longer context), and the header lines are all still there.
    """
    out: list[dict] = []
    for m in msgs:
        if out and out[-1].get('role') == m.get('role') and m.get('role') != 'system':
            out[-1] = {'role': m['role'],
                       'content': str(out[-1].get('content') or '') + '\n\n'
                                  + str(m.get('content') or '')}
        else:
            out.append(dict(m))
    return out


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    return str(v or '').strip().lower() in ('true', 'yes', '1', '是', '有')
