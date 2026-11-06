# -*- coding: utf-8 -*-
"""向量嵌入模块：支持本地模型、Ollama、API 服务。

配置：
- EMBEDDING_PROVIDER: local / api / ollama / none
- EMBEDDING_MODEL_LOCAL: 本地模型名（如 BAAI/bge-small-zh-v1.5）
- EMBEDDING_MODEL_API: API 模型名（如 text-embedding-3-small）
- EMBEDDING_OLLAMA_MODEL: Ollama 模型名（如 nomic-embed-text）
- EMBEDDING_OLLAMA_URL: Ollama 服务地址

English:
Vector embedding module: supports local models, Ollama, API services.
Configuration:
- EMBEDDING_PROVIDER: local / api / ollama / none
- EMBEDDING_MODEL_LOCAL: local model name (e.g. BAAI/bge-small-zh-v1.5)
- EMBEDDING_MODEL_API: API model name (e.g. text-embedding-3-small)
- EMBEDDING_OLLAMA_MODEL: Ollama model name (e.g. nomic-embed-text)
- EMBEDDING_OLLAMA_URL: Ollama service URL
"""
from __future__ import annotations

import asyncio
from typing import Any
import httpx

from config import CFG

_LOG = __import__("logging").getLogger("nws.embedding")


class EmbeddingProvider:
    """向量嵌入提供者基类。
        English:
    Base class for vector embedding providers.
    """

    async def embed(self, text: str) -> list[float]:
        """将文本转换为向量。
                English:
        Convert text to a vector.
        """
        raise NotImplementedError

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量将文本转换为向量。
                English:
        Convert texts to vectors in batch.
        """
        return [await self.embed(t) for t in texts]


class OllamaEmbedding(EmbeddingProvider):
    """Ollama embedding 提供者。
        English:
    Ollama embedding provider.
    """

    def __init__(self, model: str = "nomic-embed-text",
                 base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    async def embed(self, text: str) -> list[float]:
        """调用 Ollama embedding API。
                English:
        Call the Ollama embedding API.
        """
        client = await self._get_client()
        try:
            resp = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text}
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("embedding", [])
        except Exception as e:
            _LOG.error("Ollama embedding 失败: %s", e)
            raise

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量调用（Ollama 没有原生批量接口，逐个调用）。
                English:
        Batch call (Ollama has no native batch interface, call one by one).
        """
        results = []
        for text in texts:
            try:
                vec = await self.embed(text)
                results.append(vec)
            except Exception:
                results.append([])
        return results

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


class LocalEmbedding(EmbeddingProvider):
    """本地模型 embedding 提供者（需要 sentence-transformers）。
        English:
    Local model embedding provider (requires sentence-transformers).
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                _LOG.info("加载本地 embedding 模型: %s", self.model_name)
            except ImportError:
                _LOG.error("未安装 sentence-transformers，请运行: pip install sentence-transformers")
                raise
            except Exception as e:
                _LOG.error("加载模型失败: %s", e)
                raise

    async def embed(self, text: str) -> list[float]:
        """使用本地模型生成向量。
                English:
        Generate vectors using a local model.
        """
        self._load_model()
        try:
            # sentence-transformers 是同步的，用 asyncio 包装
            # [EN] sentence-transformers is synchronous, wrap it with asyncio
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(None, self._model.encode, text)
            return embedding.tolist()
        except Exception as e:
            _LOG.error("本地 embedding 失败: %s", e)
            raise

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成向量。
                English:
        Generate vectors in batch.
        """
        self._load_model()
        try:
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(None, self._model.encode, texts)
            return [e.tolist() for e in embeddings]
        except Exception as e:
            _LOG.error("批量 embedding 失败: %s", e)
            raise


def _bill(purpose: str, texts: list[str], data: dict) -> None:
    """把一次 embedding 调用**记进全局台账**（2026-10-19 补的缺口）。

    ★★★ 为什么必须补：`APIEmbedding` 走的是**自己建的 httpx 客户端**，
      绕过了 `llm/router.Ledger` —— 而 `Ledger.add` 是全项目**唯一**的记账汇合点。
      于是 embedding 一花钱就完全隐形（用户问"用量统计有没有缺"，这就是一处确凿的缺）。

    ⚠ 口径：embedding 的计费按**输入 token**，所以 `out_tok=0`、`in_tok` 用
      `usage.prompt_tokens`（服务端给了就用它，没给就按字数估）。
      **不按"条数"记** —— 那会让"多少 token"这一列对不上。
    ⚠ 失败不抛（旁路纪律，同 `usage.record`）。
    [EN] ★★★ Why this must be added: `APIEmbedding` uses **its own httpx client**, bypassing
    [EN] `llm/router.Ledger` -- and `Ledger.add` is the **only** accounting convergence point in the
    [EN] project. So embedding spend was completely invisible (the user asked "is the usage stats
    [EN] missing anything" -- this is a confirmed gap).
    [EN] ⚠ Convention: embedding bills by **input tokens**, so `out_tok=0` and `in_tok` comes from
    [EN] `usage.prompt_tokens` (fallback: estimate from characters). **Never count "items"** -- that
    [EN] would break the token column.
    [EN] ⚠ Never throws (bypass discipline, same as `usage.record`).
    """
    try:
        from llm import usage as U
        from llm.tokens import estimate_tokens
        u = (data or {}).get('usage') or {}
        tin = int(u.get('prompt_tokens') or u.get('total_tokens') or 0)
        if tin <= 0:
            tin = sum(estimate_tokens(str(x or '')) for x in (texts or []))
        U.record(model=str(CFG.s('EMBEDDING_MODEL_API') or 'embedding'),
                 purpose=str(purpose), in_tok=tin, out_tok=0, cost=0.0,
                 tier='embedding')
    except Exception:                                            # noqa: BLE001
        pass


class APIEmbedding(EmbeddingProvider):
    """API embedding 提供者（OpenAI 兼容）。
        English:
    API embedding provider (OpenAI-compatible).
    """

    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=CFG.s("LLM_BASE_URL").rstrip("/"),
                headers={"Authorization": f"Bearer {CFG.s('LLM_API_KEY')}"},
                timeout=30
            )
        return self._client

    async def embed(self, text: str) -> list[float]:
        """调用 OpenAI 兼容 embedding API。
                English:
        Call the OpenAI-compatible embedding API.
        """
        client = await self._get_client()
        try:
            resp = await client.post(
                "/embeddings",
                json={"model": self.model, "input": text}
            )
            resp.raise_for_status()
            data = resp.json()
            _bill('embed', [text], data)
            return data["data"][0]["embedding"]
        except Exception as e:
            _LOG.error("API embedding 失败: %s", e)
            raise

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量调用 embedding API。
                English:
        Call the embedding API in batch.
        """
        client = await self._get_client()
        try:
            resp = await client.post(
                "/embeddings",
                json={"model": self.model, "input": texts}
            )
            resp.raise_for_status()
            data = resp.json()
            _bill('embed_batch', texts, data)
            return [item["embedding"] for item in data["data"]]
        except Exception as e:
            _LOG.error("批量 API embedding 失败: %s", e)
            raise

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


class NoOpEmbedding(EmbeddingProvider):
    """无操作 embedding 提供者（返回空向量）。
        English:
    No-op embedding provider (returns empty vectors).
    """

    async def embed(self, text: str) -> list[float]:
        return []

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]


def get_embedding_provider() -> EmbeddingProvider:
    """根据配置获取 embedding 提供者。
        English:
    Get the embedding provider according to configuration.
    """
    provider = CFG.s("EMBEDDING_PROVIDER")

    if provider == "ollama":
        model = CFG.s("EMBEDDING_OLLAMA_MODEL")
        url = CFG.s("EMBEDDING_OLLAMA_URL")
        _LOG.info("使用 Ollama embedding: %s @ %s", model, url)
        return OllamaEmbedding(model=model, base_url=url)

    elif provider == "local":
        model = CFG.s("EMBEDDING_MODEL_LOCAL")
        _LOG.info("使用本地 embedding: %s", model)
        return LocalEmbedding(model_name=model)

    elif provider == "api":
        model = CFG.s("EMBEDDING_MODEL_API")
        _LOG.info("使用 API embedding: %s", model)
        return APIEmbedding(model=model)

    else:  # none
        _LOG.info("embedding 已关闭，使用关键词退化")
        return NoOpEmbedding()


# 全局单例
# [EN] Global singleton
embedding_provider = get_embedding_provider()