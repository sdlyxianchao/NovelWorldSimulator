# -*- coding: utf-8 -*-
"""验证：**剧本审读承担「语义级重复」与「越界」**（2026-10-18）。

用户原话：「剧本审读承担语义级别重复和越界判定这条路你彻底实施下去」。

为什么要走这条路（前一轮五轮实测的结论）
----------------------------------------
文本层的逐字重复已经由三处护栏管住了（台词 `_said` / 动作 `_last_action` /
环境句池）。剩下的是**语义重复**与**硬约束越界**，两件事都"读得通、但读起来是假的"：

  · 语义重复：「你觉得我是个什么样的人？」→「我是个好人吧？」；
    「叶子端酒壶站门口」→「一壶酒从半开纸门推进来」；
    「眼盯他侧脸」→「眼没离他脸」→「盯他嘴」。
    文字相似度只有 0.3–0.6，`near_same`（0.86）抓不到。
  · 越界：红线上写着"她的声音只用来唤人、传话"，她却在门外成句问人来不来；
    铁律写着"不许写明确的心里想"，正文里出现"她想：我要说吗"。

而这两件事**只有"读懂意思"才判得出**。演员提示词加句子已经到头了
（豆包单次决策 ~100 token，提示词 7000+ 字），所以搬到这里：
**上屏之前**由独立的一个职位判，判完能改写 —— 位置比提示词硬。

这一支钉住的行为（**每条都要能红**，见 `developers/mutate_review_semantic.py`）：

  A **候选扫描**（零成本）：程序先挑"可能是同一件事"的配对，模型只判真假。
    为什么要拆开：便宜模型的输出预算 100–200 token，"自己通读 40 行找重复"
    实测是漏的；而"这几对里哪一对真是同一件事"它判得准。
  B **类别判定**：`重复` / `越界` / `其他`。三类处置不同，不能一刀切。
  C **提示词**：铁律、人物红线、候选配对都要真的递进去（真跑一次抓 prompt）。
  D **处置**：改写优先；**重复改不动就放行**（删掉会留空白）；整拍全拦 ⇒ 全部放行。
  E **记账**：按类别计数，进日志与《剧本审读.md》。

跑法：.venv\\Scripts\\python.exe tools/verify_review_semantic.py
产出：assets/screenshots/review_semantic_report.json

English:
Verification: **script review takes on "semantic repetition" and "out of bounds"** (2026-10-18).
User: "implement the path where script review handles semantic-level repetition and boundary
judgment thoroughly".
Why this path (conclusion of the previous five measured runs): verbatim repetition is already
covered by three guards; what remains is **semantic** repetition (similarity 0.3-0.6, invisible to
`near_same`) and **hard-constraint violations** (a character red line or an iron rule broken).
Both can only be judged by *understanding*, and adding sentences to the actor prompt has hit its
ceiling (Doubao emits ~100 tokens against a 7000+ character prompt), so it moves here: before
anything goes on screen, an independent role judges it -- and can rewrite it.
Groups: A candidate scan (zero cost), B category, C prompt (captured by really running `work()`),
D disposition, E accounting. Run: .venv\\Scripts\\python.exe tools/verify_review_semantic.py
"""
from __future__ import annotations

import asyncio
import ast
import inspect
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

REPORT = APP_DIR / 'assets' / 'screenshots' / 'review_semantic_report.json'
report: dict = {'checks': [], 'ok': False}


def ok(name: str, cond: bool, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:400]})
    print(f'{"✓" if cond else "✗"} {name}' + (f'  [{detail}]' if detail else ''), flush=True)
    return bool(cond)


def _read(rel: str) -> str:
    """读源码。⚠ 一律兜住 `OSError`（并行回归时 Windows 独占打开 ⇒ PermissionError）。"""
    try:
        return (APP_DIR / rel).read_text(encoding='utf-8')
    except OSError:
        return ''


#: 真实语料（取自《雪国》五轮实测的正文，不是编的）。
#: 左边"已上屏"，右边"这一拍新写的"。
TRUE_DUPS: tuple[tuple[str, str], ...] = (
    ('你这人哪……', '你这个人哪，倒是吭一声啊。'),
    ('驹子伏在火钵边上，头发散了，脸上还带着酒气，眼神有些迷离地看着岛村。',
     '驹子伏在火钵边上，头发散了，脸上带着酒气，眼神有些迷离地看着岛村。'),
    ('叶子脚步放得很轻，走到纸门外停下，双手交叠在腹前。',
     '叶子脚步放得很轻，走到纸门外停下，双手交叠在身前。'),
)
#: 成对：**真的不相干**的句子（相似度 < 0.15）
NOT_DUPS: tuple[tuple[str, str], ...] = (
    ('夜里雪光冷白，落在席上。', '她把杯子推近他膝半寸，指压杯沿。'),
    ('叶子：先生，要出去看雪吗？', '岛村：终于能好好歇会儿了。'),
)
#: ★ 已知的**假阳性**：形状像、其实是问答。程序会把它当候选挑出来（0.42 > 门槛 0.40），
#: 这一对**必须在 prompt 里被明确排除**（"问答不算重复"），由模型判掉。
#: 留在这里是因为它是"为什么必须让模型判"的直接证据（见 `DUP_SEED_THR` 的注释）。
# [EN] ★ A known **false positive**: it looks alike but is a question and its answer. The program
# [EN] proposes it (0.42 > 0.40), and the prompt must explicitly rule it out ("Q&A is not
# [EN] repetition"). It stays here because it is the direct evidence for "why the model must judge".
QA_PAIR: tuple[str, str] = ('叶子：先生，要出去看雪吗？', '驹子：出去看雪？这大半夜的，冷死了。')


# ══════════════════════════════════════════════════════════
#  A  候选扫描：程序挑、模型判
# [EN] A  Candidate scan: the program proposes, the model judges
# ══════════════════════════════════════════════════════════
def group_a() -> None:
    from crew import review as R

    ok('A1 ★★ `crew/review.dup_candidates` 存在（挑候选的唯一入口）',
       callable(getattr(R, 'dup_candidates', None)), '')

    # 真实重复对：每一对都必须被挑出来（**召回**是这一层的职责）
    missed = []
    for prev, new in TRUE_DUPS:
        got = R.dup_candidates(
            [{'序号': 1, '类型': 'dialogue' if '哪' in new else 'action',
              '谁': '驹子', '文本': new}],
            [f'〔{"dialogue" if "哪" in new else "action"}·驹子〕{prev}'])
        if not got:
            missed.append((prev[:14], new[:14]))
    ok('A3 ★★★ 真实语料里的语义重复**一条都别漏**（五轮实测挑出来的那三对）',
       not missed, f'漏了 {missed}' if missed else '3/3')

    # 成对：**真的不相干**的不能算候选（否则 40 行历史全是噪音）
    fp = []
    for prev, new in NOT_DUPS:
        got = R.dup_candidates(
            [{'序号': 1, '类型': 'dialogue', '谁': '岛村', '文本': new}],
            [f'〔dialogue·叶子〕{prev}'])
        if got:
            fp.append((prev[:14], new[:14], got[0]['相似']))
    ok('A4 ★★★ 成对：**真的不相干**的句子不能被挑成候选（否则 40 行历史全是噪音）',
       not fp, f'误挑 {fp}' if fp else '2/2 干净')

    # 已知假阳性（问答）：**允许**被挑出来（这是召回），但必须带上"不同人"这条线索
    got = R.dup_candidates(
        [{'序号': 1, '类型': 'dialogue', '谁': '驹子', '文本': QA_PAIR[1]}],
        [f'〔dialogue·叶子〕{QA_PAIR[0]}'])
    ok('A4b ★★★ 已知假阳性（问答对）**允许**被挑出来 —— 但候选行必须带着 '
       '`同一个人=False`，让模型一眼能判掉（这是"必须让模型判"的直接证据）',
       bool(got) and got[0].get('同一个人') is False,
       json.dumps(got[:1], ensure_ascii=False)[:160])

    # 批内互比：同一拍里两条几乎一样（实测 repeat-fix2 的"叶子送酒两次"）
    got = R.dup_candidates([
        {'序号': 1, '类型': 'action', '谁': '叶子', '文本': '叶子端着酒壶推门进来，放在门槛内侧。'},
        {'序号': 2, '类型': 'action', '谁': '叶子', '文本': '叶子端着酒壶推门进来，把酒放在门槛内。'},
    ], [])
    ok('A5 ★★★ **同一批内部**也要互比（实测有一整拍里"叶子送酒"出现两次，'
       '两条都在同一批 —— 只跟历史比永远看不出来）',
       bool(got) and got[0].get('同批') is True and int(got[0].get('序号')) == 2,
       json.dumps(got[:1], ensure_ascii=False)[:180])

    # 成对：只跟**同类**比（动作 ↔ 台词不互比）
    got = R.dup_candidates(
        [{'序号': 1, '类型': 'action', '谁': '驹子',
          '文本': '驹子伏在火钵边上，头发散了，脸上还带着酒气。'}],
        ['〔dialogue·驹子〕驹子伏在火钵边上，头发散了，脸上还带着酒气。'])
    ok('A6 ★★ 成对：**动作只跟动作比、台词只跟台词比**'
       '（动作句与台词句本来就不会"重复"；混着比只会多出噪音）',
       not got, json.dumps(got, ensure_ascii=False)[:140])

    # 短句不判：`嗯`/`走吧`/`我不知道` 这类本来就会反复出现
    #   ⚠ 用 4–5 个字的例子：1–2 个字的（"嗯"）连 `look_alike` 的下限都够不着，
    #    那样即使把这道闸拆了判据也照样绿（变异"没改行为 ⇒ 绿是应该的"）。
    got = R.dup_candidates(
        [{'序号': 1, '类型': 'dialogue', '谁': '驹子', '文本': '我不知道呀。'}],
        ['〔dialogue·驹子〕我不知道。'])
    ok('A7 ★★ 成对：**短应答不进候选**（"嗯""走吧""我不知道"本来就是反复说的，'
       '挑成"重复"会把正常应答也判掉）',
       not got, json.dumps(got, ensure_ascii=False)[:140])
    ok('A7b ★★ 成对：同一对里**稍长一点就进候选**（说明 A7 卡的是长度，不是恰好没算出来）',
       bool(R.dup_candidates(
           [{'序号': 1, '类型': 'dialogue', '谁': '驹子',
             '文本': '我不知道该说什么才好。'}],
           ['〔dialogue·驹子〕我不知道该说什么好。'])), '')

    # 条目多的时候要**限量**（预算只有 100~200 token）
    items = [{'序号': i, '类型': 'action', '谁': '驹子',
              '文本': f'驹子伏在火钵边上，头发散了，脸上带着酒气，第{i}次抬眼。'}
             for i in range(1, 9)]
    got = R.dup_candidates(items, [], max_pairs=4)
    ok('A8 ★★ 候选**限量**（`max_pairs`）—— 一个条目挂五条会把模型的预算挤光',
       len(got) <= 4, f'{len(got)} 条')

    ok('A9 ★★★ 相似度是"**召回**门槛"而不是"判决门槛"'
       '（门口那一段真假混在一起，所以必须交给模型判）',
       not (R.look_alike(TRUE_DUPS[0][0], TRUE_DUPS[0][1]) < R.DUP_SEED_THR)
       and not (R.look_alike(NOT_DUPS[0][0], NOT_DUPS[0][1]) >= R.DUP_SEED_THR),
       f'真对 {R.look_alike(*TRUE_DUPS[0]):.2f} / 假对 {R.look_alike(*NOT_DUPS[0]):.2f}'
       f' / 门槛 {R.DUP_SEED_THR}')


# ══════════════════════════════════════════════════════════
#  B  类别判定
# [EN] B  Category
# ══════════════════════════════════════════════════════════
def group_b() -> None:
    from crew import review as R

    ok('B1 ★★★ `重复` 认得出（模型会写成"重复（同一动作两次）"这种自由文本）',
       R.category_of({'类别': '重复（同一动作两次）'}) == R.CAT_DUP
       and R.category_of({'类别': '复读'}) == R.CAT_DUP, '')
    ok('B2 ★★★ `越界` 认得出（"踩了人物红线" / "违反铁律" 都得认）',
       R.category_of({'类别': '越界：踩了人物红线'}) == R.CAT_BOUND
       and R.category_of({'类别': '违反铁律'}) == R.CAT_BOUND, '')
    ok('B3 ★★ 成对：**认不出的归其他**（宁可漏不可误杀 —— 不能因为类别写歪就拦下）',
       R.category_of({'类别': '人话不通'}) == R.CAT_OTHER
       and R.category_of({}) == R.CAT_OTHER
       and R.category_of({'类别': ''}) == R.CAT_OTHER, '')

    # ── B4–B8：**心声必须是第一人称**（2026-10-18 某次续跑实测）──
    #   台账第 21 拍：审读判对了越界（"这是 A 的心里话，B 的视角里不可能出现"），
    #   它给的 `改成` 却是「A 歪着头问我："B 哥，你盯着那纸看半天了。"」——
    #   第三人称旁白 + 转述台词，**比原文更糟**，而 `rule_check` 对 aside 没有专属规则
    #   ⇒ 这句更糟的改写原样上屏。
    # ⚠ **夹具里的人名必须是虚构通用的**（甲/乙/"某人"）：写真人名会撞
    #   `verify_generic_project`（"代码里不许出现某部具体作品的专名"），
    #   而且模型会被真人名带偏。夹具要的是**形态**，不是谁。
    # [EN] The fixture names must be **generic placeholders**: real names trip
    # [EN] `verify_generic_project`, and the point here is the *shape*, not who.
    bad_aside = '某乙歪着头问我：“甲哥，你盯着那纸看半天了。”'
    ok('B4 ★★★ 心声写成"**人名 + 动作**"（第三人称旁白）⇒ 规则层判坏',
       R.rule_check(bad_aside, kind='aside') != '', '')
    ok('B5 ★★★ 心声里**转述别人的话**（"问我：""他对我说"）⇒ 也判坏',
       R.rule_check('甲对我说：“喝茶。”', kind='aside') != ''
       and R.rule_check('他问："这字谁写的。"', kind='aside') != '', '')
    # 成对：合法的第一人称**一条都不许误杀**（否则心声全被拦，比重复更糟）
    # [EN] Paired: no legitimate first-person line may be killed (blocking all inner voice is
    # [EN] worse than repetition).
    good = ('这甲看着旧账，怎么跟丢了魂似的？', '他要是问起来，我就说醉了。',
            '我看着他垂下眼。', '这字怎么像我写的。', '不能问，掌柜交代过别提。',
            '我记得。', '茶凉了。')
    killed = [x for x in good if R.rule_check(x, kind='aside')]
    ok('B6 ★★★ 成对：**合法的第一人称一句都不误杀**（含"他/她"开头的想法）',
       not killed, f'误杀 {killed}')
    # 成对：这条规则**不许**影响台词与动作
    ok('B7 ★★ 成对：台词与动作**不受**这条规则影响（"某乙歪着头问"当台词是正常的）',
       R.rule_check(bad_aside, kind='dialogue') == ''
       and R.rule_check(bad_aside, kind='action') == '', '')
    # 三类各用一套规则（防止以后又退回"只有两套"）
    ok('B8 ★★★ 三类**各用一套**规则（台词/心声/动作）——'
       '"台词多查半截话、心声多查第一人称"这件事有地方可写',
       R.ASIDE_RULES is not R.RULES and R.DIALOGUE_RULES is not R.RULES
       and any(r.key == 'aside_third' for r in R.ASIDE_RULES)
       and not any(r.key == 'aside_third' for r in R.DIALOGUE_RULES), '')



# ══════════════════════════════════════════════════════════
#  C  提示词：铁律 / 红线 / 候选配对真的递进去了吗
# [EN] C  Prompt: are the iron rules / red lines / candidate pairs really passed in
# ══════════════════════════════════════════════════════════
class _FakeWorld:
    scene = '温泉旅馆·岛村的房间'
    weather = '雪'

    def __init__(self) -> None:
        from world.state import PersonState
        self.rules_text = ('## 世界铁律\n- 几乎不写情节，只写物与声音。\n'
                           '- 时代禁忌词：手机、电话')
        self.people = {
            '驹子': PersonState(name='驹子', identity='温泉旅馆的艺伎',
                               catchphrase='说话快，爱说"你这个人哪"',
                               redline='不许人可怜她'),
            '叶子': PersonState(name='叶子', identity='旅馆帮工',
                               catchphrase="只叫'先生'",
                               redline='她的声音只用来唤人、传话'),
        }


def _capture_prompt(items: list[dict], history: list[str]) -> str:
    """真跑一次 `ScriptDoctor.work`，把发出去的 prompt 抓下来（打桩，不花钱）。"""
    from crew import agents as A
    from crew.agents import SetCtx
    from llm import replies as R2
    from llm.replies import Reply

    w = _FakeWorld()
    ctx = SetCtx(world=w, db=None, day=1, people=['驹子', '叶子'])
    seen: dict = {}
    real = A.ask

    async def fake_ask(tier, messages, **kw):
        seen['prompt'] = messages[-1]['content'] if messages else ''
        return Reply(ok=True, value={
            '裁决': [{'序号': 1, '过': True, '类别': '其他', '问题': '', '改成': ''}],
            '主题': '驹子想问一句说不出口的话。'})

    A.ask = fake_ask
    try:
        asyncio.run(A.ScriptDoctor().work(ctx, items=items, history=history))
    finally:
        A.ask = real
    assert isinstance(R2, object)
    return str(seen.get('prompt') or '')


def group_c() -> None:
    items = [{'序号': 1, '类型': 'dialogue', '谁': '驹子', '对': '岛村',
              '文本': '你这个人哪，倒是吭一声啊。'}]
    hist = ['〔dialogue·驹子〕你这人哪……',
            '〔action·叶子〕叶子脚步放得很轻，走到纸门外停下，双手交叠在腹前。']
    p = _capture_prompt(items, hist)
    ok('C1 ★★ 真跑一次 `work()` 抓到了 prompt（不是空跑）', len(p) > 800, f'{len(p)} 字')
    ok('C2 ★★★ 提示词里有**这本书的铁律**（世界铁律 / 禁忌词）——'
       '判"越界"的另一半依据，原来从来没递进来过',
       '世界铁律' in p and '手机、电话' in p, p[:0] or '')
    ok('C3 ★★★ 人物卡上带着**红线**（判"越界"的第一依据）',
       '红线：她的声音只用来唤人、传话' in p and '红线：不许人可怜她' in p, '')
    ok('C4 ★★★ 提示词里有**程序挑出的候选配对**（`第 1 条 ↔ …` 那种行），'
       '并写明"判不判由你"',
       '第 1 条 ↔' in p and '判不判由你' in p and '同一个人' in p, '')
    ok('C5 ★★★ 两条新检查都在：⑦ 语义重复、⑧ 越界',
       '是不是同一件事（重复）' in p and '有没有越界' in p, '')
    ok('C6 ★★★ ⑦ 明写了**判重复不看字面看意思**，并给了"同一件事的下一步不算重复"这条边界',
       '不看字面像不像' in p and '同一件事的下一步' in p, '')
    ok('C7 ★★★ 输出格式里有 `类别`（程序要靠它决定"改写 / 放行 / 拦下"）',
       '"类别"' in p, '')
    ok('C8b ★★★ ⑧ 里点了**时代/地点错置**这一种越界（实测两轮都被评委点名：'
       '日本温泉旅馆的深夜出现"更鼓一声一声"）',
       '时代 / 地点错置' in p and '更鼓' in p, '')
    ok('C8c ★★★ ⑧ 里点了**心声必须第一人称**（实测 sg-01 把旁白塞进了心里话，'
       '这一条 40%–74% 不遵守）',
       '必须是第一人称的心里话' in p, '')
    # 成对：没有铁律时不许硬凑一个空标题
    from crew import agents as A
    from crew.agents import SetCtx
    from llm.replies import Reply

    class _W2(_FakeWorld):
        def __init__(self) -> None:
            super().__init__()
            self.rules_text = ''

    seen: dict = {}
    real = A.ask

    async def fake_ask(tier, messages, **kw):
        seen['prompt'] = messages[-1]['content'] if messages else ''
        return Reply(ok=True, value={'裁决': [{'序号': 1, '过': True}], '主题': ''})

    A.ask = fake_ask
    try:
        asyncio.run(A.ScriptDoctor().work(
            SetCtx(world=_W2(), db=None, day=1, people=['驹子']),
            items=items, history=hist))
    finally:
        A.ask = real
    p2 = str(seen.get('prompt') or '')
    ok('C8 ★★ 成对：**没有铁律时不许留一个空标题**（"这本书的铁律"那段整块不出现）',
       '这本书的铁律' not in p2, '')


# ══════════════════════════════════════════════════════════
#  D  处置：改写优先 / 重复改不动就放行 / 整拍全拦 ⇒ 全部放行
# [EN] D  Disposition: rewrite first / let repetition through / never empty a beat
# ══════════════════════════════════════════════════════════
class _FakeBuilder:
    def __init__(self) -> None:
        self.dropped: list = []

    def drop_entries(self, entries):
        self.dropped.extend(entries)
        return len(entries)


def _make_loop(verdicts: list[dict]):
    from crew.review import ScriptLog
    from sim.loop import RunLoop
    from world.state import GameTime, PersonState, WorldState

    w = WorldState()
    w.scene = '温泉旅馆·岛村的房间'
    w.clock = GameTime()
    w.people['驹子'] = PersonState(name='驹子', location='温泉旅馆·岛村的房间')
    loop = RunLoop.__new__(RunLoop)
    loop.world = w
    loop.script_log = ScriptLog()
    loop._builder = _FakeBuilder()
    loop._tick_no = 0
    loop._current_day = 1
    loop._review_rewrites = {}
    loop._review_cat_rewrite = {}
    loop._review_cat_pass = {}
    loop._review_blocked_today = 0
    loop._review_themes = []
    loop._warn_once = lambda tag, msg: None
    loop._crew_ctx = lambda: None
    # ⚠ 不要在这里写死 `_MODEL_KINDS`：它是类属性，`RunLoop.__new__` 之后照样取得到。
    #   写死成 ('dialogue','action') 会把 `aside` 挡在门外，D10 就永远测不出真假。
    # [EN] ⚠ Do not hardcode `_MODEL_KINDS` here: it is a class attribute and is reachable after
    # [EN] `RunLoop.__new__`. Hardcoding ('dialogue','action') excludes `aside` and makes D10
    # [EN] untestable.

    class _Studio:
        def __init__(self) -> None:
            self.seen: list[dict] = []

        async def audit(self, ctx, *, items, history):
            from crew.agents import CrewNote
            self.seen = list(items or [])
            return CrewNote(role='script_doctor', ok=True, title='桩',
                            data={'裁决': list(verdicts), '主题': '桩'})

    loop.studio = _Studio()
    return loop


def _entries(texts: list[tuple[str, str]]):
    from display import script as S
    return [S.dialogue(who, text) for who, text in texts]


def _run_review(loop, entries) -> list:
    return asyncio.run(loop._script_review(entries))


def group_d() -> None:
    from crew import review as R
    from config import CFG

    # ── D1 重复 + 改成 ⇒ 改写 ──
    loop = _make_loop([{'序号': 1, '过': False, '类别': '重复',
                        '问题': '同一句自白换个说法又说了', '改成': '她把杯子推得远了些。'}])
    es = _entries([('驹子', '你这个人哪，我是个好人吧？')])
    out = _run_review(loop, es)
    ok('D1 ★★★ 「重复」给了 `改成` ⇒ **真的改写**（不是只记账）',
       len(out) == 1 and out[0].text == '她把杯子推得远了些。', out[0].text if out else '')
    ok('D2 ★★ 而且改写**按类别计数**（`重复` 记了一笔 —— 作者要看得出"修的是什么"）',
       loop._review_cat_rewrite.get(R.CAT_DUP) == 1,
       str(loop._review_cat_rewrite))

    # ── D3 重复 + 没有改成 ⇒ **放行**（不许删空）──
    #   ⚠ 必须**两条**：单条的批次会被"整拍不许删空"那条救回来，
    #     那样就分不清"因为它是重复才放行"和"因为只剩一条才放行"。
    # [EN] ⚠ Must be **two** entries: a single-entry batch is rescued by "never empty the beat",
    # [EN] which would make "let through because repetition" indistinguishable from "let through
    # [EN] because it is the only one".
    loop = _make_loop([
        {'序号': 1, '过': False, '类别': '重复', '问题': '同一动作做第二遍', '改成': ''},
        {'序号': 2, '过': True, '类别': '其他', '问题': '', '改成': ''},
    ])
    es = _entries([('驹子', '她端酒壶过来，放在门槛内。'), ('驹子', '她把杯子推远了些。')])
    out = _run_review(loop, es)
    ok('D3 ★★★ 「重复」**改不动 ⇒ 放行**（删掉会让这一拍变成空白，'
       '而空白比重复更伤 —— 第三轮实测）',
       len(out) == 2 and out[0].text == '她端酒壶过来，放在门槛内。'
       and not loop._builder.dropped, f'{len(out)} 条 / 删了 {len(loop._builder.dropped)}')
    ok('D4 ★★ 而且台账里留了一笔（`[重复]` 前缀 + 非"拦下"）',
       any('[重复]' in str(r.why) and not r.blocked
           for r in loop.script_log.rows + loop.script_log.blocked),
       str([(r.why[:20], r.blocked) for r in loop.script_log.blocked]))
    ok('D5 ★★ 计数也记了"重复放行"（`_review_cat_pass`）',
       loop._review_cat_pass.get(R.CAT_DUP) == 1, str(loop._review_cat_pass))

    # ── D6 越界 + 没有改成 ⇒ 拦下（`strict` 开着）──
    #   ⚠ 必须**两条**：一条越界、一条正常 —— 单条的批次会被
    #     "整拍不许删空"那条救回来（见 D7），那是**有意的**取舍。
    # [EN] ⚠ Must be **two** entries: one out of bounds, one fine. A single-entry batch is rescued
    # [EN] by the "never empty the beat" rule (D7), and that is **intentional**.
    with _Cfg(SCRIPT_REVIEW_STRICT='true'):
        loop = _make_loop([
            {'序号': 1, '过': False, '类别': '越界', '问题': '她的声音只用来唤人', '改成': ''},
            {'序号': 2, '过': True, '类别': '其他', '问题': '', '改成': ''},
        ])
        es = _entries([('叶子', '先生，要出去看雪吗？'), ('驹子', '她把杯子推远了些。')])
        out = _run_review(loop, es)
    ok('D6 ★★★ 「越界」改不动 ⇒ **真的拦下**（这一类才该拦 —— 踩的是硬约束），'
       '而且同一批里没问题的照留',
       len(out) == 1 and out[0].text == '她把杯子推远了些。'
       and len(loop._builder.dropped) == 1,
       f'剩 {[e.text[:12] for e in out]} / 删了 {len(loop._builder.dropped)}')

    # ── D6b 成对：**单条**批次的越界 ⇒ 放行（宁可留一句越界的，也不要整拍空白）──
    with _Cfg(SCRIPT_REVIEW_STRICT='true'):
        loop = _make_loop([{'序号': 1, '过': False, '类别': '越界',
                            '问题': '越界', '改成': ''}])
        out = _run_review(loop, _entries([('叶子', '先生，要出去看雪吗？')]))
    ok('D6b ★★★ 成对：**单条**批次里的越界 ⇒ 放行（删了就整拍空白，'
       '这条取舍要显式钉住，不许悄悄变）',
       len(out) == 1 and not loop._builder.dropped, f'剩 {len(out)} 条')

    # ── D6c 规则层判坏的**不享受**"整拍不许删空"那条 ──
    #   实测（`verify_script_review` 的 C1 当场变红）：残留 JSON 被救回来后
    #   直接印进了正文 —— 垃圾上屏比空白糟得多。
    # [EN] Entries rejected by the **rule layer** do NOT get the "never empty a beat" rescue.
    # [EN] Measured: leftover JSON was rescued and printed into the body.
    with _Cfg(SCRIPT_REVIEW_STRICT='true'):
        loop = _make_loop([])          # 没有裁决 ⇒ 只可能是规则层判的
        bad_line = '{"动作": "speak", "台词": "你来了"}'
        out = _run_review(loop, _entries([('驹子', bad_line)]))
    ok('D6c ★★★ 成对：**规则层**判坏的（残留 JSON / 占位话）即使整拍只有这一条，'
       '也照样拦下（垃圾上屏比空白糟）',
       not out and len(loop._builder.dropped) == 1,
       f'剩 {len(out)} 条 / 删了 {len(loop._builder.dropped)}')

    # ── D7 整拍全拦 ⇒ 全部放行（不许留空白）──
    with _Cfg(SCRIPT_REVIEW_STRICT='true'):
        loop = _make_loop([
            {'序号': 1, '过': False, '类别': '越界', '问题': '越界', '改成': ''},
            {'序号': 2, '过': False, '类别': '越界', '问题': '越界', '改成': ''},
        ])
        es = _entries([('叶子', '先生，要出去看雪吗？'), ('叶子', '我去看看病人。')])
        out = _run_review(loop, es)
    ok('D7 ★★★ **整拍会被删空 ⇒ 全部放行**（宁可留一句越界的，也不要整拍空白）',
       len(out) == 2 and not loop._builder.dropped,
       f'剩 {len(out)} 条 / 删了 {len(loop._builder.dropped)}')

    # ── D8 成对：`strict=false` 时越界也只记不拦 ──
    with _Cfg(SCRIPT_REVIEW_STRICT='false'):
        loop = _make_loop([{'序号': 1, '过': False, '类别': '越界',
                            '问题': '越界', '改成': ''}])
        out = _run_review(loop, _entries([('叶子', '先生，要出去看雪吗？')]))
    ok('D8 ★★ 成对：`SCRIPT_REVIEW_STRICT=false` ⇒ 越界也只记不拦（老语义不变）',
       len(out) == 1 and not loop._builder.dropped,
       f'剩 {len(out)} 条')

    ok('D9 ★ `SCRIPT_REVIEW_STRICT` 仍然只有一个开关（不新增假旋钮）',
       'SCRIPT_REVIEW_STRICT' in _read('config.py'), '')

    # ── D10 心声要如实标成 `aside`（不许压成"动作"）──
    #   压成动作之后，审读**永远判不出**"第一人称"那条铁律 ——
    #   实测 sg-01：「司马昭心想：司马昭一夹马腹向前半步…」被放过了。
    # [EN] Inner voice must be labelled `aside` (not flattened into "action"): once flattened the
    # [EN] reviewer can never judge the first-person rule -- measured in sg-01.
    from display import script as S
    loop = _make_loop([{'序号': 1, '过': True}, {'序号': 2, '过': True}])
    es = [S.dialogue('司马昭', '父亲，何不冲杀进去？'),
          S.aside('司马昭', '司马昭一夹马腹向前半步，又回头看父亲脸色。')]
    _run_review(loop, es)
    kinds = [str(it.get('类型')) for it in loop.studio.seen]
    ok('D10 ★★★ 心声**如实标成 `aside`**（压成"动作"就没法判"第一人称"那条铁律）',
       kinds == ['dialogue', 'aside'], str(kinds))

    # ── D11 审读自己加的标签要洗掉（实测进过一次正文）──
    #   某一轮续写：`改成` = 「〔改动作〕某人的拇指沿杯口抹了半圈…」⇒ 标签跟着改写
    #   一起上屏。`Entry.__post_init__` 只在**构造**时洗，而改写是直接赋 `entry.text`。
    # [EN] The Mowen run had `改成` = "[改动作] Liu Shi ran a thumb along the cup rim..." and the
    # [EN] label rode into the body: `Entry.__post_init__` only washes at construction, while a
    # [EN] rewrite assigns `entry.text` directly.
    loop3 = _make_loop([])
    e1 = S.dialogue('柳氏', '这茶的味道，和我记忆中的有些相似。')
    loop3._review_rewrite(e1, '〔改动作〕柳氏拇指沿杯口抹了半圈，把盏推回原处半分。',
                          '重复', cat='重复')
    ok('D11 ★★★ 改写串里的**审读自用标签**要洗掉（`〔改动作〕` / `（心里）`）'
       '—— 它们是我们的内部格式，不是正文',
       not e1.text.startswith('〔') and not e1.text.startswith('（心里）')
       and e1.text.startswith('柳氏拇指'), e1.text[:40])
    e2 = S.aside('老陈', '这小子的字怎么和旧账上的这么像。')
    loop3._review_rewrite(e2, '（心里）旧账上也有这一笔……谁教他写的。', '重复', cat='重复')
    ok('D12 ★★ 成对：**行首的 `（心里）` 也洗**（它是"给这段贴的类型"，不是内容）',
       not e2.text.startswith('（心里'), e2.text[:30])
    e3 = S.action('老陈', '把桶放下。')
    loop3._review_rewrite(e3, '他把碗放下（没再拿起）。', '其他', cat='其他')
    ok('D13 ★★★ 成对：**句中的圆括号一动都不许动**'
       '（"（没再拿起）"是正文，不是标签）',
       e3.text == '他把碗放下（没再拿起）。', e3.text)

    assert CFG is not None


class _Cfg:
    """临时改配置（离开时还原）。⚠ 只改传进来的那几个键。"""

    def __init__(self, **kw: str) -> None:
        self.kw = kw
        self.old: dict = {}

    def __enter__(self):
        from config import CFG
        for k, v in self.kw.items():
            self.old[k] = CFG.s(k)
            CFG.set(k, v)
        return self

    def __exit__(self, *a) -> None:
        from config import CFG
        for k, v in self.old.items():
            CFG.set(k, v)


# ══════════════════════════════════════════════════════════
#  E  记账：按类别的处置要进《剧本审读.md》
# [EN] E  Accounting: per-category disposition must reach the review report
# ══════════════════════════════════════════════════════════
def group_e() -> None:
    src = _read('sim/loop.py')
    try:
        tree = ast.parse(src)
    except SyntaxError:
        ok('E0 ★ sim/loop.py 能解析', False, 'SyntaxError')
        return
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == '_flush_review_report'), None)
    ok('E1 ★ `_flush_review_report` 在 AST 里找得到', fn is not None, '')
    if fn is None:
        return
    body = ast.unparse(fn)
    ok('E2 ★★★ 审读小结里有一节**按类别记账**（改写数 / 放行数）',
       '按类别的处置' in body and '_review_cat_rewrite' in body, '')
    ok('E3 ★★ 而且写清了"重复改不动时放行而不是删掉"这条口径（读者要看得懂）',
       '放行而不是删掉' in body, '')
    ok('E4 ★★ 类别计数**按天清零**（和 `_review_themes` 一起）',
       '_review_cat_rewrite = {}' in body or '_review_cat_rewrite = {}' in src, '')

    # 日志里要看得见"重复放行"这个数（不然没人知道它救回了多少）
    m = [n for n in ast.walk(tree)
         if isinstance(n, ast.Call)
         and 'n_dup_pass' in ast.unparse(n)]
    ok('E5 ★★ 每拍的日志里报了"重复放行"条数（不报就等于没发生）',
       bool(m), f'{len(m)} 处')

    # ── E6 行为判：真跑一次落盘，**md 里真有那张表** ──
    #   AST 只能证明"代码里有这段"；这里要证明"写出来的文件里有这张表"
    #   （MEMORY 里那条"prompt 里写了 ≠ 生效"的同一课）。
    # [EN] Behavioural: really run the flush and assert the **written file** has the table
    # [EN] (the same lesson as "written in the prompt != in effect").
    import tempfile

    from crew import review as R

    tmp = Path(tempfile.mkdtemp(prefix='nws_rev_'))

    class _Folder:
        def __init__(self) -> None:
            self.root = tmp
            self.reports: dict = {}

        def write_report(self, name: str, md: str) -> None:
            self.reports[str(name)] = str(md)

    loop = _make_loop([])
    loop.runfolder = _Folder()
    loop._review_cat_rewrite = {R.CAT_DUP: 2, R.CAT_BOUND: 1}
    loop._review_cat_pass = {R.CAT_DUP: 1}
    loop.script_log.add(kind='dialogue', text='她把杯子推远了些。', who='驹子',
                        day=1, tick=1, source='actor', place='某屋')
    loop._flush_review_report()
    md = '\n'.join(loop.runfolder.reports.values())
    ok('E6 ★★★ 落盘的小结里**真有**「这一天审读按类别的处置」那张表，'
       '两类的数字都对得上',
       '这一天审读按类别的处置' in md and '| 重复 | 2 | 1 |' in md
       and '| 越界 | 1 | 0 |' in md, md[-260:])
    ok('E7 ★★ 表下面写清了"重复改不动时放行而不是删掉"这条口径（给作者读的）',
       '放行而不是删掉' in md, '')

    # ── E8 改写要进台账（含原文），而且**不许污染"读者看过的那一份"** ──
    #   实测（samples 那一轮）：日志里 3 次改写，`审读台账.jsonl` 里一条都没有 ——
    #   因为改写只写了内存字典。而用户要的是「一直记录生成的所有信息」。
    #   ⚠ 必须走**真实生产路径**（`_review_rewrite`），不能直接调 `log.add` ——
    #     直接调等于测我自己刚写的那行，产品那一路删掉也照样绿（反例法 ㉓ 抓出来的）。
    # [EN] Measured (the samples run): 3 rewrites in the log, zero in `审读台账.jsonl`,
    # [EN] because rewrites only went into an in-memory dict.
    # [EN] ⚠ Must go through the **real production path** (`_review_rewrite`); calling `log.add`
    # [EN] directly would test the line I just wrote, and deleting it from the product would stay
    # [EN] green (caught by mutation ㉓).
    from display import script as S

    loop2 = _make_loop([])
    e0 = S.dialogue('驹子', '我这是怎么了，怎么在他面前这么失态。')
    loop2._review_rewrite(e0, '她笑了一声，说：“酒上头了。”',
                          '明确的心里想，违反铁律', cat='越界')
    stream = [r for r in loop2.script_log.everything() if r.was]
    ok('E8 ★★★ 改写**进流水**（`everything()` 里查得到原文、新文与原因）',
       len(stream) == 1 and '失态' in stream[0].was
       and '酒上头' in stream[0].text and '越界' in stream[0].why,
       str([(r.was[:12], r.text[:12], r.why[:16]) for r in stream]))
    ok('E9 ★★★ 成对：改写记录**不进 `recent()`**（否则同一句话会在'
       '"读者看过的那一份"里出现两次）',
       not [r for r in loop2.script_log.recent(10) if r.was],
       str([r.text[:12] for r in loop2.script_log.recent(10)]))
    ok('E10 ★★ 小结里能把"被审读改写 N 条"数出来（不数就等于没发生）',
       '被审读改写 1 条' in loop2.script_log.report_md(),
       loop2.script_log.report_md()[:160])

    # ── E11–E13：**场景介绍只上屏、不进小说正文**（2026-10-18）──
    #   实测：雪国那篇正文**第一段**是「温泉旅馆岛村客房：纸门向西开，外是雪地。
    #   屋内北墙摆火钵…南边岛村坐望火」—— 那是**场记单**（用户 2026-10-12 要求
    #   "照着就能画出平面"），被作家当正文第一段原样上屏了。
    #   链路：剧作者 `场景介绍` → `_open_day` 里 `_push_narrative(..., kind=AMBIENT)`
    #   → `_review_gate` 记账 → 作家按台账整理正文。
    # [EN] ── E11-E13: **the scene intro goes on screen but not into the novel** (2026-10-18) ──
    # [EN] Measured: the first paragraph of the Snow Country output was "Onsen inn, Shimamura's
    # [EN] room: the paper door opens west, outside is snow. A brazier sits on the north wall...
    # [EN] Shimamura sits to the south" -- a **stage note** (the user asked on 2026-10-12 for it to
    # [EN] be detailed enough to draw a floor plan) that the writer printed as the opening paragraph.
    import ast as _ast

    tree = _ast.parse(_read('sim/loop.py'))
    push = next((n for n in _ast.walk(tree)
                 if isinstance(n, _ast.FunctionDef) and n.name == '_push_narrative'), None)
    gate = next((n for n in _ast.walk(tree)
                 if isinstance(n, _ast.FunctionDef) and n.name == '_review_gate'), None)
    ok('E11 ★★★ `_push_narrative` 能把"只上屏不记账"传下去（否则场景介绍一定进正文）',
       push is not None
       and any(a.arg == 'to_ledger' for a in push.args.args), '')
    # ⚠ 判的是**表达式** `not to_ledger`，不是"源码里含 `archived` 这个词" ——
    #   后者被 `archived=False` 一改就绿（本判据第一版就这么假绿过）。
    # [EN] Judge the **expression** `not to_ledger`, not "the word `archived` appears" -- the latter
    # [EN] stays green under `archived=False` (the first version of this check did exactly that).
    _arch = ''
    if gate is not None:
        for n in _ast.walk(gate):
            if (isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
                    and n.func.attr == 'add'):
                for k in n.keywords:
                    if k.arg == 'archived':
                        _arch = _ast.unparse(k.value).replace(' ', '')
    ok('E12 ★★★ `_review_gate` 把它翻成 `archived=not to_ledger`'
       '（语义与"审读改写记录"一致：进 `everything()`、不进 `recent()`）',
       _arch == 'notto_ledger',
       f'实际写成 `archived={_arch or "(没有这个参数)"}`')
    # 调用点：**只有**场景介绍那一处传 False（别的上屏都要记账）
    calls = [n for n in _ast.walk(tree)
             if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
             and n.func.attr == '_push_narrative']
    no_ledger = [c for c in calls
                 if any(k.arg == 'to_ledger' and _ast.unparse(k.value) == 'False'
                        for k in c.keywords)]
    ok('E13 ★★★ 只有**一处**上屏不记账，而且那一处是场景介绍（`kind=S.AMBIENT` '
       '且传的是 intro）——不是"一刀切全都不记"',
       len(no_ledger) == 1 and 'intro' in _ast.unparse(no_ledger[0])
       and 'AMBIENT' in _ast.unparse(no_ledger[0]),
       f'{len(calls)} 处调用 / {len(no_ledger)} 处不记账')


def main() -> int:
    for fn in (group_a, group_b, group_c, group_d, group_e):
        try:
            fn()
        except Exception as e:                                   # noqa: BLE001
            ok(f'{fn.__name__} 执行失败', False, repr(e))
    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['ok'] = not bad
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n剧本审读·语义重复与越界验证：{len(checks) - len(bad)}/{len(checks)}', flush=True)
    return 0 if not bad else 2


if __name__ == '__main__':
    raise SystemExit(main())
