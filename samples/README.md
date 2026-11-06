# 示例输入文件夹 · Sample input folders

六个**原创**短篇（同一个故事写了中英两版），一个题材一篇。它们是给「开卷」用的**输入文件夹**范例 —— 按说明书第 6 节的**黄金档**组织，可以直接拿一篇来试跑。

Six **original** short stories (each written in both Chinese and English), one per genre. They are example **input folders** for Import — laid out to the **Gold** standard in section 6 of the manual. Point Import at any single story folder and run it.

> 版权：全部原创，随程序分发，随便改。  Copyright: all original, shipped with the app, modify freely.

## 中文 / Chinese — `samples/zh/`

| 文件夹 | 题材 | 故事 | 一句话 |
|---|---|---|---|
| `01_悬疑单元_更漏子/` | 悬疑 · 单元剧 | 《更漏子》 | 唐代长安，一个管更漏的小吏，靠"水走得快不快"查案。每坊一桩，各自独立，暗里连成一条线。 |
| `02_玄幻修仙_借山道人/` | 玄幻修仙 | 《借山道人》 | 修真界里替人"借"东西的行当：借山、借水、借寿。借了必须还 —— 还不上的，欠痕会自己记账。 |
| `03_都市_夜班书店/` | 都市 | 《夜班书店》 | 一家 24 小时书店。凌晨三点到四点之间来的客人，都不是"随便逛逛"。店主听得见书想被读的声音。 |
| `04_历史架空_河工疏/` | 历史架空 | 《河工疏》 | 架空王朝，一位河工主簿发现盖了印的治河方案里，堤高算错了一尺。而"改"本身是死罪。 |
| `05_言情_灯花记/` | 言情 | 《灯花记》 | 江南水乡。摆渡人和绣娘一年只见一次 —— 灯节那晚的最后一趟船。 |
| `06_科幻_回声站/` | 科幻 | 《回声站》 | 深空中继站，一个守站人。最近收到的信号里，出现了他自己还没说过的话。 |

## English — `samples/en/`

| Folder | Genre | Story | One line |
|---|---|---|---|
| `01_mystery_the_water_clock/` | Mystery · Case-of-the-week | The Water Clock | Tang-dynasty Chang'an. A clerk who tends the water clocks solves crimes by asking how fast the water ran. One case per ward, each standing alone — and one thread running underneath. |
| `02_xianxia_the_mountain_borrower/` | Xianxia / Cultivation | The Mountain Borrower | In the cultivation world nothing is taken — everything is borrowed. Mountains, rivers, years of life. What you borrow must be returned, and the ledger is written on your own skin. |
| `03_urban_the_all_night_bookshop/` | Urban / Contemporary | The All-Night Bookshop | A 24-hour bookshop. Between three and four in the morning, nobody who walks in is just browsing. The owner can hear which books want to be read. |
| `04_alternate_history_the_river_memorial/` | Alternate History | The River Memorial | An invented dynasty. A junior river-works clerk discovers that the sealed flood plan is one chi short. And altering it is a capital crime. |
| `05_romance_the_lamp_flower/` | Romance | The Lamp Flower | A river town in Jiangnan. A ferryman and an embroiderer meet exactly once a year — on the last crossing of the Lantern Festival. |
| `06_scifi_echo_station/` | Science Fiction | Echo Station | A deep-space relay station with one keeper. Lately the signals coming in contain things he has not said yet. |

## 每篇里面长什么样 / What is inside one story

```
zh/<一个故事>/                     en/<one story>/
├── 设定/                          ├── setting/
│   ├── 世界观.md                  │   ├── world.md
│   ├── 顶级规则.md                │   ├── rules.md
│   ├── 地点.yaml                  │   ├── places.yaml
│   └── 人物/                      │   └── characters/
│       ├── <甲>.md                │       ├── <a>.md
│       └── <乙>.md                │       └── <b>.md
├── 大纲/                          ├── outline/
│   └── 故事大纲.md                │   └── story-outline.md
├── 伏笔.md                        ├── foreshadowing.md
└── 正文/                          └── chapters/
    ├── 第一章.md                  │   ├── chapter-01.md
    ├── 第二章.md                  │   ├── chapter-02.md
    └── 第三章.md                  │   └── chapter-03.md
```

### 为什么要**三章**正文（不是一章）

三个数决定的，都在代码里：

| 程序读什么 | 上限 | 在哪 |
|---|---|---|
| **风格卡**：从正文里学文风 | 取正文**前 4000 字** | `ingest/style.py` |
| **前情对齐**：判"哪些节点已完成" | **每章取前 1500 字**，总上限 8000 | `ingest/progress.py` |
| **起始点**：从哪个节点接着演 | 由上面"已完成节点"决定 | `ingest/progress.suggest_start_point` |

所以正文只有一章、三四百字时：风格卡**样本太薄**（学不出"章法偏好""对话占比"），
前情对齐**没有可对齐的东西**、只能给个空的前情提要，起始点**永远退回第一个节点**。
三章 × 约 1300 字 ≈ 4000 字，正好吃满前两个预算。

> 这也是"黄金档"（说明书 §6.4）写 `正文/ 第一章.md … 第N章.md` 的**原因** ——
> 这里的三章示例就是把那个标准**做成实物**给作者看。

### 大纲为什么写到 3400 字以上

| | 中文六篇 | 英文六篇 |
|---|---|---|
| 大纲体量 | **3489 – 4103 字** | **1905 – 2304 词** |

⚠ **光把大纲写长没用** —— 程序开卷时只读大纲里的「站表」，站表只渲染八个字段
（跨度 / 篇幅 / 章数 / 完成判据 / 高潮 / 选项 / 概要 / 情节线）。大纲里别的章节
（比如"故事线""篇幅规划"）**进不了模型**。所以这六篇的"厚"是**厚在站表字段里**：

- **每一站都写了「完成判据 / 高潮 / 情节线」三样**（中英两版 98 站，零缺项）。
  「情节线」是最容易被漏掉的一栏：程序明确写着"大纲里作者写了「情节线」就照抄"，
  而此前十二篇大纲里它**一处都没有**。
- **「高潮」不是「完成判据」的复述**。判据说的是"演到哪算完"，高潮说的是
  "那一瞬具体发生了什么"。判据 `tools/verify_samples.py` H5 用三道网守着：
  模板尾巴、判据被整段包进去、以及**高潮必须比判据多出实质内容**（中文新字 ≥10 / 英文新词 ≥8）。
- 另加一节 **「二、悬念的次序（读者什么时候知道什么）」** —— 按"读者知道什么"而不是
  "角色做了什么"排一遍，防止揭秘过早。
- `设定/顶级规则.md` 里都有一节 **「幽默」**（支点 → 小谎 → 反噬 → 揭穿 → 嘴硬 → 回收）。
  幽默不是"处境好笑"，是一个人的小算盘被情节撞了一下；少一环就只剩场面滑稽。

### Why each outline runs past 3400 characters

| | Chinese (6) | English (6) |
|---|---|---|
| Outline size | **3489 – 4103 chars** | **1905 – 2304 words** |

⚠ **Simply writing a longer outline gains nothing** — Import only reads the **station table**, and
the table renders eight fields only (span / length / chapters / done-when / climax / choices /
summary / beats). Other outline sections ("story line", "length plan") **never reach the model**.
So the extra weight in these six sits **inside the station fields**:

- **Every station states all three**: done-when / climax / beats (98 stations across both
  languages, nothing missing). "Beats" is the easiest one to omit: the program says outright
  "if the author wrote beats, copy them", yet all twelve outlines had **zero** of them before.
- **The climax is not a restatement of the done-when.** The criterion says "when is this station
  over"; the climax says "what concretely happens in that instant". Criterion
  `tools/verify_samples.py` H5 guards it with three nets: a template tail, the criterion being
  swallowed whole, and **the climax must add real content** (>=10 new Chinese characters /
  >=8 new English words).
- Plus a section **"2. The order of the reveals (what the reader knows, and when)"** — ordered by
  "what does the reader know" rather than "what did the characters do", so nothing is given away
  too early.
- Every `setting/rules.md` carries a **"Humour"** section (anchor -> small lie -> backlash ->
  exposure -> bluster -> callback). Humour is not "a funny situation"; it is one person's private
  calculation getting bumped by the plot. Drop a link and all that is left is slapstick.

⚠ **开卷时请选中「某一个小故事」这一层**（例如 `samples/zh/01_悬疑单元_更漏子/`），不要选 `samples/` 或 `samples/zh/` —— 那样六个故事会被当成一本书读进来。

⚠ **Point Import at one story folder** (e.g. `samples/en/01_mystery_the_water_clock/`), not at `samples/` or `samples/en/` — otherwise all six get read as one book.
