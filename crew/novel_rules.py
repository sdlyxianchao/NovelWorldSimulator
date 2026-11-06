# -*- coding: utf-8 -*-
"""小说质量规则表 —— **改这一块之前先读这里**（2026-10-19 第八轮整理）。

这份表是"最近几轮修复到底学到了什么"的**唯一登记处**。每一条都是被真实产物
打出来、又被反例法验过的东西；不是设计意图，是**踩过的坑的编号**。

为什么不写成一份 md
------------------
写 md 会烂：改了代码不改文档，文档就开始说谎（本项目已经有一堆这样的段落）。
所以这里是**机器可读的登记表**，`tools/verify_novel_rules.py` 拿它对账：

  · `landing` 指的文件必须真的在；
  · `checks` 指的判据 ID 必须在那个 `verify_*.py` 里真的出现；
  · `mutations` 指的变异编号必须在那个 `mutate_*.py` 里真的存在；
  · `checks` 有而 `mutations` 空的，必须显式登记进 `pending`（欠账），
    欠账条数**不许增长** —— 想加一条欠账，就得先还一条。

文档 `developers/docs/小说质量规则.md` 由
`python tools/verify_novel_rules.py --write-doc` 从这张表生成，
**不要手改那份 md**（判据 C 组会逐字节比对）。

字段怎么填
--------
`countable`（可数形状）是这份表里最要紧的一栏：**一条规则如果写不出"怎么数"，
它就不是规则，是感想。** 本项目反复栽在这上面 —— 用户说"句子太碎"，
四轮探针量出来与真人持平；用户说"人物的话没有线"，字面承接率反而在最好的那版最低。
"""
from __future__ import annotations

from dataclasses import dataclass, field


#: 分层的顺序与中文名（渲染文档时按这个顺序）。
LAYERS: tuple[tuple[str, str, str], ...] = (
    ('measure', '量测', '直觉经常是错的'),
    ('criterion', '判据', '写一条**真能红**的判据'),
    ('fixture', '夹具', '让判据真的碰到被测对象'),
    ('mutation', '反例法', '变异脚本本身也会坏'),
    ('product', '产品', '写出来的东西该怎么改'),
)


@dataclass(frozen=True)
class Rule:
    """一条规则。**每一条都有出处**，不许凭印象写。"""

    id: str
    title: str
    layer: str
    #: 现象 —— 用户原话，或者实测到的具体数字。空话不收。
    symptom: str
    #: ★★★ 可数形状：怎么量它。写不出来就不要收进表。
    countable: str
    #: 怎么改（一句话，能直接落到某个函数上）。
    fix: str
    #: 试过但**错**的解法。这一栏比 fix 值钱 —— 防止下一轮又走一遍。
    wrong: str = ''
    #: 代码落点（相对仓库根）。
    landing: tuple[str, ...] = ()
    #: 探针/测量脚本（`developers/probe_*.py`）。
    evidence: tuple[str, ...] = ()
    #: 已闭环的判据，格式 `verify_xxx:ID`。
    checks: tuple[str, ...] = ()
    #: 对应的反例法，格式 `mutate_xxx:M12`。
    mutations: tuple[str, ...] = ()
    #: 有判据但没配反例法 ⇒ 必须在这里登记，且总数不许增长。
    pending: bool = False
    #: 备注（口径、边界、为什么这么定阈值）。
    note: str = ''


#: 欠账条数上限。**加一条新的欠账就必须先还一条旧的**（这是"不许假装闭环"）。
#: **欠账现在是 0**（2026-10-19 第九轮把六条全还了）。这个值就是"以后不许欠"：
#: 新加一条规则时，判据和反例法要一起写；配不上就把理由写进 note 并**先把上限调高**
#: （那一步必须是一次显式的、能被人看见的决定，不能顺手标个 pending 就过去）。
# [EN] **Debts are now 0** (all six paid off in round nine). The value means "no more debts":
# [EN] a new rule ships its criterion and its mutation together; if you genuinely cannot, raise the
# [EN] cap explicitly -- that has to be a visible decision, not a quiet `pending=True`.
PENDING_MAX = 0


RULES: tuple[Rule, ...] = (

    # ══════════════════════════════════════════════════════════
    #  量测
    # ══════════════════════════════════════════════════════════
    Rule(
        id='R01',
        title='用户说的"感觉"要先用探针量，量完再决定改哪一层',
        layer='measure',
        symptom='「小短句子特别多，每一句都恨不得交代一个事情，说话没逻辑」'
                '（2026-10-19，贴了整段产物）',
        countable='与 `samples/zh/*/正文/*.md` 同口径逐项比：句长中位、分句/句号、'
                  '极短句占比、相邻承接率、逻辑连接词密度。**任一项偏差 < 15% 就不能当病因**。',
        fix='统计持平时，去查"谁把它写成这样"（生成机制），不要继续调阈值。'
            '那一次查出来是改写层 `_transcribe_once`：材料是一拍一行，'
            '提示词写着"一处都不许跳过" ⇒ 模型一行翻一句。',
        wrong='直接写"让模型写长一点" ⇒ 句长中位 10 → 31 字，'
              '整段成逗号长龙，比原来更难看。',
        landing=('crew/agents.py', 'crew/prose_flow.py'),
        evidence=('developers/probe_sentence_flow.py',
                  'developers/probe_clause_density.py',
                  'developers/probe_narration_vs_dialogue.py',
                  'developers/probe_sentence_link.py'),
        note='实测：真人 10.6 / 产物 10（中位），分句 2.38 / 2.30，'
             '逻辑连接词 11.8% / 12.5% —— **全部持平**，而产物确实是坏的。',
    ),
    Rule(
        id='R02',
        title='字面重合量判不了"语义是不是同一条线"',
        layer='measure',
        symptom='「一个人从头到尾说的话之间没有任何关系，不是一系列有关联的事件，'
                '还是不同的事情胡乱跳」',
        countable='同一指标在"人读明显更好"的那一版上**不升反降** ⇒ 该指标失效。',
        fix='语义连贯只能靠两条：①人读（`probe_thread_read.py` 把某人的台词按序打出来）；'
            '②把"线"落成**机制**判据（派活有没有交接、账本在不在、四种走法在不在）。',
        wrong='写一个"人物内承接%"当效果判据 ⇒ 四版分数 34.6 / 50.0 / 35.0 / **27.8**，'
              '而 27.8 那版文本最好（"多留些日子"与"路可就断了"字面不共享任何实词，'
              '语义上是同一件事的加压）。',
        evidence=('developers/probe_character_thread.py',
                  'developers/probe_thread_read.py'),
        note='这是本项目第三次确认同一件事（前两次是"句子太碎"和"接话率"）。'
             '**字面统计量只能当守门员，不能当效果判据。**',
    ),
    Rule(
        id='R03',
        title='判"是不是同一件事"要数共享二元组**个数**，不要用相似率',
        layer='measure',
        symptom='同一晚三次派给同一个人，是同一件事的三种说法'
                '（"送罢酒候在廊下守着那人" / "在廊下守着那人，任房内言语飘过" / '
                '"廊下守着，任那句恨语飘过耳"），字面一个都不相等。',
        countable='共享二元组个数：**同一件事 7–8 个；不同的事只有 3 个**（全是人名）。'
                  '门槛取 5 就干净分开。',
        fix='`director.dispatch` 的"连派同一件"检测按共享二元组个数判。',
        wrong='`store.db.similarity` 判 0.55 阈值 —— 同义换说法只有 **0.33–0.40**，'
              '一次都没触发，她就在廊下守了整场。'
              '**相似率是比值，会被长度稀释；个数不会。**',
        landing=('director/engine.py',),
        checks=('verify_repetition_guards:I39', 'verify_repetition_guards:I40'),
        mutations=('mutate_anchor_thread:M26', 'mutate_anchor_thread:M27'),
    ),

    # ══════════════════════════════════════════════════════════
    #  判据
    # ══════════════════════════════════════════════════════════
    Rule(
        id='R04',
        title='prompt 里写了 ≠ 生效：关键约束必须落到解析层',
        layer='criterion',
        symptom='提示词里"一个句号不超过四十个字""长句最多占三成"每一条都写着，'
                '而连跑四次长句占比 **21% → 60% → 47% → 85.7%**（真人 14.8%）。',
        countable='同一个约束连跑 3 次仍越界 ⇒ 它必须变成代码里的硬闸'
                  '（`prose_flow.split_long_sentences`），不能只留在提示词里。',
        fix='提示词给**目标**，代码给**兜底**：`_fix_flat_paragraphs` 末尾切长句。',
        wrong='继续加提示词（"请一定要写短"）—— 四次实测一次比一次长。',
        landing=('crew/prose_flow.py', 'crew/agents.py'),
        checks=('verify_prose_flow:G8', 'verify_prose_flow:G12'),
        mutations=('mutate_prose_flow:M15', 'mutate_prose_flow:M18'),
    ),
    Rule(
        id='R05',
        title='判据要钉真实生产路径，读它**发出去的东西**',
        layer='criterion',
        symptom='"源码里有没有这串字"这种判据，在把 `open_asks` 换成 `[]` 之后**照样绿**：'
                '文案还在，账本永远算不出来。',
        countable='真跑一次生产函数（`Agent.decide()` / `DirectorEngine.dispatch()`），'
                  '读**发出去的 prompt**、落盘内容或返回值。',
        fix='夹具里替换 `llm.chat` / `ask`，把 messages 抓下来再断言。',
        wrong='`inspect.getsource(...)` 里 `in` 一下就算判过 —— 那是文案判据，不是行为判据。',
        landing=('tools/verify_repetition_guards.py',),
        checks=('verify_repetition_guards:I22', 'verify_repetition_guards:I38'),
        mutations=('mutate_anchor_thread:M12', 'mutate_anchor_thread:M25'),
    ),
    Rule(
        id='R06',
        title='期望值不许来自被测函数的**另一条路**',
        layer='criterion',
        symptom='判"每幕恰好一行幕头"时，从 `full` 里取幕头，而 `full` 是'
                '`scene_lines()` 算的期望值、根本不经过 `_day_lines` ⇒ 恒 0 行、恒假红。',
        countable='判据的**取数源**必须与被测函数是同一份产物（`got`），'
                  '不能是夹具自己拼的另一份。',
        fix='只在"被测函数真跑出来的那一坨"里找。',
        landing=('tools/verify_novel_fullness.py',),
        checks=('verify_novel_fullness:A5b', 'verify_novel_fullness:A5d'),
        mutations=('mutate_novel_fullness:⑯', 'mutate_novel_fullness:⑱'),
    ),
    Rule(
        id='R07',
        title='计数类判据不能用来判"某一处有没有"',
        layer='criterion',
        symptom='判"早退分支也切长句"用的是 `count("split_long_sentences") >= 2`，'
                '而变异把早退那处删掉之后**还剩 2 处**（前置 + 末尾）⇒ 判据照绿。',
        countable='要判"某个位置"，就把那段源码切出来判（`split("if not spans:", 1)`），'
                  '不要数总数。',
        fix='`_fsp.split("if not spans:", 1)[-1].split("_LOG.info", 1)[0]` 再判。',
        landing=('tools/verify_prose_flow.py',),
        checks=('verify_prose_flow:G12',),
        mutations=('mutate_prose_flow:M18',),
    ),
    Rule(
        id='R08',
        title='夹具的字段必须与真实对象对齐',
        layer='fixture',
        symptom='夹具 `_Scene` 只有 `entries`，没有 `time_label` ⇒ '
                '"每一幕有没有时间"在这个夹具里**根本不存在**，'
                '`getattr(sc, "time_label", "")` 恒为空串 ⇒ 幕头判据怎么写都绿。',
        countable='夹具类的字段 ⊇ 被测函数 `getattr` 到的字段。'
                  '**凡 `getattr(obj, "字段", 默认)` 都是在让"字段不存在"隐身。**',
        fix='补齐 `time_label` / `place` / `node_name`，并让时间轴落在一天之内严格递增。',
        wrong='夹具时间写成 `(i % 12) * 2 + 6`，30 幕里绕回两圈 ⇒ A5d（单调递增）'
              '红得**对**，是夹具造了假数据。',
        landing=('tools/verify_novel_fullness.py',),
        checks=('verify_novel_fullness:A5c',),
        mutations=('mutate_novel_fullness:⑰',),
        note='证据：补 `time_label` 之前，A5c 怎么写都绿（`getattr` 取不到就空串）。'
             '补上字段之后，⑰（幕头不写时间）立刻把它打红。',
    ),
    Rule(
        id='R09',
        title='夹具必须走到判据**真正生效的那一步**',
        layer='fixture',
        symptom='"连着两次派同一件事"的检测要"前两次"作历史；'
                '夹具只派了两次 ⇒ 第二次时历史只有 1 条，任何门槛都不触发，'
                '把门槛降到 1 也没反应（变异 M27 没红）。',
        countable='变异之后判据仍绿时，第一问不是"判据太弱"，'
                  '而是"夹具走到那一步了吗"。',
        fix='夹具派**三次**，第三次才断言。',
        landing=('tools/verify_repetition_guards.py',),
        checks=('verify_repetition_guards:I40',),
        mutations=('mutate_anchor_thread:M27',),
    ),
    Rule(
        id='R10',
        title='夹具的量值必须**明显超过**阈值',
        layer='fixture',
        symptom='判"一段不能并太长"的夹具只有 12×17=204 字，上限 260 ⇒ '
                '变异把上限删掉也超不过 ⇒ 变异无效、判据恒绿。',
        countable='夹具量值 ≥ 阈值 × 1.3（本例改成 24 行 ≈ 408 字）。',
        fix='先算一遍数字再写夹具，别凭感觉凑。',
        landing=('tools/verify_prose_flow.py',),
        checks=('verify_prose_flow:G18',),
        mutations=('mutate_prose_flow:M22',),
    ),
    Rule(
        id='R11',
        title='切句门槛按**真人分布**定，不是按提示词里那句目标定',
        layer='criterion',
        symptom='第一版把门槛定成 32，理由是"提示词说的是四十个字，往下让一档"，'
                '而真人句长中位只有 **10.6** ⇒ 按 32 切，切完中位还在 21，等于没切到位。',
        countable='在真产物上扫参数，看中位与长句占比落在真人区间才算数：'
                  '32 → 21 / 43.5%；24 → 17 / 31%；**26 → 18 / 40.9%**。',
        fix='门槛取 26 + 按段配平（每段留最长一句当骨架），不再一路往下压。',
        wrong='一路压到 18 ⇒ 中位 12 看起来更像真人，但碎片成片出现'
              '（"弯身放下："四个字单独成句）。',
        landing=('crew/prose_flow.py',),
        checks=('verify_prose_flow:G11',),
        mutations=('mutate_prose_flow:M17',),
        note='**切句的天花板就是 ~36%**。再往下只有碎片 —— 剩下的差距只能靠模型自己写短。',
    ),
    Rule(
        id='R12',
        title='加一条要求必须同时给上限（钟摆两头都要判）',
        layer='criterion',
        symptom='只写"要并句、要长句" ⇒ 句长中位 10 → 20 → 31；'
                '只写"按幕头写时间" ⇒ 全篇盖了五处"二十三点三十五分"，像值班记录。',
        countable='提示词里每一条"多写 X"都必须能配到一条"最多 X"，'
                  '并且两边各有判据。',
        fix='`一个句号里最多装两件事` / `长句掺着用，三句里有一句长的就够` / '
            '`全篇最多两处钟点` / `一段三到六句` —— 每条上限都给可数的单位或数字。',
        wrong='⚠⚠ 这条的判据自己烂过一次（第九轮查出来的）：B3 原来判 '
              '`"不超过四十个字" in s`，而那句话后来变成了**反面教材**'
              '（"实测这种字数上限模型根本不数"）—— 判据于是靠一句"这条没用"的话'
              '保持常绿。**源码含字符串当判据，会在文案演化中悄悄失效。**',
        landing=('crew/agents.py',),
        checks=('verify_prose_flow:B3',),
        mutations=('mutate_prose_flow:M24',),
        note='B3 现在判的是**真正给出的上限**（"最多装两件事" + "三句里有一句长的就够"）。',
    ),

    # ══════════════════════════════════════════════════════════
    #  反例法
    # ══════════════════════════════════════════════════════════
    Rule(
        id='R13',
        title='变异脚本本身会坏：锚点换行用 `chr(10)`，替换串必须仍是合法 Python',
        layer='mutation',
        symptom='锚点里写 `\\n`（反斜杠 + n 两个字符），经 shell 传参后变成 `/n` ⇒ '
                '一次都匹配不到；只替换两行中的一行 ⇒ 留下孤立括号 ⇒ 语法错误 ⇒ '
                '整份判据崩 ⇒ "没红"是假的。',
        countable='变异之后 `ast.parse` 那两份文件；锚点命中用 `assert count >= 1`。',
        fix='换行用 `chr(10)` 拼；多行锚点整段替换；跑完 `grep -rn "变异："` 查残留。',
        wrong='用 `"a\\nb"` 直接写字面换行 —— Git Bash 会把 `\\n` 转掉（MEMORY 记过这个坑）。',
        landing=('developers/mutate_prose_flow.py', 'developers/mutate_anchor_thread.py'),
    ),
    Rule(
        id='R14',
        title='"变异没红"的第一嫌疑永远是脚本，不是判据',
        layer='mutation',
        symptom='这一轮三次"没红"，全是脚本问题：锚点过时（`merge` 重写后旧串没了）、'
                '换行被转义、夹具太短。判据本身是好的。',
        countable='手动跑一次"变异 + 单条判据"，比反复猜快得多。',
        fix='变异脚本必须在 `patch()` 里 assert 锚点命中；'
            '跑完核对"红的是不是预期那条"。',
        landing=('developers/mutate_anchor_thread.py', 'developers/mutate_prose_flow.py'),
    ),

    # ══════════════════════════════════════════════════════════
    #  产品
    # ══════════════════════════════════════════════════════════
    Rule(
        id='R15',
        title='"该不该切"按**主语切换次数**判，不按长度判',
        layer='product',
        symptom='按长度一刀切，43 字的正常描写被切碎；而真正要治的"一句串四件事"'
                '和它一样长。',
        countable='数一段里有几个不同主语：\n'
                  '✅ `他伸手过去，指尖碰到的那片皮肤是凉的，她没动，屋里静得能听见灯芯炸响`'
                  '（43 字，**2 个**主语 = 一条动作链，长是对的）\n'
                  '❌ `甲拨了拨火箸，火苗跳一下，廊板响，乙端着壶回来，弯身放下，丙退去`'
                  '（40 字，**3 个**主语 = 一句串了四件事）',
        fix='门禁：`不同主语 >= 3` 或 `有真超长句(>=45)` 或 `段内多句且长句过半`。'
            '切点偏好"人名前面"（后半段才有主语）与"的/了/着"之后。',
        wrong='只看 `zh_len(one) > hard_max` ⇒ 好描写被切 → 变全短句 → 白花一次重写'
              '（判据 H4「好文字不动」当场抓到）。',
        landing=('crew/prose_flow.py',),
        checks=('verify_prose_flow:G13', 'verify_prose_flow:G14',
                'verify_prose_flow:G15'),
        mutations=('mutate_prose_flow:M19', 'mutate_prose_flow:M20'),
    ),
    Rule(
        id='R16',
        title='两个相反的病要**分职责**，不要用"回滚"调和',
        layer='product',
        symptom='切句把长句切短 ⇒ `list_like_spans` 判成平铺段 ⇒ 平铺段 0 → 4；'
                '加"切碎就回滚" ⇒ **一个字都没切**。',
        countable='一个函数只治一种病；两条相反判据靠**顺序**互相接住，不靠回滚。',
        fix='`split_long_sentences` 只治"太长"（不回滚）；'
            '`list_like_spans` + 重写只治"太碎"；'
            '而且**先切、再检测、最后温和再切一次**。',
        wrong='回滚两版都死锁：①用 `list_like_spans` 整体判 ⇒ 它同时判两头，'
              '切完仍"长句过半"的段被判中 → 回滚；②只判"太碎" ⇒ '
              '一段只有一句长句时，切开必然是"全短句" = 平铺段 → 回滚。'
              '根因不是回滚写错，是**职责没分开**：一句 66 字的逗号长龙靠"切"永远修不好，'
              '要么还长、要么切碎，只能**重写**。',
        landing=('crew/agents.py', 'crew/prose_flow.py'),
        checks=('verify_prose_flow:G12', 'verify_prose_flow:G17'),
        mutations=('mutate_prose_flow:M18', 'mutate_prose_flow:M21'),
    ),
    Rule(
        id='R17',
        title='排版也是内容："一句一段 + 空行"要用纯代码合并',
        layer='product',
        symptom='整篇变成一句一行、每行之间一个空行；'
                '而合并函数按"连续 4 行"判、遇空行就 flush ⇒ **一行都没合并**'
                '（44 行正文 / 47 个空行全没动）。',
        countable='一次合并之后：段数应明显减少，且**汉字数一个不差**。',
        fix='空行算作"连续"（模型用空行分的是句子，不是段落）；'
            '一段上限 220 字（不给上限时 44 行并成 **2 段**，比原来更难读）；'
            '不合并时空行**原样还回去**。',
        wrong='遇空行 flush ⇒ 攒到 1 行就断开，等于没合并。',
        landing=('crew/prose_flow.py',),
        checks=('verify_prose_flow:G16', 'verify_prose_flow:G17', 'verify_prose_flow:G18'),
        mutations=('mutate_prose_flow:M21', 'mutate_prose_flow:M22',
                   'mutate_prose_flow:M23'),
    ),
    Rule(
        id='R18',
        title='材料里没有时间 ⇒ 时序必乱',
        layer='product',
        symptom='「岛村两次说"终于到了，先休息一下吧"」「"夜深了"反复强调」'
                '「整个时间线像是打乱的拼图」。',
        countable='整理材料里每一幕是否带钟点、钟点是否单调递增；'
                  '正文里"一次性短语"（终于到了 / 刚到）重复次数、"时段转折"'
                  '（夜深了）超配额次数、"钟点当句首"处数。',
        fix='`sim/loop._day_lines` 每幕前加一行幕头 `〔第 N 幕 · 子时 23:40 · 地点〕`；'
            '`prose_flow.time_anchor_issues` 判重复与配额；提示词"时间只准从幕头来"。',
        wrong='只在提示词里写"注意时间顺序" —— 材料里根本没有时间，模型只能自己编。',
        landing=('sim/loop.py', 'crew/prose_flow.py', 'crew/agents.py'),
        checks=('verify_novel_fullness:A5b', 'verify_novel_fullness:A5d',
                'verify_prose_flow:J1', 'verify_prose_flow:J3',
                'verify_prose_flow:J9'),
        mutations=('mutate_novel_fullness:⑯', 'mutate_novel_fullness:⑰',
                   'mutate_prose_flow:M13'),
        note='三个变异掐三种可能：**没有幕头**（⑯）/ **幕头没钟点**（⑰）/ '
             '**钟点当句首泛滥**（M13）。⑱（时间倒序）专门证明"单调递增"那一半是独立的。',
    ),
    Rule(
        id='R19',
        title='一次性事件与时段转折的**台词口径不同**',
        layer='product',
        symptom='第一版把两类词都只算叙述 ⇒ "两次说终于到了"（那正是用户点名的现象，'
                  '发生在台词里）判不出来；两类都算 ⇒ 人物嘴上说"夜深了"被误判成叙述乱了。',
        countable='`ONE_SHOT`（终于到了/刚到）**台词也计入** —— 它不是说话方式，'
                  '是事件本身；`PERIOD_TURN`（夜深了/更鼓）**只计叙述**。',
        fix='`time_anchor_issues` 里分别用 `full` 与 `bare = _strip_quotes(full)`。',
        landing=('crew/prose_flow.py',),
        checks=('verify_prose_flow:J1', 'verify_prose_flow:J5'),
        mutations=('mutate_prose_flow:M25', 'mutate_prose_flow:M26'),
        note='⚠ J5 的夹具原来是**假绿**：它只写了两句台词，而「夜深了」的配额正好是 2，'
             '口径换成"连台词一起数"也照样不过线 ⇒ M26 打不红。改成三句才测得出。'
             '（夹具必须走到判据真正生效的那一步 —— 就是 R09。）',
    ),
    Rule(
        id='R20',
        title='态度要有台阶："一直在躲"到"突然改口"中间必须有一级',
        layer='product',
        symptom='「反复"没听清"（至少三次）…突然"捕捉到一点"，这个转变**缺乏铺垫**」。',
        countable='`world.dodge_count()` 数"用同一种方式躲了几次"；'
                  '躲到第 3 次**必须表态**（承认 / 拒绝 / 改口），不许"没听清"第四次。',
        fix='账本进提示词（`[你一直在躲]`），并给三种表态方式。',
        wrong='只写"别一直躲" —— 模型会再躲一次（没有任何可数的事实压着它）。',
        landing=('world/state.py', 'agent/core.py'),
        checks=('verify_repetition_guards:I33', 'verify_repetition_guards:I34',
                'verify_repetition_guards:I35', 'verify_repetition_guards:I36'),
        mutations=('mutate_anchor_thread:M19', 'mutate_anchor_thread:M20',
                   'mutate_anchor_thread:M21'),
    ),
    Rule(
        id='R21',
        title='配角像 NPC 的根因在**派活**：导演只收到一个名字',
        layer='product',
        symptom='「叶子几乎只在做两件事：送东西和提醒…更像一个推动场景转换的"NPC"」。',
        countable='派活日志里这个人的连续三次：是同一件事的换说法（共享二元组 7–8 个）'
                  '还是三件不同的事。',
        fix='`dispatch` 递**人设**（身份 / 性子 / 他自己想要的），'
            '并检测"连着两次派同一件" ⇒ 第 3 次强制换，且要贴着他自己想要的换。',
        wrong='在改写层加一句"配角要有自己的动机" —— 上游派不出有动机的活，'
              '下游只能编个姿势。**她不是被写成 NPC 的，是派活时不知道她是谁。**',
        landing=('director/engine.py',),
        checks=('verify_repetition_guards:I38', 'verify_repetition_guards:I39',
                'verify_repetition_guards:I40'),
        mutations=('mutate_anchor_thread:M25', 'mutate_anchor_thread:M26',
                   'mutate_anchor_thread:M27'),
    ),
    Rule(
        id='R22',
        title='派活要**接着上一件**：目标每 8 拍漂移一次，下游怎么改都没用',
        layer='product',
        symptom='同一晚三次派给同一个人：「让陪伴显得自然妥帖」/「护住谈笑余温」/'
                '「达成对那声姐的安然受用」—— 三件毫无关系，而且全是**氛围描写**，'
                '人物演不出来。',
        countable='连续两轮派给同一个人的活：新的一件是不是上一件的**下一步**'
                  '（能说出"它办成了会变成什么"）。',
        fix='`_last_dispatch` 记住上一轮并递回提示词；明写"新派的一件必须是上面那件的下一步"；'
            '同一件事推 3 次没结果 ⇒ 派"把它逼出结果的那一步"；**禁止氛围描写**。',
        wrong='只在演员层加"你要有自己的一条线" —— 线的上头每 8 拍被剪断一次。',
        landing=('director/engine.py',),
        checks=('verify_repetition_guards:I29', 'verify_repetition_guards:I30',
                'verify_repetition_guards:I31', 'verify_repetition_guards:I32'),
        mutations=('mutate_anchor_thread:M16', 'mutate_anchor_thread:M17',
                   'mutate_anchor_thread:M18'),
    ),
    Rule(
        id='R31',
        title='反例法**被打断**会把变异留在产品源码里，而紧接着那次真跑用的是变异版',
        layer='mutation',
        symptom='`sim/loop.py:6651` 残留过 `out.append(ln)   # 变异：不去重`；'
                '十分钟后又残留了 `if False:` 那一行。两次都是'
                '**反例法跑到一半被 SIGTERM**，`finally` 没执行。',
        countable='扫产品源码：行里既有代码、`#` 之后又有 `变异：` ⇒ 就是残留。'
                  '（说明文字里的"变异："不算 —— 那种行没有 `#`。）',
        fix='`verify_mutation_anchors` 的 E 组：`mutation_leftovers()` 返回 '
            '`["sim/loop.py:6651"]`，非空即红。**跑真跑之前必须先跑它。**',
        wrong='⚠ 已有的检测（`run_all_verifications._mutation_leftovers`）**只在全量回归里跑** ——'
              '单跑一个 mutate 脚本、被中断，没有人会去看。'
              '⚠⚠ **判法试了三版才对**：①"行里有 `变异：`" ⇒ 把说明文字判成残留；'
              '②"`#` 之后且 `#` 前有代码" ⇒ 把**字符串字面量里的井号**当成注释'
              '（`symptom=…残留过 out.append(ln)   # 变异：不去重` 正是这种）。'
              '③定案：用 `tokenize` 只认 `COMMENT` token —— 只有它能分清"注释"和'
              '"字符串里的井号"。',
        landing=('tools/verify_mutation_anchors.py',),
        checks=('verify_mutation_anchors:E1', 'verify_mutation_anchors:E2'),
        mutations=('mutate_mutation_anchors:P06',),
        note='这条的代价很实在：`snow_v10` 那次真跑就是在残留版代码上跑的，'
             '产出的数字**不可信**（已重跑 `snow_v11`）。',
    ),
    Rule(
        id='R32',
        title='重写出来的段落**没人收排版**：模型被要求"铺开"就逐句分行写',
        layer='product',
        symptom='`snow_v11` 开头 merge 过一遍（14 段那批正常），但产物里仍有一整段是'
                '**一句一行**（叶子送酒那 8 行）。',
        countable='`_fix_flat_paragraphs` 里 `merge_one_line_paragraphs` 被调用 **几次**；'
                  '≤1 次 = 重写那一支没人收。',
        fix='末尾（**切句之后**）再 merge 一次。它只动"连续 ≥4 行、每行 ≤2 句"的块，'
            '对已铺开的段落零影响（真人样本 23 段→23 段）。',
        wrong='⚠ 只加"开头 merge"是不够的：merge 在检测**之前**，而重写在检测**之后** ——'
              '两者之间隔着模型，它返回什么就落什么。',
        landing=('crew/agents.py',),
        checks=('verify_prose_flow:G19', 'verify_prose_flow:G20'),
        mutations=('mutate_prose_flow:M34',),
    ),
    Rule(
        id='R26',
        title='反例法会**静默失效**：锚点被重构搬走后，变异什么都不做，而人只看到"没红"',
        layer='mutation',
        symptom='`mutate_novel_fullness.py` 的 #1/#9 两个锚点早在加幕头、重写第 5 条时就过期了，'
                '脚本直接拒跑 —— 这份反例法很久没人跑过。实测全库：'
                '597 条可静态核对的锚点里 **56 条已打死（9.4%）**；128 个反例法脚本里'
                '只有 65 个有锚点自检，其余 63 个连"没命中就停"都没有。',
        countable='把反例法里 `(标题, 路径, 旧串, 新串, 期望)` 的**旧串**取出来，'
                  '去目标源码里数 `count(旧串)`；`== 0` 就是死的。'
                  '现可静态核对 597 条（活 541 / 死 56），另 1050 条是用 `chr(10)` 拼的，摘不出来。',
        fix='`tools/verify_mutation_anchors.py` 把失效列成基线 `developers/_anchor_baseline.txt`，'
            '判据 B1 要求"基线以外全部命中"—— 以后谁重构搬走锚点，当场红。'
            '基线**只许减不许增**（修一条删一条）。',
        wrong='⚠ 写过一版"自动重定位"（`developers/repair_anchors.py`）：按"逐行 strip 相同"'
              '去源码里找新位置。**只修得了 1 条** —— 失效的 56 条里绝大多数是代码真的改了，'
              '不是缩进漂移。这类只能人工改锚点或删掉那条变异。',
        landing=('tools/verify_mutation_anchors.py', 'developers/_anchor_baseline.txt',
                 'developers/repair_anchors.py'),
        checks=('verify_mutation_anchors:A2', 'verify_mutation_anchors:B1',
                'verify_mutation_anchors:C1', 'verify_mutation_anchors:C2',
                'verify_mutation_anchors:D2'),
        mutations=('mutate_mutation_anchors:P01', 'mutate_mutation_anchors:P02',
                   'mutate_mutation_anchors:P03', 'mutate_mutation_anchors:P04',
                   'mutate_mutation_anchors:P05'),
        note='⚠ C1（"已修好的必须从基线删掉"）**没有反例法**：要验它得先把一条真失效的锚点'
             '修活，而改哪一行取决于当前代码，盲替换会改错位置（试过）。这条欠账记在这里。',
    ),
    Rule(
        id='R27',
        title='**注释里宣称的自检，必须真的存在**',
        layer='criterion',
        symptom='`verify_generic_project.py` 的注释写着"下面的自检（往产品文件里塞一个书名，'
                '看它抓不抓）依然在跑"，**实际一行都没有**。',
        countable='注释里出现"自检""仍在跑""依然在跑"之类的话，就去 AST 里数该文件有没有'
                  '对应的检查语句 —— 零条就是谎。',
        fix='补上 D 组四条：①产品文件里塞书名必须被抓；②被跳过的目录里塞书名必须绕过；'
            '③同名但不在该前缀下的 `results/` 不许跳过；④每条跳过都是显式前缀。',
        wrong='⚠ 每加一条 `SKIP_*`，扫描面就缩小一块，而**放宽从不报警**。'
              '所以跳过不能按目录名匹配（`results` 太通用），只能按**路径前缀**。',
        landing=('tools/verify_generic_project.py',),
        checks=('verify_generic_project:D1', 'verify_generic_project:D2',
                'verify_generic_project:D3', 'verify_generic_project:D4'),
        mutations=('mutate_generic_project:G1',),
        note='四个判据各守一头：D1 证明扫描真的在扫、D2 证明跳过真的生效、'
             'D3 证明口径是路径前缀不是目录名、D4 证明没有裸目录名。',
    ),
    Rule(
        id='R28',
        title='判"派活是不是漂移"不能用字面重合 —— 但可以用"**他还在办吗**"',
        layer='product',
        symptom='同一晚三次派给同一个人：「说定再消磨几日」→「静看不插一言」→'
                '「把自语当风景照旧消磨」。三件共享 **0** 个二元组 —— 既不是重复，也不是下一步。',
        countable='把上一件的 2 字片段（剔人名与虚词开头）拿去他最近 6 条**自己的**言行里找，'
                  '命中 **≥ 2 个** ⇒ 他还在办。',
        fix='`sim/loop._maybe_dispatch`：**还在办就不覆盖** `ps.mission`（跳过这个人）。'
            '这是结构性的 —— 以前是 `ps.mission = what` 无条件覆盖。',
        wrong='⚠ 先试过"共享 0 就判漂移、强制重派"：实测**判不了**——'
              '真正的漂移共享 0，而正常的下一步（"说定消磨几日"→"把这话说给驹子听"）'
              '**也是 0**（"这话"是代词）。拿它当闸会把大量正常推进当成漂移、'
              '逼导演改成模板。⇒ 那个函数（`director.assignment_shared`）降级为**只记日志**的诊断。',
        landing=('sim/loop.py', 'director/engine.py'),
        checks=('verify_repetition_guards:I50', 'verify_repetition_guards:I51',
                'verify_repetition_guards:I53', 'verify_repetition_guards:I54'),
        mutations=('mutate_anchor_thread:M33', 'mutate_anchor_thread:M34',
                   'mutate_anchor_thread:M35'),
    ),
    Rule(
        id='R29',
        title='称呼一换，读者就读成"关系变了" —— 换必须有事垫着',
        layer='product',
        symptom='「驹子从称"客人"改口称"岛村先生"——这个转变**没有心理或事件上的铺垫**。'
                '称呼是人际关系最直接的反映，它的变化必须有情感逻辑支撑。」',
        countable='同一个说话人、同一个对象、用了 **几种**称呼（`world.address_ledger`）。'
                  '≥ 2 种就说明换过。',
        fix='账本进提示词：列出"你叫过他 X 次、Y 次"，给两条出路'
            '（有事垫着再改口 / 没事就还用原来的）。',
        wrong='⚠ 「名字+称谓」必须算**一个**称呼：第一版按词表顺序挑、第二版按位置挑，'
              '两次都把「岛村先生」记成「先生」——**改口这件事本身被抹掉了**。'
              '现在称谓前面紧挨着人名时，拼成整体。',
        landing=('world/state.py', 'agent/core.py'),
        checks=('verify_repetition_guards:I44', 'verify_repetition_guards:I45',
                'verify_repetition_guards:I46', 'verify_repetition_guards:I48'),
        mutations=('mutate_anchor_thread:M31', 'mutate_anchor_thread:M32'),
    ),
    Rule(
        id='R30',
        title='"反应标签"是**叙述层**的复读，与台词层的口癖不是一回事',
        layer='product',
        symptom='「"慢一拍""没听清""答非所问"出现了七次以上…第一次用是惊艳，第二次是强化，'
                '**第三次开始是重复，第四次之后是读者的疲劳**。」',
        countable='叙述里（**不含台词**）数"慢一拍/没听清/迟疑/顿了顿/怔了怔"这类现成写法，'
                  '**同一个超过 2 次**就报。',
        fix='提示词第 4.4 条给上限两次 + 四条替代写法（写他做了什么却没接话 / 写别人怎么看他的'
            '沉默 / 说别的 / 干脆跳过）；检测器只记日志不改字。',
        wrong='⚠ 只记日志**不等于修好了** —— 真正起作用的是提示词。'
              '要说"改善了多少"只能看下一轮真跑的计数。',
        landing=('crew/prose_flow.py', 'crew/agents.py'),
        checks=('verify_prose_flow:K1', 'verify_prose_flow:K2', 'verify_prose_flow:K3',
                'verify_prose_flow:K5'),
        mutations=('mutate_prose_flow:M31', 'mutate_prose_flow:M32',
                   'mutate_prose_flow:M33'),
    ),
    Rule(
        id='R24',
        title='最短的口癖是**2 字**，而"只留 3 字以上连续段"的正则正好把它丢掉',
        layer='product',
        symptom='`snow_v10`（第十轮真跑）里岛村 7 句台词有 **5 句**以「是啊」开头、'
                '驹子 10 句以「客人，您」开头，而语气配额**一声不响**。',
        countable='把台词按**标点切段**，数"同一个 2–8 字段在几段里出现过"。'
                  '「是啊。」后面紧跟句号 ⇒ 那段只有 **2 个字**，'
                  '`[\u4e00-\u9fff]{3,}` 会整段丢掉。',
        fix='先用 `[\u4e00-\u9fff]+` 取所有段，**整段 2–8 字直接计入**，再做 5/4/3 字滑窗。'
            '整段计数**不适用**"停用开头"表 —— 那张表防的是滑窗跨词切碎片，'
            '而整段两端都是标点、从来没被切过。',
        wrong='⚠ 第一版把整段计数和滑窗**分别累加** ⇒ 同一短语既等于整段又被 4 字滑窗切到，'
              '数了两遍（5 次报成 6 次）。第二版改成"每段只记一次"却仍然数错，'
              '因为 `''.join(texts)` 把**相邻两行拼成一段**，跨行的两次重复被并成一次'
              '（5 次报成 4 次）。⇒ 两处一起改：**按行分隔 + 每段去重**。',
        landing=('agent/core.py',),
        checks=('verify_repetition_guards:I41', 'verify_repetition_guards:I42',
                'verify_repetition_guards:I43'),
        mutations=('mutate_anchor_thread:M28', 'mutate_anchor_thread:M29',
                   'mutate_anchor_thread:M30'),
        note='计数口径统一成"**在几段里出现过**" —— 这也是读者感受到的那个量。',
    ),
    Rule(
        id='R25',
        title='判"是不是同一件事"要先**剔掉人名**，人名不构成证据',
        layer='measure',
        symptom='`snow_v10` 里叶子连续三次被派「在廊下守着」，而"连派同一件"检测'
                '一次都没触发 —— 那三句只共享 4 个二元组，其中两个只是名字（`让叶` `叶子`）。',
        countable='共享二元组个数（**剔除由人名字符组成的二元组**）：'
                  '同一件事的换说法 **2–3**；不同的事、以及"派活了但没接着上一件" **全是 0**（10 对实测）。',
        fix='门槛取 **2**。原来是 5，因为把名字也算进"证据"了。',
        wrong='门槛收到 3 或 4 都不行：实测「同一件 驹子2」只有 3，而「不同的事」也能到 3 —— '
              '不解耦人名的话，这两类根本分不开。',
        landing=('director/engine.py',),
        checks=('verify_repetition_guards:I39', 'verify_repetition_guards:I40'),
        mutations=('mutate_anchor_thread:M26', 'mutate_anchor_thread:M27'),
    ),
    Rule(
        id='R23',
        title='提示词里的例子会被当素材抄，正反例都一样',
        layer='product',
        symptom='正例 `"你这个人哪。"` 真跑用了 **8 次**；'
                '反面例子 `"你觉得我是个什么样的人？"` 被模型**照抄**进正文。',
        countable='正文里那条例子的原样出现次数。',
        fix='**例子里不出现具体台词**：要举例就写"动作 + 句式 + 占位"，不写句子本身。'
            '反例同理 —— 反例也要"具体到形态"（三个引号各自独立、中间没垫着、'
            '彼此看不出关系），并明写"这里故意不给例句"。',
        wrong='⚠⚠ 原来的判据方向是反的：`verify_prose_flow` 的 C4 曾经要求反例里'
              '**必须**写三句现成台词（"水还温着"/"外头好像有人"/"你怎么不答我"）——'
              '判据在逼人往提示词里放会被抄的素材。已改成"具体到形态"。',
        landing=('crew/agents.py', 'prompts/agent_decide_tail.txt'),
        checks=('verify_prose_flow:A8', 'verify_prose_flow:A9',
                'verify_prose_flow:C4'),
        mutations=('mutate_prose_flow:M27',),
        note='A8 的口径**故意窄**：只抓"以第二人称或呼语开头的整句"'
             '（`先生，…` / `你…。`）。更宽的两版都误伤了叙述示例'
             '（`擦得慢，像在磨什么` 是教"写看得见的样子"，删了模型就不会写）——'
             '**动作示例与台词示例形状完全一样，只能靠开头分**。'
             '已知会漏"我"开头与名字开头的台词，那两类只能人读，判据不假装完备。',
    ),
    Rule(
        id='R33',
        title='反例法的锚点必须**恰好命中 1 次**，而且必须打在**真会被读的那一份**上',
        layer='mutation',
        symptom='2026-10-19 第十二轮一次抓到两条静默假绿：'
                '① `mutate_dispatch` 的 "派活结果不写进 ps.mission" 锚点是裸的'
                '`ps.mission = what`，而 `sim/loop.py` 的**注释里**也写着同一串 ⇒ '
                '`count == 2` ⇒ `replace(..., 1)` 改的是**注释** ⇒ 变异什么都没做、判据当然还绿；'
                '② 同脚本的 "提示词里换回写死的三层说法" 改的是 `agent/core.py` 的 f-string 副本，'
                '而 `PROMPTS_DIR/agent_decide_tail.txt` **优先** ⇒ Python 那份只是兜底、'
                '在真机上**从不生效** ⇒ 又一行死代码。两条都静默存在了好几轮。',
        countable='锚点在目标文件里的命中次数 `count(锚点) == 1`；'
                  '以及"锚点所在文件 = 生产侧真读的那一份"'
                  '（提示词这类两份实现的，看 `PROMPTS.template()` 的选取路径）。',
        fix='① 每条 `mutate_*.py` 在跑变异**之前**先自检 `assert count == 1`，'
            '把"命中 0 次"和"命中 ≥2 次"一起挡住；'
            '② 锚点尽量带**上下文**（多行锚点用 `chr(10)` 拼），不要用裸短串；'
            '③ 两份实现的东西，锚点钉在**优先级高的那一份**上，并在注释里写明为什么。',
        wrong='⚠ 只判 `count == 0`（现在的 `tools/verify_mutation_anchors.py` 就这么做）'
              '**查不出 `count >= 2`** —— 而 `count == 2` 恰恰是最毒的一种：'
              '它让变异"看起来跑过了"。已在本脚本里加运行前自检补住这一条。'
              '⚠ 别把"命中 >1 次"一刀切判红：少数脚本**故意** `replace(old, new, 1)` 去打'
              '多个相同行里的第一个（写明了原因的那种），一刀切会误伤。',
        landing=('developers/mutate_dispatch.py', 'developers/mutate_anchor_thread.py',
                 'tools/verify_mutation_anchors.py'),
        note='**这是手法条（layer=mutation），不是判据条** —— '
             '"跑变异前自检锚点"这件事本身不可自动化（反例法是改源码的那一方，'
             '让它自带的自检去守全局判据，会把因果关系绕回来）。'
             '⇒ 靠 `developers/mutate_*.py` 里那一句 `assert count == 1` 执行，'
             '`tools/verify_mutation_anchors.py` 只负责 `count == 0` 那一半。'
             '凡新写/改一个反例法脚本，第一件事就是补上这句自检。',
    ),
    Rule(
        id='R34',
        title='"上一件还在办就不换"必须配**卡死放行闸**，否则越卡住越永远派不到活',
        layer='product',
        symptom='`snow_v11` 真跑：第 16 拍、第 24 拍连续两次'
                '「派活：1 人的上一件还在办，这一轮不换（同一个人）」。'
                '当天只派出 2 人的活、`dialogue` 从 36 条掉到 18 条、正文 1075 → 656 字（-39%）。'
                '剧本审读三次抓到同一个人"位置倒退""把上一拍已完成的动作又说一遍"'
                '"未按派活要求把那件事办成" —— 全是同一件派活在打转。',
        countable='同一个人被"上一件还在办"**连续拦下几轮**'
                  '（`PersonState.mission_stuck`：只在被拦时 +1，派到新活立刻归零）。'
                  '攒到 `DISPATCH_STUCK_ROUNDS` 轮还在"办" ⇒ 判卡死。',
        fix='`sim/loop.stuck_mission_release(rounds, cap)` 纯函数 + `_maybe_dispatch` 里放行：'
            '连续被拦 `cap` 轮 ⇒ 强制换新目标，并单独打一行日志'
            '「派活放行：…判卡死，强制换新的」。'
            '新旋钮 `DISPATCH_STUCK_ROUNDS`（默认 2，0 = 关闸 = 老行为）。',
        wrong='⚠⚠ 原注释写的防卡方向是**反的**："如果他自己卡住了（关键词一直不出现），'
              '下一轮就会重新派" —— 那治的是"人停了不干"；实测的卡住形状是'
              '**关键词一直在、事一直没办成**。而拦人时只 `missions.pop(name)`、'
              '**`ps.mission` 一个字节都没动** ⇒ 下一轮同一串派活 + 同一个"最近 6 条自己言行"'
              '窗口 ⇒ 同一个 True ⇒ 再拦。**越卡住越永远派不到活。**'
              '⇒ 门槛必须记"轮数"而不是等关键词消失。'
              '⚠ 轮数是**本轮之前**已攒下的数（不含本轮）：`cap=2` = 空转两轮、第三轮强制换。',
        landing=('sim/loop.py', 'world/state.py', 'config.py'),
        checks=('verify_dispatch:E1', 'verify_dispatch:E2', 'verify_dispatch:E3',
                'verify_dispatch:E4', 'verify_dispatch:E5', 'verify_dispatch:E6'),
        mutations=('mutate_dispatch:M36', 'mutate_dispatch:M37',
                   'mutate_dispatch:M38', 'mutate_dispatch:M39',
                   'mutate_dispatch:M40'),
        note='E2（该放行时真放行）与 E3（关闸后真的每轮都被拦、目标一个字节不变）'
             '是**成对**的 —— 没有 E3，E2 可能只是测试里压根没触发拦截。'
             'E4 走 AST 扫"真正的属性读 / getattr 兜底"：用字符串包含判会被引号一换就漏。',
    ),
    Rule(
        id='R35',
        title='**悬空第三人称**：引语里的"她/他"落不到地上 ⇒ 事件里根本不许有引语',
        layer='product',
        symptom='用户点名"最致命"的一条：`驹子忽然安静，说"她恨我"，又笑着说"算了"` —— '
                '那句话在正文里**全文找不到"她"是谁**，情感分量很重却毫无承接。'
                '**六次独立真跑、五次命中同一句**'
                '（`snow_v10` / `snow_v11` / `scale1` / `snow_thread3` / `snow_time1` / `ykg1000`）。',
        countable='一句引语里用了第三人称代词（他/她），而**同一行材料里、引语之前**'
                  '除说话人自己之外**没有出现过任何人名**'
                  '（`prose_flow.dangling_reference`：`names` 取当天在场名单，'
                  '说话人不传时按"行内最早出现的名字"推断）。',
        fix='两道闸，成对：'
            '① **导演事件里不许有引语**（`director/engine._inject_event` 的硬闸 '
            '+ 提示词那一行）—— 事件是"发生的事"，不是"某人说的一句话"；'
            '② **整理材料按行剔**（`crew/agents.Novelist._drop_dangling_lines`）—— '
            '同样的形状从别的路进来（角色自己说的、心声、旁白）也拦得住。'
            '闸门给模型**一次**重写机会，再犯就 `return None`（宁缺毋滥）。',
        wrong='⚠⚠ 判"引语里有没有第三人称"**必须按行判，不能等成稿**：'
              '成稿是按段的 —— 那一行一旦并进段落，段里到处是人名'
              '（`叶子` 前两行刚出现过），判据就看不见它了。'
              '实测把窗口放宽到"同段"后，这条判据**一次都不红**。'
              '而**写这一行的人（小说作家）手上只有这些行** —— '
              '连写的人都不知道"她"是谁，读的人更不可能知道。'
              '⇒ 按行判，判的正是"这一行还能不能被写进小说"。'
              '⚠ 已知的漏（可数性换来的）：同一行里**出现过别的名字**时不判，'
              '即使那只是顺带被提到（`驹子接下门边叶子递来的酒壶…说"她恨我"`）—— '
              '那需要"铺垫足不足"这种语义判断。这条路由事件闸兜住。',
        landing=('crew/prose_flow.py', 'director/engine.py', 'crew/agents.py'),
        checks=('verify_prose_flow:I1', 'verify_prose_flow:I2', 'verify_prose_flow:I3',
                'verify_prose_flow:I4', 'verify_prose_flow:I5', 'verify_prose_flow:I6',
                'verify_prose_flow:I7', 'verify_prose_flow:I8', 'verify_prose_flow:I9',
                'verify_prose_flow:I10', 'verify_prose_flow:I11', 'verify_prose_flow:I12',
                'verify_prose_flow:I13', 'verify_prose_flow:I14'),
        mutations=('mutate_prose_flow:M36', 'mutate_prose_flow:M37',
                   'mutate_prose_flow:M38', 'mutate_prose_flow:M39',
                   'mutate_prose_flow:M40', 'mutate_prose_flow:M41',
                   'mutate_prose_flow:M42'),
        note='实测安全边界：18 个真跑的 **4,959 行**材料里，行级判据命中 **2 行**，'
             '两次都是同一句"她恨我"，**零误报**。\n'
             '★ I3（判悬空）与 I4（引语前有别人名字 ⇒ 不判）、'
             'I6（没有引号的事件不判）、I7（没有在场名单就不判）都是**成对**的 —— '
             '单有 I3 会变成"看到第三人称就红"。',
    ),
    Rule(
        id='R36',
        title='**进出场断链**：标了退场的人又动了，中间没有进场标记',
        layer='product',
        symptom='用户报的第四条：「叶子行动线逻辑矛盾：送酒 → 退下 → **无回归标记**又出现 '
                '→ 拿凉壶 → 送回温好的酒」。整理稿里写成"叶子低头退下 …… '
                '她把壶往驹子手边推了推"—— **人在门外却伸手进屋**。',
        countable='材料里出现 `〔退场〕X（…）` 之后，X 又作为**说话人**出现在一行 '
                  '`X：…` / `X（…）对Y：…` 里，而两者之间既没有 `〔出场〕X`、'
                  '也没有换幕（`prose_flow.presence_chain_breaks`）。',
        fix='两半，缺一不可：\n'
            '① **先把标记造出来** —— 导演事件本来就带结构化的 `离场人物` / `进场人物` '
            '两栏（`DirectorEvent.leaving` / `.entering`，提示词 JSON 规范里那两行），'
            '`scene_builder.observe_event` 据此往材料里补 `〔退场〕X（离场）` / '
            '`〔出场〕X（入画）`（与 `_sync_cast` 发的标记同一形状）；\n'
            '② **再让判据盯着它** —— `prose_flow.presence_chain_breaks` 判链，'
            '`crew/agents.Novelist._presence_break_note` 在**真有断链时**往整理提示词里'
            '插一句指令（"要么补一次他回来，要么把两次并成一次完整动作"）。',
        wrong='⚠⚠ 另外两条更"自然"的路都被实测堵死了，别再走：\n'
              '① **按词表判**（"退下 / 回去 / 离开 / 出门…"）：19 个真跑项目 / 47 份'
              '白天材料上 **11 命中里 10 条误报** —— 「离开膝上的白羽折扇」'
              '「半起又压回去」「把后半句咽回去」「又收回去」'
              '「天亮前不要出门（台词）」。自由文本里的"走"，十个里九个不是离场；\n'
              '② **挂世界状态**：`_sync_cast` 的退场那一支在生产里**一次都没响过**'
              '（同上样本：`exit` 词条 **0 条**、`enter` 词条 77 条）—— '
              '`world._loc_matches` 有意从宽（"他只是挪到门外/柜台后"算在场），'
              '人物 `status` 永远是「在场」。\n'
              '⇒ 唯一可靠的来源是**结构化标记本身**。\n'
              '⚠ 还有一条：这道判据只**提醒**、不**删行**。'
              '"人在门外却伸手进屋"有两种来历，可数地分不开 —— 真断链，与'
              '合法的隔门对话（材料行形状完全相同，都是 `名字：…`）。'
              '删行会把一句真台词连材料一起删掉。',
        landing=('crew/prose_flow.py', 'display/scene_builder.py',
                 'director/engine.py', 'crew/agents.py'),
        checks=('verify_prose_flow:J0', 'verify_prose_flow:J1', 'verify_prose_flow:J2',
                'verify_prose_flow:J3', 'verify_prose_flow:J4', 'verify_prose_flow:J5',
                'verify_prose_flow:J6', 'verify_prose_flow:J7', 'verify_prose_flow:J8',
                'verify_prose_flow:J9', 'verify_prose_flow:J10', 'verify_prose_flow:J11',
                'verify_prose_flow:J12', 'verify_prose_flow:J13', 'verify_prose_flow:J14',
                'verify_prose_flow:J15', 'verify_prose_flow:J16', 'verify_prose_flow:J17',
                'verify_prose_flow:J18'),
        mutations=('mutate_prose_flow:M43', 'mutate_prose_flow:M44',
                   'mutate_prose_flow:M45', 'mutate_prose_flow:M46',
                   'mutate_prose_flow:M47', 'mutate_prose_flow:M48',
                   'mutate_prose_flow:M49', 'mutate_prose_flow:M50'),
        note='★ 成对的一整排：J2（中间有进场标记 ⇒ 不判）、J3（换幕 ⇒ 不判）、'
             'J4（`（别处）` ⇒ 不判）、J5（心声 ⇒ 不判）、J6（没有名单 ⇒ 不判）、'
             'J17（材料干净时提示词里一个字都不加）。单有 J1 会变成"看到退场就红"。\n'
             '★ J15 第一版写成"源码里含 `离场人物`"，被 M47 当场打绿'
             '（提示词键改名后 `result.get("离场人物")` 还在）—— '
             '已改成"提示词要的键 与 解析读的键 逐字一致"的两侧对照。',
    ),
    Rule(
        id='R37',
        title='沉默只走一条路：否定回应紧跟视线落点，一天最多一次',
        layer='product',
        symptom='「岛村沉默无层次：全段只有「不说话看雪光」和「嗯……」两种反应，'
                '建议用身体语言 / 感知细节 / 回忆联想增加层次。」',
        countable='叙述层（**不含台词**）里「否定回应 + 紧跟一个视线落点」成套句式'
                  '（「没应，看那道门缝雪光」），一天 >= 2 处就报。'
                  '真人 18 章：17 章 0 处、1 章 1 处，**从没有 >=2**；'
                  '真跑 55 份：50 份 0、4 份 1、1 份 2（正是 snow_v11 那个白天）。',
        fix='检测器 `prose_flow.silence_gaze_issues`（纯代码、零成本）记日志；'
            '提示词第 4.8 条给四条替代写法（写手上的动作 / 写别人看见他沉默的样子 / '
            '写他想起的一件事 / 干脆跳过这个反应）；`agents._fix_repeats` 在超出时'
            '让模型换法子重写（给可数的事实「已经 2 次，最多留 1 次」）。',
        wrong='⚠ **只靠提示词 4.8 条** —— 提示词里明写了照样复读（prompt 里写了 ≠ 生效）。'
              '⚠ **按通道判**（身 / 感 / 声分三类计数）—— 岛村那天三种通道都用了，'
              '按通道会漏；可数的是「这个成套句式本身被复用」这件事，不是通道数。',
        landing=('crew/prose_flow.py', 'crew/agents.py'),
        checks=('verify_prose_flow:L1a', 'verify_prose_flow:L2'),
        mutations=('mutate_prose_flow:M51',),
        note='L2 是成对：沉默 1 次（上限内）**不报**，防一刀切也算绿。'
             '这是通用修复：阈值来自真人 18 章对照，不是为雪国定制。',
    ),
    Rule(
        id='R38',
        title='口癖与细节复读，各最多两次：整篇对白累计、不按说话人',
        layer='product',
        symptom='「你这个人哪」4 次、「炭塌了」2 次。建议精简至 2 次。',
        countable='① 台词里同一段 >= 4 字的话，**整篇对白累计、不问说话人**，一天 > 2 次；'
                  '② 旁白里同一「道具 + 状态动词」二元组，一天 >= 3 次。'
                  '真人 18 章：两类 **0 命中**；snow_v11 那个白天：「你这个人哪」4 次。',
        fix='`prose_flow.repeated_tic_issues` / `detail_repeat_issues`（纯代码、零成本）；'
            '提示词第 4.9 条给上限两次 + 替代写法（第三次起换说法 / 让别人替他说完 / '
            '道具状态最多两次、其余让它换个样子出现）；`agents._fix_repeats` 重写。',
        wrong='⚠ **按说话人判口癖** —— 实测从正文归属说话人完全不可靠：'
              '四句「你这个人哪」的说话人被切成「驹子转 / 火钵边 / 炭塌了 / 又说」，'
              '一次都报不出。**整篇累计**才对。'
              '⚠ **把指称类短语当口癖**（「十五年前」一章说 3 次是同一件事）；'
              '⚠ **把道具名字当细节**（真人一章「漏刻」出现 4–8 次正常 —— 那是名词指代，'
              '不是「同一件东西经历同一次变化」）。',
        landing=('crew/prose_flow.py', 'crew/agents.py'),
        checks=('verify_prose_flow:L1b', 'verify_prose_flow:L1c',
                'verify_prose_flow:L3', 'verify_prose_flow:L4'),
        mutations=('mutate_prose_flow:M52', 'mutate_prose_flow:M53'),
        note='L3 成对：口癖整篇累计、不问说话人（不同人各说一次、合计 3 次仍报）；'
             'L4 成对：指称类短语不判。阈值来自真人 18 章对照，通用修复。',
    ),
    Rule(
        id='R39',
        title='配角按模版刷存在感：称呼式台词一天最多 15%',
        layer='product',
        symptom='「叶子从一个"功能性配角"变成了一个"无处不在的干扰源"。她的每一次'
                '出现都在打断岛村和驹子之间的对话，而且打断的方式高度重复'
                '（提醒、送东西、催促休息）……她只是一个不断重复"先生"的复读机。」',
        countable='台词里以「称呼 + 停顿标点」开头（「先生，…」「X姐，…」）的条数，'
                  '超过 `int(总台词 * 0.15)` 就报。'
                  '真人 18 章（samples/zh，6 部作品 × 3 章）：**中位 0%、最大 0%**，一条都没有；'
                  '真跑 snow_v11 19.1%（4/22）、snow_v12 **30.0%（12/41）**。',
        fix='检测器 `prose_flow.vocative_share_issues`（纯代码、零成本）；'
            '作为**第四类**并入 `repeat_issues`（kind=`vocative`），于是'
            '`agents._fix_repeats` 会给可数的事实（"12 条，最多留 6 条"）让模型改写。'
            '上限按**条数**给，好与另外三类共用 `{what, times, cap}` 这一个形状 —— '
            '否则占比 0.15 和条数 12 混在一个字段里，修复提示词说不清"最多留几条"。',
        wrong='⚠ **用"相邻台词共享二元组"判"答非所问"** —— 同一个探针量过：真人问→答的'
              '字面零承接率是 **100%**，泛化相邻台词也有 88%，都比真跑（74%）高。'
              '字面重合判不了语义是不是同一条线（R02），拿它立判据会把真人一起判死。'
              '⚠ **只靠提示词写"配角少说话"** —— prompt 里写了 ≠ 生效（R04）。'
              '⚠ **把称呼前缀写成必须前面还有字**（`{1,4}`）—— 真跑里那九句全是'
              '**以称呼开头**的，这么写一条都抓不到（探针第一版就栽在这里，'
              '把占比量成了 0，差点得出"配角没抢戏"的反向结论）。',
        landing=('crew/prose_flow.py', 'crew/agents.py'),
        checks=('verify_prose_flow:N1a', 'verify_prose_flow:N1b',
                'verify_prose_flow:N2', 'verify_prose_flow:N3',
                'verify_prose_flow:N4'),
        mutations=('mutate_prose_flow:M54', 'mutate_prose_flow:M55'),
        note='N1b 直接读 samples/zh 的 18 章判**零误报** —— 这条红了就是判据在误伤真人，'
             '比抓不到更严重。N2/N3 是成对：正常对话与短文本都不报。'
             '阈值来自真人 18 章对照；检测器里没有任何作品专用词，通用修复。',
    ),
    Rule(
        id='R40',
        title='派活不许只派"不做什么"：每个在场的人至少要有一条肯开口 / 肯动手的事',
        layer='product',
        symptom='雪国 v12 的「今日任务」把岛村派成「要观察驹子而**不轻易回应**」，'
                '于是他通篇只有"是啊""嗯""还没定" —— 读者问"我为什么要关心这个人"。',
        countable='解析后的 `角色任务`（`{人名: [任务, ...]}`）里，某个角色的**每一条**'
                  '任务都是否定型（含 不 / 别 / 沉默 / 忍 …），且**没有任何一条**带'
                  '未被否定的肯定性动词 ⇒ 报。'
                  '⚠ 这是**结构性约束**而非统计阈值（"只被派了不做什么的人不可能有戏"），'
                  '所以**不需要**真人样本定阈值 —— R11 管的是阈值类判据，不是这一类。',
        fix='检测器 `prose_flow.passive_task_roles` / `passive_task_note`（纯代码、零成本），'
            '在 `agents._plotpilot_plan` 解析 `角色任务` 之后**记日志**（这一步只记不改：'
            '改派活要再问一次模型，而这一层已经问过一次了，先让它可见）。'
            '提示词第 4 条补一句"每条都要有他能**做**的事，光写不做什么他就没有戏"。',
        wrong='⚠ **肯定性动词只做子串匹配** —— 实测「不说话」里就有"说"，照子串判它是'
              '肯定动作，"全否定"那一条被放过去了（检测器第一版就栽在这里，该报的没报）。'
              '必须看动词**前两个字符**里有没有否定词（窗口取 2 才挡得住"不要说话"）。'
              '⚠ **把"要 / 做 / 观察"算作肯定动词** —— 每条任务都以"要"开头，'
              '放进去等于给所有任务发通行证，这条判据会永远绿（一条都抓不到）。'
              '⚠ **一刀切** —— "先忍着不说、末了把话挑明"是好派活，只要有任何一条'
              '肯定性动作就不该报，否则会把真正有层次的派活一起判死（P1b 守这条）。'
              '⚠ **在下游改** —— 根因在派活（R21），下游再怎么写也写不出主动性。',
        landing=('crew/prose_flow.py', 'crew/agents.py'),
        checks=('verify_prose_flow:P1a', 'verify_prose_flow:P1b',
                'verify_prose_flow:P2', 'verify_prose_flow:P3',
                'verify_prose_flow:P4', 'verify_prose_flow:P5',
                'verify_prose_flow:P6'),
        mutations=('mutate_prose_flow:M56',),
        note='P2 是被否定动词的成对（"不说话"必须仍算否定）；P1b 是好派活的成对；'
             'P5/P6 是**动词表两头**的成对：位移算肯定动作、万能词不算。'
             '检测器与提示词里都没有作品专用词，通用修复。'
             '⚠ 2026-10-20 修了一个真跑里的**误报**：叶子被派「从廊道走到纸门外'
             '停步不出声惊动屋内」，她明明有事可做却因"走/停"不在动词表里被判成'
             '"只派了不做什么"（v13 日志那条 WARNING 就是它）。'
             '★ 区分标准：万能词（要/做/观察）**每条任务都有**，放进来判据永远绿；'
             '位移与肢体动词**只有真要动起来才有**，放进来不会让它失效。'
             '⚠ 这一条**没能**修好 snow_v12 —— v12 给岛村派的是'
             '「不轻易回应」+「末了给她一句认定」，有肯定动作所以不报；'
             '真正的失败是那个"认定"**下游没执行**（又是 R04 写了≠生效），'
             '那是语义层，纯代码判不了。R40 是**防止再派出纯被动角色**的护栏。',
    ),
    Rule(
        id='R41',
        title='对话没人正面回答：含糊应答（「唔……」+ 不相干的尾巴）一天最多 2 条',
        layer='product',
        symptom='雪国 v13 里岛村一律「唔……这么晚了。」「唔……路上滑吧。」—— '
                '看着像一句人话，其实什么都没答；驹子连问五遍得不到回应。'
                '读者会失去"对话正在推进什么"的理解，最终放弃跟随。',
        countable='台词里以语气词（唔 / 嗯 / 啊 / 哦 …）开头、去掉语气词与尾巴后'
                  '几乎没内容的条数 > `HEDGE_CAP`(2) 就报。'
                  '真人 18 章（samples/zh，6 部作品 × 3 章）：**14 章是 0 条，'
                  '最多的一章也只有 1 条**；真跑 snow_v12 = 3、snow_v13 = **5**。',
        fix='检测器 `prose_flow.hedge_reply_issues`（纯代码、零成本）；'
            '作为**第五类**并入 `repeat_issues`（kind=`hedge`），于是'
            '`agents._fix_repeats` 会给可数的事实（"5 条，最多留 2 条"）让模型改写。'
            '⚠ 与"纯应答"分工：「是啊」整句是应答词（那是口癖检测器的事），'
            '这一类专门抓**带尾巴**的（「唔……路上滑吧。」），纯应答抓不到它们。',
        wrong='⚠ **用占比当基线** —— 真人每章只有 3~44 句台词，5 句里 1 句应答就是'
              '20%，小样本把真人的最大值抬得比真跑还高。探针第一版就是这么得出'
              '"含糊应答无区分度、立不了判据"的**错误结论**的；'
              '改用**绝对条数**后信号立刻干净（真人最大 1 vs 真跑 5）。'
              '⚠ **"追问链"（同一件事被问了 N 遍）** —— 试过，已删，别捡回来：'
              '真跑 v12 上它抓到的 5 条全是叶子那几句「先生，…」（只因共享'
              '「先生」「驹子姐」），跟 vocative 抓的是同一个现象，零新增信息；'
              '而真正的追问（「您就不好奇…吗？」「您还没回答我呢。」）字面'
              '一个二元组都不共享，一条都抓不到（crew/prose_flow.py 里有注释）。'
              '⚠ **判"答非所问"本身** —— 语义层，真人问→答字面零承接率 100%（R02）。'
              '能判的只有它的**结构性后果**（含糊应答），不是错位本身。',
        landing=('crew/prose_flow.py',),
        checks=('verify_prose_flow:Q1a', 'verify_prose_flow:Q1b',
                'verify_prose_flow:Q2', 'verify_prose_flow:Q3',
                'verify_prose_flow:Q4', 'verify_prose_flow:Q5'),
        mutations=('mutate_prose_flow:M57',),
        note='Q1b 直接读 samples/zh 的 18 章判**零误报** —— 这条红了就是判据在误伤真人，'
             '比抓不到更严重。Q2/Q3 是成对：正常对白与短文本都不报。'
             '阈值来自真人 18 章**绝对条数**对照；检测器里没有任何作品专用词，通用修复。'
             '⚠ 这一条**修不好**"答非所问"本身，只能压住它最可数的那一半。',
    ),
    Rule(
        id='R42',
        title='一大段不许塞太多件事：段内最多 7 件（真人 18 章上限）',
        layer='product',
        symptom='真跑 snow_v12 最长一段 638 字、里面塞了 **44 件事**（一句接一句，'
                '中间没有一个分段）；v13 = 12 件、v14 = 19 件。'
                '读者眼里就是一坨流水账，没有换气的地方 —— 这是"读不下去"'
                '**最可数**的一条，也是目前量到的差距最干净的一条。',
        countable='一段里按句号/问号/叹号切出的子句数，最大那段 > `PARA_EVENT_CAP`(7) 就报。'
                  '真人 18 章（samples/zh）：段落最长 125 字、**段内最多 7 件事**，'
                  '**18 章没有一章越界**；真跑 v12=44 / v13=12 / v14=19（1.7~6 倍）。',
        fix='检测器 `prose_flow.crowded_paragraph_issues`（纯代码、零成本）；'
            '修复走**独立的** `crowded_rewrite_prompt` + `agents._fix_crowded`，'
            '接在 `_fix_flat_paragraphs` / `_fix_repeats` 之后，'
            '开关 `PROSE_CROWD_FIX=1`（默认开，设 0 回到只报不修）。'
            '修法是**拆段**不是删事：事实一个字不动，字数不许变少。',
        wrong='⚠ **并入 `repeat_issues`** —— 那边的改写提示词整段都在讲'
              '"同一个写法用了一次又一次"，把"一段太挤"混进去会指错方向'
              '（那边该换法子，这边该分段），所以走独立提示词。'
              '⚠ **判字数而不是段内事件数** —— 一段可以很长但只要在一件事里打转'
              '就不挤（真人最长那段 125 字只有 7 件事）；反过来短短一段塞十件事'
              '同样是流水账。**事件数才是那个可数的东西**。'
              '⚠ **用占比当基线** —— 见 R41 那条：小样本会把真人最大值抬得比真跑还高。'
              '⚠ **拿它去判"答非所问"** —— 那是语义层，真人问→答字面零承接率 100%（R02）。',
        landing=('crew/prose_flow.py', 'crew/agents.py', 'config.py'),
        checks=('verify_prose_flow:S1a', 'verify_prose_flow:S1b',
                'verify_prose_flow:S2', 'verify_prose_flow:S3',
                'verify_prose_flow:S4'),
        mutations=('mutate_prose_flow:M58',),
        note='S1b 直接读 samples/zh 的 18 章判**零误报** —— 这条红了就是判据在误伤真人，'
             '比抓不到更严重。S2/S3 是成对：正常分段与只有一件事都不报。'
             '阈值来自真人 18 章对照；检测器里没有任何作品专用词，通用修复。'
              '★ 这一条**不判语义**，所以是目前最稳的一条 —— 它修的是"排版"不是"文笔"，'
              '但对可读性的影响比前几条加起来都大。',
    ),
    Rule(
        id='R43',
        title='不许在同一个地方打转：判决交 LLM 判官，代码只管住"不许改坏"',
        layer='product',
        symptom='真跑 snow_v16 用户点名两处：**叶子送酒 5 次**（「将酒壶搁在火钵旁」'
                '「端进一壶温酒」「把温酒放火钵边」「壶搁这儿」「酒给您放这了」）和'
                '**驹子把同一件事问了 7 遍**（「好人是不是都没好报」'
                '「什么样的人才算有好报」「我是不是好人」「我到底算不算好人」，'
                '全文"好人"10 次、"好报"8 次）。'
                '读者感受是"她怎么又在送酒""这话题怎么还没过去"。',
        countable='★★ **这一条的判决不在代码里**。四条字面路实测全部零区分度：'
                  '① 动宾紧邻的正则 —— 真人 18 章最大 1 次、真跑也是 1 次；'
                  '② 全文 2-gram 峰值 —— 真人 top 是**角色名**（阿箬 14、沈砚 10）与'
                  '**核心道具**（老河 14、簿子 8），真跑是火钵 13，人是这么写小说的；'
                  '③ 字面零承接 —— 真人 **100%**，比真跑还高（R02）；'
                  '④ 台词 2-gram —— 真人是专有名词（主簿 5），真跑"好人"10，太近。'
                  '⑤ **最长同题链**（2026-10-20 补量）—— 真人中位 2、**最大 4**，'
                  '真跑 v12–v19 全是 1–2 ⇒ 真人的重复比真跑**还多**，这个量反向。'
                  '⇒ 可算的只有**候选在哪**：`repeat_clusters` 用实词骨架 + 并查集'
                  '把"换了说法的同一件事"聚成组（真人 18 章共 22 组，21 组 2 条，'
                  '唯一 1 个 3 条组是"十五年前"的**证据链**，是手法）—— '
                  '组只说明"这几句像是同一件事"，**不说明谁该删**。'
                  '判决仍交给判官；代码能钉的是备料、解析层、删除闸与两个提示词的内容。',
        fix='判官 `prose_flow.spin_judge_prompt` 判定（每幕一次，不设门槛 ——'
            '误报只多花一次调用）；`parse_spin_verdict` 解析；'
            '开关 `PROSE_SPIN_FIX=1`（默认开）。'
            '★★★ **分三步，按"改坏的风险"从小到大**：'
            '① **先删**（2026-10-20 起的主路）：判官按**重复组**表态'
            '（`repeat_clusters` 用实词骨架 + 并查集找出"换了说法的同一件事"，'
            '每组问一句"删掉这一条，读者会损失什么"），代码只删它点的那一条 ——'
            '删是唯一**不会写进新东西**的动作。'
            '② 判官没给组（老格式）⇒ 走 `spin_rewrite_prompt` 整章重写。'
            '③ 重写完**再问一次判官**，还打转就交回原文。'
            '⚠ 删除侧六道闸：整句对得上才删 / 删掉的片段**引号必须配平** / '
            '不许删空一段 / 不许删这一段最后一句 / 单条 >80 字（判官抄的是段落）不收 / '
            '删掉的台词按台词总数 15% 封顶；组内**第一条永远不删**（两条的组例外，'
            '否则一条也删不了 ⇒ 修复链静默失效）。'
            '⚠ 删除后还要复检 R46（删掉一句"答话"会让原本接上的问答变悬空）。',
        wrong='⚠ **自己写一条字面判据去判打转** —— 上面四条实测全废，'
              '硬做只会造出一条**专杀真人**的假判据（真人的 top 永远是人名和道具）。'
              '⚠ **判官提示词只写正例** —— 不写"道具反复出现不算打转"，'
              '判官就会把"火钵 13 次"当打转，改稿时把**舞台**改掉，稿子更空。'
              '⚠ **把"重复"直接当病** —— 用户 2026-10-20 的原话：'
              '「不是所有重复都有问题，要结合上下文语境进行分析」。'
              '真人 18 章里有一章通篇是**回声式对答**（字面重合 100%），'
              '还有一章一个 3 条组反复强调同一个时间点（证据链）—— 都是好写法。'
              '提示词里必须列出这几种正当重复，否则判官见重复就判病（M73 钉这条）。'
              '⚠ **只看"重复了几次"** —— 标准必须是**可删除性**：'
              '删掉这一条，读者会损失什么？说不出具体损失才是病。'
              '⚠ **改完全章重写再复检、还报就整篇退回** —— 这就是 snow_v19 的死法：'
              '判官报 5 条出处 → 整章重写 → 复检还报 → 一小时 1782 秒的成品'
              '一个字没变，"我是不是好人"照样问了 6 次。'
              '**全有或全无 = 什么都没做**。'
              '⚠ **解析层不查否定词** —— 「没打转」里就有"打转"两个字，'
              '只看这两个字会把"判官说没事"读成"有事"，然后去改一篇好稿。'
              '⚠ **看不懂的回话当成打转** —— 这一步回的是"要不要改稿"，'
              '宁可漏改，也绝不能因为解析错把好稿改坏（M60 就是钉这条的）。'
              '⚠ **拿热点词当证据** —— 它只是给判官的**线索**，'
              '提示词里明写了"仅供参考，别当成证据"。',
        landing=('crew/prose_flow.py', 'crew/agents.py', 'config.py'),
        checks=('verify_prose_flow:T1a', 'verify_prose_flow:T1b',
                'verify_prose_flow:T1c', 'verify_prose_flow:T2',
                'verify_prose_flow:T3', 'verify_prose_flow:T4',
                'verify_prose_flow:T4b', 'verify_prose_flow:T4c',
                'verify_prose_flow:T5',
                'verify_prose_flow:X1', 'verify_prose_flow:X2',
                'verify_prose_flow:X3', 'verify_prose_flow:X4',
                'verify_prose_flow:X5', 'verify_prose_flow:X6',
                'verify_prose_flow:X7', 'verify_prose_flow:X8',
                'verify_prose_flow:X9', 'verify_prose_flow:X10',
                'verify_prose_flow:X11', 'verify_prose_flow:X12',
                'verify_prose_flow:X13', 'verify_prose_flow:X14',
                'verify_prose_flow:X15', 'verify_prose_flow:X16'),
        mutations=('mutate_prose_flow:M59', 'mutate_prose_flow:M60',
                   'mutate_prose_flow:M68', 'mutate_prose_flow:M69',
                   'mutate_prose_flow:M70', 'mutate_prose_flow:M71',
                   'mutate_prose_flow:M72', 'mutate_prose_flow:M73'),
        note='★ T1b/T1c/T2 是**安全侧**，比"抓得到"重要得多：产品拿它决定要不要改稿，'
             '改坏一篇好稿比漏改一处打转严重得多 —— M59/M60 两条反例法就是钉这三条的。'
             '★ 判据**不覆盖判官本身**的判断力（那要在线调 LLM，不可离线回归）；'
             '能离线钉住的是聚类、解析层、删除闸、备料与提示词内容，这是诚实的边界。'
             '★ **判官有抖动**：同一份 v19 连跑两次，一次判"打转"、一次判"没打转"'
             '（`temperature=0` 也没完全消除）。抖动方向是**漏修**不是改坏，属安全侧；'
             '但"修不修看运气"这件事必须写在这里，不许假装它稳定。'
             '★★★ **判官的判别力验过**（2026-10-20 三份样本）：'
             '① 合成样本（女方连问 5 遍、男方从头到尾只有"是啊"）⇒ 判**打转**，'
             '并给出"删 2,3"；② `snow_v19` ⇒ 判没打转，理由是"岛村的反应在变'
             '（敷衍、给答案、以酒和雪回避、沉默）"；③ `snow_v20` ⇒ 判没打转，'
             '理由是"茶凉从暗示到明要再到指责、叶子从送酒到欲言又止均有推进"。'
             '⇒ 它区分的是**"对面有没有变化"**，不是"重复了几次" —— 与人的读感一致。'
             '⚠ 提示词曾经把"一个人反复用同一句挡话"列为正当写法，'
             '结果判官拿它当**免罪符**（连上面那个合成样本都判没打转）⇒ '
             '现在补了边界："敷衍只有在**态度有层次**时才算手法"。'
             '检测器与提示词里都没有作品专用词，通用修复。',
    ),
    Rule(
        id='R44',
        title='叙述者不许跳出来讲结构：删掉那半句（我们自己的提示词喂出来的病）',
        layer='product',
        symptom='真跑 snow_v17 用户读完点出来："叶子对岛村，**这回不重复进门送物**，'
                '只站在门边探进半张脸"—— 这是**叙述者在给读者讲自己怎么安排这场戏**，'
                '不是岛村看见的东西。同一版还有「算是第二层的新问」'
                '「把这第三轮收住」「这回只换了个由头」「不再提夜色，只换由头问」，'
                '一共 6 处。'
                '⚠ 这是**我们自己造出来的病**：snow_v12 / v15 / v16 四类信号**全为 0**，'
                'v17 一上打转判官（R43）就冒出来 —— 因为 R43 的修复提示词里写了'
                '"同一件事最多来回三轮""就换个由头"，模型照做，做出来的却是'
                '**把这条要求念给读者听**。',
        countable='句子里的元叙述标记，两种形状：'
                  '① 序数 + 言语行为（「第二轮追问」「第三层的新问」「把这第三轮收住」）—— '
                  '真人 18 章 **0 条**；真跑 v17 **4 条**；'
                  '② 与前文写法对比（「这回不再…」「换了个由头」）—— '
                  '真人 18 章 **0 条**；真跑 v17 **2 条**。（合计 6 条，全部落地剥离。）'
                  '⚠ **光匹配「第N轮/第N遍」不通**：真人 18 章里有 7 条'
                  '（「抄第二遍」「第七遍的时候」），那是叙事里的**事实**；'
                  '配上言语行为词（追问/收住/逼出/新问…）之后才是 0 —— '
                  '判据必须带上下文，只盯一个词会误伤真人。'
                  '⚠ **「不再」单独也不通**：真人里有 5 条（「她没听懂，也没再问」）。',
        fix='检测器 `prose_flow.meta_narration_issues`；'
            '修复是**确定性剥离** `strip_meta_narration`（按从句删除，'
            '不调模型）+ `agents._fix_meta_narration`，排在 `agents._polish` 的**最后一步**，'
            '开关 `PROSE_META_FIX=1`（默认开）。'
            '治本那一层在提示词：所有重写提示词（repeat / crowded / spin / plausibility）'
            '都带上 `_NO_META_CLAUSE`，并且 R43 的修复要求改写成抽象措辞'
            '（"别一直绕""别做第二遍"，不再写"几轮""由头"）。',
        wrong='⚠ **只改提示词就收工** —— 本项目反复实测：prompt 里写了 ≠ 生效。'
              '所以必须配一层确定性剥离（R31 同一条纪律）。'
              '⚠ **让模型重写这一句** —— 元叙述是"多写了一句"，'
              '删除是唯一不会写坏的动作；重写会把已经修好的事实再交出去一遍（R42 的教训）。'
              '⚠ **直接按 `_SENT` 在原文上切句** —— 台词自带句末标点'
              '（「…：\\"我是个好人吧？\\"」里那个 `？`），会把句子从台词中间劈开，'
              '后半句带着半个引号开始 ⇒ 引号配对整体错位，'
              '真正的叙述句被当成台词蒙住（v17 上真的漏了一条）。'
              '必须在**蒙好的版本**上找句末（见 `_narration_spans`）。'
              '⚠ **删掉带台词的那一句** —— 三条护栏缺一条就会把人物的话连锅端。',
        landing=('crew/prose_flow.py', 'crew/agents.py', 'config.py'),
        checks=('verify_prose_flow:U1a', 'verify_prose_flow:U1b',
                'verify_prose_flow:U1d', 'verify_prose_flow:U1c',
                'verify_prose_flow:U2', 'verify_prose_flow:U3',
                'verify_prose_flow:U4', 'verify_prose_flow:U4b',
                'verify_prose_flow:U4c', 'verify_prose_flow:T6'),
        mutations=('mutate_prose_flow:M61', 'mutate_prose_flow:M62'),
        note='U1b 直接读 samples/zh 的 18 章判**零误报**。'
             'U2/U3 是成对：**正常叙事里的序数**（第二次、第三遍）与'
             '**正常的"不再"**（她没听懂，也没再问）都**不许报**。'
             '检测器里没有任何作品专用词，通用修复。'
             '★ 这条规则的价值不在删掉的那几处，在于它把"**提示词里的要求会被模型念给读者听**"'
             '这条教训固定成了可回归的判据 —— 下一次再有人往修复提示词里写结构性要求，'
             '他会先在这一条上撞见后果。',
    ),
    Rule(
        id='R45',
        title='不许前后打架：听不见的话不许被听见（判不了形状的那一半交给判官）',
        layer='product',
        symptom='真跑 snow_v17 用户点出的**头号硬伤**：驹子那句私语被写成'
                '「齿间漏出那点怨毒的私语。她唇几乎没动。只让那几字像叹息般溜出来」，'
                '紧接着却是「叶子**正进门**便听见了」—— 隔着一道纸门的门外人，'
                '听见了唇几乎没动的话。用户的原话："既然是在进门这个动作发生时听到的，'
                '说明她之前不在室内……如何能清晰捕捉到屋内人唇几乎没动的私语？"'
                '同版还有两处：**隔着门写到「睫毛上沾着一点廊下的寒气」**（用户："这更像是'
                '全知视角的描写"）和**物理瑕疵**「壶在灯下晃了晃，釉面流过一道亮痕」'
                '（用户："干燥的釉面自己会流动吗"）。',
        countable='两类有可数形状，第三类没有：'
                  '① 私语 × 听见 —— 写了"几乎听不见"（私语/唇几乎没动/像叹息/气音…）之后，'
                  '6 句之内出现**肯定**的"听见/听清"：真人 18 章 **0 条**、真跑 v17 **1 条**；'
                  '② 微距 × 距离/弱光 —— 同一句里既有"睫毛/瞳仁…"又有"门外/廊下/昏暗…"：'
                  '真人 18 章 **0 条**、真跑 v17 **1 条**；'
                  '③ 物理瑕疵（干燥的釉面自己流过一道亮痕）—— '
                  '**写不出字面判据**：它要的是常识，不是形状。判不出就老实交给判官。'
                  '⚠ ①②的**否定必须先查**：真人第 6 部第 3 章'
                  '「说了三个字，又断在一个收不住的气音上。那三个字他**没听清**」'
                  '—— 那正是作家处理"听不清"的**正确写法**，把它当病就冤了'
                  '（第三次踩"否定词就长在被查的那个词里"这个坑了：'
                  '前有 `parse_spin_verdict` 的「没打转」、后有本条的「没听清」）。',
        fix='触发不设门槛（用户原话"阈值可以低一些"）：正文够长就问判官'
            '`prose_flow.plausibility_judge_prompt`（三类一起问，把"不算"的四条也写进去 —— '
            '不写的话判官会把"雪会化、手会冻红"当成物理不成立）；'
            '`parse_plausibility_verdict` 解析（**看不懂一律当没问题**）；'
            '然后**定点替换**：`plausibility_rewrite_prompt` 只许模型改判官点名的那几句'
            '（`swap_lines` 只在**整句完全对得上**时才替换），**不像 R43 那样整章重写** —— '
            '这类毛病通常只有一两句，整章重写会把前面修好的东西再暴露给模型一遍。'
            '四道闸：毛病不许变多 / 台词不许变少 / 长度 0.9–1.3 倍 / 新句不短于原句 0.6 倍。'
            '开关 `PROSE_PLAUS_FIX=1`（默认开）。',
        wrong='⚠ **给第三类硬编一条字面判据** —— 物理瑕疵要的是常识，'
              '写在代码里就是一条**假的**规则（见了"釉面"就说谎）。'
              '⚠ **把 ①② 扩成一条包打天下的"第三人称有限视角"判据** —— '
              '"岛村能不能看见睫毛"要的是语义与常识，代码只能数到"睫毛"与"门外"'
              '**同时出现**这一层；再往前一步就开始误伤真人（真人确实会在近距离写微距）。'
              '⚠ **不查否定词** —— 见 countable 里那条，会把正确的写法当成病。'
              '⚠ **凭直觉补缺点** —— 这一条里的每一个毛病都必须能写成'
              '`countable` 那一栏里的一个数字，写不进来的就是感想，不是规则。',
        landing=('crew/prose_flow.py', 'crew/agents.py', 'config.py'),
        checks=('verify_prose_flow:V1a', 'verify_prose_flow:V1c',
                'verify_prose_flow:V1b', 'verify_prose_flow:V2',
                'verify_prose_flow:V3', 'verify_prose_flow:V4',
                'verify_prose_flow:V4b', 'verify_prose_flow:V4c',
                'verify_prose_flow:V4d', 'verify_prose_flow:V4e'),
        mutations=('mutate_prose_flow:M63', 'mutate_prose_flow:M64',
                   'mutate_prose_flow:M65'),
        note='V1b 直接读 samples/zh 的 18 章判**零误报**。'
             'V2/V3 是成对：**正常的低声 + 没听清**、**近距离写微距**（没有距离词）都**不许报**。'
             '⚠ 诚实的边界：这一类里**要靠常识的那一半**（物理瑕疵）'
             '没有也不可能有可数判据，能离线钉住的只有检测器、'
             '解析层与四道闸；判官自己判得准不准要在线调 LLM 才知道。'
             '★ 把这一条登记进表的目的，正是**不许有人假装它闭环了**。',
    ),
    Rule(
        id='R46',
        title='对话不许各说各话：连着三句问出去没人接就修一处（"问一句不答"本身不是病）',
        layer='product',
        symptom='真跑 snow_v18 用户读完第二遍，只提了一句：**"为何两个主角说的话'
                '又完全牛头不对马嘴了"**。正文里是五连问：'
                '「你要不要看？」→「这酒还够喝吗」→「你什么时候回去」→'
                '「东京的雪大不大」→「行李收拾好了没有」，两个人各拨各的号码，'
                '谁也没拨通。'
                '⚠ 这一版**其它四项都过了**（R44 元叙述 0、R45 感知自洽 0），'
                '所以它不是"打磨没做到"，是**这一层从来没上过手段**。',
        countable='两把尺子，第一把**必须废掉**才能立第二把：'
                  '① **悬空率**（问了没有直接答的比例）—— 真人 18 章中位 **0.8**、'
                  '最高 **1.0**，比真跑还高（v18 是 0.846）⇒ '
                  '**"问一句不答"本身不是病**，那是留白、是回避、是这场戏的味道；'
                  '② **最长连续悬空** —— 真人的天花板是 **2**，'
                  'v12/v15/v16/v17 是 2/2/2/1，**v18 是 5** ⇒ 阈值取 **≥3**，'
                  '在 18 章真人上**零误报**。'
                  '⚠ 度量必须是**相邻**台词：中间只要有一句真接住了，段就断在那里 —— '
                  '这正是把关的关键（稀释过就不算病）。',
        fix='检测器 `prose_flow.qa_drift_runs`（确定性，**不再设判官**：'
            '已经知道有毛病，再来一轮判官只是多花一次调用）；'
            '`answer_drift_rewrite_prompt` 只许模型**每段改 1 句**（最多 2 句），'
            '且明写"不许把所有问句都改成有问必答"—— 留一处，改多了戏就没了；'
            '`swap_lines` 整句精确替换；`agents._fix_answer_drift` 接在 '
            '`_polish` 的**打转之后、物理自洽之前**；开关 `PROSE_DRIFT_FIX=1`（默认开）。'
            '四道闸：**毛病必须变少**（最长连续要真的降下来）/ 台词不许变少 / '
            '长度 0.9–1.3 倍 / 新句不短于原句 0.6 倍。'
            '**改几句也管**：`best_swap_prefix` 从少到多试前缀，取第一个把最长连续'
            '压到人的天花板（<3）以下的那一档 —— 实测模型一次给 4 句改写，'
            '全用会把每句都改成"半句回答；自己的问题"，四句连排是**新的模版腔**，'
            '用前 2 句又不够，前 3 句刚好。'
            '提示词带 `_NO_META_CLAUSE`（R44 的教训：不写就会被念进正文）。',
        wrong='⚠ **只立悬空率** —— 真人比真跑还高，这条判据会把好小说判成病，'
              '是典型的"尺子用错了还以为有区分度"。'
              '⚠ **修的时候逼成"有问必答"** —— 那会把《雪国》式的沉默与回避抹平，'
              '比原来的毛病更难救；所以提示词里必须**明写**"留一处就够了"。'
              '⚠ **以为 `sim/loop.py::_audit_talk` 已经在管** —— 它每拍都算、'
              '日志里也真的报了五次，但那层的注释写着**只算不拦**。'
              '**看见了不等于处置了；只写日志的护栏等于没有护栏。**'
              '（这一条是本轮最贵的教训，因为日志早就在喊，而没人接。）',
        landing=('crew/prose_flow.py', 'crew/agents.py', 'config.py'),
        checks=('verify_prose_flow:W1', 'verify_prose_flow:W2',
                'verify_prose_flow:W3', 'verify_prose_flow:W4',
                'verify_prose_flow:W4b', 'verify_prose_flow:W5',
                'verify_prose_flow:W6', 'verify_prose_flow:W7',
                'verify_prose_flow:W8', 'verify_prose_flow:W9',
                'verify_prose_flow:W10a', 'verify_prose_flow:W10b',
                'verify_prose_flow:W10c', 'verify_prose_flow:W10d'),
        mutations=('mutate_prose_flow:M66', 'mutate_prose_flow:M67'),
        note='W2 直接读 samples/zh 的 18 章判**零误报**。'
             'W3/W4/W4b/W5 是成对：**单次悬空**（留白）、**真的答了**、'
             '**反问/重复上一句**、**根本没有问句**，这四种都**不许报**。'
             '⚠ 诚实的边界：这条只数得到**形状**（问句后面那句接不接），'
             '数不到"答得对不对"—— 答非所问但共享实词的，它抓不到。'
             '检测器与提示词里没有作品专用词，通用修复。',
    ),
    Rule(
        id='R47',
        title='道具不许循环：同一件东西被反复续上—耗掉就换动作（手在打转，不是话在打转）',
        layer='product',
        symptom='真跑 snow_v20，用户原话：「继续修复道具循环」。正文是：'
                '茶凉了 → 我让人再送一壶 → 茶凉了就说一声 → 叫壶热的来 → '
                '酒还温着再喝一杯 → 杯子空了半天 → 酒壶往火边挪。'
                '⚠ **台词每句都不同、每句都有推进** —— 所以打转判官（R43）'
                '**放过了它，那是对的判断**：R43 数的是"话"，这一条数的是"手"。'
                '读者看到的是"东西又凉了、又续上"，这台戏在原地踏步。',
        countable='**同一件东西的最大复位次数** = 同一类器皿/可消耗物里，'
                  '"被补给"（斟/倒/添/续/换/再送）与"被消耗"（凉了/空了/见底）'
                  '的句子数之和的最大值。'
                  '真人 18 章：中位 **0**、最大 **0**（一次都没有）；'
                  '真跑 v12/v15/v17/v18 = 0，v16/v19/v20 = **4** ⇒ 阈值 ≥3，零误报。'
                  '⚠ 这个数**必须贴着东西**算：句子里要有器皿（壶/杯/碗/炉…）'
                  '或可消耗物（茶/酒/水/炭/纸…），否则真人科幻那一章会判进 '
                  '**11 次**"消耗"—— 全是表格里的「没有」「空着」。'
                  '⚠ 器皿要**归类**（`粗陶酒壶`／`那把壶`／`壶底` 是同一件），'
                  '不归类"同一件东西被反复复位"永远数不出来（实测恒为 0）。',
        fix='检测器 `prose_flow.prop_cycle_issues`（确定性，不设判官）；'
            '`prop_cycle_rewrite_prompt` 只许模型改**每件东西中间那 1–2 句**'
            '（首尾不动：第一次用它和收束）；`swap_lines` 整句精确替换；'
            '`agents._fix_prop_cycle` 接在多轮检查的**第 3 步**；'
            '开关 `PROSE_PROP_FIX=1`（默认开）。'
            '四道闸：毛病变少 / 台词不许变少 / 长度 0.9–1.3 倍 / 新句不短于原句。'
            '★ **不删戏，只换动作**，并明写"不许换成同族动作"（又喝了/又添了/又换了）。',
        wrong='⚠ **拿"道具出现得多"当判据** —— 火钵出现 13 次是真人的正常写法'
              '（那是舞台，不是动作），所以关键词只认"补给/消耗"的**动词**。'
              '⚠ **消耗信号不锚定到东西** —— 见 countable 里那条 11 次误报。'
              '⚠ **按标点切句** —— 台词里的 `。` 会把一句台词劈成两半，'
              '"又凉了"那一半没有东西名 ⇒ 类别为空 ⇒ 检测恒为 0'
              '（实测：六句清清楚楚的循环，一段都报不出来）。'
              '必须**按行切、行内再在蒙好引号的版本上切句末**'
              '（整篇蒙引号会把整章并成一段，那是第二版踩的坑）。'
              '⚠ **删掉那些句子** —— 它们承载的是"她一直在伺候他"这层关系，'
              '删了这场戏就剩两个人干坐着。只换手上的事。',
        landing=('crew/prose_flow.py', 'crew/agents.py', 'config.py'),
        checks=('verify_prose_flow:Y1', 'verify_prose_flow:Y2',
                'verify_prose_flow:Y3', 'verify_prose_flow:Y4',
                'verify_prose_flow:Y5', 'verify_prose_flow:Y6',
                'verify_prose_flow:Y7', 'verify_prose_flow:Y8'),
        mutations=('mutate_prose_flow:M74', 'mutate_prose_flow:M75',
                   'mutate_prose_flow:M76'),
        note='Y3/Y4 是**成对**的安全侧：道具只是被提到不算循环、'
             '"没有/空着"单独不算消耗 —— 这两条比"抓得到"重要，'
             '因为它们的误报会去改一篇正常的稿子。'
             '词表全是通用词，没有作品专用词。',
    ),
    Rule(
        id='R48',
        title='两个关口各查几轮：一开始写小说、最后导出（改完必须复查）',
        layer='product',
        symptom='用户原话：「我希望一开始写小说和最后导出的时候都可以进行几轮的问题检查'
                '也修复，把常见的问题都修复掉」。'
                '此前是**一轮串行跑完就走**：七个修复各跑一次，**改完从不复查**。'
                '后果实测得到：'
                '① 修 A 把 B 弄坏了没人管（删一句答话 ⇒ R46 变悬空；'
                '整章重写 ⇒ 又添一句元叙述）；'
                '② 一轮修不好的没人再试（snow_v19 的六次追问就是这么留下来的，'
                '打转修复报了 5 条出处，复检还报，整篇退回原文）。',
        countable='**每一次检查后还剩多少处毛病**（按类分开数）：'
                  '平铺段 / 重复 / 拥挤段 / 元叙述 / 感知自洽 / 问答悬空 / 道具循环。'
                  '这七类**全部是确定性检测器**，可以随时重算，不花钱。'
                  '⚠ **判官类（打转 / 自洽）故意不进这个数**：它们每判一次要花一次调用，'
                  '而且自己会抖动（同一份稿子连跑两次结论相反）—— '
                  '拿它们当收敛判据，循环会被噪声带着跑。这是有意的取舍。',
        fix='`Novelist._checkup`（写小说时）与模块级 `agents.prose_checkup`'
            '（导出关口）跑的是**同一份实现**：'
            '每轮把"删 → 改内容 → 排版 → 元叙述剥离"走一遍；'
            '⚠ **从第 2 轮起只跑还有指望的那几步**（`_steps_to_run`）：'
            '某一类已经清到 0 ⇒ 跳过它；某一类上一轮被它改**多**了 ⇒ 也跳过。'
            '不跳的话会**越改越差**：`_fix_flat_paragraphs` 第 2 轮看到的是'
            '**它自己上一轮重写的结果**，于是把刚写好的段又判成"平铺"再改一次 ——'
            '实测 `平铺段 2 → 3 → 6`。'
            '★ 还要**保留总数最小的那一版**（某一轮可能修好两处、同时把另一类改差）。'
            '然后**重新数一遍**；两条止损：'
            '① **连续几轮没变少才停**（`PROSE_CHECK_PATIENCE`，默认 2）——'
            '一轮没进展可能只是模型抖动，同一句下一轮换个说法就通了，'
            '所以给它一次喘息再判死刑（作者 2026-10-20：「成本可以接受 以质量优先」）；'
            '② **轮数封顶**（`PROSE_CHECK_ROUNDS`，默认 **5**，设 1 = 退回老样子）。'
            '导出关口 `export.novel_version.checkup_before_bind` 逐天复查后'
            '把结果作为"最终改写稿"装订（开关 `EXPORT_FINAL_CHECK`，默认开）。'
            '★ 一轮内部的顺序就是"改坏风险从小到大"：'
            '先删（打转逐条删、元叙述剥离）→ 再改内容（答非所问/道具循环/自洽）'
            '→ 最后排版（平铺/拥挤）；`_fix_meta_narration` 永远在最后。',
        wrong='⚠ **导出关口连「原始稿」一起改** —— `write_raw_manuscript` '
              '是"一字未改"的凭据稿，它存在的全部价值就是原样；改它等于毁掉凭据。'
              '只许改"最终改写稿"这一档。'
              '⚠ **不切文件头就交给检查** —— 整理稿开头是 `# 当天故事` + 引用块，'
              '那是**版式**；交给"合并平铺段"会把它并进正文，'
              '实测一轮下来 `# 当天故事` 整行消失（Y16b / M81 钉这条）。'
              '⚠ **只交最后一轮的结果** —— 某一轮可能修好两处、同时把另一类改差'
              '（实测 v20：平铺段 2 → 3）；必须保留**总数最小**的那一版（Y15b / M80）。'
              '⚠ **把判官类算进收敛判据** —— 判官抖动会让循环白跑（见 countable）。'
              '⚠ **只加轮数不加止损** —— 改不动了还一轮一轮跑，是纯烧钱。'
              '⚠ **导出关口另写一份规则** —— "同一件事两处实现"是万恶之源；'
              '它必须调 `crew.agents.prose_checkup`。'
              '⚠ **复查失败就中断导出** —— 复查只是锦上添花，'
              '拿原文照常装订才是底线。',
        landing=('crew/agents.py', 'crew/prose_flow.py', 'export/bundle.py',
                 'export/novel_version.py', 'config.py'),
        checks=('verify_prose_flow:Y9', 'verify_prose_flow:Y10',
                'verify_prose_flow:Y11', 'verify_prose_flow:Y12',
                'verify_prose_flow:Y13', 'verify_prose_flow:Y14',
                'verify_prose_flow:Y15', 'verify_prose_flow:Y15b',
                'verify_prose_flow:Y15c', 'verify_prose_flow:Y15d',
                'verify_prose_flow:Y16', 'verify_prose_flow:Y16b',
                'verify_prose_flow:Y16c', 'verify_prose_flow:Y17',
                'verify_prose_flow:Y18', 'verify_prose_flow:Y19',
                'verify_prose_flow:Y20', 'verify_prose_flow:W8'),
        mutations=('mutate_prose_flow:M77', 'mutate_prose_flow:M78',
                   'mutate_prose_flow:M79', 'mutate_prose_flow:M80',
                   'mutate_prose_flow:M81'),
        note='★ Y18 钉的是一条**前提**而不是行为：`_fix_*` 必须全部无状态，'
             '因为导出关口靠 `Novelist.__new__` 跳过构造来复用它们。'
             '谁将来在里面加一个实例属性，这条判据会立刻变红 —— '
             '这正是"把隐含前提写成判据"该有的样子。'
             '★ Y16 判的是**调用图**而不是"源码里有没有这个字符串"：'
             '`checkup_before_bind` 的 docstring 里就写着「原文一字不动」，'
             '按字符串判会永远假红（第一版就是这样）。'
             '★ 诚实的边界：轮数上限是成本与收益的折中（3 轮实测够用），'
             '不是"清了就一定好"的保证；判官类的收敛仍然要看在线模型。',
    ),
    Rule(
        id='R49',
        title='「一句一件事」的可数形态是**句子没有分句**（这个口径我量错过两次）',
        layer='product',
        symptom='2026-10-20 多轮检查上线后实测：`snow_v21` 报「平铺段 2 处」，'
                '重写之后变成 3 处，再一轮变成 6 处 —— **越改越差**。'
                '读那两段原文，写得不错（有动作、有细节、有对话），不该动。',
        countable='段内「**逗号数 / 句子数**」（台词不计）。'
                  '真人 18 章 60 个叙述段：最小 **0.25** / 5% 分位 0.67 / 中位 **1.00**；'
                  '真跑 v23 有两段是 **0.06、0.1**，v22 一段 0.17，v19 一段 0.23。'
                  '⇒ 阈值 **0.2**（比真人下限再留 20% 余量）：只抓明显的"一句一件事"，'
                  '**真人 18 章命中 0 段**。'
                  '⚠ 真人那种「三年前二月，宣阳坊。」的枚举段是 1.0，抓不到 —— 那是对的。',
        
        fix='`prose_flow.long_span_issues` 挑「太长」、`flat_span_issues` 挑「太碎」；'
            '⚠ 另一步**确定性**的：`normalize_quotes` 把成对的英文引号换成中文引号'
            '（`snow_v24` 整篇 24 个 `"`、0 个 `“”`，而 `_QUOTED` 两种都认 ⇒ '
            '所有检测器都照常工作，没人发现）。'
            '只处理**一行内偶数个**的情况，奇数个原样不动，幂等。'
            '`agents._fix_flat_paragraphs` 改用它决定重写哪几段；'
            '计数表里那一类从 `平铺段` 改名为 `憋气段`（只数太长）。'
            '「太碎」不再触发任何自动修复。'
            '⚠ 同时补了一道漏掉的闸：**重写不许把台词并掉**'
            '（R45/R46/R47 都有，唯独这一步没有 —— 实测在 v21 上丢过两句真台词，26 → 23）。',
        wrong='★★★ **先说这一条自己的历史：我量错过两次。**\n'
              '**第一次**：判"整段有没有 ≥25 字的句子"（`list_like_spans` 的太平那一路）。'
              '真人 18 章该指标 **中位 3 / 最大 9**、真跑 v21 是 **0** —— '
              '真人比真跑还"平"，这个口径**根本分不开**；拿它改稿只会打健康段落'
              '（实测 2→3→6 越改越差）。'
              '**第二次**：于是矫枉过正地宣布"太碎不是病"、干脆不修了。'
              '可 v23 那种「岛村倚着窗框。驹子坐在火钵旁。炭火映着她半边脸颊。」'
              '读起来明明白白是病。'
              '**真正的区分点**：不是"句子多长"，是"**句子有没有分句**"。'
              '真人再碎的段落也保持 逗号/句 ≥0.25（「三年前二月，宣阳坊。」是 1.0），'
              '而病段落是光秃秃的主谓宾（0.06）。\n'
              '⚠ **修完把病换到另一头** —— 修"太碎"之后憋气段 0→2：'
              '提示词只写了"长短掺着来"，模型写成 2 长 1 短就判中"长句过半"。'
              '两个方向都必须明写"**长句只留一句**"。'
              '⚠ **台词里的句号被当成空格** —— 这比"太平"更隐蔽：`_strip_quotes` '
              '把一句台词连里面的 `。` 一起蒙掉，于是这种极常见的写法整段并成一句：'
              '`他翻书：“书名忘了。”门外叶子声音清亮：“您真要待十天吗？”……`'
              '蒙完中间一个句末都没有 ⇒ 61 字 / 85 字的"长句"就是这么来的，'
              '而它其实是**多人对话连排**，读者一点不憋气。'
              '⇒ 台词收尾本身就是句子边界，蒙的时候要在收尾处留一个句末标记。'
              '实测：真人 18 章「太长」中位 0 / 最大 1 **改前改后完全一样**（零误伤），'
              '真跑 v19 4→1、v21 2→0、v22 2→0。'
              '⚠ **重写之后只查台词、不查"感知"** —— 为了把长句拆短，'
              '模型会写出「隔着纸门看清睫毛上的雪」这种句子（多轮计数表报出'
              '`感知自洽 0 → 1` 就是这么来的）。这一步只该改**句子长短**，'
              '没有资格改动"谁能看见什么"。'
              '⚠ **把"重复""太平""短句多"当成病** —— 这一类错误的共同形状是：'
              '**没有先量真人**。真人在这些维度上往往比真跑**更极端**：'
              '· 重复：真人最长同题链 4，真跑 1–2（R43）；'
              '· 太平：真人中位 3 / 最大 9，真跑 0（本条）。'
              '⇒ 凡是要判"多不多"的规则，必须先在同一批真人样本上量出分布；'
              '量出来真人更高的，就不是病。'
              '⚠ **重写之后不复检"它是不是更差了"** —— 这条 bug 是靠多轮检查'
              '（R48）的计数表暴露出来的：一轮 3 处、下一轮 6 处。'
              '没有那个计数表，这个修复会一直"看起来很努力"。',
        landing=('crew/prose_flow.py', 'crew/agents.py'),
        checks=('verify_prose_flow:Y9b', 'verify_prose_flow:Y21',
                'verify_prose_flow:Y25', 'verify_prose_flow:Y25b',
                'verify_prose_flow:Y25c', 'verify_prose_flow:Y25d',
                'verify_prose_flow:Y22', 'verify_prose_flow:Y23',
                'verify_prose_flow:Y9c', 'verify_prose_flow:Y24',
                'verify_prose_flow:Y9d', 'verify_prose_flow:Y9e',
                'verify_prose_flow:H1', 'verify_prose_flow:H2',
                'verify_prose_flow:H8', 'verify_prose_flow:H9',
                'verify_prose_flow:H9b'),
        mutations=('mutate_prose_flow:M83', 'mutate_prose_flow:M84',
                   'mutate_prose_flow:M85', 'mutate_prose_flow:M86',
                   'mutate_prose_flow:M88', 'mutate_prose_flow:M89',
                   'mutate_prose_flow:M90', 'mutate_prose_flow:M91',
                   'mutate_prose_flow:M92', 'mutate_prose_flow:M93',
                   'mutate_prose_flow:M94', 'mutate_prose_flow:M95'),
        note='★ 这一条记的不是"新功能"，而是**一条判据被推翻**：'
             '`list_like_spans` 判"整段没有一句铺开"，当初确实抓到了用户点名的碎句'
             '（`他伸手，指尖碰了碰她耳后的皮肤，凉的。`），'
             '但那个毛病**已经被别的步骤治好了**（并段 + 提示词 + 切句），'
             '判据却留着继续开火 —— 于是它开始打健康的段落。'
             '**判据要有保质期**：症状消失了，判据就该退场或降级，'
             '不然它会自己制造新毛病。'
             '★ 词表与阈值全部来自真人基线，没有作品专用词。',
    ),
    Rule(
        id='R50',
        title='导出关口要检查**真正会被装订的那一份**（剧本不是小说）',
        layer='product',
        symptom='2026-10-20：导出关口的日志一直是「重复 2→2」，两轮都改不动。'
                '查下去发现量错了对象 —— `read_day` 读的是 `每天的生活/第N天.md`，'
                '那是**剧本呈现层**（场景标记、动作标注、旁白，另一种文体）；'
                '实测同一跑：剧本上 2 处"重复"、整理稿上 **0 处** —— '
                '那两个"重复"是剧本格式的固有特征，当然修不动。'
                '⚠ 更要命的是当时没暴露的那半边：`day_bodies` 会**完全替换**正文，'
                '所以只要它真改了，就会把**剧本**装订进「最终改写稿」。'
                '没出事只是因为那些改动全被闸拦下了。',
        countable='两份文本各自的毛病数（同一跑、同一天）：'
                  '`read_day` 的剧本 vs `_day_novel_of` 的整理稿。'
                  '实测 `snow_v22`：剧本 2 处重复 / 整理稿 0 处 ⇒ 差值不是噪声，是文体。'
                  '⇒ 可数的是**装订路径**：`render_manuscript` 在 `day_bodies` 有这一天时'
                  '直接用它、否则走 `_tidy_for_novel(body)` + `_day_novel_of`。'
                  '关口必须走**同一条路**，否则量的和装的是两份东西。',
        fix='`checkup_before_bind` 先取 `_day_novel_of(run, day)`（整理稿），'
            '取不到才退回 `_tidy_for_novel(body)`（剧本）—— 与 `render_manuscript` 完全一致；'
            '检查的就是这一份，改完作为 `day_bodies[day]` 传回去。'
            '判据钉两件事：① 代码里**真的调用** `_day_novel_of`；'
            '② 它是 `src` 的**主赋值**、`_tidy_for_novel` 只是行号更大的兜底。',
        wrong='⚠ **在剧本上量小说毛病** —— 剧本有场景标记与动作标注，'
              '重复/拥挤这些指标在它上面没有意义。'
              '⚠ **改了剧本却当成小说正文传回去** —— `day_bodies` 是**替换**语义，'
              '不是"补丁"：传错就把剧本装订进最终改写稿。'
              '⚠ **判据写成恒真** —— 第一版写的是 `ok(..., "__src_ok__" or True, "")`，'
              '永远绿，等于没判（发现后改成查语法树里的 `src = _day_novel_of(...)` 赋值）。',
        landing=('export/novel_version.py',),
        checks=('verify_prose_flow:Y16d', 'verify_prose_flow:Y16e',
                'verify_prose_flow:Y16b', 'verify_prose_flow:Y16c'),
        mutations=('mutate_prose_flow:M87', 'mutate_prose_flow:M81'),
        note='★ 这一条与 R48 是**同一条链上的两半**：R48 管"查几轮"，'
             'R50 管"查的是哪一份"。链上任何一半错了，另一半的努力都白费 —— '
             'R48 那两轮检查在剧本上跑得很认真，但量的是另一份文本。'
             '★ Y16e 的教训值得单记：**判据写成恒真**是最难发现的假绿，'
             '它不会红、不会报错、也不会有人怀疑。',
    ),
    Rule(
        id='R51',
        title='bench 与产品侧是**两处实现、同一个定义**：靠对账判据盯着，不靠自觉',
        layer='product',
        symptom='2026-10-20 晚：主程序这一轮修好了四类毛病（道具循环 / 太碎 / 太长 / '
                '引号混用），可 `novel_bench` 一个都量不出来 —— 它是另一套指标。'
                '于是同一份稿子，产品侧判据说"修掉了"、bench 报告说"和以前一样"。'
                '两边都是真的，因为它们量的不是同一件事。',
        countable='**两边的数字在同一批文本上是否相等**：'
                  '真人 18 章 + 7 版真跑，逐篇比 `prop_cycle` / `flat_spans` / '
                  '`long_spans` 的结论与段数；再比 6 个阈值常量与 2 张词表是否一字节不差。'
                  '当前 18 条全绿（`tools/verify_bench_parity.py`）。',
        fix='`novel_bench/bench/metrics.py` 新增四个计数（道具循环 / 太碎段 / 憋气段 / '
            '引号混用），每个常量都**注明对齐 `crew/prose_flow.py` 的哪个常量**；'
            '`tools/verify_bench_parity.py` 自动对账：'
            '阈值不一致、词表不一致、逐篇结论不一致、真人身上有命中 —— 四条任一触发就红。'
            '**不合并实现**（bench 的独立性是有意的：它不 import `crew/`，'
            '否则会被推演侧依赖拖住），但对账必须自动。',
        wrong='⚠ **"两处实现所以必然会漂，算了"** —— 漂的代价是两份报告互相矛盾，'
              '而人只会相信自己先看到的那一份。'
              '⚠ **为了统一就 merge 成一份** —— bench 的价值就是"主程序之外的第二把尺子"，'
              '共用代码会让它跟着产品侧一起错。对账 > 合并。'
              '⚠ **对账只比阈值、不比结论** —— 阈值一样而切句方式不同，'
              '结论照样分叉（本轮就撞到了：`SENT_SPLIT` 是分隔符正则，'
              '误用 `finditer` 导致 bench 一句都切不出来、道具循环恒为 0）。'
              '⚠ **拿旧 `metrics.json` 跟新跑对比** —— 旧文件缺字段，'
              '`compare` 会把"没有这个指标"读成"没有这个毛病"，看着像变好了。',
        landing=('novel_bench/bench/metrics.py', 'novel_bench/bench/report.py',
                 'tools/verify_bench_parity.py', 'novel_bench/USAGE.md'),
        checks=('verify_bench_parity:P1', 'verify_bench_parity:P2',
                'verify_bench_parity:P3', 'verify_bench_parity:P4',
                'verify_bench_parity:P5', 'verify_bench_parity:P6',
                'verify_bench_parity:P7', 'verify_bench_parity:P8',
                'verify_bench_parity:P9', 'verify_bench_parity:P10',
                'verify_bench_parity:P11', 'verify_bench_parity:P12',
                'verify_bench_parity:P13'),
        mutations=('mutate_bench_parity:M1', 'mutate_bench_parity:M2',
                   'mutate_bench_parity:M3', 'mutate_bench_parity:M4',
                   'mutate_bench_parity:M5', 'mutate_bench_parity:M6'),
        note='★ 这条规则是 `process` 层：它管的不是"稿子写得好不好"，'
             '而是"两把尺子会不会吵起来"。'
             '★ P9/P10 是最要紧的两条 —— 它们钉的是"**真人身上必须零命中**"，'
             '因为这两条判据初版都差点变成专杀真人的假判据（见 R49）。'
             '★ 本轮实测最有说服力的一次对账：bench 一开始把 v19 的道具循环量成 3、'
             '产品侧是 4 —— 差距逼出了 `SENT_SPLIT.finditer` 那个 bug。'
             '如果只看"有没有报"，两边都"报了"，就永远发现不了。',
    ),
    Rule(
        id='R52',
        title='**判定权交给确定性验收层**：LLM 只负责写，不负责判自己写得好不好',
        layer='product',
        symptom='2026-10-20：这一年反复出现的三类毛病，根子是同一个 —— '
                '让"写稿的那一方"同时当裁判。'
                '① 修完"太碎"变成"太长"（实测 0→2）：提示词里加"长句最多一句"也没用，'
                '因为仍是模型自己判；'
                '② 某一轮修好两处、把第三类改多（平铺 2→3→6）：每一步自己判自己，'
                '跨类退化**没有任何一处能看见**；'
                '③ 同分时保留原文、把整轮修改丢掉：`if after < best` 没有 tie-break，'
                '等于"什么都没做"。'
                '公开研究把这条路走完了：在闭环优化里 LLM 判官会偏向自己的输出'
                '（rubric 明确时，误判自己合格的概率比判别人高 50%），'
                '在分布外输入上退化到接近抛硬币 —— **可争辩的判定，优化压力一定找得到缝**。',
        countable='多目标向量（每类毛病分开数 + 汉字数 + 台词数 + 句数），'
                  '不是求和；'
                  '三条硬约束：台词不许变少 / 字数 0.85~1.45 / 句数不许暴涨 1.8 倍；'
                  'canary：毛病清零且字数掉 9% 以上 ⇒ 判"删达标"；'
                  '帕累托：**任一类变多就退回**（单类退化 ≤1 才允许降级成候选）；'
                  'archive 三级排序（加权 → 台词 → 字数），同分时**先改好的那版不被丢掉**。',
        fix='`crew/verdict.py`（`Score` / `compare_scores` / `Decision` / `better`）'
            '负责判定；`crew/reflexion.py`（`reflect` / `Memory` / `Lesson`）负责'
            '「试 → 验 → 写教训 → 再试」；`crew/repair_recipes.py` 是步骤的唯一登记处。'
            '`Novelist._checkup` 只做分发（`PROSE_REFLEXION=0` 逐字回到 `_checkup_legacy`）。',
        wrong='① 只把提示词收紧（"长句最多一句"）—— 判官还是模型自己，病一定换到另一头；'
              '② 只加"保留总数最小的一版"—— 单标量把"两类互换"看成没变化，'
              '而且同分时仍会丢整轮；'
              '③ 用 LLM 当验收方（"你判断一下这稿子有没有变好"）—— 它会偏自己、会抖，'
              '拿它当收敛判据等于让循环跟着噪声跑；'
              '④ 把"重复"直接当病 —— 真人比真跑重复得更多（最长同题链人中位 2 / 最大 4，'
              '真跑全 1–2），标准是**可删除性**，那是语义判断。',
        landing=('crew/verdict.py', 'crew/reflexion.py', 'crew/repair_recipes.py',
                 'crew/global_checks.py', 'crew/critic.py', 'crew/agents.py',
                 'crew/prose_flow.py', 'export/novel_version.py'),
        evidence=('developers/probe_checkup.py',),
        checks=('verify_reflexion:A1', 'verify_reflexion:A2', 'verify_reflexion:A3',
                'verify_reflexion:A4', 'verify_reflexion:A5', 'verify_reflexion:A7',
                'verify_reflexion:A8', 'verify_reflexion:A9',
                'verify_reflexion:B1', 'verify_reflexion:B2', 'verify_reflexion:B3',
                'verify_reflexion:B3b', 'verify_reflexion:B6', 'verify_reflexion:B8',
                'verify_reflexion:C1', 'verify_reflexion:C2', 'verify_reflexion:C3',
                'verify_reflexion:C5', 'verify_reflexion:C5c', 'verify_reflexion:C6',
                'verify_reflexion:C7', 'verify_reflexion:E1', 'verify_reflexion:E2',
                'verify_reflexion:E4', 'verify_reflexion:E5', 'verify_reflexion:E6',
                'verify_reflexion:E7'),
        mutations=('mutate_reflexion:M1', 'mutate_reflexion:M2', 'mutate_reflexion:M3',
                   'mutate_reflexion:M4', 'mutate_reflexion:M5', 'mutate_reflexion:M7',
                   'mutate_reflexion:M8', 'mutate_reflexion:M9', 'mutate_reflexion:M10',
                   'mutate_reflexion:M11', 'mutate_reflexion:M14',
                   'mutate_reflexion:M15'),
        note='★ 四条设计纪律，改之前先读：'
             '① **验收层只认可数的东西**，语义好坏交给顾问（`verbalize` 只有一票建议权）；'
             '② **每步的候选数按 kind 定**（确定性剥离给 1，改写给 2）—— 候选是线性花钱的；'
             '③ **教训库有界**（`PROSE_REFLECT_MEMORY`，默认 24）并按类别去重，'
             '否则记忆会把上下文吃光；'
             '④ **止损三条**：轮数上限 / 连续无改善 patience / 每步都跳过就停。'
             '★ 加一类新毛病 = 在 `repair_recipes` 登记一行 + 在 `prose_issue_count` 数它，'
             '**不改 `_checkup` 的流程** —— C2/C3 会盯着"有没有漏掉某一类"。'
             '★ canary 的阈值（0.90）**必须比硬约束（0.85）宽**，否则它永远不独立触发，'
             '成了死代码（反例法 M3 当场照出来）。',
    ),
    Rule(
        id='R53',
        title='导出关口要有**全书级反思**：跨句/跨天的毛病，单章指标一条都看不见',
        layer='product',
        symptom='2026-10-20：四篇真跑（红楼梦 / 边城 / 诛仙 / 望江楼）逐篇读过，'
                '肉眼能看见三类毛病，而**八项指标全是 0**：'
                '反复问"缺什么"、反复答"够使"（问法每次不同、答法不变）；'
                '碧瑶 5 次"跟我走"、张小凡 3 次"我跟你走"；'
                '那只鸭子被提来推去 7 次。'
                '共同点：**它们都是跨句、跨段、跨天**才成形的，'
                '而原来的检测器都在单句/单段粒度上量。',
        countable='台词里 3~6 字片段的频次（≥4 次且跨 ≥4 句不同台词）；'
                  '量词短语指称的物件在"递/推/提/放"上下文里出现 ≥4 次；'
                  '同一条 ≥6 字台词在 ≥2 天里逐字一样。'
                  '⚠ 阈值**先用真人样本校准**：`ECHO_MIN=4` 时真人 54 篇零命中。',
        fix='`crew/global_checks.py`（`echo_phrase` / `prop_churn` / `cross_day_echo` / '
            '`audit_book`）出候选；`export/novel_version.py::_reflect_whole_book` '
            '把候选当反思提示、定向重写、过验收层、写 `导出/反思记录.md`。',
        wrong='① 把命中数当"毛病数" —— 真人 18 章在门槛 3 上命中 5 处，'
              '全是"崇仁坊""十五年前""这段堤"这类**正常写法**；'
              '② 只按"给予动词紧邻宾语"抓道具 —— 中文的"把"字句让宾语跑到动词前面'
              '（"把鸭子放她脚边"），紧邻写法漏掉一半（实测边城漏了）；'
              '③ 捕获组写 `{1,3}` —— 把谓语一起吃进去（"这两只鸭子肥"抓成"鸭子肥"），'
              '同一物件被拆成十几个"不同名词"，计数永远到不了门槛。',
        landing=('crew/global_checks.py', 'export/novel_version.py'),
        evidence=(),
        checks=('verify_reflexion:D1', 'verify_reflexion:D2', 'verify_reflexion:D3',
                'verify_reflexion:D4', 'verify_reflexion:D5', 'verify_reflexion:D6',
                'verify_reflexion:D7', 'verify_reflexion:D8', 'verify_reflexion:D9'),
        mutations=('mutate_reflexion:M12', 'mutate_reflexion:M13'),
        note='★ 这一层**故意不产出毛病数**，也不进 `verdict.RUBRIC` 与 '
             '`prose_issue_count`（D7 钉着）。判"重复"不能直接当病 —— '
             '标准是可删除性，代码只负责圈出候选、给出可回查的原句。'
             '★ 定向重写必须过验收层：最坏情况是"什么都没改"，'
             '永远不会为了让候选消失而把稿子改差。',
    ),
    Rule(
        id='R54',
        title='**可数 ≠ 该自动改**：「概述句代替场景」只进候选，不进修复链',
        layer='product',
        symptom='2026-10-20 读 `snow_v25` 成品时肉眼发现一句：'
                '「忽然对岛村吐露自己长年记日记的私密习惯，说些只有纸笔知道的琐碎。」'
                '—— 前后全是具体动作与台词，中间插一句总结：读者**被告知**有这件事，'
                '却没有看到它发生（telling 代替 showing）。八项指标全 0，没人管它。',
        countable='叙述动词（吐露/说起/交代/诉说…）+ 抽象宾语（习惯/琐碎/心事/往事…），'
                  '且**该句没有台词**；另加一条"说些/做些 + 一长串"的松散形态'
                  '（宾语被定语从句挡在后面时纯词表抓不到）。'
                  '实测：真人 54 篇命中 **0**，`snow_v25` 精准命中那 1 句。',
        fix='**只检测、不修**。`crew/global_checks.telling_sentences` 出候选，'
            '进导出的 `导出/反思记录.md`，由作者与顾问看。',
        wrong='① 想自动修：修它必须**写出她具体说了什么**，那是新增内容 ⇒ '
              '违反"事实一个字不许改"的硬约束，机器会编造日记内容；'
              '② 把「什么/这些/事情」放进抽象宾语表 —— 它们在任何中文叙述里满地都是，'
              '真人样本立刻被顶红（实测加"什么"时命中「商量什么事」，那明明是具体动作）。',
        landing=('crew/global_checks.py',),
        evidence=(),
        checks=('verify_reflexion:D10', 'verify_reflexion:D10b',
                'verify_reflexion:D10c', 'verify_reflexion:D10d',
                'verify_reflexion:D2b'),
        mutations=('mutate_reflexion:M16', 'mutate_reflexion:M17',
                   'mutate_reflexion:M18'),
        note='★ 这条规则的价值不只在检测，而在它**示范了边界**：'
             '**可数 ≠ 该自动改**。它故意留在 `prose_issue_count` 之外 —— '
             '一旦进去就会被 Reflexion 的步骤链抓走，机器就开始编造情节了。'
             'D10c / D10d 两条判据钉的就是这个"不许它进链"。'
             '★ 样本只有 1 处，所以**没有**去动提示词（一句话方向归提示词，'
             '但一条证据不足以立规矩）。等它再出现几次，再考虑加提示词约束。',
    ),
    Rule(
        id='R55',
        title='**称谓 + 指代不是"台词回声"**：词表漏掉一类称谓，全篇会假阳性',
        layer='product',
        symptom='2026-10-20 四篇横向对比时发现：望江楼那篇报「台词回声 ×6：掌柜这」。'
                '读台词才发现 —— 那是「掌柜，这白灯笼…」「掌柜，这纸…」这类'
                '**称谓 + 指代**，属于正常称呼，不是"同一句话换着说"。'
                '而同一批里诛仙那三条（「小凡你」「跟你走」「你师父」）是真问题。',
        countable='命中数（是否被报出来）与命中键（是不是称谓）。'
                  '加上店家类称谓后：真人 54 篇仍 **0** 命中、望江楼归零、'
                  '诛仙三条一条未漏、边城仍 0。',
        fix='`crew/global_checks._ADDRESS` 补店家类称谓'
            '（掌柜 / 老板 / 店主 / 公子 / 小姐 / 大人 / 师傅 / 先生）。',
        wrong='① 直接把「重复」全关掉 —— 诛仙那三条真问题会一起消失；'
              '② 只补「掌柜」两个字 —— 「掌柜这」是三字片段，'
              '白名单判的是"片段里含称谓"，所以补「掌柜」就够，但要验证。',
        landing=('crew/global_checks.py',),
        evidence=(),
        checks=('verify_reflexion:D2b',),
        mutations=('mutate_reflexion:M18',),
        note='★ 这条是**横向对比四篇**才暴露的：单看一篇会觉得"报了就应该改"，'
             '把四篇的候选并排放，才发现其中一条是称谓噪声。'
             '⇒ 候选清单要**多篇一起看**，单篇的"命中"没有意义。'
             '★ 夹具要真的能触发：第一版只写 2 句含「掌柜这」，'
             '少于门槛 4，剔掉白名单也照样不命中 —— 独立跑一次才发现。',
    ),
    Rule(
        id='R56',
        title='**规则要有配额**：「可以不接」不加上限，会被过度执行成"一直挡"',
        layer='product',
        symptom='2026-10-20 望江楼那篇：阿九反复问（白灯笼 2 次、纸上的字 3 次），'
                '沈砚的回答 7 次里 6 次是挡回去（「坐」「喝茶」「你再看仔细些」'
                '「你是认还是不认」）。八项指标全 0、全书候选 0 —— '
                '**它就是"写得很顺、但戏没往前走"**。'
                '读 `LIVE_SPEECH_RULES` 才发现根因：那条规则本意是对的'
                '（「一场戏不必让每句台词都得到回应」，防两个人念稿），'
                '但它**只有方向、没有上限**，模型读成了"可以一直不答"。',
        countable='答句里"挡回去"的比例（极短 ≤4 字 / 反问 / "你再看…"开头）。'
                  '⚠ 这个数**在真人与真跑之间分不开**：真人 4 篇命中、'
                  '最高比例 0.88，而望江楼只有 0.44 —— 所以**不做检测器**。',
        fix='在 `LIVE_SPEECH_RULES` 那条后面补**配额**：'
            '「一场戏不能一次都不接……挡回去可以用一次、两次；'
            '第三次还在挡，就必须换成回答」，并写明**什么算回答**'
            '（给出一条对方原本不知道的信息，不是态度、不是评语、不是又一句反问）。',
        wrong='① 做一个"短答比例"检测器 —— 真人比真跑更像病（0.88 vs 0.44），'
              '会变成专杀真人的假判据；'
              '② 在导出层定向重写"把挡改成回答" —— 那是**新增内容**，'
              '撞上"事实一个字不许改"的硬约束，机器会编造答案；'
              '③ 把「不是每句都得接」整条删掉 —— 走向另一个极端，'
              '对话会变回"两个人严丝合缝念稿"。',
        landing=('crew/agents.py',),
        evidence=(),
        checks=('verify_reflexion:F1', 'verify_reflexion:F2',
                'verify_reflexion:F3', 'verify_reflexion:F4',
                'verify_reflexion:F5'),
        mutations=('mutate_reflexion:M19', 'mutate_reflexion:M20'),
        note='★ 这条是"**源头修**"而不是"后处理修"的样板：'
             '症状在导出稿上看得见，但**成因在提示词里**，'
             '而后处理要修它只能靠编造 —— 所以必须回到源头。'
             '★ 可推广的形态：**凡写了"可以不/不必/偶尔"的规则，都要配一句上限**'
             '（"但一次都不…不行"）。这类规则被过度执行时，'
             '稿子会很顺、指标全绿、**只有读的人觉得闷**。'
             '★ 这一项**故意没有检测器**，F5 钉住"别有人又去加一个假判据"。',
    ),
    Rule(
        id='R57',
        title='装订稿**末尾**附质量指标页：每个数字都要能读懂',
        layer='product',
        symptom='2026-10-20 用户要求：「在软件导出小说内容的时候，把上面的指标放到结尾，'
                '并逐项说清楚各个数值的意思」。此前导出的稿子只有正文，'
                '作者想知道"这一稿哪里不对"只能靠读；'
                '而诊断数据只在 `metrics.json` 里（那是给程序读的）。',
        countable='八项检测 + 四类全书候选 + 三项节奏指标，**逐项列全（为 0 也列）**，'
                  '每项都要有「口径」与「为什么算毛病」两栏；'
                  '真人参考必须带样本量（36 篇）。'
                  '判据 G2 要求 8 项全在页面上，G3 要求每项口径 ≥8 字、理由 ≥15 字。',
        fix='`export/quality_page.py::render` 生成；'
            '`export/novel_version.render_manuscript` 在**末尾**追加，'
            '**只对 `novel` 那一档**（参考册要看过程痕迹、原文稿一字不许动）。',
        wrong='① 放在**文件头** —— 一上来先看一堆百分比和阈值，读小说的兴致就没了；'
              '② 在 `total == 0` 时只写一句"八项全部为 0" —— 那不是逐项解释：'
              '读者分不清"没毛病"和"没检查"（G2 钉住）；'
              '③ 生成失败就让导出失败 —— 附录是加分项，'
              '宁可没有它，不许把稿子搞没（G6 钉住）。',
        landing=('export/quality_page.py', 'export/novel_version.py'),
        evidence=(),
        checks=('verify_reflexion:G1', 'verify_reflexion:G2', 'verify_reflexion:G3',
                'verify_reflexion:G4', 'verify_reflexion:G5', 'verify_reflexion:G6',
                'verify_reflexion:G7', 'verify_reflexion:G8', 'verify_reflexion:G9'),
        mutations=('mutate_reflexion:M21', 'mutate_reflexion:M22',
                   'mutate_reflexion:M23'),
        note='★ 这一页**只解释口径、不给建议** —— 建议在 `导出/反思记录.md` 里。'
             '混在一起会变成第二份待办清单，而没人读第二份。'
             '★ 反复强调"真人参考不是及格线"：真人样本里有 1 段憋气、'
             '逗号密度低到 0.67，拿它当"必须 0"去改会把正常段落改坏。'
             '★ M23 那次很有教育意义：G8 测的是"指标页自身以 `---` 开头"，'
             '与拼接位置无关 ⇒ 把 `text + _page` 改成 `_page + text` 照样绿。'
             '补了 G9 用 **AST 找"赋值给 text、加法右操作数含 `_page`"** 才测得住。',
    ),
    Rule(
        id='R58',
        title='剧情卡住要在**世界状态层**判，不在文本层判：四样全同才算没动',
        layer='product',
        symptom='2026-10-20 夜：望江楼连跑两版都是"剧情原地打转"——'
                '柳氏反复逼问白绫、阿九反复隐瞒（"壶…壶空了""白绫我不认得"），'
                '四场戏全在同一个前厅，八项指标全 0，全书候选 0。'
                '**读完稿子觉得闷，但所有尺子都说没问题。**'
                '场记在日志里连报"第二幕事件与前情完全重复"，而它是**有意只报不修**的'
                '（`_crew_wrap` 注释：分不清"真错"与"有意复现"）。',
        countable='每拍算一个世界状态指纹：**空间 + 在场人物 + 每人手上那件事 + 这一段在谈什么**。'
                  '四样**逐字相同** ⇒ 这一拍什么都没变。'
                  '连续 3 拍 → `vary`（换事件类型）· 5 拍 → `shift`（必须有人进出）· '
                  '8 拍 → `settle`（走已有僵局结算）。'
                  '实测（mwl_v1）：24 拍里 7 条事件，**5 条都是"【来人】"**（送油/讨钱/找弟弟）。',
        fix='`director/stall.py`（`fingerprint` / `note` / `level` / `pick_type` / `shift_hint`）；'
            '`sim/loop._tick` 每拍调 `note_and_hint`；'
            '`director.engine._inject_event` 在停滞时用 `pick_type` 避开上一拍的类型。',
        wrong='① **句子层**（`global_checks.echo_phrase`）：真人 4 篇命中、最高比例 0.88，'
              '望江楼只有 0.44 ⇒ 真人比真跑更像病，分不开；'
              '② **派活文本相似度**（`assignment_shared`）：共享 3 可能是推进'
              '（"拿准主意"→"定下并传令"），共享 7 可能只是换词'
              '（"因紫砂壶浮起旧忆"→"从所持壶上浮起旧忆"）⇒ **字面相似不是"重复"的量**；'
              '③ **日志四元组**（本文件第一版）：日志只记场景级 3–7 拍，粒度太粗，最长停滞全 ≤2；'
              '④ 在导出层改写：那是**新增内容**，违反"事实一个字不许改"。',
        landing=('director/stall.py', 'director/engine.py', 'sim/loop.py', 'world/state.py'),
        evidence=('developers/probe_stall_e2e.py',),
        checks=('verify_reflexion:H1', 'verify_reflexion:H2',
                'verify_reflexion:H2b', 'verify_reflexion:H2c',
                'verify_reflexion:H2d', 'verify_reflexion:H3',
                'verify_reflexion:H4', 'verify_reflexion:H5', 'verify_reflexion:H6',
                'verify_reflexion:H7', 'verify_reflexion:H8', 'verify_reflexion:H9',
                'verify_reflexion:H10', 'verify_reflexion:H11',
                'verify_reflexion:H13', 'verify_reflexion:H14',
                'verify_reflexion:H15', 'verify_reflexion:H16'),
        mutations=('mutate_reflexion:M24', 'mutate_reflexion:M25',
                   'mutate_reflexion:M26', 'mutate_reflexion:M27',
                   'mutate_reflexion:M28', 'mutate_reflexion:M29',
                   'mutate_reflexion:M30', 'mutate_reflexion:M31',
                   'mutate_reflexion:M32', 'mutate_reflexion:M33',
                   'mutate_reflexion:M34', 'mutate_reflexion:M43',
                   'mutate_reflexion:M44'),
        note='★ **"有意复现"与"卡住"的分界线就是这四样**：'
             '真要复现，作者一定至少动一样 —— 换空间（回到那年）、换在场人（当年的证人）、'
             '换话题（"后来我才知道"）。那个"这是另一层时间"的信号，本身就是指纹的变化。'
             '卡住是**四样全不动，只有字数在涨**。'
             '★ 三档处置**全部复用已有设施**（`pick_type` 包在 `PRESS.decide` 外面、'
             '`watch_note` 是现成的跨拍通道、`request_settle` 是 2026-10-19 就建好的），'
             '不新造机制 —— 新造的东西没人维护。'
             '★ 两个坑记在这里：'
             '① 计数语义必须与阈值语义对齐（第一版"与上一拍相同的次数"让阈值 3 实际到第 4 拍）；'
             '② 判据要**逐项容错**：指纹一崩，第一版让整个 `group_h` 抛出去，'
             '反例法只看到"组崩溃"、定位不到是哪一项（M24/M25 就是这么隐身的）。'
             '★ **第三样（每人手上那件事）本来会漏同义词**：它吃的是模型写的派活文本，'
             '同一个目标换个说法（"弄清白绫的来历"/"搞明白那条白绫是从哪来的"）'
             '字面不同 ⇒ 指纹不同 ⇒ **被算成推进**，卡住反而更难发现（实测）。'
             '`_goal_key` 只归并三族（弄清 / 来历 / 追问），**不碰对象**：'
             '"弄清"→"说出" 依然算推进（查到 ≠ 交出去）。H15/H16 钉住这一对方向。',
    ),
    Rule(
        id='R59',
        title='**外部评审也是判官**：诊断可采信，处方必须过闸，验不了的如实说',
        layer='product',
        symptom='2026-10-20 深夜：作者把望江楼一段发给另一个 AI（以"资深小说作家 + '
                '剧作改编"身份）评审，拿回 5 条批评。逐条量完，**只有 2 条能直接用**：'
                '① 人物标识混乱 → 真（2 处会被读成祈使句），但处方错；'
                '② 动作脱节"大量琐碎动作" → 真（19.4 处/千字，真人上限 5.6）且它还说轻了；'
                '③ "5 次追问白绫" → 带问号的只有 2 次，同主题台词 13/34 句；'
                '④ 时空跳跃 → 无过渡句，真但弱；'
                '⑤ 第一人称混全知 → 需要位置推理，验不了。',
        countable='四档分诊：`confirmed`（有可数证据）/ `exaggerated`（方向对、数字被放大）'
                  '/ `refuted`（有证据反驳）/ `unverifiable`（**没有可数代理**）。'
                  '只有 `confirmed` 转成改写教训；其余**不驱动改写**。'
                  '⚠ 阈值必须先在真人样本上量：动作密度真人 36 篇中位 0.0 / 最高 **5.6**，'
                  '取 6.0；而 mwl_v2（被评审那版）是 **19.4**。',
        fix='`crew/critique.py`（`split_items` / `adjudicate` / `lessons` / `markdown`）；'
            '`crew/name_guard.py`（`collides` / `risky_positions` / `first_mention_hint`）；'
            '`crew/global_checks.action_density`；'
            '`export/novel_version._adjudicate_review` 读 `<运行目录>/外部评审.md` 并把分诊表'
            '写进 `导出/反思记录.md`。',
        wrong='① **照处方改**：评审建议「若"沈砚"是动词，应改为"别问"」—— 而「沈砚」'
              '同时是**楼名**（望江楼）、**人名**、楼的**规矩**（"不问来路，不问去处"）、'
              '掌柜的**口头禅**。照改这本书的骨架就没了。⇒ 处方含"改名/改为"时一律标'
              '`prescription_risky`，只报不改；'
              '② **接错验证器**：把"视角混杂"接到 `percept_issues`（那个测的是'
              '"隔着纸门看见睫毛上沾着雪"），于是评审第 5 条被判 `refuted` —— **假反驳**。'
              '接错验证器比不接更糟：它给出一个看似有理的否定结论；'
              '③ **动作密度匹配光杆动词**：「点/按/收」把"一点点/按住/收下"都算进去，'
              '把 6 处数成 **35 处**，还据此判"成立"；口径必须是**动宾**（抹壶/搁盏）；'
              '④ 短文本也下密度结论：220 字里一处动作算出 59 每千字，那个数没有意义 —— '
              '必须 `judged=False` ⇒ `unverifiable`，不是 `refuted`。',
        landing=('crew/critique.py', 'crew/name_guard.py', 'crew/global_checks.py',
                 'export/novel_version.py'),
        evidence=('developers/probe_critique.py',),
        checks=('verify_reflexion:I1', 'verify_reflexion:I2', 'verify_reflexion:I3',
                'verify_reflexion:I4', 'verify_reflexion:I5', 'verify_reflexion:I6',
                'verify_reflexion:I7', 'verify_reflexion:I8', 'verify_reflexion:I9',
                'verify_reflexion:I10', 'verify_reflexion:I11', 'verify_reflexion:I12',
                'verify_reflexion:I13', 'verify_reflexion:I14', 'verify_reflexion:I15',
                'verify_reflexion:I16'),
        mutations=('mutate_reflexion:M35', 'mutate_reflexion:M36',
                   'mutate_reflexion:M37', 'mutate_reflexion:M38',
                   'mutate_reflexion:M39', 'mutate_reflexion:M40',
                   'mutate_reflexion:M41', 'mutate_reflexion:M42'),
        note='★★★ 这条规则最重要的一句：**外部批评和我们自己的判据是同一类东西** —— '
             '都会误判、都会给出看似有理的错结论。所以它也要走"降级为顾问"那一套。'
             '★ `unverifiable` 这一档是刻意留的。这一晚量了三次才认下来：'
             '"追问次数""主题集中度""悬念密度"在真人与真跑之间**分不开**'
             '（真人最大主题覆盖 33%，望江楼 20%；v3 22% 反而比 v2 好读）——'
             '硬做检测器就会变成专杀真人的假判据。**不知道就说不知道。**'
             '★ 这一轮反例法又抓到两个"改不动行为"的变异：'
             '① M39 被更窄的 `zh<120` 先拦住（两道闸管同一件事 ⇒ 一道是死代码，已删）；'
             '② M40 只改 KEYWORDS 而 VERIFIERS 里早已没有该条目 ⇒ 无效变异。',
    ),
    Rule(
        id='R60',
        title='**"不许半文半白"只管了台词**：叙述层一条语体约束都没有',
        layer='product',
        symptom='2026-10-20 深夜，作者读完望江楼说"感觉有点半文半白"。'
                '实测不是"文得多"也不是"白得多"，而是**一段里两种语体打架**：'
                '`柳氏西窗坐，白衣映灯`（砍掉"在/着"的文言四字句）+ '
                '`布料上的暗绣被暖黄的光勾出浅淡的轮廓`（"被…勾出…轮廓"的翻译腔）+ '
                '`安静得像一幅画`（现代明喻）。'
                '根因：`agent/core.py` 那条"不许夹文言词、不许半文半白"**只管台词**'
                '（分镜那条也只管台词），**叙述层一条约束都没有**；'
                '而 `style.sentence` 只写"句子短、动词多、形容词少"是**纯方向** —— '
                '模型要"短"，最省力的办法就是砍虚词 ⇒ 砍成文言。与 R56 同型。',
        countable='分两层量：'
                  '① **提示词层**（可数）：生成的「顶级规则」里有没有「全篇一种语体」'
                  '与成对的两条边界（不许砍虚词 / 不许翻译腔）；'
                  '② **文本层**（**不可数，故意不做**）：'
                  '用"处所状语直接接动词"（`柳氏西窗坐`/`我立柜边擦桌`）量，'
                  '真人 54 篇命中 **13 处全是误报**（`他在铺上躺`/`梯子往墙上靠`/`往下看`）'
                  '—— 正则在现代汉语里分不开"文言倒装"与"正常省略"；'
                  '换成词频（之/其/乃 × 情绪/开始）更糟：真人也有"之×1 + 开始×1"。',
        fix='`novel_bench/bench/project_builder._rules` 在「写法」段补三条'
            '（全篇一种语体 / 不许靠砍虚词变短 / 不许用现代翻译腔），'
            '并用**真实错句**当反例（`柳氏西窗坐` ✗ → `柳氏在西窗下坐着` ✓）；'
            '`29_mowenlou.yaml` 的 `style.sentence` 补回设定原文那句'
            '"明清白话，**不是文言**，也不是现代书面语"。',
        wrong='① **只写"不许文言"** —— 会被现代翻译腔填满（"被…勾出…轮廓"）；'
              '② **只写"句子短"** —— 这正是逼出文言的原因，砍虚词是最省力的短法；'
              '③ **把"句子短"整条删掉** —— 走向另一个极端，变成冗长（M47 钉住）；'
              '④ **做文本层检测器** —— 真人 54 篇 13 处误报，会变成专杀真人的假判据；'
              '⑤ **拿关键词松匹配当判据** —— `style.sentence` 里也写了"不许靠砍虚词"，'
              '删掉代码那条**关键词仍在**，M46 一开始就是这么隐身的。'
              '改成匹配**规则整行**（含 `·` 前缀与箭头示例）才测得准。',
        landing=('novel_bench/bench/project_builder.py',
                 'novel_bench/dataset/works/29_mowenlou.yaml'),
        evidence=(),
        checks=('verify_reflexion:F6', 'verify_reflexion:F7',
                'verify_reflexion:F8', 'verify_reflexion:F9',
                'verify_reflexion:F10', 'verify_reflexion:F11'),
        mutations=('mutate_reflexion:M45', 'mutate_reflexion:M46',
                   'mutate_reflexion:M47', 'mutate_reflexion:M48',
                   'mutate_reflexion:M49'),
        note='★ 这与 R56 是**同一个形态**："规则只有方向、没有边界"。'
             'R56 是「可以不接」没配配额，被过度执行成"一直挡"；'
             '这一条是「句子短」没配边界，被过度执行成"砍虚词"。'
             '可推广：**凡写了"要更 X"的规则，都要补一句"但不许靠 Y 换 X"**。'
             '★ 语体一致性**故意没有文本层检测器**：量了两种口径都失败（见 `countable`）。'
             'F9 钉住这个结论，免得下一个人又去写一个假判据。'
             '★ 反例用的是**真实错句**而不是抽象描述 —— 模型看得懂'
             '"柳氏西窗坐 ✗ → 柳氏在西窗下坐着 ✓"，看不懂"注意语体一致性"。'
             '★★ **只治句式会换到词汇那头**（第二轮实测，v4）：'
             '翻译腔 4→0、倒装 3→0，但冒出「我**遂**问」「**便以**鞋尖抵住」。'
             '补第三类反例（文言虚词）之后才补全。这条规则因此要**三类反例**：'
             '砍虚词 / 翻译腔 / 文言词 —— 少一类就漏一类。'
             '★ 但**不许禁** `方才/为何/可还/不曾`：那是明清白话里本来就有的，'
             '禁了就是"专杀正常白话"（F11 钉住）。',
    ),
    Rule(
        id='R61',
        title='**先总后分、逐层过闸**：剧情空转要在结构层治，不在句子层治',
        layer='product',
        symptom='2026-10-21 凌晨，作者问："为何小说作家/剧作家/导演不能先生成一个大的'
                '故事框架，再补细节，一点点变成小说？把打草稿、审核剧情、单独修改草稿、'
                '最终确认、补充细节这些真实创作流程引入进来……每完成一步都确认没有'
                '剧情空转、逻辑错误，没问题了再继续。"'
                '对应的实测事实：望江楼连跑三版都在原地打转（问白绫→挡回去→再问），'
                '八项指标全 0 —— 空转不是"某一句写坏了"，是**整章没让任何事情发生变化**，'
                '逐句尺子天生看不见。而按日装订出来的是"每天的过程稿首尾相接"，'
                '没有全书骨架，空转在结构上就已注定，事后修句子没用。',
        countable='**变化账本**：每一步写清「谁 · 关于什么 · 从哪个状态到哪个状态」，'
                  '四个槽全部来自闭集 —— kind∈{信息,关系,处境,物}、'
                  'subject∈人物表、obj∈推演材料里出现过的词、'
                  'before/after∈该 kind 的状态闭集（信息：不知→疑→知→确证）。'
                  '签名 = kind|subject|obj|after。'
                  '相邻章/相邻拍签名相同 ⇒ `stall`；同一签名 ≥3 次 ⇒ `repeat`；'
                  '状态倒退且没标 reversal ⇒ `regress`。'
                  '另有四道结构闸：事件全覆盖（含拍级）、无凭空事件、时序单调、每章指向主线。',
        fix='`crew/atelier.py`（数据模型 + 账本 + 四道闸 + 导图，**零模型调用**）；'
            '`crew/atelier_run.py`（四层提示词 + 解析 + 重试 + 选优）；'
            '`export/novel_version.compose_by_atelier`（从本次推演抽事实、跑四层、'
            '落盘 `导出/骨架.json` 与 `导出/分层稿.md`）；'
            '`render_manuscript` 优先装订分层稿。'
            '开关 `EXPORT_ATELIER`（默认开），失败自动退回按日装订。',
        wrong='① **用文本相似判空转**：句子相似（真人比真跑更像病）、派活相似'
              '（共享 3 可能是推进、共享 7 只是换词）两次实测都分不开；'
              '② **账本用自由文本**：第一版写 `after="他知道井里有白绫"`，'
              '三章换成「知道/晓得/明白」签名各不相同 —— 三章打转一条都没报，'
              '与 `_goal_key` 踩的是同一个同义词后门；⇒ 必须闭集，不许自由文本。'
              '③ **一层没过还往下跑**：第一版记下问题继续跑 L2/L3，'
              '等于"先记下来后面一起修" —— 正是旧流程失败的原因（D5 钉住）；'
              '④ **只治骨架不管衔接**：骨架对、账本对，L2 仍会把上一章的取壶、'
              '见无影再演一遍（真跑实测），因为没告诉它"前面演过什么"'
              '（E4/E5 钉住，`replay_open` 兜底）；'
              '⑤ **人名靠"说/问/道前面的两三个字"**：`台后头说` `我正想问` `她只说` '
              '全被当成人名，真跑一次误报 7~12 条把 L2 卡死 ⇒ 必须数频次（≥2 次）。',
        landing=('crew/atelier.py', 'crew/atelier_run.py',
                 'export/novel_version.py', 'config.py'),
        evidence=('developers/probe_atelier.py',),
        checks=('verify_atelier:A1', 'verify_atelier:A2', 'verify_atelier:A3',
                'verify_atelier:A4', 'verify_atelier:A5', 'verify_atelier:A6',
                'verify_atelier:A7', 'verify_atelier:A8',
                'verify_atelier:B1', 'verify_atelier:B1b', 'verify_atelier:B2',
                'verify_atelier:B3', 'verify_atelier:B4', 'verify_atelier:B5',
                'verify_atelier:B6', 'verify_atelier:B7', 'verify_atelier:B8',
                'verify_atelier:B9', 'verify_atelier:B10', 'verify_atelier:B11',
                'verify_atelier:B12', 'verify_atelier:B12b',
                'verify_atelier:B13', 'verify_atelier:B14',
                'verify_atelier:C1', 'verify_atelier:C2', 'verify_atelier:C2b',
                'verify_atelier:C3', 'verify_atelier:C4', 'verify_atelier:C5',
                'verify_atelier:C6', 'verify_atelier:C7',
                'verify_atelier:D1', 'verify_atelier:D2', 'verify_atelier:D3',
                'verify_atelier:D4', 'verify_atelier:D5', 'verify_atelier:D6',
                'verify_atelier:D7',
                'verify_atelier:E1', 'verify_atelier:E2', 'verify_atelier:E3',
                'verify_atelier:E4', 'verify_atelier:E5', 'verify_atelier:E6'),
        mutations=('mutate_atelier:M1', 'mutate_atelier:M2', 'mutate_atelier:M3',
                   'mutate_atelier:M4', 'mutate_atelier:M5', 'mutate_atelier:M6',
                   'mutate_atelier:M7', 'mutate_atelier:M8', 'mutate_atelier:M9',
                   'mutate_atelier:M10', 'mutate_atelier:M11', 'mutate_atelier:M12',
                   'mutate_atelier:M13', 'mutate_atelier:M14',
                   'mutate_atelier:M15', 'mutate_atelier:M16'),
        note='★★★ 这条最重要的判断：**判定权必须完全归代码，而且必须在这一层就判**。'
             '旧流程"写完再挑毛病"有三个绕不过去的后果：空转只能事后发现（逐句尺子看不见）、'
             '改一处碰坏另一处、改不动结构。分层之后，"没问题了再继续"落成一句硬的：'
             '闸返回非空 ⇒ 这一层不算完、下一层不跑（`compose` 里的 `break`）。'
             '★ 空转的定义因此从"像不像"变成"变没变"：账本签名逐字相同才算没动 —— '
             '这正是 R58 世界状态指纹的同一思路，只是搬到了写作侧。'
             '★★ 写到一半就发现：**我自己又踩了两个已经写进规则的坑** —— '
             '自由文本账本（同义词后门）、一层没过还往下跑（先记后修）。'
             '两个都是判据逼出来的，不是想出来的。'
             '★ 真跑验收（mwl_v4，3 章，两次独立复现）：四层**全部一轮过闸**、'
             '事件 7/7、变化 10 种、空转对 0、未解决 0；正文 2516 字、逗号/句 1.40'
             '（真人中位 1.00）。装订验证：`render_manuscript` 的来源行改为'
             '"分层创作"、正文用分层稿、指标页仍在。'
             '★ 第一版正文把第 1 章开场演了两遍 —— 骨架和账本都对，是"衔接"没给 '
             '⇒ 补 `prev_summary` + `replay_open`，复跑后第 2 章从"我从井台回来"'
             '接着写。这条说明：**结构对 ≠ 正文对**，衔接也是结构的一部分。',
    ),
    Rule(
        id='R62',
        title='群众演员必须挂得住主线：说不出为哪件事来的，不准进门',
        layer='product',
        symptom='用户 2026-10-21 读完真跑稿："有些群众演员出现的没道理，群众演员出来'
                '也必须跟故事主线有关系才可以，最好不要突然出来一个，没有任何作用'
                '就又退场了。群众演员临时演员的意思，是在主角列表之外，承接剧情需要的'
                '演员，而不是没有任何作用，突然出现的人。"'
                '⚠ 这不是"群演不够好"，是**三处因果全断了**：'
                '① 投人的提示词明写「**不要直接推动主线**」（等于教模型投无关的人）；'
                '② 登记时**不问"他为哪件事来"**，谁都能进门；'
                '③ 退场**按拍数到期**（3~5 拍），和他要的事办没办成无关。'
                '出场与退场都不由剧情决定，读者看到的就是"突然来了又走了"。',
        countable='四项都可数，全部零模型调用：'
                  '① 正在推进的事有几条（`crowd.open_threads`）—— 空世界必须是 **0 条**，'
                  '且"他真正缺的东西"（`need`）**不许**进清单；'
                  '② 模型给的 `挂`（那件事的序号）能不能落进 `1..N` —— '
                  '**落不进就不投**（闭集，措辞无处可逃）；'
                  '③ 登记时 `挂` 在不在当前清单里 —— 不在就 **不登记**（三个来源共用一道闸）；'
                  '④ 没人搭话时能撑几拍（`FUNC_PATIENCE`=8）与有人接住后收尾几拍'
                  '（`ENGAGE_AFTER`=2）—— **退场理由必须说得出来**'
                  '（"等不到人，走了"而不是凭空消失）。',
        fix='`world/crowd.py` 加挂靠层：`open_threads`（活跃故事线 / 这一段在谈的原话 / '
            '在场人物的 `mission`·`goal`）+ `anchor_ok`（挂不上就不登记）+ '
            '`engaged`（称呼被叫到、或诉求被说起 ≥2 个实字）；'
            '`add_extra` 一律过 `anchor_ok`（规则池 / 剧组投人 / 别处登记**同一个漏斗**）；'
            '`tick_extras` 对**有挂靠**的人改成"事办没办成"：有人接 → `ENGAGE_AFTER` 拍收尾，'
            '没人接 → `FUNC_PATIENCE` 拍**空等而走**并记进钩子名册；'
            '`ExtraCasting.cast` 提示词删掉「不要直接推动主线」，改成摊出编号清单、'
            '要求填 `挂`（序号）+ `接`（怎么搭上的）；没有正在推进的事就**不投、不调模型**；'
            '`new_extra` 走 `pick_from_pool`（池子里那条诉求必须与某条线共用 ≥2 个实字）。',
        wrong='⚠ **加一条"诉求必须提到主线关键词"的字面比对** —— 换个说法就归零'
              '（MEMORY：同义词是字面判据的后门）；本条用**序号**（闭集）而不是自由文本。'
              '⚠ **把"挂靠"做成提示词里的一句话** —— 写了不等于遵守（40%~74% 不遵守），'
              '所以登记处必须有代码闸；`add_extra` 就是那道闸。'
              '⚠ **给规则池开一条免检后门**（"兜底嘛，抽到谁算谁"）—— 那正是病灶③；'
              '兜底也要挂得住，搭不上就**这拍没人来**（门口空着好过白来一个）。'
              '⚠ **把 `tick_extras` 直接改成永不退场** —— 会留僵尸；'
              '等满了要**带着理由**走，并记进钩子名册（这趟不白来）。',
        landing=('world/crowd.py', 'crew/agents.py', 'crew/atelier.py', 'sim/loop.py'),
        checks=('verify_extras_anchor:A1', 'verify_extras_anchor:A1b',
                'verify_extras_anchor:A2', 'verify_extras_anchor:A2b',
                'verify_extras_anchor:A3',
                'verify_extras_anchor:B1', 'verify_extras_anchor:B1b',
                'verify_extras_anchor:B2', 'verify_extras_anchor:B2b',
                'verify_extras_anchor:B3', 'verify_extras_anchor:B4',
                'verify_extras_anchor:B4b', 'verify_extras_anchor:B5',
                'verify_extras_anchor:B5b',
                'verify_extras_anchor:C1', 'verify_extras_anchor:C1b',
                'verify_extras_anchor:C2', 'verify_extras_anchor:C2b',
                'verify_extras_anchor:C2c', 'verify_extras_anchor:C2d',
                'verify_extras_anchor:C2e', 'verify_extras_anchor:C2f',
                'verify_extras_anchor:C2g', 'verify_extras_anchor:C2h',
                'verify_extras_anchor:C2i',
                'verify_extras_anchor:D1', 'verify_extras_anchor:D2',
                'verify_extras_anchor:D2b', 'verify_extras_anchor:D2c',
                'verify_extras_anchor:D2d',
                'verify_extras_anchor:D3', 'verify_extras_anchor:D3b',
                'verify_extras_anchor:D3c',
                'verify_extras_anchor:D4', 'verify_extras_anchor:D5',
                'verify_extras_anchor:F1', 'verify_extras_anchor:F1b',
                'verify_extras_anchor:F2', 'verify_extras_anchor:F2b',
                # ★ 2026-10-21 真跑判决后补的两组：话题排序（A1c/A1d）与"有人去理他"（G）
                # [EN] ★ Two groups added after the 2026-10-21 real-run verdict: topic ordering
                # [EN] (A1c/A1d) and "someone deals with him" (G)
                'verify_extras_anchor:A1c', 'verify_extras_anchor:A1d',
                'verify_extras_anchor:G1', 'verify_extras_anchor:G1b',
                'verify_extras_anchor:G2',
                'verify_extras_anchor:G3', 'verify_extras_anchor:G3b',
                'verify_extras_anchor:G4', 'verify_extras_anchor:G4b',
                'verify_extras_anchor:G5', 'verify_extras_anchor:G5b',
                'verify_extras_anchor:G6', 'verify_extras_anchor:G6b',
                'verify_extras_anchor:G7', 'verify_extras_anchor:G7b',
                'verify_extras_anchor:G7d', 'verify_extras_anchor:G7e',
                'verify_extras_anchor:G8', 'verify_extras_anchor:G8b',
                'verify_extras_anchor:D6', 'verify_extras_anchor:D6b',
                'verify_extras_anchor:G9', 'verify_extras_anchor:G9b',
                'verify_extras_anchor:G9c', 'verify_extras_anchor:G9d'),
        mutations=('mutate_extras_anchor:M1', 'mutate_extras_anchor:M2',
                   'mutate_extras_anchor:M3', 'mutate_extras_anchor:M4',
                   'mutate_extras_anchor:M5', 'mutate_extras_anchor:M7',
                   'mutate_extras_anchor:M8', 'mutate_extras_anchor:M9',
                   'mutate_extras_anchor:M10', 'mutate_extras_anchor:M11',
                   'mutate_extras_anchor:M12', 'mutate_extras_anchor:M13',
                   'mutate_extras_anchor:M14', 'mutate_extras_anchor:M15',
                   'mutate_extras_anchor:M16', 'mutate_extras_anchor:M17',
                   'mutate_extras_anchor:M18',
                   'mutate_extras_anchor:M19', 'mutate_extras_anchor:M20'),
        note='★ 这条的核心是**把"因果"落到一个可数的槽上**：`挂` 是序号（闭集），'
             '不是"他跟主线的相似度"（那是量不出来的，也只能量成字面重合）。'
             '★ 判据分两层测同一件事的两面：`add_extra` 测"进不进门"，'
             '`tick_extras` 测"走不走得成"—— 一条判据只测一道闸。'
             '★★★ 2026-10-21 **真跑判决推翻了第一版的一半**：'
             'mwl_v5 来了 6 个群演、都能说清"为哪件事来"（来由修好了），'
             '**正文出现 0 次**、4 个「等不到人，走了」。三处根因全部实测到：'
             '① `engaged` 拿"内容重合"当"有人在理他" —— 打更人的诉求「说白衣客没影子」'
             '与阿九心里「柳氏坐桌边没有影子」共用 4 个实字，被判"已接"，'
             '其实没人在跟他说话；'
             '② **导演派活不看群演** —— 打更人进门那一拍，派出去的三条活'
             '（回屋歇着 / 吩咐续茶 / 低念一句）没有一条与他有关，人物当然不理他；'
             '③ 挂靠清单把 `topic` 排在人物的活前面 —— AI 从「水底看不见月亮」里'
             '读出的不是一件事而是**氛围**，于是投出"还伞的脚夫""赶夜路的皮货客"'
             '这种背景音；而 mwl_v4 规则池投的是「讨账的」（压力型来客）。'
             '⇒ 补三处：`engaged` 只认称呼/`to`（关系，不是内容）；'
             '`open_threads` 把 `topic` 挪到最后（顺序就是优先级）；'
             '`director.dispatch` 摊出「门口此刻等着的人」+ **代码硬兜底**'
             '（`unhandled`/`handoff_line`，并让那一条不被"上一件还在办"拦掉），'
             '`_sync_crowd` 在**进门那一拍**就派活（dispatch 每 8 拍、耐心也是 8 拍，'
             '卡在边界上，实测一次都没赶上）。'
             '⚠ 诚实边界：v4 的 4 个群演**也是正文 0 次** —— "群演白来"是老问题，'
             '不是这一版改坏的；这次只修好了"来由"，"作用"要靠上面三处才可能修好。'
             '⚠ 另一条：这一组判据第一版有两条**查源码字符串**（G7/G7c），'
             '反例法当场证明是假判据（把 `waiting()` 改成 `[]`，那段字符串还在，照样绿）'
             '⇒ 改成真跑一次 `dispatch`、真跑一次 `_apply_missions` 的行为判据，'
             '并因此把"应用派活"那段从 `_maybe_branch` 抽成 `_apply_missions`。'
             '★★★ 第三处（第四次真跑才查出来，最隐蔽）：**整理稿禁止他出现**。'
             '`_transcribe_once` 的提示词写着「今天真正上场的人（正文里**不许出现**'
             '名单外的任何人）…… 一个字都不许写」，而那份名单取自 `on_stage_names()`，'
             '群演在 `world.extras` 里、**永远不在名单上** ⇒ 模型忠实地一个字都没写。'
             '证据：v6 的日志里阿九向柳氏打听过那位掏井匠、柳氏也反问了一句，'
             '而正文 1402 字里\\"掏井\\"出现 **0 次**。'
             '⇒ 加 `WorldState.extras_engaged`（当天被叫到名字/被对着说话的群演），'
             '收工时在禁令上开**显式例外**，并写明"只写实际发生的那几句"。'
             '⚠ 只对**被理过的**开（没人理的照样不许进正文，那才是白来一趟）。',
    ),
    Rule(
        id='R63',
        title='只报了个到的群演不进事实底账：删掉他读者什么都没丢',
        layer='product',
        symptom='群演那一行（`【来人】某某——要什么`）会作为 `event` 落进台本，'
                '再被 `Source.from_run` 当成"真的发生了"的事实喂给分层创作 —— '
                '于是正文里出现一个**没有前因、没有后果的人**（用户："没有任何作用'
                '就又退场了"）。⚠ 推演期修好"挂得上才进门"之后**仍有残余**：'
                '挂上了不等于有人理；这种"挂得住、没人接"的人照样会进正文。',
        countable='**可删除性**（不是长度、不是相似度）：这个称呼在整份台本里'
                  '出现次数 **≤1** ⇒ 删掉读者什么都没丢 ⇒ 它只是一声门响，不是一件事；'
                  '**≥2** ⇒ 后文有人提过他，这条必须留（否则后文成了凭空出现的人）。'
                  '⚠ 拿不到整份台本时**一条都不动**：只看 events 的话每个称呼都只出现一次，'
                  '会把所有群演事件全删光（"量错了对象"比不判更糟）。',
        fix='`world/crowd.drop_orphan_casts(events, rows)`：只认 `【来人】/【又来了】`'
            '两种行，别的 event 一概不动；接在 `crew/atelier.Source.from_run` 里 —— '
            '**在事实源头摘掉**，下游 L0~L3 就没有机会照抄一个不该出现的人。',
        wrong='⚠ **在提示词里写"不要写没来由的群演"** —— 那是把可数的活交给模型猜；'
              '而且 L0~L3 的规定是"事实只能来自 `Source`"，源头不干净，下游只能照抄。'
              '⚠ **顺手把 `【又来了】` 排除在过滤之外** —— 老熟人没人接也是白来一趟，'
              '规则一视同仁（他要是真被提起，出现次数自然 ≥2）。'
              '⚠ **拿不到台本时按 events 自己比** —— 见 countable 最后一句。',
        landing=('world/crowd.py', 'crew/atelier.py'),
        checks=('verify_extras_anchor:E1', 'verify_extras_anchor:E2',
                'verify_extras_anchor:E3', 'verify_extras_anchor:E4',
                'verify_extras_anchor:E4b', 'verify_extras_anchor:E5'),
        mutations=('mutate_extras_anchor:M6',),
        note='★ 这一条是 R62 的**下游兜底**，不是重复：R62 管"能不能进门"，'
             '它管"进了门但没人理的人**能不能进正文**"。'
             '★ 判据用的是"可删除性"，与 R43/R47 判"重复"的口径一致 —— '
             '删掉读者损失什么，说不出就不算事。',
    ),
)


# ══════════════════════════════════════════════════════════════
#  查询
# ══════════════════════════════════════════════════════════════
def by_id(rule_id: str) -> Rule | None:
    """按 id 取一条规则（找不到返回 None）。"""
    for r in RULES:
        if r.id == rule_id:
            return r
    return None


def by_layer(layer: str) -> list[Rule]:
    """按层取规则（保持表内顺序）。"""
    return [r for r in RULES if r.layer == layer]


def pending_rules() -> list[Rule]:
    """欠账清单：有判据、还没配反例法的那几条。"""
    return [r for r in RULES if r.pending]


def layer_name(key: str) -> str:
    """层的显示名（未知层原样返回）。"""
    for k, zh, _desc in LAYERS:
        if k == key:
            return zh
    return key
