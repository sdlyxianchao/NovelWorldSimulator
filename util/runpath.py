# -*- coding: utf-8 -*-
"""运行文件夹的路径工具。

## 为什么值得单开一个模块

这个坑**已经被踩过两次**（`sim/autosave.py` 的 B4 判据抓到过一次，
`sim/resume.py` 第一版又原样踩了一次），所以提出来放在一处：

```
root = Path(getattr(run_folder, 'root', run_folder))     # ← 错！
```

`pathlib.Path` **自带 `.root` 属性**（`PurePath.root`，返回路径的根部件，
Windows 上就是反斜杠）。于是**传一个 `Path` 进来**时，那个 `getattr`
命中的不是"我要的那个运行文件夹"，而是 **pathlib 自己的 `.root`** ——
`root` 当场变成盘根，紧接着 `root / '自动落盘'` 就写到了**当前盘根目录下**，
而且一声不响（`mkdir(parents=True, exist_ok=True)` 会把它建出来）。

`sim/autosave.py` 的 B4（"写不进去时该返回失败"）就是那么抓出来的：
给一个**普通文件**当路径，本该失败，结果它返回成功、`dir` 居然是盘根下那一个。

## 规矩

**判类型，不判属性**：`str` / `PathLike`（含 `Path`）一律当"路本身"；
只有**别的对象**才去取它的 `.root`。

English:
Path utilities for the run folder.
## Why this deserves its own module
This pitfall **has already been stepped on twice** (the B4 criterion in `sim/autosave.py` caught
it once,
and the first version of `sim/resume.py` stepped on it again exactly the same way), so it's
pulled out and put in one place:
```
root = Path(getattr(run_folder, 'root', run_folder))     # ← WRONG!
```
`pathlib.Path` **has a built-in `.root` attribute** (`PurePath.root`, which returns the root
component of the path,
which on Windows is the backslash). So **when you pass a `Path` in**, that `getattr`
doesn't hit "the run folder I want", but rather **pathlib's own `.root`** ——
`root` immediately becomes the drive root, and then `root / '自动落盘'` gets written to **the
current drive root**,
and silently at that (`mkdir(parents=True, exist_ok=True)` will create it).
B4 in `sim/autosave.py` ("should return failure when it can't write") was caught exactly that
way:
given a **regular file** as the path, it should have failed, but instead it returned success and
`dir` turned out to be the one under the drive root.
## Rules
**Check the type, not the attribute**: `str` / `PathLike` (including `Path`) are always treated
as "the path itself";
only **other objects** get their `.root` taken.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def run_root(run_folder: Any) -> Path:
    """把 `RunFolder` 或它的 `Path` 都归一成"运行文件夹根"。

    传什么进来都行：`RunFolder` 对象取它的 `.root`；
    `str` / `Path` / 任何 `os.PathLike` 当路本身（**见模块说明里那个坑**）。
    
        English:
    Normalize both `RunFolder` and its `Path` to the "run folder root".
        Pass in anything: for a `RunFolder` object, take its `.root`;
        `str` / `Path` / any `os.PathLike` is treated as the path itself (**see that pitfall in the module description**).
    """
    if isinstance(run_folder, (str, Path)) or hasattr(run_folder, '__fspath__'):
        return Path(run_folder)
    inner = getattr(run_folder, 'root', None)
    return Path(inner) if inner else Path(run_folder)
