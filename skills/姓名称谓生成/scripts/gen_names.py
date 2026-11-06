#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""姓名 / 字 / 号 与称谓生成（技能附带工具，由「姓名称谓生成」技能调用）。

用法
    python gen_names.py --style 唐宋 --n 5
    python gen_names.py --style 明清 --surname 沈 --n 5
    python gen_names.py --titles 主角 --identity 官员
    python gen_names.py --styles
    python gen_names.py --style 魏晋 --n 3 --seed 7     # 固定随机种子，结果可复现

说明
    生成的是**风格合规**的名字，不是历史真人。用之前自己念两遍——
    读起来顺不顺、有没有谐音不雅，机器判断不了。

English:
Given name / courtesy name / art name and appellation generation (skill-attached tool, invoked
by the "given name and appellation generation" skill).
Usage
    python gen_names.py --style 唐宋 --n 5
    python gen_names.py --style 明清 --surname 沈 --n 5
    python gen_names.py --styles
    python gen_names.py --style 魏晋 --n 3 --seed 7     # fixed random seed, results are reproducible
Notes
    What is generated is **style-compliant** names, not historical real people. Before using them, read them aloud yourself --
    whether they read smoothly or have unfortunate homophones is something a machine cannot judge.
"""
from __future__ import annotations

import random
import sys

SURNAMES = ['沈', '陆', '顾', '谢', '裴', '崔', '柳', '苏', '程', '林',
            '江', '许', '宋', '温', '贺', '邵', '韩', '白', '杜', '岑']

# 风格 → (名字用字, 字用字, 号用字)
# [EN] Style → (characters used for given name, courtesy name, art name)
STYLES = {
    '先秦': (
        ['纠', '突', '忽', '无咎', '无知', '匄', '夷吾', '重', '牟', '季',
         '获', '戍', '磬', '般', '黑臀', '杵臼'],
        ['子', '伯', '仲', '叔', '季'],
        [''],
    ),
    '汉魏': (
        ['广', '信', '霸', '武', '通', '禹', '参', '安', '充', '虑',
         '章', '晏', '统', '萌', '丰', '勋'],
        ['子', '公', '伯', '文', '元'],
        ['先生'],
    ),
    '魏晋': (
        ['羲', '之', '道', '虔', '澈', '澹', '渊', '寂', '朗', '玄',
         '徽', '衍', '湛', '畅', '粲'],
        ['子', '叔', '季', '道', '僧'],
        ['居士', '山人', '子'],
    ),
    '唐宋': (
        ['观', '澈', '澈明', '延', '晦', '商', '隐', '牧', '邺', '适',
         '颢', '翰', '涣', '澈之', '彦', '闳'],
        ['子', '伯', '叔', '季', '仲', '德', '文', '君'],
        ['居士', '山人', '处士', '野老'],
    ),
    '明清': (
        ['居正', '廷', '岳', '应', '启', '慎', '承', '允', '敬', '焕',
         '鹤', '襄', '维', '宗', '守', '元'],
        ['叔', '大', '伯', '季', '子', '文', '公'],
        ['先生', '山人', '主人', '居士'],
    ),
}

# 身份 → 称谓表（自称 / 对称 / 上称别人）
# [EN] Identity → appellation table (self-reference / address to other / reference to others)
TITLES = {
    '官员': {
        '自称': ['下官', '卑职', '臣（对君）'],
        '对称': ['{官}大人', '{姓}大人', '{字}兄（同僚平辈）'],
        '提及家人': ['家父 / 内子 / 犬子', '对方：令尊 / 尊夫人 / 令郎'],
        '备注': '明清官场以「姓+官职/大人」为常；唐宋多用官称或字。',
    },
    '文士': {
        '自称': ['仆', '不才', '愚'],
        '对称': ['{字}兄', '先生', '{号}先生'],
        '提及家人': ['家父 / 拙荆 / 犬子', '对方：令尊 / 尊夫人 / 令郎'],
        '备注': '文人之间称字称号，最忌直呼其名。',
    },
    '商人': {
        '自称': ['小的', '在下', '敝人'],
        '对称': ['{姓}员外', '{姓}掌柜', '老板（近代感，慎用）'],
        '提及家人': ['家父 / 贱内', '对方：令尊 / 尊夫人'],
        '备注': '对官面自称「小的」「草民」；同行可称「某掌柜」。',
    },
    '仆役': {
        '自称': ['小的', '奴才（清，旗人家）', '奴婢（女）'],
        '对称': ['老爷', '夫人', '公子', '小姐', '少爷（明清以后）'],
        '提及家人': ['家父 / 贱内', '—'],
        '备注': '对主人一律用「老爷/夫人」类称呼，绝不自称「我」。',
    },
    '女性（闺秀）': {
        '自称': ['妾', '妾身', '儿（对父母）'],
        '对称': ['{字}兄（对平辈男子）', '夫人（对已婚）', '娘子（唐以后）'],
        '提及家人': ['家父 / 家母', '对方：令尊 / 令堂'],
        '备注': '闺名不外传，对外多称「某氏」或「夫姓+本姓」（王李氏）。',
    },
    '武人': {
        '自称': ['末将', '属下', '某'],
        '对称': ['{姓}将军', '{官职}', '老兄（同袍）'],
        '提及家人': ['家父 / 拙荆', '对方：令尊 / 尊夫人'],
        '备注': '上下级分明；同袍间可粗直，但称上官仍要官称。',
    },
}

# 字号搭配的常见关联（名 → 字的取义方向）
# [EN] Common associations in given name and courtesy name pairing (given name → the meaning direction
# [EN] of the courtesy name)
ZI_HINT = {
    '砚': '取「砚之/石溪」一类，与文房相关',
    '渊': '取「子渊/渊如」一类，与水相关',
    '鹤': '取「云龄/鸣皋」一类，与高洁相关',
    '岳': '取「仲山/维岳」一类，与山岳相关',
}


def gen_one(surnames: list[str], names: list[str], zis: list[str],
            haos: list[str], rng: random.Random) -> dict:
    surname = rng.choice(surnames)
    name = rng.choice(names)
    # 字：常见结构是「子/伯/叔/季 + 一字」或「与名相承的一字」
    # [EN] Courtesy name: common structures are "子/伯/叔/季 + one character" or "one character that echoes the
    # [EN] given name"
    zi = ''
    if rng.random() < 0.6:
        zi = rng.choice(zis) + (name[0] if len(name) == 1 else '之')
    else:
        zi = rng.choice(zis) + rng.choice(['甫', '卿', '元', '言', '文'])
    hao = ''
    if haos and haos[0] and rng.random() < 0.5:
        hao = rng.choice(['城南', '西溪', '青岩', '柳下', '听雨', '半山',
                          '石泉', '东篱']) + rng.choice(haos)
    return {'姓': surname, '名': name, '字': zi, '号': hao}


def cmd_styles() -> None:
    print('可用风格：')
    for s in STYLES:
        print(f'  {s}')
    print('\n可用身份：')
    for k in TITLES:
        print(f'  {k}')


def cmd_gen(style: str, surname: str | None, n: int, seed: int | None) -> None:
    if style not in STYLES:
        print(f'不认识的风格：{style}。可用：{"、".join(STYLES)}', file=sys.stderr)
        sys.exit(2)
    names, zis, haos = STYLES[style]
    surnames = [surname] if surname else SURNAMES
    rng = random.Random(seed)

    print(f'风格：{style}　姓氏：{surname or "随机"}　共 {n} 个\n')
    for i in range(n):
        p = gen_one(surnames, names, zis, haos, rng)
        full = p['姓'] + p['名']
        line = f'  {full:<6s}  字 {p["字"]:<6s}'
        if p['号']:
            line += f'  号 {p["号"]}'
        print(line)
        hint = ZI_HINT.get(p['名'])
        if hint:
            print(f'            └ {hint}')
    print('\n提示：平辈对称用「字」，长辈/自谦用「名」；直呼人「名」是失礼。')


def cmd_titles(name: str, identity: str, zi: str = '', hao: str = '') -> None:
    if identity not in TITLES:
        print(f'不认识的身份：{identity}。可用：{"、".join(TITLES)}', file=sys.stderr)
        sys.exit(2)
    surname = name[0] if name else ''
    table = TITLES[identity]
    print(f'人物：{name}　身份：{identity}\n')
    for key in ('自称', '对称', '提及家人', '备注'):
        vals = table.get(key) or []
        if isinstance(vals, str):
            vals = [vals]
        vals = [v for v in vals if v and v != '—']       # 过滤空项与占位符
        # [EN] Filter empty entries and placeholders
        if not vals:
            continue
        rendered = [v.replace('{姓}', surname).replace('{字}', zi or '（未定字）')
                     .replace('{号}', hao or '（未定号）')
                     .replace('{官}', '知府') for v in vals]
        print(f'  {key}：{" / ".join(rendered)}')
    print('\n也可用：称官（姓+官职）、称地望（籍贯）、称谥号。')


def main() -> None:
    args = sys.argv[1:]
    if not args or '--styles' in args:
        cmd_styles()
        return

    def value_of(flag: str) -> str | None:
        if flag in args:
            i = args.index(flag)
            if i + 1 < len(args):
                return args[i + 1]
        return None

    if '--titles' in args:
        name = value_of('--titles') or ''
        cmd_titles(name, value_of('--identity') or '文士',
                   zi=value_of('--zi') or '', hao=value_of('--hao') or '')
        return

    try:
        n = int(value_of('--n') or 5)
    except ValueError:
        n = 5
    try:
        seed = int(value_of('--seed')) if '--seed' in args else None
    except ValueError:
        seed = None
    cmd_gen(value_of('--style') or '唐宋', value_of('--surname'), n, seed)


if __name__ == '__main__':
    main()
