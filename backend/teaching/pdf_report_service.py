"""
PDF报告生成服务 - 教学督导报告生成器
使用 ReportLab 和 matplotlib 生成专业的教学督导报告
"""
import os
import io
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

# ReportLab imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, ListFlowable, ListItem, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

# Matplotlib imports
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端

# 导入教学会话模型
from .session import TeachingSession, TeachingStatus, KnowledgePoint, SupervisorSuggestion, TeachingMessage, TeachingPhase
from .evaluation_models import InteractionNode, InteractionType, QuizResult, ObjectiveAssessment


# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FontManager:
    """字体管理器 - 处理中文字体注册"""
    
    # Windows 系统常用中文字体路径
    WINDOWS_FONT_PATHS = [
        ("Microsoft YaHei", "C:/Windows/Fonts/msyh.ttc"),
        ("SimHei", "C:/Windows/Fonts/simhei.ttf"),
        ("SimSun", "C:/Windows/Fonts/simsun.ttc"),
        ("SimSun", "C:/Windows/Fonts/simsunb.ttf"),
    ]
    
    # Linux 系统常用中文字体路径
    LINUX_FONT_PATHS = [
        ("WenQuanYi Micro Hei", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        ("Noto Sans CJK SC", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        ("Noto Sans CJK SC", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
        ("Droid Sans Fallback", "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
    ]
    
    # macOS 系统常用中文字体路径
    MAC_FONT_PATHS = [
        ("PingFang SC", "/System/Library/Fonts/PingFang.ttc"),
        ("Heiti SC", "/System/Library/Fonts/STHeiti Light.ttc"),
        ("Heiti SC", "/System/Library/Fonts/STHeiti Medium.ttc"),
        ("Arial Unicode MS", "/Library/Fonts/Arial Unicode.ttf"),
    ]
    
    _registered_fonts: Dict[str, str] = {}
    _chinese_font_name: Optional[str] = None
    
    @classmethod
    def register_fonts(cls) -> str:
        """注册中文字体，返回可用字体名称"""
        if cls._chinese_font_name:
            return cls._chinese_font_name
        
        # 检测操作系统
        import platform
        system = platform.system()
        
        if system == "Windows":
            font_paths = cls.WINDOWS_FONT_PATHS
        elif system == "Darwin":
            font_paths = cls.MAC_FONT_PATHS
        else:
            font_paths = cls.LINUX_FONT_PATHS
        
        # 尝试注册字体
        for font_name, font_path in font_paths:
            try:
                if os.path.exists(font_path):
                    # 检查是否已注册
                    if font_name not in cls._registered_fonts:
                        pdfmetrics.registerFont(TTFont(font_name, font_path))
                        cls._registered_fonts[font_name] = font_path
                        logger.info(f"成功注册字体: {font_name} ({font_path})")
                    
                    if cls._chinese_font_name is None:
                        cls._chinese_font_name = font_name
                        logger.info(f"使用中文字体: {font_name}")
                        return font_name
            except Exception as e:
                logger.warning(f"注册字体失败 {font_name}: {e}")
        
        # 如果没有找到中文字体，使用默认字体
        logger.warning("未找到中文字体，使用默认 Helvetica 字体")
        cls._chinese_font_name = "Helvetica"
        return cls._chinese_font_name
    
    @classmethod
    def get_font_name(cls) -> str:
        """获取当前可用字体名称"""
        if cls._chinese_font_name is None:
            return cls.register_fonts()
        return cls._chinese_font_name


class PDFReportService:
    """PDF报告生成服务"""
    
    def __init__(self, output_dir: Optional[str] = None):
        """
        初始化PDF报告服务
        
        Args:
            output_dir: 报告输出目录，默认为 backend/reports/
        """
        self.font_name = FontManager.register_fonts()
        
        # 设置输出目录
        if output_dir is None:
            backend_dir = Path(__file__).parent.parent
            self.output_dir = backend_dir / "reports"
        else:
            self.output_dir = Path(output_dir)
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化样式
        self.styles = self._create_styles()
        
        logger.info(f"PDF报告服务初始化完成，输出目录: {self.output_dir}")
    
    def _create_styles(self) -> Dict[str, ParagraphStyle]:
        """创建PDF样式"""
        styles = getSampleStyleSheet()
        
        # 封面标题样式
        styles.add(ParagraphStyle(
            name='CoverTitle',
            fontName=self.font_name,
            fontSize=32,
            leading=40,
            alignment=TA_CENTER,
            spaceAfter=30,
            textColor=colors.HexColor('#1a365d'),
        ))
        
        # 封面副标题样式
        styles.add(ParagraphStyle(
            name='CoverSubtitle',
            fontName=self.font_name,
            fontSize=18,
            leading=24,
            alignment=TA_CENTER,
            spaceAfter=20,
            textColor=colors.HexColor('#4a5568'),
        ))
        
        # 封面信息样式
        styles.add(ParagraphStyle(
            name='CoverInfo',
            fontName=self.font_name,
            fontSize=12,
            leading=18,
            alignment=TA_CENTER,
            spaceAfter=10,
            textColor=colors.HexColor('#718096'),
        ))
        
        # 章节标题样式
        styles.add(ParagraphStyle(
            name='ChapterTitle',
            fontName=self.font_name,
            fontSize=20,
            leading=28,
            alignment=TA_LEFT,
            spaceBefore=20,
            spaceAfter=15,
            textColor=colors.HexColor('#2c5282'),
            borderWidth=0,
            borderColor=colors.HexColor('#2c5282'),
            borderPadding=5,
        ))
        
        # 小节标题样式
        styles.add(ParagraphStyle(
            name='SectionTitle',
            fontName=self.font_name,
            fontSize=14,
            leading=20,
            alignment=TA_LEFT,
            spaceBefore=15,
            spaceAfter=10,
            textColor=colors.HexColor('#2d3748'),
        ))
        
        # 正文样式 - 如果已存在则更新
        if 'BodyText' in styles:
            styles['BodyText'].fontName = self.font_name
            styles['BodyText'].fontSize = 10
            styles['BodyText'].leading = 16
            styles['BodyText'].alignment = TA_JUSTIFY
            styles['BodyText'].spaceAfter = 8
            styles['BodyText'].textColor = colors.HexColor('#1a202c')
        else:
            styles.add(ParagraphStyle(
                name='BodyText',
                fontName=self.font_name,
                fontSize=10,
                leading=16,
                alignment=TA_JUSTIFY,
                spaceAfter=8,
                textColor=colors.HexColor('#1a202c'),
            ))
        
        # 目录样式
        styles.add(ParagraphStyle(
            name='TOCEntry',
            fontName=self.font_name,
            fontSize=11,
            leading=18,
            alignment=TA_LEFT,
            spaceAfter=6,
            textColor=colors.HexColor('#2d3748'),
        ))
        
        # 表格标题样式
        styles.add(ParagraphStyle(
            name='TableHeader',
            fontName=self.font_name,
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.white,
        ))
        
        # 评分样式
        styles.add(ParagraphStyle(
            name='ScoreText',
            fontName=self.font_name,
            fontSize=12,
            leading=18,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#2c5282'),
        ))
        
        # 建议样式
        styles.add(ParagraphStyle(
            name='SuggestionText',
            fontName=self.font_name,
            fontSize=10,
            leading=15,
            alignment=TA_LEFT,
            leftIndent=20,
            spaceAfter=6,
            textColor=colors.HexColor('#744210'),
        ))
        
        return styles
    
    def _load_messages_from_db(self, session_id: str) -> List[TeachingMessage]:
        """从数据库加载教学消息"""
        try:
            import sqlite3
            import os
            db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'platform.db')
            if not os.path.exists(db_path):
                return []
            
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT * FROM teaching_messages WHERE session_id = ? ORDER BY iteration, created_at",
                (session_id,)
            )
            rows = cursor.fetchall()
            conn.close()
            
            messages = []
            for row in rows:
                data = dict(row)
                # 解析JSON字段
                if data.get('refs'):
                    try:
                        data['references'] = json.loads(data['refs'])
                    except:
                        data['references'] = []
                else:
                    data['references'] = []
                
                data['agent_type'] = data.get('agent_type', 'teacher')
                data['phase'] = data.get('phase', 'design')
                
                messages.append(TeachingMessage.from_dict(data))
            
            return messages
        except Exception as e:
            logger.error(f"从数据库加载消息失败: {e}")
            return []
    
    def generate_pdf_report(self, session: TeachingSession, 
                           interaction_path: Optional[List[Dict]] = None,
                           quiz_result: Optional[QuizResult] = None,
                           output_path: Optional[str] = None) -> str:
        """
        生成完整的教学督导报告
        
        Args:
            session: 教学会话对象
            interaction_path: 互动路径数据
            quiz_result: 测验结果
            output_path: 输出文件路径，默认为自动生成
            
        Returns:
            生成的PDF文件路径
        """
        # 从数据库加载messages（如果session中没有）
        if not hasattr(session, 'messages') or not session.messages:
            session.messages = self._load_messages_from_db(session.id)
            logger.info(f"从数据库加载了 {len(session.messages)} 条消息到session")
        
        # 确定输出路径
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"teaching_report_{session.id}_{timestamp}.pdf"
            output_path = self.output_dir / filename
        else:
            output_path = Path(output_path)
        
        # 创建PDF文档
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm,
        )
        
        # 构建文档内容
        story = []
        
        # 1. 封面
        story.extend(self._create_cover_page(session))
        story.append(PageBreak())
        
        # 2. 目录
        story.extend(self._create_toc_page())
        story.append(PageBreak())
        
        # 3. 内容页
        story.extend(self._create_content_pages(session, interaction_path, quiz_result))
        
        # 生成PDF
        try:
            doc.build(story)
            logger.info(f"PDF报告生成成功: {output_path}")
            return str(output_path)
        except Exception as e:
            logger.error(f"PDF报告生成失败: {e}")
            raise
    
    def _create_cover_page(self, session: TeachingSession) -> List:
        """创建封面页"""
        story = []
        
        # 顶部空白
        story.append(Spacer(1, 4*cm))
        
        # 主标题
        story.append(Paragraph("教学督导报告", self.styles['CoverTitle']))
        story.append(Spacer(1, 1*cm))
        
        # 副标题 - 课程名称
        story.append(Paragraph(f"《{session.title}》", self.styles['CoverSubtitle']))
        story.append(Spacer(1, 2*cm))
        
        # 装饰线
        story.append(Table(
            [['']],
            colWidths=[10*cm],
            style=TableStyle([
                ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#2c5282')),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ])
        ))
        story.append(Spacer(1, 2*cm))
        
        # 报告信息
        story.append(Paragraph(f"报告编号: {session.id[:8].upper()}", self.styles['CoverInfo']))
        story.append(Paragraph(f"生成日期: {datetime.now().strftime('%Y年%m月%d日')}", self.styles['CoverInfo']))
        
        if session.completed_at:
            story.append(Paragraph(
                f"课程完成: {session.completed_at.strftime('%Y年%m月%d日 %H:%M')}",
                self.styles['CoverInfo']
            ))
        
        story.append(Spacer(1, 1*cm))
        
        # 状态信息
        status_text = self._get_status_display(session.status)
        story.append(Paragraph(f"课程状态: {status_text}", self.styles['CoverInfo']))
        
        if session.max_iterations > 0:
            story.append(Paragraph(
                f"迭代次数: {session.current_iteration}/{session.max_iterations}",
                self.styles['CoverInfo']
            ))
        
        story.append(Spacer(1, 3*cm))
        
        # 底部信息
        story.append(Paragraph("AI 教学督导系统", self.styles['CoverInfo']))
        story.append(Paragraph("Multi-Agent Teaching Platform", self.styles['CoverInfo']))
        
        return story
    
    def _create_toc_page(self) -> List:
        """创建目录页"""
        story = []
        
        story.append(Paragraph("目 录", self.styles['ChapterTitle']))
        story.append(Spacer(1, 0.5*cm))
        
        toc_items = [
            ("第1章 课程概述", "3"),
            ("第2章 教学内容分析", "4"),
            ("第3章 互动分析", "5"),
            ("第4章 督导点评", "6"),
            ("第5章 学习目标评估", "7"),
            ("第6章 测验结果", "8"),
        ]
        
        for title, page in toc_items:
            # 创建目录项表格
            toc_table = Table(
                [[Paragraph(title, self.styles['TOCEntry']), 
                  Paragraph(page, self.styles['TOCEntry'])]],
                colWidths=[14*cm, 2*cm],
            )
            toc_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (-1, 0), (-1, 0), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(toc_table)
        
        return story
    
    def _create_content_pages(self, session: TeachingSession,
                             interaction_path: Optional[List[Dict]],
                             quiz_result: Optional[QuizResult]) -> List:
        """创建内容页"""
        story = []
        
        # 第1章 课程概述
        story.extend(self._create_chapter1_overview(session))
        story.append(PageBreak())
        
        # 第2章 教学内容分析
        story.extend(self._create_chapter2_content_analysis(session))
        story.append(PageBreak())
        
        # 第3章 互动分析
        story.extend(self._create_chapter3_interaction(session, interaction_path))
        story.append(PageBreak())
        
        # 第4章 督导点评
        story.extend(self._create_chapter4_supervisor(session))
        story.append(PageBreak())
        
        # 第5章 学习目标评估
        story.extend(self._create_chapter5_objectives(session))
        story.append(PageBreak())
        
        # 第6章 测验结果
        story.extend(self._create_chapter6_quiz(session, quiz_result))
        
        return story
    
    def _create_chapter1_overview(self, session: TeachingSession) -> List:
        """创建第1章：课程概述"""
        story = []
        
        story.append(Paragraph("第1章 课程概述", self.styles['ChapterTitle']))
        
        # 1.1 基本信息
        story.append(Paragraph("1.1 基本信息", self.styles['SectionTitle']))
        
        basic_info = [
            ["课程名称", session.title],
            ["报告编号", session.id[:8].upper()],
            ["课程状态", self._get_status_display(session.status)],
            ["迭代次数", f"{session.current_iteration}/{session.max_iterations}"],
            ["知识点数量", str(len(session.knowledge_points))],
        ]
        
        if session.document_id:
            basic_info.append(["关联文档", session.document_id[:8].upper()])
        
        info_table = Table(basic_info, colWidths=[4*cm, 12*cm])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), self.font_name),
            ('FONTNAME', (1, 0), (1, -1), self.font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2d3748')),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 0.5*cm))
        
        # 1.2 教学目标
        story.append(Paragraph("1.2 教学目标", self.styles['SectionTitle']))
        
        if session.teaching_framework and 'objectives' in session.teaching_framework:
            objectives = session.teaching_framework['objectives']
            for i, obj in enumerate(objectives[:5], 1):
                obj_text = obj if isinstance(obj, str) else obj.get('description', str(obj))
                story.append(Paragraph(f"{i}. {obj_text}", self.styles['BodyText']))
        else:
            story.append(Paragraph("暂无明确的教学目标记录", self.styles['BodyText']))
        
        story.append(Spacer(1, 0.5*cm))
        
        # 1.3 知识点列表
        story.append(Paragraph("1.3 知识点列表", self.styles['SectionTitle']))
        
        if session.knowledge_points:
            kp_data = [["序号", "知识点", "章节", "重点", "难度"]]
            for i, kp in enumerate(session.knowledge_points[:10], 1):
                kp_data.append([
                    str(i),
                    kp.title,
                    kp.chapter,
                    "是" if kp.is_key_point else "否",
                    kp.difficulty_level,
                ])
            
            kp_table = Table(kp_data, colWidths=[1.5*cm, 6*cm, 4*cm, 1.5*cm, 2*cm])
            kp_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), self.font_name),
                ('FONTNAME', (0, 1), (-1, -1), self.font_name),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (1, 1), (1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(kp_table)
            
            if len(session.knowledge_points) > 10:
                story.append(Spacer(1, 0.3*cm))
                story.append(Paragraph(
                    f"* 共 {len(session.knowledge_points)} 个知识点，此处显示前10个",
                    self.styles['BodyText']
                ))
        else:
            story.append(Paragraph("暂无知识点记录", self.styles['BodyText']))
        
        return story
    
    def _get_messages_by_phase(self, session: TeachingSession, phase: str) -> List[TeachingMessage]:
        """从session.messages中获取指定阶段的消息"""
        if hasattr(session, 'messages') and session.messages:
            return [m for m in session.messages if m.phase == phase]
        return []
    
    def _create_chapter2_content_analysis(self, session: TeachingSession) -> List:
        """创建第2章：教学内容分析"""
        story = []
        
        story.append(Paragraph("第2章 教学内容分析", self.styles['ChapterTitle']))
        
        # 从messages中获取教师讲授内容
        teach_messages = self._get_messages_by_phase(session, TeachingPhase.TEACH_KNOWLEDGE)
        
        # 2.1 讲课稿摘要
        story.append(Paragraph("2.1 讲课稿摘要", self.styles['SectionTitle']))
        
        if teach_messages:
            # 按轮次排序并合并内容
            teach_messages.sort(key=lambda m: m.iteration)
            for msg in teach_messages:
                story.append(Paragraph(f"<b>第 {msg.iteration} 轮教学内容</b>", self.styles['SectionTitle']))
                # 截取前800个字符
                content = msg.content[:800] if len(msg.content) > 800 else msg.content
                if len(msg.content) > 800:
                    content += "..."
                story.append(Paragraph(content, self.styles['BodyText']))
                story.append(Spacer(1, 0.3*cm))
        elif session.teaching_script:
            # 兼容旧数据
            script_summary = session.teaching_script[:1000]
            if len(session.teaching_script) > 1000:
                script_summary += "..."
            story.append(Paragraph(script_summary, self.styles['BodyText']))
        else:
            story.append(Paragraph("暂无讲课稿记录", self.styles['BodyText']))
        
        story.append(Spacer(1, 0.5*cm))
        
        # 2.2 知识点覆盖情况
        story.append(Paragraph("2.2 知识点覆盖情况", self.styles['SectionTitle']))
        
        # 生成知识点覆盖饼图
        if session.knowledge_points:
            chart_path = self._generate_knowledge_coverage_chart(session)
            if chart_path:
                story.append(Image(chart_path, width=10*cm, height=7.5*cm))
                story.append(Spacer(1, 0.3*cm))
        
        # 覆盖统计表格
        covered_count = sum(1 for kp in session.knowledge_points if hasattr(kp, 'covered') and kp.covered)
        total_count = len(session.knowledge_points)
        coverage_rate = (covered_count / total_count * 100) if total_count > 0 else 0
        
        coverage_data = [
            ["总知识点数", str(total_count)],
            ["已覆盖", str(covered_count)],
            ["覆盖率", f"{coverage_rate:.1f}%"],
        ]
        
        coverage_table = Table(coverage_data, colWidths=[4*cm, 4*cm])
        coverage_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ebf8ff')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#90cdf4')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(coverage_table)
        
        return story
    
    def _create_chapter3_interaction(self, session: TeachingSession,
                                     interaction_path: Optional[List[Dict]]) -> List:
        """创建第3章：互动分析"""
        story = []
        
        story.append(Paragraph("第3章 互动分析", self.styles['ChapterTitle']))
        
        # 3.1 学生提问记录
        story.append(Paragraph("3.1 学生提问记录", self.styles['SectionTitle']))
        
        # 从messages中获取学生提问
        student_messages = self._get_messages_by_phase(session, TeachingPhase.STUDENT_QUESTION)
        
        if student_messages:
            # 按轮次分组
            by_iteration = {}
            for msg in student_messages:
                iter_num = msg.iteration
                if iter_num not in by_iteration:
                    by_iteration[iter_num] = []
                by_iteration[iter_num].append(msg)
            
            # 按轮次排序显示
            for iter_num in sorted(by_iteration.keys()):
                story.append(Paragraph(f"<b>第 {iter_num} 轮学生提问</b>", self.styles['SectionTitle']))
                
                for i, msg in enumerate(by_iteration[iter_num], 1):
                    # 学生名称和问题内容
                    content = msg.content[:300] if len(msg.content) > 300 else msg.content
                    if len(msg.content) > 300:
                        content += "..."
                    
                    story.append(Paragraph(
                        f"{i}. <b>{msg.agent_name}</b>：{content}",
                        self.styles['BodyText']
                    ))
                    story.append(Spacer(1, 0.15*cm))
                
                story.append(Spacer(1, 0.2*cm))
        else:
            story.append(Paragraph("暂无学生提问记录", self.styles['BodyText']))
        
        story.append(Spacer(1, 0.3*cm))
        
        # 3.2 提问-回答统计（来自interaction_path）
        story.append(Paragraph("3.2 互动统计", self.styles['SectionTitle']))
        
        # 统计互动数据
        if interaction_path:
            question_count = sum(1 for node in interaction_path 
                               if node.get('interaction_type') == 'question')
            answer_count = sum(1 for node in interaction_path 
                             if node.get('interaction_type') == 'answer')
            comment_count = sum(1 for node in interaction_path 
                              if node.get('interaction_type') == 'comment')
            total_count = len(interaction_path)
            
            stats_data = [
                ["总互动数", str(total_count)],
                ["提问数", str(question_count)],
                ["回答数", str(answer_count)],
                ["点评数", str(comment_count)],
                ["问答覆盖率", f"{(answer_count/max(question_count,1)*100):.1f}%"],
            ]
            
            stats_table = Table(stats_data, colWidths=[4*cm, 4*cm])
            stats_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), self.font_name),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0fff4')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#9ae6b4')),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(stats_table)
            story.append(Spacer(1, 0.5*cm))
        else:
            story.append(Paragraph("暂无互动记录", self.styles['BodyText']))
        
        # 3.2 互动时间线
        story.append(Paragraph("3.2 互动时间线", self.styles['SectionTitle']))
        
        # 生成时间线图
        if interaction_path and len(interaction_path) > 0:
            timeline_path = self._generate_interaction_timeline(interaction_path)
            if timeline_path:
                story.append(Image(timeline_path, width=15*cm, height=8*cm))
                story.append(Spacer(1, 0.3*cm))
        
        # 3.3 高频问题
        story.append(Paragraph("3.3 高频问题", self.styles['SectionTitle']))
        
        if interaction_path:
            # 收集所有问题内容
            questions = [node.get('content', '') for node in interaction_path 
                        if node.get('interaction_type') == 'question']
            
            if questions:
                for i, q in enumerate(questions[:5], 1):
                    # 截断过长的问题
                    q_text = q[:200] + "..." if len(q) > 200 else q
                    story.append(Paragraph(f"{i}. {q_text}", self.styles['BodyText']))
            else:
                story.append(Paragraph("暂无问题记录", self.styles['BodyText']))
        else:
            story.append(Paragraph("暂无问题记录", self.styles['BodyText']))
        
        return story
    
    def _create_chapter4_supervisor(self, session: TeachingSession) -> List:
        """创建第4章：督导点评"""
        story = []
        
        story.append(Paragraph("第4章 督导点评", self.styles['ChapterTitle']))
        
        # 从messages中获取督导点评
        supervisor_messages = self._get_messages_by_phase(session, TeachingPhase.SUPERVISOR_COMMENT)
        
        # 4.1 督导点评详情
        story.append(Paragraph("4.1 督导点评详情", self.styles['SectionTitle']))
        
        if supervisor_messages:
            # 按轮次分组
            by_iteration = {}
            for msg in supervisor_messages:
                iter_num = msg.iteration
                if iter_num not in by_iteration:
                    by_iteration[iter_num] = []
                by_iteration[iter_num].append(msg)
            
            # 按轮次排序显示
            for iter_num in sorted(by_iteration.keys()):
                story.append(Paragraph(f"<b>第 {iter_num} 轮督导点评</b>", self.styles['SectionTitle']))
                
                for msg in by_iteration[iter_num]:
                    # 督导名称
                    story.append(Paragraph(f"<b>{msg.agent_name}</b>", self.styles['SectionTitle']))
                    # 点评内容（截取前600字符）
                    content = msg.content[:600] if len(msg.content) > 600 else msg.content
                    if len(msg.content) > 600:
                        content += "..."
                    story.append(Paragraph(content, self.styles['BodyText']))
                    story.append(Spacer(1, 0.2*cm))
                
                story.append(Spacer(1, 0.3*cm))
        elif session.supervisor_suggestions:
            # 兼容旧数据 - 按维度统计建议数量
            dimension_scores = {}
            for suggestion in session.supervisor_suggestions:
                dimension = suggestion.dimension or "综合"
                if dimension not in dimension_scores:
                    dimension_scores[dimension] = []
                dimension_scores[dimension].append(suggestion)
            
            # 创建评分表格
            score_data = [["维度", "建议数", "评分"]]
            for dim, suggestions in dimension_scores.items():
                score = max(60, 100 - len(suggestions) * 5)
                score_data.append([dim, str(len(suggestions)), f"{score}分"])
            
            score_table = Table(score_data, colWidths=[6*cm, 3*cm, 3*cm])
            score_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), self.font_name),
                ('FONTNAME', (0, 1), (-1, -1), self.font_name),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(score_table)
            
            story.append(Spacer(1, 0.5*cm))
            
            # 改进建议汇总
            story.append(Paragraph("4.2 改进建议汇总", self.styles['SectionTitle']))
            for i, suggestion in enumerate(session.supervisor_suggestions[:10], 1):
                dim = suggestion.dimension or "综合"
                content = suggestion.suggestion_content
                if len(content) > 300:
                    content = content[:300] + "..."
                
                story.append(Paragraph(
                    f"{i}. [{dim}] {content}",
                    self.styles['SuggestionText']
                ))
            
            if len(session.supervisor_suggestions) > 10:
                story.append(Spacer(1, 0.3*cm))
                story.append(Paragraph(
                    f"* 共 {len(session.supervisor_suggestions)} 条建议",
                    self.styles['BodyText']
                ))
        else:
            story.append(Paragraph("暂无督导点评记录", self.styles['BodyText']))
        
        return story
    
    def _create_chapter5_objectives(self, session: TeachingSession) -> List:
        """创建第5章：学习目标评估"""
        story = []
        
        story.append(Paragraph("第5章 学习目标评估", self.styles['ChapterTitle']))
        
        # 5.1 目标匹配度表格
        story.append(Paragraph("5.1 目标匹配度", self.styles['SectionTitle']))
        
        if session.objective_assessments:
            obj_data = [["目标", "达成度", "证据", "差距"]]
            for assessment in session.objective_assessments:
                objective = None
                for obj in session.learning_objectives:
                    if obj.get('id') == assessment.get('objective_id'):
                        objective = obj
                        break
                
                obj_desc = objective.get('description', '未知目标') if objective else '未知目标'
                coverage = assessment.get('coverage_score', 0)
                evidence = assessment.get('evidence', '')[:50]
                gaps = ', '.join(assessment.get('gaps', [])[:2])
                
                obj_data.append([
                    obj_desc[:30] + "..." if len(obj_desc) > 30 else obj_desc,
                    f"{coverage:.0f}%",
                    evidence[:30] + "..." if len(evidence) > 30 else evidence,
                    gaps[:30] + "..." if len(gaps) > 30 else gaps,
                ])
            
            obj_table = Table(obj_data, colWidths=[5*cm, 2*cm, 4*cm, 4*cm])
            obj_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), self.font_name),
                ('FONTNAME', (0, 1), (-1, -1), self.font_name),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c5282')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e0')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7fafc')]),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(obj_table)
        else:
            story.append(Paragraph("暂无目标评估记录", self.styles['BodyText']))
        
        story.append(Spacer(1, 0.5*cm))
        
        # 5.2 未覆盖目标
        story.append(Paragraph("5.2 未覆盖或覆盖不足的目标", self.styles['SectionTitle']))
        
        if session.objective_assessments:
            uncovered = [a for a in session.objective_assessments 
                        if a.get('coverage_score', 0) < 50]
            
            if uncovered:
                for assessment in uncovered:
                    objective = None
                    for obj in session.learning_objectives:
                        if obj.get('id') == assessment.get('objective_id'):
                            objective = obj
                            break
                    
                    if objective:
                        obj_desc = objective.get('description', '未知目标')
                        coverage = assessment.get('coverage_score', 0)
                        story.append(Paragraph(
                            f"• {obj_desc} (达成度: {coverage:.0f}%)",
                            self.styles['BodyText']
                        ))
                        
                        # 显示改进建议
                        suggestions = assessment.get('suggestions', [])
                        for sg in suggestions[:2]:
                            story.append(Paragraph(f"  - {sg}", self.styles['SuggestionText']))
            else:
                story.append(Paragraph("所有目标均已良好覆盖", self.styles['BodyText']))
        else:
            story.append(Paragraph("暂无目标评估记录", self.styles['BodyText']))
        
        return story
    
    def _create_chapter6_quiz(self, session: TeachingSession,
                              quiz_result: Optional[QuizResult]) -> List:
        """创建第6章：测验结果"""
        story = []
        
        story.append(Paragraph("第6章 测验结果", self.styles['ChapterTitle']))
        
        if quiz_result:
            # 6.1 测验得分
            story.append(Paragraph("6.1 测验得分", self.styles['SectionTitle']))
            
            score_data = [
                ["总分", f"{quiz_result.total_score:.1f}/{quiz_result.max_score:.1f}"],
                ["得分率", f"{(quiz_result.total_score/quiz_result.max_score*100):.1f}%"],
                ["是否通过", "通过" if quiz_result.passed else "未通过"],
            ]
            
            score_table = Table(score_data, colWidths=[4*cm, 4*cm])
            score_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), self.font_name),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#faf5ff')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d6bcfa')),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(score_table)
            story.append(Spacer(1, 0.5*cm))
            
            # 6.2 薄弱知识点
            story.append(Paragraph("6.2 薄弱知识点", self.styles['SectionTitle']))
            
            if quiz_result.weak_knowledge_points:
                for kp in quiz_result.weak_knowledge_points:
                    story.append(Paragraph(f"• {kp}", self.styles['BodyText']))
            else:
                story.append(Paragraph("暂无薄弱知识点记录", self.styles['BodyText']))
            
            story.append(Spacer(1, 0.5*cm))
            
            # 6.3 改进建议
            story.append(Paragraph("6.3 改进建议", self.styles['SectionTitle']))
            
            if quiz_result.improvement_suggestions:
                for i, sg in enumerate(quiz_result.improvement_suggestions, 1):
                    story.append(Paragraph(f"{i}. {sg}", self.styles['SuggestionText']))
            else:
                story.append(Paragraph("暂无改进建议", self.styles['BodyText']))
        else:
            story.append(Paragraph("暂无测验记录", self.styles['BodyText']))
        
        return story
    
    def _generate_knowledge_coverage_chart(self, session: TeachingSession) -> Optional[str]:
        """
        生成知识点覆盖饼图
        
        Returns:
            临时图片文件路径
        """
        try:
            # 统计知识点覆盖情况
            covered = sum(1 for kp in session.knowledge_points if hasattr(kp, 'covered') and kp.covered)
            uncovered = len(session.knowledge_points) - covered
            
            if uncovered == 0 and covered == 0:
                # 使用模拟数据
                covered = 7
                uncovered = 3
            
            # 创建图表
            fig, ax = plt.subplots(figsize=(8, 6))
            
            # 设置中文字体
            plt.rcParams['font.sans-serif'] = [self.font_name, 'SimHei', 'Microsoft YaHei']
            plt.rcParams['axes.unicode_minus'] = False
            
            labels = ['已覆盖', '未覆盖']
            sizes = [covered, uncovered]
            colors_list = ['#48bb78', '#fc8181']
            explode = (0.05, 0)
            
            wedges, texts, autotexts = ax.pie(
                sizes, explode=explode, labels=labels, colors=colors_list,
                autopct='%1.1f%%', shadow=True, startangle=90
            )
            
            # 设置字体
            for text in texts:
                text.set_fontsize(12)
            for autotext in autotexts:
                autotext.set_fontsize(11)
                autotext.set_color('white')
                autotext.set_weight('bold')
            
            ax.set_title('知识点覆盖情况', fontsize=16, pad=20)
            
            # 保存图片
            temp_path = self.output_dir / f"coverage_chart_{session.id[:8]}.png"
            plt.tight_layout()
            plt.savefig(temp_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()
            
            return str(temp_path)
        except Exception as e:
            logger.error(f"生成知识点覆盖图表失败: {e}")
            return None
    
    def _generate_interaction_timeline(self, interaction_path: List[Dict]) -> Optional[str]:
        """
        生成互动时间线图
        
        Args:
            interaction_path: 互动路径数据
            
        Returns:
            临时图片文件路径
        """
        try:
            if not interaction_path:
                return None
            
            # 准备数据
            times = list(range(len(interaction_path)))
            types = [node.get('interaction_type', 'unknown') for node in interaction_path]
            
            # 映射类型到数值
            type_map = {'question': 3, 'answer': 2, 'comment': 1, 'discussion': 0}
            values = [type_map.get(t, 0) for t in types]
            
            # 创建图表
            fig, ax = plt.subplots(figsize=(12, 5))
            
            # 设置中文字体
            plt.rcParams['font.sans-serif'] = [self.font_name, 'SimHei', 'Microsoft YaHei']
            plt.rcParams['axes.unicode_minus'] = False
            
            # 使用不同颜色标记不同类型的互动
            colors_list = []
            for t in types:
                if t == 'question':
                    colors_list.append('#e53e3e')
                elif t == 'answer':
                    colors_list.append('#38a169')
                elif t == 'comment':
                    colors_list.append('#3182ce')
                else:
                    colors_list.append('#718096')
            
            # 绘制时间线
            ax.scatter(times, values, c=colors_list, s=100, alpha=0.7)
            ax.plot(times, values, 'k--', alpha=0.3, linewidth=0.5)
            
            # 设置Y轴标签
            ax.set_yticks([0, 1, 2, 3])
            ax.set_yticklabels(['讨论', '点评', '回答', '提问'])
            
            ax.set_xlabel('互动序号', fontsize=11)
            ax.set_ylabel('互动类型', fontsize=11)
            ax.set_title('教学互动时间线', fontsize=14, pad=15)
            ax.grid(True, alpha=0.3)
            
            # 添加图例
            from matplotlib.lines import Line2D
            legend_elements = [
                Line2D([0], [0], marker='o', color='w', markerfacecolor='#e53e3e', 
                       markersize=10, label='提问'),
                Line2D([0], [0], marker='o', color='w', markerfacecolor='#38a169', 
                       markersize=10, label='回答'),
                Line2D([0], [0], marker='o', color='w', markerfacecolor='#3182ce', 
                       markersize=10, label='点评'),
            ]
            ax.legend(handles=legend_elements, loc='upper right')
            
            # 保存图片
            temp_path = self.output_dir / f"timeline_chart_{id(interaction_path):08x}.png"
            plt.tight_layout()
            plt.savefig(temp_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()
            
            return str(temp_path)
        except Exception as e:
            logger.error(f"生成互动时间线图失败: {e}")
            return None
    
    def _get_status_display(self, status) -> str:
        """获取状态显示文本"""
        status_map = {
            TeachingStatus.PENDING: "待开始",
            TeachingStatus.DESIGNING: "设计中",
            TeachingStatus.TEACHING: "进行中",
            TeachingStatus.PAUSED: "已暂停",
            TeachingStatus.COMPLETED: "已完成",
            TeachingStatus.FAILED: "失败",
            'pending': "待开始",
            'designing': "设计中",
            'teaching': "进行中",
            'paused': "已暂停",
            'completed': "已完成",
            'failed': "失败",
        }
        if hasattr(status, 'value'):
            status = status.value
        return status_map.get(status, str(status))
    
    def cleanup_temp_files(self, session_id: str):
        """清理临时图表文件"""
        try:
            for pattern in [f"coverage_chart_{session_id[:8]}*.png", 
                          f"timeline_chart_*.png"]:
                for f in self.output_dir.glob(pattern):
                    f.unlink(missing_ok=True)
                    logger.info(f"清理临时文件: {f}")
        except Exception as e:
            logger.warning(f"清理临时文件失败: {e}")

    def cleanup_expired_reports(self, max_age_hours: int = 24) -> int:
        """
        清理过期的PDF报告文件
        
        Args:
            max_age_hours: 文件最大保存时间（小时），默认24小时
            
        Returns:
            清理的文件数量
        """
        try:
            from datetime import datetime, timedelta
            
            cleaned_count = 0
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            # 清理PDF报告文件
            for pdf_file in self.output_dir.glob("teaching_report_*.pdf"):
                try:
                    file_mtime = datetime.fromtimestamp(pdf_file.stat().st_mtime)
                    if file_mtime < cutoff_time:
                        pdf_file.unlink(missing_ok=True)
                        cleaned_count += 1
                        logger.info(f"清理过期报告文件: {pdf_file}")
                except Exception as e:
                    logger.warning(f"清理文件失败 {pdf_file}: {e}")
            
            # 清理临时图表文件
            for pattern in ["coverage_chart_*.png", "timeline_chart_*.png"]:
                for temp_file in self.output_dir.glob(pattern):
                    try:
                        file_mtime = datetime.fromtimestamp(temp_file.stat().st_mtime)
                        if file_mtime < cutoff_time:
                            temp_file.unlink(missing_ok=True)
                            cleaned_count += 1
                            logger.info(f"清理过期临时文件: {temp_file}")
                    except Exception as e:
                        logger.warning(f"清理文件失败 {temp_file}: {e}")
            
            logger.info(f"共清理 {cleaned_count} 个过期文件")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"清理过期报告失败: {e}")
            return 0

    def get_report_file_info(self) -> Dict[str, Any]:
        """
        获取报告目录的文件信息
        
        Returns:
            包含文件统计信息的字典
        """
        try:
            pdf_files = list(self.output_dir.glob("*.pdf"))
            temp_files = list(self.output_dir.glob("*.png"))
            
            total_size = sum(f.stat().st_size for f in pdf_files + temp_files)
            
            return {
                "pdf_count": len(pdf_files),
                "temp_count": len(temp_files),
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "output_dir": str(self.output_dir),
            }
        except Exception as e:
            logger.error(f"获取文件信息失败: {e}")
            return {
                "pdf_count": 0,
                "temp_count": 0,
                "total_size_mb": 0,
                "output_dir": str(self.output_dir),
            }


# 便捷函数
def generate_teaching_report(session: TeachingSession,
                            interaction_path: Optional[List[Dict]] = None,
                            quiz_result: Optional[QuizResult] = None,
                            output_dir: Optional[str] = None) -> str:
    """
    生成教学督导报告的便捷函数
    
    Args:
        session: 教学会话对象
        interaction_path: 互动路径数据
        quiz_result: 测验结果
        output_dir: 输出目录
        
    Returns:
        生成的PDF文件路径
    """
    service = PDFReportService(output_dir=output_dir)
    return service.generate_pdf_report(session, interaction_path, quiz_result)
