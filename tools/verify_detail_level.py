# -*- coding: utf-8 -*-
"""验证：**详细程度档位** + **书斋「运行」页的项目级覆盖**（2026-10-30 用户点名）。

用户原话：
  「你把天机 运行 时间系统里的事件倍率 这一个上面加一个详细程度吧 包含很详细 详细
    中间 简略 带过 选了之后对应的时间倍率和一拍（故事秒）跟着变化 同样 在书卷
    把类型风格里的运行边界移动到一个单独的Tab 叫做运行 然后也加同样的详细程度和
    时间系统 在天机里标注上这个是全局配置 在书斋里写明这里的配置会覆盖全局配置
    运行界面的时间信息根据书斋里的设定生成 默认书斋里的设定从天机里集成」

要验的四件事
------------
① 档位表（`sim/pace.py`）：五档闭集、每组数字合法、**每档都不一样**、反查精确；
② 覆盖层（`config.Config`）：`raw()` 认覆盖、`g()` 只看全局、`save()` **绝不**把
   覆盖写进 `.env`、换书时**整体替换**（上一本的覆盖必须撤掉）；
③ 项目文件（`.nwsproj`）：有覆盖才写 `[运行]` 段，读回来一模一样，老文件读回 `{}`；
④ 接线与联动：天机读**全局**、书斋写**覆盖**、起笔同步覆盖、运行面板读**有效值**，
   选一档两个数一起变、手改数字档位变「自定义」。

判据分组
  A 档位表（闭集 / 合法 / 互不相同 / 单调 / 精确反查）
  B 覆盖层（认覆盖 / 全局不受影响 / 不写进 .env / 整体替换 / 清空回全局）
  C 项目文件（写段 / 往返 / 老文件 / 空覆盖不写段）
  D 接线（AST：天机的读取闭包、书斋的写入闭包、不再有第二处写同一键、切书装覆盖、起笔同步）
  E 联动（选档位→两个数一起变；手改→变自定义；空值不写配置；运行面板跟着书斋走）
  F 反例（把关键实现各改坏一处，对应判据必须变红）

跑法：.venv\\Scripts\\python.exe tools/verify_detail_level.py
产出：assets/screenshots/detail_level_report.json

English:
Verify the **detail-level ladder** and the **project-level override on Study · Run**
(user request, 2026-10-30). Four things: the ladder table (closed set, valid numbers,
all distinct, exact reverse lookup); the override layer (`raw()` sees it, `g()` does not,
`save()` never writes it to `.env`, switching books replaces it wholesale); the project
file (a `[运行]` section only when there is something to write, round-trips, old files
read back as `{}`); and the wiring/linkage (Tianji reads the global layer, Study writes
the override, Start Writing mirrors it, the run panel reads the effective value; picking a
level moves both numbers, hand-editing turns the level into 自定义).
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from config import CFG, SPEC, Config                          # noqa: E402
from sim import pace as PACE                                  # noqa: E402
from store.project import Project                             # noqa: E402

OUT = APP / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)[:400]})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''), flush=True)
    return bool(cond)


#: 跑完要还原的配置项（别把用户的 `.env` 内存值改了就不还）
# [EN] Config keys to restore afterwards -- never leave the user's in-memory config modified.
_TOUCHED = ('BEAT_SECONDS', 'TIME_RATIO', 'TICK_REAL_MS', 'QUIET_MINUTES',
            'RUN_MODE', 'STORY_START_POINT', 'PLOT_ADHERENCE')
_ORIG = {}


def _snap() -> None:
    for k in _TOUCHED:
        _ORIG[k] = CFG.g(k)


def _restore() -> None:
    CFG.clear_overrides()
    for k, v in _ORIG.items():
        if v == '':
            CFG.set(k, '')
        else:
            CFG.set(k, v)


# ══════════════════════════════════════════════════════════════════════
#  A —— 档位表
# ══════════════════════════════════════════════════════════════════════
def _all_distinct(presets: dict) -> bool:
    """每档的两个数**互不相同**（有两档撞了 ⇒ 选了看不出区别，等于少一档）。"""
    seen = set()
    for v in presets.values():
        if tuple(v) in seen:
            return False
        seen.add(tuple(v))
    return True


def a_ladder() -> None:
    print('\n── A 档位表 ──')
    ok('A1 ★★★ 五档**闭集**且顺序 = 用户点名的顺序（很详细→带过）',
       PACE.DETAIL_LEVELS == ('很详细', '详细', '中间', '简略', '带过'),
       str(PACE.DETAIL_LEVELS))
    ok('A2 ★★★ 每档都**真有一组数**（缺一档 ⇒ 选了没反应）',
       all(lv in PACE.DETAIL_PRESETS for lv in PACE.DETAIL_LEVELS),
       str(sorted(PACE.DETAIL_PRESETS)))
    # 两个数都要落在 `config.SPEC` 的 min/max 里：越界会被 `coerce` 夹掉，
    # 界面上填 1800、跑起来变成 3600 这种事没人查得出来。
    # [EN] Both numbers must sit inside `config.SPEC`'s min/max: out of range they are clamped
    # [EN] by `coerce`, and "typed 1800, ran as 3600" is undetectable.
    bad = []
    for lv, (beat, ratio) in PACE.DETAIL_PRESETS.items():
        sb, sr = SPEC['BEAT_SECONDS'], SPEC['TIME_RATIO']
        if not (sb['min'] <= beat <= sb['max'] and sr['min'] <= ratio <= sr['max']):
            bad.append((lv, beat, ratio))
    ok('A3 ★★★ 每档的两个数都在 `config.SPEC` 的 min~max 里（越界会被静默夹掉）',
       not bad, str(bad))
    ok('A4 ★★★ 五档**互不相同**（两档撞了 ⇒ 选谁都一样，等于少一档）',
       _all_distinct(PACE.DETAIL_PRESETS), str(PACE.DETAIL_PRESETS))
    beats = [PACE.DETAIL_PRESETS[lv][0] for lv in PACE.DETAIL_LEVELS]
    ok('A5 ★★★ 「一拍」随档位**单调变长**（很详细最短、带过最长）',
       beats == sorted(beats) and len(set(beats)) == len(beats), str(beats))
    reals = [PACE.real_seconds_of(*PACE.DETAIL_PRESETS[lv]) for lv in PACE.DETAIL_LEVELS]
    ok('A6 ★★ 每拍真实秒落在 **30~200 秒**（太短=一天几分钟就演完，太长=一集等半天）',
       all(30 <= r <= 200 for r in reals), str([round(r, 1) for r in reals]))
    ok('A7 ★★★ 反查是**逐值相等**：匹配的认出来、不匹配的一律「自定义」',
       PACE.level_of(1800, 20) == '带过' and PACE.level_of(1799, 20) == PACE.DETAIL_CUSTOM
       and PACE.level_of(0, 1) == PACE.DETAIL_CUSTOM,
       f'{PACE.level_of(1800, 20)} / {PACE.level_of(1799, 20)}')
    ok('A8 ★★ `自定义`**不是档位**：`preset_of` 给 None、`apply_to` 给空字典'
       '（选了它必须什么都不改）',
       PACE.preset_of(PACE.DETAIL_CUSTOM) is None
       and PACE.apply_to(PACE.DETAIL_CUSTOM) == {},
       str(PACE.apply_to(PACE.DETAIL_CUSTOM)))
    ok('A9 ★★ `apply_to` 只回那两个键（多了就会顺手改掉别的运行参数）',
       set(PACE.apply_to('带过')) == {'BEAT_SECONDS', 'TIME_RATIO'},
       str(PACE.apply_to('带过')))


# ══════════════════════════════════════════════════════════════════════
#  B —— 覆盖层
# ══════════════════════════════════════════════════════════════════════
def b_override() -> None:
    print('\n── B 覆盖层 ──')
    CFG.clear_overrides()
    CFG.set('BEAT_SECONDS', '120')
    CFG.set_override('BEAT_SECONDS', '1800')
    ok('B1 ★★★ 覆盖之后 `raw()`/`i()` 读到的是**覆盖值**（推演循环、界面都读它）',
       CFG.i('BEAT_SECONDS') == 1800, str(CFG.i('BEAT_SECONDS')))
    ok('B2 ★★★ `g()`/`gi()` **不看覆盖**（天机改的是全局，读错了保存就会写脏 .env）',
       CFG.g('BEAT_SECONDS') == '120' and CFG.gi('BEAT_SECONDS') == 120,
       f'{CFG.g("BEAT_SECONDS")} / {CFG.gi("BEAT_SECONDS")}')
    ok('B3 ★★ `has()` 认覆盖（否则"这项设过没有"会答没设过）',
       CFG.has('BEAT_SECONDS'), '')
    # 空串**不算**覆盖 —— 与 `has()` 同一个口径；不然清一项会把值变成空。
    # [EN] An empty string is not an override (same rule as `has()`), else clearing a key
    # [EN] would leave an empty value.
    CFG.set_override('BEAT_SECONDS', '')
    ok('B4 ★★★ 覆盖值设为空串 = **取消覆盖**（回落到全局 120，而不是变成空）',
       CFG.i('BEAT_SECONDS') == 120, str(CFG.i('BEAT_SECONDS')))
    CFG.set_override('BEAT_SECONDS', '1800')
    # 写盘重定向到临时文件 —— 绝不碰用户真实 `.env`
    # [EN] Redirect the write to a temp file -- never touch the user's real `.env`.
    tmp = Path(tempfile.mkdtemp()) / 'env.txt'
    old_redirect = Config.redirect_save
    try:
        Config.redirect_save = tmp
        CFG.save()
        txt = tmp.read_text(encoding='utf-8')
    finally:
        Config.redirect_save = old_redirect
    ok('B5 ★★★ 落盘**不带覆盖值**（一本书的节奏不能变成整台机器的）',
       'BEAT_SECONDS=1800' not in txt and 'BEAT_SECONDS=120' in txt,
       '1800 in file' if 'BEAT_SECONDS=1800' in txt else 'ok')
    CFG.set_overrides({'TIME_RATIO': '20', 'BEAT_SECONDS': '1800'})
    CFG.set_overrides({'RUN_MODE': 'open'})
    ok('B6 ★★★ `set_overrides` 是**整体替换**：换书时上一本的覆盖必须**全撤**'
       '（否则这本书按上一本的节奏跑）',
       CFG.overrides() == {'RUN_MODE': 'open'} and CFG.i('BEAT_SECONDS') == 120,
       str(CFG.overrides()))
    CFG.clear_overrides()
    ok('B7 ★★ 清空之后完全回全局（老项目 / 没打开书时就是这个状态）',
       CFG.overrides() == {} and CFG.i('BEAT_SECONDS') == 120
       and CFG.i('TIME_RATIO') == int(_ORIG.get('TIME_RATIO') or 1),
       f'{CFG.i("BEAT_SECONDS")} / {CFG.i("TIME_RATIO")}')
    CFG.set_override('BEAT_SECONDS', '1800')
    ok('B8 ★★★ 覆盖**不影响 `as_dict()`**（那是"这台机器的配置"，用于导出/排查）',
       CFG.as_dict().get('BEAT_SECONDS') == 120, str(CFG.as_dict().get('BEAT_SECONDS')))
    CFG.clear_overrides()


# ══════════════════════════════════════════════════════════════════════
#  C —— 项目文件
# ══════════════════════════════════════════════════════════════════════
def c_project_file() -> None:
    print('\n── C 项目文件 ──')
    root = Path(tempfile.mkdtemp()) / '书一'
    root.mkdir(parents=True, exist_ok=True)
    p = Project(root=root, name='书一')
    p.write_nwsproj()
    txt = p.nwsproj_path.read_text(encoding='utf-8')
    ok('C1 ★★★ **没有覆盖就不写 `[运行]` 段**（老项目读回来就是"完全跟随天机"）',
       '[运行]' not in txt, 'has section' if '[运行]' in txt else 'no section')
    ok('C2 ★★ 真实项目读回来是**空覆盖**（不是补一堆默认值 —— 补了以后天机改了它不跟）',
       Project.from_nwsproj(p.nwsproj_path).run_overrides == {},
       str(Project.from_nwsproj(p.nwsproj_path).run_overrides))

    p.run_overrides = {'BEAT_SECONDS': '1800', 'TIME_RATIO': '20', 'RUN_MODE': 'open'}
    p.write_nwsproj()
    back = Project.from_nwsproj(p.nwsproj_path)
    ok('C3 ★★★ 写了覆盖 ⇒ 读回来**一模一样**（键、值都不许走样）',
       back.run_overrides == p.run_overrides, str(back.run_overrides))
    ok('C4 ★★ 键用**配置键名**（ASCII）而不是中文 —— 界面语言一换不能影响盘上的键',
       all(k.isascii() and k.isupper() for k in back.run_overrides),
       str(list(back.run_overrides)))

    # 造一份"老项目"：手工删掉 [运行] 段，确认照常能读
    # [EN] Simulate an old project: drop the section by hand and check it still reads.
    lines = p.nwsproj_path.read_text(encoding='utf-8').splitlines()
    keep, skip = [], False
    for ln in lines:
        if ln.strip().startswith('['):
            skip = ln.strip() == '[运行]'
        if not skip:
            keep.append(ln)
    p.nwsproj_path.write_text('\n'.join(keep), encoding='utf-8')
    old = Project.from_nwsproj(p.nwsproj_path)
    ok('C5 ★★★ 老项目文件（没有 `[运行]`）读回来是 `{}`，**不报错、不迁移**',
       old.run_overrides == {} and old.name == '书一', str(old.run_overrides))

    p2 = Project(root=root, name='书二', run_overrides={'BEAT_SECONDS': '', 'RUN_MODE': 'open'})
    ok('C6 ★★ 空值的键**不进** `run_overrides`（空 = 没设过，不是"设成空"）',
       p2.run_overrides == {'RUN_MODE': 'open'}, str(p2.run_overrides))


# ══════════════════════════════════════════════════════════════════════
#  D —— 接线（AST）
# ══════════════════════════════════════════════════════════════════════
def _func(tree, name: str):
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


def _calls(node, fname: str) -> list:
    out = []
    for n in ast.walk(node or ast.Module(body=[], type_ignores=[])):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id == fname:
                out.append(n)
            elif isinstance(f, ast.Attribute) and f.attr == fname:
                out.append(n)
    return out


def _lambda_attr(call, idx: int) -> str:
    """取 `call.args[idx]` 那个 lambda 体内调用的**属性名**（`CFG.gi` → `gi`）。"""
    try:
        a = call.args[idx]
    except IndexError:
        return ''
    if not isinstance(a, ast.Lambda):
        return ''
    body = a.body
    if isinstance(body, ast.Call) and isinstance(body.func, ast.Attribute):
        return body.func.attr
    return ''


def d_wiring() -> None:
    print('\n── D 接线 ──')
    src = (APP / 'gui' / 'app_flet.py').read_text(encoding='utf-8')
    tree = ast.parse(src)

    gl = _func(tree, 'show_global_settings')
    gl_pace = _calls(gl, 'mk_pace_block')
    ok('D1 ★★★ 天机用的是**同一套控件**（`mk_pace_block`），不是另画一份',
       len(gl_pace) == 1, f'{len(gl_pace)} 处')
    ok('D2 ★★★ 天机的**读**闭包是 `CFG.gi`（全局层）—— 读有效值会把某本书的数'
       '当全局显示、保存时写进 `.env`',
       bool(gl_pace) and _lambda_attr(gl_pace[0], 0) == 'gi',
       _lambda_attr(gl_pace[0], 0) if gl_pace else '')
    ok('D3 ★★★ 天机的**写**闭包是 `CFG.set`（写内存的全局层，落盘走「保存」）',
       bool(gl_pace) and _lambda_attr(gl_pace[0], 1) == 'set',
       _lambda_attr(gl_pace[0], 1) if gl_pace else '')

    bp = _func(tree, 'show_project_settings')
    bp_pace = _calls(bp, 'mk_pace_block')
    ok('D4 ★★★ 书斋也用同一套控件（两边各写一份 ⇒ 一改就漂）',
       len(bp_pace) == 1, f'{len(bp_pace)} 处')
    ok('D5 ★★★ 书斋的**读**闭包是 `CFG.i`（有效值 = 覆盖优先）',
       bool(bp_pace) and _lambda_attr(bp_pace[0], 0) == 'i',
       _lambda_attr(bp_pace[0], 0) if bp_pace else '')
    ok('D6 ★★★ 书斋的**写**闭包是 `_ov_write`（写项目覆盖，不是全局）',
       bool(bp_pace) and isinstance(bp_pace[0].args[1], ast.Name)
       and bp_pace[0].args[1].id == '_ov_write',
       ast.dump(bp_pace[0].args[1])[:60] if bp_pace else '')

    # 这三项**不许**再挂 `_live*`（那是写全局 + CFG.save），否则两处写同一个键
    # [EN] These three must not also be wired through `_live*` (global + CFG.save): two writers
    # [EN] for one key is exactly the trap.
    dup = []
    for fname in ('_live', '_live_dd'):
        for c in _calls(bp, fname):
            if c.args and isinstance(c.args[0], ast.Constant) and \
                    c.args[0].value in ('RUN_MODE', 'STORY_START_POINT', 'PLOT_ADHERENCE'):
                dup.append(c.args[0].value)
    ok('D7 ★★★ 书斋里这三个键**没有第二处写全局**（`_live*` 不再碰它们）',
       not dup, str(dup))

    act = _func(tree, '_activate_project')
    ok('D8 ★★★ 切书时**装这本书的覆盖**（`_activate_project` 是唯一"用户打开了某本书"的时刻）',
       bool(_calls(act, 'set_overrides')), '')
    st = _func(tree, 'show_start_story_dialog')
    ok('D9 ★★★ 起笔里选运行模式/起始点要**同步进覆盖**（否则覆盖压着全局，'
       '用户选了没反应）',
       bool(_calls(st, 'set_override')), '')
    bp_src = ast.dump(bp or ast.Module(body=[], type_ignores=[]))
    ok('D10 ★★ 「恢复跟随天机」只清这一页的键（`RUN_TAB_KEYS`），**没有** `clear_overrides()`'
       '（顺手全清会把以后加在别处的覆盖一起干掉）',
       'RUN_TAB_KEYS' in bp_src and '_reset_run_overrides' in bp_src
       and 'clear_overrides' not in bp_src,
       f"keys={'RUN_TAB_KEYS' in bp_src} clear={'clear_overrides' in bp_src}")


# ══════════════════════════════════════════════════════════════════════
#  E —— 联动（真控件、无窗口）
# ══════════════════════════════════════════════════════════════════════
def e_linkage() -> None:
    print('\n── E 联动 ──')
    import gui.app_flet as G

    vals = {'BEAT_SECONDS': 120, 'TIME_RATIO': 1}
    writes: list = []

    def _read(k):
        return vals.get(k, 1)

    def _write(k, v):
        vals[k] = int(v)
        writes.append((k, int(v)))

    blk = G.mk_pace_block(_read, _write, half_w=200)
    ok('E1 ★★ 打开时档位 = 当前两个数的档（120/1 ⇒ 详细），不是空白',
       blk['detail']._field.value == '详细', str(blk['detail']._field.value))

    writes.clear()
    blk['detail']._field.value = '带过'
    blk['detail']._field.on_change(NS(control=blk['detail']._field))
    ok('E2 ★★★ 选「带过」⇒ 时间倍率与一拍**一起变**（1800 故事秒 / 20×）',
       vals['BEAT_SECONDS'] == 1800 and vals['TIME_RATIO'] == 20, str(vals))
    ok('E3 ★★★ 两个输入框**也跟着刷新**（只写配置不刷框 = 界面上还是旧数）',
       blk['beat']._field.value == '1800' and blk['ratio']._field.value == '20',
       f"{blk['beat']._field.value} / {blk['ratio']._field.value}")
    _hint_txt = ''.join(getattr(s, 'text', '') for s in (blk['hint'].spans or []))
    ok('E4 ★★ 说明那句话跟着变（用 `set_hint`；写 `.value` 对带 spans 的 Text 静默无效）',
       '半小时' in _hint_txt and '真实秒' in _hint_txt, _hint_txt[:120])

    writes.clear()
    blk['beat']._field.value = '999'
    blk['beat']._field.on_change(NS(control=blk['beat']._field))
    ok('E5 ★★★ 手改一拍 ⇒ 写进去的是 999，且档位变回「自定义」'
       '（显示成"详细"就等于骗人）',
       ('BEAT_SECONDS', 999) in writes and blk['detail']._field.value == PACE.DETAIL_CUSTOM,
       f'{writes} / {blk["detail"]._field.value}')

    writes.clear()
    blk['ratio']._field.value = ''
    blk['ratio']._field.on_change(NS(control=blk['ratio']._field))
    ok('E6 ★★ 空值**不写配置**（否则一次误删就把倍率写成 0，`coerce` 会当 0 用）',
       not any(k == 'TIME_RATIO' for k, _ in writes), str(writes))

    writes.clear()
    blk['detail']._field.value = PACE.DETAIL_CUSTOM
    blk['detail']._field.on_change(NS(control=blk['detail']._field))
    ok('E7 ★★ 选「自定义」**什么都不改**（它只是显示值）', not writes, str(writes))

    # 运行面板的时间信息必须跟着**书斋**（有效值）走
    # [EN] The run panel's time info must follow the **Study** (the effective value).
    CFG.set('BEAT_SECONDS', '120')
    CFG.set('TIME_RATIO', '1')
    CFG.set_override('BEAT_SECONDS', '1800')
    CFG.set_override('TIME_RATIO', '20')
    feat = G.runtime_features()
    ok('E8 ★★★ 运行面板读的是**有效值**：书斋覆盖 20×/1800 ⇒ 面板显示 20×',
       feat['time_ratio'] == 20, str(feat['time_ratio']))
    ok('E9 ★★★ 面板那句节奏也按覆盖算（一拍 = 1800÷20 = 90 秒，不是 120 秒）',
       '90' in G.beat_pace_text(ratio=20, beat=1800),
       G.beat_pace_text(ratio=20, beat=1800))
    CFG.clear_overrides()
    ok('E10 ★★ 清掉覆盖 ⇒ 面板回到天机的全局值（"默认从全局继承"就是这条）',
       G.runtime_features()['time_ratio'] == int(_ORIG.get('TIME_RATIO') or 1),
       str(G.runtime_features()['time_ratio']))


# ══════════════════════════════════════════════════════════════════════
#  F —— 反例（把关键实现改坏一处，对应判据必须变红）
# ══════════════════════════════════════════════════════════════════════
def f_counter() -> None:
    print('\n── F 反例 ──')
    # ① 两档撞成同一组数 ⇒ A4 必须红
    bad = dict(PACE.DETAIL_PRESETS)
    bad['中间'] = bad['详细']
    ok('F1 ★★★ 反例①：把「中间」改成「详细」的数 ⇒ A4 变红（少一档却看不出来）',
       not _all_distinct(bad), str(bad['中间']))

    # ② `raw()` 不看覆盖 ⇒ B1 必须红
    CFG.set('BEAT_SECONDS', '120')
    CFG.set_override('BEAT_SECONDS', '1800')
    real_raw = Config.raw
    try:
        Config.raw = lambda self, key: self._raw.get(key, '')
        blind = CFG.i('BEAT_SECONDS')
    finally:
        Config.raw = real_raw
    ok('F2 ★★★ 反例②：`raw()` 不看覆盖 ⇒ B1 变红（书斋里怎么改都不生效）',
       blind == 120, str(blind))

    # ③ `save()` 写的是 `_raw` ⇒ B5 必然绿；这里反过来证明"若写的是有效值就会漏"
    # [EN] ③ `save()` writes `_raw`, so B5 is green by construction; show that writing the
    # [EN] effective value *would* leak.
    leaked = str(CFG.i('BEAT_SECONDS'))
    ok('F3 ★★★ 反例③：若 `save()` 写成有效值，`.env` 里就会出现 `BEAT_SECONDS=1800`'
       '（B5 抓的就是这件事）', leaked == '1800', leaked)

    # ④ 项目文件没有 `[运行]` 段还得能读 ⇒ C5 变红的情形是"读它就崩 / 补默认值"
    root = Path(tempfile.mkdtemp()) / '书三'
    root.mkdir(parents=True, exist_ok=True)
    p = Project(root=root, name='书三')
    p.write_nwsproj()
    ok('F4 ★★★ 反例④：老项目读回 `{}` 而不是补上当时的全局值'
       '（补了以后天机改了它不跟）',
       Project.from_nwsproj(p.nwsproj_path).run_overrides == {}, '')

    CFG.clear_overrides()


def main() -> int:
    print('=' * 62)
    print('  详细程度档位 · 书斋运行覆盖全局')
    print('=' * 62)
    _snap()
    try:
        for fn in (a_ladder, b_override, c_project_file, d_wiring, e_linkage, f_counter):
            try:
                fn()
            except Exception as e:                               # noqa: BLE001
                import traceback
                ok(f'{fn.__name__} 跑完', False, f'{e!r}')
                print(traceback.format_exc()[-900:])
    finally:
        _restore()
    n = len(report['checks'])
    good = sum(1 for c in report['checks'] if c['ok'])
    print(f'\n详细程度 / 运行覆盖验证：{good}/{n}')
    (OUT / 'detail_level_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if good == n else 2


if __name__ == '__main__':
    raise SystemExit(main())
