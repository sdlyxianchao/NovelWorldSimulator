# UI 测试

本目录包含 GUI 的自动化测试。

## 测试脚本

| 脚本 | 说明 |
|------|------|
| `test_gui_headless.py` | Headless 模式组件测试（不启动窗口） |
| `test_dialogs_integration.py` | 对话框集成测试（真实启动窗口，逐个点开所有对话框） |
| `test_ingest_flow.py` | 摄取流程测试（进度回调 / AI 优化 / 冻结落盘，MOCK 零网络） |
| `run_all.py` | 运行所有 UI 测试 |

另有真机验证脚本在 `../tools/`（会截图 + 写 JSON 证据）：

> **开发期的「尺子」与「眼睛」在 `../developers/`**（2026-10-06 从 tools/ 分出）：
> 像素探针 `probe_*`、几何量测 `measure_*`、观感预览 `preview_*`、排查
> `audit_screens` / `find_hardcoded_zh`、以及说明书插图与示例文件的生产线
> （`shoot_manual` / `make_samples`）。**它们是给人看的工具，不是断言集**，
> 所以不参与 `run_all_verifications.py` 的批量回归。
> 下面表里带「（工具）」的那几支，路径已写成 `developers/`。

| 脚本 | 说明 |
|------|------|
| `tools/verify_ingest_ui.py` | 开卷摄取对话框：进度条 / 实时日志 / AI 对话 / 完成后进主界面 |
| `tools/verify_ingest_scan.py` | **开卷必须读整个文件夹**（用户 2026-10-06：「为何现在只读一个文件」）：★★A1 = 文件夹里放一份旧版残留的 `.ingest_cache.json`（匹配除一个之外的全部文件）→ 仍必须读到**全部**（旧实现只读到 1 个，必红）· A3 只改一个文件后重扫仍是全部 · A5 递归子文件夹 · A6 该跳过的一个不少（点号开头 / `~$` / `AI补全设定.md` / 不支持的扩展名）· A7 归类修正表仍生效 · A9 管线端到端 `run_ingest` · B1/B2 真机日志与同意门面板报出的文件数 == 实际数 | `ingest_scan_*.png` / `ingest_scan_report.json` |
| `tools/verify_main_screen.py` | 运行界面：默认留空（禁止词扫描）+ 命令栏间距像素测量 |
| `tools/verify_main_flags.py` | 运行界面**随全局开关自适应**（4 组开关组合 + 小窗口场景） |
| `tools/verify_resume_menu.py` | 开始菜单「回卷」：顺序、灰化、点击跳转 |
| `tools/verify_run_modes.py` | 运行模式：三模式 × 中英，前台显示修饰名、后台存变量值 |
| `tools/verify_installer.py` | **安装器**：三平台安装/卸载产物、.lnk 回读断言、--dry-run 不落盘、安全边界 |
| `tools/verify_icon.py` | **图标**：配色对比（亮度/色相）、单主色占比、logo 连通性、16px 可辨识 |
| `tools/verify_opacity.py` | **界面透明度**：叙事区/开始界面/对话框真的透出背景；夹紧与下限规则；天机滑块落盘 |
| `tools/verify_ui_common.py` | 不是测试，是上面几个脚本共用的量测工具（纯色背景 + 合成色 + 像素量测） |
| `tools/verify_script_output.py` | **剧本式叙事**：15 种词条往返、三套渲染、**同时性的四种情形**、出场退场 diff、RunLoop 端到端、旧格式兼容、真机 GUI 渲染 |`script_*.png` / `script_report.json` |
| `tools/verify_mcp_skills.py` | **MCP + 技能**：真起进程走 initialize/tools-list/tools-call、协议错误码、只读性、技能路由与附带脚本。**不弹窗口**，纯命令行 |
| `tools/verify_export.py` | **导出**：装订两种模式（素材册/可读稿）的行级差异、截断、版本自增、空运行、账单统计、调度层端到端、开关读取、真机按钮与对话框（走真实点击路径） | `export_*.png` / `export_report.json` |
| `tools/verify_portraits.py` | **人物肖像**（v1.16 起：一律文生图 / 开卷生成一次 / 不支持就用文字）：提示词、项目级落盘与跨轮复用（第二轮不再调模型）、清单、不支持时明说+文字代替、hook 只认项目里那张、SceneBuilder 的文字兜底与整轮去重、真机中栏出字/出图 | `portrait_*.png` / `portrait_report.json` |
| `tools/verify_image_mode.py` | **对话插图四模式**（关闭/ASCII 画/PNG 矢量图/全彩文生图）：项目文件往返、四档产出、上下文影响画面、去重、回退链、书斋下拉与保存落盘、中栏字符画渲染 | `image_mode_*.png` / `image_mode_report.json` |
| `tools/verify_story_depth.py` | **讲故事别空转 + 每轮开场**（4.2.4）：在场按「这一刻在这儿」（未登场/去了别处都不算）、登场推进（`debut_day` 到日子才出场）、客流随天气/时辰/场所变、群演三闸门与到期回收、★**提示词不再教人闲着**（真机日志里「比如擦紫砂壶」被抄 565 遍）且三层目标在位、★★反空转闸（三层目标全空 + wait 要留痕）、开场字段规格（只列在场 / **秘密不进开场** / 未登场只给天数 / brief 档 / 导出给读者的版本剃掉未登场）；★**每轮开场是「中栏里的一张卡」**（4.2.4，2026-10-06 用户改的）：**不弹对话框**、**不等确认**、点了「开始推演」就直接开跑、卡片是这一轮的**第一条**、★卡片上的文本**就是** `开场.md` 里的（同一份，不许两套格式）、★★**标记色法**证明这张卡真的画在屏幕上（控件树里有 ≠ 看得见）；命令 `opening` 重看 = 再推一张卡（不是又弹一个框） | `story_depth_opening.png` / `story_depth_opening_card.png` / `story_depth_report.json` |
| `tools/verify_story_flow.py` | **中栏的故事体**（4.2.2，2026-10-06）：台词给**叙述动词**（`主角压低声音，对阿枝说：「…」`，不再是 `人名：`）、动作写成人名+动作（不带冒号）、心声/回想是人话、出场退场写成叙述、事件剥掉类型、已出场的人**不出句子**；★★故事正文里**一个场记标记都没有**（`〔心声〕`/`〔出场〕`/`· 动作`），而机制标注 `※` 与结构标记 `〔切至·地点〕` **刻意保留**；★分段（叙述并成段 / 台词独立成段 / 事件独立成段 / 段不过长 / 台词与标注不缩进）；★★`group()` 是**纯函数**；★★真机：中栏段落控件数 **＝** `group()` 段数（不多不少）、至少一段装了多句、**重进界面后切分完全一样** | `story_flow_chat.png` / `story_flow_report.json` |
| `tools/verify_run_output_style.py` | **运行界面的输出样式**（4.2.2/4.2.3）：样式表覆盖全部词条类型、叙述类配了段内样式（`SPAN_STYLE` 的键**恰好**等于 `JOINABLE`）；真机走一遍运行并验分隔符、状态条、按类型分层 | `run_style_*.png` / `run_style_report.json` |
| `tools/verify_run_status_bar.py` | **运行界面底部那条状态小字**（4.2.3）：`_status_view` 每个分支（含 ★**暂停优先于细粒度 key** —— 顺序写反屏幕上就是「运行中」）、★★**没在跑时不挂秒表**（回归「未运行 · 已 1791256630 秒」）、★★**秒表真的在走**（6 秒轮询取样，`max ≥ 2` 且数字变过 —— ticker 没调用点时是一串 0）、同状态连续上报不重置秒表、停下来秒表拿掉、ticker 起落（`_status_task` 启动后又清回 None）；真机走启动故事对话框真实开跑，并用**标记色法**证明那条胶囊真画在屏幕下半屏、靠左、不铺满 | `run_status_bar_probe.png` / `run_status_bar_report.json` |
| `tools/verify_scrollbars.py` | **各栏的常驻滚动条**（4.2.3/4.5.1/4.10，2026-10-06 用户：「回答问题的地方回答区也需要滚动条，开卷的AI部分左侧和右侧也需要滚动条，运行窗口的输出对话的地方也需要滚动条，还有别的地方你看下我有遗漏吗」）：★这些条是**自己画的**（控件级/主题级 `thumb_visibility=True` 在这个 Flet 构建里都不生效，实测车道里一个像素都没有），所以判据必须**像素取证** —— 把 thumb 临时染成品红（标记色法，只动颜色不动几何），断言它「画出来了」（≥20 像素、整条 ≥24px）且「画得对」（**是 ≤8px 宽的竖条**、落在右半侧）；覆盖帮助「问个问题」回答区 · 开卷左右两栏 · 运行界面中栏 + 左右侧栏 · 拾卷三栏 · 消息列表，另有 A 组纯逻辑（条的结构 4px、`reset`/`sync` 语义、车道 ≥ 条宽）；★★**拾卷/消息框没有 `auto_scroll`**，所以另判一条「打开就自己画了条，不需要先滚一下」（预载内容时那句 `reset` 是它们唯一的出路） | `scrollbars_*.png` / `scrollbars_report.json` |
| `developers/mutate_scrollbars.py` | **反例法**（工具）：11 处变异逐一打断 —— 六个界面各自"完全没有条"（★忠实改法是**把条从版面里换回原始控件**：`content=chat_bar` → `content=chat_col`；让条去包一个空壳控件**抓不到**，因为 `Stack([空壳, thumb])` 照样挂在版面上、像素判据照样量得到它）、条永远不显示、条画成一整块、车道归零、拾卷/消息框装载完不重判。全部确认能红，还原后必须 0 条红 | `developers/mutate_scrollbars.py` 的 stdout |
| `tools/verify_font.py` | **随程序附带的字体**（霞鹜文楷，SIL OFL 1.1，可商用可分发，2026-10-06 用户选的）：文件在 `assets/fonts/` 且 magic 是 TrueType · `bundled_font_files()` 给「族名 → 相对 assets 的路径」· `UI_FONT` 跟随 · 界面/标题/正文**零系统宋体残留** · 等宽场景仍是 Consolas · `start_gui()` **显式**给 `assets_dir`；★★真机**认字形**（拿截图里的墨迹与 PIL 用三个候选字体渲染的同段文字归一化后逐像素比，平均绝对差最小的那个就是它）——被测行必须最像霞鹜文楷，两个阳性对照（SimSun / 雅黑）必须各自认对。⚠ 判据的选法本身踩了三版：中文串**宽度无区分度**（汉字全角 1em）、拉丁串宽度**模棱两可**（霞鹜 565 vs 雅黑 555），只有认字形靠得住 | `font_ui.png` / `font_report.json` |
| `tools/verify_window_max.py` | **启动即最大化**（用户 2026-10-06 的原话走了一圈：「为何默认不全屏了？」→「我希望默认打开全屏才对」→**「我可能有的地方说错了 我是想默认最大化 不是默认全屏把屏幕都占满」**，最终定为**最大化**、全屏留给 F11）：★A2 = 启动 2.0 秒时把 `maximized` 关掉（模拟平台还原），**3.4 秒必须已被拉回** —— 只有"重试盯到 3.2 秒"的实现才过得去（旧的两段重试必红，实测打回 `(0.35, 1.55)` 后 A2/A3 真的红了）· ★A4 = **默认不是全屏**（别把任务栏盖掉）· ★A5 = 用户按过 F11 之后启动兜底收工 · B = F11 进出全屏后仍是最大化且页面尺寸不是 1440 初值 | `window_max_verify.png` / `window_max_verify.json` |
| `tools/verify_minimap.py` | **小地图**（4.2.3.1，2026-10-06：「用矢量图的形式每次都重新画一下（切换场景的时候绘制）…根据故事里的设计尽可能的反应其布局…要求使用AI动态绘制」）：★★**矢量**——渲染器的字形集合与交给 AI 的白名单**完全相等**（少一个会静默掉进"屋"那个默认分支）；★★**每次切场景重画**——**标记色法**把"当前地点"染成品红，换地点后**质心必须移动 > 20px**（这是"重画"的硬证据）；★**AI 按设定摆位**——坐标夹取、**模型编出来的地点一律丢掉**、漏掉的**补回来**、失败/抛异常都退回兜底、缓存往返、**只写运行文件夹**；行为判据（非源码哨兵）：关掉 `MINIMAP_AI` **一次模型都不调**、连续 4 次切场景**没有任何模型调用且用的是同一个布局对象**（"切场景 ≠ 重算布局"）。像素用**纸底染独占色自定位**画布范围，再在其中数墨迹 | `minimap_*.png` / `minimap_report.json` |
| `developers/mutate_minimap.py` | **反例法**（工具）：11 处变异逐一打断 —— 拿掉纸底、不给"当前地点"垫朱砂圈、两个字形集合对不上、`_on_scene` 不重画、重画时不用新地点、每次切场景都重算布局、不拦编造的地名、不补漏项、兜底不看"河/渡"、失败不兜底、开关失效。全部确认能红，还原后必须 0 条红。⚠ 两条经验：`_reindent` 会**保留原行缩进再拼**（body 里多带一层就是 IndentationError，退出码 1 且**一条判据都不打**，看着像"判据没抓到"）；`image_gen/*.py` 是 **CRLF**，锚点行尾要探测、别硬编码 | `developers/mutate_minimap.py` 的 stdout |
| `tools/verify_run_control.py` | **运行会话**：装配层（含空设定集必须报错）、`RunLoop.run` 未被属性遮蔽的回归断言、状态机、**暂停中停止**、收尾落盘与自动导出、真机三按钮与启动故事对话框（走真实点击路径，真的开跑） | `run_*.png` / `run_control_report.json` |
| `tools/verify_repair_writeback.py` | **AI 补全并回写引用文件夹**（4.5.3）：清单该列/不该列什么、落点选择、"**不许写**"的五道护栏（越界/非文本/隐藏文件/阶段不对/项目已存在）、只追加不改写、`.bak` 备份、转码不动换行、归类表让扫描真的生效、补全文档不进素材、并进设定只填空不覆盖；真机走「跳过」与「同意」两条路（含像素证据） | `repair_*.png` / `repair_writeback_report.json` |
| `tools/verify_world_rules.py` | **顶级规则**（6.6）：文件名识别（含"规则优先于设定"与不误伤其他分类）、**原文照录**（逐字相等，含 Markdown 结构）、AI 提取条目只在没有规则文档时兜底、两者都有时只用原文、畸形输入归一化、`world_prefix()` 里排最前且**截断但不概括**、装配读回（YAML 与手改 md 两种形态）、真机开卷落盘 → 决策/台词/导演 prompt 里真的有，以及"**没写规则时不许凭空多一段**"的反例 | `world_rules_report.json` |
| `tools/verify_sim_depth.py` | **推演深度四项**（不弹窗）：① 双记忆 —— 相关性的二元组分词（旧实现按单字，几乎恒命中）、recency 走**故事时间**、前情提要落盘与升序读回；② 导演死旋钮 —— 张力曲线回落（否则事件注入被永久关死）、高潮日强制挑事、事件重复度拦截、停滞检测走故事时间；③ 速度 —— 决策并发的**耗时取证**（串行 0.6s vs 并发 0.3s）；④ 计划链 —— `make_plan` 真的被调用并进 prompt；另有 `world_prefix` 缓存与 persona 分层 | `sim_depth_report.json` |
| `tools/verify_help_qa.py` | **帮助面板：两个选项卡 + 「问个问题」**（4.10）：说明书切段（带 `A › B` 父级路径）、中文正例命中对应章节、**无关问题不命中**（宁可说"没写"）、英文问题在英文手册里命中、全是疑问词时不检索、prompt 写死"只根据这些内容/没写就说没写/不许凭常识补功能"且句句可查、★**检索为空时一次请求都不发**；多轮 —— 历史进 prompt、**轮数有上限**、只有当前问题说不清时才借上一轮去检索。真机：选项卡数量与标签、**切页两张截图真的不同**、输入框与「发送」按钮、点示例问题后出现**问 + 答两个气泡**、★气泡分左右（**标记色法像素取证**：作者气泡在右半边、AI 在左半边）、★★第二次请求的 prompt 里带「此前对话」 | `help_tab_*.png` / `help_bubble_marker.png` / `help_qa_report.json` |
| `developers/measure_dialogs.py` | **对话框尺寸**（工具，不是断言集）：在纯色背景下量六个对话框的外框宽高，断言「宽 620±6」「高 440~700」「**各对话框高度不全相同**」（都一样高 = 又被 `expand` 撑满了） | `measure_*.png` / `measure_report.json` |
| `developers/measure_controls.py` | **控件几何**（工具）：对话框里控件的宽度/高度/字号，断言「宽度都落在栅格（520/256/168）」「控件等高同字号」「**框高/字号 ∈ [1.6, 2.6]**」「**标签/正文 ≥ 1.0**」「控件高 ≤ 26」。**读控件树，不走像素**（输入框纸白与纸面只差 6 个色阶，像素量不出来） | `controls_*.png` / `measure_controls_report.json` |
| `developers/probe_field_height.py` | **控件高度探针**（工具）：把 `SET_H` 依次设成 30/28/26/24/22，各截一张图量**框高 / 框上方标签带 / 框内正文带**——回答"还能不能接着压小"。**改控件高度前先跑它**（实测：Flet 严格认 `height`，框高 1:1 联动；22 时框内只剩 19px 开始局促，24 是可读下限） | `probe/field_h*.png` |
| `tools/verify_background.py` | **背景图管线**：裁 16:9 → 4K → WebP、柔化程度、柔化背景上的文字对比度 |
| `developers/preview_look.py` | 配色预览：开始界面/向导/天机/书斋/运行界面/摄取对话框各截一图 |
| `developers/preview_narrative.py` | 运行界面**卡片式输出**预览：两幕完整剧本 → 整屏截图 + **中栏放大图**，并打印卡片高度/卡间距（给人看） | `narrative_cards*.png` |
| `developers/audit_screens.py` | 把每个界面/对话框渲染一遍，导出全部可见文本与控件类型 |

## 运行方式

```bash
# 运行所有 UI 测试
python tests/ui/run_all.py

# 单独运行组件测试
python tests/ui/test_gui_headless.py

# 单独运行对话框集成测试
python tests/ui/test_dialogs_integration.py

# 真机验证（会弹窗口、截图、写证据 JSON）
python tools/verify_ingest_ui.py
python tools/verify_main_flags.py                     # 开关自适应
python tools/verify_run_modes.py                      # 运行模式修饰名
python tools/verify_installer.py                      # 安装器（桌面图标/开始菜单）
python tools/verify_icon.py                           # 图标配色与可辨识性
python tools/verify_opacity.py                        # 界面透明度（真背景图）
python tools/verify_background.py                     # 背景图管线（文生图 → 界面用图）
python tools/verify_mcp_skills.py                     # MCP 服务器 + 技能库（不弹窗口）
python tools/verify_script_output.py                  # 剧本式叙事（逻辑 + 真机）
python tools/verify_export.py                         # 导出（--logic-only 可跳弹窗）
python tools/verify_image_mode.py                    # 对话插图四模式（--logic-only 可跳弹窗）
python tools/verify_portraits.py                     # 人物肖像：文生图/复用/文字代替（--logic-only 可跳弹窗）
python tools/verify_run_control.py                    # 运行会话：起停/暂停/启动故事（--logic-only 可跳弹窗）
python tools/verify_run_status_bar.py                 # 底部状态条：文案/秒表/ticker/像素位置（--logic-only 只跑 A 组 10 项）
python tools/verify_story_flow.py                    # 中栏小说体：句子化 / 分段 / 不出现场记标记（--logic-only 只跑 A 组 25 项）
python tools/verify_story_depth.py                    # 讲故事别空转 + 每轮开场卡片（--logic-only 只跑 A 组 36 项）
python tools/verify_repair_writeback.py               # AI 回写引用文件夹（--logic-only 只跑护栏那 34 项）
python tools/verify_world_rules.py                    # 顶级规则：识别/原文照录/注入 prompt（不弹窗）
python tools/verify_sim_depth.py                      # 推演深度：双记忆/导演旋钮/速度/计划链（不弹窗）
python tools/verify_help_qa.py                        # 帮助面板：两个选项卡 + 问个问题（--logic-only 只跑检索与多轮那 21 项）
python developers/measure_dialogs.py                       # 对话框尺寸量测（改尺寸后跑）
python developers/measure_controls.py                      # 控件几何量测（改高度/字号后跑）
python developers/probe_field_height.py                    # 控件高度探针（想知道"还能压多低"时跑）
python developers/preview_narrative.py                     # 运行界面卡片输出预览（放大图）
python developers/preview_look.py                          # 配色预览截图
NWS_LANG=en python tools/verify_main_screen.py     # 英文界面
```

### 并行回归（分组 + 多实例，2026-10-06）

64 支脚本**串行**要跑 11 分钟，但大部分时间是在**等**（等 Flutter 客户端起来、
等脚本里那几拍 `asyncio.sleep`），不是 CPU 忙。这些脚本互相独立
（各自 `isolate_projects_dir()` 到临时目录），所以可以分组并行：

```bash
.venv\Scripts\python.exe tools/run_all_verifications.py            # 并行（默认）≈ 2.5 分钟
.venv\Scripts\python.exe tools/run_all_verifications.py --serial    # 回到一次一支
.venv\Scripts\python.exe tools/run_all_verifications.py --jobs 8    # 调真机并发（默认 6）
.venv\Scripts\python.exe tools/run_all_verifications.py --groups    # 只列分组
.venv\Scripts\python.exe tools/run_all_verifications.py --only verify_minimap,verify_font
```

**三组，写在脚本顶部的白名单里**：

| 组 | 是什么 | 并发 |
|---|---|---|
| `LOGIC` | 纯逻辑，不起 Flet 窗口（20 支） | 8 |
| `GUI` | 真机 Flet 窗口（42 支） | 6 |
| `ALONE` | **必须独占**，一次一支（2 支） | 1 |

> ⚠ **新加 `verify_*.py` 必须登记进某个组**，否则回归器直接报错退出（退出码 3）。
> 不静默塞进某个组 —— 那是"测试悄悄变慢/变脆"的经典来源。

**为什么 `ALONE` 是必须的**（实测踩出来的，别再试）：

- `verify_taskbar_icon`：用 `find_app_hwnd()` → `FindWindowW(None, title)` **按窗口标题**
  找自己的窗口。并行时多个实例标题一样 → 找到**别人**的窗口、读到别人的图标 →
  判据随机变红。实测 6 路并行时它从"全部通过"变成"有失败"。
- `verify_icon` / `verify_taskbar_icon`：**故意重写**共享产物
  `assets/images/icon*` + `assets/app_icon.*`（它们就是要验"换了图标之后产物跟不跟着换"）
  → 两个实例抢同一批文件。

**并行之后结论还可信吗？** 两个保障：

1. **`--recheck`（默认开）**：并行阶段**失败**的脚本会**串行**再跑一遍。
   两次都红 = 真红；串行绿 = **并行不稳**，报告里单列成 `⚠并行不稳`，并建议加进 `ALONE`。
   （一次红就说"产品坏了"是错的，一次绿就说"没事"也是错的。）
2. 改过分组/并发之后，拿 **`developers/probe_parallel.py`** 复核：同一批脚本
   串行/并行各跑一遍，逐支比退出码与结论行。整轮比对用
   **`developers/compare_verifications.py`** 比两份 `all_verifications.txt`。

**每支脚本有自己的一份日志**：回归器会给子进程设 `NWS_LOG_DIR`
（`logs/_parallel/<脚本名>/`）。因为日志文件名只精确到**分钟**，
同分钟启动的多个进程本来会写**同一个文件** —— 于是"往日志里数条目"的判据
（`verify_dialogue_log` B 组：`日志 +16 / 实际 9`）当场错乱。见 `logger.log_dir()`。

### 判据的**退出码**：红了必须退出码非 0（2026-10-28）

回归器**只看退出码**（`ok = code == 0`）。⇒ 一支判据哪怕断言红成一片，
只要退出码是 0，它在回归里就是**绿的** ——
「红灯打出来也没人看得见」⇒ 那条覆盖**从来没被证明过**。

⚠ 这个病**不会自己暴露**：判据自己跑一遍是绿的、回归也是绿的、
报告上写着「N/N 通过」，一切看起来都对。
⇒ 只有**故意把某条断言改坏**再真跑，才看得出它会不会红。

**统一出口**：`tools/verify_exit.py` 的 `finish()`（不是断言集，是公共库，
所以在 `run_all_verifications.py` 的 `HELPERS` 里排掉）。

```python
import sys
from pathlib import Path
APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP / 'tools'))
from verify_exit import finish          # noqa: E402

report = {'checks': [{'name': 'A1 …', 'ok': True, 'detail': ''}]}
sys.exit(finish(report, out_path=APP / 'reports' / 'xxx_report.json'))
```

三条规矩：

1. `main()` **返回 int**（不要写成 `-> None`）；
2. `__main__` 里 `sys.exit(main())`；
3. **真机判据**（要 `page` 的）也一样：`code = 0 if rep['ok'] else 2`，
   `await shutdown(page, code=code)`，**并且 `return code`** ——
   ⚠ 只把 `code` 交给 `shutdown()` 而**不 return**，那么**无头跑**（`main(None)`）
   时退出码恒为 0 ⇒ 又一支恒绿判据。

**自查**：`tools/verify_exit_codes.py`（**ALONE 组**）把每支**纯逻辑**判据
**改坏一处再真跑一遍**，看退出码是不是非 0。
⚠ 它会**改判据自己的源码** ⇒ 只能独占，别和任何东西并行。
⚠ 静态扫 AST **不可靠**（`return 0 if report.get('ok') else 1` 静态判断不了它跟失败状态有关
⇒ 大面积误报）⇒ **唯一可靠的口径是真跑一次红的**。

```bash
.venv\Scripts\python.exe tools/verify_exit_codes.py                  # 全量（几分钟）
$env:NWS_EXIT_ONLY='verify_x,verify_y'; .venv\Scripts\python.exe tools/verify_exit_codes.py   # 定点
```

三条容易踩的：

1. **不能碰真机脚本** —— ALONE 组里混着会起真机窗口的（`verify_splash_boot`
   会**真的把整个程序启动一遍**）⇒ 体检器按**源码里有 `ft.run(`** 排掉它们。
2. **「改不坏」不能当「验过了」** —— 检出器**从源码自己推断**哪个函数是断言记录器
   （函数体里有 `X.append({... 'ok': ...})`），不是硬编码名单；
   否则 43 支用 `rec(...)` 的判据会被记成"跳过" ⇒ 那条覆盖**从没被证明过**。
   **转发壳**型（自己一条断言都没有，只 `raise SystemExit(x.main())`）另走一路：
   改它转发出去的那个调用（⚠ 填 **`1`** 而不是 `False` ——
   `SystemExit(False)` 的退出码是 **0**，会被读成"恒绿" ⇒ **假结论**）。
3. **「脚本崩了」≠「判据变红」** —— 抛 Traceback 时退出码也是非 0，但那时红的是
   "脚本崩了"，**证明不了那条覆盖能红** ⇒ 单独记成「崩了」，不混进「会红」。
4. **还原用 `os.replace`，别用「拷贝回去 + 删备份」** —— 那个 `unlink` 会被安全策略
   当"批量删除"拦下（实测：体检跑到第 43 支时进程被杀，磁盘上留着改坏的判据）。

> **实测（2026-10-28）**：**121 支纯逻辑判据全部实测会红** ——
> 恒绿 0 支、跳过 0 支、崩了 0 支。
> （这一轮当场抓出 **7 支恒绿**：`verify_ui_probe_paging` · `verify_style_control` ·
> `verify_setting_layers` · `verify_crew_onduty` · `verify_chapter_split` · `verify_must_on`
> —— 最后一支是**本轮自己刚写的** ⇒ 这个病是自己带来的。）

## 测试内容

### test_gui_headless.py

- 开始界面组件（菜单项）
- 导入向导组件（FilePicker、TextField、Dropdown、Switch）
- 全局设置组件（配置读取、容器创建）
- 项目设置组件（Slider、ProgressRing）
- 对话框创建（AlertDialog）
- 按钮回调（点击、悬停）

### test_dialogs_integration.py

实际启动 Flet 应用并构建所有对话框，捕获运行时错误：

- 应用初始化
- 开始界面-开卷向导
- 开始界面-拾卷
- 开始界面-天机（全局设置）
- 开始界面-书斋（项目设置）
- 菜单项处理函数（开卷、拾卷、天机、书斋）
- 开卷向导-步骤切换
- 天机-保存按钮
- 书斋-保存按钮
- 主界面

测试结果写入 `logs/ui_test_result.txt`。

### test_ingest_flow.py

MOCK 模式下跑完整摄取管线（零网络、零成本）：

- 进度回调单调递增、13 个阶段齐全、最后 100%
- LLM 事件成对（request/response 带完整文本）
- 设定摘要 / AI 体检 / 按指令改设定 / 空指令短路
- 冻结 9 个设定文件、`.nwsproj`、运行文件夹、`scan_projects` 回读

### verify_installer.py

安装器会往用户桌面和开始菜单写东西，这类改动不能靠「看着像对的」就交付，
但也**绝不能为了测试就往真实桌面放图标**。所以：

- 所有真实写入都用 `--dest-root` 指向临时目录
- Windows 的 `.lnk` **真建真读**：建完用 PowerShell 回读 TargetPath /
  IconLocation / WorkingDirectory / Description，逐项断言
- 真的跑一遍 `setup.exe` / `uninstall.exe`（用 `--dry-run`，所以不动真实桌面）
- macOS / Linux 分支在本机强制切平台跑一遍，真的把 `.app` 包和 `.desktop`
  写出来再校验内容与权限位（`.icns` 依赖 macOS 的 `sips`，别处会优雅降级）
- 安全性断言：`--purge` 的删除目标里**绝不能出现小说项目目录**

### verify_icon.py

图标是唯一没法靠肉眼确认的资源（本机模型读不了图片），而要求又很具体
（单一主色 + 明确的 logo、两色对比明显、中国色）。所以全部转成可测断言：

- 对不透明像素做 **2-means 聚色**，得到实际的底色与记号色（不是照抄期望值）
- **对比明显** = 亮度 ≥3:1 **或** 色相差 ≥120°（月白这类近无彩色记号只能靠亮度）
- **单一主色**：底色占比要够大（≥60%），不能是花图
- **logo 明确**：记号必须是**一个连通块**（最大块 ≥90%），散点噪点不算 logo
- **16 / 32 / 48px 可辨识**：缩下去后记号占比仍在 12% / 10% 以上
- 产物齐全：`icon.ico` 含 16~256 多尺寸、`app_icon.png` 与 `icon_256.png` 逐字节一致
- 顺带导出 `assets/screenshots/icon_preview.png`：两套配色 × 各尺寸（浅底 + 深底各一行）

### verify_mcp_skills.py

MCP 服务器是**独立进程**，光读代码没法确认它能用，所以这个脚本真的起进程说话：

- **握手**：真的发 `initialize`，断言回了 `protocolVersion` 与 `serverInfo`
- **列工具**：`tools/list` 的工具清单必须与预期**完全一致**；每个工具都要有描述，
  且 `inputSchema.type == "object"`（否则 LLM 不会用）
- **真调每个工具**：造一个临时小说项目当靶子（设定集 + 运行文件夹 + 每日正文 +
  事件卡），断言返回里**真的出现预期内容**（如人物卡里有「秘密」、检索命中「设定集/」）
- **协议错误码**：未知方法必须回 `-32601`，缺必填参数必须回 `-32602`
- **业务失败用 `isError`**：项目不存在时给可读提示，而**不是**协议错误 —— 后者会让客户端崩
- **stdout 纯净**：每一行都必须是合法 JSON（往 stdout 写杂字会破坏协议）
- **时辰换算的正确性**：19 点 = 戌时、23 点归子时、**戌时 +7h → 第 4 天丑时**（跨日进位）、
  负小时倒推。这几条是 LLM 最容易算错的地方，所以当断言写死
- **只读性**：扫 `mcp/servers/*.py`，**不允许出现任何写盘调用**（`write_text` / `mkdir` /
  `open(...,'w')` / `unlink` / `rmtree`）—— 对应「程序永不反写项目文件夹」
- **占位符**：`{python}` / `{app_dir}` / `{project_dir}` / `{env:NAME}` 都真的解析对
- **客户端整合**：走 app 真正用的 `MCPClient`（`list_tools` / `call_tool`）与
  **考据通道**（技能层命中 `技能/…`、MCP 层命中 `MCP/…`）
- **技能**：注册表加载 8 个、frontmatter 完整、**没有单字触发关键词**、
  8 句自然话都能路由到正确技能、无关问题不误命中、附带脚本能跑通且算得对

### verify_script_output.py

`--logic-only` 可跳过弹窗部分（调试快得多；正式验证要跑全量）。

**同时性**是这一层最容易做错的地方——一个 tick 里三个人各做各的，拼成三行就是
"先后"，而事实是"同时"。所以断言四种情形：

- 单人做事 → **不该**出现并行轨（一个人做事说"同时"反而怪）
- 同场多人 → 一条并行轨、轨数 = 人数，且"谁在开口"标出来
- 异地有人做实事（move/interact/有台词的 speak）→ 要 `切至` + `切回`
- 异地只是在发呆/变脸 → **不该**切（否则每 tick 刷一遍转场标记）

**「不是一直说话」**：断言 `speakers()` 与 `actors()` 分开统计；并断言
「想事情」渲染成**心声**而不是动作（早期版本把它写成
`· 动作 主角：（若今晚走不走得成…）`，读起来像自言自语）。

**落盘能读回**：Markdown 反解无损（词条类型/数量/可见性/语气/锚点）、
JSON 边车优先、**旧纯文本格式返回空幕**（由界面回退纯文本，不硬拆散文）。

真机部分把一份剧本渲染进中栏并断言：幕首/旁白/对白/动作/心声/同时/切至/本幕依据
都上了屏，`场外`/`别处` 标出来了，图片是**真的 `ft.Image` 控件**，
**间距量测仍通过（4px）**，英文界面下 `Meanwhile`/`off stage` 也翻了，
空项目仍显示占位提示（不预填编造的剧本）。

### verify_export.py

`--logic-only` 可跳过弹窗（快得多；正式验证要跑全量）。

**「只删不改」用行级子集关系证明**，不用字数阈值：
素材册保留过程痕迹、可读稿剃掉它们，断言
`可读稿的正文行 ⊂ 素材册的正文行` 且行数更少。
阈值断言会掩盖改动，子集关系不会。（第一次跑就是栽在阈值上——而且
还犯了「拿 set 的长度和 list 的长度比」的错。）

**中途导出**：数据里第 4 天**故意不落盘**，断言稿子与报告里都不出现它——
证明"没跑完就导出"拿到的是干净的半截稿。

**报告先有硬数据**：断言 `运行报告_v1.md` 里「## 1 运行概览」与「## 账单」
来自程序统计（天数、账单表格、次数），且**在 MOCK 下也出得来**。
同时断言设计稿的固定入口 `运行小结.md` 仍同步存在。

**空运行不崩**：一天都没落盘时，稿子写「尚无任何已落盘的天」，调度不抛异常。

**真机**：断言运行界面出现📤按钮 → 打开对话框（三个分组标题 + 四类产物名都在）
→ **走真实点击路径**（调 `btn.on_click(None)`，不是直接 await 内部协程）
→ 结果列出现 ✓ 与产物路径 → `<运行文件夹>/导出/` 下真的落了两个文件。

> 采集可见文本时注意：Flet 1.0 里 `FilledButton("导出")` 的第一个位置参数
> 就是 `content`，于是 `content` 是**裸字符串**而不是 `ft.Text`。
> 只认 `ft.Text` 的采集器会把所有按钮文字漏掉（这里踩过）。
> 对话框不在 `page.controls` 里，用 `app._export_ui['dlg']` 直接遍历。

### verify_run_control.py

`--logic-only` 可跳过弹窗（快得多；正式验证要跑全量）。

要验的不是「按钮画出来了」，而是**链路真的通了**：
设定集 → 装配世界 → 起会话 → 叙事出现在中栏 → 暂停真的冻结 → 停止真的收尾。

**回归断言（重要）**：`inspect.iscoroutinefunction(loop.run)`。
`RunLoop` 以前把运行文件夹存在 `self.run`，**把 `run()` 方法本身覆盖了** ——
`await loop.run()` 报 `'RunFolder' object is not callable`。
因为循环从没被真正跑过，这 bug 潜伏了很久。这条断言就是钉住它不许复发。

**暂停中停止**：主循环卡在 `while self._paused` 时，外面只把 `_running` 置 False
是出不来的（点了停止会一直挂着）。所以专门断言「暂停中 stop() 被接受、且真的收尾完成」。
为了让会话不自己跑到终点，数据里**不给进度表**（`is_at_end()` 对空表恒为 False）。

**真机**：断言三按钮存在、未运行时暂停/停止是禁用的 → 打开启动故事对话框
（分组标题与字段齐全）→ **走真实点击路径**（`btn.on_click(None)`）开跑 →
中栏收到实时叙事 → 暂停后按钮文字变「继续」→ 停止 → 产物落盘 → 四张截图。

> 两个环境坑：
> ① 对话框里点「开始推演」会 `CFG.save()` 把测试用的 `MOCK_LLM=true` 写进 `.env`，
>    所以脚本开头备份 `.env`、`finally` 里还原。
> ② 本机 safe-delete 守卫会在单次删除 >50 文件时 `SystemExit(1)`（`ignore_errors`
>    拦不住），所以临时目录建到系统临时区（`tempfile.mkdtemp`），
>    清理走 `VU.safe_rmtree`。

### ⚠️ 验证脚本必须**隔离项目根**，别往用户真实目录里造项目

`verify_ui_common.isolate_projects_dir(dir)` 把 `CFG.projects_dir()` 临时指到临时目录。
两个理由：

1. **别污染用户的「拾卷」列表。** 脚本都要造项目，靠收尾 `rmtree` 清；
   本机的批量删除守卫经常拦住收尾 → 夹具会一直留在用户的项目根里
   （本机曾攒下 8 个：`导出验证`／`开关自适应验证`／`回卷测试项目`…）。
2. **别让断言依赖环境。** `verify_resume_menu` 有一条「没有项目时「拾卷」该灰掉」——
   用户自己建过项目就会**假失败**（本机就这么挂过一次）。

要点：**在开界面之前就隔离**，而且隔离目录**先清一次**
（上次跑剩的夹具就在里面，会把计数带偏）。

### ⚠️ 半透明面板：量测必须走 `verify_ui_common.py`

面板现在受 `UI_OPACITY` 控制、是**半透明**的，屏幕上的实际颜色是

    alpha × 面板色 + (1 - alpha) × 背景色

水墨背景让每处位置颜色都不同，于是「找某一种颜色的连续段」这类量测**会失效**
（曾经把「叙事区改成半透明」误判成「布局坏了」，间距从 9px 跳到 561px）。

- **布局类**量测（间距、边界）→ 先用 `VU.patch_flat_background()` 换成纯色背景，
  再用 `VU.panel_rgb()` / `VU.field_rgb()` 算合成色。合成用的 alpha 是
  **从界面自己的颜色表里读的**（`C['panel']` 已是 `#AARRGGBB`），不另抄一份逻辑。
- **透明本身**只能靠真背景图验 → `tools/verify_opacity.py`：
  同一块区域在 100% 与 40% 下比较 `mean|Δ|`、`std|Δ|` 和表面 std。
- 定位面板时注意**界面上有多块颜色相近的纸**（标题块 / 菜单卡 / 对话框纸面）。
  用 `panel_bbox(..., y_from=, y_to=, min_h=)` 限制范围 ——
  我们踩过「把开始界面标题块当成对话框纸面」。纸册还是**渐变**，单一颜色定不准。

## 多实例：共享一组创作服务，谁最后关谁收尸

三座外部创作服务都**绑固定端口**（端口写在同一份 `.env`）⇒ 第二个实例只会收到
一句「已经在运行，不重复启动」⇒ **全程只有一组服务在跑**（实测：端口上已有健康
服务时 `novelservice.py start` 0.1 秒返回）。所以"每个实例各起一组"在这套架构上
**做不到**，也不是该要的（要动态端口 + 服务发现，且首次建环境 + 470MB 模型要付两遍）。

于是"主窗口退出 ⇒ 服务跟着退出"在多实例下的正确说法是：**最后一个关的人负责收尸**。

- 登记表 `logs/service_users/<pid>.use`：主程序**启动时登记**（`start_gui` 最早处）、
  **退出时撤销**（`on_disconnect`）；**判空**（一个活着的使用者都没有）才真的停。
- ★ 判空只看 **pid 死活**，不看"撤销成功没有" ⇒ 实例被强杀留下的文件**自动不算数**。
- ⚠ 判活的两个坑（都踩过）：
  ① **光能 `OpenProcess` 不算活着** —— 还有人攥着句柄时，它对**已死的**进程照样成功
    ⇒ 必须再问 `GetExitCodeProcess`（退出码 != 259 就是死了）；
  ② Windows 上**不许用 `os.kill(pid, 0)` 探活** —— 那里的 `os.kill` 走
    `TerminateProcess`，`sig=0` = **以退出码 0 终止它**。
- 两家各写死一份目录串（Python `util/svc_users.py:DIR_REL`、
  Go `launchers/services.go:svcUsersDir`）⇒ 改名必须两边一起改。

判据 `tools/verify_svc_users.py`（**22/22**，LOGIC）：登记表 / 判活 / 收尸决策 /
两边目录串。**不真起服务、不真停服务**（三家桥打桩）。
反例法 `developers/mutate_svc_users.py`（**9/9**）：把"不问还有没有别人在用"
"只停 MuMu 一家""判空出错也照停"等逐条做坏，要求**那一条**真的红。

## 说明

由于 Flet 1.0 没有内置的测试客户端，对话框集成测试通过实际启动应用并调用对话框构建方法来实现。这能在构建阶段捕获 API 变更导致的错误（如组件参数不兼容）。

## 注意事项

- 测试使用 `MOCK_LLM=true` 演示模式，不会发送真实 API 请求
  （注意 `CFG` 只读 `.env`，所以脚本内部是 `CFG.set('MOCK_LLM', 'true')`，
  设 `os.environ` 是**无效**的）
- 每次运行会生成新的日志文件到 `logs/` 目录
- `bash -n` 做语法检查时要用**相对文件名 + cwd=项目根**：
  本机的 `bash` 是 PortableGit/WSL 混合体，喂绝对 Windows 路径会直接返回 127
- Windows 上把路径拼进 PowerShell 脚本文本非常容易出事（中文、空格、长路径被折行）。
  统一走 `platform_install.ps_job()`：输入输出都经 UTF-8 JSON 文件，任何字符都安全

### ⚠️ 退出时必须关掉 Flet 窗口（否则会攒出一堆 "Working..." 孤儿窗口）

`ft.run()` 会另外拉起一个 `flet.exe` 客户端进程。脚本如果直接 `os._exit(0)`，
Python 侧退了，但**客户端会变成孤儿留在后台**，卡在启动加载页上 ——
跑几次验证就会在桌面上攒出一堆一直转圈、写着 `Working...` 的窗口。

正确写法（收尾三件套）：

```python
from util.flet_shutdown import shutdown, exit_now

# 在 async 上下文里：
await shutdown(page)      # 先 await page.window.destroy() 让客户端自己退
exit_now(0 if ok else 1)  # 再 os._exit（跳过 Flet 后台线程 join，避免脚本挂住）

# 在同步回调里（没法 await）：
exit_now(1)               # exit_now 内部会按父进程 PID 收掉本进程的 flet 客户端
```

`util/flet_shutdown.py` 除了优雅关闭，还会兜底：按
「父进程 PID = 本脚本进程」把残留的 `flet.exe` 一并 `Stop-Process`，双保险。

如果已经漏了一堆窗口，手动清：

```powershell
Get-Process -Name flet -ErrorAction SilentlyContinue | Stop-Process -Force
```
