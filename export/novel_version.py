# -*- coding: utf-8 -*-
"""小说合订导出（设计稿 §10.10）：把**某一次运行**的产物装订成册。

一次运行会散落成 N 个「第NNN天.md」。想通读一遍、或想拿去改写，
都需要把它们装订起来。本模块提供两种装订方式，**区别只有一列**：留不留过程痕迹。

| 模式 | 产物 | 留下什么 | 给谁看 |
|---|---|---|---|
| `reference` | `原始稿加细节_v1.md` | **全留**：在场名单、本幕依据（节点/伏笔）、机制备注、图片路径 | 创作者对照改写用的**素材册** |
| `novel` | `最终改写稿_v1.md` | **剃净**：只留时间/场景/出场退场/旁白/对白/动作/心声/同时 | 当**小说**读 |

两者都**零成本、不调 LLM、一字不改正文**。想更连贯，再走可选的润色（另存一份）。

和既有导出物的分工，别搞混：

| 导出物 | 归属 | 面向 |
|---|---|---|
| 故事线汇总 / 写作指导（大纲建议） | `export/outputs.py` | 推演结论与建议 |
| 运行报告 | `export/outputs.py` | 复盘与账单 |
| 调度与勾选 | `export/bundle.py` | 把上面这些串起来 |
| **原始稿加细节 / 最终改写稿** | 本文件 | 装订成册，拿来读 |

**中途导出是天生支持的**：只把「已经落盘的天」写进去。
循环只在 `_end_day` 落盘，所以落盘的天天然就是完整的——没跑完的那天
不会以半成品的样子混进稿子。要再往前截断，传 `upto_day`。

English:
**Mid-run export is natively supported**: only write the "days already flushed to disk".
The loop only flushes at `_end_day`, so the flushed days are naturally complete - the day that
hasn't finished running
won't get mixed into the draft as a half-finished product. To truncate earlier, pass `upto_day`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from config import CFG
from llm.router import llm
from util.io import atomic_write_text, ensure_dir
from util.text import now_str

_LOG = __import__("logging").getLogger("nws.export.novel")

_DAY_RE = re.compile(r"^第(\d+)天$")


# ══════════════════════════════════════════════════════════════
#  读：从运行文件夹里把「天」捞出来
# [EN] Read: extract the "day" from the run folder
# ══════════════════════════════════════════════════════════════
def list_days(run) -> list[tuple[int, Path]]:
    """返回 `[(天号, 路径), …]`，按天号升序。路径**优先是 `.md`**。

    ★★★ 2026-10-26：**改成 `.md` ∪ `.json` 的并集**（原来只扫 `.md`）。

    原来这里写着"只看 `.md`，不必拿 `.json` 重渲染一遍（结果一样）"——
    **两处都错了**：
      ① "结果一样"不成立：`.md` 会被纯文本分支覆盖成残片（见 `read_day_full`），
         `.json` 才是事实来源；
      ② 只扫 `.md` ⇒ **某天 `.md` 丢了/没写，那一天就整个从导出里消失**，
         哪怕 `.json` 完整。实测（2026-10-26 端到端探针）：只放 `.json` 的那一天
         根本没出现在导出里 —— 而且**没有任何报错**，因为"没有这一天"和
         "这一天是空的"在调用方看来一样。
    ⇒ 现在按天号取并集；只有 `.json` 时返回一个**可能不存在的 `.md` 路径**，
      `read_day_full` 会自己去读边车（它先看 `.json`）。
    [EN] ★★★ 2026-10-26: now the **union of `.md` and `.json`** (it used to scan `.md` only).
    [EN] The old comment claimed re-rendering was pointless "the result is the same" -- wrong twice:
    [EN] (1) it isn't the same, `.md` may be an overwritten remnant (see `read_day_full`) while
    [EN] `.json` is the source of truth; (2) scanning `.md` only means **a day whose `.md` is missing
    [EN] vanishes from the export entirely**, silently. Measured with the e2e probe: a day that had
    [EN] only `.json` never appeared. Now the union by day number; when only `.json` exists we return a
    [EN] possibly-missing `.md` path and `read_day_full` reads the sidecar.
    """
    d = run.daily_dir
    if not d.exists():
        return []
    found: dict[int, Path] = {}
    for p in sorted(d.glob('*.md')):
        m = _DAY_RE.match(p.stem)
        if m:
            found[int(m.group(1))] = p
    for p in sorted(d.glob('*.json')):
        m = _DAY_RE.match(p.stem)
        if m:
            n = int(m.group(1))
            if n not in found:          # 只有 json：留一个 md 路径占位
                found[n] = p.with_suffix('.md')
    return sorted(found.items(), key=lambda x: x[0])


def _days_of(d) -> list[tuple[int, Path]]:
    """`list_days` 的通用版：给一个目录，返回 `[(天号, 路径), …]`（**只收 `第NNN天.md`**）。

    ⚠ 必须**只认 `第NNN天.md` 这个形状**：原文目录里可能以后还会放别的东西
      （校对稿、去 AI 味稿），不加过滤就会把它们一起当"原文"装订进去。
    
        English:
    Generic version of `list_days`: given a directory, return `[(day_number, path), …]` (**only
    collect `第NNN天.md`**).
        ⚠ Must **only recognize the `第NNN天.md` shape**: the source directory may later contain other things
          (proofread drafts, de-AI-flavored drafts), and without filtering they'd get bound in as "source text" too.
    """
    d = Path(d)
    if not d.exists():
        return []
    out: list[tuple[int, Path]] = []
    for p in sorted(d.glob("*.md")):
        m = _DAY_RE.match(p.stem)
        if m:
            out.append((int(m.group(1)), p))
    return sorted(out, key=lambda x: x[0])


def _split_day_file(text: str) -> tuple[str, str, str]:
    """把一天的文件拆成 `(标题, 元信息行, 正文)`。

    落盘格式（`RunFolder.flush_daily_script`）：
        # 第 1 天 · 历法 · 天气
        > 在场：…  关键事件：…  张力：…
        （空行）
        正文…

    正文里的 `## 幕` 标题保持不动，它本来就该跟着走。
    
        English:
    Split a single day's file into `(title, meta_info_line, body)`.
        Flushed format (`RunFolder.flush_daily_script`):
            # Day 1 · Calendar · Weather
            > Present: …  Key events: …  Tension: …
            (blank line)
            body…
        The `## Act` headings in the body stay untouched; they should follow along anyway.
    """
    lines = text.splitlines()
    title = ""
    meta = ""
    body_lines: list[str] = []
    state = 0                     # 0=等标题 1=等元信息 2=正文
    # [EN] 0=waiting for title 1=waiting for meta info 2=body
    for ln in lines:
        s = ln.strip()
        if state == 0:
            if s.startswith("#"):
                title = s.lstrip("#").strip()
                state = 1
            elif s:
                state = 2             # 没有标题的裸文本，整段算正文
                # [EN] Bare text without a title, the whole block counts as body
                body_lines.append(ln)
            continue
        if state == 1:
            if s.startswith(">"):
                meta = s.lstrip(">").strip()
                continue
            if not s:
                continue              # 标题与正文之间的空行
                # [EN] Blank line between title and body
            state = 2
        body_lines.append(ln)
    body = "\n".join(body_lines).strip()
    return title, meta, body


def read_day(path: Path) -> tuple[str, str, str]:
    """读一天的文件（容错：读不出来就当空）。
        English:
    Read one day's file (fault-tolerant: if it can't be read, treat as empty).
    """
    try:
        return _split_day_file(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return "", "", ""


#: 行内绝对路径（`〔图〕望江楼  C:\…\第3次模拟…\插画\x.png`）。
#: 导出稿里**绝不能留**：那是**别的运行**的目录，发出去对方点不开，而且泄露本机路径。
#: 只留地点名（`〔图〕望江楼`），真正的插图由 `scene_plate_block` 按本运行重出。
#: [EN] Inline absolute path. Must **never** survive into an export: it points at **another run's**
#: folder, so it is dead for the reader and leaks a local path. Keep only the place name; real
#: plates are produced by `scene_plate_block` for this run.
_INLINE_ABS_PATH = re.compile(r'(〔图〕\s*\S+)\s+[A-Za-z]:\\[^\n]*')


def day_json_path(md_path: Path) -> Path:
    """某一天的 `.json` 边车路径（与 `.md` 同目录同名）。"""
    return Path(md_path).with_suffix('.json')


def read_day_full(path: Path) -> tuple[str, str, str]:
    """读一天的**全量**正文，返回 `(标题, 元信息, 正文)`。

    ★★★ 2026-10-26 新增，修的是一个**内容级**的错：

    以前导出走 `read_day()`，它只读 `.md`。而 `.md` 会**被纯文本分支覆盖**
    （`RunFolder.flush_daily` 只写 md、不写 json，两条路径共用同一个文件名）——
    实测某次运行：第 1 天的 `.json` 记着 **133 幕 / 21.3 万字**（辰时 08:00 → 子时 23:59），
    而 `.md` 只剩 **381 字**（那一刻的十几句对话）。
    ⇒ 导出把"一天最后十几秒"当成了"一整天"，用户看到「原始稿和最终成稿完全不是一个故事」。

    ⇒ 现在**以 `.json` 为事实来源**（它本来就是：`read_daily_script()` 续跑读的就是它），
      用同一套渲染器 `script_render.to_markdown` 出文本 —— 渲染器只有一处，
      不会出现"界面一套、导出一套"。

    ⚠ json 不存在（老运行，或纯文本模式）→ **退回 `.md`**，不是返回空。
    ⚠ json 存在但解析不出幕（空列表）→ 也退回 `.md`：宁可给旧的，也不要给空。
    [EN] ★★★ Added 2026-10-26, fixing a **content-level** bug. Exports used `read_day()`,
    [EN] which reads only `.md`. But `.md` **gets overwritten by the plain-text branch**
    [EN] (`flush_daily` writes md and never json, yet both share one filename). Measured: one run's
    [EN] day 1 `.json` held **133 acts / 213k chars** while `.md` was down to **381 chars**.
    [EN] So the export treated "the last dozen seconds of a day" as "the whole day".
    [EN] Now `.json` is the source of truth (it always was), rendered by the same
    [EN] `script_render.to_markdown`, so there is exactly one renderer.
    """
    from display import script_render as SR

    jp = day_json_path(path)
    if jp.is_file():
        try:
            scenes = SR.from_json(jp.read_text(encoding="utf-8", errors="ignore"))
        except Exception:                                        # noqa: BLE001
            scenes = []
        scenes = [s for s in scenes if s is not None]
        if scenes:
            m = _DAY_RE.match(Path(path).stem)
            day = int(m.group(1)) if m else 0
            labels = [str(getattr(s, 'time_label', '') or '').strip() for s in scenes]
            labels = [x for x in labels if x]
            title = f"第 {day} 天" if day else Path(path).stem
            if labels:
                span = labels[0] if labels[0] == labels[-1] else f"{labels[0]} → {labels[-1]}"
                title += f" · {span}"
            # 元信息：这一天的在场并集 + 幕数。数字是**数出来的**，不是估的。
            # [EN] Meta: union of the cast across the day + act count. Numbers are **counted**.
            cast: list[str] = []
            for s in scenes:
                for n in (getattr(s, 'cast', None) or []):
                    n = str(n or '').strip()
                    if n and n not in cast:
                        cast.append(n)
            bits = [f"共 {len(scenes)} 幕"]
            if cast:
                bits.insert(0, "在场：" + "、".join(cast))
            meta = "  ".join(bits)
            body = "\n\n".join(SR.to_markdown(s).rstrip() for s in scenes)
            body = _INLINE_ABS_PATH.sub(r'\1', body).strip()
            if body:
                return title, meta, body
    return read_day(path)


# ══════════════════════════════════════════════════════════════
#  按**事件**分组（一个事件可能跨天）
# [EN] Group by **event** (one event may span several days)
# ══════════════════════════════════════════════════════════════
def day_stations(path: Path) -> list[str]:
    """这一天**演了哪几站**（进度节点的名字），按出现顺序。

    ★★★ 2026-10-26 新增。用户原话：「**注意 一个事件可能跨天**」——
    而装订层一直按**天**切章，于是同一站演到一半被日界切断，
    读者看到两章各半截（第 1 天章末尾在"推门"，第 2 天章开头又是另一场）。
    `_carry_unplayed_beats` 已经让剩余的拍跨到第二天，所以这种切断在真跑里**会发生**。

    ⚠ 只读 `.json` 边车（幕里才带 `node_name`）。没有 json 的老运行 ⇒ 返回空列表
      ⇒ 下游**不分组**，逐字回到"一天一章"的旧行为。这是有意的退化路径：
      跨天合并是**增强**，不该让任何老项目导不出书。
    ⚠ 只做**连续去重**（`[A,B,A]` 保持原样）：`[0]` 与 `[-1]` 分别是"这天开头/结尾在哪一站"，
      真去重会把结尾那一站改错 —— 而那正是判"是否跨天"的依据。
    [EN] Which stations (progress nodes) this day played, in order. ⚠ Reads only the `.json`
    [EN] sidecar (only scenes carry `node_name`). Old runs without json => empty list => no
    [EN] grouping => the exact old one-chapter-per-day behaviour. Deliberate: cross-day merging is
    [EN] an enhancement and must never make an old project unexportable. ⚠ Collapse **consecutive**
    [EN] duplicates only: `[0]` / `[-1]` are "where the day starts / ends", and deduplicating
    [EN] across the whole list would corrupt the ending station -- which is the very signal used
    [EN] to decide whether the event spans days.
    """
    jp = day_json_path(path)
    if not jp.is_file():
        return []
    try:
        from display import script_render as SR
        scenes = SR.from_json(jp.read_text(encoding="utf-8", errors="ignore"))
    except Exception:                                            # noqa: BLE001
        return []
    out: list[str] = []
    for s in (scenes or []):
        n = str(getattr(s, 'node_name', '') or '').strip()
        if n and (not out or out[-1] != n):
            out.append(n)
    return out


def group_days_by_event(days: list[tuple[int, Path]]) -> list[dict]:
    """把相邻的天按**同一个事件**分组：`[{name, days:[(day,path)], single}]`。

    ★ 判据（保守，宁可少合并不错合并）：
      前一天**整天空只演了一个站**（`single`），且今天**从这个站开始** ⇒ 同一事件跨天。

    ⚠ 为什么要求"前一天只有一个站"：如果前一天演了 A、B 两站，而今天从 B 开始，
      把前一天整天并进"B 事件"那一章里，A 那场戏就被归到了标题写着 B 的章下 ——
      读者会以为 A 是 B 的一部分。**章名与内容不符，比不合并更糟**。
    ⚠ 一旦某天不是"单站"，这一组就不再吸收后面的天（`single` 更新为 False）——
      中间插进来别的站，说明事件已经换了，后面的不该再算同一件。
    [EN] Group adjacent days by the same event. Criterion (deliberately conservative): the
    [EN] previous day played **exactly one station**, and today **starts with that station**.
    [EN] ⚠ Requiring "previous day was single-station" matters: if that day played A then B and
    [EN] today starts with B, folding the whole previous day under a chapter titled B would file
    [EN] scene A under B -- a chapter whose title contradicts its content is worse than no merge.
    [EN] ⚠ Once a day is not single-station the group stops absorbing further days: another
    [EN] station in between means the event changed.
    """
    groups: list[dict] = []
    for day, path in (days or []):
        st = day_stations(path)
        prev = groups[-1] if groups else None
        if prev is not None and prev['single'] and st and st[0] == prev['name']:
            prev['days'].append((day, path))
            prev['single'] = len(st) == 1
            continue
        groups.append({'name': (st[0] if st else ''),
                       'single': len(st) == 1,
                       'days': [(day, path)]})
    return groups


# ══════════════════════════════════════════════════════════════
#  事实采集：没有 world/db 对象时，从落盘文件倒推
# [EN] Fact collection: when there is no world/db object, infer from persisted files
# ══════════════════════════════════════════════════════════════
def collect_facts(run) -> dict:
    """从运行文件夹统计出这次运行的事实。

    为什么要这个？GUI 的「运行中导出」手上**没有** `WorldState` / `DB` 对象
    （循环还没接进界面），只有运行文件夹。所有事实都必须能从盘上读出来。
    读不出来的字段一律留空/为 0，**不许编**。
    
        English:
    Compute this run's facts from the run folder.
        Why is this needed? The GUI's "export during run" has **no** `WorldState` / `DB` object on hand
        (the loop isn't wired into the UI yet), only the run folder. All facts must be readable from disk.
        Any field that can't be read is left empty/0, **no fabrication allowed**.
    """
    days = list_days(run)
    chars = 0
    cast: list[str] = []
    titles: list[str] = []
    for day, path in days:
        # ⚠ 统计也必须读**全量**：以前读 `.md`（可能被覆盖成残稿），
        #   于是导出对话框上"共 N 字"显示的是一天的零头。
        # [EN] Stats must read the **full** body too: `.md` may be an overwritten remnant, so the
        # [EN] dialog's "N chars" used to show a fraction of one day.
        title, _meta, body = read_day_full(path)
        chars += len(re.sub(r"\s", "", body))
        titles.append(title or f"第 {day} 天")
        for name in _speakers_of_day(path):
            if name not in cast:
                cast.append(name)

    ev_dir = run.events_dir
    events = sorted(p.stem for p in ev_dir.glob("*.md")) if ev_dir.exists() else []

    return {
        "run_name": run.root.name,
        "project": run.project_dir.name,
        "days": len(days),
        "last_day": days[-1][0] if days else 0,
        "chars": chars,
        "cast": cast,
        "titles": titles,
        "events": events,
        "cost": _read_cost(run),
    }


def _speakers_of_day(path: Path) -> list[str]:
    """取当天出场的人物名。

    优先读 `.json` 边车（无损、最准）；**没有边车就从 Markdown 里认**——
    这条兜底不能省：旧格式运行文件夹、用户手改删掉边车的、以及
    `OUTPUT_FORMAT=prose` 落下的纯文本，都只有 `.md`。
    少了它，"出场人物"这一栏在这些情况下永远是空的。
    
        English:
    Get the character names appearing that day.
        Prefer reading the `.json` sidecar (lossless, most accurate); **if there's no sidecar, recognize from Markdown** -
        this fallback can't be dropped: old-format run folders, users who manually edited and deleted the sidecar, and
        plain text written by `OUTPUT_FORMAT=prose` all have only `.md`.
        Without it, the "characters present" column would always be empty in these cases.
    """
    sidecar = path.with_suffix(".json")
    if sidecar.exists():
        try:
            from display import script_render as SR
            scenes = SR.from_json(sidecar.read_text(encoding="utf-8"))
            names: list[str] = []
            for s in scenes:
                try:
                    for n in s.speakers():
                        if n and n not in names:
                            names.append(n)
                except Exception:
                    continue
            if names:
                return names
        except Exception:
            pass
    try:
        return _speakers_from_markdown(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return []


# Markdown 里能认出"人"的几种行。顺序 = 可靠性顺序。
# [EN] The kinds of lines in Markdown that can be recognized as a "person". Order = reliability order.
_RE_MD_CAST = re.compile(r'^\*\*在场\*\*\s*(?P<names>.+)$')
_RE_MD_DIR = re.compile(r'^[▸▲]\s*(?:出场|退场|Enter|Exit)\s*(?P<name>[^（(]+)')
_RE_MD_ACTION = re.compile(r'^[·•]\s*(?:动作|Action)\s*(?P<name>[^：:（(]+)')
_RE_MD_ASIDE = re.compile(r'^◇\s*(?:心声|Inner voice)\s*(?P<name>[^：:]+)')
_RE_MD_TRACK = re.compile(r'^-\s*(?P<name>[^｜|]+)[｜|]')
_RE_MD_SPEECH = re.compile(
    r'^(?P<name>[^：:（(*#>〔▸▲·•◇\-\s][^：:（(]{0,11}?)'
    r'(?:（[^）]*）)?(?:\s*→\s*[^：:]+)?[：:]')


def _speakers_from_markdown(text: str) -> list[str]:
    """从落盘 Markdown 里认出当天出现的人物名（去重保序）。

    刻意保守：**只认结构明确的行**，认不出就当没有。
    这比"宁滥勿缺"重要——一份人名单里混进「**环境** 天色」这种东西
    比名单短几个更让人不信任。
    
        English:
    Recognize the character names appearing that day from the flushed Markdown (dedupe, preserve
    order).
        Deliberately conservative: **only recognize clearly structured lines**, and treat unrecognized ones as absent.
        This matters more than "better to over-include than miss" - getting junk like "**environment** sky color" into a
        name list is more untrustworthy than a list that's a few names short.
    """
    names: list[str] = []

    def _add(n: str) -> None:
        n = n.strip().strip('、，,')
        if n and 1 <= len(n) <= 12 and n not in names:
            names.append(n)

    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        m = _RE_MD_CAST.match(s)
        if m:
            for part in re.split(r'[、,，]', m.group('names')):
                _add(part)
            continue
        for rx in (_RE_MD_DIR, _RE_MD_ACTION, _RE_MD_ASIDE, _RE_MD_TRACK, _RE_MD_SPEECH):
            m = rx.match(s)
            if m:
                _add(m.group('name'))
                break
    return names


def _read_cost(run) -> dict:
    """汇总 `原始日志/llm_calls.jsonl`（记录格式见 `llm/router.py: _log_call`）。
        English:
    Aggregate `原始日志/llm_calls.jsonl` (for the record format see `llm/router.py: _log_call`).
    """
    out = {"calls": 0, "in": 0, "out": 0, "by_purpose": {}, "by_model": {}}
    path = run.logs_dir / "llm_calls.jsonl"
    if not path.exists():
        return out
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                tin = int(rec.get("in") or 0)
                tout = int(rec.get("out") or 0)
                out["calls"] += 1
                out["in"] += tin
                out["out"] += tout
                purpose = str(rec.get("purpose") or "未标注")
                slot = out["by_purpose"].setdefault(purpose, {"calls": 0, "in": 0, "out": 0})
                slot["calls"] += 1
                slot["in"] += tin
                slot["out"] += tout
                model = str(rec.get("model") or "未标注")
                mslot = out["by_model"].setdefault(model, {"calls": 0, "in": 0, "out": 0})
                mslot["calls"] += 1
                mslot["in"] += tin
                mslot["out"] += tout
    except OSError:
        pass
    return out


# ══════════════════════════════════════════════════════════════
#  装订成册
# [EN] Bind into a book
# ══════════════════════════════════════════════════════════════
MODE_REFERENCE = 'reference'      # 素材册：全留
MODE_NOVEL = 'novel'              # 最终改写稿：剃净
# [EN] Material book: keep everything
# [EN] Readable draft: shave clean

#: ★★ 第三档：**原始稿**（2026-10-10 用户点名加的）。
# [EN] : ★★ Third tier: **novel raw text** (added 2026-10-10 at the user's explicit request).
#:
#: 与上面两种**根本不同**：上面两种都是"加工过的呈现"（一个剃痕迹、一个全留，
#: 但都只是**从日志里重建**出来的）；这一档是**逐字原样**把
#: `每天的生活/第NNN天.md` 拼起来 —— 不剃、不改、不补标题、不并段。
# [EN] : **Fundamentally different** from the above two: the above two are both "processed
# [EN] presentations" (one strips the traces, one keeps everything,
# [EN] : but both are only **reconstructed from the log**); this tier is **verbatim** concatenation of
#:
#: 用户原话：「**保留原始稿**，后续推演结束导出的时候，**原文是重点导出项目**
#: （如果导出选项里没这个记得加上）」。
#: 为什么需要它：另外两种装订稿都是**程序理解出来的**，一旦渲染规则变了
#: （改了 `_tidy_for_novel`、改了落盘格式），旧稿与新稿就对不上了。
#: 原文是"**当初到底写了什么**"的唯一凭据，也是作者回头改写的原始稿。
# [EN] : User's exact words: "**Keep the novel raw text**; when exporting after a later simulation run
# [EN] finishes, **the raw text is a key export item**
# [EN] : (if there's no such option in the export settings, remember to add it)".
# [EN] : Why it's needed: the other two bound drafts are both **produced by program interpretation**,
# [EN] so once the rendering rules change
# [EN] : (changed `_tidy_for_novel`, changed the on-disk format), old drafts no longer match new
# [EN] drafts.
# [EN] : The raw text is the only evidence of "**what was actually written at the time**", and is the
# [EN] original manuscript the author goes back to rewrite.
MODE_RAW = 'raw'

#: 三档的文件名前缀（**用户看到的、界面上显示的就是这三个词**）。
#:
#:   | 名字 | 拆开看 | 加工到哪一步 | 拿来干什么 |
#:   |---|---|---|---|
#:   | **原始稿** | 原始 | **零加工**：只把每天拼起来加个文件头，**一个字都不动** | 凭据：那时**到底写了什么** |
#:   | **原始稿加细节** | 原始稿 + 细节 | 正文**一字不改**，额外留下过程"细节" | 对照：「这句是从哪条设定长出来的」 |
#:   | **最终改写稿** | 最终 + 改写 | 剃掉细节；**可能整篇被重写**（见下面的 ⚠⚠） | 直接当小说读、拿去改写 |
#:
#:   ★ 名字是**在同一个词根上递进**的：`原始稿` → `原始稿加细节` → `最终改写稿` ——
#:     一眼看得出第一档是起点、第二档是"在它基础上加细节"、第三档是终点。
#:   「细节」= 这四类东西（只有中间那档有）：`**在场**`（这一场都有谁）、
#:   `**依据**`（本幕推进了哪条设定/伏笔）、机制备注、`〔图〕` 图片路径。
#:   它们对**写作者**有用（能倒查依据），对**读者**是噪音。
#:   三份的**素材是同一批**推演记录，区别只有"加不加细节"。名字里不带"小说"二字 ——
#:   它们本来就是小说，差的只是加工到哪一步。
#:
#: ★ 命名来历（2026-10-25 → 26，用户连提四次才定，**别再动**）：
#:   ① 「小说原文 / 小说参考 / 小说版本」—— 三个都带"小说"二字，像同一件东西的三种叫法；
#:   ② 「原稿 / 明细稿 / 正文稿」—— 用户："过程稿 可读稿还是不清楚"；
#:   ③ 「逐字原样稿 / 保留痕迹稿 / 重写可读稿」—— 用户："**保留痕迹稿不好**"，
#:      并直接指定了现在这三个（原始稿 / 原始稿加细节 / 最终改写稿）。
#:   ⚠ 用户当时还点破一件事：**"净稿"那一类说法是错的** ——"净"暗示"只做了减法、内容没动"，
#:     而他实际看到的**内容变化很大**（见下）。这是第三档用"改写"而不是"净"的原因。
#:
#: ⚠⚠ 「最终改写稿」有一个**已知的偏差**，改名前先读这段：
#:   · `MUMU_FOR_EXPORT=false`（出厂默认）时，这一档其实**只是剃掉细节、正文一字未改** ——
#:     此时"改写"偏重了，叫"净稿"反而准。
#:   · `MUMU_FOR_EXPORT=true`（**用户这台机器就是**）时，每天会调 MuMuAINovel
#:     按「原始稿 + 推演过程 + 设定集 + 前几章」**重写一遍** ⇒ 内容确实大变
#:     （实测 v1/v2 相同句子只有 6.1%）。
#:   ⇒ 用户**明知这个偏差、仍然选了「最终改写稿」**，因为他实际看到的就是重写后的东西，
#:     "只洗了一遍"会骗他。**别自作主张改回"净稿"** —— 那正是他否掉的。
#:
#: ⚠ 改名必须**同步改已有文件**：`next_version()` 按 `{前缀}_v*.md` 找编号，
#:   只改代码不改文件 ⇒ 找不到旧号 ⇒ 新导出的又从 v1 开始，出现两份 v1。
#:   （`原始稿` 是 `原始稿加细节` 的前缀，但**不冲突**：glob 是 `原始稿_v*.md`，
#:     而后者在"原始稿"后面跟的是"加细节"、不是 `_v` —— 已实测确认。）
# [EN] Filename prefixes for the three kinds (**these are what the user sees, in the UI and in
# [EN] filenames**): 原始稿 (zero processing, the proof copy) -> 原始稿加细节 (prose untouched, all
# [EN] process "details" kept: cast list / per-scene basis / mechanism notes / image paths) ->
# [EN] 最终改写稿 (details stripped; **may be rewritten wholesale**, see the warning below).
# [EN] ★ The names progress on one root: 原始稿 -> 原始稿加细节 -> 最终改写稿 -- the first is the
# [EN] starting point, the second is "that plus details", the third is the end product.
# [EN] ★ Naming history (user raised it four times, 2026-10-25/26; **do not touch it again**):
# [EN] (1) 小说原文/参考/版本 -- all carried "小说", looked like three labels for one thing;
# [EN] (2) 原稿/明细稿/正文稿 -- rejected as still unclear; (3) 逐字原样稿/保留痕迹稿/重写可读稿 --
# [EN] rejected ("保留痕迹稿不好"), and the user named the current three directly.
# [EN] ⚠ The user also pointed out that a "净稿"-style word is wrong: "clean" implies **only
# [EN] subtraction, content untouched**, while what he actually saw was **a large content change**
# [EN] (see below). That is why the third kind says "rewritten", not "clean".
# [EN] ⚠⚠ "最终改写稿" carries one **known inaccuracy**, read this before renaming:
# [EN] · with `MUMU_FOR_EXPORT=false` (factory default) this kind only strips details and the prose
# [EN]   is untouched -- "rewritten" overstates it then;
# [EN] · with `MUMU_FOR_EXPORT=true` (**this user's machine**) every day is **rewritten** by
# [EN]   MuMuAINovel, so the content genuinely changes (measured: only 6.1% of sentences identical).
# [EN] => The user **knew this trade-off and still chose "最终改写稿"**, because what he sees is the
# [EN]    rewritten output and "just washed" would mislead him. **Do not "fix" it back to a
# [EN]    clean-only word** -- that is exactly what he rejected.
# [EN] ⚠ Renaming must **also rename existing files**, or `next_version()` restarts at v1.
# [EN] (No glob collision: `原始稿_v*.md` does not match `原始稿加细节_v1.md` -- measured.)
_STEM = {MODE_REFERENCE: '原始稿加细节', MODE_NOVEL: '最终改写稿', MODE_RAW: '原始稿'}

# 只有「最终改写稿」才剃掉的行前缀（这些是给人审计用的过程痕迹，不是叙事）：
#   `**在场** A、B`  —— 幕内人物名单
#   `**依据** 节点 …` —— 本幕推进了哪条设定（**参考册里必须留**，这是它的价值）
#   `※ `             —— 机制备注
#   `〔图〕`          —— 插图说明 + 本地路径（路径对读者毫无意义）
# [EN] Only the "readable draft" strips these line prefixes (these are process traces for human
# [EN] auditing, not narrative):
# [EN] `**在场** A、B`  —— in-scene character list
# [EN] `**依据** 节点 …` —— which setting this scene advanced (**must be kept in the reference booklet**;
# [EN] that's its value)
# [EN] `※ `             —— mechanism notes
# [EN] `〔图〕`          —— illustration caption + local path (the path means nothing to readers)
_DROP_IN_NOVEL = ('**在场** ', '**依据** ', '※ ', '〔图〕')

#: **行内**的元标记（不是行首前缀，所以 `_DROP_IN_NOVEL` 抓不到）：
#:   `〔aside·甲〕`   —— 模型把"这是甲的心声"这条机器标记写进了正文
#:   `〔dialogue·甲 → 乙〕`、`{aside·丙}`（半角花括号）
#: 实测某一天里有 **132 处**（`〔aside·` 128 + `〔dialogue·` 12）。留着的话
#: 读起来就是"文件格式"而不是小说 —— 用户要的是成稿。
#: ⚠ **只剃带 `·` 的这几个词**：`〔切至 …〕` / `〔切回〕` / `〔同时〕` / `〔事件 · …〕`
#:   是**转场**，是"同一时刻不同人在做不同事"的表达载体，必须留（见 `_tidy_for_novel`）。
# [EN] **Inline** metadata markers (not line prefixes, so `_DROP_IN_NOVEL` can't catch them):
# [EN]   `〔aside·甲〕` -- the model wrote "this is A's inner voice" into the prose
# [EN]   `〔dialogue·甲 → 乙〕`, `{aside·丙}` (half-width braces)
# [EN] Measured **132 occurrences** in one day (`〔aside·` 128 + `〔dialogue·` 12). Leaving them in makes
# [EN] it read like a file format rather than a novel -- the user wants a finished draft.
# [EN] ⚠ **Only strip these words when they carry `·`**: `〔切至 …〕` / `〔切回〕` / `〔同时〕` /
# [EN]   `〔事件 · …〕` are **transitions**, the vehicle for "different people doing different things at
# [EN]   the same moment", and must be kept (see `_tidy_for_novel`).
_DROP_INLINE_RE = re.compile(
    r'[〔{]\s*(?:aside|dialogue|recall|action|narration|note|inner)'
    r'(?:\s*·[^〕}\n]{0,80})?[〕}]', re.I)


def _tidy_for_novel(body: str) -> str:
    """把一天的正文剃成「最终改写稿」：只去过程痕迹，不动任何叙事文本。

    特意**不删**转场标记（`〔切至 …〕`/`〔切回〕`/`〔同时〕`）——
    它们是「同一时刻不同人在做不同事」的表达载体，正是要留下的东西。
    
        English:
    Trim a day's body into a "readable draft": remove only process traces, don't touch any narrative
    text.
        they're the expression vehicle for "different people doing different things at the same moment", exactly what we want to keep.
    """
    kept: list[str] = []
    for ln in body.splitlines():
        s = ln.strip()
        if s and s.startswith(_DROP_IN_NOVEL):
            continue
        # 行内元标记（`〔aside·丁〕` 之类）就地剃掉。
        # ⚠ 剃完可能剩下一对空括号 / 一个多余的空白，顺手收一下：
        #   不然会出现「甲 →乙：（）我记得」这种残骸。
        # [EN] Strip inline metadata markers (`〔aside·甲〕` etc.) in place.
        # [EN] ⚠ After stripping, a pair of empty brackets / a stray space may remain; tidy that up,
        # [EN] otherwise you get leftovers like "甲 →乙：（）我记得".
        if s and _DROP_INLINE_RE.search(ln):
            ln = _DROP_INLINE_RE.sub('', ln)
            ln = re.sub(r'[（(]\s*[）)]', '', ln)
            ln = re.sub(r'[ \t]{2,}', ' ', ln).rstrip()
            if not ln.strip():
                continue
        kept.append(ln)
    # 剃完会留下一串连续空行，压回最多一个
    # [EN] After stripping, a run of consecutive blank lines remains; collapse back to at most one
    out: list[str] = []
    for ln in kept:
        if not ln.strip() and out and not out[-1].strip():
            continue
        out.append(ln)
    return "\n".join(out).strip()


#: 「领衔前缀」最短字数：台词归一化后与前一句共享 >= 此字数的前缀，视为同一句口头禅。
#: [EN] Minimum length of the "leading prefix": if a line's normalized text shares a prefix of
#: [EN] at least this many chars with a recent line, it's treated as the same catchphrase.
_FOLD_MIN_CORE = 3
#: 滑动窗口：最近多少句台词内算「复读」。跨天也连续（角色的口头禅隔天再念照样折）。
#: [EN] Sliding window: how many recent lines count as "repeat". Spans across days too
#: [EN] (a character's catchphrase repeated the next day is still folded).
_FOLD_RECENT = 30
#: 说话人冒号（全角/半角）—— 删复读时连「名字＋冒号」整段一起删，不留悬空。
#: [EN] Speaker colons (full/half width) -- when folding, delete the whole "name + colon"
#: [EN] attribution so nothing is left dangling.
_FOLD_COLONS = '：:'


def _find_quotes(text: str) -> list[tuple[int, int, str]]:
    """找出正文里所有成对引号区间，支持中文 / 英文引号。

    Returns list of (start, end, quote) where start/end 是含引号的区间。
    [EN] Return all paired-quote spans (Chinese / English), as (start, end, quote)
    with start/end covering the quotes.
    """
    out: list[tuple[int, int, str]] = []
    i, n = 0, len(text)
    pairs = (('“', '”'), ('"', '"'), ('‘', '’'), ("'", "'"))
    while i < n:
        c = text[i]
        pair = None
        for o, cl in pairs:
            if c == o:
                pair = (o, cl)
                break
        if pair is None:
            i += 1
            continue
        j = text.find(pair[1], i + 1)
        if j == -1:
            i += 1
            continue
        out.append((i, j + 1, text[i + 1:j]))
        i = j + 1
    return out


def _fold_repeats(text: str) -> str:
    """折叠装订稿里的「复读机」：同一角色在滑动窗口内反复念同一句（或只换几个字）的
    口头禅 / 口号，只留第一句，其余整句删掉。

    这是**可读性正确性**修复（属"不像人话"的那类），不另设开关 —— 与
    `crew/agents.REPEAT_RULES` / `SCREEN_HARD_RULES` 同一条口径：关掉没有正当理由
    （见 `crew/agents.py` 1525 行附近）。只动**带引号的台词**（prose 里的 `名字："…"`），
    不动旁白 / 动作 / 叙述；`原始稿`（逐字原样）模式不走这里。

    判据：见 `tools/verify_novel_repeat.py`；反例法：见 `developers/mutate_novel_repeat.py`。

        English:
    Fold the "repeat machine" in the bound volume: if the same character repeats the same
    catchphrase (or one with only a few characters changed) within the sliding window, keep only
    the first and delete the rest whole-clause. This is a **readability-correctness** fix
    (the "doesn't sound human" kind), with **no separate switch** -- same calibration as
    `crew/agents.REPEAT_RULES` / `SCREEN_HARD_RULES`: no legitimate reason to turn it off.
    Only touches **quoted dialogue** (the `name: "…"` in prose), not narration / action /
    description; the `原始稿` (verbatim) mode doesn't go through here.
    """
    quotes = _find_quotes(text)
    if not quotes:
        return text
    drop: list[tuple[int, int]] = []
    recent: list[str] = []
    for (s, e, q) in quotes:
        k = _norm_utt(q)
        if not k:
            continue
        if _is_repeat_utt(k, recent):
            drop.append((_drop_start(text, s), e))
        else:
            recent.append(k)
            if len(recent) > _FOLD_RECENT:
                recent.pop(0)
    if not drop:
        return text
    drop.sort()
    merged: list[tuple[int, int]] = []
    for (a, b) in drop:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    out: list[str] = []
    prev = 0
    for (a, b) in merged:
        out.append(text[prev:a])
        prev = b
    out.append(text[prev:])
    res = ''.join(out)
    res = re.sub(r'\n{3,}', '\n\n', res)
    res = re.sub(r'[：:]\s*(?=\n)', '', res)
    res = re.sub(r'\n{2,}(?=##)', '\n\n', res)
    res = re.sub(r'([。！？])\s*(?=[，：])', r'\1', res)  # 清掉悬空标点后的逗号/冒号
    return res.strip()


def _norm_utt(s: str) -> str:
    """归一化一句台词：去空白与标点，只留汉字/字母/数字。"""
    return re.sub(r"""\s，。！？、；：“”‘’""''（）()—…·\.\,\!\?\;\:\*\·\|\/""", '', s)


def _is_repeat_utt(cur: str, recent: list[str]) -> bool:
    """当前台词是否与窗口内某句共享 >= _FOLD_MIN_CORE 字的前缀（领衔口头禅）。"""
    for r in recent:
        k = min(len(r), len(cur))
        for kk in range(_FOLD_MIN_CORE, k + 1):
            if cur.startswith(r[:kk]) or r.startswith(cur[:kk]):
                return True
    return False


def _drop_start(text: str, s: int) -> int:
    """引号在 s 处打开；往回扫，把「说话人＋冒号」整段算进删除起点。"""
    i = s
    while i > 0:
        ch = text[i - 1]
        if ('\u4e00' <= ch <= '\u9fff') or ch.isalnum() or ch in _FOLD_COLONS:
            i -= 1
        elif ch == '，':
            seg = text[i - 1:s]
            # 仅当这是短小的「动词，」归因（如 她顿了顿，）才连逗号一起删；
            # 长铺垫（如「白衣女人望向窗外，院里…渗进来：」）只删逗号之后的部分。
            # [EN] Only when this is a short "verb," attribution (e.g. 她顿了顿，) do we delete
            # [EN] the comma too; for a long lead-in we keep it and only drop what's after the comma.
            if 0 < len(seg) <= 6 and not any(p in seg for p in '。！？：““'):
                i -= 1
            else:
                break
        else:
            break
    return i


def _opening_section(run, mode: str) -> str:
    """装订稿开头那一节「开场」（读 `<运行文件夹>/开场.md`）。

    读**落盘的那一份**，不重算 —— 开场是「那一刻」的扉页；重算会带上现在的
    在场人物与天气，那就不是当时那一屏了。没有这个文件（旧的一轮）就返回空串。

    `novel`（最终改写稿）剃掉「未登场」那行 —— 那是写给作者的体检表，
    不该出现在给读者看的稿子里（§3.6.1 明确要求）。
    
        English:
    The "opening" section at the start of the bound volume (read `<run_folder>/开场.md`).
        Read **the flushed copy**, don't recompute - the opening is the title page of "that moment"; recomputing would bring in the current
        present characters and weather, which wouldn't be that screen from back then. If this file is missing (old run), return an empty string.
        `novel` (readable draft) trims the "not yet appeared" line - that's a health check written for the author,
        and shouldn't appear in the draft shown to readers (§3.6.1 explicitly requires this).
    """
    if run is None:
        return ""
    p = run.root / "开场.md"
    if not p.exists():
        return ""
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError as e:                                        # noqa: BLE001
        _LOG.warning("读开场失败：%r", e)
        return ""
    if mode == MODE_NOVEL:
        txt = "\n".join(ln for ln in txt.splitlines()
                        if not ln.strip().startswith("*未登场："))
    return txt


# ══════════════════════════════════════════════════════════════════
# 分层稿（atelier 的四层产物）—— 导出时优先装订它
# ══════════════════════════════════════════════════════════════════
#: 分层稿的落点（跟成品放在一起，作者一眼能对照）。
ATELIER_DIR = '导出'
ATELIER_MD = '分层稿.md'
ATELIER_JSON = '骨架.json'
ATELIER_LOG = '分层日志.md'
#: 全书反思记录（`write_reflection` 写的）。与分层稿同类：**过程档案**，不是交付物。
# [EN] : The whole-book reflection record. Same category as the atelier draft: a **process archive**,
# [EN] : not a deliverable.
REFLECT_MD = '反思记录.md'

#: 导出目录里的**过程档案**：给作者对照用的，不算交付物，但**必须能点开**。
#: 这张清单由产品与判据**共用一份**，只有这里定义。导出目录里出现没登记的 .md 时
#: `verify_export` 会红 —— 那是在提醒「新产物要么登记、要么删掉」，不是让人放宽判据。
# [EN] : **Process archives** in the export dir: for the author to compare against, not
# [EN] : deliverables, but **they must be clickable**. One list, shared by the product and the
# [EN] : criterion, defined only here. An unregistered .md appearing in the export dir turns
# [EN] : `verify_export` red -- a reminder to register or delete it, not to loosen the criterion.
SIDE_FILES: tuple[str, ...] = (ATELIER_MD, ATELIER_LOG, REFLECT_MD)


def atelier_dir(run) -> Path:
    """分层稿的目录 = `<运行文件夹>/导出/`。"""
    for attr in ('root', 'dir', 'path'):
        v = getattr(run, attr, None)
        if v:
            return Path(v) / ATELIER_DIR
    try:
        days = list_days(run)
        if days:
            return days[0][1].parent.parent / ATELIER_DIR
    except Exception:                                            # noqa: BLE001
        pass
    return Path('.') / ATELIER_DIR


def side_archives(run) -> list[Path]:
    """导出目录里**真实存在**的过程档案（分层稿 / 分层日志 / 反思记录）。

    ★ 为什么要有它（2026-10-21）：这三个文件落在导出目录里，却不在结果列表里 ——
      于是 `verify_export` 那条「落盘的每个 .md 都能在结果里点到」一直红着，
      而根因不是判据太严，是**产品漏了一条**：用户看不见、也点不开自己的反思记录。
      ⇒ 产品侧把它们挂进 `extra_paths`，判据侧按同一份清单核对。
      ⚠ 一份清单两处用，只有一处定义（就是这里）—— 否则产品加了、判据不知道，
        或者判据要求了、产品没加，两边永远对不上。

        English:
    **Actually existing** process archives in the export dir (atelier draft / its log / reflection).
        ★ Why it exists (2026-10-21): these three land in the export dir but never appeared in the
          result list, so "every .md on disk is clickable in the result" stayed red -- and the root
          cause was not a strict criterion but a **missing product line**: the user could neither see
          nor open their own reflection record.
          => The product attaches them to `extra_paths`; the criterion checks the same list.
        ⚠ One list, two consumers, defined only here -- otherwise the product adds and the criterion
          does not know, or the criterion demands and the product does not add.
    """
    try:
        d = atelier_dir(run)
    except Exception:                                            # noqa: BLE001
        return []
    out: list[Path] = []
    for name in SIDE_FILES:
        f = d / name
        try:
            if f.is_file() and f.stat().st_size > 0:
                out.append(f)
        except OSError:
            continue
    return out


def atelier_novel_of(run) -> str:
    """读分层稿正文（没有就返回空串）。

    ★ 为什么**只读文件、不在这里生成**：`render_manuscript` 是同步函数，
      而且会被多处调用（导出、预览、对比）。在这里偷偷跑四个 LLM 阶段
      会让"预览"变成"等五分钟"。生成放在 `compose_by_atelier()`（异步），
      由 `checkup_before_bind` 调一次，这里只负责装订。
    """
    p = atelier_dir(run) / ATELIER_MD
    try:
        if p.exists():
            t = p.read_text(encoding='utf-8').strip()
            return t if len(t) >= 200 else ''
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('分层稿读不出来（退回按日装订）：%r', e)
    return ''


def scene_plate_block(run, day: int) -> list[str]:
    """**这一天的场景图版**：每个场景一张大地图 + 一句描述（用户 2026-10-22 点名）。

    用户原话：「所有地图（小地图和大地图）都需要按照场景保存下来」
    「后续导出小说的时候每个场景都需要插入大地图并带有简单描述」。

    ★ 图是从 `<运行文件夹>/场景地图/` 里取的（`sim/loop._save_scene_plate` 在**每一次
      换场**时存下的一张 SVG）。没有存档就返回空表 —— **不编一张图**。
    ★ 路径写**相对**（`../场景地图/…`）：导出的 md 在 `导出/`，图在它隔壁。
      写绝对路径的话，把整个运行文件夹搬走/发给别人，图就全断了。
    ★ 只读清单、不重算地图：导出**不该再花一次计算**，而且"导出时重算"会让
      图和当时屏幕上那张不一样（读者拿它去对剧情，就会对不上）。

        English:
    **This day's scene plates**: one big map per scene plus a one-line description (user, 2026-10-22).
    ★ The images come from `<run>/场景地图/` (one SVG saved by `sim/loop._save_scene_plate` at **every
      scene change**). With no archive it returns an empty list -- it **never invents a map**.
    ★ Paths are **relative** (`../场景地图/...`): the exported md lives in `导出/` and the images sit
      next to it. Absolute paths break the moment the run folder is moved or sent to someone.
    ★ It only reads the manifest and never recomputes: the export **must not spend another
      computation**, and recomputing would make the picture differ from the one on screen when the
      scene played (a reader comparing it against the plot would find it wrong).
    """
    try:
        from image_gen import scenemap as SM
        rows = SM.plates_of_day(run, day)
    except Exception as e:                                   # noqa: BLE001
        _LOG.warning('场景图版读不出来（这一天不插图）：%r', e)
        return []
    if not rows:
        return []
    out: list[str] = []
    for i, r in enumerate(rows, 1):
        when = str(r.get('时辰') or '').strip()
        place = str(r.get('地点') or '').strip() or '未命名'
        desc = str(r.get('描述') or '').strip()
        src = str(r.get('来源') or '').strip()
        head = ' · '.join(x for x in (f'场景 {i}', when, place) if x)
        out.append(f'**{head}**')
        out.append('')
        out.append(f'![地图 · {place}](../场景地图/{r.get("图") or ""})')
        out.append('')
        line = f'> {desc}' if desc else '> （这一场没有留下场景描写）'
        if src:
            line += f'（取图：{src}）'
        out.append(line)
        out.append('')
    return out


def render_manuscript(run, *, mode: str = MODE_NOVEL,
                      upto_day: int | None = None, version: int = 1,
                      day_bodies: dict[int, str] | None = None) -> dict:
    """生成装订稿的 Markdown（**不落盘**）。

    返回 `{"text","days","chars","skipped","mode"}`。
    `skipped` = 因为 `upto_day` 被截掉的天数，用于把「这是半截稿」说清楚。
    
        English:
    Generate the bound volume's Markdown (**not flushed to disk**).
        Returns `{"text","days","chars","skipped","mode"}`.
        `skipped` = number of days truncated by `upto_day`, used to make clear "this is a partial draft".
    """
    if mode not in _STEM:
        mode = MODE_NOVEL
    days_all = list_days(run)
    days = days_all if upto_day is None else [d for d in days_all if d[0] <= upto_day]
    skipped = len(days_all) - len(days)
    # ★★★ 2026-10-26：先分组再写文件头 —— 头里要如实说"这一本是按什么装的"。
    #   `_layered`（有分层稿）时不走按日/按事件装订，那时不报这个。
    # [EN] ★★★ 2026-10-26: group before writing the header -- it must say honestly what this
    # [EN] volume was bound by. When a layered draft exists neither path applies, so don't claim it.
    _groups = group_days_by_event(days)
    _merged = sum(1 for g in _groups if len(g['days']) > 1)

    title = run.project_dir.name or run.root.name
    label = _STEM[mode]
    header: list[str] = [
        f"# 《{title}》· {label}",
        "",
        f"> 第 {run.root.name} · **装订稿** v{version}",
        f"> 导出时间：{now_str()}",
    ]
    if days:
        header.append(f"> 截至：第 {days[-1][0]} 天（已纳入 {len(days)} 天"
                      + (f"，另 {skipped} 天未纳入" if skipped else "") + "）")
    else:
        header.append("> 尚无任何已落盘的天")
    _src_line = "> 来源：每天的生活/（**按日装订，未经改写**）"
    if _merged:
        # ★ 跨天事件合成了一章 ⇒ 头里要说清"按事件装订"，否则读者会以为漏了一天。
        #   数字是**数出来的**（几件事跨了天），不是估的。
        # [EN] A cross-day event was merged into one chapter, so the header must say "bound by
        # [EN] event" -- otherwise the reader thinks a day is missing. The number is **counted**.
        _src_line = (f"> 来源：每天的生活/（**按事件装订**：{_merged} 件事跨了天，"
                     "已合在同一章里，未经改写）")
    if mode == MODE_NOVEL and atelier_novel_of(run):
        _src_line = ("> 来源：**分层创作**（骨架 → 章纲 → 草稿 → 细节，"
                     "每层过闸后才往下写）")
    header.append(_src_line)

    if mode == MODE_NOVEL:
        header += ["",
                   "**这是素材稿，不是成稿。** 已剃掉过程痕迹（在场名单 / 本幕依据 /",
                   "机制备注 / 图片路径），留下时间、场景、出场退场、旁白、对白、动作、",
                   "心声与同时性——目的是读起来像小说，改写时直接用。"]
    else:
        header += ["",
                   "**这是素材册，不是成稿。** 过程痕迹全部保留（在场名单、本幕依据、",
                   "机制备注、图片路径），方便对照「这句是从哪条设定长出来的」。"]
    header += ["", "---", ""]

    body_parts: list[str] = []
    # ★★★ 2026-10-28（用户：「导出的时候也从前情和之前故事的最后一段加入进来，
    #   以方便后续拼接故事」）：装订稿开头冠**承接上一部**的段 ——
    #   内容 = `前情提要.md`（摄取对齐写的：前情 + 故事停在 + 上部结尾原句）。
    #   为什么两档（最终改写稿 / 素材册）**都**加：既有硬判据
    #   「novel 的正文行必须是 reference 的子集（只删不加）」，只给一档加必红；
    #   而且两档读者都需要知道"这本接着哪一部"。
    #   ⚠ 「原始稿」（write_raw_manuscript）**一个字不动** —— 它是"一字未改"的凭据稿。
    # [EN] ★★★ 2026-10-28 (user: "add the recap and the previous story's last paragraph at export
    # [EN] so successive stories can be stitched"): head the bound draft with a continuation block
    # [EN] sourced from 前情提要.md (written by ingest alignment: recap + where it stopped + the
    # [EN] verbatim tail). **Both** volumes get it (the "novel ⊆ reference" criterion demands the
    # [EN] same code path), while the verbatim raw manuscript stays byte-untouched.
    _prev_story = _previous_story_of(run)
    if _prev_story:
        body_parts += ["## 前情提要 · 承接上一部", "", _prev_story, "", "---", ""]
    chars = 0
    # ★ 每轮开场（§3.6.1）：装订稿的**开头冠这一节**。
    #   `novel` 版剃掉「未登场」与来源标注（那是写给作者的体检表）；
    #   `reference`（素材册）全留 —— 它本来就是"对照着看"的那一本。
    # [EN] ★ Each round's opening (§3.6.1): the bound draft **is headed by this section**.
    # [EN] The `novel` version strips "未登场" and source annotations (that's a health-check sheet written for
    # [EN] the author);
    # [EN] `reference` (the material booklet) keeps everything — it was always the volume meant to be "read
    # [EN] side by side".
    opening_sec = _opening_section(run, mode)
    if opening_sec:
        body_parts.append(opening_sec.strip())
        body_parts.append("")
        body_parts.append("---")
        body_parts.append("")
    # ★★★ 有分层稿（atelier 四层产物）就**装订它**，不再按日拼（2026-10-21）。
    #   为什么优先它：按日拼出来的是"每天的原始稿加细节首尾相接"，没有全书骨架，
    #   于是空转（好几章在问同一件事）在结构上就已经注定 —— 事后再修句子没用。
    #   分层稿是"先总后分、逐层过闸"出来的，结构与推进都验过。
    #   ⚠ 只对 `novel` 那一档生效：素材册要看过程痕迹，原文稿一字不许动。
    #   ⚠ 分层稿读不出来（太短/不存在）就**退回按日装订**，绝不因此导不出书。
    # [EN] If a layered draft exists, bind **it** and skip the per-day assembly. The per-day
    # [EN] output is "yesterday's process draft appended to today's" with no book-level
    # [EN] skeleton, so a stall is structurally predetermined and sentence-level repair
    # [EN] cannot help. Only the readable `novel` volume takes this path.
    _layered = atelier_novel_of(run) if mode == MODE_NOVEL else ''
    if _layered:
        body_parts.append(_layered)
        body_parts.append("")
        _LOG.info('装订：使用分层稿（%d 字），跳过按日拼装', len(_layered))

    for grp in ([] if _layered else _groups):
        # ★★★ 2026-10-26：**章 = 事件，节 = 天**（用户：「注意 一个事件可能跨天」）。
        #
        #   改之前这里是 `for day, path in days:` —— 一天一章。于是同一站演到一半被日界
        #   切断：第 1 天章末在"推门"，第 2 天章首又是另一场，读者看到"两章各半截"。
        #   现在相邻的天如果属于同一个站（`group_days_by_event` 判），**合成一章**：
        #     · 章标题 `## 第 1-2 天 · 入楼收留`（一件事一章）
        #     · 章内每天用一行粗体 `**第 1 天 · 辰时 08:00 → 子时 23:59**` 标出，
        #       正文仍是原生内容（每个字的来源不变）
        #   ⚠ 不跨天时输出**逐字不变**：标题仍是 `## {day_title}`，不加粗体行,
        #     不加章级 `---`（既有 105 条判据里有一大批按旧结构断言，必须逐字兼容）。
        #   ⚠ 两档（最终改写稿 / 素材册）走**同一段**代码 —— 有一条硬判据
        #     「最终改写稿的正文行必须是素材册正文行的子集（只删不加）」，只给一档加就会红。
        #   ⚠ 为什么章内用**粗体行**而不是 `### 第 N 天`：正文里本来就有 `## 时辰` 那个级别的
        #     幕标题，再插一层 `### ` 会让层级从"章 → 幕"变成"章 → 天 → 幕"；
        #     而润色的分块与硬回填都只认 `## `（`_split_chunks` / `polish_manuscript`），
        #     新增一级标题就得同时改那两处 —— 为一行的可读性不值得。
        # [EN] ★★★ 2026-10-26: **a chapter is an event, a bold line is a day**. It used to be
        # [EN] `for day, path in days:` -- one chapter per day -- so an event cut in half by the
        # [EN] day boundary produced "two half chapters". Adjacent days belonging to the same
        # [EN] station now merge into one chapter: title `## 第 1-2 天 · station`, and each day
        # [EN] inside marked by a bold line. ⚠ With no spanning event the output is **byte
        # [EN] identical** to before (same `## {day_title}`, no bold lines, no chapter-level
        # [EN] `---`), which the existing criteria depend on. ⚠ Both volumes run through the
        # [EN] **same** code: a hard criterion asserts the readable draft's body lines are a
        # [EN] subset of the material book's. ⚠ Why a bold line instead of `### 第 N 天`: the
        # [EN] body already has `## 时辰` act headings, and the polish path's chunking and hard
        # [EN] header restore only recognise `## ` -- adding a level means changing both.
        _gdays = grp['days']
        _multi = len(_gdays) > 1
        if _multi:
            _a, _b = _gdays[0][0], _gdays[-1][0]
            _nm = str(grp.get('name') or '').strip()
            body_parts.append(f"## 第 {_a}-{_b} 天" + (f" · {_nm}" if _nm else ""))
            body_parts.append("")
        for day, path in _gdays:
            # ★★★ 读**全量**（`.json` 优先，退回 `.md`）：见 `read_day_full` 的说明。
            # [EN] Read the **full** body (`.json` first, falling back to `.md`) — see `read_day_full`.
            day_title, meta, body = read_day_full(path)
            if not day_title:
                day_title = f"第 {day} 天"
            if mode == MODE_NOVEL:
                meta = ""
                if day_bodies is not None and day in day_bodies:
                    # ★ 2026-10-16（MUMU_FOR_EXPORT）：这一天改走 MuMuAINovel 重写稿。
                    #   已经是干净的小说正文，不再过 `_fold_repeats`（那是给内部整理稿
                    #   去复读机用的，MuMuAINovel 出稿默认就干净）。
                    # [EN] 2026-10-16 (MUMU_FOR_EXPORT): this day uses the MuMuAINovel rewrite.
                    # [EN] Already clean novel text; skip `_fold_repeats` (that's for the internal
                    # [EN] edited draft's repeat-machine fold; MuMu output is clean by default).
                    body = day_bodies[day]
                else:
                    body = _tidy_for_novel(body)
                    # ★★ **优先用「当天故事」那份整理稿**（2026-10-07）。
                    # [EN] ★★ **Prefer the "same-day story" edited draft** (2026-10-07). [Output language] All **output
                    # [EN] text** must be written in **Simplified Chinese** — narration, voiceover, dialogue,
                    # [EN] documentation, summaries, and suggestions all count, **even if the source material is in another
                    # [EN] language**. Proper nouns such as personal names, place names, and book titles **keep their
                    # [EN] original spelling**; do not transliterate or translate them. **Key names in JSON stay as-is**
                    # [EN] (e.g. "动作", "台词"); only write the **values** in Chinese.
                    #
                    # 用户：「每天总结你看下包含当天故事整理吗(整理成小说形式)
                    # 手动导出也要看下是否包含导出小说形式内容 没有这两个地方都加上」。
                    # [EN] User: "For the daily summary, check whether it includes the day's story organized (organized
                    # [EN] into novel form)
                    # [EN] Also check for manual export whether it includes novel-form export content; if neither place has
                    # [EN] these, add both".
                    #
                    # `当天故事.md` 是收工时由**小说作家**把这一天实际发生的
                    # 写成小说形式的那一份（`sim/loop._day_novel`）——它比"把剧本
                    # 剃掉痕迹"更接近小说：句子本来就是按小说写的，不是从场记体改的。
                    # 有它就用它，没有就退回原来那条路（老运行文件夹里没有这个文件）。
                    # [EN] `当天故事.md` is the version written in novel form by the **novelist** at wrap-up,
                    # [EN] covering what actually happened that day (`sim/loop._day_novel`) — it's closer to a novel than
                    # [EN] "stripping the traces
                    # [EN] off the script": the sentences were written as a novel to begin with, not converted from a
                    # [EN] scene-log style.
                    # [EN] If it exists, use it; otherwise fall back to the original path (old run folders don't have this
                    # [EN] file).
                    #
                    # ⚠ `参考`（素材册）**不走这条路**：那一本要的是"这句从哪条设定
                    #   长出来"的对照，把成稿塞进去反而丢了对不上的过程痕迹。
                    # [EN] ⚠ `参考` (the material booklet) **does not take this path**: that volume wants the cross-reference
                    # [EN] of "which setting this sentence
                    # [EN] grew out of"; stuffing the finished draft in instead loses the process traces of mismatches.
                    # ★★ **整理稿要有"够长"才采用**（2026-10-17 修）。
                    #   以前是 `if better: body = better` —— 只要 `当天故事.md` 里有这一天
                    #   那一段，就**整份替换**掉可读材料。而那份整理稿在 2026-10-17 之前
                    #   是被 `raw[:6000]` + `2600 token` 做残的：一天 43,648 字的最终改写稿
                    #   被 **917 字**覆盖 ⇒ 导出的《最终改写稿》只有 1,185 字。
                    #   用户原话：「为何发生给你了很多事情 最后导出的内容非常少？
                    #   剧情部分呢？人物对话呢？导出的应该是一个经过润色的完整的小说才对」。
                    #
                    #   ⇒ 现在要求整理稿**至少是可读材料的 `_NOVEL_MIN_RATIO`**（默认 15%）
                    #     才用它。够不着就**保留可读材料**（带 `· 动作`/`◇ 心声` 标记，
                    #     但内容是完整的），并在文件头如实说"这一天用的是素材稿"。
                    #   ⚠ 15% 这个数不是拍的：流水账整理成小说正常是**压缩 4-5 倍**
                    #     （实测 4.4 万字 → 1 万字 ≈ 23%）；只有"整理残了"才会掉到 2%。
                    #     两边都留了余量。
                    # [EN] ★★ **Only adopt the organized draft when it is "long enough"** (fixed
                    # [EN] 2026-10-17).
                    # [EN] It used to be `if better: body = better` -- whenever `当天故事.md` had a section
                    # [EN] for that day it **replaced the whole** readable material. And before 2026-10-17
                    # [EN] that organized draft was crippled by `raw[:6000]` + `2600 token`: a day's 43,648
                    # [EN] characters of readable text were overwritten by **917 characters** => the
                    # [EN] exported "最终改写稿" was only 1,185 characters.
                    # [EN] The user's exact words: "why is the exported content so little? Where is the
                    # [EN] plot? Where is the dialogue? The export should be a polished, complete novel."
                    # [EN] => Now the organized draft must be at least `_NOVEL_MIN_RATIO` (default 15%) of
                    # [EN] the readable material to be used. Otherwise **keep the readable material** (it
                    # [EN] carries `· 动作`/`◇ 心声` markers but the content is complete) and state honestly
                    # [EN] in the header that this day uses the material draft.
                    # [EN] ⚠ The 15% is not arbitrary: a scene log condensing into prose normally compresses
                    # [EN] 4-5x (measured 44k -> 10k ≈ 23%); only a "crippled" organizing run drops to 2%.
                    # [EN] Margin on both sides.
                    better = _day_novel_of(run, day)
                    if better and len(better) >= max(1, int(len(body) * _NOVEL_MIN_RATIO)):
                        body = better
                    elif better:
                        # 整理稿太短：留材料，并在正文前说清楚为什么（不静默降级）。
                        # [EN] The organized draft is too short: keep the material and explain why before
                        # [EN] the body (no silent downgrade).
                        _LOG.info(
                            '第 %d 天：整理稿只有 %d 字（材料 %d 字，不足 %d%%）'
                            '—— 这一天改用素材稿，避免把内容丢掉',
                            day, len(better), len(body), int(_NOVEL_MIN_RATIO * 100))
                        body = (f'> ⚠ 这一天的整理稿只有 {len(better)} 字，'
                                f'明显少于当天的材料（{len(body)} 字）——'
                                f'为防止内容丢失，这里改用**素材稿**（带 `· 动作` / `◇ 心声` 标记，'
                                f'但内容是完整的）。\n\n') + body
                    # ★ 2026-10-16（用户：「生成的小说不像人话」）：折叠同一角色在一天内
                    #   反复念同一句口头禅的「复读机」。这条只动 MODE_NOVEL（最终改写稿），
                    #   `原始稿`（逐字原样）不受影响。详见 `_fold_repeats` 与
                    #   `tools/verify_novel_repeat.py`。
                    # [EN] 2026-10-16 (user: "the generated novel doesn't sound human"): fold the
                    # [EN] "repeat machine" where one character keeps repeating the same catchphrase in a day.
                    # [EN] Only affects MODE_NOVEL (readable draft); `原始稿` (verbatim) is untouched.
                    body = _fold_repeats(body)
            # ★ 2026-10-26：跨天事件**章内不再标题**，只加一行粗体标出"这是第几天"。
            #   不跨天时仍是原来的 `## {day_title}` —— 逐字不变。
            # [EN] 2026-10-26: inside a multi-day chapter the day is a **bold line**, not a
            # [EN] heading. Single-day chapters keep the original `## {day_title}`, byte for byte.
            if _multi:
                body_parts.append(f"**{day_title}**")
            else:
                body_parts.append(f"## {day_title}")
            body_parts.append("")
            # ★★★ 2026-10-22：**每章开头先给这一天的场景图版**（每个场景一张大地图 + 一句描述）。
            #   ⚠ 两档（最终改写稿 / 素材册）**必须加同一段**：`verify_export` 有一条硬判据
            #     「最终改写稿的正文行必须是素材册正文行的子集（只删不加）」——
            #     只给最终改写稿加图，那条判据当场红，而它红得**对**（确实多加了行）。
            # [EN] ★★★ 2026-10-22: **each chapter opens with that day's scene plates** (one big map plus a
            # [EN] one-line description per scene). ⚠ The **same block must go into both modes**: a hard
            # [EN] criterion asserts "the readable draft's body lines are a subset of the material book's
            # [EN] (delete only, never add)" -- adding images to only one mode turns it red, and rightly so.
            _plates = scene_plate_block(run, day)
            if _plates:
                body_parts.extend(_plates)
            if meta:
                body_parts.append(f"> ※ {meta.replace('  ', ' ｜ ').strip()}")
                body_parts.append("")
            body_parts.append(body or "（这一天没有落盘正文。）")
            body_parts.append("")
            # ★ 2026-10-26：`---` 是**章**的分隔，不是天的 —— 跨天事件的章内不能断开，
            #   否则读者看到的两半截又多了一道横线，等于把刚合起来的东西又切开。
            # [EN] `---` separates **chapters**, not days: a multi-day chapter must not be split
            # [EN] inside, or the reader sees the very seam the merge was meant to remove.
            if not _multi:
                body_parts.append("---")
                body_parts.append("")
            chars += len(re.sub(r"\s", "", body))
        if _multi:
            body_parts.append("---")
            body_parts.append("")

    text = "\n".join(header + body_parts).rstrip() + "\n"

    # ══════════════════════════════════════════════════════════════
    # 末尾附**质量指标页**（2026-10-20，用户要求）
    # ══════════════════════════════════════════════════════════════
    # ★ 为什么放末尾不放文件头：文件头是"读者进门的门厅"，一上来先看一堆
    #   百分比和阈值，读小说的兴致就没了。末尾是"放下书之后翻到的附录"，
    #   这时候人已经在想"这一稿哪里不对"，正是需要数字的时候。
    # ★ **只加在 `novel`（最终改写稿）那一档**：
    #   `参考`（素材册）本来就要看过程痕迹，塞一份质量表会把对照关系弄乱；
    #   `原文`（逐字凭据稿）一个字符都不许动 —— 它存在的全部价值就是原样。
    # ★ 生成失败一律**不影响导出**：宁可没有附录，不许把稿子搞没。
    # [EN] Append the quality sheet at the **end**, and only for the readable `novel`
    # [EN] volume: the material booklet needs its process traces intact, and the
    # [EN] verbatim draft must stay byte-identical. Any failure here is swallowed --
    # [EN] no appendix is better than a lost manuscript.
    if mode == MODE_NOVEL:
        try:
            from export import quality_page as _QP
            # ⚠ 量的是**正文**（`body_parts`），不是整份 `text` ——
            #   后者含着文件头的元信息（书名、导出时间、"这是素材稿"说明），
            #   把它们算进句长/逗号密度会让指标偏移。
            _page = _QP.render("\n".join(body_parts))
            if _page.strip():
                text = text.rstrip() + "\n\n" + _page
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('质量指标页生成失败（稿子照常导出）：%r', e)

    # ★ 正文与"整份文件"分开返回（2026-10-21）。
    #   为什么要分：末尾那份**质量指标附录**是给作者看的、文末自己也写着"可以直接删掉"，
    #   它**不是正文**。以前返回值只有 `text`（正文+附录），于是
    #   `verify_export` 那条"最终改写稿必须是素材册正文的子集（只删不加）"必然误报 ——
    #   附录多出 42 行、还让最终改写稿比素材册长（112 行 vs 84 行）。
    #   ⚠ 正确的修法**不是**让判据去剥字符串（那是让判据将就实现），
    #     而是让实现把两样东西分开交出来：`body` = 正文，`text` = 落盘那份（正文+附录）。
    #   ⚠ `chars` 一直是按正文累加的，与 `body` 同口径；附录不参与任何指标。
    # [EN] ★ Body text and "the whole file" are returned separately (2026-10-21).
    # [EN] Why: the quality-metrics appendix at the end is for the author and says so itself
    # [EN] ("can be deleted, does not affect the work") -- it is **not body text**. The return value
    # [EN] used to be only `text` (body + appendix), so the `verify_export` criterion "the readable
    # [EN] draft must be a subset of the material book's body (delete only, never add)" was bound to
    # [EN] misfire: the appendix added 42 lines and made the draft longer than the book (112 vs 84).
    # [EN] ⚠ The right fix is **not** to make the criterion strip strings (that bends the criterion to
    # [EN] fit the implementation) but to have the implementation hand over two things separately:
    # [EN] `body` = body text, `text` = the file on disk (body + appendix).
    # [EN] ⚠ `chars` has always accumulated over body parts, so it shares `body`'s basis; the appendix
    # [EN] contributes to no metric.
    return {"text": text, "body": "\n".join(body_parts).rstrip(),
            "days": len(days), "chars": chars,
            "skipped": skipped, "mode": mode,
            # ★ 天号列表（不只是"几天"）：`_flush_manuscript` 要把范围写进文件名
            #   （`最终改写稿_v1_第1-2天.md`）。只给数量的话，文件名只能说"2 天"，
            #   说不出是**第 3-4 天**还是第 1-2 天 —— 而中断续跑时那恰恰是要紧信息。
            # [EN] ★ The list of day numbers (not just "how many"): `_flush_manuscript` writes the
            # [EN] range into the filename (`最终改写稿_v1_第1-2天.md`). With only a count the name
            # [EN] could say "2 days" but not **which** two -- and after a resume that is exactly
            # [EN] the information that matters.
            "day_numbers": [int(d) for d, _ in days]}


#: 「当天故事」那份整理稿的**唯一文件名**（与 `crew/studio.FILE_DAY_NOVEL` 一致）。
#: ⚠ 这边**不 import 剧组**：导出这一层不该把 `crew/` 拖进来（那是推演侧的事）。
#:   名字写死一处、两边各有一份常量，靠判据
#:   （`tools/verify_crew_stage.py` 的 E 组）钉住它们一致。
# [EN] : The **sole filename** of the "当天故事" edited draft (consistent with
# [EN] `crew/studio.FILE_DAY_NOVEL`).
# [EN] : ⚠ This side **does not import the crew**: the export layer shouldn't drag `crew/` in (that's
# [EN] the simulation side's concern).
# [EN] :   Hardcode the name in one place; each side has its own constant; rely on the check
# [EN] :   (`tools/verify_crew_stage.py` group E) to pin them as consistent.
_DAY_NOVEL_NAME = '当天故事.md'

#: 整理稿**至少**是可读材料的多少比例才采用（见 `render_manuscript` 里的长注释）。
#: 够不着就保留可读材料 —— "宁可给素材，也不能把 4 万字换成 900 字"。
# [EN] The organized draft must be at least this fraction of the readable material to be adopted (see
# [EN] the long note in `render_manuscript`). Below that, keep the readable material -- "better to hand
# [EN] over the raw material than to swap 40k characters for 900".
_NOVEL_MIN_RATIO = 0.15

#: 「当天整理稿」被当成成稿采用的**绝对下限**（字）。低于它就当没有 ——
#: 一份 800 字的"整理稿"不可能覆盖一整天的戏，那是整理残了，不是写得简洁。
#: ⚠ 与 `_NOVEL_MIN_RATIO` 是**两道**闸：比例防"相对太短"，绝对值防"两边都短"
#:   （材料只剩 900 字时，15% 只有 135 字，任何碎片都能过）。
# [EN] Absolute floor (chars) for adopting the day's organized draft. Below it, treat as absent: an
# [EN] 800-char "organized draft" cannot cover a whole day. Two gates together with the ratio, which
# [EN] alone degenerates when the material itself is tiny.
_ORGANIZED_MIN_CHARS = 1200

#: 喂给 MuMuAINovel 的单次正文上限（字）。它的 `MUMU_TARGET_WORDS` 默认 2500，
#: 即一次调用只产出一章 2500 字；输入远超它只会被压缩，白花钱还丢内容。
#: 实测某一章 17~207 秒，所以这里**不做分块循环**（21 万字要 80+ 次调用、数小时），
#: 超过就截断并**记进 `degrades`**（不静默降级）。
# [EN] Per-call input cap (chars) for MuMuAINovel. Its `MUMU_TARGET_WORDS` defaults to 2500, i.e.
# [EN] one call yields one 2500-char chapter; a much longer input just gets squeezed. No chunk loop
# [EN] here (213k chars would need 80+ calls / hours), so it truncates and **records** it.
_MUMU_INPUT_MAX = 6000


def _mumu_input(body: str) -> str:
    """把一天的全量正文裁成 MuMu 单次能吃的大小，**在段落边界**裁。

    ⚠ 截断处留一句显式标记：读者/作者必须知道"这一天只喂了开头"，
      不能让一份被截断的输入看起来像完整输入。
    [EN] Trim a day's full body to what MuMu can take in one call, cutting at a paragraph boundary,
    [EN] with an explicit marker so a truncated input never looks like a complete one.
    """
    s = str(body or '')
    if len(s) <= _MUMU_INPUT_MAX:
        return s or "（这一天没有落盘正文）"
    cut = s[:_MUMU_INPUT_MAX]
    # 尽量在段落/句子边界断开，别把一句话劈成两半
    for sep in ('\n\n', '\n', '。'):
        i = cut.rfind(sep)
        if i > _MUMU_INPUT_MAX // 2:
            cut = cut[:i + len(sep)]
            break
    return cut.rstrip() + (
        f"\n\n（⚠ 输入被截断：这一天共 {len(s)} 字，这里只给了前 {len(cut)} 字。"
        f"整份正文在导出成品的「原始稿」里。）")


def _settings_dir_of(run):
    """项目设定集目录：`本地设定集/` 优先，其次项目根本身；都没有 → None。

    ★ 为什么单独抽出来（"同一件事两处实现"是万恶之源）：
      `_setting_brief`（MuMu 重写的输入）与 `_previous_story_of`（装订稿的
      承接段）都要定位同一个目录 —— 各写一份迟早有一处忘了跟着改。
    [EN] Locate the project's settings dir (`本地设定集/` preferred, else the project root);
    [EN] None when neither exists. Factored out so the MuMu brief and the bound draft's
    [EN] continuation block cannot drift apart.
    """
    try:
        root = Path(str(getattr(run, 'project_dir', None) or run.root))
    except Exception:                                            # noqa: BLE001
        return None
    cand = [root / '本地设定集', root]
    return next((p for p in cand if p.is_dir()), None)


def _previous_story_of(run) -> str:
    """**上一部的前情 + 结尾**（装订稿开头的承接段；没有就空串）。

    ★ 2026-10-28（用户：「导出的时候也从前情和之前故事的最后一段加入进来，
      以方便后续拼接故事」）：多次推演的产物要能首尾相接 ——
      下一轮开卷导入的是**上一轮的导出稿**，而导出稿开头带上"前情提要 +
      上一部结尾"，下一轮的对齐就既有提要又有停笔处，链才续得上。
    ⚠ 事实来源**只有** `前情提要.md`（摄取对齐写的，见 `ingest.pipeline._freeze`）；
      读不到就空 —— 老项目 / 首部作品没有上一部，**一个字都不编**。
    [EN] **Previous story's recap + ending** (the continuation block at the head of a bound
    [EN] draft; empty when absent). ★ 2026-10-28 (user: "add the recap and the previous story's
    [EN] last paragraph at export, so successive stories can be stitched"): the next round
    [EN] ingests **this export**, so carrying recap + where it stopped keeps the chain unbroken.
    [EN] Single source of truth: 前情提要.md; empty when missing -- never invent.
    """
    sd = _settings_dir_of(run)
    if sd is None:
        return ''
    p = sd / '前情提要.md'
    try:
        return p.read_text(encoding='utf-8', errors='ignore').strip()
    except Exception:                                            # noqa: BLE001
        return ''


def _setting_brief(run, cap: int = 2200) -> str:
    """**设定集摘要**：这本书是什么、有谁、守什么规矩（导出时的第一份材料）。

    ★★★ 2026-10-21（用户点名的导出输入）：导出阶段的材料是
      「**设定集 + 历史小说 + 本地推演过程**」三样。在此之前导出只给了后两样 ——
      外部服务不知道柳氏是谁、这楼是什么地方，只能照台本的字面意思编，
      写出来的人容易"性格漂移"。

    取法：项目目录下的设定集目录（`本地设定集/` 优先，其次项目根本身）
    → 复用 `sim/setup.load_settings`（**一处实现，别在这里再写一份解析**）
    → 拼成"人 + 世界 + 规矩"三段。读不到就返回空串（**不编**）。
    ★ 2026-10-28：补一段【前情提要】—— 接续导入故事推演的项目，
      MuMu 重写也必须知道"故事停在哪"，否则重写稿照样从大纲开头讲起
      （用户实测：「故事情节没从之前的故事开始」）。
    
        English:
    **Setting brief**: what this book is, who is in it, what rules it obeys (the first material at
    export).
        ★★★ 2026-10-21 (the export inputs the user named): export uses
          "**setting book + history novel + local derivation process**". Before this, export only
          provided the last two -- the external service did not know who Liu is or what this
          building is, so it could only improvise from the literal transcript, and characters drifted.
        How: the setting directory under the project (prefer `本地设定集/`, else the project root) ->
        reuse `sim/setup.load_settings` (**one implementation; do not write a second parser here**)
        -> assemble "people + world + rules". Returns an empty string when unreadable (**no
        inventing**).
        ★ 2026-10-28: adds a 【前情提要】 bit -- for projects continuing an imported story, the MuMu
        rewrite must also know "where the story stopped", or it retells from the outline head.
    """
    settings_dir = _settings_dir_of(run)
    if settings_dir is None:
        return ''
    try:
        from sim.setup import load_settings
        st = load_settings(settings_dir) or {}
    except Exception as e:                                       # noqa: BLE001
        _LOG.debug('读设定集失败（导出照旧，只是少了这一段）：%r', e)
        return ''
    bits: list[str] = []
    # ★ 2026-10-28：前情提要排第一 —— MuMu 重写先知道"故事停在哪"。
    # [EN] ★ 2026-10-28: the recap bit goes first -- the rewrite learns where the story stopped.
    _recap = str(st.get('recap') or '').strip()
    if _recap:
        bits.append('【前情提要】\n' + _recap[:900])
    people = st.get('people') or []
    if people:
        rows = []
        for p in people[:14]:
            if not isinstance(p, dict):
                continue
            name = str(p.get('姓名') or p.get('名字') or '').strip()
            if not name:
                continue
            tail = '；'.join(str(p.get(k) or '').strip()
                            for k in ('身份', '性格', '目标') if str(p.get(k) or '').strip())
            rows.append(f'- {name}' + (f'：{tail}' if tail else ''))
        if rows:
            bits.append('【人物】\n' + '\n'.join(rows))
    world = str(st.get('worldview') or '').strip()
    if world:
        bits.append('【世界】\n' + world[:900])
    rules = str(st.get('rules') or '').strip()
    if rules:
        bits.append('【这本书的规矩】\n' + rules[:600])
    style = st.get('style_card') or {}
    if isinstance(style, dict) and style:
        s = '；'.join(f'{k}：{v}' for k, v in list(style.items())[:6]
                      if str(v or '').strip())
        if s:
            bits.append('【写法】\n' + s[:300])
    return '\n\n'.join(bits).strip()[:cap]


def _day_novel_of(run, day: int) -> str:
    """从 `当天故事.md` 里取**第 N 天**那一节（没有就返回空串）。

    文件长这样（`sim/loop._day_novel` 写的）::

        # 当天故事

        > …（给作者看的说明）

        ## 第 3 天 · 第3天·辰时

        这一天的戏收在灯上。……

    ⚠ 切的是 `## 第 N 天` 到**下一个** `## 第 ` 之间 —— 用"找到下一个天号"
      比"按空行切"可靠（整理稿里本来就有空行分段）。
    
        English:
    Extract the **Day N** section from `当天故事.md` (return an empty string if absent).
        The file looks like this (written by `sim/loop._day_novel`)::
            > ... (notes for the author)
            ## Day 3 · Day 3 · Chen hour
            This day's drama ends on the lamp. ...
        ⚠ The cut is between `## Day N` and the **next** `## Day ` -- using "find the next day header"
          is more reliable than "split by blank lines" (the edited draft already has blank-line paragraphs).
    """
    p = Path(run.root) / _DAY_NOVEL_NAME
    try:
        if not p.is_file():
            return ''
        text = p.read_text(encoding='utf-8', errors='replace')
    except Exception:                                            # noqa: BLE001
        return ''
    marks = list(re.finditer(r'^##\s+第\s*(\d+)\s*天', text, re.M))
    for i, m in enumerate(marks):
        if int(m.group(1)) != int(day):
            continue
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.end():end]
        # 去掉紧跟着的"· 时辰"那半截行尾与首尾空行
        # [EN] Remove the trailing half-line "· 时辰" that immediately follows, along with leading/trailing blank
        # [EN] lines
        body = body.split('\n', 1)[1] if '\n' in body else ''
        return body.strip()
    return ''


def _span(numbers: list[int] | tuple[int, ...]) -> str:
    """把天号列表变成文件名后缀：`_第2天` / `_第1-3天` / `_第1,3天`（空 → 空串）。

    ★ 为什么天数要进文件名（2026-10-25 用户：*"名字太长了""看不出来具体是怎么回事"*）：
      原来叫 `最终改写稿_v1.md`、`最终改写稿_v2.md`，**光看名字分不出哪个更全** ——
      得打开两个文件左右比对半天。天数写进名字之后，文件名排序就是
      "这份稿子写到第几天"，一眼看得出 v2 是在 v1 之后又跑了一天。
      同一份稿重导一次天数不变、只有版本号变大，这区分也就自然成立了。

    ★★★ `_vN` 必须留在**最前面**，天数只能追加在它**后面**。
      `next_version()` 靠 `glob(f'{stem}_v*.md')` + `re.search(r'_v(\\d+)')` 找最大编号；
      写成 `最终改写稿_第1-2天_v2.md` 这种（编号挪到中间）**glob 匹配不上** ⇒
      下次导出又从 v1 开始，于是出现两份 v1、同名不同内容，而症状完全看不出跟文件名有关。
      实测两种写法：`最终改写稿_v1_第1天.md` ✅ 抽出 1；`最终改写稿_第1天_v1.md` ❌ 抽不出。
    
        English:
    Turn a list of day numbers into a filename suffix: `_第2天` / `_第1-3天` / `_第1,3天`
    (empty -> empty string).
        ★ Why the day range belongs in the filename (user, 2026-10-25: "the names are too long"
          / "can't tell what's actually in them"): they used to be `最终改写稿_v1.md` /
          `最终改写稿_v2.md`, so **you could not tell which was more complete without opening both
          and diffing by eye**. With the day count in the name, sorting by filename means "how many
          days this draft covers", and you can see at a glance that v2 ran one more day than v1.
          Re-exporting the same draft keeps the same day range and only bumps the version, which
          keeps the two axes distinct.
        ★★★ `_vN` must stay **first**; the day range may only be appended **after** it.
          `next_version()` finds the highest index via `glob(f'{stem}_v*.md')` +
          `re.search(r'_v(\\d+)')`; putting the index in the middle (`最终改写稿_第1-2天_v2.md`)
          **fails the glob** => the next export restarts at v1, producing two v1 files with
          different content and no visible connection to the filename.
          Measured: `最终改写稿_v1_第1天.md` OK (index 1), `最终改写稿_第1天_v1.md` FAILS.
    """
    ns = sorted({int(n) for n in (numbers or ())})
    if not ns:
        return ''
    if len(ns) == 1:
        return f'_第{ns[0]}天'
    if ns == list(range(ns[0], ns[-1] + 1)):
        return f'_第{ns[0]}-{ns[-1]}天'
    return '_第' + ','.join(str(n) for n in ns) + '天'


def next_version(run, mode: str = MODE_NOVEL) -> int:
    """下一个版本号（**版本自增不覆盖**，跟故事文档一个规矩）。
        English:
    Next version number (**versions auto-increment without overwriting**, same rule as the story
    documents).
    """
    d = run.export_dir
    stem = _STEM.get(mode, _STEM[MODE_NOVEL])
    v = 1
    if d.exists():
        for p in d.glob(f"{stem}_v*.md"):
            m = re.search(r"_v(\d+)", p.name)
            if m:
                v = max(v, int(m.group(1)) + 1)
    return v


def write_raw_manuscript(run, *, upto_day: int | None = None) -> dict:
    """导出**原始稿**：把 `每天的生活/第NNN天.md` **逐字原样**装订成册。

    返回 `{"path","version","days","chars","skipped","mode"}`（与 `write_manuscript` 同形）。

    ★ 与另外两种装订稿的区别，一句话：**这一份不经过任何解析与渲染**。
      所以就算以后落盘格式改了、`_tidy_for_novel` 改了，这一份仍然是
      当初那几天的**原文**（这也是它能当凭据的原因）。
    ★ 只加一个文件头（书名/时间/截至），正文**一个字不动** ——
      连"天与天之间"都只是原样拼，不插分隔线（分隔线也是"改"）。
    
        English:
        Returns `{"path","version","days","chars","skipped","mode"}` (same shape as `write_manuscript`).
        ★ The difference from the other two bound drafts, in one sentence: **this copy goes through no parsing or rendering at all**.
          So even if the on-disk format changes later, or `_tidy_for_novel` changes, this copy is still
          the **raw text** of those days back then (which is also why it can serve as evidence).
        ★ Only a file header is added (title/time/up to), the body **not a single character is touched** --
          even "between days" it is just concatenated as-is, with no separator inserted (a separator would also be a "change").
    """
    ensure_dir(run.export_dir)
    # ★★★ 2026-10-26：源改成**每天的全量正文**（`.json` 优先），不再优先 `每天的生活/原文/`。
    #
    #   为什么必须换（这是"原始稿和最终成稿完全不是一个故事"的第一半原因）：
    #     `原文/第NNN天.md` 是 `flush_day_story` 在**开演前**写下的**样章**
    #     （`ds.story`，代码注释原话「样章一写好就落一份原文」）。
    #     剧本模式下一天演 133 幕，而那份样章只有 **1525 字** —— 它是一天的
    #     **开场引导段**，不是这一天。
    #   ⇒ 拿它当"原始稿"，等于把**开演前那段引子**冒充成"这一天的全部原文"。
    #     用户看到的必然"跟成稿完全不是一个故事"：一份是开场，一份是深夜。
    #
    #   现在的口径：**原始稿 = 这一天真实演出的全部正文**，逐字不改（只做渲染，
    #   不剃痕迹、不润色、不合并）。`原文/` 那份样章仍在盘上、仍可在
    #   `原始稿加细节` 里查到，但**不再冒充"原始稿"**。
    # [EN] ★★★ 2026-10-26: source changed to **each day's full body** (`.json` first); no longer
    # [EN] prefers `每天的生活/原文/`. That folder holds `flush_day_story`'s **opening sample**
    # [EN] written before the day starts ("as soon as the sample is written, save a copy"), only
    # [EN] **1525 chars** for a day that ran 133 acts -- an intro, not the day.
    # [EN] New rule: **原始稿 = everything actually performed that day**, verbatim (rendered only:
    # [EN] no trace stripping, no polishing, no merging). The sample stays on disk but no longer
    # [EN] masquerades as the raw draft.
    src = list_days(run)
    days_all = src
    days = days_all if upto_day is None else [d for d in days_all if d[0] <= upto_day]
    skipped = len(days_all) - len(days)
    title = run.project_dir.name or run.root.name
    header = [
        # ⚠ 标题里的档名**必须走 `_STEM`**，不许再硬编码"原始稿"一遍 ——
        #   档名一改，这里就跟着漂（"同一件事两处实现"是万恶之源）。
        # [EN] The kind name in the title **must come from `_STEM`**, never hardcoded again --
        # [EN] otherwise it drifts the moment the name changes.
        f"# 《{title}》· {_STEM[MODE_RAW]}",
        "",
        f"> 第 {run.root.name} · **原始稿**（逐字原样，未做任何处理）",
        f"> 导出时间：{now_str()}",
    ]
    if days:
        header.append(f"> 截至：第 {days[-1][0]} 天（已纳入 {len(days)} 天"
                      + (f"，另 {skipped} 天未纳入" if skipped else "") + "）")
    else:
        header.append("> 尚无任何已落盘的天")
    header += ["",
               "**这一份是那一天真实演出的全部正文，不是成稿。**",
               "没有剃过程痕迹、没有润色、没有合并、没有被重写；",
               "只做了一件事：把 `每天的生活/第NNN天.json`（推演的事实来源）"
               "按同一套渲染器铺成文字。",
               "作者回头改写请以它为准 —— 它是**唯一一份没被任何人改写过**的稿子。",
               "", "---", ""]
    parts: list[str] = []
    put: list[int] = []
    chars = 0
    for _day, path in days:
        # ★ 读**全量**（`.json` 优先，退回 `.md`）：见 `read_day_full`。
        #   这里**不**调 `_tidy_for_novel`、不加 `## 第N天` 以外的任何标题 ——
        #   这一档的全部价值就是"没动过"。
        # [EN] Read the **full** body; no `_tidy_for_novel`, no headings beyond the day's own.
        # [EN] This tier's entire value is "untouched".
        day_title, _meta, body_one = read_day_full(path)
        if not day_title:
            day_title = f"第 {_day} 天"
        text = f"## {day_title}\n\n{body_one}".strip() if body_one else ""
        if not text:
            _LOG.warning("第 %s 天没有可导出的正文（跳过）", _day)
            continue
        chars += len(text)
        parts.append(text)
        put.append(int(_day))
    body = "\n\n".join(parts)
    version = next_version(run, MODE_RAW)
    path = run.export_dir / f"{_STEM[MODE_RAW]}_v{version}{_span(put)}.md"
    atomic_write_text(path, "\n".join(header) + body + "\n")
    _LOG.info("%s导出: %s（%d 天 / %d 字）", _STEM[MODE_RAW], path.name, len(parts), chars)
    return {"path": path, "version": version, "days": len(parts),
            "chars": chars, "skipped": skipped, "mode": MODE_RAW}


def _flush_manuscript(run, rendered: dict, mode: str, version: int) -> dict:
    """把 `render_manuscript` 的结果落盘，返回 `{"path","version","days","chars","skipped","mode"}`。
        English:
    Flush the result of `render_manuscript` to disk, return
    `{"path","version","days","chars","skipped","mode"}`.
    """
    ensure_dir(run.export_dir)
    path = run.export_dir / f"{_STEM[rendered['mode']]}_v{version}{_span(rendered.get('day_numbers') or [])}.md"
    atomic_write_text(path, rendered["text"])
    _LOG.info("%s导出: %s（%d 天 / %d 字）",
              _STEM[rendered['mode']], path.name, rendered["days"], rendered["chars"])
    return {"path": path, "version": version,
            **{k: rendered[k] for k in ("days", "chars", "skipped", "mode", "day_numbers")}}


def write_manuscript(run, *, mode: str = MODE_NOVEL,
                     upto_day: int | None = None,
                     day_bodies: dict | None = None) -> dict:
    """落盘装订稿（内部整理稿路径），返回 `{"path","version","days","chars","skipped","mode"}`。

    `day_bodies` 传了就用它当每天的正文（`{天数: 文本}`）—— 导出关口做完
    多轮复查后，把修过的正文从这里透进来，其余日子照常走渲染。
        English:
    Write the bound draft to disk (internal edited-draft path), return
    `{"path","version","days","chars","skipped","mode"}`.
    """
    version = next_version(run, mode)
    rendered = render_manuscript(run, mode=mode, upto_day=upto_day,
                                 version=version, day_bodies=day_bodies)
    return _flush_manuscript(run, rendered, mode, version)


async def compose_by_atelier(run, *, upto_day: int | None = None,
                             chapters: int | None = None,
                             rounds: int = 3, n_best: int = 2) -> dict:
    """**导出时走一遍分层创作**：推演事实 → 骨架 → 章纲 → 草稿 → 细节。

    用户要求：「等到导出的时候也是这个过程：先从推演里抽取总体框架，
    然后按照前面说的这个步骤进行，唯一的区别是所有的细节信息都来自这一次推演。」

    ★ 事实来源**只有这一跑**：`Source.from_run` 只吃 `transcript.jsonl` 的
      `event` / `scene` / `dialogue` 与 `当天故事.md`。它不读别的作品、不读设定库
      之外的东西 —— 这是"所有细节都来自这次推演"的可执行版本（闸还会再验一次：
      变化对象与专名必须在推演里出现过）。
    ★ 返回 `unsolved`（没过闸的问题）**不吞**：写进 `导出/分层日志.md`，
      也进返回值。宁可标出来让作者看，不许假装过了。
    """
    from crew import atelier as AT
    from crew import atelier_run as AR
    # ⚠ 名字**不许**叫 `_ask`：下面要定义一个同名包装函数，会自己调自己
    #   （实测 `TypeError: _ask() got an unexpected keyword argument 'want'`）。
    #   这种遮蔽读代码时几乎看不出来 —— 函数名和它要包装的东西同名。
    # [EN] Do not name this `_ask`: the wrapper below shadows it and then calls itself.
    from llm.replies import ask as _llm_ask

    days_all = list_days(run)
    days = days_all if upto_day is None else [d for d in days_all if d[0] <= upto_day]
    day_text: dict[int, str] = {}
    for day, _path in days:
        t = _day_novel_of(run, day)
        if t:
            day_text[day] = t
    src = AT.Source.from_run(run, days=day_text)
    out_dir = atelier_dir(run)
    out_dir.mkdir(parents=True, exist_ok=True)

    async def _ask(prompt: str, tier: str, purpose: str):
        # 统一走 `llm.replies.ask`（台账唯一汇合点），不另建 httpx。
        r = await _llm_ask('standard', [{'role': 'user', 'content': prompt}],
                           purpose=purpose, want='text', max_tokens=6000)
        # ⚠ `ask(...)` 返回的是 **Reply 对象**，`str(r)` 得到的是
        #   `Reply(value='{...}', meta=..., ok=True)` 这种 repr —— 拿它去
        #   `json.loads` 一定失败（实测：L0 两轮都"没有分章"，其实模型答得很好，
        #   10918 token 的骨架全在 `value` 里）。
        #   ⇒ 取 `.value`；拿不到就当它已经是字符串。
        # [EN] `ask()` returns a **Reply object**; `str(r)` yields its repr, so parsing fails
        # [EN] while the model actually answered fine. Take `.value`.
        return str(getattr(r, 'value', r) or '')

    def _save(layer: str, sk) -> None:
        # 每过一层存一次：中断了可以看出来断在哪层、断在哪一章。
        try:
            AT.dump(sk, out_dir / ATELIER_JSON)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('骨架落盘失败（不影响继续）：%r', e)

    lines: list[str] = []

    def _say(msg: str) -> None:
        lines.append(str(msg))
        _LOG.info(msg)

    _say(f'分层创作开始：事实 {len(src.events)} 件事 / '
         f'{len(src.lines)} 句台词 / {len(src.scenes)} 个场景')
    sk, unsolved = await AR.compose(
        _ask, src,
        chapters=chapters or max(3, min(8, len(src.events) or 3)),
        rounds=rounds, n_best=n_best, save=_save, progress=_say)

    cov = AT.coverage(sk, src)
    _say(f'覆盖：事件 {cov["events_used"]}/{cov["events_total"]}，'
         f'章 {cov["chapters"]}，拍 {cov["beats"]}，'
         f'变化 {cov["unique_all"]} 种，空转对 {cov["stall_pairs"]}')

    # 拼正文：只用**过闸的**那几章；没过闸的章标出来，绝不悄悄混进去。
    parts: list[str] = []
    bad: set[int] = set()
    for x in unsolved:
        m = re.search(r'第 (\d+) 章', x)
        if m:
            bad.add(int(m.group(1)))
    for c in sk.chapters:
        body = (c.final or c.draft or '').strip()
        if not body:
            continue
        parts.append(f'## 第 {c.idx} 章　{c.title}'.rstrip())
        if int(c.idx) in bad:
            # 明确标出"这一章没过闸"，装订稿里也看得见（不静默降级）。
            parts.append('> ⚠ 这一章的层级闸没过（见 `导出/分层日志.md`），'
                         '下面是它能给出的最好一版，尚未定稿。')
        parts.append('')
        parts.append(body)
        parts.append('')
    text = "\n".join(parts).strip()

    try:
        (out_dir / ATELIER_MD).write_text(text + "\n", encoding='utf-8')
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('分层稿落盘失败：%r', e)

    log = ['# 分层创作日志', '',
           f'- 事实来源：本次推演（{len(src.events)} 件事 / '
           f'{len(src.lines)} 句台词）',
           f'- 覆盖：{cov}',
           '']
    if unsolved:
        log += ['## 没过闸的（**没有假装过**）', '']
        log += [f'- {x}' for x in unsolved]
    else:
        log += ['## 四层全部过闸 ✓', '', '每章都交代了"哪一格变了"，'
                '相邻章/相邻拍没有重复的变化，落点都能在正文里引到原句。']
    log += ['', '## 过程', ''] + [f'- {x}' for x in lines]
    try:
        (out_dir / ATELIER_LOG).write_text("\n".join(log) + "\n", encoding='utf-8')
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('分层日志落盘失败：%r', e)

    return {'text': text, 'unsolved': unsolved, 'coverage': cov,
            'chapters': len(sk.chapters), 'skeleton': sk}


async def checkup_before_bind(run, *, upto_day: int | None = None,
                              mode: str = MODE_NOVEL,
                              rounds: int | None = None,
                              on_stage=None) -> dict:
    """**成书前整本复查**（R48 的导出关口）：逐天跑多轮检查，返回修过的正文。

    用户原话：「一开始写小说和最后导出的时候都可以进行几轮的问题检查也修复」。

    `on_stage(text, frac)` —— **细粒度进度回调**（2026-10-28 加，用户：「导出过程的
      进度条希望更细致一些」）。`frac` ∈ [0,1] 是**这一整步**的完成比例，调用方拿它
      去推进那一档的进度条。为什么必须把它打进内部：**这一步是导出里最长的一段**
      （今天实测一次三天的导出，96 秒里有 90 秒在这：5 轮 × 每轮多步、每步一次模型
      调用），而在此之前调用方只能看到"检查开始"和"检查结束" ⇒ 进度条一动不动
      ⇒ 用户的判断是"导出卡死了"。
      回调异常一律吞掉 —— 界面上的问题不许弄挂导出。
    [EN] `on_stage(text, frac)` fine-grained progress callback added 2026-10-28 (user: "make the
    [EN] export progress bar more granular"). This step is the long silent stretch of an export
    (measured: 90 of 96 s), and without it the UI bar cannot move at all.

    ★★★ 为什么导出关口**不是重复劳动**：写小说时每章都查过，但那是**单章视角**。
      跨天才暴露的毛病只有合并后看得见：
        · 同一件东西昨天续、今天续、后天还续（单看每天都够不上阈值）；
        · 同一句问话昨天问、今天还问；
        · 元叙述习惯在第二天又冒出来。
      所以这里对**每一天**再跑一轮 —— 用的是同一套规则（`crew.agents.prose_checkup`），
      不是另写一份实现。
    ⚠ **只改「最终改写稿」那一档**。`原始稿`（`write_raw_manuscript`）是
      "一字未改"的凭据稿，**一个字符都不许动** —— 它存在的全部价值就是原样。
    ⚠ 任何一天查失败都**保留那一天原样**（查不出问题 ≠ 稿子有问题）。
    [EN] Per-day multi-round checkup at bind time. Not redundant with the per-chapter
    [EN] pass: cross-day defects (the same prop refilled every day, the same question
    [EN] asked again tomorrow) are only visible after merging. Only the folded "novel
    [EN] version" is touched; the verbatim manuscript must stay byte-identical.
    """
    def _say(text: str, frac: float) -> None:
        """把这一小步报给调用方（界面用它推进度条）。

        ⚠ `frac` 会被**夹到 [0,1)**：它是"还剩多少"的量度，等于 1 就意味着这一步
          已经结束，而真正结束是由 `checkup_before_bind` 返回来表达的。
          界面那边两条消息都会来，进度只会往前走、不会跳回去。
        [EN] Relay one micro-step. `frac` is clamped to [0,1): reaching 1 would claim the whole
        [EN] step is finished, which the function returning expresses instead.
        """
        if on_stage is None:
            return
        try:
            on_stage(str(text), min(0.99, max(0.0, float(frac))))
        except Exception:                                        # noqa: BLE001
            pass

    _say('准备装订（读 Actor 素材）', 0.01)

    # ══════════════════════════════════════════════════════════════
    # 先走一遍**分层创作**（2026-10-21）：推演 → 骨架 → 章纲 → 草稿 → 细节
    # ══════════════════════════════════════════════════════════════
    # ★ 为什么放在这里：这是"装订之前"唯一的异步关口，而且**只跑一次**。
    #   放在 `render_manuscript` 里会让"预览"变成"等五分钟"（它是同步函数、
    #   多处调用）。
    # ★ 失败一律**退回按日装订**：分层创作是加分项，不许因为它导出失败。
    #   但失败原因要进日志 —— 静默降级是本项目的零容忍项。
    # [EN] Run the layered composition here: the only async pre-bind hook, executed once.
    # [EN] Any failure falls back to per-day assembly -- never block the export -- but the
    # [EN] reason is always logged (silent downgrade is a zero-tolerance item here).
    if mode == MODE_NOVEL and CFG.b('EXPORT_ATELIER'):
        _say('分层创作（搭骨架 / 写章纲）', 0.05)
        try:
            _res = await compose_by_atelier(
                run, upto_day=upto_day, rounds=CFG.i('EXPORT_ATELIER_ROUNDS'))
            _LOG.info('分层创作：%d 章 / %d 字 / 未解决 %d 条',
                      _res.get('chapters') or 0, len(_res.get('text') or ''),
                      len(_res.get('unsolved') or ()))
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('分层创作失败（退回按日装订，稿子照常导出）：%r', e)

    def _say(text: str, frac: float) -> None:
        """把这一小步报给调用方（界面用它推进度条）。

        ⚠ `frac` 会被**夹到 [0,1)**：它是"还剩多少"的量度，等于 1 就意味着这一步
          已经结束，而真正结束是由 `checkup_before_bind` 返回来表达的。
          界面那边两条消息都会来，进度只会往前走、不会跳回去。
        [EN] Relay one micro-step. `frac` is clamped to [0,1): reaching 1 would claim the whole
        [EN] step is finished, which the function returning expresses instead.
        """
        if on_stage is None:
            return
        try:
            on_stage(str(text), min(0.99, max(0.0, float(frac))))
        except Exception:                                        # noqa: BLE001
            pass

    from crew import agents as A          # 懒导入：导出层不拖推演侧（同 `write_manuscript_mumu`）

    days_all = list_days(run)
    days = days_all if upto_day is None else [d for d in days_all if d[0] <= upto_day]
    _n_days = max(1, len(days))
    bodies: dict[int, str] = {}
    checked = changed = 0
    for _di, (day, path) in enumerate(days, 1):
        try:
            # 复查必须看**整份**正文：拿残稿去复查，等于复查了个零头。
            # [EN] The check must see the **whole** body; checking a remnant misses everything.
            _title, _meta, body = read_day_full(path)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('成书复查：第 %d 天读不出来（原样跳过）：%s', day, e)
            continue
        # ★★★ **要检查的是"真正会被装订进最终改写稿的那一份"**（2026-10-20 修的大坑）。
        #   `read_day` 读的是 `每天的生活/第N天.md` —— **剧本呈现层**
        #   （场景标记、动作标注、旁白，是另一种文体）。
        #   而 `render_manuscript` 装订时优先用**当天故事的整理稿**（`_day_novel_of`），
        #   没有才退回剧本 + `_tidy_for_novel`。
        #   原来这里直接用 `body` 检查 ⇒ 两个后果：
        #     ① 在**剧本**上量小说毛病，量出来的东西不是稿子的毛病
        #        （实测 v22：剧本 2 处"重复"、整理稿 0 处 —— 那两个是剧本格式的固有特征）；
        #     ② 更要命的：`day_bodies` 会**完全替换**正文 ⇒ 一旦真的改了，
        #        就会把剧本装订进最终改写稿。没暴露只是因为那些改动全被闸拦下了。
        # [EN] Check **the text that will actually be bound**, not the screenplay.
        # [EN] `read_day` returns the screenplay layer while `render_manuscript` prefers the
        # [EN] edited daily story. Measuring the screenplay reported 2 repeats where the draft
        # [EN] had none -- and `day_bodies` **replaces** the body, so a real edit would have
        # [EN] bound the screenplay into the novel version.
        src = _day_novel_of(run, day)
        if not src:
            try:
                src = _tidy_for_novel(body or '')
            except Exception:                                    # noqa: BLE001
                src = (body or '')
        src = src.strip()
        if not src:
            continue
        before = src
        # ★★★ **先切掉文件头，只把正文交出去检查**（实测踩到的硬伤）：
        #   整理稿开头是 `# 当天故事` + 一段引用块（"它是**原始稿加细节**……"），
        #   那是**版式**不是正文。把它一起交给"合并平铺段 / 收拥挤段"，
        #   标题行会被并进正文、然后就没了 —— 实测一轮下来 `# 当天故事` 整行消失。
        #   ⇒ 头原样留着，只检查一级标题 `## ` 之后的部分（没有就整篇当正文）。
        # [EN] Strip the file header first: the prose pass merges "flat" paragraphs and
        # [EN] would swallow the `# title` line (measured: the heading vanished entirely).
        head, tail = _split_md_header(src)
        if not tail.strip():
            continue
        # ── 逐轮 / 逐步的细粒度进度（2026-10-28）──
        #   `_base` = 这一天在这一步里的起点份额；一天内部再按「轮 → 步」细分。
        #   ⇒ 界面上会看到 "复查第 2/3 天 · 第 3/5 轮 · 打转重写" 一路往前爬，
        #     而不是干等一分钟。
        # [EN] Per-round / per-step granularity: the day owns a slice, and inside it each round
        # [EN] and each repair step owns a fraction, so the UI crawls visibly instead of waiting.
        _base = (_di - 1) / _n_days
        _share = 1.0 / _n_days

        def _on_round(_r, _tr, _label, _si, _sn, _b=_base, _s=_share):
            _r_i, _tr_i = max(1, int(_r)), max(1, int(_tr))
            _inner = ((_r_i - 1) + (int(_si) + 1) / max(1, int(_sn))) / _tr_i
            _say(f'复查第 {_di}/{_n_days} 天 · 第 {_r_i}/{_tr_i} 轮 · {_label}',
                 _b + _s * min(0.95, _inner))

        _say(f'复查第 {_di}/{_n_days} 天', _base + _share * 0.05)
        try:
            fixed = await A.prose_checkup(
                tail, rounds=int(rounds or 0), tag=f'导出第{day}天',
                on_round=_on_round)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('成书复查：第 %d 天检查失败（原样保留）：%s', day, e)
            continue
        checked += 1
        merged = (head + fixed) if fixed and fixed.strip() else before
        if merged != before:
            bodies[day] = merged
            changed += 1
        else:
            bodies[day] = before
    _LOG.info('成书复查：查了 %d 天，改了 %d 天', checked, changed)
    # ══════════════════════════════════════════════════════════════
    # 全书级 Reflection（2026-10-20，用户点名"导出环节加入 Reflection Agent"）
    # ══════════════════════════════════════════════════════════════
    # ★★★ 为什么逐天检查完还要再来一遍：逐天用的是**单章视角**，
    #   而四篇真跑逐篇读过之后暴露的三类毛病，全都**跨天才成形**：
    #     · 反复问"缺什么"、反复答"够使"（问法每次不同、答法不变）；
    #     · 同一句请求来回说（"跟我走"/"我跟你走"）；
    #     · 同一件东西在几个人手里转（鸭子提来推去 7 次）。
    #   而当时**八项指标全是 0** —— 它们都在单句/单段粒度上量。
    # ⚠ 这一层的产物是**候选 + 一份给人看的记录**，不是"毛病数"：
    #   判"重复"不能直接当病（真人比真跑重复得更多，实测真人 3 字片段命中 5 处
    #   全是"崇仁坊""十五年前"这类正常写法），标准是**可删除性**，
    #   那是语义判断 —— 交给反思记录里的清单，由作者与顾问判。
    # [EN] Book-level Reflection at export. Per-day checks use a single-chapter view;
    # [EN] the three defects found by reading four real runs are all cross-day. The
    # [EN] output is candidates plus a human-readable record, never a defect count:
    # [EN] whether a repetition is a device is a deletability call, not a counter's.
    _say('全书反思（跨天毛病）', 0.93)
    try:
        bodies = await _reflect_whole_book(run, bodies, days, rounds=rounds)
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('全书反思失败（逐天结果照常装订）：%r', e)
    return bodies


def _reflect_days_root(run) -> Path:
    """反思记录的落点：`<运行文件夹>/导出/`（跟成品在一起，方便对照）。

    ⚠ 第一版写的是 `Path(run.dir)` —— `RunFolder` 根本没有 `dir` 这个属性
      （目录叫 `root`），于是异常被兜底成 `Path('.')`，
      **记录被写到了项目根目录**（真跑 snow_v25 实测：`./反思记录.md`）。
      兜底到当前目录是最坏的兜底：不报错、还留下一个没人找得到的文件。
    [EN] `RunFolder` exposes `root`, not `dir`; the old fallback wrote the record into
    [EN] the project root and said nothing.
    """
    for attr in ('root', 'dir', 'path'):
        v = getattr(run, attr, None)
        if v:
            return Path(v) / '导出'
    try:                                    # 再兜一层：从第一天的位置反推
        days = list_days(run)
        if days:
            return days[0][1].parent.parent / '导出'
    except Exception:                                            # noqa: BLE001
        pass
    return Path('.')


async def _reflect_whole_book(run, bodies: dict, days: list,
                              *, rounds: int | None = None) -> dict:
    """**全书级反思**：找候选 → 定向重写 → 验收 → 记录。

    三件事按顺序，缺一件就退化成"只报不改"或"改了没底"：
      1. `global_checks.audit_book` 出候选（带可回查的原句）；
      2. 命中的那几天，把候选当成**反思提示**（`hint`）再跑一轮改写 ——
         这是 Reflexion 的"语言反馈进下一次尝试"；
      3. 改完的结果**必须过 `verdict.compare`**：退化 / 违反硬约束 / 可疑就保留原文。
         ⇒ 这一层永远不会让稿子变差，最坏是什么都没改。
    """
    from crew import global_checks as GC
    from crew import verdict as V
    from crew import agents as A
    from crew import critic as CR

    pairs = [(int(d), str(bodies.get(int(d)) or '')) for d, _p in days]
    found = GC.audit_book(pairs)
    out_dir = _reflect_days_root(run)
    if found['total'] == 0:
        _LOG.info('全书反思：没有值得复核的跨句/跨天形态')
        # ★ 即使没有跨句候选，**外部评审仍要分诊** —— 那两种情况完全不同：
        #   稿子很干净 vs 内部检测器看不见评审说的那个毛病（这一轮实测过）。
        _md0 = ''
        try:
            _whole0 = '\n'.join(t for _d, t in pairs)
            _md0, _ = _adjudicate_review(run, _whole0, ())
        except Exception as _e:                                  # noqa: BLE001
            _LOG.debug('评审分诊失败（不影响导出）：%r', _e)
        _write_reflect_note(out_dir, found, {}, 0, opinion=None, critique=_md0)
        return bodies
    _LOG.info('全书反思：%d 条候选（%s）', found['total'],
              '、'.join(f'{k}×{v}' for k, v in found['counts'].items()))

    # ★★★ 让**顾问**过一眼：哪一条是手法、哪一条真在原地打转。
    #   这一步是整条链上唯一用 LLM 的地方，而它被压到最低权限：
    #   只表态"该留/该改"、只说一句理由，**不给改法**（给了它就同时成了写稿方，
    #   自偏好立刻回来 —— 见 `crew/critic.py` 顶部）。
    #   内建一条"明显是手法"的对照：顾问若把它判成打转，整批降级、只用日志不用它。
    # [EN] Ask the advisor which candidates are devices. It is the only LLM step here
    # [EN] and its powers are deliberately minimal: verdict plus one reason, never a
    # [EN] rewrite. A built-in canary downgrades the whole batch if the advisor calls
    # [EN] an obviously-fine repetition a loop.
    items = [{'kind': x.kind, 'key': x.key, 'detail': x.detail,
              'sample': (x.samples or ('',))[0]} for x in found['issues']]
    opinion = await CR.review(items, ask=_ask_advisor, tier='cheap')
    loop_hint = CR.hint_of(opinion)
    _LOG.info('全书反思：顾问 %s', opinion.summary())
    if loop_hint and opinion.trusted:
        hint = loop_hint
    else:
        # 顾问不可用/不可信 ⇒ 退回"把全部候选当提示"。这是安全的：
        # 改完还要过 `verdict.compare`，改坏了不会被采纳，最坏只是白跑一次改写。
        hint = '\n'.join(x.one_line() for x in found['issues'])

    # 命中的天：候选自带 days 时用它；整篇级的（无 days）就用最长的那天。
    hot: set[int] = set()
    for x in found['issues']:
        hot.update(int(d) for d in (x.days or ()))
    if not hot and pairs:
        hot = {max(pairs, key=lambda p: len(p[1]))[0]}

    # ── 外部评审分诊（有 `外部评审.md` 才跑）──
    _names = set()
    try:
        from crew import prose_flow as _PFN
        _whole = '\n'.join(t for _d, t in pairs)
        _names = {n for n in _PFN._cast_names(_whole) if n}
    except Exception:                                            # noqa: BLE001
        pass
    crit_md, crit_lessons = _adjudicate_review(run, _whole if pairs else '', _names)
    if crit_lessons:
        # 只把**成立**的条目追加进反思提示（不覆盖原有的候选提示）。
        extra = '\n'.join(f'- {x["why"]} ⇒ {x["advice"]}' for x in crit_lessons)
        hint = (hint + '\n' + extra) if hint else extra

    applied: dict[int, str] = {}
    for d, _p in days:
        d = int(d)
        if d not in hot:
            continue
        head, tail = _split_md_header(bodies.get(d) or '')
        if not tail.strip():
            continue
        try:
            fixed = await A.prose_checkup(tail, rounds=max(1, int(rounds or 1)),
                                          tag=f'导出反思第{d}天', hint=hint)
        except Exception as e:                                   # noqa: BLE001
            _LOG.warning('全书反思：第 %d 天改写失败（保留原样）：%r', d, e)
            continue
        if not fixed or fixed.strip() == tail.strip():
            continue
        cand = head + fixed
        dec = V.compare(bodies.get(d) or '', cand, label=f'第{d}天反思')
        if dec.applied:
            bodies[d] = cand
            applied[d] = dec.why
            _LOG.info('全书反思：第 %d 天采纳（%s）', d, dec.why)
        else:
            _LOG.info('全书反思：第 %d 天未采纳（%s）', d, dec.why)

    _write_reflect_note(out_dir, found, applied, len(hot), opinion=opinion,
                        critique=crit)
    return bodies


# ══════════════════════════════════════════════════════════════
# **外部评审分诊**（2026-10-20，用户要求"结合现有评价工作流"）
# ══════════════════════════════════════════════════════════════
#: 用户把稿子发给别的 AI 评审之后，把那份意见存成这个文件放在运行文件夹里。
#: 为什么用**文件**而不是接口：外部评审是人工发出去的，结果也是人工拿回来的；
#: 假装能自动对接只会做出一个用不上的接口。
REVIEW_NAME = '外部评审.md'


def _load_review(run) -> str:
    """读 `外部评审.md`（放在运行文件夹根或 `导出/` 下都行）。读不到返回空串。

    ⚠ 读失败一律返回空串、**不报错** —— 没有外部评审是常态，不是故障。
    """
    for base in (_reflect_days_root(run).parent, _reflect_days_root(run)):
        for name in (REVIEW_NAME, '外部评审.txt'):
            try:
                p = Path(base) / name
                if p.is_file():
                    return p.read_text(encoding='utf-8')
            except OSError:
                continue
    return ''


def _adjudicate_review(run, text: str, names) -> tuple[str, list]:
    """把外部评审拆条、逐条量、分级。返回 `(分诊表 markdown, 教训列表)`。

    ★ 这是"结合现有评价工作流"的**唯一**接法，而且它**不改稿** ——
      只做三件事：量一遍、分诊、把`成立`的转成教训。
      为什么不让它直接改：批评的处方常常是"改名/删段"，
      照改会撞上既定设计（实测：一份评审建议把「沈砚」改成「别问」，
      而那四个字是楼名+人名+规矩+口头禅的合一）。**诊断可以采信，处方必须过闸。**
    ★ 验证不了的条目**如实标 `无法验证`**，不假装验过 ——
      这一轮量过三次，"追问次数""主题集中度""悬念密度"在真人与真跑之间分不开。
    [EN] Adjudicate an external review: measure each claim, grade it, and keep only the
    [EN] confirmed ones as lessons. It never rewrites -- prescriptions like "rename X"
    [EN] routinely collide with deliberate design. Unmeasurable claims are reported as such.
    """
    try:
        from crew import critique as CR
    except Exception as e:                                       # noqa: BLE001
        _LOG.debug('评审分诊不可用：%r', e)
        return '', []
    raw = _load_review(run)
    if not raw.strip():
        return '', []
    try:
        items = CR.adjudicate(raw, text=text, names=tuple(names or ()))
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('外部评审分诊失败（不影响导出）：%r', e)
        return '', []
    n_ok = sum(1 for it in items if it.verdict == 'confirmed')
    _LOG.info('外部评审分诊：%d 条，成立 %d 条（只有这些驱动改写）',
              len(items), n_ok)
    for it in items:
        _LOG.info('  %s', it.line())
    try:
        md = CR.markdown(items)
    except Exception:                                            # noqa: BLE001
        md = ''
    return md, CR.lessons(items)


async def _ask_advisor(prompt: str, tier: str, purpose: str) -> str:
    """顾问的调用适配器（**只走 `llm.replies.ask`**，别自建 httpx —— 会漏账）。"""
    from llm import replies
    rep = await replies.ask(tier, [{'role': 'user', 'content': prompt}],
                            purpose=purpose, want='text', max_tokens=1200,
                            min_chars=8)
    return str(getattr(rep, 'raw', '') or getattr(rep, 'value', '') or '')


def _write_reflect_note(out_dir: Path, found: dict, applied: dict,
                        hot: int, *, opinion=None, critique: str = '') -> None:
    """写一份给人看的 `反思记录.md`。

    ★ 必须写"哪些天被改了、为什么采纳/没采纳" —— 只写候选清单的话，
      作者没法判断"机器到底动过什么"。这是可审计性，不是装饰。
    """
    from crew import global_checks as GC
    lines = ['# 导出前的全书反思', '',
             f'- 候选：{found.get("total", 0)} 条（'
             + '、'.join(f'{k}×{v}' for k, v in (found.get('counts') or {}).items())
             + '）' if found.get('total') else '- 候选：0 条',
             f'- 涉及天数：{hot} 天', '']
    lines += GC.report_lines(found)
    lines += ['', '## 顾问复核（只表"手法/打转"，不给改法）', '']
    if opinion is None:
        lines.append('- 没有候选，不需要顾问。')
    elif not opinion.opinions:
        lines.append(f'- 顾问没有给出可用的表态（{opinion.why or "原因未说明"}）。')
    else:
        if not opinion.trusted:
            lines.append(f'- ⚠ **这一批表态不可信**：{opinion.why}')
        for x in opinion.opinions:
            lines.append(f'- {x.one_line()}')
    if critique:
        lines += ['', critique]
    lines += ['', '## 定向重写的验收结果', '']
    if applied:
        for d, why in sorted(applied.items()):
            lines.append(f'- 第 {d} 天：**采纳** —— {why}')
    else:
        lines.append('- 没有采纳任何改写（要么没命中，要么验收层判为退化/可疑）。')
    lines += ['', '> 说明：这些是**候选**。重复也可能是手法 ——'
                  '判据是"删掉它读者会损失什么"，说不出损失才算病。', '']
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / REFLECT_MD).write_text('\n'.join(lines), encoding='utf-8')
        _LOG.info('全书反思：记录已写到 %s', out_dir / REFLECT_MD)
    except OSError as e:
        _LOG.warning('全书反思：记录写不出去（不影响装订）：%r', e)


def _split_md_header(text: str) -> tuple[str, str]:
    """把整理稿切成 `(文件头, 正文)`。

    文件头 = 开头的 `# 标题` 到最后一段引用块（`>`）为止，**含空行**；
    正文 = 第一个 `## ` 之后的内容。找不到 `## ` 就整篇当正文（头为空）。
    ⚠ 这是"版式"与"内容"的分界，不是内容判断 —— 所以只用行首标记判，不猜语义。
    [EN] Split the markdown into `(header, body)`: header = the `# title` plus the
    [EN] following blockquote, body = everything from the first `## ` on.
    """
    raw = str(text or '')
    pos = -1
    for m in re_md_h2.finditer(raw):
        pos = m.start()
        break
    if pos < 0:
        return '', raw
    return raw[:pos], raw[pos:]


re_md_h2 = __import__('re').compile(r'^## ', __import__('re').M)



async def write_manuscript_mumu(run, *, upto_day: int | None = None,
                                on_day=None) -> dict:
    """导出『最终改写稿』时改走 MuMuAINovel：据『原始稿 + 推演过程』重写每一天。

    服务没起 / 超时 / 写空 → 那一天**退回内部整理稿**（`_day_novel_of` /
    `_tidy_for_novel` + `_fold_repeats`），绝不丢这一天的戏。
    返回同 `write_manuscript`（另在日志里写明哪些天回退了、为什么）。

    `on_day(i, total, day)` —— **逐天进度回调**（2026-10-26 加）。
    ★ 为什么必须有它：这一步**每天**都要调一次 MuMu，实测一章 17~207 秒，
      而 `MUMU_EXPORT_TRIES` 默认 2（每章写两遍）⇒ 两天就能跑十分钟。
      在此之前界面只知道"档"级进度（原文/改写稿各一行），进度条**十分钟不动**
      ⇒ 用户以为卡死 → 去点「停止」→ 多出一份 v1/v2。**这是那次重复导出的直接诱因。**
    [EN] `on_day(i, total, day)` -- **per-day progress callback** (added 2026-10-26).
    [EN] Why it is required: each day calls MuMu once, measured 17-207 s per chapter, and
    [EN] `MUMU_EXPORT_TRIES` defaults to 2 (two passes) => two days can take ten minutes.
    [EN] Before this the UI only knew kind-level progress, so the bar sat still for ten minutes,
    [EN] the user assumed a freeze and clicked Stop -- which is what produced the duplicate draft.
    """
    # 懒导入：导出这一层不该在顶层把 `crew/` 拖进来（那是推演侧的事）。
    # [EN] Lazy import: the export layer shouldn't pull `crew/` in at top level (that's the
    # [EN] simulation side's concern).
    from crew import agents as A

    days_all = list_days(run)
    days = days_all if upto_day is None else [d for d in days_all if d[0] <= upto_day]
    day_bodies: dict[int, str] = {}
    degrades: list[str] = []
    try:
        project_key = str(getattr(run, 'project_dir', None) or run.root).strip() or '未命名'
    except Exception:                                            # noqa: BLE001
        project_key = '未命名'
    novel_dir = getattr(run, 'project_dir', None) or Path(run.root)

    _total = len(days)
    for _i, (day, path) in enumerate(days, 1):
        # 逐天进度：**排在真正干活之前**（界面立刻能看到"正在写第 1/2 天"，
        # 而不是等这一章十分钟后才变）。回调异常一律吞掉 —— 界面问题不该弄挂导出。
        # [EN] Emit **before** the work so the UI shows "writing day 1/2" immediately; swallow
        # [EN] callback errors (a UI problem must not break the export).
        if on_day is not None:
            try:
                on_day(_i, _total, int(day))
            except Exception:                                    # noqa: BLE001
                pass
        day_title, meta, body = read_day_full(path)
        if not day_title:
            day_title = f"第 {day} 天"
        # ★★★ 2026-10-26：**先看有没有「当天整理稿」，有就直接用，不走 MuMu**。
        #
        #   为什么这条排在 MuMu 之前（这是本轮 bug 的直接修法）：
        #     `MUMU_TARGET_WORDS` 默认 2500 —— MuMu 每调一次只吐**一章 2500 字**。
        #     实测那一天真实演了 **21.3 万字**（133 幕），而以前喂给它的是被覆盖成
        #     **381 字**的残稿 ⇒ 它拿 381 字编出 8654 字，用户看到的"最终成稿"
        #     根本不是那天发生的事（原话：「完全不是一个故事了」）。
        #
        #   而项目里**本来就有**一份正经小说成稿：`当天故事.md`（收工时小说作家
        #   把这一天写成小说形式，`sim/loop._day_novel` 写的）。同一天它有 **13 万字**。
        #   ⇒ 有它就**没必要**再让 MuMu 拿零头重写一遍 —— 那既丢内容又烧时间。
        #
        #   ⚠ 够不着门槛（老运行没有这份文件 / 整理残了）才走 MuMu，且输入**受控**：
        #     见下面 `_mumu_input`，超长会截断并记账，不静默。
        # [EN] ★★★ 2026-10-26: **use the day's organized draft first; only then MuMu**.
        # [EN] Reason: `MUMU_TARGET_WORDS` is 2500 -- each call yields **one 2500-char chapter**.
        # [EN] The day actually ran **213k chars** (133 acts) while it used to be fed the
        # [EN] **381-char** remnant, so it invented 8654 chars from it: the "final draft" was not that
        # [EN] day's story at all. The project already has a real novel draft, `当天故事.md`
        # [EN] (written by the novelist at wrap-up): **130k chars** for the same day.
        _organized = _day_novel_of(run, day)
        if _organized and len(_organized) >= max(_ORGANIZED_MIN_CHARS,
                                                 int(len(body) * _NOVEL_MIN_RATIO)):
            day_bodies[day] = _fold_repeats(_organized)
            _LOG.info('第 %d 天：用当天整理稿（%d 字），不调 MuMu（全量正文 %d 字）',
                      day, len(_organized), len(body))
            continue
        # 原始稿 = 这一天逐字记录的正文；推演过程 = 这一天的过程痕迹
        # （在场名单 / 本幕依据 / 机制备注）。两者都在 read_day 里现成可取。
        # [EN] raw novel = this day's verbatim body; derivation process = this day's process
        # [EN] traces (cast list / scene basis / mechanism notes), both available from read_day.
        raw_novel = _mumu_input(body)
        process = (meta or "").strip() or "（这一天没有过程痕迹记录）"
        if len(body) > _MUMU_INPUT_MAX:
            degrades.append(
                f"第 {day} 天：全量正文 {len(body)} 字，超过 MuMu 单次能吃的 "
                f"{_MUMU_INPUT_MAX} 字，只喂了开头一段")
        # ★★★ 2026-10-21（用户点名的导出输入三件套）：
        #   **设定集 + 历史小说 + 本地推演过程**。
        #   `setting` 取自这本项目的设定集（与推演时喂给演员的是同一份），
        #   `_history_novel` 在 `_mumu_export` 内部按天号取前几章正文。
        # [EN] ★★★ 2026-10-21 (the three export inputs the user named):
        # [EN] **setting book + history novel + local derivation process**.
        # [EN] `setting` comes from this project's setting book (the same one fed to the actors during
        # [EN] simulation); `_history_novel` takes the previous chapters' prose by day number inside
        # [EN] `_mumu_export`.
        text, why = await A._mumu_export(
            day=day, title=day_title, raw_novel=raw_novel, process=process,
            project_key=project_key, novel_dir=novel_dir,
            characters=[], genre="",
            setting=_setting_brief(run),
        )
        if text and text.strip():
            day_bodies[day] = text
        else:
            # 回退：与 `render_manuscript` 内部路径完全一致（保证「不丢戏」）。
            # [EN] Fallback: identical to `render_manuscript`'s internal path (guarantees "no lost
            # [EN] day").
            fb = _tidy_for_novel(body)
            better = _day_novel_of(run, day)
            if better:
                fb = better
            fb = _fold_repeats(fb)
            day_bodies[day] = fb
            degrades.append(f"第 {day} 天：{why or '未成功'}")

    version = next_version(run, MODE_NOVEL)
    rendered = render_manuscript(run, mode=MODE_NOVEL, upto_day=upto_day,
                                 version=version, day_bodies=day_bodies)
    if degrades:
        _LOG.warning("导出改写回退 %d/%d 天（已用内部整理稿兜底）：%s",
                     len(degrades), len(days), "；".join(degrades))
    return _flush_manuscript(run, rendered, MODE_NOVEL, version)


# ══════════════════════════════════════════════════════════════
#  可选：LLM 润色稿
# [EN] Optional: LLM-polished draft
# ══════════════════════════════════════════════════════════════
_POLISH_SYSTEM = (
    "你是一位中文小说编辑。任务是把「按天合订的模拟素材稿」整理成一份"
    "连贯、可读的小说稿。\n"
    "硬要求：\n"
    "1. **只做整理，不新增情节**——不许编出原作里没有的事件、人物、对话。\n"
    "2. 删掉一切过程记录（在场名单、关键事件编号、张力数值、幕次标记）。\n"
    "3. 保持既有的人称、语气、称呼；人物性格不许漂移。\n"
    "4. 让相邻的日子读起来是连续的（上一段结尾自然接上下一段），"
    "**但 `## 第 N 天` 这种分天标题必须原样保留**：它是分天标记，不是过程痕迹。\n"
    "5. 直接输出正文，不要目录、不要说明、不要用代码块包起来。\n"
    "★ 2026-10-25 改第 4 条：原来写的是「而不是每天各起一段」，模型就把"
    "`## 第 N 天` 当成\"每天各起一段\"的痕迹一并删了 —— 润色稿因此变成一整片，"
    "读者分不清哪段是哪天。**要连贯的是行文，不是取消分天。**"
)
# [EN] ★ 2026-10-25 changed rule 4: it used to read "rather than each day starting a new
# [EN] section", and the model took `## 第 N 天` as exactly that trace and deleted it -- the
# [EN] polished draft became one continuous block and readers could not tell days apart.
# [EN] **Smoothness is about the prose, not about erasing day boundaries.**

_POLISH_CHUNK = 6000          # 单次提交的正文字数上限（超了分块处理）
# [EN] Max body character count for a single submission (split into chunks if exceeded)


async def polish_manuscript(run, manuscript: str, *,
                            instructions: str = "") -> str:
    """把合订本交给 LLM 整理成连贯小说稿。

    **只在用户明确要求时调用**（默认不跑）：它要花 token，而且会改写原文措辞。
    长稿分块处理，块与块之间带上一块的结尾做衔接上下文。
    
        English:
    Hand the bound volume to the LLM to organize into a coherent novel draft.
        **Only call when the user explicitly requests it** (not run by default): it costs tokens, and it rewrites the original wording.
        Long drafts are processed in chunks, with the end of the previous chunk carried as linking context between chunks.
    """
    body = _strip_bundle_header(manuscript)
    if not body.strip():
        return manuscript

    model_key = CFG.s("STORY_DOC_MODEL")
    tier = "front" if model_key == "MODEL_FRONT" else "daily"

    chunks = _split_chunks(body, _POLISH_CHUNK)
    done: list[str] = []
    tail = ""
    n_head_in = len(re.findall(r"(?m)^## ", body))
    n_head_out = 0
    # ★ 2026-10-26：跨天章里的**日期行**（`**第 N 天 · …**`）也要数。
    #   只数 `## ` 的话，模型把日期行改没了这条路上**一个字都不会被看见** ——
    #   而读者正是靠它才知道这一章里哪一段是第几天。
    # [EN] ★ 2026-10-26: also count the **day markers** (`**第 N 天 · …**`) inside a multi-day
    # [EN] chapter. Counting only `## ` means a model that drops every marker is never noticed --
    # [EN] and those markers are exactly how the reader knows which stretch is which day.
    n_mark_in = len(re.findall(r"(?m)^\*\*第 \d+ 天", body))
    n_mark_out = 0
    for idx, chunk in enumerate(chunks):
        # ★★★ 分天标题**硬回填**（2026-10-25）：提示词里写了"必须保留"也不算数 ——
        #   实测模型把 `## 第 N 天` 当格式噪音删掉（v2 润色稿 0 个标题）。
        #   所以在这里先抽出块首标题、润色后如果没了就补回去。
        #   ⚠ 为什么只在**块级**补：`_split_chunks` 已经保证「尽量在天标题处断开」，
        #     所以每个 `## 第 N 天` 天然落在**某一块的开头**，补回块首位置就是准确位置。
        #     全文里到处找位置补是做不到的（LLM 改了措辞，锚点对不上）。
        # [EN] ★★★ Hard restore of day headers (2026-10-25): saying "must keep" in the prompt is not
        # [EN] enough -- the model measuredly deletes `## 第 N 天` as formatting noise (0 headers in the
        # [EN] v2 polished draft). So extract the chunk's leading header first and put it back if lost.
        # [EN] ⚠ Why chunk level only: `_split_chunks` already breaks at day headers, so every
        # [EN] `## 第 N 天` naturally sits at the **start of some chunk**, and restoring it there is the
        # [EN] exact position. Re-finding positions in the whole text is impossible (wording changed).
        head = ""
        # ⚠ 2026-10-26：块首可能是 `## 标题`，也可能是跨天章里的 `**第 N 天 …**` 日期行。
        #   两种都要抽出来 —— 只认 `## ` 的话，日期行被模型删掉就补不回来了
        #   （`_split_chunks` 已经在它前面断开，所以它一定落在块首）。
        # [EN] 2026-10-26: a chunk may start with `## heading` or with the bold `**第 N 天 …**`
        # [EN] day marker of a multi-day chapter. Both must be extracted: recognising only `## `
        # [EN] means a deleted marker can never be restored (`_split_chunks` already breaks before
        # [EN] it, so it always sits at a chunk head).
        m_head = re.match(r"(?s)^((?:## .*?|\*\*第 \d+ 天[^\n]*))\n", chunk)
        if m_head:
            head = m_head.group(1).rstrip()
            chunk = chunk[m_head.end():]

        if len(chunks) == 1:
            scope = "下面是全部正文。"
        elif idx == 0:
            scope = f"下面是正文的第 1 段（共 {len(chunks)} 段），后面还有。"
        elif idx == len(chunks) - 1:
            scope = f"下面是正文的最后一段（第 {idx + 1}/{len(chunks)} 段）。"
        else:
            scope = f"下面是正文的第 {idx + 1}/{len(chunks)} 段。"

        parts = [scope]
        if tail:
            parts.append(f"上一段结尾（仅供衔接，不要重复输出）：\n…{tail}")
        extra = f"\n额外要求：{instructions.strip()}" if instructions.strip() else ""
        parts.append(f"正文：\n{chunk}{extra}")

        messages = [
            {"role": "system", "content": _POLISH_SYSTEM},
            {"role": "user", "content": "\n\n".join(parts)},
        ]
        text = await llm.chat(tier, messages, purpose="novel_polish",
                              max_tokens=8000, temperature=0.6)
        text = (text or "").strip()
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
        # ⚠ 补回的判据也要认日期行：模型把 `**第 1 天 · 辰时 → 子时**` 改成 `**第 1 天**`
        #   时，"已经有日期行"就成立，不必再补一行（补了会重复）。
        # [EN] The restore test must also accept the bold day marker: when the model simplifies
        # [EN] `**第 1 天 · 辰时 → 子时**` to `**第 1 天**`, a marker already exists and adding
        # [EN] another would duplicate it.
        if head and not re.match(r"(?m)^(?:#{1,2} |\*\*第 \d+ 天)", text):
            text = head + "\n\n" + text
        n_head_out += len(re.findall(r"(?m)^## ", text))
        n_mark_out += len(re.findall(r"(?m)^\*\*第 \d+ 天", text))
        done.append(text)
        tail = text[-300:]

    out = "\n\n".join(done).strip()
    if n_head_in and n_head_out < n_head_in:
        # 不静默吞掉：跨天标题数对不上时说出来（块内多天时兜不住，得让人看见）。
        # [EN] Never swallow it silently: report when the day-header count drops (a chunk spanning
        # [EN] several days cannot be fully restored, and that must be visible).
        _LOG.warning("润色稿的天标题比原始稿少（原 %d → 润色后 %d）："
                     "块内跨多天时只能补回块首那一个，请人工核对分天", n_head_in, n_head_out)
    if n_mark_in and n_mark_out < n_mark_in:
        # 同一条口径也用在跨天章的日期行上：丢了就说，别让人以为"这一章本来就没有分天"。
        # [EN] Same rule for the day markers of a multi-day chapter: say it when they are lost, so
        # [EN] nobody assumes "this chapter simply has no day breaks".
        _LOG.warning("润色稿的**日期行**比原始稿少（原 %d → 润色后 %d）："
                     "跨天事件的章内分天可能已经丢了，请人工核对", n_mark_in, n_mark_out)
    return out or manuscript


def _strip_bundle_header(text: str) -> str:
    """去掉合订本的文件头（到第一条 `---` 为止），只留正文。
        English:
    Strip the file header from the bound volume (up to the first `---`), keeping only the body.
    """
    parts = text.split("\n---\n")
    if len(parts) > 1:
        return "\n---\n".join(parts[1:])
    return text


def _split_chunks(text: str, limit: int) -> list[str]:
    """按段落切块，尽量在 `## ` 章/幕标题处断开，**也**在跨天章里的 `**第 N 天 …**` 处断开。

    ★ 2026-10-26：跨天事件装订成一章之后，章内的"这是第几天"是**粗体行**（不是标题）。
      这里必须也在它前面断开，否则同一个块里会跨好几天 ——
      而 `polish_manuscript` 的硬回填**只能在块首**补回被模型删掉的那一行
      （模型改了措辞，全文里再找位置是对不上的）。
      不断开 ⇒ 块内第 2 天以后的日期行删了就永远补不回来，读者看到一整章没有分天。
    [EN] Split into chunks by paragraph, breaking at `## ` headings and **also** at the bold
    [EN] `**第 N 天 …**` day marker inside a multi-day chapter. ★ 2026-10-26: after a cross-day
    [EN] event is bound into one chapter, "which day" is a bold line, not a heading. Chunking must
    [EN] break there too: `polish_manuscript` can only restore a deleted marker **at the chunk
    [EN] head** (the model rewords things, so re-finding positions in the whole text is
    [EN] impossible). Without this, markers for day 2 onward are lost for good and the chapter has
    [EN] no day breaks at all.
    """
    if len(text) <= limit:
        return [text]
    # 先按天标题切，再把小块合并到 limit 以内
    # [EN] First split by day titles, then merge small chunks up to within the limit
    pieces = re.split(r"(?m)^(?=## |\*\*第 \d+ 天)", text)
    chunks: list[str] = []
    buf = ""
    for piece in pieces:
        if len(buf) + len(piece) > limit and buf:
            chunks.append(buf.strip())
            buf = piece
        else:
            buf += piece
        # 单块本身就超限（罕见）→ 硬切
        # [EN] If a single chunk itself exceeds the limit (rare) → hard split
        while len(buf) > limit * 2:
            chunks.append(buf[: limit * 2].strip())
            buf = buf[limit * 2:]
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


def write_polished(run, text: str, version: int,
                   day_numbers: list[int] | None = None) -> Path:
    """落盘润色稿（跟合订本同版本号，文件名带「润色」与天数）。

    **永远另存**：润色是 LLM 改写过的，不能覆盖合订本，
    否则「事实来源」和「最终改写稿」就分不清了。
    
        English:
    Write the polished draft to disk (same version number as the bound volume, filename includes
    "润色" and the day range).
        **Always save as a new file**: the polished draft has been rewritten by the LLM, and must not overwrite the bound volume,
        otherwise the "source of truth" and the "rewritten draft" become indistinguishable.
    """
    ensure_dir(run.export_dir)
    stem = f"{_STEM[MODE_NOVEL]}_v{version}{_span(day_numbers or [])}_润色"
    path = run.export_dir / f"{stem}.md"
    n = 2
    while path.exists():
        path = run.export_dir / f"{stem}{n}.md"
        n += 1
    atomic_write_text(path, text.rstrip() + "\n")
    _LOG.info("%s润色稿: %s", _STEM[MODE_NOVEL], path.name)
    return path


def latest_file(run, mode: str) -> "Path | None":
    """这一档**最新的一份**装订稿（按版本号最高者），没有 → `None`。

    ★ 抽出来是因为「推演结果」对话框（2026-10-29）要**读**现成的稿子来显示，
      与写盘那侧用的是**同一个命名规则**（`_STEM` + `_v{n}`）—— 各写一份
      glob 迟早漂。
    [EN] The **latest** bound draft of this kind (highest version), None when absent.
    [EN] ★ Factored out because the "Derivation Results" dialog (2026-10-29) must **read** the
    [EN] existing draft to display it, sharing the same naming rule (`_STEM` + `_v{n}`) as the
    [EN] writing side -- separate globs would inevitably drift.
    """
    d = Path(run.export_dir)
    if not d.is_dir():
        return None
    stem = _STEM.get(mode, _STEM[MODE_NOVEL])
    best: tuple[int, Path] | None = None
    for p in d.glob(f"{stem}_v*.md"):
        m = re.search(r"_v(\d+)", p.name)
        if not m:
            continue
        v = int(m.group(1))
        if best is None or v > best[0]:
            best = (v, p)
    return best[1] if best else None


def latest_polished(run) -> "Path | None":
    """最新的一份 **LLM 润色稿**（`最终改写稿_vN_…_润色.md`），没有 → `None`。

    同名多份（`_润色2.md`）时按**修改时间**取最新 —— 序号后缀就是为了
    区分同一版润过几次，"最新"按时间看才是用户心里的那个"最新"。
    [EN] The **latest** LLM-polished draft (`最终改写稿_vN_..._润色.md`), None when absent.
    [EN] Among same-version copies (`_润色2.md`), the newest by mtime wins -- the numeric
    [EN] suffix exists to distinguish repeated polish passes of the same version, and
    [EN] "latest" for the user means newest in time.
    """
    d = Path(run.export_dir)
    if not d.is_dir():
        return None
    cands = list(d.glob(f"{_STEM[MODE_NOVEL]}_v*_润色*.md"))
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)

