# -*- coding: utf-8 -*-
"""摄取流程测试：进度回调 / AI 优化 / 落盘（MOCK 模式，零网络）。

跑法：
    .venv\\Scripts\\python.exe tests/ui/test_ingest_flow.py

English:
Ingest flow test: progress callback / AI optimization / persistence to disk (MOCK mode, zero
network).
How to run:
    .venv\\Scripts\\python.exe tests/ui/test_ingest_flow.py
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(APP_DIR))

from config import CFG          # noqa: E402
CFG.set('MOCK_LLM', 'true')     # CFG 只读 .env，演示模式必须显式 set
# [EN] CFG only reads .env, demo mode must be explicitly set

from llm.router import llm      # noqa: E402
from ingest.pipeline import (run_ingest, STAGES, freeze_settings,  # noqa: E402
                             required_stages, IngestDeclined)
from ingest import optimize as opt  # noqa: E402

PASS = 0
FAIL = 0
ERRORS: list[str] = []


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"[OK]   {msg}")


def bad(msg: str) -> None:
    global FAIL
    FAIL += 1
    ERRORS.append(msg)
    print(f"[FAIL] {msg}")


def make_fixture(root: Path) -> Path:
    """造一个小说文件夹：大纲 + 人物 + 正文。
        English:
    Create a novel folder: outline + characters + main text.
    """
    src = root / "雨夜来客"
    (src / "正文").mkdir(parents=True, exist_ok=True)
    (src / "大纲.md").write_text(
        "# 大纲\n\n起：雨夜来客打破平静。\n承：旧事被翻出。\n转：最可信的人露出破绽。\n合：有人离开。\n",
        encoding="utf-8")
    (src / "人物设定.md").write_text(
        "# 人物\n\n## 主角\n掌柜，沉默寡言。\n\n## 阿枝\n伙计，嘴上不饶人。\n",
        encoding="utf-8")
    (src / "正文" / "第1章.md").write_text(
        "# 第1章\n\n雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃。\n\n"
        "「你今日话里有话。」\n\n「话就是话，哪来的里外。」\n" * 8,
        encoding="utf-8")
    return src


async def test_pipeline(src: Path, freeze_dir: Path) -> dict:
    """① 管线：进度回调单调递增、阶段齐全、产物完整。
        English:
    ① Pipeline: progress callback monotonically increasing, all stages present, artifacts complete.
    """
    print("\n── 测试 1：摄取管线 + 进度回调 ──")
    seen: list[tuple[str, float]] = []
    logs: list[str] = []
    llm_events: list[dict] = []

    def on_stage(stage_id, label, pct, extra=''):
        seen.append((stage_id, pct))
        logs.append(f"{label}:{pct:.2f}{(' ' + extra) if extra else ''}")

    def on_llm(ev):
        llm_events.append(ev)

    llm.add_listener(on_llm)
    try:
        result = await run_ingest(src, settings_dir=freeze_dir, on_stage=on_stage)
    finally:
        llm.remove_listener(on_llm)

    # 进度单调不减
    # [EN] Progress is monotonically non-decreasing
    pcts = [p for _, p in seen]
    if pcts == sorted(pcts):
        ok(f"进度单调递增：{pcts}")
    else:
        bad(f"进度不单调：{pcts}")

    # 阶段齐全（`consent` 是有 gate 才有的阶段，这次没传 gate，不算）
    # [EN] All stages present (`consent` is a stage that only exists when a gate is passed; this time no
    # [EN] gate was passed, so it doesn't count)
    ids = {s[0] for s in seen}
    expect = required_stages(has_gate=False)
    if expect <= ids:
        ok(f"全部 {len(expect)} 个阶段都触发了")
    else:
        bad(f"缺少阶段：{expect - ids}")

    # 最终 100%
    # [EN] Finally 100%
    if seen and abs(seen[-1][1] - 1.0) < 1e-6:
        ok("最后阶段进度 = 100%")
    else:
        bad(f"最后进度不是 100%：{seen[-1] if seen else None}")

    # 产物
    # [EN] Artifacts
    n_chars = len(result.settings.get("人物", []))
    if n_chars >= 2:
        ok(f"提取到人物 {n_chars} 位")
    else:
        bad(f"人物提取异常：{n_chars}")

    if result.nodes:
        ok(f"故事进度表 {len(result.nodes)} 个节点")
    else:
        bad("故事进度表为空")

    if result.opening_candidates:
        ok(f"开局候选 {len(result.opening_candidates)} 个")
    else:
        bad("开局候选为空")

    if result.tier in ("青铜", "白银", "黄金"):
        ok(f"评档：{result.tier}（缺口 {result.missing_for_gold}）")
    else:
        bad(f"评档异常：{result.tier}")

    # LLM 事件：request / response 成对
    # [EN] LLM events: request / response in pairs
    reqs = [e for e in llm_events if e["type"] == "request"]
    resps = [e for e in llm_events if e["type"] == "response"]
    if reqs and len(reqs) == len(resps):
        ok(f"LLM 事件成对：{len(reqs)} 请求 / {len(resps)} 响应")
    else:
        bad(f"LLM 事件不成对：{len(reqs)} / {len(resps)}")
    if resps and all("text" in e and e["text"] for e in resps):
        ok("每个响应都带完整文本（可在日志里展示）")
    else:
        bad("有响应缺文本")

    print("    阶段日志：")
    for line in logs:
        print("      " + line)

    # 冻结产物（settings_dir 路径）
    # [EN] Frozen artifacts (settings_dir path)
    if (freeze_dir / "人物.yaml").exists() and (freeze_dir / "故事进度.yaml").exists():
        ok("管线内冻结生效（settings_dir）")
    else:
        bad(f"管线内冻结缺文件：{sorted(p.name for p in freeze_dir.iterdir())}")
    return result


async def test_optimize(result) -> dict:
    """② AI 优化：体检文本 + 按指令改设定。
        English:
    ② AI optimization: review text + modify settings per instructions.
    """
    print("\n── 测试 2：AI 优化对话 ──")
    settings = result.settings

    summary = opt.settings_summary(settings)
    if "主角" in summary and "人物" in summary:
        ok("设定摘要可读（含人名/分节）")
    else:
        bad(f"设定摘要异常：{summary[:80]!r}")

    review = await opt.review_settings(settings, name="雨夜来客",
                                      tier=result.tier,
                                      missing=result.missing_for_gold)
    if review and len(review) > 20:
        ok(f"AI 体检返回 {len(review)} 字")
    else:
        bad(f"AI 体检返回异常：{review!r}")

    new_settings, note = await opt.apply_instruction(
        settings, "把主角的秘密改成与井有关，并补一条伏笔",
        history=[{"role": "user", "content": "先给个意见"},
                 {"role": "assistant", "content": review}])
    if new_settings.get("人物"):
        ok(f"改设定后仍有 {len(new_settings['人物'])} 位人物")
    else:
        bad("改设定后人物丢失")
    if note:
        ok(f"变更说明：{note[:50]}")
    else:
        bad("变更说明为空")

    # 空指令不应崩
    # [EN] Empty instructions should not crash
    same, note2 = await opt.apply_instruction(settings, "   ")
    if same is settings:
        ok("空指令原样返回，未调 LLM")
    else:
        bad("空指令行为异常")

    return new_settings


def test_freeze(root: Path, src: Path, result, settings) -> None:
    """③ 落盘：冻结设定集 + 建项目 + 运行文件夹。
        English:
    ③ Persistence: freeze settings set + create project + run folder.
    """
    print("\n── 测试 3：冻结与建项目 ──")
    from store.project import Project
    from store.runfolder import RunFolder, make_run_name
    from util.text import now_str

    projects_dir = root / "Projects"
    proj = Project.create_new(projects_dir, "雨夜来客",
                              genre=str(result.genre.get("主题材", "")),
                              style="auto", source_folder=str(src))
    freeze_settings(proj.settings_dir, settings, result.genre,
                    result.style, result.nodes, result.alignment)
    rf = RunFolder(proj.root, make_run_name(proj.next_run_index())).create()
    rf.write_task_intro({"项目": "雨夜来客", "源文件夹": str(src)})
    proj.run_count = 1
    proj.last_run = now_str("%Y-%m-%d %H:%M")
    proj.write_nwsproj()

    need = ["人物.yaml", "世界观.md", "地点.yaml", "关系.yaml",
            "伏笔与悬线.yaml", "剧情走向.md", "类型卡.yaml", "风格卡.yaml",
            "故事进度.yaml"]
    missing = [n for n in need if not (proj.settings_dir / n).exists()]
    if not missing:
        ok(f"设定集冻结完整（{len(need)} 个文件）")
    else:
        bad(f"冻结缺文件：{missing}")

    if proj.nwsproj_path.exists():
        ok(f".nwsproj 已生成：{proj.nwsproj_path.name}")
    else:
        bad(".nwsproj 未生成")

    runs = proj.list_runs()
    if runs and (runs[0] / "任务介绍.md").exists():
        ok(f"运行文件夹已建：{runs[0].name}")
    else:
        bad("运行文件夹/任务介绍缺失")

    # 回读
    # [EN] Read back
    from store.project import scan_projects
    found = scan_projects(projects_dir)
    if any(p.name == "雨夜来客" for p in found):
        ok("scan_projects 能拾到新项目（拾卷可见）")
    else:
        bad("scan_projects 拾不到新项目")


async def test_consent(src_root: Path) -> None:
    """④ 「交给 AI 之前」的同意门：停下来问、不同意就一个请求都不发。
        English:
    ④ The consent gate "before handing off to AI": stop and ask; if declined, not a single request
    is sent.
    """
    print("\n── 测试 4：交给 AI 之前的同意门 ──")
    stages: list[str] = []
    reqs = {'n': 0}

    def on_stage(stage_id, label, pct, extra=""):
        stages.append(stage_id)

    def on_llm(ev):
        if ev.get('type') == 'request':
            reqs['n'] += 1

    llm.add_listener(on_llm)
    try:
        # ① 同意 → 跑完，且 `consent` 阶段确实出现过
        # [EN] ① Consent → runs to completion, and the `consent` stage did indeed appear
        src = make_fixture(src_root / 'yes')
        seen: list = []
        reqs['n'] = 0

        def gate_yes(brief):
            seen.append(brief)
            return True

        # 传 settings_dir：`freeze` 阶段是"给了冻结目录才有"的
        # [EN] Pass settings_dir: the `freeze` stage only exists "when a freeze directory is provided"
        result = await run_ingest(src, settings_dir=src_root / 'yes_设定集',
                                  on_stage=on_stage, gate=gate_yes)
        expect = required_stages(has_gate=True)
        if expect <= set(stages):
            ok(f"有 gate 时 {len(expect)} 个阶段全触发（含 consent）")
        else:
            bad(f"有 gate 时缺阶段：{expect - set(stages)}")
        if seen and seen[0].get('has_novel') and seen[0].get('est_input_tokens'):
            ok(f"闸门拿到真概览（正文 {seen[0]['novel_files']} 个，"
               f"预计输入 {seen[0]['est_input_tokens']} token）")
        else:
            bad(f"闸门概览异常：{seen[0] if seen else None}")
        if reqs['n'] > 0 and result.settings:
            ok(f"同意后正常调用 LLM（{reqs['n']} 次请求）")
        else:
            bad(f"同意后没跑起来：requests={reqs['n']}")

        # ② 不同意 → IngestDeclined + 零请求
        # [EN] ② Decline → IngestDeclined + zero requests
        src2 = make_fixture(src_root / 'no')
        reqs['n'] = 0
        declined = False
        try:
            await run_ingest(src2, gate=lambda brief: False)
        except IngestDeclined:
            declined = True
        if declined:
            ok("不同意 → 抛 IngestDeclined（中止，不是报错）")
        else:
            bad("不同意时没有中止")
        if reqs['n'] == 0:
            ok("不同意 → LLM 请求数 = 0（一分钱没花）")
        else:
            bad(f"不同意却发了 {reqs['n']} 次请求")
    finally:
        llm.remove_listener(on_llm)


async def main() -> int:
    print("=" * 62)
    print("摄取流程测试（MOCK 模式）")
    print("=" * 62)
    await llm.ensure_started()
    print(f"LLM mock = {CFG.mock}")

    tmp = Path(tempfile.mkdtemp(prefix="nws_ingest_"))
    try:
        await test_consent(tmp)
        src = make_fixture(tmp)
        result = await test_pipeline(src, tmp / "设定集_管线冻结")
        settings = await test_optimize(result)
        test_freeze(tmp, src, result, settings)
    finally:
        await llm.close()
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 62)
    print(f"通过 {PASS} 项，失败 {FAIL} 项")
    if ERRORS:
        for e in ERRORS:
            print(f"  ✗ {e}")
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
