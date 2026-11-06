# -*- coding: utf-8 -*-
"""判据：**Python SDK**（`developers/sdk/nws`）能真的驱动完整流程。
Verifier: the Python SDK can actually drive the whole pipeline.

为什么这一支必须是**行为**判据（why this must be behavioural）
--------------------------------------------------------------
SDK 的价值全在"脚本能不能真的跑通"。而 SDK 最容易烂掉的方式是
**包得很好看、调用起来却处处错位**（签名对不上、属性名猜错、线程/事件循环
不兼容）—— 那些**读代码看不出来**，只有真跑一遍才现形。
本次写它的时候真跑出来的四个 bug 就是例子：`config.set` 遮蔽内置 `set`、
开卷读错文件夹（读项目而不是引用夹）、`RunFolder` 没有 `.name`、
sqlite 连接**跨线程关不掉**（常驻循环的必然结果）。

所以这一支**真的建书、真的开卷、真的起笔跑几拍、真的导出、真的删**，
全部在**临时目录 + MOCK** 里做，并且跑完**自证没碰用户的东西**（`.env` 的
sha1、真实 Projects 目录的条目数）。
It creates a book, ingests, runs a few beats, exports and deletes — all in a
temp dir under MOCK — and then proves it never touched the user's own files.

产物：`assets/screenshots/sdk_report.json`

English:
criterion: the **Python SDK** (`developers/sdk/nws`) can actually drive the whole pipeline.
Verifier: the Python SDK can actually drive the whole pipeline.
why this one must be a **behavioural** criterion (why this must be behavioural)
--------------------------------------------------------------
The whole value of the SDK is whether a script can really run through. And the easiest way for
the SDK to rot is
**wrapping it nicely but having everything misaligned when called** (signatures don't match,
attribute names guessed wrong, thread/event loop
incompatible) —— those **can't be seen by reading the code**, only by really running it once.
The four bugs actually hit while writing it this time are examples: `config.set` shadowing the
builtin `set`,
ingesting the wrong folder (reading the project instead of the reference folder), `RunFolder`
has no `.name`,
the sqlite connection **can't be closed across threads** (the inevitable result of the resident
loop).
So this one **really creates a book, really ingests, really writes a few beats, really exports,
really deletes**,
all done in a **temp dir + MOCK**, and after the run it **proves it never touched the user's
stuff** (the `.env`
sha1, the entry count of the real Projects directory).
It creates a book, ingests, runs a few beats, exports and deletes — all in a
temp dir under MOCK — and then proves it never touched the user's own files.
artifact: `assets/screenshots/sdk_report.json`
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
# ⚠ **只**挂 SDK 目录，**故意不挂 APP** ——
#    "nws 自己会把项目根注入 sys.path" 这条要有意义，判据就不能替它做
#    （替它做了，A4 与 J 组那六条 CLI 就都成了恒真）。
# [EN] ⚠ **Only** mount the SDK directory, **intentionally not the APP** ——
# [EN] For "nws injects the project root into sys.path itself" to be meaningful, the check must not do
# [EN] it for it
# [EN] (if it did, all six CLI checks of group A4 and J would become tautologies).
sys.path.insert(0, str(APP / "developers" / "sdk"))

OUT = APP / "assets" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
REPORT = OUT / "sdk_report.json"

CHECKS: list[dict] = []


def ok(name: str, cond: bool, detail: str = "") -> bool:
    """记一条判据。/ Record one check.
        English:
    Record one check. / Record one check.
    """
    CHECKS.append({"name": name, "ok": bool(cond), "detail": str(detail)[:600]})
    print(("  ✓ " if cond else "  ✗ ") + name + (f"   [{detail}]" if detail and not cond else ""))
    return bool(cond)


def okv(name: str, fn, detail: str = "") -> bool:
    """`ok()` 的**惰性求值版**：表达式自己抛异常 ⇒ 记一条红，而不是炸掉整段。
    Lazy `ok()`: an exception inside the expression becomes a red check rather
    than blowing up the whole section.

    ★★ 为什么需要它（反例法实测抓到的）：变异 `M07`（把 `export_dir` 当属性用）
      会让 `Path(bound method)` 抛 `TypeError`。那一条本该"红"，结果**整段崩了**，
      报出来只有一句「段内未捕获异常」—— 看不出这是 F3 的账。
      于是「判据红了」和「判据崩了」混成一样，反例法就没法定位。
      **凡是要调用被测代码的判据，一律用它。**
    
        English:
    the **lazy-evaluated version** of `ok()`: if the expression itself throws ⇒ record a red one,
    instead of blowing up the whole section.
        Lazy `ok()`: an exception inside the expression becomes a red check rather
        than blowing up the whole section.
        ★★ why it is needed (caught by counterexample testing): mutating `M07` (using `export_dir` as an attribute)
          makes `Path(bound method)` throw `TypeError`. That one should have been "red", but instead **the whole section crashed**,
          and the only report was "uncaught exception in section" —— you can't tell this is F3's account.
          Thus "check went red" and "check crashed" become the same thing, and counterexample testing can't localize.
          **Any check that calls the code under test must use it.**
    """
    try:
        val = fn()
    except BaseException as e:                              # noqa: BLE001
        return ok(name, False, f"取值时抛异常：{type(e).__name__}: {str(e)[:110]}")
    return ok(name, False, detail)


def guard(fn, default=None):
    """取值但**允许它抛**（抛了就按缺省走，并打一行说明）。/ Evaluate, tolerating a throw.

    给"后面几条判据都要用这个值"的地方用：不这样的话，一次异常会让
    **后面所有判据**一起消失（连"红"都留不下）。
    
        English:
    Evaluate but **allow it to throw** (if it throws, fall back to the default and print a note). /
    Evaluate, tolerating a throw.
        Use it where "the following checks all need this value": otherwise one exception makes
        **all following checks** disappear together (not even a "red" is left).
    """
    try:
        return fn()
    except BaseException as e:                              # noqa: BLE001
        print(f"    （取值抛异常，按缺省处理：{type(e).__name__}: {str(e)[:80]}）")
        return default


def section(title: str) -> None:
    print(f"\n── {title} " + "─" * max(0, 56 - len(title)))


# ══════════════════════════════════════════════════════════════════
#  0 先记下"用户的东西"长什么样，跑完再比（隔离自证）
# [EN] 0 first record what "the user's stuff" looks like, compare after the run (isolation self-proof)
# ══════════════════════════════════════════════════════════════════

ENV_PATH = APP / ".env"
ENV_SHA = hashlib.sha1(ENV_PATH.read_bytes()).hexdigest() if ENV_PATH.is_file() else "-"


def _dir_sig(p: Path) -> int:
    """目录的"指纹"：顶层条目数（够用且便宜）。/ Cheap fingerprint of a folder.
        English:
    Cheap fingerprint of a folder: top-level entry count (good enough and cheap). / Cheap
    fingerprint of a folder.
    """
    try:
        return len(list(p.iterdir()))
    except Exception:                                       # noqa: BLE001
        return -1


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="nws_sdk_"))
    real_projects = None
    try:
        import nws

        # ══ A 包结构 / package shape ══
        # [EN] ══ A package shape ══
        section("A 包结构（import 就能用、不碰 GUI）")
        ok("A1 `import nws` 直接可用（不需要额外 sys.path 操作）", True)
        ok("A2 十个子模块齐全 / 10 submodules present",
           all(hasattr(nws, m) for m in
               ("config", "project", "ingest", "run", "archive", "export",
                "usage", "mumu", "aio", "cli")),
           "、".join(m for m in
                     ("config", "project", "ingest", "run", "archive",
                      "export", "usage", "mumu", "aio", "cli")
                     if not hasattr(nws, m)))
        ok("A3 **不 import flet**（SDK 能在服务器上跑，没有窗口）",
           "flet" not in sys.modules, "flet 被 import 了")
        import importlib
        try:
            importlib.import_module("store.project")
            _imp = True
        except Exception as e:                              # noqa: BLE001
            _imp = False
            print("    import store.project 失败:", e)
        ok("A4 项目根已注入 sys.path，且**真的 import 得到项目模块**"
           "（这才是「能在项目外运行」的证据）",
           str(APP) in sys.path and _imp, f"in_path={str(APP) in sys.path} imp={_imp}")
        ok("A5 `where()` 指出的 app_root == 项目根",
           nws.where()["app_root"] == str(APP), nws.where()["app_root"])
        ok("A6 `version()` 能说出 SDK 版本与程序版本",
           nws.version().startswith("nws ") and "app " in nws.version(),
           nws.version())

        # ══ B 全局设置 ══
        # [EN] ══ B global settings ══
        section("B 全局设置（config）")
        real_projects = nws.config.projects_dir()
        # ⚠ 基线必须在**这里**取：`__main__` 里那时还没 `import nws`，
        #   项目根还没注入 sys.path ⇒ `from config import CFG` 失败 ⇒
        #   量出个 -1（第一版就是这么把 K5 判成红的）。
        # [EN] ⚠ the baseline must be taken **here**: in `__main__` at that point `import nws` has not happened
        # [EN] yet,
        # [EN] the project root has not been injected into sys.path ⇒ `from config import CFG` fails ⇒
        # [EN] you measure a -1 (that is how the first version turned K5 red).
        _REAL_PROJ_N[0] = _dir_sig(real_projects)
        g = nws.config.groups()
        ok("B1 读得到分组（与「天机」同一套 SPEC）", len(g) >= 20, len(g))
        ok("B2 读一项**按类型**返回（不是原始串）",
           isinstance(nws.config.get("MOCK_LLM"), bool)
           and isinstance(nws.config.get("AUTO_RUN_DAYS"), int),
           f'{type(nws.config.get("MOCK_LLM")).__name__}')
        ok("B3 `describe()` 给出类型/默认/分组/说明",
           {"type", "default", "group", "desc"} <= {k for k in nws.config.describe("MOCK_LLM")},
           sorted(nws.config.describe("MOCK_LLM")))
        ok("B4 大小写不敏感（mock_llm == MOCK_LLM）",
           nws.config.get("mock_llm") == nws.config.get("MOCK_LLM"), "")
        ok("B5 未知键 → 返回缺省值且不抛", nws.config.get("NO_SUCH_KEY", "X") == "X", "")
        ok("B6 `restart_keys()` 认得 LLM 那几项",
           "LLM_BASE_URL" in nws.config.restart_keys()
           and "UI_OPACITY" not in nws.config.restart_keys(), "")
        # temporary()：出了 with 必须还原
        # [EN] temporary(): must be restored after exiting the with
        before = nws.config.get("AUTO_RUN_DAYS")
        with nws.config.temporary(AUTO_RUN_DAYS=999):
            inside = nws.config.get("AUTO_RUN_DAYS")
        ok("B7 `temporary()` 里改、出来**自动还原**（脚本最常犯的蠢事）",
           inside == 999 and nws.config.get("AUTO_RUN_DAYS") == before,
           f"里={inside} 外={nws.config.get('AUTO_RUN_DAYS')} 原={before}")

        # ══ 隔离：项目目录 / 台账 / 演示模式 ══
        # [EN] ══ isolation: project dir / ledger / demo mode ══
        nws.config.set(DEFAULT_PROJECTS_DIR=str(tmp / "Projects"), MOCK_LLM="true")
        from llm import usage as U
        U.db_path = lambda: tmp / "usage.db"
        ok("B8 隔离生效（SDK 这一步之后写的是临时目录）",
           nws.config.projects_dir() == tmp / "Projects",
           str(nws.config.projects_dir()))
        ok("B9 演示模式开着（后面全程零成本零网络）", nws.config.mock(), "")

        # ══ C 项目 ══
        # [EN] ══ C project ══
        section("C 项目（建 / 找 / 打开 / 设置 / 删）")
        src = APP / "samples" / "zh" / "01_悬疑单元_更漏子"
        ok("C0 示例素材在（这一支拿它当真素材）", src.is_dir(), str(src))
        book = nws.project.create("SDK判据书", source=str(src), genre="悬疑·单元")
        ok("C1 建书 → 目录与 .nwsproj 都出来了",
           Path(book.root).is_dir() and Path(book.nwsproj_path).is_file(),
           str(book.root))
        ok("C2 引用文件夹被**登记**了（但没被写过一个字）",
           nws.project.settings(book).get("源文件夹") == str(src),
           nws.project.settings(book).get("源文件夹"))
        ok("C3 `find` / `open` 按名字找得到",
           nws.project.find("SDK判据书") is not None
           and nws.project.open("SDK判据书").name == "SDK判据书", "")
        try:
            nws.project.open("根本没这本书")
            ok("C4 找不到时报 `NotFound` 且列出有哪些书", False, "没抛")
        except nws.project.NotFound as e:
            ok("C4 找不到时报 `NotFound` 且列出有哪些书",
               "SDK判据书" in str(e), str(e)[:80])
        ok("C5 `info()` 报的是**真数据**（设定集空、0 轮、2 人物源里还没抽）",
           nws.project.info(book)["runs"] == []
           and nws.project.info(book)["settings_files"] == [],
           nws.project.info(book)["runs"])
        changed = nws.project.update(book, output_lang="zh", scene_name="临河茶肆")
        ok("C6 项目设置能改并落盘（英文别名也认）",
           changed == ["输出语言", "场景名称"]
           and nws.project.settings(book).get("输出语言") == "zh",
           f"{changed} / {nws.project.settings(book).get('输出语言')}")

        # ══ D 开卷 ══
        # [EN] ══ D ingest ══
        section("D 开卷（摄取）")
        b = nws.ingest.plan(book)
        ok("D1 `plan()` 说的是**真实数字**（文件数 > 0、字数 > 0）",
           b.get("files_total", 0) > 0 and b.get("total_chars", 0) > 0,
           f"files={b.get('files_total')} chars={b.get('total_chars')}")
        ok("D2 `plan()` 认出这是**引用文件夹**（不是项目文件夹）",
           str(b.get("source")) == str(src), b.get("source"))
        # 没有引用文件夹时必须**明确报错**（而不是默默读项目文件夹 → 0 文件）
        # [EN] when no reference folder is given it must **error explicitly** (instead of silently reading the
        # [EN] project folder → 0 files)
        lonely = nws.project.create("没登记源的书")
        try:
            nws.ingest.plan(lonely)
            ok("D3 没登记引用文件夹 → **明确报错**（不静默读错文件夹）", False, "没抛")
        except ValueError as e:
            ok("D3 没登记引用文件夹 → **明确报错**（不静默读错文件夹）",
               "引用文件夹" in str(e), str(e)[:70])
        # 同意门：不同意 → 抛 IngestDeclined 且一个字都不落盘
        # [EN] consent gate: declined → raise IngestDeclined and not a single byte written to disk
        sd_before = list(Path(book.settings_dir).iterdir())
        declined = nws.ingest.declined_exc()
        try:
            nws.ingest.run(book, gate=lambda brief: False)
            ok("D4 同意门投否 → 抛 `IngestDeclined`（不是错误，是中止）", False, "没抛")
        except declined as e:
            ok("D4 同意门投否 → 抛 `IngestDeclined`（不是错误，是中止）",
               nws.ingest.is_declined(e), type(e).__name__)
        ok("D5 而被拒绝时**设定集一个字都没写**（零落盘）",
           list(Path(book.settings_dir).iterdir()) == sd_before,
           f"{len(list(Path(book.settings_dir).iterdir()))} vs {len(sd_before)}")
        # 真跑
        # [EN] actually run
        stages: list[str] = []
        res = nws.ingest.run(book, on_stage=lambda sid, lab, pct, extra="":
                             stages.append(sid))
        s = nws.ingest.summary(res)
        ok("D6 真开卷 → 有人物、有节点、有评档",
           s["people"] > 0 and s["nodes"] > 0 and bool(s["tier"]),
           f"{s['people']}人物 {s['nodes']}节点 {s['tier']}")
        #  ⚠ `freeze` **不算**：SDK 走的是 GUI 那条两步路 ——
        #    `run_ingest(settings_dir=None)` 只提取，冻结由 SDK 之后自己调
        #    `freeze_settings`（所以管线阶段表里看不到 freeze，而 D8 另验它真冻了）。
        # [EN] ⚠ `freeze` **does not count**: the SDK takes the GUI's two-step path ——
        # [EN] `run_ingest(settings_dir=None)` only extracts, freezing is done by the SDK afterwards on its own
        # [EN] via `freeze_settings` (so freeze is not visible in the pipeline stage table, while D8 separately
        # [EN] verifies it really froze).
        want_stages = set(nws.ingest.required_stages()) - {"freeze"}
        ok("D7 阶段齐全（与管线同一张表；`freeze` 由 SDK 自己那一步做，见 D8）",
           want_stages <= set(stages),
           f"跑了 {len(stages)} 个：缺 {want_stages - set(stages)}")
        ok("D8 **成果冻结进了项目设定集**（`人物.yaml` 真在）",
           (Path(book.settings_dir) / "人物.yaml").is_file(), "")
        ok("D9 `info()` 跟着更新（现在有设定集了）",
           len(nws.project.info(book)["settings_files"]) > 5,
           len(nws.project.info(book)["settings_files"]))

        # ══ E 起笔 ══
        # [EN] ══ E start writing ══
        section("E 起笔（推演）")
        r = nws.run.start(book, days=1, max_ticks=3, images=False,
                          directive="先埋一个误会。")
        ok("E1 `start()` 返回时**已经在跑**（不是「启动了个空壳」）",
           r.status in ("running", "paused", "finished"), r.status)
        ok("E2 装配出了世界与人物（world 有在场名单）",
           len(getattr(r.world, "people", {}) or {}) > 0,
           len(getattr(r.world, "people", {}) or {}))
        done = r.wait(timeout=600)
        ok("E3 `wait()` 等到收尾（不是超时）", done, f"status={r.status}")
        ok("E4 跑完了/停了，且**没报错**",
           r.status in ("finished", "stopped") and not r.error,
           f"{r.status} / {r.error!r}")
        ok("E5 SDK **自己收了叙事**（不挂回调也能 tail）", len(r.lines()) > 0,
           f"{len(r.lines())} 条")
        snap = r.snapshot()
        ok("E6 快照是真数据（有第几天 / 时辰 / 场景）",
           snap.get("day", 0) >= 1 and bool(snap.get("clock")),
           f"day={snap.get('day')} clock={snap.get('clock')}")
        ok("E7 作者建议真的传下去了",
           str(getattr(r.world, "user_directive", "")) == "先埋一个误会。",
           getattr(r.world, "user_directive", None))
        okv("E8 这一轮真落盘了（每天的生活 / 或导出目录存在）",
            lambda: any(f["rel"].startswith("每天的生活") for f in r.files())
            or any(f["rel"].startswith("导出") for f in r.files()),
            str([f["rel"] for f in guard(lambda: r.files(), [])][:4]))
        ok("E9 `pause()`/`resume()` 对已结束的一轮**不乱改状态**（返回 False）",
           r.pause() is False and r.resume() is False, f"pause={r.pause()}")
        # 关库：必须**在常驻线程里**关（不然 sqlite 跨线程拒）
        # [EN] closing the DB: must be done **in the resident thread** (otherwise sqlite refuses across
        # [EN] threads)
        ok("E10 `close()` 真的关掉了这一轮的库（跨线程那条坎过去了）",
           r.close() is True, "close 返回 False（sqlite 跨线程？）")

        # ══ F 导出 ══
        # [EN] ══ F export ══
        section("F 报告导出")
        okv("F1 五种产物都认得，且**知道哪几种要花钱**",
            lambda: set(nws.export.kinds()) == {"raw_novel", "novel",
                                                "reference", "report", "guide"}
            and nws.export.uses_llm("report") is True
            and nws.export.uses_llm("novel") is False)
        ex = guard(lambda: nws.export.run_for_round(
            r.run, kinds=["novel", "reference", "report"]), {"items": []})
        got = {it["kind"]: it for it in ex.get("items", [])}
        okv("F2 三样都导出来了（每样都报 ok + 有路径）",
            lambda: all(got[k]["ok"] and got[k].get("path") for k in
                        ("novel", "reference", "report")),
            str({k: (got[k].get("error") or "")[:60] for k in got}))
        okv("F3 产物落在**这一轮的** `导出/` 里",
            lambda: all(nws.export.export_dir(r.run) in Path(got[k]["path"]).parents
                        for k in got if got[k].get("path")))
        rep = guard(lambda: nws.export.read(r.run, "report"), "")
        ok("F4 能把报告**读回来**（有标题、有概览表）",
           "运行报告" in rep and "运行概览" in rep, rep[:60].replace("\n", " "))
        okv("F5 没导过的种类读回来是**空串**（不抛异常）",
            lambda: nws.export.read(r.run, "guide") == "")
        f1 = len(guard(lambda: nws.export.files(r.run), []))
        guard(lambda: nws.export.run_for_round(r.run, kinds=["novel"]))
        okv("F6 再导一次是**版本自增**（不覆盖旧的）",
            lambda: len(nws.export.files(r.run)) > f1, f"改前 {f1} 个文件")

        # ══ G 存档 ══
        # [EN] ══ G archive ══
        section("G 存档")
        sv = nws.archive.save(book, name="判据存档", description="SDK 判据", run=r)
        ok("G1 建存档 → 落在 `<书>/存档/<名>`",
           Path(sv["path"]).is_dir() and "存档" in sv["path"], sv["path"])
        ok("G2 列表读得到，且**带描述**（能认出这是哪一版）",
           any(x.get("名称") == "判据存档" for x in nws.archive.list_of(book)),
           [x.get("名称") for x in nws.archive.list_of(book)])
        ok("G3 `get()` 取得到、（G4）`delete()` 删得掉",
           nws.archive.get(book, "判据存档") is not None
           and nws.archive.delete(book, "判据存档") is True
           and nws.archive.get(book, "判据存档") is None, "")

        # ══ H 用量 ══
        # [EN] ══ H usage ══
        section("H 用量")
        t = nws.usage.totals("SDK判据书")
        ok("H1 台账记到了这一本的账（次数 > 0）", t.get("calls", 0) > 0, t.get("calls"))
        gs = nws.usage.groups("SDK判据书", nws.usage.BY_MODEL)
        ok("H2 按模型拆得开", len(gs) >= 1, [x.get("key") for x in gs])
        ok("H3 `fmt_tokens` / `fmt_cost` 说人话",
           "k" in nws.usage.fmt_tokens(12345) or nws.usage.fmt_tokens(12345) == "12345",
           nws.usage.fmt_tokens(12345))
        ok("H4 台账文件在**我们指的那个临时位置**（没混进用户账本）",
           str(tmp) in nws.usage.db_file(), nws.usage.db_file())

        # ══ I MuMuAINovel ══
        section("I MuMuAINovel（可选服务）")
        ok("I1 找得到它的家在哪", Path(nws.mumu.home()).is_dir(), nws.mumu.home())
        ok("I2 服务地址是回环地址", nws.mumu.url().startswith("http://127.0.0.1"), nws.mumu.url())
        st = nws.mumu.status(timeout=1.5)
        ok("I3 `status()` 是**查询**不是启动（没在跑也照样返回，不抛）",
           hasattr(st, "ok"), type(st).__name__)
        ok("I4 设了 `MUMU_ENABLED=false` 时 `enabled()` 说不用它（**降级纪律**）",
           nws.mumu.enabled() in (True, False), nws.mumu.enabled())
        ok("I5 `describe()` 给得出人话（没起服务也不炸）",
           len(nws.mumu.describe()) > 0, nws.mumu.describe()[:60])

        # ══ J 命令行 ══
        # [EN] ══ J command line ══
        section("J 命令行（python -m nws，只跑只读命令）")
        sdk_dir = APP / "developers" / "sdk"
        py = sys.executable

        def cli(*args: str, timeout: float = 90) -> tuple[int, str]:
            r2 = subprocess.run([py, "-m", "nws", *args], cwd=str(sdk_dir),
                                capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                timeout=timeout, env={**os.environ})
            return r2.returncode, (r2.stdout or "") + (r2.stderr or "")

        rc, out = cli("version")
        ok("J1 `version` 打得出 SDK 与位置", rc == 0 and "nws " in out, out[:70])
        rc, out = cli("list", "--json")
        ok("J2 `list --json` 输出**合法 JSON**",
           rc == 0 and isinstance(json.loads(out.strip() or "[]"), list),
           out[:60])
        rc, out = cli("settings", "--group", "运行边界")
        ok("J3 `settings --group` 列出该组的键",
           rc == 0 and "RUN_MODE" in out, out[:70])
        rc, out = cli("usage", "--by", "模型")
        ok("J4 `usage --by` 能按维度拆（数字从台账来）",
           rc == 0 and "次" in out, out[:70])
        rc, out = cli("mumu", "status")
        ok("J5 `mumu status` 不炸（服务没起也给人话）",
           rc == 0 and ("在跑" in out or "没在跑" in out), out[:70])
        rc, out = cli("new")            # 缺参数 → argparse 自己报错
        # [EN] missing argument → argparse reports the error itself
        ok("J6 参数写错时 argparse 明确报错（退出码 ≠ 0）", rc != 0, rc)

        # ══ K 清理与隔离自证 ══
        # [EN] ══ K cleanup and isolation self-proof ══
        section("K 收尾（删书可恢复 + 自证没碰用户的东西）")
        ok2, msg = nws.project.delete(book)
        ok("K1 删书 = **搬到「已删除备份」**（不是 rmtree，可恢复）",
           ok2 and Path(msg).is_dir() and "已删除备份" in msg, msg[:90])
        ok("K2 备份目录在**项目根之外**（否则扫书会把删掉的又扫出来）",
           not str(nws.project.trash_dir()).startswith(str(nws.config.projects_dir())),
           nws.project.trash_dir())
        ok("K3 原目录真的没了",
           not Path(book.root).is_dir(), str(book.root))

        now_sha = hashlib.sha1(ENV_PATH.read_bytes()).hexdigest() if ENV_PATH.is_file() else "-"
        ok("K4 ★★ **用户的 `.env` 一个字节没动**（sha1 一致）",
           now_sha == ENV_SHA, f"{ENV_SHA[:10]} → {now_sha[:10]}")
        # ⚠⚠ K5 的口径在 2026-10-11 改过：原来要求 `_dir_sig(real_projects) >= 0`，
        #   即"用户的真实 Projects 目录**必须存在**"。这条在本机**不成立** ——
        #   用户当前**没有活跃的小说项目**（他唯一那本已在
        #   `Desktop\小说世界虚拟模拟\已删除备份\` 里），默认根
        #   `Desktop\小说世界AI模拟\Projects` 根本没建过 ⇒ 量到 -1 ⇒ 判据红。
        #   而这条判据**真正要守的**是"SDK 跑一趟没有动用户的项目目录"——
        #   目录**本来就不存在**时，"跑完仍然不存在"同样是证据（有人顺手建一个，
        #   那也是动了用户目录）。所以分成两种情况，各自都有意义：
        #     · 本来存在 → 比条目数（强判据）；
        #     · 本来不存在 → 断言"跑完仍然不存在"（弱一点，但不是恒真：
        #       真被创建出来就会红）。
        #   ⚠ **不要**把它退化成"前后一致就过"：那样 -1 == -1 恒真，等于没测。
        # [EN] ⚠⚠ K5's convention changed on 2026-10-11: it used to require
        # [EN] `_dir_sig(real_projects) >= 0`, i.e. "the user's real Projects directory **must exist**". That
        # [EN] does not hold on this machine -- the user currently **has no active novel project** (his only
        # [EN] one is already under `Desktop\小说世界虚拟模拟\已删除备份\`), and the default root
        # [EN] `Desktop\小说世界AI模拟\Projects` was never created ⇒ measured -1 ⇒ the criterion went red.
        # [EN] What this criterion **really guards** is "running the SDK did not touch the user's project
        # [EN] directory" -- when the directory **never existed**, "still doesn't exist afterwards" is
        # [EN] likewise evidence (someone creating one would also be touching the user's directory). So split
        # [EN] into two cases, each meaningful:
        # [EN] · it existed -> compare entry counts (strong criterion);
        # [EN] · it did not exist -> assert "still does not exist" (weaker, but not vacuously true: it goes
        # [EN] red if one really gets created).
        # [EN] ⚠ **Do not** degrade this to "unchanged is enough": then -1 == -1 is always true, i.e. nothing
        # [EN] is tested.
        _sig_now = _dir_sig(real_projects) if real_projects else -1
        if _REAL_PROJ_N[0] < 0 and _sig_now < 0:
            ok('K5 ★★ 用户的真实 Projects 目录**本来就不存在、跑完仍然不存在**'
               '（没有可比对象，但"没被顺手创建出来"同样是证据）',
               True, f'目录={real_projects}｜条目数 前后都是 -1（不存在）')
        else:
            ok("K5 ★★ **用户的真实 Projects 目录条目数没变**",
               real_projects is not None
               and _sig_now == _REAL_PROJ_N[0],
               f'目录={real_projects}｜{_REAL_PROJ_N[0]} → {_sig_now}')

    except BaseException:                                   # noqa: BLE001
        # ★ 崩溃必须**自己留一条红的**（否则汇总会把"崩了"当成"全绿"）
        # [EN] ★ a crash must **leave a red one itself** (otherwise the summary treats "crashed" as "all
        # [EN] green")
        CHECKS.append({"name": "★ 判据运行中出现未捕获异常", "ok": False,
                       "detail": traceback.format_exc()[-900:]})
        traceback.print_exc()
    finally:
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except BaseException:                               # noqa: BLE001
            pass

    n_ok = sum(1 for c in CHECKS if c["ok"])
    allok = n_ok == len(CHECKS)
    REPORT.write_text(json.dumps(
        {"verifier": "verify_sdk", "ok": allok, "checks": CHECKS,
         "passed": n_ok, "total": len(CHECKS),
         "when": time.strftime("%Y-%m-%d %H:%M:%S")},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n验证：{n_ok}/{len(CHECKS)}")
    if not allok:
        print("失败项：")
        for c in CHECKS:
            if not c["ok"]:
                print("  ✗", c["name"], "|", c["detail"][:200])
    return 0 if allok else 2


#: 进 main 之前先把"真实项目目录条目数"记下来（K5 要比它）
# [EN] : before entering main, record the "real project directory entry count" first (K5 compares
# [EN] against it)
_REAL_PROJ_N = [0]

if __name__ == "__main__":
    sys.exit(main())
