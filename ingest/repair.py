# -*- coding: utf-8 -*-
"""开卷时的「AI 自行修复 + 回写引用文件夹」（用户 2026-10-06 要求）。

需求原话
--------
「开卷的时候，AI 找出来的问题如果可以自己修复的，需要 AI 主动修复并回写引用
文件夹里的文档，但是**后续项目开始了就不要去动引用文件夹了**。」

为什么单独一个模块
------------------
1. **它是这个程序里唯一会写用户原始素材的地方。** 摄取、推演、导出一律只读引用
   文件夹 —— 这条"永不反写"的纪律不能破，所以那唯一的例外必须有一个**显式的、
   可审计的**落点，而不是散在 GUI 的某个分支里。
2. **要能被脚本直接测。** 写用户的原稿不可逆，靠手点一遍不算验证。

三条硬规矩（改之前先读）
------------------------
1. **只在开卷阶段写。** `write_back(..., phase=...)` 只认 `'ingest'`，并且
   **项目一旦创建**（`<项目>/*.nwsproj` 落地）就一律拒绝 —— 这就是用户说的
   "后续项目开始了就不要去动引用文件夹"。
2. **只追加，不改写。** 设定类补全一律**追加到目标文件末尾**（带日期小节），
   原有内容一个字符都不动；每个被改的文件先留一份 `<名>.bak`（只留最早那份）。
3. **先列清单，作者点头才动手。** `scan_issues()` 是纯本地判定（零成本、不联网），
   界面靠它列清单；AI 真正生成补全内容是在作者同意**之后**（`build_repairs()`）。

修哪三类（2026-10-06 与用户确认过）
-----------------------------------
| 类别 | 例子 | 怎么修 |
|---|---|---|
| 评档缺口 | 缺伏笔清单 / 人物秘密与口癖 / 大纲 / 世界观太短 | AI 读正文补齐 |
| 人物空缺字段 | 人物条目里空着的 身份·性格·口癖·目标·红线 | AI 读正文补齐 |
| 格式与归类 | 非 UTF-8 的文档、文件名不含类别词 | 就地转 UTF-8（原文不动）；**不改文件名**，写一份读取说明 |

⚠ **不修**的两类缺口（AI 造不出来，硬凑就是编）：`至少 2 个有姓名的人物`、
`正文（至少 1 章）`。

English:
The "AI self-repair + write back to the reference folder" at ingest time (requested by the user
on 2026-10-06).
Original request wording
--------
"At ingest time, if the problems AI finds can be self-repaired, AI needs to proactively repair
them and write them back to the reference
folder's documents, but **once a later project has started, do not touch the reference folder
anymore**."
Why a separate module
------------------
1. **It is the only place in this program that writes to the user's original material.** Ingest, inference, and export are all read-only on the reference
   folder -- this "never write back" discipline must not be broken, so that one exception must have an **explicit,
   auditable** landing point, rather than being scattered in some branch of the GUI.
2. **It must be directly testable by scripts.** Writing to the user's original manuscript is irreversible; verifying by clicking through manually doesn't count.
Three hard rules (read before changing)
------------------------
1. **Only write during the ingest phase.** `write_back(..., phase=...)` only accepts `'ingest'`, and
   **once a project is created** (`<project>/*.nwsproj` lands) it refuses unconditionally -- this is what the user meant by
   "once a later project has started, do not touch the reference folder".
2. **Append only, never rewrite.** Setting-type completions are always **appended to the end of the target file** (with a dated section),
   and not a single character of the original content is touched; each modified file first gets a `<name>.bak` copy (only the earliest one is kept).
3. **List first, act only after the author nods.** `scan_issues()` is a purely local determination (zero cost, no network),
   and the UI relies on it to list issues; AI actually generating completion content happens **after** the author consents (`build_repairs()`).
Which three categories are fixed (confirmed with the user on 2026-10-06)
-----------------------------------
| Category | Example | How to fix |
|---|---|---|
| Missing review items | Missing foreshadowing list / character secrets and verbal tics / outline / worldview too short | AI reads the main text to fill in |
| Missing character fields | Empty identity, personality, verbal tics, goals, red lines in character entries | AI reads the main text to fill in |
| Format and categorization | Non-UTF-8 documents, filenames without category words | Convert to UTF-8 in place (original text untouched); **do not change filenames**, write a reading note |
⚠ Two kinds of gaps **not fixed** (AI cannot produce them; forcing it is fabrication): `at least
2 named characters`,
`main text (at least 1 chapter)`.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from i18n import t
from ingest.scanner import CLASSIFY_NAME, COMPLETION_NAME, load_classify
from llm.replies import ask
from llm import models as MODELS
from util.io import atomic_write_bytes, atomic_write_text
from util.text import fill

_LOG = __import__("logging").getLogger("nws.ingest.repair")

# ── 阶段标记：只有开卷能写 ──
# [EN] ── Phase markers: only writable during ingest ──
PHASE_INGEST = "ingest"

# `COMPLETION_NAME` / `CLASSIFY_NAME` / `load_classify` 都定义在 `ingest/scanner.py`
# （扫描器是最底层的一环，而且它**读**这两个文件）—— 这里只导入，别另写一份。
# [EN] `COMPLETION_NAME` / `CLASSIFY_NAME` / `load_classify` are all defined in `ingest/scanner.py`
# [EN] (the scanner is the lowest layer, and it **reads** these two files) -- only import here, don't
# [EN] write another copy.
BAK_SUFFIX = ".bak"
# 能安全追加文本的后缀。⚠ **不碰 .docx / .html**：它们要么是二进制、
# 要么有标签结构，往里追加纯文本会把用户的文件搞坏。
# [EN] Suffixes to which text can be safely appended. ⚠ **Do not touch .docx / .html**: they are either
# [EN] binary,
# [EN] or have a tag structure, and appending plain text will corrupt the user's file.
APPEND_SUFFIX = {".md", ".txt"}

# 人物条目里"空着就该补"的字段（姓名/简介 不算：姓名必有，简介通常也提得出来）
# [EN] Fields in a character entry that "should be filled if empty" (name/summary excluded: name always
# [EN] exists, summary can usually be extracted too)
EMPTY_FIELDS = ("身份", "性格", "口癖", "目标", "红线")
# 世界观短于这个字数就算"没铺开"，值得补
# [EN] If the worldbuilding is shorter than this character count, it counts as "not fleshed out" and is
# [EN] worth filling in
WORLD_MIN_CHARS = 40
# 一条清单最多列几个"疑似归类错"的文件（再多用户也看不过来）
# [EN] Maximum number of "suspected misclassified" files to list in one list (the user can't read more
# [EN] than that anyway)
MAX_CLASSIFY_ITEMS = 12

# ── Issue 类型 ──
KIND_GAP = "gap"            # 评档缺口
KIND_FIELD = "field"        # 人物空缺字段
KIND_ENCODING = "encoding"  # 非 UTF-8
KIND_CLASSIFY = "classify"  # 文件名不含类别词
# [EN] ── Issue types ──
# [EN] Review gap
# [EN] Missing character fields
# [EN] Non-UTF-8
# [EN] Filename contains no category word

# 缺口 → 目标文件名关键词（按顺序找第一个有内容的文件）
# [EN] Gap -> target filename keyword (find the first file with content in order)
_TARGET_HINTS: dict[str, tuple[tuple[str, ...], str]] = {
    "gap:foreshadow": (("伏笔", "悬念", "线索", "foreshadow"), "伏笔"),
    "gap:secret": (("人物", "角色", "character"), "人物"),
    "gap:outline": (("大纲", "剧情", "梗概", "outline"), "大纲"),
    "gap:world": (("设定", "世界观", "背景", "world"), "设定"),
    KIND_FIELD: (("人物", "角色", "character"), "人物"),
}


# ══════════════════════════════════════════════════════════════
#  数据结构
# [EN] Data structures
# ══════════════════════════════════════════════════════════════
@dataclass
class Issue:
    """一处「查出来、且 AI 能自己修」的问题。

    `title` / `plan` 都是**给人看的一句话**（已走 `t()`），界面直接拿去列清单；
    `target` 是**绝对路径**（'' = 引用文件夹里没有对应文档，补全写到新增的
    `AI补全设定.md`）；`payload` 放结构化数据供 `build_repairs` / `write_back` 用。
    
        English:
    One problem that is "detected and AI can fix itself".
        `title` / `plan` are both **one-line human-readable** (already passed through `t()`); the UI directly takes them to list items;
        `target` is an **absolute path** ('' = no corresponding document in the reference folder; the completion is written to the newly added
        `AI补全设定.md`); `payload` holds structured data for `build_repairs` / `write_back` to use.
    """

    key: str
    kind: str
    title: str
    plan: str
    target: str = ""
    payload: dict = field(default_factory=dict)

    def target_label(self, src_root: Path | None = None) -> str:
        """清单里显示的落点（相对路径更好读）。
                English:
        The target shown in the list (relative path is more readable).
        """
        if not self.target:
            return COMPLETION_NAME
        p = Path(self.target)
        if src_root is not None:
            try:
                return str(p.relative_to(src_root)).replace("\\", "/")
            except ValueError:
                pass
        return p.name


@dataclass
class RepairReport:
    """一次回写的结果（给界面讲给作者听，也给验证脚本断言）。
        English:
    The result of one write-back (told to the UI for the author, and also for the validation script
    to assert on).
    """

    ok: bool = True
    why: str = ""
    phase: str = ""
    appended: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    converted: list[str] = field(default_factory=list)
    backups: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    classify: dict[str, str] = field(default_factory=dict)
    tier_before: str = ""
    tier_after: str = ""

    @property
    def changed(self) -> int:
        return len(self.appended) + len(self.created) + len(self.converted)

    def summary(self) -> str:
        """一句话回执（日志与消息框都用它）。
                English:
        One-line receipt (used by both log and message box).
        """
        if not self.ok:
            return t("没能回写引用文件夹：{why}", why=self.why)
        bits = []
        if self.appended:
            bits.append(t("追加 {n} 篇", n=len(self.appended)))
        if self.created:
            bits.append(t("新增 {n} 篇", n=len(self.created)))
        if self.converted:
            bits.append(t("转码 {n} 篇", n=len(self.converted)))
        if self.classify:
            bits.append(t("归类说明 {n} 条", n=len(self.classify)))
        if not bits:
            return t("没有需要改动的文件")
        out = t("已回写引用文件夹：") + "、".join(bits)
        if self.backups:
            out += t("（原件备份为 {n} 份 .bak）", n=len(self.backups))
        if self.skipped:
            out += t("；{n} 项跳过", n=len(self.skipped))
        return out

    def detail_lines(self) -> list[str]:
        """逐条明细（日志栏里一行一条）。
                English:
        Per-item details (one line per item in the log panel).
        """
        lines = []
        for p in self.appended:
            lines.append(t("· 追加补全 → {p}", p=p))
        for p in self.created:
            lines.append(t("· 新建文档 → {p}", p=p))
        for p in self.converted:
            lines.append(t("· 转为 UTF-8 → {p}", p=p))
        for p, why in self.skipped:
            lines.append(t("· 跳过 {p}：{why}", p=p, why=why))
        return lines


# ══════════════════════════════════════════════════════════════
#  1. 本地扫"有哪些可修的问题"（零成本、不联网）
# [EN] 1. Locally scan "what fixable problems exist" (zero cost, no network)
# ══════════════════════════════════════════════════════════════
def scan_issues(items: Iterable, settings: dict[str, Any], *,
                missing_for_gold: Iterable[str] = (),
                tier: str = "", src_root: Path | None = None) -> list[Issue]:
    """把「能自动修的问题」找出来（**只做本地判定，不调模型**）。

    界面拿这份清单给作者过目；作者点头之后才轮到 `build_repairs()` 花钱。
    `missing_for_gold` 传 `IngestResult.missing_for_gold`（评档缺口）。
    
        English:
    Find the "problems that can be auto-fixed" (**local determination only, no model calls**).
        The UI takes this list to the author for review; only after the author nods does `build_repairs()` get to spend money.
        `missing_for_gold` is passed `IngestResult.missing_for_gold` (missing review items).
    """
    items = [it for it in items if getattr(it, "content", "")]
    out: list[Issue] = []
    chars = [c for c in (settings.get("人物") or []) if isinstance(c, dict)]

    # ── A. 评档缺口（只挑 AI 真能补的）──
    # ⚠ `至少 2 个有姓名的人物` 与 `正文（至少 1 章）` **不在列表里**：
    #   AI 造不出人物和正文，硬凑就是编 —— 那比"缺着"更坏。
    # [EN] ── A. Review gaps (only pick ones AI can actually fill) ──
    # [EN] ⚠ `at least 2 characters with names` and `body text (at least 1 chapter)` are **not in the
    # [EN] list**:
    # [EN] AI cannot fabricate characters and body text; forcing it is making things up -- that's worse
    # [EN] than "missing".
    def _gap(key: str, title: str, plan_tpl: str, *, payload: dict | None = None) -> Issue:
        hint_kws, cat = _TARGET_HINTS[key]
        tg = _pick_target(items, hint_kws, cat)
        return Issue(key, KIND_GAP, title,
                     t(plan_tpl, f=_target_label(tg, src_root)),
                     target=tg, payload=payload or {})

    if not (settings.get("伏笔") or []):
        out.append(_gap("gap:foreshadow", t("缺 伏笔清单"),
                        "AI 读正文找出埋设点与预计回收点，追加到 {f} 末尾"))

    if chars and not any(str(c.get("秘密") or c.get("口癖") or "").strip() for c in chars):
        out.append(_gap("gap:secret", t("人物没有秘密 / 口癖"),
                        "AI 从正文推断每位人物的秘密与口癖，写入 {f}",
                        payload={"names": [str(c.get("姓名") or "") for c in chars][:12]}))

    if not str(settings.get("剧情参考线") or "").strip():
        out.append(_gap("gap:outline", t("缺 大纲 / 剧情参考线"),
                        "AI 读正文概括一条「起承转合」线，追加到 {f} 末尾"))

    world = str(settings.get("世界观") or "").strip()
    if len(world) < WORLD_MIN_CHARS:
        out.append(_gap("gap:world", t("世界观太短（{n} 字）", n=len(world)),
                        "AI 读正文铺开一段世界观（120 字内），追加到 {f} 末尾"))

    # ── B. 人物空缺字段（合并成一条，免得清单被刷屏）──
    # [EN] ── B. Missing character fields (merged into one entry, to avoid spamming the list) ──
    vacant: dict[str, list[str]] = {}
    for c in chars:
        nm = str(c.get("姓名") or "").strip()
        if not nm or nm == "未知":
            continue
        holes = [f for f in EMPTY_FIELDS if not str(c.get(f) or "").strip()]
        if holes:
            vacant[nm] = holes
    if vacant:
        n_holes = sum(len(v) for v in vacant.values())
        hint_kws, cat = _TARGET_HINTS[KIND_FIELD]
        tg = _pick_target(items, hint_kws, cat)
        out.append(Issue(
            "field:people", KIND_FIELD,
            t("人物空缺字段（{p} 位 · 共 {n} 处）", p=len(vacant), n=n_holes),
            t("AI 从正文补齐这些字段，写入 {f}", f=_target_label(tg, src_root)),
            target=tg, payload={"vacant": vacant}))

    # ── C. 格式：非 UTF-8 的文本文件 ──
    # [EN] ── C. Format: non-UTF-8 text files ──
    for it in items:
        p = Path(getattr(it, "path", ""))
        if p.suffix.lower() not in APPEND_SUFFIX:
            continue
        enc = _bad_encoding(p)
        if not enc:
            continue
        out.append(Issue(
            f"encoding:{_rel(p, src_root)}", KIND_ENCODING,
            t("{name} 不是 UTF-8（{enc}）", name=p.name, enc=enc),
            t("转成 UTF-8（正文一字不改，旧文件先备份为 {name}{bak}）",
              name=p.name, bak=BAK_SUFFIX),
            target=str(p), payload={"encoding": enc}))

    # ── D. 归类：文件名/路径不含任何类别词（内容白读了）──
    # [EN] ── D. Classification: filename/path contains no category word (content read for nothing) ──
    odd = [it for it in items
           if getattr(it, "category", "") == "杂项"
           and Path(getattr(it, "path", "")).suffix.lower() in APPEND_SUFFIX]
    if odd:
        names = [_rel(Path(it.path), src_root) for it in odd[:MAX_CLASSIFY_ITEMS]]
        out.append(Issue(
            "classify:odd", KIND_CLASSIFY,
            t("{n} 个文件看不出属于哪一类", n=len(odd)),
            t("AI 判断它们其实是哪一类，写进 {f}（**不改你的文件名**）",
              f=COMPLETION_NAME),
            target="", payload={"files": names, "total": len(odd)}))
    return out


def _rel(p: Path, src_root: Path | None) -> str:
    if src_root is not None:
        try:
            return str(p.relative_to(src_root)).replace("\\", "/")
        except ValueError:
            pass
    return p.name


def _target_label(target: str, src_root: Path | None) -> str:
    """清单里显示的落点：`''`（没有对应文档）就说那个补全文档的名字。
        English:
    The target shown in the list: if `''` (no corresponding document), say the name of that
    completion document.
    """
    return _rel(Path(target), src_root) if target else COMPLETION_NAME


def _pick_target(items: list, keywords: tuple[str, ...], category: str) -> str:
    """挑一个已存在的目标文档（绝对路径字符串）。

    先按**文件名关键词**找（`伏笔.md` 这种最贴），找不到再退到**同类别的第一个
    文件**（用户那份设定全写在一个 `设定.md` 里也能补进去）。
    都没有就返回 `''` —— 调用方据此把补全写到新增的 `AI补全设定.md`。
    
        English:
    Pick an existing target document (absolute path string).
        First search by **filename keyword** (`伏笔.md` and the like fit best); if not found, fall back to the **first file of the same category**
        (if the user wrote all their settings in a single `设定.md`, it can still be filled in).
        If neither exists, return `''` — the caller uses this to write the completion to the newly added `AI补全设定.md`.
    """
    for kw in keywords:
        for it in items:
            if kw in str(getattr(it, "name", "")).lower():
                return str(Path(it.path))
    if category:
        for it in items:
            if getattr(it, "category", "") == category:
                return str(Path(it.path))
    return ""


def _bad_encoding(path: Path) -> str:
    """这个文件不是 UTF-8 吗？返回探测到的编码名（是 UTF-8 则返回 ''）。
        English:
    Is this file not UTF-8? Return the detected encoding name (return '' if it is UTF-8).
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    if not raw:
        return ""
    try:
        raw.decode("utf-8-sig")
        return ""
    except UnicodeDecodeError:
        pass
    try:
        import chardet
        det = chardet.detect(raw[:10000])
        return str(det.get("encoding") or "未知编码")
    except Exception:                                      # noqa: BLE001
        return "未知编码"


# ══════════════════════════════════════════════════════════════
#  2. 让 AI 产出补全内容（**作者同意之后**才调用）
# [EN] 2. Have AI produce the completion content (only called **after author consent**)
# ══════════════════════════════════════════════════════════════
_MAX_SOURCE = 12000
_MAX_SETTINGS_JSON = 6000
_REPAIR_MAX_TOKENS = 4000

_REPAIR_PROMPT = """你是一位小说项目的资料整理助手。作者的小说素材里有几处缺口，
请你**读正文**把它们补齐 —— 只补下面「要补的东西」里列的，别的一概不要动。

项目名称：{name}
评档：{tier}

现有的结构化设定（JSON）：
---
{settings_json}
---

正文节选：
---
{novel}
---

要补的东西：
{todo}

硬性要求（违反任何一条，这次输出都算失败）：
- **只依据上面给的正文与设定来写**。正文里推不出来的，宁可留空字符串，**不要编**。
- 每一条都写短：字段 ≤ 30 字，伏笔每条 ≤ 25 字，大纲/世界观 ≤ 120 字。
- 只输出 JSON，不要解释、不要开场白、不要 ```json 代码块。
- 顶层 key 只允许这几个（没有要补的就给空数组 / 空字符串）：
  {{"人物字段": [{{"姓名": "…", "补": {{"身份": "…", "性格": "…", "口癖": "…",
   "目标": "…", "红线": "…", "秘密": "…"}}}}],
   "伏笔": [{{"编号": "F1", "内容": "…", "埋设": "…", "预计回收": "…"}}],
   "大纲": "起…承…转…合…",
   "世界观": "…",
   "归类": [{{"文件": "…", "类别": "正文/人物/大纲/伏笔/设定（五选一）", "理由": "…"}}]}}
"""


async def build_repairs(issues: list[Issue], items: Iterable, settings: dict[str, Any], *,
                        name: str = "", tier: str = "") -> dict[str, Any]:
    """按清单让 AI 生成补全内容（一次调用），返回结构化结果。

    拿不到可用结果时**返回空 dict**（调用方据此说"这次没补上"，而不是写半截东西）。
    
        English:
    Have AI generate completion content per the list (one call), returning structured results.
        When no usable result is obtained, **return an empty dict** (the caller uses this to say "nothing was filled in this time" rather than writing half-baked stuff).
    """
    todo = _todo_text(issues)
    if not todo:
        return {}
    novel = "\n".join(str(getattr(it, "content", "") or "") for it in items
                      if getattr(it, "category", "") in ("正文", "大纲"))
    if not novel:
        novel = "\n".join(str(getattr(it, "content", "") or "") for it in items)
    if len(novel) > _MAX_SOURCE:
        from util.text import truncate_mid
        novel = truncate_mid(novel, _MAX_SOURCE)

    sjson = json.dumps(settings, ensure_ascii=False, indent=1)
    if len(sjson) > _MAX_SETTINGS_JSON:
        sjson = sjson[:_MAX_SETTINGS_JSON] + "\n…（已截断）"

    rep = await ask("cheap",
                    [{"role": "user", "content": fill(
                        _REPAIR_PROMPT, name=name or "（未命名）", tier=tier or "未知",
                        settings_json=sjson, novel=novel, todo=todo)}],
                    purpose="repair_source", want=dict, json_mode=True,
                    max_tokens=_REPAIR_MAX_TOKENS, temperature=0.3, default=None)
    if not isinstance(rep.value, dict) or not rep.value:
        _LOG.warning("AI 补全拿不到可用结果：%s", "；".join(rep.notes))
        return {}
    if rep.notes:
        _LOG.info("AI 补全：%s", rep.notes)
    out = dict(rep.value)
    out["_notes"] = list(rep.notes)
    return out


def _todo_text(issues: list[Issue]) -> str:
    """把清单翻译成"给模型看"的待办（模型看的，不走 i18n）。
        English:
    Translate the list into "for the model to see" to-dos (for the model, not going through i18n).
    """
    lines = []
    for i, iss in enumerate(issues, 1):
        if iss.kind == KIND_GAP:
            what = {
                "gap:foreshadow": "补一份伏笔清单（编号 / 内容 / 埋设 / 预计回收），"
                                  "写进 \"伏笔\" 字段",
                "gap:secret": "给每个人物补上「秘密」与「口癖」，写进 \"人物字段\"",
                "gap:outline": "概括一条「起承转合」的剧情参考线，写进 \"大纲\"",
                "gap:world": "把世界观铺开成 120 字以内的一段，写进 \"世界观\"",
            }.get(iss.key, iss.title)
        elif iss.kind == KIND_FIELD:
            names = list((iss.payload.get("vacant") or {}).keys())
            what = ("把这些人物的空缺字段补齐（只补空着的），写进 \"人物字段\"："
                    + "、".join(names))
        elif iss.kind == KIND_CLASSIFY:
            files = iss.payload.get("files") or []
            what = ("判断这几个素材文件各属于哪一类（正文/人物/大纲/伏笔/设定），"
                    "写进 \"归类\"：" + "、".join(files))
        else:
            continue
        lines.append(f"{i}. {what}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
#  3. 把补全并进设定 + 渲染成可追加的正文块
# [EN] 3. Merge the completions into the settings + render them into appendable body-text blocks
# ══════════════════════════════════════════════════════════════
def merge_into_settings(settings: dict[str, Any],
                        repairs: dict[str, Any]) -> tuple[dict, list[str]]:
    """把 AI 补全**并进**设定 dict（只填空，不覆盖已有内容）。

    返回 `(新设定, 变更说明)`。变更说明是给人看的一行行字（走日志）。
    ⚠ **只填空** —— AI 的补全不该盖掉作者原本写好的东西。
    
        English:
    **Merge** the AI completion into the settings dict (only fill blanks, do not overwrite existing
    content).
        Return `(new settings, change notes)`. Change notes are human-readable lines (via log).
        ⚠ **Only fill blanks** — AI completion should not overwrite what the author originally wrote.
    """
    import copy
    out = copy.deepcopy(settings) if settings else {}
    notes: list[str] = []

    by_name = {str(c.get("姓名") or ""): c for c in (out.get("人物") or [])
               if isinstance(c, dict)}
    for row in (repairs.get("人物字段") or []):
        if not isinstance(row, dict):
            continue
        nm = str(row.get("姓名") or "").strip()
        patch = row.get("补") if isinstance(row.get("补"), dict) else {}
        tgt = by_name.get(nm)
        if tgt is None or not patch:
            continue
        done = []
        for k, v in patch.items():
            if k in EMPTY_FIELDS or k == "秘密":
                if not str(tgt.get(k) or "").strip() and str(v or "").strip():
                    tgt[k] = str(v).strip()
                    done.append(k)
        if done:
            notes.append(t("· {name}：补上 {fields}", name=nm, fields="、".join(done)))

    if repairs.get("伏笔") and not (out.get("伏笔") or []):
        rows = [r for r in repairs["伏笔"] if isinstance(r, dict)]
        if rows:
            out["伏笔"] = [{"编号": str(r.get("编号") or f"F{i + 1}"),
                            "内容": str(r.get("内容") or ""),
                            "埋设": str(r.get("埋设") or ""),
                            "预计回收": str(r.get("预计回收") or "")}
                           for i, r in enumerate(rows)]
            notes.append(t("· 补上 {n} 条伏笔", n=len(out["伏笔"])))

    if repairs.get("大纲") and not str(out.get("剧情参考线") or "").strip():
        out["剧情参考线"] = str(repairs["大纲"]).strip()
        notes.append(t("· 补上剧情参考线"))

    if repairs.get("世界观"):
        if len(str(out.get("世界观") or "").strip()) < WORLD_MIN_CHARS:
            out["世界观"] = str(repairs["世界观"]).strip()
            notes.append(t("· 补上世界观"))
    return out, notes


def render_appendix(repairs: dict[str, Any], *, issues: list[Issue],
                    src_root: Path | None = None,
                    want_keys: set[str] | None = None) -> str:
    """把补全内容渲染成一段 Markdown（**追加**到目标文件末尾用）。

    `want_keys` 限定只渲染这几个 Issue 对应的段落（同一份补全可能落到不同文件：
    伏笔进 `伏笔.md`、人物字段进 `人物.md`）。None = 全都渲染。
    
        English:
    Render the completion content into a Markdown passage (for **appending** to the end of the
    target file).
        `want_keys` limits rendering to only the passages corresponding to these Issues (the same completion may land in different files:
        foreshadowing into `伏笔.md`, character fields into `人物.md`). None = render all.
    """
    def _want(k: str) -> bool:
        return want_keys is None or k in want_keys

    stamp = __import__("time").strftime("%Y-%m-%d %H:%M")
    lines = [f"## AI 补全（{stamp}）",
             "",
             t("> 下面这一段是开卷导入时由 AI 读正文补写的；"
               "**原有的内容一字未动**，可以放心对照。"),
             ""]

    if _want("field:people") or _want("gap:secret"):
        rows = [r for r in (repairs.get("人物字段") or []) if isinstance(r, dict)]
        shown = []
        for r in rows:
            nm = str(r.get("姓名") or "").strip()
            patch = r.get("补") if isinstance(r.get("补"), dict) else {}
            pairs = [f"{k}：{str(v).strip()}" for k, v in patch.items()
                     if str(v or "").strip()]
            if nm and pairs:
                shown.append(f"- **{nm}**　" + "；".join(pairs))
        if shown:
            lines += ["### " + t("人物补充"), ""] + shown + [""]

    if _want("gap:foreshadow"):
        rows = [r for r in (repairs.get("伏笔") or []) if isinstance(r, dict)]
        shown = []
        for i, r in enumerate(rows, 1):
            c = str(r.get("内容") or "").strip()
            if not c:
                continue
            bits = [str(r.get("埋设") or "").strip(), str(r.get("预计回收") or "").strip()]
            tail = "　（" + " · ".join(b for b in bits if b) + "）" if any(bits) else ""
            shown.append(f"- [{str(r.get('编号') or f'F{i}')}] {c}{tail}")
        if shown:
            lines += ["### " + t("伏笔"), ""] + shown + [""]

    if _want("gap:outline") and str(repairs.get("大纲") or "").strip():
        lines += ["### " + t("剧情参考线"), "", str(repairs["大纲"]).strip(), ""]

    if _want("gap:world") and str(repairs.get("世界观") or "").strip():
        lines += ["### " + t("世界观"), "", str(repairs["世界观"]).strip(), ""]

    if _want("classify:odd"):
        rows = [r for r in (repairs.get("归类") or []) if isinstance(r, dict)]
        shown = []
        for r in rows:
            f = str(r.get("文件") or "").strip()
            c = str(r.get("类别") or "").strip()
            if f and c:
                why = str(r.get("理由") or "").strip()
                shown.append(f"- `{f}` → {c}" + (f"（{why}）" if why else ""))
        if shown:
            lines += ["### " + t("本次读取说明"), "",
                      t("- 下面这几个文件的名字里没有类别词，AI 判断它们其实是："), ""]
            lines += shown + [""]

    if len(lines) <= 4:          # 只有标题和说明，说明什么都没补上
    # [EN] Only title and description, meaning nothing was actually filled in
        return ""
    return "\n".join(lines).rstrip() + "\n"


# ══════════════════════════════════════════════════════════════
#  4. 回写（**唯一写盘的地方**，护栏都在这）
# [EN] 4. Write back (**the only place that writes to disk**, all guardrails are here)
# ══════════════════════════════════════════════════════════════
def write_back(src_root: Path, *, phase: str,
               appends: list[tuple[Path, str]] | None = None,
               convert: list[Path] | None = None,
               classify: dict[str, str] | None = None,
               project_root: Path | None = None) -> RepairReport:
    """把补全写回引用文件夹。**这是全程序唯一会写用户原始素材的地方。**

    - `phase` **只认 `'ingest'`**：调用点必须自己声明"我在开卷阶段"。
    - `project_root` 一旦已经有 `*.nwsproj`（= 这本书已经开卷了），一律拒绝 ——
      用户原话：「后续项目开始了就不要去动引用文件夹了」。
    - 每个要改的文件先留一份 `<名>.bak`（**已存在就不覆盖**：保留的是
      "第一次让 AI 改之前"的样子，那个版本最有用）。
    - 任何一个文件写失败 → 记进 `skipped`，**继续处理下一个**（不半途而废，
      也不假装成功）。
    
        English:
    Write the completion back to the reference folder. **This is the only place in the whole program
    that writes the user's original material.**
        - `phase` **only accepts `'ingest'`**: the call site must itself declare "I am in the ingest phase".
        - Once `project_root` already has `*.nwsproj` (= this book has already been ingested), always refuse —
          the user's exact words: "once a follow-up project has started, don't touch the reference folder".
        - For each file to be modified, first keep a `<name>.bak` (**do not overwrite if it already exists**: what is preserved is
          the state "before the first AI modification"; that version is the most useful).
        - If any file write fails → record into `skipped`, **continue to the next one** (do not give up halfway,
          and do not pretend success).
    """
    src_root = Path(src_root)
    rep = RepairReport(phase=phase)
    if phase != PHASE_INGEST:
        rep.ok, rep.why = False, t("只允许在开卷阶段回写引用文件夹")
        return rep
    if project_root is not None and list(Path(project_root).glob("*.nwsproj")):
        rep.ok, rep.why = False, t("项目已经开始，不再改动引用文件夹")
        return rep
    if not src_root.is_dir():
        rep.ok, rep.why = False, t("引用文件夹不存在")
        return rep

    # ── ① 编码转换（就地重写，正文一字不改）──
    # [EN] ── ① Encoding conversion (rewrite in place, not a single character of body text changed) ──
    #
    # ★ **全程走字节，不走 `write_text`**（2026-10-06 实测踩到）：
    #   `Path.write_text` 在 Windows 上是**通用换行模式** —— 文本里的 `\n` 会被
    #   翻译成 `\r\n`。而用户那份 UTF-16 文件里本来就有 `\r\n`（解码后已经在
    #   字符串里了），再经 `write_text` 写一遍就成了 `\r\r\n`，读回来**每行多一个
    #   空行**。追加补全那段同理：LF 的文件会被整篇换成 CRLF（"只增不改"就成了空话）。
    #   所以：读字节 → 解码成 str → `encode('utf-8')` → 写字节。换行一个字节不动。
    # [EN] ★ **Go through bytes the whole way, do not use `write_text`** (actually hit this on 2026-10-06):
    # [EN] `Path.write_text` on Windows is in **universal newline mode** -- `\n` in the text gets
    # [EN] translated to `\r\n`. And the user's UTF-16 file already has `\r\n` in it (after decoding it's
    # [EN] already in
    # [EN] the string), and after going through `write_text` once more it becomes `\r\r\n`, so reading it
    # [EN] back gives **one extra
    # [EN] blank line per line**. Same for the append-completion part: an LF file gets the whole thing
    # [EN] converted to CRLF ("append only" becomes an empty promise).
    # [EN] So: read bytes -> decode to str -> `encode('utf-8')` -> write bytes. Not a single byte of
    # [EN] newline is touched.
    for p in (convert or []):
        p = Path(p)
        why = _guard_target(p, src_root)
        if why:
            rep.skipped.append((_rel(p, src_root), why))
            continue
        try:
            raw = p.read_bytes()
        except OSError as e:
            rep.skipped.append((_rel(p, src_root), t("读不了：{e}", e=e)))
            continue
        if not raw:
            continue
        try:
            text = raw.decode("utf-8-sig")          # 已经是 UTF-8（可能带 BOM）→ 只去 BOM
            # [EN] Already UTF-8 (possibly with BOM) -> only strip the BOM
        except UnicodeDecodeError:
            try:
                import chardet
                enc = chardet.detect(raw[:10000]).get("encoding") or ""
                if not enc:
                    rep.skipped.append((_rel(p, src_root), t("认不出它是什么编码")))
                    continue
                text = raw.decode(enc)
            except Exception as e:                          # noqa: BLE001
                rep.skipped.append((_rel(p, src_root), t("转码失败：{e}", e=e)))
                continue
        try:
            _backup(p, rep)
            if text.encode("utf-8") == raw:
                continue                                    # 本来就没变，别白写一次盘
                # [EN] Nothing actually changed, don't waste a disk write
            atomic_write_bytes(p, text.encode("utf-8"))
            rep.converted.append(_rel(p, src_root))
        except OSError as e:
            rep.skipped.append((_rel(p, src_root), t("写不进去：{e}", e=e)))

    # ── ② 追加补全（原文的**字节**一个都不动，只在末尾接一段）──
    # [EN] ── ② Append completions (not a single **byte** of the original is touched, just append a section
    # [EN] at the end) ──
    for p, block in (appends or []):
        p = Path(p)
        if not (block or "").strip():
            continue
        why = _guard_target(p, src_root)
        if why:
            rep.skipped.append((_rel(p, src_root), why))
            continue
        try:
            existed = p.exists()
            raw = p.read_bytes() if existed else b""
            old = raw.decode("utf-8")
        except UnicodeDecodeError:
            # 不是 UTF-8 就**别动它** —— 解码出来的字符是错的，往后面接一段
            # 等于把用户的文件写坏（转码那一步会先把它修好，这里只兜"没人要求转码"）
            # [EN] If it's not UTF-8, **don't touch it** -- the decoded characters are wrong, and appending a
            # [EN] section afterward
            # [EN] means corrupting the user's file (the transcoding step will fix it first; here we only cover the
            # [EN] "nobody asked for transcoding" case)
            rep.skipped.append((_rel(p, src_root), t("不是 UTF-8，先别动它（避免写坏）")))
            continue
        except OSError as e:
            rep.skipped.append((_rel(p, src_root), t("读不了：{e}", e=e)))
            continue
        try:
            if existed:
                _backup(p, rep)
            sep = b"" if (not raw or raw.endswith(b"\n")) else b"\n"
            head = b"" if not raw else b"\n\n"
            atomic_write_bytes(p, raw + sep + head + block.encode("utf-8"))
            (rep.appended if existed else rep.created).append(_rel(p, src_root))
        except OSError as e:
            rep.skipped.append((_rel(p, src_root), t("写不进去：{e}", e=e)))

    # ── ③ 归类修正表（**扫描器会读** —— 让推断真的生效，而不只是写给人看）──
    # [EN] ── ③ Classification correction table (**the scanner reads it** -- so the inference actually
    # [EN] takes effect, not just written for humans to read) ──
    if classify:
        try:
            tbl = load_classify(src_root)
            tbl.update({str(k).replace("\\", "/"): str(v) for k, v in classify.items()})
            atomic_write_text(src_root / CLASSIFY_NAME,
                              json.dumps(tbl, ensure_ascii=False, indent=2))
            rep.classify = dict(classify)
        except OSError as e:
            rep.skipped.append((CLASSIFY_NAME, t("写不进去：{e}", e=e)))

    _LOG.info("回写引用文件夹：追加 %d · 新增 %d · 转码 %d · 跳过 %d",
              len(rep.appended), len(rep.created), len(rep.converted), len(rep.skipped))
    return rep


def _guard_target(p: Path, src_root: Path) -> str:
    """能不能写这个文件？返回拒绝原因（'' = 可以）。

    三条护栏（**任何一条不过都不许写**）：
      ① 必须**在引用文件夹里面**（挡 `..`、绝对路径乱指、符号链接逃逸）；
      ② 后缀必须是能安全追加文本的（`.md` / `.txt`）—— 不碰 docx/其它；
      ③ 不许动程序自己生成的补全文档以外的隐藏/临时文件。
    
        English:
    Can this file be written? Return the refusal reason ('' = ok).
        Three guardrails (**if any one fails, writing is not allowed**):
          ① Must be **inside the reference folder** (blocks `..`, absolute path misdirection, symlink escape);
          ② The suffix must be one that can safely append text (`.md` / `.txt`) — do not touch docx/others;
          ③ Do not touch hidden/temporary files other than the completion document generated by the program itself.
    """
    try:
        rp, rs = p.resolve(), Path(src_root).resolve()
        rp.relative_to(rs)
    except (OSError, ValueError):
        return t("拒绝：目标不在引用文件夹里")
    if p.suffix.lower() not in APPEND_SUFFIX:
        return t("拒绝：只改 .md / .txt 文档")
    if p.name.startswith("."):
        return t("拒绝：不动隐藏文件")
    return ""


def _backup(p: Path, rep: RepairReport) -> None:
    """就地留一份 `<名>.bak`。**已存在就不覆盖**（保留最早那份，最能救命）。
        English:
    Keep a `<name>.bak` in place. **Do not overwrite if it already exists** (keep the earliest one;
    it saves the most).
    """
    bak = p.with_name(p.name + BAK_SUFFIX)
    if bak.exists():
        return
    shutil.copy2(p, bak)
    rep.backups.append(bak.name)


# ══════════════════════════════════════════════════════════════
#  5. 归类修正表（scanner 读它，见 `ingest.scanner.load_classify`）
# [EN] 5. Classification correction table (scanner reads it, see `ingest.scanner.load_classify`)
# ══════════════════════════════════════════════════════════════
def classify_map_from_repairs(repairs: dict[str, Any]) -> dict[str, str]:
    """把 AI 的「归类」结果转成修正表（只认五个合法类别）。
        English:
    Convert the AI's "categorization" results into a correction table (only five legal categories
    accepted).
    """
    ok_cats = {"正文", "人物", "大纲", "伏笔", "设定"}
    out: dict[str, str] = {}
    for r in (repairs.get("归类") or []):
        if not isinstance(r, dict):
            continue
        f = str(r.get("文件") or "").strip().replace("\\", "/")
        c = str(r.get("类别") or "").strip()
        if f and c in ok_cats:
            out[f] = c
    return out


# ══════════════════════════════════════════════════════════════
#  6. 编排：清单 → 同意 → 生成 → 回写（GUI 只调这一个）
# [EN] 6. Orchestration: list -> consent -> generate -> write back (GUI only calls this one)
# ══════════════════════════════════════════════════════════════
@MODELS.agent('ingest')
async def run_repairs(issues: list[Issue], items: Iterable, settings: dict[str, Any], *,
                      src_root: Path, phase: str = PHASE_INGEST,
                      project_root: Path | None = None,
                      name: str = "", tier: str = "",
                      on_note=None) -> tuple[dict, RepairReport, list[str]]:
    """走完整条链：AI 生成补全 → 并进设定 → 写回引用文件夹。

    返回 `(设定, 报告, 变更说明)`；`on_note(line)` 有的话逐条喂给界面日志。
    ⚠ 只能在这个函数里写引用文件夹 —— 别在别处另开一条路。
    
        English:
    Run the whole chain: AI generates completion → merge into settings → write back to reference
    folder.
        Return `(settings, report, change notes)`; if `on_note(line)` exists, feed each entry to the UI log.
        ⚠ Only this function may write to the reference folder — do not open another path elsewhere.
    """
    def _note(msg: str) -> None:
        if on_note:
            try:
                on_note(msg)
            except Exception:                                # noqa: BLE001
                pass

    issues = list(issues)
    ai_issues = [i for i in issues if i.kind in (KIND_GAP, KIND_FIELD, KIND_CLASSIFY)]
    repairs: dict = {}
    if ai_issues:
        repairs = await build_repairs(ai_issues, items, settings, name=name, tier=tier)
        for n in (repairs.get("_notes") or []):
            _note(f"! AI 补全：{n}")
        if not repairs:
            _note(t("! AI 没能给出补全内容（详见对话日志）—— 引用文件夹不会改动"))

    new_settings, settings_notes = merge_into_settings(settings, repairs)
    for line in settings_notes:
        _note(line)

    # 按 Issue 分桶：同一份补全里，伏笔进 `伏笔.md`、人物字段进 `人物.md`…
    # [EN] Bucket by Issue: within the same completion, foreshadowing goes into `伏笔.md`, character fields
    # [EN] into `人物.md`...
    by_target: dict[Path, set[str]] = {}
    for iss in issues:
        if iss.kind == KIND_CLASSIFY:
            keys = {"classify:odd"}
        elif iss.kind == KIND_GAP and iss.key == "gap:secret":
            keys = {"field:people", "gap:secret"}
        elif iss.kind == KIND_FIELD:
            keys = {"field:people", "gap:secret"}
        else:
            keys = {iss.key}
        tgt = Path(iss.target) if iss.target else (src_root / COMPLETION_NAME)
        by_target.setdefault(tgt, set()).update(keys)

    appends: list[tuple[Path, str]] = []
    for tgt, keys in by_target.items():
        block = render_appendix(repairs, issues=issues, src_root=src_root,
                                want_keys=keys)
        if block:
            appends.append((tgt, block))

    convert = [Path(i.target) for i in issues if i.kind == KIND_ENCODING]
    classify = classify_map_from_repairs(repairs) if repairs else {}

    if not appends and not convert and not classify:
        rep = RepairReport(phase=phase)
        if not ai_issues:
            rep.ok, rep.why = False, t("没有可自动修复的问题")
        return new_settings, rep, settings_notes

    rep = write_back(src_root, phase=phase, appends=appends, convert=convert,
                     classify=classify, project_root=project_root)
    rep.tier_before = tier or ""
    return new_settings, rep, settings_notes
