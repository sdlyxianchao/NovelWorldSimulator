# -*- coding: utf-8 -*-
"""剧情层：把一次推演摊成「一条从头到尾的故事线」（剧情总览）。

当前只有 `flow` 一个模块。它**不调模型、不碰界面** —— 纯读盘 + 纯函数，
所以「日界自动刷新」和「对话框打开时补算」用的是同一份代码。

English:
Plot layer: lay one run out as "a story line from start to finish" (the story overview).
For now it holds a single module, `flow`. It **calls no model and touches no UI** -- it only reads
disk and runs pure functions, so "refresh at the day boundary" and "fill in when the dialog opens"
share the exact same code.
"""
