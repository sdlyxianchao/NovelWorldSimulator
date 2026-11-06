"""世界风格档案 —— 地图**按什么建筑传统画**。

## 为什么要有这一层

`image_gen/roomplan.py` 里原来把「中式店宅」写死成了代码：
分带次序 `('门','堂','厅','店','铺','院','厨','灶','房','仓','屋','阁','楼')`、
面积权重「堂/厅 2.4、院 3.0、厨 1.6」、见天词 `('院','天井','庭')` ……

那是**一本书的建筑类型**，不是通用规则。换一本西式庄园、一本赛博都市，
上面每一条都会**悄悄给出错误答案**（它不会报错，只会把宅邸画成四合院）。
这个项目反复栽在同一件事上：**规则通用、例子不通用**。

所以这里做三件事：

1. **把建筑传统做成数据**（`Style`），代码只读参数，不再含任何一国的词；
2. **判定要能说出理由**（`detect` 返回命中了哪些词），判不出来就是判不出来
   —— 不猜、不"最像的那个凑合"；
3. **判不出来时明确列出"缺什么"**（`needs_research`），交给美术 Agent 去查，
   查回来的东西落盘成 skill（`skills/地图学-*`），下次直接能用。

## 与"小说题材"的关系

`world.genre_card` 里是**题材**（悬疑/玄幻/都市…），那是"讲什么故事"；
这里要的是**世界的建筑长什么样**，两者不是一回事（古装悬疑与古装言情同一套建筑）。
所以题材只作**弱提示**（权重低），主判据来自地点名、备注、世界观文本里的实物词。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════════════════
#  一、档案的数据形状
# [EN] 1. The shape of a style profile
# ══════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Style:
    """一种建筑传统：**只放数据，不放判断**。

    每个字段都是"这种建筑里会出现的词/比例"，`roomplan` 与各尺度渲染器照着用。
    [EN] One architectural tradition: **data only, no logic**. Every field is "the words /
    [EN] proportions you would find in this kind of building", consumed by `roomplan` and the
    [EN] per-scale renderers.
    """

    key: str
    #: 给人看的名字（界面、日志、打回意见里都用它）
    # [EN] Human-readable name (UI, logs, revision notes)
    名: str
    #: 大类：`cn` / `west` / `modern` / `future` / `fantasy` —— 只用于分组与显示
    # [EN] Family: only for grouping and display
    族: str
    #: 这一族**为什么这么画**的一句话（写进图例与打回意见，让模型知道约束来自哪里）
    # [EN] One line on **why** it is drawn this way (goes into the legend and revision notes)
    依据: str

    # ── 命名词表（全是"这种建筑里会出现的实物"）────────────────────
    #: 见天（没有屋顶）的空间
    # [EN] Open-to-sky spaces
    见天词: tuple = ()
    #: 陈设（摆在房间里，本身不是房间）
    # [EN] Fixtures (placed inside a room; not rooms themselves)
    陈设词: tuple = ()
    #: 通向街面的门洞（不是房间）
    # [EN] Street doorways (not rooms)
    门洞词: tuple = ()
    #: 楼上空间
    # [EN] Upper-floor spaces
    楼上词: tuple = ()
    #: **地下**空间。★ 2026-10-26 从 `楼上词` 里拆出来的：原来 `地下车库` 命中
    #: `'地下'` 就被归成 **2 楼** —— 于是它画在二层图上，一层图上没有车库，
    #: 而"地下"和"二楼"在建筑上是相反的两件事。现在单独一类，层号用**负数**。
    # [EN] **Underground** spaces. ★ Split out of `楼上词` on 2026-10-26: `地下车库` used to match
    # [EN] `'地下'` and land on **floor 2**, so it was drawn on the second-floor plan and missing
    # [EN] from the ground plan -- while "underground" and "upstairs" are opposites. Now its own
    # [EN] class, with a **negative** floor number.
    地下词: tuple = ()
    #: 楼梯
    # [EN] Stairs
    楼梯词: tuple = ()
    #: **房间**的名字特征（含这些字的基本是空间而不是陈设）
    # [EN] Room name patterns (containing these = a space, not a fixture)
    房间词: tuple = ()
    #: 分带次序提示（同深度时谁在前）
    # [EN] Band-order hint (who comes first at equal depth)
    分带次序: tuple = ()

    # ── 比例（相对值，不是平方米）──────────────────────────────
    #: 主厅类 / 见天类 / 厨房类 / 其余
    # [EN] Main hall / open-to-sky / kitchen / everything else
    主厅词: tuple = ()
    厨房词: tuple = ()
    权重: dict = field(default_factory=lambda: {
        '主厅': 2.4, '见天': 3.0, '厨房': 1.6, '其余': 1.2})

    # ── 判定用词（拿来自动认出这种风格）────────────────────────
    #: 强证据：出现就基本可以确定（建筑构件、专名）
    # [EN] Strong evidence: near-certain when present (architectural elements, proper nouns)
    强词: tuple = ()
    #: 弱证据：只在没有强证据时参考
    # [EN] Weak evidence: only consulted when nothing strong matched
    弱词: tuple = ()
    #: 反证：出现就**大幅降低**这种风格的可能（防止"有门有窗"就算西式）
    # [EN] Counter-evidence: sharply lowers this style (so "has doors and windows" is not "Western")
    反证: tuple = ()

    # ── 画法参数（各尺度渲染器读）──────────────────────────────
    #: 屋顶做法（室内图里画"上坡线"的密度与方向）
    # [EN] Roof treatment (density/direction of the slope lines on the interior plan)
    屋顶: str = 'flat'
    #: 墙的线型：`'double'`（双线，砖石） / `'single'`（单线，木构/轻质）
    # [EN] Wall line style: double (masonry) or single (timber/light)
    墙线: str = 'double'
    #: 城市尺度默认路网：`'grid'`（棋盘） / `'radial'`（放射） / `'organic'`（自然生长）
    # [EN] Default street network at city scale
    路网: str = 'organic'
    #: 城际尺度默认地物：`'terrain'`（山河为主） / `'administrative'`（政区为主）
    # / `'nautical'`（航路图：没有政区，只有航路与港口）
    # [EN] Default features at inter-city scale
    城际: str = 'terrain'

    # ── 制图语汇（城市图 / 城际图读）──────────────────────────────
    #: **聚落等级**词表：`{4: (词…), 3: …, 2: …, 1: …}`（4 高 → 1 低）。
    #:
    #: ★★★ 为什么这一条必须按档案给（2026-10-26 实测）：等级词是**建制词**，
    #:   每个世界一套 —— 中式「州/府/县/关」、西式「castle/keep/abbey」、
    #:   现代「城区/街道」、未来「站点/基地」。原来写死一份中式表，后果是：
    #:   西幻的「刚铎」「米那斯提力斯」一个都不命中 ⇒ 全部落到 **1 级**（2.8px 小圆点），
    #:   有城墙有塔的主城，画出来跟村口渡口一样大。而"判不出来给最低级"这条纪律
    #:   本身是对的（宁可画小），错的是**词表只认一种文明**。
    # [EN] **Settlement rank** word lists per profile (4 high .. 1 low). ★★★ Why per profile
    # [EN] (measured 2026-10-26): rank words are **administrative terms**, and each world has its
    # [EN] own set -- Chinese 州/府/县/关, Western castle/keep/abbey, modern 城区/街道. A single
    # [EN] hard-coded Chinese table meant a Western citadel ("Gondor", "Minas Tirith") matched
    # [EN] nothing and fell to rank **1** (a 2.8px dot), drawing a walled capital at the size of a
    # [EN] ferry crossing. The discipline "unknown stays lowest" is right; the fault was a
    # [EN] single-civilisation word list.
    聚落等级: dict = field(default_factory=dict)

    #: 等级在图例里怎么**说**：`{4: '州府 / 都城', 3: '县城 / 关隘', …}`。
    #: ★ 等级号是抽象的（4/3/2/1），读者只认词。用中式的词去说西幻的图
    #:   （"县城"出现在城堡图上）会被当成画错了。
    # [EN] How each rank is **named** in the legend. ★ Rank numbers are abstract; the reader reads
    # [EN] words, and saying "county seat" on a Western castle map looks like a mistake.
    聚落名: dict = field(default_factory=dict)

    # ── 缺什么（判不出来 / 资料不足时，要 LLM 去查的东西）──────────
    #: 这种风格下"画得准需要知道、但我们可能没有"的条目
    # [EN] Things needed to draw it correctly that we may not have
    需查: tuple = ()

    def weight_of(self, name: str, sky: bool) -> float:
        """按本档案的比例给面积权重。**没有一国默认值**，全部来自 `权重` 表。

        [EN] Area weight from this profile's proportions; nothing is hard-coded per country.
        """
        n = str(name or '')
        if sky:
            return float(self.权重.get('见天', 3.0))
        if any(k in n for k in self.主厅词):
            return float(self.权重.get('主厅', 2.4))
        if any(k in n for k in self.厨房词):
            return float(self.权重.get('厨房', 1.6))
        return float(self.权重.get('其余', 1.2))

    def rank_of(self, name: str) -> int:
        """这个名字在**本档案**里是几级聚落（4 高 ~ 1 低）；判不出返回 **0**。

        ★ 返回 0 而不是 1，是为了让调用方分得清"这个名字在本档案里没有等级含义"
          与"它确实是 1 级（村子）" —— 前者还要看作者给的 `size`，后者不用。
        ★ 从 4 往下查：像「京师」同时含「京」与「师」这种不必管，但「州」与「镇」若
          都出现在一个名字里（「镇州」），取高的那个 —— 建制词叠用时高者优先。
        [EN] This name's rank in **this profile** (4 high .. 1 low); 0 when unknown. ★ 0 rather than 1
        [EN] so the caller can tell "no rank meaning here" from "definitely a village": the former
        [EN] still consults the author's `size`. ★ Scanned 4 downwards, so stacked administrative
        [EN] words take the higher rank.
        """
        表 = self.聚落等级 or {}
        n = str(name or '')
        if not n:
            return 0
        nl = n.lower()
        for r in (4, 3, 2, 1):
            for w in 表.get(r, ()):
                w = str(w or '')
                if not w:
                    continue
                # ⚠ 拉丁字母要**不分大小写**比：地名常写成 `Dunharrow Keep`（首字母大写），
                #   而词表里是小写 `keep` ⇒ 直接 `in` 会漏掉，等级又回落成 1。
                #   这正是"等级全部变成村口"的第二种成因（第一种是只认汉字）。
                # [EN] ⚠ Latin words must compare **case-insensitively**: a name is often written
                # [EN] `Dunharrow Keep` while the table holds lowercase `keep`, so a plain `in`
                # [EN] misses it and the rank falls back to 1 -- the second cause of "every
                # [EN] settlement is a hamlet" (the first was recognising Chinese only).
                if w.isascii():
                    if w.lower() in nl:
                        return r
                elif w in n:
                    return r
        return 0

    def rank_name(self, rank: int) -> str:
        """本档案里这个等级叫什么（图例用）；没有就返回空串。

        [EN] What this rank is called in this profile (for the legend); empty when unspecified.
        """
        try:
            return str((self.聚落名 or {}).get(int(rank), ''))
        except (TypeError, ValueError):
            return ''


# ══════════════════════════════════════════════════════════════════════
#  二、内置档案
# [EN] 2. Built-in profiles
# ══════════════════════════════════════════════════════════════════════
#  设计纪律（踩过坑，写在这里免得下次忘）：
#    · 词表只收"这种建筑里**真的有**的东西"，不收"气氛词"（"阴森""荒凉"不是构件）；
#    · **每个档案都要有反证**，否则"任何房子都有门"会让所有档案同时命中；
#    · 不追求覆盖全部，追求**判不出来时敢说判不出来**。
# [EN] Discipline (learned the hard way): only *real elements* go into the word lists (atmosphere
# [EN] words are not elements); **every profile needs counter-evidence**, or "every house has a door"
# [EN] makes all profiles match at once; and the goal is not full coverage but **daring to say
# [EN] "I cannot tell"**.
CN_SHOP_HOUSE = Style(
    key='cn_shop_house',
    名='中式店宅（沿街铺面＋院落）',
    族='cn',
    依据='沿街开门面，进内为堂屋，堂屋之后见天院子，灶间贴院；楼上是次层。'
         '这是宋元以降城镇店宅的常规格局。',
    见天词=('院', '天井', '庭', '露台', '晒'),
    陈设词=('柜', '台', '桌', '案', '炉', '灶', '床', '席', '屏', '架', '橱',
            '灯', '缸', '桶', '笼', '龛', '幔', '帘', '井', '泉', '池', '辘', '碑', '匾'),
    门洞词=('门', '大门', '门洞', '门脸', '门面', '街门'),
    楼上词=('二楼', '三楼', '四楼', '楼上', '阁楼', '顶层', '上层', '二层', '三层'),
    地下词=('地窖', '酒窖', '地下室', '地牢', '暗室'),
    楼梯词=('梯', '楼梯', '阶梯', '踏跺'),
    房间词=('屋', '房', '厅', '室', '间', '厨', '灶', '仓', '廊', '厢', '院', '门', '楼'),
    分带次序=('门', '堂', '厅', '店', '铺', '院', '厨', '灶', '房', '仓', '屋', '阁', '楼'),
    主厅词=('堂', '厅', '店', '铺'),
    厨房词=('厨', '灶', '火房'),
    # ★ 2026-10-26 补镖局与乡土民居（实测：镖局判不出、乡土民居只 1.00 勉强过线）。
    #   镖局是"前店后宅＋练武场＋马厩"，与店宅同一套骨架；乡土民居是"堂屋居中、灶房在侧"。
    # [EN] Added the escort agency and rural dwellings (measured: the agency was unrecognised and the
    # [EN] rural house barely cleared at 1.00). An agency is "shop in front, home behind, a training
    # [EN] yard and a stable", the same skeleton as a shop-house; a rural house puts the hall in the
    # [EN] middle and the kitchen to one side.
    强词=('堂屋', '天井', '照壁', '影壁', '厢房', '耳房', '倒座', '垂花', '穿堂',
          '灶间', '正房', '抄手游廊', '斗拱', '飞檐', '马头墙',
          '演武厅', '练武场', '账房', '镖局', '镖旗', '趟子手',
          '晒谷场', '猪圈', '柴房', '灶房', '水井', '磨坊', '偏房', '堂前',
          # 沿河街市（江南水乡、码头镇）
          # ★ 实测：这一组地名（河埠/石桥/廊棚/临水阁/船舫）原来靠「弄堂」蹭到
          #   **民国** 1.00 分 —— 那是误判。沿河街市是中式店宅的变体：
          #   前门临街、后门落河、骑楼廊棚遮雨，与"沿街铺面＋院落"同一套骨架。
          # [EN] Waterside market streets. ★ Measured: these names scored 1.00 as **Republican**
          # [EN] purely via 弄堂 -- a misjudgement. A waterside street is a shop-house variant: shop
          # [EN] on the street side, steps down to the water behind, an arcade for the rain.
          '河埠', '石桥', '廊棚', '临水阁', '船舫', '水阁', '骑楼', '河房',
          '码头镇', '埠头', '河沿', '水巷',
          # 江湖场景（实测：客栈/马厩/渡口/破庙/山道 判不出 —— 它们都属"沿街沿路开门"
          # 那一套骨架，只是前后换成路与渡口）
          '客栈', '酒肆', '茶棚', '破庙', '山道', '驿道', '渡头', '车马店',
          '打尖', '住店', '灶台', '柴垛',
          # ★★★ 英文：**只收中式专属的音译/专名，绝不收通用词**。
          #
          #   我第一版写了 `courtyard` / `main hall` / `kitchen` / `stable` / `well` /
          #   `guest room` —— 结果「西幻酒馆」（common room / kitchen / stable / cellar /
          #   upstairs rooms）被判成了**中式店宅**。原因很简单：
          #   `kitchen`、`stable`、`well`、`guest room`、`courtyard` 这些**中西都有**，
          #   拿它们当强词，等于"谁先列谁赢"。
          #   ⇒ 通用英文词一律不收。西式/现代场景的英文地名本来就有自己的档案认领。
          #   ⚠ 这也是"误判比兜底更坏"的第三次实证：加词的时候只想"能不能认出来"，
          #     忘了问"会不会认错"。
          # [EN] ★★★ English words: **only Chinese-specific transliterations, never generic terms.**
          # [EN] My first version listed `courtyard` / `main hall` / `kitchen` / `stable` / `well` /
          # [EN] `guest room`, and a Western tavern (common room / kitchen / stable / cellar /
          # [EN] upstairs rooms) was then judged a **Chinese shop-house**. The reason is simple:
          # [EN] kitchen, stable, well, guest room and courtyard exist in both traditions, so using
          # [EN] them as strong words means "whoever lists first wins". => No generic English words.
          # [EN] Western and modern English names are claimed by their own profiles.
          # [EN] ⚠ Third proof that "a misjudgement is worse than a fallback": while adding words I
          # [EN] only asked "will it recognise?" and forgot "will it misrecognise?".
          'siheyuan', 'hutong', 'zhaobi', 'yingbi', 'tangwu'),
    弱词=('院子', '门房', '阁楼', '条凳', '八仙桌', '炕'),
    反证=('客厅', '卧室', '浴室', '车库', '电梯', '壁炉', '沙发', '走廊', '阳台'),
    屋顶='pitched',
    墙线='single',
    路网='organic',
    城际='terrain',
    # 建制词（宋元以降的城镇体系）：州府—县城/关隘—镇驿渡—村。
    # ⚠ 单字「城」放 3 级、「州/府」放 4 级：中文里「州」几乎只作行政区，
    #   「城」可以是城墙也可以是城隍庙，所以给低一级（宁可画小）。
    聚落等级={4: ('京师', '都城', '王城', '京城', '皇城', '国都', '州', '府', '郡'),
              3: ('县', '关', '隘', '要塞', '边关', '城', '卫所', '所城'),
              2: ('镇', '驿', '集', '渡', '港', '码头', '堡', '关津'),
              1: ()},
    聚落名={4: '州府 / 都城', 3: '县城 / 关隘', 2: '镇 / 驿 / 渡', 1: '村落'},
    需查=('这种地域的民居开间习惯（面阔几间、进深几架）',
          '当地常见的院落进制（一进/二进/三进）',
          '临街铺面与居住部分的分界做法'),
)

CN_MANSION = Style(
    key='cn_mansion',
    名='中式府邸／寺观／宫殿（中轴多进）',
    族='cn',
    依据='中轴多进：门厅—正堂—内宅—后花园，两侧厢房与游廊围合。'
         '寺观与宫殿用的是同一套空间秩序（中轴、殿在中、配殿两侧、院在前后），'
         '所以共用一份画法，只换词。',
    见天词=('院', '天井', '庭', '园', '花园', '花厅', '广场', '丹墀', '演武场'),
    陈设词=('柜', '案', '几', '榻', '屏', '架', '灯', '鼎', '炉', '匾', '联',
            '瓶', '盆景', '缸', '轿'),
    门洞词=('门', '大门', '仪门', '角门', '垂花门', '后门', '侧门'),
    楼上词=('二楼', '楼上', '阁', '楼', '绣楼'),
    楼梯词=('梯', '楼梯', '阶梯'),
    房间词=('堂', '厅', '房', '院', '阁', '楼', '轩', '斋', '榭', '廊', '门', '园'),
    分带次序=('门', '仪门', '堂', '厅', '院', '房', '园', '楼', '轩'),
    主厅词=('堂', '厅', '正堂', '大厅'),
    厨房词=('厨', '灶', '厨房', '膳'),
    # ★★★ 2026-10-26 扩：**寺观、宗门、宫殿都并进来** —— 理由不是"名字像"，
    #   而是**画法相同**（中轴多进、殿在中、配殿两侧、院在前后）。
    #   实测：原来「山门/大殿/藏经阁/丹房/演武场」与「午门/太和殿/御花园/东宫」
    #   全都判成**兜底**，因为旧强词只认府邸那一套（仪门/垂花门/倒座）。
    #   立档标准是"画法不同"才新增档案，"词不同"应该并进来 —— 否则档案会无限膨胀，
    #   而每多一个档案就多一层误判风险。
    # [EN] ★★★ Expanded 2026-10-26: **temples, sect compounds and palaces all merge in** -- not
    # [EN] because the names look alike, but because the **drawing** is the same (axial, multi-
    # [EN] courtyard, hall in the middle, side halls flanking, yards fore and aft). Measured: the old
    # [EN] strong words only knew the mansion vocabulary (仪门/垂花门/倒座), so 山门/大殿/藏经阁 and
    # [EN] 午门/太和殿/御花园 all fell through to the fallback. The bar for a *new* profile is a
    # [EN] different drawing; different words belong in the same profile, or the list balloons and
    # [EN] every addition raises the misjudgement risk.
    强词=('仪门', '垂花门', '倒座', '厢房', '耳房', '后罩', '抄手游廊', '影壁',
          '绣楼', '花厅', '内宅', '外宅', '跨院',
          # 寺观／宗门
          '山门', '大殿', '藏经阁', '丹房', '演武场', '禅房', '钟楼', '鼓楼',
          '祖师殿', '弟子房', '戒律堂', '后山', '洞府', '药圃',
          # 宫殿
          '午门', '太和殿', '御花园', '东宫', '西宫', '内务府', '尚衣局',
          '朝房', '金銮', '后宫', '御书房', '廊庑', '掖门',
          # 英文（temple / palace / manor 那套）
          'main gate', 'great hall', 'side hall', 'inner court', 'rear garden',
          'cloister', 'pagoda', 'shrine', 'ancestral hall', 'scripture hall',
          'throne room', 'inner palace', 'side courtyard'),
    弱词=('院子', '天井', '游廊', '月洞门', '广场', '香炉', '经幢', '碑亭'),
    反证=('客厅', '卧室', '浴室', '电梯', '车库', '沙发'),
    屋顶='pitched',
    墙线='double',
    # ★ 2026-10-26 改：原来给的是 `radial`（放射）。理由不成立 ——
    #   中轴多进的宫殿／府邸在**城市尺度**上对的是坊市制都城（唐长安式棋盘），
    #   放射是欧洲巴洛克都城的做法。放射留给真正需要的档案（未来／环形巨构）。
    路网='grid',
    城际='terrain',
    聚落等级={4: ('京师', '都城', '王城', '京城', '皇城', '宫城', '州', '府', '郡'),
              3: ('县', '关', '隘', '要塞', '边关', '城', '卫所', '所城'),
              2: ('镇', '驿', '集', '渡', '港', '码头', '堡', '坊市'),
              1: ()},
    聚落名={4: '都城 / 州府', 3: '县城 / 关隘', 2: '镇 / 驿 / 坊市', 1: '村落'},
    需查=('府邸的进数与中轴次序（几进院落、各进功能）',
          '东西厢与正房的高下关系'),
)

WEST_MANOR = Style(
    key='west_manor',
    名='西式宅邸（主厅＋两翼）',
    族='west',
    依据='前门厅（foyer）入大厅（great hall），两侧翼楼，后部厨房与佣人区，'
         '卧室在楼上。房间靠走廊串联，不是靠院落。',
    见天词=('庭院', '花园', '露台', '阳台', '天井', 'courtyard', 'garden', 'terrace'),
    陈设词=('柜', '桌', '椅', '床', '架', '炉', '壁炉', '镜', '灯', '画', '地毯',
            '书', '钢琴', '酒', '柜橱', '梳妆'),
    门洞词=('门', '大门', '正门', '前门', '后门', '侧门', 'front door', 'portal'),
    楼上词=('二楼', '三楼', '楼上', '阁楼', 'upper', 'first floor', 'second floor'),
    地下词=('地窖', '酒窖', 'cellar', 'basement', 'dungeon'),
    楼梯词=('梯', '楼梯', '阶梯', 'stair', 'staircase'),
    房间词=('厅', '室', '房', '间', '廊', '厨', '阁', '室',
           'hall', 'room', 'chamber', 'kitchen', 'study', 'library'),
    分带次序=('门', '厅', '廊', '室', '房', '厨', '后', '楼'),
    主厅词=('厅', '堂', '大厅', 'hall', 'salon', 'drawing'),
    厨房词=('厨', '灶', 'pantry', 'kitchen', 'scullery'),
    强词=('壁炉', '沙发', '钢琴', '宴会厅', '书房', '图书室', '早餐厅', '客厅',
          'great hall', 'fireplace', 'parlour', 'parlor', 'foyer', 'balcony',
          # 维多利亚那套（实测 `drawing room/parlour/servants hall/nursery` 只 1.00）
          'drawing room', 'servants hall', 'nursery', 'morning room', 'study',
          'dining room', 'billiard room', 'library', 'conservatory', 'cellar',
          'nanny', 'butler', 'scullery', 'pantry', 'gallery'),
    弱词=('走廊', '楼梯', '卧室', '更衣室', '马厩'),
    反证=('天井', '堂屋', '厢房', '影壁', '灶间', '八仙桌'),
    屋顶='pitched',
    墙线='double',
    路网='grid',
    城际='administrative',
    聚落等级={4: ('capital', 'citadel', 'castle', 'kingdom', 'duchy', '都城', '王城'),
              3: ('keep', 'fortress', 'abbey', 'stronghold', 'barony', 'manor',
                  'gate', '堡', '要塞', '庄园'),
              2: ('town', 'village', 'mill', 'inn', 'bridge', 'ford', '镇', '村'),
              1: ()},
    聚落名={4: '都城 / 城堡', 3: '要塞 / 庄园', 2: '镇 / 村落', 1: '小聚落'},
    需查=('这种时期的宅邸主厅与翼楼的相对位置',
          '仆役区（厨房/储藏）与前厅的连接方式',
          '楼层数与卧室分布'),
)

WEST_TOWN = Style(
    key='west_town',
    名='西式城镇（街屋／中世纪—近代）',
    族='west',
    依据='沿街联排（row house / townhouse），底层临街做店铺，上层居住；'
         '街廓狭长、后侧小院。',
    见天词=('庭院', '内院', '后院', '天井', 'courtyard', 'yard'),
    陈设词=('柜', '桌', '椅', '床', '炉', '壁炉', '酒桶', '招牌', '灯', '吧台'),
    门洞词=('门', '大门', '店门', '后门', 'door'),
    楼上词=('二楼', '楼上', '阁楼', 'upper'),
    楼梯词=('梯', '楼梯', 'stair'),
    房间词=('厅', '室', '房', '间', '厨', '廊', '铺', '店', 'hall', 'room', 'shop'),
    分带次序=('门', '店', '铺', '厅', '室', '房', '厨', '院', '楼'),
    主厅词=('厅', '堂', 'taproom', 'hall'),
    厨房词=('厨', 'kitchen', '灶'),
    # ★★★ 2026-10-26：**「马厩」从强词降为弱词**。实测：中式镖局（大门/演武厅/账房/
    #   **马厩**/地牢/客房）被判成「西式城镇」—— 因为马厩、地窖这类东西**中式西式都有**，
    #   拿它当强证据必然误判。**误判比兜底更坏**：兜底至少会说"我认不出"，
    #   误判会真的画成西洋联排街屋，而用户看到的是"我的镖局呢"。
    #   强词只留**别处不可能有**的（酒馆/铁匠铺/公会/钟楼/城墙/市集/smithy/guild）。
    # [EN] ★★★ 2026-10-26: **「马厩」(stable) demoted from strong to weak.** Measured: a Chinese
    # [EN] escort agency (大门/演武厅/账房/**马厩**/地牢/客房) was judged "Western town" because a
    # [EN] stable exists in both traditions, so it cannot be strong evidence. **A misjudgement is
    # [EN] worse than a fallback**: a fallback at least says "I cannot tell", while a misjudgement
    # [EN] really draws a Western row of shops and the user asks "where is my escort agency?". Strong
    # [EN] words keep only what the other tradition cannot have.
    # ★ 2026-10-26 补西幻酒馆那一套：`common room` / `upstairs rooms` / `cellar`
    #   是中世纪—近代欧洲酒馆的标准叫法，原来一个都不认（实测判成兜底 0.20）。
    # [EN] Added the fantasy-tavern vocabulary: `common room` / `upstairs rooms` / `cellar` are the
    # [EN] standard names in a medieval-European inn and none were recognised (measured: fallback,
    # [EN] 0.20).
    强词=('酒馆', '面包房', '铁匠铺', '公会', '钟楼', '城墙', '市集', '市政厅',
          'tavern', 'inn', 'smithy', 'guild', 'market', 'town hall',
          'common room', 'great room', 'upstairs room', 'alehouse', 'brewhouse',
          'blacksmith', 'apothecary', 'chapel', 'keep', 'bailey', 'portcullis',
          'armory', 'great hall', '酒窖', '面包炉', '行会',
          # 西部（木质联排＋一条主街，与西式街屋同一种画法，所以并进来）
          'saloon', 'sheriff', '牛仔', '驿马车', 'bank', '教堂', 'hotel', '马桩'),
    弱词=('柜台', '地窖', '阁楼', '招牌', '马厩', 'stable', 'church'),
    反证=('天井', '堂屋', '厢房', '影壁', '电梯', '车库'),
    屋顶='pitched',
    墙线='double',
    路网='organic',
    城际='administrative',
    聚落等级={4: ('capital', 'citadel', 'castle', 'kingdom', 'duchy', 'city', '都城'),
              3: ('keep', 'fortress', 'abbey', 'stronghold', 'barony', 'manor',
                  'gate', '堡', '要塞', '城墙'),
              2: ('town', 'village', 'mill', 'inn', 'bridge', 'ford', '镇', '村'),
              1: ()},
    聚落名={4: '都城 / 城堡', 3: '要塞 / 庄园', 2: '镇 / 村落', 1: '小聚落'},
    需查=('这类城镇的街廓尺度（临街面宽、进深）',
          '店铺与住宅的竖向分层做法'),
)

MODERN = Style(
    key='modern',
    名='现代（公寓／办公／校园／医院／商场／机构）',
    族='modern',
    依据='核心筒或走廊串联，房间靠走廊；公共空间在大堂层；'
         '城市尺度是分级路网＋街区，不是院落。'
         '校园／医院／商场／机构共用同一套画法（平屋顶、走廊、核心筒、一处露天场地），'
         '只换词，所以是一个档案而不是四个。',
    # ★ 见天词补 `广场/操场/停机坪/靶场`：这些是**露天场地**，不是房间。
    #   不收的话它们会被当成房间排进"带"里，图上会出现"一间巨大的操场"。
    # [EN] 见天词 gains 广场/操场/停机坪/靶场: these are **open ground**, not rooms. Otherwise they
    # [EN] would be sorted into a band as a room and the plan shows "one huge playground".
    见天词=('阳台', '露台', '天台', 'roof', 'terrace', 'balcony', '天井', '中庭',
            '广场', '操场', '停机坪', '靶场', '操场'),
    陈设词=('桌', '椅', '沙发', '床', '柜', '电脑', '屏幕', '前台', '货架', '冰箱',
            '咖啡机', '打印机', '文件柜', '饮水机', '病床', '黑板', '收银台',
            '储物柜', 'X光机', '手术台'),
    门洞词=('门', '大门', '正门', '侧门', '后门', '旋转门', 'entry', 'lobby'),
    楼上词=('二楼', '三楼', '四楼', '五楼', '楼上', '顶层', '楼层'),
    # ★ 「地下」原来在楼上词里 ⇒ 地下车库被排到二楼。拆出来，层号给负数。
    # [EN] 「地下」 used to sit in 楼上词, sending the underground garage to floor 2. Split out.
    地下词=('地下', '地下一层', 'B1', 'B2', '负一', '负二', '地库'),
    楼梯词=('梯', '楼梯', '电梯', '扶梯', 'escalator', 'elevator'),
    房间词=('室', '间', '厅', '房', '廊', '区', '室', 'office', 'room', 'lab'),
    分带次序=('门', '厅', '堂', '廊', '室', '间', '房', '厨', '库'),
    主厅词=('厅', '大堂', '中庭', 'lobby', '大厅'),
    厨房词=('厨', '厨房', 'kitchen', '配餐'),
    # ★★★ 2026-10-26 大扩（实测：校园 / 医院 / 商场 / 军事基地**全部判成兜底**）。
    #   为什么并进同一个档案而不是各立一个：它们**画法相同** ——
    #   平屋顶、砖石双线墙、走廊串联、核心筒竖交通、广场/中庭这类公共空间。
    #   差别只在词（`手术室` 与 `教室` 在图上都是"靠走廊的一间"）。
    #   按立档标准（画法不同才新增），这些都该并进来。
    #   ⚠ 军事基地是个例外的一半：它有大量**露天场地**（停机坪/靶场/操场），
    #     所以 `广场` 类词也收进 `见天词`，否则会被当成"房间"排进带里。
    # [EN] ★★★ Big expansion 2026-10-26 (measured: campus / hospital / mall / military base **all
    # [EN] fell through to the fallback**). Why merge instead of one profile each: they are **drawn
    # [EN] the same way** -- flat roof, masonry double walls, corridor-linked rooms, a core for
    # [EN] vertical circulation, and one large public space (plaza/atrium). Only the words differ
    # [EN] (`手术室` and `教室` are both "a room off the corridor" on the plan). By the profiling rule
    # [EN] (new profile only for a different drawing) these belong here. ⚠ Military bases are the
    # [EN] half-exception: they are mostly **open ground** (apron/range/parade ground), so those words
    # [EN] go into 见天词 or they would be sorted into a band as if they were rooms.
    强词=('电梯', '地下车库', '停车位', '前台', '会议室', '办公区', '茶水间',
          '监控室', '消防通道', '机房', '中央空调', '地铁',
          # 校园
          '教学楼', '宿舍楼', '图书馆', '食堂', '操场', '实验室', '阶梯教室',
          '礼堂', '体育馆', '辅导员', '值日', '教研室',
          # 医院
          '门诊', '急诊', '手术室', '病房', '药房', '护士站', '太平间', '检验科',
          '放射科', '输液室', '重症监护', '留观',
          # 商场/公共
          '中庭', '扶梯', '商铺', '美食广场', '影院', '收银台', '试衣间',
          '美食城', '观光电梯', '地下停车场',
          # 住宅（实测：合租公寓被判成「西式宅邸」—— 因为 `客厅` 是那边的弱词，
          #   而 `主卧/次卧` 哪边都不认。现代住宅的强特征是"户型语言"）
          '主卧', '次卧', '户型', '客厅', '卫生间', '玄关', '飘窗', '阳台',
          '厨房', '餐厅', '共用厨房', '合租', '单间', '一室一厅', '两室一厅',
          # 军事/机构
          '指挥所', '军械库', '营房', '停机坪', '哨塔', '靶场', '禁闭室'
          '作战室', '值班室', '防空洞',
          # ★★★ 英文（2026-10-26 实测发现的**结构性缺口**：现代档案原来一个英文词都没有，
          #   于是 `lobby` / `meeting room` / `parking garage` / `roof` 全判兜底。
          #   中文小说里用英文地名很常见，尤其现代、科幻、西幻 —— 这不是"顺手补"，是漏了一整块。
          #   ⚠ 词要取**单数形式**（`_count` 是子串匹配，单数能命中复数，反之不行）。
          'lobby', 'meeting room', 'cubicle', 'parking garage', 'underground parking',
          'reception', 'open office', 'break room', 'stairwell', 'elevator',
          'restroom', 'corridor', 'classroom', 'dormitory', 'cafeteria',
          'gymnasium', 'laboratory', 'auditorium', 'library',
          'operating room', 'ward', 'pharmacy', 'nurse station', 'morgue',
          'emergency room', 'intensive care', 'examination room',
          'atrium', 'escalator', 'food court', 'cinema', 'shop', 'checkout',
          'command post', 'armory', 'barrack', 'helipad', 'watchtower',
          # ⚠ `kitchen` / `guest room` 删掉：**中西共有**的通用词，留着会把西幻酒馆
          #   判成现代公寓（H9 判据抓到的第二例）。现代住宅的专属特征是"户型语言"，
          #   `master bedroom` / `living room` / `cubicle` 才是。
          # [EN] `kitchen` and `guest room` removed: generic terms shared by both traditions, and
          # [EN] keeping them made a Western tavern read as a modern apartment (the second case H9
          # [EN] caught). Modern homes are identified by their **floor-plan vocabulary**.
          'master bedroom', 'balcony', 'living room', 'studio apartment'),
    弱词=('走廊', '阳台', '洗手间', '储藏室', '前台', '办公桌', '储物柜',
          '黑板', '病床', '货架', '操场'),
    反证=('堂屋', '天井', '厢房', '影壁', '灶间', '院落', '壁炉', '马厩',
          '榻榻米', '障子', '锅庄', '气闸', '舰桥'),
    屋顶='flat',
    墙线='double',
    路网='grid',
    城际='administrative',
    聚落等级={4: ('市中心', '主城区', '中央商务区', 'downtown', 'city center', 'cbd'),
              3: ('城区', '新区', '开发区', '行政区', '园区', 'district', 'township'),
              2: ('街道', '社区', '镇', 'suburb', 'town', 'neighborhood'),
              1: ()},
    聚落名={4: '市中心 / 主城区', 3: '城区 / 开发区', 2: '街道 / 社区', 1: '居民点'},
    需查=('建筑层数与核心筒位置',
          '街区尺度与路网分级（主干/次干/支路）'),
)

FUTURE = Style(
    key='future',
    名='未来／科幻',
    族='future',
    依据='模块化舱段、气闸、环形/分层结构；也可以是巨构内部的城市。'
         '没有普适原型，**优先照设定文本画**。',
    见天词=('穹顶', '天窗', '观景台', '露天', 'dome', 'atrium'),
    陈设词=('终端', '控制台', '舱位', '培养舱', '机械臂', '屏幕', '全息', '储罐',
            '反应堆', '服务器'),
    门洞词=('气闸', '舱门', '闸门', 'airlock', 'hatch', '大门'),
    楼上词=('上层', '甲板', '楼层', 'deck', 'level'),
    地下词=('下层', '底舱', '下甲板', 'lower deck'),
    楼梯词=('梯', '升降', '电梯', '通道', 'lift', 'elevator', 'ramp'),
    房间词=('舱', '室', '区', '廊', '厅', '层', 'bay', 'module', 'section'),
    分带次序=('闸', '门', '厅', '廊', '区', '舱', '室', '库'),
    主厅词=('厅', '中枢', '舰桥', 'bridge', 'core'),
    厨房词=('厨', '配餐', '合成', 'galley'),
    # ★ 2026-10-26 补：太空站 / 水下基地 / 轨道站（实测「对接舱/观测穹顶/储物舱」
    #   「气压舱/水密门/观察窗」全都判成现代，只有 1.20 —— 它们和"办公楼"画法相近，
    #   但**没有窗、没有街、是靠舱段串联**，必须区分）。
    # [EN] Added 2026-10-26: space stations / underwater bases / orbital habitats. Measured, these
    # [EN] fell to "modern" at 1.20 -- the drawing is similar, but they have **no windows, no
    # [EN] streets and are linked by modules**, so the distinction matters.
    强词=('气闸', '舱段', '舰桥', '曲率', '跃迁', '反应堆', '全息', '义体',
          'airlock', 'warp', 'reactor', 'hologram', 'cyberware',
          '对接舱', '观测穹顶', '休眠舱', '气压舱', '水密门', '减压舱',
          '轨道站', '空间站', '居住舱', '货运舱', '生命维持', '维生系统',
          '舷梯', '离心重力', '隔离舱', '生态舱'),
    弱词=('控制台', '终端', '通道', '舷窗'),
    反证=('堂屋', '天井', '厢房', '壁炉', '八仙桌', '马厩'),
    屋顶='flat',
    墙线='double',
    路网='radial',
    城际='administrative',
    聚落等级={4: ('主基地', '母舰', '总站', 'prime base', 'capital station'),
              3: ('空间站', '轨道站', '基地', '殖民地', 'colony', 'station', '站'),
              2: ('前哨', 'outpost', '中继站', '补给点', 'relay', '停泊'),
              1: ()},
    聚落名={4: '主基地 / 母舰', 3: '站点 / 基地', 2: '前哨 / 补给点', 1: '落脚点'},
    需查=('这个设定的建筑是舱段、巨构还是星球表面聚居点',
          '交通方式（舱内通道/轨道/飞行）'),
)

FANTASY = Style(
    key='fantasy',
    名='奇幻（照设定画，不套原型）',
    族='fantasy',
    依据='奇幻没有统一原型：可能是塔、地下城、树屋、漂浮岛。'
         '所以这里**故意不给强词表** —— 一旦硬套，它会把精灵的树屋画成四合院。',
    见天词=('庭院', '花园', '露台', '天井', '中庭', '广场', '林间', 'garden'),
    陈设词=('柜', '桌', '椅', '床', '架', '炉', '坩埚', '符文', '法阵', '祭坛',
            '卷轴', '药瓶', '水晶'),
    门洞词=('门', '大门', '传送门', '拱门', 'gate', 'portal'),
    楼上词=('楼上', '二楼', '上层', '塔顶', '阁楼'),
    楼梯词=('梯', '楼梯', '旋梯', 'spiral', 'stair'),
    房间词=('室', '厅', '房', '间', '塔', '殿', '窟', '洞', '廊', '院', '阁'),
    分带次序=('门', '厅', '殿', '廊', '室', '院', '塔', '窟'),
    主厅词=('厅', '殿', '大厅', 'hall'),
    厨房词=('厨', '灶', '厨房', 'kitchen'),
    强词=('法师塔', '传送门', '祭坛', '法阵', '地牢', '酒馆', '公会', '圣殿',
          '精灵', '矮人', '龙巢', '塔楼', 'dungeon', 'altar', 'rune'),
    弱词=('水晶', '符文', '卷轴', '符文石'),
    反证=(),          # 奇幻**不设反证**：它本来就可能是任何东西
    屋顶='pitched',
    墙线='double',
    路网='organic',
    城际='terrain',
    需查=('这个世界的力量体系如何影响建筑（浮空/地下/树居？）',
          '主要种族/势力的聚居形态',
          '交通与地形的特殊之处（传送门？航线？）'),
)

# ══════════════════════════════════════════════════════════════════════
#  2026-10-26 补的五个（用户问"覆盖所有小说类型了吗" ⇒ 实测 22 种里 15 种不行）
# [EN] Five added 2026-10-26 (the user asked "does it cover every genre?" -- measured, 15 of 22
# [EN] failed), so these are the real gaps, not guesses.
# ══════════════════════════════════════════════════════════════════════
#  立档标准（**这一条决定要不要新增**）：**画法不同**才立一个档案，词不同不立。
#  画法维度 = 屋顶做法 / 墙线单双 / 路网形态 / 分带次序 / 主厅词。
#  所以：寺庙与宫殿**并入**中式府邸（都是中轴多进）；校园医院商场**并入**现代
#  （都是平屋顶＋走廊串联）。而日式、民国、工业、废土、舟船是**真的画法不同**。
# [EN] Rule for adding a profile: **a different drawing**, not different words. Drawing dimensions
# [EN] are roof treatment, wall line, street network, band order and hall words. So temples and
# [EN] palaces **merge into** the Chinese mansion (all axial, multi-courtyard), and campuses /
# [EN] hospitals / malls **merge into** modern (flat roof, corridor-linked). Japanese, Republican,
# [EN] industrial, wasteland and vessels really are drawn differently.

JP_WASHITSU = Style(
    key='jp_washitsu',
    名='日式和风（书院造／武家造）',
    族='jp',
    依据='玄关脱鞋入内，室内铺榻榻米按「间」为模数，房间用障子／襖分隔，'
         '外有缘侧（外廊）连向庭园；武家造另有天守。',
    见天词=('庭园', '坪庭', '中庭', '露台', '缘侧'),
    陈设词=('榻榻米', '屏风', '火钵', '座垫', '矮几', '茶釜', '刀架', '甲胄',
            '佛坛', '灯笼', '石灯笼'),
    门洞词=('玄关', '门', '大门', '木门', '表门'),
    楼上词=('二楼', '楼上', '天守', '橹', '望楼'),
    楼梯词=('梯', '楼梯', '阶段'),
    房间词=('室', '间', '之间', '间', '书院', '座敷', '台所', '廊', '庭', '门'),
    分带次序=('玄关', '门', '座敷', '书院', '间', '台所', '缘侧', '庭', '天守'),
    主厅词=('座敷', '书院', '广间', '大厅'),
    厨房词=('台所', '厨', '灶'),
    强词=('玄关', '和室', '榻榻米', '障子', '襖', '缘侧', '座敷', '书院', '天守',
          '鸟居', '坪庭', '枯山水', '台所', '大广间', '武家', '町屋', '藏',
          # 英文（日式场景被译成英文时）
          'genkan', 'tatami', 'shoji', 'fusuma', 'engawa', 'zashiki', 'shoin',
          'tokonoma', 'donjon', 'torii', 'karesansui', 'daidokoro'),
    弱词=('庭园', '屏风', '石灯笼', '木廊'),
    反证=('堂屋', '天井', '厢房', '影壁', '沙发', '壁炉', '电梯', '车库', '客厅'),
    屋顶='pitched',
    墙线='single',
    路网='organic',
    城际='terrain',
    聚落等级={4: ('京都', '江户', '大阪', '城下町', '天守'),
              3: ('藩', '阵屋', '代官所', '宿场', '町奉行', '奉行所'),
              2: ('町', '宿', '凑', '村', '在乡'),
              1: ()},
    聚落名={4: '城下町 / 京都', 3: '藩厅 / 宿场', 2: '町 / 村', 1: '小村'},
    需查=('这种武家／町屋的「间取り」惯例（几间×几间、房间如何连）',
          '缘侧与庭园的关系（哪一侧朝庭）',
          '玄关到座敷的过渡（是否经书院）'),
)

REPUBLIC = Style(
    key='republic',
    名='民国近代（洋楼＋弄堂）',
    族='republic',
    依据='中西混合：临街石库门／洋楼用砖石双线墙与平屋顶或小坡顶，'
         '内部却是中式天井与亭子间的混搭；城市尺度是弄堂＋马路。',
    见天词=('天井', '晒台', '阳台', '露台', '院子', '花园'),
    陈设词=('沙发', '留声机', '书桌', '玻璃柜', '洋灯', '电话', '钢琴',
            '麻将桌', '衣帽架', '痰盂'),
    门洞词=('大门', '石库门', '黑漆门', '后门', '侧门', '门'),
    楼上词=('二楼', '三楼', '楼上', '亭子间', '晒台', '阁楼'),
    楼梯词=('梯', '楼梯', '楼梯间', '电梯'),
    房间词=('厅', '室', '间', '房', '房', '廊', '楼', '门', '堂'),
    分带次序=('门', '天井', '厅', '室', '房', '亭子间', '晒台', '楼'),
    主厅词=('客厅', '客堂', '正厅', '大厅', '厅'),
    厨房词=('灶披间', '厨房', '灶', '厨'),
    强词=('石库门', '弄堂', '亭子间', '灶披间', '客堂', '晒台', '洋行', '巡捕房',
          '租界', '公馆', '舞厅', '报馆', '电车', '留声机', '旗袍', '洋楼',
          '西式壁炉', '百叶窗', '水门汀', '石库门里弄',
          # 英文（民国场景的英文写法 / 租界里的洋文名）
          'shikumen', 'longtang', 'lane house', 'concession', 'comprador',
          'verandah', 'gramophone', 'parlour', 'godown'),
    弱词=('天井', '沙发', '玻璃窗', '砖墙', '弄口'),
    反证=('堂屋', '厢房', '影壁', '灶间', '八仙桌', '榻榻米', '障子', '电梯',
          '地下车库', '办公区', '会议室'),
    屋顶='flat',
    墙线='double',
    路网='grid',
    城际='administrative',
    聚落等级={4: ('特别市', '市中心', '租界', '商埠', 'city'),
              3: ('县', '区', '公馆区', '码头区', 'district', '市'),
              2: ('镇', '弄堂', '坊', '站', '集'),
              1: ()},
    聚落名={4: '特别市 / 租界', 3: '县 / 区', 2: '镇 / 弄堂', 1: '居民点'},
    需查=('这类石库门的标准平面（一客堂两厢房？前后天井？）',
          '亭子间与晒台的位置关系',
          '弄堂的宽度与主弄支弄分级'),
)

STEAMPUNK = Style(
    key='steampunk',
    名='工业／蒸汽（厂房＋机械）',
    族='industrial',
    依据='大跨钢结构厂房、锅炉与管道为主干，烟囱与飞艇坪是地标；'
         '房间按功能分区（动力区／加工区／生活区），靠通道串联。',
    见天词=('天井', '露天', '平台', '烟囱口', '平台'),
    陈设词=('锅炉', '蒸汽机', '齿轮', '管道', '阀门', '仪表', '工作台',
            '吊车', '车床', '铆钉', '煤堆', '储气罐'),
    门洞词=('大门', '铁门', '闸门', '舱门', '门'),
    楼上词=('二楼', '楼上', '平台', '天车', '阁楼', '上层'),
    楼梯词=('梯', '铁梯', '升降机', '楼梯', '吊笼'),
    房间词=('房', '间', '厅', '车间', '室', '区', '库', '廊'),
    分带次序=('门', '厅', '车间', '炉', '机', '库', '廊', '平台'),
    主厅词=('车间', '厂房', '大厅', '控制室', '装配'),
    厨房词=('厨房', '食堂', '配餐', '厨'),
    强词=('锅炉', '蒸汽机', '飞艇', '齿轮', '烟囱', '蒸汽', '管道', '阀门',
          '铆钉', '车床', '锻造', '煤仓', '气压', '发条', '黄铜', '飞空艇',
          'boiler room', 'engine room', 'workshop', 'smokestack', 'chimney',
          'airship', 'gear', 'piston', 'valve', 'foundry', 'blast furnace',
          'catwalk', 'gantry'),
    弱词=('铁梯', '工作台', '仪表', '吊车', '煤'),
    反证=('堂屋', '天井', '厢房', '影壁', '榻榻米', '障子', '电梯', '地下车库',
          '气闸', '舰桥', '反应堆', '全息'),
    屋顶='pitched',
    墙线='double',
    路网='organic',
    城际='administrative',
    聚落等级={4: ('王都', '大都会', '帝国首都', 'metropolis'),
              3: ('工业城', '矿区', '空港', 'factory town', 'works', '城'),
              2: ('镇', '站', '集市', 'mill town', '驿站'),
              1: ()},
    聚落名={4: '王都 / 大都会', 3: '工业城 / 空港', 2: '镇 / 站', 1: '聚落'},
    需查=('这套设定的动力从哪来（蒸汽机？发条？以太？）',
          '厂房与居住区是否分离、如何连通',
          '飞艇／轨道这类交通工具的停靠处形态'),
)

WASTELAND = Style(
    key='wasteland',
    名='废土／末日（避难所＋废墟）',
    族='post',
    依据='不是"新建的建筑"，而是**改造与残骸**：地下避难所按舱段分区、'
         '气密门串联；地上是残破街区与临时棚屋，靠清出的通道连通。',
    见天词=('天井', '露天', '废墟广场', '天台', '通风井'),
    陈设词=('净水器', '发电机', '储水罐', '弹药箱', '工作台', '床垫',
            '燃烧桶', '无线电', '滤芯', '医疗箱'),
    门洞词=('气密门', '闸门', '铁门', '大门', '门'),
    楼上词=('上层', '下层', '二层', '楼', '平台', '天台'),
    楼梯词=('梯', '铁梯', '竖井', '楼梯', '爬梯'),
    房间词=('区', '室', '间', '厅', '库', '廊', '房', '舱'),
    分带次序=('门', '闸', '厅', '区', '室', '库', '廊', '井'),
    主厅词=('大厅', '主控', '指挥', '公共区', '厅'),
    厨房词=('厨房', '配餐', '伙房', '厨'),
    强词=('避难所', '地堡', '净水', '废土', '废墟', '拾荒', '辐射', '柴油机',
          '气密门', '防毒面具', '感染', '幸存者', '隔离区', '警戒线', '滤芯',
          'bunker', 'shelter', 'fallout', 'radiation', 'scavenger', 'raid',
          'water purifier', 'generator', 'quarantine', 'checkpoint', 'ruin'),
    弱词=('发电机', '储水罐', '燃烧桶', '弹药箱', '铁皮'),
    反证=('堂屋', '天井', '厢房', '影壁', '榻榻米', '电梯', '大堂', '会议室',
          '舰桥', '气闸', '全息', '锅炉'),
    屋顶='flat',
    墙线='single',
    路网='organic',
    城际='terrain',
    聚落等级={4: ('大营', '要塞', '聚居地', 'bunker city', 'vault city'),
              3: ('避难所', 'bunker', 'shelter', '据点', 'vault', '地堡'),
              2: ('营地', '聚落', 'checkpoint', '哨站', 'camp', '哨塔'),
              1: ()},
    聚落名={4: '大营 / 要塞', 3: '避难所 / 据点', 2: '营地 / 哨站', 1: '落脚点'},
    需查=('这个世界毁于什么（核／疫／战争／天灾），残存建筑还剩什么',
          '避难所是地下还是地上、如何分区',
          '水电从哪来（这是废土布局的第一约束）'),
)

VESSEL = Style(
    key='vessel',
    名='舟船（甲板＋舱室）',
    族='vessel',
    依据='**狭长的层叠空间**：纵向沿龙骨分舱，横向分舷；甲板是唯一的"见天"，'
         '下层舱室无窗、靠舱口与梯道连通。与陆地建筑的"进"完全不是一回事。',
    见天词=('甲板', '露天甲板', '船首', '船尾', '桅盘'),
    陈设词=('舵轮', '锚机', '缆绳', '货箱', '酒桶', '火炮', '罗盘', '海图桌',
            '吊床', '灶台'),
    门洞词=('舱门', '舷门', '跳板', '门'),
    楼上词=('上层甲板', '上甲板', '二层', '顶层', '桅盘', '瞭望'),
    地下词=('底舱', '货舱', '下层舱', '压舱'),
    楼梯词=('舷梯', '梯', '舱梯', '升降口'),
    房间词=('舱', '室', '甲板', '房', '厅', '间'),
    分带次序=('跳板', '甲板', '舱', '室', '底舱'),
    主厅词=('船长室', '大舱', '主舱', '厅'),
    厨房词=('厨房', '灶房', '厨', '配餐'),
    强词=('甲板', '船长室', '货舱', '桅杆', '底舱', '舵轮', '舷窗', '帆',
          '锚', '舱室', '船首', '船尾', '海盗', '跳板',
          'deck', 'captain cabin', 'cargo hold', 'mast', 'hull', 'galley',
          'brig', 'quarterdeck', 'gangplank', 'prow', 'stern', 'hold'),
    弱词=('缆绳', '罗盘', '火炮', '吊床', '酒桶'),
    反证=('堂屋', '天井', '厢房', '影壁', '榻榻米', '电梯', '大堂', '会议室',
          '地下车库', '气闸', '舰桥', '反应堆'),
    屋顶='flat',
    墙线='double',
    路网='organic',
    # ★ 2026-10-26 改：`terrain` → **`nautical`**。
    #   一条航线上的世界**没有政区**：把"浪高岛"画成一块行政分区、把航路画成官道，
    #   就等于给它编了国界。海图该有的是：水面、岸线、锚地/港口、虚线航路。
    城际='nautical',
    聚落等级={4: ('母港', '大港', '皇家港', 'home port'),
              3: ('港', 'port', 'harbor', 'harbour', '码头'),
              2: ('锚地', '泊地', '滩', '小港', 'anchorage', 'bay'),
              1: ()},
    聚落名={4: '母港', 3: '港口', 2: '锚地 / 泊地', 1: '未知名处'},
    需查=('这是什么船（商船／战舰／渔船／内河船），几个桅、几层甲板',
          '货舱与住舱的相对位置',
          '船上有无火炮甲板、弹药库'),
)


ALL: tuple = (CN_SHOP_HOUSE, CN_MANSION, JP_WASHITSU, WEST_MANOR, WEST_TOWN,
              REPUBLIC, STEAMPUNK, MODERN, FUTURE, WASTELAND, VESSEL, FANTASY)
BY_KEY: dict = {s.key: s for s in ALL}

#: 判不出来时用哪一份。
#: ★ 选**最不禁忌**的那一份：`fantasy` 不设反证、词表宽松，套错了伤害最小
#:   （它不会把西式强行画成四合院，只是少一点特征）。
#:   ⚠ 但**必须告诉调用方"这是兜底"**，别让它以为判准了。
# [EN] The fallback when detection fails. ★ `fantasy` is the least opinionated profile (no
# [EN] counter-evidence, loose word lists), so a wrong guess hurts least. ⚠ The caller must still
# [EN] be told **this was a fallback**, not a detection.
FALLBACK = FANTASY


# ══════════════════════════════════════════════════════════════════════
#  二·补  判不出风格时用的**通用**等级表
# [EN] 2b. The **generic** rank table used when the profile is unknown
# ══════════════════════════════════════════════════════════════════════
#: 通用等级词表＝各档案的**并集**。
#:
#: ★ 只在"判不出风格"时用（`FANTASY` 的等级表故意留空 ⇒ 落到这里）。
#:   为什么并集是安全的：这份表**不参与风格竞争**，它只回答"这个名字像什么规模的聚落"，
#:   而"州"在任何世界里都是大地方、"港口"都值得画大一号。
#: ⚠ 反过来说：**能判出风格时一定用档案自己的表** —— 否则西幻的 `keep` 会被中式表漏掉，
#:   又回到"全部 1 级"那个坑。
# [EN] The generic rank table is the **union** of the profiles. ★ Used only when the profile is
# [EN] unknown (`FANTASY` deliberately leaves its tables empty, so it lands here). A union is safe
# [EN] because this table **does not compete** for style: it only answers "what size of settlement
# [EN] does this name suggest". ⚠ Conversely, a known profile must use **its own** table, or a
# [EN] Western `keep` falls through the Chinese list and we are back to "everything rank 1".
GENERIC_RANKS = {
    4: ('京师', '都城', '王城', '京城', '皇城', '国都', '州', '府', '郡',
        'capital', 'citadel', 'metropolis', '主基地'),
    3: ('县', '关', '隘', '要塞', '边关', '卫所', '所城', '城堡', '要塞',
        'keep', 'fortress', 'abbey', 'stronghold', 'barony', '空间站', '轨道站', '基地',
        '避难所', '城区', '开发区', '工业城'),
    2: ('镇', '驿', '集', '渡', '港', '码头', '堡', '铺', '村',
        'town', 'village', 'inn', 'bridge', 'ford', 'port', 'harbor', 'anchor',
        '前哨', '营地', '街道', '社区', '弄堂'),
    1: (),
}

#: 通用等级的**说法**（图例用）。★ 刻意中性：「要地／据点／集镇／小聚落」——
#: 不知道这是什么世界时，说"县城"就是替作者断言了一个文明。
# [EN] Neutral names for the generic ranks. ★ Deliberately neutral: saying "county seat" would
# [EN] assert a civilisation the author never specified.
GENERIC_RANK_NAME = {4: '要地（最大聚落）', 3: '据点 / 城', 2: '集镇 / 驿 / 渡', 1: '小聚落'}


def rank_table(st: 'Style | None') -> dict:
    """这个档案用哪张等级词表：它有就用它的，没有（判不出／奇幻）用通用表。

    [EN] Which rank table this profile uses: its own when it has one, otherwise the generic table.
    """
    表 = getattr(st, '聚落等级', None) or {}
    return 表 or GENERIC_RANKS


def rank_name(st: 'Style | None', rank: int) -> str:
    """这个等级在这个档案里叫什么（图例）。判不出就返回**中性**说法。

    [EN] What this rank is called in this profile (legend); neutral wording when unknown.
    """
    s = ''
    if st is not None:
        try:
            s = st.rank_name(rank)
        except Exception:                                     # noqa: BLE001
            s = ''
    if s:
        return s
    try:
        return GENERIC_RANK_NAME.get(int(rank), '')
    except (TypeError, ValueError):
        return ''


#: 作者给的**规模** → 聚落等级。只在名字判不出时用（见 `settlement_rank`）。
#: ⚠ `Place.size` 的 schema 默认值是「中」⇒ 没想过的地点落在 2。这是有意的取舍：
#:   落在 1 会让"作者明确标了大"彻底消失。
# [EN] Author-declared **size** -> rank, used only when the name says nothing. ⚠ The schema default
# [EN] is 中, so unconsidered places land at 2 -- a deliberate trade-off: landing at 1 would erase
# [EN] "the author marked it big".
SIZE_TO_RANK = {'特大': 4, '大': 3, '中': 2, '小': 1}


def settlement_rank(name: str, *, size: str = '', style: 'Style | None' = None) -> int:
    """这个名字是**什么等级的聚落**（4 高 ~ 1 低）。

    ★★★ **唯一一份实现**。`scalemap`（大地图）与 `minimap`（小地图）都调它 ——
      这两处原来各判各的（小地图根本没有等级概念），结果"大地图上行距分明的
      州府与村子，在小地图上全是一个大小"。同一件事两处实现必然漂（本项目头号老坑）。
      ⚠ 放在 `worldstyle` 是因为它**零依赖**（只 import re/dataclasses）：
        `scalemap` 依赖 `minimap`，所以 `minimap` 不能反过来 import `scalemap`。

    ## 判法三级（先证据、后作者的声明、最后才是最低级）

    1. **档案自己的等级词表**（中式 州/府/县…、西式 castle/keep/abbey…、现代 城区/街道…）；
    2. **通用表**（各档案的并集）—— 档案例外没覆盖的写法（外文译名、混搭世界）；
    3. **作者给的 `size`**：`特大→4 / 大→3 / 中→2 / 小→1`；
    4. 都没有 ⇒ 1（**不抬等级**）。

    ★★★ 2026-10-26/27 修（自查发现的**真错**）：原来只认**中式建制**词表
      （`州/府/县/关/镇/驿/渡`），凡是"不是汉字建制词"的名字一律落到 1。后果不是
      "画小了"，而是**画错了**：西幻的 `Minas Tirith`、`Dunharrow keep`、东方的宗门
      全被画成 2.8px 的小圆点，有城墙有塔的主城与村口渡口**一样大** ——
      而"哪座城重要"正是城际图上唯一能传达的信息。
    [EN] What **rank of settlement** this name is (4 high .. 1 low). ★★★ **The one
    [EN] implementation**: both `scalemap` (big map) and `minimap` call it; they used to judge
    [EN] separately (the minimap had no notion of rank at all), so a prefecture and a hamlet came out
    [EN] the same size on the minimap. ⚠ It lives in `worldstyle` because that module is
    [EN] **dependency-free**: `scalemap` imports `minimap`, so `minimap` cannot import `scalemap`.
    [EN] ## Four tiers: the profile's own rank words, the generic union table, the author's `size`,
    [EN] and 1 as the floor (**never promoted**). ★★★ Fixed 2026-10-26/27 (a real bug found on audit):
    [EN] it used to recognise **Chinese administrative** words only, so `Minas Tirith` or a sect
    [EN] compound fell to 1 -- a walled capital the size of a ferry crossing.
    """
    n = str(name or '')
    r = 0
    if n and style is not None:
        try:
            r = int(style.rank_of(n))
        except Exception:                                     # noqa: BLE001
            r = 0
    if not r and n:
        # 档案没认出来 ⇒ 用并集表（它不参与风格竞争，只回答"这名字像多大")
        # [EN] The profile did not recognise it => the union table, which does not compete for style
        nl = n.lower()
        for k in (4, 3, 2, 1):
            for w in GENERIC_RANKS.get(k, ()):
                w = str(w or '')
                if not w:
                    continue
                # 拉丁字母不分大小写（`Dunharrow Keep` vs 词表里的 `keep`）
                # [EN] Latin words ignore case (`Dunharrow Keep` vs `keep` in the table)
                if (w.lower() in nl) if w.isascii() else (w in n):
                    r = k
                    break
            if r:
                break
    if not r:
        r = SIZE_TO_RANK.get(str(size or ''), 0)
    return max(1, min(4, r or 1))


def for_layout(layout, places=None, *, genre: str = '') -> 'Match':
    """从**一份地图布局**判"按哪种建筑传统画"。

    ★ 判法的次序（有强证据就不猜）：
      ① 布局里有任务书（`layout.program['风格']`）⇒ **直接用**。任务书是
         "这栋房子长什么样"的记录，比从地名反推可靠；顺带把"当时就是兜底"的
         事实（`风格依据` 里写着"判不出"）也带回来，不然重解一次就成了"已识别"。
      ② 否则用 `detect()` 看地名 + 备注（题材只作弱提示）。
    ★ 为什么需要这个函数：`roomplan` 只判**室内**；城市图／城际图／甲板图从来
      没人判过风格，于是那三层一直在用写死的默认值。两处各写一遍判法就是漂移的入口。
    [EN] Decide the building tradition from **a map layout**. ★ Order (never guess over hard
    [EN] evidence): (1) if the layout carries a program, use its recorded profile, and carry back
    [EN] the "this was a fallback" fact (`风格依据` says 判不出) so a re-solve does not turn an
    [EN] honest fallback into a "detection"; (2) otherwise `detect()` on names and notes, with the
    [EN] genre only as a weak hint. ★ Why this function exists: `roomplan` only judged **indoor**
    [EN] plans, so the city / region / deck layers always used hard-coded defaults -- and two
    [EN] copies of one judgement is how drift starts.
    """
    prog = getattr(layout, 'program', None) or {}
    if isinstance(prog, dict) and prog:
        st = BY_KEY.get(str(prog.get('风格') or ''))
        if st is not None:
            why = str(prog.get('风格依据') or '')
            fallback = '判不出' in why
            return Match(style=st, score=(0.0 if fallback else 1.0), 是兜底=fallback)
    ps = list(places if places is not None else (getattr(layout, 'places', None) or []))
    texts: list[str] = []
    for p in ps:
        texts.append(str(getattr(p, 'name', '') or ''))
    for p in ps:
        texts.append(str(getattr(p, 'note', '') or ''))
    return detect(*texts, genre=str(genre or ''))


# ══════════════════════════════════════════════════════════════════════
#  三、判定
# [EN] 3. Detection
# ══════════════════════════════════════════════════════════════════════
@dataclass
class Match:
    """一次判定的结果 —— **带着理由**，不是光秃秃一个 key。

    [EN] One detection result -- **with reasons**, not a bare key.
    """

    style: Style
    #: 0.0~1.0。**不是概率**，只是"证据强度"，用来比较与决定要不要去查资料。
    # [EN] 0.0~1.0. **Not a probability**, just evidence strength: for comparing and for deciding
    # [EN] whether to go research.
    score: float = 0.0
    #: 命中的词（给日志与打回意见看："我按这些词判成西式宅邸"）
    # [EN] Matched words (so logs/revision notes can say "judged Western manor from these")
    强命中: tuple = ()
    弱命中: tuple = ()
    #: 判成兜底的就不再叫"判定"
    # [EN] True when this is the fallback rather than a real detection
    是兜底: bool = False

    @property
    def 可信(self) -> bool:
        return (not self.是兜底) and self.score >= 0.5

    def why(self) -> str:
        """一句话说清"凭什么"。空证据就说空证据，别装。
        [EN] One line saying "on what grounds"; say "no evidence" when there is none.
        """
        if self.是兜底:
            return f'判不出建筑类型，按「{self.style.名}」兜底（不套任何一国原型）'
        parts = []
        if self.强命中:
            parts.append('强证据 ' + '、'.join(self.强命中[:4]))
        if self.弱命中:
            parts.append('弱证据 ' + '、'.join(self.弱命中[:4]))
        return f'{self.style.名}（' + ('；'.join(parts) or '仅凭反证排除') + '）'


def _count(text: str, words) -> tuple:
    """返回 `text` 里**真的出现**的那些词（长词优先，避免"门"吃掉"门厅"）。

    ⚠ 中文没有词边界 ⇒ `w in text` 会命长词的子串。这里对**同一档案内**做一次
      长词优先去重：先命中的长词占了，短词就不再重复计数（否则"垂花门"会被记成
      "门"和"垂花门"两次，把分数灌水）。
    [EN] Return the words from `words` that actually appear in `text`, longest first (so "门" does
    [EN] not swallow "门厅"). ⚠ Chinese has no word boundaries, so within one profile we dedupe
    [EN] longest-first: once "垂花门" matched, "门" no longer counts again (otherwise one hit scores
    [EN] twice and inflates the total).
    """
    t = str(text or '')
    if not t:
        return ()
    hits: list[str] = []
    for w in sorted({str(x) for x in words if x}, key=len, reverse=True):
        if w in t:
            # 已经被更长的命中覆盖过就不重复记
            if any(w in h and w != h for h in hits):
                continue
            hits.append(w)
    return tuple(hits)


def detect(*texts, genre: str = '') -> Match:
    """从一堆文本里判出**这是哪种建筑传统**。

    Args:
        *texts: 任意段文本（地点名、地点说明、世界观摘要、剧本片段……）。
                传进来什么就看什么，**调用方负责把有用的都传进来**。
        genre: 题材（`genre_card['主题材']`）。**只作弱提示** ——
               "古装"不等于"中式"，"都市"也不等于"现代建筑"，所以它的权重
               比任何一个实物词都低。

    Returns:
        `Match`。判不出来时返回 `FALLBACK` 且 `是兜底=True`。

    ★★ 判据的分层（有意如此）：
      ① **强词**命中 → 该档案 +1.0/个（最多计 3 个，防止一个长段落里
         反复出现同一个词把分数刷满）；
      ② **弱词**命中 → +0.15/个（最多 4 个）；
      ③ **反证**命中 → ×0.15（几乎排除，但不归零 —— 混搭世界是存在的）；
      ④ 题材提示 → +0.2；
      ⑤ 最高分 **< 0.5** ⇒ 视为"判不出来"，走兜底。
      门槛 0.5 的意思是：**至少一个强词，或三个弱词＋题材**。凭"有门有窗"判不出来。
    [EN] Layered on purpose: strong words +1.0 each (capped at 3), weak +0.15 each (capped at 4),
    [EN] counter-evidence x0.15 (near-elimination, not zero -- mashups exist), genre +0.2, and
    [EN] anything under 0.5 counts as "cannot tell" and falls back. 0.5 means: one strong word, or
    [EN] three weak words plus genre. "Has doors and windows" is not enough.
    """
    blob = '\n'.join(str(x) for x in texts if x)
    g = str(genre or '')

    # ★★★ 2026-10-26 修一个**设计缺陷**：`FANTASY` 既是"兜底档"，又**参与竞争** ——
    #   于是它的强词（祭坛/法阵/dungeon/传送门）只要命中一个，就会"真判"成奇幻。
    #   实测：「西幻城堡」「武侠镖局」「洞穴地下城」全部得到 `是兜底=False` 的"奇幻"，
    #   用户看到的是"已识别：奇幻（照设定画，不套原型）"—— **看起来认出来了，其实没认出来**。
    #   ⇒ 兜底档**不参与竞争**：它只在没有任何真档案过门槛时使用。
    #     这样"判成奇幻"永远等价于"我认不出，所以照你的设定画"，语义只有一种。
    #   ⚠ 代价：真正的奇幻世界（塔/地下城/树屋）也会显示成兜底。这是**对的** ——
    #     奇幻本来就没有统一原型，说"照设定画"比假装认出来更诚实。
    # [EN] ★★★ Fixed a **design flaw** 2026-10-26: `FANTASY` was both the *fallback* and a
    # [EN] *competitor*, so one hit on its strong words (祭坛/法阵/dungeon/传送门) "really judged" it
    # [EN] as fantasy. Measured: a Western castle, a Chinese escort agency and an underground lair all
    # [EN] came back as a non-fallback "fantasy", i.e. the user saw "identified: fantasy" -- **it
    # [EN] looked recognised when it was not**. => The fallback tier **does not compete**; it is used
    # [EN] only when no real profile clears the bar. "Fantasy" then always means "I cannot tell, so
    # [EN] draw what you wrote". ⚠ Cost: genuine fantasy worlds also show as fallback -- which is
    # [EN] **right**, because fantasy has no single prototype and "draw your setting" is more honest
    # [EN] than pretending to recognise it.
    _competitors = [st for st in ALL if st is not FALLBACK]

    best: Match | None = None
    for st in _competitors:
        strong = _count(blob, st.强词)[:3]
        weak = _count(blob, st.弱词)[:4]
        bad = _count(blob, st.反证)

        score = 1.0 * len(strong) + 0.15 * len(weak)
        if bad:
            score *= 0.15
        # 题材弱提示：只认「族」这个层级的词，不认具体题材
        if g and _genre_hint(st, g):
            score += 0.2
        if score <= 0:
            continue
        if best is None or score > best.score:
            best = Match(style=st, score=score, 强命中=strong, 弱命中=weak,
                         是兜底=False)

    if best is None or best.score < 0.5:
        # 判不出来：给兜底，但**把"其实有一点线索"也带回去**，好让打回意见有用
        # [EN] Cannot tell: return the fallback but **keep whatever weak hints existed**, so the
        # [EN] revision notes can still be useful.
        return Match(style=FALLBACK, score=(best.score if best else 0.0),
                     强命中=(best.强命中 if best else ()),
                     弱命中=(best.弱命中 if best else ()),
                     是兜底=True)
    return best


#: 题材 → 可能的族（**弱提示**，绝不是映射表）。
#: ★ 为什么不写成一一对应：`玄幻修仙` 可以是中式仙山、也可以是西幻大陆；
#:   `都市` 可以是现代、也可以是民国。写死了就是"按题材猜建筑"，那是编。
# [EN] Genre -> possible family (**weak hint only**, never a mapping table). ★ Why not one-to-one:
# [EN] "玄幻" may be Chinese immortal mountains or a Western fantasy continent; "都市" may be
# [EN] contemporary or 1930s. Hard-coding it is guessing.
_GENRE_FAMILY = {
    '历史架空': ('cn', 'west'),
    '悬疑灵异': ('modern', 'cn'),
    '玄幻修仙': ('fantasy', 'cn'),
    '科幻': ('future', 'modern'),
    '言情': ('modern', 'cn', 'west'),
    '都市': ('modern',),
}


def _genre_hint(style: Style, genre: str) -> bool:
    for k, fams in _GENRE_FAMILY.items():
        if k in genre:
            return style.族 in fams
    return False


# ══════════════════════════════════════════════════════════════════════
#  四、缺什么：交给美术 Agent 去查
# [EN] 4. What is missing: hand it to the art agent to research
# ══════════════════════════════════════════════════════════════════════
def needs_research(m: Match, *, have: str = '') -> list[str]:
    """列出"要画准还缺什么"，每条都是**一个可查的问题**。

    ★ 为什么必须返回**问题**而不是"缺字段"：美术 Agent 要拿它去查资料
      （`llm` 一次调用就能答），给个字段名它没法查。
    ★ 判成兜底时**多给一条**：先问"这是什么建筑传统" —— 那是根上的问题。
    ★ 已有资料（`have`）里已经写到的就不再问（避免每一轮都问同一件事）。
    [EN] List what is still missing to draw it correctly; every line is **a question worth
    [EN] researching**. ★ They must be **questions** (the art agent researches by asking, and a
    [EN] field name is not searchable). ★ On a fallback, prepend "what tradition is this at all".
    ★ Skip anything already present in `have` (do not ask the same thing every round).
    """
    out: list[str] = []
    if m.是兜底:
        out.append('这处地方属于哪种建筑传统？（中式/西式/现代/未来/其他）依据是哪几个实物？')
    have_t = str(have or '')
    for q in m.style.需查:
        # 粗略去重：问题里的关键字已经出现在已有资料里就不再问
        core = re.sub(r'[（(].*?[）)]', '', q)
        key = core[:6]
        if key and key in have_t:
            continue
        out.append(q)
    return out
