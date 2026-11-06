# -*- coding: utf-8 -*-
"""真机验证：LLM 能力配置 + 启动校验 + 全局消息框。

三部分：
  A. **识别**：模型名 → 能力表（聊天模型 / 推理模型 / 出图模型 / 认不出的）。
  B. **纠偏**：`.env` 里的声明与模型不符时，`check_capabilities()` 是否
     ① 报告出来；② 以模型为准改回；③ 真的落到 `.env`；④ 消息里说清依据与"需重启"。
     还有两条推论：三档**取交集**、认不出**不猜**。
  C. **真机 GUI**：开始界面有消息框 → 启动校验的消息出现在框里 →
     天机对话框里有四项能力开关 + 重启提示 → 改一项保存 → 消息框报「需要重启」。
     再验两条**接线**：能力关掉时 `ai_available()` 直接拦下（不发请求）、
     router 按能力组装请求体（推理模型不发 temperature、JSON 模式发 response_format、
     不认 system 就并进 user）。

产出 `assets/screenshots/llm_caps_*.png` + `llm_caps_report.json`。

跑法：
    .venv/Scripts/python tools/verify_llm_caps.py              # 全部
    .venv/Scripts/python tools/verify_llm_caps.py --logic-only  # 只跑 A/B（不弹窗）
    NWS_LANG=en .venv/Scripts/python tools/verify_llm_caps.py   # 英文界面（断言走 t()，双语都过）

注：**能力校验自己拼的那几句**（「已改回」「需要重启」）由 `llm/capabilities.py`
用中文拼成（含动态模型名，不经过 i18n），所以中英文界面下都是中文；
涉及它们的断言写中文是**正确**的，其余断言一律走 `t()` 或读控件自己的值。

⚠️ 本脚本会**把 `.env` 的写盘路径重定向到临时文件**（`Config.redirect_save`）再跑纠偏，
绝不碰用户的真 `.env`。

English:
Real-machine verification: LLM capability configuration + startup validation + global message
box.
Three parts:
  A. **Identification**: model name -> capability table (chat model / reasoning model / image-generation model / unrecognized).
  B. **Correction**: when the declaration in `.env` doesn't match the model, does `check_capabilities()`
     ① report it; ② correct it back based on the model; ③ actually persist it to `.env`; ④ state the basis and "needs restart" in the message.
     Plus two corollaries: the three tiers **take the intersection**, unrecognized **don't guess**.
  C. **Real-machine GUI**: the start screen has a message box -> the startup validation message appears in the box ->
     the Tianji dialog has four capability switches + restart prompt -> change one and save -> the message box reports "needs restart".
     Then verify two **wirings**: when a capability is off, `ai_available()` blocks it directly (no request sent),
     the router assembles the request body by capability (reasoning models don't send temperature, JSON mode sends response_format,
     if system is unrecognized, merge it into user).
Produce `assets/screenshots/llm_caps_*.png` + `llm_caps_report.json`.
How to run:
    .venv/Scripts/python tools/verify_llm_caps.py              # all
    .venv/Scripts/python tools/verify_llm_caps.py --logic-only  # only run A/B (no popup)
    NWS_LANG=en .venv/Scripts/python tools/verify_llm_caps.py   # English UI (assertions go through t(), both languages pass)
Note: **the few sentences the capability validation assembles itself** ("changed back", "needs
restart") are assembled by `llm/capabilities.py`
in Chinese (including dynamic model names, not going through i18n), so they are Chinese under
both Chinese and English UIs;
assertions involving them are **correct** when written in Chinese; all other assertions go
through `t()` or read the control's own value.
⚠️ This script will **redirect the `.env` write path to a temporary file**
(`Config.redirect_save`) before running the correction,
and never touches the user's real `.env`.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

import config as CFG_MOD                                  # noqa: E402
from config import CFG, restart_keys                      # noqa: E402

# ── 关键：先把 .env 写盘路径挪到临时文件 ──
# 纠偏是**真的会写 .env** 的（那是它的设计目标），验证脚本要是写在用户
# 的真配置上，跑一次测试就改一次用户配置 —— 这是绝对不能接受的。
# [EN] ── Critical: first move the .env write path to a temp file ──
# [EN] Correction really does write .env (that is its design goal), so if the verification script
# [EN] writes to the user's
# [EN] real config, every test run modifies the user's config -- this is absolutely unacceptable.
#
# ⚠ 用 `Config.redirect_save`（进程内、显式、优先级最高），**不要**去改
#   `CFG_MOD.ENV_PATH` 这个模块全局（2026-10-06 改）：
#   回归器会给每个子进程设 `NWS_ENV_SINK`（见 `config.env_sink_path()`），
#   而它的优先级**高于** `ENV_PATH` —— 于是"改 ENV_PATH"这招在回归里会失效，
#   本脚本第 168 行读 `_TMP_ENV` 就会读到空 → 「.env 被真的改写了」**假红**。
#   `redirect_save` 排在 `NWS_ENV_SINK` 前面，两边各说各的、互不抢道。
# [EN] ⚠ Use `Config.redirect_save` (in-process, explicit, highest priority), **do not** modify
# [EN] the `CFG_MOD.ENV_PATH` module global (changed 2026-10-06):
# [EN] The regression harness sets `NWS_ENV_SINK` for each subprocess (see `config.env_sink_path()`),
# [EN] and its priority is **higher than** `ENV_PATH` -- so the "modify ENV_PATH" trick fails in
# [EN] regressions,
# [EN] and this script reading `_TMP_ENV` at line 168 will read empty -> ".env was actually rewritten"
# [EN] **false red**.
# [EN] `redirect_save` is ordered before `NWS_ENV_SINK`, each handles its own path without contention.
_TMP_ENV = Path(tempfile.mkdtemp(prefix='nws_caps_env_')) / '.env'
CFG_MOD.Config.redirect_save = _TMP_ENV

CFG.set('MOCK_LLM', 'true')          # 零成本；能力校验不看这一项
# ★★★ 2026-10-22：下面有一组要**打桩 client 看真实请求体**（`_client = fake`），
#   而缓存命中时根本不发请求 ⇒ 抓到的 body 是 None ⇒ 判据假红；
#   而且打桩答复会被写进跨会话共享缓存、留在用户机器上。
#   同批修了 `verify_progress_eval` / `verify_thinking_mode`（A1 就是被这类残留判红的）。
# [EN] ★★★ 2026-10-22: a group below **stubs the client to inspect the real request body**; a cache
# [EN] hit sends nothing => the captured body is None => a false red; and the stubbed reply would be
# [EN] written into the cross-session shared cache and left on the user's machine.
CFG.set('LLM_DEDUP_ENABLED', 'false')
CFG.set('LLM_CACHE_ENABLED', 'false')
# 界面语言：跟其他验证脚本一个规矩 —— `NWS_LANG=en` 跑英文界面。
# 断言一律走 `t()` 或"读控件自己的值"，不写死中文文案（写死了改文案就假失败）。
# [EN] Zero cost; capability check does not look at this item
# [EN] UI language: same rule as other verification scripts -- `NWS_LANG=en` runs the English UI.
# [EN] Assertions always go through `t()` or "read the control's own value", never hardcode Chinese
# [EN] text (hardcoding makes text changes cause false failures).
_lang = os.environ.get('NWS_LANG', 'zh')
CFG.set('LANGUAGE', _lang)

from llm import capabilities as CAP                        # noqa: E402
from llm import router as R                                # noqa: E402
from i18n import t, set_lang                               # noqa: E402
set_lang(_lang)
import verify_ui_common as VU                              # noqa: E402

OUT = APP_DIR / 'assets' / 'screenshots'
OUT.mkdir(parents=True, exist_ok=True)
SUFFIX = '' if _lang == 'zh' else f'_{_lang}'
report: dict = {'steps': [], 'produced': {}, 'lang': _lang}


def rec(name: str, ok: bool, detail: str = '') -> bool:
    report['steps'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)})
    print(f'  {"[OK]  " if ok else "[FAIL]"} {name}'
          + (f'  — {detail}' if detail else ''), flush=True)
    return bool(ok)


def head(t: str) -> None:
    print(f'\n── {t} ──', flush=True)


def setup_cfg(front='deepseek-chat', daily=None, cheap=None, img=''):
    """把三档模型与出图模型摆好（只改内存）。

    `daily` / `cheap` 传 `None` = 与 `front` 相同（三档同一模型是最常见的配置）。
    踩过的坑：一开始写成 `daily='deepseek-chat'` 的固定默认值，于是
    `setup_cfg('my-private-proxy')` 只改了华彩档，日常/摘要还是 deepseek-chat ——
    测试以为在测「认不出的模型」，实际上三档里有两档认得出来，
    结论自然对不上。**默认值要表达"跟前面一样"，别写死一个具体模型名。**
    
        English:
    Set up the three tiers and the image-generation model (in memory only).
        `daily` / `cheap` passing `None` = same as `front` (all three tiers being the same model is the most common configuration).
        Pitfall encountered: initially written as a fixed default value `daily='deepseek-chat'`, so
        `setup_cfg('my-private-proxy')` only changed the premium tier, while daily/summary were still deepseek-chat --
        the test thought it was testing an "unrecognized model", but in fact two of the three tiers were recognized,
        so the conclusion naturally didn't match. **The default value should express "same as before", don't hardcode a specific model name.**
    """
    CFG.set('MODEL_FRONT', front)
    CFG.set('MODEL_DAILY', front if daily is None else daily)
    CFG.set('MODEL_CHEAP', front if cheap is None else cheap)
    CFG.set('IMAGE_AI_MODEL', img)


# ══════════════════════════════════════════════════════════════
#  A. 识别
# [EN] A. Recognition
# ══════════════════════════════════════════════════════════════
def test_detect() -> bool:
    ok = True
    cases = [
        ('deepseek-chat',       {'LLM_CAP_IMAGE': False, 'LLM_CAP_REASONING': False,
                                 'LLM_CAP_JSON_MODE': True, 'LLM_CAP_SYSTEM_ROLE': True}),
        ('deepseek-reasoner',   {'LLM_CAP_IMAGE': False, 'LLM_CAP_REASONING': True,
                                 'LLM_CAP_JSON_MODE': True, 'LLM_CAP_SYSTEM_ROLE': True}),
        ('gpt-4o',              {'LLM_CAP_IMAGE': False, 'LLM_CAP_REASONING': False,
                                 'LLM_CAP_JSON_MODE': True, 'LLM_CAP_SYSTEM_ROLE': True}),
        # o 系列是推理模型，且不接受 system 角色
        # [EN] o series are reasoning models, and do not accept the system role
        ('o3-mini',             {'LLM_CAP_IMAGE': False, 'LLM_CAP_REASONING': True,
                                 'LLM_CAP_JSON_MODE': True, 'LLM_CAP_SYSTEM_ROLE': False}),
        ('qwen-max',            {'LLM_CAP_IMAGE': False, 'LLM_CAP_REASONING': False,
                                 'LLM_CAP_JSON_MODE': True, 'LLM_CAP_SYSTEM_ROLE': True}),
        ('glm-4-flash',         {'LLM_CAP_IMAGE': False, 'LLM_CAP_REASONING': False,
                                 'LLM_CAP_JSON_MODE': True, 'LLM_CAP_SYSTEM_ROLE': True}),
        # 出图模型：能出图，但不会聊天
        # [EN] Image models: can generate images, but cannot chat
        ('gpt-image-1',         {'LLM_CAP_IMAGE': True, 'LLM_CAP_REASONING': False,
                                 'LLM_CAP_JSON_MODE': False, 'LLM_CAP_SYSTEM_ROLE': True}),
        ('dall-e-3',            {'LLM_CAP_IMAGE': True, 'LLM_CAP_REASONING': False,
                                 'LLM_CAP_JSON_MODE': False, 'LLM_CAP_SYSTEM_ROLE': True}),
    ]
    for name, want in cases:
        got, label = CAP.detect(name)
        ok &= rec(f'识别 {name} → {label}', got == want,
                  json.dumps(got, ensure_ascii=False))
    # 认不出来的**不能猜**
    # [EN] What cannot be recognized **must not be guessed**
    for name in ('my-private-proxy', 'internal-llm-v2', ''):
        got, label = CAP.detect(name)
        ok &= rec(f'认不出 {name or "(空)"} → 不猜', got == {} and label == '',
                  f'{got} / {label!r}')
    report['detected_models'] = {n: CAP.detect(n)[0] for n, _ in cases}
    return ok


# ══════════════════════════════════════════════════════════════
#  B. 纠偏
# [EN] B. Correction
# ══════════════════════════════════════════════════════════════
def test_check(apply: bool) -> bool:
    ok = True

    # ① 填错了：deepseek-chat 标成"支持文生图"、声明"不支持 JSON 模式"
    # [EN] ① Filled in wrong: deepseek-chat marked as "supports text-to-image", declares "does not support
    # [EN] JSON mode"
    setup_cfg('deepseek-chat')
    CFG.set('LLM_CAP_IMAGE', 'true')          # 错
    CFG.set('LLM_CAP_JSON_MODE', 'false')     # 错
    CFG.set('LLM_CAP_REASONING', '')          # 未声明
    CFG.set('LLM_CAP_SYSTEM_ROLE', 'true')    # 对
    # [EN] wrong
    # [EN] wrong
    # [EN] not declared
    # [EN] right

    before_env = _TMP_ENV.read_text(encoding='utf-8') if _TMP_ENV.exists() else ''
    rep = CAP.check_capabilities(CFG, apply=apply)
    keys = [f.key for f in rep.fixes]
    ok &= rec('文生图与模型不符 → 报出一条修正',
              'LLM_CAP_IMAGE' in keys, str(keys))
    ok &= rec('JSON 模式与模型不符 → 报出一条修正',
              'LLM_CAP_JSON_MODE' in keys, str(keys))
    ok &= rec('未声明的项 → 自动填入（也算一条）',
              'LLM_CAP_REASONING' in keys, str(keys))
    ok &= rec('本来就对、且已声明的项 → 不动它',
              'LLM_CAP_SYSTEM_ROLE' not in keys, str(keys))
    fix_img = next((f for f in rep.fixes if f.key == 'LLM_CAP_IMAGE'), None)
    ok &= rec('修正依据写清了是哪个模型（且同名不重复三遍）',
              bool(fix_img) and fix_img.model == 'deepseek-chat',
              fix_img.model if fix_img else '')
    msgs = [m for m, _ in rep.messages()]
    ok &= rec('消息里提示了需要重启',
              any('重启' in m for m in msgs), ' / '.join(msgs)[:120])
    ok &= rec('消息里没有 Markdown 标记（** 会原样显示出来）',
              not any('**' in m for m in msgs))

    if apply:
        after_env = _TMP_ENV.read_text(encoding='utf-8')
        ok &= rec('.env 被真的改写了',
                  after_env != before_env and after_env != '',
                  f'{len(before_env)} → {len(after_env)} 字节')
        ok &= rec('.env 里 LLM_CAP_IMAGE=false',
                  _env_line('LLM_CAP_IMAGE') == 'false',
                  _env_line('LLM_CAP_IMAGE'))
        ok &= rec('.env 里 LLM_CAP_JSON_MODE=true',
                  _env_line('LLM_CAP_JSON_MODE') == 'true',
                  _env_line('LLM_CAP_JSON_MODE'))
        ok &= rec('.env 里 LLM_CAP_REASONING=false（自动填入）',
                  _env_line('LLM_CAP_REASONING') == 'false',
                  _env_line('LLM_CAP_REASONING'))
        ok &= rec('内存里的 CFG 也跟着变了',
                  CFG.b('LLM_CAP_IMAGE') is False and CFG.b('LLM_CAP_JSON_MODE') is True,
                  f"img={CFG.b('LLM_CAP_IMAGE')} json={CFG.b('LLM_CAP_JSON_MODE')}")

    # ② 三档取交集：华彩用 chat、摘要用 reasoner → 推理模型判为"不支持"
    # [EN] ② Intersection of three tiers: chat for polishing, reasoner for summaries -> reasoning model
    # [EN] judged as "not supported"
    setup_cfg('deepseek-chat', 'deepseek-chat', 'deepseek-reasoner')
    for k in CAP.CAP_KEYS:
        CFG.set(k, 'true')
    rep2 = CAP.check_capabilities(CFG, apply=False)
    ok &= rec('三档不一致 → 推理模型取最保守（不支持）',
              rep2.detected.get('LLM_CAP_REASONING') is False,
              str(rep2.detected.get('LLM_CAP_REASONING')))
    # 判 False 是因为 chat 两档不支持；提示里该点名这两个模型，并说明为什么取保守值
    # [EN] Judged False because the two chat tiers do not support it; the hint should name these two models
    # [EN] and explain why the conservative value is taken
    ok &= rec('三档不一致时说明了是哪一档、以及为何取保守值',
              any('deepseek-chat' in n and '保守' in n for n in rep2.notes),
              ' / '.join(rep2.notes)[:140])

    # ③ 认不出的模型：保留用户填的值，只提示
    # [EN] ③ Unrecognized model: keep the user-filled value, only warn
    setup_cfg('my-private-proxy')
    CFG.set('LLM_CAP_IMAGE', 'true')
    CFG.set('LLM_CAP_REASONING', 'true')
    CFG.set('LLM_CAP_JSON_MODE', 'true')
    CFG.set('LLM_CAP_SYSTEM_ROLE', 'true')
    rep3 = CAP.check_capabilities(CFG, apply=False)
    ok &= rec('认不出的模型 → 一条都不改',
              not rep3.fixes, str([f.key for f in rep3.fixes]))
    ok &= rec('认不出的模型 → 有"未能识别/自行确认"的提示',
              any('未能识别' in n for n in rep3.notes), ' / '.join(rep3.notes)[:140])
    rep3b = CAP.check_capabilities(CFG, apply=True)
    ok &= rec('认不出时 apply 也不动内存里的值',
              CFG.b('LLM_CAP_IMAGE') is True and not rep3b.fixes)

    # ④ 出图模型决定 LLM_CAP_IMAGE
    # [EN] ④ Image model determines LLM_CAP_IMAGE
    setup_cfg('deepseek-chat', img='gpt-image-1')
    CFG.set('LLM_CAP_IMAGE', 'false')
    rep4 = CAP.check_capabilities(CFG, apply=False)
    ok &= rec('配了 gpt-image-1 → 文生图判为支持',
              rep4.detected.get('LLM_CAP_IMAGE') is True,
              str(rep4.detected.get('LLM_CAP_IMAGE')))
    ok &= rec('据此把声明改成 true 并说明依据',
              any(f.key == 'LLM_CAP_IMAGE' and f.model == 'gpt-image-1'
                  for f in rep4.fixes),
              str([(f.key, f.model) for f in rep4.fixes]))

    # ⑤ 首次启动（四项都没写过）→ 只出一条 info，**不许刷警告**
    # 这是"初始化"不是"纠错"。若按纠错报，用户一开程序就是四条警告 ——
    # 那种噪音会把他练成不看警告。
    # [EN] ⑤ First launch (none of the four items written) -> emit only one info, **no warnings allowed**
    # [EN] This is "initialization", not "correction". If reported as correction, the user sees four
    # [EN] warnings the moment they open the program --
    # [EN] that kind of noise trains them to ignore warnings.
    setup_cfg('deepseek-chat')
    for k in CAP.CAP_KEYS:
        CFG.set(k, '')
    rep5 = CAP.check_capabilities(CFG, apply=False)
    m5 = rep5.messages()
    ok &= rec('首次启动（四项全未声明）→ 一条警告都没有',
              all(level == 'info' for _t, level in m5),
              ' / '.join(f'[{lv}]{t}' for t, lv in m5)[:140])
    ok &= rec('首次启动 → 只合成一条「自动填入」，不是四条',
              sum(1 for t, _lv in m5 if '自动填入' in t) == 1,
              ' / '.join(t for t, _lv in m5)[:140])
    ok &= rec('首次启动 → 不提示"需要重启"（能力项是自动填的，没用错）',
              not any('重启' in t for t, _lv in m5))

    report['check_report'] = rep.as_dict()
    return ok


def _env_line(key: str) -> str:
    if not _TMP_ENV.exists():
        return ''
    for ln in _TMP_ENV.read_text(encoding='utf-8').splitlines():
        if ln.startswith(key + '='):
            return ln.split('=', 1)[1].strip()
    return ''


# ══════════════════════════════════════════════════════════════
#  B2. 接线：出图判据 / 请求体组装
# [EN] B2. Wiring: image criterion / request body assembly
# ══════════════════════════════════════════════════════════════
def test_output_caps() -> bool:
    """D. **输出上限表**：认不出的模型会退回全局兜底，兜底值只对某一两个模型安全。

    ★★★ 起因（2026-10-18 真事故）：把演员换成 `doubao-seed-character-251128` 之后，
      一个 1 拍的推演**整拍空掉**：
        `「祥子」决策失败，本轮降级为 wait：Client error '400 Bad Request'`
        `第 1 天落盘（剧本）：{'幕数': 1, '对白': 0, '动作': 0, '旁白': 0, ...}`
      真因不是模型、不是提示词 —— 是 `MAX_OUTPUT_TOKENS` 里**没有豆包的条目**，
      `max_output_tokens()` 返回 `None`，调用方退回 `LLM_MAX_TOKENS_FALLBACK`，
      而那个值当时是 **819200**（为 hy3 设的；`hy3` 实测确实收）。
      豆包的上限是 32768 ⇒ **每一发都被 400 拒掉**。
    ⚠ 这类 bug 的形状很坏：**模型看起来"能用"**（短请求一测就通），
      只有真正跑起来才炸，而且炸的方式是"人物不出声"，不像报错。

        English:
    D. **Output-cap table**: an unrecognized model falls back to the global default, and that
    default is only safe for one or two models.
        ★★★ Origin (a real incident on 2026-10-18): after switching the actor to
        `doubao-seed-character-251128`, a 1-tick run produced **an entirely empty beat**:
        `「祥子」决策失败，本轮降级为 wait：Client error '400 Bad Request'` /
        `第 1 天落盘（剧本）：{'幕数': 1, '对白': 0, ...}`.
        The cause was neither the model nor the prompt: `MAX_OUTPUT_TOKENS` had **no Doubao row**,
        so `max_output_tokens()` returned `None`, the caller fell back to
        `LLM_MAX_TOKENS_FALLBACK`, which at the time was **819200** (set for hy3, which really does
        accept it). Doubao's ceiling is 32768, so **every request was rejected with 400**.
        ⚠ The shape of this bug is nasty: **the model looks usable** (a short request succeeds),
        it only explodes when the simulation really runs, and it explodes as "the character goes
        silent", which does not look like an error.
    """
    ok = True
    import llm.router as R

    # D1 豆包系**登记了**（返回 None 就意味着会退回那个 819200 的兜底），
    #   而且落在**两端都安全**的区间里：
    #     · 上界 = 实测天花板（超了整发 400，这是本次事故）
    #     · 下界 8192 —— 再小就是"写一半被砍"，另一种事故（2026-10-14 那回）
    #   ⚠ 判 `<= 天花板` 而不是 `== 天花板`：本表的纪律是**猜小不猜大**
    #     （大了是硬 400，小了只是截断）。lite 实测能到 131072，但登记 32768 是**故意保守**，
    #     不该被判成错 —— 第一版写成 `==` 就红在这里，是判据自己太死。
    # [EN] D1 The Doubao family is registered (a `None` means falling back to that 819200 default),
    # [EN] and the value sits in a **safe interval on both ends**: upper bound = the measured
    # [EN] ceiling (exceeding it rejects the whole request -- this incident); lower bound 8192 --
    # [EN] anything smaller means "cut off mid-way", the other incident (2026-10-14).
    # [EN] ⚠ Assert `<= ceiling`, not `== ceiling`: the table's discipline is **guess low, not
    # [EN] high** (too high is a hard 400, too low merely truncates). lite measurably accepts
    # [EN] 131072, but registering 32768 is **deliberately conservative** and should not be graded
    # [EN] wrong -- the first version used `==` and went red right here: the criterion was too rigid.
    for m, ceiling in (('doubao-seed-character-251128', 32768),
                       ('doubao-seed-2-1-lite-260915', 131072)):
        got = CAP.max_output_tokens(m)
        ok &= rec(f'D1 ★★★ `{m}` 已登记且在安全区间内（8192 ≤ 值 ≤ 实测天花板 {ceiling}）',
                  got is not None and 8192 <= got <= ceiling, f'got={got!r}')

    # D2 ★★★ 成对：hy3 还是 819200。不许为了修豆包把**所有**模型一起压小
    #   —— 那会把 hy3 从"能写 1856 字"变成"写一半被砍"（2026-10-14 刚修过这个）
    # [EN] ★★★ Pair: hy3 stays at 819200. Do not shrink **every** model just to fix Doubao --
    # [EN] that would take hy3 from "can write 1856 chars" back to "cut off mid-way"
    # [EN] (fixed on 2026-10-14).
    ok &= rec('D2 ★★★ 成对：`hy3` 仍是 819200（没被一刀切压小）',
              CAP.max_output_tokens('hy3') == 819200,
              f'got={CAP.max_output_tokens("hy3")!r}')

    # D3 顺序：本表**按顺序取第一个命中**，`doubao-seed-character` 必须排在 `doubao` 前
    # [EN] D3 Order: the table takes the **first match**, so `doubao-seed-character` must precede `doubao`
    pats = [p for p, _v in CAP.MAX_OUTPUT_TOKENS]
    ok &= rec('D3 顺序正确：`doubao-seed-character` 排在 `doubao` 之前（否则永远匹配不到）',
              'doubao-seed-character' in pats and 'doubao' in pats
              and pats.index('doubao-seed-character') < pats.index('doubao'),
              f'{pats.index("doubao-seed-character") if "doubao-seed-character" in pats else -1}'
              f' < {pats.index("doubao") if "doubao" in pats else -1}')

    # D4 ★★★ **行为判**：真正发出去的那个数。只判表里写了什么是不够的 ——
    #   调用方走的是 `_effective_max_tokens()`，它会拿 `LLM_MAX_TOKENS_FALLBACK` 兜底。
    # [EN] D4 ★★★ **Behavioural**: the number actually sent. Checking the table alone is not
    # [EN] enough -- the caller goes through `_effective_max_tokens()`, which falls back to
    # [EN] `LLM_MAX_TOKENS_FALLBACK`.
    sent = R._effective_max_tokens('doubao-seed-character-251128', 'agent_decide', 1200)
    ok &= rec('D4 ★★★ 豆包**实际发出的** max_tokens ≤ 32768（不然整发 400、那一拍空掉）',
              sent <= 32768, f'sent={sent}')

    # D5 成对：hy3 实际发出的仍是它自己的上限（D4 不是靠"全局压小"过的）
    # [EN] D5 Pair: hy3 still sends its own ceiling (D4 did not pass by shrinking everything)
    sent_hy3 = R._effective_max_tokens('hy3', 'agent_decide', 1200)
    ok &= rec('D5 ★★ 成对：hy3 实际发出的仍是 819200', sent_hy3 == 819200, f'sent={sent_hy3}')

    return ok


def test_wiring() -> bool:
    ok = True
    from image_gen.ai import ai_available

    # ① 文生图：能力关掉 → 直接拦下，一次请求都不发
    # [EN] ① Text-to-image: capability off -> block directly, no request sent at all
    setup_cfg('deepseek-chat', img='gpt-image-1')
    CFG.set('MOCK_LLM', 'false')          # 让 ai_available 只按能力判断
    # [EN] Let ai_available judge only by capability
    CFG.set('LLM_API_KEY', 'sk-test')
    CFG.set('LLM_CAP_IMAGE', 'false')
    avail, why = ai_available()
    ok &= rec('能力=假 → ai_available 拦下，且原因点明文生图',
              avail is False and '文生图' in why and 'LLM_CAP_IMAGE' in why, why)
    CFG.set('LLM_CAP_IMAGE', 'true')
    avail2, why2 = ai_available()
    ok &= rec('能力=真 + 有模型 + 有 Key → 放行', avail2 is True, why2)
    # 聊天模型当出图模型：拦下（这就是"填错了也不至于每次 404"）
    # [EN] Chat model used as image model: block (this is "even if filled in wrong, it won't 404 every
    # [EN] time")
    CFG.set('IMAGE_AI_MODEL', 'deepseek-chat')
    r = CAP.check_capabilities(CFG, apply=False)
    ok &= rec('把聊天模型填成出图模型 → 校验会判为不支持',
              r.detected.get('LLM_CAP_IMAGE') is False,
              str(r.detected.get('LLM_CAP_IMAGE')))
    CFG.set('MOCK_LLM', 'true')
    CFG.set('LLM_API_KEY', '')

    # ② 请求体组装（假 client 抓包，不联网）
    # [EN] ② Request body assembly (fake client captures packets, no network)
    ok &= _test_request_body()

    # ③ system 合并是纯函数，单独测
    # [EN] ③ system merging is a pure function, test it separately
    merged = R._merge_system_into_user([
        {'role': 'system', 'content': '系统提示'},
        {'role': 'user', 'content': '正文'},
        {'role': 'assistant', 'content': '回话'},
    ])
    ok &= rec('不认 system 时：系统提示并进首条 user，且没有 system 角色了',
              merged[0]['role'] == 'user'
              and '系统提示' in merged[0]['content']
              and '正文' in merged[0]['content']
              and all(m['role'] != 'system' for m in merged),
              json.dumps(merged, ensure_ascii=False)[:120])
    same = R._merge_system_into_user([{'role': 'user', 'content': 'x'}])
    ok &= rec('没有 system 消息时原样返回（不做多余处理）',
              same == [{'role': 'user', 'content': 'x'}])

    # ④ 需要重启的项要覆盖 LLM 相关键
    # [EN] ④ Items requiring restart must cover LLM-related keys
    rk = restart_keys()
    want = {'LLM_BASE_URL', 'LLM_API_KEY', 'MODEL_FRONT', 'MODEL_DAILY', 'MODEL_CHEAP',
            'LLM_CAP_IMAGE', 'LLM_CAP_REASONING', 'LLM_CAP_JSON_MODE',
            'LLM_CAP_SYSTEM_ROLE', 'IMAGE_AI_MODEL', 'IMAGE_AI_SIZE'}
    ok &= rec('SPEC 里标了 restart 的项覆盖全部 LLM 配置', want <= rk,
              str(sorted(want - rk)))
    ok &= rec('界面外观类不需重启（UI_OPACITY 不在 restart 里）',
              'UI_OPACITY' not in rk)
    return ok


def _test_request_body() -> bool:
    """假 client 抓请求体：验 temperature / response_format / system 三件事。
        English:
    Fake client captures the request body: verify the three things temperature / response_format /
    system.
    """
    ok = True

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {'choices': [{'message': {'content': '{}'}}],
                    'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}

    class _Client:
        def __init__(self):
            self.body = None

        # ★ 2026-10-12：_real_call 现在**逐发**传 headers（多服务商），假客户端也要收下它。
        # [EN] 2026-10-12: _real_call now passes headers per request (several providers).
        async def post(self, url, json=None, headers=None, timeout=None):
            self.body = json
            return _Resp()

    async def _run():
        nonlocal ok
        loop = asyncio.get_running_loop()
        saved = (R.llm._client, R.llm._sem, R.llm._started, R.llm._loop)
        fake = _Client()
        R.llm._client = fake
        R.llm._sem = asyncio.Semaphore(4)
        R.llm._started = True
        R.llm._loop = loop
        CFG.set('MOCK_LLM', 'false')
        try:
            setup_cfg('deepseek-chat')
            # (a) 推理模型 → 不发 temperature
            # [EN] (a) Reasoning model -> do not send temperature
            CFG.set('LLM_CAP_REASONING', 'true')
            CFG.set('LLM_CAP_JSON_MODE', 'true')
            CFG.set('LLM_CAP_SYSTEM_ROLE', 'true')
            await R.llm.chat('front', [{'role': 'user', 'content': 'hi'}])
            ok &= rec('推理模型：请求体里没有 temperature',
                      'temperature' not in (fake.body or {}),
                      json.dumps(sorted((fake.body or {}).keys()), ensure_ascii=False))
            # (b) 支持 JSON 模式 → 带 response_format
            # [EN] (b) Supports JSON mode -> include response_format
            fake.body = None
            await R.llm.chat('front', [{'role': 'user', 'content': 'hi json'}],
                             json_mode=True)
            ok &= rec('JSON 模式：请求体带 response_format',
                      (fake.body or {}).get('response_format') == {'type': 'json_object'},
                      json.dumps((fake.body or {}).get('response_format'),
                                 ensure_ascii=False))
            # (c) 不支持 JSON 模式 → 退回提示词追加，且不带 response_format
            # [EN] (c) Does not support JSON mode -> fall back to appending to prompt, and do not include
            # [EN] response_format
            CFG.set('LLM_CAP_JSON_MODE', 'false')
            fake.body = None
            await R.llm.chat('front', [{'role': 'user', 'content': 'hi'}],
                             json_mode=True)
            ok &= rec('不支持 JSON 模式：改走提示词追加',
                      'response_format' not in (fake.body or {})
                      and 'JSON' in fake.body['messages'][-1]['content'],
                      fake.body['messages'][-1]['content'][-60:])
            # (d) 不支持 system → 请求体里看不到 system 角色
            # [EN] (d) Does not support system -> no system role visible in request body
            CFG.set('LLM_CAP_SYSTEM_ROLE', 'false')
            fake.body = None
            await R.llm.chat('front', [{'role': 'system', 'content': 'S'},
                                       {'role': 'user', 'content': 'U'}])
            roles = [m.get('role') for m in fake.body['messages']]
            ok &= rec('不认 system：请求体里没有 system 角色',
                      'system' not in roles and 'S' in fake.body['messages'][0]['content'],
                      str(roles))
            # (e) 非推理模型 → 正常发 temperature
            # [EN] (e) Non-reasoning model -> send temperature normally
            CFG.set('LLM_CAP_REASONING', 'false')
            fake.body = None
            await R.llm.chat('front', [{'role': 'user', 'content': 'x'}])
            ok &= rec('非推理模型：temperature 照常发送',
                      'temperature' in (fake.body or {}),
                      str((fake.body or {}).get('temperature')))
        finally:
            R.llm._client, R.llm._sem, R.llm._started, R.llm._loop = saved
            CFG.set('MOCK_LLM', 'true')

    asyncio.run(_run())
    return ok


# ══════════════════════════════════════════════════════════════
#  C. 真机 GUI
# [EN] C. Real GUI
# ══════════════════════════════════════════════════════════════
def walk(c, out: list, d: int = 0) -> None:
    if c is None or d > 40:
        return
    out.append(c)
    for a in ('controls', 'content', 'actions', 'title'):
        v = getattr(c, a, None)
        if isinstance(v, list):
            for x in v:
                walk(x, out, d + 1)
        elif v is not None and hasattr(v, '__class__'):
            walk(v, out, d + 1)


#: 「需要重启」的**语义锚点**：产品的措辞会变（见下面那两处注释），
#: 但"这句是提醒你重启"这件事不变。判据抓语义，不抄文案。
# [EN] : the **semantic anchor** of "requires restart": the product wording will change (see the two
# [EN] comments below),
# [EN] : but the fact that "this sentence is reminding you to restart" does not change. The criterion
# [EN] captures semantics, not copied text.
RESTART_HINT = '需要重启'


def _btn_label(ctrl) -> str:
    ct = getattr(ctrl, 'content', None)
    if isinstance(ct, __import__('flet').Text):
        return str(ct.value or '')
    return str(ct or '')


async def test_gui(page) -> bool:
    import flet as ft
    ok = True
    tmpdirs: list[Path] = []
    try:
        # **不换纯色背景**：本脚本的断言全部读控件树与文本，一个像素都不量，
        # 所以留着真背景反而更好 —— 截图是给人看的，水墨底比灰底体面。
        # （要量留白/间距的脚本才必须 `VU.patch_flat_background()`，见铁律 2。）
        # [EN] **Do not switch to a solid background**: this script's assertions all read the control tree and
        # [EN] text, not a single pixel is measured,
        # [EN] so keeping the real background is actually better -- screenshots are for humans, and an ink-wash
        # [EN] background looks more respectable than gray.
        # [EN] (Only scripts that measure whitespace/spacing must call `VU.patch_flat_background()`, see iron
        # [EN] rule 2.)
        tmpdirs.append(Path(tempfile.mkdtemp(prefix='nws_caps_proj_')))
        VU.isolate_projects_dir(tmpdirs[0])
        from gui.app_flet import NovelWorldApp

        # 故意制造一处不符：deepseek-chat 却声明支持文生图
        # [EN] Deliberately create one mismatch: deepseek-chat but declares support for text-to-image
        setup_cfg('deepseek-chat')
        CFG.set('LLM_CAP_IMAGE', 'true')
        CFG.set('LLM_CAP_JSON_MODE', 'true')
        CFG.set('LLM_CAP_REASONING', '')
        CFG.set('LLM_CAP_SYSTEM_ROLE', 'true')

        app = NovelWorldApp()
        app.main(page)                 # 内部会跑启动校验（写临时 .env）
        # [EN] Internally runs startup validation (writes temp .env)
        page.enable_screenshots = True
        page.update()
        await asyncio.sleep(2.0)

        async def shot(name: str) -> None:
            page.update()
            await asyncio.sleep(0.5)
            (OUT / (name[:-4] + SUFFIX + '.png')).write_bytes(
                await page.take_screenshot())

        # ── ① 开始界面有消息框，且里面有启动校验的话 ──
        # [EN] ── ① Start screen has a message box, and it contains startup validation text ──
        nodes: list = []
        for c in page.controls:
            walk(c, nodes)
        texts = [str(getattr(c, 'value', '') or '') for c in nodes
                 if isinstance(c, ft.Text)]
        joined = '\n'.join(texts)
        # 判"消息框渲染出来了"用**控件自己的值**去比对（语言无关），
        # 别去找「共 N 条」这种中文串 —— 英文界面下就假失败了。
        # [EN] To judge "the message box rendered", compare using **the control's own value**
        # [EN] (language-independent),
        # [EN] do not look for Chinese strings like "total N items" -- that would falsely fail under the
        # [EN] English UI.
        count_val = str(getattr(app._ui_msg.get('count'), 'value', '') or '')
        bar_mounted = any(c is app._ui_msg.get('bar') for c in nodes)
        ok &= rec('开始界面渲染出了消息框（那块框 + 计数都在控件树里）',
                  bar_mounted and bool(count_val)
                  and any(x.strip() == count_val.strip() for x in texts),
                  f'bar={bar_mounted} count={count_val!r}')
        # 消息框一条行只放得下**一条**，所以这里要验的是"挑哪一条"的规则：
        # 启动校验是一串消息，最后一条往往是「演示模式」这种 info；
        # 如果按"最新一条"显示，真正要紧的警告就被顶掉了（实测顶掉过一次）。
        # [EN] The message box can only fit **one** line per row, so what is verified here is the rule for
        # [EN] "which one to pick":
        # [EN] startup validation is a series of messages, and the last one is often info like "demo mode";
        # [EN] if displayed by "most recent", the truly important warning gets pushed out (observed once in
        # [EN] practice).
        msgs_txt = [m['text'] for m in app._messages]
        headline = app._headline_message()
        ok &= rec('消息框显示的**不是**最后那条 info，而是最近的警告（警告优先）',
                  bool(headline) and headline['level'] == 'warn'
                  and msgs_txt[-1] != headline['text']
                  and headline['text'] in joined,
                  f"最后一条={msgs_txt[-1][:26]!r}｜显示={headline['text'][:30] if headline else ''!r}")
        # 注意：下面两条找的是**能力校验自己拼的那几句话**（改了什么、依据哪个模型）。
        # 它们由 `llm/capabilities.py` 用中文拼出来（含动态模型名，不经过 i18n），
        # 所以中英文界面下都是中文 —— 断言中文在这里是**正确**的。
        # [EN] Note: the next two lines look for **the sentences capability validation assembles itself** (what
        # [EN] was changed, based on which model).
        # [EN] They are assembled in Chinese by `llm/capabilities.py` (including dynamic model names, not going
        # [EN] through i18n),
        # [EN] so they are Chinese under both Chinese and English UIs -- asserting Chinese here is **correct**.
        ok &= rec('「已改回 / 依据是哪个模型」的细节都在完整列表里（点「查看」可见）',
                  any('改回' in m and '文生图' in m for m in msgs_txt),
                  next((m for m in msgs_txt if '改回' in m), '')[:90])
        ok &= rec('消息框里有「需要重启」的警示',
                  '需要重启' in ' '.join(msgs_txt),
                  next((x for x in texts if '需要重启' in x), '')[:90])
        ok &= rec('内存里的 CFG 已按模型纠正',
                  CFG.b('LLM_CAP_IMAGE') is False,
                  f"LLM_CAP_IMAGE={CFG.b('LLM_CAP_IMAGE')}")
        report['app_messages'] = [m['text'] for m in app._messages][:10]
        await shot('llm_caps_start.png')

        # ── ② 运行界面也有消息框 ──
        # [EN] ── ② The run screen also has a message box ──
        from store.project import Project
        tmpdirs.append(Path(tempfile.mkdtemp(prefix='nws_caps_p2_')))
        proj = Project.create_new(tmpdirs[-1], '能力验证')
        app.current_project = proj
        app.show_main_screen()
        page.update()
        await asyncio.sleep(1.2)
        nodes2: list = []
        for c in page.controls:
            walk(c, nodes2)
        texts2 = [str(getattr(c, 'value', '') or '') for c in nodes2
                  if isinstance(c, ft.Text)]
        count2 = str(getattr(app._ui_msg.get('count'), 'value', '') or '')
        ok &= rec('运行界面上消息框也在',
                  bool(count2) and any(x.strip() == count2.strip() for x in texts2),
                  f'count={count2!r}')
        await shot('llm_caps_main.png')

        # ── ③ 天机对话框：能力开关 + 重启提示 ──
        # [EN] ── ③ Tianji dialog: capability switches + restart hint ──
        dlg = app.show_global_settings()
        page.update()
        await asyncio.sleep(0.8)
        dn: list = []
        walk(dlg, dn)
        switches = [c for c in dn if isinstance(c, ft.Switch)]
        sw_labels = [str(getattr(s, 'label', '') or '') for s in switches]
        for name in ('文生图', '推理模型', '思考开关', 'JSON 模式', 'system 角色'):
            ok &= rec(f'天机里有「{name}」开关', t(name) in sw_labels, str(sw_labels))
        dtexts = [str(getattr(c, 'value', '') or '') for c in dn
                  if isinstance(c, ft.Text)]
        djoined = '\n'.join(dtexts)
        restart_banner = t('本页设置改动后需要重启程序才会生效')
        ok &= rec('对话框里明显注明了「需要重启」',
                  restart_banner in djoined, restart_banner)
        verdict_prefix = t('按模型判定：{v}', v='X').split('X')[0]
        ok &= rec('对话框里显示了按模型判定的结论',
                  any(verdict_prefix in x for x in dtexts),
                  next((x for x in dtexts if verdict_prefix in x), '')[:90])
        ok &= rec('识别到的模型名也写在页面上',
                  'deepseek' in djoined.lower())

        # ── ③b 界面语言：位置对不对 + 显示的是不是语言自己的名字 ──
        # 用户 2026-10-05：「界面语言这个应该是在界面外观里，为何放到 LLM 接入了？
        # 而且它的选项应该是中文/英文（后台值是 zh 和 en，写到 .env 也是 zh/en，
        # 但 UI 上应该是 中文/English）」
        # [EN] ── ③b UI language: is the position right + does it display the language's own name ──
        # [EN] User 2026-10-05: "UI language should be under appearance, why is it placed in LLM integration?
        # [EN] And its options should be Chinese/English (backend values are zh and en, written to .env as
        # [EN] zh/en,
        # [EN] but on the UI it should be Chinese/English)"
        tab_ctrls = [c for c in dn if isinstance(c, ft.Tabs)]
        ok &= rec('天机对话框是选项卡结构', bool(tab_ctrls))
        if tab_ctrls:
            tb = tab_ctrls[0]
            tab_labels = [str(getattr(x, 'label', '') or '')
                          for x in tb.content.controls[0].tabs]
            views = list(tb.content.controls[1].controls)
            want_appear = t('界面外观')
            want_llm = t('AI模型配置')
            ok &= rec('有「界面外观」这一页', want_appear in tab_labels,
                      str(tab_labels))

            def _find_lang_dd(container):
                """在某一页里找「界面语言」下拉（按选项 key = zh/en 认）。
                                English:
                Find the "UI language" dropdown in a certain page (recognized by option key = zh/en).
                """
                ns: list = []
                walk(container, ns)
                for c in ns:
                    if isinstance(c, (ft.Dropdown, ft.DropdownM2)):
                        if {o.key for o in (c.options or [])} == {'zh', 'en'}:
                            return c
                return None

            dd_appear = (_find_lang_dd(views[tab_labels.index(want_appear)])
                         if want_appear in tab_labels else None)
            dd_llm = (_find_lang_dd(views[tab_labels.index(want_llm)])
                      if want_llm in tab_labels else None)
            ok &= rec('界面语言在「界面外观」页里', dd_appear is not None)
            ok &= rec('「LLM 接入」页里**已经没有了**（换语言跟模型无关）',
                      dd_llm is None)
            if dd_appear is not None:
                shown = {o.key: str(getattr(getattr(o, 'content', None),
                                            'value', '') or '')
                         for o in dd_appear.options}
                ok &= rec('选项显示的是语言自己的名字，不是 zh / en',
                          shown.get('zh') == t('中文')
                          and shown.get('en') == 'English', str(shown))
                ok &= rec('选项的 key 仍是 zh / en（存进 .env 的是它）',
                          sorted(shown) == ['en', 'zh'], str(sorted(shown)))
                # 显示文字搬到 `content` 之后，**选中值仍然是 key** ——
                # 保存时 `CFG.set('LANGUAGE', field_value(...))` 拿的就是它，
                # 写的必须是 zh / en，不能变成「中文」。
                # [EN] After the display text is moved to `content`, **the selected value is still the key** --
                # [EN] when saving, `CFG.set('LANGUAGE', field_value(...))` gets exactly that,
                # [EN] what is written must be zh / en, and must not become "Chinese".
                ok &= rec('下拉的选中值仍是 zh / en（不是显示名）',
                          str(dd_appear.value) in ('zh', 'en'),
                          repr(dd_appear.value))

        await shot('llm_caps_dialog.png')

        # ── ④ 改一项 LLM 能力 → 保存 → 消息框报「需要重启」 ──
        # [EN] ── ④ Change one LLM capability -> save -> message box reports "requires restart" ──
        json_sw = next((s for s in switches
                        if str(getattr(s, 'label', '')) == t('JSON 模式')), None)
        ok &= rec('找到「JSON 模式」开关本体', json_sw is not None)
        if json_sw is not None:
            json_sw.value = not bool(json_sw.value)
            page.update()
            await asyncio.sleep(0.2)

            def _restart_msgs() -> list:
                """当前消息列表里**含「需要重启」的那些**（判据按"条数变多"比）。

                ★★ 为什么不是 `app._messages[n_before:]`（2026-10-11 修）：
                  那是**按下标切片**，而"保存"是**异步**的 ——
                  `on_click` 返回之后消息才落进列表。原来只 `await sleep(0.8)` 就去切片，
                  机器一忙（比如在回归器里跑）切片就是**空**的，
                  于是「保存后多了一条提示」当场假红 —— 而产品**明明发了那条消息**
                  （同一支脚本最后 dump 的 `app_messages` 里它就在）。
                  `n_before` 那种写法还怕"列表被裁剪/重排"。
                  ⇒ 改成**数条数**：保存前后各数一次"含「需要重启」的消息有几条"，
                    多了就算过。这样既不受下标影响，也仍然只在"真的多了一条"时才绿。

                    English:
                The messages in the current list **containing "needs restart"** (the criterion compares
                "does the count go up").
                    ★★ Why not `app._messages[n_before:]` (fixed 2026-10-11):
                      that is an **index slice**, and "save" is **asynchronous** -- the message lands in
                      the list only after `on_click` returns. It used to `await sleep(0.8)` and then
                      slice; when the machine is busy (e.g. inside the regressor) the slice is **empty**,
                      so "one more hint after saving" went falsely red -- even though the product
                      **did** post that message (it is right there in the `app_messages` dump this same
                      script writes at the end). The `n_before` form is also vulnerable to the list
                      being trimmed/reordered.
                      ⇒ Switched to **counting**: count messages containing "needs restart" before and
                        after the save; an increase passes. That is immune to indices and still only
                        green when one really appeared.
                """
                return [str(m.get('text', '')) for m in app._messages
                        if RESTART_HINT in str(m.get('text', ''))]

            restart_before = _restart_msgs()
            n_before = len(app._messages)
            saved = False
            for c in dn:
                if c.__class__.__name__ in ('FilledButton', 'TextButton'):
                    if t('保存') in _btn_label(c) and getattr(c, 'on_click', None):
                        c.on_click(None)
                        saved = True
                        break
            ok &= rec('点了「保存」', saved)
            # ★ 轮询等待（最多 ~3s）而不是睡死 0.8s：保存是异步的，
            #   固定睡眠在忙的时候不够 —— 这就是上面那条假红的直接成因。
            # [EN] ★ Poll (up to ~3s) instead of sleeping a fixed 0.8s: saving is asynchronous and a
            # [EN] fixed sleep isn't enough when the machine is busy -- the direct cause of the false
            # [EN] red above.
            new_msgs: list = []
            for _ in range(15):
                await asyncio.sleep(0.2)
                new_msgs = [x for x in _restart_msgs() if x not in restart_before
                            or _restart_msgs().count(x) > restart_before.count(x)]
                if len(_restart_msgs()) > len(restart_before):
                    break
            _after = _restart_msgs()
            new_msgs = _after[len(restart_before):] if len(_after) >= len(restart_before) else _after
            # ⚠ **不要抄产品那句话来比对**（2026-10-08 的教训）：
            #   这里原来写的是 `t('⚠ LLM 配置已改动（{items}）—— 需要重启程序才会生效')`
            #   —— 把产品的整句复制进了判据。那一轮加了「常规」页签，
            #   产品把这句改成「⚠ 配置已改动（…）」（这一页现在还装日志目录，
            #   说"LLM 配置"张冠李戴），**判据没跟着改 → 假红两条**。
            #   现在改用**语义锚点**：那句提示一定含「需要重启」，
            #   措辞怎么调都不影响判据的意图（意图是"有没有那条提示"，
            #   不是"那句话怎么写的"）。
            # [EN] ⚠ **Do not copy the product's sentence for comparison** (lesson from 2026-10-08):
            # [EN] -- Copied the product's full sentence into the criterion. That round added the "General" tab,
            # [EN] The product changed this sentence to "⚠ Configuration changed (...)" (this page still holds the
            # [EN] log directory,
            # [EN] saying "LLM configuration" mismatched), **the criterion wasn't updated along with it -> two
            # [EN] false reds**.
            # [EN] Now switched to a **semantic anchor**: that prompt always contains "needs restart",
            # [EN] however the wording is adjusted, it doesn't affect the criterion's intent (the intent is "is
            # [EN] that prompt there",
            # [EN] not "how that sentence is written").
            ok &= rec('保存后消息框里多了一条「需要重启」的提示',
                      len(_restart_msgs()) > len(restart_before),
                      f'保存前 {len(restart_before)} 条 → 保存后 {len(_restart_msgs())} 条 · '
                      f'新增={new_msgs}')
            ok &= rec('这条提示点名了改的是哪一项',
                      any('JSON' in m for m in new_msgs),
                      '新增=' + ' / '.join(new_msgs)[:140])
            page.update()
            await asyncio.sleep(0.4)
            (OUT / ('llm_caps_after_save' + SUFFIX + '.png')).write_bytes(
                await page.take_screenshot())

        # ── ⑤ 消息列表对话框能打开 ──
        # [EN] -- 5. The message list dialog can open --
        app.show_messages_dialog()
        page.update()
        await asyncio.sleep(0.7)
        ok &= rec('「查看」能打开完整消息列表',
                  bool(getattr(page, '_dialogs', None)))
        await shot('llm_caps_messages.png')
        try:
            page.pop_dialog()
        except Exception:
            pass

        # ── ⑥ 回归：打开对话框、什么都不改就保存 → **不该**报"需要重启" ──
        # 之前把"原始串不同"当成"改过"，`.env` 里没写的项（空串）在保存时
        # 会被填上默认值，于是"原样保存"也会虚报一条要重启的警告。
        # [EN] -- 6. Regression: open the dialog, save without changing anything -> should **not** report
        # [EN] "needs restart" --
        # [EN] Previously "raw string differs" was treated as "changed"; items not written in `.env` (empty
        # [EN] string) at save time
        # [EN] get filled with default values, so "save as-is" also falsely reports a restart warning.
        dlg2 = app.show_global_settings()
        page.update()
        await asyncio.sleep(0.7)
        dn2: list = []
        walk(dlg2, dn2)
        n_before2 = len(app._messages)
        for c in dn2:
            if c.__class__.__name__ in ('FilledButton', 'TextButton'):
                if t('保存') in _btn_label(c) and getattr(c, 'on_click', None):
                    c.on_click(None)
                    break
        await asyncio.sleep(0.7)
        new2 = [m['text'] for m in app._messages[n_before2:]]
        report['unchanged_save_msgs'] = new2
        ok &= rec('原样保存（什么都没改）→ 不虚报"需要重启"',
                  not any(RESTART_HINT in m for m in new2),
                  ' / '.join(new2)[:140])

        report['ok'] = bool(ok)
    except Exception:
        report['fatal'] = traceback.format_exc()
        report['ok'] = False
    finally:
        # 临时项目只建在系统临时区（`tempfile.mkdtemp`），**绝不落在用户的
        # `Projects/` 里**；删除也走逐项删的兜底版（本机的批量删除守卫会
        # 在单次删 >50 个文件时 SystemExit，那会把"写报告"这步也一起带走）。
        # [EN] The temporary project is only created in the system temp area (`tempfile.mkdtemp`), **never in
        # [EN] the user's
        # [EN] `Projects/`**; deletion also goes through the item-by-item fallback version (the local
        # [EN] bulk-delete guard will
        # [EN] SystemExit when deleting >50 files in a single pass, which would also take away the "write
        # [EN] report" step).
        for d in tmpdirs:
            VU.safe_rmtree(d, ignore_errors=True)
        (OUT / f'llm_caps_report{SUFFIX}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        passed = sum(1 for s in report['steps'] if s['ok'])
        failed = [s['name'] for s in report['steps'] if not s['ok']]
        print(f'\n{"=" * 62}\n通过 {passed}/{len(report["steps"])} 项'
              + ('' if not failed else '\n失败：\n  - ' + '\n  - '.join(failed)),
              flush=True)
        if report.get('fatal'):
            print('\n⚠ 验证中途崩溃：\n' + report['fatal'][-1200:], flush=True)
        from util.flet_shutdown import shutdown, exit_now
        # ⚠ 退出码必须在**关窗之前**落实：`page.window.destroy()` 会抛 CancelledError
        #   取消本协程，写在 `await shutdown(page)` 后面那行 `exit_now(...)`
        #   **从来没执行过**（退出码恒为 0 = 假绿）。见 `util/flet_shutdown.shutdown()`。
        # [EN] ⚠ The exit code must be enforced **before closing the window**: `page.window.destroy()` will
        # [EN] throw CancelledError
        # [EN] to cancel this coroutine; the line `exit_now(...)` written after `await shutdown(page)`
        # [EN] **was never executed** (exit code is always 0 = false green). See
        # [EN] `util/flet_shutdown.shutdown()`.
        await shutdown(page, code=0 if report.get('ok') else 2)


if __name__ == '__main__':
    print('LLM 能力配置 · 启动校验 · 全局消息框 —— 验证', flush=True)
    head('A. 模型名 → 能力表')
    ok_a = test_detect()
    head('B. 启动校验（纠偏 / 取交集 / 认不出）')
    try:
        ok_b = test_check(apply=True)
    except Exception:
        report['fatal'] = traceback.format_exc()
        print(report['fatal'][-1200:])
        ok_b = False
    head('B2. 接线（出图判据 / 请求体组装）')
    try:
        ok_c = test_wiring()
    except Exception:
        report['fatal'] = traceback.format_exc()
        print(report['fatal'][-1200:])
        ok_c = False
    head('D. 输出上限表（认不出的模型会退回全局兜底）')
    try:
        ok_d = test_output_caps()
    except Exception:
        report['fatal'] = traceback.format_exc()
        print(report['fatal'][-1200:])
        ok_d = False
    logic_ok = bool(ok_a and ok_b and ok_c and ok_d)
    report['logic_ok'] = logic_ok

    if '--logic-only' in sys.argv:
        report['ok'] = logic_ok
        (OUT / f'llm_caps_report_logic{SUFFIX}.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        passed = sum(1 for s in report['steps'] if s['ok'])
        print(f'\n{"=" * 62}\n（仅逻辑）通过 {passed}/{len(report["steps"])} 项')
        sys.exit(0 if logic_ok else 2)

    head('C. 真机 GUI（消息框 / 天机能力页 / 保存后需重启提示）')
    import flet as ft
    ft.run(test_gui)
