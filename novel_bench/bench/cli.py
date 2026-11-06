# -*- coding: utf-8 -*-
"""NovelBench command line.

    python novel_bench/bench/cli.py check
    python novel_bench/bench/cli.py list --kind 网络
    python novel_bench/bench/cli.py smoke --case hlm-01
    python novel_bench/bench/cli.py run   --preset core --ticks 8
    python novel_bench/bench/cli.py judge --run results/20261018-101500
    python novel_bench/bench/cli.py report --run results/20261018-101500
    python novel_bench/bench/cli.py all   --preset smoke
    python novel_bench/bench/cli.py compare --a results/A --b results/B

Only ``run`` / ``judge`` cost money.  ``check`` / ``list`` / ``build`` /
``smoke`` are free and are the ones to run after editing the dataset.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent.parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from novel_bench.bench import dataset as DS          # noqa: E402
from novel_bench.bench import metrics as MET        # noqa: E402
from novel_bench.bench import report as REP         # noqa: E402
from novel_bench.bench.config import BENCH_DIR, Settings, judge_profiles  # noqa: E402


def _load_cases(kind: str = "", case: str = "", preset: str = "") -> list[tuple]:
    works = DS.load_all()
    presets = DS.load_presets()
    if case:
        w, c = DS.find_case(works, case)
        if not c:
            raise SystemExit(f"未知用例：{case}")
        return [(w, c)]
    picked = [(w, c) for w in works for c in w.cases]
    if preset and preset != "full":
        ids = presets.get(preset)
        if not ids:
            raise SystemExit(f"未知预设：{preset}（可用：{', '.join(sorted(presets))}）")
        picked = [x for x in picked if x[1].id in ids]
    if kind:
        picked = [x for x in picked if kind in (x[0].medium, x[0].category, *x[0].genres)]
    if not picked:
        raise SystemExit("没有匹配的用例")
    return picked


def cmd_check(a: argparse.Namespace) -> int:
    works = DS.load_all()
    issues = DS.validate(works)
    st = DS.stats(works)
    print(json.dumps(st, ensure_ascii=False, indent=2))
    if issues:
        print(f"\n✗ {len(issues)} 个问题：")
        for i in issues:
            print("  -", i)
        return 1
    print("\n✓ 数据集通过校验")
    return 0


def cmd_list(a: argparse.Namespace) -> int:
    for w, c in _load_cases(a.kind):
        print(f"{c.id:16s} {w.title:24s} {w.category}/{w.medium:2s} "
              f"{'/'.join(w.genres)[:18]:20s} {c.cut:4s} {c.place}")
    return 0


def cmd_build(a: argparse.Namespace) -> int:
    out = Path(a.out) if a.out else (BENCH_DIR / "results" / ".build")
    out.mkdir(parents=True, exist_ok=True)
    for w, c in _load_cases(case=a.case, preset=a.preset):
        from novel_bench.bench.project_builder import build_project
        proj = build_project(w, c, out)
        print(f"✓ {c.id} → {proj.root}")
    return 0


def cmd_smoke(a: argparse.Namespace) -> int:
    """Build + assemble one case without a single model call.

    This catches the failure mode that matters most for a benchmark harness:
    a project that assembles but has zero people, or settings written with the
    wrong keys, which would produce a plausible-looking but meaningless run.
    """
    import shutil
    import tempfile

    from novel_bench.bench.project_builder import build_project
    from sim.setup import assemble
    from store.runfolder import RunFolder

    works = DS.load_all()
    picked = _load_cases(case=a.case, preset=a.preset) or [(w, c) for w in works for c in w.cases]
    tmp = Path(tempfile.mkdtemp(prefix="nb_smoke_"))
    bad = 0
    try:
        for w, c in picked[:a.limit or len(picked)]:
            proj = build_project(w, c, tmp)
            run = RunFolder(proj.root, "第1次模拟").create()
            try:
                loop, world, db = assemble(proj, run)
                ppl = len(getattr(world, "people", {}) or {})
                text = getattr(world, "worldview_text", "") or ""
                rule = getattr(world, "rules_text", "") or ""
                ok = ppl >= 2 and len(text) > 80 and len(rule) > 40
                print(f"{'✓' if ok else '✗'} {c.id}: 人物 {ppl} · 世界观 {len(text)} 字 · "
                      f"规则 {len(rule)} 字 · 前置 {len(loop.agents)} 个 Agent")
                bad += 0 if ok else 1
                db.close()
            except Exception as e:                    # noqa: BLE001
                bad += 1
                print(f"✗ {c.id}: 装配失败 {e}")
                traceback.print_exc()
            finally:
                shutil.rmtree(proj.root, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'✓ 全部通过' if not bad else f'✗ {bad} 个用例装配有问题'}")
    return 0 if not bad else 1


def cmd_run(a: argparse.Namespace) -> int:
    cfg = Settings.load()
    if a.ticks:
        cfg.ticks = a.ticks
    if getattr(a, "think_mode", ""):
        cfg.think_mode = a.think_mode
    run_id = a.run_id or time.strftime("%Y%m%d-%H%M%S")
    # 每轮一个项目目录（见 `runner._run_case` 的说明）：run_id 决定落点。
    cfg.run_id = run_id
    run_dir = (Path(a.out) if a.out else (cfg.output_dir / run_id))
    run_dir.mkdir(parents=True, exist_ok=True)
    picked = _load_cases(kind=a.kind, case=a.case, preset=a.preset)

    from novel_bench.bench.runner import run_case
    print(f"▶ {len(picked)} 个用例 → {run_dir}")
    rows = []
    for i, (w, c) in enumerate(picked, 1):
        cdir = run_dir / "cases" / c.id
        print(f"[{i}/{len(picked)}] {c.id} 《{w.title}》 {c.cut} …", flush=True)
        meta = run_case(w, c, cdir, cfg)
        m = MET.compute(w, c, cdir) if not meta.get("fatal") else {"error": meta["fatal"]}
        (cdir / "metrics.json").write_text(
            json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        rows.append({"case": c.id, "meta": meta, "metrics": m})
        print(f"    {meta.get('ticks_done', 0)} 拍 · {meta.get('chars', 0)} 字 · "
              f"{meta.get('seconds', 0)}s · 卫生 {m.get('hygiene_score', '—')}", flush=True)
    (run_dir / "run.json").write_text(json.dumps({
        "run": run_id, "cases": [r["case"] for r in rows],
        "cfg": {"ticks": cfg.ticks, "beat_seconds": cfg.beat_seconds,
                "time_ratio": cfg.time_ratio,
                "think_mode": cfg.think_mode or "env"},
        "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ 推演完成 → {run_dir}")
    return 0


def cmd_metrics(a: argparse.Namespace) -> int:
    run_dir = Path(a.run)
    works = {w.id: w for w in DS.load_all()}
    cases = {c.id: (w, c) for w in works.values() for c in w.cases}
    n = 0
    for d in sorted((run_dir / "cases").iterdir()):
        if not d.is_dir() or d.name not in cases:
            continue
        w, c = cases[d.name]
        m = MET.compute(w, c, d)
        (d / "metrics.json").write_text(
            json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ {d.name}: 卫生 {m.get('hygiene_score', '—')}")
        n += 1
    return 0 if n else 1


def cmd_judge(a: argparse.Namespace) -> int:
    from novel_bench.bench.judge import Judge, review_case

    profs = judge_profiles()
    if not profs:
        print("✗ 没有配置评审模型。请复制 .env.example 为 .env 并填写 NB_JUDGE_*")
        return 2
    cfg = Settings.load()
    judge = Judge(profs, cfg)
    run_dir = Path(a.run)
    cases = {c.id: (w, c) for w in DS.load_all() for c in w.cases}
    targets = ([a.case] if a.case else
               [d.name for d in sorted((run_dir / "cases").iterdir()) if d.is_dir()])
    done = 0
    for cid in targets:
        if cid not in cases:
            print(f"! 跳过未知用例 {cid}")
            continue
        w, c = cases[cid]
        res = review_case(w, c, run_dir / "cases" / cid, judge)
        if "error" in res:
            print(f"✗ {cid}: {res['error']}")
            continue
        print(f"✓ {cid}: 推演 {res['sim'].get('weighted_100')} · "
              f"原著 {res['ref'].get('weighted_100')} · gap {res.get('gap')} · "
              f"盲评 {(res.get('pairwise') or {}).get('verdict')}")
        done += 1
    print(f"\n评审模型：{', '.join(p.name for p in profs)} · 完成 {done} 例")
    return 0 if done else 1


def cmd_report(a: argparse.Namespace) -> int:
    s = REP.build(Path(a.run))
    print(json.dumps({k: s[k] for k in ("run", "sim_mean", "ref_mean", "gap_mean",
                                        "win_rate", "hygiene_mean", "verdicts")},
                     ensure_ascii=False, indent=2))
    print(f"→ {Path(a.run) / 'report.md'}")
    print(f"→ {Path(a.run) / 'report.html'}")
    return 0


def cmd_all(a: argparse.Namespace) -> int:
    if not a.run_id:
        a.run_id = time.strftime("%Y%m%d-%H%M%S")
    if not a.out:
        a.out = str(Settings.load().output_dir / a.run_id)
    rc = cmd_run(a)
    if rc:
        return rc
    return cmd_report(argparse.Namespace(run=a.out))


def cmd_compare(a: argparse.Namespace) -> int:
    text = REP.compare(Path(a.a), Path(a.b))
    print(text)
    out = Path(a.out) if a.out else (Path(a.b) / "compare.md")
    out.write_text(text, encoding="utf-8")
    print(f"→ {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="novel_bench", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="校验数据集（免费）")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("list", help="列出用例（免费）")
    p.add_argument("--kind", default="")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("build", help="只生成项目设定集，不跑（免费）")
    p.add_argument("--case", default="")
    p.add_argument("--preset", default="")
    p.add_argument("--out", default="")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("smoke", help="装配自检：建项目+assemble，不调模型（免费）")
    p.add_argument("--case", default="")
    p.add_argument("--preset", default="smoke")
    p.add_argument("--limit", type=int, default=0)
    p.set_defaults(fn=cmd_smoke)

    p = sub.add_parser("run", help="跑推演（花钱）")
    p.add_argument("--preset", default="")
    p.add_argument("--case", default="")
    p.add_argument("--kind", default="")
    p.add_argument("--ticks", type=int, default=0)
    p.add_argument("--think-mode", default="", choices=["", "auto", "off", "always"],
                   help="覆盖思考模式（只影响这一轮，不改 .env）；做 A/B 对比时用")
    p.add_argument("--run-id", default="")
    p.add_argument("--out", default="")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("metrics", help="重算计数指标（免费）")
    p.add_argument("--run", required=True)
    p.set_defaults(fn=cmd_metrics)

    p = sub.add_parser("judge", help="LLM 评审（花钱）")
    p.add_argument("--run", required=True)
    p.add_argument("--case", default="")
    p.set_defaults(fn=cmd_judge)

    p = sub.add_parser("report", help="汇总报告（免费）")
    p.add_argument("--run", required=True)
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("all", help="run + report（评审另跑 judge）")
    p.add_argument("--preset", default="smoke")
    p.add_argument("--case", default="")
    p.add_argument("--kind", default="")
    p.add_argument("--ticks", type=int, default=0)
    p.add_argument("--think-mode", default="", choices=["", "auto", "off", "always"])
    p.add_argument("--run-id", default="")
    p.add_argument("--out", default="")
    p.set_defaults(fn=cmd_all)

    p = sub.add_parser("compare", help="两次运行对比")
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--out", default="")
    p.set_defaults(fn=cmd_compare)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
