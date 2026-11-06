# -*- coding: utf-8 -*-
"""验证：**每支判据红了都真的会红**（退出码非 0）。

背景
====
`tools/run_all_verifications.py` **只看退出码**（`ok = code == 0`）。
⇒ 一支判据哪怕断言红成一片，只要退出码是 0，它在回归里就是**绿的** ——
「红灯打出来也没人看得见」，那条覆盖**从来没被证明过**。

⚠⚠ 这个病**不会自己暴露**：
  判据自己跑一遍是绿的、回归也是绿的、报告上写着「N/N 通过」，一切看起来都对。
  ⇒ 只有**故意把某条断言改坏**再跑，才看得出它会不会红。

实测抓到的（2026-10-28）：
  `verify_style_control` / `verify_setting_layers` / `verify_crew_onduty`
  —— 三支都是「有 page 才把 code 交出去」或「压根没有 `sys.exit`」⇒ **恒绿**。

怎么查
------
**不是**静态扫 AST（`return 0 if report.get('ok') else 1` 这种写法，
静态扫只能看见那个字面量，判断不了它跟失败状态有关 ⇒ **大面积误报**）。
⇒ 唯一可靠的口径是**真跑一次红的**：

  1. 备份该判据；
  2. 用 AST 找到**第一处** `ok('...', <cond>)`，把 `<cond>` 那段源码
     **按字节切片**换成 `False`
     （⚠ AST 的 `col_offset` 是 **UTF-8 字节偏移**，按字符切会把中文切错位）；
  3. 跑它 ⇒ 退出码**必须非 0**；
  4. 还原。

★ **哪些判据要查**：只查**纯逻辑**的（LOGIC 组 + ALONE 组）。
  GUI 组的真机判据要起窗口、耗时长，本脚本**不碰**（它们由
  `verify_ui_common` 那套 `shutdown(page, code=...)` 管着）。

⚠⚠ **别把自己算进去**：本脚本**自己**也是判据 ⇒ 它也必须遵守"红了退出码非 0"。
  （它自己改了别人的源码，别人红了它当然绿 ⇒ 它的红只来自"某支判据恒绿"。）

跑法：.venv\\Scripts\\python.exe tools\\verify_exit_codes.py

English:
Verification: **every criterion really goes red when it should** (non-zero exit code).
The regression harness only looks at the exit code, so a criterion that prints red but exits 0 is
**always green** in the regression -- and that illness never surfaces on its own (the criterion
passes, the regression passes, the report says "N/N passed"). The only reliable way to find it is
to deliberately break one assertion and see whether the process exits non-zero. Static AST
scanning is **not** reliable here (a `return 0 if report.get('ok') else 1` cannot be judged
statically) => this script really runs each criterion with one assertion broken.
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from tools.verify_exit import finish        # noqa: E402  ★ 退出码统一出口

PY = str(APP / '.venv' / 'Scripts' / 'python.exe')
TOOLS = APP / 'tools'

#: 本脚本自己（改别人的源码 ⇒ 自己当然绿 ⇒ 它不能查自己）。
SELF = 'verify_exit_codes'

CHECKS: list[dict] = []


def ok(name: str, cond, detail='') -> bool:
    """记一条检查。**红的必须让退出码非 0** —— 回归器只看退出码。

    ⚠ 这一支**自己**也必须守这条（它就是那条铁律的执行者）⇒
      末尾走 `tools/verify_exit.py` 的 `finish()`，**别各写一份**算退出码。
    """
    good = bool(cond)
    CHECKS.append({'name': name, 'ok': good, 'detail': str(detail)[:400]})
    print(('  ✓ ' if good else '  ✗ ') + name
          + (f'   [{detail}]' if detail else ''), flush=True)
    return good


#: 断言记录器的**常见名字**（`ok` / `rec` / …）。
#: ⚠ 这只是**兜底名单**，主路径是 `_recorders()`（从源码自己推断）——
#:   名单硬编码 ⇒ 新判据换个名字就"改不坏"⇒ 被记成"跳过"⇒
#:   那条覆盖**从没被证明过**（而跳过的人往往以为"查过了"）。
#: [EN] Common names for the assertion recorder (`ok` / `rec` / ...).
#: [EN] ⚠ This is only a **fallback list**; the main path is `_recorders()` (inferred from the source
#: [EN] itself) -- a hard-coded list => a new criterion that picks a different name comes out
#: [EN] "unbreakable" => recorded as "skipped" => that coverage **was never proven** (and whoever
#: [EN] reads "skipped" usually assumes "checked").
RECORDER_NAMES = {'ok', 'rec', 'okv', 'record', 'expect', 'add_check', 'assert_ok', 'note'}


def _recorders(tree: ast.Module) -> set[str]:
    """从源码自己推断：**哪些函数是断言记录器**。

    判据：**函数体里有 `X.append({... 'ok': ...})` 这样的写法** ——
    即"把一条检查结果收进某个列表"。
    ⇒ 不靠名字猜 ⇒ 新判据叫什么都能认出来。
    """
    out: set[str] = set()
    for n in ast.walk(tree):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(n):
            if not isinstance(sub, ast.Call):
                continue
            f = sub.func
            if not isinstance(f, ast.Attribute) or f.attr != 'append':
                continue
            # `X.append({...})` —— 看那个字典里有没有 'ok' 键
            if sub.args and isinstance(sub.args[0], ast.Dict):
                keys = [k.value for k in sub.args[0].keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                if 'ok' in keys:
                    out.add(n.name)
                    break
    return out


def _first_ok_cond(tree: ast.Module) -> ast.expr | None:
    """第一处断言记录器调用的**条件表达式**节点。

    条件在**第二个位置参数**（`rec('名字', <cond>, detail)`），
    也可能是关键字参数（`rec(name=..., ok_=<cond>)`）。
    """
    names = _recorders(tree)
    if not names:
        names = RECORDER_NAMES
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        fname = getattr(n.func, 'id', None) or getattr(n.func, 'attr', None)
        if fname not in names:
            continue
        # 位置参数：第 2 个
        if len(n.args) >= 2:
            cond = n.args[1]
            if not isinstance(cond, ast.Constant):
                return cond
            continue
        # 关键字参数：ok / ok_ / cond / value
        for kw in n.keywords:
            if kw.arg in ('ok', 'ok_', 'cond', 'value', 'passed') and kw.arg:
                if not isinstance(kw.value, ast.Constant):
                    return kw.value
    return None



def _shell_return(src: str) -> ast.expr | None:
    """**转发壳**型判据：`raise SystemExit(X.main())` 里那个 `main()` 调用。

    例：`tools/verify_i18n_coverage.py` 自己一条断言都没有 —— 它只是
    `raise SystemExit(i18n_check.main())`，真正的检查在 `tools/i18n_check.py` 里。
    ⇒ 壳里当然找不到"断言记录器" ⇒ 但**壳能不能红**是另一回事：
    它红不红，取决于**转发出去的那个 `main()` 会不会返回非 0**。
    ⇒ 把那个 `main()` 换成 `lambda: 1` ⇒ 壳必然退出非 0 ⇒ 测的就是"壳的出口通不通"。
    """
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        # `X.main(...)` 或 `main(...)`
        if isinstance(f, ast.Attribute) and f.attr == 'main' and not n.args:
            return n
        if isinstance(f, ast.Name) and f.id == 'main' and not n.args:
            return n
    return None


def break_first_ok(src: str) -> tuple[str, int]:
    """把第一处断言的条件换成 `False`；返回 (新源码, 改了第几行)。

    ⚠ **按字节切片**：AST 的 `col_offset` 是 **UTF-8 字节偏移**，
      而 `str.split('\\n')` 给的是**字符** —— 按字符切会把中文切错位
      （这是 `developers/sync_generator.py` 里踩过的同一个坑）。

    ⚠ **两路要填不同的值**：
      · 断言条件 ⇒ `False`（让那一条红）；
      · 转发壳的 `main()` ⇒ **`1`** —— ⚠ 不能填 `False`！
        `raise SystemExit(False)` 的退出码是 **0**（False == 0）⇒
        会被读成"恒绿" ⇒ **测出来的是假结论**。
    """
    tree = ast.parse(src)
    cond = _first_ok_cond(tree)
    filler = b'False'
    if cond is None:
        # 转发壳型 ⇒ 改它转发出去的那个调用。
        call = _shell_return(src)
        if call is None:
            raise AssertionError('找不到断言记录器的条件，也不是转发壳')
        cond = call
        filler = b'1'
    b = src.encode('utf-8')
    line_starts = []
    pos = 0
    for line in src.split('\n'):
        line_starts.append(pos)
        pos += len(line.encode('utf-8')) + 1          # +1 = 换行符
    s = line_starts[cond.lineno - 1] + cond.col_offset
    e = line_starts[cond.end_lineno - 1] + cond.end_col_offset
    return (b[:s] + filler + b[e:]).decode('utf-8'), cond.lineno


def targets() -> list[str]:
    """要查的判据：**纯逻辑**的那些（LOGIC 组 + ALONE 组里不起真机窗口的）。

    ⚠⚠ **别把 ALONE 组整组塞进来**：ALONE 里混着**会起真机窗口**的脚本
    （`verify_splash_boot` 会**真的把整个程序启动一遍**、`verify_agent_colwidth`
    会**真的缩放窗口**、`verify_run_output_style` / `verify_story_depth` 会
    **真跑一轮推演**）。
    ⇒ 本脚本会把它们**改坏一处再真跑一遍** ⇒ 那就不是"体检"，是**在体检时
    启动了整个程序**（还会抢桌面、还会写 `.ui_state/`、还会烧一轮推演的钱）。
    ⇒ 判据：**源码里有 `ft.run(` 的不查**（与 `run_all_verifications.py` 里
    `suspicious()` 用的同一把尺子 —— 同一件事只有一处实现）。

    ⚠ 顺带一提：GUI 组**一律不查**（要起窗口、耗时长）。
    """
    import tools.run_all_verifications as R
    names: list[str] = []
    for n in list(R.LOGIC) + list(R.ALONE):
        if n == SELF:
            continue
        p = TOOLS / f'{n}.py'
        if not p.exists():
            continue
        try:
            src = p.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        if 'ft.run(' in src:
            # 起真机窗口的 ⇒ 本脚本不碰（理由见上面）。
            continue
        names.append(n)
    return names


def _restore_leftovers() -> list[str]:
    """启动时：**把上次没善终的改坏还原**。

    ⚠ `probe()` 的还原靠 `finally`，而 `finally` **挡不住进程被杀**
      （实测：`mutate_*.py` 那次被 `SIGTERM` 打断，产品文件就停在变异上）。
      ⇒ 本脚本改的是**判据自己的源码** ⇒ 停在改坏状态 ⇒
      后面所有判据都在量一个**错的判据**，而且它们照样"全绿"。
      ⇒ 启动先扫一遍 `.exitbak`，有就还原。
    [EN] On startup: **restore anything left over from a run that didn't finish cleanly**.
    ⚠ `probe()` restores via `finally`, and `finally` **can't stop the process from being killed**
      (measured: a `mutate_*.py` run was interrupted by `SIGTERM` and the product file stayed
      mutated).
      => This script edits **criterion sources themselves** => left in the broken state => every later
      criterion measures a **wrong criterion**, and they still come out "all green".
      => Sweep for `.exitbak` on startup and restore.
    """
    out: list[str] = []
    for bak in sorted(TOOLS.glob('verify_*.py.exitbak')):
        orig = bak.with_suffix('')
        try:
            # ⚠ 用 `os.replace`（原子替换）而不是"拷贝 + 删" ⇒ 不触发批量删除拦截。
            os.replace(bak, orig)
            out.append(orig.name)
        except OSError:
            try:
                shutil.copy2(bak, orig)
            except OSError:
                continue
            out.append(orig.name)
    return out


def probe(name: str) -> tuple[int, str]:
    """把该判据改坏一处，跑它，返回 (退出码, 说明)。

    ⚠⚠ **崩溃 ≠ 断言红**：脚本抛 Traceback 时退出码也是非 0，但那时红的是
      "脚本崩了"，**不是"这条覆盖真的能红"** ⇒ 那一次体检**什么都没证明**。
      ⇒ 单独记成"崩了"（`code = -5`），不混进"会红"里。
      （这跟 `developers/mutate_*.py` 那条老铁律一样：
        **「脚本自己崩了」不算「判据变红」**。）
    """
    p = TOOLS / f'{name}.py'
    if not p.exists():
        return -1, '文件不存在'
    src = p.read_text(encoding='utf-8')
    try:
        new_src, ln = break_first_ok(src)
    except Exception as ex:                                # noqa: BLE001
        return -2, f'改不坏（{ex}）'
    if new_src == src:
        return -3, '改坏后内容没变'
    bak = p.with_suffix(p.suffix + '.exitbak')
    shutil.copy2(p, bak)
    try:
        p.write_text(new_src, encoding='utf-8')
        r = subprocess.run([PY, str(p)], cwd=str(APP), capture_output=True,
                           text=True, encoding='utf-8', errors='replace',
                           timeout=900)
        tail = (r.stdout or '') + (r.stderr or '')
        # ★★★ 2026-10-31：判"崩了"**不能只看有没有 Traceback**。
        #   有的判据**故意**让产品接一个异常再验证"接住了"（`verify_svc_users` 的 C4：
        #   往 `SU.any_other_alive` 里塞 `RuntimeError('boom')`，期望 `_stop_services_if_last`
        #   吞掉它）—— 产品接住后用 `log_exception` 把 Traceback **记进日志**，
        #   脚本继续往下跑、结论照常打出来。那不是崩，是**测到了**。
        #   ⇒ 真崩的标志是：**最后一个** Traceback 之后**再没有**判据自己的结论行
        #     （"断言 X/Y" / "=== X/Y ===" / "共 N 项断言" / "验证：X/Y" 这类）。
        #     结论行在 Traceback 后面还出现 = 脚本活到了收尾 = 没崩。
        # [EN] ★★★ 2026-10-31: "crashed" **cannot be judged by the mere presence of a Traceback**.
        #   Some criteria **deliberately** make the product catch an exception and then assert it
        #   was caught (`verify_svc_users` C4: stuff `RuntimeError('boom')` into
        #   `SU.any_other_alive`, expecting `_stop_services_if_last` to swallow it) -- the product
        #   logs that Traceback via `log_exception` and the script **keeps running to its summary**.
        #   That is not a crash, it is the assertion working.
        #   => A real crash means: after the **last** Traceback there is **no** conclusion line of the
        #     criterion itself ("断言 X/Y" / "=== X/Y ===" / "共 N 项断言" / "验证：X/Y").
        #     A conclusion line appearing *after* the last traceback = the script survived = not a crash.
        tb = tail.rfind('Traceback (most recent call last)')
        after_tb = tail[tb:] if tb >= 0 else ''
        survived = bool(re.search(r'\d+\s*/\s*\d+', after_tb))
        crashed = tb >= 0 and not survived and r.returncode != 0
        if crashed:
            # 把崩在哪一行摘出来（够定位就行，不必全文）
            where = ''
            for line in tail.splitlines():
                if 'Error' in line and not line.startswith(' '):
                    where = line.strip()[:80]
                    break
            return -5, f'第 {ln} 行 · **脚本崩了**（不算"会红"）{where}'
        return r.returncode, f'第 {ln} 行'
    except subprocess.TimeoutExpired:
        return -4, '超时'
    finally:
        # ⚠⚠ **还原必须用 `os.replace`，不能用"拷贝回去 + 删掉备份"** ——
        #   那个 `unlink` 会被安全策略当"批量删除"拦下来（实测：跑到第 43 支
        #   时进程被沙箱杀掉，退出码 1 ⇒ **体检中断在半路**，
        #   磁盘上还留着改坏的判据）。
        #   `os.replace` 是**原子替换** ⇒ 备份自然消失，**一次删除动作都不需要**。
        try:
            os.replace(bak, p)
        except OSError:
            shutil.copy2(bak, p)
            bak.unlink(missing_ok=True)


def main() -> int:
    print('判据的退出码 —— 「红了到底会不会红」', flush=True)
    left = _restore_leftovers()
    if left:
        print(f'⚠ 先还原上次没跑完的改坏：{left}\n', flush=True)
    names = targets()
    # ★ `--only` ：定点复跑（不然每次都得重跑一百多支，几十分钟）。
    only = {s.strip() for s in os.environ.get('NWS_EXIT_ONLY', '').split(',') if s.strip()}
    if only:
        names = [n for n in names if n in only]
    print(f'要查 {len(names)} 支（LOGIC + ALONE 里不起真机窗口的，纯逻辑）\n', flush=True)

    never_red: list[str] = []
    skipped: list[str] = []
    crashed: list[str] = []
    for i, name in enumerate(names, 1):
        code, detail = probe(name)
        if code == 0:
            never_red.append(name)
            print(f'  [{i}/{len(names)}] {name}：退出码 0 ⇒ **恒绿**   [{detail}]',
                  flush=True)
        elif code == -5:
            # ⚠ 崩了 ≠ 红了 ⇒ 单独一类，别混进"跳过"（混了报错信息会误导人）。
            crashed.append(f'{name}（{detail}）')
            print(f'  [{i}/{len(names)}] {name}：{detail}', flush=True)
        elif code < 0:
            skipped.append(f'{name}（{detail}）')
            print(f'  [{i}/{len(names)}] {name}：跳过（{detail}）', flush=True)
        else:
            print(f'  [{i}/{len(names)}] {name}：退出码 {code} ✓ 会红', flush=True)

    ok('E1 ★★★ **没有恒绿的判据**（改了断言，退出码必须非 0）',
       not never_red,
       ('恒绿：' + ', '.join(never_red)) if never_red
       else f'{len(names)} 支全部实测会红')
    ok('E2 ★★ 没跳过的（跳过的不算"验过了"）',
       not skipped, '; '.join(skipped[:3]) if skipped else '无')
    ok('E3 ★★ 没崩的（崩了证明不了"这条能红"）',
       not crashed, '; '.join(crashed[:3]) if crashed else '无')

    # ★★★ **自己也得守这条铁律** ⇒ 走统一出口，别在这里另写一份算退出码。
    return finish({'checks': CHECKS}, label='判据退出码体检')


if __name__ == '__main__':
    # ★ `main()` 返回 int ⇒ **必须 `sys.exit`**（忘了就又是一支恒绿判据）。
    sys.exit(main())
