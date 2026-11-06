# -*- coding: utf-8 -*-
"""剧本式输出：把运行时的原始材料拼成一幕幕剧本。

这里是「同一时刻不同人在做不同事」真正被处理的地方。

输入是**每个 tick 的全部动作**（不是逐个），因为"同时"这个信息只在
「一次拿到整组动作」时才能看出来。以前的写法是逐个 append 成字符串，
于是并行变成了先后 —— 这是这次改造要修的核心问题。

同时性的三级处理
----------------
1. **同场同时**（都在这场戏的地点上）→ 一条 `PARALLEL`，每人一条轨
2. **异地同时**（有人在这个地点之外）→ 先 `CUT` 切过去，给那边的轨，
   再 `CUT_BACK` 切回来。屏幕上标「同一时刻」
3. **单人**（这一 tick 只有一个人动）→ 不套「同时」，直接是动作/对白
   （只有一个人做事却说"同时"，反而怪）

另外解决的两件事
----------------
* **出场/退场**：每 tick 与上一 tick 的在场集合做 diff，自动生成。
* **人物在做事而不是一直说话**：每个 Action 都变成 `ACTION` 词条，
  带主体；`SceneScript.actors()` 与 `speakers()` 的差集就是"在场但没开口的人"，
  界面上因此能看出"谁一句话没说，但一直在做事"。

出处分两处可见：幕首的「本幕依据」（节点/伏笔）与词条级 `anchors`。
这样"每个人按自己的设定和目标行事"就不只是 prompt 里的约束，而是**看得见**的。

English:
Script-style output: assemble the raw runtime material into scene-by-scene scripts.
This is where "different people doing different things at the same moment" is actually handled.
The input is **all actions for each tick** (not one by one), because the information of
"simultaneity" can only be
seen when "the whole group of actions is obtained at once". The previous approach appended them
one by one into a string,
so parallelism became sequential order — this is the core problem this refactor fixes.
Three levels of handling simultaneity
----------------
1. **Same location, same time** (all at this scene's location) → one `PARALLEL`, one track per person
2. **Different locations, same time** (someone is outside this location) → first `CUT` over, give that side's track,
   then `CUT_BACK` back. Mark "same moment" on screen
3. **Single person** (only one person acts this tick) → do not wrap in "simultaneous", just action/dialogue
   (saying "simultaneous" when only one person is doing something is actually odd)
Two other things solved
----------------
* **Entrance/exit**: diff each tick's present set against the previous tick's, generate automatically.
* **Characters doing things rather than always talking**: every Action becomes an `ACTION` entry,
  with a subject; the difference between `SceneScript.actors()` and `speakers()` is "people present but not speaking",
  so the UI can show "who hasn't said a word but has been doing things all along".
Provenance is visible in two places: the scene-opening "basis for this scene"
(nodes/foreshadowing) and entry-level `anchors`.
This way "each person acts according to their own settings and goals" is not just a constraint
in the prompt, but **visible**.
"""
from __future__ import annotations

import difflib as _difflib
import hashlib
from typing import Any

from config import CFG
from display import script as S
from util.text import norm_line as _norm_line, bare_detail as _bare_detail

_LOG = __import__("logging").getLogger("nws.script")

# 一幕最多几张图。图是点缀不是主体，而且一屏挤三张图会把文字挤下去。
# [EN] At most a few images per act. Images are decoration, not the main body, and cramming three
# [EN] images into one screen pushes the text down.
MAX_IMAGES_PER_SCENE = 2

# ── 情绪 → 语气提示（从真实情绪状态推，不编造）──
# [EN] ── Emotion → tone hint (inferred from real emotional state, not fabricated) ──
_EMOTION_TONE = (
    ('anger', 0.55, '语气不善'),
    ('fear', 0.55, '声音发紧'),
    ('sadness', 0.55, '声音低下去'),
    ('happiness', 0.65, '语气轻快'),
    ('surprise', 0.6, '一怔'),
)

# ── 环境句库：按（时段, 天气档）取，确定性挑选 ──
# 只写"由真实状态推出来的"句子（时段和天气都是 WorldState 里的真值），
# 不用它编造剧情。想关掉就 SCRIPT_AMBIENT=false。
# [EN] ── Ambient sentence pool: selected by (time period, weather tier), deterministic selection ──
# [EN] Only write sentences "derived from real state" (time period and weather are both true values in
# [EN] WorldState),
# [EN] don't use it to fabricate plot. To turn it off, set SCRIPT_AMBIENT=false.
_AMBIENT: dict[tuple[str, str], list[str]] = {
    ('清晨', '雨'): ['雨还在下，瓦沟里的水一线一线地淌。',
                     '檐水砸在阶石上，声音比昨夜更密。'],
    ('清晨', '晴'): ['天刚亮透，远处屋脊上浮着一层薄薄的日光。',
                     '日头刚爬上墙头，潮气还没散。'],
    ('上午', '雨'): ['雨丝斜着扫过院子，青石板湿得发亮。',
                     '雨不大，却一直不停。'],
    ('上午', '晴'): ['日头渐高，街上的水汽一点点蒸散。',
                     '天光敞亮，屋里的影子短了下去。'],
    ('晌午', '雨'): ['雨里天色发暗，像傍晚提前来了。',
                     '雨敲着檐角，屋里比外头还闷。'],
    ('晌午', '晴'): ['日头正毒，屋里静得听得见苍蝇。',
                     '正午的光从窗纸透进来，落成一块白。'],
    ('午后', '雨'): ['雨声渐缓，只剩檐下一滴一滴地落。',
                     '雨势收了些，天色仍旧压着。'],
    ('午后', '晴'): ['午后日影斜长，屋里浮着细小的尘埃。',
                     '光从窗棂斜进来，照见半张桌面。'],
    ('傍晚', '雨'): ['天色一点点沉下去，雨还在下。',
                     '暮色混着雨气，屋里的东西都看不清了。'],
    ('傍晚', '晴'): ['日头压到屋脊后头，屋里暗下来。',
                     '天色将暮，远处有人在收摊。'],
    ('入夜', '雨'): ['雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃。',
                     '夜里的雨声比白天更清楚。'],
    ('入夜', '晴'): ['夜色落下来，屋里那盏灯显得格外亮。',
                     '入了夜，街上的人声一点点稀了。'],
    ('深夜', '雨'): ['雨声里，更鼓显得很远。',
                     '夜深了，雨还没停。'],
    ('深夜', '晴'): ['夜深，只余更鼓一声一声。',
                     '屋里静下来，只剩灯芯偶尔炸响。'],
    ('凌晨', '雨'): ['天没亮，雨声是唯一的动静。',
                     '雨下了一夜，地上的水积了浅浅一层。'],
    ('凌晨', '晴'): ['天将亮未亮，屋外一片铁青。',
                     '夜最黑的时候，远处有一两声犬吠。'],
}


def _weather_bucket(weather: str) -> str:
    """把天气文本归到「雨 / 晴」两档（环境句库只需要这两档）。
        English:
    Classify weather text into two buckets "rain / clear" (the environment sentence bank only needs
    these two).
    """
    w = (weather or '').strip()
    if any(ch in w for ch in ('雨', '雪', '雷', '雾')):
        return '雨'
    return '晴'


#: 判"是不是同一句话"的相似度门槛（`difflib` 比值，0~1）。
#: 0.86 是量出来的：《雪国》那轮「脸埋回臂弯」/「下巴抵回臂弯」这类
#: **换个动词的同一动作**约 0.55（够不着，靠 `[你上一拍做的]` 挡）；
#: 而「你那车份儿打算拖到什么时候」/「车份儿打算拖到什么时候」约 0.92。
#: ⚠ 剧本模式（`SceneBuilder.already_said`）与 prose 模式（`sim/loop._repeat_hit`）
#:   都读这一个常量 —— 两处各写一个数，迟早一个改了一个没改。
# [EN] Threshold for "is this the same sentence" (`difflib` ratio, 0..1). 0.86 is measured.
# [EN] ⚠ Both the script mode (`SceneBuilder.already_said`) and prose mode
# [EN] (`sim/loop._repeat_hit`) read this single constant.
SAID_NEAR = 0.86


def norm_line(text: str) -> str:
    """去掉标点与空白，只留字 —— 判"是不是同一句"用（真身在 `util.text.norm_line`）。

    ★ 2026-10-18 挪进 `util/text.py`：`crew/review` 的重复候选扫描也要用它，
      而 crew 不该 import display（会形成反向依赖）。这里留一层薄别名，
      是为了既有调用点（`scene_builder.norm_line` / `SceneBuilder._norm_line`）一行不改。
    [EN] Moved into `util/text.py` on 2026-10-18: the duplicate-candidate scan in `crew/review`
    [EN] needs it too, and crew must not import display (reverse dependency). This thin alias keeps
    [EN] existing call sites unchanged.
    """
    return _norm_line(text)


def near_same(a: str, b: str, *, min_len: int = 4) -> bool:
    """两句话是不是"换个说法说同一件事"（2026-10-18）。

    为什么需要（《雪国》/`ltxz-01` 实测）：模型复读时很少一字不差，它会把语序
    挪一下、漏两个字 ——「你那车份儿打算拖到什么时候？」→「车份儿打算拖到什么时候」；
    精确比对放过去，读起来完全是"他又说了一遍"。
    ⚠ 归一化后 < `min_len` 字的**不判**：`嗯`/`走吧` 这种本来就是口语里反复出现的，
      判成重复会把正常应答也拦掉。

    [EN] Are these two lines "the same thing in different words" (2026-10-18)?
    [EN] Why needed: the model rarely repeats verbatim; it reorders or drops a couple of characters,
    [EN] and exact comparison lets it through while it reads exactly like saying it again.
    [EN] ⚠ Lines shorter than `min_len` after normalization are **not** judged: "mm" / "let's go"
    [EN] are what people genuinely repeat.
    """
    na, nb = norm_line(a), norm_line(b)
    if len(na) < min_len or len(nb) < min_len:
        return False
    if na == nb:
        return True
    longest = max(len(na), len(nb))
    if abs(len(na) - len(nb)) > longest * 0.5:
        return False
    return _difflib.SequenceMatcher(None, na, nb).ratio() >= SAID_NEAR


#: 明显**在户外/市井**才成立的环境句用词。罐头池是写死的 32 句，全是中式市井意象；
#: 用在封闭空间（舱室、殿内、屋里）或现代/科幻世界里就错位。
#: 实测（2026-10-18《回声站》，深空中继站的**密封值班室**里）：
#: 「日头渐高，街上的水汽一点点蒸散」「天光敞亮，屋里的影子短了下去」——
#: 一个在深空、没有街也没有太阳的地方。
# [EN] Words that only work **outdoors / in a street**. The canned pool is 32 hardcoded lines, all
# [EN] Chinese market-town imagery; inside a sealed room or in a modern/sci-fi world they land wrong.
# [EN] Measured on 2026-10-18 in 《回声站》 (a sealed duty room on a deep-space relay): "the sun
# [EN] climbs and the street's damp evaporates" -- in deep space, with no street and no sun.
_OUTDOOR_WORDS = ('街', '巷', '院子', '屋脊', '墙头', '摊', '田', '路人')
#: 只在**非现代**日历下成立（"更鼓"是古代报时器物）。
#: 实测：《雪国》(日式温泉旅馆)、《回声站》(深空) 都出现过"更鼓一声一声"，两轮都被评委记成时代错置。
# [EN] Only valid under a **non-modern** calendar ("night watch drum" is an ancient timekeeping
# [EN] instrument). Measured: both 《雪国》 (a Japanese inn) and 《回声站》 (deep space) got "a night
# [EN] watch drum, one beat after another"; the judge called it an era mismatch both times.
_ANCIENT_ONLY = ('更鼓', '瓦沟', '檐瓦')
#: 场景名里出现这些字 ⇒ 认定**在室内**（宁可偶尔误判成室内，也不要在舱里说街上的水汽）。
# [EN] If the scene name carries one of these, treat it as **indoors**.
_INDOOR_WORDS = ('室', '房', '殿', '堂', '厅', '舱', '屋', '楼', '店', '馆',
                 '帐', '塔', '厢', '舍', '内', '间')
#: **"天光"类** —— 现代/科幻的室内是灯，不是天光（密封舱连窗都没有）。
#: 古风室内用"天光从窗纸透进来"是成立的，所以这一条只在 `indoor and modern` 时生效。
# [EN] "Daylight" words: a modern / sci-fi interior is lit by lamps, not daylight (a sealed module
# [EN] has no window at all). In an old-style interior "daylight through the paper window" is fine,
# [EN] so this only applies when `indoor and modern`.
_SKY_WORDS = ('天光', '日头', '日光', '日影', '暮色', '天色')
#: 只在**室内**成立的那半（反向：室外场景不该说"屋里"）。
#: 实测：判"是不是室内"只看场景名，而"茶峒·河街河边"这种**室外**场景拿到了
#: 「天光敞亮，屋里的影子短了下去」—— 河边没有屋里的影子。
# [EN] The other direction: only valid **indoors** (an outdoor scene must not say "inside the
# [EN] room"). Measured: "茶峒·河街河边" (an outdoor scene) received "daylight is bright, the shadows
# [EN] inside the room have shortened" -- there is no room by the river.
_INDOOR_ONLY = ('屋里', '屋内', '堂前', '桌面', '窗纸', '窗棂', '灯芯')


def _ambient_ok(line: str, *, indoor: bool, modern: bool) -> bool:
    """这一句罐头环境句**放在当前场景里成立吗**。

    三条判断（零成本，全用词表）：
      · 室内场景 ⇒ 不收"街上/院子/屋脊/摊"这类只在外面才看得见的句子；
      · 现代/科幻（`calendar == 'modern'`）⇒ 不收"更鼓/瓦沟/檐瓦"这类古代器物；
      · 其余照旧。
    ⚠ 判断**从宽**：只排除明确不成立的，拿不准就留着 —— 少一句环境句没什么，
      写错一句（舱里出现日头）读者立刻出戏。
    [EN] Does this canned ambient line **hold in the current scene**? Three list-based checks:
    [EN] indoors => drop lines only visible outside; modern calendar => drop ancient instruments;
    [EN] otherwise keep. ⚠ Deliberately lenient: only clearly-wrong lines are dropped -- one fewer
    [EN] ambient line costs nothing, one wrong line (a sun inside a sealed module) breaks the spell.
    """
    t = str(line or '')
    if indoor and any(w in t for w in _OUTDOOR_WORDS):
        return False
    if modern and any(w in t for w in _ANCIENT_ONLY):
        return False
    if indoor and modern and any(w in t for w in _SKY_WORDS):
        return False
    if not indoor and any(w in t for w in _INDOOR_ONLY):
        return False
    return True


def _stable_pick(items: list[str], *seed_parts: Any) -> str:
    """按种子确定性挑选 —— 同一天同一时段重跑结果一致，便于复现与测试。
        English:
    Select deterministically by seed — rerunning the same time period on the same day gives
    consistent results, easing reproduction and testing.
    """
    if not items:
        return ''
    key = '|'.join(str(p) for p in seed_parts)
    h = int(hashlib.md5(key.encode('utf-8')).hexdigest()[:8], 16)
    return items[h % len(items)]


class SceneBuilder:
    """把运行时的动作/事件/反思攒成一幕幕剧本。
        English:
    Assemble runtime actions/events/reflections into scene-by-scene scripts.
    """

    def __init__(self, world: Any, *, day: int = 1,
                 image_hook: Any = None,
                 initial_scenes: list | None = None):
        """`initial_scenes` = **今天已经写好的那几幕**（续跑时才给）。

        ★ 为什么要有它（2026-10-08 用户要的"从某一天某个时间继续"）：
          上一轮在一天演到一半时被停，收尾**补落**过一份当天的稿子
          （`RunLoop._finish` → `_end_day`）。这一轮接着写**同一天**，
          如果从空的幕列表起，收工落盘时会**整个覆盖**那份 ——
          那一天的前半段就没了。
          把旧幕放在前面，新的幕接在后面，落盘出来的就是**完整的这一天**。

        ⚠ 两件必须跟着做的事（不然续跑会"重来一遍"）：
          · `_known_cast` 要填上**旧幕里出现过的人** ——
            它决定"这个人是不是第一次出场"（`_sync_cast` 的
            `first_ever`），不填的话续跑第一拍会把每个人再"入画"
            介绍一遍（用户在别处报过"人物介绍讲两遍"）；
          · `_said` / `_last_action` 也照填 —— 否则"上一轮已经说过的
            那句话"会被去重护栏放过去（它只认得本轮记过的）。
        
                English:
        `initial_scenes` = **the scenes already written today** (only provided when resuming).
                ★ Why it is needed (2026-10-08, user wants "continue from a certain time on a certain day"):
                  The previous round was stopped halfway through a day, and wrap-up **patched in** a draft of that day
                  (`RunLoop._finish` → `_end_day`). This round continues writing **the same day**;
                  if starting from an empty scene list, the wrap-up persist will **entirely overwrite** that draft —
                  and the first half of that day is gone.
                  Put the old scenes in front, append the new scenes after, and what gets persisted is **the complete day**.
                ⚠ Two things that must be done along with it (otherwise resuming will "start over"):
                  · `_known_cast` must be filled with **the people who appeared in the old scenes** —
                    it determines "whether this person is appearing for the first time" (`_sync_cast`'s
                    `first_ever`); if not filled, the first beat of the resume will "enter frame" and
                    introduce everyone again (the user has reported "character introductions said twice" elsewhere);
                  · `_said` / `_last_action` must also be filled — otherwise "the line already said
                    last round" will slip past the dedup guard (it only recognizes what was recorded this round).
        """
        self.world = world
        self.day = day
        self._scenes: list[S.SceneScript] = list(initial_scenes or [])
        self._cur: S.SceneScript | None = None
        self._known_cast: set[str] = set()      # 曾经在场过的人（首次出场判定）
        # [EN] People who were once present (first-appearance determination)
        self._prev_cast: set[str] = set()
        # image_hook(kind, name_or_place[, ctx]) -> 图片绝对路径；由调用方注入，
        # 这样这一层不依赖 image_gen，也方便测试时关掉。
        # `ctx` 是这一幕的上下文（地点/天气/时段/在场人数）—— 有了它，
        # 插图才能"渡口下着雨"和"堂内"画得不一样（hook 支持 ctx 时才传，
        # 两参的老 hook 照旧能用）。
        # [EN] image_hook(kind, name_or_place[, ctx]) -> absolute image path; injected by the caller,
        # [EN] so this layer does not depend on image_gen, and it's easy to turn off during testing.
        # [EN] `ctx` is the context of this act (location/weather/time period/number of people present) — with
        # [EN] it,
        # [EN] illustrations can render "rain at the ferry crossing" and "inside the hall" differently (pass
        # [EN] ctx only when the hook supports it,
        # [EN] two-arg old hooks still work as before).
        self._image_hook = image_hook
        self._hook_takes_ctx = bool(getattr(image_hook, 'takes_ctx', False)) \
            if image_hook else False
        self._last_place = ''                 # 上次出场景图的地点（避免每幕重复出）
        self._img_count: dict[int, int] = {}  # 幕 → 已出图数（按 id 计）
        #: ★★★ 2026-10-17：这一天**已经写过的环境句**（用来防"同一句反复刷"）。
        #   实测一次真实运行：3453 字的一天里有 **11 条环境白描，去重后只有 1 种**
        #   （91% 是同一句 `茶炉顶盖噗噗轻跳…井水该回的那一声，没回` 逐字重复）。
        #   真人小说不会这么写 —— 这不是"氛围"，是排版噪声。
        #   根因在 `_stable_pick` 的种子：它只带 `self.day`，同一天算出来永远是同一条；
        #   而 `Sound` 明明写了 **3 条**事件声，一整天只用了其中 1 条。
        # [EN] ★★★ 2026-10-17: the ambient lines **already written today** (to stop the same
        # [EN] sentence being emitted over and over). Measured on one real run: a 3453-character day
        # [EN] had **11 ambient lines that deduplicated to 1** (91% verbatim repeats of the same
        # [EN] sentence). A human novel doesn't write like that -- this is not "atmosphere", it is
        # [EN] typographic noise. Root cause is `_stable_pick`'s seed: it only carries `self.day`, so
        # [EN] the same day always yields the same line; and `Sound` had written **3** event sounds,
        # [EN] only 1 of which was ever used.
        # ★★★ 2026-10-18：从"**用过就永不**"改成"**隔 N 条可复现**"。
        #   旧行为：`set` + "全部用过 ⇒ 返回空串"，而候选池实测只有 **1–5 条**
        #   （空 `sound_design` 时 1 条，写了三条事件声也才 5 条）⇒
        #   **一天最多 5 条环境白描**。长跑 1000 拍也只有 5 条，
        #   而 `AMBIENT_MINUTES` 明明写着"每 1 故事分钟一条" —— 那是个假旋钮。
        #   实测印证：6 拍 54 条条目里只有 **1 条** `ambient`（真人样本约 20% 的句子
        #   是环境/体感）。
        #   ⇒ 值改成"**上次是第几次取句**"，冷却 `AMBIENT_REPEAT_EVERY` 条之后
        #     同一句可以回来；冷却期内仍然"宁可不写"（不刷屏这条 2026-10-17 的修复保留）。
        #   ⚠ 但别指望罐头池提供文学性：真正的"空气"主要由演员的 `细节` 承担，
        #     这里只是**兜底**（空场、冷场、没人动的时候）。
        # [EN] ★★★ 2026-10-18: from "**used once, never again**" to "**reappears after N lines**".
        # [EN] Old behavior: a `set` + "all used => return empty", while the candidate pool is
        # [EN] measured at **1-5 lines** (1 with an empty `sound_design`, 5 even with three event
        # [EN] sounds) => **at most 5 ambient lines per day**. A long run of 1000 beats still got 5,
        # [EN] while `AMBIENT_MINUTES` claims "one every story minute" -- a fake knob.
        # [EN] Measured: 6 beats / 54 entries had exactly **1** `ambient` line (a human sample is
        # [EN] about 20% environment/body-sensation sentences).
        # [EN] => value becomes "**the sequence number when it was last used**", so a line can come
        # [EN] back after `AMBIENT_REPEAT_EVERY` lines; within the cooldown it still writes nothing
        # [EN] (the 2026-10-17 "never spam" fix is kept).
        # [EN] ⚠ Do not expect literary quality from a canned pool: the real "air" comes from the
        # [EN] actor's `细节`; this is only a **fallback** (empty scenes, cold scenes, nobody moving).
        self._ambient_used: dict[str, int] = {}
        #: 取过多少次环境句（当"时间轴"用；`AMBIENT_REPEAT_EVERY` 与它相减就是冷却）
        # [EN] How many ambient lines were drawn (used as a time axis)
        self._ambient_seq = 0
        # 已经"交代过"的 (kind, key)：肖像**整轮只出一次图**
        # （入画→离场→再入画不该重复刷同一张脸）。
        # [EN] Location of the last scene image (avoid repeating every act)
        # [EN] Act → number of images already produced (counted by id)
        # [EN] Already "accounted for" (kind, key): a portrait **is only illustrated once per whole run**
        # [EN] (entering → leaving → re-entering should not repeatedly refresh the same face).
        self._imagined: set[tuple[str, str]] = set()
        # ── 去重护栏（2026-10-07 加）──────────────────────────────────
        # 用户报的「有点乱了」有两半：满屏「同时」，以及**重复**——
        # 实测 `第001天.md` 里丁那句「账差七文」一字不差地出现了 **4 次**
        # （105 / 111 / 163 / 166 行），而「转向阿福」这种小动作反复刷。
        # [EN] ── Dedup guardrails (added 2026-10-07) ──────────────────────────────────
        # [EN] The user's report of "it's getting a bit messy" has two halves: a screen full of "at the same
        # [EN] time", and **repetition**——
        # [EN] In actual testing, Old Chen's line "the accounts are off by seven wen" in `第001天.md` appeared
        # [EN] verbatim **4 times**
        # [EN] (lines 105 / 111 / 163 / 166), while small actions like "turns toward A'fu" kept getting
        # [EN] refreshed.
        #
        # 根因不是模型笨，是**每拍都要输出一条**：一天几百拍、人物目标不变，
        # 模型只能把同一件事再讲一遍。所以护栏放在这里（内容出口），
        # 比改 prompt 可靠——prompt 管不住"第 87 拍时它还记得自己说过什么吗"。
        self._last_action: dict[str, str] = {}   # 人名 → 上一拍的动作文本
        self._last_gesture: dict[str, bool] = {}  # 人名 → 上一拍是不是"纯手势"
        self._said: set[tuple[str, str]] = set()  # (人名, 台词) 已说过的
        #: 归一化台账（人名 → 去过标点的台词，按说出的先后）。**与 `_said` 同步写**
        #: （唯一写入口见 `_remember_line`）—— 近似判定靠它（`_near_said`）。
        # [EN] : Normalized ledger (name -> line with punctuation stripped, in the order spoken).
        # [EN] Written **in sync with** `_said` (single write entry: `_remember_line`) -- the
        # [EN] near-duplicate check relies on it (`_near_said`).
        self._said_norm: dict[str, list[str]] = {}
        # ★ **"必须重复"的放行名单**（2026-10-07 加）。
        #   用户报了另一面：「如果说了一样的话，你要看下是不是必须，如果不是
        #   必须重复，就让人物重新想清楚当前情况，重新说话」。
        #   —— 去重护栏只认得"一模一样"，它分不清"模型偷懒复读"和
        #   "这句话非说不可"。所以加一条通路：人物被要求**重说**之后若仍坚持
        #   原话（见 `sim/loop._review_repeat`），就把这句登记在这里放行。
        # [EN] The root cause is not that the model is dumb, it's that **every beat must output a line**:
        # [EN] several hundred beats a day, character goals unchanged,
        # [EN] the model can only tell the same thing again. So the guardrail goes here (the content exit),
        # [EN] which is more reliable than changing the prompt — the prompt can't control "does it still
        # [EN] remember what it said at beat 87".
        # [EN] Person name → action text of the previous beat
        # [EN] Person name → whether the previous beat was a "pure gesture"
        # [EN] (person name, line) already said
        # [EN] ★ **Whitelist of "must repeat"** (added 2026-10-07).
        # [EN] The user reported the other side: "If the same thing is said, you should check whether it's
        # [EN] necessary; if not
        # [EN] necessary to repeat, have the character rethink the current situation and speak again".
        # [EN] —— The dedup guardrail only recognizes "exactly identical"; it can't distinguish "the model is
        # [EN] being lazy and repeating" from
        # [EN] "this line must be said". So add a path: after a character is asked to **restate**, if they
        # [EN] still insist on
        # [EN] the original words (see `sim/loop._review_repeat`), register this line here to let it pass.
        self._forced: set[tuple[str, str]] = set()
        if self._scenes:
            self._learn_from(initial_scenes)

    def _learn_from(self, scenes: list) -> None:
        """从**已经写好的那几幕**里把三样东西学回来（续跑专用，见 `__init__`）。

        不学的话续跑会出现三种"重来一遍"：每个人再入一次画、已经说过的台词
        再护栏外说一次、同一个动作再刷一遍 —— 全都因为护栏的记性从这一轮才起。
        
                English:
        Learn three things back from **the scenes already written** (resume-only, see `__init__`).
                Without learning them, resuming will produce three kinds of "start over": everyone enters frame again, lines already said
                get said again outside the guard, the same action gets replayed again — all because the guard's memory only starts from this round.
        """
        for sc in (scenes or []):
            for name in (getattr(sc, 'cast', None) or []):
                if str(name).strip():
                    self._known_cast.add(str(name))
            for e in (getattr(sc, 'entries', None) or []):
                who = str(getattr(e, 'speaker', '') or '').strip()
                if who:
                    self._known_cast.add(who)
                text = str(getattr(e, 'text', '') or '').strip()
                kind = str(getattr(e, 'kind', '') or '')
                if not who:
                    continue
                if kind == S.DIALOGUE and text:
                    self._remember_line(who, text)
                    self._last_action[who] = f'说：{text}'
                elif kind == S.ACTION and text:
                    self._last_action[who] = text

    # ══════════════════════════════════════════════════════════
    #  幕的开关
    # [EN] Act switch
    # ══════════════════════════════════════════════════════════
    @property
    def current(self) -> S.SceneScript | None:
        return self._cur

    @property
    def scenes(self) -> list[S.SceneScript]:
        return list(self._scenes)

    def _cast_now(self) -> list[str]:
        """此刻"在这场戏里"的人：在场的人（含后台人物）。

        后台人物也算在场 —— 他们不说话、不主动行动，但**确实在**，
        这正是"人物不是一直说话"的一种形态，屏幕上应该看得到。

        ★ 「位置算不算在这一场里」**复用 `WorldState._loc_matches`**（2026-10-07）：
          这里原来自己写了一遍 `loc == scene`，比那边**严** —— 人物在同一场戏里
          挪到「柜台后」「后院」，这边当他**离场**（屏幕上打出「离场」），
          而 `world.is_on_stage` 那边还算他在场。两套判定不一致的后果是
          "同一刻两处说法不一样"，而且人一被打成离场就整轮不再出场。
          判定只该有一处：`world/state.py`。
        
                English:
        People "in this scene" right now: those present (including background characters).
                Background characters count as present too — they do not speak or act on their own, but they **really are** there,
                and this is exactly one form of "characters do not always talk"; it should be visible on screen.
                ★ "Whether the location counts as within this scene" **reuses `WorldState._loc_matches`** (2026-10-07):
                  here it used to have its own copy of `loc == scene`, which was **stricter** than that side — a character in the same scene
                  moving to "behind the counter" or "the backyard" was treated here as **leaving the stage** (the screen printed "exit"),
                  while `world.is_on_stage` still counted them as present. The consequence of two inconsistent judgments is
                  "the same moment described differently in two places", and once a person is marked as exited they no longer appear for the whole round.
                  The judgment should exist in only one place: `world/state.py`.
        """
        scene = (getattr(self.world, 'scene', '') or '').strip()
        people = getattr(self.world, 'people', {}) or {}
        loc_ok = getattr(self.world, '_loc_matches', None)
        out: list[str] = []
        for name, ps in people.items():
            if getattr(ps, 'status', '在场') != '在场':
                continue
            if callable(loc_ok):
                if loc_ok(ps):
                    out.append(name)
                continue
            # 兑底（假 world，没有 `_loc_matches` 时）：老规矩
            # [EN] Fallback (fake world, when there is no `_loc_matches`): same as before
            loc = (getattr(ps, 'location', '') or '').strip()
            if not loc or not scene or loc == scene:
                out.append(name)
        return out

    def begin_scene(self, *, force: bool = False) -> S.SceneScript:
        """开新的一幕（默认若当前幕还有内容就先收尾）。
                English:
        Open a new scene (by default, if the current scene still has content, wrap it up first).
        """
        if self._cur is not None and not force:
            return self._cur
        if self._cur is not None:
            self._scenes.append(self._cur)

        clock = getattr(self.world, 'clock', None)
        time_label = ''
        if clock is not None:
            time_label = f'{clock.shichen} {clock.hhmm()}'

        place = (getattr(self.world, 'scene', '') or '').strip()
        cast = self._cast_now()

        scene = S.SceneScript(
            time_label=time_label,
            place=place,
            place_desc=(getattr(self.world, 'scene_desc', '') or '').strip(),
            weather=(getattr(self.world, 'weather', '') or '').strip(),
            cast=cast,
            day=self.day,
            node=(getattr(self.world, 'current_node', '') or ''),
            tension_before=float(getattr(self.world, 'tension', 0.0) or 0.0),
        )
        node_info = None
        if hasattr(self.world, 'current_node_info'):
            try:
                node_info = self.world.current_node_info()
            except Exception:
                node_info = None
        if isinstance(node_info, dict):
            # ★★★ 2026-10-26：**读 `名称`，不是 `name`**。
            #   进度节点表是 `ingest.progress.ProgressNode.to_dict()` 出来的，
            #   键是中文（`名称/概要/完成判据/状态/跨度/篇幅`）—— 这里原来写的是
            #   `node_info.get('name')`，永远取到 None ⇒ 每一幕的 `node_name` 都是空串
            #   （实测望江楼那份 `第001天.json`：133 幕 **133 个空串**）。
            #   后果是整条"按情节单元写"的路静默退化成"一个单元、全按中档"，
            #   而 `_day_lines` 的幕头也就永远不带站名。
            #   ⚠ 保留 `name` 作兜底：外部服务/老存档里可能真的是英文键。
            # [EN] ★★★ 2026-10-26: **read `名称`, not `name`**. The progress table comes from
            # [EN] `ProgressNode.to_dict()`, whose keys are Chinese. The old `get('name')` always
            # [EN] returned None, so every act's `node_name` was an empty string (measured: 133 of
            # [EN] 133 empty in a real `第001天.json`), silently degrading "write by plot unit" to
            # [EN] "one unit, medium tier". `name` stays as a fallback for external services and
            # [EN] older saves that really do use English keys.
            scene.node_name = str(node_info.get('名称') or node_info.get('name') or '')

        # 环境句：由真实时段与天气推出（可关）
        # [EN] Ambient sentences: derived from real time period and weather (can be turned off)
        if not scene.place_desc and CFG.b('SCRIPT_AMBIENT'):
            segment = clock.segment() if clock is not None else '上午'
            bank = _AMBIENT.get((segment, _weather_bucket(scene.weather)))
            if bank:
                scene.place_desc = _stable_pick(bank, self.day, segment,
                                                scene.weather, place)

        # 幕首插图：只在**地点变化**时给一张场景图（Pillow 生成，零成本）。
        # 同一地点连着几幕不重复出——图是标记"换地方了"，不是每幕的装饰。
        # [EN] Act-opening illustration: give a scene image only when the **location changes** (generated by
        # [EN] Pillow, zero cost).
        # [EN] Consecutive acts at the same location are not repeated — the image marks "changed place", not
        # [EN] decoration for every act.
        if place and place != self._last_place:
            self._maybe_image(scene, kind='scene', key=place, caption=place,
                              at_head=True)
            self._last_place = place

        self._cur = scene
        self._sync_cast(scene)
        return scene

    def _sync_cast(self, scene: S.SceneScript) -> None:
        """对比上一刻的在场集合，自动生成出场/退场。

        每 tick 都调（不只是分幕时）——**人物可能中途离开或回来**，
        只在分幕时对比会漏掉。

        第一幕没有"上一刻"，所以上一刻按空集算：于是开场所有人都会记一条
        「出场（已在场）」。这正是读者需要的第一拍：谁在这个场景里。
        
                English:
        Compare the present set against the previous moment, and automatically generate entrance/exit.
                Called every tick (not just at scene breaks) — **characters may leave or return mid-tick**,
                comparing only at scene breaks would miss it.
                The first act has no "previous moment", so the previous moment is treated as an empty set: thus everyone present at the opening records an
                "appearance (already on scene)". This is exactly the first beat the reader needs: who is in this scene.
        """
        cast = self._cast_now()
        now = set(cast)
        first_ever = not self._known_cast

        for name in cast:
            if name not in self._prev_cast:
                scene.add(S.enter(name, '已在场' if first_ever else '入画'))
                self._maybe_image(scene, kind='portrait', key=name,
                                  caption=name, once=True)
        for name in sorted(self._prev_cast - now):
            scene.add(S.exit_(name, '离场'))

        self._prev_cast = now
        self._known_cast |= now

    def _maybe_image(self, scene: S.SceneScript, *, kind: str, key: str,
                     caption: str, at_head: bool = False,
                     once: bool = False) -> None:
        mode = (CFG.s('SCRIPT_IMAGES') or 'off').strip().lower()
        if mode == 'off' or not self._image_hook or not key:
            return
        want = (mode == 'both' or mode == kind
                or (mode == 'map' and kind == 'scene')
                or (mode == 'portrait' and kind == 'portrait'))
        if not want:
            return
        sid = id(scene)
        if self._img_count.get(sid, 0) >= MAX_IMAGES_PER_SCENE:
            return
        # `once=True`：同一个人整轮只交代一次（入场→离场→再入场不该重复刷）。
        # [EN] `once=True`: the same person is only accounted for once per whole run (entering → leaving →
        # [EN] re-entering should not repeatedly refresh).
        if once and (kind, key) in self._imagined:
            return
        # 这一幕的上下文：插图要按"哪儿 / 什么天气 / 什么时候 / 几个人"画，
        # 不然一个项目里所有插图长得都一样。
        # [EN] Context of this act: illustrations should be drawn according to "where / what weather / when /
        # [EN] how many people",
        # [EN] otherwise all illustrations in a project look the same.
        ctx = {'place': scene.place or key, 'weather': scene.weather,
               'time_label': scene.time_label,
               'cast': len(scene.cast or self._cast_now())}
        try:
            if self._hook_takes_ctx:
                path = self._image_hook(kind, key, ctx)
            else:
                path = self._image_hook(kind, key)
        except Exception:
            path = None
        if once:
            self._imagined.add((kind, key))

        if not path:
            # ★ **拿不到图就不再另写一段人物介绍**（2026-10-07 用户改的口径）。
            # [EN] ★ **If no image is available, do not write another character introduction** (the standard the
            # [EN] user changed on 2026-10-07).
            #
            #   以前这里会 `scene.add(S.note(self._person_line(name), label='肖像'))`
            #   —— 用一行 `※ 肖像：主角 · 沈家长子 · 沉稳内敛` 代替肖像图。
            #   但每轮开跑时**开场卡里已经交代过这个人**（`sim/opening.py`
            #   的「登场人物」：身份 + 与主角的关系 + 当下 + 标志），正文再来一遍
            #   就是同一批信息说两次。用户原话：「人物介绍了两遍 这个没必要」。
            #   所以肖像图拿不到就**只是没有图**，不补文字。
            # [EN] Previously here it would `scene.add(S.note(self._person_line(name), label='肖像'))`
            # [EN] But at the start of each run **the opening card has already accounted for this person**
            # [EN] (`sim/opening.py`
            # [EN] 's "登场人物": identity + relationship to the protagonist + current situation + signature),
            # [EN] repeating it in the body text
            # [EN] So if the portrait image is unavailable, it's **just no image**, no text substitute.
            return

        self._img_count[sid] = self._img_count.get(sid, 0) + 1
        entry = S.image(path, caption, kind_hint=kind)
        if at_head:
            scene.entries.insert(0, entry)      # 幕首图放最前，先见图再读文
            # [EN] Act-opening image goes first, see the image before reading the text
        else:
            scene.add(entry)                    # 肖像跟在它自己的出场之后
            # [EN] The portrait follows its own appearance

    # ══════════════════════════════════════════════════════════
    #  观察（RunLoop 调这几个）
    # [EN] Observation (RunLoop calls these)
    # ══════════════════════════════════════════════════════════
    def observe_tick(self, actions: list[tuple[Any, Any]],
                     *, tick_num: int = 0) -> None:
        """一次处理**整个 tick** 的全部动作 —— 同时性靠这一步才看得出来。

        `actions` 是 `[(Agent, Action), ...]`。
        
                English:
        Process **all actions of an entire tick** at once — simultaneity is only visible through this
        step.
                `actions` is `[(Agent, Action), ...]`.
        """
        if not actions:
            self.observe_quiet()
            return

        scene = self._ensure_scene()
        if len(scene.entries) >= CFG.i('SCRIPT_SCENE_MAX_ENTRIES'):
            self.begin_scene(force=True)
            scene = self._cur
        # 每 tick 对一次在场名单：人物可能中途走了或回来了
        # [EN] Check the present-list once per tick: characters may leave or return midway
        self._sync_cast(scene)

        # 按地点分组 → 决定是同场同时还是异地同时
        # [EN] Group by location → decide whether it's same-scene simultaneous or remote simultaneous
        here: list[tuple[Any, Any]] = []
        elsewhere: dict[str, list[tuple[Any, Any]]] = {}
        for agent, act in actions:
            loc = (getattr(getattr(agent, 'ps', None), 'location', '') or '').strip()
            scene_place = (scene.place or '').strip()
            if loc and scene_place and loc != scene_place:
                elsewhere.setdefault(loc, []).append((agent, act))
            else:
                here.append((agent, act))

        if elsewhere:
            if here:
                self._emit_group(scene, here, visibility=S.PRESENT)
            for loc, group in elsewhere.items():
                # 异地同时**只在值得切时才切**：一个在别处的人在发呆/变脸，
                # 不值得为他把镜头切走又切回来（否则每 tick 都刷一遍
                # 「切至…切回…」，满屏都是转场标记）。
                #   —— 但如果是"别处正在发生事情"，那正是要切过去的理由。
                # [EN] Remote simultaneous **only cuts when it's worth cutting**: if someone elsewhere is spacing
                # [EN] out/making a face,
                # [EN] it's not worth cutting the camera away and back for them (otherwise every tick refreshes
                # [EN] "cut to… cut back…", and the screen is full of transition markers).
                # [EN] —— But if it's "something is happening elsewhere", then that's exactly the reason to cut over.
                if not any(self._worth_cutting(act) for _, act in group):
                    continue
                scene.add(S.cut(loc, '同一时刻'))
                self._emit_group(scene, group, visibility=S.ELSEWHERE,
                                 place=loc)
                scene.add(S.cut_back(scene.place or ''))
        else:
            self._emit_group(scene, here, visibility=S.PRESENT)

    @staticmethod
    def _worth_cutting(act: Any) -> bool:
        """这个动作值不值得为它切一个镜头？
                English:
        Is this action worth cutting a shot for?
        """
        verb = getattr(act, 'verb', '')
        if verb in ('move', 'interact'):
            return True
        if verb == 'speak':
            return bool(getattr(act, 'dialogue', ''))
        return False

    #: 「纯手势」开头 —— 只表示"他动了一下"，不推进任何事。
    #: 反复出现就是刷版面（用户报的「转向阿福」刷屏就是这个）。
    # [EN] : starts with "pure gesture" —— only means "he moved a bit", advances nothing.
    # [EN] : repeated appearance is just refreshing the layout (the user's reported "turns toward A'fu"
    # [EN] screen-spam is this).
    _GESTURE_PREFIX = ('转向', '转头', '望向', '看向', '朝着', '面向', '瞥了',
                       '扫了', '点了点', '动了动', '坐着', '站在', '起身',
                       '坐下', '点头', '摇头', '沉默', '不语')

    @staticmethod
    def _narrate_order(group: list[tuple[Any, Any]]) -> list[tuple[Any, Any]]:
        """叙事顺序：**说话的排前面**，其余保持原序。

        台词是剧情、动作是陪衬 —— 先读"谁说了什么"，再接"他说这话时顺手
        做了什么"，才像人写的。`sorted` 是稳定的，所以同档内不改变原顺序。
        
                English:
        Narrative order: **speakers come first**, the rest keep their original order.
                Dialogue is the plot, actions are the accompaniment — read "who said what" first, then "what he did
                while saying it", only then does it read like a human wrote it. `sorted` is stable, so within the same tier the original order is unchanged.
        """
        def _rank(item: tuple[Any, Any]) -> int:
            verb = getattr(item[1], 'verb', '')
            return 0 if (verb == 'speak'
                         and getattr(item[1], 'dialogue', '')) else 1
        return sorted(group, key=_rank)

    #: 判"纯手势"的长度上限（**不是"多短"，而是"有没有附加成分"**）。
    #: ★★★ 2026-10-18：原来是 14，把**闲笔**也一起判成了噪声 ——
    #:   实测误伤：`站在门口听了一会儿。`（10 字）、`扫了一眼屋角那只旧箱子`（11 字）
    #:   都被当成"纯手势"，于是"连着两拍都这样"时第二拍被删。
    #:   而这两句正是真人小说控节奏的写法（用户当时的原话是
    #:   「句子感觉太简练了，过于追求故事推进，不像正常人写的小说」）。
    #:   ⇒ 门槛降到 8：`转向某人`(4) / `望向纸门`(4) / `点头`(2) 照旧算刷屏，
    #:     带对象、带时长、带结果的（`一会儿` / `那只旧箱子` / `没动`）算**有东西**，放行。
    #: ⚠ 别再按"推不推进主线"判 —— 那是内容判断，一段文字删不删不能由它决定；
    #:   渲染层能判的只有"这句话里除了动作还有没有别的东西"。
    # [EN] Length cap for "pure gesture" -- **not "how short", but "does it carry anything
    # [EN] besides the movement"**. ★★★ 2026-10-18: it used to be 14, which swept **idle lines**
    # [EN] into the noise bucket. Measured false positives: "stood at the door listening for a
    # [EN] while" (10 chars) and "glanced at that old chest in the corner" (11 chars) were both
    # [EN] treated as pure gestures, so the second of two consecutive beats got dropped -- and
    # [EN] those are exactly how human novels pace themselves. Threshold lowered to 8:
    # [EN] "turns to X" (4) / "looks at the paper door" (4) / "nods" (2) still count as spam,
    # [EN] while anything with an object, a duration or a result is let through.
    # [EN] ⚠ Do not judge by "does it advance the plot" -- that is a content call, and a
    # [EN] rendering layer can only judge "is there anything here besides the movement".
    GESTURE_MAX_LEN = 8

    def _is_pure_gesture(self, text: str) -> bool:
        """只表示"他动了一下"、**没有附加成分**的那种动作（且很短）。

        ⚠ 判的是"有没有东西"，**不是"推不推进"** —— 后者是内容判断，
          渲染层做不了，做了就会把闲笔当噪声删（见 `GESTURE_MAX_LEN` 的说明）。
        [EN] The kind of action that only means "he moved a bit" with **nothing attached**.
        [EN] ⚠ It judges "is there anything here", **not "does it advance"** -- the latter is a
        [EN] content call; making it here deletes idle lines as noise.
        """
        t = (text or '').strip()
        return len(t) <= self.GESTURE_MAX_LEN and t.startswith(self._GESTURE_PREFIX)

    #: 判"是不是同一句话"的相似度门槛（`difflib` 比值，0~1）。
    #: 0.86 是量出来的：《雪国》那轮「脸埋回臂弯」/「下巴抵回臂弯」这类
    #: **换个动词的同一动作**约 0.55（够不着，靠 `[你上一拍做的]` 挡）；
    #: 而「你那车份儿打算拖到什么时候」/「车份儿打算拖到什么时候」约 0.92。
    #: ⇒ 这条门槛只管"同一句换了几个字"，不管"同一类动作"，别调太低。
    #: ⚠ 真身在模块级 `SAID_NEAR`（prose 模式那条路 `sim/loop._repeat_hit`
    #:   也要用同一个数——两处各写一个数，迟早一个改了一个没改）。
    # [EN] Threshold for "is this the same sentence" (`difflib` ratio, 0..1).
    # [EN] 0.86 is measured: in the Snow Country run, "face buried back in the crook of the arm" /
    # [EN] "chin propped back on the crook of the arm" is about 0.55 (out of reach -- the
    # [EN] `[你上一拍做的]` block handles those), while "when are you going to pay the cart rent" /
    # [EN] "the cart rent, when are you going to pay it" is about 0.92.
    # [EN] => this threshold only covers "the same sentence with a few words changed", not "the same
    # [EN] kind of action". Do not lower it.
    # [EN] ⚠ The real one lives at module level as `SAID_NEAR` (the prose-mode path
    # [EN] `sim/loop._repeat_hit` must use the same number -- two copies will drift).
    SAID_NEAR = SAID_NEAR

    @staticmethod
    def _norm_line(text: str) -> str:
        """去掉标点与空白，只留字 —— 判"是不是同一句"用（真身是模块级 `norm_line`）。"""
        return norm_line(text)

    def _remember_line(self, name: str, line: str) -> None:
        """把一句台词登记进**两本账**（原文台账 + 归一化台账）。

        ★★★ 2026-10-18：这是**唯一写入口**。原来 `_worth_emitting` /
          `observe_speech` / `_learn_from` 各写一遍 `self._said.add(...)`，
          现在近似判定还要多一本归一化账 —— 三处各写一遍就是三个漏点
          （漏一处，那一路的台词就永远判不出重复）。
        [EN] ★★★ 2026-10-18: this is the **single write entry**. `_worth_emitting` /
        [EN] `observe_speech` / `_learn_from` each used to add to `self._said` on their own; the
        [EN] near-duplicate check needs a second normalized ledger, and writing it in three places
        [EN] means three ways to miss (miss one and that path can never detect a repeat).
        """
        who = str(name or '').strip()
        t = str(line or '').strip()
        if not (who and t):
            return
        self._said.add((who, t))
        n = self._norm_line(t)
        if n:
            self._said_norm.setdefault(who, []).append(n)

    def _near_said(self, name: str, line: str) -> bool:
        """**换个说法说同一件事**算不算说过 —— 近似判定（2026-10-18）。

        为什么精确比对不够（《雪国》/`ltxz-01` 实测）：
          · 模型复读时很少一字不差，它会把语序挪一下、漏两个字 ——
            「你那车份儿打算拖到什么时候？」→「车份儿打算拖到什么时候」；
          · 精确比对放过去，读起来完全是"他又说了一遍"。
        ⚠ 短句（归一化后 < 4 字）**不判近似**：`嗯`/`走吧`/`我不知道` 这种
          本来就是口语里反复出现的东西，判成重复会把正常应答也拦掉
          （`_review_repeat` 那边另有 `is_short_reply` 一档放行）。
        [EN] **Saying the same thing in different words** still counts as said -- near-duplicate
        [EN] check (2026-10-18). Why exact comparison is not enough: the model rarely repeats word for
        [EN] word; it reorders or drops a couple of characters, yet it reads exactly like "he said it
        [EN] again". ⚠ Short lines (under 4 chars after normalization) are **not** near-checked:
        [EN] "mm" / "let's go" / "I don't know" are what people genuinely repeat, and flagging them
        [EN] would block normal replies (`_review_repeat` has the `is_short_reply` tier for that).
        """
        who = str(name or '').strip()
        n = norm_line(line)
        if len(n) < 4:
            return False
        for prev in list(self._said_norm.get(who) or ())[-8:]:
            if prev == n or near_same(n, prev):
                return True
        return False

    def already_said(self, name: str, line: str) -> bool:
        """这句话他说过了吗 —— **只读**，不改任何状态。

        给 `sim/loop._review_repeat` 用的：人物决定要说的那句话如果撞上护栏，
        主循环要先问一句"你是不是非说不可"，而不是让它无声无息地消失
        （那正是探针里"整拍空白"的来源）。

        ⚠ 与 `_worth_emitting` 用**同一份** `_said`：判定源与护栏同源，
          才不会出现"重说了却还是被挡"的错位。
        ★ 2026-10-18：先查精确，再查**近似**（`_near_said`）——
          "换个说法说同一件事"也算说过，交给 `_review_repeat` 去问他是不是非说不可。
        
                English:
        Has he already said this line — **read-only**, does not modify any state.
                Used by `sim/loop._review_repeat`: if the line the character decides to say hits the guardrail,
                the main loop must first ask "do you really have to say it", instead of letting it vanish silently
                (that is exactly the source of the "blank whole beat" in the probe).
                ⚠ Uses the **same** `_said` as `_worth_emitting`: the decision source and the guardrail share the same source,
                  so there is no mismatch of "it was repeated but still blocked".
                ★ 2026-10-18: check exact first, then **near** (`_near_said`) -- "the same thing in
                  different words" also counts as said, and `_review_repeat` decides whether it must
                  be said.
        """
        key = (str(name or '').strip(), str(line or '').strip())
        if key in self._said and key not in self._forced:
            return True
        if key in self._forced:
            return False
        return self._near_said(name, line)

    def allow_repeat(self, name: str, line: str) -> None:
        """放行一句"必须重复"的台词（人物重说之后**仍然**说的是这一句）。

        登记之后 `_worth_emitting` / `observe_speech` 都会放它过去。
        这条通路**只由主循环在重说失败后**调用 —— 不要在别处用它绕过去重。
        
                English:
        Let through a line that "must be repeated" (after the character repeats it, it is **still** this
        line).
                After registration, `_worth_emitting` / `observe_speech` will both let it through.
                This path is **only called by the main loop after a repeat failure** — do not use it elsewhere to bypass dedup.
        """
        self._forced.add((str(name or '').strip(), str(line or '').strip()))

    def _worth_emitting(self, agent: Any, act: Any) -> bool:
        """这一条值不值得写进正文 —— **去重 + 去噪声**。

        三条都是用户报过的毛病，实测证据见 `__init__` 里那段注释：
          ① **同一句话只说一次**（`(人名, 台词)` 说过了就不再写）。
             丁那句「账差七文」一字不差出现了 4 次，就是这么来的。
             ★ 但"必须重复"的放行名单（`_forced`）在这里让路 —— 见
             `already_said` / `allow_repeat`。
          ② **同一个人的动作不连着重**（与上一次一字不差就丢）。
          ③ **连续两拍都只是"纯手势"** → 第二拍丢掉。
             用户：「尽量每件事 每句话都跟主线有关」——"转向某人"不推进任何事。

        返回 False 的会被 `_emit_group` 丢掉；**但整组不会因此变空**（见那边的兜底）。
        
                English:
        Is this item worth writing into the body — **dedup + noise removal**.
                All three are bugs reported by users, see the comment block in `__init__` for empirical evidence:
                  ① **The same line is said only once** (`(name, line)` is not written again once said).
                     Lao Chen's line "account is short seven wen" appeared verbatim 4 times, and that is how it happened.
                     ★ But the "must repeat" allowlist (`_forced`) gives way here — see
                     `already_said` / `allow_repeat`.
                  ② **The same person's actions are not consecutive duplicates** (dropped if verbatim identical to the previous one).
                  ③ **Two consecutive beats that are both only "pure gestures"** → the second beat is dropped.
                     User: "try to make everything and every line related to the main plot" — "turning to someone" advances nothing.
                Those returning False are dropped by `_emit_group`; **but the whole group will not become empty because of that** (see the fallback there).
        """
        name = self._name_of(agent)
        verb = getattr(act, 'verb', '')
        if verb == 'speak' and getattr(act, 'dialogue', ''):
            line = str(act.dialogue).strip()
            if (name, line) in self._said and (name, line) not in self._forced:
                return False                     # ① 同一句话重复 → 丢
                # [EN] ① Same line repeated → drop
            self._remember_line(name, line)
            self._last_action[name] = f'说：{line}'
            self._last_gesture.pop(name, None)
            return True

        text = (self._action_text(act) or '').strip()
        if not text:
            return False
        prev_act = self._last_action.get(name) or ''
        # ★★★ 2026-10-18：**一字不差**升级成**近似重复**。
        #   实测（《雪国》repeat-fix 那一轮）：同一拍里驹子出现了两条
        #   「头发散了，脸上**还**带着酒气，眼神有些迷离地看着岛村」/
        #   「头发散了，脸上带着酒气，眼神有些迷离地看着岛村」—— 差一个"还"字，
        #   精确比对放过去，读者看到的是同一段描写写了两遍。
        #   ⚠ `min_len=6`：短动作（"蹲下""转身"）本来就该反复出现，
        #     只判**长句**的近似（评语里那种"两次重复同一动作"全是长句）。
        # [EN] ★★★ 2026-10-18: "verbatim identical" upgraded to **near duplicate**.
        # [EN] Measured (Snow Country, repeat-fix run): two entries in the same beat read "hair loose,
        # [EN] face **still** smelling of wine, eyes on Shimamura" and "hair loose, face smelling of wine,
        # [EN] eyes on Shimamura" -- one character apart; exact comparison let it through and the reader
        # [EN] sees the same description twice.
        # [EN] ⚠ `min_len=6`: short actions ("crouches", "turns") are supposed to recur; only **long
        # [EN] sentences** are near-checked (every "the same action twice" verdict was a long one).
        if prev_act and (text == prev_act
                         or (not prev_act.startswith('说：')
                             and near_same(text, prev_act, min_len=6))):
            return False                         # ② 与上一拍（或同拍上一条）重复 → 丢
            # [EN] ② Duplicate of the previous beat (or the previous entry) → drop
        gesture = self._is_pure_gesture(text)
        if gesture and self._last_gesture.get(name):
            return False                         # ③ 连着两拍都只是动一下 → 丢
            # [EN] ③ Two consecutive beats of just moving a bit → drop
        self._last_action[name] = text
        if gesture:
            self._last_gesture[name] = True
        else:
            self._last_gesture.pop(name, None)
        return True

    def _emit_group(self, scene: S.SceneScript, group: list[tuple[Any, Any]],
                    *, visibility: str, place: str = '') -> None:
        """输出这一拍的动作 —— **按先后一件件写，不再套「同时」**。

        ★ 2026-10-07 改写。用户原话：「人物做事情总是有先有后的  你这全部都
          是· 同一时刻  好像大家都在很快的干任何事情一样  而且你这个又有点乱了」。

        以前：这一拍只要有 2 个人各做一个动作，就 `S.parallel()` 并列成
        `〔同时〕 / - 甲｜… / - 乙｜…`。一天几百拍下来满屏都是「同时」——
        读起来像**所有人同时在乱动**，而不是"一件事接一件事发生"。
        现在：一律**按先后逐个 `scene.add`**（先谁后谁不苛求，但必须是先后）。

        「同时」只剩一处：**异地切镜头**（`observe_tick` 里那对
        `〔切至 X·同一时刻〕 … 〔切回〕`）—— 那才真是"同一时刻不同人在不同地方"，
        也正是这个标记本来该表达的。用户 2026-10-07 明确要的就是这样：
        「只保留异地切镜头」。

        ★ 关于**兜底**：这里**故意不做**"全被滤掉就留第一条"。
          第一版写了那个兜底，结果**去重当场失效** —— 重复的台词被滤掉之后
          又被兜底留住，等于没滤（自我反例法当场抓出来）。
          正确的语义是：**被滤掉 = 这一拍确实没发生新事情 → 就该空着**。
          人物在原地重复同样的事，本来就不该写进正文。
          正常情况也不会空：第一次出现的动作/台词必定通过（`_last_action`
          还没记过它），只有"重复"才会被滤。
        
                English:
        Output this beat's actions — **write them one by one in sequence, no more wrapping in
        "simultaneous"**.
                ★ Rewritten 2026-10-07. User's original words: "characters doing things always have an order   yet all of yours
                  are · the same moment  as if everyone is very quickly doing everything  and yours is also a bit messy".
                Before: as long as this beat had 2 people each doing one action, it used `S.parallel()` to list them side by side as
                `〔simultaneous〕 / - A｜… / - B｜…`. Over hundreds of beats a day the screen was full of "simultaneous" —
                it read like **everyone moving chaotically at the same time**, rather than "one thing happening after another".
                Now: always **`scene.add` one by one in sequence** (who comes first is not strict, but there must be a sequence).
                "Simultaneous" remains in only one place: **cutting to a different location** (the pair in `observe_tick`
                `〔cut to X · same moment〕 … 〔cut back〕`) — that is truly "different people in different places at the same moment",
                and is exactly what this marker was meant to express. This is precisely what the user explicitly asked for on 2026-10-07:
                "keep only cross-location cuts".
                ★ About the **fallback**: here "if all are filtered out, keep the first one" is **deliberately not done**.
                  The first version wrote that fallback, and **dedup failed on the spot** — duplicate lines, after being filtered out,
                  were kept again by the fallback, equivalent to not filtering at all (caught on the spot by the self-counterexample method).
                  The correct semantics are: **filtered out = this beat really has no new events → it should stay empty**.
                  A character repeating the same thing in place should not be written into the body in the first place.
                  Normally it will not be empty either: an action/line appearing for the first time always passes (`_last_action`
                  has not recorded it yet), only "repeats" get filtered.
        """
        if not group:
            return
        ordered = self._narrate_order(group)
        for agent, act in ordered:
            if not self._worth_emitting(agent, act):
                continue
            for entry in self._entries_for(agent, act, visibility, place):
                scene.add(entry)

    def _entries_for(self, agent: Any, act: Any, visibility: str,
                     place: str) -> list[S.Entry]:
        """这一拍，这个人物产出哪些词条。

        ★★★ 2026-10-14（用户）：「我看现在的推演结果 是大量的对话 正常小说的话
        应该有…心理活动…」—— 这里改了**心理活动的产出条件**：

        **改之前**：`inner`（内心）**只在 `verb == 'think'` 时**才被用。
        也就是说，模型在 `speak` / `move` / `interact` / `emote` 时写了
        `"内心": "…"`，那个字段**被直接丢掉**。
        而提示词里 `think` 本来就是个边缘选项（"真没得做时才用 wait"），
        于是**实际推演里几乎见不到"心声"这一层** ——
        用户看到的就成了"只有对话"。

        **改之后**：**任何动作都可以带心声** —— 说话的人可以心里另有想法
        （嘴上答应的和心里想的不是一回事，这恰恰是小说的常态），
        做事的人可以一边做一边想。有心声就多产一条 `ASIDE`。

        ⚠ 顺序：**动作在前、心声在后**（`out.append` 的先后就是中栏的先后）。
          反过来的话读者会先看到"他想…"再看到"他做了什么"，因果是倒的。
        ⚠ `ASIDE` 是"心声，不外泄"（`display/script.py` 的定义）——
          它**不进** `world.recent_lines`（那是"场上公开的事"），
          所以加它**不会**让别人"听到"这个人的想法，人设不会崩。
          这一点由 `tools/verify_actor_layers.py` 的那一类判据守着。

            English:
        Which entries this character produces this beat.

        ★★★ 2026-10-14 (user): "I see the deduction output is mostly dialogue; a normal novel
        should have ... inner activity" -- the **conditions for producing inner activity** changed
        here:

        **Before**: `inner` was used **only when `verb == 'think'`**. So when the model wrote
        `"内心": "..."` alongside `speak` / `move` / `interact` / `emote`, that field was **simply
        discarded**. And `think` was already a marginal option in the prompt ("only use `wait` when
        there is really nothing to do"), so **the "inner voice" layer was almost never seen** in
        practice -- which is exactly why what the user saw became "only dialogue".

        **After**: **any action can carry an inner voice** -- a speaker may be thinking something
        else (what he answers aloud and what he thinks are not the same thing, which is precisely
        the norm in fiction), and someone doing something can think while doing it. An inner voice
        yields one extra `ASIDE`.

        ⚠ Order: **action first, inner voice after** (the `out.append` order is the middle-column
          order). Reversed, the reader would see "he thought..." before "he did...", which inverts
          the causality.
        ⚠ `ASIDE` means "inner voice, not leaked" (per its definition in `display/script.py`) --
          it does **not** enter `world.recent_lines` (that is "what is publicly happening on
          stage"), so adding it **cannot** let others "hear" this person's thoughts and the
          character cannot collapse. That is guarded by the criteria family in
          `tools/verify_actor_layers.py`.
        """
        name = self._name_of(agent)
        verb = getattr(act, 'verb', '')
        inner = getattr(act, 'inner_thought', '') or ''
        out: list[S.Entry] = []

        if verb == 'speak' and getattr(act, 'dialogue', ''):
            out.append(S.dialogue(name, act.dialogue,
                                  to=getattr(act, 'target', '') or '',
                                  tone=self._tone_of(agent, act)))
            # ★ 说话也可以心里另有一套（嘴上答应的 ≠ 心里想的）——
            #   这正是小说里"表里不一"那一层，以前被整段丢掉。
            # [EN] ★ Speaking can also carry a separate inner track (what he agrees to aloud != what
            # [EN] he thinks inside) -- exactly the "outward vs inward" layer in fiction, which used
            # [EN] to be dropped wholesale.
            if inner:
                out.append(S.aside(name, inner[:80]))
        elif verb == 'think':
            # 「想事情」是内心活动，不是动作 —— 早期版本把它写成
            # `· 动作 主角：（若今晚走不成…）`，读起来像他在自言自语。
            # [EN] "Thinking about something" is inner activity, not an action —— early versions wrote it as
            out.append(S.aside(name, inner[:80]) if inner
                       else S.action(name, '在想事情', visibility=visibility,
                                     place=place))
        else:
            out.append(S.action(name, self._strip_own_name(
                self._action_text(act) or '（无动作）', name),
                                visibility=visibility, place=place))
            # ★ 做事的时候心里在想什么（"一边擦桌子一边盘算"）——
            #   同样以前只在 `think` 那条路上才产。动作在前、心声在后。
            # [EN] ★ What he is thinking while doing something ("wiping the table while scheming")
            # [EN] -- also only produced on the `think` path before. Action first, inner voice after.
            if inner:
                out.append(S.aside(name, inner[:80]))
        return out

    @staticmethod
    def _strip_own_name(text: str, name: str) -> str:
        """`细节` 若以**自己的名字**开头就先去掉 —— 否则正文里会出现「驹子驹子伏在…」。

        为什么会有（2026-10-18《雪国》repeat-fix 实测）：
        模型有时把 `细节` 写成**第三人称**（"驹子伏在火钵边上，头发散了…"），
        而正文渲染时是 `（<说话人><细节>）` ⇒ 名字写了两遍。
        去掉开头的名字不改任何语义（名字本来就会由渲染层给出）。
        [EN] If `细节` starts with the character's **own name**, drop it -- otherwise the body reads
        [EN] "Jouji Jouji leaned over the brazier". Measured in the Snow Country repeat-fix run: the
        [EN] model sometimes writes `细节` in **third person**, while the renderer emits
        [EN] `(<speaker><detail>)` => the name appears twice. Dropping the leading name changes no
        [EN] meaning (the renderer supplies it anyway).
        """
        t = str(text or '').strip()
        n = str(name or '').strip()
        if n and t.startswith(n):
            t = t[len(n):].lstrip('，,。：:、 ')
        return t or text

    def observe_speech(self, name: str, line: str, *, to: str = ''):
        """群聊轮转里的一句台词 —— 与前台步进**同一个出口**。

        ★ 2026-10-07 加。用户报的毛病：「这个故事线里把任务（人物）说的话讲
          一遍，然后人物自己再说一遍，很诡异」。

        起因是群聊轮转以前自己拼一句话推给屏幕：
        `self._push_narrative(f"{a.name}说：「{line}」", 2, kind=S.DIALOGUE)`
        —— 那句话是**旁白在复述台词**，屏幕上于是先出现"某某说：「…」"，
        紧接着这个人物又用台词的样子说了一遍；而且它**只在中栏有、落盘的
        剧本里没有**，屏幕与文件对不上。

        现在：台词就是台词（`DIALOGUE` 词条，剧本体 `人名：台词`），
        走同一条去重护栏（`_said`：同一句话不再说第二遍）。

        返回真的加进去的那条词条（被去重滤掉时返回 `None`）——
        调用方据此决定要不要推到屏幕上，免得把滤掉的又推一遍。
        
                English:
        A line in the group-chat rotation — the **same exit** as foreground stepping.
                ★ 2026-10-07 added. The bug users reported: "In this storyline, the task's (character's) speech is narrated
                  once, and then the character says it again themselves — very strange."
                The cause was that group-chat rotation used to assemble a sentence itself and push it to the screen:
                `self._push_narrative(f"{a.name}说：「{line}」", 2, kind=S.DIALOGUE)`
                —— that sentence was **the narrator restating the dialogue**, so the screen first showed "so-and-so says: '...'",
                and then the character said it again in the form of a line; moreover it **only existed in the middle column and not in the
                script written to disk**, so the screen and the file didn't match.
                Now: a line is just a line (`DIALOGUE` entry, script body `name: line`),
                going through the same dedup guardrail (`_said`: the same sentence is not said a second time).
                Return the entry that was actually added (return `None` when filtered out by dedup) ——
                the caller uses this to decide whether to push it to the screen, to avoid pushing the filtered one again.
        """
        text = str(line or '').strip()
        name = str(name or '').strip()
        if not text:
            return None
        if (name, text) in self._said and (name, text) not in self._forced:
            return None
        self._remember_line(name, text)
        self._last_action[name] = f'说：{text}'
        self._last_gesture.pop(name, None)
        entry = S.dialogue(name, text, to=to)
        self._ensure_scene().add(entry)
        return entry

    def observe_event(self, director_event: Any) -> None:
        """外部事件（导演注入）——这是"天气/外部事件影响故事"的入口。

        ★★★ 2026-10-19 第十二轮：事件说完，**把进出场标记补进材料**。
        --------------------------------------------------------
        用户点名的第四条：「叶子行动线逻辑矛盾：送酒→退下→**无回归标记**又出现
        →拿凉壶→送回温好的酒」。

        根因不在作家那边，在**材料**：`world._loc_matches` 有意从宽
        （"他只是挪到门外/柜台后"算在场），人物 `status` 永远是「在场」
        ⇒ `_sync_cast` 的退场那一支**在生产里一次都没响过**
        （19 个真跑项目 / 47 天：`exit` 词条 0 条、`enter` 77 条）。
        于是"叶子低头退下"只活在一句事件描述里 —— 落在长句中间、
        和后面的动作隔了四行，作家看不见这条链，只能让她"人在门外却伸手进屋"。

        修法：导演事件本来就带**结构化的** `离场人物` / `进场人物` 两栏
        （`DirectorEvent.leaving` / `.entering`），这里据此往材料里补
        `〔退场〕X（离场）` / `〔出场〕X（入画）` —— 与 `_sync_cast`
        发的标记**同一形状**（`script_render.one_line` 认的就是它）。

        ⚠ 三条护栏（缺一不可，都是为了防止"凭空造进出场"）：
          · **必须在场名单里**才许标离场、**不在场**才许标进场 ——
            不然会把一个还在屋里的人标成退了；
          · **必须在事件描述里真的出现过** —— 挡模型在两栏里编名字；
          · 描述为空 ⇒ 什么都不补（老行为）。
        ⚠ 世界状态**一个字都不改**：这里只往材料里加标记。
          改 `status`/`location` 会让那个人从此不再决策（太险），而本条修的是
          "作家看不见链"，不是"世界算错了人在哪"。
        [EN] External events (director injection). ★★ Round twelve: after the event,
        [EN] **add the entrance/exit marks to the material**. The root cause was not
        [EN] the novelist but the material: `_sync_cast`'s exit branch never fires
        [EN] in production (0 `exit` entries in 47 days), so "she bowed out" lived
        [EN] only inside a prose sentence. Now the structured `leaving` / `entering`
        [EN] lists add real marks of the **same shape** `_sync_cast` emits.
        [EN] ⚠ Three guards, all mandatory: must be in the cast to leave / out of the
        [EN] cast to enter, must actually appear in the description, and no description
        [EN] means no marks. ⚠ The world state is **not touched at all**.
        """
        scene = self._ensure_scene()
        desc = getattr(director_event, 'description', '') or ''
        kind_name = getattr(director_event, 'event_type', '') or ''
        if not desc:
            return
        scene.add(S.event(desc, kind_name=kind_name))
        cast = {str(x).strip() for x in (getattr(scene, 'cast', None) or [])
                if str(x).strip()}
        # ── 离场：在场名单里、且事件里真的提到了他 ──
        # [EN] Leaving: in the cast and actually named in the event.
        for name in (getattr(director_event, 'leaving', None) or []):
            n = str(name or '').strip()
            if not n or n not in cast or n not in desc:
                continue
            scene.add(S.exit_(n, '离场'))
        # ── 进场：**不在**场名单里、且事件里真的提到了他 ──
        #   （在场的人"进场"没有意义 —— `_sync_cast` 也会发一条重复的）
        # [EN] Entering: **not** in the cast and actually named in the event
        # [EN] (someone already present "entering" is meaningless).
        for name in (getattr(director_event, 'entering', None) or []):
            n = str(name or '').strip()
            if not n or n in cast or n not in desc:
                continue
            # 世界已经算他在场 ⇒ `_sync_cast` 下一拍自己会发一条「进场」，
            # 这里再发就是重复的（同一件事两处实现的经典入口）。
            # [EN] If the world already counts him present, `_sync_cast` emits its own
            # [EN] entrance next tick -- emitting here too would duplicate it.
            if n in self._prev_cast:
                continue
            scene.add(S.enter(n, '入画'))

    def observe_reflection(self, name: str, text: str) -> None:
        """人物的**回忆/省思**。

        ⚠ 用 `RECALL` 而不是 `ASIDE`（2026-10-06 分出来的）：`ASIDE` 是"他此刻心里
        那句话"，`RECALL` 是"他心里翻出来的一件旧事" —— 屏幕上样式不同
        （回想是暗色斜体 + ↺ 符号），读者才分得出"他现在想"和"他想起"。
        
                English:
        A character's **recollection/reflection**.
                ⚠ Use `RECALL` instead of `ASIDE` (split out on 2026-10-06): `ASIDE` is "the sentence in his mind right now",
                `RECALL` is "an old matter dredged up in his mind" —— their styles differ on screen
                (recollection is dark italic + ↺ symbol), so the reader can tell "what he's thinking now" from "what he's remembering".
        """
        if not text:
            return
        self._ensure_scene().add(S.recall(name, text))

    def observe_quiet(self) -> None:
        """这一 tick 没人动 —— 空场也要有交代，否则读者以为卡住了。

        这是"人物不是一直在说话"的极端形态（全都在沉默）。给它**环境白描**
        （`AMBIENT`）而不是干巴巴一句"片刻无话"：沉默的片刻恰恰是写环境的
        时候 —— 雨声、市声、灯影，这些才是让场面活着的东西。

        ★ 2026-10-14：真正"产环境"的那半段抽成了 `_emit_ambient()`
          （见它的说明）—— 因为现在**有两条路**要产环境：
          ① 空场（这里）；② 按故事时间节流的那个（`observe_ambient`，新）。
          两处各写一遍的话，以后改"环境怎么写"会只改到一条路。
        
                English:
        No one moved this tick —— even an empty scene needs an account, otherwise the reader thinks it's
        stuck.
                This is the extreme form of "the characters aren't always talking" (all silent). Give it **environmental description**
                (`AMBIENT`) rather than a dry sentence like "a moment of silence": a silent moment is precisely the time to write the
                environment —— rain sounds, street sounds, lamplight shadows; these are what keep a scene alive.

        ★ 2026-10-14: the half that actually "produces environment" was extracted into
          `_emit_ambient()` (see its note) -- because **two paths** now produce environment:
          (1) an empty scene (here); (2) the story-time-throttled one (`observe_ambient`, new).
          Writing it twice would mean a future change to "how environment is written" only reaches
          one path.
        """
        scene = self._ensure_scene()
        has_content = any(e.kind not in (S.NOTE, S.SCENE) for e in scene.entries)
        if not has_content:
            return
        if scene.entries and scene.entries[-1].kind in (S.BEAT, S.AMBIENT):
            return
        scene.add(S.beat('片刻无话'))
        self._emit_ambient(scene)

    def observe_ambient(self) -> None:
        """**补一条环境白描**，与"有没有人在动"无关（2026-10-14 新增）。

        ★★★ 用户 2026-10-14 原话：
          「我看现在的推演结果 是大量的对话 正常小说的话应该是有任务的各种动作
            大量的环境 故事情节 人物做的事情 心理活动 等等不同的内容…
            不应该只有对话」

        ⚠ 为什么必须新增这条通路：**环境原来只在"全场都没动"时才写**
          （`_maybe_quiet()` ← `observe_quiet()`），而推演里"有动静"是常态
          ⇒ **环境几乎不出现**。用户看到的就成了"一屏台词"。
        ★ 与空场那条的区别：这里**不写** `BEAT`（「片刻无话」）——
          有人正在做事的时候写上"片刻无话"是错的（那句话本身也上不了屏，
          见 `WINDOW_KINDS`）。所以它直接产 `AMBIENT`。
        ⚠ **不编造内容**：用的还是同一份素材（`world.sound_design` 优先，
          回落"时段 × 天气"罐头池），而且有"上一条已经是 `AMBIENT` 就跳过"
          的护栏 ⇒ 不会连着刷同一句。

            English:
        **Emit one line of environmental description**, independent of "whether anyone is moving"
        (added 2026-10-14).

        ★★★ User's words on 2026-10-14:
          "I see the deduction output is mostly dialogue; a normal novel should have the characters'
          various actions, **a lot of environment**, plot, things the characters do, inner activity
          and so on ... it should not be only dialogue"

        ⚠ Why this path must be added: **environment used to be written only when "nobody moved at
          all"** (`_maybe_quiet()` <- `observe_quiet()`), while "something is happening" is the norm
          in a deduction => **environment almost never appears**. What the user saw became "a screen
          of dialogue".
        ★ Difference from the empty-scene path: this one does **not** write `BEAT` ("a moment of
          silence") -- writing "a moment of silence" while someone is working is simply wrong (and
          that line cannot even reach the screen, see `WINDOW_KINDS`). So it emits `AMBIENT`
          directly.
        ⚠ **Nothing is fabricated**: it draws on the same material (`world.sound_design` first,
          falling back to the "time period x weather" canned pool), and it keeps the "skip if the
          previous entry is already `AMBIENT`" guardrail => it will not spam the same line.
        """
        scene = self._ensure_scene()
        has_content = any(e.kind not in (S.NOTE, S.SCENE) for e in scene.entries)
        if not has_content:
            return
        # ⚠ 与 `observe_quiet` 同一条护栏：上一条已经是环境 ⇒ 别连着刷。
        # [EN] ⚠ Same guardrail as `observe_quiet`: the previous entry is already environment =>
        # [EN] do not spam.
        if scene.entries and scene.entries[-1].kind == S.AMBIENT:
            return
        self._emit_ambient(scene)

    def _emit_ambient(self, scene) -> None:
        """真正拼一条环境白描进这一场（**唯一实现**，两条路共用）。

        ★ 素材优先级（2026-10-07 定的，别改顺序）：
          ① `world.sound_design`（`crew/agents.Sound` 开拍前写好，"今天这一场
             听得见什么"）—— 它比罐头池贴这一天；
          ② 回落"时段 × 天气"的罐头池 `_AMBIENT`。
          罐头池是**按（时段, 天气）稳定取**的（`_stable_pick`）——
          同一天同一时段重复调用给同一句，不会一跳一换。
        ⚠ `SCRIPT_AMBIENT` 关掉时**一句都不产**（用户要能自己关）。

            English:
        Actually assemble one environmental line into this scene (**the single implementation**,
        shared by both paths).

        ★ Material priority (set 2026-10-07, do not reorder):
          ① `world.sound_design` (written by `crew/agents.Sound` before shooting starts: "what can be
             heard in today's scene") -- it fits this day better than the canned pool;
          ② fall back to the "time period x weather" canned pool `_AMBIENT`.
          The canned pool is taken **stably per (time period, weather)** (`_stable_pick`) -- the same
          call in the same period of the same day yields the same line, so it does not flicker beat
          to beat.
        ⚠ With `SCRIPT_AMBIENT` off, **nothing is emitted** (the user must be able to switch it off).
        """
        if not CFG.b('SCRIPT_AMBIENT'):
            return
        # ★★ **先问声音**（2026-10-07 审计补上）：今天这一场"听得见什么"
        #   由剧组的声音design定（`world.sound_design`，开拍前写好）。
        #   它比下面那池罐头句子更贴这一天 —— 那一池是按"时段 × 天气"
        #   写死的，连着几天同一个时段就会重复。
        #   这就是名册里 `sound.feeds='actor'` 那一行的落点：
        #   声音**不进人物的嘴**（人物不会说"现在有雨声"），
        #   而是变成场面本身的一部分。
        # [EN] ★★ **Ask about sound first** (added in the 2026-10-07 audit): what can be "heard" in today's
        # [EN] scene
        # [EN] is defined by the crew's sound design (`world.sound_design`, written before shooting starts).
        # [EN] It fits this day better than the canned sentence pool below —— that pool is keyed to "time
        # [EN] period × weather"
        # [EN] hardcoded, so the same time period on consecutive days will repeat.
        # [EN] This is where the `sound.feeds='actor'` row in the roster lands:
        # [EN] sound **does not enter the character's mouth** (characters won't say "there's rain now"),
        # [EN] but becomes part of the scene itself.
        line = self._pick_ambient_line()
        if line:
            scene.add(S.ambient(line,
                                place=(getattr(self.world, 'scene', '') or '')))

    def _ambient_candidates(self) -> list[str]:
        """这一天**所有可能**的环境句：声音层几句 + 罐头池几句（去重保序）。

        ★★★ 2026-10-17 新增。老实现只取**一句**（`_sound_line()` 里
          `_stable_pick(events, day, 'sound')` 的种子只有 day ⇒ 一整天算出来同一条），
          于是"这一场的声音"变成了"这一整天循环播放的那一句"：
          实测 3453 字里有 11 条环境，去重后 1 种。
          而 `Sound` 明明写了 3 条事件声 —— 素材是有的，是**取用方式**把它废掉了。
          现在把候选**全摊开**，交给 `_pick_ambient_line()` 轮换。

        [EN] ★★★ Added 2026-10-17. The old implementation took **one** line (inside
        [EN] `_sound_line()`, `_stable_pick(events, day, 'sound')` seeds on `day` alone => the same line
        [EN] for the whole day), so "the sound of this scene" became "the one sentence played on repeat
        [EN] all day": measured 11 ambient lines in a 3453-character day, 1 distinct. And `Sound` had
        [EN] written 3 event sounds -- the material was there, the **retrieval** wasted it. Now the
        [EN] candidates are laid out in full and handed to `_pick_ambient_line()` for rotation.

        ★★★ 2026-10-18：**不再把底噪/静默捆进每一条**（《雪国》实测的复读源头）。
          上一版把「底噪；这一下；该响没响的」拼成一条 ⇒ 三条候选**共用同样两截**，
          轮换只换了中间那句 ⇒ 正文里「该响的敲门声没有响」逐字出现好几次
          （那篇 263 字里出现 2 次 + 宣发那一行 1 次），评委的原话是
          「叙述者在替读者点题」。
          现在三样**各自成句、各说一次**：底噪一句、每条事件声一句、静默一句。
          拿不到的就跳过（素材没有就空着，不编）。
        [EN] ★★★ 2026-10-18: **stop bundling bed/silence into every candidate** (the repetition
        [EN] source measured on Snow Country). The previous version spliced "bed; this one; the thing
        [EN] that should have sounded" into one line, so three candidates **shared the same two
        [EN] clauses** and rotation only changed the middle one => "the knock that should have sounded
        [EN] did not" appeared verbatim several times in a 263-character piece (twice in the body plus
        [EN] once in the publicity line), and the judge called it "the narrator underlining the point
        [EN] for the reader". Now the three are **separate sentences, spoken once each**: one bed line,
        [EN] one line per event sound, one silence line. Anything missing is skipped (no material, no
        [EN] invention).
        """
        out: list[str] = []
        d = getattr(self.world, 'sound_design', None)
        if isinstance(d, dict) and d:
            bed = str(d.get('底噪') or '').strip()
            quiet = str(d.get('静默') or '').strip()
            events = [str(x).strip() for x in (d.get('事件声') or []) if str(x).strip()]
            if bed:
                out.append(bed)
            out.extend(events)
            if quiet:
                out.append(quiet)
        clock = getattr(self.world, 'clock', None)
        segment = clock.segment() if clock is not None else '上午'
        bank = _AMBIENT.get((segment,
                             _weather_bucket(getattr(self.world, 'weather', ''))))
        # ★★★ 2026-10-18：**先过一遍"这句放这儿成立吗"**（见 `_ambient_ok`）。
        #   实测《回声站》：深空站的密封值班室里写「日头渐高，街上的水汽一点点蒸散」。
        # [EN] ★★★ 2026-10-18: **filter by "does this line hold here" first** (see
        # [EN] `_ambient_ok`). Measured in 《回声站》: a sealed duty room in deep space got "the sun
        # [EN] climbs and the street's damp evaporates".
        _place = str(getattr(self.world, 'scene', '') or '')
        _indoor = any(w in _place for w in _INDOOR_WORDS)
        _modern = str(getattr(self.world, 'calendar', '') or '') == 'modern'
        out.extend(x for x in (bank or [])
                   if _ambient_ok(x, indoor=_indoor, modern=_modern))
        # 去重保序（声音层与罐头池偶尔会撞同一句）
        seen: set[str] = set()
        uniq: list[str] = []
        for x in out:
            if x and x not in seen:
                seen.add(x)
                uniq.append(x)
        return uniq

    def _pick_ambient_line(self) -> str:
        """挑一条环境句；冷却期内的全跳过，全在冷却 ⇒ 返回空串（宁可不写，也不刷屏）。

        ⚠ 这一条是"质量"而不是"功能"：功能上随便挑一句都行，但**同一句逐字重复**
          是读者第一眼就出戏的东西（2026-10-17 实测 11 条只有 1 种）。所以：
            · 优先挑**冷却期外**的（种子带"已取几条"，同一天也能轮换出不同句子）；
            · **全在冷却里 ⇒ 不写**。真人小说不会为了填满而重复上一句。
        ★ 2026-10-18 改的是"冷却多长"，不是"要不要冷却"：
          旧版把"用过"记成永久的，而候选池只有 1–5 条 ⇒ 一天之后再也没有环境句
          （长跑 1080 拍也只有 5 条）。现在按 `AMBIENT_REPEAT_EVERY` 条冷却，
          池子小也能持续渗出；设成 0 = 退回旧行为（永不复现）。
        [EN] ⚠ This is about **quality**, not function: functionally any line works, but
        [EN] **verbatim repetition** is the first thing a reader notices (measured: 11 lines,
        [EN] 1 distinct). So: prefer one **outside its cooldown** (seed carries "how many drawn"
        [EN] so the same day still rotates); **all cooling down => write nothing**.
        [EN] ★ 2026-10-18 changed "how long the cooldown is", not "whether there is one": the old
        [EN] version recorded "used" forever, and the pool is only 1-5 lines => after the first day
        [EN] there is never another ambient line (a 1080-beat run still got 5). Now it cools for
        [EN] `AMBIENT_REPEAT_EVERY` lines, so a small pool still seeps; 0 = old behavior.
        """
        cands = self._ambient_candidates()
        if not cands:
            return ''
        self._ambient_seq += 1
        gap = CFG.i('AMBIENT_REPEAT_EVERY')
        if gap <= 0:
            # ⚠ `0` 的语义是**永不复现**（退回旧行为），不是"不冷却"。
            #   第一版写成 `seq - used > 0`，那等于"上一次之后立刻可以再来" ⇒
            #   同一句每两条就出现一次，比旧行为还糟（C4 当场抓出来）。
            # [EN] ⚠ `0` means **never reappear** (the old behavior), not "no cooldown". The
            # [EN] first version used `seq - used > 0`, i.e. "usable again right after the
            # [EN] previous draw" -- the same line came back every other line, worse than the old
            # [EN] behavior (C4 caught it immediately).
            fresh = [x for x in cands if x not in self._ambient_used]
        else:
            fresh = [x for x in cands
                     if self._ambient_seq - self._ambient_used.get(x, -10 ** 6) > gap]
        if not fresh:
            return ''
        pick = _stable_pick(fresh, self.day, len(self._ambient_used), 'ambient')
        self._ambient_used[pick] = self._ambient_seq
        # 账本别无限长（文字不会删，但键会随场景变多）
        # [EN] Keep the ledger bounded (text is not removed, but keys grow with scenes)
        if len(self._ambient_used) > 400:
            if gap <= 0:
                self._ambient_used = {}
            else:
                self._ambient_used = {k: v for k, v in self._ambient_used.items()
                                      if self._ambient_seq - v <= gap}
        return pick

    def observe_time_jump(self, text: str) -> None:
        self._ensure_scene().add(S.Entry(S.TIME, text))

    def observe_note(self, text: str, *, anchors: dict | None = None) -> None:
        self._ensure_scene().add(S.note(text, anchors=anchors))

    # ══════════════════════════════════════════════════════════
    #  收尾
    # [EN] Wrap-up
    # ══════════════════════════════════════════════════════════
    def rollback(self, n: int) -> int:
        """**回档**：从尾部删掉最近 n 条词条，返回**真的删掉了几条**。

        用户 2026-10-07：「导演随时可以要求回档 即删除最近生成的一段戏」。

        为什么要做到**词条级**而不是"整天重来"：导演发现的问题通常很小
        （三个人说了同一句话、某个人连着发呆），删掉那几条重演就够了；
        整天重来会把好的部分一起扔掉，而且很贵。

        三条约定：
        ① **删到跨幕**：当前幕被删空时，回退到上一幕继续删 ——
           不这样的话"回档 6 条"在刚分过幕的时刻只能删掉一两条（而且静默少删）。
        ② **不碰 `_said` 去重台账**：那是"这个人这一天说过什么"的记录。
           回档之后重演时，他说回同一句会被护栏拦下 —— 那是**对**的
           （回档是为了不重复，不是为了允许重复）。
        ③ 返回**实际条数**：调用方（`sim/loop`）要拿它去同步屏幕上的行数。
           删不动（已经空了）就返回 0，让它知道"这次回档没生效"。
        
                English:
        **Rollback**: delete the most recent n entries from the tail, and return **how many were
        actually deleted**.
                User 2026-10-07: "The director can request a rollback at any time, i.e. delete the most recently generated stretch of drama."
                Why do it at the **entry level** rather than "redo the whole day": the problems the director finds are usually small
                (three people said the same line, someone spaced out twice in a row), so deleting those few entries and redoing it is enough;
                redoing the whole day throws out the good parts too, and it's expensive.
                Three conventions:
                ① **Delete across acts**: when the current act is emptied, fall back to the previous act and keep deleting ——
                   otherwise "rollback 6 entries" can only delete one or two at a moment right after an act break (and it silently under-deletes).
                ② **Don't touch the `_said` dedup ledger**: that's the record of "what this person said this day".
                   When redoing after a rollback, if he says the same line again it'll be blocked by the guardrail —— that's **correct**
                   (rollback is to avoid repetition, not to allow it).
                ③ Return the **actual count**: the caller (`sim/loop`) needs it to sync the number of lines on screen.
                   If nothing can be deleted (already empty), return 0, so it knows "this rollback had no effect".
        """
        want = int(n or 0)
        if want <= 0:
            return 0
        done = 0
        while done < want:
            if self._cur is not None and self._cur.entries:
                self._cur.entries.pop()
                done += 1
                continue
            if self._scenes:
                # 当前幕空了（或还没起幕）→ 退到上一幕继续删
                # [EN] The current scene is empty (or hasn't started yet) → step back to the previous scene and keep
                # [EN] deleting
                self._cur = self._scenes.pop()
                continue
            break                        # 真的一条都没有了
            # [EN] There really isn't a single one left
        return done

    def drop_entries(self, entries: list) -> int:
        """按**对象身份**撤掉指定的几条词条，返回真的撤掉了几条。

        与 `rollback(n)` 的分工：那个是"从尾部删 n 条"（导演回档用），
        这个是"删**这几条**"—— 审读拦下的是中间某一条，不是尾巴上的。

        用途（2026-10-08）：`sim/loop._script_review` 拦下一条不行的话/动作时，
        光"不推到屏幕上"是不够的 —— 屏幕与落盘的稿子必须一致（本项目的铁律），
        所以要从幕里**真的撤掉**。撤不干净的话，收工时写进
        `每天的生活/` 的剧本里还留着那句。

        搜索范围：当前幕 → 已收的幕（**从后往前**，最近的最可能）。
        
                English:
        Remove the specified entries **by object identity**, and return how many were actually removed.
                Division of labor with `rollback(n)`: that one is "delete n entries from the tail" (used for director rollback),
                this one is "delete **these entries**" —— what the review intercepts is some entry in the middle, not one at the tail.
                Use (2026-10-08): when `sim/loop._script_review` intercepts a bad line/action,
                merely "not pushing it to the screen" is not enough —— the screen and the script written to disk must match (this project's iron rule),
                so it must be **actually removed** from the act. If it isn't removed cleanly, then when work wraps up and it's written into
                Search range: current act → completed acts (**from back to front**, the most recent is most likely).
        """
        want = {id(e) for e in (entries or []) if e is not None}
        if not want:
            return 0
        done = 0
        for sc in ([self._cur] if self._cur is not None else []) + \
                list(reversed(self._scenes)):
            if not want:
                break
            keep: list = []
            for e in sc.entries:
                if id(e) in want:
                    want.discard(id(e))
                    done += 1
                    continue
                keep.append(e)
            sc.entries = keep
        return done

    def recent_entries(self, n: int = 20) -> list:
        """最近 n 条词条（**时间顺序**，最后一条最新）。给导演盯戏用。

        ⚠ 要连**当前幕**一起取（`scenes` 不含正在写的那一幕，见 `scenes`
          的说明）—— 只看 `_scenes` 会永远落后一幕，盯戏盯的是"刚才那几条"。
        
                English:
        The most recent n entries (**chronological order**, the last one is the newest). Used by the
        director to watch the drama.
                ⚠ Must fetch the **current act** along with it (`scenes` does not include the act currently being written, see the description of `scenes`) — looking only at `_scenes` will always lag one act behind, and scene-watching is about "those few just now".
                  looking only at `_scenes` will always lag one act behind, and scene-watching is about "those few just now".
        """
        out: list = []
        for sc in self._scenes:
            out.extend(getattr(sc, 'entries', None) or [])
        if self._cur is not None:
            out.extend(getattr(self._cur, 'entries', None) or [])
        k = int(n or 0)
        return out[-k:] if k > 0 else out

    def close_scene(self) -> S.SceneScript | None:
        """收当前幕（时段/地点变化时调）。
                English:
        Close the current act (called when time slot/location changes).
        """
        if self._cur is None:
            return None
        scene = self._cur
        scene.tension_after = float(getattr(self.world, 'tension', 0.0) or 0.0)
        self._scenes.append(scene)
        self._cur = None
        return scene

    def maybe_break(self, *, prev_clock: Any = None,
                    prev_place: str = '') -> bool:
        """该不该分幕？时段变了、地点变了 → 分。

        返回 True 表示刚刚分过幕（调用方随后可以继续写入新幕）。
        
                English:
        Should it split into an act? Time slot changed, location changed -> split.
                Returning True means an act was just split (the caller can then continue writing into the new act).
        """
        if self._cur is None:
            return False
        clock = getattr(self.world, 'clock', None)
        place = (getattr(self.world, 'scene', '') or '').strip()
        changed = False
        if prev_clock is not None and clock is not None:
            if getattr(prev_clock, 'shichen', '') != getattr(clock, 'shichen', ''):
                changed = True
        if prev_place and place and prev_place != place:
            changed = True
        if changed:
            self.close_scene()
            self.begin_scene(force=True)
            return True
        return False

    def flush(self) -> list[S.SceneScript]:
        """收尾并返回全部幕（当天结束时调）。
                English:
        Close out and return all acts (called at end of day).
        """
        self.close_scene()
        return self.scenes

    # ══════════════════════════════════════════════════════════
    #  小工具
    # [EN] small utility
    # ══════════════════════════════════════════════════════════
    def _ensure_scene(self) -> S.SceneScript:
        if self._cur is None:
            return self.begin_scene(force=True)
        return self._cur

    @staticmethod
    def _name_of(agent: Any) -> str:
        return (getattr(getattr(agent, 'ps', None), 'name', '')
                or getattr(agent, 'name', '') or '某人')

    @staticmethod
    def _action_text(act: Any) -> str:
        """把 Action 转成一句"他在做什么"。

        这是**骨架文本**：保证结构完整、不出现空槽，读得通但谈不上文采。
        分工是「规则保证结构，模型负责文笔」——

        ⚠ 2026-10-07 更正：这一段以前写着"「每天的生活」的 LLM 整理档
          （`NOVEL_LOG_MODEL`）会在此基础上润色成正式叙事"。**那个旋钮早就删了**
          （见 `tools/verify_config_sweep.py` 的假旋钮清单），所以那句注释**是假的**：
          骨架文本从来没有人给它润色过。

          真正在润色的是另外两条路（都在，都不是这个旋钮）：
            · 导出时 `export/novel_version.polish_manuscript`（`EXPORT_NOVEL_POLISH`）；
            · 剧组：当天**先**由小说作家写样章、剧作者写成能拍的剧本，
              **动作台词由演员（人物 Agent）自己产** —— 骨架文本只兜底空槽。
          （"先写样章再开拍"意味着骨架文本在正常路径上本来就很少露面。）
        
                English:
        Convert the Action into a sentence of "what he is doing".
                This is **skeleton text**: guarantees structural completeness, no empty slots, reads coherently but is hardly literary.
                The division of labor is "rules guarantee structure, the model is responsible for prose" ——
                ⚠ 2026-10-07 correction: this paragraph previously said "the LLM digest file of 'daily life'
                  (`NOVEL_LOG_MODEL`) would polish this into a formal narrative on top of it". **That knob was deleted long ago**
                  (see the fake knob list in `tools/verify_config_sweep.py`), so that comment **is false**:
                  the skeleton text has never been polished by anyone.
                  What is actually doing the polishing are two other paths (both exist, neither is this knob):
                    · At export time, `export/novel_version.polish_manuscript` (`EXPORT_NOVEL_POLISH`);
                    · Crew: on the day, **first** the novelist writes a sample chapter, the screenwriter writes it into a shootable script,
                      **action and dialogue are produced by the actors (character Agents) themselves** —— the skeleton text only fills empty slots.
                  ("Write the sample chapter first, then start shooting" means the skeleton text rarely shows up on the normal path anyway.)
        """
        verb = getattr(act, 'verb', '')
        target = getattr(act, 'target', '') or ''
        inner = getattr(act, 'inner_thought', '') or ''
        # ★★★ 2026-10-14（用户）：「正常小说…应该有…人物做的事情」——
        #   **模型给了描写就用描写**（`Action.detail`），没给才落回下面的骨架。
        #   ⚠ 这一行是"动作干瘪"的**结构性**解药：在它之前，
        #     `emote`/`interact`/`move` 无论模型多想写，都只能落成
        #     `神色变了变`/`转向X`/`去了X`（`Action` 以前**没有地方放描写**）。
        #   ⚠ 放在最前面 ⇒ **覆盖**下面所有分支（连 `think` 那句也一并走这条路，
        #     因为"一边想一边手上在做什么"确实该用描写）。
        # [EN] ★★★ 2026-10-14 (user): "a normal novel should have ... things the characters do" --
        # [EN] **if the model gave a description, use it** (`Action.detail`); only fall back to the
        # [EN] skeleton below when it did not.
        # [EN] ⚠ This line is the **structural** cure for "thin actions": before it, `emote` /
        # [EN]   `interact` / `move` could only become `expression shifted` / `turns toward X` /
        # [EN]   `went to X` no matter what the model wanted (`Action` had **nowhere to put a
        # [EN]   description**).
        # [EN] ⚠ Putting it first means it **overrides** every branch below (including the `think`
        # [EN] one, because "what his hands are doing while he thinks" deserves a description too).
        detail = str(getattr(act, 'detail', '') or '').strip()
        if detail:
            # ★★★ 2026-10-28：与 `sim/loop._verb_desc` 同一口径 —— 剥掉开头的"我"。
            #   剧本模式这边由调用方拼名字/人物，留着"我"就会成「张三我把壶搁下」。
            # [EN] ★★★ 2026-10-28: same convention as `sim/loop._verb_desc` -- strip the leading 我;
            # [EN] this path also prefixes the name, so keeping it yields "张三我把壶搁下".
            return _bare_detail(detail)
        if verb == 'move':
            return f'去了{target}' if target else '走开了'
        if verb == 'speak':
            return f'叫住{target}' if target else ''
        if verb == 'interact':
            # 不区分目标是人是物，用「转向」这类中性说法，
            # 否则会出现「和柜台打了照面」这种别扭的句子
            # [EN] Do not distinguish whether the target is a person or an object; use neutral wording like "turns
            # [EN] toward",
            # [EN] otherwise you get awkward sentences like "came face to face with the counter"
            return f'转向{target}' if target else '动了动'
        if verb == 'emote':
            return '神色变了变'
        if verb == 'wait':
            return '没动，也没出声'
        if verb == 'think':
            return inner[:60] if inner else '在想事情'
        return verb or '（无动作）'

    @staticmethod
    def _ongoing_text(act: Any) -> str:
        """已废弃：以前拿 `inner_thought` 当"说话时手上在做的事"，
        结果是**把心里想的当成他在做**（"· 动作 主角：（若今晚走不成…）"）。
        内心的东西归 `ASIDE`，不能冒充动作。保留空实现只为兼容旧调用。
                English:
        Deprecated: previously used `inner_thought` as "what the hands are doing while speaking",
                Inner things belong to `ASIDE`, they cannot impersonate actions. The empty implementation is kept only for compatibility with old calls.
        """
        return ''

    @staticmethod
    def _tone_of(agent: Any, act: Any) -> str:
        """语气提示：只从真实情绪状态推，不凭空加。
                English:
        Tone hint: infer only from the real emotional state, do not add out of thin air.
        """
        ps = getattr(agent, 'ps', None)
        emo = getattr(ps, 'emotion', None) or {}
        for key, thr, label in _EMOTION_TONE:
            try:
                if float(emo.get(key, 0.0)) >= thr:
                    return label
            except (TypeError, ValueError):
                continue
        return ''
