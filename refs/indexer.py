# -*- coding: utf-8 -*-
"""资料库索引（设计稿 §8.5）：用户资料库索引与片段检索。

资料库结构：
├── 参考书/      教科书、学术书摘、笔记
├── 参考小说/    用户自己写的或有权使用的小说文本
└── 规则/        用户自定义创作规则

English:
Library index (design doc §8.5): user library index and snippet retrieval.
Library structure:
├── 参考书/      textbooks, academic book excerpts, notes
├── 参考小说/    novel texts written by the user or that the user has the right to use
└── 规则/        user-defined creation rules
"""
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from config import CFG
from ingest.scanner import read_single_file

_LOG = __import__("logging").getLogger("nws.refs")


class RefIndexer:
    """资料库索引器：扫描、索引、检索用户资料库。
        English:
    Library indexer: scans, indexes, and retrieves the user library.
    """

    def __init__(self, ref_dir: Path | None = None):
        self._ref_dir = ref_dir or CFG.resolved("REFERENCE_DIR")
        self._index: dict[str, dict] = {}  # 文件路径 -> 元数据
        # [EN] file path -> metadata
        self._loaded = False

    def load(self) -> None:
        """加载资料库索引。
                English:
        Load the library index.
        """
        if self._loaded:
            return

        if not self._ref_dir.exists():
            _LOG.info("资料库目录不存在: %s", self._ref_dir)
            return

        # 扫描三个子目录
        # [EN] scan three subdirectories
        for subdir in ("参考书", "参考小说", "规则"):
            dir_path = self._ref_dir / subdir
            if not dir_path.exists():
                continue

            for f in dir_path.rglob("*"):
                if f.is_file() and f.suffix in (".md", ".txt", ".docx", ".html"):
                    try:
                        item = read_single_file(f)
                        self._index[str(f)] = {
                            "路径": str(f),
                            "名称": f.name,
                            "类别": subdir,
                            "字数": len(item.content),
                            "行数": item.lines,
                            "内容摘要": item.content[:200] if item.content else "",
                        }
                    except Exception as e:
                        _LOG.warning("索引失败 %s: %s", f.name, e)

        self._loaded = True
        _LOG.info("资料库索引完成: %d 个文件", len(self._index))

        # 保存索引
        # [EN] save index
        self._save_index()

    def _save_index(self) -> None:
        """保存索引到 资料索引.yaml。
                English:
        Save the index to 资料索引.yaml.
        """
        index_path = self._ref_dir / "资料索引.yaml"
        try:
            with open(index_path, "w", encoding="utf-8") as f:
                yaml.dump(self._index, f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            _LOG.warning("保存索引失败: %s", e)

    def search(self, query: str, category: str = "", limit: int = 5) -> list[dict]:
        """搜索资料库。
                English:
        Search the library.
        """
        results = []
        query_lower = query.lower()

        for path, meta in self._index.items():
            # 类别过滤
            # [EN] category filtering
            if category and meta["类别"] != category:
                continue

            # 简单关键词匹配
            # [EN] simple keyword matching
            content = meta.get("内容摘要", "")
            if query_lower in content.lower() or query_lower in meta["名称"].lower():
                results.append(meta)

            if len(results) >= limit:
                break

        return results

    def get_all(self, category: str = "") -> list[dict]:
        """获取所有资料。
                English:
        Get all materials.
        """
        if not category:
            return list(self._index.values())
        return [m for m in self._index.values() if m["类别"] == category]

    def get_summary(self) -> dict:
        """获取资料库摘要。
                English:
        Get a library summary.
        """
        categories = {}
        for meta in self._index.values():
            cat = meta["类别"]
            if cat not in categories:
                categories[cat] = {"文件数": 0, "总字数": 0}
            categories[cat]["文件数"] += 1
            categories[cat]["总字数"] += meta.get("字数", 0)

        return {
            "目录": str(self._ref_dir),
            "总文件数": len(self._index),
            "分类": categories,
        }


# 全局单例
# [EN] global singleton
ref_indexer = RefIndexer()