# -*- coding: utf-8 -*-
"""验证：天机「花费与优化」页签（2026-11-01）。

用户原话
--------
    「这个报告是否可以在天机里有一个Tab，并且记录单独的日志，并且后续可以在这个上
      有一个按钮进行智能分析并在现有软件框架下给出优化方法，包括修改配置
      选择不同LLM等等能够想到的方法 再加一个深度优化 是从软件层面给出建议」

拆成五件可验的事
----------------
  ① **页签在**，而且下标常量与页签表**对得上**（页签插在中间，后面五个页签的
     下标整体 +1；漏改不报错，只会"点运行配置打开的是导演那一页"）。
  ② **两个按钮真的接了活**（不是画出来的装饰）：`智能分析` / `深度优化`
     各挂一个 `run_task`，而真正的调用只走 `cost_advisor.advise()`。
  ③ **写配置只有一条路**：界面里**不许**自己 `CFG.set`，必须经
     `cost_advisor.apply_change()`（白名单 + SPEC + coerce 三道闸在那里）。
     这条是本轮最要紧的一条 —— 界面自己写配置，以后任何入口都能绕过闸门。
  ④ **那一页有自己的日志**（`logs/cost_advisor.log`），打开这一页就有一行。
  ⑤ **建议能被应用**：`check_change` 拒绝越权/越界，`apply_change` 真写进 CFG；
     演示模式下 `advise()` 回的建议**每条都过得了闸**（否则按钮永远不出现）。

判据分三组：
  A 源码级（页签 / 接线 / 唯一实现，AST+文本）
  B 纯逻辑（临时台账算账、闸门、解析、失败不抛）
  C 真机（打开天机切到这一页、点「刷新」、看日志有没有落一行）

用法：.venv\\Scripts\\python.exe tools/verify_cost_tab.py
产出：assets/screenshots/cost_tab_report.json

English:
Verifies the Tianji "Cost & Tuning" tab (2026-11-01). Five things: ① the tab exists and the index
constant matches the tab table (inserting a page shifts five indices; a miss raises nothing);
② both buttons are really wired (analysis goes through `cost_advisor.advise()`); ③ **writing
config has exactly one path** -- the UI must never call `CFG.set` itself (whitelist + SPEC +
coerce live in `apply_change()`); ④ the page keeps its own log; ⑤ advice can actually be applied
(`check_change` rejects out-of-scope values, `apply_change` really writes), and in demo mode every
suggested value passes the gate. Groups: A source-level, B pure logic (temp ledger), C real GUI.
"""
from __future__ import annotations

import asyncio
import ast
import csv
import inspect
import json
import os
import re
import sys
import tempfile
import time
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402

import verify_ui_common as VU                                  # noqa: E402
from verify_exit import finish as vfinish                      # noqa: E402
from util.flet_shutdown import shutdown                        # noqa: E402

from config import CFG, SPEC                                   # noqa: E402

CFG.set('MOCK_LLM', 'true')
CFG.set('SHOW_OPENING', 'false')

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

from gui.app_flet import NovelWorldApp                         # noqa: E402
from llm import cost_advisor as CA                             # noqa: E402
from llm import usage as U                                     # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail: str = '') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:500]})
    return bool(cond)


# ══════════════════════════════════════════════════════════════════
#  源码切片
# [EN] Source slicing
# ══════════════════════════════════════════════════════════════════
def _file() -> str:
    return (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')


def _between(src: str, a: str, b: str) -> str:
    i = src.find(a)
    if i < 0:
        return ''
    j = src.find(b, i + len(a))
    return src[i:j] if j > 0 else src[i:]


def _gs_block(src: str) -> str:
    """`show_global_settings` 整段（从文件里切，`inspect.getsource` 取不到内层函数体）。"""
    return _between(src, 'def show_global_settings(self', 'def show_project_settings')


def _tab_labels(defs: str) -> list[str]:
    """页签表一级标题（12 空格缩进那一层）。"""
    return re.findall(r'(?m)^ {12}\(t\("([^"]+)"\),', defs)


def _cost_src(src: str) -> str:
    """`_cost_block()` 的整段源码（到下一个大节注释为止）。"""
    return _between(src, 'def _cost_block() -> list:',
                    '        # ── 创作服务 · MuMuAINovel（2026-10-09）')


# ══════════════════════════════════════════════════════════════════
#  A 组：源码级
# [EN] Group A: source level
# ══════════════════════════════════════════════════════════════════
def logic_checks() -> None:
    src = _file()
    gs = _gs_block(src)
    defs = _between(gs, 'tab_defs = [', '\n        ]\n')
    labels = _tab_labels(defs)
    report['tab_labels'] = labels
    cost = _cost_src(src)

    # ── A1 页签在，且常量指得对 ──────────────────────────────────
    ok('A1 ★★★ 天机里有「花费与优化」这一页，且 `TAB_COST` 等于它在页签表里的下标',
       '花费与优化' in labels
       and NovelWorldApp.TAB_COST == labels.index('花费与优化'),
       f'TAB_COST={NovelWorldApp.TAB_COST}｜页签={labels}')

    ok('A1b ★★ 页签表里真的挂的是 `_cost_block()`（不是同名的空列表）',
       '(t("花费与优化"), _cost_block()),' in gs, '')

    # ── A2 后面五个下标整体 +1（插在中间最容易只改一半）───────────
    # ⚠ 这条是"按**标题**核对下标"，不是"数一数常量变了没有"：
    #   只把 `TAB_GLOBAL_RUN` +1、忘了 `TAB_GLOBAL_CREW`，界面照样能开，
    #   点「运行配置」会落到隔壁页 —— 静默。
    # [EN] ⚠ This checks indices **by title**, not "did the numbers change": bumping only
    # [EN] `TAB_GLOBAL_RUN` and forgetting `TAB_GLOBAL_CREW` still opens fine, and "Run config"
    # [EN] silently lands on the neighbouring page.
    pairs = [(NovelWorldApp.TAB_COST, '花费与优化'),
             (NovelWorldApp.TAB_GLOBAL_EXTERNAL, '外部创作服务'),
             (NovelWorldApp.TAB_GLOBAL_APPEARANCE, '界面外观'),
             (NovelWorldApp.TAB_GLOBAL_RUN, '运行'),
             (NovelWorldApp.TAB_GLOBAL_STYLE, '导演与合规'),
             (NovelWorldApp.TAB_GLOBAL_CREW, '剧组 Agents')]
    wrong = [(i, want, labels[i] if 0 <= i < len(labels) else '<越界>')
             for i, want in pairs
             if not (0 <= i < len(labels) and labels[i] == want)]
    ok('A2 ★★★ 插入「花费与优化」之后，它和后面五页的下标**逐个仍然指得对**'
       '（按标题反查，不是数常量）',
       not wrong, str(wrong or pairs))
    idx = [i for i, _ in pairs]
    ok('A2b ★★ 这一组下标是**连续递增**的（插一页就 +1，没人漏改）',
       idx == list(range(idx[0], idx[0] + len(idx))), str(idx))

    # ── A3 两个按钮真的接了活 ────────────────────────────────────
    ok('A3 ★★★ 两颗按钮各自挂了 `_start(False)` / `_start(True)`'
       '（分开的一个"智能分析"、一个"深度优化"）',
       '_start(False)' in cost and '_start(True)' in cost, '')
    ok('A3b ★★ `_start` 真的把活交给异步任务（`page.run_task(_run, deep)`）—— '
       '只写 `on_click=...` 不 run_task 的话，按钮点了没有任何反应',
       'self.page.run_task(_run, deep)' in cost, '')

    # ── A4 分析与写配置都只有一条路 ──────────────────────────────
    ok('A4 ★★★ 界面**自己不做分析**：`_cost_block` 里一次 `llm.chat(` 都没有'
       '（分析只能走 `cost_advisor.advise()`，否则两处提示词会各走各的）',
       'llm.chat(' not in cost, '')
    ok('A4b ★★★ 界面**自己不改配置**：`_cost_block` 里一次 `CFG.set(` 都没有'
       '（写配置只能走 `apply_change()` —— 白名单 / SPEC / coerce 三道闸在那儿）',
       'CFG.set(' not in cost, '')
    ok('A4c ★★ 而它确实调了那两个入口（`apply_change` / `apply_model`）—— '
       '否则上面两条只是"没做事"',
       'CA.apply_change(' in cost and 'CA.apply_model(' in cost, '')

    # ── A5 这一页有自己的日志 ────────────────────────────────────
    ok('A5 ★★ 打开这一页会往**自己的**日志里写一行（`CA.log_line(`）',
       'CA.log_line(' in cost, '')
    ok('A5b ★ `LOG_NAME` 是 `cost_advisor.log`（与主日志同目录、另一个文件）',
       CA.LOG_NAME == 'cost_advisor.log'
       and CA.log_path().name == 'cost_advisor.log', str(CA.log_path()))

    # ── A6 白名单本身是安全的 ────────────────────────────────────
    missing = [k for k in CA.APPLICABLE if k not in SPEC]
    ok('A6 ★★★ 白名单里每个键**都真实存在于 SPEC**'
       '（写错一个键名 ⇒ 那条建议的「应用」按钮永远不出现，界面上却看着正常）',
       not missing, str(missing))
    danger = [k for k in CA.APPLICABLE
              if k in ('MOCK_LLM', 'LOG_DIR', 'DEFAULT_PROJECTS_DIR',
                       'LLM_BASE_URL', 'LLM_API_KEY') or k.startswith('LLM_CAP_')]
    ok('A6b ★★★ 白名单里**没有**危险键（演示模式 / 路径 / 凭据 / 能力开关）'
       '—— 模型最爱提这几样，改了就"看起来优化了、其实把程序改坏"',
       not danger, str(danger))
    ok('A6c ★★ 白名单里每一项都有界（int/float 有 min·max、enum 有 opt、bool 天然安全）',
       all((SPEC[k].get('type') in ('bool', 'enum')
            or SPEC[k].get('min') is not None or SPEC[k].get('max') is not None)
           for k in CA.APPLICABLE),
       str([k for k in CA.APPLICABLE if SPEC[k].get('type') in ('int', 'float')
            and SPEC[k].get('min') is None and SPEC[k].get('max') is None]))

    # ── A7 配置项在 SPEC 里（不是只有界面认识它）──────────────────
    ok('A7 ★★ 「分析用哪档」是一个**真的配置项**（`COST_ADVISOR_TIER` 在 SPEC 里，'
       '不是写死在界面上的一个数字）',
       SPEC.get('COST_ADVISOR_TIER', {}).get('type') == 'enum'
       and set(SPEC['COST_ADVISOR_TIER'].get('opt') or []) == {'cheap', 'daily', 'front'},
       str(SPEC.get('COST_ADVISOR_TIER')))

    # ── A8 用途说明（「描述」这一列的来源）────────────────────────
    # ★ 用户 2026-11-01：「在用途右边加一列 为描述 说一下这个用途是做什么的」。
    #   `purpose` 是英文代号，作者看到只会问"这是什么" —— 这一页的用处正是
    #   "认出哪一项花钱不值"，认不出这步在做什么就只剩一堆单词。
    # [EN] The user asked for a "description" column next to "purpose": the code alone tells the
    # [EN] author nothing, and the whole point of this page is spotting where money is wasted.
    bad_desc = [k for k, v in CA.PURPOSE_DESC.items()
                if not str(v).strip() or len(str(v).strip()) < 6 or str(v).strip() == k]
    ok('A8 ★★★ 每个用途都有一句**人话**说明（非空、够长、不是把代号抄一遍）',
       not bad_desc, str(bad_desc))
    ok('A8b ★★ 查不到的代号给兜底文案，**绝不返回空串**'
       '（空格子看着像"这一行没有用途"，真相是"没人写说明"——两件事处置完全不同）',
       bool(CA.purpose_desc('__no_such_purpose__').strip())
       and CA.purpose_desc('__no_such_purpose__') == CA.DESC_UNKNOWN,
       CA.purpose_desc('__no_such_purpose__'))
    # ⚠ 直接读 `_ZH2EN` 而不是 `t(v)`：判据跑在中文下，`t(中文)` 原样返回中文，
    #   `t(v) != v` 永远不成立 ⇒ 那是条**恒绿的空靶**。
    # [EN] Read `_ZH2EN` directly, not `t(v)`: the criteria run in Chinese, where `t(zh)`
    #   returns the text unchanged, so `t(v) != v` would never fire -- an always-green target.
    from i18n import _ZH2EN
    no_en = [k for k, v in CA.PURPOSE_DESC.items() if v not in _ZH2EN]
    ok('A8c ★★ 每条说明都有英文（切到英文界面不许留中文）',
       not no_en, str(no_en[:5]))

    # ★★ 为什么这条看**真台账**而不是源码：`purpose` 有动态传进去的（`purpose=purpose`、
    #   三元、`f'…{x}'`），**从源码枚举永远会漏** —— 实测漏了 `director_event`，
    #   而它是花钱第 3 多的一步（占 7.2%），页面上一直显示"（还没登记说明）"。
    #   代价是这条会随账目变红 —— 但那正是要的：花钱大头没有说明，就该补一句。
    # [EN] ★★ Why the **real ledger** and not the source: purposes are also passed in dynamically
    #   (variables, ternaries, f-strings), so any source scan misses some -- it missed
    #   `director_event`, the 3rd priciest step (7.2%), which showed "(no description)" forever.
    #   This can go red as the ledger changes, and that is exactly the point: patch the table.
    live = CA.desc_rows(CA.overview(7))[:5]
    naked = [r['purpose'] for r in live if r['desc'] == CA.DESC_UNKNOWN]
    ok('A8d ★★★ 台账里花钱最多的 5 个用途**都有说明**'
       '（新冒出来的代号没人写说明 ⇒ 这一列又变回一堆英文单词）',
       not naked, f'没说明的 {naked}｜当前 top5 {[r["purpose"] for r in live]}')

    # ── A9 导出 CSV ─────────────────────────────────────────────
    ok('A9 ★★ 「导出 CSV」按钮挂在 `_export_csv` 上'
       '（按钮不接回调 = 点了没反应，界面上一点异样都看不出来）',
       "mk_btn(t('导出 CSV'), _export_csv" in cost, '')
    ok('A9b ★★★ 界面**自己不做 CSV**：`_cost_block` 里没有 `csv.writer` / `\',\'.join`'
       '（编码、列序、逗号转义只能有一处；两处写，改了一处另一处照旧）',
       'csv.writer' not in cost and "','.join" not in cost, '')
    ok('A9c ★★ 屏幕与 CSV 的行都来自 `CA.desc_rows()`'
       '（描述 / 命中率 / 占比各算一遍，就有一处会对不上，而三处看着都正常）',
       'CA.desc_rows(' in cost, '')


# ══════════════════════════════════════════════════════════════════
#  B 组：纯逻辑（临时台账）
# [EN] Group B: pure logic (temp ledger)
# ══════════════════════════════════════════════════════════════════
def _temp_ledger(tmp: Path) -> Path:
    """造一份**小台账**：一条"低命中 + 量大"、一条"高命中"。

    ★ 为什么不用真库：真库每天都在变，判据会随账目红绿（那是最糟的一种判据 ——
      "昨天是绿的"）。
    [EN] Build a **small ledger**: one "low hit + large volume" row and one "high hit" row.
    ★ Why not the real DB: it changes every day, so the criterion would flip with the numbers.
    """
    p = tmp / 'usage.db'
    now = time.time()
    for _ in range(5):
        U.record(model='m1', purpose='p_big', in_tok=100_000, out_tok=2_000,
                 cost=0.05, ts=now, cache_tok=0, path=p)
        U.record(model='m2', purpose='p_hi', in_tok=100_000, out_tok=2_000,
                 cost=0.05, ts=now, cache_tok=80_000, path=p)
    return p


async def calc_checks(tmp: Path) -> None:
    p = _temp_ledger(tmp)
    ov = CA.overview(7, path=p)
    ok('B1 ★★ 台账算得对：调用 10 次、输入 1.0M、命中 0.4M'
       '（数字由 SQL 算，不靠界面自己加总）',
       ov['calls'] == 10 and ov['in_tok'] == 1_000_000 and ov['cache_tok'] == 400_000,
       str({k: ov[k] for k in ('calls', 'in_tok', 'out_tok', 'cache_tok')}))
    ok('B1b ★★ 命中率 = 命中 ÷ 输入（不是"命中 ÷ 总量"那种自创口径）',
       abs(ov['hit'] - 0.4) < 1e-9, str(ov['hit']))
    sus = [r['purpose'] for r in CA.suspects(ov)]
    ok('B1c ★★★ 只把「低命中 + 量大」那一条揪出来（高命中那条不许出现）',
       sus == ['p_big'], str(sus))
    # ⚠ 行级命中率与总账命中率是**两个口径**：`overview()` 的那句 `hit` 是拿汇总数**重算**的
    #   （cache÷Σin），根本没读 `purposes()` 行里的 `hit`。只测总账 ⇒ 行级算式改错了照样绿
    #   （2026-11-01 反例法第 ⑮ 刀打空才发现的空靶）。
    #   行级 `hit` 是表格那一列与 `suspects()` 的输入 —— 口径错了就查不出该查的那条。
    # [EN] Row-level hit and the total's hit are two different conventions: the total is
    #   recomputed from sums and never reads the per-row value. Testing only the total leaves the
    #   row formula unguarded -- an empty target found by mutation test #15 on 2026-11-01.
    row_hi = next((r for r in ov['rows'] if r.get('purpose') == 'p_hi'), {})
    ok('B1e ★★★ 每一行自己的命中率也按「命中 ÷ 本行输入」'
       '（表格那一列与 suspects() 都读它，口径错了就查不出该查的那条）',
       abs(float(row_hi.get('hit', -1)) - 0.8) < 1e-9, str(row_hi))

    txt = CA.report(7, path=p)
    ok('B1d ★★ 文本报表与界面读的是**同一份实现**（报表里出现那两条用途名）',
       'p_big' in txt and 'p_hi' in txt and '低' in txt, txt[:200])

    # ── 闸门 ────────────────────────────────────────────────────
    cases = [
        ('未知键名（模型瞎编的）', 'SCRIPT_REVIEW_EVERY', 3, False),
        ('不在白名单（演示模式）', 'MOCK_LLM', True, False),
        ('不在白名单（凭据）', 'LLM_API_KEY', 'x', False),
        ('枚举不认识的值', 'COST_ADVISOR_TIER', 'gold', False),
        ('合法值', 'SCRIPT_REVIEW_EVERY_TICKS', 3, True),
        ('越界值（会被夹紧，但允许）', 'TASK_FREEDOM', 999, True),
    ]
    bad = []
    for label, k, v, want in cases:
        got, msg, eff = CA.check_change(k, v)
        if bool(got) != want:
            bad.append((label, k, v, got, msg))
    ok('B2 ★★★ 三道闸按预期放行/拦截（未知键 / 白名单外 / 枚举不认识 / 越界 / 合法）',
       not bad, str(bad))
    ok('B2b ★★ 越界值被**夹紧到上限**并如实说出来（不是静默写 999）',
       CA.check_change('TASK_FREEDOM', 999)[2] == 100, '')

    # ── 真写一遍（.env 已被重定向到临时文件，见 entry()）──────────
    old_tier = CFG.s('COST_ADVISOR_TIER')
    oks, msg = CA.apply_change('COST_ADVISOR_TIER', 'cheap')
    ok('B3 ★★ 应用一条合法建议**真的写进 CFG**（不是只改界面）',
       oks and CFG.s('COST_ADVISOR_TIER') == 'cheap', msg)
    CA.apply_change('COST_ADVISOR_TIER', old_tier or 'daily')
    ok('B3b ★★ 而越权的建议**一个字节都不写**（拒绝之后 CFG 不变）',
       (lambda: (CA.apply_change('MOCK_LLM', 'true')[0] is False
                 and CFG.b('MOCK_LLM') is True))(), '')

    # ── 换模型 ──────────────────────────────────────────────────
    from llm import models as MODELS
    entries = MODELS.ensure_ready()
    # ⚠ 这条必须**自己兜住异常**：把 `apply_model` 里那道登记表校验删掉之后，代码会走到
    #   `hit.key` 抛 AttributeError ⇒ 整套判据 rc=2 退出、一条红都打不出来，反例法读到的是
    #   "没红"（2026-11-01 第 ⑯ 刀就是这样被误判成"判据没用"的）。抛异常 != 合格的拒绝：
    #   拒绝的语义是 `(False, 一句原因)`，界面拿到它好显示；抛出去整页就白了。
    # [EN] This check must swallow the exception itself: with the registry gate removed, the code
    #   hits `hit.key` and raises AttributeError -- the whole verifier exits rc=2 with no red line,
    #   which mutation test #16 read as "the criterion never fires". Raising is NOT a valid
    #   rejection: rejection means `(False, a reason)` the UI can display.
    try:
        oks2, msg2 = CA.apply_model('cheap', 'no-such-model-key')
        blew = ''
    except Exception as e:                                      # noqa: BLE001
        oks2, msg2, blew = True, f'{type(e).__name__}: {e}', 'threw'
    ok('B4 ★★★ 换模型要**按登记表校验**：不存在的 key 一律拒绝，且是 `(False, 原因)`'
       '（写进去 = 那一档解析不到模型，界面上却显示"配好了"；抛异常 = 整页白掉）',
       (not oks2) and not blew, f'{msg2} {blew}'.strip())

    if entries:
        old_cheap = CFG.s('MODEL_CHEAP')
        # ⚠ 必须挑一个**与当前不同**的：拿"现在本来就是它"的那条去换，
        #   `CFG.s(...) == key` 恒真 —— 那就是一条**永远绿的空靶**。
        # [EN] ⚠ Must pick an entry **different from the current one**: switching to the very
        # [EN] model already in place makes `CFG.s(...) == key` always true -- an empty target.
        pick = next((e for e in entries if e.key != old_cheap), entries[0])
        oks3, msg3 = CA.apply_model('cheap', pick.key)
        ok('B4b ★★ 换成登记表里真有的那个模型 ⇒ 写进 `MODEL_CHEAP`',
           oks3 and CFG.s('MODEL_CHEAP') == pick.key and pick.key != old_cheap, msg3)
        CFG.set('MODEL_CHEAP', old_cheap)

    # ── 解析容错 ────────────────────────────────────────────────
    ok('B5 ★★★ 模型回的东西不是 JSON 时**返回空字典**、不抛'
       '（界面拿到空就出"没给出建议"，而不是整个对话框炸掉）',
       CA.parse_advice('我说我觉得你应该少花点钱。') == {}, '')
    d = CA.parse_advice('```json\n{"summary":"x","where":[{"purpose":"a"}],'
                        '"config_changes":[],"extra":"丢我"}\n```')
    ok('B5b ★★ 带围栏的 JSON 能解出来，且**只留认识的四个字段**'
       '（模型自己加的字段不许牵着前端走）',
       d.get('summary') == 'x' and 'extra' not in d and d.get('where'),
       str(d))

    # ── 失败不抛 ────────────────────────────────────────────────
    from llm.router import llm as LLM
    orig = LLM.chat

    async def _boom(*a, **kw):
        raise RuntimeError('网关提前挂了')

    LLM.chat = _boom
    try:
        res = await CA.advise(1)
    finally:
        LLM.chat = orig
    ok('B6 ★★★ 模型调用炸了也只是"这次没结果"（`ok=False` + 原因），**不往上抛**'
       '—— 它是设置页里的一颗按钮，抛出去整个天机就开不出来了',
       (res.get('ok') is False) and '网关提前挂了' in str(res.get('error')), str(res.get('error'))[:120])

    # ── 演示模式下的建议必须**过得了闸** ────────────────────────
    r = await CA.advise(7)
    chs = (r.get('data') or {}).get('config_changes') or []
    allows = [CA.check_change(c.get('key'), c.get('suggest'))[0] for c in chs]
    ok('B7 ★★★ 演示模式（MOCK）下回的建议**每一条都过得了闸**'
       '（过不了 ⇒ 界面上那颗「应用」不出现，看着像"这个功能点不动"）',
       bool(chs) and all(allows), f'{len(chs)} 条：{allows}')
    deep = await CA.advise(7, deep=True)
    sw = (deep.get('data') or {}).get('software') or []
    ok('B7b ★★ 深度优化真的给了**软件层**建议（≥3 条，且每条都有"改哪里"）',
       len(sw) >= 3 and all(str(x.get('how') or '').strip() for x in sw),
       f'{len(sw)} 条')

    # ── CSV 导出 ────────────────────────────────────────────────
    # ★ 用户 2026-11-01：「还需要能够导出报告为 csv」。
    csv_p = tmp / 'out.csv'
    CA.export_csv(7, path=p, out=csv_p)
    raw = csv_p.read_bytes()
    # ⚠ 不带 BOM，Excel 双击就是乱码 —— 而"乱码"在作者眼里等于"导出坏了"
    #   （他不会去研究编码）。这条必须真读字节。
    # [EN] Without a BOM, Excel shows mojibake on double-click, and the author concludes
    #   "the export is broken" (nobody investigates encodings). Read real bytes here.
    ok('B8 ★★★ 导出的 CSV 带 BOM（utf-8-sig）—— Excel 双击不许乱码',
       raw.startswith(b'\xef\xbb\xbf'), str(raw[:6]))
    with csv_p.open(encoding='utf-8-sig', newline='') as fh:
        table = list(csv.reader(fh))
    head = table[0] if table else []
    ok('B8b ★★ 列头 = 用途 / 描述 / 次数 …（「描述」紧挨「用途」右边，与屏幕同序）',
       head[:3] == ['用途', '描述', '调用次数'] and len(head) == 8, str(head))
    body = table[1:]
    ok('B8c ★★ 行数 = 台账里的用途数，且每行的描述都不是空的',
       len(body) == len(ov['rows']) and all(len(r) == 8 and r[1].strip() for r in body),
       f'{len(body)} 行（台账 {len(ov["rows"])} 个用途）')

    # ⚠ 手拼 `','.join` 的经典死法：描述里一出现逗号就整行错列，**而且错得整齐**，
    #   看着像数据本来就长这样。这里塞一条"带逗号 + 带引号"的描述进去，必须原样读回来。
    # [EN] The classic hand-joined CSV failure: one comma in a description shifts the whole row,
    #   and it shifts *consistently*, looking like the data was always like that.
    _bak = CA.PURPOSE_DESC.get('p_big')
    CA.PURPOSE_DESC['p_big'] = '带逗号, 也带"引号"'
    try:
        CA.export_csv(7, path=p, out=csv_p)
        with csv_p.open(encoding='utf-8-sig', newline='') as fh:
            rows2 = list(csv.reader(fh))
    finally:
        if _bak is None:
            CA.PURPOSE_DESC.pop('p_big', None)
        else:
            CA.PURPOSE_DESC['p_big'] = _bak
    line2 = next((r for r in rows2 if r and r[0] == 'p_big'), [])
    ok('B8d ★★★ 描述里有逗号和引号时整行仍然对齐（用了 `csv` 模块，不是手拼）',
       line2[:2] == ['p_big', '带逗号, 也带"引号"'] and len(line2) == 8, str(line2))
    ok('B8e ★★ 文件名带范围与时间戳（导出不会覆盖上一次的）',
       'cost_' in CA.csv_path(7).name and '7d' in CA.csv_path(7).name
       and CA.csv_path(None).name != CA.csv_path(7).name,
       f'{CA.csv_path(7).name} / {CA.csv_path(None).name}')


# ══════════════════════════════════════════════════════════════════
#  C 组：真机
# [EN] Group C: real GUI
# ══════════════════════════════════════════════════════════════════
async def gui_checks(page: ft.Page, app) -> None:
    # ⚠⚠ 先确认"这一页能构建出来"，且**自己兜住异常**：
    #   列数与格子数对不上、控件构造抛错这类毛病会让**整页渲染失败**，
    #   而失败会把后面每一条 C 组判据一起带走 —— 反例法读到的就是
    #   "rc=2 但一条红都打不出来"，看着像"判据没用"（2026-11-01 第 ⑳ 刀）。
    # [EN] ⚠⚠ First prove the page **builds**, and swallow the exception here: a column/cell
    #   count mismatch makes the whole page fail to render, which takes every later C check with
    #   it -- mutation test #20 read that as "rc=2 with no red line", i.e. "the criterion is useless".
    dlg = None
    build_err = ''
    try:
        dlg = app.show_global_settings(tab=NovelWorldApp.TAB_COST)
        page.update()
        await asyncio.sleep(1.2)
    except BaseException as ex:                                  # noqa: BLE001
        build_err = f'{type(ex).__name__}: {ex}'
    ok('C0 ★★★ 这一页**能构建出来**（列数与格子数对不上这类错会让整页崩；'
       '崩在这里要判红，不能把整组判据一起带走）',
       dlg is not None and not build_err, build_err)
    if dlg is None:
        return

    panels = VU.tab_panels(dlg)
    labels = list(panels)
    ok('C1 ★★ 对话框里真有这一页（按页签结构取，不靠全文搜——后者连别的页也会算进来）',
       t('花费与优化') in labels, str(labels))

    pane = panels.get(t('花费与优化'))
    texts = '\n'.join(VU.all_texts(pane)) if pane is not None else ''
    report['pane_text_sample'] = texts[:400]
    ok('C1b ★★★ 页面上两颗粒按钮都在（文案对得上）',
       t('智能分析（1 次调用）') in texts and t('深度优化（软件层建议）') in texts,
       texts[:300])

    ov = CA.overview(7)
    want = f'{ov["calls"]:,}'
    ok('C1c ★★★ 屏幕上的汇总数字与 `cost_advisor.overview()` **算出来的一致**'
       '（同一份实现；两处各算一遍迟早对不上）',
       want in texts, f'想找 {want}（共 {ov["calls"]} 次调用）')

    ok('C1d ★★ 表格列头在（用途 / 描述 / 次数 / 输入 / 输出 / 命中率 / 占比 / 花费）',
       all(x in texts for x in (t('用途'), t('描述'), t('次数'), t('命中率'), t('花费'))), '')

    # ── 「描述」必须紧挨在「用途」右边（用户原话："在用途右边加一列"）──
    # ★ 为什么要看**顺序**而不是"有没有"：加在第 8 位也是"有一列描述"，
    #   但读表的人得把眼睛从代号挪到最右边再回来，这一列就白加了。
    # [EN] Order, not mere presence: a description column at the far right still exists, but the
    #   reader has to jump from the code to the last column and back -- the column is wasted.
    cols = [c for c in VU.walk(pane or ft.Column()) if isinstance(c, ft.DataTable)]
    # ⚠ 列头是 `DataColumn.label`（一个 `ft.Text`），要用 `ctrl_text`；
    #   用 `text_of` 取的是 `.content`，Text 上恒为空 ⇒ 八个空串（第一版就是这么错的）。
    # [EN] A heading is `DataColumn.label` (an `ft.Text`) -- use `ctrl_text`; `text_of` reads
    #   `.content`, which is always empty on a Text, giving eight empty strings.
    heads = [VU.ctrl_text(col.label) for col in cols[0].columns] if cols else []
    report['headings'] = heads
    ok('C1d2 ★★★ 「描述」紧挨在「用途」右边（不是"有这一列"就算过）',
       len(heads) > 2 and heads[0] == t('用途') and heads[1] == t('描述'), str(heads))

    # ★ 有列头不等于格子里有字：`_desc_cell('')` 一样能建出 8 列，
    #   屏幕上就是"描述"底下**一片空白** —— 加了个空列，用户什么也没得到。
    # [EN] A heading is not content: `_desc_cell('')` still builds 8 columns, and the screen shows
    #   an empty description column -- a column was added and the user gained nothing.
    _rows = CA.desc_rows(ov)
    want_desc = t(_rows[0]['desc'])[:10] if _rows else ''
    ok('C1d3 ★★★ 描述那一列**真有字**（不是只加了个列头、底下空着）',
       bool(want_desc) and want_desc in texts,
       f'想找「{want_desc}」（{len(_rows)} 行数据）')

    ok('C1e ★★ 这一页的日志路径**写在页面上**（不然"为什么是 0"没人查得动）',
       str(CA.log_path()) in texts or 'cost_advisor.log' in texts, '')

    # ── 点一下「刷新」 ──────────────────────────────────────────
    btn = None
    for c in VU.walk(pane) if pane is not None else []:
        if VU.text_of(c) == t('刷新') and getattr(c, 'on_click', None):
            btn = c
            break
    err = ''
    if btn is not None:
        try:
            btn.on_click(None)
            page.update()
            await asyncio.sleep(0.4)
        except BaseException as ex:                              # noqa: BLE001
            err = f'{type(ex).__name__}: {ex}'
    ok('C2 ★★ 点「刷新」不抛（它会重读台账并重画表格）', btn is not None and not err,
       err or ('找到了' if btn else '没找到按钮'))

    # ── 日志真的落了一行 ────────────────────────────────────────
    lp = CA.log_path()
    body = lp.read_text(encoding='utf-8') if lp.exists() else ''
    ok('C3 ★★★ 这一页**有自己的一份日志**，且打开它就写了一行'
       '（用户："记录单独的日志"）',
       lp.exists() and '花费与优化' in body, str(lp))
    ok('C3b ★ 日志与主日志**同目录、另一个文件**（不是往 nws_*.log 里塞）',
       lp.name == 'cost_advisor.log' and 'nws_' not in lp.name, str(lp))

    # ── 点一下「导出 CSV」：真的要出文件 ────────────────────────
    # ⚠ 不能只在源码里找到那个按钮名：`mk_btn(..., _export_csv)` 写对了，
    #   但 `_export_csv` 内部抛异常，界面上只会闪一下提示，看着像"导出了"。
    # [EN] Don't settle for finding the button name in source: if `_export_csv` raises, the UI
    #   only flashes a message and it still looks like it exported.
    exp_btn = None
    for c in VU.walk(pane) if pane is not None else []:
        if VU.text_of(c) == t('导出 CSV') and getattr(c, 'on_click', None):
            exp_btn = c
            break
    before = {p.name for p in (CA.log_path().parent / 'cost_report').glob('*.csv')} \
        if (CA.log_path().parent / 'cost_report').exists() else set()
    err2 = ''
    if exp_btn is not None:
        try:
            exp_btn.on_click(None)
            page.update()
            await asyncio.sleep(0.5)
        except BaseException as ex:                              # noqa: BLE001
            err2 = f'{type(ex).__name__}: {ex}'
    shots = (CA.log_path().parent / 'cost_report')
    after = {p.name for p in shots.glob('*.csv')} if shots.exists() else set()
    new_csv = sorted(after - before)
    ok('C4 ★★★ 点「导出 CSV」真的落了一个新文件（不是"按钮在、点了没动"）',
       exp_btn is not None and not err2 and bool(new_csv),
       err2 or (f'新文件 {new_csv}' if new_csv else '没找到按钮/没出新文件'))
    if new_csv:
        with (shots / new_csv[-1]).open(encoding='utf-8-sig', newline='') as fh:
            r2 = list(csv.reader(fh))
        ok('C4b ★★ 落下的那个文件能当表读：列头八列、至少一行数据、描述不空',
           r2 and len(r2[0]) == 8 and len(r2) > 1 and all(x[1].strip() for x in r2[1:]),
           f'{len(r2)} 行｜头 {r2[0] if r2 else []}')
    # ⚠ 这条判据点的是**真实界面**，导出的文件会落在用户的 `logs/cost_report/` 里
    #   ⇒ 验完必须把**这一次新出现的**那几个删掉（只删新出现的，用户自己的永远不碰）。
    #   本项目栽过：判据在真实项目里写了测试数据、然后留在那儿（`地图/锚定.json`）。
    # [EN] This criterion clicks the **real** button, so files land in the user's
    #   `logs/cost_report/`. Delete only the ones that appeared during this run; never touch the
    #   user's own. This project has been burned before by criteria leaving test data behind.
    for n in new_csv:
        try:
            (shots / n).unlink()
        except Exception:                                        # noqa: BLE001
            pass


async def entry(page: ft.Page) -> None:
    tmp = Path(tempfile.mkdtemp(prefix='nws_cost_'))
    VU.isolate_projects_dir(tmp / 'Projects')
    # 这条判据会真调用 `apply_change()`（写 `.env`）—— 必须整段重定向掉
    # [EN] This criterion really calls `apply_change()` (writes `.env`) -- redirect the whole run
    VU.redirect_env_writes()
    # ★ 这一页的日志、分析存档、导出的 CSV 全都挂在 `log_dir()` 上 —— 一并指到临时目录。
    #   `NWS_LOG_DIR` 就是为这件事准备的测试钩子（见 `logger.log_dir` 的说明）。
    #   ⚠ 它排在 `.env` 的 `LOG_DIR` **之后**：用户显式配过 `LOG_DIR` 时它不生效，
    #     所以 C4 那边仍留了一道"只删这次新出现的文件"的兜底。
    # [EN] The page's log, advice archive and exported CSV all follow `log_dir()` -- point it at
    #   the temp dir via the `NWS_LOG_DIR` test hook. ⚠ It ranks **after** `.env`'s `LOG_DIR`,
    #   so a user-configured `LOG_DIR` wins; C4 therefore still deletes only what it created.
    os.environ['NWS_LOG_DIR'] = str(tmp / 'logs')
    report['log_dir'] = str(CA.log_path().parent)
    app = NovelWorldApp()
    app.main(page)
    page.update()
    await asyncio.sleep(1.8)
    try:
        logic_checks()
        await calc_checks(tmp)
        await gui_checks(page, app)
    except BaseException:                                        # noqa: BLE001
        report['fatal'] = traceback.format_exc()
    finally:
        VU.safe_rmtree(tmp, ignore_errors=True)
    await shutdown(page, code=finish())


def finish() -> int:
    return vfinish(report, out_path=OUT / 'cost_tab_report.json', label='花费与优化验证')


if __name__ == '__main__':
    ft.run(entry)
    sys.exit(finish())
