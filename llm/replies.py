# -*- coding: utf-8 -*-
"""把 LLM 回复变成「可用结果」的公共入口：解析 → 截断就重试 → 还不行就抢救。

## 为什么要有这个模块

从 2026-10-06 起，同一类故障在开卷管线里**反复出现**，每次表现都不一样、
但根子都是同一句话：**模型的输出撞上了 `max_tokens`，而调用方没接住。**

| 日期 | 哪一步 | 表现 |
|---|---|---|
| 10-06 | `extract`（提取设定） | 截在半句话里 → 整份设定换成空骨架，**7 个人物全丢** |
| 10-06 | `progress`（进度表） | 数组被截断 → `extract_json_list` 返回空表 → **静默变 0 个节点** |
| 10-06 | `optimize_review`（AI 优化体检） | 800 token **全被思考内容吃掉** → 正文为空 → **界面上 AI 一句话都没说** |

前两次是"**修一个地方**"，这次不再逐个打补丁，而是把这件事收成**一个函数**：

    reply = await ask("cheap", messages, purpose="progress", want=list, max_tokens=3000)

它按固定顺序做四件事，每一步都会在 `reply.notes` 里留下**给人看的说明**：

1. **正常解析**（严格：`extract_json` / `extract_json_list`，按 `want` 选）；
2. 拿不到东西 → **重试一次**：上限翻倍 + 追加一句"上一次被截断了，请写短、要完整"；
   空正文（推理模型把额度吃在思考里）也走这条，但换一句"直接给正文、不要思考过程"；
3. 还拿不到 → **按「最长可闭合前缀」抢救**（`repair_json` / `repair_json_list`），
   能救回多少算多少，并明确标注"可能不完整"；
4. 连抢救都没有 → `ok=False`，`value` 是调用方给的兜底值。

## ⚠ 两条不许改的规矩

1. **"空的容器"不算拿到东西**。`extract_json_list()` 解析失败时返回的**就是 `[]`**，
   只看 `isinstance(v, list)` 会让重试与抢救变成**死代码**（踩过，见 `jsonio.parse_or_repair`）。
2. **重试只做一次**。重试是花钱的，而且"再试一次就会好"这个假设只对"预算不够"成立；
   格式真的错、模型真的不听话时，第三次也一样。宁可把失败**讲清楚**，别偷偷烧钱。

## 谁用、谁不用

`progress` / `opening`（数组）· `optimize_review` / `optimize_apply`（正文与 JSON）·
`style` / `genre` 用这个。

`extract_settings` **故意不用**（2026-10-06 的说明）：它自带等价的三级处理，而且是
**唯一需要「严格解析失败」这个信号**的地方（要靠"解析失败 + truncated"去触发重试，
`repair_json` 一救回来重试就永远不发生），另外它把提示攒进 `_NOTES` 由
`ingest.pipeline` 折进界面日志，有自己的一套接线。**别顺手把它改成用本模块** ——
那会同时动到 6 条已有断言在盯的提示文案。

English:
The common entry point that turns an LLM reply into a "usable result": parse → on truncation
retry → still no good then rescue.
## Why this module exists
Since 2026-10-06, the same class of failure has **repeatedly occurred** in the opening pipeline,
each time with a different symptom,
but the root is always the same sentence: **the model's output hit `max_tokens`, and the caller
didn't catch it.**
| Date | Which step | Symptom |
|---|---|---|
| 10-06 | `extract` (extract settings) | truncated mid-sentence → the whole settings replaced by an empty skeleton, **all 7 characters lost** |
| 10-06 | `progress` (progress table) | array truncated → `extract_json_list` returns empty list → **silently becomes 0 nodes** |
| 10-06 | `optimize_review` (AI optimization review) | 800 tokens **entirely eaten by thinking content** → body empty → **the UI showed not a single word from the AI** |
The first two times were "**fix one place**"; this time we no longer patch one by one, but
consolidate this into **one function**:
    reply = await ask("cheap", messages, purpose="progress", want=list, max_tokens=3000)
It does four things in a fixed order, and each step leaves a **human-readable note** in
`reply.notes`:
1. **Normal parse** (strict: `extract_json` / `extract_json_list`, chosen by `want`);
2. Got nothing → **retry once**: cap doubled + append "last time it was truncated, please write shorter and complete";
   empty body (reasoning model spent the budget on thinking) also takes this path, but with a different sentence "give the body directly, no thinking process";
3. Still got nothing → **rescue by "longest closable prefix"** (`repair_json` / `repair_json_list`),
   save as much as possible, and clearly mark "may be incomplete";
4. Even rescue fails → `ok=False`, `value` is the fallback value provided by the caller.
## ⚠ Two rules that must not be changed
1. **An "empty container" doesn't count as getting something**. `extract_json_list()` returns **exactly `[]`** on parse failure,
   checking only `isinstance(v, list)` would make retry and rescue **dead code** (been there, see `jsonio.parse_or_repair`).
2. **Retry only once**. Retrying costs money, and the assumption "one more try and it'll be fine" only holds for "budget too small";
   when the format is genuinely wrong or the model genuinely won't obey, a third time is the same. Better to **explain the failure clearly** than quietly burn money.
## Who uses it, who doesn't
`progress` / `opening` (arrays) · `optimize_review` / `optimize_apply` (body and JSON) ·
`style` / `genre` use this.
`extract_settings` **deliberately doesn't use it** (note from 2026-10-06): it has its own
equivalent three-tier handling, and is
**the only place that needs the "strict parse failed" signal** (it relies on "parse failure +
truncated" to trigger retry,
once `repair_json` rescues it the retry would never happen), plus it accumulates notes into
`_NOTES` which
`ingest.pipeline` folds into the UI log, having its own wiring. **Don't casually change it to
use this module** --
that would simultaneously touch the prompt texts watched by 6 existing assertions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from i18n import t
from llm.credit import OutOfCredit
from llm.router import llm
from util.jsonio import parse_or_repair

_LOG = logging.getLogger("nws.llm.replies")

# 重试时的上限倍数与硬顶（防跑飞）
# [EN] Retry upper-bound multiplier and hard cap (prevent runaway)
RETRY_FACTOR = 2.0
MAX_TOKENS_CAP = 16000

# 重试时追加的那句话（按想要的东西分三种）。
# ⚠ 这些是**给模型看的**，不是给人看的，所以不进 i18n —— 与提示词保持同一种语言
#   （输出语言由 `util/outlang` 的那句指令负责）。
# [EN] The sentence appended on retry (three kinds depending on what is wanted).
# [EN] ⚠ These are **for the model to read**, not for humans, so they don't go into i18n -- keep the
# [EN] same language as the prompt
# [EN] (output language is handled by the instruction in `util/outlang`).
_RETRY_HINT = {
    dict: ("\n\n⚠ 上一次你的输出被长度上限截断了，JSON 不完整。请**重写一遍**："
           "每个字段都写得更短，务必输出**完整且合法**的 JSON 对象，不要有多余文字。"),
    list: ("\n\n⚠ 上一次你的输出被长度上限截断了，JSON 不完整。请**重写一遍**："
           "缩短每段文字，务必输出**完整且合法**的 JSON 数组，不要有多余文字。"),
    "text": ("\n\n⚠ 上一次你没有输出正文内容（额度被思考过程占掉了）。"
             "这一次请**直接给出正文本身**，不要输出任何思考、分析、解释或开场白。"),
}

_WANT_LABEL = {dict: "JSON 对象", list: "JSON 数组", "text": "正文"}

# 「正文为空」时**追加**的一句。截断与空正文是**两种病，药不一样**：
# 截断是"写太长了"，要它写短；空正文是"额度整份花在思考上"，要它别思考。
# 用错那一句等于没提醒（2026-10-06：progress_eval 空正文却收到"写短点"的提示，
# 重试照样一个字节都不给）。
# [EN] The sentence **appended** when "body is empty". Truncation and empty body are **two different
# [EN] illnesses, different medicine**:
# [EN] Truncation is "wrote too long", tell it to write shorter; empty body is "the whole budget was
# [EN] spent on thinking", tell it not to think.
# [EN] Using the wrong sentence is as good as no reminder (2026-10-06: progress_eval had empty body but
# [EN] received the "write shorter" prompt,
# [EN] and the retry still didn't give a single byte).
_EMPTY_HINT = ("\n\n⚠ 上一次你的额度**整份花在思考过程上**了，正文一个字都没有。"
               "这一次请**直接输出答案本身**，不要写任何思考、分析或解释。")


@dataclass
class Reply:
    """一次「我要的东西」的完整答卷（含怎么拿到的，供界面讲给用户听）。
        English:
    A complete answer sheet for one "what I want" (including how it was obtained, for the UI to tell
    the user).
    """

    value: Any = None
    raw: str = ""
    meta: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    ok: bool = True
    salvaged: bool = False
    retried: bool = False
    calls: int = 0

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    @property
    def empty(self) -> bool:
        return self.value is None or (hasattr(self.value, "__len__")
                                      and not self.value)


def _trunc_reason(meta: dict) -> str:
    """「为什么不够用」的短说明（含思考内容时要明说，不然越查越糊涂）。
        English:
    A short explanation of "why it's not enough" (must state clearly when thinking content is
    involved, otherwise the more you investigate the more confused you get).
    """
    return t("（含思考内容）") if meta.get("has_reasoning") else ""


async def ask(
    tier: str,
    messages: list[dict],
    *,
    purpose: str,
    want: Any = "text",
    max_tokens: int = 2000,
    temperature: float = 0.2,
    json_mode: bool = False,
    retry: bool = True,
    salvage: bool = True,
    default: Any = None,
    min_chars: int = 0,
    no_think: bool | None = None,
) -> Reply:
    """要一份「可用结果」：解析 → 重试 → 抢救。参数见模块头注释。

    `want`：`dict`（JSON 对象）/ `list`（JSON 数组）/ `"text"`（纯正文，只要非空）。
    `default`：连抢救都没结果时放进 `value` 的兜底值。
    `ok` 只表示"有没有拿到东西"，与 `default` 是不是空无关。
    `min_chars`：**只对 `want="text"` 有意义** —— 正文短于这个字数就当成"没拿到"，
    一样走重试。**光判"非空"是不够的**：这次事故里模型确实吐了几个字（正文被思考
    挤到只剩开头），判非空就放行了，用户拿到的还是一段没用的残句。
    `no_think`：透传给 `llm.chat()`。`None` = 由那边按 `NO_THINK_PURPOSES` 决定
    （**推荐留 `None`**，别在调用点重复一遍那张表）。
    
        English:
    Want a "usable result": parse → retry → rescue. See the module header comment for parameters.
        `want`: `dict` (JSON object) / `list` (JSON array) / `"text"` (plain body, only needs to be non-empty).
        `default`: the fallback value put into `value` when even rescue yields nothing.
        `ok` only indicates "whether something was obtained", unrelated to whether `default` is empty.
        `min_chars`: **only meaningful for `want="text"`** -- if the body is shorter than this character count it's treated as "got nothing",
        and also goes through retry. **Judging only "non-empty" is not enough**: in this incident the model did spit out a few characters (body squeezed by thinking
        down to just the beginning), and judging non-empty would let it pass, so the user still gets a useless fragment.
        `no_think`: passed through to `llm.chat()`. `None` = decided on that side by `NO_THINK_PURPOSES`
        (**recommended to leave `None`**, don't repeat that table at the call site).
    """
    label = _WANT_LABEL.get(want, "结果")
    rep = Reply(value=default)

    def _usable(v: Any) -> bool:
        """拿到的这个东西**算不算数**。空容器与过短的正文都不算。
                English:
        Whether this thing obtained **counts or not**. Empty containers and overly short bodies don't
        count.
        """
        if v is None:
            return False
        if want == "text":
            return len(str(v).strip()) >= max(1, min_chars)
        return bool(v)

    async def _once(msgs: list[dict], budget: int) -> None:
        rep.raw, rep.meta = await llm.chat(
            tier, msgs, purpose=purpose, json_mode=json_mode,
            temperature=temperature, max_tokens=budget, return_meta=True,
            no_think=no_think)
        rep.calls += 1

    # ① 第一次
    # [EN] ① First time
    try:
        await _once(messages, max_tokens)
    except OutOfCredit:
        # ★★★ **"没钱了"不在这里降级**（2026-10-25）：本模块的职责是"这一次拿到了没有"，
        #   而欠费不是"这一次没拿到"，是"再试一万次也一样"。
        #   把它写成 `ok=False` 的话，调用方只会当成普通失败——于是这一拍降级成
        #   "人物什么都没做"，而用户永远看不到"去充值"那句话。
        #   ⇒ 原样往上抛，让能决定"停下"的那一层处理。
        # [EN] ★★★ **"Out of money" is not degraded here** (2026-10-25): this module's job is
        # [EN] "did this call get anything", and billing is not "got nothing this time", it is "a
        # [EN] million more tries give the same". Writing `ok=False` would make callers treat it as
        # [EN] an ordinary failure -- the beat degrades to "the characters did nothing" and the user
        # [EN] never sees the "go top up" line. => re-raise verbatim.
        raise
    except Exception as e:                                        # noqa: BLE001
        _LOG.error("调用失败（%s）: %s", purpose, e)
        rep.ok = False
        rep.note(t("模型调用失败：{err}", err=e))
        return rep

    value, salvaged = parse_or_repair(rep.raw, None, want=want)
    if _usable(value):
        rep.value, rep.salvaged, rep.ok = value, salvaged, True
        if salvaged:
            rep.note(t("输出不完整，已按「最长可闭合前缀」抢救"
                       "（末尾内容可能缺失，请核对）"))
        return rep

    # ② 拿不到东西 → 重试一次（上限翻倍 + 说清上次哪里不行）
    # [EN] ② Got nothing → retry once (cap doubled + explain clearly what was wrong last time)
    why = t("被长度上限截断") if rep.meta.get("truncated") else (
        t("正文为空（额度被思考内容占掉）") if rep.meta.get("has_reasoning")
        else (t("正文太短，只有 {n} 字", n=len(str(value or "").strip()))
              if want == "text" and value
              else t("没能解析出{label}", label=t(label))))
    if retry:
        bigger = min(int(max_tokens * RETRY_FACTOR), MAX_TOKENS_CAP)
        rep.note(t("模型没给出可用的{label}（{why}）→ 已按 {bigger} token 上限重试一次",
                   label=t(label), why=why, bigger=bigger))
        hint = _RETRY_HINT.get(want, _RETRY_HINT["text"])
        if rep.meta.get("empty_output"):
            hint += _EMPTY_HINT
        try:
            await _once(list(messages) + [{"role": "user", "content": hint}], bigger)
            rep.retried = True
        except OutOfCredit:
            # 重试也一样：欠费不重试、不降级（理由见上面第一次那一段）。
            # [EN] Same on retry: billing is neither retried nor degraded (see the first block).
            raise
        except Exception as e:                                    # noqa: BLE001
            _LOG.error("重试失败（%s）: %s", purpose, e)
            rep.note(t("重试也失败了：{err}", err=e))
            rep.ok = False
            return rep
        value, salvaged = parse_or_repair(rep.raw, None, want=want)
        if _usable(value):
            rep.value, rep.salvaged, rep.ok = value, salvaged, True
            if salvaged:
                rep.note(t("重试后仍不完整，已按「最长可闭合前缀」抢救"
                           "（末尾内容可能缺失，请核对）"))
            return rep

    # ③ 抢救（截断留下的半截内容也能救回前半段）
    # [EN] ③ Rescue (truncated half-content can also have its first half saved)
    if salvage:
        from util.jsonio import repair_json, repair_json_list
        loose = repair_json if want is dict else (
            repair_json_list if want is list else None)
        if loose is not None:
            best = loose(rep.raw, None)
            if best:
                rep.value, rep.salvaged, rep.ok = best, True, True
                rep.note(t("输出不完整，已按「最长可闭合前缀」抢救"
                           "（末尾内容可能缺失，请核对）"))
                return rep

    # ④ 彻底没拿到
    # [EN] ④ Completely got nothing
    _LOG.warning("拿不到可用的%s（purpose=%s），原始文本：%s",
                 label, purpose, str(rep.raw)[:200])
    rep.ok = False
    rep.note(t("模型没有返回可用的{label} —— 原始文本已写进对话日志，"
               "可到「天机 · 日志」里查看", label=t(label)))
    return rep
