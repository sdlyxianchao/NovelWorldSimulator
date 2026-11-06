# -*- coding: utf-8 -*-
"""验证：**真模型下"正文被思考吃光"的两道防线**（2026-10-07 加）。

背景（真跑两天推演时实测到的，不是推演）
----------------------------------------
`deepseek-flash` / `deepseek-v4-*` **默认思考**，而思考**连 `max_tokens` 一起吃**。
用 `samples/` 的样例真跑两天，日志里出现 **九处**：

    LLM 一个字都没拿到（max_tokens 全被用光，含思考内容）：**正文为空**

后果不是"少一条产出"，而是**功能整块报废**：

  · `crew_day_map` 挂了 → **当天地图从来没画出来过**（用户上一轮刚点名的功能）
  · `day_verify`  挂了 → 导演验算永远"拿不到结论"，只能带着空意见重写
  · `day_summary` 挂了 → 当天的摘要没有 → **第二天的前情提要就是空的**
  · `crew_research` / `crew_continuity` / `crew_props` / `crew_publicity` 全挂
    → 资料员 / 场记 / 道具 / 宣发 **天天报"没出活"**

两道防线（这一支各钉一条）
--------------------------
  ① **结论型用途关掉思考**（`NO_THINK_PURPOSES`）—— 它的输出主体是"一个结论"
     （一份布局 JSON / 通过与否 / 一份存疑清单），思考帮不上忙却会把额度吃光。
     ⚠ `crew_day_map` 与表里原有的 `minimap_layout` 是**同一个东西的前后两版**：
     当天地图改造时换了用途名，而这张表**没跟着改** —— 于是它从"关思考"
     掉回了"开思考"。这条判据就是防这种"换了名字忘了表"。
  ② **额度不够时自愈**（`LLM_NO_THINK_RETRY`）—— 正文为空**且确实带着思考**
     时，关掉思考重发一次。这是**兜底**：① 管不住"以后新加的用途"。

跑法：.venv\\Scripts\\python.exe tools/verify_llm_budget.py
产出：assets/screenshots/llm_budget_report.json

English:
Verification: **the two lines of defense against "body eaten up by thinking" under the real
model** (added 2026-10-07).
Background (measured during two days of real-run dry run, not a dry run)
----------------------------------------
`deepseek-flash` / `deepseek-v4-*` **think by default**, and thinking **is consumed together
with `max_tokens`**.
Running the samples in `samples/` for two real days, **nine occurrences** appeared in the logs:
    LLM didn't get a single word (max_tokens fully used up, including thinking content): **empty body**
The consequence is not "one less output", but **the whole feature is scrapped**:
  · `crew_day_map` failed → **the day's map was never drawn** (the feature the user just named last round)
  · `day_verify`  failed → the director's verification could never "get a conclusion", and could only rewrite with empty opinions
  · `day_summary` failed → no summary for the day → **the next day's recap is empty**
  · `crew_research` / `crew_continuity` / `crew_props` / `crew_publicity` all failed
    → researcher / script supervisor / props / publicity **report "no output" every day**
Two lines of defense (this branch pins one each)
--------------------------
  ① **Disable thinking for conclusion-type use cases** (`NO_THINK_PURPOSES`) —— their output body is "a conclusion"
     (a layout JSON / pass or fail / a list of doubts); thinking doesn't help but eats up the quota.
     ⚠ `crew_day_map` and the existing `minimap_layout` in the table are **two versions of the same thing before and after**:
     when the day's map was reworked, the use case name was changed, but this table **wasn't changed along with it** —— so it went from "thinking disabled"
     back to "thinking enabled". This criterion is exactly to guard against this kind of "changed the name, forgot the table".
  ② **Self-heal when the quota is insufficient** (`LLM_NO_THINK_RETRY`) —— when the body is empty **and it actually carries thinking**,
     disable thinking and resend once. This is a **fallback**: ① cannot control "use cases added later".
How to run: .venv\\Scripts\\python.exe tools/verify_llm_budget.py
Output: assets/screenshots/llm_budget_report.json
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

from config import SPEC, CFG                                    # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}

#: **输出主体是"一个结论"的用途** —— 它们必须关掉思考。
#: 加新用途进这张表的两条标准（与 `llm/router.py` 的注释一致）：
#:   ① 输出结构的主体是一个结论（是不是 / 哪一类 / 一份结构化判定）；
#:   ② 附带的自由文本只是说明，不是主体。
#: ⚠ 要写东西的（叙事、台词、设定、摘要、改写）**不在表里** —— 它们需要思考，
#:   靠 ② 那条自愈兜底。
# [EN] : **Use cases whose output body is "a conclusion"** —— they must have thinking disabled.
# [EN] : Two criteria for adding a new use case to this table (consistent with the comments in
# [EN] `llm/router.py`):
# [EN] : ① The main body of the output structure is a conclusion (yes/no / which category / a
# [EN] structured verdict);
# [EN] :   ② The accompanying free text is only explanatory, not the main body.
# [EN] : ⚠ Those that need to *write* something (narrative, dialogue, settings, summaries, rewrites)
# [EN] are **not in the table** —— they need thinking,
# [EN] :   and rely on the self-healing fallback ②.
CONCLUSION_PURPOSES = {
    'progress_eval': '进度判据满足了没有（布尔 + 两句说明）',
    'genre': '属于哪个故事类型（一个标签）',
    'alignment': '正文对上了哪几个进度节点（一串 id）',
    'minimap_layout': '旧版小地图布局（一份 JSON）',
    'crew_day_map': '★ 当天地图布局（`minimap_layout` 的后继，同一种东西）',
    'day_verify': '剧本验算（通过 / 不通过 + 几条意见）',
    'crew_research': '考据结论（一份「存疑」清单 + 一句话）',
}

#: 明显偏低的额度（真跑时被思考吃光的那些）。下限取"够思考 + 够输出"的量级。
# [EN] : The noticeably low quotas (the ones that get eaten up by thinking during real runs). The lower
# [EN] bound is set to a magnitude of "enough for thinking + enough for output".
TOKEN_FLOOR = {
    'CREW_ART_TOKENS': 1200,         # 画风说明 —— 与当天地图共用这一项
    # [EN] Art style description —— shares this item with the day's map
    'CREW_PROPS_TOKENS': 1400,
    'CREW_CONTINUITY_TOKENS': 1800,
    'CREW_SETTINGS_TOKENS': 2400,
    'CREW_SCRIPT_TOKENS': 3500,      # 剧作者写当天分镜
    # [EN] The screenwriter writes the day's storyboard
    'CREW_RESEARCH_TOKENS': 1400,
    'CREW_PUBLICITY_TOKENS': 1200,
    'CREW_EXTRA_TOKENS': 800,        # 群众演员 —— 实测也被思考吃光
    # [EN] Extras —— also measured to be eaten up by thinking
}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


# ══════════════════════════════════════════════════════════════════
#  ① 结论型用途必须关思考
# [EN] ① Conclusion-type use cases must have thinking disabled
# ══════════════════════════════════════════════════════════════════
def test_no_think() -> None:
    from llm.router import NO_THINK_PURPOSES
    missing = sorted(set(CONCLUSION_PURPOSES) - set(NO_THINK_PURPOSES))
    ok('A1 ★★ 全部「结论型」用途都进了 `NO_THINK_PURPOSES`'
       f'（{len(CONCLUSION_PURPOSES)} 个）', not missing,
       f'漏了：{missing}' if missing else '都关着思考')

    # 这几个是 2026-10-07 真跑推演时实测"正文为空"之后补进去的 —— 单独钉一遍，
    # 免得以后有人觉得"这条不该关"又删掉（删掉就会退回"当天地图画不出来"）
    # [EN] These few were added after measuring "empty body" during the real-run dry run on 2026-10-07 ——
    # [EN] pin them down individually,
    # [EN] so that later someone won't think "this one shouldn't be disabled" and delete them again
    # [EN] (deleting them reverts to "the day's map can't be drawn")
    for p, why in (('crew_day_map', '当天地图'),
                   ('day_verify', '导演验算'),
                   ('crew_research', '资料员考据')):
        ok(f'A1b ★ {why}（`{p}`）在关思考表里 —— 真跑时它整块不出活',
           p in NO_THINK_PURPOSES, '')

    # 这条防的是**"换了用途名、忘了改表"**：当天地图与旧小地图是同一种东西
    # [EN] What this one guards against is **"changed the use case name, forgot to change the table"**: the
    # [EN] day's map and the old minimap are the same kind of thing
    ok('A2 ★★ 当天地图与旧小地图**同类同待**（换了名字不能掉出这张表）',
       ('crew_day_map' in NO_THINK_PURPOSES)
       == ('minimap_layout' in NO_THINK_PURPOSES), '')

    # 反过来：要"写东西"的用途**不许**进表（关掉思考会伤质量）
    # [EN] Conversely: use cases that need to "write something" **must not** go into the table (disabling
    # [EN] thinking hurts quality)
    WORDS = ('crew_story', 'agent_decide', 'day_summary', 'crew_settings',
             'crew_publicity', 'summary')
    bad = sorted(p for p in WORDS if p in NO_THINK_PURPOSES)
    ok('A3 要"写东西"的用途**没有**被误关掉思考（关了会伤质量）',
       not bad, f'误关：{bad}' if bad else '没误关')


# ══════════════════════════════════════════════════════════════════
#  ② 自愈通路（额度不够时的兜底）
# [EN] ② Self-healing path (fallback when the quota is insufficient)
# ══════════════════════════════════════════════════════════════════
def test_selfheal() -> None:
    src = (APP_DIR / 'llm' / 'router.py').read_text(encoding='utf-8')
    tree = ast.parse(src)

    # 找 `chat()` 里那次"关思考重试"：特征 = 二次调用 `_real_call(..., no_think=True)`
    # [EN] Find that "disable thinking and retry" in `chat()`: signature = the second call `_real_call(...,
    # [EN] no_think=True)`
    chat_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and sub.name == 'chat':
                    chat_fn = sub
    ok('B1 找得到 `chat()`（判据不是空转）', chat_fn is not None, '')
    if chat_fn is None:
        return
    seg = ast.get_source_segment(src, chat_fn) or ''
    ok('B2 ★★ 正文为空时会**关掉思考重试一次**（`no_think=True` 的二次调用在里面）',
       'no_think=True' in seg and seg.count('_real_call') >= 2,
       f'_real_call 出现 {seg.count("_real_call")} 次')

    # 只在"确实带思考"时才重试 —— 不能变成"所有空输出都重试两遍"
    # [EN] Only retry when it "actually carries thinking" —— it must not become "retry twice for all empty
    # [EN] outputs"
    ok('B3 ★ 只在"正文为空 **且** 确实带着思考"时才重试'
       '（别的失败原因不该白花一次调用）',
       "has_reasoning" in seg or "empty_output" in seg, '')
    # ⚠ 2026-10-07：那个开关**搬进了共用判定函数**
    #   `llm.router.should_auto_no_think_retry()` —— `_real_call`（算 `auto_retry`
    #   标记）与 `chat()`（真的重试）共用同一份判定（两处各写一遍会漂，
    #   而漂的方向恰好是"标记说会重试、实际不重试"）。
    #   所以这条判据不能再只看 `chat()` 那一段 —— 会假红。
    # [EN] ⚠ 2026-10-07: that switch **was moved into a shared decision function**
    # [EN] `llm.router.should_auto_no_think_retry()` —— `_real_call` (computes the `auto_retry`
    # [EN] flag) and `chat()` (does the actual retry) share the same decision (writing it twice in two
    # [EN] places would drift,
    # [EN] and the direction of drift happens to be "the flag says it will retry, but actually it
    # [EN] doesn't").
    # [EN] So this check can no longer look only at the `chat()` section —— it would be a false red.
    from llm.router import should_auto_no_think_retry as _auto
    _auto_src = inspect.getsource(_auto)
    ok('B4 重试有开关（`LLM_NO_THINK_RETRY`）—— 排查时能关掉对照'
       '（开关在**共用判定函数**里，两处调用都归它管）',
       'LLM_NO_THINK_RETRY' in _auto_src
       and 'LLM_NO_THINK_RETRY' not in seg,
       f'共用函数里有={"LLM_NO_THINK_RETRY" in _auto_src}；'
       f'chat() 里不再内联={"LLM_NO_THINK_RETRY" not in seg}')
    ok('B5 开关默认是开的（否则新用户第一次跑就撞上"整块不出活"）',
       bool(SPEC.get('LLM_NO_THINK_RETRY', {}).get('default')) is True, '')
    ok('B6 重试仍然撞空时**要说一声**（不能静默再失败一次）',
       '仍然是空的' in seg or '仍然是空' in seg, '')


# ══════════════════════════════════════════════════════════════════
#  ③ 额度下限
# [EN] ③ Quota lower bound
# ══════════════════════════════════════════════════════════════════
def test_tokens() -> None:
    low = []
    for k, floor in TOKEN_FLOOR.items():
        s = SPEC.get(k)
        if not s:
            low.append(f'{k}（没有这一项）')
            continue
        if int(s['default']) < floor:
            low.append(f'{k}={s["default"]} < {floor}')
    ok(f'C1 ★ 这批额度不低于下限（{len(TOKEN_FLOOR)} 项）—— 真跑时它们被思考吃光了',
       not low, '；'.join(low) if low else '都在下限之上')

    # `.env` 覆盖优先 —— 用户实际吃的是这一份，所以也要看
    # [EN] `.env` override takes priority —— that's the one users actually get, so it must be checked too
    env = APP_DIR / '.env'
    if env.is_file():
        text = env.read_text(encoding='utf-8', errors='replace')
        env_low = []
        for k, floor in TOKEN_FLOOR.items():
            for ln in text.splitlines():
                if ln.strip().startswith(k + '='):
                    v = ln.strip().split('=', 1)[1].strip()
                    if v.isdigit() and int(v) < floor:
                        env_low.append(f'{k}={v} < {floor}')
        ok('C2 ★★ `.env` 里的同一批额度也不低于下限'
           '（**生效的是这一份**，只改默认值没用）',
           not env_low, '；'.join(env_low) if env_low else '都够')


# ══════════════════════════════════════════════════════════════════
#  ④ 判据自检
# [EN] ④ Self-check of the criterion
# ══════════════════════════════════════════════════════════════════
def test_self_check() -> None:
    """把 `crew_day_map` 从表里"拿掉"，A1/A1b/A2 必须红。
        English:
    "Remove" `crew_day_map` from the table; A1/A1b/A2 must go red.
    """
    import llm.router as R
    real = R.NO_THINK_PURPOSES
    try:
        R.NO_THINK_PURPOSES = frozenset(set(real) - {'crew_day_map'})
        missing = sorted(set(CONCLUSION_PURPOSES) - set(R.NO_THINK_PURPOSES))
        red = bool(missing)
    finally:
        R.NO_THINK_PURPOSES = real
    ok('D1 ★ 判据自检：把 `crew_day_map` 从表里拿掉，A 组**会红**'
       '（这条检查不是形式）', red, '')
    ok('D2 自检后已还原', R.NO_THINK_PURPOSES is real or
       'crew_day_map' in R.NO_THINK_PURPOSES, '')


def main() -> int:
    print('═' * 62)
    print('  验证：真模型下"正文被思考吃光"的两道防线')
    print('═' * 62)
    try:
        print('\n【A】结论型用途关掉思考')
        test_no_think()
        print('\n【B】自愈通路（额度不够时的兜底）')
        test_selfheal()
        print('\n【C】额度下限')
        test_tokens()
        print('\n【D】判据自检')
        test_self_check()
    except Exception:                                            # noqa: BLE001
        import traceback
        traceback.print_exc()
        report['fatal'] = traceback.format_exc()

    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['passed'] = len(checks) - len(bad)
    report['total'] = len(checks)
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'llm_budget_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  思考额度验证：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
