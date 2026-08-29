"""
文档解析模块 - 集成 DocumentParser
支持解析 PDF/DOCX/MD 格式，提取知识点
"""
import os
import json
import uuid
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend import database


class KnowledgePoint:
    """知识点"""
    def __init__(
        self,
        title: str = "",
        chapter: str = "",
        is_key_point: bool = False,
        difficulty_level: str = "中等",
        keywords: Optional[List[str]] = None,
    ):
        self.title = title
        self.chapter = chapter
        self.is_key_point = is_key_point
        self.difficulty_level = difficulty_level
        self.keywords = keywords or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "chapter": self.chapter,
            "is_key_point": self.is_key_point,
            "difficulty_level": self.difficulty_level,
            "keywords": self.keywords,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgePoint":
        return cls(
            title=data.get("title", ""),
            chapter=data.get("chapter", ""),
            is_key_point=data.get("is_key_point", False),
            difficulty_level=data.get("difficulty_level", "中等"),
            keywords=data.get("keywords", []),
        )


class DocumentUpload:
    """文档上传记录"""
    def __init__(
        self,
        file_name: str,
        file_path: str,
        file_type: str,
        doc_id: Optional[str] = None,
        status: str = "pending",
        parse_result: Optional[Dict[str, Any]] = None,
    ):
        self.id = doc_id or str(uuid.uuid4())
        self.file_name = file_name
        self.file_path = file_path
        self.file_type = file_type
        self.status = status  # pending/parsing/completed/failed
        self.parse_result = parse_result or {}
        self.created_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "status": self.status,
            "parse_result": self.parse_result,
            "created_at": self.created_at.isoformat(),
        }


class DocumentParser:
    """
    文档解析器

    集成自 student_profile_platform 的 DocumentParser，
    支持 PDF/DOCX/MD 格式文档解析
    """

    def __init__(self):
        self._parser = None
        self._analyzer = None
        self._init_parser()

    def _init_parser(self):
        """初始化解析器"""
        try:
            # 尝试导入 student_profile_platform 的 DocumentParser
            import sys
            sys.path.insert(0, r"D:\paper\cc\projects\ai_teaching_competition\student_profile_platform")
            from services.document_parser import DocumentParser as SPDocumentParser
            self._parser = SPDocumentParser()
        except ImportError as e:
            print(f"[DocumentParser] Failed to import SPDocumentParser: {e}")
            self._parser = None

    def parse(self, file_path: str) -> Dict[str, Any]:
        """
        解析文档

        Args:
            file_path: 文档路径

        Returns:
            Dict containing:
                - knowledge_points: List[KnowledgePoint]
                - chapters: List of chapter info
                - raw_text: str
                - course_name: str
                - chapter_title: str
        """
        if self._parser is None:
            # 降级方案：使用简单文本提取
            return self._parse_simple(file_path)

        try:
            result = self._parser.parse(file_path)
            return {
                "knowledge_points": [
                    KnowledgePoint(
                        title=kp.title,
                        chapter=kp.chapter,
                        is_key_point=kp.is_key_point,
                        difficulty_level=kp.difficulty_level,
                        keywords=kp.keywords,
                    ).to_dict()
                    for kp in result.knowledge_points
                ],
                "chapters": [
                    {
                        "title": ch.title,
                        "index": ch.index,
                    }
                    for ch in result.chapters
                ],
                "raw_text": result.raw_text[:10000] if result.raw_text else "",  # 限制长度
                "course_name": result.course_name,
                "chapter_title": result.chapter_title,
                "total_paragraphs": result.total_paragraphs,
            }
        except Exception as e:
            print(f"[DocumentParser] Parse error: {e}")
            return self._parse_simple(file_path)

    def _parse_simple(self, file_path: str) -> Dict[str, Any]:
        """简单文本提取（降级方案）"""
        import re
        import zipfile
        from xml.etree import ElementTree as ET
        ext = os.path.splitext(file_path)[1].lower()
        content = ""
        course_name = os.path.basename(file_path)

        if ext == ".md":
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 提取第一个标题作为课程名
            for line in content.split("\n")[:20]:
                match = re.match(r'^#\s+(.+)$', line.strip())
                if match:
                    course_name = match.group(1).strip()
                    break

        elif ext == ".docx":
            # 使用 zipfile + XML 解析 docx
            try:
                with zipfile.ZipFile(file_path, 'r') as z:
                    xml_content = z.read('word/document.xml')

                # 解析 XML
                root = ET.fromstring(xml_content)
                ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

                # 提取段落文本
                para_texts = []
                for p in root.iter(f'{{{ns}}}p'):
                    texts = []
                    for t in p.iter(f'{{{ns}}}t'):
                        if t.text:
                            texts.append(t.text)
                    if texts:
                        # 规范化中文文本（移除字符间多余空格）
                        para_text = self._normalize_chinese_text(''.join(texts))
                        if para_text.strip():
                            para_texts.append(para_text)

                content = "\n".join(para_texts)

                # 提取课程名（第一个非空短段落）
                for p in para_texts[:20]:
                    p = p.strip()
                    if p and 3 < len(p) < 50 and not any(p.startswith(x) for x in ['•', '-', '*', '1.', '2.', '3.']):
                        course_name = self._normalize_chinese_text(p)
                        break

            except Exception as e:
                print(f"[DocumentParser] Failed to parse docx: {e}")
                content = ""

        else:
            # 对于其他格式，尝试读取原始字节
            try:
                with open(file_path, "rb") as f:
                    content = f.read().decode("utf-8", errors="ignore")
            except:
                content = ""

        # 简单提取段落
        para_list = [p.strip() for p in content.split("\n") if p.strip()]

        return {
            "knowledge_points": self._extract_key_points(para_list),
            "chapters": [],
            "raw_text": content[:10000],
            "course_name": course_name,
            "chapter_title": "",
            "total_paragraphs": len(para_list),
        }

    def _extract_key_points(self, paragraphs: List[str]) -> List[Dict[str, Any]]:
        """从段落中提取关键知识点（改进版）"""
        import re
        key_points = []
        found_knowledge_section = False
        found_difficulty_section = False

        for p in paragraphs:
            p = p.strip()
            if not p:
                continue

            # 检测是否进入"知识点"或"重点难点"章节
            if re.match(r'^#{1,3}\s*知识点', p) or re.match(r'^#{1,3}\s*重点难点', p):
                if '重点' in p or '难点' in p:
                    found_difficulty_section = True
                else:
                    found_knowledge_section = True
                continue

            # 如果在知识点章节中，提取列表项
            if found_knowledge_section or found_difficulty_section:
                # 跳过 markdown 标题
                if p.startswith('#'):
                    continue

                # 跳过整个文档的标题（第一个以#开头的）
                if p.startswith('# '):
                    continue

                # 匹配列表项: "1. xxx" 或 "- xxx"
                match = re.match(r'^\d+\.\s*(.+)', p) or re.match(r'^-\s*(.+)', p)
                if match:
                    title = match.group(1).strip()
                    if len(title) > 5 and len(title) < 100:
                        key_points.append(KnowledgePoint(
                            title=title,
                            chapter="",
                            is_key_point=found_difficulty_section,
                            difficulty_level="中等",
                            keywords=[],
                        ).to_dict())
                elif found_knowledge_section and len(p) > 10 and len(p) < 100 and not p.startswith('#'):
                    # 如果不是列表项但还在知识点章节中，也可能是内容
                    key_points.append(KnowledgePoint(
                        title=p[:50],
                        chapter="",
                        is_key_point=False,
                        difficulty_level="中等",
                        keywords=[],
                    ).to_dict())

            # 重置状态如果遇到新的大标题
            if re.match(r'^#{1,3}\s*[^知]', p) and '重点' not in p:
                found_knowledge_section = False
                found_difficulty_section = False

        # 如果没有找到任何知识点，使用智能方法提取
        if not key_points:
            # 智能识别可能的知识点：章节标题、编号列表项
            for p in paragraphs:
                p = p.strip()
                if not p:
                    continue

                # 匹配章节标题：第X章、第X节、一、XXX（一、之后是标题）
                section_match = re.match(
                    r'^(第[一二三四五六七八九十\d]+(?:章|节)|[一二三四五六七八九十]+[、、][^。！？]{2,30})$',
                    p
                )
                if section_match:
                    title = section_match.group(0).strip()
                    if 4 <= len(title) <= 50 and not any(c in title for c in '（）()《》'):
                        key_points.append(KnowledgePoint(
                            title=title,
                            chapter="",
                            is_key_point=False,
                            difficulty_level="中等",
                            keywords=[],
                        ).to_dict())
                        continue

                # 匹配编号列表项: "1. xxx", "(1) xxx"
                list_match = re.match(r'^([1-9]\d*)[.、](.+)$', p) or re.match(r'^\(([1-9])\)(.+)$', p)
                if list_match:
                    title = list_match.group(2).strip()
                    # 检查是否像标题（不是完整句子）
                    if 4 <= len(title) <= 60 and not title.endswith(('。', '！', '？', '，', '；')):
                        key_points.append(KnowledgePoint(
                            title=title[:50],
                            chapter="",
                            is_key_point=False,
                            difficulty_level="中等",
                            keywords=[],
                        ).to_dict())
                        continue

                # 匹配以括号开头的内容: "(1) xxx"
                bracket_match = re.match(r'^\([1-9]\)\s*(.+)$', p)
                if bracket_match:
                    title = bracket_match.group(1).strip()
                    if 4 <= len(title) <= 60 and not title.endswith(('。', '！', '？')):
                        key_points.append(KnowledgePoint(
                            title=title[:50],
                            chapter="",
                            is_key_point=False,
                            difficulty_level="中等",
                            keywords=[],
                        ).to_dict())
                        continue

                # 如果已经收集到足够的知识点，停止
                if len(key_points) >= 8:
                    break

        return key_points[:8]

    def _normalize_chinese_text(self, text: str) -> str:
        """规范化中文文本，移除字符间的多余空格"""
        import re
        # 移除中文字符之间的空格
        # 匹配一个中文后面跟空格再跟中文的模式
        result = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', text)
        # 移除空格后跟中文但前面是中文字符的模式
        result = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', result)
        # 多次应用以处理多个连续空格
        for _ in range(5):
            new_result = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', result)
            if new_result == result:
                break
            result = new_result
        return result


def parse_document(file_path: str, file_name: str, file_type: str) -> DocumentUpload:
    """
    解析上传的文档

    Args:
        file_path: 临时文件路径
        file_name: 原始文件名
        file_type: 文件类型 (pdf/docx/md)

    Returns:
        DocumentUpload 对象
    """
    doc_id = str(uuid.uuid4())
    upload = DocumentUpload(
        file_name=file_name,
        file_path=file_path,
        file_type=file_type,
        doc_id=doc_id,
        status="parsing",
    )

    # 保存到数据库
    database.save_document(upload.to_dict())

    try:
        # 解析文档
        parser = DocumentParser()
        parse_result = parser.parse(file_path)

        # 更新上传记录
        upload.status = "completed"
        upload.parse_result = parse_result
        database.update_document(doc_id, {
            "status": "completed",
            "parse_result": parse_result,
        })

    except Exception as e:
        print(f"[DocumentParser] Failed to parse document: {e}")
        upload.status = "failed"
        database.update_document(doc_id, {"status": "failed"})

    return upload


def get_document(doc_id: str) -> Optional[DocumentUpload]:
    """获取文档上传记录"""
    doc_data = database.load_document(doc_id)
    if doc_data:
        return DocumentUpload(
            file_name=doc_data["file_name"],
            file_path=doc_data["file_path"],
            file_type=doc_data["file_type"],
            doc_id=doc_data["id"],
            status=doc_data.get("status", "pending"),
            parse_result=doc_data.get("parse_result", {}),
        )
    return None


def list_documents(limit: int = 100) -> List[DocumentUpload]:
    """列出上传的文档"""
    docs_data = database.load_documents(limit)
    return [
        DocumentUpload(
            file_name=d["file_name"],
            file_path=d["file_path"],
            file_type=d["file_type"],
            doc_id=d["id"],
            status=d.get("status", "pending"),
            parse_result=d.get("parse_result", {}),
        )
        for d in docs_data
    ]
