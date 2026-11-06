# -*- coding: utf-8 -*-
"""文件写入：OneDrive 同步锁很常见，统一走「临时文件 + 替换 + 重试」。
English:
File writing: OneDrive sync locks are very common, so uniformly use "temp file + replace +
retry".
"""
from __future__ import annotations

import os
import time
from pathlib import Path


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_name(name: str) -> str:
    bad = '<>:"/\\|?*'
    for c in bad:
        name = name.replace(c, "_")
    return name.strip().rstrip(".") or "未命名"


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8", retries: int = 5) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    last = None
    for i in range(retries):
        try:
            tmp.write_text(text, encoding=encoding)
            os.replace(tmp, path)
            return
        except (PermissionError, OSError) as e:
            last = e
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            time.sleep(0.15 * (i + 1))
    raise last if last else OSError(f"写入失败：{path}")


def atomic_write_bytes(path: Path, data: bytes, retries: int = 5) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    last = None
    for i in range(retries):
        try:
            tmp.write_bytes(data)
            os.replace(tmp, path)
            return
        except (PermissionError, OSError) as e:
            last = e
            time.sleep(0.15 * (i + 1))
    raise last if last else OSError(f"写入失败：{path}")