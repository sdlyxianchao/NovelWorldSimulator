# -*- coding: utf-8 -*-
"""LLM 用量台账：**落库、聚合、导出**（用户 2026-10-10 的第二个需求）。

用户原话（要点）
----------------
「现在有大量的模块用到 LLM，我希望在运行界面的合适位置加一个链接，点进去之后
可以看到**当前项目以及软件整体**最近一段时间来的 LLM Token 使用情况（Token 量以及费用）……
最好这些信息**不使用 LLM 动态生成**的，而且**不要在本地保存 md 等信息**，
默认统计信息**存入数据库**，然后需要的时候使用软件动态生成界面各个元素……
还希望可以支持**导出报告**，最好是导出 **xlsx** 格式（默认是软件整体或者某个项目
这个级别导出，再下一层不支持），导出时支持选择**中文还是英语**，不同的统计信息
**按照 Sheet 区分**。第一个 Sheet 一定是**总体信息**，后续每个 Sheet 包含自己的
**简单介绍信息和详细统计信息**。」

这个模块解决三件事
------------------
1. **落库** —— 全项目原来只有一个「内存账本」（`llm/router.Ledger`），
   进程一退就没了；`store/db.budget_log` 表建了、`add_budget()` 也写好了，
   但**全项目没有一处调用过它**（又一个"假按钮"）。这里把每一次调用
   落进一个**全局** sqlite 库。
2. **聚合** —— 全部走 SQL + 纯计算，**不调模型**（用户点名要求）。
3. **导出 xlsx** —— 多 Sheet、中英双语、第一张是总体。

为什么是**全局**一个库（而不是各项目的 `state.db`）
--------------------------------------------------
运行文件夹里那份 `state.db` 是**一次推演**的库；而用户要的是"**软件整体**"的
口径 —— 它必须跨项目、跨存档。所以另开一个库放在软件根目录，
与 `.env` 平级（`logs/` 会随发布包被排除，不能放那儿）。

★ 与 `llm/router.Ledger`（内存账本）的分工
------------------------------------------
Ledger 管的是**进程内的即时判断**（今日额度、超支告警），它必须快、不落盘；
这里管的是**历史与跨项目统计**，它必须持久。两边各记一份是有意的：
**不要**为了"避免重复"把 Ledger 改成读库 —— 那会让每次调用都碰磁盘。

English:
LLM usage ledger: **persist to DB, aggregate, export** (the user's second requirement on
2026-10-10).
User's exact words (key points)
----------------
"Now a large number of modules use LLM; I want a link added at a suitable place in the run UI,
and after clicking in
you can see the **current project as well as the whole software**'s recent LLM Token usage
(Token amount and cost)……
it would be best if this information is **not dynamically generated using LLM**, and **do not
save md etc. locally**,
by default the statistics are **stored into the database**, then when needed use the software to
dynamically generate the various UI elements……
also hope it can support **exporting reports**, preferably exporting **xlsx** format (by default
at the whole-software or a single project
level export; the next level down is not supported), and when exporting support choosing
**Chinese or English**, with different statistics
**separated by Sheet**. The first Sheet is always the **overall information**, and each
subsequent Sheet contains its own
**brief introduction information and detailed statistics information**."
This module solves three things
------------------
1. **Persist to DB** —— the whole project originally had only one "in-memory ledger" (`llm/router.Ledger`),
   which vanishes once the process exits; the `store/db.budget_log` table was created and `add_budget()` was written,
   but **nowhere in the whole project has it ever been called** (yet another "fake button"). Here we persist every call
   into a **global** sqlite library.
2. **Aggregation** —— everything goes through SQL + pure computation, **no model calls** (the user explicitly required this).
3. **Export xlsx** —— multiple Sheets, bilingual Chinese/English, the first being the overall.
Why a **global** library (instead of each project's `state.db`)
--------------------------------------------------
The `state.db` in the run folder is the library of **a single simulation**; whereas what the
user wants is the "**whole software**"
perspective —— it must span projects and saves. So open a separate library placed in the
software root directory,
at the same level as `.env` (`logs/` is excluded from release packages, so it cannot go there).
★ Division of labor with `llm/router.Ledger` (the in-memory ledger)
------------------------------------------
Ledger handles **in-process immediate judgment** (today's quota, overspend alerts); it must be
fast and not persisted;
here we handle **history and cross-project statistics**, which must be persistent. Recording a
copy on both sides is intentional:
**do not** change Ledger to read the DB just to "avoid duplication" —— that would touch disk on
every call.
"""
from __future__ import annotations

import contextvars
import logging
import sqlite3
import time
from datetime import date, datetime
from pathlib import Path

_LOG = logging.getLogger('nws.usage')

APP_DIR = Path(__file__).resolve().parent.parent

#: 模块名 —— 用来区分"这笔钱是哪个模块花的"。
#: 用户点名要有这一层（"比如 NovelWorldSimulator 本身，MuMuAINovel 模块，
#: 以及后续其他会引入的模块"），所以它是一等字段，不是备注。
# [EN] : module name —— used to distinguish "which module spent this money".
# [EN] : the user explicitly asked for this layer ("e.g. NovelWorldSimulator itself, the MuMuAINovel
# [EN] module,
# [EN] : and other modules introduced later"), so it is a first-class field, not a remark.
MODULE_SELF = 'NovelWorldSimulator'
MODULE_MUMU = 'MuMuAINovel'

# ── 上下文（每次调用都要带的四样：模块 / 项目 / 存档 / Agent）──────────
# 用 `contextvars` 而不是全局变量：推演可能并发（`sim` 里就有并行段），
# 全局变量在并发下会把 A 的 Agent 名记到 B 的账上。
# [EN] ── Context (the four things carried on every call: module / project / save / Agent) ──────────
# [EN] Use `contextvars` instead of globals: simulation may be concurrent (there are parallel sections
# [EN] in `sim`),
# [EN] globals under concurrency would charge A's Agent name to B's account.
_CTX: contextvars.ContextVar[dict] = contextvars.ContextVar('nws_usage_ctx', default={})


def set_ctx(**kw) -> None:
    """设置当前上下文（`module` / `project` / `run` / `agent`）。

    ★ **只覆盖给了的键**（没给的保持原样）—— 否则设一次 `agent` 会把
      `project` 抹掉，而调用方通常是分散设置的（`sim/setup` 设项目，
      `crew/studio` 设 Agent）。
    
        English:
    Set the current context (`module` / `project` / `run` / `agent`).
        ★ **only overwrite the keys provided** (leave the rest as-is) —— otherwise setting `agent` once would wipe out
          `project`, whereas callers usually set them separately (`sim/setup` sets the project,
          `crew/studio` sets the Agent).
    """
    cur = dict(_CTX.get() or {})
    for k in ('module', 'project', 'run', 'agent'):
        if k in kw and kw[k] is not None:
            cur[k] = str(kw[k])
    _CTX.set(cur)


def clear_ctx(*keys: str) -> None:
    """清掉几个键（**不传就全清**）。用在"一轮结束/换人"的地方。
        English:
    Clear a few keys (**if none passed, clear all**). Used at places like "end of a round / change
    of person".
    """
    cur = dict(_CTX.get() or {})
    for k in (keys or tuple(cur)):
        cur.pop(k, None)
    _CTX.set(cur)


def ctx() -> dict:
    return dict(_CTX.get() or {})


# ══════════════════════════════════════════════════════════════════
#  库
# [EN] Library
# ══════════════════════════════════════════════════════════════════
_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL    NOT NULL,
    day      TEXT    NOT NULL,          -- YYYY-MM-DD（**落库时算好**：SQL 里按天分组不必再转换）
    module   TEXT    NOT NULL DEFAULT '',
    project  TEXT    NOT NULL DEFAULT '',
    run      TEXT    NOT NULL DEFAULT '',   -- 存档名（"第2次模拟2026-10-10-01-30"）
    agent    TEXT    NOT NULL DEFAULT '',
    model    TEXT    NOT NULL DEFAULT '',
    purpose  TEXT    NOT NULL DEFAULT '',
    tier     TEXT    NOT NULL DEFAULT '',
    in_tok   INTEGER NOT NULL DEFAULT 0,
    out_tok  INTEGER NOT NULL DEFAULT 0,
    cost     REAL    NOT NULL DEFAULT 0.0,
    -- ★ 2026-10-12：这次输入里**命中前缀缓存**的 token 数（0 = 没命中或对方不报）。
    --   为什么要单独存：DeepSeek 的命中价是未命中的 **1/10 上下**，这一列是
    --   "我们省下了多少钱"唯一的量化依据 —— 不存下来，用户永远看不到缓存有没有生效。
    -- [EN] ★ 2026-10-12: how many input tokens **hit the prefix cache** this time (0 = no hit or the
    -- [EN] provider doesn't report it). Why store it separately: DeepSeek's hit price is about
    -- [EN] **1/10** of the miss price, and this column is the only quantitative basis for "how much
    -- [EN] we saved" -- without it, the user can never tell whether caching is working.
    cache_tok INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_usage_day     ON usage_log(day);
CREATE INDEX IF NOT EXISTS idx_usage_project ON usage_log(project, day);
CREATE INDEX IF NOT EXISTS idx_usage_module  ON usage_log(module, day);
"""

#: 后加的列（**老库要补**）：`CREATE TABLE IF NOT EXISTS` 对已存在的表什么都不做，必须显式 `ALTER TABLE`。
# [EN] : columns added later (**old databases must be patched**): `CREATE TABLE IF NOT EXISTS` does
# [EN] nothing to an existing table, so `ALTER TABLE` is required.
_LATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ('cache_tok', 'INTEGER NOT NULL DEFAULT 0'),
)


def db_path() -> Path:
    """全局台账库的位置（软件根目录，与 `.env` 平级）。

    ⚠ **不要**放 `logs/`：那个目录随发布包被排除，台账跟着没。
    
        English:
    Location of the global ledger library (software root directory, at the same level as `.env`).
        ⚠ **do not** put it in `logs/`: that directory is excluded from release packages, and the ledger would disappear with it.
    """
    return APP_DIR / 'usage.db'


def _conn(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p), timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    _migrate(c)
    _tune(c)
    return c


def _migrate(c: sqlite3.Connection) -> None:
    """把老库缺的列补上（现在只有 `cache_tok`）。

    ★ 为什么必须显式做（2026-10-12）：`CREATE TABLE IF NOT EXISTS` 对**已存在**的表
      **一行都不改** —— 只往 `_SCHEMA` 里加列，老用户升级后每一次 `record()`
      都会撞 `no such column: cache_tok`，而且 `record()` 是"失败只记日志"的旁路，
      **于是记账静默全废、界面上什么错都看不到**。这类"新列只在新建库时存在"的坑，
      在 SQLite 项目里很常见。
    
        English:
    Add the columns an old database is missing (currently only `cache_tok`).
        ★ Why it must be done explicitly (2026-10-12): `CREATE TABLE IF NOT EXISTS` **changes
          nothing** on an **existing** table -- just adding a column to `_SCHEMA` means every
          `record()` by an upgraded user hits `no such column: cache_tok`, and since `record()`
          is a "log on failure only" bypass, **bookkeeping silently dies with no visible error**.
          This "a new column only exists in a newly created database" trap is common in SQLite
          projects.
    """
    try:
        have = {str(r[1]) for r in c.execute('PRAGMA table_info(usage_log)').fetchall()}
    except Exception:                                            # noqa: BLE001
        return
    for name, decl in _LATE_COLUMNS:
        if name not in have:
            try:
                c.execute(f'ALTER TABLE usage_log ADD COLUMN {name} {decl}')
            except Exception as e:                               # noqa: BLE001
                _LOG.warning('补列 %s 失败：%r', name, e)
    try:
        c.commit()
    except Exception:                                            # noqa: BLE001
        pass


def _tune(c: sqlite3.Connection) -> None:
    """让库**别把整份文件重写一遍**。

    ★ 为什么（2026-10-12 实测）：这个库默认放在**程序根目录**，而用户把它放在
      OneDrive 同步盘里。库长到 30MB / 14.6 万行之后，一次 `INSERT + COMMIT` 要
      **45 秒** —— 因为回滚日志模式（delete）每次提交都要把整份主库刷一遍，
      而 OneDrive 要把这 30MB 重新上传。表现是"判据无端超时"，实际是**磁盘在同步**。
    · `journal_mode=WAL`：写只追加到 `-wal` 小文件，**主库不被整份重写**；
    · `synchronous=NORMAL`：WAL 下的推荐档位（掉电最多丢最后一笔，记账可接受）。
      ⚠ 这是**持久设置**（写进库文件），设一次就长期生效，所以放这里是幂等的。
    · `wal_autocheckpoint` 调小一点：别让 `-wal` 长到又要整份同步。
    
        English:
    Make the database **stop rewriting the whole file**.
        ★ Why (measured 2026-10-12): this database lives in the **program root**, and users put it on
          a OneDrive-synced drive. Once it grows to 30MB / 146k rows, one `INSERT + COMMIT` takes
          **45 seconds** -- because in rollback-journal (delete) mode every commit flushes the
          entire main database, and OneDrive re-uploads those 30MB. It looks like "a criterion
          timing out for no reason", but it is actually **the disk syncing**.
          · `journal_mode=WAL`: writes only append to a small `-wal` file, so the **main database is
            not rewritten wholesale**;
          · `synchronous=NORMAL`: the recommended level under WAL (at worst the last transaction is
            lost on power failure; acceptable for bookkeeping).
            ⚠ This is a **persistent setting** (written into the database file) and applies once, so
            it is idempotent here.
          · A smaller `wal_autocheckpoint`: don't let `-wal` grow to where it needs a full sync
            again.
    """
    for pragma in ('PRAGMA journal_mode=WAL',
                   'PRAGMA synchronous=NORMAL',
                   'PRAGMA wal_autocheckpoint=400'):
        try:
            c.execute(pragma)
        except Exception as e:                                   # noqa: BLE001
            _LOG.debug('PRAGMA 设置跳过（%s）：%r', pragma, e)


def record(*, model: str, purpose: str = '', in_tok: int = 0, out_tok: int = 0,
           cost: float = 0.0, tier: str = '', ts: float | None = None,
           cache_tok: int = 0,
           path: Path | None = None, **ctx_over) -> bool:
    """记一笔。**失败只记日志、绝不抛** —— 记账不该把一次正常的调用弄挂。

    ★ 这条"失败不抛"是刻意的：它是**旁路**。旁路把自己变成故障源，
      是这类模块最常见的翻车方式（磁盘满 / 库被锁）。
    
        English:
    Record an entry. **On failure only log, never throw** —— bookkeeping should not break a normal
    call.
        ★ This "failure does not throw" is deliberate: it is a **bypass**. A bypass turns itself into a failure source,
          which is the most common way this kind of module crashes (disk full / locked database).
    """
    c = ctx()
    c.update({k: str(v) for k, v in ctx_over.items() if v is not None})
    t = float(ts if ts is not None else time.time())
    try:
        conn = _conn(path)
        try:
            conn.execute(
                'INSERT INTO usage_log(ts, day, module, project, run, agent, model,'
                ' purpose, tier, in_tok, out_tok, cost, cache_tok)'
                ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (t, date.fromtimestamp(t).isoformat(),
                 c.get('module', '') or MODULE_SELF, c.get('project', ''),
                 c.get('run', ''), c.get('agent', ''), str(model or ''),
                 str(purpose or ''), str(tier or ''),
                 int(in_tok or 0), int(out_tok or 0), float(cost or 0.0),
                 max(0, int(cache_tok or 0))))
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('用量落库失败（不影响调用）：%r', e)
        return False


# ══════════════════════════════════════════════════════════════════
#  聚合（**全 SQL / 纯计算，不调模型**）
# [EN] Aggregation (**all SQL / pure computation, no model calls**)
# ══════════════════════════════════════════════════════════════════
#: 第二层的划分方式。用户点名的两套：
#:   软件整体 —— 模型 / 日期 / 模块
#:   某个项目 —— 模型 / 日期 / 推演任务 / 模块
# [EN] : the partitioning scheme of the second layer. The two sets the user named:
# [EN] :   whole software —— model / date / module
# [EN] :   a single project —— model / date / simulation task / module
BY_MODEL, BY_DAY, BY_MODULE, BY_RUN = '模型', '日期', '模块', '推演任务'
BY_ORDER: tuple[str, ...] = (BY_MODEL, BY_DAY, BY_MODULE, BY_RUN)
#: 软件整体能用的划分（没有"推演任务"—— 那是项目级的概念）
# [EN] : the partitions available for the whole software (no "simulation task" —— that is a
# [EN] project-level concept)
BY_FOR_GLOBAL: tuple[str, ...] = (BY_MODEL, BY_DAY, BY_MODULE)
BY_FOR_PROJECT: tuple[str, ...] = (BY_MODEL, BY_DAY, BY_RUN, BY_MODULE)
#: 划分方式 → 库里的列
# [EN] : partitioning scheme → columns in the library
_BY_COL = {BY_MODEL: 'model', BY_DAY: 'day', BY_MODULE: 'module', BY_RUN: 'run'}
#: 四种划分的中英名（导出 xlsx 时要按语言换）
# [EN] : the Chinese and English names of the four partitions (must switch by language when exporting
# [EN] xlsx)
BY_EN = {BY_MODEL: 'Model', BY_DAY: 'Date', BY_MODULE: 'Module', BY_RUN: 'Run'}

#: 「没有值」那一档的标签。**数据层只负责拼出来，翻译是界面的事。**
# [EN] : the label for the "no value" bucket. **The data layer is only responsible for assembling it;
# [EN] translation is the UI's job.**
#:
#: ⚠ 它同时是**不透明的 key**：第三层那个 `（未标：purpose）` 会原样回传给
#:   `detail()` 当过滤条件（见那边 `startswith(UNLABELED_PREFIX)` 那一支）。
#:   所以界面**只翻"显示"的那一份**，绝对不许改这个值本身。
#:   这两条常量存在的意义就是"界面不用把中文写死一遍"（写死就会跟这里漂移）。
# [EN] : ⚠ it is also an **opaque key**: the `（未标：purpose）` in the third layer will be passed back
# [EN] verbatim to
# [EN] :   `detail()` as a filter condition (see the `startswith(UNLABELED_PREFIX)` branch over there).
# [EN] : so the UI **only translates the "display" copy**, and absolutely must not change this value
# [EN] itself.
# [EN] : the whole point of these two constants is "the UI does not have to hardcode the Chinese once"
# [EN] (hardcoding would drift from here).
UNLABELED = '（未标）'
UNLABELED_PREFIX = '（未标：'


def _unlabeled_sql() -> str:
    """SQL 里"未标"那一档的表达式：`（未标：<purpose>）`。

    ★ 为什么收成一个函数：`agents()` 要用它**拼出**标签，`detail()` 要用它
      **对回来**当过滤条件。两处若各写一遍，改了前缀就会出现
      "点得进去、查不出东西"（点一个 Agent → 明细空）—— 这种错**不报错**。
    
        English:
    The expression for the "unlabeled" tier in SQL: `(unlabeled: <purpose>)`.
        ★ Why fold it into one function: `agents()` needs it to **compose** labels, `detail()` needs it
          **to reverse** them back as filter conditions. If both places wrote it separately, changing the prefix would cause
          "clickable but nothing queryable" (click an Agent -> empty detail) -- this kind of bug **does not raise an error**.
    """
    return f"'{UNLABELED_PREFIX}' || purpose || '）'"


def _where(scope: str | None, since: str | None = None) -> tuple[str, list]:
    """`scope=None` ⇒ 软件整体；否则限定某个项目。
        English:
    `scope=None` => whole software; otherwise limited to a certain project.
    """
    sql, args = '', []
    if scope:
        sql += ' AND project = ?'
        args.append(str(scope))
    if since:
        sql += ' AND day >= ?'
        args.append(str(since))
    return sql, args


def totals(scope: str | None = None, *, since: str | None = None,
           path: Path | None = None) -> dict:
    """总体：调用次数 / 入出 token / 费用 / 涉及几个模型与模块。
        English:
    Overall: call count / input-output tokens / cost / how many models and modules involved.
    """
    w, args = _where(scope, since)
    try:
        conn = _conn(path)
        try:
            r = conn.execute(
                'SELECT COUNT(*) n, COALESCE(SUM(in_tok),0) ti, COALESCE(SUM(out_tok),0) to2,'
                ' COALESCE(SUM(cost),0) c, COUNT(DISTINCT model) nm,'
                ' COALESCE(SUM(cache_tok),0) ct,'
                ' COUNT(DISTINCT module) nmod, COUNT(DISTINCT agent) na,'
                ' MIN(day) d0, MAX(day) d1 FROM usage_log WHERE 1=1' + w, args).fetchone()
        finally:
            conn.close()
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('读用量失败：%r', e)
        return {'calls': 0, 'in_tok': 0, 'out_tok': 0, 'cost': 0.0, 'cache_tok': 0,
                'models': 0, 'modules': 0, 'agents': 0, 'first_day': '', 'last_day': ''}
    return {'calls': r['n'], 'in_tok': r['ti'], 'out_tok': r['to2'], 'cost': r['c'],
            'cache_tok': r['ct'],
            'models': r['nm'], 'modules': r['nmod'], 'agents': r['na'],
            'first_day': r['d0'] or '', 'last_day': r['d1'] or ''}


def groups(scope: str | None, by: str, *, since: str | None = None,
           path: Path | None = None) -> list[dict]:
    """第二层：按 `by` 分组（模型 / 日期 / 模块 / 推演任务）。

    返回 `[{key, calls, in_tok, out_tok, cost, agents}]`（按费用降序）。
    
        English:
    Second layer: grouped by `by` (model / date / module / reasoning task).
        Returns `[{key, calls, in_tok, out_tok, cost, agents}]` (sorted by cost descending).
    """
    col = _BY_COL.get(by)
    if not col:
        return []
    w, args = _where(scope, since)
    try:
        conn = _conn(path)
        try:
            rows = conn.execute(
                f'SELECT {col} AS k, COUNT(*) n, COALESCE(SUM(in_tok),0) ti,'
                f' COALESCE(SUM(out_tok),0) to2, COALESCE(SUM(cost),0) c,'
                f' COALESCE(SUM(cache_tok),0) ct,'
                f' COUNT(DISTINCT agent) na FROM usage_log WHERE 1=1' + w
                + f' GROUP BY {col} ORDER BY c DESC, n DESC', args).fetchall()
        finally:
            conn.close()
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('分组失败：%r', e)
        return []
    return [{'key': str(r['k'] or UNLABELED), 'calls': r['n'], 'in_tok': r['ti'],
             'out_tok': r['to2'], 'cost': r['c'], 'cache_tok': r['ct'],
             'agents': r['na']} for r in rows]


def purposes(*, days: float | None = 7, scope: str | None = None,
             path: Path | None = None) -> list[dict]:
    """按 **purpose（用途）** 汇总 —— 「钱花在哪一步」的那张表。

    ★★ 为什么单独一支（而不是再给 `groups()` 加一个 `by`）：
      `groups()` 的 `by` 是**用户可选的四个维度**（模型/日期/模块/推演任务），
      它们都会出现在用量窗口的第二栏里；`purpose` **不是**那一栏的选项
      （它比"模块"细、比"Agent"粗，属于**诊断口径**）。
      混进去会让用户在下拉里看到一个他不知道该不该选的东西。

    ★★★ 2026-11-01（用户：「我想看看 LLM 花费到底花在哪」）：
      这一支是**唯一实现** —— `tools/report_llm_cost.py` 与「天机 · 花费与优化」
      那一页**都**从这里取数。两边各写一份 SQL 是本项目最老的坑
      （改了阈值一边变、另一边还是老口径，而界面看着一切正常）。

    返回 `[{purpose, calls, in_tok, out_tok, cache_tok, cost, hit}]`，按 `in+out` 降序。
    `hit` = 命中厂商前缀缓存的比例（`cache_tok / in_tok`，`in_tok=0` 时算 0）。
        English:
    Aggregate by **purpose** -- the table that answers "which step spent the money".
    ★★ Why a separate function: `groups()`'s `by` is the **four user-facing dimensions**
      (model/day/module/run); `purpose` is a **diagnostic** cut, not one of them.
    ★★★ 2026-11-01: this is the **single implementation** -- both the CLI report and the
      "Cost & Tuning" tab read from here. Two copies of the same SQL is this project's
      oldest trap (one side changes, the other keeps the old convention, and the UI looks fine).
    Returns `[{purpose, calls, in_tok, out_tok, cache_tok, cost, hit}]`, sorted by `in+out` desc.
    """
    since = None if days is None else (
        date.fromtimestamp(time.time() - float(days) * 86400).isoformat())
    w, args = _where(scope, since)
    try:
        conn = _conn(path)
        try:
            rows = conn.execute(
                'SELECT purpose AS p, COUNT(*) n, COALESCE(SUM(in_tok),0) ti,'
                ' COALESCE(SUM(out_tok),0) to2, COALESCE(SUM(cache_tok),0) ct,'
                ' COALESCE(SUM(cost),0) c FROM usage_log WHERE 1=1' + w
                + ' GROUP BY p ORDER BY ti + to2 DESC', args).fetchall()
        finally:
            conn.close()
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('按用途汇总失败：%r', e)
        return []
    out = []
    for r in rows:
        tin = int(r['ti'] or 0)
        out.append({'purpose': str(r['p'] or UNLABELED), 'calls': r['n'],
                    'in_tok': tin, 'out_tok': int(r['to2'] or 0),
                    'cache_tok': int(r['ct'] or 0), 'cost': r['c'],
                    'hit': (int(r['ct'] or 0) / tin) if tin else 0.0})
    return out


def agents(scope: str | None, by: str, key: str, *, since: str | None = None,
           path: Path | None = None) -> list[dict]:
    """第三层：在某个分组下，按 **Agent** 拆。

    ★ "Agent" 这一栏对**没有 Agent 概念**的调用（比如开卷时的抽取）填的是
      模块自己的用途名（`purpose`）—— 否则那一大块开销会全落到"（未标）"里，
      而它恰恰是开卷最贵的一段。
    
        English:
    Third layer: under a certain group, split by **Agent**.
        ★ The "Agent" column, for calls with **no Agent concept** (e.g. extraction at open-book), is filled with
          the module's own purpose name (`purpose`) -- otherwise that entire chunk of cost would all fall into "(unlabeled)",
          and it is precisely the most expensive stretch of open-book.
    """
    col = _BY_COL.get(by)
    if not col:
        return []
    w, args = _where(scope, since)
    args = [str(key), *args]
    # ★ 拼接用的是同一个函数（不是再写一遍中文）——
    #   界面靠 `UNLABELED_PREFIX` 认出"这是未标那一档、要翻"，两边写死就会漂移。
    # [EN] ★ concatenation uses the same function (not rewriting the Chinese) ——
    # [EN] the UI relies on `UNLABELED_PREFIX` to recognize "this is the unlabeled bucket, needs
    # [EN] translating"; hardcoding both sides would drift.
    _unk = _unlabeled_sql()
    try:
        conn = _conn(path)
        try:
            rows = conn.execute(
                f"SELECT CASE WHEN agent = '' THEN {_unk} ELSE agent END AS a,"
                f' COUNT(*) n, COALESCE(SUM(in_tok),0) ti, COALESCE(SUM(out_tok),0) to2,'
                f' COALESCE(SUM(cache_tok),0) ct,'
                f' COALESCE(SUM(cost),0) c FROM usage_log WHERE {col} = ?' + w
                + ' GROUP BY a ORDER BY c DESC, n DESC', args).fetchall()
        finally:
            conn.close()
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('Agent 分组失败：%r', e)
        return []
    return [{'agent': str(r['a'] or UNLABELED), 'calls': r['n'], 'in_tok': r['ti'],
             'out_tok': r['to2'], 'cost': r['c'], 'cache_tok': r['ct']} for r in rows]


def detail(scope: str | None, by: str, key: str, agent: str = '', *,
           since: str | None = None, limit: int = 400,
           path: Path | None = None) -> list[dict]:
    """第四层：明细（每次调用一行）。给表格用。
        English:
    Fourth layer: detail (one row per call). For tables.
    """
    col = _BY_COL.get(by)
    if not col:
        return []
    w, args = _where(scope, since)
    args = [str(key), *args]
    sql = f'SELECT ts, day, module, project, run, agent, model, purpose, tier,' \
          f' in_tok, out_tok, cost, cache_tok FROM usage_log WHERE {col} = ?' + w
    if agent:
        if agent.startswith(UNLABELED_PREFIX):
            # ⚠ 2026-10-14 修（**双重错**）：
            #   ① `_unk` 这个名字只在 `agent_groups()` 里定义过 —— `detail()` 够不着
            #      ⇒ 直接 `NameError`（`detail()` 够不着那个名字）；
            #   ② 就算够得着，`_unk()` 也是**在调用一个字符串**（`_unlabeled_sql()`
            #      返回的是 SQL 片段，不是函数）⇒ `TypeError: 'str' object is not callable`。
            #   而本文件 `_unlabeled_sql()` 的注释里写的**正是这个用法**：
            #   "`detail()` 要用它**对回来**当过滤条件" —— 设计是对的，代码写错了。
            #   后果：在用量窗口点「未标注」那一档看明细 ⇒ 抛异常 ⇒ 明细空
            #   （或者整个对话框报错）。判据 `tools/verify_usage_stats.py` 没覆盖到
            #   这一条路径，所以一直没被发现。
            # [EN] ⚠ Fixed 2026-10-14 (**doubly wrong**):
            # [EN] ① the name `_unk` is only ever defined inside `agent_groups()` -- `detail()`
            # [EN]   cannot reach it => `NameError`;
            # [EN] ② even if it could, `_unk()` would be **calling a string**
            # [EN]   (`_unlabeled_sql()` returns an SQL fragment, not a function) =>
            # [EN]   `TypeError: 'str' object is not callable`.
            # [EN] And the docstring of `_unlabeled_sql()` in this very file describes **exactly
            # [EN] this usage**: "`detail()` needs it **to reverse** them back as filter
            # [EN] conditions" -- the design is right, the code was wrong.
            # [EN] Consequence: clicking the "unlabeled" bucket in the usage window to view
            # [EN] details raises, so the detail list is empty (or the whole dialog errors).
            # [EN] `tools/verify_usage_stats.py` never covered this path, so it went unnoticed.
            sql += f" AND agent = '' AND ({_unlabeled_sql()}) = ?"
            args.append(agent)
        else:
            sql += ' AND agent = ?'
            args.append(agent)
    sql += ' ORDER BY ts DESC LIMIT ?'
    args.append(int(limit))
    try:
        conn = _conn(path)
        try:
            rows = conn.execute(sql, args).fetchall()
        finally:
            conn.close()
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('明细失败：%r', e)
        return []
    return [dict(r) for r in rows]


def projects(path: Path | None = None) -> list[dict]:
    """有哪些项目（最左那一列）。按费用降序。
        English:
    Which projects there are (the leftmost column). Sorted by cost descending.
    """
    try:
        conn = _conn(path)
        try:
            rows = conn.execute(
                "SELECT project AS p, COUNT(*) n, COALESCE(SUM(cost),0) c,"
                " COALESCE(SUM(in_tok+out_tok),0) t FROM usage_log"
                " WHERE project <> '' GROUP BY project ORDER BY c DESC").fetchall()
        finally:
            conn.close()
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('读项目失败：%r', e)
        return []
    return [{'name': str(r['p']), 'calls': r['n'], 'cost': r['c'], 'tokens': r['t']}
            for r in rows]


def delete_project(project: str, path: Path | None = None) -> int:
    """删掉**某个项目**的全部用量记录。返回删掉的行数；**`-1` = 没删成**。

    ★ 为什么要有它（用户 2026-10-10 的要求：「最左边一列的内容允许删除」）：
      台账是**只增不减**的 —— 项目删掉了 / 名字改了，它的记录会**永远**留在
      最左那一栏里，越攒越多。没有"删掉这一项"的口子，那一栏就只能一直烂下去。

    ★★ 三个刻意的设计（都是"错了就不可恢复"逼出来的）
    -------------------------------------------------
    1. **空项目名不许删。** 传 `''` 直接返回 0、**一行都不碰**。
       不这么写会有一个**灾难性**的形态：`record()` 里 `project` 的默认值就是
       `''`（没有项目上下文的调用 —— 比如开卷那一段），所以库里有**一大块**
       空项目名的记录。一次误调 `delete_project('')` 会把**软件整体的绝大部分账**
       抹掉，而且**返回一个漂亮的"删了 N 条"**。这类"参数没传进来就把库清了"的
       写法，是删除类函数最容易出的致命错。
    2. **返回 -1 而不是抛异常，也不静默吞掉。** 模块里别的读函数出错都是
       "记日志 + 返回空"，但这一支是**用户点了删除**：静默失败 = 用户以为删掉了、
       列表却没变（正是本项目最忌讳的"不报错但给你错结果"）。
       所以把"没删成"**命名**出来，由界面明说。
       ⚠ 这与 `record()` 那条"失败只记日志、绝不抛"不冲突：那条是**旁路**
         （记账不该弄挂一次正常调用），这条是**用户主动发的命令**。
    3. **只删 `usage_log` 里的行**，不动任何别的表、更不碰磁盘上的小说项目。
    
        English:
    Delete all usage records of **a certain project**. Returns the number of deleted rows; **`-1` =
    deletion failed**.
        ★ Why it must exist (user's 2026-10-10 request: "the content of the leftmost column must be deletable"):
          the ledger is **append-only** -- a project is deleted / its name changed, its records will **forever** remain
          in the leftmost column, piling up more and more. Without an opening to "delete this item", that column can only rot forever.
        ★★ Three deliberate designs (all forced out by "once wrong, unrecoverable")
        -------------------------------------------------
        1. **Deleting with an empty project name is not allowed.** Passing `''` directly returns 0, **without touching a single row**.
           Otherwise there would be a **catastrophic** shape: in `record()`, the default value of `project` is
           `''` (calls with no project context -- e.g. the open-book stretch), so the database has a **large chunk**
           of records with an empty project name. A single mistaken call to `delete_project('')` would wipe out
           **the vast majority of the whole software's ledger**, and **return a nice-looking "deleted N rows"**.
           This "parameter not passed in so the database gets cleared" pattern is the most fatal error in deletion functions.
        2. **Return -1 instead of throwing, and do not silently swallow either.** Other read functions in the module, on error,
           "log + return empty", but this branch is **the user clicking delete**: silent failure = the user thinks it was deleted,
           but the list is unchanged (exactly the "no error but wrong result" that this project most abhors).
           So "deletion failed" is **named**, and stated explicitly by the UI.
           ⚠ This does not conflict with the `record()` rule "failures only log, never throw": that one is a **bypass**
             (bookkeeping should not crash a normal call), this one is **a command actively issued by the user**.
        3. **Only delete rows in `usage_log`**, do not touch any other table, let alone the novel project on disk.
    """
    name = str(project or '').strip()
    if not name:                                    # 见上面第 1 条：这是**防灾难**，不是洁癖
    # [EN] See item 1 above: this is **disaster prevention**, not fastidiousness
        _LOG.warning('拒绝删除：项目名为空（那会把没有项目上下文的记录一起清掉）')
        return 0
    try:
        conn = _conn(path)
        try:
            cur = conn.execute('DELETE FROM usage_log WHERE project = ?', (name,))
            conn.commit()
            return int(cur.rowcount or 0)
        finally:
            conn.close()
    except Exception as e:                                       # noqa: BLE001
        _LOG.warning('删用量记录失败：%r', e)
        return -1


def recent_days(n: int = 30, scope: str | None = None,                path: Path | None = None) -> list[str]:
    """最近有记录的 N 天（给"最近一段时间"这个说法一个具体的口径）。
        English:
    The last N days with records (giving a concrete definition to the phrase "a recent period").
    """
    w, args = _where(scope)
    try:
        conn = _conn(path)
        try:
            rows = conn.execute(
                'SELECT DISTINCT day FROM usage_log WHERE 1=1' + w
                + ' ORDER BY day DESC LIMIT ?', [*args, int(n)]).fetchall()
        finally:
            conn.close()
    except Exception:                                            # noqa: BLE001
        return []
    return sorted(str(r['day']) for r in rows)


# ══════════════════════════════════════════════════════════════════
#  展示用小工具
# [EN] Display helper utilities
# ══════════════════════════════════════════════════════════════════
def fmt_tokens(n: int) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f'{n / 1_000_000:.2f}M'
    if n >= 1_000:
        return f'{n / 1_000:.1f}k'
    return str(n)


def fmt_cost(c: float) -> str:
    """费用一律显示成 **¥**（本项目默认人民币口径，见 pricing 用元/百万 token）。
        English:
    Cost is always displayed as **¥** (this project defaults to the RMB convention, see pricing in
    yuan per million tokens).
    """
    c = float(c or 0.0)
    return f'¥{c:.4f}' if c < 1 else f'¥{c:.2f}'
