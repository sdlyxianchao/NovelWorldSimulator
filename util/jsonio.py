# -*- coding: utf-8 -*-
"""结构化输出兜底：LLM 常返回带解释、带代码块、带尾逗号的 JSON。
English:
Structured output fallback: LLMs often return JSON with explanations, code blocks, and trailing
commas.
"""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.S)
_OBJ = re.compile(r"\{.*\}", re.S)
_ARR = re.compile(r"\[.*\]", re.S)


def _clean(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"```$", "", s.strip()).strip()
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    return s


def safe_json_loads(text: str, default: Any = None) -> Any:
    try:
        return json.loads(_clean(text))
    except Exception:
        return default


def extract_json(text: str, default: Any = None) -> Any:
    if not text:
        return default
    m = _FENCE.search(text)
    cands = []
    if m:
        cands.append(m.group(1))
    cands.append(_clean(text))
    m2 = _OBJ.search(text)
    if m2:
        cands.append(m2.group(0))
    for c in cands:
        try:
            v = json.loads(_clean(c))
            if isinstance(v, dict):
                return v
        except Exception:
            continue
    return default


def extract_json_list(text: str, default: Any = None) -> Any:
    if not text:
        return default if default is not None else []
    m = _FENCE.search(text)
    cands = []
    if m:
        cands.append(m.group(1))
    cands.append(_clean(text))
    m2 = _ARR.search(text)
    if m2:
        cands.append(m2.group(0))
    for c in cands:
        try:
            v = json.loads(_clean(c))
            if isinstance(v, list):
                return v
        except Exception:
            continue
    obj = extract_json(text)
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list):
                return v
    return default if default is not None else []


# ══════════════════════════════════════════════════════════════════
#  「输出被 max_tokens 截断」的抢救
# [EN] "Output truncated by max_tokens" salvage
# ══════════════════════════════════════════════════════════════════
# 2026-10-06 的真实事故：开卷「提取设定」那一步的输出被上限**截在半句话里**，
# `json.loads` 报 `Unterminated string` → `extract_json` 返回空 → 整个设定集变成
# 空骨架（人物 0 位），**已经写完的人物全丢了**，界面上只留一句"无法解析"。
# [EN] 2026-10-06 real incident: the output of the opening "extract settings" step was cut off by the
# [EN] limit **mid-sentence**,
# [EN] `json.loads` reported `Unterminated string` -> `extract_json` returned empty -> the entire
# [EN] settings collection became
# [EN] an empty skeleton (0 characters), **all characters that had already been written were lost**,
# [EN] and the UI only showed "cannot parse".
#
# 这里做的是"**从后往前找最长的可闭合前缀**"：一个字都不改，只把还开着的
# `{` `[` 和半截的字符串收个尾 —— 能解析出多少算多少。
# [EN] What is done here is "**find the longest closable prefix from the back**": not a single
# [EN] character is changed, only the still-open
# [EN] `{` `[` and the half-finished string are closed off -- salvage as much as can be parsed.
#
# ⚠ 原则：**只补结构，不改内容**。不要在这里"猜"缺失的字段、不要补默认值、
#   不要把数字圆整 —— 那不是抢救，是编造。
# ⚠ 救回来的是**残缺数据**（末尾字段可能只写了一半），所以调用方**必须**
#   自己决定要不要用，并且把"这是救回来的、可能不完整"讲给用户听。
# [EN] ⚠ Principle: **only patch structure, do not change content**. Do not "guess" missing fields
# [EN] here, do not fill in default values,
# [EN] do not round numbers -- that is not salvage, it is fabrication.
# [EN] ⚠ What is recovered is **incomplete data** (trailing fields may be only half-written), so the
# [EN] caller **must**
# [EN] decide for itself whether to use it, and tell the user "this was salvaged and may be
# [EN] incomplete".

def _close_suffix(prefix: str) -> str | None:
    """给一段（可能被截断的）JSON 前缀算"把还开着的括号都关掉"要补的尾巴。

    停在字符串中间、或括号错位 → 返回 `None`（这个切点补不了，调用方往前退）。
    
        English:
    Given a (possibly truncated) JSON prefix, compute the tail needed to "close all still-open
    brackets".
        Stopping in the middle of a string, or mismatched brackets -> return `None` (this cut point cannot be patched, the caller backs up).
    """
    stack: list[str] = []
    in_str = False
    esc = False
    for ch in prefix:
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == '{':
            stack.append('}')
        elif ch == '[':
            stack.append(']')
        elif ch in '}]':
            if stack and stack[-1] == ch:
                stack.pop()
            else:
                return None                 # 括号错位，这段已经不是合法前缀
                # [EN] Mismatched brackets, this segment is no longer a valid prefix
    if in_str:
        return None
    return ''.join(reversed(stack))


_DANGLING_KEY = re.compile(r',?\s*"(?:[^"\\]|\\.)*"\s*:\s*$')


def _repair(text: str, want: type, default: Any = None) -> Any:
    """抢救**被截断**的 JSON：从后往前找最长的可闭合前缀，补上收尾括号。

    `want` = `dict` 或 `list` —— 顶层要救回来的类型。

    ★ 政策：**只补结构，不补内容** —— 尤其**不把截在半句里的字符串补成完整值**。
    被砍掉尾巴的那个字段**整条丢掉**，宁缺勿滥：设定集会一路流进推演，
    一句"半句话"混在里面比少一个字段更糟（调用方会明确告诉用户"可能不完整"）。
    
        English:
    Salvage **truncated** JSON: find the longest closable prefix from the back, and append the
    closing brackets.
        `want` = `dict` or `list` -- the top-level type to recover.
        ★ Policy: **only patch structure, not content** -- especially **do not complete a string cut off mid-sentence into a full value**.
        The field whose tail was cut off is **dropped entirely**; better to have less than something bad: the settings collection flows all the way into the simulation,
        and a "half-sentence" mixed in there is worse than a missing field (the caller will explicitly tell the user "may be incomplete").
    """
    if not text:
        return default
    s = _clean(text)
    starts = [p for p in (s.find('{'), s.find('[')) if p >= 0]
    if not starts:
        return default
    s = s[min(starts):]
    # 顶层就找想要的那种括号：要 list 时从 `[` 起，要 dict 时从 `{` 起。
    # ⚠ **别一律用"两种括号最早出现的那个"** —— 要 list 而文本以 `{` 开头时
    #   （模型把数组包进 `{"节点": [...]}` 这类外壳），从 `{` 起救回来的是 dict，
    #   顶层类型不对，调用方还是拿不到东西，等于白救一次。
    # [EN] At the top level, find the kind of bracket you want: when you want a list, start from `[`; when
    # [EN] you want a dict, start from `{`.
    # [EN] ⚠ **Do not just use "whichever of the two bracket types appears earliest"** -- when you want a
    # [EN] list but the text starts with `{`
    # [EN] (the model wraps the array in a shell like `{"nodes": [...]}`), starting from `{` recovers a
    # [EN] dict,
    # [EN] the top-level type is wrong, and the caller still gets nothing -- a wasted salvage.
    head = s.find('[' if want is list else '{')
    if head < 0:
        return default
    s = s[head:]
    # 候选切点只在"结构点"上（逗号/括号/引号/行尾），别逐字符试 —— 那是 O(n²)。
    # ⚠ **必须排序**：候选里先放了 `len(s)`（"整段"这个切点），不排序的话它会被
    #   排到最后才试，等于"从最短的前缀开始找" —— 救回来的东西白白少一截
    #   （踩过：`..."地点": [` 本该救成 `"地点": []`，结果整条 key 被丢了）。
    # [EN] Candidate cut points are only at "structural points" (comma/bracket/quote/end of line), do not
    # [EN] try character by character -- that is O(n^2).
    # [EN] ⚠ **Must sort**: `len(s)` (the "whole thing" cut point) was placed in the candidates first;
    # [EN] without sorting it will be
    # [EN] tried last, which amounts to "searching from the shortest prefix" -- and the recovered result is
    # [EN] needlessly shortened
    # [EN] (seen before: `..."location": [` should have been salvaged into `"location": []`, but the whole
    # [EN] key was dropped).
    cuts = sorted(set([len(s)] + [i for i, ch in enumerate(s)
                                  if ch in ',}]{["']))
    for pos in reversed(cuts[-400:]):
        prefix = s[:pos].rstrip()
        if prefix.endswith(','):
            prefix = prefix[:-1].rstrip()
        # 悬空的 key（`..."姓名":` 或 `..."姓名"`）留着就解析不了，去掉。
        # ⚠ 只对 dict 做 —— list 里没有 key，而 `_DANGLING_KEY` 的 `"?":` 形状
        #   在数组里是**元素内容**（比如 `"关系": "..."` 这种字符串值），误删会把元素吃掉。
        # [EN] A dangling key (`..."name":` or `..."name"`) cannot be parsed if kept, so drop it.
        # [EN] ⚠ Only do this for dict -- lists have no keys, and the `"?":` shape of `_DANGLING_KEY`
        # [EN] inside an array is **element content** (for example a string value like `"relation": "..."`),
        # [EN] and removing it by mistake eats the element.
        if want is dict:
            prefix = _DANGLING_KEY.sub('', prefix).rstrip()
            if prefix.endswith(','):
                prefix = prefix[:-1].rstrip()
        suffix = _close_suffix(prefix)
        if suffix is None:
            continue
        try:
            v = json.loads(prefix + suffix)
        except Exception:
            continue
        if isinstance(v, want):
            return v
    return default


def repair_json(text: str, default: Any = None) -> Any:
    """抢救被截断的 **JSON 对象**（顶层 `{...}`）。
        English:
    Salvage truncated **JSON object** (top-level `{...}`).
    """
    return _repair(text, dict, default)


def repair_json_list(text: str, default: Any = None) -> Any:
    """抢救被截断的 **JSON 数组**（顶层 `[...]`）。

    2026-10-06 补：以前只有 `repair_json`，它**只认 dict** —— 于是所有"返回数组"
    的步骤（故事进度表 `build_progress_table`、开局方案 `propose_opening`）在被截断时
    **抢救等于没做**：`extract_json_list` 返回空 ⇒ `progress` 那一步静默产出**空表**，
    屏幕上只看到"进度节点 0 个"，没有任何报错（当天那次真实开卷就是这么丢的）。
    
        English:
    Salvage truncated **JSON array** (top-level `[...]`).
        2026-10-06 addendum: previously there was only `repair_json`, which **only recognizes dict** -- so all "returns an array"
        steps (story progress table `build_progress_table`, opening proposal `propose_opening`) when truncated had
        **salvage effectively not done**: `extract_json_list` returned empty => the `progress` step silently produced an **empty table**,
        and the screen only showed "0 progress nodes", with no error at all (that day's real opening was lost exactly this way).
    """
    return _repair(text, list, default)


def parse_or_repair(text: str, default: Any = None, *, want: Any = dict) -> tuple[Any, bool]:
    """先按正常路径解析；不行再抢救。返回 `(结果, 是否是抢救来的)`。

    `want` 收 `dict` / `list` / `"text"` —— 最后一种表示**这一路不需要解析**
    （纯文本回复，只要非空就算拿到了），此时第二个返回值恒为 False。

    ⚠ **"空的容器"不算拿到东西，必须继续走抢救**。这条是踩出来的：
    `extract_json_list()` 解析失败时的返回值就是 `[]`（它内部 `default` 兜底成空表），
    于是 `isinstance(v, list)` 恒为真 —— 抢救那一步**永远不会被执行**，
    函数安静地返回一个空表，看起来像"模型说没有节点"。**空表 = 这一步白干**，
    对调用方而言和"解析失败"完全等价，所以这里一律当成失败。
    
        English:
    First parse by the normal path; if that fails, salvage. Returns `(result, whether it was
    salvaged)`.
        `want` accepts `dict` / `list` / `"text"` -- the last means **this path does not need parsing**
        (a plain-text reply, counted as obtained as long as it is non-empty), and in that case the second return value is always False.
        ⚠ **"An empty container" does not count as getting something; salvage must still be attempted**. This was learned the hard way:
        the return value of `extract_json_list()` on parse failure is `[]` (internally `default` falls back to an empty list),
        so `isinstance(v, list)` is always true -- the salvage step **is never executed**,
        and the function quietly returns an empty list, looking like "the model said there are no nodes". **An empty list = this step was wasted**,
        which for the caller is completely equivalent to "parse failure", so here it is always treated as failure.
    """
    if want == "text":
        s = (text or "").strip()
        return (s or default), False
    strict = extract_json if want is dict else extract_json_list
    loose = repair_json if want is dict else repair_json_list
    v = strict(text, None)
    if isinstance(v, want) and v:                    # ← `and v`：空容器不算成功
    # [EN] <- `and v`: an empty container does not count as success
        return v, False
    v = loose(text, None)
    if isinstance(v, want) and v:
        return v, True
    return default, False


def extract_json_lenient(text: str, default: Any = None) -> Any:
    """`extract_json` 的"能救就救"版本：严格解析失败时按可闭合前缀抢救。

    ⚠ 与 `extract_json` 的分工 —— **看"解析失败之后会怎样"**：
      · 失败会**触发重试或明确报错**的地方用严格版（`extract_settings` 就是靠
        "解析失败 + truncated" 去触发重试的，若这里悄悄救回来，重试就永远不会发生）；
      · 失败就**降级成默认值、而默认值等于这一步白干**的地方用这个 ——
        救回一半也比全丢强（进度表、风格卡、开局方案、导演事件都属于这类：
        它们的默认值是空表，等于这次调用白花钱）。
    
        English:
    The "salvage when possible" version of `extract_json`: on strict parse failure, salvage by
    closable prefix.
        ⚠ Division of labor with `extract_json` -- **look at "what happens after parse failure"**:
          · Use the strict version where failure **triggers a retry or an explicit error** (`extract_settings` relies on
            "parse failure + truncated" to trigger a retry; if it quietly salvaged here, the retry would never happen);
          · Use this one where failure **degrades to a default value, and the default value equals this step being wasted** --
            recovering half is better than losing everything (progress table, style cards, opening proposal, director events all fall into this category:
            their default value is an empty list, which equals this call wasting money).
    """
    v = extract_json(text, None)
    if isinstance(v, dict) and v:
        return v
    v = repair_json(text, None)
    return v if isinstance(v, dict) and v else default


def extract_json_list_lenient(text: str, default: Any = None) -> Any:
    """`extract_json_list` 的"能救就救"版本（数组版，见 `repair_json_list` 的说明）。

    ⚠ 同样要 `and v`：`extract_json_list` 失败时返回的是 `[]`，
    只看 `isinstance` 会让抢救变成死代码。
    
        English:
    The "salvage when possible" version of `extract_json_list` (array version, see the description
    of `repair_json_list`).
        ⚠ Also needs `and v`: `extract_json_list` returns `[]` on failure,
        and looking only at `isinstance` turns salvage into dead code.
    """
    v = extract_json_list(text, None)
    if isinstance(v, list) and v:
        return v
    v = repair_json_list(text, None)
    return v if isinstance(v, list) and v else default