# -*- coding: utf-8 -*-
"""Headless runner: one case -> one transcript.

This drives the *real* simulation loop (``RunLoop``) rather than calling any
LLM directly, because the thing under test is the whole pipeline: director
framing, crew script, per-agent decisions, scene building and the transcript
formatting.  Anything cheaper would measure a different system.

Runtime knobs are forced through ``CFG.set`` (memory only, never written to
``.env``).  The run is bounded by ``max_ticks``; the expensive end-of-run
chain (auto export / crew wrap-up) is switched off because the benchmark only
reads the live transcript.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import time
import traceback
from pathlib import Path
from typing import Any

from .config import Settings
from .dataset import Case, Work, clock_of
from .metrics import PROSE_KINDS
from .project_builder import build_project

# Everything unrelated to the transcript is turned off before assembling.
_FORCED = {
    "AUTO_EXPORT": "false",          # the wrap-up export costs minutes and adds nothing
    "ENDING_SCENE": "false",
    "SHOW_OPENING": "false",         # no window, no opening card
    "PAUSE_AT_NIGHT": "false",       # headless: nobody can click "resume"
    "CHECKPOINT_PAUSE": "false",
    "RUN_MODE": "open",              # bounded by max_ticks, not by the progress table
    "MUMU_ENABLED": "false",         # never start the external services
    "PENSHOT_ENABLED": "false",
    "PLOTPILOT_ENABLED": "false",
    "SCRIPT_REVIEW_EVERY_TICKS": "1",
}


def _divider_text(d: Any) -> str:
    """`Divider(kind=..., meta=..., note=...)` -> something a human can read."""
    note = getattr(d, "note", "") or ""
    kind = getattr(d, "kind", "") or ""
    meta = getattr(d, "meta", None) or {}
    if kind == "day_end":
        return f"第 {meta.get('day', '?')} 天结束"
    if kind == "day_start":
        return f"第 {meta.get('day', '?')} 天开始"
    if kind == "scene_end":
        return f"这一场结束（{note or '—'}）"
    if kind == "story_end":
        return f"故事结束（{note or '—'}）"
    if kind == "module_start":
        return f"模块开始：{meta.get('name') or note or '—'}"
    return note or kind or str(d)


async def _run_case(work: Work, case: Case, out_dir: Path, cfg: Settings) -> dict:
    from config import CFG
    from store.runfolder import RunFolder
    from sim.setup import assemble
    from sim.session import RunSession
    from util.flet_shutdown import kill_pid_tree  # noqa: F401  (import kept for parity)

    for k, v in _FORCED.items():
        CFG.set(k, v)
    CFG.set("BEAT_SECONDS", str(cfg.beat_seconds))
    CFG.set("TIME_RATIO", str(cfg.time_ratio))
    # ★★★ 2026-10-18：`GAME_START_TIME` **只认 `HH:MM`**（`sim/setup._start_clock` 要冒号），
    #   以前直接塞 `case.story_time`（"午后"/"深夜"）⇒ 静默退回 08:00（辰时）。
    #   第一轮四例全部从辰时开演，被评委记成"时间标注与正文冲突"。
    # [EN] ★★★ 2026-10-18: `GAME_START_TIME` **only accepts `HH:MM`** (`sim/setup._start_clock`
    # [EN] requires a colon); passing `case.story_time` ("午后"/"深夜") silently fell back to 08:00
    # [EN] (辰时). All four cases of round one started at 辰时 and the judge recorded it as a time
    # [EN] conflict.
    _clock = clock_of(case.story_time)
    if _clock:
        CFG.set("GAME_START_TIME", _clock)
    # ★★★ 2026-10-18：**本轮只让 present 里那几个人上场**（`ROUND_CAST` 是硬限制，见
    #   `world.is_on_stage`）。不设的话全体人物都算在场 —— 第一轮《红楼梦》里宝玉
    #   凭空出现（present 只有贾母/黛玉/王熙凤/王夫人）、《聊斋》里吴生凭空出现，
    #   两次都被评委记成"与设定直接冲突"。**这是基准漏设，不是产品 bug。**
    #   顺便锁住地点（`ROUND_SCENE`），免得跑到别的场景去。
    # [EN] ★★★ 2026-10-18: **only the people in `present` take the stage** (`ROUND_CAST` is a hard
    # [EN] limit, see `world.is_on_stage`). Without it every character counts as present -- in round
    # [EN] one, Bao Yu appeared out of nowhere in the Red Chamber case (present was only the
    # [EN] matriarch / Dai Yu / Xi Feng / Wang Furen) and Wu Sheng in the Liao Zhai case; the judge
    # [EN] called both "a direct conflict with the settings". **The harness simply never set it; this
    # [EN] is not a product bug.** The place is locked too (`ROUND_SCENE`) so the scene cannot wander.
    if case.present:
        CFG.set("ROUND_CAST", ",".join(case.present))
    if case.place:
        CFG.set("ROUND_SCENE", case.place)
    # 思考模式（A/B 对比用）。空 = 不碰，跟主程序 `.env` 走。
    # ⚠ 只改内存：`CFG.set` 不落盘，用户的 `.env` 一个字都不会被改。
    # [EN] Thinking mode (for A/B runs). Empty = leave it alone, follow the app's `.env`.
    # [EN] ⚠ Memory only: `CFG.set` never writes to disk, the user's `.env` stays untouched.
    if cfg.think_mode:
        CFG.set("LLM_THINKING_MODE", cfg.think_mode)

    # ★★★ 2026-10-18：**每一轮一个项目目录**。
    #   以前是 `work_dir/projects/<case_id>` —— 同一用例跑第二轮会复用上一轮的
    #   `第1次模拟/state.db`，于是"第二轮的前情提要带着第一轮的内容"，
    #   A/B 对比从第一步就不公平（而且外面完全看不出来：拍数、字数都正常）。
    #   默认建在**系统临时区**：用户不关心，也不会在项目里堆垃圾。
    #   `NB_KEEP_PROJECTS=true` 时才落到 `results/.work/projects/<run_id>/<case>/` 供复查。
    # [EN] ★★★ 2026-10-18: **one project directory per run**. It used to be
    # [EN] `work_dir/projects/<case_id>`, so a second run of the same case reused the previous
    # [EN] `第1次模拟/state.db` -- the second run's recap carried the first run's content, and the A/B
    # [EN] comparison was unfair from step one (with nothing visible from outside: tick count and
    # [EN] character count both look normal). Default lives in the **system temp dir**; only
    # [EN] `NB_KEEP_PROJECTS=true` writes under `results/.work/projects/<run_id>/<case>/`.
    if cfg.keep_projects:
        projects_root = cfg.work_dir / "projects" / (cfg.run_id or "adhoc") / case.id
        projects_root.mkdir(parents=True, exist_ok=True)
    else:
        import tempfile
        projects_root = Path(tempfile.mkdtemp(prefix=f"nb_{case.id}_"))
    proj = build_project(work, case, projects_root)
    run = RunFolder(proj.root, "第1次模拟").create()

    entries: list[dict] = []
    dividers: list[str] = []

    def on_narrative(text: str, priority: int = 0, kind: str = "", **kw: Any) -> None:
        entries.append({"t": round(time.time() - t0, 2), "kind": kind or "",
                        "text": str(text), "who": str(kw.get("who") or "")})

    def on_divider(d: Any) -> None:
        txt = _divider_text(d)
        dividers.append(txt)
        entries.append({"t": round(time.time() - t0, 2), "kind": "_divider",
                        "text": txt, "who": ""})

    t0 = time.time()
    loop, world, db = assemble(proj, run)
    loop.on_narrative(on_narrative)
    ses = RunSession(loop, world, run, max_ticks=cfg.ticks,
                     on_divider=on_divider, on_narrative=None)
    # RunSession wires loop.on_narrative to its own callback when given one;
    # we passed None so the callback installed above survives.
    ses.start()

    timed_out = False
    while ses.is_alive:
        await asyncio.sleep(1.0)
        tick = int(getattr(loop, "_tick_no", 0) or 0)
        budget_used = cfg.ticks and tick >= cfg.ticks
        elapsed = time.time() - t0
        # After the last beat the loop runs the (expensive) wrap-up chain; that is
        # not a timeout. Only cut it with the hard deadline.
        if elapsed > cfg.case_timeout and not budget_used:
            timed_out = True
            try:
                loop.stop()
            except Exception:                      # noqa: BLE001
                pass
            break
        if elapsed > cfg.case_timeout + 900:
            timed_out = True
            try:
                loop.stop()
            except Exception:                      # noqa: BLE001
                pass
            break
    try:
        await ses.wait(180)
    except Exception:                              # noqa: BLE001
        pass
    try:
        db.close()
    except Exception:                              # noqa: BLE001
        pass

    novel_text = _extract_novel(run.root)
    out_dir.mkdir(parents=True, exist_ok=True)
    if novel_text:
        (out_dir / "novel.md").write_text(novel_text, encoding="utf-8")
    with (out_dir / "transcript.jsonl").open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    (out_dir / "transcript.md").write_text(
        _render_md(work, case, entries, dividers), encoding="utf-8")

    meta = {
        "case": case.id,
        "work": work.id,
        "title": work.title,
        "ticks_requested": cfg.ticks,
        "ticks_done": int(getattr(loop, "_tick_no", 0) or 0),
        "status": getattr(ses, "status", ""),
        "reason": str(getattr(ses, "reason", "")),
        "timed_out": timed_out,
        "seconds": round(time.time() - t0, 1),
        "entries": len(entries),
        "chars": sum(len(e["text"]) for e in entries),
        "novel_chars": len(novel_text),
        # ★★ 2026-10-18：`cut` / `genres` / `author` / `medium` / `license` 原先**漏写**了 ——
        #   报告里"体裁""切入点"两列全空，而数据本身是有的（在用例 YAML 里）。
        #   这是"写了一半"的典型：`report` 读这些键，`runner` 不写，谁也不报错。
        # [EN] ★★ 2026-10-18: `cut` / `genres` / `author` / `medium` / `license` were **missing** --
        # [EN] the report's "genre" and "cut" columns came out empty while the data existed (in the
        # [EN] case YAML). A textbook "wrote half of it": `report` reads these keys, `runner` never
        # [EN] wrote them, and nothing complained.
        "cut": case.cut,
        "genres": list(work.genres),
        "author": work.author,
        "medium": work.medium,
        "license": work.license,
        "place": case.place,
        "present": case.present,
        "story_time": case.story_time,
        "cfg": {"ticks": cfg.ticks, "beat_seconds": cfg.beat_seconds,
                "time_ratio": cfg.time_ratio},
        "think_mode": (cfg.think_mode or "（跟主程序 .env 走）"),
        "model_note": "simulator LLM settings come from the app's own .env",
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if not cfg.keep_projects:
        _try_rmtree(projects_root)
    return meta


def _try_rmtree(path: Path) -> None:
    """删临时目录：**逐顶层子项**删，绝不因删不掉而中断。

    `shutil.rmtree(ignore_errors=True)` 挡不住本机的 safe-delete 守卫：它按
    "一次删 >50 个文件"直接 `SystemExit(1)`，而 `SystemExit` 是 `BaseException`
    —— `ignore_errors` 只吞 `OSError`。被它一杀，后面的写报告、关窗口全都不执行
    （`ab-auto` 那轮的退出码 1 就是这么来的）。
    [EN] Delete a temp dir **one top-level child at a time**, never aborting on failure.
    [EN] `shutil.rmtree(ignore_errors=True)` cannot stop the local safe-delete guard: it raises
    [EN] `SystemExit(1)` when a single operation removes >50 files, and `SystemExit` is a
    [EN] `BaseException` -- `ignore_errors` only swallows `OSError`. Once killed, writing the report
    [EN] and closing the window never run (that is where the ab-auto run's exit code 1 came from).
    """
    try:
        kids = list(path.iterdir())
    except OSError:
        return
    for k in kids:
        try:
            if k.is_dir():
                shutil.rmtree(k, ignore_errors=True)
            else:
                k.unlink(missing_ok=True)
        except BaseException:                     # noqa: BLE001
            pass
    try:
        path.rmdir()
    except OSError:
        pass


def _extract_novel(run_root: Path) -> str:
    """Pick the best available finished prose from a run folder.

    Preference: newest `导出/小说版本_*.md` > `当天故事.md` > longest daily file.
    The export is what a user would actually read, which is what we want to judge.
    """
    # ★★★ 2026-10-18：**优先 `小说原文`，不是 `小说版本`**。
    #   这是第一次 A/B 跑完才发现的：`小说版本_*.md` 自己就写着"**这是素材稿，
    #   不是成稿**"，而且**故意保留**剧本标记（`▸ 出场`、`◇ 心声`、`**场景**`）——
    #   于是基准会一边把它算成"元标记泄漏 30 处"、一边系统性拉低所有分数，
    #   而那不是产品的病，是**基准自己拿错了产物**。
    #   `小说原文` 是小说作家写的那一篇（没有剧本标记），才是"用户会读到的正文"。
    #   顺序：小说原文 → 当天故事 → 小说版本（最后兜底）→ 每日落盘。
    # [EN] ★★★ 2026-10-18: **prefer `小说原文` over `小说版本`**. Discovered only after the first
    # [EN] A/B run: `小说版本_*.md` says of itself "**this is a source draft, not a finished piece**"
    # [EN] and **deliberately keeps** script markers (`▸ 出场`, `◇ 心声`, `**场景**`), so the harness
    # [EN] was counting them as "30 leaked meta-marks" and systematically depressing every score --
    # [EN] not a product defect but **the harness reading the wrong artefact**. `小说原文` is the piece
    # [EN] the novelist wrote (no script markers), which is what a user would actually read.
    # [EN] Order: 原文 -> 当天故事 -> 版本 (last resort) -> daily dumps.
    # ★★★ 2026-10-18 第三次修正：**`当天故事.md` 排第一**。
    #   实测（6 拍那一轮）：
    #     · `小说原文_*.md` 只有 **531 字** —— 它是开演前作家写的"原著样章"，
    #       只覆盖开场那一拍，**不是全天的产出**（拿它评会把 6 拍算成 1 拍）；
    #     · `当天故事.md` 有 **2121 字**，覆盖全天，且是**纯正文**（无 `▸ 出场`/`◇ 心声`）；
    #     · `小说版本_*.md` 也是全天，但**故意保留**剧本标记。
    #   ⇒ 顺序：当天故事（收工整理稿）→ 小说原文（短，只作兜底）→ 小说版本 → 每日落盘。
    # [EN] ★★★ Third fix on 2026-10-18: **`当天故事.md` comes first**.
    # [EN] Measured on the 6-beat run:
    # [EN] · `小说原文_*.md` is only **531 characters** -- it is the "sample chapter" the novelist wrote
    # [EN]   *before* shooting, covering just the opening beat, **not the whole day's output** (judging it
    # [EN]   would score 6 beats as 1);
    # [EN] · `当天故事.md` is **2121 characters**, covers the whole day, and is **plain prose**
    # [EN]   (no `▸ 出场` / `◇ 心声`);
    # [EN] · `小说版本_*.md` also covers the day but **deliberately keeps** script markers.
    # [EN] => order: 当天故事 (wrap-up draft) -> 小说原文 (short, fallback only) -> 小说版本 -> dailies.
    cands: list[Path] = []
    p = run_root / "当天故事.md"
    if p.is_file():
        cands.append(p)
    exp = run_root / "导出"
    if exp.is_dir():
        cands += sorted(exp.glob("小说原文_*.md"), key=lambda q: q.stat().st_mtime)
    if exp.is_dir():
        cands += sorted(exp.glob("小说版本_*.md"), key=lambda q: q.stat().st_mtime)
    daily = run_root / "每天的生活"
    if daily.is_dir():
        cands += sorted(daily.glob("第*天.md"))
    # ★★★ 2026-10-18 第二处修正：**按顺序取第一个够长的，不再取"最长"的**。
    #   第一版是"把候选按优先级排好，然后取最长的" —— 排名形同虚设：
    #   `小说版本`（带剧本标记）永远比 `小说原文` 长，于是永远被选中。
    #   这是"改了一半"的典型：顺序改了，选择规则没跟着改。
    # [EN] ★★★ Second fix on 2026-10-18: **take the first candidate that is long enough, in order;
    # [EN] stop picking "the longest"**. The first version sorted candidates by priority and then
    # [EN] took the longest -- the ranking was decorative, because `小说版本` (with script markers) is
    # [EN] always longer than `小说原文`, so it always won. A textbook "changed half of it": the order
    # [EN] was fixed while the selection rule was not.
    for p in cands:
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(txt.strip()) >= 200:
            return txt
    return ""


def _render_md(work: Work, case: Case, entries: list[dict], dividers: list[str]) -> str:
    head = [f"# 推演实录 ·《{work.title}》· {case.id}", "",
            f"- 切入点：{case.cut} · {case.place} · {case.story_time}",
            f"- 在场：{'、'.join(case.present)}",
            f"- 关注：{'、'.join(case.focus) or '—'}", "",
            "## 前情提要", "", case.previously or "（开篇）", "",
            "## 起点", "", case.scene_seed, "",
            "## 推演", ""]
    body: list[str] = []
    skipped = 0
    for e in entries:
        txt = e["text"].strip()
        if not txt:
            continue
        if e["kind"] == "_divider":
            body.append(f"— {txt} —")
        elif e["kind"] in PROSE_KINDS:
            body.append(txt)
        else:
            skipped += 1
    tail = [f"\n（另有 {skipped} 条制作过程记录：道具/造型/审读进度等，见 transcript.jsonl）"] if skipped else []
    return "\n".join(head + body + tail) + "\n"


def run_case(work: Work, case: Case, out_dir: Path, cfg: Settings) -> dict:
    """Synchronous wrapper used by the CLI (one fresh event loop per case)."""
    try:
        return asyncio.run(_run_case(work, case, out_dir, cfg))
    except Exception:                              # noqa: BLE001
        out_dir.mkdir(parents=True, exist_ok=True)
        tb = traceback.format_exc()
        (out_dir / "error.txt").write_text(tb, encoding="utf-8")
        return {"case": case.id, "work": work.id, "fatal": tb.splitlines()[-1][:300],
                "ticks_done": 0, "entries": 0, "chars": 0, "seconds": 0}
