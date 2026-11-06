# -*- coding: utf-8 -*-
"""LLM 能力表：模型能力知识库 + 启动时的配置纠偏。

为什么要有这一层
================
三档模型（华彩 / 日常 / 摘要）是可以分开配的，而「这个模型到底支持什么」
是**模型自己的属性**，不该由用户随手填的开关说了算：把 `deepseek-chat`
标成「支持文生图」，程序会去调一个不存在的接口，然后每次都在运行时报 404。

所以这里把两件事分开：

* **声明** = `.env` 里的 `LLM_CAP_*`，用户以为自己配的模型能干什么；
* **事实** = 本模块的知识库，按模型名判定它究竟能干什么。

启动时拿事实校验声明：不一致就**以事实为准写回 `.env`**，并留下一条
可读的说明（谁、从什么改成什么、依据是哪个模型）。界面的消息框负责播报。

三条规则
--------
1. **取交集（保守）**：三档模型的取值相与 —— 只要有一档不支持，
   整项就判为不支持（否则「华彩档能出图、摘要档不能」这种配置
   会让同一项功能时灵时不灵）。
2. **认不出来就不猜**：自建代理、小众推理服务的模型名不在表里时，
   原样保留用户填的值，只在消息里提示「未能识别，请自行确认」。
   瞎改用户配置比不改更糟。
3. **表里的值是保守值**：只收录能确定的主流模型。型号细节（上下文长度等）
   随版本变动，所以这里不收录易变的数值，只收录结构性能力（能不能出图、
   能不能发 temperature、认不认 system 角色、支持不支持 JSON 模式）。

用法
----
    from llm.capabilities import check_capabilities, CAP_KEYS, CAP_META
    rep = check_capabilities()          # 启动时调一次
    for fix in rep.fixes:               # 已写回 .env，这里拿来说人话
        print(fix.human())

English:
LLM capability table: model capability knowledge base + configuration correction at startup.
Why this layer exists
================
The three model tiers (premium / daily / summary) can be configured separately, and "what this
model actually supports"
is a **property of the model itself**, and should not be dictated by a switch the user casually
fills in: marking `deepseek-chat`
as "supports text-to-image" will make the program call a nonexistent interface, then throw a 404
at runtime every time.
So here two things are separated:
* **Declaration** = `LLM_CAP_*` in `.env`, what the user thinks their configured model can do;
* **Fact** = this module's knowledge base, determining by model name what it actually can do.
At startup, validate the declaration against the fact: if inconsistent, **write back to `.env`
based on the fact**, and leave a
readable explanation (who, changed from what to what, based on which model). The UI message box
is responsible for announcing it.
Three rules
--------
1. **Take the intersection (conservative)**: AND the values of the three tiers -- as long as one tier does not support it,
   the whole item is judged unsupported (otherwise a configuration like "premium tier can generate images, summary tier cannot"
   would make the same feature work inconsistently).
2. **If unrecognized, do not guess**: when the model name of a self-hosted proxy or niche inference service is not in the table,
   keep the user-entered value as-is, and only note in the message "unrecognized, please confirm yourself".
   Recklessly changing the user's config is worse than not changing it.
3. **The values in the table are conservative**: only include certain mainstream models. Model details (context length, etc.)
   change with versions, so volatile numeric values are not included here; only structural capabilities (can it generate images,
   can it send temperature, does it recognize the system role, does it support JSON mode).
Usage
----
    from llm.capabilities import check_capabilities, CAP_KEYS, CAP_META
    rep = check_capabilities()          # call once at startup
    for fix in rep.fixes:               # already written back to .env, use here for human-readable output
        print(fix.human())
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 提示语要跟着界面语言走 —— **这几条会出现在状态栏/消息框里**（能力校验的备注）。
# `i18n` 不反过来导入本项目任何模块，所以这里不会有循环导入。
# [EN] Prompts must follow the UI language — **these lines appear in the status bar/message box**
# [EN] (notes for capability validation).
# [EN] `i18n` does not import any module of this project in reverse, so there will be no circular
# [EN] import here.
from i18n import t

# ── 能力键（与 config.SPEC 里的一一对应）──
CAP_IMAGE = 'LLM_CAP_IMAGE'          # 文生图（/images/generations）
CAP_REASONING = 'LLM_CAP_REASONING'  # 推理模型（自带思维链，不发 temperature）
CAP_THINKING = 'LLM_CAP_THINKING'    # 能关掉思考（thinking:{"type":"disabled"}）
CAP_JSON = 'LLM_CAP_JSON_MODE'       # JSON 模式（response_format）
CAP_SYSTEM = 'LLM_CAP_SYSTEM_ROLE'   # 接受 role=system
# [EN] ── Capability keys (one-to-one with config.SPEC) ──
# [EN] Text-to-image (/images/generations)
# [EN] Reasoning model (has built-in chain-of-thought, does not send temperature)
# [EN] Can disable thinking (thinking:{"type":"disabled"})
# [EN] JSON mode (response_format)
# [EN] Accepts role=system

CAP_KEYS: tuple[str, ...] = (CAP_IMAGE, CAP_REASONING, CAP_THINKING, CAP_JSON, CAP_SYSTEM)

# 键 → (中文名, 英文名, 说明)。说明同时用在界面的开关小字与文档里。
# [EN] Key → (Chinese name, English name, description). The description is used both for the small
# [EN] toggle text in the UI and in the docs.
CAP_META: dict[str, tuple[str, str, str]] = {
    CAP_IMAGE: (
        '文生图',
        'Text-to-image',
        '能否调 /images/generations 出图。关掉则「全彩文生图」这一档'
        '自动降级为本地 PNG 矢量图，肖像图出不来时只是不插肖像。',
    ),
    CAP_REASONING: (
        '推理模型',
        'Reasoning model',
        '模型自带思维链（deepseek-reasoner / o1 / o3 / R1 这类）。'
        '开启后请求里不再发送 temperature —— 这类模型会拒绝或忽略该参数。',
    ),
    CAP_THINKING: (
        '思考开关',
        'Thinking switch',
        '模型能关掉思考模式（发 thinking:{"type":"disabled"}，DeepSeek V4 系列支持）。'
        '开启后，「只要结论」的用途（进度评估、类型判定、正文对齐）会主动关掉思维链：'
        '它们不需要推理过程，而思考是连 max_tokens 一起吃的 —— 2026-10-06 实测，'
        '一句「判据满足了吗」让 deepseek-flash 思考 3233 token，把 2000 的额度整份'
        '用光，正文一个字都没写出来。不支持的模型（o1 / o3 / Claude…）别打开，'
        '它们不认识这个参数，发了可能直接 400。',
    ),
    CAP_JSON: (
        'JSON 模式',
        'JSON mode',
        '支持 response_format={"type":"json_object"} 结构化输出。'
        '关掉则退回「在提示词末尾追加『请仅以 JSON 回答』」这条老路。',
    ),
    CAP_SYSTEM: (
        'system 角色',
        'System role',
        '接受 role=system 的消息。不支持时把系统提示并入首条 user 消息，'
        '否则有的服务会直接 400。',
    ),
}

# ── 模型能力知识库 ──
# [EN] ── Model capability knowledge base ──
#
# 结构：(匹配子串, 展示名, {能力键: bool})。匹配规则：**按顺序取第一个命中的**
# （小写子串匹配），所以**具体的名字必须排在笼统的名字前面**
# （deepseek-reasoner 在 deepseek 之前、gpt-image 在 gpt-4 之前）。
# [EN] Structure: (match substring, display name, {capability key: bool}). Matching rule: **take the
# [EN] first hit in order**
# [EN] (lowercase substring match), so **specific names must come before generic names**
# [EN] (deepseek-reasoner before deepseek, gpt-image before gpt-4).
#
# 只填「结构性能力」，不填上下文长度之类的易变数值 —— 那些随版本变，
# 猜错了会误导人，不如不写。
# [EN] Only fill in "structural capabilities", do not fill in volatile values like context length —
# [EN] those change with versions,
# [EN] and guessing wrong misleads people, so better to omit them.
_TRUE, _FALSE = True, False
_MODELS: list[tuple[str, str, dict[str, bool]]] = [
    # ── 图像模型（只能出图，不能聊天）──
    # [EN] ── Image models (can only generate images, cannot chat) ──
    ('dall-e',            'OpenAI DALL·E',       {CAP_IMAGE: _TRUE, CAP_REASONING: _FALSE, CAP_JSON: _FALSE, CAP_SYSTEM: _TRUE}),
    ('gpt-image',         'OpenAI gpt-image',    {CAP_IMAGE: _TRUE, CAP_REASONING: _FALSE, CAP_JSON: _FALSE, CAP_SYSTEM: _TRUE}),
    ('stable-diffusion',  'Stable Diffusion',    {CAP_IMAGE: _TRUE, CAP_REASONING: _FALSE, CAP_JSON: _FALSE, CAP_SYSTEM: _TRUE}),
    ('sd3',               'Stable Diffusion 3',  {CAP_IMAGE: _TRUE, CAP_REASONING: _FALSE, CAP_JSON: _FALSE, CAP_SYSTEM: _TRUE}),
    ('flux',              'FLUX',                {CAP_IMAGE: _TRUE, CAP_REASONING: _FALSE, CAP_JSON: _FALSE, CAP_SYSTEM: _TRUE}),
    ('cogview',           '智谱 CogView',         {CAP_IMAGE: _TRUE, CAP_REASONING: _FALSE, CAP_JSON: _FALSE, CAP_SYSTEM: _TRUE}),
    ('wanx',              '通义万相',             {CAP_IMAGE: _TRUE, CAP_REASONING: _FALSE, CAP_JSON: _FALSE, CAP_SYSTEM: _TRUE}),
    ('kolors',            '可图 Kolors',          {CAP_IMAGE: _TRUE, CAP_REASONING: _FALSE, CAP_JSON: _FALSE, CAP_SYSTEM: _TRUE}),

    # ── DeepSeek ──
    # ⚠ **2026-10-06 补**：V4 系列（`deepseek-flash` / `deepseek-v4-*`）**默认开着
    #   思考模式**（`reasoning_effort=high`），所以它同时是"推理模型"和"能关思考"。
    #   以前知识库里没有这两个名字，`deepseek-flash` 落到下面笼统的 `deepseek` 上
    #   被判成**非推理模型** —— 声明与事实不符（用户 .env 里就这么写错的）。
    #   具体名字必须排在 `deepseek` **前面**（匹配是"按顺序取第一个命中的"）。
    # [EN] ⚠ **Added 2026-10-06**: the V4 series (`deepseek-flash` / `deepseek-v4-*`) **has thinking mode
    # [EN] on by
    # [EN] default** (`reasoning_effort=high`), so it is both a "reasoning model" and "can disable
    # [EN] thinking".
    # [EN] Previously the knowledge base did not have these two names, so `deepseek-flash` fell through to
    # [EN] the generic `deepseek` below
    # [EN] and was judged a **non-reasoning model** — the declaration did not match the facts (the user
    # [EN] wrote it wrong in .env).
    # [EN] Specific names must come **before** `deepseek` (matching is "take the first hit in order").
    ('deepseek-flash',    'DeepSeek V4 Flash',   {CAP_IMAGE: _FALSE, CAP_REASONING: _TRUE,  CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('deepseek-v4-pro',   'DeepSeek V4 Pro',     {CAP_IMAGE: _FALSE, CAP_REASONING: _TRUE,  CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('deepseek-v4',       'DeepSeek V4',         {CAP_IMAGE: _FALSE, CAP_REASONING: _TRUE,  CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    # reasoner 有思维链、会拒绝 temperature；两档 chat 都支持 JSON 模式与 system。
    # `deepseek-chat` 实测仍然可用（2026-10-06 直连探过，**非思考模式**、不带
    # reasoning_content），所以它是最省心的"摘要档"选择。
    # [EN] reasoner has a chain-of-thought and rejects temperature; both chat tiers support JSON mode and
    # [EN] system.
    # [EN] `deepseek-chat` is still usable in practice (directly probed on 2026-10-06, **non-thinking
    # [EN] mode**, no
    # [EN] reasoning_content), so it is the most worry-free "summary tier" choice.
    ('deepseek-reasoner', 'DeepSeek Reasoner',   {CAP_IMAGE: _FALSE, CAP_REASONING: _TRUE,  CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('deepseek-r1',       'DeepSeek R1',         {CAP_IMAGE: _FALSE, CAP_REASONING: _TRUE,  CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('deepseek-chat',     'DeepSeek Chat',       {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('deepseek',          'DeepSeek',            {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),

    # ── OpenAI ──
    # o 系列（o1/o3/o4-mini）是推理模型，且**不接受 system 角色**（要用 developer）。
    # [EN] The o series (o1/o3/o4-mini) are reasoning models and **do not accept the system role** (use
    # [EN] developer instead).
    ('o4-mini',           'OpenAI o4-mini',      {CAP_IMAGE: _FALSE, CAP_REASONING: _TRUE,  CAP_JSON: _TRUE, CAP_SYSTEM: _FALSE}),
    ('o3-mini',           'OpenAI o3-mini',      {CAP_IMAGE: _FALSE, CAP_REASONING: _TRUE,  CAP_JSON: _TRUE, CAP_SYSTEM: _FALSE}),
    ('o3',                'OpenAI o3',           {CAP_IMAGE: _FALSE, CAP_REASONING: _TRUE,  CAP_JSON: _TRUE, CAP_SYSTEM: _FALSE}),
    ('o1',                'OpenAI o1',           {CAP_IMAGE: _FALSE, CAP_REASONING: _TRUE,  CAP_JSON: _TRUE, CAP_SYSTEM: _FALSE}),
    ('gpt-4.1',           'OpenAI GPT-4.1',      {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('gpt-4o',            'OpenAI GPT-4o',       {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('gpt-4',             'OpenAI GPT-4',        {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('gpt-3.5',           'OpenAI GPT-3.5',      {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('gpt',               'OpenAI',              {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),

    # ── 国内主流 ──
    # [EN] ── Domestic mainstream ──
    ('qwen',              '通义千问',             {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('glm',               '智谱 GLM',             {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('moonshot',          'Moonshot',            {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('kimi',              'Kimi',                {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('ernie',             '文心一言',             {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    # ── 腾讯混元 / TokenHub（2026-10-10 加：用户要在 TokenHub 上用 Hy3）──
    #   TokenHub 的 OpenAI 兼容入口是 `https://tokenhub.tencentmaas.com/plan/v3`
    #   （完整 URL `…/plan/v3/chat/completions`），模型 id 就是 **`hy3`**
    #   （旧的开放权重版叫 `hy3-preview`，TokenHub 上已被路由到 hy3）。
    #   逐项依据（都是官方文档/模型卡上写明的，不是猜的）：
    #     · **默认不思考**：`reasoning_effort` 默认 `no_think`（另有 low/high 两档），
    #       且官方推荐参数是 `temperature=0.9, top_p=1.0` —— **它接受 temperature**
    #       ⇒ 不属于本表意义上的「推理模型」（那一列的语义是"自带思维链、不能发
    #       temperature"，见 CAP_META）。所以 `CAP_REASONING` 取 **False**。
    #     · 它**能**被要求思考，但那走 `extra_body.chat_template_kwargs.reasoning_effort`，
    #       **与本项目发的 `thinking:{"type":"disabled"}` 不是同一个开关**
    #       ⇒ 不列进 `_THINKING_SWITCH`（列了就等于发一个它不认的参数）。
    #     · **结构化输出**：TokenHub 文档写支持，但另有来源标 No ⇒ 按本模块
    #       "表里的值是保守值"的规矩取 **False**（不发 `response_format`，
    #       退回提示词约束 + 本项目的容错 JSON 解析）。真要用请在
    #       「天机 · 推演服务LLM设定 → 模型能力」里手动打开。
    # [EN] ── Tencent Hunyuan / TokenHub (added 2026-10-10: the user wants to use Hy3 on TokenHub) ──
    # [EN] TokenHub's OpenAI-compatible endpoint is `https://tokenhub.tencentmaas.com/plan/v3`
    # [EN] (full URL `…/plan/v3/chat/completions`), the model id is simply **`hy3`**
    # [EN] (the old open-weights version was called `hy3-preview`, and on TokenHub it has been routed to
    # [EN] hy3).
    # [EN] Item-by-item basis (all stated in official docs/model cards, not guessed):
    # [EN] · **Does not think by default**: `reasoning_effort` defaults to `no_think` (there are also
    # [EN] low/high tiers),
    # [EN] and the officially recommended parameters are `temperature=0.9, top_p=1.0` — **it accepts
    # [EN] temperature**
    # [EN] ⇒ it does not fall under "reasoning model" in the sense of this table (the semantics of that
    # [EN] column is "has built-in chain-of-thought, cannot send
    # [EN] temperature", see CAP_META). So `CAP_REASONING` is **False**.
    # [EN] · It **can** be asked to think, but that goes through
    # [EN] `extra_body.chat_template_kwargs.reasoning_effort`,
    # [EN] **which is not the same switch as this project's `thinking:{"type":"disabled"}`**
    # [EN] ⇒ do not list it in `_THINKING_SWITCH` (listing it would mean sending a parameter it does not
    # [EN] recognize).
    # [EN] · **Structured output**: TokenHub docs say it is supported, but another source marks No ⇒ per
    # [EN] this module's
    # [EN] rule that "values in the table are conservative", take **False** (do not send `response_format`,
    # [EN] fall back to prompt constraints + this project's fault-tolerant JSON parsing). If you really
    # [EN] want it, manually
    # [EN] turn it on in "Tianji · Deduction Service LLM Settings → Model Capabilities".
    ('hy3-preview',       '腾讯混元 Hy3 (preview)', {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _FALSE, CAP_SYSTEM: _TRUE}),
    ('hy3',               '腾讯混元 Hy3',           {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _FALSE, CAP_SYSTEM: _TRUE}),
    ('hunyuan',           '腾讯混元',             {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('doubao',            '豆包',                {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('minimax',           'MiniMax',             {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('step-',             '阶跃星辰',             {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('spark',             '讯飞星火',             {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('abab',              'MiniMax abab',        {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),

    # ── 小米 MiMo（2026-10-13 加：用户已在用，原不识别 → 能力开关落到通用缺省）──
    #   模型名形如 `mimo-v2-pro` / `mimo-v2.5` / `mimo-v2-omni` / `xiaomi-*`。
    #   依据（公开模型卡 / 厂商文档，保守填）：MoE + 多模态（文/图/音/视频）、1M 上下文、
    #   工具调用与 JSON 模式都支持；**不是文生图模型**（CAP_IMAGE 指 /images/generations），
    #   故 IMAGE=False；也不声称"默认带思维链、不能发 temperature"，故 REASONING=False
    #   （真要思考走各家自有参数，本项目不主动发 `thinking`）。
    # [EN] ── Xiaomi MiMo (added 2026-10-13: user already uses it; was unrecognized → caps fell to generic default) ──
    ('mimo-v2-omni',     '小米 MiMo V2 Omni',  {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('mimo',             '小米 MiMo',           {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('xiaomi',           '小米 Xiaomi',         {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),


    # ── 国外主流（OpenAI 已在上面；这里补 Anthropic / Google / Meta / Mistral / Cohere / xAI / Perplexity）──
    # [EN] ── Foreign mainstream (OpenAI is above; here: Anthropic / Google / Meta / Mistral / Cohere / xAI / Perplexity) ──
    # 现代对话模型统一支持 JSON 模式 / system 角色；均非文生图、不声称默认带思维链
    # ⇒ IMAGE=False / REASONING=False / JSON=True / SYSTEM=True（与 qwen/glm 一致，保守可考）。
    # 模型名形如 `claude-opus-4` / `gemini-2.5-pro` / `llama-4-scout` / `mistral-large` /
    # `command-r-plus` / `grok-3` / `sonar` —— 具体的排在笼统的 `claude` / `gemini` / `llama` / `mistral` 前面。
    # [EN] Modern chat models uniformly support JSON mode / system role; none are text-to-image and none claim
    # [EN] built-in thinking by default ⇒ IMAGE=False / REASONING=False / JSON=True / SYSTEM=True.
    # [EN] Names like `claude-opus-4` / `gemini-2.5-pro` / `llama-4-scout` / `mistral-large` /
    # [EN] `command-r-plus` / `grok-3` / `sonar` — specific ones precede generic `claude`/`gemini`/`llama`/`mistral`.
    ('claude-opus',       'Claude Opus',         {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('claude-sonnet',     'Claude Sonnet',       {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('claude-haiku',      'Claude Haiku',        {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('claude',            'Claude',              {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('gemini-2.5',        'Google Gemini 2.5',   {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('gemini-2.0',        'Google Gemini 2.0',   {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('gemini-1.5',        'Google Gemini 1.5',   {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('gemini',            'Google Gemini',       {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('llama-4',           'Meta Llama 4',        {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('llama-3',           'Meta Llama 3',        {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('llama',             'Llama',               {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _FALSE, CAP_SYSTEM: _TRUE}),
    ('mixtral',           'Mistral Mixtral',     {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('codestral',         'Mistral Codestral',   {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('mistral',           'Mistral',             {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _FALSE, CAP_SYSTEM: _TRUE}),
    ('command-r',         'Cohere Command R',    {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('command',           'Cohere Command',      {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('grok',              'xAI Grok',            {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('sonar',             'Perplexity Sonar',    {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('pplx',              'Perplexity',          {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('perplexity',        'Perplexity',          {CAP_IMAGE: _FALSE, CAP_REASONING: _FALSE, CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),

    # ── 按名字推断（放最后：前面的具体型号都匹配不上才走这里）──
    # [EN] ── Inferred by name (placed last: only reached when none of the specific models above match) ──
    ('reasoner',          '推理模型（按名称推断）', {CAP_IMAGE: _FALSE, CAP_REASONING: _TRUE,  CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('thinking',          '推理模型（按名称推断）', {CAP_IMAGE: _FALSE, CAP_REASONING: _TRUE,  CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
    ('-r1',               '推理模型（按名称推断）', {CAP_IMAGE: _FALSE, CAP_REASONING: _TRUE,  CAP_JSON: _TRUE, CAP_SYSTEM: _TRUE}),
]


def detect(model: str) -> tuple[dict[str, bool], str]:
    """识别一个模型名 → (能力字典, 展示名)。

    认不出来时返回 `({}, '')` —— 调用方必须把这种情况当成「不知道」，
    **不要**拿默认值去覆盖用户的声明。
    
        English:
    Recognize a model name → (capability dict, display name).
        When unrecognized, return `({}, '')` -- the caller must treat this case as "unknown",
        and **must not** use default values to overwrite the user's declaration.
    """
    name = (model or '').strip().lower()
    if not name:
        return {}, ''
    for pat, label, caps in _MODELS:
        if pat in name:
            return dict(caps), label
    return {}, ''


def detect_one(model: str, cap: str) -> bool | None:
    """单个能力：True / False / None（不知道）。
        English:
    Single capability: True / False / None (unknown).
    """
    caps, _ = detect(model)
    if not caps:
        return None
    return bool(caps.get(cap, False))


# ── 「能不能关掉思考」单独一张小表 ──────────────────────────────────
# [EN] ── A separate small table for "can thinking be disabled" ──────────────────────────────────
#
# 为什么不并进 `_MODELS`：这一列对**绝大多数模型是"不适用"** —— 它们不认识
# `thinking` 这个参数，发了轻则被忽略、重则直接 400。34 条型号逐条填一遍
# 既容易漏，也看不出到底谁支持。所以反过来只列**能关的**，其余一律 False。
# [EN] Why not merge it into `_MODELS`: this column is **"not applicable" for the vast majority of
# [EN] models** — they do not recognize
# [EN] the `thinking` parameter, and sending it is at best ignored, at worst a direct 400. Filling in
# [EN] all 34 model entries one by one
# [EN] is both error-prone and makes it impossible to see who actually supports it. So instead, list
# [EN] only **those that can disable it**, and everything else is False.
#
# 依据：2026-10-06 直连实测（DeepSeek 官方 API）—— V4 系列（`deepseek-flash`
# / `deepseek-v4-flash` / `deepseek-v4-pro`）**默认开着思考**，
# `thinking:{"type":"disabled"}` 一发就回到"秒回几十 token"；
# `deepseek-reasoner` 同样认这个参数。
# [EN] Basis: direct probing on 2026-10-06 (DeepSeek official API) — the V4 series (`deepseek-flash`
# [EN] / `deepseek-v4-flash` / `deepseek-v4-pro`) **has thinking on by default**,
# [EN] and sending `thinking:{"type":"disabled"}` immediately returns to "replying in dozens of
# [EN] tokens";
# [EN] `deepseek-reasoner` also recognizes this parameter.
_THINKING_SWITCH: tuple[str, ...] = (
    'deepseek-flash',
    'deepseek-v4',
    'deepseek-reasoner',
    'deepseek-r1',
)


def detect_thinking_switch(model: str) -> bool | None:
    """这个模型能不能**关掉**思考。`None` = 认不出（**不猜**）。

    先过 `detect()` 门槛：知识库里根本没有这个模型名时一律返回 `None`，
    免得把 `my-private-proxy` 这种自建代理误判成"不支持"而写回用户配置。
    
        English:
    Whether this model can **turn off** thinking. `None` = unrecognized (**don't guess**).
        First pass the `detect()` threshold: when the model name isn't in the knowledge base at all, always return `None`,
        so that self-hosted proxies like `my-private-proxy` aren't misjudged as "unsupported" and written back to the user's config.
    """
    name = (model or '').strip().lower()
    if not name or not detect(name)[0]:
        return None
    return any(pat in name for pat in _THINKING_SWITCH)


def known_models() -> list[tuple[str, str]]:
    """知识库里的 (展示名, 匹配子串)，供界面提示「表里有哪些」。
        English:
    The (display name, match substring) pairs in the knowledge base, for the UI to show "what's in
    the table".
    """
    return [(label, pat) for pat, label, _ in _MODELS]


# ══════════════════════════════════════════════════════════════
#  启动校验
# [EN] Startup validation
# ══════════════════════════════════════════════════════════════

@dataclass
class Fix:
    """一条被纠偏的配置。
        English:
    A config entry that was corrected.
    """
    key: str
    label: str          # 能力中文名
    # [EN] Capability Chinese name
    old: bool
    new: bool
    model: str          # 依据的模型名
    declared: bool      # 用户是否显式写过这一项
    # [EN] Model name used as basis
    # [EN] Whether the user explicitly wrote this item

    def human(self) -> str:
        want = t('支持') if self.new else t('不支持')
        label = t(self.label)
        if not self.declared:
            # 没写过 → 自动填入，不算"改用户的东西"
            # [EN] If not written → fill in automatically, does not count as "modifying the user's stuff"
            return t('未声明「{label}」，按模型 {model} 自动填入：{want}',
                     label=label, model=self.model, want=want)
        return t('「{label}」与模型 {model} 不符，已改回：{want}',
                 label=label, model=self.model, want=want)

    def as_dict(self) -> dict:
        return {'键': self.key, '能力': self.label, '原值': self.old, '新值': self.new,
                '依据模型': self.model, '原为显式声明': self.declared,
                '说明': self.human()}


@dataclass
class Report:
    """校验结果。`fixes` 里的每一条都已经**写回 CFG 并落盘**（apply=True 时）。
        English:
    Validation result. Every entry in `fixes` has already been **written back to CFG and persisted**
    (when apply=True).
    """
    ok: bool = True
    fixes: list[Fix] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    models: dict[str, str] = field(default_factory=dict)   # 档位 → 模型名
    detected: dict[str, bool | None] = field(default_factory=dict)  # 能力 → 判定值
    labels: dict[str, str] = field(default_factory=dict)   # 模型名 → 展示名
    # [EN] Tier → model name

    @property
    def changed(self) -> bool:
        return bool(self.fixes)

    def messages(self) -> list[tuple[str, str]]:
        """给界面的 (文本, 级别) 列表：级别 = info / warn / ok。

        **区分两种修改**，因为它们的性质完全不同：

        * **纠错**（用户明确写过、但与模型不符）→ `warn` + 一句"需要重启"。
          这是"你配错了，我按事实改回来了"，必须让人看见。
        * **填空**（`.env` 里根本没写过这一项）→ 只合成**一条 info**。
          这不是纠错，是初始化。首次启动时什么都没有，若按纠错报，
          一开程序就是四条警告 —— 那种噪音会把人练成不看警告。
        
                English:
        The (text, level) list for the UI: level = info / warn / ok.
                **Distinguish the two kinds of modification**, because their nature is completely different:
                * **Correction** (the user explicitly wrote it, but it doesn't match the model) → `warn` + a "needs restart" message.
                  This is "you configured it wrong, I changed it back per the facts" and must be seen.
                * **Fill-in** (this item was never written in `.env` at all) → synthesize only **one info**.
                  This isn't a correction, it's initialization. On first startup there's nothing, and if it were reported as a correction,
                  the program would show four warnings right on launch — that kind of noise trains people to ignore warnings.
        """
        out: list[tuple[str, str]] = []
        corrected = [f for f in self.fixes if f.declared]
        filled = [f for f in self.fixes if not f.declared]
        if corrected:
            out.append((t('LLM 能力校验：{n} 项与模型特性不符，已自动改回',
                          n=len(corrected)), 'warn'))
            for f in corrected:
                out.append((f.human(), 'warn'))
            out.append((t('LLM 配置已变更 —— 需要重启程序才会生效'), 'warn'))
        if filled:
            who = filled[0].model
            yes, no = t('支持'), t('不支持')
            detail = ' / '.join(f'{t(f.label)}={yes if f.new else no}'
                                for f in filled)
            out.append((t('已按模型 {who} 自动填入 LLM 能力：{detail}',
                          who=who, detail=detail), 'info'))
        for n in self.notes:
            out.append((n, 'info'))
        return out

    def as_dict(self) -> dict:
        return {
            'ok': self.ok,
            'changed': self.changed,
            'models': self.models,
            'labels': self.labels,
            'detected': self.detected,
            'fixes': [f.as_dict() for f in self.fixes],
            'notes': list(self.notes),
        }


def _text_models(cfg) -> dict[str, str]:
    """三档模型里非空的那几个：档位 → 模型名。
        English:
    The non-empty ones among the three tiers: tier → model name.
    """
    out: dict[str, str] = {}
    for tier, key in ((t('华彩档'), 'MODEL_FRONT'), (t('日常档'), 'MODEL_DAILY'),
                      (t('摘要档'), 'MODEL_CHEAP')):
        m = (cfg.s(key) or '').strip()
        if m:
            out[tier] = m
    return out


def detect_capabilities(cfg=None) -> tuple[dict[str, bool | None], dict[str, str], list[str]]:
    """算出「按模型事实，各项能力应当是什么」。

    返回 `(判定值, 档位→模型名, 提示语)`；判定值里 `None` = 认不出来。
    
        English:
    Compute "what each capability should be, according to model facts".
        Return `(verdict value, tier→model name, hint text)`; `None` in the verdict value = unrecognized.
    """
    from config import CFG as _CFG
    cfg = cfg or _CFG
    models = _text_models(cfg)
    labels: dict[str, str] = {}
    notes: list[str] = []

    text_caps = (CAP_REASONING, CAP_JSON, CAP_SYSTEM)
    verdict: dict[str, bool | None] = {}

    for cap in text_caps:
        vals: list[tuple[str, bool]] = []     # (模型名, 该模型的值)
        # [EN] (model name, the model's value)
        for tier, m in models.items():
            v = detect_one(m, cap)
            if v is None:
                continue
            labels.setdefault(m, detect(m)[1])
            vals.append((m, v))
        if not vals:
            verdict[cap] = None
            continue
        # 取交集（保守）：任一档不支持 → 整项判为不支持
        # [EN] Take intersection (conservative): if any tier does not support it, the whole item is judged
        # [EN] unsupported
        bad = [(m, v) for m, v in vals if not v]
        verdict[cap] = not bad
        # **三档不一致时才提示** —— 三档都说"不支持"是正常结论，不是"被最保守的
        # 档位拖累"；只有分档配置（华彩用 A、摘要用 B）才会真的产生歧义。
        # [EN] **Only warn when the three tiers disagree** -- all three saying "not supported" is a normal
        # [EN] conclusion, not "dragged down by
        # [EN] the most conservative tier"; only when the tier configs differ (A for highlights, B for summary)
        # [EN] does real ambiguity arise.
        if bad and len(bad) < len(vals):
            # 去重：三档常常配同一个模型名，重复三遍读起来像坏了
            # [EN] Dedupe: the three tiers often use the same model name, and reading it three times looks broken
            names = '、'.join(dict.fromkeys(m for m, _ in bad))
            notes.append(t('{label}：{names} 这一档不支持，三档不一致，'
                           '已按最保守的取值（不支持）',
                           label=t(CAP_META[cap][0]), names=names))

    # ── 「思考开关」**单独判，不走取交集** ──
    # [EN] ── "Thinking toggle" is **judged separately, not via intersection** ──
    #
    # ⚠ 2026-10-06 真机抓到的：用户三档配的是
    #   `MODEL_FRONT=deepseek-chat`（本来就不思考）+ `MODEL_DAILY/CHEAP=deepseek-flash`
    #   （思考、且能关）。取交集 → 判 false → **摘要档明明能关思考却关不了**，
    #   `progress_eval` 继续每拍爆预算（就是用户拿来问的那 8 条告警）。
    # [EN] ⚠ Captured on a real machine on 2026-10-06: the user's three tiers were configured as
    # [EN] `MODEL_FRONT=deepseek-chat` (does not think anyway) + `MODEL_DAILY/CHEAP=deepseek-flash`
    # [EN] (thinks, and can be turned off). Intersection → false → **the summary tier can clearly disable
    # [EN] thinking but cannot**,
    # [EN] `progress_eval` keeps blowing its budget every tick (those 8 alerts the user asked about).
    #
    # 为什么这项不该保守：它不是「整个会话的组装开关」（像 JSON 模式那样），
    # 而是**逐请求的优化许可** —— 灵不灵只取决于"那一次请求用的模型"，
    # 而 `llm/router` 手里就有那个模型名（它会**再逐模型确认一遍**，
    # 所以"混配里有 o1"这种危险组合在那里就被挡住了）。
    # 这里判 True 只是说"允许去关"，不是"对任何模型都发"。
    # [EN] Why this item should not be conservative: it is not the "assembly switch for the whole session"
    # [EN] (like JSON mode),
    # [EN] but rather a **per-request optimization permit** -- whether it works depends only on the "model
    # [EN] used for that one request",
    # [EN] and `llm/router` has that model name in hand (it will **confirm it again per model**,
    # [EN] so dangerous combinations like "an o1 in the mix" are blocked right there).
    # [EN] Judging True here only means "allowed to turn it off", not "send it for any model".
    vals_t = [(m, detect_thinking_switch(m)) for m in models.values()]
    vals_t = [(m, v) for m, v in vals_t if v is not None]
    if vals_t:
        verdict[CAP_THINKING] = any(v for _m, v in vals_t)
        if verdict[CAP_THINKING] and not all(v for _m, v in vals_t):
            names = '、'.join(dict.fromkeys(m for m, v in vals_t if v))
            notes.append(t('{label}：{names} 支持关掉思考，'
                           '已按「能用就用」判定（每次都还会按当次请求的模型再确认）',
                           label=t(CAP_META[CAP_THINKING][0]), names=names))
    else:
        verdict[CAP_THINKING] = None

    # 文生图看的是 IMAGE_AI_MODEL（它可以和聊天模型不同）；
    # 没配图像模型时，退回看三档聊天模型有没有出图能力。
    # [EN] Text-to-image looks at IMAGE_AI_MODEL (it can differ from the chat model);
    # [EN] when no image model is configured, fall back to checking whether any of the three chat tiers has
    # [EN] image-generation capability.
    img_model = (cfg.s('IMAGE_AI_MODEL') or '').strip()
    if img_model:
        v = detect_one(img_model, CAP_IMAGE)
        verdict[CAP_IMAGE] = v
        if v is not None:
            labels.setdefault(img_model, detect(img_model)[1])
        if v is False:
            notes.append(t('文生图模型 {model} 不在支持出图的型号里'
                           '（或本来就是聊天模型），「全彩文生图」会被降级',
                           model=img_model))
    else:
        vals = []
        for m in models.values():
            v = detect_one(m, CAP_IMAGE)
            if v is not None:
                vals.append(v)
        verdict[CAP_IMAGE] = (all(vals) if vals else None)

    return verdict, models, notes


def check_capabilities(cfg=None, *, apply: bool = True) -> Report:
    """启动时校验 LLM 能力声明，不符就按模型特性改回并落盘。

    `apply=False` 只算不改（验证脚本用）。
    
        English:
    Validate LLM capability declarations at startup; if they don't match, correct them per model
    characteristics and persist.
        `apply=False` only computes without modifying (used by the verification script).
    """
    from config import CFG as _CFG
    cfg = cfg or _CFG

    verdict, models, notes = detect_capabilities(cfg)
    labels = {m: detect(m)[1] for m in models.values() if detect(m)[1]}
    rep = Report(models=models, labels=labels, notes=list(notes))
    rep.detected = verdict

    if cfg.mock:
        rep.notes.append(t('演示模式（MOCK_LLM）：不联网，能力校验仍按模型名执行'))

    if not models and not (cfg.s('IMAGE_AI_MODEL') or '').strip():
        rep.notes.append(t('尚无模型配置，跳过 LLM 能力校验'))
        return rep

    img_model = (cfg.s('IMAGE_AI_MODEL') or '').strip()

    def _why(key: str) -> str:
        """该项能力是**拿哪个模型**去判的（提示语里要说清依据）。

        去重：三档通常配同一个模型，不去重就会写成
        「deepseek-chat、deepseek-chat、deepseek-chat」，读起来像出了 bug。
        
                English:
        Which model this capability was **judged with** (the hint text must state the basis clearly).
                Deduplicate: the three tiers usually all use the same model, and without dedup it would read
                "deepseek-chat, deepseek-chat, deepseek-chat", which looks like a bug.
        """
        if key == CAP_IMAGE and img_model:
            return img_model
        return '、'.join(dict.fromkeys(models.values()))

    for key in CAP_KEYS:
        want = verdict.get(key)
        if want is None:
            rep.notes.append(
                t('{label}：未能识别 {why}，保留你填的值（请自行确认）',
                  label=t(CAP_META[key][0]), why=_why(key)))
            continue
        raw = (cfg.raw(key) or '').strip()
        declared = raw != ''
        cur = cfg.b(key)
        if declared and cur == want:
            continue
        rep.fixes.append(Fix(key=key, label=CAP_META[key][0], old=cur, new=want,
                             model=_why(key), declared=declared))
        if apply:
            cfg.set(key, 'true' if want else 'false')

    if rep.fixes and apply:
        try:
            cfg.save()
        except OSError:
            rep.ok = False
            rep.notes.append(t('能力校验结果写回 .env 失败，请检查文件权限'))
    return rep


# ══════════════════════════════════════════════════════════════
#  界面辅助
# [EN] UI helper
# ══════════════════════════════════════════════════════════════

def capability_rows(cfg=None) -> list[dict]:
    """给设置界面用：每项能力一行（键、中文名、说明、当前值、检测值）。
        English:
    For the settings UI: one line per capability (key, Chinese name, description, current value,
    detected value).
    """
    from config import CFG as _CFG
    cfg = cfg or _CFG
    verdict, models, _ = detect_capabilities(cfg)
    rows = []
    for key in CAP_KEYS:
        label, _en, desc = CAP_META[key]
        rows.append({
            'key': key,
            'label': label,
            'desc': desc,
            'value': cfg.b(key),
            'detected': verdict.get(key),
            'why': ((cfg.s('IMAGE_AI_MODEL') or '').strip()
                    if key == CAP_IMAGE and (cfg.s('IMAGE_AI_MODEL') or '').strip()
                    else ' / '.join(models.values())),
        })
    return rows


def models_text(cfg=None) -> str:
    """当前参与判定的模型（三档 + 出图模型），给界面显示用。
        English:
    The models currently participating in the verdict (three tiers + image generation model), for UI
    display.
    """
    from config import CFG as _CFG
    cfg = cfg or _CFG
    models = _text_models(cfg)
    who = '、'.join(dict.fromkeys(models.values()))     # 三档常常同名，去重
    # [EN] The three tiers often share the same name; deduplicate
    img = (cfg.s('IMAGE_AI_MODEL') or '').strip()
    if img:
        who += f'（出图：{img}）' if who else img
    return who


def value_text(v: bool | None) -> str:
    """能力判定值 → 界面文字。`None` = 认不出来，**不猜**。
        English:
    Capability verdict value → UI text. `None` = unrecognized, **don't guess**.
    """
    if v is None:
        return t('未识别')
    return t('支持') if v else t('不支持')


def summary_text(cfg=None) -> str:
    """一行人类可读的「当前模型特性」，放在设置界面顶部。
        English:
    A single human-readable line of "current model characteristics", placed at the top of the
    settings UI.
    """
    from config import CFG as _CFG
    cfg = cfg or _CFG
    verdict, models, _ = detect_capabilities(cfg)
    who = models_text(cfg)
    if not who:
        return t('尚未配置模型')
    parts = [f'{t(CAP_META[k][0])}={value_text(verdict.get(k))}' for k in CAP_KEYS]
    return t('识别到模型：{who}', who=who) + '｜' + '｜'.join(parts)


# ══════════════════════════════════════════════════════════════════
#  模型的**输出上限**（2026-10-10，用户要求"按模型的上限来限制，
#  而不是手动设一个上限"）
# [EN] The model's **output cap** (2026-10-10, user requested "limit by the model's cap,
# [EN] rather than manually setting a cap")
# ══════════════════════════════════════════════════════════════════
#
# 为什么要有这张表
# [EN] Why this table exists
# ----------------
# 2026-10-10 用户第一次真跑一天，日志里出现了两次 `out=3998`
# （`CREW_SCRIPT_TOKENS=4000`，正好卡在上限）、一次 `day_summary out=2000`，
# 都是**写到一半被砍断**。事后复盘里的"掌柜该给的坦白拍没有落地"、
# "剧本 rewrite 了 4 轮还是被判不通过"，根子都在这儿：
# **额度是按"我们觉得它要写多少"设的，而模型自己知道它能写多少。**
# [EN] On 2026-10-10 the user really ran it for a day for the first time, and the logs showed
# [EN] `out=3998` twice
# [EN] (`CREW_SCRIPT_TOKENS=4000`, right at the cap), and once `day_summary out=2000`,
# [EN] all of them **cut off halfway through writing**. The post-mortem's "the shopkeeper's confession
# [EN] shot that should have been delivered never landed",
# [EN] and "the script was rewritten 4 rounds and still judged as failing", both trace back to here:
# [EN] **The quota was set by "how much we think it needs to write", but the model itself knows how
# [EN] much it can write.**
#
# ⇒ 上限改由这里查出来的数决定（见 `llm/router._effective_max_tokens`）。
# [EN] ⇒ The cap is now determined by the number looked up here (see
# [EN] `llm/router._effective_max_tokens`).
#
# ⚠⚠ **这张表是"猜的"，所以绝不能只靠它**
# [EN] ⚠⚠ **This table is a "guess", so never rely on it alone**
# ----------------------------------------
# 各家 API 的 max output 各不相同（几百到几万），而且**同一个模型名在不同
# 供应商后面也可能不一样**（本项目就吃过"名字会骗人"的亏）。给一个太大的值
# 去请求，有的服务会直接 **400**（不是截断，是整发失败）。
# ⇒ 两条一起用：
#     ① 下面这张表 + `LLM_MAX_TOKENS_FALLBACK` 给"先用多大"；
#     ② `llm/router` 收到**和 max_tokens 有关的 400** 时，把上限减半重试
#        （`_looks_like_token_limit_error`）—— 于是"猜错"最多贵一次调用，
#        不会把这条路堵死。
# [EN] Each vendor's API has a different max output (ranging from a few hundred to tens of thousands),
# [EN] and **the same model name under different
# [EN] vendors may also differ** (this project has been burned by "names can lie"). Requesting with too
# [EN] large a value,
# [EN] some services will directly return **400** (not truncation, but the whole send failing).
# [EN] ⇒ Use both together:
# [EN] ① The table below + `LLM_MAX_TOKENS_FALLBACK` to decide "how much to use first";
# [EN] ② When `llm/router` receives a **400 related to max_tokens**, halve the cap and retry
# [EN] (`_looks_like_token_limit_error`) -- thus a "wrong guess" costs at most one extra call,
# [EN] and won't block this path entirely.
#
# 单位：token。找不到就是 `max_output_tokens() is None`，由调用方用 fallback。
# [EN] Unit: token. If not found, it is `max_output_tokens() is None`, and the caller uses the
# [EN] fallback.
MAX_OUTPUT_TOKENS: tuple[tuple[str, int], ...] = (
    # 顺序即匹配顺序：**更具体的名字放前面**（`deepseek-v4-pro` 要在
    # `deepseek-v4` 之前，否则永远匹配不到）。
    # [EN] Order is match order: **put more specific names first** (`deepseek-v4-pro` must come before
    # [EN] `deepseek-v4`, otherwise it will never match).
    ('deepseek-v4-pro', 65536),
    ('deepseek-v4', 32768),
    ('deepseek-flash', 32768),
    ('deepseek-reasoner', 65536),
    ('deepseek-r1', 32768),
    ('deepseek-chat', 8192),
    ('deepseek', 8192),
    ('gpt-5', 32768),
    ('gpt-4o', 16384),
    ('gpt-4', 8192),
    ('o3', 100000),
    ('o4', 100000),
    ('o1', 32768),
    ('claude', 32768),
    ('qwen3', 32768),
    ('qwen-max', 8192),
    ('qwen', 8192),
    ('glm-4', 16384),
    ('glm', 4096),
    ('moonshot', 8192),
    ('kimi', 8192),
    # ★★★ 2026-10-14（用户）：「调用模型的时候会报错撞到 max_tokens 8192……
    #   如果是本地配置的 这个很明显已经过时了」→ 要求改成 **819200**（原按 100 倍）。
    #   实据（`logs/nws_2026_10_14_22_32_05.log`）：
    #     `LLM 输出被截断（max_tokens=8192，实际输出 8192 token / 正文 1856 字，
    #      且本次带思考内容（思考也算在 max_tokens 里））… purpose=extract model=hy3`
    #   ⇒ 命中的就是**这一行**。这个值是**本地写死的猜测**（本表开头写着"各家不一样、是猜的"），
    #     与大模型返回无关；8192 太保守 —— hy3 带思考时，思考 + 正文一起算在 max_tokens 里，
    #     8192 只够写 1856 字正文就被砍断。
    #   ★ 实测（`developers/probe_hy3_maxtokens.py` 真调该端点）：
    #     8192 / 131072 / 419200 / **819200** 全部 **HTTP 200**，服务端不收拒。
    #   ⚠ 猜大了不是"写得短"而是**整发被拒**（400）；router 的
    #     `_looks_like_token_limit_error` 会减半重试兜住，但每次减半都是一次真实调用。
    # [EN] ★★★ 2026-10-14 (user): "calling a model errors out hitting max_tokens 8192 ... if it's a
    # [EN] local config it's clearly outdated" -> change it to **819200**.
    # [EN] Evidence (`logs/nws_2026_10_14_22_32_05.log`): `LLM output truncated (max_tokens=8192,
    # [EN] actual output 8192 token / 1856 chars of body, and this call carried thinking content
    # [EN] (thinking counts toward max_tokens)) ... purpose=extract model=hy3` => it hits **this row**.
    # [EN] This is a **hard-coded local guess** (the table header says limits differ per vendor and are
    # [EN] guessed); nothing to do with what the model returns. 8192 was too conservative -- with thinking
    # [EN] on, thinking + body both count, so 8192 only bought 1856 chars of body.
    # [EN] ★ Measured (`developers/probe_hy3_maxtokens.py`, real call): 8192 / 131072 / 419200 /
    # [EN] **819200** all return **HTTP 200** -- the endpoint does not reject it.
    # [EN] ⚠ Guessing too large is not "writing less" but **the whole request being rejected** (400);
    # [EN] router's `_looks_like_token_limit_error` halves and retries, but each halving is a real call.
    ('hy3', 819200),
    # ★★★ 2026-10-18 **火山方舟 / 豆包系**。为什么必须登记（不是"顺手补全"）：
    #   表里没有 → `max_output_tokens()` 返回 `None` → 调用方退回
    #   `LLM_MAX_TOKENS_FALLBACK`，而那个值当时是 **819200**（为 hy3 设的）。
    #   于是豆包被发了 819200 ⇒ **整发 400**：
    #     `InvalidParameter: The parameter max_tokens ... integer above maximum value`
    #   实测后果不是"写得短"，是**每拍都失败、降级成 wait**：
    #     `「祥子」决策失败，本轮降级为 wait`（2026-10-18 12:41，跑 1 拍全空）。
    #   ★ 实测上限（逐档试到被拒为止）：
    #     doubao-seed-character-251128 → 32768（65536 起 400）
    #     doubao-seed-2-1-lite-260915  → 131072（262144 起 400）
    #   ⚠ 顺序：`doubao-seed-character` 必须排在 `doubao` 之前（本表按顺序取第一个命中）。
    #   ⚠ 族兜底取 32768（**保守**）：猜大了是硬 400，猜小了只是截断 —— 宁可截断。
    # [EN] ★★★ 2026-10-18 **Volcengine Ark / Doubao family**. Why it must be registered (not "just
    # [EN] filling in a gap"): without a row, `max_output_tokens()` returns `None`, the caller falls
    # [EN] back to `LLM_MAX_TOKENS_FALLBACK`, which at the time was **819200** (set for hy3). Doubao
    # [EN] then received 819200 and **the whole request 400'd**:
    # [EN]   `InvalidParameter: The parameter max_tokens ... integer above maximum value`
    # [EN] The measured consequence is not "writes less" but **every beat failing and degrading to
    # [EN] wait**: `「祥子」决策失败，本轮降级为 wait` (2026-10-18 12:41, one tick produced nothing).
    # [EN] ★ Measured ceilings (stepped up until rejected):
    # [EN]   doubao-seed-character-251128 -> 32768 (400 from 65536)
    # [EN]   doubao-seed-2-1-lite-260915  -> 131072 (400 from 262144)
    # [EN] ⚠ Order: `doubao-seed-character` must precede `doubao` (first match wins).
    # [EN] ⚠ The family fallback is 32768 (**conservative**): guessing high is a hard 400, guessing
    # [EN] low only truncates -- prefer truncation.
    ('doubao-seed-character', 32768),
    ('doubao', 32768),
    # ── 国外主流（2026-10-13，保守猜测；真被 400 会减半重试，见 router）──
    # [EN] Foreign mainstream (2026-10-13, conservative guess; real 400 halves & retries)
    ('claude-opus', 32768),
    ('claude-sonnet', 8192),
    ('claude-haiku', 8192),
    ('claude', 32768),
    ('gemini-2.5', 65536),
    ('gemini', 8192),
    ('llama-4', 8192),
    ('llama-3', 8192),
    ('llama', 4096),
    ('mixtral', 8192),
    ('mistral', 8192),
    ('command', 4096),
    ('grok', 8192),
    ('sonar', 4096),
    ('perplexity', 4096),
    # ── 小米 MiMo（2026-10-13，保守猜测；真被 400 会减半重试，见 router）──
    # [EN] Xiaomi MiMo (2026-10-13, conservative guess; real 400 halves & retries)
    ('mimo', 8192),
)


def max_output_tokens(model: str) -> int | None:
    """这个模型**自己**的输出上限（token）。认不出来返回 `None`（**不猜**）。

    ★ 「认不出来就返回 None、由调用方给一个保守的兜底」与本模块一贯的做法
      一致：`detect_thinking_switch()` 对不认识的模型也返回 `None`，
      理由是**猜错会去改用户的配置**。这里的后果轻一些（只是发一个可能偏大的
      `max_tokens`，真被拒了就减半重试），但同一个道理：**别把猜测写死成事实**。
    
        English:
    This model's **own** output limit (tokens). Return `None` if unrecognized (**don't guess**).
        ★ "Return None when unrecognized, and let the caller provide a conservative fallback" is consistent with this module's usual
          approach: `detect_thinking_switch()` also returns `None` for unrecognized models,
          the reason being that **a wrong guess would modify the user's config**. The consequences here are milder (it only sends a possibly
          too-large `max_tokens`, and if it's really rejected, it halves and retries), but the same principle applies: **don't hard-code a guess as fact**.
    """
    name = str(model or '').strip().lower()
    if not name:
        return None
    for pat, limit in MAX_OUTPUT_TOKENS:
        if pat in name:
            return int(limit)
    return None
