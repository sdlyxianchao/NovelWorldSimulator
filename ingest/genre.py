# -*- coding: utf-8 -*-
"""类型判定（设计稿 §3.3）：题材 × 结构 × 频道三轴正交组合。
English:
Type determination (design doc §3.3): orthogonal combination of the three axes: subject matter ×
structure × channel.
"""
from __future__ import annotations

from typing import Any
from llm.replies import ask
from util.text import fill

_GENRE_MAX_TOKENS = 1200
_LOG = __import__("logging").getLogger("nws.ingest")

_PROMPT = """你是一位网络文学/出版类型学专家。根据以下小说项目的文本内容，判断其类型。

三轴组合：
- 题材（主题材+副题材）：悬疑、灵异、玄幻、修仙、都市、历史、架空、言情、科幻、武侠、推理、现实……
- 结构：单元剧、升级流、公路、群像、副本制、种田、三幕……
- 频道：男频、女频、出版向、古风、网文……

请以 JSON 回答：
{
  "主题材": "...",
  "副题材": "...",
  "结构": "...",
  "频道": "...",
  "置信度": 0.0~1.0,
  "理由": "一句话"
}

★ 长度是硬要求：每个字段**一句话、不超过 20 字**。只输出 JSON 对象本身，
不要开场白、不要结语、不要用 ```json 代码块包起来。

文本内容（节选）：
{content}
"""


async def detect_genre(content: str, manual: str = "") -> dict[str, Any]:
    """类型判定。manual 非空则跳过 LLM 直接解析。
        English:
    Type determination. If manual is non-empty, skip the LLM and parse directly.
    """
    if manual and manual != "auto":
        parts = manual.replace("+", "|").replace("｜", "|").split("|")
        return {"主题材": parts[0] if len(parts) > 0 else "通用",
                "副题材": parts[1] if len(parts) > 1 else "",
                "结构": parts[2] if len(parts) > 2 else "三幕",
                "频道": parts[3] if len(parts) > 3 else "出版向",
                "置信度": 0.9, "理由": "手动指定"}

    if not content.strip():
        return {"主题材": "通用", "副题材": "", "结构": "三幕", "频道": "出版向",
                "置信度": 0.1, "理由": "无可读内容"}

    # 截取前 3000 字给 LLM
    # [EN] Truncate to the first 3000 characters and give them to the LLM
    sample = content[:3000]
    messages = [{"role": "user", "content": fill(_PROMPT, content=sample)}]
    rep = await ask("cheap", messages, purpose="genre", want=dict,
                    json_mode=True, max_tokens=_GENRE_MAX_TOKENS, temperature=0.2)
    result = rep.value if isinstance(rep.value, dict) else None
    if not result:
        _LOG.warning("类型判定拿不到结果：%s", rep.notes)
        return {"主题材": "通用", "副题材": "", "结构": "三幕", "频道": "出版向",
                "置信度": 0.1, "理由": "解析失败"}
    return result