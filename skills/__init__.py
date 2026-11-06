# -*- coding: utf-8 -*-
"""技能系统（设计稿 §8.6）。

  registry.py  扫描 skills/<技能名>/SKILL.md，按「触发关键词」路由
  <技能名>/     每个技能一个目录，至少含 SKILL.md（YAML frontmatter + 正文）

注意这个目录是**双重身份**：既是 Python 包（本文件、registry.py），
也是技能内容目录（各子目录）。注册表只认「子目录 + SKILL.md」的组合，
所以不会把 .py 文件误当技能。

写自己的技能见 skills/README.md。

English:
Skills system (design doc §8.6).
  registry.py  scans skills/<skill-name>/SKILL.md, routes by "trigger keywords"
  <skill-name>/     one directory per skill, containing at least SKILL.md (YAML frontmatter + body)
Note this directory has a **dual identity**: it is both a Python package (this file,
registry.py)
and a skill content directory (the subdirectories). The registry only recognizes the combination
of "subdirectory + SKILL.md",
so it will not mistake .py files for skills.
To write your own skill see skills/README.md.
"""
