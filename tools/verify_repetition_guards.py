# -*- coding: utf-8 -*-
"""验证：**复读、上一拍说的话、以及"雪国那一轮"的教训**（2026-10-18）。

用户要求：「speak 的问题修复，复读的问题修复 雪国的教训也想办法修复」。

三件事，一条一条钉住：

  一、`speak` 没被喂回去（`[你上一拍说的]` 从来不存在）
  ----------------------------------------------------
  实测（`ltxz-01`，豆包当演员）：**6 次决策里有 4 次是同一句台词**。
  根因与"上一拍做了什么"同源：`[刚才]` 只给 6 条，一拍七个人各说一句，
  他自己上一句早被挤出窗口 ⇒ 他不知道"这话我说过了"。
  豆包单次输出 100–160 token，不会自己换花样；hy3 输出 2900+ token 把缝遮住了
  ⇒ 这是**模型无关**的缺陷。

  二、**`kind` 表与生生产侧不一致 ⇒ 防重演整版没生效**（本次最要紧的一条）
  ----------------------------------------------------------------------
  `sim/loop._note_stage_line` 写的是 `kind='act'`，而 `last_own_action`
  只认 `'action'`（产品从不写这个字符串）⇒ 那个块**从来没有内容**，
  可 2026-10-17 那支判据自己造了 `kind='action'` 的夹具，**全绿**。
  ⇒ 本支 A 组**扫生产侧真实写入的 kind**，再要求 `last_own_action` 认它。

  三、复读：两处实现都有缝
  ------------------------
  · **环境句**：`_ambient_candidates` 曾把「底噪+事件声+静默」捆成一条 ⇒
    底噪与静默**每拍重复**（《雪国》263 字里"该响的敲门声没有响"出现 2 次），
    而且评语是"叙述者在替读者点题"；
  · **台词**：去重只认一字不差 ⇒「车份儿打算拖到什么时候」这种换语序的复读全放行。

  四、雪国的教训（评委的五条缺陷 → 三条落到产品）
  ----------------------------------------------
  · 台词太直太完整（"你觉得我是个什么样的人？"）⇒ 口癖/风格**离输出太远**；
  · 叶子开口成句（越硬约束）⇒ 同上；
  · "该响的敲门声没有响"⇒ 静默句被**原样当叙述**（声音设计提示词要它写"事实"）；
  · 戏没有落点 ⇒ 每拍要留下**一处不同**。

跑法：.venv\\Scripts\\python.exe tools/verify_repetition_guards.py
产出：assets/screenshots/repetition_guards_report.json

English:
Verification: **repetition, "what you said last beat", and the Snow Country lessons**
(2026-10-18). User: "fix the speak problem, fix the repetition problem, and find a way to fix the
Snow Country lesson too."

A. `speak` was never fed back -- measured (`ltxz-01`, Doubao as actor): **4 of 6 decisions were the
   same line**. Same cause as "what I did last beat": `[刚才]` yields 6 entries and seven people
   speaking pushes his own line out.
B. **The `kind` table disagreed with the producer => anti-replay never ran for a whole version**.
   `sim/loop._note_stage_line` writes `kind='act'`, `last_own_action` only accepted `'action'` (a
   string the product never writes), yet the 2026-10-17 verifier built its own `kind='action'`
   fixture and passed. => group A **scans the real kinds written by the production side**.
C. Repetition: two implementations were both leaking -- the ambient pool bundled bed/event/silence
   into every candidate (so bed and silence repeated every beat), and the dialogue guard only caught
   verbatim repeats.
D. Snow Country: the five judge defects reduce to three product causes -- the verbal tic/style sat
   too far from the output; the silence line was emitted verbatim as narration ("the narrator
   underlining the point"); and a beat could pass with no change at all.
Run: .venv\\Scripts\\python.exe tools/verify_repetition_guards.py
Output: assets/screenshots/repetition_guards_report.json
"""
from __future__ import annotations

import ast
import textwrap as _textwrap
import inspect
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

REPORT = APP_DIR / 'assets' / 'screenshots' / 'repetition_guards_report.json'
report: dict = {'checks': [], 'ok': False}


def ok(name: str, cond: bool, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:400]})
    print(f'{"✓" if cond else "✗"} {name}' + (f'  [{detail}]' if detail else ''), flush=True)
    return bool(cond)


def _read(rel: str) -> str:
    """读源码。⚠ 一律兜住 `OSError`：并行回归时 Windows 会独占打开 ⇒ 整支崩。"""
    try:
        return (APP_DIR / rel).read_text(encoding='utf-8')
    except OSError:
        return ''


# ══════════════════════════════════════════════════════════
#  A  kind 表 vs 生产侧
# [EN] The kind table vs the production side
# ══════════════════════════════════════════════════════════
def _produced_kinds() -> dict[str, set[str]]:
    """扫**生产代码**里 `note_line(...)` 的 `kind=` 实参，按文件归类。

    只扫 `sim/` `agent/` `crew/` `world/` `gui/`（产品），**不扫** `tools/`
    （判据自己）与 `developers/`（反例法与探针）—— 那些地方造夹具，
    它们写什么 kind 与产品无关，混进来反而会把这道判据变松。
    [EN] Scan the `kind=` arguments of `note_line(...)` in **production code**. Only
    [EN] `sim/` `agent/` `crew/` `world/` `gui/` -- not `tools/` or `developers/`, whose fixtures have
    [EN] nothing to do with what the product writes.
    """
    out: dict[str, set[str]] = {}
    for sub in ('sim', 'agent', 'crew', 'world', 'gui', 'display'):
        for p in sorted((APP_DIR / sub).glob('*.py')):
            try:
                src = p.read_text(encoding='utf-8')
            except OSError:
                continue
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            kinds: set[str] = set()
            for n in ast.walk(tree):
                if not isinstance(n, ast.Call):
                    continue
                fn = n.func
                nm = getattr(fn, 'attr', None) or getattr(fn, 'id', None)
                if nm != 'note_line':
                    continue
                for kw in n.keywords or []:
                    if kw.arg == 'kind' and isinstance(kw.value, ast.Constant) \
                            and isinstance(kw.value.value, str):
                        kinds.add(kw.value.value)
            if kinds:
                out[str(p.relative_to(APP_DIR))] = kinds
    return out


def group_a() -> None:
    from world.state import WorldState

    ok('A1 ★ `WorldState.SPEAK_KINDS` / `ACT_KINDS` 存在（kind 两族的唯一真相）',
       isinstance(getattr(WorldState, 'SPEAK_KINDS', None), tuple)
       and isinstance(getattr(WorldState, 'ACT_KINDS', None), tuple),
       f'{getattr(WorldState, "SPEAK_KINDS", None)} / '
       f'{getattr(WorldState, "ACT_KINDS", None)}')

    prod = _produced_kinds()
    ok('A2 ★★ 扫到了生产侧的 `note_line(kind=…)` 调用（扫不到就没资格往下判）',
       bool(prod), json.dumps({k: sorted(v) for k, v in prod.items()},
                              ensure_ascii=False)[:200])

    all_kinds = sorted({k for v in prod.values() for k in v})
    known = set(WorldState.SPEAK_KINDS) | set(WorldState.ACT_KINDS)
    unknown = [k for k in all_kinds if k not in known]
    ok('A3 ★★★ **生产侧写的每一个 kind 都归了族**（这一条就是本次的真凶：'
       '`act` 不在 `last_own_action` 的表里 ⇒ 防重演整版没生效）',
       bool(all_kinds) and not unknown,
       f'生产侧={all_kinds} 未归类={unknown}')

    # 端到端：拿**生产侧真写的**动作 kind 造一条，`last_own_action` 必须取到
    w = WorldState()
    w.scene = '某屋'
    w.recent_lines = []
    act_kinds = [k for k in all_kinds if k in WorldState.ACT_KINDS]
    for k in act_kinds:
        w.recent_lines.append({'who': '乙', 'text': f'第{k}拍：蹲下擦桌',
                               'kind': k, 'to': '', 'place': '某屋'})
    got = w.last_own_action('乙')
    ok('A4 ★★★ **产品写进去的 kind，`last_own_action` 就取得到**（不是夹具自说自话）',
       bool(act_kinds) and got == f'第{act_kinds[-1]}拍：蹲下擦桌', repr(got))

    w2 = WorldState()
    w2.scene = '某屋'
    w2.recent_lines = [{'who': '乙', 'text': '我是谁。怎么躺在这。',
                        'kind': 'aside', 'to': '', 'place': '某屋'}]
    ok('A5 ★★ 成对：**心声不算动作**（喂回去会让模型以为"想过的事已经发生了"）',
       w2.last_own_action('乙') == '', repr(w2.last_own_action('乙')))

    w3 = WorldState()
    w3.scene = '某屋'
    w3.recent_lines = [{'who': '乙', 'text': '我不知道。', 'kind': 'speak',
                        'to': '', 'place': '某屋'}]
    ok('A6 ★★ 成对：**台词不算动作**（台词走 `last_own_lines`，混在一起就分不清'
       '"我做过"与"我说过"）',
       w3.last_own_action('乙') == '', repr(w3.last_own_action('乙')))


# ══════════════════════════════════════════════════════════
#  B  上一拍说了什么
# [EN] What I said last beat
# ══════════════════════════════════════════════════════════
def _lines_fixture() -> list[dict]:
    return [
        {'who': '丙', 'text': '这屋早先从某地搬来。', 'kind': 'speak', 'to': '', 'place': '某屋'},
        {'who': '乙（别处）', 'text': '在别处说的。', 'kind': 'speak', 'to': '', 'place': '某屋'},
        {'who': '乙', 'text': '第一句。', 'kind': 'speak', 'to': '甲', 'place': '某屋'},
        {'who': '甲', 'text': '别人的话。', 'kind': 'speak', 'to': '乙', 'place': '某屋'},
        {'who': '乙', 'text': '我是谁。', 'kind': 'aside', 'to': '', 'place': '某屋'},
        {'who': '乙', 'text': '第二句。', 'kind': 'speak', 'to': '甲', 'place': '某屋'},
    ]


def group_b() -> None:
    from world.state import WorldState

    ok('B1 ★ `WorldState.last_own_lines` 存在（"上一拍说了什么"只有一个取数口子）',
       callable(getattr(WorldState, 'last_own_lines', None)), '')

    w = WorldState()
    w.scene = '某屋'
    w.recent_lines = _lines_fixture()
    got = w.last_own_lines('乙', 2)
    ok('B2 ★★★ 取到的是**自己说的两句**，旧→新（读起来是时间顺序），'
       '不是别人的、也不是心声',
       got == ['第一句。', '第二句。'], repr(got))
    ok('B3 ★★ 名字带后缀也认得出（`乙（别处）` 是他本人说的，'
       '不剥括号就查不到 ⇒ 在别处说的话照样复读）',
       w.last_own_lines('乙', 3) == ['在别处说的。', '第一句。', '第二句。'],
       repr(w.last_own_lines('乙', 3)))

    ok('B4 ★ 数量按 `limit` 收（给 1 就只给最新那句）',
       w.last_own_lines('乙', 1) == ['第二句。'], repr(w.last_own_lines('乙', 1)))

    w2 = WorldState()
    w2.scene = '某屋'
    w2.recent_lines = [{'who': '乙', 'text': '拎桶进屋。', 'kind': 'act',
                        'to': '', 'place': '某屋'}]
    ok('B5 ★★ 成对：**只做了动作没开口 ⇒ 空列表**（不能把动作当台词喂回去）',
       w2.last_own_lines('乙') == [], repr(w2.last_own_lines('乙')))

    w3 = WorldState()
    w3.scene = '某屋'
    w3.recent_lines = [{'who': '乙', 'text': '我是谁。', 'kind': 'aside',
                        'to': '', 'place': '某屋'}]
    ok('B6 ★★ 成对：**心声不算"说出口的话"**',
       w3.last_own_lines('乙') == [], repr(w3.last_own_lines('乙')))

    ok('B7 ★ 成对：问一个没说过话的人 ⇒ 空列表（不拿别人的充数）',
       w.last_own_lines('路人甲') == [], repr(w.last_own_lines('路人甲')))

    # 缓冲要留得下：一拍七个人各一句，8 条根本活不过一拍
    ok('B8 ★★★ 缓冲至少 24 条（8 条时"上一拍说的话"必然已被挤出去 —— '
       '这正是这条缝存在的原因）',
       int(getattr(WorldState, 'RECENT_LINES_MAX', 0)) >= 24,
       str(getattr(WorldState, 'RECENT_LINES_MAX', 0)))

    # ── B9/B10「这一场已经做过的事」（隔一拍的招牌动作）──
    w4 = WorldState()
    w4.scene = '某屋'
    w4.recent_lines = [
        {'who': '乙', 'text': '端酒壶站门口。', 'kind': 'act', 'to': '', 'place': '某屋'},
        {'who': '乙', 'text': '我是谁。', 'kind': 'aside', 'to': '', 'place': '某屋'},
        {'who': '乙', 'text': '脸埋进臂弯。', 'kind': 'act', 'to': '', 'place': '某屋'},
        {'who': '乙', 'text': '走吧。', 'kind': 'speak', 'to': '', 'place': '某屋'},
        {'who': '乙（别处）', 'text': '又端酒过来。', 'kind': 'act', 'to': '', 'place': '某屋'},
    ]
    ok('B9 ★★★ `own_actions` 只回**这一场他做过的动作**（旧→新、不带台词/心声）',
       w4.own_actions('乙', 4) == ['端酒壶站门口。', '脸埋进臂弯。', '又端酒过来。'],
       repr(w4.own_actions('乙', 4)))
    ok('B10 ★ 数量按 `limit` 收（只留最近的几条，别把一整场都摆上去）',
       w4.own_actions('乙', 2) == ['脸埋进臂弯。', '又端酒过来。'],
       repr(w4.own_actions('乙', 2)))


# ══════════════════════════════════════════════════════════
#  C  提示词里真的挂上了
# [EN] Actually mounted in the prompt
# ══════════════════════════════════════════════════════════
def group_c() -> None:
    src = _read('agent/core.py')
    try:
        tree = ast.parse(src)
    except SyntaxError:
        ok('C0 ★ agent/core.py 能解析', False, 'SyntaxError')
        return
    decide = next((n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and n.name == 'decide'), None)
    ok('C1 ★ `decide` 在 AST 里找得到', decide is not None, '')
    if decide is None:
        return

    adds = [n for n in ast.walk(decide)
            if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name)
            and n.target.id == '_stage']
    joined = '\n'.join(ast.unparse(n) for n in adds)
    # ⚠ 2026-10-19 改名：`[你上一拍说的]` → `[你在这场说过的话]`（取 4 句，让"线"看得见）。
    #   判据跟着改锚点，但判的仍是**同一件事**：他自己的原话要追加进 `_stage`。
    #   成对的"四种走法"由 I 组守（I1-I5），这里只管"有没有挂上"。
    # [EN] Renamed on 2026-10-19: `[你上一拍说的]` -> `[你在这场说过的话]` (4 lines, so the
    # [EN] thread is visible). The anchor moves but the criterion is the same: his own lines must
    # [EN] be appended to `_stage`. The paired "four ways forward" is guarded by group I.
    ok('C2 ★★★ `decide` 里把「这场他自己说过的话」那段**追加进 `_stage`**',
       ('[你在这场说过的话]' in joined or '[你上一拍说的]' in joined), joined[:120])
    ok('C3 ★★★ 而且明写了"**换个说法说同一件事也是复读**"'
       '（只说"你别重复"不够 —— 模型会理解成别用同样的字）',
       '换个说法说同一件事也是复读' in joined, joined[-140:])
    ok('C4 ★★ 成对：「上一拍说的」与「上一拍做的」**同一个开关**'
       '（`DIALOGUE_CONTEXT`；关掉一刀全关，不许偷偷给）',
       joined.count('DIALOGUE_CONTEXT') < 1
       and 'DIALOGUE_CONTEXT' in ast.unparse(decide), '')

    # 口癖/说话方式：必须在**离输出最近**的动态层末尾挂上。
    # ⚠ 认**两条语句**：`_voice = self._voice_rules()` + `_dyn.append(_voice)`。
    #   只认其中一条都不算 —— 算出来不 append（等于没挂），append 一个空变量也是。
    # [EN] Two statements are required: the assignment and the append. Either alone does not count.
    # ★★★ 2026-10-19：**位置契约变了**（不是判据放松，是设计改了）。
    #
    #   原来是"算出来 + 挂进 `_dyn` 末尾（离输出最近）"。
    #   上一轮为**前缀缓存**把 `_voice` 前置到了规则区（`_semi` 开头那一段）——
    #   理由：口癖是**一轮不变**的（同一本书同一个人的说话方式），放在最前面
    #   才能被所有人物共用一次缓存命中；而"离输出最近"那个位置应该留给
    #   **真正每拍在变**的东西（导演提示 / 距离档 / 口癖配额）。
    #
    #   ⇒ 现在守的是"**挂上了，且恰好一次**"：
    #     · `_voice` 在 `_semi` 的元组里出现（挂载）；
    #     · `_dyn.append` 里**没有**它（否则同一段出现两次 —— 白烧 token，
    #       而且模型会当成两条独立要求；`verify_prefix_cache` 的 E3 也守这条）。
    # [EN] ★★★ 2026-10-19: **the position contract changed** (not a loosened check -- the design
    # [EN] changed). It used to be "assign + append to the end of `_dyn`". The previous round moved
    # [EN] `_voice` forward into the rules zone for **prefix caching**: the tic is stable within a
    # [EN] round, so putting it first lets every character share one cache hit; the "closest to
    # [EN] output" slot belongs to what really changes each beat (director hint / distance / quota).
    # [EN] => Now it guards "**mounted, and exactly once**": `_voice` appears in the `_semi` tuple,
    # [EN] and `_dyn.append` does NOT contain it (twice would burn tokens and read as two rules).
    assigned = [n for n in ast.walk(decide)
                if isinstance(n, ast.Assign)
                and 'voice_rules' in ast.unparse(n.value)]
    _semi_src = ''
    for _n in ast.walk(decide):
        if (isinstance(_n, ast.Assign) and isinstance(_n.targets[0], ast.Name)
                and _n.targets[0].id == '_semi'):
            _semi_src = ast.unparse(_n.value)
            break
    mounted = [1] if (assigned and '_voice' in _semi_src) else []
    dup = [n for n in ast.walk(decide)
           if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
           and n.func.attr == 'append'
           and isinstance(n.func.value, ast.Name) and n.func.value.id == '_dyn'
           and n.args and ast.unparse(n.args[0]).strip() in ('_voice',)]
    ok('C5 ★★★ 「你怎么开口」（口癖 + 说半句）算出来**并挂进了 `_semi`**'
       '（规则区；恰好一次，不在 `_dyn` 里重复）',
       bool(assigned) and bool(mounted) and not dup,
       f'赋值 {len(assigned)} 处 / 挂载 {len(mounted)} 处 / '
       f'`_dyn` 里重复 {len(dup)} 处')

    ok('C7 ★★★ 「你在这场已经做过的」挂进了 `_stage`，而且明写了"别再重演"'
       '＋**"没什么可做不是理由"**（只禁不推 ⇒ 三个人一起 wait，实测过一轮）',
       '[你在这场已经做过的]' in joined and '别再重演' in joined
       and '不是理由' in joined, joined[-120:])

    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == '_voice_rules'), None)
    ok('C6 ★★ `_voice_rules` 存在，而且是**从人设/风格卡取值**，不是写死的套话',
       fn is not None and 'catchphrase' in ast.unparse(fn)
       and 'style_card' in ast.unparse(fn), '')


# ══════════════════════════════════════════════════════════
#  D  环境句：不再"每条都带底噪+静默"
# [EN] Ambient lines: no longer bundling bed + silence into every candidate
# ══════════════════════════════════════════════════════════
class _FakeWorld:
    def __init__(self, **kw: object) -> None:
        self.scene = '某屋'
        self.weather = '晴'
        self.clock = None
        self.sound_design = {}
        self.__dict__.update(kw)


def group_d() -> None:
    from display.scene_builder import SceneBuilder

    bed, ev1, ev2, quiet = ('檐水不断', '算盘被谁碰了一下', '门轴响了一声',
                            '门外没有脚步声')
    w = _FakeWorld(sound_design={'底噪': bed, '事件声': [ev1, ev2], '静默': quiet})
    b = SceneBuilder(w, day=1)
    cands = b._ambient_candidates()
    sound = [c for c in cands if c in {bed, ev1, ev2, quiet}]

    ok('D1 ★★★ 候选里**没有一条是"底噪+事件声+静默"拼起来的**'
       '（旧实现这么拼 ⇒ 轮换只换了中间那句，底噪与静默每拍重复）',
       bool(sound) and all('；' not in c for c in sound), repr(sound))

    ok('D2 ★★★ 底噪、静默、每条事件声**各出现一次**（素材一条不少、也不重复）',
       [c for c in cands if c == bed] == [bed]
       and [c for c in cands if c == quiet] == [quiet]
       and ev1 in cands and ev2 in cands,
       f'底噪{ cands.count(bed) } 静默{ cands.count(quiet) } 事件声 {ev1 in cands}/{ev2 in cands}')

    b2 = SceneBuilder(_FakeWorld(
        sound_design={'底噪': bed, '事件声': [ev1, ev2], '静默': quiet}), day=1)
    picked = [b2._pick_ambient_line() for _ in range(6)]
    got = [x for x in picked if x]
    ok('D3 ★★★ 连取 6 次**没有一条重复**（"挑没用过的，全用过就不写"）',
       len(got) == len(set(got)) and len(got) >= 4, repr(picked))

    b3 = SceneBuilder(_FakeWorld(sound_design={'底噪': '', '事件声': [],
                                               '静默': quiet}), day=1)
    ok('D4 ★★ 成对：**只有静默**时也给得出来（不是整段哑掉）',
       quiet in b3._ambient_candidates(), repr(b3._ambient_candidates()[:3]))

    b4 = SceneBuilder(_FakeWorld(sound_design={}), day=1)
    ok('D5 ★★ 成对：**没有声音设计**就退回罐头池，不编（不许凭空造声）',
       not any(c in {bed, ev1, ev2, quiet} for c in b4._ambient_candidates()), '')


# ══════════════════════════════════════════════════════════
#  E  近似重复："换个说法说同一件事"也算说过
# [EN] Near-duplicates: "the same thing in different words" also counts as said
# ══════════════════════════════════════════════════════════
def group_e() -> None:
    from display.scene_builder import SceneBuilder, near_same, norm_line

    ok('E1 ★★ `norm_line` 只去标点不去字（"我不知道。"与"我不知道"同句）',
       norm_line('我不知道。') == '我不知道', repr(norm_line('我不知道。')))
    ok('E2 ★★ 成对：**少一个"不"必须不同**（判成同句就正好把意思反过来）',
       not near_same('我不知道', '我知道'), '')

    ok('E3 ★★★ 换语序的复读判得出来'
       '（「你那车份儿打算拖到什么时候？」→「车份儿打算拖到什么时候」）',
       near_same('你那车份儿打算拖到什么时候？', '车份儿打算拖到什么时候'), '')
    ok('E4 ★★ 成对：**真的换了一句**不误伤',
       not near_same('你那车份儿打算拖到什么时候？', '今儿个天不错。'), '')
    ok('E5 ★★★ 成对：**短应答不判**（"嗯"/"走吧"本来就是反复说的话，'
       '判成重复会把正常应答也拦掉）',
       not near_same('嗯', '嗯。') and not near_same('走吧', '走吧。'), '')

    b = SceneBuilder(_FakeWorld(), day=1)
    b._remember_line('老程', '你那车份儿打算拖到什么时候？')
    ok('E6 ★★★ 护栏认得出近似复读（`already_said` → 主循环才会去问"是不是非说不可"）',
       b.already_said('老程', '车份儿打算拖到什么时候') is True, '')
    ok('E7 ★★ 成对：**别人**说了同一句不算他说过',
       b.already_said('祥子', '车份儿打算拖到什么时候') is False, '')
    ok('E8 ★★ 成对：**放行过的**那句不再拦（`allow_repeat` 仍然有效）',
       (lambda: (b.allow_repeat('老程', '车份儿打算拖到什么时候'),
                 b.already_said('老程', '车份儿打算拖到什么时候') is False)[1])(), '')

    src = ''
    try:
        from sim.loop import RunLoop
        src = inspect.getsource(RunLoop._repeat_hit)
    except Exception as e:                                       # noqa: BLE001
        src = f'（取不到：{e!r}）'
    # ⚠ 认的是**判等那一行**（`_near_same(prev`），不是"源码里出现过 near_same" ——
    #   import 那一行还在时，把判等退回精确比对，后者照样为真（反例法 ⑫ 抓出来的）。
    # [EN] Judge the **comparison line** (`_near_same(prev`), not "near_same appears somewhere":
    # [EN] with the import line still present, reverting the comparison to exact equality would
    # [EN] still look green (caught by mutation ⑫).
    ok('E9 ★★★ prose 模式那条路也用**同一个**近似判定（两处各写一套迟早一边松一边紧）',
       '_near_same(prev' in src, src[-160:])


# ══════════════════════════════════════════════════════════
#  F  雪国的教训
# [EN] The Snow Country lessons
# ══════════════════════════════════════════════════════════
def group_f() -> None:
    from util.prompts import strip_comments, template

    tail, src_name = template('agent_decide_tail', '（内置）')
    body = strip_comments(tail)
    ok('F1 ★★★ 指令段里禁了"替读者点题"（"该响的 X 没响"这一类解释）'
       '—— 这就是《雪国》被扣的那一条',
       '替读者点题' in body and '该响的敲门声没有响' in body, src_name)
    ok('F2 ★★★ 指令段里写了"说半句，不说整句"（评委：「她的话应当总是半句」）',
       '说半句' in body, '')
    # ★★★ 2026-10-18：措辞从"每一拍要留下一处不同"改成了"**这一拍要往前走一步**，
    #   但不必每句都在走"——同一个诉求（评委那条「戏没有转折就停住」），
    #   但要**成对**判，否则就是"为了改红把判据放了水"：
    #     · F3 守诉求本身：一拍必须有一处真的变了；
    #     · F3b 守新增的边界：允许"不推进的句子"（用户 2026-10-18 的诉求）。
    #   两条**必须同时为真** —— 只剩 F3 就是回到"每句都在推进"的老毛病，
    #   只剩 F3b 就是放水成"什么都不用发生"。
    # [EN] ★★★ 2026-10-18: the wording changed from "every beat must leave a change" to "this beat
    # [EN] moves one step forward, but not every sentence has to move" -- same requirement (the
    # [EN] judge's "the scene stalls"), but it must be judged **in pairs**, otherwise changing the
    # [EN] criterion to go red is just letting it off:
    # [EN]   · F3 holds the requirement: a beat must change **one** thing;
    # [EN]   · F3b holds the new boundary: non-advancing sentences are allowed (2026-10-18 ask).
    # [EN] Both must hold -- F3 alone is the old "every sentence advances", F3b alone is "nothing
    # [EN] has to happen".
    ok('F3 ★★★ 指令段里仍然要求"**这一拍要往前走一步**"（一拍有一处真的变了）'
       '—— 评委原话「戏没有转折就停住」',
       ('往前走一步' in body or '有一处不同' in body) and '有一处' in body, '')
    ok('F3b ★★★ 成对：同时明写"**不必每句都在走**"（一拍里其余的句子可以不推进）'
       '—— 用户原话「句子太简练、过于追求故事推进」',
       '不必每句都在走' in body, '')

    # 声音设计：静默必须写成"事实"，不许写成"该响的…没响"
    try:
        from crew.agents import Sound
        ssrc = inspect.getsource(Sound.work)
    except Exception as e:                                       # noqa: BLE001
        ssrc = f'（取不到：{e!r}）'
    ok('F4 ★★★ 声音设计的提示词要求静默写"**听见了什么没有**"这个事实，'
       '并明写禁止"该响的 X 没有响"（它会原样进正文）',
       '听见了什么没有' in ssrc and '不许' in ssrc and '该响的 X 没有响' in ssrc,
       ssrc[-160:])
    ok('F4b ★★★ 声音设计还要求**三样别写同一件东西** ——'
       '实测一轮里底噪/事件声/静默全在写火，评委点名"意象重复"',
       '三样别都写同一件东西' in ssrc, '')

    # `_voice_rules()` 的**产物**（行为判，不是看源码含字符串）
    from agent.core import Agent
    from world.state import PersonState

    class _W:
        style_card = {'句长': '短句，句与句之间留白'}

    a = Agent.__new__(Agent)
    a.ps = PersonState(name='叶子', identity='旅馆帮工', personality='安静',
                       catchphrase="只叫'先生'，说话像唱歌")
    a.world = _W()
    got = a._voice_rules()
    ok('F5 ★★★ `_voice_rules()` 真的把**口癖**写进去了，并且把它当**限制**（不是装饰）',
       "只叫'先生'" in got and '限制' in got, got[:160])
    ok('F6 ★★ 而且带上了"说半句/不许自我剖白"这条可执行禁令',
       '说半句' in got and '自我剖白' in got, got[-120:])
    ok('F6b ★★★ 口癖还明写了**一场最多用一次**（不然模型会每句都套 ——'
       '实测一场戏里「你这个人哪」被套了 5 次，正是这条缝）',
       '一场最多用一次' in got, got[:200])

    a2 = Agent.__new__(Agent)
    a2.ps = PersonState(name='某人', identity='', personality='')
    a2.world = type('_W2', (), {'style_card': {}})()
    ok('F7 ★★ 成对：**口癖与风格都拿不到 ⇒ 空串**（提示词与从前一字不差，'
       '不许凭空多出一段套话）',
       a2._voice_rules() == '', repr(a2._voice_rules()))


# ══════════════════════════════════════════════════════════
#  G  端到端：真跑一次 `decide()`，**抓发出去的 prompt**
# [EN] End-to-end: really run `decide()` and capture the prompt that goes out
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


def _capture_decide_prompt() -> str:
    """造一个演员，喂两拍历史（他自己说的 + 他自己做的），真跑 `decide()`，返回 prompt。

    ★ 这一组存在的理由（MEMORY 里那条"prompt 里写了 ≠ 生效"）：C 组查的是 AST，
      只证明"代码里有这段"；真正要证的是**拼出来的那一坨**里有它。
      实测教训：`是否拼接`写对了、但值算成空串，AST 照样绿。
    [EN] Why this group exists (the MEMORY rule "written in the prompt != in effect"): group C only
    [EN] inspects the AST, i.e. "the code contains this"; what must be proven is that the **assembled
    [EN] prompt** contains it. Measured lesson: the concatenation can be correct while the value
    [EN] computes to an empty string, and the AST check stays green.
    """
    import asyncio

    from agent import core as AC
    from agent.core import Agent
    from world.state import GameTime, PersonState, WorldState

    w = WorldState()
    w.scene = '临河茶肆'
    w.clock = GameTime()
    ps = PersonState(name='主角', location='临河茶肆', role='前台',
                     identity='茶肆掌柜', personality='话少，先听后说',
                     catchphrase='说话必带"罢了"', current_goal='把账上的窟窿弄清')
    w.people['主角'] = ps
    w.recent_lines = [
        # ⚠ 动作要放**够老**：`recent_text` 只给最后 6 条，动作若还在那 6 条里，
        #   `[你上一拍做的]` 会**故意不加**（已经在眼前了，说了就是重复）。
        #   这正是它的设计：只在"被挤出窗口"时才补一条。
        # [EN] ⚠ The action must be **old enough**: `recent_text` only shows the last 6, and if the
        # [EN] action is still among them, `[你上一拍做的]` is **deliberately omitted** (it is already
        # [EN] in view, restating it would be the duplication itself). That is the design: add the
        # [EN] dedicated line only when it has been squeezed out of the window.
        {'who': '主角', 'text': '把凳子往后挪了半尺。', 'kind': 'act',
         'to': '', 'place': '临河茶肆'},
        {'who': '主角', 'text': '把茶壶提到灶上温着。', 'kind': 'act',
         'to': '', 'place': '临河茶肆'},
        {'who': '伙计', 'text': '外头雪停了。', 'kind': 'speak', 'to': '', 'place': '临河茶肆'},
        {'who': '伙计', 'text': '茶凉了。', 'kind': 'speak', 'to': '', 'place': '临河茶肆'},
        {'who': '账房', 'text': '这页翻过去罢。', 'kind': 'speak', 'to': '', 'place': '临河茶肆'},
        {'who': '账房', 'text': '算盘珠子拨了两下。', 'kind': 'act', 'to': '', 'place': '临河茶肆'},
        {'who': '伙计', 'text': '灯芯短了。', 'kind': 'speak', 'to': '', 'place': '临河茶肆'},
        {'who': '账房', 'text': '明儿再说。', 'kind': 'speak', 'to': '', 'place': '临河茶肆'},
        {'who': '主角', 'text': '上回那笔钱我没动。', 'kind': 'speak',
         'to': '', 'place': '临河茶肆'},
    ]
    a = Agent(ps, _FakeDB(), w)
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


def _capture_decide_prompt_with_asks() -> str:
    """同 `_capture_decide_prompt`，但历史里**真有**"问了两次、两次都被岔开"。

    ⚠ 为什么要另起一个夹具而不是改上面那个：那个夹具被 G 组用着
      （G2/G3 断言里带着特定台词），改动会连带弄红别的东西。
      "同一件事一个夹具一个用途" —— 这也是"两处实现"那条纪律的正面用法。
    [EN] Same as `_capture_decide_prompt` but the history **really contains** "asked twice, dodged
    [EN] twice". A separate fixture because the other one is used by group G with specific lines.
    """
    import asyncio

    from agent import core as AC
    from agent.core import Agent
    from world.state import GameTime, PersonState, WorldState

    w = WorldState()
    w.scene = '临河茶肆'
    w.clock = GameTime()
    ps = PersonState(name='主角', location='临河茶肆', role='前台',
                     identity='茶肆掌柜', personality='话少，先听后说',
                     current_goal='把账上的窟窿弄清')
    w.people['主角'] = ps
    w.recent_lines = [
        {'who': '主角', 'text': '把凳子往后挪了半尺。', 'kind': 'act',
         'to': '', 'place': '临河茶肆'},
        {'who': '主角', 'text': '这笔账你打算怎么算？', 'kind': 'speak',
         'to': '', 'place': '临河茶肆'},
        {'who': '伙计', 'text': '外头雪停了。', 'kind': 'speak', 'to': '', 'place': '临河茶肆'},
        {'who': '主角', 'text': '那笔账到底怎么算？', 'kind': 'speak',
         'to': '', 'place': '临河茶肆'},
        {'who': '伙计', 'text': '灯芯短了。', 'kind': 'speak', 'to': '', 'place': '临河茶肆'},
    ]
    a = Agent(ps, _FakeDB(), w)
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


def _capture_decide_prompt_with_address(*, single: bool = False) -> str:
    """真跑 `decide()`，返回发出去的 prompt。历史里对方用过 `single` 控制几种称呼。

    ⚠ 为什么要另起夹具：`_capture_decide_prompt` 被 G 组用着（断言里带着特定台词），
      改动会连带弄红别的东西。"一个夹具一个用途"。
    [EN] Run `decide()` for real and return the prompt. A separate fixture because the other one is
    [EN] used by group G with specific lines.
    """
    import asyncio

    from agent import core as AC
    from agent.core import Agent
    from world.state import GameTime, PersonState, WorldState

    w = WorldState()
    w.scene = '临河茶肆'
    w.clock = GameTime()
    ps = PersonState(name='某甲', location='临河茶肆', role='前台',
                     identity='茶肆掌柜', personality='话少，先听后说',
                     current_goal='把账上的窟窿弄清')
    w.people['某甲'] = ps
    w.people['某乙'] = PersonState(name='某乙', location='临河茶肆', role='客')
    seq = [('客人，您坐。', '某乙')]
    if not single:
        seq += [('客人，您喝么。', '某乙'), ('客人，您这话少。', '某乙'),
                ('某乙先生，您还没休息呀？', '某乙')]
    for txt, to in seq:
        w.note_line('某甲', txt, kind='speak', to=to)
    a = Agent(ps, _FakeDB(), w)
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


def group_g() -> None:
    p = _capture_decide_prompt()
    ok('G1 ★★★ 真跑 `decide()` 一次，抓到了 prompt（不是空跑）',
       len(p) > 500, f'{len(p)} 字')
    ok('G2 ★★★ 发出去的 prompt 里**真有**「他自己说过的话」那一段，'
       '而且是他那句原话（2026-10-19 改名：`[你在这场说过的话]`，取 4 句）',
       ('[你在这场说过的话]' in p or '[你上一拍说的]' in p)
       and '上回那笔钱我没动' in p, p[-260:])
    ok('G3 ★★★ 发出去的 prompt 里**真有** `[你上一拍做的]`，'
       '而且是生产侧写进来的 `act`（这一条就是 2026-10-17 那次假绿的现场复核）',
       '[你上一拍做的]' in p and '把凳子往后挪了半尺' in p, p[-260:])
    # ⚠ 必须在**这一段之内**找口癖：人格卡里也有一行 `口癖：…`，
    #   只在整份 prompt 里找，那段没挂上也照样绿（反例法 ⑰ 抓出来的）。
    # [EN] ⚠ Look for the tic **inside this block**: the persona card also has a `口癖: ...` line,
    # [EN] so searching the whole prompt stays green even when the block never mounted (caught by ⑰).
    _i = p.find('[你怎么开口]')
    _blk = p[_i:_i + 400] if _i >= 0 else ''
    ok('G4 ★★★ 发出去的 prompt 里**真有** `[你怎么开口]`，且**这一段里**带着这个人的口癖'
       '（"说话必带罢了"）—— 口癖在离输出最近的地方再说一遍',
       bool(_blk) and '说话必带' in _blk, _blk[:160])
    # ★★ 2026-10-19：参照物换成**输出格式说明**。
    #   原来判"口癖 ⓘ 在「你上一拍说的」之后"，而口癖已前置到规则区（见 C5），
    #   那个比较不再成立。要守的事没变：**人格卡不许贴在输出跟前**
    #   （贴太近，模型会把"这个人是什么样的"抄成"他这样做了"）。
    # [EN] ★★ 2026-10-19: the reference point is now the **output-format instruction**. The original
    # [EN] compared against "what you said last beat", which no longer holds after the tic moved to
    # [EN] the rules zone (see C5). The thing being guarded is unchanged: **the persona card must not
    # [EN] sit next to the output** (too close and the model copies "what he is like" into "what he did").
    _i_tic = p.find('[你怎么开口]')
    _i_json = p.find('请以 JSON 回答')
    ok('G5 ★★ 成对：`[你怎么开口]` 排在**输出格式说明之前**（人格卡不许贴在输出跟前，'
       '贴太近模型会把"他是什么样的"抄成"他这样做了"）',
       _i_tic >= 0 and _i_json >= 0 and _i_tic < _i_json,
       f'口癖@{_i_tic} / 格式@{_i_json}')
    _j = p.find('[你在这场已经做过的]')
    _blk2 = p[_j:_j + 300] if _j >= 0 else ''
    ok('G6 ★★★ 发出去的 prompt 里**真有** `[你在这场已经做过的]`，'
       '且摆出了这一场他做过的两件事（防"隔一拍换个说法再做一遍"）',
       bool(_blk2) and '把凳子往后挪了半尺' in _blk2 and '把茶壶提到灶上' in _blk2,
       _blk2[:200])


# ══════════════════════════════════════════════════════════
#  H  **同一拍内部**的重复动作（《雪国》repeat-fix 实测那一条）
# [EN] Duplicate actions **within one beat** (measured in the Snow Country repeat-fix run)
# ══════════════════════════════════════════════════════════
class _FakeAgent:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeAction:
    def __init__(self, verb: str, detail: str = '', target: str = '') -> None:
        self.verb = verb
        self.detail = detail
        self.target = target
        self.dialogue = ''
        self.inner_thought = ''


def group_h() -> None:
    from display.scene_builder import SceneBuilder

    b = SceneBuilder(_FakeWorld(), day=1)
    me = _FakeAgent('驹子')
    a1 = _FakeAction('emote', '头发散了，脸上还带着酒气，眼神有些迷离地看着岛村。')
    a2 = _FakeAction('emote', '头发散了，脸上带着酒气，眼神有些迷离地看着岛村。')
    ok('H1 ★★★ 同一拍里**只差一个字的同一段动作** ⇒ 第二条丢掉'
       '（实测就是这一条进了正文：读者看到同一段描写写了两遍）',
       b._worth_emitting(me, a1) is True and b._worth_emitting(me, a2) is False, '')

    b2 = SceneBuilder(_FakeWorld(), day=1)
    a3 = _FakeAction('interact', '把碗推远了一点，手指在桌沿上敲了两下。')
    a4 = _FakeAction('interact', '起身走到窗边，把窗子推开一条缝，看外头的雪。')
    ok('H2 ★★ 成对：**真的换了一件事**照样写（不许一刀切）',
       b2._worth_emitting(me, a3) is True and b2._worth_emitting(me, a4) is True, '')

    b3 = SceneBuilder(_FakeWorld(), day=1)
    a5 = _FakeAction('emote', '蹲下。')
    a6 = _FakeAction('emote', '蹲下，')
    ok('H3 ★★ 成对：短动作（几字）**不按近似判**，只按一字不差判 ——'
       '短句本来就会反复出现，按相似度判会把正常动作全拦掉',
       b3._worth_emitting(me, a5) is True and b3._worth_emitting(me, a6) is True, '')

    b4 = SceneBuilder(_FakeWorld(), day=1)
    b4._last_action['驹子'] = '说：你这个人哪。'
    a7 = _FakeAction('emote', '说你这个人哪，声音很轻，被雪吸掉了，也没抬眼。')
    ok('H4 ★★ 成对：**不能拿上一句台词当"上一个动作"比**'
       '（否则"接着他那句话做动作"会被当成复读）',
       b4._worth_emitting(me, a7) is True, '')

    # ── H5/H6 `细节` 写成第三人称时，别让名字出现两遍 ──
    from display import script as S

    b5 = SceneBuilder(_FakeWorld(), day=1)
    a8 = _FakeAction('emote', '驹子伏在火钵边上，头发散了，脸上还带着酒气。')
    ents = b5._entries_for(_FakeAgent('驹子'), a8, S.PRESENT, '')
    texts = [e.text for e in ents if e.kind == S.ACTION]
    ok('H5 ★★★ `细节` 以**自己的名字**开头 ⇒ 词条里不再重复（'
       '否则正文写成「驹子驹子伏在…」—— 实测就这么进过一次正文）',
       bool(texts) and not any(t.startswith('驹子') for t in texts),
       repr(texts))

    b6 = SceneBuilder(_FakeWorld(), day=1)
    a9 = _FakeAction('interact', '把火钵往岛村那边推了推，炭灰飘起来一点。')
    ents2 = b6._entries_for(_FakeAgent('驹子'), a9, S.PRESENT, '')
    texts2 = [e.text for e in ents2 if e.kind == S.ACTION]
    ok('H6 ★★ 成对：**本来就不带名字的细节一字不动**（不许顺手改写动作）',
       texts2 == ['把火钵往岛村那边推了推，炭灰飘起来一点。'], repr(texts2))

    # ── H7 章节头里的日期不许写两遍（《雪国》复测评委点名的第 5 条）──
    from util.timefmt import GameTime, format_game_clock

    gt = GameTime(day=1, minutes=23 * 60)
    heads = {cal: format_game_clock(gt, cal, with_day=False)
             for cal in ('auto', 'modern', 'daycount', 'ganzhi')}
    ok('H7 ★★★ 只给时段的那一档**不含"第N天/日"**（否则章节头会写成'
       '「第 1 天 · 第1天·子时」）',
       all(('第' not in v and '日' not in v) for v in heads.values()), repr(heads))
    # ⚠ 光有那一档不够：**调用点**也得用上它（判据只测函数不算数 —— 反例法 ㉒ 抓出来的）。
    # [EN] ⚠ Having the option is not enough: the **call site** must use it (testing only the
    # [EN] function does not count -- caught by mutation ㉒).
    _loop = _read('sim/loop.py')
    _heads = []
    try:
        for n in ast.walk(ast.parse(_loop)):
            if isinstance(n, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == 'head' for t in n.targets):
                src = ast.unparse(n.value)
                # ★ 2026-10-26：**只收"往章节头里接时钟"的那几条**。
                #   以前收"任何含『第』的 head 赋值"，而全库还有别的地方拼
                #   `head = f'## 第 {int(day)} 天'`（不带时钟）⇒ 那一条必然没有
                #   `with_day=False`，`all(...)` 就永远红。
                #   判据真正要守的是：**只要这里接了时钟，就必须用"不带年号"的那一档**
                #   （否则章节头会写成「第 1 天 · 第1天·子时」）。
                # [EN] ★ 2026-10-26: **only collect the ones that put a clock in the chapter head**.
                # [EN] It used to collect any `head = ...` containing 「第」, and the codebase has
                # [EN] another `head = f'## 第 {int(day)} 天'` (no clock) => that one can never carry
                # [EN] `with_day=False` and `all(...)` was permanently red.
                # [EN] What the criterion really guards: **whenever a clock is concatenated here it
                # [EN] must be the no-year variant** (otherwise the head reads 「第 1 天 · 第1天·子时」).
                if 'clock_display' in src:
                    _heads.append(src)
    except SyntaxError:
        _heads = []
    ok('H7b ★★★ 章节头**真的调了** `clock_display(with_day=False)`（调用点也要钉）',
       bool(_heads) and all('with_day=False' in h for h in _heads),
       ' / '.join(_heads)[:200])
    ok('H8 ★★ 成对：默认那一档**照旧带日期**（UI 上还需要它）',
       format_game_clock(gt, 'auto') == '第1天·子时'
       and format_game_clock(gt, 'modern') == '第1日 23:00', '')

    # ── H9：**每一个日历选项都得真的改变显示**（假旋钮）──
    #   实测（2026-10-18 审计）：`CALENDAR_DISPLAY` 的 `opt` 里有 `regnal`（年号），
    #   而 `format_game_clock` 只有在**外部传年号**时才用那一支，全库**没有任何地方传**
    #   ⇒ 用户在「天机」里选"年号"，界面永远还是"第1天·辰时"，而一切看起来正常。
    #   ⇒ 判据：对 `opt` 里每个值，显示结果必须**与默认档不同**；否则它就是假旋钮，
    #     要么删选项，要么把来源补上。
    # [EN] ── H9: **every calendar option must actually change the display** (fake knob) ──
    # [EN] Measured (2026-10-18 audit): `CALENDAR_DISPLAY` offered `regnal` (era name), but
    # [EN] `format_game_clock` only uses that branch when an era name is **passed in**, and nothing
    # [EN] in the codebase passes one => picking "era name" changes nothing and looks fine.
    # [EN] => criterion: each value in `opt` must yield a display **different from the default**.
    from config import SPEC

    opts = list((SPEC.get('CALENDAR_DISPLAY') or {}).get('opt') or [])
    plain = format_game_clock(gt, 'auto')
    dead = [c for c in opts if c != 'auto' and format_game_clock(gt, c) == plain]
    ok('H9 ★★★ `CALENDAR_DISPLAY` 的**每个选项都真的改变了显示**'
       '（"年号"那一档曾经是假旋钮：选了它界面还是"第1天·辰时"）',
       bool(opts) and not dead, f'选项 {opts} / 选了等于没选 {dead}')


def group_i() -> None:
    """I：**一个人要有自己的一条线**（2026-10-19 第五轮）。

    用户原话：「一个人从头到尾说的话之间没有任何关系，不是一系列有关联的事件
    连续下来，还是不同的事情胡乱跳」。

    实测（第 3 轮产物）：同一人物相邻两句 **65% 换了话题**，中间只隔 1 句别人的话。
    根因是演员层**每拍只接上一句**（`[刚才]` 6 条），手上没有"我这条线走到哪了"。

    ⚠ 这跟 A–H 组的"复读"是**一对相反的病**：
      复读 = 同一句换着说；散线 = 每句都对得上，连起来不是一件事。
      只判"别重复"会把模型推向"换话题"（正解变成了躲重复），所以必须**成对**加这条。
    [EN] I: **one person needs one thread**. Measured in round 3: 65% of a character's adjacent
    [EN] lines changed topic. The cause is that the actor layer only answers the previous line.
    [EN] ⚠ This is the **opposite** disease of A-H ("repeating"): repeating = the same line
    [EN] reworded; scattered = each line answers the last, but together they are not one thing.
    [EN] Judging only "don't repeat" pushes the model toward "change topic", so this must be added
    [EN] as a pair.
    """
    from agent import core as AC
    import inspect

    src = inspect.getsource(AC.Agent.decide)
    ok('I1 ★★★ 演员提示词里有 `[你在这场说过的话]` 这一块（不是只有"上一拍" ——'
       '两句只看得见"刚说了什么"，看不见"我这条线在往哪走"）',
       '[你在这场说过的话]' in src, '')
    ok('I2 ★★★ 给的是**四句**不是两句（`last_own_lines(…, 4)`）',
       'last_own_lines(self.name, 4)' in src, '')
    ok('I3 ★★★ 而且要求"从你自己上一句往前走"，并给了**四种走法**'
       '（逼到底 / 改口 / 退让 / 摊开）—— 只写"要有线"模型不知道线怎么走',
       all(k in src for k in ('逼到底', '改口', '退让', '摊开')), '')
    ok('I4 ★★★ 明写这四种**都不是换话题**（否则模型会把"往前走"理解成"说下一件事"）',
       '都不是换话题' in src, '')
    # 成对：复读那条不许被这次改动冲掉
    ok('I5 ★★★ 成对：**原样重复仍是复读**那句还在'
       '（加了"线"不许把"别重复"顶掉 —— 两条是一对，缺一条就荡到另一头）',
       '原样重复是复读' in src, '')

    # ── 外置模板与内置镜像必须同口径（只改一份 = 没改）──
    from util.prompts import strip_comments, template
    tpl, _src = template('agent_decide_tail', '')
    body = strip_comments(tpl or '')
    ok('I6 ★★★ 外置模板 `prompts/agent_decide_tail.txt` 里也有这条（规则区）',
       '你要有自己的一条线' in body and '逼到底' in body, f'{len(body)} 字')
    ok('I7 ★★★ 内置镜像（`agent/core.py` 的 f-string）里也有 —— '
       '只改外置那份，没有用户目录的机器上等于没改',
       '你要有自己的一条线' in src or '你要有自己的一条线' in inspect.getsource(
           AC.Agent), '')

    # ── 导演层：事件要接着上一件（不是"别重复"就够）──
    from director import engine as DE
    dsrc = inspect.getsource(DE.DirectorEngine._inject_event)
    ok('I8 ★★★ 导演注入事件时**不许另开一件无关的**'
       '（只写"不要重复"⇒ 模型的正解变成"换一件不一样的事"，'
       '于是「送酒→送茶→送水→送酒壶」连着四件 —— 第 3 轮实测）',
       '也不许另开一件无关的事' in dsrc, '')
    ok('I9 ★★★ 而且指明了**怎么接**：这一件是上一件的「后果 / 下一步 / 代价」',
       '后果 / 下一步 / 代价' in dsrc, '')
    ok('I10 ★★ 成对：**"不要重复"那条还在**（两条一起才叫"有关联的事件"）',
       '不要重复' in dsrc, '')
    ok('I11 ★★ 给了**具体的反例**（又有人送了一样东西来），不是抽象口号',
       '又有人送了一样东西来' in dsrc, '')

    # ── 加了"线"之后模型找到的新偷懒：**用同一套语气标记同一个人**（行为判）──
    # 实测（`snow_thread1`）：「声音含混」6 次、「偏头」5 次、「含混」8 次、
    # 「是啊」7 次、「先生」17 次 —— 上一轮这些全是 0–1 次。**改动引入的新病**。
    # [EN] The model's new shortcut after "you need your own thread": tagging one person with the
    # [EN] same tone. Measured: 声音含混 x6, 偏头 x5 ... while the previous round had 0-1.
    class _W:
        def own_actions(self, n, k=4):
            return ['偏头看她，声音含混，说了半句就停下', '声音含混地应了一声',
                    '又是声音含混地开口，眼睛没抬', '偏头看她，声音含混',
                    '偏头，声音含混']

        def last_own_lines(self, n, k=2):
            return ['是啊，你坐过来些', '是啊，你接着说下去']

    class _P:
        catchphrase = ''
        name = '某甲'

    ag = AC.Agent.__new__(AC.Agent)
    ag.world = _W()
    ag.ps = _P()
    line = ag._repeat_phrase_line()
    ok('I12 ★★★ 反复用的语气短语被**点名 + 给了次数**'
       '（"你已经用了 5 次「声音含混」" —— 与口癖配额同一条纪律：可数的事实才管用）',
       '声音含混' in line and '5 次' in line, line[:80].replace('\n', ' / '))
    ok('I13 ★★★ 而且给了**三条替换办法**（手上的动作 / 别人看见的样子 / 干脆不写语气）'
       '—— 只说"别再用"模型会换成一个更空的形容词',
       '手上的动作' in line and '不写语气' in line, '')
    class _W2:
        def own_actions(self, n, k=4):
            return ['偏头看她', '把盏子推了推']

        def last_own_lines(self, n, k=2):
            return ['嗯。']

    ag2 = AC.Agent.__new__(AC.Agent)
    ag2.world = _W2()
    ag2.ps = _P()
    ok('I15 ★★★ 成对：**用得少时不报**（1–2 次是正常用词，报了就是噪音）',
       ag2._repeat_phrase_line() == '', repr(ag2._repeat_phrase_line()[:40]))

    # ★★★ **五字口癖**（第六轮实测）：3–4 字滑窗切不出「你这个人哪」，
    #   于是它真跑里出现 **5 次**而配额一声不响。窗口必须含 5 字，
    #   且停用开头只管 3 字窗口（「你这个人哪」首字是「你」）。
    # [EN] **Five-character tics**: 3-4 char windows cannot cut 「你这个人哪」, so it appeared five
    # [EN] times in the real run while the quota stayed silent. Windows must include 5, and the
    # [EN] stop-head list must only apply to 3-char windows.
    # ⚠ 夹具里**不许让口癖紧跟标点**（2026-10-19 第十轮）：若写成
    #   「你这个人哪，连句…」，整段计数会把它当成一个 5 字整段抓走 ——
    #   于是"滑窗 5 字"那一层被整段计数覆盖，M22/M23 都失效（变异没改行为）。
    #   ⇒ 让它落在**长句中间**（整段 > 8 字，滑窗才够得着）。
    # [EN] ⚠ The fixture must **not** put the tic immediately before punctuation: then the
    # [EN] whole-segment counter catches it as a 5-char segment, the sliding window becomes
    # [EN] redundant, and M22/M23 change no behaviour. Keep it **inside a long run** (> 8 chars).
    class _W5:
        def own_actions(self, n, k=4):
            return ['你这个人哪连句真话也不肯说', '你这个人哪就知道看着我笑']

        def last_own_lines(self, n, k=2):
            return ['你这个人哪酒都凉了', '你这个人哪就不能哄我一句']

    ag5 = AC.Agent.__new__(AC.Agent)
    ag5.world = _W5()
    ag5.ps = _P()
    _l5 = ag5._repeat_phrase_line()
    ok('I37 ★★★ **五字**口癖被点名（3–4 字窗口切不出「你这个人哪」，'
       '真跑里它出现 5 次而配额一声不响）',
       '你这个人哪' in _l5 and '4 次' in _l5,
       _l5.split('\n')[1] if '\n' in _l5 else '（没报）')

    # ── **两字口癖**（第十轮真跑抓出来的）──
    # `snow_v10` 里岛村 7 句台词有 5 句以「是啊」开头、驹子 10 句以「客人，您」开头，
    # 而配额**一声不响**：`{3,}` 只留 >=3 字的连续中文段，而「是啊。」后面紧跟句号
    # ⇒ 那段只有 **2 个字** ⇒ 直接被正则丢掉。**最短最规整的口癖恰恰是 2 字。**
    # [EN] **Two-character tics** (caught by a real run in round ten): five of Island's seven lines
    # [EN] opened with 「是啊」 and ten of Jouji's with 「客人，您」, while the quota stayed silent --
    # [EN] `{3,}` keeps only 3+ char runs, and 「是啊。」 is followed by a full stop, so that run is
    # [EN] **2 chars** and gets dropped. The shortest, most regular tics are exactly 2 chars.
    class _W8:
        def own_actions(self, n, k=4):
            return []

        def last_own_lines(self, n, k=4):
            return ['是啊。您这手，练过弦吧。', '是啊。雪，看不看都一样。',
                    '是啊。你方才那句话说到一半。', '是啊。……你先暖暖手。']

    ag8 = AC.Agent.__new__(AC.Agent)
    ag8.world = _W8()
    ag8.ps = _P()
    _l8 = ag8._repeat_phrase_line()
    ok('I41 ★★★ **两字**口癖（「是啊。」后面紧跟句号）必须被点名 —— '
       '`{3,}` 会把它整段丢掉，而这类恰恰是最常见的一种',
       '是啊' in _l8 and '4 次' in _l8,
       _l8.split('\n')[1] if '\n' in _l8 else '（没报）')
    ok('I42 ★★★ 计数口径是"**在几段里出现过**"，不是"切出几次"'
       '（否则同一个短语既等于整段、又被 4 字滑窗切到 ⇒ 数两遍，5 次报成 6 次）',
       '声音含混」已经出现 **5 次**' in line,
       [x for x in line.split('\n') if '声音含混' in x][:1])
    # 成对：正常的一两句短句**不许被当成口癖**（否则每人每拍都在被报警）
    class _W9:
        def own_actions(self, n, k=4):
            return []

        def last_own_lines(self, n, k=4):
            return ['是啊。', '外头雪停了。']

    ag9 = AC.Agent.__new__(AC.Agent)
    ag9.world = _W9()
    ag9.ps = _P()
    ok('I43 ★★★ 成对：**只出现一两次**的短句不算口癖（报了就是噪音，模型会当背景忽略）',
       ag9._repeat_phrase_line() == '',
       repr(ag9._repeat_phrase_line()[:40]))

    # ── **上一件还在办就不派新的**（第十一轮：目标漂移的硬机制）──
    # 用户报的现象：同一个人一晚上被派了三件毫无关系的事。
    # 根因是 `ps.mission = what` **无条件覆盖**；以前只有一句提示词，而提示词治不了。
    # [EN] **Do not assign a new task while the previous one is still running** (round eleven: the
    # [EN] hard mechanism for goal drift). Root cause: unconditional `ps.mission = what`.
    from sim.loop import RunLoop as _RL2
    from world.state import WorldState as _WS5

    def _running(rows: list[tuple[str, str, str]], mission: str) -> bool:
        lp2 = _RL2.__new__(_RL2)
        lp2.world = _WS5()
        for who, txt, kind in rows:
            lp2.world.note_line(who, txt, kind=kind)
        return lp2._mission_still_running('某甲', mission)

    _M = '让某甲说定在此地再消磨几日'
    ok('I50 ★★★ **还在办**就判 True（言行里提到那件事的关键词）',
       _running([('某甲', '再消磨几日也无妨。', 'speak'),
                 ('某甲', '说着又坐了下来。', 'act')], _M), '')
    ok('I51 ★★★ 成对：**已经停了**判 False（否则派活会被永久冻结，人物不再接新活）',
       not _running([('某甲', '雪停了。', 'speak'),
                     ('某甲', '把头转开。', 'act')], _M), '')
    ok('I52 ★★ 边界：**没有旧目标**时判 False（从没派过活的人必须能接到第一件）',
       not _running([], ''), '')
    # ★★ 2026-10-26：**扫的对象跟着代码搬家了**。那套循环从 `_maybe_dispatch` 抽成了
    #   `_apply_missions`（`_maybe_dispatch` 只剩一句委托）。判据要问的事没变：
    #   **生产路径到底有没有用 `_mission_still_running` 去挡？**
    # [EN] ★★ 2026-10-26: **the scanned target moved with the code**. The loop was extracted from
    # [EN] `_maybe_dispatch` into `_apply_missions`. The question is unchanged: **does the
    # [EN] production path actually gate on `_mission_still_running`?**
    _apply_src = inspect.getsource(_RL2._apply_missions)
    ok('I53 ★★★ **生产路径真的用了它**'
       '（只写方法没人调 = 回到"无条件覆盖"）',
       '_mission_still_running(' in _apply_src and 'kept.append(name)' in _apply_src, '')
    # ⚠ **不能数源码里的字符串**：那个赋值在注释里也被引用了（"根因就在下面那一行
    #   `ps.mission = what`"），于是 `count == 1` 恒假 —— 判据红得莫名其妙。
    #   这与本项目"别用源码含字符串当判据"是同一条，只是这次栽在**计数**上。
    #   ⇒ 改成 AST 数**真语句**。
    # [EN] Do **not** count the string in the source: the assignment is also quoted inside a
    # [EN] comment ("the root cause is the line below `ps.mission = what`"), so `count == 1` is
    # [EN] always false. Same rule as "never judge by source text", this time on a count. Count real
    # [EN] `ast.Assign` statements instead.
    import ast as _ast

    def _assign_count(method) -> int:
        tree = _ast.parse(_textwrap.dedent(inspect.getsource(method)))
        n = 0
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Assign):
                for t in node.targets:
                    if (isinstance(t, _ast.Attribute) and t.attr == 'mission'
                            and isinstance(t.value, _ast.Name) and t.value.id == 'ps'):
                        n += 1
        return n

    # ⚠ 原来是"`ps.mission = what` 恰好 1 处"。抽出 `_apply_missions` 之后多了
    #   "导演点名强制换活"那条分支（也是 `ps.mission = what`），于是变成 2 处 ——
    #   那是对的。**数条数的判据一改代码就假红**，所以改成钉**机制**：
    #   要保住的其实是"被跳过的人**在赋值之前就 `continue` 走了**"。
    # [EN] ⚠ It used to be "exactly one `ps.mission = what`". After the extraction a second branch
    # [EN] appeared (the director forcing a new task), so there are two -- and that is correct.
    # [EN] **Counting criteria go falsely red on any refactor**, so pin the **mechanism** instead:
    # [EN] what must hold is "a skipped person `continue`s **before** any assignment".
    def _kept_continues(method) -> bool:
        tree = _ast.parse(_textwrap.dedent(inspect.getsource(method)))
        for node in _ast.walk(tree):
            # ⚠ `body` 与 `orelse` 都要看：那句 `continue` 通常在 `if ... else:` 的
            #   `else` 分支里（"没卡死 ⇒ 记下来 ⇒ 跳过他" 这条）。
            # [EN] ⚠ Check both `body` and `orelse`: the `continue` usually sits in the `else`
            # [EN] branch ("not stuck => remember him => skip him").
            for body in (getattr(node, 'body', None), getattr(node, 'orelse', None)):
                if not isinstance(body, list):
                    continue
                if _kept_then_continue(body):
                    return True
        return False

    def _kept_then_continue(body: list) -> bool:
        for i, stmt in enumerate(body):
            call = getattr(stmt, 'value', None)
            fn = getattr(call, 'func', None)
            if (isinstance(fn, _ast.Attribute) and fn.attr == 'append'
                    and isinstance(fn.value, _ast.Name) and fn.value.id == 'kept'):
                rest = body[i + 1:]
                if rest and isinstance(rest[0], _ast.Continue):
                    return True
        return False

    ok('I54 ★★★ 被跳过的人**在赋值之前就 continue 走了**（保留旧目标；'
       '没有这一步就等于"无条件覆盖"）',
       _assign_count(_RL2._apply_missions) >= 1 and _kept_continues(_RL2._apply_missions),
       f'{_assign_count(_RL2._apply_missions)} 处赋值 / continue '
       f'{"有" if _kept_continues(_RL2._apply_missions) else "没有"}')

    # ── **称呼一致性**（第十一轮，用户点名的最严重的一条）──
    # 用户原话：「驹子从称'客人'改口称'岛村先生'——这个转变**没有心理或事件上的铺垫**。
    # 称呼是人际关系最直接的反映，它的变化必须有情感逻辑支撑，
    # 否则就是机械的文字游戏。」
    # 可数形状：**同一个说话人、同一个对象、用了 N 种称呼**。
    # [EN] **Address consistency** (round eleven; the user's most severe complaint). Countable shape:
    # [EN] **one speaker, one addressee, N different terms of address.**
    from world.state import WorldState as _WS4

    def _addr(seq: list[tuple[str, str]]) -> list[tuple[str, str, int]]:
        w4 = _WS4()
        for txt, to in seq:
            w4.note_line('某甲', txt, kind='speak', to=to)
        return w4.address_ledger('某甲')

    _sw = _addr([('客人，您坐。', '某乙'), ('客人，您喝么。', '某乙'),
                 ('客人，您这话少。', '某乙'), ('某乙先生，您还没休息呀？', '某乙')])
    ok('I44 ★★★ **改口**被账本记下来了（「客人」3 次、「名字+先生」1 次，'
       '两项都在 —— 只记一种就等于没看见改口）',
       any(w == '客人' and n == 3 for _t, w, n in _sw)
       and any(w == '某乙先生' and n == 1 for _t, w, n in _sw),
       str(_sw))
    ok('I45 ★★★ 成对：**一直用同一个称呼**只记一条（否则每个人每拍都会被说"换过称呼"）',
       _addr([('客人，您坐。', '某乙'), ('客人，您喝么。', '某乙')])
       == [('某乙', '客人', 2)],
       str(_addr([('客人，您坐。', '某乙'), ('客人，您喝么。', '某乙')])))
    # ★★★ 这两条守的是"名字+称谓要算一个称呼" —— 试了两次才做对（见 `detect_address` 注释）
    ok('I46 ★★★ **名字+称谓算一个称呼**（「某乙先生」不许被切成「先生」，'
       '否则改口这件事本身就被抹掉了）',
       _WS4.detect_address('某乙先生，您还没休息呀？', ('某甲', '某乙')) == '某乙先生',
       _WS4.detect_address('某乙先生，您还没休息呀？', ('某甲', '某乙')))
    ok('I47 ★★ 成对：**没叫人**的句子不记称呼（"是啊。雪，看不看都一样。"里没有称呼）',
       _WS4.detect_address('是啊。雪，看不看都一样。', ('某甲', '某乙')) == '',
       repr(_WS4.detect_address('是啊。雪，看不看都一样。', ('某甲', '某乙'))))
    # ⚠⚠ **必须行为判**：第一版判的是"源码里有没有这几句话"，而变异把
    #   `address_ledger` 换成 `[]` 之后**文案还在** ⇒ 判据照绿（M32 抓出来的）。
    #   这是本项目反复踩的坑（源码含字符串当判据）—— 第三次了。
    #   ⇒ 真跑一次 `decide()`，读**发出去的 prompt**。
    # [EN] ⚠⚠ **Must be a behaviour check**: the first version judged "does the source contain these
    # [EN] lines", and mutation M32 (replacing `address_ledger` with `[]`) **kept the wording** => the
    # [EN] criterion stayed green. Third time this project has hit that trap. Run `decide()` for real
    # [EN] and read the assembled prompt.
    _p_addr = _capture_decide_prompt_with_address()
    ok('I48 ★★★ **发出去的 prompt** 里真有称呼账本，并给了**两条出路**'
       '（有事垫着再改口 / 没事就还用原来的）和最坏的一种',
       '[你对他的称呼：已经换过了]' in _p_addr
       and '先把那件事写出来，再改口' in _p_addr
       and '读者会以为漏读了一段' in _p_addr
       and '你叫「' in _p_addr,
       _p_addr[_p_addr.find('[你对他的称呼'):][:70].replace('\n', ' / ')
       if '[你对他的称呼' in _p_addr else '（没挂上）')
    ok('I49 ★★★ 成对：**只用过一个称呼**时这段不出现（否则每拍都在说废话）',
       '[你对他的称呼：已经换过了]' not in _capture_decide_prompt_with_address(single=True),
       '')

    ok('I16 ★★★ 这一条**真的挂进了动态层**（写了方法没人调 = 死代码）',
       '_repeat_phrase_line()' in inspect.getsource(AC.Agent.decide), '')

    # ── **你这一场要办的事**（第五轮第二次修）──
    # 只写"你要有自己的一条线"是**抽象要求**，实测两次真跑一次 50%、一次退回 35%。
    # 看材料才看清是结构问题：每一拍都有别人在说话，他每拍都在答**别人新提的问题**
    # ⇒ 话题被牵着走。所以要**点名那一件事**，并明写"被打断也要拐回来"。
    # [EN] "You need your own thread" is **abstract**: two runs gave 50% then 35%. The structure
    # [EN] is that every beat someone else asks something and he answers **that**. So **name the
    # [EN] one thing** and say "come back to it after being interrupted".
    ok('I17 ★★★ 演员提示词里有 `[你这一场要办的事]`，内容是导演派的活（`_mission_line`）'
       '—— 点名那一件事，比"你要有自己的一条线"这种抽象要求管用',
       '[你这一场要办的事]' in inspect.getsource(AC.Agent.decide)
       and '_mission_line()' in inspect.getsource(AC.Agent.decide), '')
    ok('I18 ★★★ 明写"**答完要拐回来**"（结构上的病就是：被打断就跟着别人的问题走了）',
       '答完要拐回来' in inspect.getsource(AC.Agent.decide), '')
    ok('I19 ★★★ 而且说清"拐回来不是重复提问，而是更近一步"'
       '（否则它会把刚才那句再问一遍 —— 那正是被复读护栏拦的那件事）',
       '拐回来的说法不是重复提问' in inspect.getsource(AC.Agent.decide), '')

    # ── **账本**：问过、没被正面答的那件事（第五轮第三次修，本轮真正的解）──
    # 上面两块还是"要求"，这一块是**事实**。实测同一组提示词两次：50% → 35%，
    # 时灵时不灵 ⇒ 光有要求不够，必须有可数的账。
    # [EN] **Ledger**: asked but never answered. The two blocks above are still "requests"; this
    # [EN] is a **fact**. Two runs of the same prompts gave 50% then 35% => requests alone are not
    # [EN] enough.
    from world.state import WorldState as _WS
    w = _WS()
    for who, t in (('某甲', '你觉得我是不是个可信的人？'), ('某乙', '这雪下得真不小。'),
                   ('某甲', '我到底可不可信？'), ('某乙', '嗯，你坐过来些。')):
        w.note_line(who, t, kind='speak')
    asks = w.open_asks('某甲', 2)
    ok('I20 ★★★ 账本算得出"同一件事问了 2 次、两次都被人岔开"'
       '—— 这是"一系列有关联的事件"的可数形状：一个问题悬在那里没被解决',
       bool(asks) and max(a['times'] for a in asks) == 2,
       repr(asks[0] if asks else None))
    w2 = _WS()
    w2.note_line('某甲', '账本你见过吗？', kind='speak')
    w2.note_line('某乙', '账本在柜子里。', kind='speak')
    ok('I21 ★★★ 成对：**真答了的不会被算成没答**'
       '（误判方向必须是"宁可不报" —— 多报一条假"没答"，模型会去追问一件已经答过的事）',
       w2.open_asks('某甲', 2) == [], repr(w2.open_asks('某甲', 2)))
    # ⚠⚠ **必须行为判**：第一版这里判的是"源码里有没有这串字"，
    #   而反例法 M12（把 `open_asks` 的结果换成 `[]`）**照样绿** —— 文案还在，
    #   账本永远算不出来。这是本项目反复踩的坑（源码含字符串当判据）。
    #   ⇒ 真跑一次 `decide()`，读**发出去的那一坨**。
    # [EN] ⚠⚠ **Must be a behaviour check**: the first version judged "does the source contain
    # [EN] this string", and mutation M12 (replacing `open_asks` with `[]`) **stayed green** --
    # [EN] the wording remains while the ledger can never compute. Run `decide()` for real and
    # [EN] read the assembled prompt.
    p_led = _capture_decide_prompt_with_asks()
    ok('I22 ★★★ **发出去的 prompt** 里真有账本那一段，'
       '并给了四种把答案逼出来的办法（替他说 / 降条件 / 说到最狠 / 自己先答）',
       '[你问过、一直没被正面答的那件事]' in p_led
       and '把答案替他说出来' in p_led and '问过 **2 次**' in p_led,
       p_led[p_led.find('[你问过'):][:90].replace('\n', ' / ')
       if '[你问过' in p_led else '（没挂上）')
    ok('I23 ★★ 成对：账本只在**真有过**时才挂（正常对话不啰嗦）'
       '—— 没有"问了没答"的夹具里，这一段不出现',
       '[你问过、一直没被正面答的那件事]' not in _capture_decide_prompt(), '')

    # ── **"非说不可"的三个条件真的被查了**（第五轮）──
    # 改前是**无条件放行**：只要"重问一次还是这句"就放。实测 `snow_thread3`：
    # 同一句隔十句原样重现。而 `_REPEAT_CTX` 里给模型的三条标准，代码一条都没查。
    # [EN] The three "must say" conditions are **really checked**. Before it passed
    # [EN] unconditionally; measured: the same line resurfaced ten lines later while none of the
    # [EN] three criteria in `_REPEAT_CTX` was ever verified in code.
    from sim.loop import RunLoop as _RL
    from world.state import WorldState as _WS2

    def _why(rows: list[tuple[str, str]], me: str, line: str) -> str:
        lp = _RL.__new__(_RL)
        lp.world = _WS2()
        for who, txt in rows:
            lp.world.note_line(who, txt, kind='speak')
        return lp._must_repeat_reason(me, line)

    L_ASK = '你就不能多留些日子吗？'
    # ⚠ 夹具**不许带问号/疑问词**：第一版用的是「你说什么？我没听清。」，
    #   而那句会**同时**被"在追问"那条命中 ⇒ 删掉 `_DEAF` 之后判据照样绿
    #   （反例法 M14：变异没改行为，绿是应该的）。要测 `_DEAF` 就只留它一条路。
    # [EN] ⚠ The fixture must **not contain a question mark or interrogative**: the first version
    # [EN] used "你说什么？我没听清。" which is **also** caught by the "pressing" branch, so
    # [EN] deleting `_DEAF` stayed green (mutation M14 changed no behaviour).
    ok('I24 ★★★ 对方**没听清** ⇒ 算"非说不可"（这是三条标准里唯一最硬的那条）',
       bool(_why([('驹子', L_ASK), ('岛村', '我没听清。')], '驹子', L_ASK)),
       _why([('驹子', L_ASK), ('岛村', '我没听清。')], '驹子', L_ASK))
    ok('I25 ★★★ 对方**在追问** ⇒ 也算（被追问时重说一遍是正常的）',
       bool(_why([('驹子', '你看我是不是好人？'), ('岛村', '你为什么这么问？')],
                 '驹子', '你看我是不是好人？')), '')
    # ★★★ 这条是核心：改之前它会放行，正是"同一句隔十句原样重现"的来源
    ok('I26 ★★★ **对方岔开了话题** ⇒ 不算"非说不可"（改之前这里会无条件放行 —— '
       '`snow_thread3` 里同一句隔十句原样重现就是它放过去的）',
       _why([('驹子', L_ASK), ('岛村', '这雪下得真不小。')], '驹子', L_ASK) == '',
       repr(_why([('驹子', L_ASK), ('岛村', '这雪下得真不小。')], '驹子', L_ASK)))
    ok('I27 ★★ 边界：**后面没人说话**也不算（不能拿"没人应"当放行理由）',
       _why([('驹子', '随你吧。'), ('岛村', '嗯。')], '驹子', '随你吧。') == '', '')
    # ── **回避要有上限**（第六轮，用户贴的分析第二条：「转变缺乏铺垫」）──
    # 用户原话：「反复"没听清"（至少三次）…突然"捕捉到一点"，这个转变**缺乏铺垫**」。
    # 可数形状：**用同一种方式躲了 N 次，第 N+1 次突然变了，中间没有台阶**。
    # [EN] **Dodging must be bounded** (round six; the user's second complaint: "the shift has no
    # [EN] setup"). Countable shape: dodged N times the same way, then changed with no step.
    w4 = _WS()
    for who, txt in (('某甲', '你说什么？我没听清。'), ('某乙', '我问你是不是好人'),
                     ('某甲', '不知道，说不好。'), ('某乙', '你就说一句'),
                     ('某甲', '算了，夜深了。')):
        w4.note_line(who, txt, kind='speak')
    _dn, _ds = w4.dodge_count('某甲', 12)
    ok('I33 ★★★ 账本算得出"同一个人用同一种方式躲了 3 次"，并记住每次怎么躲的',
       _dn == 3 and len(_ds) == 3, f'{_dn} 次：{_ds}')
    ok('I34 ★★★ 成对：**正常回答不算躲**（否则每个人都被判成在躲，提示词天天报警）',
       w4.dodge_count('某乙', 12)[0] == 0, repr(w4.dodge_count('某乙', 12)))
    ok('I35 ★★★ 提示词里明写"躲到第 3 次**必须表态**"，并给了三种表态方式'
       '（承认 / 拒绝 / 改口）—— 只写"别一直躲"模型会再躲一次',
       '躲到第 3 次' in inspect.getsource(AC.Agent.decide)
       and all(k in inspect.getsource(AC.Agent.decide) for k in ('承认', '拒绝', '改口')), '')
    ok('I36 ★★ 而且明写"不许再没听清第四次"（点的是用户实测的那个具体写法）',
       '第四次' in inspect.getsource(AC.Agent.decide), '')

    # ── **派活要接着上一件**（第五轮，结构性根因）──
    # 实测同一晚三次派给同一个人的活：`让陪伴显得自然妥帖` / `护住谈笑余温` /
    # `达成对那声姐的安然受用` —— 三件毫无关系，而且全是**氛围描写，人物演不出来**。
    # 人物的线每 8 拍被剪断一次，下游怎么改都没用。
    # [EN] **Assignments must continue the previous one** (structural root cause). Measured: three
    # [EN] unrelated assignments to one person in one night, all mood descriptions a character
    # [EN] cannot act on. His thread is cut every 8 beats; downstream fixes cannot help.
    from director import engine as _DE
    import asyncio as _aio

    seen: dict = {}
    _real_ask = _DE.ask

    async def _fake_ask(tier, msgs, **kw):
        seen['p'] = msgs[-1]['content']

        class _R:
            ok = True
            value = {'派活': [{'人物': '某甲', '要什么': '让他说出能留几天'}]}
            notes = []
        return _R()

    class _DB:
        def recent_events(self, n=8):
            return [{'content': '有人递了一壶酒'}]

    from world.state import PersonState as _PS, WorldState as _WS3
    w3 = _WS3()
    w3.people['某甲'] = _PS(name='某甲', location='某屋')
    eng = _DE.DirectorEngine(w3, _DB())
    _DE.ask = _fake_ask
    try:
        _aio.run(eng.dispatch(['某甲']))
        first_has = '上一次你派给他们的活' in seen['p']
        _aio.run(eng.dispatch(['某甲']))
        second = seen['p']
    finally:
        _DE.ask = _real_ask
    ok('I29 ★★★ 第二次派活时，**上一次派的那件**被递回给导演了'
       '（第一次没有 = 对；第二次有 = 交接链接上了）',
       (not first_has) and '上一次你派给他们的活' in second and '让他说出能留几天' in second,
       f'第一次有块={first_has} 第二次有块={"上一次你派给他们的活" in second}')
    ok('I30 ★★★ 而且明写"新派的一件必须是上面那件的**下一步**"'
       '（只说"参考上次"不够 —— 模型会礼貌地换一件）',
       '必须是上面那件的下一步' in second, '')
    ok('I31 ★★★ 而且**点名禁止氛围描写**，正反例都用实测派出来的原话'
       '（"要达成对门外静立的毫不刻意的好奇"那种，人物演不出来）',
       '不是场景气氛' in second and '毫不刻意的好奇' in second and '让他说出能留几天' in second, '')
    # ── **配角不是 NPC**（第七轮）──
    # 用户原话：「叶子几乎只在做两件事：送东西和提醒…更像一个推动场景转换的"NPC"」。
    # 真跑的派活日志给出根因：三次全是「送罢酒候在廊下守着那人」的换说法 ——
    # **导演只收到一个名字**，不知道她是谁、想要什么。
    # [EN] **Supporting roles are not NPCs** (round seven). The user: "Yoko only brings things and
    # [EN] reminds people". The dispatch log shows why: all three assignments were rewordings of
    # [EN] "wait in the corridor after delivering the wine" -- **the director only got a name**.
    _w6 = _WS3()
    _w6.people['某甲'] = _PS(name='某甲', location='某屋',
                            identity='旅馆帮佣的姑娘', personality='话少，眼睛亮',
                            goal='想让那件事有个了结')
    _eng6 = _DE.DirectorEngine(_w6, _DB())
    _seen6: dict = {}
    _seq6 = ['让某甲送罢酒候在廊下守着那人',
             '让某甲在廊下守着那人，任屋内言语飘过',
             '让某甲廊下守着，任那句话飘过耳']
    _hit6: list[bool] = []
    _real6 = _DE.ask
    for _v in _seq6:
        async def _f6(tier, msgs, **kw):
            _seen6['p'] = msgs[-1]['content']
            _vv = _v

            class _R6:
                ok = True
                value = {'派活': [{'人物': '某甲', '要什么': _vv}]}
                notes = []
            return _R6()
        _DE.ask = _f6
        _aio.run(_eng6.dispatch(['某甲']))
        _hit6.append('连着 2 次' in _seen6['p'])
    _DE.ask = _real6
    ok('I38 ★★★ 派活时**把人设递进去了**（身份 / 性子 / 他自己想要的）—— '
       '只给一个名字，导演就只能派"送东西、退下、歇着"',
       '他们各是谁' in _seen6['p'] and '旅馆帮佣的姑娘' in _seen6['p']
       and '自己想要' in _seen6['p'], '')
    ok('I39 ★★★ **连着两次派同一件事**要被抓出来，第 3 次必须换'
       '（三次一字不相等，但分明是同一件 —— 所以按**共享二元组个数**判，不按字面相等）',
       _hit6 == [False, False, True], str(_hit6))
    # ⚠ 这是本轮最容易判错的一条：**相似率判不出来**（同义换说法只有 0.33–0.40），
    #   而"共享二元组个数"能把两者分开（同一件事 7–8 个 / 不同的事 3 个）。
    #   ⇒ 成对判：**不同的事不许误报**。
    # [EN] The easiest thing to get wrong this round: a **ratio** cannot separate them
    # [EN] (rewordings score 0.33-0.40), while the **count of shared bigrams** can (7-8 vs 3).
    # [EN] So judge the other side: different things must not be flagged.
    _eng7 = _DE.DirectorEngine(_WS3(), _DB())
    _seen7: dict = {}
    # ⚠ 必须派**三次**：检测要"前两次"作历史，只派两次时第二次的 hist 只有 1 条，
    #   任何门槛都不会触发 ⇒ 变异（门槛降到 1）也没反应（反例法 M27 抓出来的）。
    # [EN] Must dispatch **three** times: the check needs the previous two, and on the second call
    # [EN] history holds only one entry, so no threshold fires (mutation M27 caught this).
    _seq7 = ['让某乙把酒杯递向某甲', '让某乙从某甲处讨来那句回话',
             '让某乙把窗子推开些']
    _real7 = _DE.ask
    for _v in _seq7:
        async def _f7(tier, msgs, **kw):
            _seen7['p'] = msgs[-1]['content']
            _vv = _v

            class _R7:
                ok = True
                value = {'派活': [{'人物': '某甲', '要什么': _vv}]}
                notes = []
            return _R7()
        _DE.ask = _f7
        _aio.run(_eng7.dispatch(['某甲']))
    _DE.ask = _real7
    ok('I40 ★★★ 成对：**不同的事不许误报**'
       '（"把酒杯递向甲"与"从甲处讨来那句回话"只共享 3 个二元组 = 全是人名，'
       '门槛 5 正好分开；判松了会每轮都喊"必须换"，那就成了噪音）',
       '连着 2 次' not in _seen7['p'], '')

    ok('I32 ★★ 成对：同一件事推了 3 次还没结果时，要求派**逼出结果的那一步**'
       '（否则会变成每 8 拍换个说法重复派同一件）',
       '能把它逼出结果的那一步' in second, '')

    ok('I28 ★★★ 生产路径：`_review_repeat` 真的调了它，'
       '**不再无条件 `_free_repeat`**（只写方法没人调 = 回到改之前）',
       '_must_repeat_reason(' in inspect.getsource(_RL._review_repeat)
       and 'if _why:' in inspect.getsource(_RL._review_repeat), '')


def main() -> int:
    for fn in (group_a, group_b, group_c, group_d, group_e, group_f, group_g, group_h,
               group_i):
        try:
            fn()
        except Exception as e:                                   # noqa: BLE001
            ok(f'{fn.__name__} 执行失败', False, repr(e))
    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['ok'] = not bad
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n复读/防重演验证：{len(checks) - len(bad)}/{len(checks)}', flush=True)
    return 0 if not bad else 2


if __name__ == '__main__':
    raise SystemExit(main())
