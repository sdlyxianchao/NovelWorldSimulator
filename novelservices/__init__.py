# -*- coding: utf-8 -*-
"""`novelservices` —— NovelWorldSimulator 旁挂的服务目录。

这个包本身只是个**入口**，里面装的是与主程序解耦的东西：

| 成员 | 是什么 |
|---|---|
| `mumu_bridge.py` | 让主程序（剧组 Agent）能调用 MuMuAINovel 写小说的**接入层** |
| `MuMuAINovel/`   | 接入的开源写作服务本体（上游见 `MuMuAINovel/服务说明.md`） |

两条纪律：

1. **可有可无。** 主程序**不 import 它也能跑**（桥接层是懒加载的），
   服务没起、目录被删掉，主程序只是少一项增强，不该报错、不该拒绝启动。
2. **不写死盘符。** 路径一律从 `__file__` 推（见 `MuMuAINovel/nws_paths.py`），
   整个 NovelWorldSimulator 文件夹搬到哪儿都能用。

English:
`novelservices` —— service directory attached to NovelWorldSimulator.
This package itself is just an **entry point**; what it contains is decoupled from the main
program:
| Member | What it is |
|---|---|
| `mumu_bridge.py` | The **integration layer** that lets the main program (the crew Agent) call MuMuAINovel to write novels |
| `MuMuAINovel/`   | The body of the integrated open-source writing service (upstream see `MuMuAINovel/服务说明.md`) |
Two rules:
1. **Optional.** The main program **can run without importing it** (the bridge layer is lazy-loaded),
   if the service isn't started or the directory is deleted, the main program just loses one enhancement; it should not error or refuse to start.
2. **No hardcoded drive letters.** Paths are always derived from `__file__` (see `MuMuAINovel/nws_paths.py`),
   so the entire NovelWorldSimulator folder works no matter where it is moved.
"""
