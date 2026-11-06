# -*- coding: utf-8 -*-
"""判据：**LLM 用量统计**（用户 2026-10-10 第二个需求）。

用户原话要点 → 对应判据
----------------------
| 用户要求 | 判据 |
|---|---|
| 运行界面加链接，点进去看用量 | G1…G3 |
| 左栏 = 软件整体 + 各项目（可滚动） | G2 |
| 软件整体按 **模型 / 日期 / 模块** 分；项目多一个 **推演任务** | A1 |
| 第三层按 **Agent** 分 | A2 |
| **不使用 LLM 动态生成** | C1 |
| **不在本地保存 md**，存数据库、需要时动态生成界面 | C2 / C3 |
| 支持导出 **xlsx**（软件整体或项目级） | B1 / B5 |
| 导出可选**中文/英语** | B4 |
| **按 Sheet 区分**，第一个一定是**总体信息**，每 Sheet 带介绍 | B2 / B3 |
| 第四栏明细 | A3 |

★ 两条写法纪律（都是反例法教的）：
  ① 不许"在文件里搜得到"就算接上了 —— 要在**那个方法的那个块里**查；
  ② 不许只判"名字在不在" —— 要**调一次看返回值**。

跑法：`.venv/Scripts/python.exe tools/verify_usage_stats.py`
报告：`assets/screenshots/usage_stats_report.json`

English:
Criterion: **LLM usage statistics** (the user's second requirement on 2026-10-10).
User's key points -> corresponding criteria
----------------------
| User requirement | Criterion |
|---|---|
| Add a link in the run UI, click through to see usage | G1...G3 |
| Left column = software as a whole + each project (scrollable) | G2 |
| Software as a whole split by **model / date / module**; project has one extra **simulation task** | A1 |
| Third level split by **Agent** | A2 |
| **Do not use LLM dynamic generation** | C1 |
| **Do not save md locally**, store in the database, dynamically generate the UI when needed | C2 / C3 |
| Support export to **xlsx** (software as a whole or project level) | B1 / B5 |
| Export can be **Chinese/English** | B4 |
| **Distinguish by Sheet**, the first is always **overall information**, each Sheet has an introduction | B2 / B3 |
| Fourth column details | A3 |
★ Two writing disciplines (both taught by counterexamples):
  ① Do not count it as wired just because "it can be found by searching the file" -- check **inside that block of that method**;
  ② Do not judge only "whether the name is present" -- **call it once and look at the return value**.
How to run: `.venv/Scripts/python.exe tools/verify_usage_stats.py`
Report: `assets/screenshots/usage_stats_report.json`
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

REPORT: dict = {'checks': [], 'notes': []}


def ok(name: str, cond: bool, detail='') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    return bool(cond)


def read(rel: str) -> str:
    p = APP / rel
    return p.read_text(encoding='utf-8', errors='replace') if p.is_file() else ''


def between(text: str, start: str, end: str = '') -> str:
    i = text.find(start)
    if i < 0:
        return ''
    j = text.find(end, i + len(start)) if end else -1
    return text[i:j if j > 0 else len(text)]


def code_only(text: str) -> str:
    """去掉**整行注释** —— 判"代码干了什么"，不是"文件里有没有这几个字"。
        English:
    Remove **whole-line comments** -- judge "what the code does", not "whether the file contains
    these words".
    """
    return '\n'.join(ln for ln in str(text or '').splitlines()
                     if not ln.lstrip().startswith('#'))


_SEED = [
    # (module, project, run, agent, model, purpose, in, out, cost)
    ('NovelWorldSimulator', '甲项目', '第1次模拟', '小说作家', 'deepseek-v4-pro', 'crew_novelist', 12000, 3400, 0.20),
    ('NovelWorldSimulator', '甲项目', '第1次模拟', '剧作者', 'deepseek-chat', 'crew_screen', 8000, 2200, 0.03),
    ('NovelWorldSimulator', '甲项目', '第1次模拟', '导演', 'deepseek-chat', 'day_plan', 3000, 900, 0.01),
    ('MuMuAINovel', '甲项目', '第1次模拟', '小说作家', 'deepseek-chat', 'mumu_batch', 15000, 4000, 0.06),
    ('NovelWorldSimulator', '乙项目', '第1次模拟', '复盘', 'deepseek-flash', 'crew_review', 5000, 1200, 0.02),
    ('NovelWorldSimulator', '乙项目', '第2次模拟', '场记', 'deepseek-flash', 'crew_cont', 4000, 800, 0.016),
]


def _seed_db(tmp: Path):
    from llm import usage as U
    for (m, p, r, a, mdl, pur, ti, to, c) in _SEED:
        assert U.record(model=mdl, purpose=pur, in_tok=ti, out_tok=to, cost=c,
                        module=m, project=p, run=r, agent=a, path=tmp), '落库失败'
    return U


# ══════════════════════════════════════════════════════════════════
#  A. 数据层：落库 / 划分 / 聚合
# [EN] A. Data layer: persistence / partitioning / aggregation
# ══════════════════════════════════════════════════════════════════
def test_data(tmp: Path) -> bool:
    U = _seed_db(tmp)
    k = True
    tt = U.totals(path=tmp)
    k &= ok('A1 ★★ 落库后总体算得对（6 次调用 / 入 47000 / 出 12500 / 3 个模型 / 2 个模块 / 5 个 Agent）',
            tt['calls'] == 6 and tt['in_tok'] == 47000 and tt['out_tok'] == 12500
            and tt['models'] == 3 and tt['modules'] == 2 and tt['agents'] == 5,
            str({x: tt[x] for x in ('calls', 'in_tok', 'out_tok', 'models', 'modules', 'agents')}))
    # ★★ 划分方式：用户点名的两套（软件整体 3 个、项目 4 个）
    # [EN] ★★ Partitioning: the two sets the user named (3 for the software as a whole, 4 for the project)
    k &= ok('A2 ★★★ 软件整体能按 **模型 / 日期 / 模块** 三种划分'
            '（用户点名这三样）',
            tuple(U.BY_FOR_GLOBAL) == ('模型', '日期', '模块'), str(U.BY_FOR_GLOBAL))
    k &= ok('A2b ★★★ 某个项目能按 **模型 / 日期 / 推演任务 / 模块** 四种划分'
            '（项目比整体多一个"推演任务"）',
            tuple(U.BY_FOR_PROJECT) == ('模型', '日期', '推演任务', '模块'),
            str(U.BY_FOR_PROJECT))
    k &= ok('A2c ★ 每种划分真的查得出结果（四种都试一遍，不是只有常量）',
            all(U.groups(None, b, path=tmp) for b in ('模型', '日期', '模块'))
            and all(U.groups('甲项目', b, path=tmp)
                    for b in ('模型', '日期', '推演任务', '模块')),
            '')
    # ★ 项目隔离
    # [EN] ★ Project isolation
    g = U.groups('甲项目', '模型', path=tmp)
    k &= ok('A3 ★★★ 按项目过滤真的生效（甲项目 4 次 / 乙项目 2 次，两边不串）',
            U.totals('甲项目', path=tmp)['calls'] == 4
            and U.totals('乙项目', path=tmp)['calls'] == 2
            and len(g) == 2, f"甲={U.totals('甲项目', path=tmp)['calls']} 乙={U.totals('乙项目', path=tmp)['calls']}")
    # 第三层：Agent
    # [EN] Third level: Agent
    ags = U.agents(None, '模型', 'deepseek-chat', path=tmp)
    k &= ok('A4 ★★★ 第三层按 **Agent** 拆得出来（某个模型下有三个 Agent）',
            len(ags) == 3, str([a['agent'] for a in ags]))
    # 没有 Agent 的调用要归到"（未标：用途）"而不是静默丢掉
    # [EN] Calls without an Agent must be attributed to "(unlabeled: purpose)" rather than silently dropped
    U.record(model='deepseek-flash', purpose='book_scan', in_tok=100, out_tok=50,
             cost=0.001, module=U.MODULE_SELF, project='甲项目', run='第1次模拟',
             agent='', path=tmp)
    ags2 = U.agents('甲项目', '模型', 'deepseek-flash', path=tmp)
    k &= ok('A4b ★★ **没有 Agent 的调用归到「（未标：用途）」**，不许静默丢掉'
            '—— 开卷那一大块开销正是没有 Agent 的',
            any('（未标' in a['agent'] for a in ags2), str([a['agent'] for a in ags2]))
    # 明细
    # [EN] Details
    k &= ok('A5 ★ 第四栏的明细查得出来（每次调用一行）',
            len(U.detail('甲项目', '模型', 'deepseek-chat', path=tmp)) >= 2, '')
    k &= ok('A5b ★ 明细能按 Agent 再过滤（点第三栏某一个 Agent）',
            len(U.detail('甲项目', '模型', 'deepseek-chat', '剧作者', path=tmp)) == 1, '')
    # 项目清单
    # [EN] Project list
    k &= ok('A6 ★ 左栏要的项目清单查得出来（按费用降序）',
            [x['name'] for x in U.projects(path=tmp)] == ['甲项目', '乙项目'],
            str([x['name'] for x in U.projects(path=tmp)]))
    # 时间范围
    # [EN] Time range
    k &= ok('A7 ★ 可按日期范围筛（"最近一段时间"落地成一个真的过滤条件）',
            isinstance(U.recent_days(60, path=tmp), list)
            and len(U.groups(None, '模型', since='2999-01-01', path=tmp)) == 0, '')
    # 上下文：并发安全 + 只覆盖给了的键
    # [EN] Context: concurrency-safe + only overrides the keys given
    U.set_ctx(module='X', project='P1', run='R1', agent='A1')
    U.set_ctx(agent='A2')
    c = U.ctx()
    k &= ok('A8 ★★★ 上下文用 `contextvars`，且 `set_ctx` **只覆盖给了的键**'
            '（设 `agent` 不许把 `project` 抹掉）',
            c.get('project') == 'P1' and c.get('agent') == 'A2' and c.get('run') == 'R1',
            str(c))
    U.clear_ctx('agent')
    k &= ok('A8b ★ `clear_ctx` 只清点名的键（别的留着）',
            U.ctx().get('agent') is None and U.ctx().get('project') == 'P1',
            str(U.ctx()))
    U.clear_ctx()
    return k


# ══════════════════════════════════════════════════════════════════
#  D. 删掉一个项目的用量记录（用户 2026-10-10：「最左边一列的内容允许删除」）
# [EN] D. Delete a project's usage records (user 2026-10-10: "the contents of the leftmost column may
# [EN] be deleted")
# ══════════════════════════════════════════════════════════════════
def test_delete(tmpdir: Path) -> bool:
    """数据层：**删得准、删得干净、删不成要说话**。

    ★ 三条都是"错了就不可恢复"逼出来的，而且**都不是可选的**：
      · 空项目名的护栏 —— 见 D1，这是防灾难；
      · 只删那一个 —— 见 D2，`DELETE` 漏了 `WHERE` 会把整本账清空；
      · 失败返回 -1 —— 见 D3b，静默失败 = 用户以为删掉了、列表却没变。
    真机那半（确认框、界面上那一行跟不跟着没）在 `verify_usage_delete.py`。
    
        English:
    Data layer: **delete accurately, delete cleanly, speak up if deletion fails**.
        ★ All three are forced out by "if wrong, it's unrecoverable", and **none of them are optional**:
          · Guard against empty project name -- see D1, this prevents disaster;
          · Delete only that one -- see D2, a `DELETE` missing its `WHERE` will wipe the entire ledger clean;
          · Return -1 on failure -- see D3b, silent failure = user thinks it was deleted, but the list doesn't change.
        The real-machine half (confirmation dialog, whether that row in the UI disappears too) is in `verify_usage_delete.py`.
    """
    from llm import usage as U
    db = tmpdir / 'del.db'
    k = True
    for p, c in (('甲项目', 0.20), ('乙项目', 0.05)):
        U.record(model='deepseek-chat', purpose='crew_novelist', in_tok=100,
                 out_tok=20, cost=c, module='NovelWorldSimulator', project=p,
                 run='第1次模拟', agent='小说作家', path=db)
    # 再加一笔**没有项目上下文**的（开卷那一整段就是这么落库的：
    # `record()` 里 project 的默认值就是空串）。
    # [EN] Also add one with **no project context** (that whole opening section was persisted exactly like
    # [EN] this:
    # [EN] the default value of project in `record()` is the empty string).
    U.record(model='deepseek-chat', purpose='book_scan', in_tok=10, out_tok=5,
             cost=0.01, module='NovelWorldSimulator', project='', run='',
             agent='', path=db)
    n0 = U.totals(path=db)['calls']

    k &= ok('D1 ★★★ 传**空项目名**时 `delete_project(\'\')` 一行都不删（返回 0）'
            '—— `record()` 里 project 的默认值就是空串（开卷那些调用落的就是它），'
            '一次误调会把那一大块账**全抹掉**、还返回一个漂亮的"删了 N 条"',
            U.delete_project('', path=db) == 0
            and U.totals(path=db)['calls'] == n0,
            f'删完之后还剩 {U.totals(path=db)["calls"]}/{n0} 条'
            + ('　★ 被删掉了！' if U.totals(path=db)['calls'] != n0 else ''))
    k &= ok('D2 ★★★ 删一个项目**只删它**（返回删掉的行数）：'
            '另一个项目、以及"空项目名"那些记录都不受影响',
            U.delete_project('甲项目', path=db) == 1
            and [x['name'] for x in U.projects(path=db)] == ['乙项目']
            and U.totals(path=db)['calls'] == n0 - 1,
            f"剩 {U.totals(path=db)['calls']} 条，"
            f"项目={[x['name'] for x in U.projects(path=db)]}")
    k &= ok('D3 ★★ 删一个**不存在**的项目 ⇒ 返回 0（不是报错、也不是 -1）',
            U.delete_project('丙项目', path=db) == 0, '')
    k &= ok('D3b ★★★ 写不进去时返回 **-1**（既不抛、也不假装成功）'
            '—— 静默失败就是"以为删掉了、列表却没变"，本项目最忌讳的那一种',
            U.delete_project('乙项目', path=tmpdir) == -1,
            '（把一个目录当库路径用 ⇒ 打不开）')
    return k


# ══════════════════════════════════════════════════════════════════
#  B. 导出 xlsx
# [EN] B. Export xlsx
# ══════════════════════════════════════════════════════════════════
def test_export(tmp: Path, out: Path) -> bool:
    from export import usage_report as R
    from openpyxl import load_workbook
    k = True
    pj = R.build('甲项目', out / 'p_zh.xlsx', lang='zh', path=tmp)
    wb = load_workbook(pj)
    k &= ok('B1 ★★★ 导出的是 **xlsx**（用户点名要的格式）'
            '—— 而且真的能被 openpyxl 读回来（不是改后缀的假货）',
            pj.suffix == '.xlsx' and pj.stat().st_size > 2000
            and len(wb.sheetnames) >= 4, f'{pj.stat().st_size} B · {wb.sheetnames}')
    k &= ok('B2 ★★★ 第一个 Sheet **一定是总体信息**（不管什么语言）',
            wb.sheetnames[0] == '总体信息', str(wb.sheetnames))
    # ★ 项目级要有"推演任务"这张表；软件整体**不该有**（那是项目级概念）
    # [EN] ★ Project level must have the "simulation task" table; the software as a whole **must not**
    # [EN] (that is a project-level concept)
    pj_titles = ''.join(wb.sheetnames)
    k &= ok('B3 ★★★ 项目级导出含 **按推演任务统计**；软件整体**不含**它'
            '（两套划分不一样，用户点名区分的）',
            '推演任务' in pj_titles, str(wb.sheetnames))
    gl = R.build(None, out / 'g_zh.xlsx', lang='zh', path=tmp)
    gwb = load_workbook(gl)
    k &= ok('B3b ★★ 软件整体导出**没有**"按推演任务"这张表',
            '推演任务' not in ''.join(gwb.sheetnames), str(gwb.sheetnames))
    # 每张 Sheet 都要有"简单介绍"（用户点名）
    # ⚠ 判据要判**介绍那句话的内容**，不是"前几行字数够 12" ——
    #   第一版用字数，标题本身就有 12 字 ⇒ 把介绍整段删掉也不红。
    # [EN] Every Sheet must have a "brief introduction" (user named this)
    # [EN] ⚠ The criterion must judge **the content of that introduction sentence**, not "the first few
    # [EN] rows have at least 12 characters" --
    # [EN] The first version used character count, and the title itself already had 12 characters =>
    # [EN] deleting the entire introduction still passed.
    _intro_words = ('这是一份', '这张表', '这是逐次', 'Overview of', 'This sheet',
                    'Aggregated across', 'Per-call detail')
    missing = []
    for nm in wb.sheetnames:
        ws = wb[nm]
        txt = ' '.join(str(c.value) for row in ws.iter_rows(max_row=4)
                       for c in row if c.value)
        if not any(w in txt for w in _intro_words):
            missing.append(nm)
    k &= ok('B3c ★★★ **每张 Sheet 都有自己的简短介绍**（用户点名要的）'
            '—— 判的是介绍句的**内容**，不是"前几行字数够"',
            not missing, f'缺介绍的: {missing}')
    # 中英两版
    # [EN] Chinese and English versions
    pe = R.build('甲项目', out / 'p_en.xlsx', lang='en', path=tmp)
    ewb = load_workbook(pe)
    k &= ok('B4 ★★★ 导出支持**中文 / 英语**两版（Sheet 名与表头都跟着换）',
            ewb.sheetnames[0] == 'Overview'
            and 'By Model' in ewb.sheetnames and '总体信息' not in ''.join(ewb.sheetnames),
            str(ewb.sheetnames))
    k &= ok('B4b ★★ 英文版的**数据不跟着变**（只换文案 —— 换语言不该换数）',
            _first_num(ewb) == _first_num(wb), f'{_first_num(ewb)} vs {_first_num(wb)}')
    # 数字来自库
    # ⚠ 判"一致"要拿**库里的值**去比，不许写死一个数字 ——
    #   第一版写死 4，而 A 组后来往同一个库又插了一笔 ⇒ 判据假红。
    # [EN] Numbers come from the database
    # [EN] ⚠ To judge "consistency" you must compare against **the value in the database**, not hard-code a
    # [EN] number --
    # [EN] The first version hard-coded 4, and group A later inserted another row into the same database =>
    # [EN] false red.
    from llm import usage as _U
    _want = _U.totals('甲项目', path=tmp)['calls']
    k &= ok('B5 ★★★ 导出里的总数**与库里一致**（不是另算一遍：拿库里的值比）',
            _find(load_workbook(pj)) == _want,
            f'导出={_find(load_workbook(pj))} 库里={_want}')
    # 文件名 ASCII 安全
    # [EN] File name ASCII-safe
    nm = R.default_name('甲 项目/x', lang='en')
    k &= ok('B5b ★ 默认文件名**不含空格与斜杠**（中文项目名会被换掉，免得写不出去）',
            ' ' not in nm and '/' not in nm and nm.endswith('.xlsx'), nm)
    return k


def _first_num(wb) -> object:
    """总表里"调用次数"那一行的值（用来比对中英两版的数据是否一致）。
        English:
    The value of the "call count" row in the summary table (used to compare whether the data of the
    Chinese and English versions match).
    """
    ws = wb[wb.sheetnames[0]]
    for row in ws.iter_rows():
        vals = [c.value for c in row if c.value is not None]
        if any(str(v) in ('调用次数', 'Calls') for v in vals):
            nums = [v for v in vals if isinstance(v, (int, float))]
            if nums:
                return nums[0]
    return None


def _find(wb) -> object:
    return _first_num(wb)


# ══════════════════════════════════════════════════════════════════
#  C. 两条硬约束：不调模型 / 不落 md + 接线
# [EN] C. Two hard constraints: do not call the model / do not persist md + wiring
# ══════════════════════════════════════════════════════════════════
def test_constraints() -> bool:
    k = True
    src = code_only(read('llm/usage.py'))
    k &= ok('C1 ★★★ 统计层**一次模型调用都没有**（用户："最好这些信息不使用 LLM '
            '动态生成的"）—— 判 `llm/usage.py` 里没有 `ask(` / `llm.chat`',
            'ask(' not in src and 'llm.chat' not in src and 'import httpx' not in src,
            '')
    k &= ok('C2 ★★★ **不落 md**（用户："不要在本地保存 md 等信息"）'
            '—— 统计层里没有任何写 `.md` 的地方',
            '.md' not in src.replace('usage.md', ''), '')
    # 台账落库是**旁路**：失败不许抛
    # [EN] Ledger persistence is a **side path**: failure must not throw
    k &= ok('C3 ★★ 记账是**旁路**：失败只记日志、绝不抛（磁盘满/库被锁不该把一次正常调用弄挂）',
            'except Exception as e:' in src and 'return False' in src, '')
    # 全局位置：不在 logs/（logs 随发布包被排除）
    # ⚠ 判据要判"**有没有把 logs 当路径用**"，不是"文件里有没有 logs 这几个字" ——
    #   第一版用 `'logs' not in src`，撞上了 docstring 里那句"别放 logs/"说明 ⇒ 假红。
    # [EN] Global location: not in logs/ (logs is excluded with the release package)
    # [EN] ⚠ The criterion must judge "**whether logs is used as a path**", not "whether the word logs
    # [EN] appears in the file" --
    # [EN] The first version used `'logs' not in src`, and hit the sentence in a docstring saying "don't
    # [EN] put it in logs/" => false red.
    k &= ok('C3b ★★ 台账库放在**软件根目录**，**不在 `logs/`**'
            '（`logs/` 随发布包被排除 —— 放那儿台账会跟着没）',
            "APP_DIR / 'usage.db'" in src
            and "/ 'logs'" not in src and "'logs' /" not in src, '')
    # ★★ 接线：必须在**那个方法的那个块里**查（不许全文件 grep）
    # [EN] ★★ Wiring: must check **inside that block of that method** (no whole-file grep)
    rt = read('llm/router.py')
    add_blk = between(rt, '    def add(self, rec: UsageRecord) -> None:', '    @property')
    k &= ok('C4 ★★★ `Ledger.add` —— **所有 LLM 调用的唯一汇合点** —— 真的在落库'
            '（块内查，不全文件 grep：那是本项目踩过的坑）',
            'USAGE.record(model=rec.model' in add_blk, add_blk[:80].replace('\n', ' '))
    su = read('sim/setup.py')
    su_blk = between(su, 'db = DB(run.db_path)', 'agents = [Agent(')
    k &= ok('C5 ★★★ 推演装配时把**项目 / 存档**告诉台账（第二层要按它俩划分）'
            '—— 判的是**实参**，不是"出现过 project= 这几个字"',
            "USAGE.set_ctx(module=USAGE.MODULE_SELF" in su_blk
            and "project=str(getattr(project, 'name', '') or '')" in su_blk
            and "run=str(getattr(run, 'name', '') or '')" in su_blk,
            '')
    st = read('crew/studio.py')
    call_blk = between(st, '    async def call(self, key: str', 'self._work_notify')
    k &= ok('C6 ★★★ 出工时把**当前 Agent 名**告诉台账（第三层要按它划分）'
            '—— 在 `Studio.call` 那个块里查，且判的是**非空实参**'
            '（`agent=\'\'` 也含"agent="三个字，第一版就是这么漏掉的）',
            "USAGE.set_ctx(agent=member.role.name" in call_blk,
            '')
    k &= ok('C6b ★★ 出工结束**清掉 Agent 上下文**（免得下一个人的账挂到这个人身上）',
            'clear_ctx' in between(st, '    async def call(self, key: str', 'async def '),
            '')
    return k


# ══════════════════════════════════════════════════════════════════
#  D. GUI：入口 + 四栏
# [EN] D. GUI: entry point + four columns
# ══════════════════════════════════════════════════════════════════
def test_gui() -> bool:
    k = True
    g = read('gui/usage_dialog.py')
    k &= ok('G1 ★★★ 用量对话框有**四栏**（左到右：项目 / 划分卡片 / Agent / 明细）',
            # 四栏**各自**都要被拼进布局里（只数字数会被"删掉一栏但还有 3 个"
            # 骗过；只判名字在不在会被"定义过但没用"骗过）
            # ⚠ 用**带参数的调用形式**判（`_pane(col1, `）—— 函数定义那行是
            #   `def _pane(col: ...)`，用 `_pane(col` 会把定义也算进去（恒多 1）。
            # [EN] Each of the four columns **individually** must be assembled into the layout (counting only
            # [EN] characters is fooled by "one column deleted but 3 remain"
            # [EN] and checking only whether the name is present is fooled by "defined but never used")
            # [EN] ⚠ Judge using **the call form that takes arguments** (`_pane(col1, `) -- the function definition
            # [EN] line is
            # [EN] `def _pane(col: ...)`, so using `_pane(col` would also count the definition (always one too
            # [EN] many).
            all(f'_pane(col{i}, ' in g for i in (1, 2, 3, 4)),
            f"缺={[i for i in (1, 2, 3, 4) if f'_pane(col{i}, ' not in g]}")
    k &= ok('G2 ★★★ 第 2 栏顶上有**下拉框**，且选项**跟着 scope 变**'
            '（软件整体 3 个 / 项目 4 个 —— 用户点名这个区别）'
            '—— 判的是那句**条件表达式**，不是"文件里出现过 BY_FOR_PROJECT"',
            "bys = U.BY_FOR_PROJECT if st['scope'] else U.BY_FOR_GLOBAL" in g,
            '')
    k &= ok('G2b ★★ 第 1 栏是「软件整体 + 各项目」，且**可滚动**'
            '（用户："各个项目可以滚动（如果过多的时候）"）',
            'ScrollMode' in g and 'U.projects(' in g, '')
    # ★★ G3 的**口径**（2026-10-11 改）：原来钉的是**具体算式**
    # [EN] ★★ G3's **scope/definition** (changed 2026-10-11): previously pinned to a **concrete formula**
    #   （`'size * 0.94' in g and 'height * 0.88' in g`）。
    #   用户那天要求「整体 LLM 窗口默认最大化」，比例从 94%/88% 改成
    #   "客户区 − 12px"（铺满），算式当然就变了 ⇒ 这条**假红**。
    #   ⚠ 钉算式本来就是脆的（换个写法就红），而它想守的是"撑开、不是小盒子"。
    #   ⇒ 改成钉**意图**：尺寸必须从**客户区**（`page.width/height`）算、
    #     并且用统一的 `DLG_MARGIN` —— 三者缺一就说明它又退回了"按窗口比例缩"。
    #   ★ 真正"到底撑开多少"由**真机**判据量：`tools/verify_usage_layout.py` 的 A3
    #     （实测对话框宽 ≈ 客户区宽 − 2×边距）。这里只做静态兜底。
    # [EN] ★★ G3's **convention** (changed 2026-10-11): it used to pin the **concrete formula**
    # [EN] (`'size * 0.94' in g and 'height * 0.88' in g`).
    # [EN] That day the user asked to "make the whole LLM window maximized by default", and the ratio
    # [EN] changed from 94%/88% to "client area - 12px" (filling it), so the formula naturally changed ⇒
    # [EN] this became a **false red**.
    # [EN] ⚠ Pinning a formula is brittle by nature (any rewrite turns it red), while what it guards is
    # [EN] "it's stretched open, not a small box".
    # [EN] ⇒ Change it to pin the **intent**: the size must be computed from the **client area**
    # [EN] (`page.width/height`) and use the shared `DLG_MARGIN` -- missing any of the three means it has
    # [EN] fallen back to "scale by window ratio".
    # [EN] ★ How far it actually stretches is measured by the **real-device** criterion instead: A3 in
    # [EN] `tools/verify_usage_layout.py` (measured dialog width ≈ client width - 2*margin). This is only
    # [EN] the static fallback.
    k &= ok('G3 ★★ 对话框**默认最大化**：尺寸从**客户区**算、用统一的边距'
            '（钉意图，不钉算式；"到底撑开多少"由 verify_usage_layout 的 A3 真机量）',
            'page.width' in g and 'page.height' in g and 'DLG_MARGIN' in g
            and 'int(size * 0.94)' not in g,
            '')
    # ★ 2026-10-10 收紧：原来只查 `'ask(' not in 源码` —— 粗口径，会**假红**：
    #   我在删除逻辑里起过一个局部变量叫 `ask`（`ask = getattr(app, ...)`），
    #   当场被这条判据判成"界面调了模型"。**假红比漏报更坏**（看多了就没人看这一项）。
    #   现在两条一起判，两条都是"真去调模型"的必要条件：
    #     ① 源码里**没有把模型入口 import 进来**（`from llm.client import ask` 这种）；
    #     ② 源码里没有对某个模块调 `ask/chat/generate`（`xxx.ask(` 这种）。
    #   ⚠ 但**保留**那条裸 `ask(` 的检查：它是"忘了 import 也调了"的兜底，
    #     代价是"局部变量不能叫 ask"—— 这条已经写进 `gui/usage_dialog.py` 的注释里了。
    # [EN] ★ 2026-10-10 tightened: originally it only checked `'ask(' not in source` -- too coarse, would
    # [EN] produce **false red**:
    # [EN] I had once used a local variable named `ask` in the deletion logic (`ask = getattr(app, ...)`),
    # [EN] and it was immediately flagged by this criterion as "the UI called the model". **False red is
    # [EN] worse than a miss** (no one looks at this item once they've seen too many).
    # [EN] Now the two are judged together, and both are necessary conditions for "actually calling the
    # [EN] model":
    # [EN] ① the source **does not import the model entry point** (`from llm.client import ask` and the
    # [EN] like);
    # [EN] ② the source does not call `ask/chat/generate` on any module (`xxx.ask(` and the like).
    # [EN] ⚠ But **keep** the bare `ask(` check: it is the fallback for "called it even though the import
    # [EN] was forgotten",
    # [EN] at the cost of "a local variable may not be named ask" -- this has been written into the
    # [EN] comments of `gui/usage_dialog.py`.
    _g = code_only(g)
    k &= ok('G4 ★ 界面里的表头/文案**不调模型**（本模块一次 `ask` 都没有；'
            '也不是靠 import 把模型入口拉进来）',
            # ★★ 裸 `ask(` 必须带**词边界**（2026-10-11 修）。
            #   原来是子串检查，于是 `page.run_task(_go)` 里的 `..task(` ——
            #   "t-a-s-k-(" 含子串 **"ask("** —— 被当成"界面调了模型"，当场假红。
            #   这正是这条判据自己的注释警告过的那类假红（"局部变量不能叫 ask"），
            #   只是当时只想到了变量名、没想到**别的函数名里也能套出 ask(**。
            #   `(?<![\w.])` 的含义：`ask(` 前面不能是字母/数字/下划线/点 ——
            #   这样 `run_task(`（前面是 t）、`_ask_delete(`（前面是 _）、
            #   `llm.ask(`（前面是点）都不算，而**光秃秃一句 `ask(...)` 仍然算**。
            # [EN] ★★ The bare `ask(` needs a **word boundary** (fixed 2026-10-11).
            # [EN] It used to be a substring check, so `..task(` inside `page.run_task(_go)` --
            # [EN] "t-a-s-k-(" contains the substring **"ask("** -- was treated as "the UI called the
            # [EN] model", a false red on the spot.
            # [EN] This is exactly the kind of false red this criterion's own comment warned about
            # [EN] ("a local variable may not be named ask"), except back then only variable names were
            # [EN] considered, not "another function name can also contain ask(".
            # [EN] `(?<![\w.])` means: `ask(` must not be preceded by a letter/digit/underscore/dot --
            # [EN] so `run_task(` (preceded by t), `_ask_delete(` (preceded by _) and `llm.ask(`
            # [EN] (preceded by a dot) don't count, while a **bare `ask(...)` still does**.
            not re.search(r'(?<![\w.])ask\s*\(', _g) and 'import httpx' not in _g
            and not re.search(r'from\s+\S*llm\S*\s+import\s+.*\b(ask|chat)\b', _g)
            and not re.search(r'\b\w+\.(ask|chat|generate)\s*\(', _g),
            '')
    # 入口：运行状态条那一行
    # [EN] Entry point: the run status bar row
    a = read('gui/app_flet.py')
    bar = between(a, 'self._refresh_run_status()', 'def show_usage_dialog')
    k &= ok('G5 ★★★ 运行界面上真的加了**入口**（在状态条那一行，与"跑到第几天/'
            '自动落盘"并排）',
            'self._usage_link' in bar and 'on_click=self.show_usage_dialog' in bar, '')
    k &= ok('G5b ★★ 入口走 `t()`（英文界面不许露"用量"两个字）',
            "t('用量')" in a and "t('查看用量')" in a, '')
    i = read('i18n.py')
    k &= ok('G5c ★★ i18n 里两版都有（中英**同现**）',
            "'用量': 'Usage'" in i and "'查看用量': 'View usage'" in i, '')
    k &= ok('G6 ★★ `gui/usage_dialog.py` **不 import `app_flet`**'
            '（否则循环导入 —— 配色是参数传进去的）',
            'from gui.app_flet' not in g and 'import app_flet' not in g
            and 'colors' in g, '')
    # ── 2026-10-11：筛选从"顶上集中一排"搬到**各栏栏头**（用户点名的那件事）──
    #   用户原话：「关于用量 界面设计有问题，你现在最上面那几个筛选功能，希望是除了
    #   最左边列，中间第二个第三个列都有自己的一套筛选，且用合适的**上下文菜单**的
    #   方式放到**每个列的表头上**，而不是单独放一个地方。」
    #   ⚠ 这里判"源码长什么样"是**够用的**：这几条守的是"结构没被改回去"
    #     （顶上又冒出下拉、菜单被挪出栏头）。"点菜单真的改变了内容"那类**行为**
    #     判据在 `tools/verify_usage_filters.py`（真机、GUI 组）——
    #     静态判不了那个，别在这儿硬凑。
    # [EN] -- 2026-10-11: filters moved from "a centralized row at the top" to **each column header** (the
    # [EN] thing the user named) --
    # [EN] User's exact words: "There is a problem with the usage UI design. Those filter functions you
    # [EN] currently have at the very top, I hope that except for the
    # [EN] leftmost column, the second and third columns in the middle each have their own set of filters,
    # [EN] and using a suitable **context menu**
    # [EN] placed on **each column's header**, rather than placed separately in one place."
    # [EN] ⚠ Here judging "what the source looks like" is **sufficient**: these items guard against "the
    # [EN] structure being changed back"
    # [EN] (a dropdown reappearing at the top, the menu being moved out of the column header).
    # [EN] Behavior-type things like "clicking the menu actually changes the content"
    # [EN] have their criterion in `tools/verify_usage_filters.py` (real machine, GUI group) --
    # [EN] that cannot be judged statically, so don't force it here.
    g_code = code_only(g)
    tr = between(g, 'tools_row = ft.Row([', '], spacing=8, wrap=True)')
    k &= ok('G7 ★★★ 顶上那排**不再集中放筛选**（工具行里只剩导出；'
            '原来那两个「划分 / 自」下拉已经删干净）',
            bool(tr) and 'by_dd' not in tr and 'since_dd' not in tr
            and 'by_dd' not in g_code and 'since_dd' not in g_code,
            f'工具行={tr[:70]!r}')
    hb = between(g, 'def build_heads()', 'def _pick_scope(')
    k &= ok('G8 ★★★ 四栏**各有栏头**，且栏头是每栏的第一个子控件（"表头"该在的位置）',
            hb.count('_head(') >= 4
            and all(f'head{i}.content = _head(' in hb for i in (1, 2, 3, 4))
            and all(f'_pane(col{i}, ' in g for i in (1, 2, 3, 4))
            and 'kids += [head, ft.Divider(' in g,
            f'栏头调用 {hb.count("_head(")} 次')
    i2, i3, i4 = (hb.find('head2.content'), hb.find('head3.content'),
                  hb.find('head4.content'))
    by_at = hb.find("tag='by'")
    since_at, agent_at = hb.find("tag='since'"), hb.find("tag='agent'")
    k &= ok('G9 ★★★ 三个菜单挂在**对的栏头**上（划分 → 第 2 栏；'
            '时间范围 + Agent 筛选 → 第 3 栏；第 1 / 4 栏不挂）',
            -1 not in (i2, i3, i4, by_at, since_at, agent_at)
            and i2 < by_at < i3 and i3 < since_at < i4 and i3 < agent_at < i4,
            f'位置 head2={i2} by={by_at} head3={i3} since={since_at} '
            f'agent={agent_at} head4={i4}')
    k &= ok('G10 ★★★ 第 3 栏自己那套筛选**真的接进去**了（不是摆着好看）',
            'def _apply_agent_filter' in g
            and '_apply_agent_filter(' in between(g, 'def build_col3()',
                                                  'def build_col4()'),
            '')
    k &= ok('G10b ★★ 菜单里**当前项带勾**（换成菜单之后最容易丢掉的信息：'
            '"现在筛的是哪个"要用眼睛读得出来）',
            'checked=bool(cur)' in g, '')
    k &= ok('G11 ★★ 栏头的小字会复述当前筛选（图标按钮本身看不出状态）',
            "t('时间：{v}', v=_since_text())" in g
            and "t('筛选：{v}', v=_agent_text())" in g, '')
    return k


def main() -> int:
    tmpdir = Path(tempfile.mkdtemp(prefix='nws_usage_'))
    db = tmpdir / 'usage.db'
    out = tmpdir / 'out'
    checks = [('数据层', lambda: test_data(db)),
              ('删除', lambda: test_delete(tmpdir)),
              ('导出', lambda: test_export(db, out)),
              ('硬约束与接线', test_constraints),
              ('界面', test_gui)]
    for name, fn in checks:
        try:
            fn()
        except Exception:                                        # noqa: BLE001
            REPORT['checks'].append({'name': f'{name} 组崩了', 'ok': False,
                                     'detail': traceback.format_exc()[-900:]})
    p = APP / 'assets' / 'screenshots' / 'usage_stats_report.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
    bad = [c for c in REPORT['checks'] if not c['ok']]
    n = len(REPORT['checks'])
    print(f'\nLLM 用量统计验证：{n - len(bad)}/{n}')
    for c in bad:
        print(f'  ✗ {c["name"]}')
        if c['detail']:
            print(f'      {c["detail"][:400]}')
    print('→ 全部通过' if not bad else '→ 有失败项')
    print('报告 ->', p.relative_to(APP))
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
