# -*- coding: utf-8 -*-
"""**演员与选角**（`actors/`）。

这个包管一件事：**一个演员是怎么组起来的**。

一句话
------
剧组名册（`crew/roster.py`）管"有哪些**职位**"（作家、剧作者、场记……），
这个包管"有哪些**演员**、他们各自怎么演"。

两层
----
```
预设层（actors/archetypes.yaml）  这一类演员**怎么演** —— 演员自带，不随书变
     ＋
定制层（人物卡 + 选角细读）        在本子里**演谁** —— 剧本给的，一部一换
     ↓
actors/casting.prompt_block()     拼起来，并附上**仲裁规则**
     ↓
agent/core.Agent._persona_prompt  真的进演员每一拍的决策提示词
```

为什么分两层（用户 2026-10-07 的原话）
------------------------------------
「所有Agent 提示词分两部分 一部分预设 一部分根据小说定制，定制的部分优先级高于预设」

这条设计解决的是一个很具体的老毛病：以前"人怎么说话"完全由模型当场决定，
所以同一个人物的台词**换给谁都能说**，两拍之间还会忽冷忽热。
分成两层之后，"怎么演"被固定下来（一类人有一种说话方式），
"演谁"每本书重新给 —— 而**冲突时以角色为准**（只有一处例外，见 `ARBITRATION`）。

同型多人
--------
一个类型被两个人领走时，靠**变奏轴**区分（每型至少 3 条）：
第 1 个用第 1 条、第 2 个用第 2 条……**不是复制粘贴**。
变奏轴同时是反刻板的保证 —— 一个类型只有一种演法，那它就是套路。

用法
----
```python
from actors import casting as C
c = C.instantiate('主角', {'性格': '沉默寡言，记性极好'})
print(c.archetype, '|', c.hit, '|', c.variant)   # 青年·高冷 | 沉默 | 冷在防
block = C.prompt_block(c, {'身份': '帐房', '秘密': '他认得那笔账'})
```

English:
**Actors and casting** (`actors/`).
This package handles one thing: **how an actor is assembled**.
One sentence
------
The crew roster (`crew/roster.py`) manages "which **positions** exist" (writer, playwright,
script supervisor...),
this package manages "which **actors** exist and how each of them performs".
Two layers
----
```
Preset layer (actors/archetypes.yaml) how this type of actor **performs** -- built into the
actor, does not change per book
     +
Custom layer (character card + casting close read) **who** they play in this script -- given by
the script, swapped per book
     ↓
actors/casting.prompt_block()     stitches them together, and attaches **arbitration rules**
     ↓
agent/core.Agent._persona_prompt  actually enters the actor's decision prompt for every beat
```
Why two layers (user's original words, 2026-10-07)
------------------------------------
"All Agent prompts are split into two parts: one part preset, one part customized per novel; the
customized part has higher priority than the preset"
This design solves a very concrete old problem: previously "how a person talks" was decided
entirely on the spot by the model,
so the same character's lines **could be said by anyone**, and between two beats they would
swing hot and cold.
After splitting into two layers, "how to perform" is fixed (one type of person has one way of
speaking),
"who to play" is re-given per book -- and **on conflict the character wins** (only one
exception, see `ARBITRATION`).
Multiple of the same type
--------
When a type is taken by two people, they are distinguished by the **variation axis** (at least 3
per type):
the 1st uses the 1st, the 2nd uses the 2nd... **not copy-paste**.
The variation axis is also the anti-stereotype guarantee -- if a type has only one way to
perform, it is a cliché.
Usage
----
```python
from actors import casting as C
c = C.instantiate('Shen Yan', {'personality': 'silent and taciturn, remembers everything'})
print(c.archetype, '|', c.hit, '|', c.variant)   # youth·aloof | silent | cold as defense
block = C.prompt_block(c, {'identity': 'accountant', 'secret': 'he recognized that account'})
```
"""
from actors import casting  # noqa: F401

__all__ = ['casting']
