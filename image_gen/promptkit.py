# -*- coding: utf-8 -*-
"""出图提示词工具箱 —— **画风圣经 + 空镜 + 统一负向 + 两路权重**。

这个模块的存在理由：出图提示词原来散在 `image_gen/ai.py`、
`image_gen/portraits.py`、`crew/studio.image_prefix()` 三处，
各拼各的，于是有四个问题（都来自 2026-10-10 的外部调研，
原始出处见 `developers/docs/外部借鉴/03_美术造型道具声音.md`）：

1. **画风只有正向、没有负向**（`STYLE_PROMPT` 是一句正向词）。
   借鉴 **StoryDiffusion** `style_template.py` 的**正/负双模板**结构
   （它把"这部戏长什么样"和"这部戏**绝不能出现**什么"分开存），自己重写。
   ⚠ StoryDiffusion 许可冲突 ⇒ **只学结构，一行代码都没抄**。

2. **负向词只有"无水印"，没有质量词**。借鉴 **InstantID** 的 `n_prompt`
   （代码 Apache-2.0）：补 `lowres / bad anatomy / extra fingers / cross-eyed /
   deformed` 一类**通用质量负向**，与原有的"无水印/无文字"合并成一行。

3. **空镜画不出"没有人"**。借鉴 **StoryDiffusion** 的 `[NC]`（no-character）标记
   思路：空镜（只有物、没有人）时**不叠人物形象段**，否则"更鼓空响"那张图里
   会凭空多出一个人来。

4. **风格与主体是"一条拼死的字符串"**，调"更重画风"还是"更像本人"只能改源码。
   借鉴 **ComfyUI_IPAdapter_plus**（GPL-3.0，**只学原理**）的
   `weight_style / weight_composition` 两路分开的思路：这里拆成
   **风格段 / 主体段**两段，并用一个 `style_boost` 旋钮调风格段的权重。

★ 关于"权重"的一句实话：文生图的提示词**没有真正的数值权重**，
   行业里表达权重的两种土办法是 **位置**（越靠前越重）和 **重复**（同一词组说两遍）。
   所以这里的 `style_boost` 落到实现上就是**把风格词说 1 遍还是 2 遍**，
   并且在文档与判据里都如实这么写 —— 不假装它是个连续可调的力度。

English:
Image generation prompt toolbox —— **style bible + empty shot + unified negative + two-way
weights**.
Reason this module exists: image generation prompts used to be scattered across
`image_gen/ai.py`,
`image_gen/portraits.py`, `crew/studio.image_prefix()` in three places,
each assembling its own, hence four problems (all from external research on 2026-10-10,
1. **Style only has positive, no negative** (`STYLE_PROMPT` is a single positive phrase).
   Borrow **StoryDiffusion** `style_template.py`'s **positive/negative dual template** structure
   (it stores "what this production looks like" and "what this production **must never show**" separately), rewrite it ourselves.
   ⚠ StoryDiffusion license conflict ⇒ **only learn the structure, not a single line of code was copied**.
2. **Negative words only have "no watermark", no quality words**. Borrow **InstantID**'s `n_prompt`
   (code Apache-2.0): add **generic quality negatives** like `lowres / bad anatomy / extra fingers / cross-eyed /
   deformed`, merge with the existing "no watermark/no text" into one line.
3. **Empty shots can't depict "no people"**. Borrow **StoryDiffusion**'s `[NC]` (no-character) marker
   idea: for empty shots (only objects, no people) **do not stack the character appearance section**, otherwise in the "更鼓空响" image
   a person would appear out of nowhere.
4. **Style and subject are "one hard-assembled string"**, to adjust "heavier style" or "more
like the real person" you can only edit the source code.
   Borrow **ComfyUI_IPAdapter_plus** (GPL-3.0, **only learn the principle**) of
   `weight_style / weight_composition` two-way separation idea: here split into
   **style section / subject section** two sections, and use a `style_boost` knob to adjust the weight of the style section.
★ One truth about "weight": text-to-image prompts **have no real numeric weight**,
   the industry's two crude ways to express weight are **position** (further forward = heavier) and **repetition** (say the same phrase twice).
   So here `style_boost` in implementation is just **saying the style words once or twice**,
   and it's honestly written that way in both docs and criteria —— not pretending it's a continuously tunable strength.
"""
from __future__ import annotations

# ── 通用质量负向词（InstantID `n_prompt` 的常见一档，自行整理）──
# [EN] ── Generic quality negative words (a common set for InstantID `n_prompt`, compiled in-house) ──
QUALITY_NEGATIVE = (
    'lowres, blurry, jpeg artifacts, bad anatomy, bad hands, extra fingers, '
    'missing fingers, fused fingers, extra limbs, cross-eyed, deformed, ugly'
)
# ── 本项目原有的"别画出字"那一档（保持原样，别丢）──
# [EN] ── This project's existing "don't draw text" set (keep as-is, don't drop) ──
CLEAN_NEGATIVE = 'no text, no letters, no watermark, no signature, no frame'


def negatives(*, extra: str = '') -> str:
    """一行英文负向词：**质量档 + 干净档 +（可选的）作品自己的忌**。

    两档的来源不同、作用也不同，所以**分开拼、不合着写** ——
    将来想只关掉质量档（比如接了一个不吃负向词的模型）时不必动另一档。
    
        English:
    One line of English negative words: **quality tier + clean tier + (optional) the work's own
    taboos**.
        The two tiers have different sources and different roles, so **assemble separately, don't write them together** ——
        so that later if you want to disable only the quality tier (e.g. when using a model that doesn't accept negative words) you don't have to touch the other tier.
    """
    bits = [QUALITY_NEGATIVE, CLEAN_NEGATIVE]
    e = str(extra or '').strip().strip('.,，。;；')
    if e:
        bits.append(e)
    return ', '.join(bits)


# ══════════════════════════════════════════════════════════════════
#  画风圣经（一部戏一套：正向前缀 + 负向前缀）
# [EN] Style bible (one per production: positive prefix + negative prefix)
# ══════════════════════════════════════════════════════════════════
class StyleBook:
    """这部戏的「美术圣经」。

    `positive` 是**每张图都要带**的画风前缀（例如"彩墨江南、宣纸质感、
    雾气、轻型电影感"）；`negative` 是**每张图都不能出现**的东西
    （例如"现代物件、塑料质感、日式动漫"）——后一半以前根本不存在。

    ⚠ 与 `crew/agents.Art` 的关系：美术指导（Agent）产出的是**内容**
    （画风一句话 + 主色 + 忌），这个类是**把那份内容变成提示词**的地方。
    别把"这部戏什么风格"写死在代码里 —— 它是数据，随作品走。
    
        English:
    This production's "art bible".
        `positive` is the style prefix that **every image must carry** (e.g. "color ink Jiangnan, rice paper texture,
        mist, light cinematic feel"); `negative` is what **every image must not show**
        (e.g. "modern objects, plastic texture, Japanese anime") —— the latter half didn't exist at all before.
        ⚠ Relation to `crew/agents.Art`: what the art director (Agent) produces is **content**
        (a one-line style + main color + taboos), this class is **where that content is turned into prompts**.
        Don't hardcode "what style this production is" in the code —— it's data, it follows the work.
    """

    __slots__ = ('positive', 'negative', 'palette', 'avoid')

    def __init__(self, positive: str = '', *, negative: str = '',
                 palette: list[str] | None = None,
                 avoid: list[str] | None = None) -> None:
        self.positive = str(positive or '').strip()
        self.negative = str(negative or '').strip()
        self.palette = [str(x).strip() for x in (palette or []) if str(x).strip()]
        self.avoid = [str(x).strip() for x in (avoid or []) if str(x).strip()]

    # ── 拼装 ──────────────────────────────────────────────────────
    # [EN] ── Assembly ──────────────────────────────────────────────────────
    def positive_line(self, *, boost: int = 1) -> str:
        """正向前缀。`boost=2` 时把**风格词**再说一遍（见模块头"权重"那段）。
                English:
        Positive prefix. When `boost=2`, repeat the **style words** (see the "weights" section in the
        module header).
        """
        bits = [b for b in (self.positive,) if b]
        if self.palette:
            bits.append('主色：' + '、'.join(self.palette[:3]))
        if not bits:
            return ''
        s = '，'.join(bits)
        if int(boost or 1) >= 2 and self.positive:
            # 重复的只放**风格那一句**，不把主色也念两遍（那是噪音不是权重）
            # [EN] Duplicates only include the **style sentence**, do not recite the main color twice as well
            # [EN] (that's noise, not weight)
            s = f'{s}。{self.positive}'
        return s

    def negative_line(self) -> str:
        """负向前缀：通用质量档 + 干净档 + 这部戏的"忌"。
                English:
        Negative prefix: general quality tier + clean tier + this show's "taboos".
        """
        return negatives(extra='，'.join(self.avoid))

    def is_empty(self) -> bool:
        return not (self.positive or self.palette or self.avoid)

    # ── 从美术指导的产出建（容错：拿不到就返回空圣经，不许编）──
    # [EN] ── Built from the art director's output (fault-tolerant: if unavailable, return an empty bible,
    # [EN] do not fabricate) ──
    @classmethod
    def from_art(cls, art_note) -> 'StyleBook':
        """从 `crew.agents.Art` 的产出（`CrewNote.data`）建一本圣经。

        ★ **拿不到就返回空圣经**（`is_empty()` 为真），由调用方决定加不加 ——
          宁可不加，也别塞一句假的画风要求进用户的作品提示词里。
        
                English:
        Build a bible from the output of `crew.agents.Art` (`CrewNote.data`).
                ★ **If unavailable, return an empty bible** (`is_empty()` is true), and let the caller decide whether to add it --
                  better to add nothing than to stuff a fake art-style requirement into the user's prompt for their work.
        """
        if art_note is None or not getattr(art_note, 'ok', False):
            return cls()
        data = getattr(art_note, 'data', None) or {}
        if not isinstance(data, dict):
            return cls()
        pos = ''
        for k in ('画风', '风格', '画风一句话', 'style'):
            v = str(data.get(k) or '').strip()
            if v:
                pos = v
                break
        if not pos:
            # 有些版本把它写成一句 prompt 前缀，退回用 `prompt_prefix`
            # [EN] Some versions write it as a single prompt prefix; fall back to `prompt_prefix`
            pos = str(getattr(art_note, 'body', '') or '').splitlines()[0][:80]
        pal = data.get('主色') or data.get('palette') or []
        if isinstance(pal, str):
            pal = [x for x in pal.replace('，', ',').split(',')]
        avoid = data.get('忌') or data.get('避免') or []
        if isinstance(avoid, str):
            avoid = [x for x in avoid.replace('，', ',').split(',')]
        return cls(pos, palette=list(pal), avoid=list(avoid))


# ══════════════════════════════════════════════════════════════════
#  组装一条完整提示词
# [EN] Assemble one complete prompt
# ══════════════════════════════════════════════════════════════════
def compose(subject: str, *, book: StyleBook | None = None,
            style_line: str = '', subject_line: str = '',
            place: str = '', time_label: str = '', weather: str = '',
            no_character: bool = False, style_boost: int = 1,
            extra_negative: str = '') -> str:
    """把一幕的要素拼成提示词。

    段落顺序 = 权重顺序（文生图对靠前的词权重大）：

        【主体段（剧组给的美术+道具+人物形象）】【风格段】【地点 / 时辰 / 天气】【负向段】

    ⚠ **主体段必须在最前**（这一条是**原有契约**，判据 `verify_crew.E3` 钉着）：
      剧组给的那段前缀里**本来就含"这部戏长什么样"**（美术的画风与主色），
      它是全局约束，压在后面的具体描述之前才不会被冲淡。
      ★ 我第一版把它排在风格段之后，当场被 E3 打红 —— **别改这里的顺序**。

    `subject_line` 是**人物形象段**（造型 + 随身物，由 `Studio.image_prefix` 给）。
    `no_character=True`（**空镜**）时**整段丢掉** —— 这是它存在的唯一理由。

    ★ 空镜这条**不是锦上添花**：原先是"有人没人都会把人物形象叠上去"，
      于是"更鼓空响""空荡的院子"这类镜头**必然画出人来**，与剧本直接矛盾。
    
        English:
    Assemble one scene's elements into a prompt.
        Section order = weight order (text-to-image weights earlier words more):
            [Subject section (the art + props + character appearance given by the crew)][Style section][Location / time of day / weather][Negative section]
        ⚠ **The subject section must be first** (this is the **existing contract**, nailed down by the criterion `verify_crew.E3`):
          the prefix given by the crew **already contains "what this production looks like"** (the art style and main color),
          It is a global constraint; only by placing it before the specific descriptions that follow will it not be diluted.
          ★ In my first version I put it after the style section and E3 immediately flagged it red -- **do not change the order here**.
        `subject_line` is the **character appearance section** (styling + carried items, provided by `Studio.image_prefix`).
        When `no_character=True` (**empty shot**), the **entire section is dropped** -- this is its sole reason for existing.
        ★ This empty-shot rule is **not a nice-to-have**: originally it was "overlay the character appearance whether or not anyone is present",
          so shots like "the watch drum sounds in vain" or "the empty courtyard" would **inevitably have people drawn in**, directly contradicting the script.
    """
    parts: list[str] = []
    bk = book if isinstance(book, StyleBook) else StyleBook()
    # ① 主体段（剧组前缀）—— 必须最前，见上面那段警告
    # [EN] ① Subject section (crew prefix) —— must be first, see the warning above
    body = str(subject_line or '').strip()
    if body and not no_character:
        parts.append(body)
    # ② 风格段（画风圣经正向前缀；boost=2 时风格句说两遍）
    # [EN] ② Style section (style bible positive prefix; when boost=2 the style sentence is said twice)
    head = style_line or bk.positive_line(boost=style_boost)
    if head:
        parts.append(head)
    # ③ 地点 / 时辰 / 天气
    # [EN] ③ Location / time of day / weather
    scene_bits = [str(subject or '').strip()]
    if place and place != subject:
        scene_bits.append(str(place).strip())
    if time_label:
        scene_bits.append(str(time_label).strip())
    if weather:
        scene_bits.append(f'{weather}天气')
    scene = '，'.join(b for b in scene_bits if b)
    if scene:
        parts.append(scene)
    tail = bk.negative_line() if bk.negative else negatives(extra=extra_negative)
    if bk.negative and extra_negative:
        tail = f'{tail}，{str(extra_negative).strip()}'
    return '；'.join(parts) + f'. {tail}.'


# ══════════════════════════════════════════════════════════════════
#  声音：非语言标记 + 声音名片（第 03 类第 3、6 条）
# [EN] Sound: non-verbal markers + sound profile (category 03 items 3 and 6)
# ══════════════════════════════════════════════════════════════════
#: 非语言标记（借鉴 Bark 的 `[laughs]` 写法，**词表由本项目自定**）。
#: 用途：让对白层能表达"他笑了一下"这种**听得见但写不成字**的东西，
#: 也让"声音"这个职位有一份与"造型"对称的、可核对的产出。
# [EN] : Non-verbal markers (borrowing Bark's `[laughs]` convention, **the word list is defined by this
# [EN] project**).
# [EN] : Purpose: let the dialogue layer express things like "he laughed" that are **audible but not
# [EN] writable as text**,
# [EN] : and also give the "sound" role a checkable output symmetric with "styling".
NONVERBAL = {
    '咳': '咳', '笑': '笑', '冷笑': '冷笑', '叹': '叹气', '哼': '哼',
    '喘': '喘气', '沉默': '沉默', '顿': '停顿', '颤': '声音发颤',
    '低': '压低声', '哑': '嗓音发哑',
}
#: 声音名片的字段 —— 每个角色一份，**跨天不许变**（否则第一天沙哑第二天清亮）
# [EN] : Fields of the sound profile —— one per character, **must not change across days** (otherwise
# [EN] hoarse on day one and clear on day two)
VOICE_CARD_FIELDS = ('音色', '语速', '口音', '常用语', '非语言')


def voice_card_rows(data: dict | None) -> list[dict]:
    """把「声音」职位的产出规整成**声音名片**行（缺字段就留空，不编）。
        English:
    Normalize the output of the "sound" role into **sound card** lines (leave blank for missing
    fields, do not invent).
    """
    rows = (data or {}).get('角色声音') or (data or {}).get('声音名片') or []
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        nm = str(r.get('人名') or r.get('角色') or '').strip()
        if not nm:
            continue
        row = {'人名': nm}
        for f in VOICE_CARD_FIELDS:
            row[f] = str(r.get(f) or '').strip()
        out.append(row)
    return out


def event_sounds(data: dict | None) -> list[str]:
    """事件声 —— 固定成**短名词短语**（第 03 类第 6 条）。

    来历：AudioGen / AudioCraft 的建议是"要生成一段声音，提示词写**短名词短语**
    最稳"（`['茶盏磕在木桌', '算盘珠子轻拨']`），写成整句叙述反而生成不出东西。
    这里**在入口就把它规整短**，而不是等将来接音频时才想起来 ——
    因为产出这一栏的是 LLM，它默认爱写整句。
    
        English:
    Event sound -- fixed as a **short noun phrase** (category 03, item 6).
        Origin: AudioGen / AudioCraft's recommendation is that "to generate a sound, write the prompt as a **short noun phrase**
        for the most reliable results" (`['tea cup clinks on wooden table', 'abacus beads lightly clicked']`); writing it as a full narrative sentence instead produces nothing.
        Here we **normalize it to short right at the entry point**, rather than waiting until audio integration to remember --
        because the one producing this column is the LLM, which by default loves to write full sentences.
    """
    raw = (data or {}).get('事件声') or []
    if isinstance(raw, str):
        raw = [x for x in raw.replace('；', ';').replace('，', ',').replace(';', ',').split(',')]
    out: list[str] = []
    for x in raw:
        s = str(x or '').strip().strip('。;；,，')
        if not s:
            continue
        # 砍掉"的"字定语与"传来…声音"这种叙述壳，只留名词短语
        # [EN] Cut the "的" attributives and narrative shells like "传来…声音", keep only noun phrases
        for shell in ('传来', '响起', '听到了', '好像', '似乎'):
            if shell in s:
                s = s.split(shell, 1)[-1]
        s = s.strip('的了着')
        out.append(s[:24])
    return out[:3]
