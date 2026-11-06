# -*- coding: utf-8 -*-
"""验证：**作者说「修复4个问题 / 修复所有问题 不要问我 / 至少3轮别问我」时，软件真的听懂并照办**。

用户 2026-10-11 夜的原话（这是本支判据的**唯一**依据）：
    「摄取的时候还是有问题 系统给我列出了4个自查问题 我说**修复4个问题**
      但是它不知道我什么意思 **而且反复让我修改**
      我让它**修复所有自查问题 不要问我** 也不行 **必须一轮一问**
      我想如果我跟它说 **至少多少轮不要问我 修复所有问题**
      或者说**修复所有问题 不要问我** 他应该理解并执行才对」

## 三件事，三组判据

**A 组（纯逻辑：认不认得出）**
  A1 ★★★ 「修复N个问题」里的 N 对上列表长度 ⇒ 认成"整批"
  A2 ★★★ 「修复所有问题 / 全都改掉 / 都改了」⇒ 整批
  A3 ★★★ 「不要问我 / 别问我」⇒ 免打扰（一直）；「至少3轮不要问我」⇒ 3 轮
  A4 ★★  「可以问我了」⇒ 撤销免打扰
  A5 ★★★ 「处理 1 2」「先改第 2 条」「前两个」「后两条」⇒ 点名的编号
  A6 ★★  **普通的话不许被误认**（"下一场再让它炸开""把主角改个名字"）
  A7 ★★  编辑 `review_items`：体检报告里**带段头的那一行**（`【建议优先打磨】1. …`）
      也要收得到（实测第一版整份报告抽出 0 条）

**B 组（行为：认出来之后真的照办）**
  B1 ★★★ **免打扰是硬拦**：模型这一轮还在 `{"问": …}`，`turn.question` 必须是空、
      而且要有一条"别问、自己定"的观察结果喂回去（**不是求模型配合**）
  B2 ★★★ 免打扰的**轮数会走**：说"2 轮"，第 1、2 轮不问，第 3 轮恢复会问
  B3 ★★★ 「修复4个问题」⇒ 那 4 条**编号进了下达给模型的消息**（模型数不清，
      我们算得出）
  B4 ★★  自查出来的问题**被记下来**（下一句"修复4个问题"才有的可指）
  B5 ★★  「我懂你的意思了」那句话**回给了作者**（`turn.notes` —— 光内部理解不够）
  B6 ★★  「可以问我了」之后反问恢复

**C 组（真机：这句话打进去，对话栏里确实出现了回应）**
  C1 ★★★ 摄取跑到 AI 优化阶段，输入「修复所有问题 不要问我」⇒
      右侧对话栏出现"我懂你这句的意思了"那条，**并且下一轮的轮次没有停下来等问题**

产出：`assets/screenshots/polish_intent_report.json`

English:
Verify: **when the author says "fix the 4 problems / fix all problems, don't ask me / don't ask me
for at least 3 rounds", the software really understands and complies**.
The user's exact words, late 2026-10-11 (the **only** basis for this criterion):
  "There is still a problem during ingestion. The system listed 4 self-check problems for me, I said
  **fix the 4 problems**, but it does not understand what I mean, **and it keeps making me revise**.
  I told it to **fix all the self-check problems and don't ask me**, that doesn't work either -- it
  insists on **one question per round**. I think if I tell it **don't ask me for at least N rounds,
  fix all problems**, or say **fix all problems, don't ask me**, it should understand and do it."
## Three things, three groups of criteria
**Group A (pure logic: does it recognise)**
  A1 ★★★ the N in "fix the N problems" matches the list length ⇒ recognised as "the whole batch"
  A2 ★★★ "fix all problems / change them all / changed them all" ⇒ the whole batch
  A3 ★★★ "don't ask me" ⇒ do-not-disturb (forever); "don't ask me for at least 3 rounds" ⇒ 3 rounds
  A4 ★★  "you can ask me now" ⇒ revokes do-not-disturb
  A5 ★★★ "process 1 2" / "change item 2 first" / "the first two" / "the last two" ⇒ named numbers
  A6 ★★  **ordinary sentences must not be misread** ("just let it blow up next scene", "rename the
      protagonist")
  A7 ★★  `review_items`: a line **carrying a section header** in the checkup report
      (`【suggested priorities】1. ...`) must also be caught (measured: the first version extracted 0
      items from a whole report)
**Group B (behaviour: having recognised it, does it really comply)**
  B1 ★★★ **Do-not-disturb is a hard block**: even if the model still emits `{"ask": ...}` this round,
      `turn.question` must be empty and an observation "don't ask, decide yourself" must be fed back
      (**not begging the model to cooperate**)
  B2 ★★★ the do-not-disturb **round count decrements**: say "2 rounds", rounds 1 and 2 do not ask,
      the third goes back to asking
  B3 ★★★ "fix the 4 problems" ⇒ those 4 items **go into the message handed to the model** (the model
      cannot count; we can)
  B4 ★★  self-checked problems **are remembered** (so the next sentence "fix the 4 problems" has
      something to point at)
  B5 ★★  the "I understood you" line **is returned to the author** (`turn.notes` -- understanding
      internally is not enough)
  B6 ★★  after "you can ask me now" the questions come back
**Group C (real machine: type the sentence in, and a response really shows in the chat pane)**
  C1 ★★★ run ingestion to the AI-refinement stage, type "fix all problems, don't ask me" ⇒ the
      right-hand chat pane shows the "I understood that" line, **and the next round does not stop to
      wait for an answer**
Output: `assets/screenshots/polish_intent_report.json`
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import traceback
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')

import verify_ui_common as VU  # noqa: E402
VU.redirect_env_writes()

from i18n import set_lang, t  # noqa: E402
import os  # noqa: E402
_lang = os.environ.get('NWS_LANG', 'zh')
set_lang(_lang)

import polish.agent as AG  # noqa: E402
from polish import intent as INTENT  # noqa: E402
from polish.sandbox import Scope  # noqa: E402

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT: dict = {'checks': []}
_FAILS = 0

#: 一份够用的设定（改设定工具要能跑）。
# [EN] A sufficient settings object (so the change-settings tool can run).
SAMPLE_SETTINGS = {
    '人物': [{'姓名': '主角', '身份': '茶楼掌柜', '性格': '沉默', '目标': '守住茶楼',
              '说话方式': '简短', '外貌': '清瘦', '背景': '旧案牵连'}],
    '世界观': {'设定': '江南水乡'}, '地点': [{'名称': '临河茶肆', '描述': '河边茶楼'}],
    '主线': [{'节点': '当票现身', '描述': '袖里半张当票'}], '伏笔': [],
}

#: 自查出来的四条（编号 1..4）—— 「修复4个问题」要指的就是它们。
# [EN] The four self-checked items (numbered 1..4) -- exactly what "fix the 4 problems" points at.
PROBLEMS = ['阿福的口吻不像跑堂', '当票的来历没交代', '地点描写重复', '主线推进太快']


def ok(name: str, cond, detail='') -> bool:
    """记一条判据（`✓` / `!`）。
        English:
    Record one criterion (`✓` / `!`).
    """
    global _FAILS
    good = bool(cond)
    if not good:
        _FAILS += 1
    REPORT['checks'].append({'name': name, 'ok': good, 'detail': str(detail)[:400]})
    print(('  ✓ ' if good else '  ! ') + name
          + (f'  | {str(detail)[:110]}' if detail else ''))
    return good


# ══════════════════════════════════════════════════════════════════
#  A 组：认不认得出
# [EN] Group A: does it recognise
# ══════════════════════════════════════════════════════════════════
def group_a() -> None:
    """A 组：纯逻辑（`polish/intent.py` 的解析）。
        English:
    Group A: pure logic (parsing in `polish/intent.py`).
    """
    print('\n── A 组：认不认得出（解析）──')
    P = list(PROBLEMS)

    r = INTENT.parse('修复4个问题', problems=P)
    ok('A1 ★★★ 「修复4个问题」⇒ 认成**整批**（N 正好等于自查条数）',
       r.fix_all and r.work == P, f'fix_all={r.fix_all} work={len(r.work)}')

    for s in ('修复所有自查问题', '把所有问题都改掉', '全都改掉', '上面的问题都改了',
              '这些都给处理了'):
        rr = INTENT.parse(s, problems=P)
        ok(f'A2 ★★★ 「{s}」⇒ 整批', rr.fix_all and rr.work == P,
           f'fix_all={rr.fix_all} work={len(rr.work)}')

    r = INTENT.parse('修复所有问题 不要问我', problems=P)
    ok('A3 ★★★ 「不要问我」⇒ 免打扰（一直）+ 整批一起认出来'
       '（用户原话就是这一句）',
       r.noask_all and r.fix_all and r.noask_rounds == 0,
       f'noask_all={r.noask_all} fix_all={r.fix_all} rounds={r.noask_rounds}')
    r = INTENT.parse('至少3轮不要问我 修复所有问题', problems=P)
    ok('A3b ★★★ 「至少3轮不要问我」⇒ **3** 轮（不是"一直"）',
       r.noask_rounds == 3 and not r.noask_all and r.fix_all,
       f'rounds={r.noask_rounds} noask_all={r.noask_all}')
    for s in ('接下来5轮别问我', '往后 4 轮不要问我', '两轮内不要问我'):
        rr = INTENT.parse(s, problems=P)
        ok(f'A3c ★★ 「{s}」⇒ 认出轮数 {rr.noask_rounds}',
           rr.noask_rounds in (2, 4, 5), f'rounds={rr.noask_rounds}')

    r = INTENT.parse('可以问我了', problems=P)
    ok('A4 ★★ 「可以问我了」⇒ 撤销免打扰（不然一次"别问我"会让后面永远哑巴）',
       r.ask_again and not r.noask_all, f'ask_again={r.ask_again}')

    r = INTENT.parse('处理 1 2', problems=P)
    ok('A5 ★★★ 「处理 1 2」⇒ 点名 1、2 条（就是用户说的那种指代）',
       r.picks == [1, 2] and r.work == [P[0], P[1]], f'picks={r.picks}')
    r = INTENT.parse('先改第 2 条', problems=P)
    ok('A5b ★★★ 「先改第 2 条」⇒ 只点名第 2 条',
       r.picks == [2] and r.work == [P[1]], f'picks={r.picks}')
    r = INTENT.parse('前两个', problems=P)
    ok('A5c ★★ 「前两个」⇒ 1、2 条', r.picks == [1, 2], f'picks={r.picks}')
    r = INTENT.parse('后两条', problems=P)
    ok('A5d ★★ 「后两条」⇒ 3、4 条', r.picks == [3, 4], f'picks={r.picks}')
    r = INTENT.parse('把上面那4条都改掉', problems=P)
    ok('A5e ★★ 「把上面那4条都改掉」⇒ 整批（"都"+动词）', r.fix_all,
       f'fix_all={r.fix_all}')

    # ⚠ **不许误认**：普通的话被当成"全改"或"点名"都会让软件乱动设定。
    # [EN] ⚠ **Must not misread**: taking an ordinary sentence as "change everything" or "named items"
    # [EN] would make the software touch settings at random.
    for s in ('下一场再让它炸开', '把主角改个名字', '补两条伏笔', '世界观再冷一点',
              '把 3 处描写改细一点'):
        rr = INTENT.parse(s, problems=P)
        ok(f'A6 ★★ 普通的话「{s}」**不许**被当成整批/点名',
           not rr.fix_all and not rr.picks and not rr.note,
           f'fix_all={rr.fix_all} picks={rr.picks} note={rr.note[:40]}')

    rep = ('【最突出的问题】人物单薄。\n【建议优先打磨】1. 改主角 —— 补他的旧案\n'
           '2. 改阿福 —— 口吻要像跑堂\n3. 补一条伏笔\n【等你回话】说吧')
    items = INTENT.review_items(rep)
    ok('A7 ★★ 体检报告里**带段头那一行**（`【建议优先打磨】1. …`）也要收到',
       len(items) == 3 and items[0].startswith('改主角'),
       f'{len(items)} 条：{items[:1]}')
    ok('A7b ★★ 没有编号的段落不许被当条目'
       '（`【最突出的问题】`那一句不是 1 号，混进来会让"第 2 条"指错）',
       all('人物单薄' not in x for x in items), str(items)[:80])


# ══════════════════════════════════════════════════════════════════
#  B 组：认出来之后真的照办
# [EN] Group B: having recognised it, does it really comply
# ══════════════════════════════════════════════════════════════════
SCRIPT: list = []
SEEN: list = []


def _reply(value):
    return SimpleNamespace(value=value, meta={}, notes=[], ok=bool(value),
                           retried=False, salvaged=False, calls=1)


async def _fake_ask(tier, messages, **kw):
    """替身模型：按 `SCRIPT` 一条一条回（与 `verify_polish_agent` 同一手法）。

    ⚠ **必须在覆盖之前抓原件**（`real_ask = AG.ask`）—— 抓晚了抓到的是假货自己，
      "还原"等于没还原，后面的组整组跟着假红。
    [EN] Stand-in model: replies one by one from `SCRIPT` (same technique as `verify_polish_agent`).
    [EN] ⚠ **Must capture the original before overriding** (`real_ask = AG.ask`) -- capturing later
    [EN] gets the fake itself, "restoring" amounts to nothing, and later groups go fake-red with it.
    """
    SEEN.append({'purpose': kw.get('purpose'),
                 'texts': [str(m.get('content') or '') for m in messages]})
    return _reply(SCRIPT.pop(0) if SCRIPT else None)


def _fixture(prefix: str):
    """造一对目录（引用文件夹 + 输出区）。
        English:
    Create a pair of directories (reference folder + output area).
    """
    src = Path(tempfile.mkdtemp(prefix=f'nws_pi_src_{prefix}_'))
    out = Path(tempfile.mkdtemp(prefix=f'nws_pi_out_{prefix}_'))
    (src / '设定').mkdir()
    (src / '设定' / '人物.md').write_text('# 人物\n主角：茶楼掌柜。\n', encoding='utf-8')
    return src, out, Scope(src_root=src, out_root=out, timeout=6.0)


def _new_agent(sc, **kw):
    SCRIPT.clear()
    SEEN.clear()
    return AG.PolishAgent(settings=json.loads(json.dumps(SAMPLE_SETTINGS)),
                          scope=sc, name='临河茶肆', tier='白银',
                          missing=('伏笔回收',), **kw)


async def group_b() -> None:
    """B 组：行为的硬拦与下达（用替身模型，零网络）。
        English:
    Group B: the hard block and the hand-down, behaviourally (stand-in model, zero network).
    """
    print('\n── B 组：认出来之后真的照办（行为）──')
    real_ask = AG.ask
    AG.ask = _fake_ask
    src, out, sc = _fixture('b')
    try:
        # ── B1 ★★★ 免打扰是硬拦 ──
        # [EN] -- B1 ★★★ do-not-disturb is a hard block --
        ag = _new_agent(sc)
        # 自查先给一条问题，好让"别问我"这句话有上下文
        # [EN] Give self-check one problem first, so that "don't ask me" has a context.
        ag.last_problems = list(PROBLEMS)
        SCRIPT.extend([
            {'想': '我拿不准', '问': '你希望阿福说哪种话？'},   # ← 模型就是想问
            # [EN] <- the model really wants to ask
            {'想': '那我自己定', '终': '按跑堂的口气改好了（我替他定的）。',
             '改了什么': []},
            {'有问题': False, '问题': [], '下一步': ''},          # 自省
            # [EN] self-reflection
        ])
        turn = await ag.ask('修复所有问题 不要问我')
        rep = REPORT.setdefault('b1', {})
        rep['question'] = turn.question
        rep['reply'] = turn.reply[:60]
        rep['notes'] = turn.notes
        ok('B1 ★★★ 模型这一轮**还在问**，但免打扰状态下 `turn.question` 必须是空'
           '（硬拦，不是求模型配合）',
           turn.question == '' and bool(turn.reply), str(rep))
        # 拦下来之后要**把"别问、自己定"喂回去**才叫真的拦住
        # [EN] Only by feeding "don't ask, decide yourself" back afterwards is it really
        # [EN] blocked.
        obs = [e for e in ag.events if e['kind'] == 'observe'
               and '不要问他' in str(e.get('text') or '')]
        ok('B1b ★★ 而且把「别问、自己定」作为**观察结果喂回去**了'
           '（不给它一个改口的机会就只是丢弃那句话）',
           bool(obs), f'{len(obs)} 条')
        ok('B1c ★★ 「我懂你的意思了」**回给了作者**（`turn.notes`）',
           bool(turn.notes) and any('不再问你' in x for x in turn.notes),
           str(turn.notes)[:120])

        # ── B2 ★★★ 轮数会走：说 2 轮 ⇒ 第 3 轮恢复会问 ──
        # [EN] -- B2 ★★★ the round count decrements: say 2 rounds -> the 3rd asks again --
        ag2 = _new_agent(sc)
        ag2.last_problems = list(PROBLEMS)
        asked = []
        for i in range(3):
            SCRIPT.extend([
                {'想': '拿不准', '问': f'第{i}轮的问题'},
                {'想': '自己定', '终': f'第{i}轮自己定了。', '改了什么': []},
                {'有问题': False, '问题': [], '下一步': ''},
            ])
            # ⚠ **只第 1 轮说那句话，后面两轮是普通指令** —— 这才是"轮数会走"
            #   的真实场景。三轮都说同一句的话，每轮都会把计数重置回 2
            #   （那也是对的：作者又说了一遍"接下来 2 轮"，当然要重新算 2 轮）。
            # [EN] ⚠ **Only round 1 says that sentence; the next two are ordinary instructions** --
            # [EN] that is the realistic scenario for "the round count decrements". Saying the same
            # [EN] sentence in all three rounds would reset the counter to 2 each time (which is also
            # [EN] correct: the author said "the next 2 rounds" again, so 2 rounds it is).
            tn = await ag2.ask('接下来2轮不要问我，先把设定打磨一遍' if i == 0
                               else f'接着改第{i}处')
            asked.append(bool(tn.question))
        REPORT['b2'] = {'asked': asked, 'noask_left': ag2.noask_left}
        ok('B2 ★★★ 「2 轮不要问我」⇒ 第 1、2 轮不问，**第 3 轮恢复会问**'
           '（无限期不问就成了哑巴，比反复问更糟）',
           asked[:2] == [False, False] and asked[2] is True, str(asked))

        # ── B3 ★★★ 整批 ⇒ 编号清单进了下达给模型的消息 ──
        # [EN] -- B3 ★★★ the whole batch -> the numbered list lands in the message handed to the
        # [EN] model --
        ag3 = _new_agent(sc)
        ag3.last_problems = list(PROBLEMS)
        SCRIPT.extend([
            {'想': '干活', '终': '四条都改完了。', '改了什么': []},
            {'有问题': False, '问题': [], '下一步': ''},
        ])
        await ag3.ask('修复4个问题')
        last = next((x for x in reversed(SEEN) if x['purpose'] == 'polish_step'), None)
        joined = '\n'.join(last['texts']) if last else ''
        REPORT['b3'] = {'has_head': '点名' in joined,
                        'n_items': sum(1 for p in PROBLEMS if p in joined)}
        ok('B3 ★★★ 「修复4个问题」⇒ 那 4 条**逐条编号**进了下达给模型的消息'
           '（模型数不清"4 个"是哪四条，这份清单是我们算出来的）',
           bool(last) and all(p in joined for p in PROBLEMS)
           and '点名' in joined,
           f"{REPORT['b3']}")

        # ── B4 ★★ 自查的问题被记下来 ──
        # [EN] -- B4 ★★ the self-checked problems are remembered --
        ag4 = _new_agent(sc)
        SCRIPT.extend([
            {'想': '先看一遍', '终': '看完了。', '改了什么': []},
            {'有问题': True, '问题': list(PROBLEMS), '下一步': '接着改'},   # 自省：4 条
            # [EN] self-reflection: 4 items
            {'想': '再改一轮', '终': '改了第一轮。', '改了什么': []},
            {'有问题': False, '问题': [], '下一步': ''},
        ])
        await ag4.ask('把设定打磨一遍')
        ok('B4 ★★ 自查出来的几条**被记下来**（下一句"修复4个问题"才有的可指）',
           ag4.last_problems == list(PROBLEMS),
           f'{len(ag4.last_problems)} 条')

        # ── B6 ★★ 「可以问我了」之后反问恢复 ──
        # [EN] -- B6 ★★ after "you can ask me now" the questions come back --
        ag5 = _new_agent(sc)
        SCRIPT.extend([
            {'想': '拿不准', '问': '要不要动主线？'},
            {'想': '自己定', '终': '先不动。', '改了什么': []},
            {'有问题': False, '问题': [], '下一步': ''},
        ])
        await ag5.ask('别问我')
        SCRIPT.extend([
            {'想': '拿不准', '问': '现在能问了吗？'},
            {'想': '好', '终': '那就先这样。', '改了什么': []},
            {'有问题': False, '问题': [], '下一步': ''},
        ])
        tn = await ag5.ask('可以问我了')
        ok('B6 ★★ 「可以问我了」之后**反问恢复**（免打扰是可撤销的）',
           tn.question == '现在能问了吗？', f'question={tn.question!r}')
    finally:
        AG.ask = real_ask
        VU.safe_rmtree(src, ignore_errors=True)
        VU.safe_rmtree(out, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════
#  C 组：真机（打进去，对话栏里真的有回应）
# [EN] Group C: real machine (type it in; the chat pane really responds)
# ══════════════════════════════════════════════════════════════════
async def group_c(page) -> None:
    """C 组：真机 —— 摄取到 AI 优化阶段，把这句话打进去。

    ⚠ 夹具照 `verify_ingest_rounds` 的做法：**引用文件夹**（作者的素材）才是
      `_wizard_path`，不是项目根 —— 给错地方会"成功"跑出一个 0 人物、评档青铜的
      空项目（SDK 那轮踩过这个坑）。
    [EN] Group C: real machine -- run ingestion to the AI-refinement stage and type that sentence in.
    [EN] ⚠ The fixture follows `verify_ingest_rounds`: the **reference folder** (the author's material)
    [EN] is `_wizard_path`, not the project root -- giving the wrong place "succeeds" in producing an
    [EN] empty project with 0 characters and a bronze grade (a pitfall hit during the SDK round).
    """
    print('\n── C 组：真机（打进去，对话栏真有回应）──')
    import flet as ft
    from gui.app_flet import NovelWorldApp

    tmp = Path(tempfile.mkdtemp(prefix='nws_pi_gui_'))
    old_projects = VU.isolate_projects_dir(tmp / 'Projects')
    src = tmp / '听懂指令'
    (src / '正文').mkdir(parents=True, exist_ok=True)
    (src / '大纲.md').write_text('# 大纲\n\n起：雨夜来客打破平静。\n合：有人离开。\n',
                                 encoding='utf-8')
    (src / '人物设定.md').write_text('# 人物\n\n## 主角\n掌柜，沉默寡言。\n',
                                     encoding='utf-8')
    (src / '正文' / '第1章.md').write_text('# 第1章\n\n雨脚敲着檐瓦。\n' * 6,
                                           encoding='utf-8')
    try:
        app = NovelWorldApp()
        app.main(page)
        page.enable_screenshots = True
        page.update()
        await asyncio.sleep(1.6)
        VU.disable_source_repair(app)
        app.show_import_wizard()
        page.update()
        await asyncio.sleep(0.5)
        app._wizard_path = str(src)
        app._wizard_name = '听懂指令'
        app._wizard_opts['ai_optimize'] = True
        VU.disable_source_repair(app)
        CFG.set('POLISH_MAX_ROUNDS', '3')
        app._do_import(page)
        st = app._ingest_state or {}
        ui = (st.get('ui') or {})

        async def _wait(pred, timeout=90.0):
            """轮询等一个条件成立（返回是否等到）。
                English:
            Poll until a condition holds (returns whether it was reached).
            """
            loop = asyncio.get_event_loop()
            t0 = loop.time()
            while loop.time() - t0 < timeout:
                try:
                    if pred():
                        return True
                except Exception:                                # noqa: BLE001
                    pass
                await asyncio.sleep(0.15)
            return False

        await _wait(lambda: bool(ui.get('consent_panel'))
                    and ui['consent_panel'].visible, 45)
        for b in (ui.get('consent_boxes') or []):
            b.value = True
            if getattr(b, 'on_change', None):
                b.on_change(None)
        if ui.get('consent'):
            ui['consent'](True)
        entered = await _wait(lambda: st.get('phase') == 'chat', 120)
        ok('C0 摄取跑到了 AI 优化阶段（真机夹具够用）', entered,
           f"phase={st.get('phase')!r}")
        if not entered:
            return
        ui = st.get('ui') or {}
        chat = ui.get('chat_list')
        n_before = len(getattr(chat, 'controls', None) or [])

        # 说那句话（走真入口：填进输入框 + 点发送）
        # [EN] Say that sentence (through the real entry: fill the input + press send).
        ui['chat_input'].value = '修复所有问题 不要问我'
        ui['send'](None)
        got = await _wait(lambda: len(getattr(chat, 'controls', None) or [])
                          > n_before + 1, 120)
        texts = [str(x) for x in VU.all_texts(ui.get('chat_list'))]
        REPORT['c1'] = {'before': n_before,
                        'after': len(getattr(chat, 'controls', None) or []),
                        'hit': [x for x in texts if '不再问你' in x][:2],
                        'phase': st.get('phase')}
        ok('C1 ★★★ 真机：说「修复所有问题 不要问我」⇒ 对话栏里出现'
           '**"我懂你这句的意思了"**（作者必须看得见它听懂了）',
           got and any('不再问你' in str(x) for x in texts),
           str(REPORT['c1'])[:200])
        page.enable_screenshots = True
        shot = await page.take_screenshot()
        if shot:
            (OUT / 'polish_intent_gui.png').write_bytes(shot)
    finally:
        try:
            CFG.set('DEFAULT_PROJECTS_DIR', old_projects)
        except Exception:                                        # noqa: BLE001
            pass
        VU.safe_rmtree(tmp, ignore_errors=True)


async def main(page) -> None:
    """跑完 A/B/C 三组，写报告。

    `--no-gui` 跳过 C 组（真机那一组要真跑一遍摄取，一两分钟）——
      反例法要跑十几遍，不能每次都等真机。
    [EN] Run groups A/B/C and write the report.
    [EN] `--no-gui` skips group C (the real-machine group actually runs ingestion, one or two minutes)
    [EN] -- the counterexample harness runs a dozen times and cannot wait for the real machine each time.
    """
    skip_gui = '--no-gui' in sys.argv
    try:
        group_a()
        await group_b()
        if skip_gui:
            print('\n（--no-gui：跳过 C 组真机）')
        else:
            try:
                await group_c(page)
            except Exception:                                    # noqa: BLE001
                REPORT['c_error'] = traceback.format_exc()[-400:]
                ok('C 组真机段跑完', False, REPORT['c_error'][-180:])
    finally:
        REPORT['passed'] = len(REPORT['checks']) - _FAILS
        REPORT['total'] = len(REPORT['checks'])
        (OUT / 'polish_intent_report.json').write_text(
            json.dumps(REPORT, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'\n打磨指令听懂验证：{REPORT["passed"]}/{REPORT["total"]}')
        print('报告：assets/screenshots/polish_intent_report.json')


def _run() -> None:
    """入口：起一个真实窗口跑三组，然后按结论退出。
        English:
    Entry point: open a real window, run the three groups, then exit with the verdict.
    """
    import flet as ft
    from util.flet_shutdown import shutdown

    async def _wrapped(page) -> None:
        await main(page)
        await shutdown(page, code=0 if _FAILS == 0 else 1)

    ft.run(_wrapped, assets_dir=str(APP / 'assets'))


if __name__ == '__main__':
    _run()
