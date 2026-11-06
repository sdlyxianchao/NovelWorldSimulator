# -*- coding: utf-8 -*-
"""验证：LLM 输出被 `max_tokens` 截断时，**不再静默丢掉整份设定**（v1.40）。

用户报的现象（2026-10-06）：「无法解析LLM返回值 LLM 返回无法解析，原始文本:
{"人物": [{"姓名": "…", ...」——开卷摄取卡在"提取设定"，设定集变成空骨架。

**根因（用那次运行留下的对话日志查出来的，不是猜的）**：
`logs/nws-dialogue-*.log` 里那条 extract 响应，
`8265+3000 token` —— `tout` **正好等于**当时写死的 `max_tokens=3000`，
正文停在半句话里（33 个引号 = 奇数、`{` 2 个 `}` 0 个、`[` 1 个 `]` 0 个，
`json.loads` 报 `Unterminated string`）。也就是说：**输出撞上限被砍断了**。

代码这边有三处是真问题（这一轮全修）：
  1. `max_tokens=3000` 对这份要装下全部人物的 JSON 根本不够，
     而且**提示词没约束字段长度**（用户那份里单个人物的"身份/秘密/目标"就上百字）；
  2. `_real_call` **完全不看 `finish_reason`** → "被截断"这件事对上层不可见，
     所以只能退化成"无法解析"；
  3. 解析不了就 `_empty_skeleton()` —— **已经写完的人物全丢**，界面上只留一句警告。

判据分四组：

**A 抢救函数**（`util.jsonio.repair_json`）
  · ★ **夹具在脚本里自带**（一条砍在半句话里的响应）：`extract_json` 返回空（复现 bug），
    `repair_json` 能把第一个人物完整救回来（7 个字段，只丢被砍在半句里的最后一个）；
  · 各种截断位置都能救：切在字符串中 / 切在 key 后 / 切在数组中间 / 切在数字后 / 带尾逗号；
  · **不编造**：救回来的每个字符串都必须是原文的子串（截断→只能是前缀）；
  · 完整合法的 JSON 走 `repair_json` 结果**一模一样**（不能把好数据弄坏）；
  · 彻底不是 JSON 的文本 → 返回默认值，不抛异常。

**B 路由层把"截断"说出来**（`llm/router.py`）
  · `chat(..., return_meta=True)` 返回 `(文本, 元信息)`，元信息含 `truncated`；
  · 默认（不传）仍然返回字符串 —— 29 处老调用点不受影响；
  · MOCK 下 `truncated=False`、`finish_reason='stop'`；
  · 元信息里带 `max_tokens`（写日志/界面提示要用它说清"撞的是哪个数"）。

**C 提取层三级处理**（`ingest/extractor.py`，用打桩的 LLM，零网络）
  · 第一次就被截断 → **自动重试一次**，且重试的 `max_tokens` 比第一次大；
  · 重试成功 → 用重试的结果，`take_notes()` 里有"已重试"的说明；
  · 重试仍被截断 → **抢救**，人物不为空，且说明里写明"末尾字段可能只写了一半"；
  · 提示词里**必须有长度约束**（不然还是会写到超限）—— 直接查 `_PROMPT` 文本。

**D 提示能传到界面**（`ingest/pipeline.py` + `gui/app_flet.py`）
  · `extract_done` 那一步的 `extra` 里带上了 `take_notes()` 的内容
    （用户才看得见；只写文件日志等于没说）；
  · 界面收到 `truncated` 的响应事件时，会往日志里补一条 `err` 行。

跑法：
    .venv\\Scripts\\python.exe tools/verify_llm_truncation.py
产出：
    assets/screenshots/llm_truncation_report.json

English:
Verification: when LLM output is truncated by `max_tokens`, **no longer silently drops the whole
setting set** (v1.40).
The phenomenon the user reported (2026-10-06): "Cannot parse LLM return value LLM returned
unparseable, raw text:
{"人物": [{"姓名": "…", ..." —— open-book ingestion stuck at "extracting settings", the setting set
became an empty skeleton.
**Root cause (found using the dialogue log left by that run, not guessed)**:
The extract response in `logs/nws-dialogue-*.log`,
`8265+3000 token` —— `tout` **exactly equals** the then-hardcoded `max_tokens=3000`,
the body stops mid-sentence (33 quotes = odd, `{` 2 `}` 0, `[` 1 `]` 0,
`json.loads` reports `Unterminated string`). In other words: **the output hit the limit and was
cut off**.
On the code side there are three real problems (all fixed this round):
  1. `max_tokens=3000` is simply not enough for this JSON that must hold all characters,
     and **the prompt does not constrain field length** (in the user's copy a single character's "identity/secret/goal" is over a hundred characters);
  2. `_real_call` **completely ignores `finish_reason`** → the fact of "being truncated" is invisible to the upper layer,
     so it can only degrade into "unparseable";
  3. When unparseable it calls `_empty_skeleton()` —— **all already-written characters are lost**, leaving only one warning line in the UI.
Assertions are in four groups:
**A Repair function** (`util.jsonio.repair_json`)
  · ★ **The fixture is built into the script** (a response cut off mid-sentence): `extract_json` returns empty (reproduces the bug),
    `repair_json` can fully recover the first character (7 fields, losing only the last one cut off mid-sentence);
  · It can recover at various truncation positions: cut inside a string / after a key / in the middle of an array / after a number / with a trailing comma;
  · **No fabrication**: every string recovered must be a substring of the original text (truncated → can only be a prefix);
  · Complete valid JSON through `repair_json` gives **exactly the same** result (must not corrupt good data);
  · Text that is not JSON at all → returns the default value, does not throw.
**B Routing layer states "truncation"** (`llm/router.py`)
  · `chat(..., return_meta=True)` returns `(text, meta)`, meta contains `truncated`;
  · By default (not passed) still returns a string —— the 29 old call sites are unaffected;
  · Under MOCK `truncated=False`, `finish_reason='stop'`;
  · Meta carries `max_tokens` (used by logging/UI hint to make clear "which number was hit").
**C Extraction layer three-tier handling** (`ingest/extractor.py`, with stubbed LLM, zero
network)
  · Truncated on the first try → **automatically retry once**, and the retry's `max_tokens` is larger than the first;
  · Retry succeeds → use the retry's result, `take_notes()` contains a "retried" note;
  · Retry still truncated → **repair**, characters are not empty, and the note states "the trailing field may be only half written";
  · The prompt **must have a length constraint** (otherwise it will still write past the limit) —— directly check the `_PROMPT` text.
**D The prompt can reach the GUI** (`ingest/pipeline.py` + `gui/app_flet.py`)
  · The `extra` of the `extract_done` step carries the content of `take_notes()`
    (only then can the user see it; writing only to the file log is as good as not saying it);
  · When the GUI receives the `truncated` response event, it appends an `err` line to the log.
How to run:
    .venv\\Scripts\\python.exe tools/verify_llm_truncation.py
Output:
    assets/screenshots/llm_truncation_report.json
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')

from util.jsonio import extract_json, repair_json, parse_or_repair  # noqa: E402
from i18n import set_lang, t, _ZH2EN  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

# ── A 组夹具：一条**被砍在半句话里**的 extract 响应 ──
# [EN] ── Group A fixtures: an extract response that is **cut off mid-sentence** ──
#
# ⚠ 早先这里直接去读 `logs/nws-dialogue-<日期>.log`（某一次真实运行的原文）。两个毛病：
#   ① 那把**一本具体的书**的内容带进了测试 —— 这个程序必须与任何具体作品无关；
#   ② 它依赖一个随时会被 `cleanup_old_logs` 清掉、或用户自己删掉的**用户文件**：
#      文件一没，A 组就静默变哑（第一条判据还会直接红）。
#   现在改成脚本**自己造**一条同样形状的样本：人物字段齐全、断在半句话里。
#   判据 `tools/verify_generic_project.py` 盯着"验证脚本不许读用户日志"这一条。
_FIRST_NAME = '甲'          # 夹具里第一个人物的名字（断言要对得上）
# [EN] ⚠ Earlier this directly read `logs/nws-dialogue-<date>.log` (the raw text of some real run). Two
# [EN] problems:
# [EN] ① It brought the content of **one specific book** into the test —— this program must be
# [EN] independent of any specific work;
# [EN] ② It depends on a **user file** that may be cleared at any time by `cleanup_old_logs`, or
# [EN] deleted by the user:
# [EN] Once the file is gone, Group A silently goes mute (and the first assertion turns red
# [EN] immediately).
# [EN] Now changed so the script **builds its own** sample of the same shape: complete character
# [EN] fields, cut off mid-sentence.
# [EN] The assertion `tools/verify_generic_project.py` enforces the rule "verification scripts must not
# [EN] read user logs".
# [EN] Name of the first character in the fixture (the assertion must match it)


def synthetic_truncated_sample() -> str:
    """造一条"输出撞上 `max_tokens`、砍在半句话里"的 extract 响应。
        English:
    Construct an extract response where "the output hits `max_tokens` and is cut off mid-sentence".
    """
    people = [
        {'姓名': '甲', '身份': '示例身份一', '简介': '示例简介一，大约一句话',
         '性格': '示例性格一', '口癖': '「示例口癖。」',
         '秘密': '示例秘密一，不超过四十个字', '目标': '示例目标一',
         '红线': '示例红线一'},
        {'姓名': '乙', '身份': '示例身份二', '简介': '示例简介二',
         '性格': '示例性格二', '口癖': '「示例口癖二。」',
         '秘密': '示例秘密二', '目标': '示例目标二', '红线': '示例红线二'},
    ]
    full = json.dumps({'人物': people, '世界观': '示例世界观，一到两句话。'},
                      ensure_ascii=False, indent=1)
    # 掐在最后那句的**中间**（不是结构点上）—— 这正是事故的形状
    # [EN] Cut off in the **middle** of the last sentence (not at a structural point) —— this is exactly
    # [EN] the shape of the incident
    return full[:full.rindex('。')]


_ITEMS: list = []          # 断言记录（模块级，`ok()` 直接往里塞）
# [EN] Assertion record (module-level, `ok()` stuffs into it directly)


def ok(name: str, cond, detail: str = '') -> bool:
    _ITEMS.append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    if not cond:
        print(f'FAIL  {name}   [{detail}]')
    return bool(cond)


async def main():
    items = _ITEMS
    report: dict = {}
    set_lang('zh')

    # ══════════ A. 抢救函数 ══════════
    # [EN] ══════════ A. Repair function ══════════
    raw = synthetic_truncated_sample()
    report['fixture_len'] = len(raw)
    ok('A：★ 夹具自带、且形状对（结尾停在半句话里，没有收尾引号/括号）',
       bool(raw) and not raw.rstrip().endswith(('"', '}', ']')),
       f'{len(raw)} 字，结尾 {raw[-8:]!r}')

    if raw:
        ok('A：★ 复现 bug —— `extract_json` 对这条返回空（所以设定集才会变成空骨架）',
           extract_json(raw, {}) == {}, str(extract_json(raw, {}))[:40])
        salv = repair_json(raw, {})
        chars = salv.get('人物') or []
        ok('A：★ 抢救回来至少 1 位人物（以前是 0 位、整份丢失）',
           len(chars) >= 1, f'人物 {len(chars)} 位')
        if chars:
            p = chars[0]
            report['salvaged_person'] = {k: str(v)[:40] for k, v in p.items()}
            ok('A：救回的是**完整字段**（姓名/身份/简介/性格/口癖/秘密/目标 都在）',
               all(p.get(k) for k in ('姓名', '身份', '简介', '性格', '口癖',
                                      '秘密', '目标')),
               str(sorted(k for k, v in p.items() if v)))
            ok('A：救回的姓名对得上（夹具里第一个人物）',
               p.get('姓名') == _FIRST_NAME, p.get('姓名'))
        # 不编造：救回来的每个字符串都得是原文里的子串
        # [EN] No fabrication: every string recovered must be a substring of the original text
        flat = [str(v) for v in (salv.get('人物') or [{}])[0].values()]
        ok('A：★ 没有编造 —— 救回的每个字段都是原文的子串',
           all(s in raw for s in flat if s), str(flat[:2]))

    # 各种截断位置
    # [EN] Various truncation positions
    full = ('{"人物": [{"姓名": "甲", "身份": "乙"}, {"姓名": "丙", "身份": "丁"}], '
            '"世界观": "戊己庚辛", "地点": [{"名称": "壬", "说明": "癸"}], '
            '"关系": [], "伏笔": [], "剧情参考线": "子丑寅卯"}')
    cases = {
        '切在字符串中间': full[:full.index('子丑') + 2],
        '切在 key 冒号后': full[:full.index('"剧情参考线":') + len('"剧情参考线":')],
        '切在数组元素中': full[:full.index('"说明": "癸"') + len('"说明"')],
        '切在数字后': '{"人物": [], "世界观": "甲", "地点": [], "关系": [], "伏笔": [], '
                      '"剧情参考线": "乙", "评档": 12',
        '带尾逗号': '{"人物": [{"姓名": "甲"},], "世界观": "乙",',
        '切在数组开始处': '{"人物": [{"姓名": "甲", "身份": "乙"}], "世界观": "丙", "地点": [',
    }
    bad = []
    for label, text in cases.items():
        v = repair_json(text, None)
        if not isinstance(v, dict) or '人物' not in v:
            bad.append(f'{label}: {v!r}')
    report['truncation_cases'] = {k: bool(repair_json(v, None)) for k, v in cases.items()}
    ok('A：六种截断位置都能救回一个含「人物」的 dict', not bad, ' | '.join(bad))
    # ⚠ 第一版这条写成"'丙' 不该出现" —— 错了：'丙' 在**截断点之前**，本来就该救回来。
    #   "不越界"指的是**不越过截断点**，判据得换成"半截的那个数组不许凭空多出元素"。
    # [EN] ⚠ The first version wrote this line as "'丙' should not appear" —— wrong: '丙' is **before the
    # [EN] truncation point**, so it should have been recovered anyway.
    # [EN] "No out-of-bounds" means **not past the truncation point**; the assertion should be changed to
    # [EN] "the half-cut array must not gain extra elements out of nowhere".
    _cut = repair_json(cases['切在数组开始处'], {})
    ok('A：★ 不越过截断点 —— 半截的「地点」数组救回来是**空数组**（不编造元素）',
       _cut.get('地点') == [], json.dumps(_cut, ensure_ascii=False)[:90])
    # 政策：截在半句里的那个字段**整条丢掉**，不把半句话塞进设定集
    # [EN] Policy: a field cut off mid-sentence is **dropped entirely**, don't stuff a half sentence into
    # [EN] the setting set
    _mid = repair_json(cases['切在字符串中间'], {})
    ok('A：★ 截在半句里的字段整条丢掉，而不塞进半句话（宁缺勿滥）',
       '剧情参考线' not in _mid, repr(_mid.get('剧情参考线')))
    ok('A：★ 但它**前面**那些字段一个都不能少（人物 2 位 / 世界观 / 地点 都在）',
       len(_mid.get('人物') or []) == 2 and _mid.get('世界观') == '戊己庚辛'
       and len(_mid.get('地点') or []) == 1,
       json.dumps(_mid, ensure_ascii=False)[:110])
    ok('A：★ 完整合法的 JSON 走抢救函数**结果不变**（不能把好数据弄坏）',
       repair_json(full, None) == json.loads(full), '')
    ok('A：彻底不是 JSON 时返回默认值、不抛异常',
       repair_json('今天天气不错，我们聊聊别的。', 'X') == 'X'
       and repair_json('', 'X') == 'X' and repair_json(None, 'X') == 'X', '')
    v, was = parse_or_repair(full)
    ok('A：`parse_or_repair` 对合法 JSON 不走抢救（was_repaird=False）',
       isinstance(v, dict) and was is False, str(was))
    v, was = parse_or_repair(raw or cases['切在字符串中间'])
    ok('A：`parse_or_repair` 对截断数据会标出"这是救回来的"', was is True, str(was))

    # ══════════ B. 路由层 ══════════
    # [EN] ══════════ B. Routing layer ══════════
    import inspect

    from llm.router import llm
    sig = inspect.signature(llm.chat)
    ok('B：`chat()` 有 `return_meta` 参数（默认 False，老调用点不受影响）',
       'return_meta' in sig.parameters
       and sig.parameters['return_meta'].default is False, str(sig)[:80])

    import llm.router as R
    src = inspect.getsource(R)
    ok('B：`_real_call` 读了 `finish_reason` 并算出 `truncated`',
       'finish_reason' in src and 'truncated' in src and "'length'" in src, '')
    ok('B：截断时会往日志里写一条 warning（不再无声）',
       'LLM 输出被截断' in src, '')
    ok('B：响应事件里带 `truncated`（界面靠它提示）', '"truncated": truncated' in src, '')

    await llm.ensure_started(APP_DIR / 'logs')
    text, meta = await llm.chat('cheap', [{'role': 'user', 'content': 'x'}],
                                purpose='genre', json_mode=True, return_meta=True)
    report['mock_meta'] = {k: meta.get(k) for k in
                           ('finish_reason', 'truncated', 'max_tokens')}
    ok('B：`return_meta=True` 拿到 (文本, 元信息) 二元组',
       isinstance(text, str) and isinstance(meta, dict), str(type(meta)))
    ok('B：元信息里有 `finish_reason` / `truncated` / `max_tokens` 三个键',
       all(k in meta for k in ('finish_reason', 'truncated', 'max_tokens')),
       str(report['mock_meta']))
    ok('B：MOCK 下不算截断', meta.get('truncated') is False, str(meta.get('truncated')))
    text2 = await llm.chat('cheap', [{'role': 'user', 'content': 'x'}], purpose='genre',
                           json_mode=True)
    ok('B：★ 不传 `return_meta` 时仍然直接返回字符串（29 处老调用点不受影响）',
       isinstance(text2, str), type(text2).__name__)

    # ══════════ C. 提取层三级处理（打桩，零网络）══════════
    # [EN] ══════════ C. Extraction layer three-tier handling (stubbed, zero network) ══════════
    import ingest.extractor as EX

    ok('C：输出上限已从 3000 提上来（3000 就是用户那次撞的数）',
       EX._MAX_OUT_TOKENS > 3000, str(EX._MAX_OUT_TOKENS))
    ok('C：★ 提示词里有字段长度约束（治本：不约束就会写超）',
       '每个字段都要短' in EX._PROMPT and '≤ 30 字' in EX._PROMPT, '')
    ok('C：重试时会把上限再放大', EX._RETRY_FACTOR > 1, str(EX._RETRY_FACTOR))

    class Item:
        category = '正文'
        name = 'x.md'
        content = '雨脚敲着檐瓦。'

    calls: list = []
    real_chat = llm.chat

    def _stub(plan):
        """按 plan 依次返回 (文本, 元信息)。
                English:
        Return (text, metadata) in order according to the plan.
        """
        idx = {'n': 0}

        async def fake(tier, messages, **kw):
            i = min(idx['n'], len(plan) - 1)
            idx['n'] += 1
            calls.append({'max_tokens': kw.get('max_tokens'),
                          'n_messages': len(messages),
                          'return_meta': kw.get('return_meta')})
            text, meta = plan[i]
            meta = dict(meta)
            meta.setdefault('max_tokens', kw.get('max_tokens'))
            return (text, meta) if kw.get('return_meta') else text
        return fake

    trunc = (raw or '{"人物": [{"姓名": "甲", "身份": "示例身份", "简介": "示例简介", '
                   '"性格": "示例性格", "口癖": "示例口癖", "秘密": "示例秘密", "目标": "示例',
           {'truncated': True, 'finish_reason': 'length', 'tout': 3000,
            'has_reasoning': False})

    # C1：第一次截断 → 重试成功
    # [EN] C1: first truncation → retry succeeds
    EX._NOTES.clear()
    calls.clear()
    good = json.dumps({'人物': [{'姓名': '甲', '身份': '乙', '简介': '丙', '性格': '丁'}],
                       '世界观': '戊', '地点': [], '关系': [], '伏笔': [],
                       '剧情参考线': '己'}, ensure_ascii=False)
    llm.chat = _stub([trunc, (good, {'truncated': False, 'finish_reason': 'stop'})])
    try:
        res = await EX.extract_settings([Item()])
        notes = EX.take_notes()
    finally:
        llm.chat = real_chat
    report['c1'] = {'calls': calls, 'notes': notes,
                    'chars': len(res.get('人物') or [])}
    ok('C：被截断后**自动重试了一次**', len(calls) == 2, f'{len(calls)} 次调用')
    ok('C：重试的 `max_tokens` 比第一次大',
       calls[1]['max_tokens'] > calls[0]['max_tokens'],
       f"{calls[0]['max_tokens']} → {calls[1]['max_tokens']}")
    ok('C：重试里加了"写短一点"的追加消息', calls[1]['n_messages'] > calls[0]['n_messages'],
       f"消息数 {calls[0]['n_messages']} → {calls[1]['n_messages']}")
    ok('C：用了重试的结果（人物 1 位）', len(res.get('人物') or []) == 1,
       str(res.get('人物')))
    ok('C：`take_notes()` 里写明了"被截断 + 已重试"（界面要显示它）',
       any('截断' in n and '重试' in n for n in notes), str(notes))

    # C2：两次都截断 → 抢救
    # [EN] C2: both truncated → repair
    EX._NOTES.clear()
    calls.clear()
    llm.chat = _stub([trunc, trunc])
    try:
        res = await EX.extract_settings([Item()])
        notes = EX.take_notes()
    finally:
        llm.chat = real_chat
    report['c2'] = {'calls': len(calls), 'notes': notes,
                    'chars': len(res.get('人物') or [])}
    ok('C：★ 两次都截断时不再返回空骨架 —— 抢救出人物',
       len(res.get('人物') or []) >= 1, f"人物 {len(res.get('人物') or [])} 位")
    ok('C：说明里点明"末尾字段可能只写了一半"（不许把残缺当完整）',
       any('可能只写了一半' in n or '抢救' in n for n in notes), str(notes))

    # C3：完全解析不出来（不是截断）→ 说明要指路
    # [EN] C3: completely unparseable (not truncation) → indicates the need to point the way
    EX._NOTES.clear()
    llm.chat = _stub([('这不是 JSON，只是一段闲聊。',
                       {'truncated': False, 'finish_reason': 'stop'})])
    try:
        res = await EX.extract_settings([Item()])
        notes = EX.take_notes()
    finally:
        llm.chat = real_chat
    ok('C：彻底解析不了时给出的是空骨架（不编数据）',
       res.get('人物') == [] and res.get('世界观') == '', str(res)[:60])
    ok('C：说明里告诉用户"原始文本在哪看"', any('对话日志' in n for n in notes),
       str(notes))

    # ══════════ D. 提示能传到界面 ══════════
    # [EN] ══════════ D. Hints can reach the UI ══════════
    #
    # ⚠ **不能只查源码里有没有那几个字符串**（第一版就是这么写的）：
    #   把 `if _notes: extra += ...` 整段删掉，`'take_notes()' in 源码` 和
    #   `'extract_done' in 源码` 依然为真 —— 判据根本不会红。所以这里**真的跑一遍管线**：
    #   把 `extract_settings` 打桩成"返回空设定 + 留一条提示"，
    #   看 `extract_done` 那一步的 `extra` 里到底有没有把提示带出来。
    # [EN] ⚠ **Cannot just check whether those strings exist in the source** (the first version was written
    # [EN] that way):
    # [EN] Delete the whole `if _notes: extra += ...` block; `'take_notes()' in source` and
    # [EN] `'extract_done' in source` are still true —— the assertion would never turn red. So here we
    # [EN] **actually run the pipeline**:
    # [EN] Stub `extract_settings` to "return empty settings + leave a note",
    # [EN] and see whether the `extra` at the `extract_done` step actually carries the note out.
    import ingest.pipeline as PL

    fixture = Path(tempfile.mkdtemp(prefix='nws_trunc_'))
    (fixture / 'a.md').write_text('# 测试\n\n雨脚敲着檐瓦。\n', encoding='utf-8')

    async def _fake_extract(items, project_name=""):
        EX._note('测试用提示：输出被截断')
        return EX.empty_skeleton()

    stages: list = []
    real_fn = PL.extract_settings
    PL.extract_settings = _fake_extract

    async def _on_stage(stage_id, label, pct, extra=''):
        stages.append({'id': stage_id, 'extra': str(extra)})

    try:
        EX._NOTES.clear()
        await PL.run_ingest(fixture, settings_dir=fixture / '设定集',
                            on_stage=_on_stage)
    finally:
        PL.extract_settings = real_fn
        import shutil
        shutil.rmtree(fixture, ignore_errors=True)
    done = next((s for s in stages if s['id'] == 'extract_done'), None)
    report['extract_done_extra'] = done['extra'] if done else None
    ok('D：★ 真的跑一遍管线 —— `extract_done` 那一步带出了"输出被截断"的提示',
       done is not None and '测试用提示' in done['extra'] and '⚠' in done['extra'],
       str(done and done['extra'])[:120])
    ok('D：提示没把「人物 N 位 · 地点 M 处」顶掉（两样都得在）',
       done is not None and '人物' in done['extra'], str(done and done['extra'])[:80])

    gsrc = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    ok('D：界面收到 `truncated` 的响应事件时会补一条错误行',
       "ev.get('truncated')" in gsrc and '输出被截断' in gsrc, '')
    # ★ 这条**真的把模板渲染一遍**，而不是去 grep 源码里的字面量。
    #   第一版写的是 `"max_tokens={ev.get('max_tokens', '?')}" in gsrc` ——
    #   2026-10-06 把这两条日志改成走 `t()`（英文界面也要能看）之后，
    #   那段 f-string 就不存在了，这条判据**假红**了一轮。
    #   抓"文案里有没有说清撞的是哪个数"，就该看**渲染出来的字**。
    # [EN] ★ This one **actually renders the template**, rather than grepping for literals in the source.
    # [EN] The first version wrote `"max_tokens={ev.get('max_tokens', '?')}" in gsrc` ——
    # [EN] After 2026-10-06 changed these two log lines to go through `t()` (so the English UI can read
    # [EN] them too),
    # [EN] that f-string no longer exists, so this assertion was **falsely red** for a round.
    # [EN] To catch "does the text make clear which number was hit", you should look at the **rendered
    # [EN] text**.
    _tpl = next((k for k in _ZH2EN if '撞到 max_tokens={mt}' in k), '')
    _rendered = t(_tpl, ts='00:00:00', mt=9999, tout=800, rz='') if _tpl else ''
    ok('D：那条提示说明了"撞的是哪个 max_tokens"（渲染出来真的带上了那个数）',
       '9999' in _rendered and '800' in _rendered, _rendered[:70] or '（模板没找到）')
    ok('D：界面把 `ev["max_tokens"]` 传进了那条提示',
       "mt=ev.get('max_tokens'" in gsrc, '')
    set_lang('en')
    _en = t('⚠ 输出被长度上限截断，内容可能不完整')
    set_lang('zh')
    ok('D：新文案中英都有',
       _en != '⚠ 输出被长度上限截断，内容可能不完整' and bool(_en), repr(_en))

    report['items'] = items
    report['n_ok'] = sum(1 for i in items if i['ok'])
    report['n_all'] = len(items)
    report['ok'] = all(i['ok'] for i in items)
    (OUT / 'llm_truncation_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n截断处理验证：{report['n_ok']}/{report['n_all']}")
    for i in items:
        if not i['ok']:
            print(f"  ✗ {i['name']}  [{i['detail']}]")
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
