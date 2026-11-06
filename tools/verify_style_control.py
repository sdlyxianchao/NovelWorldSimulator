# -*- coding: utf-8 -*-
"""验证：**风格控制**（`util/style_kit.py`）—— 那七个旋钮**不再是死的**。

用户 2026-10-27
--------------
「我看过很多小说 我觉得比较好的 比如民调局异闻录 饕餮娘子 神鬼食堂 ……」

那一轮做完之后发现一件事：界面上的「虐心 / 幽默 / 爽点 / 感情 / 悬念 /
世界观 / 智商 / 节奏」八个旋钮，**读进 `WorldState` 之后没有任何消费者** ——
它们只影响界面上那行"幽默度 30%"的摘要，**推演一模一样**。
⇒ 这就是"死旋钮"：**作者怎么调，稿子不变**。

这一组判据要证明三件事（每条都要能红）：

  A **旋钮不是死的**：每一个旋钮**动了就发声**，而且**低档与高档说的话不一样**。
    （死旋钮的判据就是"怎么调输出都一样" ⇒ 必须比对**两端**。）
  B **话是可执行的**：每一句都**能数、能查**，不许是"更虐一点"这种形容词；
    幽默那一项走**六步链**（支点→小谎→反噬→揭穿→嘴硬→回收），
    范例一律用 `[方括号]` 占位（**提示词里的例子会被当素材抄**）。
  C **两处默认值不许漂**：`util/style_kit.py::DEFAULTS` ↔ `config.py::SPEC`，
    `style_kit.CFG_KEYS` ↔ `sim/setup.py::_STYLE_FIELDS`，
    `config.py::SPEC` ↔ `world/state.py` 的字段默认值。
    （⚠ 这条是**文档漂移闸**：`style_kit.py` 的注释白纸黑字写着
     "判据 `verify_style_control.py` 会核对这两处" —— 而那个脚本**当时并不存在**。）
  D **真的接进提示词了**：`SetCtx.style_block()` 在开关打开时非空、
    关掉时**一个字都不发**、旋钮动了输出**跟着变**；
    `crew/agents.py` 里三处接（作家提示词 / MuMuAINovel 那条细纲 / 导出那一路）
    每处的"── 风格控制"标题**旁边**必须真的调了 `style_block()` 或 `from_config()`。

用法：.venv\\Scripts\\python.exe tools/verify_style_control.py
产出：assets/screenshots/style_control_report.json

English:
Verification: **style control** (`util/style_kit.py`) -- those seven knobs **are no longer dead**.
User 2026-10-27: "I have read a lot of novels... 民调局异闻录, 饕餮娘子, 神鬼食堂 ..."
After that round it turned out that the eight knobs on the screen were read into `WorldState`
and then **nothing consumed them** -- they only affected the "humor 30%" summary line in the UI,
**the derivation was unchanged**. That is a "dead knob": however the author turns it, the prose
doesn't move.
What this script must prove (every line must be able to go red):
  A **the knobs aren't dead**: every knob **speaks when moved**, and the low end says something
    different from the high end (the criterion for a dead knob is "the output is the same however
    you turn it" => both ends must be compared).
  B **the sentences are executable**: each one is countable and checkable, never "a bit more
    tragic"; the humor knob goes through the **six-step chain**; the examples use `[bracket]`
    placeholders (the hard rule: "examples in a prompt get copied as material").
  C **the two defaults must not drift**: `util/style_kit.py::DEFAULTS` vs `config.py::SPEC`,
    `style_kit.CFG_KEYS` vs `sim/setup.py::_STYLE_FIELDS`, `config.py::SPEC` vs the field
    defaults in `world/state.py`. (This is the **documentation-drift gate**: `style_kit.py`'s
    comment says "criterion `verify_style_control.py` checks these two" -- and that script
    **did not exist**.)
  D **it really reaches the prompt**: `SetCtx.style_block()` is non-empty with the switch on,
    emits **not a single word** with it off, and **follows the knobs**; the three wiring points
    in `crew/agents.py` must really call `style_block()` / `from_config()` next to their
    "── 风格控制" headers.
Usage: .venv\\Scripts\\python.exe tools/verify_style_control.py
Output: assets/screenshots/style_control_report.json
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from dataclasses import fields
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG, SPEC                                    # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


#: 退出码统一出口（2026-10-28）。⚠ 这一支原来 `main() -> None`、**没有 `sys.exit`** ⇒
#:   它在 `tools/run_all_verifications.py` 里**恒绿**：断言红成一片，回归器看到的退出码仍是 0
#:   ⇒「红灯打出来也没人看得见」⇒ 那条覆盖**从来没被证明过**。
#:   （2026-10-28 实测：把第 126 行的条件改成 `False`，退出码仍是 0。）
#: [EN] ⚠ This one used to have `main() -> None` and **no `sys.exit`** => it was **always green** in
#: [EN] the regression (measured 2026-10-28: forcing an assertion to `False` still exited 0).
#: [EN] The exit code now goes through the shared outlet `tools/verify_exit.py`.
from tools.verify_exit import finish   # noqa: E402


# ══════════════════════════════════════════════════════════════
#  A 旋钮不是死的
# [EN] A The knobs are not dead
# ══════════════════════════════════════════════════════════════

#: `style_control_lines()` 里那六个数值旋钮：`(名字, 低档, 高档)`。
#: ⚠ 低/高档必须与默认值**差得够开**（`NEAR = 0.12`）—— 否则"没动过"，
#:   一行都不该发（那是 A2 钉的事）。
#: [EN] The six numeric knobs in `style_control_lines()`: `(name, low, high)`.
#: ⚠ The low/high ends must be **far enough** from the default (`NEAR = 0.12`) -- otherwise
#: [EN] "not moved" and not a single line should be emitted (that is what A2 pins).
KNOBS = (
    ('angst', 0.05, 0.90),
    ('satisfaction', 0.05, 0.90),
    ('romance', 0.05, 0.90),
    ('suspense', 0.05, 0.90),
    ('worldbuilding', 0.05, 0.90),
    ('iq', 0.05, 0.90),
)


def logic_knobs() -> None:
    from util import style_kit as SK

    # ── A1 ★★★ 每一个旋钮**动了就发声**，而且两端说的话**不一样** ──
    #   这才是"死旋钮"的判据：死旋钮 = 无论怎么调，输出都一样。
    #   ⚠ 只测"非空"不够 —— 一个恒返回同一句话的函数也"非空"。
    # [EN] ── A1 ★★★ Every knob **speaks when moved**, and the two ends say **different** things ──
    # [EN] That is the criterion for a dead knob: a dead knob reads the same however you turn it.
    # [EN] ⚠ "non-empty" alone is not enough -- a function that always returns the same sentence is
    # [EN] also "non-empty".
    dead = []
    for name, lo, hi in KNOBS:
        l_lo = SK.style_control_lines(**{name: lo})
        l_hi = SK.style_control_lines(**{name: hi})
        if not l_lo or not l_hi:
            dead.append(f'{name}: 有一端是空的（{len(l_lo)}/{len(l_hi)} 行）')
        elif l_lo == l_hi:
            dead.append(f'{name}: 两端说的话一样（还是死的）')
    ok('A1 ★★★ 六个数值旋钮**每一个**动了都发声，且两端说的**不一样**',
       not dead, str(dead))

    # ── A2 ★★ 默认值时**一个字都不发** ──
    #   默认 = 不打扰。旋钮全在默认位却每次都发一大段 ⇒ 作者会学会无视它。
    # [EN] ── A2 ★★ At the defaults, **not a single word** is emitted ──
    # [EN] Default = don't disturb. If it always emitted a big block at the defaults, the author
    # [EN] would learn to ignore it.
    ok('A2 ★★ 默认值时**一句话都不发**（默认 = 不打扰）',
       SK.style_control_lines() == [], str(SK.style_control_lines()))

    # ── A3 ★★★ 每一句都要**能数、能查**（不许是形容词）──
    #   "更虐一点""稍微搞笑些"执行不了 —— 模型只能猜。
    #   判据不靠词表，靠**结构**：句子里必须出现
    #     ① 一个**量**（阿拉伯数字或中文数字："一处""三成""一个"）
    #     或 ② 一个**判定**（必须 / 不许 / 只许 / 至少 / 最多）
    #   这样"可以花三成篇幅讲设定"算可数（"三成"是量），
    #   而"更虐一点"算不可数（"一点"是程度副词，不是量）。
    # [EN] ── A3 ★★★ Every sentence must be countable and checkable (never an adjective) ──
    # [EN] The criterion is structural, not a word list: the sentence must contain
    # [EN]   (1) a **quantity** (an Arabic or Chinese numeral: "一处" "三成" "一个"), or
    # [EN]   (2) a **verdict** (必须 / 不许 / 只许 / 至少 / 最多).
    # [EN] That way "可以花三成篇幅讲设定" counts as countable ("三成" is a quantity) while
    # [EN] "更虐一点" does not ("一点" is an adverb of degree, not a quantity).
    QUANT = re.compile(r'[0-9]|[零〇一二两三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟]')
    VERDICT = ('最多', '至少', '必须', '不许', '只许', '允许')
    ADJECTIVE = ('一点', '稍微', '些许', '尽量', '更虐', '更搞笑', '更甜', '更悬')
    lines = []
    for name, lo, hi in KNOBS:
        lines += SK.style_control_lines(**{name: lo})
        lines += SK.style_control_lines(**{name: hi})
    lines += SK.style_control_lines(pacing='fast')
    lines += SK.style_control_lines(pacing='slow')
    bad_cnt = [ln for ln in lines
               if not (QUANT.search(ln) or any(w in ln for w in VERDICT))]
    bad_adj = [ln for ln in lines if any(w in ln for w in ADJECTIVE)]
    ok('A3 ★★★ 每一句都**能数能查**（不许是"更…一点"这种形容词）',
       not bad_cnt and not bad_adj,
       f'不可数 {len(bad_cnt)} 条：{bad_cnt[:1]}｜形容词 {len(bad_adj)} 条：{bad_adj[:1]}')

    # ── A4 ★★ 幽默**不在** `style_control_lines` 里 ──
    #   数量要求跟写法要求放在同一处（`humor_guide`），免得"最多几处"写两遍。
    # [EN] ── A4 ★★ Humor is **not** in `style_control_lines` ──
    # [EN] The "how many" and the "how" live together (in `humor_guide`), so "at most how many" is
    # [EN] never written in two places.
    all_lines = SK.style_control_lines(angst=0.9, satisfaction=0.9, romance=0.9,
                                       suspense=0.9, worldbuilding=0.9, iq=0.9,
                                       pacing='roller')
    ok('A4 ★★ 幽默那一项**不在**风格控制里（它在 `humor_guide`，避免写两遍）',
       '笑点' not in all_lines and '幽默' not in all_lines, all_lines[:1])

    # ── A5 ★★ 节奏（枚举旋钮）动了也发声 ──
    # [EN] ── A5 ★★ The pacing knob (an enum) also speaks when moved ──
    pace_lines = {p: SK.style_control_lines(pacing=p) for p in ('slow', 'fast', 'roller')}
    ok('A5 ★★ 节奏（枚举）动了也发声，且三档各说各的',
       all(pace_lines.values())
       and len({tuple(v) for v in pace_lines.values()}) == 3,
       str({k: (v[0][:16] if v else '') for k, v in pace_lines.items()}))


# ══════════════════════════════════════════════════════════════
#  B 幽默那条链
# [EN] B The humor chain
# ══════════════════════════════════════════════════════════════
def logic_humor() -> None:
    from util import style_kit as SK

    hg = SK.humor_guide(0.3)

    # ── B1 ★★★ 六步链六步都在 ──
    #   少一步就只剩场面滑稽：笑完什么也不剩。
    # [EN] ── B1 ★★★ All six steps of the chain are there ──
    # [EN] One missing and only the farcical scene remains: you laugh and nothing is left.
    steps = ('支点', '小谎', '反噬', '揭穿', '嘴硬', '回收')
    miss = [s for s in steps if s not in hg]
    ok('B1 ★★★ 幽默的**六步链**六步都在（支点→小谎→反噬→揭穿→嘴硬→回收）',
       not miss, str(miss))

    # ── B2 ★★ 揭穿那一步只**陈述事实**、不许评判 ──
    #   一说"你撒谎"就变成批判，笑就死了。
    # [EN] ── B2 ★★ The exposure step only **states facts**, no judgement ──
    # [EN] Once it says "you're lying" it becomes a critique and the joke dies.
    ok('B2 ★★ 揭穿那一步写明「只陈述事实、不许评判」',
       '不许评判' in hg and '只陈述事实' in hg, '')

    # ── B3 ★★★ 范例用 [方括号] 占位，不许出现具体台词 ──
    #   硬规矩：「提示词里的例子会被当素材抄」——
    #   例子一旦带具体人名/物件，模型就会把它搬进正文。
    # [EN] ── B3 ★★★ The examples use [bracket] placeholders, no concrete lines ──
    # [EN] The hard rule: "examples in a prompt get copied as material".
    try:
        from util import prompts as P
        text, _src = P.template('humor', '')
        text = P.strip_comments(text)
    except Exception as e:                                     # noqa: BLE001
        text = ''
        ok('B3 ★★★ 范例用 [方括号] 占位，不许出现具体台词', False, repr(e))
        return
    ok('B3 ★★★ 范例用 [方括号] 占位，不许出现具体台词',
       '[' in text and ']' in text and '不是要骗谁' in text, '')

    # 范例段里**每一句"台词"**都必须带方括号占位。
    #   ⚠ 不能只看"带引号的行" —— 结论那句「笑点不是"他撒谎"，是"他自己的小算盘…。"」
    #     也带引号，但引的是**说法**不是台词。
    #   ⇒ 判据要认得出**台词行**：行里有引号 **且** 旁边有"说/道/问/答"这类动词。
    # [EN] Every **line of dialogue** in the example section must carry a bracket placeholder.
    # [EN] ⚠ "a line containing quotes" is not enough -- the conclusion line ("the joke is not 'he's
    # [EN] lying', it is 'his own little calculation got hit by the plot'") also contains quotes, but
    # [EN] it quotes a **phrase**, not a line of dialogue.
    # [EN] => the criterion has to recognize **dialogue lines**: a quote plus a speech verb nearby.
    start = text.find('**范例')
    end = text.find('**不成的写法')
    seg = text[start:end] if start >= 0 and end > start else ''
    SPEECH = ('说', '道', '问', '答', '喊', '叫', '回')
    quoted = [ln for ln in seg.splitlines()
              if ('"' in ln or '“' in ln)
              and any(w in ln for w in SPEECH)]
    no_ph = [ln for ln in quoted if '[' not in ln]
    ok('B3b ★★★ 范例段里**每一句台词**都带 [方括号] 占位（不许写具体台词）',
       seg and quoted and not no_ph,
       f'{len(quoted)} 句台词；没占位的：{no_ph[:1]}')

    # ── B4 ★★ 幽默档位不同 ⇒ 数量要求不同 ──
    # [EN] ── B4 ★★ A different humor level => a different count requirement ──
    ok('B4 ★★ 幽默档位不同 ⇒ 数量要求不同（最多一处 / 至少两处）',
       '最多一处' in SK.humor_guide(0.3) and '至少要有两处' in SK.humor_guide(0.9),
       '')

    # ── B5 ★★ 幽默调到 0 ⇒ 明确说"不许出现笑点" ──
    #   说"最多一处"等于**允许一处**。
    # [EN] ── B5 ★★ Humor at 0 => explicitly "no jokes allowed" ──
    # [EN] Saying "at most one" **allows** one.
    blk = SK.style_control_block(humor=0.0)
    ok('B5 ★★ 幽默调到 0 ⇒ 明确说「不许出现笑点」（"最多一处"等于允许一处）',
       SK.humor_guide(0.0) == '' and '不许出现笑点' in blk, '')

    # ── B6 ★★ 幽默与其它六项**故意不对称** ──
    #   别的六项在默认位**沉默**（离默认太近 = 当没动过）；
    #   幽默**始终发话**（调到 0 才闭嘴）—— 因为六步链是这本书幽默的**底子**，
    #   不是"动过才发"的那一类，而且"最多一处"是**上限**（作者不幽默也不会多出笑点）。
    #   ⇒ 这条判据是为了把这个**有意的例外**钉住，别哪天被人"统一"掉。
    # [EN] ── B6 ★★ Humor and the other six are **deliberately asymmetric** ──
    # [EN] The other six stay **silent** at their defaults (too close to the default = not moved);
    # [EN] humor **always speaks** (only 0 shuts it up) -- because the six-step chain is the **base**
    # [EN] of this book's humor, not a "only when moved" kind, and "at most one" is a **cap**.
    # [EN] => This assertion pins that **intentional exception** so nobody "unifies" it away.
    ok('B6 ★★ 幽默与其它六项**故意不对称**：幽默始终发话，六项在默认位沉默',
       '最多一处' in SK.style_control_block(humor=0.3)
       and SK.style_control_lines() == [],
       '')


# ══════════════════════════════════════════════════════════════
#  C 两处默认值不许漂
# [EN] C The two defaults must not drift
# ══════════════════════════════════════════════════════════════
def logic_defaults() -> None:
    from util import style_kit as SK

    # ── C1 ★★★ `style_kit.DEFAULTS` ↔ `config.SPEC` ──
    #   `style_kit.py` 写死一份是为了"不 import config"（config 读盘慢），
    #   于是**必须有人核对这两处** —— 那个人就是这份判据。
    # [EN] ── C1 ★★★ `style_kit.DEFAULTS` vs `config.SPEC` ──
    # [EN] `style_kit.py` hardcodes a copy so this module doesn't import `config` (which reads
    # [EN] from disk) -- so **someone must check the two agree**, and that someone is this script.
    drift = []
    for name, key in SK.CFG_KEYS.items():
        want = SK.DEFAULTS.get(name)
        got = SPEC.get(key, {}).get('default')
        if want is None or got is None or abs(float(want) - float(got)) > 1e-9:
            drift.append(f'{name}/{key}: style_kit={want} config={got}')
    ok('C1 ★★★ `style_kit.DEFAULTS` 与 `config.SPEC` 的默认值**一致**',
       not drift, str(drift))

    # ── C2 ★★★ `style_kit.CFG_KEYS` ↔ `sim/setup.py::_STYLE_FIELDS` ──
    #   多一张少一张 ⇒ 有一边读不到那个旋钮（表现成"推演时有、导出时没有"）。
    #   ⚠ 比的是**配置键的集合**，不是字典的键名 —— 两边的键名**故意不一样**：
    #     `setup` 那边用 world 的属性名（`angst_level`），`style_kit` 那边用短名（`angst`）。
    #     比字典本身会永远红，而且红得没有意义。
    # [EN] ── C2 ★★★ `style_kit.CFG_KEYS` vs `sim/setup.py::_STYLE_FIELDS` ──
    # [EN] One extra or one missing key means one side can't read that knob.
    # [EN] ⚠ Compare the **set of config keys**, not the dict keys -- the two key names are
    # [EN] **deliberately different**: `setup` uses the world attribute names (`angst_level`),
    # [EN] `style_kit` uses short names (`angst`). Comparing the dicts themselves would always be
    # [EN] red, and meaninglessly so.
    try:
        from sim import setup as S
        setup_pairs = {attr: key for attr, key in S._STYLE_FIELDS}
        same = (set(setup_pairs.values()) == set(SK.CFG_KEYS.values())
                and len(setup_pairs) == len(SK.CFG_KEYS))
        ok('C2 ★★★ `style_kit.CFG_KEYS` 与 `sim/setup._STYLE_FIELDS` 指的是**同一组配置键**',
           same,
           f'setup={sorted(setup_pairs.values())} vs kit={sorted(SK.CFG_KEYS.values())}')
    except Exception as e:                                     # noqa: BLE001
        ok('C2 ★★★ `style_kit.CFG_KEYS` 与 `sim/setup._STYLE_FIELDS` 指的是**同一组配置键**',
           False, repr(e))

    # ── C3 ★★ `config.SPEC` ↔ `world/state.py` 的字段默认值 ──
    #   三处（config / style_kit / state）写的是**同一个数**。
    # [EN] ── C3 ★★ `config.SPEC` vs the field defaults in `world/state.py` ──
    # [EN] Three places (config / style_kit / state) write the **same number**.
    try:
        from world.state import WorldState
        fmap = {f.name: f for f in fields(WorldState)}
        pairs = {'angst': 'angst_level', 'humor': 'humor_level',
                 'satisfaction': 'satisfaction_density', 'romance': 'romance_ratio',
                 'suspense': 'suspense_density',
                 'worldbuilding': 'worldbuilding_pace', 'iq': 'character_iq'}
        drift3 = []
        for name, attr in pairs.items():
            key = SK.CFG_KEYS.get(name, '')
            want = SPEC.get(key, {}).get('default')
            fld = fmap.get(attr)
            got = fld.default if fld is not None else None
            if want is None or got is None or abs(float(want) - float(got)) > 1e-9:
                drift3.append(f'{attr}: config={want} state={got}')
        ok('C3 ★★ `config.SPEC` 与 `world/state.py` 的字段默认值**一致**',
           not drift3, str(drift3))
    except Exception as e:                                     # noqa: BLE001
        ok('C3 ★★ `config.SPEC` 与 `world/state.py` 的字段默认值**一致**', False, repr(e))


# ══════════════════════════════════════════════════════════════
#  D 真的接进提示词了
# [EN] D It really reaches the prompt
# ══════════════════════════════════════════════════════════════
class _FakeWorld:
    """一个够用的假 `WorldState`（只要旋钮那几个属性）。"""

    def __init__(self, **knobs):
        self.angst_level = 0.3
        self.humor_level = 0.3
        self.satisfaction_density = 0.5
        self.romance_ratio = 0.3
        self.suspense_density = 0.5
        self.worldbuilding_pace = 0.5
        self.character_iq = 0.5
        self.pacing_style = 'medium'
        for k, v in knobs.items():
            setattr(self, k, v)


def logic_wiring() -> None:
    from crew.agents import SetCtx

    # ── D1 ★★★ 开关开着 ⇒ `style_block()` 非空 ──
    # [EN] ── D1 ★★★ Switch on => `style_block()` is non-empty ──
    ctx = SetCtx(world=_FakeWorld(), db=None)
    blk = ctx.style_block()
    ok('D1 ★★★ 开关开着时 `style_block()` 非空（那一段真的存在）',
       bool(blk.strip()), f'{len(blk)} 字')

    # ── D2 ★★★ 旋钮动了 ⇒ 输出**跟着变** ──
    #   这一条是"死旋钮"的**端到端**判据：从 world 一直到那一段话。
    #   ⚠ 只测 `style_control_lines()` 不够 —— 那只是纯函数；
    #     死旋钮真正坏在"world 上那个值根本没进这一段"。
    # [EN] ── D2 ★★★ Moving a knob changes the output ──
    # [EN] This is the **end-to-end** criterion for a dead knob: from `world` down to that paragraph.
    # [EN] ⚠ Testing `style_control_lines()` alone is not enough -- that is just a pure function;
    # [EN] a dead knob really breaks because "the value on world never reaches this paragraph".
    ctx2 = SetCtx(world=_FakeWorld(humor_level=0.95, angst_level=0.95), db=None)
    blk2 = ctx2.style_block()
    ok('D2 ★★★ 旋钮调了 ⇒ `style_block()` 的输出**跟着变**（旋钮不再是死的）',
       blk2 != blk and '至少要有两处' in blk2,
       f'{len(blk)} 字 → {len(blk2)} 字')

    # ── D3 ★★★ 开关关掉 ⇒ **一个字都不发** ──
    # ⚠ `CFG.set()` 只改内存（不落盘），但仍要**还原** —— 别把后面的判据带歪。
    # [EN] ── D3 ★★★ Switch off => **not a single word** is emitted ──
    # ⚠ `CFG.set()` only changes memory (no disk write), but it must still be **restored**.
    old = CFG.s('STYLE_CONTROL_ACTIVE')
    try:
        CFG.set('STYLE_CONTROL_ACTIVE', 'false')
        off = SetCtx(world=_FakeWorld(humor_level=0.95), db=None).style_block()
        ok('D3 ★★★ 开关关掉时**一个字都不发**（关掉 = 回到从前）',
           off == '', repr(off[:40]))
    finally:
        CFG.set('STYLE_CONTROL_ACTIVE', old)

    # ── D4 ★★ `from_config()` 读的是**配置**（导出那一侧手上没有 WorldState）──
    # [EN] ── D4 ★★ `from_config()` reads the **config** (the export side has no WorldState) ──
    from util import style_kit as SK
    old2 = CFG.s('STYLE_CONTROL_ACTIVE')
    try:
        CFG.set('STYLE_CONTROL_ACTIVE', 'false')
        ok('D4 ★★ `from_config()` 在开关关时返回**空串**（不猜、不硬填）',
           SK.from_config() == '', repr(SK.from_config()[:40]))
        CFG.set('STYLE_CONTROL_ACTIVE', 'true')
        ok('D4b ★★ `from_config()` 在开关开时**读得到配置**（不是空串）',
           bool(SK.from_config().strip()), '')
    finally:
        CFG.set('STYLE_CONTROL_ACTIVE', old2)

    # ── D5 ★★★ `crew/agents.py` 里三处接线，每处的标题旁边**真的调了**它 ──
    #   ⚠ 光看"标题字符串还在"不够 —— 有人把 `ctx.style_block()` 删掉、
    #     标题还留着，提示词里就只剩一个空标题（**看起来还在，其实没了**）。
    #   ⚠ 也不能只按"附近几行有没有那个调用"来判 —— 导出那一路是
    #     **隔着四百多行传参**的（`from_config()` → 形参 `style` → 标题那一行）。
    #   ⇒ 判据要**追一遍值的来路**：
    #     ① 直连：标题那几行里就有 `style_block()` / `from_config()`；
    #     ② 直连变量：`X = …style_block()` / `X = …from_config()`；
    #     ③ 间接变量：`Y = X`（把上面那个 X 当参数传下去）。
    # [EN] ── D5 ★★★ The three wiring points in `crew/agents.py` really call it ──
    # [EN] ⚠ Checking only that the header string is still there is not enough -- someone could
    # [EN] delete `ctx.style_block()` and leave the header, and the prompt would keep an empty
    # [EN] header (**it looks present but it is gone**).
    # [EN] ⚠ Nor can it be judged by "is the call within a few lines" -- the export path passes it
    # [EN] **four hundred lines away** (`from_config()` -> parameter `style` -> the header line).
    # [EN] => the criterion has to **trace where the value came from**:
    # [EN]   (1) direct: the call is in the header's own lines;
    # [EN]   (2) a direct variable: `X = ...style_block()` / `X = ...from_config()`;
    # [EN]   (3) an indirect variable: `Y = X` (that X passed along as a parameter).
    src = (APP_DIR / 'crew' / 'agents.py').read_text(encoding='utf-8')
    lines = src.split('\n')
    src_names = set(re.findall(
        r'^\s*(\w+)\s*=\s*[^\n=]*?(?:style_block\(\)|from_config\(\))', src, re.M))
    indirect: set[str] = set()
    if src_names:
        alt = '|'.join(re.escape(x) for x in sorted(src_names, key=len, reverse=True))
        indirect = set(re.findall(
            r'(\w+)\s*=\s*(?:[\w.]*\.)?(?:' + alt + r')\b', src))
    wired_names = src_names | indirect
    spots = [i for i, ln in enumerate(lines) if '── 风格控制' in ln]
    unwired: list[int] = []
    for i in spots:
        expr = '\n'.join(lines[i:i + 2])
        near = '\n'.join(lines[max(0, i - 4):i + 4])
        direct = ('style_block()' in near) or ('from_config()' in near)
        names = set(re.findall(r'[A-Za-z_]\w*', expr))
        if not (direct or (names & wired_names)):
            unwired.append(i + 1)
    ok('D5 ★★★ `crew/agents.py` 里每处「── 风格控制」标题**真的接上了**它',
       spots and not unwired,
       f'共 {len(spots)} 处；没接上的行号 {unwired}'
       f'｜直连变量 {sorted(src_names)}｜间接变量 {sorted(indirect)}')
    ok('D5b ★★ 接进提示词的路**至少三条**（作家 / MuMuAINovel 细纲 / 导出）',
       len(spots) >= 3, f'{len(spots)} 处')
    ok('D5c ★★ 三条路里**导出那一路**也接上了（它靠传参，最容易漏）',
       'style' in indirect or 'style' in src_names,
       f'直连 {sorted(src_names)}｜间接 {sorted(indirect)}')


# ══════════════════════════════════════════════════════════════
def main() -> int:
    try:
        print('\n── A 旋钮不是死的 ──')
        logic_knobs()
        print('\n── B 幽默那条链 ──')
        logic_humor()
        print('\n── C 两处默认值不许漂 ──')
        logic_defaults()
        print('\n── D 真的接进提示词了 ──')
        logic_wiring()
    except BaseException:                                        # noqa: BLE001
        report['fatal'] = traceback.format_exc()
        print(report['fatal'])

    return finish(report, out_path=OUT / 'style_control_report.json')


if __name__ == '__main__':
    sys.exit(main())
