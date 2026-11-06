# -*- coding: utf-8 -*-
"""**导演盯戏** —— 查"好几个人各自独立地重复同一件事/同一句话"。

用户 2026-10-07
---------------
「我看到有好几个人连续重复一句话 一件事情的问题(之前是一个人单独
  现在我发现了有几个人一起单独做一件事的问题 注意升级导演能力
  演员演绎过程中 导演要一直盯着 如果有演员演的台词和动作不对 要及时提出来
  导演随时可以要求回档 即删除最近生成的一段戏 然后导演可以要求暂停表演
  自己想一下刚才的戏 要求演员修改 如果必要的话 可能会找剧作家 小说作者
  临时开会 修改剧本和小说故事之后重新开始 导演要一直心里有一个大纲
  从顶层到细节一直把控剧情进展)」

它和"单人复读"的分工（这两件事**必须在不同的层解决**）
-------------------------------------------------------
| 毛病 | 在哪解决 | 为什么 |
|---|---|---|
| **同一个人**说同一句话 | `SceneBuilder._said` + `sim/loop._review_repeat` | 那人自己的问题，问他自己就行 |
| **好几个人各自**说同一句话 | **本模块** | 单看每一个都对（各人只说了一次），**只有合起来看才看得出重复** |

第二类是这个模块存在的全部理由 —— 它**任何单个演员的护栏都抓不到**，
因为对每个人来说那句话都是"第一次说"。

三条口径（改之前先读）
----------------------
1. **零成本**。用的是 `store.db.similarity`（二元组 Jaccard），不调模型 ——
   所以"每拍都盯"才做得起（`DIRECTOR_WATCH_EVERY` 只用来降频，不是为了省钱）。
2. **只报事实，不说好坏**。"三个人都说了类似的话"是一个**可验证的事实**；
   "这样写得不好"是判断 —— 判断交给导演（`sim/loop._director_watch`），
   或者更上面的复盘。
3. **宁可漏，不可误报**。阈值低一点点，整个推演就会一直在"回档/重说"里打转，
   那比偶尔漏一次重复更糟。所以默认阈值偏高（0.62），且只在**够多的人**
   各自说过时才报。

"导演心里的大纲"（顶层到细节）
------------------------------
`outline_check()` 回答的是另一件事：**今天该走到哪、现在走到哪了**。
它是 `OUTLINE_DRIFT` 那类判断的依据（节点走完没有、今天的分拍用掉几拍）。
放在同一个模块，是因为"盯戏"和"盯进度"都是导演在**一直看着**的东西。

English:
**Director watches the play** -- checks "several people independently repeating the same
thing/same line".
User 2026-10-07
---------------
"I see a problem where several people consecutively repeat one line, one thing (previously it
was one person alone
  now I have discovered the problem of several people doing one thing separately. Note: upgrade director capability.
  During actor performance, the director must keep watching. If an actor's line or action is wrong, raise it in time.
  The director can request a rollback at any time, i.e. delete the most recently generated segment of the play, then the director can request pausing the performance
  to think about the recent scene and ask the actor to revise. If necessary, may call in the playwright, novel author
  for an ad-hoc meeting, revise the script and novel story, then restart. The director must always keep an outline in mind,
  controlling story progress from top level down to detail)"
Its division of labor with "single-person repetition" (these two things **must be solved at
different layers**)
-------------------------------------------------------
| Problem | Where to solve | Why |
|---|---|---|
| **The same person** says the same line | `SceneBuilder._said` + `sim/loop._review_repeat` | That person's own problem, just ask him |
| **Several people each** say the same line | **this module** | Each one alone looks fine (each person said it only once), **only viewed together is the repetition visible** |
The second category is the entire reason this module exists -- it **cannot be caught by any
single actor's guardrail**,
because for each person that line is "said for the first time".
Three criteria (read before changing)
----------------------
1. **Zero cost**. Uses `store.db.similarity` (bigram Jaccard), no model calls ——
   so "watch every beat" is affordable (`DIRECTOR_WATCH_EVERY` is only used to reduce frequency, not to save money).
2. **Report facts only, not judgments**. "Three people said similar things" is a **verifiable fact**;
   "this is badly written" is a judgment —— leave judgments to the director (`sim/loop._director_watch`),
   or to the higher-level review.
3. **Better to miss than to false-positive**. If the threshold is a little too low, the whole simulation will keep spinning in "rewind/re-say",
   which is worse than occasionally missing a repeat. So the default threshold is on the high side (0.62), and only reports when **enough people**
   have each said it.
"The outline in the director's mind" (top-level to detail)
------------------------------
`outline_check()` answers a different question: **where should we be today, and where are we
now**.
It is the basis for judgments like `OUTLINE_DRIFT` (whether a node is finished, how many beats
of today's beat plan are used up).
It lives in the same module because "watching the drama" and "watching progress" are both things
the director is **constantly looking at**.
"""
from __future__ import annotations

import re

from dataclasses import dataclass, field

#: 判定"两句话是同一件事"的**字面**相似度阈值（二元组 Jaccard）。
# [EN] : Threshold for **literal** similarity (bigram Jaccard) when deciding "two sentences are the
# [EN] same thing".
#:
#: ⚠ 这个数是**量出来的，不是拍的**。2026-10-07 在样例上实测这一组：
# [EN] : ⚠ This number is **measured, not guessed**. On 2026-10-07 this set was measured on samples:
#:
#: | 关系 | 例子 | 相似度 |
# [EN] : | Relation | Example | Similarity |
#: |---|---|---|
#: | 换个人说同一句（只差代词） | 「他低头看了看账本。」/「她低头看了看账本。」 | **0.73~0.75** |
#: | 同一件事换个说法 | 「这账我记着。」/「账我记着，你别管。」 | **0.43~0.50** |
#: | 同一动作换个近义说法 | 「先看水。」/「先看水，再看人。」 | 0.50 |
#: | 毫无关系 | 「这账我记着。」/「水不会说谎。」 | **0.00** |
# [EN] : | Same line spoken by a different person (only the pronoun differs) | "He lowered his head and
# [EN] looked at the ledger." / "She lowered her head and looked at the ledger." | **0.73~0.75** |
# [EN] : | Same thing said a different way | "I'm keeping this account in mind." / "I'm keeping the
# [EN] account in mind, you don't need to worry about it." | **0.43~0.50** |
# [EN] : | Same action said with a near-synonym | "Look at the water first." / "Look at the water
# [EN] first, then look at the person." | 0.50 |
# [EN] : | Completely unrelated | "I'm keeping this account in mind." / "Water doesn't lie." | **0.00**
# [EN] |
#:
#: ★ 实测的**分离度**（这一轮量了两组，才是这个数的依据）：
#:   · 正常对话往来（6 句两两比）：字面 **全是 0.00**，骨架最高 0.50；
#:   · 真·重复（4 句两两比）：字面 0.22~0.80，骨架 0.40~1.00。
#: 两组**分得开**，所以取 0.42 —— 正好落在"换个说法"那一档（0.43）之下一点。
#: ⚠ 单靠字面会漏掉最低那一对（0.22），所以再叠一层 `core_tokens`（实词骨架，
#:   见 `DEFAULT_CORE_SIM`）：两条**任一命中**就算。
# [EN] : ★ The measured **separation** (this round measured two groups, which is the basis for this
# [EN] number):
# [EN] : · Normal dialogue exchange (6 sentences, pairwise): literal is **all 0.00**, skeleton max
# [EN] 0.50;
# [EN] :   · True repetition (4 sentences, pairwise): literal 0.22~0.80, skeleton 0.40~1.00.
# [EN] : The two groups **separate cleanly**, so 0.42 is chosen -- just a bit below the "said
# [EN] differently" band (0.43).
# [EN] : ⚠ Literal alone would miss the lowest pair (0.22), so layer on `core_tokens` (content-word
# [EN] skeleton,
# [EN] :   see `DEFAULT_CORE_SIM`): **either** of the two hitting counts.
DEFAULT_SIM = 0.42

#: **实词骨架** 相似度阈值。把虚词/代词/标点去掉之后，剩下字的集合。
# [EN] : **Content-word skeleton** similarity threshold. After removing function
# [EN] words/pronouns/punctuation, the set of remaining characters.
#:
#: 为什么需要它：二元组对**短句**很不稳 ——
#: 「看了看井口。」/「看了看那口井。」字面只有 **0.29**（"井口"与"那口井"
#: 切出来的二元组完全不同），但它俩显然是同一件事。
#: 去掉虚词之后 `{看,井,口}` / `{看,井,口}` = 1.0，一眼就对上了。
# [EN] : Why it is needed: bigrams are very unstable for **short sentences** --
# [EN] : produce completely different bigrams), yet they are obviously the same thing.
#:
#: 0.60 来自上面那张分离度表（正常最高 0.50 / 真重复 0.67 起）。
#: "至少 2 个实词"那道是为了挡住两三个字的短句
#: （「他走了」/「她走了」只有 `{走}`，不算数）。
# [EN] : 0.60 comes from the separation table above (normal max 0.50 / true repetition starts at 0.67).
# [EN] : The "at least 2 content words" rule exists to block short 2-3 character sentences
DEFAULT_CORE_SIM = 0.60

#: 短于这个长度的句子**不参与**多人重复比对。
#: 越短越容易撞（两三个字的一句话可能一半都是共用字），而"三个人都说了
#: 四个字"这种事本来也算不上重复。
# [EN] : Sentences shorter than this length **do not participate** in multi-person repetition
# [EN] comparison.
# [EN] : The shorter it is, the easier it collides (a 2-3 character sentence may be half shared
# [EN] characters), and "three people all said
# [EN] : four characters" does not really count as repetition anyway.
MIN_LINE_CHARS = 5

#: 中文虚词/代词 —— 比对**骨架**时先剔掉。
#: ⚠ 别往里加实词（"看""说"这类是骨架的一部分）；也别指望它齐全，
#:   它只是"比对前先归一"的第一步，不是分词。
# [EN] : Chinese function words/pronouns -- strip them before comparing the **skeleton**.
# [EN] : ⚠ Do not add content words to it (words like "看" "说" are part of the skeleton); and do not
# [EN] expect it to be complete,
# [EN] :   it is only the first step of "normalize before comparing", not tokenization.
_STOP = set('的了着过地得是和与在把被给对向从到就都也还很太不没'
            '他她它他们我们你们这个那个哪些什么么呢吧啊呀哦嘛'
            '一又再还只才更最然后而并且但如果因为所以')
_PUNCT = set('，。！？；：、「」『』（）《》…—-　 ·,.!?;:"\'()[]')

#: 至少**几个不同的人**说过类似的话才算"多人各自独立重复"。
#: 2 个人其实已经能看出来了（"两个人轮流说同一句"读起来最怪），
#: 但两个人在对话里接同一句话也可能是正常的（附和、复述确认）——
#: 所以默认 3，要更敏感就调 `DIRECTOR_WATCH_MIN_PEOPLE`（配置或参数）。
# [EN] : At least **how many different people** must have said something similar for it to count as
# [EN] "multiple people independently repeating".
# [EN] : 2 people is actually already detectable ("two people taking turns saying the same line" reads
# [EN] the weirdest),
# [EN] : but two people picking up the same line in dialogue can also be normal (agreeing, repeating to
# [EN] confirm) --
# [EN] : so the default is 3; to be more sensitive, adjust `DIRECTOR_WATCH_MIN_PEOPLE` (config or
# [EN] parameter).
DEFAULT_MIN_PEOPLE = 3


@dataclass
class Issue:
    """盯戏查出来的一个问题。`kind` 定了它该怎么处理。
        English:
    A problem found by watching the drama. `kind` determines how it should be handled.
    """

    kind: str                  # multi_repeat / single_repeat / idle
    who: list[str] = field(default_factory=list)
    sample: str = ''           # 有代表性的那句原文（截断）
    detail: str = ''           # 一句人话（进日志与提示词）
    severity: int = 1          # 1=提醒 2=该回档
    # [EN] A representative original line (truncated)
    # [EN] A plain-language sentence (goes into logs and prompts)
    # [EN] 1=remind 2=should roll back

    def line(self) -> str:
        names = '、'.join(self.who[:4]) or '（多人）'
        return f'{self.detail}｜{names}：{self.sample}'


def core_tokens(text: str) -> set[str]:
    """**实词骨架**：去掉虚词/代词/标点之后剩下的字（集合）。

    只用于本模块的比对，**不做分词、不建索引** —— 它的目的很窄：
    让「看了看井口」和「看了看那口井」能对上。
    
        English:
    **Content-word skeleton**: the characters left after removing function
    words/pronouns/punctuation (a set).
        Only used for comparison within this module, **no tokenization, no index building** —— its purpose is very narrow:
    """
    return {ch for ch in str(text or '') if ch not in _STOP and ch not in _PUNCT
            and not ch.isspace()}


def _same_thing(a: str, b: str, *, sim: float, core_sim: float) -> bool:
    """这两句算不算"同一件事"（两层任一命中）。见 `DEFAULT_SIM` 那张表。
        English:
    Whether these two sentences count as "the same thing" (either of the two layers hits). See the
    `DEFAULT_SIM` table.
    """
    from store.db import similarity
    if similarity(a, b) >= sim:
        return True
    ca, cb = core_tokens(a), core_tokens(b)
    if len(ca) < 2 or len(cb) < 2:
        return False                    # 太短的不比骨架（「他走了」/「她走了」）
        # [EN] Too short ones don't get compared against the skeleton ("He left" / "She left")
    inter = len(ca & cb)
    return inter / max(1, len(ca | cb)) >= core_sim


def _rows_from(lines, people: list[str]) -> list[tuple[str, str]]:
    """把"叙事行"整理成 `[(谁, 文本)]`。

    认的是**剧本体**与**小说体**两种——
    `主角：台词` / `主角 →柳娘：（动作）台词` / `（主角转向后院。）`。
    认不出来的一律**丢掉**（宁少不多：把旁白当成"某人说的话"会直接导致误报）。
    
        English:
    Organize "narrative lines" into `[(who, text)]`.
        Recognizes two forms —— **script style** and **novel style** ——
        Anything unrecognized is **discarded** (better fewer than too many: treating narration as "something someone said" will directly cause false positives).
    """
    import re
    out: list[tuple[str, str]] = []
    known = {str(x).strip() for x in (people or []) if str(x).strip()}
    for ln in (lines or []):
        s = ' '.join(str(ln or '').split())
        if not s or len(s) < 4:
            continue
        # 台词行：`名字：…` 或 `名字 →别人：（动作）…`
        # [EN] Dialogue line: `Name: ...` or `Name →Other: (action)...`
        m = re.match(r'^([^\s：:]{1,12})\s*(?:→\s*[^\s：:]{1,12}\s*)?[：:](.*)$', s)
        if m:
            who, what = m.group(1).strip(), m.group(2).strip()
            if known and who not in known:
                continue
            what = re.sub(r'^（[^）]*）', '', what).strip()
            if len(what) >= MIN_LINE_CHARS:
                out.append((who, what))
            continue
        # 动作行：`（主角转向后院。）` —— 也算"他做了一件事"
        # [EN] Action line: `(Shen Yan turns toward the back courtyard.)` —— also counts as "he did something"
        m2 = re.match(r'^（([^\s，。]{2,12})(.{2,40})）$', s)
        if m2:
            who, what = m2.group(1).strip(), m2.group(2).strip()
            if known and who not in known:
                continue
            if len(what) >= MIN_LINE_CHARS - 2:
                out.append((who, what))
    return out


def scan_repetition(lines, *, people: list[str] | None = None,
                    sim: float = DEFAULT_SIM,
                    core_sim: float = DEFAULT_CORE_SIM,
                    min_people: int = DEFAULT_MIN_PEOPLE,
                    window: int = 14) -> list[Issue]:
    """查"多人各自独立重复"与"单人连着重复"。

    `lines` 是**最近的叙事行**（顺序 = 时间顺序，最后一条最新）。
    `window` = 只看最近这么多条（看太远会把"前面早就说过、现在已经翻篇"的
    也算进来 —— 那是正常的呼应，不是重复）。
    
        English:
    Check "multiple people each independently repeating" and "a single person repeating
    consecutively".
        `lines` are the **most recent narrative lines** (order = chronological order, last one is newest).
        `window` = only look at the most recent this many lines (looking too far back will also count "said long ago, already moved on"
        —— that is a normal callback, not a repeat).
    """
    rows = _rows_from(lines[-window:] if window > 0 else lines, list(people or []))
    issues: list[Issue] = []
    if len(rows) < 2:
        return issues

    # ── ① 多人各自独立说了类似的话 ──
    #   做法：两两比。按"说话人"聚成组，一组里有 ≥min_people 个**不同的人**才算。
    #   不用"先聚类再统计"：那些都是启发式的，而这个规模（十几条）两两比够快，
    #   而且**行为可预测**（判据好写、反例法好打）。
    # [EN] -- ① Multiple people independently said something similar --
    # [EN] Approach: pairwise comparison. Group by "speaker"; only a group with >=min_people **different
    # [EN] people** counts.
    # [EN] Not "cluster first, then count": those are all heuristic, and at this scale (a dozen or so
    # [EN] lines) pairwise is fast enough,
    # [EN] and **behavior is predictable** (criteria are easy to write, counterexamples are easy to
    # [EN] attack).
    groups: list[dict] = []
    for i, (who, what) in enumerate(rows):
        placed = False
        for g in groups:
            if _same_thing(what, g['sample'], sim=sim, core_sim=core_sim):
                if who not in g['who']:
                    g['who'].append(who)
                g['n'] += 1
                g['idx'].append(i)
                # 样本取**较长的那条**（信息多、给人看更清楚）
                # [EN] The sample takes the **longer one** (more information, clearer for a human to read)
                if len(what) > len(g['sample']):
                    g['sample'] = what
                placed = True
                break
        if not placed:
            groups.append({'who': [who], 'sample': what, 'n': 1, 'idx': [i]})
    for g in groups:
        if len(g['who']) >= max(2, int(min_people)):
            issues.append(Issue(
                kind='multi_repeat', who=list(g['who']), sample=g['sample'][:40],
                detail=f'{len(g["who"])} 个人各自独立说了同一件事'
                       + f'（共 {g["n"]} 次）',
                severity=2))

    # ── ② 同一个人**连着**说差不多的话 ──
    #   `_said` 那层管"一字不差"；这里管"换个说法又说一遍"（它抓不到的那种）。
    # [EN] -- ② The same person saying similar things **consecutively** --
    # [EN] The `_said` layer handles "word-for-word"; this one handles "said it again in other words" (the
    # [EN] kind it cannot catch).
    for i in range(1, len(rows)):
        who, what = rows[i]
        pw, pwhat = rows[i - 1]
        if who == pw and _same_thing(what, pwhat, sim=sim, core_sim=core_sim):
            issues.append(Issue(
                kind='single_repeat', who=[who], sample=what[:40],
                detail=f'{who} 连着两条把同一件事说了两遍（换了说法）',
                severity=1))
    return issues


def idle_issue(lines, *, window: int = 6, min_chars: int = 0) -> Issue | None:
    """最近这一小段里**一件事都没发生**吗（全是"看/等/沉默"）？

    用户说的"好几个人一起单独做一件事"里，有一半其实是**谁都没做事**：
    一整拍下来只有"他看了看""她没说话"。这类"空转"比重复更伤 ——
    读起来是三个人在同一个屋里各自发呆。

    ⚠ 判据要窄：只在**连续 window 条**全是短句、且全落在
      "看/望/听/等/沉默"这一小撮动词上时才报。写宽了每拍都会报。
    
        English:
    In this most recent small stretch, did **not a single thing happen** (all "look/wait/silence")?
        Of what the user calls "several people each doing one thing separately", half is actually **nobody doing anything**:
        a whole beat with only "he looked" "she didn't speak". This kind of "idling" hurts more than repetition ——
        it reads as three people each spacing out in the same room.
        ⚠ The criterion must be narrow: only report when **consecutive window lines** are all short sentences, and all fall on
          this small handful of verbs "look/gaze/listen/wait/silence". If written too broadly, it will report every beat.
    """
    # ⚠ 「站着」这一类**必须也在表里**：`verify_studio_v2` 的 D4 用
    #   「柳娘站着。」当反例时才发现原来漏了它 —— 漏一个词就是漏一整个
    #   常见动作（"站着/坐着/靠着"是空转戏里最常见的三个姿势）。
    # [EN] ⚠ Things like "站着" **must also be in the table**: `verify_studio_v2`'s D4 used
    # [EN] "柳娘站着。" as a counterexample and only then was it discovered missing -- missing one word means
    # [EN] missing an entire
    idle_words = ('看', '望', '瞧', '听', '等', '沉默', '不语', '没说话',
                  '没出声', '站在', '站着', '坐着', '靠着', '低头', '抬头',
                  '转身', '不动', '没动')
    tail = [' '.join(str(x or '').split()) for x in (lines or [])[-window:]]
    tail = [t for t in tail if t]
    if len(tail) < window:
        return None
    for t in tail:
        if min_chars and len(t) > min_chars:
            return None
        if not any(w in t for w in idle_words):
            return None
    return Issue(kind='idle', who=[], sample=tail[-1][:40],
                 detail=f'连着 {len(tail)} 条都在原地打转（看/等/沉默）',
                 severity=2)


# ══════════════════════════════════════════════════════════════════
#  ★★★ 对话是不是各说各话（2026-10-18）
# [EN] ★★★ Is the dialogue everyone-talking-to-themselves (2026-10-18)
# ══════════════════════════════════════════════════════════════════
#  用户 2026-10-18
#  -------------
#  「好几次人物说的话互相不对应 就是一个人说的话 另外一个人不去接
#    两个人各说各话的现象到处存在…在很短的一段时间内 出场人物应该是按照
#    一个主题展开对话的 而不是每个人自己一个主题 中间应该有协调者
#    特别是导演 应该消除这种自说自话的问题」
#
#  实测形状（`developers/probe_dialogue_cohesion.py` 量出来的）：
#    · 雪国 18 拍：**接话率 0.27**（4 句里只有 1 句接上一句）、**最长 4 句无人接**；
#    · 同一段里三个话题并行：驹子质问、叶子招呼、岛村回避，
#      而每一个人单独看都"说得对"。
#
#  为什么它和"重复"必须分开（两件事在不同层解决）：
#    | 毛病 | 在哪解决 |
#    |---|---|
#    | 好几个人说同一句话 | `scan_repetition`（上面） |
#    | **好几个人各说各的** | **本段** |
#    第一类是"内容撞车"，第二类是"内容不撞、但互不承接" —— 只看任意一句都正常。
#
#  三条口径
#  --------
#  1. **零成本**：只解析已经渲染好的一行行文本（`one_line` 的格式），不调模型。
#     所以"每拍都查"做得起。
#  2. **算出来的"话题锚"，不是生成的**：不写"这一段在讨论 X"这种概括，
#     而是把**最近一组真正的问答**里"答"的那一句**原样**当锚递回去。
#     概括要靠模型（贵且会歪）；引文是事实（免费且准确）。
#  3. **只报事实**："连续 4 句没人接"是可数的；"这样写得不好"是判断。

#: `one_line()` 渲染出来的台词行：`驹子（声音轻）对岛村：……`
#: ⚠ 括号（语气）是可选的，`对XX` 也是可选的 —— 两种都要认。
# [EN] A dialogue line rendered by `one_line()`: `A (tone) to B: ...`
# [EN] ⚠ The parenthesized tone is optional and `to B` is optional; both shapes must match.
#: 台词头里的"对谁"两种写法都要认：
#:   ① `one_line()` 产出：`驹子（声音轻）对岛村：……`
#:   ② 逐条实录（transcript）里：`驹子：（向岛村）（声音轻）……`
#: ⚠ 第一版只认 ①，于是拿真产物（②格式）当夹具时**整行解析失败**，
#:   `talk_audit` 返回"没有台词" ⇒ 判据 A1/A2 当场红，而产品看起来完全正常
#:   （那正是"两种格式各写一套"最典型的坑）。
# [EN] Two spellings of "addressed to" in a dialogue header must both be recognised:
# [EN] ① what `one_line()` emits: `A (tone) to B: ...`
# [EN] ② what the transcript record keeps: `A: (to B) (tone) ...`
# [EN] ⚠ The first version only knew ①, so using a real transcript as the fixture made **the whole
# [EN] line fail to parse** and `talk_audit` reported "no dialogue" => A1/A2 went red while the
# [EN] product looked perfectly normal (the classic "two formats, two implementations" trap).
_HEAD_TO_RE = re.compile(r'^([^（(对]{1,12})(?:[（(]\s*(?:向|对)?\s*([^）)]{1,12})[）)])?$')


def _spoken(lines) -> list[tuple[str, str, str]]:
    """从渲染好的行里取出台词：`[(谁, 对谁, 正文)]`（非台词行跳过）。

    做法（与排版格式**无关**，三种写法都吃得下）：
      1. **"对谁"**：整行里搜第一个 `（向X）` / `（对X）` / `对X：` —— 这是唯一的信息源；
      2. **"谁"**：冒号左边那一段，切掉所有括号；
      3. **正文**：冒号右边，去掉开头的括号（那是"向X"或语气）。

    ⚠ 第一版要求"头部形如 `A（语气）对B`"或"`A：（向B）`"，**只认后者的冒号位置**，
      于是夹具里 `A（向B）（语气）：…`（括号在冒号前）整行解不出"对谁"
      ⇒ A1/A2 当场红，而产物里的真实行恰好是这种混排。
      教训：**别按"我以为的格式"写解析**，按"最稳的信息源"写。
    [EN] Format-agnostic: ① "to whom" = the first `(to X)` / `(at X)` / `to X:` anywhere in the
    [EN] line (the only information source); ② "who" = the segment left of the colon with all
    [EN] brackets cut; ③ body = right of the colon with leading brackets removed.
    [EN] ⚠ The first version required a specific layout and failed on `A (to B) (tone): ...`
    [EN] (brackets before the colon), so A1/A2 went red on real mixed lines.
    [EN] Lesson: **do not parse "the format I assumed"** -- parse the most reliable source.
    """
    out: list[tuple[str, str, str]] = []
    for ln in (lines or []):
        t = ' '.join(str(ln or '').split())
        if not t or t.startswith(('〔', '※', '▷', '▪', '·', '>')):
            continue
        cut = max(t.rfind('：'), t.rfind(':'))
        if cut <= 0:
            continue
        left, right = t[:cut], t[cut + 1:].strip()

        # ① 对谁：整行里第一个 `（向X）` / `（对X）` / `(to X)`
        to = ''
        # ⚠ `（对着纸门的方向，轻声）` 里的"对着"**不是**"对某人"：`对` 后面跟 `着`
        #   就必须排除，否则"对象"会解成 `着纸门的方向，轻声`（实测 A2 报成这样）。
        #   对象也不该带标点 —— 人名里没有逗号顿号。
        # [EN] "facing the paper door" is **not** "addressing someone": exclude 对 followed by
        # [EN] 着, otherwise the target parses as `ing at the paper door, softly` (measured).
        # [EN] A target also carries no punctuation -- names have no commas.
        m = re.search(r'[（(]\s*(?:向|对)(?!着)\s*([^）)，。、；：]{1,12})[）)]', t)
        if m:
            to = m.group(1).strip()
        else:
            # ⚠ 不能用 `\s对` —— `one_line` 产出的是 `驹子（声音轻）对岛村`，
            #   `对` 前面是 `）`，不是空白（第一版就这么漏了）。
            #   取**最后一个** `对`，且它右边不含括号 ⇒ 那就是对象。
            # [EN] ⚠ Do not require whitespace before 对: `one_line` emits
            # [EN] `A (softly) to B`, where 对 follows `)`. Take the **last** 对 whose right
            # [EN] side has no bracket -- that is the target.
            a, sep, c = left.rpartition('对')
            if sep and c and '（' not in c and '(' not in c and len(c) <= 12:
                to = c.strip()

        # ② 谁：冒号左边第一段，括号与"对X"都切掉
        who = re.split(r'[（(]', left, 1)[0]
        who = who.split('对')[0].strip()

        # ③ 正文：去掉开头所有括号
        body = right
        while body.startswith(('（', '(')):
            close = body.find('）') if body.startswith('（') else body.find(')')
            if close < 0:
                break
            body = body[close + 1:].strip()

        if who and body:
            out.append((who, to, body))
    return out


def _links(a: tuple[str, str, str], b: tuple[str, str, str],
           *, share: float = 0.40) -> bool:
    """b 是不是在接 a。**保守判**（宁可漏，不可误报）。

    ⚠⚠⚠ 量出来的事实（2026-10-18）：**字面相似度判不出"接没接"**。
      正常的一问一答 `更鼓是几时敲的。` / `三更刚过，博士。` 相似度 **0.00**；
      而"各说各话"的 `岛村先生，您倒是说句话呀。` / `先生，驹子姐她……` 是 **0.08**。
      两组**分不开** —— 所以字面重合只能当"明显同一件事"的辅助（阈值抬到 0.40）。

    ⇒ **唯一可靠的信号是"谁对谁说"**（`对` 字段）：
      ① a 冲着 b 说 ⇒ b 该答；
      ② b 冲着 a 说 ⇒ b 在答 a；
      ③ 两句字面高度重合（≥0.40，只在"同一件东西"时发生）。
    ⚠ 没有 `对` 字段的两句 ⇒ 一律算"没接"。这是**有意保守**：
      漏判的代价是"少数一次没提醒"，误判的代价是"每拍都在回档重排"。
    [EN] ⚠⚠⚠ Measured fact (2026-10-18): **wording similarity cannot tell "answered" from
    [EN] "ignored"**. A normal exchange scores **0.00**, while two lines of the talk-past-each-other
    [EN] kind score **0.08** -- the two groups do not separate. So wording overlap can only be an
    [EN] auxiliary signal for "clearly the same thing" (threshold raised to 0.40).
    [EN] => **The only reliable signal is who-addressed-whom** (the `to` field): ① a addressed b;
    [EN] ② b addressed a; ③ the two lines overlap heavily (>= 0.40, only for the same object).
    [EN] ⚠ Two lines with no `to` count as "not answered" -- deliberately conservative: a miss
    [EN] costs one unreminded beat, a false positive means rolling back every beat.
    """
    # ① **a 点名 b、b 开口** —— 这才是"回答"的定义。
    # ⚠ 不能放宽成"b 冲着 a 说也算"：雪国那段里驹子、叶子**都在对岛村说话**，
    #   彼此并不接（"先生，热水备好了" / "你这个人哪"），放宽了会把
    #   "两个人都跟第三个人说"当成"在对话"——那恰好是用户说的各说各话。
    # [EN] ① **a addressed b and b speaks** -- that is what "answering" means.
    # [EN] ⚠ Do not relax it to "b speaks at a": in the Snow Country stretch both women address
    # [EN] Shimamura and do not answer each other. Relaxing turns "two people each talking to a
    # [EN] third" into "a conversation" -- which is exactly the talk-past-each-other.
    if a[1] and b[0] and a[1] == b[0]:
        return True
    # ② 字面高度重合（"同一件东西"）—— 只在明显同题时命中
    # [EN] ② Heavy wording overlap ("the same object") -- only when clearly on-topic.
    from store.db import similarity
    return similarity(a[2], b[2]) >= share


#: 看多少句台词。★ 12 句 ≈ 6–10 拍，正是用户说的"很短的一段时间"。
#: ⚠ 第一版用 8，而雪国那段最长的一串"没人接"有 12 句、恰好被切在窗口外
#:   ⇒ 判据只量到 2，险些把"没毛病"写进报告。
# [EN] How many dialogue lines to look at. ★ 12 lines is roughly 6-10 beats, exactly the
# [EN] "very short stretch" the user means. ⚠ The first version used 8, while the longest
# [EN] unanswered run in the Snow Country stretch was 12 and got cut off by the window.
def talk_audit(lines, *, window: int = 12, min_run: int = 3) -> tuple[Issue | None, dict]:
    """最近这一小段对话，**有没有人在各说各话**。

    返回 `(问题, 账)`；账里三样都是给**下一拍的演员**看的：
      · `topic`     —— 这一段在谈什么（最近一组真问答里"答"的那句，**原样**）；
      · `open_with` —— 谁被点名、还欠一句（下一拍**必须**让他先开口）；
      · `run`       —— 连续几句没人接（≥ `min_run` 就报 `Issue`）。

    ⚠ `min_run` 默认 3：真人对话里"两句不接"很常见（听岔、各想各的），
      连到 3 句才是用户说的那种"各说各话"。
    [EN] Returns `(issue, ledger)`. The ledger is what the **next beat's actors** need:
    [EN] `topic` (what this stretch is about, the **verbatim** reply line of the most recent
    [EN] real exchange), `open_with` (who was addressed and still owes an answer -- he **must**
    [EN] speak first next beat), `run` (how many consecutive lines nobody picked up).
    [EN] ⚠ `min_run` defaults to 3: two unlinked lines happen in real talk; three in a row is the
    [EN] "everyone talking to themselves" the user means.
    """
    spoken = _spoken(lines)
    ledger: dict = {'topic': '', 'open_with': '', 'run': 0, 'speakers': []}
    if len(spoken) < 2:
        return None, ledger
    tail = spoken[-window:]
    ledger['speakers'] = sorted({w for w, _t, _b in tail})

    # ① **整段里最长的一串"没人接"**（不是"末尾连续几句"）。
    #   ★ 第一版从最新往回数、遇到一次"接上"就停 —— 实测雪国那段返回 2，
    #     而同一段里真正连着不接的是 **12 句**（只因为最新处恰好有一句
    #     "叶子问、岛村答"）。"这一段是不是各说各话"看的是**整体**，不是结尾。
    # [EN] ① The **longest run of unanswered lines in the whole window** (not "how many at the
    # [EN] end"). ★ The first version counted backwards from the newest and stopped at the first
    # [EN] answered pair -- measured 2 on the Snow Country stretch, while the real long run inside
    # [EN] it was **12**. "Is this stretch talk-past-each-other" is a property of the **whole**.
    run = 0
    cur = 0
    for a, b in zip(tail, tail[1:]):
        if b[0] == a[0]:
            continue          # 同一人连说：不算"接"，但也不清零（那不是别人插话）
        if _links(a, b):
            cur = 0
        else:
            cur += 1
            run = max(run, cur)
    ledger['run'] = run

    # ② 话题锚：最近一组**真问答**里"答"的那一句（原样）
    # [EN] ② Topic anchor: the **verbatim** reply line of the most recent real exchange.
    for a, b in reversed(list(zip(tail, tail[1:]))):
        if a[0] != b[0] and _links(a, b):
            ledger['topic'] = b[2][:60]
            break
    if not ledger['topic']:
        ledger['topic'] = tail[-1][2][:60]

    # ③ 谁欠一句：**被点名最多次、回答最少**的那个人。
    #   ★ 第一版找"最后一条冲着谁、那人之后没开口" —— 实测返回空：
    #     最后几条常常是谁都没对着说的自言自语。而真正的问题是**累计**的：
    #     雪国那段岛村被点名 10 次、只答了 3 次。
    #   ⚠ 差值 ≥2 才报（一次没答可能只是没听见，那是正常的）。
    # [EN] ③ Who owes an answer: the person **addressed most often and answering least**.
    # [EN] ★ The first version looked at "the last line's target, if he never spoke after" --
    # [EN] measured empty, because the last few lines are often nobody-directed asides. The real
    # [EN] problem is **cumulative**: Shimamura was addressed 10 times and answered 3.
    # [EN] ⚠ Report only when the gap is >= 2 (missing one is normal).
    asked: dict[str, int] = {}
    answered: dict[str, int] = {}
    for i2, (who, to, _b) in enumerate(tail):
        if to and to != who and to in {w for w, _t, _b2 in tail}:
            asked[to] = asked.get(to, 0) + 1
            # ★ 只有**紧接着的下一条**是他，才算"接上了"。
            #   ⚠ 放宽成"之后某个地方开过口"会漏掉真问题：雪国那段岛村确实开过口
            #     （"外面的雪，应该还在下吧"），但那是在 5 句之后、且完全回避 ——
            #     按旧口径岛村"每次都答了"，差值为 0。
            # [EN] ★ Only if the **very next line** is his does it count as answered.
            # [EN] ⚠ Relaxing to "he spoke somewhere later" hides the real problem: Shimamura did
            # [EN] speak ("the snow outside is probably still falling") but five lines later and as
            # [EN] a total dodge -- under the old rule he "answered every time", gap 0.
            nxt = tail[i2 + 1] if i2 + 1 < len(tail) else None
            if nxt is not None and nxt[0] == to:
                answered[to] = answered.get(to, 0) + 1
    if asked:
        worst = max(asked, key=lambda k: (asked[k] - answered.get(k, 0), asked[k]))
        if asked[worst] - answered.get(worst, 0) >= 2:
            ledger['open_with'] = worst

    issue = None
    if run >= max(1, int(min_run)):
        issue = Issue(kind='talk_drift', who=list(ledger['speakers']),
                      sample=tail[-1][2][:40],
                      detail=f'连着 {run} 句没人接上一句（各说各话）',
                      severity=1)
    return issue, ledger


def outline_check(world, *, today_beats: int = 0) -> str:
    """**导演心里那个大纲**：现在该走到哪、今天走到哪了。

    返回一句人话（进日志与决策提示词的 `[导演提示]`）；没问题就返回空串。
    ⚠ 它**只报状态**，不决定动不动 —— 动谁的判断在 `sim/loop._director_watch`。
    
        English:
    **The outline in the director's mind**: where we should be now, and where we are today.
        Returns one plain sentence (goes into the log and the decision prompt's `[导演提示]`); returns an empty string if there's no problem.
        ⚠ It **only reports status**, does not decide whether to act —— the judgment of who to move is in `sim/loop._director_watch`.
    """
    bits: list[str] = []
    nodes = list(getattr(world, 'progress_nodes', None) or [])
    cur = str(getattr(world, 'current_node', '') or '')
    done = [n for n in nodes if isinstance(n, dict) and n.get('状态') == '已完成']
    if nodes:
        bits.append(f'进度 {len(done)}/{len(nodes)}')
        here = next((n for n in nodes
                     if isinstance(n, dict) and str(n.get('id') or '') == cur), None)
        if here is not None:
            nm = str(here.get('名称') or cur)
            bits.append(f'当前站在「{nm}」')
    if today_beats:
        bits.append(f'今天的戏排了 {today_beats} 拍')
    return '；'.join(bits)

# ══════════════════════════════════════════════════════════════════
#  ★★★ 这一拍的**时机**与**品级**（2026-10-18）
# [EN] ★★★ This beat's **moment** and **grade** (2026-10-18)
# ══════════════════════════════════════════════════════════════════
#  用户：「很多Agent的提示词请动态拼接 而不是固定的 根据需要由特定Agent负责品级」。
#
#  为什么"品级"归导演判（而不是各职位自己判、也不是写死在配置里）：
#   · 它是**唯一在看整场戏**的职位 —— 它知道这一段是不是各说各话、
#     今天排了几拍、张力到哪儿了；演员只看得到自己那一句。
#   · 品级不是"质量等级"，是**这一拍该给多少约束**：
#     日常拍塞十条规矩，文本会变匠气（2026-10-18 实测：句长掉到 5–6 字、
#     零动作）；开场/转折/收束才该读满。
#   ⇒ 判据（`verify_craft_dispatch`）守三件事：
#     ① 纯函数、零成本（不调模型，每拍都跑得起）；
#     ② 三个品级都真的会出现（否则等于只有一档）；
#     ③ 品级真的改变条数（`craft/dispatch.pick` 读它）。
#
#  ⚠ 这两个值**只影响"给多少手艺"**，不影响剧情、不影响分拍、不改提示词里
#    任何一句已经写好的话 —— 所以判错了也只是"这一拍少读两条/多读两条"，
#    不会把戏带歪。这是它敢每拍都算的前提。
#  [EN] User: "many Agents' prompts should be assembled dynamically rather than fixed; a specific
#  [EN] Agent should own the grade". Why the **director** owns it: it is the only position watching
#  [EN] the whole scene (talk-drift, beats scheduled today, tension); an actor sees only his own line.
#  [EN] Grade is not "quality", it is **how much constraint this beat gets** -- piling ten rules onto
#  [EN] a daily beat makes the prose mannered (measured 2026-10-18: sentence length fell to 5-6 chars,
#  [EN] zero actions). Criteria guard three things: pure function / all three grades occur / the grade
#  [EN] really changes the count.
#  [EN] ⚠ These two values **only affect "how much craft is fed"**, never the plot, the beat split,
#  [EN] or any existing sentence of the prompt -- so a misjudgement costs at most "two entries more or
#  [EN] less this beat". That is the precondition for computing it every beat.

#: 张力到这个数就算"这一拍在打"（该读满）。
# [EN] Tension at or above this means "this beat is a fight" (read it all).
_GRADE_TENSION = 0.55
#: 各说各话到这个数就算"僵住了"（该读满 —— 需要结构手艺来打破）。
# [EN] Talk-drift at or above this means "stuck" (read it all -- needs structural craft to break).
_GRADE_RUN = 3


def beat_moment(world, *, is_new_scene: bool = False, beats_left_today=None,
                reviewing: bool = False, finishing: bool = False) -> str:
    """这一拍处在故事的哪个位置：`开场 / 冲突 / 转折 / 收束 / 查稿 / 成稿 / 日常`。

    顺序就是**优先级**（先命中先算）：
      1. `finishing`（正在收工/落盘）→ `成稿`
      2. `reviewing`（这一拍要跑剧本审读）→ `查稿`
      3. 本场第一拍 / 今天第一拍 → `开场`
      4. `beats_left_today <= 2` → `收束`
      5. 各说各话 ≥ 3 句 或 张力 ≥ 0.55 → `冲突`
      6. 上一场刚留下"没完的事"（`aftermath` 有待决定的一条）→ `转折`
      7. 其余 → `日常`

    ⚠ 为什么"场末"排在"冲突"前面：一场最后两拍如果还在打，读者没有落地的地方 ——
      `收束` 要的是"把这一场收住"的手艺，不是"再拱一把火"。
    [EN] Which position this beat sits at; the order below **is** the priority:
    [EN] finishing -> 成稿; reviewing -> 查稿; first beat of scene/day -> 开场;
    [EN] <=2 beats left today -> 收束; talk-drift>=3 or tension>=0.55 -> 冲突;
    [EN] last scene left an undecided matter -> 转折; otherwise 日常.
    [EN] ⚠ Why "end of scene" outranks "conflict": if the last two beats are still fighting, the
    [EN] reader has nowhere to land -- 收束 needs "close this scene" craft, not "stoke it again".
    """
    w = world
    if finishing:
        return '成稿'
    if reviewing:
        return '查稿'
    if is_new_scene:
        return '开场'
    if beats_left_today is not None:
        try:
            if int(beats_left_today) <= 2:
                return '收束'
        except (TypeError, ValueError):
            pass
    run = int(getattr(w, 'topic_run', 0) or 0)
    tens = float(getattr(w, 'tension', 0.0) or 0.0)
    if run >= _GRADE_RUN or tens >= _GRADE_TENSION:
        return '冲突'
    aft = getattr(w, 'aftermath', None)
    if isinstance(aft, dict) and str(aft.get('决定') or '').strip():
        # 上一场留下了一个"他决定了什么" —— 这一拍是从那个决定长出来的
        # [EN] The last scene left a "he decided X" -- this beat grows out of that decision.
        return '转折'
    return '日常'


def grade_beat(world, *, is_new_scene: bool = False, beats_left_today=None,
               reviewing: bool = False, finishing: bool = False) -> tuple[str, str]:
    """**导演给这一拍定品级**：返回 `(时机, 品级)`。

    品级三档（决定这一拍读几条手艺，见 `craft/dispatch.pick`）：

    | 品级 | 什么时候 | 读几条 |
    |---|---|---|
    | `重` | 开场 / 转折 / 收束 / 冲突 / 查稿 / 成稿 | 读满 |
    | `中` | 其余，且有事正在发生 | 读满 |
    | `轻` | **日常**且张力低且没人欠话 | 只读一半 |

    ⚠ `轻` **不是**"这一拍不重要"，是"这一拍不需要那么多规矩"——
      日常戏写得匠气，比写得随意更伤（实测：句长掉到 5–6 字、动作归零）。
    [EN] The director grades this beat: returns `(moment, grade)`. Heavy for
    [EN] opening/turn/closing/conflict/review/finishing; light only for a daily beat with low tension
    [EN] and nobody owing an answer (reads half). ⚠ Light is not "unimportant", it is "needs fewer
    [EN] rules" -- mannered daily prose hurts more than casual daily prose.
    """
    mom = beat_moment(world, is_new_scene=is_new_scene,
                      beats_left_today=beats_left_today,
                      reviewing=reviewing, finishing=finishing)
    if mom in ('开场', '转折', '收束', '冲突', '查稿', '成稿'):
        return mom, '重'
    tens = float(getattr(world, 'tension', 0.0) or 0.0)
    owe = str(getattr(world, 'topic_open_with', '') or '').strip()
    # ⚠ 用 `<=`：`WorldState()` 的默认张力就是 0.30，那正是"开场铺完、没什么事"
    #   的常态 —— 写 `< 0.30` 会让**默认状态永远落到 `中`**，`轻` 只在
    #   张力被人为调低时才出现，等于这一档形同虚设（判据"三档都要出现"会红）。
    # [EN] ⚠ Use `<=`: the default tension of `WorldState()` is 0.30, exactly the "setup done,
    # [EN] nothing happening" normal state. Writing `< 0.30` makes the **default always fall to
    # [EN] medium**, so `light` appears only when tension is artificially lowered -- a dead grade.
    if tens <= 0.30 and not owe:
        return mom, '轻'
    return mom, '中'



#: 心理距离三档（专业论述 #10，Cohn《透明的心灵》）—— 与 `agent/core._DISTANCE_RULES` 的键一致。
# [EN] The three psychological-distance grades (#10, Cohn) -- keys match `agent/core._DISTANCE_RULES`.
DISTANCES: tuple[str, ...] = ('贴近', '中间', '拉远')


def distance_for(moment: str, *, prev: str = '') -> str:
    """这一拍该**贴多近**：`贴近 / 中间 / 拉远`。

    专业论述（Cohn）：距离是**连续可调**的，来回推拉本身就是节奏；
    一直贴着是满篇心声，一直拉着是满篇旁白 —— 两种都实测出现过。

    | 时机 | 距离 | 为什么 |
    |---|---|---|
    | 冲突 / 转折 | `贴近` | 最难受的那一下该进他脑子里，读者才跟着疼 |
    | 收束 | `拉远` | 收场要把镜头拉开，否则读者出不来 |
    | 其余（开场/日常/查稿/成稿） | `中间` | 用他的判断词但不加引号，最省也最稳 |

    ★ **连拍不重复**：上一拍已经贴着了，这一拍强制换到 `中间`。
      为什么：贴着写三拍就是满篇心声（那正是"We 要么全贴要么全拉"的另一头）。
    ⚠ 纯函数、零成本，每拍都算得起 —— **不调模型**。
    [EN] How close this beat stands. Close for conflict/turn (the hurt must be inside his head),
    [EN] far for closing (pull the camera back or the reader cannot leave), middle otherwise.
    [EN] ★ **No two close beats in a row**: if the previous beat was already close, force middle --
    [EN] three close beats in a row is walls of inner voice (the other end of the same problem).
    [EN] ⚠ Pure function, zero cost, no model call.
    """
    m = str(moment or '日常')
    if m in ('冲突', '转折'):
        want = '贴近'
    elif m == '收束':
        want = '拉远'
    else:
        want = '中间'
    if want == '贴近' and str(prev or '') == '贴近':
        return '中间'
    return want
