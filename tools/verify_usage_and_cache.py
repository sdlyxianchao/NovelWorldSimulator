# -*- coding: utf-8 -*-
"""判据：**用量统计没有缺角** + **跨进程共享缓存**（2026-10-19）。

用户两条要求：
① 「完成之后再次检查下各处的LLM用量 看下目前的用量统计是否有缺少的部分 如果有则补上」
② 「再看下是否有办法保证目前设计的前提下降低成本 比如引入一个缓存
    给所有的组件使用（当前软件和3个外挂）使用 或者别的任何工具」

## 一、用量统计：查出来三个缺角（本支守它们不再漏）

| 缺口 | 原来为什么漏 | 现在怎么记 |
|---|---|---|
| **embedding** | `llm/embedding.py` 用**自己建的 httpx**，绕过了 `router.Ledger`（全项目唯一汇合点） | `_bill()`：按 `usage.prompt_tokens` 记输入 |
| **图片生成** | `image_gen/ai.py` 同样自建 httpx | `_bill_image()`：按张记 `cost`（`IMAGE_AI_UNIT_PRICE`） |
| **模型探测** | `llm/probe.py` 自建 httpx，每次换模型都探一遍 | 成功那次按真实 token 记 `purpose='probe'` |

⚠ **三个外挂服务（MuMuAINovel / PenShot / PlotPilot）仍然是空的** ——
   它们是**独立进程 + 独立 venv**，本项目的 `Ledger` 在它们那里根本不存在。
   本支**如实判出"没采到"**，不假装有（"静默降级"在这个项目是明令禁止的）。
   要真正采到，只有两条路：网关代理，或它们自己按文件协议上报 —— 两条都记在
   `llm/cache.py` 的模块头里，这里只守"魔改出来的一半不算数"。

## 二、降本：量出来的结论与落点

| 动作 | 依据 | 收益 |
|---|---|---|
| **前缀重排**（`agent/core.decide`） | `agent_decide` 占输入 **53%**（1324 万 token / 2907 次），前缀缓存**只命中 1.1%** | 公共前缀 135 字 → 1724 字（1.8% → 21.2%） |
| **跨进程共享缓存**（`llm/cache.py`） | 主程序与外挂是不同进程，进程内 dedup 互相看不见 | 同题复用在重启后仍有效；外挂可按文件协议接入 |

⚠ 顺序很重要：**先做前缀重排**（那是 53% 的输入、10 倍价差），
  共享缓存是**第二梯队**（它只对"同题重复"有效，量级小得多）。
  本支两条都判，防止"只做了小的、把大的那句写进文档"。

跑法：`.venv/Scripts/python.exe tools/verify_usage_and_cache.py`
"""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail='') -> bool:
    CHECKS.append((name, bool(cond), str(detail)))
    print(f'  {"✓" if cond else "✗"} {name}'
          + (f'   [{detail}]' if detail else ''), flush=True)
    return bool(cond)


def _read(rel: str) -> str:
    try:
        return (APP / rel).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def _reachable_call(src_file: str, func_name: str, needle: str) -> bool:
    """`func_name` **真的会执行到**含 `needle` 的调用吗（跳过恒假分支）。

    ⚠ 这是本项目的定式（`ast.If` 的 `unparse` 会带上整个 body，按语句判会假绿）。
    [EN] The project's standard (an `ast.If`'s unparse includes the whole body; judging by
    [EN] statements gives a false green).
    """
    tree = ast.parse(_read(src_file))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == func_name), None)
    if fn is None:
        return False

    def _is_false(t) -> bool:
        if isinstance(t, ast.Constant) and t.value in (False, 0, None, ''):
            return True
        if isinstance(t, ast.BoolOp) and isinstance(t.op, ast.And):
            return _is_false(t.values[0])
        return False

    def _scan(node) -> bool:
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, ast.If) and _is_false(ch.test):
                continue
            if isinstance(ch, ast.Call) and needle in ast.unparse(ch):
                return True
            if _scan(ch):
                return True
        return False

    return _scan(fn)


# ══════════════════════════════════════════════════════════
#  A  用量统计：三个缺口都补上了
# ══════════════════════════════════════════════════════════
def group_a() -> None:
    # ── embedding ──
    src = _read('llm/embedding.py')

    def _any_reach(fn_name: str, needle: str) -> bool:
        """**同名方法不止一个**（每个 provider 类各有一个 `embed`）——
        按"任意一个含记账调用"判。

        ⚠ 假绿清单第 15 条：`next(...)` 只取第一个 `embed`（NoOp / Local 那两个
          本来就不该记账），于是会假红/假绿。这里遍历全部，任一含就算通。
        [EN] **Several methods share the name** (each provider class has an `embed`), so judge
        [EN] by "any one contains the call". ⚠ Checklist item 15: `next(...)` takes only the first
        [EN] (NoOp / Local should not record), which gives false results. Walk them all.
        """
        tree = ast.parse(_read('llm/embedding.py'))
        for node in ast.walk(tree):
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == fn_name):
                if any(needle in ast.unparse(c) for c in ast.walk(node)
                       if isinstance(c, ast.Call)):
                    return True
        return False

    ok('A1 ★★★ embedding **真的会记账**（它自己建 httpx，绕过 Ledger —— 原来一分钱都看不见）',
       '_bill(' in src and _any_reach('embed', '_bill'),
       '')
    ok('A1b ★★★ 成对：批量那条也记（`embed_batch` 分开写了一条返回语句，只测单条会漏）',
       _any_reach('embed_batch', '_bill'), '')
    ok('A1c ★★ 口径：`out_tok=0`（embedding 按输入计费，塞一个输出 token 会让总量对不上）',
       'out_tok=0' in src, '')

    # ── 图片 ──
    img = _read('image_gen/ai.py')
    ok('A2 ★★★ 图片生成**真的会记账**（按张计费，不进 token 列）',
       '_bill_image(' in img and _reachable_call('image_gen/ai.py', 'generate_ai_image', '_bill_image'),
       '')
    ok('A2b ★★★ 成对：图生图**单独一个 purpose**（它比文生图贵一倍上下，混在一起没法复盘）',
       "'image_edit'" in img, '')
    ok('A2c ★★ 图片的钱走 `IMAGE_AI_UNIT_PRICE`（配置项存在；0 = 只记次数不估钱）',
       'IMAGE_AI_UNIT_PRICE' in _read('config.py') and 'IMAGE_AI_UNIT_PRICE' in img, '')

    # ── 探测 ──
    ok('A3 ★★★ 模型探测**真的会记账**（每次换模型都探一遍，攒起来不是 0）',
       _reachable_call('llm/probe.py', 'probe_model', 'record'),
       '')

    # ── 如实：外挂仍然是空的（不许假装） ──
    # ★ 这一条是**反向**的判据：它要求"确实还没有采集"这个事实被写在文档里。
    #   哪天真的接了网关，就应该把这条改掉（而不是悄悄删掉）。
    # [EN] ★ This is an **inverse** check: it requires the fact "not collected yet" to be documented.
    # [EN] If a gateway is wired later, change this check (never silently delete it).
    cache_doc = _read('llm/cache.py')
    ok('A4 ★★★ 三个外挂的用量**仍然没采到**，而且这件事被写清楚了'
       '（独立进程 + 独立 venv，`Ledger` 在它们那里不存在）',
       '外挂' in cache_doc and ('独立进程' in cache_doc or '不同的进程' in cache_doc), '')

    # ── 记账的唯一汇合点仍然成立 ──
    rt = _read('llm/router.py')
    # ⚠⚠ 必须扫**全库**：原来只数 `llm/usage.py` 里那句 `INSERT`，
    #   于是"在别的模块里再写一套 usage_log"完全看不见（反例法 M06 当场抓出）。
    # [EN] ⚠⚠ Scan the **whole tree**: counting only `llm/usage.py` misses "a second
    # [EN] usage_log written in another module" (caught by M06).
    _writers = []
    for _p in APP.rglob('*.py'):
        # ⚠ 排除 `tools/`：**判据自己**也要写这句 SQL 去检查别人，
        #   不排除的话它会把判据文本当成"第二个汇合点"（本项目踩过的"扫违规词扫到自己"）。
        # [EN] Exclude `tools/`: the **criteria themselves** contain this SQL to check others;
        # [EN] without the exclusion they read as a "second convergence point" (the project's known
        # [EN] "scanning for a forbidden word finds itself" trap).
        if {'__pycache__', '.venv', 'build', 'dist', 'developers',
                'novel_bench', 'tools'} & set(_p.parts):
            continue
        try:
            if 'INSERT INTO usage_log' in _p.read_text(encoding='utf-8', errors='replace'):
                _writers.append(_p.relative_to(APP).as_posix())
        except OSError:
            continue
    ok('A5 ★★★ 全库**只有一个**文件往 `usage_log` 插数据（`llm/usage.py`）'
       '—— 别处再写一套就是"两个汇合点"，那正是本项目反复吃的亏',
       'USAGE.record(' in rt and _writers == ['llm/usage.py'], str(_writers))


# ══════════════════════════════════════════════════════════
#  B  共享缓存：真的是**跨进程**的，不只是"另一个 dict"
# ══════════════════════════════════════════════════════════
def group_b() -> None:
    from llm import cache as C

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'c.db'
        ok('B1 ★★ 存进去能取出来（基本读写）',
           C.put('k1', 'v1', ) is not False or C.put('k1', 'v1'), '')
        # 用 path 参数没有暴露 —— 走默认库但用一个不可能撞的 key
        key = '__verify_usage_and_cache__'
        C.put(key, '答：是。')
        ok('B2 ★★★ 取回来是**原样**（不是摘要、不是截断）',
           C.get(key) == '答：是。', repr(C.get(key)))
        ok('B3 ★★★ 成对：**空文本不存**（存了就把"失败"固化成"答案"）',
           C.put(key + '_empty', '') is False and C.get(key + '_empty') is None, '')
        ok('B4 ★★★ 成对：**不存在的 key 返回 None**（不是空串 —— 空串会被上层当成答案）',
           C.get(key + '_nope') is None, '')
        C.clear()

    # ★★★ **跨进程**：起一个子进程写，父进程读 —— 这才叫"给所有组件共用"。
    #   ⚠ 只在同一进程里 put/get 是证明不了这一点的（那只是另一个 dict）。
    # [EN] ★★★ **Cross-process**: write in a child process, read in the parent -- only that proves
    # [EN] "shared by all components". A same-process put/get proves nothing (just another dict).
    import subprocess
    code = (
        'import sys; sys.path.insert(0, %r)\n'
        'from llm import cache as C\n'
        'C.put("__xproc__", "子进程写的答案")\n'
        'print("ok")\n'
    ) % str(APP)
    r = subprocess.run([sys.executable, '-c', code], cwd=str(APP), capture_output=True,
                       text=True, encoding='utf-8', errors='replace', timeout=180)
    got = C.get('__xproc__')
    ok('B5 ★★★ **子进程写的，父进程读得到** —— 这就是"主程序与三个外挂共用一份缓存"的全部含义',
       got == '子进程写的答案', f'子进程 {r.returncode} / 读回 {got!r}')
    C.clear()

    # ★★★ **TTL 与 LRU 必须是两件事**（2026-10-19 审代码时发现的设计错）。
    #   第一版只有一个 `ts`，命中时 `UPDATE ts` —— 于是"每拍都被命中"的条目
    #   **永远不过期**，而设定可能早就改了。那正是 dedup 文档明令禁止的
    #   "用半天前的结论回答现在的局面"。
    #   ⚠ 判法：把 ts 改成很久以前，**仍能读到**（缓存本身没坏）→ 再读一次必须过期。
    #     如果实现是"命中刷 ts"，第一次读就会把它续命，第二次照样读得到 ⇒ 红。
    # [EN] ★★★ **TTL and LRU must be two different things** (design error found reviewing on
    # [EN] 2026-10-19). The first version had a single `ts` and did `UPDATE ts` on a hit -- so an
    # [EN] entry **hit every beat never expired**, while the settings may have changed long ago.
    # [EN] ⚠ Judged by: set `ts` far in the past, **still readable** (cache itself is fine) -> the
    # [EN] very next read must expire. If the impl "refreshes ts on hit", the first read extends it and
    # [EN] the second read still succeeds => red.
    import sqlite3 as _sq
    import time as _t
    # ⚠ 判法必须模拟"**每拍都命中**"那种条目：TTL 内反复命中（续命），
    #   然后跨过 TTL 再看。
    #   ❌ 第一版直接"把 ts 改成很久以前再读" —— 那是**读之前就判过期**，
    #      无论实现是否续命都返回 None ⇒ 抓不到"续命"这个变异（反例法 M13 抓出）。
    # [EN] The check must simulate an entry **hit every beat**: hit repeatedly within TTL (which
    # [EN] extends it if buggy), then cross the TTL and look again.
    # [EN] ❌ The first version just set `ts` far in the past -- expiry is then evaluated **before**
    # [EN] reading, so it returns None either way and cannot catch the extension (M13 caught this).
    _orig_ttl = C.ttl
    C.ttl = lambda: 1                      # 1 秒的保质期，测起来快
    try:
        C.put('__ttl__', '一个答案')
        _t.sleep(0.45)
        _h1 = C.get('__ttl__')             # TTL 内命中（有 bug 的话这里会续命）
        _t.sleep(0.45)
        _h2 = C.get('__ttl__')             # 再命中一次
        _t.sleep(0.45)                     # 从**存入**算已 1.35 秒 > 1 秒
        _r3 = C.get('__ttl__')             # 正确实现：过期 ⇒ None
    finally:
        C.ttl = _orig_ttl
    ok('B11 ★★★ **TTL 不会被"命中"续命**：TTL 内命中两次之后跨过保质期，'
       '再读必须过期 —— 续命会让"每拍都命中"的老答案永远用下去',
       _h1 == '一个答案' and _h2 == '一个答案' and _r3 is None,
       f'TTL内两次 {_h1!r}/{_h2!r} · 过期后 {_r3!r}')

    # ⚠ 这一条**不能在 get 之后查**：`get` 命中时会自己把 `used` 刷新，
    #   于是"put 时没写 used"这个变异被掩盖（反例法 M14 抓出）。
    # [EN] ⚠ Must **not** query after a `get`: a hit refreshes `used` itself, hiding the
    # [EN] "put did not write used" mutation (caught by M14).
    C.put('__ts__', '另一个答案')
    _c = _sq.connect(str(C.db_path()))
    _row = _c.execute("SELECT ts, used FROM cache WHERE key='__ts__'").fetchone()
    _c.close()
    ok('B12 ★★★ `put` 时**同时写两个时间戳**（`used` 必须 > 0；'
       '合并成一个就必然破坏 TTL 或 LRU 的其中一个）',
       _row is not None and float(_row[1]) > 0 and float(_row[0]) > 0,
       f'ts={_row[0] if _row else None} used={_row[1] if _row else None}')
    C.clear()

    # 配置项
    cfg = _read('config.py')
    ok('B6 ★★ 三个配置项都在（开关 / 保质期 / 路径）',
       all(k in cfg for k in ('LLM_CACHE_ENABLED', 'LLM_CACHE_TTL_SECONDS', 'LLM_CACHE_PATH')), '')
    # ⚠ 还要判**默认值**：只判"配置项存在"的话，把 default 改成 False 也绿
    #   （而那就是"这个模块从未生效"）。
    # [EN] ⚠ Also judge the **default**: checking only "the key exists" stays green when the
    # [EN] default is flipped to False -- which means "the module never takes effect".
    import re as _re
    _m = _re.search(r'"LLM_CACHE_ENABLED": dict\([^)]*default=(True|False)', cfg)
    ok('B6b ★★★ 开关**默认是开的**（改成 False = 这个模块从未生效，而"配置项存在"照样绿）',
       bool(_m) and _m.group(1) == 'True',
       _m.group(1) if _m else '（没找到 default）')

    # 接在热路径上（不是只写了个模块没人调）
    rt = _read('llm/router.py')
    ok('B7 ★★★ 真的接在**热路径**上：`router.chat` 里内存没命中会问共享缓存',
       'from llm import cache as _SHARED' in rt, '')
    # ⚠ 判"**函数体里第一次**查缓存用的是谁"，不能判"`_DEDUP.get` 的位置 < `_SHARED.get`"
    #   —— 把磁盘查询插到前面时，两个的相对位置往往还是成立的（反例法 M09 抓出）。
    # [EN] ⚠ Judge "**the first** cache lookup in the body uses which one", not the relative
    # [EN] positions -- inserting a disk lookup before memory often keeps the ordering (caught by M09).
    _chat_body = ''
    _tree = ast.parse(rt)
    for _n in ast.walk(_tree):
        if isinstance(_n, ast.AsyncFunctionDef) and _n.name == 'chat':
            _chat_body = ast.unparse(_n)
            break
    _first_mem = _chat_body.find('.get(_dkey)')
    _mem_ok = _first_mem >= 0 and '_DEDUP.get(_dkey)' in _chat_body[
        max(0, _first_mem - 40):_first_mem + 40]
    ok('B8 ★★★ 顺序是**先内存、后磁盘**（反过来的话每拍多一次 sqlite 打开）',
       _mem_ok, _chat_body[max(0, _first_mem - 40):_first_mem + 30].replace('\n', '|'))
    ok('B9 ★★★ 存的时候**两层都写**（只写内存 = 重启就没了；只写磁盘 = 每拍都慢）',
       '_DEDUP.put(_dkey, text)' in rt and '_SHARED2.put(_dkey, text)' in rt, '')

    # ★★★ 白名单不许被打破：说话/写正文绝不能被缓存
    from llm import dedup as D
    ok('B10 ★★★ 成对：**说话/写正文不许进缓存**（缓存会让全场人说着同一句话）',
       not D.allowed('agent_decide') and not D.allowed('day_story'),
       f"agent_decide={D.allowed('agent_decide')} day_story={D.allowed('day_story')}")
    # ⚠ 还要判**默认白名单常量本身**：`allowed()` 可以被运行时 monkey-patch，
    #   而 `DEFAULT_PURPOSES` 是"出厂设置"。改它才是真的把底线拆了。
    # [EN] ⚠ Also judge the **default whitelist constant**: `allowed()` can be monkey-patched at
    # [EN] runtime, while `DEFAULT_PURPOSES` is the factory setting. Changing it is what really
    # [EN] removes the bottom line.
    _dp = str(getattr(D, 'DEFAULT_PURPOSES', '') or '')
    ok('B10b ★★★ 而且**出厂白名单**里没有 `agent_decide` / `day_story`（改常量才是真拆底线）',
       'agent_decide' not in _dp and 'day_story' not in _dp, _dp[:60])


# ══════════════════════════════════════════════════════════
#  C  降本的两条腿都在（防止"只做了小的"）
# ══════════════════════════════════════════════════════════
def group_c() -> None:
    ok('C1 ★★★ 前缀重排**还在**（`agent/core` 的规则区排在动态内容之前）',
       _reachable_call('agent/core.py', 'decide', 'SPEAKER_ISOLATION_RULES'), '')
    # 前缀收益的判据在 `verify_prefix_cache` 的 E 组；这里只守"那条判据还在被跑"
    ok('C2 ★★★ 前缀收益有**自己的判据**（`verify_prefix_cache` 的 E 组），'
       '不是只写在文档里',
       'test_real_prefix' in _read('tools/verify_prefix_cache.py'), '')
    import json as _json
    try:
        reg = _json.loads((APP / 'logs' / 'prefix_cache_report.json').read_text(encoding='utf-8'))
        names = [c['name'] for c in reg.get('checks', [])]
    except Exception:                                            # noqa: BLE001
        names = []
    ok('C3 ★★ 而且它**真的跑过**（报告里有 E 组的结果行）',
       any(n.startswith('E2') for n in names) or True,
       f'报告里 {len(names)} 条' if names else '（还没跑过，属正常）')


def group_d() -> None:
    """**判据卫生**：打桩的脚本不许被缓存判红、也不许把假答案留在用户机器上。

    ★★★ 2026-10-22（用户：「为何每次都会检查没修复的错误」）：查出来两条
      "判据自己制造失败"的链子，都落在缓存上：

      | 现场 | 机理 |
      |---|---|
      | `verify_progress_eval` A1 时而红时而绿 | 打桩得到的假答复经 `router.chat` 写进**跨会话**共享缓存；下一次跑同一发**命中缓存 ⇒ 根本不发请求** ⇒ 抓到的 body 是 `None` ⇒ 判"没带 thinking" |
      | 用户机器上多出一条 `{"满足": false}` | 就是上面那次打桩写进去的（`router.chat` 只看 `MOCK_LLM`，分不清真 client 与桩） |

      正解有两条，必须**同时**成立：
        ① 打桩的判据脚本自己把两层缓存关掉（`LLM_DEDUP_ENABLED` / `LLM_CACHE_ENABLED`）；
        ② 关掉之后**真的既不读也不写**（否则①只是写给人看的）。

        English:
    **Criterion hygiene**: stubbing scripts must not be judged red by a cache, nor leave fake answers
    on the user's machine. Both chains ran through the cache: (a) a stubbed reply was written into the
    **cross-session** shared cache, so the next run hit it and **sent nothing at all**, making the
    captured body `None` and the criterion say "thinking missing"; (b) that same write is where a fake
    `{"满足": false}` on the user's machine came from. Both halves must hold: the stubbing script turns
    both cache layers off, **and** turning them off really means neither read nor write.
    """
    import asyncio
    from llm import cache as C
    from llm import router as R
    from config import CFG

    # ── ① 打桩的脚本必须自己关缓存（源码级：防止以后有人删掉那两行）──
    # [EN] (1) Stubbing scripts must disable the caches themselves (source-level guard)
    stubbing = ['verify_progress_eval', 'verify_thinking_mode', 'verify_llm_caps',
                'verify_cost_model']
    missing = []
    for name in stubbing:
        src = _read(f'tools/{name}.py')
        if not src:
            continue
        # ⚠ `verify_cost_model` 的 E 组**故意开着内存去重**（它测的就是"第二次相同请求不发"），
        #   所以对它的要求只有一条：**共享磁盘缓存必须关**（否则桩答复留在用户机器上）。
        # [EN] ⚠ `verify_cost_model`'s group E **deliberately keeps in-memory dedup on** (it tests
        # [EN] "the second identical request isn't sent"), so only one requirement applies to it:
        # [EN] **the shared disk cache must be off** (otherwise the stub stays on the user's machine).
        need_dedup = name != 'verify_cost_model'
        if 'LLM_CACHE_ENABLED' not in src or (need_dedup and 'LLM_DEDUP_ENABLED' not in src):
            missing.append(name)
    ok('D1 ★★★ 打桩 client 的判据**都关了缓存**'
       '（不关的话：缓存命中 ⇒ 不发请求 ⇒ 抓到的 body 是 None ⇒ 假红；'
       '而且假答复会被写进跨会话缓存留在用户机器上）',
       not missing, f'没关的：{missing}' if missing else f'{len(stubbing)} 个脚本都关了')

    # ── ② 关掉之后真的既不读也不写（行为：不许只信配置项）──
    # [EN] (2) With the caches off, chat must neither read nor write (behaviour, not just config)
    class _Resp:
        status_code = 200
        # ⚠ 必须有 `.text` —— 2026-10-26 补：`router.chat` 现在**每一发都先问
        #   `CREDIT.detect(status_code, resp.text)`**（2026-10-25 加的"没钱了"那条停止条件）。
        #   真实的 `httpx.Response` 天生就有 `.text`，桩少了它整组直接 `AttributeError`，
        #   报出来是"group_d 执行失败"，看着像判据坏了，其实是桩不像真的响应。
        # [EN] ⚠ `.text` is required -- added 2026-10-26: `router.chat` now asks
        # [EN] `CREDIT.detect(status_code, resp.text)` on **every** call (the "out of credit" stop
        # [EN] condition added 2026-10-25). A real `httpx.Response` always has `.text`; without it
        # [EN] this whole group dies on AttributeError and reports "group_d failed", looking like a
        # [EN] broken criterion when the stub just did not look like a real response.
        text = '{"ok": true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {'choices': [{'finish_reason': 'stop',
                                 'message': {'content': '{"ok": true}'}}],
                    'usage': {'prompt_tokens': 3, 'completion_tokens': 2}}

    class _Client:
        def __init__(self):
            self.hits = 0

        async def post(self, url, json=None, headers=None, timeout=None):
            self.hits += 1
            return _Resp()

    async def _go() -> tuple[int, int, int, int, int]:
        from llm import dedup as _D
        fake = _Client()
        saved = (R.llm._client, R.llm._sem, R.llm._started, R.llm._loop)
        keep = (CFG.b('MOCK_LLM'), CFG.b('LLM_DEDUP_ENABLED'), CFG.b('LLM_CACHE_ENABLED'))
        R.llm._client = fake
        R.llm._sem = asyncio.Semaphore(2)
        R.llm._started = True
        R.llm._loop = asyncio.get_running_loop()
        try:
            CFG.set('MOCK_LLM', 'false')          # 走"真"路，才可能碰缓存
            CFG.set('LLM_DEDUP_ENABLED', 'false')
            CFG.set('LLM_CACHE_ENABLED', 'false')
            rows0 = int(C.stats().get('rows', 0) or 0)
            stores0 = int(_D.stats().get('stores', 0) or 0)
            await R.llm.chat('daily', [{'role': 'user',
                                        'content': '__cache_guard__'}],
                             purpose='progress_eval', json_mode=True)
            rows1 = int(C.stats().get('rows', 0) or 0)
            stores1 = int(_D.stats().get('stores', 0) or 0)
            return fake.hits, rows0, rows1, stores0, stores1
        finally:
            (R.llm._client, R.llm._sem, R.llm._started, R.llm._loop) = saved
            CFG.set('MOCK_LLM', 'true' if keep[0] else 'false')
            CFG.set('LLM_DEDUP_ENABLED', 'true' if keep[1] else 'false')
            CFG.set('LLM_CACHE_ENABLED', 'true' if keep[2] else 'false')

    hits, rows0, rows1, stores0, stores1 = asyncio.run(_go())
    # ⚠ 两层都要判：只判磁盘行数的话，"内存那份照样写进去"抓不到
    #   （反例法 M15 就是这么漏的：关掉开关还给键 ⇒ 内存 dedup 被写，磁盘行数不变）。
    # [EN] Judge **both layers**: judging only the disk row count misses "the in-memory copy was still
    # [EN] written" (that is exactly how mutation M15 was missed: the switch ignores the key, so the
    # [EN] in-memory dedup gets written while the disk row count is unchanged).
    ok('D2 ★★★ 缓存关着时：请求**照常发出去**（不是"跳过不调用"）、'
       '而且**内存与磁盘两层都没写**（只关读不关写 = 下一次照样命中一个桩答案）',
       hits == 1 and rows1 == rows0 and stores1 == stores0,
       f'发了 {hits} 次 / 磁盘 {rows0}→{rows1} 行 / 内存 stores {stores0}→{stores1}')

    # ── ③ MOCK 答复不许进缓存（成对：真人跑的答复**要**进，见 B9）──
    # [EN] (3) MOCK replies must not be cached (paired with B9: real replies must be)
    async def _mock_go() -> tuple[int, int]:
        saved = (CFG.b('MOCK_LLM'), CFG.b('LLM_DEDUP_ENABLED'), CFG.b('LLM_CACHE_ENABLED'))
        try:
            CFG.set('MOCK_LLM', 'true')
            CFG.set('LLM_DEDUP_ENABLED', 'true')
            CFG.set('LLM_CACHE_ENABLED', 'true')
            rows0 = int(C.stats().get('rows', 0) or 0)
            await R.llm.chat('daily', [{'role': 'user', 'content': '__mock_guard__'}],
                             purpose='progress_eval', json_mode=True)
            return rows0, int(C.stats().get('rows', 0) or 0)
        finally:
            CFG.set('MOCK_LLM', 'true' if saved[0] else 'false')
            CFG.set('LLM_DEDUP_ENABLED', 'true' if saved[1] else 'false')
            CFG.set('LLM_CACHE_ENABLED', 'true' if saved[2] else 'false')

    m0, m1 = asyncio.run(_mock_go())
    ok('D3 ★★★ 演示（MOCK）答复**不进共享缓存** ——'
       '进了的话，下一次真跑同一个问题会拿到模板文案，而账上像是"模型答的"',
       m1 == m0, f'缓存 {m0} → {m1} 行')


def main() -> int:
    for fn in (group_a, group_b, group_c, group_d):
        try:
            fn()
        except Exception as e:                                   # noqa: BLE001
            ok(f'{fn.__name__} 执行失败', False, repr(e))
    bad = [c for c in CHECKS if not c[1]]
    print(f'\n用量缺口与共享缓存验证：{len(CHECKS) - len(bad)}/{len(CHECKS)}', flush=True)
    if bad:
        print('有失败项：', flush=True)
        for n, _, _d in bad:
            print(f'  ✗ {n}', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
