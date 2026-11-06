# -*- coding: utf-8 -*-
"""人物肖像 · **开卷时一次性生成**（文生图）。

为什么单独一个模块
------------------
肖像和"场景插图"是两件事，取值逻辑完全不同：

| | 场景插图（`scene.py` / `hook.py`） | **人物肖像（本模块）** |
|---|---|---|
| 什么时候要 | 推演途中，换地点 / 换幕 | **开卷时一次**，之后永不重画 |
| 存在哪 | `<运行文件夹>/插画/`（每轮一份） | **`<项目>/肖像/`（整本书共用）** |
| 为什么 | 同一地点的图每轮都可能不同 | 同一个人**不能两轮换一张脸** |
| 拿不到图怎么办 | 本地画 / 字符画 / 不出图 | **明说不支持，这一段不插肖像** |

用户的原话（三条硬约束，改之前先读）：

1. **肖像一律走文生图** —— 本地 Pillow 画的那个几何头像太难看，**不再用作对话肖像**。
2. **只在开卷时生成一次**，后续轮次直接复用（`<项目>/肖像/` 里的文件就是缓存）。
3. **模型不支持文生图就说明白**，然后用**文字**代替（不是偷偷换成本地图）。

「模型不支持」的四种情形（`ai_available()` 判断，都是**预期内**的，不抛异常）：
没配 API Key / 演示模式 / 没配 `IMAGE_AI_MODEL` / 接口 404（DeepSeek 这类只有 chat 的服务）。

产物
----
```
<项目>/
└── 肖像/
    ├── 主角.png          ← 文生图结果（1024²，按需缩放显示）
    ├── 柳氏.png
    └── 肖像清单.md        ← 给人看：谁成了、谁没成、为什么
       肖像清单.json      ← 给程序读：hook 靠它知道"这个人的肖像到底能不能用"
```

English:
Character portraits · **generated once at book opening** (text-to-image).
Why a separate module
------------------
Portraits and "scene illustrations" are two different things, with completely different value
logic:
| | Scene illustrations (`scene.py` / `hook.py`) | **Character portraits (this module)** |
|---|---|---|
| When needed | During deduction, changing location / changing act | **Once at book opening**, never redrawn afterward |
| Where stored | `<run folder>/插画/` (one per round) | **`<project>/肖像/` (shared across the whole book)** |
| Why | Images of the same location may differ each round | The same person **must not change face between rounds** |
| What if no image | Local drawing / ASCII art / no image | **Explicitly say unsupported, do not insert a portrait for this section** |
The user's exact words (three hard constraints, read before changing):
1. **Portraits always use text-to-image** - the geometric avatar drawn locally with Pillow is too ugly, **no longer used as dialogue portraits**.
2. **Generate only once at book opening**, reuse directly in subsequent rounds (the files in `<project>/肖像/` are the cache).
3. **If the model does not support text-to-image, say so clearly**, then substitute with **text** (not secretly switch to a local image).
The four cases of "model unsupported" (`ai_available()` check, all **expected**, no exceptions
raised):
No API Key configured / demo mode / no `IMAGE_AI_MODEL` configured / API 404 (services like
DeepSeek that only have chat).
Artifacts
----
```
<project>/
└── 肖像/
    ├── 主角.png          ← text-to-image result (1024², scaled on demand for display)
    ├── 柳氏.png
    └── 肖像清单.md        ← for humans: who succeeded, who failed, why
       肖像清单.json      ← for programs: hook uses it to know "whether this person's portrait is usable"
```
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from util.io import atomic_write_text, ensure_dir
from util.text import now_str

_LOG = logging.getLogger('nws.imagegen')

# 肖像目录名（项目级；**别改**，改了等于把老项目的肖像全丢了）
# [EN] Portrait directory name (project-level; **do not change**, changing it means losing all
# [EN] portraits of old projects)
PORTRAIT_DIRNAME = '肖像'
MANIFEST_MD = '肖像清单.md'
MANIFEST_JSON = '肖像清单.json'

# 画风词：跟界面/背景图同一套彩墨语言。**固定**，不随正文风格卡变
# （风格卡说的是"文风"——句长、视角、词汇偏好，跟"画出来什么样"没关系）。
# [EN] Style words: same set of ink-wash color language as the UI/background images. **Fixed**, does
# [EN] not change with the body text style card
# [EN] (The style card talks about "writing style" - sentence length, point of view, vocabulary
# [EN] preference, it has nothing to do with "what it looks like when drawn").
ART_STYLE = (
    'Chinese ink-and-wash portrait (彩墨人物), half-body front view, '
    'soft spring palette, rice-paper texture, gentle light, clean background, '
    'detailed face, historically plausible clothing'
)
NEGATIVE = ('no text, no letters, no watermark, no signature, no frame, '
            'no extra fingers, not a photograph')


# ══════════════════════════════════════════════════════════════
#  路径与清单
# [EN] Paths and manifest
# ══════════════════════════════════════════════════════════════
def portrait_dir(project) -> Path:
    """肖像目录：`<项目>/肖像/`（**项目级** —— 跨轮复用靠的就是这个位置）。
        English:
    Portrait directory: `<project>/肖像/` (**project-level** - cross-round reuse relies on this
    location).
    """
    return Path(project.root) / PORTRAIT_DIRNAME


def portrait_path(project, name: str) -> Path:
    safe = ''.join(ch for ch in str(name) if ch not in '\\/:*?"<>|').strip() or '未命名'
    return portrait_dir(project) / f'{safe}.png'


def manifest_path(project, *, as_json: bool = False) -> Path:
    d = portrait_dir(project)
    return d / (MANIFEST_JSON if as_json else MANIFEST_MD)


def load_manifest(project) -> dict:
    """读清单；没有/坏了都返回空 dict（hook 只做"有没有这张图"的判断）。
        English:
    Read the manifest; if missing/corrupt, return an empty dict (hook only judges "whether this
    image exists").
    """
    p = manifest_path(project, as_json=True)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:                                       # noqa: BLE001
        return {}


def has_portrait(project, name: str) -> bool:
    """这个人的肖像能不能用（**只看文件在不在**，不看清单）。
        English:
    Whether this person's portrait is usable (**only checks whether the file exists**, does not read
    the manifest).
    """
    p = portrait_path(project, name)
    try:
        return p.exists() and p.stat().st_size > 0
    except OSError:
        return False


# ══════════════════════════════════════════════════════════════
#  提示词
# [EN] Prompt
# ══════════════════════════════════════════════════════════════
def build_portrait_prompt(name: str, *, identity: str = '', personality: str = '',
                          genre: str = '', extra: str = '') -> str:
    """由人物设定拼提示词。

    结构跟 `ai.build_prompt` 一致：**中文在前（模型要读懂"这是谁"），
    英文画风词在后**（出图质量主要吃这一串）。
    
        English:
    Build the prompt from the character settings.
        Structure matches `ai.build_prompt`: **Chinese first (the model needs to understand "who this is"),
        English style words after** (image quality mainly depends on this string).
    """
    bits = [f'中国古代人物肖像，半身正面，人物：{name}']
    if identity:
        bits.append(f'身份：{identity}')
    if personality:
        bits.append(f'气质：{personality}')
    if genre:
        bits.append(f'题材：{genre}')
    if extra:
        bits.append(extra)
    return '，'.join(bits) + f'. {ART_STYLE}. {NEGATIVE}'


# ══════════════════════════════════════════════════════════════
#  批量生成
# [EN] Batch generation
# ══════════════════════════════════════════════════════════════
@dataclass
class PortraitReport:
    """一次肖像批量生成的结果（**给界面和验证脚本读的**）。
        English:
    Result of one portrait batch generation (**for the UI and validation scripts to read**).
    """
    available: bool = True          # 模型支不支持文生图
    why: str = ''                   # 不支持时的原因（**要照原样显示给用户**）
    ok: list[str] = field(default_factory=list)        # 这次真画出来的
    cached: list[str] = field(default_factory=list)    # 早就有了、直接复用
    failed: list[tuple[str, str]] = field(default_factory=list)   # (姓名, 原因)
    # [EN] Whether the model supports text-to-image
    # [EN] Reason when unsupported (**must be shown to the user verbatim**)
    # [EN] Actually drawn this time
    # [EN] Already existed, reused directly
    # [EN] (name, reason)

    @property
    def total(self) -> int:
        return len(self.ok) + len(self.cached) + len(self.failed)

    def summary(self) -> str:
        """一句话结论（i18n 的 key 用中文原文，见 `i18n.py`）。
                English:
        One-sentence conclusion (the i18n key uses the Chinese original, see `i18n.py`).
        """
        if not self.available:
            return f'文生图不可用（{self.why}），正文不插肖像图'
        bits = []
        if self.ok:
            bits.append(f'新画 {len(self.ok)} 张')
        if self.cached:
            bits.append(f'复用 {len(self.cached)} 张')
        if self.failed:
            bits.append(f'失败 {len(self.failed)} 张')
        return ' / '.join(bits) if bits else '没有需要画的人物'


def ensure_portraits(project, people: Iterable[Any], *,
                     genre: str = '',
                     style: str = '',
                     force: bool = False,
                     on_progress: Callable[[str], None] | None = None,
                     generator: Callable[[str, Path], Path | None] | None = None,
                     ) -> PortraitReport:
    """把这本书的人物肖像补齐（**开卷时调一次**）。

    `people` 可以传 `设定集['人物']`（dict 列表）或 `WorldState.people.values()`；
    两种都认，取「姓名 / 身份 / 性格」三个字段。

    `generator` 是给测试用的注入口（默认走 `ai.generate_ai_image`）；
    注入后**不再检查 `ai_available()`** —— 测试要能验证"成功那条路"。

    幂等：已有文件的直接算 `cached`，不重复调模型（除非 `force=True`）。
    
        English:
    Fill in the character portraits for this book (**called once at book opening**).
        `people` can be passed `设定集['人物']` (list of dicts) or `WorldState.people.values()`;
        `generator` is an injection point for tests (defaults to `ai.generate_ai_image`);
        after injection, **no longer checks `ai_available()`** - tests must be able to verify the "success path".
        Idempotent: existing files are directly counted as `cached`, no repeated model calls (unless `force=True`).
    """
    rep = PortraitReport()

    def _log(msg: str) -> None:
        _LOG.info(msg)
        if on_progress:
            try:
                on_progress(msg)
            except Exception:                               # noqa: BLE001
                pass

    persons = [_person_fields(p) for p in (people or [])]
    persons = [p for p in persons if p['name']]
    if not persons:
        rep.available = False
        rep.why = '设定集里没有人物'
        _write_manifest(project, rep, [])
        return rep

    if generator is None:
        from image_gen.ai import ai_available, generate_ai_image
        ok, why = ai_available()
        rep.available = ok
        rep.why = why
        if not ok:
            # ★ 预期内的分支：**不抛异常、不降级成丑陋的本地图**，
            #   如实记下原因，让界面明说"不支持"，正文里这一段就不插肖像
            #   （2026-10-07 起也不再另写一段人物介绍 —— 那由开场卡负责）。
            # [EN] ★ Expected branch: **do not raise exceptions, do not degrade to an ugly local image**,
            # [EN] record the reason truthfully, let the UI explicitly say "unsupported", and do not insert a
            # [EN] portrait for this section in the body text
            # [EN] (As of 2026-10-07, no separate character introduction is written either - that is handled by the
            # [EN] opening card).
            _log(f'肖像：文生图不可用（{why}），正文不插肖像图')
            rep.failed = [(p['name'], why) for p in persons]
            _write_manifest(project, rep, persons)
            return rep
        generator = generate_ai_image
    else:
        rep.available = True

    ensure_dir(portrait_dir(project))
    _log(f'肖像：开始生成 {len(persons)} 位（{genre or "未定题材"}）')
    for p in persons:
        name = p['name']
        path = portrait_path(project, name)
        if path.exists() and path.stat().st_size > 0 and not force:
            rep.cached.append(name)
            _log(f'肖像：复用「{name}」')
            continue
        prompt = build_portrait_prompt(name, identity=p['identity'],
                                       personality=p['personality'],
                                       genre=genre, extra=style)
        try:
            got = generator(prompt, path)
        except Exception as e:                              # noqa: BLE001
            got = None
            _LOG.warning('肖像生成异常 %s: %r', name, e)
        if got and Path(got).exists():
            rep.ok.append(name)
            p['prompt'] = prompt
            _log(f'肖像：已生成「{name}」')
        else:
            reason = '文生图调用失败（见日志）'
            rep.failed.append((name, reason))
            p['prompt'] = prompt
            _log(f'肖像：「{name}」失败（{reason}）')

    _write_manifest(project, rep, persons)
    _log('肖像：' + rep.summary())
    return rep


def _person_fields(p: Any) -> dict:
    """从 dict（设定集）或对象（`PersonState`）里取三个字段，兼容两种来源。
        English:
    Extract three fields from a dict (settings) or an object (`PersonState`), compatible with both
    sources.
    """
    def g(*keys: str) -> str:
        for k in keys:
            if isinstance(p, dict):
                v = p.get(k)
            else:
                v = getattr(p, k, None)
            if v:
                return str(v).strip()
        return ''
    return {'name': g('姓名', 'name'),
            'identity': g('身份', 'identity'),
            'personality': g('性格', 'personality'),
            'prompt': ''}


def _write_manifest(project, rep: PortraitReport, persons: list[dict]) -> None:
    """写两份清单：`.md` 给人看，`.json` 给程序读。
        English:
    Write two manifests: `.md` for humans, `.json` for programs.
    """
    d = portrait_dir(project)
    ensure_dir(d)
    prompts = {p['name']: p.get('prompt', '') for p in persons}
    lines = [
        '# 肖像清单',
        '',
        f'> 生成时间：{now_str()}',
        f'> 结论：{rep.summary()}',
        '',
    ]
    if not rep.available:
        lines += [f'**文生图不可用**：{rep.why}。',
                  '正文里这一段**不插肖像图**（不会用本地画的头像凑数）。',
                  '人物是谁、什么脾气，由每轮开跑时的**开场卡**统一交代 —— '
                  '所以正文里不会再重复写一遍。',
                  '']
    lines += ['| 人物 | 状态 |', '|---|---|']
    for n in rep.cached:
        lines.append(f'| {n} | 复用（早先已生成） |')
    for n in rep.ok:
        lines.append(f'| {n} | 本次生成 |')
    for n, why in rep.failed:
        lines.append(f'| {n} | 未生成：{why} |')
    lines += ['', '## 提示词', '']
    lines += [f'- **{n}**：{prompts.get(n) or "（未生成，无提示词）"}'
              for n in [*rep.ok, *rep.cached, *[f for f, _ in rep.failed]]]
    atomic_write_text(manifest_path(project), '\n'.join(lines).rstrip() + '\n')

    payload = {
        '生成时间': now_str(),
        '支持文生图': rep.available,
        '不支持原因': rep.why,
        '本次生成': rep.ok,
        '复用': rep.cached,
        '失败': [{'姓名': n, '原因': w} for n, w in rep.failed],
        '可用': {p['name']: has_portrait(project, p['name']) for p in persons},
        '提示词': prompts,
    }
    atomic_write_text(manifest_path(project, as_json=True),
                      json.dumps(payload, ensure_ascii=False, indent=2))


def load_report(project) -> PortraitReport:
    """把清单读回 `PortraitReport`（验证脚本/界面复述结论时用）。
        English:
    Read the manifest back into `PortraitReport` (used by validation scripts/UI to restate
    conclusions).
    """
    data = load_manifest(project)
    if not data:
        return PortraitReport(available=False, why='尚未生成肖像')
    return PortraitReport(
        available=bool(data.get('支持文生图')),
        why=str(data.get('不支持原因', '')),
        ok=list(data.get('本次生成') or []),
        cached=list(data.get('复用') or []),
        failed=[(str(x.get('姓名')), str(x.get('原因')))
                for x in (data.get('失败') or [])],
    )
