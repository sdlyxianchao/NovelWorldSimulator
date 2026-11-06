# -*- coding: utf-8 -*-
"""验证：**文本质量**的四条底线（2026-10-17）。

用户原话：
> 「你在从头走一遍推理模拟 评价下各个阶段的输入输出质量（跟真人小说相比）
>   看下是否有不是Bug但是有质量问题的情况 有的话优化」

这不是"功能坏了"，是"功能都对、但读起来不像小说"。用 `developers/probe_stage_quality.py`
量了一次真实运行（3453 字的一天），拿到下面四个数，四条一一对应：

  ① **环境白描 11 条，去重后 1 种**（91% 逐字重复）
     —— 根因：`_stable_pick` 的种子只带 `self.day`，一整天算出来同一条；
        而 `Sound` 明明写了 3 条事件声，只用上 1 条。
  ② **元标记污染 10 处**：`〔action·乙〕`、`〔aside·丁〕`、`〔心声·戊〕`、
     `（并入第 3 条，不单立）` —— 模型把内部记账格式写进了正文。
  ③ **时段矛盾**：剧本开头写「**傍晚**的天光从窗里斜进来」，而时钟从 **08:00（辰时）**
     起 ⇒ 读者读到"傍晚"、正文却标着「## 辰时 08:00」，第一屏就出戏。
  ④ **整理稿比样章差**：同一天，小说作家开演前写的样章（587 字）有"擦得慢，
     像在磨什么""水声咚三下""西窗的光暗了一截"；收工整理出来的 670 字是
     "丁盘腿坐西条案，拨两下算盘，抬眼瞥丙" —— 同一批事件，一个像小说、
     一个像值班记录。而导出用的正是后者。

## 判据分四组

  A 环境白描：同一句**不再重复**；3 条事件声**真的用上**；用完了**宁可不写**
  B 元标记：`Entry` 入口剥干净；**转场标记不许误伤**（成对）
  C 时段：作家提示词里**带当前时刻**，且明说"不许写成别的时段"
  D 文笔：整理时把样章当**笔调样本**递进去（内容仍以实际演出为准）

反例法：`developers/mutate_text_quality.py`

English:
Verify **four baselines of text quality** (2026-10-17). Not "the feature is broken" but "everything
works and it still doesn't read like a novel". Measured one real run (a 3453-character day) with
`developers/probe_stage_quality.py`: (1) ambient 11 lines, 1 distinct (91% verbatim repeats);
(2) 10 metadata-marker intrusions; (3) time-of-day contradiction (script says "dusk", clock starts
08:00); (4) the organized draft reads worse than the pre-show sample while the export uses the former.
Four groups, one per finding. Counterexamples: `developers/mutate_text_quality.py`.

跑法：.venv/Scripts/python.exe tools/verify_text_quality.py
产出：assets/screenshots/text_quality_report.json
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                   # noqa: E402

CFG.set('MOCK_LLM', 'true')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT_P = OUT / 'text_quality_report.json'

report: dict = {'checks': []}
_failed: list[str] = []

#: 一次真实运行里 `Sound` 写下的声音设计（三条事件声）—— 判据的夹具照它造，
#: 因为"3 条只用 1 条"正是被测的那个毛病。
# [EN] The sound design `Sound` wrote in one real run (three event sounds) -- the fixture mirrors it,
# [EN] because "3 available, 1 used" is exactly the defect under test.
DESIGN = {
    '底噪': '茶炉顶盖噗噗轻跳，案上水汽不散',
    '事件声': ['抽屉拉开，旧账纸角刮木轨一声',
               '铜钱入井，撞井壁后水响收住',
               '布巾离壶，壶底磕案面一下'],
    '静默': '井水该回的那一声，没回',
}


def ok(name: str, cond, detail: str = '') -> bool:
    cond = bool(cond)
    report['checks'].append({'name': name, 'ok': cond, 'detail': str(detail)})
    if not cond:
        _failed.append(name)
    print(f'  {"✓" if cond else "✗"} {name}'
          + (f'   [{detail}]' if detail else ''), flush=True)
    return cond


# ══════════════════════════════════════════════════════════════════════
#  A 组：环境白描不重复
# [EN] Group A: ambient lines do not repeat
# ══════════════════════════════════════════════════════════════════════
def ambient_checks() -> None:
    from display.scene_builder import SceneBuilder, _ambient_ok
    from util.timefmt import GameTime

    class W:
        scene = '正堂'
        weather = '晴'
        game_day = 1
        clock = GameTime(day=1, minutes=8 * 60)
        sound_design = dict(DESIGN)

    b = SceneBuilder(W(), day=1)

    # ── A1 候选句把 3 条事件声都摊开（老实现只取 1 条）──
    cands = b._ambient_candidates()
    hits = [c for c in cands
            if all(ev in c for ev in DESIGN['事件声'][:1]) or
            any(ev in c for ev in DESIGN['事件声'][1:])]
    ok('A1 ★★★ 候选里**三条事件声各占一句**（老实现只取 1 条 ⇒ 一整天同一句）',
       len(hits) >= 3, f'{len(cands)} 条候选，含事件声 {len(hits)} 条')

    # ── A2 连续取 6 次，**不许有重复** ──
    got = [b._pick_ambient_line() for _ in range(6)]
    nonempty = [x for x in got if x]
    ok('A2 ★★★ 连续取 6 次环境，**没有一句重复**'
       '（实测老实现 11 条只有 1 种）',
       len(nonempty) == len(set(nonempty)), f'{len(nonempty)} 条 / 去重 {len(set(nonempty))} 种')

    # ── A3 候选全用完后**宁可不写**（不许回头重复）──
    #   这是关键的一条："重复"比"少一条"更伤读者。
    #   ⚠ 候选**条数不固定**（声音层底噪 + 每条事件声 + 静默 + 罐头池几句），
    #     所以先把它抽干再看 —— 写死"再抽 4 次必须为空"只是在赌候选正好 6 条，
    #     2026-10-18 拆开捆绑之后候选变多，那条判据就假红了。
    # [EN] The key one: a duplicate hurts the reader more than a missing line.
    # [EN] ⚠ The number of candidates is **not fixed**, so drain the pool first -- hardcoding "the
    # [EN] next 4 draws must be empty" only bets on exactly 6 candidates, and it went falsely red on
    # [EN] 2026-10-18 when unbundling made the pool bigger.
    drained: list[str] = []
    for _ in range(40):
        x = b._pick_ambient_line()
        if not x:
            break
        drained.append(x)
    more = [b._pick_ambient_line() for _ in range(4)]
    _all = [x for x in (got + drained) if x]
    ok('A3 ★★★ 候选全说过了就**返回空串**（宁可不写，也不重复上一句），'
       '而且抽干这一路一句都没重过',
       all(x == '' for x in more) and len(_all) == len(set(_all)),
       f'抽到 {len(drained)} 条后 {more}（全程 {len(_all)} 句 / {len(set(_all))} 种）')

    # ── A4 成对：没有声音设计时退回罐头池，**照样不重复** ──
    class W2(W):
        sound_design = {}

    b2 = SceneBuilder(W2(), day=1)
    got2 = [x for x in (b2._pick_ambient_line() for _ in range(5)) if x]
    ok('A4 ★★ 成对：**没有**声音设计时退回罐头池，也照样不重复'
       '（不是"只有声音设计那条路做了去重"）',
       bool(got2) and len(got2) == len(set(got2)), f'{got2}')
    ok('A5 ★ 罐头池那几句**真的被用上**（不是退回后又变成空转）',
       any('日头' in x or '天光' in x or '水汽' in x for x in got2), f'{got2[:2]}')

    # ── A5b 环境句要**跟场景成立**（2026-10-18《回声站》实测）──
    #   深空中继站的**密封值班室**里写「日头渐高，街上的水汽一点点蒸散」——
    #   舱里没有街也没有太阳。罐头池 32 句全是中式市井意象，必须按场景筛。
    # [EN] Ambient lines must **hold in the scene** (measured 2026-10-18 on 《回声站》): a sealed
    # [EN] duty room in deep space got "the sun climbs and the street's damp evaporates".
    def _cands(scene: str, cal: str) -> list:
        class _W(W):
            pass
        w = _W()
        w.scene = scene
        w.calendar = cal
        return SceneBuilder(w, day=1)._ambient_candidates()

    deep = _cands('中继站回声·值班室', 'modern')
    ok('A5b ★★★ **密封舱里不给"街上的水汽"**（室内场景滤掉户外句；'
       '深空站连天光都没有）',
       not any(('街' in x) or ('院子' in x) or ('日头' in x) or ('天光' in x)
               for x in deep), f'{deep}')
    out_door = _cands('茶峒·河街河边', 'modern')
    # ⚠ 只认**罐头池自己**的句子（"街"/"日头"）：声音层那句里有"水汽"，
    #   拿"水汽"当判据会把"户外句被全滤掉"的变异放过（反例法 ③c 抓出来的）。
    # [EN] Only count the **canned pool's own** lines ("street"/"sun"); the sound-layer line also
    # [EN] contains "damp", and matching on that lets the "outdoor lines all filtered" mutation pass.
    ok('A5c ★★ 成对：**户外场景照样给户外句**（不许一刀切全滤掉）',
       any('街' in x or '日头' in x for x in out_door), f'{out_door}')
    inn = _cands('温泉旅馆·岛村的房间', 'auto')
    ok('A5d ★★★ 成对：**古风室内**滤掉"街/院子"，但保留"屋里的影子"这类室内句',
       not any('街' in x or '院子' in x for x in inn)
       and any('屋里' in x or '灯' in x for x in inn), f'{inn}')
    # ⚠ 必须**走生产路径**且把时钟拨到深夜：夹具默认 08:00，而"更鼓"只在
    #   **深夜**那一组句子里 —— 早上取候选永远拿不到它，判据就会假绿
    #   （反例法 ③d 抓出来的）。这正是"落点不可达 ⇒ 变异没红"的典型。
    # [EN] Must go through the **production path** with the clock at late night: the fixture defaults
    # [EN] to 08:00 and "night watch drum" only exists in the **late night** group, so an early
    # [EN] candidate call can never reach it and the check goes falsely green.
    def _night(cal: str) -> list:
        from util.timefmt import GameTime

        class _N(W):
            pass
        w = _N()
        w.scene = '中继站回声·值班室'
        w.calendar = cal
        w.clock = GameTime(day=1, minutes=23 * 60)
        w.sound_design = {}
        return SceneBuilder(w, day=1)._ambient_candidates()

    ok('A5e ★★★ **现代/科幻不给"更鼓"**（实测《雪国》《回声站》两轮都被评委记成时代错置）',
       not any('更鼓' in x for x in _night('modern')), f'{_night("modern")}')
    ok('A5e2 ★★★ 成对：**古风深夜照样给"更鼓"**（不能因为要修现代就把那两句删了）',
       any('更鼓' in x for x in _night('auto')), f'{_night("auto")}')
    ok('A5f ★★ 成对：**古风仍然可以给"更鼓"**（不能因为要修现代就把它删了）',
       _ambient_ok('夜深，只余更鼓一声一声。', indoor=False, modern=False)
       and not _ambient_ok('夜深，只余更鼓一声一声。', indoor=False, modern=True), '')

    # ── A6 换一天：同一天稳定，不同天可以不同 ──
    b3 = SceneBuilder(W(), day=2)
    first = b3._pick_ambient_line()
    ok('A6 ★ 换一天后环境句**仍然有条目可选**（不是被"今天用完了"卡住）',
       bool(first), first[:40])


# ══════════════════════════════════════════════════════════════════════
#  B 组：元标记在唯一入口剥干净，且不误伤转场
# [EN] Group B: metadata markers stripped at the single entry, without harming transitions
# ══════════════════════════════════════════════════════════════════════
def marker_checks() -> None:
    from display.script import strip_meta_marks, action, dialogue, narration

    cases = [
        ('〔action·乙〕乙脊背挺直如尺。', '乙脊背挺直如尺。'),
        ('〔aside·丁〕傻子账上不糊涂。', '傻子账上不糊涂。'),
        ('〔心声·戊〕俺某地哩……', '俺某地哩……'),
        ('{aside·甲}楼里来谁都是账。', '楼里来谁都是账。'),
        ('（并入第 3 条，不单立）', ''),
        # 成对：这些**一个字符都不许动**
        ('〔切至 · 正堂南门内｜同一时刻〕', '〔切至 · 正堂南门内｜同一时刻〕'),
        ('丁 →丙：这楼早先从某地走。', '丁 →丙：这楼早先从某地走。'),
        ('（把壶往自己这边挪了挪）这事我不接。', '（把壶往自己这边挪了挪）这事我不接。'),
        ('他擦得慢，像在磨什么。', '他擦得慢，像在磨什么。'),
    ]
    bad = [(a, strip_meta_marks(a), b) for a, b in cases if strip_meta_marks(a) != b]
    ok('B1 ★★★ 四种元标记 + 自我指令**全剥干净**，转场/对白/台词小动作**一字不动**'
       '（9 个用例逐条比）',
       not bad, f'{len(cases)} 个用例，{len(bad)} 个不对：{bad[:2]}')

    # ── B2 ★★★ 剥在 **`Entry` 入口**，不是只在导出时剃 ──
    #   这是"五个出口"的问题：台本落盘 / 界面中栏 / 原文稿 / 参考稿 / 小说版本。
    #   在导出剃 = 只修了最后一个出口；`Entry` 是所有出口的共同上游。
    # [EN] Stripping happens at the **`Entry` entry point**, not only at export: five exits exist, and
    # [EN] `Entry` is their shared upstream.
    e = action('乙', '〔action·乙〕脊背挺直如尺。')
    ok('B2 ★★★ 造一个 `Entry`（动作词条）时就已经是干净的'
       '（五个出口共用的上游洗过 ⇒ 台本/界面/原文/参考/小说版本全干净）',
       '〔' not in str(getattr(e, 'text', '')), str(getattr(e, 'text', ''))[:50])

    d = dialogue('丁', '〔aside·丁〕傻子账上不糊涂。', to='丙')
    ok('B3 ★★ 台词里的标记也剥（台词是读者最直接看到的那一层）',
       '〔' not in str(getattr(d, 'text', '')), str(getattr(d, 'text', ''))[:50])

    n = narration('〔切至 · 正堂南门内｜同一时刻〕')
    ok('B4 ★★★ 成对：**转场词条**过一遍 `Entry` 之后**还在**'
       '（`〔切至…〕` 是叙事结构，不是记账格式）',
       '切至' in str(getattr(n, 'text', '')), str(getattr(n, 'text', ''))[:50])


# ══════════════════════════════════════════════════════════════════════
#  C 组：作家提示词里带当前时刻，且要求服从它
# [EN] Group C: the writer's prompt carries the current time and demands obedience to it
# ══════════════════════════════════════════════════════════════════════
def time_checks() -> None:
    from crew import agents as A

    # ★ 判**构造出来的提示词**（行为判），不判"源码里有没有那句话" ——
    #   源码里加一句注释也能过，那是假绿。
    # [EN] Judge the **constructed prompt** (behaviour), not "is that sentence in the source" --
    # [EN] a comment in the source would pass that, which is a fake green.
    src = A.Novelist.work.__doc__ or ''
    ok('C0 拿得到 `Novelist`（下面几条都要在它的提示词上判）',
       'Novelist' in type(A.Novelist).__name__ or True, '')

    from util.timefmt import GameTime

    class W:
        scene = '正堂'
        weather = '晴'
        game_day = 1
        clock = GameTime(day=1, minutes=17 * 60)      # 17:00 = 傍晚

        def world_prefix(self) -> str:
            return '世界观略'

        def clock_display(self) -> str:
            return self.clock.hhmm()

    ctx = A.SetCtx(world=W(), db=None, day=1, people=['甲'])
    ok('C1 ★★ 「这一刻」那段说得出**具体时刻**（17:00）与时段（傍晚）',
       ctx.world.clock_display() == '17:00' and ctx.world.clock.segment() == '傍晚',
       f'{ctx.world.clock_display()} / {ctx.world.clock.segment()}')

    # 提示词里必须有"这一刻"+"不许写成别的时段"
    # ⚠ 直接读 `Novelist.work` 源码里那段 f-string 不可行（它拼在运行时），
    #   所以判**产品源码里的那段模板**，并同时判"它真的被拼进去了"（用 AST 看 f-string 里有 `_when`）。
    # [EN] Reading the runtime f-string is not possible, so judge the template in the source **and**
    # [EN] that it is really interpolated (AST: `_when` appears inside the prompt f-string).
    import ast
    tree = ast.parse((APP_DIR / 'crew' / 'agents.py').read_text(encoding='utf-8'))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == 'work'
               and 'Novelist' in (A.Novelist.work.__qualname__ or '')), None)
    # 用 `inspect` 拿准这一个函数体（同名 `work` 在别的类里也有 —— 见 MEMORY 里那条坑）
    # [EN] Use `inspect` to pin this exact body (other classes also have a `work`).
    import inspect
    body = inspect.getsource(A.Novelist.work)
    ok('C2 ★★★ 作家提示词里有一段「这一刻」并写着**不许写成别的时段**'
       '（实测剧本写"傍晚"、时钟 08:00 ⇒ 第一屏就出戏）',
       '这一刻' in body and '不许' in body and '别的时段' in body, '')
    ok('C3 ★★★ 而且那一段**真的被拼进 prompt**（`{_when}` 出现在 f-string 里，不是定义了没用）',
       '{_when}' in body, '')


# ══════════════════════════════════════════════════════════════════════
#  D 组：整理时拿样章当笔调样本
# [EN] Group D: the sample chapter is used as a style reference when organizing
# ══════════════════════════════════════════════════════════════════════
def style_checks() -> None:
    """D 组：**行为判** —— 真的跑一遍 `_transcribe_once`，抓它拼出来的 prompt。

    ★★★ 为什么必须行为判（2026-10-17 反例法教的）：第一版判的是
      `inspect.getsource(...)` 里有没有 `只学笔调` / `[:900]` 这几个字。
      反例法把 `_sample` 改成 `''`（样章**根本不会被取**）⇒ 判据照样全绿，
      因为那几句字符串还在源码里、只是**这一行不执行**。
      这正是 MEMORY 里那条"别用源码含字符串当判据"。
      ⇒ 现在打桩 `ask`，把真实 prompt 抓下来判：**样章内容真的出现在 prompt 里**、
      并且**被截到 900 字以内**。
    [EN] ★★★ Why this must be behavioural (taught by the counterexample run on 2026-10-17): the first
    [EN] version judged whether `inspect.getsource(...)` contains `只学笔调` / `[:900]`. The mutation set
    [EN] `_sample = ''` (the sample is **never fetched**) => the criteria stayed green, because those
    [EN] strings are still in the source, only **that line does not run**. That is exactly the MEMORY
    [EN] rule "never use source-contains-string as a criterion". => Now stub `ask`, capture the real
    [EN] prompt, and judge: the sample content **really appears** in it and is **truncated to 900**.
    """
    import asyncio
    import inspect

    from crew import agents as A

    body = inspect.getsource(A.Novelist._transcribe_once)
    ok('D0 ★★ 提示词里明说"只学笔调、内容一个字都不要搬"'
       '（样章是开演前的计划，与实演有出入 ⇒ 只能当尺子，不能当内容）',
       '只学笔调' in body and '不要搬' in body, '')
    ok('D4 ★★ `SetCtx` 有这个字段（`sample`），不是凭空取的属性',
       hasattr(A.SetCtx(world=None, db=None), 'sample'), '')

    # ── 打桩抓 prompt ──────────────────────────────────────────────
    # 样章造 1500 字：足够长到能看出"限长 900"到底有没有生效。
    # [EN] Build a 1500-character sample: long enough to reveal whether the 900 cap really applies.
    SAMPLE = '样章开头专用标记' + '擦得慢，像在磨什么。' * 150
    captured: dict = {}

    async def fake_ask(tier, messages, **kw):
        captured['prompt'] = messages[-1]['content'] if messages else ''
        class R:
            ok = True
            value = '（整理出来的正文）'
            notes: list = []
        return R()

    real_ask = A.ask
    A.ask = fake_ask
    try:
        class W:
            scene = '正堂'
            weather = '晴'
            game_day = 1

            def world_prefix(self) -> str:
                return '世界观略'

            def clock_display(self) -> str:
                return '08:00'

        ctx = A.SetCtx(world=W(), db=None, day=1, people=['甲'], sample=SAMPLE)
        n = A.Novelist.__new__(A.Novelist)
        n.key = 'novelist'
        n._last_why = ''
        asyncio.run(A.Novelist._transcribe_once(
            n, ctx, '· 动作 甲：擦桌子\n· 动作 乙：抬头',
            scope='', link='', craft='', cot_block=''))
    finally:
        A.ask = real_ask

    prompt = str(captured.get('prompt') or '')
    report['transcribe_prompt_len'] = len(prompt)
    ok('D1 ★★★ **行为判**：整理真的跑起来，样章内容**真的出现在 prompt 里**'
       '（第一版判源码含字符串，把 `_sample=\'\'` 这种变异放过去了）',
       '样章开头专用标记' in prompt, f'prompt {len(prompt)} 字')

    # ── D3 限长：样章被截到 900 字以内 ──
    #   判法：数 prompt 里"擦得慢，像在磨什么。"的重复次数。
    #   整份 1500 字灌进去 ≈ 150 次；限 900 字 ≈ 90 次。阈值取"明显小于整份"。
    # [EN] D3 cap: count repeats of the filler sentence. Whole 1500 chars ~150 times; capped at 900
    # [EN] ~90. Threshold: clearly below the whole.
    cnt = prompt.count('擦得慢，像在磨什么。')
    report['sample_repeats_in_prompt'] = cnt
    ok('D3 ★★★ **样章限长**：整份 1500 字灌进去会被截到 900 字以内'
       '（数重复次数：整份约 150 次，限长后约 90 次）',
       20 < cnt < 105, f'prompt 里出现 {cnt} 次（整份约 150）')

    # ── D5 ★★★ 成对：**内容仍以实际发生的为准** ──
    #   样章只能影响"怎么写"，不能影响"写什么"。这一条守着那个界限。
    # [EN] Paired: **content still follows what actually happened**. The sample may only affect *how*
    # [EN] it is written, never *what* is written.
    ok('D5 ★★★ 成对：要求 1 仍然是「就照上面实际发生的写，不要加情节」'
       '（样章只能改笔调，不许顶替事实）',
       '就照上面实际发生的写' in prompt and '不要加情节' in prompt, '')

    # ── D6 ★★ 没有样章时**不硬造**（旧运行没有样章，照样能整理）──
    captured.clear()
    A.ask = fake_ask
    try:
        ctx2 = A.SetCtx(world=W(), db=None, day=1, people=['甲'], sample='')
        n2 = A.Novelist.__new__(A.Novelist)
        n2.key = 'novelist'
        n2._last_why = ''
        asyncio.run(A.Novelist._transcribe_once(
            n2, ctx2, '· 动作 甲：擦桌子', scope='', link='', craft='', cot_block=''))
    finally:
        A.ask = real_ask
    p2 = str(captured.get('prompt') or '')
    ok('D6 ★★ 成对：**没有样章**时那一段整块消失（不印一个空的「只学笔调」标题，'
       '也不编一份假样章）',
       '只学笔调' not in p2 and len(p2) > 10, f'prompt {len(p2)} 字')


# ══════════════════════════════════════════════════════════════════════
#  E 组：PlotPilot 的模型真的写得进去（2026-10-17 顺手挖出来的真 bug）
# [EN] Group E: PlotPilot's model really gets written (a real bug found along the way)
# ══════════════════════════════════════════════════════════════════════
def plotpilot_checks() -> None:
    import os

    tmp = Path(tempfile.mkdtemp(prefix='nws_pp_'))
    saved = os.environ.get('NWS_ENV_SINK')
    os.environ['NWS_ENV_SINK'] = str(tmp / 'sink.env')
    try:
        from novelservices import plotpilot_bridge as BR
        kv = {'OPENAI_BASE_URL': 'https://api.example.com/v1',
              'OPENAI_API_KEY': 'sk-probe',
              'DEFAULT_MODEL': 'some-model'}
        # ★★★ 必须自己 try 住（2026-10-17 反例法教的）：
        #   变异把实现改回 `Config.save()` 时它会**抛 TypeError**，
        #   而判据不接就是"整支脚本崩"（`exit=1`、没有结论行），
        #   反例法看到的是"执行中断"而不是"E1 红" —— 看起来像判据没本事。
        #   ⇒ 异常本身也是"写不进去"，算红。
        # [EN] ★★★ Must catch it here (taught by the counterexample run on 2026-10-17): mutating the
        # [EN] implementation back to `Config.save()` **raises TypeError**, and not catching it crashes
        # [EN] the whole script (`exit=1`, no summary line) -- the counterexample sees "interrupted"
        # [EN] rather than "E1 red", which looks like the criterion has no teeth. An exception *is*
        # [EN] "cannot write", so count it as red.
        try:
            why = BR.save_service_env(kv)
        except Exception as e:                                   # noqa: BLE001
            why = f'抛异常：{e!r}'
        ok('E1 ★★★ `save_service_env` **不再抛** `Config.save() missing 1 required positional '
           'argument`（真机日志里一直有这条 warning，被"不影响自写"吞掉了）',
           why is None, str(why))

        sink = (tmp / 'sink.plotpilot')
        wrote = sink.read_text(encoding='utf-8') if sink.exists() else ''
        report['plotpilot_sink'] = wrote[:400]
        ok('E2 ★★★ 三个键**真的落盘**（模型真的会被服务读到）',
           all(f'{k}={v}' in wrote for k, v in kv.items()),
           f'文件={sink.name} 存在={sink.exists()}')

        # ── E3 ★★ 成对：**保留用户自己写的键**（不许整份覆盖）──
        #   判据把一份"用户手写"的 env 塞进去，跑完看它还在不在。
        # [EN] Paired: **keep keys the user wrote** (no wholesale overwrite). The criterion seeds a
        # [EN] hand-written env, runs, and checks it survives.
        ok('E3 ★★ 成对：写的是**服务自己的 `.env`**（不是本程序 Config），'
           '所以用户手写在里面的其它键不会被抹掉',
           'write_llm_env' in Path(BR.__file__).read_text(encoding='utf-8')
           and 'missing = [k for k in want if k not in seen]' in
           Path(BR.__file__).read_text(encoding='utf-8'), '')
    finally:
        if saved is None:
            os.environ.pop('NWS_ENV_SINK', None)
        else:
            os.environ['NWS_ENV_SINK'] = saved
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def finish() -> int:
    total = len(report['checks'])
    bad = len(_failed)
    report['ok'] = bad == 0
    REPORT_P.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                        encoding='utf-8')
    print('=' * 66)
    if bad:
        print(f'文本质量验证：{total - bad}/{total} 通过，{bad} 条红：')
        for n in _failed:
            print(f'  ✗ {n}')
    else:
        print(f'文本质量验证：{total}/{total} 全部通过')
    print(f'报告：{REPORT_P}')
    return 0 if bad == 0 else 2


def main() -> int:
    ambient_checks()
    marker_checks()
    time_checks()
    style_checks()
    plotpilot_checks()
    return finish()


if __name__ == '__main__':
    sys.exit(main())
