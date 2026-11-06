# -*- coding: utf-8 -*-
"""提示词外置（设计稿 §2.4「AI 工程质量」）。

设计稿原文：
    提示词外置：全部提示词模板放 `prompts/` 文件夹（按用途分文件、带版本注释），
    启动加载、`PROMPT_WATCH=true` 热重载；**用户目录同名文件优先覆盖** ——
    改提示词不动代码，与策略库同一纪律。

两条纪律（与 `world/crowd` 的策略库、`compliance` 的词表同源）
--------------------------------------------------------------
1. **用户目录优先**：`PROMPTS_DIR/<名字>.txt` 存在就用它；否则用内置那份。
   用户改坏了不该让程序崩 —— 读不动就退回内置，并**说一声**（`last_error`）。
2. **热重载按 mtime**（`PROMPT_WATCH`）：改了文件下次取就生效，
   不用重启。关掉时**进程内缓存**，省掉每拍读盘。

内置模板的来源就是代码里原本那段字面量 —— 外置的目的是"**能改**"，
不是"换个地方存"。

English:
Prompts externalized (design doc §2.4 "AI Engineering Quality").
Original design doc text:
    Prompts externalized: all prompt templates go in the `prompts/` folder (split into files by purpose, with version comments),
    loaded at startup, hot-reloaded with `PROMPT_WATCH=true`; **a file of the same name in the user directory takes priority** --
    modifying prompts doesn't touch code, same discipline as the strategy library.
Two disciplines (same origin as the strategy library in `world/crowd` and the word list in
`compliance`)
--------------------------------------------------------------
1. **User directory takes priority**: if `PROMPTS_DIR/<name>.txt` exists, use it; otherwise use the built-in one.
   A user breaking it should not crash the program -- if unreadable, fall back to the built-in one, and **say so** (`last_error`).
2. **Hot reload by mtime** (`PROMPT_WATCH`): changes take effect on the next fetch,
   no restart needed. When off, **cache in-process**, saving a disk read every tick.
The source of the built-in template is exactly the literal that was originally in the code --
the purpose of externalizing is "**being able to change it**",
not "storing it somewhere else".
"""
from __future__ import annotations

import threading
from pathlib import Path

from config import CFG

_LOG = __import__("logging").getLogger("nws.prompts")

_lock = threading.RLock()
# 名字 -> (文本, 来源路径或 None, mtime)
# [EN] name -> (text, source path or None, mtime)
_cache: dict[str, tuple[str, str, float]] = {}
# 最近一次读取失败的原因（给界面/验证脚本看，别让失败静默）
# [EN] Reason for the most recent read failure (for the UI/validation scripts to see, don't let
# [EN] failures be silent)
last_error: str = ""


def prompts_dir() -> Path:
    """用户提示词目录（`PROMPTS_DIR`）。相对路径按程序目录算。
        English:
    User prompt directory (`PROMPTS_DIR`). Relative paths are resolved against the program
    directory.
    """
    raw = (CFG.s("PROMPTS_DIR") or "").strip() or "prompts"
    p = Path(raw)
    if not p.is_absolute():
        try:
            from config import APP_DIR
            p = APP_DIR / p
        except Exception:                                       # noqa: BLE001
            pass
    return p


def builtin_dir() -> Path:
    """内置模板目录（仓库里那份）。
        English:
    Built-in template directory (the one in the repo).
    """
    try:
        from config import APP_DIR
        return APP_DIR / "prompts"
    except Exception:                                       # noqa: BLE001
        return Path("prompts")


def template(name: str, default: str = "") -> tuple[str, str]:
    """取模板 `name`。返回 `(文本, 来源)`；`来源` = `'user'` / `'builtin'` / `'default'`。

    `name` 不带扩展名（`agent_decide_tail` → `agent_decide_tail.txt`）。
    
        English:
    Fetch template `name`. Returns `(text, source)`; `source` = `'user'` / `'builtin'` /
    `'default'`.
        `name` has no extension (`agent_decide_tail` -> `agent_decide_tail.txt`).
    """
    global last_error
    name = str(name or "").strip()
    if not name:
        return default, "default"
    watch = bool(CFG.b("PROMPT_WATCH"))
    key = name
    with _lock:
        cached = _cache.get(key)
    if cached is not None and not watch:
        return cached[0], cached[1]

    for src, d in (("user", prompts_dir()), ("builtin", builtin_dir())):
        p = d / f"{name}.txt"
        try:
            if not p.exists():
                continue
            mtime = p.stat().st_mtime
            if cached is not None and cached[2] == mtime and cached[1] == src:
                return cached[0], src                      # 没改，照旧
                # [EN] Unchanged, as before
            text = p.read_text(encoding="utf-8")
        except Exception as e:                              # noqa: BLE001
            last_error = f"{p}：{e!r}"
            _LOG.warning("提示词 %s 读不动（%r），改用下一份", p, e)
            continue
        if not text.strip():
            last_error = f"{p} 是空的"
            _LOG.warning("提示词 %s 是空的，改用下一份", p)
            continue
        with _lock:
            _cache[key] = (text, src, mtime)
        last_error = ""
        return text, src
    # 两份都没有 → 用代码里的兜底（**永远有得用**，不然推演会断）
    # [EN] Neither exists -> use the fallback in the code (**there is always something usable**, otherwise
    # [EN] the simulation will break)
    with _lock:
        _cache[key] = (default, "default", 0.0)
    return default, "default"


def reload() -> int:
    """清空缓存（`PROMPT_WATCH` 之外的强制重载）。返回清掉了几个。
        English:
    Clear the cache (forced reload independent of `PROMPT_WATCH`). Returns how many were cleared.
    """
    with _lock:
        n = len(_cache)
        _cache.clear()
    return n


def strip_comments(text: str) -> str:
    """去掉以 `#` 开头的整行 —— 那是**给人看的注释**，模型不需要看。

    为什么要有它（2026-10-07）：模板文件的头部十几行是"想改提示词就改这个文件、
    占位符只有这两个"这类**给维护者**的说明。以前它们**原样进了提示词** ——
    每一拍、每个人物都带着一段"对着这个文件改就行"发给模型
    （那一行里的 `prompts/`、`PROMPT_WATCH` 对人物角色是纯粹的噪音，
    还会稀释真正管用的那几条行动纪律）。

    ⚠ 只剥**整行注释**，行中间的 `#` 不动（中文提示词里 `#` 可能是有意义的字符）。
    ⚠ 调用方要**自己记住**：剥完可能只剩空白 → 那时该退回兜底文本。
    
        English:
    Remove whole lines starting with `#` -- those are **comments for humans**, the model doesn't
    need to see them.
        Why this exists (2026-10-07): the first dozen or so lines of a template file are things like "to change the prompt, edit this file,"
        and "there are only these two placeholders" -- notes **for maintainers**. Previously they went **verbatim into the prompt** --
        every tick, every character carried a passage saying "just edit this file" sent to the model
        (the `prompts/` and `PROMPT_WATCH` in that line are pure noise to the character roles,
        and it dilutes the few action disciplines that actually matter).
        ⚠ Only strip **whole-line comments**; a `#` in the middle of a line is untouched (in Chinese prompts `#` may be a meaningful character).
        ⚠ Callers must **remember on their own**: after stripping, only whitespace may remain -> in that case fall back to the default text.
    """
    out: list[str] = []
    for ln in str(text or "").splitlines():
        if ln.lstrip().startswith("#"):
            continue
        out.append(ln)
    return "\n".join(out).strip("\n")


def ensure_builtin(name: str, text: str) -> Path:
    """把一份内置模板写到 `prompts/<name>.txt`（**只在不存在时写**）。

    给"第一次运行就把内置模板摊开给你改"用 —— 与策略库同一做法。
    
        English:
    Write a built-in template to `prompts/<name>.txt` (**only write if it doesn't exist**).
        Used for "on first run, lay out the built-in templates for you to edit" -- same approach as the strategy library.
    """
    p = builtin_dir() / f"{name}.txt"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text(text, encoding="utf-8")
    except Exception as e:                                      # noqa: BLE001
        _LOG.warning("内置提示词落盘失败 %s：%r", p, e)
    return p
