# -*- coding: utf-8 -*-
"""把 `.env.example` 与 `config.SPEC` 对齐：保留现有手工注释，补齐缺失的键。

为什么需要它
------------
`.env.example` 是**手工维护**的富化注释版（注释比 `Config.write_example()` 详细得多），
而发布包用 `write_example()` 重新生成（354 键但注释只有一行 desc）。
两份长期演化必然分叉 —— 2026-10-25 实测：样例 234 键、SPEC 354 键，**差 120 个**，
用户照样例配，那 120 个旋钮等于不存在。

做法
----
按 `SPEC` 的组序与键序重排，**每个键的注释优先用现有文件里的那一段**（一个字不改），
没有的才用 `SPEC` 的 `desc`（+ 枚举候选）兜底。于是：
  · 键集合 = SPEC（一个不多、一个不少）
  · 手写注释全部保留
  · 以后加旋钮，重跑一次就补齐

用法
----
    .venv/Scripts/python.exe tools/sync_env_example.py            # 干跑，只报告
    .venv/Scripts/python.exe tools/sync_env_example.py --apply    # 写回
"""
from __future__ import annotations

import sys
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import SPEC, GROUPS, ENV_EXAMPLE_PATH  # noqa: E402

HEADER = """\
# ═══════════════════════════════════════════════════════════════════════════════
# 小说世界AI模拟 · 配置文件
# ═══════════════════════════════════════════════════════════════════════════════
#
# 使用说明：
# 1. 复制此文件为 .env：cp .env.example .env
# 2. 按需要修改配置
# 3. 启动程序：python start.exe（或 python main_gui.py）
#
# 配置指南请参见：配置指南.md
#
# ⚠ 本文件由 tools/sync_env_example.py 与 config.py 的 SPEC 对齐（键集合以 SPEC 为准）。
#   改注释请直接改本文件并重跑脚本 —— 脚本会保留已有注释，只补缺失的键。
#
# ═══════════════════════════════════════════════════════════════════════════════
"""


def read_comments(path: Path) -> dict[str, list[str]]:
    """抽出「键 → 它头顶那一段连续注释」。遇到空行或分组框就断。

    ⚠ **纯占位块要当成"没有注释"**（2026-10-25）：上一版补键时给没有 `desc` 的键写过
      `# （暂无说明）`，而本函数会把它当成有效注释原样保留 ⇒ 后来 `desc` 写好了，
      这行占位仍然杵在那儿，看起来像"这一项还是没说明"。判断口径：整块只有占位行
      （外加"候选"/"要重启"这类脚本自己生成的附加行）时，视为空。
    [EN] ⚠ **A pure placeholder block counts as "no comment"** (2026-10-25): an earlier version wrote
    [EN] `# （暂无说明）` for keys without `desc`, and this function kept it as a valid comment => once
    [EN] `desc` was filled in, the placeholder was still sitting there, looking like "still undocumented".
    [EN] Rule: a block containing only placeholders (plus the script-generated "candidates"/"restart"
    [EN] lines) is treated as empty.
    """
    if not path.exists():
        return {}
    out: dict[str, list[str]] = {}
    block: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").split("\n"):
        s = raw.rstrip()
        if s.startswith("#"):
            if s.startswith(("# ┌", "# │", "# └", "# ══")):
                block = []          # 分组框不是注释，清空累积
            else:
                block.append(s)
            continue
        if not s:
            block = []
            continue
        if "=" in s:
            key = s.split("=", 1)[0].strip()
            if key and block and not _only_placeholder(block):
                out[key] = block[:]
        block = []
    return out


#: 这些行由本脚本自己生成，不构成"人写过的说明"
_AUTO_LINES = ("候选：", "⚠ 改完要重启", "（暂无说明）")


def _only_placeholder(block: list[str]) -> bool:
    for s in block:
        t = s.lstrip("#").strip()
        if not t:
            continue
        if any(t.startswith(a) for a in _AUTO_LINES):
            continue
        return False
    return True


def default_text(spec: dict) -> str:
    d = spec["default"]
    if spec.get("secret"):
        return ""
    if spec["type"] == "bool":
        return "true" if d else "false"
    return "" if d is None else str(d)


def build(comments: dict[str, list[str]]) -> tuple[str, dict]:
    stat = {"kept": 0, "fallback": 0}
    lines = [HEADER]

    for g in GROUPS:
        keys = [k for k, v in SPEC.items() if v["group"] == g]
        if not keys:
            continue
        title = g
        inner = title.center(74)
        lines.append("# ┌" + "─" * 77 + "┐")
        lines.append("# │" + inner + "│")
        lines.append("# └" + "─" * 77 + "┘")
        lines.append("")
        for k in keys:
            spec = SPEC[k]
            if k in comments:
                block = list(comments[k])
                stat["kept"] += 1
            else:
                asc = spec.get("desc") or "（暂无说明）"
                # ⚠ 必须**逐行**加 `#`：`desc` 可能是多行字符串，只在开头拼一次
                #   会让第二行裸着落进文件里 —— 而它常常含 `=`（"设 0 = 不复查"），
                #   于是那行会被后来的解析当成一个**键**（2026-10-25 实测踩到：
                #   产出多出一个叫「跑几轮由 `PROSE_CHECK_ROUNDS` 决定；设 0 」的键）。
                block = ["# " + seg.rstrip() for seg in str(asc).split("\n")]
                stat["fallback"] += 1

            # ★★ 补齐"候选 / 要重启"这两行 —— 但**先查有没有**。
            #   ⚠ 这是幂等的关键：`read_comments` 会把这两行读进注释块，
            #     若无条件再追加一次，每跑一遍就多一份（2026-10-25 实测：
            #     第二次 `--apply` 后文件涨了 108 行，全是重复的「⚠ 改完要重启」）。
            if spec["type"] == "enum":
                opt_line = "# 候选：" + " / ".join(spec["opt"])
                if not any(x.lstrip("# ").startswith("候选：") for x in block):
                    block.append(opt_line)
            if spec.get("restart") and not any("重启" in x for x in block):
                block.append("# ⚠ 改完要重启程序才生效")

            lines.extend(block)
            lines.append(f"{k}={default_text(spec)}")
            lines.append("")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n", stat


def main() -> int:
    apply = "--apply" in sys.argv
    path = Path(ENV_EXAMPLE_PATH)
    comments = read_comments(path)
    text, stat = build(comments)
    # ⚠ 只认"长得像配置键"的行：`^[A-Z][A-Z0-9_]*$`。只按 `=` 切会把注释里
    #   含等号的句子（"设 0 = 不复查"）当成键，而那种"多出来的键"看起来完全正常。
    keys = []
    for ln in text.split("\n"):
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k = ln.split("=", 1)[0].strip()
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", k):
            keys.append(k)
        else:
            print("!! 可疑行（不当成键）:", ln[:90])

    print("SPEC 键数        :", len(SPEC))
    print("现有注释段       :", len(comments))
    print("沿用注释的键     :", stat["kept"])
    print("用 desc 兜底的键 :", stat["fallback"])
    print("产出键数         :", len(keys), "去重后", len(set(keys)))
    missing = [k for k in SPEC if k not in set(keys)]
    extra = [k for k in set(keys) if k not in SPEC]
    print("缺键             :", missing or "无")
    print("多键             :", extra or "无")

    if not apply:
        print("\n[DRY-RUN] 未写盘。加 --apply 执行。")
        return 0
    if missing or extra:
        print("\n!! 键集合不匹配，拒绝写盘")
        return 2
    path.write_text(text, encoding="utf-8")
    print("\n已写回:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
