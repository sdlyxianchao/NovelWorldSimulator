# -*- coding: utf-8 -*-
"""验证：**设定分层**（`world/layers.py`）与**编剧室会审**（`crew/agents.SettingsRoom`）。

用户 2026-10-07
--------------
「我导入的设定文件夹的内容可能包含很多地方 包括很大的设定 也包括很细节的设定
  你要自己分层管理 有些很大的背景只在后台特定的时候发挥作用 具体每天的故事
  可能是由很小的设定影响的 你要分层管理……

  而且有些时候需要导演 和 小说作者 以及 剧作家 讨论生成一些新的设定
  这些都要进行推演 以便方便故事推进 **同时不能够影响总体设定**

  （你自己在项目里分层次 设置设定文件集合，同时自己管理好不同层级
    不同内容设定发挥的时间 场合 权重 影响谁等等 你心里要清楚）」

这个脚本一条条钉住那段话，**每条都要能红**：

  A **分层本身**：五层在位；索引把设定集编成四层条目（人物层不进前缀）；
    「时机 / 场合 / 影响谁 / 权重」四件事**真的参与筛选**。
  B **大背景只在特定时候展开**：平时被压短、开篇/高潮日/每 N 天展开；
    这份额度是**量出来的**（两个状态下的字数差）。
  C **细节层是每天的主角**：场合对得上就出现、对不上就不出现、额度内整条丢。
  D **闸门是真的**（"不能够影响总体设定"）：世界层/主线层/人物层一律拒；
    没有作用范围的一律拒；**`worldview_text` / `rules_text` 一字不变**。
  E **接线**：`WorldState.world_prefix()` 走分层；没有索引 / 关掉开关时
    **一字不变地退回老行为**；缓存仍生效且能被新设定冲掉。
  F **文件集合**：`分层设定.yaml` / `.md` + `临时设定.json` / `.md` 落得出来、
    读得回来，且 `.md` 里五层与"作用范围"都在。
  G **真链路（MOCK）**：`assemble()` → `_compose_day()` → 编剧室出工 →
    收下的设定**真的进了提示词**，拒收的**真的没进**。

用法：.venv\\Scripts\\python.exe tools/verify_setting_layers.py
产出：assets/screenshots/setting_layers_report.json

English:
Verification: **setting layering** (`world/layers.py`) and the **writers' room review**
(`crew/agents.SettingsRoom`).
User 2026-10-07
--------------
"The content of the settings folder I import may include many places, including very large
settings and also very detailed settings.
  You must manage the layers yourself. Some very large backgrounds only take effect at specific times in the background. The specific daily story
  may be affected by very small settings. You must manage the layers...
  And sometimes the director, the novelist, and the playwright need to discuss and generate some new settings.
  These must all be reasoned through, so as to facilitate story progression, **while not being able to affect the overall setting**.
  (You layer them yourself within the project, set up the setting file sets, and at the same time manage well the different layers
    and the times, occasions, weights, who is affected, etc. of the different content settings. You must be clear in your own mind.)"
This script nails down that passage line by line, **every line must be able to go red**:
  A **The layering itself**: five layers are in place; the index compiles the setting set into four layers of entries (the character layer does not enter the prefix);
    the four things "timing / occasion / who is affected / weight" **really participate in filtering**.
  B **The big background only unfolds at specific times**: normally compressed short, unfolded at the opening / climax day / every N days;
    this quota is **measured** (the character-count difference between the two states).
  C **The detail layer is the protagonist every day**: it appears when the occasion matches, does not appear when it doesn't, and is dropped whole within the quota.
  D **The gate is real** ("must not be able to affect the overall setting"): the world layer / mainline layer / character layer are all rejected;
    anything without a scope of effect is rejected; **`worldview_text` / `rules_text` remain verbatim**.
  E **Wiring**: `WorldState.world_prefix()` goes through layering; when there is no index / when the switch is off,
    **fall back to the old behavior verbatim**; the cache still takes effect and can be flushed by new settings.
    and read back, and the five layers and "scope of effect" are all present in the `.md`.
  G **Real pipeline (MOCK)**: `assemble()` → `_compose_day()` → writers' room produces work →
    the settings accepted **really enter the prompt**, and the rejected ones **really do not enter**.
Usage: .venv\\Scripts\\python.exe tools/verify_setting_layers.py
Output: assets/screenshots/setting_layers_report.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(APP_DIR / 'tools'))

from config import CFG                                         # noqa: E402
CFG.set('MOCK_LLM', 'true')

from i18n import set_lang                                      # noqa: E402
set_lang('zh')

from store.project import Project                              # noqa: E402
from store.runfolder import RunFolder                          # noqa: E402
from crew import roster as ROSTER                              # noqa: E402
from verify_ui_common import safe_rmtree                       # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
report: dict = {'checks': []}


def ok(name: str, cond, detail='') -> bool:
    report['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
    print(('  ✓ ' if cond else '  ✗ ') + name + (f' | {detail}' if detail else ''),
          flush=True)
    return bool(cond)


#: 退出码统一出口（2026-10-28）。⚠ 这一支原来 `main() -> None`、**没有 `sys.exit`** ⇒
#:   它在 `tools/run_all_verifications.py` 里**恒绿**：断言红成一片，回归器看到的退出码仍是 0
#:   ⇒「红灯打出来也没人看得见」⇒ 那条覆盖**从来没被证明过**。
#:   （2026-10-28 实测：把第 191 行的条件改成 `False`，退出码仍是 0。）
#: [EN] ⚠ This one used to have `main() -> None` and **no `sys.exit`** => it was **always green** in
#: [EN] the regression (measured 2026-10-28: forcing an assertion to `False` still exited 0).
#: [EN] The exit code now goes through the shared outlet `tools/verify_exit.py`.
from tools.verify_exit import finish   # noqa: E402


# ══════════════════════════════════════════════════════════════
#  夹具
# [EN] Fixture
# ══════════════════════════════════════════════════════════════
SETTINGS = {
    'worldview': '临河小城，常年落雨，纸贵、衙门只手遮天，人情密而口风紧。'
                 '镇上的人信奉"能不说话就不说话"。',
    'plot': '起：雨夜来了个不速之客。承：旧事被一点点翻出。'
            '转：最可信的人露出破绽。合：有人离开，有人留下。',
    'places': [{'名称': '临河茶肆', '说明': '临河的茶楼，两层，后院有口井'},
               {'名称': '城东渡口', '说明': '船来船往，夜里就没人了'}],
    'relations': [{'甲': '主角', '乙': '阿枝', '关系': '主仆', '张力': '阿枝藏着身世'}],
    'foreshadows': [{'编号': 'F01', '内容': '后院那口井夜里会响', '埋设': '开篇',
                     '预计回收': '中段'}],
    'nodes': [{'id': 'N01', '名称': '开端', '概要': '茶楼来了个不速之客',
               '完成判据': '掌柜出手', '状态': '未开始'},
              {'id': 'N02', '名称': '揭盖', '概要': '旧账被翻出来',
               '完成判据': '有人认账', '状态': '未开始'}],
    'detail': [{'名称': '缺角的紫砂壶', '内容': '柜上那把壶缺了个角，谁也不许动',
                '场合': '临河茶肆', '涉及': '主角'},
               {'名称': '渡口不夜渡', '内容': '渡口天黑之后不再开船，敲也不开',
                '场合': '城东渡口', '涉及': ''},
               # ⚠ 这一条**只**限场合（`涉及` 空）—— 它是"场合真的在筛"的
               #   唯一证据：上面那条同时限了人，人不在场时也会被滤掉，
               #   于是"忽略场合"这个变异它会照样通过（反例法当场抓出来的）。
               # [EN] ⚠ This one is **only** limited to occasion (`涉及` empty) -- it is the
               # [EN] only evidence that "the occasion is really filtering": the one above also limits people, and
               # [EN] gets filtered out when the person is absent,
               # [EN] so the mutation "ignore occasion" will still pass it (caught on the spot by the counterexample
               # [EN] method).
               {'名称': '楼里那盏长明灯', '内容': '堂里那盏灯整夜不熄，谁也没见它灭过',
                '场合': '临河茶肆', '涉及': ''},
               {'名称': '旧疤', '内容': '掌柜右腕内侧有道旧疤，天阴时会按一按',
                '场合': '', '涉及': '主角'},
               # 既不限场合、也不限人 —— 这条该**处处都在**（C3 用它当对照）
               # [EN] Limits neither occasion nor people -- this one should be **present everywhere** (C3 uses it as a
               # [EN] control)
               {'名称': '更漏只校一次', '内容': '店里的更漏一夜只许校一次，校错要赔',
                '场合': '', '涉及': ''}],
    'genre_card': {'主题材': '悬疑', '结构': '单元剧', '频道': '男频'},
    'style_card': {'句长': '中短句', '叙事距离': '贴身第三人称', 'AI腔禁词表': ['不禁', '或许']},
}


def make_project(root: Path, *, with_run_files: bool = True):
    """造项目 + 冻结设定集（格式照抄 `ingest/pipeline._freeze`）。
        English:
    Build the project + freeze the setting set (format copied from `ingest/pipeline._freeze`).
    """
    proj = Project(root, root.name)
    sd = proj.settings_dir
    sd.mkdir(parents=True, exist_ok=True)
    import yaml

    def _y(name, data):
        (sd / name).write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False,
                      sort_keys=False), encoding='utf-8')

    _y('人物.yaml', [
        {'姓名': '主角', '身份': '临河茶肆掌柜', '性格': '沉稳内敛，话少',
         '口癖': '且慢', '秘密': '压着一件旧事', '目标': '守住这间楼', '红线': '不伤人'},
        {'姓名': '阿枝', '身份': '伙计', '性格': '嘴上不饶人，心却软',
         '口癖': '罢了', '秘密': '在等一个不会回来的人', '目标': '守住铺子', '红线': ''},
        {'姓名': '胡账', '身份': '账房', '性格': '精于算计',
         '口癖': '数目不对', '秘密': '', '目标': '', '红线': ''},
    ])
    _y('世界观.md', SETTINGS['worldview'])
    _y('剧情走向.md', SETTINGS['plot'])
    _y('地点.yaml', SETTINGS['places'])
    _y('关系.yaml', SETTINGS['relations'])
    _y('伏笔与悬线.yaml', SETTINGS['foreshadows'])
    # ★ 细节设定.yaml —— 本轮新增的细节层素材
    # [EN] ★ 细节设定.yaml -- the detail-layer material newly added this round
    _y('细节设定.yaml', SETTINGS['detail'])
    _y('故事进度.yaml', {'节点': SETTINGS['nodes']})
    _y('类型卡.yaml', SETTINGS['genre_card'])
    _y('风格卡.yaml', SETTINGS['style_card'])
    return proj


# ══════════════════════════════════════════════════════════════
#  A/B/C/D —— 纯逻辑（分层引擎本身）
# [EN] A/B/C/D -- pure logic (the layered engine itself)
# ══════════════════════════════════════════════════════════════
def logic_layers() -> None:
    from world import layers as L

    # ── A 分层本身 ──
    # [EN] ── A The layering itself ──
    ok('A1 五层在位，键就是那五个',
       L.LAYER_KEYS == ('canon', 'arc', 'scene', 'detail', 'person'),
       str(L.LAYER_KEYS))
    ok('A2 剧组只能写「场景层/细节层」（世界层与主线层是作者的总体设定）',
       L.CREW_WRITABLE == ('scene', 'detail'), str(L.CREW_WRITABLE))
    ok('A3 人物层不进世界前缀（由人物卡承载，重复进两处只是让 prompt 变贵）',
       L.BY_KEY['person'].in_prefix is False, '')
    ok('A4 每层都写了"什么时候出场 / 谁有权写"（用户要的那张表）',
       all(l.expand and l.writer and l.duty for l in L.LAYERS), '')
    ok('A5 每层都列了它来自哪几个设定文件（"设定文件集合"）',
       all(L.LAYER_SOURCES.get(l.key) for l in L.LAYERS),
       str({l.key: len(L.LAYER_SOURCES.get(l.key, ())) for l in L.LAYERS}))

    idx = L.build_index(SETTINGS)
    got = {k: sum(1 for i in idx if i.layer == k) for k in L.LAYER_KEYS}
    ok('A6 索引把设定集编成四层条目（人物层 0 条 —— 它不进索引）',
       got['canon'] == 1 and got['arc'] >= 3 and got['scene'] >= 3
       and got['detail'] == 5 and got['person'] == 0, str(got))
    ok('A7 世界层那条就是作者写的世界观原文（**不做概括**）',
       any(i.layer == 'canon' and SETTINGS['worldview'] in i.text for i in idx), '')
    # ★ 顶层键名**两套都认**：归一后的 `worldview`，以及 `ingest.extractor` 出来的
    #   原始件 `世界观`。只认一套的话，另一种输入会得到**空索引** ——
    #   而且一声不吭（表现成"分层没生效"）。这条是给演示页生成样例时撞出来的。
    # [EN] ★ Top-level key names **both sets are recognized**: the normalized `worldview`, and the one
    # [EN] produced by `ingest.extractor`
    # [EN] raw form `世界观`. If only one set is recognized, the other kind of input gets an **empty index**
    # [EN] --
    # [EN] and silently so (manifesting as "the layering didn't take effect"). This one was hit while
    # [EN] generating samples for the demo page.
    raw_idx = L.build_index({
        '世界观': '临河小城，纸贵。',
        '地点': [{'名称': '临河茶肆', '说明': '临河茶楼'}],
        '细节': [{'名称': '缺角的壶', '内容': '缺了个角', '场合': '临河茶肆'}]})
    ok('A7b ★ 提取原始件的键名（世界观 / 地点 / 细节）也认 —— 不认的话索引会是空的',
       [i.layer for i in raw_idx].count('canon') == 1
       and [i.layer for i in raw_idx].count('scene') == 1
       and [i.layer for i in raw_idx].count('detail') == 1,
       str([(i.layer, i.name) for i in raw_idx]))
    ok('A8 地点编成场景层、`where` = 地点名（这就是"场合"的数据来源）',
       {i.where for i in idx if i.layer == 'scene'
        and i.note == '地点'} == {'临河茶肆', '城东渡口'}, '')
    ok('A9 关系带"影响谁"（甲/乙）—— 这样它只在牵到的人在场时出现',
       any(i.layer == 'scene' and i.who == ('主角', '阿枝') for i in idx), '')
    ok('A10 权重参与了排序（世界层/剧情参考线最靠前，伏笔在后）',
       idx[0].weight >= 4 and idx[-1].weight <= 3,
       f'{[(i.layer, i.weight) for i in idx[:3]]} … {idx[-1].weight}')
    ok('A11 层名别名：中文"世界层/细节"与英文 key 都归一',
       (L.normalize_layer('世界层'), L.normalize_layer('细节'),
        L.normalize_layer('detail'), L.normalize_layer('胡编'))
       == ('canon', 'detail', 'detail', ''), '')

    # ── 时机 / 场合 / 影响谁 ──
    # [EN] ── Timing / Occasion / Who it affects ──
    def item(**kw):
        base = {'层': '细节', '名称': 'x', '内容': 'y'}
        base.update(kw)
        return L.SettingItem.from_dict(base)

    it = item(生效时机='第3-5天')
    ok('A12 生效时机「第3-5天」只在区间里生效',
       (it.when_ok(2), it.when_ok(3), it.when_ok(5), it.when_ok(6))
       == (False, True, True, False), '')
    ok('A13 「首日」只在第 1 天生效',
       (item(生效时机='首日').when_ok(1), item(生效时机='首日').when_ok(2))
       == (True, False), '')
    ok('A14 ★ 时机**认不出就当生效**（别让作者写的一句话悄悄失效）',
       item(生效时机='说不清').when_ok(9) is True, '')
    ok('A15 场合：站在"临河茶肆"时，"城东渡口"那条不出现',
       (item(场合='临河茶肆').where_ok('临河茶肆 · 堂内'),
        item(场合='临河茶肆').where_ok('城东渡口')) == (True, False), '')
    ok('A16 场合/人名任一边为空 = 算对得上（规则从宽）',
       item(场合='').where_ok('哪儿都行') and item(影响谁=[]).who_ok([]), '')
    ok('A17 影响谁：牵到的人不在场就不出现',
       (item(影响谁=['主角']).who_ok(['阿枝']),
        item(影响谁=['主角']).who_ok(['阿枝', '主角'])) == (False, True), '')

    # ── B 大背景只在特定时候展开 ──
    # [EN] ── B The big background only unfolds at specific times ──
    ok('B1 开篇（第 1 天）展开大背景', L.should_expand(day=1) is True, '')
    ok('B2 高潮日（张力 ≥ 0.7）展开', L.should_expand(day=5, tension=0.8) is True, '')
    ok('B3 每 3 天展开一次', (L.should_expand(day=3), L.should_expand(day=6),
                              L.should_expand(day=4)) == (True, True, False), '')
    long_wv = '这是一座临河的小城。' * 60          # 960 字，够看出短/长两档
    # [EN] 960 characters, enough to see the short/long two tiers
    s = dict(SETTINGS, worldview=long_wv)
    i2 = L.build_index(s)
    txt1, _ = L.prefix_block(i2, day=1, scene='临河茶肆', people=['主角'])
    txt4, _ = L.prefix_block(i2, day=4, scene='临河茶肆', people=['主角'])
    n1 = len([ln for ln in txt1.splitlines() if ln.startswith('[世界观]')][0])
    n4 = len([ln for ln in txt4.splitlines() if ln.startswith('[世界观]')][0])
    ok('B4 ★ 同一份世界观：第 1 天（开篇）给的多、第 4 天给的少 —— '
       '"很大的背景只在后台特定的时候发挥作用"',
       n1 > n4 * 1.5 and n4 <= L.CANON_BRIEF + 12, f'第1天 {n1} 字 / 第4天 {n4} 字')
    ok('B5 常态额度就是 `CANON_BRIEF`（是一句"气候"，不是一段背景）',
       L.CANON_BRIEF <= 200 and L.CANON_FULL > L.CANON_BRIEF, 
       f'{L.CANON_BRIEF} → {L.CANON_FULL}')

    # ── C 细节层是每天的主角 ──
    # [EN] ── C The detail layer is the protagonist every day ──
    _, view_here = L.prefix_block(idx, day=4, scene='临河茶肆', people=['主角'])
    _, view_far = L.prefix_block(idx, day=4, scene='城东渡口', people=['阿枝'])
    names_here = {i.name for i in view_here.get('detail')}
    names_far = {i.name for i in view_far.get('detail')}
    ok('C1 站在临河茶肆 → 那把壶（场合=临河茶肆）出现',
       '缺角的紫砂壶' in names_here, str(sorted(names_here)))
    ok('C2 ★ 站在渡口 → 渡口那条出现、**只限场合**的茶楼那盏灯不出现'
       '（"场合"真的在筛，不是摆设）',
       '渡口不夜渡' in names_far and '楼里那盏长明灯' not in names_far
       and '楼里那盏长明灯' in names_here,
       f'临河茶肆 {sorted(names_here)} / 渡口 {sorted(names_far)}')
    ok('C3 ★ 既不限场合、也不限人的小设定（更漏）处处都在 —— '
       '它是"每天都能用得上的小事"，与上面两条形成对照',
       '更漏只校一次' in names_here and '更漏只校一次' in names_far,
       f'临河茶肆 {sorted(names_here)} / 渡口 {sorted(names_far)}')
    ok('C3b 「影响谁」也真的在筛：旧疤→主角，所以主角不在场就不出现',
       '旧疤' in names_here and '旧疤' not in names_far, '')
    ok('C4 细节层有条数上限（一次塞二十条就又变成一坨了）',
       L.DETAIL_MAX_ITEMS <= 6, str(L.DETAIL_MAX_ITEMS))

    # 额度满了要**整条丢**，不许截半句。两个夹具各管一头：
    #   · 短条目（40 字）× 10 → 条数上限说了算；
    #   · 长条目（70 字，正好顶到每条上限）× 6 → **额度**说了算（第四条会被整条丢）。
    # [EN] When the quota is full, the **whole entry must be dropped**, half a sentence must not be cut.
    # [EN] The two fixtures each handle one end:
    # [EN] · short entries (40 chars) × 10 → the entry-count limit decides;
    # [EN] · long entries (70 chars, exactly hitting the per-entry limit) × 6 → the **quota** decides (the
    # [EN] fourth entry gets dropped whole).
    many = [{'层': '细节', '名称': f't{i}', '内容': '甲' * 40} for i in range(10)]
    txt3, _ = L.prefix_block(L.build_index({'worldview': '短', 'detail': many}),
                             day=4, scene='', people=[])
    line3 = [ln for ln in txt3.splitlines() if ln.startswith('[小事]')][0]
    n_in = sum(1 for i in range(10) if f't{i}：' in line3)
    ok('C5 细节层有条数上限（十条只进 4 条，不是把十条全塞进去）',
       n_in == L.DETAIL_MAX_ITEMS, f'{n_in} 条 / 上限 {L.DETAIL_MAX_ITEMS}')

    big = [{'层': '细节', '名称': f'b{i}', '内容': '乙' * 70} for i in range(6)]
    txt_b, _ = L.prefix_block(L.build_index({'worldview': '短', 'detail': big}),
                              day=4, scene='', people=[])
    line_b = [ln for ln in txt_b.splitlines() if ln.startswith('[小事]')][0]
    present = [i for i in range(6) if f'b{i}：' in line_b]
    ok('C6 ★ 额度不够时**整条丢**、不截半句（半句进提示词比少一条更坏）',
       '…' not in line_b and 0 < len(present) < 6
       and line_b.count('乙') == 70 * len(present),
       f'{len(present)} 条完整 / 6 条中；共 {line_b.count("乙")} 个"乙"')

    # ── D 闸门：不能影响总体设定 ──
    # [EN] ── D Gate: must not affect the overall setting ──
    def rej(why_layer, **kw):
        it = item(层=why_layer, **kw)
        return L.why_reject(it) if it else '读不出来'

    ok('D1 世界层一律拒（"不能够影响总体设定"）', bool(rej('世界层', 场合='临河茶肆')), '')
    ok('D2 主线层一律拒', bool(rej('主线', 场合='临河茶肆')), '')
    ok('D3 人物层也拒（它不进前缀，塞进去等于塞进黑洞）',
       bool(rej('人物层', 场合='临河茶肆')), '')
    ok('D4 场景层收（这是剧组该补的东西）', rej('场景', 场合='临河茶肆') == '', '')
    ok('D5 细节层收', rej('细节', 场合='临河茶肆') == '', '')
    ok('D6 ★ 没有作用范围的（不限地点/人/时）当场拒 —— 那等于改总体设定',
       '作用范围' in rej('细节', 场合=''), rej('细节', 场合=''))
    ok('D7 有限人 / 限时也算有作用范围（不逼着每条都写地点）',
       rej('细节', 影响谁=['主角']) == '' and rej('细节', 生效时机='第3天') == '', '')
    ok('D8 内容太长（像设定文档而不像局部设定）拒',
       '太长' in rej('细节', 场合='临河茶肆', 内容='甲' * 400),
       rej('细节', 场合='临河茶肆', 内容='甲' * 400))

    good = item(名称='铜钱', 内容='他袖里有枚磨得发亮的铜钱', 场合='临河茶肆')
    bad = item(层='世界层', 名称='改天', 内容='这城其实归外邦管')
    bad2 = item(名称='处处', 内容='到处都是灯')
    bad3 = {'层': '胡编', '名称': 'x', '内容': 'y'}          # 连层都读不出
    # [EN] Cannot even read a layer
    acc, rej_list = L.admit_new([good, bad, bad2, bad3])
    ok('D9 收下合法的、拒掉非法的', [i.name for i in acc] == ['铜钱'],
       str([i.name for i in acc]))
    ok('D10 ★ 被拒的**带原因**（静默丢掉会变成"剧组说了半天什么都没发生"）',
       len(rej_list) == 3 and all(w for _i, w in rej_list),
       ' / '.join(w[:24] for _i, w in rej_list))
    ok('D11 读不出层的也要报一声（不是 `continue` 静默丢）',
       any('认不出是哪一层' in w for _i, w in rej_list), '')
    ok('D12 一次会审有条数上限',
       L.MAX_NEW_PER_ROUND <= 6, str(L.MAX_NEW_PER_ROUND))
    ok('D13 ★ 作者已经写过的同名同层设定不再重复收'
       '（否则台账会写"新增 2 条"，其中一条只是把作者的话又说了一遍）',
       '已经写过' in (L.why_reject(item(名称='缺角的紫砂壶', 场合='临河茶肆'),
                                   existing={('detail', '缺角的紫砂壶')}) or ''),
       '')


# ══════════════════════════════════════════════════════════════
#  E/F —— 接线与文件
# [EN] E/F -- Wiring and files
# ══════════════════════════════════════════════════════════════
def logic_wire(tmp: Path) -> None:
    from world import layers as L
    from world.state import WorldState, PersonState

    # ── E1/E2 没有索引时**一字不变**地退回老行为 ──
    # [EN] ── E1/E2 With no index, **fall back to the old behavior verbatim** ──
    w0 = WorldState()
    w0.worldview_text = '这是个临河的小城。'
    w0.rules_text = '夜里不许出门。'
    pre0 = w0.world_prefix()
    ok('E1 ★ 没有分层索引 → 老行为一字不变（`[世界观] 世界观前500字`）',
       pre0.startswith('[顶级规则·不可违背]') and '[世界观] 这是个临河的小城。' in pre0,
       pre0.replace('\n', '⏎')[:70])

    saved = CFG.raw('SETTING_LAYERS')
    w1 = WorldState()
    w1.worldview_text = '【世界观】临河小城，纸贵。'
    w1.rules_text = '谁动了更漏谁就得说清行踪。'
    w1._layer_settings = {'worldview': '临河小城，纸贵。',
                          'plot': '起：来了个不速之客。',
                          'places': [{'名称': '临河茶肆', '说明': '临河的茶楼'}],
                          'detail': [{'名称': '缺角的紫砂壶',
                                      '内容': '柜上那把壶缺了个角',
                                      '场合': '临河茶肆'}]}
    w1.scene = '临河茶肆'
    w1.add_person(PersonState('主角'))
    w1.rebuild_layers()
    try:
        CFG.set('SETTING_LAYERS', 'true')
        pre1 = w1.world_prefix()
        CFG.set('SETTING_LAYERS', 'false')
        pre_off = w1.world_prefix()
        ok('E2 ★ `SETTING_LAYERS=false` 时行为与从前一字不差'
           '（"退回老做法"必须是真的退回，不是换个说法）',
           '[主线]' not in pre_off and '[世界观]' in pre_off and
           '缺角的紫砂壶' not in pre_off, pre_off.replace('\n', '⏎')[:70])
        CFG.set('SETTING_LAYERS', 'true')
        pre1 = w1.world_prefix()
        ok('E3 有索引 → 分层渲染：`[世界观]`/`[主线]`/`[此处]`/`[小事]` 都在',
           all(k in pre1 for k in ('[世界观]', '[主线]', '[此处]', '[小事]')),
           pre1.replace('\n', '⏎')[:90])
        ok('E4 ★ `[世界观]` 标签没改（五支验证脚本靠它做断言）',
           pre1.startswith('[顶级规则·不可违背]') and '[世界观]' in pre1, '')
        ok('E5 细节层那条**真的进了提示词**（"具体每天的故事由小设定影响"）',
           '缺角的紫砂壶' in pre1, '')
        ok('E6 顶级规则仍排在最前面、且原文照录',
           pre1.splitlines()[0] == '[顶级规则·不可违背]'
           and '谁动了更漏' in pre1, '')

        # ── E7 缓存仍然生效、而且能被新设定冲掉 ──
        # [EN] ── E7 The cache still takes effect, and can be flushed by new settings ──
        p1 = w1.world_prefix()
        ok('E7 `world_prefix()` 结果被缓存（第二次直接返回缓存那个串）',
           getattr(w1, '_prefix_cache', None) is not None
           and w1.world_prefix() is p1, '')
        L.add_local(w1, [L.SettingItem(layer='detail', name='铜钱',
                                       text='袖里有枚磨亮的铜钱', where='临河茶肆',
                                       source='剧组')])
        p2 = w1.world_prefix()
        ok('E8 ★ 收下新设定后缓存立刻失效（否则"剧组说了，人物当没听见"）',
           '铜钱' in p2 and p2 is not p1, p2.replace('\n', '⏎')[-60:])
        ok('E9 新设定只进 `local_settings`，**没进**世界层的正文',
           any(i.name == '铜钱' for i in w1.local_settings)
           and '铜钱' not in w1.worldview_text, '')

        # ── E10 阵容变了（换地点）也要重算 ──
        # [EN] ── E10 When the roster changes (location swap), it must also recompute ──
        w1.scene = '城东渡口'
        p3 = w1.world_prefix()
        ok('E10 换地点后重新渲染（那把壶留在临河茶肆，不跟着走）',
           '缺角的紫砂壶' not in p3, p3.replace('\n', '⏎')[:80])
    finally:
        CFG.set('SETTING_LAYERS', saved)

    # ── F 文件集合 ──
    # [EN] ── F File set ──
    root = tmp / '分层文件'
    root.mkdir(parents=True, exist_ok=True)
    w2 = WorldState()
    w2._layer_settings = dict(SETTINGS)
    w2.rebuild_layers()
    L.save_profile(root, w2.layer_index, day=3)
    L.save_local(root, w2)
    for fn in (L.FILE_PROFILE_YAML, L.FILE_PROFILE_MD,
               L.FILE_LOCAL_JSON, L.FILE_LOCAL_MD):
        ok(f'F1 `{fn}` 落得出来', (root / fn).exists(), '')
    md = (root / L.FILE_PROFILE_MD).read_text(encoding='utf-8')
    ok('F2 `分层设定.md` 有那五层（作者一眼看到"哪一层管什么"）',
       all(l.name in md for l in L.LAYERS),
       [l.name for l in L.LAYERS if l.name not in md])
    ok('F3 `分层设定.md` 写了每条的**作用范围**（时机/场合/影响谁）',
       '作用范围' in md and ('限「临河茶肆」' in md or '涉及 主角' in md), '')
    ok('F4 `分层设定.md` 写了"想改哪一层去动哪个文件"',
       '世界观.md' in md and '细节设定.yaml' in md, '')
    ok('F5 `临时设定.md` 明确说"**没有写进你的设定集**"（不能让人误会）',
       '没有写进你的设定集' in (root / L.FILE_LOCAL_MD).read_text(encoding='utf-8'),
       '')
    ok('F6 `load_local` 能把落盘的局部设定读回来',
       [i.name for i in L.load_local(root)] == [], '空表（还没新增过）')
    w2.local_settings = [L.SettingItem(layer='detail', name='铜钱', text='袖里有枚铜钱',
                                       where='临河茶肆', source='剧组')]
    L.save_local(root, w2)
    back = L.load_local(root)
    ok('F7 落盘 → 读回往返（同一轮续跑要靠它）',
       [i.name for i in back] == ['铜钱'] and back[0].source == '剧组',
       str([i.name for i in back]))
    ok('F8 读回的那条渲染得出来（不是只存在文件里）',
       '铜钱' in L.render(L.select(
           L.build_index({'worldview': '短'}, local=back), day=3, scene='临河茶肆',
           people=['主角'])), '')


# ══════════════════════════════════════════════════════════════
#  G —— 真链路（MOCK：装配 → 跨天 → 编剧室 → 提示词）
# [EN] G -- Real pipeline (MOCK: assembly → cross-day → writers' room → prompt)
# ══════════════════════════════════════════════════════════════
async def logic_e2e(tmp: Path) -> None:
    from sim.setup import assemble
    from world import layers as L

    proj = make_project(tmp / '端到端')
    run = RunFolder(proj.root, '第1次模拟2026-01-01-00-00').create()
    loop, world, db = assemble(proj, run)
    try:
        ok('G1 装配后 world.layer_index 非空，四层都有',
           len(world.layer_index) >= 8
           and all(any(i.layer == k for i in world.layer_index)
                   for k in ('canon', 'arc', 'scene', 'detail')),
           str({k: sum(1 for i in world.layer_index if i.layer == k)
                for k in L.LAYER_KEYS}))
        root = Path(run.root)
        ok('G2 装配时就把 `分层设定.md` / `.yaml` 落进了运行文件夹',
           (root / L.FILE_PROFILE_MD).exists()
           and (root / L.FILE_PROFILE_YAML).exists(), '')
        ok('G3 装配时也落了 `临时设定.md`（"还没有新增过"也要说清楚）',
           (root / L.FILE_LOCAL_MD).exists(), '')

        pre = world.world_prefix()
        ok('G4 提示词里已经有细节层（开篇那一天）',
           '缺角的紫砂壶' in pre, pre.replace('\n', '⏎')[-70:])

        # ── 跨天：编剧室会审 ──
        # [EN] ── Cross-day: writers' room review ──
        world.game_day = 1
        before_wv = world.worldview_text
        before_rules = world.rules_text
        await loop._compose_day()
        n_local = len(world.local_settings or [])
        ok('G5 ★ 编剧室真的出工并收下了局部设定（MOCK 演示数据）',
           n_local >= 1, f'{n_local} 条')
        ok('G6 ★★ `worldview_text` / `rules_text` **一字未变**'
           '（"不能够影响总体设定"是结构保证的）',
           world.worldview_text == before_wv and world.rules_text == before_rules, '')
        ok('G7 收下的都只有场景层/细节层',
           all(i.layer in L.CREW_WRITABLE for i in world.local_settings),
           str(sorted({i.layer for i in world.local_settings})))
        ok('G8 收下的每条都有作用范围',
           all(i.when or i.where or i.who for i in world.local_settings), '')
        ok('G9 ★ MOCK 里那条"世界层"的新设定被拒收（闸门是活的）',
           (root / L.FILE_LOCAL_MD).exists()
           and '这座城其实归外邦管' not in (root / L.FILE_LOCAL_MD)
           .read_text(encoding='utf-8'), '')
        _n = loop.studio.note_of('settings_room')
        ok('G9b ★ 与作者已写过的重名条目也被拒（MOCK 的演示数据里正好有一条重名）',
           bool(_n) and any('已经写过' in str(w) for w in (_n.data.get('拒收') or [])),
           str((_n.data.get('拒收') if _n else []) or [])[:120])
        ok('G10 收下的设定**进了提示词**（"这些都要进行推演"的落点）',
           all(i.name in world.world_prefix() for i in world.local_settings),
           str([i.name for i in world.local_settings]))
        ok('G11 台账里编剧室那一行有状态（界面「剧组」面板读的就是它）',
           any(r['key'] == 'settings_room' and r['state'] == 'done'
               for r in loop.studio.ledger()), '')
        _led = loop.studio.ledger()
        _eff = ROSTER.roles()
        _led_keys = [r.get('key') for r in _led]
        _eff_keys = [r.key for r in _eff]
        # ⚠ 台账比有效名册**多出** `actor::某角色` 那几行 ——
        #   那是**运行时按在场角色开出来的演员行**（今天三个主要人物各一行），
        #   不是"多出来的职位"。⇒ 比的时候要把它们**摘出来**再比。
        #   剩下那几行必须与有效名册**一一对应**（不多、不少、不重）。
        # [EN] ⚠ The ledger has **extra** `actor::<character>` rows -- those are the **per-character
        # [EN] actor rows opened at runtime** (one per on-stage character today), not "extra
        # [EN] positions". => take them out before comparing.
        # [EN] The rest must correspond to the effective roster **one to one** (none extra, none
        # [EN] missing, no duplicates).
        _actor_rows = [k for k in _led_keys if str(k).startswith('actor::')]
        _base_keys = [k for k in _led_keys if not str(k).startswith('actor::')]
        _roster_keys = set(ROSTER.keys())
        _member_keys = set(__import__('crew.agents', fromlist=['x']).MEMBERS)
        ok('G12 名册/在位者一一对应（多一个实现或少一个职位都算断链）',
           sorted(_base_keys) == sorted(_eff_keys)
           and len(_led_keys) == len(set(_led_keys))
           and not ROSTER.audit_hooks() and _roster_keys == _member_keys,
           f'台账 {len(_led)} 行 = 名册 {len(_eff)} + 演员 {len(_actor_rows)}'
           f'｜演员行 {sorted(_actor_rows)}'
           f'｜名册多出 {sorted(set(_base_keys) - set(_eff_keys))}'
           f'｜名册少了 {sorted(set(_eff_keys) - set(_base_keys))}'
           f'｜名册-在位者 {sorted(_roster_keys - _member_keys)}'
           f'｜在位者-名册 {sorted(_member_keys - _roster_keys)}'
           f'｜audit_hooks {list(ROSTER.audit_hooks())}')

        # ── 剧本已经写出来，说明"先补设定、再动笔"这条顺序没把流程弄断 ──
        # [EN] ── The script has already been written, showing that the order "fill in settings first, then
        # [EN] start writing" did not break the flow ──
        ok('G13 编剧室排在写样章之前，这一天照样写出了剧本',
           loop._day_script is not None and bool(loop._day_script.story), '')
    finally:
        try:
            db.close()
        except Exception:                                        # noqa: BLE001
            pass
        try:
            loop.studio.save_sidecar()
        except Exception:                                        # noqa: BLE001
            pass


# ══════════════════════════════════════════════════════════════
#  H 「必出日」：第 N 章必出
#    2026-10-27 加的那条**唯一保证** —— 细节层是"每天按场合随机抽 4 条"，
#    所以「第 3 章埋的那只壶、第 8 章才用得上」这种结构在架构上**没法保证**，
#    而笑点/伏笔的"埋—逼—揭"三步恰恰靠这个。
#    ⚠ 这一组判据是**补上去的**：这个功能加进来时**一条判据都没有**
#    （⇒ 它的解析器只认单个字的中文数字这件事，**藏了很久**才被发现）。
# [EN] H "must appear": chapter N
#    The **one guarantee** added on 2026-10-27 -- the detail layer samples 4 items per day by occasion,
#    so "the pot planted in chapter 3 and cashed in chapter 8" was structurally impossible, and that is
#    exactly what the plant/force/expose chain needs.
#    ⚠ This group of assertions was **added afterwards**: when the feature landed it came with **not a
#    [EN] single assertion** (=> the fact that its parser only accepted single-character Chinese
#    [EN] numerals **hid** for a long time before it was found).
# ══════════════════════════════════════════════════════════════
def logic_must_on() -> None:
    from world import layers as L

    def item(**kw):
        base = {'层': '细节', '名称': 'x', '内容': 'y'}
        base.update(kw)
        return L.SettingItem.from_dict(base)

    # ── H1 各种写法都认得出 ──
    # [EN] ── H1 Every spelling is recognized ──
    shapes = [('3', (3,)), ('3,7', (3, 7)), ('第3天', (3,)), ('第三天', (3,)),
              ('第3、7章', (3, 7)), ('3 7', (3, 7)), ('第3章必出', (3,)),
              ([3, 7], (3, 7)), (3, (3,))]
    bad = [(k, L.parse_must_on(k), v) for k, v in shapes if L.parse_must_on(k) != v]
    ok('H1 「必出日」的各种写法都认得出（数字/串/列表/带前后缀）',
       not bad, str(bad))

    # ── H2 ★★★ 中文数字**两个字的**也要认 ──
    #   这一条是本组判据存在的**主要理由**：老解析器只认单字（「三」认得、「十五」不认），
    #   而模型与作者写的偏偏常是「第十五章」 ⇒ 那一条**静默丢掉**，
    #   表现成"程序照跑、就是没出" —— 作者完全看不出来。
    #   ⚠ 判据要钉住的是**闭集**：`两三`（约数）必须判**非法**。
    # [EN] ── H2 ★★★ Chinese numerals of **two characters** must be recognized too ──
    # [EN] This is the **main reason** this group exists: the old parser accepted single characters
    # [EN] only ("三" yes, "十五" no), while models and authors typically write "第十五章" => that
    # [EN] entry was **silently dropped**, manifesting as "the program runs fine, it just never shows
    # [EN] up" -- the author cannot tell at all.
    # [EN] ⚠ The assertion pins the **closed set**: "两三" (an approximate count) must be **invalid**.
    ok('H2 ★★★ 中文数字**两个字的**也要认（「第十五章」「第二十三章」）',
       L.parse_must_on('第十五章') == (15,)
       and L.parse_must_on('第二十三章') == (23,)
       and L.parse_must_on('第一百零八章') == (108,),
       f'第十五章 → {L.parse_must_on("第十五章")}｜第二十三章 → {L.parse_must_on("第二十三章")}')
    ok('H2b ★★ 约数「两三」判**非法**（它不是章号；猜一个会让细节冒到错的章节）',
       L.parse_must_on('两三') == () and L.parse_must_on('第0章') == (),
       f'两三 → {L.parse_must_on("两三")}')

    # ── H3 ★ 区间要展开成每一个章号 ──
    #   旧口径只给出一个（3）—— 那是**静默的半个答案**：第 4、5 章照样没出，
    #   而作者以为"第3到5章"都包了。
    # [EN] ── H3 ★ A range must expand into every chapter number ──
    # [EN] The old behaviour gave just one (3) -- a **silently halved answer**: chapters 4 and 5 still
    # [EN] never showed up while the author thought "chapter 3 to 5" covered them.
    ok('H3 ★★ 区间「第3-5章」展开成 3、4、5（不是只给一个 3）',
       L.parse_must_on('第3-5章') == (3, 4, 5)
       and L.parse_must_on('3-5') == (3, 4, 5)
       and L.parse_must_on('三到五') == (3, 4, 5),
       f'第3-5章 → {L.parse_must_on("第3-5章")}')

    # ── H4 ★★ 认不出来一律当没有（不许猜一个章号出来）──
    # [EN] ── H4 ★★ Unrecognizable always means "none" (never guess a chapter number) ──
    ok('H4 ★★ 认不出来的一律当没有（不许从一段话里猜一个数出来）',
       L.parse_must_on('abc') == () and L.parse_must_on('') == ()
       and L.parse_must_on(None) == () and L.parse_must_on(True) == (),
       '')

    # ── H5 ★★★ 「必出日」**绕过场合/在场两道闸** ──
    #   场合/在场是"今天用得上吗"，「必出」是作者写死的"这天一定要有" —— 后者等级更高。
    #   不绕过的话，"第 3 章必出的那只壶"在第 3 章没这场戏就被筛掉了，
    #   而那正是它要存在的理由。
    # [EN] ── H5 ★★★ The "must appear" day **bypasses the occasion/presence gates** ──
    # [EN] The occasion/presence gates ask "is it useful today", while "must appear" is the author's
    # [EN] "it must be here on that day" -- the latter outranks.
    # [EN] Without bypassing, the pot that must appear on chapter 3 gets filtered out on chapter 3
    # [EN] precisely because it was needed there.
    mi = item(必出日='3', 场合='临河茶肆', 影响谁=['主角'])
    ok('H5 ★★★ 必出日**绕过场合/在场两道闸**（场合不对、人不在场照样出）',
       mi.active(day=3, scene='城东渡口', people=['阿枝']) is True,
       f'must_on={mi.must_on}')
    ok('H5b ★★ 别的日子它**照旧**按场合/在场走（不是"永久常驻"）',
       mi.active(day=4, scene='城东渡口', people=['阿枝']) is False
       and mi.active(day=4, scene='临河茶肆', people=['主角']) is True,
       '')

    # ── H6 ★★★ 必出日在渲染里**排最前**（不会被额度挤掉）──
    #   细节层的**条数上限 4** 与**字符额度**是两道闸。一条"第 3 章必出的那只壶"
    #   若排在第 5 位，它会被挤掉 —— 而这一章正是要埋它的那一章 ⇒ 埋了，后文收不回来。
    # [EN] ── H6 ★★★ The "must appear" items go **first** in the rendering (not squeezed out by quota) ──
    # [EN] The detail layer has **two** gates (max 4 items AND a char quota). A "the pot that must
    # [EN] appear on chapter 3" sitting in 5th place gets squeezed out -- and that is precisely the
    # [EN] chapter where it was meant to be planted, so it would never be cashed in later.
    detail6 = [{'层': '细节', '名称': f'高权{i}', '内容': '甲' * 60, '权重': 5}
               for i in range(4)]
    detail6.append({'层': '细节', '名称': '必出的壶', '内容': '乙' * 60,
                     '权重': 1, '必出日': '3'})
    txt6, _ = L.prefix_block(L.build_index({'worldview': '短', 'detail': detail6}),
                              day=3, scene='', people=[])
    line6 = [ln for ln in txt6.splitlines() if ln.startswith('[小事]')][0]
    ok('H6 ★★★ 必出的那一条**排在最前**、挤不掉（权重最低也照样进）',
       line6.startswith('[小事] 必出的壶：'), line6[:60])
    ok('H6b ★★ 必出的那一条**真的占了位置**（条数上限 4，它在第 4 位之外也得进）',
       '必出的壶' in line6 and line6.count('乙') == 60,
       f'共 {line6.count("乙")} 个"乙"')

    # ── H7 作者看得见（作用范围那一列要写出来）──
    # [EN] ── H7 The author can see it (the scope column must spell it out) ──
    ok('H7 ★★ 作用范围那一列写得出「第 N 章必出」（作者得知道自己写过什么）',
       '第 3 章必出' in item(必出日='3').scope_line(),
       item(必出日='3').scope_line())

    # ── H8 「必出日」的各种键名都认（模型/作者可能用别的叫法）──
    # [EN] ── H8 Every key spelling is recognized ──
    keys = ['必出日', '必出章', '必出', '指定章次', 'must_on', 'must_on_days']
    miss = [k for k in keys
            if (item(**{k: '3'}) is None or item(**{k: '3'}).must_on != (3,))]
    ok('H8 ★★ 「必出日」的六种键名都认（少认一种 = 那种写法静默失效）',
       not miss, str(miss))

    # ── H9 ★★ 提取器把模型给的**各种形状**统一收成 "3,7" ──
    #   模型可能给 `"3"`、`3`、`["3","7"]`、`"第3、7章"`、`"第三天"`……
    #   形状差别若照原样透传，下游一个都认不出 ⇒ 「必出」这条唯一保证就**静默失效**。
    # [EN] ── H9 ★★ The extractor normalizes every shape the model may produce into "3,7" ──
    # [EN] The model may give `"3"`, `3`, `["3","7"]`, `"第3、7章"`, `"第三天"`... If those shape
    # [EN] differences are passed through as-is, the downstream parser recognizes **none** of them =>
    # [EN] the one guarantee ("must appear") **silently fails**.
    try:
        from ingest.extractor import _must_on_text
        # ⚠ 用**三元组列表**装 (输入, 实得, 期望)，不用字典 ——
        #   输入里有 `['3','7']`（**不可哈希**），拿它当字典键会 TypeError。
        # [EN] ⚠ Use a **list of triples** (input, got, expected), not a dict -- the inputs include
        # [EN] `['3','7']` (**unhashable**), using one as a dict key raises TypeError.
        inputs = ['3', 3, ['3', '7'], '第3、7章', '第三天', '第十五章', '第3-5章']
        want = ['3', '3', '3,7', '3,7', '3', '15', '3,4,5']
        rows = [(i, _must_on_text({'必出日': i}), w)
                for i, w in zip(inputs, want)]
        bad = [(i, g, w) for i, g, w in rows if g != w]
        ok('H9 ★★ 提取器把各种形状统一收成「3,7」（形状差别 = 静默失效）',
           not bad, str(bad))
        ok('H9b ★★ 收不出来就**空串**（不许猜一个章号出来）',
           _must_on_text({'必出日': '乱写'}) == '', '')
    except Exception as e:                                     # noqa: BLE001
        ok('H9 ★★ 提取器把各种形状统一收成「3,7」（形状差别 = 静默失效）', False, repr(e))


# ══════════════════════════════════════════════════════════════
def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix='nws_layers_'))
    try:
        print('\n── A/B/C/D 分层引擎 ──')
        logic_layers()
        print('\n── E/F 接线与文件 ──')
        logic_wire(tmp / 'wire')
        print('\n── H 「必出日」（第 N 章必出）──')
        logic_must_on()
        print('\n── G 真链路（MOCK）──')
        asyncio.run(logic_e2e(tmp))
    except BaseException:                                        # noqa: BLE001
        report['fatal'] = traceback.format_exc()
        print(report['fatal'])
    finally:
        safe_rmtree(tmp, ignore_errors=True)

    return finish(report, out_path=OUT / 'setting_layers_report.json')


if __name__ == '__main__':
    sys.exit(main())
