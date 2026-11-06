# -*- coding: utf-8 -*-
"""导出调度（设计稿 §10.10）：把四类导出物串成一个动作。

为什么要有个调度层？因为「导出」这件事有两个入口——
**运行结束时自动出**、**界面上手动出（含运行中途）**——而这两条路
要产出的东西必须完全一样。把「导出哪些、怎么导出」收在一处，
两个入口就只是换个调用点，不会各写一套然后慢慢走偏。

四类导出物：

| kind | 产物 | 代价 | 数据来源 |
|---|---|---|---|
| `raw_novel` | **小说原文**（逐字原样） | 零成本 | 每天的生活/ |
| `reference` | 小说参考（素材册） | 零成本 | 每天的生活/ |
| `novel` | 小说版本（最终改写稿） | 零成本（润色另算） | 每天的生活/ |
| `report` | 运行报告 | 要 LLM（统计部分不要） | 落盘 + LLM |
| `guide` | 写作指导（大纲建议） | 要 LLM | 落盘 + LLM |

「哪些在结束时自动出」由配置决定（`auto_kinds()`），
**手动导出不受开关限制**——开关管的是"自动不自动"，不是"能不能"。

English:
Export scheduling (design doc §10.10): string the four export kinds into a single action.
Why is there a scheduling layer? Because "export" has two entry points --
**automatic on run finish** and **manual from the UI (including mid-run)** -- and these two
paths
must produce exactly the same things. By centralizing "what to export and how",
the two entry points just become different call sites, instead of each writing its own copy and
slowly drifting apart.
The four export kinds:
| kind | artifact | cost | data source |
|---|---|---|---|
| `raw_novel` | **Novel raw text** (verbatim, character for character) | zero cost | 每天的生活/ |
| `novel` | Novel version (readable draft) | zero cost (polish counted separately) | 每天的生活/ |
| `report` | Run report | needs LLM (the stats part does not) | disk + LLM |
| `guide` | Writing guide (outline suggestions) | needs LLM | disk + LLM |
"Which ones auto-export on finish" is decided by config (`auto_kinds()`),
**manual export is not restricted by the switches** -- the switches govern "auto or not", not
"can or cannot".
"""
from __future__ import annotations

from config import CFG

from export import novel_version as NV
from export import outputs as OUT

#: 本模块的 logger。⚠ 必须与 `_LOG_EXC` 用**同一个名字**（`nws.export`），
#: 否则日志分叉成两个 channel，按 logger 名过滤时只看到一半。
# [EN] Module logger. Must match the name used by `_LOG_EXC` (`nws.export`), or logs split into
# [EN] two channels and filtering by logger name shows only half of them.
_LOG = __import__("logging").getLogger("nws.export")

KIND_REFERENCE = 'reference'
KIND_NOVEL = 'novel'
# ★★ 2026-10-10：**小说原文**（用户点名：「原文是重点导出项目」）。
# [EN] ★★ 2026-10-10: **Novel raw text** (user explicitly requested: "raw text is the key export
# [EN] item").
KIND_RAW_NOVEL = 'raw_novel'
KIND_REPORT = 'report'
KIND_GUIDE = 'guide'

# 展示顺序：零成本的排前面（用户更容易先拿到东西）
#: 顺序 = 界面上的显示顺序，也是**导出顺序**。
#  ★ 2026-10-10：`raw_novel` 排**第一个** —— 用户说「原文是重点导出项目」，
#    排在第一位就是「重点」在界面上的样子（勾选、阅读顺序都跟着它）。
# [EN] Display order: zero-cost ones come first (users get something in hand more easily)
# [EN] : order = display order in the UI, which is also the **export order**.
# [EN] ★ 2026-10-10: `raw_novel` is placed **first** -- the user said "raw text is the key export
# [EN] item",
# [EN] placing it first is what "key" looks like in the UI (both checkbox and reading order follow it).
KINDS: tuple[str, ...] = (KIND_RAW_NOVEL, KIND_NOVEL, KIND_REFERENCE,
                          KIND_REPORT, KIND_GUIDE)

KIND_LABEL = {
    # ★★★ 2026-10-25 改名（用户："原文 参考 版本 这几个后缀体现不出具体这些是什么情况下的小说"）：
    #   三个旧名都带"小说"两字，读起来像同一件东西的三种叫法。
    #   新名按**加工到哪一步**排，一眼看得见递进：原始稿（零加工）→ 原始稿加细节（留痕迹）→ 最终改写稿（剃净）。
    #   详见 `export/novel_version.py` 的 `_STEM` 注释。
    # [EN] ★★★ Renamed 2026-10-25 (user: "these suffixes don't convey what kind of novel each one
    # [EN] is"): all three old names carried "小说" and read like three labels for one thing. The new
    # [EN] names sort by **how far processing went**: 原始稿 (zero) -> 原始稿加细节 (traces kept) ->
    # [EN] 最终改写稿 (traces stripped). See `_STEM` in `export/novel_version.py`.
    KIND_RAW_NOVEL: '原始稿',
    KIND_NOVEL: '最终改写稿',
    KIND_REFERENCE: '原始稿加细节',
    KIND_REPORT: '运行报告',
    KIND_GUIDE: '写作指导',
}

KIND_DESC = {
    KIND_RAW_NOVEL: '按天装订的**原始稿**：一个字都不动，不剃细节、不润色、不合并。'
                    '当初到底写了什么，以它为准',
    KIND_NOVEL: '按天装订的**最终改写稿**：剃掉过程细节（在场/依据/机制备注/图片路径），'
                '读起来像小说，可直接改写。⚠ 开着重写开关时正文会被重写，'
                '要"一字不改"请看原始稿',
    KIND_REFERENCE: '按天装订的**原始稿加细节**：正文一字不改，'
                    '另外留着过程细节，用来对照「这句是从哪条设定长出来的」',
    KIND_REPORT: '概览、账单、人物表现与优化建议；跑完再看更有用',
    KIND_GUIDE: '推演后的写作大纲，可直接当提纲用',
}

# 每个 kind 的「结束自动导出」开关（项目级）
# [EN] Per-kind "auto-export on finish" switch (project level)
KIND_AUTO_KEY = {
    KIND_RAW_NOVEL: 'EXPORT_ON_END_RAW',
    KIND_REFERENCE: 'EXPORT_ON_END_REFERENCE',
    KIND_NOVEL: 'EXPORT_ON_END_NOVEL',
    KIND_REPORT: 'AUTO_SUMMARY_ON_END',
    KIND_GUIDE: 'EXPORT_ON_END_GUIDE',
}

# 是否要调 LLM（界面据此提示「耗 token」）
# [EN] Whether an LLM call is needed (the UI uses this to hint "costs tokens")
KIND_USES_LLM = {
    KIND_RAW_NOVEL: False,
    KIND_NOVEL: False,
    KIND_REFERENCE: False,
    KIND_REPORT: True,
    KIND_GUIDE: True,
}


def auto_kinds() -> list[str]:
    """本轮结束时该自动导出哪些（读配置）。
        English:
    Which kinds should auto-export at the end of this round (reads config).
    """
    return [k for k in KINDS if CFG.b(KIND_AUTO_KEY[k])]


def default_manual_kinds() -> list[str]:
    """手动导出对话框的默认勾选。

    ① 有「结束时自动导出」开着的档 → 就勾那些（与自动开关同步，用户心智一致）；
    ② **一个都没开**（2026-10-26 起是出厂默认，四个都关）→ **兜底勾「零成本」那三档**
       （原始稿 / 原始稿加细节 / 最终改写稿），**不勾要花 token 的**（运行报告 / 写作指导）。

    ⚠ 为什么兜底不是"全勾"也不是"全不勾"：
       · 全不勾 ⇒ 用户点开导出框一片空白，点「开始导出」直接报"至少选一样"，
         等于把"默认关闭"变成了"默认不能用"。
       · 全勾 ⇒ 把两项**要花 token** 的也默认勾上，用户点一下就开始烧钱。
       零成本那三档正是他 99% 想要的东西，勾它们既不烧钱也不是空框。
    [EN] Default ticks for the manual dialog: (1) kinds whose auto switch is on; (2) if none is on
    [EN] (the factory state since 2026-10-26) fall back to the **zero-cost** kinds only -- not all
    [EN] (would tick the token-spending ones) and not none (an empty dialog that errors out).
    """
    picked = auto_kinds()
    if picked:
        return picked
    return [k for k in KINDS if not KIND_USES_LLM[k]]


def label_of(kind: str) -> str:
    return KIND_LABEL.get(kind, kind)


# ══════════════════════════════════════════════════════════════
#  本轮导出状态：**防重复导出**（2026-10-26）
# [EN] Per-round export state: **prevent exporting twice** (2026-10-26)
# ══════════════════════════════════════════════════════════════
#  用户 2026-10-25 的疑问：「导出稿件不是我在最后才导出的吗？应该只有一个版本才对」
#  ⇒ 实测那一次是**两条路径各导了一份**：
#     ① 22:50 点「停止」→ 收工自动导出（`EXPORT_ON_END_*` 全开就会跑）
#     ② 22:55 用户以为没反应 → 手动点「开始导出」
#     于是同时产出 v1 / v2，而用户**只记得自己点了一次**。
#
#  用户 2026-10-26 定的口径：「**已经自动导出，手动导出就跳过**」。
#  所以这里维护两件东西：
#    · `inflight` —— 现在有没有导出行在跑（哪一条）。**这条必须有**：
#      上面那个 22:55 的例子，自动那次**还没跑完**（MuMu 重写 9 分钟），
#      只记「已导出」是拦不住的。
#    · `auto_done` —— 收工自动导出**已经成功出过**哪些档（界面据此把它们默认勾掉）。
#
#  ⚠ key 用 `str(run.root)`：一次运行一个目录，换轮次就是新 key，天然是"本轮"语义。
#  ⚠ 只记**成功**的档：失败的那些必须允许手动重导（否则用户被一次失败卡死）。
#  ⚠ 这是**进程内**状态。重启程序后自动失效 —— 那正好：自动导出本来只在"点停止"那一次发生，
#    重启后不存在"上一轮的自动导出"这回事。
# [EN] User's rule (2026-10-26): **if auto-export already ran, manual export skips**.
# [EN] Two things are tracked: `inflight` (which path is currently running -- required, because in
# [EN] the reported case the auto run was still busy for 9 minutes) and `auto_done` (which kinds the
# [EN] finish-time auto-export actually produced). Only **successful** kinds are recorded, so a
# [EN] failure can always be retried by hand. In-process only, which is exactly the right scope.
_EXPORT_STATE: dict[str, dict] = {}


def _state_of(run) -> dict:
    key = str(getattr(run, "root", run))
    return _EXPORT_STATE.setdefault(key, {"auto_done": {}, "inflight": ""})


def auto_done(run) -> dict:
    """收工自动导出**已经成功出过**的档：`{kind: {"path","version"}}`。"""
    return dict(_state_of(run).get("auto_done") or {})


def inflight(run) -> str:
    """正在跑的是哪条导出（`'auto'` / `'manual'` / `''`）。"""
    return str(_state_of(run).get("inflight") or "")


def manual_kinds_to_run(run, kinds: list[str]) -> tuple[list[str], list[str]]:
    """手动导出时，把「已经自动导出过」的档剔掉，返回 `(要跑的, 被跳过的)`。

    ⚠ 只在 `auto_done` 有的档上生效；同一次手动导出里**没跑过的档照常导**。
    [EN] Drop kinds already produced by the finish-time auto-export; returns
    [EN] `(to_run, skipped)`. Kinds the auto run did not produce are left alone.
    """
    done = auto_done(run)
    to_run = [k for k in kinds if k not in done]
    skipped = [k for k in kinds if k in done]
    return to_run, skipped


# ══════════════════════════════════════════════════════════════
#  主入口
# [EN] Main entry
# ══════════════════════════════════════════════════════════════
async def export_bundle(run, kinds: list[str] | None = None, *, upto_day: int | None = None,
                        partial: bool = False, polish: bool | None = None,
                        world=None, db=None, ledger_cost: dict | None = None,
                        on_progress=None, on_day=None,
                        source: str = "manual") -> dict:
    """导出指定的几类产物。

    参数
    ----
    kinds      要导出哪些（缺省 = 全部四类）。非法项会被忽略。
    upto_day   只装订到此天为止（缺省 = 所有已落盘的天）。
    partial    是否为「中途导出」——只影响报告/指导里那句「尚未跑完」的提示。
    polish     小说版本是否另出 LLM 润色稿；缺省读 `EXPORT_NOVEL_POLISH`。
    on_progress 回调 `(kind, state)`，state ∈ {'start','ok','fail'}，界面用来显示进度。
    on_day     回调 `(kind, i, total, day)` —— **逐天进度**（只有走 MuMu 重写那条路才有）。
    source     `'manual'`（界面按钮）/ `'auto'`（收工自动导出）；`'auto'` 会把成功
               出过的档记进 `auto_done`，界面据此把手动导出里这些档勾掉。

    返回 `{"items": [...], "ok": bool, "days": int, "partial": bool}`；
    **忙时**另返回 `{"busy": True, "busy_source": 'auto'|'manual'}` 且 `items` 为空 ——
    调用方必须据此提示「已经有一个导出在跑了」，**不能当成"导出成功但没产物"**。
    每一项是 `{"kind","label","ok","path","detail","error","llm"}`，
    **可能**还带 `extra_paths`（同一类多落出来的文件，如润色稿 ——
    界面会把它也列成一行可点的链接）。
    单项失败**不影响其它项**——导出是各算各的，不能因为报告挂了就没收小说。
    
        English:
    Export the specified kinds of artifacts.
        Parameters
        ----
        kinds      Which kinds to export (default = all four). Invalid entries are ignored.
        upto_day   Only bind up to this day (default = all days already on disk).
        partial    Whether this is a "mid-run export" -- only affects the "not yet finished" hint in the report/guide.
        polish     Whether the novel version also produces an LLM-polished draft; default reads `EXPORT_NOVEL_POLISH`.
        on_progress callback `(kind, state)`, state ∈ {'start','ok','fail'}, used by the UI to show progress.
        on_day     callback `(kind, i, total, day)` -- **per-day progress** (MuMu rewrite path only).
        source     `'manual'` (UI button) or `'auto'` (finish-time auto-export); `'auto'` records the
                   kinds it produced into `auto_done`.
        When **busy**, also returns `{"busy": True, "busy_source": ...}` with empty `items` -- callers
        must report "another export is already running" and **not** treat it as a successful empty run.
        Returns `{"items": [...], "ok": bool, "days": int, "partial": bool}`;
        each item is `{"kind","label","ok","path","detail","error","llm"}`,
        and **may** carry `extra_paths` (files produced in addition by the same kind, such as the
        polished draft -- the UI lists them as extra clickable link rows).
        A single item failing **does not affect other items** -- exports are computed independently, and a broken report must not confiscate the novel.
    """
    wanted = [k for k in (kinds or list(KINDS)) if k in KINDS]
    if polish is None:
        polish = CFG.b("EXPORT_NOVEL_POLISH")

    # ★★★ 防重复导出（用户 2026-10-26：「已经自动导出，手动导出就跳过」）
    #   真正要拦的是**并发**：实测用户点「停止」→ 收工自动导出开始跑（MuMu 重写 9 分钟）
    #   → 他以为没反应 → 5 分钟后又点「开始导出」⇒ 两份同时产出 v1/v2。
    #   ⇒ 只记"已导出"拦不住，必须先记"正在跑"。
    # [EN] ★★★ Prevent double export (user, 2026-10-26). The real case is **concurrency**: the
    # [EN] finish-time auto-export was still running for 9 minutes when the user manually
    # [EN] triggered a second one => two drafts at once. Guarding only "already done" cannot
    # [EN] catch that, so "in flight" is recorded first.
    _st = _state_of(run)
    _busy = str(_st.get("inflight") or "")
    if _busy:
        _LOG.info("导出被跳过：已经有一条导出在跑（%s）", _busy)
        return {"items": [], "ok": False, "days": 0, "partial": partial,
                "busy": True, "busy_source": _busy}
    _src = (source or "manual").strip() or "manual"
    _st["inflight"] = _src

    try:
        items: list[dict] = []
        days = 0
        _n = max(1, len(wanted))

        def _emit(kind: str, state: str, info: dict | None = None) -> None:
            """`(kind, state, info)` —— `info` 可选，2026-10-28 起带**细粒度**信息。

            ⚠ 为什么第三个参数可选而不是改签名：给 Several 调用点留活路 ——
              老的两参回调（`on_progress(kind, state)`）照样能用，只是拿不到细分进度。
            [EN] Third argument is optional so existing two-argument callbacks keep working;
            [EN] they simply receive no fine-grained info.
            """
            if on_progress is None:
                return
            try:
                try:
                    on_progress(kind, state, info or {})
                except TypeError:                        # 老的两参回调 → 退回旧口径
                    # [EN] Legacy two-arg callback -> fall back to the old protocol
                    on_progress(kind, state)
            except Exception:
                pass                      # 界面回调出问题不该弄挂导出
                # [EN] UI callback failures should not break exports

        def _emit_day(kind: str, i: int, total: int, day: int) -> None:
            """逐天进度（2026-10-26）：`on_day(kind, i, total, day)`。

            为什么要把 `kind` 带上：界面是按 kind 一行显示进度的，不带 kind
            就没法知道"正在写第 1/2 天"该更新哪一行。
            [EN] Per-day progress. `kind` is included because the UI keeps one row per kind and
            [EN] needs to know which row to update.
            """
            if on_day is None:
                return
            try:
                on_day(kind, i, total, day)
            except Exception:
                pass                      # 同上：界面回调出问题不该弄挂导出

        for kind in wanted:
            _idx = wanted.index(kind)

            def _step(text: str, within: float) -> None:
                """★ 2026-10-28（用户：「导出过程的进度条希望更细致一些」）：
                   **每一小步都报一次**，附带整条进度条的位置 `frac`。

                   为什么有必要细到这一步（这行的来由）：以前只有"档"级三件事
                   （开始 / 成功 / 失败），而一档内部最长的一段（成书复查）实测 **90 秒**
                   一个字不报 ⇒ 进度条一动不动 ⇒ 用户判定"导出卡死" ⇒ 去点停止
                   ⇒ 多出一份 v2（这在本项目里已经发生过一次）。
                   ⇒ 细分到人眼看得见的粒度，是"防卡死误判"，不是锦上添花。
                   [EN] Every micro-step is reported with its position on the whole bar. The
                   [EN] longest inner stretch once ran 90 s with zero updates, which read as a
                   freeze and made the user click Stop (producing a duplicate draft once before).
                """
                _emit(kind, 'step', {'text': str(text),
                                     'frac': min(0.985, (_idx + within) / _n)})

            _emit(kind, 'start', {'frac': (_idx) / _n})
            item = {"kind": kind, "label": label_of(kind), "ok": False,
                    "path": None, "detail": "", "error": "",
                    "llm": KIND_USES_LLM[kind]}
            try:
                if kind == KIND_RAW_NOVEL:
                    _step('扫描已落盘的天', 0.08)
                    r = NV.write_raw_manuscript(run, upto_day=upto_day)
                    days = max(days, r["days"])
                    item["path"] = r["path"]
                    item["detail"] = f"{r['days']} 天 · {r['chars']} 字"
                    if r["skipped"]:
                        item["detail"] += f"（另有 {r['skipped']} 天未纳入）"
                    item["ok"] = True
                elif kind in (KIND_NOVEL, KIND_REFERENCE):
                    # ★ 2026-10-16（用户：「导出时重写小说应调 MuMuAINovel，而非内部 Agent」）：
                    #   导出『小说版本』且开了 MUMU_FOR_EXPORT → 改走 MuMuAINovel
                    #   据『小说原文 + 推演过程』重写；失败自动回退内部整理稿（写在桥里）。
                    # [EN] ★ 2026-10-16 (user: "rewriting at export should call MuMuAINovel, not the
                    # [EN] internal Agent"): exporting the "novel version" with MUMU_FOR_EXPORT on ->
                    # [EN] switch to MuMuAINovel; failure auto-falls back to the internal edited draft.
                    # ★★★ 2026-10-27：**MOCK（演示）模式不许碰外部服务**。
                    #   与 `crew/agents.py::_mumu_enabled_for` 同一个口径 ——
                    #   日志里那句「演示模式：零网络、零成本」是**承诺**，
                    #   导出这条路原来只认 `MUMU_FOR_EXPORT`（用户这台机器是开着的），
                    #   ⇒ MOCK 下导出照样真花钱。
                    # [EN] ★★★ 2026-10-27: **MOCK (demo) mode must not touch external services**.
                    # [EN] Same rule as `crew/agents.py::_mumu_enabled_for` -- the log line "demo mode:
                    # [EN] zero network, zero cost" is a **promise**, and this export path only knew
                    # [EN] about `MUMU_FOR_EXPORT` (which is on on this machine) => exporting under
                    # [EN] MOCK still really spent money.
                    if kind == KIND_NOVEL and CFG.b("MUMU_FOR_EXPORT") and not CFG.b("MOCK_LLM"):
                        # MuMu 天天都要调一次服务 ⇒ **逐天**既是天然刻度，也最有用
                        # （实测一章 17~207 秒）。这一天在这一档里的窗口是 [0.05, 0.90]。
                        # [EN] One service call per day => per-day is both natural and the only
                        # [EN] useful granularity here (17-207 s per chapter).
                        def _on_day(i, t_, d):
                            _within = 0.05 + 0.85 * ((max(1, int(i)) - 1) / max(1, int(t_)))
                            _step(f'重写第 {i}/{t_} 天', _within)
                            _emit_day(kind, i, t_, d)

                        r = await NV.write_manuscript_mumu(
                            run, upto_day=upto_day, on_day=_on_day)
                    else:
                        mode = NV.MODE_NOVEL if kind == KIND_NOVEL else NV.MODE_REFERENCE
                        # ★★★ **成书前整本复查**（R48 的导出关口，2026-10-20）。
                        #   用户原话：「一开始写小说和最后导出的时候都可以进行几轮的问题
                        #   检查也修复，把常见的问题都修复掉」。
                        #   ⚠ 写小说时每章已经查过，但那是**单章视角**：跨天才暴露的毛病
                        #     （同一件东西天天续、同一句话天天问）只有合并后看得见。
                        #   ⚠ 只作用于「小说版本 / 参考」这一档；**「小说原文」一个字不动**
                        #     —— 它是"一字未改"的凭据稿（`write_raw_manuscript` 自己的承诺）。
                        #   ⚠ 关掉这个开关就完全走老路（不多花一次调用）。
                        # [EN] Bind-time whole-book checkup (R48 export gate). Per-chapter checks
                        # [EN] are single-chapter views; defects that only appear across days show
                        # [EN] up here. Only the folded novel version is touched -- the verbatim
                        # [EN] manuscript must stay byte-identical.
                        _bodies = None
                        if CFG.b("EXPORT_FINAL_CHECK"):
                            # ★ `on_stage` 把内部的「第几天 / 第几轮 / 第几步」透出来 ——
                            #   这一段就是以前"进度条一分钟不动"的那段（见 `_step` 的注释）。
                            #   它在这一档里的窗口是 [0.05, 0.85]。
                            # [EN] `on_stage` surfaces day/round/step from inside the checkup -- the
                            # [EN] stretch that used to freeze the bar. Window here: [0.05, 0.85].
                            def _on_stage(text, frac):
                                try:
                                    _f = min(0.99, max(0.0, float(frac)))
                                except Exception:                    # noqa: BLE001
                                    _f = 0.0
                                _step(str(text), 0.05 + 0.80 * _f)

                            try:
                                _bodies = await NV.checkup_before_bind(
                                    run, upto_day=upto_day, mode=mode,
                                    on_stage=_on_stage)
                            except Exception as _e:                  # noqa: BLE001
                                # ⚠ 复查失败**不能弄挂导出** —— 它只是锦上添花的一步，
                                #   拿原文照常装订才是底线。
                                # [EN] A failed checkup must not break the export: binding the
                                # [EN] text as-is is the floor.
                                import logging as _lg
                                _lg.getLogger("nws.export").warning(
                                    "成书复查失败（按原样导出）：%s", _e)
                                _bodies = None
                        _step('装订成稿 · 写盘', 0.88)
                        r = NV.write_manuscript(run, mode=mode, upto_day=upto_day,
                                                day_bodies=_bodies)
                    days = max(days, r["days"])
                    item["path"] = r["path"]
                    item["detail"] = f"{r['days']} 天 · {r['chars']} 字"
                    if r["skipped"]:
                        item["detail"] += f"（另有 {r['skipped']} 天未纳入）"
                    item["ok"] = True
                    if kind == KIND_NOVEL and polish:
                        _step('LLM 润色（要花 token）', 0.93)
                        raw = r["path"].read_text(encoding="utf-8", errors="ignore")
                        polished = await NV.polish_manuscript(run, raw)
                        # 天数一路透传下去，润色稿的文件名才带得上（`…_v2_第1-2天_润色.md`）。
                        # [EN] Pass the day numbers all the way down so the polished filename carries
                        # [EN] the range (`..._v2_第1-2天_润色.md`).
                        pp = NV.write_polished(run, polished, r["version"],
                                              day_numbers=r.get("day_numbers"))
                        item["detail"] += f" · 润色稿 {pp.name}"
                        item["llm"] = True
                        # ★ 2026-10-17（用户：「导出按钮最后的导出的文件的列表我都能点击」）：
                        #   润色稿是**同一个类别多落的一个文件** —— 以前只在 `detail` 里写了
                        #   它的名字，界面就点不到它。补进 `extra_paths`，界面按
                        #   "每个 path 一行可点链接"渲染，那份列表才是完整的。
                        # [EN] ★ 2026-10-17 (user: "every file in the list at the end of the export
                        # [EN] button must be clickable"): the polished draft is **an extra file produced
                        # [EN] by the same kind** -- previously only its name appeared in `detail`, so the
                        # [EN] UI could not click it. Added to `extra_paths`; the UI renders "one
                        # [EN] clickable link row per path", which makes that list complete.
                        item.setdefault("extra_paths", []).append(pp)
                elif kind == KIND_REPORT:
                    _step('汇总账单与事件', 0.15)
                    path = await OUT.generate_run_summary(
                        run, world, db, ledger_cost, partial=partial, upto_day=upto_day)
                    item["path"] = path
                    item["detail"] = "含概览与账单"
                    item["ok"] = True
                elif kind == KIND_GUIDE:
                    _step('整理节点与伏笔', 0.15)
                    path = await OUT.generate_outline(run, world, db, partial=partial)
                    item["path"] = path
                    item["detail"] = "可直接当提纲"
                    item["ok"] = True
            except Exception as e:                 # noqa: BLE001
                _LOG_EXC(kind, e)
                item["error"] = f"{type(e).__name__}: {e}"
            # ★★ 2026-10-21：**过程档案也要能点开**（只在"小说版本"这一条上挂一次）。
            #   分层稿 / 分层日志 / 反思记录都落在导出目录里，但以前不在结果列表里 ——
            #   用户看不见、也点不开，`verify_export` 那条「磁盘上的每个 .md 都能点到」
            #   因此一直红着（链接 3 个 / 磁盘 6 个）。
            #   ⚠ **必须收在 `kind == KIND_NOVEL` 里**：第一版放在了按 kind 循环的公共层，
            #     于是"小说参考"那条也挂了一份 ⇒ 同一个文件名在列表里出现两次
            #     （判据当场抓到：链接 9 个 / 磁盘 6 个）。它们在语义上属于小说版本那一稿。
            #   ⚠ 清单只有一份（`NV.SIDE_FILES`），产品与判据共用。
            # [EN] ★★ 2026-10-21: **process archives must be clickable too** (attached once, on the
            # [EN] "novel version" row only). The atelier draft / its log / the reflection record land in
            # [EN] the export dir but were absent from the result list -- invisible and unopenable, which
            # [EN] kept "every .md on disk is clickable" red (3 links / 6 files).
            # [EN] ⚠ Must stay **inside `kind == KIND_NOVEL`**: the first version sat on the shared layer
            # [EN] of the per-kind loop, so the "reference" row got a copy too => the same filename
            # [EN] appeared twice (caught immediately: 9 links / 6 files). These belong to the novel draft.
            # [EN] ⚠ One list only (`NV.SIDE_FILES`), shared by the product and the criterion.
            if kind == KIND_NOVEL and item.get("ok"):
                for _side in NV.side_archives(run):
                    if _side not in (item.get("extra_paths") or []):
                        item.setdefault("extra_paths", []).append(_side)
            items.append(item)
            _emit(kind, 'ok' if item["ok"] else 'fail',
                  {'frac': (_idx + 1) / _n})

    finally:
        _st["inflight"] = ""
        # 收工自动导出**成功**了哪些档 → 记下来，界面据此把手动导出里这些档默认勾掉。
        # ⚠ 只记成功的：失败的那档必须允许手动重导，否则一次失败就把用户卡死。
        # [EN] Record which kinds the finish-time auto-export actually produced (successful only,
        # [EN] so a failure can still be retried by hand).
        if _src == "auto":
            for _it in items:
                if _it.get("ok") and _it.get("path") is not None:
                    _st["auto_done"][str(_it.get("kind"))] = {
                        "path": str(_it.get("path")), "detail": str(_it.get("detail") or "")}
    return {"items": items, "ok": all(i["ok"] for i in items) if items else False,
            "days": days, "partial": partial}


async def export_on_end(run, *, world=None, db=None, ledger_cost: dict | None = None,
                        on_progress=None) -> dict | None:
    """运行结束时按开关自动导出。一项都没开就返回 `None`（不产生空动作）。

    ★ `source='auto'` 必须传：它让 `export_bundle` 把「这次成功出了哪些档」记进
      `auto_done`，界面据此把手动导出里这些档默认勾掉（用户 2026-10-26 的口径）。
    [EN] `source='auto'` matters: it makes `export_bundle` record which kinds succeeded into
    [EN] `auto_done`, so the manual dialog can pre-untick them.
    """
    kinds = auto_kinds()
    if not kinds:
        return None
    return await export_bundle(run, kinds, partial=False, world=world, db=db,
                               ledger_cost=ledger_cost, on_progress=on_progress,
                               source="auto")


def _LOG_EXC(kind: str, e: Exception) -> None:
    import logging
    logging.getLogger("nws.export").warning("导出 %s 失败: %s", kind, e)
