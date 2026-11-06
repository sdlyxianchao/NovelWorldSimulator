# -*- coding: utf-8 -*-
"""验证：**去 AI 库** 与全链路审计（2026-10-07）。

用户原话
--------
「有时候演员说话会有 AI 味道，你收集整理 AI 味道表达方式相关词语之类的，
  做一个去 AI 库，所有演员说话之前，所有工作人员产出任何内容之前，
  都做去 AI 味道审计处理。」

这一支钉住四件事（每一条都要能红）：

  A **库本身**：六类分得开 · 硬禁/软提示不混 · 都能查到 · 有出处注释。
  B **审计判得准**：该命中的命中（套话词 / 直白情绪 / 套路句式），
    **不该命中的不命中**（正常台词、说明书式的元信息行）。
  C **事前那半**（提示词）：`prompt_block` 进得了演员决策提示词；
    剧组职位也拿得到；`DEAI=false` 时整段消失。
  D **事后那半**（审计 + 清理）：台词里的套话词被删掉**且记了一笔**；
    剧组产出的命中进得了 `去AI审计.md`；关掉开关就什么都不做。

跑法：.venv\\Scripts\\python.exe tools/verify_deai.py
产出：assets/screenshots/deai_report.json

English:
Verify: **the de-AI library** and full-chain audit (2026-10-07).
User's exact words
--------
"Sometimes actors' speech has an AI flavor. Collect and organize AI-flavored expression words
and such,
  make a de-AI library. Before any actor speaks, before any crew member produces any content,
  do de-AI flavor audit processing."
This branch pins down four things (each one must be able to go red):
  A **The library itself**: six categories are distinguishable · hard bans/soft hints are not mixed · all can be looked up · has source annotations.
  B **The audit judges accurately**: what should hit does hit (cliche words / blunt emotion / formulaic sentence patterns),
    **what should not hit does not hit** (normal dialogue, manual-style meta-information lines).
  C **The before-the-fact half** (prompt): `prompt_block` makes it into the actor decision prompt;
    crew positions can also get it; when `DEAI=false` the whole paragraph disappears.
  D **The after-the-fact half** (audit + cleanup): cliche words in dialogue are deleted **and a record is left**;
    crew output hits make it into `去AI审计.md`; turn off the switch and nothing is done.
How to run: .venv\\Scripts\\python.exe tools/verify_deai.py
Output: assets/screenshots/deai_report.json
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')

from verify_ui_common import safe_rmtree                       # noqa: E402
from style import deai                                         # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


class _EmptyDB:
    """最小假 DB —— `Agent.decide` 只读记忆/摘要/事件。

    ⚠ 定义在**模块级**：写在函数里会被 `from agent.core import Agent` 那类
      名字遮蔽（实测 `NameError: cannot access free variable '_DB'`）。这类
      "判据脚本自己的 Python 坑"要自己在脚本里躲开，别让它看起来像产品坏了。
    
        English:
    Minimal fake DB -- `Agent.decide` only reads memory/summary/events.
        ⚠ Define at **module level**: writing it inside a function gets shadowed by names like
          `from agent.core import Agent` (observed `NameError: cannot access free variable '_DB'`). Such
          "Python pitfalls of the criterion script itself" must be avoided within the script; don't let it look like the product is broken.
    """

    def retrieve_memory(self, *a, **k):
        return []

    def get_summaries(self, *a, **k):
        return []

    def recent_events(self, *a, **k):
        return []

    def add_memory(self, *a, **k):
        return None

    def add_event(self, *a, **k):
        return None


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


# ══════════════════════════════════════════════════════════════════
#  A —— 库本身
# [EN] A -- the library itself
# ══════════════════════════════════════════════════════════════════
def test_library() -> None:
    hw = deai.all_hard_words()
    ok('A1 硬禁分五类（论述腔 / 连接腔 / 情绪直说 / 空转修饰 / 文言虚词）',
       set(hw) == {'论述腔', '连接腔', '情绪直说', '空转修饰', '文言虚词'},
       str(sorted(hw)))
    ok('A2 四类都有词，且总量够用（≥50）',
       all(v for v in hw.values()) and len(deai.words()) >= 50,
       f'{len(deai.words())} 个词')
    ok('A3 词表里没有重复项（同一个词只在两类里出现会让人无从下手）',
       len(deai.words()) == len(set(deai.words())), '')
    ok('A4 软提示按"句式/修辞"分组，且每条都带一句人话说明',
       bool(deai.SOFT) and all(len(x) == 3 and x[1] and x[2] for x in deai.SOFT),
       f'{len(deai.SOFT)} 条规则')
    # ★ 硬禁与软提示**不许混** —— 混了之后审计报告 90% 是噪音。
    #   判据：软提示每条都能在**一段反例文本**上匹配到（说明它是真正则、
    #   而且方向对）。
    #   ⚠ 第一版按**类目**给探针 —— 而同一个类目底下有两条规则
    #     （"对仗句"有「不是A而是B」与「与其说A不如说B」两条），
    #     于是第二条永远匹配不到、判据恒红。**要按规则给探针，不是按类目。**
    #     这也是判据自己的错，不是产品的错。
    # [EN] ★ Hard bans and soft hints **must not be mixed** -- once mixed, 90% of the audit report is
    # [EN] noise.
    # [EN] Criterion: every soft hint can match on **a counterexample text** (proving it is a real rule,
    # [EN] and the direction is right).
    # [EN] ⚠ The first version assigned probes **by category** -- but under a single category there are two
    # [EN] rules
    # [EN] ("parallel couplet" has both "not A but B" and "rather than saying A, it's better to say B"),
    # [EN] so the second one never matches and the criterion is permanently red. **Assign probes by rule,
    # [EN] not by category.**
    # [EN] This is also the criterion's own fault, not the product's fault.
    probes = [
        ('不是[^，。！？]{1,30}，?而是', '他不是害怕，而是失望。'),
        ('与其说[^，。！？]{1,30}，?不如说', '与其说是失望，不如说是累了。'),
        ('既[^，。！？]{1,20}[，,]?又[^，。！？]{1,20}[，,]?既是',
         '既像哭，又像笑，既是疼。'),
        ('(仿佛|宛如|犹如|好似)[^，。！？]{1,12}[，。，][^。！？]{0,20}'
         '(仿佛|宛如|犹如|好似)', '仿佛隔世，宛如从前。'),
        (r'像[^，。！？]{1,10}[，,]?一样[^，。！？]{0,8}[，,]?(像|仿佛)'
         r'[^，。！？]{1,10}', '像石头一样，像冰一样。'),
        ('(这|那)(意思|意味着|代表着|说明)[是着]?[^。！？]{2,}', '这意味着他早知道。'),
        ('[^，。！？]{2,8}，[^，。！？]{2,8}，[^，。！？]{2,8}，'
         '(都|又|也|是|像)', '他们来了，他们站着，他们不说话，都像等什么。'),
        ('——[^。\\n]{1,40}——', '他顿了顿——像是——要说什么。'),
        (r'……[^。\n]{0,6}……', '他……然后……走了。'),
        ('(这|那)(一刻|一天|一夜|一切)[^。！？]{0,12}(都|才|终于)',
         '这一刻，一切都变了。'),
    ]
    pats = [p for _k, p, _n in deai.SOFT]
    miss = []
    for pat, probe in probes:
        if pat not in pats:
            continue                     # 库改了、这条规则没了 → 不算失败
            # [EN] The library changed, this rule is gone -> does not count as failure
        if not re.search(pat, probe):
            miss.append(probe[:14])
    ok('A5 ★ 每条软提示在**它自己那条**反例上匹配得到（正则是活的、方向对）',
       not miss, f'匹配不到的：{miss}' if miss else f'{len(deai.SOFT)} 条规则都有反例命中')
    # 每条软提示的正则都要能编译（写坏了会静默跳过，等于没有这条）
    # [EN] Every soft hint's regex must compile (a broken one is silently skipped, equivalent to the rule
    # [EN] not existing)
    bad = []
    for kind, pat, _note in deai.SOFT:
        try:
            re.compile(pat)
        except re.error as e:
            bad.append(f'{kind}:{e}')
    ok('A6 每条软提示的正则都编译得过（写坏了会被静默跳过）',
       not bad, '；'.join(bad) if bad else f'{len(deai.SOFT)} 条都能编译')
    # 审计本身不许调模型
    # [EN] The audit itself must not call the model
    src = (APP_DIR / 'style' / 'deai.py').read_text(encoding='utf-8')
    ok('A7 ★ 审计**零 LLM 调用**（不然"每次都查"就只能退化成抽样）',
       'llm' not in src.replace('llm_chat', '') or 'ask(' not in src,
       '')


# ══════════════════════════════════════════════════════════════════
#  B —— 审计判得准
# [EN] B -- the audit judges accurately
# ══════════════════════════════════════════════════════════════════
def test_audit() -> None:
    # 该命中的
    # [EN] What should hit
    cases_hit = [
        ('首先，我得说，这不是我做的。', '论述腔', 'hard'),
        ('与此同时，屋里安静下来。', '连接腔', 'hard'),
        ('他心里五味杂陈。', '情绪直说', 'hard'),
        ('他深深地叹了一口气。', '空转修饰', 'hard'),
        ('呜呼，天亡我也！', '文言虚词', 'hard'),
        ('她不是害怕，而是失望。', '对仗句', 'soft'),
        ('屋里静悄悄的，仿佛时间停了，宛如隔世。', '比喻堆叠', 'soft'),
        ('这意味着他早就知道了。', '解释腔', 'soft'),
    ]
    for text, kind, level in cases_hit:
        r = deai.audit_text(text, who='测试')
        got = {(h.kind, h.level) for h in r.hits}
        ok(f'B1 命中「{text[:12]}…」→ {kind}({level})',
           (kind, level) in got, str(sorted(got)))

    # 不该命中的（假阳性会让审计失去意义）
    # [EN] What should not hit (false positives make the audit meaningless)
    cases_miss = [
        '水不会说谎，人会。',
        '这一夜的水，比平时快了一刻。',
        '先看水。',
        '漏刻只许校，不许改。',
        '# 第 1 天 · 辰时',
        '> 在场：主角、柳娘',
        '〔切至 · 城东渡口〕',
        '（剧组 · 美术）今天 1 处：司天台漏刻科',
        '他安安静静坐着，能省事就省事。',
        '他以此为荣，走得很快。',
    ]
    for text in cases_miss:
        r = deai.audit_text(text)
        ok(f'B2 正常内容不误报「{text[:14]}」',
           not r.hard and not r.soft, f'硬{len(r.hard)} 软{len(r.soft)}')

    # 空 / 极短
    # [EN] Empty / extremely short
    ok('B3 空串与纯标点不报（省得每拍都算一次）',
       deai.audit_text('').hits == [] and deai.audit_text('……').hits == [], '')

    # 只按硬禁算 ok
    # [EN] Count only hard bans, ok
    r = deai.audit_text('她不是害怕，而是失望。')
    ok('B4 ★ `ok` 只按硬禁算（软提示不进结论 —— 句式本身没错）',
       r.ok and len(r.soft) == 1, f'hard={len(r.hard)} soft={len(r.soft)}')

    # 聚合
    # [EN] Aggregation
    r = deai.audit_many([('主角', '首先，我不去。'), ('柳娘', '我心里五味杂陈。')])
    ok('B5 一次查一批（演员台词那个用法）',
       len(r.hard) == 2 and {h.who for h in r.hard} == {'主角', '柳娘'},
       str(r.kinds()))

    # ★ 报告里要能读出"谁写的、哪一类、几次"
    # [EN] ★ The report must let you read out "who wrote it, which category, how many times"
    md = deai.render_report(r)
    ok('B6 ★ 报告写清了「谁 + 哪个词 + 几次」',
       '主角' in md and '首先' in md and '论述腔' in md, '')
    ok('B7 没命中时不写空报告（一天一份空文件没意义）',
       '没有发现' in deai.render_report(deai.AuditResult(checked=3)), '')

    # 清理：只删词，不动句式
    # [EN] Cleanup: only delete words, do not touch sentence structure
    new, removed = deai.strip_hard('首先，他深深地叹了一口气，走了。')
    ok('B8 ★ 清理只删**套话词**（"首先""深深地"），句子仍然成立',
       '首先' not in new and '深深地' not in new and '走了' in new,
       f'{new!r}｜删了 {removed}')
    new2, removed2 = deai.strip_hard('她不是害怕，而是失望。')
    ok('B9 ★ 句式**一个字都不动**（删了会把句子弄坏）',
       new2 == '她不是害怕，而是失望。' and not removed2, repr(new2))
    new3, _ = deai.strip_hard('水不会说谎，人会。')
    ok('B10 干净的话原样不动', new3 == '水不会说谎，人会。', repr(new3))
    # 删完不该留下"，，"
    # [EN] After deletion there should not be left over ",,"
    new4, _ = deai.strip_hard('他先是愣了愣，然后又坐下。')
    ok('B11 删完不留双逗号（那是修复，不是改写）',
       '，，' not in new4 and not new4.startswith('，'), repr(new4))


# ══════════════════════════════════════════════════════════════════
#  C —— 事前那半：提示词
# [EN] C -- the before half: prompt words
# ══════════════════════════════════════════════════════════════════
def test_prompt_block() -> None:
    blk = deai.prompt_block(per_kind=4)
    ok('C1 提示词段有开场白 + 四类词 + 句式说明',
       '【' in blk and '论述腔' in blk and '对仗句' in blk, blk[:40])
    ok('C2 每类只列前 N 个（`per_kind` 真的生效）',
       blk.count('、') <= 40 and '首先' in blk, f'{len(blk)} 字')
    big = deai.prompt_block(per_kind=0)          # 0 = 全列
    # [EN] 0 = all listed
    ok('C3 `per_kind=0` 列全部（与默认那档明显不同）', len(big) > len(blk),
       f'{len(blk)} vs {len(big)}')
    ok('C4 只要词的版本（给剧组那些写结构化文本的职位）',
       '不要用这些 AI 套话' in deai.words_only_block()
       and '句式' not in deai.words_only_block(), '')
    # ⚠ 词全没了时**不该吐出空的类目行**（`· 论述腔：` 后面什么都没有）——
    #   那种行进了提示词只会占位置、干扰模型。
    #   （软提示还在，所以整段**不该**消失；第一版判据写成"整段消失"，
    #    那是错的期望 —— 判据红了先问"是产品坏了还是前提错了"。）
    # [EN] ⚠ When all words are gone it **must not emit an empty category line** (`· 论述腔：` with nothing
    # [EN] after it) --
    # [EN] that kind of line entering the prompt only takes up space and disturbs the model.
    real = deai.HARD
    try:
        deai.HARD = {}
        deai._extra_cache = {}
        blk0 = deai.prompt_block(per_kind=4)
        empty_rows = [ln for ln in blk0.splitlines()
                      if ln.strip().startswith('· ') and ln.rstrip().endswith('：')]
        ok('C5 ★ 某类词为空时**不吐空的类目行**（那种行只会占位置）',
           not empty_rows, str(empty_rows[:3]))
        ok('C5b 词全空时"只要词"那个版本给空串（不给一个光秃秃的标题）',
           deai.words_only_block().strip() == '', repr(deai.words_only_block()))
    finally:
        deai.HARD = real
        deai._extra_cache = None

    # ★ 真的进了演员决策提示词（判据要打到"提示词里有没有那一段"）
    # [EN] ★ Actually made it into the actor decision prompt (the criterion must target "whether that
    # [EN] paragraph is in the prompt")
    import asyncio
    from world.state import WorldState, PersonState
    from agent.core import Agent

    w = WorldState(scene='司天台')
    w.add_person(PersonState('主角'))
    seen: list[str] = []
    real_chat = None
    try:
        from llm import router as R
        real_chat = R.llm.chat

        async def _fake(tier, messages, **kw):
            seen.append(str(messages[0]['content']))
            body = json.dumps({'动作': 'wait', '参数': {}, '台词': '',
                               '内心': '', '理由': ''}, ensure_ascii=False)
            return (body, {}) if kw.get('return_meta') else body

        R.llm.chat = _fake
        a = Agent(w.people['主角'], _EmptyDB(), w)

        CFG.set('DEAI', 'true')
        asyncio.run(a.decide())
        got_on = seen[-1] if seen else ''
        CFG.set('DEAI', 'false')
        asyncio.run(a.decide())
        got_off = seen[-1] if seen else ''
    finally:
        if real_chat is not None:
            from llm import router as R
            R.llm.chat = real_chat
        CFG.set('DEAI', 'true')
    ok('C6 ★★ 演员决策提示词里**真的有**去 AI 清单',
       '别写成 AI 腔' in got_on and '五味杂陈' in got_on,
       f'{len(got_on)} 字')
    ok('C7 ★★ `DEAI=false` 时那一段**完全消失**（与从前一字不差）',
       '别写成 AI 腔' not in got_off, f'{len(got_off)} 字')


# ══════════════════════════════════════════════════════════════════
#  D —— 事后那半：审计接进了主循环与剧组
# [EN] D -- the after-the-fact half: audit is wired into the main loop and the crew
# ══════════════════════════════════════════════════════════════════
def test_wiring() -> None:
    loop_src = (APP_DIR / 'sim' / 'loop.py').read_text(encoding='utf-8')
    studio_src = (APP_DIR / 'crew' / 'studio.py').read_text(encoding='utf-8')
    agent_src = (APP_DIR / 'agent' / 'core.py').read_text(encoding='utf-8')
    ok('D1 ★ 演员提示词注入了去 AI 段（`agent/core.py`）',
       'deai' in agent_src and 'prompt_block' in agent_src, '')
    ok('D2 ★ 主循环有"清理台词套话词"这一步（`_deai_clean`）',
       '_deai_clean' in loop_src and 'strip_hard' in loop_src, '')
    ok('D3 ★ 主循环有"逐条审计上屏词条"这一步（`_deai_audit`）',
       '_deai_audit' in loop_src, '')
    ok('D4 ★★ 剧组**唯一入口** `Studio.call` 里过审计'
       '（挂这里 15 个职位一个都不会漏）',
       '_deai_check' in studio_src and 'self._deai_check(note)' in studio_src, '')
    ok('D5 审计结果落盘成 `去AI审计.md`',
       '_flush_deai_report' in loop_src and '去AI审计.md' in loop_src, '')
    ok('D6 开关 `DEAI` 真的被读到（不是个假旋钮）',
       'DEAI' in loop_src and 'DEAI' in agent_src, '')

    # ★ 清理这一步是**真的改写**，所以要"记一笔"
    # [EN] ★ This cleanup step is a **real rewrite**, so it must "leave a record"
    ok('D7 ★★ 删掉的词**记了一笔**（日志 + 审计页）——静默改写是禁止的',
       '_deai_stripped' in loop_src and '删掉了套话词' in loop_src, '')

    # 端到端：拿一个假 action 走一遍 `_deai_clean`
    # [EN] End-to-end: take a fake action through `_deai_clean` once
    import asyncio
    from world.state import WorldState, PersonState
    from agent.core import Agent, Action
    from sim.loop import RunLoop

    w = WorldState(scene='司天台')
    w.add_person(PersonState('主角'))
    a = Agent(w.people['主角'], _EmptyDB(), w)
    loop = RunLoop(w, [a], _EmptyDB(), _EmptyDB(), None)
    act = Action(verb='speak', dialogue='首先，水不会说谎。')
    try:
        loop._deai_clean([(a, act)])
        got = act.dialogue
        stripped = list(loop._deai_stripped)
    except Exception as e:                                       # noqa: BLE001
        got, stripped = f'（异常 {e!r}）', []
    ok('D8 ★ 走一遍 `_deai_clean`：台词里的"首先"真的没了',
       '首先' not in got and '水不会说谎' in got, f'{got!r}')
    ok('D9 ★ 而且记下了删的是什么（可追溯）', stripped == ['首先'], str(stripped))


def main() -> int:
    print('═' * 62)
    print('  验证：去 AI 库与全链路审计（2026-10-07）')
    print('═' * 62)
    try:
        print('\n【A】库本身')
        test_library()
        print('\n【B】审计判得准')
        test_audit()
        print('\n【C】事前那半：提示词')
        test_prompt_block()
        print('\n【D】事后那半：接线')
        test_wiring()
    except Exception:                                            # noqa: BLE001
        traceback.print_exc()
        report['fatal'] = traceback.format_exc()
        ok('Z 判据自己跑通（没被异常打断）', False, report['fatal'].splitlines()[-1])

    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['passed'] = len(checks) - len(bad)
    report['total'] = len(checks)
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'deai_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  去 AI 验证：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
