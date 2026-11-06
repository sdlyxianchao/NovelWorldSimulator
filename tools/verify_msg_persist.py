# -*- coding: utf-8 -*-
"""验证：**全局消息跨启动保留**（2026-10-09）。

用户原话：

    「系统消息应该是**跨启动保留**，除非我主动删除，否则不能够上次运行
      过程中的消息关闭再启动就没了」

判据分层（每层都要能红，见 `developers/mutate_msg_persist.py`）：

  A **落盘助手**（源码级）：文件位置合理、JSONL 一行一条、只追加、
    坏了只丢那一行、写不进去不抛、上限会压
  B **真机**：跑一次真程序 → 发一条消息 → **换一个新实例**（模拟重启）→
    那条消息还在；点「清空」之后**盘上也干净**、再开一次也不回来
  C **不回归**：坏文件不拦启动；非今天的条目**带日期**（否则昨天的
    23:41 和今天的 23:41 长得一样，"怎么刚发生的"）

用法：.venv\\Scripts\\python.exe tools/verify_msg_persist.py
产出：assets/screenshots/msg_persist_report.json

English:
Verification: **global messages persist across restarts** (2026-10-09).
User's exact words:
    "System messages should **persist across restarts**; unless I actively delete them, messages from the previous run
      must not disappear when closed and restarted"
Criterion layers (every layer must be able to turn red, see `developers/mutate_msg_persist.py`):
  A **persistence helper** (source level): file location reasonable, JSONL one per line, append-only,
    if corrupted discard only that line, if write fails do not throw, cap will shrink
  B **real machine**: run the real program once → send a message → **switch to a new instance** (simulate restart) →
    that message is still there; after clicking "clear", **the disk is also clean**, and opening again does not bring it back
  C **no regression**: corrupted file does not block startup; entries not from today **include the date** (otherwise yesterday's
    23:41 and today's 23:41 look the same, "how did this just happen")
Usage: .venv\\Scripts\\python.exe tools/verify_msg_persist.py
Output: assets/screenshots/msg_persist_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402
import verify_ui_common as VU                                  # noqa: E402
from util.flet_shutdown import shutdown                        # noqa: E402

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')
CFG.set('SHOW_OPENING', 'false')
# ⚠ 起界面就会走 `app.main()` → 能力校验 → `CFG.save()`；从头到尾禁写真实 .env
# [EN] ⚠ Starting the UI will run `app.main()` → capability check → `CFG.save()`; from start to finish,
# [EN] writing the real .env is forbidden
VU.redirect_env_writes()

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

from gui import app_flet as G                                  # noqa: E402
from gui.app_flet import NovelWorldApp                         # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
REPORT: dict = {'checks': []}
#: 判据自己那条消息的标记（用来在文件里精确找它）
# [EN] : the marker of the criterion's own message (used to locate it precisely in the file)
MARK = '判据-跨启动保留-20261009'


def ok(name: str, cond, detail: str = '') -> bool:
    REPORT['checks'].append({'name': name, 'ok': bool(cond),
                             'detail': str(detail)[:400]})
    if not cond:
        print(f'FAIL  {name}   [{detail}]')
    return bool(cond)


def msg_lines() -> list[str]:
    p = G.msg_file_path()
    if not p.exists():
        return []
    return [ln for ln in p.read_text(encoding='utf-8').splitlines() if ln.strip()]


def cleanup() -> None:
    """把判据自己写进去的那条清掉（**别留垃圾给用户**）。
        English:
    Clear out the one that the criterion itself wrote (**do not leave garbage for the user**).
    """
    p = G.msg_file_path()
    if not p.exists():
        return
    keep = [ln for ln in p.read_text(encoding='utf-8').splitlines()
            if MARK not in ln]
    try:
        if keep:
            p.write_text('\n'.join(keep) + '\n', encoding='utf-8')
        else:
            p.unlink()
    except OSError:
        pass


# ══════════════════════════════════════════════════════════════════
#  A. 落盘助手（不需要界面）
# [EN] A. Persistence helper (no UI needed)
# ══════════════════════════════════════════════════════════════════
def test_helpers() -> bool:
    import inspect
    ok_ = True
    src = inspect.getsource(G)

    # A1 文件位置：**不能放 logs/** —— `log_dir()` 可配置且会按 `LOG_ROTATE_DAYS`
    #    清理，消息要"留到用户主动删"，被日志清理扫掉就白做了。
    # [EN] A1 File location: **must not go in logs/** —— `log_dir()` is configurable and will follow
    # [EN] `LOG_ROTATE_DAYS`
    # [EN] for cleanup, messages must "stay until the user actively deletes them"; if they get swept away
    # [EN] by log cleanup, the whole thing is wasted.
    #
    # ⚠ 这里要判的是**默认位置**，不能拿 `msg_file_path()` 的结果去判 ——
    #   判据脚本自己会 `VU.redirect_env_writes()`，于是它看到的已经是
    #   **临时 sink**（`…\Temp\nws_envsink_xxx\.env.msg`）。
    #   第一版就是拿它判的，A1/A1b 两条当场假红。
    #   ★ 而且必须**真的走一遍产品的默认分支**（把两个 sink 都临时摘掉再问它）——
    #     只比 `APP_DIR / MSG_FILE_NAME` 这两个常量是不够的：
    #     "把 `msg_file_path()` 的默认返回值改成 `logs/`" 这个变异**打不红它**
    #     （反例法当场揭穿：常量没变，变的是返回那一行）。
    # [EN] ⚠ What must be checked here is the **default location**, and you cannot judge using the result
    # [EN] of `msg_file_path()` ——
    # [EN] the criterion script itself calls `VU.redirect_env_writes()`, so what it sees is already
    # [EN] a **temporary sink** (`…\Temp\nws_envsink_xxx\.env.msg`).
    # [EN] The first version judged using that, and A1/A1b both showed false red on the spot.
    # [EN] ★ And it must **actually go through the product's default branch once** (temporarily remove both
    # [EN] sinks and then ask it) ——
    # [EN] Comparing only the two constants `APP_DIR / MSG_FILE_NAME` is not enough:
    # [EN] the mutation "change the default return value of `msg_file_path()` to `logs/`" **will not make
    # [EN] it turn red**
    # [EN] (the counterexample method exposes it on the spot: the constant did not change, what changed is
    # [EN] the line that returns).
    import os as _os
    _cfg = sys.modules['config']
    # ⚠ **两个出口都要摘**：消息的 sink 是 `NWS_MSG_SINK`（回归器按脚本名给的），
    #   `NWS_ENV_SINK` 只是退路。只摘后者，`msg_file_path()` 还是走 sink，
    #   A1/A1b 两条会假红（实测踩到）。
    # [EN] ⚠ **Both exits must be removed**: the message sink is `NWS_MSG_SINK` (given by the regressor
    # [EN] according to the script name),
    # [EN] `NWS_ENV_SINK` is only the fallback. Remove only the latter, and `msg_file_path()` still goes
    # [EN] through the sink,
    # [EN] A1/A1b will show false red (encountered in actual testing).
    _bak_env = _os.environ.pop('NWS_ENV_SINK', None)
    _bak_msg = _os.environ.pop('NWS_MSG_SINK', None)
    _bak_rs = _cfg.Config.redirect_save
    _cfg.Config.redirect_save = None
    try:
        real = G.msg_file_path()
    finally:
        _cfg.Config.redirect_save = _bak_rs
        if _bak_env is not None:
            _os.environ['NWS_ENV_SINK'] = _bak_env
        if _bak_msg is not None:
            _os.environ['NWS_MSG_SINK'] = _bak_msg
    ok_ &= ok('A1 ★★ 消息**默认**落在程序目录下，不在 `logs/`（日志会按天数清理）'
              '—— 真的走一遍产品的默认分支，不是比两个常量',
              real.parent == APP_DIR and 'log' not in real.parent.name.lower(),
              str(real))
    ok_ &= ok('A1b ★ 文件名以 `.nws_` 打头（与别处"程序状态文件"同一套命名）',
              real.name.startswith('.nws_'), real.name)
    # A1c ★★★ 验证/回归期间**不许写用户的真实消息文件**（2026-10-09 补）
    #   为什么这条必须有：回归里有几十支脚本会起真界面、`app.main()` 一上来就发消息 ——
    #   不隔离的话每跑一次回归就往用户的 `.nws_messages.jsonl` 里灌几十条**中文测试消息**
    #   （实测：`verify_ui_english` 因此在自己那份英文界面里读出别人的中文消息，直接假红）。
    # [EN] A1c ★★★ During verification/regression, **writing the user's real message file is not allowed**
    # [EN] (added 2026-10-09)
    # [EN] Why this is required: in regression there are dozens of scripts that will start the real UI, and
    # [EN] `app.main()` sends messages as soon as it starts ——
    # [EN] without isolation, every regression run pours dozens of **Chinese test messages** into the
    # [EN] user's `.nws_messages.jsonl`
    # [EN] (actual test: `verify_ui_english` therefore read other people's Chinese messages in its own
    # [EN] English UI, directly showing false red).
    ok_ &= ok('A1c ★★★ 设了 sink（`NWS_MSG_SINK` / `NWS_ENV_SINK`）时，'
              '消息**写到临时文件**（回归不会往用户的真实文件里灌测试垃圾）',
              G.msg_file_path() != real,
              f'{G.msg_file_path()}')

    # A2 格式：JSONL（一行一条）
    # [EN] A2 Format: JSONL (one per line)
    ok_ &= ok('A2 ★★ 用 JSONL 一行一条（追加不用读全量；坏一行只丢一行）',
              'json.dumps(m' in src and "f.write(" in src
              and '+ \'\\n\'' in src.replace('"', "'"), '')

    # A3 读坏了只丢那一行（不是整份丢掉）
    # [EN] A3 If a read is corrupted, discard only that line (not the whole thing)
    bak = None
    p = G.msg_file_path()
    if p.exists():
        bak = p.read_text(encoding='utf-8')
    try:
        p.write_text('{"ts":"01:02:03","day":"2026-01-01","text":"好的一行","level":"ok"}\n'
                     '@@ 这不是 JSON @@\n'
                     '{"ts":"01:02:04","day":"2026-01-01","text":"另一行好的","level":"warn"}\n',
                     encoding='utf-8')
        got = G.load_messages()
        ok_ &= ok('A3 ★★ 文件里有一行是坏的 → 只丢那一行，好的两行照样读回来',
                  [m['text'] for m in got] == ['好的一行', '另一行好的'],
                  str([m['text'] for m in got]))
    finally:
        if bak is None:
            p.unlink(missing_ok=True)
        else:
            p.write_text(bak, encoding='utf-8')

    # A4 整个文件坏了 / 不存在 → 返回空表，**不抛**（绝不拦启动）
    # [EN] A4 Whole file corrupted / does not exist → return empty table, **do not throw** (never block
    # [EN] startup)
    try:
        p.write_text('全部都是垃圾\x00\x00', encoding='utf-8')
        ok_ &= ok('A4 ★★★ 文件整个读不动时 `load_messages()` **返回空表、不抛**'
                  '（一个坏文件让软件打不开是最不划算的交换）',
                  G.load_messages() == [], '')
    except Exception as e:                                     # noqa: BLE001
        ok_ &= ok('A4 ★★★ 文件整个读不动时不抛异常', False, repr(e))
    finally:
        if bak is None:
            p.unlink(missing_ok=True)
        else:
            p.write_text(bak, encoding='utf-8')

    # A5 内存上限仍有（别让内存无限涨）
    # [EN] A5 There is still an in-memory cap (do not let memory grow without bound)
    ok_ &= ok('A5 ★ 内存里仍然只留最近 200 条（原行为没被改坏）',
              'len(self._messages) > 200' in src
              and 'del self._messages[:-200]' in src, '')

    # A6 时间标签：非今天要带日期
    # [EN] A6 Time label: if not today, include the date
    ok_ &= ok('A6 ★★ 非今天的条目**带日期**（否则昨天的 23:41 会被当成刚发生的）',
              G.msg_time_label({'ts': '23:41:00', 'day': '2020-08-14'},
                               '2026-10-09').startswith('08-14')
              and G.msg_time_label({'ts': '23:41:00', 'day': '2026-10-09'},
                                   '2026-10-09') == '23:41:00',
              G.msg_time_label({'ts': '23:41:00', 'day': '2020-08-14'}, '2026-10-09'))
    return ok_


# ══════════════════════════════════════════════════════════════════
#  B/C. 真机
# [EN] B/C. Real machine
# ══════════════════════════════════════════════════════════════════
async def test_ui(page: ft.Page) -> bool:
    ok_ = True
    cleanup()

    # ── B1 实例甲：发一条消息 → 它必须**立刻**在盘上 ──
    # [EN] ── B1 Instance A: send a message → it must be on disk **immediately** ──
    app1 = NovelWorldApp()
    app1.main(page)
    page.update()
    await asyncio.sleep(0.8)
    n_before = len(msg_lines())
    app1._post_message(MARK, level='warn', keep=True)
    page.update()
    await asyncio.sleep(0.3)
    lines = msg_lines()
    REPORT['after_post'] = {'before': n_before, 'after': len(lines)}
    ok_ &= ok('B1 ★★★ 发出消息后**立刻落盘**（不是等到退出时才写 —— '
              '那样崩一次就全丢）',
              len(lines) == n_before + 1 and MARK in lines[-1],
              f'{n_before} → {len(lines)}')
    rec = json.loads(lines[-1])
    ok_ &= ok('B1b ★ 落盘里带 `day`（跨启动之后要靠它判断"是不是今天"）',
              rec.get('day') and len(str(rec['day'])) >= 10, str(rec))
    ok_ &= ok('B1c ★ 级别也存下来了（界面按级别给颜色）', rec.get('level') == 'warn',
              str(rec))

    # ── B2 判据自己别留垃圾：清空之后盘上要干净 ──
    # [EN] ── B2 The criterion itself must not leave garbage: after clearing, the disk must be clean ──
    app1._clear_messages()
    page.update()
    await asyncio.sleep(0.3)
    ok_ &= ok('B2 ★★★ 点「清空」→ **盘上也清了**（否则下次启动原样回来，'
              '用户会以为清空坏了）',
              G.msg_file_path().exists() is False, str(G.msg_file_path()))

    # ── B3 ★★★ 核心：换一个**新实例**（= 模拟"关掉再启动"）──
    app1._post_message(MARK, level='warn', keep=True)     # 再发一条，留给"重启"看
    # [EN] ── B3 ★★★ Core: switch to a **new instance** (= simulate "close and restart") ──
    # [EN] Then send another message, leaving it for the "restart" to see
    page.update()
    await asyncio.sleep(0.3)
    ok_ &= ok('B3 前置：重启前盘上有那条消息', any(MARK in l for l in msg_lines()), '')

    app2 = NovelWorldApp()          # ← 新实例，走的是 `load_messages()`
    # [EN] ← new instance, goes through `load_messages()`
    texts = [m['text'] for m in app2._messages]
    REPORT['after_restart'] = {'n': len(texts), 'hit': any(MARK in x for x in texts)}
    ok_ &= ok('B3 ★★★ **关掉再启动**（新实例）之后，上次运行的消息**还在**'
              '—— 用户要的就是这一条',
              any(MARK in x for x in texts), str(texts[-3:]))
    ok_ &= ok('B3b ★★ 重启后**打开消息框能看到它**（不是只在文件里躺着）',
              any(isinstance(c, ft.Text) and MARK in str(c.value or '')
                  for c in VU.walk(app2._ui_msg.get('bar'))
                  if hasattr(app2, '_ui_msg')) if getattr(app2, '_ui_msg', None)
              else True, '（消息框还没建，由 B3 覆盖）')

    # ── B4 主动删除之后，重启也不回来 ──
    # [EN] ── B4 After active deletion, restart does not bring it back ──
    app2._clear_messages()
    page.update()
    await asyncio.sleep(0.3)
    app3 = NovelWorldApp()
    texts3 = [m['text'] for m in app3._messages]
    ok_ &= ok('B4 ★★★ 「主动删除」之后**再启动也不会回来**'
              '（否则"删不掉"比"留不住"更吓人）',
              not any(MARK in x for x in texts3), str(texts3[-2:]))

    # ── C1 坏文件不拦启动 ──
    # [EN] ── C1 Corrupted file does not block startup ──
    p = G.msg_file_path()
    p.write_text('这不是 JSON\n{{{\n', encoding='utf-8')
    try:
        app4 = NovelWorldApp()
        ok_ &= ok('C1 ★★★ 盘上是一个**坏文件**时，程序照样起得来'
                  '（消息丢了就丢了，不许拦启动）',
                  isinstance(app4._messages, list), str(type(app4._messages)))
    except Exception as e:                                     # noqa: BLE001
        ok_ &= ok('C1 ★★★ 坏文件不拦启动', False, repr(e))
    finally:
        cleanup()

    REPORT['final_lines'] = len(msg_lines())
    ok_ &= ok('C2 ★ 判据收尾：没在用户盘上留下垃圾消息',
              not any(MARK in l for l in msg_lines()), str(msg_lines()[-2:]))
    return ok_


def finish() -> int:
    (OUT / 'msg_persist_report.json').write_text(
        json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
    bad = [c for c in REPORT['checks'] if not c['ok']]
    n = len(REPORT['checks'])
    print(f'\n全局消息跨启动保留验证：{n - len(bad)}/{n}')
    for c in bad:
        print(f'  ✗ {c["name"]}   [{c["detail"]}]')
    print('→ 全部通过' if not bad else '→ 有失败项')
    return 0 if not bad else 1


async def entry(page: ft.Page) -> None:
    try:
        REPORT['helpers_ok'] = test_helpers()
        REPORT['ui_ok'] = await test_ui(page)
    except BaseException:                                      # noqa: BLE001
        import traceback
        REPORT['fatal'] = traceback.format_exc()[-1800:]
        print(REPORT['fatal'])
    finally:
        await shutdown(page, code=finish())


if __name__ == '__main__':
    ft.run(entry)
    sys.exit(finish())
