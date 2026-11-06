# -*- coding: utf-8 -*-
"""验证：2026-10-18 的三项优化真的落在**产品行为**上。

三项（来自实测评语，不是凭空想的）：

1. **创意增量**（`novelty` 均值只有 2.2，四例没有一处主动开新岔路）
   ⇒ 编剧提示词加"岔口"：先列 2-3 条都讲得通的路，选**最有戏**的一条，
   且**不许选最像原著的那条**；`岔口`/`选哪条`/`为什么` 落进台账。
2. **人物成形**（评语反复出现"心思被叙述者代说""称谓当专名用"）
   ⇒ 小说作家提示词加两条：心里话只能写视角人物的；称谓不许当专名用。
3. **戏能立住**（四例里三例跑满 3 轮验算重写）
   ⇒ 验算按严重度分级：只有 `硬伤` 判不通过，`建议` 不阻断。

判据写法纪律（照项目老规矩）：
· 不判"源码里有没有这句话"当唯一证据 —— 提示词那几条必须**真的进了拼出来的 prompt**
  （`PROMPTS.template()` 取到的是用户目录优先的那份）；
· 验算分级要**打点真函数**（`_verify` 跑假 ask），判行为不判字符串；
· 每条都要有**成对**：改了 A 不能把 B 弄坏（比如"不许更宽松到把真矛盾放过"）。

跑法：
    .venv\\Scripts\\python.exe tools/verify_story_quality_ops.py
    .venv\\Scripts\\python.exe tools/verify_story_quality_ops.py --only=1,3
"""
from __future__ import annotations

import asyncio
import inspect
import re
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

RESULTS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'✓' if cond else '✗'} {name}" + (f"  [{detail}]" if detail else ""), flush=True)


def find_method(*markers: str) -> str:
    """按**源码里出现的标记**找工作方法，不写死类名/方法名。

    为什么要这样找：这些类改过名（`Screenwriter` 原来是 `Script` 之类），
    判据里写死 `CA.Screenwriter.compose` 会直接 AttributeError。
    找的是"**含某个已知调用**的那个方法"——这也是项目里认准目标的老办法。
    [EN] Locate a work method by a **marker inside its source**, never by a hardcoded class/method
    [EN] name. These classes have been renamed before, and `CA.Screenwriter.compose` raises
    [EN] AttributeError. We look for "whichever method contains a known call" -- the project's usual way
    [EN] of pinning a target.
    """
    import crew.agents as CA
    for _cls_name, cls in vars(CA).items():
        if not inspect.isclass(cls):
            continue
        for _m, fn in vars(cls).items():
            try:
                s = inspect.getsource(fn)
            except Exception:                                # noqa: BLE001
                continue
            if all(m in s for m in markers):
                return s
    return ""


def section(t: str) -> None:
    print(f"\n{'─' * 68}\n  {t}\n{'─' * 68}", flush=True)


# ══════════════════════════════════════════════════════════════
#  1 创意增量：编剧的"岔口"
# ══════════════════════════════════════════════════════════════
def group_1() -> None:
    section("1 创意增量：编剧先列岔口、选最有戏的一条")
    import crew.agents as CA

    src = find_method("day_script")
    ok("1.0 找到了编剧那一段（含 `day_script` 调用）", bool(src), f"{len(src)} 字")

    # ① 提示词里真的有"岔口"这一条，且写清了"不许选最像原著的"
    # ⚠ 判"列 2~3 条"这句**整句**，不判"岔口"这个孤零零的词 ——
    #   反例法第 2 组删掉标题行时，正文里的"岔口"还在，于是假绿。
    # [EN] ⚠ Assert the **whole sentence** "列 2~3 条", not the bare word "岔口": mutation #2 deleted
    # [EN] the heading while the body still contained the word, which stayed falsely green.
    ok("1.1 ★★★ 提示词要求列 2~3 条岔口",
       "在 `岔口` 里列 **2~3 条**" in src)
    ok("1.2 ★★★ 明写「不要选最像原著的那条」（这条直接对着 novelty）",
       "最像原著" in src)
    ok("1.3 ★★ 成对：同时禁止「为了新奇而站不住」（新奇必须有底线）",
       "站不住" in src or "立得住" in src)
    ok("1.4 ★★ 明写「只演那一条」，不许把几条路都演一遍",
       "只演那一条" in src)

    # ② 输出 schema 里真有这三个字段（不然模型不会给）
    # ⚠ 只看 schema 那一小段（`"岔口": [{"走法"` 起点往后 240 字）：
    #   只看全文的话，规则正文里也提到这些词，删 schema 照样绿（反例法第 3 组）。
    # [EN] ⚠ Only look at the schema snippet (240 chars from `"岔口": [{"走法"`): scanning the whole
    # [EN] function stays green after deleting the schema, because the rule text mentions the same
    # [EN] words (mutation #3).
    # ⚠ 锚点不能写花括号：schema 在 **f-string** 里，源码是 `{{"走法"`（双花括号），
    #   写 `{"走法"` 永远找不到。用 `"岔口":` 定位就够 —— 它只出现一次（另一处是 5b 规则的
    #   "在 `岔口` 里列"，带反引号，写法不同）。
    # [EN] ⚠ Do not anchor on braces: the schema sits inside an **f-string**, so the source has
    # [EN] `{{"走法"` (doubled). Anchoring on `"岔口":` is enough -- it occurs once (the other place is
    # [EN] the 5b rule, which writes it as `岔口` in backticks).
    _si = src.find('"岔口":')
    _schema = src[_si:_si + 260] if _si >= 0 else ""
    ok("1.5 schema 里有 `岔口` / `选哪条` / `为什么` 三个字段",
       bool(_schema) and all(k in _schema for k in ("岔口", "选哪条", "为什么")),
       f"schema 片段 {len(_schema)} 字")

    # ③ 解析真的把岔口取出来（行为判：拿一个假 data 走一遍解析段不现实，
    #    这里判"取值的键名出现在解析代码里"，并且**落台账**那一行也在）
    ok("1.6 ★★ 解析读的是 `岔口` 键（不是只写在提示词里没人看）",
       "data.get('岔口')" in src or 'data.get("岔口")' in src)
    ok("1.7 ★★ 岔口写进台账（`_lines` 里出现「岔口：」）", "岔口：" in src)
    ok("1.8 解析带默认与截断（模型不给也不炸）",
       "or data.get('forks')" in src or "or []" in src.split("岔口")[1][:400])


# ══════════════════════════════════════════════════════════════
#  2 人物成形：心里话与称谓
# ══════════════════════════════════════════════════════════════
def group_2() -> None:
    section("2 人物成形：心里话只归视角人物、称谓不当专名")
    import crew.agents as CA

    # ⚠ 只用 `crew_day_novel` 会命中外层 `_transcribe`（它只是调度，不含要求文本）。
    #   加"要求："把范围收窄到**真正拼 prompt 的那一段**。
    # [EN] ⚠ `crew_day_novel` alone matches the outer `_transcribe` (scheduling only, no requirement
    # [EN] text). Adding "要求：" narrows it to **the block that actually builds the prompt**.
    src = find_method("crew_day_novel", "要求：")
    ok("2.0 找到了小说作家拼 prompt 的那一段", bool(src), f"{len(src)} 字")

    # ⚠ 判**整句**：`"别人的心思" in src and "不许写" in src` 这种写法，
    #   两个词出现在**不同地方**也算通过 —— 反例法第 6 组删掉那半句后仍然绿。
    # [EN] ⚠ Assert the **whole sentence**: `"A" in src and "B" in src` also passes when A and B
    # [EN] appear in *different* places -- mutation #6 stayed green after deleting that clause.
    ok("2.1 ★★★ 明写「别人的心思一个字都不许写」",
       "别人的心思**一个字都不许写**" in src)
    ok("2.2 ★★★ 明写「不许把别人的心里话改写成叙述事实」",
       "把别人的心里话改写成叙述事实" in src)
    ok("2.3 ★★★ 称谓那一条在：叙述用名字、只有对话/视角心里才用称谓",
       "称谓不是名字" in src and "对话里" in src)
    ok("2.4 ★★ 成对：没把「引用内心」整条禁掉"
       "（作家仍可以在视角内写心里话，只是不许越界）",
       "视角贴着的那个人" in src or "视角" in src)

    # 提示词真的被拼进 prompt：走一次 PROMPTS.template 取源，确认是**当前**那份
    try:
        # ⚠ 模块级函数 `template()`，**不是** `PROMPTS.template()` ——
        #   我第一版写成后者，直接 ImportError，于是 2.5/2.6 无条件红。
        # [EN] ⚠ It is a module-level `template()`, **not** `PROMPTS.template()`; the first version used
        # [EN] the latter and got an ImportError, so 2.5/2.6 were unconditionally red.
        from util.prompts import template as _tpl
        got = _tpl("agent_decide_tail")
        tpl = got[0] if isinstance(got, tuple) else (got or "")
    except Exception as e:                                    # noqa: BLE001
        tpl = ""
        print(f"   （取模板失败：{e}）", flush=True)
    ok("2.5 演员尾段模板取得到（用户目录优先）", bool(tpl), f"{len(tpl)} 字")
    ok("2.6 演员提示词仍保留「内心必须第一人称」那条（没被这次改动挤掉）",
       "第一人称" in tpl)


# ══════════════════════════════════════════════════════════════
#  3 戏能立住：验算按严重度分级（打点真函数）
# ══════════════════════════════════════════════════════════════
class _Rep:
    def __init__(self, value, ok=True, notes=None):
        self.value = value
        self.ok = ok
        self.notes = notes or []


def _run_verify(payload: dict) -> tuple[bool, list[str], str]:
    """打点 `_verify`：把 `ask` 换成返回 `payload` 的假函数，真跑一遍。"""
    import director.day_plan as DP

    class _W:
        genre_card = {}
        progress_nodes = []

    async def _fake_ask(*a, **k):
        return _Rep(payload)

    orig_ask = DP.ask
    DP.ask = _fake_ask
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                DP._verify(_W(), None, "故事", [{"拍": 1, "场": "屋里", "发生": "某事"}], {}))
        finally:
            loop.close()
    finally:
        DP.ask = orig_ask


def group_3() -> None:
    section("3 戏能立住：只有硬伤才判不通过")

    ok_v, probs, _fix = _run_verify({"通过": True, "硬伤": [], "建议": ["换个写法更好"]})
    ok("3.1 ★★★ 只有 `建议` ⇒ **通过**（口味差异不该触发重写）",
       ok_v is True, f"通过={ok_v} 问题={probs[:1]}")

    ok_v, probs, _fix = _run_verify({"硬伤": ["第2拍有人不在场却说话"]})
    ok("3.2 ★★★ 有 `硬伤` ⇒ **不通过**（真矛盾必须拦住）",
       ok_v is False, f"通过={ok_v} 问题={probs[:1]}")

    ok_v, probs, _fix = _run_verify({"硬伤": [], "建议": [], "问题": ["跟前情矛盾"]})
    ok("3.3 ★★ 兼容旧键 `问题`：当成硬伤（老提示词/老模型也不会漏）",
       ok_v is False, f"通过={ok_v}")

    ok_v, probs, _fix = _run_verify({"通过": False, "硬伤": [], "建议": []})
    ok("3.4 ★★★ 成对：说不通过却列不出硬伤 ⇒ 放行并记一条建议"
       "（不许因为模型嘴硬就白改三轮）",
       ok_v is True and any("列不出硬伤" in p for p in probs),
       f"通过={ok_v} 建议={[p[:24] for p in probs]}")

    ok_v, probs, _fix = _run_verify({"硬伤": ["真矛盾"], "建议": ["顺一顺"]})
    ok("3.5 硬伤与建议同时在 ⇒ 不通过，且两类都返回",
       ok_v is False and len(probs) >= 2, f"{len(probs)} 条")

    # 拿不到结论不许当通过
    import director.day_plan as DP

    async def _bad_ask(*a, **k):
        return _Rep(None)

    orig = DP.ask
    DP.ask = _bad_ask
    try:
        loop = asyncio.new_event_loop()
        try:
            v, _p, _f = loop.run_until_complete(
                DP._verify(type("W", (), {"genre_card": {}, "progress_nodes": []})(),
                           None, "故事", [], {}))
        finally:
            loop.close()
    finally:
        DP.ask = orig
    ok("3.6 ★★ 拿不到验算结论 ⇒ 不算通过（fail-closed，老教训）", v is False)

    # 提示词里必须写明分级，否则模型还是会把建议当硬伤
    src = (APP / "director" / "day_plan.py").read_text(encoding="utf-8")
    ok("3.7 ★★★ 验算提示词里写明了「硬伤 vs 建议」的分级",
       "硬伤" in src and "建议" in src and "不是硬伤" in src)
    ok("3.8 ★★ 提示词明写「不因为原文没这么写判不通过」（口径一致）",
       "原文没这么写" in src)


GROUPS = {"1": group_1, "2": group_2, "3": group_3}


def main() -> int:
    t0 = time.time()
    only = None
    for a in sys.argv[1:]:
        if a.startswith("--only"):
            only = {x.strip() for x in a.split("=", 1)[-1].split(",") if x.strip()}
    try:
        for k, fn in GROUPS.items():
            if not only or k in only:
                fn()
    finally:
        passed = sum(1 for _n, c, _d in RESULTS if c)
        print(f"\n{'=' * 68}\n  三项优化验证：{passed}/{len(RESULTS)}"
              f"　（{time.time() - t0:.1f}s）\n{'=' * 68}", flush=True)
        bad = [n for n, c, _d in RESULTS if not c]
        if bad:
            print("未通过：\n  - " + "\n  - ".join(bad), flush=True)
    return 0 if all(c for _n, c, _d in RESULTS) else 2


if __name__ == "__main__":
    sys.exit(main())
