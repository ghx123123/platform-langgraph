from types import SimpleNamespace

import pytest

from backend.classroom.repository import ClassroomRepository
from backend.classroom.router import role_settings, save_role_settings, delete_role_version
from backend.classroom.router import generate_role_settings


@pytest.mark.asyncio
async def test_generate_is_draft_only_and_preserves_dimensions(tmp_path):
    import json
    repo = ClassroomRepository(tmp_path / 'draft.db')
    await repo.initialize()
    class Engine:
        async def generate(self, system, user):
            assert '不修改编排接口' in system
            assert '谨慎' in user
            return json.dumps({'role_definition': '谨慎的学生', 'system_prompt': '遇到困难先表达不确定。', 'evaluation_focus': ['changed']})
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        classroom_service=SimpleNamespace(repository=repo),
        workflow_service=SimpleNamespace(model=SimpleNamespace(provider='dsh', ensure_dsh_engine=lambda: Engine())))))
    result = await generate_role_settings('run-a', 'student:low', request, {
        'requirement': '更加谨慎', 'profile': {'role_definition': '学生', 'system_prompt': '保持基础水平', 'evaluation_focus': []}})
    assert result['system_prompt']
    assert result['evaluation_focus'] == []
    assert await repo.get_agent_instance('run-a', 'student:low') is None


@pytest.mark.asyncio
async def test_role_versions_retention_and_isolation(tmp_path):
    repo = ClassroomRepository(tmp_path / 'roles.db')
    await repo.initialize()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        classroom_service=SimpleNamespace(repository=repo))))
    for index in range(4):
        result = await save_role_settings('run-a', 'teacher', request, {
            'role_definition': 'Teacher', 'system_prompt': f'Prompt {index}'})
    assert len(result['versions']) == 3
    assert result['profile']['system_prompt'] == 'Prompt 3'
    result = await delete_role_version('run-a', 'teacher', result['versions'][0]['id'], request)
    assert len(result['versions']) == 2
    assert result['profile']['system_prompt'] == 'Prompt 3'
    other = await role_settings('run-b', 'teacher', request)
    assert other['versions'] == []
    assert (await role_settings('run-a', 'student:low', request))['versions'] == []
