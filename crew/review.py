# -*- coding: utf-8 -*-
"""**剧本审读**：全程记账 + 上屏之前过一遍。

用户 2026-10-08
---------------
「这段对话很奇怪 有个人来讨要欠款 突然出现 柳娘也去看他了 结果什么都没做 …
  大家都在讨论自己的事情 很奇怪 人物进场了肯定是有用的 大家要去跟他沟通
  （动作 对话 事情等等）不然不要突然来一个人 而且这段对话感觉大家没有讨论
  一个主题 或者讨论了主题 但是很散 而且说的话都不个人化」
「'目光顺着小臂滑到底 才收回 压在壶盖上'这不是人话 … '卷了' 是啥意思 看不懂
  跑堂对自家伙计说'客官慢用' 啥意思 他又不是客人」
「你看是否有独立的Agent 而不是导演在盯着演员说的每一句话 没有就做一个
  在演员真的说出来之前 把新生成的话放到已经出现的话里过一遍 看是否通顺
  而且这个Agent要一直记录生成的所有信息 所有输出到窗口的东西包括动作
  场景切换 伏笔激活 导演动作 人物对话 等等 都要让这个Agent记录下来
  任何一个新出现的东西 不管来自哪个Agent或者来源 都需要这个Agent放到已有
  历史里看下是否是一个合理的 正确的好看的故事和剧本 不是就不要放出来」

它和已有的三个「看戏的人」怎么分工（**别把它们并成一个**）
-----------------------------------------------------
| 谁 | 什么时候看 | 看什么 | 能不能拦 |
|---|---|---|---|
| `crew/agents.Continuity`（场记） | **一天结束** | 连戏：时间/物件/称呼/在场 | 不能（只报） |
| `crew/agents.Reviewer`（复盘） | **一天结束** | 这一段作为一章成不成立 | 不能（只报） |
| `director/supervisor`（导演盯戏） | 每 N 拍 | 好几个人重复同一件事（零成本字面比对） | 不能（只提醒） |
| **本模块 + `crew/agents.ScriptDoctor`** | **上屏之前** | 是不是人话／像不像这个人／接不接上文／一个主题 | **能**（改写或拦下） |

为什么非要有第四个：上面三个**全在事后**（一天结束，或者"已经发生了"），
而用户报的毛病**在上屏那一刻就看得出来**（"卷了"、"客官慢用"不是人话）。
事后能做的只有"明天注意"，而屏幕上那句读者已经看了。

两件事，一个模块
----------------
1. **记**（`ScriptLog`）：**一切上屏的东西**都记 —— 动作 / 对话 / 旁白 /
   场景切换分隔符 / 伏笔激活（导演事件）/ 前情提要 / 今日简介 / 今日任务 /
   阶段 / 剧组状态 / 收工总结。这半是**零成本**的（往一张表里追加一行），
   所以"每一轮都记满"才做得起。
2. **审**：规则层在这一模块（**逐条、零成本、抓形式问题**）；
   模型层在 `crew/agents.ScriptDoctor`（**每拍一次、抓语义问题**）。
   两层的分工是**故意的**，见 `RULES` 那段注释。

三条口径（改之前先读）
----------------------
1. **宁可漏，不可误杀。** 规则层只写"命中了就一定不是人话"的那种
   （残留的 JSON、占位符、出戏词、标点乱码、半截话）。**语感**类的东西
   （"卷了"是不是人话、这句像不像这个人）一律交给模型 —— 规则判不准，
   而规则判错的代价是**把好句子删了**，那比漏一句更糟。
2. **拦下要留痕。** 被拦的东西进 `审读台账.jsonl`、进日志、进
   `剧本审读.md`，**绝不静默丢弃**（本项目对"静默降级"零容忍）。
3. **台账是"读者真正看过的那一份"。** 只记**真的上屏了**的（被去重挡下的、
   被拦下的走各自的分支），所以"审读读到的历史"与"读者读到的正文"是同一份。

English:
**Script review**: bookkeeping throughout + a pass before going on screen.
User 2026-10-08
---------------
"This dialogue is very strange. Someone comes to demand repayment, suddenly appears, Liu Niang
also goes to look at him, and in the end does nothing ...
  Everyone is discussing their own matters, very strange. A character entering must be useful, everyone should go communicate with them
  (action, dialogue, matter, etc.) otherwise don't suddenly bring in a person. And this dialogue feels like everyone is not discussing
  one topic, or discusses a topic but it's very scattered, and what they say isn't personalized."
"'Gaze slides down the forearm to the bottom, only then retracts, presses on the pot lid' is not
human speech ... '卷了' what does it mean, can't understand
  The waiter says to his own colleague '客官慢用', what does that mean, he's not a guest"
"See if there's an independent Agent rather than the director watching every line the actors
say. If not, make one
  before the actor actually says it, put the newly generated line through the already-appeared lines, see if it's coherent
  and this Agent must always record all generated information, all things output to the window including actions
  scene switches, foreshadowing activations, director actions, character dialogue, etc., all must be recorded by this Agent
  any newly appearing thing, no matter which Agent or source it comes from, needs this Agent to put it into the existing
  history and see if it's a reasonable, correct, good-looking story and script; if not, don't let it out"
How it divides work with the existing three "audience members" (**don't merge them into one**)
-----------------------------------------------------
| Who | When it looks | What it looks at | Can it block |
|---|---|---|---|
| `crew/agents.Continuity` (continuity) | **end of day** | continuity: time/props/forms of address/presence | no (report only) |
| `crew/agents.Reviewer` (review) | **end of day** | whether this segment holds up as a chapter | no (report only) |
| `director/supervisor` (director watching the scene) | every N beats | several people repeating the same thing (zero-cost literal comparison) | no (remind only) |
| **this module + `crew/agents.ScriptDoctor`** | **before going on screen** | is it human speech / does it resemble this person / does it connect to prior text / one topic | **yes** (rewrite or block) |
Why a fourth is necessary: the above three are **all after the fact** (end of day, or "it
already happened"),
whereas the problems the user reported **are visible at the moment of going on screen** ("卷了",
"客官慢用" are not human speech).
All you can do after the fact is "pay attention tomorrow", but the reader has already seen that
line on screen.
Two things, one module
----------------
1. **Record** (`ScriptLog`): record **everything that goes on screen** —— action / dialogue / narration /
   scene-switch separator / foreshadowing activation (director event) / recap / today's intro / today's task /
   stage / crew status / wrap-up summary. This half is **zero-cost** (append a row to a table),
   so "record fully every round" is affordable.
2. **Review**: the rule layer is in this module (**line by line, zero cost, catches form problems**);
   the model layer is in `crew/agents.ScriptDoctor` (**once per beat, catches semantic problems**).
   The division of labor between the two layers is **intentional**, see the `RULES` comment.
Three principles (read before changing)
----------------------
1. **Better to miss than to false-positive.** The rule layer only writes things where "if it matches, it's definitely not human speech"
   (leftover JSON, placeholders, out-of-character words, garbled punctuation, half-sentences).**Language sense**-type things
   (whether "卷了" is human speech, whether this line sounds like this person) are all left to the model -- rules can't judge accurately,
   and the cost of a rule misjudging is **deleting a good sentence**, which is worse than missing one.
2. **Blocking must leave a trace.** Blocked items go into `审读台账.jsonl`, into the logs, into
   `剧本审读.md`, **never silently discarded** (this project has zero tolerance for "silent degradation").
3. **The ledger is "the copy the reader actually saw."** Only record what **actually made it on screen** (items blocked by dedup,
   items blocked go through their own branches), so "the history the reviewer read" and "the text the reader read" are the same copy.
"""
from __future__ import annotations

import difflib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from util.text import norm_line, similarity

_LOG = __import__("logging").getLogger("nws.review")

#: 运行文件夹里那份**给人看**的审读小结（一天一份，覆盖写）
# [EN] : The **human-readable** review summary in the run folder (one per day, overwritten)
FILE_MD = '剧本审读.md'
#: 运行文件夹里那份**给程序看**的流水（一轮一份，追加写）
# [EN] : The **program-readable** log in the run folder (one per round, appended)
FILE_LOG = '审读台账.jsonl'


# ══════════════════════════════════════════════════════════════════════
#  台账
# [EN] ledger
# ══════════════════════════════════════════════════════════════════════
@dataclass
class Rec:
    """台账里的一行：**一条上屏的东西**（或一条被拦下的）。

    `seq` 是流水号（审读给模型的"序号"就用它，回来好对上号）；
    `source` 是**来源**（哪个 Agent／哪条通道）—— 用户要的
    「不管来自哪个Agent或者来源」就靠它落下来。
    
        English:
    One line in the ledger: **one thing that made it on screen** (or one thing that was blocked).
        `seq` is the serial number (the "number" the reviewer gives the model uses it, so it can be matched up on return);
        `source` is the **origin** (which Agent / which channel) -- the user's requirement
        "regardless of which Agent or source it comes from" lands on this.
    """

    seq: int
    day: int
    tick: int
    kind: str
    who: str
    text: str
    source: str = ''
    to: str = ''
    place: str = ''
    blocked: bool = False
    why: str = ''
    was: str = ''            # 被改写时：改之前的原文
    # [EN] when rewritten: the original text before the change

    def line(self) -> str:
        """给**模型读**的那一行（一句话，含说话人）。
                English:
        The line given to the **model** to read (one sentence, including the speaker).
        """
        t = ' '.join(str(self.text or '').split())
        if self.who:
            return f'〔{self.kind}·{self.who}〕{t}'
        return f'〔{self.kind}〕{t}'

    def to_dict(self) -> dict:
        return {'序号': self.seq, '天': self.day, '拍': self.tick,
                '类型': self.kind, '谁': self.who, '对': self.to,
                '地点': self.place, '来源': self.source,
                '文本': self.text, '被拦': self.blocked, '原因': self.why,
                '原文': self.was}


class ScriptLog:
    """**上屏台账**：每一轮从头记起，一路追加。

    ⚠ 它不是"日志"（`logs/` 那套是给排障用的，谁都能写）。
      它是**审读的材料**：审读要"把新生成的话放到已经出现的话里过一遍"，
      那张"已经出现的话"的表就是这里。所以它有两条硬约束：
        · **只收真的上屏了的**（被去重／被拦下的不进 `recent()`）；
        · **顺序就是上屏顺序**（模型判断"接不接上文"靠的就是这个顺序）。
    
        English:
    **On-screen ledger**: each round records from the start, appending all the way.
        ⚠ It is not a "log" (the `logs/` set is for troubleshooting, anyone can write it).
          It is the **material for review**: review needs to "take the newly generated lines and run them through the lines that have already appeared",
          and the table of "lines that have already appeared" is right here. So it has two hard constraints:
            · **Only accept what actually went on screen** (things deduped/blocked do not enter `recent()`);
            · **The order is the on-screen order** (that is exactly the order the model relies on to judge "does this follow the preceding text").
    """

    def __init__(self, *, cap: int = 4000) -> None:
        self.rows: list[Rec] = []
        self.blocked: list[Rec] = []
        self._cap = max(100, int(cap))
        self._seq = 0
        #: 名字 → 首次出现在第几拍（判"进场之后有没有戏"）
        # [EN] : name -> first appears at which beat (to judge "is there any drama after entering")
        self._first_tick: dict[str, int] = {}
        #: 名字 → 说过几次话 / 被点名几次 / 做过几次动作
        # [EN] : name -> how many times spoken / how many times addressed by name / how many times performed an
        # [EN] action
        self._spoke: dict[str, int] = {}
        self._addressed: dict[str, int] = {}
        self._acted: dict[str, int] = {}

    # ── 记 ────────────────────────────────────────────────────────
    # [EN] ── Record ────────────────────────────────────────────────────────
    def add(self, *, kind: str, text: str, who: str = '', to: str = '',
            day: int = 0, tick: int = 0, source: str = '', place: str = '',
            blocked: bool = False, why: str = '', was: str = '',
            archived: bool = False) -> Rec:
        """记一行。

        `archived=True` = **改写记录**：它不是"上屏的那一份"，所以不进 `rows`
        （否则 `recent()` 会把改写后的句子当成一条新的历史，同一句话在
        "已经出现过的话"里出现两次），但要进流水，供人查"原来是什么、被改成什么"。
        [EN] `archived=True` = a **rewrite record**: it is not "the copy that went on screen", so it
        does not enter `rows` (otherwise `recent()` would treat the rewritten sentence as a new
        history entry and the same line would appear twice in "what has already been said"), but it
        does enter the stream so a human can see "what was it before, what did it become".
        """
        self._seq += 1
        r = Rec(seq=self._seq, day=int(day or 0), tick=int(tick or 0),
                kind=str(kind or ''), who=str(who or ''), to=str(to or ''),
                text=str(text or ''), source=str(source or ''),
                place=str(place or ''), blocked=bool(blocked),
                why=str(why or ''), was=str(was or ''))
        if blocked:
            self.blocked.append(r)
            return r
        if archived:
            # 只进流水（`everything()` 读 `rows + blocked`），不进"读者看过的那一份"
            # [EN] Stream only (`everything()` reads `rows + blocked`), not "the copy the reader saw"
            self.blocked.append(r)
            return r
        self.rows.append(r)
        if len(self.rows) > self._cap:
            self.rows = self.rows[-self._cap:]
        self._observe(r)
        return r

    def _observe(self, r: Rec) -> None:
        """顺手记「谁什么时候第一次出现、有没有开过口」——给"进场无戏"用。
                English:
        Conveniently record "who first appeared when, and whether they have ever spoken" —— used for
        "enters with no scene".
        """
        who = str(r.who or '').strip()
        if who:
            self._first_tick.setdefault(who, int(r.tick or 0))
        if r.kind == 'enter' and who:
            self._first_tick.setdefault(who, int(r.tick or 0))
        if r.kind == 'dialogue' and who:
            self._spoke[who] = self._spoke.get(who, 0) + 1
        tgt = str(r.to or '').strip()
        if tgt:
            self._addressed[tgt] = self._addressed.get(tgt, 0) + 1
        if r.kind == 'action':
            if who:
                self._acted[who] = self._acted.get(who, 0) + 1
            # ★ 动作句里**提到了谁的名字**也算"有人跟他搭上了"。
            #   用户要的是「大家要去跟他沟通（**动作** 对话 事情等等）」——
            #   "柳娘过去招呼他一声"是动作，不是对话，不数它就会误报"没人理他"。
            #   取子串命中（中文没有词边界），与 `sim/loop._mentioned_names`
            #   同一个口径；**只在已知名字里找**，免得把常用词当人名。
            # [EN] ★ In an action sentence, **whose name is mentioned** also counts as "someone engaged with them".
            # [EN] What the user wants is "everyone should go communicate with them (**action**, dialogue, matter,
            # [EN] etc.)" ——
            # [EN] "Liu Niang went over to greet him" is an action, not dialogue; if you don't count it, you'll
            # [EN] falsely report "nobody paid attention to him".
            # [EN] Substring match hit (Chinese has no word boundaries), same as `sim/loop._mentioned_names`
            # [EN] same standard; **only search among known names**, to avoid treating common words as names.
            blob = str(r.text or '')
            for nm in list(self._first_tick):
                if nm and nm != who and nm in blob:
                    self._addressed[nm] = self._addressed.get(nm, 0) + 1

    # ── 取 ────────────────────────────────────────────────────────
    # [EN] ── Fetch ────────────────────────────────────────────────────────
    def recent(self, n: int = 40) -> list[Rec]:
        """最近 n 条**真的上屏了的**（给模型当"已经出现的话"）。
                English:
        The most recent n **that actually went on screen** (given to the model as "lines that have
        already appeared").
        """
        return list(self.rows[-max(1, int(n)):])

    def recent_lines(self, n: int = 40) -> list[str]:
        return [r.line() for r in self.recent(n)]

    def since(self, seq: int) -> list[Rec]:
        """从 `seq`（不含）之后的全部行 —— "这一拍新加的"用得上。
                English:
        All lines after `seq` (exclusive) —— "newly added in this beat" can use it.
        """
        return [r for r in self.rows if r.seq > int(seq)]

    def everything(self, after_seq: int = 0) -> list[Rec]:
        """**上屏的 + 被拦下的**，按流水号排（给`审读台账.jsonl` 用）。

        ⚠ 为什么流水里也要有拦下的：用户要的是「**一直记录**生成的所有信息」——
          被拦下的那几条恰恰是最该查的（"为什么这句没上屏"）。
          只把上屏的写进流水，等于把这份台账变成"正文的副本"，
          那它就白记了。
        
                English:
        **On-screen + blocked**, sorted by serial number (used for `审读台账.jsonl`).
                ⚠ Why the serial also needs the blocked ones: what the user wants is "**always record** all generated information" ——
                  the blocked few are exactly the ones most worth checking ("why did this sentence not go on screen").
                  Writing only the on-screen ones into the serial amounts to turning this ledger into a "copy of the main text",
                  then it would have been recorded for nothing.
        """
        out = [r for r in (self.rows + self.blocked) if r.seq > int(after_seq)]
        out.sort(key=lambda r: r.seq)
        return out

    def max_seq(self) -> int:
        return int(self._seq)

    def first_tick(self, name: str) -> int:
        return int(self._first_tick.get(str(name or '').strip(), -1))

    def spoke(self, name: str) -> int:
        return int(self._spoke.get(str(name or '').strip(), 0))

    def idle_newcomers(self, now_tick: int, *, window: int = 8) -> list[str]:
        """**进了场、过了 `window` 拍还没搭上话的人**。

        用户原话：「人物进场了肯定是有用的 大家要去跟他沟通（动作 对话 事情等等）
        不然不要突然来一个人」。

        ⚠ 这是**报**（放进导演提示与审读小结），**不是拦** —— 人已经上场了，
          拦不住；能做的只是"下一拍提醒场上的人去接他"。而且它零成本
          （只在台账里数三个数），所以每拍都能问一次。
        
                English:
        **People who have entered the scene and passed `window` beats without yet getting a word in**.
                User's exact words: "A character entering the scene definitely has a purpose; everyone should go communicate with them (action, dialogue, events, etc.)
                otherwise do not suddenly bring in a person".
                ⚠ This is a **report** (put into the director's prompt and the review summary), **not a block** —— the person is already on stage,
                  cannot be blocked; all that can be done is "next beat remind the people on stage to engage with them". And it is zero-cost
                  (only counts three numbers in the ledger), so it can be asked once per beat.
        """
        out: list[str] = []
        for name, t0 in self._first_tick.items():
            if t0 < 0 or now_tick - t0 < max(1, int(window)):
                continue
            if self._spoke.get(name, 0) or self._addressed.get(name, 0):
                continue
            out.append(name)
        return out[:6]

    # ── 落盘 ──────────────────────────────────────────────────────
    # [EN] ── Persist ──────────────────────────────────────────────────────
    def append_jsonl(self, path: Any, rows: Iterable[Rec] | None = None) -> int:
        """把若干行**追加**进流水文件（一轮一份，不做覆盖）。返回写下几行。
                English:
        **Append** several lines into the serial file (one per round, no overwriting). Return how many
        lines were written.
        """
        rows = list(rows if rows is not None else self.rows)
        if not rows:
            return 0
        try:
            with open(path, 'a', encoding='utf-8') as f:
                for r in rows:
                    f.write(json.dumps(r.to_dict(), ensure_ascii=False) + '\n')
            return len(rows)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('审读台账落盘失败（不影响推演）：%r', e)
            return 0

    def report_md(self) -> str:
        """给人看的一天小结：记了多少、拦了几条、拦的是什么、谁进了场没戏。
                English:
        A one-day summary for humans to see: how many recorded, how many blocked, what was blocked, who
        entered the scene with no scene.
        """
        day = max((r.day for r in self.rows), default=0)
        n_kind: dict[str, int] = {}
        for r in self.rows:
            n_kind[r.kind] = n_kind.get(r.kind, 0) + 1
        kinds = '、'.join(f'{k} {v}' for k, v in
                          sorted(n_kind.items(), key=lambda x: -x[1]))
        out = [f'# 剧本审读 · 第 {day} 天', '',
               '> 这份是**审读台账**的小结：它把**所有上屏的东西**记了下来',
               '> （动作 / 对话 / 旁白 / 场景切换 / 伏笔激活 / 导演动作 / 阶段…），',
               '> 并在每一条上屏**之前**与已出现的历史比一遍。',
               '', f'- 上屏 {len(self.rows)} 条' + (f'（{kinds}）' if kinds else ''),
               f'- 拦下 {sum(1 for r in self.blocked if r.blocked)} 条',
               f'- 被审读改写 {sum(1 for r in self.blocked if not r.blocked and r.was)} 条']
        if self.blocked:
            _blocked = [x for x in self.blocked[-60:] if x.blocked]
            _rew = [x for x in self.blocked if not x.blocked and x.was]
            if _blocked:
                out += ['', '## 拦下的（**没有上屏**）', '']
                for r in _blocked:
                    out.append(f'- 第 {r.day} 天 第 {r.tick} 拍 · {r.line()}'
                               f' —— {r.why}')
            if _rew:
                out += ['', '## 被改写的（**上屏的是后半句**）', '']
                for r in _rew[-40:]:
                    out.append(f'- 第 {r.day} 天 第 {r.tick} 拍 · 原：{r.was[:60]}'
                               f' → 改：{r.text[:60]} —— {r.why}')
        idle = [n for n, t in self._first_tick.items()
                if not self._spoke.get(n) and not self._addressed.get(n)]
        if idle:
            out += ['', '## 上了场却没人跟他说上话的（提请下一场补）', '',
                    '、'.join(idle[:12])]
        out += ['', '> 「拦下」的判据见 `crew/review.py` 的 `RULES`（形式类）与',
                '> `crew/agents.ScriptDoctor`（人话 / 像不像这个人 / 接不接上文 /',
                '> 一个主题）。拦下的东西**只记在这里与日志里**，不进正文。']
        return '\n'.join(out) + '\n'

    def reset(self) -> None:
        """新的一轮（同一次运行里换天不用清；换轮才清）。
                English:
        A new round (switching days within the same run does not clear; only switching rounds clears).
        """
        self.rows.clear()
        self.blocked.clear()
        self._first_tick.clear()
        self._spoke.clear()
        self._addressed.clear()
        self._acted.clear()


# ══════════════════════════════════════════════════════════════════════
#  规则层（**零成本、逐条、只抓形式**）
# [EN] Rule layer (**zero cost, line by line, only catches form**)
# ══════════════════════════════════════════════════════════════════════
# 为什么规则层只管"形式"不管"语感"
# [EN] Why the rule layer only handles "form" and not "feel"
# ---------------------------------
# 用户举的例子（"目光顺着小臂滑到底 才收回 压在壶盖上"、"卷了"）
# 都是**语感**问题 —— 它们每一句都"语法通"（有主语有动词），只有读了才知道
# 不是人话。用规则去抓这种句子，要么写一条只对那一个句子生效的正则（没用），
# 要么放宽到"动作句里不许写视线"（把好句子也砍了）。
# 规则判错的代价是**把好句子删掉**，那比漏一句更糟（本项目的口径：
# 宁可漏，不可误杀）。所以：
#   · 这里只留**命中了就一定是错的**那几条；
#   · "像不像人话"整个交给模型（`crew/agents.ScriptDoctor`），
#     它读得到人物设定与上文，那正是它擅长的。
# [EN] The examples the user gave ("gaze slides down the forearm to the bottom, only then retracts,
# [EN] presses on the pot lid", "卷了")
# [EN] are all **feel** problems —— each of them is "grammatically fine" (has subject and verb), only
# [EN] upon reading do you know
# [EN] it's not human speech. To catch such sentences with rules, either write a regex that only works
# [EN] for that one sentence (useless),
# [EN] or loosen it to "no gaze-writing allowed in action sentences" (which cuts the good sentences
# [EN] too).
# [EN] The cost of a rule misjudging is **deleting a good sentence**, which is worse than missing one
# [EN] (this project's standard:
# [EN] better to miss than to falsely kill). So:
# [EN] · Here only keep the few rules where **a hit is definitely an error**;
# [EN] · "Does it sound like human speech" is left entirely to the model (`crew/agents.ScriptDoctor`),
# [EN] which can read the character settings and prior context, which is exactly what it's good at.
#
#: 台词/动作里出现就等于"这不是戏里的人说的话"（模型漏出来的**残留标记**）。
#: 例子：它把 JSON 或代码块一起吐进台词、或者把网址留在正文里。
# [EN] : If it appears in dialogue/action, it means "this is not speech spoken by someone in the scene"
# [EN] (a **residual marker** leaked by the model).
# [EN] : Example: it spits JSON or a code block into the dialogue, or leaves a URL in the body text.
_JUNK_MARKS = ('{"', '"}', '```', '</', '/>', 'http://', 'https://')

#: **元话语**：写稿的人留的"这里以后再补"。人物**不会**这么说。
# [EN] : **Meta-discourse**: a "I'll fill this in later" note left by the writer. A character **would
# [EN] not** say this.
_META_WORDS = ('此处省略', '以下省略', '（略）', '（下略）', '待补', '文中略',
               'TODO', 'XXX', '某某某', '……（此处')

#: **出戏词**：一出现就说明它不是在戏里说话（在跟"作者/用户/系统"讲话）。
# [EN] : **Out-of-scene words**: their appearance means it is not speaking inside the scene (it's
# [EN] talking to the "author/user/system").
_OUT_OF_PLAY = ('作为AI', '作为 AI', '作为人工智能', '我是语言模型',
                '我是 AI', '语言模型', '系统提示', '提示词', '用户要求',
                '根据要求', '本次生成', '输出格式')

#: 连续 3 个以上同类标点（`？？？` / `，，，`）—— 键盘乱敲，不是人写的。
# [EN] : 3 or more consecutive identical punctuation marks (`？？？` / `，，，`) —— keyboard mashing, not
# [EN] written by a human.
_PUNCT_RUN = re.compile(r'([，。！？、；：,.!?;:])\1{2,}')


@dataclass(frozen=True)
class Rule:
    key: str
    why: str
    hit: Callable[[str], bool]


def _r_empty(t: str) -> bool:
    return not t.strip()


def _r_junk(t: str) -> bool:
    return any(m in t for m in _JUNK_MARKS)


def _r_meta(t: str) -> bool:
    return any(m in t for m in _META_WORDS)


def _r_out_of_play(t: str) -> bool:
    return any(m in t for m in _OUT_OF_PLAY)


def _r_punct(t: str) -> bool:
    return bool(_PUNCT_RUN.search(t))


def _r_tail_comma(t: str) -> bool:
    """以逗号/顿号/分号结尾 —— **半截话**（这一条只对**台词**用）。

    ⚠ 边界：句末是「……」或「～」不算（那两种是正常的停顿写法），
      所以只看 `，、；` 三个。
    
        English:
    Ends with a comma/enumeration comma/semicolon —— **half-finished sentence** (this rule applies
    only to **dialogue**).
        ⚠ Boundary: ending with "……" or "～" does not count (those two are normal pause notation),
          so only look at `，、；` these three.
    """
    return str(t).rstrip().endswith(('，', '、', '；'))


#: 通用规则（台词与动作都过）
# [EN] : general rules (applied to both dialogue and action)
RULES: tuple[Rule, ...] = (
    Rule('empty', '空的（没写出东西来）', _r_empty),
    Rule('junk', '混进了代码/网址之类的残留（不是人说的话）', _r_junk),
    Rule('meta', '写稿的人留的占位话（人物不会这么说）', _r_meta),
    Rule('out_of_play', '出戏了（在跟作者/系统讲话，不是在戏里说话）',
         _r_out_of_play),
    Rule('punct', '标点乱敲（连着一串同样的标点）', _r_punct),
)

#: 心声（`aside`）里"**不是第一人称**"的样子。
#:
#: ★★★ 为什么这条必须有（2026-10-18 实测，某次续写第 21 拍）：
#:   审读自己判对了越界（台账原文：「这是 A 的心里话，B 的视角里不可能出现」），
#:   然后它给的 `改成` 是一句**第三人称旁白 + 转述台词** ——
#:   一句**第三人称旁白 + 转述台词**，比原文更糟。而改写要通过的 `rule_check`
#:   对 `aside` **没有任何专属规则** ⇒ 这句"更糟的改写"原样上屏。
#:   ⇒ 规则层要能零成本判出来：心声里出现"他/她 + 动作"、或以人名开头转述，就是错的。
#: [EN] ★★★ Why this rule must exist (measured 2026-10-18, Mowenlou resume, beat 21): the review
#: [EN] correctly flagged an out-of-bounds aside (ledger: "[越界] this is Xiao Liuzi's inner voice,
#: [EN] impossible in Chen Wang's POV"), then its `改成` was "**Xiao Liuzi tilted his head and asked
#: [EN] me: ...**" -- third-person narration plus reported speech, worse than the original. And
#: [EN] `rule_check` had **no aside-specific rule** => that worse rewrite went straight on screen.
#: [EN] => the rule layer must catch it for free: an inner voice that narrates "he/she + action" or
#: [EN] opens with a name reporting speech is wrong.
_ASIDE_THIRD_PERSON = re.compile(
    r'(?:^|[。！？；\n])\s*'
    r'(?P<who>[\u4e00-\u9fff]{2,4})'
    r'(?:歪着头|抬|低|站|坐|走|看|盯|说|问|答|笑|转身|伸手|把|将|从|向|在)')
#: 心声里**允许**以这些开头的（第一人称视角的常见起句）
# [EN] Openings **allowed** in an inner voice (common first-person starts)
_ASIDE_OK_START = ('我', '这', '那', '他', '她', '他们', '她们', '自己', '怎么',
                   '为什', '难道', '若是', '要是', '可', '但', '不', '别', '该',
                   '借', '偏', '倒', '也')
#: 心声里出现这些 ⇒ 是在**讲别人**（不是"我"的想法）
# [EN] These mean it is **narrating someone else**, not "my" thought.
_ASIDE_REPORTED = ('问我：', '问我:', '对我说', '他问', '她问', '他说', '她说',
                   '心想：', '心里：')


def _r_aside_not_first_person(t: str) -> bool:
    """心声必须像"我"在自言自语；以**人名开头 + 动作动词**就成了旁白。

    ⚠ 只判**开头那一小段**（心声里提到"他/她"是正常的 —— 你在想别人）。
      第一版若判全文，`我看着他垂下眼` 会被误杀。
    [EN] Only the **opening fragment** is judged (mentioning others inside is normal -- you are
    [EN] thinking about them). Judging the whole line would kill "I watched him lower his eyes".
    """
    s = str(t or '').strip()
    if not s:
        return False
    # ⚠ **先查"转述"的硬标记，再判开头**。
    #   反了的话 `他问："这字谁写的。"` 会被"允许以`他`开头"提前放过
    #   （B5 第一版就是这么红的 —— 判据抓出来的）。
    # [EN] ⚠ **Check the "reported speech" marker first, then the opening**. In the other order,
    # [EN] `他问："..."` slips through on "may start with 他" (B5 caught this in its first version).
    if any(x in s for x in _ASIDE_REPORTED):
        return True
    if any(s.startswith(x) for x in _ASIDE_OK_START):
        return False
    return bool(_ASIDE_THIRD_PERSON.match(s))


#: 只对**台词**再加的那条（动作句以逗号结尾是常见的，不算半截话）
# [EN] : the rule added only for **dialogue** (action sentences commonly end with a comma, not a
# [EN] half-finished sentence)
DIALOGUE_RULES: tuple[Rule, ...] = RULES + (
    Rule('tail_comma', '半截话（这句没说完就断了）', _r_tail_comma),
)

#: 心声专属的规则（`kind='aside'` 才会跑）
# [EN] Rules exclusive to inner voice (only run when `kind='aside'`)
ASIDE_RULES: tuple[Rule, ...] = RULES + (
    Rule('aside_third', '心声写成了旁白（"他/她+动作"或转述别人的话）——'
                        '心里话只能是第一人称', _r_aside_not_first_person),
)


def leak_check(text: str, world, who: str) -> str:
    """这句话有没有**说出别人的秘密**（2026-10-18，信息差那一层）。

    为什么必须在规则层做（而不是只写在提示词里）：`Agent` 的提示词已经写了
    "不许替他们说破"，但**提示词写了 ≠ 生效**（本项目记过多次）。这里零成本兜底。

    ⚠ 只在**真的说了**的时候报（`WorldState.leaks` 判"最长公共片段 ≥5 字"），
      而且**知情者说了不算** —— 他知道，他说出来是正常的。
    ⚠ 判出来只**标类别**，不改写：改写需要理解"这句话的意思"，那是审读模型的事。
    [EN] Does this line **state someone else's secret** (2026-10-18, the information-asymmetry
    [EN] layer). Why it must be in the rule layer: the actor prompt already says "never tell their
    [EN] secret for them", but **written in a prompt != in effect** (recorded several times here).
    [EN] ⚠ Only reports a real leak (`WorldState.leaks`: longest shared run >= 5 chars), and a
    [EN] knower stating it does **not** count. ⚠ It only flags a category; rewriting needs meaning,
    [EN] which is the review model's job.
    """
    try:
        owner = world.leaks(str(text or ''), str(who or ''))
    except Exception:                                            # noqa: BLE001
        return ''
    if not owner:
        return ''
    return f'说出了{owner}的秘密（他不在知情者里，说出来就是越界）'


#: 判"说破了需求"的最短公共片段（字）。
#: ⚠ 比 `_LEAK_MIN`（5）**宽一格**是刻意的：需求通常写在人物卡里是一句完整的话
#:   （"想被人当成一个人看"），而台词里说破它时往往**照抄其中半句**。
#:   用 4 能抓到"当成一个人看"，5 会漏掉"被人当成一个人"这种少一字的变体。
#:   —— 代价是误报风险略高，但误报只**记一条台账**（`why`），
#:   真正拦不拦由 `SCRIPT_REVIEW_STRICT` 定，不会静默吃字。
# [EN] Shortest shared run (chars) that counts as "the need said out loud". ⚠ One char looser than
# [EN] `_LEAK_MIN` deliberately: the need is a full sentence in the card, and a line that gives it
# [EN] away usually copies half of it. 4 catches "treated as a person", 5 misses one-char variants.
# [EN] The cost is a slightly higher false-positive rate, but a false positive only **records a
# [EN] ledger row** (`why`); whether it blocks is decided by `SCRIPT_REVIEW_STRICT`.
_NEED_MIN = 4


# ══════════════════════════════════════════════════════════════════
#  需求不许说破（2026-10-18，专业论述 #4）
# [EN] The need must not be said out loud (2026-10-18, #4)
# ══════════════════════════════════════════════════════════════════
from world.state import _shared_run            # noqa: E402  （同一份实现，别复制第二份）


def need_check(text: str, world, who: str) -> str:
    """这句话有没有**把人物自己的"需求"说破**（2026-10-18，专业论述 #4 欲望 vs 需求）。

    为什么必须有一条规则兜底：`need`（他真正缺的东西）给到演员时，
    提示词里已经明写"不许说出口、不许让心声总结"，但**提示词写了 ≠ 生效**
    （本项目记过多次）。而"说破需求"是**最容易发生**的一种失败 ——
    模型的默认行为就是把人物的动机总结成一句漂亮话（"他其实只是想被当成一个人"）。

    ⚠ 判法极保守：只认"秘密内容本身出现在台词里"（最长公共片段 ≥ `_NEED_MIN`）。
      不判"意思相近"，不判"暗示" —— 那些交给审读模型。
      **宁可漏，不可误报**：误报会把正常台词拦掉（用户最恨的那种）。
    ⚠ 只对**台词与心声**判（动作句里不可能"说破"）。
    [EN] Does this line **say the character's own need out loud** (2026-10-18, #4 want vs need).
    [EN] Why a rule backstop: when `need` is handed to the actor, the prompt already says "never say
    [EN] it, never summarise it", but **written in a prompt != in effect** (recorded several times).
    [EN] Saying the need out loud is the **most likely** failure -- the model's default is to summarise
    [EN] the motive into a nice line ("he just wants to be treated as a person").
    [EN] ⚠ Deliberately conservative: only the **need's own words** appearing in the line (longest
    [EN] shared run >= `_NEED_MIN`). No "similar meaning", no hints -- those go to the review model.
    [EN] **Better to miss than to false-positive**: a false positive blocks a normal line.
    """
    try:
        ps = (getattr(world, 'people', None) or {}).get(str(who or '')) if world is not None else None
        need = str(getattr(ps, 'need', '') or '').strip() if ps else ''
    except Exception:                                            # noqa: BLE001
        return ''
    if len(need) < 4:
        return ''
    t = str(text or '')
    if not t:
        return ''
    # 复用信息差那条"最长公共片段"的判法（同一个工具，不另写一份）
    # [EN] Reuse the shared-run helper from the information-asymmetry check (one implementation).
    try:
        if _shared_run(need, t) >= _NEED_MIN:
            return '把自己的「需求」说破了（那是作者替人物做总结，只能靠选错露出来）'
    except Exception:                                            # noqa: BLE001
        return ''
    return ''


def rule_check(text: str, *, kind: str = '') -> str:
    """跑一遍规则层。**通过返回空串**，不通过返回那句话（给人看的原因）。

    这是唯一入口 —— `sim/loop` 的闸门与判据都调它，
    "什么算形式上的错"只有这一处定义。
    
        English:
    Run the rule layer once. **Return empty string if it passes**, otherwise return that sentence
    (the reason for humans to see).
        This is the only entry point —— the gate and criteria of `sim/loop` both call it,
        "what counts as a formal error" is defined only here.
    """
    t = str(text or '')
    k = str(kind or '')
    # ★★★ 三类各用一套：台词多查"半截话"，心声多查"第一人称"。
    #   ⚠ 以前只有"台词 / 其余"两套 ⇒ 心声落到"其余"那一套，**第一人称这条永远没人查**
    #     （实测：审读把一句旁白当成"合格的心声改写"放行了）。
    # [EN] ★★★ Three kinds, three rule sets: dialogue adds "half sentence", inner voice adds
    # [EN] "first person". ⚠ There used to be only "dialogue / the rest", so inner voice fell into
    # [EN] "the rest" and **the first-person rule was never checked** (measured: the review let a
    # [EN] narration line through as a valid aside rewrite).
    rules = (DIALOGUE_RULES if k == 'dialogue'
             else ASIDE_RULES if k == 'aside' else RULES)
    for r in rules:
        try:
            if r.hit(t):
                return r.why
        except Exception:                                        # noqa: BLE001
            continue
    return ''


# ══════════════════════════════════════════════════════════════════
#  语义级重复：**程序先挑候选，模型只管判**（2026-10-18）
# [EN] Semantic repetition: **the program proposes candidates, the model only judges**
# ══════════════════════════════════════════════════════════════════
#  为什么要有这一层（2026-10-18 五轮实测的直接结论）
#  --------------------------------------------------
#  文本层的"逐字重复"已经由三处护栏管住了（台词 `_said` / 动作 `_last_action` /
#  环境句池）。**剩下的全是语义重复**：
#    · 「你觉得我是个什么样的人？」→「我是个好人吧？」（换了个说法，同一句自白）
#    · 「叶子端酒壶站门口」→「一壶酒从半开纸门推进来」（同一个动作，第二次）
#    · 「眼盯他侧脸」→「眼没离他脸」→「盯他嘴」（同一个姿态，三次）
#  这些的**文字相似度只有 0.3–0.6**，`near_same`（0.86）抓不到；
#  而"要靠读懂意思才判得出"这件事，只有模型能做。
#
#  但**别指望便宜模型自己去 40 行历史里搜**：它的输出预算只有 100–200 token，
#  让它"通读并找出重复"实测是漏的。所以分工是：
#    · **程序**（本模块，零成本）把"可能是同一件事"的**配对**挑出来，
#      连"像哪一句、像到什么程度"一起递给它；
#    · **模型**只回答"这几对里哪些真的是同一件事"。
#  这是把"检索"（可计算）与"判断"（需要理解）分开，与 `_pick_ambient_line`
#  "摊开候选再挑"是同一条思路。
#
# [EN] Why this layer exists (the direct conclusion of five measured runs on 2026-10-18):
# [EN] verbatim repetition is already handled by three guards (dialogue `_said` / action
# [EN] `_last_action` / ambient pool). What is left is **semantic** repetition: the same
# [EN] confession reworded, the same action performed twice, the same posture three times. Its
# [EN] text similarity is only 0.3-0.6, below `near_same` (0.86), and only a model can judge it.
# [EN] But **do not expect a cheap model to search 40 history lines itself** -- its output budget
# [EN] is 100-200 tokens and measured recall was poor. So the split is: the **program** (this
# [EN] module, zero cost) proposes the pairs along with "which line does it resemble and how
# [EN] strongly", and the **model** only answers "which of these really are the same thing".
# [EN] That separates retrieval (computable) from judgment (needs understanding).

#: 裁决的**类别**（模型报，程序按它决定"改写 / 拦下 / 只记"）。
#: ⚠ 认不出的类别一律归 `其他` —— 审读是"宁可漏不可误杀"的岗。
# [EN] The **category** of a verdict (reported by the model; the program uses it to decide
# [EN] rewrite / block / record-only). ⚠ Unrecognized categories fall back to `其他`.
CAT_DUP = '重复'
CAT_BOUND = '越界'
CAT_OTHER = '其他'

#: 挑候选的门槛。**这是"召回"门槛，不是"判决"门槛** ——
#: 挑多了只是让模型多看两行字（便宜），挑漏了才是真损失。
#: 0.40 是拿《雪国》三份实测正文**逐对量**出来的（`repeat-fix` / `repeat-fix2` /
#: `repeat-fix4` 的全部相邻句对）：
#:   · 真重复对：0.98（差一个"还"字）、0.82（同一句说了两遍）、0.46（「你这人哪」×3）；
#:   · 无关对最高 0.39（叶子影子 → 影子停住，评委也说"三次写同一件事"）；
#:   · **0.42 那一对是"叶子问 / 驹子答"** —— 形状像、其实是问答。
#: ⇒ 0.40 以上的区间**真假混在一起**，这正是"必须让模型来判"的证据；
#:   程序只负责别把真的漏掉。
# [EN] Candidate threshold. **Recall, not verdict** -- extra pairs cost the model two lines to
# [EN] read; missing one is the real loss. 0.40 comes from measuring **every adjacent pair** in the
# [EN] three Snow Country runs: true duplicates at 0.98 / 0.82 / 0.46, the highest unrelated pair at
# [EN] 0.39, and a 0.42 pair that was a question and its answer (looks alike, isn't a repeat).
# [EN] => the range above 0.40 mixes true and false, which is exactly why the model must judge;
# [EN] the program only has to avoid missing the true ones.
DUP_SEED_THR = 0.40


def split_line(line: str) -> tuple[str, str, str]:
    """把 `ScriptLog.Rec.line()` 那一行拆回 `(kind, who, text)`。

    台账给模型的是一整行字（`〔action·驹子〕伏在火钵边…`）——
    要比"是不是同一件事"得先把"谁"和"说了什么"分开，否则名字会算进相似度里
    （同一个人的两句话天然共享名字 ⇒ 假重复）。
    [EN] Split the line `ScriptLog.Rec.line()` back into `(kind, who, text)`. The ledger hands
    [EN] the model one whole line; comparing "is this the same thing" requires separating who from
    [EN] what, otherwise the name counts toward similarity (two lines by the same person share the
    [EN] name and look falsely alike).
    """
    s = str(line or '').strip()
    m = re.match(r'^〔([^〕]*)〕(.*)$', s)
    if not m:
        return '', '', s
    head, text = m.group(1), m.group(2)
    bits = head.split('·', 1)
    return bits[0].strip(), (bits[1].strip() if len(bits) > 1 else ''), text.strip()


def look_alike(a: str, b: str) -> float:
    """两句话"看起来有多像"（0~1）：**字面顺序相似**与**用词重合**取大的那个。

    为什么要取两个而不是一个（实测）：
      · 只算 `difflib` 顺序比：「眼盯他侧脸」/「盯他嘴」≈ 0.45（还行），
        但「伏在火钵边，头发散了」/「头发散在颊侧，伏到火钵边」会被调序打分打低；
      · 只算 bigram 重合：「一壶酒从纸门推进来」/「端酒壶站门口」重合很低，
        可读者一看就知道是同一件事（都是"叶子的酒"）。
      ⇒ 两个都算、取大值，牺牲一点精度换召回（判决交给模型）。
    [EN] How alike two lines look (0..1): the larger of **sequence similarity** and **word
    [EN] overlap**. Two measures because one alone misses a whole class (reordered sentences, or
    [EN] reworded actions that share key nouns). Take the max, trade precision for recall -- the
    [EN] model makes the actual call.
    """
    na, nb = norm_line(a), norm_line(b)
    if len(na) < 4 or len(nb) < 4:
        return 0.0
    seq = difflib.SequenceMatcher(None, na, nb).ratio()
    return round(max(seq, similarity(na, nb)), 3)


def dup_candidates(items: list[dict], history: list[str], *,
                   thr: float = DUP_SEED_THR,
                   max_pairs: int = 6) -> list[dict]:
    """从"这一批新内容 × 已上屏历史 × 批内互比"里挑出**可能是同一件事**的配对。

    返回的行（给模型读，也进台账）：
      `序号` 这一批里的第几条 · `文本` 它自己
      `像这句` 历史里（或同批更早）那句 · `谁` 说话/做事的人
      `相似` 0~1 · `同一个人` 是不是同一人干的 · `同批` 是不是本批内部的重复

    ⚠ **每个条目最多留一条**配对（分数最高的那条）—— 一个条目挂五条候选会把
      预算挤光，而模型只需要知道"它跟哪一句最像"。
    ⚠ 批内互比**也要做**：实测有一整拍里"叶子送酒"出现两次（`repeat-fix2`），
      两条都在同一批里，只跟历史比是永远看不出来的。
    [EN] Pick the pairs that may be "the same thing" from (this batch x on-screen history x
    [EN] intra-batch). Returns rows for the model: index, its own text, the line it resembles,
    [EN] who, similarity, same-person flag, intra-batch flag.
    [EN] ⚠ **At most one pair per item** (the highest scoring) -- five candidates per item would
    [EN] eat the budget, and the model only needs "which line does it resemble most".
    [EN] ⚠ **Intra-batch comparison is required**: measured, one beat had Yoko delivering wine
    [EN] twice, both inside the same batch -- comparing only against history can never see it.
    """
    hist: list[tuple[str, str, str]] = [split_line(x) for x in (history or [])]
    out: list[dict] = []
    done: list[tuple[str, str, str]] = []        # 本批已处理的（类型, 谁, 文本），给批内互比用
    for it in (items or []):
        try:
            no = int(it.get('序号'))
        except Exception:                                        # noqa: BLE001
            continue
        kind = str(it.get('类型') or '')
        who = str(it.get('谁') or '').strip()
        text = str(it.get('文本') or '').strip()
        if len(norm_line(text)) < 6:
            continue
        best: dict | None = None
        # ⚠ **只跟同类型比**（动作↔动作、台词↔台词）：动作句与台词句本来就不会"重复"，
        #   混着比只会把"叶子问 / 驹子答"这种噪音当候选（实测 0.42，见 `DUP_SEED_THR`）。
        # [EN] ⚠ **Same kind only** (action vs action, dialogue vs dialogue): an action and a
        # [EN] line can never be "the same act", and mixing them only produces noise such as the
        # [EN] measured 0.42 question/answer pair.
        for hk, hw, ht in hist:
            if kind and hk and hk != kind:
                continue
            score = look_alike(text, ht)
            if score < thr:
                continue
            if best is None or score > best['相似']:
                best = {'相似': score, '像这句': ht, '同一个人': bool(who and hw == who),
                        '同批': False}
        for pk, pw, pt in done:
            if kind and pk and pk != kind:
                continue
            score = look_alike(text, pt)
            if score < thr:
                continue
            if best is None or score > best['相似']:
                best = {'相似': score, '像这句': pt,
                        '同一个人': bool(who and pw == who), '同批': True}
        done.append((kind, who, text))
        if best is None:
            continue
        best.update({'序号': no, '谁': who, '文本': text})
        out.append(best)
    # 排序：**同一个人**的先（同一个人重做同一件事才是典型复读），再按相似度
    # [EN] Order: **same person** first (one person redoing the same thing is the typical case),
    # [EN] then by similarity.
    out.sort(key=lambda r: (not r.get('同一个人'), -float(r.get('相似') or 0)))
    return out[:max_pairs]


def category_of(row: dict) -> str:
    """这条裁决说的是哪一类问题（`重复` / `越界` / `其他`）。

    为什么要分（2026-10-18）：三类问题的**处置不一样**，不能一刀切：
      · `重复` —— 能改写就改写；**改不动就放行**（删掉会把这一拍删空，
        这是 2026-10-18 第三轮实测的教训：禁而不推 ⇒ 全员 `wait` 12 次）；
      · `越界` —— 踩了人物红线 / 世界铁律，改写优先，改不动可以拦；
      · `其他` —— 沿用老规矩（能改就改，改不动按 `SCRIPT_REVIEW_STRICT` 拦）。
    ⚠ 模型写的类别是自由文本（"重复（同一动作两次）"），所以按**关键词**认，
      认不出归 `其他`（宁可漏）。
    [EN] Which kind of problem a verdict describes. Why it matters (2026-10-18): the three need
    [EN] **different handling** -- repetition should be rewritten when possible and **let through
    [EN] otherwise** (blocking empties the beat, the lesson of the third measured round), an
    [EN] out-of-bounds line hits a character red line or world rule and may be blocked, everything
    [EN] else follows the old rule. ⚠ The model's category is free text, so match on keywords and
    [EN] fall back to `其他`.
    """
    raw = ''
    for k in ('类别', '分类', '类型'):
        v = str(row.get(k) or '').strip()
        if v:
            raw = v
            break
    if not raw:
        return CAT_OTHER
    if any(w in raw for w in ('重复', '复读', '重演', '炒冷饭', '同一件事', '原地打转')):
        return CAT_DUP
    if any(w in raw for w in ('越界', '红线', '铁律', '违规', '出格', '人设崩', '破功')):
        return CAT_BOUND
    return CAT_OTHER


def verdicts_of(note: Any) -> dict[int, dict]:
    """把审读 Agent 的产出（`CrewNote.data['裁决']`）整理成 `{序号: 裁决}`。

    ⚠ **认不出的条目一律"不出现"**（= 当它通过）：
      审读是"宁可漏不可误杀"的岗，模型少给一条裁决时，
      正确做法是放行那一条，而不是把它当成"没过"而拦下。
    
        English:
        ⚠ **Unrecognizable entries are always "absent"** (= treat as passed):
          review is a post of "better to miss than to wrongly kill"; when the model gives one fewer verdict,
          the correct thing is to let that one through, not to treat it as "not passed" and block it.
    """
    out: dict[int, dict] = {}
    try:
        rows = (note.data or {}).get('裁决') if note is not None else None
    except Exception:                                            # noqa: BLE001
        rows = None
    for row in (rows or []):
        if not isinstance(row, dict):
            continue
        try:
            n = int(row.get('序号'))
        except Exception:                                        # noqa: BLE001
            continue
        out[n] = row
    return out


def is_pass(row: dict) -> bool:
    """这条裁决算不算"过"。`过` 字段缺省时**算过**（同上：宁可漏）。
        English:
    Whether this verdict counts as "passed". When the `过` field is missing, **count as passed**
    (same as above: better to miss).
    """
    v = row.get('过')
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ('true', '1', 'yes', '是', '通过', '过')
    if v is None:
        return True
    return bool(v)


def fix_of(row: dict) -> str:
    """模型给的改写（没有就空串）。
        English:
    The rewrite given by the model (empty string if none).
    """
    for k in ('改成', '改写', '建议'):
        v = str(row.get(k) or '').strip()
        if v:
            return v
    return ''


def why_of(row: dict) -> str:
    for k in ('问题', '原因', '理由'):
        v = str(row.get(k) or '').strip()
        if v:
            return v[:120]
    return ''


def stamp() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S')
