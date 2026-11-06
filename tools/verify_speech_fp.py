# -*- coding: utf-8 -*-
"""验证：**说话指纹**这条链（2026-10-28）。

背景（这条判据为什么存在）
--------------------------
作者转来一份退稿复盘：编辑把稿子退回来，只圈了三段对话，批注一句
「你这两个人说话，像在互相念说明书」。编辑的判法很土也很好用 ——
**把人名遮住，如果所有人都一个味，那就是机器写的**。

顺着这句话拆，能治的病有四类（本判据一组一组钉住）：
  ① 所有角色一个腔调 ⇒ **动笔前定"说话指纹"**（句长 / 嘴上抓手 / 心虚动作 / 称呼差）；
  ② 事情全靠嘴说 ⇒ **能不说就不说**：动作、表情、环境、手里的东西能说清的，不开口；
  ③ 回答太完整 ⇒ **别答完整**：答一半、答错方向、先问回去；
  ④ 标签堆砌 ⇒ **别拿副词盖章**：「他严肃地说道」这种句式一章最多两处，
     超出的部分由确定性检测器数出来、由 `_fix_dialogue_tags` 删掉副词并归一动词。

四组
----
  A 字段链路：设定集 → `PersonState` → 选角层 → 开口前那一段（**真调**，不打桩）
  B 对话标签：检测 / 配额边界 / 清理（**引号里的台词一个字都不许少**）
  C 提示词纪律：演员尾段三条、写作层三条
  D 某本书的设定集（`--project <目录>` 才跑；**源码里不写任何作品专名**）

★ 不开窗口、不调模型、零网络。
★ D 组默认不跑：判据夹具一旦写进真实作品的专名，`verify_generic_project` 就会红
  —— 那是"在用户真实项目上验证完要清干净"的同一条纪律。

    English:
Verification: the **speech fingerprint** chain (2026-10-28).
An editor returned a manuscript with three passages circled: "your two characters talk
like they are reading spec sheets to each other." His test was crude: **cover the names;
if everyone sounds the same, a machine wrote it.**
Four diseases follow from that sentence, one group per pair:
  (1) everyone the same voice => define a **speech fingerprint** before writing;
  (2) everything pushed through dialogue => **say it only when you must**;
  (3) answers too complete => **answer incompletely**;
  (4) tag piling => **no adverb-stamped tags**, at most two per chapter.
Groups: A the field chain (really executed), B the tag detector/quota/strip
(**not one character of quoted speech may be lost**), C prompt discipline,
D one book's settings (only with `--project`; **no work's proper nouns in this source**).
"""
from __future__ import annotations

import ast
import inspect
import sys
import types
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

OUT = APP / 'assets' / 'screenshots'
EXTRACTOR = APP / 'ingest' / 'extractor.py'
SETUP = APP / 'sim' / 'setup.py'
STATE = APP / 'world' / 'state.py'

CHECKS: list[dict] = []
FAILED: list[str] = []


def ok(name: str, cond, detail='') -> bool:
    """记一条检查。**红的必须让退出码非 0** —— 回归器只看退出码。"""
    good = bool(cond)
    CHECKS.append({'name': name, 'ok': good, 'detail': str(detail)[:400]})
    if not good:
        FAILED.append(name)
    print(('  ✓ ' if good else '  ✗ ') + name + (('  —— ' + str(detail)[:200]) if not good and detail else ''))
    return good


# ══════════════════════════════════════════════════════════════════════
#  A 字段链路
# ══════════════════════════════════════════════════════════════════════
def test_chain() -> None:
    print('\nA 字段链路（设定集 → 人格状态 → 选角层 → 开口前那一段）')
    from ingest import extractor
    from world.state import PersonState
    from actors import casting

    # A1 提取层不许把新字段丢掉（丢掉的症状是"我明明写了，人物就是不这么说"）
    out = extractor._validate({'人物': [{'姓名': '甲', '身份': '账房',
                                         '说话指纹': '一句不超过十字；虚了摸炭条'}]})
    got = out['人物'][0].get('说话指纹', None)
    ok('A1 提取层保留「说话指纹」（不是静默丢掉）', got == '一句不超过十字；虚了摸炭条', got)

    # A2 提示词必须要求"四件事"且**禁形容词** —— 形容词没法执行，
    #    模型只会把它翻译回"客气、完整、有礼貌"，那正是要治的病
    p = extractor._PROMPT
    need = ['说话指纹', '句子多长', '心虚时手上干什么', '称呼', '不许写形容词']
    miss = [w for w in need if w not in p]
    ok('A2 提取提示词说清"四件事"并禁用形容词', not miss, '缺：' + '、'.join(miss))

    # A3 运行时状态有这一格，且缺省是空串（不编）
    f = getattr(PersonState, '__dataclass_fields__', {}).get('speech_fp')
    ok('A3 PersonState 有 speech_fp 且默认空串', f is not None and f.default == '', f)

    # A4 `setup` 真把它搬进去（AST 查 PersonState(...) 的 keyword，不靠 grep 字符串）
    src = SETUP.read_text(encoding='utf-8')
    tree = ast.parse(src)
    kw = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'PersonState':
            kw = any(k.arg == 'speech_fp' for k in node.keywords)
            if kw:
                break
    ok('A4 setup 把「说话指纹」搬进 PersonState', kw)

    # A5 选角层（定制层）要把它念出来 —— 写进卡里但提示词不给，等于没写
    card = {'身份': '账房', '性格': '认死理', '口癖': '傻子账上不糊涂。',
            '说话指纹': '一句不超过十字；爱反问；虚了先摸炭条；叫她六丫头'}
    c = casting.instantiate('甲', card)
    txt = casting.render_cast(c, card)
    ok('A5 选角层输出里有「说话指纹」那一行', '说话指纹：' in txt and '摸炭条' in txt, txt[:120])

    # A6 **只有指纹、没有口癖与风格**时也必须生效（这是最常见的真实情形）
    from agent.core import Agent
    stub = types.SimpleNamespace(
        ps=types.SimpleNamespace(catchphrase='', speech_fp='一句不超过十个字；虚了摸炭条'),
        world=types.SimpleNamespace(style_card=None))
    block = Agent._voice_rules(stub)
    ok('A6 只写了指纹也进"开口前"那一段', '说话指纹' in block and '摸炭条' in block, block[:160])

    # A7 成对：三样都空 ⇒ 一个字都不加（不许为了这功能硬塞空段落、白占前缀）
    empty = types.SimpleNamespace(
        ps=types.SimpleNamespace(catchphrase='', speech_fp=''),
        world=types.SimpleNamespace(style_card={}))
    ok('A7 成对：口癖/风格/指纹全空 ⇒ 不拼这一段', Agent._voice_rules(empty) == '',
       Agent._voice_rules(empty)[:80])


# ══════════════════════════════════════════════════════════════════════
#  B 对话标签（副词盖章）
# ══════════════════════════════════════════════════════════════════════
BAD = ('阿甲把算盘往桌上一推。\n'
       '他严肃地说道：「这账不对。」\n'
       '阿乙低声地问：「哪儿不对？」\n'
       '他冷冷地道：「多了一笔。」\n'
       '她轻轻地说：「我看不出来。」\n'
       '「我慢慢地说给你听。」她又补了一句。\n')


def test_tags() -> None:
    print('\nB 对话标签（检测 / 配额 / 清理）')
    from crew import prose_flow as PF
    from crew import repair_recipes as REC

    spans = PF.dialogue_tag_spans(BAD)
    ok('B1a 叙述里的「××地说道 / ××地问」被抓到',
       '严肃地说道' in spans and '低声地问' in spans, spans)

    # B1b 成对：**台词里**的同一串不许抓（"我慢慢地说给你听"是内容，不是盖章）
    ok('B1b 成对：引号里的同一串不抓', '我慢慢地说给你听' not in ' '.join(spans), spans)

    two = '他一字一句地说：「走。」\n她低声地问：「谁？」\n'
    ok('B2a 成对：配额内两处不报', PF.dialogue_tag_issues(two) == [],
       PF.dialogue_tag_issues(two))
    ok('B2b 第三处才报（配额边界）', len(PF.dialogue_tag_issues(BAD)) == 2,
       len(PF.dialogue_tag_issues(BAD)))

    fixed, n = PF.strip_dialogue_tag_adverbs(BAD)
    ok('B3a 清理数得准（4 处命中、前 2 处按配额留着）', n == 4 and '严肃地说道' in fixed, n)
    ok('B3b 超配额的动词归一到 说/问/答（不留「他道」这种半文半白）',
       '他说：「多了一笔。」' in fixed and '她说：「我看不出来。」' in fixed, fixed[-120:])
    # ★★ 这一条是"吃字"守卫：第一版 `re.split` 没写捕获组，整段台词被删掉过
    ok('B3c ★ 引号里的台词一个字都不少（防 re.split 吃掉分隔符）',
       '「这账不对。」' in fixed and '「我慢慢地说给你听。」' in fixed, fixed)

    labels = PF.prose_issue_count(BAD)
    ok('B4a 计数表里有「对话标签」这一类', '对话标签' in labels, list(labels))
    ok('B4b 修复合约登记了它，且没漏也没多',
       '对话标签' not in REC.uncovered(labels.keys())
       and '对话标签' not in REC.extra(labels.keys()),
       (REC.uncovered(labels.keys()), REC.extra(labels.keys())))


# ══════════════════════════════════════════════════════════════════════
#  C 提示词纪律（演员 / 写作层）
# ══════════════════════════════════════════════════════════════════════
def test_prompts() -> None:
    print('\nC 提示词纪律（能不说就不说 / 遮名 / 别答完整 / 别拿副词盖章）')
    from agent.core import Agent
    src = inspect.getsource(Agent.decide)
    need = ['能不说就不说', '遮名测试', '别答完整']
    miss = [w for w in need if w not in src]
    ok('C1 演员尾段有三条纪律', not miss, '缺：' + '、'.join(miss))

    from crew import agents
    live = agents.LIVE_SPEECH_RULES
    need2 = ['能不说就不说', '别拿副词盖章', '遮名要分得出谁']
    miss2 = [w for w in need2 if w not in live]
    ok('C2 写作层（作家/剧作）三条纪律', not miss2, '缺：' + '、'.join(miss2))


# ══════════════════════════════════════════════════════════════════════
#  E 叙事层（2026-10-28）：机器味的大头在**结构**不在词句
#  ⚠ 证据：61,608 篇对照实验（StoryScope，arXiv:2604.03136v6）——
#    只把表面词句换干净，识别率仅 95.5% → 93.9%（1.6 个点）；
#    只给分类器看叙事结构，准确率仍有 93.2%。
#    来源工具：sepia（Nanako0129/sepia, MIT）narrative-pass / rubric；
#    no-ai-slop（petergyang/no-ai-slop, MIT；中文版 shenxianpeng/no-ai-slop）"Patterns to cut"。
# [EN] E. Narrative layer (2026-10-28): the bulk of the machine smell is **structure**, not wording.
# [EN] Evidence: StoryScope 61,608-story controlled experiment -- rewording the surface only moves
# [EN] detection 95.5% -> 93.9% (1.6 pts); narrative structure alone still gives 93.2%.
# ══════════════════════════════════════════════════════════════════════
def test_narrative() -> None:
    print('\nE 叙事层：套话闸 + 开关（机器味的大头在结构）')
    from crew import prose_flow as PF
    from config import CFG

    # E1 —— 最要紧的一条边界：**只查叙述，引号里的台词一条都不查**。
    #   人物说"不是 X，是 Y"是完全自然的（设定集里那句「这页没写坏。是写完了。」
    #   就是活的对白）；把它判成套话 = 误伤作者的好句子。
    for t in ('「这页没写坏。是写完了。」', '「不是我干的，是你。」他说。',
              '她道：「这不是茶的事，是人的事。」'):
        ok(f'E1 ★★★ 台词里的对立**不许判成套话**（误伤比漏报坏）｜{t[:14]}…',
           not PF.slop_spans(t), str(PF.slop_spans(t)))

    hits = PF.slop_spans('这不是钱的事，而是信任。')
    ok('E2 ★★ 叙述层**真的报得出来**（词表里躺着没人用 = 白写）',
       bool(hits), str(hits))

    names = {n for n, _ in PF.slop_spans(
        '这不是钱的事，而是信任。他终于明白。最关键的一点：他没说实话。'
        '这标志着一个里程碑式的时刻。说到底，人都是这样。')}
    ok('E3 五类都能命中（二元对立 / 否定列举 / 冒号揭示 / 重要性吹捧 / 总结式点题）',
       len(names) >= 4, str(sorted(names)))

    three = '这不是钱的事，而是信任。这不是茶的事，而是人。这不是账的事，而是命。'
    ok('E4 ★★ 配额：前两处**不报**（真人也这么说，全报比口径更狠）',
       len(PF.slop_spans(three)) == 3 and len(PF.slop_issues(three)) == 1,
       f'命中 {len(PF.slop_spans(three))} / 报 {len(PF.slop_issues(three))}')

    cnt = PF.prose_issue_count(three)
    ok('E5 ★★ 进**计数表**（不进就没人看，进了才会被多轮检查收敛）',
       cnt.get('套话') == 1, str(cnt.get('套话')))

    # E6 —— 行为级证明开关真的管用（开→有 / 关→无），不是"字符串哨兵"。
    from crew import agents
    was = CFG.b('CREW_ANTI_FP')
    try:
        CFG.set('CREW_ANTI_FP', 'false')
        off = agents.anti_fp_block()
        CFG.set('CREW_ANTI_FP', 'true')
        on = agents.anti_fp_block()
    finally:
        CFG.set('CREW_ANTI_FP', 'true' if was else 'false')
    ok('E6 ★★★ 行为级：`CREW_ANTI_FP` 关→空、开→有'
       '（本项目对每个新规则的统一承诺：关掉回到从前）',
       off == '' and len(on) > 500, f'关={len(off)} 开={len(on)}')

    need = ['情绪', '直接说出来', '天气就是天气', '别把意思点破', '真有的', '别改过头']
    miss = [w for w in need if w not in on]
    ok('E7 四条都在（情绪混用 / 天气就是天气 / 别点破 / 真东西）+ 两条"别改过头"',
       not miss, '缺：' + '、'.join(miss))

    ok('E8 ★★ 明写了"过度纠正也是新指纹"'
       '（不加这句，模型会把全文剁成电报句 —— 那比机器写的还不像人话）',
       '新的指纹' in on and '电报' in on, '')

    # E9 —— 挂载点**恰好两处**：小说作家 + 剧作者。
    #   ⚠ **不挂演员**：这段是长段落，而演员离输出最近，长段落会被它忽略
    #     （本项目的实测结论）⇒ 演员那一层的同款纪律走 `agent/core.py` 的 `_tail` 短句。
    #     挂错地方 = 写了不生效，而判据绿着（正是本项目反复在防的那种）。
    # ⚠ 必须用 **AST** 数，不能对源码 `count('anti_fp_block()')`：
    #   注释里也写着这个名字（本项目注释写得很满），字符串计数会把注释一起数进去 ——
    #   实测数出 5 处，其中 3 处是注释。**注释里的名字不是挂载点。**
    tree = ast.parse(Path('crew/agents.py').read_text(encoding='utf-8'))
    n_mount = sum(1 for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == 'anti_fp_block')
    ok('E9 ★★ 挂载**恰好两处**（小说作家 + 剧作者）—— 多挂一处就挂到演员身上了'
       '（演员离输出最近，长段落会被它整段忽略）'
       '｜⚠ 用 AST 数，**注释里的同名文字不算**',
       n_mount == 2, f'{n_mount} 处')
    core = Path('agent/core.py').read_text(encoding='utf-8')
    ok('E10 ★★ 演员那层**没有**这段长段落（它走 `_tail` 的短句纪律）',
       'ANTI_FINGERPRINT' not in core and 'anti_fp_block' not in core, '')


# ══════════════════════════════════════════════════════════════════════
#  D 某本书的设定集（--project 才跑）
# ══════════════════════════════════════════════════════════════════════
def test_project(proj: Path) -> None:
    print(f'\nD 设定集：{proj.name}')
    cards = sorted(proj.glob('**/02_人物/*.md'))
    if not cards:
        ok('D0 找到人物卡（02_人物/*.md）', False, str(proj))
        return
    texts: dict[str, str] = {}
    bad_len: list[str] = []
    for f in cards:
        t = f.read_text(encoding='utf-8')
        for line in t.splitlines():
            if line.strip().startswith('- **说话指纹**'):
                body = line.split('：', 1)[-1].strip()
                texts[f.stem] = body
                if len(body) > 60:
                    bad_len.append(f'{f.stem}({len(body)})')
    ok('D1 每张人物卡都有「说话指纹」', len(texts) == len(cards),
       f'{len(texts)}/{len(cards)}：缺 ' + '、'.join(sorted({f.stem for f in cards} - set(texts))))
    ok('D2 指纹不许写成长篇小传（≤60 字，否则会变成自我剖白）', not bad_len, bad_len)
    dup = [k for k in texts if list(texts.values()).count(texts[k]) > 1]
    ok('D3 两两不同（遮名测试的机械代理：撞了就分不出谁在说）', not dup, dup)

    rules = sorted(proj.glob('**/01_设定/顶级规则.md'))
    if rules:
        rt = rules[0].read_text(encoding='utf-8')
        need = ['遮名测试', '能不说就不说', '别答完整', '别拿副词盖章']
        miss = [w for w in need if w not in rt]
        ok('D4 顶级规则写进了四条对白纪律', not miss, '缺：' + '、'.join(miss))
    else:
        ok('D4 找到顶级规则.md', False, str(proj))


def main() -> int:
    from tools.verify_exit import finish
    print('说话指纹 —— 遮住名字，还分得出谁在说吗', flush=True)
    proj = None
    if '--project' in sys.argv:
        i = sys.argv.index('--project')
        if i + 1 < len(sys.argv):
            proj = Path(sys.argv[i + 1])
    try:
        test_chain()
        test_tags()
        test_prompts()
        test_narrative()
        if proj is not None:
            test_project(proj)
    except Exception:                                       # noqa: BLE001
        import traceback
        return finish({'checks': CHECKS,
                       'fatal': traceback.format_exc()[-2000:]},
                      out_path=OUT / 'speech_fp_report.json')
    return finish({'checks': CHECKS},
                  out_path=OUT / 'speech_fp_report.json')


if __name__ == '__main__':
    sys.exit(main())
