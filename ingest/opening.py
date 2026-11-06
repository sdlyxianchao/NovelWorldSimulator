# -*- coding: utf-8 -*-
"""开局方案（设计稿 §3.6）：2~3 个候选小世界开局。
English:
Opening candidates (design doc §3.6): open with 2~3 candidate small worlds.
"""
from __future__ import annotations

from typing import Any

from llm.replies import ask
from util.jsonio import extract_json_lenient
from util.text import fill

# ★ 显式预算（别靠默认 2000）：这一步输出的是**数组**，每个方案 5 个字段。
#   当天实测正文 1024 token 才写完，离默认上限只剩一半余量；而推理模型还要
#   在额度里再挤一份思考。数组被砍断时旧代码同样一点都救不回来（见 `progress` 的说明）。
# [EN] ★ Explicit budget (don't rely on the default 2000): this step outputs an **array**, with 5
# [EN] fields per candidate.
# [EN] The measured body text on that day only finished at 1024 tokens, leaving only half the default
# [EN] limit as headroom; and reasoning models also need
# [EN] to squeeze in a chunk of thinking within the quota. When the array is truncated, the old code
# [EN] likewise cannot salvage anything at all (see the note on `progress`).
_OPENING_MAX_TOKENS = 2400

_PROMPT = """你是一位小说开局设计专家。根据以下设定信息，请为这个故事设计 2~3 个候选的小世界开局方案。

每个方案包含：
- 场景：开局发生在哪里（具体地点）
- 时刻：什么时间（时辰/天色/气候）
- 在场：谁在场（列出在场人物）
- 情境：开局一句话描述（一句有钩子的话）
- 理由：为什么选这个开局（一句话）

★ 长度是硬要求：**方案数 2~3 个**（不要更多）；每一个字段都**一句话、不超过 30 字**；
「情境」要是一句**有钩子**的话，不要写成梗概。
只输出 JSON 数组本身：第一个字符是 `[`、最后一个是 `]`，
不要开场白、不要结语、不要用 ```json 代码块包起来。

设定信息：
人物：{characters}
世界观：{worldview}
起始节点：{start_node}
类型：{genre}

请以 JSON 回答：
[
  {{"场景": "...", "时刻": "...", "在场": ["..."], "情境": "...", "理由": "..."}},
  ...
]
"""


async def propose_opening(settings: dict[str, Any], start_node_name: str = "") -> list[dict[str, Any]]:
    """生成 2~3 个候选开局方案。

    ★ 走 `llm/replies.ask(want=list)` —— 数组被截断时能救回前面写完的那几个方案，
    而不是**直接掉到那句写死的通用方案**（以前就是这样：模型明明给了 2 个方案，
    只是第 3 个写了一半，结果全被丢掉，作者拿到的是"一个寻常的夜晚，有人敲门"）。
    
        English:
    Generate 2~3 candidate opening plans.
        ★ Use `llm/replies.ask(want=list)` -- when the array is truncated it can salvage the candidates that were fully written earlier,
        instead of **falling straight through to that hardcoded generic plan** (the previous behavior: the model clearly gave 2 candidates,
        only the 3rd was half-written, yet all were discarded and the author got "a ordinary night, someone knocks on the door").
    """
    chars = ", ".join(p.get("姓名", "？") for p in settings.get("人物", [])[:6])
    worldview = settings.get("世界观", "未知")[:500]
    genre = settings.get("类型卡", {}).get("主题材", "通用")

    messages = [{"role": "user", "content": fill(
        _PROMPT, characters=chars, worldview=worldview,
        start_node=start_node_name or "故事开始",
        genre=genre)}]
    rep = await ask("cheap", messages, purpose="opening", want=list,
                    json_mode=True, max_tokens=_OPENING_MAX_TOKENS, temperature=0.5)

    candidates = rep.value if isinstance(rep.value, list) else []
    if not candidates:
        # 有的模型会把数组包进 {"候选": [...]}
        # [EN] Some models wrap the array in {"候选": [...]}
        obj = extract_json_lenient(rep.raw, {})
        if isinstance(obj, dict) and "候选" in obj:
            candidates = obj["候选"]
    # 抢救回来的数组末尾可能带一个空壳（补悬空 `{` 的产物），丢掉
    # [EN] The salvaged array may end with an empty shell (the product of completing a dangling `{`);
    # [EN] discard it
    candidates = [c for c in candidates
                  if isinstance(c, dict) and (c.get("场景") or c.get("情境"))]
    if not candidates:
        return [_default_opening(settings)]
    return candidates[:3]


def _default_opening(settings: dict) -> dict:
    chars = [p.get("姓名", "主角") for p in settings.get("人物", [])]
    return {
        "场景": "寻常场所",
        "时刻": "入夜",
        "在场": chars[:2] if chars else ["主角"],
        "情境": "一个寻常的夜晚，一切看起来和往常一样，直到有人敲门。",
        "理由": "低信息缺口开局，适合所有类型。"
    }