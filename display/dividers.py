# -*- coding: utf-8 -*-
"""运行界面与落盘用的**分隔符**（2026-10-06 用户要求）。

用户原话
--------
「一天以及一个场景和一个故事结束之后，给一个明显的分隔符，不同类型（可能还有别的
类型 你加上）用不同的分隔符，分隔符还可以用于某个模块开始，分隔符中间可以带时间
（小说里的时间）标题 以及别的关键信息（不能太长）」

规格
----
一条分隔符 = **左右两道细线 + 中间一枚标签**。标签 = `符号 + 标题 + 关键信息`。
信息量有**硬上限**（太长就把线挤没了，屏幕上只剩一行字，起不到"分界"的作用），
所以在 `Divider.__post_init__` 里就截断。

| kind | 何时用 | 符号 | 标签长相（示例） |
|---|---|---|---|
| `DAY_START` | 新的一天开始 | ◆ | `◆ 第七天 · 辰时 07:20` |
| `DAY_END` | 一天结束 | ◆ | `◆ 第七天终 · 12 幕 · 3 件大事` |
| `SCENE_END` | 一幕结束（换了时间/地点） | ◇ | `◇ 戌时 · 临河茶肆` |
| `STORY_END` | 整个故事结束 | ❖ | `❖ 全篇终 · 走到第 12 天 · 31 幕` |
| `MODULE_START` | 某个模块开始（导出/小结…） | ▣ | `▣ 导出 · 素材册` |

分工（跟 `display.script_render` 一样）
--------------------------------------
* `display` 只出**结构化数据** + **纯文本**，**不依赖 flet、不依赖界面语言**；
* 屏幕上的标签由 GUI 用 `t()` 现拼（`sim` 层绝不拼给人看的句子）；
* 落盘/CLI 用 `line()`（中文，跟 `script_render.KIND_LABEL` 那批常量同一路数）。

为什么要有 `tmpl`
-----------------
`Divider.meta` 存**结构化字段**（第几天、几幕、什么时辰…），而不是拼好的句子 ——
这样同一份数据在中英文界面都能正确显示，也不会出现"落盘文本跟着界面语言变"。

English:
**Separator** for runtime UI and disk output (user request 2026-10-06).
User's own words
--------
"After a day, a scene, and a story end, give an obvious separator; different types (there may be
other
types, you add them) use different separators; separators can also be used when a module starts;
a separator can carry time in the middle
(in-story time), title, and other key info (can't be too long)"
Spec
----
One separator = **two thin lines on the left and right + one label in the middle**. Label =
`symbol + title + key info`.
Information has a **hard cap** (too long and it squeezes the lines away, leaving just a line of
text on screen, failing the "boundary" purpose),
so it's truncated right in `Divider.__post_init__`.
| kind | when to use | symbol | label appearance (example) |
|---|---|---|---|
Division of labor (same as `display.script_render`)
--------------------------------------
* `display` only produces **structured data** + **plain text**, **does not depend on flet, does not depend on UI language**;
* on-screen labels are assembled live by the GUI using `t()` (`sim` layer never assembles human-facing sentences);
* disk/CLI uses `line()` (Chinese, same approach as the `script_render.KIND_LABEL` constants).
Why `tmpl` is needed
-----------------
`Divider.meta` stores **structured fields** (which day, how many acts, what time...), not
pre-assembled sentences --
so the same data displays correctly in Chinese and English UIs, and disk text won't change with
UI language.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DAY_START = 'day_start'
DAY_END = 'day_end'
SCENE_END = 'scene_end'
STORY_END = 'story_end'
MODULE_START = 'module_start'

ALL_KINDS = (DAY_START, DAY_END, SCENE_END, STORY_END, MODULE_START)

# 每种一个符号 —— 符号本身承担了一半"一眼看出这是哪一类分界"的活。
# [EN] Each type gets one symbol -- the symbol itself carries half the job of "instantly telling which
# [EN] kind of boundary this is".
SYMBOL = {
    DAY_START: '◆', DAY_END: '◆',
    SCENE_END: '◇', STORY_END: '❖', MODULE_START: '▣',
}

LINE_CHAR = '─'
_LINE_FILL = 30        # 纯文本形态里标签两侧各铺多长（屏幕侧由 GUI 按可用宽度自适应）
# [EN] In plain-text form, how wide to pad on each side of the label (the screen side is adapted by the
# [EN] GUI based on available width)

# 信息量上限。**按"整条标签"算，不是各段各算** —— 用户原话是"不能太长"，
# 而分三段各限一次的结果是三段加起来照样把线挤没（第一版就吃了这个亏）。
# [EN] Cap on information. **Counted for the whole label, not per segment** -- the user's own words
# [EN] were "can't be too long",
# [EN] and limiting each of the three segments separately still lets the three combined squeeze the
# [EN] line away (the first version learned this the hard way).
MAX_LABEL = 30
# 单段的兜底上限（第一段无论如何也要放得下）
# [EN] Fallback cap for a single segment (the first segment must fit no matter what)
MAX_SEG = 20


def _clip(s: str, n: int) -> str:
    s = str(s or '').strip()
    return s if len(s) <= n else s[:max(1, n - 1)] + '…'


@dataclass
class Divider:
    """一条分隔符。`meta` 是给界面用的结构化字段，不是给人读的句子。
        English:
    One divider. `meta` is structured fields for the UI, not a human-readable sentence.
    """

    kind: str
    meta: dict = field(default_factory=dict)
    # 调用方额外挂的一句短注（**已经是给人读的文本**，屏幕上原样显示；
    # 中英文界面都能用 —— 比如模块名、结束原因）
    # [EN] A short note the caller tacks on extra (**already human-readable text**, displayed as-is on
    # [EN] screen;
    # [EN] works in both Chinese and English UIs -- e.g. module name, end reason)
    note: str = ''

    def __post_init__(self) -> None:
        if self.kind not in ALL_KINDS:
            raise ValueError(f'未知分隔符类型: {self.kind!r}')
        self.note = _clip(self.note, MAX_SEG)

    @property
    def symbol(self) -> str:
        return SYMBOL[self.kind]

    # ── 纯文本形态（落盘 / CLI / 日志）──
    # [EN] -- Plain-text form (disk / CLI / logs) --
    def label(self) -> str:
        """中文标签（落盘与命令行用；屏幕请让 GUI 用 `t()` 现拼）。

        **整段塞不下就丢段，而不是把句子截成 `…`**：`第 7 天终 · 12 幕 · 3…`
        这种半截话读起来像坏了；宁可少给一段信息。
        
                English:
        Chinese label (for disk and command line; for screen, have the GUI assemble live with `t()`).
                **If the whole thing doesn't fit, drop a segment rather than truncating the sentence with `…`**: `第 7 天终 · 12 幕 · 3…`
                this kind of half-sentence reads as broken; better to give one less segment of info.
        """
        parts = [p for p in (self._zh_title(), self.note) if p]
        if not parts:
            return self.symbol
        out = f'{self.symbol} {_clip(parts[0], MAX_SEG)}'
        for p in parts[1:]:
            cand = f'{out} · {p}'
            if len(cand) > MAX_LABEL:
                break
            out = cand
        return out

    def _zh_title(self) -> str:
        m = self.meta
        if self.kind == DAY_START:
            bits = [f'第 {m.get("day", 1)} 天']
            if m.get('clock'):
                bits.append(str(m['clock']))
            return ' · '.join(bits)
        if self.kind == DAY_END:
            bits = [f'第 {m.get("day", 1)} 天终']
            if m.get('scenes'):
                bits.append(f'{m["scenes"]} 幕')
            if m.get('events'):
                bits.append(f'{m["events"]} 件大事')
            return ' · '.join(bits)
        if self.kind == SCENE_END:
            bits = [str(m.get('clock') or ''), str(m.get('place') or '')]
            return ' · '.join(b for b in bits if b) or '换场'
        if self.kind == STORY_END:
            bits = ['全篇终']
            if m.get('day'):
                bits.append(f'走到第 {m["day"]} 天')
            if m.get('scenes'):
                bits.append(f'{m["scenes"]} 幕')
            return ' · '.join(bits)
        return str(m.get('name') or '')

    def line(self) -> str:
        """纯文本一整条。
                English:
        The plain-text whole line.
        """
        side = LINE_CHAR * _LINE_FILL
        return f'{side} {self.label()} {side}'

    def md_line(self) -> str:
        """落盘用的一行。

        **用 `> ` 起头**（引用块）：这样它既在 Markdown 里看得出是分隔，
        又不会被 `script_render` 的反解正则当成台词或正文（那套正则认的是
        `名字：台词`、`· 动作` 这些形态，`> ` 开头的行一律落空）。
        
                English:
        The one line used for disk output.
                **Start with `> `** (blockquote): this way it reads as a separator in Markdown,
                and won't be treated as dialogue or body text by `script_render`'s reverse-parse regex (that regex recognizes
        """
        return f'> {self.line()}'

    def to_dict(self) -> dict:
        return {'kind': self.kind, 'meta': dict(self.meta), 'note': self.note}


# ══════════════════════════════════════════════════════════════
#  工厂（调用方用这些，别手搓 Divider）
# [EN] Factory (callers use these, don't hand-roll a Divider)
# ══════════════════════════════════════════════════════════════
def day_start(day: int, clock: str = '') -> Divider:
    return Divider(DAY_START, {'day': int(day or 1), 'clock': str(clock or '')})


def day_end(day: int, *, scenes: int = 0, events: int = 0,
            note: str = '') -> Divider:
    return Divider(DAY_END, {'day': int(day or 1), 'scenes': int(scenes or 0),
                             'events': int(events or 0)}, note=note)


def scene_end(clock: str = '', place: str = '') -> Divider:
    return Divider(SCENE_END, {'clock': str(clock or ''), 'place': str(place or '')})


def story_end(*, day: int = 0, scenes: int = 0, note: str = '') -> Divider:
    return Divider(STORY_END, {'day': int(day or 0), 'scenes': int(scenes or 0)},
                   note=note)


def module_start(name: str, info: str = '') -> Divider:
    return Divider(MODULE_START, {'name': str(name or '')}, note=info)
