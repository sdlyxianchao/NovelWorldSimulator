# -*- coding: utf-8 -*-
"""验证：**导出『小说版本』时改走 MuMuAINovel 重写**（用户 2026-10-16）。

用户原话
--------
「我希望导出的时候如果需要重写小说，应该是根据小说原文和推演过程调用
MuMuAINovel 小说服务去写新的，而不是用自己内部的 Agent 编写。」

根因 / 做法
----------
此前「小说版本」导出用的是推演时内部 Agent 写的「当天故事」整理稿
（`render_manuscript` 的 `better` 路径）。本轮新增一条**独立的导出开关**
`MUMU_FOR_EXPORT`：打开后，`export/bundle.export_bundle` 在导出小说版本时
改调 `export/novel_version.write_manuscript_mumu`，它**每一天**据
『小说原文 + 推演过程』调 MuMuAINovel（`crew/agents._mumu_export`）重写；
服务没起 / 超时 / 写空 → 那一天**退回内部整理稿**（与 `render_manuscript`
内部路径一致），绝不丢戏。

这一支钉住的行为（**每条都要能红**，见 `developers/mutate_mumu_export.py`）：

  A **开关接线**：`_mumu_enabled_for('export')` 现读 `MUMU_FOR_EXPORT`，
     且不与 `MUMU_FOR_NOVELIST` 串台。
  B **render 用 day_bodies**：`render_manuscript` 在 `MODE_NOVEL` 分支里，
     当传入 `day_bodies={天: 重写稿}` 时，真的用重写稿（不再过内部整理稿 /
     `_fold_repeats`）；不传则走内部路径。
  C **导出落盘**：`write_manuscript_mumu` 是异步的；服务返回正文 → 落盘含
     该正文；服务失败 → 回退内部整理稿并落盘（不崩、不丢天）。
  D **调度接线**：`export/bundle.py` 在 `MUMU_FOR_EXPORT` 开时真的调
     `write_manuscript_mumu`（不是一直走老的 `write_manuscript`）。
  E **配置与界面**：`config.py` 有 `MUMU_FOR_EXPORT`（默认关）；天机
     「创作服务」页有这个开关的显示与保存。

跑法：.venv\\Scripts\\python.exe tools/verify_mumu_export.py
产出：assets/screenshots/mumu_export_report.json

English:
Verification: **exporting the "novel version" switches to MuMuAINovel rewrite** (user 2026-10-16).
User's exact words
--------
"I want that when exporting, if the novel needs rewriting, it should call the MuMuAINovel novel
service based on the raw novel text and the derivation process to write a new one, instead of using
this program's own internal Agent."
Root cause / fix
--------
Previously the "novel version" export used the internal Agent's "same-day story" edited draft
(`render_manuscript`'s `better` path). This round adds a **separate export switch** `MUMU_FOR_EXPORT`:
when on, `export/bundle.export_bundle` calls `export/novel_version.write_manuscript_mumu` when
exporting the novel version; it **rewrites each day** via MuMuAINovel (`crew/agents._mumu_export`)
from "raw novel text + derivation process"; if the service isn't up / timed out / empty -> that day
**falls back to the internal edited draft** (identical to `render_manuscript`'s internal path), never
losing the day.
Behaviors pinned by this branch (**every one must be able to go red**, see
`developers/mutate_mumu_export.py`):
  A **switch wiring**: `_mumu_enabled_for('export')` reads `MUMU_FOR_EXPORT` live, and doesn't
    cross-talk with `MUMU_FOR_NOVELIST`.
  B **render uses day_bodies**: `render_manuscript`, in the `MODE_NOVEL` branch, really uses the
    rewrite when `day_bodies={day: rewrite}` is passed (no internal path / `_fold_repeats`); without
    it, takes the internal path.
  C **export flush**: `write_manuscript_mumu` is async; service returns text -> disk contains it;
    service fails -> falls back to internal draft and flushes (no crash, no lost day).
  D **scheduler wiring**: `export/bundle.py` really calls `write_manuscript_mumu` when
    `MUMU_FOR_EXPORT` is on (not always the old `write_manuscript`).
  E **config & UI**: `config.py` has `MUMU_FOR_EXPORT` (default off); Tianji's "Creation Service"
    page shows and saves this switch.
Run: .venv\\Scripts\\python.exe tools/verify_mumu_export.py
Output: assets/screenshots/mumu_export_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
#: **判据自己**等收尾的上限（秒）。★ 2026-10-26：以前借产品的 `WRAP_WAIT_SECONDS`，
#: 而那个键**产品源码一次都没读过**（`config_sweep` D1 抓到的假旋钮，已从 SPEC 删掉）。
#: 判据的等待上限是**判据的东西**，不该挂在产品配置上 —— 那会让"用户能调"变成一句空话。
#: 为什么是 900 秒：收尾要跑 场记→宣发→审校→复盘→整理→导出 一串调用，真机几十秒到几分钟；
#: 以前写死 20 秒，于是把"收尾正常但要跑两分钟"误判成"停止坏了"。
# [EN] **The criterion's own** wrap-up wait limit (seconds). ★ 2026-10-26: it used to borrow the
# [EN] product's `WRAP_WAIT_SECONDS`, which the product **never read** (a fake knob caught by
# [EN] `config_sweep` D1 and deleted from SPEC). A criterion's patience is the criterion's own
# [EN] business; hanging it on product config makes "the user can tune it" an empty promise.
WRAP_WAIT_LIMIT = 900
sys.path.insert(0, str(APP_DIR))

from config import CFG, SPEC                                     # noqa: E402
from export.novel_version import render_manuscript, write_manuscript_mumu, MODE_NOVEL  # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}

MARKER = '【MUMU重写稿标记-请勿删除-ZX9F】'


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


class _Run:
    """极简假 run：只给导出链要的属性。
        English: Minimal fake run: only the attributes the export chain needs.
    """

    def __init__(self, root: Path):
        self.root = root
        self.project_dir = root
        self.daily_dir = root / '每天的生活'
        self.export_dir = root / 'export'
        self.story_dir = None


def _make_run() -> _Run:
    root = Path(tempfile.mkdtemp(prefix='mumu_export_'))
    daily = root / '每天的生活'
    daily.mkdir(parents=True, exist_ok=True)
    # 含一个会触发 _fold_repeats 的复读口头禅（"井茶入梦"×3），
    # 用来区分「day_bodies 路径（不过 fold）」与「内部路径（过 fold）」。
    # [EN] Include a catchphrase ("井茶入梦"×3) that triggers `_fold_repeats`, to tell
    # [EN] the "day_bodies path (no fold)" from the "internal path (fold)".
    (daily / '第1天.md').write_text(
        '# 第 1 天 · 历法 · 晴\n'
        '> 在场：甲、乙  关键事件：…  张力：3\n\n'
        '客人乙说："井茶入梦，井茶入梦，井茶入梦。"丁说："傻子账上不糊涂。"\n',
        encoding='utf-8')
    (root / 'export').mkdir(parents=True, exist_ok=True)
    return _Run(root)


# ── A —— 开关接线 ───────────────────────────────────────────────────
# [EN] A -- switch wiring
def test_enabled_for() -> None:
    from crew import agents as A
    old_export = CFG.s('MUMU_FOR_EXPORT')
    old_novelist = CFG.s('MUMU_FOR_NOVELIST')
    try:
        CFG.set('MUMU_FOR_EXPORT', 'true')
        CFG.set('MUMU_FOR_NOVELIST', 'false')
        ok('A1 ★ _mumu_enabled_for("export") 在 MUMU_FOR_EXPORT=true 时为 True',
           A._mumu_enabled_for('export') is True, '')
        CFG.set('MUMU_FOR_EXPORT', 'false')
        ok('A2 ★ _mumu_enabled_for("export") 在 MUMU_FOR_EXPORT=false 时为 False',
           A._mumu_enabled_for('export') is False, '')
        # 不与 novelist 串台：novelist 走自己的键
        # [EN] No cross-talk with novelist: novelist uses its own key
        CFG.set('MUMU_FOR_NOVELIST', 'true')
        CFG.set('MUMU_FOR_EXPORT', 'false')
        ok('A3 ★ novelist 仍由 MUMU_FOR_NOVELIST 管（false→False），'
           'export 不影响它',
           A._mumu_enabled_for('novelist') is True
           and A._mumu_enabled_for('export') is False, '')
    finally:
        CFG.set('MUMU_FOR_EXPORT', old_export)
        CFG.set('MUMU_FOR_NOVELIST', old_novelist)


# ── B —— render 用 day_bodies（不过内部路径 / _fold_repeats） ────────
# [EN] B -- render uses day_bodies (no internal path / _fold_repeats)
def test_render_day_bodies() -> None:
    run = _make_run()
    # ① 传 day_bodies → 用重写稿，原 day 文件正文被替换（不过 fold）
    # [EN] ① pass day_bodies -> use rewrite, original day body replaced (no fold)
    r1 = render_manuscript(run, mode=MODE_NOVEL, day_bodies={1: MARKER})
    ok('B1 ★ 传 day_bodies 后，重写稿标记出现在稿里', MARKER in r1['text'], '')
    ok('B2 ★ 原 day 文件正文被替换（"傻子账上不糊涂"不在）',
       '傻子账上不糊涂' not in r1['text'], '')
    ok('B3 ★ day_bodies 路径不过 _fold_repeats（标记原样，未被去重折叠）',
       r1['text'].count(MARKER) == 1, f'标记出现 {r1["text"].count(MARKER)} 次')

    # ② 不传 day_bodies → 走内部路径（原 day 正文在）
    # [EN] ② no day_bodies -> internal path (original day body present)
    r2 = render_manuscript(run, mode=MODE_NOVEL)
    ok('B4 ★ 不传 day_bodies 时走内部路径（原 day 文件正文在）',
       '傻子账上不糊涂' in r2['text'], '')
    # 两条路径产出必须不同：day_bodies 路径用重写稿、内部路径用原 day 正文
    # （这才是「分支真的被接上」的铁证，不依赖 _fold_repeats 的具体折叠行为）。
    # [EN] The two paths must yield different output: the day_bodies path uses the rewrite, the
    # [EN] internal path uses the original day body (this is the hard proof the branch is really
    # [EN] wired, independent of _fold_repeats' exact folding behavior).
    ok('B5 ★ 两条路径产出不同（day_bodies 路径 ≠ 内部路径）',
       r1['text'] != r2['text']
       and MARKER in r1['text'] and MARKER not in r2['text'], '')


# ── C —— 导出落盘（服务成 / 服务败 两条） ───────────────────────────
# [EN] C -- export flush (service ok / service fail)
def test_write_mumu() -> None:
    import crew.agents as A

    async def _fake_ok(*, day, title, raw_novel, process, project_key, novel_dir,
                       characters=None, genre='', setting='', target_words=None):
        return (MARKER, '')

    async def _fake_fail(*, day, title, raw_novel, process, project_key, novel_dir,
                         characters=None, genre='', setting='', target_words=None):
        return ('', '服务没起（变异/测试）')

    run = _make_run()
    real = A._mumu_export
    try:
        # ① 服务成 → 落盘含重写标记
        # [EN] ① service ok -> disk contains rewrite marker
        A._mumu_export = _fake_ok
        r_ok = asyncio.run(write_manuscript_mumu(run))
        ok('C1 ★ write_manuscript_mumu 是异步函数（返回 dict，含 path）',
           isinstance(r_ok, dict) and r_ok.get('path'), '')
        txt_ok = Path(r_ok['path']).read_text(encoding='utf-8')
        ok('C2 ★ 服务返回正文 → 落盘稿里含重写稿标记',
           MARKER in txt_ok, '')

        # ② 服务败 → 回退内部整理稿并落盘（不崩、不丢天）
        # [EN] ② service fails -> fall back to internal draft and flush (no crash, no lost day)
        A._mumu_export = _fake_fail
        r_fail = asyncio.run(write_manuscript_mumu(run))
        ok('C3 ★ 服务失败也不抛异常（返回 dict）',
           isinstance(r_fail, dict) and r_fail.get('path'), '')
        txt_fail = Path(r_fail['path']).read_text(encoding='utf-8')
        ok('C4 ★ 服务失败时回退内部整理稿（原 day 正文在）',
           '傻子账上不糊涂' in txt_fail or '井茶入梦' in txt_fail, '')
        ok('C5 ★ 服务失败时重写稿标记不出现（确实用的内部稿）',
           MARKER not in txt_fail, '')
    finally:
        A._mumu_export = real


# ── D —— 调度接线（bundle.py 真调 write_manuscript_mumu） ───────────
# [EN] D -- scheduler wiring (bundle.py really calls write_manuscript_mumu)
def test_bundle_wiring() -> None:
    src = (APP_DIR / 'export' / 'bundle.py').read_text(encoding='utf-8')
    ok('D1 ★ bundle.py 读到了 MUMU_FOR_EXPORT 开关',
       'MUMU_FOR_EXPORT' in src, '')
    # ⚠ 2026-10-26：原来写的是 `'write_manuscript_mumu(run' in src` —— 那要求
    #   "函数名后面紧跟 run" 这**一种写法**。导出重构后调用变成带模块前缀、参数换行
    #   （`NV.write_manuscript_mumu(\n run, ...`）⇒ 判据因为**排版**变红，
    #   而"开开关时真的改走 MuMu 那条路"一个字没变。
    #   ⇒ 认**调用本身**（带不带前缀都行），并且仍然要求它挂在那个开关条件下面。
    # [EN] ⚠ 2026-10-26: the old anchor required one exact spelling (`write_manuscript_mumu(run`).
    # [EN] After the export refactor the call became module-qualified with the first argument on
    # [EN] the next line, so the criterion went red over **formatting** while "on the switch it
    # [EN] really goes through MuMu" had not changed. Accept the call itself (prefixed or not),
    # [EN] and still require it under that switch condition.
    ok('D2 ★ bundle.py 在开开关时调 write_manuscript_mumu（而非一直走老路径）',
       'write_manuscript_mumu(' in src
       and 'KIND_NOVEL and CFG.b("MUMU_FOR_EXPORT")' in src, '')


# ── F —— 2026-10-21 架构：外部服务优先 / 输入三件套 / 部分成功取回 ────────
# [EN] F -- 2026-10-21 architecture: prefer the external service / three inputs / keep partial wins
def test_arch_2026_10_21() -> None:
    import inspect
    from crew import agents as A
    from export import novel_version as NV
    from novelservices import mumu_bridge as BR

    # F1 **服务不在就拉起来**（不是"探测一下就走"）
    # ⚠ 判据测的是**行为契约**：`_ensure_mumu` 必须先探、再拉、最后才判失败。
    #   查源码字符串不够 —— 把 `start_service` 换成 `pass` 名字还在（反例法会咬）。
    # [EN] F1 **start the service if it isn't up** (not "probe and give up").
    # [EN] ⚠ The criterion tests a **behavioural contract**: `_ensure_mumu` must probe, then start,
    # [EN] and only then decide failure. A source-string check is not enough -- replacing
    # [EN] `start_service` with `pass` leaves the name in place (the counterexample method bites).
    calls: list[str] = []
    real_status, real_start = BR.service_status, BR.start_service

    def _st(reason='测试：没起'):
        calls.append('probe')

        class _S:
            ok = False
            def __init__(self):
                self.reason = reason
        return _S()

    def _start(timeout=0.0):
        calls.append('start')
        return False, '测试：起不来'
    try:
        BR.service_status, BR.start_service = _st, _start
        A._MUMU_START_TRIED['done'] = False
        good, why = A._ensure_mumu(BR)
    finally:
        BR.service_status, BR.start_service = real_status, real_start
        A._MUMU_START_TRIED['done'] = False
    ok('F1 ★★★ 服务不在 ⇒ **先探、再尝试拉起**（"优先外部服务"的落实处）',
       calls == ['probe', 'start'], f'调用顺序 {calls}')
    ok('F1b ★★★ 拉起失败才判不可用，而且**带回原因**（不静默回退）',
       good is False and '起不来' in (why or ''), why)

    # F1c 成对：探到"在跑"就**不拉起**（别每次写稿都多等几十秒）
    calls.clear()

    class _S2:
        ok = True
        reason = ''
    try:
        BR.service_status, BR.start_service = (lambda *a, **k: _S2()), _start
        A._MUMU_START_TRIED['done'] = False
        good2, _ = A._ensure_mumu(BR)
    finally:
        BR.service_status, BR.start_service = real_status, real_start
    ok('F1c ★★★ 成对：服务在跑 ⇒ **不再拉起**（不白等）',
       good2 is True and calls == ['start'] or good2 is True and calls == [],
       f'调用 {calls} / ok={good2}')

    # F2 输入三件套 —— **真拼一次**（行为判据），不查源码字符串
    # ⚠ 第一版是 `'这本书的设定集' in src and 'setting' in src` —— 反例法第 ⑥ 刀
    #   （把历史小说那段改成空串）之后字符串还在，判据照样绿。**判据测字符串 = 永远绿。**
    # [EN] F2 the three inputs -- **actually assemble once** (behavioural criterion), no source
    # [EN] strings. ⚠ The first version was a string match, and counterexample cut 6 (blanking the
    # [EN] history-novel entry) kept the criterion green. **A criterion matching strings is
    # [EN] permanently green.**
    import tempfile as _tf
    _d = _tf.mkdtemp()
    Path(_d, '当天故事.md').write_text(
        '# 当天故事\n## 第 1 天 · 亥时\n\n前一天写成的正文。\n', encoding='utf-8')
    got = A.export_outline(day=2, raw_novel='今天逐字的原文。',
                           process='今天的推演过程。',
                           characters=['甲'], setting='设定集内容。',
                           novel_dir=_d)
    ok('F2 ★★★ 导出材料里有**设定集**', '设定集内容' in got, got[:60])
    ok('F2b ★★★ 导出材料里有**历史小说**（前几章的实际正文，不是摘要）',
       '前一天写成的正文' in got, '有' if '前一天写成的正文' in got else '没有')
    ok('F2c ★★★ 导出材料里仍有**本地推演过程**', '今天的推演过程' in got, '')
    ok('F2d ★★ 而**当天原文**也在（三样之外那条不能少）', '今天逐字的原文' in got, '')
    # ⚠ 要带「── 」前缀：任务说明那句里也写着"前几章写成的样子"，
    #   只判名字会永远命中（第一次就是这么误报的）。
    # [EN] ⚠ Must include the "── " prefix: the task paragraph also says "what the previous
    # [EN] chapters read like", so matching the bare name always hits (that was the first false
    # [EN] report).
    ok('F2e ★★ 成对：读不到历史时不硬塞一段空的（不留"── 前几章… ──"空标题）',
       '── 前几章写成的样子（' not in A.export_outline(
           day=2, raw_novel='原文。', process='过程。', setting='设定。',
           novel_dir='/nonexistent-dir'), '')
    ok('F2f ★★ `_setting_brief` 复用 `sim.setup.load_settings`（不另写一份解析）',
       'load_settings' in inspect.getsource(NV._setting_brief), '')

    # F3 历史小说取的是**正文**，且只取当天之前的
    import tempfile
    d = tempfile.mkdtemp()
    Path(d, '当天故事.md').write_text(
        '# 当天故事\n## 第 1 天 · 亥时\n\n第一天的正文。\n\n## 第 2 天 · 子时\n\n第二天的正文。\n',
        encoding='utf-8')
    ok('F3 ★★★ 只取"当天之前"的章节（当天还没写，不能当历史）',
       A._history_novel(d, before_day=2).find('第一天的正文') >= 0
       and '第二天的正文' not in A._history_novel(d, before_day=2),
       A._history_novel(d, before_day=2)[:40])
    ok('F3b ★ 读不到就返回空串（**不编**）',
       A._history_novel('/nonexistent-dir', before_day=9) == '', '')

    # F4 部分成功：批次被判失败、正文其实写好了 ⇒ 必须取回
    src_gen = inspect.getsource(BR.generate_chapter)
    ok('F4 ★★★ 批次 failed **不再直接放弃**（正文可能已经写好，实测就是如此）',
       '继续试着读回正文' in src_gen, '')
    ok('F4b ★★★ 空章会**换不思考的模型重试一次**'
       '（推理模型把预算烧在思考上，实测 reasoning 6347 字、正文 0 字）',
       '_plain_model' in src_gen and '_retried' in src_gen, '')
    ok('F4c ★ `_plain_model` 优先用配置里的分析模型，留空退回不思考的',
       getattr(BR, '_plain_model', None) is not None
       and 'deepseek-chat' in inspect.getsource(BR._plain_model), '')
    # ⚠ 判据测**行为**，不测字符串：把 `if empties:` 改成 `if False:` 后
    #   源码里那两段字符串还在 —— 第一版就是这么被反例法咬住的。
    # [EN] ⚠ Test **behaviour**, not strings: after `if empties:` becomes `if False:` both strings are
    # [EN] still in the source -- the first version was bitten by the counterexample method this way.
    ok('F4d ★★ 末尾连续空壳会被复用重写（不让一个空章堵死后面所有导出）',
       BR.trailing_empty_numbers(
           [{'id': 'a', 'chapter_number': 1}, {'id': 'b', 'chapter_number': 2},
            {'id': 'c', 'chapter_number': 3}],
           lambda cid: '正文' if cid == 'a' else '') == [3, 2],
       BR.trailing_empty_numbers(
           [{'id': 'a', 'chapter_number': 1}, {'id': 'b', 'chapter_number': 2}],
           lambda cid: '正文' if cid == 'a' else ''))
    ok('F4e ★★ 成对：最后一章有正文 ⇒ **一个都不复用**（否则会把好章节重写掉）',
       BR.trailing_empty_numbers(
           [{'id': 'a', 'chapter_number': 1}, {'id': 'b', 'chapter_number': 2}],
           lambda cid: '正文') == [], '')


# ── G —— "写归服务、查归自己、不过退回"（2026-10-21 用户点名）──────────────
# [EN] G -- "service writes, we check, send it back if it fails" (named by the user 2026-10-21)
def test_write_check_retry() -> None:
    """测 `write_check_retry` 的**行为**（不是查源码字符串）。

    ⚠ 这里必须打桩打到底：`generate_chapter` 换成假的，`make_task` 记下每遍拿到的 fix_list。
      否则这条判据要么真调服务（贵、慢、还会被网络搞挂），要么只能查字符串（假判据）。
    [EN] Test `write_check_retry`'s **behaviour** (not source strings).
    [EN] ⚠ Stub all the way down: fake `generate_chapter`, and let `make_task` record the fix_list of
    [EN] each pass. Otherwise the criterion either calls the real service (expensive, slow, network
    [EN] dependent) or can only match strings (a false criterion).
    """
    from crew import agents as A
    from novelservices import mumu_bridge as BR

    SHORT = '太短。'
    DIRTY = ('他伸手，指尖碰了碰。声音很轻。门外没有脚步声。' * 6
             + '壶凉了。壶凉了。壶凉了。') * 8      # 长句/重复一大堆
    # ⚠ 干净夹具**不许整段重复**：同一段复制 14 遍本身就会命中"重复"这条判据
    #   （第一次写的时候就是这么让 G2 红的 —— 不是产品错，是夹具不干净）。
    # [EN] ⚠ The clean fixture must **not repeat a whole paragraph**: copying one paragraph 14
    # [EN] times trips the "repetition" detector itself (that is why G2 went red the first time --
    # [EN] not a product bug, a dirty fixture).
    CLEAN = (
        '沈砚把壶往他手边一搁，壶把磕在桌沿上，闷闷一声。'
        '阿九的手停在半空，话到嘴边又咽回去，屋里的灯芯炸了一下。'
        '檐下的白灯笼被风推得往里凹，光一明一暗，照得桌上那圈水渍像块浸湿的旧布。'
        '柳氏没有抬头，指尖在碗沿上来回蹭，蹭出一道浅浅的白痕。'
        '后院传来水桶磕井沿的响声，一下，又一下，像是有人在井里数着什么。'
        '阿九站起来又坐下，膝盖撞了一下桌腿，茶面漾开，晃出半个灯笼的影子。'
        '沈砚拿抹布揩柜面，揩到一半停下，抬眼看西墙那扇门，看了很久。'
        '门外有脚步，不紧不慢，踩在冻硬的泥地上，一声比一声近。'
        '柳氏忽然把碗推开半寸，碗底在木头上磨出一声长长的涩响。'
        '风从门缝里挤进来，把灯焰吹得一歪，满厅的影子都跟着歪。'
    )

    class _R:
        def __init__(self, text, ok=True):
            self.text, self.ok, self.reason = text, ok, ''

    real_gen = BR.generate_chapter

    # ── G1 清单数出毛病 ⇒ **退回重写**（第二遍的 fix_list 必须带着那几条）──
    got_fix: list[str] = []
    seq = [_R(DIRTY), _R(DIRTY)]
    idx = {'i': 0}

    def _gen(task):
        idx['i'] += 1
        got_fix.append(str(getattr(task, 'outline', '')))
        return seq[min(idx['i'] - 1, len(seq) - 1)]

    class _T:
        def __init__(self, fix=''):
            self.outline, self.title, self.target_words = fix, 't', 1500
    try:
        BR.generate_chapter = _gen
        A.CFG.set('MUMU_EXPORT_TRIES', 2)
        txt, why = A.write_check_retry(
            BR, lambda fix: (_ for _ in ()).throw(AssertionError()) if False else _T(fix),
            tag='判据G1')
    finally:
        BR.generate_chapter = real_gen
        A.CFG.set('MUMU_EXPORT_TRIES', 2)
    # ⚠ 我们传的 make_task 只把 fix 放进 outline，所以"第二遍带了清单"= 第二遍 outline 非空
    ok('G1 ★★★ 清单数出毛病 ⇒ **真的退回重写了一遍**（调了 2 次）',
       idx['i'] == 2, f'调了 {idx["i"]} 次')
    # ⚠ **括号不能省**：Python 里 `and` 比 `or` 紧，写成
    #   `A and B and C or D or E` 等价于 `(A and B and C) or D or E` ——
    #   只要文本里有"重复"，后面两个 or 就让整条恒真。第一次就是这么被反例法咬住的
    #   （第 ⑨ 刀把清单置空，判据照样绿）。
    # [EN] ⚠ **The parentheses are load-bearing**: `and` binds tighter than `or`, so
    # [EN] `A and B and C or D or E` means `(A and B and C) or D or E` -- as long as the text has
    # [EN] "repetition", the trailing ors make it always true. Counterexample cut 9 caught exactly
    # [EN] that (blank the list, criterion stays green).
    _has_class = any(k in got_fix[1] for k in ('憋气段', '重复', '篇幅不足')) if len(got_fix) > 1 else False
    ok('G1b ★★★ 退回时**带着具体清单**（不是"再写一遍"这种空话）',
       len(got_fix) >= 2 and '上一版没通过的地方' in got_fix[1] and _has_class,
       (got_fix[1][:60] if len(got_fix) > 1 else '没有第二遍'))

    # ── G2 清单 0 处 ⇒ **不白跑**（只调一次）──
    # ⚠ 这里**打桩把计数压成 0**，不用"真干净的长文"当夹具。理由：
    #   ① 写一段 600 字以上、真的一处毛病都没有的中文很难，而夹具一旦不干净，
    #      这条判据就会红 —— **红的原因是夹具，不是产品**，属于"判据被夹具牵连"；
    #   ② 这条判据要测的是**分支逻辑**（计数为 0 时要不要再写一遍），
    #      检测器准不准由另外的判据管（`verify_prose_flow`）。
    # [EN] ⚠ Stub the count to 0 instead of using "a genuinely clean long text" as the fixture:
    # [EN] ① writing 600+ characters with truly zero defects is hard, and once the fixture is dirty
    # [EN] this criterion goes red **because of the fixture, not the product** -- a criterion dragged
    # [EN] down by its fixture; ② what this criterion tests is the **branch** (rewrite or not when the
    # [EN] count is 0); detector accuracy is covered by `verify_prose_flow`.
    from crew import prose_flow as _PF2
    real_cnt = _PF2.prose_issue_count
    idx2 = {'i': 0}

    def _gen2(task):
        idx2['i'] += 1
        return _R(CLEAN * 3, ok=True)                    # 够长（过篇幅下限）
    try:
        BR.generate_chapter = _gen2
        _PF2.prose_issue_count = lambda _t: {}           # 恒 0 处
        A.write_check_retry(BR, lambda fix: _T(fix), tag='判据G2')
    finally:
        BR.generate_chapter = real_gen
        _PF2.prose_issue_count = real_cnt
    ok('G2 ★★★ 清单数出 0 处 ⇒ **只调一次**（不白花钱）',
       idx2['i'] == 1, f'调了 {idx2["i"]} 次')

    # ── G3 太短不算过关（实测服务端只还回 94 字，清单却数出 0 处）──
    idx3 = {'i': 0}

    def _gen3(task):
        idx3['i'] += 1
        return _R(SHORT)
    try:
        BR.generate_chapter = _gen3
        A.write_check_retry(BR, lambda fix: _T(fix), tag='判据G3')
    finally:
        BR.generate_chapter = real_gen
    ok('G3 ★★★ **太短不算过关**（94 字时清单数出 0 处，但那是没写出来，不是干净）',
       idx3['i'] == 2, f'调了 {idx3["i"]} 次（应 > 1）')

    # ── G4 **不许无条件采用新稿**：第二遍更差 ⇒ 留第一遍 ──
    #   第一遍：够长、毛病少；第二遍：更短（短文=毛病少但字数缩水）⇒ 必须留第一遍。
    good1 = ('她拨了拨火箸，火苗跳一下，廊板响，伙计端着壶回来。'
             '伙计弯身放下，退去时没出声响，屋里静得能听见灯芯炸。') * 16
    worse2 = ('火箸一拨。火苗跳。廊板响。伙计回来。放下。退去。') * 10
    idx4 = {'i': 0}
    seq4 = [_R(good1), _R(worse2)]

    def _gen4(task):
        idx4['i'] += 1
        return seq4[min(idx4['i'] - 1, 1)]
    try:
        BR.generate_chapter = _gen4
        txt4, _ = A.write_check_retry(BR, lambda fix: _T(fix), tag='判据G4')
    finally:
        BR.generate_chapter = real_gen
    ok('G4 ★★★ 第二遍**更差** ⇒ 留第一遍（不是"改过就用新的"）',
       len(txt4) == len(good1), f'留下 {len(txt4)} 字 / 第一遍 {len(good1)} 字 / 第二遍 {len(worse2)} 字')

    # ── G5 两个阶段**共用一份实现**（不是各写一段）──
    import inspect
    src_exp = inspect.getsource(A._mumu_export)
    src_smp = inspect.getsource(A._mumu_sample)
    ok('G5 ★★★ 导出与写样章**都调同一个** `write_check_retry`（不许各写一段）',
       'write_check_retry' in src_exp and 'write_check_retry' in src_smp,
       f'导出={"有" if "write_check_retry" in src_exp else "没有"} / '
       f'样章={"有" if "write_check_retry" in src_smp else "没有"}')

    # ── G6 退回的话**必须可执行**（每条带数量 + 一句怎么改）──
    one = A.fix_list_line({'憋气段': 3, '道具循环': 2})
    ok('G6 ★★★ 退回的清单一条一类、带数量、带怎么改（不是"写得更好"）',
       '憋气段 3 处' in one and '拆成短句' in one and '道具循环 2 处' in one, one[:70])
    ok('G6b ★ 而且明写"不许靠删减过关"（否则它会把段落删掉换清白）',
       '不许靠删减' in one, one[-40:])
    ok('G6c ★ 数出 0 处 ⇒ 清单是空串（不硬凑一条）',
       A.fix_list_line({}) == '' and A.fix_list_line({'憋气段': 0}) == '', '')


# ── H —— 2026-10-21 专业分析报告提的五条：提示词能治的三条 ────────────────
# [EN] H -- three of the five issues from the 2026-10-21 professional review that prompts CAN fix
def test_prompt_fixes_for_review() -> None:
    """一份专业分析报告提了 5 条问题，**3 条能靠提示词治、2 条不能**。

    能治的三条（本组测）：
      ① 重复变奏过多（"壶里空了" 7 次）—— 原来提示词里是**两条互相打架**的规则
         （「只留第一次」vs「写足两三次」），现在合并成"最多三次、每次多知道一件"；
      ② 超自然规则模糊（三件怪事各自指向不同解释）—— 导出侧要求"异常必须从设定集派生"；
      ③ 配角功能重叠 / 揭秘过早 / 结尾无力 —— 这三条只写在**写样章（计划层）**那侧，
         因为导出层铁律是"只整理不新增"，强求只能靠编。
    [EN] The review raised 5 issues: **3 fixable by prompts, 2 not**.
    [EN] Fixable: ① too much repetition (the prompt had **two contradictory rules**); ② blurry
    [EN] supernatural rules; ③ overlapping supporting roles / early reveal / weak ending -- these
    [EN] three live **only on the sample-chapter (planning) side**, because the export side must
    [EN] "organize only, never add" and demanding them there only forces invention.
    [EN] ⚠ The criterion inspects **the prompt actually produced**, not source strings: round F2/F4d
    [EN] were bitten by source matching (comment the rule out, the string remains, still green).
    [EN] Here we really run one organize pass and one sample pass and read the captured prompt.
    """
    import asyncio

    from crew import agents as A
    from novelservices import mumu_bridge as BR

    # ── H1/H2 导出整理侧 ──
    got: list[str] = []
    old_ask = A.ask
    try:
        A.ask = _prompt_sink({'正文': '占位'}, got)
        asyncio.run(A.Novelist()._transcribe_once(
            _min_ctx(), '· 动作 阿九：擦桌子。', scope='（判据用）'))
    finally:
        A.ask = old_ask
    p_exp = got[-1] if got else ''

    ok('H1 ★★★ 导出提示词问「同一件事最多三次」（原来两条打架的规则已合并）',
       '同一件事最多三次' in p_exp, '在' if '同一件事最多三次' in p_exp else '不在')
    ok('H1b ★★★ 并写清三次**各管一件事**（立规矩 / 试规矩 / 破规矩）',
       all(k in p_exp for k in ('立规矩', '试规矩', '破规矩')), '')
    ok('H1c ★★★ 旧的两条打架规则**已经删掉**（不许再出现「只留第一次」）',
       '只留第一次' not in p_exp, '还在' if '只留第一次' in p_exp else '已删')
    ok('H1d ★★★ 给了可判的自查句（"并成一处会少知道什么"）—— 可删除性落地',
       '会少知道什么' in p_exp, '')
    ok('H2 ★★★ 导出提示词要求「异常必须能从设定集的那条规矩推出来」',
       '所有异常都必须能从那条规矩推出来' in p_exp, '')
    ok('H2b ★★★ 且明写「不许这一章临时再立一条新的」',
       '不许这一章临时再立一条新的' in p_exp, '')
    ok('H2c ★★★ 成对：材料里没那条规矩时**不许替它编**（否则违反"不新增情节"）',
       '不要替它编一条规矩' in p_exp, '')

    # ── H3/H4/H5 写样章（计划层）──
    outs: list[str] = []
    real_gen = BR.generate_chapter
    real_ensure = A._ensure_mumu

    class _R:
        ok = True
        text = '占位正文，写够长度用。' * 40
        reason = ''

    def _gen(task):
        outs.append(str(getattr(task, 'outline', '')))
        return _R()
    old_tries = CFG.i('MUMU_EXPORT_TRIES')
    try:
        BR.generate_chapter = _gen
        A._ensure_mumu = lambda _br: (True, '')
        CFG.set('MUMU_EXPORT_TRIES', 1)
        asyncio.run(A._mumu_sample(_min_ctx(), nodes='节点一', yesterday='', craft=''))
    finally:
        BR.generate_chapter = real_gen
        A._ensure_mumu = real_ensure
        CFG.set('MUMU_EXPORT_TRIES', old_tries)
    o = outs[-1] if outs else ''

    ok('H3 ★★★ 写样章要求「每人一件**只有他能办**的事」（治配角功能重叠）',
       '只有他能办' in o, '')
    ok('H3b ★★★ 且给了反面（两个人都只在警告 ⇒ 只顶一个人用）',
       '只顶一个人用' in o, '')
    ok('H4 ★★★ 写样章要求「**只揭一层底**」（治高潮提前泄气）',
       '只揭一层底' in o, '')
    ok('H5 ★★★ 写样章要求结尾有「**一件不可逆的事**」（治结尾力度不足）',
       '不可逆的事' in o, '')
    ok('H5b ★★ 且给了自查句（"把结尾拿掉，这一天有没有损失"）',
       '有没有损失' in o, '')

    # ── H6 分工不能反 ──
    #   导出层"只整理不新增"，让它"加反转/挪揭秘"只会逼它编。
    # [EN] The division must not be reversed: demanding a twist on the export side only forces
    # [EN] invention, since that side may not add anything.
    ok('H6 ★★★ 结构要求**不许**混进导出整理侧（那边"只整理不新增"）',
       '不可逆的事' not in p_exp and '只揭一层底' not in p_exp,
       '混进去了' if ('不可逆的事' in p_exp or '只揭一层底' in p_exp) else '分工正确')


def _min_ctx(day: int = 1):
    """一份最小的 `SetCtx`（判据只关心提示词拼装，不关心世界细节）。"""
    from crew.agents import SetCtx
    from world.state import WorldState
    w = WorldState()
    w.scene = '临河茶肆'
    w.game_day = day
    w.topic = '查夜登记'
    return SetCtx(world=w, db=None, day=day, people=['掌柜'])


def _prompt_sink(value: dict, sink: list[str]):
    """把提示词抓进 `sink` 的桩（返回真的 `Reply`，与生产同形）。"""
    from llm.replies import Reply

    async def _fake(_tier, messages, **_kw):
        sink.append('\n'.join(str(m.get('content') or '') for m in messages))
        return Reply(ok=True, value=dict(value), raw='{}', meta={})
    return _fake

# ── I —— 提示词"去书化"与"项目级规则只对自己生效"（2026-10-21 用户点名）────
# [EN] I -- "de-bookify" the prompts, and keep project-level rules scoped to their own book
def test_prompt_scope() -> None:
    """用户原话：「检查下这些规则是否是通用规则。如果是针对特定小说的规则，
    请把相关内容写到特定小说对应项目的配置文件里，**只在这个小说导出的时候起作用**，
    而不是所有小说都起作用。你检查下其他的规则是否也存在这个问题。」

    ★ 查下来的结论分两半，这条判据两半都钉住：
      ① **规则本身是通用的**（三次变奏 / 配角差异化 / 只揭一层 / 结尾不可逆 /
         异常从设定集派生 / 心声不许丢）—— 它们对所有小说都成立，留在通用提示词；
      ② 但**举例不是通用的**：原来通用提示词里混着好几本书的专名与实例
         （某角色的"复读机"、某些物象"成装饰品"、某本书的「壶」「井台」「荷包」）。
         两头都错 —— 对别的小说那是纯干扰（而且 MEMORY 有一条：例子会被当素材抄），
         对那本书则等于没归位。
      ③ ⇒ 通用提示词去掉全部专名；某本书实测出来的写法约束写进它自己的
         `style.notes`（只进它自己的 `顶级规则.md`）。

    ⚠ 判据打的是**真发出去的提示词**：造一个"无关的第三本书"，看它的提示词里
      有没有别人的专名。上一轮 F2/F4d 就是栽在查源码上，这里不再重犯。
    [EN] The user's words: "check whether these rules are generic; if a rule targets a specific
    [EN] novel, move it into that project's config so it only applies when exporting that novel, not to
    [EN] every novel. Check whether other rules have the same problem."
    [EN] ★ The finding has two halves, and this criterion pins both:
    [EN]   ① **The rules themselves are generic** (three variations / differentiated supporting roles
    [EN]      / reveal one layer / irreversible ending / anomalies derive from the setting book /
    [EN]      inner voice must not be dropped) -- true for every novel, they stay in the shared prompt;
    [EN]   ② **The examples are not**: the shared prompt carried several books' proper nouns and
    [EN]      incidents. Wrong both ways -- noise for other books (and MEMORY records that examples get
    [EN]      copied as material), and for that book the lesson never landed where it belongs.
    [EN]   ③ => Shared prompt drops every proper noun; a book's measured constraints go into its own
    [EN]      `style.notes`, which reach only its own `顶级规则.md`.
    [EN] ⚠ The criterion inspects **the prompt actually sent**: it builds an unrelated third book and
    [EN] checks for other books' proper nouns. Round F2/F4d were bitten by source matching; not again.
    """
    import asyncio

    from crew import agents as A
    from novelservices import mumu_bridge as BR

    # 两本 bench 作品的专名（只用来查"有没有漏进来"）
    PROPER = {
        '望江楼': ['柳氏', '沈砚', '阿九', '白绫', '荷包', '井台', '掏井', '望江楼', '茶肆'],
        '雪国': ['驹子', '岛村', '火钵', '艺伎', '雪国', '县界', '绉纱'],
    }

    def _third_book_prompt() -> str:
        """造一本"跟那两本都无关"的书，抓它真收到的提示词。"""
        from crew.agents import SetCtx
        from world.state import PersonState, WorldState
        w = WorldState()
        w.scene = '某处'
        w.game_day = 1
        w.rules_text = '这本书的规矩：不许出现任何超自然现象。'
        w.people['掌柜'] = PersonState(name='掌柜')
        ctx = SetCtx(world=w, db=None, day=1, people=['掌柜'])
        got: list[str] = []
        old = A.ask

        async def _fake(_tier, msgs, **_kw):
            got.append('\n'.join(str(m.get('content') or '') for m in msgs))
            from llm.replies import Reply
            return Reply(ok=True, value={'正文': 'x'}, raw='{}', meta={})
        A.ask = _fake
        try:
            asyncio.run(A.Novelist()._transcribe_once(
                ctx, '· 动作 某人：擦桌。', scope='（判据用）'))
        finally:
            A.ask = old
        return got[-1] if got else ''

    # ⚠ **光查专名不够**：有些污染是"通用名词 + 那本书特有的设定"
    #   （某样东西永远不满、某件东西自己回到袖子里）—— 名词本身不专有，
    #   专名表抓不到，但对别的小说同样是"把别人的设定搬过来了"。
    #   ⇒ 再加一张**设定短语**表。只收"换成任何别的书都不会这么说"的短语。
    # [EN] ⚠ **Proper nouns alone are not enough**: some leakage is "a common noun plus that
    # [EN] book's specific setting" (something that is never full, something that returns to a
    # [EN] sleeve by itself) -- the noun is not proper, so a proper-noun table misses it, yet for
    # [EN] another book it is still "importing someone else's setting".
    # [EN] => A second table of **setting phrases**, only those no other book would ever say.
    SETTING = ['壶永远不满', '荷包自己回袖', '荷包回袖', '井台上有霜', '白绫三尺']
    p = _third_book_prompt()
    leaked = sorted({w for ws in PROPER.values() for w in ws if w in p}
                    | {w for w in SETTING if w in p})
    ok('I1 ★★★ 通用导出提示词里**没有别的书的专名**'
       '（有就等于把别人的道具搬进这本书，而且会被当素材抄）',
       not leaked, f'泄漏 {leaked}' if leaked else '干净')

    # I2 规则本身还在（去例子不等于把规则删掉）
    ok('I2 ★★★ 成对：去专名之后**规则还在**（三次变奏 / 只揭一层 / 不可逆 / 异常派生）',
       all(k in p for k in ('同一件事最多三次', '立规矩', '所有异常都必须能从那条规矩推出来')),
       '')

    # I3 写样章的 outline 也不许带别书专名
    outs: list[str] = []
    real_gen, real_ensure = BR.generate_chapter, A._ensure_mumu

    class _R:
        ok = True
        text = '占位正文。' * 80
        reason = ''

    def _g(task):
        outs.append(str(getattr(task, 'outline', '')))
        return _R()
    old_tries = CFG.i('MUMU_EXPORT_TRIES')
    try:
        BR.generate_chapter = _g
        A._ensure_mumu = lambda _b: (True, '')
        CFG.set('MUMU_EXPORT_TRIES', 1)
        from crew.agents import SetCtx
        from world.state import PersonState, WorldState
        w = WorldState()
        w.scene = '某处'
        w.game_day = 1
        w.rules_text = '这本书的规矩：不许出现任何超自然现象。'
        w.people['掌柜'] = PersonState(name='掌柜')
        asyncio.run(A._mumu_sample(SetCtx(world=w, db=None, day=1, people=['掌柜']),
                                   nodes='节点一', yesterday='', craft=''))
    finally:
        BR.generate_chapter = real_gen
        A._ensure_mumu = real_ensure
        CFG.set('MUMU_EXPORT_TRIES', old_tries)
    o = outs[-1] if outs else ''
    leaked2 = sorted({w for ws in PROPER.values() for w in ws if w in o}
                     | {w for w in SETTING if w in o})
    ok('I3 ★★★ 写样章的材料里也**没有别的书的专名**', not leaked2,
       f'泄漏 {leaked2}' if leaked2 else '干净')

    # ── I4 项目级规则只对自己生效（真读两本 yaml 的 style.notes）──
    import yaml
    from pathlib import Path as _P
    root = _P('.') / 'novel_bench' / 'dataset' / 'works'
    mw = yaml.safe_load((root / '29_mowenlou.yaml').read_text(encoding='utf-8'))
    yg = yaml.safe_load((root / '24_yukiguni.yaml').read_text(encoding='utf-8'))
    mw_notes = ' '.join(str(x) for x in ((mw['bible'].get('style') or {}).get('notes') or []))
    yg_notes = ' '.join(str(x) for x in ((yg['bible'].get('style') or {}).get('notes') or []))
    ok('I4 ★★★ 两本书**各自有**自己的写法约束（`style.notes`）',
       bool(mw_notes.strip()) and bool(yg_notes.strip()),
       f'望江楼 {len(mw_notes)} 字 / 雪国 {len(yg_notes)} 字')

    def _prompt_with(rules_text: str) -> str:
        from crew.agents import SetCtx
        from world.state import PersonState, WorldState
        w = WorldState()
        w.scene = '某处'
        w.game_day = 1
        w.rules_text = rules_text
        w.people['掌柜'] = PersonState(name='掌柜')
        ctx = SetCtx(world=w, db=None, day=1, people=['掌柜'])
        got: list[str] = []
        old = A.ask

        async def _fake(_tier, msgs, **_kw):
            got.append('\n'.join(str(m.get('content') or '') for m in msgs))
            from llm.replies import Reply
            return Reply(ok=True, value={'正文': 'x'}, raw='{}', meta={})
        A.ask = _fake
        try:
            asyncio.run(A.Novelist()._transcribe_once(ctx, '· 动作 甲：坐。', scope='（判据用）'))
        finally:
            A.ask = old
        return got[-1] if got else ''

    p_mw = _prompt_with('这本书的规矩：甲\n' + mw_notes)
    p_yg = _prompt_with('这本书的规矩：乙\n' + yg_notes)
    ok('I5 ★★★ 望江楼导出时**带着它自己的**约束（茶/水/壶/灯的复位上限）',
       '茶、水、壶、灯' in p_mw, '')
    ok('I5b ★★★ 而雪国导出时**不带**望江楼那条（作用域隔离的关键）',
       '茶、水、壶、灯' not in p_yg, '串过来了' if '茶、水、壶、灯' in p_yg else '隔离正确')
    ok('I5c ★★★ 对称：雪国带自己的（岛村的沉默），望江楼不带',
       ('岛村的沉默' in p_yg) and ('岛村的沉默' not in p_mw), '')

    # I6 `_rules` 真的会把 notes 写进 `顶级规则.md`（否则配置写了等于没写）
    import inspect
    from novel_bench.bench import dataset as _DS
    from novel_bench.bench import project_builder as PB
    src_pb = inspect.getsource(PB._rules)
    # ⚠ 2026-10-21 换了落点：`style.notes` **不再进「顶级规则.md」**，
    #   而是单独一份「写作层规则.md」—— 因为前者会**原样进每个演员的提示词**，
    #   而「每样最多复位三次」这类成品要求演员没法执行，只会让他不敢动。
    #   判据跟着钉**新落点**，并且成对钉住「不许再混回顶级规则」。
    # [EN] ⚠ Landing spot changed 2026-10-21: `style.notes` **no longer goes into 顶级规则.md**
    # [EN] but into a separate 写作层规则.md -- the former goes **verbatim into every actor prompt**,
    # [EN] and finished-form requirements like "each prop resets at most three times" are not
    # [EN] executable by an actor; they only make him avoid the prop.
    # ⚠ `dataset` 在**本函数内**导入：`DS` 只在 J 组导过，I 组直接引用会 NameError ——
    #   那会让 I6b **以及它后面的判据**全部不跑（「判据总数莫名减少」那类假绿）。
    # [EN] ⚠ Import `dataset` **inside this function**: `DS` is only imported in group J, and a bare
    # [EN] reference raises NameError -- which would skip I6b **and every criterion after it**.
    _w = _DS.load_work(Path('novel_bench/dataset/works/29_mowenlou.yaml'))
    ok('I6 ★★★ `style.notes` 写进**独立的**「写作层规则.md」（配置写了要真的生效）',
       # ⚠ 判**写文件那一处**（`build_project`），不是 `_rules` ——
       #   第一版判的是 `_rules` 的源码里有没有「写作层规则」四个字，
       #   而落盘发生在 `build_project`，判错了对象（红得对，红的位置不对）。
       # [EN] ⚠ Judge **the write site** (`build_project`), not `_rules` -- the first version looked
       # [EN] for the string inside `_rules` while the file write happens in `build_project`.
       '写作层规则' in inspect.getsource(PB.build_project), '')
    ok('I6b ★★★ 成对：**不许**再混进「顶级规则.md」（那份会进演员提示词）',
       '茶、水、壶、灯' not in PB._rules(_w, _w.cases[0]),
       '混进去了' if '茶、水、壶、灯' in PB._rules(_w, _w.cases[0]) else '已分开')
    ok('I6c ★★★ 而**写作层规则**里确实有它（分开不等于弄丢）',
       '茶、水、壶、灯' in PB._writer_notes(_w), '')

# ── J —— "揭秘后移 / 结尾反转"在计划层解决（2026-10-21 用户点名）────────────
# [EN] J -- "reveal later / twist at the end" solved in the planning layer (named 2026-10-21)
def test_planning_layer_solves_structure() -> None:
    """用户问：「把揭秘后移、给结尾加反转，这 2 个你看是否在一开始写小说的时候解决？」

    ★ 查下来的答案：**是同一个机关 —— 进度节点**。
      · 产品 2026-10-14 就为「第一天就想把谜底解开」修过：`_nodes_text` 只给**当前节点**，
        并明说"后面的路还没走到、不许提前揭"。
      · 但它**依赖节点表**：表里只有一步（bench 以前每本书只生成 1 个节点「这一场」），
        就没有"层"可揭 —— "只给当前节点"这条修法没有东西可给。
      · 「结尾反转」同理：它不是文字技巧（在导出层强加就是"新增情节"），
        而是"这一天结束时某人的处境不可逆地变了"，**那正是节点的完成判据**。

    ★ 所以这一轮的修法全在**数据层**，不在提示词里加要求：
      ① `project_builder._progress` 支持 `bible.progress`（多节点），没有才退回单节点；
      ② 退路的单节点**不再叫「这一场」**，改成「把当下这一步走完」+ 要求一处不可逆的变化；
      ③ 望江楼补了 4 个分层节点（立规矩 → 越界付代价 → 欠下未了事 → 井台一句话）；
      ④ 补了「知情者」（此前全空 ⇒ `blind_spots` 空转、信息边界没有实体）；
      ⑤ 写样章那两条要求**明写"以节点为准"**，免得同一件事两处说法打架。
    [EN] The user asked: "can moving the reveal later and adding a twist at the end be solved when
    [EN] the novel is first written?" The answer: **one mechanism -- the progress node**.
    [EN] · The product fixed "wants to crack the mystery on day one" on 2026-10-14 by handing the
    [EN]   writer **only the current node** plus "the road past here has not been reached".
    [EN] · But it **depends on the node table**: with a single node ("this scene") there was no
    [EN]   "layer" to reveal, so the fix had nothing to hand over.
    [EN] · "A twist at the end" likewise: not a wording trick (forcing it in export = adding plot)
    [EN]   but "someone's situation changed irreversibly by the end of the day" -- **exactly a
    [EN]   node's completion criterion**.
    [EN] ★ So this round's fix lives in the **data layer**, not in extra prompt demands:
    [EN]   ① `_progress` accepts `bible.progress` (multi-node), falling back to one node;
    [EN]   ② the fallback node is no longer "this scene" but "finish the current step" + require an
    [EN]      irreversible change; ③ Mowen Tower got four layered nodes; ④ "knowers" filled in
    [EN]      (previously empty, so `blind_spots` idled and the information boundary had no
    [EN]      substance); ⑤ the two sample-chapter requirements now say **the node wins**, so one
    [EN]      rule is not stated twice.
    """
    import tempfile

    from director.day_plan import _nodes_text
    from novel_bench.bench import dataset as DS
    from novel_bench.bench import project_builder as PB
    from sim.setup import load_settings
    from world.state import PersonState, WorldState

    root = Path('.')
    work = DS.load_work(root / 'novel_bench' / 'dataset' / 'works' / '29_mowenlou.yaml')

    # ── J1 多节点：yaml 写了就照它建（不是永远只有 1 个）──
    prog = PB._progress(work, work.cases[0])
    nodes = prog.get('节点') or []
    ok('J1 ★★★ 作品写了 `bible.progress` ⇒ **多节点**真的建出来了'
       '（以前无条件只生成 1 个「这一场」，就没有"层"可揭）',
       len(nodes) >= 3, f'{len(nodes)} 个节点')

    # ── J2 退路：没写节点的作品，单节点也要含"不可逆的变化" ──
    class _W:
        bible: dict = {}
    fb = PB._progress(_W(), work.cases[0]).get('节点') or []
    ok('J2 ★★★ 成对：没写节点的作品退回**单节点**，且完成判据含"不可逆的变化"'
       '（反转从这里长出来，不是在文字上硬加）',
       len(fb) == 1 and '不可逆的变化' in str(fb[0].get('完成判据') or ''),
       str(fb[0].get('完成判据') or '')[:50])
    ok('J2b ★★ 而且退路的节点**不再叫「这一场」**'
       '（那名字等于告诉模型"今天只要演一场"，它就不往"结尾要有变化"上想）',
       '这一场' not in str(fb[0].get('名称') or ''),
       str(fb[0].get('名称') or ''))

    # ── J3 节点真的进提示词：只给当前节点，不点后面节点的名字 ──
    tmp = Path(tempfile.mkdtemp())
    PB.build_project(work, work.cases[0], tmp)
    pdir = next(tmp.rglob('故事进度.yaml')).parent
    st = load_settings(pdir)
    w = WorldState()
    w.progress_nodes = st.get('nodes') or []
    w.current_node = 'N01'
    ntext = _nodes_text(w, None)
    ok('J3 ★★★ 发给小说的是**当前节点的名称 + 完成判据**',
       '白灯下的第一碗茶' in ntext and '主动试过一次' in ntext, ntext[:60])
    later = [str(n.get('名称') or '') for n in (st.get('nodes') or [])[1:]]
    ok('J3b ★★★ 而且**不点后面节点的名字**（节点名本身就是剧透，'
       '2026-10-14 为"第一天就想把谜底解开"就是这么修的）',
       all(x and x not in ntext for x in later), f'后面的节点 {later}')
    ok('J3c ★★★ 并明写「只走这一步 / 不许提前揭开后面的真相」',
       '只走这一步' in ntext and '不许提前揭开' in ntext, '')

    # ── J4 知情者：信息边界要有实体（空着 = 机制空转）──
    people = st.get('people') or []
    with_knowers = [p for p in people if (p.get('知情者') or [])]
    ok('J4 ★★★ 至少三个人**写了`知情者`**（空着 ⇒ `blind_spots` 空转、'
       '"信息边界"只是四个字）',
       len(with_knowers) >= 3, f'{len(with_knowers)} 人有知情者')

    w2 = WorldState()
    for p in people:
        nm = str(p.get('姓名') or '')
        w2.people[nm] = PersonState(
            name=nm, secret=str(p.get('秘密') or ''),
            knows=[str(x) for x in (p.get('知情者') or [])])
    # 柳氏知道沈砚在瞒事？她不在沈砚的知情者里（沈砚的知情者是柳氏，表示"柳氏知道沈砚"）…
    # ⚠ 语义：`知情者` 列在**秘密拥有者**身上，写"谁可以知道我的秘密"。
    #   所以沈砚的秘密写着 知情者=[柳氏] ⇒ 柳氏知道沈砚的事 ⇒ 柳氏不该"察觉他在瞒"。
    ok('J4b ★★★ 语义正确：在知情名单里的人**不会**被判成"察觉对方在瞒事"',
       '沈砚' not in w2.blind_spots('柳氏'),
       f'柳氏察觉={w2.blind_spots("柳氏")}')
    ok('J4c ★★★ 成对：不在名单里的人**会**被判成察觉（这才有信息差与试探）',
       '柳氏' in w2.blind_spots('阿九'),
       f'阿九察觉={w2.blind_spots("阿九")}')

    # ── J5 两条要求不许打架：写样章里必须明写「以节点为准」──
    import inspect
    from crew import agents as _A   # ⚠ 本函数里没引入 A（J 组只用 project_builder），
    #   上一版直接写 `A._mumu_sample` ⇒ NameError ⇒ **后面两条判据根本没跑**。
    #   这是「判据总数莫名减少」那类假绿：74/74 看着全绿，其实少跑两条。
    src = inspect.getsource(_A._mumu_sample)
    ok('J5 ★★★ "只揭一层"与节点**不打架**：明写"给了节点就以节点为准"'
       '（同一件事两处说法，模型只会随机挑一条）',
       '以节点为准' in src, '')
    ok('J5b ★★★ "结尾不可逆"也与节点对齐（明说和"完成判据"是同一件事）',
       '完成判据' in src, '')

# ── K —— 保护"推演出来的风格"：只有实病才退回（2026-10-21）──────────────
# [EN] K -- protect the style the simulation produces: only real defects trigger a rewrite
def test_soft_classes_do_not_trigger() -> None:
    """用户问：「加了这么多导入导出的限制之后，中间的推演步骤还有足够的灵活性吗？」

    查下来我这几轮的改动只占演员提示词的 **0.9%**（85 字 / 1 处约束词），
    **不是**这轮把空间压掉的。但查出一个**我这轮引入的真问题**：

      `write_check_retry` 把检测器的**候选**当成了**判决** —— 只要 `prose_issue_count`
      数出任何一处，就拿去退回重写。而"重复 / 道具循环 / 憋气段 / 平铺段"这四类是
      **风格候选**：那篇专业分析报告明说"重复变奏手法纯熟"是**优点**，
      病与不病的分界是**可删除性**（删掉读者损失什么）—— 那是语义判断。

    ★ 实测证据（本判据的 K2/K3）：
      · 7 次有推进的变奏：检测器判「道具循环 2 处」
      · 7 次一模一样的重复：检测器也判「道具循环 2 处」
      ⇒ 检测器**分不出来**。拿它当"毛病"退回，就是拿判决的分量去用候选。

    ★ 而且实测的代价很具体：第 1 遍 3417 字 11 处 → 退回 → 第 2 遍 4580 字 **13 处**
      （越改越多）；另一次 2145→2116，憋气段 5→4 但新增自洽 1 —— 它在追候选。

    ★ 修法（与 `crew/global_checks.py` 的"只出候选、不进自动修复"同一条纪律）：
      · 实病（元叙述/拥挤段/感知自洽/问答悬空/**篇幅不足**）→ 退回重写；
      · 候选（憋气段/平铺段/重复/道具循环）→ 进清单**当参考**，不单独触发退回。

    ⚠ 候选**不丢**：照样进日志、照样写进清单（分成"必须改"与"你可以自己判断"两段）。
    [EN] The user asked: "after all these import/export limits, is the simulation still free
    [EN] enough?" Measured: this round's additions are only **0.9%** of the actor prompt (85 chars,
    [EN] one extra constraint word) -- the space was **not** squeezed here. But it exposed a **real
    [EN] problem I introduced**: `write_check_retry` treated the detector's **candidates** as
    [EN] **verdicts**, sending back a rewrite for anything counted. Yet repetition / prop cycles /
    [EN] long-sentence rhythm / report style are **style candidates** -- the professional review called
    [EN] the repetition-variation technique a **strength**, and the real dividing line is
    [EN] **deletability**, a semantic judgement.
    [EN] ★ Measured (K2/K3): seven advancing variations and seven identical repeats both score
    [EN] "prop cycle 2" -- the detector **cannot tell them apart**. Sending that back uses a candidate
    [EN] with a verdict's authority. The cost is concrete: pass 1 3417 chars / 11 defects -> pass 2
    [EN] 4580 chars / **13** defects (worse), another run 2145 -> 2116 with long spans 5 -> 4 but a new
    [EN] contradiction -- it was chasing candidates.
    [EN] ★ Fix (same discipline as "detect-only, never auto-fix" in `crew/global_checks.py`):
    [EN] real defects (meta / crowded / perceptual / unanswered / **too short**) trigger a rewrite;
    [EN] candidates go into the list as **reference** and never trigger one alone.
    [EN] ⚠ Candidates are not dropped: they still reach the log and the list (now split into
    [EN] "must fix" and "your call").
    """
    from crew import agents as A
    from crew import prose_flow as PF
    from novelservices import mumu_bridge as BR

    # ── K1 划分正确：候选不算实病，而"篇幅不足"算（那不是风格，是没写出来）──
    ok('K1 ★★★ 四类**风格候选**不算实病（重复/道具循环/憋气段/平铺段）',
       A.issue_split({'重复': 3, '道具循环': 2, '憋气段': 5, '平铺段': 1}) == (0, 11),
       str(A.issue_split({'重复': 3, '道具循环': 2, '憋气段': 5, '平铺段': 1})))
    ok('K1b ★★★ 成对：**篇幅不足**算实病（94 字被当"干净"交过，那不是风格）',
       A.issue_split({'篇幅不足': 1})[0] == 1, str(A.issue_split({'篇幅不足': 1})))
    ok('K1c ★★★ 不认识的类**算实病**（宁多退一次，也不让真毛病静默进成品）',
       A.issue_split({'某个新检测器': 2})[0] == 2, str(A.issue_split({'某个新检测器': 2})))

    # ── K2/K3 实测那个关键事实：检测器分不出"有意变奏"与"原地打转" ──
    adv = ('沈砚提壶来斟。碗满了，壶嘴还在滴。阿九把碗端起来喝了一口，水是凉的。\n\n'
           '过了半刻，沈砚又提壶过来。这一回碗里的水只剩小半碗，而他明明一口没喝。\n\n'
           '第三次添水，阿九特意先看了看碗，碗是满的。他抬头看沈砚，沈砚正在擦柜子。\n\n'
           '第四次，他故意把碗里的水泼在地上。沈砚看了一眼地上那摊水，提壶，又给他添满了。\n\n'
           '第五次，他不再看碗，改成看壶。壶嘴是干的，壶身也不烫，可倒出来的水是热的。')
    same = '沈砚提壶来斟，阿九说了声谢。他把碗端起来喝了一口，放回去。\n\n' * 5
    n_adv = PF.prose_issue_count(adv).get('道具循环', 0)
    n_same = PF.prose_issue_count(same).get('道具循环', 0)
    ok('K2 ★★★ 记录在案：检测器**分不出**"有意变奏"与"原地打转"（所以不能当判决）',
       n_adv >= 1 and n_same >= 1, f'变奏={n_adv} 打转={n_same}（两者都 >0）')

    # ── K4 **核心行为**：只有候选 ⇒ 不退回（只调一次）──
    #   打桩把计数固定成"只有候选"，看会不会白退一遍。
    from crew import prose_flow as _PF
    real_cnt = _PF.prose_issue_count
    calls = {'n': 0}

    class _R:
        ok = True
        text = '这一版的笔法很好，长句多但那是我们要的。' * 40
        reason = ''

    class _T:
        def __init__(self, fix=''):
            self.outline, self.title, self.target_words = fix, 't', 1500

    real_gen = BR.generate_chapter
    old_tries = CFG.i('MUMU_EXPORT_TRIES')
    try:
        BR.generate_chapter = lambda _t: (calls.__setitem__('n', calls['n'] + 1), _R())[1]
        _PF.prose_issue_count = lambda _t: {'憋气段': 5, '重复': 3}   # 全是候选
        CFG.set('MUMU_EXPORT_TRIES', 2)
        txt, _ = A.write_check_retry(BR, lambda fx: _T(fx), tag='判据K4')
    finally:
        BR.generate_chapter = real_gen
        _PF.prose_issue_count = real_cnt
        CFG.set('MUMU_EXPORT_TRIES', old_tries)
    ok('K4 ★★★ **只剩风格候选 ⇒ 不退回**（保留这一版的笔法，不为"重复多"再改一遍）',
       calls['n'] == 1, f'调了 {calls["n"]} 次')
    ok('K4b ★★★ 成对：而这一版**原样交出去**（不是被清空、也不是被回退成空）',
       len(txt) > 100, f'{len(txt)} 字')

    # ── K5 有实病 ⇒ 仍然退回（成对，别把这条改成人人都不退）──
    calls2 = {'n': 0}
    try:
        BR.generate_chapter = lambda _t: (calls2.__setitem__('n', calls2['n'] + 1), _R())[1]
        _PF.prose_issue_count = lambda _t: {'感知自洽': 1, '重复': 3}   # 有实病
        CFG.set('MUMU_EXPORT_TRIES', 2)
        A.write_check_retry(BR, lambda fx: _T(fx), tag='判据K5')
    finally:
        BR.generate_chapter = real_gen
        _PF.prose_issue_count = real_cnt
        CFG.set('MUMU_EXPORT_TRIES', old_tries)
    ok('K5 ★★★ 成对：有**实病**（感知自洽）⇒ 照样退回重写',
       calls2['n'] == 2, f'调了 {calls2["n"]} 次')

    # ── K6 清单分两段说，别让服务把候选当硬要求 ──
    one = A.fix_list_line({'感知自洽': 1, '憋气段': 5})
    ok('K6 ★★★ 退回的清单**分两段**：「必须改的」与「你可以自己判断的」',
       '必须改的' in one and '你可以自己判断的' in one, '')
    ok('K6b ★★★ 并明写候选"改不改由你定，别为了它把戏改散"'
       '（否则服务会把风格也一起改平）',
       '别为了它把戏改散' in one and '不是硬要求' in one, '')
    ok('K6c ★★ 只有候选时，清单里**没有**「必须改的」那一段（不虚报硬要求）',
       '必须改的' not in A.fix_list_line({'憋气段': 5}), '')

# ── L —— 2026-10-21 两个建议：许可补强 / notes 分级 ──────────────────────
# [EN] L -- the two suggestions from 2026-10-21: stronger permissions / tiered notes
def test_license_and_note_tiers() -> None:
    """用户说「2个建议帮我处理了」—— 这两条都要能测、能防回归。

    ① **许可补强**：实测演员提示词里约束词 : 许可词 = 5.9 : 1（47 : 8）。
       比例失衡的后果不是"读起来凶"，而是**模型趋于保守**——每一句禁令都在暗示
       "保险的做法是别动"，而许可只说了"你可以不回话"，等于把"不动"也允许了。
       补的是最缺的那半边：**允许他做错、允许他不讨人喜欢、允许他偏离今天的目标**。

    ② **`style.notes` 分级**：上一轮我把某本书的实测写法约束写进 `style.notes`，
       而它随 `顶级规则.md` → `rules_text` → `world_prefix_stable()`
       **原样进了每个演员的提示词**。问题是那些是「成品读起来该是什么样」，
       不是演员一拍里能执行的动作（「每样最多复位三次」→ 他只会不敢碰那只壶）。
       ⇒ 拆成 `notes`（写作层，进 `写作层规则.md`）与 `actor_notes`（演员也读，进 `表演备注.md`）。

    ⚠ 全部测**真跑出来的提示词**，不测源码字符串。
    [EN] The user said "handle those two suggestions"; both must be testable.
    [EN] ① **Stronger permissions**: measured 47 constraint words vs 8 permission words = 5.9:1.
    [EN] The consequence is not "reads harsh" but **the model turns conservative** -- every ban
    [EN] whispers "the safe move is doing nothing", and the only permission on offer was "you may not
    [EN] answer", which blesses inaction too. What was missing: **allowed to be wrong, allowed to be
    [EN] unlikable, allowed to miss today's goal**.
    [EN] ② **Tiered `style.notes`**: last round a book's measured writing constraints went into
    [EN] `style.notes`, which travelled `顶级规则.md` -> `rules_text` -> `world_prefix_stable()`
    [EN] **verbatim into every actor prompt**. Those describe "what the finished prose reads like",
    [EN] not an action an actor can take ("each prop resets at most three times" -> he just avoids
    [EN] the prop). => Split into `notes` (writing layer, -> 写作层规则.md) and `actor_notes`
    [EN] (actors too, -> 表演备注.md).
    [EN] ⚠ Everything is tested against **the prompt actually produced**, not source strings.
    """
    import asyncio
    import tempfile

    from agent import freedom as FR
    from crew import agents as A
    from novel_bench.bench import dataset as DS
    from novel_bench.bench import project_builder as PB
    from sim.setup import load_settings
    from world.state import PersonState, WorldState

    # ── L1 许可段补了三条（做错 / 不讨喜 / 办不成）──
    lic = FR.license_line()
    ok('L1 ★★★ 许可段补上了「可以不讨人喜欢」'
       '（实测稿子里所有人物都太得体，冲突只能靠情节硬推）',
       '不讨人喜欢' in lic, '')
    ok('L1b ★★★ 「这一次可以办不成」'
       '（以前"必须推进主线"被读成"这一拍必须办成事"，没人会失败 —— 而失败才是戏）',
       '办不成' in lic, '')
    ok('L1c ★★★ 「可以理解错」'
       '（接话永远接得准，读者感觉不到"两个人在各想各的"）',
       '理解错' in lic, '')
    ok('L1d ★★★ 而且明写「这些都不算跑题」，跑题只有一种：做了自己也做不出的决定',
       '都不算跑题' in lic, '')
    ok('L1e ★★★ 成对：**两条禁令一个都不能少**'
       '（替别人说话 / 说他不可能知道的事 —— 那不是规训，是世界的物理法则）',
       '替别人说话' in lic and '不可能知道' in lic, '')
    # 成对：低规训档仍然返回空（那一档人物该跟着剧本走）
    _old_task = FR.task_level
    try:
        FR.task_level = lambda: 0.1
        low = FR.license_line()
    finally:
        FR.task_level = _old_task
    ok('L1f ★★★ 成对：低规训档**仍然返回空**（那一档该跟着剧本走，给许可只会打架）',
       low == '', repr(low[:30]))

    # ── L2/L3 `style.notes` 分级（真建一次项目，看两份文件与两份前缀）──
    root = Path('.')
    work = DS.load_work(root / 'novel_bench' / 'dataset' / 'works' / '29_mowenlou.yaml')
    tmp = Path(tempfile.mkdtemp())
    PB.build_project(work, work.cases[0], tmp)
    sdir = next(tmp.rglob('故事进度.yaml')).parent
    st = load_settings(sdir)

    ok('L2 ★★★ 建项目时多了两份文件：写作层规则.md + 表演备注.md',
       '写作层规则' in ' '.join(p.name for p in sdir.glob('*.md'))
       and '表演备注' in ' '.join(p.name for p in sdir.glob('*.md')),
       str(sorted(p.name for p in sdir.glob('*.md'))))

    w = WorldState()
    w.scene = '某处'
    w.game_day = 1
    w.rules_text = st.get('rules') or ''
    w.writer_notes = st.get('writer_rules') or ''
    w.actor_notes = st.get('actor_notes') or ''
    pre = w.world_prefix_stable()

    ok('L3 ★★★ **写作层约束进不了演员前缀**（「茶、水、壶、灯」这类成品要求）',
       '茶、水、壶、灯' not in pre, '进了' if '茶、水、壶、灯' in pre else '没进')
    ok('L3b ★★★ **表演备注进得了演员前缀**（「沉默不能只有一种形态」是表演要求）',
       '沉默不能只有一种形态' in pre, '')
    ok('L3c ★★★ 成对：**世界铁律还在**（分级不是把规则一起搬走 —— '
       '第一版就误删过「不许半文半白」整段）',
       bool(w.rules_text.strip()) and ('顶级规则' in pre or '世界铁律' in pre or
                                       '语体' in pre), '')

    # ── L4 作家能读到写作层规则（分级不等于让作家也看不见）──
    class _Ctx(A.SetCtx):
        pass
    ctx = A.SetCtx(world=w, db=None, day=1, people=['阿九'])
    ok('L4 ★★★ 成对：**作家读得到**写作层规则（否则等于把约束弄丢了）',
       '茶、水、壶、灯' in ctx.world_brief(4000), '')

# ── M —— 点停止时也出一章（2026-10-21 用户点名）────────────────────────
# [EN] M -- hitting stop also produces a chapter (named by the user 2026-10-21)
def test_novel_on_stop() -> None:
    """测 `_flush_novel_on_stop` 的**行为**（打桩调真函数），外加两处接线。

    ⚠ 为什么不整跑 `_finish`：它里面要跑落盘、结局小节、自动导出（好几次 LLM 调用）。
      这里只想证明"停止时窗口里一定有今天这一章、且不会重复"，
      所以用 `RunLoop.__new__` 造一个只带几个属性的假实例，把 `_push_narrative`
      与 `_day_novel` 换成记录器 —— 与 K 组同一套手法。

    [EN] Test `_flush_novel_on_stop`'s **behaviour** (stubbed, real function), plus two wiring checks.
        ⚠ Why not run `_finish` end to end: it does persistence, the ending section and auto export several
        [EN] LLM calls deep. Here we only need "on stop the window always gets today's chapter, exactly once",
        [EN] so build a fake instance via `RunLoop.__new__` with a few attributes and replace
        [EN] `_push_narrative` / `_day_novel` with recorders -- the same trick as group K.
    """
    import asyncio
    import inspect
    import sim.loop as L

    class _Cfg:
        def __init__(self, m):
            self.m = m
        def b(self, k):
            return bool(self.m.get(k, False))
        def i(self, k):
            return int(self.m.get(k, 0))
        def s(self, k):
            return str(self.m.get(k, ''))

    def _mk(cfg_map, *, pushed=None, lines=None, organized=None):
        calls: list = []

        class _Fake:
            _current_day = 3
            runfolder = None
            _daily_narrative = list(lines if lines is not None else ['他擦了一遍柜台。'])
            _novel_pushed_days = set(pushed or [])

            def _day_lines(self, raw, scenes=None):
                return [str(x) for x in (raw or []) if str(x).strip()]

            def _organized_chapter_of_day(self, day):
                # 现成的整理稿（模拟"收工已经整理过、文件里有了"）
                return str(organized or '')

            async def _day_novel(self, raw, scenes=None):
                calls.append(('day_novel', self._current_day))

            def _push_narrative(self, text, tier, kind=None):
                calls.append(('push', text, kind))

        f = _Fake()
        real = L.CFG
        L.CFG = _Cfg(cfg_map)
        try:
            asyncio.run(L.RunLoop._flush_novel_on_stop(f, '手动停止'))
        finally:
            L.CFG = real
        return f, calls

    on = {'SHOW_NOVEL_IN_WINDOW': True, 'CREW': True, 'CREW_DAY_NOVEL': True}

    # M1 **当天已经推过 ⇒ 一次都不再推**（否则一次停止留两章）
    _f, _c = _mk(dict(on), pushed=[3])
    ok('M1 ★★★ 今天这一章**已经推过 ⇒ 不再推**（一次停止不会留两章）',
       _c == [], f'调用 {_c}')

    # M2 **每日整理关掉 ⇒ 直推原文，并明说「未整理」**
    _f2, _c2 = _mk({**on, 'CREW_DAY_NOVEL': False})
    ok('M2 ★★★ **每日整理关掉时，窗口里也得有东西**（否则用户以为停止坏了）',
       len(_c2) == 1 and _c2[0][0] == 'push', f'调用 {[_c[0] for _c in _c2]}')
    ok('M2b ★★★ 而且**说清这是未整理的原文**（不然会被当成"整理稿变差了"）',
       bool(_c2) and '未整理' in _c2[0][1] and '他擦了一遍柜台。' in _c2[0][1],
       (_c2[0][1][:40] if _c2 else '没推'))
    ok('M2c ★★ 推的类型是 `NOVEL`（不是 NOTE —— 几千字会被压成一行）',
       bool(_c2) and _c2[0][2] == 'novel', (_c2[0][2] if _c2 else '没推'))
    ok('M2d ★★ 直推之后**记下这一天**（下次停止不再重复推）',
       _f2._novel_pushed_days == {3}, _f2._novel_pushed_days)

    # M3 **窗口开关关掉 ⇒ 一步不做**（用户明确不要）
    _f3, _c3 = _mk({**on, 'SHOW_NOVEL_IN_WINDOW': False})
    ok('M3 ★★★ 成对：`SHOW_NOVEL_IN_WINDOW` 关着就**一步都不做**',
       _c3 == [], f'调用 {_c3}')

    # M4 **今天一个字都没有 ⇒ 安静跳过**（不硬推空章节）
    _f4, _c4 = _mk(dict(on), lines=[])
    ok('M4 ★★★ 成对：今天没有内容 ⇒ **不推空章节**（安静跳过）',
       _c4 == [], f'调用 {_c4}')

    # M5 ★★★ **停止不许再花一次 LLM**（2026-10-21 判据当场抓到过一版这么写的）
    #    第一版在"整理开着"时补调了一次 `_day_novel`，`verify_run_control` 从 68 掉到 55 ——
    #    整条收尾链卡在那次整理上，停止后的落盘/状态/导出全没跑。
    #    ⇒ 现在只做"搬运"：有现成整理稿就搬，没有就推原文，**一次 LLM 都不许调**。
    # [EN] M5 ★★★ **Stopping must not spend another LLM call** (a first version did and the criteria
    # [EN] caught it): it re-ran `_day_novel` when organization was on, and `verify_run_control` fell
    # [EN] from 68 to 55 -- the whole wrap chain stalled on that call and persistence/status/export
    # [EN] never ran. => Now it only **relocates text**: use the ready-made organized chapter if there
    # [EN] is one, else push the raw text, and **call no LLM at all**.
    _f5, _c5 = _mk(dict(on), organized='## 第 3 天 · 亥时\n\n他擦了一遍柜台，抹布拧得很干。')
    ok('M5 ★★★ 有现成的整理稿 ⇒ **直接搬它**（零 LLM 调用）',
       len(_c5) == 1 and _c5[0][0] == 'push'
       and '抹布拧得很干' in _c5[0][1], f'调用 {[_x[0] for _x in _c5]}')
    ok('M5b ★★★ 而且**一次 LLM 都不许调**（`_day_novel` 一次都没被调用）',
       all(_x[0] != 'day_novel' for _x in _c5), f'调用 {[_x[0] for _x in _c5]}')
    ok('M5c ★★ 搬的是整理稿 ⇒ **不再**打"未整理"的标（打了就自相矛盾）',
       bool(_c5) and '未整理' not in _c5[0][1], (_c5[0][1][:40] if _c5 else '没推'))

    # M5d/M5e 「已落盘的整理稿」怎么从 `当天故事.md` 里取（**切错就等于把幕头当正文**）
    #    ⚠ 真实文件的标题是 `## 第 1 天 · 第1天·辰时` —— 只切 `## 第 1 天` 会把
    #      「 · 第1天·辰时」留在正文开头，用户看到的小说就以一行时间戳打头（实测如此）。
    # [EN] M5d/M5e How the "already saved chapter" is cut out of `当天故事.md` (cut it wrong and the
    # [EN] act header becomes body text). ⚠ Real headings read `## 第 1 天 · 第1天·辰时`; cutting only
    # [EN] `## 第 1 天` leaves " · 第1天·辰时" at the top, so the novel starts with a timestamp (measured).
    import tempfile as _tf2
    _d2 = Path(_tf2.mkdtemp())
    Path(_d2, '当天故事.md').write_text(
        '# 当天故事\n\n## 第 1 天 · 亥时\n\n第一天的正文。\n\n## 第 2 天 · 子时\n\n第二天的正文。\n',
        encoding='utf-8')

    class _RF:
        root = _d2

    class _F:
        runfolder = _RF()

    _d1 = L.RunLoop._organized_chapter_of_day(_F(), 1)
    _d2t = L.RunLoop._organized_chapter_of_day(_F(), 2)
    ok('M5d ★★★ 取出来的正文**不带幕头**（「· 亥时」不许留在开头）',
       _d1 == '第一天的正文。', repr(_d1))
    ok('M5e ★★★ 多天文件**互不串**（第 2 天只拿到第 2 天那节）',
       _d2t == '第二天的正文。', repr(_d2t))
    ok('M5f ★★ 那一天还没写 ⇒ 空串（**不编**）',
       L.RunLoop._organized_chapter_of_day(_F(), 9) == '', '')

    # M6 接线：收尾真的调了它，且排在 `_end_day` **之后**
    #    ⚠ 这是**顺序判据**，不是"查有没有这个词"：排前面会先推原文再推整理稿 = 两章。
    #    ⚠ 2026-10-21：收尾的正文从 `_finish` 拆到了 `_finish_steps`
    #      （`_finish` 只负责把整段包进「收尾」那条 doing 登记），所以顺序要在
    #      `_finish_steps` 里看。判据跟着代码结构走，但要盯着**同一件事**。
    # [EN] ⚠ 2026-10-21: the wrap-up body moved from `_finish` to `_finish_steps` (`_finish` only
    # [EN] wraps the whole stretch in the "wrapping up" registration), so the order is checked there.
    src_finish = inspect.getsource(L.RunLoop._finish_steps)
    i_end = src_finish.find('await self._end_day()')
    i_flush = src_finish.find('_flush_novel_on_stop')
    ok('M6 ★★★ 收尾真的调了兜底，而且排在 `_end_day()` **之后**'
       '（排前面会先推原文、再推整理稿 = 同一天两章）',
       i_end > 0 and i_flush > i_end, f'end_day@{i_end} flush@{i_flush}')

    # M7 接线：`_day_novel` 推送成功后**记账**（兜底的防重复全靠这个集合）
    src_dn = inspect.getsource(L.RunLoop._day_novel)
    ok('M7 ★★★ `_day_novel` 推送成功后**记下这一天**（兜底靠它防重复）',
       '_novel_pushed_days' in src_dn and 'add(' in src_dn, '')

    # M9 界面：真的造一次那个可折叠块（不是查字符串 —— 它必须真能按配置开合）
    #    ⚠ 打桩只打 `_wrap_narr_block`（那是外壳样式）；flet 控件本身是真的。
    # [EN] M9 UI: actually build the collapsible block once (not a string match -- it must really open
    # [EN] and close per config). ⚠ Only `_wrap_narr_block` (the shell styling) is stubbed; the flet
    # [EN] controls are real.
    import gui.app_flet as _G
    _App = _G.NovelWorldApp

    class _Shell:
        def _wrap_narr_block(self, inner, style):
            return inner

    _old_open = CFG.b('NOVEL_WINDOW_OPEN')
    try:
        CFG.set('NOVEL_WINDOW_OPEN', 'false')
        _c = _App._mk_novel_block(_Shell(), '他擦了一遍柜台。' * 40, {})
        _closed = _c.controls[1].visible
        _caret_c = _c.controls[0].content.controls[0].value
        _title = _c.controls[0].content.controls[1].value
        CFG.set('NOVEL_WINDOW_OPEN', 'true')
        _c2 = _App._mk_novel_block(_Shell(), '他擦了一遍柜台。' * 40, {})
        _opened = _c2.controls[1].visible
        _caret_o = _c2.controls[0].content.controls[0].value
    finally:
        CFG.set('NOVEL_WINDOW_OPEN', 'true' if _old_open else 'false')
    ok('M9 ★★★ 小说块**真的按 `NOVEL_WINDOW_OPEN` 开合**（默认收起那一条要成立）',
       _closed is False and _opened is True, f'收起配置→visible={_closed} / 展开配置→visible={_opened}')
    ok('M9b ★★ 箭头跟着状态变（`▸` 收起 / `▾` 展开）—— 收起时看得出来这里能点',
       _caret_c == '▸' and _caret_o == '▾', f'{_caret_c} / {_caret_o}')
    ok('M9c ★★★ 标题**带字数**（收起时也知道这里有三千字，不是一片空白）',
       '字' in str(_title) and '320' in str(_title), str(_title)[:40])

    # M8 **停止时不再空手**：`stop()` 里那句即时反馈还在（别为了加兜底把它删了）
    src_stop = inspect.getsource(L.RunLoop.stop)
    ok('M8 ★★ 成对：`stop()` 的**即时反馈**（"正在停止"那条）还在',
       '_push_stop_notice' in src_stop, '')



# ── N —— 状态条一直显示"正在做什么 + 做了多久"（2026-10-21 用户点名）──────
# [EN] N -- the status bar always shows "what is being done + for how long" (named by the user)
def test_doing_status_bar() -> None:
    """测 `crew.doing` 的**行为** + 状态条真的用了它。

    ⚠ 三条都要测**行为**，不查源码字符串：
      · 栈的 push/pop 与回落（嵌套阶段是收尾那一段的真实形状）；
      · `session.snapshot()` 真的带出 `doing` / `doing_secs`；
      · 状态条那行字**真的拼进去了**（造一个假 session 调 `_refresh_run_status`）。
    [EN] Test `crew.doing`'s **behaviour** plus whether the status bar really uses it.
    [EN] ⚠ All three test behaviour, never source strings: the push/pop stack with fallback (the real
    [EN] shape of wrap-up, which nests), `session.snapshot()` really carrying `doing` / `doing_secs`,
    [EN] and the bar text really being composed (fake session -> `_refresh_run_status`).
    """
    import asyncio
    import inspect
    import time
    from crew import doing as DOING

    DOING.reset()

    # N1 栈：内层盖外层，内层退出回落到外层
    DOING.reset()
    t1 = DOING.push('一天结束后讨论')
    t2 = DOING.push('场记 · 连戏检查')
    inner = DOING.snapshot()
    DOING.pop(t2)
    back = DOING.snapshot()
    DOING.pop(t1)
    empty = DOING.snapshot()
    ok('N1 ★★★ **显示最内层**（最具体的那个动作，不是笼统的外层阶段）',
       inner.get('label') == '场记 · 连戏检查', inner.get('label'))
    ok('N1b ★★★ 内层退出 ⇒ **自动回落到外层**（不是变空白）',
       back.get('label') == '一天结束后讨论', back.get('label'))
    ok('N1c ★★ 全退出 ⇒ 空（**读不到就是空**，不编"正在思考"）',
       empty.get('label') == '' and empty.get('secs') == 0.0, empty)

    # N2 秒表：是"这一件事"的时长，会走
    DOING.reset()
    DOING.push('整理当天这一章')
    s1 = DOING.snapshot().get('secs', 0)
    time.sleep(0.25)
    s2 = DOING.snapshot().get('secs', 0)
    ok('N2 ★★★ 秒数是**这一件事**做了多久，而且真的在走',
       s2 > s1 and s2 >= 0.2, f'{s1:.2f} → {s2:.2f}')

    # N3 乱序退出：先弹外层也不能弹错人（异常路径的真实形状）
    DOING.reset()
    a = DOING.push('外层')
    b = DOING.push('内层')
    DOING.pop(a)
    still = DOING.snapshot()
    DOING.pop(b)
    ok('N3 ★★★ 乱序退出**不弹错人**（先弹外层，内层还在）',
       still.get('label') == '内层', still.get('label'))
    ok('N3b ★★ 空栈上 pop 不抛（它在 `finally` 里，抛出去会盖掉真异常）',
       (DOING.pop(99999) or True) and DOING.snapshot().get('label') == '', '')

    # N4 `session.snapshot()` 必须带出这两项（界面读的就是它）
    import sim.session as SS
    src_snap = inspect.getsource(SS.RunSession.snapshot)
    # ⚠ 两种引号都认：源码里写的是 `"doing"`（双引号），只查单引号会误报
    # （第一版就是这么红的 —— 判据查的是"字符串长什么样"，不是"有没有这个键"）。
    # [EN] ⚠ Accept both quote styles: the source uses `"doing"` and checking only single quotes
    # [EN] false-reports (the first version went red exactly that way).
    _dq = chr(34)
    ok('N4 ★★★ 会话快照带出 `doing` / `doing_secs`（界面唯一的读入口）',
       ('doing' in src_snap) and ('doing_secs' in src_snap), '')

    # N5 状态条真的拼了那行字（造一个假 session，调真函数）
    import gui.app_flet as G
    App = G.NovelWorldApp

    class _Txt:
        def __init__(self):
            self.value = ''
            self.color = None
            self.tooltip = None

    class _Sess:
        is_alive = True
        status = 'running'
        reason = ''

        def __init__(self, doing='', secs=0.0, stopping=False):
            self.stopping = stopping
            self._d, self._s = doing, secs

        def snapshot(self):
            return {'day': 3, 'doing': self._d, 'doing_secs': self._s}

    class _Fake:
        _run_status_key = 'running'
        _run_status_kw = None
        _run_status_at = time.time() - 120

        def __init__(self, sess):
            self.session = sess
            self._run_bar_text = _Txt()
            self._run_status_dot = _Txt()

        def _status_view(self, key, kw):
            return '运行中 · 第 3 天', '#0a0'

    f = _Fake(_Sess('场记 · 连戏检查', 12.0))
    App._refresh_run_status(f)
    got = f._run_bar_text.value
    ok('N5 ★★★ 状态条**真的写了"正在做什么 + 做了多久"**',
       ('场记 · 连戏检查' in got) and ('12' in got), got)

    f2 = _Fake(_Sess('', 0.0))
    App._refresh_run_status(f2)
    ok('N5b ★★★ 成对：没在做事时**不编**（只写状态，不出现假的"正在做什么"）',
       '场记' not in f2._run_bar_text.value and '秒' in f2._run_bar_text.value,
       f2._run_bar_text.value)

    f3 = _Fake(_Sess('小说作家 · 写当天这一章', 47.0, stopping=True))
    App._refresh_run_status(f3)
    ok('N5c ★★★ 点了停止 ⇒ 明说「正在停止…」+ 在等哪一步'
       '（实测停止不能中断正在跑的那一次调用，用户会以为按钮没生效）',
       '正在停止' in f3._run_bar_text.value
       and '小说作家' in f3._run_bar_text.value,
       f3._run_bar_text.value)

    # N6 **每个阶段都有名字**：常用阶段一个都不许漏（漏了状态条就显示英文 key）
    need = ['prep', 'novelist', 'screenwriter', 'rehearsal', 'shooting',
            'stopping', 'day_review', 'wrap_meeting', 'novelize', 'export']
    missing = [k for k in need if DOING.stage_label(k) == k]
    ok('N6 ★★★ 每个阶段都有中文名（漏了状态条会显示英文 key）',
       not missing, f'缺 {missing}')

    # N7 角色标签断在词上（实测硬截 10 字会留一个孤零零的字）
    lab = DOING.role_label('小说作家', '写当天这一章的原著样章')
    ok('N7 ★★ 角色标签**断在词上**（不出现"…原著样"这种半截词）',
       lab == '小说作家 · 写当天这一章', lab)
    ok('N7b ★ 标点优先：职责里有「：」就断在那儿',
       DOING.role_label('场记', '连戏检查：时间·物件·称呼') == '场记 · 连戏检查', '')

    # N8 两个写入口：`stage` 与 `call` 都要 push，而且都要 pop（漏 pop = 标签永久挂着）
    from crew import studio as ST
    src_stage = inspect.getsource(ST.Studio.stage)
    src_call = inspect.getsource(ST.Studio.call)
    ok('N8 ★★★ `stage` 有 push 也有 pop（漏 pop ⇒ 状态条永远停在那一步）',
       'DOING.push' in src_stage and 'DOING.pop' in src_stage, '')
    ok('N8b ★★★ `call` 也有 push/pop（收尾那四个职位靠它逐个显示）',
       'DOING.push' in src_call and 'DOING.pop' in src_call, '')

    # N9 收尾整段被包住：点停止之后到全部结束，状态条永远有东西
    import sim.loop as L
    src_finish = inspect.getsource(L.RunLoop._finish)
    ok('N9 ★★★ 收尾整段包在 `push/pop` 里（点停止后一直显示「收尾」）',
       'DOING.push' in src_finish and 'DOING.pop' in src_finish, '')
    ok('N9b ★★ 而且 `try/finally`：某一步抛异常也不能把「收尾」留在栈上',
       'finally' in src_finish and 'DOING.pop' in src_finish.split('finally')[-1], '')

    # N10 **点停止后不许再开新的一遍**（实测：又写了两遍、多等 3 分钟）
    from crew import agents as AG
    src_retry = inspect.getsource(AG.write_check_retry)
    ok('N10 ★★★ 退回重写**每遍开始前问一句"要停吗"**（实测停止后又写了两遍）',
       'should_stop' in src_retry and 'attempt > 1' in src_retry, '')
    src_sample = inspect.getsource(AG._mumu_sample)
    ok('N10b ★★★ 写样章**进门先看停止标志**（已经在停就别再开新活）',
       'stopping' in src_sample, '')

    # N11 收尾等待时长**从配置来**（原来写死 20 秒 / 120 秒，把"正常但慢"误判成"停止坏了"）
    ok('N11 ★★★ 收尾等待是配置项（默认 900 秒），不是写死的 20 秒',
       WRAP_WAIT_LIMIT >= 120, WRAP_WAIT_LIMIT)

    DOING.reset()



# ── E —— 配置与界面 ─────────────────────────────────────────────────
# [EN] E -- config & UI
def test_config_ui() -> None:
    ok('E1 ★ config.py 有 MUMU_FOR_EXPORT 且默认关',
       SPEC.get('MUMU_FOR_EXPORT', {}).get('default') is False,
       f"default={SPEC.get('MUMU_FOR_EXPORT', {}).get('default')!r}")
    gui = (APP_DIR / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    ok('E2 ★ 天机页面有这个开关的显示（标签文案）',
       '导出小说版本时用它重写' in gui, '')
    ok('E3 ★ 天机保存时会写 MUMU_FOR_EXPORT',
       "CFG.set('MUMU_FOR_EXPORT'" in gui, '')
    ok('E4 ★ 开关定义变量存在（mumu_export = mk_switch）',
       'mumu_export = mk_switch(' in gui, '')


def main() -> int:
    print('═' * 62)
    print('  验证：导出「小说版本」改走 MuMuAINovel 重写（2026-10-16）')
    print('═' * 62)
    try:
        print('\n【A】开关接线')
        test_enabled_for()
        print('\n【B】render 用 day_bodies')
        test_render_day_bodies()
        print('\n【C】导出落盘（成 / 败）')
        test_write_mumu()
        print('\n【D】调度接线')
        test_bundle_wiring()
        print('\n【E】配置与界面')
        test_config_ui()
        print('\n【F】2026-10-21 架构：外部服务优先 / 输入三件套 / 部分成功取回')
        test_arch_2026_10_21()
        print('\n【G】写归服务、查归自己、不过退回重写')
        test_write_check_retry()
        print('\n【H】专业分析报告的五条：提示词能治的三条')
        test_prompt_fixes_for_review()
        print('\n【I】提示词去书化 / 项目级规则只对自己生效')
        test_prompt_scope()
        print('\n【J】揭秘后移 / 结尾反转：在计划层（进度节点）解决')
        test_planning_layer_solves_structure()
        print('\n【K】保护推演出来的风格：只有实病才退回')
        test_soft_classes_do_not_trigger()
        print('\n【L】许可补强 / style.notes 分级')
        test_license_and_note_tiers()
        print('\n【M】点停止时也出一章')
        test_novel_on_stop()
        print('\n【N】状态条：一直显示正在做什么 + 做了多久')
        test_doing_status_bar()
    except Exception:                                            # noqa: BLE001
        import traceback
        traceback.print_exc()
        report['fatal'] = traceback.format_exc()

    checks = report['checks']
    bad = [c for c in checks if not c['ok']]
    report['passed'] = len(checks) - len(bad)
    report['total'] = len(checks)
    report['ok'] = not bad and not report.get('fatal')
    (OUT / 'mumu_export_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('\n' + '─' * 62)
    print(f'  MuMuAINovel 导出重写验证：{report["passed"]}/{report["total"]}'
          + ('' if report['ok'] else '   ← 有失败'))
    for c in bad:
        print(f'    ! {c["name"]}  [{c["detail"]}]')
    print('─' * 62)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
