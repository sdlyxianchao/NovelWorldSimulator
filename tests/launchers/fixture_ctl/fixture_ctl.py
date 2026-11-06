# -*- coding: utf-8 -*-
"""判据用的**假统一控制器**（替掉 `novelservices/service_ctl.py`）。

为什么不能直接用真的：真控制器的 `stop` 会去 import 服务的桥、真去
`taskkill` / `POST /internal/shutdown`；`prepare` 会建 venv、装依赖
（PenShot 一套下来约 2GB）。判据不可能为了一条断言跑几分钟。

它只做一件事：**把收到的动作记下来**（`NWS_FIXTURE_CTL_LOG` 指向的文件，
每行一条 JSON）。于是判据可以断言"主窗口退出之后 / 卸载之前，启动器确实
通过控制器调了 `stop penshot` 和 `stop plotpilot`" —— 那是启动器那一侧的
**契约**；至于 stop 本身停不停得掉进程，是控制器和桥的事（另有判据守）。

由 `start.exe` / `uninstall.exe` 的环境变量 `NWS_TEST_SERVICE_CTL` 指过来；
两个服务目录由 `NWS_TEST_PENSHOT_DIR` / `NWS_TEST_PLOTPILOT_DIR` 指到
本目录下的 `penshot/` / `plotpilot/`（启动器要求"目录在"才认这个服务）。

English:
The **fake unified controller** used for the assertions (replaces
`novelservices/service_ctl.py`).
Why not use the real one: the real controller's `stop` imports the service's
bridge and really runs `taskkill` / `POST /internal/shutdown`; `prepare`
builds a venv and installs dependencies (about 2GB for PenShot alone).
The assertions can't possibly take several minutes for a single assertion.

It does only one thing: **record the actions it receives** (the file
`NWS_FIXTURE_CTL_LOG` points at, one JSON per line). Thus the assertions can
assert "after the main window exits / before uninstalling, the launcher did
indeed call `stop penshot` and `stop plotpilot` through the controller" --
that is the **contract** on the launcher's side; as for whether `stop`
itself can kill the process, that is the controller's and the bridge's
business (guarded by separate assertions).

Pointed here by `start.exe` / `uninstall.exe`'s environment variable
`NWS_TEST_SERVICE_CTL`; the two service directories are pointed at the
`penshot/` / `plotpilot/` folders under this one by
`NWS_TEST_PENSHOT_DIR` / `NWS_TEST_PLOTPILOT_DIR` (the launcher only
recognizes the service when "the directory is there").
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    service = sys.argv[2] if len(sys.argv) > 2 else ''
    rec = {
        'action': action,
        'service': service,
        'argv': sys.argv[1:],
        'pid': os.getpid(),
        'at': time.time(),
    }
    log = os.environ.get('NWS_FIXTURE_CTL_LOG', '').strip()
    if log:
        p = Path(log)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open('a', encoding='utf-8') as f:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        # 记录失败不该改退出码：判据会因为"没记到"而红，那比悄悄失败更容易查。
        # [EN] A recording failure must not change the exit code: the assertion
        # [EN] will go red for "nothing recorded", which is easier to trace
        # [EN] than a silent failure.
        except OSError:
            pass
    # 支持一个 `stop <id> sleep <秒>` 形式之外的简单等待：控制器真版在
    # `stop` 里可能等一会儿，这里不等 —— 判据不需要它等。
    # [EN] Supports a simple wait beyond `stop <id> sleep <seconds>`: the real
    # [EN] controller may wait a while inside `stop`; this one doesn't -- the
    # [EN] assertions don't need it to.
    if action == 'sleep' and len(sys.argv) > 2:
        time.sleep(float(sys.argv[2]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
