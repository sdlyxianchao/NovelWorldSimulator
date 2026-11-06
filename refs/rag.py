# -*- coding: utf-8 -*-
"""资料库检索（设计稿 §8.5）：RAG 检索接口。

用法：
    from refs.rag import ref_rag
    results = ref_rag.query("宋代货币制度", top_k=3)

English:
Reference library retrieval (design doc §8.5): RAG retrieval interface.
Usage:
    from refs.rag import ref_rag
"""
from __future__ import annotations

from typing import Any
from pathlib import Path

from refs.indexer import ref_indexer
from config import CFG

_LOG = __import__("logging").getLogger("nws.refs")


class RefRAG:
    """资料库 RAG 检索接口。
        English:
    Reference library RAG retrieval interface.
    """

    def __init__(self):
        self._inject_max = CFG.i("REFERENCE_INJECT_MAX")

    def query(self, query: str, category: str = "", top_k: int = 3) -> list[dict]:
        """查询资料库，返回相关片段。
                English:
        Query the reference library, return relevant snippets.
        """
        # 搜索
        # [EN] Search
        results = ref_indexer.search(query, category, limit=top_k)

        # 截取到注入上限
        # [EN] Truncated to injection limit
        for r in results:
            if len(r.get("内容摘要", "")) > self._inject_max:
                r["内容摘要"] = r["内容摘要"][:self._inject_max] + "..."

        return results

    def inject_context(self, query: str, category: str = "") -> str:
        """注入上下文：返回可用于 prompt 的文本。
                English:
        Inject context: return text usable for the prompt.
        """
        results = self.query(query, category)
        if not results:
            return ""

        parts = []
        for r in results:
            parts.append(f"【{r['类别']}】{r['名称']}\n{r['内容摘要']}")

        return "\n\n".join(parts)

    def get_reference_books(self, topic: str) -> list[dict]:
        """获取相关参考书。
                English:
        Get related reference books.
        """
        return self.query(topic, category="参考书")

    def get_reference_novels(self, style: str) -> list[dict]:
        """获取相关参考小说（用于风格取样）。
                English:
        Get related reference novels (for style sampling).
        """
        return self.query(style, category="参考小说")

    def get_rules(self, topic: str) -> list[dict]:
        """获取相关规则。
                English:
        Get related rules.
        """
        return self.query(topic, category="规则")


# 全局单例
# [EN] Global singleton
ref_rag = RefRAG()