"""**这一轮是从哪一轮分出来的**（存档血统）—— 拾卷树状图的唯一依据。

★★★ 为什么要有它（2026-10-21 用户点名）：
  「节点设计从现在的卡片改成可以展开和缩起来的卡片……整体是**树状图**，
   跟 Windows 资源管理器左侧树状图的那样。**默认节点是根节点，所有从某个节点
   开始的推演都是这个节点的子节点，这些节点之间是兄弟节点**。」

  在此之前，存档之间**没有任何关系记录**：`停点.json` 记的是"这一轮停在哪"，
  不是"这一轮从哪来"。于是拾卷只能把它们排成一条扁平列表 ——
  从同一轮分出去跑了两遍（一次让柳氏先开口、一次让阿九先开口），
  在列表上只是两条看不出关系的邻居，用户没法知道它们是"同一个岔路的两条支线"。

★★★ 三个设计决定（都不是随手选的）：

  ① **一跑就写，不存在就推**（`write_lineage` / `read_lineage`）。
     旧存档没有这个文件 —— 那不代表"它没有来历"，只代表"那时候还没记"。
     ⇒ 读不到时按**根节点**处理（用户原话：「默认节点是根节点」），
       而不是"猜一个父节点"。猜错比不建有树更糟：用户会按错的图去理解自己的存档。

  ② **父节点按"名字"存，不按绝对路径**。
     存档会被整体搬走（换机器、换项目目录、从「已删除备份」还原），
     绝对路径一搬就断，整棵树会散成一片根节点。名字在同一本书里是唯一的
     （`第N次模拟YYYY-MM-DD-HH-MM`），而且搬了也还是它。

  ③ **树是纯函数**（`build_tree`），同层顺序由调用方给。
     "谁是谁的儿子"是数据的事，"同层怎么排"也是数据的事（`tree_order`：按生成时间正序），
     两者都不归界面 —— 混在一起，界面换一个排序档就会把树拆散。
     ⚠ 2026-10-22 之前这句写的是"排序由界面那侧的排序档给"，那是错的（实测两栏一正一反）。

        English:
    **Which round this one branched from** (save lineage) -- the sole basis for the Pick-a-Volume tree.

    ★★★ Why it exists (named by the user 2026-10-21): "change the node design from the current cards to
    expandable/collapsible cards ... the whole thing is a **tree**, like the tree on the left of Windows
    File Explorer. **The default node is a root node; every derivation that starts from some node is a
    child of that node; these nodes are siblings of each other**."

    Before this, saves had **no recorded relationship at all**: `停点.json` says "where this round
    stopped", not "where it came from". So Pick a Volume could only lay them out as one flat list --
    running twice from the same round (once with Liu speaking first, once with Chen) showed up as two
    unrelated neighbours, and the user could not tell they were two branches off the same fork.

    ★★★ Three design decisions (none of them arbitrary):
      ① **Write on start, infer when absent** (`write_lineage` / `read_lineage`). Old saves lack this
         file -- which does not mean "it has no origin", only "we were not recording then".
         => Treat a missing file as a **root node** (the user's words: "the default node is a root
         node"), never guess a parent. A wrong tree is worse than no tree: the user would read their
         own saves by a wrong map.
      ② **Store the parent by name, not absolute path.** Saves get moved wholesale (new machine, new
         project dir, restored from the trash), and an absolute path breaks on the first move,
         shattering the tree into roots. Names are unique within one book
         (`第N次模拟YYYY-MM-DD-HH-MM`) and survive the move.
      ③ **The tree is a pure function** (`build_tree`); the per-level order comes from the caller.
         "Who is whose child" is data, and "how to order a level" is data too (`tree_order`,
         generation time ascending). Neither belongs to the UI -- mixed together, switching one sort
         profile would shatter the tree. ⚠ Before 2026-10-22 this note claimed ordering was the UI's
         job, which was wrong (measured: the two columns ran in opposite directions).
"""
from __future__ import annotations

import json
from pathlib import Path

#: 血统文件名（落在每一轮的运行文件夹里）。
# [EN] Lineage file name (lives in each round's run folder).
FILE_LINEAGE = '来源.json'


def write_lineage(run_dir, *, parent=None, kind: str = 'fresh',
                  note: str = '') -> bool:
    """记下「这一轮从哪来」。**永不抛**（写不进去最坏只是这棵树少一条边）。

    参数
    ----
    run_dir 这一轮的运行文件夹。
    parent  **父存档的名字**（`第1次模拟2026-10-18-02-30`）。`None` = 这是一棵树的根。
    kind    `'fresh'`（从头开）/ `'resume'`（接着上一轮）/ `'next_day'`（上一轮收工了，开新的一天）。
            只用于界面文案，不参与建树。
    note    一句话备注（出问题时看得懂）。

    返回是否写成功。**不抛异常**：起笔是主操作，记血统失败绝不能把起笔顶住。
    
        English:
    Record "where this round came from". **Never raises** (a failed write at worst loses one edge).
    Params: `run_dir` this round's folder; `parent` the **parent save's name**, `None` for a tree root;
    `kind` `'fresh'|'resume'|'next_day'`, used only in UI text, not for building the tree;
    `note` a one-line remark. Returns whether it was written. **Does not raise**: starting a run is the
    primary operation, and failing to record lineage must never block it.
    """
    try:
        d = Path(run_dir)
        d.mkdir(parents=True, exist_ok=True)
        name = str(parent or '').strip() or None
        payload = {'parent': name, 'kind': str(kind or 'fresh'), 'note': str(note or '')}
        (d / FILE_LINEAGE).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return True
    except Exception:                                            # noqa: BLE001
        return False


def read_lineage(run_dir) -> dict:
    """读「这一轮从哪来」。**读不到就给一份"根节点"**（不猜）。

    返回 `{'parent': str|None, 'kind': str, 'note': str}`。
    ⚠ 读不到 / 文件坏了 / 没有这个文件 —— 一律 `parent=None`。
      这不是"容错"，这是**语义**：没有记录 ≠ 有父节点。
    
        English:
    Read "where this round came from". **A missing record yields a root node** (never a guess).
    Returns `{'parent': str|None, 'kind': str, 'note': str}`.
    ⚠ Unreadable / corrupt / absent -- all give `parent=None`. That is not "error tolerance", it is
    **semantics**: no record does not mean "has a parent".
    """
    out = {'parent': None, 'kind': '', 'note': '', 'recorded': False}
    try:
        f = Path(run_dir) / FILE_LINEAGE
        if not f.is_file():
            return out
        data = json.loads(f.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return out
        p = str(data.get('parent') or '').strip()
        out['parent'] = p or None
        out['kind'] = str(data.get('kind') or '')
        out['note'] = str(data.get('note') or '')
        # ★ 这个字段是关键：**"明确是根"与"没有记录"必须分开**。
        #   前者（`kind='fresh'`）是作者真的从头开的；
        #   后者（这个文件不存在）只是"那时候还没记" —— 可以推断，不许当成根。
        # [EN] ★ This field matters: **"explicitly a root" and "no record" must be kept apart**. The
        # [EN] former (`kind='fresh'`) means the author really started fresh; the latter (file absent)
        # [EN] only means "we were not recording then" -- it can be inferred, never treated as a root.
        out['recorded'] = True
    except Exception:                                            # noqa: BLE001
        return {'parent': None, 'kind': '', 'note': '', 'recorded': False}
    return out


_RUN_IDX = __import__('re').compile(r'第(\d+)次模拟')


def run_index(name: str) -> int:
    """存档名里的序号（`第3次模拟2026-…` → 3）。认不出返回 0。

        English:
    The index inside a save name (`第3次模拟2026-...` -> 3). 0 when unrecognized.
    """
    m = _RUN_IDX.search(str(name or ''))
    return int(m.group(1)) if m else 0


#: 存档名里的**生成时间**。优先认紧跟在 `第N次模拟` 后面那一段
#: （`第3次模拟2026-10-03-10-00` → `2026-10-03-10-00`）；
#: 认不出再退回"名字里最后一个 `年-月-日-时-分`"。
#: ⚠ 为什么不能只取**第一个**：回收站目录名前面挂着**删除时刻**的时间戳
#:   （`20261022-103544_存档_第3次模拟2026-10-03-10-00`，这一版是紧凑格式所以不会误认，
#:    但只要哪天前缀改成带横线的写法，取第一个就会拿"删除时间"当"存档时间"，
#:    整棵同级树按删的时刻排 —— 错得毫无痕迹）。取"最后一个"或"紧跟序号那个"都安全。
# [EN] The **generation time** in a save name. Prefer the part right after `第N次模拟`; otherwise
# [EN] fall back to the **last** `Y-M-D-H-M` in the string. ⚠ Never the **first**: bin folder names
# [EN] carry a **deletion** timestamp prefix, and if that prefix were ever written with dashes, taking
# [EN] the first match would treat "deleted at" as "saved at" and sort a level by deletion time --
# [EN] wrong with no visible trace.
_RUN_TIME = __import__('re').compile(
    r'第\d+次模拟\s*(\d{4}-\d{2}-\d{2}-\d{2}-\d{2})')
_RUN_TIME_ANY = __import__('re').compile(r'(\d{4}-\d{2}-\d{2}-\d{2}-\d{2})')

#: 认不出时间的排在哪一段（`0` = 认得，`1` = 认不得）。见 `tree_order`。
_TIME_UNKNOWN = 1


def run_time(name: str):
    """从存档名里抠出**生成时间**，可直接比较；认不出返回 `None`。

    ⚠ 返回 `None` 而不是 `(0, 0, 0, 0, 0)`：后者会让一条**老存档**冒充
      "最早的一轮"排到最前面（正序时），把真正该看的那几轮挤下去。

        English:
    Extract the **generation time** from a save name, directly comparable; `None` when unrecognized.
    ⚠ Returns `None`, not `(0, 0, 0, 0, 0)`: the latter lets a **legacy save** masquerade as "the
    earliest round" and jump to the top (in ascending order), pushing down the runs that matter.
    """
    s = str(name or '')
    m = _RUN_TIME.search(s)
    stamp = m.group(1) if m else ''
    if not stamp:
        found = _RUN_TIME_ANY.findall(s)
        stamp = found[-1] if found else ''
    if not stamp:
        return None
    try:
        return tuple(int(x) for x in stamp.split('-'))
    except (TypeError, ValueError):
        return None


def time_key(name: str) -> tuple:
    """同一层排序用的键：**先按生成时间正序**，时间一样按序号，再按名字。

    ★ 认不出时间的那几条**整段排在最后**（`_TIME_UNKNOWN`），内部再按序号/名字 ——
      它们不是"最早"，也不是"最晚"，是"不知道"，不能混进时间里排。

        English:
    Sort key for one level: **generation time ascending**, then index, then name.
    ★ Entries without a readable time form a separate segment **after** the known ones
      (`_TIME_UNKNOWN`) and are ordered among themselves by index/name -- they are neither earliest
      nor latest, they are unknown, and must not be mixed into the time order.
    """
    t = run_time(name)
    idx = run_index(name)
    if t is None:
        return (_TIME_UNKNOWN, (), idx or 10 ** 9, str(name or ''))
    return (0, t, idx or 10 ** 9, str(name or ''))


def tree_order(names) -> list[str]:
    """**同一层**（所有根之间 / 同一个父节点的子节点之间）的顺序 —— 按生成时间正序。

    ★★★ 为什么要有它（2026-10-22 用户）：「拾卷页面的存档同一级别（即所有根节点以及
      所有从某个节点推演出来的子节点）默认按照从时间顺序排列 回收站也是这样」。
      两栏说的必须是**同一句话**，所以规则只有这**一处** —— 两边都调它，
      就不存在"拾卷一种顺序、回收站另一种顺序"。

    ★★★ 这件事以前是错的，而且错得看不出来（2026-10-22 实测）：
      拾卷把**排序档**（默认 `end_desc`，新的在前）当同层顺序传下去，
      回收站不传、自己按序号**升序**排 —— 于是同一段血统在两栏里一正一反。
      更糟的是回收站那边有个 `_merge_order` 要把被删的按序号**插值**回活着的中间，
      而它假设"活着的顺序是升序"，默认档偏偏给的是**降序**：
        第1次的四个儿子 [2, 3(被删), 4, 5] 在拾卷里排成 **5, 4, 2**（3 还消失了），
        既不是正序也不是倒序。用户看到的就是"同一层没按时间排"。
      ⇒ 现在把"同层顺序"从排序档手里收回来，固定在**时间正序**：
        树是往下长的，时间从上往下流，这才是树该有的读法（资源管理器也是升序）。
      ⚠ 排序档没有废：它仍然决定**打开拾卷时默认选中哪一轮**（`_sorted_runs` 的第一条），
        只是不再左右树的形状 —— "谁是谁的儿子"和"同层怎么排"都归数据层，
        界面再换档也不会把树拆散。

        English:
    The **per-level** order (between all roots / between the children of one parent): generation time
    ascending.
    ★★★ Why it exists (user, 2026-10-22): "saves at the same level in Pick-a-Volume -- all roots and
      all children derived from a node -- should default to time order; same for the recycle bin."
      Both columns must say **the same sentence**, so the rule lives in **one** place and both call it.
    ★★★ This used to be wrong in a way you could not see (measured 2026-10-22): Pick-a-Volume passed
      its **sort profile** (default `end_desc`, newest first) as the per-level order while the bin
      sorted ascending by index, so one lineage read forwards on one tab and backwards on the other.
      Worse, the bin's `_merge_order` interpolated deleted rounds back among the live ones **assuming
      live order was ascending** while the default profile is **descending**: round 1's four children
      `[2, 3(deleted), 4, 5]` came out as **5, 4, 2** (and 3 vanished) -- neither ascending nor
      descending. That is what "same level is not in time order" looked like.
      => The per-level order is taken back from the sort profile and fixed to **time ascending**: a
      tree grows downward and time flows downward, which is how a tree should read (Explorer agrees).
      ⚠ The sort profiles are not dead: they still decide **which round is selected by default** when
      Pick-a-Volume opens (the first item from `_sorted_runs`); they just no longer shape the tree.
    """
    return sorted((str(n) for n in (names or [])), key=time_key)


def parents_of(runs, *, infer_missing: bool = False, key=None) -> dict[str, str | None]:
    """一批存档的父子关系：`{名字: 父名字 | None}`。

    `infer_missing=True` 时，**没有记录**的存档按"序号前一轮"推断父节点。
    `key` 把"路径"翻成**逻辑名**（默认就是 `Path.name`）。

    ★★★ 为什么需要 `key`（2026-10-21，回收站）：
      存档搬进 `已删除备份/` 时，目录名被加上了时间戳与类别前缀 ——
      `第3次模拟2026-10-03-10-00` → `20261021-175403_存档_第3次模拟2026-10-03-10-00`。
      于是 `path.name` 不再是那个**逻辑名**，而 `来源.json` 里记的父名一直是逻辑名。
      不做这层翻译，回收站里的树**必然散成一片根节点**（实测：5 个节点只认出 2 个，
      另外 3 个因为父名对不上而成了孤儿）。

    ★★★ 为什么加参数而不是在回收站那边另写一份（那才是真正的坑）：
      "谁是谁的儿子"只有一处实现（本模块），两处各写一份迟早分叉 ——
      分叉的表现是"拾卷里父子对、回收站里父子错"，而两边都"看起来正常"。
      ⚠ 默认 `None` ⇒ 行为与以前**逐字相同**，拾卷那边一个字都不用改。

    ★★★ 为什么允许推断（2026-10-21，用户："看不到树，条目数量少了些"）：
      `来源.json` 是这一版才加的。他已有的存档**全都没有这个文件**，
      于是每一条都按"根"处理 —— 树是平的，看起来还是原来的列表，
      功能等于没生效。而存量存档恰恰是他最想理清的那一批。

    ★★★ 推断的**依据**（不是我编的）：
      `sim/resume.plan()` 的语义就是"**新的一轮从最近那一轮的停点继续**"
      （它读 `latest_run(proj)`）。所以按序号排，第 N 轮的父几乎必然是第 N-1 轮。
      这与产品自己的行为一致，不是我在猜一个好看的形状。

    ★★★ 但推断**必须标明**（界面会给这些节点加一句"父子关系是推断的"）：
      如果当年是**从更早的存档起笔**（跳过中间那轮），这一条会错。
      用户能一眼看出"这条是推断的"，就知道要不要信。

    ⚠ **按序号算，不按列表顺序算**：列表顺序会被排序档改（开始/结束、正序/倒序），
      拿它推断就等于"换个排序，父子关系跟着变" —— 那是灾难。
    ⚠ 明确记为 `kind='fresh'`（作者亲口说"从头开"）的**不推断**，保持为根。

        English:
    Parent map for a batch of saves: `{name: parent_name | None}`.
    With `infer_missing=True`, saves **without a record** get "the previous round by index" as parent.
    ★★★ Why inference is allowed (2026-10-21, user: "I can't see the tree, and some entries are
      missing"): `来源.json` is new in this version. All of his existing saves **lack that file**, so
      every one was treated as a root -- the tree was flat and looked exactly like the old list, i.e.
      the feature did nothing. And those legacy saves are precisely the ones he wants organized.
    ★★★ The **basis** for the inference (not invented): `sim/resume.plan()` means "**a new round
      continues from the most recent round's stop point**" (it reads `latest_run(proj)`). So ordered by
      index, round N's parent is almost certainly round N-1. This matches the product's own behaviour.
    ★★★ But inference **must be labelled** (the UI adds "this parent link is inferred"): if he once
      started from an **older** save (skipping the middle round), this one is wrong. Seeing that label
      tells him whether to trust it.
    ⚠ **Index order, not list order**: list order changes with the sort profile, and inferring from it
      would mean "change the sort, change the family tree" -- a disaster.
    ⚠ Entries explicitly recorded as `kind='fresh'` are **not** inferred; they stay roots.
    """
    items = [Path(r) for r in (runs or [])]
    nm = key or (lambda p: Path(p).name)
    out: dict[str, str | None] = {}
    explicit: dict[str, bool] = {}
    for r in items:
        try:
            info = read_lineage(r)
        except Exception:                                        # noqa: BLE001
            info = {'parent': None, 'recorded': False, 'kind': ''}
        out[nm(r)] = str(info.get('parent') or '').strip() or None
        # "有记录且明确是 fresh" ⇒ 作者亲口说根，不许推断
        explicit[nm(r)] = bool(info.get('recorded')) and (
            bool(out[nm(r)]) or str(info.get('kind') or '') == 'fresh')
    if not infer_missing:
        return out
    # 按**序号**排（不是列表顺序，理由见 docstring）
    # ⚠ 序号从**逻辑名**里认：回收站目录名前面挂着时间戳，但 `第N次模拟` 仍在里面，
    #   `run_index` 是 search 不是 match，两种名字都认得出。
    # [EN] ⚠ The index is read from the **logical name**: trash folders carry a timestamp prefix,
    # [EN] but `第N次模拟` is still inside, and `run_index` searches rather than matches.
    by_idx = sorted(items, key=lambda p: (run_index(nm(p)) or 10 ** 9, nm(p)))
    prev: str | None = None
    for r in by_idx:
        if out.get(nm(r)):
            prev = nm(r)                     # 已有明确父节点，往后接
            continue
        if explicit.get(nm(r)):
            prev = nm(r)                     # 明确是根：不推断，但它仍是"下一轮的上一轮"
            continue
        if prev is not None:
            out[nm(r)] = prev
        prev = nm(r)
    return out


def build_tree(runs, parents: dict[str, str | None], *,
               key=None) -> list[tuple[Path, int, bool]]:
    """把扁平的存档列表排成**树的前序遍历**：`[(路径, 层级, 有没有子节点)]`。

    `key` 把"路径"翻成**逻辑名**（默认 `Path.name`）—— 与 `parents_of` 的 `key` 必须给同一个，
    否则一边按逻辑名算父、一边按目录名建树，树会散成一片根节点（理由见 `parents_of`）。

    ★ `runs` 的**顺序就是同层的顺序** —— 调用方用 `tree_order()` 排好（按生成时间正序），
      这里只负责"谁挂在谁下面"，不重排。
      ⚠ 2026-10-22 之前这里是"排序档在界面那侧决定"（见模块说明③）。实践证明了那是个坏主意：
        拾卷按"结束时间倒序"传进来、回收站按序号升序自己排 ⇒ 同一段血统两栏一正一反。

    ★ 三条边界（都用判据盯着）：
      ① **父节点不在这批里**（被删了 / 从「已删除备份」只拿回一个子节点）
         ⇒ 这一条自己当根。不许把它从界面上"弄丢"——存档还在磁盘上。
      ② **自己当自己的父**（坏数据 / 手改过 json）⇒ 当根，不许死循环。
      ③ **互相指认成环**（A→B→A）⇒ 环里第一个遇到的那条当根，其余按它的子树展开，
         一个都不丢。宁可层级难看，也不许让存档消失。
      ④ 兜底：走完一遍还有没被访问到的，按根补在最前面 —— 保证
         **返回条的目数 == 输入条数**（少一条就是"存档看不见了"，那是最严重的观感故障）。

    参数
    ----
    runs     已用 `tree_order()` 排好的存档路径（顺序 = 同层顺序）。
    parents  `{名字: 父名字 | None}`（`parents_of()` 给的）。

        English:
    Lay the flat save list out as a **pre-order traversal of the tree**: `[(path, depth, has_children)]`.
    ★ `runs`' **order is the per-level order** -- callers sort it with `tree_order()` (generation time
      ascending); this only decides "who hangs under whom" and never re-sorts.
      ⚠ Before 2026-10-22 this said "sorting belongs to the UI (module note ③)". Practice proved that
      a bad idea: Pick-a-Volume passed "end time descending" while the bin sorted ascending on its
      own, so one lineage read forwards on one tab and backwards on the other.
    ★ Four edges (all covered by criteria): ① parent not in this batch (deleted, or only a child
      restored from the trash) => that item becomes a root; it must never vanish from the UI, the save
      is still on disk. ② self-parent (bad data / hand-edited json) => root, no infinite loop.
      ③ mutual cycle (A->B->A) => the first one met in the cycle becomes the root, the rest expand
      under it, nothing lost; ugly depth beats a missing save. ④ Fallback: anything unvisited after
      the walk is appended as a root, guaranteeing **len(result) == len(input)** -- one missing entry
      means "a save you cannot see", the worst possible failure for this screen.
    """
    ordered = [Path(r) for r in (runs or [])]
    if not ordered:
        return []
    #: 逻辑名（默认就是目录名）。⚠ 只在这一个地方定义，下面全用它，别混着 `p.name` 用。
    # [EN] Logical name (the folder name by default). ⚠ Defined once; everything below uses it --
    # [EN] never mix it with `p.name`.
    nm = key or (lambda p: Path(p).name)
    by_name = {nm(p): p for p in ordered}

    # ── 环：**在这里就把它剪断**，而不是留给末尾那道兜底 ──
    # ★★★ 2026-10-22（用户：「同一级别（所有根节点……）默认按照从时间顺序排列」）：
    #   以前环里的节点两条都不是根、也到不了，于是靠末尾的兜底 `for p in ordered` 补成根 ——
    #   补出来的根**一律排在最后**，于是"根之间按时间正序"这条在坏数据上当场失效
    #   （实测：根排成 第1次 / 第9次 / 第12次 / **第10次**）。用户要的是"凡是同层就按时间"，
    #   而环里的那条也是个根，它凭什么排在 第12次 后面。
    #   ⇒ 现在沿父链走一圈，**回到自己**的那一条把父边剪掉（它就名正言顺当根），
    #     同层顺序自然就是 `ordered` 的顺序；末尾的兜底只作为最后保险（正常情况下一个都补不到）。
    # ⚠ 只剪"回到自己"的那一条（`ordered` 里最早遇到的那个环成员）：一个环剪一刀就够了，
    #   其余成员顺着它往下展开 —— 与原来"环里第一个当根"的语义一致，只是位置对了。
    # [EN] -- Cycles: **cut them here**, not via the fallback at the end --
    # [EN] ★★★ 2026-10-22 (user: "everything at the same level, including all roots, should default
    # [EN] to time order"): a cycle's members were neither roots nor reachable, so the tail fallback
    # [EN] appended them as roots -- and appended roots always land **last**, so "roots are in time
    # [EN] order" failed on bad data (measured: roots came out 1st / 9th / 12th / **10th**). A cycle
    # [EN] member is a root too, so it has no business sorting after the 12th.
    # [EN] => Walk the parent chain; the node that comes back to itself has its parent edge cut (it
    # [EN] legitimately becomes a root), so per-level order is just `ordered` order; the tail fallback
    # [EN] remains only as a last resort (normally it appends nothing).
    # [EN] ⚠ Cut only the one that returns to itself (the earliest cycle member in `ordered`): one cut
    # [EN] per cycle suffices, the rest expand below it -- same semantics as "first in the cycle is the
    # [EN] root", just in the right place.
    def _par(n: str):
        v = (parents or {}).get(n) if parents else None
        return str(v or '').strip() or None

    cut: set[str] = set()
    for p in ordered:
        n = nm(p)
        if n in cut:
            continue
        cur, guard = _par(n), 0
        while cur and cur in by_name and guard <= len(ordered):
            guard += 1
            if cur == n:
                cut.add(n)              # 环回到自己 ⇒ 剪这一刀，它当根
                break
            nxt = _par(cur)
            if nxt == cur:
                break                   # 撞上"自己当自己的父"，那一头自己会当根
            cur = nxt

    children: dict[str, list[Path]] = {}
    roots: list[Path] = []
    seen_names: set[str] = set()
    for p in ordered:
        # 同名的重复项（理论上不该有）只留第一个 —— 否则树里会出现两条一模一样的节点
        if nm(p) in seen_names:
            continue
        seen_names.add(nm(p))
        par = _par(nm(p))
        if par and par == nm(p):
            roots.append(p)                 # ② 自己当自己的父
        elif par and par in by_name and nm(p) not in cut:
            children.setdefault(par, []).append(p)
        else:
            roots.append(p)                 # ① 父不在这批里（或根本没有父）/ ③ 环被剪断的那一条

    out: list[tuple[Path, int, bool]] = []
    visited: set[str] = set()

    def _walk(node: Path, depth: int) -> None:
        if nm(node) in visited:
            return                          # ②③ 防环 / 防重
        visited.add(nm(node))
        kids = children.get(nm(node), [])
        out.append((node, depth, bool(kids)))
        for k in kids:
            _walk(k, depth + 1)

    for r in roots:
        _walk(r, 0)
    # ④ 兜底：环里的那些（既不是根、也没被父节点带到）也要出现
    for p in ordered:
        if nm(p) not in visited:
            _walk(p, 0)
    return out


# ── 树线（2026-10-21 第二批：用户「有办法在不同条目之间拉上线来明确表现树的形状吗」）──
# [EN] -- Tree rails (second round, 2026-10-21: "can we draw lines between the entries to make the
# [EN] tree shape explicit?") --
#: 竖线往下延续（这一列的祖先后面还有兄弟）。
RAIL_DOWN = '│'
#: 分叉：自己还有兄弟，竖线从上面下来、穿过本行继续往下。
RAIL_TEE = '├'
#: 收口：自己是最后一个孩子，竖线到本行为止，向右拐进这一条。
RAIL_ELBOW = '└'
#: 这一层不画（没有线从上面经过）。
RAIL_BLANK = ' '


def tree_guides(tree) -> list[str]:
    """给 `build_tree` 的每一行算**左边那一竖列要画什么**：`['', '│', ' ├', …]`。

    用户原话（2026-10-21）：「拾卷的树状图有办法在不同条目之间拉上线来明确的表现树的形状吗」。
    只靠缩进看不出"这两条是同一个父节点的"（尤其跨屏、尤其分叉多的时候），
    资源管理器就是靠左边这一列 `│ ├ └` 把形状画出来的。

    ★ 返回的字符串**一格一层**，从最外层往里数：
        · 第 0 格对应"深度 1 的祖先"（也就是根的孩子那一列），依次往里；
        · **最后一格**是**自己**的分支记号（`├` / `└`）；
        · 根节点（深度 0）给空串 —— 顶端不画线（资源管理器的根也没有分支号）。
      于是 `len(guide) == 深度`，与缩进一一对应：一格一棵 `SAVE_TREE_INDENT` 的树。

    ★ 三条判据（都用反例法盯着，见 `developers/mutate_pick_volume_tree.py`）：
      ① **自己还有没有兄弟**，看的是"跳过自己整棵子树之后"的那一行，
         **不是下一行** —— 下一行可能是自己的孩子。拿下一行算，所有当爹的都会被画成 `└`
         （"最后一个"），它的孩子那一列就会断掉。
      ② **祖先那一列的竖线要接着往下**（`│`），否则 `└` 画得再对也只是一堆断线：
         用户要的是"形状"，形状由**连续**的那几条竖线给。
      ③ **一个都不断言出错就抛**：这个函数是纯的，遇到坏数据（层级跳跃）按"补空"处理。

    ⚠ 只算**形状**，不碰数据：谁是谁的儿子仍然由 `build_tree` 决定，这里只是把
      已经排好的前序序列翻译成"画线指令"。所以四个排序档下都成立。

        English:
    For each row from `build_tree`, compute **what to draw in the left rail**: `['', '│', ' ├', ...]`.
    User's words (2026-10-21): "can we draw lines between the entries to make the tree shape explicit?"
    Indentation alone cannot show "these two share a parent" (especially across a scroll, or with many
    forks); Explorer draws the shape with that `│ ├ └` column.
    ★ One cell per level, from the outside in: cell 0 is the "depth-1 ancestor" column (the root's
      children), and the **last cell is the node's own branch mark** (`├`/`└`). A root (depth 0) gets
      an empty string -- nothing is drawn at the top level (Explorer's root has no branch either).
      Hence `len(guide) == depth`, matching the indentation: one `SAVE_TREE_INDENT` per cell.
    ★ Three criteria (all guarded by the counterexample method):
      ① Whether the node **has a following sibling** is decided by the row **after its whole
         subtree**, **not the next row** -- the next row may be its own child. Using the next row
         makes every parent a `└` ("last"), which snaps the children's column.
      ② **The ancestor columns must keep going down** (`│`), otherwise perfect `└`s are still a pile
         of disconnected dashes: the user asked for a *shape*, and the shape is carried by those
         **continuous** verticals.
      ③ Pure function, never raises: bad data (depth jumps) is padded with blanks instead.
    ⚠ Shape only, never data: who is whose child is still `build_tree`'s business; this just
      translates an already-ordered pre-order sequence into drawing instructions. Works under all four
      sort profiles.
    """
    rows: list[tuple[Path, int]] = []
    for item in (tree or []):
        p, d = item[0], item[1]
        rows.append((Path(p), max(0, int(d))))
    n = len(rows)
    if not n:
        return []
    out: list[str] = []
    #: `open_[k]` = 深度 k 的那一层祖先"后面还有兄弟"⇒ 它那一列的竖线要往下延续。
    #: [EN] `open_[k]` = the ancestor at depth k still has a sibling afterwards => its column continues.
    open_: list[bool] = []
    for i, (_p, d) in enumerate(rows):
        # ★ 判断"还有没有兄弟"要**跳过自己的整棵子树**（判据①）。
        # [EN] ★ "Has a following sibling" must **skip this node's whole subtree** (criterion ①).
        j = i + 1
        while j < n and rows[j][1] > d:
            j += 1
        more = (j < n and rows[j][1] == d)
        del open_[d:]                       # 更深的层已经走出去了
        while len(open_) < d:
            open_.append(False)             # 坏数据（层级跳跃）⇒ 补空，不抛
        if d == 0:
            out.append('')                  # 顶层不画线
        else:
            cells = ''.join(RAIL_DOWN if open_[k] else RAIL_BLANK
                            for k in range(1, d))
            out.append(cells + (RAIL_TEE if more else RAIL_ELBOW))
        if len(open_) > d:
            open_[d] = more
        else:
            open_.append(more)
        # 顶层（depth 0）的"还有兄弟"不画：根与根之间不连线（与 `out.append('')` 一致）。
        if d == 0:
            open_[0] = False
    return out


def depth_of(run_dir, parents: dict[str, str | None]) -> int:
    """这一条在树里第几层（0 = 根）。用来给界面算缩进。

    ⚠ 只用于**缩进**，不用于建树 —— 所以防环只要"走满页数就停"，不需要严谨。
    [EN] Which level this entry sits at (0 = root), for indentation only. Since it is only used for
    indentation, cycle protection just needs a bound, not precision.
    """
    name = Path(run_dir).name
    depth = 0
    cur = name
    guard = 0
    while guard < 64:
        guard += 1
        par = str((parents or {}).get(cur) or '').strip()
        if not par or par == cur or par not in (parents or {}):
            break
        depth += 1
        cur = par
    return depth
