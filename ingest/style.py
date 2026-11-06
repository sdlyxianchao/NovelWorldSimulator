# -*- coding: utf-8 -*-
"""风格卡（设计稿 §3.4）：从正文样本统计 + LLM 归纳风格特征。
English:
Style card (design doc §3.4): compute stats from body-text samples + LLM summarizes style
features.
"""
from __future__ import annotations

from typing import Any
from llm.replies import ask
from util.text import fill

# 这一步的输出很小（7 个字段），但**仍要显式给预算**：别靠默认值，
# 也别让"预算多大"这件事散在各处（推理模型会再挤一份思考额度进去）。
# [EN] The output of this step is small (7 fields), but **you still must give the budget explicitly**:
# [EN] don't rely on defaults,
# [EN] and don't let "how big the budget is" be scattered everywhere (the reasoning model will squeeze
# [EN] in another chunk of thinking allowance).
_STYLE_MAX_TOKENS = 1500

_LOG = __import__("logging").getLogger("nws.ingest")

_PROMPT = """你是一位文学风格分析专家。请根据下面的小说正文样本，归纳作者的写作风格卡。

风格卡包含：
- 句长：长句/中句/短句为主
- 叙事距离：全知/限知/贴近人物
- 词汇偏好：白描/华丽/古风/现代/方言等
- 对话占比：大致百分比（低/中/高）
- 视角纪律：第一/第三人称，限知程度
- 章法偏好：小节短留钩/大段连贯/章节节奏等
- AI腔禁词表：列出在该风格中最违和的5~10个典型AI套话词（如「首先」「其次」「值得注意的是」「在这个过程里」「不仅仅」等）

请以 JSON 回答：
{
  "句长": "...",
  "叙事距离": "...",
  "词汇偏好": "...",
  "对话占比": "...",
  "视角纪律": "...",
  "章法偏好": "...",
  "AI腔禁词表": ["词1", "词2", ...]
}

★ 长度是硬要求：每个字段**一句话、不超过 20 字**；「AI腔禁词表」**5~10 个词**，
每个词不超过 6 个字。只输出 JSON 对象本身，不要开场白、不要结语、
不要用 ```json 代码块包起来。

正文样本（节选）：
{content}
"""


async def extract_style(content: str) -> dict[str, Any]:
    """从正文提取风格卡。无正文返回默认风格。
        English:
    Extract the style card from the body text. Return the default style if there is no body text.
    """
    if not content.strip() or len(content.strip()) < 100:
        return _default_style("无正文或正文过短，使用默认风格")

    # ★ 2026-10-10（第 04 类第 2 条）：**按句截断**，别截在半句上。
    #   原来 `content[:4000]` 会切出残句，而模型照着"样本"学文风时
    #   **残句也是一种句式** —— 它会把这个断掉的节奏也学过去。
    # [EN] ★ 2026-10-10 (category 04, item 2): **truncate by sentence**, don't cut mid-sentence.
    # [EN] The old `content[:4000]` would cut off a fragment, and when the model learns the writing style
    # [EN] from the "sample",
    # [EN] **a fragment is also a sentence pattern** — it will learn that broken rhythm too.
    from util.text import head_sentences
    sample = head_sentences(content, 4000)
    messages = [{"role": "user", "content": fill(_PROMPT, content=sample)}]
    rep = await ask("cheap", messages, purpose="style", want=dict,
                    json_mode=True, max_tokens=_STYLE_MAX_TOKENS, temperature=0.2)

    result = rep.value if isinstance(rep.value, dict) else None
    if not result:
        _LOG.warning("风格卡拿不到结果：%s", rep.notes)
        return _default_style("解析失败，使用默认风格")
    result.setdefault("来源", "LLM 从正文提取")
    return result


def _default_style(reason: str) -> dict[str, Any]:
    return {
        "句长": "中短句为主",
        "叙事距离": "贴近人物限知视角",
        "词汇偏好": "白描、少形容词",
        "对话占比": "中（约四成）",
        "视角纪律": "第三人称限知，不跳头",
        "章法偏好": "小节短、段尾留钩",
        "AI腔禁词表": ["首先", "其次", "总的来说", "值得注意的是",
                       "在这个过程里", "不仅仅", "与此同时", "毋庸置疑"],
        "来源": reason,
    }