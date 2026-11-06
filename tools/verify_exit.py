# -*- coding: utf-8 -*-
"""判据的**退出码**统一出口（2026-10-28 新建）。

为什么需要它
------------
`tools/run_all_verifications.py` **只看退出码**（`ok = code == 0`）。
⇒ 一支判据哪怕断言红成一片，只要退出码是 0，它在回归里就是**绿的** ——
「红灯打出来也没人看得见」，那条覆盖**从来没被证明过**。

⚠⚠ 这个病**不会自己暴露**：判据自己跑一遍是绿的、回归也是绿的、
  报告上写着「N/N 通过」，一切看起来都对。
  ⇒ 只有**故意把某条断言改坏**再跑，才看得出它会不会红
  （实测：`verify_style_control` / `verify_setting_layers` / `verify_crew_onduty`
  三支都是 `main() -> None` 且**没有 `sys.exit`** ⇒ 恒绿）。

怎么用
------
    from tools.verify_exit import finish

    # 判据跑完时：
    sys.exit(finish(report))     # report = {'checks': [{'name':…, 'ok':…}, …]}

`finish()` 会：
  · 统计通过/失败条数；
  · **有红的（或崩了）⇒ 返回 2；全绿 ⇒ 返回 0**；
  · 把失败清单打印出来（人要看得到红的是哪几条）。

⚠ 判据里**别再各写一份** `bad = [...]; return 0 if not bad else 2` ——
  同一件事两处实现 ⇒ 迟早有一处忘了「红的要非 0」。

English:
The single exit-code outlet for criteria. The regression harness only looks at the exit code,
so a criterion that prints red but exits 0 is **always green** in the regression -- and that
failure never surfaces on its own (the criterion passes, the regression passes, the report says
"N/N passed"). The only way to find it is to deliberately break one assertion and see whether the
process exits non-zero. Use `finish(report)` instead of hand-rolling the same arithmetic in every
criterion: two implementations of one thing => one of them eventually forgets "red must exit
non-zero".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent


def failed_checks(report: dict) -> list[dict]:
    """报告里没过的那几条（`ok` 为假）。"""
    return [c for c in (report.get('checks') or []) if not c.get('ok')]


def finish(report: dict, *, out_path: Path | None = None,
           label: str = '断言') -> int:
    """把报告算成**退出码**：全绿 0，有红的（或崩了）2。

    参数
    ----
    report : 形如 `{'checks': [{'name': str, 'ok': bool, 'detail': str}, …]}`
    out_path : 可选 —— 把报告写成 JSON 的地方
    label : 打印那一行时的前缀（「断言 12/12」）
    """
    checks = report.get('checks') or []
    bad = failed_checks(report)
    total = len(checks)
    passed = total - len(bad)
    fatal = report.get('fatal')
    report['ok'] = not bad and not fatal
    report['failed'] = [c.get('name', '') for c in bad]
    report['passed'] = passed
    report['total'] = total
    if out_path is not None:
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                encoding='utf-8')
        except Exception:                                       # noqa: BLE001
            pass
    print(f'\n{label} {passed}/{total}')
    for c in bad:
        detail = str(c.get('detail') or '')[:110]
        print(f"  ! {c.get('name', '')} | {detail}")
    if fatal:
        print(f'\n⚠ 中途崩溃：\n{str(fatal)[-1200:]}')
    # ★★★ **红了 ⇒ 退出码非 0**（这一行就是这支库存在的全部理由）
    return 0 if report['ok'] else 2


def run(main_func) -> int:
    """跑一个判据的 `main()` 并把它的返回值变成进程退出码。

    用法（替代裸的 `main()`）：

        if __name__ == '__main__':
            sys.exit(run(main))
    """
    return int(main_func() or 0)


if __name__ == '__main__':
    print(__doc__)
    sys.exit(0)
