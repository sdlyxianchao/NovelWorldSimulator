# -*- coding: utf-8 -*-
"""LLM-as-judge layer.

Design decisions worth knowing before editing:

* **Reference-anchored, not absolute.**  Every case is scored twice with the
  same rubric: once for the simulation transcript, once for the author's own
  continuation.  The headline number is the *gap* to the human anchor, because
  absolute 1-5 scores drift between models and between weeks.
* **Blind pairwise.**  The two texts are shown as 甲/乙 in both orders; a win
  only counts when the judge picks the same text in both orders (otherwise it
  is a tie).  This cancels the well-documented position bias of LLM judges.
* **Multi-judge median.**  If more than one profile is configured, the report
  takes the median per dimension.  A single judge is a single opinion.
* **Cached by prompt hash.**  Re-running the report never re-pays for a call.

Rubric sources are listed in docs/sources.md (G-Eval, MT-Bench judge biases,
LitBench, WebNovelBench's eight narrative dimensions).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
from pathlib import Path
from typing import Any

from .config import JudgeProfile, Settings
from .dataset import Case, Work
from .llm import LLMError, chat, parse_json

# ★★★ 2026-10-18（用户）：**"我这个软件是给作者提供创意用的，不追求跟原文完全相同；
# 在合理的范围内有变化也是一个重要的功能"**。
#
# 这句话推翻了第一版的评分口径，必须先记下错在哪：
#   · 旧 `plot` 的问法是"作为这一段之后的**续写**，推进是否合理"——"续写"这个词
#     本身就在要求接原文；
#   · 旧盲评问"哪一段更适合作为**直接续写**"——同样在奖励复刻；
#   · 旧 `gap`（推演 − 原著，越接近 0 越好）把原著当成**上限**。
#   后果在评语里看得见：《红楼梦》被扣"王熙凤未当众夸赞黛玉、未转泪，三步骨架缺了第二步"，
#   《雪国》被扣"驹子说'她恨我'时叶子不在场，原文因果接不上"。
#   **这两条都不是崩设定，是走了另一条路**——对一个给人找灵感的工具，那是功能不是缺陷。
#
# 所以：`canon` 只扣"违反世界规则 / 时代 / 称谓 / 已知事实"，**新增人物地点支线不再自动算错**；
# 新增 `novelty`（创意增量），专门奖励"原著没走、但走得有道理"的路。
# [EN] ★★★ 2026-10-18 (user): **"this software exists to give authors ideas; it does not try to
# [EN] match the original text. Reasonable variation is an important feature."**
# [EN] That sentence overturns the first scoring rubric, so record what was wrong:
# [EN] · old `plot` asked "as a **continuation** of this passage, is the advance reasonable" --
# [EN]   "continuation" itself demands fidelity to the original;
# [EN] · old pairwise asked "which is more suitable as a **direct continuation**" -- same bias;
# [EN] · old `gap` (sim - reference, closer to 0 is better) treated the original as a **ceiling**.
# [EN] The damage is visible in the comments: the Red Chamber case was docked for "Xi Feng never
# [EN] praised Dai Yu publicly and never turned to tears, the three-beat skeleton is missing step
# [EN] two", and Snow Country for "Ye Zi was not present when Komako said 她恨我, the causality does not
# [EN] connect". **Neither is a canon break -- both took another road**, which for an idea-generating
# [EN] tool is a feature, not a defect.
# [EN] So: `canon` only deducts for "violates world rules / period / forms of address / established
# [EN] facts"; **new people, places and subplots no longer count as errors**; and a new `novelty`
# [EN] dimension rewards "a road the original did not take, taken for good reasons".
DIMENSIONS = {
    "canon": ("设定不崩", 0.15),
    "character": ("人物成形", 0.20),
    "plot": ("戏能立住", 0.15),
    "prose": ("语言质地", 0.15),
    "texture": ("世界质感", 0.05),
    "engagement": ("可读性", 0.10),
    "novelty": ("创意增量", 0.20),
}

RUBRIC = """\
评分维度（每项 0–5，整数；5 = 达到出版水准，3 = 合格网文，1 = 明显坏掉）：

⚠ 这是一位作者用来**找灵感**的推演。上面给了**几条都成立的走法**——
  待评文本走了其中一条、几条的混合、或全新的第 N 条路，**都算合格**。
  **不要因为"不像第一条"而扣分。**

1. canon（设定不崩）：有没有**踩到上面任何一条硬约束**？只扣踩线：
   时代错置、称谓错、世界规则被推翻、已被前情确立的事实被改写。
   ⚠ **新增人物、地点、支线、新的可能，只要不出戏，一律不扣分**——那正是推演该干的事。
   ⚠ 也不要用"某一走法里没发生"当作冲突。
2. character（人物成形）：每个人说话、做事是否像他自己？遮住名字还认得出是谁吗？
   有没有人只会念旁白式台词？有没有把别人的心声写成他自己的？
3. plot（戏能立住）：这一段**自己**能否算一场戏——有起势、有转折、有落点？
   不要求它和任何一条走法一致；要求它内部有因果，不原地打转，也不跳着走。
4. prose（语言质地）：是否具体、克制、有细节？有没有模板腔、形容词堆砌、每句都抒情？
5. texture（世界质感）：时代、地点、器物、称谓、天气是否落地？有没有穿越感？
6. engagement（可读性）：想不想继续读下去？有没有让人出戏的地方？
7. novelty（创意增量）：**这一段给出的东西，是不是上面那几条走法都没给的**，
   而且**站得住**（不踩硬约束、人物不崩）？
   5 = 让人眼前一亮，"这个方向我没想过，但成立"，作者能顺着它往下写；
   4 = 有明显新意，只有小瑕疵；
   3 = 稳，但基本落在已知走法的范围内 —— **这就是"没有新意但也不白读"的那一档**；
   2 = 只是把某条走法换了个说法，几乎没多出东西；
   1 = 复述原文 / 复述已知走法，读完什么都没多出来。

另外给两个**描述性**字段（不打分，帮助作者理解）：
- `closest`：待评文本最接近哪条走法（填编号 `1`/`2`/`3`…，或 `new` = 都不像、自己开了一条）。
- `defects`：最多 5 条，每条一句话，指出**具体位置或句子**的问题。
  ⚠ 不要写"与原文不符"——那不是问题。要指"踩了硬约束 / 人物走形 / 语言失真 / 原地打转"。

⚠ JSON 里**不要用英文双引号**做内层引用（会破坏 JSON）：要引原文请用「」或『』。

只输出 JSON，不要解释：
{"scores":{"canon":0,"character":0,"plot":0,"prose":0,"texture":0,"engagement":0,"novelty":0},
 "closest":"new","defects":["..."],"comment":"一句话总评"}"""

SYSTEM = ("你是资深中文小说编辑，做过出版社的终审，也读大量网络小说。"
          "你评稿只看文本本身，不因为作者是谁、是不是 AI 而加减分。")


def salvage_scores(text: str) -> dict | None:
    """JSON 整份解析不了时，**只把 `scores` 抠出来**。

    为什么需要：评委偶尔在 `defects` 里写一个没转义的英文引号
    （实测 `st-01`：「Expecting ',' delimiter: line 1 column 407」），
    整份 JSON 就废了 —— 于是**一个能用的分数都没有**，报告里那一例成了 `sim: None`。
    但分数本身是好的，坏的是评语。所以退一步：只要能把 `scores` 那一段拿出来，
    这一发的评分就还算数，评语记"未能解析"。
    [EN] When the whole JSON fails to parse, **pull out just `scores`**.
    [EN] Why: the judge occasionally writes an unescaped English quote inside `defects` (measured on
    [EN] `st-01`: "Expecting ',' delimiter: line 1 column 407"), which kills the entire document --
    [EN] so **no usable score at all** and that case shows up as `sim: None` in the report. The scores
    [EN] themselves are fine; only the comments are broken. So step back: if `scores` can be extracted,
    [EN] the scoring still counts and the comments are recorded as "unparsable".
    """
    m = re.search(r'"scores"\s*:\s*\{([^{}]*)\}', text, re.S)
    if not m:
        return None
    body = m.group(1)
    out: dict[str, float] = {}
    for k in DIMENSIONS:
        mm = re.search(r'"' + k + r'"\s*:\s*([0-9.]+)', body)
        if mm:
            try:
                out[k] = max(0.0, min(5.0, float(mm.group(1))))
            except ValueError:
                continue
    if len(out) < len(DIMENSIONS):
        return None
    return out


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    head = int(limit * 0.65)
    tail = limit - head
    return text[:head] + "\n……（中段略）……\n" + text[-tail:]


def _bible_digest(work: Work) -> str:
    b = work.bible
    lines = [f"《{work.title}》（{work.author}）· {'/'.join(work.genres)}", "",
             "【世界观】", str(b.get("worldview") or "").strip(), "", "【人物】"]
    for p in b.get("people") or []:
        p = p or {}
        lines.append(
            f"- {p.get('姓名')}：{p.get('身份')}；性格：{p.get('性格')}；"
            f"口癖：{p.get('口癖') or '—'}；目标：{p.get('目标') or '—'}；"
            f"秘密：{p.get('秘密') or '—'}")
    rules = b.get("rules") or []
    if rules:
        lines += ["", "【铁律】"] + [f"- {r}" for r in rules]
    style = work.style()
    lines += ["", "【写法】", f"视角：{style.get('pov', '—')}；{style.get('sentence', '')}"]
    return "\n".join(lines)


def _case_digest(case: Case) -> str:
    return "\n".join([
        f"【切入点】{case.cut} · {case.place} · {case.story_time}",
        f"【在场】{'、'.join(case.present)}",
        "【前情提要】", case.previously or "（这是开篇，没有前情）", "",
        "【此刻】", case.scene_seed,
    ])


def _truth_digest(case: Case) -> str:
    """**硬约束 + 多条合法走法**（2026-10-18 重写）。

    ★★★ 用户："不追求跟原文完全相同，合理范围内的变化是重要功能"。
    所以这里不再给"标准答案"，改给两样东西：

    1. **硬约束**（`case.hard`）—— 所有走法都不许踩的线。这才是"错"的定义。
    2. **几条都合格的走法**（`case.all_paths()`）—— 它们**互不相同**，
       摆在评委面前是为了让评委看见"这个岔口本来就有好几条路"，
       从而不去奖励"像第一条"，而去分辨"哪条更站得住、哪条更有新意"。

    ⚠ 第一版这里是"作者实际写下的后续（仅供对照）"+ 逐条 beats ——
      嘴上说不用复刻，实际递了份标杆答案，评委当然照着扣分
      （《红楼梦》因此被扣"三步骨架缺第二步"）。
    [EN] **Hard constraints + several legitimate paths** (rewritten 2026-10-18).
    [EN] The user: "not trying to match the original; reasonable variation is a feature". So this no
    [EN] longer hands over an answer key, but two things:
    [EN] 1. **Hard constraints** (`case.hard`) -- the lines no path may cross. This is what "wrong"
    [EN]    now means.
    [EN] 2. **Several equally acceptable paths** (`case.all_paths()`) -- deliberately *different* from
    [EN]    each other, shown so the judge sees "this fork had several roads" and stops rewarding
    [EN]    "looks like the first one", instead judging which stands up better and which is fresher.
    [EN] ⚠ The first version said "the author's actual continuation (for reference only)" followed by
    [EN] the beats -- it denied being a key while handing over exactly a key, and the judge graded
    [EN] against it (that is why the Red Chamber case was docked for "the three-beat skeleton is
    [EN] missing step two").
    """
    out: list[str] = []
    hard = case.hard
    if hard:
        out += ["【硬约束 —— 任何走法都不许踩这些线】"]
        out += [f"- {h}" for h in hard]
        out.append("")
    paths = case.all_paths()
    out.append(f"【这个岔口上，已知有 {len(paths)} 条**都成立**的走法"
               "（它们故意互不相同；**不是标准答案，也不是要你选一条最像的**）】")
    for i, p_ in enumerate(paths, 1):
        out.append(f"\n走法 {i}｜{p_['stance']}")
        if p_.get("why_valid"):
            out.append(f"  为什么成立：{p_['why_valid']}")
        for b in p_.get("beats") or []:
            out.append(f"  · {b}")
        ex = (p_.get("excerpt") or "").strip()
        if ex:
            out.append(f"  原文摘录：{ex}")
    if case.divergence_note:
        out += ["", f"【出题人的话】{case.divergence_note}"]
    out += ["", "⚠ 上面这些走法**都算合格**。待评文本走了其中一条、走了它们的混合、"
                "或者走了第 N 条全新的路，都可以——只要不踩硬约束。"]
    return "\n".join(out)


# ★★★ 2026-10-18（口径纠偏）：给"参考片段"的说明必须点明**它不是评分标准**。
#   否则评委会把"原著"当成自带光环的东西，`novelty` 那一项对它一律给高分 ——
#   那就等于又回到了"以原著为上限"。
#   （⚠ 这段定义在 2026-10-18 重写 `_truth_digest` 时被误删过一次，
#     报错是 `NameError: REF_NOTE`，评审直接崩 —— 判据 C1 本该抓到，
#     但它只查两个字符串，查不到"变量未定义"。已补。）
# [EN] ★★★ 2026-10-18 (stance correction): the note for the "reference excerpt" must state that it
# [EN] is **not the scoring standard**. Otherwise the judge treats "the original" as self-illuminating
# [EN] and hands out high `novelty` to it -- which puts the original back on top as a ceiling.
# [EN] (⚠ This definition was accidentally deleted while rewriting `_truth_digest` on 2026-10-18; the
# [EN] error was `NameError: REF_NOTE` and the review crashed. Criterion C1 should have caught it but
# [EN] only checks two strings, not "variable undefined". Fixed.)
REF_NOTE = ("【评分说明】下面这段是从原著里截取的一小段。"
            "**它不是评分标准，只是同一把尺子的校准点。** 只评它自身的写法、人物与推进；"
            "不要因为它没有交代前因后果、篇幅短而扣分。"
            "也**不要因为它是原著就加分**——`novelty` 这一项对它通常不高，就照实给。")


def _point_prompt(work: Work, case: Case, target: str, label: str,
                  is_ref: bool = False) -> str:
    parts = ["下面是一部小说的设定与一个中断点。请评价【待评文本】。",
             _bible_digest(work), _case_digest(case), _truth_digest(case)]
    if is_ref:
        parts.append(REF_NOTE)
    parts += [f"【待评文本 · {label}】\n{target}", RUBRIC]
    return "\n\n".join(parts)


def _pair_prompt(work: Work, case: Case, a: str, b: str) -> str:
    return "\n\n".join([
        "下面是一部小说的设定与一个中断点。甲、乙是两段候选推演——",
        "**这是一位作者用来找灵感的工具，不要求任何一段去复刻原著。**",
        "请判断：**哪一段更值得作者拿去参考**——更可能给他一个能往下写的方向。",
        "参考标准依次是：不违背设定 > 人物像他自己 > 这段自己能立住 > 有让人眼前一亮的东西 > 语言不假。"
        "⚠ **不要因为哪一段「更像原著」就判它更好**；和原文走了不同的路，只要站得住，就该加分。"
        "两段长度不同是正常的（一段是分拍实录，一段是成稿），**不要因为哪段更长就判它更好**。"
        "两段难分高下就判 tie，不要为了不判平局而硬选。",
        _bible_digest(work), _case_digest(case), _truth_digest(case),
        f"【甲】\n{a}", f"【乙】\n{b}",
        '只输出 JSON：{"winner":"甲|乙|tie","reason":"一句话"}',
    ])


class Judge:
    def __init__(self, profiles: list[JudgeProfile], cfg: Settings,
                 cache_path: Path | None = None):
        self.profiles = profiles
        self.cfg = cfg
        self.cache_path = cache_path or (cfg.output_dir / "judge_cache.jsonl")
        self._cache: dict[str, str] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        if not self.cache_path.is_file():
            return
        for line in self.cache_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
                self._cache[row["k"]] = row["v"]
            except Exception:                        # noqa: BLE001
                continue

    def _key(self, profile: JudgeProfile, prompt: str) -> str:
        raw = f"{profile.model}\x00{profile.temperature}\x00{prompt}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _ask(self, profile: JudgeProfile, prompt: str) -> str:
        k = self._key(profile, prompt)
        if k in self._cache:
            return self._cache[k]
        out = chat(profile, SYSTEM, prompt)
        self._cache[k] = out
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"k": k, "v": out, "model": profile.model}, ensure_ascii=False) + "\n")
        return out

    def pointwise(self, work: Work, case: Case, text: str, label: str,
                  is_ref: bool = False) -> dict:
        limit = self.cfg.judge_max_chars
        prompt = _point_prompt(work, case, _clip(text, limit), label, is_ref=is_ref)
        rows = []
        for p in self.profiles:
            # ⚠ `raw` 必须在 try **外面**先赋空串：`_ask` 本身可能抛（网络/限额），
            #   那时 try 里的赋值没执行过 —— 原来用 `raw if 'raw' in dir() else ""`
            #   兜，既不可靠又难读。
            # [EN] ⚠ `raw` must be initialised **before** the try: `_ask` itself can raise (network /
            # [EN] quota) and then the assignment never happened. The old `raw if 'raw' in dir() else ""`
            # [EN] guard was both unreliable and hard to read.
            raw = ""
            try:
                raw = self._ask(p, prompt)
                data = parse_json(raw)
            except (LLMError, json.JSONDecodeError, ValueError) as e:
                # ★ 2026-10-18：整份 JSON 废了就退一步，只救 scores（见 `salvage_scores`）。
                # [EN] ★ 2026-10-18: if the whole document is dead, step back and salvage only
                # [EN] `scores` (see `salvage_scores`).
                salv = salvage_scores(raw) if raw else None
                if salv:
                    rows.append({"judge": p.name, "scores": salv,
                                 "closest": "", "defects": [],
                                 "comment": "（评语未解析：JSON 损坏，分数已救回）"})
                else:
                    rows.append({"judge": p.name, "error": str(e)[:200]})
                continue
            scores = data.get("scores") or {}
            clean = {}
            for k in DIMENSIONS:
                try:
                    clean[k] = max(0.0, min(5.0, float(scores.get(k, 0))))
                except (TypeError, ValueError):
                    clean[k] = 0.0
            rows.append({"judge": p.name, "scores": clean,
                         # ★ 2026-10-18：`closest` = 最接近哪条已知走法（`new` = 自己开了一条）。
                         #   它是**描述性**的，不打分；但报告里很有用：
                         #   "多数用例都 closest=1"说明推演倾向于复刻，那正是 novelty 上不去的原因。
                         # [EN] ★ 2026-10-18: `closest` = which known path it is nearest to (`new` = opened
                         # [EN] its own). Descriptive, not scored -- but very useful in the report: "most
                         # [EN] cases are closest=1" means the run tends to re-tell path one, which is
                         # [EN] exactly why novelty stays low.
                         "closest": str(data.get("closest") or "").strip(),
                         "defects": [str(x)[:160] for x in (data.get("defects") or [])][:5],
                         "comment": str(data.get("comment") or "")[:300]})
        ok = [r for r in rows if "scores" in r]
        if not ok:
            return {"error": rows[0]["error"] if rows else "no judge", "raw": rows}
        merged = {}
        for k in DIMENSIONS:
            vals = sorted(r["scores"][k] for r in ok)
            merged[k] = vals[len(vals) // 2]
        closest = [r.get("closest") for r in ok if r.get("closest")]
        return {
            "scores": merged,
            "closest": closest[0] if closest else "",
            "weighted_100": round(sum(merged[k] * w for k, (_n, w) in DIMENSIONS.items()) / 5 * 100, 1),
            "defects": [d for r in ok for d in r.get("defects", [])][:8],
            "comment": ok[0].get("comment", ""),
            "per_judge": rows,
        }

    def pairwise(self, work: Work, case: Case, sim: str, ref: str) -> dict:
        if not self.cfg.pairwise:
            return {"skipped": True}
        limit = self.cfg.judge_max_chars
        sim, ref = _clip(sim, limit), _clip(ref, limit)
        rng = random.Random(f"{self.cfg.seed}:{case.id}")
        sim_first = rng.random() < 0.5
        votes: list[str] = []          # "sim" | "ref" | "tie"
        details = []
        for p in self.profiles:
            for order in (0, 1):
                if (order == 0) == sim_first:
                    a, b, a_role, b_role = sim, ref, "sim", "ref"
                else:
                    a, b, a_role, b_role = ref, sim, "ref", "sim"
                try:
                    data = parse_json(self._ask(p, _pair_prompt(work, case, a, b)))
                except (LLMError, json.JSONDecodeError, ValueError) as e:
                    details.append({"judge": p.name, "error": str(e)[:160]})
                    continue
                w = str(data.get("winner") or "").strip()
                picked = "tie"
                if w in ("甲", "A", "a"):
                    picked = a_role
                elif w in ("乙", "B", "b"):
                    picked = b_role
                votes.append(picked)
                details.append({"judge": p.name, "order": order, "vote": picked,
                                "reason": str(data.get("reason") or "")[:200]})
        if not votes:
            return {"error": "no pairwise result", "details": details}
        # consistency across the two orders is required for a win
        sim_votes = votes.count("sim")
        ref_votes = votes.count("ref")
        if sim_votes and ref_votes:
            verdict = "tie"
        elif sim_votes:
            verdict = "sim"
        elif ref_votes:
            verdict = "ref"
        else:
            verdict = "tie"
        return {"verdict": verdict, "votes": votes, "details": details}


def review_case(work: Work, case: Case, case_dir: Path, judge: Judge) -> dict:
    tpath = case_dir / "transcript.jsonl"
    if not tpath.is_file():
        return {"case": case.id, "error": "no transcript"}
    from .metrics import load_result_text, prose_entries

    rows = []
    for line in tpath.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    novel_text, source = load_result_text(case_dir)
    sim = novel_text or "\n".join(e["text"].strip() for e in prose_entries(rows))
    if not sim:
        return {"case": case.id, "error": "empty transcript"}

    t0 = time.time()
    sim_res = judge.pointwise(work, case, sim, "推演实录（分拍记录，台词带说话人）")
    ref_res = judge.pointwise(work, case, case.excerpt, "参考片段", is_ref=True)
    pair = judge.pairwise(work, case, sim, case.excerpt)
    out = {
        "case": case.id,
        "work": work.id,
        "source": source,
        #: 这个用例给了几条"都成立"的走法（含作者那条）。≥2 才叫"多答案"。
        #: [EN] How many equally valid paths this case provides (including the author's).
        #: [EN] >= 2 is what "multiple acceptable answers" means.
        "paths": len(case.all_paths()),
        "hard_constraints": len(case.hard),
        "title": work.title,
        "sim": sim_res,
        "ref": ref_res,
        "pairwise": pair,
        "seconds": round(time.time() - t0, 1),
    }
    if "weighted_100" in sim_res and "weighted_100" in ref_res:
        out["gap"] = round(sim_res["weighted_100"] - ref_res["weighted_100"], 1)
    (case_dir / "judge.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
