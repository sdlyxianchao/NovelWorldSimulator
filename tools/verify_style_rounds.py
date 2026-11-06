# -*- coding: utf-8 -*-
"""验证：**整理稿的 Reflexion 只对"实病"多跑轮，文风类只改第一轮**（2026-10-25）。

为什么要有这一条
----------------
用户问「小说作家 2800 多秒还没结束时什么原因」。前面已经查明：
`novelize` 那 49 分钟里有 **93 次模型调用、2960.9 秒、$2.52**，其中

    crew_day_novel  68 次 / 2330.5 秒（78.7%）
    prose_flow_fix  24 次 / 617.0 秒
    crew_review      1 次 /  13.4 秒

而 68 次 `crew_day_novel` 里，**18 次是"写这一段"，剩下 50 次是 Reflexion 在整段重写**。
拿日志看那 50 次是被什么触发的：22:32→22:39 反复出现的是
「细节复读『墙那张』」「台词口癖『签筒不离柜』」「憋气」「太挤」——
**全是文风类**。

而本项目自己的规则写着（见 `MEMORY.md`「推演文本质量」）：
    检测器的输出是"候选"不是"判决"：**文风类（重复/道具循环/憋气）不触发退回**，
    只有实病（元叙述/拥挤/自洽/悬空/篇幅）才触发。

规则在那儿，这条路径却没照做。判据很硬：文风类删掉之后读者**不损失任何东西**
（真人比模型重复更多，`samples/zh` 实测），为它一轮轮重写整段，改的是自己刚写出来的东西
——日志里"太挤"的件数 12 → 21 → **37**（上限 7），越改越挤。

改法（只改"要不要再跑一轮"，不改"第一轮改不改"）
------------------------------------------------
· `repair_recipes.Recipe` 加一条轴 `nature`：`defect`（实病）/ `style`（文风）。
· `reflexion.reflect(style_rounds=…)`：第 `style_rounds` 轮之后，`style` 那几步不再跑。
· `Novelist._transcribe_once` 传 `style_rounds=1`（整理稿这条最贵的路）。
  ⚠ 别的路（导出关口 `prose_checkup`）**不传** ⇒ 仍是 0 = 老行为，一个字都不变。

判据分组（一条判据守一道闸）
--------------------------
  A **登记**：每一步都标了 nature；两个集合都是**闭集**（多一个少一个都报）
  B **行为**：文风步只跑 N 轮，实病步不受影响；停下时说得清是哪一半没改
  C **接线**：整理稿这条路真的传了 1，且这个值真的到了 `reflect`

跑法：.venv\\Scripts\\python.exe tools/verify_style_rounds.py
产出：assets/screenshots/style_rounds_report.json

English:
Verify that **the organizer's Reflexion only keeps re-running for real defects; style classes
get round 1 only**. The user asked why the novelist ran 2800+ seconds. The 49-minute window
held 93 calls / 2960.9 s / $2.52; of the 68 `crew_day_novel` calls, 18 wrote a chunk and **50
were Reflexion rewriting one** -- triggered mostly by repetition / catchphrase / breathless /
crowding, i.e. **style** classes. This project's own rule says style classes must not trigger a
rewrite. Chasing them round after round rewrites the model's own output: the crowding count went
12 -> 21 -> **37** against a limit of 7. Fix: a `nature` axis on each recipe, a `style_rounds`
cap in `reflect`, and `style_rounds=1` only on the organizer path (the export path keeps the old
behaviour). Groups: A registration is a closed set / B behaviour / C the value really reaches
`reflect`.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from crew import prose_flow as PF                            # noqa: E402
from crew import reflexion as RX                             # noqa: E402
from crew import repair_recipes as REC                       # noqa: E402
from crew import verdict as V                                # noqa: E402
from crew.agents import Novelist                             # noqa: E402

OUT = APP / 'assets' / 'screenshots'
REPORT = OUT / 'style_rounds_report.json'
_rows: list[dict] = []


def ok(name: str, cond, detail='') -> bool:
    _rows.append({'判据': name, '通过': bool(cond), '实测': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''))
    return bool(cond)


# ── A 登记 ──────────────────────────────────────────────────────
def a_registry():
    print('\n【A】登记')
    rows = REC.ordered()
    natures = {r.nature for r in rows}
    ok('A1 ★★★ 每一步都标了 nature，且只有 defect / style 两个值'
       '（第三个数出现 = 有人塞了个没人认的类别，跳过规则会静默失效）',
       natures <= {'defect', 'style'} and all(r.nature for r in rows),
       f'{sorted(natures)} × {len(rows)} 步')

    # ⚠ 闭集：不是"包含"而是"恰好是"。少标一个 ⇒ 它被当成实病、继续烧钱；
    #   多标一个 ⇒ 实病被当成文风、永远改不完。两头都得报。
    # ⚠ 而且必须按**步骤**数，不能只比 label 集合（反例法抓到的真问题）：
    #   「重复」有**两步**（order 10 治"话在打转"、31 治"同一件事反复说"），
    #   只把其中一步的 nature 去掉，label 集合还是那三个 ⇒ 集合比的写法照样绿，
    #   而实际有一个步骤在继续烧钱。改成比**排好序的步骤 label 列表**。
    # [EN] ⚠ Count **steps**, not the label set (a real hole the counterexample method found):
    # [EN] "重复" has **two** steps (order 10 for conversational spin, 31 for repeating one thing);
    # [EN] dropping `nature` from just one leaves the label set unchanged, so a set comparison stays
    # [EN] green while one step keeps burning money.
    # ★★ 2026-10-28：多了一步「对话标签」（确定性删副词，`_fix_dialogue_tags`）。
    #   为什么它算**文风类**而不是实病：删掉"严肃地"这三个字，读者**不损失任何东西**
    #   （谁在说、说了什么、什么语气，都由台词与动作自己承担）—— 这正是本文档
    #   开头那条定义。为什么它算**一步**：它是 `strip`，第一轮跑一次就够（幂等），
    #   不该为它多烧一轮整段重写。
    #   ⚠ 所以这里是"恰好**五**步"，不是"四步里再加一个" —— 数的是**步骤**，
    #     「重复」仍占两格（10 治话在打转、31 治同一件事反复说）。
    # [EN] ★★ 2026-10-28: one more step, 「对话标签」 (deterministic adverb strip).
    # [EN] It is **style**, not a defect: deleting "sternly" costs the reader nothing.
    # [EN] It is **one step**: a `strip`, idempotent, so one round is enough.
    # ⚠ 顺序按 `sorted()` 的 Unicode 码点排（「套」U+5957 在「对」U+5BF9 前面），
    #   不是按笔画、也不是按想当然 —— 手写错顺序会红得很莫名。
    want_style = ['套话', '对话标签', '平铺段', '道具循环', '重复', '重复']
    want_defect = ['元叙述', '感知自洽', '拥挤段', '问答悬空']
    got_style = sorted(r.label for r in rows if r.nature == 'style')
    got_defect = sorted(r.label for r in rows if r.nature == 'defect')
    ok('A2 ★★★ 文风类**恰好六步**「重复×2 / 道具循环 / 平铺段 / 对话标签 / 套话」'
       '（少一步 ⇒ 它继续烧钱，多一步 ⇒ 真该改的改不完）',
       got_style == want_style, f'{got_style}')
    ok('A3 ★★★ 实病**恰好四步**「元叙述 / 感知自洽 / 问答悬空 / 拥挤段」',
       got_defect == want_defect, f'{got_defect}')

    labs = REC.style_labels()
    ok('A4 ★★★ `style_labels()` 按**步骤的 label** 返回（不是 `all_labels()`）：'
       '「憋气段」是「平铺段」那一步**顺带**治的，不是独立步骤 —— '
       '把它也算进去就会变成"有一个步骤叫憋气段"，跳过规则那时按谁跳就说不清了',
       labs == set(want_style) and '憋气段' not in labs, f'{sorted(labs)}')

    keys = list(PF.prose_issue_count('岛村倚窗。驹子坐在火钵旁，说了句「知道了」。').keys())
    ok('A5 ★★★ 登记表与计数表的**名字仍然对得上**（数得出来的都有人负责、'
       '登记的都能数出来）—— 两边一漂，"治了没有"就永远判不出来',
       not REC.uncovered(keys) and not REC.extra(keys),
       f'没人负责={REC.uncovered(keys)} 数不出={REC.extra(keys)}')

    # 「憋气段」只由「平铺段」顺带治 ⇒ 封顶平铺段就等于封顶憋气。
    # 这不是副作用，是**设计**：憋气（长句过半）也是文风类。写出来免得以后有人
    # 以为是漏了。
    cover = [r for r in rows if '憋气段' in r.covers]
    ok('A6 ★★★ 「憋气段」只由「平铺段」顺带治 ⇒ 封顶它**同时**封顶憋气，'
       '这是有意的（憋气也是文风类，不是实病）',
       len(cover) == 1 and cover[0].label == '平铺段' and cover[0].nature == 'style',
       f'{[(r.label, r.nature) for r in cover]}')


# ── B 行为（假步骤，零 LLM）────────────────────────────────────
class _FakeScore:
    """计数固定的一份"分"。用它把 `V.Score.of` 换掉，就不用造出一段恰好长那样的中文。

    ⚠ 计数固定不动的副作用：`_regressed` 恒空、`weighted` 恒等 ⇒ 走到 `flat` 那一步。
      所以下面把 `patience` 设成 99，并且把 `_should_skip` 打空 ——
      这一组要量的是**新的那道闸**，不是 stalled / regressed（那两条另有一组判据）。
    """
    zh = 500
    speeches = 5
    sentences = 20

    def __init__(self, counts=None):
        self.counts = dict(counts or {'重复': 1, '道具循环': 1, '拥挤段': 1, '元叙述': 1})

    @property
    def total(self) -> int:
        return sum(int(v or 0) for v in self.counts.values())

    @property
    def weighted(self) -> float:
        return round(sum(V.RUBRIC.get(k, 1.0) * int(v or 0)
                         for k, v in self.counts.items()), 3)

    @classmethod
    def of(cls, text):
        return cls()


def _run_rounds(style_rounds: int, trials: int = 4) -> dict:
    """真跑 `RX.reflect`，只数"每一步被叫了几次"。"""
    calls: dict[str, int] = {}

    def _mk(label):
        async def _step(text):
            calls[label] = calls.get(label, 0) + 1
            return text + f'（{label}改）'
        return _step

    steps = [(_mk('重复'), '重复', 1), (_mk('道具循环'), '道具循环', 1),
             (_mk('平铺段'), '平铺段', 1), (_mk('拥挤段'), '拥挤段', 1),
             (_mk('元叙述'), '元叙述', 1)]

    old_score, old_skip = V.Score, RX._should_skip
    V.Score = _FakeScore
    RX._should_skip = lambda *a, **k: ''            # 这道闸另有判据（E 组）
    try:
        RX.reflect and asyncio.run(RX.reflect(
            '原文', steps, trials=trials, patience=99,
            style_rounds=style_rounds, style_labels=REC.style_labels()))
    finally:
        V.Score = old_score
        RX._should_skip = old_skip
    return calls


def b_behavior():
    print('\n【B】行为')
    old = _run_rounds(0)
    ok('B1 ★★★ `style_rounds=0`（老行为、也是导出关口的取值）⇒ 文风步**每轮都跑**：'
       '「0 = 不限」这句是真的，不是"顺手也封个顶"',
       old.get('重复') == 4 and old.get('平铺段') == 4, f'{old}')

    new = _run_rounds(1)
    ok('B2 ★★★ `style_rounds=1` ⇒ 文风步**只跑 1 次**（这就是省下来的那 50 次整段重写）',
       new.get('重复') == 1 and new.get('道具循环') == 1 and new.get('平铺段') == 1,
       f'{new}')
    ok('B3 ★★★ **实病一步都没少**（拥挤/元叙述照旧跑满 4 轮）—— '
       '封顶的是文风类，不是"复查轮数"，这两件事混在一起就成了"整体降质量"',
       new.get('拥挤段') == 4 and new.get('元叙述') == 4, f'{new}')
    ok('B4 ★★★ 成对：同一次运行里，文风步少了 3 轮而实病步一轮没少 —— '
       '只判"文风步变少了"会被"整体轮数降成 1"骗过（那样实病也少跑）',
       new.get('重复') == 1 and new.get('拥挤段') == 4 > new.get('重复'),
       f'文风={new.get("重复")} 实病={new.get("拥挤段")}')

    # 停下理由：只剩文风类不干净时，必须说清是"按规则不再多跑"，
    # 而不是"所有步骤都被跳过"（后者读起来像出了故障）。
    txt = _stop_reason(1)
    ok('B5 ★★★ 停下来的理由是「实病这边没有还能改的步了（文风类只改第 1 轮…）」，'
       '不是"所有步骤都被跳过"——后者读起来像故障，而这是设计',
       '文风类只改第 1 轮' in txt, f'{txt}')

    txt0 = _stop_reason(0)
    ok('B6 ★★ 成对：`style_rounds=0` 时**不给这句新理由**（老路径的话要一字不变，'
       '否则日志比对全乱）', '文风类只改第' not in txt0, f'{txt0}')


def _stop_reason(style_rounds: int) -> str:
    """只让**实病**那几步被 stalled 挡住 ⇒ 第 2 轮必然 ran==0，量停下理由。"""
    async def _step(text):
        return text + '改'

    steps = [(_step, '重复', 1), (_step, '拥挤段', 1)]
    old_score = V.Score
    V.Score = _FakeScore
    try:
        res = asyncio.run(RX.reflect(
            '原文', steps, trials=4, patience=99,
            style_rounds=style_rounds,
            style_labels=REC.style_labels()))
        return str(res.stop or '')
    finally:
        V.Score = old_score


# ── C 接线 ──────────────────────────────────────────────────────
def c_wiring():
    print('\n【C】接线')
    seen: list[dict] = []

    async def _reflect(text, steps, **kw):
        seen.append(dict(kw))
        return RX.Result(text=text)

    # ⚠ 必须让"开跑前就没有可数的毛病"那条早退**不成立**，否则 `reflect` 根本不会被调用，
    #   `seen` 是空的 ⇒ 判据拿 None 去比，红得莫名其妙（第一版就栽在这儿）。
    #   用真文本造不出恰好有病的一段，所以直接把这一个函数打桩。
    # [EN] The "nothing countable, return immediately" early exit must be disabled, otherwise
    # [EN] `reflect` is never called and `seen` stays empty (the first version failed this way).
    _old_total = PF.issue_total
    PF.issue_total = lambda *_a, **_k: 1
    old = RX.reflect
    RX.reflect = _reflect
    try:
        obj = Novelist.__new__(Novelist)
        asyncio.run(obj._checkup_reflexion('岛村倚窗。驹子坐在火钵旁。', rounds=2,
                                          tag='整理稿', style_rounds=1))
    finally:
        RX.reflect = old
        PF.issue_total = _old_total

    got = seen[0] if seen else {}
    ok('C1 ★★★ `_checkup_reflexion` 真的把 `style_rounds` **和** `style_labels` '
       '一起递给了 `reflect`（只传一个 ⇒ 上限在，但没人知道哪些算文风 ⇒ 等于没接）',
       got.get('style_rounds') == 1 and set(got.get('style_labels') or ()) == REC.style_labels(),
       f'style_rounds={got.get("style_rounds")} '
       f'labels={sorted(got.get("style_labels") or ())}')

    seen2: list[dict] = []

    # ⚠ 挂到类上之后它就成了**未绑定函数**，第一个位置参数是 self ——
    #   签名少写 self 会报"takes 1 positional argument but 2 were given"。
    async def _reflex2(self, text, **kw):
        seen2.append(dict(kw))
        return text

    old_reflex = Novelist._checkup_reflexion
    Novelist._checkup_reflexion = _reflex2
    try:
        obj2 = Novelist.__new__(Novelist)
        asyncio.run(obj2._checkup('岛村倚窗。', rounds=1, tag='整理稿', style_rounds=3))
    finally:
        Novelist._checkup_reflexion = old_reflex

    ok('C2 ★★★ `_checkup` 到 `_checkup_reflexion` 这一层没把值吃掉'
       '（中间层漏传是最难发现的：上面传了、下面收不到，日志看着一切正常）',
       (seen2[0].get('style_rounds') if seen2 else None) == 3,
       f'{seen2[0] if seen2 else {}}')

    src = (APP / 'crew' / 'agents.py').read_text(encoding='utf-8')
    ok('C3 ★★★ 整理稿这条路**传的是 1**（这就是这次要省的那笔钱）',
       "self._checkup(prose, tag='整理稿', style_rounds=1)" in src, '')

    # ⚠ 成对：别的路一律不许传。若哪天有人"顺手"给导出关口也传 1，
    #   成书的文风质量会静默下降，而没有任何地方会报错。
    extra = [ln.strip() for ln in src.splitlines()
             if '_checkup(' in ln and 'style_rounds' in ln
             and "tag='整理稿'" not in ln]
    ok('C4 ★★★ 而且**只有整理稿这条路**传了它 —— 导出关口/正文/样章仍是 0（老行为）：'
       '顺手给成书那条路也封顶，文风质量会静默下降，而没有任何地方会报错',
       not extra, f'{extra}')

    ok('C5 ★★ 默认值就是 0（`_checkup` / `_checkup_reflexion` / `reflect` 三处）—— '
       '"不传 = 不限"必须三处一致，缺一处就成了"某个调用点悄悄被封顶"',
       all(('style_rounds: int = 0' in src)
           for _ in [0]) and src.count('style_rounds: int = 0') >= 2
       and 'style_rounds: int = 0,' in (APP / 'crew' / 'reflexion.py').read_text(encoding='utf-8'),
       f'agents.py 里 {src.count("style_rounds: int = 0")} 处')


def main() -> int:
    print('═' * 62)
    print('  整理稿只对实病多跑轮（文风类只改第一轮，2026-10-25）')
    print('═' * 62)
    for fn in (a_registry, b_behavior, c_wiring):
        try:
            fn()
        except Exception as e:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            ok(f'{fn.__name__} 整组没跑完：{e!r}', False, '')

    bad = [r for r in _rows if not r['通过']]
    print('\n' + '─' * 62)
    print(f'  文风类只改一轮验证：{len(_rows) - len(bad)}/{len(_rows)}'
          + ('   ← 有失败' if bad else ''))
    for r in bad:
        print(f'    ! {r["判据"]}  [{r["实测"]}]')
    print('─' * 62)
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(_rows, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
