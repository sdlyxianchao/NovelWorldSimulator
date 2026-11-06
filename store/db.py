# -*- coding: utf-8 -*-
"""SQLite 存储：记忆流、事件、快照、合规记录、账单。

表结构覆盖设计稿 §五（记忆流）、§九（快照）、§十（原始日志）、§十六（合规日志）。
内存表量级很小，单线程直连 sqlite3 即可（<1ms/操作）。

English:
SQLite storage: memory stream, events, snapshots, compliance records, billing.
Table structure covers design draft §5 (memory stream), §9 (snapshots), §10 (raw log), §16
(compliance log).
In-memory tables are tiny, single-threaded direct sqlite3 connection is enough (<1ms/op).
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from config import CFG

_LOG = __import__("logging").getLogger("nws.store")

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokens(text: str) -> set[str]:
    """把一段文本切成可比较的片段（只用于"相关性"打分）。

    ⚠ 上一版是 `set(query)` —— 把整句拆成**单个汉字**的集合。
    中文里任何两句话都共享常用字（"的""了""是""他"），于是"命中率"几乎恒等于 1：
    相关性这一项**完全没有区分度**，检索退化成"按时间取最近的"。
    （这正是"记忆检索打折"的根源，2026-10-06 修。）

    现在：中文按**二元组**滑窗（"今夜别出门" → {今夜, 夜别, 别出, 出门}），
    英文/数字按词，单字 CJK 段（长度 1）才退回单字。
    
        English:
    Split a piece of text into comparable segments (only used for "relevance" scoring).
        ⚠ The previous version was `set(query)` —— splitting the whole sentence into a set of **individual Chinese characters**.
        In Chinese any two sentences share common characters ("的" "了" "是" "他"), so the "hit rate" is almost always exactly 1:
        the relevance term has **no discriminating power at all**, and retrieval degenerates into "take the most recent by time".
        (This is exactly the root cause of "memory retrieval discounting", fixed 2026-10-06.)
        English/digits are split by word, only single-character CJK segments (length 1) fall back to single characters.
    """
    text = str(text or "")
    out = {w.lower() for w in _WORD_RE.findall(text) if len(w) > 1}
    for seg in _CJK_RE.findall(text):
        if len(seg) == 1:
            out.add(seg)
        else:
            out.update(seg[i:i + 2] for i in range(len(seg) - 1))
    return out


def similarity(a: str, b: str) -> float:
    """两段文本的 Jaccard 相似度（0~1）。导演用它拦"换个说法的同一件事"。
        English:
    Jaccard similarity between two pieces of text (0~1). The director uses it to catch "the same
    thing said differently".
    """
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)

_TABLES = """
CREATE TABLE IF NOT EXISTS memory (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    agent     TEXT    NOT NULL,
    ts        REAL    NOT NULL,
    game_ts   REAL    DEFAULT 0,
    type      TEXT    NOT NULL DEFAULT 'observation',
    content   TEXT    NOT NULL,
    importance REAL   DEFAULT 5.0,
    ref_event TEXT    DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_mem_agent ON memory(agent);
CREATE INDEX IF NOT EXISTS idx_mem_ts   ON memory(ts);

CREATE TABLE IF NOT EXISTS events (
    id        TEXT    PRIMARY KEY,
    ts        REAL    NOT NULL,
    game_day  INTEGER NOT NULL,
    type      TEXT    NOT NULL DEFAULT 'action',
    content   TEXT    NOT NULL,
    involved  TEXT    DEFAULT '[]',
    node      TEXT    DEFAULT '',
    snapshot  TEXT    DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ev_day ON events(game_day);

CREATE TABLE IF NOT EXISTS snapshots (
    id        TEXT    PRIMARY KEY,
    ts        REAL    NOT NULL,
    note      TEXT    DEFAULT '',
    game_day  INTEGER NOT NULL,
    path      TEXT    DEFAULT ''
);

CREATE TABLE IF NOT EXISTS compliance_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL    NOT NULL,
    checkpoint TEXT   NOT NULL,
    level     TEXT    NOT NULL DEFAULT 'C2',
    action    TEXT    NOT NULL DEFAULT 'pass',
    original  TEXT    DEFAULT '',
    rewritten TEXT    DEFAULT '',
    detail    TEXT    DEFAULT '',
    exonerated INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS budget_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL    NOT NULL,
    model     TEXT    NOT NULL,
    purpose   TEXT    NOT NULL,
    in_tok    INTEGER DEFAULT 0,
    out_tok   INTEGER DEFAULT 0,
    cost      REAL    DEFAULT 0.0
);

-- ★ 前情提要（2026-10-06）：每天一条，把当天发生的事压成几句话。
--   这是"双记忆"里的长期那一半 —— 短期是 memory 表里最近 K 条，
--   长期是这份跨天累积的故事梗概。没有它，推演到第十天时人物只知道
--   "最近五条记忆"，前面九天等于没发生过。
CREATE TABLE IF NOT EXISTS summary (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL    NOT NULL,
    game_day INTEGER NOT NULL DEFAULT 0,
    scope    TEXT    NOT NULL DEFAULT '故事',
    text     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sum_scope ON summary(scope, game_day);
"""


class DB:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_TABLES)
        self._conn.commit()
        _LOG.info("DB 打开: %s", path)

    def close(self):
        self._conn.close()

    # ── 记忆 ──
    # [EN] ── Memory ──
    def add_memory(self, agent: str, content: str, memory_type: str = "observation",
                   importance: float = 5.0, game_ts: float = 0, ref_event: str = "") -> int:
        cur = self._conn.execute(
            "INSERT INTO memory(agent, ts, game_ts, type, content, importance, ref_event) VALUES(?,?,?,?,?,?,?)",
            (agent, time.time(), game_ts, memory_type, content, importance, ref_event))
        self._conn.commit()
        return cur.lastrowid  # type: ignore

    def count_memories(self, agent: str) -> int:
        """这个人一共攒了多少条记忆（`SUMMARIZE_MEMORY_AFTER` 的判据）。
                English:
        How many memories this person has accumulated in total (the criterion for
        `SUMMARIZE_MEMORY_AFTER`).
        """
        row = self._conn.execute("SELECT COUNT(*) FROM memory WHERE agent=?",
                                 (agent,)).fetchone()
        return int(row[0] if row else 0)

    def oldest_memories(self, agent: str, n: int) -> list[dict]:
        """最老的 n 条记忆（按**故事时间**排；没有故事时间才退回真实时间）。

        ⚠ 排序必须用 `game_ts`：一轮推演在真实世界里只跑十几分钟，
        故事里过了三十天 —— 按 `ts` 排会把三十天的记忆当成"同一批"。
        
                English:
        The n oldest memories (sorted by **story time**; fall back to real time only when there is no
        story time).
                ⚠ Sorting must use `game_ts`: one round of simulation only runs for a dozen minutes in real time,
                but thirty days pass in the story —— sorting by `ts` would treat thirty days of memories as "the same batch".
        """
        rows = self._conn.execute(
            "SELECT * FROM memory WHERE agent=? "
            "ORDER BY (CASE WHEN game_ts > 0 THEN game_ts ELSE ts / 86400.0 END) ASC, id ASC "
            "LIMIT ?", (agent, max(0, int(n)))).fetchall()
        return [dict(r) for r in rows]

    def drop_memories(self, ids: list[int]) -> int:
        """删掉若干条记忆（压缩后用）。返回删掉的条数。
                English:
        Delete several memories (used after compression). Returns the number deleted.
        """
        ids = [int(x) for x in (ids or [])]
        if not ids:
            return 0
        marks = ",".join("?" * len(ids))
        cur = self._conn.execute(f"DELETE FROM memory WHERE id IN ({marks})", ids)
        self._conn.commit()
        return int(cur.rowcount or 0)

    def retrieve_memory(self, agent: str, k: int = 8, query: str = "",
                        now_game_min: float | None = None) -> list[dict]:
        """检索 top-K 记忆：recency + importance + relevance。

        `now_game_min` = **当前故事时间**（分钟，从第 1 天 00:00 起）。
        给了就按故事时间算新近度，不给才退回真实时间。

        ⚠ 为什么必须用故事时间：一轮推演在真实世界里可能只跑十几分钟，
        故事里却过了三十天。按真实时间算 → 所有记忆的 recency 几乎相等
        （都是"刚刚"），新近度这一项同样失去区分度。这是 2026-10-06 修的另一半。

        `RECENCY_DECAY`（默认 0.995）= **每真实/故事小时**的留存系数：
        0.995^24 ≈ 0.89（隔一天）、0.995^240 ≈ 0.30（隔十天）。
        
                English:
        Retrieve top-K memories: recency + importance + relevance.
                `now_game_min` = **current story time** (minutes, starting from day 1 00:00).
                If given, compute recency by story time; only fall back to real time when not given.
                ⚠ Why story time is mandatory: one round of simulation may only run for a dozen minutes in real time,
                but thirty days pass in the story. Computing by real time → the recency of all memories is nearly equal
                (all "just now"), and the recency term likewise loses its discriminating power. This is the other half of the 2026-10-06 fix.
                `RECENCY_DECAY` (default 0.995) = retention factor **per real/story hour**:
                0.995^24 ≈ 0.89 (after one day), 0.995^240 ≈ 0.30 (after ten days).
        """
        rows = self._conn.execute(
            "SELECT * FROM memory WHERE agent=? ORDER BY ts DESC, importance DESC LIMIT ?",
            (agent, k * 3)).fetchall()
        results = [dict(r) for r in rows]

        if CFG.b("DEBUG_MODE"):
            _LOG.debug("[%s] 记忆检索: 查询 %d 条, query=%s", agent, len(results),
                       query[:50] if query else "")

        # 相关性：二元组重叠（空 query 就一律 0，不做"人人有份"的假分）
        # [EN] Relevance: bigram overlap (empty query is always 0, no fake "everyone gets a share" score)
        q = tokens(query)
        for r in results:
            if q:
                t = tokens(r["content"])
                r["_relevance"] = len(q & t) / len(q) if t else 0.0
            else:
                r["_relevance"] = 0.0

        wr = CFG.f("WEIGHT_RECENCY")
        wi = CFG.f("WEIGHT_IMPORTANCE")
        wrel = CFG.f("WEIGHT_RELEVANCE")
        decay = max(0.9, min(1.0, CFG.f("RECENCY_DECAY")))
        for r in results:
            age_min = self._age_minutes(r, now_game_min)
            r["_age_min"] = round(age_min, 1)
            r["_recency"] = decay ** (age_min / 60.0)
            r["_score"] = (wr * r["_recency"]
                           + wi * (r["importance"] / 10.0)
                           + wrel * r["_relevance"])
        results.sort(key=lambda r: r["_score"], reverse=True)

        if CFG.b("DEBUG_MODE"):
            for i, r in enumerate(results[:k]):
                _LOG.debug("  [%d] score=%.2f recency=%.2f importance=%.1f "
                           "relevance=%.2f content=%s", i, r["_score"], r["_recency"],
                           r["importance"], r["_relevance"], r["content"][:40])

        return results[:k]

    @staticmethod
    def _age_minutes(row: dict, now_game_min: float | None) -> float:
        """这条记忆"有多旧"（分钟）。

        有故事时间就用故事时间（`game_ts` 是写入时记下的故事分钟数）；
        没记 game_ts 的老数据退回真实时间 —— 但那是**兜底**，不是首选。
        
                English:
        How old this memory is (minutes).
                Use story time if available (`game_ts` is the story minute count recorded at write time);
                old data without game_ts falls back to real time —— but that is a **fallback**, not the first choice.
        """
        g = float(row.get("game_ts") or 0.0)
        if now_game_min is not None and g > 0:
            return max(0.0, float(now_game_min) - g)
        return max(0.0, (time.time() - float(row.get("ts") or 0.0)) / 60.0)

    # ── 前情提要（长期记忆）──────────────────────────────────────────
    # [EN] ── Previously on (long-term memory) ──────────────────────────────────────────
    def add_summary(self, game_day: int, text: str, scope: str = "故事") -> int:
        """记一条前情提要（每天一条）。空文本不记。
                English:
        Record a previously-on entry (one per day). Empty text is not recorded.
        """
        text = str(text or "").strip()
        if not text:
            return 0
        cur = self._conn.execute(
            "INSERT INTO summary(ts, game_day, scope, text) VALUES(?,?,?,?)",
            (time.time(), int(game_day), scope, text))
        self._conn.commit()
        return cur.lastrowid  # type: ignore

    def get_summaries(self, k: int = 6, scope: str = "故事") -> list[dict]:
        """取最近 k 条前情提要，**按天数升序**返回。

        升序是有意的：拼进 prompt 时要"从早到晚"读才顺，
        倒着给模型会看到"后一天在前一天上面"（人读起来别扭，模型也容易串）。
        
                English:
        Take the most recent k previously-on entries, returned **in ascending day order**.
                Ascending order is intentional: when assembled into the prompt it must be read "from early to late" to flow well;
                giving it in reverse makes the model see "the later day above the earlier day" (awkward for humans to read, and the model also gets confused easily).
        """
        rows = self._conn.execute(
            "SELECT * FROM summary WHERE scope=? ORDER BY game_day DESC, id DESC LIMIT ?",
            (scope, max(1, int(k)))).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ── 事件 ──
    # [EN] ── Events ──
    def add_event(self, event_id: str, content: str, event_type: str = "action",
                  game_day: int = 1, involved: list[str] | None = None,
                  node: str = "", snapshot: str = "") -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO events(id, ts, game_day, type, content, involved, node, snapshot) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (event_id, time.time(), game_day, event_type, content,
             json.dumps(involved or [], ensure_ascii=False), node, snapshot))
        self._conn.commit()

    def recent_events(self, n: int = 20, game_day: int = 0) -> list[dict]:
        if game_day > 0:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE game_day=? ORDER BY ts DESC LIMIT ?", (game_day, n)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM events ORDER BY ts DESC LIMIT ?", (n,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── 快照 ──
    # [EN] ── Snapshots ──
    def add_snapshot(self, sid: str, note: str, game_day: int, path: str) -> None:
        self._conn.execute(
            "INSERT INTO snapshots(id, ts, note, game_day, path) VALUES(?,?,?,?,?)",
            (sid, time.time(), note, game_day, path))
        self._conn.commit()

    def drop_snapshot(self, sid: str) -> int:
        """清掉一条快照登记（`SNAPSHOT_KEEP` 用）。**不删磁盘上的文件**。
                English:
        Clear a snapshot registration (used by `SNAPSHOT_KEEP`). **Does not delete files on disk**.
        """
        cur = self._conn.execute("DELETE FROM snapshots WHERE id=?", (str(sid),))
        self._conn.commit()
        return int(cur.rowcount or 0)

    def snapshots(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM snapshots ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ── 合规 ──
    # [EN] ── Compliance ──
    def add_compliance(self, checkpoint: str, level: str, action: str,
                       original: str, rewritten: str, detail: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO compliance_log(ts, checkpoint, level, action, original, rewritten, detail) "
            "VALUES(?,?,?,?,?,?,?)",
            (time.time(), checkpoint, level, action, original, rewritten, detail))
        self._conn.commit()
        return cur.lastrowid  # type: ignore

    def exonerate(self, cid: int) -> bool:
        r = self._conn.execute("UPDATE compliance_log SET exonerated=1 WHERE id=?", (cid,))
        self._conn.commit()
        return r.rowcount > 0

    def compliance_records(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM compliance_log ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ── 账单 ──
    # [EN] ── Billing ──
    def add_budget(self, model: str, purpose: str, in_tok: int, out_tok: int, cost: float) -> None:
        self._conn.execute(
            "INSERT INTO budget_log(ts, model, purpose, in_tok, out_tok, cost) VALUES(?,?,?,?,?,?)",
            (time.time(), model, purpose, in_tok, out_tok, cost))
        self._conn.commit()

    def budget_summary(self) -> dict:
        rows = self._conn.execute(
            "SELECT model, SUM(in_tok) AS ti, SUM(out_tok) AS to2, SUM(cost) AS cost "
            "FROM budget_log GROUP BY model").fetchall()
        return {r["model"]: {"in": r["ti"], "out": r["to2"], "cost": r["cost"]} for r in rows}