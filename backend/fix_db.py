"""
修复数据库表结构 - 添加缺失的列
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "platform.db")

def fix_teaching_sessions_table():
    """修复教学会话表结构"""
    if not os.path.exists(DB_PATH):
        print(f"[FixDB] 数据库文件不存在: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 检查并添加缺失的列
    columns_to_add = [
        ("interaction_path", "TEXT DEFAULT '[]'"),
        ("learning_objectives", "TEXT DEFAULT '[]'"),
        ("objective_assessments", "TEXT DEFAULT '[]'"),
        ("teaching_framework", "TEXT"),
        ("supervisor_suggestions", "TEXT DEFAULT '[]'"),
    ]

    for column_name, column_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE teaching_sessions ADD COLUMN {column_name} {column_type}")
            print(f"[FixDB] 成功添加列: {column_name}")
        except sqlite3.OperationalError as e:
            if "already exists" in str(e):
                print(f"[FixDB] 列已存在: {column_name}")
            else:
                print(f"[FixDB] 添加列失败 {column_name}: {e}")

    conn.commit()
    conn.close()
    print("[FixDB] 数据库修复完成")

if __name__ == "__main__":
    fix_teaching_sessions_table()
