# -*- coding: utf-8 -*-
"""**风格旋钮 → 提示词里能执行的那句话**（2026-10-27）。

★★★ 这个模块是为修一个真 bug 建的：界面上那七八个"风格控制"滑杆
（虐心 / 幽默 / 爽点 / 感情 / 悬念 / 世界观 / 智商 / 节奏）**全是死的**。
链路查下来是：`config.py` 有定义 → `sim/setup.py` 读进 `world.humor_level`
→ **然后就没有任何消费者了**。唯一能读它的是 `world/state.py` 的
`style_control_summary()` / `style_control_dict()`，而这两个方法
**全项目零调用**（只有定义行）。于是拖到 0 和拖到 1，推演一模一样。

★ 为什么这个模块是"一句可执行的话"，不是"幽默度 30%"：
  「幽默度 30%」对写东西**没有任何约束力** —— 模型没法执行一个百分比。
  要能执行，就得写成"这一段最多一处这样的笑点""必须有一处拿不回来的东西"
  这种**能数、能查、能照做**的话。

★ 为什么放在 `util/` 而不是 `world/` 或 `crew/`：
  `crew` 依赖 `world`（`crew/agents.py` 拿 `world.world_prefix()`）。
  放 `world/` 里 → `world` 要 import `crew` ⇒ 循环 import；
  放 `crew/` 里 → `world/state.py` 用不了（而**作家那一侧**要靠它）。
  `util/` 两边都能进，且它不依赖任何一边。

★ 为什么"偏离默认值"才产出一句话：
  默认值是"作者没动过"的意思。若每个值都产出一句话，那么
  ① 每本书的提示词都凭空多出七八行噪音；
  ② 用户**没有动过**的那些旋钮也会开始管事（等于替他做了决定）。
  所以：**离默认值够远才算"作者动过"**（`NEAR`）。
  ⚠ 这条不能改成"只要不是默认值就发"—— 那会让 `0.30 → 0.30`（浮点相等
    没问题，但 `0.3` 与 `0.30000000000000004` 这类）忽然生效，
    而用户什么也没做。

★ 幽默那一项**不在这份清单里**：它有六步链和范例，单独一个函数
  `humor_guide()`（内容外置在 `prompts/humor.txt`），避免"数量"在两处各写一遍
  （那是本项目最恨的"同一件事两处实现"）。

English:
**Style knobs → the one executable sentence in the prompt** (2026-10-27).
★★★ This module exists to fix a real bug: the "style control" sliders in the UI
(angst / humor / payoff / romance / suspense / worldbuilding / IQ / pacing) were **all dead**.
The chain: `config.py` defines them -> `sim/setup.py` reads them into `world.humor_level`
-> **and then nothing consumes them**. The only things that could read them are
`world/state.py`'s `style_control_summary()` / `style_control_dict()`, and **those two methods have
zero callers in the whole project** (only their definition lines). So dragging to 0 and dragging to 1
produced identical derivations.
★ Why each knob becomes "one executable sentence" and not "humor 30%": "humor 30%" has **no
constraining power** on prose -- a model cannot execute a percentage. To be executable it has to be
"at most one such joke in this passage" / "there must be one thing you cannot get back" -- countable,
checkable, followable.
★ Why this module lives in `util/` and not `world/` or `crew/`: `crew` depends on `world`
(`crew/agents.py` reads `world.world_prefix()`). Putting it in `world/` means `world` imports `crew`
=> circular import; putting it in `crew/` means `world/state.py` can't use it (and the **writer side**
needs it). `util/` is reachable from both and depends on neither.
★ Why a sentence is only produced when the knob **deviates from its default**: the default means
"the author never touched it". If every value produced a sentence, then (1) every book's prompt
gains seven or eight lines of noise, and (2) knobs the author never touched would start dictating
the prose (making decisions for them). So: **far enough from the default counts as "the author moved
it"** (`NEAR`).
★ Humor is **not** in that list: it has a six-step chain and examples, so it gets its own function
`humor_guide()` (content externalized in `prompts/humor.txt`) -- otherwise the "how many" would be
written in two places (the thing this project hates most: "two implementations of one thing").
"""
from __future__ import annotations

__all__ = ['NEAR', 'humor_guide', 'style_control_lines', 'style_control_block',
           'from_config']


#: 离默认值多近算"没动过"。0.12 ≈ 量程的 12%。
#: ⚠ 调大它 = 旋钮更接近死的；调小它 = 轻微一动就发话。都别乱动。
# [EN] How close to the default still counts as "never touched". 0.12 is about 12% of the range.
# [EN] ⚠ Bigger = closer to a dead knob; smaller = a tiny nudge starts speaking. Don't fiddle.
NEAR = 0.12


#: 旋钮默认值（`config.py` 里那些 `default=`）。
#: ⚠ **两处必须一样** —— 这里写死是为了"不 import config"（`config` 读盘慢，
#:   而且 `util/` 不想依赖它）；`config.py` 那边的默认值改了，这里要跟着改。
#:   判据 `verify_style_control.py` 会核对这两处（不一致就红）。
# [EN] Knob defaults (the `default=` values in `config.py`).
# [EN] ⚠ **The two places must agree** -- hardcoded here so this module doesn't import `config`
# [EN] (`config` reads from disk and `util/` doesn't want that dependency); if the default in
# [EN] `config.py` changes, this must change with it. Criterion `verify_style_control.py` checks
# [EN] that (red on mismatch).
DEFAULTS: dict[str, float] = {
    'angst': 0.3,
    'humor': 0.3,
    'satisfaction': 0.5,
    'romance': 0.3,
    'suspense': 0.5,
    'worldbuilding': 0.5,
    'iq': 0.5,
}


def _on(v: float, default: float) -> bool:
    """这个旋钮算不算"作者动过"。
        English:
    Whether this knob counts as "the author moved it".
    """
    try:
        return abs(float(v) - float(default)) >= NEAR
    except (TypeError, ValueError):
        return False


def style_control_lines(*, angst: float = 0.3, satisfaction: float = 0.5,
                        romance: float = 0.3, suspense: float = 0.5,
                        worldbuilding: float = 0.5, iq: float = 0.5,
                        pacing: str = 'medium') -> list[str]:
    """风格旋钮 → **能数、能查、能照做**的一句话（每项一行）。

    ★ **幽默不在这里**（它在 `humor_guide()` 里，带着六步链和范例）——
      数量要求跟写法要求放在同一处，免得"最多几处"在两个地方各写一遍。

    ★ 每一句都必须**可执行**：
      - 能数（"最多一处" / "至少两处"）
      - 能查（"有人当场被驳倒"）
      - 不许是形容词（不许写"更虐一点""更搞笑一点"—— 那执行不了）。

        English:
    Style knobs -> **countable, checkable, followable** one-liners (one per knob).
        ★ **Humor is not here** (it is in `humor_guide()`, with the six-step chain and examples) -- the
        [EN] "how many" requirement sits next to the "how" requirement, so "at most how many" is never
        [EN] written in two places.
        ★ Every line must be **executable**: countable ("at most one" / "at least two"), checkable
        [EN] ("someone is refuted on the spot"), and never an adjective (never "a bit more tragic" --
        [EN] that cannot be executed).
    """
    out: list[str] = []

    # ① 虐心
    if _on(angst, DEFAULTS['angst']):
        if float(angst) <= 0.10:
            out.append('① **这一段不许有真伤**：没有人死、没有人受不可逆的伤，'
                       '最重不过是难堪一次。')
        elif float(angst) >= 0.70:
            out.append('① **必须有一处拿不回来的东西**：不是受伤、不是生气 —— '
                       '是失去（一个人、一件东西、一个机会），而且当场补不回来。')
        else:
            out.append('① **要有一处不划算的取舍**：总有人吃亏，并且没人补偿他。')

    # ② 爽点
    if _on(satisfaction, DEFAULTS['satisfaction']):
        if float(satisfaction) <= 0.15:
            out.append('② **这一段不许当场解决任何事**：谁都没赢，问题留着。')
        elif float(satisfaction) >= 0.70:
            out.append('② **必须有一处当场兑现**：有人当场被驳倒、当场拿到、'
                       '当场认出来 —— 而且读者看得见那个瞬间。')
        else:
            out.append('② **可以有一处小小的如愿**（不必当场翻盘，'
                       '但要让读者看见一点甜头）。')

    # ③ 感情线
    if _on(romance, DEFAULTS['romance']):
        if float(romance) <= 0.12:
            out.append('③ **这一段不许有感情戏**（不许心动、不许暧昧、'
                       '不许"他看了她一眼"那一路）。')
        elif float(romance) >= 0.65:
            out.append('③ **感情线要往前挪一格**：两人之间有一件事**没说破**，'
                       '但有一个**看得见的动作**（替她挡了一下、把伞递过去、多买了一份）。')
        else:
            out.append('③ **感情线只许留一点温度**（一个动作、一句话的后半截，不许表白）。')

    # ④ 悬念
    if _on(suspense, DEFAULTS['suspense']):
        if float(suspense) <= 0.15:
            out.append('④ **这一段不许新增悬念**（别再抛出没头没尾的新谜团）。')
        elif float(suspense) >= 0.70:
            out.append('④ **至少留两个没解开的扣**，且最后那个扣要**具体**'
                       '（不是一个气氛，是一件看得见、说不清的事）。')
        else:
            out.append('④ **留一个没解开的扣**（要具体，不许只是"还有蹊跷"）。')

    # ⑤ 世界观展开
    if _on(worldbuilding, DEFAULTS['worldbuilding']):
        if float(worldbuilding) <= 0.20:
            out.append('⑤ **不许停下来讲解设定**：世界只许通过"人物怎么用它"露出来，'
                       '不许旁白解释。')
        elif float(worldbuilding) >= 0.75:
            out.append('⑤ **可以花三成篇幅讲设定**（但要有人在场听，别写成说明书）。')
        else:
            out.append('⑤ **设定只许从人物的用法里露出来**，不要停下来讲解。')

    # ⑥ 人物智商
    if _on(iq, DEFAULTS['iq']):
        if float(iq) <= 0.25:
            out.append('⑥ **允许人物犯他认知范围内的错**'
                       '（不许犯"任何人都不会犯"的低级错）。')
        elif float(iq) >= 0.75:
            out.append('⑥ **人物不许犯他已经知道能避免的错**；'
                       '他的错只能来自"他不知道"或"他不敢"。')
        else:
            out.append('⑥ **人物不许犯常识性的蠢错**'
                       '（错可以，但要错在他不知道或他不敢的地方）。')

    # ⑦ 节奏（枚举：不是默认值就发）
    if str(pacing or 'medium').strip().lower() != 'medium':
        _p = str(pacing or '').strip().lower()
        if _p == 'slow':
            out.append('⑦ **慢**：宁可少写一件事，也要把当下的气息写足；不许赶。')
        elif _p == 'fast':
            out.append('⑦ **快**：这一段要有一处明显的推进'
                       '（新的信息、新的动作、新的麻烦），不许原地转。')
        elif _p == 'roller':
            out.append('⑦ **过山车**：这一段要有一次**起落**'
                       '（先紧起来再松一下，或反过来）。')

    return out


def humor_guide(level: float = 0.3) -> str:
    """幽默那一项 → **六步链 + 范例**（内容外置在 `prompts/humor.txt`）。

    ★ 为什么范例里用 `[方括号]` 而不是具体台词：
      本项目的硬规矩是「**提示词里的例子会被当素材抄**」——
      例子一旦带具体台词/专名，模型就会把它搬进正文（"孙胖子""打火机"
      直接出现在别的书里）。用方括号占位，它就只学到**做法与节奏**，
      抄不走内容。
    ★ 为什么 `level ≤ 0.05` 返回空串：
      作者明确把幽默调到 0 = "这一本不许有笑点"。这时候连"最多一处"
      都不该说 —— 说"最多一处"等于**允许一处**。

        English:
    The humor knob -> **the six-step chain + examples** (content externalized in `prompts/humor.txt`).
        ★ Why the examples use `[brackets]` instead of concrete dialogue: this project's hard rule is
        [EN] "**examples in a prompt get copied as material**" -- once an example carries concrete lines
        [EN] or proper nouns, the model carries them into the prose ("Sun Pangzi" and "the lighter" show
        [EN] up in another book). With bracketed placeholders it only learns the **method and rhythm**,
        [EN] and nothing copyable.
        ★ Why `level <= 0.05` returns an empty string: the author explicitly set humor to 0 = "no jokes
        [EN] in this book". Even "at most one" should not be said then -- saying it **allows** one.
    """
    try:
        lv = float(level)
    except (TypeError, ValueError):
        lv = 0.3
    if lv <= 0.05:
        return ''
    try:
        from util import prompts as _P
        text, _src = _P.template('humor', '')
        # ⚠ **必须剥掉整行注释**（`util/prompts.py` 有现成的 `strip_comments`）——
        #   模板头部那几行是"改这个文件就能改提示词"这类**给维护者**的说明，
        #   原样进提示词就是纯噪音（而且"改提示词就改这个文件"对模型毫无意义）。
        #   ★ 别的调用方（如 `agent/core.py` 的 `_tail`）也是这么处理的 ——
        #   漏一次就会让人在日志里看见"改提示词请编辑 prompts/xxx.txt"。
        # [EN] ⚠ **Must strip whole-line comments** (`util/prompts.py` has `strip_comments`) -- the
        # [EN] template header is a note **for maintainers** ("change the prompt by editing this file"),
        # [EN] and verbatim in the prompt it is pure noise ("change the prompt by editing this file" means
        # [EN] nothing to the model).
        # [EN] ★ Other callers (e.g. `_tail` in `agent/core.py`) do the same -- miss it once and you see
        # [EN] "change the prompt by editing prompts/xxx.txt" in the logs.
        text = _P.strip_comments(text)
    except Exception:                                        # noqa: BLE001
        text = ''
    text = str(text or '').strip()
    if not text:
        return ''
    if lv >= 0.65:
        cap = ('**这一段至少要有两处**这样的笑点（不要都挤在一处 —— '
               '至少有一处要落在人物自己身上）。')
    else:
        cap = '**这一段最多一处**这样的笑点。'
    return f'{text}\n{cap}'


def style_control_block(*, humor: float = 0.3, angst: float = 0.3,
                         satisfaction: float = 0.5, romance: float = 0.3,
                         suspense: float = 0.5, worldbuilding: float = 0.5,
                         iq: float = 0.5, pacing: str = 'medium',
                         with_humor: bool = True) -> str:
    """风格控制 → **一整段**（给作家与 MuMuAINovel 那一侧用）。

    ★ 为什么它**不能**塞进 `world_brief()`：
      `world_brief(cap)` 是 `world_prefix()[:cap]`，而 `world_prefix()` **最前面**
      就是顶级规则（实测某部真实作品那份 1853 字）⇒ `cap=1200` 时，顶级规则就把
      位置吃满了，**世界观/类型/风格/写作层规则全被挤掉**（实测）。
      所以风格控制必须走**独立的一段**，不能挂在那一串后面。

        English:
    Style control -> **one whole section** (for the writer and the MuMuAINovel side).
        ★ Why it **cannot** go inside `world_brief()`: `world_brief(cap)` is `world_prefix()[:cap]`, and
        [EN] `world_prefix()` starts with the top-level rules (measured: 1853 chars for one real book)
        [EN] => at `cap=1200` the rules alone fill the space and **the worldview/type/style/writer notes
        [EN] are all squeezed out** (measured). So the style control has to be **its own section**; it
        [EN] cannot hang off the end of that string.
    """
    parts: list[str] = []
    if with_humor:
        hg = humor_guide(humor)
        if hg:
            parts.append(hg)
        elif float(humor) <= 0.05:
            parts.append('── 幽默 ──\n'
                         '**这一段不许出现笑点**（不许插科打诨、不许角色讲笑话、'
                         '不许旁白抖机灵、不许夸张的动作或口音）。')
    lines = style_control_lines(angst=angst, satisfaction=satisfaction,
                                romance=romance, suspense=suspense,
                                worldbuilding=worldbuilding, iq=iq,
                                pacing=pacing)
    if lines:
        parts.append('── 风格控制（这一段要写成什么样，**逐条照做**）──\n'
                     + '\n'.join(lines))
    return '\n\n'.join(p for p in parts if p.strip())


#: 旋钮 → 配置键（与 `sim/setup.py::_STYLE_FIELDS` 指的是**同一组配置键**）
#: —— 导出那一侧手上**没有** `WorldState`（见 `export/novel_version.py` 的
#: "事实采集"注释），只能直接读配置。
#: ⚠ 两张表的**键名故意不一样**：那边用 world 的属性名（`angst_level`），
#:   这边用短名（`angst`）—— 所以比的时候要比**配置键的集合**，比字典本身会永远红。
#: ⚠ 配置键的集合必须一样：多一个少一个，就有一边读不到那个旋钮（表现成
#:   "推演时有、导出时没有"）。
# [EN] Knob -> config key (the **same set of config keys** as `sim/setup.py::_STYLE_FIELDS`) --
# [EN] the export side has **no** `WorldState` on hand (see the "fact collection" note in
# [EN] `export/novel_version.py`), so it reads the config directly.
# [EN] ⚠ The two tables' **key names are deliberately different**: that one uses the world attribute
# [EN] names (`angst_level`), this one uses short names (`angst`) -- so compare the **set of config
# [EN] keys**; comparing the dicts themselves would always be red.
# [EN] ⚠ The sets of config keys must match: one extra or one missing key means one side can't read
# [EN] that knob (manifesting as "present during derivation, absent at export").
CFG_KEYS: dict[str, str] = {
    'angst': 'ANGST_LEVEL',
    'humor': 'HUMOR_LEVEL',
    'satisfaction': 'SATISFACTION_DENSITY',
    'romance': 'ROMANCE_RATIO',
    'suspense': 'SUSPENSE_DENSITY',
    'worldbuilding': 'WORLDBUILDING_PACE',
    'iq': 'CHARACTER_IQ',
}


def from_config() -> str:
    """**直接从配置读旋钮** → 一段（给手上没有 `WorldState` 的场合，比如导出）。

    ★ 为什么不多这一条路：导出那一侧（`export/novel_version.py`）**没有**
      `WorldState` 对象 —— 它只有运行文件夹。而旋钮本来就是**配置级**的
      （`sim/setup.py` 也是 `CFG.f(...)` 读出来的），所以这里读配置是**同一个源**，
      不是"另一份数据"。
    ⚠ 读不到配置时**返回空串**（不猜、不用默认值硬填）—— 那说明配置坏了，
      宁可这一段不发，也不要发一份错的风格要求。

        English:
    **Read the knobs straight from the config** -> one paragraph (for places with no `WorldState`,
    e.g. export).
        ★ Why this extra path: the export side (`export/novel_version.py`) has **no** `WorldState`
        [EN] object -- only the run folder. And the knobs are **config-level** to begin with
        [EN] (`sim/setup.py` reads them with `CFG.f(...)` too), so reading the config here is the
        [EN] **same source**, not "another copy of the data".
        ⚠ If the config can't be read, **return an empty string** (don't guess, don't hard-fill the
        [EN] defaults) -- that means the config is broken, and it's better to emit nothing than to emit
        [EN] wrong style requirements.
    """
    try:
        from config import CFG as _CFG
        if not _CFG.b('STYLE_CONTROL_ACTIVE'):
            return ''
    except Exception:                                        # noqa: BLE001
        return ''
    vals: dict[str, float] = {}
    for name, key in CFG_KEYS.items():
        try:
            vals[name] = float(_CFG.f(key))
        except Exception:                                    # noqa: BLE001
            return ''
    try:
        pacing = str(_CFG.s('PACING_STYLE') or 'medium')
    except Exception:                                        # noqa: BLE001
        pacing = 'medium'
    try:
        return style_control_block(pacing=pacing, **vals)
    except Exception:                                        # noqa: BLE001
        return ''
