# -*- coding: utf-8 -*-
"""验证：**剧本审读** —— 用户 2026-10-08 点名要的那个独立 Agent。

用户原话（这一支存在的全部理由）
--------------------------------
「这段对话很奇怪 有个人来讨要欠款 突然出现 柳娘也去看他了 结果什么都没做 …
  大家都在讨论自己的事情 很奇怪 **人物进场了肯定是有用的** 大家要去跟他沟通
  （动作 对话 事情等等）**不然不要突然来一个人** 而且这段对话感觉大家没有
  讨论一个主题 或者讨论了主题 但是很散 而且说的话都不个人化」
「'目光顺着小臂滑到底 才收回 压在壶盖上'**这不是人话** … '卷了' 是啥意思
  看不懂 阿枝跟主角说'客官慢用' 啥意思 **主角又不是客官**」
「你看是否有**独立的Agent** 而不是导演在盯着演员说的每一句话 **没有就做一个**
  **在演员真的说出来之前**，把新生成的话放到已经出现的话里过一遍，看是否通顺
  而且这个Agent要**一直记录生成的所有信息**，**所有输出到窗口的东西**包括动作
  场景切换 伏笔激活 导演动作 人物对话 等等 都要让这个Agent记录下来
  任何一个新出现的东西，不管来自哪个Agent或者来源，都需要这个Agent放到已有
  历史里看下是否是一个合理的 正确的好看的故事和剧本 **不是就不要放出来**」

判据分层（每层都要能红，见 `developers/mutate_script_review.py`）：

  A **接线与配置**：SPEC 七项 · 名册职位（`when=tick` / `feeds=director`）·
    hook 真解析得到 · 有人到岗 · 工艺货架与点名条目 · 思考骨架 ·
    MOCK 登记 · `.env.example` · 以及**闸门挂在哪一行**（AST，不看文本）
  B **规则层**（零成本那半）：抓得住形式问题，**抓不住语感** ——
    用户举的那三句"不是人话"必须**一条都不命中**（那是模型层的活）
  C **闸门行为**（真跑 `_process_actions`）：改写 / 拦下 / 从幕里撤掉 /
    关掉就不记不拦 / 只记不拦 / 关掉模型就一次都不调 / 模型漏答一律放行 /
    「进场无戏」提醒进导演提示 / 审读自己崩了不连累推演 / 两份产物落盘
  D **真机（GUI）**：天机「运行」页那五个控件 · 剧组面板里「剧本审读」这一行

跑法：.venv\\Scripts\\python.exe tools/verify_script_review.py
产出：assets/screenshots/script_review_report.json

English:
Verification: **剧本审读** —— the standalone Agent the user explicitly requested on 2026-10-08.
User's original words (the entire reason this branch exists)
--------------------------------
"This conversation is weird. Someone comes to demand repayment, suddenly appears, Liu Niang also
goes to see him, and in the end nothing happens …
  everyone is discussing their own things, very weird **when a character enters, they must be useful**; everyone should go communicate with him
  (actions, dialogue, events, etc.) **otherwise do not suddenly bring in a person**. Also this conversation feels like everyone is not
  discussing one topic, or they discussed a topic but it is very scattered, and what they say is not personalized"
"'Gaze slides down the forearm to the bottom, then retracts, presses onto the pot lid' **this is
not human speech** … what does '卷了' mean
  can't understand it. A Zhi says to Shen Yan '客官慢用', what does that mean **Shen Yan is not a customer**"
"See whether there is a **standalone Agent** rather than the director staring at every line the
actors say. **If not, make one**
  **Before the actor actually says it**, run the newly generated line through the lines that have already appeared to check whether it flows.
  Also, this Agent must **continuously record all generated information**, **everything output to the window**, including actions.
  Scene switches, foreshadowing activations, director actions, character dialogue, etc. must all be recorded by this Agent.
  Anything newly appearing, regardless of which Agent or source it comes from, must be placed by this Agent into the existing
  history to check whether it is a reasonable, correct, good-looking story and script. **If not, do not release it.**"
Criteria layered (each layer must be able to go red, see `developers/mutate_script_review.py`):
  A **Wiring and configuration**: SPEC seven items · roster positions (`when=tick` / `feeds=director`) ·
    hook actually resolves · someone on duty · craft shelf and roll-call entries · thinking skeleton ·
    MOCK registration · `.env.example` · and **which line the gate is attached to** (AST, not text)
  B **Rule layer** (the zero-cost half): catches formal problems, **cannot catch feel** ——
    the three sentences the user cited as "not human speech" must **not be matched by even one** (that is the model layer's job)
  C **Gate behavior** (actually run `_process_actions`): rewrite / block / pull from the act /
    off means no record and no block / record only and no block / off model means not called even once / model misses answer means always let through /
    "enters with no scene" reminder into director prompt / review crashing itself does not drag down the simulation / two artifacts written to disk
  D **Real machine (GUI)**: the five controls on Tianji's "Run" page · the "script review" row in the crew panel
How to run: .venv\\Scripts\\python.exe tools/verify_script_review.py
Output: assets/screenshots/script_review_report.json
"""
from __future__ import annotations

import asyncio
import ast
import inspect
import json
import random
import sys
import tempfile
import textwrap
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG, SPEC                                    # noqa: E402

import verify_ui_common as VU                                   # noqa: E402
# ⚠ **第一件事就禁写真实 `.env`**（本项目的老教训，已发生四次）：
#   真机段会走 `app.main()` → 能力校验 → `CFG.save()`，那一步会把脚本里的
#   `CFG.set('SCRIPT_REVIEW', 'false')` 这类测试值写进用户的配置。
# [EN] ⚠ **The first thing: writing to the real `.env` is forbidden** (the project's old lesson, has
# [EN] happened four times):
# [EN] The real-machine segment goes through `app.main()` → capability check → `CFG.save()`, and that
# [EN] step will write the script's
# [EN] test values like `CFG.set('SCRIPT_REVIEW', 'false')` into the user's config.
VU.redirect_env_writes()
CFG.set('MOCK_LLM', 'true')

ONLY_LOGIC = '--logic-only' in sys.argv
OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:400]})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _src(fn) -> str:
    return textwrap.dedent(inspect.getsource(fn))


def _calls(fn) -> list[tuple[int, str]]:
    """函数里所有调用的 `(行号, 被调的东西)`（AST，**不看注释**）。
        English:
    All `(line number, thing being called)` calls inside the function (AST, **do not look at
    comments**).
    """
    try:
        tree = ast.parse(_src(fn))
    except Exception:                                            # noqa: BLE001
        return []
    out: list[tuple[int, str]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            out.append((int(getattr(n, 'lineno', -1)), ast.unparse(n.func)))
    return out


# ══════════════════════════════════════════════════════════════════════
#  A 接线与配置
# [EN] A Wiring and config
# ══════════════════════════════════════════════════════════════════════
def logic_checks() -> None:
    from crew import roster as R
    from crew import agents as A
    from sim.loop import RunLoop
    from display.scene_builder import SceneBuilder

    # ── A1 配置项 ──
    # [EN] ── A1 Config items ──
    want = {'SCRIPT_REVIEW': 'bool', 'SCRIPT_REVIEW_MODEL': 'bool',
            'SCRIPT_REVIEW_EVERY_TICKS': 'int', 'SCRIPT_REVIEW_HISTORY': 'int',
            'SCRIPT_REVIEW_STRICT': 'bool', 'SCRIPT_REVIEW_NEWCOMER_TICKS': 'int',
            'SCRIPT_REVIEW_TOKENS': 'int'}
    miss = [k for k in want if k not in SPEC]
    ok('A1 ★ 七个 `SCRIPT_REVIEW*` 配置项都在 SPEC 里', not miss, str(miss))
    bad = [k for k, t in want.items() if k in SPEC and SPEC[k]['type'] != t]
    ok('A1b 类型都对（bool/int）', not bad, str(bad))
    ok('A1c ★ `SCRIPT_REVIEW` / `SCRIPT_REVIEW_MODEL` / `SCRIPT_REVIEW_STRICT` '
       '**默认开**（用户要的是"默认就在把关"）',
       all(bool(SPEC[k]['default']) for k in
           ('SCRIPT_REVIEW', 'SCRIPT_REVIEW_MODEL', 'SCRIPT_REVIEW_STRICT')), '')
    ok('A1d ★ `SCRIPT_REVIEW_EVERY_TICKS` 默认 **1**（每一拍都过模型）',
       int(SPEC['SCRIPT_REVIEW_EVERY_TICKS']['default']) == 1, '')

    # ── A2 名册 ──
    # [EN] ── A2 Roster ──
    role = R.BY_KEY.get('script_doctor')
    ok('A2 ★★ 名册里有 `script_doctor`（**独立的一个职位**，不是导演兼职）',
       role is not None, '')
    if role is not None:
        ok("A2b ★ 排班是 `tick`（**每一拍都要看** —— 闸门挂在拍上，不是日界）",
           role.when == 'tick', role.when)
        ok('A2c 产出交给导演（拦住/改写之后的意见给下一拍用）',
           role.feeds == 'director', role.feeds)
        ok('A2d 用便宜档（它每一拍都跑）', role.tier == 'cheap', role.tier)

    # ── A3 hook 真的解析得到（名册自己会 audit）──
    # [EN] ── A3 hook actually resolves (the roster audits itself) ──
    ok('A3 ★★ 它声明的两处 hook **在程序里真的存在**'
       '（名册自己的 `audit_hooks()` 全绿）', R.audit_hooks() == {},
       str(R.audit_hooks()))
    ok('A3b `crew.review.ScriptLog` 真的解析得到（台账那一半）',
       R.resolve_hook('crew.review.ScriptLog') is not None, '')
    ok('A3c `sim.loop.RunLoop._script_review` 真的解析得到（闸门那一半）',
       R.resolve_hook('sim.loop.RunLoop._script_review') is not None, '')

    # ── A4 到岗 ──
    # [EN] ── A4 On duty ──
    ok('A4 ★ 有人到岗（名册上写了、程序里没人 = 假职位）',
       'script_doctor' not in A.missing_members(), str(A.missing_members()))

    # ── A5/A6 工艺 ──
    # [EN] ── A5/A6 Craft ──
    ok('A5 给了工艺货架（它得读点东西才判得出"像不像这个人"）',
       'script_doctor' in A.SHELVES, '')
    reads = A.READS.get('script_doctor') or ()
    ok('A5b ★ 点名要读的条目 ≥ 4 条（用户举的每类毛病各要一条手艺对着）',
       len(reads) >= 4, str(len(reads)))
    shelf = A.SHELVES.get('script_doctor') or ()
    cross: list[str] = []
    try:
        from craft import craftmix
        entries = craftmix.load()['entries']
        cross = [n for n in reads
                 if str((entries.get(n) or {}).get('_货架') or '') not in shelf]
    except Exception:                                            # noqa: BLE001
        cross = ['（工艺库读不到）']
    ok('A6 ★ 点名读的每一条**都属于它自己的货架**（跨架点名 = 职位声明是假的）',
       not cross, str(cross))
    ok('A6b 读的条数上限放得下那几条（默认 3 条会截掉一条）',
       int(A.READ_LIMIT.get('script_doctor', 3)) >= len(reads),
       str(A.READ_LIMIT.get('script_doctor')))

    # ── A7 思考骨架 ──
    # [EN] ── A7 Thinking skeleton ──
    try:
        from crew import cognition as COG
        pat = COG.pattern('script_doctor')
        steps = COG.THINK_STEPS.get('script_doctor') or ()
        field = COG.THINK_FIELD.get('script_doctor')
    except Exception as e:                                       # noqa: BLE001
        pat, steps, field = '', (), ''
        ok('A7 思考骨架读得到', False, repr(e))
    ok('A7 ★ 模式是 CoT（审查型里最需要顺序的一个：先逐条读、最后才判主题）',
       pat == getattr(COG, 'COT', 'cot'), str(pat))
    ok('A7b 有思考字段（答案要落成字段，才留得住痕）', bool(field), str(field))
    ok('A7c ★ 骨架 ≥ 4 步（人话 / 上文 / 这个人 / 主题 各一步）',
       len(steps) >= 4, str(len(steps)))
    ok('A7d ★★ 骨架里每条自问挂的条目**都是它读得到的**（不新发明理论）',
       all((not s[1]) or (s[1] in reads) for s in steps),
       str([s[1] for s in steps if s[1] and s[1] not in reads]))
    ok('A7e 最后一步是"判主题"（那是**合起来**才看得出的，必须放最后）',
       bool(steps) and ('主题' in steps[-1][0]), str(steps[-1][0] if steps else ''))

    # ── A8 MOCK 登记 ──
    # [EN] ── A8 MOCK registration ──
    try:
        from llm import mock as MK
        ok('A8 ★ 演示模式登记了 `crew_script_doctor`'
           '（不登记的话演示里这个职位永远在空转）',
           'crew_script_doctor' in MK._HANDLERS, '')
    except Exception as e:                                       # noqa: BLE001
        ok('A8 ★ 演示模式登记了 `crew_script_doctor`', False, repr(e))

    # ── A9 闸门挂在哪儿（**AST 行号**，不看注释里提没提）──
    # [EN] ── A9 Where the gate is attached (**AST line number**, not whether comments mention it) ──
    procs = _calls(RunLoop._process_actions)
    rev = [ln for ln, f in procs if '_script_review' in f]
    note = [ln for ln, f in procs if '_note_entry' in f]
    push = [ln for ln, f in procs if '_push_narrative' in f]
    ok('A9 ★★★ 上屏前那一道闸真的接在 `_process_actions` 里',
       bool(rev), str(rev))
    # ⚠ `_process_actions` 里**还有一条** `_push_narrative`（"人物决策连续失败
    #   3 次"的提示）排在闸门**前面** —— 那是给作者看的故障提示，不是剧情内容，
    #   它先推是对的。所以比的是**最后那一次**推屏幕（词条那条路）。
    # [EN] ⚠ In `_process_actions` there is **still another** `_push_narrative` (the "character decision
    # [EN] failed repeatedly
    # [EN] 3 times" notice) placed **before** the gate —— that is a fault notice for the author, not story
    # [EN] content,
    # [EN] so pushing it first is correct. Therefore compare the **last** screen push (the entry path).
    ok('A9b ★★★ 而且排在**记进"场上刚发生"之前、推到窗口之前**'
       '（拦下的东西两头都不进 —— 不会出现"读者没看见、下一个人却听见了"）',
       bool(rev) and bool(note) and bool(push)
       and min(rev) < min(note) and min(rev) < max(push),
       f'闸 {rev} vs 记缓冲 {note} vs 推屏幕 {push}')

    # ⚠ 这里**必须走 AST**：`_push_narrative` 的**文档字符串**里就写着
    #   `_on_narrative`（解释历史 bug 时提到的），按文本 `find` 会命中注释，
    #   于是"把闸门挪到播报之后"这种变异根本抓不到（第一版就是这么假绿的）。
    # [EN] ⚠ Here you **must use AST**: `_push_narrative`'s **docstring** literally contains
    # [EN] `_on_narrative` (mentioned when explaining the historical bug), and a text `find` would match
    # [EN] the comment,
    # [EN] so a mutation like "move the gate after the broadcast" cannot be caught at all (the first
    # [EN] version was falsely green this way).
    tree_push = ast.parse(_src(RunLoop._push_narrative))
    ln_gate = min((int(n.lineno) for n in ast.walk(tree_push)
                   if isinstance(n, ast.Call) and '_review_gate' in ast.unparse(n.func)),
                  default=-1)
    ln_cb = min((int(n.lineno) for n in ast.walk(tree_push)
                 if isinstance(n, ast.Call) and '_on_narrative' in ast.unparse(n.func)),
                default=-1)
    ok('A9c ★★ `_push_narrative` 里**先过闸、再播报**（记账在最前面）',
       ln_gate > 0 and ln_cb > 0 and ln_gate < ln_cb, f'闸@{ln_gate} 播报@{ln_cb}')
    ln_ret = min((int(n.lineno) for n in ast.walk(tree_push)
                  if isinstance(n, ast.If) and 'text is None' in ast.unparse(n.test)),
                 default=-1)
    ok('A9d ★★★ 被拦下时**直接 return**（不播报、也不进显示队列）',
       # ⚠ 必须带 `ln_gate > 0`：闸门整条被删掉时 `ln_gate == -1`，
       #   而 `-1 < ln_ret` 仍然成立 —— 少了这一条，变异②会假绿。
       # [EN] ⚠ Must include `ln_gate > 0`: when the whole gate is deleted, `ln_gate == -1`,
       # [EN] and `-1 < ln_ret` still holds —— without this condition, mutation ② would be falsely green.
       ln_gate > 0 and ln_gate < ln_ret < ln_cb,
       f'闸@{ln_gate} return@{ln_ret} 播报@{ln_cb}')

    # ── A10 其它落点 ──
    # [EN] ── A10 Other attachment points ──
    src_div = _src(RunLoop._push_divider)
    src_scn = _src(RunLoop._push_scene)
    ok('A10 ★ 分隔符（场景切换）也记进台账',
       '_review_record_only' in src_div, '')
    ok('A10b ★「换地方了」也记进台账', '_review_record_only' in src_scn, '')

    t_tick = _src(RunLoop._tick)
    i_watch = t_tick.find('_director_watch()')
    i_newc = t_tick.find('_note_idle_newcomers()')
    ok('A11 ★★「进场了没人搭上话」的提醒排在**导演盯戏之后**'
       '（它是**追加**：两条提示能同时活在下一拍）',
       0 <= i_watch < i_newc, f'盯戏@{i_watch} 新上场@{i_newc}')

    ok('A12 ★ 收工时把台账与小结落盘（`_flush_review_report`）',
       any('_flush_review_report' in f for _ln, f in _calls(RunLoop._end_day)), '')

    ok('A13 ★★ `SceneBuilder.drop_entries` 真的存在（拦下的要从幕里撤掉）',
       hasattr(SceneBuilder, 'drop_entries'), '')
    ok('A13b ★ 而 `RunLoop._drop_entries` 里取的就是它'
       '（⚠ 这里走的是 `getattr(builder, …)` —— 取属性不是调用，AST 看不见，'
       '所以这一条查源码；"真的撤掉了没有"由 C1b 用行为证）',
       'drop_entries' in _src(RunLoop._drop_entries), '')

    # ── A14 天机里能改（源码级）──
    # [EN] ── A14 Editable in Tianji (source level) ──
    gui = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    sets = [k for k in want if f"CFG.set('{k}'" in gui]
    ok('A14 ★★ 那几项在天机里**改得到**（每一项都有「写回配置」那一句）',
       len(sets) >= 5, f'{len(sets)}/{len(want)}：{sets}')

    # ── A15 .env.example ──
    ex = (APP_DIR / '.env.example').read_text(encoding='utf-8')
    miss_ex = [k for k in want if f'{k}=' not in ex]
    ok('A15 `.env.example` 里列了这几项（样例要跟得上）', not miss_ex, str(miss_ex))


# ══════════════════════════════════════════════════════════════════════
#  B 规则层（零成本那一半）
# [EN] B Rule layer (the zero-cost half)
# ══════════════════════════════════════════════════════════════════════
def rule_checks() -> None:
    from crew import review as RV

    hits = [
        ('junk', '{"动作": "speak", "台词": "你来了"}', 'dialogue'),
        ('junk', '看这个 https://example.com/a 就知道了', 'dialogue'),
        ('meta', '（此处省略三百字）', 'dialogue'),
        ('meta', '这句先不写 TODO', 'dialogue'),
        ('out_of_play', '作为AI，我不能回答这个问题', 'dialogue'),
        ('out_of_play', '系统提示里说的是这样', 'dialogue'),
        ('punct', '你到底想怎么样？？？？', 'dialogue'),
        ('punct', '好，，，，，我知道了', 'dialogue'),
        ('tail_comma', '账我记着，', 'dialogue'),
        ('tail_comma', '这事我先、', 'dialogue'),
        ('empty', '   ', 'action'),
    ]
    for key, text, kind in hits:
        why = RV.rule_check(text, kind=kind)
        ok(f'B 规则命中：{key} —— {text[:16]!r}', bool(why), why)

    # ★★ 规则层**不许**去抓语感 —— 那是模型层的活，规则抓会把好句子删掉
    # [EN] ★★ The rule layer **must not** try to catch language feel —— that is the model layer's job;
    # [EN] rules catching it would delete good sentences
    keeps = [
        '目光顺着小臂滑到底，才收回，压在壶盖上。',
        '卷了',
        '干净，这一句先给你留着。',
        '客官慢用～',
        '（把壶挪了挪）这事我不接。',
        '账上的七文，谁记的？',
        '嗯。',
        '去把掌柜请来。',
    ]
    for text in keeps:
        why = RV.rule_check(text, kind='dialogue')
        ok(f'B ★ 规则**不越界**：{text[:18]!r} 不该被规则拦（语感归模型）',
           not why, why)

    ok('B 动作句以逗号结尾**不算**半截话（`DIALOGUE_RULES` 分开是有意的）',
       not RV.rule_check('他把壶推过去，', kind='action'), '')
    ok('B `RULES` 里每条都有 `key` 与 `why`（好让台账写得出原因）',
       all(r.key and r.why for r in RV.RULES), '')
    ok('B 空串命中「空的」那条（其它规则都拿空串没辙）',
       RV.rule_check('', kind='action') == RV.RULES[0].why, '')


# ══════════════════════════════════════════════════════════════════════
#  C 闸门行为（真跑 `_process_actions`）
# [EN] C Gate behavior (actually runs `_process_actions`)
# ══════════════════════════════════════════════════════════════════════
class _DB:
    def get_summaries(self, k=6, scope='故事'):
        return []

    def recent_events(self, n=20, game_day=0):
        return []

    def retrieve_memory(self, *a, **k):
        return []

    def add_memory(self, *a, **k):
        pass

    def add_event(self, *a, **k):
        pass

    def count_memories(self, *a, **k):
        return 0

    def similarity(self, a, b):
        return 0.0


class _StubDirector:
    def __init__(self):
        self._pending_intervention = None

    async def on_tick(self):
        return None

    def is_at_end(self):
        return False


def make_loop(*, run=None):
    """造一个够用的 RunLoop：**真的 builder、真的 `_push_narrative`**。
        English:
    Build a sufficient RunLoop: **real builder, real `_push_narrative`**.
    """
    from world.state import WorldState, PersonState
    from agent.core import Agent
    from sim.loop import RunLoop
    w = WorldState(scene='临河茶肆')
    for n, ident in (('主角', '掌柜'), ('阿枝', '跑堂'), ('柳娘', '账房')):
        w.add_person(PersonState(n, identity=ident, personality='话不多'))
    w.place_names = ['临河茶肆', '西市']
    w.worldview_text = '一座停在未了之事旁边的茶楼。'
    db = _DB()
    agents = [Agent(w.people[n], db, w) for n in w.people]
    loop = RunLoop(w, agents, _StubDirector(), db, run)
    loop._rng = random.Random(7)
    loop._status = lambda *a, **k: None
    loop._note_think = lambda *a, **k: None
    loop._maybe_quiet = lambda: None
    loop._warn_once = lambda *a, **k: None
    return loop, agents


def _wire(loop) -> list[str]:
    """把上屏记下来（真实现照跑，台账照记）。
        English:
    Record what goes on screen (run the real implementation as-is, keep the ledger as-is).
    """
    seen: list[str] = []
    real = loop._push_narrative

    def _push(text, priority, **kw):
        seen.append(str(kw.get('raw') or text))
        return real(text, priority, **kw)

    loop._push_narrative = _push
    return seen


def _agent(agents, name):
    return next(a for a in agents if a.name == name)


async def behavior_checks() -> None:
    from agent.core import Action

    # ★★★ 2026-10-17：**测试自足 —— 钉住"每拍都过模型"**。
    #   这一段（C3）看的是"第二拍能拿到第一拍的话"，前提是**每一拍都会问模型**。
    #   而 `SCRIPT_REVIEW_EVERY_TICKS` 是**用户可以调的**（默认 1 = 每拍）；
    #   用户在 `.env` 里把它调成 2 之后，`loop._tick_no = 3` 那一拍
    #   `3 % 2 != 0` ⇒ 模型层不跑 ⇒ `calls` 只有 1 条 ⇒ `hist2 = []` ⇒ C3 **假红**。
    #   实测就是这个原因（user 的 `.env` 被调成 2 了，为了省 token）。
    #   ⇒ 这里把"每拍都问"钉死，不读用户环境；退出时还原。
    # [EN] ★★★ 2026-10-17: **test self-sufficiency -- pin "ask the model every beat"**.
    # [EN] This section (C3) checks "the second beat can see the first beat's lines", which presupposes
    # [EN] that **every beat asks the model**. But `SCRIPT_REVIEW_EVERY_TICKS` is **user-tunable**
    # [EN] (default 1 = every beat); once the user sets it to 2 in `.env`, `loop._tick_no = 3` gives
    # [EN] `3 % 2 != 0` => the model layer does not run => `calls` has only 1 entry => `hist2 = []` =>
    # [EN] C3 goes **false red**. That is exactly the cause measured here (the user's `.env` was set to 2
    # [EN] to save tokens). => Pin "ask every beat" here, don't read the user environment; restore after.
    _saved_every = CFG.raw('SCRIPT_REVIEW_EVERY_TICKS')
    CFG.set('SCRIPT_REVIEW_EVERY_TICKS', '1')
    try:
        await _behavior_checks_body()
    finally:
        if _saved_every is not None:
            CFG.set('SCRIPT_REVIEW_EVERY_TICKS', _saved_every)


async def _behavior_checks_body() -> None:
    from agent.core import Action

    # ── C1 拦下：坏台词不进剧本、不上屏 ──
    # [EN] ── C1 Intercept: bad lines do not enter the script, do not go on screen ──
    loop, agents = make_loop()
    seen = _wire(loop)
    loop._tick_no = 2
    bad = Action(verb='speak', target='柳娘',
                 dialogue='{"动作": "speak", "台词": "你来了"}')
    await loop._process_actions([(_agent(agents, '主角'), bad)])
    ok('C1 ★★★ 坏台词**没有上屏**（拦下的不进窗口）',
       not any('{"' in s for s in seen), str(seen))
    ents = [e.text for e in (loop._builder.current.entries if loop._builder else [])]
    ok('C1b ★★★ 而且**真的从幕里撤掉了**（屏幕与落盘的稿子必须一致）',
       not any('{"' in t for t in ents), str(ents))
    ok('C1c ★★ 台账里留了痕（拦下**不是静默丢弃**）',
       len(loop.script_log.blocked) == 1
       and '残留' in loop.script_log.blocked[0].why
       or '代码' in (loop.script_log.blocked[0].why if loop.script_log.blocked else ''),
       str([r.why for r in loop.script_log.blocked]))
    ok('C1d 它**不在**"读者看过的那一份"里（`recent()` 只给上屏的）',
       all('{"' not in r.text for r in loop.script_log.recent(50)), '')

    # ── C2 模型给的改写会落到词条上 ──
    # [EN] ── C2 Model-provided rewrites land on the entry ──
    loop, agents = make_loop()
    seen = _wire(loop)
    loop._tick_no = 2
    calls: list[dict] = []

    async def _audit(ctx, *, items, history=None):
        calls.append({'items': list(items), 'history': list(history or [])})
        # 认准**那一句台词**的序号（`_MODEL_KINDS` 之后进场标记不再进来，
        # 但隔着一层"序号"总归要按内容找，别写死 1）
        # [EN] Identify the sequence number of **that specific line** (after `_MODEL_KINDS`, entry markers no
        # [EN] longer come in,
        # [EN] but across a layer of "sequence number" you still have to find by content; do not hardcode 1)
        n = next((i['序号'] for i in items if i['文本'] == '卷了'), 1)
        return _note([{'序号': n, '过': False, '问题': '不是人话',
                       '改成': '账上的七文，谁记的？'}])

    loop.studio.audit = _audit
    act = Action(verb='speak', target='柳娘', dialogue='卷了')
    await loop._process_actions([(_agent(agents, '阿枝'), act)])
    ok('C2 ★★★ 模型给了「改成」→ 词条被**改写**（不是整条扔掉）',
       '账上的七文，谁记的？' in seen, str(seen))
    ok('C2b ★★ 台账里记着**原文**（"为什么改了"要查得到）',
       any(r.was == '卷了' for r in loop.script_log.rows),
       str([(r.text, r.was) for r in loop.script_log.rows]))
    ok('C2c ★★「场上刚发生」缓冲同步改成新句'
       '（不同步的话下一个人会去回应读者没看见的那句）',
       not any(str(x.get('text')) == '卷了'
               for x in (loop.world.recent_lines or [])),
       str([x.get('text') for x in (loop.world.recent_lines or [])]))

    ok('C2d ★★ 送去问模型的那一批**不含程序的舞台指示**'
       '（`入画`/`已在场`/`离场` 是程序拼的，不是谁说的话；送过去会替演员挨刀）',
       not any(str(i['文本']) in ('入画', '已在场', '离场')
               for c in calls for i in c['items']),
       str([i['文本'] for i in (calls[0]['items'] if calls else [])]))

    # ── C3 模型把「已出现的话」递进去了（否则判不了"接不接上文"）──
    # [EN] ── C3 Model passes in "already appeared lines" (otherwise "does it follow the context" cannot be
    # [EN] judged) ──
    #
    # ⚠ 第一拍**本来就没有历史**（闸门在"上屏之前"，那一刻台账还是空的）——
    #   所以要看**第二拍**：那时第一拍那几句已经躺在台账里了。
    # [EN] ⚠ The first beat **has no history by design** (the gate is "before screen push", so at that
    # [EN] moment the ledger is still empty) ——
    # [EN] so look at the **second beat**: by then the first beat's lines are already sitting in the
    # [EN] ledger.
    loop._tick_no = 3
    await loop._process_actions([(_agent(agents, '柳娘'),
                                  Action(verb='speak', dialogue='记下了。'))])
    hist2 = calls[-1]['history'] if len(calls) >= 2 else []
    ok('C3 ★★★ 第二拍时审读拿得到**已经出现过的话**'
       '（判"接不接上文 / 是不是一个主题"全靠它）',
       bool(hist2) and any('七文' in str(x) or '卷了' in str(x) for x in hist2),
       str(hist2)[:160])

    # ── C4 关掉总闸：既不记也不拦 ──
    # [EN] ── C4 Turn off the master gate: neither record nor intercept ──
    CFG.set('SCRIPT_REVIEW', 'false')
    try:
        loop, agents = make_loop()
        seen = _wire(loop)
        loop._tick_no = 2
        await loop._process_actions([(_agent(agents, '主角'),
                                      Action(verb='speak', dialogue='？？？？'))])
        ok('C4 ★★ `SCRIPT_REVIEW=false`：**不拦**（坏句子照样放出去）',
           any('？' in s for s in seen), str(seen))
        ok('C4b ★★ 而且**一个字都不记**（关掉 = 既不审也不记）',
           not loop.script_log.rows and not loop.script_log.blocked,
           f'{len(loop.script_log.rows)}/{len(loop.script_log.blocked)}')
    finally:
        CFG.set('SCRIPT_REVIEW', 'true')

    # ── C5 只记不拦 ──
    # [EN] ── C5 Record but do not intercept ──
    CFG.set('SCRIPT_REVIEW_STRICT', 'false')
    try:
        loop, agents = make_loop()
        seen = _wire(loop)
        loop._tick_no = 2
        await loop._process_actions([(_agent(agents, '主角'),
                                      Action(verb='speak', dialogue='？？？？'))])
        ok('C5 ★★ `SCRIPT_REVIEW_STRICT=false`：**只记不拦**'
           '（坏句子放出去，但台账里留了原因）',
           any('？' in s for s in seen)
           and any(r.why for r in loop.script_log.rows), str(seen))
    finally:
        CFG.set('SCRIPT_REVIEW_STRICT', 'true')

    # ── C6 关掉模型层：一次都不调 ──
    # [EN] ── C6 Turn off the model layer: not called even once ──
    CFG.set('SCRIPT_REVIEW_MODEL', 'false')
    try:
        loop, agents = make_loop()
        _wire(loop)
        loop._tick_no = 2
        n_calls = {'n': 0}

        async def _audit2(ctx, *, items, history=None):
            n_calls['n'] += 1
            return _note([])

        loop.studio.audit = _audit2
        await loop._process_actions([(_agent(agents, '主角'),
                                      Action(verb='speak', dialogue='喝茶。'))])
        ok('C6 ★★ 关掉模型层 → **一次都不问模型**（只跑零成本的规则层）',
           n_calls['n'] == 0, f'调了 {n_calls["n"]} 次')
    finally:
        CFG.set('SCRIPT_REVIEW_MODEL', 'true')

    # ── C7 模型漏答 → 一律放行（宁可漏，不可误杀）──
    # [EN] ── C7 Model misses a response → always let through (rather miss than falsely kill) ──
    loop, agents = make_loop()
    seen = _wire(loop)
    loop._tick_no = 2

    async def _empty(ctx, *, items, history=None):
        return _note([])

    loop.studio.audit = _empty
    await loop._process_actions([(_agent(agents, '主角'),
                                  Action(verb='speak', dialogue='喝茶。'))])
    ok('C7 ★★★ 模型一条裁决都没给 → **全部放行**'
       '（审读是"宁可漏不可误杀"的岗：误杀读者就少看一段，还没人查得出来）',
       '喝茶。' in seen, str(seen))

    # ── C7b 序号对不上 → 那一条也放行 ──
    # [EN] ── C7b Sequence number mismatch → that entry is also let through ──
    loop, agents = make_loop()
    seen = _wire(loop)
    loop._tick_no = 2

    async def _wrong(ctx, *, items, history=None):
        return _note([{'序号': 99, '过': False, '问题': '乱写的序号'}])

    loop.studio.audit = _wrong
    await loop._process_actions([(_agent(agents, '主角'),
                                  Action(verb='speak', dialogue='喝茶。'))])
    ok('C7b ★★ 裁决的序号对不上任何一条 → 也放行（不拿错位的裁决去误杀）',
       '喝茶。' in seen, str(seen))

    # ── C8 审读自己崩了，不连累推演 ──
    # [EN] ── C8 Review crashes itself, does not drag down the simulation ──
    loop, agents = make_loop()
    seen = _wire(loop)
    loop._tick_no = 2

    async def _boom(ctx, *, items, history=None):
        raise RuntimeError('审读挂了')

    loop.studio.audit = _boom
    threw = ''
    try:
        await loop._process_actions([(_agent(agents, '主角'),
                                      Action(verb='speak', dialogue='喝茶。'))])
    except Exception as e:                                       # noqa: BLE001
        threw = repr(e)
    ok('C8 ★★ 审读自己抛异常时**推演照走**（这一批按放行处理）',
       not threw and '喝茶。' in seen, f'抛了 {threw}；上屏 {seen}')

    # ── C9 「进场无戏」提醒 ──
    # [EN] ── C9 "Entering with no scene" reminder ──
    loop, agents = make_loop()
    loop._tick_no = 2
    loop.script_log.add(kind='enter', text='入画', who='讨债人', day=1, tick=2)
    idle = loop.script_log.idle_newcomers(12, window=8)
    ok('C9 ★★★ 台账数得出「上了场却没人跟他说上话的人」',
       '讨债人' in idle, str(idle))
    loop._tick_no = 12          # `_note_idle_newcomers` 读的就是它
    # [EN] `_note_idle_newcomers` reads exactly this
    loop._note_idle_newcomers()
    ok('C9b ★★★ 而这个提醒**真的进了导演提示**'
       '（`world.watch_note` —— 下一拍的每个人都会看到，戏才跟得上他）',
       '讨债人' in str(loop.world.watch_note or ''), str(loop.world.watch_note))
    loop.script_log.add(kind='dialogue', text='你来的路上淋湿了吧？', who='柳娘',
                        to='讨债人', day=1, tick=3)
    loop.world.watch_note = ''
    loop._tick_no = 12
    loop._note_idle_newcomers()
    ok('C9c ★★ 有人接上他之后就不再提醒（不刷屏）',
       '讨债人' not in str(loop.world.watch_note or ''),
       str(loop.world.watch_note))

    # ── C10 一切上屏的东西都记（含分隔符 / 换场景）──
    # [EN] ── C10 Everything pushed to screen is recorded (including separators / scene changes) ──
    loop, agents = make_loop()
    _wire(loop)
    from display import dividers as D
    loop._push_divider(D.scene_end('戌时', '临河茶肆'))
    loop._push_scene(place='后厨', segment='戌时')
    kinds = {r.kind for r in loop.script_log.rows}
    ok('C10 ★★ 分隔符（场景切换）进了台账',
       'divider' in kinds, str(sorted(kinds)))
    ok('C10b ★★「换地方了」进了台账', 'scene' in kinds, str(sorted(kinds)))

    # ── C11 落盘两份 ──
    # [EN] ── C11 Persist two copies ──
    tmp = Path(tempfile.mkdtemp(prefix='nws_review_'))
    from store.runfolder import RunFolder
    run = RunFolder(tmp, '第1次模拟2026-10-08-03-00').create()
    loop, agents = make_loop(run=run)
    loop._wire_log = None
    loop.script_log.add(kind='dialogue', text='喝茶。', who='主角', day=1, tick=1)
    loop.script_log.add(kind='action', text='我记着。', who='柳娘', day=1, tick=1, blocked=True, why='半截话')
    loop._review_themes = ['这几句围着同一件事在说']
    loop._flush_review_report()
    ok('C11 ★★ 收工落了《剧本审读.md》', (run.root / '剧本审读.md').is_file(),
       str(sorted(p.name for p in run.root.iterdir())))
    ok('C11b ★★ 也落了 `审读台账.jsonl`（流水，一轮一份、追加写）',
       (run.root / '审读台账.jsonl').is_file(), '')
    md = (run.root / '剧本审读.md').read_text(encoding='utf-8')
    ok('C11c ★ 小结里写清了「拦下了什么、为什么」（给人查）',
       '拦下的' in md and '半截话' in md, md[:200].replace('\n', '⏎'))
    n1 = len((run.root / '审读台账.jsonl').read_text(
        encoding='utf-8').strip().splitlines())
    loop.script_log.add(kind='dialogue', text='第二句。', who='主角', day=2, tick=1)
    loop._flush_review_report()
    lines = (run.root / '审读台账.jsonl').read_text(
        encoding='utf-8').strip().splitlines()
    ok('C11d ★★ 台账是**追加**的（不覆盖：下一轮那句加上去了，上一轮那几条还在）',
       n1 == 2 and len(lines) == 3, f'第一轮 {n1} 行 → 现在 {len(lines)} 行')
    ok('C11e ★★ 流水里**上屏的和被拦下的都在**'
       '（只写上屏的，这份台账就退化成"正文的副本"了）',
       any('"被拦": true' in x for x in lines)
       and any('"被拦": false' in x for x in lines), '')

    # ── C12 逐条裁决认得出（`verdicts_of` 的口径）──
    # [EN] ── C12 Per-item verdicts are recognizable (the `verdicts_of` convention) ──
    from crew import review as RV
    n = _note([{'序号': '2', '过': 'false', '问题': '称呼不对', '改成': '掌柜。'},
               {'序号': 3, '过': True}])
    v = RV.verdicts_of(n)
    ok('C12 裁决按序号收得回来（序号是字符串也认）',
       set(v) == {2, 3} and not RV.is_pass(v[2]) and RV.is_pass(v[3]), str(v))
    ok('C12b 认不出「过」字段时**算过**（宁可漏）', RV.is_pass({'序号': 1}), '')
    ok('C12c `fix_of` 认「改成」/「改写」/「建议」三种写法',
       all(RV.fix_of({k: 'x'}) == 'x' for k in ('改成', '改写', '建议')), '')


def _note(verdicts: list):
    from crew.agents import CrewNote
    return CrewNote(role='script_doctor', title='（桩）', ok=bool(verdicts),
                    data={'裁决': verdicts, '主题': '（桩）围着同一件事在说'})


# ══════════════════════════════════════════════════════════════════════
#  D 真机（GUI）
# [EN] D Real machine (GUI)
# ══════════════════════════════════════════════════════════════════════
async def gui_checks(page) -> None:
    VU.redirect_env_writes()          # ⚠ 起了界面就可能走 `CFG.save()`（老教训）
    # [EN] ⚠ Starting the UI may go through `CFG.save()` (old lesson)
    import flet as ft
    from gui.app_flet import NovelWorldApp

    app = NovelWorldApp()
    app.main(page)
    # ⚠ 不开这个，`page.take_screenshot()` 返回**空 bytes**（第一版 D2c 就 0 字节）
    # [EN] ⚠ Without enabling this, `page.take_screenshot()` returns **empty bytes** (the first version's
    # [EN] D2c was 0 bytes)
    page.enable_screenshots = True
    await asyncio.sleep(1.4)
    app.show_main_screen()
    await asyncio.sleep(0.6)

    # ── D1 天机「运行」页里那五个控件 ──
    # ⚠ `show_global_settings()` **不是** async（它同步把对话框挂上去）——
    #   `await` 它会报 `object AlertDialog can't be used in 'await' expression`
    #   （第一版就是这么崩的）。`tab=3` = 「运行」页，与 `verify_ingest_rounds` 同一个。
    # [EN] ── D1 The five controls in Tianji's "Run" page ──
    # [EN] ⚠ `show_global_settings()` is **not** async (it mounts the dialog synchronously) ——
    # [EN] `await`-ing it raises `object AlertDialog can't be used in 'await' expression`
    # [EN] (the first version crashed this way). `tab=3` = the "Run" page, same as `verify_ingest_rounds`.
    app.show_global_settings(tab=3)
    await asyncio.sleep(1.8)
    # ⚠ 两类控件两种取法，**缺一种就假红**：
    #   `ft.Switch` / `ft.TextField` 的文字在 **`.label`** 属性上；
    #   小节标题（`mk_section`）是一个 Row 里嵌的 `ft.Text`，只能从
    #   `VU.all_texts()`（遍历树取 `Text.value`）里拿。
    #   第一版只取了上一行那种，于是 `miss == ['剧本审读']` —— 它明明在屏幕上写着。
    # [EN] ⚠ Two kinds of controls, two ways to fetch them; **missing one kind means false red**:
    # [EN] `ft.Switch` / `ft.TextField` text lives on the **`.label`** attribute;
    # [EN] section titles (`mk_section`) are an `ft.Text` nested in a Row, only obtainable from
    # [EN] `VU.all_texts()` (walk the tree and take `Text.value`).
    # [EN] The first version only fetched the former kind, so `miss == ['剧本审读']` —— even though it is
    # [EN] clearly written on screen.
    labels: set[str] = set()
    for d in VU.open_dialogs(page):
        labels |= {str(getattr(c, 'label', '') or '') for c in VU.walk(d)}
        labels |= set(VU.all_texts(d))
    want = ['剧本审读', '启用剧本审读', '审读要问模型', '每几拍过模型', '带多少条上文',
            '判不过就拦下']
    miss = [x for x in want if x not in labels]
    ok('D1 ★★ 天机里那几项都有地方改（六个标签逐一看得见）', not miss, str(miss))
    try:
        page.pop_dialog()
        await asyncio.sleep(0.4)
    except Exception:                                            # noqa: BLE001
        pass

    # ── D2 剧组面板里「剧本审读」占一行 ──
    # [EN] ── D2 In the crew panel, "script review" takes one row ──
    from crew import roster as R
    loop, _agents = make_loop()
    app.session = _FakeSession(loop)
    app._refresh_crew_panel()
    page.update()
    await asyncio.sleep(0.5)
    texts = VU.all_texts(app._ui_run.get('crew_list')) if app._ui_run else []
    ok('D2 ★★ 剧组面板里真的有「剧本审读」这一行'
       '（名册加了、面板自己会多一行 —— 不用另画一套）',
       any('剧本审读' in str(x) for x in texts), str(texts[:6]))
    ok('D2b 面板行数 = 名册职位数（不多不少）',
       len([c for c in VU.walk(app._ui_run.get('crew_list')) 
            if type(c).__name__ == 'Row']) == len(R.ROSTER)
       if app._ui_run else False, '')
    png = await page.take_screenshot()
    (OUT / 'script_review_panel.png').write_bytes(png or b'')
    ok('D2c 整屏也截下来了（给人看）', bool(png), f'{len(png or b"")} 字节')


class _FakeSession:
    def __init__(self, loop):
        self.loop = loop
        self.is_alive = False
        self.status = 'idle'


# ══════════════════════════════════════════════════════════════════════
async def main(page) -> None:
    print('\n── A 接线与配置 ──')
    try:
        logic_checks()
    except Exception:                                            # noqa: BLE001
        ok('A 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1500:])
    print('\n── B 规则层（零成本那一半）──')
    try:
        rule_checks()
    except Exception:                                            # noqa: BLE001
        ok('B 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1500:])
    # ★ C 组**不需要界面**（它直接跑 `_process_actions`），所以 `--logic-only`
    #   也照样跑 —— 否则"只跑逻辑段"会漏掉一半判据，反例法打红时会误判成
    #   "这条变异抓不到"。
    # [EN] ★ Group C **does not need the UI** (it directly runs `_process_actions`), so `--logic-only`
    # [EN] still runs it —— otherwise "run only the logic segment" would miss half the criteria, and when
    # [EN] the counterexample method goes red it would misjudge as
    # [EN] "this mutation cannot be caught".
    print('\n── C 闸门行为（真跑一拍）──')
    try:
        await behavior_checks()
    except Exception:                                            # noqa: BLE001
        ok('C 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1500:])
    if page is not None:
        print('\n── D 真机（GUI）──')
        try:
            await gui_checks(page)
        except Exception:                                        # noqa: BLE001
            ok('D 组跑完（真机）', False, traceback.format_exc()[-400:])
            print(traceback.format_exc()[-1500:])
    rep = {'checks': report['checks'],
           'passed': sum(1 for c in report['checks'] if c['ok']),
           'total': len(report['checks'])}
    rep['ok'] = rep['passed'] == rep['total']
    (OUT / 'script_review_report.json').write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n剧本审读验证：{rep['passed']}/{rep['total']}")
    if page is not None:
        from util.flet_shutdown import shutdown
        await shutdown(page, code=0 if rep['ok'] else 2)


if __name__ == '__main__':
    if ONLY_LOGIC:
        asyncio.run(main(None))
    else:
        import flet as ft
        ft.run(main, assets_dir=str(APP_DIR / 'assets'))
