# -*- coding: utf-8 -*-
"""Dataset loading + schema validation.

One YAML file per work under ``dataset/works/``.  A work carries:

* ``bible`` -- the setting collection that the simulator will actually run on
  (worldview / rules / people / places / relations / foreshadows / details /
  style).  It is deliberately short: ~800-1500 characters.  A benchmark that
  costs an hour per case never gets run, and the point here is to expose
  *structural* quality problems (voice drift, repetition, pacing) rather than
  to reproduce an entire novel.
* ``cases`` -- one or more cut points.  Each case carries the recap that a
  human would need (``previously``), the exact moment the simulation starts
  (``scene_seed``), and the ground truth of what the author actually wrote
  next (``ground_truth``).

The YAML is validated against the schema below; ``check`` prints one line per
problem so a bad hand edit is caught before an expensive run.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import BENCH_DIR

WORKS_DIR = BENCH_DIR / "dataset" / "works"

CATEGORIES = {"古典", "现代", "当代", "网络"}
MEDIA = {"出版", "网络"}
POV_TAGS = {"第一人称", "第三人称限知", "第三人称全知", "多视角", "书信", "剧本"}

REQUIRED_WORK = ("id", "title", "author", "country", "language", "category",
                 "medium", "genres", "representativeness", "bible", "cases")
REQUIRED_BIBLE = ("worldview", "people")
REQUIRED_CASE = ("id", "cut", "place", "present", "scene_seed", "ground_truth")
GT_KEYS = ("beats", "excerpt")


#: 中文时段 → `HH:MM`。**只收"能确定"的**，含糊的一律不收（查不到就报错，
#: 别猜 —— 猜错会让整场的时钟、天气、光线全错，而这种错在报告上完全看不见）。
#: [EN] Chinese time-of-day -> `HH:MM`. **Only unambiguous ones**, vague terms are deliberately
#: absent (an unknown value is reported, never guessed -- guessing puts the clock, weather and light
#: of the whole scene in the wrong place, and that kind of error is invisible in the report).
PHASE_CLOCK: dict[str, str] = {
    "拂晓": "05:00", "清晨": "06:00", "一早": "07:00", "辰时": "08:00",
    "上午": "09:00", "晌午": "11:30", "正午": "12:00", "中午": "12:00",
    "午后": "14:00", "下午": "15:00", "傍晚": "18:00", "黄昏": "18:30",
    "入夜": "19:30", "晚上": "20:00", "夜晚": "21:00", "夜里": "22:30",
    "深夜": "23:30",
    "半夜": "00:30", "凌晨": "03:00",
}


def clock_of(story_time: str) -> str:
    """把用例里的 `story_time` 变成 `HH:MM`；认不出返回空串（调用方负责报错）。

    为什么要这一层：程序的 `GAME_START_TIME` **只认带冒号的 `HH:MM`**
    （见 `sim/setup._start_clock`），传"午后"会被静默忽略、退回 08:00。
    2026-10-18 第一轮四例全中：`story_time` 写的是"午后""深夜"，
    产物一律从"辰时"开始，被评委记成"时间标注与正文冲突"
    （《聊斋》午后、《嫌疑人X》深夜，都成了辰时）。
    [EN] Turn a case's `story_time` into `HH:MM`; return "" when unrecognized (caller reports it).
    [EN] Why this layer exists: the app's `GAME_START_TIME` **only accepts `HH:MM` with a colon**
    [EN] (see `sim/setup._start_clock`); passing "午后" is silently ignored and falls back to 08:00.
    [EN] All four cases of the first round hit this on 2026-10-18: `story_time` said "午后"/"深夜"
    [EN] while every transcript started at "辰时", and the judge recorded it as "time label conflicts
    [EN] with the text" (Liao Zhai was an afternoon scene, Suspect X a late night -- both became 辰时).
    """
    raw = str(story_time or "").strip()
    if not raw:
        return ""
    m = re.fullmatch(r"(\d{1,2})[:：](\d{2})", raw)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"
        return ""
    return PHASE_CLOCK.get(raw, "")


@dataclass
class Case:
    id: str
    cut: str                     # 开篇 / 中段 / 转折 / 高潮前 / 收束
    place: str
    present: list[str]
    scene_seed: str
    previously: str = ""
    story_time: str = "09:00"
    focus: list[str] = field(default_factory=list)
    at: str = ""
    ground_truth: dict[str, Any] = field(default_factory=dict)
    work: "Work | None" = None

    @property
    def beats(self) -> list[str]:
        b = self.ground_truth.get("beats") or []
        return [str(x) for x in b]

    @property
    def excerpt(self) -> str:
        return str(self.ground_truth.get("excerpt") or "")

    @property
    def divergence_note(self) -> str:
        return str(self.ground_truth.get("divergence_note") or "")

    # ── 多合法走法（2026-10-18 加，用户要求）─────────────────────────
    @property
    def hard(self) -> list[str]:
        """**所有合法走法都不许违背的硬约束**（世界规则、时代、称谓、已知事实）。

        为什么要有这一层：一旦承认"可以走别的路"，就必须回答"那到底什么算错"。
        答案不是"不像原文"，而是**踩了这些线**。所以约束来自设定，不来自原文情节。

        ⚠ 只写"不许什么"，不写"必须发生什么"。写了后者，就等于又给了一个标准答案。
        [EN] **Hard constraints no legitimate path may violate** (world rules, period, forms of
        address, established facts). Once "other roads are allowed" is accepted, the next question is
        "then what counts as wrong" -- and the answer is *these lines*, not "unlike the source". So
        the constraints come from the settings, never from the original plot.
        ⚠ Write only "must not", never "must happen" -- the latter is just another answer key.
        """
        out = self.ground_truth.get("hard") or []
        return [str(x).strip() for x in out if str(x).strip()]

    @property
    def alternatives(self) -> list[dict]:
        """2–3 条**都符合要求**的走法。第一条永远是作者实际走的那条。

        每条：`{'stance': 取径标签, 'beats': [...], 'excerpt': 文本, 'why_valid': 为什么成立}`。
        这是"给作者找灵感"这个定位在数据上的落实：评价一段推演时，问的不该是
        "它等于第几条"，而是"**它是否踩了 hard 里的线**"；都没踩就都算合格，
        再去比它有没有给出原文没给的东西（`novelty`）。

        ⚠ `stance` 必须是**取径**（"凤姐不提黛玉家事，转而先问月例"），
          不是**质量评价**（"更好的写法"）。后者会把评委往一个方向带。
        [EN] 2-3 **equally acceptable** paths; the first is always the one the author took.
        [EN] This is the "idea generator" stance expressed in data: judging a passage should ask
        [EN] "did it cross a line in `hard`", not "does it equal path N". Nothing crossed => all
        [EN] acceptable, then compare whether it offered something the source did not (`novelty`).
        [EN] ⚠ `stance` must describe a **route** ("Xifeng skips Dai Yu's family and asks about the
        [EN] monthly allowance first"), never a **quality verdict** ("the better version") -- the
        [EN] latter steers the judge.
        """
        out: list[dict] = []
        raw = self.ground_truth.get("alternatives") or []
        if isinstance(raw, list):
            for a in raw:
                if not isinstance(a, dict):
                    continue
                out.append({
                    "stance": str(a.get("stance") or "").strip(),
                    "beats": [str(x) for x in (a.get("beats") or [])],
                    "excerpt": str(a.get("excerpt") or "").strip(),
                    "why_valid": str(a.get("why_valid") or "").strip(),
                })
        return out

    def all_paths(self) -> list[dict]:
        """统一视图：作者那条 + `alternatives`。

        把作者那条也当成一条"路径"，而不是"答案"——否则调用方总会不自觉地把它特殊对待。
        [EN] A uniform view: the author's path plus `alternatives`. Treating the author's text as
        [EN] just another path (not "the answer") keeps callers from special-casing it.
        """
        paths = [{"stance": "作者实际写的（原著）", "beats": self.beats,
                  "excerpt": self.excerpt, "why_valid": ""}]
        paths += self.alternatives
        return paths


@dataclass
class Work:
    id: str
    title: str
    author: str
    country: str
    language: str
    category: str
    medium: str
    genres: list[str]
    representativeness: str
    bible: dict[str, Any]
    cases: list[Case]
    year: str = ""
    title_en: str = ""
    license: str = "public_domain"
    path: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def people_names(self) -> list[str]:
        out = []
        for p in self.bible.get("people") or []:
            n = str((p or {}).get("姓名") or "").strip()
            if n:
                out.append(n)
        return out

    def people_aliases(self) -> dict[str, list[str]]:
        """每个人物的**别称**：`{本名: [称谓, 代称, ...]}`。

        ★★★ 2026-10-18 加。为什么必须有：中文小说里人物**本来就该按称谓写** ——
        《红楼梦》里王熙凤在场时写"奶奶"、王夫人写"太太"、贾母写"老太太"，
        《聊斋》写"女""老媪"，《嫌疑人X》从美里视角写"母亲"。
        这些全是**正确写法**，但原先的 `present_coverage` 只按姓名精确匹配，
        于是把"写对了"判成"在场却没出场"（实测 4 例里有 3 例误报，
        红楼梦 0.25、聊斋 0.33、嫌疑人X 0.67）。**指标惩罚了正确行为**，
        比漏报还糟 —— 它会把人往错的方向推。

        ⚠ 别称写在作品 YAML 的 `people[].别称` 里，是**作品知识**，不是通用规则：
          「奶奶」在红楼是王熙凤，「奶奶」在别处可能是任何人。所以不许在指标里
          写死一张称谓表。
        ⚠ `check` 会校验"某人的别称不能等于别人的姓名"，否则两个人会互相顶替。

            English:
        Each character's **aliases**: `{real name: [title, metonym, ...]}`.
            ★★★ Added 2026-10-18. Why it is mandatory: in Chinese fiction, characters are
            **supposed to be written by their title** -- when Wang Xifeng is present, Dream of the Red
            Chamber writes "奶奶" (young mistress), Wang Furen is "太太", the matriarch is "老太太";
            Liao Zhai writes "女"/"老媪"; Suspect X writes "母亲" from the daughter's point of view.
            All of these are **correct writing**, but the original `present_coverage` matched real
            names only, so it graded "written correctly" as "present but absent" (3 of 4 measured
            cases were false alarms: 0.25 / 0.33 / 0.67). **The metric punished correct behaviour**,
            which is worse than missing it -- it pushes people the wrong way.
            ⚠ Aliases live in the work YAML under `people[].别称` as **work knowledge**, not a
            general rule: "奶奶" is Wang Xifeng in this novel and could be anyone elsewhere. So the
            metric must never hardcode an alias table.
            ⚠ `check` verifies that one person's alias is not another person's real name, otherwise
            the two would stand in for each other.
        """
        out: dict[str, list[str]] = {}
        for p in self.bible.get("people") or []:
            p = p or {}
            name = str(p.get("姓名") or "").strip()
            if not name:
                continue
            al = [str(a).strip() for a in (p.get("别称") or []) if str(a).strip()]
            out[name] = [a for a in al if a != name]
        return out

    def style(self) -> dict[str, Any]:
        return self.bible.get("style") or {}


def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else []


def load_work(path: Path) -> Work:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases: list[Case] = []
    for c in _as_list(data.get("cases")):
        cases.append(Case(
            id=str(c.get("id") or ""),
            cut=str(c.get("cut") or "中段"),
            place=str(c.get("place") or ""),
            present=[str(x) for x in _as_list(c.get("present"))],
            scene_seed=str(c.get("scene_seed") or "").strip(),
            previously=str(c.get("previously") or "").strip(),
            story_time=str(c.get("story_time") or "09:00"),
            focus=[str(x) for x in _as_list(c.get("focus"))],
            at=str(c.get("at") or ""),
            ground_truth=c.get("ground_truth") or {},
        ))
    w = Work(
        id=str(data.get("id") or path.stem),
        title=str(data.get("title") or ""),
        author=str(data.get("author") or ""),
        country=str(data.get("country") or ""),
        language=str(data.get("language") or "zh"),
        category=str(data.get("category") or ""),
        medium=str(data.get("medium") or "出版"),
        genres=[str(x) for x in _as_list(data.get("genres"))],
        representativeness=str(data.get("representativeness") or "").strip(),
        bible=data.get("bible") or {},
        cases=cases,
        year=str(data.get("year") or ""),
        title_en=str(data.get("title_en") or ""),
        license=str(data.get("license") or "public_domain"),
        path=path,
        raw=data,
    )
    for c in w.cases:
        c.work = w
    return w


def load_all(works_dir: Path | None = None) -> list[Work]:
    d = works_dir or WORKS_DIR
    out: list[Work] = []
    for p in sorted(d.glob("*.yaml")):
        out.append(load_work(p))
    return out


def find_case(works: list[Work], case_id: str) -> tuple[Work, Case] | tuple[None, None]:
    # ⚠ 这个函数**只查找，不校验**。2026-10-18 曾把两段校验误插在这里：
    #   它们在 `find_case` 的作用域里引用了 `issues` / `tag`（不存在），
    #   而 `check` 从不调用 `find_case` ⇒ **校验从来没跑过，`check` 一直假绿**。
    #   校验只有一处：`validate()`。
    # [EN] ⚠ **Lookup only, no validation.** On 2026-10-18 two validation blocks were
    # [EN] accidentally inserted here: they referenced `issues` / `tag` which do not exist
    # [EN] in this scope, and `check` never calls `find_case` ⇒ **the checks never ran and
    # [EN] `check` was falsely green the whole time**. Validation lives in `validate()` only.
    for w in works:
        for c in w.cases:
            if c.id == case_id:
                return w, c
    return None, None


def load_presets(path: Path | None = None) -> dict[str, list[str]]:
    p = path or (BENCH_DIR / "dataset" / "presets.yaml")
    if not p.is_file():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out: dict[str, list[str]] = {}
    for k, v in data.items():
        if isinstance(v, list):
            out[str(k)] = [str(x) for x in v]
        elif isinstance(v, dict) and isinstance(v.get("cases"), list):
            out[str(k)] = [str(x) for x in v["cases"]]
    return out


def validate(works: list[Work]) -> list[str]:
    """Return a list of human-readable schema problems (empty == clean)."""
    issues: list[str] = []
    seen_work: set[str] = set()
    seen_case: set[str] = set()

    for w in works:
        tag = w.path.name if w.path else w.id
        for key in REQUIRED_WORK:
            if not getattr(w, key, None):
                issues.append(f"[{tag}] missing field: {key}")
        if w.id in seen_work:
            issues.append(f"[{tag}] duplicate work id: {w.id}")
        seen_work.add(w.id)
        if w.category and w.category not in CATEGORIES:
            issues.append(f"[{tag}] unknown category {w.category!r} (expect one of {sorted(CATEGORIES)})")
        if w.medium and w.medium not in MEDIA:
            issues.append(f"[{tag}] unknown medium {w.medium!r} (expect one of {sorted(MEDIA)})")
        if not w.genres:
            issues.append(f"[{tag}] genres is empty")
        for key in REQUIRED_BIBLE:
            if not w.bible.get(key):
                issues.append(f"[{tag}] bible.{key} is empty")
        people = w.bible.get("people") or []
        if len(people) < 2:
            issues.append(f"[{tag}] bible.people needs >=2 entries (got {len(people)})")
        names = set()
        for p in people:
            if not isinstance(p, dict) or not p.get("姓名"):
                issues.append(f"[{tag}] a person entry has no 姓名: {p!r}")
                continue
            names.add(str(p["姓名"]))
            for k in ("身份", "性格"):
                if not p.get(k):
                    issues.append(f"[{tag}] person {p['姓名']} has no {k}")
        # ★★★ 2026-10-18：别称校验（三条都是"会静默出错"的那种）。
        #   ① 单字别称 —— 指标层不收（会被"女儿""学生"误命中），数据里写了也不生效，
        #      等于假配置，必须当场报出来；
        #   ② 别称等于**别人的姓名** —— 两个人会互相顶替，出场率直接错；
        #   ③ 同一部里两人共用别称 —— 同上。
        # [EN] ★★★ 2026-10-18: alias validation (all three fail silently).
        # [EN] ① single-character aliases -- the metric ignores them (they would hit "女儿"/"学生"),
        # [EN] so writing one is a fake setting and must be reported on the spot;
        # [EN] ② an alias equal to **someone else's real name** -- the two would stand in for each
        # [EN] other and coverage goes wrong; ③ two people sharing one alias -- same.
        alias_owner: dict[str, str] = {}
        for p in people:
            if not isinstance(p, dict) or not p.get("姓名"):
                continue
            owner = str(p["姓名"])
            for a in (p.get("别称") or []):
                a = str(a).strip()
                if not a:
                    continue
                if len(a) < 2:
                    issues.append(f"[{tag}] person {owner} alias {a!r} is a single character "
                                  f"(metric ignores it; write 2+ chars such as 「女子」)")
                elif a in names and a != owner:
                    issues.append(f"[{tag}] person {owner} alias {a!r} is another person's name")
                elif a in alias_owner and alias_owner[a] != owner:
                    issues.append(f"[{tag}] alias {a!r} claimed by both "
                                  f"{alias_owner[a]} and {owner}")
                else:
                    alias_owner[a] = owner
        for r in (w.bible.get("relations") or []):
            if not isinstance(r, dict) or not (r.get("甲") and r.get("乙")):
                issues.append(f"[{tag}] relation entry needs 甲/乙: {r!r}")
                continue
            for side in ("甲", "乙"):
                if str(r[side]) not in names:
                    issues.append(f"[{tag}] relation {r['甲']}-{r['乙']} references unknown person {r[side]}")
        pov = (w.bible.get("style") or {}).get("pov")
        if pov and str(pov) not in POV_TAGS:
            issues.append(f"[{tag}] style.pov {pov!r} not in {sorted(POV_TAGS)}")

        if not w.cases:
            issues.append(f"[{tag}] has no cases")
        for c in w.cases:
            ctag = f"{tag}:{c.id or '?'}"
            if not c.id:
                issues.append(f"[{ctag}] case has no id")
            if c.id in seen_case:
                issues.append(f"[{ctag}] duplicate case id {c.id}")
            seen_case.add(c.id)
            for key in REQUIRED_CASE:
                if not getattr(c, key, None):
                    issues.append(f"[{ctag}] missing field: {key}")
            if c.cut != "开篇" and not c.previously:
                issues.append(f"[{ctag}] non-opening case must carry `previously` (recap)")
            # ★★★ 2026-10-18（用户要求"多个符合要求的结果集"）：每个用例必须给
            #   ≥1 条硬约束 + ≥1 条 `alternatives` ⇒ 总共 ≥2 条合法走法。
            #   ⚠ 缺了它，评测就退化成"像不像原文"，而那正是用户明确否定的口径。
            #   ⚠⚠ 这一段曾被误插进 `find_case()`（作用域里没有 `issues`），
            #     于是**从来没执行过、`check` 一直假绿**。校验只许写在 `validate()` 里，
            #     并由 `verify_bench_tool.py` 的"空数据集必须报红"一条守着。
            # [EN] ★★★ 2026-10-18 (the user asked for "multiple results that all satisfy the
            # [EN] requirement"): every case needs >=1 hard constraint and >=1 `alternatives` entry
            # [EN] => >=2 legitimate paths total. Without them the evaluation degenerates into
            # [EN] "does it look like the source", the stance the user explicitly rejected.
            # [EN] ⚠⚠ This block was once inserted into `find_case()` by mistake (no `issues` in that
            # [EN] scope), so it **never ran and `check` was falsely green throughout**. Validation
            # [EN] belongs in `validate()` only, guarded by `verify_bench_tool.py`'s
            # [EN] "an empty dataset must go red" assertion.
            if not c.hard:
                issues.append(f"[{ctag}] has no ground_truth.hard "
                              f"(need >=1 line that no path may cross)")
            if len(c.all_paths()) < 2:
                issues.append(f"[{ctag}] gives only 1 valid path "
                              f"(need >=2: add at least one entry under ground_truth.alternatives)")
            for _a, alt in enumerate(c.alternatives, 1):
                if not alt["stance"]:
                    issues.append(f"[{ctag}] alternatives[{_a}] has no stance "
                                  f"(describe the ROUTE, not a quality verdict)")
                if not alt["beats"] and not alt["excerpt"]:
                    issues.append(f"[{ctag}] alternatives[{_a}] has neither beats nor excerpt")
            for h in c.hard:
                if h.startswith(("必须", "一定要", "务必", "must")):
                    issues.append(f"[{ctag}] hard constraint starts with {h[:6]!r} "
                                  f"-- write only what must NOT happen")
            # ★★ `story_time` 必须是 `HH:MM` 或表里认得的时段：程序只认带冒号的形式，
            #   认不出就静默退回 08:00（辰时）—— 第一轮四例全中。
            # [EN] ★★ `story_time` must be `HH:MM` or a known phase: the app only accepts the colon
            # [EN] form and silently falls back to 08:00 -- all four cases of round one hit this.
            if c.story_time and not clock_of(c.story_time):
                issues.append(f"[{ctag}] story_time {c.story_time!r} is neither HH:MM nor a known "
                              f"phase ({'/'.join(sorted(PHASE_CLOCK))})")
            if c.cut == "开篇" and c.previously:
                issues.append(f"[{ctag}] opening case should leave `previously` empty")
            for n in c.present:
                if n not in names:
                    issues.append(f"[{ctag}] present person {n!r} is not in bible.people")
            if len(c.scene_seed) < 30:
                issues.append(f"[{ctag}] scene_seed too short ({len(c.scene_seed)} chars)")
            gt = c.ground_truth or {}
            if not gt.get("beats"):
                issues.append(f"[{ctag}] ground_truth.beats is empty")
            if not c.excerpt:
                issues.append(f"[{ctag}] ground_truth.excerpt is empty")
            if len(c.excerpt) > 1500:
                issues.append(f"[{ctag}] ground_truth.excerpt too long ({len(c.excerpt)} chars)")
    return issues


def stats(works: list[Work]) -> dict[str, Any]:
    cases = [c for w in works for c in w.cases]
    by_cat: dict[str, int] = {}
    by_medium: dict[str, int] = {}
    by_country: dict[str, int] = {}
    for w in works:
        by_cat[w.category] = by_cat.get(w.category, 0) + 1
        by_medium[w.medium] = by_medium.get(w.medium, 0) + 1
        by_country[w.country] = by_country.get(w.country, 0) + 1
    bible_chars = sum(len(str(w.bible.get("worldview") or "")) for w in works)
    return {
        "works": len(works),
        "cases": len(cases),
        "by_category": by_cat,
        "by_medium": by_medium,
        "by_country": by_country,
        "genres": sorted({g for w in works for g in w.genres}),
        "bible_chars_total": bible_chars,
    }
