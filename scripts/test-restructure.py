# test-restructure.py — 验证 restructure_outline: 合并 1.1 和 1.2
import asyncio, sys
sys.path.insert(0, '.')
from backend.material_units.service import restructure_outline

base = {
    'version': 1, 'title': '第1章 Python 概述', 'status': 'draft',
    'nodes': [
        {'id': 'n1', 'parent_id': None, 'level': 1, 'title': '第1章 Python 概述', 'description': '', 'is_key_point': False, 'is_difficult_point': False, 'teacher_note': '', 'evidence': [{'source_type': 'teacher', 'quote': '教材', 'label': '教材'}]},
        {'id': 'n1a', 'parent_id': 'n1', 'level': 2, 'title': '1.1 Python 语言简介', 'description': '语言简介', 'is_key_point': False, 'is_difficult_point': False, 'teacher_note': '', 'evidence': [{'source_type': 'teacher', 'quote': '1.1', 'label': '教材'}]},
        {'id': 'n1b', 'parent_id': 'n1', 'level': 2, 'title': '1.2 Python 版本简介', 'description': '版本简介', 'is_key_point': False, 'is_difficult_point': False, 'teacher_note': '', 'evidence': [{'source_type': 'teacher', 'quote': '1.2', 'label': '教材'}]},
    ],
    'source_material_ids': [], 'teacher_instruction': '', 'change_summary': '创建知识大纲', 'based_on_version': None,
}
# 模型返回: 合并 1.1 与 1.2 → 新节点"1.1 Python 语言与版本简介"
model_nodes = [
    {'title': '第1章 Python 概述', 'level': 1, 'parent_id': None, 'description': '概述'},
    {'title': '1.1 Python 语言与版本简介', 'level': 2, 'parent_id': '第1章 Python 概述', 'description': '合并了语言简介与版本简介的说明。'},
]
v = restructure_outline(base, '合并1.1和1.2', model_nodes)
print('version:', v['version'])
print('summary:', v['change_summary'])
for n in v['nodes']:
    print(' -', n['level'], n['title'], '| parent:', n['parent_id'], '| evidence:', len(n['evidence']))
# 校验
from backend.material_units.models import KnowledgeOutline
import json
v2 = dict(v)
v2['id'] = 'o1'; v2['unit_id'] = 'u1'; v2['created_at'] = 'x'; v2['updated_at'] = 'x'
outline = KnowledgeOutline.model_validate(v2)
print('KnowledgeOutline validate OK, nodes:', len(outline.nodes))
