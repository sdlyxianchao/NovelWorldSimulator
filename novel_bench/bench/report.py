# -*- coding: utf-8 -*-
"""Aggregate one run directory into a readable report.

Outputs (all inside ``results/<run_id>/``):

* ``summary.json`` -- machine readable, everything downstream reads this
* ``scores.csv``   -- one row per case, easy to paste into a spreadsheet
* ``report.md``    -- the human report (Chinese body, English headings)
* ``report.html``  -- same content, self-contained, no external assets

The report is written so that "what got worse / what got better" is a *visual*
comparison: every table has a per-case row, and the gap column is sorted.
"""
from __future__ import annotations

import csv
import html
import json
import random
import statistics
from pathlib import Path
from typing import Any

from .judge import DIMENSIONS


def _case_meta_from_dataset(case_id: str) -> dict:
    """从数据集补 `cut` / `genres` / `title` 这些**不该由运行产物决定**的字段。

    ★★ 2026-10-18：`meta.json` 早期没写 `cut`/`genres`（见 `runner` 那段说明），
      报告于是出现"体裁、切入点两列全空"。补在**读的时候**而不是要求重跑 ——
      历史结果也要能出正确报告，否则"以前跑的不能比"会变成习惯。
    [EN] ★★ 2026-10-18: early `meta.json` files lack `cut`/`genres` (see the note in `runner`), so
    [EN] the report showed empty genre/cut columns. Fill it **at read time** instead of demanding a
    [EN] re-run -- historical results must still produce correct reports, otherwise "old runs cannot be
    [EN] compared" becomes a habit.
    """
    try:
        from .dataset import load_all
        for w in load_all():
            for c in w.cases:
                if c.id == case_id:
                    return {"work": w.id, "title": w.title, "author": w.author,
                            "genres": list(w.genres), "medium": w.medium,
                            "license": w.license, "cut": c.cut,
                            "place": c.place, "story_time": c.story_time,
                            "focus": list(c.focus), "present": list(c.present)}
    except Exception:                                  # noqa: BLE001
        return {}
    return {}


def _load_case_rows(run_dir: Path) -> list[dict]:
    rows = []
    cdir = run_dir / "cases"
    if not cdir.is_dir():
        return rows
    for d in sorted(cdir.iterdir()):
        if not d.is_dir():
            continue
        row: dict[str, Any] = {"case": d.name}
        for name, key in (("meta.json", "meta"), ("metrics.json", "metrics"),
                          ("judge.json", "judge")):
            p = d / name
            if p.is_file():
                try:
                    row[key] = json.loads(p.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    row[key] = {}
            else:
                row[key] = {}
        # 缺失的元信息用数据集补齐（不覆盖运行产物里已有的值）
        fill = _case_meta_from_dataset(d.name)
        for k, v in fill.items():
            if not row["meta"].get(k):
                row["meta"][k] = v
        rows.append(row)
    return rows


def _bootstrap_ci(vals: list[float], n: int = 2000, alpha: float = 0.05,
                  seed: int = 7) -> tuple[float, float]:
    if len(vals) < 3:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = []
    for _ in range(n):
        means.append(statistics.fmean(rng.choice(vals) for _ in vals))
    means.sort()
    lo = means[int(n * alpha / 2)]
    hi = means[int(n * (1 - alpha / 2)) - 1]
    return (round(lo, 1), round(hi, 1))


def build(run_dir: Path) -> dict:
    rows = _load_case_rows(run_dir)
    ok = [r for r in rows if r["judge"].get("sim", {}).get("weighted_100") is not None]
    hyg = [r["metrics"]["hygiene_score"] for r in rows if r["metrics"].get("hygiene_score") is not None]
    sim_scores = [r["judge"]["sim"]["weighted_100"] for r in ok]
    ref_scores = [r["judge"]["ref"]["weighted_100"] for r in ok]
    gaps = [r["judge"].get("gap", 0.0) for r in ok]

    verdicts = {"sim": 0, "ref": 0, "tie": 0, "none": 0}
    for r in ok:
        v = (r["judge"].get("pairwise") or {}).get("verdict")
        verdicts[v if v in verdicts else "none"] += 1

    novelty_vals = [(r["judge"].get("sim") or {}).get("scores", {}).get("novelty") for r in ok]
    novelty_vals = [v for v in novelty_vals if v is not None]
    novelty_mean = round(statistics.fmean(novelty_vals), 2) if novelty_vals else None

    dims: dict[str, dict[str, float]] = {}
    for k in DIMENSIONS:
        a = [r["judge"]["sim"]["scores"].get(k, 0) for r in ok]
        b = [r["judge"]["ref"]["scores"].get(k, 0) for r in ok]
        dims[k] = {
            "label": DIMENSIONS[k][0],
            "sim": round(statistics.fmean(a), 2) if a else 0,
            "ref": round(statistics.fmean(b), 2) if b else 0,
        }

    lo, hi = _bootstrap_ci(gaps) if gaps else (float("nan"), float("nan"))
    decisive = verdicts["sim"] + verdicts["ref"]
    metric_avg = {}
    for key in ("repeat_4gram", "dialogue_ratio", "sentence_len_median",
                "dup_pairs", "dup_sent_pairs", "idle_beats",
                "present_coverage", "cast_coverage",
                # 2026-10-20 晚新增（口径同 `crew/prose_flow.py`）
                "prop_cycle_max", "flat_spans", "long_spans"):
        vals = [r["metrics"].get(key) for r in rows if r["metrics"].get(key) is not None]
        metric_avg[key] = round(statistics.fmean(vals), 3) if vals else None
    # 引号混用是布尔量，取"几次运行里混用过"更有意义
    _qm = [r["metrics"].get("quotes_mixed") for r in rows
           if r["metrics"].get("quotes_mixed") is not None]
    metric_avg["quotes_mixed_runs"] = sum(1 for x in _qm if x) if _qm else None

    issues: dict[str, int] = {}
    for r in rows:
        for it in r["metrics"].get("issues") or []:
            head = it.split("：")[0].split("（")[0][:24]
            issues[head] = issues.get(head, 0) + 1

    worst = sorted(ok, key=lambda r: r["judge"].get("gap", 0))[:5]

    summary = {
        "run": run_dir.name,
        "cases_total": len(rows),
        "cases_scored": len(ok),
        "hygiene_mean": round(statistics.fmean(hyg), 1) if hyg else None,
        "sim_mean": round(statistics.fmean(sim_scores), 1) if sim_scores else None,
        "ref_mean": round(statistics.fmean(ref_scores), 1) if ref_scores else None,
        "gap_mean": round(statistics.fmean(gaps), 1) if gaps else None,
        #: **创意增量**均值（0–5）。这是主指标之一：给作者找灵感靠的就是它。
        #: [EN] **Novelty** mean (0-5). A primary metric: this is what an idea-generating tool is for.
        "novelty_mean": novelty_mean,
        "gap_ci95": [lo, hi],
        "verdicts": verdicts,
        "win_rate": (round(verdicts["sim"] / max(1, decisive), 3) if decisive else None),
        "dims": dims,
        "metrics": metric_avg,
        "issues": dict(sorted(issues.items(), key=lambda kv: -kv[1])),
        "cases": [{
            "case": r["case"],
            "work": r["meta"].get("work", ""),
            "title": r["meta"].get("title", ""),
            "genres": r["meta"].get("genres", []),
            "cut": r["meta"].get("cut", ""),
            "hygiene": r["metrics"].get("hygiene_score"),
            "sim": r["judge"].get("sim", {}).get("weighted_100"),
            "ref": r["judge"].get("ref", {}).get("weighted_100"),
            "gap": r["judge"].get("gap"),
            "novelty": (r["judge"].get("sim") or {}).get("scores", {}).get("novelty"),
            "verdict": (r["judge"].get("pairwise") or {}).get("verdict"),
            "defects": r["judge"].get("sim", {}).get("defects", []),
            "issues": r["metrics"].get("issues", []),
            "chars": r["metrics"].get("chars"),
        } for r in rows],
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(run_dir / "scores.csv", summary["cases"])
    (run_dir / "report.md").write_text(_md(summary), encoding="utf-8")
    (run_dir / "report.html").write_text(_html(summary), encoding="utf-8")
    return summary


def _write_csv(path: Path, cases: list[dict]) -> None:
    cols = ["case", "work", "title", "cut", "chars", "hygiene", "sim", "ref",
            "gap", "verdict"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for c in cases:
            w.writerow({k: c.get(k) for k in cols})


def _pct1(v: Any) -> str:
    """0–1 的小数 → 百分比（1 位小数）。None / 缺值 →「—」。"""
    if v is None:
        return "—"
    return f"{float(v) * 100:.1f}%"


def _pct(v: Any) -> str:
    return "—（无胜负）" if v is None else f"{v:.0%}"


def _ci_txt(ci: list) -> str:
    lo, hi = ci
    if lo != lo or hi != hi:            # NaN
        return "（样本不足，未给区间）"
    return f"(95% CI {lo}~{hi})"


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def _fmt2(v: Any) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}" if abs(v) < 10 else f"{v:.1f}"


def _md(s: dict) -> str:
    L: list[str] = []
    L += [f"# 小说推演质量报告 · {s['run']}", "",
          "## 总览 (Overview)", "",
          "| 指标 | 值 | 含义 |", "|---|---|---|",
          f"| 用例 (cases) | {s['cases_scored']}/{s['cases_total']} | 有评分的用例数 |",
          # ★★★ 2026-10-18（用户）：**这是给作者找灵感的工具，不追求和原文一致**。
          #   所以 `gap` 从"主指标"降级成"**尺子校准值**"：它回答"这把尺子对这篇严不严"，
          #   不是"离原著还差多少"。旧文案写着"越接近 0 越好"= 把原著当上限，
          #   会把"走了另一条路"判成退步 —— 而那正是这软件的功能。
          # [EN] ★★★ 2026-10-18 (user): **an idea-generating tool, not a fidelity test**, so `gap`
          # [EN] is demoted to "**ruler calibration**": it says how strict the rubric is on this work,
          # [EN] not how far from the original. The old line ("closer to 0 is better") treated the
          # [EN] original as a ceiling and graded "took another road" as a regression -- which is
          # [EN] precisely this tool's feature.
          f"| 推演得分 (sim) | {_fmt(s['sim_mean'])} | **主指标**：同一把尺子的 0–100 |",
          f"| 原著的锚点 (ref) | {_fmt(s['ref_mean'])} | 量原著，**只用来校准尺子** |",
          f"| 与原著的距离 (gap) | {_fmt(s['gap_mean'])} {_ci_txt(s['gap_ci95'])} | **不是分数目标**；只说明尺子严不严 |",
          f"| 创意增量 (novelty) | {_fmt(s.get('novelty_mean'))} | **看这一项**：5=眼前一亮，3=稳，1=复述原文 |",
          f"| 盲评胜率 (win) | {_pct(s['win_rate'])} | 只看有胜负的用例；平局不计入 |",
          f"| 文本卫生 (hygiene) | {_fmt(s['hygiene_mean'])} | 纯计数打分：重复/元标记/禁忌词… |",
          f"| 盲评结果 | 胜 {s['verdicts']['sim']} · 负 {s['verdicts']['ref']} · 平 {s['verdicts']['tie']} | 两个顺序都判对才算胜负 |",
          "",
          "> **读法**：本工具服务于「给作者找灵感」，**不要求推演复刻原著**。",
          "> `novelty`（创意增量）专门奖励「原著没走、但走得有道理」的路；",
          "> `gap` 只用来判断尺子严不严，**不要当成「还差多少」**。", "",
          "## 分维度 (Dimensions)", "",
          "| 维度 | 推演 | 原著锚点 | 差 |", "|---|---|---|---|"]
    for k, d in s["dims"].items():
        L.append(f"| {d['label']} | {d['sim']:.2f} | {d['ref']:.2f} | {d['sim'] - d['ref']:+.2f} |")
    L += ["", "## 文本卫生 (Automatic metrics)", "",
          "| 指标 | 均值 | 参考 |", "|---|---|---|",
          # ★★ 2026-10-18：重复率是 0–1 的小数，`_fmt` 只给 1 位小数 ⇒ 0.035 显示成 "0.0"，
          #   报告上看着"完全没重复"，而实际是 3.5%（真人 0–3%）。小数一律按百分比。
          # [EN] ★★ 2026-10-18: the repetition rate is a 0..1 fraction; `_fmt` gives one decimal, so
          # [EN] 0.035 printed as "0.0" -- the report looked like "no repetition at all" while it was
          # [EN] 3.5% (human baseline 0-3%). Fractions are always shown as percentages.
          f"| 四字重复率 | {_pct1(s['metrics'].get('repeat_4gram'))} | 真人 0–3% |",
          f"| 相邻近似复读 | {_fmt(s['metrics'].get('dup_pairs'))} | 越好越接近 0 |",
          f"| 相邻**句**近似复读 | {_fmt(s['metrics'].get('dup_sent_pairs'))} | 行内重复，行级看不到 |",
          f"| 对白占比 | {_pct1(s['metrics'].get('dialogue_ratio'))} | 散文按含引号的行算 |",
          f"| 句长中位 | {_fmt(s['metrics'].get('sentence_len_median'))} | 真人 9–13 字 |",
          f"| 空拍 | {_fmt(s['metrics'].get('idle_beats'))} | 0 最好 |",
          f"| 在场人物出场率 | {_fmt(s['metrics'].get('present_coverage'))} | 1.0 最好 |",
          # ── 2026-10-20 晚新增四条（每条都先在真人 18 章上量过零误报）──
          # 出处的实测数字写在右列，方便一眼看出"这个数是不是真的算高"。
          # [EN] Four metrics added 2026-10-20, each calibrated on the 18 human chapters;
          # [EN] the measured human figure is printed in the reference column.
          f"| 道具循环（同一件东西反复续上/耗掉） | {_fmt(s['metrics'].get('prop_cycle_max'))} | 真人最大 **0**；≥3 算病 |",
          f"| 太碎段（段内逗号比句子还少） | {_fmt(s['metrics'].get('flat_spans'))} | 真人 **0** 段 |",
          f"| 憋气段（长句过半/有超长句） | {_fmt(s['metrics'].get('long_spans'))} | 真人最高 1 段 |",
          # ⚠ 用 `quotes_mixed_runs`（有几篇混用），不是 `quotes_mixed` ——
          #   `metric_avg` 里聚合过的 key 才在 `s['metrics']` 里，写错名字会永远显示"否"。
          # [EN] Use the aggregated key `quotes_mixed_runs`; the raw per-case key is absent
          # [EN] from the aggregate, and a wrong name silently prints "no" forever.
          f"| 引号混用 | {'{} 篇'.format(_fmt(s['metrics'].get('quotes_mixed_runs'))) if s['metrics'].get('quotes_mixed_runs') else '否'} | 单一样式不扣分（真人全用 ASCII） |",
          ""]
    if s["issues"]:
        L += ["### 问题频次", ""] + [f"- {k}：{v} 例" for k, v in s["issues"].items()] + [""]
    L += ["## 用例明细 (Cases)", "",
          "| 用例 | 作品 | 体裁 | 切入点 | 卫生 | **创意** | 推演 | 原著 | 距离 | 盲评 |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    # ★ 2026-10-18：排序改成**创意分升序**（最没灵感的排最前，那才是要改进的）。
    #   原来按 gap 升序 = "离原著越远越差"，与"鼓励变化"正好相反。
    # [EN] ★ 2026-10-18: sort by **novelty ascending** (least inventive first -- those are the ones
    # [EN] to improve). Sorting by gap meant "further from the original is worse", the opposite of
    # [EN] encouraging variation.
    for c in sorted(s["cases"], key=lambda x: (x.get("novelty") is None, x.get("novelty") or 0)):
        L.append(f"| {c['case']} | {c['title']} | {'/'.join(c['genres'])} | {c['cut']} | "
                 f"{_fmt(c['hygiene'])} | **{_fmt(c.get('novelty'))}** | {_fmt(c['sim'])} | "
                 f"{_fmt(c['ref'])} | {_fmt(c['gap'])} | {c['verdict'] or '—'} |")
    L += ["", "## 最缺创意的用例 (Least inventive)", ""]
    worst = sorted([c for c in s["cases"] if c.get("novelty") is not None],
                   key=lambda x: x["novelty"])[:5]
    for c in worst:
        L.append(f"### {c['case']} · {c['title']}"
                 f"（创意 {_fmt(c.get('novelty'))} · 推演 {_fmt(c['sim'])}）")
        for d in c.get("defects", [])[:4]:
            L.append(f"- {d}")
        for i in c.get("issues", [])[:4]:
            L.append(f"- [计数] {i}")
        L.append("")
    L += ["---", "",
          "口径与公式见 `docs/methodology.md`；书单与出处见 `dataset/works/` 与 `docs/sources.md`。",
          "评审模型、温度、重复次数都在 `.env` 里，报告不写死模型名 —— 换模型请连同报告一起归档。"]
    return "\n".join(L) + "\n"


def _html(s: dict) -> str:
    def bar(v: float, color: str = "#c0392b") -> str:
        w = max(0, min(100, v)) * 2.2
        return (f'<span style="display:inline-block;height:10px;width:{w:.0f}px;'
                f'background:{color};border-radius:2px;vertical-align:middle"></span>')

    rows = []
    for c in sorted(s["cases"], key=lambda x: (x["gap"] is None, x["gap"] or 0)):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(c['case']))}</td>"
            f"<td>{html.escape(str(c['title']))}</td>"
            f"<td>{html.escape('/'.join(c['genres']))}</td>"
            f"<td>{html.escape(str(c['cut']))}</td>"
            f"<td class='n'>{_fmt(c['hygiene'])}</td>"
            f"<td class='n'>{_fmt(c['sim'])} {bar(c['sim'] or 0)}</td>"
            f"<td class='n'>{_fmt(c['ref'])} {bar(c['ref'] or 0, '#7f8c8d')}</td>"
            f"<td class='n'>{_fmt(c['gap'])}</td>"
            f"<td>{c['verdict'] or '—'}</td>"
            "</tr>")
    dims = "".join(
        f"<tr><td>{html.escape(d['label'])}</td><td class='n'>{d['sim']:.2f}</td>"
        f"<td class='n'>{d['ref']:.2f}</td><td class='n'>{d['sim'] - d['ref']:+.2f}</td></tr>"
        for d in s["dims"].values())
    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>小说推演质量报告 · {html.escape(s['run'])}</title>
<style>
 body{{font-family:-apple-system,"Segoe UI","Noto Sans SC",sans-serif;margin:32px;color:#1c1c1c;background:#faf9f7}}
 h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:16px;margin:28px 0 8px;color:#333}}
 .sub{{color:#777;font-size:13px;margin-bottom:20px}}
 table{{border-collapse:collapse;width:100%;font-size:13px;background:#fff}}
 th,td{{border-bottom:1px solid #e6e2dc;padding:6px 8px;text-align:left}}
 th{{background:#f1ede7;font-weight:600}} td.n{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}
 .cards{{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}}
 .card{{background:#fff;border:1px solid #e6e2dc;border-radius:8px;padding:12px 16px;min-width:150px}}
 .k{{font-size:12px;color:#888}} .v{{font-size:22px;font-weight:600;margin-top:2px}}
</style></head><body>
<h1>小说推演质量报告</h1>
<div class="sub">{html.escape(s['run'])} · 用例 {s['cases_scored']}/{s['cases_total']}</div>
<div class="cards">
 <div class="card"><div class="k">推演得分</div><div class="v">{_fmt(s['sim_mean'])}</div></div>
 <div class="card"><div class="k">原著锚点</div><div class="v">{_fmt(s['ref_mean'])}</div></div>
 <div class="card"><div class="k">差距 gap</div><div class="v">{_fmt(s['gap_mean'])}</div></div>
 <div class="card"><div class="k">盲评胜率</div><div class="v">{_pct(s['win_rate'])}</div></div>
 <div class="card"><div class="k">文本卫生</div><div class="v">{_fmt(s['hygiene_mean'])}</div></div>
</div>
<h2>分维度</h2>
<table><tr><th>维度</th><th>推演</th><th>原著锚点</th><th>差</th></tr>{dims}</table>
<h2>用例明细（按差距排序，越靠上越差）</h2>
<table><tr><th>用例</th><th>作品</th><th>体裁</th><th>切入点</th><th>卫生</th><th>推演</th><th>原著</th><th>差</th><th>盲评</th></tr>
{''.join(rows)}</table>
<p class="sub">口径见 docs/methodology.md</p>
</body></html>
"""


def compare(a_dir: Path, b_dir: Path) -> str:
    """Markdown diff between two runs (b against a)."""
    a = json.loads((a_dir / "summary.json").read_text(encoding="utf-8"))
    b = json.loads((b_dir / "summary.json").read_text(encoding="utf-8"))
    L = [f"# 对比 · {a['run']} → {b['run']}", "",
         "| 指标 | 前 | 后 | 变化 |", "|---|---|---|---|"]
    for key, label in (("sim_mean", "推演得分"), ("ref_mean", "原著锚点"),
                       ("gap_mean", "差距"), ("hygiene_mean", "文本卫生")):
        va, vb = a.get(key), b.get(key)
        d = "—" if va is None or vb is None else f"{vb - va:+.1f}"
        L.append(f"| {label} | {_fmt(va)} | {_fmt(vb)} | {d} |")
    wa, wb = a.get("win_rate"), b.get("win_rate")
    if wa is None or wb is None:
        L.append(f"| 盲评胜率 | {_pct(wa)} | {_pct(wb)} | — |")
    else:
        L.append(f"| 盲评胜率 | {wa:.0%} | {wb:.0%} | {(wb - wa) * 100:+.0f}pp |")
    L += ["", "## 逐用例变化", "", "| 用例 | 前 | 后 | 变化 |", "|---|---|---|---|"]
    am = {c["case"]: c for c in a["cases"]}
    for c in b["cases"]:
        old = am.get(c["case"], {}).get("sim")
        new = c.get("sim")
        d = "—" if old is None or new is None else f"{new - old:+.1f}"
        L.append(f"| {c['case']} | {_fmt(old)} | {_fmt(new)} | {d} |")
    # ★★ 2026-10-20 晚：加"文本卫生分项"一节。
    #   总分变化只告诉你"变好/变坏"，分项才告诉你**是哪一类变的** ——
    #   而"改了一处、另一处变差"正是这个项目最常见的失败模式。
    #   ⚠ 旧 `summary.json` 里没有这些键 ⇒ 显示"—"（并提示重算），
    #     不能把"字段缺失"读成"没有毛病"。
    # [EN] ★ 2026-10-20: add a per-metric hygiene section. The total tells you "better or
    # [EN] worse"; the breakdown tells you **which class** moved -- and "fixed one, broke
    # [EN] another" is the most common failure mode here. Older summaries lack these keys,
    # [EN] so show "—" and say to recompute, never read a missing field as "no problem".
    ma, mb = a.get("metrics") or {}, b.get("metrics") or {}
    _keys = ("prop_cycle_max", "flat_spans", "long_spans", "quotes_mixed_runs",
             "repeat_4gram", "dup_pairs", "dup_sent_pairs", "idle_beats",
             "sentence_len_median", "present_coverage")
    _labels = {"prop_cycle_max": "道具循环（真人 0）",
               "flat_spans": "太碎段（真人 0）",
               "long_spans": "憋气段（真人 ≤1）",
               "quotes_mixed_runs": "引号混用的篇数",
               "repeat_4gram": "四字重复率",
               "dup_pairs": "相邻近似复读",
               "dup_sent_pairs": "相邻句近似复读",
               "idle_beats": "空拍",
               "sentence_len_median": "句长中位",
               "present_coverage": "在场人物出场率"}
    if any(k in ma or k in mb for k in _keys):
        L += ["", "## 文本卫生分项（看出修的是哪一类）", "",
              "| 指标 | 前 | 后 | 变化 |", "|---|---|---|---|"]
        #: 显示格式：**比率必须按百分比显示**。
        #: ⚠ `_fmt` 只给 1 位小数 ⇒ 0.0415 和 0.0085 都显示 "0.0"，
        #:   看着"完全没变"而实际差 3.3 个百分点（报告层踩过一次同样的坑）。
        # [EN] Fractions must print as percentages: `_fmt` gives one decimal, so 4.2% and
        # [EN] 0.9% both read "0.0" and the change looks like nothing.
        _pct_keys = {"repeat_4gram", "present_coverage", "cast_coverage"}
        for k in _keys:
            if k not in ma and k not in mb:
                continue
            va, vb = ma.get(k), mb.get(k)
            if k in _pct_keys:
                show = lambda v: _pct1(v)          # noqa: E731
                d = ("—" if not isinstance(va, float) or not isinstance(vb, float)
                     else f"{(vb - va) * 100:+.1f}pp")
            elif isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                show = lambda v: _fmt(v)           # noqa: E731
                # 计数类（道具循环 4 次、太碎 2 段）显示整数增量；长度/人次一律 1 位小数。
                # ⚠ `metric_avg` 用 fmean 聚合过 ⇒ 4 变成 4.0，光看类型分不出来，
                #   所以看"值本身是不是整数"。
                # [EN] Counts show an integer delta; `metric_avg` goes through fmean so a
                # [EN] count of 4 arrives as 4.0 and the type cannot tell them apart.
                _int_like = (float(va).is_integer() and float(vb).is_integer())
                d = f"{int(vb) - int(va):+d}" if _int_like else f"{vb - va:+.1f}"
            else:
                show = lambda v: _fmt(v)           # noqa: E731
                d = "—"
            L.append(f"| {_labels.get(k, k)} | {show(va)} | {show(vb)} | {d} |")
        if "prop_cycle_max" not in ma and "prop_cycle_max" not in mb:
            L += ["", "> ⚠ 两边都没有新指标 —— 旧产物请先跑 "
                      "`metrics --run <目录>` 重算，否则这份对比看不到道具循环/太碎/引号。"]
    return "\n".join(L) + "\n"
