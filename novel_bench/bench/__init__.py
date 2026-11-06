# -*- coding: utf-8 -*-
"""NovelBench: an out-of-tree quality benchmark for the novel world simulator.

This package is intentionally independent of the application's own config
module: it reads its own `.env` (``novel_bench/.env``) so that judging models
and keys never mix with the simulator's runtime LLM settings.

Entry point: ``python -m novel_bench.bench.cli`` (see README.md).
"""
from __future__ import annotations

__version__ = "1.0.0"
