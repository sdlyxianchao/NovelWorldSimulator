# -*- coding: utf-8 -*-
"""真机验证：人物肖像 —— **全用文生图 / 开卷生成一次 / 不支持就不插肖像**。

用户的三条硬要求（这个脚本就是钉这三条）：

1. **肖像全部用文生图** —— 本地 Pillow 画的那个几何头像不再接入对话
   （`hook('portrait', ...)` 在没生成过时必须返回 `None`，**不许兜底本地画**）。
2. **只在开卷时生成一次**，之后各轮复用 —— 肖像存在 **`<项目>/肖像/`**
   （项目级，不是运行文件夹级），第二次调用的结果是「全部复用」且**不再调模型**。
3. **模型不支持就说明白，这一段不插肖像** —— 明说原因（不是抛异常、不是偷偷降级）。
   ★ 2026-10-07 改口径：**也不再另写一段人物介绍**。以前正文里会补一行
   `※ 肖像：主角 · 沈家长子 · 沉稳内敛`，而每轮开跑时开场卡已经把这个人
   交代过一遍了 —— 用户实机看到的就是「人物介绍了两遍 这个没必要」。
   人物介绍的唯一出口现在在 `sim/opening.py::person_rows()`。

真机部分（要开窗口）：
  · 真的调 `app._make_portraits(...)`，看它返回什么、日志里写了什么、清单落没落盘
  · 真的把一天的剧本渲染到运行界面，量屏幕上**有没有**「※ 肖像：」那一行
  · 再往项目里放一张肖像图，确认这次出的是**图片**

产出：assets/screenshots/portrait_*.png / portrait_report.json
      assets/screenshots/portrait_logic_report.json

English:
Real device verification: character portraits -- **all use text-to-image / generated once at
open / if unsupported, no portrait is inserted**.
The user's three hard requirements (this script exists to pin these three down):
1. **All portraits use text-to-image** -- the geometric avatar drawn locally with Pillow is no longer wired into the conversation
   (`hook('portrait', ...)` must return `None` when it has never been generated, **no falling back to local drawing**).
2. **Generate only once at open**, then reuse across rounds -- portraits are stored in **`<project>/portraits/`**
   (project-level, not run-folder-level); the second call's result is "all reused" and **no longer calls the model**.
3. **If the model doesn't support it, say so clearly, and this section inserts no portrait** -- state the reason explicitly (not by throwing an exception, not by silently degrading).
   ★ 2026-10-07 Changed stance: **also no longer write a separate character introduction**. Previously the body would add a line
   `※ Portrait: Shen Yan · Shen family's eldest son · calm and reserved`, but the opening card at each round's start had already
   explained this person once -- what the user actually sees is "the character introduction appears twice, this is unnecessary".
   The only outlet for the character introduction is now `sim/opening.py::person_rows()`.
Real device part (requires opening a window):
  · Actually call `app._make_portraits(...)`, see what it returns, what is written in the log, and whether the manifest is persisted
  · Actually render one day's script to the running UI, and measure whether the line "※ Portrait:" **appears** on screen
  · Then place a portrait image into the project, and confirm that what comes out this time is an **image**
Output: assets/screenshots/portrait_*.png / portrait_report.json
      assets/screenshots/portrait_logic_report.json
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import verify_ui_common as VU  # noqa: E402
from util.flet_shutdown import shutdown, exit_now  # noqa: E402

from config import CFG  # noqa: E402
CFG.set('MOCK_LLM', 'true')

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
SUFFIX = ''

_checks: list[tuple[str, bool, str]] = []


def rec(name: str, ok: bool, detail: str = '') -> bool:
    _checks.append((name, bool(ok), detail))
    print(f'  [{"OK" if ok else "!!"}]   {name}' + (f'  — {detail}' if detail else ''),
          flush=True)
    return bool(ok)


def count_ok() -> tuple[int, int]:
    return sum(1 for _n, o, _d in _checks if o), len(_checks)


# ══════════════════════════════════════════════════════════════
#  夹具
# [EN] Fixture
# ══════════════════════════════════════════════════════════════
PEOPLE = [{'姓名': '主角', '身份': '沈家长子', '性格': '沉稳内敛', '简介': '二十六岁'},
          {'姓名': '柳氏', '身份': '主角之妻', '性格': '性子爽利', '简介': '管着账目'},
          {'姓名': '阿福', '身份': '沈家老仆', '性格': '忠厚爱唠叨', '简介': '五十岁'}]


def make_project(root: Path, people: list | None = None) -> 'object':
    """造一个**有设定集**的项目（不跑真摄取，直接写 `人物.yaml`）。
        English:
    Create a project **with a setting collection** (don't run real ingestion, just write
    `characters.yaml`).
    """
    import yaml
    from store.project import Project
    proj = Project.create_new(root.parent, root.name)
    sd = proj.settings_dir
    sd.mkdir(parents=True, exist_ok=True)
    ppl = people if people is not None else PEOPLE
    (sd / '人物.yaml').write_text(
        yaml.dump(ppl, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding='utf-8')
    (sd / '世界观.md').write_text(
        yaml.dump('临河小城，常年落雨。', allow_unicode=True), encoding='utf-8')
    return proj


def fake_generator(log: list):
    """假出图器：写一张纯色图，并记下被调了几次（用来证明"只生成一次"）。
        English:
    Fake image generator: write a solid-color image, and record how many times it was called (to
    prove "generate only once").
    """
    from PIL import Image

    def gen(prompt: str, path: Path):
        log.append(prompt)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (48, 48), (198, 150, 110)).save(path)
        return path
    return gen


# ══════════════════════════════════════════════════════════════
#  A. 逻辑验证
# [EN] A. Logic verification
# ══════════════════════════════════════════════════════════════
def run_logic(tmp: Path) -> None:
    from image_gen.portraits import (PORTRAIT_DIRNAME, build_portrait_prompt,
                                     ensure_portraits,
                                     has_portrait, load_manifest, load_report,
                                     portrait_dir, portrait_path)
    from image_gen.hook import make_image_hook

    print('\n── 1. 肖像提示词 ──')
    prompt = build_portrait_prompt('主角', identity='沈家长子',
                                   personality='沉稳内敛', genre='历史架空')
    ok_prompt = all(w in prompt for w in ('主角', '沈家长子', '沉稳内敛', '历史架空'))
    rec('提示词带上了人物自己的设定（姓名/身份/性格/题材）', ok_prompt,
        prompt[:64] + '…')
    rec('提示词里有画风与禁用项（不要文字/水印/照片感）',
        'ink-and-wash' in prompt and 'no text' in prompt and 'no watermark' in prompt)

    print('\n── 2. 存在哪：项目级（跨轮复用的关键）──')
    proj = make_project(tmp / '肖像验证项目')
    rec('肖像目录在**项目根**下，不在运行文件夹里',
        portrait_dir(proj) == proj.root / PORTRAIT_DIRNAME
        and PORTRAIT_DIRNAME == '肖像',
        str(portrait_dir(proj).relative_to(tmp)))
    rec('每人一个文件，名字按姓名',
        portrait_path(proj, '主角') == portrait_dir(proj) / '主角.png')
    rec('姓名里的非法字符会被清掉（不炸路径）',
        '?' not in portrait_path(proj, 'a?b/c').name
        and '\\' not in portrait_path(proj, 'a?b/c').name,
        portrait_path(proj, 'a?b/c').name)

    print('\n── 3. 只生成一次，之后复用 ──')
    calls: list[str] = []
    gen = fake_generator(calls)
    r1 = ensure_portraits(proj, PEOPLE, genre='历史架空', generator=gen)
    # 注意：中文排序按**码位**不是拼音，所以用集合比（踩过：sorted 比会假失败）
    # [EN] Note: Chinese sorting here is by **code point**, not pinyin, so compare with sets (learned the
    # [EN] hard way: comparing with sorted gives false failures)
    rec('第一轮：三位全部新画',
        set(r1.ok) == {'主角', '柳氏', '阿福'} and not r1.cached,
        f'ok={r1.ok}')
    rec('第一轮：真的调了 3 次模型', len(calls) == 3, f'{len(calls)} 次')
    r2 = ensure_portraits(proj, PEOPLE, genre='历史架空', generator=gen)
    rec('第二轮：**一个都没重画**，全部复用',
        not r2.ok and set(r2.cached) == {'主角', '柳氏', '阿福'},
        f'cached={r2.cached}')
    rec('第二轮：**没有再次调用模型**（省 token 的关键）', len(calls) == 3,
        f'累计仍是 {len(calls)} 次')
    r3 = ensure_portraits(proj, PEOPLE, genre='历史架空', generator=gen, force=True)
    rec('force=True 才重画', len(r3.ok) == 3 and len(calls) == 6, f'{len(calls)} 次')
    rec('三个人的图都真在盘上', all(has_portrait(proj, p['姓名']) for p in PEOPLE))

    print('\n── 4. 清单：人能看、程序能读 ──')
    mpath = portrait_dir(proj) / '肖像清单.md'
    jpath = portrait_dir(proj) / '肖像清单.json'
    md = mpath.read_text(encoding='utf-8') if mpath.exists() else ''
    rec('落了给人看的「肖像清单.md」', mpath.exists() and '主角' in md, mpath.name)
    rec('也落了给程序读的 json', jpath.exists())
    man = load_manifest(proj)
    rec('json 里有「支持文生图 / 可用 / 提示词」',
        man.get('支持文生图') is True and man.get('可用', {}).get('主角') is True
        and bool(man.get('提示词', {}).get('主角')),
        f"键={sorted(man)[:6]}")
    back = load_report(proj)
    rec('报告能读回来（界面复述结论要用）',
        back.available and len(back.ok) == 3, f'ok={len(back.ok)}')

    print('\n── 5. 模型不支持：明说 + 不插肖像（MOCK 就是"不支持"）──')
    proj2 = make_project(tmp / '不支持的项目')
    msgs: list[str] = []
    r4 = ensure_portraits(proj2, PEOPLE, genre='历史架空',
                          on_progress=msgs.append)
    rec('MOCK 下判定为「不支持文生图」', r4.available is False, r4.why)
    rec('原因是一句**能读给人听**的话（不是异常栈）',
        bool(r4.why) and 'Traceback' not in r4.why and len(r4.why) > 4, r4.why)
    rec('结论里写明「正文不插肖像图」'
       '（2026-10-07 起不再说"改用文字代替" —— 那件事已经没有了）',
       '不插肖像图' in r4.summary(), r4.summary())
    rec('不抛异常、也不写任何图（**不许本地画凑数**）',
        not list(portrait_dir(proj2).glob('*.png')),
        f'目录里只有 {[p.name for p in portrait_dir(proj2).glob("*")]}')
    rec('这一条也进了日志（界面要显示给用户）',
        any('文生图不可用' in m and '不插肖像' in m for m in msgs), str(msgs[:1]))
    md2 = (portrait_dir(proj2) / '肖像清单.md').read_text(encoding='utf-8')
    rec('清单里写明不支持与原因',
        '文生图不可用' in md2 and r4.why[:8] in md2)

    print('\n── 6. hook：只认「开卷时生成好的那张」──')
    class _Run:
        def __init__(self, root):
            self.root = root
    run = _Run(tmp / '第1次模拟')
    run.root.mkdir(parents=True, exist_ok=True)
    CFG.set('SCRIPT_IMAGES', 'both')
    proj2.image_mode = 'png'
    h2 = make_image_hook(proj2, run)
    warns: list[str] = []
    orig_log = None
    rec('没生成过肖像 → 返回 None（正文里这一段就不插肖像）',
        h2('portrait', '主角') is None)
    proj.image_mode = 'png'
    h1 = make_image_hook(proj, run)
    got = h1('portrait', '主角', {'personality': '沉稳'})
    rec('生成过 → 返回**项目里那张**（不是运行文件夹里的副本）',
        bool(got) and Path(got) == portrait_path(proj, '主角'),
        Path(got).name if got else '没返回')
    rec('「关闭」档：连肖像都不查（什么图都不要）',
        make_image_hook(_off_project(tmp), run)('portrait', '主角') is None)

    print('\n── 7. 人物介绍**只在开场卡里写一次**（SceneBuilder 不再补文字）──')
    from display.scene_builder import SceneBuilder

    class _PS:
        def __init__(self, n, i, p):
            self.name, self.identity, self.personality = n, i, p
            self.status, self.location = '在场', ''

    class _W:
        def __init__(self):
            self.scene, self.weather, self.game_day = '临河茶肆', '雨', 1
            self.people = {'主角': _PS('主角', '沈家长子', '沉稳内敛'),
                           '柳氏': _PS('柳氏', '主角之妻', '性子爽利')}

    b = SceneBuilder(_W(), day=1, image_hook=lambda k, key, ctx=None: None)
    b.observe_tick([], tick_num=1)
    sc = b.current
    notes = [e for e in sc.entries if e.kind == 'note']
    # ★ 2026-10-07 翻面的判据（原判据要求"必须出一条 `※ 肖像：…`"）：
    #   用户实机看到的就是"人物介绍了两遍"——开场卡一次、正文一次。现在
    #   正文**一次都不写**，肖像拿不到图就只是没有图。
    # [EN] ★ 2026-10-07 Reversal criterion (the original criterion required "must emit a `※ Portrait:
    # [EN] ...`"):
    # [EN] What the user actually sees is "the character introduction appears twice" - once in the opening
    # [EN] card, once in the body. Now
    # [EN] the body writes it **not even once**; if the portrait can't get an image, it simply has no
    # [EN] image.
    rec('拿不到肖像图 → 正文里**不写**人物介绍（不再与开场卡重复）',
        len(notes) == 0, f'{len(notes)} 条' + (f'：{notes[0].text[:30]}' if notes else ''))
    rec('但"谁在场"不能丢：人物照样出场（介绍不写了，在场要写）',
        len([e for e in sc.entries if e.kind == 'enter']) == 2,
        f'{len([e for e in sc.entries if e.kind == "enter"])} 条出场')
    b._prev_cast.clear()                    # 模拟"离场后再入场"
    # [EN] Simulate "leave then re-enter"
    b.observe_tick([], tick_num=2)
    rec('再入场也不会补一段人物介绍',
        len([e for e in sc.entries if e.kind == 'note']) == 0)

    IMG = str(portrait_path(proj, '主角'))
    b2 = SceneBuilder(_W(), day=1,
                      image_hook=lambda k, key, ctx=None: IMG if k == 'portrait' else None)
    b2.observe_tick([], tick_num=1)
    imgs = [e for e in b2.current.entries if e.kind == 'image']
    rec('有图时出的是**图片词条**，不是备注', len(imgs) == 2 and not any(
        e.kind == 'note' for e in b2.current.entries), f'{len(imgs)} 张')
    rec('图片指向项目里那张肖像', imgs[0].image == IMG, Path(imgs[0].image).name)


def _off_project(tmp: Path):
    from store.project import Project
    p = Project(tmp / '关闭档项目', '关闭档项目')
    p.image_mode = 'off'
    return p


# ══════════════════════════════════════════════════════════════
#  B. 真机验证
# [EN] B. Real device verification
# ══════════════════════════════════════════════════════════════
async def main(page: 'object') -> None:
    import flet as ft
    VU.patch_flat_background()
    from gui.app_flet import NovelWorldApp
    from image_gen.portraits import portrait_dir, portrait_path

    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.0)

    report: dict = {}
    tmp = OUT / '_portrait_tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)

    async def shot(name: str):
        page.update()
        await asyncio.sleep(0.45)
        png = await page.take_screenshot()
        (OUT / name).write_bytes(png)
        return png

    print('\n── B1. 真机：开卷时生成肖像（MOCK 下应明说不支持）──')
    proj = make_project(tmp / '真机肖像项目')
    logs: list[str] = []
    prog: list[tuple] = []
    rep = await app._make_portraits(
        proj, {'人物': PEOPLE, '主题材': '历史架空'},
        lambda m, k='stage': logs.append(m), lambda p, x: prog.append((p, x)))
    report['make_portraits'] = {
        'available': rep.available if rep else None,
        'why': rep.why if rep else '',
        'logs': logs,
    }
    rec('真机：_make_portraits 跑通并回报「不支持」',
        rep is not None and rep.available is False, rep.why if rep else '返回 None')
    rec('真机：日志里写明原因 + 「正文里不插肖像图」',
        any('文生图不可用' in m and '不插肖像' in m for m in logs),
        logs[-1][:80] if logs else '无日志')
    rec('真机：进度条文案提到了肖像',
        any('肖像' in str(x[1]) for x in prog), str(prog[:1]))
    rec('真机：清单文件真的落盘了',
        (portrait_dir(proj) / '肖像清单.md').exists()
        and (portrait_dir(proj) / '肖像清单.json').exists(),
        str(sorted(p.name for p in portrait_dir(proj).glob('*'))))

    print('\n── B2. 真机：拿不到肖像图时，正文里**不再重复介绍人物** ──')
    from store.runfolder import RunFolder
    run = RunFolder(proj.root, '第1次模拟2026-10-05-13-00').create()
    run.settings_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(proj.settings_dir / '人物.yaml', run.settings_dir / '人物.yaml')
    app._activate_project(proj)

    def _cast_day(day: int, *, place: str = '临河茶肆',
                  suppress_scene_image: bool = False) -> None:
        """造一天（肖像拿不到图的情形）。

        ★ 2026-10-07 口径改了：以前这一档断言"正文里应出现 `※ 肖像：…`"，
          现在反过来 —— 肖像拿不到图就**只是没有图**，正文里**不补文字介绍**。
          理由：每轮开跑时开场卡（`sim/opening.py` 的「登场人物」）已经把
          这个人的身份/关系/当下/标志说了一遍，正文再来一遍就是同一批信息
          说两次（用户原话：「人物介绍了两遍 这个没必要」）。

        `suppress_scene_image=True` 时假装"地点没变"（幕首就不出场景图了）——
        用来把肖像单独隔离出来测：**场景图与肖像共用每幕 2 张的额度**，
        默认情况下幕首那张场景图会占掉一格。
        
                English:
        Create one day (the case where the portrait can't get an image).
                ★ 2026-10-07 Stance changed: previously this tier asserted "the body should contain `※ Portrait: ...`",
                  now it's the reverse -- if the portrait can't get an image, it **just has no image**, and the body **does not add a text introduction**.
                  Reason: at each round's start, the opening card (`sim/opening.py`'s "Dramatis Personae") has already stated
                  this person's identity/relationships/current status/markers once; repeating it in the body is the same batch of information
                  said twice (the user's exact words: "the character introduction appears twice, this is unnecessary").
                When `suppress_scene_image=True`, pretend "the location is unchanged" (so the scene image isn't placed at the start of the act) --
                used to isolate and test the portrait alone: **the scene image and the portrait share a quota of 2 per act**,
                and by default the scene image at the start of the act takes up one slot.
        """
        from display.scene_builder import SceneBuilder
        from display import script as S

        class _PS:
            def __init__(self, n, i, p):
                self.name, self.identity, self.personality = n, i, p
                self.status, self.location = '在场', ''

        class _W:
            def __init__(self):
                self.scene, self.weather, self.game_day = place, '雨', day
                self.people = {p['姓名']: _PS(p['姓名'], p['身份'], p['性格'])
                               for p in PEOPLE}

        from image_gen.hook import make_image_hook
        hook = make_image_hook(proj, run)
        b = SceneBuilder(_W(), day=day, image_hook=hook)
        if suppress_scene_image:
            b._last_place = place       # 让"地点没变"，幕首不放场景图
            # [EN] Make "the location unchanged", so the scene image is not placed at the start of the act
        b.observe_tick([], tick_num=1)
        b.current.add(S.narration('雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃。'))
        # ★ 必须走 `flush()`：它内部 `close_scene()` 才把正在写的这一幕
        #   收进 `scenes` —— 直接拿 `b.scenes` 会是**空的**（踩过：
        #   JSON 边车写成 `[]`，中栏什么都没有，看着像"没生效"）。
        #   主循环里也是这么落盘的（`sim/loop.py` 的 `_end_day`）。
        # [EN] ★ Must go through `flush()`: only its internal `close_scene()` puts the currently-being-written
        # [EN] act
        # [EN] into `scenes` -- directly taking `b.scenes` will be **empty** (learned the hard way:
        # [EN] the JSON sidecar is written as `[]`, the middle column has nothing, looking like "it didn't take
        # [EN] effect").
        # [EN] The main loop persists the same way (`sim/loop.py`'s `_end_day`).
        run.flush_daily_script(day, b.flush(), calendar_str='第1天·戌时',
                               weather='雨', cast=list(_W().people), tension='0.3')

    _cast_day(1)
    app.show_main_screen()
    await asyncio.sleep(0.8)
    png1 = await shot(f'portrait_text{FALLBACK_SUFFIX}.png')
    texts = _texts(page)
    report['text_fallback'] = {
        'found': any('※ 肖像：' in x for x in texts),
        'sample': next((x for x in texts if '肖像' in x), '')}
    rec('真机：中栏**不再**出现「※ 肖像：…」这行字（人物介绍只在开场卡里一次）',
        not any('※ 肖像：' in x for x in texts),
        report['text_fallback']['sample'][:70] or '（没有这一行 ✓）')
    # 但"介绍"本身不能丢 —— 它只是搬到开场卡里去了（一份信息一个出口）
    # [EN] But the "introduction" itself must not be lost -- it has just moved into the opening card (one
    # [EN] piece of information, one outlet)
    from sim import opening as _OP

    class _PS2:
        def __init__(self, n, i, p):
            self.name, self.identity, self.personality = n, i, p
            self.status, self.location = '在场', ''
            self.current_goal, self.goal, self.catchphrase = '查清旧账', '', ''

    class _W2:
        def __init__(self):
            self.scene, self.weather, self.game_day = '临河茶肆', '雨', 1
            self.clock_display = lambda: '戌时 19:30'
            self.relations = []
            self.people = {p['姓名']: _PS2(p['姓名'], p['身份'], p['性格'])
                           for p in PEOPLE}
            self.on_stage_names = lambda: [p['姓名'] for p in PEOPLE]

    rows = _OP.person_rows(_W2(), PEOPLE[0]['姓名'], PEOPLE[0]['姓名'])
    rec('★ 介绍**没有丢** —— 开场卡那边照样写得出这个人的那几行',
        bool(rows) and any(PEOPLE[0]['身份'] in r for r in rows),
        ' / '.join(rows)[:70])

    print('\n── B3. 真机：放一张肖像图后，出的就是图片 ──')
    from PIL import Image as _I
    _I.new('RGB', (96, 96), (188, 140, 96)).save(portrait_path(proj, '主角'))
    _I.new('RGB', (96, 96), (150, 160, 180)).save(portrait_path(proj, '柳氏'))
    run2 = RunFolder(proj.root, '第2次模拟2026-10-05-14-00').create()
    run2.settings_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(proj.settings_dir / '人物.yaml', run2.settings_dir / '人物.yaml')
    run = run2
    _cast_day(1, suppress_scene_image=True)
    app.show_main_screen()
    await asyncio.sleep(0.8)
    png2 = await shot(f'portrait_image{FALLBACK_SUFFIX}.png')
    imgs = _images(page)
    # ⚠ 页面上的 `ft.Image` 还包括背景图与小地图 —— 必须按路径筛出**肖像**，
    #   否则"有图片控件"会因为背景图而假通过（第一版就是这么假过的）。
    # [EN] ⚠ The `ft.Image` on the page also includes background images and the minimap -- must filter out
    # [EN] the **portrait** by path,
    # [EN] otherwise "has an image control" will falsely pass because of the background image (that's how
    # [EN] the first version falsely passed).
    ports = [x for x in imgs if str(portrait_dir(proj)) in str(x)]
    report['with_image'] = {'all_images': [str(i)[-40:] for i in imgs],
                            'portraits': [Path(x).name for x in ports]}
    rec('真机：有肖像文件后，中栏出的是**肖像图**（不是背景/地图）',
        len(ports) == 2, str([Path(x).name for x in ports]) or str(len(imgs)))
    rec('真机：图片指向**项目**里的肖像（跨轮复用同一张）',
        all(str(portrait_dir(proj)) in str(x) for x in ports) and bool(ports))
    rec('真机：这一轮不会再冒出「※ 肖像：…」那种重复介绍',
        not any('※ 肖像：' in x for x in _texts(page)))

    # 再补一条：幕首的场景图与肖像**共用每幕 2 张的额度**，会挤掉一张。
    # 这不是 bug 而是设计（"图是点缀"），但要钉住 —— 免得以后以为该出两张。
    # [EN] One more thing: the scene image at the start of the act and the portrait **share a quota of 2
    # [EN] per act**, and will squeeze out one.
    # [EN] This is not a bug but a design choice ("images are embellishment"), but it must be pinned down
    # [EN] -- lest later it be assumed two should be emitted.
    run3 = RunFolder(proj.root, '第3次模拟2026-10-05-15-00').create()
    run3.settings_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(proj.settings_dir / '人物.yaml', run3.settings_dir / '人物.yaml')
    run = run3
    _cast_day(1)                       # 这次不抑制：幕首会放场景图
    # [EN] This time no suppression: the scene image will be placed at the start of the act
    app.show_main_screen()
    await asyncio.sleep(0.6)
    ports2 = [x for x in _images(page) if str(portrait_dir(proj)) in str(x)]
    report['shared_budget'] = [Path(x).name for x in ports2]
    rec('真机：幕首场景图会占掉一格 → 只放得下一张肖像（共用额度，设计如此）',
        len(ports2) == 1, str([Path(x).name for x in ports2]))

    report['logic'] = {k: v for k, v in report.items() if k != 'checks'}
    try:
        VU.safe_rmtree(tmp)
        report['cleaned'] = str(tmp)
    except BaseException as e:                              # noqa: BLE001
        report['cleanup_error'] = str(e)
    report['checks'] = [{'name': n, 'ok': o, 'detail': d} for n, o, d in _checks]
    passed, total = count_ok()
    report['ok'] = passed == total
    (OUT / f'portrait_report{SUFFIX}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n{"=" * 62}\n通过 {passed}/{total} 项', flush=True)
    # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
    #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
    #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
    # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` will throw
    # [EN] CancelledError
    # [EN] and cancel this coroutine; write it on the line after `await shutdown(page)`, i.e.
    # [EN] `exit_now(...)`
    # [EN] **never executed** (exit code always 0 = false green). See `util/flet_shutdown.shutdown()`.
    await shutdown(page, code=0 if report['ok'] else 2)


FALLBACK_SUFFIX = ''


def _walk(node, out: list) -> None:
    if node is None:
        return
    out.append(node)
    import flet as ft
    for attr in ('controls', 'content', 'actions'):
        v = getattr(node, attr, None)
        if isinstance(v, list):
            for c in v:
                _walk(c, out)
        elif v is not None and hasattr(v, '__class__'):
            _walk(v, out)


def _texts(page) -> list[str]:
    import flet as ft
    nodes: list = []
    for c in getattr(page, 'controls', []) or []:
        _walk(c, nodes)
    for holder in ('dialog', 'overlay', '_overlay'):
        v = getattr(page, holder, None)
        if isinstance(v, list):
            for c in v:
                _walk(c, nodes)
        elif v is not None and hasattr(v, '__class__'):
            _walk(v, nodes)
    return [str(c.value) for c in nodes if isinstance(c, ft.Text) and c.value]


def _images(page) -> list[str]:
    import flet as ft
    nodes: list = []
    for c in getattr(page, 'controls', []) or []:
        _walk(c, nodes)
    return [str(c.src) for c in nodes if isinstance(c, ft.Image) and c.src]


def _has_ink(png: bytes, text: str) -> bool:
    """像素层复核：中栏那一片里确实有文字（不是控件树里有、屏幕没画）。
        English:
    Pixel-level recheck: there really is text in that region of the middle column (not just in the
    control tree, but actually drawn on screen).
    """
    im = VU.image_of(png)
    x0, x1 = im.width // 3, im.width * 2 // 3
    g = im.convert('L')
    dark = 0
    for y in range(0, im.height, 2):
        for x in range(x0, x1, 3):
            if g.getpixel((x, y)) < 110:
                dark += 1
    return dark > 200


if __name__ == '__main__':
    tmp = OUT / '_portrait_logic'
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    logic_fatal = ''
    try:
        run_logic(tmp)
    except BaseException:                                   # noqa: BLE001
        logic_fatal = traceback.format_exc()
        print(logic_fatal)
    try:
        VU.safe_rmtree(tmp)
    except BaseException:                                   # noqa: BLE001
        pass
    passed, total = count_ok()
    (OUT / f'portrait_logic_report{SUFFIX}.json').write_text(
        json.dumps({'ok': passed == total and not logic_fatal,
                    'passed': passed, 'total': total, 'fatal': logic_fatal,
                    'checks': [{'name': n, 'ok': o, 'detail': d}
                               for n, o, d in _checks]},
                   ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n（逻辑）通过 {passed}/{total} 项')
    if '--logic-only' in sys.argv:
        raise SystemExit(0 if (passed == total and not logic_fatal) else 2)
    _checks.clear()
    import flet as ft  # noqa: E402
    ft.run(main)
