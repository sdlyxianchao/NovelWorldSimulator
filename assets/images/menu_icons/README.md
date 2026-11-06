# 开始菜单的彩色图标

界面（开始界面左侧那个菜单）八项图标用的位图。**不是**手绘素材，来源与许可见下。

## 来源与许可

| | |
|---|---|
| 素材库 | [microsoft/fluentui-emoji](https://github.com/microsoft/fluentui-emoji)（微软官方表情库） |
| 许可 | **MIT License** —— 允许使用、复制、修改、合并、发布、再分发，含商用；唯一义务是保留版权与许可声明（本页即是） |
| 版权 | Copyright (c) Microsoft Corporation |
| 取用通道 | `https://cdn.jsdelivr.net/gh/microsoft/fluentui-emoji@main/assets/…` |
| 取用日期 | 2026-10-10 |
| 本项目做的处理 | 裁掉四周空白 → 按最长边等比缩放到 128×128 透明画布（留白 10%）→ 另存一份去色褪色版（`_dim`） |

为什么不用别的常见图标库：Twemoji / OpenMoji 是 **CC-BY / CC-BY-SA**，要求
"使用时署名"，桌面程序里没有合适的地方挂署名；Fluent Emoji 是 MIT，署名义务
落到这个文件里就够了。

## 文件

| 文件 | 用在哪 |
|---|---|
| `<槽位>.png` | 正常状态 |
| `<槽位>_dim.png` | 同一张的**去色褪色版**，那一项**不可点**时用（与标题一起灰） |
| `src/…` | 下载的原始素材（`.svg` = 扁平彩色，`.png` = 立体彩色），留档，便于离线重建 |

槽位 → 菜单项 → 素材：

| 槽位 | 菜单项 | 素材条目 | 备注 |
|---|---|---|---|
| `open_book` | 开　卷 | Open book | |
| `books` | 拾　卷 | Books | |
| `play` | 起　笔 | Play button | |
| `puzzle` | 拆　书 | Puzzle piece | 用户点名要"拼图" |
| `gear` | 天　机 | Gear | 用户点名要"全局设置"的意思 |
| `brush` | 书　斋 | Paintbrush | |
| `rewind` | 回　卷 | Fast reverse button | 见下 |
| `door` | 归　去 | Door | 用户点名要"门 + 从门里离开" |

## 关于「回　卷」这一个

用户 2026-10-10 点名要的形状是：**下面一横、上面一个向左的逆时针箭头**
（Material 的 `SETTINGS_BACKUP_RESTORE`）。**emoji 里没有这个字形** ——
所以退到候选里挑最接近的：默认 `Fast reverse button`（⏪，语义="倒回/回到之前"）。
同一批候选（`Counterclockwise arrows button` ⏄ / `Left arrow` / `Back arrow` /
`Right arrow curving left`）都能在 `assets/screenshots/menu_icons_sheet.png`
里看到实际效果，换一个只要改 `developers/make_menu_icons.py` 的 `SLOTS`
那一行 + `gui/app_flet.py` 里对应的素材名，然后重跑生成脚本。

## 两种风格 & 怎么重建

风格写在**同一批文件名**里，所以换风格不需要改产品代码：

```bash
.venv/Scripts/python.exe developers/make_menu_icons.py --fetch --both-styles  # 抓素材（联网）
.venv/Scripts/python.exe developers/make_menu_icons.py                        # 扁平彩色（默认）
.venv/Scripts/python.exe developers/make_menu_icons.py --style 3d             # 立体彩色
```

`--style color` 要用 **Edge 无头截图**把 SVG 画成 PNG（本机没装 SVG 光栅化库）。
这只影响**开发期重建**；程序运行时只读 PNG，不依赖 Edge、不联网。
