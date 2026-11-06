# -*- coding: utf-8 -*-
"""手艺**调度器**：按"这一刻该读哪几条"挑，而不是"文件顺序前几条"。

## 为什么要有这个模块

2026-10-18 用户：「71 条手艺也全部落地 且根据需要动态映射……都在合理的实际的
动态的映射到不同类型且在合适的时候进行调用」。

盘点出来的硬数据：**81 条里有 24 条从来没到过任何人的提示词**
（`crew/agents._craft_for` 的第 ③ 步是"遍历 `entries` 按 yaml 文件顺序补满"，
`entries` 的顺序是文件顺序，于是每个职位拿到的永远是同一批前几条）。

`_craft_for` 修过一次（2026-10-07 加 `READS` 点名），但那只是**手工给十几个职位
各点了 4–10 条**，剩下的靠"补满"撞运气。于是有三个问题：

1. **写进库里，永远读不到**（24 条）；
2. **读到了，也不合时宜** —— 演员在开场那一拍读到「章回钩子」，
   在收束那一拍读到「黄金三章」，都是噪声；
3. **同一职位每一拍读到的完全一样** —— 而"这一拍是日常还是转折"决定该读什么。

## 三条设计判断

### ① 候选池按**职位**定，不按"文件顺序"
职位读哪几架由 `crew/agents.SHELVES` 说（那是唯一真相，不在这里复制一份）。
池子里**全架都进**，不是前 N 条 —— 进不进提示词由下面的调度决定。

### ② 时机是**派生的**，不是手写标签
81 条 × 14 职位 × 7 时机 = 7938 个格子，手写必错且会漂。
`时机` 从条目的**名字与提示词**里按关键词派生（`_MOMENT_HINTS`），
yaml 里显式写了 `时机:` 的以 yaml 为准（留了升级口，现在一条都没写）。

### ③ 品级是**算出来的**，不是标上去的
```text
重  这个职位点名要读的（READS）＋ 本类型卡映射到的   ⇒ 这一拍说了算的
中  本职位货架里的其它条目                        ⇒ 常备
轻  兜底（同架但与这一刻无关的）                    ⇒ 偶尔提一次，避免匠气
```
`品级`（`重/中/轻`）**决定这一拍读几条**：重=读满、中=读满、轻=只读一半。
—— 日常拍不该被塞十条规矩（塞多了文本会变匠气，2026-10-18 实测过），
   开场和转折拍才该读满。这就是"由特定 Agent 负责品级"的落点：
   **导演**在 `director/supervisor.grade_beat()` 里定这一拍是重是轻，
   本模块只负责按那个品级调条数。

## 反例法要知道的一件事

`pick()` 的**可复现性**是硬要求：同一个 `(role, genre, moment, level, tick, k)`
必须给出同一个结果。绝不能用 `hash()` —— 它在 Python 3 里带 `PYTHONHASHSEED`
随机化，同一个 tick 两次跑会不同，判据就永远在飘。这里用 `_stable_hash()`
（按字符序号求和），跨进程稳定。
"""
from __future__ import annotations

import logging

from craft import craftmix as CM

_LOG = logging.getLogger("nws.craft.dispatch")

#: 这一拍处在故事的哪个位置（决定"该读什么"）。
#: ⚠ 顺序有含义：`MOMENTS[0]` 是缺省值（拿不准时按日常算，最不容易出错）。
# [EN] Where this beat sits in the story (decides "what to read"). Order matters:
# [EN] `MOMENTS[0]` is the default (when unsure, treat as daily -- least likely to hurt).
MOMENTS: tuple[str, ...] = ('日常', '开场', '冲突', '转折', '收束', '查稿', '成稿')

#: 品级：决定这一拍**读几条**（不是读哪几条）。
# [EN] Grade: decides **how many** entries this beat reads (not which ones).
LEVELS: tuple[str, ...] = ('重', '中', '轻')

#: 时机关键词表（**顺序敏感**：先匹配先生效）。
#: 为什么这样派生而不是手写：见模块头 ②。关键词取自条目的**名字 + 提示词**，
#: 所以条目改了名也会跟着走，不会像手写标签那样悄悄过期。
#: ⚠ 最后一条 `日常` 是兜底，不在这里 —— 匹配不到就是日常。
# [EN] Moment keyword table (order sensitive). Derived from the entry's **name + prompt**, so
# [EN] renaming an entry keeps it correct, unlike hand-written tags.
_MOMENT_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    # ── 收束：结尾、钩子、终场 ──
    (('章回', '结尾', '钩子', '终场', '收束', '归来', '收工'), '收束'),
    # ── 查稿：自查、检查、毒点 ──
    (('检查', '自查', '逐拍', '毒点', '可拍性', '一致性', '减头绪'), '查稿'),
    # ── 成稿：句子层面的活（文气、语域、停顿要不要写下来）──
    (('文气', '语域', '普通话', '口语', '句子', '停顿落在纸上', '话长短'), '成稿'),
    # ── 开场：建置、第一次亮相 ──
    (('开场', '开篇', '黄金三章', '铺垫', '催化', '登场', '平凡世界', '建置'), '开场'),
    # ── 冲突：对抗、两难、障碍 ──
    (('冲突', '反打', '反派', '障碍', '代价', '两难', '伦理', '考验'), '冲突'),
    # ── 转折：突转、发现、价值转变、中点 ──
    (('转折', '突转', '发现', '转变', '中点', '高潮', '磨难', '复活'), '转折'),
)

#: 品级 → 读满比例（分子/分母）。
#: ⚠ 三档**必须互不相同**：如果 `重` 与 `中` 都读满，那两个品级就是一个，
#:   判据"品级真的改变条数"永远证明不了任何事（成对判据会红）。
# [EN] Grade -> fraction of `k` to read. ⚠ The three must **differ**: if heavy and medium
# [EN] both read everything, they are the same grade and the criterion "grade changes the count"
# [EN] can never prove anything.
_LEVEL_RATIO: dict[str, tuple[int, int]] = {'重': (1, 1), '中': (3, 4), '轻': (1, 2)}


def _stable_hash(text: str) -> int:
    """跨进程稳定的散列（**不能用 `hash()`**，见模块头最后一节）。"""
    return sum((i + 1) * ord(c) for i, c in enumerate(str(text or '')))


def moment_of(name: str, entry: dict | None = None, *, fallback: str = '日常') -> str:
    """这一条适合**什么时候**读（派生）。

    ⚠ yaml 里显式写了 `时机:` 的以它为准 —— 那是留给"派生猜错"的升级口。
    [EN] When this entry is fit to be read (derived). An explicit `时机:` in yaml wins.
    """
    e = entry or (CM.load()['entries'].get(str(name or '')) or {})
    raw = str(e.get('时机') or '').strip()
    if raw:
        # 允许写一条，也允许写逗号/顿号分隔的多条；取第一个合法的
        for piece in raw.replace('、', ',').replace('/', ',').split(','):
            p = piece.strip()
            if p in MOMENTS:
                return p
    blob = f"{name} {e.get('原理') or ''} {e.get('提示词') or ''}"
    for keys, mom in _MOMENT_HINTS:
        for k in keys:
            if k in blob:
                return mom
    return fallback


def _shelf_roles(shelf: str) -> tuple[str, ...]:
    """读这一架的职位（**从 `SHELVES` 反查**，不在这里复制一份）。

    ⚠ 惰性 import：`crew.agents` 会 import 本模块（`craft_block`），
      顶层互相 import 会成环。
    [EN] Roles reading this shelf, **looked up from `SHELVES`** (not copied here).
    [EN] ⚠ Lazy import: `crew.agents` imports this module, so a top-level cycle would form.
    """
    try:
        from crew.agents import SHELVES
    except Exception:                                            # noqa: BLE001
        return ()
    return tuple(r for r, shelves in SHELVES.items() if shelf in shelves)


def pool(role: str, genre: str = '', structure: str = '') -> list[tuple[str, dict]]:
    """这个职位的**全部候选**（按架取全量，不截断）。

    返回 `[(名字, 条目)]`，顺序固定（按货架顺序 + 架内 yaml 顺序）——
    顺序固定是 `pick()` 可复现的前提。
    [EN] All candidates for this role (whole shelves, not truncated). Fixed order is the
    [EN] precondition for `pick()` reproducibility.
    """
    try:
        from crew.agents import SHELVES
    except Exception:                                            # noqa: BLE001
        return []
    shelves = SHELVES.get(str(role or '')) or ()
    if not shelves:
        return []
    entries = CM.load()['entries']
    out: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for shelf in shelves:
        for name, e in entries.items():
            if name in seen:
                continue
            if str(e.get('_货架') or '') == shelf:
                out.append((name, e))
                seen.add(name)
    return out


def tier(role: str, name: str, entry: dict, card: dict | None = None) -> str:
    """这一条的**品级**（重 / 中 / 轻）—— 见模块头 ③。

    · `重`：本职位 `READS` 点名的，或本类型卡映射到的（这一拍说了算的）
    · `中`：本职位货架里其余的
    · `轻`：同架、但既没被点名也没被映射（偶尔提一次的那一类）
    [EN] This entry's grade (heavy / medium / light) -- see header ③.
    """
    try:
        from crew.agents import READS
        named = tuple(READS.get(str(role or '')) or ())
    except Exception:                                            # noqa: BLE001
        named = ()
    if name in named:
        return '重'
    mapped = {str(x) for x in ((card or {}).get('playbook映射') or [])}
    if name in mapped:
        return '重'
    # 映射名与条目名可能不完全一致（`换地图节奏` vs `换地图`）⇒ 再用模糊判一次
    for m in mapped:
        hit = CM.resolve_entry(m)
        if hit is not None and str(hit.get('提示词')) == str(entry.get('提示词')):
            return '重'
    return '中'


def pick(role: str, *, genre: str = '', structure: str = '', moment: str = '日常',
         level: str = '中', k: int = 4, tick: int = 0,
         avoid: tuple[str, ...] | list[str] = ()) -> list[tuple[str, str, str]]:
    """挑出这一拍该读的条目：`[(名字, 提示词片段, 品级)]`。

    挑选顺序（**这就是"动态映射"的全部规则**）：

    1. **池** = 这个职位读的每一架的全部条目（`pool()`）；
    2. 按**时机**分两组：`时机 == moment` 的在前，其余在后 ——
       时机对不上的不是删掉，是排到后面（万一这一拍没有对得上的，总得有几条可读）；
    3. 组内按**品级**（重 → 中 → 轻）；
    4. 同组同品级内**环形轮换**：`offset = (tick*7 + stable_hash(role)) % n`，
       这样拍数往前走，同一职位读到的东西会换 —— 81 条都能轮到
       （老实现"永远取前 N 条"的修法就是这个）；
    5. `avoid` 里的（这一场已经读过的）排到最后 —— 不是硬删，
       全都读过了就允许重读（否则这一场后半段会没东西可读）；
    6. 条数 = `k` 按品级折算（`轻` 只读一半）。

    ⚠ **限流不在这里放宽**：每条仍走 `CM._clip_tokens(…, CM.MAX_ENTRY_TOKENS)`，
      总条数由 `k` 与品级决定。想多读就传更大的 `k`，别改这个函数的默认。
    [EN] Pick what this beat should read. Rules 1-6 above are the whole of "dynamic mapping".
    [EN] ⚠ Rate limiting is still enforced (`MAX_ENTRY_TOKENS` per entry, count by `k` and grade).
    """
    cands = pool(role, genre, structure)
    if not cands:
        return []
    card = CM.card(genre, structure) or {}
    mom = str(moment or '日常')
    if mom not in MOMENTS:
        mom = '日常'
    lvl = str(level or '中')
    if lvl not in LEVELS:
        lvl = '中'

    avoid_set = {str(x) for x in (avoid or ())}
    rows: list[tuple[int, int, int, str, str, str]] = []
    for idx, (name, e) in enumerate(cands):
        tip = str(e.get('提示词') or e.get('原理') or '').strip()
        if not tip:
            continue
        t = tier(role, name, e, card)
        # 排序键：时机对上(0) / 没对上(1) → 品级(重0 中1 轻2) → 是否躲开(0/1) → 环形位置
        mom_ok = 0 if moment_of(name, e) == mom else 1
        lvl_rank = {'重': 0, '中': 1, '轻': 2}[t]
        seen = 1 if name in avoid_set else 0
        rows.append((mom_ok, lvl_rank, seen, idx, name, tip))
    if not rows:
        return []

    # 组内环形：先算出每组的长度，再按 (tick, role) 定起点。
    # ⚠ 不用整体排序后切片 —— 那等于"按排位固定取前 N"，又回到老毛病。
    # [EN] Ring inside each (moment, tier) group: compute group size, then pick a start point
    # [EN] from (tick, role). Not "sort then slice", which is the old bug again.
    grouped: dict[tuple[int, int], list[tuple[int, int, str, str]]] = {}
    for mom_ok, lvl_rank, seen, idx, name, tip in rows:
        grouped.setdefault((mom_ok, lvl_rank), []).append((seen, idx, name, tip))

    order = sorted(grouped)
    picked: list[tuple[str, str, str]] = []
    # 品级折算条数
    num, den = _LEVEL_RATIO[lvl]
    want = max(1, (int(k) * num + den - 1) // den) if int(k) > 0 else 0
    base = _stable_hash(role) + int(tick or 0) * 7
    for key in order:
        if len(picked) >= want:
            break
        items = grouped[key]
        # 组内先按"躲开过的排后面"，再按环形起点取
        fresh = [x for x in items if x[0] == 0]
        stale = [x for x in items if x[0] == 1]
        for bucket in (fresh, stale):
            if not bucket or len(picked) >= want:
                continue
            n = len(bucket)
            off = (base + key[1]) % n
            rotated = bucket[off:] + bucket[:off]
            for _seen, _idx, name, tip in rotated:
                if len(picked) >= want:
                    break
                picked.append((name, CM._clip_tokens(tip, CM.MAX_ENTRY_TOKENS),
                               {'0': '重', '1': '中', '2': '轻'}[str(key[1])]))
    return picked


def render(picked: list[tuple[str, str, str]]) -> str:
    """把 `pick()` 的结果排成提示词里的那几行。

    ⚠ **不带品级标记**：`重/中/轻` 是内部调度用的，写进提示词只会让模型
      去琢磨"为什么这条是重"，反而分散注意力（我们踩过"清单件数写死"的坑）。
    [EN] Render into prompt lines. ⚠ No grade tag: grades are for scheduling; exposing them
    [EN] only makes the model wonder "why is this one heavy".
    """
    return '\n'.join(f'〔{name}〕{tip}' for name, tip, _lv in picked)


def coverage(role: str, genre: str = '', structure: str = '',
             *, k: int = 4, ticks: int = 60) -> dict[str, list[str]]:
    """**哪些条目在这一职位上真的能被选中**（自查 + 判据用）。

    返回 `{条目名: ['日常@3', ...]}`，只列真的出现过的。
    为什么在模块里而不是判据里算：判据要复用它，而"两份实现"是本项目的万恶之源。
    [EN] Which entries actually get picked for this role (self-check + criteria). Returns
    [EN] `{name: ['日常@3', ...]}`.
    """
    seen: dict[str, list[str]] = {}
    for mom in MOMENTS:
        for t in range(max(1, int(ticks))):
            for name, _tip, _lv in pick(role, genre=genre, structure=structure,
                                        moment=mom, level='重', k=k, tick=t):
                seen.setdefault(name, []).append(f'{mom}@{t}')
    return seen


def reachable(*, k: int = 4, ticks: int = 60) -> set[str]:
    """**全部职位合起来，哪些条目够得到**（判据要的那一个数）。"""
    out: set[str] = set()
    try:
        from crew.agents import SHELVES
        roles = tuple(SHELVES)
    except Exception:                                            # noqa: BLE001
        return out
    for role in roles:
        for mom in MOMENTS:
            for t in range(max(1, int(ticks))):
                for name, _tip, _lv in pick(role, moment=mom, level='重', k=k, tick=t):
                    out.add(name)
    return out
