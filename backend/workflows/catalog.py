from backend.workflows.models import AgentSpec, WorkflowTemplate


TEACHING_TEMPLATE = WorkflowTemplate(
    id="teaching_design",
    name="多智能体课程教学设计",
    description="教师剖析课程材料并设计教学，学生分层提问，教师答疑，督导逐轮点评改进。",
    category="课程教学",
    agents=[
        AgentSpec(id="content_analysis", name="课程内容分析", role="teacher", description="识别知识结构、重点与认知难点", accent="#28765b"),
        AgentSpec(id="teaching_design", name="教学环节设计", role="teacher", description="形成目标、活动、策略与评价框架", accent="#2f6f9f"),
        AgentSpec(id="teach_knowledge", name="教师讲授", role="teacher", description="按教学方案实施分轮讲授", accent="#2d7a66"),
        AgentSpec(id="student_question", name="学生提问", role="student", description="优秀、中等和基础学生从不同层次提问", accent="#b1742d"),
        AgentSpec(id="teacher_answer", name="教师答疑", role="teacher", description="回应学生疑问并澄清误区", accent="#476fa8"),
        AgentSpec(id="supervisor_comment", name="督导点评", role="supervisor", description="评价教学设计、讲授方式和回答质量", accent="#9a4b50"),
        AgentSpec(id="finalize", name="教学成果", role="finalize", description="汇总教学过程与改进建议", accent="#5c6570"),
    ],
    review_threshold=85,
)


def list_templates() -> list[WorkflowTemplate]:
    return [TEACHING_TEMPLATE]


def get_template(template_id: str) -> WorkflowTemplate | None:
    return TEACHING_TEMPLATE if template_id == TEACHING_TEMPLATE.id else None
