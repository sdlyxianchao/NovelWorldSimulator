# -*- coding: utf-8 -*-
"""界面多语言（i18n）。

设计：
- 以**中文原文为 key**，查表得英文；未登记的 key 原样返回（不会崩，只是不翻译）
- 语言来源：`.env` 的 `UI_LANG`（zh / en），也可在运行时 set_lang()
- 带变量的文案用命名占位符：t('共 {n} 项', n=3)

用法：
    from i18n import t, set_lang, get_lang, LANGS
    label = t('开　卷')                 # zh → '开　卷'；en → 'New Story'
    msg = t('拾起旧卷（{n} 个项目）', n=3)

English:
UI multilingual (i18n).
Design:
- Use the **Chinese original text as the key**, look up the English in the table; unregistered keys are returned as-is (won't crash, just untranslated)
- Language source: `.env`'s `UI_LANG` (zh / en), can also be set at runtime via set_lang()
- Texts with variables use named placeholders: t('共 {n} 项', n=3)
Usage:
    from i18n import t, set_lang, get_lang, LANGS
"""
from __future__ import annotations

DEFAULT_LANG = 'zh'

# 语言代码 → 显示名（下拉框用）
# [EN] Language code → display name (for dropdown)
LANGS: dict[str, str] = {
    'zh': '中文',
    'en': 'English',
}

_current: str = DEFAULT_LANG


def set_lang(code: str) -> str:
    """设置当前界面语言，返回生效的语言代码。
        English:
    Set the current UI language, returns the effective language code.
    """
    global _current
    _current = code if code in LANGS else DEFAULT_LANG
    return _current


def get_lang() -> str:
    return _current


def is_en() -> bool:
    return _current == 'en'


# ══════════════════════════════════════════════════════════════
#  中文原文 → English
# [EN] Chinese source → English
# ══════════════════════════════════════════════════════════════
_ZH2EN: dict[str, str] = {
    # ── 开始界面 ──
    # 菜单标题沿用写作语汇（开卷/拾卷/天机/书斋），但**说明要短、要直白** ——
    # 看说明的人是第一次打开软件，扫一眼就完事，所以每条 ≤ 14 字。
    # [EN] ── Start screen ──
    # [EN] Menu titles follow the writing lexicon (open volume / pick up volume / heavenly secret / study),
    # [EN] but **descriptions must be short and plain** ——
    # [EN] The reader is opening the software for the first time and just scans it, so each ≤ 14
    # [EN] characters.
    '小 说 世 界 A I 模 拟': 'Novel World AI Simulator',
    '── 把 故 事 ， 活 一 遍 ──': '——   Live the story once   ——',
    '开　卷': 'New Story',
    '导入小说文件夹': 'Import a novel folder',
    '当前项目': 'Current project',
    # ★ 2026-10-28：重启后报的是记录里那本书（本次还没打开），说「当前项目」不准确。
    # [EN] After a restart the name shown comes from the record (not opened this session),
    # [EN] so "last opened" is the honest label.
    '上次打开': 'Last opened',
    '尚未开卷 —— 从「开　卷」开始': 'No project open yet — start with "New Story"',
    '已开卷 · 点「拾　卷」挑一本': 'Volume opened · click "Open Story" to pick one',
    '小说世界AI模拟 — {name}': 'Novel World AI Simulator — {name}',
    '拾　卷': 'Open Story',
    '打开以前的故事': 'Open a previous story',
    '还没有做过的故事': 'No stories yet',
    '拾起旧卷（无项目）': 'No project yet',
    '天　机': 'Settings',
    '程序设置：模型、预算': 'App settings: models, budget',
    '书　斋': 'Project Settings',
    '本书设置：类型、风格': 'Story settings: genre, style',
    '回　卷': 'Resume',
    '回到推演界面': 'Back to the running screen',
    '没有在推演的故事': 'Nothing is running',
    '暂无正在运行的故事，请先开卷': 'No story is running — create one with New Story first',
    '回到运行界面': 'return to the running story',
    '归　去': 'Quit',
    '退出程序': 'Quit the app',
    'v{VERSION} · 本地运行 · Python + Flet': 'v{VERSION} · runs locally · Python + Flet',

    # ── 开卷向导 ──
    # [EN] ── Open Volume wizard ──
    '开 卷 · 导 入 向 导': 'New Story · Import Wizard',
    '步骤 1/4：选择文件夹': 'Step 1 of 4 · Choose folder',
    '步骤 2/4：项目设置': 'Step 2 of 4 · Project',
    '步骤 3/4：AI 优化设置': 'Step 3 of 4 · AI options',
    '步骤 4/4：确认并开始': 'Step 4 of 4 · Confirm',
    '小说文件夹路径': 'Novel folder path',
    '选择文件夹': 'Choose folder',
    '浏览…': 'Browse…',
    '提示：文件夹中应包含大纲、设定、人物等文件':
        'Tip: the folder should contain outline, settings, character files',
    '程序目录下的 samples/ 里有 6 篇现成示例（每个题材一篇，中英各一版），'
    '可以直接挑一篇试跑':
        "There are 6 ready-made samples under samples/ in the program folder "
        "(one per genre, in Chinese and English) — pick one and run it.",
    # ── 开卷向导 · 「这本已经开过卷了」（2026-10-07）──
    # [EN] ── Open Volume wizard · "this volume has already been opened" (2026-10-07) ──
    '⚠ 这本已经开过卷了：「{name}」。再走一遍会重新读一次'
    '素材 —— 只想看故事的话，去开始界面点「拾　卷」打开它。':
        "⚠ This novel has already been opened: “{name}”. Running it again "
        "re-reads the source — to carry on with the story, use “Open Story” "
        "on the start screen.",
    '这本小说已经开过卷了': 'This novel has already been opened',
    '这本小说已经开过卷了，不必再开一遍。':
        'This novel has already been opened — no need to open it again.',
    '· 项目：「{name}」': '· Project: “{name}”',
    '· 创建 {created}　最近运行 {last}　跑过 {runs} 轮':
        '· Created {created}　last run {last}　{runs} run(s)',
    '· 源文件夹：{src}': '· Source folder: {src}',
    '（时间未记）': '(time not recorded)',
    '（还没跑过）': '(never run)',
    '（另外还有 {n} 本同名或同素材的项目）':
        '(plus {n} more project(s) with the same name or source)',
    '再走一遍会重新读一遍素材（多花一次开卷的时间与额度）。'
    '只想接着看故事的话，点左边那个按钮打开已经开好的那本。':
        "Running it again re-reads the source (another import's worth of time "
        "and tokens). If you just want the story, use the button on the left "
        "to open the one that is already there.",
    '「仍然重新开卷」不会覆盖已有的那本 —— 会另存成一个新的项目名。':
        '“Open it again anyway” will not overwrite the existing one — '
        'it is saved under a new project name.',
    '打开「{name}」': 'Open “{name}”',
    '仍然重新开卷': 'Open it again anyway',
    '项目名已改成「{name}」—— 不会覆盖已经开过的那本':
        'Project name changed to “{name}” — the existing one is left untouched',
    '开卷被拦下（已经开过卷）': 'Import blocked (already opened)',
    '扫描已有项目失败': 'Failed to scan existing projects',
    '检查是否已经开过卷失败':
        'Failed to check whether this novel was already opened',
    '项目名称': 'Project name',
    '故事类型': 'Genre',
    '风格来源': 'Style source',
    '场景名称': 'Scene name',
    'auto 或手填场景名': 'auto, or type a scene name',
    '提示：选择 auto 会自动检测类型和风格':
        'Tip: "auto" detects genre and style from your files',
    '选择 AI 自动优化选项：': 'Choose what the AI should prepare:',
    '自动提取世界观和人物设定': 'Extract worldbuilding and characters',
    '生成故事进度表': 'Generate story progress table',
    '生成风格卡': 'Generate style card',
    '使用 AI 优化项目设定': 'Let AI refine the project settings',
    '提示：AI 会分析你的小说文件，自动提取设定和生成进度表':
        'Tip: the AI reads your files, extracts settings and builds a progress table',
    '请确认以下设置：': 'Please confirm:',
    '将创建项目：\n• 源文件夹：{src}\n• 项目名称：{name}\n'
    '• 故事类型：{genre}\n• 风格来源：{style}':
        'Will create the project:\n• Source folder: {src}\n• Project name: {name}\n'
        '• Story genre: {genre}\n• Style source: {style}',
    '提示：都选「自动判断」就交给 AI 读正文自己定；手动指定类型会跳过那一步的类型判定':
        'Tip: leaving both on "Auto-detect" lets the AI decide from the text; '
        'picking a genre skips the AI genre step.',
    # ── 故事类型 / 风格来源的人话名（**动态取值**：`t(_GENRE_LABEL[...])`，
    #    `i18n_check` 扫不到字面量，必须手工登记）──
    # [EN] ── Plain-language names for story type / style source (**dynamic values**:
    # [EN] `t(_GENRE_LABEL[...])`,
    # [EN] `i18n_check` cannot scan literals, must be registered manually) ──
    '自动判断（由 AI 读正文后决定）':
        'Auto-detect (the AI decides after reading the text)',
    '悬疑 · 单元剧': 'Mystery · Episodic',
    '自动判断（从正文里学笔法）':
        'Auto-detect (learned from the source text)',
    '朴素白描（不加修饰）': 'Plain and unadorned',
    '冷笔白描（短句、少形容词）':
        'Terse and cool (short sentences, few adjectives)',
    '华丽辞藻（长句、意象密）':
        'Ornate and lush (long sentences, dense imagery)',
    '自定义（在下方自己调）': 'Custom (tune it below)',
    '（未选择）': '(not chosen)',
    '（未填写）': '(not entered)',
    '小说世界AI模拟 v{VERSION}': 'Novel World AI Simulator v{VERSION}',
    '无法打开文件选择器: {ex}': 'Could not open the file picker: {ex}',
    '类型：{genre}  最近：{seen}': 'Genre: {genre}   Last run: {seen}',
    '日志目录：{path}': 'Log folder: {path}',
    '❌ 保存失败: {ex}': '❌ Save failed: {ex}',
    '上一步': 'Back',
    '下一步': 'Next',
    '开始摄取': 'Start import',
    '取消': 'Cancel',
    '正在分析小说文件...': 'Analyzing novel files…',
    '正在导入': 'Importing',
    '这可能需要几分钟时间': 'This may take a few minutes',
    '点击「开始摄取」开始导入过程': 'Click "Start import" to begin',
    '导入完成！': 'Import finished!',
    '提示：勾选「使用 AI 优化」后，摄取完成会停下来，'
    '你可以和 AI 对话把设定打磨到满意再进入运行界面':
        'Tip: with "Let AI refine" checked, the import pauses when done — '
        'chat with the AI to polish the settings before you enter the story.',

    # ── 开卷 · 摄取（进度条 + 日志 + AI 对话）──
    # [EN] ── Open Volume · ingestion (progress bar + log + AI dialogue) ──
    '开 卷 · 摄 取': 'New Story · Importing',
    '摄取进度': 'Import progress',
    '正在准备…': 'Getting ready…',
    '运行日志 · 含 AI 调用全过程': 'Run log · every AI call in full',
    'AI 优化对话': 'AI refinement chat',
    '输入修改意见，让 AI 打磨设定…': 'Type a change and let the AI refine it…',
    '完成优化并进入': 'Finish & enter story',
    '取消摄取': 'Cancel import',
    '已有一个摄取任务正在进行': 'An import is already running',
    '请先选择一个存在的小说文件夹': 'Please pick an existing novel folder first',
    'AI 优化中 —— 可对话打磨设定': 'AI refining — chat to polish the settings',
    '正在创建项目与运行文件夹…': 'Creating project and run folder…',
    '摄取完成，正在进入运行界面…': 'Import done — entering the story…',
    '自动摄取完成': 'Automatic import finished',
    '摄取已取消。': 'Import cancelled.',
    '摄取失败（详见日志）': 'Import failed (see log)',
    '摄取失败：{e}': 'Import failed: {e}',
    '摄取过程失败: {e}': 'Import failed: {e}',
    # 三级底图（2026-10-08）：开卷时那两步的界面文案
    # [EN] Three-level base map (2026-10-08): UI text for those two steps during Open Volume
    '正在生成三级底图（整体 / 局部 / 室内）…':
        'Generating the three-level base map (overall / local / indoor)…',
    '正在画地图底图（{n} 张）…': 'Painting base-map images ({n})…',
    '生成三级底图失败': 'failed to build the base map',
    # ── 天机 · 常规 页签（2026-10-08）──
    # [EN] ── Heavenly Secret · General tab (2026-10-08) ──
    '常规': 'General',
    '项目根目录': 'Projects folder',
    '留空 = 默认（桌面 · 小说世界AI模拟/Projects）':
        'empty = the default (Desktop · 小说世界AI模拟/Projects)',
    '你的小说都存在这个目录下（每本一个文件夹）。留空 = 默认的「桌面 · 小说世界AI模拟/Projects」':
        'All your novels live under this folder (one folder each). Leave it empty for the '
        'default: Desktop · 小说世界AI模拟/Projects',
    '★ **改完不用重启**：回到开始界面，书列表就是这个目录里的了（实测：`projects_dir()` 每次现读）。':
        '★ **No restart needed**: go back to the start screen and the book list is already '
        'that folder (verified: `projects_dir()` is read fresh every time).',
    '⚠ 已经打开的那本书**不会跟着搬** —— 它还在原来的位置，照常能读能写；下次开新卷才建到新目录里。「已删除备份」也随之改到新目录旁边。':
        '⚠ The book you have open now **does not move** — it stays where it is and keeps '
        'working; the next book you open is created in the new folder. The "deleted backups" '
        'folder moves alongside it.',
    '项目根目录改为 {p}': 'Projects folder changed to {p}',
    '✅ 项目根目录已改为 {p}（不用重启）':
        '✅ Projects folder is now {p} (no restart needed)',
    '⚠ 配置已改动（{items}）—— 需要重启程序才会生效':
        '⚠ Configuration changed ({items}) — the program must be restarted to take effect',
    '在这份日志里找……（不区分大小写，整行匹配）':
        'Search this log… (case-insensitive, whole line)',
    '对话日志 · 每次 LLM 交换全文': 'Dialogue log · every LLM exchange in full',
    '主日志 · 程序流水': 'Main log · program flow',
    '已 {n} 拍': '{n} beats so far',
    '{n} 条/页': '{n} per page',
    '← 上一页': '← Prev',
    '下一页 →': 'Next →',
    '⟳ 刷新': '⟳ Refresh',
    '主日志': 'Main log',
    '共 {n} 行 · 第 {p}/{q} 页': '{n} lines · page {p}/{q}',
    '命中 {m} 行 · ': '{m} hits · ',
    '〔地图底图〕{m}': '[map base] {m}',
    '地图底图没生成出来（{e}）—— 小地图会退回每天现摆位。'
    '开卷时生成、或删掉 `设定集/小世界地图.yaml` 后重开这一轮再试。':
        'The map base images were not generated ({e}) — the minimap falls back to '
        'laying out each day. Try again on a later round, or delete '
        '`设定集/小世界地图.yaml` and let it be rebuilt.',
    '画地图底图失败': 'failed to paint the base-map images',
    # 时间面板 + 日志对话框（2026-10-08）
    # [EN] Time panel + log dialog (2026-10-08)
    '（时辰未定）': '(hour not set)',
    '打开日志': 'opened the log viewer',
    '生成地图底图失败': 'failed to build the map base images',
    "🧾 日志": "🧾 Log",
    "日 志": "L O G",
    '看哪一份：': 'Which log:',
    '每页：': 'Per page:',
    '最新在前': 'Newest first',
    '最早在前': 'Oldest first',
    '自动刷新': 'Auto-refresh',
    '🔍 搜索': '🔍 Search',
    '转到': 'Go',
    '跳至': 'Jump to',
    '第 {p} / {q} 页': 'Page {p} / {q}',
    '这个日志文件还没出现（{n}）': 'That log file does not exist yet ({n})',
    '（这一页没有内容）': '(nothing on this page)',
    '打开这本小说的项目文件夹': "Open this novel's project folder",
    '刷新 LLM 过程失败': 'failed to refresh the LLM trace',
    '初始化 LLM 客户端失败': 'failed to initialise the LLM client',
    '条消息': 'message(s)',
    '花费 {c}': 'cost {c}',
    # ── 「跟大模型沟通到哪一步了」那行小字（v1.39）──
    # 这一行专门回答「现在是在跑还是卡住了、要不要联网、要不要花钱」，
    # 所以英文也要把这层意思说清，别直译成 "status"。
    # [EN] ── That small line "which step are we at in talking to the LLM" (v1.39) ──
    # [EN] This line specifically answers "is it running or stuck right now, does it need network, does it
    # [EN] cost money",
    # [EN] so the English must also convey that meaning, don't just translate it as "status".
    '待机 —— 还没开始': 'Idle — not started yet',
    '准备中 —— 先读本地文件': 'Getting ready — reading local files first',
    '本地处理：{label}（这一步不联网）':
        'Local step: {label} (no network call here)',
    '准备调用 AI：{label}': 'Calling the AI: {label}',
    '正在思考 · 等待回复（已等 0 秒 · {m} · {p}）':
        'Thinking · waiting for the reply (0s · {m} · {p})',
    '正在思考 · 等待回复（已等 {s} 秒 · {m} · {p}）':
        'Thinking · waiting for the reply ({s}s · {m} · {p})',
    '✓ 已回复 · 用时 {ms} ms · {tin}+{tout} token · 花费 ¥{c}':
        '✓ Replied · {ms} ms · {tin}+{tout} tokens · ¥{c}',
    '! 调用失败（第 {n}/{m} 次）': '! Call failed (attempt {n}/{m})',
    '，正在重试…': ', retrying…',
    '，不再重试': ', giving up',
    '已暂停：等你确认之后才会调用 AI':
        'Paused — the AI will not be called until you confirm',
    '轮到你 —— 打字下指令，AI 在等你':
        'Your turn — type an instruction, the AI is waiting',
    '✓ 摄取完成': '✓ Import finished',
    '✓ 全部完成': '✓ All done',
    '（这次没有拿到内容）': '(nothing was returned this time)',
    # ── ★ 报错与关键信息也进右侧「AI 优化对话」（2026-10-07）──
    #   用户：「如果有报错以及AI回复的关键信息 则请将其放到右侧AI优化对话的
    #   回复里 否则可能看不见」。`【系统】` 是这些气泡的**统一前缀** ——
    #   让它一眼区别于"AI 说的话"，不然它会冒充对话内容。
    # [EN] ── ★ Errors and key info also go into the right-side "AI optimization dialogue" (2026-10-07) ──
    # [EN] User: "If there are errors and key info from AI replies, please put them into the right-side AI
    # [EN] optimization dialogue
    # [EN] replies, otherwise they might not be seen". `【系统】` is the **unified prefix** for these bubbles
    # [EN] ——
    # [EN] so it stands out at a glance from "what the AI said", otherwise it would masquerade as dialogue
    # [EN] content.
    '【系统】': '[System] ',
    '✓ 设定提取完成 · 评档 {tier} · 人物 {n} 位 · 接下来可以在这里让我改设定':
        '✓ Settings extracted · grade {tier} · {n} characters · '
        'you can ask me to change them right here',
    '✓ 项目已创建：{p}': '✓ Project created: {p}',
    '未评': 'ungraded',
    # ── ★ 空正文：报的是"没救回来"，不是每一次尝试（2026-10-07）──
    #   用户：「[23:30:00] ⚠ 正文为空（撞到 max_tokens=2400…）**这一直在报错**
    #   这个要怎么修复」。根因不是功能坏了：`router` 会立刻**关掉思考重试**，
    #   真实日志里触发 101 次、失败 0 次 —— 但以前在**第一发失败时**就报红字，
    #   而"救回来了"一个字都不说。现在分岔：注定要被重试的那一发只是提示，
    #   只有真的没救回来才是错误。
    # [EN] ── ★ Empty body: it reports "not saved", not every attempt (2026-10-07) ──
    # [EN] User: "[23:30:00] ⚠ Body is empty (hit max_tokens=2400…) **this keeps erroring**
    # [EN] how to fix this". The root cause isn't a broken feature: `router` will immediately **disable
    # [EN] thinking and retry**,
    # [EN] in real logs it triggered 101 times, 0 failures —— but previously it showed red text on **the
    # [EN] first failed attempt**,
    # [EN] while saying nothing about "saved it". Now it branches: the attempt destined for retry is only a
    # [EN] hint,
    # [EN] only a true failure to save is an error.
    '⚠ 首次没拿到正文（额度被思考吃光）—— 正在关掉思考重试…':
        '⚠ Nothing came back on the first try (thinking ate the budget) — '
        'retrying with thinking off…',
    '[{ts}] ⚠ 首次没拿到正文（max_tokens={mt} 被思考吃光）—— 正在自动关掉思考重试（不用你管）':
        '[{ts}] ⚠ Nothing came back on the first try (max_tokens={mt} eaten by '
        'thinking) — retrying automatically with thinking off (nothing for you '
        'to do)',
    '[{ts}] ✓ 关掉思考重试成功，拿到正文了{extra}':
        '[{ts}] ✓ Retried with thinking off and got the text{extra}',
    '；已记住这个用途，以后直接关思考发，不再白烧一次':
        '; this purpose is remembered, so it will be sent with thinking off '
        'from now on — no more wasted first try',
    '[{ts}] ⚠ 正文为空（撞到 max_tokens={mt}，{tout} token 全用光{rz}）：'
    '额度被思考吃光，而且这次**不会**自动重试（关思考的开关关着 / 已经关过 / '
    '这个模型不支持关思考）—— 请把这个用途的额度调大，或打开「模型与额度」里的'
    '「空正文自动关思考重试」':
        '[{ts}] ⚠ Empty body (hit max_tokens={mt}; all {tout} tokens used{rz}): the '
        'budget was eaten by thinking, and this time there is **no** automatic '
        'retry (the thinking switch is off / thinking was already off / this model '
        'cannot disable thinking) — raise this purpose\'s budget, or turn on '
        '"retry with thinking off on empty body" under Model & budget',
    # ── 开卷向导第 2 步：项目名称默认用文件夹名（2026-10-06）──
    # [EN] ── Open Volume wizard step 2: project name defaults to the folder name (2026-10-06) ──
    '项目名称默认用你选的文件夹名，不对就直接改':
        'The project name defaults to the folder you picked — just edit it if it is off',
    '自动填写项目名称失败': 'Could not prefill the project name',
    '刷新项目名称失败': 'Could not refresh the project name',
    '⚠ 输出被长度上限截断，内容可能不完整':
        '⚠ The output hit the length cap — it may be incomplete',
    '⚠ 这次一个字都没拿到（额度被思考过程吃掉了）':
        '⚠ Nothing came back this time (the budget was spent on reasoning)',
    # ── 摄取日志里那两条（会画在日志栏里，所以要翻）──
    # [EN] ── The two entries in the ingestion log (they get drawn in the log pane, so they must be
    # [EN] translated) ──
    '，含思考内容': ', including reasoning tokens',
    '，且本次带思考内容（思考也占这个额度）':
        ' (this run also carried reasoning, and reasoning shares the same budget)',
    '[{ts}] ⚠ 正文为空（撞到 max_tokens={mt}，{tout} token 全用光{rz}）：'
    '多半是推理模型把额度吃在思考里了':
        '[{ts}] ⚠ Empty reply body (hit max_tokens={mt}; all {tout} tokens were '
        'spent{rz}) — most likely a reasoning model used the budget for thinking',
    '[{ts}] ⚠ 输出被截断（撞到 max_tokens={mt}）{rz}：'
    '长文/JSON 很可能不完整，详见下面那行「提取」提示':
        '[{ts}] ⚠ Output truncated (hit max_tokens={mt}){rz} — long text or JSON '
        'is likely incomplete; see the "extract" note below',
    # ── llm/replies.py（「要一份可用结果」的重试/抢救说明）──
    # 这些是**给人看的**（会折进开卷日志、状态栏），所以要翻译。
    # 判定/重试的说明**不是**给人看的，留在模块里不进这里。
    # [EN] ── llm/replies.py (retry/rescue description for "want a usable result") ──
    # [EN] These are **for humans** (they get folded into the Open Volume log, status bar), so they must be
    # [EN] translated.
    # [EN] The decision/retry descriptions are **not** for humans, they stay in the module and don't go
    # [EN] here.
    '（含思考内容）': ' (including reasoning)',
    'JSON 对象': 'JSON object',
    'JSON 数组': 'JSON array',
    '被长度上限截断': 'truncated by the length cap',
    '正文为空（额度被思考内容占掉）':
        'the reply body is empty (the budget went to reasoning)',
    '正文太短，只有 {n} 字': 'the reply is too short — only {n} characters',
    '没能解析出{label}': 'could not parse a {label}',
    '模型调用失败：{err}': 'The model call failed: {err}',
    '模型没给出可用的{label}（{why}）→ 已按 {bigger} token 上限重试一次':
        'The model gave no usable {label} ({why}) → retried once at a '
        '{bigger}-token cap',
    '重试也失败了：{err}': 'The retry failed too: {err}',
    '输出不完整，已按「最长可闭合前缀」抢救（末尾内容可能缺失，请核对）':
        'The output was incomplete; salvaged the longest closable prefix '
        '(the tail may be missing — please check)',
    '重试后仍不完整，已按「最长可闭合前缀」抢救（末尾内容可能缺失，请核对）':
        'Still incomplete after the retry; salvaged the longest closable '
        'prefix (the tail may be missing — please check)',
    '模型没有返回可用的{label} —— 原始文本已写进对话日志，可到「天机 · 日志」里查看':
        'The model returned no usable {label} — the raw text is in the '
        'dialogue log (Settings · Logs)',
    '✗ 失败 —— 详见左侧日志': '✗ Failed — see the log on the left',
    '已中止（没有发出任何请求）': 'Stopped (no request was sent)',
    'AI 体检失败': 'AI review failed',
    'AI 修改设定失败': 'AI failed to apply the change',
    '（AI 体检未完成，你可以直接输入修改意见。）':
        '(The AI review did not finish — you can still type your instructions.)',
    '（修改失败：{ex}）': '(Change failed: {ex})',
    '（AI 体检未能完成，你可以直接输入修改意见，我仍会尝试照办。）':
        '(The AI review did not finish — type your instructions and I will still try.)',
    '你可以说：把主角改个名字 / 加强主线悬念 / 补两条伏笔 / 世界观再冷一点。':
        'Try: rename the lead / sharpen the main suspense / add two hooks / '
        'make the world colder.',

    # ── 摄取阶段名（进度条 / 日志）──
    # [EN] ── Ingestion stage names (progress bar / log) ──
    '扫描文件夹': 'Scanning folder',
    '读取与分章': 'Reading and splitting chapters',
    '提取人物与世界观': 'Extracting characters and world',
    '判定故事类型': 'Detecting genre',
    '构建故事进度表': 'Building story progress table',
    '正文与进度对齐': 'Aligning text with the plot',
    '推断起始点': 'Inferring the start point',
    '推演开局方案': 'Drafting opening options',
    '评估资料档位': 'Grading the material',
    '冻结本地设定集': 'Freezing the local settings',
    '摄取完成': 'Import complete',

    # ── LLM 调用用途名（日志）──
    # [EN] ── LLM call purpose names (log) ──
    '提取设定': 'extract settings',
    '类型判定': 'genre',
    '风格卡': 'style card',
    '故事进度表': 'progress table',
    '正文对齐': 'text alignment',
    '开局方案': 'opening options',
    'AI 体检': 'AI review',
    '按指令改设定': 'apply instruction',
    '通用': 'general',

    # ── 任务介绍字段 ──
    # [EN] ── Task intro fields ──
    '项目': 'Project',
    '源文件夹': 'Source folder',
    '类型': 'Genre',
    '评档': 'Grade',
    '起始节点': 'Start node',
    'AI 优化轮次': 'AI refinement rounds',

    # ── 拾卷 ──
    # [EN] ── Pick Up Volume ──
    '拾 卷 · 继 续 已 有 项 目': 'Open Story · Existing projects',
    '暂无项目，请先开卷导入。': 'No projects yet — create one with New Story first.',
    '浏览其他项目…': 'Browse other projects…',
    '关闭': 'Close',

    # ── 天机（全局设置）──
    # [EN] ── Heavenly Secret (global settings) ──
    '天 机 · 全 局 设 定': 'Settings · Global',
    '界面语言': 'Interface language',
    '界面外观': 'Appearance',
    '界面透明度': 'Panel transparency',
    '透明度': 'Transparency',
    # ⚠ 2026-10-13 用户把**方向翻过来了**（"100%应该是完全透明 最低才是不透明"），
    #   原来那两条「100% = 完全不透 / 作用范围含所有对话框」已经**说反了**，
    #   产品不再引用 ⇒ 直接删掉，免得哪天被误用（新说法见文件末尾那一块）。
    # [EN] ⚠ 2026-10-13 the user **flipped the direction** ("100% should be fully transparent, the
    # [EN] minimum should be opaque"), so the old "100% = fully opaque / applies to all dialogs"
    # [EN] entries now say the **opposite**; the product no longer references them => delete them
    # [EN] outright so they can't be misused later (the new wording is in the block at the end of
    # [EN] this file).
    '文字与描边保持不透明；输入框有 {n}% 下限（要看清输入的字）':
        'Text and borders stay opaque; input fields keep a {n}% floor for legibility',
    '✅ 透明度已生效': '✅ Transparency applied',
    '接口配置': 'LLM connection',
    '演示模式 (MOCK_LLM)': 'Demo mode (MOCK_LLM)',
    '请求超时(秒)': 'Timeout (seconds)',
    '重试次数': 'Retries',
    '并发上限': 'Max concurrency',
    # ★ 2026-10-18：思考模式（`LLM_THINKING_MODE`）的三个选项与两段说明。
    #   键是**中文原文**，值给英文界面用；`.env` 里存的是 auto/off/always。
    # [EN] ★ 2026-10-18: the three thinking-mode options and two hints.
    '思考模式': 'Thinking',
    '自动（只关判定类）': 'Auto (off for verdict-type calls only)',
    '一律关（快且省）': 'Always off (faster, cheaper)',
    '一律开（连判定也不关）': 'Always on (even for verdicts)',
    '新版 DeepSeek Flash / V4 默认会"先想再写"：思考按输出计费，'
    '还和正文抢同一份额度（实测一句话能想出 3000+ token）。'
    '选「一律关」最省也最快，但人物决策可能变得毛躁；'
    '选「自动」只在判定类用途上关。改完下一拍生效，不用重启。':
        'New DeepSeek Flash / V4 models think before writing by default: thinking is billed as '
        'output and competes with the body for the same budget (one sentence can think for 3000+ '
        'tokens). "Always off" is the cheapest and fastest, but character decisions may get hasty; '
        '"Auto" only turns it off for verdict-type calls. Takes effect on the next beat, no restart.',
    '模型选择': 'Models',
    # ── 「拉取模型列表」与「测试」两个按钮（2026-10-06）──
    # 这两个按钮的结果文字里带**服务端原话**（`llm/probe.py` 拼的），
    # 那一部分走原文兜底、不登记 —— 报错信息翻译过来反而不好照着手改。
    # [EN] ── The "Fetch model list" and "Test" buttons (2026-10-06) ──
    # [EN] The result text of these two buttons contains **the server's own words** (assembled by
    # [EN] `llm/probe.py`),
    # [EN] that part falls back to the original and is not registered —— translated error messages are
    # [EN] actually harder to follow when fixing manually.
    '拉取模型列表': 'Fetch models',
    '测试': 'Test',
    '正在拉取模型列表…': 'Fetching the model list…',
    '❌ 拉取时出错：{err}': '❌ Fetch failed: {err}',
    '已替换不在列表里的模型名：{list}（记得点「保存」）':
        'Replaced model name(s) not in the list: {list} (remember to Save)',
    '正在测试「{m}」…': 'Testing "{m}"…',
    '这个档位还没填模型名 —— 先在上面选一个。':
        'No model name for this tier yet — pick one above first.',
    '❌ 测试时出错：{err}': '❌ Test failed: {err}',
    # ── 岔路口（走向选择面板，2026-10-06；2026-10-07 重做成单选 + 自定义）──
    #  ★ 2026-10-11：这一套面板**升格为通用提问对话框**了 ——
    #    岔路口 / 导演介入 / 预算耗尽 / 存档点 四处共用（`RunLoop._ask`
    #    → `NovelWorldApp._on_ask`）。所以下面几条不再只是"岔路口"的文案。
    # ★ 续跑时中栏的历史分界（2026-10-11）
    # [EN] ── Crossroads (direction selection panel, 2026-10-06; 2026-10-07 redone as single-choice +
    # [EN] custom) ──
    # [EN] ★ 2026-10-11: this panel set **was promoted to a general question dialog** ——
    # [EN] Crossroads / Director intervention / Budget exhausted / Save point all four share it
    # [EN] (`RunLoop._ask`
    # [EN] → `NovelWorldApp._on_ask`). So the entries below are no longer just "Crossroads" text.
    # [EN] ★ History divider in the middle column on resume (2026-10-11)
    '—— 以下是上一次演到这儿 ——':
        '— Above is where the previous run left off —',
    '—— 以下是上一次演到这儿（第 {n} 天）——':
        '— Above is where the previous run left off (day {n}) —',
    '—— 以上是上一次的记录 ——':
        '— End of the previous run —',
    # ★★ 「剧组 Agents」设置页（2026-10-11）
    #   ⚠ 下面最后那几条是**动态取值**（`catalog.WHEN_ZH` / `usage_options()` /
    #     「（没写）」兜底），`i18n_check` 扫不到字面量，**必须手工登记**。
    # ── 开卷向导第 4 步（剧组 Agents，2026-10-11）──
    # [EN] ★★ "Crew Agents" settings page (2026-10-11)
    # [EN] ⚠ The last few entries below are **dynamic values** (`catalog.WHEN_ZH` / `usage_options()` /
    # [EN] "(not written)" fallback), `i18n_check` cannot scan literals, **must be registered manually**.
    # [EN] ── Open Volume wizard step 4 (Crew Agents, 2026-10-11) ──
    '步骤 1/5：选择文件夹': 'Step 1/5: choose the folder',
    '步骤 2/5：项目设置': 'Step 2/5: project settings',
    '步骤 3/5：AI 优化设置': 'Step 3/5: AI optimization',
    '步骤 4/5：剧组 Agents（可以整步跳过）': 'Step 4/5: Crew agents (you may skip this step)',
    '步骤 5/5：确认并开始': 'Step 5/5: confirm and start',
    "这里的每一行是**这个剧组里的一个职位**（写小说的、改剧本的、场记、美术、审读…）。你可以给**这一本书**写一句：'这本书要它多做什么、少做什么'。\n· 你填了 → 就按你填的（只影响这一本）；\n· 没填、且勾了下面那个勾 → 摄取完成后由 AI 依据这本书的类型与风格替你推一句（推荐）；\n· 什么都不填又不勾 → 照「天机 · 剧组 Agents」里的软件默认跑。\n想改得更细（名字、系统提示词、出工时机），开完卷去「书斋 · 剧组 Agents」。": 'Each row is **one post in this crew** (novelist, screenwriter, continuity, art, script doctor…). For **this book** you may write one line: what it should pay more (or less) attention to.\n· You wrote it → it is used as-is (this book only);\n· Left blank with the box ticked → after ingestion an AI infers one line from this book\'s genre and style (recommended);\n· Blank and unticked → the software default from "Setting · Crew Agents" applies.\nTo go finer (name, system prompt, when it works), open the book and use "Study · Crew Agents".',
    '没填的那些，让 AI 依据这本书的类型与风格推断': "For the ones left blank, let an AI infer from this book's genre and style",
    '（不填 = 交给 AI 推断，或就用软件默认）': '(blank = let the AI infer, or keep the software default)',
    '正在为各个 Agent 推断本书的定制…': "Inferring this book's per-agent overrides…",
    '✓ 剧组 Agents：{n} 个职位记下了这本书的定制（可在「书斋 · 剧组 Agents」里接着改）': '✓ Crew agents: {n} post(s) recorded an override for this book (refine it later in "Study · Crew Agents")',
    '剧组 Agents：没有项目级定制，照软件默认跑': 'Crew agents: no per-book override; the software default applies',
    'AI 推断 Agent 定制失败（改用你的填写）': 'AI inference of agent overrides failed (your own entries still apply)',
    'Agent 定制没落盘（不影响开卷）': 'Agent overrides were not written (ingestion is unaffected)',
    '初始化 Agent 目录失败：{e}': 'Could not initialise the agents folder: {e}',
    '剧组 Agents': 'Crew Agents',
    '**这个软件有哪些职位**：每个职位的名字、作用、系统提示词。改这里等于改所有小说的默认；只改某一本请去「书斋 · 剧组 Agents」。': '**Which posts this software has**: each one\'s name, role and system prompt. Changing it here changes the default for every book; to change just one book, go to "Study · Crew Agents".',
    '这本书里各个 Agent 的定制：名字、作用、系统提示词。只写你改过的项，其余跟「天机 · 剧组 Agents」里的软件默认走；新建与删除只在软件层做。': 'Per-agent overrides for this book: name, role, system prompt. Only the fields you change are written; the rest follow the software default in "Setting · Crew Agents". Creating and deleting happens only at the software level.',
    '自建': 'Custom',
    '软件自带': 'Built-in',
    '本项目已定制': 'Overridden here',
    '（还没写系统提示词）': '(no system prompt yet)',
    '（这里还没有职位）': '(no agents here yet)',
    '共 {n} 个职位 · 第 {p}/{m} 页': '{n} agents · page {p}/{m}',
    '＋ 新建职位': '+ New agent',
    '自建职位在**每天收工**时出工一次，产物落在那一轮的运行文件夹里': "A custom agent works once a day, at wrap-up; its output lands in that run's folder.",
    '这里是**这一本书**的定制：只覆盖你改过的那几项，其余跟「天机 · 剧组 Agents」里的软件默认走。新建与删除只在软件层做 —— 那是"这个软件有哪些职位"的事。': 'These are **this book\'s** overrides: only the fields you change are written, the rest follow the software default in "Setting · Crew Agents". Creating and deleting happen only at the software level — that is "which posts this software has".',
    '文件目录：{p}': 'Folder: {p}',
    '每页 {n} 条': '{n} / page',
    # ★ 2026-10-11：分页那一行改成「标签写用途 + 选项只写数字」——
    #   原来那格下拉的**空标签**仍占 88px，写「每页 N 条」会被省略成「每」。
    # [EN] ★ 2026-10-11: the pagination row now uses "label says what it is + options are bare numbers" --
    # [EN] the dropdown's **empty label** still occupied 88px, so "每页 N 条" was ellipsized to "每".
    '每页': 'Per page',
    '上一页': 'Prev',
    '下一页': 'Next',
    '第 {p}/{m} 页': 'Page {p}/{m}',
    '删除这个自建职位': 'Delete this custom agent',
    '恢复软件默认（只影响这一本书）': 'Restore software default (this book only)',
    '删除自建职位': 'Delete custom agent',
    '职位：{n}（{s}.md）': 'Agent: {n} ({s}.md)',
    '目录：{p}': 'Folder: {p}',
    '删掉之后这个职位不会再出工；它不会进回收站。': 'After deletion this agent will not work again; it does not go to the recycle bin.',
    '已删除自建职位「{n}」': 'Deleted custom agent "{n}"',
    '没能删除：{why}': 'Could not delete: {why}',
    '「{n}」已回到软件默认（只影响这一本书）': '"{n}" is back to the software default (this book only)',
    '没能恢复：{why}': 'Could not restore: {why}',
    '英文标识（文件名）': 'English id (file name)',
    '例如 fact_checker': 'e.g. fact_checker',
    '名字': 'Name',
    '简介': 'Summary',
    '什么情况下使用': 'When it is used',
    '（没写）': '(none)',
    '出工时机': 'Works on',
    '模型档': 'Model tier',
    '产出交给': 'Output goes to',
    '新建职位': 'New agent',
    '编辑职位 · {n}': 'Edit agent · {n}',
    '本项目定制 · {n}': 'This book · {n}',
    '正文就是**系统提示词**；它会在每次出工前拼在该职位的提示词最前面。': "The body **is** the system prompt; it is prepended to that agent's prompt before every turn of work.",
    '这里只写**这一本书**要改的项；没改的跟软件默认。': 'Write only the fields **this book** changes; the rest follow the software default.',
    '系统提示词': 'System prompt',
    '名字不能空着': 'The name cannot be empty',
    '保存失败：{e}': 'Save failed: {e}',
    '已保存「{n}」': 'Saved "{n}"',
    '保存 Agent 设置失败': 'Failed to save agent settings',
    '读 Agent 设置失败：{e}': 'Failed to read agent settings: {e}',
    '每一拍都在场（"活着"本身）': 'On stage every beat (this is what "alive" means)',
    '每天出工一次': 'Works once a day',
    '导出/收尾时出工一次': 'Works once, at export / wrap-up',
    '全程在场（每拍都要看、要判断）': 'Always on (must watch and judge every beat)',
    '每一拍': 'Every beat',
    '每天开拍前': "Before each day's shoot",
    '每天收工时': "At each day's wrap-up",
    '导出时': 'At export',
    '按需触发': 'On demand',
    '岔路口 · 往哪走': 'Fork in the road',
    '故事走到一个分岔口：挑一个走向，导演会顺着它安排后面的戏；都不合意就自己写一句。':
        'The story has reached a fork. Pick a direction and the director will '
        'arrange what follows along it — or write your own if none of them fit.',
    '需要你定一下': 'Your call',
    '需要你定一下。': 'This one needs your call.',
    '自己定一个': 'Or write your own',
    '取 消（暂停推演）': 'Cancel (pause the run)',
    # ★ 提问对话框 —— 四个 kind 的题干与选项（2026-10-11）
    #   ⚠ 岔路口的**选项**不在这批里：那是导演现写的走向，翻不了。
    # [EN] ★ Question dialog —— prompts and options for the four kinds (2026-10-11)
    # [EN] ⚠ The Crossroads **options** are not in this batch: those are directions the director writes on
    # [EN] the fly, they can't be translated.
    '导演想介入': 'The director wants to step in',
    '剧情停滞太久，导演想插手改变方向 —— 要不要听它的？':
        'The plot has stalled for a long time and the director wants to change '
        'direction — go with it?',
    '听导演的': 'Follow the director',
    '按它的方案往下走（有人敲门把僵局打断）':
        'Go with its plan (someone knocks and breaks the deadlock)',
    '这次不用': 'Not this time',
    '跳过这次介入，照现在的方向接着演':
        'Skip this intervention and keep going the way it is',
    '今天的 token 用完了': "Today's token budget is used up",
    '本日已用 {used} / 上限 {cap} token —— 接着往下写，还是收工？':
        'Used {used} of {cap} tokens today — keep writing, or wrap up?',
    '接着写（预算翻一倍）': 'Keep writing (double the budget)',
    '把本日上限抬到 {cap2}，继续往下推演':
        "Raise today's cap to {cap2} and carry on",
    '今天先到这儿': "That's it for today",
    '停下这一轮，补落今天的稿子、写今日总结，然后按设置导出':
        'Stop this run, flush today\'s draft, write the daily summary, then '
        'export per your settings',
    '第 {day} 天 · 存档点': 'Day {day} · checkpoint',
    '按设置每 {every} 天在这里停一下（已落盘）—— 接着写吗？':
        'Your settings pause here every {every} day(s) (already saved) — keep writing?',
    '接着写': 'Keep writing',
    '什么都不改，直接往下推演': 'Change nothing and carry on',
    '停在这儿': 'Stop here',
    '推演暂停，你可以在「天机」里改参数，回头点「继续」接着跑':
        'The run pauses; tweak settings in the Setting panel and press Resume later',
    '在等你决定 —— 不点「确定」推演就一直停在这儿':
        'Waiting for you — the run stays parked until you press Confirm',
    '提交选择失败': 'Failed to submit the choice',
    '取消选择失败': 'Failed to cancel the choice',
    '{n} 秒后由导演按策略决定': 'The director decides by policy in {n}s',
    '还剩 {n} 秒，之后按策略自动决定': 'Auto-decides by policy in {n}s',
    '还剩 {m} 分 {s} 秒，之后按策略自动决定':
        'Auto-decides by policy in {m}m {s}s',
    '已停止自动决定 —— 你正在选，选好点「确定」':
        'Auto-decide stopped — you are choosing. Press Confirm when ready.',
    '不挑了，按策略自动决定': 'Skip — let the policy decide',
    '确 定': 'Confirm',
    '自己定一个走向': 'Write your own direction',
    '也可以自己写一句：你想让故事往哪儿走？（写了就以它为准，上面选哪条都不算）':
        'Or write it yourself: where should the story go? '
        '(If you write something, it wins over any option above.)',
    '先挑一条，或者自己写一句 —— 再点「确定」':
        'Pick one, or write your own — then press Confirm.',
    '提交走向失败': 'Failed to submit the direction',
    '提交自定义走向失败': 'Failed to submit your own direction',
    # 「当前故事发展」那一小块（2026-10-07）
    # [EN] The "current story development" little block (2026-10-07)
    '第 {d} 天 · {scene}': 'Day {d} · {scene}',
    '（场景未定）': '(scene not set yet)',
    ' · 在场：{who}': ' · present: {who}',
    '前情：{x}': 'So far: {x}',
    '拉取模型列表：{r}': 'Fetch models: {r}',
    # ── 书斋 · 自定义风格（2026-10-06）──
    # [EN] ── Study · custom style (2026-10-06) ──
    '自定义风格': 'Custom style',
    # ── 「还没配 LLM」引导框（2026-10-06）──
    # [EN] ── "LLM not configured yet" guide box (2026-10-06) ──
    '还没有配置 LLM': 'LLM is not configured yet',
    '这一轮还**没有可用的模型接口**，所以推演跑不起来。':
        'There is **no usable model endpoint** yet, so the simulation cannot run.',
    '现在能做什么：程序可以正常打开，也能翻看设定与文档；'
    '但人物不会真的思考 —— 出来的东西是**内置的演示语料**，'
    '不是你的故事。':
        'What still works: the app opens normally and you can read your settings '
        'and docs — but the characters do not actually think. What comes out is the '
        '**built-in demo corpus**, not your story.',
    '缺什么：{why}': 'What is missing: {why}',
    '（没说清）': '(not specified)',
    '怎么申请 API Key、怎么填进来：看使用说明的'
    '「2.4 API Key 获取」与「3.4 怎么把 Key 配进来」两节'
    '（README 旁边的 `使用说明.md`），里面按厂商列了网址与步骤 —— '
    'DeepSeek / OpenAI / Claude / Google / 微软 / 智谱 GLM / '
    '通义千问 / MiniMax 等都有。':
        'How to apply for an API key and how to plug it in: see sections '
        '"2.4 API Key Setup" and "3.4 How to Plug the Key In" in the manual '
        '(`User_Manual.md`), which list URLs and steps per vendor — '
        'DeepSeek / OpenAI / Claude / Google / Microsoft / Zhipu GLM / '
        'Qwen / MiniMax and more.',
    '点「去配置」直接打开「天机 · 推演服务LLM设定」；'
    '点「以后再说」就这样先用着，下次启动还会提醒你。':
        'Click "Configure now" to open Heavenly Secrets · LLM Access directly; '
        'click "Later" to keep using the app as-is — it will remind you again '
        'on the next launch.',
    '去配置': 'Configure now',
    # ── 开始界面右上角「帮助」+ 帮助面板的关键字检索 + 没配 LLM 的变灰（2026-10-06）──
    # [EN] ── Start screen top-right "Help" + help panel keyword search + graying out when LLM not
    # [EN] configured (2026-10-06) ──
    '❓ 帮 助': '❓ Help',
    '打开使用说明': 'Open the manual',
    '在说明书里检索关键字…': 'Search the manual…',
    '清除': 'Clear',
    '共 {n} 节': '{n} sections',
    '命中 {n} 节': '{n} matches',
    '只沾到一部分：{n} 节（下面这些不一定相关）':
        'Partial matches only: {n} section(s) — these may not be relevant',
    '没有找到包含「{q}」的章节': 'No section contains "{q}"',
    '换一个词试试（一个词往往比一句话准），或者清空检索框翻目录。':
        'Try a different word (one word usually beats a whole sentence), or clear '
        'the box and browse the contents.',
    '「{q}」在这一节出现 {n} 次': '"{q}" appears {n} time(s) in this section',
    '没有可用的模型接口': 'no usable model endpoint',
    'LLM 还没配置，「问个问题」暂时用不了。':
        'LLM is not configured, so "Ask a question" is unavailable for now.',
    'LLM 还没配置，「问个问题」用不了':
        'LLM is not configured — "Ask a question" is unavailable',
    '它要调模型照着《使用说明》答题。没配好之前，'
    '可以先用「帮助信息」页的关键词检索 —— 那个不调模型。':
        'It answers by calling a model against the manual. Until it is configured, '
        'use the keyword search on the "Help" page instead — that one calls no model.',
    '申请与填写步骤见使用说明的「2.4 API Key 获取」与「3.4 怎么把 Key 配进来」。':
        'For how to apply and fill it in, see "2.4 API Key Setup" and '
        '"3.4 How to Plug the Key In" in the manual.',
    '（配置好 LLM 之后，这里会显示问答记录）':
        '(Once LLM is configured, the Q&A log will show up here.)',
    '以后再说': 'Later',
    '还没有配置 LLM：当前只有演示数据与模拟运行。'
    '去「天机 · 推演服务LLM设定」填 API Key 与 Base URL，'
    '申请办法见使用说明「2.4 API Key 获取」。':
        'LLM is not configured: only demo data and simulated runs are available. '
        'Fill in API Key and Base URL under Heavenly Secrets · LLM Access; '
        'see "2.4 API Key Setup" in the manual for how to apply.',
    '自定义风格已更新': 'custom style updated',
    '模型测试 {label}「{m}」：{r}': 'Model test {label} "{m}": {r}',
    '「测试」真发一条最小请求，结果写在下面（不受「演示模式」影响）。':
        '"Test" sends one minimal request and writes the result right below it '
        '(demo mode does not affect it).',
    # ── 「没配模型」的启动提示（走全局消息框）──
    # [EN] ── Startup prompt for "no model configured" (goes through global message box) ──
    '尚未配置模型（{why}）—— 本次只提供演示数据与模拟运行，'
    '不会调用真实 AI。到「天机 · 推演服务LLM设定」填好 Base URL 与 API Key，'
    '用「拉取模型列表」挑一个模型、用「测试」确认连通即可。':
        'No model configured ({why}) — this session only provides demo data and '
        'simulated runs, no real AI is called. Open "天机 · 推演服务LLM设定", fill in '
        'the Base URL and API Key, pick a model with "Fetch models" and verify '
        'it with "Test".',
    '没有填 Base URL': 'no Base URL',
    '没有填 API Key': 'no API key',
    '三个档位的模型名都是空的': 'all three model names are empty',
    '模型已配置好 —— 已自动关掉演示模式（MOCK_LLM），'
    '本次保存生效后就会调用真实 AI。':
        'Models are configured — demo mode (MOCK_LLM) has been turned off '
        'automatically; real AI will be used once this save takes effect.',
    'LLM 配置检查失败': 'LLM configuration check failed',
    '华彩档模型': 'Premium model',
    '华彩档：关键事件/重要对话（~15%）': 'Premium: key events / dialogue (~15%)',
    '日常档模型': 'Daily model',
    '日常档：常规循环/日志整理（~55%）': 'Daily: routine loops (~55%)',
    '摘要档模型': 'Budget model',
    '摘要档：压缩/打分/后台（~30%）': 'Budget: compression / scoring (~30%)',
    '向量检索': 'Embeddings',
    '向量检索方案': 'Embedding provider',
    '关闭（关键词退化）': 'Off (keyword fallback)',
    '本地 Ollama': 'Local Ollama',
    '本地模型': 'Local model',
    'API 服务': 'API service',
    '运行模式': 'Run mode',
    # ── 运行模式：界面上只显示人话，不显示 story / open / story_day 变量值 ──
    # 后台 CFG('RUN_MODE') 存的一直是变量值，这里只管前台怎么念。
    # ⚠ 这几条是**动态取值**（`t(_MODE_NAME.get(...))`），i18n_check 扫不到字面量，
    #   必须手工登记 —— 换名字时两边都要改，否则英文界面里会冒出中文。
    # [EN] ── Run mode: the UI shows only plain language, not the story / open / story_day variable values
    # [EN] ──
    # [EN] The backend CFG('RUN_MODE') always stores the variable value, this only handles how the frontend
    # [EN] reads it out.
    # [EN] ⚠ These entries are **dynamic values** (`t(_MODE_NAME.get(...))`), i18n_check cannot scan
    # [EN] literals,
    # [EN] must be registered manually —— when renaming, both sides must be changed, otherwise Chinese will
    # [EN] pop up in the English UI.
    '走完故事（有终点）': 'Run to the end (has an ending)',      # story
    '不限期限（一直续写）': 'Open-ended (keeps going)',          # open
    '定期暂停（每几天停一次）': 'Pause every few days',           # story_day
    '未知模式': 'Unknown mode',
    # 每个模式的一句话解释（下拉框下面那行）。
    # ⚠ 英文**故意不写 "story" 这个词**：`verify_run_modes` 会把界面上出现的
    #   story / open / story_day 当"露出变量名"报错，散文里的 story 也得绕开 ——
    #   与其给校验脚本开一堆"这句是散文"的口子，不如把话说得干净些。
    # [EN] One-sentence explanation for each mode (the line below the dropdown).
    # [EN] ⚠ English **deliberately avoids the word "story"**: `verify_run_modes` will report
    # [EN] story / open / story_day appearing in the UI as "exposing variable names", so prose containing
    # [EN] story must also be avoided ——
    # [EN] rather than opening a bunch of "this sentence is prose" exceptions in the validation script,
    # [EN] it's better to phrase it cleanly.
    '照着已有的设定一路推演到剧情终点，然后收尾。':
        'Runs all the way to the ending, then wraps up.',
    '不设终点，故事一直往下续写，你想停才停。':
        'No ending — it just keeps going until you stop it.',
    '正常推演，每过 N 天（游戏里的天）自动暂停一次，等你确认再继续。':
        'Runs normally, pausing automatically every N in-game days '
        'for your confirmation.',
    # 兼容旧名（可能还有别处动态取到）
    # [EN] Compatible with old names (may still be dynamically fetched elsewhere)
    '走完故事': 'Run to the end',
    '不限期限': 'Open-ended',
    '定期暂停': 'Pause periodically',
    '【{name}】· {mode}': '【{name}】 · {mode}',
    '暂停间隔（天）': 'Pause interval (days)',
    '「暂停间隔」只在「定期暂停」模式下生效；「自动运行天数限制」0 = 不限':
        'Pause interval only applies in the "pause every few days" mode; '
        'an auto-run day limit of 0 means unlimited',
    '切换后界面立刻重建，不用重启；存进配置的是 zh / en':
        'Switching rebuilds the interface immediately (no restart needed); '
        'the config file stores zh / en',
    '中文': 'Chinese',
    # ── 输出语言（项目级，`util/outlang.py`）──
    # ⚠ 选项的**键永远是字面量**（auto/zh/en），显示名才走 t()。
    #   这几个是**动态取值**（`t(LABELS[...])`），i18n_check 扫不到，手工登记。
    # [EN] ── Output language (project-level, `util/outlang.py`) ──
    # [EN] ⚠ Option **keys are always literals** (auto/zh/en), only display names go through t().
    # [EN] These are **dynamic values** (`t(LABELS[...])`), i18n_check cannot scan them, register manually.
    '输出语言': 'Output language',
    '跟随界面语言': 'Follow the interface language',
    '跟随界面语言 —— 现在是「{lang}」（输出与界面同一种语言）':
        'Follows the interface language — currently {lang} (output and interface use '
        'the same language)',
    '固定用「{lang}」输出，不管界面是什么语言、原稿是什么语言':
        'Always writes in {lang}, regardless of the interface language or the language '
        'of the source material',
    '「输出语言」= 推演出来的叙事、文档、小结、建议用哪种语言写；'
    '原稿是别的语言也没关系。改完立刻生效，不用重启。':
        'Output language: the language used for the narrative, documents, summaries and '
        'suggestions this program produces. The source material may be in any language. '
        'Changes take effect immediately — no restart needed.',
    '「输出语言」= 推演出来的叙事、文档、小结、建议用哪种语言写。'
    '原稿是别的语言也没关系。':
        'Output language: the language used for the narrative, documents, summaries and '
        'suggestions this program produces. The source material may be in any language.',
    '自动运行天数限制': 'Auto-run day limit',
    '夜间暂停': 'Pause at night',
    '时间系统': 'Time system',
    '时间倍率': 'Time ratio',
    '心跳间隔(ms)': 'Tick interval (ms)',
    '预算控制': 'Budget',
    '每日 Token 预算': 'Daily token budget',
    '⚠️ 价格仅供参考，以服务商官方价格为准':
        '⚠ Prices are estimates — check your provider',
    '导演与合规': 'Director & compliance',
    '导演引擎': 'Director engine',
    '戏剧总闸': 'Drama level',
    '冲突频率': 'Conflict frequency',
    '0.3=平淡  0.6=适中  0.9=高强度': '0.3 = calm   0.6 = medium   0.9 = intense',
    '内容合规': 'Content compliance',
    '合规检测': 'Compliance check',
    '审查力度': 'Review level',
    '严格': 'Strict',
    '标准': 'Standard',
    '宽松': 'Relaxed',
    '日志设置': 'Logging',
    '日志级别': 'Log level',
    '调试模式': 'Debug mode',
    '保存': 'Save',
    '✅ 配置已保存': '✅ Settings saved',
    '✅ 语言已切换': '✅ Language switched',

    # ── 书斋（项目设置）──
    # [EN] ── Study (project settings) ──
    '书 斋 · {name}': 'Project Settings · {name}',
    '类型与风格': 'Genre & style',
    '类型风格': 'Genre',
    '历法显示': 'Calendar display',
    '自动推断': 'Auto',
    '年号纪年': 'Regnal years',
    '干支纪年': 'Sexagenary cycle',
    '现代日期': 'Modern date',
    '第 N 天': 'Day N',
    '运行边界': 'Run boundaries',
    '起始点': 'Start point',
    '从头开始': 'From the beginning',
    '接续': 'Continue',
    '主线吸附力': 'Plot adherence',
    '风格参数': 'Style parameters',
    '虐心程度': 'Angst',
    '幽默度': 'Humour',
    '爽点密度': 'Payoff density',
    '感情线占比': 'Romance ratio',
    '悬念密度': 'Suspense density',
    '世界观展开': 'Worldbuilding pace',
    '人物智商': 'Character IQ',
    '节奏感': 'Pacing',
    '慢热': 'Slow burn',
    '适中': 'Medium',
    '快节奏': 'Fast',
    '过山车': 'Rollercoaster',
    '张力曲线': 'Tension curve',
    '平淡': 'Flat',
    '中等': 'Medium',
    '自动': 'Auto',
    '✅ 项目设置已保存': '✅ Project settings saved',

    # ── 选项值（类型 / 风格 / 历法）──
    # [EN] ── Option values (type / style / calendar) ──
    '自动检测': 'Auto-detect',
    '悬疑·单元': 'Mystery (episodic)',
    '玄幻修仙': 'Xianxia / cultivation',
    '都市': 'Urban',
    '历史架空': 'Alternate history',
    '言情': 'Romance',
    '科幻': 'Sci-fi',
    '平淡白描': 'Plain',
    '冷笔白描': 'Cold and plain',
    '华丽辞藻': 'Ornate',
    '自定义': 'Custom',

    # ── 主界面 ──
    # [EN] ── Main UI ──
    '尚未开始': 'Not started yet',
    '地点待生成': 'Places not generated yet',
    # ── 大地图对话框（2026-10-12）：点小地图打开的那张细图 ──
    # [EN] ── The big-map dialog (2026-10-12): the detailed map opened by clicking the minimap ──
    '大地图': 'Large map',
    '地图 · {p}': 'Map · {p}',
    '关闭这张地图': 'Close this map',
    '打开大地图失败': 'Failed to open the large map',
    '画大地图失败': 'Failed to draw the large map',
    '（未定）': '(undetermined)',
    '图上这一处是「{p}」· 细致程度：{d} · 比例尺只表示相对比例（没有真实尺寸）。':
        'This spot on the map is "{p}" · Level of detail: {d} · '
        'the scale bar only shows relative proportions (there are no real dimensions).',
    # ── 大地图**画在画布上**的那些字（图例 / 信息框 / 指北针）──
    #   ⚠ 画布的字不在控件树里，`verify_ui_english` 扫不到它 ——
    #     所以这里更要主动登记（判据看不见 ≠ 用户看不见）。
    # [EN] ── The text the big map **draws on the canvas** (legend / info box / north arrow) ──
    # [EN]   ⚠ Canvas text is not in the control tree and `verify_ui_english` cannot see it -- so it is
    # [EN]     all the more important to register it here (criteria can't see it != the user can't see
    # [EN]     it).
    '图例': 'Legend',
    '北': 'N',
    '地点': 'Location',
    '建筑': 'Building',
    '通路': 'Path',
    '水系': 'Water',
    '街道': 'Street',
    '房间墙': 'Room walls',
    '整座建筑': 'Whole building',
    '屋内陈设': 'Indoor fixtures',
    '院子（露天）': 'Courtyard (open air)',
    '小建筑（缩略）': 'Small building (abbreviated)',
    '门（缺口 + 开合弧）': 'Door (opening + swing arc)',
    # 2026-10-22：图上那两条虚线是**通路**（廊 / 甬道），图例里补了这一条。
    # [EN] 2026-10-22: the two dashed lines are **paths** (corridors); this legend entry was added.
    '通路（虚线，从这里走到那里）': 'Path (dashed -- from here to there)',
    '比例尺（示意）': 'Scale bar (schematic)',
    '细致程度：{d}': 'Level of detail: {d}',
    '时间：{w}': 'Time: {w}',
    '（未记）': '(not recorded)',
    '（待定）': '(undetermined)',
    '（还没有地点设定）': '(no locations set yet)',
    '今天这一幕发生在哪儿，以及在场的人各在哪个位置。\n'
    '底图取自「设定集/小世界地图.yaml」；每次换场景重画。\n'
    '★ **点这张图**可以打开**大地图**（左上角有地点 / 时间 / 图例 / 比例尺）。':
        'Where today\'s scene takes place, and where each character present is. \n'
        'The base map comes from "settings/小世界地图.yaml"; redrawn on every scene change. \n'
        '★ **Click this map** to open the **large map** (with location / time / legend / scale bar in '
        'its top-left).',
    '尚无人物登场': 'No character on stage yet',
    '节点': 'Node',
    '张力 — · 事件 —': 'Tension — · Events —',
    '进度表 —': 'Progress table —',
    # ⚠ `'导演 · 未启动'` 这一条**删掉了**（2026-10-12）：运行界面「系统」面板里
    #   那一行本身被用户点名去掉了（「没有特别的意义」），代码里再也没有
    #   `t('导演 · 未启动')`。词表只留还在用的 key —— 留一条没人用的，
    #   下次搜"导演"时会以为界面上还有这行。
    # [EN] ⚠ The entry `'导演 · 未启动'` was **removed** (2026-10-12): the row itself in the run
    # [EN] UI's "System" panel was named by the user for removal ("it has no particular meaning"),
    # [EN] and there is no `t('导演 · 未启动')` left in the code. The table keeps only keys still in
    # [EN] use -- keeping an unused one would make the next search for "导演" think the row is still
    # [EN] on screen.
    '模型': 'Model',
    '（故事尚未开始 —— 点右上角「📖 起　笔」开始）':
        '(Story not started — click "Pen to paper" at the top right to begin)',

    # ── 剧本式叙事（界面标签；落盘文件里固定用中文，见 剧本输出格式.md）──
    # [EN] ── Scripted narrative (UI labels; on-disk files are always in Chinese, see 剧本输出格式.md) ──
    '场景': 'Scene',
    '出场': 'Enter',
    '退场': 'Exit',
    '旁白': 'Narration',
    '动作': 'Action',
    '心声': 'Inner voice',
    '同时': 'Meanwhile',
    '这几件事发生在同一时刻': 'These happen at the same moment',
    '切至': 'Cut to',
    '切回': 'Cut back',
    '事件': 'Event',
    '停顿': 'Beat',
    '标注': 'Note',
    '图': 'Still',
    '本幕依据': 'Based on',
    '在场': 'on stage',
    '场外': 'off stage',
    '别处': 'elsewhere',
    '读取叙事产物失败': 'failed to read the narrative output',

    # ── 导出（设计稿 §10.10）──
    # [EN] ── Export (design doc §10.10) ──
    '📤 导出': '📤 Export',
    '导 出 · {name}': 'Export · {name}',
    '开始导出': 'Start export',
    '① 本次要导出什么': '1. What to export',
    '② 导出到哪': '2. Where it goes',
    '③ 结束时自动导出': '3. Auto-export when a run ends',
    # ★★★ 导出三档的档名（2026-10-26 改名，`_STEM` 是唯一事实来源）：
    #   原始稿 / 原始稿加细节 / 最终改写稿。
    #   ⚠ 这套名字改过四轮，**每次改名都必须同步改这里** —— 名字是 `t()` 的 key，
    #     漏改的症状是"英文界面下档名冒出中文"，而界面判据只报几个字，很容易被当噪音忽略。
    #   ⚠ 英文译名要与 `User_Manual.md` 表格里的一致（Original draft / + details / Final rewritten）。
    # [EN] ★★★ The three export kinds (renamed 2026-10-26, `_STEM` is the single source of truth).
    # [EN] ⚠ The names have changed four times; **every rename must update this table too** --
    # [EN] the name is the `t()` key, so a missed update shows Chinese in the English UI.
    '最终改写稿': 'Final rewritten draft',
    '原始稿加细节': 'Original draft + details',
    '原始稿': 'Original draft',
    '运行报告': 'Run report',
    '写作指导': 'Writing guide',
    '（零成本）': '(free)',
    '（耗 token）': '(costs tokens)',
    # ⚠ 这三条是 `KIND_DESC` 的照抄 —— 改 `bundle.KIND_DESC` 就必须同步改这里，
    #   否则英文界面会显示整段中文说明（描述比标签长得多，更刺眼）。
    # [EN] ⚠ These three mirror `KIND_DESC`; changing it means changing these too.
    '按天装订的**原始稿**：一个字都不动，不剃细节、不润色、不合并。'
    '当初到底写了什么，以它为准':
        'The **original draft**, one day per section: not a character changed -- '
        'no detail stripping, no polishing, no merging. This is the authority on '
        'what was actually written.',
    '按天装订的**最终改写稿**：剃掉过程细节（在场/依据/机制备注/图片路径），'
    '读起来像小说，可直接改写。⚠ 开着重写开关时正文会被重写，'
    '要"一字不改"请看原始稿':
        'The **final rewritten draft**, one day per section: production details '
        '(cast list / per-scene basis / mechanism notes / image paths) stripped, '
        'so it reads like a novel and can be rewritten directly. '
        'Warning: with the rewrite switch on, the prose is rewritten -- '
        'for "not a character changed", use the original draft.',
    '按天装订的**原始稿加细节**：正文一字不改，'
    '另外留着过程细节，用来对照「这句是从哪条设定长出来的」':
        'The **original draft plus details**, one day per section: the prose is '
        'untouched, with production details kept alongside -- for tracing which '
        'setting a line grew from.',
    '概览、账单、人物表现与优化建议；跑完再看更有用':
        'Overview, billing, character performance and suggestions; best read after the run ends',
    '推演后的写作大纲，可直接当提纲用':
        'A writing outline derived from the run, usable as a synopsis',
    '最终改写稿额外出一份 LLM 润色稿（改写稿，另存不覆盖）':
        'Also produce an LLM-polished copy of the final rewritten draft '
        '(saved separately, never overwrites)',
    '本次还没跑完（报告与指导里注明「截至第 {n} 天」）':
        'This run is unfinished (the report and guide will note "up to day {n}")',
    '产物写到：{path}': 'Output goes to: {path}',
    '已落盘 {n} 天（第 1 ~ 第 {d} 天）': '{n} day(s) on disk (day 1 – {d})',
    '，正文约 {c} 字': ', about {c} characters',
    '还没落盘任何一天——导出会得到一份空稿，先推演一段再来':
        'No day written yet — you would get an empty manuscript; run the story a while first',
    '运行中途导出只纳入已完成的整天（循环在一天结束时才落盘）':
        'Exporting mid-run includes only complete days (a day is written when it ends)',
    '改动立即生效（写进配置文件）；手动导出不受这里影响，随时可用':
        'Changes take effect at once (written to the config file); manual export is always available',
    '至少选一样要导出的东西': 'Pick at least one thing to export',
    '导出失败': 'export failed',
    '导出出错：{ex}': 'Export failed: {ex}',
    '完成 {ok} / {total} 项': 'Done: {ok} / {total}',
    '导出产物': 'export outputs',
    '导出完成：{n} 项': 'Export finished: {n} item(s)',
    # ★ 2026-10-28：导出进度条上的「已用几秒 / 当前在做什么」（用户：「导出步骤卡死了」+
    #   「希望导出过程的进度条更细致一些」⇒ 秒数每秒跳一次，不依赖有没有新消息）。
    # [EN] Export progress: elapsed seconds / current micro-step.
    '已用 {s} 秒': '{s}s elapsed',
    '已用 {s} 秒 · 完成': 'Done in {s}s',
    '正在准备': 'getting ready',
    '更改自动导出开关': 'toggle auto-export preference',
    '还没有可导出的运行（先在运行界面推演一段）':
        'Nothing to export yet (run the story for a while first)',

    # ── 运行会话（§七）：新一轮 / 暂停 / 继续 / 停止 ──
    # [EN] ── Run session (§7): new round / pause / resume / stop ──
    '📖 起　笔': '📖 Pen to paper',
    '起　笔': 'Pen to paper',
    '开始推演一轮': 'Start one round',
    '先开卷导入小说': 'Import a story first',
    # ★ 2026-10-28（用户：「删了存档、重启之后推不动」）：盘上有书、这一次还没打开
    #   那一档的小字 —— 以前这一档走的是「先开卷导入小说」，让用户以为要重开一遍。
    # [EN] ★ 2026-10-28 (user: "deleted the saves, restarted, cannot start"): the wording for
    # [EN] "books exist on disk but none is open yet" -- this case used to show "Import a story
    # [EN] first", making the user think they had to open the book all over again.
    '接着上次那本书开始': 'Continue with your last book',
    '已开卷 · 点「起　笔」接着上次那本':
        'Volume opened · click "Pen to paper" to continue it',
    '选一本书再设置': 'Pick a book to configure',
    '选一本书回到推演': 'Pick a book to go back to',
    '还没有书 —— 先点「开　卷」导入一本': 'No books yet — click "Open Volume" to import one',
    '先在「拾　卷」里选一本书，再{what}': 'Pick a book in "Pick Volume" first, then {what}',
    '看本书设置': 'open this book\'s settings',
    '启动时接回上次打开的书': 'Reopened the last book at startup',
    '接回上次打开的书失败（不影响启动）：{e}':
        'Could not reopen the last book (startup is unaffected): {e}',
    '记「上次打开的书」失败（下次要手点拾卷）：{e}':
        'Could not remember the last opened book (you will need to pick it by hand next time): {e}',
    '⏸ 暂停': '⏸ Pause',
    '▶ 继续': '▶ Resume',
    '⏹ 停止': '⏹ Stop',
    '⏸ 暂停（与继续共用一个按钮）': '⏸ Pause (shares a button with Resume)',
    '运行中 · 第 {d} 天': 'Running · day {d}',
    '已暂停 · 第 {d} 天': 'Paused · day {d}',
    '已结束（{r}）': 'Finished ({r})',
    '已停止（{r}）': 'Stopped ({r})',
    '正在停止…': 'Stopping…',
    # ── 起笔的启动守卫（2026-10-12）──
    # 用户报的两件事：连点两次起笔 ⇒ 两轮同时在跑；点完没反应 ⇒ 以为没生效又点一次。
    # [EN] ── The launch guard for start-writing (2026-10-12) ──
    # [EN] The two things the user reported: clicking start-writing twice ⇒ two rounds running at once;
    # [EN] nothing happening after the click ⇒ assuming it did not take effect and clicking again.
    '正在装配这一轮的世界……装配完成就自动开演。':
        'Assembling this round\'s world… it starts playing automatically once assembly finishes.',
    '正在启动 —— 装配完成就自动开演（最多等 {n} 秒）':
        'Starting — it plays automatically once assembled (waiting up to {n} s)',
    '正在启动 —— 装配中 · 已 {n} 秒': 'Starting — assembling · {n} s elapsed',
    '上一趟「起笔」还在装配（已 {n} 秒）—— 再等一下，'
    '不会同时开两轮':
        'The previous start-writing is still assembling ({n} s) — give it a moment, '
        'two rounds never run at once',
    '已经在启动或推演中了 —— 不会同时开两轮':
        'Already starting or running — two rounds never run at once',
    '已经在启动或推演中了 —— 这一轮跑完（或先「停止」）再开下一轮。':
        'Already starting or running — finish this round (or press Stop) before starting the next.',
    '发现上一轮还在跑 —— 已让新的这一轮接管，'
    '旧的那一轮正在收尾':
        'The previous round was still running — the new one has taken over and the old one is wrapping up',
    '启动超时（已等 {n} 秒）—— 已停止等待，可以再点一次「起笔」重试':
        'Launch timed out ({n} s) — stopped waiting; click start-writing again to retry',
    '已取消这一趟启动 —— 不再等装配（可以再点一次「起笔」重试）':
        'This launch was cancelled — no longer waiting for assembly (click start-writing again to retry)',
    '⚠ 这一趟启动已经被取代（或者等超时了）—— 没有开演。':
        '⚠ This launch was superseded (or timed out) — it did not start playing.',
    '启动失败：{e}': 'Launch failed: {e}',
    '⏹ 取消启动': '⏹ Cancel launch',
    '不再等这一趟装配 —— 界面立刻回到可以重来的样子'
    '（后台那一趟会自己作废，不会偷跑）。':
        'Stop waiting for this assembly — the UI returns to a retryable state right away '
        '(the background pass voids itself and will not sneak in).',
    '起笔超时(秒)': 'Start timeout (s)',
    '起笔启动': 'Starting a round',
    '点「开始推演」之后**最多等多久**（秒）装配世界。'
    '超过这个时间界面就**停止等待**：状态条回到'
    '「未运行」，中栏留一条说明，可以再点一次「起笔」重试。\n'
    '**不会同时开两轮** —— 超时作废的那一趟就算后来装好了'
    '也会自己退场（它会发现令牌对不上）。\n'
    '正常机器十几秒就装完；老机器 / 项目在云盘上同步慢时'
    '再往上调。范围 20~3600，默认 180。':
        'How long at most to wait (seconds) for the world to be assembled after clicking "Start".\n'
        'Past this the UI **stops waiting**: the status bar goes back to "Stopped", a note stays in the\n'
        'middle column, and you can click start-writing again to retry.\n'
        '**Two rounds never run at once** — a launch voided by timeout exits by itself even if assembly\n'
        'later finishes (it notices the token no longer matches).\n'
        'A normal machine finishes in ten-odd seconds; raise this for old machines or projects syncing\n'
        'slowly on cloud drives. Range 20~3600, default 180.',
    # 日志里那条（不上屏，但 i18n 口径是"全项目"）
    # [EN] The log-only lines (not shown on screen, but the i18n scope is "whole project")
    '起笔启动超时': 'start-writing launch timed out',
    '起笔启动失败': 'start-writing launch failed',
    '启动新一轮失败': 'failed to start a new round',
    '启动被取代 —— 这一趟作废': 'launch superseded — this pass was voided',
    '触发"只留一个" —— 停掉上一轮':
        'triggered "keep only one" — stopping the previous round',
    '作废这一趟的运行文件夹': 'discarded this launch\'s run folder',
    '开场之后发现这一趟已作废 —— 不启动':
        'after the opening, this pass turned out to be voided — not starting',
    '（本轮已开始，等第一句叙事……）':
        '(This round has started — waiting for the first line…)',
    '这一轮还在跑 —— 先「停止」再开新一轮':
        'This round is still running — stop it before starting a new one',
    '先开一卷，才能开始推演': 'Open a story before running',
    '已停止 · 本轮落盘 {n} 天，产物已收尾':
        'Stopped · {n} day(s) written this round; outputs finalised',
    '暂停推演': 'pause the run',
    '继续推演': 'resume the run',
    '停止推演': 'stop the run',
    '开始新一轮推演': 'start a new round',
    '创建运行文件夹失败': 'failed to create the run folder',
    '创建运行文件夹失败：{e}': 'Could not create the run folder: {e}',
    '装配世界失败': 'failed to assemble the world',
    '保存本轮设置失败': 'failed to save this round\'s settings',
    '保存本轮设置失败：{e}': 'Could not save this round\'s settings: {e}',
    # 结束原因（主循环给的字符串）
    # [EN] End reason (string given by the main loop)
    '手动停止': 'stopped by user',
    '到达故事终点': 'reached the end of the story',
    '达到最大 tick 数': 'tick limit reached',
    '达到设定天数 {n}': 'day limit reached ({n})',
    'story 模式终点完成': 'story mode finished',
    'story_day 模式终点完成': 'story-day mode finished',
    '没有可用的事件循环': 'no event loop available',
    '已取消': 'cancelled',

    # ── 启动故事对话框（一轮 = 一次完整推演）──
    # [EN] ── Start story dialog (one round = one full simulation) ──
    '启动故事': 'Start story',
    '启动故事 · {name}': 'Start story · {name}',
    '开始推演': 'Start the run',
    '这一轮载入': 'This round loads',
    '（读不到设定集，请先完成开卷摄取）':
        '(Cannot read the settings — finish the import first)',
    '一轮 = 一次完整推演，会新建一个运行文件夹；跑完或停止后，下一轮重新设。':
        'One round = one complete run and creates a new run folder; '
        'after it ends or is stopped, the next round is configured afresh.',
    '本轮上限天数': 'Day limit this round',
    '每 N 天暂停': 'pause every N days',
    '上限天数 0 = 不限；「定期暂停」模式会按暂停间隔停下来等你确认。':
        'A day limit of 0 means unlimited; "Pause periodically" stops at the '
        'chosen interval and waits for you.',
    '风格控制（这一轮怎么讲）': 'Style controls (how this round is told)',
    '导演与预算': 'Director and budget',
    '这些都写进配置文件，本轮立即生效。':
        'These are written to the config file and take effect immediately.',
    '本轮上限天数：{n}': 'day limit this round: {n}',
    '不限': 'unlimited',
    '每天 token 上限': 'token limit per day',
    '已开始新一轮 · 第 {n} 次模拟': 'New round started · simulation #{n}',
    '载入设定': 'settings loaded',
    '位人物': 'character(s)',
    '个节点': 'node(s)',
    '装配世界失败：{e}': 'Could not assemble the world: {e}',
    '前台人物': 'front-stage characters',
    '看这一轮怎么跑': 'how this round runs',

    # ── 运行界面 · 配置自适应（随天机里的开关变化）──
    # [EN] ── Run UI · config adaptive (changes with the toggles in 天机) ──
    '运行配置': 'Run settings',
    '暂停间隔': 'Pause every',
    '天': 'day(s)',
    '自动运行上限': 'Auto-run limit',
    '开': 'on',
    '心跳间隔': 'Tick interval',
    '记忆检索': 'Memory search',
    'Token 预算': 'Token budget',
    '合规': 'Compliance',
    '合规 · {lvl}': 'Compliance · {lvl}',
    '调试模式 · 已开': 'Debug mode · on',
    '已关闭': 'Disabled',
    '每 {n} 天暂停': 'pauses every {n} day(s)',
    '自动 ≤ {n} 天': 'auto ≤ {n} day(s)',
    '导演已关': 'director off',
    '合规已关': 'compliance off',
    '📋 菜单': '📋 Menu',
    '💾 快照': '💾 Snapshot',
    '❓ 帮助': '❓ Help',
    '时间': 'Time',
    '小地图': 'Map',
    # ── 小地图的状态行（2026-10-06：矢量 + AI 摆位）──
    # [EN] ── Minimap status line (2026-10-06: vector + AI placement) ──
    '还没有地点设定 —— 开卷时导入「地点」就有了':
        'No places yet — import a folder that has a "places" file',
    '{n} 处地点 · 简化排布（没调用模型）':
        '{n} places · simple layout (no model was called)',
    '重画小地图失败': 'failed to redraw the map',
    '天气：雨 · 临河茶肆': 'Weather: rain · Riverside teahouse',
    '第3天·戌时(19:30)': 'Day 3 · 19:30',
    '风格控制': 'Story tone',
    '虐心': 'Angst',
    '幽默': 'Humour',
    '爽点': 'Payoff',
    '感情': 'Romance',
    '悬念': 'Suspense',
    '智商': 'IQ',
    '在场人物': 'On stage',
    '剧情': 'Plot',
    '节点 N07 破绽': 'Node N07 · The crack',
    '张力 0.6 · 事件 15': 'Tension 0.6 · Events 15',
    '风格：小虐·轻松': 'Tone: mild angst · light',
    '系统': 'System',
    '前台 4 · 后台 3': 'Foreground 4 · Background 3',
    '导演 · 运行中': 'Director · running',
    '导演 · 已停': 'Director · stopped',
    '输入命令（/help 查可用命令）':
        'Type a command (/help lists them)',

    # ── 对话插图（**项目级设置**，存在 .nwsproj 的 [项目] 对话图片）──
    # 四个选项名就是四个词：关闭 / ASCII 画 / PNG 矢量图 / 全彩文生图。
    # 「关闭」的英文沿用表里已有的 'Close'（对话框关闭按钮用的也是它）——
    # 同一个中文词在两种语境下要不同英文，而这张表是一对一的，
    # 所以靠选项说明把语义补清楚（英文说明里写明 "no images at all"）。
    # [EN] The four option names are just four words: off / ASCII art / PNG vector image / full-color
    # [EN] text-to-image.
    # [EN] "off" reuses the existing 'Close' in the table (the dialog close button also uses it) ——
    # [EN] The same Chinese word needs different English in two contexts, and this table is one-to-one,
    # [EN] so the semantics are clarified via the option description (the English description states "no
    # [EN] images at all").
    '对话图片': 'Dialogue images',
    '图片': 'Images',
    'ASCII 画': 'ASCII art',
    'PNG 矢量图': 'PNG illustration',
    '全彩文生图': 'AI full-colour',
    '肖像': 'Portrait',
    '不生成任何图片（含人物肖像）—— 最省，只有文字':
        'No images at all (portraits included) — cheapest, text only',
    '场景用字符画拼，占用最少也最难看；人物肖像仍走文生图':
        'Scenes as ASCII — smallest footprint, ugliest; portraits still AI-drawn',
    '场景用本地彩墨插画（不花 token）；人物肖像仍走文生图':
        'Scenes drawn locally in ink-and-wash (no tokens); portraits still AI-drawn',
    '场景与人物肖像都交给模型画 —— 最好看，耗 token 最多':
        'Scenes and portraits both AI-drawn — best looking, most tokens',
    '存进项目文件（.nwsproj），只影响这一个故事；人物肖像一律用文生图，'
    '在开卷时生成一次、之后各轮复用；模型不支持时明说，不塞本地画的头像凑数':
        'Stored in the project file (.nwsproj), affects this story only; '
        'portraits are always AI-drawn, generated once at import and reused '
        'every round; if the model cannot draw, we say so instead of '
        'substituting a locally drawn avatar',
    '（字符画读取失败）': '(could not read the character art)',
    '已存入项目文件：{items}': 'Saved to the project file: {items}',
    '项目设置没有改动': 'No changes to save',
    '❌ 改名失败：{why}': '❌ Rename failed: {why}',
    '📊 推演结果': '📊 Results',
    '推演结果 · {name}': 'Results · {name}',
    '自动导出设置': 'Auto-export settings',
    '结束时自动导出': 'Auto-export on finish',
    '勾了的档，这一轮点「停止」收工时会自动导出一份。改动立即生效（写进配置文件）。':
        'Ticked kinds are exported automatically when you press Stop. Changes take effect '
        'immediately (written to the config file).',
    '要现在手动出一份：用「推演结果」右上角的「导出」。':
        'To produce one right now: use "Export" at the top right of "Results".',
    '产物目录：{path}': 'Output folder: {path}',
    '预览来自最近一次装订的稿子；要按最新进度重出一份，用右上角「导出」。':
        'The preview shows the latest bound draft; to re-bind from the latest progress, '
        'use "Export" at the top right.',
    '还没有这份稿子 —— 点「生成」来出一份':
        'No draft yet -- press "Generate" to produce one',
    '装订失败：{ex}': 'Binding failed: {ex}',
    '生成': 'Generate',
    '更新': 'Update',
    '正在生成…（要花 token，别关这个框）':
        'Generating... (costs tokens; keep this dialog open)',
    '已经有一个在跑了，等它结束': 'One generation is already running; wait for it to finish',
    '⚠ 收工时的自动导出还在跑，等它结束再生成':
        '⚠ The finish-time auto-export is still running; wait for it before generating',
    '生成失败：{ex}': 'Generation failed: {ex}',
    '生成推演结果': 'Generate derivation result',
    'LLM润色稿': 'LLM-polished draft',
    '对「最终改写稿」跑一遍 LLM 润色（另存一份，不覆盖）':
        'Run an LLM polish pass over the rewritten draft (saved as a separate file, never overwriting)',
    '点一下就让模型写这一份（要花 token，等几十秒）':
        'One click lets the model write this piece (costs tokens, takes tens of seconds)',
    '看这一次推演已经出来的结果：原始稿 / 最终改写稿 / 原始稿加细节 / 运行报告 / 写作指导。\n零成本的三份打开就有；报告、润色稿、指导要点「生成」才调模型。\n右上角「导出」出正式文件，运行中途也能点 —— 只纳入**已落盘的完整天**。':
        'See what this run has already produced: raw / rewritten / reference drafts, run report, '
        'writing guide.\nThe three zero-cost drafts are there on open; the report, polished draft '
        'and guide only call the model when you press "Generate".\n"Export" at the top right writes '
        'the formal files -- clickable mid-run too, and only includes **fully persisted days**.',
    '〔插图〕{m}': '[image] {m}',
    '发送': 'Send',

    # ── 人物肖像（开卷时生成一次；文生图不可用就不插肖像）──
    # [EN] ── Character portraits (generated once at 开卷; if text-to-image is unavailable, no portrait is
    # [EN] inserted) ──
    '正在生成人物肖像（{n} 位）…': 'Drawing portraits ({n} people)…',
    '肖像：文生图不可用（{why}），正文里不插肖像图':
        'Portraits: text-to-image unavailable ({why}) — no portrait inserted',
    '生成肖像失败': 'Portrait generation failed',
    '肖像清单.md': 'portraits.md',
    '未命名': 'Untitled',
    '未设定': 'Not set',
    '未运行': 'Stopped',

    # ── 示例内容（演示模式）──
    # [EN] ── Sample content (demo mode) ──
    '雨脚敲着檐瓦，堂前一盏灯被风扑得晃了晃，影子跟着歪。\n\n'
    '「你今日话里有话。」\n\n'
    '「话就是话，哪来的里外。」\n\n'
    '（这件事，不能让他知道第三个人。）\n':
        'Rain tapped the eaves; the lamp in the hall swayed and the shadows leaned with it.\n\n'
        '"There is something behind your words today."\n\n'
        '"Words are just words. Nothing behind them."\n\n'
        '(He must not learn there was a third person.)\n',
    '主角': 'Shen Yan',
    '阿枝': 'A Zhi',
    '掌柜': 'Keeper',
    '伙计': 'Assistant',
    '沉默寡言': 'Taciturn',
    '嘴上不饶人': 'Sharp-tongued',

    # ── 小地图地点 ──
    # [EN] ── Minimap locations ──
    '书房': 'Study',
    '大堂': 'Hall',
    '庭院': 'Courtyard',
    '后院': 'Backyard',
    '灶间': 'Kitchen',
    '门楼': 'Gate',

    # ── 选项卡名 ──
    # [EN] ── Tab names ──
    '推演服务LLM设定': 'Simulation LLM Settings',
    '常见服务怎么填（Base URL 写到 /v1 或 /plan/v3 这一层，'
    '程序自己接 /chat/completions）：\n'
    '· DeepSeek：https://api.deepseek.com/v1\n'
    '· 腾讯 TokenHub（混元 Hy3）：'
    'https://tokenhub.tencentmaas.com/plan/v3，模型名 hy3\n'
    '别的服务照它的文档填。地址与 Key 填在**那一条模型**上，'
    '在「编辑模型」里点「拉取这家的模型名」，'
    '能列出名字就说明地址与 Key 都对。':
        'How to fill common services (write the Base URL down to the '
        '/v1 or /plan/v3 level; the app appends /chat/completions):\n'
        '- DeepSeek: https://api.deepseek.com/v1\n'
        '- Tencent TokenHub (Hunyuan Hy3): '
        'https://tokenhub.tencentmaas.com/plan/v3, model name hy3\n'
        'For other services follow their docs. Put the endpoint and key on '
        '**that model entry**, then click "Fetch this provider\'s model names" '
        'in "Edit model" - if it lists names, both the URL and the key are right.',
    '运行': 'Runtime',
    '导演': 'Director',
    '日志': 'Logging',

    # ── 向导细则 ──
    # [EN] ── Wizard details ──
    '选择小说项目文件夹，支持 .md / .txt / .docx / .html':
        'Choose the novel folder — .md / .txt / .docx / .html are supported',
    'E:\\我的小说\\悬疑故事': 'E:\\Novels\\mystery-story',

    # ── 日志与错误（随语言切换，便于统一阅读）──
    # [EN] ── Logs and errors (follow the language switch, for consistent reading) ──
    '保存全局设置': 'save global settings',
    '保存项目设置': 'save project settings',
    '打开全局设置': 'open global settings',
    '打开项目设置': 'open project settings',
    '保存配置失败': 'failed to save settings',
    '保存项目设置失败': 'failed to save project settings',
    '切换全屏失败': 'failed to toggle full screen',
    '打开文件夹选择器失败': 'failed to open the folder picker',
    '显示提示条失败': 'failed to show the snack bar',
    '注册 FilePicker 失败': 'failed to register FilePicker',
    '生成背景图失败': 'failed to generate the background image',
    '生成背景图（%s）…': 'generating background image (%s)…',
    '背景图已生成: %s': 'background image saved: %s',
    '确认最大化失败': 'failed to confirm maximize',
    '注册字体失败': 'failed to register fonts',
    '设置窗口图标失败': 'failed to set the window icon',
    '重建界面失败': 'failed to rebuild the view',
    '刷新向导内容失败': 'failed to refresh the wizard step',
    '同步 MCP 项目路径失败': 'failed to sync the MCP project path',
    '从文生图原图构建背景失败': 'failed to build the background from the AI source image',
    '没有文生图原图，改用程序化背景（兜底）':
        'no AI source image found; falling back to the procedural background',
    '背景图缺失，正从文生图原图构建：%s':
        'background missing; building it from the AI source image: %s',

    # ── LLM 能力（天机 · 推演服务LLM设定 → 模型能力 / 文生图）──
    # 说明：`llm/capabilities.py` 里拼出来的那几句（改了什么、依据哪个模型）
    # 带动态模型名，走的是原文兜底，这里不重复登记。这里只收**固定的界面文案**。
    # [EN] Note: the sentences assembled in `llm/capabilities.py` (what changed, which model it is based
    # [EN] on)
    # [EN] They carry dynamic model names and go through the raw-text fallback; not re-registered here.
    # [EN] Only **fixed UI text** is collected here.
    '模型能力': 'Model capabilities',
    # 四项能力的名字。它们取自 `llm/capabilities.CAP_META`，界面上经 `t()` 翻译 ——
    # 因为是**动态取值**，i18n_check 扫源代码扫不到，**必须在这里手工登记**。
    # （「文生图」既是开关名也是那一节的小标题，同一个词两种语境，英文用
    #   Text-to-image 两个位置都读得通。）
    # [EN] The names of the four capabilities. They come from `llm/capabilities.CAP_META` and are
    # [EN] translated in the UI via `t()` ——
    # [EN] Because they are **dynamically resolved**, i18n_check cannot find them when scanning the source,
    # [EN] so they **must be registered here manually**.
    # [EN] ("text-to-image" is both a toggle name and the section subtitle; the same word in two contexts,
    # [EN] in English
    # [EN] Text-to-image reads fine in both places.)
    '文生图': 'Text-to-image',
    '推理模型': 'Reasoning model',
    '思考开关': 'Thinking switch',
    'JSON 模式': 'JSON mode',
    'system 角色': 'System role',
    '按模型判定：{v}': 'According to the model: {v}',
    '（认不出这个模型，保留你填的值）':
        ' (model not recognised — keeping what you entered)',
    '识别到模型：{who}': 'Models detected: {who}',
    # `_clip()` 的省略后缀。它**会被人看到**（帮助面板左栏标题就靠它截断）——
    # 2026-10-06 `verify_ui_english` 在英文界面下抓到过「…（省略 5 字）」。
    # [EN] The ellipsis suffix of `_clip()`. It **will be seen by people** (the help panel's left column
    # [EN] titles rely on it for truncation) ——
    # [EN] On 2026-10-06 `verify_ui_english` caught "…（省略 5 字）" under an English UI.
    ' …（省略 {n} 字）': ' …({n} chars omitted)',
    # 帮助面板左栏的第一项（说明书正文之前那段合成的「导言」）
    # [EN] The first item in the help panel's left column (the synthesized "introduction" before the manual
    # [EN] body)
    '开篇': 'Preface',
    # `sim.setup.settings_summary()`：本轮载入什么的概括，会显示在对话框上
    # [EN] `sim.setup.settings_summary()`: a summary of what is loaded this round, shown on the dialog
    '人物 {n} 位': '{n} characters',
    '进度节点 {n} 个': '{n} plot nodes',
    '地点 {n} 处': '{n} places',
    '伏笔 {n} 条': '{n} foreshadows',
    '本地设定集里没有人物（{dir}）。请先在开卷向导里完成摄取，或检查「人物.yaml」。':
        'The local settings have no characters ({dir}). Finish Import first, or '
        'check "人物.yaml".',
    '人物.yaml 解析后仍为空 —— 检查文件格式（应为 `- 姓名: …` 的列表）。':
        '人物.yaml is still empty after parsing — check the format (it should be a '
        'list of `- 姓名: …` entries).',
    # 三档模型的名字（`_text_models` 里当标签用，会出现在「未能识别 …」那条提示里）
    # [EN] The names of the three model tiers (used as labels in `_text_models`, appear in the
    # [EN] "unrecognized …" notice)
    '华彩档': 'front tier',
    '日常档': 'daily tier',
    '摘要档': 'cheap tier',
    # 能力校验的备注 / 纠错说明 —— 都是**动态拼出来**再进消息框的，
    # `i18n_check` 扫不到，必须手工登记（2026-10-06 英文界面下露出中文才发现的）。
    # [EN] Notes / correction messages for capability validation —— all **dynamically assembled** before
    # [EN] entering the message box,
    # [EN] `i18n_check` cannot find them, so they must be registered manually (discovered on 2026-10-06
    # [EN] when Chinese leaked under an English UI).
    '演示模式（MOCK_LLM）：不联网，能力校验仍按模型名执行':
        'Demo mode (MOCK_LLM): offline — capability checks still run by model name',
    '尚无模型配置，跳过 LLM 能力校验':
        'No model configured yet — skipping the LLM capability check',
    '能力校验结果写回 .env 失败，请检查文件权限':
        'Could not write the capability result back to .env — check file permissions',
    '{label}：{names} 这一档不支持，三档不一致，已按最保守的取值（不支持）':
        '{label}: {names} does not support this, so the three tiers disagree — '
        'taking the conservative value (not supported)',
    '{label}：{names} 支持关掉思考，已按「能用就用」判定（每次都还会按当次请求的模型再确认）':
        '{label}: {names} can turn thinking off — going with "use it where it '
        'helps". Every request still re-checks against the model it is actually '
        'sent to.',
    '{label}：未能识别 {why}，保留你填的值（请自行确认）':
        '{label}: {why} not recognised — keeping the value you entered '
        '(please verify it yourself)',
    '文生图模型 {model} 不在支持出图的型号里（或本来就是聊天模型），「全彩文生图」会被降级':
        'Image model {model} is not in the list of models that can generate images '
        '(or it is a chat model), so "full-colour AI images" will be downgraded',
    '未声明「{label}」，按模型 {model} 自动填入：{want}':
        '"{label}" was not declared — filled in from model {model}: {want}',
    '「{label}」与模型 {model} 不符，已改回：{want}':
        '"{label}" does not match model {model} — reverted to: {want}',
    'LLM 能力校验：{n} 项与模型特性不符，已自动改回':
        'LLM capability check: {n} item(s) did not match the model and were reverted',
    'LLM 配置已变更 —— 需要重启程序才会生效':
        'LLM settings changed — restart the program to apply them',
    '已按模型 {who} 自动填入 LLM 能力：{detail}':
        'Filled in LLM capabilities from model {who}: {detail}',
    # 四项能力的说明（取自 `llm.capabilities.CAP_META` 的第 3 项，界面上经 `t()`）
    # [EN] Descriptions of the four capabilities (taken from item 3 of `llm.capabilities.CAP_META`,
    # [EN] translated in the UI via `t()`)
    '能否调 /images/generations 出图。关掉则「全彩文生图」这一档'
    '自动降级为本地 PNG 矢量图，肖像图出不来时只是不插肖像。':
        'Whether the model can call /images/generations. If off, the '
        '"full-colour AI images" option falls back to local PNG vector art, and '
        'no portrait is inserted when the image cannot be produced.',
    '模型自带思维链（deepseek-reasoner / o1 / o3 / R1 这类）。'
    '开启后请求里不再发送 temperature —— 这类模型会拒绝或忽略该参数。':
        'The model reasons internally (deepseek-reasoner / o1 / o3 / R1 and the '
        'like). With this on, `temperature` is no longer sent — such models reject '
        'or ignore it.',
    '支持 response_format={"type":"json_object"} 结构化输出。'
    '关掉则退回「在提示词末尾追加『请仅以 JSON 回答』」这条老路。':
        'Supports `response_format={"type":"json_object"}`. If off, we fall back to '
        'appending "answer in JSON only" to the end of the prompt.',
    '模型能关掉思考模式（发 thinking:{"type":"disabled"}，DeepSeek V4 系列支持）。'
    '开启后，「只要结论」的用途（进度评估、类型判定、正文对齐）会主动关掉思维链：'
    '它们不需要推理过程，而思考是连 max_tokens 一起吃的 —— 2026-10-06 实测，'
    '一句「判据满足了吗」让 deepseek-flash 思考 3233 token，把 2000 的额度整份'
    '用光，正文一个字都没写出来。不支持的模型（o1 / o3 / Claude…）别打开，'
    '它们不认识这个参数，发了可能直接 400。':
        'The model can turn thinking mode off (send thinking:{"type":"disabled"}; '
        'DeepSeek V4 series support this). With it on, "conclusion-only" tasks '
        '(progress check, genre detection, aligning text to nodes) turn the chain '
        'of thought off on purpose: they need no reasoning, and thinking is billed '
        'against max_tokens — measured on 2026-10-06, a single "is the criterion '
        'met?" made deepseek-flash think 3233 tokens, spend the whole 2000 budget, '
        'and write not one word of output. Do not enable it for models that do not '
        'support it (o1 / o3 / Claude…), they may return 400.',
    '接受 role=system 的消息。不支持时把系统提示并入首条 user 消息，'
    '否则有的服务会直接 400。':
        'Accepts `role=system` messages. When unsupported, the system prompt is '
        'merged into the first user message — otherwise some services return 400.',
    '尚未配置模型': 'No model configured yet',
    '支持': 'yes',
    '不支持': 'no',
    '未识别': 'unknown',
    '按模型名自动校验：不一致会改回并记进「消息」；认不出的不猜。':
        'Checked automatically against the model name: a mismatch is corrected '
        'back and reported in Messages; an unknown model is left as you set it.',
    # 「改了 XX，需要重启」这句里的配置名（同样是动态取值，扫不到要手工登记）
    # [EN] The config names inside the sentence "changed XX, restart required" (also dynamically resolved;
    # [EN] not scanned, must be registered manually)
    '接入协议': 'Provider',
    '请求超时': 'Timeout',
    '演示模式': 'Demo mode',
    '文生图模型': 'Image model',
    '文生图模型（IMAGE_AI_MODEL）': 'Image model (IMAGE_AI_MODEL)',
    '如 gpt-image-1 / dall-e-3；留空=不出图':
        'e.g. gpt-image-1 / dall-e-3; empty = no image generation',
    '文生图尺寸': 'Image size',
    '本页设置改动后需要重启程序才会生效':
        'Changes on this page take effect only after restarting the app',
    '⚠ LLM 配置已改动（{items}）—— 需要重启程序才会生效':
        '⚠ LLM settings changed ({items}) — restart the app to apply',
    '⚠ 当前模型未标记「支持文生图」（LLM_CAP_IMAGE=false）：'
    '「全彩文生图」会自动降级为 PNG 矢量图，肖像图出不来时'
    '只是不插肖像。换出图模型请到「天机 · 推演服务LLM设定」':
        '⚠ The current model is not marked as supporting text-to-image '
        '(LLM_CAP_IMAGE=false): the "AI full-colour" option falls back to a local '
        'PNG illustration and portraits use text instead. To switch the image '
        'model, go to Settings · LLM.',

    # ── 全局消息框（状态栏那块常驻的消息条）──
    # [EN] ── Global message box (the persistent message bar in the status area) ──
    '暂无消息': 'No messages yet',
    '共 {n} 条': '{n} message(s)',
    '共 {n} 条 · 未读 {u}': '{n} message(s) · {u} unread',
    '查看': 'View',
    '清空': 'Clear',
    '消 息 · 共 {n} 条': 'Messages · {n} total',
    '提示': 'Info',
    '完成': 'Done',
    '注意': 'Notice',
    '错误': 'Error',
    'LLM 能力校验失败': 'LLM capability check failed',
    '生成图标失败': 'failed to generate the app icon',
    '计算图标指纹失败': 'failed to compute the icon fingerprint',

    # ── 开卷「交给 AI 之前」的确认（同意门）──
    # 本地几步走完、第一次调用 LLM 之前停下来，把"传进来了什么"摊开，
    # 并对「正文外发」与「内容多→花 token」分别取同意。
    # [EN] ── 开卷 "before handing to AI" confirmation (consent gate) ──
    # [EN] After the local steps finish and before the first LLM call, stop and lay out "what was passed
    # [EN] in",
    # [EN] and obtain consent separately for "sending the body text out" and "more content → more tokens".
    '交给 AI 之前，先看看传进来了什么':
        'Before handing this to the AI, here is what was imported',
    '同意，开始 AI 处理': 'Agree — start AI processing',
    '不同意，取消': 'Do not agree — cancel',
    '文件：{n} 个（有内容 {m} 个）· 合计 {chars}':
        'Files: {n} ({m} with content) · {chars} in total',
    '- {cat}：{n} 个 · {chars}': '- {cat}: {n} file(s) · {chars}',
    '预计发出去：约 {tin} token 输入 + {tout} token 输出 · 按摘要档 {model} 约 ¥{cost}':
        'Estimated to send: ~{tin} input + {tout} output tokens · '
        'about ¥{cost} at the budget tier ({model})',
    '（未配置）': '(not configured)',
    '※ 源内容超过单次上限（提取设定最多读 {cap} 字），中间部分会被截断 —— '
    '只保留开头与结尾各一段。':
        'Note: the source exceeds the per-call limit ({cap} chars for setting '
        'extraction), so the middle will be cut — only the beginning and the end '
        'are kept.',
    '⚠ 含小说正文：{n} 个文件、共 {chars}':
        '⚠ Contains novel text: {n} file(s), {chars}',
    '这些正文内容会被发送到你所配置的大模型服务。{where}是否同意？':
        'That novel text will be sent to the model service you configured. '
        '{where}Do you agree?',
    '当前是演示模式（MOCK_LLM），不会真的联网。':
        'Demo mode (MOCK_LLM) is on — nothing actually leaves your machine.',
    '将发送到：{host}': 'Will be sent to: {host}',
    '我同意把小说正文发送给大模型':
        'I agree to send the novel text to the model',
    '⚠ 内容比较多：源文件共 {chars}（超过 {limit}）':
        '⚠ Quite a lot of content: {chars} in total (over {limit})',
    'AI 处理这一趟会消耗较多 token（本次预计约 ¥{cost}）。是否继续？':
        'A pass like this burns more tokens (about ¥{cost} this time). Continue?',
    '我同意这次可能产生较多 token 开销':
        'I accept the possible extra token cost',
    '没有需要特别确认的事项 —— 没读到正文，内容量也不大。':
        'Nothing to confirm — no novel text found and the volume is small.',
    '等你确认 —— 确认之前不会调用任何 AI':
        'Waiting for you — no AI is called until you confirm',
    '确认是否交给 AI': 'Confirm before sending to the AI',
    # 扫描器给的资料分类（出现在确认面板的明细里）
    # [EN] The scanner's data categories (appear in the confirmation panel's details)
    '正文': 'novel text',
    '人物': 'characters',
    '大纲': 'outline',
    '设定': 'worldbuilding',
    '伏笔': 'foreshadowing',
    '杂项': 'misc',

    # ── 日志页（日志目录改成可编辑 + 浏览）──
    # [EN] ── Log page (log directory made editable + browse) ──
    '日志目录': 'Log folder',
    '留空 = 程序目录下的 logs': 'Empty = the logs/ folder next to the app',
    '留空 = 程序目录下的 logs/（推荐）；改这项要重启程序才生效':
        'Empty = the logs/ folder next to the app (recommended); '
        'changes take effect after restarting',
    '无法打开文件选择器': 'Could not open the folder picker',

    # ── 拾卷（存档列表 + 详情）──
    # [EN] ── 拾卷 (save list + details) ──
    '拾 卷 · 存 档 列 表': 'R E S U M E · S A V E S',
    '选择小说': 'Novel',
    '请从左侧选择一个存档': 'Pick a save on the left',
    '该项目暂无存档': 'This novel has no saves yet',
    '打开选中项目': 'Open selected novel',
    '存档时间': 'Saved at',
    '最近剧情': 'Recent story',
    '运行小结': 'Run summary',
    '（无元信息）': '(no details)',
    '（无摘要）': '(no summary)',
    '（无法读取）': '(unreadable)',
    '（暂无每天的生活记录）': '(no daily records yet)',
    '（暂无运行小结）': '(no run summary yet)',
    # ── 帮助面板 / 命令框（v1.28）──
    # [EN] ── Help panel / command box (v1.28) ──
    '帮 助 · 使用说明': 'Help · User Manual',
    # ── 每轮开场（§3.6.1，2026-10-06）──
    # [EN] ── Each round's opening (§3.6.1, 2026-10-06) ──
    '已把本轮开场重新推到中栏': 'Pushed this round\'s opening back into the middle pane',
    # ── 中栏小说体（display/story_render.py，2026-10-06）──
    # 这些是**叙述脚手架词**：把场记式的 `主角（压低声）对阿枝：…` 写成
    # `主角压低声音，对阿枝说：「…」`。它们跟着界面语言走。
    # [EN] ── Middle column novel style (display/story_render.py, 2026-10-06) ──
    '{tone}，': '{tone}, ',
    '对{who}': ' to {who}',
    '说：': ' says: ',
    '心想：': ' thinks: ',
    '想起，': ' remembers, ',
    '走了进来': ' walks in',
    '走了出去': ' walks out',
    '就在这时，': 'Just then, ',
    '同一刻，': 'At that same moment, ',
    '天气': 'Weather',
    '依据': 'Basis',
    '打开开场': 'Opening',
    '没有在跑的故事': 'No story is running',
    '还没有在跑的故事 —— 开一轮才有开场':
        'No story is running yet — an opening appears once a round starts',
    '没有开场': 'No opening',
    '本轮没有开场.md —— 可能是关掉了「每轮开场」，或是旧的一轮':
        'This round has no 开场.md — either "Run opening" is off, or this is from '
        'an older round',
    '打开帮助': 'Open help',
    '已打开帮助': 'Help opened',
    # ── LLM 用量报表（2026-10-10）──
    # 运行界面那一行的链接、以及对话框里的标题。
    # ⚠ 对话框内部的表头文案**不在**这里 —— 它要中英双语**同时**写进
    #   xlsx（`export/usage_report.py` 的 `L`），而这里只管界面。
    # [EN] ── LLM usage report (2026-10-10) ──
    # [EN] The link on the run UI row, and the title in the dialog.
    # [EN] ⚠ The table header text inside the dialog is **not** here —— it must be written into
    # [EN] xlsx in both Chinese and English **simultaneously** (the `L` in `export/usage_report.py`), while
    # [EN] this only covers the UI.
    '用量': 'Usage',
    '查看用量': 'View usage',
    '查看 LLM Token 用量与费用（软件整体 / 各项目）':
        'LLM token usage and cost (whole app / per project)',
    # ── 用量对话框**本体**（2026-10-10 补）──
    #   ★ 这一窗原来是**整窗硬编码中文**的 —— 产品里唯一一个没做双语的窗口，
    #     而根因不是"忘了翻"，是**判据从来没打开过它**（`verify_ui_english` 的
    #     清单里没有它，它自己还因为用了 Flet 1.0 不存在的 API 一次都没打开成功过）。
    #     ⇒ 补文案的同时，把它加进了 `verify_ui_english`，否则"翻了"同样没人守。
    #   ⚠ 下面几个**四字表头**既是界面表头、又同时是「划分」下拉的显示名
    #     （`t(by)` 里的 `by` 是变量 ⇒ `i18n_check` 看不见它，只能靠人记住）。
    #     `模型 / 日期 / 模块 / 推演任务` 必须与 `llm/usage.BY_EN`（xlsx 用的那套）
    #     **逐字一致**：同一件事在两个地方翻成两个词，比不翻更让人困惑。
    # [EN] ── The usage dialog **itself** (added 2026-10-10) ──
    # [EN] ★ This window was originally **entirely hardcoded in Chinese** —— the only window in the product
    # [EN] without bilingual support,
    # [EN] and the root cause was not "forgot to translate", but that **the criterion never opened it**
    # [EN] (`verify_ui_english`'s
    # [EN] list did not include it, and it itself had never once opened successfully because it used an API
    # [EN] that does not exist in Flet 1.0).
    # [EN] ⇒ Along with adding text, it was added to `verify_ui_english`, otherwise "translated" would
    # [EN] likewise be unguarded.
    # [EN] ⚠ The **four-character headers** below are both UI table headers and the display names of the
    # [EN] "partition" dropdown
    # [EN] (the `by` in `t(by)` is a variable ⇒ `i18n_check` cannot see it, so it relies on people
    # [EN] remembering).
    # [EN] **word for word**: the same thing translated into two different words in two places is more
    # [EN] confusing than not translating.
    'LLM 用量': 'LLM Usage',
    '软件整体': 'Whole app',
    '划分': 'Group by',
    '自': 'Since',
    '全部': 'All',
    '导出语言': 'Export language',
    '导出 xlsx': 'Export xlsx',
    '已导出：{name}': 'Exported: {name}',
    '导出失败：{e}': 'Export failed: {e}',
    '日期': 'Date',
    '模块': 'Module',
    '推演任务': 'Run',
    '（还没有记录）': '(no records yet)',
    '（这项还没有记录）': '(no records for this yet)',
    '← 先选一张卡片': '← pick a card first',
    '（没有明细）': '(no details)',
    '（没有调用记录）': '(no calls recorded)',
    # 「未标」这两条：数据层拼出来的标签（`llm/usage.UNLABELED`），界面只翻显示那一份
    # [EN] The two "未标" entries: labels assembled in the data layer (`llm/usage.UNLABELED`); the UI only
    # [EN] translates the displayed copy
    '（未标）': '(untagged)',
    '（未标：{p}）': '(untagged: {p})',
    '指标': 'Metric',
    '值': 'Value',
    '用途': 'Purpose',
    '入': 'In',
    '出': 'Out',
    '费用': 'Cost',
    '调用次数': 'Calls',
    '输入 Token': 'Input tokens',
    '输出 Token': 'Output tokens',
    '合计 Token': 'Total tokens',
    '涉及模型': 'Models',
    '涉及模块': 'Modules',
    '涉及 Agent': 'Agents',
    '日期范围': 'Date range',
    '{n} 次 · {c}': '{n} calls · {c}',
    '{n} 次 · {tok} · {c}': '{n} calls · {tok} · {c}',
    # ── 删掉一个项目的用量记录（用户 2026-10-10：「最左边一列的内容允许删除」）──
    #   确认框里那几句的用意与拾卷删存档一致：**把要删的东西列清楚**再问。
    # [EN] ── Delete a project's usage records (user 2026-10-10: "the leftmost column's content may be
    # [EN] deleted") ──
    # [EN] The intent of the sentences in the confirmation box matches deleting saves in 拾卷: **list clearly
    # [EN] what will be deleted** before asking.
    '删除这个项目的用量记录': 'Delete the usage records of this project',
    '项目：{name}': 'Project: {name}',
    '将删除 {n} 次调用记录 · 合计 {c}':
        'This removes {n} call records · {c} in total',
    '只删统计台账里的记录 —— 小说项目本身一个字都不会动。':
        'Only the records in this usage ledger are removed — '
        'your novel projects are not touched at all.',
    '删掉之后无法恢复。': 'This cannot be undone.',
    '已删除 {n} 条用量记录': 'Deleted {n} usage records',
    '删除失败 —— 台账库写不进去（被占用？详见日志）':
        'Delete failed — the usage database could not be written '
        '(locked? see the log)',
    # 帮助面板里的插图加载失败时的降级文案（说明书插图走相对路径）
    # [EN] Fallback text in the help panel when an illustration fails to load (manual illustrations use
    # [EN] relative paths)
    '（这张插图没能加载 —— 图片在 assets/images/manual/ 下）':
        '(This figure could not be loaded — images live under '
        'assets/images/manual/)',
    # 天机 · 日志：对话日志（每次 LLM 交换的全文 + 界面对话）
    # [EN] 天机 · Logs: conversation log (full text of each LLM exchange + UI conversation)
    '对话日志': 'Dialogue log',
    '每次 LLM 请求/响应（全文）与界面上的作者 ↔ AI 对话，'
    '自动记在这个文件里（与主日志同目录）：':
        'Every LLM request and response (in full), plus the author ↔ AI chat from the '
        'interface, is written to this file automatically (same folder as the main log):',
    # ── 时间系统·节奏（全是动态插值，i18n_check 扫不到，手工登记）──
    # [EN] ── Time system · pacing (all dynamic interpolation, i18n_check cannot scan, registered manually)
    # [EN] ──
    '一拍': 'Beat',
    '一拍(故事秒)': 'Beat (story seconds)',
    '安静门槛(故事分)': 'Quiet threshold (story minutes)',
    '安静门槛': 'Quiet threshold',
    # ⚠ 2026-10-26 口径变了（日界 = 拍预算用完）：故事钟不再按"真实流逝 × 倍率"走，
    #   所以旧那句「一个故事日约 24 小时」已经不成立 —— 一天是这一站的拍数那么多拍。
    # [EN] ⚠ 2026-10-26 the basis changed (the day ends when the beat budget runs out): the story
    # [EN] clock no longer follows "real elapsed x multiplier", so "a story day takes about 24
    # [EN] hours" no longer holds -- a day is as many beats as this station's budget.
    '一拍约 {r} · 一个故事日约 {d}':
        'one beat ≈ {r} · a story day takes about {d}',
    '{v:.1f} 真实秒': '{v:.1f} real seconds',
    '不到 0.1 真实秒（跑起来由模型速度决定）':
        'under 0.1 real seconds (in practice the model speed decides)',
    '{v:.1f} 小时': '{v:.1f} hours',
    '{v:.0f} 分钟': '{v:.0f} minutes',
    '{v:.0f} 秒': '{v:.0f} seconds',
    '「时间倍率」= 1 真实秒走多少故事秒。1 = 实时（一个故事日约 24 小时）；'
    '60 = 一个故事日约 24 分钟':
        'Time ratio = how many story seconds pass per real second. 1 = real time (a story '
        'day takes about 24 hours); 60 = a story day takes about 24 minutes',
    '「时间倍率」= 演出速度：数字越大，拍来得越快（每拍等 BEAT_SECONDS ÷ 倍率 真实秒）。'
    '⚠ 它**不再**决定故事时间 —— 故事时间由「这一站的跨度」决定（一场 2 小时、数月 90 天）':
        'Time ratio = showing speed: the larger, the faster beats come (each beat waits '
        'BEAT_SECONDS / ratio real seconds). ⚠ It no longer decides story time -- that comes '
        'from the station\'s span (a scene 2 hours, months 90 days)',
    '「一拍」= 人物多久动一次脑子（也就是多久花一次钱）。'
    '它只决定**演出节拍**，不决定故事时间；改小会更话密，改大会更沉默。'
    '「心跳间隔」只是循环多久醒一次，一般不用动':
        'Beat = how often a character thinks again (and thus how often money is spent). It sets '
        'only the **showing tempo**, not story time; smaller is chattier, larger is quieter. The '
        'heartbeat interval only controls how often the loop wakes up — you normally never touch it',
    '模型客户端没建起来（{e}）—— 人物将无法思考与说话。'
    '检查「天机 · 推演服务LLM设定」里的地址与密钥。':
        'The model client could not be created ({e}) — characters will be unable to think '
        'or speak. Check the address and key under Settings · LLM access.',
    '初始化模型客户端失败': 'Failed to initialise the model client',
    '初始化模型客户端失败：{e}': 'Failed to initialise the model client: {e}',
    # ── 拾卷 · 删除存档 / 删除小说（危险操作，文案要说清后果）──
    # [EN] ── 拾卷 · Delete save / delete novel (dangerous operations; the text must state the consequences
    # [EN] clearly) ──
    '确认删除': 'Delete',
    '删除这个存档': 'Delete this save',
    '删除这本小说': 'Delete this novel',
    '删掉这一轮存档？': 'Delete this save?',
    '删掉整本小说？': 'Delete the whole novel?',
    '存档：{name}': 'Save: {name}',
    '小说：{name}': 'Novel: {name}',
    '路径：{path}': 'Path: {path}',
    '里面有 {n} 个文件，共 {sz}': 'It holds {n} files, {sz} in total',
    '设定集、肖像、全部 {n} 轮存档一起删，共 {c} 个文件 / {sz}':
        'Settings, portraits and all {n} saved rounds go with it — '
        '{c} files, {sz} in total',
    '这一轮会**移到「已删除备份」**（项目目录的旁边）—— '
    '反悔了可以手工搬回来。同一本书的其他轮次不受影响。':
        'This round is **moved to “deleted backups”** (next to the projects folder) — '
        'you can move it back by hand if you change your mind. Other rounds of this '
        'book are untouched.',
    '会**移到「已删除备份」**（项目目录的旁边）—— 反悔了可以手工搬回来。':
        'It is **moved to “deleted backups”** (next to the projects folder) — '
        'you can move it back by hand if you change your mind.',
    '要删的是整整一本书（含全部轮次与设定），所以还要**手打一次书名**才让点确认。':
        'This removes a whole book (every round and its settings), so you must also '
        '**type the book name** before the button unlocks.',
    '在这里打出「{w}」以确认': 'Type “{w}” here to confirm',
    '备份目录：{path}': 'Backups folder: {path}',
    '已把存档「{name}」移到已删除备份：{path}':
        'Moved the save “{name}” to deleted backups: {path}',
    '已把《{name}》移到已删除备份：{path}':
        'Moved “{name}” to deleted backups: {path}',
    '没能删掉：{why}': 'Could not remove it: {why}',
    # 删掉最后一本小说之后：开始界面要跟着熄火（菜单状态与盘面同步）
    # [EN] After deleting the last novel: the start screen must shut down accordingly (menu state
    # [EN] synchronized with the board)
    '已删除最后一本小说 —— 开始界面里「拾卷」「书斋」「回卷」已随之置灰。备份在：{path}':
        'The last novel was removed — "Open Story", "Studio" and "Resume" are now '
        'greyed out on the start screen. Backups are in: {path}',
    '小说都被删掉了 —— 「拾　卷」已置灰，要重新开始请点「开　卷」':
        'All novels are gone — "Open Story" is now greyed out. '
        'Click "New Story" to start again.',
    '重建开始界面失败': 'failed to rebuild the start screen',
    '先在上面选一本小说。': 'Pick a novel above first.',
    # 天机 · 日志：界面构建时间（用来分辨窗口新旧）
    # [EN] 天机 · Logs: UI build time (used to tell old and new windows apart)
    '界面构建': 'UI build',
    '界面源码最后改动：{stamp}（和窗口标题里那个时间对一下 —— '
    '不一样就说明这个窗口是改之前启动的，重启即可）':
        'UI source last changed: {stamp} (compare it with the time in the window title — '
        'if they differ, this window was started before the change: just restart)',
    '未知': 'unknown',
    # ── 拾卷 · 三栏（① 小说 / ② 存档 / ③ 存档内容）──
    # [EN] ── 拾卷 · Three columns (① novel / ② saves / ③ save contents) ──
    '① 小说': '① Novel',
    '② 存档': '② Saves',
    '③ 存档内容': '③ Save contents',
    '点一本，中间那栏就换成它的存档。': 'Click one and the middle column switches to its saves.',
    '这本书跑过的每一轮，最新的在最上面。点一条看右边。':
        'Every round this book has run, newest on top. Click one to read it on the right.',
    '选中那一轮的世界：元信息、最近剧情、运行小结。':
        'The world as of that round: metadata, latest narrative, run summary.',
    '（先在中间选一条存档）': '(pick a save in the middle column first)',
    '创建 {t}': 'Created {t}',
    '{n} 轮存档': '{n} saves',
    '还没跑过': 'never run yet',
    '这本书还没跑过 —— 存档在第一次推演之后出现。':
        'This book has not run yet — saves appear after the first round.',
    '这本书还没有存档': 'This book has no saves yet',
    '先在左边选一本小说。': 'Pick a novel on the left first.',
    '删除这一轮（会移到「已删除备份」）':
        'Delete this round (it is moved to “deleted backups”)',
    '（这一节是空的）': '(this section is empty)',
    '没找到随程序附带的说明书（{f}）。':
        'The bundled manual was not found ({f}).',
    '可以在程序目录里直接打开《使用说明.md》查看。':
        'You can open "User_Manual.md" in the program folder directly.',
    '状态：{s}': 'Status: {s}',
    '已打开天机（程序设置）': 'Opened program settings',
    '命令「{c}」还没接上 —— 说明书第 5 节里列的那些命令目前只有 '
    'help / status / settings 三条可用':
        'Command "{c}" is not wired up yet — only help / status / settings '
        'from section 5 of the manual work today.',
    '未实现的命令：{c}': 'Unsupported command: {c}',
    # 场景名称（书斋 · 类型与风格）：显示人话、存盘存真值
    # [EN] Scene name (书斋 · type and style): display human-readable text, store the real value on disk
    '自动（按设定里的地点推断）': 'Auto (infer from places in the setting)',
    # 下拉框里"当前值不在选项表里"时的兜底显示
    # [EN] Fallback display when the 'current value is not in the options list' in a dropdown
    '{v}（AI 判定）': '{v} (AI decided)',
    '{v}（自定义）': '{v} (custom)',
    # ── 风格参数说明（书斋 · 风格控制 · 标题旁的「?」，v1.29）──
    # [EN] ── Style parameter notes (Study · Style control · '?' next to title, v1.29) ──
    #
    # ⚠ **下面这一大段都是"动态取值"**：`t(name)` / `t(what)` 里的字符串来自
    # `gui/app_flet.py` 的 `STYLE_HELP_ITEMS` / `STYLE_HELP_GENRES` 两张表，
    # `i18n_check` 扫源码扫不到字面量，**必须在这里手工登记**。
    # 新加的守卫：`tools/verify_style_help.py` 会逐条断言
    # 「en 下 t(s) != s」——漏登记会当场报红，不再靠人眼。
    # （'风格参数' 这个键上面已经有了，别重复登记）
    # [EN] ⚠ **The whole block below is 'dynamic values'**: the strings in `t(name)` / `t(what)` come from
    # [EN] the `STYLE_HELP_ITEMS` / `STYLE_HELP_GENRES` tables in `gui/app_flet.py`;
    # [EN] `i18n_check` cannot find literals when scanning source, so they **must be registered manually
    # [EN] here**.
    # [EN] Newly added guard: `tools/verify_style_help.py` will assert each entry
    # [EN] "en: t(s) != s" -- missing registration turns red immediately, no longer relying on human eyes.
    # [EN] (The 'style parameters' key already exists above, do not register it again)
    '风格参数 · 怎么调': 'Style parameters · how to tune them',
    '这些参数怎么调？': 'How to tune these?',
    '打开风格参数说明': 'Open style-parameter help',
    '逐项说明': 'Parameter by parameter',
    '常见类型的建议档': 'Suggested presets by genre',
    '八个滑杆都不分好坏，只看「你想让读者有什么感觉」。'
    '每项都是 0~1，下面第二行是低↔高的手感差别，第三行是各类小说常见的落点。':
        'None of the eight sliders is "good" or "bad" — it is only about what you '
        'want the reader to feel. Each is 0~1; the second line below is the low↔high '
        'difference, the third is where common genres usually land.',
    '顺序就是上面八项：虐心｜幽默｜爽点｜感情线｜悬念｜世界观｜人物智商｜节奏感。':
        'The order is the same eight: angst | humor | payoff | romance | suspense | '
        'worldbuilding | character IQ | pacing.',
    '※ 这些是起点、不是规矩：跑起来之后按实际手感再调。'
    '改值的地方是「📖 起　笔 · 风格控制」（会把值写进配置文件，本轮立即生效）。':
        '※ These are starting points, not rules — adjust by feel once it runs. You '
        'change the values in "📖 Pen to paper · style control" (they are written to the '
        'config file and take effect for that round immediately).',
    # 八项：管什么
    # [EN] Eight items: what it controls
    '角色受苦、失去、意难平的密度。':
        'How much suffering, loss and unfinished business the characters go through.',
    '叙述与对白里插科打诨的比重。':
        'How much banter and levity sits in the narration and dialogue.',
    '打脸、得手、碾压这类「读者解气」的节拍出现得多不多。':
        'How often the "reader gets satisfaction" beats land (comeuppance, wins, sweeps).',
    '情感关系在主线里占的分量（不是「有没有」，是「占多少」）。':
        'The weight of relationships in the main line — not whether, but how much.',
    '未解之谜与钩子的数量、间距。':
        'How many open questions and hooks there are, and how far apart they sit.',
    '设定信息释放的快慢（什么时候把规矩讲给读者）。':
        'How fast the worldbuilding is released — when the rules are told to the reader.',
    '角色判断与行事的水平 —— 读者说的「智商在线」。':
        'How smart the characters act — what readers call "IQ online".',
    '事件推进的速度与起伏形状（慢热 / 适中 / 快节奏 / 过山车）。':
        'How fast events move and what shape the curve has (slow-burn / medium / fast / rollercoaster).',
    # 八项：低↔高
    # [EN] Eight items: low<->high
    '低：顺遂轻松，挫折只是过场；高：反复重压，代价沉重、真会有人走。':
        'Low: things go smoothly, setbacks pass by; High: repeated pressure, real costs, people do leave.',
    '低：正剧口吻；高：吐槽与冷幽默密，接近轻喜剧。':
        'Low: straight-faced drama; High: dense snark and dry humor, close to a light comedy.',
    '低：写实平缓，半天不给甜头；高：三五章一个爽点，节奏往上顶。':
        'Low: plain and realistic, no payoff for a long while; High: a payoff every few chapters.',
    '低：事业与谜题为主，感情只是侧写；高：感情本身就是主线。':
        'Low: career and puzzles lead, romance is a side note; High: romance IS the main line.',
    '低：交代清楚、少留扣；高：多线悬念并行，章末必留钩。':
        'Low: everything explained, few loose ends; High: many threads at once, a hook every chapter end.',
    '低：边写边漏、用到了才说；高：前期成体系铺开，先立规矩再动人。':
        'Low: revealed piecemeal on demand; High: laid out systematically up front.',
    '低：冲动犯蠢、靠巧合推进；高：各有算计、棋逢对手。':
        'Low: impulsive and dumb, plot moves by coincidence; High: everyone schemes, equals trade blows.',
    '慢热：铺垫长、后段发力；快节奏：两三章一件大事；过山车：大起大落连着来。':
        'Slow-burn: long setup, late payoff; Fast: a big event every few chapters; Rollercoaster: highs and lows back to back.',
    # 八项：常见落点
    # [EN] Eight items: common landing points
    '常见：言情 0.6~0.8 · 悬疑 0.4~0.5 · 玄幻 0.2~0.4 · 治愈系 0.1':
        'Typical: romance 0.6~0.8 · mystery 0.4~0.5 · xianxia 0.2~0.4 · healing 0.1',
    '常见：都市 0.5~0.7 · 玄幻 0.3~0.5 · 严肃正剧 0.1~0.2':
        'Typical: urban 0.5~0.7 · xianxia 0.3~0.5 · serious drama 0.1~0.2',
    '常见：玄幻修仙 0.7~0.9 · 都市 0.6~0.8 · 现实向 0.2~0.3':
        'Typical: xianxia 0.7~0.9 · urban 0.6~0.8 · realistic 0.2~0.3',
    '常见：言情 0.8~1.0 · 都市 0.3~0.5 · 悬疑 0.1~0.2':
        'Typical: romance 0.8~1.0 · urban 0.3~0.5 · mystery 0.1~0.2',
    '常见：悬疑 · 单元 0.8~0.9 · 科幻 0.6~0.8 · 言情 0.3':
        'Typical: mystery/episodic 0.8~0.9 · sci-fi 0.6~0.8 · romance 0.3',
    '常见：玄幻 · 科幻 0.7~0.9 · 历史架空 0.7~0.8 · 都市 0.2~0.4':
        'Typical: xianxia/sci-fi 0.7~0.9 · alt-history 0.7~0.8 · urban 0.2~0.4',
    '常见：悬疑 0.7~0.8 · 权谋 0.8~0.9 · 纯爽文 0.4~0.5':
        'Typical: mystery 0.7~0.8 · scheming 0.8~0.9 · pure power-fantasy 0.4~0.5',
    '常见：玄幻 快节奏 · 悬疑 适中 · 言情 慢热 · 冒险 过山车':
        'Typical: xianxia fast · mystery medium · romance slow-burn · adventure rollercoaster',
    # 类型名（新增的两个）
    # [EN] Type names (the two newly added)
    '悬疑 · 单元': 'Mystery · episodic',
    '群像 / 现实向': 'Ensemble / realistic',
    # 各类型的建议档：一句话 + 一整串数值
    # [EN] Suggested range per type: one sentence + a whole string of numbers
    '爽点要密、世界观铺得开、感情线轻':
        'Dense payoffs, a wide-open world, light romance',
    '悬念最密、人物智商在线，爽点反而要压':
        'Maximum suspense, sharp characters, payoffs held down',
    '爽点与幽默并重，节奏往前推':
        'Payoffs and humor together, pacing pushing forward',
    '世界观与人物智商偏高，别急着给爽点':
        'Heavier worldbuilding and sharper characters, payoffs slow',
    '感情线是主轴，甜虐自己定档':
        'Romance is the spine; pick your own sweet/bitter setting',
    '世界观最重、悬念中高，人物服务于设定':
        'Worldbuilding first, medium-high suspense, characters serve the setting',
    '整体压中低，靠人物与细节撑，不要爽点轰炸':
        'Keep it all low-to-medium; carry it with people and detail, no payoff barrage',
    '0.3｜0.4｜0.8｜0.2｜0.5｜0.7｜0.5｜快节奏':
        '0.3 | 0.4 | 0.8 | 0.2 | 0.5 | 0.7 | 0.5 | fast',
    '0.4｜0.3｜0.4｜0.2｜0.9｜0.5｜0.7｜适中':
        '0.4 | 0.3 | 0.4 | 0.2 | 0.9 | 0.5 | 0.7 | medium',
    '0.3｜0.6｜0.7｜0.4｜0.5｜0.3｜0.5｜快节奏':
        '0.3 | 0.6 | 0.7 | 0.4 | 0.5 | 0.3 | 0.5 | fast',
    '0.4｜0.3｜0.5｜0.3｜0.5｜0.8｜0.6｜适中':
        '0.4 | 0.3 | 0.5 | 0.3 | 0.5 | 0.8 | 0.6 | medium',
    '0.6｜0.4｜0.4｜0.9｜0.4｜0.2｜0.5｜慢热':
        '0.6 | 0.4 | 0.4 | 0.9 | 0.4 | 0.2 | 0.5 | slow-burn',
    '0.4｜0.3｜0.4｜0.3｜0.7｜0.9｜0.6｜适中':
        '0.4 | 0.3 | 0.4 | 0.3 | 0.7 | 0.9 | 0.6 | medium',
    '0.5｜0.3｜0.3｜0.4｜0.4｜0.3｜0.6｜慢热':
        '0.5 | 0.3 | 0.3 | 0.4 | 0.4 | 0.3 | 0.6 | slow-burn',

    # ══════════════════════════════════════════════════════════════
    #  「AI 补全并回写引用文件夹」（`ingest/repair.py`，2026-10-06）
    # [EN] "AI completes and writes back the reference folder" (`ingest/repair.py`, 2026-10-06)
    # ══════════════════════════════════════════════════════════════
    # ⚠ 这一块里有**两条走 `t(plan_tpl)` 的动态取值**（`repair._gap` 把模板当参数传进去）：
    #   · 'AI 读正文找出埋设点与预计回收点，追加到 {f} 末尾'
    #   · 'AI 从正文推断每位人物的秘密与口癖，写入 {f}'
    #   · 'AI 读正文概括一条「起承转合」线，追加到 {f} 末尾'
    #   · 'AI 读正文铺开一段世界观（120 字内），追加到 {f} 末尾'
    #   `tools/i18n_check.py` 只扫 `t('字面量')`，**扫不到它们** —— 必须手工登记。
    # [EN] ⚠ This block has **two dynamic values using `t(plan_tpl)`** (`repair._gap` passes the template
    # [EN] as a parameter):
    # [EN] · 'AI reads the body text to find planted and expected payoff points, appends to end of {f}'
    # [EN] · 'AI infers each character's secret and verbal tic from the body text, writes to {f}'
    # [EN] · 'AI reads the body text and summarizes a "setup-development-turn-conclusion" line, appends to
    # [EN] end of {f}'
    # [EN] · 'AI reads the body text and expands a worldview passage (within 120 chars), appends to end of
    # [EN] {f}'
    # [EN] `tools/i18n_check.py` only scans `t('literal')`, **cannot find these** -- must register
    # [EN] manually.
    '缺 伏笔清单': 'Missing: foreshadowing list',
    '人物没有秘密 / 口癖': 'Characters have no secrets / catchphrases',
    '缺 大纲 / 剧情参考线': 'Missing: outline / story arc',
    '世界观太短（{n} 字）': 'Worldview too short ({n} chars)',
    '人物空缺字段（{p} 位 · 共 {n} 处）':
        'Empty character fields ({p} characters · {n} fields)',
    'AI 读正文找出埋设点与预计回收点，追加到 {f} 末尾':
        'The AI finds the setup and payoff points in the original text and appends them to {f}',
    'AI 从正文推断每位人物的秘密与口癖，写入 {f}':
        'The AI infers each character\u2019s secret and catchphrase from the text and writes them into {f}',
    'AI 读正文概括一条「起承转合」线，追加到 {f} 末尾':
        'The AI summarises a setup\u2013development\u2013turn\u2013resolution arc from the text and appends it to {f}',
    'AI 读正文铺开一段世界观（120 字内），追加到 {f} 末尾':
        'The AI expands the worldview in under 120 characters and appends it to {f}',
    'AI 从正文补齐这些字段，写入 {f}':
        'The AI fills these fields in from the text and writes them into {f}',
    '{name} 不是 UTF-8（{enc}）': '{name} is not UTF-8 ({enc})',
    '转成 UTF-8（正文一字不改，旧文件先备份为 {name}{bak}）':
        'Convert to UTF-8 (content unchanged; old file backed up as {name}{bak})',
    '{n} 个文件看不出属于哪一类': '{n} files cannot be told apart by category',
    'AI 判断它们其实是哪一类，写进 {f}（**不改你的文件名**）':
        'The AI decides which category they really belong to and writes that into {f} (**your file names are not changed**)',
    '人物补充': 'Character additions',
    '本次读取说明': 'How these files were read',
    '世界观': 'Worldview',
    '剧情参考线': 'Story arc',
    '> 下面这一段是开卷导入时由 AI 读正文补写的；**原有的内容一字未动**，可以放心对照。':
        '> The section below was written by the AI from the original text during import; **your own text is untouched**, so you can compare safely.',
    '- 下面这几个文件的名字里没有类别词，AI 判断它们其实是：':
        '- These files have no category word in their names; the AI judged them to be:',
    '· 追加补全 → {p}': '· Appended completion → {p}',
    '· 新建文档 → {p}': '· Created document → {p}',
    '· 转为 UTF-8 → {p}': '· Converted to UTF-8 → {p}',
    '· 跳过 {p}：{why}': '· Skipped {p}: {why}',
    '· {name}：补上 {fields}': '· {name}: added {fields}',
    '· 补上 {n} 条伏笔': '· Added {n} foreshadowing entries',
    '· 补上剧情参考线': '· Added the story arc',
    '· 补上世界观': '· Added the worldview',
    '已回写引用文件夹：': 'Written back to the source folder: ',
    '追加 {n} 篇': '{n} appended',
    '新增 {n} 篇': '{n} created',
    '转码 {n} 篇': '{n} re-encoded',
    '归类说明 {n} 条': '{n} category notes',
    '没有需要改动的文件': 'No files needed changing',
    '（原件备份为 {n} 份 .bak）': ' ({n} originals backed up as .bak)',
    '；{n} 项跳过': '; {n} skipped',
    '没能回写引用文件夹：{why}': 'Could not write back to the source folder: {why}',
    '只允许在开卷阶段回写引用文件夹':
        'The source folder can only be written back during import',
    '项目已经开始，不再改动引用文件夹':
        'The project has already started; the source folder is no longer modified',
    '引用文件夹不存在': 'Source folder does not exist',
    '认不出它是什么编码': 'Could not detect its encoding',
    '转码失败：{e}': 'Re-encoding failed: {e}',
    '不是 UTF-8，先别动它（避免写坏）':
        'Not UTF-8 — leaving it alone rather than corrupting it',
    '读不了：{e}': 'Could not read: {e}',
    '写不进去：{e}': 'Could not write: {e}',
    '拒绝：目标不在引用文件夹里': 'Refused: target is not inside the source folder',
    '拒绝：只改 .md / .txt 文档': 'Refused: only .md / .txt documents are changed',
    '拒绝：不动隐藏文件': 'Refused: hidden files are left alone',
    '没有可自动修复的问题': 'No auto-fixable issues',
    '! AI 没能给出补全内容（详见对话日志）—— 引用文件夹不会改动':
        '! The AI could not produce any completion (see the dialogue log) — the source folder will not be touched',
    'AI 发现 {n} 处它可以自己修好的问题':
        'The AI found {n} issues it can fix on its own',
    '　→ 落点：{p} —— {plan}': '　→ Goes to: {p} — {plan}',
    '· 每个被改动的文件都会先留一份同名 .bak 备份；你原有的文字只增不改，不会被删掉或改写。':
        '· Every file that gets modified is first backed up as a same-named .bak; your own text is only appended to, never deleted or rewritten.',
    '我同意让 AI 按上面的做法修复，并写回引用文件夹':
        'I agree to let the AI fix them as listed and write back to the source folder',
    '同意修复并回写': 'Agree, fix and write back',
    '跳过，不改引用文件夹': 'Skip, leave the source folder alone',
    '等你确认 —— 要不要把这些补全写回引用文件夹':
        'Waiting for you — should these completions be written back to the source folder?',
    '已暂停：等你确认之后才会改动引用文件夹':
        'Paused: the source folder is only changed after you confirm',
    'AI 正在读正文补全缺口…': 'The AI is reading the text to fill the gaps…',
    '正在补全 —— 稍后写回引用文件夹':
        'Completing — will write back to the source folder shortly',
    'AI 补全失败': 'AI completion failed',
    '检查可修复问题时出错': 'Failed to check for fixable issues',
    '「补全缺口并回写引用文件夹」：AI 会把缺的伏笔、人物空字段、'
    '编码不对的文档补好，**写回你导入的那个文件夹**。'
    '动手前会先列一份清单让你过目；每个被改的文件都留 .bak 备份，'
    '你的原文只增不改。**项目一旦开始推演，就再也不会碰这个文件夹**。':
        '"Fill gaps and write back to the source folder": the AI completes the missing '
        'foreshadowing, empty character fields and wrongly-encoded documents, then '
        '**writes them back into the folder you imported**. You see a checklist first; '
        'every modified file keeps a .bak backup, and your own text is only appended to. '
        '**Once the project starts running, this folder is never touched again.**',

    # ══════════════════════════════════════════════════════════════
    #  运行界面：底部状态条 + 分隔符标签（2026-10-06）
    # [EN] Run UI: bottom status bar + divider labels (2026-10-06)
    # ══════════════════════════════════════════════════════════════
    # ⚠ 这一块里 `sim` 层只给**数据**（第几天/几幕/什么时辰），句子在 GUI 里拼 ——
    #   所以这些 key 必须在这儿登记（`i18n_check` 扫 `gui/app_flet.py` 能扫到大部分；
    #   `t(str(meta.get('name')))` 那种动态取值扫不到，见 `'导出'` 的手工登记）。
    # [EN] ⚠ In this block the `sim` layer only provides **data** (day number / act / time of day),
    # [EN] sentences are assembled in the GUI --
    # [EN] so these keys must be registered here (`i18n_check` can scan most of `gui/app_flet.py`;
    # [EN] dynamic values like `t(str(meta.get('name')))` cannot be found, see the manual registration of
    # [EN] `'Export'`).
    '运行中': 'Running',
    '运行中 —— 等下一次行动': 'Running — waiting for the next action',
    '正在生成 —— 人物在行动': 'Generating — characters are acting',
    '正在安排今天要做的事': 'Planning what to do today',
    '导演在看这一拍': 'The director is watching this beat',
    '正在核对故事进度': 'Checking story progress',
    '已暂停 —— 等你点「继续」': 'Paused — press "Resume" to continue',
    # ★ 2026-10-25：因为某家模型服务没钱而暂停。**服务名照原样显示**（它是专名，不翻）。
    # [EN] ★ 2026-10-25: paused because a model provider ran out of money. The provider name is a
    # [EN] proper noun and stays as-is.
    '已暂停 —— {who} 余额不足或欠费，充值后点「继续」':
        'Paused — {who} is out of credit; top up, then press "Resume"',
    '{s} · 已 {n} 秒': '{s} · {n}s ago',
    '第 {d} 天': 'Day {d}',
    '第 {d} 天终': 'End of day {d}',
    '{n} 幕': '{n} scenes',
    '{n} 件大事': '{n} major events',
    '换场': 'Scene change',
    '全篇终': 'The End',
    '走到第 {d} 天': 'reached day {d}',
    # ── 日志改名失败（2026-10-07）──
    # [EN] ── Log rename failure (2026-10-07) ──
    '日志改名失败（日志继续写在原名里）':
        'The log file could not be renamed (it keeps its original name)',
    '回想': 'Memory',
    # ── 剧组（`crew/`，2026-10-07）──
    #   面板标题、职位名、职责、四个状态词。**职位名与职责都要能在界面上翻**：
    #   剧组面板是"这班人在干什么"的窗口，留着中文等于英文用户看不懂它。
    # [EN] ── Crew (`crew/`, 2026-10-07) ──
    # [EN] Panel title, position names, duties, four status words. **Both position names and duties must be
    # [EN] translatable in the UI**:
    # [EN] The crew panel is the window into "what this group is doing"; leaving Chinese means English
    # [EN] users cannot understand it.
    '剧组': 'Crew',
    # ── 认知模式（`crew/cognition.py`，2026-10-07 第七轮）──
    #   这一组旋钮在 `.env` / 配置说明里以分组名出现（与「剧组」同一口径）。
    # [EN] ── Cognition mode (`crew/cognition.py`, 2026-10-07 round 7) ──
    # [EN] This group of knobs appears as a group name in `.env` / config docs (same convention as "Crew").
    '认知模式': 'Cognition',
    '小说作家': 'Novelist',
    '剧作者': 'Screenwriter',
    # 注：'导演' 已在上面登记过（与「导演引擎」同名同译），此处不再重复
    # [EN] Note: 'Director' is already registered above (same name and translation as 'Director Engine'),
    # [EN] not repeated here
    '演员': 'Actors',
    '群众演员': 'Extras',
    '场记': 'Script Supervisor',
    '道具': 'Props',
    '美术': 'Art Director',
    '宣发': 'Publicity',
    '资料员': 'Researcher',
    '写当天这一章的原著样章':
        'Writes today\u2019s chapter as original prose',
    '把样章改写成能拍的剧本（分场·分拍·谁做什么）':
        'Turns the prose into a shootable script (scenes, beats, who does what)',
    '定框架、派活、挑事、验算、收尾':
        'Sets the frame, assigns work, injects events, verifies, wraps up',
    '在框架之内自由发挥': 'Improvises within the frame',
    '门外的人与事（外部输入）': 'The people and errands outside (external input)',
    '连戏检查：时间·物件·称呼·状态对不对得上':
        'Continuity check: time, props, names, on-stage state',
    '这一场该有什么物件、哪件要反复出现':
        'Decides the props for this scene, and which one recurs',
    '定这一部的画风与配色，管住出图一致性':
        'Sets the look and palette, keeps generated images consistent',
    '写一句话卖点、看点、预告':
        'Writes the one-line pitch, the hooks, the teaser',
    '考据：这一处的名物、制度、称谓站不站得住':
        'Fact-checks names, institutions and forms of address',
    # ── 剧组扩充 · 今日简介 · 复盘 · 导演盯戏（2026-10-07 第二轮）──
    #   ⚠ 四位新职位的**名字与职责**也是动态取值（读名册），这里必须手工登记；
    #     `reviewer` 等的名字在下面，职责那句在 roster 里，两处都要有。
    # [EN] ── Crew expansion · Today's brief · Review · Director watching (2026-10-07 round 2) ──
    # [EN] ⚠ The **names and duties** of the four new positions are also dynamic values (read from roster),
    # [EN] must be registered manually here;
    # [EN] names like `reviewer` are below, the duty sentence is in the roster, both places are needed.
    '复盘': 'Review',
    '每天收工复盘：剧情总结 + 存在的问题 + 后续修改意见（必要时建议改当天的戏）':
        'End-of-day review: what happened, what went wrong, what to fix',
    '造型': 'Styling',
    '人物身上的东西：衣着·随身物·仪态 —— 给演员穿戴，并进出图提示词':
        'What each person wears, carries and how they stand',
    '声音': 'Sound',
    '这一场的声音层：环境音·静默·声音的转折 —— 喂给场景的环境句':
        'The sound of a scene: ambience, silence, the turn of a sound',
    '语言审校': 'Copy Editor',
    '读当天样章，点名哪几句 AI 味重、该怎么改（去 AI 库的每日深查）':
        'Reads the day\'s prose and names the lines that sound machine-written',
    # ── 排练 + 阶段小消息 + 当天整理（2026-10-07 第三轮）──
    #   ⚠ 阶段名是**动态取值**（`story_render.stage_line` 从一张表里取），
    #     虽然那张表里是字面量 `t('…')`（`i18n_check` 扫得到），
    #     但这几条例外 —— 它们是**新增文案**，要手工登记英文。
    # [EN] ── Rehearsal + stage messages + daily organizing (2026-10-07 round 3) ──
    # [EN] ⚠ Stage names are **dynamic values** (`story_render.stage_line` takes from a table),
    # [EN] although that table contains literal `t('...')` (`i18n_check` can find them),
    # [EN] these few are exceptions -- they are **newly added copy**, English must be registered manually.
    '排练': 'Rehearsal',
    '剧本定稿后把这一天**空走一遍**：哪一拍谁做不到、人不在场、'
    '写死了台词 —— 有问题就退回剧作者改':
        'Walks the whole day once before shooting: who cannot do what, who is '
        'not there, which lines are too rigid \u2014 problems go back to the '
        'screenwriter',
    '开拍前准备': 'Pre-production',
    '作者写小说': 'Author writes the day\u2019s chapter',
    '剧作者写剧本': 'Screenwriter turns it into a script',
    '剧组排练': 'Crew rehearses',
    '带意见重新修改': 'Rewriting with notes',
    '开演': 'Shooting begins',
    '临时暂停': 'Paused',
    '继续': 'Resumed',
    '剧组重新修改设定细节': 'Crew revises setting details',
    '美术画当天地图': 'Art director draws today\u2019s map',
    '一天结束后讨论': 'End-of-day discussion',
    '总结会': 'Wrap-up meeting',
    '整理当天这一章': 'Turning the day into a chapter',
    '（失败）': ' (failed)',
    '{s}s': '{s}s',
    '今日剧情简介': 'Today\'s brief',
    # ── 开演前的第三块 + 停止那两条（2026-10-07 第八轮）──
    # [EN] ── Third block before showtime + the two stop entries (2026-10-07 round 8) ──
    '今日任务': 'Today\'s assignments',
    '收尾（落盘 + 总结）': 'Wrapping up (flush + summary)',
    '还没开始': 'not started yet',
    '这一轮已经停了（{r}）—— 要在跑的时候点它才算数':
        'This round has already stopped ({r}) — the button only does something '
        'while it is still running.',
    # ★ 2026-10-10 用户点名改的英文名：**Book Deconstruction**（原来叫
    #   `Book Lab`）。改名的理由值得记一笔 —— 「拆书」是行业里既有的说法
    #   （见 `booklab/__init__` 模块头），英文上就该意译成它本来的意思：
    #   **deconstruction**（拆解）而不是 lab（实验室）。
    # [EN] ★ 2026-10-10 name explicitly changed by user: **Book Deconstruction** (originally
    # [EN] `Book Lab`). The reason for the rename is worth noting -- "book deconstruction" is an existing
    # [EN] term in the industry
    # [EN] (see `booklab/__init__` module header), in English it should be semantically translated to its
    # [EN] original meaning:
    # [EN] **deconstruction** rather than lab.
    '拆\u3000书': 'Book Deconstruction',
    '读一本好书，学写法': 'Learn craft from a book',
    '拆书': 'Book deconstruction',
    '拆书不是读书笔记 —— 它读的是**写法**：节奏怎么控、人物怎么立、情节怎么推。拆出来的东西会进技能库，以后写同类故事时被剧组用上。': 'This is not note-taking — it reads for **craft**: how pace is held, how a character is made to land, how plot is pushed. What comes out goes into the skill library and is used by the crew when a similar story comes in.',
    # ⚠ **下面八条（四问的 ask + hint）是"动态 key"** —— 界面上是
    #   `t(q['ask'])` / `t(q['hint'])`（见 `booklab/theory.QUESTIONS`），
    #   `tools/i18n_check.py` 只扫 `t('字面量')`，**扫不到它们**。
    #   所以这八条漏过一次译（英文界面下这四条问题一直显示中文，
    #   而检查脚本一声不吭）。改 `theory.QUESTIONS` 里那几个字，
    #   **必须回来同步这八条**。
    # [EN] ⚠ **The eight entries below (ask + hint for four questions) are 'dynamic keys'** -- in the UI
    # [EN] they are
    # [EN] `t(q['ask'])` / `t(q['hint'])` (see `booklab/theory.QUESTIONS`),
    # [EN] `tools/i18n_check.py` only scans `t('literal')`, **cannot find these**.
    # [EN] So these eight were missed in translation once (the four questions kept showing Chinese in the
    # [EN] English UI,
    # [EN] and the check script said nothing). Changing those characters in `theory.QUESTIONS`,
    # [EN] **must come back to sync these eight**.
    '这本书叫什么': 'What is this book called?',
    '随便写 —— 它只用来给拆出来的技能包命名':
        'Anything you like — it is only used to name the skill pack.',
    '它是什么类型': 'What genre is it?',
    '比如"年代文·群像""悬疑·单元剧"。写得越准，以后越容易在同类书上被用起来':
        'e.g. "period drama · ensemble", "mystery · procedural". '
        'The more accurate it is, the likelier a similar book picks it up later.',
    '你觉得它哪些地方好': 'What do you think it does well?',
    '哪一段、哪个人物、哪种写法让你觉得"这个我写不出来"。**这一条最要紧** —— 拆解会重点看这些地方':
        'Which passage, character or technique made you feel '
        '"I could not have written that". **This is the one that matters most** '
        '— Book Deconstruction looks there first.',
    '想重点拆什么': 'What should it focus on?',
    '比如"对话怎么写得像真人""怎么让人物立住""节奏怎么控"。不填就按标准维度全拆一遍':
        'e.g. "how dialogue sounds like real people", "how a character is made '
        'to land", "how pace is held". Leave it blank to go through every '
        'standard dimension.',
    '正在拆……这一步会有几十次模型调用，可以关掉窗口去干别的（拆完会写进技能库）': 'Digging in… this takes dozens of model calls. You can close the window; it still writes to the skill library when done.',
    '每读完一批就报一行 —— 下面这些能看出它读到哪儿了': 'One line per batch — this shows how far it has read.',
    '拆完了。': 'Done.',
    '归纳出 {n} 条可复用的写法（粗扫 {c}，精读 {d} 条笔记，用时 {s:.0f} 秒）': 'Distilled {n} reusable techniques (scanned {c}, {d} close-reading notes, {s:.0f}s)',
    '这一轮**没归纳出可用的写法** —— 报告仍然写出来了，可以打开看看问题出在哪一步。': 'No reusable technique came out of this run — the report was still written; open it to see which step failed.',
    '已写入技能库：{p}': 'Written to the skill library: {p}',
    '以后写**同类型**的书时，各职位会自动拿到这一份（三人小组拿到的是完整版）。': 'When you write a book of the **same genre**, every position picks this up automatically (the trio gets the full version).',
    '打开文件夹': 'Open folder',
    '看拆书记录': 'Read the report',
    '再拆一本': 'Dig another',
    '这一步的说明（照实记）：': 'Notes on this run (recorded as-is):',
    '还没选书': 'No book chosen yet',
    '选了：{p}': 'Chosen: {p}',
    '选一个文件': 'Pick a file',
    '选一个文件夹': 'Pick a folder',
    # ⚠ 这里原来有一条 `'用 samples/ 里的一篇试拆'`（注意是「篇」）——
    #   它在**任何代码里都没有引用**：曾经那个按钮先写成「一篇」、后来改成
    #   「一本」、现在改名成「用 sample 测试」，这条一直没删。
    #   留着它的坏处不是体积，而是**下一个人会以为它是当前文案**（改名时漏改）。
    #   `tools/i18n_check.py` 只查"缺译/重复"，查不出"没人用" —— 这条靠人看。
    # [EN] ⚠ There used to be an entry `'try deconstructing one from samples/'` here (note it is "one
    # [EN] article") --
    # [EN] it is **referenced nowhere in any code**: the button was first written as "one article", later
    # [EN] changed to
    # [EN] "one book", now renamed to "test with sample", this entry was never deleted.
    # [EN] The harm of keeping it is not size, but that **the next person will think it is the current
    # [EN] copy** (missed on rename).
    # [EN] `tools/i18n_check.py` only checks "missing/duplicate translation", cannot find "unused" -- this
    # [EN] relies on human review.
    '支持 .txt / .md / .docx / .html；一本被拆成多个文件的，选文件夹。': 'Supports .txt / .md / .docx / .html; if one book is split across files, pick the folder.',
    '长篇小说不用全传 —— **传一部分也行**：程序会自己分层取样（开头几章必读），不会逐字读完。': 'You do not need the whole novel — **a portion is fine**: it samples by position (the opening chapters always included) rather than reading every word.',
    '开 始 拆': 'Start',
    '先选一本书': 'Pick a book first',
    '开始：{p}': 'Starting: {p}',
    '① 分章': '1. Split chapters',
    '① 分章完了': '1. Chapters split',
    '② 粗扫': '2. Scan',
    '③ 精读': '3. Close reading',
    '④ 归纳': '4. Distil',
    '④ 归纳完了': '4. Distilled',
    '{n} 批': '{n} batches',
    '{n} 章': '{n} chapters',
    '拆书失败': 'Book lab failed',
    '拆书失败：{ex}': 'Book lab failed: {ex}',
    '写入技能库失败（结果仍可查看）': 'Failed to write to the skill library (results are still viewable)',
    '写入技能库失败：{ex}': 'Failed to write to the skill library: {ex}',
    '打开失败': 'Open failed',
    '打开失败：{ex}': 'Open failed: {ex}',
    '打开文件选择器失败': 'Could not open the file picker',
    '选示例失败: {ex}': 'Could not pick a sample: {ex}',
    'samples/ 里没有可拆的文本': 'No text to dig in samples/',
    '这本书里没有读到正文（文件是空的 / 全是二进制？）': 'No prose found in this book (empty file, or all binary?)',
    '第 {i} 批（{a}~{b}）没读到 —— 这本书是浮着拆的': 'Batch {i} ({a}~{b}) was not read — this book was dug at a distance',
    '粗扫一章都没读到 —— 检查模型配置，或这本书太大': 'Not a single chapter was scanned — check the model settings, or the book is too large',
    '精读这几章没拿到笔记 —— 归纳那一步只有概览可依': 'No notes came back from the close reading — the distillation only has the overview to work from',
    '归纳这一步没拿到结果 —— 没有产出可用的写法': 'The distillation step returned nothing — no reusable technique was produced',
    '拆书库里还没有东西。': 'The book-deconstruction library is still empty.',
    '拆书功能被关掉了（天机里的 `BOOKLAB_ENABLED`）':
        'Book Deconstruction is switched off (`BOOKLAB_ENABLED` in the '
        'settings).',
    '拆书库里还没有东西。\n\n想让 Agent 有"同类书的写法"可用：在开始菜单点「拆\u3000书」，把一本你觉得写得好的书拆一遍。': 'The book-deconstruction library is still empty.\n\nTo give the agents '
        '"how similar books do it": open Book Deconstruction from the start '
        'menu and dig through one you admire.',
    '导演回档：撤掉了最近 {n} 条戏，重演这一拍':
        'Director rewind: removed the last {n} lines and reshot this beat',
    '（复盘 · 判定这一天立不住）回档重演：撤掉了最近 {n} 条，后半段重新来过。':
        '(Review · the day does not hold up) Rewinding: removed the last {n} '
        'lines; the second half starts over.',
    # ── 编剧室 + 设定分层（2026-10-07）──
    #   ⚠ 「编剧室」这一条与它的职责是**动态取值**（界面读名册里的 name/duty），
    #     `i18n_check` 扫不到字面量 —— 必须手工登记，别删。
    # [EN] ── Writers room + setting layers (2026-10-07) ──
    # [EN] ⚠ The 'writers room' entry and its duty are **dynamic values** (UI reads name/duty from roster),
    # [EN] `i18n_check` cannot find literals -- must register manually, do not delete.
    '编剧室': 'Story Room',    '导演·小说作家·剧作者三方会审：为该推进的故事补局部设定'
    '（只能动场景层/细节层，不碰总体设定）':
        'Director, novelist and screenwriter meet to add local settings '
        '(scene/detail layers only \u2014 never the core canon)',
    '细节 {n} 条': '{n} detail notes',
    # 顺手补的一条历史缺译（`display/story_render.py` 的剧本体台词头：
    # "主角：（压低声，向阿枝）…" —— 这是 `t('向{who}', who=…)` 的动态取值，
    # `i18n_check` 的字面量扫描正好抓到了它）
    # [EN] Also filled a historical missing translation (`display/story_render.py` script body dialogue
    # [EN] header:
    # [EN] "Shen Yan: (lowering voice, to Azhi) ..." -- this is a dynamic value of `t('to {who}',
    # [EN] who=...)`,
    # [EN] `i18n_check`'s literal scan happened to catch it)
    '向{who}': 'to {who}',
    '还没轮到': 'Not called yet',
    # 有人正在干活时那行第二句要写"它在做什么"（用户 2026-10-08：
    # 「右边人员都在干活了 跟着他们的状态还是 还没轮到 这个有点奇怪」）。
    # [EN] When someone is working, the second sentence of that line should say "what it is doing" (user
    # [EN] 2026-10-08:
    # [EN] "the people on the right are all working, but following their status it still says 'not yet
    # [EN] their turn', this is a bit odd").
    '正在做：{d}': 'Doing: {d}',
    '正在做…': 'Working…',
    '这一轮没启用': 'Not enabled this run',
    '出工中': 'Working',
    '未启用': 'Disabled',
    '点「起\u3000笔」开拍后，这班人各司其职':
        'Press \u201cPen to paper\u201d \u2014 the crew takes their posts',
    '{n} / {m} 位已交活': '{n} of {m} have delivered',
    # ── 补齐历史缺译（`i18n_check` 一直列着这 5 条）──
    # [EN] ── Fill in historical missing translations (`i18n_check` has always listed these 5) ──
    '{n} 处地点 · {base}': '{n} locations · {base}',
    '「{here}」附近 {n} 处': '{n} places near "{here}"',
    '今天这场戏在 {n} 处': 'Today\'s scene spans {n} places',
    '简化排布（没调用模型）': 'Simplified layout (no model call)',
    '这一轮还在跑 —— 先点「停止」，再删它的存档。':
        'This round is still running — press Stop first, then delete its save.',
    # 前情提要（2026-10-07 新增的词条类型 `display/script.RECAP`）：
    # 屏幕上是中栏开头那一块，`story_render.sentence()` 拼成 `§ 前情提要：…`。
    # [EN] Previously on (new entry type added 2026-10-07 `display/script.RECAP`):
    # [EN] on screen it is the block at the start of the middle column, `story_render.sentence()` assembles
    # [EN] it as `§ Previously on: ...`.
    '前情提要': 'Recap',
    # ★★ 2026-10-14（用户）：「对话里的时间显示 剧里时间 真实时间 格式改成
    #   剧情时间: xxx  系统时间:xxx」——
    #   每条叙事左上角那行小字的**两个标签**（见 `gui/app_flet.py::_stamp`）。
    #   ⚠ 冒号**不在 key 里**：key 是"词"，`剧情时间: {值}` 那个冒号是**结构**，
    #     由代码拼（见那边的注释）。把冒号写进 key 会让同一个词出现两个版本。
    # [EN] ★★ 2026-10-14 (user): "the time display in the dialogue, story time vs real time, change
    # [EN] the format to 剧情时间: xxx  系统时间:xxx" --
    # [EN] the **two labels** of the small line at the top-left of every narrative entry (see
    # [EN] `gui/app_flet.py::_stamp`).
    # [EN] ⚠ The colon is **not** in the key: the key is a "word", and the colon in
    # [EN] `剧情时间: {value}` is **structure**, assembled by code (see the note there). Putting the
    # [EN] colon in the key would create two versions of the same word.
    '剧情时间': 'Story time',
    '系统时间': 'System time',
    # ⚠ 手工登记（`i18n_check` 扫不到）：
    #   `gui/app_flet.py::_divider_label` 里是 `t(str(m.get('name') or ''))` ——
    #   模块名由 `sim` 层给（`D.module_start('导出')`），是**动态取值**。
    #   以后再加模块名，记得往这里补一条。
    # [EN] ⚠ Manual registration (`i18n_check` cannot find):
    # [EN] In `gui/app_flet.py::_divider_label` it is `t(str(m.get('name') or ''))` --
    # [EN] the module name is given by the `sim` layer (`D.module_start('Export')`), it is a **dynamic
    # [EN] value**.
    # [EN] When adding module names in the future, remember to add an entry here.
    '导出': 'Export',
    '💬 问个问题': '💬 Ask a question',
    '帮 助 · 问个问题': 'Help · Ask a question',
    '问使用问题': 'Ask a usage question',
    # 帮助面板的两个选项卡（2026-10-06 合成一个窗口）
    '帮助信息': 'Manual',            # 这一页就是说明书本身（"Manual" 比 "Help" 准确）
    # [EN] The two tabs of the help panel (merged into one window on 2026-10-06)
    # [EN] This page is the manual itself ("Manual" is more accurate than "Help")
    '问个问题': 'Ask a question',
    '问题': 'Question',
    '例如：怎么设置运行模式': 'e.g. How do I set the run mode?',
    '提问': 'Ask',
    '先写下你的问题': 'Type your question first',
    '正在查《使用说明》…': 'Checking the manual…',
    '没有找到相关章节，模型没有被调用。': 'No relevant chapters found; the model was not called.',
    '依据 {n} 个章节：{s}': 'Based on {n} chapters: {s}',
    '这次没能问到模型：{e}': 'Could not reach the model: {e}',
    '回答只依据随程序附带的《{f}》；说明书里没写的会直说。': 'Answers are based only on the bundled {f}; if the manual does not cover it, it will say so.',
    '可以问使用上的任何问题。下面几个是现成的例子 ——': 'Ask anything about using the app. A few ready-made examples:',
    '《使用说明》里没有找到和这个问题相关的章节。换个说法再问一次，或者打开帮助面板翻目录会更准。': 'The manual has no chapter relevant to this question. Try rephrasing, or browse the Help panel contents — that is more reliable.',
    '这次没能问到模型（{e}）。可以稍后再试，或直接看下面的相关章节。': 'Could not reach the model ({e}). Try again later, or read the related chapters below.',
    '模型这次没有给出内容。换个说法再问一次试试。': 'The model returned nothing this time. Try rephrasing the question.',
    '**参考章节**：': '**Related chapters**: ',
    '怎么设置运行模式': 'How do I set the run mode?',
    '顶级规则怎么写': 'How do I write top-level rules?',
    '对话插图有哪几种': 'What dialogue image modes are there?',

    # ── 天机 ·「创作服务」（外部写小说服务 MuMuAINovel，2026-10-09）──
    # [EN] ── Tianji · "Creation Service" (external novel-writing service MuMuAINovel, 2026-10-09) ──
    '创作服务LLM设定': 'Writing Service LLM Settings',
    '按天装订的**原著样章原文**：逐字原样，不剃痕迹、不润色、'
    '不合并。作者回头改写请以它为准':
        'The **original chapter drafts**, one day each: verbatim - no trace '
        'stripping, no polishing, no merging. Rewrite from this one.',
    '自动拉起创作服务失败': 'Failed to auto-start the writing service',
    '自动拉起创作服务失败：{e}': 'Failed to auto-start the writing service: {e}',
    '创作服务已自动拉起（MuMuAINovel）':
        'Creation service auto-started (MuMuAINovel)',
    # ★ 2026-10-22（用户：「为何外部服务都没启动」）：拉起过程本身也要说话 ——
    #   以前十余秒里界面毫无动静，用户只会认为"没启动"。
    # [EN] ★ 2026-10-22 (user: "why are the external services all not running"): the boot process itself
    # [EN] must speak -- previously the UI showed nothing for ten-plus seconds, which reads as "not started".
    '正在拉起创作服务（{n} 家）—— 首次启动要建环境，可能要几十秒':
        'Starting creation services ({n}) — the first launch builds the environment, '
        'which can take tens of seconds',
    '创作服务已全部就绪（{n} 家）':
        'All {n} creation services are ready',
    '创作服务只起来了 {ok}/{n} 家；没起来的：{who}。'
    '去「天机 → 创作服务」可以点「启动」手动再试一次':
        'Only {ok}/{n} creation services came up; down: {who}. '
        'Go to "Tianji → Creation service" and click "Start" to retry manually',
    '创作服务没拉起来：{why}（{p} · 模块加载失败）':
        'Could not start the creation service: {why} ({p} · module failed to load)',
    # ★ 2026-10-22：天机那一页的状态行改成了**会自己刷新的**，并分清"正在拉起"与"没起"。
    # [EN] ★ 2026-10-22: Tianji's status line now **refreshes itself** and separates
    # [EN] "starting" from "not started".
    '◐ 正在拉起（程序刚启动，要几十秒；点「刷新状态」可以再看一次）':
        '◐ Starting (the app just launched; this takes tens of seconds — '
        'click "Refresh status" to look again)',
    '○ 还没启动（端口 {p}）。点下面「启动服务」现在就起，'
    '或打开「程序启动时自动拉起服务」让它下次自己起':
        '○ Not started (port {p}). Click "Start service" below to start it now, '
        'or turn on "Auto-start services when the program starts" so it starts by itself next time',
    '刷新状态':
        'Refresh status',
    '创作服务已自动拉起（PlotPilot）':
        'Creation service auto-started (PlotPilot)',
    '创作服务已自动拉起（PenShot）':
        'Creation service auto-started (PenShot)',
    # ★ 2026-10-17：三家一起自动拉起后，失败那句要点名「哪家、谁回退」
    #   —— 三家退路不一样（小说作家自写 / 剧作者自写方案 / 导演自排分镜），
    #   不说清楚用户会以为这一天的戏丢了。
    # [EN] ★ 2026-10-17: with all three auto-starting, the failure line must name
    # [EN] "which service and who falls back" -- the three fallbacks differ
    # [EN] (novelist self-writes / screenwriter self-plans / director self-storyboards);
    # [EN] without saying so, users would think the day's scene is lost.
    '创作服务没拉起来：{why}（MuMuAINovel · 小说作家会退回自写，不影响推演）':
        'Creation service did not start: {why} (MuMuAINovel - the novelist '
        'falls back to writing locally; the run is unaffected)',
    '创作服务没拉起来：{why}（PlotPilot · 剧作者会退回自己写方案，不影响推演）':
        'Creation service did not start: {why} (PlotPilot - the screenwriter '
        'falls back to its own in-house plan; the run is unaffected)',
    '创作服务没拉起来：{why}（PenShot · 导演会退回自己排分镜，不影响推演）':
        'Creation service did not start: {why} (PenShot - the director falls '
        'back to its own in-house storyboard; the run is unaffected)',
    # ★ 2026-10-17：外部创作服务页（MuMuAINovel + PlotPilot + PenShot 三合页）
    #   新增/改名的文案。上一轮这批字符串没登记，英文界面下整页漏中文
    #   （`tools/verify_ui_english.py` 抓到 8 处）—— 这里补齐。
    # [EN] ★ 2026-10-17: copy for the External Creative Services page
    # [EN] (MuMuAINovel + PlotPilot + PenShot merged tab). These strings were
    # [EN] unregistered last round, leaking Chinese across the whole page in
    # [EN] English UI (`tools/verify_ui_english.py` caught 8 spots) -- filled in here.
    '外部创作服务': 'External Creative Services',
    '来自 AI模型配置': 'From AI Model Config',
    '（不覆盖 —— 用服务自己的配置）':
        "(Leave untouched — use the service's own config)",
    '服务地址': 'Service address',
    '连接参数': 'Connection settings',
    '启用 PlotPilot（总开关）': 'Enable PlotPilot (master switch)',
    '剧作者用它产出本章方案':
        "The screenwriter produces this chapter's plan with it",
    '启用 PenShot（总开关）': 'Enable PenShot (master switch)',
    '导演用它产出分镜方案': 'The director produces storyboards with it',
    '来自 PlotPilot（外部叙事引擎 → 剧作者）':
        'From PlotPilot (external narrative engine → screenwriter)',
    '这一页配的是**另一个程序**：PlotPilot（墨枢）—— 一个独立的「叙事引擎内核」，跑在本机，由本项目通过 HTTP 调用。它擅长在长篇跨度里维护人物一致性、因果链、伏笔与故事线结构，用来给**剧作者/编剧**设计『这一章该发生什么』。许可：Apache-2.0 + Commons Clause；上游：':
        'This page configures **a separate program**: PlotPilot — an independent '
        '"narrative-engine kernel" that runs locally and is called by this project '
        'over HTTP. It excels at maintaining character consistency, causal chains, '
        'foreshadowing and storyline structure across long spans, and is used to '
        'design "what should happen in this chapter" for the **screenwriter**. '
        'License: Apache-2.0 + Commons Clause; upstream:',
    '默认**关**。关掉 = 完全用本程序自己的编剧逻辑；打开后若服务没起/超时/空章，会自动退回本程序自己的编剧逻辑，并把降级原因记在产出上（不丢戏）':
        '**Off by default**. Off = fully use the built-in screenwriter logic; '
        'when on, if the service is not up / times out / returns empty, it '
        'automatically falls back to the built-in screenwriter logic and records '
        'the degradation reason in the output (no lost scene)',
    '上面选中哪个模型，保存时就把它写进 PlotPilot 自己的 novelservices/PlotPilot/.env：地址是 Anthropic → ANTHROPIC_*，火山方舟 → ARK_*，其余（含本地 Ollama）→ OPENAI_*；登记表里没有的模型或没有 Key 的会警告、不写。改完要重启那个服务':
        "Whichever model is picked above gets written into PlotPilot's own "
        'novelservices/PlotPilot/.env on save: an Anthropic address → ANTHROPIC_*, '
        'Volcano Ark → ARK_*, everything else (including local Ollama) → OPENAI_*; '
        'models missing from the registry or without a key warn and are not '
        'written. Restart that service afterwards',
    '来自 PenShot（外部导演/分镜引擎 → 导演）':
        'From PenShot (external director / storyboard engine → director)',
    '这一页配的是**另一个程序**：PenShot —— 一个独立的「AI 导演 / 分镜引擎」，跑在本机，由本项目通过 HTTP 调用。它把一段剧本拆成镜头分解（分镜）、情绪评分、配乐建议、可视化时间线，用来给**导演**安排『这一场怎么拍』。支持 **OpenAI 兼容**端点（Moonshot / DeepSeek / 硅基流动 / 本地 Ollama…）。上游：':
        'This page configures **a separate program**: PenShot — an independent '
        '"AI director / storyboard engine" that runs locally and is called by this '
        'project over HTTP. It breaks a script into a shot breakdown (storyboard), '
        'emotion scoring, music suggestions and a visual timeline, used to arrange '
        '"how to shoot this scene" for the **director**. Supports '
        '**OpenAI-compatible** endpoints (Moonshot / DeepSeek / SiliconFlow / '
        'local Ollama…). Upstream:',
    '默认**关**。关掉 = 完全用本程序自己的导演逻辑；打开后若服务没起/超时，会自动退回本程序自己的导演逻辑，并把降级原因记在产出上（不丢戏）':
        '**Off by default**. Off = fully use the built-in director logic; when '
        'on, if the service is not up / times out, it automatically falls back '
        'to the built-in director logic and records the degradation reason in '
        'the output (no lost scene)',
    '上面选中哪个模型，保存时就把它写进 PenShot 自己的 novelservices/PenShot/.env（PENSHOT_LLM__DEFAULT__* 与 PENSHOT_EMBED__DEFAULT__*：地址 / 密钥 / 模型名）。它是 OpenAI 兼容服务，登记表里的模型都能写；地址是原生 Ollama（11434）的话按 Ollama 协议写、不带密钥。改完要重启那个服务':
        "Whichever model is picked above gets written into PenShot's own "
        'novelservices/PenShot/.env on save (PENSHOT_LLM__DEFAULT__* and '
        'PENSHOT_EMBED__DEFAULT__*: address / key / model name). It is an '
        'OpenAI-compatible service, so every model in the registry can be '
        'written; a native Ollama address (11434) is written in Ollama protocol '
        'without a key. Restart that service afterwards',
    '**外部创作服务**（MuMuAINovel + PlotPilot + PenShot）：三个本程序之外的程序，地址 / 密钥 / 端口 / 生成参数各写进它们自己的 .env（改完要重启对应服务）。· MuMuAINovel（外部写小说服务）：可把它当「写手」写整章正文；· PlotPilot（叙事引擎内核）：给**剧作者**设计「这一章该发生什么、结构怎么立」；· PenShot（AI 导演 / 分镜引擎）：给**导演**拆「这一场怎么拍、机位怎么摆」。':
        '**External Creative Services** (MuMuAINovel + PlotPilot + PenShot): '
        'three programs outside this one; addresses / keys / ports / generation '
        'parameters each go into their own .env (restart the matching service '
        'after changes). · MuMuAINovel (external novel-writing service): can act '
        'as the "writer" for whole chapters of prose; · PlotPilot '
        '(narrative-engine kernel): designs for the **screenwriter** "what should '
        'happen in this chapter, how to structure it"; · PenShot (AI director / '
        'storyboard engine): breaks down for the **director** "how to shoot this '
        'scene, how to place the cameras".',
    '正在启动{n}…（可能要几分钟）': 'Starting {n}… (may take a few minutes)',
    '正在停止{n}…': 'Stopping {n}…',
    '{n}操作失败': '{n} operation failed',
    '{n}操作失败：{e}': '{n} operation failed: {e}',
    '{n}已启动': '{n} started',
    '{n}已停止': '{n} stopped',
    '（读不到配置 —— novelservices 被删掉了？）':
        "(Can't read config — was the novelservices folder removed?)",
    '登记表里找不到这条模型（{k}）—— 没写{n}的 .env':
        "Can't find that model in the registry ({k}) — {n}'s .env was not written",
    '⚠ {n} 的 .env 没写：{e}': "⚠ {n}'s .env was not written: {e}",
    'ℹ 已把选中的模型写入{n}自己的 .env —— **要重启那个服务**才生效':
        "ℹ The picked model has been written into {n}'s own .env — "
        '**restart that service** for it to take effect',
    '自动拉起 PlotPilot': 'Auto-start PlotPilot',
    '自动拉起 PenShot': 'Auto-start PenShot',
    '导出『最终改写稿』时改走 MuMuAINovel：据『原始稿 + 推演过程』重写每一天。关掉则导出沿用内部整理稿；打开后若服务没起/超时/写空，会自动退回内部整理稿并记明原因（不丢戏）':
        "When on, exporting the 'final rewritten draft' goes through MuMuAINovel instead: "
        'every day is rewritten from the "original draft + simulation history". '
        '**Off keeps the internal tidy draft**; when on, if the service is not up / '
        'times out / writes empty, it falls back to the internal tidy draft and '
        "records the reason -- the day's scene is never lost",
    '运行窗口底部的 AI 对话输入框':
        'AI chat input at the bottom of the run window',
    '来自 MuMuAINovel（外部写小说服务）': 'Provided by MuMuAINovel (external novel-writing service)',
    '这一页配的是**另一个程序**：MuMuAINovel —— 一个独立的「写小说」后端，跑在本机，由本项目通过 HTTP 调用。它不是本项目写的，上游在这里：':
        'This page configures **a separate program**: MuMuAINovel — an independent novel-writing backend that runs locally and is called over HTTP. It is not part of this project; upstream repository:',
    '许可：GPL-3.0。本地说明见 novelservices/MuMuAINovel/服务说明.md':
        'License: GPL-3.0. Local notes live under novelservices/MuMuAINovel/ (the .md file).',
    '当前状态：{s}': 'Status: {s}',
    '○ 没在运行': '○ Not running',
    '自动拉起创作服务': 'Auto-start the writing service',
    '● 正在运行：{u}': '● Running at {u}',
    '○ 没在运行（{why}）': '○ Not running ({why})',
    # 2026-10-17（用户：「天机打开现在报错」）：不再把桥的 `URLError` 原话贴进界面，
    # 改成"还没启动 + 端口"的人话 —— 这两条是替代它的新文案。
    # [EN] 2026-10-17 (user: "opening Tianji now errors"): no longer paste the bridge's raw
    # [EN] URLError text; use "not started yet + port" instead -- these two are the replacements.
    '○ 还没启动（端口 {p}）。需要时点下面的「启动服务」':
        '○ Not started yet (port {p}). Click "Start service" below when needed.',
    '○ 还没启动（端口 {p}）。打开「程序启动时自动拉起服务」，下次启动程序时它就会自己起':
        '○ Not started yet (port {p}). Turn on "start the service automatically at program '
        'start" and it will come up on the next launch.',
    # 2026-10-17：「启动/停止服务」弹窗（显示后台命令的全套输出）
    # [EN] 2026-10-17: the Start/Stop dialog (shows the full background command output)
    '准备中…': 'Preparing…',
    '下面是后台命令的完整输出（命令行 + stdout/stderr）：':
        'Full output of the background command (command line + stdout/stderr):',
    '✔ 完成': '✔ Done',
    '✘ 失败：{w}': '✘ Failed: {w}',
    '模块没加载': 'module not loaded',
    '→ {n}：{a}（下面的输出是实时刷的，可能要几分钟）':
        '→ {n}: {a} (the output below streams live; it may take a few minutes)',
    '→ MuMuAINovel：{a}（下面的输出是实时刷的，首次下模型可能要几分钟）':
        '→ MuMuAINovel: {a} (the output below streams live; the first model download can '
        'take a few minutes)',
    '✘ 没加载到 novelservices.{m} —— novelservices 目录被删了，或者里面缺依赖？':
        '✘ Could not load novelservices.{m} — was the novelservices folder deleted, or '
        'are its dependencies missing?',
    '✘ 没加载到 novelservices.mumu_bridge —— novelservices 目录被删了，或者里面缺依赖？':
        '✘ Could not load novelservices.mumu_bridge — was the novelservices folder '
        'deleted, or are its dependencies missing?',
    '{n}正在忙，等这次操作结束再点':
        '{n} is busy; try again when this operation finishes',
    '创作服务正在忙，等这次操作结束再点':
        'The writing service is busy; try again when this operation finishes',
    '{n}没成功：{why}': '{n} did not succeed: {why}',
    '（读不到它的配置 —— novelservices 被删掉了？）':
        '(Cannot read its config — was the novelservices folder removed?)',
    '（读不到：{e}）': '(Cannot read: {e})',
    '本程序怎么用它': 'How this app uses it',
    '启用创作服务（总开关）': 'Enable the writing service (master switch)',
    '默认**关**。关掉 = 完全用本程序自己的写法。打开后若服务没起/超时/写空，会自动退回本程序自己的写法，并把降级原因记在产出上（不会把这一天的戏弄丢）':
        'Off by default. Off = use this app\u2019s own writer. When on, if the service is down, times out, or returns an empty chapter, it falls back automatically and records why (the day\u2019s scene is never lost).',
    '小说作家用它写样章': 'Let the novelist write the daily draft with it',
    '打开后「写当天样章」这一步交给它；「收工整理稿」仍走本程序—— 那一步要求「今天没发生的一个字都不许加」，而它是自由写作，做不对':
        'When on, "write today\u2019s draft" is delegated to it. The end-of-day transcript still uses this app: that step requires "add nothing that did not happen today", which a free-writing service cannot honour.',
    '程序启动时自动拉起服务': 'Start the service automatically when the app starts',
    '关闭程序时一并停掉服务': 'Stop the service when the app closes',
    '★ 改这一项要重启程序才生效。关掉则自己跑 backend/novelservice.py start':
        '★ Takes effect after restarting the app. If off, run backend/novelservice.py start yourself.',
    '关窗口时停创作服务失败': 'Failed to stop the writing service on window close',
    '默认**开**：关掉程序就真的什么都不留（那个服务是后台常驻的，默认会一直占着 8001 端口）。关掉它 = 服务留着，下次启动**不用冷启动**（首次要下模型，可能几分钟）。\n⚠ 这一项**两个地方都会读**：启动器 `start.exe`（主窗口退出后由它收尸）和本程序自己。所以它**立刻生效、不用重启**。':
        'On by default: closing the app really leaves nothing behind (the service is a '
        'background daemon and would otherwise keep holding port 8001). Turn it off and the '
        'service stays, so the next start needs no cold boot (the first run may download a '
        'model and take minutes).\n'
        '★ Two places read this: the launcher `start.exe` (it cleans up after the main '
        'window exits) and this app itself. So it takes effect immediately, no restart needed.',
    '生成参数': 'Generation settings',
    '单章等待上限(秒)': 'Chapter wait limit (s)',
    '目标字数': 'Target words',
    '等待上限**别调太小**：实测同一章 17 秒到 207 秒都出现过，推理模型想多久控不住；超时 = 这一章白等':
        'Do not set the wait limit too low: the same chapter took anywhere from 17 s to 207 s in testing — a reasoning model\u2019s thinking time is uncontrollable. A timeout wastes that chapter.',
    '每章做一次分析（慢）': 'Analyse every chapter (slower)',
    '开着它下一章能「记得住」，代价是明显更慢。分析模型留空 = deepseek-chat':
        'On, the next chapter "remembers"; the cost is being clearly slower. Leave the analysis model empty = deepseek-chat.',
    '分析模型': 'Analysis model',
    '技能名': 'Skill name',
    'MuMuAINovel 自己的参数': 'MuMuAINovel\u2019s own settings',
    '⚠ 下面这几项**存在它自己的 novelservices/MuMuAINovel/backend/.env 里**，不抄进本程序的 .env（保持单一来源）。改完**要重启那个服务**才生效。':
        '⚠ The items below are stored in **its own** novelservices/MuMuAINovel/backend/.env, not copied into this app\u2019s .env (single source of truth). They take effect only after **restarting that service**.',
    '接口地址': 'API base URL',
    '默认生成模型': 'Default model',
    '温度': 'Temperature',
    '单次最大 token': 'Max tokens per call',
    '服务端口': 'Service port',
    'Key 填本程序在用的那个也行（同一家模型服务）':
        'You can reuse the key this app already uses (same model provider).',
    '写小说用**不思考**的模型更稳（如 deepseek-chat）：推理模型会把输出预算烧在思考上，实测最坏一次想 22876 字符、正文 0 字':
        'For novel writing, a **non-thinking** model is more reliable (e.g. deepseek-chat): a reasoning model burns the output budget on thinking — worst case measured: 22,876 chars of thinking, 0 chars of prose.',
    '⚠ MuMuAINovel 自己的配置没写成功：{e}': '⚠ Could not write MuMuAINovel\u2019s own config: {e}',
    'ℹ MuMuAINovel 自己的参数已写入它的 backend/.env —— **要重启那个服务**才生效':
        'ℹ MuMuAINovel\u2019s settings were written to its own backend/.env — they take effect only after **restarting that service**',

    # ── 详细程度 / 时间系统（2026-10-30）──
    # [EN] Detail level / time system
    '详细程度': 'Detail level',
    '很详细': 'Very detailed',
    '详细': 'Detailed',
    '中间': 'Balanced',
    '简略': 'Brief',
    '带过': 'Skipped over',
    '恢复跟随天机': 'Follow Tianji again',
    '一举一动都写到底：一句话、一个眼神都算一拍，看得最慢':
        'Every gesture is written out: one line, one glance is a beat. The slowest watch.',
    '一场戏细写到底；一拍推一两分钟故事':
        'A scene written out in full; one beat covers one or two story minutes',
    '正常叙事：一场戏几拍带过，一拍推三五分钟':
        'Normal narration: a scene takes a few beats, each covering 3-5 story minutes',
    '只交代关键几步，细节从略，一拍推十来分钟':
        'Only the key steps, details skipped; one beat covers about ten minutes',
    '一句话交代过去（一段路、几个月的空白），一拍推半小时上下':
        'Summed up in one line (a journey, months of nothing); one beat covers ~half an hour',
    '当前这两个数不在任何一档里（自己定的）；选一档会把它们改回那一档的数':
        'These two numbers are not on any level (set by hand). Picking a level resets them to that level\u2019s numbers.',
    '**全局配置**：这里是整台机器的默认节奏。某一本书想不一样，去「书斋 · 运行」单独设 —— 那边一改就**覆盖**这里，这里不会跟着变。':
        '**Global config**: the default pace for this whole machine. For one book to differ, set it in Study · Run — a change there **overrides** this, and this page stays as it is.',
    '**这里的配置会覆盖全局配置**：下面每一项只对「{name}」这本书生效；「天机 · 运行」里的是整台机器的默认节奏。\n没动过的项照旧跟天机走；改过的项列在最后一行，点「恢复跟随天机」可以全部还原。':
        '**These settings override the global ones**: every item below applies to 「{name}」 only; Tianji · Run holds the machine-wide default pace.\nUntouched items keep following Tianji; the ones you changed are listed on the last line, and "Follow Tianji again" reverts them all.',
    '这本书覆盖了：{items}': 'Overridden for this book: {items}',
    '这本书没有任何覆盖项：全部跟随「天机 · 运行」里的全局值。':
        'Nothing is overridden for this book: it follows the global values in Tianji · Run.',
    '已改为跟随天机（点「保存」后落盘）':
        'Now following Tianji (written to the project file on Save)',
    '运行设定（{n} 项覆盖全局）': 'Run settings ({n} overriding the global)',
    '撤回运行设定失败': 'Failed to revert the run settings',
    '装载这本书的运行设定失败（按全局跑）':
        'Failed to load this book\u2019s run settings (running on the global values)',
    '「运行模式」决定这一卷跑到哪停、「起始点」决定从哪一天开演（与「起笔」里选的是同一个值）。':
        '"Run mode" decides where this volume stops; "start point" decides which day it plays from (the same value you pick in Start Writing).',
    '「详细程度」选一档就同时定下「时间倍率」和「一拍」，两个数也可以自己改（改完那一档会变成「自定义」）。「心跳间隔」只是循环多久醒一次，一般不用动。':
        'Picking a detail level sets both "time ratio" and "per beat" at once; you can also edit the two numbers by hand (the level then becomes "Custom"). "Heartbeat interval" only decides how often the loop wakes up — usually leave it alone.',
    '这本书**怎么跑**：跑到哪停、从哪天开演，以及节奏（详细程度 / 时间倍率 / 一拍）。\n**这里的配置会覆盖全局**：「天机 · 运行」是整台机器的默认值，在这里改过的项只对这本书生效。':
        'How **this book** runs: where it stops, which day it plays from, and its pace (detail level / time ratio / per beat).\n**These override the global settings**: Tianji · Run holds the machine-wide defaults; anything changed here applies to this book only.',
    '这本书的**类型与风格**：故事类型、笔法、场景名、输出语言。（这些是**这本书**的设置，与程序设置无关）':
        'This book\u2019s **type and style**: genre, prose style, scene name, output language. (These belong to **this book**, not to the program.)',
}


def t(text: str, /, **kw) -> str:
    """翻译。中文环境原样返回；英文环境查表，未登记则回退原文。
        English:
    Translate. In the Chinese environment returns as-is; in the English environment looks up the
    table, falls back to the original if not registered.
    """
    out = text if _current == 'zh' else _ZH2EN.get(text, text)
    if kw:
        try:
            out = out.format(**kw)
        except (KeyError, IndexError, ValueError):
            pass
    return out


def missing_keys() -> list[str]:
    """（开发用）列出待补的 key —— 目前返回空，占位便于后续校验。
        English:
    (For development) List the keys pending translation —— currently returns empty, a placeholder
    for later validation.
    """
    return []


# ══════════════════════════════════════════════════════════════════
#  开卷打磨 Agent（2026-10-07）
# [EN] Kaijuan polish Agent (2026-10-07)
# ══════════════════════════════════════════════════════════════════
#  `polish/` 那一包里的文案：沙盒拒绝的理由、工具回给模型的话、界面上的提示。
#  ⚠ 拒绝理由**必须翻译**：英文界面下冒中文，作者会以为程序坏了 ——
#    而这个项目里"沙盒拒绝"恰恰是他最可能撞见的一类消息。
#  ⚠ 这一块是 `_ZH2EN.update(...)`，不是字典字面量的一部分 ——
#    `i18n_check` 照样查得到（它扫文件里**所有** Dict 节点）。
# [EN] Text in the `polish/` package: sandbox rejection reasons, messages the tools return to the
# [EN] model, UI hints.
# [EN] ⚠ Rejection reasons **must be translated**: under an English UI, Chinese text popping up makes
# [EN] the author think the program is broken ——
# [EN] and in this project, "sandbox rejection" is precisely the kind of message he is most likely to
# [EN] run into.
# [EN] ⚠ This block is `_ZH2EN.update(...)`, not part of the dict literal ——
# [EN] `i18n_check` can still find it (it scans **all** Dict nodes in the file).
_ZH2EN.update({
    '\n…（设定较长，已截断；可以用「读设定」带路径只看某一段）':
        '\n… (the settings are long, so this is truncated; use 「read settings」 with a path to see one part)',
    '## 改了什么':
        '## What changed',
    '## 现场生成的工具（在项目的 AI工具/ 里）':
        "## Tools written on the spot (in the project's AI工具/)",
    '## 过程（调过哪些工具）':
        '## What it did (which tools it called)',
    '## 追加回引用文件夹的文件':
        '## Files appended to the reference folder',
    '- （这一场没有改动设定）':
        '- (nothing was changed this session)',
    '> 由打磨 Agent 在开卷时生成；**引用文件夹里正文一个字没动**':
        '> Written by the polishing agent at ingest time; **not a single word of the reference folder was touched**',
    '{n} 不是动作工具（它由流程处理）':
        '{n} is not an action tool (the flow handles it)',
    '{n} 是内置工具名，换一个':
        '{n} is a built-in tool name — pick another one',
    '→ 调它：{{"想":"…","用":"{n}","参":{{…}}}}':
        '→ call it with: {{"想":"…","用":"{n}","参":{{…}}}}',
    '★ 你上一轮交的东西**自查出这些问题**，请在这一轮里改掉：':
        '★ The self-check on your last pass found these problems — fix them this round:',
    '⚠ 我自查时还看出这些问题，没能在一轮里解决：':
        '⚠ The self-check still sees these and they were not resolved in one round:',
    '⚠ 试跑**没通过**，先看这个再决定要不要修：{why}':
        '⚠ The trial run **failed** — read this before deciding whether to fix it: {why}',
    '「打磨结论也写一份到引用文件夹」：把「这次改了什么」追加成 `AI打磨记录.md`。同样只追加、留备份；项目里也留一份同样的。':
        '「Also write the polishing notes into the reference folder」: appends "what changed" as `AI打磨记录.md`. Append-only with a backup, exactly like the other one; the project keeps an identical copy.',
    '【现在的设定】':
        '[Current settings]',
    '【现在请你处理】作者刚说的：{x}':
        '[Your turn] The author just said: {x}',
    '一处都没改成：\n':
        'Not one change went through:\n',
    '下标越界：{k}':
        'Index out of range: {k}',
    '不能删掉整份设定':
        'You cannot delete the whole settings object',
    '不能把整份设定替换掉（请指定具体路径）':
        'You cannot replace the whole settings object (give a concrete path)',
    '不行：{why}':
        'Not allowed: {why}',
    '不认得的动作「{a}」（只有 改/加/删）':
        'Unknown action "{a}" (only 改 / 加 / 删)',
    '不许从 {m} 里导入（可用的只有：{ok}）':
        'Importing from {m} is not allowed (only: {ok})',
    '不许取双下划线属性（{a}）—— 那是绕开沙盒的经典入口':
        'Dunder attribute access ({a}) is not allowed — it is the classic sandbox escape',
    '不许导入 {m}（可用的只有：{ok}）':
        'Importing {m} is not allowed (only: {ok})',
    '不许用 {n} —— 文件读写请用沙盒给的 read_text / write_text / list_files，它们会替你检查路径':
        '{n} is not allowed — use the sandbox helpers read_text / write_text / list_files, they check the path for you',
    '不许调用 {a}（删除 / 改名 / 写盘 / 起进程 这类操作一律不开放；要写东西请用 write_text 写到打磨输出区）':
        'Calling {a} is not allowed (deleting / renaming / writing to disk / spawning are all closed; to write something use write_text into the polishing output area)',
    '作者：{x}':
        'Author: {x}',
    '你是这本小说《{n}》的**设定打磨师**，替作者把开卷时自动提取出来的设定打磨好。':
        'You are the **settings polisher** for the novel "{n}"; your job is to polish the settings that were auto-extracted at ingest time.',
    '写文件只能写打磨输出区（前缀 {o}）—— 想改引用文件夹请用 append_source 工具（只追加、自动留备份）':
        'You may only write into the polishing output area (prefix {o}) — to touch the reference folder use the append_source tool (append-only, automatic backup)',
    '到了步数上限（{n} 步），先把现状讲清楚':
        'Hit the step limit ({n} steps) — sum up where things stand',
    '参数由这个工具自己定（看它的源码）':
        'This tool defines its own arguments (see its source)',
    '取不到这一段：{why}。可以先用「读设定」不填路径看全貌':
        'Cannot read that part: {why}. Try 「read settings」 with no path to see the whole thing',
    '只收相对路径（不要盘符、不要开头的斜杠）：{p}':
        'Only relative paths (no drive letter, no leading slash): {p}',
    '子进程没有回话（退出码 {c}）':
        'The child process did not answer (exit code {c})',
    '工具「{n}」已经生成好了，现在起你可以直接调它。':
        'Tool "{n}" is generated — you can call it directly from now on.',
    '工具「{n}」返回：\n{x}':
        'Tool "{n}" returned:\n{x}',
    '工具名只用汉字/字母/数字/下划线，最长 24 字':
        'Tool names may only use Chinese/letters/digits/underscore, max 24 characters',
    '工具调用次数超过上限（{n} 次）—— 停下来收尾吧':
        'Tool-call limit reached ({n}) — stop and wrap up',
    '已**追加**到 {p}（{n} 字）；原文件留了一份 {p}.bak，正文一个字没动':
        '**Appended** to {p} ({n} chars); the original was copied to {p}.bak and not a word of it changed',
    '已写入 {p}（{n} 字）':
        'Written to {p} ({n} chars)',
    '已新建 {p}（{n} 字）':
        'Created {p} ({n} chars)',
    '引用文件夹（前缀 {p}，只能追加）':
        'reference folder (prefix {p}, append-only)',
    '当前评档：{x}':
        'Current tier: {x}',
    '打磨 Agent 起不来（退回一问一答）':
        'The polishing agent could not start (falling back to one-shot Q&A)',
    '打磨 Agent 这一轮失败':
        'The polishing agent failed this round',
    '打磨产物搬进项目失败（不影响开卷）':
        'Moving the polishing artefacts into the project failed (ingest is unaffected)',
    '打磨记录写回引用文件夹失败':
        'Writing the polishing notes back to the reference folder failed',
    '打磨输出区（前缀 {p}，可新建可覆盖）':
        'polishing output area (prefix {p}, creating and overwriting allowed)',
    '找不到这个文件：{p}':
        'No such file: {p}',
    '搜到 {n} 处：':
        'Found {n} hits:',
    '改了 {n} 处：':
        'Changed {n} places:',
    '整理打磨记录失败（不影响开卷）':
        'Building the polishing report failed (ingest is unaffected)',
    '未知原因':
        'unknown reason',
    '模型没有给出可用的动作':
        'the model gave no usable action',
    '沙盒不允许导入 {m}（可用的只有：{ok}）':
        'The sandbox does not allow importing {m} (only: {ok})',
    '没有这一项：{k}':
        'No such item: {k}',
    '没有这个工具：{n}。可用的有：{ok}':
        'No such tool: {n}. Available: {ok}',
    '离黄金档还缺：{x}':
        'Still missing for the Gold tier: {x}',
    '自省发现 {n} 个问题，再走一轮：{x}':
        'Self-check found {n} problems; going one more round: {x}',
    '自省：{x}':
        'Self-check: {x}',
    # ── 「我懂你这句的意思了」（polish/intent.py，2026-10-11）──
    # [EN] ── "I understood that" (polish/intent.py, 2026-10-11) ──
    '好，有问题我会再问你。':
        'OK, I will ask you when something comes up.',
    '好，接下来 {n} 轮我不会问你 —— 拿不准的我自己定，'
    '并把我的假设写在回话里。':
        'OK, I will not ask you for the next {n} rounds -- I will decide the uncertain parts myself '
        'and write my assumptions into my reply.',
    '好，从现在起我不再问你（要我重新问你，说一句「可以问我了」）。':
        'OK, I will not ask you again from now on (say "you can ask me now" to turn that back on).',
    '你说的是上面那 {n} 条 —— 这一轮我**全都**改掉。':
        'You mean those {n} items above -- I will fix **all** of them this round.',
    '我理解你要的是第 {x} 条 —— 这一轮就改这几条。':
        'I read that as items {x} -- I will change exactly those this round.',
    '这一轮要做的（作者点名）：\n{x}':
        'To do this round (named by the author):\n{x}',
    '（作者说了**不要问他** —— 这一句不许用「问」。'
    '按你认为最合理的做法**直接做**，'
    '把你替他定的那几处，连同理由，写进「终」的回话里。）':
        '(The author said **do not ask him** -- this sentence may not use "ask". '
        '**Just do** what you judge best, and write the parts you decided for him, with reasons, '
        'into the "final" reply.)',
    '★ 作者这一轮**点名**要做的事（全部做完再收尾，一条不落）：':
        '★ What the author **named** to be done this round (finish all of it before wrapping up, '
        'not one missed):',
    # ── 语言审校的出口（2026-10-12）──
    # [EN] ── The language review's outlet (2026-10-12) ──
    ' —— 细节并进了下面的「今日总结」':
        ' -- the details were merged into "today\'s summary" below',
    ' —— 细节在「语言审校.md」':
        ' -- the details are in "语言审校.md"',
    #  ⚠ **key 必须与源码逐字相同**（含开头的 `★★`）—— 上一轮这里少了一个 `★`，
    #    于是英文界面下那句话**静默退回中文**，而 `i18n_check`（只查 GUI 那半）看不见它。
    #    ⇒ 查 i18n 一律用 `--all`（查全项目），别用默认那个只查 GUI 的口径。
    # [EN] ⚠ The **key must match the source verbatim** (including the leading `★★`) -- last round this
    # [EN] one was missing a `★`, so that sentence **silently fell back to Chinese** in the English UI, and
    # [EN] `i18n_check` (which only covers the GUI half) could not see it.
    # [EN] ⇒ Always check i18n with `--all` (whole project), not the default GUI-only scope.
    '★★ 作者明确要求：**{x}**。所以：\n'
    '· 这一轮**不许**用「问」这个动作；\n'
    '· 拿不准的，按你认为最合理的做法**直接定了**，'
    '并把你替他做的判断与理由，写进「终」的回话里；\n'
    '· 清单上的事**全做完**再收尾。':
        '★ The author requires: **{x}**. Therefore:\n'
        '· This round you may **not** use the "ask" action;\n'
        '· For anything uncertain, **just decide** what you judge best, and write the calls you made '
        'for him, with reasons, into the "final" reply;\n'
        '· Finish **everything** on the list before wrapping up.',
    '从现在起都不要问':
        'do not ask from now on',
    '接下来 {n} 轮（含这一轮）都不要问':
        'do not ask for the next {n} rounds (including this one)',
    '装回了 {n} 个上次生成的工具：{x}':
        'Reloaded {n} tools generated earlier: {x}',
    '要给出「代码」':
        '「code」 is required',
    '要给出「关键词」':
        '「keyword」 is required',
    '要给出「内容」':
        '「content」 is required',
    '要给出「名称」和「代码」':
        '「name」 and 「code」 are required',
    '要给出「操作」，形如 [{"动作":"改","路径":"人物[0].性格","值":"…"}]':
        '「ops」 is required, e.g. [{"动作":"改","路径":"人物[0].性格","值":"…"}]',
    '要给出「路径」和「内容」':
        '「path」 and 「content」 are required',
    '要给出「路径」（可以先「列引用文件」看看）':
        '「path」 is required (try 「list reference files」 first)',
    '要追加的内容 {n} 字节，超过单文件上限 {m} 字节':
        'The text to append is {n} bytes, over the {m}-byte per-file limit',
    '试跑通过（{s} 秒）。它回的是：\n{x}':
        'Trial run passed ({s}s). It returned:\n{x}',
    '语法错误：第 {n} 行附近 —— {msg}':
        'Syntax error near line {n} — {msg}',
    '读不出这个工具的源码：{e}':
        "Cannot read this tool's source: {e}",
    '读不到这个文件：{p}':
        'Cannot read this file: {p}',
    '起不了子进程：{e}':
        'Cannot start the child process: {e}',
    '超出了一次打磨的许可范围：{p}':
        'Outside the scope allowed for this polishing session: {p}',
    '跑了 {n} 秒还没停，已被强制中断（大概率是死循环）':
        'Still running after {n}s and was killed (most likely an infinite loop)',
    '路径写法有问题：{why}':
        'The path is malformed: {why}',
    '路径片段看不懂：{s}（写法像「人物[0].性格」或「伏笔」）':
        'Cannot parse this path segment: {s} (write it like 「人物[0].性格」 or 「伏笔」)',
    '路径解析失败：{e}':
        'Path resolution failed: {e}',
    '路径里不许出现 ..（想往上跳一级是不允许的）：{p}':
        'Paths may not contain .. (going up one level is not allowed): {p}',
    '这一层不是对象，改不了：{k}':
        'That level is not an object and cannot be changed: {k}',
    '这一步没拿到动作：{why}':
        'No action came back on this step: {why}',
    '这一项不是对象：{x}':
        'This entry is not an object: {x}',
    '这个工具自己出错了：{e!r}':
        'The tool itself errored: {e!r}',
    '这个工具还不能用，先改这几点：\n· ':
        'This tool is not usable yet — fix these first:\n· ',
    '这个工具还没接上：{n}':
        'This tool is not wired up yet: {n}',
    '这份内容 {n} 字节，超过单文件上限 {m} 字节':
        'This content is {n} bytes, over the {m}-byte per-file limit',
    '这几处没成：':
        'These did not go through:',
    '这是程序自己生成的资料，不在打磨范围内：{p}':
        'This file was generated by the program and is out of scope for polishing: {p}',
    '这次会话关掉了「动态生成工具」':
        'Generating tools on the spot is turned off for this session',
    '这次会话关掉了「现场写代码」':
        'Writing code on the spot is turned off for this session',
    '这次会话没有可写的打磨输出区':
        'This session has no writable polishing output area',
    '这次会话没有可写的打磨输出区，生成不了工具':
        'This session has no writable polishing output area, so no tool can be generated',
    '这次会话没有连接引用文件夹':
        'This session is not connected to a reference folder',
    '这次会话被设定为不回写引用文件夹':
        'This session is set not to write back into the reference folder',
    '这次没有连接引用文件夹':
        'No reference folder is connected this time',
    '这段代码里必须有一个顶层函数 run(args)（我要调它）':
        'The code must define a top-level function run(args) (I need to call it)',
    '那是一个目录，不能当文件写：{p}':
        'That is a directory and cannot be written as a file: {p}',
    '（{p} 共 {n} 字，这次给你第 {s}~{e} 字）':
        '({p} has {n} chars; here are chars {s}–{e})',
    '（上次生成的工具）':
        '(a tool generated earlier)',
    '（上面这次没拿到东西。换个手段：先「列引用文件」或「读设定」看一眼现状，再决定怎么做。）':
        '(Nothing came back. Change tack: first 「list reference files」 or 「read settings」 to see where things stand, then decide.)',
    '（你这一轮回的 JSON 里既没有「用」也没有「终」也没有「问」。照着协议回一个。）':
        '(Your JSON this round had none of 「用」/「终」/「问」. Reply following the protocol.)',
    '（同名的那份被这次的新版本覆盖了）':
        '(the file of that name was overwritten by this new version)',
    '（引用文件夹里没有可读的文件）':
        '(the reference folder has no readable files)',
    '（未命名）':
        '(unnamed)',
    '（没有可用的目录，只能改内存里的设定）':
        '(no usable folders — only the in-memory settings can be changed)',
    '（没有搜到「{k}」）':
        '(no hits for "{k}")',
    '（没能跑成）{why}':
        '(it did not run) {why}',
    '（现场生成的工具）':
        '(a tool written on the spot)',
    '（空指令，没动任何东西）':
        '(empty instruction, nothing was touched)',
    '（空）':
        '(empty)',
    '（系统提示）{x}':
        '(system note) {x}',
    '（结构化的改动明细）{x}':
        '(structured change details) {x}',
    '（跑完了，没有输出）':
        '(it finished with no output)',
    '（过程中打印：{x}）':
        '(printed along the way: {x})',
    '（还没有过程记录）':
        '(no transcript yet)',
    '（这一轮我先停在这 —— 我做的事都记在上面了。你可以说一句"接着做"，也可以直接告诉我下一步要改什么。）':
        '(I stopped here for this round — everything I did is logged above. You can say "carry on", or just tell me what to change next.)',
    '（这一轮没有改动）':
        '(nothing changed this round)',
    '（这一轮没走完：{ex}）':
        '(this round did not finish: {ex})',
    '（这是我刚看过的体检结论）\n{x}':
        '(this is the review conclusion I just read)\n{x}',
    '（这是本轮第 {n}/{m} 步；步数用完我就会停下来收口）':
        '(this is step {n}/{m} of this round; when the steps run out I stop and wrap up)',

    # ── 开卷 AI 优化：轮数上限 + 强制停止（2026-10-08）──────────────────
    # 用户原话：「开卷 AI 优化 要有轮数上限且有地方配置 而且可以点击某个按钮强制停止」。
    # 天机 ·「运行」→「开卷打磨」那一节的三个数、摄取窗口里那个「⏹ 强制停止」按钮，
    # 以及它们全部的过程播报。
    # [EN] ── Kaijuan AI optimization: round cap + force stop (2026-10-08) ──────────────────
    # [EN] User's exact words: "Kaijuan AI optimization should have a round cap and a place to configure
    # [EN] it, and a button to force stop".
    # [EN] Tianji · "Run" → the three numbers in the "Kaijuan polish" section, the "⏹ Force stop" button in
    # [EN] the ingestion window,
    # [EN] and all their progress broadcasts.
    '⏹ 强制停止':
        '⏹ Force stop',
    '⏹ 已强制停止（这一轮作废，已改的设定保留）':
        '⏹ Force-stopped (this round is dropped; changes already made are kept)',
    '⏹ 已达轮数上限（{n} 轮）—— 等你收工':
        '⏹ Round limit reached ({n} rounds) — waiting for you to wrap up',
    '⏹ 这一轮被你停掉了（已经改好的设定保留，可以继续说下一句）。':
        '⏹ You stopped this round (the settings already changed are kept; '
        'you can just say the next thing).',
    '⏹ AI 优化已到轮数上限（{n} 轮）—— 想接着聊就把「天机 · 运行 · 开卷打磨」里的'
    '「优化轮数」调大，或直接点「完成优化并进入」':
        '⏹ AI refinement reached its round limit ({n} rounds) — raise '
        '「Refinement rounds」 under Global settings · Run · Ingest refinement '
        'to keep going, or just press 「Finish and enter」',
    'AI 正在处理：{what}（想停就点「⏹ 强制停止」）':
        'AI is working on: {what} (press 「⏹ Force stop」 to stop it)',
    '打磨中':
        'refining',
    '开场体检':
        'opening review',
    '第 {n} 轮':
        'round {n}',
    '打磨这一轮失败':
        'this refinement round failed',
    '（开场体检被你停掉了 —— 你可以直接告诉我你要改什么，不用等它。）':
        '(You stopped the opening review — just tell me what you want changed; '
        'no need to wait for it.)',
    '[{ts}] ⏹ 你按了「强制停止」—— 正在打断这一轮 AI…':
        '[{ts}] ⏹ You pressed 「Force stop」 — interrupting this round of AI…',
    '[{ts}] ⏹ 你按了「强制停止」—— 优化到此为止，开始收尾':
        '[{ts}] ⏹ You pressed 「Force stop」 — refinement ends here, wrapping up',
    '[{ts}] （现在没有正在跑的 AI）':
        '[{ts}] (no AI is running right now)',
    '[{ts}] ⏹ 开场体检已强制停止':
        '[{ts}] ⏹ The opening review was force-stopped',
    '[{ts}] ⏹ 第 {n} 轮已强制停止（改动的部分保留）':
        '[{ts}] ⏹ Round {n} was force-stopped (changes made so far are kept)',
    '[{ts}] 设定已更新（第 {n} 轮）':
        '[{ts}] Settings updated (round {n})',
    '[{ts}] 已到轮数上限（{n} 轮）—— 这条指令没有执行':
        '[{ts}] Round limit reached ({n} rounds) — this instruction was not run',
    '[{ts}] ⏹ 已到 AI 优化轮数上限（{n} 轮）—— 不再收新指令，请点「完成优化并进入」':
        '[{ts}] ⏹ AI refinement hit its round limit ({n} rounds) — '
        'no new instructions; please press 「Finish and enter」',
    # 天机 ·「运行」→「开卷打磨」（三个数）
    # [EN] Tianji · "Run" → "Kaijuan polish" (three numbers)
    '开卷打磨':
        'Ingest refinement',
    '优化轮数':
        'Refinement rounds',
    '每轮步数':
        'Steps per round',
    '工具次数':
        'Tool calls',
    '只管开卷那一段的「AI 优化」：\n'
    '· 「优化轮数」= 你发一条指令算一轮，最多几轮；到上限就不收新指令了；\n'
    '· 「每轮步数」= AI 收到一条指令后，最多走几步（想 → 用工具 → 看结果 算一步）；\n'
    '· 「工具次数」= 一场打磨总共最多调多少次工具。\n'
    '中途想打断正在跑的那一轮：摄取窗口里那个「⏹ 强制停止」随时可点。':
        'These numbers only govern the 「AI refinement」 step of opening a book:\n'
        '· 「Refinement rounds」 = one round per instruction you send; how many at '
        'most. Once the limit is hit, no new instructions are accepted;\n'
        '· 「Steps per round」 = after one instruction, how many steps the AI may '
        'take at most (think → use a tool → read the result counts as one step);\n'
        '· 「Tool calls」 = how many tool calls one refinement session may make in total.\n'
        'To interrupt the round that is running right now: the 「⏹ Force stop」 button '
        'in the ingest window is always clickable.',
    # 开卷向导第 3 步的说明
    # [EN] Explanation for step 3 of the Kaijuan wizard
    '轮数与叫停：AI 优化最多来回 {n} 轮（你每发一条指令算一轮），'
    '到上限就不再收新指令，让你点「完成优化并进入」；'
    '正在跑的那一轮随时可以用「⏹ 强制停止」打断'
    '（已经改好的设定保留）。这两个数都能在'
    '天机 ·「运行」→「开卷打磨」里改。':
        'Rounds and stopping: AI refinement allows at most {n} rounds back and forth '
        '(one round per instruction you send). Once the limit is hit, no new '
        'instructions are accepted and you are asked to press 「Finish and enter」. '
        'The round that is running right now can be interrupted at any time with '
        '「⏹ Force stop」 (settings already changed are kept). Both numbers live under '
        'Global settings · Run · Ingest refinement.',
    '打磨 Agent：它会**记得整场对话**（你说过的、它查过的、改过的都在），'
    '会自己动手改设定、读你的素材、必要时**现场写一个小工具**'
    '（在沙盒里跑，只能写打磨暂存区），做完还会**自查一遍**有没有漏改、'
    '改坏或越权。想关掉：天机 ·「运行」→「开卷打磨」那一节。':
        'The refining Agent **remembers the whole conversation** (what you said, what '
        'it looked up, what it changed), changes settings on its own, reads your '
        'material, writes a small tool on the spot when needed (it runs in a sandbox '
        'and may only write the polishing scratch area), and reviews itself at the end '
        'for missed edits, damage, or overreach. To turn it off: Global settings · Run · '
        'Ingest refinement.',

    # ── 小地图：只画"当前故事所在的地点"（2026-10-08）────────────────────
    # 用户 2026-10-08：小地图上主角所在的那一处旁边画着一串**世界层级**的名字
    # （各界、各域），用户说「这些不是真实的地名」，要求
    # 「只根据当前发生的故事所在的地点画图，而不是根据整本小说设定画图」。
    # [EN] ── Minimap: only draw "the location where the current story takes place" (2026-10-08)
    # [EN] ────────────────────
    # [EN] User 2026-10-08: on the minimap, next to the place where the protagonist is, a string of **world
    # [EN] hierarchy** names is drawn
    # [EN] (various realms, various domains); the user said "these are not real place names" and requested
    # [EN] "only draw the map based on the location where the current story takes place, not based on the
    # [EN] entire novel's setting".
    '今天这场戏就在这一处':
        'Today\'s scene is right here',
    '今天这张图还没出来（导演写完当天剧本、美术出工才有）—— 先只标出你所在的这一处':
        'Today\'s map is not out yet (it comes after the director writes the day\'s '
        'script and the art department draws it) — for now only your current spot is '
        'marked',
    '相对位置由模型按当天剧情摆放（仅供参考）':
        'Relative positions are placed by the model from today\'s script (for reference '
        'only)',
    '还不知道你在哪儿 —— 等第一场戏开演就有了':
        'Your location is not known yet — it appears once the first scene starts',

    # ── 剧组面板「谁在干活」高亮（2026-10-08）────────────────────────────
    # 用户：「右侧的剧组成员 谁在干活请高亮显示 等不干活了再恢复普通样式
    # 以让用户知道谁在干活」。
    # [EN] ── Crew panel "who is working" highlight (2026-10-08) ────────────────────────────
    # [EN] User: "In the crew members on the right, please highlight who is working, and restore the normal
    # [EN] style when they are no longer working
    # [EN] so the user knows who is working".
    '出工中…':
        'working…',
    '出工中 · 已跑 {s} 秒':
        'working · {s}s so far',
    '{n} 位正在出工（高亮的那几位）':
        '{n} crew members are working (the highlighted ones)',
    '刷新剧组面板失败':
        'Refreshing the crew panel failed',

    # ── 定时落盘（2026-10-08）────────────────────────────────────────────
    # 用户：「我点暂停的时候以及平时也有可能随时关闭软件 所以后台还需要一个
    # 定时器实现定时落盘 比如没30秒落盘一次」。
    # [EN] ── Periodic save to disk (2026-10-08) ────────────────────────────────────────────
    # [EN] User: "When I click pause, and at other times, I might close the software at any moment, so the
    # [EN] backend also needs a
    # [EN] timer to save to disk periodically, e.g. save once every 30 seconds".
    '自动落盘':
        'autosave',
    '自动落盘 · 每 {n} 秒':
        'autosave · every {n}s',
    '自动落盘 · 每 {n} 秒（{s} 秒前）':
        'autosave · every {n}s ({s}s ago)',
    '自动落盘 · 已关闭':
        'autosave · off',
    # ── 续跑：「起笔」时这一轮从哪天哪个时辰开始（2026-10-08）────────
    # 用户原话：「运行窗口起笔 加一个逻辑 点击之后如果检查发现一天的时间还没结束
    # （之前在一天没结束的时候点的停止）则提示从某一天某个时间继续，
    # 如果一天已经结束了，则开启新一天」。
    # [EN] ── Resume: at "start writing", the round begins from which day and which hour (2026-10-08)
    # [EN] ────────
    # [EN] User's exact words: "In the run window's start writing, add a logic: after clicking, if it finds
    # [EN] that the day has not yet ended
    # [EN] (stop was clicked before the day ended), then prompt to continue from a certain day and time;
    # [EN] if the day has already ended, then start a new day".
    '从哪儿开始': 'Where this run starts',
    '第 {n} 天': 'day {n}',
    '从头开始 —— 第 1 天': 'Starting from the beginning - day 1',
    '这本书还没有跑过（上一轮没留下停点）。':
        'This book has not been run yet (the previous run left no stop point).',
    '接着上次演 —— 从 {when} 起': 'Picking up where it stopped - from {when}',
    '上次是在这一天**演到一半**停的（不是收工）—— '
    '这一轮从那个时间继续，这一天的稿子接着写、前半段不会丢。':
        'The previous run stopped **halfway through this day** (not at wrap-up) - '
        'this run continues from that time, and this day\'s script keeps being '
        'written from there, so the first half is not lost.',
    '开新的一天 —— 第 {n} 天': 'Starting a new day - day {n}',
    '上一次已经把**上一天演完了**（收工落盘过）—— '
    '所以这一轮从新的一天开始。':
        'The previous run **finished the previous day** (it wrapped up and was '
        'written to disk) - so this run starts a new day.',
    '上一轮停在：{day} · {cal} · {scene}；那天已经跑了 {n} 拍。':
        'Previous run stopped at: {day} · {cal} · {scene}; that day had run {n} beats.',
    '上一轮是**收工**停的（第 {n} 天已经落盘完毕）。':
        'The previous run stopped at **wrap-up** (day {n} was fully written to disk).',
    '这一轮从': 'This run starts from',
    '查上一轮停在哪失败（这一轮按从头开始）':
        'Could not read where the previous run stopped (this run starts from the beginning)',
    '⚠ 这里的「起始点」说的是**剧情节点**（从哪一段故事开始）；'
    '上面那块说的是**第几天哪个时辰** —— 两件事。':
        'Note: "Start point" here means the **story node** (which part of the story to '
        'begin at); the panel above is about **which day and hour** - two different things.',
    # ── 自动落盘：倒计时 + 「刚落了」提示（2026-10-08）──────────────
    # 用户原话：「自动落盘没有倒计时 也没看到它干没干（如果干了应该给一个提示
    # 在自动落盘状态标签里）」。
    # [EN] ── Auto save: countdown + "just saved" hint (2026-10-08) ──────────────
    # [EN] User's exact words: "Auto save has no countdown, and I can't see whether it did anything (if it
    # [EN] did, a hint should be given
    # [EN] in the auto save status label)".
    '自动落盘 · 还有 {n} 秒（还没落过）':
        'autosave · in {n}s (nothing saved yet)',
    '自动落盘 · 还有 {n} 秒（上次 {s} 秒前）':
        'autosave · in {n}s (last saved {s}s ago)',
    '自动落盘 · ✓ 刚落盘（第 {k} 次）':
        'autosave · ✓ just saved (no. {k})',
    # ── 剧本审读（2026-10-08）────────────────────────────────────────
    # 用户原话：「你看是否有独立的Agent 而不是导演在盯着演员说的每一句话
    # 没有就做一个 **在演员真的说出来之前**，把新生成的话放到已经出现的话里
    # 过一遍，看是否通顺 … 不是就不要放出来」。
    # [EN] ── Script review (2026-10-08) ────────────────────────────────────────
    # [EN] User's exact words: "See whether there is an independent Agent instead of the director watching
    # [EN] every line the actor says;
    # [EN] if not, make one **before the actor actually says it**, putting the newly generated lines
    # [EN] together with the lines that have already appeared
    # [EN] and run through them to see whether they are fluent ... if not, don't let them out".
    '剧本审读': 'Script review',
    '启用剧本审读': 'Enable script review',
    '审读要问模型': 'Let it ask the model',
    '每几拍过模型': 'Model pass every N beats',
    '带多少条上文': 'History lines to bring',
    '判不过就拦下': 'Block what fails',
    '上屏**之前**把新生成的内容读一遍：是不是人话·像不像这个人·接不接上文·'
    '是不是一个主题。\n'
    '· 不通过就**改写**（改不动才**拦下**）—— 拦下的不进正文，'
    '只在运行文件夹的 `剧本审读.md` 与日志里留痕；\n'
    '· 它同时**记录一切上屏的东西**（动作 / 对话 / 场景切换 / 伏笔激活 / '
    '导演动作…），流水在 `审读台账.jsonl`；\n'
    '· 「每几拍过模型」调大更省，中间那几拍只剩零成本的规则层'
    '（残留的 JSON / 占位话 / 出戏词 / 标点乱敲 / 半截话）。':
        'Reads every new piece of text **before** it reaches the screen: is it '
        'human speech, does it sound like this person, does it connect to what '
        'came before, is it one theme.\n'
        '· If it fails it is **rewritten** (and **blocked** only when it cannot '
        'be fixed). Blocked lines never enter the script - they are recorded in '
        'the run folder\'s `剧本审读.md` and the log.\n'
        '· It also **records everything that reaches the window** (actions / '
        'dialogue / scene changes / foreshadow activations / director moves ...); '
        'the stream goes to `审读台账.jsonl`.\n'
        '· Raising "model pass every N beats" saves money: in between, only the '
        'free rule layer runs (leftover JSON, placeholder talk, out-of-play '
        'words, mashed punctuation, half sentences).',
    '自动落盘(秒)':
        'Autosave (s)',
    '每隔这么多秒，把**当前这一天已经演出来的**写一份中途稿到运行文件夹的 '
    '`自动落盘/进度.md`（滚动覆盖，不是一天一个文件）。\n'
    '点「暂停」时、关窗口时、收工前，**各再补一次**。\n'
    '为什么需要：正式产物只在**跨天/收工**时才写，在那之前关掉程序，'
    '当天演过的大半就白跑了。\n'
    '`0` = 关闭。运行界面中栏左下角那颗小胶囊会显示当前的间隔与'
    '「上次落盘在几秒前」。':
        'Every this many seconds, write a **work-in-progress draft** of the current '
        'day to `自动落盘/进度.md` in the run folder (overwritten in place, not one '
        'file per save).\n'
        'It also saves once more when you press Pause, when you close the window, '
        'and before the run wraps up.\n'
        'Why it is needed: the final output is only written at a day boundary or on '
        'wrap-up, so closing the program before that throws away most of the day.\n'
        '`0` = off. The small pill at the bottom-left of the middle pane shows the '
        'current interval and how many seconds ago the last save happened.',
    '自动落盘失败':
        'Autosave failed',
    '关窗口前的自动落盘失败':
        'Autosave before closing the window failed',
})

# ══════════════════════════════════════════════════════════════════
#  悬停提示（白问号）与拾卷的排序（2026-10-10）
# [EN] Hover tooltips (white question mark) and Shijuan sorting (2026-10-10)
# ══════════════════════════════════════════════════════════════════
#  用户原话：「你看下软件的 UI 上哪些地方需要 Tip 解释的 你都加上 样式是有一个
#  白色带圈小问号（很小） 鼠标放上去就解释对应目标是什么东西」。
# [EN] User's exact words: "Look at which places in the software UI need Tips to explain, and add them
# [EN] all; the style is a
# [EN] white small question mark in a circle (very small); hovering the mouse over it explains what the
# [EN] corresponding target is".
#
#  ⚠ 提示文案**必须翻译**，理由与沙盒拒绝理由一样：英文界面下悬停冒中文，
#    用户会以为程序坏了 —— 而"看不明白才去悬停"的那一刻，正是他最需要
#    看得懂的时候。
# [EN] ⚠ Tooltip text **must be translated**, for the same reason as sandbox rejection reasons: under
# [EN] an English UI, hovering pops up Chinese,
# [EN] and the user will think the program is broken —— and the moment of "I don't understand so I
# [EN] hover" is exactly when he most needs
# [EN] to be able to understand it.
_ZH2EN.update({
    # ── 运行界面顶部按钮 ──
    # [EN] ── Top buttons of the run screen ──
    '开跑下一轮推演。会先问你「这一轮从哪儿接着演」。':
        'Start the next round. It first asks where this round should pick up.',
    '停下这一轮，**进度留着** —— 再点一次（按钮会变成「继续」）就从原地接着跑。':
        'Pause this round — **the progress is kept**. Click it again (the label '
        'becomes "Resume") and it carries on from where it stopped.',
    '从这个存档接着往下跑 —— 进度、记忆、在场的人都在原位。':
        'Carry on from here — progress, memories and who is on stage all stay '
        'exactly where they were.',
    '结束这一轮推演并收工（会写运行小结、装订稿）。\n'
    '与「暂停」不同：停了就**不接着跑了**，想继续得重新起笔。':
        'End this round and wrap up (writes the run summary and the bound '
        'manuscript).\nUnlike Pause: once stopped it **will not continue** — you '
        'have to start a new round.',
    '把已经跑出来的东西装订成稿（小说 / 剧本 / 分镜表 / 报告…）。\n'
    '运行中途也能点 —— 只纳入**已落盘的完整天**。':
        'Bind what has been produced so far (novel / screenplay / storyboard / '
        'reports…).\nYou can click it mid-run — only **fully saved days** are '
        'included.',
    '回到开始界面（**不会**停掉这一轮，随时能从「回卷」回来）':
        'Go back to the start screen (**this does not** stop the round; come '
        'back any time via "Resume Story").',
    '打开使用说明；也可以直接问它问题':
        'Open the manual; you can also just ask it a question',
    '看后台到底做了什么（报错、重试、每一次模型调用）。出问题时先看它。':
        'See what the program actually did (errors, retries, every model call). '
        'Look here first when something goes wrong.',

    # ── 运行界面左栏 / 右栏的面板 ──
    # [EN] ── Panels in the left / right column of the run screen ──
    '这一轮**故事里**走到了第几天、什么时辰。\n'
    '下面那行小字是这一轮的运行状态（在跑 / 已暂停 / 未开始）。':
        'Which day and hour it is **inside the story**.\nThe small line below is '
        'the run state (running / paused / not started).',
    '这一卷当前的运行边界：运行模式、要不要夜间暂停、自动跑到第几天停。\n'
    '想改它们去「天机 · 运行」。':
        'The run boundaries of this volume: run mode, night pause, and the day '
        'limit for auto-running.\nChange them in Settings · Run.',
    '今天这一幕发生在哪儿，以及在场的人各在哪个位置。\n'
    '底图取自「设定集/小世界地图.yaml」；每次换场景重画。':
        "Where today's scene takes place and where everyone is standing.\nThe "
        'base map comes from the small-world map file in the book settings, '
        'and is redrawn on every scene change.',
    '这一轮**当前**的风格参数（当值 / 最大值）。\n'
    '它们由「书斋」里那几个滑块决定起点，推演过程中会被导演与场记按剧情微调。\n'
    '想改绝对值，去「书斋 · 风格控制」。':
        "This round's **current** style values (current / maximum).\nTheir "
        'starting point comes from the sliders in Project Settings; the director '
        'and script supervisor nudge them as the plot develops.\nTo change the '
        'absolute values, go to Project Settings · Style.',
    '此刻**这一场**里有谁（不是全书人物表）。换场景时会跟着换。':
        'Who is in **this scene** right now (not the full cast list). It changes '
        'with the scene.',
    '故事走到哪个节点了、当前张力多大、进度表上还剩几项。\n'
    '节点与进度表都来自「设定集/故事进度.yaml」。':
        'Which story node we are at, the current tension, and how many progress '
        'items are left.\nBoth come from the story-progress file in the book '
        'settings.',
    '这一班出工的人（小说作家 / 编剧 / 导演 / 场记 …）。\n'
    '谁在干活会高亮；点了名的人这一轮没派上用场就一直是灰的。':
        'The crew on duty (novelist / screenwriter / director / script '
        'supervisor …).\nWhoever is working is highlighted; anyone with nothing '
        'to do stays grey.',
    '程序自己的状态：模型档位、记忆检索方式、今天的 Token 用量，'
    '以及导演 / 合规 / 向量检索这些小开关现在是不是开着。':
        "The program's own state: model tiers, memory retrieval mode, today's "
        'token usage, and whether the director / compliance / vector-retrieval '
        'switches are currently on.',

    # ── 拾卷（存档列表）──
    # [EN] ── Shijuan (save list) ──
    '这本书跑过的每一轮。点一条看右边。':
        'Every round you have run on this book. Click one to see it on the right.',
    '排序': 'Sort',
    '按**故事里的时间**排 —— 不是按「你什么时候点的起笔」'
    '（那个是下面卡片上的「存档时间」）。\n'
    '悬停每个选项，会说明它具体拿哪个时间排。':
        'Sorted by the time **inside the story** — not by when you pressed Start '
        '(that is the "Saved at" line on the cards below).\nHover any option to '
        'see exactly which time it sorts by.',
    '开始 ↑': 'Start ↑', '开始 ↓': 'Start ↓',
    '结束 ↑': 'End ↑', '结束 ↓': 'End ↓',
    '按**故事里**的开始时间，早的在前':
        'By story **start** time, earliest first',
    '按**故事里**的开始时间，晚的在前':
        'By story **start** time, latest first',
    '按**故事里**的结束时间，早的在前':
        'By story **end** time, earliest first',
    '按**故事里**的结束时间，晚的在前 —— 推得最远的那一轮在最上面':
        'By story **end** time, latest first — the round that pushed the story '
        'furthest is on top',
    '⏳ 故事时间': '⏳ Story time',
    '故事时间': 'Story time',
    '这一轮**故事里**的时间跨度：从第几天演到第几天。'
    '不是「你什么时候点的起笔」——那个时间在下面那一行。':
        'How far the **story** got this round: from which day to which day. '
        'Not when you pressed Start — that is the line below.',
    '⏳ 故事时间：（这一轮还没有落盘的故事）':
        '⏳ Story time: (nothing saved for this round yet)',
    '故事里过了多久 —— 从第几天演到第几天，取自 `每天的生活/` 里的落盘产物。':
        'How much time passed inside the story — from which day to which day, '
        'read from the day files this run has saved.',
    '**现实世界**里这个存档是什么时候生成的（文件夹名上那串年月日）。':
        'When this save was created in the **real world** (the timestamp in the '
        'folder name).',

    # ── 天机：六个页签各一句 ──
    # [EN] ── Tianji: one line for each of the six tabs ──
    '这台程序自己的设置：项目放在哪、界面语言、日志详细程度。'
    '与某本书有关的东西不在这里 —— 那些在「书斋」里。':
        'Settings for the program itself: where projects live, the UI language, '
        'log verbosity. Anything about a particular book is in Project Settings, '
        'not here.',
    '**推演服务**用的模型：人物说话、导演写剧本、场记校对，'
    '都是在调这里配的模型。三档分别管关键场面 / 常规循环 / 压缩打分。':
        'The models used by the **simulation service**: characters speaking, the '
        'director writing script, the script supervisor checking it. The three '
        'tiers cover key scenes / the regular loop / compression and scoring.',
    '**创作服务**（MuMuAINovel）用的模型：小说作家要写整章正文时，'
    '会另起一个本地服务来写。这里的地址与 Key 配的是**那个服务**，'
    '与上面那一页不是同一个 —— 两个都要配，推演时才不会退回自写。':
        'The models used by the **writing service** (MuMuAINovel): when the '
        'novelist has to write a whole chapter it calls a separate local '
        'service. The URL and key here configure **that** service, which is not '
        'the same one as the page above — configure both, or the run falls back '
        'to in-house writing.',
    '界面长什么样：面板的透明度、中英切换。改完当场生效，不用重启。':
        'How the interface looks: panel transparency and the Chinese/English switch. '
        'Applied immediately, no restart needed.',
    '这一卷**怎么跑**：跑多快、多久算一拍、要不要定期暂停、'
    '每天最多花多少 Token、隔多久自动落盘、开卷打磨与剧本审读的上限。':
        'How this volume **runs**: how fast, how long a beat is, whether to pause '
        'periodically, the daily token budget, the autosave interval, and the '
        'limits for ingest polishing and script review.',
    '导演引擎的力度（要不要制造冲突、冲突多频繁）与内容合规的松紧。'
    '关掉导演，故事会变得更「顺」，但也没什么起伏。':
        'How hard the director engine pushes (whether to create conflict, and how '
        'often) and how strict content compliance is. Turn the director off and '
        'the story becomes smoother but flatter.',

    # ── 书斋：四个页签各一句（并点破"书斋 vs 天机"）──
    # [EN] ── Shuzhai: one line for each of the four tabs (and clarify "Shuzhai vs Tianji") ──
    '这本书的**类型与风格**，以及这一卷跑到哪、贴着原著演还是放飞。'
    '（这些是**这本书**的设置，与程序设置无关）':
        'The **genre and style of this book**, plus where this volume runs and '
        'how closely it follows the source. (These are settings for **this '
        'book**, not for the program.)',
    '这本书的风格参数起点：对话密度、段落长度、描写浓度…'
    '推演时导演与场记会在这些值上微调。':
        'Starting style values for this book: dialogue density, paragraph '
        'length, description density… The director and script supervisor adjust '
        'them during the run.',
    '这本书的导演力度：要不要制造冲突、冲突多频繁、张力曲线往哪走。':
        'Director intensity for this book: whether to create conflict, how '
        'often, and which way the tension curve should go.',
    '这本书出图的模型与尺寸（肖像、场景插画都走这里）。':
        'The image model and size for this book (used for both portraits and '
        'scene illustrations).',

    # ── 帮助面板的两个页签 ──
    # [EN] ── The two tabs of the help panel ──
    '按目录翻《使用说明》——想自己找。':
        'Browse the manual by its table of contents — for when you want to look '
        'it up yourself.',
    '直接用一句话问，答案从《使用说明》里找。'
    '答不上来时它会说不知道，而不是编。':
        'Ask in one sentence; the answer is looked up in the manual. When it '
        'cannot answer it says so instead of making something up.',
})

# ══════════════════════════════════════════════════════════════════
#  拆书：三种输入（文件 / 文件夹 / 网址）与"只拆一段"（2026-10-10）
# [EN] Book splitting: three kinds of input (file / folder / URL) and "split only a segment"
# [EN] (2026-10-10)
# ══════════════════════════════════════════════════════════════════
#  用户原话：「拆书 我希望同时支持传入文件（PDF docx md html txt等文档格式）
#  或者包含这些类型文件的文件夹 或者一个网址 里面是书籍的索引网页（软件可以去爬取）
#  另外根据我学的理论 拆书不需要全拆 最后支持拆哪些页（按照1-10,15-21这样输入，
#  或者前多少页，或者哪些章节）」。
# [EN] User's exact words: "For book splitting, I hope to support passing in files (PDF docx md html
# [EN] txt and other document formats)
# [EN] or a folder containing files of these types, or a URL whose page is the book's index page (the
# [EN] software can crawl it)
# [EN] Also, according to the theory I learned, book splitting does not need to split everything;
# [EN] finally support selecting which pages to split (input like 1-10,15-21,
# [EN] or the first N pages, or which chapters)".
#
#  ⚠ 提示文案**必须翻译**：英文界面下悬停冒中文，用户会以为程序坏了 ——
#    而"看不明白才去悬停"的那一刻，正是他最需要看得懂的时候。
# [EN] ⚠ Tooltip text **must be translated**: under an English UI, hovering pops up Chinese, the user
# [EN] will think the program is broken ——
# [EN] and the moment of "I don't understand so I hover" is exactly when he most needs to be able to
# [EN] understand it.
_ZH2EN.update({
    '网址': 'URL',
    '选择范围': 'Range',
    '书籍的章节目录页，http… 开头': 'The book\'s chapter-index page, starting with http…',
    '留空=整本；也可写 1-10,15-21 / 前3章 / 第5章-第8章':
        'Empty = whole book; you may also write 1-10,15-21 / first 3 chapters / '
        'ch.5-ch.8',
    # ⚠ 这里原来还有一条 `'书的**索引页**（章节目录那一页）地址。填了它，…'`
    #   （`mk_tip` 的悬停文案）—— 网址输入框搬进弹窗之后**代码里已无引用**，
    #   已删。留着的坏处：下一个人会以为它是当前文案（改文案时漏改）。
    # [EN] (`mk_tip`'s hover text) —— after the URL input box was moved into the dialog, **there is no
    # [EN] longer any reference in code**,
    # [EN] so it was deleted. The downside of keeping it: the next person will think it is the current text
    # [EN] (and miss updating it when changing text).
    '**只拆其中一段** —— 拆书本来就不用全拆。\n'
    '能写：`1-10,15-21`（按第几段）、`前10页`、`前3章`、`第5章-第8章`、'
    '`最后2章`、`「井底」`（按章节名里的字）。\n'
    '留空 = 整本（程序自己分层取样，开头几章必读、末尾几章也读）。':
        '**Take only one slice** — there is no need to dismantle the whole '
        'book.\nAccepted: `1-10,15-21` (by position), `first 10 pages`, '
        '`first 3 chapters`, `ch.5-ch.8`, `last 2 chapters`, `"井底"` (match '
        'chapter titles).\nEmpty = the whole book (the program samples in '
        'layers: the opening chapters are always read, and so are the last '
        'few).',
    '留空 = 整本（按分层取样读）': 'Empty = whole book (read by layered sampling)',
    '只拆：{x}': 'Dismantling only: {x}',
    # ── 「网址」改成**弹对话框**输入之后（2026-10-10 用户要求）──────────
    #  用户原话：「点击网址时候 弹出一个对话框 输入网址 而不是在下面」。
    #  ⚠ 对话内容的提示与老版**逐字不同**（老版是 `mk_tip` 的悬停提示，
    #    现在是对话框里的一段正文），所以要单独登记一条 —— 字符串差一个字
    #    `t()` 就查不到，英文界面会把整段中文原样吐出来。
    # [EN] ── After "URL" was changed to input via a **dialog popup** (user request 2026-10-10) ──────────
    # [EN] User's exact words: "When clicking URL, pop up a dialog to input the URL, instead of below".
    # [EN] ⚠ The dialog content's hint is **word-for-word different** from the old version (the old version
    # [EN] was `mk_tip`'s hover hint,
    # [EN] now it is a paragraph of body text in the dialog), so it must be registered separately —— if the
    # [EN] string differs by one character,
    # [EN] `t()` won't find it, and the English UI will spit out the whole Chinese paragraph verbatim.
    '网址：{u}': 'URL: {u}',
    '网址还没填 —— 再点一次「网址」填上':
        'No URL yet — click 「网址」 again and enter one',
    # ★ 网址弹窗那句说明（2026-10-10 下午改短过 —— 老板太长，撑出了"又高又窄"）。
    #   ⚠ 旧的整段（带「有些小说站是脚本渲染的…」那句）**已无代码引用**，已删；
    #     留着只会让下一个人以为它是当前文案（改名/改文案时漏改）。
    # [EN] ★ The explanation sentence in the URL dialog (shortened on the afternoon of 2026-10-10 —— the
    # [EN] old version was too long and pushed out a "tall and narrow" layout).
    # [EN] keeping it would only make the next person think it is the current text (and miss updating it
    # [EN] when renaming/changing text).
    '填书的**索引页**（章节目录那一页）地址 —— '
    '程序逐章去爬，只读来看写法，不会转发别人的正文。':
        "The book's **index page** (the chapter list) — the program crawls each "
        'chapter, read-only, to study the craft; it never republishes '
        "anyone's text.",
    '确定': 'OK',
    # ── 用量对话框打开失败（2026-10-10：把静默失败改成看得见）──────────
    # [EN] ── Usage dialog failed to open (2026-10-10: changed silent failure to visible) ──────────
    '打开用量对话框失败': 'Failed to open the usage dialog',
    '打开用量对话框失败：{e}': 'Failed to open the usage dialog: {e}',
    # ⚠ 旧的 `'当前来源：网址'` 随本次改动删掉（被 `'网址：{u}'` 取代 ——
    #   网址框改成弹对话框之后，界面上得把填过的地址显示出来）；
    #   `'用 samples/ 里的一本试拆'` 改名为 `'用 sample 测试'`
    #   （用户点名："这个改名叫做用sample测试"）。
    #   ★ 下面这四条**仍在用**（改名的只是 samples 那一条），别顺手删：
    # [EN] after the URL box was changed to a dialog popup, the UI has to display the address that was
    # [EN] filled in);
    # [EN] (the user called out: "rename this to 用sample测试").
    # [EN] ★ The following four are **still in use** (only the samples one was renamed), don't delete them
    # [EN] in passing:
    '还没选书 —— 在上面选一个，或者点「网址」填地址':
        'No book chosen yet — pick one above, or click 「网址」 and enter an address',
    '先选一本书：文件 / 文件夹 / samples，或者点「网址」填一个地址':
        'Pick a source first: a file / a folder / samples — or click 「网址」 '
        'and enter an address',
    '网址还空着 —— 先在上面那个框里填一个地址':
        'The URL is still empty — type an address into the box above first',
    '还没选书，先选一个': 'No book chosen yet — pick one first',
    '用 sample 测试': 'Try a sample',
    # ── 天机页新增的「启动 / 停止服务」两个按钮（2026-10-10）──────────
    #  这一页原先**只能看状态、不能启停** —— 用户关掉程序之后后台服务还在跑，
    #  他却无从处理（只能去任务管理器）。补上这两个键。
    # [EN] ── Two new buttons on the Tianji page: "Start / Stop Service" (2026-10-10) ──────────
    # [EN] This page previously **could only show status, not start/stop** — after the user closed the
    # [EN] program the background service was still running,
    # [EN] but they had no way to deal with it (only via Task Manager). These two keys were added.
    '启动服务': 'Start service',
    '停止服务': 'Stop service',
    '正在启动创作服务…（首次要下模型，可能要几分钟）':
        'Starting the writing service… (the first run downloads a model; it can '
        'take several minutes)',
    '正在停止创作服务…': 'Stopping the writing service…',
    '创作服务已启动': 'Writing service started',
    '创作服务已停止': 'Writing service stopped',
    '创作服务操作失败': 'Writing-service action failed',
    '创作服务操作失败：{e}': 'Writing-service action failed: {e}',
    '没成功：{why}': 'Failed: {why}',
    '选择范围那行看不懂，改一下再开始':
        'The range line cannot be parsed — fix it before starting',
    '支持 .txt / .md / .docx / .html / .pdf；一本被拆成多个文件的，选文件夹。':
        'Supports .txt / .md / .docx / .html / .pdf; if one book is split into '
        'many files, pick the folder.',
    'samples/ 里没有可拆的书': 'No dismantlable book found under samples/',
    # ⚠ 这里原来还有一条 `'开始：{p}': 'Start: {p}'` —— 与上面那条
    #   `'Starting: {p}'` **同 key**，而字典字面量遇到重复 key 是**静默覆盖**
    #   （后者赢），于是先写的那条纯属白写、还让人以为改过。
    #   已删（两条意思一样，留先写的那条）。`tools/i18n_check.py` 会查这一类。
    # [EN] ⚠ There used to be another entry here, `'开始：{p}': 'Start: {p}'` — with the entry above
    # [EN] `'Starting: {p}'` **same key**, and a dict literal on a duplicate key **silently overwrites**
    # [EN] (the latter wins), so the earlier one was written for nothing and made people think it had been
    # [EN] changed.
    # [EN] Deleted (both mean the same, the earlier one is kept). `tools/i18n_check.py` checks for this
    # [EN] kind.
    '① 打开网址': '(1) opening the URL',
    '① 找到章节': '(1) chapters found',
    '① 抓取': '(1) fetching',
    '② 定量画像': '(2) quantitative profile',
    '读了（{k}）：{s}': 'Read ({k}): {s}',
    # ⚠ 这条原来写成 `'文件': 'file', '文件夹': 'folder', '网址': 'URL'` ——
    #   而 `'网址'` 上面（本区块第一行）已经登记过一次，**重复 key 静默覆盖**。
    #   值恰好一样所以看不出毛病，但那是运气。已把重复的那个删掉。
    # [EN] but `'网址'` was already registered above (first line of this block), **duplicate key silently
    # [EN] overwrites**.
    # [EN] The values happened to be the same so the bug was invisible, but that was luck. The duplicate
    # [EN] has been removed.
    '文件': 'file', '文件夹': 'folder',
    '**只拆了这一部分**：{x}（源里一共 {n} {u}）':
        '**Only this part was dismantled**: {x} (the source has {n} {u} in '
        'total)',
    '只拆了「{x}」—— 不是整本：{n} {u}（源里一共 {tot} {u}）':
        'Only "{x}" was dismantled — not the whole book: {n} {u} (the source '
        'has {tot} {u} in total)',
    # ── 用量报表：**栏头（表头）筛选**（2026-10-11）────────────────────────
    #   用户原话：「最上面那几个筛选功能……中间第二个第三个列都有自己的一套筛选，
    #   且用合适的**上下文菜单**的方式放到**每个列的表头上**，而不是单独放一个地方。」
    #   ⚠ 下面★那两组是**动态取值**（`t(_AGENT_FILTER_LABEL[k])` / `t(name)`），
    #     `tools/i18n_check.py` 只扫字面量 `t('…')`，**扫不到它们** ⇒ 必须手工登记。
    #     （漏了不会崩，只是英文界面下露中文 —— 正因为"不崩"，最容易漏。
    #       改那两张表的文案时，记得回这儿补。）
    # [EN] ── Usage report: **header (table header) filters** (2026-10-11) ────────────────────────
    # [EN] User's exact words: "The filters at the very top ... the second and third columns in the middle
    # [EN] each have their own set of filters,
    # [EN] and put them on **each column's header** using an appropriate **context menu**, instead of a
    # [EN] single separate location."
    # [EN] ⚠ The two ★ groups below are **dynamic values** (`t(_AGENT_FILTER_LABEL[k])` / `t(name)`),
    # [EN] `tools/i18n_check.py` only scans literals `t('…')`, **it cannot see them** ⇒ they must be
    # [EN] registered by hand.
    # [EN] (Missing them won't crash, it just leaks Chinese in the English UI — precisely because it "won't
    # [EN] crash", they're the easiest to miss.
    # [EN] When changing the wording of those two tables, remember to come back here and add them.)
    '范围': 'Scope',
    '明细': 'Details',
    '软件整体 + 各项目': 'Whole software + each project',
    '按它把这一栏分组': 'This column is grouped by it',
    '这一栏按什么分组': 'What to group this column by',
    '时间：{v}': 'Time: {v}',
    '筛选：{v}': 'Filter: {v}',
    '时间范围（作用于四栏）：{v}': 'Time range (applies to all four columns): {v}',
    '筛选这一栏的 Agent：{v}': 'Filter the Agents in this column: {v}',
    # ★ 动态取值 ·「时间范围」菜单的四项（`gui/usage_dialog.SINCE_PRESETS`）
    # [EN] ★ Dynamic value · the four entries of the "Time Range" menu (`gui/usage_dialog.SINCE_PRESETS`)
    '全部时间': 'All time',
    '今天': 'Today',
    '最近 7 天': 'Last 7 days',
    '最近 30 天': 'Last 30 days',
    # ★ 动态取值 ·「Agent 筛选」菜单的四项（`gui/usage_dialog._AGENT_FILTER_LABEL`）
    # [EN] ★ Dynamic value · the four entries of the "Agent Filter" menu
    # [EN] (`gui/usage_dialog._AGENT_FILTER_LABEL`)
    '全部 Agent': 'All agents',
    '只看剧组 Agent': 'Crew agents only',
    '只看未标用途': 'Unlabeled purposes only',
    '只看花费较大的': 'Only the costlier ones',
    # 顺手补的两条（**既有缺译**，不是本轮功能）：续跑时中栏那行「上一回演到…」
    # ——`i18n_check --all` 报出来的，`sim/resume.py` 在用。
    # [EN] Two entries fixed in passing (**pre-existing missing translations**, not part of this round's
    # [EN] feature): the middle column line "last time it played up to..." during resume
    '上一回演到 {where}。': 'Last time it played to {where}.',
    '上一回演到 {where}，说到：': 'Last time it played to {where}, and said:',
    # ── 「起笔」对话框：前情提要 + 作者对本轮走向的建议（2026-10-11）──────
    #   用户原话：「我希望在起笔的时候，可以有一个地方加上用户自己对于故事
    #   接下来走向的建议。我觉得可以在提笔的前情提要的下面……而且请确保
    #   这里的前情提要和后续运行窗口对话显示的时候给的前情提要一样。」
    #   ⚠ 「前情提要」**上面已经登记过**（`'前情提要': 'Recap'`）——
    #     第一版在这里又写了一遍，`i18n_check` 的"重复 key"当场报出来。
    #     重复 key 是**静默覆盖**，值恰好一样所以看不出毛病 —— 那是运气。
    # [EN] ── "Start Writing" dialog: recap + author's suggestion for this round's direction (2026-10-11)
    # [EN] ──────
    # [EN] User's exact words: "I hope that when starting to write, there can be a place to add the user's
    # [EN] own suggestions for
    # [EN] where the story goes next. I think it can go below the recap when starting to write ... and
    # [EN] please make sure
    # [EN] the recap here is the same as the recap shown later in the running window's dialogue."
    # [EN] the first version wrote it again here, and `i18n_check`'s "duplicate key" flagged it
    # [EN] immediately.
    # [EN] Duplicate keys are **silent overwrites**, and the values happened to be the same so the bug was
    # [EN] invisible — that was luck.
    '（还没有可念的前情 —— 这本书没跑过，设定集里也没写【剧情参考线】/【世界观】）':
        '(No recap to tell yet — this book has not been run, and the setting '
        'has neither [Story arc] nor [Worldview])',
    '这一轮开头，**中栏屏幕上念的就是这一段**（与运行窗口同一份，不是另算的）。':
        'At the start of this round, **this very passage is what appears in the '
        'middle column** (the same one the run window uses — not a separate copy).',
    '您对接下来剧情发展的建议': 'Your suggestions for where the story goes next',
    '（可不填）比如：这三天先埋一个误会，别急着解释；下一场再让它炸开。':
        '(Optional) e.g. Plant a misunderstanding over the next three days and do '
        'not explain it yet; let it blow up in the following scene.',
    '写在这里的话会交给剧组每一个人（导演、剧作者、小说作家…）——它是**往哪个方向使劲**的建议，'
    '不是设定、也不会写进你的稿子。**只对这一轮有效**：跑完或停止后重新起笔，这里要重新填。':
        'What you write here goes to everyone in the crew (director, screenwriter, '
        'novelist…) — it is a suggestion about **which way to push**, not a setting, '
        'and it never gets written into your manuscript. **It applies only to this '
        'round**: after the round ends or stops, you fill it in again.',
    # ★ 这两条是**动态取值**（`sim/directive`）：`line()` 拼开场卡片那一行，
    #   `block()` 是给模型的段落（那句不用翻，提示词本来就是中文写的）。
    # [EN] ★ These two are **dynamic values** (`sim/directive`): `line()` assembles the opening card line,
    # [EN] `block()` is the paragraph for the model (that one doesn't need translation, the prompt is
    # [EN] written in Chinese anyway).
    '作者对本轮走向的要求': "Author's direction for this round",
    '{head}：{text}': '{head}: {text}',
    '作者走向建议': 'Author direction',
    # ── 演员的两层设置（2026-10-11，用户："演员Agent在系统层面没有具体角色、
    #   项目层面有具体角色，在系统全局设置（天机）里怎么设置、在项目级别怎么设置"）──
    #   分四层：①本文件职位 ②「演员类型库」 ③项目同名 md ④项目的**每个角色**。
    #   ⚠ ④（角色）**绝不能写进任何 md** —— 那些是全组通读的，写进去就串台。
    # [EN] ── The actor's two-level settings (2026-10-11, user: "the actor Agent has no specific role at
    # [EN] the system level,
    # [EN] but has a specific role at the project level; how to set it in the system global settings
    # [EN] (Tianji), and how to set it at the project level") ──
    # [EN] Four levels: ① this file's roles ② "Actor Type Library" ③ project's same-named md ④ the
    # [EN] project's **each role**.
    # [EN] ⚠ ④ (roles) **must never be written into any md** —— those are read by the whole group, writing
    # [EN] it in causes cross-talk.
    '"年龄层·气质"的写法与本库一致':
        '"age · temperament" style, same as the rest of this library',
    '⚠ **具体角色不要写在这里**：这里每一份是**全组通读**的，写进来每个角色都会读到别人的设定。演员的**具体角色**在「项目 · 剧组 Agents」→「角色设置」里（一人一份）。':
        '⚠ **Do not write individual characters here**: every file here is read'
        'by the **whole crew**, so whatever you write becomes visible to every'
        'character. The actors\' **individual characters** live in "Project · Crew'
        'Agents" → "Character setup" (one per person).',
    '⚠ 它**不管演谁**。谁演谁在「项目 · 剧组 Agents」→「角色设置」里 （一人一份），参考：{p}':
        '⚠ It does **not** decide who is played. See "Project · Crew Agents" →'
        '"Character setup" for that (one per person). File: {p}',
    '⚠ 清空某一项 = 删掉那一行（不留空壳）。改的是**这本书**的人物表，写前自动备份一份 `.bak`。':
        '⚠ Clearing a field deletes that line (no empty shell left). This edits'
        "**this book's** cast list; a `.bak` is written before every save.",
    '⚠ 演员那一行 md 里**不要**写具体角色 —— 那份是全组通读的。改完**下一轮**起生效（这一轮的设定集已冻结）。':
        '⚠ Do **not** put individual characters in the actor `.md` — it is read'
        'by the whole crew. Changes take effect from **the next round** (this'
        "round's setting is already frozen).",
    '⚠ 演员那一行右边还有一个**「角色设置」**（👥）：那里定**每个具体角色**演成什么样（一人一份）；这一份 md 只管**演员这个工种**（全组通读，别写具体角色）。':
        '⚠ The actor row also has a **"Character setup"** button (👥) that decides'
        'how **each character** is played (one per person). This `.md` only'
        'covers **the actor as a craft** (read by the whole crew — no individual'
        'characters).',
    '一行一条。**至少三条** —— 同一个类型要能长出好几种人，只有一种演法就是套路':
        'One per line. **At least three** — one type must be able to grow several'
        'different people; a type with a single way of playing is a cliché',
    '上层是「演员类型库」（这一类演员**怎么说话**）；两者冲突时**以这里的角色为准**（类型只管怎么说，角色管演谁）。':
        'Above it sits the Actor type library (how this kind of actor'
        '**speaks**). When the two disagree, **the character here wins** — the'
        'type only governs how they talk, the character governs who they are.',
    '与哪一型天然对冲（可空）':
        'Which type it naturally clashes with (optional)',
    '主角位 / 对手位…（可以空着）':
        'Lead / antagonist parts… (can be left empty)',
    '变奏 {n} 条（同型多人的分流轴）':
        '{n} variations (how several actors of one type are told apart)',
    '变奏轴（同型多人靠它分流）':
        'Variations (what separates several actors of the same type)',
    '句子长短':
        'Sentence length',
    '只写一点：这个人**不像**他那一型的哪一处':
        'Just one point: in what way this person is **not** like their type',
    '如：不解释动机、不说长段':
        'e.g. never explains motives, never speaks at length',
    '如：动作少而准；不主动靠近别人':
        'e.g. few but precise movements; does not step toward others',
    '如：嗯。，不用。，随你。':
        'e.g. Mhm., No need., Suit yourself.',
    '如：慢，中间有停顿':
        'e.g. slow, with pauses in between',
    '如：短，通常一句说完':
        'e.g. short — usually one sentence',
    '已保存「{n}」的演法（**下一轮**起生效）':
        'Saved how "{n}" is played (takes effect from **the next round**)',
    '常演':
        'Usually cast as',
    '张力':
        'Friction',
    '忌讳（别写成什么）':
        'Avoid (what not to write it as)',
    '惯用语（逗号分隔）':
        'Catchphrases (comma-separated)',
    '打破类型':
        'Break the type',
    '改的是**这一类演员怎么演**（系统层，所有书共用）。它是方法、不是某一个角色 —— 具体角色在「角色设置」里。':
        'This edits **how this kind of actor performs** (system level, shared by'
        'every book). It is a method, not a character — individual characters'
        'live in "Character setup".',
    '改这一型':
        'Edit this type',
    '改这个角色怎么演':
        'Edit how this character is played',
    '新建一型演员':
        'New actor type',
    '没能保存：{w}':
        'Could not save: {w}',
    '演员类型':
        'Actor type',
    '演员类型库':
        'Actor type library',
    '演员类型库 · {n} 型':
        'Actor type library · {n} types',
    '演员类型：{a}{v}':
        'Actor type: {a}{v}',
    # ★★ 2026-10-13：「演员按出场人物每人一行」之后新出现的三条（见
    #   `gui/app_flet.py` 的 `_expand_actor_rows` / `_agent_row`）。
    # [EN] ★★ 2026-10-13: three new strings after "one actor row per character" (see
    # [EN] `_expand_actor_rows` / `_agent_row` in `gui/app_flet.py`).
    '演员·{n}':
        'Actor · {n}',
    '点开：改「{n}」这个角色怎么演（一人一份）':
        'Click to change how "{n}" performs (one per person)',
    '读人物表失败：{e}':
        'Failed to read the character roster: {e}',
    '类型名不能为空':
        'The type name cannot be empty',
    '类型名（如 青年·高冷）':
        'Type name (e.g. Young · Aloof)',
    '编辑：{n}':
        'Edit: {n}',
    '角色设置 · {n}':
        'Character setup · {n}',
    '角色设置 —— 这本书里**每个角色**演成什么样（一人一份）':
        'Character setup — how **each character** in this book is played (one per'
        'person)',
    '角色：**{n}**\u3000（人本身在那本书的 `设定集/{f}` 里；这里只定"演成什么样"）':
        "Character: **{n}** (the person themselves lives in that book's"
        '`设定集/{f}`; this only decides how they are played)',
    '语速':
        'Speech rate',
    '说话忌讳':
        'Speech taboos',
    '身体 / 习惯':
        'Body / habits',
    '这一份怎么演（可选，但很值）':
        'How this one is played (optional, but worth it)',
    '这一份怎么演（这一本书里他的处境/跟谁顶/说话要注意什么）':
        'How this one is played (their situation in this book / who they clash'
        'with / what to mind when speaking)',
    '这一份的变奏':
        "This one's variation",
    '这一类人**是什么样**（两三句，说清"为什么这样"）':
        'What this kind of person is **like** (two or three sentences — say'
        '**why** they are that way)',
    '这是**系统层**：这一库里每一"型"是一种演员**怎么说话** —— 句长、语速、身体习惯、待人接物的底色。换一本书它也一样。':
        'This is the **system level**: each type here is one kind of actor and'
        '**how they speak** — sentence length, pace, bodily habits, the tone they'
        'meet the world with. It stays the same across books.',
    '这里是**这一本书**：每个角色**演成什么样** —— 一人一份。':
        'This is **this one book**: how **each character** is played — one per'
        'person.',
    '（没有身份/性格）':
        '(no identity / personality)',
    '（类型库读不到 —— 见日志）':
        '(type library unreadable — see the log)',
    '（自动配 —— 按性格/身份从类型库里挑）':
        '(auto — picked from the type library by personality / identity)',
    '（自动配）':
        '(auto)',
    '（自动：同型多人按顺序分不同的那条）':
        '(auto: several of one type take their variations in order)',
    '（这本书还没有人物表 —— 先完成「开卷」摄取）':
        '(this book has no cast list yet — finish the "ingest" step first)',
    '（选一个类型才会出现变奏；"自动配"由程序按顺序分）':
        '(variations appear once a type is chosen; "auto" lets the program assign'
        'them in order)',
    '＋ 新建一型':
        '+ New type',
    # ── 起笔 ·「本轮推演」那一节（2026-10-11，用户点名要控制的几件事）──
    #   ⚠ 六件都是**程序行为**，不是提示词里的一句话。那个「建议」输入框管不了。
    # [EN] ── Start Writing · the "this round's inference" section (2026-10-11, several things the user
    # [EN] explicitly wanted controlled) ──
    # [EN] ⚠ All six are **program behavior**, not a sentence in the prompt. That "suggestion" input box
    # [EN] cannot control them.
    '本轮推演':
        'This round',
    '这一轮的性质':
        'Nature of this round',
    '正常（照常推主线、导演照常挑事）':
        'Normal (push the mainline; the director stirs things up as usual)',
    '日常生活型（不带关键剧情，只过日子）':
        'Slice of life (no key plot; just living the days)',
    '最多几件关键事':
        'At most how many key events',
    '0 = 不限':
        '0 = unlimited',
    '每天大概写多少字':
        'Roughly how many words per day',
    '本轮出场人物':
        'Cast this round',
    '逗号分隔；空 = 全体':
        'Comma-separated; empty = everyone',
    '锁定在一个地点':
        'Lock to one place',
    '不锁（正常换场）':
        'Not locked (scenes change as usual)',
    '没事就把时间跳过去':
        'Skip time when nothing happens',
    '连着几拍没事才跳':
        'Idle beats before skipping',
    '默认 6 拍':
        'default 6 beats',
    '每次跳多少故事分钟':
        'Story minutes per skip',
    '默认 30 分钟':
        'default 30 minutes',
    '上面那个「建议」是**一句话的方向**（给剧组看的）；这一节是**真的开关** —— 管事件与时间怎么走。':
        'The "suggestions" box above is a **one-line direction** (for the'
        'crew); this section holds **real switches** — how events and time'
        'behave.',
    '「日常生活型」= 导演**不主动挑事**（一次模型都不调在挑事上），只让日子自己过；剧情真走到节点该满足时**照样推进**。':
        '"Slice of life" means the director **never stirs things up on its'
        'own** (not a single model call for it) — the days just pass. If the'
        'story genuinely reaches a node, it **still advances**.',
    '「最多几件关键事」= 这一轮导演最多挑几件事（挑够就停手，剩下的靠人物自己走）。':
        '"At most how many key events" caps how many times the director stirs'
        'things up this round; once it hits the cap it stops and the characters'
        'carry on by themselves.',
    '「没事就把时间跳过去」= 连着几拍谁都没做事时，直接用一句旁白带过一段时间，不再一拍拍空转（省 token）。有人说话做事就重新数 —— 该演的戏一秒都不会被跳掉。':
        '"Skip time when nothing happens": after several beats in a row with'
        'nobody doing anything, one line of narration carries the clock forward'
        'instead of idling beat by beat (saves tokens). One word or action'
        'resets the count — no scene that should play will ever be skipped.',
    '「本轮出场人物」= 只让这几个人上场（逗号分隔，名字要跟人物卡里一致；空 = 全体）。⚠ 这几项**会记住** —— 下次起笔还在这儿，看得见、随时能改。':
        '"Cast this round" restricts the stage to these people (comma-'
        'separated; names must match the character cards; empty = everyone). ⚠'
        'These settings are **remembered** — they will still be here next time'
        'you pen to paper, visible and editable.',
    '（可不填）比如：这三天先埋个误会，先别解释。\n⚠ 这里只定**方向**；"发生几件事/时间跳不跳"用下面「本轮推演」的开关。':
        '(Optional) e.g. Plant a misunderstanding over the next three days and'
        'do not explain it yet. ⚠ This box only sets the **direction**; for'
        '"how many events happen / whether time skips", use the switches in the'
        '"This round" section below.',
    # ── 「没事跳过时间」那句旁白 + 状态条上的字数（2026-10-11）──
    #   ⚠ 后半截是**动态取值**（`display/story_render` 从表里取出来再 t()），
    #     `i18n_check` 扫不到字面量 —— 必须手工登记（英文界面下中栏不该冒中文）。
    # [EN] ── The "skip time when nothing happens" narration + the word count on the status bar
    # [EN] (2026-10-11) ──
    # [EN] ⚠ The second half is a **dynamic value** (`display/story_render` fetches it from the table and
    # [EN] then t()),
    # [EN] `i18n_check` cannot scan literals —— must be registered by hand (the middle column shouldn't
    # [EN] leak Chinese in the English UI).
    ' · 今日 {n} 字 / 目标 {t} 字':
        ' · {n} words today / target {t}',
    ' · 今日跳过 {n} 次':
        ' · {n} time skips today',
    '{n} 分钟':
        '{n} minutes',
    '{dur}就这么过去 —— {place}里没什么事：{amb}。':
        '{dur} passed just like that — nothing was going on at {place}: {amb}.',
    '{dur}就这么过去 —— 没什么事：{amb}。':
        '{dur} passed just like that — nothing was going on: {amb}.',
    # ★ 2026-10-26：站末补时间那句（与"空闲跳过"**有意分开**，见 `time_pass_line` 的说明）。
    # [EN] ★ 2026-10-26: the end-of-station top-up line (deliberately separate from the idle skip;
    # [EN] see `time_pass_line`).
    '这一段到这儿为止 —— 此后{dur}，{place}照旧：{amb}。':
        'this stretch ends here — for the next {dur} things at {place} went on as before: {amb}.',
    '这一段到这儿为止 —— 此后{dur}，屋里屋外照旧：{amb}。':
        'this stretch ends here — for the next {dur} things went on as before: {amb}.',
    '一盏茶的工夫':
        'the time for a cup of tea',
    '小半个时辰':
        'a short while',
    '一两个时辰':
        'a couple of hours',
    '大半日':
        'most of a day',
    # ★ 2026-10-26：站末补时间（跳几天到几个月）用到的档 —— 缺了英文界面会冒中文。
    # [EN] ★ 2026-10-26: tiers used by the end-of-station jump (days to months); without English
    # [EN] the English UI shows Chinese.
    '几日':
        'a few days',
    '十来天':
        'ten days or so',
    '一个来月':
        'a month or so',
    '几个月':
        'several months',
    '院里的树换了一茬叶子，墙根生了新的青苔':
        'the courtyard tree had shed a round of leaves and moss grown at the wall base',
    '檐下的旧燕巢空了又满，来往的人换过几张脸':
        'the old swallow nest under the eaves emptied and refilled, and the faces'
        'coming and going had changed',
    '门前的石板被踩得更亮了些，去年挂的灯早收了':
        'the flagstones before the door were worn brighter, and last year\'s lanterns'
        'were long taken down',
    '雨脚一阵密一阵疏，檐水没断过':
        'the rain came in fits and starts, never letting up',
    '雪无声地落，院里的脚印很快填平了':
        'snow fell soundlessly and soon smoothed over the footprints',
    '灯芯剪过一回，窗外静得听得见风声':
        'the lamp wick was trimmed once; outside it was still enough to hear'
        'the wind',
    '天色一寸寸暗下来，街上的声气也淡了':
        'the light ebbed away inch by inch and the street sounds faded with it',
    '檐水一滴一滴，晨光从门槛上移过去':
        'eaveswater dripped one drop at a time as the morning light crept past'
        'the sill',
    '茶凉了又续上，院子里始终没有别的声息':
        'the tea went cold and was poured again; no other sound came from the'
        'yard',
    '案上的账页翻过去几页，谁也没开口':
        'a few ledger pages were turned; nobody said a word',
    '光在墙上慢慢挪，屋里的东西都还在原处':
        'the light crawled along the wall; everything indoors stayed where it'
        'was',
})



# ══════════════════════════════════════════════════════════════════════
#  界面字体 / 界面字号 / 命令行开关（2026-10-11）
# [EN] UI font / UI font size / command-bar switch (2026-10-11)
# ══════════════════════════════════════════════════════════════════════
#
#  ⚠⚠ **字体名这一组是"动态取值"，`i18n_check` 扫不到，必须手工登记**：
#    `font_choices()` 里是 `t('随附{name}', name=t(zh))` —— 那个 `zh`
#    来自 `BUNDLED_FONTS` / `SYSTEM_FONTS` 两张数据表，源码里没有
#    `t('思源宋体')` 这样的字面量。漏登记的后果是"英文界面下冒出中文选项"。
# [EN] ⚠⚠ **The font-name group here is "dynamic values"; `i18n_check` cannot see them, so they must
# [EN] be registered by hand**: `font_choices()` writes `t('随附{name}', name=t(zh))` -- that `zh`
# [EN] comes from the `BUNDLED_FONTS` / `SYSTEM_FONTS` data tables, and there is no literal like
# [EN] `t('思源宋体')` in the source. Missing entries mean "Chinese options pop up in the English UI".
_ZH2EN.update({
    '界面字体': 'UI font',
    '界面字号': 'UI font size',
    '缩放': 'Scale',
    '随附宋体（推荐）': 'Bundled Noto Serif SC (recommended)',
    '随附{name}': 'Bundled {name}',
    '跟随系统': 'Follow the system',
    '系统 · {name}': 'System · {name}',
    '{v}（当前值，本机可能没装）': '{v} (current value; may not be installed here)',
    # ── 动态取值：字体名（见上面的说明）──
    # [EN] ── Dynamic values: font names (see the note above) ──
    '思源宋体': 'Noto Serif SC',
    '思源黑体': 'Noto Sans SC',
    '霞鹜文楷': 'LXGW WenKai',
    '微软雅黑': 'Microsoft YaHei',
    '宋体': 'SimSun',
    '黑体': 'SimHei',
    '楷体': 'KaiTi',
    '等线': 'DengXian',
    '苹方': 'PingFang SC',
    '宋体-简': 'Songti SC',
    '思源黑体 CJK': 'Noto Sans CJK SC',
    # ── 说明文字 ──
    # [EN] ── Explanatory text ──
    '默认「随附宋体」（思源宋体）：字形按国标，'
    '不会出现「门」写成日文斜撇那种情况':
        'Default is "Bundled Noto Serif SC": glyphs follow the national standard, so 「门」 will not be '
        'drawn with a Japanese-style slanted flick',
    '带「随附」的都能随程序分发；带「系统」的只在本机装了的时候才列出来，'
    '换到别的机器上会回落到系统默认':
        'Anything marked "Bundled" ships with the program; anything marked "System" is listed only '
        'when installed locally, and falls back to the system default on another machine',
    '100% = 标准。标题、正文、提示、按钮与控件高度**一起**缩放':
        '100% = standard. Headings, body text, hints, buttons and control heights all scale '
        '**together**',
    '范围 80%~150%；调到很大时对话框内容可能需要滚动查看':
        'Range 80%–150%; at the largest settings a dialog may need scrolling',
    # ── 命令行开关 ──
    # [EN] ── Command-bar switch ──
    '运行窗口底部的命令行': 'Command bar at the bottom of the run window',
    '关闭命令行（不显示命令输入框与按钮）':
        'Hide the command bar (no command box or Send button)',
    '打开 = 不显示运行窗口最下方那条命令输入框与「发送」按钮（默认）':
        'On = the command box and "Send" button at the very bottom of the run window are hidden '
        '(default)',
    '关掉不减能力：命令照旧可用，「❓ 帮助」与 F11 都还在。'
    '这一栏只有 /help /status /settings 三条，平时用不上':
        'Turning it off costs no capability: commands still work, and "❓ Help" and F11 are still '
        'there. That bar only has three commands (/help /status /settings) and is rarely needed',
    '✅ 界面字体已生效': '✅ UI font applied',
    '✅ 界面字号已生效': '✅ UI font size applied',
    '✅ 界面字体与字号已生效': '✅ UI font and size applied',
    '✅ 命令行已关闭（运行窗口底部不再显示）':
        '✅ Command bar hidden (no longer shown at the bottom of the run window)',
    '✅ 命令行已打开（运行窗口底部会显示）':
        '✅ Command bar shown (it will appear at the bottom of the run window)',
})


# ══════════════════════════════════════════════════════════════════════
#  叙事窗口：翻页条（2026-10-11）
# [EN] Narrative window: the pager bar (2026-10-11)
# ══════════════════════════════════════════════════════════════════════
#
#  ⚠ 这一组是**真机判据抓到的**：`verify_ui_english` 在英文界面下量到
#    「最早一页 / 更早一页 / 第 1 / 1 页 · 共 0 条 · 已是最新」五处中文 ——
#    翻页条的四个 tooltip 与那一行文案当时是硬编码的。
# [EN] ⚠ This group was **caught by the on-device criterion**: `verify_ui_english` measured five
# [EN] Chinese strings on the English UI ("最早一页 / 更早一页 / 第 1 / 1 页 · 共 0 条 · 已是最新") --
# [EN] the pager's four tooltips and that one label line were hardcoded at the time.
_ZH2EN.update({
    '最早一页': 'Earliest page',
    '更早一页': 'Earlier page',
    '更晚一页': 'Later page',
    '回到最新': 'Back to newest',
    '第 {a} / {b} 页 · 共 {c} 条': 'Page {a} of {b} · {c} entries',
    ' · 有 {n} 条新内容': ' · {n} new',
    ' · 已是最新': ' · up to date',
})


# ══════════════════════════════════════════════════════════════════════
#  运行页面板 → 设置页（2026-10-11）
# [EN] Run-page panels → settings pages (2026-10-11)
# ══════════════════════════════════════════════════════════════════════
#
#  这一组是「点标题跳转」那一套的文案：标题上的悬停说明、跳转的留痕、
#  以及三块面板 tip 里新加的那几行（把"点标题能去哪"直接写在面板上）。
# [EN] This group is the wording for the "click the title to jump" feature: the hover text on the title, the
# [EN] trace for the jump, and the new lines added to the three panel tips (spelling out on the panel itself
# [EN] where clicking the title can go).
_ZH2EN.update({
    # ── 标题上的悬停说明（说清"会去哪一页"）──
    # [EN] ── Hover text on the title (states which page it goes to) ──
    '点这里去改这些值': 'Click here to change these values',
    '点标题去改这些值（在跑：书斋 · 运行 / 没跑：天问 · 运行）':
        'Click the title to change these values (running: Study · Run / not running: Tianji · Run)',
    '点标题去改这些值（在跑：书斋 · 风格控制 / 没跑：天问 · 导演与合规）':
        'Click the title to change these values (running: Study · Style Control / not running: Tianji · '
        'Director & Compliance)',
    '点标题去「剧组 Agents」列表（在跑：书斋 / 没跑：天问）':
        'Click the title for the cast Agents list (running: Study / not running: Tianji)',
    '点这一行去改「{name}」的设置': 'Click this row to edit the settings for "{name}"',
    # ── 时间面板的时辰说明（2026-10-24）──
    # [EN] The time panel's shichen tooltip (2026-10-24)
    '现代时间：{now}': 'Modern time: {now}',
    '{name} = {rng}（一个时辰两小时）': '{name} = {rng} (two hours per shichen)',
    '{a}:00 – 次日 {b}:00': '{a}:00 - {b}:00 next day',
    '\n（子时跨午夜，前后各一小时）':
        '\n(zhi hour straddles midnight: one hour on each side)',
    '（这一行没有内容）': '(this row has nothing yet)',
    # ── 「AI 往来」对话框（2026-10-24，聊天流形态）──
    # [EN] The "LLM exchange" dialog (2026-10-24, chat-stream shape)
    'AI 往来（点状态条打开）': 'LLM exchange (opened from the status pill)',
    '点一下 展开 / 收起': 'Click to expand / collapse',
    '还没有发过请求': 'Nothing sent yet',
    '开拍之后，这里会像聊天窗口一样，一条我发的一条它回的，往上一发一发排列。':
        'Once filming starts this works like a chat window: one message from me, one from it, '
        'stacked upwards one exchange at a time.',
    '（正在等回复…）': '(waiting for the reply...)',
    '（这一发没有正文 —— 可能是空回复，见日志）':
        '(this exchange has no body -- possibly an empty reply, see the logs)',
    '（这条请求没有消息体）': '(this request has no message body)',
    '〔系统提示〕': '[system prompt]',
    '〔用户〕': '[user]',
    '〔助手〕': '[assistant]',
    '发给模型 · {p} · {m} · {w}': 'sent to model · {p} · {m} · {w}',
    '模型返回 · {s} 秒 · {a}+{b} token': 'model returned · {s}s · {a}+{b} token',
    '模型返回 · 正在接收…（已 {n} 字）': 'model returned · receiving... ({n} chars so far)',
    '点一下看**这一发**发给模型的全部内容，以及它返回的全部内容':
        'Click to see **everything** sent to the model in this exchange, and everything it returned',
    '打开 AI 往来': 'Open LLM exchange',
    # ── 整理稿的段进度与停止说明（2026-10-24）──
    # [EN] The organizer's chunk progress and stop notice (2026-10-24)
    '整理第 {i}/{n} 段': 'Organizing chunk {i}/{n}',
    '还没开始整理就点了停止（这一段稿子要重跑一轮才有）':
        'Stop was clicked before organizing began (this chapter needs another round)',
    '（这一章在整理到第 {i}/{n} 段时，作者点了停止 —— '
    '上面是已经写好的部分，后面几段没有整理。）':
        '(The author clicked stop while organizing chunk {i}/{n} -- above is what was written; '
        'the remaining chunks were not organized.)',
    # ── 跳转留痕（写进界面日志，不出现在屏幕上）──
    # [EN] ── Jump trace (written to the UI log, never shown on screen) ──
    '跳转到运行配置': 'Jump to run config',
    '跳转到风格控制': 'Jump to style control',
    '跳转到剧组 Agents': 'Jump to cast Agents',
    # ── 失败与告警 ──
    # [EN] ── Failures and warnings ──
    '打开设置页失败：{e}': 'Failed to open the settings page: {e}',
    '重建运行界面失败': 'Failed to rebuild the run screen',
    '写入配置失败：{e}': 'Failed to write the config: {e}',
    '⚠ 全局配置未能落盘': '⚠ The global config could not be written to disk',
    # ── 三块面板的 tip（新增了"点标题去哪"那几行）──
    # [EN] ── The three panels' tips (they gained the "where clicking the title goes" lines) ──
    '这一卷当前的运行边界：运行模式、要不要夜间暂停、自动跑到第几天停。\n'
    '★ **点标题**直接去改这些值（右下角的 `↗` 就是那个意思）：\n'
    '推演正在跑 → 去「书斋 · 运行」（这本书的节奏，覆盖全局）；\n'
    '还没起笔 → 去「天问 · 运行」里的时间与预算。\n'
    '改完**立刻生效**，回到这一页数值就是新的。':
        'This volume\'s current run boundaries: run mode, whether to pause at night, and which day auto-run '
        'stops on.\n'
        '★ **Click the title** to change these values directly (that is what the `↗` on the right means):\n'
        'deduction running -> the **run boundaries** under "Study · Type & Style";\n'
        'before starting -> the time and budget under "Tianji · Run".\n'
        'Changes take effect **immediately**; coming back to this page shows the new numbers.',
    '这一轮**当前**的风格参数（当值 / 最大值）。\n'
    '它们由「书斋」里那几个滑块决定起点，推演过程中会被导演与场记按剧情微调。\n'
    '★ **点标题**直接去改绝对值（右下角的 `↗` 就是那个意思）：\n'
    '推演正在跑 → 去「书斋 · 风格控制」；还没起笔 → 去「天问 · 导演与合规」。':
        'This round\'s **current** style parameters (current / maximum).\n'
        'Their starting point comes from those sliders in the Study, and during the deduction the director '
        'and script supervisor fine-tune them to fit the plot.\n'
        '★ **Click the title** to change the absolute values directly (that is what the `↗` on the right '
        'means):\n'
        'deduction running -> "Study · Style Control"; before starting -> "Tianji · Director & Compliance".',
    '这一班出工的人（小说作家 / 编剧 / 导演 / 场记 …）。\n'
    '谁在干活会高亮；点了名的人这一轮没派上用场就一直是灰的。\n'
    '★ **点标题**去「剧组 Agents」列表；**点某一行**直接打开那个职位的设置（名字 / 作用 / 系统提示词）。':
        'The crew on shift (novelist / screenwriter / director / script supervisor ...).\n'
        'Whoever is working is highlighted; a named member who got no use this round stays grey.\n'
        '★ **Click the title** for the cast Agents list; **click a row** to open that position\'s settings '
        'right away (name / duty / system prompt).',
})


# ══════════════════════════════════════════════════════════════════════
#  多模型 + Agent 模型选项（2026-10-12）
# [EN] Multiple models + per-Agent model option (2026-10-12)
# ══════════════════════════════════════════════════════════════════════
# ⚠ 这一块里有**一半是动态取值**（职位名/职责、能力档名与说明、逐位推荐理由）——
#   它们是从数据表里取出来再交给 `t()` 的，`tools/i18n_check.py` **扫不到**，
#   必须像现在这样手工登记。改 `crew/roster.py` / `llm/recommend.py` 的文案时，
#   这里要**一起改**，否则英文界面会冒中文（`tools/verify_ui_english.py` 会报）。
# [EN] ⚠ Half of this block is **dynamic values** (position names/duties, ability profile names
# [EN] and explanations, per-Agent reasons) -- they are taken from data tables and handed to `t()`,
# [EN] so `tools/i18n_check.py` **cannot see them** and they must be registered by hand as below.
# [EN] When changing text in `crew/roster.py` / `llm/recommend.py`, change it here **too**, or the
# [EN] English UI will show Chinese (reported by `tools/verify_ui_english.py`).
_ZH2EN.update({
    # ★ 2026-10-13 用户点名把「模型与LLM」这一页改叫「AI模型配置」（原名中英夹生）。
    #   译名跟着改：英文界面要说清"配的是模型"，不再提 LLM 这个行内缩写。
    # [EN] ★ 2026-10-13 the user renamed this page from "模型与LLM" to "AI模型配置" (the old name was
    # [EN] half Chinese, half jargon). The translation follows: the English UI should say "configuring
    # [EN] models", not mention the in-jargon abbreviation LLM.
    'AI模型配置':
        'AI Model Config',
    '模型列表':
        'Model list',
    '＋ 新增模型':
        '+ Add model',
    '默认模型':
        'Default model',
    '默认与三档':
        'Default & three tiers',
    '通用参数':
        'General parameters',
    '推荐：哪个功能用什么模型':
        'Recommended: which model for which job',
    '（默认）':
        '(default)',
    '共 {n} 个模型 · 默认：{d}':
        '{n} models · default: {d}',
    '（没指定，用第一条）':
        '(not set — the first one is used)',
    '（还没配模型 —— 点下面「＋ 新增模型」，或者照上面那套默认接口填一条）':
        '(No models yet — click "+ Add model" below, or add one using the default endpoint above.)',
    '每一条 = 一家可以调用的服务（自有地址与密钥），所以能同时接**多家**：写小说用一家、判定用另一家都行。\n增删改**立刻生效**，不用点保存。':
        'Each entry = one callable service (its own endpoint and key), so you can use **several\nproviders at once**: one for prose, another for judgments. Add/edit/delete **take effect\nimmediately**; no need to press Save.',
    '显示名':
        'Display name',
    '例如 混元 Hy3':
        'e.g. Hunyuan Hy3',
    '模型名':
        'Model name',
    '发给服务端的名字，例如 hy3':
        'The name sent to the server, e.g. hy3',
    '写到 /v1 这一层，程序自己接 /chat/completions':
        'Stop at the /v1 level; the app appends /chat/completions itself',
    '备注':
        'Note',
    '给自己看的：这家是谁给的、什么时候到期':
        'For your own reference: who gave you this key, when it expires',
    '新建模型':
        'New model',
    '编辑模型 · {n}':
        'Edit model · {n}',
    '这一条 = **一家可以调用的服务**（地址 + 密钥 + 模型名）。不同的 Agent 可以用不同的服务商。':
        'One entry = **one callable service** (endpoint + key + model name). Different Agents may\nuse different providers.',
    '默认按**模型名**自动判定；只有你确知它不一样时才改。':
        'Judged automatically from the **model name**; change it only when you are sure it differs.',
    '按模型名判定：{v}':
        'Judged from the model name: {v}',
    '显示名与模型名至少填一个':
        'Fill in at least the display name or the model name',
    '已保存模型「{n}」':
        'Saved model "{n}"',
    '已删除模型「{n}」':
        'Deleted model "{n}"',
    '模型测试「{m}」：{r}':
        'Model test "{m}": {r}',
    '测试这一条（真发一条最小请求）':
        'Test this entry (really sends a minimal request)',
    '改这一条':
        'Edit this entry',
    '删除这一条（不影响已经点名的 Agent，它们会退回档位/默认）':
        'Delete this entry (Agents that named it fall back to their tier / the default)',
    '（跟上面那个默认接口）':
        '(uses the default endpoint above)',
    '{p} · {u}':
        '{p} · {u}',
    '解析顺序：**Agent 点名 → 该 Agent 的档位 → 默认模型 → 第一条**。\n所以「三档都留空、只指定一个默认模型」也是合法配法：全程序都用它，只有点名了的 Agent 例外。\n三档是**快速配置**：各个职位默认按它自己的档走（华彩=关键事件、日常=常规循环、摘要=压缩打分）。':
        'Resolution order: **Agent names one -> that Agent\'s tier -> default model -> first entry**.\nSo "leave all three tiers empty and only set a default model" is also valid: the whole app\nuses it, except Agents that named one.\nThe three tiers are **quick config**: each position follows its own tier by default\n(flourish = key events, daily = regular loop, summary = compression & scoring).',
    '按推荐新增':
        'Add by recommendation',
    '推荐：{p} —— {why}':
        'Recommended: {p} — {why}',
    '已配好，可以直接选：{n}':
        'Configured — pick it directly: {n}',
    '还没配这类模型 —— 可以用默认模型，或者点右边那颗按钮按推荐新增一条（建议：{names}）':
        'This kind of model is not configured yet — use the default, or click the button on the right\nto add one by recommendation (suggested: {names})',
    '模型：{n}':
        'Model: {n}',
    '剧组职位':
        'Crew positions',
    '系统服务':
        'System services',
    '特殊 Agent':
        'Special Agent',
    '已配：{n}':
        'Configured: {n}',
    '还没配 —— 建议加一个：{names}':
        'Not configured — suggested: {names}',
    '每拍都跑':
        'runs every beat',
    '这张表是**按功能**给的（不是排名）。「已配」= 你已经在上面配好了对应的模型，在「剧组 Agents」里点那一位就能选它。':
        'This table is **by function** (not a ranking). "Configured" means you already added a\nmatching model above; click that Agent under "Crew Agents" to select it.',
    '读模型列表失败：{e}':
        'Failed to read the model list: {e}',
    '拉到了 {n} 个模型名：{list}{more} —— 在「＋ 新增模型」里把它们填进去（每条要自己的密钥）。':
        'Fetched {n} model names: {list}{more} — add them under "+ Add model" (each needs its own key).',
    '（还有 {n} 个）':
        '({n} more)',
    '{n}（不在列表里）':
        '{n} (not in the list)',
    # ★ 2026-10-17：页签合并后「推荐表」搬去了「AI模型配置」页体内，
    #   hover 文案随之改短（不再提那张表）—— key 必须与运行时串逐字相同。
    # [EN] Key must match the runtime string character for character.
    '**所有模型都在这儿配**：先加几条模型（每条是自己的地址 + 密钥，所以能同时接多家服务商），再指定一个默认模型。具体某一位 Agent 用哪个模型，去「剧组 Agents」里点它。':
        '**All models are configured here**: add a few models (each with its own endpoint + key, so\nyou can use several providers at once), then pick a default. To set the model for one specific\nAgent, click it under "Crew Agents".',
    '**这个软件有哪些职位**：每个职位的名字、作用、系统提示词，以及**它用哪个模型**。改这里等于改所有小说的默认；只改某一本请去「书斋 · 剧组 Agents」。':
        '**Which positions this software has**: each one\'s name, duty, system prompt, and **which\nmodel it uses**. Editing here changes the default for every novel; to change just one book,\nuse "Study · Crew Agents".',
    '开卷摄取':
        'Book Ingest',
    '把作者给的资料读成能用的设定：提取人物与世界观、判类型、定风格、排进度、拟开局、按需打磨':
        'Turn the material the author provides into usable settings: extract characters and world,\nclassify the genre, fix the style, lay out the progress table, draft the opening, polish\non demand.',
    '记忆摘要':
        'Memory Summarizer',
    '跨天把当天压成几句话、给后台人物补经历 —— 前情提要的来源':
        'Compress each day into a few sentences and give background characters their experiences —\nthe source of the recap.',
    '进度评估':
        'Progress Evaluator',
    '每一拍判断「这一站的判据满足了没有」—— 推进故事进度节点':
        "On every beat, judge whether this stop's criteria are met — advancing the story nodes.",
    '合规复核':
        'Compliance Review',
    '按力度复核即将落盘的正文（独立于创作 Agent，只做判级与提示）':
        'Review the text about to be written to disk, at the chosen strictness (independent of the\ncreating Agents; only grades and advises).',
    '创作服务':
        'Creation Service',
    '外挂的写作后端（MuMuAINovel）：开卷后由它写样章（可选）':
        'An external writing backend (MuMuAINovel): it may write the sample chapters (optional).',
    '文笔与长文':
        'Prose & long form',
    '要写出能读的散文：句子要有节奏、人物要有口气、一段能写几百字不散。便宜模型在这里最容易露馅（重复、套话、一句话掰成三句）。':
        'It must write readable prose: sentences with rhythm, characters with a voice, a passage of\nhundreds of words that holds together. Cheap models give themselves away here (repetition,\ncliches, one sentence stretched into three).',
    '改写与编排':
        'Rewriting & arranging',
    '把已有的材料重新组织成另一种东西（样章→剧本、设定→开局）。要求**读得懂输入、改得动结构**，而且不能丢原意。':
        'Reorganize existing material into something else (sample chapter -> script, settings ->\nopening). It must **read the input and restructure it** without losing the original meaning.',
    '判断与把关':
        'Judgment & gating',
    '只要**一个结论**（满足了没有 / 属于哪一类 / 有几个问题）。这类调用最频繁、最不该花大钱，而且**思考会连输出额度一起吃掉**。':
        'It only needs **one conclusion** (met or not / which category / how many problems). These\ncalls are the most frequent and should be the cheapest — and **thinking eats the output\nbudget too**.',
    '抽取与结构化':
        'Extraction & structuring',
    '把一堆散文本变成**程序能读的 JSON**：字段名固定、条数固定、长了会被截断在半句话里。':
        'Turn loose text into **JSON the program can read**: fixed field names, fixed counts, and\ntruncated mid-sentence when it gets long.',
    '高频演出':
        'High-frequency performance',
    '每一拍都要跑（人物的动作与台词）。它决定"故事活着没有"，也决定账单 —— 所以**要快、要短、要像人说话**。':
        "Runs on every beat (characters' actions and lines). It decides whether the story feels alive\n— and it decides the bill. It must be **fast, short, and sound human**.",
    '事务清单':
        'Checklists',
    '交一份**短清单**（道具单、造型表、宣发一句话、场记核对）。质量要求是"齐、对、短"，不是"华丽"。':
        'Hands in a **short checklist** (prop list, styling sheet, one-line pitch, continuity check).\nThe bar is "complete, correct, short", not "ornate".',
    '外挂服务':
        'External service',
    '这一条指向**另一个程序**（创作服务），它有自己的模型配置；这里选的是"用它的时候按哪个模型算"。':
        'This one points at **another program** (the creation service) which has its own model\nconfig; what you pick here is "which model it counts as when used".',
    '它是全剧组**唯一写正文**的人：样章要能当小说读，文笔不行整条链都白搭。「DeepSeek 小说能力不足」最先卡在这儿。':
        'The only member of the crew who **writes the main text**: the sample chapter must read like\na novel. Without prose skill the whole chain is wasted. "DeepSeek isn\'t good enough at\nfiction" shows up here first.',
    '把样章拆成能拍的分场分拍 —— 要读得懂原著、又要下得了刀，便宜模型容易写成"原句搬运"。':
        'Splits the sample chapter into filmable scenes and beats — it must read the original and be\nwilling to cut. Cheap models tend to just carry sentences over.',
    '导演·作家·剧作者三方会审补局部设定 —— 要同时理解世界规则与当前剧情，是最容易"编出与设定打架的东西"的一步。':
        'Director, novelist and playwright review together to fill in local settings — it must hold\nboth the world rules and the current plot; this is where contradictions with the settings\nare most likely to be invented.',
    '收工复盘：结论 + 修改意见。用的是**已经落盘的正文**，不需要文笔，要的是一眼看得出问题。':
        'Wrap-up retrospective: a conclusion plus change requests. It works on **text already on\ndisk**; it needs no prose skill, just the ability to spot problems at a glance.',
    '衣着·随身物·仪态，一人一条 — 短清单。':
        'Clothing, carried items, bearing — one line per person. A short checklist.',
    '这一场的声音层：环境音·静默·转折，一句话即可。':
        "This scene's sound layer: ambience, silence, turns — one sentence is enough.",
    '点名"哪几句 AI 味重、该怎么改"。它读稿子、不改稿子，所以**要便宜**（每天一次）但**要认得出来**。':
        'Names which lines have an AI flavour and how to fix them. It reads the draft but does not\nrewrite it, so it must be **cheap** (once a day) yet **able to tell**.',
    '剧本定稿后空走一遍，报"哪里会卡住"。产出不进正文，结论型任务。':
        'Walks through the finished script once and reports where it would stall. Its output never\nenters the text; it is a conclusion-type task.',
    '每拍判断"要不要挑事、挑什么事"—— 它决定故事有没有劲。事件本身要贴世界观、要扣人物，写砸了整段戏都平。':
        'On every beat it decides whether to stir things up and how — it decides whether the story has\nenergy. The event must fit the world and involve the characters; done badly the whole\nstretch goes flat.',
    '**全程序花钱最多的一位**：每一拍每个在场人物各一次。它要的是"像人说话"，不是"辞藻漂亮" —— 用大模型写台词既贵又容易演成朗诵。':
        '**The biggest spender in the whole program**: once per present character per beat. What it\nneeds is "sounding human", not "pretty wording" — using a big model for dialogue is both\nexpensive and turns into declamation.',
    '群众演员：一句半句、有诉求的那种。同样高频，但比主要角色更短。':
        'Extras: half a line, with a want behind it. Equally high-frequency but shorter than the main\ncharacters.',
    '场记：每场有没有落点、谁在场上 —— 核对型短输出。':
        'Script supervisor: does every scene land, who is on stage — a checking-type short output.',
    '上屏**之前**的闸门：是不是人话、接不接上文。它每一拍都跑，所以"便宜 + 判得准"比"文笔好"重要得多。':
        'The gate **before** anything goes on screen: is it human, does it connect. It runs every\nbeat, so "cheap + accurate" matters far more than "good prose".',
    '道具单：这一场台面上该有什么。':
        'Prop list: what should be on the table for this scene.',
    '当天那张地图与画面要素 —— 短清单。':
        "The day's map and visual elements — a short checklist.",
    '宣发：一句话卖点与 logline。':
        'Marketing: a one-line selling point and logline.',
    '考据：名物/制度/称谓站不站得住。它要把结论整理成短条目，还要在不确定时**明确说不知道**（编一个错的制度比说不知道坏得多）。':
        'Research: do the objects, institutions and titles hold up. It must organize conclusions into\nshort entries and **say plainly when it does not know** (inventing a wrong institution is far\nworse than saying so).',
    '开卷：把作者给的资料读成人物/世界观/地点/伏笔/进度表/开局方案 —— **一次要吐几百上千行合法 JSON**，是所有步骤里最容易"被长度截断"的一个。这一位建议配一个**输出上限大、JSON 稳**的模型。':
        "Open-book: turns the author's material into characters / world / places / foreshadowing /\nprogress table / opening plan — **hundreds to thousands of lines of valid JSON in one shot**,\nthe step most likely to be cut off by length. Give this one a model with a **large output cap\nand reliable JSON**.",
    '把当天压成 2~3 句前情提要、给后台人物补经历。一天一次、纯压缩，便宜的够了。':
        'Compresses the day into 2-3 sentences of recap and gives background characters their\nexperiences. Once a day, pure compression — cheap is fine.',
    '每一拍问"这一站的判据满足了没有"。**它是最典型的"只要一个结论"**：不需要推理过程，而思考会把输出额度整份吃掉（2026-10-06 的事故就是它）。建议配一个**支持关掉思考**的模型。':
        'On every beat it asks "are this stop\'s criteria met". **The most typical "just give me one\nconclusion" task**: no reasoning process is needed, and thinking would eat the whole output\nbudget (the 2026-10-06 incident). Give it a model that **supports disabling thinking**.',
    '合规复核：会不会越线、该判哪一级。安全功能，**拿不到结论时按"不放行"处理**，所以宁可配一个稳的。':
        'Compliance review: does it cross a line, which level. A safety feature that **treats "no\nconclusion" as "do not release"**, so prefer a reliable model.',
    '它是**外挂的整个写作后端**（MuMuAINovel），写的是整章正文 —— 按"写小说好不好"挑，你自己实测过的那家优先。':
        'It is **the whole external writing backend** (MuMuAINovel) and writes entire chapters — pick\nby "how well does it write fiction", preferring the one you tested yourself.',
    '这是你自己加的职位，没有预设推荐 —— 按它的活像上面哪一类来挑即可。':
        'This is a position you added yourself, with no preset recommendation — pick by which kind of\nwork above it resembles.',
})

_ZH2EN.update({
    # 模型登记表：从旧配置迁移过来的那一条（程序写的备注，要能翻）
    # [EN] Model registry: the entry migrated from the old config (a program-written note)
    '从「天问 · LLM 接入」的旧配置迁移而来':
        'Migrated from the old "Tianji · LLM Access" configuration',
})

_ZH2EN.update({
    # 省钱四招 + 单价（2026-10-12，用户「尽量降低费用」）
    # [EN] Money-saving levers + unit price (2026-10-12, user asked to "reduce the cost")
    '**当前状态**：同题复用 {on}（这次运行已复用 {n} 次，保质期 {ttl} 秒）· 空闲折扣 {d}。':
        '**Current state**: same-question reuse {on} (reused {n} times this run, shelf life {ttl}s) · off-peak discount {d}.',
    'DeepSeek 是峰谷定价：高峰（北京时间周一至周五 9:00-12:00、14:00-18:00）是空闲时段的 **2 倍**。模拟是"可以挑时间跑"的活 —— 把大批量推演放到晚上或周末，账直接砍一半。\n现在的时段：**{now}**。（认得出是峰谷定价的模型才受影响，别家是平价。）':
        'DeepSeek uses peak/off-peak pricing: peak (Beijing time Mon-Fri 09:00-12:00 and 14:00-18:00) is **2x** off-peak. A simulation is work that can pick its time -- move bulk runs to the evening or weekend and the bill is cut in half.\nCurrent window: **{now}**. (Only models recognizable as peak-priced are affected; other providers are flat.)',
    'DeepSeek 的**命中价约为未命中的 1/10**，但它要求"从第一个 token 起完全相同"才算命中。所以**别往固定层（世界观 + 人格固定层 + 系统提示词）里塞会变的东西** —— 一个精确到秒的时间戳就能把后面几千 token 的折扣全废掉。\n看效果：「用量报表」里每个模型的 **缓存命中率** 与 **缓存省下**。长期是 0 就说明前缀里有东西在变。':
        'DeepSeek bills a cache hit at roughly **1/10 of a miss**, but it only counts when the prefix is byte-identical **from the very first token**. So **do not put anything varying into the fixed layer (worldview + static persona layer + system prompt)** -- one timestamp with seconds resolution wastes the discount on the thousands of tokens behind it.\nTo see the effect: the **cache hit ratio** and **cache savings** per model in the Usage Report. A long-run zero means something in the prefix is changing.',
    '关着':
        'off',
    '单价 {p} 元/百万 token（命中/未命中/输出）':
        'Unit price {p} CNY per million tokens (hit/miss/output)',
    '单价未填 —— 账本按内置参考价估算；想让账准，点「改」按你的账单填上':
        'Unit price not filled -- the ledger estimates from built-in reference prices; to make it accurate, click Edit and enter the prices on your own bill',
    '单价（元 / 百万 token，可留空）':
        'Unit price (CNY per million tokens, optional)',
    '各家旗舰与廉价档的单价差 **25~50 倍**。真正需要好模型的只有写正文那几步；判定、抽取、压缩、校对这类"要的是一个结论"的活，便宜档往往做得一样好。\n去「剧组 Agents」点任意一行，就能**单独**给它指定模型 —— 上面那张推荐表写着每个职位推荐哪一类。':
        'Flagship and budget tiers differ **25-50x** in unit price. Only the few steps that write prose really need a good model; judging, extraction, compression and proofreading -- work that wants *a conclusion* -- are often done just as well by the budget tier.\nClick any row under "Crew Agents" to assign a model to it **individually** -- the recommendation table above says which kind each position wants.',
    '完全相同的输入 + 模型 + 参数，在保质期内再问一次 → **直接返回上次的答案**，不发请求、不花钱，而结果仍然是对的。\n只对"同一段输入就该给出同一个结论"的用途生效（判定 / 抽取 / 校对）；**说话、写正文、起名绝不缓存** —— 那些要的正是"每次不一样"。\n开关与白名单在「天问 · 运行」的 Token 经济一组里。':
        'An identical input + model + parameters asked again within its shelf life **returns the previous answer outright**: no request, no cost, and the result is still correct.\nIt only applies to uses where "the same input must give the same conclusion" (judging / extraction / proofreading); **speech, prose and naming are never cached** -- those want "different every time".\nThe switch and whitelist are in the Token economy group under "Tianji · Run".',
    '开着':
        'on',
    '怎么把账单降下来（四招，按省钱多少排）':
        'How to bring the bill down (four levers, biggest saving first)',
    '打开「同题复用」':
        'Turn on "same-question reuse"',
    '把固定前缀钉死（让缓存真的命中）':
        'Pin the fixed prefix (so caching actually hits)',
    '挑时段跑（最省事，不改一个字）':
        'Run in the cheap window (easiest, no prompt change)',
    '普通输入价':
        'plain input price',
    '最贵，账单大头':
        'the priciest, the main item on the bill',
    '未命中价':
        'Cache-miss price',
    '留空 = 按内置参考价估算（价格一直在变，**想让账准请照你的账单填**）。三个数依次是：命中缓存 / 没命中 / 输出。':
        'Empty = estimated from built-in reference prices (prices keep moving, **fill in your own bill to make it accurate**). The three numbers are: cache hit / miss / output.',
    '空闲 —— 现在跑最划算':
        'off-peak --- the cheapest time to run',
    '给粗活配便宜模型（省得最多）':
        'Give routine work a cheap model (biggest saving)',
    '缓存命中价':
        'Cache-hit price',
    '输出价':
        'Output price',
    '通常最便宜':
        'usually the cheapest',
    '高峰 —— 建议等空闲再跑':
        'peak --- better to wait for off-peak',
})

_ZH2EN.update({
    # 用量报表：缓存那几列（2026-10-12）
    # [EN] Usage report: the cache columns (2026-10-12)
    ' · 缓存命中 {p}':
        ' · cache hit {p}',
    '缓存':
        'Cache',
    '缓存命中 Token':
        'Cache-hit tokens',
    '缓存省下（估算）':
        'Saved by cache (estimated)',
    '（还没有命中过缓存 —— 见「AI模型配置」页底部的省钱提示）':
        '(No cache hit yet -- see the money-saving tips at the bottom of the "AI Model Config" page)',
})

_ZH2EN.update({
    # 剧组 Agents 改成 Table（2026-10-13 用户点名）+ 输入框按内容估宽
    # ⚠ 这五个字是**表头/按钮提示**，界面上一出现就是给人看的 ——
    #   不登记的话英文界面那一列表头全是中文（`verify_ui_english` 会报）。
    # [EN] Crew Agents turned into a Table (user asked by name, 2026-10-13) + input boxes sized from
    # [EN] content
    # [EN] ⚠ These five are **headers / button tooltips**: the moment they appear on screen they are read
    # [EN] by humans -- unless registered, that whole column of headers is Chinese under the English UI
    # [EN] (reported by `verify_ui_english`).
    '职位':
        'Position',
    '标记':
        'Tag',
    '作用':
        'Role',
    '提示词':
        'Prompt',
    '改这个职位':
        'Edit this position',
    # ★★ 2026-10-13：剧组表**十列**剩下的栏头 + 那两列单元格里的词。
    #   用户点名「加一些列」之后表头到齐了，但只有前四个登记过 ——
    #   英文界面下「英文名 / 档位 / 出工 / 产出」那一排全是中文。
    # [EN] ★★ 2026-10-13: the remaining headers of the crew table's **ten columns** plus the words in
    # [EN] those two cell columns. The user asked for "some more columns", the headers filled in, but
    # [EN] only the first four were registered -- under an English UI the row
    # [EN] "英文名 / 档位 / 出工 / 产出" was all Chinese.
    '英文名':
        'English name',
    '档位':
        'Tier',
    '出工':
        'Timing',
    '产出':
        'Feeds',
    '每拍':
        'Every beat',
    '每天收工':
        'Daily wrap',
    '常驻':
        'Always on',
    '作者':
        'Author',
    '查看 / 编辑':
        'View / Edit',
    '删除这个职位':
        'Delete this position',
    # ★★ 2026-10-13：「背景滤镜」那一小节（上一轮加的控件）当时漏登记了 ——
    #   英文界面下这一整节都是中文。一并补上。
    # [EN] ★★ 2026-10-13: the "background scrim" section (a control added last round) was not
    # [EN] registered at the time -- the whole section was Chinese under an English UI. Fill it in.
    '背景滤镜':
        'Background scrim',
    '滤镜浓度':
        'Scrim density',
    '纸色滤镜盖在背景图之上、界面内容之下，用来压暗背景、保证文字可读':
        'The paper-colored scrim sits above the background image and below the UI content, dimming'
        ' the background to keep text readable',
    '只作用于开始界面与运行界面，**不影响任何对话框**':
        'Affects only the start and run screens; **no dialog is affected**',
    '0% = 不压暗（背景最清晰）；越大背景越退到文字后面（上限 70%）':
        '0% = no dimming (background clearest); the higher it is, the further the background recedes'
        ' behind the text (max 70%)',
    '这是「运行时滤镜」，改它不会动到背景图片文件；拖动后界面立刻重建生效':
        'This is a **runtime filter**: changing it does not touch the background image file, and the'
        ' UI rebuilds immediately after you drag',
    '✅ 背景滤镜已生效':
        '✅ Background scrim applied',
})

_ZH2EN.update({
    # 天机界面重构（2026-10-12 第二轮：放大 / Table / 拆 Tab / 左对齐）
    # [EN] Tianji UI rework (2026-10-12 round two: enlarge / Table / split Tab / left align)
    '**外部写小说服务**（MuMuAINovel）：本程序可以把它当"写手"用，由它来写整章正文。这一页配的是**那个程序**的地址、密钥、端口与生成参数；它自己的参数写进它的 backend/.env，**改完要重启那个服务**。':
        '**External novel-writing service** (MuMuAINovel): this program can use it as the "writer" for whole\nchapters. This page configures **that program\'s** endpoint, key, port and generation parameters; its\nown parameters go into its backend/.env, and **restarting that service is required**.',
    '**谁都没点名时**用哪一个 —— 换成别的说法：程序里的"兜底"就是它。\n它只影响**没有单独指定过模型**的那些 Agent；要按职位指定，去「剧组 Agents」点那一行。':
        'Which one is used **when nobody named a model** -- in other words, this is the program\'s fallback.\nIt only affects Agents that have **no model of their own**; to assign per position, click that row under\n"Crew Agents".',
    '{n} ✓已配':
        '{n} ✓ configured',
    '{p} 元/百万':
        '{p} CNY/M',
    '三档 = **上一版的配置方式**，现在降级成"没点名时按档走"。下面每一档**先给一句解释**，再给下拉。':
        'The three tiers = **the previous configuration scheme**, now demoted to "follow your tier when nothing\nwas named". Each tier below gives **a line of explanation first**, then its dropdown.',
    '三档（快速配置）':
        'Three tiers (quick config)',
    '为什么':
        'Why',
    '关':
        'off',
    '功能':
        'Function',
    '协议':
        'Protocol',
    '单价':
        'Unit price',
    '右边那列是**推荐**：挑 1~2 个最合适的（照它们去「AI模型配置」上面配好，再去「剧组 Agents」点那一行选上）。已经配好的会标 ✓已配。':
        'The right-hand column is the **recommendation**: one or two best fits (configure them on "AI Model\nConfig" above, then click that row under "Crew Agents" to select it). Anything already configured is\nmarked ✓ configured.',
    '哪个功能用什么模型':
        'Which function uses which model',
    '外部小说服务配置':
        'External novel service',
    '当前：{slot} · 同题复用 {on}（已复用 {n} 次）':
        'Now: {slot} · same-question reuse {on} (reused {n} times)',
    '怎么把账单降下来':
        'How to bring the bill down',
    '打开后**一次模型都不调**：所有回复都用本地写死的样例，用来先看界面、试流程（也用来跑判据）。配好真实模型之后关掉它。':
        'Once on, **not a single model is called**: every reply comes from a hardcoded local sample, so you can\nlook at the UI and try the flow first (the criteria use it too). Turn it off once a real model is\nconfigured.',
    '拉到的模型名':
        'Fetched model names',
    '拉取这家的模型名':
        "Fetch this provider's model names",
    '按内置参考价估算':
        'estimated from built-in reference prices',
    '推荐模型':
        'Recommended model',
    '操作':
        'Actions',
    '某一条模型**自己填了**超时/重试就用它的，没填才用这里的值。\n⚠ 「并发上限」**只能**是全局的：它是一台机器的资源（一个信号量）。按模型各给一个 = N 个模型就有 N 倍并发，反而更容易被服务商限流。':
        'If a model entry **filled in** its own timeout/retries, that wins; these values apply only when it did\nnot.\n⚠ "Concurrency" **can only** be global: it is a machine-level resource (one semaphore). One per model\nwould mean N models give N times the actual concurrency, making rate limits more likely, not less.',
    '正在拉取这一家的模型名…':
        "Fetching this provider's model names...",
    '每一条 = 一家可以调用的服务（**地址与密钥写在它自己身上**），所以能同时接多家：写小说用一家、判定用另一家都行。超时与重试也按条配 —— 各家的脾气不一样。\n增删改**立刻生效**，不用点保存。':
        'One entry = one callable service (**endpoint and key live on the entry itself**), so several providers\ncan be used at once: one for prose, another for judgments. Timeout and retries are per entry too --\nevery provider differs.\nAdd/edit/delete **take effect immediately**; no need to click Save.',
    '没填就用这三项（全局兜底）':
        'Used when unfilled (global fallbacks)',
    '测试结果':
        'Test result',
    '留空 = 用全局':
        'empty = use the global value',
    '空闲时段（半价）':
        'off-peak (half price)',
    '能力':
        'Caps',
    '要什么':
        'Needs',
    '解析顺序：**Agent 点名 → 该 Agent 的档位 → 默认模型 → 第一条**。\\n所以「三档都留空、只指定一个默认模型」也是合法配法：全程序都用它，只有点名了的 Agent 例外。':
        'Resolution order: **the Agent named one -> that Agent\'s tier -> the default model -> the first entry**.\nSo "leave all three tiers empty and set only a default model" is valid too: the whole program uses it,\nexcept Agents that named one.',
    '超时':
        'Timeout',
    '超时(秒)':
        'Timeout (s)',
    '重试':
        'Retries',
    '高峰时段（贵 2 倍）':
        'peak (2x price)',
    '（未填）':
        '(not filled)',
    '（未指定）':
        '(none)',
    '（点这里看说明）':
        '(click for the explanation)',
    '（照上面那类挑）':
        '(pick along the lines above)',
    '（还没配模型 —— 点下面「＋ 新增模型」填一条；一条 = 一家服务，地址与密钥都填在它自己身上）':
        '(No model configured yet -- click "Add model" below and fill one in; one entry = one service, with its\nown endpoint and key)',
})

_ZH2EN.update({
    # 简介简化（2026-10-12，用户：「简介部分简化一下」）
    # [EN] Intro simplification (2026-10-12, user: "simplify the intro")
    '模型自己填了超时/重试就用它的，没填才用这里的值。「并发上限」只能是全局的 —— 它是一台机器的资源，按模型各给一个反而更容易被限流。':
        'If a model filled in its own timeout/retries that wins; these values apply only when it did not.\n"Concurrency" can only be global -- it is a machine-level resource, and one per model would make rate\nlimits more likely, not less.',
    '每一条 = 一家服务（地址、密钥、超时、重试都在它自己身上），所以能同时接多家；增删改**立刻生效**，不用点保存。':
        'One entry = one service (endpoint, key, timeout and retries all live on the entry itself), so several\nproviders can be used at once; add/edit/delete **take effect immediately**, no need to click Save.',
    '这一页配的是**另一个程序**：MuMuAINovel —— 一个独立的「写小说」后端，跑在本机，由本项目通过 HTTP 调用。上游 github.com/xiamuceer-j/MuMuAINovel（GPL-3.0），本地说明见 novelservices/MuMuAINovel/服务说明.md。':
        'This page configures **another program**: MuMuAINovel -- a standalone "novel writing" backend that\nruns locally and is called by this program over HTTP. Upstream: github.com/xiamuceer-j/MuMuAINovel\n(GPL-3.0); local notes in novelservices/MuMuAINovel/服务说明.md.',
})

_ZH2EN.update({
    # 三档解释（`llm/models.TIER_WHY`）—— ⚠ 它是**变量**传给 `t()` 的，
    #   `tools/i18n_check.py` 扫不到 ⇒ 靠 `verify_cost_model` 的 G 段钉住"必须登记"。
    # [EN] Tier explanations (`llm/models.TIER_WHY`) -- ⚠ passed to `t()` as a **variable**, so
    # [EN] `tools/i18n_check.py` cannot see it ⇒ the G section of `verify_cost_model` pins "must be
    # [EN] registered" instead.
    '**关键场面的那几步**（约 15% 的调用量）：重要对话、反思、故事文档、运行小结。这些地方"差一点"看得出来 —— 想让故事好看，钱花在这里。':
        '**The key-scene steps** (~15% of calls): important dialogue, reflection, story\ndocuments, run summaries. A shortfall here is visible -- to make the story good, spend here.',
    '**常规循环**（约 55%）：人物决策、台词、导演派活 —— 量最大的一档。它决定的是"故事跑不跑得动"，不一定要最贵的，但太差会明显水。':
        '**The routine loop** (~55%): character decisions, dialogue, the director assigning work --\nthe largest tier. It decides whether the story runs at all; it need not be the priciest, but too weak\nshows immediately.',
    '**压缩、打分、后台**（约 30%）：记忆摘要、进度判断、校对、抽取。这些只要**一个结论**，便宜档往往做得一样好 —— 省钱最先该动这一档。':
        '**Compression, scoring, background** (~30%): memory summaries, progress judgments,\nproofreading, extraction. These want **a conclusion**, and a cheap tier often does them just as well --\nthe first place to cut.',
    '这一页配的是**另一个程序**：MuMuAINovel —— 一个独立的「写小说」后端，跑在本机，由本项目通过 HTTP 调用（GPL-3.0）。上游：':
        'This page configures **another program**: MuMuAINovel -- a standalone "novel writing" backend that\nruns locally and is called by this program over HTTP (GPL-3.0). Upstream:',
})

_ZH2EN.update({
    '这一页配的是**另一个程序**：MuMuAINovel —— 一个独立的「写小说」后端，跑在本机，由本项目通过 HTTP 调用。许可：GPL-3.0；本地说明见 novelservices/MuMuAINovel/服务说明.md。上游：':
        'This page configures **another program**: MuMuAINovel -- a standalone "novel writing" backend that\nruns locally and is called by this program over HTTP. License: GPL-3.0; local notes in\nnovelservices/MuMuAINovel/服务说明.md. Upstream:',
})

_ZH2EN.update({
    # 用量报表：缓存并进现有行（2026-10-12）
    # [EN] Usage report: the cache figures merged into existing rows (2026-10-12)
    '（命中缓存 {n}）': ' (cache hit {n})',
    '（缓存省下 {c}）': ' (saved by cache {c})',
})

_ZH2EN.update({
    # ── 界面透明度（2026-10-13：方向翻过来了 —— **数字越大越透**）──
    # [EN] ── UI transparency (2026-10-13: the direction was flipped -- **bigger number = more
    # [EN] transparent**)
    '0% = 完全不透（背景图一点不透出）；数值越大越透':
        '0% = fully opaque (no background shows through); the higher the number, the more transparent',
    '最透只到 {m}%：面板底色再低，字就糊在背景花纹上了 —— 所以 {m}%~100% 都停在最透那一档':
        'It only gets as transparent as {m}%: any lower and the text smears into the background '
        'pattern -- so everything from {m}% to 100% stays at the most transparent step',
    '作用范围：**只有**开始界面与运行界面（含中间的叙事/输出区）；**对话框不受影响**，始终是不透明的纸':
        'Scope: **only** the start screen and the run screen (including the centre narrative area); '
        '**dialogs are unaffected** and always keep opaque paper',

    # ── 剧组 Agents 那张表的列宽（2026-10-13）──
    # [EN] ── The crew Agents table's column widths (2026-10-13)
    '左右拖动：调「{c}」这一列的宽度':
        'Drag left/right: adjust the width of the "{c}" column',
    '恢复默认列宽': 'Restore default widths',
    '拖表头两列之间那条缝能调宽窄；天机与书斋**各存一套**，下次打开还是你调好的':
        'Drag the seam between two header columns to resize; Tianji and Study each keep **their own '
        'set**, and it is still how you left it next time you open it',
    '列宽没能存下来：{e}': 'Could not save the column widths: {e}',

    # ── 剧组表名字那格的 tooltip（★ 别写成"拼接字符串再 t()"：拼出来的 key
    #    扫描器扫不到 ⇒ 永远不翻译，英文界面会漏中文）
    # [EN] ── The name cell's tooltip in the crew table (★ don't write "concatenate then t()": the
    # [EN] resulting key is invisible to the scanner => it never translates, leaking Chinese into
    # [EN] the English UI)
    '点开：查看/编辑': 'Click to view / edit',
    '点开：查看/编辑 · 删除（仅自建职位）':
        'Click to view / edit · delete (custom posts only)',
})

# ══════════════════════════════════════════════════════════════
#  运行界面右栏「在场人物」「剧情」两块（2026-10-17）
# [EN] The "On-stage Characters" / "Plot" blocks in the run screen's right column (2026-10-17)
#  ⚠ 这两块以前是**写死的占位文案**（「节点 —」「张力 — · 事件 —」），
#    接上真数据之后新增了下面这几条带占位符的句子 —— 必须登记，
#    不然英文界面上会冒中文。
# [EN] ⚠ These two blocks used to be **hardcoded placeholders** ("节点 —" / "张力 — · 事件 —").
# [EN] After wiring real data, the following parameterised sentences are new -- they must be
# [EN] registered, otherwise Chinese leaks into the English UI.
_ZH2EN.update({
    '张力 {v} · 事件 {e}': 'Tension {v} · Events {e}',
    '张力 {d} · 事件 {d}': 'Tension {d} · Events {d}',
    '进度表 {a}/{b} 已完成': 'Progress {a}/{b} done',
    # 跑马灯的位置指示（2026-10-22）：用户要"翻的时候数字跟着变"。
    # ⚠ **已完成数不跟着翻**：那是事实，翻页改变不了它。跟着变的是"正在看第几站"。
    # [EN] Carousel position indicator: the user wants "the numbers follow while browsing".
    # [EN] ⚠ The **done count does not** follow -- that is a fact and browsing cannot change it; what
    # [EN] follows is "which station I am looking at".
    '进度表 {a}/{b} 已完成 · 看第 {i}/{n}': 'Progress {a}/{b} done · viewing {i}/{n}',
    '上一站': 'Previous station',
    '下一站': 'Next station',
    '{name} · 第 {i}/{n} 站': '{name} · station {i}/{n}',
    '还没有进度表': 'No progress table yet',
    '进度表 {d}': 'Progress {d}',
    '此刻**这一场**里有谁（不是全书人物表）。换场景时会跟着换。\n'
    '★ **点某一行**直接打开那个角色的设置。':
        'Who is in **this scene** right now (not the whole cast list). It follows the scene '
        'when you switch.\n'
        '★ **Click a row** to open that character\'s settings.',
    # ── 顺带补上 2026-10-15「在岗」那一版的欠账（一直是缺译）──
    # [EN] ── Also clears the 2026-10-15 "on duty" debt (never translated)
    '在岗': 'On duty',
    '在岗 · 正在做：{d}': 'On duty · doing: {d}',
    '{n} 位在岗（导演 / 演员 / 群众演员已就位）':
        '{n} on duty (director / actor / extras are in place)',
})

# ══════════════════════════════════════════════════════════════
#  导出结果清单：每一行都是可点的文件链接（2026-10-17）
# [EN] Export result list: every row is a clickable file link (2026-10-17)
#  用户原话：「导出按钮最后的导出的文件的列表我都能点击 点了之后自动用默认md编辑器
#  打开这些文件」。
# [EN] User's exact words: "every file in the list at the end of the export button must be
# [EN] clickable, and clicking should open it with the default markdown editor".
_ZH2EN.update({
    '点一下用系统默认程序打开': 'Click to open with the system default program',
    '（文件已不在）': ' (file is gone)',
    '打不开：文件已不在 {p}': 'Cannot open: the file is gone ({p})',
    '打开导出文件': 'Open an exported file',
    '完成 {ok} / {total} 项 · 点文件名可用默认程序打开':
        'Done {ok} / {total} · click a filename to open it with the default program',
})

# ══════════════════════════════════════════════════════════════
#  「暂停间隔」到点到底停不停（2026-10-17）
# [EN] Does the "pause interval" actually stop on the day it reaches (2026-10-17)
#  用户原话：「一天暂停一次改成3天暂停一次」—— 这个开关以前**只在 .env 里**，
#  界面上没有，于是改了间隔也不会真的停。
# [EN] User's exact words: "change it from pausing once a day to once every 3 days" -- this switch
# [EN] used to live **only in .env** with no UI, so changing the interval never actually paused.
_ZH2EN.update({
    '存档点停下等确认': 'Pause at checkpoint and wait for confirmation',
    '开着：每到一个「暂停间隔」就停下来问你（接着写 / 收工）；'
    '关掉：到点只落盘存档、接着说戏，不停。':
        'On: stop every "pause interval" and ask you (keep writing / wrap up); '
        'off: just save a checkpoint and keep performing, no pause.',
    '「夜间暂停」= 故事里的晚上（22:00–次日 05:00）**每一拍都停**等你点「继续」；'
    '想让它自己跑到底就关掉。':
        '"Night pause" = during story night (22:00-05:00) it **stops on every beat** waiting for '
        'you to click "continue"; turn it off to let it run through on its own.',
})

_ZH2EN.update({
    '⚠ 「暂停间隔」只决定**几天一次**；到点要不要**停下等你**，'
    '是「天问 · 运行」里那个「存档点停下等确认」开关管的。':
        '⚠ "Pause interval" only decides **how often**; whether it actually **stops and waits for you** '
        'is controlled by the "Pause at checkpoint and wait for confirmation" switch in "Tianji · Run".',
})


# ══════════════════════════════════════════════════════════════════
#  界面主路径的英文（2026-10-26 补）
# [EN] English for the main UI paths (added 2026-10-26)
# ══════════════════════════════════════════════════════════════════
#  `verify_ui_english.py` 真机跑英文界面报了 62 处中文，去重后是这四组。
#  为什么单独用 `update()`：它们横跨天机 / 拾卷 / 起笔 / 运行界面四个模块，
#  分散插进上面那个大字典反而更难找 —— 而"这四组曾整组缺英文"本身是值得记的一件事。
#
#  ★ 术语沿用既有译法，别另外发明：
#    · 拾卷 → `Open Story`（`'拾　卷'` 早就这么译，全角空格那版）
#    · 回收站 → `Recycle bin`（`'不会进回收站'` 那条用的就是 recycle bin）
#    · 天机 → `Settings`
#
#  ⚠ 仍然缺译的是**错误提示与罕见路径**（`i18n_check.py` 报的另外 150 余条）：
#    那些不是主路径，但英文界面下一旦触发就是整句中文。要补得整批补，
#    单个补等于"看起来在做事"。清单见 `python tools/i18n_check.py`。
# [EN] ★ Terminology follows existing translations; do not invent new ones.
# [EN] ⚠ What is still missing is **error messages and rare paths** (~150 more keys from
# [EN] `i18n_check.py`). Not main paths, but when they fire under an English UI the whole
# [EN] sentence is Chinese. They should be done as a batch, not one at a time.
_ZH2EN.update({
    # ── 天机 / 书斋：两个核心旋钮（滑块）──
    # [EN] ── Settings / Project Settings: the two core dials (sliders) ──
    '任务规训(0-100)': 'Task discipline (0-100)',
    '文笔规训(0-100)': 'Prose discipline (0-100)',
    '低=照剧本演 / 高=只给议程': 'Low = play the script / High = agenda only',
    '低=很讲究 / 高=松': 'Low = very strict / High = loose',

    # ── 拾卷：页签、回收站、批量删除 ──
    # [EN] ── Open Story: tabs, recycle bin, bulk delete ──
    '拾卷': 'Open Story',
    '回收站': 'Recycle bin',
    '删除选中': 'Delete selected',
    '删除选中（{n}）': 'Delete selected ({n})',
    '全选': 'Select all',
    '全选这一栏（再点一次全不选）':
        'Select everything in this column (click again to clear)',
    '这一栏现在没有能勾的东西。': 'There is nothing to tick in this column right now.',
    '勾上左边那些小方框（可多选），再点这里一次删掉。':
        'Tick the boxes on the left (multi-select), then click here to delete them all at once.',
    '勾上它，再用栏头的「删除选中」一次删几轮（连同它下面的子节点）':
        'Tick it, then use "Delete selected" in the header to remove several runs at once '
        '(including everything nested under them)',

    # ── 起笔：自由度滑块与三档说明 ──
    # [EN] ── New Story: the freedom slider and its three bands ──
    '自由度（这一轮让别人替你做多少决定）':
        'Freedom (how much this round decides on your behalf)',
    '只给要办的事：剧本压到一小段，**不给分拍表** —— '
    '他知道今天要办什么，不知道这一拍该演什么。':
        '**Tasks only**: the script is cut down to a short paragraph with **no beat sheet** -- '
        'he knows what to get done today, but not what to play in this beat.',
    '标准：禁词少列约四分之一，其余与"很讲究"相同。':
        'Standard: about a quarter fewer banned words, otherwise the same as "very strict".',

    # ── 运行界面：剧情/进度条的提示（tooltip）──
    # [EN] ── Run screen: the plot/progress tooltip ──
    '故事走到哪个节点了、当前张力多大、进度表上还剩几项。\n'
    '**剧情用跑马灯看**：点左右三角或滚动鼠标滚轮翻站，'
    '● 演过了 / ○ 还没演 / ▶ 正在演这一站。\n'
    '节点与进度表都来自「设定集/故事进度.yaml」。':
        'Which node the story has reached, current tension, and how many items remain.\n'
        '**Scroll the track to browse**: click the left/right arrows or use the mouse wheel. '
        '● played / ○ not yet / ▶ playing now.\n'
        'Nodes and progress both come from "settings/story-progress.yaml".',
})


# ⚠ 这几条是「译了长文案、漏了前缀/实参」的补充（2026-10-26）。
#   真机判据当时报的是 `任务：**Tasks only**: …` —— 英文句子开头挂着中文前缀。
# [EN] Follow-up for "translated the sentence but missed its prefix / placeholder argument".
# [EN] The criterion reported `任务：**Tasks only**: ...` -- a Chinese prefix on an English sentence.
_ZH2EN.update({
    '任务：': 'Task: ',
    '文笔：': 'Prose: ',
    # `{what}` 的实参（`t('这一轮')`）—— 实参不译，英文模板里就会夹中文
    # [EN] the `{what}` argument; if untranslated, Chinese appears inside the English template
    '这一轮': 'this run',
    '展开看{what}的摘要（点标题才是选中）':
        'Expand the summary of {what} (click the title to select)',
    # 与"…一次删几轮"是两个不同的 key：这条删的是**小说**（整本），上面那条删的是**存档**
    # [EN] Distinct from the "...删几轮" key: this one deletes whole novels, that one deletes saves
    '勾上它，再用栏头的「删除选中」一次删几本':
        'Tick it, then use "Delete selected" in the header to remove several novels at once',
})


# ══════════════════════════════════════════════════════════════════
#  防重复导出 + 逐天进度（2026-10-26）
# [EN] Duplicate-export guard + per-day progress (2026-10-26)
# ══════════════════════════════════════════════════════════════════
#  背景：用户点「停止」→ 收工自动导出开始跑（MuMu 逐天重写，可十分钟）→
#  他以为没反应 → 又点手动导出 ⇒ 产出 v1/v2。这一块是那两个改动的配套文案。
# [EN] Background: Stop triggers a finish-time auto export (MuMu rewrites day by day, up to ten
# [EN] minutes); the user assumed a freeze and exported again => two drafts. These are the strings
# [EN] for the two fixes.
_ZH2EN.update({
    # 逐天进度
    '正在写第 {i}/{n} 天': 'writing day {i}/{n}',
    # 「已经自动导出过」的说明与出口
    '这一轮结束（点「停止」）时已经自动导出过下面这几档，'
    '手动导出默认跳过它们 —— 要再导一份请勾上最后那一项：':
        'These were already auto-exported when this round ended (on "Stop"), so manual export '
        'skips them by default -- tick the last box to export one more copy:',
    '仍然再导一份（会多出 v2 等新版本）': 'Export one more copy anyway (produces v2 etc.)',
    '这几档在「停止」时已经自动导出过了 —— 文件在上面那几行，'
    '要再导一份请勾「仍然再导一份」':
        'These were already auto-exported on "Stop" -- the files are listed above. '
        'Tick "Export one more copy anyway" to do it again.',
    '已跳过（「停止」时自动导出过了）：{names}':
        'Skipped (already auto-exported on "Stop"): {names}',
    # 忙（另一条导出在跑）
    '⚠ 收工时的自动导出**还在跑**，等它结束再导（否则会拦下来）':
        '⚠ The finish-time auto export is **still running**; wait for it to finish '
        '(otherwise this one is blocked)',
    '⚠ 已经有一个导出在跑（{who}），这一次没有执行 —— 等它结束再点一次。':
        '⚠ Another export is already running ({who}); this one did not run -- try again after it '
        'finishes.',
    '收工自动导出': 'finish-time auto export',
    '手动导出': 'manual export',
})

# ══════════════════════════════════════════════════════════════
#  「剧情总览」（2026-10-26）
# ⚠ 与前面那块分开写：这一批是新窗口的文案，堆在文件末尾好找、也好整体删改。
#   两条规矩照旧：**key 必须与 `t(…)` 里的字面量逐字相同**（多一个空格就查不到，
#   表现为"英文界面里冒中文"，而 `t()` 不会报错）；带占位符的 key 里占位符名字
#   要与调用处的 `**kw` 一致。
# [EN] "Story overview" (2026-10-26). ⚠ Kept separate from the block above: this is one new window's
# [EN] copy, easy to find and revise as a unit. Two rules hold: **the key must match the literal in
# [EN] `t(…)` exactly** (one extra space and the lookup misses, which shows up as Chinese in the
# [EN] English UI while `t()` reports nothing), and placeholder names must match the call site.
# ══════════════════════════════════════════════════════════════
_ZH2EN.update({
    # ── 对话框与入口 ──
    '剧情总览 · 从头到尾': 'Story overview · start to finish',
    '上一次推演': 'Previous run',
    '下一次推演': 'Next run',
    '更新于 {x}': 'updated {x}',
    '还没有推演记录 —— 先点「起　笔」跑一段':
        'No runs yet -- start one with "Begin" first',
    '先在「拾卷」里选一本书': 'Pick a book in "Pickup" first',
    '剧情总览：从头到尾的流程图（还能翻看以前的推演）':
        'Story overview: a start-to-finish flowchart (earlier runs included)',
    '点这里看从头到尾的流程图': 'Click for the start-to-finish flowchart',
    '点标题打开「剧情总览」：这次推演从头到尾的流程图':
        'Click the title for the story overview: this run from start to finish',
    '故事走到哪个节点了、当前张力多大、进度表上还剩几项。\n'
    '**剧情用跑马灯看**：点左右三角或滚动鼠标滚轮翻站，'
    '● 演过了 / ○ 还没演 / ▶ 正在演这一站。\n'
    '**点标题、点站名、或点最右边那个图标** → 打开「剧情总览」：'
    '从头到尾的流程图，还能翻看以前的推演。':
        'Which plot point we are on, how tense it is, how many stations are left.\n'
        '**Browse with the carousel**: click the left/right triangles or scroll the wheel; '
        '● played / ○ not yet / ▶ playing now.\n'
        '**Click the title, the station name, or the icon on the right** to open the story '
        'overview: a start-to-finish flowchart, with earlier runs included.',

    # ── 流程图本身 ──
    '已演过': 'played',
    '正在演': 'playing now',
    '还没演到': 'not yet',
    '要你选': 'your choice',
    '故事线': 'Story line',
    '情节流程（从上往下）': 'Plot flow (top to bottom)',
    '设定集里还没有情节表。': 'The setting bible has no plot table yet.',
    '这次推演还没有落盘的戏': 'This run has no saved scenes yet',
    '第 {d} 天 · {n} 幕 · 演过 {p}/{q} 站':
        'Day {d} · {n} scenes · {p}/{q} stations played',
    '第 {a}–{b} 天': 'days {a}-{b}',
    '{span} · {n} 幕': '{span} · {n} scenes',
    '设定集标为已完成（这次推演没演到）':
        'marked done in the bible (this run never reached it)',
    # ⚠ 译文里**不许再出现中文文件名**：`verify_ui_english` 把"CJK 出现在英文界面上"
    #   一律算漏翻（文件名是特例，但把特例塞进 ALLOW 会放行整类文案）。
    #   中文原文照旧写全名（那边是给作者看的），英文只说"进度表"。
    # [EN] ⚠ The translation must not repeat the Chinese filename: `verify_ui_english` treats any CJK
    # [EN] on the English UI as a miss (a filename is a special case, but whitelisting it would let a
    # [EN] whole class through). The Chinese original keeps the full name; English says "progress table".
    '设定集里还没有「故事进度.yaml」，所以这张图只有演过的正文，没有情节骨架。':
        'The setting bible has no progress table yet, so this chart only has what was played, '
        'with no plot skeleton.',
    '这次推演还没演到任何一站。': 'This run has not reached any station yet.',

    # ── 选择点 ──
    '这条线后面还有 {n} 个情节': '{n} plot points follow this line',
    '点这条，从它往下看（这条后面的事还没演到）':
        'Pick this line and read down from it (nothing has been played after it yet)',
    '（这几条是从概要里读出来的；想改就在设定的「故事进度」里给这一站加「选项:」）':
        '(These were read out of the summary; to change them, add a "choices" field to this '
        'station in the setting bible)',
    '沿「{x}」这条线往下看': 'Following the "{x}" line',
    '（这条线后面的事还没演到）': '(nothing after this line has been played yet)',
    '点一条，从这里往下看': 'Pick one and read down from it',
})

# ══════════════════════════════════════════════════════════════
#  「详细剧情」（2026-10-26 第二轮：用户嫌总览太简略）
# [EN] "Detailed story" (2026-10-26, round two: the user found the overview too brief)
# ══════════════════════════════════════════════════════════════
_ZH2EN.update({
    # ── 页签与标题 ──
    '详细剧情': 'Detailed story',
    '流程图': 'Flow chart',
    '{n} 拍 · 正文 {c} 字': '{n} beats · {c} characters of prose',

    # ── 汇总块 ──
    '关键剧情与转折点（共 {a} 个转折 · {b} 个关键）':
        'Key plot and turning points ({a} turns · {b} key beats)',
    '关键剧情与转折点': 'Key plot and turning points',
    '这一轮还没有数出转折点（剧情站没换、张力也没大跳）——戏还在铺，属于正常。':
        'No turning point has been counted yet (no station change, no big tension jump) -- the '
        'story is still laying groundwork, which is normal.',
    '按天详细': 'Day by day',
    '这次推演还没有落盘的戏，所以没有详细剧情。':
        'This run has no saved scenes yet, so there is no detailed story.',
    '点这里展开 / 收起这一天的详细剧情': 'Click to expand / collapse this day',
    '这一天的转折与关键': 'Turning points and key beats in this day',
    '剧作家的分拍（{n} 小段）': 'The playwright’s beats ({n} segments)',
    '正文（剧作家写的 {n} 段）': 'Prose ({n} paragraphs by the playwright)',
    '分镜（{n} 镜）': 'Storyboard ({n} shots)',
    '当天梗概': 'Day summary',
    '场景：{x}': 'Setting: {x}',
    '台词：{x}': 'Line: {x}',

    # ── 分拍里的字段名 ──
    '推进：{x}': 'Pushes: {x}',
    '目标：{x}': 'Goal: {x}',
    '难题：{x}': 'Problem: {x}',
    '道具：{x}': 'Props: {x}',

    # ── 转折 / 关键 ──
    '转折': 'Turn',
    '关键': 'Key',
    # caption 是闭集（`director/engine.py` 的 event_type + 代码硬给的「导演自救」）。
    # ⚠ 新加一类事件时**两条都要改**：这条表 + `gui.story_flow_dialog.CAPTION_KEYS`
    #   （后者决定"要不要走翻译"，前者给译文）。只改一处的表现是英文界面里
    #   冒出一条中文 —— 而 `t()` 不报错。
    # [EN] The captions are a closed set. ⚠ Adding a kind means editing **both** this table and
    # `gui.story_flow_dialog.CAPTION_KEYS` (the latter decides whether to translate at all).
    # Changing only one shows a Chinese line in the English UI -- and `t()` reports nothing.
    '外部刺激': 'Outside stimulus',
    '人物冲突': 'Character clash',
    '巧合': 'Coincidence',
    '秘密泄露': 'Secret leaks',
    '伏笔激活': 'Foreshadow fires',
    '导演自救': 'Director rescue',
    # 换场 / 站切换这两句是**代码拼出来的**（不是素材），所以 key 要能对上
    '换场：{a} → {b}': 'Change of place: {a} → {b}',
    '情节推进到「{x}」': 'Plot advances to “{x}”',
    '张力 {a} → {b}': 'Tension {a} → {b}',
})

# ══════════════════════════════════════════════════════════════════
#  剧情总览 / 详细剧情 —— 补齐（2026-10-26 英语版体检）
# [EN] Story flow / detailed plot -- gaps found in the 2026-10-26 English pass
# ══════════════════════════════════════════════════════════════════
#  这几条是**带占位符的模板**或**隐式拼接的长句**：探针按单行正则扫不到，
#  只有整串登记才命中。`t()` 缺 key 时静默回退原文 ⇒ 英文界面里冒中文、不报错。
# [EN] These are templated or implicitly concatenated strings: a per-line regex probe cannot
# [EN] match them, so only the whole string registers. A missing key silently falls back to the
# [EN] original -- Chinese text in the English UI, with no error.
_ZH2EN.update({
    '{n} 拍': '{n} beats',
    '正文 {n} 字': '{n} characters of prose',
    '{name} · 出工中…': '{name} · working…',
})

# ══════════════════════════════════════════════════════════════════
#  拾卷 · 回收站 / 存档树（2026-10-26 英语版补齐）
# [EN] Open Story · Recycle bin / save tree (English pass, 2026-10-26)
# ══════════════════════════════════════════════════════════════════
#  这一整块是**回收站面板**的文案。它一直没登记英文：面板只在"回收站里有东西"
#  时才铺开，而 `verify_ui_english` 打开的是空回收站 ⇒ 屏幕上一个中文都没有 ⇒
#  判据绿着、英文用户一点进去满屏中文。**"没被打开过的界面"等于没被守住。**
# [EN] This whole block is the **recycle-bin pane's** copy. It was never registered in English:
# [EN] the pane only renders when the bin has something in it, while `verify_ui_english` opens an
# [EN] empty bin, so not a single Chinese character shows on screen, the check stays green, and an
# [EN] English user sees a wall of Chinese the moment they click in.
# [EN] **A screen nobody opens is a screen nobody guards.**
_ZH2EN.update({
    # ── 回收站页与两个桶 ──
    '① 回收站里的书': '① Books in the recycle bin',
    '② 存档（回收站）': '② Saves (recycle bin)',
    '整本被删的书，和"只有存档在回收站"的书。':
        'Books deleted whole, and books with "only saves in the recycle bin".',
    '实线框 = 真的在回收站里；**虚线框** = 只是借来撑树的父节点，**并没有被删除**。':
        'Solid box = really in the recycle bin; **dashed box** = a parent node kept only to hold '
        'the tree up, **not deleted**.',
    '回收站是空的。': 'The recycle bin is empty.',
    '这一桶里没有存档。': 'No saves in this bucket.',
    '（来源不明的存档）': '(save of unknown origin)',
    '书还在；只有 {n} 轮存档在回收站':
        'The book is still here; only {n} saved rounds are in the recycle bin',
    '原书已不在项目里 · {n} 轮存档': 'The original book is gone from this project · {n} saved rounds',
    '不知道原本属于哪本书 · {n} 轮': 'Unknown original book · {n} rounds',
    '未删除·撑树': 'not deleted · holds the tree up',
    '已删除 · {when}': 'Deleted · {when}',
    '删于 {w}': 'Deleted {w}',
    '删除时间：{w}': 'Deleted at: {w}',
    '路径：{p}': 'Path: {p}',
    '{n} 个文件 / {sz}': '{n} files / {sz}',
    '… 还有 {n} 轮': '… {n} more rounds',
    '这一轮里有 {n} 个文件，共 {sz}': 'This round holds {n} files, {sz} in total',
    '合计 {n} 轮存档 / {c} 个文件 / {sz}。': '{n} saved rounds / {c} files / {sz} in total.',
    '勾选：{names}': 'Ticked: {names}',
    '小说：{names}': 'Books: {names}',
    '（先在中间点一条）': '(click one in the middle first)',
    '这一轮在回收站里的样子。': 'This round as it sits in the recycle bin.',
    '这一栏空了': 'This column is empty',
    '（这一栏空了 —— 书都在最左边的「回收站」里）':
        '(this column is empty — the books are all in the "Recycle bin" tab on the far left)',
    '（没有书，也就没有存档）': '(no books, so no saved rounds)',
    # ── 树上的节点说明 ──
    '推断': 'Inferred',
    '在回收站': 'In the recycle bin',
    '这一轮**还没收工** —— 正文已经自动落盘到 {at}，断电/关掉程序后下次起笔会从这里接着演'
    '（最多损失一个落盘间隔）。':
        'This round **has not wrapped up yet** — the prose is already auto-saved to {at}; after a '
        'power cut or a restart the next start continues from there (losing at most one save '
        'interval).',
    '这一条和上面那一轮的父子关系是**推断**的：旧存档没有记录"从哪一轮起笔"，'
    '按序号前一轮推。如果你当年是从更早的存档起笔，这一条会不准。':
        'The parent/child link between this item and the round above is **inferred**: old saves '
        'never recorded which round they started from, so the previous one is assumed by index. '
        'If you actually started from an earlier save, this will be wrong.',
    '这一轮现在在回收站里 —— 它出现在这里，只是因为下面那几轮是从它分出来的；'
    '没有它，那棵子树就没有根。要去处理它，请切到最左边的「回收站」。':
        'This round is in the recycle bin — it only appears here because the rounds below branched '
        'from it; without it that subtree has no root. To deal with it, switch to the "Recycle bin" '
        'tab on the far left.',
    '这一轮没有被删除。它出现在这里，只是因为下面那几轮是从它分出来的 —— '
    '没有它，那棵子树就没有根。':
        'This round was not deleted. It appears here only because the rounds below branched from '
        'it — without it that subtree has no root.',
    '这本书的存档都在回收站里 —— 去最左边的「回收站」可以恢复。':
        'All saves for this book are in the recycle bin — restore them from the "Recycle bin" tab '
        'on the far left.',
    '这一轮**故事里**的时间跨度：从第几天演到第几天。不是「你什么时候点的起笔」'
    '——那个时间在标题右边。':
        'The time span **inside the story** for this round: which days it runs from and to. Not '
        '"when you clicked start" — that one is on the right of the title.',
    '起笔时记录（第 {d} 天）': 'Recorded when starting (day {d})',
    '记「这一轮从哪来」失败（不影响起笔，拾卷里会当根节点）：{e}':
        'Could not record where this round came from (starting still works; it shows as a root in '
        'Open Story): {e}',
    '类型 · {g}': 'Type · {g}',
    '展开/收起存档节点': 'Expand/collapse save nodes',
    # ── 勾选 / 删除 / 恢复的按钮与提示 ──
    '恢复这一轮': 'Restore this round',
    '把这一轮恢复回原来的书里': 'Restore this round into its original book',
    '永久删除这一轮': 'Permanently delete this round',
    '永久删除这一轮（连它下面的子节点）': 'Permanently delete this round (with the rounds under it)',
    '永久删除这一轮？': 'Permanently delete this round?',
    '永久删除这一轮和它下面的 {n} 轮？':
        'Permanently delete this round and the {n} rounds under it?',
    '永久删除（{n}）': 'Delete permanently ({n})',
    '永久删除': 'Delete permanently',
    '恢复选中（{n}）': 'Restore selected ({n})',
    '恢复选中': 'Restore selected',
    '彻底删除': 'Delete permanently',
    '现在能做什么：程序可以正常打开，也能翻看设定与文档；':
        'What works right now: the program opens normally and you can browse settings and docs;',
    '删掉这一轮和它下面的 {n} 轮？': 'Delete this round and the {n} rounds under it?',
    '删掉选中的 {n} 轮（连子节点共 {m} 轮）？':
        'Delete the selected {n} rounds ({m} including child rounds)?',
    '删掉选中的 {n} 本小说？': 'Delete the selected {n} books?',
    '永久删除这一本？': 'Permanently delete this book?',
    '永久删除这 {n} 本？': 'Permanently delete these {n} books?',
    '永久删除选中的 {n} 轮（连子节点共 {m} 轮）？':
        'Permanently delete the selected {n} rounds ({m} including child rounds)?',
    '勾上它，再用栏头的「永久删除」一次删几本':
        'Tick it, then use "Delete permanently" in the column header to delete several books at once',
    '勾上它，再用栏头的「永久删除」一次删几轮（连同它下面的子节点）':
        'Tick it, then use "Delete permanently" in the column header to delete several rounds at '
        'once (with their child rounds)',
    '先点每条左边的小方框勾上，再点这里。':
        'Tick the little box on the left of each row first, then click here.',
    '先点每本书左边的小方框勾上，再点这里。':
        'Tick the little box on the left of each book first, then click here.',
    '这一栏（小说）还没勾 —— 先点书名左边的小方框。':
        'Nothing ticked in this column (books) — click the little box left of the title first.',
    '这一栏（存档）还没勾 —— 先点标题左边的小方框。':
        'Nothing ticked in this column (saves) — click the little box left of the title first.',
    '先在上面点一本"有存档在回收站"的书。':
        'First click a book above that "has saves in the recycle bin".',
    '勾上的那几本在回收站里找不到对应条目。':
        'The ticked books have no matching entry in the recycle bin.',
    '勾上的那几轮在回收站里找不到对应条目。':
        'The ticked rounds have no matching entry in the recycle bin.',
    '把这一栏勾上的东西**永久删掉**（存档会连子节点一起走）。':
        '**Permanently delete** the ticked items in this column (saves take their child rounds '
        'along).',
    '把这一栏勾上的东西搬回原来的位置。':
        'Move the ticked items in this column back where they were.',
    '删一条带子节点的，会连子节点一起走。':
        'Deleting one that has child rounds takes the child rounds along.',
})

# ── 删除/移动确认框里的那几句长正文（同一段话有几个变体，逐条登记） ──
# [EN] The long confirmation paragraphs (several variants of the same wording, one entry each)
_ZH2EN.update({
    '这些会**移到回收站**（对话框最左边那个 Tab）—— 在回收站里可以找回，也可以永久删除。':
        'These are **moved to the recycle bin** (the leftmost tab) — restore them from there, or '
        'delete them for good.',
    '都会**移到回收站**（对话框最左边那个 Tab），在那边可以找回或永久删除。':
        'All of them are **moved to the recycle bin** (the leftmost tab), where they can be '
        'restored or deleted for good.',
    '都会**移到回收站**（对话框最左边那个 Tab），在那边可以恢复或永久删除。':
        'All of them are **moved to the recycle bin** (the leftmost tab), where they can be '
        'restored or deleted for good.',
    '会**移到回收站**（对话框最左边那个 Tab）—— 在回收站里可以整本恢复，也可以永久删除。':
        '**Moved to the recycle bin** (the leftmost tab) — the whole book can be restored there, '
        'or deleted for good.',
    '**这一轮下面还衍生着 {n} 轮**，它们会跟着一起移到回收站：':
        '**{n} more rounds branch off this one**; they move to the recycle bin with it:',
    '有些轮次下面还衍生着别的轮次 —— 子节点会跟着一起走，合计 {m} 轮。':
        'Some rounds have other rounds branching off them — child rounds go along too, {m} rounds '
        'in total.',
    '设定集、肖像、全部 {n} 轮存档一起走，共 {c} 个文件 / {sz}':
        'Settings, portraits and all {n} saved rounds go with it — {c} files / {sz}',
    '设定集、肖像、全部存档一起走。': 'Settings, portraits and every save go with it.',
    '会**永久删除这一轮**，以及所有从它衍生的子节点（共 {n} 轮）。**不可恢复** —— '
    '文件真的从磁盘上删掉。':
        '**Permanently deletes this round** and every child round branching from it ({n} rounds). '
        '**Cannot be undone** — the files really are removed from disk.',
    '会**永久删除**这些轮次（含它们下面衍生的子节点），**不可恢复**。':
        '**Permanently deletes** these rounds (including the child rounds branching off them). '
        '**Cannot be undone**.',
    '会**永久删除**这一本书（设定集、肖像、全部存档），**不可恢复**。':
        '**Permanently deletes** this book (settings, portraits, every save). **Cannot be undone**.',
    '要删的是整整一本书，所以还要**手打一次「{w}」**才让点确认。':
        'This deletes a whole book, so **type "{w}" by hand** before the confirm button works.',
    '（一次删多本，所以打的是「彻底删除」而不是每本书名。）':
        '(several books at once, so the phrase is "Delete permanently" rather than each title.)',
    '已把 {n} 轮存档移到回收站（最左边那个 Tab 里可以找回）：{names}':
        'Moved {n} saved rounds to the recycle bin (restore them from the leftmost tab): {names}',
    '已把《{name}》移到回收站：{path}': 'Moved "{name}" to the recycle bin: {path}',
    '已删除最后一本小说 —— 「拾卷」这一栏空了。它还在最左边的「回收站」里，随时可以恢复。':
        'Deleted the last book — the "Open Story" column is now empty. It is still in the '
        '"Recycle bin" tab on the far left and can be restored at any time.',
    '没能删掉「{name}」：{why}': 'Could not delete "{name}": {why}',
    '已恢复 {n} 条到原来的位置。': 'Restored {n} items to where they were.',
    '有 {n} 条没恢复成：{why}': '{n} items could not be restored: {why}',
    '已永久删除 {n} 本小说。': 'Permanently deleted {n} books.',
    '有 {n} 本没删成：{why}': '{n} books could not be deleted: {why}',
    '已永久删除 {n} 条。': 'Permanently deleted {n} items.',
    '有 {n} 条没删成：{why}': '{n} items could not be deleted: {why}',
})

# ── 启动、创作服务、剧组消息、运行界面上的小字 ──
# [EN] Startup, creation services, crew messages and the small print on the runtime screen
_ZH2EN.update({
    '界面正在启动…': 'Starting the interface…',
    '正在进入开始界面…': 'Entering the start screen…',
    '显示主窗口失败': 'Could not show the main window',
    '写启动失败标记失败': 'Could not write the startup-failure marker',
    '关掉对话框失败': 'Could not close the dialog',
    '创作服务已全部就绪': 'All creation services are ready',
    # ── 2026-10-27：启动窗口里那批**服务拉起的细节行**（`[时间][服务]` 那一格）──
    #   ★★★ 它们进的是启动窗口的日志区（用户这次点名要看的），**不是**运行界面上的小字；
    #     但 `i18n_check` 扫的是"源码里写下的每一条中文" ⇒ 不登记英文就是缺译，
    #     回归里的 `verify_i18n_coverage` 当场变红（这一轮就是这么被抓住的）。
    # [EN] ── 2026-10-27: the **service bring-up detail lines** in the splash log box (the
    # [EN] `[time][service]` column). ★★★ They land in the splash log (what the user asked to see),
    # [EN] not in the runtime UI's small print; but `i18n_check` scans **every Chinese string in the
    # [EN] source**, so no English entry means a missing translation and `verify_i18n_coverage` goes
    # [EN] red (that is exactly how this round was caught).
    '准备拉起创作服务（{n} 家）—— 首次启动要建环境，可能要几十秒':
        'Starting {n} creation services — the first run builds the environment, it may take tens of '
        'seconds',
    '第一次没起来：{why} · 3 秒后再试一次':
        'Did not start the first time: {why} · retrying in 3 seconds',
    '模块加载失败：{e}': 'Module failed to import: {e}',
    '服务本来就在跑（不再起第二个），用时 0.0 秒':
        'Already running (not starting a second one), took 0.0 s',
    '拉起过程抛异常：{e}': 'Starting it raised: {e}',
    '没起来：{why}': 'Did not start: {why}',
    '……启动日志到此为止（后面还有），看 logs/ 里这份运行的应用日志':
        '…the startup log ends here (there is more): see this run\'s application log under logs/',
    '预启动创作服务时出错': 'Error while pre-starting the creation services',
    '等待创作服务时出错': 'Error while waiting for the creation services',
    '（拉起过程出错）': '(error while starting)',
    '（拉起过程出错：{e}）': '(error while starting: {e})',
    '正在拉起 {n}（{i}/{tot}）…': 'Starting {n} ({i}/{tot})…',
    '{n} 已就绪（{i}/{tot}）': '{n} ready ({i}/{tot})',
    '{n} 没起来（{i}/{tot}）· 不影响推演，进界面后可在天机里重试':
        '{n} did not start ({i}/{tot}) · the simulation still works; retry in Tianji after entering',
    '创作服务有 {n} 家没起来（{who}）· 不影响推演，进界面后可在天机里重试':
        '{n} creation services did not start ({who}) · the simulation still works; retry in Tianji '
        'after entering',
    '创作服务已全部有结论（{s:.0f} 秒）': 'All creation services settled ({s:.0f} s)',
    '仍在拉起创作服务（已等 {m:.1f} 分钟）…':
        'Still starting the creation services ({m:.1f} min so far)…',
    '创作服务还在拉（已等 {m:.0f} 分钟）—— 可以点右上角 ✕ 先进入，它们在后台继续':
        'The creation services are still starting ({m:.0f} min so far) — click ✕ at the top right '
        'to enter now; they keep going in the background',
    '创作服务没起来：{who}。停在这里不进入开始界面 —— 点右上角 ✕ 仍然进入'
    '（进「天机 → 外部创作服务」可以手动重试）':
        'The creation services did not start: {who}. Staying here instead of entering the start '
        'screen — click ✕ at the top right to enter anyway (retry by hand in '
        '"Tianji → External creation services")',
    '{w}（novelservices 目录整个没找到 —— 是不是从别处拷了程序、漏了这个目录？）':
        '{w} (the whole novelservices folder is missing — was the program copied from somewhere '
        'without it?)',
    '{w}（novelservices 目录在，是这个模块自己缺东西 —— 多半少装了依赖，'
    '在程序目录里跑一次 "pip install -r requirements.txt"）':
        '{w} (the novelservices folder is there; this module itself is missing something — most '
        'likely a dependency. Run "pip install -r requirements.txt" in the program folder)',
    '✘ 没加载到 novelservices.mumu_bridge': '✘ Could not load novelservices.mumu_bridge',
    '✘ 没加载到 novelservices.{m}': '✘ Could not load novelservices.{m}',
    '刷新外部服务状态失败：{e}': 'Could not refresh the external service status: {e}',
    '导出小说版本时用它重写': 'used to rewrite the novel version on export',
    '隐藏运行窗口底部的 AI 对话输入框': 'Hide the AI chat box at the bottom of the runtime window',
    '✅ 已隐藏运行窗口底部的 AI 对话输入框':
        '✅ Hid the AI chat box at the bottom of the runtime window',
    '✅ 已显示运行窗口底部的 AI 对话输入框':
        '✅ Showing the AI chat box at the bottom of the runtime window',
    '默认显示（总体协调引擎入口）：用自然语言给剧组下指令，下一拍推演就生效。勾上则隐藏这一栏':
        'Shown by default (the coordinator entry point): give the crew instructions in plain '
        'language and they apply from the next beat. Tick to hide this column',
    '做不了的操作会如实告诉你去「天机」里手动做；右上角「❓ 帮助」与 F11 照旧可用':
        'Whatever it cannot do, it will tell you to do by hand in "Tianji"; "❓ Help" at the top '
        'right and F11 still work',
    '对剧组下指令（例如：让导演多写点感情戏 / 整体节奏放慢一点）':
        'Give the crew an instruction (e.g. more romance from the director / slow the whole pace '
        'down)',
    '这一章写成了小说（{n} 字）': 'This chapter was written as a novel ({n} characters)',
    '思考过程': 'Thinking',
    '执行结果': 'Result',
    '人物决策': 'Character decision',
    '导演挑事': 'Director stirs trouble',
    '群聊': 'Group chat',
    '改写法': 'Revise style',
    '派活': 'Assign work',
    '当天剧本': "Today's script",
    '剧本验算': 'Script check',
    '展开/收起小说': 'Expand/collapse the novel',
    '展开/收起剧组消息': 'Expand/collapse crew messages',
    '展开': 'Expand',
    '收起': 'Collapse',
    '（还没有开口 —— 模型正在读提示词…）': '(not talking yet — the model is still reading the prompt…)',
    '\n\n……（正在生成，会自己往下长）': '\n\n… (generating; this grows by itself)',
    '（这一步没有产出正文）': '(this step produced no prose)',
    '更新剧组消息失败': 'Could not update the crew message',
    '剧组消息起头失败': 'Could not start the crew message',
    '点开看这一步在做什么（出工中=思考过程，已完成=执行结果）':
        'Open to see what this step is doing (working = thinking, done = result)',
    '正在停止… · {d} · {k}s': 'Stopping… · {d} · {k}s',
    '{s} · 本轮已 {n} 秒': '{s} · {n}s into this round',
    '{s} · 正在：{d}（已 {k} 秒）· 本轮已 {m} 秒': '{s} · now: {d} ({k}s) · {m}s into this round',
    '⚠ 这两个旋钮**互不影响**：调任务规训不会动文笔，反过来也一样。'
    '「不许替别人说话」这一类**世界法则**，两个旋钮都碰不到。':
        '⚠ These two dials **do not affect each other**: changing story discipline leaves the '
        'prose alone, and the other way round. **World laws** like "do not speak for others" are '
        'out of reach of both.',
    # 三个外部服务的长说明（原样出现在折叠块里）
    # [EN] The three long notes for the external services (shown verbatim in the collapsed blocks)
    '这些配置**来自 MuMuAINovel** —— 一个独立的「写小说」后端程序，跑在本机，'
    '由本项目通过 HTTP 调用。许可：GPL-3.0；本地说明见 novelservices/MuMuAINovel/服务说明.md。上游：':
        'These settings **come from MuMuAINovel** — a standalone novel-writing backend running on '
        'this machine and called over HTTP. Licence: GPL-3.0; local notes in '
        'novelservices/MuMuAINovel/服务说明.md. Upstream:',
    '打开后，导出『小说版本』会改走 MuMuAINovel：据「小说原文 + 推演过程」重写每一天。'
    '默认**关**（导出沿用内部整理稿）；打开后若服务没起/超时/写空，会自动退回内部整理稿并记明原因，'
    '不会把这一天的戏弄丢':
        'When on, exporting the novel version goes through MuMuAINovel instead: each day is '
        'rewritten from "the novel text + the simulation log". Default **off** (export uses the '
        'internal manuscript). If the service is down, times out or returns an empty chapter, it '
        'falls back to the internal manuscript and records why, so that day is never lost',
    '这些配置**来自 PlotPilot**（墨枢）—— 一个独立的「叙事引擎内核」，跑在本机，'
    '由本项目通过 HTTP 调用。它擅长在长篇跨度里维护人物一致性、因果链、伏笔与故事线结构，'
    '用来给**剧作者/编剧**设计『这一章该发生什么』。许可：Apache-2.0 + Commons Clause；上游：':
        'These settings **come from PlotPilot** — a standalone narrative-engine core running on '
        'this machine and called over HTTP. It keeps character consistency, causal chains, '
        'foreshadowing and story structure across long spans, and designs "what should happen in '
        'this chapter" for the **screenwriter**. Licence: Apache-2.0 + Commons Clause; upstream:',
    '这些配置**来自 PenShot** —— 一个独立的「AI 导演 / 分镜引擎」，跑在本机，'
    '由本项目通过 HTTP 调用。它把一段剧本拆成镜头分解（分镜）、情绪评分、配乐建议、可视化时间线，'
    '用来给**导演**安排『这一场怎么拍』。支持 **OpenAI 兼容**端点'
    '（Moonshot / DeepSeek / 硅基流动 / 本地 Ollama…）。上游：':
        'These settings **come from PenShot** — a standalone AI director / storyboard engine '
        'running on this machine and called over HTTP. It breaks a script into shot lists, '
        'emotion scores, music suggestions and a visual timeline, arranging "how this scene is '
        'shot" for the **director**. Works with **OpenAI-compatible** endpoints (Moonshot / '
        'DeepSeek / SiliconFlow / local Ollama…). Upstream:',
})

# ── 协调引擎（剧组指令）与画面上的两种图例 ──
# [EN] The coordinator (crew instructions) and two image legends
_ZH2EN.update({
    '我做不了这件事，请去「天机」里手动操作（或在「起笔」对话框里写明这一轮的意图）。':
        'I cannot do that — do it by hand in "Tianji" (or state this round\'s intent in the '
        '"Pen to paper" dialog).',
    '做不了这件事，请去「天机」里手动操作': 'I cannot do that — do it by hand in "Tianji"',
    '已处理': 'Done',
    '没收到任何内容': 'Nothing came back',
    '暂时做不到：{x}': 'Cannot do that right now: {x}',
    '处理失败': 'Handling failed',
    '处理时出错了：{e}': 'Something went wrong while handling it: {e}',
    '（当前没有在场人物信息）': '(no cast information right now)',
    '已更新全局故事走向（对所有 Agent 生效）':
        'Global story direction updated (applies to every agent)',
    '已更新「{n}」的行为指令': 'Updated the behaviour instruction for "{n}"',
    '「{n}」当前不在场，没法给 TA 下实时指令（TA 不在这一拍里）':
        '"{n}" is not on stage right now, so no live instruction can be given (not in this beat)',
    '已记下「{n}」的指令（下次 TA 在场时生效）':
        'Instruction for "{n}" recorded (takes effect next time they are on stage)',
    '已更新「{n}」的实时行为指令': 'Live behaviour instruction for "{n}" updated',
    '书名不匹配': 'Book title mismatch',
    '门（缺口 + 门扇）': 'Door (opening + leaf)',
    '道路（从这里通到那里）': 'Path (from here to there)',
    # ★ 2026-10-26：拾卷里"勾还在、书没了"那一条的提示（见 `_ask_delete_saves_multi`）
    # [EN] 2026-10-26: the notice for "ticks remain, the book is gone" in Pick a Volume
    '这本书已经不在拾卷里了 —— 勾选已清空（要找回它去最左边的「回收站」）。':
        'That book is no longer in Pick a Volume -- the ticks have been cleared '
        '(to get it back, use the recycle bin tab at the far left).',
    # ★ 2026-10-26：导演介入对话框改成"给多个方向"之后的两句问话与「这次不用」。
    #   ⚠ 这三条是**变量传参**（`_fmt` 里 `t(s)`）进来的，`tools/i18n_check.py`
    #     扫不到（它只认 `t('字面量')`）⇒ 必须手工登记，否则英文界面会露中文。
    # [EN] 2026-10-26: the two questions and "not this time" for the director-intervention dialog
    # [EN] after it became "offer several directions". ⚠ These arrive **through a variable**
    # [EN] (`t(s)` inside `_fmt`), which `tools/i18n_check.py` cannot see (it only matches
    # [EN] `t('literal')`) -- so they must be registered by hand or the English UI leaks Chinese.
    '剧情停滞太久，导演提了几个能破局的方向 —— 挑一个，'
    '或者自己写一件要发生的事。':
        'The story has stalled for too long. The director proposed a few directions that could '
        'break the deadlock -- pick one, or write what you want to happen.',
    '剧情停滞太久，这次没提出方向 —— 你可以自己写一件要发生的事，'
    '或者让它接着演。':
        'The story has stalled for too long and no directions were proposed this time -- write '
        'what you want to happen, or let it keep going as it is.',
    '照现在的方向接着演，别再问这件事':
        'Keep going in the current direction and stop asking about this',

    # ★ 2026-10-27：拆书**能拆专业书**之后新增的界面文案。
    #   ⚠ `kind.label()` 那三条（`小说` / `专业书 / 资料书` / `混合（小说 + 考据）`）
    #     是**报告里**用的，界面下拉只给了前两种（"混合"是自动判出来的结果，不该让人手填）。
    # [EN] 2026-10-27: UI strings added when Book Breakdown learned to split **reference books**.
    # [EN] ⚠ The three from `kind.label()` are used in **reports**; the dropdown only offers the
    # [EN] first two ("mixed" is an automatic verdict, not something a user should pick).
    '这是本什么书': 'What kind of book is this',
    '自动（让程序判）': 'Auto (let the app decide)',
    '小说': 'Novel',
    '专业书 / 资料书': 'Reference / non-fiction',
    '混合（小说 + 考据）': 'Mixed (fiction + scholarship)',
    '① 判类型': '① Detecting the book type',
    '① OCR 识别（扫描件）': '① OCR (scanned pages)',
    '判类型：{w}': 'Book type: {w}',
    '类型由用户指定为「{k}」（不是判出来的）': 'Type set by you to "{k}" (not detected)',
    '判成「{k}」—— 既像叙事也像考据。本次按**素材线**拆（专业书那套）；'
    '若想要写法线，把类型填成「小说」再拆一次':
        'Detected as "{k}" -- it reads both like a story and like scholarship. This run uses the '
        '**material line** (the reference-book one); for the craft line, set the type to "Novel" '
        'and run it again',

    # ★ 2026-10-27：删小说**连带它的存档**（用户：「前者是包含后者的」）。
    # [EN] 2026-10-27: deleting a book **cascades to its saves** (user: "the former contains the
    # [EN] latter").
    '回收站里属于它的 {n} 轮存档也会**归到这本书下面**'
    '（不再单独列出；恢复这本书时它们一起回来）。':
        'Its {n} runs already in the recycle bin are **absorbed into this book** (no longer listed '
        'separately; they come back together when you restore the book).',
    '已把《{name}》移到回收站（连它在回收站里的 {n} 轮存档一起归到这本书下面）：{path}':
        'Moved "{name}" to the recycle bin, together with its {n} runs already there (absorbed '
        'into the book): {path}',
    '回收站里属于它的 {n} 轮存档也一起删掉 —— 书没了，'
    '那些存档本来也**恢复不回去**。':
        'Its {n} runs in the recycle bin are deleted too -- with the book gone they '
        '**could not be restored anyway**.',
})



# ★ 2026-10-28：摄取输入框的回车行为 + AI 往来对话框分页 + 系统面板那几行。
# [EN] 2026-10-28: the ingestion input's Enter behaviour + pagination in the "AI exchange" dialog
# [EN] + the rows in the System panel.
_ZH2EN.update({
    'Ctrl+Enter 发送失败': 'Ctrl+Enter send failed',
    'MOCK 模式': 'MOCK mode',
    '‹ 上一页': '‹ Previous',
    '下一页 ›': 'Next ›',
    '回车换行 · Ctrl+Enter 发送': 'Enter = new line · Ctrl+Enter sends',
    '第 {p} / {n} 页 · 共 {c} 发':
        'Page {p} / {n} · {c} exchanges in total',
    '程序自己的状态：是不是 MOCK 模式、记忆检索方式、今天的 Token 用量，'
    '三座外部创作服务在不在跑（运行 / 未运行），'
    '以及导演 / 合规这些小开关现在是不是开着。':
        "The program's own state: whether MOCK mode is on, how memory retrieval works, today's token "
        "usage, whether the three external creation services are running (running / not running), "
        "and whether the small switches (director / compliance) are on.",
})

# ★ 2026-10-31：托盘图标 + 「关窗到底做什么」。
# ⚠ 「归　去」里那个是全角空格（U+3000），key 必须与源码**逐字**一致 ——
#   写成半角空格就查不到，英文界面会直接露出中文（覆盖率判据能抓到）。
# [EN] 2026-10-31: the tray icon + "what closing the window really does".
# [EN] ⚠ The 「归　去」 key uses an ideographic space (U+3000); it must match the source
# [EN] character for character or the English UI falls back to Chinese.
_ZH2EN.update({
    '小说世界AI模拟': 'Novel World AI Simulator',
    '显示主界面': 'Show main window',
    '完全退出': 'Quit completely',
    '完全退出程序': 'Quit the program',
    '（图标没挂上，关窗会直接退出）':
        '(icon not attached -- closing will exit)',
    '窗口与托盘': 'Window & tray',
    '点 × 与「归\u3000去」时': 'When clicking × or "Leave"',
    '只关闭窗口（图标留在右下角）':
        'Close the window only (icon stays in the tray)',
    '选「只关闭窗口」时：窗口收起来，但程序继续运行、'
    '任务栏右下角（托盘）的图标还在 —— 点一下图标、'
    '或右键选「显示主界面」，界面就回来了。':
        'With "close the window only": the window tucks away but the program keeps running, and '
        'the icon stays in the notification area (tray) at the bottom-right of the taskbar -- click '
        'it, or right-click and pick "Show main window", and the UI comes back.',
    '★ 「归\u3000去」也按这一项：选了「只关闭窗口」，它就不再退出程序。'
    '想真的退出，用托盘右键菜单里的「完全退出」（那一项**永远**退出）。':
        '★ "Leave" follows this setting too: with "close the window only" it no longer quits. To '
        'really quit, use "Quit completely" in the tray right-click menu (that entry **always** '
        'quits).',
    '⚠ 选了「只关闭窗口」但图标没能挂上时，一律按「完全退出」处理 —— '
    '没有图标就没地方把窗口叫回来。':
        '⚠ If "close the window only" is selected but the icon could not attach, the app behaves '
        'as "quit completely" -- with no icon there is nowhere to bring the window back from.',
    '● 托盘图标已挂上：关窗后它还在，点它或右键「显示主界面」就回来':
        '● Tray icon attached: it stays after closing; click it or right-click "Show main window" '
        'to come back',
    '○ 托盘图标没挂上：这一项会按「完全退出」执行（图标起来之后才生效）':
        '○ Tray icon not attached: this setting acts as "quit completely" (it takes effect once '
        'the icon is up)',
    '重新挂上托盘图标': 'Re-attach the tray icon',
    '托盘图标已挂上，现在可以选「只关闭窗口」了':
        'Tray icon attached -- you can pick "close the window only" now',
    '托盘图标还是没挂上（详情见日志）':
        'The tray icon still could not attach (see the log for details)',
    # ── 日志/异常里那几句（同样会走到界面的消息条）──
    # [EN] The log/exception lines (some of them also reach the snack bar).
    '找不到托盘图标文件': 'Tray icon file not found',
    '托盘模块不可用（关窗会直接退出）':
        'Tray module unavailable (closing will exit)',
    '托盘图标没挂上（关窗会直接退出）':
        'Tray icon not attached (closing will exit)',
    '接管窗口关闭事件失败': 'Failed to intercept the window close event',
    '托盘菜单命令没能送回界面':
        'The tray menu command could not be handed to the UI',
    '托盘图标点击没能送回界面':
        'The tray icon click could not be handed to the UI',
    '从托盘显示主窗口失败': 'Failed to show the main window from the tray',
    '托盘菜单动作失败：{k}': 'Tray menu action failed: {k}',
    '收进托盘前的自动落盘失败': 'Autosave failed before going to the tray',
    '关窗决策失败，按完全退出处理':
        'The close decision failed; treating it as a full quit',
    '收进托盘（程序还在运行）': 'Tucked into the tray (the program is still running)',
    '收进托盘失败，改为完全退出':
        'Tucking into the tray failed; quitting instead',
    '起托盘图标失败': 'Failed to start the tray icon',
    '托盘菜单：完全退出': 'Tray menu: quit completely',
    '程序还在后台运行 —— 点右下角的图标就能回来':
        'Still running in the background -- click the icon at the bottom-right to come back',
})


# ══════════════════════════════════════════════════════════════════
#  「花费与优化」页签（2026-11-01）
# [EN] The "Cost & Tuning" tab (2026-11-01)
# ══════════════════════════════════════════════════════════════════
#  用户：「这个报告是否可以在天机里有一个Tab…智能分析…深度优化」。
#  这一页的报表口径与命令行脚本**同一份**（`llm/cost_advisor.py`），
#  所以两边的说明文字也一起翻。
# [EN] User: "can this report live in a Tab in Tianji ... smart analysis ... deep pass".
# [EN] Its numbers come from the same code as the CLI (`llm/cost_advisor.py`), so the
# [EN] wording is translated together.
_ZH2EN.update({
    '**钱花在哪、还能怎么省**：按用途列出输入/输出/缓存命中/花费，上面两颗按钮可以叫模型来分析（配置 / 换模型）和给软件层的改法。这一页有自己的一份日志（`logs/cost_advisor.log`）。':
        '**Where the money goes, and how to cut it**: input / output / cache hits / cost per '
        'purpose. The two buttons above let a model analyze it (config, model swaps) and '
        'suggest software-level changes. This page keeps its own log '
        '(`logs/cost_advisor.log`).',
    '{ph}完成：用 {m}，{s} 秒。结果已存档到 logs/cost_advice/，这一页的流水在 logs/cost_advisor.log。':
        '{ph} done: used {m}, {s}s. The result is archived under logs/cost_advice/; this '
        "page's log is logs/cost_advisor.log.",
    '{ph}没成功：{e}':
        '{ph} failed: {e}',
    '{p}\u3000命中 {h}\u3000输入 {i}\u3000摊到 {s} 的花费面':
        '{p}\u3000hit {h}\u3000input {i}\u3000accounts for {s} of the spend',
    '「深度优化」会把本程序的上下文拼装方式（前缀顺序、去重、缓存）也告诉模型，要它给**软件层**的改法 —— 那些改不动的话，它只能提"少写点"，那是废话。':
        'The deep pass also tells the model how this program assembles context (prefix order,'
        ' dedup, caching), so it proposes **software-level** changes -- without that it can '
        'only say "write less", which is useless.',
    '不能一键应用（{m}）—— 去对应页签手动改':
        'Cannot apply in one click ({m}) -- change it on the matching tab by hand',
    '不能应用：{m}':
        'Cannot apply: {m}',
    '为什么：{w}；预计：{e}':
        'Why: {w}; expected: {e}',
    '主力档（最准）':
        'Top tier (most accurate)',
    '低命中项（命中率 < {h} 且量 >= {m} token）—— 值得看一眼，但不一定是病：短 prompt 天生命中率低；真正能省的是「每拍一字不变的规则段排在末尾」那一种。':
        'Low-hit entries (hit rate < {h} and volume >= {m} tokens) -- worth a look, but not '
        'necessarily a defect: short prompts naturally hit little; the real win is "a '
        'constant rules block sitting at the end".',
    '便宜档（最省）':
        'Cheap tier (most economical)',
    '全部历史':
        'All time',
    '写入失败：{m}':
        'Write failed: {m}',
    '写完立刻生效（写在 .env 里）；本窗口里对应的控件也会一起改，免得你下次点「保存」又把它盖回去。':
        'Takes effect immediately (written into .env); the matching control in this window is'
        ' updated too, so your next "Save" does not put the old value back.',
    '分析失败':
        'Analysis failed',
    '分析用哪档模型':
        'Model tier for analysis',
    '刷新':
        'Refresh',
    '占比':
        'Share',
    '只换这一档的模型，写完 .env 立刻生效（下一次调用就用它）。':
        "Only this tier's model changes; written into .env and used by the next call.",
    '命中厂商缓存 {c} = {h} ｜ 合计 ¥{cost}':
        'Provider cache hit {c} = {h} ｜ total ¥{cost}',
    '命中率':
        'Hit rate',
    '常见原因：模型没配好 / 网关不支持 JSON 模式 / 这一档模型太弱。换一档再试，或去「AI模型配置」测一下。':
        'Usual causes: model not configured / the gateway does not support JSON mode / this '
        'tier is too weak. Try another tier, or test it under "AI Model Config".',
    '应用':
        'Apply',
    '打不开日志：{e}':
        'Cannot open the log: {e}',
    '打开「花费与优化」页（范围 {d}，分析档 {t}）':
        'Opened the "Cost & Tuning" page (range {d}, analysis tier {t})',
    '把上面的账、当前配置、可换的模型一起发给模型，回一份结构化建议：改哪个配置、换哪个模型。**每次只调 1 次**（输入约 2~4 千 token，账记在 `usage.db` 里）。':
        'Sends the bill above, the current config and the switchable models to the model, and'
        ' asks for structured advice: which config to change, which model to switch to. '
        '**Exactly one call per run** (about 2-4k input tokens, recorded in `usage.db`).',
    '换模型 · {t}':
        'Model swap · {t}',
    '换过去':
        'Switch',
    '改哪里、怎么改：{h}':
        'Where and how to change: {h}',
    '改配置 · {k}':
        'Config · {k}',
    '日常档（推荐）':
        'Daily tier (recommended)',
    '智能分析':
        'Smart analysis',
    '智能分析（1 次调用）':
        'Smart analysis (1 call)',
    '模型这次什么建议都没给出 —— 换一档再试。':
        'The model gave no advice this time -- try another tier.',
    '次数':
        'Calls',
    '正在{ph}…（用{m}，通常 10~40 秒）':
        'Running {ph}… (using {m}, usually 10-40s)',
    '没有任何低命中项。':
        'No low-hit entries.',
    '深度优化':
        'Deep pass',
    '深度优化（软件层建议）':
        'Deep pass (software-level advice)',
    '登记表里没有「{w}」这个模型 —— 先在「AI模型配置」里加一条':
        'The registry has no model called "{w}" -- add one under "AI Model Config" first',
    '确认换模型？':
        'Switch the model?',
    '确认改这一项？':
        'Confirm this change?',
    '结论':
        'Conclusion',
    '统计范围':
        'Range',
    '花费':
        'Spend',
    '花费与优化':
        'Cost & Tuning',
    '花费体检':
        'Cost checkup',
    '读数失败：{e}':
        'Cannot read the numbers: {e}',
    '调用 {n} 次 ｜ 输入 {i} ｜ 输出 {o} ｜ 输入/输出 = {r:.1f} 倍':
        '{n} calls ｜ input {i} ｜ output {o} ｜ input/output = {r:.1f}x',
    '软件层面 · {t}':
        'Software level · {t}',
    '输入':
        'Input',
    '输出':
        'Output',
    '这一步只改配置；改完可以再点一次「智能分析」看新账。':
        'This only changes the config; run "Smart analysis" again to see the new bill.',
    '这一页的日志：{p}（记：打开、每次分析、每次应用）':
        "This page's log: {p} (page opens, every analysis, every apply)",
    '这一页看的是 `usage.db`（软件根目录），每次真调用一行：输入、输出、命中缓存、花费。**数字全部由数据库算，不调模型**。与命令行 `tools/report_llm_cost.py` 是同一份报表。':
        'This page reads `usage.db` (program root), one row per real call: input, output, '
        'cache hits, cost. **Every number is computed by the database, no model call.** It is'
        ' the same report as the CLI `tools/report_llm_cost.py`.',
    '这个时间段里还没有记录 —— 跑一次推演之后这里就有数了。':
        'No records in this range yet -- run a simulation once and numbers will appear here.',
    '钱花在哪':
        'Where the money goes',
    '预计：{e}\u3000风险：{r}':
        'Expected: {e}\u3000risk: {r}',
    '（现在）':
        '(now)',
    '在场人物决定这一拍做什么、说什么（最贵的一步）':
        'What each present character does and says in this beat (the priciest step)',
    '人物开口说一句台词':
        'A character says one line of dialogue',
    '同场多人时说一句（群聊轮转的一拍）':
        'One line in a multi-character scene (one turn of group chat)',
    '给每个前台人物排今天这一天的打算':
        "Each foreground character's plan for the day",
    '人物反思：攒够重要性才触发一次':
        'A character reflects: fires once enough importance accumulates',
    '评估这一段到底推进了没有':
        'Did this stretch actually move the story forward?',
    '从大纲建进度节点表':
        'Build the progress milestones from the outline',
    '把这一天写成叙述文字':
        'Write the day out as narration',
    '生成两三个候选开局':
        'Generate two or three candidate openings',
    '写当天的故事正文':
        "Write the day's story prose",
    '写当天的剧本（能拍的分场分拍）':
        "Write the day's screenplay (shootable scenes and beats)",
    '把刚过去的一天压成一条前情提要':
        'Compress the day that just ended into one recap',
    '把后堂那边的动静压成一批摘要':
        'Summarise what happened backstage in one batch',
    '把较早的上下文压成两三句':
        'Compress older context into two or three sentences',
    '把一批老记忆压成两三句':
        'Compress a batch of old memories into two or three sentences',
    '把整段没铺开的段落重写一遍':
        'Rewrite a flat paragraph that never opens up',
    '从文档里抽出结构化设定':
        'Extract structured settings from documents',
    '判这本书是什么类型':
        'Detect what genre this book is',
    '从正文提取风格卡':
        'Extract a style card from the prose',
    '把写出来的正文对齐回章节结构，找出漏写错位':
        'Align the prose back to the chapter structure and find gaps',
    '按缺口清单让模型把材料补上':
        'Fill the material gaps from a checklist',
    '给设定做一遍体检，出诊断文本':
        'Health-check the settings and write a diagnosis',
    '按作者说的一句话修订设定':
        "Revise settings from the author's one-line instruction",
    '把作者的一句话解析成要改什么的结构化指令':
        "Parse the author's sentence into a structured edit instruction",
    '合规检查：有没有不该写的东西':
        'Compliance check: anything that must not be written',
    '把中文注释翻成英文（开发者工具）':
        'Translate Chinese comments to English (developer tool)',
    '拆书·粗扫：一批章节先过一遍':
        'Book intake, skim: one pass over a batch of chapters',
    '拆书·精读：挑出来的几章逐章细读':
        'Book intake, deep read: the picked chapters, one by one',
    '拆书·归纳：把读完的变成可复用的素材条目':
        'Book intake, digest: turn what was read into reusable material',
    '为这本书推断各职位的项目级定制':
        "Infer this book's project-level customisation for each crew role",
    '连戏检查：时间、物件、称呼、状态对不对得上':
        'Continuity check: time, props, forms of address, states',
    '剧组里你自己加的那个职位在干活':
        'The custom crew position you added is working',
    '画当天那张地图：今天这几场戏在哪、什么位置':
        "Draw today's map: where this day's scenes sit",
    '写当天这一章（转写材料 + 定点修句子毛病）':
        "Write today's chapter (transcribe plus targeted sentence fixes)",
    '群演：门外的人和事':
        'Extras: the people and events outside the door',
    '逐句挑毛病，点名哪几句该怎么改':
        'Go sentence by sentence: which lines need fixing and how',
    '定这一场该有哪件物件、哪件要反复出现':
        'Decide which props this scene has and which must recur',
    '剧本定稿前空走一遍：哪一拍谁做不到':
        'Dry-run the screenplay: which beat nobody can actually play',
    '考据：名物、制度、称谓站不站得住':
        'Research: do the objects, institutions and titles hold up?',
    '收工复盘：剧情总结 + 问题 + 后续意见':
        'End-of-day review: summary, problems, what to change next',
    '上屏前逐条读：是不是人话、接不接上文':
        'Read every line before it goes on screen: human? continuous?',
    '三方会审：为该推进的故事补局部设定':
        'Joint review: patch local settings for the story that must advance',
    '这一场的声音层：环境音、静默、转折':
        'The sound layer: ambience, silence, turns',
    '把定稿的分拍拆成镜头清单':
        'Break the final beats into a shot list',
    '人物衣着、随身物、仪态（进出图提示词）':
        'Costume, carried items, bearing (feeds image prompts)',
    '这一页的「智能分析」（点一次就记一笔）':
        'This page\'s "Smart analysis" (one ledger row per click)',
    '这一页的「深度优化」（点一次就记一笔）':
        'This page\'s "Deep optimisation" (one ledger row per click)',
    '试发一条最小请求：这个模型名现在能不能用':
        'Send a minimal request: does this model name work right now?',
    '判据自己造的假账（自检用，不是真花费）':
        'Fake rows written by the criteria (self-check, not real spend)',
    '判据真调一次模型，验对话链路（自检用）':
        'The criteria call the model once to test the dialogue path (self-check)',
    '判据用的探针：量试拍范围（自检用）':
        'Criteria probe: measure the trial-shoot scope (self-check)',
    '（这个代号还没登记说明）':
        '(no description registered for this code yet)',
    '描述':
        'Description',
    '导出 CSV':
        'Export CSV',
    '已导出：{p}':
        'Exported: {p}',
    '每几拍给在场人物各派一件此刻该推进的事':
        'Give every present character one thing worth advancing, every few beats',
    '导演对某个事件的处置（挑事、接住、还是放过）':
        'How the director handles an event (provoke, catch, or let it go)',
    '生成两三个剧情走向候选（卡住时给你的那个选择框）':
        'Offer two or three plot directions (the choice box when things stall)',
    '验算当天的剧本：前后接不接得上':
        "Verify the day's screenplay: does it connect end to end?",
    '一次考据：名物、制度、称谓查得对不对':
        'One research pass: do the objects, institutions and titles check out?',
    '手册问答：回答「这个功能在哪、怎么用」':
        'Manual Q&A: where is this feature and how do I use it',
    '审稿一遍：贴设定、贴风格、节奏，低分就重写一次':
        'One review pass: on-setting, on-style, pacing; rewrite once if the score is low',
    '生成故事文档':
        'Generate the story document',
    '生成推演之后的写作指导':
        'Generate the writing guide that follows a run',
    '生成这一轮运行报告':
        "Generate this run's report",
    '把合订本整理成连贯的小说稿':
        'Turn the compiled manuscript into a coherent novel draft',
    '润色 Agent 走一步（改到"收尾"或"问作者"为止）':
        'One step of the polishing agent (until "wrap up" or "ask the author")',
    '润色时回头查一遍：漏了？改坏了？越权了？':
        'While polishing, look back: missed anything? broke anything? overreached?',
    '分层创作第 0 层：把推演抽成全书骨架（先分章）':
        'Layered composition, layer 0: turn the run into a whole-book skeleton',
    '分层创作第 1 层：把一章拆成节拍':
        'Layered composition, layer 1: split a chapter into beats',
    '分层创作第 2 层：把节拍写成正文草稿':
        'Layered composition, layer 2: write the beats out as a draft',
    '分层创作第 3 层：在草稿上补细节（只改质地，不动事实）':
        'Layered composition, layer 3: add detail to the draft (texture only)',
    '生成推演世界那张底图（概览）':
        'Render the world atlas overview image',
    '生成某一处地点的底图':
        'Render the atlas image for one place',
    '画地图之前，先查一下这栋建筑该长什么样':
        'Before drawing the map, look up what this building should look like',
    '（旧版留下的代号，现在没有这一步了）':
        '(a code left over from an older version; no such step any more)',
    '（测试时留下的代号，不是真花费）':
        '(a leftover test code, not real spend)',
})
