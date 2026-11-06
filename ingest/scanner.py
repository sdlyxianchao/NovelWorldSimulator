# -*- coding: utf-8 -*-
"""摄取扫描器：读取项目文件夹全部文档，自动分类，转 UTF-8 文本。

设计稿 §3.1：扫描 → 按路径/文件名分类 → （交给 extractor 提取）。
支持格式：.md .txt .docx .html .htm（非 UTF-8 按 chardet 探测转码）。

English:
Ingest scanner: read all documents in the project folder, auto-classify, convert to UTF-8 text.
Design doc §3.1: scan → classify by path/filename → (hand to extractor for extraction).
Supported formats: .md .txt .docx .html .htm (non-UTF-8 transcoded via chardet detection).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import chardet

_LOG = __import__("logging").getLogger("nws.ingest")

# 分类关键词（文件名或路径含任一即命中；先匹配的优先）
# [EN] Classification keywords (any match in filename or path hits; first match wins)
_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    # ★★ 「规则」必须排**最前** —— 它优先级最高。
    #    用户写 `设定/顶级规则.md` 时，路径里同时含「设定」，而 `_classify`
    #    是**短路返回**（第一个命中的类别赢），所以谁在前谁说了算。
    #    为什么规则要跟其他设定分开：它是**作者对故事的硬约束**，
    #    `ingest/pipeline` 会把它**原文照录**进设定集（不交给 AI 压缩），
    #    而其他设定类文档都会经过 LLM 提取（→ 世界观被压到 120 字）。
    #    2026-10-06 加。
    # [EN] ★★ "Rules" must be placed **first** -- it has the highest priority.
    # [EN] is **short-circuit return** (the first matched category wins), so whoever is first calls the
    # [EN] shots.
    # [EN] Why rules must be separated from other settings: it is the **author's hard constraint on the
    # [EN] story**,
    # [EN] `ingest/pipeline` will **copy it verbatim** into the settings collection (not handed to AI for
    # [EN] compression),
    # [EN] while all other settings-category documents go through LLM extraction (→ worldview compressed to
    # [EN] 120 chars).
    # [EN] Added 2026-10-06.
    ("规则",  ["规则", "铁律", "铁则", "守则", "法则", "戒律", "准则", "准绳",
               "禁忌", "契约", "规范", "rule", "constraint"]),
    ("人物",  ["人物", "角色", "character", "person"]),
    ("大纲",  ["大纲", "outline", "剧情", "梗概"]),
    ("伏笔",  ["伏笔", "悬念", "线索", "foreshadow"]),
    ("正文",  ["正文", "章节", "第.*章", "chapter", "故事"]),
    ("设定",  ["设定", "世界观", "背景", "world", "setting"]),
]

_SKIP_DIRS = {
    ".workbuddy", "__pycache__", ".venv", ".git", ".svn", "node_modules",
    ".mypy_cache", ".pytest_cache",
}
#: 视为"可读文本"的后缀。
# [EN] : suffixes treated as "readable text".
#:
#: ★★ 2026-10-09 补上 `.yaml` / `.yml` —— 这是一处**真的坏了很久的东西**：
#:   示例文件夹 `samples/zh/01_悬疑单元_更漏子/设定/地点.yaml` 从加进来的那天起
#:   就在教作者"把地点写进这份 yaml，程序拿它画地图"，而**扫描器根本不读它**
#:   （后缀不在表里 → `scan_project` 直接跳过 → 内容进不了 `full_text`）。
#:   结果是：那份文件里写的 `方位` / `内里` 一个字都到不了提取器，
#:   作者照着示例写，却永远拿不到它承诺的效果（而**界面上不会报任何错**）。
#:   同类性质的东西还有一份：yaml 是"给人写设定"最自然的格式（层级清楚、
#:   能写列表），既然 `装完之后的设定集` 自己就全是 yaml，输入侧没理由不认。
# [EN] : ★★ 2026-10-09 added `.yaml` / `.yml` -- this is a spot that has been **broken for a long
# [EN] time**:
# [EN] : been teaching authors "write locations into this yaml, the program uses it to draw the map",
# [EN] while **the scanner does not read it at all**
# [EN] : (suffix not in the table → `scan_project` skips it directly → content never reaches
# [EN] `full_text`).
# [EN] :   The result: the `方位` / `内里` written in that file never reach the extractor at all,
# [EN] : the author writes following the example, yet never gets the effect it promises (and **the UI
# [EN] reports no error at all**).
# [EN] : There is one more thing of the same nature: yaml is the most natural format for "humans
# [EN] writing settings" (clear hierarchy,
# [EN] : can write lists), and since `装完之后的设定集` itself is entirely yaml, there is no reason the input
# [EN] side should not recognize it.
#:
#: ⚠ 影响面（确认过再改的）：`scan_project` 只被 `ingest/pipeline.run_ingest`
#:   和验证脚本调用，输入是**作者的引用文件夹** —— 那里面的 yaml 本来就该被读。
#:   它**不会**被用在 `设定集/` 上（那是冻结产物，由 `sim/setup` 自己按文件名读）。
# [EN] : ⚠ Scope of impact (confirmed before changing): `scan_project` is only called by
# [EN] `ingest/pipeline.run_ingest`
# [EN] : and validation scripts, with the input being the **author's reference folder** -- the yaml
# [EN] inside it should be read in the first place.
# [EN] : It is **not** applied to `设定集/` (that is a frozen artifact, read by `sim/setup` itself by
# [EN] filename).
_READ_SUFFIX = {".md", ".txt", ".html", ".htm", ".docx", ".yaml", ".yml"}

# ★ 程序自己写进引用文件夹的东西，**扫描时要跳过**（2026-10-06 加的）：
#   · `AI补全设定.md` —— 开卷时 AI 补写的设定（`ingest/repair.py`）。
#     不跳过的话，它自己的内容会被当成素材再喂给模型一遍，而且下次开卷
#     会把它当成"用户写的设定"，越滚越大。
#   · `.nws_classify.json` / `.nws_*` —— 程序的状态文件，一律不读。
#     （`.nws_*` 本来就被 `_walk_files` 的"点号开头"规则挡掉，这里写出来是为了
#     让"有哪些程序文件"一眼可见，别在别处再发明一套命名。）
# ⚠ 常量定义在**这里**（scanner 是最底层的一环），`ingest/repair.py` 从这里导入 ——
#   别两边各写一份字符串。
# [EN] ★ Things the program itself writes into the reference folder **must be skipped during scanning**
# [EN] (added 2026-10-06):
# [EN] · `AI补全设定.md` -- settings written by AI completion at open-book time (`ingest/repair.py`).
# [EN] If not skipped, its own content will be fed to the model again as material, and at the next
# [EN] open-book
# [EN] it will be treated as "settings written by the user", growing ever larger.
# [EN] · `.nws_classify.json` / `.nws_*` -- program state files, never read.
# [EN] (`.nws_*` is already blocked by `_walk_files`'s "starts with a dot" rule; it is written out here
# [EN] to
# [EN] make "what program files exist" visible at a glance, so don't invent another naming scheme
# [EN] elsewhere.)
# [EN] ⚠ Constants are defined **here** (the scanner is the lowest layer), and `ingest/repair.py`
# [EN] imports from here --
# [EN] don't write a separate copy of the string on each side.
COMPLETION_NAME = "AI补全设定.md"
CLASSIFY_NAME = ".nws_classify.json"
GENERATED_NAMES = {COMPLETION_NAME}


def load_classify(root: Path) -> dict[str, str]:
    """读引用文件夹里的**归类修正表** → `{相对路径: 类别}`。

    由开卷回写写进去（`ingest/repair.py`），让"AI 判断这个文件其实是正文"
    这件事**真的生效**（下次开卷就按修正后的类别读），而不只是写给人看。
    读不到 / 坏了都返回空表 —— 扫描绝不该因为这个文件而失败。
    
        English:
    Read the **classification correction table** in the reference folder → `{relative path:
    category}`.
        Written there by open-book write-back (`ingest/repair.py`), so that "the AI judged this file is actually main text"
        **actually takes effect** (the next open-book reads by the corrected category), rather than just being written for humans to see.
        Unreadable / corrupted both return an empty table -- scanning must never fail because of this file.
    """
    f = Path(root) / CLASSIFY_NAME
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k).replace("\\", "/"): str(v) for k, v in data.items()
            if isinstance(v, str)}


@dataclass
class FileItem:
    path: Path
    name: str
    category: str        # 人物/大纲/伏笔/正文/设定/杂项
    content: str         # UTF-8 纯文本（已去标签、转码）
    # [EN] Character / Outline / Foreshadowing / Main text / Settings / Misc
    # [EN] UTF-8 plain text (tags stripped, transcoded)
    sha256: str
    size: int            # 原始字节数
    encoding: str        # 检测到的编码；"utf-8" 表示原生
    lines: int           # 文本行数
    error: str = ""      # 非空=读取/解码失败，content 为空
    # [EN] Original byte count
    # [EN] Detected encoding; "utf-8" means native
    # [EN] Text line count
    # [EN] Non-empty = read/decode failed, content is empty


def scan_project(project_path: Path) -> list[FileItem]:
    """扫描项目文件夹，**永远是全量**：返回文件夹里全部可读文档。

    ★★ 2026-10-06 用户报「开卷这个地方为何现在只读一个文件，我放进来了一个文件夹，
    之前都读取整个文件夹」—— 根因就在这里，**别再把它加回来**：

      这里曾经有一个 `cache` 参数（`.ingest_cache.json` 的 sha256 清单），
      作用是"跳过未变更的文件"。它看着像省事的优化，实际上**把设定集做残了**：
      开卷必须把整份素材拼成 `full_text` / `novel_text` / `outline_text` 再交给
      模型（见 `ingest/pipeline.py`），少一个文件就是少一块内容 —— 第二次开卷时
      模型只看到"你这次改过的那一个文件"，写出来的设定集里其余全没了。

      而且它**只在改了一部分文件时才发作**，是最难查的那种坏法：
        · 全都没改 → 过滤后剩 0 个 → 管线兜底重扫全量 → **看着是对的**；
        · 只改一个 → 过滤后剩 1 个 → 不触发兜底 → **只读那一个**（用户遇到的）。
      所以"省下来的一次读取"根本换不来任何东西：文件读取是本机的、不要钱，
      真正花钱的几步本来就有硬上限（`ingest/preview.CAPS`）。

    凡是"某处想少读几个文件"，先回来看这段。
    
        English:
    Scan the project folder, **always full**: return all readable documents in the folder.
        ★★ 2026-10-06 user reported "why does this open-book spot now only read one file, I put in a folder,
        it used to read the whole folder" -- the root cause is right here, **don't add it back**:
          There used to be a `cache` parameter here (the sha256 manifest of `.ingest_cache.json`),
          whose purpose was "skip unchanged files". It looks like a convenient optimization, but in reality it **crippled the settings collection**:
          open-book must concatenate the entire material into `full_text` / `novel_text` / `outline_text` before handing it to
          the model (see `ingest/pipeline.py`); one fewer file is one fewer chunk of content -- at the second open-book
          the model only sees "the one file you changed this time", and everything else in the written settings collection is gone.
          Moreover it **only triggers when some files were changed**, the hardest kind of bug to track down:
            · nothing changed → 0 remain after filtering → pipeline fallback rescans everything → **looks correct**;
            · only one changed → 1 remains after filtering → fallback not triggered → **only that one is read** (what the user hit).
          So "the one read saved" buys nothing at all: file reads are local and free,
          and the steps that really cost money already have hard caps (`ingest/preview.CAPS`).
        Whenever "somewhere wants to read fewer files", come back and look at this passage first.
    """
    items: list[FileItem] = []
    if not project_path.is_dir():
        _LOG.warning("项目路径不存在: %s", project_path)
        return items
    fixes = load_classify(project_path)      # 归类修正表（开卷回写写的，见 load_classify）
    # [EN] Classification correction table (written by open-book write-back, see load_classify)
    for path in _walk_files(project_path):
        if path.suffix.lower() not in _READ_SUFFIX:
            continue
        try:
            raw = path.read_bytes()
        except OSError as e:
            _LOG.warning("读取失败 %s: %s", path, e)
            items.append(FileItem(path=path, name=path.name, category="杂项",
                                  content="", sha256="", size=0, encoding="", lines=0, error=str(e)))
            continue
        sha = hashlib.sha256(raw).hexdigest()
        try:
            rel = str(path.relative_to(project_path)).replace("\\", "/")
        except ValueError:
            rel = path.name
        cat = fixes.get(rel) or _classify(path)
        text, enc = _read_text(path, raw)
        items.append(FileItem(
            path=path, name=path.name, category=cat,
            content=text, sha256=sha, size=len(raw),
            encoding=enc, lines=text.count("\n") + 1 if text else 0))
    _LOG.info("扫描完成: %d 个文件（%d 有内容）", len(items), sum(1 for i in items if i.content))
    return items


# ── 内部 ──────────────────────────────────────────────────────────────
# [EN] ── Internal ──────────────────────────────────────────────────────────────
def _walk_files(root: Path) -> Iterator[Path]:
    for p in root.rglob("*"):
        if any(s in p.parts for s in _SKIP_DIRS):
            continue
        if p.name.startswith(".") or p.name.startswith("~$"):
            continue
        if p.name in GENERATED_NAMES:      # 程序自己写的补全文档，不当素材
        # [EN] Completion documents written by the program itself, not treated as material
            continue
        if p.is_file():
            yield p


def _classify(path: Path) -> str:
    """按文件名/路径关键词分类。
        English:
    Classify by filename/path keywords.
    """
    full = str(path).lower().replace("\\", "/")
    for cat, keywords in _CATEGORY_RULES:
        for kw in keywords:
            if re.search(kw, full):
                return cat
    return "杂项"


def _read_text(path: Path, raw: bytes) -> tuple[str, str]:
    """读取为纯文本，返回 (text, encoding)。
        English:
    Read as plain text, return (text, encoding).
    """
    suffix = path.suffix.lower()
    try:
        if suffix == ".docx":
            return _read_docx(path), "docx"
        if suffix in (".html", ".htm"):
            text = _decode_bytes(raw)
            from util.text import strip_html_tags
            return strip_html_tags(text), "html"
        return _decode_bytes(raw), "auto"
    except Exception as e:
        _LOG.warning("解析失败 %s: %s", path, e)
        return "", f"error:{e}"


def _decode_bytes(raw: bytes) -> str:
    """用 chardet 探测编码，回退 utf-8。
        English:
    Detect encoding with chardet, fall back to utf-8.
    """
    if not raw:
        return ""
    # 先试 utf-8（含 BOM）
    # [EN] Try utf-8 first (including BOM)
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    # chardet 探测
    # [EN] chardet detection
    det = chardet.detect(raw[:10000])
    enc = det.get("encoding") or "utf-8"
    try:
        return raw.decode(enc)
    except (UnicodeDecodeError, LookupError):
        return raw.decode("utf-8", errors="replace")


def _read_docx(path: Path) -> str:
    """用 python-docx 读取段落。
        English:
    Read paragraphs with python-docx.
    """
    from docx import Document
    doc = Document(str(path))
    parts = []
    for para in doc.paragraphs:
        t = para.text.strip()
        if t:
            parts.append(t)
    return "\n".join(parts)


def read_single_file(path: Path) -> FileItem:
    """读单个文件（供外部如资料库、设定刷新用）。
        English:
    Read a single file (for external use such as knowledge base, settings refresh).
    """
    try:
        raw = path.read_bytes()
    except OSError as e:
        return FileItem(path=path, name=path.name, category="杂项",
                        content="", sha256="", size=0, encoding="", lines=0, error=str(e))
    sha = hashlib.sha256(raw).hexdigest()
    text, enc = _read_text(path, raw)
    return FileItem(path=path, name=path.name, category=_classify(path),
                    content=text, sha256=sha, size=len(raw),
                    encoding=enc, lines=text.count("\n") + 1 if text else 0)