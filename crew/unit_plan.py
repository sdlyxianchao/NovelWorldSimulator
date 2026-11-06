# -*- coding: utf-8 -*-
"""**写作层按情节单元写**：把一天的材料切成"情节单元"，每一站按它的篇幅定该写多厚。

用户 2026-10-26：
  「真正小说里并不一定每天都有故事 而是根据大纲 可能会快速跳过很多时间
    每隔一段时间才会有1个事件集中描写 …… 小说时间不是匀速流逝的」
  「这个不止改这里，小说写作、框架搭建、情节设定都要优化」
  「注意 一个事件可能跨天」

以前整理稿（`crew.agents.Novelist._transcribe`）**按 6000 字机械切块**，
每一块都要求"写完整、事件一处都不许漏" ⇒ 21.3 万字的材料等密度转写成 12.9 万字，
读起来是"逐块转录剧本"：**赶路那三个月**和**开庭那一场**一样厚。

这一层只做一件事：把"按字数切"换成"按**情节单元**切"，并把篇幅档
（`ingest.progress.WEIGHTS`）翻成**可数**的写作目标（**句数**，不是字数 ——
实测模型不数字数：写"不超过四十字"，连跑四次，长句占比 21→60→47→85.7%）。

  · `详`   —— 每一幕 3~6 句（开庭那一场写足）
  · `中`   —— 每一幕 1~2 句
  · `略`   —— **整站** 2~6 句（不管它演了几幕）
  · `带过` —— **整站** 1~2 句

⚠ 为什么单位是"幕"：幕是材料里**数得出来**的（`〔第 N 幕 ⋯〕` 一行一幕）。
⚠ 这一层**纯函数、零成本、不调模型**：它决定"写多厚"，不写一个字。

English:
**Write by plot unit**, not by character count. The organizer used to slice a day's material
into mechanical 6000-character chunks and demand every chunk be written in full, so 213k
characters of material became 129k characters of prose at uniform density -- "three months of
travel" as thick as "the hearing". This module only re-slices by **plot unit** (the node name
already present in every act header) and turns the length tier into a **countable** target
(sentences, not characters: the model provably does not count characters). Pure functions,
zero cost, no model call.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

#: 幕头：`〔第 3 幕 · 子时 23:40 · 临街楼 · 入楼收留〕`（最后一个字段是**节点名**，可能没有）
#: ⚠ 与 `sim/loop._day_lines` 是同一份格式 —— 那边写、这边读，改格式要两边一起改。
# [EN] Act header. The last field is the **node name** and may be absent. Same format as
# [EN] `sim/loop._day_lines`: written there, read here -- change both together.
HEAD_RE = re.compile(r'^\s*〔(?P<body>.+?)〕\s*$')

#: 幕头的**第一字段必须是 `第 N 幕`** —— 光靠 `〔…〕` 认不出来。
#:
#: ★★★ 2026-10-26 实测踩到的坑（真数据 133 幕直接炸成 **211 个单元**）：
#:   材料里还有别的方括号行，形状一模一样：
#:     · `〔切至 · 柜上长凳｜同一时刻〕`  ← 转场标记
#:     · `〔事件 · 伏笔激活〕`            ← 剧情节点
#:     · `〔出场〕某某` / `〔心声·某人〕…`（这些带尾巴，不算）
#:   只按 `〔…〕` 判，转场标记就成了"幕头"，它的最后一个字段是**地点+时刻**，
#:   匹配不上站名 ⇒ 每两幕切一刀 ⇒ 单元数与目标字数一起爆掉（25.7 万字）。
#:   ⇒ `第 N 幕` 是**唯一的判别特征**（`_day_lines` 写幕头时第一项就是它）。
# [EN] The first field of an act header **must be `第 N 幕`** -- `〔…〕` alone cannot tell them
# [EN] apart. ★★★ Measured on real data (2026-10-26): the day's 133 acts blew up into **211
# [EN] units** because the material also carries same-shaped bracket lines: `〔切至 · 地点｜时刻〕`
# [EN] (a transition marker), `〔事件 · …〕` (a plot node). Their last field is a place + time, which
# [EN] never matches a station name, so every second act cut a new unit and the total target
# [EN] exploded to 257k characters. `第 N 幕` is the **only discriminating feature** -- it is what
# [EN] `_day_lines` writes first.
_ACT_HEAD_RE = re.compile(r'^第\s*\d+\s*幕$')
_FIELD_SEP = ' · '

#: 篇幅档 → **整站**写几句 `(下限, 上限)`。`略` / `带过` 不管演了几幕。
#: ⚠ `带过` 也**必须是 1 句起**：一句话都不写等于这一站不存在，
#:   而读的人要从这里知道"过了多久、到了哪儿"。
# [EN] Length tier -> **whole station** sentence count, regardless of how many acts played.
# [EN] ⚠ `带过` still needs at least 1 sentence: writing nothing erases the station, and the
# [EN] reader needs to learn "how much time passed, where we ended up".
WHOLE_SENTENCES: dict[str, tuple[int, int]] = {
    '略': (2, 6),
    '带过': (1, 2),
}

#: 篇幅档 → **重档**（`详`/`中`）的正文目标：`(材料占比, 下限, 上限)`，单位汉字。
#:
#: ★★★ 为什么重档按**材料占比**而不是"每幕几句"：
#:   幕的体量并不齐（实测一幕约 1,500 字材料，但配置不同时可能差一倍），
#:   按幕算会在"幕少而大"的一站上把整整一场戏压成两句 —— 那是**另一种**错误（把详写没）。
#:   材料量则与"演了多少拍"直接成正比，按占比给最稳。
#:
#: ⚠ 数不是拍的：
#:   · `详` 0.20 —— 实测老行为是 0.58（4.4 万字材料出 2.6 万字），那正是"逐块转录剧本"；
#:     0.20 意味着 6,000 字的材料出 1,200 字（约 6 段），还像一章，但不再是抄录；
#:   · `中` 0.10 —— 一半的密度；
#:   · 下限/上限是**绝对闸**：材料再少也别写不到 1,000/500 字（一章不能只有两句），
#:     材料再多也别一坨（`详` 一块最多 2,600 字，超了就是"写爆"）。
#:   · `略`/`带过` 不看材料量：它们要的就是"两三句带过"（见 `WHOLE_SENTENCES`）。
# [EN] Heavy tiers derive the target from the **material ratio**, not per act: acts vary in size
# [EN] (measured ~1,500 characters each), so per-act math can crush a whole scene into two
# [EN] sentences -- the opposite error. Material volume is directly proportional to how many beats
# [EN] were played. `详` 0.20 (the old behaviour was effectively 0.58, which is exactly the
# [EN] "block-by-block transcription"), `中` 0.10. The floor/ceiling are absolute gates: never
# [EN] under 1,000/500 characters, never over 2,600 per piece. Light tiers ignore material volume.
HEAVY_TARGET: dict[str, tuple[float, int, int]] = {
    '详': (0.22, 1200, 3000),
    '中': (0.12, 700, 1600),
}

#: 一句中文小说大约多少汉字（用来把"句数"折成"字数"）。
#: 实测真人成稿每句 18~28 汉字（`crew/prose_flow.SENTENCE_MAX` 是 45，那是"太长"的线）。
# [EN] Roughly how many CJK characters one sentence of Chinese prose holds. Human samples run
# [EN] 18-28 per sentence.
CHARS_PER_SENTENCE = 26

#: 一段正文大约多少汉字 —— **重档给模型的"可数单位"是段数**。
#: ★ 为什么是段而不是句：6000 字的一站要说"写 230 句"，那个数字对模型没有意义；
#:   而"写 6 段"它判得了，而且与第 4 条（一段三到六句、两百字以内）自洽。
# [EN] Characters per paragraph -- **the countable unit given to the model for heavy tiers is the
# [EN] paragraph count**. "Write 230 sentences" means nothing to a model; "write 6 paragraphs"
# [EN] it can judge, and it agrees with rule 4 (3-6 sentences, under 200 characters each).
CHARS_PER_PARA = 200

#: `略`/`带过` 的硬上限倍数。超了**按句末剪**（这两档要的就是"一两句带过"）。
# [EN] Hard-cap factor for `略`/`带过`; over this, **trim at a sentence boundary** -- these tiers
# [EN] exist precisely to be one or two sentences.
LIGHT_SLACK = 1.6

#: 轻单元（`略`/`带过`）的档名字。**一处定义**，别处一律用 `is_light()`。
# [EN] The light tiers. Defined once; everything else calls `is_light()`.
LIGHT_WEIGHTS: tuple[str, ...] = ('略', '带过')


def is_light(weight: str) -> bool:
    """这一站是不是"一句话带过"的那一档。"""
    return str(weight or '') in LIGHT_WEIGHTS


# ── 幕头解析 ──────────────────────────────────────────────────────────
def header_fields(line: str) -> list[str] | None:
    """**幕头**行 ⇒ 字段列表；不是幕头返回 `None`。

    ⚠ 必须同时满足两条：整行是 `〔…〕`，**而且第一字段是 `第 N 幕`**。
      只判第一条的话，`〔切至 · 地点｜时刻〕` / `〔事件 · …〕` 都会被当成幕头
      （见 `_ACT_HEAD_RE` 那段实测）。
    [EN] **Act header** line => fields; `None` otherwise. Two conditions: the whole line is
    [EN] `〔…]` **and** the first field is `第 N 幕`. Judging only the first treats transition
    [EN] markers and plot-node lines as headers (see the note on `_ACT_HEAD_RE`).
    """
    m = HEAD_RE.match(str(line or ''))
    if not m:
        return None
    fields = [x.strip() for x in m.group('body').split(_FIELD_SEP) if x.strip()]
    if not fields or not _ACT_HEAD_RE.match(fields[0]):
        return None
    return fields


#: 一幕材料大约多少字（用来在**没有幕头**的材料上估幕数）。
#: 实测：第 1 天 30 幕 / 44,736 字符 ⇒ 一幕约 1,490 字；这里取 1,200（宁可多算几幕，
#: 目标句数宁可略松 —— 算少了会把一整天的戏压成两句）。
# [EN] Roughly how many characters one act of material holds, used to estimate the act count
# [EN] when the material carries **no headers**. Measured: 30 acts / 44,736 characters => ~1,490
# [EN] per act; 1,200 is used here (deliberately on the low side: over-estimating a little is
# [EN] safe, under-estimating would crush a whole day into two sentences).
CHARS_PER_ACT = 1200

#: 相邻轻站合并成一次"掠过"时，材料总量可以放到单次上限的几倍。
#: ⚠ `CREW_DAY_NOVEL_CHUNK`（6000）守的是**输出**压力（"给多少就写多少"），
#:   而轻档的输出固定在 2~6 句 ⇒ 输入再长也不会写长，可以放宽。
# [EN] How many times the single-call cap a montage may hold. `CREW_DAY_NOVEL_CHUNK` guards
# [EN] **output** pressure ("how much you feed is how much it writes"), while a light pass is
# [EN] pinned to 2-6 sentences => a longer input cannot lengthen the output.
LIGHT_PACK_FACTOR = 4


def acts_of(text: str) -> int:
    """一段材料里有**几幕**。

    ① 有幕头就**数**幕头（那是真的、可数的）；
    ② 一个幕头都没有（纯文本材料 / 老项目的叙事行）⇒ **按字数估**。
    ⚠ 都不许返回 0：0 幕会让目标句数变成 0，整段正文一个字都不许写 ——
      那是"素材没有幕头"时**静默丢稿**。
    [EN] Count the acts. (1) With headers, count them -- that is real and countable. (2) With no
    [EN] headers (plain material, an old project's narrative lines), estimate from length.
    [EN] ⚠ Never 0: zero acts makes the target zero sentences, i.e. silently dropping the whole
    [EN] passage whenever the material carries no headers.
    """
    s = str(text or '')
    n = 0
    for ln in s.split('\n'):
        if header_fields(ln) is not None:
            n += 1
    if n:
        return n
    return max(1, len(s.strip()) // CHARS_PER_ACT)


def _known_names(nodes) -> set[str]:
    """进度表里所有可用作"幕头最后一字段"的名字（`名称` 与 `id`）。"""
    out: set[str] = set()
    for nd in (nodes or []):
        if not isinstance(nd, dict):
            continue
        for key in ('名称', 'name', 'id'):
            v = str(nd.get(key) or '').strip()
            if v:
                out.add(v)
    return out


def _unit_name(line: str, known: set[str]) -> str | None:
    """幕头行 ⇒ 节点名（`''` = 这行是幕头但没写节点名；`None` = 不是幕头）。"""
    f = header_fields(line)
    if f is None:
        return None
    if len(f) < 2:
        return ''
    last = f[-1]
    return last if last in known else ''


# ── 情节单元 ──────────────────────────────────────────────────────────
@dataclass
class Unit:
    """**一个情节单元**＝同一站在这一天里演的那一截。

    `lines` 是原样的材料行（含它自己的幕头），**一个字都不改** ——
    这一层只决定"切在哪儿、写多厚"，不加工材料。
    [EN] One plot unit: the slice of one station played today. `lines` are the raw material
    [EN] lines including their own headers, untouched; this layer only decides where to cut and
    [EN] how thick to write.
    """
    name: str = ''
    weight: str = '中'
    #: 篇幅是**程序推的**（节点上没写）—— 与 `ingest.progress.inferred` 同一口径。
    # [EN] The length tier was **inferred** (the node does not state one).
    inferred: bool = False
    lines: list[str] = field(default_factory=list)

    def material(self) -> str:
        return '\n'.join(self.lines).strip()

    @property
    def acts(self) -> int:
        return acts_of(self.material())

    @property
    def light(self) -> bool:
        return is_light(self.weight)

    def label(self) -> str:
        """给人看/给提示词看的一行身份：`入楼收留｜详｜6 幕`。"""
        bits = [self.name or '（材料没标站名）', self.weight]
        if self.inferred:
            bits.append('程序判的')
        bits.append(f'{self.acts} 幕')
        return '｜'.join(bits)


def _weight_of(node: dict | None) -> tuple[str, bool]:
    """节点 ⇒ `(篇幅档, 是不是推的)`。"""
    from ingest.progress import DEFAULT_WEIGHT, WEIGHTS, infer_weight, ProgressNode
    if not isinstance(node, dict):
        return DEFAULT_WEIGHT, True
    w = str(node.get('篇幅') or '').strip()
    if w in WEIGHTS:
        return w, False
    # 老项目 / 装配时没补 ⇒ 现推一个（与 `director/day_plan.beat_budget_for` 同一个口径）
    # [EN] Old project or not filled at assembly -> infer one (same rule as `beat_budget_for`).
    try:
        return infer_weight(ProgressNode(id=str(node.get('id') or ''),
                                         name=str(node.get('名称') or ''),
                                         summary=str(node.get('概要') or ''),
                                         criteria='')), True
    except Exception:                                            # noqa: BLE001
        return DEFAULT_WEIGHT, True


def _index_nodes(nodes) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for nd in (nodes or []):
        if not isinstance(nd, dict):
            continue
        for key in ('名称', 'name', 'id'):
            v = str(nd.get(key) or '').strip()
            if v and v not in idx:
                idx[v] = nd
    return idx


def plan_units(lines, *, nodes=None, current: str = '') -> list[Unit]:
    """把一天的材料切成**情节单元**（按幕头里的节点名，连续同站算一个）。

    ⚠ 一个站都没标（材料没有幕头 / 幕头没有站名）⇒ **一个单元**，
      篇幅按 `current` 那一站走（取不到就 `中`）。**这就是旧行为的退化路径**：
      单元数 = 1，写法和改之前完全一样，不会因为"没标站名"而写坏。
    ⚠ 同一站**分两段演**（中间去了别处又回来）⇒ 算**两个单元**：按材料里的**出现顺序**
      切，不是按名字合并 —— 合并会把时间线搅乱（那正是"时序混乱"的来源）。
    [EN] Split the material into plot units by the node name in the act header; consecutive
    [EN] acts of the same station form one unit. ⚠ No station names at all => **one unit**
    [EN] (the degenerate path: identical to the old behaviour). ⚠ A station played in two
    [EN] separate stretches counts as **two units**, in material order -- merging by name would
    [EN] scramble the timeline.
    """
    rows = [str(x) for x in (lines or [])]
    if not rows:
        return []
    idx = _index_nodes(nodes)
    known = set(idx)
    default_weight, default_inferred = _weight_of(idx.get(str(current or '').strip()))

    out: list[Unit] = []
    cur_name: str | None = None
    cur: list[str] = []
    for ln in rows:
        name = _unit_name(ln, known)
        if name is not None and cur and name != cur_name:
            out.append(Unit(name=cur_name or '', lines=cur))
            cur = []
        if name is not None:
            cur_name = name
        elif cur_name is None:
            cur_name = ''
        cur.append(ln)
    if cur:
        out.append(Unit(name=cur_name or '', lines=cur))

    for u in out:
        if u.name and u.name in idx:
            u.weight, u.inferred = _weight_of(idx[u.name])
        else:
            u.weight, u.inferred = default_weight, default_inferred
    return out


# ── 写作目标（可数）────────────────────────────────────────────────────
@dataclass
class Target:
    """**这一站写多厚**。

    · 重档（`详`/`中`）：`paras` 是给提示词的**段数**（可数），`max_chars` 是预算与日志的量纲；
    · 轻档（`略`/`带过`）：`sent_lo`~`sent_hi` 是句数（也进提示词），`max_chars` 是剪的线。

    ⚠ 三个字段各有各的用处，**不要互相换算掉**：段数是给模型的，句数是给轻档的，
      字数是给代码（预算/剪/日志）的。
    [EN] How thick this station is. Heavy tiers hand the model a **paragraph count** (countable)
    [EN] and keep `max_chars` for the budget/log line; light tiers hand it a **sentence count**.
    [EN] Three fields, three jobs -- don't collapse them into one.
    """
    weight: str = '中'
    sent_lo: int = 1
    sent_hi: int = 2
    max_chars: int = 120
    #: 重档要写几段 `(下限, 上限)`；轻档是 `(0, 0)`（轻档不按段说）。
    # [EN] Paragraph range for heavy tiers; `(0, 0)` for light ones.
    paras: tuple[int, int] = (0, 0)

    @property
    def light(self) -> bool:
        return is_light(self.weight)

    @property
    def tokens(self) -> int:
        """该给的 `max_tokens`。

        ★ 按**目标**给，不按材料长度给：材料长而目标只有两句时，
          按材料给的预算会让模型放开写（"钱松了，人就会多写"）。
        · 重档：够写完 `max_chars`（那已经是理想值的两倍）⇒ ×1.5；
          再往下卡就会截在半句上，而 `llm.replies` 会把半句当有效输出 —— 截断比写长难看。
        · 轻档：给到剪线的两倍（×3），超了反正按句末剪，先让它把话说完。
        [EN] Derive `max_tokens` from the **target**, not the material length: a generous budget
        [EN] for a two-sentence target is exactly what makes the model ramble. Heavy tiers get
        [EN] enough to finish `max_chars` (already 2x the ideal) -- any tighter and it truncates
        [EN] mid-sentence, which `llm.replies` accepts as valid output. Light tiers get twice the
        [EN] trim line; overshoot is trimmed at a sentence boundary anyway.
        """
        factor = 3.0 if self.light else 1.5
        return max(180, int(self.max_chars * factor))


def _paras_of(chars: int) -> tuple[int, int]:
    """汉字数 ⇒ 段数区间（一段约 `CHARS_PER_PARA` 字，上限放宽一档）。"""
    n = max(1, int(round(chars / CHARS_PER_PARA)))
    return n, n + max(1, n // 3)


def target_of(weight: str, material_chars: int) -> Target:
    """`(篇幅档, 这一片材料多少字)` ⇒ 写作目标。

    ★ 详/中按**材料量**给（占比 + 绝对上下限），略/带过按**整站**给固定句数 ——
      这一条就是"详略"本身：一个演了 30 幕的 `略` 站，也还是两句带过
      （那才是"快速跳过很多时间"）。
    [EN] `详`/`中` scale with the **material volume** (ratio plus absolute gates);
    [EN] `略`/`带过` get a fixed whole-station sentence count. That difference *is* the
    [EN] thick/thin allocation: a `略` station that happened to play 30 acts still gets two
    [EN] sentences -- exactly what "skip whole months quickly" means.
    """
    w = str(weight or '')
    if w in WHOLE_SENTENCES:
        lo, hi = WHOLE_SENTENCES[w]
        return Target(weight=w, sent_lo=lo, sent_hi=hi,
                      max_chars=int(hi * CHARS_PER_SENTENCE * LIGHT_SLACK))
    if w not in HEAVY_TARGET:
        w = '中'
    ratio, floor, ceil = HEAVY_TARGET[w]
    body = int(max(0, int(material_chars or 0)) * ratio)
    chars = max(int(floor), min(int(ceil), body or int(floor)))
    return Target(weight=w,
                  sent_lo=max(1, chars // CHARS_PER_SENTENCE),
                  sent_hi=max(2, int(chars / CHARS_PER_SENTENCE * 1.4)),
                  max_chars=chars,
                  paras=_paras_of(chars))


def target_for(unit: Unit) -> Target:
    return target_of(unit.weight, len(unit.material()))


def montage_target(units: list[Unit]) -> Target:
    """**一次"掠过"**（几个相邻的轻站合写）的总目标：各站目标相加。

    ⚠ 相加而不是"取最厚的那个"：三站各一句就是三句，合成一句等于有两站没写。
    [EN] Total target for a montage of adjacent light units: the per-unit targets **added**.
    [EN] Adding, not taking the thickest: three stations at one sentence each is three
    [EN] sentences; collapsing to one erases two stations.
    """
    ts = [target_for(u) for u in units] or [target_of('带过', 0)]
    return Target(weight=str(getattr(units[0], 'weight', '带过') if units else '带过'),
                  sent_lo=sum(t.sent_lo for t in ts),
                  sent_hi=sum(t.sent_hi for t in ts),
                  max_chars=sum(t.max_chars for t in ts))


def montage_block(units: list[Unit]) -> str:
    """**一次"掠过"**的写作要求：几站按顺序各写一小段。

    ★ 为什么把几站合成一次：这几站本来就是"几个月过去了"，一次写完，
      读者看到的才是一段掠过；分三次写，每站都会各自起个场面，反而变厚。
    ⚠ 只有一站时**不能用"掠过"的口径**（"共 1 站的掠过"读起来像程序出错），
      退回单站的写法。
    [EN] The montage block: several stations, one short paragraph each, in material order.
    [EN] These stations *are* "months went by"; writing them in one pass is what makes it read
    [EN] as a sweep instead of each station opening its own scene. ⚠ With a single station this
    [EN] wording is wrong ("a sweep of 1 station" reads like a bug), so fall back to the
    [EN] single-station block.
    """
    if len(units) == 1:
        return density_block(units[0])
    lines = ['── 这一批是**几段时间的掠过**（共 %d 站，按材料里的先后顺序写）──' % len(units)]
    for i, u in enumerate(units, 1):
        t = target_for(u)
        lines.append(f'{i}. {u.name or "（材料没标站名）"}｜篇幅 {t.weight}｜{u.acts} 幕 '
                     f'→ **{t.sent_lo}~{t.sent_hi} 句**')
    lines.append(
        '★ 每站**各写一小段**（一段就是那几句话），段与段的顺序**跟材料一致**；\n'
        '  **不许把几站并成一段**（那样就分不清过了多久），也**不许**给任何一站展开场面、\n'
        '  写对白。这一批的用处只有一个：让读者知道**时间过去了、位置变了**。')
    return '\n'.join(lines) + '\n'


def density_block(unit: Unit, target: Target | None = None) -> str:
    """**这一站写多厚** —— 进提示词的那一段。

    ⚠ 提示词越短越被遵守：这里是"必须说、且只在这里说"的那几句。
      不给这段，模型只有"写完整一章"一个默认档 ⇒ 全篇等密度（改之前就是这样）。
    [EN] The "how thick" block for the prompt. Shorter prompts are obeyed more, so this carries
    [EN] only what must be said. Without it the model has exactly one default gear -- "write the
    [EN] chapter in full" -- and the whole day comes out at uniform density.
    """
    t = target or target_for(unit)
    head = f'── 这一站要写多厚（{unit.name or "材料没标站名"}｜篇幅 {t.weight}）──\n'
    # ⚠ 这里**不写"材料里有 N 幕"**：一个站太长时会被切成几片分别写，
    #   而这 N 是**整站**的幕数 —— 写进每一片就成了假数字（模型会照它凑段落）。
    # [EN] No "N acts of material" here: a long station is split into several pieces, and N is the
    # [EN] **whole station's** act count -- printing it in every piece is a false number the model
    # [EN] would pad paragraphs against.
    if t.weight == '详':
        body = (f'★ 这是**要写足**的一站：写 **{t.paras[0]}~{t.paras[1]} 段**'
                '（每段三到六句、两百字以内）。\n'
                '  **每一幕都要落到正文**：谁做了什么、谁说了什么，一处都不许漏；\n'
                '  动作、对白、环境都铺开写 —— 读者应该觉得"这一场我亲眼看见了"。\n')
    elif t.weight == '中':
        body = (f'★ 这一站按**正常节奏**写：写 **{t.paras[0]}~{t.paras[1]} 段**。\n'
                '  交代清楚发生了什么、谁说了什么，不必把每一拍都铺开；\n'
                '  过场与重复的日常可以合并成一句带过。\n')
    elif t.weight == '略':
        body = (f'★★★ 这一站**只交代结果**：整站写 **{t.sent_lo}~{t.sent_hi} 句**就过。\n'
                f'  材料里有 {unit.acts} 幕，但你**不要逐幕写** —— 挑那件真正改变了什么的事，'
                '一两句话带过去。\n'
                '  过场、赶路、迎来送往、重复的日常，**一概不写**。\n')
    else:
        body = ('★★★ 这一站**一句带过**：写 **1~2 句**，说明"过了多久 / 到了哪儿 / '
                '发生了什么变化"，然后立刻往下走。\n'
                '  **不写场面、不写对白、不写心理** —— 这一站的全部价值就是让读者知道时间过去了。\n')
    return head + body


# ── 打包成"写作次"──────────────────────────────────────────────────────
def pack(units: list[Unit], size: int) -> list[list[Unit]]:
    """把单元打包成若干次写作调用。

    · 重单元（详/中）**各自一次**（材料太长由调用方再按行切，见 `_split_for_transcribe`）；
    · 连续的轻单元（略/带过）**合成一次"蒙太奇"**：三站各一句话，读起来正是
      "几站之间隔了几个月"该有的写法，而且省掉两次带全套提示词的调用。
    ⚠ 只在**相邻**时合并：跨越一个重单元就不能合 —— 顺序会被打乱。
    [EN] Pack units into writing calls. Heavy units get one call each (the caller still splits
    [EN] over-long material by line). Consecutive light units merge into **one montage call**:
    [EN] three stations at one sentence each is exactly how "months pass between stations"
    [EN] should read, and it saves two full-prompt calls. ⚠ Merge only **adjacent** units.
    """
    groups: list[list[Unit]] = []
    buf: list[Unit] = []
    buf_len = 0
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = 6000
    if size <= 0:
        size = 10 ** 9
    # 轻站可以放宽到 LIGHT_PACK_FACTOR 倍（见那个常量的说明）
    # [EN] Light stations may go up to LIGHT_PACK_FACTOR times the cap (see that constant).
    light_size = int(size * LIGHT_PACK_FACTOR)

    for u in units:
        n = len(u.material())
        if not u.light:
            if buf:
                groups.append(buf)
                buf, buf_len = [], 0
            groups.append([u])
            continue
        if buf and buf_len + n > light_size:
            groups.append(buf)
            buf, buf_len = [], 0
        buf.append(u)
        buf_len += n
    if buf:
        groups.append(buf)
    return groups


# ── 轻单元的硬上限 ────────────────────────────────────────────────────
_SENT_END = '。！？…'


def trim_light(text: str, target: Target) -> tuple[str, int]:
    """轻单元（略/带过）写超了 ⇒ **按句末剪到上限**，返回 `(正文, 删掉的字数)`。

    ★ 为什么要剪：这两档的全部意义就是"一两句带过"。模型写 800 字，
      这一站就还是"写足了"，全篇又回到等密度 —— 而这条约束没法靠提示词保证
      （实测提示词的遵循率 40~74%）。
    ⚠ 只按**句末**剪：剪出来的仍是完整句子，不是半句。
    ⚠ 重档（详/中）**绝不剪** —— 那两档要求事件一处不漏，尾巴就是结局。
    [EN] Trim an over-long light passage **at a sentence boundary**. These tiers exist to be one
    [EN] or two sentences; a model that writes 800 characters has undone the whole point, and the
    [EN] prompt alone cannot hold the line (measured obedience 40-74%). Trim only at sentence
    [EN] ends, never mid-sentence. Heavy tiers are **never** trimmed: their tail is the ending.
    """
    s = str(text or '').strip()
    if not s or not target.light:
        return s, 0
    cap = int(target.max_chars)
    if len(s) <= cap:
        return s, 0
    cut = -1
    for i, ch in enumerate(s[:cap + 1]):
        if ch in _SENT_END:
            cut = i
    if cut < 0:
        # 一句都没收住（模型在写一个超长句）⇒ 不剪：剪了就是半句。
        # [EN] Not a single sentence end within the cap => don't cut (a half sentence is worse).
        return s, 0
    kept = s[:cut + 1].strip()
    return kept, len(s) - len(kept)
