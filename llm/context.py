# -*- coding: utf-8 -*-
"""上下文分层裁剪（设计稿 §2.4「AI 工程质量」）。

设计稿原文：
    上下文分层裁剪：**固定前缀**（总世界观+人格固定层+类型档案摘要，可缓存）
    → **半固定**（风格卡+考据卡+状态层）→ **动态**（记忆 topK+近期事件+对话）；
    超 `MAX_CONTEXT_TOKENS` **从动态层尾部往前裁**，**固定前缀永不裁**。

为什么必须做
------------
不做的话，上下文只跟"这个人有多少记忆、这场戏说了多少话"一起长：
跑到第十天，一个人物的 prompt 会带上几十条记忆和整场对话，
token 账单按天翻倍，而且**最先被挤掉的恰好是世界观和人格** ——
轻则人物开始出戏，重则模型把前缀丢掉只回一句"我在等"。

三层怎么分（`LAYERS`）
----------------------
  · `fixed` —— 总世界观 / 顶级规则 / 人格固定层 / 类型档案。**永不裁**。
    它是"这个人是谁、这个世界是什么样"，裁了就不是同一个人了。
  · `semi`  —— 风格卡 / 考据卡 / 状态层（场景·时间·天气·在场·目标金字塔）。
    **不主动裁**，只在动态层被剥光后仍超预算时才动，且**从尾部**裁。
  · `dyn`   —— 记忆 topK / 近期事件 / 对话。**优先裁**。

裁的方向（照设计稿「从动态层尾部往前裁」）
------------------------------------------
把 `dyn` 写成一个**有序块列表**，块内每行都排成"**尾部最不重要**"：

  · 记忆块 —— 按重要性 × 新近度**升序**（最不重要的排最后）→ 先走的就是它；
  · 事件 / 对话块 —— **新的在前、旧的在后** → 先走的总是最旧的那些。

于是"从尾部往前裁"这一条实现下来既是**物理上的从尾往前**（简单、可断言），
又是合理的取舍（丢最不重要的 / 丢最旧的），不会出现"把刚说的话删了"
这种荒唐结果。每裁掉一段都记一笔（`trimmed`），因为**静默少喂**是事故。

English:
Layered context trimming (design doc §2.4 "AI engineering quality").
Original text of the design doc:
    Layered context trimming: **fixed prefix** (global worldview + fixed persona layer + type profile summary, cacheable)
    → **semi-fixed** (style card + research card + state layer) → **dynamic** (memory topK + recent events + dialogue);
    when over `MAX_CONTEXT_TOKENS`, **trim from the tail of the dynamic layer backward**, and **the fixed prefix is never trimmed**.
Why it must be done
-----------
If not done, the context only grows together with "how many memories this person has, how much
was said in this scene":
by the tenth day, a character's prompt will carry dozens of memories and the whole scene's
dialogue,
the token bill doubles day by day, and **the first things squeezed out are exactly the worldview
and persona** —
at best the character starts acting out of character; at worst the model drops the prefix and
only replies "I'm waiting".
How the three layers are divided (`LAYERS`)
----------------------
  · `fixed` — global worldview / top-level rules / fixed persona layer / type profile. **Never trimmed**.
    It is "who this person is and what this world is like"; trimmed, it's no longer the same person.
  · `semi`  — style card / research card / state layer (scene · time · weather · presence · goal pyramid).
    **Not actively trimmed**; only touched when the dynamic layer has been stripped bare and it still exceeds budget, and then **from the tail**.
  · `dyn`   — memory topK / recent events / dialogue. **Trimmed first**.
Direction of trimming (per the design doc "trim from the tail of the dynamic layer backward")
------------------------------------------
Write `dyn` as an **ordered block list**, with every line inside a block ordered as "**tail is
least important**":
  · Memory block — **ascending** by importance × recency (least important last) → it's the first to go;
  · Event / dialogue block — **new in front, old behind** → the first to go is always the oldest.
So "trim from the tail backward" implemented this way is both **physically from tail to front**
(simple, assertable)
and a reasonable tradeoff (drop the least important / drop the oldest), and won't produce the
absurd result of "deleting what was just said".
Every trimmed segment is recorded (`trimmed`), because **silently feeding less** is an incident.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 层名（按"能不能裁"排序，`fixed` 最不能裁）
# [EN] Layer name (sorted by "can it be trimmed", `fixed` is the least trimmable)
LAYER_FIXED = "fixed"
LAYER_SEMI = "semi"
LAYER_DYN = "dyn"

LAYERS: tuple[str, ...] = (LAYER_FIXED, LAYER_SEMI, LAYER_DYN)


@dataclass
class Packed:
    """打包结果。`text` 是最终拼好的上下文；`trimmed` 记着**裁掉了什么**。
        English:
    Packaging result. `text` is the final assembled context; `trimmed` records **what was trimmed**.
    """
    text: str = ""
    tokens: int = 0
    budget: int = 0
    trimmed: list[str] = field(default_factory=list)

    @property
    def over(self) -> bool:
        """裁到底还是超预算吗？（是的话调用方该说一声，不该静默）
                English:
        After trimming to the end, is it still over budget? (If so, the caller should be told, not left
        silent)
        """
        return self.budget > 0 and self.tokens > self.budget


def estimate(text: str) -> int:
    """token 估算。**统一走 `llm/tokens.py`**（别在这里另造一套口径）。
        English:
    Token estimation. **Always go through `llm/tokens.py`** (don't build another set of rules here).
    """
    try:
        from llm.tokens import estimate_tokens
        return int(estimate_tokens(text or ""))
    except Exception:                                           # noqa: BLE001
        return max(1, len(text or "") // 2)


def _lines(block: str) -> list[str]:
    return [x for x in str(block or "").split("\n") if x.strip()]


def trim_dynamic(blocks: list[str], budget: int, head: str, tail: str,
                 notes: list[str] | None = None) -> Packed:
    """（`blocks` **后面的越不重要** —— 裁的时候从后往前。）
        English:
    (`blocks` **the later ones are less important** — when trimming, go from back to front.)
    """
    """在预算内塞下 `blocks`（按顺序），**从尾部往前**丢。

    `head` / `tail` 是不参与裁剪的两端（固定前缀与"请以 JSON 回答"那段指令）——
    把它们的开销先扣掉，剩下的才是给动态层的预算。
    返回打包结果；`notes` 里会记下"第几块被丢了几行"。
    """
    notes = notes if notes is not None else []

    def _render(kept: list[str]) -> str:
        return _join([head] + list(kept) + [tail])

    def _fits(kept: list[str]) -> bool:
        return estimate(_render(kept)) <= budget

    # ⚠ 第一版这里写错了：它**从尾往前逐块试**，一旦某块放不下就
    #   "部分保留"它并停下 —— 结果是**保住了最不重要的那一块、把更重要的
    #   前面的块整块丢了**（自检时 `budget=300` 就是：留下了半截「当前情况」，
    #   却把「最近记忆」全丢了）。现在的顺序是：
    #   ① 能全放下就全放；② 放不下就**从尾部整块丢**，直到放得下；
    #   ③ 只剩一块还放不下，才把这一块**按行从尾部丢**（块内已经排成
    #   "尾部最不重要"，所以丢掉的是最不重要的那些行）。
    # [EN] ⚠ The first version got this wrong here: it **tries block by block from tail to front**, and
    # [EN] once a block doesn't fit it
    # [EN] "partially keeps" it and stops — the result is that it **keeps the least important block and
    # [EN] throws away the whole
    # [EN] more important earlier blocks** (in self-check `budget=300` is exactly this: it kept half of
    # [EN] "current situation",
    # [EN] but threw away all of "recent memory"). The current order is:
    # [EN] ① if everything fits, keep it all; ② if it doesn't fit, **drop whole blocks from the tail**
    # [EN] until it fits;
    # [EN] ③ only when one block still doesn't fit, **drop this block line by line from the tail** (the
    # [EN] block is already ordered as
    # [EN] "tail is least important", so what gets dropped is the least important lines).
    if _fits(list(blocks)):
        text = _render(list(blocks))
        return Packed(text=text, tokens=estimate(text), budget=budget)

    kept = list(blocks)
    dropped: list[str] = []
    while len(kept) > 1 and not _fits(kept):
        # 从尾部丢，但把丢掉的东西**按原顺序**记着 —— 下面要用它把
        # 「最不该丢的那一块」尽量补回来（否则会出现"整块记忆被扔掉，
        # 而预算明明还够放十几行"这种浪费）。
        # [EN] Drop from the tail, but record the dropped things **in original order** — below this is used to
        # [EN] restore as much as possible the "block that least should be dropped" (otherwise you get the
        # [EN] waste of "a whole block of memory thrown away,
        # [EN] while the budget clearly still has room for a dozen lines");
        dropped.insert(0, kept.pop())
        notes.append(f"尾部整块丢掉（{estimate(dropped[0])} token）")

    # 只剩最后一块仍放不下 → 这一块**按行从尾部丢**（块内尾部最不重要）
    # [EN] only the last block still doesn't fit → **drop this block line by line from the tail** (within
    # [EN] the block, the tail is least important)
    if kept and not _fits(kept):
        lines = _lines(kept[-1])
        acc: list[str] = []
        for ln in lines:                    # 从头开始留（块内头部最重要）
        # [EN] keep from the beginning (within the block, the head is most important)
            if not _fits(kept[:-1] + ["\n".join(acc + [ln])]):
                break
            acc.append(ln)
        notes.append(f"最后一块裁到只剩 {len(acc)}/{len(lines)} 行（从尾部往前丢）")
        kept = kept[:-1] + (["\n".join(acc)] if acc else [])

    # ★ 把"最重要的那个被丢掉的块"尽量补回来：只补**头部**若干行
    #   （块内头部最重要），补不下就停。这才是"先丢不重要的"该有的样子。
    # [EN] ★ Restore as much as possible the "most important dropped block": only restore **the head**
    # [EN] lines
    # [EN] (within the block the head is most important), and stop when it can't fit. This is what "drop
    # [EN] the unimportant first" should look like.
    if dropped:
        lines = _lines(dropped[0])
        acc = []
        for ln in lines:
            if not _fits(kept + ["\n".join(acc + [ln])]):
                break
            acc.append(ln)
        if acc:
            kept = kept + ["\n".join(acc)]
            notes.append(f"又把「{len(acc)}/{len(lines)} 行」补了回来（头部优先）")
        if len(dropped) > 1 + (1 if acc else 0):
            notes.append(f"另有 {len(dropped) - 1} 块（更不重要的）整块没能留下")

    text = _render(kept)
    p = Packed(text=text, tokens=estimate(text), budget=budget)
    if not kept:
        notes.append("动态层整层被裁光（预算连固定前缀都吃紧，请调大 "
                     "MAX_CONTEXT_TOKENS）")
    p.trimmed = notes
    return p


def pack(fixed: str, semi: str, dyn_blocks: list[str], tail: str,
         budget: int | None = None) -> Packed:
    """三层打包：`fixed` 永不裁 → `semi` 只在必要时裁 → `dyn` 优先裁。

    `budget` 为 None/0 时**不裁**（老行为的等价物：想全量喂就全量喂）。
    
        English:
    Three-layer packaging: `fixed` never trimmed → `semi` trimmed only when necessary → `dyn`
    trimmed first.
        When `budget` is None/0, **do not trim** (the equivalent of old behavior: feed everything if you want everything fed).
    """
    budget = int(budget or 0)
    head = _join([fixed, semi])
    if budget <= 0:
        text = _join([fixed, semi] + list(dyn_blocks) + [tail])
        return Packed(text=text, tokens=estimate(text), budget=0)
    # 先按"能裁"的顺序算：fixed 不裁，semi 与 dyn 一起排（dyn 在最后 = 先被丢）
    # [EN] First compute by "trimmability" order: fixed is not trimmed, semi and dyn are ordered together
    # [EN] (dyn last = dropped first)
    return trim_dynamic([semi] + list(dyn_blocks), budget, fixed, tail)


def _join(parts: list[str]) -> str:
    return "\n".join(x for x in (str(p or "").strip("\n") for p in parts) if x.strip())


def memory_block(rows: list[dict], limit: int = 0) -> str:
    """记忆块：按「重要性 × 新近度」**降序**排 —— **尾部最不重要**（先走的就是它）。

    ⚠ 方向**不能反**（第一版写成升序、被自检当场抓住）：升序的话
    尾部就是"最重要的那条"，裁尾部等于**先丢掉最该留的**。
    
        English:
    Memory block: sorted **descending** by "importance × recency" — **the tail is least important**
    (it's the first to go).
        ⚠ The direction **must not be reversed** (the first version wrote it ascending and was caught on the spot by self-check): if ascending,
        the tail is "the most important one", and trimming the tail equals **dropping the one that most should be kept first**.
    """
    def score(r: dict) -> float:
        try:
            return float(r.get("importance", 5.0) or 5.0) \
                * (1.0 + float(r.get("game_ts", 0.0) or 0.0) / 1440.0)
        except (TypeError, ValueError):
            return 5.0
    rows = sorted(rows, key=score, reverse=True)
    if limit > 0:
        rows = rows[:limit]
    return "\n".join(f"- [{r.get('type', '?')}] {r.get('content', '')}" for r in rows)


def recent_block(rows: list[dict], limit: int = 0) -> str:
    """事件/对话块：**新的在前、旧的在后** —— 尾部最旧（先走的就是它）。
        English:
    Event/dialogue block: **new in front, old behind** — the tail is the oldest (it's the first to
    go).
    """
    items = list(rows)
    if limit > 0:
        items = items[-limit:]
    return "\n".join(f"- {str(r.get('content') or r.get('text') or '')}"
                     for r in reversed(items))


def split_keep_recent(text: str, keep: float) -> tuple[str, str]:
    """把一段文本按**行数比例**切一刀，返回 `(要折的老那部分, 保留的最近那部分)`。

    ★★ 这是"主动压缩"里最要紧的一步（2026-10-10，用户要求"贴线就压"）：
      压**保留最近一段原文不动**，只把更老的折成摘要 ——
      刚刚发生的事一个字都不能丢，这是压缩与"扔掉"的分界。

    为什么按**行**切而不是按字符切：这里的块都是"一行一件事"
    （`- [观察] 张三把茶盏搁下` / `李四 对你说：…`）。按字符切会**切断半句话**，
    折出来的摘要会比原文更难读，而且第一行/最后一行常带块标题（`最近记忆（…）`），
    按字符切还可能把标题切下来当正文。

    ⚠ 太短的块**不切**（切了也压不了多少，反而多一次模型调用）：
      少于 `_MIN_SPLIT_LINES` 行、或者 `keep` 落在头尾的极端值时，原样返回。
    
        English:
    Cut a piece of text by **line-count ratio**, returning `(the old part to fold, the recent part
    to keep)`.
        ★★ This is the most important step in "active compression" (2026-10-10, user requested "compress when close to the line"):
          compression **keeps the most recent passage of original text untouched**, and only folds the older part into a summary —
          what just happened cannot lose a single word; this is the dividing line between compression and "throwing away".
        Why split by **line** instead of by character: the blocks here are all "one thing per line"
        (`- [Observation] Zhang San puts down the teacup` / `Li Si says to you: ...`). Splitting by character would **cut a sentence in half**,
        and the folded summary would be harder to read than the original, plus the first/last line often carries a block title (`Recent memory (...)`),
        so splitting by character might also cut off the title and treat it as body text.
        ⚠ Blocks that are too short are **not split** (splitting them barely compresses anything and just costs an extra model call):
          when there are fewer than `_MIN_SPLIT_LINES` lines, or `keep` falls at an extreme value at the head/tail, return as-is.
    """
    lines = [ln for ln in str(text or '').split('\n')]
    if len(lines) < _MIN_SPLIT_LINES:
        return '', text
    k = float(keep)
    if k <= 0.0:
        return '\n'.join(lines), ''
    if k >= 1.0:
        return '', '\n'.join(lines)
    cut = int(round(len(lines) * k))
    #: 最近那部分至少要留一行、老的至少要走一行（否则这次压缩毫无意义）
    # [EN] : the recent part must keep at least one line, and the old part must drop at least one line
    # [EN] (otherwise this compression is pointless)
    cut = max(1, min(len(lines) - 1, cut))
    old = '\n'.join(lines[:-cut])
    recent = '\n'.join(lines[-cut:])
    return old, recent


#: 少于这么多行就不切（见 `split_keep_recent`）。
# [EN] : if fewer than this many lines, do not split (see `split_keep_recent`).
_MIN_SPLIT_LINES = 6
