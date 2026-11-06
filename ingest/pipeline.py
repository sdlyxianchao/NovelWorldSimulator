# -*- coding: utf-8 -*-
"""摄取管线编排（设计稿 §3.1）：扫描→提取→类型→风格→进度表→开局→冻结。

完整流程：
  scan_project → extract_settings → detect_genre → extract_style
  → build_progress_table → align_with_text → propose_opening
  → 冻结进 本地设定集/

供 TUI 导入向导（§11.8）和首运行向导（§11.5）调用。

English:
Ingestion pipeline orchestration (design doc §3.1): scan → extract → genre → style → progress
table → opening → freeze.
Full flow:
  scan_project → extract_settings → detect_genre → extract_style
  → build_progress_table → align_with_text → propose_opening
Called by the TUI import wizard (§11.8) and the first-run wizard (§11.5).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from ingest.scanner import scan_project, FileItem
from ingest.extractor import extract_settings
from ingest import extractor
from ingest.genre import detect_genre
from ingest.style import extract_style
from ingest.progress import (
    build_progress_table, align_with_text, split_chapters,
    write_story_so_far, suggest_start_point, ProgressNode,
    parse_length_plan, is_chapter_plan, slice_chapter_plan,
    attach_chapter_plan, chapter_no,
)
from ingest.opening import propose_opening
from util.io import atomic_write_text, ensure_dir
from util.text import now_str
from config import CFG
from llm import models as MODELS

_LOG = __import__("logging").getLogger("nws.ingest")

# 阶段表：(stage_id, 中文阶段名, 完成时的进度百分比)
# GUI 直接消费这张表渲染进度条；中文名未走 i18n，GUI 侧可自行翻译。
# [EN] Stage table: (stage_id, Chinese stage name, progress percentage on completion)
# [EN] GUI directly consumes this table to render the progress bar; the Chinese names do not go through
# [EN] i18n, so the GUI side can translate them on its own.
STAGES: list[tuple[str, str, float]] = [
    ("scan",     "扫描文件夹",       0.05),
    ("read",     "读取与分章",       0.12),
    # 本地阶段到此为止；下一步开始就要联网花钱了 —— 所以在这里停一下取同意。
    # [EN] Local stages end here; the next step starts needing network and money -- so stop here and get
    # [EN] consent.
    ("consent",  "确认是否交给 AI",  0.13),
    ("extract",  "提取人物与世界观", 0.40),
    ("extract_done", "提取人物与世界观", 0.44),
    ("genre",    "判定故事类型",     0.48),
    ("style",    "生成风格卡",       0.56),
    ("progress", "构建故事进度表",   0.66),
    ("align",    "正文与进度对齐",   0.76),
    ("start",    "推断起始点",       0.82),
    ("opening",  "推演开局方案",     0.90),
    ("tier",     "评估资料档位",     0.94),
    ("freeze",   "冻结本地设定集",   0.99),
    ("done",     "摄取完成",         1.00),
]
_STAGE_LABEL: dict[str, str] = {s[0]: s[1] for s in STAGES}
_STAGE_PCT: dict[str, float] = {s[0]: s[2] for s in STAGES}

# **有条件才出现的阶段**：`consent` 只在传了 `gate` 时才会触发
# （没有 gate 的调用方 —— 比如测试 —— 不会经过"取同意"这一步）。
# 断言"阶段齐全"的地方要用 `required_stages()` 而不是直接拿 STAGES。
# [EN] **Stage that only appears conditionally**: `consent` only triggers when `gate` is passed
# [EN] (callers without gate -- e.g. tests -- will not go through the "get consent" step).
# [EN] Places that assert "all stages present" should use `required_stages()` instead of taking STAGES
# [EN] directly.
OPTIONAL_STAGES: set[str] = {"consent"}


def required_stages(has_gate: bool = False) -> set[str]:
    """一次运行**应该**触发哪些阶段（无 gate 时不算 `consent`）。
        English:
    Which stages **should** fire in a single run (without a gate, `consent` does not count).
    """
    ids = {s[0] for s in STAGES}
    return ids if has_gate else ids - OPTIONAL_STAGES


async def _emit(on_stage: Callable | None, stage_id: str, extra: str = "") -> None:
    """触发进度回调；兼容同步/异步回调，回调异常不打断管线。
        English:
    Fire progress callbacks; supports both sync/async callbacks, and a callback exception does not
    interrupt the pipeline.
    """
    if not on_stage:
        return
    label = _STAGE_LABEL.get(stage_id, stage_id)
    pct = _STAGE_PCT.get(stage_id, 0.0)
    try:
        res = on_stage(stage_id, label, pct, extra)
        if asyncio.iscoroutine(res):
            await res
    except Exception as e:   # noqa: BLE001 —— 进度展示失败不该影响摄取本身
    # [EN] noqa: BLE001 -- progress display failure should not affect ingestion itself
        _LOG.warning("进度回调失败 (%s): %s", stage_id, e)


@dataclass
class IngestResult:
    """一次完整摄取的全部产物。
        English:
    All artifacts of one complete ingestion.
    """
    items: list[FileItem]
    settings: dict[str, Any]       # 人物/世界观/地点/关系/伏笔/剧情参考线
    genre: dict[str, Any]          # 类型卡
    style: dict[str, Any]          # 风格卡
    nodes: list[ProgressNode]      # 故事进度表
    alignment: dict[str, Any]      # 正文对齐结果
    opening_candidates: list[dict] # 开局候选
    start_point: str               # 建议起始节点 ID
    tier: str                      # 评档：青铜/白银/黄金
    missing_for_gold: list[str]    # 黄金档缺项
    # [EN] Characters / worldbuilding / locations / relationships / foreshadowing / plot reference lines
    # [EN] Genre card
    # [EN] Style card
    # [EN] Story progress table
    # [EN] Main text alignment result
    # [EN] Opening candidates
    # [EN] Suggested starting node ID
    # [EN] Rating: Bronze / Silver / Gold
    # [EN] Gold tier missing items


class IngestDeclined(Exception):
    """作者在「交给 AI 之前」的确认里选择了不同意 —— 摄取中止，不是错误。
        English:
    The author chose disagree in the "before handing to AI" confirmation — ingestion aborts, not an
    error.
    """


# ══════════════════════════════════════════════════════════════════════
#  正文通道装配（拆章 → 按章号排序 → 拼正文）
# [EN] Body-text channel assembly (split chapters -> sort by chapter number -> concatenate)
# ══════════════════════════════════════════════════════════════════════
def assemble_body_chapters(items) -> tuple[dict[str, str], str]:
    """正文通道装配。返回 `(chapters, novel_text)`。

    ★★★ 2026-10-27 抽成独立函数（原来它是 `run_ingest` 里的一大段，**没法单独测**）：
      「正文按章号排序」这道闸必须能被单独测、也能被变异法打断 ——
      判据里已经有一支专测它（`tools/verify_ingest_scan.py` 的 A10 组）。

    ★★ 为什么**必须按章号排序**（不按文件系统顺序）：
      以前这里直接按 `items` 顺序拼，于是：
        ① 「文风样本＝前 4000 字」会**跨章断掉** ——
           Windows/NTFS 下 `rglob` 返回「第一章 → 第三章 → 第二章」
           （同一前缀的汉字按码位排：一 U+4E00 < 三 U+4E09 < 二 U+4E8C），
           实测「第一章 夜客」2680 字后面紧跟的是「第三章 灯让」的开头；
        ② 「正文对齐」喂给模型的章节顺序也是乱的，它按顺序列「对齐」，
           前情提要跟着乱。
      ⇒ 拆完之后**按章号重排**，认不出章号的排最后（不猜）。

    ⚠ 排序只动**正文这一路**：其它类别仍走「按重要性排」那套（见 `extractor`）。
    ⚠ 有文件拆不出章节时，`novel_text` 退回**按文件原样拼**，
      别把「拆不出」变成「少一截」。
    ⚠ **一个正文文件都没有时返回 `("", "")`** ——
      以前 `novel_text` 只在 `if chapters:` 分支里赋值，
      于是「只给设定集、不给正文」的项目会在同意门那里 **NameError**（潜伏 bug）。

        English:
    Body-text channel assembly. Returns `(chapters, novel_text)`.
    ★★★ 2026-10-27 extracted into its own function (it used to be a big block inside `run_ingest`
    and **could not be tested on its own**):
      the "sort body text by chapter number" gate has to be testable on its own, and has to be
      breakable by the mutation method -- there is a criterion dedicated to it (group A10 of
      `tools/verify_ingest_scan.py`).
    ★★ Why the sort is **mandatory** (file-system order is not chapter order):
      (1) the "style sample = first 4000 chars" would **break across chapters** ——
          on Windows/NTFS `rglob` returns "chapter 1 -> chapter 3 -> chapter 2";
      (2) the chapter order handed to the alignment model was scrambled too.
    ⚠ When **no** body-text file exists it returns `("", "")` -- previously `novel_text` was only
      assigned inside the `if chapters:` branch, so a project with settings but no body text blew
      up with a NameError at the consent gate (latent bug).
    """
    chapters: dict[str, str] = {}
    _novel_items = [it for it in items
                    if getattr(it, 'category', '') == "正文" and getattr(it, 'content', '')]
    _all_split = True
    for it in _novel_items:
        _parts = split_chapters(it.content)
        if set(_parts.keys()) == {"正文"}:
            # 拆不出章节标题的文件：以前一律塞进同一个键 "正文"，
            # **后一个文件把前一个整个盖掉**（`progress.py` 里有这段历史）。
            # ⇒ 这里用文件名当键，别让它把别人的内容吞了。
            _all_split = False
            _k = it.name
            _n = 2
            while _k in chapters:
                _k = f"{it.name}#{_n}"
                _n += 1
            chapters[_k] = it.content
        else:
            for _t, _b in _parts.items():
                _k = _t
                _n = 2
                while _k in chapters:
                    _k = f"{_t}#{_n}"
                    _n += 1
                chapters[_k] = _b
    if not chapters:
        return {}, ""
    _ordered = sorted(chapters.items(), key=lambda kv: (chapter_no(kv[0]), kv[0]))
    chapters = dict(_ordered)
    novel_text = ("\n".join(_body for _t, _body in _ordered) if _all_split
                  else "\n".join(it.content for it in _novel_items))
    return chapters, novel_text


@MODELS.agent('ingest')
async def run_ingest(project_path: Path, *, settings_dir: Path | None = None,
                     on_stage: Callable | None = None,
                     gate: Callable | None = None) -> IngestResult:
    """运行完整摄取管线。settings_dir = 冻结输出目录。

    on_stage(stage_id, label, pct, extra)：每个阶段开始时回调一次，
    GUI 用它推进进度条 + 打日志；sync / async 均可。

    gate(brief) -> bool：**可选的「同意门」**，在本地阶段（扫描/读取/分章）做完、
    第一次调用 LLM **之前**触发一次。brief 是 `ingest.preview.build_brief()` 的
    结果（传进来了什么、预计发出去多少 token、大概多少钱）。返回 False 表示
    作者不同意，管线抛 `IngestDeclined` 中止 —— **一次 LLM 请求都不发**。
    
        English:
    Run the full ingestion pipeline. settings_dir = freeze output directory.
        on_stage(stage_id, label, pct, extra): callback fired once at the start of each stage,
        the GUI uses it to advance the progress bar + write logs; sync / async both fine.
        gate(brief) -> bool: **optional "consent gate"**, fired once after the local stages (scan/read/chapter split) are done
        and **before** the first LLM call. brief is the result of `ingest.preview.build_brief()`
        (what was passed in, roughly how many tokens will be sent out, roughly how much it costs). Returning False means
        the author disagrees, the pipeline raises `IngestDeclined` and aborts — **not a single LLM request is sent**.
    """
    t0 = time.time()
    # ── 1. 扫描 ──（**每次都是全量**，理由见 `ingest/scanner.scan_project` 的注释：
    #   曾经按 `.ingest_cache.json` 跳过"未变更"的文件，结果第二次开卷只改了
    #   一个文件时，模型就只看到那一个文件、设定集被做残 —— 2026-10-06 用户报的
    #   「只读一个文件」就是它。文件读取是本机的、不要钱，别在这上面省。）
    # [EN] ── 1. Scan ── (**always full scan**, see the comment in `ingest/scanner.scan_project` for why:
    # [EN] Previously it skipped "unchanged" files based on `.ingest_cache.json`, and as a result, on the
    # [EN] second open, when only
    # [EN] one file was changed, the model only saw that one file and the settings collection was left
    # [EN] crippled — reported by the user on 2026-10-06.
    # [EN] "Only reads one file" was the cause. Reading files is local and free, don't cut corners here.)
    await _emit(on_stage, "scan", str(project_path))
    items = scan_project(project_path)
    n_files = len([it for it in items if it.content])
    await _emit(on_stage, "read", f"{len(items)} 个文件（{n_files} 个有内容）")

    # ── 2. 拼接全文 ──
    # 这三份文本在下面会被**真的发出去**，所以先在本地拼好：
    # 既是后续 LLM 步骤的入参，也是"同意门"要摊给作者看的东西（同一份，不会对不上）。
    # [EN] ── 2. Concatenate full text ──
    # [EN] These three texts will be **actually sent out** below, so assemble them locally first:
    # [EN] They are both the input to subsequent LLM steps and what the "consent gate" shows to the author
    # [EN] (the same copy, so they can't mismatch).
    full_text = "\n\n".join(f"【{it.category}】{it.name}\n{it.content}"
                            for it in items if it.content)
    chapters, novel_text = assemble_body_chapters(items)
    outline_text = "\n".join(it.content for it in items
                             if it.category == "大纲" and it.content)


    # ── 2.5 交给 AI 之前先说清楚（同意门）──
    # 这一步**一分钱不花、也不联网**：只是把"传进来了什么"和"预计要发出去多少"
    # 摊开，让作者对两件事（正文外发、token 开销）分别表态。
    # [EN] ── 2.5 Clarify before handing to AI (consent gate) ──
    # [EN] This step **costs nothing and does not go online**: it just lays out "what was brought in" and
    # [EN] "how much is expected to be sent out"
    # [EN] so the author can separately consent to two things (sending the body text externally, token
    # [EN] cost).
    if gate is not None:
        await _emit(on_stage, "consent")
        try:
            from .preview import brief_from_cfg
            brief = brief_from_cfg(items, full_text=full_text,
                                   novel_text=novel_text,
                                   outline_text=outline_text, chapters=chapters)
            res = gate(brief)
            if asyncio.iscoroutine(res):
                res = await res
        except IngestDeclined:
            raise
        except Exception as e:                # noqa: BLE001
            # **失败就"不放行"**（fail closed）：这是隐私闸门，
            # 界面出错时悄悄放行等于把作者的正文发了出去却没人同意过。
            # 宁可中止并说清原因，让作者自己决定要不要再试一次。
            # [EN] **Fail closed on failure**: this is a privacy gate,
            # [EN] silently letting it through when the UI errors means the author's body text was sent without
            # [EN] anyone agreeing.
            # [EN] Better to abort and explain why, letting the author decide whether to retry.
            _LOG.exception("同意门回调失败，已中止（未发送任何内容）")
            raise IngestDeclined(f"确认环节出错，已中止：{e}") from e
        if not res:
            _LOG.info("作者在同意门选择中止，未调用任何 LLM")
            raise IngestDeclined("未同意把内容交给大模型")

    # ── 3. LLM 提取设定 ──
    # [EN] ── 3. LLM extraction of settings ──
    await _emit(on_stage, "extract")
    settings = await extract_settings(items, project_path.name)
    # ★ 「提取设定」这一步攒下的提示（输出被截断、抢救回来多少、彻底没解析出来…）
    #   必须**折进这一行日志**才算数：它只写在文件日志里的话，用户在这个对话框里
    #   什么都看不到，还是会以为"设定好像不太对"。2026-10-06 就是这么丢掉整份设定的。
    # [EN] ★ Prompts accumulated in the "extract settings" step (output truncated, how much was salvaged,
    # [EN] what completely failed to parse...)
    # [EN] must be **folded into this log line** to count: if they are only written to the file log, the
    # [EN] user in this dialog
    # [EN] sees nothing and still thinks "the settings seem a bit off". This is exactly how the entire
    # [EN] settings collection was lost on 2026-10-06.
    extra = (f"人物 {len(settings.get('人物', []))} 位 · "
             f"地点 {len(settings.get('地点', []))} 处")
    try:
        _notes = extractor.take_notes()
    except Exception:                                       # noqa: BLE001
        _notes = []
    if _notes:
        extra += " · ⚠ " + "；".join(_notes)
    await _emit(on_stage, "extract_done", extra)

    # ── 4. 类型判定 ──
    # [EN] ── 4. Type determination ──
    await _emit(on_stage, "genre")
    genre = await detect_genre(full_text, manual=CFG.s("STORY_GENRE"))

    # ── 5. 风格卡 ──
    # [EN] ── 5. Style card ──
    await _emit(on_stage, "style")
    style = await extract_style(novel_text or full_text)

    # ── 6. 故事进度表 ──
    # [EN] ── 6. Story progress table ──
    await _emit(on_stage, "progress")
    if not outline_text:
        outline_text = settings.get("剧情参考线", "")
    nodes = await build_progress_table(outline_text)
    # ★★ 2026-10-27：**章纲按站挂到节点上**（章一级施工图）。
    #   它一直躺在 `04_大纲/章纲.md` 里，而建节点只取站表、正文通道只读正文 ——
    #   **32 章施工图一个字都没进过程序**。现在按站切好挂到节点，推演时
    #   **只喂当前站那几章**（`director/day_plan._nodes_text`），当参考不当清单。
    # [EN] ★★ 2026-10-27: **attach the chapter plan station by station**. It sat in
    # [EN] `04_大纲/章纲.md` while node building only read the station table and the body-text path
    # only read body text -- **not one char of the 32-chapter blueprint ever reached the program**.
    # [EN] Now it is sliced per station and attached; the run feeds **only the current station's
    # [EN] chapters** (`director/day_plan._nodes_text`), as reference, not as a checklist.
    _plan_blocks: list = []
    for it in items:
        if it.category == "大纲" and is_chapter_plan(it.name) and it.content:
            _plan_blocks.extend(slice_chapter_plan(it.content))
    if _plan_blocks:
        _n_attached = attach_chapter_plan(nodes, _plan_blocks)
        _LOG.info("章纲：切出 %d 站，挂上 %d 个节点",
                  len(_plan_blocks), _n_attached)
    # ★ 2026-10-27：**书级篇幅规划**（"全书几章 / 多少字"）。
    #   ⚠ 从**原始大纲文本**里读，不从节点表里读 —— 它是整本书的口径，
    #     而模型建节点表时不会把它带出来。
    # [EN] ★ 2026-10-27: the **book-level length plan** ("how many chapters / how many words for the
    # [EN] whole book"). ⚠ Parsed from the **raw outline text**, not from the node table -- it is a
    # [EN] whole-book measure and the model does not carry it into the nodes.
    length_plan = parse_length_plan(outline_text)

    # ── 7. 正文对齐 ──
    # [EN] ── 7. Body text alignment ──
    await _emit(on_stage, "align")
    alignment: dict[str, Any] = {"对齐": [], "已完成节点": [], "前情提要": ""}
    if chapters:
        alignment = await align_with_text(nodes, chapters)

    # ── 8. 起始点 ──
    # [EN] ── 8. Starting point ──
    await _emit(on_stage, "start")
    start_point = suggest_start_point(nodes, chapters)
    start_manual = CFG.s("STORY_START_POINT")
    if start_manual and start_manual != "auto":
        start_point = start_manual

    # ── 9. 开局方案 ──
    # [EN] ── 9. Opening plan ──
    await _emit(on_stage, "opening")
    start_node_name = ""
    for n in nodes:
        if n.id == start_point:
            start_node_name = n.name
            break
    opening_candidates = await propose_opening(settings, start_node_name)

    # ── 10. 评档 ──
    # [EN] ── 10. Rating ──
    await _emit(on_stage, "tier")
    tier, missing = _assess_tier(settings, items)

    # ── 11. 冻结 ──
    # [EN] ── 11. Freeze ──
    if settings_dir:
        await _emit(on_stage, "freeze", str(settings_dir))
        ensure_dir(settings_dir)
        _freeze(settings_dir, settings, genre, style, nodes, alignment,
                rules_text=collect_rules(items, settings),
                length_plan=length_plan)
        # ★ CP1（开卷时扫一遍，`COMPLIANCE_SCAN_ON_INGEST`）——
        #   **不新增阶段**：断言"阶段齐全"的地方比的是 `STAGES`，
        #   插一个新阶段会让所有既有验证脚本一起红（不值得）。
        #   ⚠ 放在**冻结之后**：冻结是"设定集的最终形态"，扫它才有意义；
        #   扫出来的问题写成 `<设定目录>/合规提示.md`，**不替作者删改**。
        # [EN] ★ CP1 (scan on open, `COMPLIANCE_SCAN_ON_INGEST`) —
        # [EN] **do not add a new stage**: places that assert "stages are complete" compare against `STAGES`,
        # [EN] inserting a new stage would make all existing validation scripts fail together (not worth it).
        # [EN] ⚠ Place it **after freeze**: freeze is "the final form of the settings collection", only then is
        # [EN] scanning it meaningful;
        # [EN] write found issues to `<settings dir>/compliance hints.md`, **do not delete or modify on the
        # [EN] author's behalf**.
        await _scan_ingest_compliance(settings_dir, settings)

        # ★ 三级底图（2026-10-08）：见 `ensure_atlas`。
        #   **不新增 STAGES 条目**（理由同上：断言"阶段齐全"的地方比的是
        #   `STAGES`，插一条会让所有既有验证脚本一起红）。
        #   ⚠ 放在**冻结之后**、与 CP1 一样：冻结是设定集的最终形态，
        #     `地点.yaml` 定下来才谈得上"照着它画图"。
        #   ⚠ 只在**传了 settings_dir** 时走这里；GUI 那条路走的是同步的
        #     `freeze_settings()`，所以它在 `finish_project` 里自己 await 一次
        #     （两条路都覆盖，见 `ensure_atlas` 的说明）。
        # [EN] ★ Three-level base map (2026-10-08): see `ensure_atlas`.
        # [EN] **Do not add a STAGES entry** (same reason as above: places that assert "stages are complete"
        # [EN] compare against
        # [EN] `STAGES`, inserting one would make all existing validation scripts fail together).
        # [EN] ⚠ Place it **after freeze**, same as CP1: freeze is the final form of the settings collection,
        # [EN] only once `地点.yaml` is settled can you talk about "drawing a map based on it".
        # [EN] ⚠ Only go through here when **settings_dir was passed**; the GUI path goes through the
        # [EN] synchronous
        # [EN] `freeze_settings()`, so it awaits once itself inside `finish_project`
        # [EN] (both paths are covered, see the description in `ensure_atlas`).
        def _atlas_note(msg: str) -> None:
            """借 `freeze` 这一格报一句。

            ⚠ 进度值取 `freeze` 自己的（0.99），**不要**手写 0.95 ——
              那会让进度条从 99% 往回退。
            ⚠ 只在"开始/结果"各报一次：每调一次 `on_stage` 界面就画一条分隔线。
            
                        English:
            Report via the `freeze` slot.
                        ⚠ The progress value uses `freeze`'s own (0.99), **do not** hardcode 0.95 ——
                          that would make the progress bar go backwards from 99%.
                        ⚠ Only report once each at "start/result": every call to `on_stage` draws a separator line in the UI.
            """
            if not on_stage:
                return
            try:
                on_stage("freeze", _STAGE_LABEL.get("freeze", "freeze"),
                         _STAGE_PCT.get("freeze", 0.99), msg)
            except Exception:                               # noqa: BLE001
                pass

        await ensure_atlas(settings_dir, settings, on_note=_atlas_note)

    elapsed = time.time() - t0
    _LOG.info("摄取完成：%.1fs，%d 文件，%d 人物，评档 %s（耗时 %.1fs）",
              elapsed, len(items), len(settings.get("人物", [])), tier, elapsed)
    await _emit(on_stage, "done", f"{tier}档 · 用时 {elapsed:.1f}s")
    return IngestResult(
        items=items, settings=settings, genre=genre, style=style,
        nodes=nodes, alignment=alignment, opening_candidates=opening_candidates,
        start_point=start_point, tier=tier, missing_for_gold=missing)


def _assess_tier(settings: dict, items: list[FileItem]) -> tuple[str, list[str]]:
    """§3.8 三档评估：青铜=能跑，白银=推荐，黄金=最佳。
        English:
    §3.8 three-tier evaluation: bronze = runs, silver = recommended, gold = best.
    """
    has_outline = bool(settings.get("剧情参考线"))
    has_chars = len(settings.get("人物", [])) >= 2
    has_novel = any(it.category == "正文" and it.content for it in items)
    has_secrets = any(p.get("秘密") for p in settings.get("人物", []))
    has_foreshadow = bool(settings.get("伏笔"))

    missing = []
    if not has_chars:
        missing.append("至少 2 个有姓名的人物")
    if not has_outline:
        missing.append("大纲/剧情参考线")
    if not has_secrets:
        missing.append("人物秘密与口癖")
    if not has_foreshadow:
        missing.append("伏笔清单（编号+埋设位置+预计回收）")
    if not has_novel:
        missing.append("正文（至少 1 章）")

    if has_outline and has_chars and has_secrets and has_foreshadow and has_novel:
        return "黄金", []
    if has_outline and has_chars:
        return "白银", missing
    return "青铜", missing


def collect_rules(items: list[FileItem], settings: dict) -> str:
    """汇集「顶级规则」正文。**原文直录优先**（2026-10-06 加）。

    作者写的规则有两条来源，优先级不同：

    ① **规则类文档**（文件名含 规则 / 铁律 / 守则 / 法则 / 戒律 / 准则 /
       禁忌 / rule…，见 `ingest/scanner._CATEGORY_RULES`）
       → **原文照录，一个字不改**。这是关键：规则是作者对故事的**硬约束**，
       每一条都可能是后文推演的判据（"谁动了更漏谁就得说清行踪"），
       交给模型概括会丢条件、改语气 —— 而概括出来的东西没法回溯核对。

    ② 没有规则类文档时，才用 AI 从普通设定文档里**归纳**出的「顶级规则」条目
       （兜底：规则散写在 `设定/世界观.md` 里也能被捞到）。

    ⚠ 两者都有时**只用 ①** —— 否则同一件事以两种措辞重复进 prompt，
    模型可能按"更像规则"的那份走，反而稀释了作者原话。
    
        English:
    Aggregate the body of "top-level rules". **Verbatim transcription takes priority** (added
    2026-10-06).
        Author-written rules have two sources, with different priority:
           禁忌 / rule…, see `ingest/scanner._CATEGORY_RULES`)
           → **transcribe verbatim, not a single character changed**. This is key: rules are the author's **hard constraints** on the story,
           each one may be the criterion for later inference ("whoever touched the water clock must account for their whereabouts"),
           summarizing them with a model loses conditions and changes tone — and summaries cannot be traced back for verification.
        ② Only when no rule-type document exists, use the "top-level rules" items **induced** by AI from ordinary setting documents
           (fallback: rules scattered in `设定/世界观.md` can also be picked up).
        ⚠ When both exist, **use ① only** — otherwise the same thing enters the prompt twice with different wording,
        and the model may follow the one that "looks more like a rule", diluting the author's original words.
    """
    blocks = [it.content.strip() for it in items
              if getattr(it, "category", "") == "规则" and (it.content or "").strip()]
    if blocks:
        return "\n\n".join(blocks)
    ai_rules = [str(r).strip() for r in (settings.get("顶级规则") or []) if str(r).strip()]
    if ai_rules:
        return "\n".join(f"- {r}" for r in ai_rules)
    return ""


async def ensure_atlas(settings_dir, settings, *, on_note=None) -> None:
    """生成**三级底图**（`MAP_ATLAS`）—— 见 `world/atlas.py` / `ingest/atlas.py`。

    用户 2026-10-08：「在开卷的时候把一些整体地图 局部地图(房屋附近 房屋内部)
    提前画好，需要的时候基于这些地图让美术加细节」。

    ★ 为什么是**公开**函数、并且要由调用方**单独调**一次：
      GUI 的开卷流程走的是 `freeze_settings()`（**同步**），不是 `run_ingest()`
      （见 `gui/app_flet` 的 worker：`run_ingest(settings_dir=None)` 只做提取，
      落盘由 `finish_project` 里那次 `freeze_settings` 完成）。
      生成底图要 `await` LLM，塞不进同步的 freeze ——
      所以两条路都各调一次这个函数（`run_ingest` 里传了 `settings_dir` 时调，
      GUI 在 freeze 之后自己 await）。
      ⚠ 只挂其中一条的后果是"命令行有底图、界面上没有"，而且两边都不报错。

    ⚠ 三条都不许动：
      · 失败**不阻断**（底图不是生死线，推演照跑，只是每天现画）；
      · **依据没变不重画**（`same_basis()`）—— 重开卷或 AI 优化后重新冻结时，
        `地点.yaml` 没变就直接复用，省一次生成；
      · 每一层的成败都要**说出来**（`on_note`），"静默少一层"是最坏的失败形态。
    
        English:
    Generate the **three-level base map** (`MAP_ATLAS`) — see `world/atlas.py` / `ingest/atlas.py`.
        User 2026-10-08: "when opening the book, draw some overall maps and local maps (near the house, inside the house)
        in advance, and when needed have the artist add details based on these maps".
        ★ Why it is a **public** function and must be called **separately** once by the caller:
          The GUI's book-opening flow uses `freeze_settings()` (**synchronous**), not `run_ingest()`
          (see the worker in `gui/app_flet`: `run_ingest(settings_dir=None)` only does extraction,
          and writing to disk is done by that `freeze_settings` call inside `finish_project`).
          Generating the base map needs to `await` the LLM, which cannot fit into the synchronous freeze —
          so both paths each call this function once (called inside `run_ingest` when `settings_dir` is passed,
          and the GUI awaits it itself after freeze).
          ⚠ Attaching only one of them results in "base map on the command line, none in the interface", and neither side reports an error.
        ⚠ None of the three may be changed:
          · Failure **does not block** (the base map is not a life-or-death line, inference still runs, it is just drawn on the spot each day);
          · **Do not redraw if the basis has not changed** (`same_basis()`) — when reopening the book or re-freezing after AI optimization,
            if `地点.yaml` has not changed, reuse directly, saving one generation;
          · The success or failure of each layer must be **spoken out** (`on_note`), "silently missing a layer" is the worst failure mode.
    """
    if not CFG.b("MAP_ATLAS"):
        return
    try:
        from world import atlas as AT
        from ingest import atlas as IAT
        places = AT.place_names(settings)
        if not places:
            _LOG.info("底图：设定里没有地点，跳过")
            return
        old = AT.load(settings_dir)
        briefs = [AT.place_brief(settings, n) for n in places]
        if AT.same_basis(old, places, briefs):
            _LOG.info("底图：依据没变（还是那 %d 处），复用已有的", len(places))
            if on_note:
                on_note(f'底图沿用上次（还是那 {len(places)} 处地点）')
            return
        notes: list[str] = []
        got = await IAT.build_vector(settings_dir, settings,
                                     tokens=CFG.i("MAP_ATLAS_TOKENS"),
                                     on_note=notes.append)
        for n in notes:                     # 逐层细节进主日志（排障要看）
        # [EN] Per-layer details go to the main log (needed for troubleshooting)
            _LOG.info("底图：%s", n)
        if on_note:
            if got is None:
                on_note('底图没生成出来 —— 小地图退回"每天现画"')
            else:
                on_note(f'底图就绪：整体 {"有" if got.overview else "无"} · '
                        f'局部 {len(got.local)} 处 · 室内 {len(got.indoor)} 处')
    except Exception as e:                                  # noqa: BLE001
        _LOG.warning("底图生成失败（不影响摄取，退回每天现画）：%r", e)


async def _scan_ingest_compliance(settings_dir, settings) -> None:
    """开卷时的合规扫描（CP1，`COMPLIANCE_SCAN_ON_INGEST`）。

    扫的是**世界观 + 顶级规则 + 人物小传**这几段"会被反复喂给模型"的文字。
    结果是**提示**，不是裁决：写一张 `合规提示.md` 放在设定目录里，
    由作者决定改不改 —— **程序绝不替作者删设定**（那是作者的东西）。

    ⚠ 失败**不阻断摄取**：开卷是本地阶段，网络不通也要能继续；
    但要在日志里留一笔，别让人以为"扫过了、没问题"。
    
        English:
    Compliance scan at book opening (CP1, `COMPLIANCE_SCAN_ON_INGEST`).
        What is scanned is the **worldview + top-level rules + character bios** text that "gets fed to the model repeatedly".
        The result is a **hint**, not a verdict: write a `合规提示.md` and place it in the settings directory,
        let the author decide whether to change it — **the program never deletes settings on the author's behalf** (that is the author's stuff).
        ⚠ Failure **does not block ingestion**: book opening is a local stage, it must continue even if the network is down;
        But leave a note in the log, so people don't think it was "scanned, no problem".
    """
    if not CFG.b("COMPLIANCE_SCAN_ON_INGEST") or not CFG.b("COMPLIANCE_ENABLED"):
        return
    try:
        parts = [str(settings.get("worldview") or ""),
                 str(settings.get("rules") or "")]
        for p in (settings.get("people") or []):
            if isinstance(p, dict):
                parts.append(str(p.get("小传") or p.get("身份") or ""))
        text = "\n".join(x for x in parts if x.strip())
        if not text.strip():
            return
        from compliance.agent import ComplianceAgent
        import tempfile
        from store.db import DB
        db = DB(Path(tempfile.mkdtemp(prefix="nws_cp1_")) / "cp1.db")
        try:
            agent = ComplianceAgent(db)
            res = await agent.check(text, "CP1")
        finally:
            try:
                db.close()
            except Exception:                                   # noqa: BLE001
                pass
        if res.passed:
            _LOG.info("开卷合规扫描（CP1）：通过（%s）", res.reason)
            return
        out = settings_dir / "合规提示.md"
        out.write_text(
            f"# 合规提示（开卷扫描）\n\n"
            f"> 程序**没有改动**你的任何设定，这里只是把扫到的东西列出来，\n"
            f"> 改不改、怎么改，由你定。\n\n"
            f"- 级别：{res.level}\n- 建议处理：{res.action}\n"
            f"- 理由：{res.reason}\n"
            + (f"\n## 建议改写方向\n\n{res.rewritten}\n" if res.rewritten else ""),
            encoding="utf-8")
        _LOG.warning("开卷合规扫描（CP1）：%s / %s —— 已写 %s",
                     res.level, res.action, out.name)
    except Exception as e:                                      # noqa: BLE001
        _LOG.warning("开卷合规扫描失败（不影响摄取）：%r", e)


def _freeze(settings_dir: Path, settings: dict, genre: dict, style: dict,
            nodes: list[ProgressNode], alignment: dict,
            rules_text: str | None = None,
            length_plan: dict | None = None) -> None:
    """把摄取产物冻结进 本地设定集/。

    `rules_text` = 「顶级规则」的正文（见 `collect_rules`）。
    **默认 `None` = 不动已有的那份** —— 界面上的「AI 优化」改完设定后会再冻结
    一次（`freeze_settings`），那时手上没有扫描结果，不能把用户的规则覆盖成空。
    
        English:
        `rules_text` = the body of the "top-level rules" (see `collect_rules`).
        **Default `None` = leave the existing one untouched** — after the "AI 优化" in the UI modifies the settings, it will freeze again
        once (`freeze_settings`); at that point there are no scan results on hand, so the user's rules must not be overwritten with empty.
    """
    def _yaml(name: str, data: Any) -> None:
        atomic_write_text(settings_dir / name, yaml.dump(data, allow_unicode=True,
                                                        default_flow_style=False, sort_keys=False))

    _yaml("人物.yaml", settings.get("人物", []))
    _yaml("世界观.md", settings.get("世界观", ""))
    _yaml("地点.yaml", settings.get("地点", []))
    _yaml("关系.yaml", settings.get("关系", []))
    _yaml("伏笔与悬线.yaml", settings.get("伏笔", []))
    _yaml("剧情走向.md", settings.get("剧情参考线", ""))
    # ★ 细节层（2026-10-07）：器物 / 习俗 / 口头禅 / 小规矩 —— 单独存一份。
    #   以前它们被概括进 `世界观.md`（≤120 字）就没了，而"每天的故事多半由
    #   这些小设定推动"（用户原话）。见 `world/layers.py`。
    #   ⚠ 总是写（哪怕是空表）：文件在不在是"这一层有没有内容"的判据，
    #     缺文件与空表在装配层要分得开 —— 见 `sim/setup.load_settings`。
    # [EN] ★ Detail layer (2026-10-07): objects / customs / catchphrases / small rules — stored separately.
    # [EN] Previously they were summarized into `worldview.md` (≤120 characters) and lost, while "most of
    # [EN] the daily story is driven by
    # [EN] these small settings" (user's exact words). See `world/layers.py`.
    # [EN] ⚠ Always write (even an empty table): whether the file exists is the criterion for "whether this
    # [EN] layer has content",
    # [EN] missing files and empty tables must be distinguished at the assembly layer — see
    # [EN] `sim/setup.load_settings`.
    _yaml("细节设定.yaml", settings.get("细节", []))
    _yaml("类型卡.yaml", genre)
    _yaml("风格卡.yaml", style)
    # ⚠ 底图（`小世界地图.yaml`）**只在文件不存在时写占位**（2026-10-08 改）。
    #   原先是无条件覆盖成 `{"名称": "待生成", "地点": []}`，而底图是**在 freeze
    #   之后**生成的（见 `run_ingest` 里那一步）—— 无条件覆盖会把刚生成的底图
    #   清掉。这条与「AI 优化改完设定再冻结一次」那条路直接冲突：
    #   用户跑来把底图生成好了，随手优化一句设定 → 底图没了，而且**没有任何提示**。
    #   "删掉不生效 / 生成完又没了"是最难怀疑到的一类。
    # [EN] ⚠ The base map (`小世界地图.yaml`) **only writes a placeholder when the file does not exist**
    # [EN] (changed 2026-10-08).
    # [EN] freeze** (see that step in `run_ingest`) — unconditional overwriting would wipe out the
    # [EN] just-generated base map.
    # [EN] This directly conflicts with the path "AI optimization modifies settings and then freezes
    # [EN] again":
    # [EN] the user comes along, generates the base map, casually optimizes one sentence of settings → the
    # [EN] base map is gone, and **there is no warning at all**.
    # [EN] "Deletion doesn't take effect / it's gone again after generation" is the hardest kind to
    # [EN] suspect.
    _map_file = settings_dir / "小世界地图.yaml"
    if not _map_file.exists():
        _yaml("小世界地图.yaml", {"名称": "待生成", "地点": []})
    if rules_text is not None:
        # 空 = **这次扫描没找到规则**。此时把上一次留下的清掉 ——
        # 不然用户删掉 `顶级规则.md` 重新开卷，旧规则还躺在设定集里继续生效，
        # 而界面上一切正常（"删了不生效"是最难怀疑到的一种）。
        # [EN] Empty = **this scan found no rules**. In this case clear out what was left from last time —
        # [EN] otherwise the user deletes `顶级规则.md` and reopens, and the old rules are still sitting in the
        # [EN] settings collection taking effect,
        # [EN] while the UI shows everything is normal ("deletion doesn't take effect" is one of the hardest
        # [EN] kinds to suspect).
        rf = settings_dir / "顶级规则.md"
        if str(rules_text).strip():
            _yaml("顶级规则.md", rules_text)
        elif rf.exists():
            rf.unlink()

    # 进度表
    # [EN] Progress table
    nodes_data = {"节点": [n.to_dict() for n in nodes]}
    # ★ 2026-10-27：**书级篇幅规划**（总章数 / 总字数 / 每章字数）与节点表同处落盘。
    #   作者在大纲里写的"全书 8 万字、32 章"以前没有任何地方接得住（被当散文读掉），
    #   现在它跟着进度表一起进 `故事进度.yaml`，装配时由 `sim/setup` 换算成每天的目标字数。
    #   ⚠ 只在**真的读到**时才写这个键：没写就不出现，免得作者以为自己写过。
    # [EN] ★ 2026-10-27: the **book-level length plan** is persisted next to the node table. "80,000
    # [EN] words, 32 chapters" written in the outline used to land nowhere (read as prose); now it
    # [EN] rides into `故事进度.yaml` and `sim/setup` turns it into a per-day word target.
    # [EN] ⚠ The key appears only when actually present, so it never looks author-written.
    if length_plan and any(int(v or 0) > 0 for v in length_plan.values()):
        nodes_data["篇幅规划"] = {k: int(v) for k, v in length_plan.items()
                                 if int(v or 0) > 0}
    atomic_write_text(settings_dir / "故事进度.yaml",
                      yaml.dump(nodes_data, allow_unicode=True, default_flow_style=False))

    # 已发生故事线
    # [EN] Existing storylines
    if alignment.get("已完成节点"):
        write_story_so_far(settings_dir / "已发生故事线.md", alignment, nodes)

    # ★★★ 2026-10-28（用户：「导入故事的时候包含一部分之前故事的提要和之前故事的最后部分」）：
    #   **运行侧真正读的那份前情**。`已发生故事线.md` 只有 MCP 时间线服务在读，
    #   推演第一章的前情提要走的是 `opening_context`（剧情参考线「起」段）——
    #   也就是"故事从大纲哪里起头"，而不是"导入的故事停在哪里"。
    #   用户实测的症状正是这个：推演起点跟前情提要对不上、没从之前的故事接着来。
    #   ⇒ 有对齐结果时把前情+末段写进 `前情提要.md`，`sim/setup.load_settings`
    #     读成 `recap`，`_worldview_text` 拼成【前情提要】段，
    #     `opening_context` **优先取它** —— 一条链，运行侧/起笔对话框/导出三处共用。
    # [EN] ★★★ 2026-10-28 (user: "include the previous story's recap and its last part when
    # [EN] importing"): this is the recap file **the run actually reads**. 已发生故事线.md is only
    # [EN] consumed by the MCP timeline server; day-1 recap goes through `opening_context`
    # [EN] (the outline's "setup" clause) -- i.e. where the **outline** starts, not where the
    # [EN] imported story **stopped**. Exactly the user's symptom: start point mismatched the recap.
    # [EN] => When alignment exists, write recap + tail into 前情提要.md; load_settings reads it as
    # [EN] `recap`; _worldview_text composes the 【前情提要】 section; opening_context prefers it.
    _recap = str(alignment.get("前情提要") or '').strip()
    if _recap:
        _bits = [_recap]
        _tail_sum = str(alignment.get("前文末段") or '').strip()
        _tail_raw = str(alignment.get("前文末段原文") or '').strip()
        if _tail_sum:
            _bits.append(f"故事停在：{_tail_sum}")
        if _tail_raw:
            _bits.append(f"上一部结尾原句：{_tail_raw}")
        atomic_write_text(settings_dir / "前情提要.md", "\n\n".join(_bits) + "\n")


# 公开别名：GUI 在 AI 优化对话改完设定后需要重新冻结一次
# [EN] Public alias: after the GUI finishes revising settings via AI-optimized dialogue, it needs to
# [EN] freeze once more
freeze_settings = _freeze
# 公开别名：AI 补全过缺口之后要**重评一次档**（补了伏笔/秘密/大纲，档位可能就上去了）
# [EN] Public alias: after AI fills gaps, the tier must be **re-evaluated** (adding
# [EN] foreshadowing/secrets/outline may bump the tier up)
assess_tier = _assess_tier