# -*- coding: utf-8 -*-
"""产物导出（设计稿 §10）：故事文档、运行报告、写作指导、新设定建议、完整设定集。

三类导出：
1. storyline 故事文档（§10.2）：随时可调用，版本自增不覆盖。
2. 运行报告（§10.3，原名「运行小结」）：随时可调用；`AUTO_SUMMARY_ON_END` 控制结束是否自动。
3. 写作指导（§10.5，原名「大纲建议」）：随时可调用，版本自增不覆盖。

**world / db 都是可选的。** 这一点很要紧：
  · 循环自己跑的时候，手上有 `WorldState` 和 `DB`，事实取自对象；
  · 但界面上的「手动导出」**手上什么都没有**，只有一个运行文件夹
    （`RunLoop` 还没接进 GUI）。这时所有事实必须能从盘上读出来——
    靠 `export.novel_version.collect_facts()` 倒推。
  两条路都通，导出才不会因为"没有运行对象"而变成摆设。

English:
Artifact export (design doc §10): story document, run report, writing guide, new setting
suggestions, full setting compendium.
Three types of export:
1. storyline story document (§10.2): callable at any time, version auto-increments without overwriting.
2. Run report (§10.3, originally "Run Summary"): callable at any time; `AUTO_SUMMARY_ON_END` controls whether it's automatic on end.
3. Writing guide (§10.5, originally "Outline Suggestions"): callable at any time, version auto-increments without overwriting.
**world / db are both optional.** This point is important:
  · When the loop runs itself, it has `WorldState` and `DB` on hand, facts are taken from the objects;
  · But "Manual export" in the UI has **nothing on hand**, only a run folder
    (`RunLoop` is not yet hooked into the GUI). In this case all facts must be readable from disk——
    derived via `export.novel_version.collect_facts()`.
  Both paths work, so export won't become useless just because there's "no run object".
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import yaml

from llm.router import llm
from store.db import DB
from store.runfolder import RunFolder
from store.project import Project
from world.state import WorldState
from config import CFG
from util.io import atomic_write_text, ensure_dir
from util.text import now_str

from export import novel_version as NV

_LOG = __import__("logging").getLogger("nws.export")


def _next_version(run: RunFolder, stem: str) -> int:
    """导出物版本号自增（**不覆盖**旧的）。
        English:
    Exported artifact version auto-increments (**does not overwrite** the old one).
    """
    d = run.export_dir
    v = 1
    if d.exists():
        for p in d.glob(f"{stem}_v*.md"):
            m = re.search(r"_v(\d+)", p.name)
            if m:
                v = max(v, int(m.group(1)) + 1)
    return v


def _facts_block(facts: dict) -> str:
    """把落盘事实写成一段给 LLM 看的文字（world 不在时用它顶替）。
        English:
    Write the persisted facts as a passage of text for the LLM to read (used as a substitute when
    world is absent).
    """
    lines = [
        f"- 运行文件夹：{facts['run_name']}",
        f"- 已落盘天数：{facts['days']} 天（最后一第 {facts['last_day']} 天）",
        f"- 正文字数：约 {facts['chars']} 字",
        f"- 出场人物：{'、'.join(facts['cast']) or '（未记录）'}",
        f"- 关键事件卡：{len(facts['events'])} 张"
        + (f"（{'、'.join(facts['events'][:10])}…）" if facts['events'] else ""),
    ]
    cost = facts.get("cost") or {}
    if cost.get("calls"):
        lines.append(f"- LLM 调用：{cost['calls']} 次，"
                     f"输入 {cost['in']} token / 输出 {cost['out']} token")
    return "\n".join(lines)


def _events_lines(run: RunFolder, db: DB | None, n: int = 30) -> list[str]:
    """取最近事件：优先 DB，没有就从「关键事件/」卡片目录读。
        English:
    Get recent events: prefer DB, otherwise read from the "key events/" card directory.
    """
    if db is not None:
        try:
            return [f"- [{e.get('game_day', '?')}天] {e.get('content', '')}"
                    for e in db.recent_events(n)][:n]
        except Exception:
            pass
    out: list[str] = []
    if run.events_dir.exists():
        for p in sorted(run.events_dir.glob("*.md"))[-n:]:
            try:
                first = p.read_text(encoding="utf-8", errors="ignore").strip()
            except OSError:
                continue
            headline = next((ln.strip("# ").strip() for ln in first.splitlines()
                             if ln.strip()), p.stem)
            out.append(f"- [{p.stem}] {headline[:80]}")
    return out


# ── 审稿 pass（§2.4）────────────────────────────────────────────────
# [EN] ── Review pass (§2.4)────────────────────────────────────────────────
async def review_pass(text: str, context: str = "") -> dict:
    """审稿 pass：贴设定/贴风格/节奏三分制，低分重写一次。

    返回：{"分数": {"贴设定": 0.8, "贴风格": 0.7, "节奏": 0.6}, "总分": 0.7, "是否通过": True, "建议": "..."}
    
        English:
    Review pass: three-way scoring of setting adherence/style adherence/pacing, rewrite once on low
    score.
        Return: {"score": {"setting adherence": 0.8, "style adherence": 0.7, "pacing": 0.6}, "total score": 0.7, "passed": True, "suggestion": "..."}
    """
    if not CFG.b("REVIEW_PASS"):
        return {"分数": {}, "总分": 1.0, "是否通过": True, "建议": "审稿已关闭"}

    prompt = f"""请对以下文本进行审稿评估（小说世界模拟器）：

文本：
{text[:2000]}

{f'上下文：{context}' if context else ''}

请以 JSON 回答，给出三个维度的分数（0-1）和建议：
{{
  "贴设定": 0.8,  // 是否符合设定（人物性格、世界观、剧情逻辑）
  "贴风格": 0.7,  // 是否符合风格卡（句长、叙事距离、词汇偏好）
  "节奏": 0.6,    // 节奏是否合适（张力、紧凑度、信息密度）
  "建议": "改进建议"
}}

评分标准：
- 0.9-1.0: 优秀
- 0.7-0.8: 良好
- 0.5-0.6: 一般
- <0.5: 需要重写"""

    messages = [{"role": "user", "content": prompt}]
    try:
        raw = await llm.chat("cheap", messages, purpose="review", json_mode=True, temperature=0.2)
        from util.jsonio import extract_json
        result = extract_json(raw, {})

        scores = {
            "贴设定": result.get("贴设定", 0.5),
            "贴风格": result.get("贴风格", 0.5),
            "节奏": result.get("节奏", 0.5),
        }
        avg_score = sum(scores.values()) / len(scores)
        threshold = CFG.f("REVIEW_THRESHOLD")

        return {
            "分数": scores,
            "总分": avg_score,
            "是否通过": avg_score >= threshold,
            "建议": result.get("建议", ""),
        }
    except Exception as e:
        _LOG.warning("审稿 pass 失败: %s", e)
        return {"分数": {}, "总分": 0.5, "是否通过": True, "建议": "审稿失败，默认通过"}


async def generate_with_review(content_func, *args, **kwargs) -> tuple[str, dict]:
    """带审稿的生成：先生成，再审稿，低分重写一次。
        English:
    Generation with review: generate first, then review, rewrite once on low score.
    """
    # 第一次生成
    # [EN] First generation
    text = await content_func(*args, **kwargs)

    # 审稿
    # [EN] Review
    review = await review_pass(text)
    _LOG.info("审稿结果: 总分=%.2f, 通过=%s", review["总分"], review["是否通过"])

    # 如果不通过，重写一次
    # [EN] If it fails, rewrite once
    if not review["是否通过"]:
        _LOG.info("审稿未通过，重写一次...")
        text = await content_func(*args, **kwargs)
        review = await review_pass(text)
        _LOG.info("重写后审稿: 总分=%.2f, 通过=%s", review["总分"], review["是否通过"])

    return text, review


# ── 故事文档（storyline）────────────────────────────────────────────────
# [EN] ── Story document (storyline)────────────────────────────────────────────────
async def generate_storyline(run: RunFolder, world: WorldState | None = None,
                             db: DB | None = None) -> Path:
    """生成故事文档，版本自增不覆盖。
        English:
    Generate story document, version auto-increments without overwriting.
    """
    facts = NV.collect_facts(run)
    events_text = "\n".join(_events_lines(run, db, 30))
    if world is not None:
        nodes_text = "\n".join(f"- [{n.get('id','')}] {n.get('名称','')}: {n.get('概要','')}"
                               for n in world.progress_nodes)
        chars = "\n".join(f"- {n}: {p.identity}（{p.personality}）"
                          for n, p in list(world.people.items())[:8])
        days, node = world.game_day, world.current_node
    else:
        nodes_text = "（未载入进度表——从运行文件夹倒推）"
        chars = "、".join(facts["cast"]) or "（未记录）"
        days, node = facts["days"], "（未载入）"

    prompt = f"""请根据以下信息，生成一份故事线汇总文档（§10.2 格式）。

项目名：{run.project_dir.name}
故事天数：{days} 天
当前节点：{node}

进度节点：
{nodes_text}

最近事件：
{events_text or '（暂无）'}

人物：
{chars or '（暂无）'}

（落盘事实，供参考）
{_facts_block(facts)}

请按以下结构生成 Markdown：
一、故事线脉络（时间轴：节点×关键事件）
二、关键场景（场景卡）
三、精彩情节（摘录）
四、人物弧线
五、伏笔状态表
六、未选之路
七、可用素材清单

要求：读起来像可以当写作大纲用的完整文档。"""

    messages = [{"role": "user", "content": prompt}]
    model_key = CFG.s("STORY_DOC_MODEL")
    tier = "front" if model_key == "MODEL_FRONT" else "daily"
    text = await llm.chat(tier, messages, purpose="storyline", max_tokens=4000)

    # 版本自增
    # [EN] Version auto-increment
    v = 1
    while (run.storyline_dir / f"故事线汇总_v{v}.md").exists():
        v += 1
    path = run.storyline_dir / f"故事线汇总_v{v}.md"
    atomic_write_text(path, text)
    _LOG.info("故事文档生成: %s", path.name)
    return path


# ── 运行报告（原名「运行小结」）───────────────────────────────────────
# [EN] ── Run report (originally "Run Summary")───────────────────────────────────────
def overview_block(run: RunFolder, facts: dict, world: WorldState | None,
                   budget: dict | None, *, partial: bool = False) -> str:
    """第 1 节「运行概览」与账单——**由程序统计，不是模型推测**。

    先有硬数据再有分析：这样即使 LLM 调用失败（断网/超额），
    导出的报告仍然是一份有内容的东西，而不是一个空壳。
    
        English:
    Section 1 "Run Overview" and the bill——**computed by the program, not inferred by the model**.
        Hard data first, then analysis: this way even if the LLM call fails (network down/quota exceeded),
        the exported report is still something with content, not an empty shell.
    """
    lines = [f"# 运行报告 · {run.project_dir.name} · {run.root.name}", ""]
    if partial:
        lines += [f"> ⚠ **中途导出**：这是截至**第 {facts['last_day']} 天**的部分报告，"
                  "运行尚未结束。", "> 已纳入的部分是完整的，后面的还没有。", ""]

    mode = CFG.s("RUN_MODE")
    lines += ["## 1 运行概览", "",
              "| 项目 | 值 |", "|---|---|",
              f"| 运行模式 | {mode} |",
              f"| 已落盘天数 | {facts['days']} 天 |",
              f"| 最后一天 | 第 {facts['last_day']} 天 |",
              f"| 正文字数 | 约 {facts['chars']} 字 |",
              f"| 出场人物 | {'、'.join(facts['cast']) or '（未记录）'} |",
              f"| 关键事件卡 | {len(facts['events'])} 张 |"]
    if world is not None:
        lines += [f"| 当前节点 | {world.current_node} |",
                  f"| 张力 | {world.tension:.2f} |",
                  f"| 事件计数 | {world.event_count} |"]
    lines.append("")

    cost = budget or facts.get("cost") or {}
    if cost.get("calls"):
        lines += ["## 账单", "",
                  f"- LLM 调用 **{cost['calls']}** 次",
                  f"- 输入 **{cost['in']}** token ／ 输出 **{cost['out']}** token", ""]
        by_purpose = cost.get("by_purpose") or {}
        if by_purpose:
            lines += ["| 用途 | 次数 | 输入 | 输出 |", "|---|---|---|---|"]
            for k, v in sorted(by_purpose.items(), key=lambda x: -x[1]["calls"]):
                lines.append(f"| {k} | {v['calls']} | {v['in']} | {v['out']} |")
            lines.append("")
        by_model = cost.get("by_model") or {}
        if by_model:
            lines += ["| 模型 | 次数 | 输入 | 输出 |", "|---|---|---|---|"]
            for k, v in sorted(by_model.items(), key=lambda x: -x[1]["calls"]):
                lines.append(f"| {k} | {v['calls']} | {v['in']} | {v['out']} |")
            lines.append("")
    elif budget:
        lines += ["## 账单", "", f"```json\n{json.dumps(budget, ensure_ascii=False, indent=2)}\n```", ""]
    lines += crew_archive_block(run)
    return "\n".join(lines)


def crew_archive_block(run: RunFolder) -> list[str]:
    """第 1.5 节「剧组档案」—— 零成本，只读盘上已有的过程稿。

    为什么要有这一节（2026-10-07 审计）：剧组各职位的产出（宣发文案、场记报告、
    道具单、造型表、声音设计、语言审校、今日总结、剧组台账…）**以前没有任何出口**
    —— 它们只躺在运行文件夹里，导出物（小说版本 / 小说参考 / 运行报告 /
    写作指导）一份都不提它们。名册上写着"产出的去处是给人看的地方"，
    而"给人看的地方"就是这里。

    两条刻意的做法：
      · **零成本** —— 只读文件头，不调模型；报告本身仍然是"先有硬数据"。
      · **不复制正文** —— 只列「哪个文件 · 谁写的 · 头一句」。要读全文就打开那个文件
        （把它整段抄进报告会让报告变成第二个运行文件夹）。
    
        English:
    Section 1.5 "Crew Archive" —— zero cost, only reads existing process drafts on disk.
        Why this section exists (2026-10-07 audit): the outputs of each crew position (publicity copy, continuity report,
        prop list, styling sheet, sound design, language review, daily summary, crew ledger...) **previously had no outlet**
        —— they just lay in the run folder, and the exported artifacts (novel version / novel reference / run report /
        writing guide) mentioned none of them. The roster says "the destination of the output is the place for people to see",
        and "the place for people to see" is right here.
        Two deliberate approaches:
          · **Zero cost** —— only read file headers, don't call the model; the report itself is still "hard data first".
          · **Don't copy the body** —— only list "which file · who wrote it · first sentence". To read the full text, open that file
            (copying it wholesale into the report would turn the report into a second run folder).
    """
    from crew import roster as CR
    from crew import studio as CS

    pairs: list[tuple[str, str]] = [
        # ⚠ `FILE_LEDGER` 是**模块级**常量，而 `FILE_DAY_MAP` 挂在类上 ——
        #   两个都在 `crew/studio.py` 里，但一个在类外一个在类内，
        #   写成 `CS.Studio.FILE_LEDGER` 会 AttributeError（已实测踩过）。
        # [EN] ⚠ `FILE_LEDGER` is a **module-level** constant, while `FILE_DAY_MAP` is attached to the class ——
        # [EN] Both are in `crew/studio.py`, but one is outside the class and one is inside,
        # [EN] Writing `CS.Studio.FILE_LEDGER` will raise AttributeError (already encountered in practice).
        (str(getattr(CS, 'FILE_LEDGER', '剧组台账.md')), '剧组台账')]
    for key, rel in CS.Studio.ARTIFACT.items():
        if not rel:
            continue
        try:
            pairs.append((rel, CR.role(key).name))
        except Exception:                                        # noqa: BLE001
            pairs.append((rel, key))
    pairs.append((CS.Studio.FILE_DAY_MAP, '美术'))

    rows: list[str] = []
    seen: set[str] = set()
    for rel, who in pairs:
        if rel in seen:
            continue
        seen.add(rel)
        p = Path(run.root) / rel
        try:
            if not p.is_file():
                continue
            text = p.read_text(encoding='utf-8', errors='replace')
        except Exception:                                        # noqa: BLE001
            continue
        one = _first_line(text)
        rows.append(f'| {rel} | {who} | {one} |')
    out = ['## 1.5 剧组档案', '',
           '> 这一轮剧组各职位留下的过程稿（都在运行文件夹根目录）。'
           '它们是**过程档**，不参与正文装订。', '']
    if not rows:
        out += ['（这一轮没有留下剧组档案 —— 剧组可能整班关着。）', '']
        return out
    out += ['| 文件 | 谁写的 | 头一句 |', '|---|---|---|'] + rows + ['']
    return out


def _first_line(text: str, limit: int = 40) -> str:
    """取文件里**第一句有内容的话**（跳过 `#` 标题、`>` 引用行与列表项）。

    ⚠ 只跳过"列表记号 + 空格"（`- ` / `* `），**不能跳过所有以 `*` 开头的行** ——
      剧组的产物普遍写成 `**底噪**　檐水不断` 这种加粗开头，
      一律跳过的话整份文件会被判成"（空）"（第一版就是这么错的）。
    
        English:
    Take the **first sentence with content** in the file (skip `#` headings, `>` quote lines and
    list items).
        ⚠ Only skip "list marker + space" (`- ` / `* `), **do NOT skip all lines starting with `*`** ——
          skipping all of them would judge the entire file as "(empty)" (this is how the first version got it wrong).
    """
    for ln in str(text or '').splitlines():
        s = ' '.join(ln.split()).strip()
        if not s or s.startswith(('#', '>', '|')):
            continue
        if s.startswith('- ') or s.startswith('* ') or s.startswith('+ '):
            continue
        return s[:limit] + ('…' if len(s) > limit else '')
    return '（空）'


def storyboard_archive_block(run: RunFolder) -> str:
    """第 N 节「分镜脚本」—— 零成本，只读盘上 `第NNN天_分镜脚本.md` 的头信息。

    和 `crew_archive_block` 同源思路：只列「哪一天 · 几镜 · 文件」，不抄正文
    （抄全文会让报告变成第二个运行文件夹）。分镜师产出的镜头清单因此进了导出物，
    不再躺在运行文件夹里没人理（P2，2026-10-15）。

        English:
    Section "Storyboard" -- zero cost, only lists `第NNN天_分镜脚本.md` headers.
    """
    d = getattr(run, 'daily_dir', None)
    if d is None or not d.exists():
        return ''
    files = sorted(d.glob('第*天_分镜脚本.md'))
    if not files:
        return ''
    lines = ["## 分镜脚本（分镜师产出）", "",
             "> 由「分镜师」角色产出，见各 `第NNN天_分镜脚本.md`。"]
    for f in files:
        day = f.stem.split('_')[0]
        n = 0
        try:
            for ln in f.read_text(encoding='utf-8').splitlines():
                _s = ln.strip()
                if _s.startswith('|') and len(_s) > 1:
                    _cell = _s[1:].strip()
                    if _cell and _cell[0].isdigit():
                        n += 1
        except Exception:                                # noqa: BLE001
            n = 0
        lines.append(f"- {day}：{n} 镜（见 `{f.name}`）")
    lines.append("")
    return "\n".join(lines) + "\n"


async def generate_run_summary(run: RunFolder, world: WorldState | None = None,
                               db: DB | None = None, ledger_cost: dict | None = None,
                               *, partial: bool = False, upto_day: int | None = None) -> Path:
    """生成运行报告（§10.3），版本自增不覆盖。

    第 1 节与账单由程序统计（`overview_block`），模型只负责后面的分析章节——
    所以**没有任何 LLM 可用时，报告依然出得来**。
    
        English:
    Generate run report (§10.3), version auto-increments without overwriting.
        Section 1 and the bill are computed by the program (`overview_block`), the model only handles the later analysis sections——
        so **when no LLM is available, the report can still be produced**.
    """
    facts = NV.collect_facts(run)
    events_text = "\n".join(_events_lines(run, db, 20))
    if world is not None:
        stats = (f"- 故事天数：{world.game_day}\n- 事件数：{world.event_count}\n"
                 f"- 当前节点：{world.current_node}\n- 张力：{world.tension:.2f}\n"
                 f"- 人物：{', '.join(world.people.keys())}")
    else:
        stats = _facts_block(facts)

    prompt = f"""请根据以下信息生成一份运行报告（§10.3 格式）。
**第 1 节「运行概览」与「账单」已经由程序写好，你不要重复写这两节。**

项目：{run.project_dir.name}
模式：{CFG.s('RUN_MODE')}

{stats}

关键事件：
{events_text or '（暂无）'}

请从第 2 节开始，按以下结构生成 Markdown（一节都不要漏）：
## 2 本次故事线
## 3 关键情节
## 4 重要场景
## 5 精彩片段
## 6 人物弧线与表现
## 7 设定与框架优化建议
## 8 后续故事发展建议
## 9 新设定建议
## 10 未选之路

请把优化建议和后续发展写得具体、可操作。若本次运行尚未跑完，属于正常情况，照实写即可。"""

    messages = [{"role": "user", "content": prompt}]
    try:
        body = await llm.chat("front", messages, purpose="summary", max_tokens=4000)
    except Exception as e:
        _LOG.warning("运行报告的分析章节生成失败，只留统计部分: %s", e)
        body = "_（分析章节生成失败，仅保留上面的程序统计部分。可稍后重跑导出。）_"

    head = overview_block(run, facts, world, ledger_cost, partial=partial)
    text = head.rstrip() + "\n\n" + (body or "").strip() + "\n\n" \
        + storyboard_archive_block(run)

    ensure_dir(run.export_dir)
    v = _next_version(run, "运行报告")
    path = run.export_dir / f"运行报告_v{v}.md"
    atomic_write_text(path, text)
    # 设计稿 §10.1 的固定入口保持可用：始终指向最新一份
    # [EN] The fixed entry in design doc §10.1 stays available: always points to the latest one
    atomic_write_text(run.run_summary_path, text)
    _LOG.info("运行报告生成: %s", path.name)
    return path


# ── 写作指导（原名「大纲建议」）───────────────────────────────────────
# [EN] ── Writing guide (originally "Outline Suggestions")───────────────────────────────────────
async def generate_outline(run: RunFolder, world: WorldState | None = None,
                           db: DB | None = None, *, partial: bool = False) -> Path:
    """生成推演后的写作指导（§10.5），版本自增不覆盖。
        English:
    Generate the post-simulation writing guide (§10.5), version auto-increments without overwriting.
    """
    facts = NV.collect_facts(run)
    if world is not None:
        nodes_text = "\n".join(
            f"- [{n.get('id','')}] {n.get('名称','')}: {n.get('概要','')}"
            f"（判据：{n.get('完成判据','')}）" for n in world.progress_nodes)
    else:
        nodes_text = "（未载入进度表——请按落盘素材给出建议）"
    events_text = "\n".join(_events_lines(run, db, 15))

    scope = ""
    if partial:
        scope = (f"\n**注意：本次推演尚未跑完，只到第 {facts['last_day']} 天。**"
                 "请按「已经推演出来的部分」给建议，后续节点按目前走向推测即可。\n")

    prompt = f"""请根据以下信息生成一份写作指导（§10.5 格式，可直接当写作大纲用）。
{scope}
项目：{run.project_dir.name}

原始进度节点：
{nodes_text}

模拟中发生的事件：
{events_text or '（暂无）'}

（落盘事实，供参考）
{_facts_block(facts)}

请按以下结构生成 Markdown：
一、节点对照表（原计划→实际发生→建议改写）
二、新增支线
三、伏笔更新
四、后续节点建议
五、人物弧线大纲

请让建议可直接当作写作大纲使用。"""

    messages = [{"role": "user", "content": prompt}]
    text = await llm.chat("front", messages, purpose="outline", max_tokens=3000)

    ensure_dir(run.export_dir)
    v = _next_version(run, "写作指导")
    path = run.export_dir / f"写作指导_v{v}.md"
    atomic_write_text(path, text)
    atomic_write_text(run.outline_path, text)      # 设计稿 §10.1 的固定入口
    # [EN] Fixed entry in design doc §10.1
    _LOG.info("写作指导生成: %s", path.name)
    return path


# ── 完整设定集导出 ─────────────────────────────────────────────────
# [EN] ── Full setting compendium export ────────────────────────────────────────────────
def export_project_settings(project: Project, run: RunFolder | None = None) -> Path:
    """导出项目级完整设定集（§10.7）：把设定集/ 打包成可导入的格式。
        English:
    Export the project-level full setting compendium (§10.7): package setting compendium/ into an
    importable format.
    """
    export_dir = project.export_dir
    ensure_dir(export_dir)

    # 拷贝设定集
    # [EN] Copy setting compendium
    src = project.settings_dir
    if src.exists():
        import shutil
        dst = export_dir / "设定集"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    # 完整度自评
    # [EN] Completeness self-assessment
    completeness = _assess_completeness(project)
    atomic_write_text(export_dir / "完整度自评.md", completeness)
    atomic_write_text(export_dir / "说明.md",
                      f"# {project.name} · 完整设定集导出\n\n"
                      f"导出时间：{now_str()}\n程序版本：{CFG.s('VERSION') if hasattr(CFG,'VERSION') else '0.1.0'}\n\n"
                      "此文件夹可直接作为新的输入文件夹再次导入。")
    _LOG.info("完整设定集导出: %s", export_dir)
    return export_dir


def _assess_completeness(project: Project) -> str:
    lines = ["# 完整度自评", "", "对照黄金档清单："]
    settings = project.settings_dir
    checks = [
        ("世界观.md", "世界观设定"),
        ("人物.yaml", "人物信息（≥2人）"),
        ("剧情走向.md", "大纲/剧情参考线"),
        ("伏笔与悬线.yaml", "伏笔清单"),
        ("风格卡.yaml", "风格卡"),
        ("类型卡.yaml", "类型卡"),
        ("故事进度.yaml", "故事进度表"),
    ]
    n = 0
    for fname, desc in checks:
        exists = (settings / fname).exists()
        mark = "✅" if exists else "❌"
        lines.append(f"- {mark} {desc}（{fname}）")
        if exists:
            n += 1
    lines.append(f"\n**完整度：{n}/{len(checks)}**")
    lines.append("黄金档达标：" + ("✅ 是" if n >= 6 else "❌ 否，缺项请参见导入优化向导"))
    return "\n".join(lines)


import json  # noqa: E402