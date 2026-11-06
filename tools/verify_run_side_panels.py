# -*- coding: utf-8 -*-
"""真机/逻辑验证：**右栏「在场人物」「剧情」两块真的有内容**（2026-10-17）。

用户 2026-10-17 原话：
    「运行窗口右上角的在场任务和剧情现在一直没有任何信息显示
      把现在剧组这个Panel里的各个具体的演员 谁在表演的 全部移动到在场任务这里
      （只是移动到这里，其自己的状态 在做的事情 都跟其在剧组里的行为一样 不用修改）
      剧情这个panel你也要加上」

根因：**这两块是"造出来就没人管"的** ——
  · 内容是**写死的占位文案**（「尚无人物登场」/「节点 —」/「张力 — · 事件 —」）；
  · 句柄**一个都没存进 `_ui_run`** ⇒ 全仓没有任何一处刷得过它们
    ⇒ 从开拍到收工，这两块永远停在那一句占位。
  （本项目第四次栽在同一个坑上：时间面板 / 风格控制 / 起停输出 / 这里。）

修法：
  · 两块各自拿到**内容句柄**（`char_list` / `char_hint` / `plot_node` /
    `plot_body` / `plot_prog`），且挂进 `_ui_run`；
  · 「在场人物」接管台账里 `is_sub` 的那几行（`演员·X`），
    每一行仍走 `_ledger_row()` → `_crew_row()`（**搬家，不是改写**）；
  · 「剧组」跳过 `is_sub`（同一个人在两栏各占一行 = 看着像两个人）；
  · 「剧情」只读**推演自己记下的**四个值，不自己存、不自己算；
  · 两块都接在「剧组」那几个刷新点上（进界面 / 秒表 / 出工事件 / 收工）。

判据（行为为主，AST 接线为辅）：
  A 创建时**句柄真的交出去了**（AST 判语句）
  B 「在场人物」内容与行为（与剧组时期一致，且剧组里不再有它）
  C 「剧情」四个值随推演状态变（行为对照：改来源 → 文本跟着变）
  D 刷新点接线（AST：每处 `_refresh_crew_panel` 后都跟着这两块）
  E 真机：控件真的挂进界面，且真的被读出来

跑法：.venv\\Scripts\\python.exe tools/verify_run_side_panels.py
产出：assets/screenshots/run_side_panels_report.json
"""
from __future__ import annotations

import ast
import asyncio
import json
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

import flet as ft                                              # noqa: E402
from util.flet_shutdown import shutdown                         # noqa: E402
import verify_ui_common as VU                                  # noqa: E402

from config import CFG                                         # noqa: E402
# ⚠ 起界面的脚本第一条就是这个重定向：`CFG.save()` 会把测试值写进用户 `.env`。
# [EN] ⚠ Any UI-starting script begins with this redirect: CFG.save() would write the test values
# [EN] into the user's `.env`.
VU.redirect_env_writes()
CFG.set('MOCK_LLM', 'true')          # 零网络、零成本、可复现

from i18n import set_lang, t                                   # noqa: E402
set_lang('zh')

from crew import studio as ST                                   # noqa: E402
from gui.app_flet import NovelWorldApp                          # noqa: E402
# ⚠ 字号取**产品里的真实常量**，不要在这里另写一个 13.5：
#   判据算的是"排几行"，换字体档或改字号时必须跟着变，否则算出来的行数不再成立。
# [EN] Take the font size from the **real product constant**, never a local 13.5: the criterion
# [EN] computes rows, so it must follow when the size changes.
from gui.app_flet import HINT_FS                                 # noqa: E402
# ⚠ 夹具要用产品里那两个"行高 / 字号"常量：夹具与产品同构，
#   高度也用同一个来源，才不至于"夹具高度对不上产品"。
# [EN] The fixture uses the product's row-height/size constants so it stays structurally identical.
from gui.app_flet import PLOT_ROW_H                              # noqa: E402
# 跑马灯那两个三角按钮的宽度（夹具照抄产品，见上面那条纪律）。
# [EN] The carousel's triangle-button width (the fixture copies the product; see the rule above).
from gui.app_flet import PLOT_ARROW_W                            # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}
APP_PATH = APP_DIR / 'gui' / 'app_flet.py'


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


def _texts(ctl, out=None) -> list[str]:
    """递归收一个控件里所有 `Text.value`。
        English:
    Recursively collect all `Text.value` in a control.
    """
    if out is None:
        out = []
    if ctl is None:
        return out
    if isinstance(ctl, ft.Text) and ctl.value:
        out.append(str(ctl.value))
    for attr in ('controls', 'content'):
        v = getattr(ctl, attr, None)
        if isinstance(v, list):
            for c in v:
                _texts(c, out)
        elif v is not None:
            _texts(v, out)
    return out


# ══════════════════════════════════════════════════════════════
#  假体：只给面板要的那几样，不接真模型
# [EN] Fakes: only what the panels need, no real model
# ══════════════════════════════════════════════════════════════
class _FakeWorld:
    def __init__(self, names=None, think=None):
        # ⚠ 别写 `names or [...]`：传 `names=[]`（空场）会被当成"没传"，
        #   反而列出两个人在场 —— 判据自己把自己骗成红的（实测踩过）。
        # [EN] ⚠ Don't write `names or [...]`: passing `names=[]` (empty stage) would be treated as
        # [EN] "not passed", and it would instead list two people on stage -- the criterion fools
        # [EN] itself into going red (hit in practice).
        self._names = list(names) if names is not None else ['林黛玉', '贾宝玉']
        self._think = dict(think if think is not None
                           else {'林黛玉': '该不该把帕子收起来',
                                 '贾宝玉': '盯着那本书出神'})
        self.actor_think_at: dict = {}
        self.tension = 0.62
        self.current_node = 'N02'
        self.progress_nodes = [
            {'id': 'N01', '名称': '黛玉进府', '状态': '已完成',
             # ⚠ `概要` **必须给**（2026-10-21，反例法照出来的）：
             #   变异「用概要当显示文本」在这份夹具上**原本抓不到** ——
             #   因为夹具没有 `概要`，`nd.get('概要') or nd.get('名称')` 退化成名称，
             #   变异前后行为一模一样。真实数据里每个节点**都有**概要
             #   （实测「故事进度.yaml」四个节点全是长段复述），夹具不写真会把判据骗绿。
             # [EN] ⚠ `概要` **must be present** (found by the counterexample harness, 2026-10-21):
             # [EN] the "use 概要 as the label" mutation was **not caught** by this fixture, because
             # [EN] without it `nd.get('概要') or nd.get('名称')` degrades to the name and the mutation
             # [EN] behaves identically. Real data **always** has a 概要 (measured: all four nodes in
             # [EN] 故事进度.yaml are long recaps), so omitting it fools the criterion.
             '概要': '黛玉于扬州别父登舟北上，随楼经金陵站处理旧客委托，见账册笔迹似己'},
            {'id': 'N02', '名称': '宝钗初见', '状态': '进行中',
             '概要': '宝钗携金锁入府，众人议金玉良缘，黛玉闻之心内不忿却只笑'},
            {'id': 'N03', '名称': '共读西厢', '状态': '未开始',
             '概要': '二人于沁芳闸桥边同看西厢记，戏语相挑，情意始露'},
        ]

    def on_stage_names(self):
        return list(self._names)

    @property
    def actor_think(self):
        return self._think

    def current_node_info(self):
        for nd in self.progress_nodes:
            if nd.get('id') == self.current_node:
                return nd
        return None


class _FakeDirector:
    def __init__(self):
        self.events_this_round = 7


class _FakeLoop:
    def __init__(self, s, w):
        self.studio = s
        self.world = w
        self.director = _FakeDirector()


class _FakeSession:
    def __init__(self, lp):
        self.loop = lp


def _make_app(world, *, with_crew: bool = True):
    st = ST.Studio(world=world, db=None)
    st.mark_onduty()
    app = object.__new__(NovelWorldApp)
    ui = {'char_list': ft.Column(), 'char_hint': ft.Text(),
          'plot_node': ft.Text(), 'plot_body': ft.Text(),
          'plot_prog': ft.Text(),
          # ★★★ 2026-10-22 第三版：节点清单改成**跑马灯**（左三角 + 显示区 + 右三角），
          #   夹具必须**与产品同构**，否则判据会红在"夹具过期"上 ——
          #   那种红比不红更浪费时间：它让人去查产品，其实产品是对的。
          #   产品形状：`Container(height=行高) > GestureDetector > Row[三角, 胶囊, 三角]`
          #             胶囊 = `Container(expanded) > Text`
          # [EN] ★★★ 2026-10-22 third version: the node list is a **carousel** (left triangle +
          # [EN] display + right triangle). The fixture must be **structurally identical to the
          # [EN] product**, or criteria go red because the *fixture* is stale -- which sends you to
          # [EN] inspect a product that is in fact correct.
          'plot_nodes': ft.Container(
              content=ft.GestureDetector(
                  content=ft.Row(
                      [ft.Container(content=ft.Icon(ft.Icons.PLAY_ARROW),
                                    width=PLOT_ARROW_W, height=PLOT_ROW_H,
                                    rotate=ft.Rotate(angle=3.14159),
                                    on_click=lambda e: None),
                       ft.Container(content=ft.Text(), expand=True),
                       ft.Container(content=ft.Icon(ft.Icons.PLAY_ARROW),
                                    width=PLOT_ARROW_W, height=PLOT_ROW_H,
                                    on_click=lambda e: None)],
                      spacing=2, tight=True),
                  on_scroll=lambda e: None),
              height=PLOT_ROW_H),
          'plot_chip': None,        # 见下：与 `plot_nodes` 里的胶囊是同一个对象
          'plot_chip_txt': None,
          'plot_note': ft.Text(max_lines=1, visible=False)}
    # `plot_chip` / `plot_chip_txt` 就是上面那排里的第 2 个控件与它里面的 Text —
    # 产品里也是**同一对象**（`_ui_run` 存的是引用，不是副本），夹具照抄这一点。
    # [EN] `plot_chip` / `plot_chip_txt` are the 2nd control in that row and the Text inside it --
    # the product stores **the same object** (references, not copies), and the fixture copies that.
    ui['plot_chip'] = ui['plot_nodes'].content.content.controls[1]
    ui['plot_chip_txt'] = ui['plot_chip'].content
    if with_crew:
        ui['crew_list'] = ft.Column()
        ui['crew_hint'] = ft.Text()
    app._ui_run = ui
    app.session = _FakeSession(_FakeLoop(st, world))
    return app, st


# ══════════════════════════════════════════════════════════════
#  A —— 创建时句柄真的交出去了（AST 判语句）
# [EN] A -- the handles really are handed out at creation (AST statement judgment)
# ══════════════════════════════════════════════════════════════
def _ui_run_keys_of(fn) -> set:
    """函数体里所有 `self._ui_run['k'] = …` 的键。
        English:
    All the keys of `self._ui_run['k'] = …` in the function body.
    """
    keys: set = set()
    for n in ast.walk(fn):
        if not isinstance(n, ast.Assign):
            continue
        for tgt in n.targets:
            if not isinstance(tgt, ast.Subscript):
                continue
            if not (isinstance(tgt.value, ast.Attribute)
                    and tgt.value.attr == '_ui_run'):
                continue
            sl = tgt.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                keys.add(sl.value)
    return keys


def creation_checks() -> None:
    src = APP_PATH.read_text(encoding='utf-8')
    tree = ast.parse(src)
    fn = None
    for n in ast.walk(tree):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        hit = any(isinstance(c, ast.Constant)
                  and isinstance(c.value, str) and c.value == '在场人物'
                  for c in ast.walk(n))
        if hit:
            fn = n
            break
    ok('A0 ★ 找到造「在场人物」面板的那个函数', fn is not None, '')
    if fn is None:
        return
    keys = _ui_run_keys_of(fn)
    # ★★★ 这是**真因**：句柄不交出去，就没有任何一处刷得过它。
    # [EN] ★★★ This is the **root cause**: if the handle isn't handed out, nowhere can refresh it.
    ok('A1 ★★★ 造面板时把 `char_list` 句柄交给了 `_ui_run`'
       '（不交 ⇒ 全仓没人刷得过它 ⇒ 永远停在占位文案）',
       'char_list' in keys, f'keys={sorted(keys)}')
    ok('A2 ★ 同时交出了 `char_hint`（空场时那一句"尚无人物登场"）',
       'char_hint' in keys, f'keys={sorted(keys)}')
    for k in ('plot_node', 'plot_body', 'plot_prog'):
        ok(f'A3 ★★★ 造面板时把 `{k}` 句柄交给了 `_ui_run`'
           '（剧情那三行以前是写死的，没人改得动）',
           k in keys, f'keys={sorted(keys)}')
    # 反例：内容不再是"造好就写死的静态 Text"
    # [EN] Counterpart: the content is no longer a "static Text hardcoded at creation"
    body = ast.unparse(fn)
    ok('A4 ★★ 「在场人物」的内容是一个**空 Column**（不是写死一句占位就完事）',
       "ft.Column([], spacing=3" in body.replace('\n', ' ')
       or 'ft.Column([],' in body, '')


# ══════════════════════════════════════════════════════════════
#  B —— 「在场人物」：搬过来了，且说法一点没变
# [EN] B -- "On-stage Characters": moved, and the wording is unchanged
# ══════════════════════════════════════════════════════════════
def char_panel_checks() -> None:
    w = _FakeWorld()
    app, st = _make_app(w)
    app._refresh_crew_panel()
    app._refresh_char_panel()

    rows = st.ledger()
    subs = [r for r in rows if r.get('is_sub')]
    ctrls = app._ui_run['char_list'].controls
    ok('B1 ★★★ 「在场人物」每个在场角色一行（行数 = 台账 `is_sub` 行数）',
       len(ctrls) == len(subs) and len(subs) == 2,
       f'{len(ctrls)} rows / {len(subs)} subs')

    by_key = {r['key']: (r, c) for r, c in zip(subs, ctrls)}
    for nm in ('林黛玉', '贾宝玉'):
        key = f'actor::{nm}'
        r, c = by_key.get(key, (None, None))
        blob = ' | '.join(_texts(c)) if c is not None else ''
        duty = r['duty'] if r else ''
        # ★★★ "行为一样" 的三点半点名：名字 / 状态词 / 在做的事，全照台账。
        # [EN] ★★★ The three halves of "behaves the same", named one by one: name / status word /
        # [EN] what it's doing -- all verbatim from the ledger.
        ok(f'B2 ★★★ 「演员·{nm}」搬过来后**名字照旧**（`演员·{nm}`）',
           f'演员·{nm}' in blob, blob)
        ok(f'B3 ★★★ 「演员·{nm}」状态照旧：写「在岗」、不写「还没轮到」',
           '在岗' in blob and '还没轮到' not in blob, blob)
        ok(f'B4 ★★★ 「演员·{nm}」在做的事照旧：取自台账 `duty`（不是界面编的）',
           duty in blob, f'duty={duty!r} blob={blob}')
        # ★★★ 点击行为也照旧（在剧组里点一下是进该职位设置）。
        # [EN] ★★★ The click behavior is unchanged too (in Cast, one click opened that position's settings).
        ok(f'B5 ★★ 「演员·{nm}」行**仍可点**，且点的是它自己（`_crew_goto` '
           f'= {key}）',
           getattr(c, '_crew_goto', None) == key,
           f'_crew_goto={getattr(c, "_crew_goto", None)!r}')
        # 搬过来的父行不在同一栏了 ⇒ 那条缩进引导线撤掉（平铺）。
        # [EN] The parent row is no longer in the same column => that indent guide line is removed (flat).
        inner = c.content if getattr(c, '_crew_goto', None) is not None else c
        guided = isinstance(inner, ft.Row) and any(
            isinstance(cc, ft.Container) for cc in inner.controls)
        ok(f'B6 ★ 「演员·{nm}」在「在场人物」里**平铺**（没有那条指着空气的缩进线）',
           not guided, type(inner).__name__)

    # ── 搬走了 ⇒ 剧组那一栏不能再有它 ──
    # [EN] ── It moved => the Cast column must not have it anymore ──
    # ⚠ 判"面板里**真的**没有这一行"，不能只数行数 / 按位置 zip：
    #   不跳过子行那一版里「剧组」会多出两行，而 `zip(non_subs, crew_ctrls)`
    #   只取前 19 个 ⇒ 键集合看着完全正常 ⇒ 变异测试全绿（判据自己骗自己）。
    #   这里改成**从画出来的控件里读文字**，找「演员·X」这个名字。
    # [EN] ⚠ Judge "that row is **really** not on the panel", not row counts / positional zip:
    # [EN] in the version that doesn't skip sub-rows, "Cast" gains two extra rows, while
    # [EN] `zip(non_subs, crew_ctrls)` only takes the first 19 => the key set looks perfectly normal =>
    # [EN] the mutation goes green (the criterion fooling itself).
    # [EN] Here we **read the text out of the drawn controls** and look for the "演员·X" names.
    non_subs = [r for r in rows if not r.get('is_sub')]
    crew_ctrls = app._ui_run['crew_list'].controls
    crew_blobs = [' | '.join(_texts(c)) for c in crew_ctrls]
    leaked = [b for b in crew_blobs if '演员·' in b]
    ok('B7 ★★★ 「剧组」那一栏**不再列**角色子行'
       '（同一个人在右栏上下各占一行 = 看着像两个人在场）',
       not leaked and len(crew_ctrls) == len(non_subs),
       f'crew_rows={len(crew_ctrls)} vs 职位 {len(non_subs)}；漏在剧组里的={leaked}')

    # ── 空场 / 没会话：留占位，不预填 ──
    # [EN] ── Empty stage / no session: leave the placeholder, do not prefill ──
    w2 = _FakeWorld(names=[], think={})
    app2, st2 = _make_app(w2)
    app2._refresh_char_panel()
    ok('B8 ★★ 没人登场时「在场人物」空着，并显示「尚无人物登场」'
       '（不预填一个假人出来 —— 本项目的规矩）',
       len(app2._ui_run['char_list'].controls) == 0
       and app2._ui_run['char_hint'].visible is True,
       f"rows={len(app2._ui_run['char_list'].controls)}")
    app2.session = None
    app2._refresh_char_panel()
    ok('B9 ★ 没有会话时也不预填',
       len(app2._ui_run['char_list'].controls) == 0, '')

    # 有角色时那句提示要收起来（不然它一直占着一行）
    # [EN] With characters present, that hint must be tucked away (otherwise it keeps occupying a row)
    ok('B10 ★ 有人在场时收起「尚无人物登场」那句（不当屏幕钉子户）',
       app._ui_run['char_hint'].visible is False,
       f'visible={app._ui_run["char_hint"].visible}')


# ══════════════════════════════════════════════════════════════
#  C —— 「剧情」：四个值随推演状态变（行为对照）
# [EN] C -- "Plot": the four values follow the simulation state (behavior contrast)
# ══════════════════════════════════════════════════════════════
def plot_panel_checks() -> None:
    w = _FakeWorld()
    app, st = _make_app(w, with_crew=False)
    app._refresh_plot_panel()
    n0 = str(app._ui_run['plot_node'].value)
    b0 = str(app._ui_run['plot_body'].value)
    p0 = str(app._ui_run['plot_prog'].value)

    ok('C1 ★★★ 「节点」那一行走的是真数据：节点 id + 名称（不是「—」）',
       'N02' in n0 and '宝钗初见' in n0 and '—' not in n0, n0)
    ok('C2 ★★★ 「张力 · 事件」那一行走的是真数据（不是「—」）',
       '0.62' in b0 and '7' in b0 and '—' not in b0, b0)
    ok('C3 ★★★ 「进度表」那一行走的是真数据（已完成 1 / 共 3）',
       '1' in p0 and '3' in p0 and '—' not in p0, p0)

    # ── 行为对照：改来源 → 文本必须跟着变（证明不是硬编码） ──
    # [EN] ── Behavior contrast: change the source -> the text must follow (proves it isn't hardcoded) ──
    w.tension = 0.11
    app._refresh_plot_panel()
    b1 = str(app._ui_run['plot_body'].value)
    ok('C4 ★★★ 改 `world.tension` → 面板上的张力跟着变（读的是推演状态，不是硬编码）',
       '0.11' in b1 and b1 != b0, f'{b0} → {b1}')

    w.current_node = 'N03'
    app._refresh_plot_panel()
    n1 = str(app._ui_run['plot_node'].value)
    ok('C5 ★★★ 改 `world.current_node` → 面板上的节点跟着变（含新节点名）',
       'N03' in n1 and '共读西厢' in n1 and n1 != n0, f'{n0} → {n1}')

    app.session.loop.director.events_this_round = 42
    app._refresh_plot_panel()
    b2 = str(app._ui_run['plot_body'].value)
    ok('C6 ★★★ 改 `director.events_this_round` → 面板上的事件数跟着变',
       '42' in b2 and b2 != b1, f'{b1} → {b2}')

    w.progress_nodes[1]['状态'] = '已完成'
    app._refresh_plot_panel()
    p1 = str(app._ui_run['plot_prog'].value)
    ok('C7 ★★★ 进度节点标「已完成」→ 面板上的进度表跟着变（2/3）',
       '2' in p1 and p1 != p0, f'{p0} → {p1}')

    # ── 没有会话：留占位，不预填 ──
    # [EN] ── No session: leave the placeholder, do not prefill ──
    app.session = None
    app._refresh_plot_panel()
    n2 = str(app._ui_run['plot_node'].value)
    b3 = str(app._ui_run['plot_body'].value)
    p2 = str(app._ui_run['plot_prog'].value)
    ok('C8 ★★ 没会话时三行留占位「—」（不编一个"N01"出来骗人）',
       ('—' in n2) and ('—' in b3) and ('—' in p2),
       f'{n2} / {b3} / {p2}')

    # ── 没进度表时也不炸、不写 0/0 那种废话 ──
    # [EN] ── With no progress table it must not crash or write a useless 0/0 ──
    w2 = _FakeWorld()
    w2.progress_nodes = []
    app3, _ = _make_app(w2, with_crew=False)
    app3._refresh_plot_panel()
    p3 = str(app3._ui_run['plot_prog'].value)
    ok('C9 ★ 没有进度表时「进度表」留占位且不抛错（不写"0/0"那种废话）',
       '—' in p3, p3)


# ══════════════════════════════════════════════════════════════
#  F —— 节点清单 + 最近进展（2026-10-21 用户点名）
#
#  用户原话：「进度表这边是否可以把要进行的进度列出来（每个进度用几个字总结，
#  当前进度高亮）」。而"进度表一直不动"查下来是**判据确实没满足**
#  （望江楼 21:34→22:18 评估 14 次、7 次结论全 false），不是坏 —— 但模型每次
#  附的「进展描述」被旧代码丢掉了，所以界面上看不出它在动。这一组钉两件事：
#    · 节点**一条条列出来**，三种状态三种符号，当前那个高亮；
#    · 「走到哪儿了」**显示出来**（不论满足与否）。
#
# [EN] F -- node list + latest note (user request, 2026-10-21).
# [EN] "The progress table never moves" turned out to be **the criteria genuinely unmet**
# [EN] (Mowenlou 21:34->22:18: 14 evaluations, all 7 verdicts false), not a defect -- but the
# [EN] model's progress line was discarded by the old code, so nothing showed it was moving.
# [EN] This group pins two things: nodes **listed one per line** with three state glyphs and the
# [EN] current one highlighted; and "where we are" **shown**, satisfied or not.
# ══════════════════════════════════════════════════════════════
def _chips_of(container):
    """把节点清单里的**胶囊**按显示顺序摊平（不管它们排成几行）。

    ⚠ 不能按"第几行"取：行号随节点个数与名称长度变，不稳定（2026-10-22 改排法时踩过）。

        English:
    Flatten the **chips** in display order regardless of row layout.
    ⚠ Never index by row: row numbers shift with the node count and name length (hit while changing
    the layout on 2026-10-22).
    """
    inner = getattr(container, 'content', None)
    lines = (getattr(inner, 'controls', None) if inner is not None
             else getattr(container, 'controls', None)) or []
    out = []
    for ln in lines:
        out.extend(getattr(ln, 'controls', None) or [ln])
    return out


def plot_nodes_checks() -> None:
    w = _FakeWorld()
    app, _ = _make_app(w, with_crew=False)
    w.progress_note = '阿九见旧账落款笔锋与执壶手势暗合，线索初现'
    app._refresh_plot_panel()
    # ⚠ 每条都**自带异常边界**：判据自己抛异常会让**整组后面的判据全不跑**，
    #   而反例法会把那看成"变红了"（假红）。第一版就是这样：一条变异让 F1 崩掉，
    #   F2~F11 全没跑，报出来却是"F 组跑完 | Traceback"。
    # [EN] ⚠ Each check **has its own exception boundary**: a criterion that raises makes **every
    # [EN] later check in the group not run**, and the counterexample harness reads that as "went red"
    # [EN] (false red). The first version did exactly that: one mutation crashed F1, F2-F11 never ran,
    # [EN] yet it reported "F group finished | Traceback".
    def _safe(name: str, fn) -> None:
        try:
            fn()
        except Exception as e:                           # noqa: BLE001
            ok(name, False, f'抛异常：{e!r}')

    col = app._ui_run['plot_nodes']
    # ★★★ 2026-10-22 第三版：节点清单改成**跑马灯**（一次显示一条，左右翻）。
    #   所以 F 组原来的口径（"3 个节点 ⇒ 3 个胶囊同时铺开"）**整个失效了** ——
    #   那不是产品坏了，是我的假设过期了。
    #   ⇒ 换成跑马灯口径：
    #     · F1 = **可达性**（连转 N 次，N 条都出现过）—— "一条都不少"的正确量法；
    #     · F2 = 三种记号（● / ▶ / ○）在**界面上真的画出来了**；
    #     · F3 = 显示的是 `名称` 不是 `概要`；
    #     · F4/F5 = 停在当前站时才高亮，且高亮跟着 `current_node` 走。
    #   ⚠ 这不是放宽判据：H 组另有"只显示前 N 个就永远看不到剩下的"的反例法刀。
    # [EN] ★★★ 2026-10-22 third version: the node list is a **carousel** (one entry, stepped left/
    # [EN] right), so group F's old measure ("3 nodes => 3 chips laid out at once") **no longer
    # [EN] applies** -- not because the product broke, but because my assumption expired.
    # [EN] => Carousel measures: F1 = **reachability** (N steps surface all N, the right way to say
    # [EN] "not one node missing"); F2 = the three glyphs (● / ▶ / ○) really appear on screen;
    # [EN] F3 = the label is `名称`, not `概要`; F4/F5 = highlighted only while on the current station,
    # [EN] and the highlight follows `current_node`.
    # [EN] ⚠ This is not loosening: group H has its own counterexample knife for "show only the first
    # [EN] N, the rest unreachable".
    chip_txt = app._ui_run['plot_chip_txt']
    chip_box = app._ui_run['plot_chip']

    def _now() -> str:
        return str(chip_txt.value or '')

    # ── F1 可达性：从当前站出发连转 N 次，N 条都出现过 ──
    # ⚠ 用 `len(nodes)` 决定转几次，不写死 3：写死就成了"针对这份夹具优化"。
    # [EN] Step `len(nodes)` times, never a hard-coded 3 -- a literal would be "tuned for this
    # [EN] fixture".
    _n_nodes = len(w.progress_nodes)
    _seen: list[str] = []
    for _ in range(_n_nodes):
        _seen.append(_now())
        app._plot_step(1)
    ok('F1 ★★★ 节点**一条都不少**：连转 ' + str(_n_nodes) + ' 次，'
       + str(_n_nodes) + ' 条全部出现过（跑马灯口径 = **可达性**，不是"同屏铺开"）',
       len(set(_seen)) == _n_nodes and all(_s.strip() for _s in _seen),
       str(_seen))

    # ── F2 三种记号都在界面上画出来了 ──
    # ★ 判的是**屏幕上那一条文字的开头**，不是纯函数的返回值（那是 H1 的事）：
    #   H1 证明"该用什么记号"，F2 证明"真的用上了"。
    # [EN] Judge **the first character of the line on screen**, not the pure function's return (that is
    # H1): H1 proves "what glyph it should be", F2 proves "it is actually used".
    _marks = {s.strip()[:1] for s in _seen if s.strip()}
    ok('F2 ★★★ 已完成 / 正在演 / 未到 三种记号在界面上**都用到了**（● / ▶ / ○）',
       {'●', '▶', '○'} <= _marks, f'走一圈看到的记号：{sorted(_marks)}')

    # ── F3 显示的是 `名称`（几个字），不是 `概要`（一整段） ──
    # ★ 拿 `概要` 里的特征词反向验："扬州"只出现在 N01 的概要里，界面上不该有。
    # [EN] Reverse-check with a word from the 概要: "扬州" only appears in N01's recap and must not be
    # on screen.
    ok('F3 ★★★ 显示的是 `名称`（几个字），**不是 `概要`**（一整段剧情）',
       all(len(s.strip()) <= 12 for s in _seen)
       and any('黛玉进府' in s for s in _seen)
       and not any(('扬州' in s or '金锁' in s) for s in _seen),
       str(_seen))

    # ── F4 停在当前站时才高亮（底色 / 金边 / 加粗，至少两样） ──
    # ⚠ 跑马灯一次只显示一条，所以"其它两行没高亮"要**翻过去看**，不能读同一屏。
    # [EN] ⚠ The carousel shows one entry, so "the others are not highlighted" requires **stepping
    # over** and looking, not reading one screen.
    def _style_now() -> dict:
        return {
            'bg': bool(getattr(chip_box, 'bgcolor', None)),
            'border': getattr(chip_box, 'border', None) is not None,
            'bold': bool(getattr(chip_txt, 'weight', None) == ft.FontWeight.W_600),
        }

    # 先翻到当前站（▶ 那条）
    _cur_style, _other_style = {}, {}
    for _ in range(len(w.progress_nodes)):
        if '▶' in _now():
            _cur_style = _style_now()
        elif not _other_style:
            _other_style = _style_now()
        app._plot_step(1)
    ok('F4 ★★★ 停在**当前站**时高亮（底色/金边/加粗 至少两样），翻到别站时**不高亮**',
       sum(_cur_style.values()) >= 2 and sum(_other_style.values()) == 0,
       f'当前站={_cur_style} 别站={_other_style}')

    # ── F5 高亮跟着 `current_node` 走（不是"永远第一站亮"） ──
    w.current_node = 'N03'
    w.progress_nodes[1]['状态'] = '未开始'      # 取消"进行中"，让判当前只能靠 current_node
    app._refresh_plot_panel()
    _lit = []
    for _ in range(len(w.progress_nodes)):
        _lit.append((_now(), sum(_style_now().values())))
        app._plot_step(1)
    _lit_ones = [t for t, n in _lit if n >= 2]
    ok('F5 ★★★ 高亮跟着 `current_node` 走（把当前改成 N03 ⇒ 亮的是「共读西厢」，且只亮一条）',
       len(_lit_ones) == 1 and '共读西厢' in _lit_ones[0],
       str(_lit))

    # 「走到哪儿了」—— 这条是"一直不动"那个观感的答案
    # [EN] "Where we are" -- the answer to the "never moves" impression
    note = app._ui_run['plot_note']
    ok('F6 ★★★ 面板上显示**最近一次「走到哪儿了」**（模型判"还没满足"时也给的那句话）',
       '线索初现' in str(note.value) and bool(getattr(note, 'visible', False)),
       f'{note.value!r} visible={getattr(note, "visible", None)}')

    w.progress_note = ''
    app._refresh_plot_panel()
    ok('F7 ★★ 没有进展描述时那一行**收起来**（不留一条空白，看着像坏了）',
       not bool(getattr(note, 'visible', True)), f'visible={getattr(note, "visible", None)}')

    # ★★★ F12：**真实数据那种情况** —— 设定集里所有节点都写着「未开始」，
    #   而 `current_node` 指着第一个。这是**望江楼项目的实际状态**
    #   （实测 yaml：四个节点全是 `状态: 未开始`，`current_node=N01`），
    #   而第一版按 `状态=='进行中'` 判当前 ⇒ **四个全是 ○，当前那个不高亮**，
    #   用户点名要的"当前进度高亮"当场落空。
    #   ⇒ 这条钉的是"判当前**以 current_node 为准**"。
    # [EN] ★★★ F12: **the real-data shape** -- every node in the settings file says "not started"
    # [EN] while `current_node` points at the first. That is the **actual state of the Mowenlou
    # [EN] project** (measured yaml: all four nodes `状态: 未开始`, `current_node=N01`), and the first
    # [EN] version decided "current" by `状态 == '进行中'` => **four ○, no highlight**, so the thing
    # [EN] the user asked for silently failed. This check pins "current is decided by current_node".
    # ★ 跑马灯口径：这两条现在要**翻到那一站**再判，而不是读"铺开后的第 N 行"。
    # [EN] Carousel measure: these two now **step to that station** and judge it, instead of reading
    # "the Nth row of the laid-out list".
    def _style_of(a, nodes_n: int, want: str) -> tuple[dict, str]:
        """翻一圈，返回**名字含 `want` 的那一站**的样式与文字（找不到返回空）。"""
        for _ in range(nodes_n):
            txt = str(a._ui_run['plot_chip_txt'].value or '')
            if want in txt:
                box = a._ui_run['plot_chip']
                tx = a._ui_run['plot_chip_txt']
                return ({'bg': bool(getattr(box, 'bgcolor', None)),
                         'border': getattr(box, 'border', None) is not None,
                         'bold': bool(getattr(tx, 'weight', None) == ft.FontWeight.W_600)}, txt)
            a._plot_step(1)
        return {}, ''

    w5 = _FakeWorld()
    for nd in w5.progress_nodes:
        nd['状态'] = '未开始'
    w5.current_node = 'N01'
    app5, _ = _make_app(w5, with_crew=False)
    app5._refresh_plot_panel()
    _s5, _t5 = _style_of(app5, len(w5.progress_nodes), '黛玉进府')
    _s5b, _t5b = _style_of(app5, len(w5.progress_nodes), '宝钗初见')
    ok('F12 ★★★ 设定集里全是「未开始」时，**当前那个仍然高亮**（按 `current_node` 判，'
       '不按 `状态` —— 望江楼项目的真实状态就是这样）',
       sum(_s5.values()) >= 2 and sum(_s5b.values()) == 0,
       f'当前站 {_t5!r} {_s5} / 别站 {_t5b!r} {_s5b}')

    # ★★★ F13：**当前节点已经标了「已完成」**（走到最后一站时 `advance_node` 会这样）
    #   ⇒ 那时该显示 ●（演完了），不该还顶着"当前"的高亮（否则"走完了"和"正走着"长得一样）。
    # [EN] ★★★ F13: the current node is **already marked done** (what `advance_node` does at the last
    # station) => show ● then, not the "current" highlight (otherwise "finished" and "walking" look
    # identical).
    w6 = _FakeWorld()
    w6.current_node = 'N03'
    w6.progress_nodes[2]['状态'] = '已完成'
    app6, _ = _make_app(w6, with_crew=False)
    app6._refresh_plot_panel()
    _s6, _t6 = _style_of(app6, len(w6.progress_nodes), '共读西厢')
    ok('F13 ★★ 当前节点已标「已完成」时显示 **●** 而不是"当前"高亮（别把走完的还当在走）',
       '●' in _t6 and sum(_s6.values()) == 0,
       f'{_t6!r} {_s6}')

    # ══════════════════════════════════════════════════════════
    #  G —— **高度与节点个数彻底无关**（跑马灯）
    #
    #  三轮演进（都是用户点出来的）：
    #   ① 「保证显示所有剧情的同时让 Panel 更矮，我想让下面的剧组 Agents 都显示出来」
    #   ② 「**每个项目每次推演剧情个数都不同，你需要改变设计**，而不是针对当前特定推演优化」
    #   ③ 「各个剧情是否可以通过**跑马灯**的形式展示」（2026-10-22 第三轮）
    #
    #  ★★★ 所以这一组**不许出现任何"10 个节点"这种具体规模**。判据要证明的是一条
    #    **性质（invariant）**：不论 N 是多少，这块的高度**是同一个常数**。
    #    第一版拿 10 个节点算账、还写死 `rows <= 5`，那正是在"针对特定推演优化"。
    #  ★ 跑马灯让这条性质达到极限形式：不是"不超过上界"，而是**恒等于一行**
    #    （1 个节点和 200 个节点一样高）。判据因此从"≤ cap"改成"全部相等且等于 cap"——
    #    更强，而不是更松。
    #
    #  ★ 判据用**产品自己的 `_plot_nodes_height`**，不另写一套估算：
    #    判据自己估一套的话，迟早"判据说 1 行、界面 2 行"，而两边都自认为对。
    # [EN] G -- **the height is completely independent of the node count** (the carousel).
    # [EN] Three rounds, all prompted by the user: (1) "shorter while still showing all the plot so the
    # [EN] Cast fits"; (2) "**every project has a different node count -- change the design**, don't
    # [EN] optimise for the current run"; (3) "can the plot points be shown as a **carousel**".
    # [EN] ★★★ So no concrete scale may appear here. What is proven is an **invariant**: for any N the
    # [EN] height is **one constant**. The first version did the arithmetic for ten nodes and
    # [EN] hard-coded `rows <= 5` -- exactly "optimising for the current run".
    # [EN] ★ The carousel takes the invariant to its limit: not "at most a bound" but **identically one
    # [EN] row** (1 node and 200 nodes are the same height). The criterion therefore moves from
    # [EN] "<= cap" to "all equal and equal to cap" -- stronger, not looser.
    # [EN] ★ The criteria use the product's **own** `_plot_nodes_height`, never a second estimate.
    # ══════════════════════════════════════════════════════════
    # ★★★ 2026-10-22：**这条必须判产品源码，不能判夹具**。
    #   判 `app._ui_run['plot_nodes']` 等于判我在 `_make_app` 里手写的那个控件 ——
    #   产品改成裸 `Column`，夹具照样是 Container ⇒ 永远绿 ⇒ **测了个空**。
    # [EN] ★★★ 2026-10-22: **this must judge the product source, not the fixture.** Judging
    # [EN] `app._ui_run['plot_nodes']` judges the control **I wrote by hand** in `_make_app`: changing
    # [EN] the product to a bare `Column` leaves the fixture a Container => always green => nothing
    # [EN] measured.
    _src = (APP_PATH).read_text(encoding='utf-8')
    _has_box = 'plot_nodes = ft.Container(content=plot_node_rows' in _src
    _has_carousel = 'plot_node_rows = ft.GestureDetector(' in _src
    ok('G1 ★★★ 节点清单是**定高容器 + 跑马灯**（不是让它随内容长高）—— '
       '这是"高度与节点个数无关"的结构前提（**判产品源码**）',
       _has_box and _has_carousel,
       f'产品里定高容器={_has_box} 跑马灯(GestureDetector)={_has_carousel}')

    # ⚠ 把这条判据要用的常量**全列上**：漏一个就是运行期 `NameError`，
    #   而它发生在 G 段中途 ⇒ 后面的判据全不跑（本项目反复踩的坑）。
    # [EN] List **every** constant this block uses: a missing one is a runtime `NameError`
    # midway through the G block, and every later criterion then never runs.
    from gui.app_flet import (PLOT_ROW_H, PLOT_CHIP_FS, PLOT_CHIP_W,   # noqa: E402
                              PLOT_ARROW_W, PLOT_CAROUSEL_W,
                              plot_carousel_step, plot_node_mark,
                              plot_carousel_pick, plot_wheel_step)

    # ── ★ 核心断言：**任意规模都是同一个高度** ──
    # 规模列表故意跨两个数量级（0 → 200），并包含奇数、质数，避免"只对某些倍数成立"。
    # [EN] The scale list spans two orders of magnitude (0 -> 200) and includes odd/primes, so
    # "only true for multiples" cannot sneak through.
    cap = PLOT_ROW_H
    # ⚠ 规模必须**包含 4**：常见规模（4~6 站）也要被测到，且下面几条引用了 `heights[4]`。
    #   第一版列表里没有 4，`KeyError: 4` 把整段打断（G4~G9 一条都没跑）。
    # [EN] The list **must include 4** (the common 4-6 station case) and later rows index
    # `heights[4]`; omitting it once raised `KeyError: 4` and cut the whole tail of the block.
    scales = (0, 1, 2, 3, 4, 6, 10, 20, 50, 100, 200)
    heights = {n: app._plot_nodes_height(n) for n in scales}
    ok('G2 ★★★ **不论多少个节点，这块高度都是同一个常数**'
       f'（1 行 = {cap}px）—— 这才是"与节点个数无关"',
       all(abs(h - cap) < 0.5 for h in heights.values()),
       ' / '.join(f'{n}个:{h:.0f}px' for n, h in heights.items()))

    bigger = [n for n in scales if n >= 20]
    ok('G3 ★★★ 大节点数**全部等于同一个高度**（' + ' / '.join(str(n) for n in bigger)
       + ' 个都一样）',
       len({heights[n] for n in bigger}) == 1 and heights[bigger[-1]] == cap,
       str({n: heights[n] for n in bigger}))

    # ★ 跑马灯下这条变成"恒等"：**1 个节点与 200 个节点完全一样高**。
    #   原来（wrap / 2 行滚动）是"少的时候矮一点、多的时候封顶"，高度仍然跟着 N 走。
    # [EN] Under the carousel this becomes identity: **1 node and 200 nodes are exactly as tall**.
    # [EN] Before (wrap / 2-row scroll) it was "shorter when few, capped when many" -- the height still
    # [EN] tracked N.
    ok('G4 ★★★ 1 个节点与 200 个节点**高度完全相同**（不预留空白、也不因多而长高）',
       heights[1] == heights[200] == cap,
       f'1个={heights[1]:.0f}px  200个={heights[200]:.0f}px  上界={cap}px')

    outs = [heights[n] for n in scales]
    ok('G5 ★★ 高度随节点数**完全不变**（不是"单调不降"，是恒定）',
       all(abs(x - cap) < 0.5 for x in outs), str([f'{x:.0f}' for x in outs]))

    # ★★ 比"竖排"省下多少 —— 拿**同一个 N** 比两种排法（排法之间的对比，不是"针对某个 N 优化"）。
    # [EN] ★★ How much it saves versus a vertical list, at the **same** N -- a comparison between
    # layouts, not "tuned for one N".
    vert_10 = 10 * (PLOT_ROW_H + 1)          # 竖排：每行 + 上下各 1px（原实现）
    ok('G6 ★★★ 同规模下比竖排省得多（10 站：竖排约 '
       f'{vert_10:.0f}px → 现在 {heights[10]:.0f}px）—— "更矮"这个诉求真的达成了',
       vert_10 - heights[10] >= 100, f'省 {vert_10 - heights[10]:.0f}px')

    # ── 「走到哪儿了」也压到 1 行 ──
    # ⚠ `note_ctl` 来自**夹具**，判它等于判我自己手写的那个值；从产品源码里取 `max_lines=N`。
    # [EN] `note_ctl` comes from the fixture, so judging it judges my own value; read `max_lines=N`
    # from the product source instead.
    import re as _re2
    _m_note = _re2.search(r'plot_note = ft\.Text\((?:[^)]|\n)*?max_lines=(\d+)', _src)
    _note_lines = int(_m_note.group(1)) if _m_note else -1
    ok('G7 ★★ 「走到哪儿了」限 **1 行**（原 2 行，值一行高度；完整内容在中栏消息里；'
       '**判产品源码**）',
       _note_lines == 1, f'产品 max_lines={_note_lines}')

    # 胶囊上下 padding 必须是 0（否则一行就不止 `PLOT_ROW_H` 了）
    # [EN] Chip vertical padding must be 0, or one row exceeds `PLOT_ROW_H`.
    _chip_pads = _re2.findall(r'padding=ft\.Padding\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)', _src)
    _pad0 = [p for p in _chip_pads if p[0] == '4' and p[2] == '4']
    ok('G8 ★★ 跑马灯胶囊上下 padding 都是 **0**（高度只由字号决定；'
       '**判产品源码**，`Padding(4, 0, 4, 0)`）',
       bool(_pad0) and all(p[1] == '0' and p[3] == '0' for p in _pad0),
       f'找到的胶囊 padding：{_pad0}')

    # ══════════════════════════════════════════════════════════
    #  H —— **跑马灯真的能转**（2026-10-22 用户点名）
    #
    #  用户原话：「我可以通过左右按钮（三角形）或者鼠标中间按键旋转的形式快速查看
    #  剧情列表，同时当前剧情会被显示出来并且前面的圆圈会变成满的，没有上演的剧情
    #  前面的圆圈则是空的，进度表的数字也跟着变化」。
    #
    #  ★ 这一组全部**真调产品方法**（`app._plot_step` / `_plot_paint_carousel`），
    #    不读夹具的 lambda —— 滚轮方向那一层已经抽成 `plot_wheel_step` 纯函数，
    #    测它就是测产品（夹具里的 `on_scroll` 是空 lambda，测它等于测空气）。
    #  ★ 判的是**行为**：转一下内容真的变了、到头真的绕回去、刷新不把位置拉回去。
    # [EN] H -- **the carousel really turns**. The user's words are quoted above.
    # [EN] ★ Everything here **calls real product methods** (`app._plot_step` /
    # [EN] `_plot_paint_carousel`) and never the fixture's lambda -- the wheel direction is already a
    # [EN] pure function (`plot_wheel_step`), so testing it tests the product (the fixture's `on_scroll`
    # [EN] is an empty lambda, and testing that measures the air).
    # [EN] ★ It judges **behaviour**: one step really changes the content, hitting an end really wraps,
    # [EN] and a refresh does not pull the position back.
    # ══════════════════════════════════════════════════════════
    # 四个节点，第 2 站是当前站（`current_node`），第 1 站已完成 ——
    # 这样三种记号（● / ▶ / ○）都有。
    w_car = _FakeWorld()
    w_car.progress_nodes = [
        {'id': 'N01', '名称': '黛玉进府', '状态': '已完成', '概要': 'x', '完成判据': 'y'},
        {'id': 'N02', '名称': '宝钗初见', '状态': '未开始', '概要': 'x', '完成判据': 'y'},
        {'id': 'N03', '名称': '共读西厢', '状态': '未开始', '概要': 'x', '完成判据': 'y'},
        {'id': 'N04', '名称': '焚稿断情', '状态': '未开始', '概要': 'x', '完成判据': 'y'},
    ]
    w_car.current_node = 'N02'
    app_car, _ = _make_app(w_car, with_crew=False)
    app_car._refresh_plot_panel()

    def _chip() -> str:
        return str(app_car._ui_run['plot_chip_txt'].value or '')

    def _prog() -> str:
        return str(app_car._ui_run['plot_prog'].value or '')

    # H1 三个记号的含义（纯函数，产品与判据共用）
    ok('H1 ★★★ 记号的含义：**演过的实心 `●` / 没演的空心 `○` / 正在演的 `▶`**'
       '（用户原话：「圆圈会变成满的…没有上演的…则是空的」）',
       plot_node_mark(done=True, is_current=False) == '●'
       and plot_node_mark(done=False, is_current=False) == '○'
       and plot_node_mark(done=False, is_current=True) == '▶'
       # 已完成优先：走到最后一站会被标完成，那时是"全演完了"，不该再留"正在"
       and plot_node_mark(done=True, is_current=True) == '●',
       f"{plot_node_mark(done=True, is_current=False)}"
       f"{plot_node_mark(done=False, is_current=True)}"
       f"{plot_node_mark(done=False, is_current=False)}")

    # H2 左右两个三角按钮都在、而且**真的挂上了回调**（源码级：夹具里是空 lambda）
    # ⚠ 2026-10-26：行里**多了一个**「剧情总览」按钮（`plot_flow_btn`）。判据原来
    #   写死了右括号（`plot_next_btn]`），于是"功能加了、判据没跟上"直接变红。
    #   它要守的其实是 **三个跑马灯元素按这个顺序在同一行**，不是"行里只有三个" ——
    #   改成允许后面还有别的（`(?:,|])`）。
    # [EN] ⚠ 2026-10-26: the row gained a "story overview" button (`plot_flow_btn`). The check used
    # [EN] to hard-code the closing bracket, so "a feature was added" turned it red. What it must
    # [EN] guard is **those three carousel elements in this order in one row**, not "only three".
    _m_row = _re2.search(
        r'ft\.Row\(\[plot_prev_btn, plot_chip, plot_next_btn(?:,|\])', _src)
    _has_click = '_mk_arrow(-1' in _src and '_mk_arrow(+1' in _src
    _has_wheel = 'on_scroll=_on_wheel' in _src and 'plot_wheel_step(' in _src
    ok('H2 ★★★ 左右两个三角按钮都挂着 `_plot_step(±1)`，滚轮也接在 '
       '`GestureDetector.on_scroll` 上（**判产品源码** —— '
       '夹具里那些 `lambda e: None` 测不出东西）',
       bool(_m_row) and _has_click and _has_wheel,
       f'Row={bool(_m_row)} 三角回调={_has_click} 滚轮={_has_wheel}')

    # H3 三角是**矢量图标**（`PLAY_ARROW`），不是字符 `◀`/`▶`：
    #    字符的宽高与基线由字体决定，换字体就忽大忽小（启动画面那一版踩过）。
    ok('H3 ★★ 三角是**矢量图标**（`ft.Icons.PLAY_ARROW`，左那个旋转 180°），'
       '不是字符 `◀`/`▶`（字符的宽高随字体漂）',
       'ft.Icons.PLAY_ARROW' in _src and 'ft.Rotate(angle=math.pi)' in _src,
       f"PLAY_ARROW={'ft.Icons.PLAY_ARROW' in _src} 左三角旋转={'ft.Rotate(angle=math.pi)' in _src}")

    # H4 一打开**就停在当前站**（用户不用先翻才能看到自己在哪）
    ok('H4 ★★★ 打开面板就停在**当前站**（`current_node`），不是从头开始',
       '▶ 宝钗初见' in _chip(), f'当前显示 {_chip()!r}')

    # H5 点右三角 ⇒ 真的走到下一站
    before = _chip()
    app_car._plot_step(1)
    ok('H5 ★★★ 点右三角 ⇒ **显示下一站**（内容真的变了）',
       _chip() != before and '共读西厢' in _chip(),
       f'{before!r} → {_chip()!r}')

    # H6 到头**绕回去**（不是停住 = 用户以为按钮坏了）
    app_car._plot_step(1)               # 到 N04
    app_car._plot_step(1)               # 越界 ⇒ 应绕回 N01
    ok('H6 ★★★ 到最后一站再点右三角 ⇒ **绕回第一站**（不是停在原地 —— '
       '停住会让人以为按钮坏了）',
       '黛玉进府' in _chip(), f'现在 {_chip()!r}')

    # H7 第一站再点左三角 ⇒ 绕到最后一站
    app_car._plot_step(-1)
    ok('H7 ★★★ 在第一站点左三角 ⇒ **绕到最后一站**',
       '焚稿断情' in _chip(), f'现在 {_chip()!r}')

    # H8 滚轮方向（纯函数）：向下滚 = 下一站，向上滚 = 上一站
    class _WheelEvent:
        def __init__(self, d):
            self.scroll_delta = d

    ok('H8 ★★★ 滚轮方向：向下滚(+)=下一站、向上滚(-)=上一站，'
       '而且**只取符号**（一次滚 120px 也只走一格，不然一下飞过好几站）',
       plot_wheel_step(_WheelEvent(120)) == 1
       and plot_wheel_step(_WheelEvent(-120)) == 1 * -1
       and plot_wheel_step(_WheelEvent(0)) == 0
       and plot_wheel_step(object()) == 0,
       f"+120→{plot_wheel_step(_WheelEvent(120))} "
       f"-120→{plot_wheel_step(_WheelEvent(-120))} "
       f"0→{plot_wheel_step(_WheelEvent(0))} 无属性→{plot_wheel_step(object())}")

    # H9 「看第 i/n」跟着翻，而**已完成数不跟着翻**（那是事实，翻页改变不了它）
    _p0 = _prog()
    app_car._plot_step(1)
    _p1 = _prog()
    _num = _re2.findall(r'(\d+)/(\d+)', _p0 + ' ' + _p1)
    ok('H9 ★★★ 进度行的**位置指示跟着翻**（`看第 i/n`），'
       '而"已完成 a/b"**不跟着翻**（那是事实，翻页改不了它）',
       _p0 != _p1 and '已完成' in _p0 and '已完成' in _p1
       and _p0.split('已完成')[0] == _p1.split('已完成')[0]
       and len(_num) >= 2,
       f'{_p0!r} → {_p1!r}')

    # ★★★ H9b：**数字要"对"，不只是"会动"**。
    #   反例法 ⑮（位置用上一帧的索引 ⇒ 总晚一格）在只有 H9 时**抓不到** ——
    #   因为 H9 只问"变没变"。用户看到的"第 3/4"其实是第 2 站，那才是真病。
    #   ⇒ 翻到第 k 站（k 由循环算出来，不写死），解析 `看第 X/n`，X 必须等于 k+1。
    # [EN] ★★★ H9b: the number must be **right**, not merely "changing". Mutation ⑮ (indicator uses
    # the previous frame's index, so it always lags one step) is **invisible to H9 alone**, because H9
    # only asks "did it change". A user seeing "3/4" while actually on station 2 is the real disease.
    # So step to station k (computed, not hard-coded) and check X == k+1.
    _pos_ok, _pos_detail = True, []
    for _k in range(len(w_car.progress_nodes)):
        for _ in range(_k):
            app_car._plot_step(1)
        _want_i = int(_re2.search(r'看第 (\d+)/', _prog()).group(1)) if _re2.search(
            r'看第 (\d+)/', _prog()) else -1
        # 用显示的站名反推"实际停在第几个"，再和数字比
        _shown = _chip()
        _real = next((j + 1 for j, nd in enumerate(w_car.progress_nodes)
                      if str(nd.get('名称') or '') in _shown), -1)
        _pos_detail.append(f'{_shown.strip()[:6]}→第{_want_i}')
        if _real != _want_i:
            _pos_ok = False
    ok('H9b ★★★ 位置数字**和实际停的那一站对得上**（不是"会动"就行 —— '
       '反例法"晚一格"只有这条抓得住）',
       _pos_ok, ' / '.join(_pos_detail))

    # H10 ★★★ 秒表每秒刷一次 —— **不许把用户翻到的位置拉回去**
    #     用户翻到第 3 站、一秒后被拉回第 1 站 ⇒ 表现就是"点了没反应"，
    #     而按钮、数据、回调全都对。这是这条功能能不能用的关键。
    # [EN] ★★★ The stopwatch refreshes every second and **must not pull the user's position back**.
    # Flipping to station 3 and being yanked to station 1 a second later **looks like "the buttons do
    # nothing"** while the buttons, data and callbacks are all correct.
    _keep = _chip()
    for _ in range(3):
        app_car._refresh_plot_panel()
    ok('H10 ★★★ 秒表每秒刷新**不会**把翻到的位置拉回去'
       '（会的话就是"点了没反应"那个观感，而按钮其实好好的）',
       _chip() == _keep, f'刷新前 {_keep!r} → 刷新 3 次后 {_chip()!r}')

    # H11 **没手动翻过**时要跟着当前站走（故事推进了，面板就该跟过去）
    # [EN] When the user has **not** browsed, the panel must follow the current station.
    app_car2, _ = _make_app(w_car, with_crew=False)
    app_car2._refresh_plot_panel()
    w_car.current_node = 'N03'
    try:
        app_car2._refresh_plot_panel()
        _followed = '共读西厢' in str(app_car2._ui_run['plot_chip_txt'].value or '')
    finally:
        w_car.current_node = 'N02'
    ok('H11 ★★ 没手动翻过时**跟着当前站走**（故事推进了，面板要跟过去）',
       _followed, f'推进到 N03 后显示 {app_car2._ui_run["plot_chip_txt"].value!r}')

    # H12 边界：空表 / 单节点 / 索引越界都不许抛
    # [EN] Edges: empty table / single node / out-of-range index must not raise.
    _edge_err = ''
    try:
        w0 = _FakeWorld()
        w0.progress_nodes = []
        a0, _ = _make_app(w0, with_crew=False)
        a0._refresh_plot_panel()
        a0._plot_step(1)
        a0._plot_step(-1)
        w1 = _FakeWorld()
        w1.progress_nodes = [{'id': 'N01', '名称': '唯一一站', '状态': '未开始'}]
        a1, _ = _make_app(w1, with_crew=False)
        a1._refresh_plot_panel()
        a1._plot_step(1)
        a1._plot_step(-1)
        _single = '唯一一站' in str(a1._ui_run['plot_chip_txt'].value or '')
        # 索引越界（节点表变短了）：不该 IndexError，也不该空白
        a1._ui_run['plot_sel'] = 99
        a1._ui_run['plot_manual'] = True
        a1._refresh_plot_panel()
        _clamped = bool(str(a1._ui_run['plot_chip_txt'].value or '').strip())
    except Exception as e:                               # noqa: BLE001
        _single = _clamped = False
        _edge_err = repr(e)
    ok('H12 ★★ 边界都不抛：**空表**（显示 —）、**单节点**（点了还是它）、'
       '**索引越界**（节点表变短时夹回去，不是空白）',
       not _edge_err and _single and _clamped, _edge_err or '三种都对')

    # ★★★ H12b：**索引夹回这件事要判函数契约，不能只判"界面没炸"**。
    #   为什么：`_plot_paint_carousel` 里还有一道夹回，`plot_carousel_pick` 不夹也炸不了
    #   （反例法 ㊽ 因此红了 0 条）。而"pick 收了个越界值"这件事**迟早会被别处拿去用**
    #   （比如以后要"跳到第 N 站"），所以契约本身必须成立。
    # [EN] ★★★ H12b: **clamping must be judged as a function contract, not just "the UI did not
    # crash"**. `_plot_paint_carousel` clamps again, so `plot_carousel_pick` failing to clamp raises
    # nothing (mutation ㊽ caught 0). Yet "pick accepted an out-of-range value" will eventually be used
    # elsewhere (e.g. a future "jump to station N"), so the contract itself has to hold.
    _pick_cases = [
        ('越界大', plot_carousel_pick(sel=99, manual=True, total=3, follow=1), 0, 2),
        ('越界负', plot_carousel_pick(sel=-5, manual=True, total=3, follow=1), 0, 2),
        ('没节点', plot_carousel_pick(sel=0, manual=False, total=0, follow=0), 0, 0),
        ('没翻过', plot_carousel_pick(sel=None, manual=False, total=3, follow=2), 2, 2),
        ('翻过', plot_carousel_pick(sel=1, manual=True, total=3, follow=2), 1, 1),
    ]
    _pick_bad = [f'{nm}:{got}∉[{lo},{hi}]' for nm, got, lo, hi in _pick_cases
                 if not (lo <= got <= hi)]
    ok('H12b ★★★ `plot_carousel_pick` 的**契约**：越界夹回、没节点返回 0、'
       '没翻过跟当前站、翻过就保持（**判函数，不判"界面没炸"** —— 界面那道夹回会把它盖住）',
       not _pick_bad, ' / '.join(_pick_bad) if _pick_bad else '五种情形都对')

    # ⚠ 判源码时**照抄产品里那两行的实际写法**（`bg = ... if is_cur else None`）。
    #   第一版把整句写成一条字符串去比对，而产品里那是**赋值语句**、还带缩进，
    #   于是判据永远找不到 ⇒ 假红。
    # [EN] When judging source, **copy the product's actual two lines** (`bg = ... if is_cur else
    # None`). The first version compared one long literal, while in the product it is an **assignment**
    # with indentation, so the criterion never found it => a false red.
    _bg_cur = "with_alpha(C['hover'], 0.55) if is_cur else None" in _src
    _bd_cur = "make_border(1, C['border_gold']) if is_cur else None" in _src
    ok('H13 ★ 跑马灯停在当前站时，胶囊带**底色 + 金边**（其余站只是一行字 —— '
       '每条都画框的话"当前"就没有区分度了；**判产品源码**）',
       _bg_cur and _bd_cur, f'底色={_bg_cur} 金边={_bd_cur}')

    # 最后量一下跑马灯那一行放不放得下（两个三角 + 中间胶囊）
    # [EN] Lastly, does one carousel row fit (two triangles plus the chip in between)?
    ok('H14 ★★★ 一行**放得下**（两个三角 + 中间胶囊 ≤ 可用宽度）—— '
       '放不下会被横向裁掉，长名称更是直接看不见',
       PLOT_CAROUSEL_W > 100 and PLOT_ARROW_W * 2 + PLOT_CAROUSEL_W <= PLOT_CHIP_W + 0.5,
       f'可用 {PLOT_CHIP_W:.0f}px = 三角 {PLOT_ARROW_W}×2 + 中间 {PLOT_CAROUSEL_W:.0f}px')

    # 没有节点时不炸
    # [EN] Must not crash with no nodes
    w3 = _FakeWorld()
    w3.progress_nodes = []
    app3, _ = _make_app(w3, with_crew=False)
    try:
        app3._refresh_plot_panel()
        empty_ok = list(getattr(app3._ui_run['plot_nodes'], 'controls', []) or []) == []
        err = ''
    except Exception as e:                               # noqa: BLE001
        empty_ok, err = False, repr(e)
    ok('F8 ★ 没有进度节点时清单是空的、且不抛错', empty_ok, err or '空')

    # 秒表每秒刷一次 ⇒ 内容没变时**不许重建控件**（否则悬停 tooltip 每秒被打断）
    # [EN] The stopwatch refreshes every second => **must not rebuild** when nothing changed
    # [EN] (otherwise an open hover tooltip is interrupted every second)
    w4 = _FakeWorld()
    app4, _ = _make_app(w4, with_crew=False)
    app4._refresh_plot_panel()
    # ★ 跑马灯口径：不再"重建一批行"，而是**改同一批控件的属性**。
    #   所以"没重建"的证据是：那个 Text 与那个胶囊**还是同一个对象**（`is` 比较）。
    #   如果哪天有人改回"每秒 new 一批控件"，这两个 id 就会变 —— 判据照样抓得住。
    # [EN] Carousel measure: no longer "rebuild a batch of rows" but **change properties of the same
    # controls**. So the evidence is that the Text and the chip are **still the same objects** (`is`).
    # If someone goes back to "new a batch every second", these ids change and the criterion catches it.
    _t_id_before = id(app4._ui_run['plot_chip_txt'])
    _c_id_before = id(app4._ui_run['plot_chip'])
    first = str(app4._ui_run['plot_chip_txt'].value or '')
    app4._refresh_plot_panel()
    second = str(app4._ui_run['plot_chip_txt'].value or '')
    ok('F9 ★★ 内容没变时**不重建控件**（还是同一批对象、同一段文字；秒表每秒刷也不抖）',
       bool(first) and first == second
       and id(app4._ui_run['plot_chip_txt']) == _t_id_before
       and id(app4._ui_run['plot_chip']) == _c_id_before,
       f'文字 {first!r}→{second!r} · 同一对象='
       f'{id(app4._ui_run["plot_chip_txt"]) == _t_id_before}')

    # ★★★ F10：**谁写 `progress_note`**。
    #   F6 只是"手设一个值、看界面显示没显示" —— 那只证明界面会读，
    #   **完全不证明推演会写**。而用户报的病根恰好在写那一侧：
    #   旧代码只在 `done=True` 时才用 `desc`，没满足时整句丢掉。
    #   ⇒ 这里**真调 `_check_progress`**，让导演返回一个"还没满足、但带进展描述"
    #     的结论，看它写不写。
    #   ⚠ 这条必须判**行为**，不能判"代码里有没有 `progress_note` 这个词"——
    #     变异把赋值挪进 `if done:` 之后，词还在。
    #   ⚠ `_check_progress` 是 async，而这一组跑在 **Flet 的 loop 里** ⇒
    #     不能自己 `run_until_complete`（会 `RuntimeError: another loop is running`）。
    #     所以 F10/F11 拆成 `async` 函数，由 `main` 用 `await` 调（见 `plot_nodes_async_checks`）。
    # [EN] ★★★ F10: **who writes `progress_note`**. F6 only "sets a value by hand and checks the UI
    # [EN] reads it" -- that proves the UI reads, **not that the simulation writes**. The reported
    # [EN] bug lived on the writing side: the old code used `desc` only when `done=True`.
    # [EN] => `_check_progress` is **actually invoked** with a "not yet satisfied but carries a
    # [EN] progress line" verdict, and we check whether it gets written.
    # [EN] ⚠ Must judge **behaviour**, not "does the file contain `progress_note`" -- moving the
    # [EN] assignment inside `if done:` keeps the word.
    # [EN] ⚠ `_check_progress` is async and this group runs **inside Flet's loop** => it cannot
    # [EN] `run_until_complete` itself (`RuntimeError: another loop is running`). F10/F11 are async
    # [EN] functions awaited by `main` (see `plot_nodes_async_checks`).


async def plot_nodes_async_checks() -> None:
    """F10/F11：`_check_progress` **真的会写 `progress_note`**（行为判据）。

    ★ 为什么要单独一组：这两条要 `await`，而别的判据是同步的 ——
      混在一起就得在同步函数里开 loop，那就是上面那个 `RuntimeError` 的来源。
    """
    from director.engine import ProgressVerdict
    from sim.loop import RunLoop

    class _Db:
        def recent_events(self, n):
            return [{'id': 'e1', 'content': '老陈取旧账置柜台'}]

    class _Dir:
        def __init__(self, v):
            self.v = v
            self.events_this_round = 0

        async def evaluate_progress(self, ev):
            return self.v

    def _mk_loop(verdict, prev_note: str):
        lp = object.__new__(RunLoop)               # 绕过 __init__（本项目夹具惯例）
        lp.world = _FakeWorld()
        lp.world.progress_note = prev_note
        lp.db = _Db()
        lp.director = _Dir(verdict)
        lp._progress_fail_streak = 0
        lp._progress_sig = None
        lp._push_narrative = lambda *a, **k: None
        lp._status = lambda *a, **k: None
        return lp

    lp = _mk_loop(ProgressVerdict(ok=True, done=False,
                                  desc='阿九见旧账落款笔锋与执壶手势暗合，线索初现'), '')
    await lp._check_progress()
    got = str(getattr(lp.world, 'progress_note', ''))
    ok('F10 ★★★ 判据**没满足**时（`done=False`）也把「走到哪儿了」记下来'
       '（旧代码只在这一站走完时才用那句话 ⇒ 界面上永远看不出在推进）',
       '线索初现' in got, f'结果={got!r}')

    lp2 = _mk_loop(ProgressVerdict(ok=True, done=False, desc=''), '上一次的进展')
    await lp2._check_progress()
    kept = str(getattr(lp2.world, 'progress_note', ''))
    ok('F11 ★★ 模型没给进展描述时**保留上一次的**（别把"走到哪了"擦成空白）',
       kept == '上一次的进展', f'结果={kept!r}')


# ══════════════════════════════════════════════════════════════
#  D —— 刷新点接线（AST）：每处 `_refresh_crew_panel` 后都跟着这两块
# [EN] D -- refresh wiring (AST): every `_refresh_crew_panel` is followed by these two
# ══════════════════════════════════════════════════════════════
def _blocks(fn):
    """函数里所有语句块。
        ⚠ **同一个块会重复进来两次**（先单独 `fn.body`，`ast.walk` 又会走到
        `fn` 自己）⇒ 顶层的每一句被**数两遍**（实测：4 处刷成 5 处）。
        块的"身份"用 `id()` 去重。
        English:
    Every statement block in the function.
        ⚠ **The same block comes in twice** (first `fn.body` alone, then `ast.walk` walks onto `fn`
        itself) => every top-level statement is **counted twice** (in practice: 4 sites became 5).
        Dedupe blocks by `id()`.
    """
    seen: set = set()
    # ⚠ `getattr` **必须给默认值**：不是每个节点都有 `body`/`orelse`
    #   （第一版没给 ⇒ `AttributeError` ⇒ 整个 D 组被兜成一条红）。
    # [EN] ⚠ `getattr` **must have a default**: not every node has `body`/`orelse`
    # [EN] (the first version omitted it => AttributeError => the whole D group collapsed into one red).
    for blk in [fn.body] + [getattr(n, a, None)
                            for n in ast.walk(fn)
                            for a in ('body', 'orelse', 'finalbody')]:
        if not isinstance(blk, list) or id(blk) in seen:
            continue
        seen.add(id(blk))
        yield blk


def wiring_checks() -> None:
    src = APP_PATH.read_text(encoding='utf-8')
    tree = ast.parse(src)
    cls = next((n for n in ast.walk(tree)
                if isinstance(n, ast.ClassDef) and n.name == 'NovelWorldApp'), None)
    ok('D0 ★ `NovelWorldApp` 类存在', cls is not None, '')
    if cls is None:
        return

    def _call_name(st):
        return (isinstance(st, ast.Expr) and isinstance(st.value, ast.Call)
                and isinstance(st.value.func, ast.Attribute)
                and st.value.func.attr)

    sites = 0
    wired = 0
    for fn in cls.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for blk in _blocks(fn):
            for i, st in enumerate(blk):
                if _call_name(st) != '_refresh_crew_panel':
                    continue
                sites += 1
                # ⚠ **必须防越界**：变异把后面两句删掉之后，`_refresh_crew_panel()`
                #   就变成了块里的最后一句 ⇒ `blk[i+1]` 抛 `IndexError`，
                #   整个 D 组被兜成一条红（看着像"变异生效了"，其实是判据自己崩了）。
                # [EN] ⚠ **Must guard against out-of-range**: after a mutation deletes the two
                # [EN] following statements, `_refresh_crew_panel()` becomes the last statement in the
                # [EN] block => `blk[i+1]` raises IndexError and the whole D group collapses into one
                # [EN] red (which looks like "the mutation took effect", when the criterion itself crashed).
                after = [_call_name(blk[j]) for j in (i + 1, i + 2) if j < len(blk)]
                if '_refresh_char_panel' in after and '_refresh_plot_panel' in after:
                    wired += 1
    ok('D1 ★★★ 每一处 `_refresh_crew_panel()` 后面都跟着 '
       '`_refresh_char_panel()` + `_refresh_plot_panel()`'
       '（进界面 / 秒表 / 出工事件 / 收工 四处都要接）',
       sites >= 4 and wired == sites, f'共 {sites} 处，接上了 {wired} 处')

    # ★★ 反例：不能只接一处（"每一处"用 `wired == sites`，不是 `wired >= 1`）。
    # [EN] ★★ Counterpart: it must not be wired at just one place ("every place" uses
    # [EN] `wired == sites`, not `wired >= 1`).
    ok('D2 ★★ 刷新点**不只一处**（右栏三块是同一个理由：数字要自己走）',
       sites >= 4, f'sites={sites}')

    # 秒表那一处：与「剧组」共用 0.5 秒那一拍（不然换场景时那一栏不会跟着换）
    # [EN] The stopwatch one: shares that 0.5s beat with "Cast" (otherwise that column won't follow
    # [EN] when the scene changes)
    # ⚠ 全类里有**两个** `_tick`（另一个是别的秒表）⇒ 单行"取最后一个"会拿到
    #   错的那个（实测：拿到 332 字符的那个，判据自己制造假红）。
    #   认准"与剧组共用那一拍"的：**含 `_refresh_crew_panel` 的那个**。
    # [EN] ⚠ There are **two** `_tick` in the whole class (the other is a different stopwatch) =>
    # [EN] "take the last one" grabs the wrong one (in practice: it grabbed the 332-char one, and the
    # [EN] criterion manufactured a false red).
    # [EN] Identify the one that **shares the beat with Cast**: the one containing `_refresh_crew_panel`.
    tick_src = ''
    for fnn in cls.body:
        for sub in ast.walk(fnn):
            if not isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if sub.name != '_tick':
                continue
            s = ast.unparse(sub)
            if '_refresh_crew_panel' in s:
                tick_src = s
    ok('D3 ★★ 秒表那一拍里也刷这两块（换场景时在场的人会整批换掉）',
       '_refresh_char_panel' in tick_src and '_refresh_plot_panel' in tick_src,
       f'tick_len={len(tick_src)}')


# ══════════════════════════════════════════════════════════════
#  E —— 真机：控件真的挂进界面，且真的被读出来
# [EN] E -- Real machine: the controls really are mounted, and really read out
# ══════════════════════════════════════════════════════════════
async def real_checks(page: ft.Page) -> None:
    import tempfile
    from sim import setup as SU
    from sim.session import RunSession
    from store.runfolder import RunFolder
    from verify_run_control import make_project

    VU.patch_flat_background()
    from gui.app_flet import NovelWorldApp as NWA

    tmp = Path(tempfile.mkdtemp(prefix='nws_sidepanels_'))
    proj = make_project(tmp / '右栏面板', nodes=2)
    run = RunFolder(proj.root, '第1次模拟2026-10-17-00-00').create()
    loop, world, db = SU.assemble(proj, run, image_hook=lambda *a, **k: None)

    app = NWA()
    app.main(page)
    await asyncio.sleep(1.8)
    app.current_project = proj
    app.session = RunSession(loop, world, run, on_crew_work=app._on_crew_work)
    app.show_main_screen()
    await asyncio.sleep(1.0)

    tree = list(VU.walk(page))
    for key in ('char_list', 'char_hint', 'plot_node', 'plot_body', 'plot_prog'):
        ctl = app._ui_run.get(key)
        ok(f'E1 ★★★ `{key}` 真的挂在运行界面上'
           '（句柄存了却没挂上去 = 一样永远看不见）',
           ctl is not None and ctl in tree,
           f'ctl={type(ctl).__name__ if ctl else None}')

    # 真推演状态 → 真接上（不是造的假世界）
    # [EN] Real simulation state -> really wired (not a fake world)
    app._refresh_plot_panel()
    nv = str(app._ui_run['plot_node'].value)
    bv = str(app._ui_run['plot_body'].value)
    pv = str(app._ui_run['plot_prog'].value)
    ok('E2 ★★★ 真会话下「节点」读的是真 `world.current_node`（N01）',
       'N01' in nv, nv)
    ok('E3 ★★★ 真会话下「张力 · 事件」读的是真值（不再是「—」）',
       '—' not in bv, bv)
    ok('E4 ★★★ 真会话下「进度表」读的是真 `progress_nodes`（0/2）',
       '0' in pv and '2' in pv and '—' not in pv, pv)

    # 改真世界的张力 → 面板跟着变（真机上的行为对照）
    # [EN] Change the real world's tension -> the panel follows (behavior contrast on the real machine)
    world.tension = 0.88
    app._refresh_plot_panel()
    bv2 = str(app._ui_run['plot_body'].value)
    ok('E5 ★★★ 真机上改 `world.tension` → 面板跟着变（读的是真状态）',
       '0.88' in bv2 and bv2 != bv, f'{bv} → {bv2}')

    # 在场人物：真会话下把人摆到场上，再刷一次
    # ⚠ `world.people` 是 **dict[str, PersonState]** —— 迭代它拿到的是**名字**
    #   （第一版就写成了 `for ps in world.people` 然后 `ps.present = True`，
    #   报 `str has no attribute present`，浪费了一轮才看出来）。
    # [EN] On-stage Characters: put people on stage in the real session, then refresh once
    # [EN] ⚠ `world.people` is a **dict[str, PersonState]** -- iterating it yields the **names**
    # [EN]   (the first version wrote `for ps in world.people` then `ps.present = True`,
    # [EN]   raising `str has no attribute present`; it took a round to spot).
    try:
        for ps in list(world.people.values()):
            ps.status = '在场'
            ps.role = '前台'
            ps.location = ''
        names = list(world.on_stage_names())
        world.actor_think = {n: '先看看这场要说些什么' for n in names}
        app._refresh_char_panel()
        ctrls = app._ui_run['char_list'].controls
        ok('E6 ★★★ 真机上「在场人物」真的列出了在场的角色'
           f'（on_stage={names}）',
           len(ctrls) == len(names) and len(names) > 0,
           f'{len(ctrls)} vs {len(names)}')
        if ctrls:
            blob = ' | '.join(_texts(ctrls[0]))
            ok('E7 ★★★ 真机上那一行照台账写「在岗」+ 在做的事',
               '在岗' in blob and '先看看这场要说些什么' in blob, blob)
    except Exception as e:                                       # noqa: BLE001
        ok('E6 ★★★ 真机上「在场人物」真的列出了在场的角色', False, repr(e))
        ok('E7 ★★★ 真机上那一行照台账写「在岗」+ 在做的事', False, repr(e))


# ══════════════════════════════════════════════════════════════
#: ⚠ `--logic-only`：**根本不起 Flet 服务**（`asyncio.run(main(None))`）。
#:   反例法要跑二十几遍，每遍都起一次 Flet 服务会慢到没法用，
#:   而且不关窗口会吊着一堆僵进程。
# [EN] ⚠ `--logic-only`: **don't start the Flet server at all** (`asyncio.run(main(None))`).
# [EN] The counterexample method runs twenty-some times; starting the Flet server each time would be
# [EN] unusably slow, and not closing the window leaves a pile of dangling processes.
ONLY_LOGIC = '--logic-only' in sys.argv


async def main(page: ft.Page | None) -> None:
    print('\n── A 创建时句柄真的交出去了（AST）──')
    try:
        creation_checks()
    except Exception:                                            # noqa: BLE001
        ok('A 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    print('\n── B 「在场人物」搬过来了、说法一点没变 ──')
    try:
        char_panel_checks()
    except Exception:                                            # noqa: BLE001
        ok('B 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    print('\n── C 「剧情」四个值随推演状态变 ──')
    try:
        plot_panel_checks()
    except Exception:                                            # noqa: BLE001
        ok('C 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    print('\n── F 节点清单 + 最近进展（2026-10-21 用户点名）──')
    try:
        plot_nodes_checks()
        # F10/F11 要 `await`（`_check_progress` 是 async，而这里就在 Flet 的 loop 里）
        # [EN] F10/F11 need `await` (they call the async `_check_progress` inside Flet's loop)
        await plot_nodes_async_checks()
    except Exception:                                            # noqa: BLE001
        ok('F 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    print('\n── D 刷新点接线（AST）──')
    try:
        wiring_checks()
    except Exception:                                            # noqa: BLE001
        ok('D 组跑完', False, traceback.format_exc()[-400:])
        print(traceback.format_exc()[-1200:])
    print('\n── E 真机 ──')
    if page is None:
        print('  （--logic-only：跳过）')
    else:
        try:
            await real_checks(page)
        except Exception:                                        # noqa: BLE001
            ok('E 组跑完', False, traceback.format_exc()[-400:])
            print(traceback.format_exc()[-1200:])

    n = len(report['checks'])
    good = sum(1 for c in report['checks'] if c['ok'])
    print(f'\n右栏两块面板验证：{good}/{n}')
    (OUT / 'run_side_panels_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    # ⚠ 先关窗口再退出：反着写会**卡住不退出**（`sys.exit` 抛在 Flet 会话里，
    #   会话没关 ⇒ 进程吊着，反例法每跑一条就多一个僵进程）。
    # [EN] ⚠ Shut the window down before exiting: writing it the other way **hangs** (`sys.exit` is
    # [EN] raised inside the Flet session; the session isn't closed => the process dangles, and the
    # [EN] counterexample method leaves one zombie per mutation).
    if page is not None:
        await shutdown(page, code=(0 if good == n else 2))


if __name__ == '__main__':
    if ONLY_LOGIC:
        asyncio.run(main(None))
        sys.exit(0)
    ft.run(main, assets_dir=str(APP_DIR / 'assets'))
