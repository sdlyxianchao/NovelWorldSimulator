#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""**自由度**：拆成两个旋钮 —— 任务规训（人物有多不听话）与文笔规训（字有多讲究）。

★★★ 为什么必须拆成两个（2026-10-19 用户点名）
--------------------------------------------
用户原话：「AGENT_FREEDOM 拆分成任务规训和文笔规训」。

拆的理由不是"多一个开关更灵活"，而是**这两件事松开的后果完全不同**：

| 旋钮 | 松开之后 | 代价 | 什么时候该松 |
|---|---|---|---|
| **任务规训** | 人物自己决定干什么（可能跑题、可能什么都不干） | 剧情会比"排好的戏"散 | 想要"意外"的时候 |
| **文笔规训** | 句子可以更长/更野/更留白 | 可能出现**难看的句子** | 想要"文体实验"的时候 |

一个旋钮同时管这两件事，会逼出两种坏结果之一：
· 想要意外 ⇒ 顺手把文笔也松了 ⇒ 得到"更散**且**更难看"；
· 想保住文笔 ⇒ 连任务也不敢松 ⇒ 回到"照剧本演"。

⚠⚠ 但有一条**两个旋钮都碰不到**：`SPEAKER_ISOLATION_RULES`（不许替别人说话）。
  它不是"规训"，是**世界的物理法则** —— 松了就不是自由度，是人物开始替别人活。
  判据 `verify_agent_freedom` 的 E 组守这一条（两个旋钮拉到两端都不许少它）。

两个旋钮各管什么（都只有一处实现，别处只调用）
--------------------------------------------
任务规训（`TASK_FREEDOM`）：
  · `frame_scope()`   —— 剧本给到多细（full / agenda / brief）
  · `stage_visible()` —— 本场分拍表给不给演员看
  · `temperature()`   —— 采样温度（它改的是"挑哪个动作"，不是"怎么写句子"）
  · `license_line()`  —— 任务侧的**许可**（"这一拍由你定"）

文笔规训（`STYLE_FREEDOM`）：
  · `deai_items()`      —— 去 AI 清单每类列几个词
  · `distance_forced()` —— 心理距离档是否强制
  · `cot_full()`        —— 思维链是否给完整骨架
  · `tic_quota()`       —— 口癖配额（"这一场已经用了 N 次"）是否启用
  · `style_license()`   —— 文笔侧的**许可**（"可以写得不那么整齐"）

★★★ 文笔规训松的是**当场约束**，不是**事后验收**：
  提示词里少列几个禁词，但落盘的「去AI审计」与 `DEAI_STRIP` 仍然全量跑。
  这个区别必须写清 —— 否则"松文笔"就等于"允许 AI 腔"，那是把毛病当风格。

⚠ 为什么要"许可"（`license_line` / `style_license`）而不只是"少一条禁令"：
  本项目实测过 —— **删掉"必须 X"，模型不是变自由，是停在原地**（十次 `wait`、零动作）。
  松绑必须成对：少一条禁令，补一句许可；许可排在所有约束之后。

全部是纯函数、零成本、**不调模型** —— 每拍问几次也付得起。
"""
from __future__ import annotations

# ── 任务规训的三档分界 ──────────────────────────────────────────
# [EN] Band boundaries for task discipline.
TASK_AGENDA = 0.35
TASK_BRIEF = 0.65

# ── 文笔规训的两档分界（严格 / 标准 / 松）────────────────────────
# [EN] Band boundaries for prose discipline (strict / standard / loose).
STYLE_STRICT = 0.35
STYLE_LOOSE = 0.65

#: 温度区间。它是**任务侧**的（它影响"人物挑哪个动作"，不影响"句子怎么写"）。
#: ⚠ 下限 0.55 不是 0：**完全确定的推演不是推演**，那叫播放录音。
# [EN] Temperature range. It belongs to the **task** side (it changes which action a character
# [EN] picks, not how sentences are written). ⚠ Floor 0.55, not 0: a fully deterministic run is
# [EN] playback, not simulation.
TEMP_LOW = 0.55
TEMP_HIGH = 0.95


def _read(key: str, default: int) -> float:
    """读一个 0–100 的配置项，转成 0.0–1.0。读不到就给 `default`。"""
    try:
        from config import CFG
        v = float(CFG.i(key))
    except Exception:                                            # noqa: BLE001
        return default / 100.0
    return max(0.0, min(1.0, v / 100.0))


def task_level() -> float:
    """任务规训档位：0 = 完全照剧本演，1 = 连今天该演什么都不说。"""
    return _read('TASK_FREEDOM', 50)


def style_level() -> float:
    """文笔规训档位：0 = 最讲究，1 = 松（清单只留最刺眼的、距离不强制）。"""
    return _read('STYLE_FREEDOM', 50)


# ══════════════════════════════════════════════════════════════
#  任务规训
# [EN] Task discipline
# ══════════════════════════════════════════════════════════════
def frame_scope() -> str:
    """剧本给到多细：`full`（照剧本演）/ `agenda`（只给事）/ `brief`（只说一句议程）。

    - `full`   ：`[今日剧本]` 全文 + 分到的事 + **本场分拍表**；
    - `agenda` ：剧本压到 160 字 + 分到的事，**不给分拍表**；
    - `brief`  ：只给"今天该推进哪件事"。
    [EN] How much script to hand over: full / agenda / brief.
    """
    f = task_level()
    if f >= TASK_BRIEF:
        return 'brief'
    if f >= TASK_AGENDA:
        return 'agenda'
    return 'full'


def stage_visible() -> bool:
    """本场分拍表要不要给演员看（只有 `full` 给）。"""
    return frame_scope() == 'full'


def temperature() -> float:
    """这一拍决策的采样温度（任务侧）。"""
    return TEMP_LOW + (TEMP_HIGH - TEMP_LOW) * task_level()


def license_line() -> str:
    """**任务侧的许可**：这一拍由人物自己定。低任务规训时返回空串。

    ★★★ 为什么必须有这一段，而不只是"少给几条约束"
    本项目的实测教训：**把"必须 X"删掉之后，模型不是变得自由，而是变得不动。**
    ⇒ 松绑必须**成对**：少给一条禁令，就补一句许可。许可写三件事：
      ① 上面那些是什么（发生过的事 / 今天要办的事，**不是台词提示**）；
      ② 这一拍由什么决定（只有三样：我是谁、我要什么、刚才谁对我说了什么）；
      ③ 允许什么（不回话 / 走开 / 问一件跟眼前无关的事）—— 并**明确排除**
         "替别人说话"和"说出你不知道的事"，因为那是坏掉，不是自由。

    ★★★ 2026-10-21 补强（用户："约束/许可 47:8 这个比例要不要处理一下"）
    ------------------------------------------------------------------
    实测过一遍演员提示词：**约束词 47 处、许可 8 处 = 5.9 : 1**。
    比例失衡的后果不是"读起来凶"，而是**模型趋于保守** —— 每一句禁令都在暗示
    "保险的做法是别动"，而许可只说了"你可以不回话"，等于把"不动"也说成了一种允许。
    ⇒ 这一版补的是**最缺的那半边：允许他做错、允许他不讨人喜欢、允许他偏离今天的目标**。
      三条都对着实测过的毛病（人物变成"礼貌的传声筒"）：
      · ⑤ **允许他不讨人喜欢**：实测稿子里所有人物都太得体，冲突只能靠情节硬推；
      · ⑥ **允许他这次办不成**：以前"必须推进主线"被读成"这一拍必须办成事"，
        于是每人都在"完成 KPI"，没有一个会失败 —— 而失败才是戏；
      · ⑦ **允许他理解错**：接话时永远接得准，读者感觉不到"两个人在各想各的"。
    ⚠ 仍然**只保留两条禁令**（替别人说话 / 说他不可能知道的事）——
      许可再多也不许把这两条冲掉，它们不是规训，是世界的物理法则（见模块开头）。
    ⚠ 低规训档（`f < TASK_AGENDA`）仍然返回空串：那一档人物该跟着剧本走，
      给许可只会跟剧本打架。
    [EN] The task-side permission. Measured lesson: deleting "must X" makes the model **stop**
    [EN] rather than free. So unbinding is paired: one ban removed, one permission added.
    [EN] ★★★ Strengthened 2026-10-21 (user: "should the 47:8 constraint/permission ratio be
    [EN] handled?"). Measured: the actor prompt has **47 constraint words vs 8 permission words =
    [EN] 5.9:1**. The consequence is not "it reads harsh" but **the model turns conservative** --
    [EN] every ban whispers "the safe move is to do nothing", while the only permission on offer was
    [EN] "you may not answer", which effectively blesses inaction too.
    [EN] => This version adds the half that was missing: **allowed to be wrong, allowed to be
    [EN] unlikable, allowed to fail at today's goal**. Each targets a measured defect (characters
    [EN] degrading into polite mouthpieces): ⑤ everyone reads too well-mannered, so conflict has to be
    [EN] forced by plot; ⑥ "must advance the mainline" was read as "must succeed this beat", so nobody
    [EN] ever fails -- and failure is where the drama is; ⑦ replies always land perfectly, so the
    [EN] reader never feels "two people thinking past each other".
    [EN] ⚠ Still **only two bans** (speaking for others / knowing the impossible) -- no amount of
    [EN] permission may wash those out; they are not discipline but the world's physics.
    [EN] ⚠ The low-discipline band still returns '' (there the character should follow the script).
    """
    f = task_level()
    if f < TASK_AGENDA:
        return ''
    out = ['\n[没人替你决定这一拍]',
           '- 上面那些是**已经发生过的事**和**你今天要办的事**，不是台词提示。',
           '- 这一拍做什么，只有三样说了算：① 你是谁 ② 你此刻最想要什么、最缺什么 '
           '③ 刚才谁对你说了什么。']
    if f >= TASK_BRIEF:
        out.append('- 今天那件事**推不推进、怎么推进，你自己判断** —— 你觉得现在不是时候，'
                   '就先不推。')
    out.append('- 你可以不回话、可以走开、可以突然问一件跟眼前无关的事 —— '
               '只要那件事**对你**要紧。')
    # ── 2026-10-21 补的三条许可（对着"人物变成礼貌的传声筒"这个实测毛病）──
    out.append('- 你可以**不讨人喜欢**：可以说难听的话、可以小气、可以在这个时候不合时宜。'
               '**不用**照顾读者的观感，也不用维持一个体面形象。')
    out.append('- 你可以**这一次办不成**：「今天要办的事」是你想办的，不是必须办成的。'
               '办砸、办到一半、临时改主意，都是你这个人的一部分。')
    out.append('- 你可以**理解错**：别人那句话你可以听岔、可以只听见一半、可以往最坏处想。'
               '你不需要每次都接得准。')
    out.append('- 上面这些**都不算跑题**。跑题只有一种：做了一件**你自己也不会做**的事。')
    out.append('- ⚠ 不许的只有两样：替别人说话；说出你不可能知道的事。'
               '**其余都不算越界。**')
    return '\n'.join(out)


# ══════════════════════════════════════════════════════════════
#  文笔规训
# [EN] Prose discipline
# ══════════════════════════════════════════════════════════════
def deai_items(base: int) -> int:
    """去 AI 清单**每类列几个词**（`style/deai.prompt_block(per_kind=…)`）。

    三档：严格 = `base`（与用户原配置一致，不擅自加）／标准 = 约 3/4／松 = 约 1/2（至少 2 条）。

    ⚠ **不降到 0**：0 条 = 提示词里完全不提禁词 ⇒ 模型会大量写出「不禁」「仿佛」
      「五味杂陈」，而事后审计只能**发现问题、救不回句子**。
      2 条是"还知道有这回事"的下限。
    ⚠ 这里少列 ≠ 事后不查：`DEAI_STRIP` 与落盘审计**不在这个旋钮的控制范围内**。
    [EN] How many words per category the de-AI list shows. Strict = `base`; standard ~3/4; loose
    [EN] ~1/2 (at least 2). ⚠ **Never 0**. ⚠ Fewer listed does NOT mean less auditing.
    """
    b = max(0, int(base or 0))
    if b == 0:
        return 0
    f = style_level()
    if f >= STYLE_LOOSE:
        return max(2, b // 2)
    if f >= STYLE_STRICT:
        return max(3, (b * 3) // 4)
    return b


def distance_forced() -> bool:
    """心理距离档要不要**强制**（`supervisor.distance_for` 算出来的那一档）。

    松文笔时不再强制 ⇒ 由演员自己决定这一拍往里钻还是往外拉。
    ⚠ 不强制 ≠ 不提示：松档仍然会说"这一拍的距离由你定"（见 `style_license`），
      否则模型会退回默认的"每句都带一点心声"（那是最平的一种）。
    [EN] Whether the psychological distance is enforced. ⚠ Not enforced != not mentioned.
    """
    return style_level() < STYLE_LOOSE


def cot_full() -> bool:
    """思维链骨架给完整版还是精简版。

    精简版只留"这一句成不成立"那一问 —— 其余几问（我要什么 / 刚才那句对我做了什么 /
    该说多长）在松档交给模型自己。
    ⚠ 精简**不等于不要**：完全不给思维链时，决策会退化成关键词反应（实测过）。

    ⚠⚠ 阈值是 `STYLE_LOOSE`，**不是 `STYLE_STRICT`**（2026-10-19 判据 B2 抓出来的）：
      第一版写成 `< STYLE_STRICT`，于是**中档就已经精简**了 —— 而配置注释与界面上
      写的都是"中档：思维链五问，只有松档才精简"。表现就是：用户把旋钮从 0 拉到 50，
      以为只少了几个禁词，实际连思维链也少了一半。
      这正是本项目记过的"阈值写错一档，行为差一整档"。
    [EN] Full CoT skeleton or a trimmed one. ⚠ Trimmed != removed.
    [EN] ⚠⚠ The threshold is `STYLE_LOOSE`, **not `STYLE_STRICT`**: the first version used the
    [EN] latter, so the middle band already trimmed it -- while the config comment and the UI both
    [EN] say "middle: five questions, only the loose band trims". The user would move the knob from
    [EN] 0 to 50 expecting a few fewer banned words and lose half the skeleton instead.
    """
    return style_level() < STYLE_LOOSE


def tic_quota() -> bool:
    """口癖配额（"这一场已经用了 N 次" + 禁令）要不要挂。

    只在**最松**那一档关掉（那时作者要的是"别管我"）。
    ⚠ 关掉之后口癖会回弹到每句都带 —— 2026-10-19 实测：34 拍里同一句口头禅用了 6 次。
      这是这个开关的**已知代价**，界面上必须写出来。
    [EN] Whether the tic quota is attached. Off only in the **loosest** band.
    [EN] ⚠ With it off the tic bounces back to every line (measured: 6 uses in 34 beats).
    """
    return style_level() < STYLE_LOOSE


def style_license() -> str:
    """**文笔侧的许可**：可以写得不那么整齐。最严格档返回空串。

    ★★★ 这一段要防的是一种很具体的误解：**"松文笔"被理解成"允许 AI 腔"**。
    那两件事相反 —— AI 腔恰恰是**最不讲究**的写法（套话、整齐、面面俱到）。
    所以要同时说清三件事：
      ① 松的是什么：句长、段落节奏、敢不敢留白/议论/写野一点；
      ② **不是**什么：不是放宽禁词（那些词是毛病，不是风格）；
      ③ 唯一不许变的：心声第一人称、不替别人说话。
    [EN] The prose-side permission. ★★★ Guards against "loose prose = AI prose allowed" -- those
    [EN] are opposites, since AI prose is the **least** careful writing. States what is loosened,
    [EN] what is not (forbidden words), and the one thing that never changes.
    """
    f = style_level()
    if f < STYLE_STRICT:
        return ''
    out = ['\n[这一拍的字，可以不那么整齐]',
           '- 句子可以长可以短，**不必**每句都短、都利落；段落节奏由这一拍的情绪定。',
           '- 可以留白（写完就停，不解释）；可以插一句议论；可以写得**野一点**。']
    if f >= STYLE_LOOSE:
        out.append('- 这一拍的距离（贴近 / 中间 / 拉远）**由你定** —— 你觉得该往里钻就钻，'
                   '该拉远就拉远，不必跟着哪一档走。')
    out.append('- ⚠ 松的是**句法与节奏**，**不是**禁词表：那些词是毛病不是风格 '
               '（禁词照旧会在落盘时被查出来）。')
    out.append('- ⚠ 有一条永远不变：心声**第一人称**，不替别人说话、不写别人心里的事。')
    return '\n'.join(out)


def summary() -> str:
    """一句话说明当前两个档位（给日志/界面用，不进提示词）。"""
    t = task_level()
    s = style_level()
    tn = '照剧本演' if t < TASK_AGENDA else ('只给要办的事' if t < TASK_BRIEF else '只给议程')
    sn = '很讲究' if s < STYLE_STRICT else ('标准' if s < STYLE_LOOSE else '松')
    return f'任务规训 {t * 100:.0f}（{tn}）／文笔规训 {s * 100:.0f}（{sn}）'
