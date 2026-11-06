# -*- coding: utf-8 -*-
"""真机 + 逻辑验证：**多模型费用统计 / 缓存命中 / 同题复用 / 降费**（2026-10-12）。

用户原话：
> 「还一个问题 现在用AI的地方越来越多 话费太快 如果多模型 则 LLM用量需要统计不同模型的
>   费用 第二 你去学一下 看有什么办法优化AI Llm使用 尽量降低费用 不然太贵了」

判据分六段：

* **A 计价**（纯逻辑）：价格表是三段式 · 覆盖国内外主要模型 · 最长前缀优先 ·
  自己填的价覆盖内置 · 只填一半也能补全 · 命中比未命中便宜 · 峰谷时段判定 ·
  空闲折扣只作用于峰谷定价的模型 · 缓存省下的钱算得对
* **B 登记表**（纯逻辑）：单价存/读往返 · 没填的不落盘 · 坏值读成"没填"不抛 ·
  `price_overrides()` 只输出填过的 · `resolve()` 带上这一条的单价
* **C 台账库**（纯逻辑）：老库自动补 `cache_tok` 列 · 落库与四层聚合都带它 ·
  WAL 生效（这是那条"一次提交 45 秒"的修复）
* **D 同题复用**（纯逻辑）：同输入同参数键一致 · 改任一参数键就变 ·
  白名单外的用途不给键 · 关掉开关不给键 · 过期不命中 · 空文本不存 · LRU 有上限
* **E 接线**（行为级）：`chat()` 真的接了复用 —— 相同请求第二次**不发**
  （假 client 数调用次数）· 复用不记账 · 缓存的 token 数从响应里读得出来
  并真的少算了钱
* **F 真机**：「AI模型配置」页有「怎么把账单降下来」四招 · 模型编辑框有单价三项 ·
  用量报表里有缓存那几列

产出 `assets/screenshots/verify_cost_model_*.png` 与 `cost_model_report.json`。

    .venv/Scripts/python.exe tools/verify_cost_model.py
    .venv/Scripts/python.exe tools/verify_cost_model.py --logic-only

English:
Real machine + logic verification: **multi-model cost accounting / cache hits / same-question
reuse / cost reduction** (2026-10-12).
The user's words:
> "One more issue: AI is used in more and more places and the cost is rising fast. With several
>   models, LLM usage must count the cost of each model. Second, go learn what ways there are to
>   optimize LLM usage and reduce the cost as much as possible -- it is too expensive."
Criteria are in six sections:
* **A Pricing** (pure logic): the price table is three-part · covers major Chinese and overseas
  models · longest prefix wins · your own prices override the built-in ones · filling only half
  still works · a hit is cheaper than a miss · peak-window detection · the off-peak discount
  applies only to peak-priced models · cache savings computed correctly
* **B Registry** (pure logic): unit-price round trip · unfilled prices are not written to disk ·
  a bad value reads back as "unfilled" without raising · `price_overrides()` only emits filled
  ones · `resolve()` carries this entry's prices
* **C Ledger database** (pure logic): an old database gets the `cache_tok` column added · both
  the write and all four aggregation layers carry it · WAL is active (the fix for that "one
  commit takes 45 seconds" problem)
* **D Same-question reuse** (pure logic): identical input and parameters give one key · changing
  any parameter changes the key · non-whitelisted purposes get no key · switching it off gives no
  key · expiry misses · empty text is not stored · the LRU has a cap
* **E Wiring** (behavioural): `chat()` really wired reuse -- the second identical request is **not
  sent** (a fake client counts calls) · reuse records no ledger entry · the cache token count is
  read from the response and really reduces the cost
* **F Real machine**: the "AI Model Config" page has the four "how to bring the bill down" levers ·
  the model editor has the three unit-price fields · the usage report has the cache columns
Output `assets/screenshots/verify_cost_model_*.png` and `cost_model_report.json`.
    .venv/Scripts/python.exe tools/verify_cost_model.py
    .venv/Scripts/python.exe tools/verify_cost_model.py --logic-only
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                                    # noqa: E402

from config import CFG                                               # noqa: E402
from llm import models as MODELS                                     # noqa: E402
from llm import tokens as TOK                                        # noqa: E402
from util.flet_shutdown import exit_now, shutdown                    # noqa: E402

LOGIC_ONLY = '--logic-only' in sys.argv
OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

checks: list[tuple[bool, str, str]] = []

#: 实测下来的**几何数字**（输入框本体宽、某列的宽…）。
#   `ok()` 只带得动"红没红 + 一串说明文字"，带不动结构化数字；而反例法
#   （`developers/mutate_*.py`）改完产品代码之后，要读的是"这个数字变成几了"。
#   ⚠ 这个字典必须**模块级**存在：早先在 G19 里直接写 `REPORT[...]`，
#   而本文件从来没有 `REPORT` ⇒ `NameError` ⇒ 整段被 `_guard` 兜成一条红，
#   看着像"判据自己崩了"，其实是"变量没定义"。
# [EN] The **geometric numbers** actually measured (input box body width, a column's width...).
# [EN] `ok()` can only carry "red or not + a string of explanation", not structured numbers; and the
# [EN] counterexample method (`developers/mutate_*.py`), after mutating the product code, needs to
# [EN] read "what this number became".
# [EN] ⚠ This dict must exist **at module level**: earlier G19 wrote `REPORT[...]` directly, but this
# [EN] file never had `REPORT` => `NameError` => the whole section was caught by `_guard` as a single
# [EN] red, looking like "the criterion itself crashed" when in fact "the variable was undefined".
REPORT: dict[str, dict] = {}


def ok(name: str, cond: bool, detail: str = '') -> bool:
    checks.append((bool(cond), name, '' if cond else str(detail)))
    print(('  ✓ ' if cond else '  ✗ ') + name + ('' if cond else f'   ← {detail}'))
    return bool(cond)


# ══════════════════════════════════════════════════════════════════════
#  A 计价
# [EN] A Pricing
# ══════════════════════════════════════════════════════════════════════
def test_a() -> None:
    print('\n── A 计价（三段式 / 覆盖 / 峰谷 / 缓存省下）──')
    ok('A1 价格表的值都是**三段式** (命中, 未命中, 输出)',
       all(isinstance(v, tuple) and len(v) == 3 for v in TOK.PRICE_TABLE.values()),
       str([k for k, v in TOK.PRICE_TABLE.items() if len(v) != 3][:5]))
    # 国内外主要模型都要**查得到**（查不到就会落到兜底价，账直接错）
    # [EN] Every major Chinese and overseas model must be **findable** -- a miss falls back
    # [EN] to the default price and the ledger is simply wrong.
    majors = ['deepseek-v4-pro', 'deepseek-flash', 'hy3', 'glm-4.6', 'kimi-k2',
              'qwen-plus', 'minimax', 'claude-sonnet', 'gpt-5.5', 'gemini-3']
    miss = [m for m in majors if TOK.price_of(m) == TOK._DEFAULT_PRICE]
    ok('A2 国内外主要模型都查得到价（没落到兜底价）', not miss, str(miss))
    # ★ 最长前缀优先：**这里必须用"多重匹配"的构造才能真的验到它**。
    #   第一版写的是 `price_of('deepseek-v4-pro') == PRICE_TABLE['deepseek-v4-pro']`
    #   —— 反例法把"精确匹配"整个删掉，判据**照样绿**：因为前缀匹配又会撞上
    #   `deepseek-v4-pro` **自己**那个键。也就是说那条断言根本没在验"最长优先"，
    #   它在验"能查到价"（那是 A2 的活）。**打不红的判据等于没有**，所以改成：
    #   一个模型名同时匹配两个 override 键，短的那个排在后面 —— 只有"比长度"
    #   才能选中长的那个；一旦退化成"取最后一个匹配"，答案立刻不同。
    # [EN] ★ Longest prefix wins: **this needs a multi-match construction to really test it**.
    # [EN] The first version was `price_of('deepseek-v4-pro') == PRICE_TABLE['deepseek-v4-pro']`
    # [EN] -- the counterexample method deleted exact matching entirely and the criterion **stayed
    # [EN] green**, because prefix matching then hit `deepseek-v4-pro`'s own key again. That assertion
    # [EN] was never testing "longest wins"; it was testing "a price can be found" (A2's job). **A
    # [EN] criterion that cannot go red is as good as absent**, so it was rewritten: a model name
    # [EN] matching two override keys, with the shorter one later in the dict -- only length
    # [EN] comparison picks the long one; degrade to "last match wins" and the answer changes at once.
    _ov = {'model-x': (1.0, 1.0, 1.0), 'model': (2.0, 2.0, 2.0)}
    ok('A3 多重匹配时**取最长的那个键**（不会"谁在后面谁赢"）',
       TOK.price_of('model-x-long', _ov) == (1.0, 1.0, 1.0),
       str(TOK.price_of('model-x-long', _ov)))
    ok('A4 自己填的价**覆盖**内置价',
       TOK.price_of('hy3', {'hy3': (1, 2, 3)}) == (1.0, 2.0, 3.0),
       str(TOK.price_of('hy3', {'hy3': (1, 2, 3)})))
    # 只填一半：没填的那段回落内置表（"我只知道输出价"也要能用）
    # [EN] Filling only half: the unfilled part falls back to the built-in table
    # [EN] ("I only know the output price" must still work).
    part = TOK.price_of('hy3', {'hy3': (-1, -1, 99.0)})
    ok('A5 只填一部分时，没填的段回落内置表', part[0] == 0.25 and part[1] == 1.0
       and part[2] == 99.0, str(part))
    # 老写法（两段）仍然能用：命中价按未命中的 1/10 推
    # [EN] The old two-part form still works: the hit price is inferred at 1/10 of a miss.
    old = TOK.parse_overrides('x=4/8')
    ok('A6 老写法 name=未命中/输出 仍能解析（命中价按 1/10 推）',
       old.get('x') == (0.4, 4.0, 8.0), str(old))
    # 命中比未命中便宜
    # 这两条用**高峰**（不打折）算，值才等于表里的名义价 —— 一眼能对上。
    # [EN] These two use **peak** (no discount) so the values equal the nominal table prices and
    # [EN] match at a glance.
    c_hit = TOK.cost_of('deepseek-v4-pro', 1_000_000, 0, None, cache_tok=1_000_000,
                        peak=True)
    c_miss = TOK.cost_of('deepseek-v4-pro', 1_000_000, 0, None, cache_tok=0,
                         peak=True)
    ok('A7 命中缓存的输入**明显更便宜**（命中 1M < 未命中 1M 的一半）',
       c_hit < c_miss * 0.5, f'hit={c_hit} miss={c_miss}')
    ok('A8 命中部分**只按命中价算**（1M 全命中 = 命中价）',
       abs(c_hit - TOK.PRICE_TABLE['deepseek-v4-pro'][0]) < 1e-9, str(c_hit))
    # 便宜的模型算出来确实更便宜（这是"给粗活配便宜模型"的依据）
    # [EN] A cheap model really does cost less -- the basis for "give routine work a cheap model".
    cheap = TOK.cost_of('hy3', 100_000, 20_000, None, peak=False)
    pricey = TOK.cost_of('claude-opus', 100_000, 20_000, None, peak=False)
    ok('A9 便宜档与旗舰档的费用差距是真的（差 15 倍以上）',
       pricey > cheap * 15, f'hy3={cheap:.4f} opus={pricey:.4f}')
    # 缓存省下的钱
    # [EN] The money saved by caching.
    saved = TOK.saved_by_cache('deepseek-v4-pro', 1_000_000)
    ok('A10 「缓存省下」= (未命中价 − 命中价) × 命中量',
       abs(saved - (TOK.PRICE_TABLE['deepseek-v4-pro'][1]
                    - TOK.PRICE_TABLE['deepseek-v4-pro'][0])) < 1e-6, str(saved))
    ok('A11 命中率算得对（1000 里命中 500 = 50%）', abs(TOK.hit_ratio(1000, 500) - 0.5) < 1e-9,
       str(TOK.hit_ratio(1000, 500)))
    ok('A12 输入为 0 时命中率是 0（不是崩溃、也不是 1）', TOK.hit_ratio(0, 0) == 0.0, '')
    # 峰谷时段（用固定时间戳，不看"跑的时候正好几点"）
    # [EN] Peak/off-peak windows, using fixed timestamps rather than "what time it is right now".
    import datetime as _dt
    tz = _dt.timezone(_dt.timedelta(hours=8))
    mon_am = _dt.datetime(2026, 10, 12, 10, 0, tzinfo=tz).timestamp()   # Mon 10:00
    mon_night = _dt.datetime(2026, 10, 12, 22, 0, tzinfo=tz).timestamp()
    sat = _dt.datetime(2026, 10, 17, 10, 0, tzinfo=tz).timestamp()      # Sat 10:00
    ok('A13 周一 10:00 = 高峰', TOK.peak_now(mon_am) is True, '')
    ok('A14 周一 22:00 = 空闲', TOK.peak_now(mon_night) is False, '')
    ok('A15 周六 10:00 = 空闲（周末全天空闲）', TOK.peak_now(sat) is False, '')
    ok('A16 只认 DeepSeek 一家是峰谷定价',
       TOK.is_peak_model('deepseek-v4-pro') and not TOK.is_peak_model('hy3'), '')
    peak_cost = TOK.cost_of('deepseek-v4-pro', 1_000_000, 0, None, peak=True)
    off_cost = TOK.cost_of('deepseek-v4-pro', 1_000_000, 0, None, peak=False)
    ok('A17 空闲时段正好是高峰的**一半**（默认折扣 0.5）',
       abs(off_cost - peak_cost * 0.5) < 1e-9, f'{off_cost} vs {peak_cost}')
    ok('A18 非峰谷定价的模型**不受折扣影响**（平价家不该被折）',
       abs(TOK.cost_of('hy3', 1_000_000, 0, None, peak=False)
           - TOK.cost_of('hy3', 1_000_000, 0, None, peak=True)) < 1e-9, '')


# ══════════════════════════════════════════════════════════════════════
#  B 登记表里的单价
# [EN] B Unit prices in the registry
# ══════════════════════════════════════════════════════════════════════
def test_b() -> None:
    print('\n── B 登记表的单价字段 ──')
    tmp = Path(tempfile.mkdtemp(prefix='nws_cost_b_'))
    with MODELS.use_path(tmp / 'llm_models.json'):
        e = MODELS.ModelEntry(key='hy3', label='混元 Hy3', model='hy3',
                              price_hit=0.25, price_miss=1.0, price_out=4.0)
        MODELS.save([e, MODELS.ModelEntry(key='x', label='没填价', model='zz-x')])
        back = MODELS.load()
        got = next((x for x in back if x.key == 'hy3'), None)
        ok('B1 单价存/读往返一致',
           got is not None and got.price_tuple() == (0.25, 1.0, 4.0), str(got))
        ok('B2 `has_price` 说这条填过价', bool(got and got.has_price), '')
        raw = json.loads((tmp / 'llm_models.json').read_text(encoding='utf-8'))
        row_none = next(r for r in raw['models'] if r['key'] == 'x')
        ok('B3 **没填价的那条**不把 -1 写进文件（不留脏字段）',
           'price_hit' not in row_none and 'price_miss' not in row_none, str(row_none))
        none_e = next((x for x in back if x.key == 'x'), None)
        ok('B4 没填价的条目 `has_price` 为假', bool(none_e) and not none_e.has_price, '')
        ov = MODELS.price_overrides(MODELS.load())
        ok('B5 `price_overrides()` 只输出填过的条目',
           'hy3' in ov and 'zz-x' not in ov, str(ov))
        # 坏值：写成字符串也要读成"没填"，不能抛
        # ⚠ 这里必须**自己接住异常**：如果实现改成"读不出就 `raise`"，
        #   不接的话判据脚本会**整段崩掉**（report 都写不出来），
        #   反例法那边就只能看到"判据自己崩了"、看不到 B6 这条红 —— 判据形同虚设。
        # [EN] A bad value written as a string must still read back as "unfilled", without raising.
        # [EN] ⚠ The exception must be **caught right here**: if the implementation were changed to
        # [EN] "raise when unreadable", not catching it would **crash the whole section** (no report
        # [EN] could be written), and the counterexample method would only see "the criterion itself
        # [EN] crashed" instead of B6 going red -- the criterion would be useless.
        (tmp / 'llm_models.json').write_text(json.dumps(
            {'version': 1, 'models': [{'key': 'bad', 'model': 'hy3',
                                       'price_miss': '不认识的数字'}]},
            ensure_ascii=False), encoding='utf-8')
        try:
            bad = MODELS.load()
        except Exception as e:                                   # noqa: BLE001
            ok('B6 价格写成乱码时读成"没填"（-1），不抛异常', False, f'抛了：{e!r}')
        else:
            ok('B6 价格写成乱码时读成"没填"（-1），不抛异常',
               len(bad) == 1 and bad[0].price_miss < 0,
               str(bad[0] if bad else None))
    ok('B7 `Resolved` 带上了这一条的单价（router 计价要用它）',
       'prices' in MODELS.Resolved.__dataclass_fields__,
       str(list(MODELS.Resolved.__dataclass_fields__)))


# ══════════════════════════════════════════════════════════════════════
#  C 台账库
# [EN] C Ledger database
# ══════════════════════════════════════════════════════════════════════
def test_c() -> None:
    print('\n── C 台账库（补列 / 落库 / 聚合 / WAL）──')
    import sqlite3
    from llm import usage as U
    tmp = Path(tempfile.mkdtemp(prefix='nws_cost_c_'))
    db = tmp / 'usage.db'
    # 先造一个**没有 cache_tok 的老库**（模拟用户从旧版本升上来）
    # [EN] First create an **old database without cache_tok** (simulating an upgrade)
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
            day TEXT NOT NULL, module TEXT NOT NULL DEFAULT '',
            project TEXT NOT NULL DEFAULT '', run TEXT NOT NULL DEFAULT '',
            agent TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
            purpose TEXT NOT NULL DEFAULT '', tier TEXT NOT NULL DEFAULT '',
            in_tok INTEGER NOT NULL DEFAULT 0, out_tok INTEGER NOT NULL DEFAULT 0,
            cost REAL NOT NULL DEFAULT 0.0);
    """)
    conn.execute("INSERT INTO usage_log(ts,day,module,model,purpose,in_tok,out_tok,cost)"
                 " VALUES(1,'2026-01-01','NovelWorldSimulator','deepseek-flash','old',10,5,0.1)")
    conn.commit()
    conn.close()
    ok('C1 落库成功（老库先被自动补上 cache_tok 列）',
       U.record(model='deepseek-flash', purpose='probe', in_tok=1000, out_tok=20,
                cost=0.05, cache_tok=900, path=db), '')
    cols = {r[1] for r in sqlite3.connect(str(db)).execute(
        'PRAGMA table_info(usage_log)').fetchall()}
    ok('C2 老库补列后确实有 cache_tok', 'cache_tok' in cols, str(sorted(cols)))
    t = U.totals(path=db)
    ok('C3 `totals()` 认出新记的 900 个缓存 token（老行算 0）',
       int(t.get('cache_tok') or 0) == 900, str(t))
    gs = U.groups(None, U.BY_MODEL, path=db)
    g = next((x for x in gs if x['key'] == 'deepseek-flash'), None)
    ok('C4 **按模型分组**里有缓存列（用户要的就是"分模型看费用"）',
       g is not None and int(g.get('cache_tok') or 0) == 900, str(gs))
    rows = U.detail(None, U.BY_MODEL, 'deepseek-flash', path=db, limit=5)
    ok('C5 明细每行都带 cache_tok',
       bool(rows) and 'cache_tok' in rows[0], str(rows[:1]))
    jm = sqlite3.connect(str(db)).execute('PRAGMA journal_mode').fetchone()[0]
    ok('C6 WAL 已生效（这是"一次提交 45 秒"的修复）', str(jm).lower() == 'wal', str(jm))


# ══════════════════════════════════════════════════════════════════════
#  D 同题复用
# [EN] D Same-question reuse
# ══════════════════════════════════════════════════════════════════════
def test_d() -> None:
    print('\n── D 同题复用（键 / 白名单 / 过期 / 上限）──')
    from llm import dedup as D
    D.clear()
    msgs = [{'role': 'user', 'content': '这一站的判据满足了吗'}]
    base = dict(model='hy3', purpose='progress_eval', messages=msgs,
                temperature=0.2, max_tokens=500)
    k1 = D.key_for(**base)
    ok('D1 同输入同参数 → 同一个键', bool(k1) and k1 == D.key_for(**base), str(k1))
    variants = {
        '温度': dict(temperature=0.9), '模型': dict(model='deepseek-flash'),
        '上限': dict(max_tokens=900), 'JSON': dict(json_mode=True),
        '思考': dict(no_think=True),
        '消息': dict(messages=[{'role': 'user', 'content': '换了一句话'}]),
    }
    bad = [n for n, ch in variants.items()
           if D.key_for(**{**base, **ch}) == k1]
    ok('D2 改**任一**影响输出的参数，键就变（漏一个就会"改了参数拿到老答案"）',
       not bad, f'没变的：{bad}')
    ok('D3 白名单外的用途不给键（说话 / 写正文 / 起名绝不缓存）',
       D.key_for(model='hy3', purpose='dialogue', messages=msgs) is None
       and D.key_for(model='hy3', purpose='crew_novelist', messages=msgs) is None, '')
    ok('D4 没写 purpose 也不给键', D.key_for(model='hy3', purpose='', messages=msgs) is None, '')
    # ⚠⚠ **必须先把配置里的白名单临时置空**，才验得到"代码兜底"这一半。
    #   反例法当场教了这一课：`.env` 里写过 `LLM_DEDUP_PURPOSES` 之后，
    #   `_cfg_str()` 读到的就是那份值、**代码里的 `DEFAULT_PURPOSES` 根本走不到** ——
    #   于是"把 `or DEFAULT_PURPOSES` 删掉"这个变异**打不红这条判据**（实际红的=[]）。
    #   判据要能红，就得**把被测分支逼出来**：临时置空 → 验 → 还原。
    #   ⚠ `CFG.set()` 只改内存（写盘已被 `redirect_env_writes()` 掐掉），不动用户的 `.env`。
    # [EN] ⚠⚠ **The whitelist in the config must be temporarily emptied** for the "code fallback"
    # [EN] half to be testable. The counterexample method taught this on the spot: once
    # [EN] `LLM_DEDUP_PURPOSES` is written in `.env`, `_cfg_str()` reads that value and the code's
    # [EN] `DEFAULT_PURPOSES` is **never reached** -- so removing `or DEFAULT_PURPOSES` **cannot turn
    # [EN] this criterion red** (actual reds = []). To make it red the criterion must **force the
    # [EN] branch under test**: empty it, verify, restore.
    # [EN] ⚠ `CFG.set()` only touches memory (disk writes are cut off by `redirect_env_writes()`), so
    # [EN] the user's `.env` is untouched.
    _purposes_bak = CFG.s('LLM_DEDUP_PURPOSES')
    CFG.set('LLM_DEDUP_PURPOSES', '')
    ok('D5 白名单**默认来自代码常量**（配置为空时仍然生效 —— 踩过的坑）',
       'progress_eval' in D.purposes() and 'dialogue' not in D.purposes(),
       str(sorted(D.purposes())))
    CFG.set('LLM_DEDUP_PURPOSES', _purposes_bak)
    CFG.set('LLM_DEDUP_ENABLED', 'false')
    ok('D6 关掉总开关后不给键', D.key_for(**base) is None, '')
    CFG.set('LLM_DEDUP_ENABLED', 'true')
    # 过期：TTL 设 1 秒，睡 1.2 秒
    # [EN] Expiry: set TTL to 1 second and sleep 1.2 seconds.
    CFG.set('LLM_DEDUP_TTL_SECONDS', '1')
    k = D.key_for(**base)
    D.put(k, '结论：满足')
    ok('D7 没过期时拿得到', D.get(k) == '结论：满足', '')
    import time as _t
    _t.sleep(1.2)
    ok('D8 过期之后就**不命中**了（设定会变，老答案不能一直用）',
       D.get(k) is None, '')
    CFG.set('LLM_DEDUP_TTL_SECONDS', '3600')
    D.put(k, '')
    ok('D9 **空文本不存**（存了等于把"失败"固化成"答案"）', D.get(k) is None, '')
    D.clear()
    for i in range(D.MAX_ENTRIES + 40):
        D.put(f'k{i:05d}', f'v{i}')
    st = D.stats()
    ok('D10 有上限（LRU），不会无限涨',
       int(st['size']) <= D.MAX_ENTRIES, str(st))
    D.clear()


# ══════════════════════════════════════════════════════════════════════
#  E 接线（行为级）
# [EN] E Wiring (behavioural)
# ══════════════════════════════════════════════════════════════════════
class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self.status_code = 200
        self.text = json.dumps(payload, ensure_ascii=False)
        self._p = payload

    def json(self) -> dict:
        return self._p

    def raise_for_status(self) -> None:
        """`_real_call` 会调它 —— 假响应必须也长这个方法。
                English:
        `_real_call` calls it -- a fake response must have this method too.
        """
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


class _FakeClient:
    """假客户端：**只记调用次数与请求体**，不发真请求。
        English:
    A fake client: **only counts calls and records request bodies**, sends nothing.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url, json=None, headers=None, timeout=None):  # noqa: A002
        self.calls.append((url, json or {}))
        return _FakeResp({
            'choices': [{'message': {'content': '结论：满足'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 1000, 'completion_tokens': 10,
                      'prompt_cache_hit_tokens': 900, 'prompt_cache_miss_tokens': 100},
        })

    # `ensure_started` 会调它 —— 假的响应/客户端必须也长这些方法。
    # [EN] `ensure_started` calls it -- fake responses/clients must have these methods too.
    async def aclose(self) -> None:
        return None


async def test_e() -> None:
    print('\n── E 接线：第二次相同请求真的不发 ──')
    from llm.router import llm
    from llm import dedup as D
    tmp = Path(tempfile.mkdtemp(prefix='nws_cost_e_'))
    with MODELS.use_path(tmp / 'llm_models.json'):
        MODELS.save([MODELS.ModelEntry(key='hy3', label='混元 Hy3', model='hy3',
                                       base_url='https://tb.example/v1', api_key='k')])
        CFG.set('MOCK_LLM', 'false')
        CFG.set('MODEL_DAILY', 'hy3')
        CFG.set('LLM_DEDUP_ENABLED', 'true')
        CFG.set('LLM_DEDUP_TTL_SECONDS', '3600')
        # ★★★ 2026-10-22：**共享磁盘缓存必须关**（这一组要的是"内存去重"，
        #   与跨会话共享缓存无关）。不关的话，打桩拿到的假答复会被写进
        #   `llm_cache.db`：① 留在**用户机器**上；② 别的判据/真跑命中它，
        #   拿到的是这里的桩文本 ⇒ 判据自己制造下一轮的红。
        # [EN] ★★★ 2026-10-22: **the shared disk cache must be off** (this group is about in-memory
        # [EN] dedup, not the cross-session shared cache). Left on, the stubbed reply is written into
        # [EN] `llm_cache.db`: (1) it stays on the **user's machine**; (2) other criteria / real runs hit
        # [EN] it and get this stub text => the criterion creates next round's red itself.
        CFG.set('LLM_CACHE_ENABLED', 'false')
        D.clear()
        fake = _FakeClient()
        llm._client = fake
        llm._sem = asyncio.Semaphore(1)
        llm._started = True
        # ⚠ `chat()` 开头会 `ensure_started()`，而它会**关掉旧 client 再建一个真的** ——
        #   我们那个假 client 会被顶掉，"发了几次"就数不出来了。
        #   这里把它换成空操作，用完**在 finally 里还原**。
        # [EN] ⚠ `chat()` calls `ensure_started()` up front, and that **closes the old client and
        # [EN] builds a real one** -- our fake would be replaced and "how many times it sent" could
        # [EN] no longer be counted. Replace it with a no-op and **restore it in finally**.
        _orig_ensure = llm.ensure_started

        async def _noop_ensure() -> None:
            return None
        llm.ensure_started = _noop_ensure
        try:
            await _check_e(llm, fake)
        finally:
            llm.ensure_started = _orig_ensure
        D.clear()
        CFG.set('MOCK_LLM', 'true')


async def _check_e(llm, fake) -> None:
    """E 段真正的断言（拆出来是为了能用 try/finally 把 monkeypatch 还原）。
        English:
    The actual assertions of section E (split out so the monkeypatch can be restored in a
    [EN] try/finally).
    """
    msgs = [{'role': 'user', 'content': '这一站的判据满足了吗'}]
    before = len(llm.ledger.records)
    t1 = await llm.chat('daily', msgs, purpose='progress_eval', max_tokens=200)
    n_after_first = len(fake.calls)
    t2 = await llm.chat('daily', msgs, purpose='progress_eval', max_tokens=200)
    n_after_second = len(fake.calls)
    ok('E1 第一次**真发**了请求', n_after_first == 1, str(n_after_first))
    ok('E2 第二次**没有发**（同题复用真的接上了）', n_after_second == 1,
       f'第一次后 {n_after_first} 次，第二次后 {n_after_second} 次')
    ok('E3 第二次拿到的还是那份答案', t1 == t2 and bool(t2), f'{t1!r} / {t2!r}')
    ok('E4 复用**不记账**（账本只记真实请求，账单不会被虚增）',
       len(llm.ledger.records) - before == 1,
       f'新增 {len(llm.ledger.records) - before} 条')
    rec = llm.ledger.records[-1]
    ok('E5 响应里的缓存命中 token 被读出来了（900）',
       int(getattr(rec, 'cache_tok', 0)) == 900, str(getattr(rec, 'cache_tok', None)))
    full = TOK.cost_of('hy3', 1000, 10, None, cache_tok=0, peak=False)
    ok('E6 命中那 900 个 token **真的少算了钱**（比全按未命中算便宜）',
       float(rec.cost) < full, f'实际 {rec.cost:.8f} < 全未命中 {full:.8f}')
    # 白名单外的用途照样每次都发
    # [EN] Purposes outside the whitelist are really sent every time.
    n0 = len(fake.calls)
    await llm.chat('daily', msgs, purpose='dialogue', max_tokens=200)
    await llm.chat('daily', msgs, purpose='dialogue', max_tokens=200)
    ok('E7 创作类用途（dialogue）**每次都真发**（绝不缓存）',
       len(fake.calls) - n0 == 2, f'实际发了 {len(fake.calls) - n0} 次')


# ══════════════════════════════════════════════════════════════════════
#  F 真机
# [EN] F Real machine
# ══════════════════════════════════════════════════════════════════════
async def test_f(page: ft.Page, report: dict) -> None:
    print('\n── F 真机 ──')
    import verify_ui_common as VU
    from gui.app_flet import NovelWorldApp
    VU.redirect_env_writes()
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(1.5)
    tmp = Path(tempfile.mkdtemp(prefix='nws_cost_f_'))
    guard = MODELS.use_path(tmp / 'llm_models.json')
    guard.__enter__()
    try:
        app.show_global_settings(tab=app.TAB_LLM)
        await asyncio.sleep(0.9)
        page.update()
        dlg = VU.open_dialogs(page)[-1]
        texts = [str(x) for x in VU.all_texts(dlg)]
        blob = '\n'.join(texts)
        ok('F1 「AI模型配置」页有「怎么把账单降下来」这一块',
           '怎么把账单降下来' in blob, blob[:120])
        # ★★ 2026-10-12（用户：「怎么把账单降下来 只保留一个标题，指向帮助信息
        #   对应章节」）：四招的正文**搬进了说明书**，页上只剩标题 + 状态行。
        #   所以这里改成验"**正文确实不在了**"（否则就是没挪干净）。
        # [EN] ★★ 2026-10-12 (user: "for 'how to bring the bill down', keep only a heading that
        # [EN] points to the corresponding help section"): the four levers' prose **moved into the
        # [EN] manual**, leaving only the heading and a status line. So this now verifies that the prose
        # [EN] **is really gone** (otherwise it was not moved out).
        ok('F2 四招的正文**已从页上移除**（只剩标题，指向说明书）',
           not any(k in blob for k in ('挑时段跑', '给粗活配便宜模型',
                                       '打开「同题复用」', '把固定前缀钉死')), '')
        ok('F3 那一块带**当前状态**（现在是不是高峰、复用开了没有）',
           '当前状态' in blob, '')
        shot = await page.take_screenshot()
        if shot:
            (OUT / f'cost_saving_tips{SUFFIX}.png').write_bytes(shot)

        # 模型编辑框：单价三项在不在
        # [EN] Model editor: are the three unit-price fields there
        state = {'entries': list(MODELS.load()),
                 'default_box': ft.Column([], spacing=4), 'pickers': {}}
        app._model_editor(page, None, state, lambda: None)
        await asyncio.sleep(0.7)
        page.update()
        dlg2 = VU.open_dialogs(page)[-1]
        t2 = '\n'.join(str(x) for x in VU.all_texts(dlg2))
        ok('F4 模型编辑框有单价三项（命中 / 未命中 / 输出）',
           all(k in t2 for k in ('缓存命中价', '未命中价', '输出价')), t2[:160])
        ok('F5 并说清楚"留空 = 按内置参考价估"', '内置参考价' in t2, '')
        try:
            page.pop_dialog()
        except Exception:                                        # noqa: BLE001
            pass
        shot2 = await page.take_screenshot()
        if shot2:
            (OUT / f'cost_model_editor{SUFFIX}.png').write_bytes(shot2)
        try:
            page.pop_dialog()
        except Exception:                                        # noqa: BLE001
            pass

        # 用量报表：缓存那几列在不在（2026-10-12 加）
        # ⚠ 这一页**内容是异步搭起来的**（它要现读 SQLite 再画四栏）—— 等 1.2 秒只看得到
        #   标题，判据当场报"没有缓存命中 Token"（第一版就是这么假红的）。
        #   所以：等久一点，并且抓**所有**对话框的文字合并着找。
        # [EN] Usage report: are the cache columns there (added 2026-10-12)
        # [EN] ⚠ This page **builds its content asynchronously** (it reads SQLite then draws four
        # [EN] columns) -- waiting 1.2s only shows the title and the criterion reports "no cache-hit
        # [EN] tokens" (the first version went falsely red exactly like that). So: wait longer and
        # [EN] search the **merged text of every** dialog.
        from gui.usage_dialog import open_usage_dialog
        open_usage_dialog(app)
        for _ in range(6):
            await asyncio.sleep(1.0)
            page.update()
        dlgs = VU.open_dialogs(page)
        # ⚠ 用本地 `_deep_texts`（**能进 `DataTable`**）—— 公共 `all_texts` 进不去，
        #   会把"屏幕上明明有"判成"没有"（详见 `_deep_texts` 的注释）。
        # [EN] ⚠ Use the local `_deep_texts` (**it enters `DataTable`**) -- the shared `all_texts`
        # [EN] cannot, and would judge "visibly there" as "missing" (see `_deep_texts`).
        u_txt = ('\n'.join(x for d in dlgs for x in _deep_texts(d))
                 if dlgs else '')
        # ⚠ 改口径（2026-10-12）：缓存那两项**并进了「合计 Token」与「费用」行**
        #   —— 第 4 栏没有纵向滚动，新开两行会把底部的横向滚动条挤出可视区
        #   （`verify_usage_layout` 的 B4b 像素取证抓到）。所以这里找的是
        #   **并进去之后的样子**，不是那两个独立行名。
        # [EN] ⚠ Changed criteria (2026-10-12): the two cache figures are **merged into the "Total
        # [EN] tokens" and "Cost" rows** -- column 4 has no vertical scrolling, and two new rows push the
        # [EN] horizontal scrollbar at the bottom out of the visible area (caught by the pixel forensics
        # [EN] of B4b in `verify_usage_layout`). So this looks for **the merged shape**, not those two
        # [EN] standalone row names.
        ok('F6 用量报表里**看得到缓存命中量**（并进「合计 Token」那一行）',
           '命中缓存' in u_txt, u_txt[:300])
        ok('F7 用量报表里**看得到缓存省下的钱**（并进「费用」那一行）',
           '缓存省下' in u_txt, '')
        ok('F8 用量报表按模型列出**缓存命中率**（"缓存命中 {p}"那条）',
           '缓存命中 ' in u_txt or '缓存命中率' in u_txt, '')
        shot3 = await page.take_screenshot()
        if shot3:
            (OUT / f'cost_usage_report{SUFFIX}.png').write_bytes(shot3)
    except Exception:
        ok('F 段整体没崩', False, traceback.format_exc()[-400:])
    finally:
        guard.__exit__(None, None, None)


# ══════════════════════════════════════════════════════════════════════
#  G 界面结构（2026-10-12 第二轮：放大 / 换 Table / 拆 Tab / 左对齐）
# [EN] G UI structure (2026-10-12 round two: enlarge / Table / split Tab / left align)
# ══════════════════════════════════════════════════════════════════════
def _col_text(col) -> str:
    """取 `DataColumn` 的显示文字。
        English:
    Get the display text of a `DataColumn`.
    """
    lbl = getattr(col, 'label', None)
    return str(getattr(lbl, 'value', '') or '')


def _deep_tables(ctrl, acc: list) -> None:
    """把一棵控件树里所有 `ft.DataTable` 捞出来（`_deep_texts` 的姊妹函数）。
        English:
    Pull every `ft.DataTable` out of a control tree (sibling of `_deep_texts`).
    """
    if ctrl is None:
        return
    if isinstance(ctrl, ft.DataTable):
        acc.append(ctrl)
    for attr in ('controls', 'content', 'tabs'):
        v = getattr(ctrl, attr, None)
        if isinstance(v, list):
            for x in v:
                _deep_tables(x, acc)
        elif v is not None and not isinstance(v, str):
            _deep_tables(v, acc)


async def test_g(page: ft.Page) -> None:
    print('\n── G 界面结构 ──')
    import verify_ui_common as VU
    from gui.app_flet import (NovelWorldApp, grid_w, grid_half, grid_third,
                              grid_width)
    from i18n import get_lang, t
    VU.redirect_env_writes()
    ok('G1 ★★ 非天机场景下栅格还是 520（**别的对话框一个像素都不许变**）',
       grid_w() == 520 and grid_half() == 256 and grid_third() == 168,
       f'{grid_w()} / {grid_half()} / {grid_third()}')
    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(1.5)
    tmp_g = Path(tempfile.mkdtemp(prefix='nws_cost_g_'))
    guard = MODELS.use_path(tmp_g / 'llm_models.json')
    guard.__enter__()
    try:
        win_h = int(getattr(page, 'height', 0) or 0) or 1167
        win_w = int(getattr(page, 'width', 0) or 0) or 1400
        app.show_global_settings(tab=app.TAB_LLM)
        await asyncio.sleep(1.0)
        page.update()
        dlg = None
        for d in reversed(VU.open_dialogs(page)):
            if isinstance(d, ft.AlertDialog):
                dlg = d
                break
        c = getattr(dlg, 'content', None)
        w, h = getattr(c, 'width', None), getattr(c, 'height', None)
        ok('G2 ★★★ 天机**按窗口放大**（至少原尺寸 684x575 的 1.4 倍宽、1.4 倍高）',
           isinstance(w, int) and isinstance(h, int)
           and w >= 684 * 1.4 and h >= 575 * 1.4, f'{w}x{h}')
        ok('G3 ★★★ 天机**不超过窗口**（按客户区算，别用 page.window.*）',
           isinstance(h, int) and isinstance(w, int)
           and h <= win_h and w <= win_w,
           f'{w}x{h} vs 窗口 {win_w}x{win_h}')
        ok('G4 ★★ 造完天机之后栅格**已还原**（不留状态泄漏给下一个对话框）',
           grid_w() == 520, str(grid_w()))
        blob = '\n'.join(_deep_texts(dlg))
        tables: list = []
        _deep_tables(dlg, tables)
        ok('G5 ★★★ 模型列表是**表格**（用户：「变成Table 而不是Panel列表」）',
           len(tables) >= 2, f'表格数 {len(tables)}')
        model_tbl = next((x for x in tables if len(x.columns) >= 8), None)
        ok('G6 ★★★ 模型表有**单价/超时/重试**列（「通用参数」分到各模型里）',
           model_tbl is not None
           and all(k in ' '.join(_col_text(x) for x in model_tbl.columns)
                   for k in ('单价', '超时', '重试')),
           f'{len(tables)} 张表')
        # ★★★ 2026-10-14（用户：「天机 剧组Agents 的那个功能用什么模型 这个部分去掉」）：
        #   这张推荐表**整节去掉了** ⇒ 判据要按**页签面板**确认它**不在**剧组 Agents 页，
        #   否则"表还在不在这一页"根本分不出来（`_deep_tables(dlg)` 会把所有页签一起收）。
        # [EN] ★★★ 2026-10-14 (user: "remove the 'which function uses which model' section from
        # [EN] Tianji's Crew Agents page"): the recommendation section is **gone entirely** => the
        # [EN] criterion must confirm **by tab panel** that it is **NOT** on the Crew Agents page
        # [EN] (`_deep_tables(dlg)` collects every tab at once).
        _crew_panel = VU.tab_panels(dlg).get(t('剧组 Agents'))
        _rec_tbls: list = []
        if _crew_panel is not None:
            _deep_tables(_crew_panel, _rec_tbls)
        rec_tbl = next((x for x in _rec_tbls
                        if 3 <= len(x.columns) <= 5
                        and any('推荐' in _col_text(c) for c in x.columns)), None)
        ok('G7 ★★★ 「哪个功能用什么模型」那张推荐表**整节去掉了**'
           '（用户："天机 剧组Agents 的那个功能用什么模型 这个部分去掉"）'
           '—— 剧组 Agents 页里**没有**带「推荐」列的表',
           rec_tbl is None,
           f'剧组页表格 {[len(getattr(x, "columns", []) or []) for x in _rec_tbls]}')
        ok('G7b ★★ 剧组 Agents 页本身**还在**（有 ≥1 张表）'
           '—— 防"把整页删了"这种一刀切也能过 G7 的做法',
           len(_rec_tbls) >= 1,
           f'剧组页表格数 {len(_rec_tbls)}')
        for want in ('模型列表', '默认模型', '三档', '模型能力', '文生图', '向量检索'):
            ok(f'G9 「{want}」这一节在页上', want in blob, '')
        ok('G10 ★★★ 「通用参数」整节**没了**（用户：「这部分去掉」）',
           '通用参数' not in blob, '')
        ok('G11 ★★★ 但超时/重试/并发三项**仍然可配**（挪到模型列表下面兜底）',
           '全局兜底' in blob and '并发上限' in blob, '')
        ok('G12 ★★ 演示模式**在最前面**（用户：「演示模式放到前面」）',
           0 <= blob.find('演示模式') < blob.find('模型列表'), '')
        ok('G13 ★★★ 「怎么把账单降下来」**只剩一个标题**（正文进了说明书）',
           '怎么把账单降下来' in blob and '给粗活配便宜模型' not in blob, '')
        # ⚠ 改口径：档名与解释**分成了两条 `ft.Text`**（拼串会让英文界面露中文，
        #   见下面 G15）—— 所以这里不再找 `华彩档：`，而是各找各的。
        # [EN] ⚠ Changed criteria: the tier name and the explanation are **two separate `ft.Text`s**
        # [EN] now (composing one string leaks Chinese into the English UI, see G15 below) -- so this no
        # [EN] longer looks for `Flourish: ` but for each part.
        ok('G14 ★★ 三档**每一档都有解释**（用户：「三档单独解释下 再配置」）',
           all(k in blob for k in ('华彩档', '日常档', '摘要档'))
           and all(k in blob for k in ('关键场面', '常规循环', '压缩、打分')), '')
        # ★★ 三档的解释文案是**变量**传给 `t()` 的（`t(MODELS.TIER_WHY[...])`），
        #   而 `tools/i18n_check.py` 只扫**字面量** `t('…')` —— 那条通道**看不见它**。
        #   于是"忘了登记译文"不会被缺译检查抓到，只会在英文界面上露中文
        #   （本轮实测：`verify_ui_english` 报了 6 处，就是这三档）。
        #   所以这里补一条**进不了扫描器的那半边**。
        # [EN] ★★ The tier explanations are passed to `t()` as a **variable**
        # [EN] (`t(MODELS.TIER_WHY[...])`), and `tools/i18n_check.py` only scans **literal** `t('...')`
        # [EN] calls -- that channel **cannot see it**. So "forgot to register the translation" is not
        # [EN] caught by the missing-translation check and only shows up as Chinese leaking into the
        # [EN] English UI (measured this round: `verify_ui_english` reported 6 spots, exactly these three
        # [EN] tiers). This pins down the half the scanner cannot reach.
        from llm import models as _M
        from i18n import set_lang as _set_lang, t as _t
        _old_lang = get_lang()
        _set_lang('en')
        try:
            _untranslated = [k for k in _M.TIER_FIELDS
                             if _t(_M.TIER_WHY[k]) == _M.TIER_WHY[k]]
        finally:
            _set_lang(_old_lang)
        ok('G15 ★★★ 三档解释**都登记了英文**（它是变量传进 `t()` 的，'
           '缺译检查扫不到这一路）',
           not _untranslated, str(_untranslated))
        shot = await page.take_screenshot()
        if shot:
            (OUT / f'cost_tianji_structure{SUFFIX}.png').write_bytes(shot)
        while VU.open_dialogs(page):
            page.pop_dialog()
        page.update()
        await asyncio.sleep(0.4)
        app.show_global_settings(tab=app.TAB_GLOBAL_EXTERNAL)
        await asyncio.sleep(1.0)
        page.update()
        dlg2 = None
        for d in reversed(VU.open_dialogs(page)):
            if isinstance(d, ft.AlertDialog):
                dlg2 = d
                break
        b2 = '\n'.join(_deep_texts(dlg2))
        ok('G16 ★★★ 「外部创作服务」页含 MuMuAINovel 的配置（2026-10-16 并入，'
           '不再是独立页）',
           'MuMuAINovel' in b2 and '生成参数' in b2, b2[:140])
        # ⚠ G16 原来写的是"那一页里没有『模型列表』"——**验不到**：`ft.Tabs` 把
        #   所有页签的控件**一次性建好**，遍历第 7 页的对象树必然也走到第一页的内容。
        #   改成验**真会错的那件事**：`TAB_GLOBAL_EXTERNAL` 指着的下标，
        #   页签名必须是「外部创作服务」（页序一改，这个常量最容易跟着漂，
        #   而且漂了不报错、只是点错页）。
        # [EN] ⚠ G16 used to say "that page has no 'model list'" -- **untestable**: `ft.Tabs` builds
        # [EN] **all** pages' controls at once, so walking page 7's object tree necessarily reaches page
        # [EN] 1's content too. It now checks **what actually can go wrong**: the index that
        # [EN] `TAB_GLOBAL_EXTERNAL` points at must have the label "External Creative Services"
        # [EN] (a page reorder easily drifts this constant, and drifting does not raise -- it just lands
        # [EN] on the wrong page).
        _labels = _deep_texts(dlg2)
        ok('G17 ★★★ `TAB_GLOBAL_EXTERNAL` 指的正是「外部创作服务」那一页（含 MuMuAINovel）',
           '外部创作服务' in _labels, str(_labels[-8:]))
        ok('G18 ★★ 天机一共 7 页，页签上就能看到那七个名字',
           all(k in _labels for k in ('常规', 'AI模型配置', '外部创作服务',
                                      '界面外观', '运行', '导演与合规',
                                      '剧组 Agents')),
           str(_labels[-9:]))

        # ══ G19 / G19b / G20：2026-10-13「输入框按内容估宽」那一轮 ══════════
        #   用户原话：「…都太长了，请根据内容预估长度全部缩短」+「模型列表 最右边
        #   侧测试结果列太宽了」。两条都改在 `gui/app_flet.py`，这里量的是
        #   **造出来的控件本体宽度**（读源码看不出来 —— 宽度是算出来的）。
        # [EN] ══ G19 / G19b / G20: the 2026-10-13 "size input boxes from their content" round ══
        # [EN] The user's words: "...they're all too long, shorten them all according to the estimated
        # [EN] length of the content" + "the rightmost test-result column of the model list is too wide".
        # [EN] Both were changed in `gui/app_flet.py`; what is measured here is the **width of the built
        # [EN] control body** (invisible in the source -- the width is computed).
        def _field_rows(root) -> list:
            """`mk_field` / `mk_dropdown` 造出来的那些行：`(标签, 本体宽度)`。
                English:
            The rows built by `mk_field` / `mk_dropdown`: `(label, body width)`.
            """
            out = []
            for c in VU.walk(root):
                f = getattr(c, '_field', None)
                if f is None:
                    continue
                lbl = ''
                kids = list(getattr(c, 'controls', None) or [])
                try:
                    lbl = str(kids[0].content.value or '')
                except Exception:                                # noqa: BLE001
                    lbl = ''
                out.append((lbl, int(getattr(f, 'width', 0) or 0)))
            return out

        _fr = _field_rows(dlg2)
        _num = [(l, w) for l, w in _fr
                if l in ('超时(秒)', '重试次数', '并发上限')]
        REPORT.setdefault('field_w', {})['num'] = _num
        ok('G19 ★★ 数字框**按内容收窄**（超时 / 重试 / 并发 三个框本体 ≤ 120px，'
           '不再撑满整行）',
           len(_num) >= 3 and all(64 <= w <= 120 for _, w in _num),
           str(_num))
        # ⚠ **另一半同样重要**：该宽的还得宽（地址 / 密钥 / 目录）。
        #   只判"都窄"的话，把 `_fit_field_w` 改成一律返回 `FIELD_NUM_W`
        #   （一刀切收窄）也照样绿 —— 那正是用户没要的东西。
        # [EN] ⚠ **The other half matters just as much**: what should be wide stays wide (URL / key /
        # [EN] directory). Judging only "everything is narrow" would stay green if `_fit_field_w`
        # [EN] returned `FIELD_NUM_W` for everything (a blanket shrink) -- which is not what the user
        # [EN] asked for.
        _wide = [(l, w) for l, w in _fr
                 if l in ('接口地址', 'API Key', '项目根目录', '日志目录')]
        REPORT['field_w']['wide'] = _wide
        ok('G19b ★★ 该宽的**还是宽的**（接口地址 / API Key / 目录 ≥ 200px）'
           '—— 收的是数字，不是一刀切',
           bool(_wide) and all(w >= 200 for _, w in _wide), str(_wide))
        # G20：「测试结果」那一列。⚠ **直接造一行来量**（`_model_row`），
        #   不从打开的对话框里找 —— 那一列有没有数据取决于用户的模型登记表，
        #   "没数据 ⇒ 量不到 ⇒ 判据绿"正是本项目反复踩的那种假绿。
        # [EN] G20: the "test result" column. ⚠ **Build one row and measure it** (`_model_row`) rather
        # [EN] than hunting in the open dialog -- whether that column has data depends on the user's
        # [EN] model registry, and "no data => nothing to measure => criterion green" is exactly the kind
        # [EN] of fake green this project keeps stepping on.
        from llm import models as _MROW

        def _result_col_w(at_w: int) -> int:
            """在**给定栅格宽度**下造一行，量「测试结果」那一格的实测宽度。"""
            with grid_width(at_w):
                _rows = app._model_row(
                    page, _MROW.ModelEntry(key='_width_probe', label='W'),
                    {'entries': []}, lambda: None)
            return int(getattr(_rows[-1].content, 'width', 0) or 0)

        # ⚠⚠ **必须在天机那种宽栅格下量**，不能只量 520。
        #   反例法实测出来的：520 时新公式 = 140、老公式 = 180 —— **两个都 ≤ 200**，
        #   判据绿着却根本分辨不出新旧（这就是"漏掉"的那一条）。
        #   而模型表**只在天机里出现**（栅格 ~1200+）：那里新公式被 200 卡住、
        #   老公式是 `grid_w()//4` ≈ 312 —— 差了一倍多，一量就红。
        #   所以判的是**这条列有没有上限**，不是"某一次量到几像素"。
        # [EN] ⚠⚠ **It must be measured at the wide grid used by Tianji**, not only at 520.
        # [EN] The counterexample method measured this: at 520 the new formula gives 140 and the old
        # [EN] one 180 -- **both ≤ 200**, so the criterion stays green while being unable to tell old
        # [EN] from new (that is the "missed" one). But the model table **only appears in Tianji**
        # [EN] (grid ~1200+): there the new formula is capped at 200 while the old is `grid_w()//4`
        # [EN] ≈ 312 -- more than double, and it goes red at once.
        # [EN] So what is judged is **whether this column has a cap**, not "how many pixels were
        # [EN] measured once".
        _narrow = _result_col_w(520)
        _wide = _result_col_w(1200)
        REPORT['field_w']['result_col'] = {'at_520': _narrow, 'at_1200': _wide}
        ok('G20 ★★ 「测试结果」那一列**有上限**（≤ 200px）：窄窗口保底 140，'
           '宽栅格下**不再跟着行宽涨**（原来是"行宽的四分之一"，把整张表顶成横向滚动）',
           100 <= _narrow <= 200 and _wide <= 200,
           f'520→{_narrow}px / 1200→{_wide}px')
        shot2 = await page.take_screenshot()
        if shot2:
            (OUT / f'cost_tianji_external{SUFFIX}.png').write_bytes(shot2)
    except Exception:
        ok('G 段整体没崩', False, traceback.format_exc()[-400:])
    finally:
        guard.__exit__(None, None, None)


def _deep_texts(ctrl) -> list[str]:
    """把一棵控件树里**所有** `ft.Text` 都捞出来（含 `DataTable` 的单元格）。

    ★ 为什么不能用公共的 `VU.all_texts()`（2026-10-12 踩的）：它递归 `Column`/`Row`/
      `Container` 这些**容器**，但**不进 `DataTable`** —— 而用量报表第 4 栏正是
      `DataTable`（`columns=[DataColumn(label=Text)]`、`rows=[DataRow(cells=[DataCell
      (content=Text)])]`）。于是判据报"界面上没有『缓存命中 Token』"，
      而**屏幕上明明有**（探针实测：那一栏在，只是没被抓到）。
      **"抓不到"与"没渲染"必须分得开**，否则假红会把真问题淹没。
    
        English:
    Pull **every** `ft.Text` out of a control tree, `DataTable` cells included.
        ★ Why the shared `VU.all_texts()` cannot be used (hit on 2026-10-12): it recurses into
          **containers** like `Column`/`Row`/`Container` but **not into `DataTable`** -- and column 4
          of the usage report *is* a `DataTable`. The criterion then reported "the UI has no
          'Cache-hit tokens'" while **it is visibly there on screen** (probe-measured). **"Not
          captured" and "not rendered" must stay distinguishable**, or false reds drown out real
          problems.
    """
    out: list[str] = []

    def _walk(c) -> None:
        if c is None:
            return
        if isinstance(c, ft.Text):
            v = getattr(c, 'value', None)
            if v:
                out.append(str(v))
        # ★★ 2026-10-12 补：`ft.Switch` / `ft.Checkbox` 的**标签**也要收。
        #   它们把显示文字放在 `label` 属性上（不是 `Text` 子控件），只认 `ft.Text`
        #   的话，"演示模式"这种开关的标题永远找不到 —— 判据就会报"页上没有演示模式"，
        #   而屏幕上明明有（本轮 G12 就是这么假红的）。
        # [EN] ★★ 2026-10-12 added: also collect the **labels** of `ft.Switch` /
        # [EN] `ft.Checkbox`. They keep their display text in a `label` attribute (not a `Text`
        # [EN] child), so recognizing only `ft.Text` means a switch's title like "demo mode" is never
        # [EN] found -- and the criterion reports "no demo mode on the page" while it is visibly there
        # [EN] (G12 went falsely red exactly like that this round).
        if isinstance(c, (ft.Switch, ft.Checkbox)):
            lbl = getattr(c, 'label', None)
            if lbl:
                out.append(str(lbl))
        rows = getattr(c, 'rows', None)
        if isinstance(rows, list):
            for r in rows:
                for cell in (getattr(r, 'cells', None) or []):
                    _walk(getattr(cell, 'content', None))
        cols = getattr(c, 'columns', None)
        if isinstance(cols, list):
            for col in cols:
                _walk(getattr(col, 'label', None))
        # 页签名（`ft.Tab.label`）也要收：它是"这个对话框里有哪几页"唯一的运行时证据。
        # [EN] Tab labels (`ft.Tab.label`) too: they are the only runtime evidence of "which pages this
        # [EN] dialog has".
        tabs = getattr(c, 'tabs', None)
        if isinstance(tabs, list):
            for x in tabs:
                lbl = getattr(x, 'label', None)
                if lbl:
                    out.append(str(lbl))
        for attr in ('controls', 'content'):
            v = getattr(c, attr, None)
            if isinstance(v, list):
                for x in v:
                    _walk(x)
            elif v is not None and not isinstance(v, str):
                _walk(v)

    _walk(ctrl)
    return out


SUFFIX = '' if not LOGIC_ONLY else '_logic'


def _dump(detail: str = '') -> dict:
    """汇总 + **写报告**。两段（逻辑 / 真机）都要写 —— 反例法靠这份报告读"哪几条红了"。

    ⚠ 早先 `--logic-only` 那一段**不写报告**：于是变异之后，反例法只能看到
      "判据自己崩了"，看不到究竟哪条红了 —— 十几条变异全被判成"漏掉"，
      看起来像"判据没用"，实际是"结果没落盘"。
    
        English:
    Summarize and **write the report**. Both sections (logic / real machine) must write it -- the
    [EN] counterexample method reads this report to find "which criteria went red".
        ⚠ Earlier the `--logic-only` branch **did not write a report**: after a mutation the
        [EN] counterexample method could only see "the criterion itself crashed", not which criterion
        [EN] went red -- a dozen mutations were all judged "missed", which looked like "the criteria
        [EN] are useless" when in fact "the result was never written out".
    """
    failed = [n for c, n, _ in checks if not c]
    report = {'total': len(checks), 'passed': len(checks) - len(failed),
              'failed': failed, 'ok': not failed, 'detail': detail,
              'measure': dict(REPORT)}
    (OUT / f'cost_model_report{SUFFIX}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n==== {report["passed"]}/{report["total"]}{detail} ====')
    for n in failed:
        print('  ✗', n)
    return report


def _guard(name: str, fn) -> None:
    """跑一段判据；**崩了就记一条红，而不是把整个脚本带走**。

    ⚠ 这一条是被反例法逼出来的：变异成"读数抛异常"之后，判据脚本自己崩了、
      报告写不出来，于是"红没红"这件事**根本无法判断**。判据要能承受
      "产品代码变得很糟"—— 那正是它存在的意义。
    
        English:
    Run one section; **if it crashes, record one red entry instead of taking the whole script
    [EN] down**.
        ⚠ This rule was forced by the counterexample method: after mutating to "raise on read", the
        [EN] criterion script crashed and wrote no report, making it **impossible to tell** whether it
        [EN] went red. A criterion must survive "the product code became terrible" -- that is exactly
        [EN] why it exists.
    """
    try:
        fn()
    except Exception:
        ok(f'{name} 段整体没崩', False, traceback.format_exc()[-400:])


async def _aguard(name: str, fn) -> None:
    try:
        await fn()
    except Exception:
        ok(f'{name} 段整体没崩', False, traceback.format_exc()[-400:])


def test_h() -> None:
    """H 段：`max_tokens` 的**上限口径**（2026-10-14 用户：「撞到 max_tokens 8192……

    如果是本地配置的 这个很明显已经过时了」）。

    ★ 这一段守的不是"某个数是多少"，而是**三件事**（都是会悄悄回退的点）：
      ① 上限是**本地**决定 / 认得出模型时**走表**（表的优先级 > 兜底值）；
      ② `coerce()` **不夹紧** —— SPEC 的 `max` 必须 ≥ default，否则改了 default
         会被静默夹回去（本轮真踩：max 留 200000，default 写 819200 会被夹成 20 万）；
      ③ 认不出的模型走兜底，且兜底**不再退回旧的 8192**。
    ⚠ 期望值用**绝对下限**（"不小于 8192 的 100 倍"这类），不写死 819200 ——
      用户以后还想再放大时，这条不该变成绊脚石；它守的是"没退回旧口径"。
    [EN] Section H: the **cap policy** for `max_tokens` (2026-10-14 user: "hitting max_tokens 8192
    [EN] ... if it's local config it's clearly outdated").
    [EN] ★ What is guarded is not "which number" but **three things**, all of which can silently
    [EN] regress: ① the cap is **locally** decided / recognized models go **through the table**
    [EN] (table outranks the fallback); ② `coerce()` does **not** clamp -- SPEC's `max` must be >=
    [EN] default, otherwise a raised default gets silently clamped back (hit in this round: `max` left
    [EN] at 200000 clamped a default of 819200 down to 200000); ③ unrecognized models use the fallback
    [EN] and it **no longer falls back to the old 8192**.
    [EN] ⚠ Expectations are **absolute lower bounds** (not a hard-coded 819200) so that raising it again
    [EN] later does not trip this; what is guarded is "the old policy has not come back".
    """
    print('\n── H max_tokens 上限口径（本地 / 表优先 / 不静默夹紧）──')
    from config import CFG, SPEC, coerce
    from llm.capabilities import MAX_OUTPUT_TOKENS, max_output_tokens
    from llm.router import _effective_max_tokens

    # ① 默认模式 = model（认得出 → 走表；认不出 → 走兜底）
    ok('H1 ★★ 默认口径是 `model`（上限由**本地表**决定，不是模型返回的）'
       '—— 用户要确认的正是这一点',
       (CFG.s('LLM_TOKEN_BUDGET_MODE') or '').strip().lower() == 'model',
       f"LLM_TOKEN_BUDGET_MODE={CFG.s('LLM_TOKEN_BUDGET_MODE')!r}")

    # ② hy3（报错那个模型）**在表里**，且上限已抬高（≥ 8192 的 100 倍 = 819200）
    _hy3 = max_output_tokens('hy3')
    ok('H2 ★★★ `hy3` 在模型表里、且上限**已从旧的 8192 抬高**（≥ 819200）'
       '—— 旧值太保守：带思考时思考 + 正文一起吃 max_tokens，8192 只够 1856 字正文',
       _hy3 is not None and int(_hy3) >= 819200,
       f'max_output_tokens(hy3)={_hy3}')

    # ③ 认得出模型 ⇒ 表的优先级高于兜底值（把兜底调小，hy3 仍是表值）
    #   ⚠ 必须 null-safe：表项被删时 `_hy3` 是 None，`int(None)` 会抛 TypeError
    #     把**整段 H 弄崩** —— 那样后面几条（比如 H6"hy3 还在表里吗"）根本跑不到，
    #     反例法会报"漏掉"，看着像判据太松，其实是前一条崩了把后面吞了。
    # [EN] ⚠ Must be null-safe: when the table entry is deleted `_hy3` is None and `int(None)` raises
    # [EN] TypeError, **crashing the whole H section** -- then later checks (e.g. H6 "is hy3 still in
    # [EN] the table") never run, the reverse harness reports "missed", and it looks like a weak
    # [EN] criterion when in fact an earlier check swallowed the rest.
    _by_table = _effective_max_tokens('hy3', 'extract', 2400)
    ok('H3 ★★★ 认得出模型时**走表、不走兜底**（兜底值不影响它）',
       _hy3 is not None and _by_table == int(_hy3),
       f'hy3 生效={_by_table} · 表值={_hy3}')

    # ④ 认不出的模型 ⇒ 走兜底，且兜底**也抬了**（不是 8192）
    _unk = _effective_max_tokens('某个没登记过的模型-xyz', 'extract', 2400)
    ok('H4 ★★★ 认不出的模型走兜底，且兜底**也不再是旧的 8192**（≥ 819200）',
       int(_unk) >= 819200,
       f'未知模型生效={_unk}')

    # ⑤★ `coerce` 不静默夹紧 —— SPEC 的 max 必须容得下 default（本轮真踩的坑）
    _sp = SPEC['LLM_MAX_TOKENS_FALLBACK']
    _val, _warn = coerce('LLM_MAX_TOKENS_FALLBACK', str(_sp['default']))
    ok('H5 ★★★ ★ 抬 default 时 **`max` 必须一起放**：用 default 原样过一遍 `coerce()`，'
       '**不许被夹紧**（它按 SPEC 的 max 静默夹 —— 本轮 max 留 200000 真把 819200 夹成 20 万）',
       _warn is None and int(_val) == int(_sp['default']),
       f"coerce(default={_sp['default']}) → ({_val}, {_warn!r})；"
       f"SPEC max={_sp['max']}")

    # ⑥ 成对：**不许靠"删表项"混过** —— hy3 必须还在表里（删了它就落到兜底，
    #    于是 H2 会红，但那条红是"表丢了"而不是"口径对了"；这里钉住它还在）
    ok('H6 ★★ 成对：`hy3` **仍在表里**（不是靠"把表项删掉落兜底"混过 H2）',
       any('hy3' in str(k) for k, _ in MAX_OUTPUT_TOKENS),
       f"表里有 hy3：{any('hy3' in str(k) for k, _ in MAX_OUTPUT_TOKENS)}")


async def main(page: ft.Page):
    import verify_ui_common as _VU0
    _VU0.redirect_env_writes()
    _guard('A', test_a)
    _guard('B', test_b)
    _guard('C', test_c)
    _guard('D', test_d)
    _guard('H', test_h)
    await _aguard('E', test_e)
    if not LOGIC_ONLY:
        await test_f(page, {})
        # G 段必须在 **F 段之后**：两者都真机、都要开对话框；G 会先把
        # 前面留下的对话框收干净再开天机。
        # [EN] Section G must come **after** F: both are real-machine and open dialogs; G cleans up any
        # [EN] dialogs left behind before opening Tianji.
        await _aguard('G', lambda: test_g(page))
    report = _dump('')
    await shutdown(page, code=0 if report['ok'] else 2)


if __name__ == '__main__':
    if LOGIC_ONLY:
        import verify_ui_common as _VU
        _VU.redirect_env_writes()
        _guard('A', test_a)
        _guard('B', test_b)
        _guard('C', test_c)
        _guard('D', test_d)
        _guard('H', test_h)
        asyncio.run(_aguard('E', test_e))
        rep = _dump(' (logic only)')
        sys.exit(0 if rep['ok'] else 2)
    try:
        ft.run(main)
    except Exception:
        print(traceback.format_exc())
        exit_now(2)
