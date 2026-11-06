# -*- coding: utf-8 -*-
"""Configuration for NovelBench -- reads ONLY ``novel_bench/.env``.

Why a separate loader instead of the app's ``config.py``:
the benchmark has to be runnable against different judge models (and different
API keys) than the simulator itself.  Sharing the app config would silently
make "which model graded this run" depend on whatever the user last clicked in
the GUI.

Resolution order for every key:  process env  >  .env  >  built-in default.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BENCH_DIR / ".env"


def _parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


_FILE = _parse_env(ENV_PATH)


def get(key: str, default: str = "") -> str:
    return os.environ.get(key) or _FILE.get(key) or default


def get_int(key: str, default: int) -> int:
    try:
        return int(get(key, str(default)))
    except ValueError:
        return default


def get_float(key: str, default: float) -> float:
    try:
        return float(get(key, str(default)))
    except ValueError:
        return default


def get_bool(key: str, default: bool) -> bool:
    v = get(key, "true" if default else "false").strip().lower()
    return v in ("1", "true", "yes", "on")


@dataclass
class JudgeProfile:
    """One OpenAI-compatible endpoint used as a reviewer."""

    name: str
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 2200
    timeout: int = 180

    @property
    def ready(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


def judge_profiles() -> list[JudgeProfile]:
    """Profiles ``NB_JUDGE*`` / ``NB_JUDGE2*`` / ``NB_JUDGE3*``.

    The first one is the primary; all of them grade every case and the report
    takes the median, which is the cheapest known defence against a single
    model's positional / verbosity bias.
    """
    out: list[JudgeProfile] = []
    for suffix in ("", "2", "3"):
        tag = f"NB_JUDGE{suffix}"
        base = get(f"{tag}_BASE_URL", get("NB_LLM_BASE_URL", ""))
        key = get(f"{tag}_API_KEY", get("NB_LLM_API_KEY", ""))
        model = get(f"{tag}_MODEL", "")
        if not model:
            continue
        out.append(JudgeProfile(
            name=get(f"{tag}_NAME", model),
            base_url=base.rstrip("/"),
            api_key=key,
            model=model,
            temperature=get_float(f"{tag}_TEMPERATURE", 0.0),
            max_tokens=get_int(f"{tag}_MAX_TOKENS", 2200),
            timeout=get_int(f"{tag}_TIMEOUT", 180),
        ))
    return out


@dataclass
class Settings:
    ticks: int = 8
    beat_seconds: int = 1
    time_ratio: int = 1
    case_timeout: int = 900
    output_dir: Path = field(default_factory=lambda: BENCH_DIR / "results")
    work_dir: Path = field(default_factory=lambda: BENCH_DIR / "results" / ".work")
    keep_projects: bool = False
    judge_repeats: int = 1
    judge_max_chars: int = 9000
    pairwise: bool = True
    seed: int = 20261018
    lang: str = "zh"
    # 推演时强制哪一种思考模式（"" = 不碰，跟主程序走）。做 A/B 对比时用。
    think_mode: str = ""
    run_id: str = ""

    @classmethod
    def load(cls) -> "Settings":
        out = cls(
            ticks=get_int("NB_RUN_TICKS", 8),
            beat_seconds=get_int("NB_RUN_BEAT_SECONDS", 1),
            time_ratio=get_int("NB_RUN_TIME_RATIO", 1),
            case_timeout=get_int("NB_RUN_TIMEOUT", 2700),
            keep_projects=get_bool("NB_KEEP_PROJECTS", False),
            judge_repeats=get_int("NB_JUDGE_REPEATS", 1),
            judge_max_chars=get_int("NB_JUDGE_MAX_CHARS", 9000),
            pairwise=get_bool("NB_PAIRWISE", True),
            seed=get_int("NB_SEED", 20261018),
            lang=get("NB_LANG", "zh"),
            think_mode=get("NB_RUN_THINKING_MODE", ""),
        )
        out_dir = get("NB_OUTPUT_DIR", "")
        if out_dir:
            p = Path(out_dir)
            out.output_dir = p if p.is_absolute() else (BENCH_DIR / p)
        out.work_dir = out.output_dir / ".work"
        return out
