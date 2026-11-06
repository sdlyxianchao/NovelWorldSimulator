# -*- coding: utf-8 -*-
"""验证：**进度表"一站一件事"** —— 判据被拆开、装配与生成两处共用同一份实现。

用户 2026-10-21：
  ①「运行界面右上角的剧情的进度表一直不动 你看下是有问题 还是确实没有变动」
  ②「进度表这边是否可以把要进行的进度列出来」
  ③「按照第一个方向执行（拆判据） 记得不要面向特定项目」

查出来的结构问题（为什么"一直不动"）：
  · 判定口径（`director/engine.py` 的 `_PROGRESS_PROMPT`）明确要求
    「判据里串了几件事，**只做到其中一件就是没满足** —— 必须**全部**做到」；
  · 那条本身是对的（治「第一天就想把谜底解开」），但**生成进度表时允许一站捆四件事**
    ⇒ "必须全部做到"变成了"几乎永远做不到"；
  · 实测某项目：那一站的判据列了四件事，日志里其中两件早就发生了，
    只卡在最后一件 ⇒ 进度表永远是 0/N，界面上看着像卡死。

修法（方向一：拆判据）：
  · 源头 —— 生成提示词要求「判据只能写一件事」；
  · 兜底 —— `world/progress_split.split_fat_nodes` 把"串了多件"的站拆成一站一件；
    **装配（存量项目）与生成（新开卷）共用这一份实现**；
  · 只在内存里拆，**不写回** `故事进度.yaml`（那是作者的设定集）。

判据分组：
  A 切分规则（纯函数）：该拆的拆、**不该拆的绝不拆**（误拆会比原本更糟）
  B 拆分整表：状态继承 / id 重排 / 不改原表 / 总数上限
  C 两处接线（AST）：装配与生成都调了**同一份**实现，且各自只调一次
  D 顺序（AST）：装配里拆分必须排在 `current_node` 与 `_apply_round_cast` **之后**
  E 面向性：实现里**不许出现任何具体作品的专名**（用户：「不要面向特定项目」）

跑法：.venv\\Scripts\\python.exe tools/verify_progress_split.py
产出：assets/screenshots/progress_split_report.json

English:
Verify **"one station, one task"**: criteria get split, and assembly + generation share one
implementation. See the module note in `world/progress_split.py` for the full reasoning.
Groups: A splitting rules (must split what should be split, and **must not split what should not** --
a wrong split is worse than the original); B whole-table splitting (status inheritance / id
renumbering / no mutation of the input / node cap); C wiring (AST): both entry points call the
**same** implementation; D order (AST): assembly splits after `current_node` and `_apply_round_cast`;
E neutrality: the implementation must contain **no proper nouns from any specific work** (user:
"don't target a specific project").
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from world import progress_split as PS                                 # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''), flush=True)
    return bool(cond)


# ══════════════════════════════════════════════════════════════
#  A —— 切分规则（纯函数）
# ══════════════════════════════════════════════════════════════
def rules_checks() -> None:
    print('\n── A 切分规则（该拆的拆、不该拆的不拆）──')
    sp = PS.split_criteria_text

    # 该拆：几件先后发生的事，用逗号/顿号/分号并列
    n_three = sp('甲完成多站差事，乙发现旧账署名线索，丙听老人讲古重走旧路')
    ok('A1 ★★★ 三件事用逗号并列 ⇒ 拆成 3 段（这正是"进度表一直不动"的原始形状）',
       len(n_three) == 3, str(n_three))

    n_dun = sp('甲把东西交给乙、丙把门关上、丁点火烧了旧纸')
    ok('A2 ★★ 顿号并列也拆（顿号几乎必然是并列）',
       len(n_dun) == 3, str(n_dun))

    n_semi = sp('甲终于认出那个记号；乙当场跪下认罪')
    ok('A3 ★★ 分号并列也拆',
       len(n_semi) == 2, str(n_semi))

    # 不该拆（**这半边更重要**：误拆会造出"永远满足不了"的假站，比原本更糟）
    # [EN] The "must not split" half matters more: a wrong split creates a station that can never be
    # [EN] satisfied, which is worse than the original.
    #
    # ★★★ 两道长度闸要**分别**有用例（2026-10-21 反例法照出来的）：
    #   第一版只有「两人公开对峙，气氛紧张」一条，它被**总长闸**先挡住（11 < 14），
    #   于是把「每段长度闸」降到 1 时判据仍然绿 —— 那道闸从来没被证明有本事。
    #   ⇒ 一条用例只能测一道闸；两道闸就两条用例，各自刚好只触发那一道。
    # [EN] ★★★ The two length gates need **separate** cases (found by the counterexample harness,
    # [EN] 2026-10-21): the first version had only one sentence, and it was stopped by the **whole-length
    # [EN] gate** first (11 < 14), so lowering the **per-part gate** to 1 left the criterion green --
    # [EN] that gate was never proven to have teeth. One case can only test one gate.
    # 只挡「总长」那道闸：11 字 < 14，**每段都够长**（5 / 5）⇒ 只能靠总长闸挡住。
    #   ⚠ 用例必须"只触发那一道闸"：`两人公开对峙，气氛紧张` 看着更自然，但它每段只有
    #     4/4 字，被「每段闸」先挡住 ⇒ 把总长闸降到 1 时判据仍然绿（反例法 ③ 照出来的）。
    # [EN] Only the whole-length gate: 11 < 14 while **every part is long enough** (5 / 5) => only the
    # [EN] whole-length gate can stop it. ⚠ A case must trigger **one** gate: a more natural sentence
    # [EN] has 4/4-char parts and is stopped by the per-part gate first, so lowering the whole-length
    # [EN] gate left the criterion green (found by mutation ③).
    ok('A4a ★★★ 不拆：甲乙丙丁戊，己庚辛壬癸（11 字 < 总长下限；两段都够长 ⇒ 单靠总长闸）',
       len(sp('甲乙丙丁戊，己庚辛壬癸')) == 1, str(sp('甲乙丙丁戊，己庚辛壬癸')))
    ok('A4a2 ★★ 不拆：两人公开对峙，气氛紧张（短判据里的逗号多半是修饰）',
       len(sp('两人公开对峙，气氛紧张')) == 1, str(sp('两人公开对峙，气氛紧张')))
    # 只挡「每段」那道闸：总长 19 ≥ 14 够长，但「然后走了」4 字 < 5，碎句要并回去
    _frag = '甲把他欠了多年的旧账一笔一笔全部算清，然后走了'
    ok('A4b ★★★ 不拆：长判据里的碎句（总长够，但有一段只有 4 字 ⇒ 每段闸；'
       '硬切会切出"然后走了"这种永远满足不了的假站）',
       len(sp(_frag)) == 1, str(sp(_frag)))
    for text, why in (('他决定离开', '没有并列'), ('丙听老人讲古', '没有并列')):
        got = sp(text)
        ok(f'A4c ★★★ 不拆：{text}（{why}）', len(got) == 1, str(got))

    # ★★★ 标记要够用：一句里并了 5 件事的判据**也要能拆**。
    #   （第一版只有 ①②③④ 四个标记 ⇒ 5 件事整句不拆 ⇒ 那一站永远卡着 ——
    #     这恰恰是这次要治的病本身。）
    # [EN] ★★★ Enough marks: a criterion naming 5 tasks **must still split**. (The first version had
    # [EN] only ①②③④, so 5 tasks stayed whole => that station stuck forever -- the very disease being
    # [EN] treated.)
    _five = sp('甲乙丙丁戊己庚辛壬一、甲乙丙丁戊己庚辛壬二、甲乙丙丁戊己庚辛壬三、'
               '甲乙丙丁戊己庚辛壬四、甲乙丙丁戊己庚辛壬五')
    ok('A5 ★★★ 一句里并了 5 件事 ⇒ 拆成 5 段（标记够用，不许"因为编号不够就整句不拆"）',
       len(_five) == 5, f'{len(_five)} 段')

    # 段数上限 = 标记数：一句里并了 10 件事 ⇒ **不拆**（硬切只会切出看不懂的碎片）
    # [EN] The part cap equals the number of marks: a criterion naming 10 tasks is **not split**.
    _ten = sp('、'.join(['甲乙丙丁戊己庚辛壬癸' + str(i) for i in range(1, 11)]))
    ok('A5b ★★ 并了 10 件事 ⇒ 不拆（超过标记数：硬切只会切出看不懂的碎片）',
       len(_ten) == 1, f'{len(_ten)} 段')

    ok('A6 ★★ 句末标点会被去掉（拆开的每一段都是独立判据，不该带句号）',
       all(not p.rstrip().endswith(('。', '.'))
           for p in sp('甲完成多站差事，乙发现旧账署名线索，丙听老人讲古重走旧路。')),
       str(sp('甲完成多站差事，乙发现旧账署名线索，丙听老人讲古重走旧路。')))

    ok('A7 ★ 空 / 空白判据原样返回一段（不炸）',
       sp('') == [''] and len(sp('   ')) == 1, '')


# ══════════════════════════════════════════════════════════════
#  B —— 拆分整表
# ══════════════════════════════════════════════════════════════
def table_checks() -> None:
    print('\n── B 拆分整表（状态继承 / id 重排 / 不改原表 / 上限）──')
    src = [
        {'id': 'N01', '名称': '第一站', '完成判据': '甲完成多站差事，乙发现旧账署名线索', '状态': '已完成'},
        {'id': 'N02', '名称': '第二站', '完成判据': '丙听老人讲古重走旧路', '状态': '进行中'},
    ]
    import copy
    before = copy.deepcopy(src)
    out, made = PS.split_fat_nodes(src)

    ok('B1 ★★★ 该拆的站拆开了、只有一件的站原样留着',
       len(out) == 3 and made == 1, f'{len(out)} 站 / 新增 {made}')
    ok('B2 ★★★ 原表**没有被改动**（调用方可能还要用）',
       src == before, '变了' if src != before else '没变')
    ok('B3 ★★★ 原来标「已完成」的站，拆开后**每一段都是已完成**'
       '（不继承的话走完的站会变回未开始 = 进度倒退）',
       all(nd['状态'] == '已完成' for nd in out[:2]), str([nd['状态'] for nd in out]))
    ok('B4 ★★ id 重排成连续的 N01..Nxx（拆开后原 id 不再连续，留着三处会各出各的问题）',
       [nd['id'] for nd in out] == ['N01', 'N02', 'N03'],
       str([nd['id'] for nd in out]))
    ok('B5 ★★ 拆出来的段带 `_拆自` 标记（只给界面 tooltip 用）',
       all(nd.get('_拆自') == '第一站' for nd in out[:2]), str(out[0].get('_拆自')))
    ok('B6 ★★ 站名带序号，一眼能看出是同一站拆出来的',
       out[0]['名称'].endswith('①') and out[1]['名称'].endswith('②'), 
       f'{out[0]["名称"]} / {out[1]["名称"]}')

    # 上限：一份每站都捆五件事的表，不许炸成二十几站
    # [EN] Cap: a table where every station packs five tasks must not explode into twenty-odd stations.
    fat = [{'id': f'X{i}', '名称': f'站{i}', '状态': '未开始',
            '完成判据': '一二三四五六个字甲，一二三四五六个字乙，一二三四五六个字丙，'
                        '一二三四五六个字丁'} for i in range(6)]
    out2, _ = PS.split_fat_nodes(fat)
    ok(f'B7 ★★★ 总数不超过上限（{PS._MAX_NODES}）：一份"每站捆四件"的 6 站表不会被炸开',
       len(out2) <= PS._MAX_NODES, f'{len(fat)} 站 → {len(out2)} 站')

    empty, zero = PS.split_fat_nodes([])
    ok('B8 ★ 空表不炸、返回空表', empty == [] and zero == 0, '')


# ══════════════════════════════════════════════════════════════
#  C / D —— 接线与顺序（AST）
# ══════════════════════════════════════════════════════════════
def _calls_of(fn) -> list[tuple[int, str]]:
    src = _src_of(fn)
    tree = ast.parse(src)
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            try:
                out.append((int(n.lineno), ast.unparse(n.func)))
            except Exception:                                # noqa: BLE001
                pass
    return out


def _src_of(fn) -> str:
    import inspect
    return inspect.getsource(fn)


def wiring_checks() -> None:
    print('\n── C 两处接线（装配 / 生成 共用同一份实现）──')
    from sim import setup as SETUP
    from ingest import progress as PROG

    # 装配侧：找那个真正做装配的函数（含 `_apply_round_cast` 调用的那个）
    setup_fn = None
    for name, obj in vars(SETUP).items():
        if inspect_isfunc(obj) and 'progress_nodes=[dict(n)' in _src_of(obj):
            setup_fn = obj
            break
    ok('C1 ★★★ 找得到装配函数（下一步要在它里面查接线）', setup_fn is not None,
       getattr(setup_fn, '__name__', ''))
    if setup_fn is None:
        return
    c_setup = _calls_of(setup_fn)
    ok('C2 ★★★ **装配侧**调了 `split_fat_nodes`（存量项目靠这一处才生效）',
       any('split_fat_nodes' in f for _l, f in c_setup),
       str([f for _l, f in c_setup if 'split' in f.lower()]))

    c_gen = _calls_of(PROG.build_progress_table)
    # ⚠ 口径已改（2026-10-27）：生成侧不再**直接**调 `split_fat_nodes`，而是调
    #   抽出来的 `split_and_rebuild`（抽它的理由见那个函数的注释：拆站时每个字段
    #   都要跟着走，埋在 `build_progress_table` 里判据测不到）。
    #   要防的东西没变 —— "新开卷那一侧也要拆" ⇒ 判据改成**两条都要**：
    #     ① 生成侧调到了拆分入口（直接或经过 `split_and_rebuild`）；
    #     ② 那个入口自己**真的调** `split_fat_nodes`（不是只挂个名字）。
    # [EN] The shape changed (2026-10-27): the generation side no longer calls `split_fat_nodes`
    #   **directly** but calls the extracted `split_and_rebuild` (why it was extracted: see its own
    #   note -- every field must ride along a split, and buried in `build_progress_table` it was
    #   untestable). What this guards has not changed => the criterion now checks **both**:
    #   ① the generation side reaches a split entry (directly or via `split_and_rebuild`);
    #   ② that entry itself **really calls** `split_fat_nodes`.
    ok('C3 ★★★ **生成侧**也走到了 `split_fat_nodes`（新开卷靠这一处）',
       (any('split_fat_nodes' in f for _l, f in c_gen)
        or (any('split_and_rebuild' in f for _l, f in c_gen)
            and any('split_fat_nodes' in f
                    for _l, f in _calls_of(PROG.split_and_rebuild)))),
       str([f for _l, f in c_gen if 'split' in f.lower()])
       + ' → ' + str([f for _l, f in _calls_of(PROG.split_and_rebuild)
                      if 'split' in f.lower()]))

    ok('C4 ★★★ 两处用的是**同一份实现**（同一个模块 `world.progress_split`），'
       '不是各写一套 —— 各写一套迟早"新卷拆了、老项目没拆"',
       'progress_split' in _src_of(setup_fn)
       and 'progress_split' in _src_of(PROG.build_progress_table), '')

    print('\n── D 顺序（AST）──')
    ln_split = min((l for l, f in c_setup if 'split_fat_nodes' in f), default=-1)
    # `current_node = ...` 是 `Store` 不是 `Call`，单独走一遍 AST
    tree = ast.parse(_src_of(setup_fn))
    ln_cur = min((int(n.lineno) for n in ast.walk(tree)
                  if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Attribute) and t.attr == 'current_node'
                          for t in n.targets)), default=-1)
    ln_cast = min((l for l, f in c_setup if '_apply_round_cast' in f), default=-1)
    ok('D1 ★★★ 拆分排在 `world.current_node = ...` **之前**'
       '（拆开要重排 id，先指再拆会指到不存在/含义变了的 id）',
       ln_split > 0 and ln_cur > 0 and ln_split < ln_cur,
       f'拆分@{ln_split} current_node@{ln_cur}')
    ok('D2 ★★ 拆分排在 `_apply_round_cast` **之后**（那一支可能整表换人，先拆等于白拆）',
       ln_cast > 0 and ln_split > 0 and ln_cast < ln_split,
       f'_apply_round_cast@{ln_cast} 拆分@{ln_split}')


def inspect_isfunc(obj) -> bool:
    import inspect
    return inspect.isfunction(obj)


# ══════════════════════════════════════════════════════════════
#  E —— 不许面向特定项目
# ══════════════════════════════════════════════════════════════
def summary_checks() -> None:
    """F —— 「本轮将载入…」那个摘要，报的必须是**拆分之后**的站数。

    ★ 为什么值得单列：装配时报 10 站、摘要报 4 站，用户会以为程序出问题了。
      两个数字各说各话，是最容易被当成 bug 的那种不一致。
    [EN] Why this deserves its own group: assembly would run 10 stations while the summary says 4, and
    [EN] the user reads that as a bug. Two numbers disagreeing is the most "looks like a bug" kind of
    [EN] inconsistency.
    """
    print('\n── F 摘要（"本轮将载入…"要报拆后的站数）──')
    from sim.setup import settings_summary
    s = {'people': [{'名称': '甲'}], 'places': [], 'foreshadows': [],
         'nodes': [{'id': 'N01', '名称': '一站', '状态': '未开始',
                    '完成判据': '甲完成多站委托，乙发现旧账线索'},
                   {'id': 'N02', '名称': '二站', '状态': '未开始',
                    '完成判据': '丙听老人讲古'}]}
    out = settings_summary(s)
    ok('F1 ★★★ 摘要在"一站捆两件事"的设定上报 **3 个**（拆后），不是设定集里的 2 个',
       '进度节点 3 个' in out, out)

    s2 = {'people': [{'名称': '甲'}], 'places': [], 'foreshadows': [],
          'nodes': [{'id': 'N01', '名称': '一站', '状态': '未开始', '完成判据': '丙听老人讲古'}]}
    ok('F2 ★★ 本来就只有一个节点的设定集，摘要照报 1 个（不该被"优化"改数）',
       '进度节点 1 个' in settings_summary(s2), settings_summary(s2))


def neutrality_checks() -> None:
    print('\n── E 面向性（不许写死某部作品的专名）──')
    mod = Path(PS.__file__).read_text(encoding='utf-8')
    # 把注释也扫进去：注释里写书名，一样会被后来的人当"规则的一部分"
    # [EN] Comments are scanned too: a book title in a comment is just as likely to be read later as
    # [EN] "part of the rule".
    # 只扫**实现代码**（docstring 里允许举例说明"为什么"，但不许出现具体人名/地名）
    # [EN] Scan the implementation; docstrings may explain "why" but must not name specific people or
    # [EN] places.
    body = re.sub(r'""".*?"""', '', mod, flags=re.S)      # 去掉 docstring
    body = re.sub(r'#[^\n]*', '', body)                    # 去掉注释
    hits = [w for w in ('望江楼', '阿九', '老陈', '雪国', '甄英莲', '贾宝玉', '林黛玉')
            if w in body]
    ok('E1 ★★★ 实现代码里**没有任何具体作品的专名**（用户：「不要面向特定项目」）',
       not hits, f'命中 {hits}' if hits else '干净')

    # 反过来说：规则必须是**可数的条件**，不能是"某种书才成立"的形态
    # [EN] Conversely the rule must be **countable conditions**, not something that only holds for one
    # [EN] kind of book.
    ok('E2 ★★★ 规则是**三个可数条件**（分隔符 / 总长下限 / 每段下限），不依赖词表',
       PS._MIN_WHOLE > 0 and PS._MIN_PART > 0 and PS._MAX_NODES > 0
       and bool(PS._SPLIT_RE.pattern), 
       f'MIN_WHOLE={PS._MIN_WHOLE} MIN_PART={PS._MIN_PART} MAX_NODES={PS._MAX_NODES}')


# ── G 跨度 / 篇幅（2026-10-26）────────────────────────────────────────
#   用户：「真正小说里并不一定每天都有故事 而是根据大纲 可能会快速跳过很多时间
#   每隔一段时间才会有1个事件集中描写 …… 小说时间不是匀速流逝的
#   现在这个模拟最大的问题就是这里」+「注意 一个事件可能跨天」。
#
#   这一组守三件事：
#     G1 两个字段是**闭集**（自由文本没法算拍预算）
#     G2 缺了要**推断**，而且**照实标注是推的**（不许冒充作者写的）
#     G3 拍预算表覆盖全部篇幅档，且**没有任何一档是"不限"**
#        （`带过` 允许 1 拍，但绝不允 0 拍 —— 0 拍那站永远推不动）
# [EN] ── G Span / length (2026-10-26) ──
# [EN] Guards three things: (G1) both ladders are **closed sets**; (G2) missing values get
# [EN] **inferred and marked as inferred**, never passed off as author-written; (G3) the beat budget
# [EN] table covers every tier and **no tier means "unlimited"** (`带过` allows 1 beat, never 0).
def span_weight_checks() -> None:
    print('\n── G 跨度 / 篇幅（小说时间不是匀速的）──')
    from ingest import progress as PR

    ok('G1 ★★★ 跨度与篇幅都是**闭集**（自由文本没法算拍预算）',
       PR.SPANS == ('一场', '当日', '数日', '一旬', '数月')
       and PR.WEIGHTS == ('详', '中', '略', '带过'),
       f'{PR.SPANS} / {PR.WEIGHTS}')

    ok('G2 ★★★ 拍预算表**覆盖全部篇幅档**，且没有一档是"不限"',
       set(PR.BEAT_BUDGET) == set(PR.WEIGHTS)
       and all(lo >= 1 and hi >= lo for lo, hi in PR.BEAT_BUDGET.values()),
       str(PR.BEAT_BUDGET))

    # 造：第一个「没写跨度/篇幅」的节点，检查推断 + 标注
    n = PR.ProgressNode(id='N01', name='入楼收留',
                        summary='阿九在淄川街头醒来，被掌柜收留，当夜第一次见夜客。',
                        criteria='阿九得到伙计身份')
    out = PR.resolve_span_weight([n])[0]
    ok('G2b ★★★ 缺字段时**会推断**（不是留空、也不是崩）',
       out.span in PR.SPANS and out.weight in PR.WEIGHTS,
       f'跨度={out.span} 篇幅={out.weight}')
    ok('G2c ★★★ 推断出来的**必须标注是推的**（不许冒充作者写的）',
       set(out.inferred) == {'span', 'weight'},
       f'inferred={out.inferred}')
    d = out.to_dict()
    ok('G2d ★★ 落盘时**带上人能看懂的「推断」说明**（作者才知道该去补）',
       '推断' in d and '程序推的' in str(d.get('推断')),
       str(d.get('推断')))

    # 作者写了的**一个字都不动**
    n2 = PR.ProgressNode(id='N02', name='开庭抉择', summary='重审开庭',
                         criteria='当众宣布', span='一场', weight='详')
    o2 = PR.resolve_span_weight([n2])[0]
    ok('G2e ★★★ 作者写了的跨度/篇幅**一个字都不动**（哪怕程序觉得该是别的档）',
       o2.span == '一场' and o2.weight == '详' and not o2.inferred,
       f'跨度={o2.span} 篇幅={o2.weight} inferred={o2.inferred}')

    # 自由文本要归一到最近的档（"两个月" → 数月）
    n3 = PR.ProgressNode(id='N03', name='x', summary='y', criteria='z',
                         span='大约两个月', weight='详细写')
    o3 = PR.resolve_span_weight([n3])[0]
    ok('G2f ★★ 自由文本（"大约两个月"）**归一到最近的档**，并标明被改过',
       o3.span == '数月' and o3.weight == '详' and o3.inferred,
       f'跨度={o3.span} 篇幅={o3.weight} inferred={o3.inferred}')

    # G3：带过只有 1 拍（不是 0）—— 0 拍那站永远推不动
    ok('G3 ★★★ 「带过」给 **1 拍**（不是 0：0 拍那一站永远推不动进度）',
       PR.BEAT_BUDGET['带过'] == (1, 1), str(PR.BEAT_BUDGET['带过']))

    # 多站地名 → 跨天的结构依据
    n4 = PR.ProgressNode(id='N04', name='重走旧路',
                         summary='太原站自悟，崂山站见封存雅间，莒州站听老陈讲从前。',
                         criteria='听老陈讲出前任掌柜')
    s4 = PR.infer_span(n4, 1, 8)
    ok('G3b ★★ 概要有**多个「…站」⇒ 跨度至少「数日」**（这是数出来的，不是猜语气）',
       s4 in ('数日', '一旬', '数月'), f'推断={s4}')

    # 拍预算的硬闸（在 director/day_plan 里）
    from director import day_plan as DP
    beats = [{'做什么': f'第{i}拍'} for i in range(200)]
    cut, why = DP._clamp_beats(beats, 15, 25)
    ok('G4 ★★★ 拍数**超上限会被截断**（一天 133 幕那种情况的硬闸）',
       len(cut) == 25, f'200 拍 → {len(cut)} 拍（{why[:30]}）')
    low, _ = DP._clamp_beats(beats[:2], 15, 25)
    ok('G4b ★★ 拍数**不够不补空拍**（补出来的拍是空的，等于花钱买废句）',
       len(low) == 2, f'2 拍 → {len(low)} 拍')
    # 推进那一拍要保住
    b2 = [{'做什么': f'第{i}拍'} for i in range(80)]
    b2[-1] = {'做什么': '完成判据：当众宣布终局'}
    keep, _ = DP._clamp_beats(b2, 15, 25)
    ok('G4c ★★★ 截断时**保住"推进判据"那一拍**（它常常在最后，砍尾巴就把它砍了）',
       any('完成判据' in str(x) for x in keep), f'保留 {len(keep)} 拍')


def cross_day_checks() -> None:
    """**跨天事件**：一个事件可能跨天（用户 2026-10-26 点名）。"""
    print('\n── H 跨天事件（一个事件可能跨天）──')
    from types import SimpleNamespace as NS
    from director.day_plan import DayScript

    runner = None
    try:
        from sim.loop import RunLoop
        runner = RunLoop.__new__(RunLoop)
    except Exception as e:                                   # noqa: BLE001
        ok('H0 能拿到 RunLoop（不然这组测不了）', False, f'{e!r}')
        return

    beats = [{'做什么': f'第{i}拍'} for i in range(20)]

    def mk(span: str, ticks: int):
        runner.world = NS(progress_nodes=[{'id': 'N01', '名称': '重走旧路',
                                           '概要': '甲站…乙站…丙站',
                                           '状态': '进行中', '跨度': span}],
                          current_node='N01', game_day=2)
        runner.db = None
        runner._current_day = 2
        runner._ticks_today = ticks
        runner._day_script = DayScript(day=2, story='旧路', beats=beats,
                                       roles={'甲': ['x']}, budget=(15, 25))
        return runner._carry_unplayed_beats()

    r1 = mk('数日', 8)
    ok('H1 ★★★ 跨度「数日」且没演完 ⇒ **把剩余分拍带到下一天**（不再是每天重新规划）',
       bool(r1) and len(r1['beats']) == 12, f'带 {len(r1["beats"]) if r1 else 0} 拍')
    ok('H2 ★★★ 带上的是**还没演的那几拍**，不是全部（全部带走会让同一批戏演两遍）',
       bool(r1) and r1['beats'][0]['做什么'] == '第8拍',
       f'第一拍={r1["beats"][0]["做什么"] if r1 and r1["beats"] else "?"}')
    ok('H3 ★★ 演完了就不带（照常规划新的一天）',
       mk('数日', 20) is None)
    ok('H4 ★★★ 跨度「当日 / 一场」**不带**（= 旧行为，逐字不变）',
       mk('当日', 5) is None and mk('一场', 1) is None)
    ok('H5 ★★ 打包里带上 `from_day` / `budget`（日志与界面要能说清"这几天在演同一站"）',
       bool(r1) and r1.get('from_day') == 2 and r1.get('budget') == (15, 25),
       f'{r1 and r1.get("from_day")} / {r1 and r1.get("budget")}')


def assembly_checks(tmp: Path) -> None:
    """**I 组：装配真的把「跨度 / 篇幅」搬过来了**（2026-10-26）。

    来历：上一轮给 `ProgressNode` 加了这两个字段、也写进了 `故事进度.yaml`，
    却**漏搬了 `sim/setup.load_settings`** —— 于是运行时 `world.progress_nodes`
    里根本没有这两个键：
      · `beat_budget_for` 每次现推（作者写的"篇幅:详"被无声忽略）；
      · `_carry_unplayed_beats` 读 `跨度` 永远空 ⇒ **跨天携带从来没生效过**；
      · 写作层按单元定详略读不到 ⇒ 静默退化成"全按中档"。
    同一族的第二处：`display/scene_builder` 读的是 `node_info.get('name')`，
    而进度表的键是中文 `名称` ⇒ 实测 133 幕 **133 个空串**，幕头永远不带站名
    （"按情节单元写"整条路因此不会启动）。

    ⚠ 这两处都是"两条路都能跑，只是永远不是作者要的那一档" ——
      正是本项目记过的「字段**漏搬**比没写更难发现」，所以判据必须**行为级**：
      真读一份 yaml、真开一幕。
    [EN] **Group I: assembly really carries span/length** (2026-10-26). The previous round added
    [EN] the fields and wrote them to the yaml but missed `sim/setup.load_settings`, so the runtime
    [EN] table had no such keys: budgets were always inferred, cross-day carry never fired, and the
    [EN] writer could not read the tier. Second site of the same family: `scene_builder` read
    [EN] `node_info.get('name')` while the table's key is the Chinese `名称` -- measured 133 of 133
    [EN] empty act names. Both are "both paths run, just never at the author's tier", hence
    [EN] behavioural checks: read a real yaml, open a real scene.
    """
    print('\n── I 装配（跨度/篇幅 与 幕头站名）──')
    from sim import setup as SETUP
    from ingest import progress as PR

    d = tmp / 'settings_span'
    d.mkdir(parents=True, exist_ok=True)
    (d / SETUP.F_PROGRESS).write_text(
        '节点:\n'
        '- id: N01\n  名称: 入楼收留\n  概要: 街头醒来被收留\n  完成判据: 拿到伙计身份\n'
        '  状态: 进行中\n  跨度: 当日\n  篇幅: 详\n'
        '- id: N02\n  名称: 重走旧路\n  概要: 途中往来\n  完成判据: 到莒州\n'
        '  状态: 未开始\n',
        encoding='utf-8')
    s = SETUP.load_settings(d)
    n1 = s['nodes'][0]
    ok('I1 ★★★ 作者写的「跨度/篇幅」**装配时搬进了节点表**'
       '（漏搬 ⇒ 作者写的档被无声忽略，全靠程序猜）',
       n1.get('跨度') == '当日' and n1.get('篇幅') == '详', str((n1.get('跨度'), n1.get('篇幅'))))
    ok('I1b ★★★ 作者写了的**不许标成"推断"**（那是冒充关系反过来了）',
       '推断' not in n1, str(n1.get('推断')))

    n2 = s['nodes'][1]
    ok('I2 ★★★ 作者没写的 ⇒ **装配时补上推断值**，并标注"程序推的"',
       n2.get('跨度') in PR.SPANS and n2.get('篇幅') in PR.WEIGHTS and '推断' in n2,
       f'{n2.get("跨度")}/{n2.get("篇幅")} 推断={n2.get("推断")}')

    # 幕头站名：`scene_builder` 读的必须是中文键 `名称`
    from display import scene_builder as SB

    class _W:
        progress_nodes = [{'id': 'N01', '名称': '入楼收留', '概要': 'x', '完成判据': 'y',
                           '状态': '进行中', '跨度': '当日', '篇幅': '详'}]
        current_node = 'N01'
        scene = ''
        scene_desc = ''
        weather = '晴'
        tension = 0.3
        people: dict = {}

        def current_node_info(self):
            for nd in self.progress_nodes:
                if nd.get('id') == self.current_node:
                    return nd
            return None

    try:
        sc = SB.SceneBuilder(_W(), day=1).begin_scene(force=True)
        got = str(getattr(sc, 'node_name', '') or '')
    except Exception as e:                                   # noqa: BLE001
        got = f'（开幕失败：{e!r}）'
    ok('I3 ★★★ 幕头的站名**真的取到了**（读中文键 `名称`；实测真实数据 133 幕全空 ⇒ '
       '"按情节单元写"整条路不会启动）',
       got == '入楼收留', repr(got))

    # 成对：外部服务/老存档真的用 `name` 时也要认
    class _W2(_W):
        progress_nodes = [{'id': 'N01', 'name': '入楼收留', '状态': '进行中'}]
    try:
        sc2 = SB.SceneBuilder(_W2(), day=1).begin_scene(force=True)
        got2 = str(getattr(sc2, 'node_name', '') or '')
    except Exception as e:                                   # noqa: BLE001
        got2 = f'（开幕失败：{e!r}）'
    ok('I3b ★★ 成对：只有英文键 `name` 的存档也认（不许为了中文把老数据读空）',
       got2 == '入楼收留', repr(got2))


def main() -> int:
    print('=' * 62)
    print('  进度表"一站一件事"验证')
    print('=' * 62)
    import tempfile
    with tempfile.TemporaryDirectory(prefix='nws_span_') as td:
        for fn in (rules_checks, table_checks, wiring_checks, summary_checks,
                   neutrality_checks, span_weight_checks, cross_day_checks):
            try:
                fn()
            except Exception as e:                               # noqa: BLE001
                import traceback
                ok(f'{fn.__name__} 跑完', False, f'{e!r}')
                print(traceback.format_exc()[-800:])
        try:
            assembly_checks(Path(td))
        except Exception as e:                                   # noqa: BLE001
            import traceback
            ok('assembly_checks 跑完', False, f'{e!r}')
            print(traceback.format_exc()[-800:])
    n = len(report['checks'])
    good = sum(1 for c in report['checks'] if c['ok'])
    print(f'\n进度表拆分验证：{good}/{n}')
    (OUT / 'progress_split_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if good == n else 2


if __name__ == '__main__':
    raise SystemExit(main())
