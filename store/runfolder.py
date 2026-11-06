# -*- coding: utf-8 -*-
"""运行文件夹：每次模拟一份，含目录结构、产物路径、每天的生活落盘。
English:
Run folder: one per simulation, containing the directory structure, artifact paths, and the
persisted daily life.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from util.io import atomic_write_text, ensure_dir
from util.text import now_str

#: 模块级 logger。★ 2026-10-26 补：之前这个文件**一个 logger 都没有**，
#: 我加"拒绝跨格式覆盖"那条 warning 时直接 `NameError`（同一个坑在
#: `export/bundle.py` 也踩过一次）——**写 `_LOG.xxx` 之前先确认这个文件有没有 `_LOG`**。
#: 名字跟全项目一致（`nws.<模块>`），否则按名字过滤日志时一半看不见。
# [EN] Module-level logger. Added 2026-10-26: this file had **no logger at all**, so the "refuse
# [EN] cross-format overwrite" warning blew up with `NameError` (same trap as `export/bundle.py`).
# [EN] Always confirm the file has `_LOG` before using it. Name follows the project convention.
_LOG = logging.getLogger("nws.runfolder")

#: `第001天.md` / `第001天.json` —— **只认这个形状**。
#: 不认的话，`每天的生活/原文/` 里以后可能多出来的校对稿、去 AI 味稿
#: 会被当成一天算进去，于是"故事跨度"凭空多几天。
# [EN] : would be counted as a day, so the "story span" gains a few days out of nowhere.
_DAY_RE = re.compile(r'^第(\d{1,5})天$')


@dataclass(frozen=True)
class StorySpan:
    """一份存档「**故事里的时间**」跨度（起 / 止）。

    用户 2026-10-10 原话：「第2列的推演存档列表 加上一个属性就其进行的推演的
    开始和结束时间（**故事里的时间**）然后上面加一组单选框 可以按照推演
    开始时间正序 / 开始时间倒序 / 结束时间正序 / 结束时间倒序 4 种方式排列」。

    ★ 为什么**不**用文件夹名里的那个时间（`第1次模拟2026-10-05-20-00`）：
      那是**现实世界**的时刻（你什么时候点的"起笔"）。用户点名要的是
      **故事里的时间** —— 这一轮从第几天演到第几天。两者常常差着十万八千里
      （一轮跑了二十分钟，故事里过了三十天）。排序要按后者排，才符合
      "我想看哪一轮把故事推得最远"这个真实意图。

    ★ 全部来自**盘上的产物**（`每天的生活/` 的文件名 + 剧本 JSON 的
      `time_label`），**不问模型**、也不重放推演 —— 打开拾卷就能立刻排好。
    
        English:
    The "**time within the story**" span (start / end) of one archive.
        User's exact words on 2026-10-10: "Add to the simulation archive list in column 2 an attribute for its simulation's
        start and end times (**time within the story**), then add a group of radio buttons above it to arrange by simulation
        start time ascending / start time descending / end time ascending / end time descending, 4 ways".
        ★ Why **not** use the time in the folder name (`第1次模拟2026-10-05-20-00`):
          that is a **real-world** moment (when you clicked "start writing"). What the user explicitly asked for is
          **time within the story** —— which day this round plays from and to. The two are often worlds apart
          (a round runs twenty minutes, thirty days pass in the story). Sorting must be by the latter to match
          the real intent of "I want to see which round pushed the story the furthest".
        ★ All comes from **artifacts on disk** (the filenames under `每天的生活/` + the script JSON's
          `time_label`), **without asking the model** and without replaying the simulation —— opening 拾卷 sorts it immediately.
    """

    start_day: int = 0          # 起始是第几天（0 = 没读到）
    start_at: str = ''          # 起始那一天的第一个时刻（如「辰时 08:00」）
    end_day: int = 0            # 结束是第几天
    end_at: str = ''            # 结束那一天的最后一个时刻
    source: str = ''            # 这份跨度是从哪儿读来的（给人查；空 = 没读到）
    # [EN] The starting day number (0 = not read)
    # [EN] The first moment of the starting day (e.g. "辰时 08:00")
    # [EN] The ending day number
    # [EN] The last moment of the ending day
    # [EN] Where this span was read from (for humans to check; empty = not read)

    @property
    def ok(self) -> bool:
        return bool(self.start_day or self.end_day)

    @property
    def days(self) -> int:
        """演了几天（含头含尾）。读不全时为 0。
                English:
        Number of days performed (inclusive of both ends). 0 when not fully readable.
        """
        if not self.ok:
            return 0
        a = self.start_day or self.end_day
        b = self.end_day or self.start_day
        return max(1, b - a + 1)

    @property
    def sort_start(self) -> tuple:
        """按"开始时间"排序用的键。**读不到的一律排最后**。

        ⚠ 缺数据不能当成 0 排到最前面 —— 那会让"没读到时间的存档"
          冒充"最早开始的存档"，把真正该看的那几轮挤到后面去。
        
                English:
        Key used for sorting by "start time". **Anything unreadable is always sorted last**.
                ⚠ Missing data must not be treated as 0 and sorted to the very front —— that would let "saves with no readable timestamp"
                  masquerade as "the earliest-started save", pushing the rounds that actually matter to the back.
        """
        return (1, 0, '') if not self.ok else (0, self.start_day, self.start_at)

    @property
    def sort_end(self) -> tuple:
        return (1, 0, '') if not self.ok else (0, self.end_day, self.end_at)

    def short(self) -> str:
        """一行短标签（存档卡上用，宽度只有 300px）。
                English:
        One short label line (used on the save card, width is only 300px).
        """
        if not self.ok:
            return ''
        a, b = self.start_day or self.end_day, self.end_day or self.start_day
        if a == b:
            return f'第 {a} 天'
        return f'第 {a} → {b} 天'

    def full(self) -> str:
        """带时刻的那一行（详情栏用，那里宽度够）。
                English:
        The line with the timestamp (used in the detail panel, where there's enough width).
        """
        if not self.ok:
            return ''
        a, b = self.start_day or self.end_day, self.end_day or self.start_day
        head = f'第 {a} 天' + (f' {self.start_at}' if self.start_at else '')
        if a == b:
            tail = self.end_at if (self.end_at and self.end_at != self.start_at) else ''
            return f'{head} → {tail}' if tail else head
        tail = f'第 {b} 天' + (f' {self.end_at}' if self.end_at else '')
        return f'{head} → {tail}'


def _time_labels(json_path: Path) -> list[str]:
    """某一天的剧本 JSON 里，按顺序出现的所有 `time_label`。
        English:
    All `time_label`s that appear in order in a given day's script JSON.
    """
    try:
        data = json.loads(json_path.read_text(encoding='utf-8', errors='ignore'))
    except Exception:                                            # noqa: BLE001
        return []
    if not isinstance(data, list):
        return []
    out = []
    for sc in data:
        if isinstance(sc, dict):
            t = str(sc.get('time_label') or '').strip()
            if t:
                out.append(t)
    return out


def _labels_from_md(md_path: Path) -> list[str]:
    """退回从 Markdown 里抠时刻 —— 场景标题写成 `## 辰时 08:00`。
        English:
    Fall back to extracting the moment from Markdown —— the scene heading is written as `## 辰时
    08:00`.
    """
    try:
        text = md_path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return []
    return [ln[3:].strip() for ln in text.splitlines()
            if ln.startswith('## ') and ln[3:].strip()]


def _days_in(d: Path) -> list[tuple[int, Path]]:
    """一个目录里所有 `第NNN天.*` 的 `[(天号, 路径), …]`（只收 md / json）。
        English:
    `[(day number, path), …]` of all `第NNN天.*` in a directory (only md / json collected).
    """
    d = Path(d)
    if not d.is_dir():
        return []
    out: list[tuple[int, Path]] = []
    for p in d.iterdir():
        if p.suffix.lower() not in ('.md', '.json'):
            continue
        m = _DAY_RE.match(p.stem)
        if m:
            out.append((int(m.group(1)), p))
    return sorted(out, key=lambda x: (x[0], str(x[1])))


def _days_from_db(db_path: Path) -> tuple[int, int]:
    """最后一招：从 `state.db` 的事件/摘要里取天数范围。

    ⚠ **只读打开**（`mode=ro`）：这一轮可能正被另一个进程写着，用可写方式
      打开会抢锁；而且"看一眼有多少天"本来就不该动人家的库。
    
        English:
    Last resort: get the day range from the events/summaries in `state.db`.
        ⚠ **Open read-only** (`mode=ro`): this round may be being written by another process right now, and opening it writable
          would fight for the lock; also, "taking a peek at how many days there are" shouldn't touch someone else's DB anyway.
    """
    if not Path(db_path).is_file():
        return (0, 0)
    try:
        con = sqlite3.connect(f'file:{Path(db_path).as_posix()}?mode=ro',
                             uri=True, timeout=1.0)
    except Exception:                                            # noqa: BLE001
        return (0, 0)
    try:
        lows: list[int] = []
        highs: list[int] = []
        for table, col in (('events', 'game_day'), ('summary', 'game_day')):
            try:
                row = con.execute(
                    f'SELECT MIN({col}), MAX({col}) FROM {table}').fetchone()
            except Exception:                                    # noqa: BLE001
                continue
            if row and row[0] is not None:
                lows.append(int(row[0]))
                highs.append(int(row[1]))
        if not lows:
            return (0, 0)
        return (min(lows), max(highs))
    finally:
        con.close()


def story_span_of(run_dir: Path) -> StorySpan:
    """读一个**运行文件夹**，算出故事里的时间跨度（**纯读盘，不问模型**）。

    取法按可靠性从高到低：

    1. `每天的生活/第NNN天.json`（**事实来源**）→ 首末两天的 `time_label`；
    2. `每天的生活/第NNN天.md`（呈现）→ 抠 `## <时刻>` 那一行；
    3. `每天的生活/原文/第NNN天.md`（小说原文，可能有、可能没有）；
    4. `state.db` 的事件/摘要表 → 只有天数、没有时刻。

    任一层读到就返回，读不到返回一个空的 `StorySpan`（`ok` 为假）——
    **界面必须容忍它**（旧存档、只跑了一半就关掉的存档都可能没有这些文件）。
    
        English:
    Read a **run folder** and compute the time span within the story (**pure disk read, no asking
    the model**).
        Methods ordered by reliability, highest to lowest:
        1. `每天的生活/第NNN天.json` (**source of truth**) → the `time_label` of the first and last days;
        4. `state.db`'s events/summaries table → only day numbers, no moments.
        Return as soon as any layer reads successfully; if none do, return an empty `StorySpan` (`ok` false) ——
        **the UI must tolerate it** (old archives and archives closed halfway through a run may lack these files).
    """
    root = Path(run_dir)
    daily = root / '每天的生活'
    raw = daily / '原文'

    days = _days_in(daily)
    days_raw = _days_in(raw)
    all_day_numbers = sorted({n for n, _ in days} | {n for n, _ in days_raw})
    if not all_day_numbers:
        lo, hi = _days_from_db(root / 'state.db')
        if lo or hi:
            return StorySpan(start_day=lo or hi, end_day=hi or lo,
                             source='state.db')
        return StorySpan()

    first_day, last_day = all_day_numbers[0], all_day_numbers[-1]

    def _side(day: int, *, first: bool) -> str:
        """某一天的时刻：优先 JSON，其次 md，其次原文。
                English:
        Timestamp for a given day: prefer JSON, then md, then raw text.
        """
        for base in (daily, raw):
            jp = base / f'第{day:03d}天.json'
            if jp.is_file():
                lab = _time_labels(jp)
                if lab:
                    return lab[0] if first else lab[-1]
            mp = base / f'第{day:03d}天.md'
            if mp.is_file():
                lab = _labels_from_md(mp)
                if lab:
                    return lab[0] if first else lab[-1]
        return ''

    return StorySpan(start_day=first_day,
                     start_at=_side(first_day, first=True),
                     end_day=last_day,
                     end_at=_side(last_day, first=False),
                     source='每天的生活')


class RunFolder:
    """管理一次模拟的运行文件夹。

    目录结构（设计稿 §10.1）:
    ├── 任务介绍.md
    ├── 本地设定集/
    ├── 每天的生活/
    ├── 关键事件/
    ├── 故事文档/
    ├── 导出/               ← 装订稿与报告（§10.10）：小说参考 / 小说版本 / 运行报告 / 写作指导
    ├── 快照/
    ├── 原始日志/
    ├── state.db
    ├── 新设定建议.md
    ├── 大纲建议.md
    ├── 考据笔记.md
    ├── 分镜表.md
    ├── 合规报告.md
    └── 运行小结.md
    
        English:
    Manage the run folder of one simulation.
        Directory structure (design doc §10.1):
        ├── 快照/
        ├── state.db
        ├── 分镜表.md
    """

    def __init__(self, project_dir: Path, run_name: str):
        self.project_dir = project_dir
        self.root = project_dir / run_name
        self._counters: dict[str, int] = {}

    def story_span(self) -> StorySpan:
        """这一次推演「故事里的时间」跨度（见 `story_span_of`）。
                English:
        The "in-story time" span of this run (see `story_span_of`).
        """
        return story_span_of(self.root)

    # ── 目录结构 ──
    # [EN] ── Directory structure ──
    def create(self) -> "RunFolder":
        for sub in ("本地设定集", "每天的生活", "关键事件", "故事文档",
                     "导出", "快照", "原始日志"):
            ensure_dir(self.root / sub)
        return self

    @property
    def settings_dir(self) -> Path:
        return self.root / "本地设定集"

    @property
    def daily_dir(self) -> Path:
        return self.root / "每天的生活"

    @property
    def story_dir(self) -> Path:
        """★ 2026-10-10：**小说原文**（原著样章）单独一个目录。

        用户原话：「**保留小说原文**，后续推演结束导出的时候，原文是重点导出项目」。

        为什么非要另开一个目录、而不是靠 `每天的生活/第NNN天.md`：
        那个文件写的是**当天最终呈现**——剧本模式下它是剧本、普通模式下它是
        收工整理稿，**都不是小说作家当初写的那一篇**。
        样章 `DayScript.story` 从前**只活在内存里**（推演结束就没了），
        所以"保留原文"这句话以前是**做不到**的，不是"没导出"而已。
        现在它在写出来的那一刻就落一份，导出再把它们拼起来。
        
                English:
        ★ 2026-10-10: **novel raw text** (original sample chapters) gets its own directory.
                User's exact words: "**keep the novel raw text**; when exporting after a run ends, the raw text is a key export item".
                That file holds the **final presentation for the day** —— in script mode it's the script, in normal mode it's the
                end-of-day cleaned-up draft, **neither is the piece the novelist originally wrote**.
                The sample chapter `DayScript.story` previously **lived only in memory** (gone when the run ended),
                so the phrase "keep the raw text" was previously **impossible**, not merely "not exported".
                Now it's saved the moment it's written out, and export concatenates them.
        """
        return self.root / "每天的生活" / "原文"

    def flush_day_story(self, game_day: int, text: str,
                        calendar_str: str = "") -> None:
        """把**当天的开场样章**落盘（`每天的生活/原文/第NNN天.md`）。

        ★★★ 2026-10-26：**这不是"这一天"**，所以改名口径也改了。
          它写的是 `ds.story` —— 剧作者**开演前**写的那一段引导（代码里原话
          「样章一写好就落一份原文」）。剧本模式下一天可能演 133 幕，
          而这一份只有一两千字 ⇒ 它是**引子**，不是全文。

          以前导出把它当"原始稿"的来源，于是用户看到
          「原始稿（1525 字，午后账房）和最终成稿（8654 字，深夜前堂）
          完全不是一个故事」—— 一份是开场、一份是深夜，当然对不上。
          现在导出的「原始稿」改读**每天的全量正文**（见 `export/novel_version.read_day_full`），
          这个文件只作为"当初那段引子"保留下来，随时可查。

        ⚠ 与 `flush_daily*` 并列而不是复用它：那两个写"当天的呈现"，
          这个写"开演前的那段引子"。混用一个文件就必然互相覆盖。
        [EN] ★★★ 2026-10-26: this is **not "the day"**, hence the renamed wording. It writes
        [EN] `ds.story` -- the lead-in the playwright wrote **before** the day started. A script-mode
        [EN] day can run 133 acts while this holds one or two thousand chars: an intro, not the whole.
        [EN] Exports used to treat it as the raw draft, which is why the user saw "raw (1525 chars,
        [EN] afternoon ledger room) vs final (8654 chars, late-night front hall) -- not even the same
        [EN] story". Now the raw draft reads the day's full body; this file is kept only as "that
        [EN] opening lead-in". Parallel to `flush_daily*` rather than reusing it: those write "the
        [EN] day's presentation", this writes "the lead-in before the curtain" -- sharing one file
        [EN] would have them overwrite each other.
        """
        body = str(text or '').strip()
        if not body:
            return
        # ⚠ 标题也改了：原来写「原文（原著样章）」，读者会以为这是这一天的全文。
        # [EN] Title changed too: it used to say "raw text (original sample)", implying the whole day.
        header = (f"# 第 {game_day} 天 · 开场样章（开演前写的引导段，不是这一天全文）"
                  + (f" · {calendar_str}" if calendar_str else ""))
        atomic_write_text(self.story_dir / f"第{game_day:03d}天.md",
                          header + "\n\n" + body + "\n")

    @property
    def events_dir(self) -> Path:
        return self.root / "关键事件"

    @property
    def storyline_dir(self) -> Path:
        return self.root / "故事文档"

    @property
    def export_dir(self) -> Path:
        """导出物目录（§10.10）：小说参考 / 小说版本 / 运行报告 / 写作指导。

        为什么不塞进 `故事文档/`？那是 `storyline` 命令的产出目录，
        语义是「推演结论」。导出物是「装订成册给人读的」，混在一起会分不清。
        
                English:
        Export artifact directory (§10.10): novel reference / novel version / run report / writing
        guide.
                Why not stuff it into `故事文档/`? That's the output directory of the `storyline` command,
                its meaning is "run conclusions". Exports are "bound into a booklet for people to read", mixing them makes it unclear.
        """
        return self.root / "导出"

    @property
    def snapshots_dir(self) -> Path:
        return self.root / "快照"

    @property
    def logs_dir(self) -> Path:
        return self.root / "原始日志"

    @property
    def db_path(self) -> Path:
        return self.root / "state.db"

    @property
    def task_intro_path(self) -> Path:
        return self.root / "任务介绍.md"

    @property
    def run_summary_path(self) -> Path:
        return self.root / "运行小结.md"

    @property
    def new_settings_path(self) -> Path:
        return self.root / "新设定建议.md"

    @property
    def outline_path(self) -> Path:
        return self.root / "大纲建议.md"

    @property
    def storyline_path(self) -> Path:
        return self.storyline_dir / "故事线汇总.md"

    @property
    def compliance_report_path(self) -> Path:
        return self.root / "合规报告.md"

    # ── 任务介绍 ──
    # [EN] ── Task introduction ──
    def write_task_intro(self, info: dict[str, Any]) -> None:
        lines = ["# 任务介绍", f"\n> 生成时间：{now_str()}", ""]
        for k, v in info.items():
            lines.append(f"- **{k}**：{v}")
        atomic_write_text(self.task_intro_path, "\n".join(lines))

    # ── 每天的生活 ──
    # [EN] ── Daily life ──
    def write_report(self, name: str, text: str) -> None:
        """在运行文件夹根写一份**给人看的报告**（`去AI审计.md` 之类）。

        为什么不各写各的 `atomic_write_text`：那样"写在哪儿"这件事就会在
        三个地方各记一遍（很容易一个写根、一个写 `每天的生活/`，
        查起来莫名其妙）。统一走这里，路径只有一个来源。
        ⚠ `name` **不许带路径分隔符** —— 用 `Path(...).name` 兜掉，
          防着有人从配置里传进来一个 `../`。
        
                English:
        Write a **human-readable report** at the root of the run folder (`去AI审计.md` or similar).
                Why not each write its own `atomic_write_text`: then "where it's written" would be recorded in
                three separate places (easy for one to write to root, one to `每天的生活/`,
                making debugging baffling). Route everything through here, so the path has only one source.
                ⚠ `name` **must not contain a path separator** —— strip it with `Path(...).name`,
                  to guard against someone passing in a `../` from config.
        """
        safe = Path(str(name or '')).name
        if not safe:
            raise ValueError('报告名不能为空')
        atomic_write_text(self.root / safe, str(text or ''))

    def flush_daily(self, game_day: int, content: str, calendar_str: str = "",
                    film_header: str = "", partial_at: str = "") -> None:
        """落盘一天（纯文本）。`film_header` = 影视镜头卡（`FILM_MODE`），
        按设计稿 §10.8 写在**段首** —— 放在正文后面就成了"附注"，
        拍剧的人要翻到最后才看得到。

        `partial_at`（2026-10-23）：与 `flush_daily_script` 的同名参数同一口径 ——
        非空 = **定时落盘写的中途稿**，头部插一行"还在演"的标记。
                English:
        Persist one day (plain text). `film_header` = film shot card (`FILM_MODE`),
                written at the **start of the paragraph** per design doc §10.8 —— placing it after the body makes it an "annotation",
                and the people shooting the drama would have to flip to the end to see it.
                `partial_at` (2026-10-23): same rule as the parameter of the same name in `flush_daily_script` --
                non-empty = **mid-progress draft written by the timer**, with a "still playing" marker in
                the header.
        """
        fname = f"第{game_day:03d}天.md"
        # ★★★ 2026-10-26 第二层防御：**同一天已经有 `.json` 边车 ⇒ 这一天是脚本格式，
        #   纯文本绝不许覆盖它**。
        #
        #   为什么需要这一层（第一层在 `sim/loop._flush`：脚本模式不再落到纯文本分支）：
        #   两条写盘路径共用同一个 `.md` 文件名，而只有脚本路径写 `.json`。
        #   于是"有 json 却调到这里"就意味着**格式要变了** —— 用纯文本盖掉剧本，
        #   而 json 还是完整的 ⇒ md 与 json 永久分叉，导出（读 md 的那些）拿到残稿。
        #   实测事故：第 1 天 json 133 幕/21.3 万字，md 被盖成 381 字。
        #
        #   ⚠ 这里**不是**静默跳过：写一条 warning（含双方字数），否则"为什么我的稿子没更新"
        #     将无法从日志里回答。
        # [EN] ★★★ 2026-10-26, second line of defence: if that day already has a `.json` sidecar it is a
        # [EN] script-format day, and plain text must **never** overwrite it. Both writers share one
        # [EN] `.md` filename while only the script path writes `.json`, so reaching here with a
        # [EN] `.json` present means the format would change -- and md/json would diverge forever,
        # [EN] leaving every md-reading consumer (exports) with a remnant. Measured: json 133 acts /
        # [EN] 213k chars, md overwritten to 381 chars. Not silent: warn with both sizes.
        sidecar = self.daily_dir / f"第{game_day:03d}天.json"
        if sidecar.exists():
            _LOG.warning(
                '第 %d 天已有 .json 边车（脚本格式），拒绝用纯文本覆盖 .md：'
                '传入 %d 字，盘上 .json %d 字节。要改这一天请走 flush_daily_script。',
                game_day, len(str(content or '')),
                sidecar.stat().st_size if sidecar.exists() else -1)
            return
        header = f"# 第 {game_day} 天" + (f" · {calendar_str}" if calendar_str else "")
        head = (film_header.strip() + "\n\n") if film_header.strip() else ""
        # ★ 中途稿标记（同 `flush_daily_script`）：第一屏就要看出"这一天还在演"。
        # [EN] Mid-progress marker (same as `flush_daily_script`): the first screen must show "this day
        # [EN] is still playing".
        if partial_at:
            head = (f"> ⏳ **定时落盘 · {partial_at}** —— 这一轮还在跑，"
                    f"收工 / 换天时会把这一天重写成完整版。\n\n") + head
        atomic_write_text(self.daily_dir / fname, header + "\n\n" + head + content)

    # ── 剧本式「每天的生活」（设计稿 §10.6 扩展，见 剧本输出格式.md）──
    # [EN] ── Script-style "daily life" (design doc §10.6 extension, see 剧本输出格式.md) ── 【Output language】All
    # [EN] **output text** must be written in **Simplified Chinese** — narration, voice-over, dialogue,
    # [EN] documents, summaries, and suggestions all count, **even if the source material is in another
    # [EN] language**. For proper nouns such as person names, place names, and book titles, **keep the
    # [EN] original spelling**, do not transliterate or free-translate. In JSON, **keep key names as they
    # [EN] are** (e.g. "动作", "台词"), and only write the **values** in Chinese.
    def flush_daily_script(self, game_day: int, scenes: list, *,
                           calendar_str: str = '', weather: str = '',
                           cast: list[str] | None = None,
                           tension: str = '', key_events: list[str] | None = None,
                           film_header: str = '', recap: str = '',
                           scene_intro: str = '', day_brief: str = '',
                           partial_at: str = ''
                           ) -> Path:
        """落盘一天的剧本：`.md` 给人看，`.json` 边车给机器读。

        `scene_intro` = **剧作者写的那一小段场景介绍**（40~80 字）。
        用户 2026-10-07：「前情提要和场景介绍不能够丢」—— 以前"场景介绍"只有
        `**场景** / **环境** / **在场**` 三行元数据，那是**表头不是介绍**。
        顺序照用户要的：**前情提要 → 场景介绍 → 人物开口**。

        ★★★ `partial_at`（2026-10-23 新增）：非空 ⇒ 这是**定时落盘写的中途稿**，
          值就是落下那一刻的时间串。会在头部插一行醒目的「还在演」标记。

          用户这次的要求：「电脑突然关机 / 随手关掉程序，**下一次打开拾卷里的存档
          可以拿到最近的记录（最多损失 30 秒）**」。
          以前 `每天的生活/` 只在**日界 / 收工**才写，于是断电丢的是**整轮**；
          现在定时器每 `AUTOSAVE_SECONDS` 秒把它重写一遍。

          ⚠ 为什么中途稿可以写进 `每天的生活/`（而 `sim/autosave.py` 的
            `进度.md` 刻意写在 `自动落盘/`）：两者的**用途不同** ——
            `进度.md` 是"给人看的中途快照"，不参与任何结构化读取；
            而这里这份**必须**能被 `read_daily_script()` 读回来，
            否则续跑时那一天的半截正文就没了（`load_resume_scenes` 读的就是它）。
          ⚠ 但"混进正式产物"的风险是真的，所以**必须留痕**：`partial_at` 非空时
            头部有一行 `> ⏳ 定时落盘（…）`。日界/收工的正式落盘**不带**这一行
            （调用方不传），于是"这份是半截还是完整的"看第一屏就知道。

        Why two files?
          Markdown 好读好改，但反解有歧义（人手改一行就可能解析错）；
          JSON 无损，界面直接读它重渲染。
          **JSON 是事实来源，Markdown 是呈现**——文件被手改过也不影响界面。
        
                English:
        Persist one day's script: `.md` for humans, `.json` sidecar for machines.
                `scene_intro` = **the short scene introduction written by the playwright** (40~80 chars).
                User 2026-10-07: "the recap and scene introduction must not be dropped" —— previously "scene introduction" was only
                Order per the user's request: **recap → scene introduction → characters speak**.
                ★★★ `partial_at` (added 2026-10-23): non-empty => this is **the mid-progress draft written
                by the timer**, and the value is the timestamp. A prominent "still playing" marker is
                inserted in the header. The user's request: "the computer suddenly shuts down / the app
                gets closed, and **next time I open the save in 拾卷 I want the latest record (losing at
                most 30 seconds)**". Previously `每天的生活/` was only written at the **day boundary /
                wrap-up**, so a power cut lost **the whole round**; now the timer rewrites it every
                `AUTOSAVE_SECONDS`.
                ⚠ Why the mid-progress draft may live in `每天的生活/` (while `进度.md` in
                `sim/autosave.py` deliberately lives in `自动落盘/`): different purposes -- `进度.md` is
                a human-readable snapshot read by nothing structured; **this** one must be readable by
                `read_daily_script()`, otherwise that day's half-finished body is gone on resume
                (`load_resume_scenes` reads exactly this).
                ⚠ The "polluting the formal artifact" risk is real, so **it must leave a trace**: with
                `partial_at` non-empty the header carries `> ⏳ 定时落盘（…）`. The day-boundary /
                wrap-up write does **not** pass it, so "half or complete" is visible at a glance.
                Why two files?
                  Markdown is easy to read and edit, but reverse-parsing is ambiguous (a single line edited by hand can break parsing);
                  JSON is lossless, the UI reads it directly to re-render.
                  **JSON is the source of truth, Markdown is the presentation** —— hand-edits to the file don't affect the UI.
        """
        from display import script_render as SR

        fname = f"第{game_day:03d}天"
        header = f"# 第 {game_day} 天"
        if calendar_str:
            header += f" · {calendar_str}"
        if weather:
            header += f" · {weather}"

        meta_bits = []
        if cast:
            meta_bits.append(f"在场：{'、'.join(cast)}")
        if key_events:
            meta_bits.append(f"关键事件：{'、'.join(key_events)}")
        if tension:
            meta_bits.append(f"张力：{tension}")

        parts = [header]
        if meta_bits:
            parts.append('> ' + '  '.join(meta_bits))
        # ★ 中途稿标记（`partial_at`）—— 放在**元信息之后、前情提要之前**：
        #   第一屏就能看到"这一天还在演"，不会有人把它当成完整的一天。
        # [EN] Mid-progress marker (`partial_at`) -- after the metadata, before the recap: visible on
        # [EN] the first screen, so nobody mistakes it for a complete day.
        if partial_at:
            parts.append('')
            parts.append(f'> ⏳ **定时落盘 · {partial_at}** —— 这一轮还在跑，'
                         f'收工 / 换天时会把这一天重写成完整版。'
                         f'（电脑突然关机时，下次续跑就从这里接上。）')
        # ★ 前情提要（2026-10-07）：用户明确要求正文里**不能丢**它 ——
        #   以前它只是喂给模型的上下文（`agent._story_so_far` / 长期记忆），
        #   正文里一个字都没有。放在**镜头卡之前**，读起来就是
        #   "先回顾、再进这一天的戏"，与用户说的顺序（前情提要 → 场景介绍 → 人物说话）一致。
        #   用 `>` 引用块：与上面的 `> 在场：…` 同一套，而且 `parse_markdown`
        #   **不会**把 `>` 认成剧本标记（§13.3 的规矩），所以不影响反解。
        # [EN] ★ Previously on (2026-10-07): the user explicitly required that it **must not be lost** from the
        # [EN] main text ——
        # [EN] Previously it was only context fed to the model (`agent._story_so_far` / long-term memory),
        # [EN] not a single word of it in the main text. Placing it **before the shot cards** reads as
        # [EN] "first recap, then enter this day's scene", consistent with the order the user stated
        # [EN] (previously on → scene introduction → characters speaking).
        # [EN] Use a `>` blockquote: same set as the `> 在场：…` above, and `parse_markdown`
        # [EN] **will not** treat `>` as a script marker (the rule in §13.3), so it does not affect parsing
        # [EN] back.
        if recap.strip():
            parts.append('')
            parts.append('> **前情提要**　' + ' '.join(recap.strip().split()))
        # ★ 今日剧情简介（2026-10-07）：用户要的顺序是
        #   「前情提要 → **今日剧情简介** → 正式剧情」，所以它排在前情之后、
        #   场景介绍之前。同样是 `>` 引用块（不影响反解）。
        # [EN] ★ Today's plot summary (2026-10-07): the order the user wants is
        # [EN] "previously on → **today's plot summary** → main plot", so it comes after the recap and
        # [EN] before the scene introduction. It is likewise a `>` blockquote (does not affect parsing back).
        if day_brief.strip():
            parts.append('')
            parts.append('> **今日剧情简介**　'
                         + ' '.join(day_brief.strip().split()))
        # ★ 场景介绍（同日）：紧跟前情提要，**在镜头卡之前**。
        #   同样是 `>` 引用块，同样不影响反解。
        # [EN] ★ Scene introduction (same day): immediately after the recap, **before the shot cards**.
        # [EN] Also a `>` blockquote, also does not affect parsing back.
        if scene_intro.strip():
            parts.append('')
            parts.append('> **场景介绍**　' + ' '.join(scene_intro.strip().split()))
        # ★ 影视镜头卡写在**段首**（设计稿 §10.8）—— 只写 `.md`（呈现），
        #   `.json` 是事实来源、供界面重渲染，不该被镜头卡污染。
        # [EN] ★ Film/TV shot cards are written at the **paragraph start** (design doc §10.8) —— only written
        # [EN] to `.md` (presentation);
        # [EN] `.json` is the source of truth, used for re-rendering the UI, and should not be polluted by shot
        # [EN] cards.
        if film_header.strip():
            parts.append('')
            parts.append(film_header.strip())
        parts.append('')
        body = '\n\n'.join(SR.to_markdown(s).rstrip() for s in scenes)
        md_path = self.daily_dir / f"{fname}.md"
        atomic_write_text(md_path, '\n'.join(parts) + '\n' + body + '\n')

        atomic_write_text(self.daily_dir / f"{fname}.json", SR.to_json(scenes))
        return md_path

    def read_daily_script(self, day: int | None = None) -> list:
        """读回某天的剧本（省略 day = 最近一天）。

        优先读 `.json` 边车；没有（旧运行文件夹、或用户删了）就反解 `.md`。
        两者都没有时返回空列表，调用方自行决定回退到纯文本。
        
                English:
                Prefer reading the `.json` sidecar; if absent (old run folder, or user deleted it), parse it back out of the `.md`.
                If neither exists, return an empty list; the caller decides whether to fall back to plain text.
        """
        from display import script_render as SR

        md_files = sorted(self.daily_dir.glob('*.md')) if self.daily_dir.exists() else []
        if not md_files:
            return []
        target = None
        if day is not None:
            target = next((p for p in md_files
                           if p.stem.startswith(f'第{day:03d}天')), None)
        target = target or md_files[-1]

        sidecar = target.with_suffix('.json')
        if sidecar.exists():
            scenes = SR.from_json(sidecar.read_text(encoding='utf-8'))
            if scenes:
                return scenes
        try:
            text = target.read_text(encoding='utf-8')
        except Exception:
            return []
        # 旧格式（自由文本）**不解析**：以原样纯文本呈现，保住它自己的段落结构
        # [EN] Old format (free text) is **not parsed**: presented as-is in plain text, preserving its own
        # [EN] paragraph structure
        if not SR.looks_like_script(text):
            return []
        try:
            return SR.parse_markdown(text)
        except Exception:
            return []

    # ── 关键事件卡 ──
    # [EN] ── Key event cards ──
    def save_event_card(self, event_id: str, content: str) -> None:
        atomic_write_text(self.events_dir / f"{event_id}.md", content)

    # ── 任意产物写入 ──
    # [EN] ── Arbitrary artifact writes ──
    def write(self, rel_path: str, text: str) -> None:
        atomic_write_text(self.root / rel_path, text)

    # ── 子文件夹枚举 ──
    # [EN] ── Subfolder enumeration ──
    def list_files(self, rel_dir: str, suffix: str = ".md") -> list[Path]:
        d = self.root / rel_dir
        return sorted(d.glob(f"*{suffix}")) if d.exists() else []


def make_run_name(run_index: int) -> str:
    return f"第{run_index}次模拟{now_str('%Y-%m-%d-%H-%M')}"