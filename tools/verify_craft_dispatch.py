# -*- coding: utf-8 -*-
"""判据：**手艺调度（71+10 条全部落地、动态映射、按品级调条数）**（2026-10-18）。

来历
----
用户：「71 条手艺也全部落地 且根据需要动态映射……四个缺口也修复 总表里的
不存在的手艺库内容全部补全 都进入提示词 都有判定依据 都进行判定
都在合理的实际动态的映射到不同类型且在合适的时候进行调用」，
以及「很多Agent的提示词请动态拼接 而不是固定的 根据需要由特定Agent负责品级」。

改造前实测的硬数据：**81 条里 24 条从来没到过任何人的提示词**
（`crew/agents._craft_for` 第 ③ 步按 yaml 文件顺序补满，永远是同一批前几条），
而且"这一拍是开场还是收束"对读什么**毫无影响**。

这一支守六件事（每条都配反例法，`developers/mutate_craft_dispatch.py`）：

| 组 | 守什么 |
|---|---|
| A | **81 条全部可达**（任何一个职位、任何一个时机、任何一拍，合起来覆盖全库） |
| B | **动态**：时机/类型/拍数真的改变读到的条目（不是"换了个说法还是同一批"） |
| C | **品级真的改变条数**（重 > 中 > 轻），且三档都会出现（否则等于一档） |
| D | **限流还在**（单条 ≤80 token、单次 ≤ k 条；不许"全喂"） |
| E | **真的进了提示词**（真跑 `decide()` 抓 prompt，不是"函数能返回"） |
| F | **库本身合格**：81 条都有可执行提示词；三条缺口条目在里面 |

⚠ 本支**不判"手艺写得好不好"**：那是主观的。判的是"到不到得了、会不会变、
  有没有限流、进没进提示词"。

跑法：`.venv/Scripts/python.exe tools/verify_craft_dispatch.py`
"""
from __future__ import annotations

import ast
import asyncio
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail='') -> bool:
    CHECKS.append((name, bool(cond), str(detail)))
    print(f'  {"✓" if cond else "✗"} {name}'
          + (f'   [{detail}]' if detail else ''), flush=True)
    return bool(cond)


def _read(rel: str) -> str:
    try:
        return (APP / rel).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def _reachable_call(src_file: str, func_name: str, needle: str) -> bool:
    """`src_file` 里 `func_name` 这个函数**真的会执行到**含 `needle` 的那句吗？

    ⚠ `'needle' in ast.unparse(fn)` 是不够的 —— `if False: x = f()` 里的调用
      照样在 AST 里、`unparse` 也照样输出它。这一条在本项目栽过不止一次
      （"AST 有赋值 ≠ 执行得到"），所以这里**走一遍函数体、跳过恒假分支**。
    ⚠ 不执行函数本身：`_review_gate` 要 loop 实例、`_maybe_break_scene` 要 builder，
      真起一个 RunLoop 是另一码事（要 db、要窗口、要模型）。
    [EN] Does `func_name` in `src_file` **really execute** the statement containing `needle`?
    [EN] ⚠ `'needle' in ast.unparse(fn)` is not enough -- a call inside `if False:` is still in the
    [EN] AST and still printed by `unparse`. This project has been bitten by "assignment exists in the
    [EN] AST != it executes", so walk the body and **skip always-false branches**.
    [EN] ⚠ The function is not executed: `_review_gate` needs a loop instance, `_maybe_break_scene`
    [EN] needs a builder; standing up a RunLoop needs db, window and a model.
    """
    tree = ast.parse(_read(src_file))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == func_name), None)
    if fn is None:
        return False

    def _is_false(test) -> bool:
        """这个条件是不是**恒假**（所以它的分支永远不执行）。

        ⚠ 只认 `Constant(False/0/None/'')` 是不够的：`if False and k == 'x':`
          同样恒假（`and` 短路），而反例法 M19 最初就写成这一种。
        [EN] Is this condition **always false** (so its branch never runs)?
        [EN] ⚠ Recognising only `Constant(False/0/None/'')` is not enough: `if False and k == 'x':`
        [EN] is equally always false (`and` short-circuits).
        """
        if isinstance(test, ast.Constant) and test.value in (False, 0, None, ''):
            return True
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
            return _is_false(test.values[0])
        return False

    def _scan(node) -> bool:
        """递归找**真的会执行到**的调用。

        ★★★ 遍历的是 **Call 节点**，不是语句 —— 这一条是从两轮"假绿"里换来的：
          ① 第一版按**语句**判 `needle in ast.unparse(st)`，而 `ast.If` 的
             unparse **把整个 body 都带上了** ⇒ 恒假分支里的调用还没被剪掉就先命中了；
          ② 第二版按语句递归 + 剪枝，仍然在 `for/while/try` 的头部漏判。
          改成"遍历 Call、遇到恒假 If 就把整棵子树剪掉"之后，两种情况都对。
        ⚠ 只剪 `if` 的恒假分支；`while False:` 之类不剪（没人那么写，
          而误剪会漏掉真调用）。
        [EN] Walk **Call nodes**, not statements. This came from two rounds of false green:
        [EN] ① judging `needle in ast.unparse(st)` on a **statement** where `ast.If`'s unparse
        [EN] **includes the whole body**, so a call in a dead branch matched before pruning;
        [EN] ② recursing per statement still missed `for/while/try` heads.
        [EN] Walking Calls and pruning whole always-false `if` subtrees fixes both.
        """
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.If) and _is_false(child.test):
                continue                      # 恒假分支：整棵剪掉（含 body 与 orelse）
            if isinstance(child, ast.Call) and needle in ast.unparse(child):
                return True
            if _scan(child):
                return True
        return False

    return _scan(fn)


#: 期望的条目总数 —— **绝对数**，不许拿 `len(load()['entries'])` 当期望
#: （那样"删掉十条"也能绿，正好把这次要守的东西绕过去）。
#: 71 条原有 + **11 条** 2026-10-18 补的叙事学正典 = 82。
#: ⚠ 11 而不是 10：第一版检查表 #22 写了「限知条目」，而库里**根本没有**任何
#:   「限知 / 视角」条目 —— 那是我自己造的假账，补上 `限知与感知边界` 之后才对得上。
#:   教训：**在表里写「已有」之前先 grep 一遍库**。
# [EN] 71 original + **11** added on 2026-10-18 = 82.
# [EN] ⚠ 11, not 10: the first checklist wrote "the limited-knowledge entry" for #22 while the
# [EN] library had **no** such entry at all -- a fake line I wrote myself. Lesson: **grep the library
# [EN] before writing "we have it" in the table**.
_N_ENTRIES = 82

#: 2026-10-18 补进库的十条（对应检查表「手艺库」列标 ❌ / 只有一半的那几条）。
# [EN] The ten entries added on 2026-10-18 (checklist rows whose "craft library" cell was ❌ or half).
_NEW_ENTRIES = ('反应与决定', '欲望与需求', '自由间接引语', '悬念与惊奇', '闲笔不是废话',
                '母题回响', '邻接对', '场与场的缝', '意象不复用', '时代与地点错置',
                '限知与感知边界')


# ══════════════════════════════════════════════════════════
#  A  81 条全部可达
# ══════════════════════════════════════════════════════════
def group_a() -> None:
    from craft import craftmix as CM
    from craft import dispatch as DISP

    entries = CM.load()['entries']
    ok(f'A1 ★★★ 手艺库现在是 {_N_ENTRIES} 条（11 条缺口今天补进库）',
       len(entries) == _N_ENTRIES, str(len(entries)))

    got = DISP.reachable(k=4, ticks=80)
    missing = sorted(set(entries) - got)
    ok('A2 ★★★ **每一条都够得到**（改造前 24 条从未进过任何提示词）',
       not missing, f'够不到 {len(missing)} 条：{missing[:8]}')
    # ⚠ **成对**：不是"把池子放大到全库"那种一刀切 —— 每个职位**只读自己的货架**。
    #   若为了全覆盖而让所有职位读全库，`actor` 就会读到"黄金三章"（想替编剧干活）。
    from crew.agents import SHELVES
    actor_shelves = set(SHELVES.get('actor', ()))
    ok('A3 ★★★ 成对：**职位只读自己的货架**（覆盖不是靠"全员读全库"做到的）',
       actor_shelves == {'人物与对话', '叙事学正典'},
       str(sorted(actor_shelves)))

    # 演员只点名两条叙事学条目 —— 给它整架它会去排结构
    from crew.agents import READS
    nar = {n for n, e in entries.items() if str(e.get('_货架')) == '叙事学正典'}
    actor_named = {x for x in READS.get('actor', ()) if x in nar}
    ok('A4 ★★★ 成对：演员从叙事学那一架只拿**两条**（邻接对/场与场的缝）',
       actor_named == {'邻接对', '场与场的缝'}, str(sorted(actor_named)))
    # 而它不是永远只能读到这两条以外的东西 —— 那两条必须真的给到它
    actor_pool = {n for n, _e in DISP.pool('actor')}
    ok('A5 ★★ 这两条**确实在演员的池子里**（不是点名了却没接进去）',
       {'邻接对', '场与场的缝'} <= actor_pool, str(sorted(actor_pool & nar)))


# ══════════════════════════════════════════════════════════
#  B  动态：时机 / 类型 / 拍数真的改变内容
# ══════════════════════════════════════════════════════════
def group_b() -> None:
    from craft import dispatch as DISP

    def names(mom, *, genre='悬疑灵异', tick=3, role='novelist'):
        return [n for n, _t, _lv in DISP.pick(role, genre=genre, moment=mom,
                                             level='重', k=6, tick=tick)]

    base = names('日常')
    ok('B1 ★★★ 手艺库读得出东西（否则下面几条都是"没数据 ⇒ 绿"）',
       len(base) > 0, str(base[:3]))

    # ① 时机
    diffs = 0
    for mom in ('开场', '冲突', '转折', '收束', '查稿', '成稿'):
        if names(mom) != base:
            diffs += 1
    ok('B2 ★★★ **时机真的改变读什么**（六个时机里至少五个与日常不同）',
       diffs >= 5, f'{diffs}/6 个不同')

    # ② 开场读的是"开篇"那类，收束读的是"收"那类 —— 按内容判，不按"名单不同"
    open_j = ' '.join(names('开场', tick=1))
    end_j = ' '.join(names('收束', tick=1))
    ok('B3 ★★★ 开场那一拍读到的是**开篇类**手艺（三幕/黄金三章/铺垫/催化之一）',
       any(k in open_j for k in ('三幕结构', '黄金三章', '铺垫', '催化', '登场')),
       open_j[:60])
    ok('B4 ★★★ 收束那一拍读到的是**收尾类**手艺（章回钩子/终场/收束/情节点之一）',
       any(k in end_j for k in ('章回钩子', '终场', '收束', '情节点', '起承转合')),
       end_j[:60])

    # ③ 类型
    ok('B5 ★★★ **类型真的改变读什么**（换一本类型，读到的不是同一批）',
       names('日常', genre='言情', tick=3) != names('日常', genre='科幻', tick=3),
       '')

    # ④ 拍数（环形轮换）
    t0 = names('日常', tick=0)
    t3 = names('日常', tick=3)
    ok('B6 ★★★ **拍数往前走，读到的会换**（老实现永远取前 N 条）',
       t0 != t3, f'{t0[:2]} vs {t3[:2]}')

    # ⑤ 可复现 —— 用 `hash()` 的话**跨进程**会飘，同进程内看不出来。
    # ⚠ 第一版只在同进程里调两次 ⇒ 用 `hash()` 也绿（PYTHONHASHSEED 在同一进程内固定）。
    #   反例法 M07 当场抓出这一点 ⇒ 改成**起两个子进程**各算一遍再比。
    # [EN] Reproducibility: with `hash()` it drifts **across processes**, invisible inside one.
    # [EN] The first version called it twice in-process, so `hash()` stayed green (PYTHONHASHSEED is
    # [EN] fixed within a process). M07 caught it => run **two separate processes** and compare.
    ok('B7 ★★★ 同一个 tick **跨进程可复现**（不许用 `hash()`，它带 PYTHONHASHSEED 随机化）',
       _ring_sig() == _ring_sig(), '')


def _ring_sig() -> str:
    """起一个干净子进程，返回"某几个 tick 读到哪些条目"的指纹。"""
    import subprocess
    code = (
        'import sys; sys.path.insert(0, %r)\n'
        'from craft import dispatch as D\n'
        'print("|".join(",".join(n for n, _t, _l in D.pick("novelist", genre="悬疑灵异",'
        ' moment="日常", level="重", k=5, tick=t)) for t in (0, 5, 11)))\n'
    ) % str(APP)
    try:
        r = subprocess.run([sys.executable, '-c', code], cwd=str(APP), capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=180)
        return (r.stdout or '').strip() or f'(exit {r.returncode})'
    except Exception as e:                                       # noqa: BLE001
        return f'({e!r})'


# ══════════════════════════════════════════════════════════
#  C  品级：三档都出现、都改变条数
# ══════════════════════════════════════════════════════════
def group_c() -> None:
    from craft import dispatch as DISP
    from director import supervisor as SUP
    from world.state import WorldState

    counts = {lv: len(DISP.pick('novelist', genre='悬疑灵异', moment='日常',
                               level=lv, k=8, tick=2))
              for lv in DISP.LEVELS}
    ok('C1 ★★★ **品级真的改变条数**（重 > 中 > 轻；否则三个品级就是一个）',
       counts['重'] > counts['中'] > counts['轻'] > 0, str(counts))
    ok('C2 ★★ 轻品级**至少还读一条**（读空等于这一拍没有手艺）',
       counts['轻'] >= 1, str(counts['轻']))

    # 三档都必须**真的会出现** —— 否则 `轻` 永远不会被选中，等于只有两档
    seen = set()
    cases = {
        '默认日常': WorldState(),
        '张力中': _w(tension=0.4),
        '张力高': _w(tension=0.7),
        '各说各话': _w(topic_run=4),
        '上一场有决定': _w(aftermath={'决定': '明天就走'}),
    }
    for _k, w in cases.items():
        seen.add(SUP.grade_beat(w)[1])
    for kw in ({'is_new_scene': True}, {'beats_left_today': 1},
               {'reviewing': True}, {'finishing': True}):
        seen.add(SUP.grade_beat(WorldState(), **kw)[1])
    ok('C3 ★★★ **三个品级都会真的出现**（`轻` 永不出现 = 这一档形同虚设）',
       seen == set(DISP.LEVELS), str(sorted(seen)))

    # 时机也要三档分布合理：开场/收束/冲突都该是"重"
    # ⚠ 第一版把六个时机塞进一个 dict-comprehension，只给"冲突/转折"之外的四个传了
    #   触发条件 ⇒ `冲突`/`转折` 拿到的是默认世界（张力 0.3、没有余波），
    #   判成"日常/轻" ⇒ **假红**。这一条改判据不改产品：**每个时机单独造夹具**，
    #   因为"怎么让它变成冲突"本来就不同（张力 / 各说各话 / 有余波）。
    # [EN] The first version pushed all six moments through one dict-comprehension and only gave
    # [EN] triggers to four of them, so 冲突/转折 got the default world (tension 0.3, no aftermath)
    # [EN] and graded as 日常/轻 => **false red**. Fixed on the criterion side: build a separate
    # [EN] fixture per moment, since the way to make it a conflict differs.
    _fixtures = {
        '开场': (dict(is_new_scene=True), {}),
        '冲突': (dict(), {'tension': 0.7}),
        '转折': (dict(), {'aftermath': {'决定': '明天就走'}}),
        '收束': (dict(beats_left_today=1), {}),
        '查稿': (dict(reviewing=True), {}),
        '成稿': (dict(finishing=True), {}),
    }
    heavy_moments = [m for m, (kw, wkw) in _fixtures.items()
                     if SUP.grade_beat(_w(**wkw), **kw) == (m, '重')]
    ok('C4 ★★ 六个"该读满"的时机**各自判成自己的时机且都是 `重`**（少一个就是漏档）',
       len(heavy_moments) == 6, str(heavy_moments))

    # 导演是唯一的判定处（不是各职位自己判）
    ok('C5 ★★★ 品级判定**只有一处实现**（`director/supervisor.grade_beat`），'
       '`sim/loop` 只是调用它',
       'SUP.grade_beat(' in _read('sim/loop.py')
       and 'grade_beat' in _read('director/supervisor.py'), '')

    # ★★★ 品级必须**真的用到生产路径上**（不是"算了但没人读"）。
    # ⚠ 第一版只测 `DISP.pick(level=...)`（直接传参），于是
    #   "`_craft_for` 把 level 写死成 '中'"这个变异**照绿**（反例法 M10 抓出来的）。
    #   ⇒ 真跑 `craft_block`，把 `world.craft_level` 换一档看条数。
    # [EN] The grade must **really be used on the production path** (not "computed but unread").
    # [EN] The first version only tested `DISP.pick(level=...)` (passed directly), so hardcoding
    # [EN] '中' inside `_craft_for` stayed green (caught by M10). => run `craft_block` for real and
    # [EN] flip `world.craft_level`.
    n_heavy = len(_block_lines('重'))
    n_light = len(_block_lines('轻'))
    ok('C6 ★★★ 品级**真的用在生产路径上**：`craft_block` 在"重"与"轻"下给出的条数不同'
       '（写死一个档 = 品级是摆设）',
       n_heavy > n_light > 0, f'重 {n_heavy} 条 / 轻 {n_light} 条')
    # ★★★ **拍数**同样要在生产路径上生效。
    #   ⚠ 这一条是补一个真 bug 来的：`_craft_for` 里写的是
    #     `getattr(_w, 'beat_tick', 0)` —— 而 `WorldState` **根本没有这个字段**，
    #     于是恒 0 ⇒ 每拍挑到的完全是同一批，**环形轮换在生产路径上从没生效过**；
    #     而 B6 直接给 `pick(tick=...)` 传参，一直是绿的。
    #   ⇒ 判据必须走 `craft_block`（生产路径），并且**成对**验证"字段确实存在"。
    # [EN] ★★★ **Beat number** must also take effect on the production path. ⚠ This check came from
    # [EN] a real bug: `_craft_for` read `getattr(_w, 'beat_tick', 0)` while `WorldState` **had no such
    # [EN] field**, so it was always 0 => every beat picked the same batch and **ring rotation never
    # [EN] worked on the production path**, while B6 (passing `tick` directly to `pick`) stayed green.
    # [EN] => must go through `craft_block`, and **pair** it with "the field really exists".
    _b0 = _block_lines('重', tick=0)
    _b7 = _block_lines('重', tick=7)
    ok('C7 ★★★ 拍数**真的用在生产路径上**：`craft_block` 在第 0 拍与第 7 拍给出的条目不同'
       '（不同 ⇒ 轮换生效；相同 ⇒ 每拍读同一批，等于没有轮换）',
       _b0 != _b7, f'第0拍：{_b0[:3]} / 第7拍：{_b7[:3]}')
    from world.state import WorldState as _WS2
    ok('C7b ★★★ 成对：`WorldState` 上**真的有** `beat_tick` 字段'
       '（`getattr(…, 0)` 读一个不存在的字段，永远不会报错）',
       hasattr(_WS2(), 'beat_tick'), '')


def _block_lines(level: str, *, tick: int = 0) -> list[str]:
    """真跑 `craft_block`（不是 `pick`），返回它给出的条目名列表。

    ⚠ 必须走 `bind_world` —— `craft_block` 是从**世界上挂着的对象**读
      `craft_level` / `beat_tick` 的（不往 14 个调用点加参数）。不绑定 world 时
      它拿默认值，那这条判据就成了"测自己的默认值"。
    [EN] ⚠ Must go through `bind_world` -- `craft_block` reads `craft_level` / `beat_tick` **off the
    [EN] world** (no params at 14 call sites). Unbound, it uses defaults and this check would be
    [EN] testing its own defaults.
    """
    from crew import agents as A
    from world.state import WorldState

    w = WorldState()
    w.craft_level = level
    w.beat_moment = '冲突'          # 固定时机，只让品级 / 拍数变
    w.beat_tick = int(tick)
    A.bind_world(w)
    try:
        txt = A.craft_block('novelist', '悬疑灵异', '')
    finally:
        A._reset_world()
    return [ln[1:ln.index('〕')] for ln in txt.splitlines() if ln.startswith('〔')]


def _w(**kw):
    from world.state import WorldState
    w = WorldState()
    for k, v in kw.items():
        setattr(w, k, v)
    return w


# ══════════════════════════════════════════════════════════
#  D  限流还在
# ══════════════════════════════════════════════════════════
def group_d() -> None:
    from craft import dispatch as DISP
    from craft import craftmix as CM
    from llm.tokens import estimate_tokens

    rows = DISP.pick('novelist', genre='悬疑灵异', moment='冲突', level='重', k=8, tick=0)
    ok('D1 ★★★ 单条**不超过 80 token**（`MAX_ENTRY_TOKENS`；全喂是另一个坑）',
       all(estimate_tokens(t) <= CM.MAX_ENTRY_TOKENS for _n, t, _lv in rows),
       str([estimate_tokens(t) for _n, t, _lv in rows]))
    ok('D2 ★★★ 单次**不超过 k 条**（想多读就传更大的 k，别偷偷放宽）',
       len(DISP.pick('novelist', genre='悬疑灵异', moment='冲突', level='重', k=3, tick=0)) <= 3,
       str(len(rows)))
    ok('D3 ★★ k=0 ⇒ 一条都不给（调用方明确说不要时不许硬塞）',
       DISP.pick('novelist', moment='日常', level='重', k=0, tick=0) == [], '')


# ══════════════════════════════════════════════════════════
#  E  真的进了提示词（真跑 decide 抓 prompt）
# ══════════════════════════════════════════════════════════
class _FakeDB:
    def retrieve_memory(self, *a, **k):
        return []

    def add_memory(self, *a, **k):
        pass

    def count_memories(self, *a, **k):
        return 0

    def get_summaries(self, *a, **k):
        return []

    def recent_events(self, *a, **k):
        return []


def _capture(*, me: str = '主角', **world_kw) -> str:
    from agent import core as AC
    from agent.core import Agent
    from world.state import GameTime, PersonState, WorldState

    w = WorldState()
    w.scene = '临河茶肆'
    w.clock = GameTime()
    w.people[me] = PersonState(name=me, identity='茶肆掌柜', location='临河茶肆',
                               goal='把这个月盘出去',
                               need='想被人当成一个人看')
    w.people['伙计'] = PersonState(name='伙计', identity='跑堂', location='临河茶肆',
                                   # ⚠ 这个**别人的需求**是给 E5 用的：没有它，
                                   #   "把别人的需求写进自己提示词"那个变异就抓不到
                                   #   （夹具里没有别的东西可串 ⇒ 恒绿）。
                                   # [EN] This **other person's need** exists for E5: without it the
                                   # [EN] "leak someone else's need" mutation cannot be caught.
                                   need='不想再被人呼来喝去')
    for k, v in world_kw.items():
        setattr(w, k, v)
    a = Agent(w.people[me], _FakeDB(), w)
    seen: dict = {}
    real = AC.llm.chat

    async def fake_chat(tier, messages, **kw):
        seen['prompt'] = messages[-1]['content'] if messages else ''
        return (json.dumps({'动作': 'wait', '参数': {'目标': ''}, '台词': '',
                            '内心': '', '理由': '测试'}, ensure_ascii=False), {})

    AC.llm.chat = fake_chat
    try:
        asyncio.run(a.decide())
    finally:
        AC.llm.chat = real
    return str(seen.get('prompt') or '')


def group_e() -> None:
    from director import supervisor as SUP
    from world.state import PersonState, WorldState, WorldState as _WS
    p = _capture()
    ok('E1 ★★★ 真跑 `decide()` 抓到了 prompt', len(p) > 500, f'{len(p)} 字')
    # ── #4 欲望 vs 需求 ──
    ok('E2 ★★★ 提示词里有 `[你嘴上要的 / 你真正缺的]`（#4 的落点）',
       '[你嘴上要的 / 你真正缺的]' in p, '')
    ok('E3 ★★★ 而且**写明了不许说出口**（否则等于告诉它去点题）',
       '不许说出口' in p and '不许有人替你说破' in p, '')
    ok('E4 ★★★ 成对：**设定的「需求」原文不许出现在别人那一侧**'
       '（给本人是让他"知道"，不是让所有人都知道）',
       '想被人当成一个人看' in p, '')     # 本人的提示词里当然有
    p_other = _capture(me='伙计')
    ok('E5 ★★★ 成对：**别人**的提示词里没有他的需求（只给本人）',
       '想被人当成一个人看' not in p_other, '')
    # ★ 反方向也守一遍：**甲的提示词里不许有乙的需求**。
    #   上面那条只测"乙看不到甲的"，漏掉"甲看到乙的"（反例法 M14 就是从这个缺口进去的）。
    # [EN] Also the other direction: **A's prompt must not contain B's need**. The check above only
    # [EN] covers "B cannot see A's", missing "A sees B's" (which is exactly the hole M14 used).
    ok('E5b ★★★ 成对：**别人**的需求也不许出现在我的提示词里',
       '不想再被人呼来喝去' not in p, '')
    # ── #10 心理距离 ──
    p_far = _capture(narrative_distance='拉远')
    ok('E6 ★★★ 心理距离 `拉远` 时提示词里有那一档的写法（#10 的落点）',
       '[这一拍的距离：拉远]' in p_far, '')
    p_close = _capture(narrative_distance='贴近')
    ok('E7 ★★★ 成对：换一档 ⇒ 提示词真的变了（不是写死一段话）',
       '[这一拍的距离：贴近]' in p_close and p_close != p_far, '')
    ok('E8 ★★ 成对：**不设档**时一个字都不挂（老存档行为逐字退回）',
       '[这一拍的距离' not in p, '')
    # ★★★ `distance_for` 本身的行为 —— 上面几条测的都是"给了档 ⇒ 提示词变"，
    #   而"档怎么来的"没人守（反例法 M16 打的就是这里）。
    #   三件事：冲突贴、收束拉、**不许连着两拍都贴**。
    # [EN] The behaviour of `distance_for` itself: the checks above only prove "given a grade, the
    # [EN] prompt changes"; nothing guarded **how the grade is chosen** (M16 targets exactly that).
    ok('E8b ★★★ 距离由时机决定：冲突/转折=贴近、收束=拉远、其余=中间',
       (SUP.distance_for('冲突') == '贴近' and SUP.distance_for('转折') == '贴近'
        and SUP.distance_for('收束') == '拉远' and SUP.distance_for('日常') == '中间'), '')
    ok('E8c ★★★ 成对：**不许连着两拍都贴着**（贴三拍就是满篇心声）',
       SUP.distance_for('冲突', prev='贴近') == '中间', '')
    # ── #7 sequel 余波 ──
    p_aft = _capture(aftermath={'反应': '他把账本合上了', '困境': '伙计那句话还没答', '决定': ''})
    ok('E9 ★★★ 余波真的进了提示词（#7 scene→sequel 的落点）',
       '[上一场留下的]' in p_aft and '他把账本合上了' in p_aft, '')
    ok('E10 ★★★ 而且明写"**没有就別替他决定**"（不编一个决定塞给他）',
       '别替他决定' in p_aft, '')
    ok('E11 ★★ 成对：**没有余波**时这一段一个字都不挂（不啰嗦）',
       '[上一场留下的]' not in p, '')
    # ★★★ 余波**怎么来的**也要守：换场时真的会记（`_note_aftermath`），不然
    #   上面那条只证明"设了字段就能进提示词"—— 而没人设字段。
    #   ⚠ 判法见 `_reachable_call`：走过函数体、**跳过恒假分支**。
    # [EN] Also guard **how the aftermath arrives**: the scene change must really record it,
    # [EN] otherwise the check above only proves "set the field and it reaches the prompt" while
    # [EN] nobody sets it. ⚠ See `_reachable_call`: walk the body, **skip always-false branches**.
    ok('E12 ★★★ 换场时**真的会**记余波（不是写在 `if False` 底下）',
       _reachable_call('sim/loop.py', '_maybe_break_scene', '_note_aftermath'), '')
    # ★★★ **余波取得到"反应"吗**（2026-10-18 晚实修的 bug）。
    #   换场的真实顺序是：`_apply_stage_move` 先 `clear_lines()`（清 `recent_lines`）
    #   → 然后 `_maybe_break_scene` 分幕 → 那时才轮到 `_note_aftermath`。
    #   于是"从 recent_lines 里倒着找最后一句"**永远找不到** ⇒ 余波只剩"困境"。
    #   ⇒ 判据必须**模拟清空之后**再算，否则又是在"有数据 ⇒ 看得见 ⇒ 绿"里自欺。
    # [EN] ★★★ Can the aftermath actually get the "reaction"? (a bug fixed 2026-10-18 evening.)
    # [EN] The real order is: `_apply_stage_move` calls `clear_lines()` first, then
    # [EN] `_maybe_break_scene` splits the scene, and only then does `_note_aftermath` run -- so
    # [EN] "scan recent_lines backwards" **never finds anything** and the aftermath had only the
    # [EN] dilemma. => the criterion must compute **after clearing**, otherwise it is again
    # [EN] "data exists => visible => green".
    _wa = WorldState()
    _wa.recent_lines = [{'who': '甲', 'text': '他把账本合上了，没说话', 'kind': 'act',
                         'place': '茶肆'}]
    _wa.topic = '这账什么时候能清'
    _wa.topic_open_with = '乙'
    _wa.clear_lines()          # ← 换场时真会走这一步
    ok('E12b ★★★ 清空 `recent_lines` 之后，余波仍拿得到"反应"'
       '（`last_beat_text` 兜底；没有它余波永远只剩"困境"）',
       bool(str(getattr(_wa, 'last_beat_text', '') or '').strip()),
       repr(str(getattr(_wa, 'last_beat_text', ''))[:30]))
    ok('E12c ★★★ 成对：`clear_lines` 之前 `last_beat_text` 是空的'
       '（否则它就是上一次换场留下的旧话，会张冠李戴）',
       WorldState().last_beat_text == '', '')
    # ★ 另一半：**有人读它**（只记不读 = 白记，正是"字段有、没人用"）。
    #   ⚠ E12b 只证明"记下来了"，证明不了"用上了" —— 反例法 M25 就从这里漏过去。
    # [EN] The other half: **somebody reads it** (recording without reading is useless -- exactly the
    # [EN] "field exists, nobody uses it" pattern). ⚠ E12b only proves "it was recorded", not "it is
    # [EN] used" -- that is the hole M25 slipped through.
    ok('E12d ★★★ `_note_aftermath` **真的读** `last_beat_text`（只记不读 = 白记）',
       _reachable_call('sim/loop.py', '_note_aftermath', 'last_beat_text'), '')
    # ── #4 说破需求的两条兜底 ──
    from crew import review as RV
    from world.state import PersonState, WorldState as _WS
    _w3 = _WS()
    _w3.people['甲'] = PersonState(name='甲', need='想被人当成一个人看')
    ok('E13 ★★★ 上屏闸**判得出"说破需求"**（说破了 ⇒ 报；无关的话 ⇒ 不报）',
       bool(RV.need_check('我不过是想被人当成一个人看', _w3, '甲'))
       and RV.need_check('外头下雪了，把门关上', _w3, '甲') == '', '')
    # ⚠ 第一版判 `'need_check' in ast.unparse(_gate)` —— `if False:` 下的调用
    #   也满足它 ⇒ M19 绿。改成可达扫描（同一个坑本项目栽过多次）。
    # [EN] The first version checked `'need_check' in ast.unparse(_gate)`, which a call under
    # [EN] `if False:` also satisfies => M19 stayed green. Switched to the reachable walk.
    ok('E14 ★★★ 成对：这条检查**真的会执行到**（不是只写了个函数没人调）',
       _reachable_call('sim/loop.py', '_review_gate', 'need_check'), '')


# ══════════════════════════════════════════════════════════
#  F  库本身合格
# ══════════════════════════════════════════════════════════
def group_f() -> None:
    from craft import craftmix as CM

    entries = CM.load()['entries']
    no_tip = [k for k, v in entries.items() if not str(v.get('提示词') or '').strip()]
    ok('F1 ★★★ **每一条都有可执行的 `提示词`**'
       '（只写"原理"的条目被喂出去等于报个书名 —— 15节拍/英雄之旅原来就是这样）',
       not no_tip, f'缺提示词：{no_tip}')

    # "有提示词"不等于"能用"：至少得是一个**指令**（含动词性的引导），
    # 不能是一串名词。判"有没有'请/让/用/写/把/要/别/不许/只/先'这类字样"。
    weak = [k for k, v in entries.items()
            if not any(x in str(v.get('提示词')) for x in
                       ('请', '让', '用', '写', '把', '要', '别', '不许', '只', '先',
                        '不要', '可以', '必须', '检查', '给', '说', '选'))]
    ok('F2 ★★★ 每条提示词都是**一句话指令**，不是名词串（否则到了也没用）',
       not weak, f'名词串：{weak}')

    missing = [n for n in _NEW_ENTRIES if n not in entries]
    ok(f'F3 ★★★ 2026-10-18 补的 {len(_NEW_ENTRIES)} 条全在库里',
       not missing, f'缺：{missing}')

    # 三条真缺口必须能被"该读它们的人"读到
    from crew.agents import READS
    ok('F4 ★★★ #7 `反应与决定` 进了复盘的点名（"这一段有没有落点"是复盘的活）',
       '反应与决定' in READS.get('reviewer', ()), '')
    ok('F5 ★★★ #4 `欲望与需求` 同上（看人物弧光），#10 `自由间接引语` 进了小说作家'
       '（只有落笔那一层才谈得上距离）',
       '欲望与需求' in READS.get('reviewer', ())
       and '自由间接引语' in READS.get('novelist', ()), '')

    # 类型卡映射里的名字必须都查得到（`_misses` 是数据缺口的自查）
    ok('F6 ★★ 类型卡映射里的条目名**全部查得到**（否则静默少喂一条）',
       not CM._misses(), str(CM._misses()))


def main() -> int:
    for fn in (group_a, group_b, group_c, group_d, group_e, group_f):
        try:
            fn()
        except Exception as e:                                   # noqa: BLE001
            ok(f'{fn.__name__} 执行失败', False, repr(e))
    bad = [c for c in CHECKS if not c[1]]
    print(f'\n手艺调度验证：{len(CHECKS) - len(bad)}/{len(CHECKS)}', flush=True)
    if bad:
        print('有失败项：', flush=True)
        for n, _, _d in bad:
            print(f'  ✗ {n}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
