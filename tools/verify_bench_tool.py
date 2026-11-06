# -*- coding: utf-8 -*-
"""验证 **基准工具自身**（不是产品）：口径、数据结构、校验器真的会红。

为什么单独一支
--------------
2026-10-18 我两次把校验代码插进 `find_case()`（作用域里没有 `issues`），
而 `check` 从不调用那个函数 ⇒ **校验从来没执行过，`check` 一直报绿**。
要不是手工 `len(c.hard)` 量了一下，这个假绿会一直骗到下一次。
所以"校验器会不会红"本身必须被判据守住 —— 这一支就是那道闸。

它还守三条口径（用户两次强调的）：
· 数据必须给**多条都成立的走法**，否则评测退化成"像不像原文"；
· 判据提示里**不许**出现"更适合作为续写"这类要求复刻的措辞；
· 报告里 `gap` 不许再写成"越接近 0 越好"（那是把原著当上限）。

跑法：
    .venv\\Scripts\\python.exe tools/verify_bench_tool.py
    .venv\\Scripts\\python.exe tools/verify_bench_tool.py --only=b,c
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

BENCH = APP / "novel_bench"
sys.path.insert(0, str(BENCH))

RESULTS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'✓' if cond else '✗'} {name}" + (f"  [{detail}]" if detail else ""), flush=True)


def section(t: str) -> None:
    print(f"\n{'─' * 68}\n  {t}\n{'─' * 68}", flush=True)


# ══════════════════════════════════════════════════════════════
#  A 数据结构：多合法走法
# ══════════════════════════════════════════════════════════════
def group_a() -> None:
    section("A 数据：每个用例都有硬约束 + ≥2 条合法走法")
    from novel_bench.bench.dataset import load_all

    works = load_all()
    cases = [c for w in works for c in w.cases]
    ok("A1 数据集非空", len(cases) >= 20, f"{len(cases)} 个用例")

    no_hard = [c.id for c in cases if not c.hard]
    ok("A2 ★★★ 每个用例都有 `ground_truth.hard`（否则'错'没有定义）",
       not no_hard, f"缺：{no_hard[:5]}" if no_hard else f"{len(cases)}/{len(cases)}")

    single = [c.id for c in cases if len(c.all_paths()) < 2]
    ok("A3 ★★★ 每个用例都给出 ≥2 条**都成立**的走法（用户要求的多结果集）",
       not single, f"只有一条：{single[:5]}" if single else
       f"共 {sum(len(c.all_paths()) for c in cases)} 条路径")

    no_stance = [c.id for c in cases
                 for a in c.alternatives if not a["stance"]]
    ok("A4 每条 alternative 都有 `stance`（取径标签）", not no_stance,
       f"{no_stance[:4]}")

    no_why = [c.id for c in cases
              for a in c.alternatives if not a["why_valid"]]
    ok("A5 ★★ 每条 alternative 都说清了 `why_valid`（评委凭什么信它成立）",
       not no_why, f"{no_why[:4]}")

    # ★★★ 成对：hard 不许写成"必须发生…"，否则就是变相的标准答案
    must = [h for c in cases for h in c.hard if h.startswith(("必须", "一定要", "务必"))]
    ok("A6 ★★★ 硬约束只写「不许」不写「必须」（写必须=又变回标准答案）",
       not must, f"{must[:2]}")

    # 一条走法至少要有点内容
    empty = [c.id for c in cases for a in c.alternatives
             if not a["beats"] and not a["excerpt"]]
    ok("A7 alternative 有 beats 或 excerpt（不是空壳）", not empty, f"{empty[:4]}")


# ══════════════════════════════════════════════════════════════
#  B 校验器**真的会红**（这一支的核心）
# ══════════════════════════════════════════════════════════════
def group_b() -> None:
    section("B 校验器自检：去掉关键字段必须报错（防假绿）")
    import yaml
    from novel_bench.bench import cli as BCLI
    from novel_bench.bench.dataset import load_all, validate

    base = load_all()
    ok("B0 现有数据集是干净的（validate 返回空）",
       not validate(base), f"{len(validate(base))} 条问题")

    # ── 造一个**只有一个走法**的用例，validate 必须点出来 ──
    import copy
    w0 = copy.deepcopy(base[0])
    c0 = w0.cases[0]
    origin_hard = list(c0.ground_truth.get("hard") or [])
    origin_alts = list(c0.ground_truth.get("alternatives") or [])

    c0.ground_truth.pop("hard", None)
    c0.ground_truth.pop("alternatives", None)
    probs = validate([w0])
    ok("B1 ★★★ 去掉 hard/alternatives ⇒ validate **必须报**（不报就是假绿）",
       any("ground_truth.hard" in p for p in probs)
       and any("only 1 valid path" in p or "valid path" in p for p in probs),
       f"{len(probs)} 条：{probs[0][:60] if probs else '（没报！）'}")

    # 还原
    c0.ground_truth["hard"] = origin_hard
    if origin_alts:
        c0.ground_truth["alternatives"] = origin_alts

    # ── 单字别称必须报（指标层不认它，写了等于假配置）──
    w1 = copy.deepcopy(base[0])
    p1 = w1.bible["people"][0]
    p1["别称"] = ["甲"]
    probs = validate([w1])
    ok("B2 ★★ 单字别称 ⇒ 必须报（指标会忽略它，等于假配置）",
       any("single character" in p for p in probs), f"{probs[:1]}")

    # ── 认不出的 story_time 必须报（否则静默退回辰时）──
    w2 = copy.deepcopy(base[0])
    w2.cases[0].story_time = "随便什么时候"
    probs = validate([w2])
    ok("B3 ★★ story_time 认不出 ⇒ 必须报（否则程序静默按 08:00 跑）",
       any("story_time" in p for p in probs), f"{probs[:1]}")

    # ── 硬约束写成"必须…"必须报 ──
    w3 = copy.deepcopy(base[0])
    w3.cases[0].ground_truth["hard"] = ["必须让王熙凤先声后人"]
    probs = validate([w3])
    ok("B4 ★★ hard 写成「必须…」⇒ 必须报（那是标准答案，不是约束）",
       any("hard constraint starts with" in p for p in probs), f"{probs[:1]}")


# ══════════════════════════════════════════════════════════════
#  C 口径：提示词里不许要求复刻
# ══════════════════════════════════════════════════════════════
def group_c() -> None:
    section("C 口径：判据与报告不许要求「复刻原著」")
    from novel_bench.bench import judge as J
    from novel_bench.bench import report as R

    forb = ["更适合作为这一段故事的直接续写", "更接近原文", "复刻原文"]
    hits = [s for s in forb if s in J.RUBRIC or s in J._pair_prompt(
        _first_work(), _first_case(), "甲", "乙")]
    ok("C1 ★★★ 评分/盲评提示里**没有**「更适合作为直接续写」这类要求复刻的措辞",
       not hits, f"命中 {hits}")

    ok("C2 ★★★ 有 `novelty` 维度且权重不小（给灵感就靠它）",
       "novelty" in J.DIMENSIONS and J.DIMENSIONS["novelty"][1] >= 0.15,
       f"权重 {J.DIMENSIONS.get('novelty', ('', 0))[1]}")

    ok("C3 维度权重合计 = 1.0（不然加权分会漂）",
       abs(sum(w for _l, w in J.DIMENSIONS.values()) - 1.0) < 1e-9,
       f"{sum(w for _l, w in J.DIMENSIONS.values()):.3f}")

    ok("C4 提示里写明了「新增人物地点不扣分」（否则又回到旧口径）",
       "不扣分" in J.RUBRIC and "新增人物" in J.RUBRIC)

    # ★★★ C5 判**渲染出来的报告**，不判源码字符串。
    #   第一版判的是源码（`"越接近 0 越好" not in src`），结果被一行**注释**打红 ——
    #   注释里正是在说"旧文案这么写是错的"。这正是项目纪律里那条：
    #   **别拿"源码含某字符串"当判据**，要判行为/产物。
    # [EN] ★★★ C5 judges the **rendered report**, not a source string. The first version checked the
    # [EN] source and went red on a **comment** that explains why the old wording was wrong -- exactly
    # [EN] the project rule: **never use "source contains X" as a criterion**, judge behaviour or
    # [EN] artefacts.
    fake = {
        "run": "verify", "cases_total": 1, "cases_scored": 1,
        "sim_mean": 50.0, "ref_mean": 70.0, "gap_mean": -20.0, "gap_ci95": [float("nan")] * 2,
        "novelty_mean": 3.0, "win_rate": None, "hygiene_mean": 95.0,
        "verdicts": {"sim": 0, "ref": 0, "tie": 1, "none": 0},
        "dims": {k: {"label": v[0], "sim": 3.0, "ref": 4.0}
                 for k, v in J.DIMENSIONS.items()},
        "metrics": {}, "issues": {},
        "cases": [{"case": "x-01", "work": "w", "title": "T", "genres": ["g"], "cut": "中段",
                   "hygiene": 95.0, "sim": 50.0, "ref": 70.0, "gap": -20.0,
                   "novelty": 3.0, "verdict": "tie", "defects": [], "issues": []}],
    }
    md = R._md(fake)
    ok("C5 ★★★ 渲染出的报告里没有「越接近 0 越好」（不把原著当上限）",
       "越接近 0 越好" not in md,
       "仍在" if "越接近 0 越好" in md else "已清除")
    ok("C5b ★★ 成对：报告明写 gap「不是分数目标」+ 给出创意增量那一行",
       "不是分数目标" in md and "创意增量 (novelty)" in md)
    ok("C6 报告按**创意分**排序（最没灵感的排最前）",
       "创意" in md.split("用例明细")[-1])

    # 多路径真的进了提示词
    digest = J._truth_digest(_first_case())
    # ⚠ 必须**真的给出两条以上**走法（`走法 1｜`、`走法 2｜` 都在）。
    #   只判"都成立"这个词的话，把 paths 截成 1 条仍然绿（反例法第 18 组）。
    # [EN] ⚠ There must be **two or more** paths actually shown (`走法 1｜` and `走法 2｜`). Asserting
    # [EN] only the phrase "都成立" stays green after truncating paths to one (mutation #18).
    ok("C7 ★★★ 提示词里同时出现「硬约束」和**两条以上**走法",
       "硬约束" in digest and "走法 1｜" in digest and "走法 2｜" in digest,
       f"{len(digest)} 字")
    ok("C8 提示词明写「不是标准答案」", "不是标准答案" in digest)


def _first_work():
    from novel_bench.bench.dataset import load_all
    return load_all()[0]


def _first_case():
    return _first_work().cases[0]


def main() -> int:
    t0 = time.time()
    only = ""
    for a in sys.argv[1:]:
        if a.startswith("--only"):
            only = a.split("=", 1)[-1]
    try:
        if not only or "a" in only:
            group_a()
        if not only or "b" in only:
            group_b()
        if not only or "c" in only:
            group_c()
    finally:
        passed = sum(1 for _n, c, _d in RESULTS if c)
        print(f"\n{'=' * 68}\n  基准工具验证：{passed}/{len(RESULTS)}"
              f"　（{time.time() - t0:.1f}s）\n{'=' * 68}", flush=True)
        bad = [n for n, c, _d in RESULTS if not c]
        if bad:
            print("未通过：\n  - " + "\n  - ".join(bad), flush=True)
    return 0 if all(c for _n, c, _d in RESULTS) else 2


if __name__ == "__main__":
    sys.exit(main())
