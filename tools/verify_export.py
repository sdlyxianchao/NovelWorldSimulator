# -*- coding: utf-8 -*-
"""真机验证：导出（设计稿 §10.10）。

两部分：
  A. 逻辑：装订两种模式（素材册 / 最终改写稿）、截断、版本自增、空运行、账单统计、
     调度层端到端（含报告）、开关读取。
  B. 真机：运行界面出现「导出」按钮 → 打开对话框（渲染 + 可见文本）
     → **走真实点击路径**跑一次导出 → 结果与落盘文件核对 → 截图。

产出 `assets/screenshots/export_*.png` + `export_report.json`。

跑法：
    .venv/Scripts/python tools/verify_export.py              # 全部
    .venv/Scripts/python tools/verify_export.py --logic-only  # 只跑逻辑（不弹窗）

English:
Real-machine verification: export (design doc §10.10).
Two parts:
  A. Logic: bind two modes (material book / readable draft), truncation, version auto-increment, empty run, bill statistics,
     scheduler layer end-to-end (including report), switch reading.
  B. Real machine: the "export" button appears in the running UI → open the dialog (render + visible text)
     → **go through the real click path** to run one export → check results against persisted files → screenshot.
Produce `assets/screenshots/export_*.png` + `export_report.json`.
How to run:
    .venv/Scripts/python tools/verify_export.py              # all
    .venv/Scripts/python tools/verify_export.py --logic-only  # logic only (no popup)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import flet as ft                                     # noqa: E402
import verify_ui_common as VU                         # noqa: E402
from util.flet_shutdown import shutdown, exit_now      # noqa: E402

from config import CFG                                 # noqa: E402
# ⚠ 起界面的脚本第一条就是这个重定向：`CFG.save()` 会把下面的测试值写进用户 `.env`。
# [EN] ⚠ First line of any UI-starting script is this redirect: CFG.save() would write the test
# [EN] values below into the user's `.env`.
VU.redirect_env_writes()
CFG.set('MOCK_LLM', 'true')                            # 零成本、零网络、可复现
# [EN] Zero-cost, zero-network, reproducible
# ★★★ **把外部服务的两条路都关掉**（2026-10-17 补）：
#   用户的 `.env` 里 `MUMU_FOR_EXPORT=true` 时，导出「小说版本」会改走 MuMuAINovel
#   —— 服务没起就要**等它超时**才回退。实测：本机 `.env` 上正是 `true`，
#   于是这一支判据从 17 秒变成 271 秒，而且「小说版本」那一行一直停在
#   `… 小说版本`（进度回调永远等不到 `ok`）⇒ 后面的"结果清单可点"全部假红。
#   ⇒ 这一支判据只验**内部导出**；MuMu 那条路有专门的 `verify_mumu_export.py`。
#   期望值一律**不读用户环境**（本项目的老规矩）。
# [EN] ★★★ **Turn both external-service paths off** (added 2026-10-17): with `MUMU_FOR_EXPORT=true`
# [EN] in the user's `.env`, exporting the "novel version" goes through MuMuAINovel -- and if the
# [EN] service is not up it **waits for the timeout** before falling back. Measured: the local `.env`
# [EN] indeed has `true`, so this criterion went from 17s to 271s, and the "novel version" row stayed
# [EN] at `… 小说版本` forever (the progress callback never gets `ok`) => every downstream
# [EN] "result list is clickable" check was a false red.
# [EN] => This criterion verifies **internal export only**; the MuMu path has its own
# [EN] `verify_mumu_export.py`. Expectations must **never read the user environment** (project rule).
CFG.set('MUMU_FOR_EXPORT', 'false')
CFG.set('EXPORT_NOVEL_POLISH', 'false')
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

from store.runfolder import RunFolder                  # noqa: E402
from store.project import Project                      # noqa: E402
from export import bundle as B                         # noqa: E402
from export import novel_version as NV                 # noqa: E402
from export import outputs as OUT                      # noqa: E402

OUTDIR = APP_DIR / 'assets' / 'screenshots'
OUTDIR.mkdir(parents=True, exist_ok=True)
SUFFIX = '' if _lang == 'zh' else f'_{_lang}'
LOGIC_ONLY = '--logic-only' in sys.argv

report: dict = {'checks': []}
_checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = '') -> bool:
    _checks.append((name, bool(ok), detail))
    return bool(ok)


# ══════════════════════════════════════════════════════════════
#  造数据
# [EN] Generate data
# ══════════════════════════════════════════════════════════════
DAY_MD = """# 第 {d} 天 · 永和三年春 · 小雨

> 在场：主角、柳氏  关键事件：E00{d}  张力：0.{d}0

## 辰时 · 账房

**场景** 沈家账房
**环境** 窗外细雨敲瓦 · 天气 小雨
**在场** 主角、柳氏
**依据** 节点 N07 开卷 · 伏笔 玉佩

> 主角立在窗前，看檐下的雨线一根根断掉。

主角（低声）：这雨再下三天，货就走不成了。
· 动作 主角：把账册往旁边一推
◇ 心声 主角：若今晚走不成，这一趟就白跑了。
▸ 出场 柳氏（掀帘而入）
〔同时〕
- 柳氏 ｜在门口抖落蓑衣上的雨水
〔切至 · 后厨｜同一时刻〕
- 阿福 ｜把灶膛的火拨旺
〔切回〕
〔事件 · 关键〕货船延误
※ 本幕推进节点 N07
〔图〕账房内景  assets/images/none.png

## 午时 · 后厨

**场景** 沈家后厨
**环境** 灶火映着湿漉漉的梁

> 阿福蹲在灶前，把最后一把柴推进去。

阿福：船家说，明日再不放晴就解缆了。
· 动作 阿福：用袖子擦了擦脸
▸ 退场 柳氏（回前院）

"""


def _body_of(text: str) -> str:
    """取装订稿 `---` 之后的正文（比较两稿时要去掉各自不同的文件头）。
        English:
    Take the body text after `---` in the bound draft (when comparing the two drafts, remove their
    different file headers).
    """
    parts = text.split('\n---\n')
    return '\n---\n'.join(parts[1:]) if len(parts) > 1 else text


def make_run(root: Path, days: int = 3, *, with_logs: bool = True,
             empty: bool = False, with_image: bool = True) -> RunFolder:
    """造一个运行文件夹。`empty=True` 时一天都不落盘（模拟"跑了但还没过完一天"）。

    `with_image=False` 去掉 `〔图〕` 行——GUI 渲染图片时 Flet 会去加载那个路径，
    指向不存在的文件会刷一堆 `Unsupported scheme` 报错，污染真机验证的日志。
    
        English:
    Create a run folder. When `empty=True`, not a single day is persisted (simulates "ran but hasn't
    finished a day yet").
        `with_image=False` removes the `〔图〕` lines — when the GUI renders images Flet will try to load that path,
        and pointing to a nonexistent file will spam a bunch of `Unsupported scheme` errors, polluting the real-machine verification log.
    """
    run = RunFolder(root.parent, root.name).create()
    if not empty:
        for d in range(1, days + 1):
            text = DAY_MD.format(d=d)
            if not with_image:
                text = '\n'.join(ln for ln in text.splitlines()
                                 if not ln.startswith('〔图〕')) + '\n'
            (run.daily_dir / f'第{d:03d}天.md').write_text(text, encoding='utf-8')
    if with_logs:
        (run.events_dir / 'E001.md').write_text(
            '# E001 货船延误\n\n主角与船家争执，柳氏从中调停。\n', encoding='utf-8')
        lines = [
            {"ts": 1.0, "model": "deepseek-chat", "purpose": "narrative",
             "in": 1200, "out": 400, "ms": 900, "preview": "…"},
            {"ts": 2.0, "model": "deepseek-flash", "purpose": "memory",
             "in": 300, "out": 100, "ms": 200, "preview": "…"},
            {"ts": 3.0, "model": "deepseek-chat", "purpose": "narrative",
             "in": 1100, "out": 380, "ms": 850, "preview": "…"},
        ]
        (run.logs_dir / 'llm_calls.jsonl').write_text(
            '\n'.join(json.dumps(r, ensure_ascii=False) for r in lines) + '\n',
            encoding='utf-8')
    return run


# ══════════════════════════════════════════════════════════════
#  A. 逻辑验证
# [EN] A. Logic verification
# ══════════════════════════════════════════════════════════════
def run_logic(tmp: Path) -> None:
    root = tmp / '第1次模拟2026-01-01-00-00'
    run = make_run(root, days=3)
    # 第 4 天**故意不落盘**——代表"这一天还没走完"，用于验证中途导出
    # [EN] Day 4 is **intentionally not persisted** — represents "this day hasn't finished yet", used to
    # [EN] verify mid-way export

    # ── 1. 事实采集 ──
    # [EN] ── 1. Fact collection ──
    facts = NV.collect_facts(run)
    check('事实：天数=3', facts['days'] == 3, str(facts['days']))
    check('事实：最后一天=3', facts['last_day'] == 3, str(facts['last_day']))
    check('事实：字数>0', facts['chars'] > 0, str(facts['chars']))
    check('事实：人物含主角/柳氏/阿福',
          {'主角', '柳氏', '阿福'} <= set(facts['cast']), str(facts['cast']))
    check('事实：事件卡 E001', facts['events'] == ['E001'], str(facts['events']))
    cost = facts['cost']
    check('事实：账单 3 次调用', cost['calls'] == 3, str(cost['calls']))
    check('事实：账单 token 合计', cost['in'] == 2600 and cost['out'] == 880,
          f"in={cost['in']} out={cost['out']}")
    check('事实：账单分用途', set(cost['by_purpose']) == {'narrative', 'memory'},
          str(list(cost['by_purpose'])))

    # ── 2. 素材册：过程痕迹全留 ──
    # [EN] ── 2. Material book: keep all process traces ──
    ref = NV.render_manuscript(run, mode=NV.MODE_REFERENCE)
    rtext = ref['text']
    # ⚠ 档名一律从 `NV._STEM` 取，**不许在这里再写一遍中文**：
    #   档名以后还会改（2026-10-25 就从"小说参考"改成了"原始稿加细节"），
    #   判据里硬编码一遍就得多改一处，而漏改的症状是"判据红了但功能是好的"。
    # [EN] Always take the kind name from `NV._STEM`; never hardcode the Chinese here. The name
    # [EN] has already changed once (2026-10-25), and a hardcoded copy means a red criterion even
    # [EN] though the feature works.
    for token in ('**在场**', '**依据**', '※ 本幕推进节点', '〔图〕',
                  '在场：主角、柳氏', NV._STEM[NV.MODE_REFERENCE]):
        check(f'素材册保留「{token}」', token in rtext)
    check('素材册：天数=3', ref['days'] == 3, str(ref['days']))

    # ── 3. 最终改写稿：剃掉过程痕迹，但留住叙事 ──
    # [EN] ── 3. Readable draft: strip process traces, but keep the narrative ──
    novel = NV.render_manuscript(run, mode=NV.MODE_NOVEL)
    ntext = novel['text']
    for token in ('**在场**', '**依据**', '※ 本幕推进节点', '〔图〕', '在场：主角'):
        check(f'最终改写稿剃掉「{token}」', token not in ntext)
    for token in ('## 辰时 · 账房', '**场景** 沈家账房', '**环境** 窗外细雨',
                  '> 主角立在窗前', '主角（低声）：这雨再下三天',
                  '· 动作 主角', '◇ 心声 主角', '▸ 出场 柳氏',
                  '〔同时〕', '〔切至 · 后厨', '〔切回〕', NV._STEM[NV.MODE_NOVEL]):
        check(f'最终改写稿保留「{token}」', token in ntext)
    # 「只删不加」的硬证据：最终改写稿的正文行必须是素材册正文行的**子集**。
    # 比"字数别差太多"这种阈值断言强得多——阈值能掩盖改动，子集关系不能。
    # [EN] "Delete only, never add" hard evidence: the body lines of the readable draft must be a
    # [EN] **subset** of the body lines of the material book.
    # [EN] Far stronger than a threshold assertion like "word count shouldn't differ too much" — thresholds
    # [EN] can mask changes, subset relations cannot.
    # ⚠ 用 `body` 而不是 `text`（2026-10-21）：`text` 末尾带**质量指标附录**，
    #   那份附录是给作者看的、文末自己写着"可以直接删掉"，不属于正文。
    #   拿 `text` 判"只删不加"必然误报（附录多出 42 行、还让最终改写稿比素材册长）。
    #   ⚠ 也不许改成"让判据去剥字符串"——那是让判据将就实现；
    #     正确做法是 `render_manuscript` 把 `body` 单独交出来（见那边的注释）。
    # [EN] ⚠ Use `body`, not `text` (2026-10-21): `text` ends with the **quality appendix**, which is
    # [EN] for the author and says itself "can be deleted" -- not body text. Judging
    # [EN] "delete only, never add" on `text` must misfire (42 extra lines, draft longer than book).
    # [EN] ⚠ Do not "make the criterion strip strings" -- that bends the criterion to the
    # [EN] implementation; the fix is for `render_manuscript` to hand over `body` separately.
    ref_lines = [ln.strip() for ln in _body_of(ref["body"]).splitlines() if ln.strip()]
    novel_lines = [ln.strip() for ln in _body_of(novel["body"]).splitlines() if ln.strip()]
    extra = [ln for ln in novel_lines if ln not in set(ref_lines)]
    check('最终改写稿：没多加任何一行（只删不改）', not extra, str(extra[:3]))
    # 长度比要用**同一口径**（都是 list）；set 只用来判子集。
    # [EN] Length ratio must use the **same basis** (both are list); set is only used to check subset.
    check('最终改写稿：确实比素材册短',
          len(novel_lines) < len(ref_lines),
          f'{len(novel_lines)} 行 vs {len(ref_lines)} 行')

    # ── 4. 截断：upto_day 只纳入到那天的天 ──
    # [EN] ── 4. Truncation: upto_day only includes days up to that day ──
    cut = NV.render_manuscript(run, mode=NV.MODE_NOVEL, upto_day=2)
    check('截断到第2天：days=2', cut['days'] == 2, str(cut['days']))
    check('截断到第2天：skipped=1', cut['skipped'] == 1, str(cut['skipped']))
    check('截断到第2天：不含第3天', '第 3 天' not in cut['text'])

    # ── 5. 落盘 + 版本自增 ──
    # [EN] ── 5. Persist + version auto-increment ──
    w1 = NV.write_manuscript(run, mode=NV.MODE_NOVEL)
    w2 = NV.write_manuscript(run, mode=NV.MODE_NOVEL)
    check('版本自增：v1 / v2', w1['version'] == 1 and w2['version'] == 2,
          f"{w1['version']} / {w2['version']}")
    check('版本不覆盖：两个文件都在',
          w1['path'].exists() and w2['path'].exists()
          and w1['path'] != w2['path'])
    check('落点在运行文件夹的「导出/」下',
          w1['path'].parent == run.export_dir and run.export_dir.name == '导出',
          str(w1['path']))

    # 第 4 天从未落盘 → 稿子里一天都不多
    # [EN] Day 4 was never persisted → not a single extra day in the draft
    check('中途导出：只含已落盘的 3 天', w2['days'] == 3, str(w2['days']))
    check('中途导出：未落盘的第4天不在稿里', '第 4 天' not in w2['path'].read_text(
        encoding='utf-8'))

    # ── 6. 调度层：零成本两项 ──
    # [EN] ── 6. Scheduler layer: two zero-cost items ──
    res = asyncio.run(B.export_bundle(run, ['novel', 'reference']))
    check('调度：两项都成功', res['ok'] and len(res['items']) == 2, str(res['ok']))
    check('调度：产出文件存在',
          all(i['path'] and Path(i['path']).exists() for i in res['items']))
    check('调度：detail 带天数与字数',
          all('天' in i['detail'] for i in res['items']), str(res['items'][0]['detail']))

    # ── 6b. ★★★ 润色稿要登记进 `extra_paths`（2026-10-17 用户点名）──
    #   用户原话：「我希望导出按钮最后的导出的文件的列表我都能点击」。
    #   润色稿是**同一类多落的一个文件**，以前只在 `detail` 里写了个名字 ⇒
    #   界面的"文件列表"点不到它 ⇒ 那句"列表里的文件都能点"就是半句假话。
    #   ⚠ 这里用**替身**跑（`polish_manuscript` / `write_polished` 换成假的），
    #     一次模型都不调 —— 这条判据守的是"登记没登记"，不是"润色好不好"。
    # [EN] ── 6b. ★★★ The polished draft must be registered in `extra_paths` (named by the user
    # [EN] 2026-10-17): "I want every file in the list at the end of the export button to be
    # [EN] clickable". The polished draft is **an extra file produced by the same kind**; it used to
    # [EN] appear only as a name inside `detail` => the UI's "file list" could not click it => the
    # [EN] sentence "every file in the list is clickable" would be only half true.
    # [EN] ⚠ This uses **stand-ins** (`polish_manuscript` / `write_polished` replaced by fakes) so not
    # [EN] a single model call is made -- the criterion guards "was it registered", not "is the polish
    # [EN] any good".
    _real_polish, _real_write = NV.polish_manuscript, NV.write_polished

    async def _fake_polish(run_, raw):
        return raw + '\n（替身润色稿）\n'

    def _fake_write_polished(run_, text, version, day_numbers=None):
        # ⚠ 签名必须跟真的 `write_polished` 一致（含 `day_numbers`）：bundle 会传它，
        #   替身少一个参数就 TypeError，而症状是"润色那块整个挂掉"，看不出是签名问题。
        # [EN] The stand-in signature must match the real `write_polished` (including
        # [EN] `day_numbers`): bundle passes it, and one missing parameter is a TypeError whose
        # [EN] symptom looks like "the whole polish step broke", not like a signature problem.
        span = NV._span(day_numbers or [])
        pp = run_.export_dir / f'{NV._STEM[NV.MODE_NOVEL]}_v{version}{span}_润色.md'
        pp.parent.mkdir(parents=True, exist_ok=True)
        pp.write_text(text, encoding='utf-8')
        return pp

    NV.polish_manuscript, NV.write_polished = _fake_polish, _fake_write_polished
    try:
        res_p = asyncio.run(B.export_bundle(run, ['novel'], polish=True))
    finally:
        NV.polish_manuscript, NV.write_polished = _real_polish, _real_write
    item_p = res_p['items'][0]
    extras = [str(x) for x in (item_p.get('extra_paths') or [])]
    check('★★★ 润色稿登记进 `extra_paths`（界面的文件列表才能把它也列成可点一行）',
          any(x.endswith('_润色.md') for x in extras),
          f'extra_paths={extras}')
    check('而且 extra_paths 里的文件**真的存在**（不是一个点不开的名字）',
          bool(extras) and all(Path(x).exists() for x in extras), str(extras))

    # ── 6c. ★★★ 润色稿不许把「## 第 N 天」删掉 ────────────────────────────────
    #   实测（2026-10-25，望江楼第 5 次那份 `小说版本_v2_润色.md`）：原始稿有 2 个天标题，
    #   润色稿 **0 个** —— 正文连成一整片，读者分不清哪段是哪天。
    #   根因是提示词第 4 条写着"让相邻的日子读起来连续，**而不是每天各起一段**"，
    #   模型就把 `## 第 N 天` 当成"每天各起一段"的痕迹一起删了。
    #   ⇒ 修法两层：提示词改口径（连续性说的是**行文**）+ 解析层**块级硬回填**。
    #     这条判据守的是**硬回填**那一层：用替身模型**故意删标题**，看补不补得回来。
    #     只改提示词是不够的（模型不遵守的概率 40~74%），所以必须能测出来。
    # [EN] ── 6c. ★★★ The polished draft must not delete `## 第 N 天` ─────────────────────────
    # [EN] Measured (2026-10-25, that `小说版本_v2_润色.md`): the source had 2 day headers, the
    # [EN] polished draft had **0** -- one continuous block, days indistinguishable. Root cause was
    # [EN] prompt rule 4 ("make adjacent days read continuously, **rather than each day starting a
    # [EN] new section**"), which the model read as "delete the day headers".
    # [EN] Fix is two layers: reword the prompt + a **hard chunk-level restore** in the parser.
    # [EN] This criterion guards the hard restore: a stand-in model **deliberately strips** the
    # [EN] headers and we check they come back. Prompt-only is not enough (models disobey 40-74%).
    _real_chat = NV.llm.chat

    async def _stripping_chat(tier, messages, **kw):
        body = str(messages[-1].get('content', '')).split('正文：\n', 1)[-1]
        return '润色后的' + re.sub(r'(?m)^## .*\n', '', body).strip()[:400]

    try:
        NV.llm.chat = _stripping_chat
        _src2 = ('## 第 1 天 · 子时\n\n第一天。' + '甲' * 3400
                 + '\n\n## 第 2 天 · 巳时\n\n第二天。' + '乙' * 3400)
        _out2 = asyncio.run(NV.polish_manuscript(None, _src2))
    finally:
        NV.llm.chat = _real_chat
    _h_in = len(re.findall(r'(?m)^## ', _src2))
    _h_out = len(re.findall(r'(?m)^## ', _out2))
    check('★★★ 润色稿的天标题被**硬回填**（替身模型故意删光，仍必须补回来）',
          _h_out >= _h_in, f'原 {_h_in} 个 → 润色后 {_h_out} 个')

    # ── 6d. ★★★ 不许导出两份（2026-10-26，用户：「已经自动导出，手动导出就跳过」）────
    #   实测事故：点「停止」→ 收工自动导出开始跑（MuMu 逐天重写，9 分钟）→ 用户以为没反应
    #   → 又点手动导出 ⇒ 同时产出 v1/v2，两份正文完全不同。
    #   守两件事：
    #     ① **正在跑**时第二条必须被拦下（只记"已导出"拦不住，因为那时还没导完）
    #     ② `source='auto'` 成功后要记账，`manual_kinds_to_run()` 据此只跳过出过的那几档
    #   ⚠ 必须用**真的 await 挂起**来造并发：`time.sleep` 会阻塞整个事件循环，
    #     第一条会一口气跑完（连 finally 都执行完）⇒ 第二条永远看不到 inflight，**假绿**。
    #     （我写探针时第一版就用了 time.sleep，测出来是假红；这里用 fake mumu + await。）
    # [EN] ── 6d. Never export twice (user, 2026-10-26: "if auto-export already ran, manual
    # [EN] export skips"). Real incident: Stop started a 9-minute auto export, the user assumed a
    # [EN] freeze and exported again => two drafts. Guards (1) an in-flight second call is blocked,
    # [EN] (2) a successful `source='auto'` run is recorded so the manual dialog can skip it.
    # [EN] ⚠ The concurrency must be created with a real `await`: `time.sleep` blocks the whole
    # [EN] event loop so the first export finishes completely and the guard is never exercised.
    _run_dd = make_run(tmp / '导出去重验证', days=2)
    if _run_dd is not None:
        # ⚠ 2026-10-28 踩坑：本脚本第 51 行把 MOCK_LLM 设成 true（零网络承诺），
        #   而 MuMu 分支的守卫是 `not CFG.b("MOCK_LLM")` ⇒ 替身 `_slow_mumu`
        #   永远装不上 ⇒ busy 拦截 / 逐天回调双双假红（93/95 那两条）。
        #   修法：**测试块内部**把 MOCK_LLM 临时切 false —— MuMu 桥整个被替身
        #   换掉了，这条路依然零网络；同时关掉润色（它走 NV.llm.chat，替身环境
        #   外没有兜底）。跑完恢复，不影响其它判据的零网络环境。
        # [EN] 2026-10-28 pitfall: line 51 forces MOCK_LLM=true (zero-network promise) while the
        # [EN] MuMu branch guard is `not CFG.b("MOCK_LLM")`, so the fake `_slow_mumu` never engaged
        # [EN] => busy / per-day checks went false-red. Fix: flip MOCK_LLM **inside this test
        # [EN] block** only -- the MuMu bridge is fully replaced by a fake, so it stays
        # [EN] zero-network; also switch polish off (it goes through NV.llm.chat with no fake here).
        _o_mumu, _o_flag = NV.write_manuscript_mumu, CFG.raw('MUMU_FOR_EXPORT')
        _o_mock, _o_polish = CFG.raw('MOCK_LLM'), CFG.raw('EXPORT_NOVEL_POLISH')

        async def _slow_mumu(run_, *, upto_day=None, on_day=None):
            await asyncio.sleep(0.4)                     # 真挂起，给第二条留窗口
            return NV.write_manuscript(run_, mode=NV.MODE_NOVEL, upto_day=upto_day)

        NV.write_manuscript_mumu = _slow_mumu
        CFG.set('MUMU_FOR_EXPORT', 'true')
        CFG.set('MOCK_LLM', 'false')
        CFG.set('EXPORT_NOVEL_POLISH', 'false')
        try:
            async def _race():
                t1 = asyncio.create_task(B.export_bundle(_run_dd, ['novel'], source='auto'))
                await asyncio.sleep(0.05)
                r2 = await B.export_bundle(_run_dd, ['novel'], source='manual')
                r1 = await t1
                return r1, r2
            _r1, _r2 = asyncio.run(_race())
        finally:
            NV.write_manuscript_mumu = _o_mumu
            CFG.set('MUMU_FOR_EXPORT', _o_flag or 'false')
            CFG.set('MOCK_LLM', _o_mock or 'true')
            CFG.set('EXPORT_NOVEL_POLISH', _o_polish or 'false')

        check('★★★ 一条导出在跑时，第二条必须被拦下（否则同时产出 v1/v2）',
              bool(_r2.get('busy')) and _r2.get('busy_source') == 'auto',
              f'第二条 busy={_r2.get("busy")} source={_r2.get("busy_source")}')
        _done_dd = B.auto_done(_run_dd)
        check('★★★ 收工自动导出成功后记账（界面据此把这几档默认勾掉）',
              'novel' in _done_dd, str(list(_done_dd)))
        _to_run, _skip = B.manual_kinds_to_run(_run_dd, ['novel', 'raw_novel'])
        check('而且手动导出只跳过已出过的档，没出过的照常导',
              _skip == ['novel'] and _to_run == ['raw_novel'],
              f'to_run={_to_run} skip={_skip}')

        # ── 6e. 逐天进度（没有它 = 进度条十分钟不动 = 用户以为卡死 = 又去点导出）──
        _day_calls: list[tuple] = []
        _o_mumu2, _o_flag2 = NV.write_manuscript_mumu, CFG.raw('MUMU_FOR_EXPORT')
        _o_mock2 = CFG.raw('MOCK_LLM')

        async def _mumu_with_days(run_, *, upto_day=None, on_day=None):
            _days = NV.list_days(run_)
            for _i, (_d, _p) in enumerate(_days, 1):
                if on_day:
                    on_day(_i, len(_days), int(_d))
            return NV.write_manuscript(run_, mode=NV.MODE_NOVEL, upto_day=upto_day)

        NV.write_manuscript_mumu = _mumu_with_days
        CFG.set('MUMU_FOR_EXPORT', 'true')
        CFG.set('MOCK_LLM', 'false')          # 同 6d：不切走不到 MuMu 分支（替身已零网络）
        try:
            asyncio.run(B.export_bundle(
                _run_dd, ['novel'], source='manual',
                on_day=lambda k, i, t_, d: _day_calls.append((k, i, t_, d))))
        finally:
            NV.write_manuscript_mumu = _o_mumu2
            CFG.set('MUMU_FOR_EXPORT', _o_flag2 or 'false')
            CFG.set('MOCK_LLM', _o_mock2 or 'true')

        check('★★★ 逐天进度回调真的会被调用（天数 × 1 次，且带上 kind）',
              len(_day_calls) == 2 and [c[1] for c in _day_calls] == [1, 2]
              and all(c[0] == 'novel' and c[2] == 2 for c in _day_calls),
              str(_day_calls))
    else:
        check('★★★ 导出去重 / 逐天进度', False, '拿不到 VU.make_run，跳过（判据缺失）')

    # ── 6h. ★★★ 前情承接：接续导入故事的推演，前情必须贯穿「起笔 → 推演 → 导出」 ──
    #   用户 2026-10-28 的两条原话：
    #     「导入故事的时候包含一部分之前故事的提要和之前故事的最后部分」
    #     「导出的时候也从前情和之前故事的最后一段加入进来 以方便后续拼接故事」
    #   加上此前实测报的「导出的故事起点跟前情提要对不上 故事情节没从之前的故事开始」。
    #   根因：摄取对齐出的「前情提要」只落进 已发生故事线.md（全项目只有 MCP 时间线
    #   在读它），推演第一章前情走的是 剧情参考线「起」段 —— 那是大纲的**起点**，
    #   不是导入故事的**停笔处**；导出更是一个字前情都不带。
    #   修法是一条链：对齐写 `前情提要.md`（含末段）→ `load_settings.recap` →
    #   `_worldview_text` 的【前情提要】段 → `opening_context` **优先取它**；
    #   导出装订稿开头冠「承接上一部」段（两档同加），MuMu 的设定摘要也带前情。
    #   ⚠ 五件事各自独立，别合并判断 —— 合并了就不知道断在哪一环。
    # [EN] ── 6h. ★★★ Recap continuity: for a run continuing an imported story the recap must
    # [EN] flow through start dialog -> simulation -> export (user, 2026-10-28). The aligned recap
    # [EN] used to land only in 已发生故事线.md (read by nobody but the MCP timeline server), day-1
    # [EN] recap used the outline's "setup" clause (where the outline starts, not where the imported
    # [EN] story stopped), and exports carried no recap at all. The fix is one chain: ingest writes
    # [EN] 前情提要.md -> load_settings.recap -> _worldview_text's 【前情提要】 section ->
    # [EN] opening_context prefers it; exports head the bound draft with a continuation block and
    # [EN] the MuMu brief carries the recap. Five independent guards.
    _run_pc = make_run(tmp / '前情承接验证' / '第1次模拟2026-01-01-00-00', days=1)
    _pc_proj = Path(str(_run_pc.project_dir))
    (_pc_proj / '前情提要.md').write_text(
        '前情：主角取回玉佩，仇家已知道他回了城。\n\n'
        '故事停在：他站在城门口回头望了一眼城楼。\n\n'
        '上一部结尾原句：他把玉佩揣进怀里，没有再回头。',
        encoding='utf-8')
    (_pc_proj / '剧情走向.md').write_text(
        '起：旧大纲里主角才刚刚入城。承：结识同伴。转：遇袭。合：决战。', encoding='utf-8')
    (_pc_proj / '世界观.md').write_text('一个架空王朝的漕运小城。', encoding='utf-8')
    from sim.setup import load_settings as _pc_ls, worldview_text_of as _pc_wv
    from director import day_plan as _DP
    _pc_st = _pc_ls(_pc_proj)
    check('★★★ 摄取写下的 前情提要.md 会被 load_settings 读成 recap（漏搬=前情永远进不了推演）',
          '玉佩' in str(_pc_st.get('recap') or ''), repr(str(_pc_st.get('recap'))[:60]))
    _pc_wvt = _pc_wv(_pc_st)
    check('而且 worldview 文本以【前情提要】段开头（排第一：故事停在哪比大纲从哪起头更要紧）',
          _pc_wvt.startswith('【前情提要】'), _pc_wvt[:40])
    _pc_oc = _DP.opening_context(_pc_wvt)
    check('★★★ 第一章前情**优先取前情提要**（而不是大纲「起」段 —— 这就是"起点对不上"的根）',
          '玉佩' in _pc_oc and '旧大纲' not in _pc_oc, _pc_oc[:60])
    _pc_novel = NV.render_manuscript(_run_pc, mode=NV.MODE_NOVEL)
    _pc_ref = NV.render_manuscript(_run_pc, mode=NV.MODE_REFERENCE)
    check('★★★ 装订稿开头冠「承接上一部」段（novel / reference 两档都有 —— 拼接靠它）',
          '## 前情提要 · 承接上一部' in _pc_novel['text']
          and '## 前情提要 · 承接上一部' in _pc_ref['text']
          and '上一部结尾原句' in _pc_novel['text'],
          f"novel={'承接段' if '承接上一部' in _pc_novel['text'] else '无'} / "
          f"ref={'承接段' if '承接上一部' in _pc_ref['text'] else '无'}")
    _pc_raw = NV.write_raw_manuscript(_run_pc)
    _pc_raw_text = Path(str(_pc_raw['path'])).read_text(encoding='utf-8', errors='ignore')
    check('而且「原始稿」一个字不动（凭据稿不掺承接段）',
          '承接上一部' not in _pc_raw_text, '')
    _pc_brief = NV._setting_brief(_run_pc)
    check('而且 MuMu 重写的设定摘要也带【前情提要】（否则重写稿照样从大纲开头讲起）',
          '【前情提要】' in _pc_brief, _pc_brief[:60])
    # 没有前情提要.md（首部作品 / 老项目）→ 一切照旧，一个字都不多
    _run_pc2 = make_run(tmp / '前情承接验证-无' / '第1次模拟2026-01-01-00-00', days=1)
    _pc_novel2 = NV.render_manuscript(_run_pc2, mode=NV.MODE_NOVEL)
    check('而且没有上一部时**什么都不加**（不拿"这是第一天"这类废话凑数）',
          '承接上一部' not in _pc_novel2['text'], '')
    # 摄取侧：对齐必须喂**末章结尾**、档案必须写末段（源级判断 —— LLM 一步不好桩）
    import inspect as _insp
    from ingest import progress as IP
    _align_src = _insp.getsource(IP.align_with_text)
    check('★★★ 正文对齐给模型的内容**带末章结尾**（只喂每章开头 ⇒ 前情提要停在倒数第二章）',
          'tail_sentences' in _align_src and '末章结尾' in _align_src, '')
    _sfs_src = _insp.getsource(IP.write_story_so_far)
    check('而且 已发生故事线.md 会写「前文末段」两节（情况摘要 + 原文摘录）',
          '前文末段原文' in _sfs_src and '前文末段' in _sfs_src, '')

    # ── 6f. ★★★ 「结束时自动导出」出厂全关 + 全关时手动默认勾选不空 ──────────────
    #   用户 2026-10-26：「自动导出默认关闭」。导出要回到"你点了才发生"。
    #   ⚠ 这条必须查 **SPEC 的出厂默认**，不能查 `CFG.b()` —— 后者读的是 `.env`，
    #     老用户的 `.env` 里可能还写着 true（改默认值不会覆盖它），
    #     拿它当判据会"看人下菜"，同一份代码在不同机器上判据结果不同。
    # [EN] ── 6f. Auto-export is **off by factory default**, and the manual dialog is never left
    # [EN] empty. ⚠ Must check **SPEC's factory default**, not `CFG.b()` — the latter reads `.env`,
    # [EN] which may still say true for existing users (changing a default does not overwrite it);
    # [EN] using it would make the same code pass on one machine and fail on another.
    from config import SPEC as _SPEC
    _auto_keys = ('EXPORT_ON_END_RAW', 'EXPORT_ON_END_REFERENCE',
                  'EXPORT_ON_END_NOVEL', 'EXPORT_ON_END_GUIDE')
    _still_on = [k for k in _auto_keys if _SPEC[k].get('default') is not False]
    check('★★★ 「结束时自动导出」四个开关**出厂默认全关**（导出只在你点了才发生）',
          not _still_on, f'仍默认开着：{_still_on}')

    # 全关时手动导出必须**有默认勾选**：否则对话框一片空白，点「开始导出」
    # 直接报"至少选一样" ⇒ 把"默认关闭"变成"默认不能用"。
    _saved = {k: CFG.raw(k) for k in _auto_keys}
    try:
        for k in _auto_keys:
            CFG.set(k, 'false')
        _def = B.default_manual_kinds()
        _costly = [k for k in _def if B.KIND_USES_LLM.get(k)]
        check('★★★ 自动导出全关时，手动导出仍默认勾选（且**不勾要花 token 的**）',
              bool(_def) and not _costly,
              f'默认勾={[B.label_of(k) for k in _def]} 含耗token={_costly}')
    finally:
        for k, v in _saved.items():
            CFG.set(k, v or 'false')

    # ── 6g. ★★★ 「导出拿到的是一天，不是一天的残片」 ─────────────────────────
    #   用户 2026-10-26 报的真 bug：「原始稿和最终成稿为何差那么大 完全不是一个故事了」。
    #   实测那一轮：第 1 天 `.json` 有 **133 幕 / 21.3 万字**（辰时 08:00 → 子时 23:59），
    #   而 `.md` 只剩 **381 字**（被纯文本分支覆盖），导出读的是 `.md`
    #   ⇒ 一份是午后账房的开场、一份是深夜前堂，当然"不是一个故事"。
    #
    #   这一组守三件事，各自独立：
    #     ① 读全量：`.json` 比 `.md` 长时，导出必须取 `.json`
    #     ② 落盘不跨格式覆盖：有 `.json` 的那天，`flush_daily` 必须拒绝写 `.md`
    #     ③ 原始稿的源是**每天全量**，不再是 `原文/`（那只是开场样章）
    # [EN] ── 6g. ★★★ "The export gets a day, not a remnant of a day" ──
    # [EN] Reported 2026-10-26. Measured: day 1 `.json` had **133 acts / 213k chars** while `.md`
    # [EN] was down to **381 chars** (overwritten by the plain-text branch), and exports read `.md`.
    # [EN] Guards three separate things: (1) read the full body; (2) never overwrite a script day
    # [EN] with plain text; (3) the raw draft's source is each day's full body, not `原文/`.
    import types as _types
    from display import script as _DS
    from display import script_render as _SR
    _run_full = make_run(tmp / '全量正文验证', days=1)
    _d1_md = _run_full.daily_dir / '第001天.md'
    _d1_js = _run_full.daily_dir / '第001天.json'
    # 造"被覆盖成残片"的真实现场：md 只剩几十字，json 有 3 幕/长正文
    _d1_md.write_text('# 第 1 天 · 子时\n\n> ⏳ **定时落盘 · 23:59**\n\n'
                      '甲：最后一句。\n\n乙：嗯。\n', encoding='utf-8')
    _scenes = []
    for _i in range(3):
        _sc = _DS.SceneScript(
            time_label=('辰时 08:00' if _i == 0 else f'午时 1{_i}:00'),
            place='望江楼', place_desc='', weather='晴', title='', day=1,
            cast=['甲', '乙'],
            entries=[_DS.Entry(kind=_DS.DIALOGUE,
                               text='这是一段完整的正文。' * 120, speaker='甲')])
        _scenes.append(_sc)
    _d1_js.write_text(_SR.to_json(_scenes), encoding='utf-8')
    _md_chars = len(_d1_md.read_text(encoding='utf-8'))
    _t_full, _m_full, _b_full = NV.read_day_full(_d1_md)
    check('★★★ 导出读**全量**正文（`.json` 比 `.md` 长时必须取 `.json`）',
          len(_b_full) > _md_chars * 3,
          f'md {_md_chars} 字 → read_day_full {len(_b_full)} 字')
    check('★★★ 全量正文的标题带**真实时间跨度**（不是被覆盖那刻的时辰）',
          '辰时' in _t_full and '午时' in _t_full,
          f'标题={_t_full!r}')
    check('★★★ 全量正文的元信息写明**幕数**（数字是数出来的，不是估的）',
          '3 幕' in _m_full, f'meta={_m_full!r}')
    # ⚠ 以上三条只证明 `read_day_full` 本身对。**"导出到底有没有用它"是另一件事** ——
    #   2026-10-26 反例法当场戳穿了这一层：把 mumu 路径的 `read_day_full` 改回
    #   `read_day`（= 把本次 bug 原样放回去），上面三条照样全绿。
    #   ⇒ 必须再测**装配链的行为**与**那条分支的源码**。
    # [EN] ⚠ The three checks above only prove `read_day_full` works. "Does the export actually use
    # [EN] it" is a different thing -- the counter-example run proved it: reverting the mumu path to
    # [EN] `read_day` (i.e. putting the bug back) left all three green. So also test the assembly
    # [EN] behaviour and that branch's source.
    _ref = NV.render_manuscript(_run_full, mode=NV.MODE_REFERENCE, version=999)['text']
    check('★★★ 装配链（`render_manuscript`）吃的是**全量**正文，不是那几十字的 md',
          '这是一段完整的正文' in _ref and len(_ref) > _md_chars * 3,
          f'装配结果 {len(_ref)} 字（md 只有 {_md_chars} 字）')
    # ⚠ 姊妹面（今天端到端探针才暴露）：`list_days` 原来只扫 `.md` ⇒
    #   **某天 `.md` 丢了、只剩 `.json`，那一天会整个从导出里消失**，而且不报错
    #   （"没有这一天"和"这天是空的"在调用方看来一样）。
    #   造一个"只有 json、没有 md"的第 3 天来钉它。
    # [EN] Sibling bug found by the e2e probe: `list_days` scanned `.md` only, so a day whose `.md`
    # [EN] is gone but whose `.json` survives **vanished from the export entirely**, silently. A day
    # [EN] with only a `.json` is created here to pin it.
    (_run_full.daily_dir / '第003天.md').unlink(missing_ok=True)
    _sc3 = _DS.SceneScript(
        time_label='戌时 19:30', place='望江楼', place_desc='', weather='晴', title='',
        day=3, cast=['甲'],
        entries=[_DS.Entry(kind=_DS.DIALOGUE, text='只有 json 的这一天。' * 40,
                           speaker='甲')])
    (_run_full.daily_dir / '第003天.json').write_text(
        _SR.to_json([_sc3]), encoding='utf-8')
    _day_nums = [d for d, _p in NV.list_days(_run_full)]
    check('★★★ `list_days` 收**只有 `.json`** 的那一天（md 丢了也不许整天空缺）',
          3 in _day_nums, f'扫到的天号={_day_nums}')
    _t3, _m3, _b3 = NV.read_day_full(_run_full.daily_dir / '第003天.md')
    check('而且那一天真的能读出正文（不是空壳）',
          '只有 json 的这一天' in _b3, f'正文 {len(_b3)} 字')
    import inspect as _inspect
    _mumu_src = _inspect.getsource(NV.write_manuscript_mumu)
    check('★★★ MuMu 那条分支也读**全量**（不是 `read_day`，否则本次 bug 原样复现）',
          'read_day_full(path)' in _mumu_src,
          '源码里 read_day_full 出现 %d 次' % _mumu_src.count('read_day_full'))
    # json 坏掉时必须退回 md（宁可给旧的，也不要给空）
    _d2_md = _run_full.daily_dir / '第002天.md'
    _d2_md.write_text('# 第 2 天\n\n这一天只有 md。\n', encoding='utf-8')
    (_run_full.daily_dir / '第002天.json').write_text('{ 这不是合法 json', encoding='utf-8')
    _t_bad, _m_bad, _b_bad = NV.read_day_full(_d2_md)
    check('json 解析不出来时**退回 `.md`**（不返回空）',
          '这一天只有 md' in _b_bad, f'正文={_b_bad[:40]!r}')

    # ② 落盘不跨格式覆盖
    _before = _d1_md.read_text(encoding='utf-8')
    _run_full.flush_daily(1, '纯文本想覆盖脚本格式的那一天。',
                          calendar_str='子时 23:59', partial_at='23:59:59')
    _after = _d1_md.read_text(encoding='utf-8')
    check('★★★ 有 `.json` 的那天，`flush_daily`（纯文本）**拒绝覆盖** `.md`',
          _after == _before, f'覆盖前 {len(_before)} 字 / 覆盖后 {len(_after)} 字')

    # ③ 原始稿的源不是 `原文/`
    _raw_run = make_run(tmp / '原始稿源验证', days=1)
    _raw_run.story_dir.mkdir(parents=True, exist_ok=True)   # ⚠ 不建就是 FileNotFoundError
    (_raw_run.story_dir / '第001天.md').write_text(
        '# 第 1 天 · 开场样章\n\n这是开演前的引子，不是这一天。\n', encoding='utf-8')
    _rd = NV.write_raw_manuscript(_raw_run)
    _rtxt = Path(_rd['path']).read_text(encoding='utf-8')
    check('★★★ 原始稿的源是**每天的全量正文**，不是 `原文/`（那只是开场样章）',
          '开演前的引子' not in _rtxt and len(_rtxt) > 200,
          f'原始稿 {len(_rtxt)} 字，含开场样章={"开演前的引子" in _rtxt}')

    # ── 6h. ★★★ 「一个事件跨天，不许切成两章各半截」─────────────────────────
    #   用户 2026-10-26：「**注意 一个事件可能跨天**」。
    #
    #   改之前装订层是 `for day, path in days:` —— 一天一章。而
    #   `sim/loop._carry_unplayed_beats` 会把没演完的拍带到下一天 ⇒ 同一站确实跨两天
    #   ⇒ 读者看到第 1 天章末在"推门"、第 2 天章首又是另一场，"两章各半截"。
    #
    #   现在：相邻两天如果**前一天只演一个站**、且**今天从这个站开始** ⇒ 合成一章
    #   （`## 第 1-2 天 · 站名`），章内每天用一行粗体标出。
    #
    #   ⚠ 最要紧的一条是 **D0：不跨天时输出逐字不变** —— 上面五十多条判据、
    #     `verify_mumu_export`/`verify_autocave` 全都按旧结构断言，破坏它就是全盘误红。
    # [EN] ── 6h. ★★★ "One event may span days; never bind it as two half chapters" ──
    # [EN] User 2026-10-26: "note that one event may span days". Before, the binder was
    # [EN] `for day, path in days:` -- one chapter per day -- while `_carry_unplayed_beats` carries
    # [EN] unplayed beats into the next day, so a station really does span two days and the reader
    # [EN] saw two half chapters. Now adjacent days merge when the previous day played a **single**
    # [EN] station and today starts with it. ⚠ The most important one is D0: with no spanning event
    # [EN] the output must be **byte-identical** -- dozens of criteria elsewhere assert the old
    # [EN] structure, and breaking it turns them all falsely red.
    _ev = make_run(tmp / '跨天事件装订', days=1)
    for _d in list(_ev.daily_dir.glob('*')):
        _d.unlink()

    def _mk_day(_day: int, _nodes: list[str]) -> None:
        """把某一天落成 json（幕里带 `node_name`）+ 一份 md。"""
        _scs = []
        for _i, _nm in enumerate(_nodes):
            _scs.append(_DS.SceneScript(
                time_label=f'辰时 0{8 + _i}:00', place='临街楼', node_name=_nm, day=_day,
                cast=['甲'],
                entries=[_DS.Entry(kind=_DS.DIALOGUE, speaker='甲',
                                   text=f'第 {_day} 天第 {_i} 场的台词。')]))
        (_ev.daily_dir / f'第{_day:03d}天.json').write_text(
            _SR.to_json(_scs), encoding='utf-8')
        (_ev.daily_dir / f'第{_day:03d}天.md').write_text(
            f'# 第 {_day} 天 · 辰时\n\n> 在场：甲\n\n' + '\n\n'.join(
                _SR.to_markdown(s) for s in _scs), encoding='utf-8')

    # ① 站名的读取（只做**连续**去重：`[0]`/`[-1]` 是"这天开头/结尾在哪一站"）
    _mk_day(1, ['入楼收留'])
    _mk_day(2, ['入楼收留', '重走旧路'])
    _st1 = NV.day_stations(_ev.daily_dir / '第001天.md')
    _st2 = NV.day_stations(_ev.daily_dir / '第002天.md')
    check('★★★ 能读出"这一天演了哪几站"（按出现顺序）',
          _st1 == ['入楼收留'] and _st2 == ['入楼收留', '重走旧路'], f'{_st1} / {_st2}')

    _mk_day(3, ['开庭抉择', '入楼收留', '开庭抉择'])
    _st3 = NV.day_stations(_ev.daily_dir / '第003天.md')
    check('★★★ 站名只做**连续**去重（`A,B,A` 必须保持原样：'
          '首尾两站正是判"是否跨天"的依据，全表去重会把结尾那一站改错）',
          _st3 == ['开庭抉择', '入楼收留', '开庭抉择'], str(_st3))
    (_ev.daily_dir / '第003天.md').unlink()
    (_ev.daily_dir / '第003天.json').unlink()

    # ② 分组：跨天合一章 / 前一天多站不合并
    _groups = NV.group_days_by_event(NV.list_days(_ev))
    check('★★★ 前一天只演一站、今天从这一站开始 ⇒ **合成一个事件**',
          [(g['name'], [d for d, _ in g['days']]) for g in _groups]
          == [('入楼收留', [1, 2])],
          str([(g['name'], [d for d, _ in g['days']]) for g in _groups]))

    _mk_day(3, ['重走旧路'])
    _g2 = NV.group_days_by_event(NV.list_days(_ev))
    check('★★★ 第 2 天已经是两站 ⇒ **不再往后合并**（中间插进别的站，说明事件换了）',
          [d for g in _g2 for d, _ in g['days']] == [1, 2, 3] and len(_g2) == 2,
          str([(g['name'], [d for d, _ in g['days']]) for g in _g2]))

    _mk_day(4, ['入楼收留', '开庭抉择'])
    _mk_day(5, ['入楼收留'])
    _g3 = NV.group_days_by_event([(d, p) for d, p in NV.list_days(_ev) if d >= 4])
    # ⚠ 这个形状才是 `single` 那道闸**唯一能起作用**的地方（反例法 ② 照出来的）：
    #   前一天演了 A、B，今天又回到 A ⇒ 只比"今天的第一站 == 前一天的第一站"是会合并的，
    #   而合出来的章名写 A、内容里却含 B 那一场 ⇒ 章名与内容不符。
    #   （第一版用的是 [A,B] + [B]，那种形状**两种实现都不合并**，判据天然测不出差别。）
    # [EN] This shape is the **only** one where the `single` gate can matter (mutation ② found
    # [EN] it): the previous day played A then B, today returns to A -- comparing only "today's
    # [EN] first station == previous day's first station" WOULD merge, producing a chapter titled A
    # [EN] whose content includes scene B. (The first version used [A,B] + [B], which **neither**
    # [EN] implementation merges, so the criterion could never tell them apart.)
    check('★★★ 前一天是**两站**、今天又回到第一站 ⇒ **不合并**'
          '（否则章名写"入楼收留"，章里却含"开庭抉择"那场戏 —— 章名与内容不符比不合并更糟）',
          [[d for d, _ in g['days']] for g in _g3] == [[4], [5]],
          str([(g['name'], [d for d, _ in g['days']]) for g in _g3]))

    # ③ 装订出来的结构
    for _d in list(_ev.daily_dir.glob('*')):
        _d.unlink()
    _mk_day(1, ['入楼收留'])
    _mk_day(2, ['入楼收留', '重走旧路'])
    _txt = NV.render_manuscript(_ev, mode=NV.MODE_REFERENCE, version=999)['text']
    check('★★★ 跨天事件的章标题是 **`## 第 1-2 天 · 站名`**（一件事一章）',
          '## 第 1-2 天 · 入楼收留' in _txt,
          [ln for ln in _txt.split('\n') if ln.startswith('## 第')][:3])
    check('★★★ 章内每天的边界用一行粗体标出（`**第 1 天 · …**`），'
          '不是再开一个 `## `（正文里本来就有 `## 时辰` 那级幕标题）',
          '**第 1 天' in _txt and '**第 2 天' in _txt
          and len(re.findall(r"(?m)^## 第 ", _txt)) == 1,
          f'章级标题 {len(re.findall(r"(?m)^## 第 ", _txt))} 个')
    # ⚠ 取"这一章"必须按**章标题**切，不能按 `\n## ` 切 —— 跨天章里第一个 `## ` 是
    #   **幕标题**（`## 辰时 08:00`），按它切只会剩下章标题下面那一行，
    #   而章内的 `---` 全在被切掉的后面（反例法 ③ 一开始就是这样"测了个寂寞"的）。
    # [EN] Take "this chapter" by **chapter heading**, not by `\n## `: inside a multi-day chapter
    # [EN] the first `## ` is an **act heading**, so cutting there leaves only the line under the
    # [EN] chapter title, and every `---` swallowed with it (mutation ③ first hit exactly this).
    _blocks = re.split(r"(?m)^(?=## 第 )", _txt)
    _seg = next((b for b in _blocks if b.startswith('## 第 1-2 天')), '')
    # ⚠ 章**末尾**那个 `---` 是"这一章完了"，允许有且只有一个；要禁的是**章中间**的。
    #   先把尾部那一个剥掉再判，否则判据永远红（第一版就是这样）。
    # [EN] The trailing `---` closes the chapter and is allowed, exactly once; what must be
    # [EN] forbidden is one **in the middle**. Strip the tail one first, or the criterion is
    # [EN] permanently red (that is how the first version read).
    _inner = re.sub(r'\n*---\s*$', '', _seg.rstrip())
    check('★★★ 合并起来的章**中间不许有章级 `---`**（那是章的分隔；'
          '留着就等于把刚合起来的东西又切开）',
          bool(_seg) and '\n---\n' not in _inner,
          f'章内 `---` 出现 {_inner.count(chr(10) + "---" + chr(10))} 次')

    # ④ ★★★ **不跨天时逐字等于旧结构**（这条是兼容性的全部保障）
    for _d in list(_ev.daily_dir.glob('*')):
        _d.unlink()
    _mk_day(1, ['入楼收留'])
    _mk_day(2, ['重走旧路'])
    _t2 = NV.render_manuscript(_ev, mode=NV.MODE_REFERENCE, version=999)['text']
    check('★★★ **不跨天时输出逐字等于旧结构**（`## 第 N 天` 一天一章、章末都有 `---`、'
          '没有粗体日期行）—— 五十多条既有判据按旧结构断言，破坏它就是全盘误红',
          '## 第 1 天' in _t2 and '## 第 2 天' in _t2
          and '**第 ' not in _t2 and len(re.findall(r"(?m)^## 第 ", _t2)) == 2,
          f'标题={re.findall(r"(?m)^## 第 .*", _t2)}')

    # ⑤ 两档一致（有硬判据"最终改写稿的正文行是素材册的子集（只删不加）"）
    _t_ref = NV.render_manuscript(_ev, mode=NV.MODE_REFERENCE, version=999)
    _t_nov = NV.render_manuscript(_ev, mode=NV.MODE_NOVEL, version=999)
    _ref_lines = set(_body_of(_t_ref['text']).split('\n'))
    _nov_extra = [ln for ln in _body_of(_t_nov['text']).split('\n')
                  if ln.strip() and ln not in _ref_lines]
    check('★★★ 跨天那套结构**两档一致**（最终改写稿不许比素材册多出结构行）',
          not any(ln.startswith('## 第') or ln.startswith('**第 ') for ln in _nov_extra),
          f'多出的结构行={[x for x in _nov_extra if x.startswith(("##", "**"))][:3]}')

    # ⑥ 文件头如实说"按事件装订"（不然读者以为漏了一天）
    # [EN] ⑥ The header says "bound by event" honestly (otherwise the reader thinks a day is missing).
    for _d in list(_ev.daily_dir.glob('*')):
        _d.unlink()
    _mk_day(1, ['入楼收留'])
    _mk_day(2, ['入楼收留', '重走旧路'])
    _hdr_ev2 = NV.render_manuscript(_ev, mode=NV.MODE_REFERENCE, version=999)['text']
    _src2 = [ln for ln in _hdr_ev2.split('\n') if ln.startswith('> 来源')]
    check('★★★ 有跨天事件时，文件头写明**按事件装订**、并给出跨天的件数'
          '（数字是数出来的，不是估的）',
          '按事件装订' in _hdr_ev2 and '1 件事跨了天' in _hdr_ev2, str(_src2[:1]))
    for _d in list(_ev.daily_dir.glob('*')):
        _d.unlink()
    _mk_day(1, ['入楼收留'])
    _mk_day(2, ['重走旧路'])
    _hdr_one = NV.render_manuscript(_ev, mode=NV.MODE_REFERENCE, version=999)['text']
    _src1 = [ln for ln in _hdr_one.split('\n') if ln.startswith('> 来源')]
    check('★★★ 成对：**没有跨天**时文件头仍是"按日装订"（不许无中生有说有跨天）',
          '按日装订' in _hdr_one and '按事件装订' not in _hdr_one, str(_src1[:1]))

    # ⑦ 润色的分块必须在跨天章的**日期行**前断开（否则模型删了补不回来）
    # [EN] ⑦ Polish chunking must break before the day marker inside a mixed chapter (otherwise a
    # [EN] deleted marker cannot be restored).
    _long = ('## 第 1-3 天 · 入楼收留\n\n**第 1 天 · 辰时**\n\n' + '甲' * 3000
             + '\n\n**第 2 天 · 酉时**\n\n' + '乙' * 3000
             + '\n\n**第 3 天 · 子时**\n\n' + '丙' * 3000)
    _chs = NV._split_chunks(_long, 4000)
    check('★★★ 润色分块在跨天章的**日期行**前也断开（`polish_manuscript` 只能在**块首**'
          '补回被模型删掉的那一行）',
          sum(1 for c in _chs[1:] if c.lstrip().startswith('**第 ')) >= 2,
          f'{len(_chs)} 块：{[c.lstrip()[:12] for c in _chs]}')


    # ── 7. 运行报告（MOCK LLM）：程序统计部分必须在 ──
    # [EN] ── 7. Run report (MOCK LLM): the program statistics section must be present ──
    rp = asyncio.run(B.export_bundle(run, ['report'], partial=True))
    rpath = rp['items'][0]['path']
    rptext = Path(rpath).read_text(encoding='utf-8') if rpath else ''
    check('报告：生成成功', rp['ok'] and bool(rpath), str(rpath))
    check('报告：文件名带版本', rpath and Path(rpath).name == '运行报告_v1.md',
          rpath and Path(rpath).name)
    check('报告：含程序统计的「运行概览」', '## 1 运行概览' in rptext)
    check('报告：概览写明 3 天', '| 已落盘天数 | 3 天 |' in rptext)
    check('报告：含账单与账单表', '## 账单' in rptext and '| 用途 |' in rptext)
    check('报告：账单数字来自落盘日志', '**3** 次' in rptext)
    check('报告：中途导出有醒目提示', '中途导出' in rptext)
    check('报告：设计稿的固定入口同步存在', run.run_summary_path.exists())
    # 只含已落盘的天：报告里不该出现第 4 天
    # [EN] Contains only persisted days: Day 4 should not appear in the report
    check('报告：不含未落盘的第4天', '第 4 天' not in rptext)

    # ── 8. 写作指导也要落「导出/」并同步固定入口 ──
    # [EN] ── 8. Writing guide must also be persisted to "export/" and synced to the fixed entry point ──
    gd = asyncio.run(B.export_bundle(run, ['guide'], partial=True))
    gpath = gd['items'][0]['path']
    check('指导：生成成功', gd['ok'] and bool(gpath), str(gpath))
    check('指导：文件名', gpath and Path(gpath).name == '写作指导_v1.md',
          gpath and Path(gpath).name)
    check('指导：同步写了大纲建议.md', run.outline_path.exists())

    # ── 9. 空运行不崩 ──
    # [EN] ── 9. Empty run doesn't crash ──
    empty_root = tmp / '第9次模拟2026-01-01-00-00'
    erun = make_run(empty_root, empty=True, with_logs=False)
    efacts = NV.collect_facts(erun)
    check('空运行：天数=0', efacts['days'] == 0, str(efacts['days']))
    ew = NV.write_manuscript(erun, mode=NV.MODE_NOVEL)
    etext = ew['path'].read_text(encoding='utf-8')
    check('空运行：稿子写明「尚无任何已落盘的天」', '尚无任何已落盘的天' in etext)
    er = asyncio.run(B.export_bundle(erun, ['novel', 'reference']))
    check('空运行：调度不抛异常', isinstance(er, dict) and er['ok'])

    # ── 10. 开关读取 ──
    # [EN] ── 10. Switch reading ──
    saved = {k: CFG.raw(k) for k in B.KIND_AUTO_KEY.values()}
    try:
        CFG.set('EXPORT_ON_END_NOVEL', 'false')
        CFG.set('EXPORT_ON_END_REFERENCE', 'true')
        CFG.set('AUTO_SUMMARY_ON_END', 'true')
        CFG.set('EXPORT_ON_END_GUIDE', 'false')
        got = B.auto_kinds()
        check(f'开关：关掉{NV._STEM[NV.MODE_NOVEL]}后不在自动列表', 'novel' not in got, str(got))
        check('开关：报告打开后在自动列表', 'report' in got, str(got))
        CFG.set('EXPORT_ON_END_NOVEL', 'true')
        check('开关：重新打开后回到列表', 'novel' in B.auto_kinds())
    finally:
        for k, v in saved.items():
            CFG.set(k, v if v != '' else 'false')

    report['logic'] = {'facts': facts, 'reference_len': len(rtext),
                       'novel_len': len(ntext)}
    report['ok'] = all(ok for _, ok, _ in _checks)


# ══════════════════════════════════════════════════════════════
#  B. 真机验证
# [EN] B. Real-machine verification
# ══════════════════════════════════════════════════════════════
def walk(node, out: list) -> None:
    """遍历控件树。**遇到 str 就停**——见 all_texts 里那条注释。
        English:
    Traverse the control tree. **Stop when a str is encountered** — see that comment in all_texts.
    """
    if node is None or isinstance(node, str):
        return
    out.append(node)
    for attr in ('controls', 'content', 'actions', 'title'):
        v = getattr(node, attr, None)
        if isinstance(v, list):
            for c in v:
                walk(c, out)
        elif v is not None:
            walk(v, out)


def _file_links(root) -> list:
    """收集 `root` 里所有**可点的文件链接行**（带 `_file_open` 抓手的控件）。

    ⚠ 按**抓手**认，不按屏幕文字认：文件名可能重名、也可能被省略号截断；
      `mk_file_link` 会把目标路径钉在 `_file_open` 上，那才是"这一行指向哪个文件"
      的唯一真相。

        English:
    Collect every **clickable file link row** inside `root` (controls carrying a `_file_open`
    handle).
        ⚠ Recognize by **handle**, not by screen text: filenames can collide or be cut by an
          ellipsis; `mk_file_link` pins the target path on `_file_open`, which is the only truth for
          "which file this row points at".
    """
    nodes: list = []
    walk(root, nodes)
    return [c for c in nodes if getattr(c, '_file_open', None)]


def all_texts(page, extra_roots: list | None = None) -> list[str]:
    nodes: list = []
    for c in page.controls:
        walk(c, nodes)
    # 对话框不在 page.controls 里，直接把我们构造的那个对象传进来遍历
    # [EN] The dialog is not in page.controls; directly pass in the object we constructed and traverse it
    for root in (extra_roots or []):
        walk(root, nodes)
    vals: list[str] = []
    for c in nodes:
        if isinstance(c, ft.Text) and c.value:
            vals.append(str(c.value))
        if isinstance(c, ft.Checkbox) and c.label:
            vals.append(str(c.label))
        if isinstance(c, ft.TextField):
            for a in ('value', 'hint_text'):
                x = getattr(c, a, None)
                if x:
                    vals.append(str(x))
        # 按钮文字可能是**裸字符串**：Flet 1.0 里 `FilledButton("导出")`
        # 的第一个位置参数就是 `content`，于是 content 是 str 而不是 ft.Text。
        # 少了这条，所有按钮的文字都采不到（本脚本第一次跑就是这么翻车的）。
        # [EN] Button text may be a **bare string**: in Flet 1.0, `FilledButton("export")`
        # [EN] 's first positional argument is `content`, so content is a str rather than ft.Text.
        # [EN] Without this, no button text can be collected (this script failed exactly this way on its first
        # [EN] run).
        v = getattr(c, 'content', None)
        if isinstance(v, str) and v.strip():
            vals.append(v)
    return vals


async def main(page: ft.Page) -> None:
    from gui.app_flet import NovelWorldApp
    from i18n import set_lang
    set_lang(_lang)

    app = NovelWorldApp()
    app.main(page)
    page.enable_screenshots = True
    page.update()
    await asyncio.sleep(2.2)

    # ★★★ **`isolate_projects_dir()` 的返回值是「换之前的老值」，不是新目录** ——
    #   以前写成 `Path(VU.isolate_projects_dir(base)) / '导出验证'`，
    #   拼出来的是**用户的真实项目目录** + `导出验证`（本机实测：
    #   `C:\小说世界AI模拟\项目\导出验证`）⇒ 这一支判据一直在往用户真项目里写，
    #   只是收尾的 `safe_rmtree` 顺手删掉了，所以一直没被发现；
    #   一旦某次跑到一半被 Kill，`导出/*.md` 就留在那儿 ⇒ 下一轮
    #   「列表与磁盘一一对应」假红（版本号从 v2 起步）。**修过一次的名场面。**
    #   ⇒ 正确用法：返回值丢掉，自己留一份 `seed` 当落点。
    # [EN] ★★★ **`isolate_projects_dir()` returns the OLD value ("what it was before the swap"),
    # [EN] not the new directory** --
    # [EN] it used to be written as `Path(VU.isolate_projects_dir(base)) / '导出验证'`, which built
    # [EN] **the user's real projects directory** + `导出验证` (measured on this machine:
    # [EN] `C:\小说世界AI模拟\项目\导出验证`) => this criterion kept writing into the user's real
    # [EN] project, and only the `safe_rmtree` at teardown deleted it, which is why nobody noticed.
    # [EN] Once a run is killed midway, `导出/*.md` stays behind => the next round's "list matches
    # [EN] disk" goes false red (version numbers start at v2).
    # [EN] => Correct usage: drop the return value and keep your own `seed` as the landing spot.
    seed = Path(__import__('tempfile').mkdtemp(prefix='nws_export_proj_'))
    VU.isolate_projects_dir(seed)
    proj_root = seed / '导出验证'
    try:
        # ★★★ **每轮一个全新目录**（2026-10-17 改）：
        #   以前是 `assets/screenshots/_proj/导出验证` 这个**固定路径**，
        #   而收尾的 `safe_rmtree` 是在**窗口还开着**的时候跑的
        #   （`main()` 的 finally 在 `await shutdown(...)` 之前）⇒ Windows 上
        #   文件句柄还被占着，`ignore_errors=True` 就**静默失败** ⇒ 上一轮的
        #   `导出/*.md` 留下来 ⇒ 下一轮「列表与磁盘一一对应」假红。
        #   实测：反例法连跑 9 轮，每轮都多出这一条无关的红。
        #   ⇒ `mkdtemp()`：一个进程一个目录，不依赖"删得掉"。
        # [EN] ★★★ **A brand-new directory every round** (changed 2026-10-17): it used to be the
        # [EN] **fixed path** `assets/screenshots/_proj/导出验证`, while the teardown
        # [EN] `safe_rmtree` runs **while the window is still open** (`main()`'s finally comes before
        # [EN] `await shutdown(...)`) => on Windows the file handles are still held, so
        # [EN] `ignore_errors=True` **fails silently** => the previous round's `导出/*.md` remains =>
        # [EN] the next round's "list matches disk" goes false red.
        # [EN] Measured: the mutation harness ran 9 rounds and every round gained this unrelated red.
        # [EN] => `mkdtemp()`: one directory per process, no dependence on "being deletable".
        proj_root.mkdir(parents=True, exist_ok=True)
        for sub in ('设定集', '优化后设定', '完整设定集导出'):
            (proj_root / sub).mkdir(exist_ok=True)
        proj = Project(proj_root, '导出验证')
        proj.write_nwsproj()
        make_run(proj_root / '第1次模拟2026-01-01-00-00', days=2, with_image=False)
        app.current_project = proj

        app.show_main_screen()
        page.update()
        await asyncio.sleep(0.9)

        texts = all_texts(page)
        # ★ 2026-10-29 改口径（用户：「修改导出按钮为推演结果按钮」）：
        #   运行页入口改叫「推演结果」，导出收进它的右上角 —— 那条变异要防的东西
        #   （"运行页有能通到导出的入口"）还在，只是名字换了 ⇒ 判据跟着查新名。
        # [EN] ★ 2026-10-29, recut (user: "rename the export button to a results button"):
        # [EN] the run-page entry is now "Results"; Export lives at its top right. The thing the
        # [EN] mutation guarded ("an entry leading to export exists on the run page") is still there,
        # [EN] only renamed => the criterion follows the new name.
        report['main_texts_has_results_btn'] = any(
            ('推演结果' in t) and ('📊' in t) for t in texts) or \
            any(t.strip() == '📊 Results' for t in texts)
        check('真机：运行界面有「推演结果」按钮', report['main_texts_has_results_btn'],
              str([t for t in texts if '推演结果' in t or '导出' in t][:5]))

        # ── 打开导出对话框（真的 show_dialog + update）──
        # [EN] ── Open the export dialog (real show_dialog + update) ──
        app.show_export_dialog()
        page.update()
        await asyncio.sleep(0.7)
        ui = getattr(app, '_export_ui', None)
        check('真机：导出句柄已挂出（可被外部驱动）', ui is not None)
        dtexts = all_texts(page, extra_roots=[ui['dlg']] if ui else None)
        report['dialog_texts'] = dtexts
        for token in ('① 本次要导出什么', '② 导出到哪', '③ 结束时自动导出',
                      NV._STEM[NV.MODE_NOVEL], NV._STEM[NV.MODE_REFERENCE],
                      '运行报告', '写作指导', '开始导出'):
            check(f'真机：对话框含「{token}」',
                  any(token in t for t in dtexts), f'got {len(dtexts)} texts')

        png_dlg = await page.take_screenshot()
        (OUTDIR / f'export_dialog{SUFFIX}.png').write_bytes(png_dlg)
        if ui:
            # 只勾零成本的两项，避免真调 LLM
            # [EN] Check only the two zero-cost items, to avoid really calling the LLM
            ui['picks']['novel'].value = True
            ui['picks']['reference'].value = True
            ui['picks']['report'].value = False
            ui['picks']['guide'].value = False
            ui['polish'].value = False
            page.update()

            # **走真实点击路径**
            # [EN] **Go through the real click path**
            ui['btn'].on_click(None)
            for _ in range(120):                       # 最多等 12s
            # [EN] Wait up to 12s
                await asyncio.sleep(0.1)
                if not ui['btn'].disabled:
                    break
            await asyncio.sleep(0.4)

            res_texts = [c.value for c in ui['result'].controls
                         if isinstance(c, ft.Text) and c.value]
            report['result_lines'] = res_texts
            check('真机：结果出现 ✓ 标记',
                  any(r.startswith('✓') for r in res_texts), str(res_texts[:4]))

            # ── ★★★ 导出的**文件列表每一行都能点、点了会打开**（2026-10-17 用户点名）──
            #   用户原话：「我希望导出按钮最后的导出的文件的列表我都能点击 点了之后
            #   自动用默认md编辑器打开这些文件」。
            #   ⚠ 以前这一行是 `ft.Text('→ {path}', selectable=True)` —— 能选中、
            #     点不动。下面这几条**就是为治它写的**：
            #       · ① 列表里每一行都是带 `_file_open` 抓手的可点控件；
            #       · ② 带手型光标 + 下划线（不然"看着不像能点"）；
            #       · ③ 悬停有完整路径；
            #       · ④ **真的点一下**，`_open_path` 收到的是那个文件的路径；
            #       · ⑤ 文件不在了就不再假装能点。
            # [EN] ── ★★★ Every row of the exported **file list is clickable and opens on click**
            # [EN] (named by the user 2026-10-17): "I want every file in the list at the end of the
            # [EN] export button to be clickable, and clicking it should open the file with the
            # [EN] default markdown editor".
            # [EN] ⚠ This row used to be `ft.Text('→ {path}', selectable=True)` -- selectable but not
            # [EN] clickable. The checks below exist to fix exactly that:
            # [EN]   ① every row in the list is a clickable control carrying a `_file_open` handle;
            # [EN]   ② hand cursor + underline (otherwise "it doesn't look clickable");
            # [EN]   ③ hovering shows the full path;
            # [EN]   ④ **really click one**, and `_open_path` receives that file's path;
            # [EN]   ⑤ when the file is gone, stop pretending it is clickable.
            links = _file_links(ui['result'])
            report['file_links'] = [getattr(c, '_file_open', '') for c in links]
            produced_now = sorted(str(p) for p in ui['run'].export_dir.glob('*.md'))
            check('真机：结果里的每个产物都是**一行可点的文件链接**'
                  '（不是"能选中、点不动"的灰字）',
                  bool(links), f'链接 {len(links)} 个 / 落盘 {len(produced_now)} 个')
            # ⚠ 口径（2026-10-21 改）。原来是"链接 == 磁盘上所有 .md"，而导出目录里
            #   还有**过程档案**（分层稿/分层日志/反思记录）—— 它们以前既不列出、也点不到，
            #   于是这条一直红着。根因不是判据太严，是**产品漏了一条**。
            #   ⇒ 现在两边都按同一份清单核对（`NV.SIDE_FILES`，只有一处定义）：
            #     · 交付物（三个正式产物）一个都不许漏；
            #     · 已登记的过程档案也必须能点；
            #     · 目录里出现**没登记**的 .md ⇒ 红（提醒"要么登记、要么删掉"，不许放宽）。
            #   这比"== 磁盘"更严：它连"新产物无声无息地多了"都能抓到。
            # [EN] ⚠ Baseline changed 2026-10-21. It used to be "links == every .md on disk", but the
            # [EN] export dir also holds **process archives** (atelier draft / log / reflection) that
            # [EN] were neither listed nor clickable, so this stayed red. The root cause was not a
            # [EN] strict criterion but a **missing product line**.
            # [EN] => Both sides now check the same list (`NV.SIDE_FILES`, defined once):
            # [EN]   · every deliverable must be present;
            # [EN]   · registered process archives must be clickable;
            # [EN]   · an **unregistered** .md in the dir => red (register it or delete it; do not
            # [EN]     loosen). Stricter than "== disk": it even catches "a new artifact appeared
            # [EN]     silently".
            side_now = sorted(str(p) for p in NV.side_archives(ui['run']))
            want = sorted(produced_now)
            got = sorted(str(Path(x)) for x in report['file_links'])
            check('真机：**落盘的每个 .md 都能在结果里点到**'
                  '（交付物一个不漏 + 过程档案也能点 + 没有没登记的产物）',
                  got == want,
                  f'链接={[Path(x).name for x in got]} '
                  f'磁盘={[Path(x).name for x in want]} 过程档案={[Path(x).name for x in side_now]}')
            check('真机：过程档案（分层稿/分层日志/反思记录）**真的在列表里**',
                  all(s in got for s in side_now),
                  f'档案={[Path(x).name for x in side_now]} / 缺='
                  f'{[Path(s).name for s in side_now if s not in got]}')
            one = links[0] if links else None
            check('真机：那一行带**手型光标**（不然用户不知道能点）',
                  one is not None
                  and getattr(one, 'mouse_cursor', None) == ft.MouseCursor.CLICK,
                  str(getattr(one, 'mouse_cursor', None)))
            # ⚠ 下划线在 **`Text.style.decoration`** 上，不在 `Text.decoration` 上 ——
            #   Flet 1.0 的 `ft.Text` 压根没有 `decoration` 这个属性/参数
            #   （产品代码第一版就写错成 `ft.Text(..., decoration=...)`，
            #    直接 `TypeError` 把整张结果清单炸掉；判据这里也差点跟着错一遍）。
            # [EN] ⚠ The underline lives on **`Text.style.decoration`**, not on `Text.decoration` --
            # [EN] Flet 1.0's `ft.Text` has no `decoration` attribute/parameter at all
            # [EN] (the first version of the product code wrote `ft.Text(..., decoration=...)`, which
            # [EN] raised TypeError and blew up the entire result list; this check nearly repeated the
            # [EN] same mistake).
            def _underlined(ctl) -> bool:
                for x in VU.walk(ctl):
                    st = getattr(x, 'style', None)
                    if (isinstance(x, ft.Text)
                            and getattr(st, 'decoration', None)
                            == ft.TextDecoration.UNDERLINE):
                        return True
                return False
            check('真机：那一行**文件名带下划线**（一屏好几行时靠它认链接）',
                  one is not None and _underlined(one), '')
            tp = str(getattr(one, 'tooltip', '') or '')
            check('真机：悬停能看到**完整路径**（那一行只显示文件名，路径太长）',
                  one is not None and str(getattr(one, '_file_open', '')) in tp,
                  tp[:120])

            # ④ **真的点一下** —— `_open_path` 打桩，确认点下去调的就是这个文件。
            # [EN] ④ **really click one** -- stub `_open_path` and confirm it receives this file.
            opened: list[str] = []
            _real_open = app._open_path
            app._open_path = lambda p, _o=opened: _o.append(str(p))
            try:
                if one is not None and callable(getattr(one, 'on_tap', None)):
                    one.on_tap(None)
                await asyncio.sleep(0.2)
            finally:
                app._open_path = _real_open
            check('★★★ 真机：点一下那一行 → **真的去打开那个文件**'
                  '（`_open_path` 收到的路径 = 那一行指向的文件）',
                  bool(opened) and one is not None
                  and Path(opened[0]) == Path(getattr(one, '_file_open', '')),
                  f'opened={opened}')

            # ⑤ 文件不在了 → 不给手型、不给下划线、不留抓手（不假装能点）。
            # [EN] ⑤ File gone -> no hand cursor, no underline, no handle (don't pretend).
            from gui.app_flet import mk_file_link as _mk
            ghost = _mk(ui['run'].export_dir / '不存在的产物.md', lambda e: None)
            check('★★ 文件不在了那一行**不再假装能点**'
                  '（灰字 +「（文件已不在）」，没有手型也没有 `_file_open` 抓手）',
                  getattr(ghost, '_file_open', None) is None
                  and isinstance(ghost, ft.Text)
                  and '文件已不在' in str(getattr(ghost, 'value', '')),
                  type(ghost).__name__)

            produced = sorted((ui['run'].export_dir).glob('*.md'))
            report['produced'] = [p.name for p in produced]
            # ⚠ 档名一律**从 `NV._STEM` 派生**，判据里不许再写一遍中文：
            #   2026-10-25 这三个名字刚改过一次（原文/参考/版本 → 原始稿/原始稿加细节/最终改写稿），
            #   硬编码一遍就得改一处，漏改的症状是"判据红了但功能是好的"。
            # [EN] Kind names are **derived from `NV._STEM`**; never hardcoded here. These three
            # [EN] were renamed once already (2026-10-25), and a stale copy shows up as a red
            # [EN] criterion on working code.
            _stem_of = {NV.MODE_RAW: NV._STEM[NV.MODE_RAW],
                        NV.MODE_NOVEL: NV._STEM[NV.MODE_NOVEL],
                        NV.MODE_REFERENCE: NV._STEM[NV.MODE_REFERENCE]}
            _stems = tuple(_stem_of.values())
            check('真机：导出目录真的落了文件',
                  any(p.name.startswith(_stem_of[NV.MODE_NOVEL] + '_v') for p in produced)
                  and any(p.name.startswith(_stem_of[NV.MODE_REFERENCE] + '_v') for p in produced),
                  str(report['produced']))

            # ★★★ 文件名必须自带天数（2026-10-25 用户："名字太长了""看不出来具体是怎么回事"）
            #   守两件事：
            #     ① 名字里有 `_第N天` / `_第N-M天` —— 光看名字就知道这份稿写到第几天，
            #        不用打开两个文件左右比对；同一份稿重导只有版本号变，天数不变。
            #     ② `_vN` 仍在**最前面** —— `next_version()` 靠 glob 找编号，
            #        编号挪到中间会让下次导出退回 v1 重号（实测过，症状与文件名毫无关联）。
            # [EN] ★★★ The filename must carry the day range (user, 2026-10-25: "the names are too
            # [EN] long" / "can't tell what's actually in them"). Guards two things: (1) the name
            # [EN] contains `_第N天` / `_第N-M天`, so you can tell how many days a draft covers
            # [EN] without opening two files; (2) `_vN` is still **first**, because `next_version()`
            # [EN] finds the index via glob and moving it later silently restarts at v1.
            named = [p.name for p in produced if p.name.startswith(_stems)]
            # ⚠ 「一天都没落盘」的产物**没有天数可写**（`_span([])` 返回空串），
            #   文件头会写「尚无任何已落盘的天」。那不是缺陷，别把它算成"名字没带天数"
            #   —— 否则将来真跑出 0 天会在这里假红一次。
            # [EN] ⚠ A product with **zero flushed days** has no day range to write (`_span([])`
            # [EN] returns ""), and its header says "no day flushed yet". That is not a defect;
            # [EN] counting it as "filename lacks the range" would produce a false red later.
            def _has_days(pth) -> bool:
                try:
                    return '尚无任何已落盘的天' not in pth.read_text(encoding='utf-8', errors='ignore')[:800]
                except OSError:
                    return False

            named_with_days = [p.name for p in produced
                               if p.name.startswith(_stems) and _has_days(p)]
            _head = '|'.join(re.escape(s) for s in _stems)
            check('★★★ 导出文件名自带天数（`…_v2_第1-2天.md`），且 `_vN` 仍在最前面',
                  bool(named_with_days) and all(
                      re.match(rf'^({_head})_v\d+_第[\d,\-]+天', n) for n in named_with_days),
                  str(named))
            check('而且 `_vN` 一律在最前面（编号挪到中间会让下次导出退回 v1 重号）',
                  bool(named) and all(
                      re.match(rf'^({_head})_v\d+', n) for n in named),
                  str(named))

            # ⚠⚠ 档名彼此不许成前缀（2026-10-26 第一次出现这种形状）：
            #   `原始稿` 是 `原始稿加细节` 的前缀。`next_version()` 按
            #   `glob(f'{stem}_v*.md')` 数编号 —— 若某个档名是另一个的前缀、
            #   且 `_v` 紧跟其后，就会把别人的编号算进自己头上（v3 直接跳到 v5 之类）。
            #   本次实测**不冲突**（"原始稿"后面跟的是"加细节"、不是 `_v`），
            #   但这条必须钉住：以后再加档名（比如"原始稿加结局"）时，
            #   若命名不慎就成了真冲突，而症状是"版本号莫名其妙跳号"，看不出跟命名有关。
            # [EN] ⚠⚠ Kind names must not be prefixes of one another (first time this shape
            # [EN] appeared, 2026-10-26): `原始稿` is a prefix of `原始稿加细节`. `next_version()`
            # [EN] counts via `glob(f'{stem}_v*.md')`, so if one name prefixes another **and `_v`
            # [EN] follows immediately**, it steals the other's numbers (jumps from v3 to v5).
            # [EN] Measured now: no collision ("原始稿" is followed by "加细节", not `_v`). Pinned
            # [EN] anyway, because a future name would make it real and the symptom (version
            # [EN] numbers jumping) shows no connection to naming.
            import fnmatch as _fnm
            _clash = []
            for a in _stems:
                for b in _stems:
                    if a != b and _fnm.fnmatch(f'{b}_v9_x.md', f'{a}_v*.md'):
                        _clash.append(f'{a} 会误匹配 {b}')
            check('档名彼此不成前缀（否则版本号会互相抢编号）',
                  not _clash, str(_clash or _stems))

            page.update()
            await asyncio.sleep(0.4)
            png_done = await page.take_screenshot()
            (OUTDIR / f'export_done{SUFFIX}.png').write_bytes(png_done)

        # ── 「推演结果」对话框真机走一遍（2026-10-29）──
        #   ⚠ 必须排在导出**之后**：预览打开时会把缺的零成本稿当场装订一份落盘，
        #     而上面那条「落盘的每个 .md 都能在结果里点到」是**闭环口径**
        #     （这次导出的清单 == 磁盘）—— 排在它前面等于先往盘上塞文件再查账，必红。
        # [EN] ── Walk the "Derivation Results" dialog on the real machine (2026-10-29) ──
        # [EN] ⚠ Must come **after** the export: opening the preview binds any missing zero-cost
        # [EN] draft to disk, and the "every .md on disk is clickable" check above is a **closed-world**
        # [EN] reading (this export's list == disk) -- placing it before would plant files first and
        # [EN] audit second, a guaranteed red.
        app.show_results_dialog()
        page.update()
        await asyncio.sleep(0.7)
        rui = getattr(app, '_results_ui', None)
        check('真机：推演结果句柄已挂出（可被外部驱动）', rui is not None)
        if rui:
            # ⚠ 五个页签名读 `TabBar.tabs[i].label`（**结构**），不走文本提取 ——
            #   TabBar 的标签在 `all_texts` 里提不到（实测：运行报告那条一直红着，
            #   其余四个是靠文件链接/按钮文字碰巧凑齐的）。
            # [EN] ⚠ Read the five tab labels **structurally** from `TabBar.tabs[i].label`, not via
            # [EN] text extraction -- TabBar labels are invisible to `all_texts` (measured: the
            # [EN] 运行报告 check stayed red while the other four passed by luck via file links).
            # ⚠ 这里用**字面中文**：`t` 没进本判据的命名空间（曾经 NameError 把
            #   整段打崩，还因为 fatal 不进「失败项」清单看起来像全绿）。
            #   真机段的其余 token（'运行报告' 等）也都是字面中文，同一口径。
            # [EN] ⚠ Literal Chinese here: `t` is not in this criterion's namespace (a NameError
            # [EN] once crashed the whole section, and since `fatal` never enters the printed
            # [EN] failure list it *looked* all-green). The other real-machine tokens ('运行报告'
            # [EN] etc.) are literal Chinese too -- same reading.
            tabbar = rui['tabs'].content.controls[0]
            labels = [getattr(tb, 'label', '') for tb in tabbar.tabs]
            for token in ('原始稿', '最终改写稿', '原始稿加细节',
                          '运行报告', '写作指导'):
                check(f'真机：推演结果有页签「{token}」', token in labels, str(labels))
            rtexts = all_texts(page, extra_roots=[rui['dlg']])
            for token in ('LLM润色稿', '自动导出设置'):
                check(f'真机：推演结果含「{token}」',
                      any(token in x for x in rtexts), f'got {len(rtexts)} texts')
        page.pop_dialog()
        page.update()
        await asyncio.sleep(0.4)

        report['ok'] = all(ok for _, ok, _ in _checks)
    except Exception:
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        try:
            VU.safe_rmtree(proj_root, ignore_errors=True)
            report['cleaned'] = str(proj_root)
        except Exception as e:
            report['cleanup_error'] = str(e)
        report['checks'] = [{'name': n, 'ok': o, 'detail': d} for n, o, d in _checks]
        (OUTDIR / f'export_report{SUFFIX}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        failed = [n for n, o, _ in _checks if not o]
        print('=' * 62)
        print(f'导出验证：{len(_checks) - len(failed)} / {len(_checks)} 通过')
        if failed:
            print('失败项：')
            for n in failed:
                print('   ✗', n)
        print('=' * 62)
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be set **before closing the window**: `page.window.destroy()` will throw
        # [EN] CancelledError
        # [EN] Cancels this coroutine, written on the line after `await shutdown(page)`: `exit_now(...)`
        # [EN] **Never actually executed** (exit code always 0 = false green). See
        # [EN] `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report.get('ok') else 2)


if __name__ == '__main__':
    # ★★★ 逻辑段的工作目录**每次都要是全新的**（2026-10-17 改）：
    #   以前是固定用 `assets/screenshots/_export_tmp` + 开跑前 `safe_rmtree`。
    #   Windows 上刚退出的进程还占着文件句柄时，`rmtree(ignore_errors=True)` 会**静默失败**
    #   ⇒ 上一轮的 `导出/*.md` 还在 ⇒ 这一轮版本号从 v2 起步 ⇒
    #   「版本自增：v1 / v2」「报告：文件名带版本」这些**跟本次改动毫无关系**的项全红。
    #   实测：反例法连跑 9 轮，从第 2 轮起每轮都红这几条 —— 把真正要打红的那条埋了。
    #   ⇒ 用 `mkdtemp()`：一个进程一个目录，天然不撞，也不依赖"删得掉"。
    # [EN] ★★★ The logic section's working directory **must be brand new every time** (changed
    # [EN] 2026-10-17): it used to be the fixed `assets/screenshots/_export_tmp` cleaned up front.
    # [EN] On Windows, when a just-exited process still holds a file handle, `rmtree(ignore_errors=True)`
    # [EN] **fails silently** => the previous round's `导出/*.md` remains => this round's version numbers
    # [EN] start at v2 => "version auto-increment: v1 / v2", "report: filename carries version" and
    # [EN] similar checks go red **for reasons unrelated to the change under test**.
    # [EN] Measured: the mutation harness ran 9 rounds and every round from the 2nd on had these reds --
    # [EN] burying the one that was supposed to go red.
    # [EN] => Use `mkdtemp()`: one directory per process, no collisions by construction, and it does not
    # [EN] depend on "being deletable".
    if LOGIC_ONLY:
        import tempfile as _tf
        tmpdir = Path(_tf.mkdtemp(prefix='nws_export_logic_'))
        try:
            run_logic(tmpdir)
        except Exception as e:
            report['fatal'] = traceback.format_exc()
            report['ok'] = False
            print('逻辑验证异常：', e)
        finally:
            VU.safe_rmtree(tmpdir, ignore_errors=True)
        report['checks'] = [{'name': n, 'ok': o, 'detail': d} for n, o, d in _checks]
        (OUTDIR / f'export_logic_report{SUFFIX}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        failed = [n for n, o, _ in _checks if not o]
        print('=' * 62)
        print(f'导出验证（仅逻辑）：{len(_checks) - len(failed)} / {len(_checks)} 通过')
        for n in failed:
            print('   ✗', n)
        print('=' * 62)
        exit_now(0 if not failed else 2)
    else:
        import tempfile as _tf
        tmpdir = Path(_tf.mkdtemp(prefix='nws_export_logic_'))
        try:
            run_logic(tmpdir)
        except Exception as e:
            report['logic_fatal'] = traceback.format_exc()
            print('逻辑验证异常：', e)
        finally:
            VU.safe_rmtree(tmpdir, ignore_errors=True)
        try:
            ft.run(main)
        except Exception:
            report['fatal'] = traceback.format_exc()
            report['ok'] = False
            report['checks'] = [{'name': n, 'ok': o, 'detail': d} for n, o, d in _checks]
            (OUTDIR / f'export_report{SUFFIX}.json').write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            exit_now(2)
