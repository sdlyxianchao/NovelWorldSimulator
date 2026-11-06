# -*- coding: utf-8 -*-
"""**跨进程共享缓存**：让主程序与三个外挂服务共用一份"问答对"缓存。

## 为什么要有它（用户 2026-10-19 的原话）

> 「再看下是否有办法保证目前设计的前提下降低成本 比如引入一个缓存
>   给所有的组件使用（当前软件和3个外挂）使用 或者别的任何工具」

先说结论（量出来的，不是猜的）：**最大的一笔省在"前缀顺序"，不在响应缓存**。

`usage.db` 近 7 天的账（18.5 万次调用 / 2.7 亿输入 token / ¥223.5）给出两个事实：

| 事实 | 数 | 含义 |
|---|---|---|
| 输入 token 是输出的 **7.6 倍** | 2.70 亿 vs 0.35 亿 | 钱几乎全花在"把上下文送进去" |
| 前缀缓存**只命中 1.4%** | 378 万 / 2.70 亿 | 厂商的命中价约为 1/10 ⇒ 这 98% 都是全价 |
| `agent_decide` 占输入 **53%** | 1324 万 / 2907 次 | 单次 4554 token，命中率 **1.1%** |

第三行是关键：同一时间 `crew_script_doctor` 能到 **17.3%**、`day_verify` **15.1%** ——
机制是通的，只有 `agent_decide` 这一条路命中不了。原因不在模型，在**拼装顺序**：
每拍都会变的「当前目标 / 情绪 / 位置 / 场景·时间 / 在场」原来排在 `semi` 的第二位，
于是**固定层只剩 135 字**，后面 7600 字稳定内容全部拿不到缓存。
那个修在 `agent/core.decide` 里（2026-10-19，前缀从 1.8% → 21.2%，判据
`tools/verify_prefix_cache.py` 的 E 组守着）。

**修完那个之后**，剩下还能省的才是本模块这一块：**同一份输入被算两遍**。

## 本模块做什么

把 `llm/dedup.py` 那个**进程内**的 OrderedDict 升级成**一个 sqlite 文件**：

| 维度 | 进程内 dedup（原来） | 本模块 |
|---|---|---|
| 活多久 | 进程一退全没 | 落盘，跨会话 |
| 谁看得见 | 只有主程序 | 主程序 + 三个外挂（同一个文件） |
| 上限 | 300 条 LRU | 按**字节预算**淘汰最久没用的（响应比 300 条大得多） |

## ⚠ 四条不许破的规矩（与 `dedup` 完全一致，一条都不能松）

1. **只对白名单用途生效。** 说话 / 写正文 / 起名**绝不在内** —— 那些要的正是
   "每次都不一样"，缓存会让全场人说着同一句话。
2. **key 覆盖所有影响输出的输入**：模型 / 消息 / 温度 / 上限 / JSON / 思考开关。
   漏一个就会出现"改了温度却拿到老答案"这种最难查的 bug。
3. **过期就重算**（TTL）。设定会改、进度会变，老答案不能一直用。
4. **失败不存**（空文本不存 —— 存了就把"失败"固化成"答案"）。

## 外挂怎么用（**不改它们一行代码**）

外挂服务（MuMuAINovel / PenShot / PlotPilot）各自有 venv，`import` 不到本项目。

**它们现在是独立进程 + 独立 venv**，本项目那个 `Ledger`（全项目唯一的记账汇合点）
在它们那里**根本不存在** —— 所以 `usage.db` 里**一条外挂的账都没有**。
这件事必须说明白，不能装作"已经覆盖了"（静默降级在这个项目是明令禁止的）。
要真的采到，只有两条路：
  ① **网关代理**：主程序起一个 loopback 的 OpenAI 兼容端点，外挂的 `base_url` 指过去，
     代理在那里统一记账 + 查缓存（外挂不用改代码，只改配置里的地址）；
  ② **它们自己按下面的文件协议上报**（要改它们的调用点，升级时会被上游覆盖，风险高）。
⚠ 本次**没有**做这两条 —— 只做了主程序这一侧（前缀重排 + 共享缓存）。
  所以：**用量窗口里"外挂"那一栏仍然是空的，那是事实，不是 bug。**
所以这里**不提供"给它们 import 的库"**，而是规定一个**文件协议**：

    缓存文件路径 = 主程序根目录下的 `llm_cache.db`

任何一个进程（不管有没有装本项目的依赖）只要用**标准库 sqlite3** 打开它，
按 `_SCHEMA` 里的表结构读写，就与主程序共用同一份缓存。表结构故意做得极简：

    cache(key TEXT PRIMARY KEY, ts REAL, text TEXT, n INT)

⚠ **不要**给外挂一份"本项目专用的 API"：它们升级时会被上游覆盖掉。
  文件协议是唯一不会被升级冲掉的接口。
⚠ 反过来说，**外挂不接也不会出错**：缓存是**增强项**，缺席就是每次都真发请求
  （与"三座服务是增强项"的既有纪律一致）。

## 与 `dedup` 的分工（不要合并成一个）

`dedup` 是**热路径**上的内存命中（纳秒级、同一进程、每拍都问）；
本模块是**冷路径**（跨进程、要开 sqlite、毫秒级）。
`router.chat` 的顺序是：**先问 dedup（内存）→ 再问本模块（磁盘）→ 都没有才真发**。
合并成一个会让每拍都碰磁盘 —— 那正是这个项目反复算过的"不值得"。
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

_LOG = logging.getLogger('nws.llm.cache')

APP_DIR = Path(__file__).resolve().parent.parent

#: 缓存文件（与 `usage.db` 平级，都在软件根目录）。
#: ⚠ 不放 `logs/`：那个目录随发布包被排除，缓存跟着没（`usage.db` 那条教训）。
# [EN] The cache file (next to `usage.db` in the software root). ⚠ Not in `logs/`: that directory
# [EN] is excluded from release packages and the cache would vanish with it.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key   TEXT PRIMARY KEY,
    -- ★★★ **两个时间戳，不能合并成一个**（2026-10-19 审代码时发现的设计错）：
    --   `ts`   = **存入时刻**，TTL 只认它（"这个答案存了多久"）；
    --   `used` = **最后被读的时刻**，淘汰只认它（"谁最久没用"）。
    --   ⚠ 第一版只有 `ts`，命中时 `UPDATE ts` 把两件事搅在一起：
    --     一个**每拍都被命中**的条目永远不会过期 —— 而设定可能已经改了，
    --     那正是 dedup 文档里明令禁止的"用半天前的结论回答现在的局面"。
    -- [EN] ★★★ **Two timestamps, never one** (design error found reviewing on 2026-10-19):
    -- [EN] `ts` = **stored at** (TTL reads only this); `used` = **last read at** (eviction reads only
    -- [EN] this). ⚠ The first version had only `ts` and did `UPDATE ts` on a hit, mixing the two: an
    -- [EN] entry **hit every beat would never expire**, while settings may have changed -- exactly
    -- [EN] the "answering today's situation with a conclusion from half a day ago" dedup forbids.
    ts    REAL NOT NULL,
    used  REAL NOT NULL DEFAULT 0,
    text  TEXT NOT NULL,
    n     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cache_ts ON cache(ts);
CREATE INDEX IF NOT EXISTS idx_cache_used ON cache(used);
"""

#: 后加的列（**老库要补**）。⚠ `CREATE TABLE IF NOT EXISTS` 对已存在的表一行都不改 ——
#: 这是 `usage.db` 那边刚踩过的坑（新列只在新建库时存在，老用户每次都撞 `no such column`）。
# [EN] Columns added later (**old databases must be patched**). ⚠ `CREATE TABLE IF NOT EXISTS`
# [EN] changes nothing on an existing table -- the exact trap hit in `usage.db`.
_LATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ('used', 'REAL NOT NULL DEFAULT 0'),
)

#: 总量上限（字节）。超了按"最久没用"淘汰到 `_KEEP_RATIO`。
#:
#: 为什么按**字节**而不按条数：响应长度从几百字到几千字不等，按条数限流的话
#: 300 条可能只占 200KB，也可能占 20MB —— 用户磁盘上那 20MB 是白占的。
#: 3000 万字节 ≈ 30MB，比 `usage.db`（也是几十 MB 量级）同一个规格。
# [EN] Total cap in **bytes** (not row count): responses vary from hundreds to thousands of chars,
# [EN] so a row cap could mean 200KB or 20MB on the user's disk. 30MB matches `usage.db`'s scale.
MAX_BYTES = 30 * 1024 * 1024
_KEEP_RATIO = 0.75


def db_path() -> Path:
    """共享缓存文件的位置（软件根目录）。
        English:
    Location of the shared cache file (software root).
    """
    try:
        from config import CFG
        custom = str(CFG.s('LLM_CACHE_PATH') or '').strip()
        if custom:
            return Path(custom).expanduser()
    except Exception:                                            # noqa: BLE001
        pass
    return APP_DIR / 'llm_cache.db'


def _conn() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p), timeout=5)
    c.executescript(_SCHEMA)
    _migrate(c)
    # 与 `usage.db` 同一套理由：这是同步盘上的库，别整份重写。
    # [EN] Same reason as `usage.db`: this database lives on a synced drive; don't rewrite it all.
    for pragma in ('PRAGMA journal_mode=WAL', 'PRAGMA synchronous=NORMAL'):
        try:
            c.execute(pragma)
        except Exception:                                        # noqa: BLE001
            pass
    return c


def _migrate(c: sqlite3.Connection) -> None:
    """把老库缺的列补上（现在只有 `used`）。

    ⚠ 不补的话：老用户升级后每一次 `get()` 都会撞 `no such column: used`，
      而 `get()` 是"失败当作没有"的旁路 ⇒ **缓存静默全废**，界面上什么错都看不到。
      这正是 `usage.db` 那边刚记下过的坑（新列只在新建库时存在）。
    [EN] Without this, an upgraded user hits `no such column: used` on every `get()`, and `get()` is
    [EN] a "treat failure as a miss" bypass => **the cache silently dies** with no visible error.
    [EN] The exact trap recorded for `usage.db` (a new column exists only in a fresh database).
    """
    try:
        have = {str(r[1]) for r in c.execute('PRAGMA table_info(cache)').fetchall()}
    except Exception:                                            # noqa: BLE001
        return
    for name, decl in _LATE_COLUMNS:
        if name not in have:
            try:
                c.execute(f'ALTER TABLE cache ADD COLUMN {name} {decl}')
                # 老行的 used 用 ts 兜底（含义：从没被读过）
                # [EN] Backfill old rows: used = ts (meaning "never read yet").
                c.execute('UPDATE cache SET used = ts WHERE used = 0')
            except Exception as e:                               # noqa: BLE001
                _LOG.warning('补列 %s 失败：%r', name, e)
    try:
        c.commit()
    except Exception:                                            # noqa: BLE001
        pass


def enabled() -> bool:
    """总开关（`LLM_CACHE_ENABLED`，默认**开**）。

    ⚠ 默认开是刻意的：它只在白名单用途上生效（见模块头第 1 条），
      而白名单里那几类（判定 / 抽取 / 校对）本来就应该"同一个问题同一个答案"。
      关掉它的唯一理由是排查"为什么这次答案和上次一样"。
    [EN] Master switch (default **on**). ⚠ On by default is deliberate: it only applies to
    [EN] whitelisted purposes, which by definition should answer the same question the same way.
    [EN] Turn it off only to debug "why is this answer identical to last time".
    """
    try:
        from config import CFG
        return bool(CFG.b('LLM_CACHE_ENABLED'))
    except Exception:                                            # noqa: BLE001
        return True


def ttl() -> int:
    """保质期（秒）。`0` = 不过期。
        English:
    Shelf life in seconds. `0` = never expires.
    """
    try:
        from config import CFG
        return int(CFG.i('LLM_CACHE_TTL_SECONDS'))
    except Exception:                                            # noqa: BLE001
        return 7200


def get(key: str | None) -> str | None:
    """拿一次（没有 / 过期 / 关着都返回 `None`）。

    ⚠ 过期条目**就地删掉**：留着会被淘汰算法当成"最近用过"，把空间花在死条目上。
    [EN] Fetch once (`None` when absent / expired / disabled). ⚠ Expired rows are **deleted in
    [EN] place**: leaving them makes the eviction read them as "recently used".
    """
    if not key or not enabled():
        return None
    age = ttl()
    now = time.time()
    try:
        c = _conn()
        try:
            row = c.execute('SELECT ts, text FROM cache WHERE key = ?', (key,)).fetchone()
            if row is None:
                return None
            ts, text = float(row[0]), str(row[1] or '')
            # ⚠ 过期只认 `ts`（存入时刻）—— **不能因为"刚被读过"就续命**。
            #   见 schema 里那段说明：续命会让"每拍都命中"的条目永不过期。
            # [EN] Expiry reads only `ts` -- never extend it because "it was just read". See the
            # [EN] schema note: extending makes an entry hit every beat never expire.
            if age > 0 and (now - ts) > age:
                c.execute('DELETE FROM cache WHERE key = ?', (key,))
                c.commit()
                return None
            # 命中：只刷 `used`（**LRU 淘汰的判据**），**不动 `ts`**。
            # [EN] Hit: refresh only `used` (the **LRU eviction** signal), **never `ts`**.
            c.execute('UPDATE cache SET used = ?, n = n + 1 WHERE key = ?', (now, key))
            c.commit()
        finally:
            c.close()
    except Exception as e:                                       # noqa: BLE001
        _LOG.debug('读共享缓存失败（当作没有）：%r', e)
        return None
    if not text.strip():
        return None
    return text


def put(key: str | None, text: str) -> bool:
    """存一次。**空文本不存**（会把失败固化），**失败不抛**（旁路纪律）。
        English:
    Store once. **Empty text is not stored** (it would freeze a failure); **never throws**.
    """
    if not key or not str(text or '').strip() or not enabled():
        return False
    try:
        c = _conn()
        try:
            _now = time.time()
            c.execute('INSERT INTO cache(key, ts, used, text, n) VALUES(?,?,?,?,0)'
                      ' ON CONFLICT(key) DO UPDATE SET ts=excluded.ts,'
                      ' used=excluded.used, text=excluded.text, n=n+1',
                      (key, _now, _now, str(text)))
            c.commit()
            _evict(c)
        finally:
            c.close()
        return True
    except Exception as e:                                       # noqa: BLE001
        _LOG.debug('写共享缓存失败（不影响调用）：%r', e)
        return False


def _evict(c: sqlite3.Connection) -> None:
    """超预算就把**最久没用**的删到 `_KEEP_RATIO`。

    ⚠ 按 `ts` 删（那就是"最后被用过的时间"，因为命中时会刷新它）。
      按 `n`（次数）删会留下"很久以前被问过很多次"的死条目。
    [EN] Over budget => delete the **least recently used** down to `_KEEP_RATIO`.
    [EN] ⚠ Evict by `ts` (which a hit refreshes), not by `n` (count would keep stale hot rows).
    """
    try:
        size = int(c.execute('SELECT COALESCE(SUM(LENGTH(text)),0) FROM cache').fetchone()[0] or 0)
        if size <= MAX_BYTES:
            return
        target = int(MAX_BYTES * _KEEP_RATIO)
        # ⚠ 淘汰按 `used`（谁最久**没被读**），不是 `ts`（谁最老）——
        #   按 ts 删会把"存得早但每拍都在用"的条目先删掉。
        # [EN] Evict by `used` (least recently read), not `ts` (oldest): deleting by ts would remove
        # [EN] entries stored early but used every beat.
        rows = c.execute('SELECT key, LENGTH(text) FROM cache ORDER BY used ASC').fetchall()
        for k, ln in rows:
            if size <= target:
                break
            c.execute('DELETE FROM cache WHERE key = ?', (k,))
            size -= int(ln or 0)
        c.commit()
        _LOG.info('共享缓存超预算，淘汰到 %d 字节', max(0, size))
    except Exception as e:                                       # noqa: BLE001
        _LOG.debug('淘汰失败（不影响调用）：%r', e)


def stats() -> dict:
    """`{rows, bytes, hits}` —— 给「天机」与运行摘要看。
        English:
    `{rows, bytes, hits}` -- for "Tianji" and the run summary.
    """
    try:
        c = _conn()
        try:
            r = c.execute('SELECT COUNT(*) n, COALESCE(SUM(LENGTH(text)),0) b,'
                          ' COALESCE(SUM(n),0) h FROM cache').fetchone()
        finally:
            c.close()
        return {'rows': int(r[0] or 0), 'bytes': int(r[1] or 0), 'hits': int(r[2] or 0)}
    except Exception:                                            # noqa: BLE001
        return {'rows': 0, 'bytes': 0, 'hits': 0}


def clear() -> int:
    """清空，返回删掉的行数（改了设定要重跑同一段时用）。
        English:
    Clear and return the number of deleted rows (used after changing settings to rerun a stretch).
    """
    try:
        c = _conn()
        try:
            n = int(c.execute('SELECT COUNT(*) FROM cache').fetchone()[0] or 0)
            c.execute('DELETE FROM cache')
            c.commit()
        finally:
            c.close()
        return n
    except Exception:                                            # noqa: BLE001
        return -1


def prune() -> int:
    """清掉过期条目，返回清掉的条数（启动时调一次）。
        English:
    Drop expired rows and return how many (called once at startup).
    """
    age = ttl()
    if age <= 0:
        return 0
    try:
        c = _conn()
        try:
            cur = c.execute('DELETE FROM cache WHERE ts < ?', (time.time() - age,))
            c.commit()
            return int(cur.rowcount or 0)
        finally:
            c.close()
    except Exception:                                            # noqa: BLE001
        return -1
