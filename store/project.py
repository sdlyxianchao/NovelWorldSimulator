# -*- coding: utf-8 -*-
""".nwsproj 项目文件：项目的身份证+目录册（设计稿 §10.9）。
English:
.nwsproj project file: the project's identity card + directory catalog (design doc §10.9).
"""
from __future__ import annotations

import configparser
import errno
import os
import re
import shutil
from pathlib import Path
from typing import Any

from config import VERSION, CFG
from util.io import atomic_write_text, safe_name, ensure_dir
from util.text import now_str, hash_file

_LOG = __import__("logging").getLogger("nws.store")

#: 推演文件夹的命名：`第N次模拟2026-10-22-19-05`。
# [EN] Run folder naming: `第N次模拟2026-10-22-19-05`.
RUN_NUM_RE = re.compile(r"第(\d+)次模拟")


def list_run_dirs(root: Path) -> list[Path]:
    """`root` 下的推演文件夹，按**序号**升序。

    ★ 抽成模块级函数（2026-10-26）：`Project.list_runs` 与「剧情总览」都要列推演，
      而后者手里**只有路径**（对话框从盘上找，不必装出 `Project` 对象）。
      两处各写一遍必然漂 —— 一处把"第10次"排到"第2次"前面，另一处排对了，
      界面上就是"跑马灯的顺序和拾卷里的顺序不一样"，而这种差异没人会去查。
    ⚠ 排序按**数字**不按字符串：字符串序下 `第10次` < `第2次`。
    [EN] Run folders under `root`, ascending by **index**. ★ A module-level function (2026-10-26)
    [EN] because both `Project.list_runs` and the story overview need to list runs, and the latter
    [EN] only has a **path** (the dialog reads from disk and need not fabricate a `Project`). Two
    [EN] copies would inevitably drift -- one sorting `第10次` before `第2次`, the other not, i.e. "the
    [EN] carousel order differs from the Pickup order", which nobody would ever investigate.
    [EN] ⚠ Sort by **number**, not string: as strings `第10次` < `第2次`.
    """
    p = Path(root)
    if not p.is_dir():
        return []
    out: list[Path] = []
    try:
        for d in p.iterdir():
            if d.is_dir() and RUN_NUM_RE.search(d.name):
                out.append(d)
    except OSError:
        return []
    out.sort(key=lambda x: (int(RUN_NUM_RE.search(x.name).group(1)), x.name))
    return out

# 目录结构
# Projects/<项目名>/
# ├── <项目名>.nwsproj
# ├── 设定集/
# ├── 优化后设定/
# ├── 完整设定集导出/
# └── 第N次模拟...
# [EN] Directory structure
# [EN] Projects/<project name>/
# [EN] ├── <project name>.nwsproj
# [EN] ├── settings/
# [EN] ├── optimized settings/
# [EN] ├── full settings export/
# [EN] └── simulation N...


class Project:
    """一个小说项目，对应 Projects/<项目名>/ 文件夹。
        English:
    One novel project corresponds to the Projects/<project name>/ folder.
    """

    def __init__(self, root: Path, name: str, *,
                 genre: str = "", style: str = "", style_custom: str = "",
                 source_folder: str = "", created: str = "",
                 last_run: str = "", run_count: int = 0,
                 image_mode: str = "", scene_name: str = "",
                 output_lang: str = "", run_overrides: "dict[str, str] | None" = None):
        self.root = root
        self.name = name or root.name
        self.genre = genre
        self.style = style
        # ★ 自定义风格正文（`NOVEL_STYLE=custom` 时用，2026-10-06）——
        #   它是**项目专属**（"这本书该怎么说话"换个项目就该换）。
        #   以前这个值只有一个全局的 `NOVEL_STYLE_CUSTOM`，书斋里改不了、
        #   也不落盘，于是"风格来源选自定义"等于没选。
        # [EN] ★ Custom style main text (used when `NOVEL_STYLE=custom`, 2026-10-06) ——
        # [EN] It is **project-specific** ("how this book should speak" should change when you switch
        # [EN] projects).
        # [EN] Previously this value had only a single global `NOVEL_STYLE_CUSTOM`, which could not be changed
        # [EN] in the study,
        # [EN] nor persisted, so "style source set to custom" was as good as not set.
        self.style_custom = style_custom
        self.source_folder = source_folder
        self.created = created or now_str("%Y-%m-%d %H:%M")
        self.last_run = last_run
        self.run_count = run_count
        # 对话图片方式：off / ascii / png / ai（空 = 没设过，按全局兜底推导）。
        # **存在项目文件里**（`[项目] 对话图片=`）—— "这本书要不要配图"是
        # 项目自己的事，不该被别的项目或全局设置带跑。
        # [EN] Dialogue image mode: off / ascii / png / ai (empty = never set, derived from global fallback).
        # [EN] **Stored in the project file** (`[project] dialogue image=`) —— "should this book have
        # [EN] illustrations"
        # [EN] is the project's own business, and should not be dragged around by other projects or global
        # [EN] settings.
        self.image_mode = image_mode
        # 开场地点：`auto`（按设定里的地点推断）或某个地点名（书斋 · 类型与风格）。
        # 同样是**项目专属**（`配置分类.md` 的 SCENE_NAME）——"这本书从哪儿开场"
        # 换个项目就该重选。空 = 没设过，运行时按全局 `.env` 兜底。
        # [EN] Opening location: `auto` (inferred from the location in settings) or a specific location name
        # [EN] (study · type and style).
        # [EN] Also **project-specific** (SCENE_NAME in `config categories.md`) —— "where this book opens"
        # [EN] should be reselected when switching projects. Empty = never set, falls back to global `.env` at
        # [EN] runtime.
        self.scene_name = scene_name
        # **输出语言**：`auto`（跟随界面语言）/ `zh` / `en`（`util/outlang.py`）。
        # 同样是**项目专属** —— "这本英文小说要推成中文"和"这本中文小说要推成英文"
        # 在同一台机器上都是正常需求，换个项目就该重选。
        # 空 = 没设过 → 当 `auto`（老项目的行为**和以前一样**，不用迁移）。
        # [EN] **Output language**: `auto` (follow the UI language) / `zh` / `en` (`util/outlang.py`).
        # [EN] Also **project-specific** —— "this English novel should be rendered into Chinese" and "this
        # [EN] Chinese novel should be rendered into English"
        # [EN] are both normal needs on the same machine, and should be reselected when switching projects.
        # [EN] Empty = never set → treated as `auto` (old projects behave **the same as before**, no migration
        # [EN] needed).
        self.output_lang = output_lang
        # ★★★ 2026-10-30：**这本书的运行设定覆盖**（书斋 · 运行）。
        #
        #   键是**配置键本身**（`RUN_MODE` / `TIME_RATIO` / `BEAT_SECONDS` …），值是字符串
        #   —— 存中文键名要再做一层翻译表，而".nwsproj 是给人看的"这条不靠它成立。
        #   ⚠ **没改过的项不写进来**：空字典 = 完全跟随天机（全局）。
        #     这是"默认书斋从天机继承"的落地点 —— 继承不是复制一份值，是**不写**。
        #   ⚠ 写进 `.env` 是**不行**的：那会把这一本书的节奏变成整台机器的节奏。
        # [EN] ★★★ 2026-10-30: **this book's run-setting overrides** (Study · Run).
        # [EN] Keys are the config keys themselves (`RUN_MODE` / `TIME_RATIO` / ...), values are
        # [EN] strings. ⚠ Untouched items are **not written here**: an empty dict means "follow
        # [EN] Tianji completely", which is how "the Study inherits from Tianji" works (inheriting
        # [EN] is *not writing*, not copying a value). ⚠ Writing these into `.env` would turn one
        # [EN] book's pace into the whole machine's pace.
        self.run_overrides: dict[str, str] = {
            str(k): str(v) for k, v in (run_overrides or {}).items()
            if str(v).strip() != ""
        }

    # ── 路径快捷 ──
    # [EN] ── Path shortcuts ──
    @property
    def nwsproj_path(self) -> Path:
        return self.root / f"{safe_name(self.name)}.nwsproj"

    @property
    def settings_dir(self) -> Path:
        return self.root / "设定集"

    @property
    def optimized_dir(self) -> Path:
        return self.root / "优化后设定"

    @property
    def export_dir(self) -> Path:
        return self.root / "完整设定集导出"

    # ── .nwsproj 读写 ──
    # [EN] ── .nwsproj read/write ──
    def rename(self, new_name: str, *,
               other_projects: "list[Project] | None" = None) -> tuple[bool, str]:
        """改项目的**显示名**（书斋 · 2026-10-29 用户点名）：**文件夹不动**。

        名字只活在两处：`.nwsproj` 里的 `名称=`（事实来源）和项目文件自己的
        文件名（`<safe_name(名称)>.nwsproj`）。文件夹名（`root`）**从头到尾
        不碰** —— 里面挂着的存档、设定集、导出稿一个都不用搬。

        ⚠ 顺序很讲究（照抄回收站那套"绝不半途毁东西"的规矩）：
          ① 先记下旧文件路径 → ② 改内存名 → ③ 写**新**项目文件 →
          ④ 写成功**才**删旧文件。写失败就把内存名改回去（旧文件原封不动）；
          删旧文件失败要**大声说**（旧 `.nwsproj` 还在盘上时 `scan_projects`
          会扫出两本"同一本书"，拾卷里凭空多一本）。

        ⚠ 撞名检查：落盘名（`safe_name` 之后）与**别的**项目相同就拒绝 ——
          两个项目落成同一个 `.nwsproj` 文件名不是"显示名一样"，
          是内容会互相覆盖。

        返回 `(是否成功, 说明)`；成功且确实改了名时说明为空串。
            English:
        Rename the project's **display name** (Study; requested by the user 2026-10-29): **the folder
        is not touched**. The name lives only in the `.nwsproj` (`名称=`) and the project file's own
        filename; the folder (`root`) with all its saves/settings/exports stays put. Order matters:
        write the **new** project file first, delete the old one only after that write succeeded;
        on write failure revert the in-memory name. Refuse names that collide (after `safe_name`)
        with **another** project. Returns `(ok, message)`.
        """
        new = str(new_name or "").strip()
        if not new:
            return False, "项目名不能为空"
        if new == self.name:
            return True, ""
        mine = _norm_name(self.name)
        want = _norm_name(new)
        if want != mine:
            for p in (other_projects or []):
                if p is self or getattr(p, "root", None) == self.root:
                    continue
                if _norm_name(p.name) == want:
                    return False, f"已有同名项目「{p.name}」，换个名字"
        old_path = self.nwsproj_path
        old_name = self.name
        self.name = new
        try:
            self.write_nwsproj()
        except Exception as e:                                    # noqa: BLE001
            self.name = old_name
            return False, f"写项目文件失败：{e}"
        try:
            if old_path != self.nwsproj_path and old_path.exists():
                old_path.unlink()
        except OSError as e:
            return False, (f"新名字已生效，但旧项目文件删不掉（{e}）—— "
                           f"请手工删除 {old_path.name}，否则拾卷里会出现两本")
        return True, ""

    def write_nwsproj(self) -> None:
        """写 .nwsproj（纯文本 UTF-8 键值对，configparser INI 格式）。
                English:
        Write .nwsproj (plain-text UTF-8 key-value pairs, configparser INI format).
        """
        cp = configparser.ConfigParser(allow_no_value=True)
        cp.optionxform = str  # 保留大小写（中文键名）
        # [EN] Preserve case (Chinese key names)
        cp["项目"] = {
            "名称": self.name,
            "类型": self.genre,
            "风格": self.style,
            "风格自定义": self.style_custom or "",
            "创建": self.created,
            "最近运行": self.last_run,
            "模拟次数": str(self.run_count),
            "源文件夹": self.source_folder,
            "对话图片": self.image_mode or "",
            "场景名称": self.scene_name or "",
            "输出语言": self.output_lang or "",
            "程序版本": VERSION,
        }
        # 文件索引：扫描目录
        # [EN] File index: scan directory
        index = self._scan_index()
        if index:
            cp["文件索引"] = index
        # 运行设定覆盖（书斋 · 运行）：**只有真改过才有这一段** ——
        # 空着时整段不写，老项目文件读回来仍然是"完全跟随天机"，不需要迁移。
        # [EN] Run-setting overrides (Study · Run): the section exists **only when something was
        # [EN] really changed**. When empty it is not written at all, so old project files read
        # [EN] back as "follow Tianji completely" with no migration.
        if self.run_overrides:
            cp["运行"] = {str(k): str(v) for k, v in self.run_overrides.items()}
        lines = []
        for section in cp.sections():
            lines.append(f"[{section}]")
            for k, v in cp[section].items():
                lines.append(f"{k}={v}")
            lines.append("")
        atomic_write_text(self.nwsproj_path, "\n".join(lines))

    def update_index(self) -> None:
        """只刷新 [文件索引]（运行结束 / 收编 / 导出后）。
                English:
        Only refresh [文件索引] (after run ends / after adoption / after export).
        """
        self.write_nwsproj()

    def _scan_index(self) -> dict[str, str]:
        """扫描项目文件夹，生成[文件索引]。
                English:
        Scan the project folder and generate a [file index]. [Output language] All **output text** must
        be written in **Simplified Chinese** — narration, voiceover, dialogue, documentation, summaries,
        and suggestions all count, **even if the source material is in another language**. Proper nouns
        such as personal names, place names, and book titles **retain their original form**; do not
        transliterate or paraphrase them. **Key names** in JSON **stay as-is** (e.g., "动作", "台词"); only
        write the **values** in Chinese.
        """
        index: dict[str, str] = {}
        skip = {".workbuddy", "__pycache__", ".venv", ".git", ".DS_Store", "Thumbs.db"}
        try:
            for p in sorted(self.root.rglob("*")):
                if any(s in p.parts or p.name.startswith(".") for s in skip):
                    continue
                if not p.is_file():
                    continue
                rel = str(p.relative_to(self.root)).replace("\\", "/")
                summary = self._file_summary(rel, p)
                if summary:
                    index[rel] = summary
        except OSError:
            pass
        return index

    def _file_summary(self, rel: str, path: Path) -> str:
        """给每个文件一个一行摘要。
                English:
        Give each file a one-line summary.
        """
        if rel.endswith(".md"):
            # 行数
            # [EN] Line count
            try:
                n = sum(1 for _ in open(path, encoding="utf-8", errors="ignore"))
                return f"{n} 行（更新 {now_str('%m-%d')}）"
            except Exception:
                return f"（更新 {now_str('%m-%d')}）"
        if rel.endswith((".yaml", ".yml")):
            return f"（更新 {now_str('%m-%d')}）"
        if rel.endswith(".json"):
            return f"JSON（更新 {now_str('%m-%d')}）"
        return f"（{path.stat().st_size} 字节，{now_str('%m-%d')}）" if path.exists() else ""

    @classmethod
    def from_nwsproj(cls, path: Path) -> "Project":
        """读取 .nwsproj 文件构建 Project。
                English:
        Read the .nwsproj file to build the Project.
        """
        cp = configparser.ConfigParser()
        cp.optionxform = str
        cp.read(str(path), encoding="utf-8")
        sec = cp["项目"] if "项目" in cp else {}
        name = sec.get("名称", path.stem)
        # 运行设定覆盖：段不存在（老项目 / 从没改过）＝ `{}` ＝ 完全跟随天机。
        # ⚠ 不要在这里补默认值 —— 补了就等于"这本书把当时的全局值抄了下来"，
        #   以后天机改了，这本书会固执地停在旧数上。
        # [EN] Run overrides: a missing section (old project / never touched) is `{}` = follow
        # [EN] Tianji completely. ⚠ Never fill in defaults here -- that would be "this book copied
        # [EN] the global values of that moment", and later Tianji changes would never reach it.
        run_ov = dict(cp["运行"]) if "运行" in cp else {}
        return cls(root=path.parent, name=name,
                   genre=sec.get("类型", ""), style=sec.get("风格", ""),
                   style_custom=sec.get("风格自定义", ""),
                   source_folder=sec.get("源文件夹", ""),
                   created=sec.get("创建", ""),
                   last_run=sec.get("最近运行", ""),
                   run_count=int(sec.get("模拟次数", "0")),
                   image_mode=sec.get("对话图片", ""),
                   scene_name=sec.get("场景名称", ""),
                   output_lang=sec.get("输出语言", ""),
                   run_overrides=run_ov)

    @classmethod
    def create_new(cls, root: Path, name: str, **kwargs: Any) -> "Project":
        """创建全新项目目录 + .nwsproj。
                English:
        Create a brand-new project directory + .nwsproj.
        """
        p = cls(root=root / safe_name(name), name=name, **kwargs)
        ensure_dir(p.root)
        ensure_dir(p.settings_dir)
        ensure_dir(p.optimized_dir)
        ensure_dir(p.export_dir)
        p.write_nwsproj()
        return p

    # ── 运行列表 ──
    # [EN] ── Run list ──
    def list_runs(self) -> list[Path]:
        """返回已有的运行文件夹列表（按序号）。

        ★ 2026-10-26：正文搬进模块级 `list_run_dirs`（「剧情总览」也用同一份，
          见那里的说明）。这里只保留这个方法名，老调用点一个字都不用改。
        [EN] Return the list of existing run folders (by index). ★ 2026-10-26: the body moved into the
        [EN] module-level `list_run_dirs` (the story overview uses the same one); this method name stays
        [EN] so no call site changes.
        """
        return list_run_dirs(self.root)

    def next_run_index(self) -> int:
        runs = self.list_runs()
        if not runs:
            return 1
        pattern = re.compile(r"第(\d+)次模拟")
        max_n = 0
        for d in runs:
            m = pattern.search(d.name)
            if m:
                max_n = max(max_n, int(m.group(1)))
        return max_n + 1


def scan_projects(projects_dir: Path) -> list[Project]:
    """扫描目录下所有 .nwsproj，返回项目列表。
        English:
    Scan all .nwsproj under the directory, return the project list.
    """
    if not projects_dir.exists():
        return []
    projects = []
    for nwsproj in projects_dir.rglob("*.nwsproj"):
        try:
            projects.append(Project.from_nwsproj(nwsproj))
        except Exception as e:
            _LOG.warning("读取 %s 失败: %s", nwsproj, e)
    projects.sort(key=lambda p: p.last_run or p.created, reverse=True)
    return projects


# ══════════════════════════════════════════════════════════════════
#  「这本是不是已经开过卷了」—— 用户 2026-10-07 报的问题：
#    「如果小说已经存在 则后续再开卷的话 要提示已经存在 而不是继续可以开卷这本小说」
# [EN] "Has this book already been started" —— the issue reported by the user on 2026-10-07:
# [EN] "If the novel already exists, then starting a new volume later should prompt that it already
# [EN] exists, rather than still allowing this novel to be started"
#
#  原来的行为是**一声不吭地又开一遍**：`Project.create_new` 用
#  `projects_dir/<safe_name(项目名)>`，目录已存在就 `ensure_dir`（存在即用），
#  然后 `write_nwsproj()` 覆盖 `.nwsproj`、`freeze_settings()` 覆盖 `设定集/`
#  里的同名文件 —— 也就是**新书的内容混进旧项目**，而旧项目那本书的存档
#  还挂在同一个文件夹里。用户看不到任何提示。
# [EN] The original behavior was to **start it again without a word**: `Project.create_new` uses
# [EN] `projects_dir/<safe_name(project name)>`, and if the directory already exists it does
# [EN] `ensure_dir` (exists means use it),
# [EN] then `write_nwsproj()` overwrites `.nwsproj`, `freeze_settings()` overwrites the same-named file
# [EN] in `settings/`
# [EN] —— that is, **the new book's content gets mixed into the old project**, while the old project's
# [EN] book saves
# [EN] are still attached to the same folder. The user sees no prompt at all.
#
#  所以这里给三条纯函数（都能单独测，不碰界面）：归一化路径 / 找出已经开过的 /
#  撞名时给一个不撞的。判定归判定、提示归提示 —— 界面那边只管怎么问用户。
# [EN] So here are three pure functions (each testable on its own, no UI touched): normalize path /
# [EN] find already-started ones /
# [EN] give a non-conflicting name on collision. Judgment is judgment, prompting is prompting —— the UI
# [EN] side only handles how to ask the user.
# ══════════════════════════════════════════════════════════════════
def norm_source(path: str) -> str:
    """素材文件夹路径归一化（**只为了比较**，不为了去找它）。

    归一化的四件事，每一件都对应一种"同一个文件夹、写出来不一样"：
      · 用户从资源管理器复制路径时带的**引号**、首尾空白；
      · `~` 与相对路径 → 绝对路径；`E:/小说` 与 `E:\\小说` → 同一种分隔符；
      · **尾随分隔符**（`E:\\小说\\` 与 `E:\\小说` 是同一个）；
      · Windows **大小写不敏感**（`E:\\Novel` 与 `e:\\novel` 是同一个）——
        走 `os.path.normcase`，在 Linux 上它什么都不做（那边本来就敏感）。

    ⚠ 不用 `resolve()` 去追符号链接：素材夹**可能已经被移走或改过名**，
      那时"追真实路径"要么抛错、要么给出一个和当初存进去的完全不同的串，
      反而认不出来。这里只做**纯字符串**归一 —— 
      **认不出来就不认**（宁可偶尔漏报，也不要误报成"同一本小说"）。
    
        English:
    Material folder path normalization (**only for comparison**, not for finding it).
        Four things in normalization, each corresponding to a way "the same folder, written differently":
          · **Quotes** and leading/trailing whitespace when the user copies a path from the file explorer;
          · `~` and relative paths → absolute paths; `E:/novel` and `E:\\novel` → the same separator;
          · **Trailing separator** (`E:\\novel\\` and `E:\\novel` are the same);
          · Windows **case-insensitive** (`E:\\Novel` and `e:\\novel` are the same) ——
            goes through `os.path.normcase`, which does nothing on Linux (it is case-sensitive there anyway).
        ⚠ Do not use `resolve()` to follow symlinks: the material folder **may have already been moved or renamed**,
          in which case "resolving the real path" either throws or gives a string completely different from what was stored originally,
          making it unrecognizable instead. Here only **pure string** normalization is done ——
          **if unrecognizable, don't recognize it** (prefer occasionally missing a match over falsely reporting "the same novel").
    """
    s = str(path or "").strip().strip('"').strip("'").strip()
    if not s:
        return ""
    try:
        s = os.path.abspath(os.path.expanduser(s))
    except (OSError, ValueError):
        return os.path.normcase(s)
    return os.path.normcase(os.path.normpath(s))


def _norm_name(name: str) -> str:
    """项目名归一化（比较用）：走 `safe_name`（落盘用的就是它）+ 大小写无关。
        English:
    Project name normalization (for comparison): use `safe_name` (that is what is written to disk) +
    case-insensitive.
    """
    return os.path.normcase(safe_name(str(name or "").strip()))


def matches(projects: list, *, name: str = "",
            source_folder: str = "") -> list[Project]:
    """在一**串已经扫好的项目**里挑出"同一本"（判定本体，见 `find_existing`）。

    ⚠ 单独立出来是为了让调用方**复用扫描结果**：界面那条路径挂在输入框的
      `on_change` 上（改一个字查一次），每次都 rglob 一遍项目目录会卡手。
      `find_existing` = `matches(scan_projects(...))`，判定逻辑**只有这一份**。
    
        English:
    Pick out the "same book" from a **string of already-scanned projects** (identity determination,
    see `find_existing`).
        ⚠ Separated out so that callers can **reuse the scan result**: the UI path hangs off the input box's
          `on_change` (query once per character changed); running rglob over the project directory every time would make it lag.
          `find_existing` = `matches(scan_projects(...))`, the determination logic exists in **only this one place**.
    """
    if not str(name or "").strip() and not norm_source(source_folder):
        return []
    want_name = _norm_name(name) if str(name or "").strip() else ""
    want_src = norm_source(source_folder)
    hits: list[Project] = []
    for p in projects or []:
        same_name = bool(want_name) and _norm_name(p.name) == want_name
        same_src = bool(want_src) and norm_source(p.source_folder) == want_src
        if same_name or same_src:
            hits.append(p)
    return hits


def find_existing(projects_dir: Path, *, name: str = "",
                  source_folder: str = "") -> list[Project]:
    """**已经开过卷**的项目：同名 或 同一素材文件夹（返回最近的排前面）。

    两条判据都要，因为它们各漏一半：
      · **同名** —— 开卷向导的项目名默认就是文件夹名，所以"同一本书再开一次"
        十有八九就撞在这条上；
      · **同素材** —— 上次开的时候换过名字，这次又想换一个名字，
        名字不同、书还是那本，只看名字就漏了。

    ⚠ 只做**相等**比较，**不做"谁包着谁"**：一个父目录里装着好几本书是
      正常用法（`E:\\我的小说` 底下有《甲》《乙》两份素材），
      把"父目录开过卷"推成"子目录也开过"会误伤。

    `name` / `source_folder` 都留空时返回空列表（没什么可比的）。
    
        English:
    **Already-opened** projects: same name or same source folder (most recent returned first).
        Both criteria are needed, because each misses half:
          · **Same name** —— the project name in the open wizard defaults to the folder name, so "opening the same book again"
            will almost always hit this one;
          · **Same source** —— the name was changed last time it was opened, and now they want to change it again;
            different name, same book, looking only at the name would miss it.
        ⚠ Only do **equality** comparison, **do not do "who contains whom"**: a parent directory holding several books is
          pushing "parent directory was opened" to "child directory was also opened" would cause false positives.
        When both `name` / `source_folder` are empty, return an empty list (nothing to compare).
    """
    return matches(scan_projects(Path(projects_dir)),
                   name=name, source_folder=source_folder)


def unique_name(projects_dir: Path, name: str) -> str:
    """给一个**不撞车**的项目名：`茶肆疑云` → `茶肆疑云 (2)` → `茶肆疑云 (3)`…

    ★ 用来干"用户坚持重新开卷"那一档：他要重开是他的事，但**不能覆盖**
      已经有东西的那本（同名会复用同一个目录，`设定集/` 被新书盖掉、
      旧存档还混在里面）。**另开一份新的**最安全 —— 不丢任何东西，
      而且名字上看得见区别（用户能自己删掉不要的那份）。

    比的是 `safe_name()` 之后的值（落盘用的就是它），所以
    `甲/乙` 与 `甲_乙` 会被当成同一个名字 —— 它们落盘确实是同一个文件夹。
    
        English:
        ★ Used for the "user insists on reopening" case: if they want to reopen, that is their business, but it **must not overwrite**
          the one that already has content (same name would reuse the same directory, `设定集/` gets overwritten by the new book,
          old saves still mixed in). **Opening a separate new copy** is safest —— nothing is lost,
          and the difference is visible in the name (the user can delete the unwanted copy themselves).
        Compares the value after `safe_name()` (that is what is written to disk), so
        `甲/乙` and `甲_乙` are treated as the same name —— they really do write to the same folder.
    """
    base = str(name or "").strip() or "未命名"
    taken = {_norm_name(p.name) for p in scan_projects(Path(projects_dir))}
    # 目录也可能已经在了（比如空目录 / 手建的）—— 一并算进去
    # [EN] The directory may also already exist (e.g. empty directory / manually created) —— count it in as
    # [EN] well
    try:
        for d in Path(projects_dir).iterdir():
            if d.is_dir():
                taken.add(_norm_name(d.name))
    except OSError:
        pass
    if _norm_name(base) not in taken:
        return base
    for i in range(2, 1000):
        cand = f"{base} ({i})"
        if _norm_name(cand) not in taken:
            return cand
    return f"{base} ({now_str('%Y%m%d-%H%M%S')})"

# ══════════════════════════════════════════════════════════════════
#  「删除」（拾卷用）：**护栏 + 可恢复**，宁可拒绝也不删错
# [EN] "Delete" (used by volume pickup): **guardrails + recoverable**, prefer refusing over deleting
# [EN] the wrong thing
# ══════════════════════════════════════════════════════════════════
# 两条护栏是同一件事的两面：**凭"路径"删东西太容易删错，
# 所以要凭"它是不是真的是个东西"来删。** 认不出来就拒绝，
# 让用户自己去看一眼 —— 报一次「这里没有项目文件」比删掉一个
# 手滑选中的目录便宜得多。
# [EN] The two guardrails are two sides of the same thing: **deleting things by "path" easily deletes
# [EN] the wrong thing,
# [EN] so delete by "whether it really is a thing".** If unrecognizable, refuse,
# [EN] and let the user go look themselves —— reporting "there is no project file here" once is much
# [EN] cheaper
# [EN] than deleting a directory picked by a slip of the hand.
#
# ⚠ 2026-10-06 加了"可恢复"：用户在新功能上线 5 分钟后就用它删掉了
#   自己整本书（当晚的日志里，几分钟内连删了两轮存档、最后把整本删掉了）。
#   那时是 `shutil.rmtree` —— **永久删除、不进回收站**，
#   正文和设定集直接没了。现在改成**移进「已删除备份」（项目根的**同级**目录）**：
#   · 同级 = 不在 `projects_root` 里面 —— `scan_projects()` 用 `rglob('*.nwsproj')`，
#     放进项目根里会让删掉的书**又冒出来**；
#   · 搬不动就**失败返回**，绝不退回 `rmtree`（"删不了"比"删错了"好）。
# [EN] ⚠ 2026-10-06 added "recoverable": the user deleted their entire book
# [EN] 5 minutes after the new feature went live (in that night's logs, they deleted two rounds of
# [EN] saves within minutes, then finally the whole book).
# [EN] At that time it was `shutil.rmtree` —— **permanent deletion, not going to recycle bin**,
# [EN] so main text and settings were simply gone. Now changed to **move into "deleted backup" (a
# [EN] **sibling** directory of the project root)**:
# [EN] · sibling = not inside `projects_root` —— `scan_projects()` uses `rglob('*.nwsproj')`,
# [EN] putting it inside the project root would make deleted books **pop up again**;
# [EN] · if it cannot be moved, **return failure**, never fall back to `rmtree` ("cannot delete" is
# [EN] better than "deleted the wrong thing").
RUN_DIR_RE = re.compile(r"^第\d+次模拟")
TRASH_DIRNAME = "已删除备份"          # 与 Projects 同级
# [EN] Sibling to Projects


def trash_dir_for(projects_root: Path) -> Path:
    """「已删除备份」目录（**项目根的同级**，不进去）。
        English:
    "Deleted backups" directory (**sibling of the project root**, does not go inside).
    """
    return projects_root.resolve().parent / TRASH_DIRNAME


def folder_stats(path: Path) -> tuple[int, int]:
    """(文件数, 总字节) —— 确认框要把「要删什么」写清楚，不能只说"确定吗"。
        English:
    (file count, total bytes) —— the confirmation dialog must clearly state "what will be deleted",
    not just say "are you sure".
    """
    n = 0
    size = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                n += 1
                try:
                    size += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return n, size


def human_size(n: int) -> str:
    """字节 → 人话（确认框里写「1.2 MB」比写 1234567 好读）。
        English:
    Bytes → human-readable (writing "1.2 MB" in the confirmation dialog is easier to read than
    1234567).
    """
    v = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if v < 1024 or unit == "GB":
            return f"{v:.0f} {unit}" if unit == "B" else f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} GB"


def _inside(child: Path, parent: Path) -> bool:
    """`child` 是不是在 `parent` **里面**（不相等、也不许是它的祖先）。
        English:
    Whether `child` is **inside** `parent` (not equal, nor allowed to be its ancestor).
    """
    try:
        c, p = child.resolve(), parent.resolve()
    except OSError:
        return False
    if c == p:
        return False
    try:
        c.relative_to(p)
        return True
    except ValueError:
        return False


def _move_to_trash(target: Path, projects_root: Path, kind: str) -> tuple[bool, str]:
    """把 `target` 搬进「已删除备份」→ `(成功, 备份路径或原因)`。

    ⚠ **不用 `shutil.rmtree`**：那是不可逆的。搬不动就老实说搬不动。
    重名时加序号（同一秒里连删两个也搬得走）。

    ★★ 2026-10-07 重写（用户报「最后一个存档无法删除」，现场代价不小）：

    原来用 `shutil.move`。它在**改不了名**时会**回退成「先复制、再删源」**——
    而改名失败最常见的原因恰恰是**目录里有文件被占着**（推演用的 `state.db`
    就在运行文件夹里）。于是回退路径成了这样：

        复制 → 备份目录里出现一份"看起来像真备份"的东西
        删源 → rmtree 删到 `state.db` 就失败，**源目录已经被删掉一半**

    用户看到的是"点了几次都删不掉"，`已删除备份/` 里还攒下 4 个同名备份
    （后 3 个只剩 7 个文件）—— 而**源目录里的东西已经被删掉一部分，
    那是真的数据损失**。

    所以现在分两条路，规矩是**绝不半途毁东西**：

      ① **同盘**（正常情形）：只用 `os.rename` —— 原子操作，要么整个搬过去、
         要么原地一点没动。失败就重试几次，仍不行就**什么都不做**并给出原因。
      ② **跨盘**（`EXDEV`，罕见：项目根被指到了别的盘）：必须复制。
         复制成功才删源；**删不掉就把复制出来的那份留着**并说清
         「备份里有一份完整的，原目录得手工删」—— 因为那时它才是唯一完整的一份。
    
        English:
    Move `target` into "deleted backups" → `(success, backup path or reason)`.
        ⚠ **Do not use `shutil.rmtree`**: that is irreversible. If it cannot be moved, honestly say it cannot be moved.
        Append a sequence number on name collision (deleting two in the same second still gets moved).
        ★★ 2026-10-07 rewrite (user reported "the last save cannot be deleted", the on-site cost was not small):
        Originally used `shutil.move`. When it **cannot rename**, it **falls back to "copy first, then delete source"** ——
        and the most common cause of rename failure is precisely **a file in the directory being held open** (the `state.db`
        used for simulation is right there in the running folder). So the fallback path became this:
            copy → a "looks like a real backup" thing appears in the backup directory
            delete source → rmtree fails at `state.db`, **the source directory has already been half deleted**
        What the user saw was "clicked several times and it still won't delete", and `已删除备份/` had accumulated 4 backups with the same name
        (the last 3 had only 7 files left) —— and **part of the source directory had already been deleted,
        that is real data loss**.
        So now there are two paths, and the rule is **never destroy things halfway**:
          ① **Same disk** (normal case): only use `os.rename` —— atomic operation, either the whole thing is moved over,
             or nothing moved at all. On failure, retry a few times; if still failing, **do nothing** and give the reason.
          ② **Cross-disk** (`EXDEV`, rare: project root points to another disk): must copy.
             Only delete the source after the copy succeeds; **if it cannot be deleted, keep the copied version** and state clearly
             "there is a complete copy in backups, the original directory must be deleted manually" —— because at that point it is the only complete copy.
    """
    trash = trash_dir_for(projects_root)
    try:
        trash.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return False, f"建不了备份目录 {trash}（{e}）"
    stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = trash / f"{stamp}_{kind}_{target.name}"
    n = 1
    while dest.exists() or _sidecar_of(dest).exists():
        n += 1
        dest = trash / f"{stamp}_{kind}_{target.name}_{n}"
    return atomic_move(target, dest)


def _sidecar_of(dest: Path) -> Path:
    """回收站条目的**旁注文件**（`store/trash.py` 写的元信息）。
    [EN] The **sidecar** of a trash entry (metadata written by `store/trash.py`).
    """
    return dest.parent / (dest.name + '.json')


def atomic_move(src: Path, dest: Path) -> tuple[bool, str]:
    """把 `src` **整个搬到** `dest`：同盘只 `os.rename`，跨盘才复制。

    ★ 抽出来是因为**回收站的"恢复"要走同一条路**（`store/trash.py`）：
      搬进回收站与搬出回收站，风险完全一样 —— 半途毁东西是最不能接受的失败。
      两条路各写一份实现，迟早一份被改、另一份留着老毛病。

    规矩（与 `_move_to_trash` 的说明同源）：
      ① 同盘：只用 `os.rename`（原子），失败重试三次，仍不行就**原地不动**；
      ② 跨盘（`EXDEV`）：复制成功才删源；删不掉就把复制品留着并说清楚。

        English:
    Move `src` **wholesale** to `dest`: same-disk uses only `os.rename`, cross-disk copies.
    ★ Extracted because the recycle bin's "restore" walks the same path (`store/trash.py`): moving in
      and moving out carry identical risk -- destroying things halfway is the least acceptable failure.
      Two separate implementations would eventually diverge.
    """
    last: OSError | None = None
    for attempt in range(3):
        if not src.exists():
            break                       # 上一次其实搬走了（只是报错晚了）
        try:
            os.rename(str(src), str(dest))
        except OSError as e:
            if getattr(e, "errno", None) != errno.EXDEV:
                last = e
                _LOG.warning("移动 %s 到 %s 失败（第 %d 次）: %s",
                             src, dest, attempt + 1, e)
                if attempt < 2:
                    __import__("time").sleep(0.35)
                continue
            return _copy_then_delete(src, dest, e)
        _LOG.info("已移动 %s → %s", src, dest)
        return True, str(dest)
    return False, _why_move_failed(last)


def _copy_then_delete(target: Path, dest: Path, why: OSError) -> tuple[bool, str]:
    """跨盘搬移：先复制、再删源。**删不掉时把复制出来的那份留住**。

    留着的理由：`rmtree` 很可能已经删掉源里的一部分了，那份复制品才是
    唯一完整的东西。宁可多留一份让用户自己收拾，也不能让内容凭空少掉。
    
        English:
    Cross-disk move: copy first, then delete source. **When deletion fails, keep the copied
    version**.
        Reason for keeping it: `rmtree` has likely already deleted part of the source, and that copy is
        the only complete thing. Better to leave an extra copy for the user to clean up than to let content vanish into thin air.
    """
    try:
        shutil.copytree(target, dest)
    except OSError as e:
        _LOG.warning("跨盘复制 %s 失败: %s", target, e)
        shutil.rmtree(dest, ignore_errors=True)
        return False, _why_move_failed(e or why)
    try:
        shutil.rmtree(target)
    except OSError as e:
        _LOG.warning("已复制到备份但删不掉源目录 %s: %s", target, e)
        return False, (f"已复制一份到备份（{dest}），但原目录删不掉（{e}）—— "
                       f"备份里那份是完整的，原目录请手工删掉。")
    _LOG.info("已移入备份（跨盘复制） %s → %s", target, dest)
    return True, str(dest)


def _why_move_failed(e: OSError | None) -> str:
    """把「搬不动」翻成**一句能照着做的话**。

    分开报是因为对策完全不同：
      · 被占用（WinError 32 / PermissionError）→ 去把那个程序/那一轮停掉；
      · 权限不够 → 换个不带只读属性的位置、或以管理员身份运行；
      · 其余 → 原样把系统那句话带上（别替它解释，解释错了更费事）。

    ★ 一律**不破坏任何东西**：这条路径上源目录与备份目录都保持原样
      （见 `_move_to_trash` 上面那段——`shutil.move` 的回退路径会删掉半个源目录）。
    
        English:
    Translate "cannot move" into **a sentence that can be acted on**.
        Reported separately because the countermeasures are completely different:
          · In use (WinError 32 / PermissionError) → go stop that program / that round;
          · Insufficient permissions → switch to a location without the read-only attribute, or run as administrator;
          · Otherwise → carry the system's message as-is (don't explain it for it; a wrong explanation is more trouble).
        ★ Never **destroy anything**: on this path both the source directory and the backup directory remain as-is
          (see the paragraph above `_move_to_trash` — the fallback path of `shutil.move` will delete half the source directory).
    """
    if e is None:
        return "搬不动（原因不明）"
    code = getattr(e, "winerror", None)
    if code == 32 or isinstance(e, PermissionError):
        return ("搬不动：里面有文件正被程序占用（多半是这一轮的 state.db）。"
                "先把这一轮停下来 —— 若它还在跑，点「停止」；"
                "还不行就关掉本程序重开，再删一次。原目录一个字没动。")
    if code == 5:
        return (f"搬不动：没有权限（{e}）。换一个可写的位置，"
                f"或以管理员身份运行。原目录一个字没动。")
    return f"搬不动（{e}）（原目录一个字没动）"



def archive_project_dir(root: Path, projects_root: Path) -> tuple[bool, str]:
    """把一整个项目文件夹移进「已删除备份」（界面上的「删除这本小说」）。

    护栏（必须全过）：① 在 `projects_root` **里面**（不许删根、不许删到别处）；
    ② 目录里**真的**有 `<名字>.nwsproj` —— 这是"它是个项目"的唯一凭据。
    返回 `(是否搬走, 备份路径或原因)`。
    
        English:
    Move an entire project folder into "Deleted Backup" ("Delete this novel" in the UI).
        Guardrails (must all pass): ① must be **inside** `projects_root` (no deleting the root, no deleting elsewhere);
        ② the directory must **actually** contain `<name>.nwsproj` — this is the only proof that "it is a project".
        Return `(whether moved, backup path or reason)`.
    """
    if not _inside(root, projects_root):
        return False, "拒绝：目标不在项目目录内"
    if not root.is_dir():
        return False, "拒绝：目标不是文件夹"
    if not list(root.glob("*.nwsproj")):
        return False, "拒绝：这个文件夹里没有 .nwsproj，认不出是项目"
    return _move_to_trash(root, projects_root, "小说")


def archive_run_dir(run_dir: Path, project_root: Path,
                   projects_root: Path = None) -> tuple[bool, str]:
    """把一轮存档移进「已删除备份」（界面上的「删除这个存档」）。

    护栏：① 必须是 `project_root` 的**直接子目录**（存档就在项目根下面一层）；
    ② 名字必须是 `第N次模拟…` —— 免得手滑删掉 `设定集/` 或 `肖像/`。
    
        English:
    Move one round of save data into "Deleted Backup" ("Delete this save" in the UI).
        Guardrails: ① must be a **direct subdirectory** of `project_root` (save data is one level below the project root);
    """
    if not run_dir.is_dir():
        return False, "拒绝：目标不是文件夹"
    try:
        if run_dir.resolve().parent != project_root.resolve():
            return False, "拒绝：目标不是该项目的直接子目录"
    except OSError:
        return False, "拒绝：路径读不了"
    if not RUN_DIR_RE.match(run_dir.name):
        return False, "拒绝：名字不像存档（不是「第N次模拟…」）"
    root = projects_root or project_root.parent
    return _move_to_trash(run_dir, root, "存档")
