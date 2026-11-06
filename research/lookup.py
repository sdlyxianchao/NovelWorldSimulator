# -*- coding: utf-8 -*-
"""考据通道（设计稿 §8.6）：知识缺口检测与考据。

触发三通道：
1. 自动：导演/前台决策检测到知识缺口
2. 手动：research 命令
3. 摄取预拉：按设定标注的时代/地域批量预考据

English:
Research channel (design doc §8.6): knowledge gap detection and research.
Three trigger channels:
1. Automatic: director/frontend decision detects a knowledge gap
2. Manual: research command
3. Ingestion pre-fetch: batch pre-research by era/region annotated in the settings
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from config import CFG
from llm.router import llm
from refs.rag import ref_rag
from skills.registry import skill_registry
from mcp.client import mcp_client

_LOG = __import__("logging").getLogger("nws.research")


class ResearchLookup:
    """考据通道：五层提供者（缓存→资料库→技能→MCP→联网兜底）。
        English:
    Research channel: five-layer providers (cache→profile library→skills→MCP→online fallback).
    """

    def __init__(self, run_dir: Path | None = None):
        self._run_dir = run_dir
        self._cache: dict[str, dict] = {}
        self._cache_days = CFG.i("RESEARCH_CACHE_DAYS")
        self._max_per_day = CFG.i("RESEARCH_MAX_PER_DAY")
        self._today_count = 0

    async def lookup(self, query: str, context: str = "") -> dict:
        """考据查询：五层提供者。

        `RESEARCH_AUTO=false`（以前零读取）→ **只走本地两层**
        （缓存 + 资料库），不碰技能 / MCP / 联网 / LLM ——
        离线写作、或不想为考据花一分钱时用这一个开关。
        
                English:
        Research query: five-layer providers.
                `RESEARCH_AUTO=false` (previously zero reads) → **only uses the two local layers**
                (cache + profile library), does not touch skills / MCP / online / LLM ——
                use this single switch for offline writing, or when you don't want to spend a cent on research.
        """
        # 检查每日限额
        # [EN] Check daily limit
        if self._today_count >= self._max_per_day:
            return {"结果": "达到每日考据限额", "来源": "限额", "置信": "无"}
        local_only = not CFG.b("RESEARCH_AUTO")

        # 1. 缓存
        # [EN] 1. Cache
        cached = self._check_cache(query)
        if cached:
            return cached

        # 2. 用户资料库
        # [EN] 2. User profile library
        ref_results = ref_rag.query(query, top_k=2)
        if ref_results:
            result = {
                "结果": ref_results[0].get("内容摘要", ""),
                "来源": f"资料库/{ref_results[0].get('名称', '')}",
                "置信": "中",
            }
            self._save_cache(query, result)
            return result

        if local_only:
            # 本地两层走完还没有 → **如实说没有**，别悄悄去联网
            # [EN] After exhausting both local layers, if still nothing → **honestly say nothing was found**, do
            # [EN] not silently go online
            return {"结果": "（本地资料里没有）", "来源": "本地", "置信": "无"}

        # 3. 技能
        # [EN] 3. Skills
        skill = skill_registry.find_skill(query)
        if skill:
            content = skill.get("_content", "")
            if content:
                result = {
                    "结果": content[:500],
                    "来源": f"技能/{skill.get('名称', '')}",
                    "置信": "中-高",
                }
                self._save_cache(query, result)
                return result

        # 4. MCP 服务（mcp_servers.yaml；总开关 MCP_ENABLED）
        # [EN] 4. MCP services (mcp_servers.yaml; master switch MCP_ENABLED)
        try:
            mcp_result = await mcp_client.search(query)
        except Exception as e:                       # MCP 坏了不能带崩模拟
        # [EN] MCP failures must not crash the simulation
            _LOG.warning('MCP 考据异常: %s', e)
            mcp_result = None
        if mcp_result:
            self._save_cache(query, mcp_result)
            return mcp_result

        # 5. 联网兜底（默认关）
        # [EN] 5. Online fallback (off by default)
        if CFG.b("ONLINE_LOOKUP"):
            result = await self._online_lookup(query)
            if result:
                self._save_cache(query, result)
                return result

        # 6. LLM 考据
        # [EN] 6. LLM research
        result = await self._llm_lookup(query, context)
        self._save_cache(query, result)
        self._today_count += 1
        return result

    def _check_cache(self, query: str) -> dict | None:
        """检查缓存。
                English:
        Check cache.
        """
        if query in self._cache:
            entry = self._cache[query]
            age_days = (time.time() - entry.get("ts", 0)) / 86400
            if age_days < self._cache_days:
                return entry.get("result")
        return None

    def _save_cache(self, query: str, result: dict) -> None:
        """保存到缓存。
                English:
        Save to cache.
        """
        self._cache[query] = {
            "ts": time.time(),
            "result": result,
        }

    async def _llm_lookup(self, query: str, context: str) -> dict:
        """LLM 考据。
                English:
        LLM research.
        """
        prompt = f"""请回答以下考据问题（来自小说世界模拟器）：

问题：{query}
{f'背景：{context}' if context else ''}

请以 JSON 回答：
{{"结果": "详细回答", "来源": "参考来源（如有）", "置信": "高/中/低"}}

注意：
1. 如果不确定，请明确标注置信度为"低"
2. 不要编造事实
3. 提供参考来源（如有）"""

        messages = [{"role": "user", "content": prompt}]
        try:
            raw = await llm.chat("cheap", messages, purpose="research", json_mode=True)
            from util.jsonio import extract_json
            result = extract_json(raw, {})
            return result or {"结果": "考据失败", "来源": "LLM", "置信": "低"}
        except Exception as e:
            _LOG.warning("LLM 考据失败: %s", e)
            return {"结果": "考据失败", "来源": "LLM", "置信": "低"}

    async def _online_lookup(self, query: str) -> dict | None:
        """联网考据（默认关）。
                English:
        Online research (off by default).
        """
        # TODO: 实际联网搜索
        # [EN] TODO: actual online search
        return None

    def write_research_notes(self) -> None:
        """写考据笔记.md。
                English:
        Write research notes.md.
        """
        if not self._run_dir:
            return

        notes_path = self._run_dir / "考据笔记.md"
        lines = ["# 考据笔记", "", f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}", ""]

        for query, entry in self._cache.items():
            result = entry.get("result", {})
            lines.append(f"## {query}")
            lines.append(f"- **来源**：{result.get('来源', '未知')}")
            lines.append(f"- **置信**：{result.get('置信', '未知')}")
            lines.append(f"- **结果**：{result.get('结果', '无')}")
            lines.append("")

        try:
            notes_path.write_text("\n".join(lines), encoding="utf-8")
            _LOG.info("考据笔记已生成: %s", notes_path)
        except Exception as e:
            _LOG.warning("写考据笔记失败: %s", e)


# 全局单例
# [EN] Global singleton
research_lookup = ResearchLookup()