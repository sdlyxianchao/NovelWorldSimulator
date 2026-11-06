# -*- coding: utf-8 -*-
"""验证：**分镜师（P2）+ 视觉参考图（P3）真的接入了 pipeline**。

用户 2026-10-15 原话（这一支的规格）
------------------------------------
    "剧本写好后导演是不是要做分镜 找下开源全流程AI漫剧软件 看下流程是否需要优化"
配合此前调研：开源漫剧流程是 剧本→分镜→视觉(角色/场景)→生图→视频→配音。
这一支把「分镜」与「视觉参考图」两位**真实接进** `director/day_plan.py::compose`：
剧本定稿后，分镜师把分拍拆成镜头清单（落 `ds.shots`），视觉参考图再为人物/场景生一致性参考图（接 image_gen）。

判据分三组
----------
  A **注册（结构）**：MEMBERS / ROSTER / 两个角色的 .md 系统提示词块
  B **接线（AST 判 compose）**：真的调 `studio.call('storyboard'/'visref')`、
     分镜写回 `ds.shots`、且带 `CREW_STORYBOARD` / `CREW_VISREF` 开关守卫、
     `DayScript` 有 `shots` 字段
  C **行为（MOCK / 打桩 image_gen）**：两个 `work` 真的产出正确结构

⚠ 为什么分 A/B/C：A 证明"登记了"、B 证明"compose 真的会调"（AST 看源码，不靠运行时巧合）、
   C 证明"调了真能产出"。只改一类，另一类会把它盖掉 / 让它形同虚设。

跑法：
    .venv\\Scripts\\python.exe tools/verify_storyboard.py
产出：assets/screenshots/storyboard_report.json

English:
Verification: **Storyboard (P2) + Visual Reference (P3) are really wired into the pipeline**.
Criteria in three groups: A registration, B wiring (AST on compose), C behaviour (MOCK / patched image_gen).
Usage:
    .venv\\Scripts\\python.exe tools/verify_storyboard.py
Output: assets/screenshots/storyboard_report.json
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

import verify_ui_common as VU                               # noqa: E402
VU.redirect_env_writes()

from config import CFG                                      # noqa: E402
CFG.set('MOCK_LLM', 'true')

from crew import catalog as CAT                             # noqa: E402

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _txt(rel: str) -> str:
    return (APP / rel).read_text(encoding='utf-8')


def _func_src(rel: str, name: str) -> str:
    """取某文件里某个函数的**源码段**（只扫那个函数，不认整份文件）。
    [EN] Take the source segment of one function in a file (scans only that fn)."""
    src = _txt(rel)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return ''
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == name):
            seg = ast.get_source_segment(src, node)
            return seg or ''
    return ''


# ══════════════════════════════════════════════════════════════════════
#  A. 注册（结构）
# [EN] A. Registration (structure)
# ══════════════════════════════════════════════════════════════════════
def test_register() -> None:
    import crew.agents as A
    import crew.roster as R

    # ★★★ A1/A2：MEMBERS 字典里真的有这两位（启动自查 `missing_members` 依赖它）
    # [EN] ★★★ A1/A2: the two roles really exist in MEMBERS
    ok("A1 ★ MEMBERS 注册 storyboard（crew/agents.py）",
       'storyboard' in A.MEMBERS,
       '' if 'storyboard' in A.MEMBERS else 'MEMBERS 没有 storyboard')
    ok("A2 ★ MEMBERS 注册 visref（crew/agents.py）",
       'visref' in A.MEMBERS,
       '' if 'visref' in A.MEMBERS else 'MEMBERS 没有 visref')

    # ★★★ A3/A4：名册 ROSTER 里也列出来（UI 可见 + audit_hooks 凭据）
    #   注意：用 **代码里的 ROSTER 元组**（不是 `roles()`）——`roles()` 在运行时还会
    #   并入自定义 / 覆盖角色，会把 key 重新加回来，看不出"代码里删了这位"。
    # [EN] ★★★ A3/A4: also listed in the roster ROSTER.
    # [EN] Use the **in-code ROSTER tuple** (not `roles()`) -- `roles()` merges custom/override
    # [EN] roles at runtime and would re-add the key, hiding "removed from code".
    rkeys = [r.key for r in R.ROSTER]
    ok("A3 ★ ROSTER 含 storyboard（crew/roster.py）",
       'storyboard' in rkeys,
       '' if 'storyboard' in rkeys else 'ROSTER 没有 storyboard')
    ok("A4 ★ ROSTER 含 visref（crew/roster.py）",
       'visref' in rkeys,
       '' if 'visref' in rkeys else 'ROSTER 没有 visref')

    # ★★★ A5：两个角色的软件层 .md 系统提示词块含中文名（直接读文件，
    #   避开 `prompt_block` 的磁盘/内存缓存，变异一定能反映）。
    # [EN] ★★★ A5: both software-layer .md prompt blocks carry the CN name.
    # [EN] Read the files directly (bypass `prompt_block` cache) so a mutation reflects.
    sb_md = _txt('agents/storyboard.md')
    vr_md = _txt('agents/visref.md')
    # 用**正文唯一短语**（不是 `name:` 那行）来判：变异只动正文那一句，
    # 若只判子串「分镜师」，frontmatter 里还有一份，会假绿。
    ok("A5 ★ 两个角色 .md 系统提示词块含中文名（分镜师 / 视觉参考图）",
       '你是本剧组的「分镜师」' in sb_md
       and '你是本剧组的「视觉参考图」' in vr_md,
       f'sb有分镜师={"你是本剧组的「分镜师」" in sb_md} '
       f'vr有视觉参考图={"你是本剧组的「视觉参考图」" in vr_md}')


# ══════════════════════════════════════════════════════════════════════
#  B. 接线（AST 判 compose）
# [EN] B. Wiring (AST on compose)
# ══════════════════════════════════════════════════════════════════════
def test_wiring() -> None:
    compose_src = _func_src('director/day_plan.py', 'compose')
    dayplan_src = _txt('director/day_plan.py')

    # ★★★ B1/B2：剧本定稿后，compose 真的会调这两位（全仓唯一的出工入口 studio.call）
    # [EN] ★★★ B1/B2: after the script is finalized, compose really calls these two roles
    ok("B1 ★ compose 调 studio.call 分镜 storyboard",
       "studio.call('storyboard'" in compose_src,
       '' if compose_src else '没取到 compose 源码')
    ok("B2 ★ compose 调 studio.call 视觉参考 visref",
       "studio.call('visref'" in compose_src,
       '' if compose_src else '没取到 compose 源码')

    # ★★★ B3：分镜的产出**真的写回** `ds.shots`（中栏/落盘走 DayScript.shots_text）
    # [EN] ★★★ B3: the storyboard output really lands in `ds.shots`
    ok("B3 ★ compose 把分镜写回 ds.shots",
       'ds.shots =' in compose_src,
       '' if compose_src else '没取到 compose 源码')

    # ★★★ B4：DayScript 真的有 `shots` 字段（否则写回无处可写）
    # [EN] ★★★ B4: DayScript really has a `shots` field
    ok("B4 ★ DayScript 有 shots 字段",
       'shots: list[dict] = field(' in dayplan_src,
       '' if dayplan_src else '没读到 day_plan.py')

    # ★★★ B5：两条调用都带开关守卫（关掉就不拦戏）
    # [EN] ★★★ B5: both calls are guarded by switches
    ok("B5 ★ compose 有 CREW_STORYBOARD / CREW_VISREF 开关守卫",
       "CFG.b('CREW_STORYBOARD')" in compose_src
       and "CFG.b('CREW_VISREF')" in compose_src,
       '' if compose_src else '没取到 compose 源码')


# ══════════════════════════════════════════════════════════════════════
#  C. 行为（MOCK / 打桩 image_gen）
# [EN] C. Behaviour (MOCK / patched image_gen)
# ══════════════════════════════════════════════════════════════════════
async def test_behaviour() -> None:
    import crew.agents as A

    # ★★★ C1：MOCK `ask` 让分镜师返回分镜 JSON，验证产出进 data 且正文含「分镜」
    # [EN] ★★★ C1: MOCK ask so the storyboard returns a shot list; verify it lands in data
    real_ask = A.ask

    async def fake_storyboard(tier, messages, **kw):
        return SimpleNamespace(
            value={'分镜': [
                {'镜': 1, '拍': 1, '景别': '中景',
                 '画面': '张三站在门口', '台词': '你来了', '镜头运动': '推'}],
                '总评': ''},
            meta={}, notes=[], ok=True, retried=False, salvaged=False, calls=1)

    A.ask = fake_storyboard
    try:
        note = await A.Storyboard().work(
            None,
            beats=[{'拍': 1, '场': '门口', '发生': '张三进门', '出场': ['张三']}])
    finally:
        A.ask = real_ask

    shots = (getattr(note, 'data', None) or {}).get('shots') or []
    ok("C1 ★ 分镜师产出 shots 进 data 且正文含「分镜」",
       getattr(note, 'ok', False) and len(shots) == 1
       and '分镜' in str(getattr(note, 'body', '') or ''),
       f'ok={getattr(note, "ok", None)} n_shots={len(shots)}')

    # ★★★ C2：打桩 image_gen，让视觉参考图产出 refs 进 data 且正文含「视觉参考」
    # [EN] ★★★ C2: patch image_gen so visual ref produces refs in data
    import image_gen.portrait as POR
    import image_gen.scene as SCN
    from PIL import Image as _PIL
    rp_port, rp_scene = POR.generate_portrait, SCN.save_scene
    _fake = _PIL.new('RGBA', (4, 4))
    POR.generate_portrait = lambda name, personality='', gender='male', size=128: _fake  # type: ignore[assignment]
    SCN.save_scene = lambda path, place, **kw: path                                       # type: ignore[assignment]
    try:
        note2 = await A.VisualRef().work(
            None,
            beats=[{'拍': 1, '场': '门口', '发生': 'x', '出场': ['张三']}])
    finally:
        POR.generate_portrait, SCN.save_scene = rp_port, rp_scene

    refs = (getattr(note2, 'data', None) or {}).get('refs') or []
    # ⚠ 只认**正文头标** `**视觉参考（`，不认松散子串：落盘路径是
    #   `generated-images/视觉参考/...png`，路径里天然带"视觉参考"，会假绿。
    # [EN] ⚠ Only the **body header** `**视觉参考（` counts -- the save path is
    # [EN] `generated-images/视觉参考/...png` and always carries the words, causing false green.
    ok("C2 ★ 视觉参考图产出 refs 进 data 且正文含「视觉参考」头标",
       getattr(note2, 'ok', False) and len(refs) >= 1
       and '**视觉参考（' in str(getattr(note2, 'body', '') or ''),
       f'ok={getattr(note2, "ok", None)} n_refs={len(refs)}')


# ══════════════════════════════════════════════════════════════════════
#  D. 展示 / 导出（P2 尾巴）：ds.shots 真的落盘 + 进导出物
# [EN] D. Surface / export (P2 tail): ds.shots really persists + enters export
# ══════════════════════════════════════════════════════════════════════
def test_display_export() -> None:
    film_src = _txt('display/film.py')
    loop_src = _txt('sim/loop.py')
    out_src = _txt('export/outputs.py')

    # ★★★ D1：film.py 真有 storyboard_plan_md（渲染 ds.shots 的那一份）
    # [EN] D1: film.py really has storyboard_plan_md
    ok("D1 ★ display/film.py 有 storyboard_plan_md（渲染 ds.shots）",
       'def storyboard_plan_md(' in film_src,
       '' if film_src else '没读到 film.py')

    # ★★★ D2：sim/loop.py 在当天边界真的调 storyboard_plan_md（落盘 分镜脚本.md）
    # [EN] D2: sim/loop.py really calls storyboard_plan_md at day boundary
    ok("D2 ★ sim/loop.py 调 storyboard_plan_md 落盘分镜脚本",
       'storyboard_plan_md(' in loop_src,
       '' if loop_src else '没读到 loop.py')

    # ★★★ D3：导出物真有 storyboard_archive_block（分镜脚本进运行报告）
    # [EN] D3: export really has storyboard_archive_block
    ok("D3 ★ export/outputs.py 有 storyboard_archive_block（分镜进报告）",
       'def storyboard_archive_block(' in out_src
       and 'storyboard_archive_block(run)' in out_src,
       '' if out_src else '没读到 outputs.py')

    # ★★★ D4：storyboard_plan_md 真把 意图/叙事点/收尾 三列渲染出来（B 的展示尾巴）
    # [EN] D4: storyboard_plan_md really renders the three new columns (B's display tail)
    ok("D4 ★ storyboard_plan_md 渲染 意图/叙事点/收尾 三列",
       '| 意图 | 叙事点 | 收尾 |' in film_src,
       '' if film_src else '没读到 film.py')


# ══════════════════════════════════════════════════════════════════════
#  E. 闭环（P3）：visref 产出不再丢弃 + 下游生图真消费参照图
# [EN] E. Closure (P3): visref output no longer discarded + downstream consumes it
# ══════════════════════════════════════════════════════════════════════
def test_closure() -> None:
    dayplan_src = _txt('director/day_plan.py')
    compose_src = _func_src('director/day_plan.py', 'compose')
    ai_src = _func_src('image_gen/ai.py', 'generate_ai_image')
    hook_src = _txt('image_gen/hook.py')
    crew_hook_src = _func_src('sim/loop.py', '_crew_image_hook')

    # ★★★ E1：DayScript 真有 refs 字段（否则 visref 产出无处可落）
    # [EN] E1: DayScript really has a refs field
    ok("E1 ★ DayScript 有 refs 字段",
       'refs: list[dict] = field(' in dayplan_src,
       '' if dayplan_src else '没读到 day_plan.py')

    # ★★★ E2：compose 真的把 visref 产出收进 ds.refs（闭环关键）
    # [EN] E2: compose really captures visref output into ds.refs
    ok("E2 ★ compose 把 visref 产出收进 ds.refs",
       'ds.refs =' in compose_src,
       '' if compose_src else '没取到 compose 源码')

    # ★★★ E3：generate_ai_image 真接受 reference 参数（图生图锚点）
    #   判「签名里的 reference:」（带冒号）：docstring 里也写 `reference`，
    #   只判子串会假绿（变异只改参数名，docstring 还在）。
    # [EN] E3: match `reference:` in the signature (docstring also says `reference`).
    ok("E3 ★ generate_ai_image 接受 reference 参数（图生图）",
       'reference:' in (ai_src or ''),
       '' if ai_src else '没取到 generate_ai_image 源码')

    # ★★★ E4：场景插图分支真把参照图传给 generate_ai_image
    # [EN] E4: the scene branch really passes the reference to generate_ai_image
    ok("E4 ★ 场景插图把参照图传给 generate_ai_image（reference=）",
       'reference=' in hook_src,
       '' if hook_src else '没读到 hook.py')

    # ★★★ E5：_crew_image_hook 真把当天场景参考图注入 ctx['visref']
    # [EN] E5: _crew_image_hook really injects the day's scene reference into ctx['visref']
    ok("E5 ★ _crew_image_hook 注入 ctx['visref']（当天场景参考图）",
       "'visref'" in (crew_hook_src or ''),
       '' if crew_hook_src else '没取到 _crew_image_hook 源码')


# ══════════════════════════════════════════════════════════════════════
#  F. 剧作者 beats 加 目标/难题（皮拉尔·亚历山德拉 Goal/Complication）
# [EN] F. Screenwriter beats add Goal / Complication
# ══════════════════════════════════════════════════════════════════════
async def test_beats_ga() -> None:
    import crew.agents as A

    # ★★★ F5：beats_text 真把 目标/难题 摊出来（验算/排练共用，源码判 f-string 标记）
    # [EN] F5: beats_text really lays out 目标/难题 (shared by verify/rehearsal; source check on the f-string marker)
    dayplan_src = _txt('director/day_plan.py')
    _has_goal = "目标：{b['目标']}" in dayplan_src
    _has_hard = "难题：{b['难题']}" in dayplan_src
    ok("F5 ★ beats_text 摊出 目标/难题（验算/排练可读）",
       _has_goal and _has_hard,
       f'目标={_has_goal} 难题={_has_hard}')

    # ★★★ F1/F2/F3/F4：MOCK `ask` 让剧作者返回含 目标/难题 的拍，
    #   判①提示词真要求这两样 ②捕获行真把它们写进 beat
    # [EN] F1/F2/F3/F4: MOCK ask so the screenwriter returns beats with Goal/Complication;
    # [EN] verify the prompt really demands them and the capture row really writes them.
    real_ask = A.ask
    captured: dict = {}

    async def fake_screen(tier, messages, **kw):
        captured['text'] = '\n'.join(
            m.get('content', '') for m in messages if m.get('role') == 'user')
        return SimpleNamespace(
            value={'拍': [{'拍': 1, '场': '临河茶肆·前厅', '主题': '对账',
                          '出场': ['张三'], '发生': '张三进门对账',
                          '要点': ['张三摊开账签'], '道具': ['账签'],
                          '情绪': '试探', '推进': '主线推进',
                          '目标': '拿到欠款', '难题': '门被反锁'}],
                   '角色任务': {'张三': ['去要债']}},
            meta={}, notes=[], ok=True, retried=False, salvaged=False, calls=1)

    A.ask = fake_screen
    try:
        ctx = SimpleNamespace(people=['张三'], genre=lambda: ('古风', '线性'))
        note = await A.Screenwriter().work(ctx, story='样章')
    finally:
        A.ask = real_ask

    ptext = captured.get('text', '')
    ok("F1 ★ 剧作者提示词含「目标」硬要求（Goal）",
       '这一拍里人物' in ptext,
       f'目标要求在提示词={"这一拍里人物" in ptext}')
    ok("F2 ★ 剧作者提示词含「难题」硬要求（Complication）",
       '挡路的什么' in ptext,
       f'难题要求在提示词={"挡路的什么" in ptext}')

    _nb = getattr(note, 'data', None) or {}
    beats = _nb.get('拍') or _nb.get('beats') or []
    ok("F3 ★ 捕获行把 目标 写进 beat（Goal 不丢）",
       len(beats) == 1 and '目标' in beats[0] and beats[0].get('目标'),
       f'n_beats={len(beats)} keys={list(beats[0].keys()) if beats else []}')
    ok("F4 ★ 捕获行把 难题 写进 beat（Complication 不丢）",
       len(beats) == 1 and '难题' in beats[0] and beats[0].get('难题'),
       f'n_beats={len(beats)} 难题={"难题" in (beats[0] if beats else {})}')


# ══════════════════════════════════════════════════════════════════════
#  G. 分镜 shots 加 意图/叙事点/收尾（皮拉尔·亚历山德拉 intent/tell/button）
# [EN] G. Storyboard shots add intent / tell / button
# ══════════════════════════════════════════════════════════════════════
async def test_shots_intent() -> None:
    import crew.agents as A

    # ★★★ G1/G3/G4：MOCK `ask` 让分镜师返回含 意图/叙事点/收尾 的镜，
    #   判①提示词真要求这三样 ②generic capture 真把它们收进 data.shots
    #   ③正文真把 叙事点 摊出来（拍摄说明书可读）
    # [EN] G1/G3/G4: MOCK ask so the storyboard returns shots with intent/tell/button;
    # [EN] verify the prompt demands them, generic capture keeps them, and the body shows 叙事点.
    real_ask = A.ask
    captured: dict = {}

    async def fake_story(tier, messages, **kw):
        captured['text'] = '\n'.join(
            m.get('content', '') for m in messages if m.get('role') == 'user')
        return SimpleNamespace(
            value={'分镜': [{'镜': 1, '拍': 1, '景别': '中景',
                            '画面': '张三站在门口', '台词': '你来了', '镜头运动': '推',
                            '意图': '交代张三的困境', '叙事点': '钱债难逃',
                            '收尾': '门关上'}]},
            meta={}, notes=[], ok=True, retried=False, salvaged=False, calls=1)

    A.ask = fake_story
    try:
        note = await A.Storyboard().work(
            None, beats=[{'拍': 1, '场': '门口', '发生': '张三进门', '出场': ['张三']}])
    finally:
        A.ask = real_ask

    ptext = captured.get('text', '')
    ok("G1 ★ 分镜提示词含 意图/叙事点/收尾 硬要求（intent/tell/button）",
       '带走的那句话' in ptext,
       f'叙事点要求在提示词={"带走的那句话" in ptext}')

    shots = (getattr(note, 'data', None) or {}).get('shots') or []
    ok("G3 ★ 分镜师把 意图/叙事点/收尾 收进 data.shots（generic capture 不丢）",
       len(shots) == 1
       and all(k in shots[0] for k in ('意图', '叙事点', '收尾')),
       f'n_shots={len(shots)} keys={list(shots[0].keys()) if shots else []}')
    body = str(getattr(note, 'body', '') or '')
    ok("G4 ★ 分镜正文把 叙事点 摊出来（拍摄说明书可读）",
       '叙事点' in body, f'body_has_叙事点={"叙事点" in body}')


def main() -> int:
    print('═' * 62)
    print('  验证：分镜师（P2）+ 视觉参考图（P3）真实接入 pipeline')
    print('═' * 62)
    try:
        print('\n【A】注册（结构）')
        test_register()
        print('\n【B】接线（AST 判 compose）')
        test_wiring()
        print('\n【C】行为（MOCK / 打桩 image_gen）')
        import asyncio
        asyncio.run(test_behaviour())
        print('\n【D】展示 / 导出（P2 尾巴）')
        test_display_export()
        print('\n【E】闭环（P3）')
        test_closure()
        print('\n【F】剧作者 beats 加 目标/难题（A · 皮拉尔 Goal/Complication）')
        asyncio.run(test_beats_ga())
        print('\n【G】分镜 shots 加 意图/叙事点/收尾（B · 皮拉尔 intent/tell/button）')
        asyncio.run(test_shots_intent())
    except Exception:                                            # noqa: BLE001
        import traceback
        report['fatal'] = traceback.format_exc()
        print(traceback.format_exc(), flush=True)

    bad = [c for c in report['checks'] if not c['ok']]
    report['passed'] = len(report['checks']) - len(bad)
    report['total'] = len(report['checks'])
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'storyboard_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  分镜/视觉参考判据：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62, flush=True)
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
