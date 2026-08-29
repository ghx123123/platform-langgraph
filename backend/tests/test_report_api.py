"""
报告导出API集成测试

测试内容：
1. GET /api/teaching/sessions/{session_id}/report/pdf - 生成并下载PDF报告
2. GET /api/teaching/sessions/{session_id}/report/status - 检查报告生成状态

运行方式：
    cd backend
    python -m pytest tests/test_report_api.py -v

或者：
    python tests/test_report_api.py
"""
import os
import sys
import uuid
import time
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# 添加项目路径
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)
sys.path.insert(0, os.path.dirname(backend_dir))

# FastAPI测试客户端
from fastapi.testclient import TestClient
from fastapi import FastAPI

# 导入测试目标
from backend.teaching.router import router as teaching_router
from backend.teaching import get_teaching_manager, TeachingSession, TeachingStatus
from backend.teaching.evaluation_models import QuizResult, QuizAnswer


# 创建测试应用
app = FastAPI()
app.include_router(teaching_router)
client = TestClient(app)


@pytest.fixture
def mock_teaching_manager():
    """创建模拟的教学管理器"""
    with patch("backend.teaching.router.get_teaching_manager") as mock_get_manager:
        mock_manager = MagicMock()
        mock_get_manager.return_value = mock_manager
        yield mock_manager


@pytest.fixture
def sample_session():
    """创建示例教学会话"""
    session = MagicMock()
    session.id = str(uuid.uuid4())
    session.title = "Python面向对象编程"
    session.status = TeachingStatus.COMPLETED
    session.teaching_script = "这是讲课稿内容..."
    session.messages = [MagicMock()]
    session.quiz_id = str(uuid.uuid4())
    session.knowledge_points = []
    session.current_iteration = 3
    session.max_iterations = 3
    session.completed_at = datetime.now()
    session.document_id = None
    return session


@pytest.fixture
def sample_quiz_result():
    """创建示例测验结果"""
    result = MagicMock()
    result.quiz_id = str(uuid.uuid4())
    result.total_score = 85.0
    result.max_score = 100.0
    result.passed = True
    result.weak_knowledge_points = ["继承", "多态"]
    result.improvement_suggestions = ["复习第4章", "做练习题"]
    result.answers = []
    result.created_at = datetime.now()
    return result


class TestReportPDFEndpoint:
    """测试PDF报告生成端点"""

    def test_generate_report_success(self, mock_teaching_manager, sample_session, sample_quiz_result, tmp_path):
        """测试成功生成并下载PDF报告"""
        # 设置模拟数据
        mock_teaching_manager.get_session.return_value = sample_session
        mock_teaching_manager.get_interaction_path.return_value = None
        mock_teaching_manager.get_quiz_results.return_value = sample_quiz_result

        # 模拟PDF生成
        pdf_path = tmp_path / "test_report.pdf"
        pdf_path.write_bytes(b"PDF content")

        with patch("backend.teaching.router.PDFReportService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.generate_teaching_report.return_value = str(pdf_path)
            mock_service_class.return_value = mock_service

            # 发送请求
            response = client.get(f"/api/teaching/sessions/{sample_session.id}/report/pdf")

            # 验证响应
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/pdf"
            assert "Content-Disposition" in response.headers
            assert "教学分析报告" in response.headers["Content-Disposition"]
            assert ".pdf" in response.headers["Content-Disposition"]
            assert response.headers["X-Report-Generated"] == "true"
            assert response.headers["X-Session-ID"] == sample_session.id

    def test_generate_report_session_not_found(self, mock_teaching_manager):
        """测试会话不存在时返回404"""
        mock_teaching_manager.get_session.return_value = None

        response = client.get("/api/teaching/sessions/nonexistent-id/report/pdf")

        assert response.status_code == 404
        assert "会话不存在" in response.json()["detail"]

    def test_generate_report_empty_content(self, mock_teaching_manager, sample_session):
        """测试教学内容为空时返回400"""
        sample_session.teaching_script = ""
        sample_session.messages = []
        mock_teaching_manager.get_session.return_value = sample_session

        response = client.get(f"/api/teaching/sessions/{sample_session.id}/report/pdf")

        assert response.status_code == 400
        assert "教学内容为空" in response.json()["detail"]

    def test_generate_report_without_quiz(self, mock_teaching_manager, sample_session, tmp_path):
        """测试不包含测验结果的报告生成"""
        sample_session.quiz_id = None
        mock_teaching_manager.get_session.return_value = sample_session
        mock_teaching_manager.get_interaction_path.return_value = None

        pdf_path = tmp_path / "test_report.pdf"
        pdf_path.write_bytes(b"PDF content")

        with patch("backend.teaching.router.PDFReportService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.generate_teaching_report.return_value = str(pdf_path)
            mock_service_class.return_value = mock_service

            response = client.get(
                f"/api/teaching/sessions/{sample_session.id}/report/pdf?include_quiz=false"
            )

            assert response.status_code == 200
            # 验证生成报告时quiz_result为None
            call_kwargs = mock_service.generate_teaching_report.call_args[1]
            assert call_kwargs["quiz_result"] is None

    def test_generate_report_without_interactions(self, mock_teaching_manager, sample_session, sample_quiz_result, tmp_path):
        """测试不包含互动路径的报告生成"""
        mock_teaching_manager.get_session.return_value = sample_session
        mock_teaching_manager.get_quiz_results.return_value = sample_quiz_result

        pdf_path = tmp_path / "test_report.pdf"
        pdf_path.write_bytes(b"PDF content")

        with patch("backend.teaching.router.PDFReportService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.generate_teaching_report.return_value = str(pdf_path)
            mock_service_class.return_value = mock_service

            response = client.get(
                f"/api/teaching/sessions/{sample_session.id}/report/pdf?include_interactions=false"
            )

            assert response.status_code == 200
            # 验证生成报告时interaction_path为None
            call_kwargs = mock_service.generate_teaching_report.call_args[1]
            assert call_kwargs["interaction_path"] is None

    def test_generate_report_filename_encoding(self, mock_teaching_manager, sample_session, tmp_path):
        """测试文件名中的特殊字符处理"""
        sample_session.title = "Python<编程>:基础/进阶|教程"
        mock_teaching_manager.get_session.return_value = sample_session

        pdf_path = tmp_path / "test_report.pdf"
        pdf_path.write_bytes(b"PDF content")

        with patch("backend.teaching.router.PDFReportService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.generate_teaching_report.return_value = str(pdf_path)
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/teaching/sessions/{sample_session.id}/report/pdf")

            assert response.status_code == 200
            # 验证文件名中不包含非法字符
            content_disposition = response.headers["Content-Disposition"]
            assert "<" not in content_disposition
            assert ">" not in content_disposition
            assert "/" not in content_disposition
            assert "|" not in content_disposition

    def test_generate_report_with_empty_title(self, mock_teaching_manager, tmp_path):
        """测试空课程名称时的文件名处理"""
        session = MagicMock()
        session.id = str(uuid.uuid4())
        session.title = "   "  # 只有空格
        session.status = TeachingStatus.COMPLETED
        session.teaching_script = "内容"
        session.messages = [MagicMock()]
        session.quiz_id = None

        mock_teaching_manager.get_session.return_value = session

        pdf_path = tmp_path / "test_report.pdf"
        pdf_path.write_bytes(b"PDF content")

        with patch("backend.teaching.router.PDFReportService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.generate_teaching_report.return_value = str(pdf_path)
            mock_service_class.return_value = mock_service

            response = client.get(f"/api/teaching/sessions/{session.id}/report/pdf")

            assert response.status_code == 200
            # 验证使用默认名称
            assert "未命名课程" in response.headers["Content-Disposition"]


class TestReportStatusEndpoint:
    """测试报告生成状态端点"""

    def test_get_status_no_task(self, mock_teaching_manager, sample_session):
        """测试没有生成任务时的状态"""
        mock_teaching_manager.get_session.return_value = sample_session

        response = client.get(f"/api/teaching/sessions/{sample_session.id}/report/status")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == sample_session.id
        assert data["status"] == "not_started"
        assert data["progress"] == 0

    def test_get_status_session_not_found(self, mock_teaching_manager):
        """测试会话不存在时返回404"""
        mock_teaching_manager.get_session.return_value = None

        response = client.get("/api/teaching/sessions/nonexistent-id/report/status")

        assert response.status_code == 404
        assert "会话不存在" in response.json()["detail"]

    def test_get_status_after_generation(self, mock_teaching_manager, sample_session, tmp_path):
        """测试报告生成后的状态"""
        mock_teaching_manager.get_session.return_value = sample_session

        # 先执行生成请求
        pdf_path = tmp_path / "test_report.pdf"
        pdf_path.write_bytes(b"PDF content")

        with patch("backend.teaching.router.PDFReportService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.generate_teaching_report.return_value = str(pdf_path)
            mock_service_class.return_value = mock_service

            # 生成报告
            client.get(f"/api/teaching/sessions/{sample_session.id}/report/pdf")

            # 查询状态
            response = client.get(f"/api/teaching/sessions/{sample_session.id}/report/status")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"
            assert data["progress"] == 100
            assert "message" in data
            assert "file_path" in data

    def test_get_status_failed_generation(self, mock_teaching_manager, sample_session):
        """测试生成失败后的状态"""
        mock_teaching_manager.get_session.return_value = sample_session
        mock_teaching_manager.get_quiz_results.return_value = None

        # 模拟生成失败
        with patch("backend.teaching.router.PDFReportService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.generate_teaching_report.side_effect = Exception("生成失败")
            mock_service_class.return_value = mock_service

            # 尝试生成报告
            response = client.get(f"/api/teaching/sessions/{sample_session.id}/report/pdf")
            assert response.status_code == 500

            # 查询状态
            response = client.get(f"/api/teaching/sessions/{sample_session.id}/report/status")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "failed"
            assert "error" in data


class TestReportCleanup:
    """测试报告清理功能"""

    def test_cleanup_expired_tasks(self, mock_teaching_manager, sample_session, tmp_path):
        """测试过期任务清理"""
        mock_teaching_manager.get_session.return_value = sample_session

        pdf_path = tmp_path / "test_report.pdf"
        pdf_path.write_bytes(b"PDF content")

        with patch("backend.teaching.router.PDFReportService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.generate_teaching_report.return_value = str(pdf_path)
            mock_service_class.return_value = mock_service

            # 生成报告
            client.get(f"/api/teaching/sessions/{sample_session.id}/report/pdf")

            # 模拟时间流逝，修改任务时间戳为过期
            from backend.teaching.router import _report_generation_tasks
            for task in _report_generation_tasks.values():
                if task["session_id"] == sample_session.id:
                    task["timestamp"] = time.time() - 4000  # 超过1小时

            # 查询状态（会触发清理）
            response = client.get(f"/api/teaching/sessions/{sample_session.id}/report/status")

            assert response.status_code == 200
            data = response.json()
            # 过期任务应该已被清理，显示为未开始
            assert data["status"] == "not_started"


class TestPDFReportService:
    """测试PDF报告服务功能"""

    def test_cleanup_expired_reports(self, tmp_path):
        """测试清理过期报告文件"""
        from backend.teaching.pdf_report_service import PDFReportService

        service = PDFReportService(output_dir=str(tmp_path))

        # 创建测试文件
        recent_file = tmp_path / "teaching_report_recent.pdf"
        recent_file.write_bytes(b"recent")
        # 修改时间为最近
        recent_mtime = time.time()
        os.utime(recent_file, (recent_mtime, recent_mtime))

        old_file = tmp_path / "teaching_report_old.pdf"
        old_file.write_bytes(b"old")
        # 修改时间为25小时前
        old_mtime = time.time() - (25 * 3600)
        os.utime(old_file, (old_mtime, old_mtime))

        temp_file = tmp_path / "coverage_chart_test.png"
        temp_file.write_bytes(b"chart")
        os.utime(temp_file, (old_mtime, old_mtime))

        # 执行清理
        cleaned_count = service.cleanup_expired_reports(max_age_hours=24)

        assert cleaned_count == 2  # 清理了old_file和temp_file
        assert recent_file.exists()  # 最近的文件应该保留
        assert not old_file.exists()  # 旧文件应该被删除
        assert not temp_file.exists()  # 临时文件应该被删除

    def test_get_report_file_info(self, tmp_path):
        """测试获取报告文件信息"""
        from backend.teaching.pdf_report_service import PDFReportService

        service = PDFReportService(output_dir=str(tmp_path))

        # 创建测试文件
        pdf_file = tmp_path / "teaching_report_test.pdf"
        pdf_file.write_bytes(b"PDF" * 1000)  # 3KB

        temp_file = tmp_path / "coverage_chart_test.png"
        temp_file.write_bytes(b"PNG" * 1000)  # 3KB

        info = service.get_report_file_info()

        assert info["pdf_count"] == 1
        assert info["temp_count"] == 1
        assert info["total_size_mb"] > 0
        assert info["output_dir"] == str(tmp_path)


# 运行测试的入口
if __name__ == "__main__":
    # 使用pytest运行测试
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v"],
        cwd=backend_dir,
        capture_output=False
    )
    sys.exit(result.returncode)
