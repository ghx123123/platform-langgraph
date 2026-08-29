"""
PDF报告生成服务测试
"""
import os
import sys
import uuid
from datetime import datetime, timedelta

# 添加项目根目录到路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)
sys.path.insert(0, os.path.dirname(backend_dir))  # 添加项目根目录

# 设置环境变量避免某些导入问题
os.environ.setdefault('PYTHONPATH', str(backend_dir))

# 直接导入模块而不是通过包
try:
    from teaching.session import TeachingSession, KnowledgePoint, SupervisorSuggestion, TeachingAgent, AgentType
    from teaching.evaluation_models import QuizResult, QuizAnswer, InteractionNode, InteractionType
    from teaching.pdf_report_service import PDFReportService, generate_teaching_report
except ModuleNotFoundError as e:
    print(f"导入错误: {e}")
    print("尝试直接导入...")
    # 如果导入失败，直接导入本地文件
    import importlib.util
    
    def load_module_from_path(module_name, file_path):
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    
    teaching_dir = os.path.join(backend_dir, 'teaching')
    session_module = load_module_from_path('session', os.path.join(teaching_dir, 'session.py'))
    eval_module = load_module_from_path('evaluation_models', os.path.join(teaching_dir, 'evaluation_models.py'))
    pdf_module = load_module_from_path('pdf_report_service', os.path.join(teaching_dir, 'pdf_report_service.py'))
    
    TeachingSession = session_module.TeachingSession
    KnowledgePoint = session_module.KnowledgePoint
    SupervisorSuggestion = session_module.SupervisorSuggestion
    TeachingAgent = session_module.TeachingAgent
    AgentType = session_module.AgentType
    
    QuizResult = eval_module.QuizResult
    QuizAnswer = eval_module.QuizAnswer
    InteractionNode = eval_module.InteractionNode
    InteractionType = eval_module.InteractionType
    
    PDFReportService = pdf_module.PDFReportService
    generate_teaching_report = pdf_module.generate_teaching_report


def create_test_session():
    """创建测试用的教学会话"""
    session = TeachingSession(
        title="Python面向对象编程基础",
        session_id=str(uuid.uuid4()),
        max_iterations=3,
    )
    
    # 设置状态为已完成
    session.status = "completed"
    session.current_iteration = 3
    session.completed_at = datetime.now()
    
    # 添加知识点
    knowledge_points = [
        KnowledgePoint(
            title="类与对象的概念",
            chapter="第1章 面向对象基础",
            is_key_point=True,
            difficulty_level="中等",
            keywords=["类", "对象", "实例"]
        ),
        KnowledgePoint(
            title="构造函数__init__",
            chapter="第2章 类定义",
            is_key_point=True,
            difficulty_level="中等",
            keywords=["__init__", "构造函数", "初始化"]
        ),
        KnowledgePoint(
            title="实例方法与self参数",
            chapter="第2章 类定义",
            is_key_point=True,
            difficulty_level="中等",
            keywords=["self", "实例方法", "方法定义"]
        ),
        KnowledgePoint(
            title="类属性与实例属性",
            chapter="第3章 属性",
            is_key_point=False,
            difficulty_level="简单",
            keywords=["类属性", "实例属性"]
        ),
        KnowledgePoint(
            title="继承与多态",
            chapter="第4章 继承",
            is_key_point=True,
            difficulty_level="困难",
            keywords=["继承", "多态", "父类", "子类"]
        ),
        KnowledgePoint(
            title="方法重写",
            chapter="第4章 继承",
            is_key_point=True,
            difficulty_level="中等",
            keywords=["重写", "覆盖", "override"]
        ),
        KnowledgePoint(
            title="封装与访问控制",
            chapter="第5章 封装",
            is_key_point=True,
            difficulty_level="中等",
            keywords=["封装", "私有", "保护"]
        ),
        KnowledgePoint(
            title="属性装饰器@property",
            chapter="第5章 封装",
            is_key_point=False,
            difficulty_level="困难",
            keywords=["@property", "装饰器", "getter", "setter"]
        ),
    ]
    session.knowledge_points = knowledge_points
    
    # 添加教学框架
    session.teaching_framework = {
        "objectives": [
            "理解面向对象编程的核心概念",
            "掌握Python类定义和对象创建",
            "理解继承和多态机制",
            "学会使用封装保护数据",
            "能够设计简单的面向对象程序"
        ],
        "duration": 90,
        "difficulty": "中等"
    }
    
    # 添加讲课稿
    session.teaching_script = """
    同学们好，今天我们开始学习Python面向对象编程。面向对象编程（OOP）是一种程序设计思想，
    它将数据和操作数据的方法组织在一起，形成"对象"。
    
    首先，我们来理解类和对象的概念。类是对一类事物的抽象描述，而对象则是类的具体实例。
    比如，"动物"是一个类，而"小猫"、"小狗"则是动物类的实例。
    
    在Python中，我们使用class关键字来定义类。每个类都有一个特殊的__init__方法，
    称为构造函数，它在创建对象时自动调用，用于初始化对象的属性。
    
    实例方法的第一个参数必须是self，它代表对象本身。通过self，我们可以访问对象的属性和方法。
    
    继承是面向对象的重要特性，它允许子类继承父类的属性和方法，同时可以添加新的功能或重写父类的方法。
    
    封装是将数据和对数据的操作封装在一起，隐藏内部实现细节，只暴露必要的接口。
    在Python中，我们使用单下划线表示保护属性，双下划线表示私有属性。
    """
    
    # 添加督导建议
    suggestions = [
        SupervisorSuggestion(
            session_id=session.id,
            agent_id="supervisor_1",
            agent_name="教学督导员A",
            iteration=1,
            phase="supervisor_comment",
            suggestion_content="建议在讲解self参数时增加更多代码示例，帮助学生理解。",
            dimension="教学内容"
        ),
        SupervisorSuggestion(
            session_id=session.id,
            agent_id="supervisor_1",
            agent_name="教学督导员A",
            iteration=1,
            phase="supervisor_comment",
            suggestion_content="可以增加一些实际案例，如设计一个简单的银行账户类。",
            dimension="教学方法"
        ),
        SupervisorSuggestion(
            session_id=session.id,
            agent_id="supervisor_2",
            agent_name="教学督导员B",
            iteration=2,
            phase="supervisor_comment",
            suggestion_content="继承部分的讲解比较抽象，建议用图形化方式展示类层次结构。",
            dimension="教学内容"
        ),
        SupervisorSuggestion(
            session_id=session.id,
            agent_id="supervisor_2",
            agent_name="教学督导员B",
            iteration=2,
            phase="supervisor_comment",
            suggestion_content="可以增加互动环节，让学生现场编写代码并演示。",
            dimension="课堂互动"
        ),
        SupervisorSuggestion(
            session_id=session.id,
            agent_id="supervisor_1",
            agent_name="教学督导员A",
            iteration=3,
            phase="supervisor_comment",
            suggestion_content="整体教学效果良好，学生反馈积极。",
            dimension="综合评价"
        ),
    ]
    session.supervisor_suggestions = suggestions
    
    # 添加学习目标
    session.learning_objectives = [
        {"id": "obj_1", "description": "理解面向对象编程的核心概念", "type": "knowledge"},
        {"id": "obj_2", "description": "掌握Python类定义和对象创建", "type": "skill"},
        {"id": "obj_3", "description": "理解继承和多态机制", "type": "knowledge"},
        {"id": "obj_4", "description": "学会使用封装保护数据", "type": "skill"},
    ]
    
    # 添加目标评估
    session.objective_assessments = [
        {"objective_id": "obj_1", "coverage_score": 95, "evidence": "课堂提问显示学生理解良好", "gaps": [], "suggestions": []},
        {"objective_id": "obj_2", "coverage_score": 85, "evidence": "学生能够编写简单类", "gaps": ["复杂类设计"], "suggestions": ["增加实践练习"]},
        {"objective_id": "obj_3", "coverage_score": 75, "evidence": "部分学生理解有困难", "gaps": ["多重继承", "抽象类"], "suggestions": ["增加案例分析", "提供参考资料"]},
        {"objective_id": "obj_4", "coverage_score": 80, "evidence": "基本理解封装概念", "gaps": ["属性装饰器"], "suggestions": ["深入讲解@property"]},
    ]
    
    return session


def create_test_interaction_path():
    """创建测试用的互动路径数据"""
    base_time = datetime.now() - timedelta(hours=1)
    
    interactions = [
        {
            "id": "int_1",
            "interaction_type": "question",
            "agent_id": "student_1",
            "agent_name": "学生A",
            "agent_type": "student",
            "content": "self参数是必须的吗？可以改成其他名字吗？",
            "created_at": base_time.isoformat(),
        },
        {
            "id": "int_2",
            "interaction_type": "answer",
            "agent_id": "teacher_1",
            "agent_name": "教师",
            "agent_type": "teacher",
            "content": "self不是关键字，可以改成其他名字，但强烈建议保持使用self，这是Python的约定俗成。",
            "parent_id": "int_1",
            "created_at": (base_time + timedelta(minutes=2)).isoformat(),
        },
        {
            "id": "int_3",
            "interaction_type": "question",
            "agent_id": "student_2",
            "agent_name": "学生B",
            "agent_type": "student",
            "content": "继承和组合有什么区别？什么时候用继承，什么时候用组合？",
            "created_at": (base_time + timedelta(minutes=15)).isoformat(),
        },
        {
            "id": "int_4",
            "interaction_type": "answer",
            "agent_id": "teacher_1",
            "agent_name": "教师",
            "agent_type": "teacher",
            "content": "继承是'是一个'关系，组合是'有一个'关系。当子类是父类的一种特殊类型时用继承，否则用组合。",
            "parent_id": "int_3",
            "created_at": (base_time + timedelta(minutes=18)).isoformat(),
        },
        {
            "id": "int_5",
            "interaction_type": "comment",
            "agent_id": "supervisor_1",
            "agent_name": "督导员A",
            "agent_type": "supervisor",
            "content": "建议在讲解继承时增加更多代码示例。",
            "created_at": (base_time + timedelta(minutes=20)).isoformat(),
        },
        {
            "id": "int_6",
            "interaction_type": "question",
            "agent_id": "student_3",
            "agent_name": "学生C",
            "agent_type": "student",
            "content": "私有属性真的可以完全保护数据吗？",
            "created_at": (base_time + timedelta(minutes=35)).isoformat(),
        },
        {
            "id": "int_7",
            "interaction_type": "answer",
            "agent_id": "teacher_1",
            "agent_name": "教师",
            "agent_type": "teacher",
            "content": "Python的私有属性是通过名称改写实现的，技术上还是可以访问的，但这是一种约定，表示不应该直接访问。",
            "parent_id": "int_6",
            "created_at": (base_time + timedelta(minutes=38)).isoformat(),
        },
        {
            "id": "int_8",
            "interaction_type": "comment",
            "agent_id": "supervisor_2",
            "agent_name": "督导员B",
            "agent_type": "supervisor",
            "content": "学生参与度很高，互动效果好。",
            "created_at": (base_time + timedelta(minutes=45)).isoformat(),
        },
    ]
    
    return interactions


def create_test_quiz_result():
    """创建测试用的测验结果"""
    quiz_result = QuizResult(
        quiz_id=str(uuid.uuid4()),
        total_score=82.5,
        max_score=100.0,
        passed=True,
        weak_knowledge_points=[
            "多重继承的理解",
            "抽象类的使用",
            "元类的概念"
        ],
        improvement_suggestions=[
            "建议复习第4章关于多重继承的内容",
            "完成课后练习第5、6题",
            "阅读推荐阅读材料《Python设计模式》",
            "参加下周的答疑课，解决疑难问题"
        ]
    )
    
    # 添加答案记录
    quiz_result.answers = [
        QuizAnswer(
            quiz_id=quiz_result.quiz_id,
            question_id="q1",
            answer_text="类是对象的抽象，对象是类的实例",
            is_correct=True,
            score=10.0
        ),
        QuizAnswer(
            quiz_id=quiz_result.quiz_id,
            question_id="q2",
            answer_text="self代表类的实例本身",
            is_correct=True,
            score=10.0
        ),
        QuizAnswer(
            quiz_id=quiz_result.quiz_id,
            question_id="q3",
            answer_text="继承允许子类使用父类的属性和方法",
            is_correct=True,
            score=10.0
        ),
        QuizAnswer(
            quiz_id=quiz_result.quiz_id,
            question_id="q4",
            answer_text="错误答案",
            is_correct=False,
            score=2.5
        ),
    ]
    
    return quiz_result


def test_pdf_generation():
    """测试PDF报告生成"""
    print("=" * 60)
    print("PDF报告生成服务测试")
    print("=" * 60)
    
    # 创建测试数据
    print("\n[1/4] 创建测试数据...")
    session = create_test_session()
    interaction_path = create_test_interaction_path()
    quiz_result = create_test_quiz_result()
    print(f"  - 会话ID: {session.id[:8]}")
    print(f"  - 知识点数量: {len(session.knowledge_points)}")
    print(f"  - 督导建议数量: {len(session.supervisor_suggestions)}")
    print(f"  - 互动记录数量: {len(interaction_path)}")
    
    # 初始化服务
    print("\n[2/4] 初始化PDF报告服务...")
    service = PDFReportService()
    print(f"  - 使用字体: {service.font_name}")
    print(f"  - 输出目录: {service.output_dir}")
    
    # 生成报告
    print("\n[3/4] 生成PDF报告...")
    try:
        output_path = service.generate_pdf_report(
            session=session,
            interaction_path=interaction_path,
            quiz_result=quiz_result
        )
        print(f"  [OK] 报告生成成功!")
        print(f"  - 文件路径: {output_path}")
        
        # 检查文件
        import os
        file_size = os.path.getsize(output_path)
        print(f"  - 文件大小: {file_size / 1024:.1f} KB")
        
    except Exception as e:
        print(f"  [ERROR] 报告生成失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 测试便捷函数
    print("\n[4/4] 测试便捷函数...")
    try:
        output_path2 = generate_teaching_report(
            session=session,
            interaction_path=interaction_path,
            quiz_result=quiz_result
        )
        print(f"  [OK] 便捷函数调用成功!")
        print(f"  - 文件路径: {output_path2}")
    except Exception as e:
        print(f"  [ERROR] 便捷函数调用失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
    return True


def test_font_registration():
    """测试字体注册"""
    print("\n" + "-" * 60)
    print("字体注册测试")
    print("-" * 60)
    
    from teaching.pdf_report_service import FontManager
    
    font_name = FontManager.register_fonts()
    print(f"可用字体: {font_name}")
    print(f"已注册字体: {list(FontManager._registered_fonts.keys())}")
    
    return True


if __name__ == "__main__":
    # 测试字体注册
    test_font_registration()
    
    # 测试PDF生成
    success = test_pdf_generation()
    
    # 退出码
    sys.exit(0 if success else 1)
