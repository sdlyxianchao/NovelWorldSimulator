# -*- coding: utf-8 -*-
"""对话插图 · 全彩文生图（四种方式里最贵的一种）。

四种方式的定位（用户定的）：
    关闭 < ASCII 画（占用最少，最难看）< PNG 矢量图 < **全彩文生图**（耗 token 最多）

这里走 **OpenAI 兼容的 `/images/generations`** 接口：`POST {base_url}/images/generations`，
body `{model, prompt, size, n:1}`，取回 `b64_json`（或 `url` 再下载）存盘。

三个必须记住的约定：

1. **同步客户端**。`image_hook` 是同步回调（在推演的事件循环里被调用），
   这里用 `httpx.Client` 而不是 `AsyncClient` —— 在 async 上下文里
   `asyncio.run()` 会直接报 "event loop is already running"。
   代价是生成期间会阻塞几秒，但这一档本来就是"最慢最贵"。
2. **失败一律返回 None**，由调用方降级成 PNG 矢量图 —— 用户的文章不能
   因为图片服务 502 就断在半路。
3. **接口不存在也算失败**：DeepSeek 这类只有 chat 的服务没有
   `/images/generations`，会 404 —— 同样降级，不抛异常。
4. **先看能力开关再发请求**：`LLM_CAP_IMAGE`（启动时按模型名自动校验）
   为假时 `ai_available()` 直接返回 false，一次网络请求都不发 ——
   "这个模型不出图"是**已知事实**，不该每次都用 404 去重新发现一遍。

English:
Dialogue illustration · full-color text-to-image (the most expensive of the four modes).
Positioning of the four modes (defined by the user):
    off < ASCII art (least resource usage, ugliest) < PNG vector art < **full-color text-to-image** (most token consumption)
Here we use the **OpenAI-compatible `/images/generations`** endpoint: `POST
{base_url}/images/generations`,
body `{model, prompt, size, n:1}`, retrieve `b64_json` (or `url` then download) and save to
disk.
Three conventions that must be remembered:
1. **Synchronous client**. `image_hook` is a synchronous callback (called within the inference event loop),
   so here we use `httpx.Client` rather than `AsyncClient` — in an async context
   `asyncio.run()` would directly raise "event loop is already running".
   The cost is blocking for a few seconds during generation, but this tier is inherently "slowest and most expensive".
2. **Failure always returns None**, and the caller degrades to PNG vector art — the user's article must not
   be cut off midway just because the image service returns 502.
3. **A nonexistent endpoint also counts as failure**: services like DeepSeek that only have chat do not have
   `/images/generations` and will return 404 — likewise degrade, do not throw an exception.
4. **Check the capability switch before sending the request**: when `LLM_CAP_IMAGE`
(auto-validated at startup by model name)
   is false, `ai_available()` directly returns false, and not a single network request is sent —
   "this model does not generate images" is a **known fact** and should not be rediscovered via a 404 every time.
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

_LOG = logging.getLogger('nws.imagegen')

# 场景描述的中文画风词：跟界面/背景图同一套彩墨语言
# [EN] Chinese art style words for scene descriptions: the same ink-wash color language as the
# [EN] UI/background images.
STYLE_PROMPT = (
    'Chinese ink-and-wash painting (彩墨江南), soft spring palette, '
    'paper texture, misty atmosphere, no text, no watermark, '
    'cinematic wide shot, gentle light'
)
# ⚠ 2026-10-10：这条**只保留给别处引用**（`crew/studio` 与判据会读它）。
#   新增的负向词走 `promptkit.negatives()` —— 它在原有"别画出字"那一档之外，
#   补了**通用质量档**（lowres / bad anatomy / extra fingers…，第 03 类第 7 条）。
#   两条并存不冲突：`promptkit.negatives()` 里已经包含了下面这句的内容。
# [EN] ⚠ 2026-10-10: this line is **kept only for reference elsewhere** (`crew/studio` and the criteria
# [EN] read it).
# [EN] Newly added negative terms go through `promptkit.negatives()` — beyond the original "don't draw
# [EN] text" tier,
# [EN] it adds a **general quality tier** (lowres / bad anatomy / extra fingers…, category 03 item 7).
# [EN] The two coexist without conflict: `promptkit.negatives()` already includes the content of the
# [EN] line below.
NEGATIVE = 'no text, no letters, no watermark, no signature, no frame'


def build_prompt(subject: str, *, weather: str = '', time_label: str = '',
                 place: str = '', crew: str = '',
                 no_character: bool = False, style_boost: int = 1) -> str:
    """把一幕的要素拼成提示词（保持简短，省 token）。

    `crew`（2026-10-07 加）＝ 剧组里「美术 + 道具」给的这段前缀
    （画风与主色、这一场可见的物件，见 `crew/studio.Studio.image_prefix`）。
    **这是道具/美术真正落到工具上的那一步**：写进 MD 不算接线，写进提示词才算。

    ⚠ 放在**最前**：文生图对靠前的词权重大；而"这部戏长什么样"是全局约束，
      压在后面的具体描述之前才不会被冲淡。

    2026-10-10 新增两个开关（第 03 类第 4、5 条）：

    `no_character=True` —— **空镜**（画面里只有物、没有人）。
      这一档以前不存在，于是"更鼓空响""空荡的院子"这类镜头**必然画出人来**，
      与剧本直接矛盾。空镜时**整段丢掉人物形象**（不是写"不要人"，是根本不提）。

    `style_boost=2` —— 把**画风那一句**再说一遍，用于"更重画风、不那么重具体描述"。
      ★ 文生图的提示词**没有数值权重**，行业里表达权重只有**位置**和**重复**
        两个土办法；所以这里如实把它做成"说一遍还是两遍"，不假装是连续可调。
    
        English:
    Assemble the elements of a scene into a prompt (keep it short to save tokens).
        `crew` (added 2026-10-07) = the prefix given by "art + props" in the crew
        (art style and primary colors, visible props in this scene, see `crew/studio.Studio.image_prefix`).
        **This is the step where props/art actually lands on the tool**: writing it into the MD is not wiring it up; writing it into the prompt is.
        ⚠ Place it **at the very front**: text-to-image gives more weight to earlier words; and "what this play looks like" is a global constraint,
          so it must precede the specific descriptions to avoid being diluted.
    2026-10-10 added two switches (category 03 items 4, 5):
    `no_character=True` — **empty shot** (only objects in the frame, no people).
        This tier did not exist before, so shots like "the watch drum sounds in vain" and "the empty courtyard" would **necessarily draw people**,
          directly contradicting the script. In an empty shot, **discard the character description entirely** (not "don't draw people", but simply don't mention them).
    `style_boost=2` — say the **art style sentence** again, for "more emphasis on art style, less on
    specific descriptions".
        ★ Text-to-image prompts have **no numeric weights**; in the industry, expressing weight has only two crude methods:
          **position** and **repetition**; so here we honestly implement it as "say it once or twice" rather than pretending it is continuously tunable.
    """
    from image_gen import promptkit                                 # noqa: PLC0415
    bk = promptkit.StyleBook(STYLE_PROMPT)
    return promptkit.compose(
        subject,
        book=bk,
        subject_line=crew,
        place=place, time_label=time_label, weather=weather,
        no_character=no_character, style_boost=style_boost)


def ai_available() -> tuple[bool, str]:
    """能不能走文生图（没有 key / 没配模型就直说，省得白等一次请求）。

    判据里有 **`LLM_CAP_IMAGE`**（模型能力，启动时按模型名自动校验，
    见 `llm/capabilities.py`）：模型本身就不出图时，这里直接拦下 ——
    省掉一次注定 404 的请求，也让界面能提前说清「不支持」而不是事后再降级。
    
        English:
    Whether text-to-image is possible (if there is no key / no model configured, say so directly to
    avoid a wasted request).
        The criteria include **`LLM_CAP_IMAGE`** (model capability, auto-validated at startup by model name,
        see `llm/capabilities.py`): when the model itself does not generate images, block it here directly —
        saving a request doomed to 404, and letting the UI state "not supported" upfront rather than degrading afterward.
    """
    from config import CFG
    if not (CFG.s('LLM_API_KEY') or '').strip():
        return False, '没有配置 API Key'
    if (CFG.s('MOCK_LLM') or '').lower() in ('true', '1', 'yes'):
        return False, '当前是演示模式（MOCK_LLM），不联网出图'
    if not CFG.b('LLM_CAP_IMAGE'):
        return False, ('当前模型未标记「支持文生图」（LLM_CAP_IMAGE=false）——'
                       '可在「天机 · LLM 能力」里查看，或把 IMAGE_AI_MODEL '
                       '改成出图模型（如 gpt-image-1 / dall-e-3）')
    if not (CFG.s('IMAGE_AI_MODEL') or '').strip():
        return False, '没有配置文生图模型（IMAGE_AI_MODEL）'
    return True, ''


def _bill_image(model: str, purpose: str) -> None:
    """把**一次图片生成**记进全局台账（2026-10-19 补的缺口）。

    ★★★ 为什么必须补：图片调用走的是这里**自己建的 httpx**（不是 `llm/router`），
      而 `Ledger.add` 是全项目唯一的记账汇合点 —— 于是插图花了多少钱，
      用量窗口里**一分都看不到**（用户问"统计有没有缺"，这是第二处确凿的缺）。

    ⚠ 口径（想清楚才写的）：
      · 图片按**张**计费，不按 token ⇒ `in_tok`/`out_tok` **留 0**，
        硬塞一个"估算 token"会让整张表的 token 总量对不上；
      · 钱落在 `cost` 上：`IMAGE_AI_UNIT_PRICE`（元/张）×1；**没填就是 0**；
      · `purpose` 用 `image` / `image_edit` 区分文生图与图生图（复盘要看这个比例）。
    ⚠ 只记**成功的那一次**（失败的回滚在下游，记了会让"张数"虚高）。
    ⚠ 失败不抛（旁路纪律）。
    [EN] ★★★ Why this must be added: image calls use **this module's own httpx** (not
    [EN] `llm/router`), and `Ledger.add` is the only accounting convergence point -- so how much
    [EN] illustrations cost was **invisible** in the usage window (the user asked "is anything
    [EN] missing"; this is the second confirmed gap).
    [EN] ⚠ Convention (thought through): images bill **per image**, not per token => `in_tok` /
    [EN] `out_tok` stay 0 (stuffing an estimate would break the token totals). Money goes into
    [EN] `cost` = `IMAGE_AI_UNIT_PRICE` x 1, and **0 when unset**. `purpose` distinguishes
    [EN] `image` / `image_edit`. ⚠ Only the **successful** call is recorded. ⚠ Never throws.
    """
    try:
        from llm import usage as U
        price = 0.0
        try:
            price = float(CFG.f('IMAGE_AI_UNIT_PRICE') or 0.0)
        except Exception:                                        # noqa: BLE001
            price = 0.0
        U.record(model=str(model or 'image'), purpose=str(purpose),
                 in_tok=0, out_tok=0, cost=max(0.0, price), tier='image')
    except Exception:                                            # noqa: BLE001
        pass


def generate_ai_image(prompt: str, out_path: Path,
                      size: str | None = None,
                      reference: 'Path | str | None' = None) -> Path | None:
    """生成一张图并存盘；任何失败都返回 `None`（调用方降级）。

    `reference` —— **图生图（image-to-image）参照图**：视觉参考图（visref）为
    这一场/这个人产的一致性参考图，传进来走 `/images/edits` 让这一镜的画风/人物
    与参考图对齐（开源漫剧流程里"分镜→视觉→生图"的统一参照）。
    没有（默认）就走原来的 `/images/generations` 文生图；参照图无效/图生图失败
    也**降级为普通文生图**，不丢这一镜。

        English:
    Generate an image and save it to disk; any failure returns `None` (the caller degrades).
    `reference` -- image-to-image anchor (visual reference art); routes to `/images/edits`.
    """
    from config import CFG
    ok, why = ai_available()
    if not ok:
        _LOG.info('文生图跳过：%s', why)
        return None

    # ★ 图生图（P3，2026-10-15）：有有效参照图就走 `/images/edits`，
    #   让这一镜和视觉参考图对齐；失败不抛异常，降级为普通文生图。
    # [EN] image-to-image: with a valid reference, route to `/images/edits`; on failure degrade.
    _ref = None
    if reference is not None:
        try:
            _rp = Path(reference)
            if _rp.is_file():
                _ref = _rp
        except Exception:                                # noqa: BLE001
            _ref = None
    if _ref is not None:
        _edited = _generate_ai_image_edit(prompt, out_path, _ref, size)
        if _edited is not None:
            return _edited
        _LOG.info('图生图不可用，降级为普通文生图')

    # base_url 里已经含 `/v1`（与 `llm/router.py` 同一约定：它拼的是
    # `{base_url}/chat/completions`），所以这里直接接 `/images/generations`。
    # [EN] base_url already contains `/v1` (same convention as `llm/router.py`: it concatenates
    # [EN] `{base_url}/chat/completions`), so here we append `/images/generations` directly.
    base = (CFG.s('LLM_BASE_URL') or '').rstrip('/')
    url = f'{base}/images/generations'
    model = CFG.s('IMAGE_AI_MODEL')
    payload = {
        'model': model,
        'prompt': prompt,
        'n': 1,
        'size': size or CFG.s('IMAGE_AI_SIZE') or '1024x1024',
    }
    headers = {
        'Authorization': f'Bearer {CFG.s("LLM_API_KEY")}',
        'Content-Type': 'application/json',
    }
    try:
        import httpx
        timeout = max(30, min(300, CFG.i('LLM_TIMEOUT_SECONDS') * 4))
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                _LOG.warning('文生图失败 HTTP %s: %s', resp.status_code,
                             resp.text[:200])
                return None
            data = resp.json()
    except Exception as e:                                  # noqa: BLE001
        _LOG.warning('文生图请求异常（将降级为 PNG）：%r', e)
        return None

    items = (data or {}).get('data') or []
    if not items:
        _LOG.warning('文生图返回里没有 data：%s', str(data)[:200])
        return None
    item = items[0]

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if item.get('b64_json'):
            out_path.write_bytes(base64.b64decode(item['b64_json']))
        elif item.get('url'):
            import httpx
            with httpx.Client(timeout=120) as client:
                r = client.get(item['url'])
                r.raise_for_status()
                out_path.write_bytes(r.content)
        else:
            _LOG.warning('文生图返回里既没有 b64_json 也没有 url')
            return None
    except Exception as e:                                  # noqa: BLE001
        _LOG.warning('文生图落盘失败（将降级）：%r', e)
        return None

    _LOG.info('文生图完成：%s（%d 字节）', out_path.name, out_path.stat().st_size)
    # ★ 只在**落盘成功**之后记一笔（失败那次不记，否则"张数"会虚高）。
    # [EN] Record only after the file **landed** (a failed attempt would inflate the count).
    _bill_image(model, 'image')
    return out_path


def _generate_ai_image_edit(prompt: str, out_path: Path,
                            ref_path: Path, size: str | None) -> Path | None:
    """图生图（image-to-image）：把 `ref_path` 当参照，走 `/images/edits`。

    任何失败都返回 `None`（调用方会降级为普通文生图，不丢这一镜）。
        English:
    image-to-image: use `ref_path` as anchor via `/images/edits`; any failure returns `None`.
    """
    from config import CFG
    base = (CFG.s('LLM_BASE_URL') or '').rstrip('/')
    url = f'{base}/images/edits'
    model = CFG.s('IMAGE_AI_MODEL')
    payload = {
        'model': model,
        'prompt': prompt,
        'n': 1,
        'size': size or CFG.s('IMAGE_AI_SIZE') or '1024x1024',
    }
    headers = {'Authorization': f'Bearer {CFG.s("LLM_API_KEY")}'}
    try:
        import httpx
        timeout = max(30, min(300, CFG.i('LLM_TIMEOUT_SECONDS') * 4))
        with httpx.Client(timeout=timeout) as client:
            with ref_path.open('rb') as fh:
                resp = client.post(
                    url, data=payload,
                    files={'image': (ref_path.name, fh, 'image/png')},
                    headers=headers)
            if resp.status_code >= 400:
                _LOG.warning('图生图失败 HTTP %s（降级为文生图）：%s',
                             resp.status_code, resp.text[:200])
                return None
            data = resp.json()
    except Exception as e:                                  # noqa: BLE001
        _LOG.warning('图生图请求异常（降级为文生图）：%r', e)
        return None

    items = (data or {}).get('data') or []
    if not items:
        _LOG.warning('图生图返回里没有 data：%s', str(data)[:200])
        return None
    item = items[0]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if item.get('b64_json'):
            out_path.write_bytes(base64.b64decode(item['b64_json']))
        elif item.get('url'):
            import httpx
            with httpx.Client(timeout=120) as client:
                r = client.get(item['url'])
                r.raise_for_status()
                out_path.write_bytes(r.content)
        else:
            _LOG.warning('图生图返回里既没有 b64_json 也没有 url')
            return None
    except Exception as e:                                  # noqa: BLE001
        _LOG.warning('图生图落盘失败（降级为文生图）：%r', e)
        return None
    _LOG.info('图生图完成：%s（%d 字节）', out_path.name, out_path.stat().st_size)
    # ★ 图生图**单独记一个 purpose**（它比文生图贵一倍上下，混在一起就没法复盘）。
    # [EN] Image-to-image gets its **own purpose** (roughly twice the price of text-to-image;
    # [EN] merging them makes review impossible).
    _bill_image(model, 'image_edit')
    return out_path
