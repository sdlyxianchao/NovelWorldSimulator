# -*- coding: utf-8 -*-
"""对话插图的**调度层**：按「对话图片」这一项设置，决定出不出图、出哪种图。

四种方式（用户定的，界面上的名字就是左边这四个词）：

| 值 | 名字 | 怎么出 | 代价 |
|---|---|---|---|
| `off`   | 关闭        | 不出图（**含肖像**） | 0 |
| `ascii` | ASCII 画    | **场景**用字符画 `.txt`（`ascii_art.py`），中栏用等宽字显示 | 占用最少，也最难看 |
| `png`   | PNG 矢量图  | **场景**用本地彩墨插画 `.png`（`scene.py`，按地点/天气/时段画） | 0，几毫秒 |
| `ai`    | 全彩文生图  | **场景**调 `/images/generations`（`ai.py`） | 耗 token 最多 |

**人物肖像不受这四档管**（用户的明确要求，见下）：
**一律走文生图**，在**开卷时一次性生成**、存 `<项目>/肖像/`、之后各轮复用；
模型不支持文生图时**明说不支持，这一段不插肖像图**（不塞本地画的头像凑数）。
详见 `image_gen/portraits.py`。

**设置存在项目文件里**（`.nwsproj` 的 `[项目] 对话图片=`），因为
"这本书要不要配图、配哪种"是**项目自己的事**，不该被别的项目或全局设置带跑。

调用方拿到的是一个 `(kind, key) -> path|None` 的同步回调，直接交给
`SceneBuilder(image_hook=...)`。新回调还支持第三个可选参数 `ctx`：
`{"place":..., "weather":..., "time_label":..., "cast":...}` ——
有了它，插图才能"这一段在渡口下着雨"和"这一段在堂内"画得不一样。

English:
The **scheduling layer** for dialogue illustrations: based on the "dialogue images" setting,
decides whether to generate images and which kind.
Four modes (defined by the user; the UI names are exactly the four words on the left):
| value | name | how it generates | cost |
|---|---|---|---|
| `off`   | off       | no image (**including portraits**) | 0 |
| `ascii` | ASCII art | **scene** uses character art `.txt` (`ascii_art.py`), displayed in monospace font in the middle column | least usage, also ugliest |
| `png`   | PNG vector art | **scene** uses local colored-ink illustration `.png` (`scene.py`, drawn by location/weather/time-of-day) | 0, a few milliseconds |
| `ai`    | full-color text-to-image | **scene** calls `/images/generations` (`ai.py`) | uses the most tokens |
**Character portraits are not governed by these four tiers** (the user's explicit requirement,
see below):
**always go through text-to-image**, generated **once at book-opening time**, stored in
`<project>/portraits/`, reused in later rounds;
when the model does not support text-to-image, **say so explicitly and do not insert a portrait
image for this section** (do not fake it with a locally drawn avatar).
See `image_gen/portraits.py` for details.
"whether this book should have illustrations, and which kind" is **the project's own business**
and should not be dragged around by other projects or global settings.
The caller receives a synchronous callback `(kind, key) -> path|None`, passed directly to
`SceneBuilder(image_hook=...)`. The new callback also supports a third optional parameter `ctx`:
`{"place":..., "weather":..., "time_label":..., "cast":...}` —
with it, illustrations can draw "this section is at the ferry in the rain" and "this section is
inside the hall" differently.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

_LOG = logging.getLogger('nws.imagegen')

MODES = ('off', 'ascii', 'png', 'ai')

# 界面上的名字与说明（**界面上不许出现 off/ascii 这些变量名**）
# [EN] The name and description shown in the UI (**variable names like off/ascii must not appear in the
# [EN] UI**)
MODE_LABELS = {
    'off': '关闭',
    'ascii': 'ASCII 画',
    'png': 'PNG 矢量图',
    'ai': '全彩文生图',
}
MODE_NOTES = {
    'off': '不生成任何图片（含人物肖像）—— 最省，只有文字',
    'ascii': '场景用字符画拼，占用最少也最难看；人物肖像仍走文生图',
    'png': '场景用本地彩墨插画（不花 token）；人物肖像仍走文生图',
    'ai': '场景与人物肖像都交给模型画 —— 最好看，耗 token 最多',
}

# 肖像这一档**独立于上面四档**（用户的明确要求）：
#   · 「关闭」= 什么图都不要 → 连肖像也不生成；
#   · 其余三档，四档只管**场景**插图，**肖像一律走文生图**；
#   · 文生图用不了 → 不出图（**也不另写人物介绍**，那由开场卡负责）。
# 原因：本地 Pillow 画的那个几何头像用户觉得"太难看"，已彻底不作为对话肖像。
# [EN] The portrait tier is **independent of the four tiers above** (the user's explicit requirement):
# [EN] · "off" = no images at all -> not even portraits are generated;
# [EN] · For the other three tiers, the four tiers only govern **scene** illustrations; **portraits
# [EN] always go through text-to-image**;
# [EN] · If text-to-image is unavailable -> no image (and **no separate character intro either**; that
# [EN] is the opening card's job).
# [EN] Reason: the user found the geometric avatar drawn locally with Pillow "too ugly", so it is no
# [EN] longer used as a dialogue portrait at all.
PORTRAIT_ALWAYS_AI = True


def normalize_mode(value: str | None) -> str:
    v = (value or '').strip().lower()
    return v if v in MODES else ''


def effective_mode(project=None) -> str:
    """算出生效的模式：**项目文件里的那一项优先**。

    项目里没设（旧项目、新建项目）时：
      · `.env` 的 `SCRIPT_IMAGES=off` → 关闭（尊重老开关）
      · 否则 → `png`（本地画，零成本 —— 原来对话里的插图就是这一档）
    
        English:
    Compute the effective mode: **the entry in the project file takes priority**.
        When the project has no setting (old projects, new projects):
          · `.env`'s `SCRIPT_IMAGES=off` -> off (respect the old switch)
          · otherwise -> `png` (local drawing, zero cost — the original dialogue illustrations were this tier)
    """
    from config import CFG
    v = normalize_mode(getattr(project, 'image_mode', '') if project else '')
    if v:
        return v
    if (CFG.s('SCRIPT_IMAGES') or '').strip().lower() == 'off':
        return 'off'
    return 'png'


def make_image_hook(project=None, run=None, *,
                    on_log: Callable[[str], None] | None = None
                    ) -> Callable[..., str | None]:
    """造一个插图回调（交给 `SceneBuilder(image_hook=...)`）。

    图片落在 `<运行文件夹>/插画/` 下，**同一幕同一个人只画一次**（按文件名去重）：
    推演一天可能几十次触发，每次都重画就白费了。
    
        English:
    Build an illustration callback (passed to `SceneBuilder(image_hook=...)`).
        Images land under `<run folder>/illustrations/`, **the same person in the same scene is drawn only once** (deduplicated by filename):
        simulating a day may trigger dozens of times; redrawing every time is wasted work.
    """
    mode = effective_mode(project)
    out_dir = (Path(run.root) / '插画') if run is not None else None

    def _log(msg: str) -> None:
        _LOG.info(msg)
        if on_log:
            try:
                on_log(msg)
            except Exception:                               # noqa: BLE001
                pass

    if mode == 'off' or out_dir is None:
        if mode == 'off':
            _log('对话插图：关闭（不出图）')
        return lambda kind, key, ctx=None: None

    _portrait_warned = False

    def _portrait_why() -> str:
        """肖像拿不到图时，**如实说清是哪一种原因**（界面要照原样显示）。
                English:
        When a portrait cannot get an image, **state clearly which cause it is** (the UI must display it
        as-is).
        """
        from image_gen.portraits import load_manifest
        m = load_manifest(project) if project is not None else {}
        if not m:
            return '尚未在开卷时生成肖像'
        if not m.get('支持文生图'):
            return str(m.get('不支持原因') or '模型不支持文生图')
        failed = m.get('失败') or []
        if failed:
            return str(failed[0].get('原因') or '文生图调用失败')
        return '肖像文件缺失'

    def hook(kind: str, key: str, ctx: dict | None = None) -> str | None:
        nonlocal _portrait_warned
        ctx = ctx or {}
        place = ctx.get('place') or (key if kind == 'scene' else '')
        weather = ctx.get('weather', '')
        time_label = ctx.get('time_label', '')
        cast = ctx.get('cast', 0)
        # ★ 剧组（2026-10-07）：美术 + 道具在这一场留下的两个信号。
        #   `crew` = 画风与主色的前缀（进文生图提示词）；
        #   `props` = 这一场可见的物件名（进本地画法的要素匹配 + 提示词）。
        #   两个都拿不到时是空值，各分支照老路走（**不塞假的**）。
        # [EN] ★ crew (2026-10-07): the two signals art + props leave in this scene.
        # [EN] `crew` = prefix for art style and main color (goes into the text-to-image prompt);
        # [EN] `props` = names of objects visible in this scene (used for element matching in the local drawing
        # [EN] method + prompt).
        # [EN] When neither is available it is empty, and each branch follows the old path (**no faking it**).
        crew_line = str(ctx.get('crew') or '').strip()
        props = list(ctx.get('crew_props') or [])
        safe = ''.join(ch for ch in str(key) if ch not in '\\/:*?"<>|').strip() or kind

        if kind == 'portrait':
            # 肖像**只用开卷时生成好的那一张**（`<项目>/肖像/<姓名>.png`），
            # 项目级共用 —— 同一个人不会两轮换一张脸。
            # [EN] Portraits **use only the one generated at book-opening time**
            # [EN] (`<project>/portraits/<name>.png`),
            # [EN] shared at the project level — the same person will not change faces between rounds.
            if project is not None:
                from image_gen.portraits import has_portrait, portrait_path
                if has_portrait(project, str(key)):
                    return str(portrait_path(project, str(key)))
            # 没有图：**不出图**（2026-10-07 起也不再另写一段人物介绍 ——
            # 人物介绍由每轮开跑时那张开场卡统一负责，正文里再来一遍就是
            # 同一批信息说两次）。
            # 原因**只说一次**（不然每出场一个人刷一行，把正文淹了）。
            # [EN] No image: **no image** (as of 2026-10-07, no separate character intro is written either —
            # [EN] character intros are handled uniformly by the opening card generated each round; repeating it in
            # [EN] the body would be
            # [EN] saying the same batch of information twice).
            # [EN] The reason is **stated only once** (otherwise every character appearing spawns a line and drowns
            # [EN] the body text).
            if not _portrait_warned:
                _portrait_warned = True
                _log(f'肖像：文生图不可用（{_portrait_why()}），这一段不插肖像图')
            return None

        stem = f'场景_{safe}'
        if mode == 'ascii':
            path = out_dir / f'{stem}.txt'
            if path.exists():
                return str(path)
            try:
                from image_gen.ascii_art import save_ascii
                p = save_ascii(path, place or str(key), weather=weather,
                               time_label=time_label, cast=cast)
                _log(f'ASCII 画：{Path(p).name}')
                return p
            except Exception as e:                          # noqa: BLE001
                _log(f'ASCII 画生成失败：{e!r}')
                return None

        if mode == 'ai':
            path = out_dir / f'{stem}.png'
            if path.exists():
                return str(path)
            try:
                from image_gen.ai import (ai_available, build_prompt,
                                          generate_ai_image)
                # 先问一句"为什么不能出图"：读日志的人要能分清
                # 「模型本来就不出图」和「这次请求失败了」—— 两者的下一步完全不同。
                # [EN] First ask "why can't it generate an image": readers of the log must be able to distinguish
                # [EN] "the model simply does not generate images" from "this request failed" — the next steps for the
                # [EN] two are completely different.
                ok_ai, why = ai_available()
                if not ok_ai:
                    _log(f'文生图不可用（{why}），降级为本地 PNG 矢量图')
                # ★ 美术 + 道具 → 提示词前缀（见 `build_prompt` 的 `crew` 参数）
                # [EN] ★ art + props -> prompt prefix (see the `crew` parameter of `build_prompt`)
                prompt = build_prompt(place or str(key), weather=weather,
                                      time_label=time_label, crew=crew_line)
                # ★ 图生图参照（P3，2026-10-15）：把这一天的视觉参考里当前场的
                #   参考图当 image-to-image 锚点，让这一镜画风和参考图对齐。
                #   没有（默认）就走普通文生图。
                # [EN] image-to-image anchor from the day's visual reference.
                _ref = ctx.get('visref') or None
                p = generate_ai_image(prompt, path, reference=_ref)
                if p:
                    _log(f'文生图：{p.name}')
                    return str(p)
                _log('文生图调用未返回图片，降级为本地 PNG 矢量图')
            except Exception as e:                          # noqa: BLE001
                _log(f'文生图异常（降级为 PNG）：{e!r}')
            # 降级路径：本地画
            # [EN] Fallback path: local drawing
            mode_png = out_dir / f'{stem}.png'
            try:
                from image_gen.scene import save_scene
                p = save_scene(mode_png, place or str(key), weather=weather,
                               time_label=time_label, cast=cast, props=props)
                return p
            except Exception as e:                          # noqa: BLE001
                _log(f'PNG 插画生成失败：{e!r}')
                return None

        # png（默认档）
        # [EN] png (default tier)
        path = out_dir / f'{stem}.png'
        if path.exists():
            return str(path)
        try:
            from image_gen.scene import save_scene
            p = save_scene(path, place or str(key), weather=weather,
                           time_label=time_label, cast=cast, props=props)
            _log(f'PNG 插画：{Path(p).name}')
            return p
        except Exception as e:                              # noqa: BLE001
            _log(f'PNG 插画生成失败：{e!r}')
            return None

    hook.takes_ctx = True       # type: ignore[attr-defined]
    return hook
