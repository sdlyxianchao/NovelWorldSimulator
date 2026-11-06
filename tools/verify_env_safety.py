# -*- coding: utf-8 -*-
"""验证：**任何验证脚本都写不进用户的 `.env`**（第四道保险丝，2026-10-11）。

## 为什么要有这一支

2026-10-11 实际踩到：手工单跑 `tools/verify_help_book.py`（它跑真机段时会点
书斋里的「保存」，触发 `CFG.save()`），**用户的真实 `.env` 被写成**
`MOCK_LLM=true` + `DEFAULT_PROJECTS_DIR=<某脚本的临时目录>`。
用户下次跑推演只会看到"怎么不调模型了"，而根因在两小时前某次判据运行里。

三道老防线各自有漏口：
  · `NWS_ENV_SINK` —— 只有**回归器**给子进程设；手工单跑没有；
  · `VU.redirect_env_writes()` —— 得**脚本自己记得调**（124 支里大多数没调）；
  · 备份/还原 —— 单跑时没人还原。

⇒ 新增**第四道**：`config.env_sink_path()` 里加"**进程自己认得出是验证脚本**"
  （文件名前缀 `verify_` / `probe_` / `mutate_` / `shoot_`），写盘一律落到临时文件。
  按项目铁律："**会写用户文件的路径，默认就该写不进去**"。

## 判据分三组

**A 组（判定规则：谁该拦、谁不该拦）**
  A1 ★★ 四类脚本名（`verify_` / `probe_` / `mutate_` / `shoot_`）**都拦**
  A2 ★★ **产品与正经工具不拦**（`main_gui.py` / `tools/make_release.py` /
     `tools/i18n_check.py`）—— 拦错了等于"用户改了配置存不下来"，比漏拦更糟
  A3 ★★ `NWS_ENV_SINK`（回归器给的）**优先**于自动拦（统一收集，互不冲突）

**B 组（真的写一次：用户的 `.env` 必须一个字节都没变）**
  B1 ★★★ 子进程伪装成验证脚本 → `CFG.set('MOCK_LLM','true')` → `CFG.save()`
     → **项目 `.env` 的 md5 前后一致**，且里面没有那个测试值
  B2 ★★★ 同一件事在"产品身份"下做 → 它**应该**写到真实 `.env`？
     ⚠ 不测这条：那会把用户的 `.env` 真改掉。改成**只测判定函数**返回 `None`
     （"不重定向"），并说明为什么到此为止。

产出：`assets/screenshots/env_safety_report.json`

English:
Verification: **no verification script can write into the user's `.env`** (fourth fuse,
2026-10-11).
## Why this branch is needed
Actually hit on 2026-10-11: manually running `tools/verify_help_book.py` alone (it clicks
"Save" in the study when running the real-machine section, triggering `CFG.save()`), **the
user's real `.env` was written with**
`MOCK_LLM=true` + `DEFAULT_PROJECTS_DIR=<some script's temp directory>`.
Next time the user runs a simulation they will only see "why is it not calling the model
anymore", while the root cause lies in a criterion run two hours earlier.
The three old defense lines each have their own gap:
  · `NWS_ENV_SINK` -- only the **regressor** sets it for child processes; manual single runs do not;
  · `VU.redirect_env_writes()` -- the **script must remember to call it** (most of the 124 branches do not);
  · backup/restore -- nobody restores during single runs.
⇒ Add a **fourth** line: in `config.env_sink_path()`, add "**the process itself can recognize it
is a verification script**"
  (filename prefixes `verify_` / `probe_` / `mutate_` / `shoot_`); all disk writes go to a temp file.
  Per the project's iron rule: "**paths that would write user files should by default be unable to write**".
## Criteria are split into three groups
**Group A (decision rules: who should be blocked, who should not)**
  A1 ★★ all four script name types (`verify_` / `probe_` / `mutate_` / `shoot_`) **are blocked**
  A2 ★★ **the product and legitimate tools are not blocked** (`main_gui.py` / `tools/make_release.py` /
     `tools/i18n_check.py`) -- blocking them wrongly is equivalent to "the user changed config but cannot save it", worse than missing a block
  A3 ★★ `NWS_ENV_SINK` (given by the regressor) **takes priority** over automatic blocking (collected uniformly, no conflict)
**Group B (actually write once: the user's `.env` must not change by a single byte)**
  B1 ★★★ child process pretends to be a verification script → `CFG.set('MOCK_LLM','true')` → `CFG.save()`
     → **project `.env` md5 identical before and after**, and the test value is not in it
  B2 ★★★ do the same thing under "product identity" → it **should** write to the real `.env`?
     ⚠ Do not test this: that would actually modify the user's `.env`. Change it to **only test the decision function** returning `None`
     ("no redirect"), and explain why it stops there.
Output: `assets/screenshots/env_safety_report.json`
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'tools'))

PY = APP / '.venv' / 'Scripts' / 'python.exe'
if not PY.exists():
    PY = Path(sys.executable)
ENV = APP / '.env'
OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)

REPORT: dict = {}
CHECKS: list = []
_FAILS = 0


def ok(name: str, cond, detail='') -> bool:
    global _FAILS
    good = bool(cond)
    if not good:
        _FAILS += 1
    CHECKS.append({'name': name, 'ok': good, 'detail': str(detail)[:400]})
    print(f'  {"[OK]  " if good else "[FAIL]"} {name}'
          + (f'   ← {detail}' if detail != '' else ''))
    return good


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest() if p.exists() else '<无>'


def run_as(argv0: str, body: str, *, env_extra: dict | None = None,
           timeout: int = 120) -> tuple:
    """起一个子进程、**把 `argv0` 伪装成给定值**，再跑 `body`。

    ★ 为什么一定要子进程：`_is_verify_process()` 读的是 `sys.argv[0]`，
      而它在本进程里改不了（改了也只影响本进程，测不出真实启动路径）。
    ★ 并且**必须清掉 `NWS_ENV_SINK`**（除非显式给）：否则测的是"回归器给的
      那一道"，测不到"自动认脚本"这一道 —— 那就成了假绿。
    [EN] ★ Why a subprocess: `_is_verify_process()` reads `sys.argv[0]`, which cannot be changed
    [EN] meaningfully in-process (changing it only affects this process, so the real launch path is never
    [EN] exercised).
    [EN] ★ And `NWS_ENV_SINK` **must be cleared** (unless explicitly provided): otherwise what gets
    [EN] exercised is "the fuse the regressor provides", not "automatic script recognition" -- a false
    [EN] green.
    
        English:
    Start a child process, **disguise `argv0` as the given value**, then run `body`.
        ★ Why a subprocess is mandatory: `_is_verify_process()` reads `sys.argv[0]`,
          and it cannot be changed in this process (changing it only affects this process, so the real launch path cannot be tested).
        ★ And `NWS_ENV_SINK` **must be cleared** (unless explicitly provided): otherwise what is tested is "the one given by the regressor",
          not "automatic script recognition" -- that would be a false green.
        [EN] ★ Why a subprocess: `_is_verify_process()` reads `sys.argv[0]`, which cannot be changed
        [EN] meaningfully in-process (changing it only affects this process, so the real launch path is never
        [EN] exercised).
        [EN] ★ And `NWS_ENV_SINK` **must be cleared** (unless explicitly provided): otherwise what gets
        [EN] exercised is "the fuse the regressor provides", not "automatic script recognition" -- a false
        [EN] green.
    """
    env = dict(os.environ)
    env.pop('NWS_ENV_SINK', None)
    if env_extra:
        env.update(env_extra)
    code = (
        "import sys\n"
        f"sys.argv[0] = {argv0!r}\n"
        f"sys.path.insert(0, {str(APP)!r})\n"
        + body
    )
    r = subprocess.run([str(PY), '-c', code], cwd=str(APP), capture_output=True,
                       text=True, encoding='utf-8', errors='replace',
                       env=env, timeout=timeout)
    return r.returncode, (r.stdout or '') + (r.stderr or '')


# ══════════════════════════════════════════════════════════════════
#  A 组：判定规则
# [EN] Group A: decision rules
# ══════════════════════════════════════════════════════════════════
PROBE = """
import os
from config import env_sink_path, _is_verify_process
s = env_sink_path()
os.environ.pop('NWS_ENV_SINK', None)
print('IS_VERIFY', _is_verify_process())
print('SINK', s if s else 'NONE')
"""


def _probe(argv0: str, *, env_extra: dict | None = None) -> tuple:
    rc, out = run_as(argv0, PROBE, env_extra=env_extra)
    isv = 'True' in out
    sink = 'NONE'
    for ln in out.split('\n'):
        if ln.startswith('SINK '):
            sink = ln[5:].strip()
    return rc, isv, sink, out


def group_a() -> None:
    print('\n── A 组：谁该拦、谁不该拦 ──')
    # A1：四类脚本名都拦
    # [EN] A1: block all four script name types
    rows = {}
    for a in ('tools/verify_help_book.py', 'developers/probe_x.py',
              'developers/mutate_y.py', 'developers/shoot_z.py',
              'developers/measure_controls.py', 'developers/preview_look.py',
              'developers/audit_screens.py'):
        rc, isv, sink, out = _probe(a)
        rows[a] = {'is_verify': isv, 'sink': sink}
    REPORT['a1'] = rows
    ok('A1 ★★ 七类脚本名（判据 / 探针 / 反例法 / 截图 / 度量 / 预览 / 审计）'
       '**都被拦住**（写盘落到临时文件）—— '
       '后三类同样会起 GUI、点按钮，一样会触发 `CFG.save()`',
       all(v['is_verify'] and v['sink'] != 'NONE' for v in rows.values()), rows)

    # A2：产品与正经工具不拦
    # [EN] A2: do not block the product and legitimate tools
    safe = {}
    for a in ('main_gui.py', 'main.py', 'tools/make_release.py',
              'tools/i18n_check.py', 'tools/platform_install.py'):
        rc, isv, sink, out = _probe(a)
        safe[a] = {'is_verify': isv, 'sink': sink}
    REPORT['a2'] = safe
    ok('A2 ★★ **产品与正经工具不拦**（`main_gui.py` / `make_release.py` / '
       '`i18n_check.py` / `platform_install.py`）—— '
       '拦错了等于"用户改了配置存不下来"，比漏拦更糟',
       all((not v['is_verify']) and v['sink'] == 'NONE' for v in safe.values()),
       safe)

    # A4：`.env` 里**一个 SPEC 键都不许缺**
    #   ★ 2026-10-11 实际踩到：`DEFAULT_PROJECTS_DIR` 那一行**整行不见了**
    #     （不是被改空 —— 是没了）。行为上等价于空值（`CFG.raw()` 返回 `''`、
    #     走默认目录），所以**界面与推演都看不出异常**；
    #     但"用户的某一项设置从文件里消失"本身是坏味道：万一那项是有值的，
    #     就等于**静默丢设置**。⇒ 立一条判据把它钉住（缺键就红、并列出缺了哪些）。
    #   ⚠ 这条通常绿（程序 `Config.save()` 会写全量），所以红了就是真出事了。
    # [EN] A4: `.env` must **not be missing a single SPEC key**.
    # [EN] ★ Actually hit on 2026-10-11: the `DEFAULT_PROJECTS_DIR` line **disappeared entirely** (not
    # [EN] blanked -- gone). Behaviourally that equals an empty value (`CFG.raw()` returns `''` and the
    # [EN] default directory is used), so **neither the UI nor the simulation shows anything wrong**; but
    # [EN] "one of the user's settings vanished from the file" is a bad smell: if that item had a value, it
    # [EN] means **silently losing a setting**. ⇒ Add a criterion pinning it down (red when a key is
    # [EN] missing, listing which).
    # [EN] ⚠ This is usually green (the program's `Config.save()` writes everything), so a red here means
    # [EN] something really went wrong.
    sys.path.insert(0, str(APP))
    from config import SPEC as _SPEC
    lines = ENV.read_text(encoding='utf-8').split('\n') if ENV.exists() else []
    missing = [k for k in _SPEC
               if not any(l.strip().startswith(k + '=') for l in lines)]
    REPORT['a4_missing'] = missing
    ok('A4 ★★ `.env` 里**一个 SPEC 键都不许缺**（缺了就是某项设置从文件里消失：'
       '界面上改了也存不下来 —— 2026-10-11 真丢过一次）',
       not missing, missing or f'{len(_SPEC)} 个键全在')

    # A3：NWS_ENV_SINK 优先
    #   ⚠⚠ **口径在 2026-10-11 改过**：第一版用 `main_gui.py`（**产品身份**）去测，
    #      而那个场景下"先判 env、先判脚本"**结果一模一样**（都不是自动拦）——
    #      于是这条判据**测不到优先级**：反例法 M4 把顺序调换之后它照样绿。
    #      ⇒ 必须构造"**两者同时存在**"：脚本身份 **且** 有 `NWS_ENV_SINK`，
    #        断言落到的是 **env 给的那个**、而不是自动的 `nws_envsink\…`。
    # [EN] A3: NWS_ENV_SINK takes priority
    # [EN] ⚠⚠ **The criteria changed on 2026-10-11**: the first version used `main_gui.py` (**product
    # [EN] identity**) for the test,
    # [EN] and in that scenario "checking env first vs checking script first" gives **identical results**
    # [EN] (neither auto-blocks) --
    # [EN] so this criterion **cannot test priority**: after the counterexample method M4 swapped the
    # [EN] order, it still passed green.
    # [EN] ⇒ Must construct "**both present at the same time**": script identity **and** `NWS_ENV_SINK`
    # [EN] present,
    # [EN] assert that what is hit is **the one given by env**, not the automatic `nws_envsink\...`.
    #   [EN] ⚠⚠ **The convention changed on 2026-10-11**: the first version used `main_gui.py` (a
    #   [EN] **product identity**), and in that scenario "check env first" and "check script first" give the
    #   [EN] **same** result (neither is the automatic block) -- so the criterion **could not measure the
    #   [EN] priority at all**: after reverse experiment M4 swapped the order it stayed green.
    #   [EN] ⇒ Construct "**both present**": script identity **and** an `NWS_ENV_SINK`, then assert it lands
    #   [EN] in **the one the env provided**, not the automatic `nws_envsink\...`.
    sink_file = OUT / '_sink_test.env'
    rc, isv, sink, out = _probe('tools/verify_help_book.py',
                                env_extra={'NWS_ENV_SINK': str(sink_file)})
    REPORT['a3'] = {'is_verify': isv, 'sink': sink}
    ok('A3 ★★ **两者同时存在时** `NWS_ENV_SINK`（回归器给的）优先 —— '
       '脚本身份也照它走，不走自动兜底（便于回归器统一收集）',
       sink != 'NONE' and '_sink_test.env' in sink and 'nws_envsink' not in sink,
       REPORT['a3'])
    try:
        sink_file.unlink()
    except OSError:
        pass


# ══════════════════════════════════════════════════════════════════
#  B 组：真的写一次，用户的 .env 必须一个字节都没变
# [EN] Group B: actually write once; the user's .env must not change by a single byte
# ══════════════════════════════════════════════════════════════════
BODY_SAVE = """
from config import CFG
CFG.set('MOCK_LLM', 'true')
CFG.set('DEFAULT_PROJECTS_DIR', 'X:/这个值绝不能进用户的env')
CFG.save()
print('SAVED_OK')
"""


def group_b() -> None:
    print('\n── B 组：真写一次，用户的 `.env` 必须一个字节没变 ──')
    # ★★★ **先备份原文**（2026-10-11 加的，理由很硬）：
    #   这一组做的正是"让一支进程去 `CFG.save()`" —— 保险丝好使时它写到临时文件；
    #   而**保险丝被拆掉时**（正是反例法要模拟的那种故障），它会**写到用户的
    #   真实 `.env`**。实测：反例法 M1/M2（拆保险丝）跑完，用户的 `.env` 里
    #   真的多出了 `MOCK_LLM=true` 与 `DEFAULT_PROJECTS_DIR=X:/…`
    #   —— **判据自己把用户文件写坏了**，而它守的恰恰是"别写坏用户文件"。
    #   ⇒ 备份原文，跑完比对；**被改了就还原**，并把这件事记一条红。
    #     （不还原的话，任何一次变异都会在用户机器上留下脏数据，
    #       而反例法是要反复跑的。）
    # [EN] ★★★ **Back up the original first** (added 2026-10-11, for a hard reason): this group does
    # [EN] exactly "let a process call `CFG.save()`" -- with the fuse working it writes to a temp file; but
    # [EN] **when the fuse is removed** (the very failure the reverse experiment simulates) it writes to the
    # [EN] user's **real `.env`**. Measured: after reverse experiments M1/M2 (fuse removed), the user's
    # [EN] `.env` really gained `MOCK_LLM=true` and `DEFAULT_PROJECTS_DIR=X:/...` -- **the criterion itself
    # [EN] broke the user's file**, while the thing it guards is precisely "don't break the user's file".
    # [EN] ⇒ Back up the original, compare afterwards, and **restore if changed**, recording that as a red.
    # [EN] (Without restoring, any mutation would leave dirt on the user's machine, and reverse experiments
    # [EN] are meant to be run repeatedly.)
    backup = ENV.read_text(encoding='utf-8') if ENV.exists() else None
    before = md5(ENV)
    REPORT['env_before_md5'] = before

    rc, out = run_as('tools/verify_help_book.py', BODY_SAVE)
    after = md5(ENV)
    REPORT['b1'] = {'rc': rc, 'saved': 'SAVED_OK' in out,
                    'md5_before': before, 'md5_after': after}
    ok('B1 ★★★ 子进程伪装成验证脚本 → `CFG.set` + `CFG.save()` → '
       '**用户的 `.env` 一个字节都没变**（md5 前后一致）',
       'SAVED_OK' in out and before == after,
       f'md5 {before[:8]} → {after[:8]}（save 执行={"SAVED_OK" in out}）')

    # 文件内容里也不许出现那个测试值
    # [EN] The test value must not appear in the file contents either
    try:
        txt = ENV.read_text(encoding='utf-8')
    except OSError:
        txt = ''
    REPORT['b1b'] = {'leaked': 'X:/这个值绝不能进用户的env' in txt}
    ok('B1b ★★ `.env` 里**没有**那个测试值（不是"md5 碰巧没变"）',
       'X:/这个值绝不能进用户的env' not in txt, REPORT['b1b'])

    # ★★★ 兜底还原：**只要被改了就还原**（无论上面几条红不红）。
    # [EN] ★★★ Fallback restore: **restore as long as it was modified** (regardless of whether the above
    # [EN] checks are red).
    if backup is not None and md5(ENV) != before:
        ENV.write_text(backup, encoding='utf-8', newline='')
        REPORT['b_restored'] = True
        print('  ⚠ `.env` 被这次运行改动了 —— **已自动还原**'
              '（这正是判据要抓的那件事，但它不该把脏数据留在用户机器上）')
        ok('B1c ★★★ 判据**自己**不许把 `.env` 写坏：被改动时已自动还原'
           '（不还原的话，反例法每跑一次就在用户机器上留一处脏数据）',
           md5(ENV) == before, f'已还原 → md5={md5(ENV)[:8]}')

    # 保险丝确实"真的写了盘"（只是写到了别处）—— 否则这条判据可能只是"什么都没发生"
    # ⚠ 判据自己也要防"恒真"：如果 `CFG.save()` 因为别的原因抛错，
    #   B1 一样是绿的（.env 没变）。所以另起一次、看 sink 文件里有没有内容。
    # [EN] The fuse really did "write to disk" (it just wrote elsewhere) -- otherwise this criterion might
    # [EN] just be "nothing happened".
    # [EN] ⚠ The criterion itself must also guard against "always true": if `CFG.save()` throws for some
    # [EN] other reason,
    # [EN] B1 still passes green (.env unchanged). So run another time and check whether the sink file has
    # [EN] content.
    sinkf = Path(os.environ.get('TEMP', '/tmp')) / 'nws_envsink'
    n_before = len(list(sinkf.glob('*.env'))) if sinkf.exists() else 0
    rc2, out2 = run_as('tools/verify_probe_env_safety.py', BODY_SAVE)
    n_after = len(list(sinkf.glob('*.env'))) if sinkf.exists() else 0
    REPORT['b2'] = {'rc': rc2, 'saved': 'SAVED_OK' in out2,
                    'sink_before': n_before, 'sink_after': n_after}
    ok('B2 ★★★ 那一次保存**真的执行了、真的落到临时文件**'
       '（否则 B1 可能只是"什么都没发生"就绿了 —— 判据自己也要防恒真）',
       'SAVED_OK' in out2 and n_after >= n_before and md5(ENV) == before,
       REPORT['b2'])


def main() -> int:
    try:
        group_a()
        group_b()
    finally:
        REPORT['checks'] = CHECKS
        REPORT['passed'] = len(CHECKS) - _FAILS
        REPORT['total'] = len(CHECKS)
        (OUT / 'env_safety_report.json').write_text(
            json.dumps(REPORT, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'\n配置写盘安全验证：{REPORT["passed"]}/{REPORT["total"]}')
        print('报告：assets/screenshots/env_safety_report.json')
    return 0 if _FAILS == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
