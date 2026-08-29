"""
Database persistence layer using SQLite
"""
import sqlite3
import json
import os
from datetime import datetime
from typing import List, Optional
from pathlib import Path

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "platform.db")

def get_db_path():
    """Get database path, creating data directory if needed"""
    db_path = os.environ.get("DATABASE_PATH", DB_PATH)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return db_path

def init_db():
    """Initialize database tables"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Agents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            description TEXT DEFAULT '',
            avatar TEXT DEFAULT '🤖',
            tools TEXT DEFAULT '[]',
            memory_scope TEXT DEFAULT 'private',
            status TEXT DEFAULT 'offline',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            msg_type TEXT DEFAULT 'chat',
            priority TEXT DEFAULT 'P2',
            from_agent TEXT NOT NULL,
            "to" TEXT NOT NULL,
            content TEXT NOT NULL,
            deadline TEXT DEFAULT 'immediate',
            callback TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Conversation history table (for multi-turn context)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Config table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

def save_agent(agent_data: dict) -> None:
    """Save or update an agent"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO agents
        (id, name, role, description, avatar, tools, memory_scope, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        agent_data["id"],
        agent_data["name"],
        agent_data["role"],
        agent_data.get("description", ""),
        agent_data.get("avatar", "🤖"),
        json.dumps(agent_data.get("tools", [])),
        agent_data.get("memory_scope", "private"),
        agent_data.get("status", "offline"),
        agent_data["created_at"],
        agent_data["updated_at"],
    ))

    conn.commit()
    conn.close()

def load_agents() -> List[dict]:
    """Load all agents from database"""
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM agents")
    rows = cursor.fetchall()
    conn.close()

    agents = []
    for row in rows:
        agent = dict(row)
        agent["tools"] = json.loads(agent["tools"])
        agents.append(agent)

    return agents

def save_message(message_data: dict) -> None:
    """Save a message"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO messages
        (id, msg_type, priority, from_agent, "to", content, deadline, callback, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        message_data["id"],
        message_data.get("msg_type", "chat"),
        message_data.get("priority", "P2"),
        message_data["from_agent"],
        message_data["to"],
        json.dumps(message_data["content"]),
        message_data.get("deadline", "immediate"),
        message_data.get("callback"),
        message_data["created_at"],
    ))

    conn.commit()
    conn.close()

def load_messages(limit: int = 1000) -> List[dict]:
    """Load recent messages"""
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(f"SELECT * FROM messages ORDER BY created_at DESC LIMIT {limit}")
    rows = cursor.fetchall()
    conn.close()

    messages = []
    for row in rows:
        msg = dict(row)
        msg["content"] = json.loads(msg["content"])
        messages.append(msg)

    return list(reversed(messages))

def save_conversation_turn(agent_id: str, role: str, content: str) -> None:
    """Save a conversation turn for context history"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO conversation_history (agent_id, role, content, created_at)
        VALUES (?, ?, ?, ?)
    """, (agent_id, role, content, datetime.now().isoformat()))

    conn.commit()
    conn.close()

def load_conversation_history(agent_id: str, limit: int = 40) -> List[dict]:
    """Load conversation history for an agent"""
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT role, content FROM conversation_history
        WHERE agent_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (agent_id, limit))

    rows = cursor.fetchall()
    conn.close()

    # Return in chronological order
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

def get_config(key: str, default: str = None) -> Optional[str]:
    """Get a config value"""
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return default

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_config(key: str, value: str) -> None:
    """Set a config value"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


# =============================================================================
# Debate Session Tables
# =============================================================================

def init_db_debate():
    """Initialize debate tables"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Debate sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS debate_sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            document_id TEXT,
            status TEXT DEFAULT 'pending',
            current_round INTEGER DEFAULT 0,
            max_rounds INTEGER DEFAULT 5,
            knowledge_points TEXT DEFAULT '[]',
            raw_text TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        )
    """)

    # Debate agents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS debate_agents (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            stance TEXT DEFAULT '',
            system_prompt TEXT NOT NULL,
            avatar TEXT DEFAULT '🤖',
            status TEXT DEFAULT 'idle',
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES debate_sessions(id)
        )
    """)

    # Debate messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS debate_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            agent_name TEXT DEFAULT '',
            agent_role TEXT DEFAULT '',
            round INTEGER DEFAULT 0,
            msg_type TEXT DEFAULT 'debate',
            content TEXT NOT NULL,
            target_agent_id TEXT,
            is_final INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES debate_sessions(id)
        )
    """)

    # Debate reports table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS debate_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL UNIQUE,
            summary TEXT DEFAULT '',
            proponent_points TEXT DEFAULT '[]',
            opponent_points TEXT DEFAULT '[]',
            key_disagreements TEXT DEFAULT '[]',
            conclusion TEXT DEFAULT '',
            suggestions TEXT DEFAULT '[]',
            generated_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES debate_sessions(id)
        )
    """)

    # Documents table for uploaded files
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            parse_result TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# Initialize debate tables on module load
init_db_debate()


# =============================================================================
# Debate Session Operations
# =============================================================================

def save_debate_session(session_data: dict) -> None:
    """Save or update a debate session"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO debate_sessions
        (id, title, document_id, status, current_round, max_rounds,
         knowledge_points, raw_text, created_at, updated_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_data["id"],
        session_data["title"],
        session_data.get("document_id"),
        session_data.get("status", "pending"),
        session_data.get("current_round", 0),
        session_data.get("max_rounds", 5),
        json.dumps(session_data.get("knowledge_points", [])),
        session_data.get("raw_text", ""),
        session_data["created_at"],
        session_data["updated_at"],
        session_data.get("completed_at"),
    ))

    conn.commit()
    conn.close()


def load_debate_sessions() -> List[dict]:
    """Load all debate sessions"""
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM debate_sessions ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()

    sessions = []
    for row in rows:
        session = dict(row)
        session["knowledge_points"] = json.loads(session["knowledge_points"])
        sessions.append(session)

    return sessions


def load_debate_session(session_id: str) -> Optional[dict]:
    """Load a specific debate session"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM debate_sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        session = dict(row)
        session["knowledge_points"] = json.loads(session["knowledge_points"])
        return session
    return None


def update_debate_session(session_id: str, updates: dict) -> None:
    """Update debate session fields"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Build dynamic update query
    set_clauses = []
    values = []
    for key, value in updates.items():
        set_clauses.append(f"{key} = ?")
        values.append(value)

    if set_clauses:
        values.append(session_id)
        cursor.execute(
            f"UPDATE debate_sessions SET {', '.join(set_clauses)} WHERE id = ?",
            values
        )

    conn.commit()
    conn.close()


def delete_debate_session(session_id: str) -> None:
    """Delete a debate session and all related data"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM debate_messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM debate_agents WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM debate_reports WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM debate_sessions WHERE id = ?", (session_id,))

    conn.commit()
    conn.close()


# =============================================================================
# Debate Agent Operations
# =============================================================================

def save_debate_agent(agent_data: dict) -> None:
    """Save or update a debate agent"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO debate_agents
        (id, session_id, name, role, stance, system_prompt, avatar, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        agent_data["id"],
        agent_data["session_id"],
        agent_data["name"],
        agent_data["role"],
        agent_data.get("stance", ""),
        agent_data["system_prompt"],
        agent_data.get("avatar", "🤖"),
        agent_data.get("status", "idle"),
        agent_data["created_at"],
    ))

    conn.commit()
    conn.close()


def load_debate_agents(session_id: str) -> List[dict]:
    """Load all debate agents for a session"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM debate_agents WHERE session_id = ?", (session_id,))
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def load_debate_agent(agent_id: str) -> Optional[dict]:
    """Load a specific debate agent"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM debate_agents WHERE id = ?", (agent_id,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def delete_debate_agent(agent_id: str) -> None:
    """Delete a debate agent"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM debate_agents WHERE id = ?", (agent_id,))

    conn.commit()
    conn.close()


# =============================================================================
# Debate Message Operations
# =============================================================================

def save_debate_message(message_data: dict) -> None:
    """Save a debate message"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO debate_messages
        (id, session_id, agent_id, agent_name, agent_role, round, msg_type,
         content, target_agent_id, is_final, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        message_data["id"],
        message_data["session_id"],
        message_data["agent_id"],
        message_data.get("agent_name", ""),
        message_data.get("agent_role", ""),
        message_data.get("round", 0),
        message_data.get("msg_type", "debate"),
        message_data["content"],
        message_data.get("target_agent_id"),
        1 if message_data.get("is_final") else 0,
        message_data["created_at"],
    ))

    conn.commit()
    conn.close()


def load_debate_messages(session_id: str, limit: int = 1000) -> List[dict]:
    """Load all messages for a debate session"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM debate_messages
        WHERE session_id = ?
        ORDER BY created_at ASC
        LIMIT ?
    """, (session_id, limit))

    rows = cursor.fetchall()
    conn.close()

    messages = []
    for row in rows:
        msg = dict(row)
        msg["is_final"] = bool(msg["is_final"])
        messages.append(msg)

    return messages


# =============================================================================
# Debate Report Operations
# =============================================================================

def save_debate_report(report_data: dict) -> None:
    """Save or update a debate report"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO debate_reports
        (session_id, summary, proponent_points, opponent_points,
         key_disagreements, conclusion, suggestions, generated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        report_data["session_id"],
        report_data.get("summary", ""),
        json.dumps(report_data.get("proponent_points", [])),
        json.dumps(report_data.get("opponent_points", [])),
        json.dumps(report_data.get("key_disagreements", [])),
        report_data.get("conclusion", ""),
        json.dumps(report_data.get("suggestions", [])),
        report_data.get("generated_at"),
    ))

    conn.commit()
    conn.close()


def load_debate_report(session_id: str) -> Optional[dict]:
    """Load the report for a debate session"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM debate_reports WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        report = dict(row)
        report["proponent_points"] = json.loads(report["proponent_points"])
        report["opponent_points"] = json.loads(report["opponent_points"])
        report["key_disagreements"] = json.loads(report["key_disagreements"])
        report["suggestions"] = json.loads(report["suggestions"])
        return report
    return None


# =============================================================================
# Document Operations
# =============================================================================

def save_document(doc_data: dict) -> None:
    """Save a document upload record"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO documents
        (id, file_name, file_path, file_type, parse_result, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        doc_data["id"],
        doc_data["file_name"],
        doc_data["file_path"],
        doc_data["file_type"],
        json.dumps(doc_data.get("parse_result")),
        doc_data.get("status", "pending"),
        doc_data["created_at"],
    ))

    conn.commit()
    conn.close()


def load_document(doc_id: str) -> Optional[dict]:
    """Load a document record"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        doc = dict(row)
        if doc.get("parse_result"):
            doc["parse_result"] = json.loads(doc["parse_result"])
        return doc
    return None


def load_documents(limit: int = 100) -> List[dict]:
    """Load recent documents"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM documents ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()

    docs = []
    for row in rows:
        doc = dict(row)
        if doc.get("parse_result"):
            doc["parse_result"] = json.loads(doc["parse_result"])
        docs.append(doc)

    return docs


def update_document(doc_id: str, updates: dict) -> None:
    """Update document fields"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    set_clauses = []
    values = []
    for key, value in updates.items():
        set_clauses.append(f"{key} = ?")
        if key == "parse_result":
            values.append(json.dumps(value))
        else:
            values.append(value)

    if set_clauses:
        values.append(doc_id)
        cursor.execute(
            f"UPDATE documents SET {', '.join(set_clauses)} WHERE id = ?",
            values
        )

    conn.commit()
    conn.close()


# =============================================================================
# Teaching Session Tables
# =============================================================================

def init_db_teaching():
    """Initialize teaching tables"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Teaching sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teaching_sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            document_id TEXT,
            status TEXT DEFAULT 'pending',
            current_iteration INTEGER DEFAULT 0,
            max_iterations INTEGER DEFAULT 3,
            current_phase TEXT DEFAULT 'design',
            knowledge_points TEXT DEFAULT '[]',
            raw_text TEXT DEFAULT '',
            teaching_script TEXT DEFAULT '',
            quiz_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        )
    """)

    # Migration: Add missing columns to existing tables
    try:
        cursor.execute("ALTER TABLE teaching_sessions ADD COLUMN quiz_id TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Teaching agents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teaching_agents (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            name TEXT NOT NULL,
            agent_type TEXT NOT NULL,
            level TEXT,
            system_prompt TEXT NOT NULL,
            avatar TEXT DEFAULT '🤖',
            status TEXT DEFAULT 'idle',
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES teaching_sessions(id)
        )
    """)

    # Teaching messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teaching_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            agent_name TEXT DEFAULT '',
            agent_type TEXT DEFAULT '',
            phase TEXT DEFAULT 'design',
            iteration INTEGER DEFAULT 0,
            content TEXT NOT NULL,
            refs TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES teaching_sessions(id)
        )
    """)

    # Supervisor suggestions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS supervisor_suggestions (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            agent_name TEXT DEFAULT '',
            iteration INTEGER DEFAULT 0,
            phase TEXT DEFAULT 'supervisor_comment',
            suggestion_content TEXT NOT NULL,
            dimension TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES teaching_sessions(id)
        )
    """)

    conn.commit()
    conn.close()


# Initialize teaching tables on module load
init_db_teaching()


# =============================================================================
# Teaching Session Operations
# =============================================================================

def save_teaching_session(session_data: dict) -> None:
    """Save or update a teaching session"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO teaching_sessions
        (id, title, document_id, status, current_iteration, max_iterations,
         current_phase, knowledge_points, raw_text, teaching_script, quiz_id,
         created_at, updated_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_data["id"],
        session_data["title"],
        session_data.get("document_id"),
        session_data.get("status", "pending"),
        session_data.get("current_iteration", 0),
        session_data.get("max_iterations", 3),
        session_data.get("current_phase", "design"),
        json.dumps(session_data.get("knowledge_points", [])),
        session_data.get("raw_text", ""),
        session_data.get("teaching_script", ""),
        session_data.get("quiz_id"),
        session_data["created_at"],
        session_data["updated_at"],
        session_data.get("completed_at"),
    ))

    conn.commit()
    conn.close()


def load_teaching_sessions() -> List[dict]:
    """Load all teaching sessions"""
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM teaching_sessions ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()

    sessions = []
    for row in rows:
        session = dict(row)
        session["knowledge_points"] = json.loads(session["knowledge_points"])
        sessions.append(session)

    return sessions


def load_teaching_session(session_id: str) -> Optional[dict]:
    """Load a specific teaching session"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM teaching_sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        session = dict(row)
        session["knowledge_points"] = json.loads(session["knowledge_points"])
        # quiz_id is loaded directly from the row
        return session
    return None


def update_teaching_session(session_id: str, updates: dict) -> None:
    """Update teaching session fields"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    set_clauses = []
    values = []
    for key, value in updates.items():
        set_clauses.append(f"{key} = ?")
        values.append(value)

    if set_clauses:
        values.append(session_id)
        cursor.execute(
            f"UPDATE teaching_sessions SET {', '.join(set_clauses)} WHERE id = ?",
            values
        )

    conn.commit()
    conn.close()


def delete_teaching_session(session_id: str) -> None:
    """Delete a teaching session and all related data"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM teaching_messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM teaching_agents WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM supervisor_suggestions WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM teaching_sessions WHERE id = ?", (session_id,))

    conn.commit()
    conn.close()


# =============================================================================
# Teaching Agent Operations
# =============================================================================

def save_teaching_agent(agent_data: dict) -> None:
    """Save or update a teaching agent"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO teaching_agents
        (id, session_id, name, agent_type, level, system_prompt, avatar, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        agent_data["id"],
        agent_data["session_id"],
        agent_data["name"],
        agent_data["agent_type"],
        agent_data.get("level"),
        agent_data["system_prompt"],
        agent_data.get("avatar", "🤖"),
        agent_data.get("status", "idle"),
        agent_data.get("created_at"),
    ))

    conn.commit()
    conn.close()


def load_teaching_agents(session_id: str) -> List[dict]:
    """Load all teaching agents for a session"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM teaching_agents WHERE session_id = ?", (session_id,))
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def load_teaching_agent(agent_id: str) -> Optional[dict]:
    """Load a specific teaching agent"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM teaching_agents WHERE id = ?", (agent_id,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def delete_teaching_agent(agent_id: str) -> None:
    """Delete a teaching agent"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM teaching_agents WHERE id = ?", (agent_id,))

    conn.commit()
    conn.close()


# =============================================================================
# Teaching Message Operations
# =============================================================================

def save_teaching_message(message_data: dict) -> None:
    """Save a teaching message"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO teaching_messages
        (id, session_id, agent_id, agent_name, agent_type, phase, iteration, content, refs, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        message_data["id"],
        message_data["session_id"],
        message_data["agent_id"],
        message_data.get("agent_name", ""),
        message_data.get("agent_type", ""),
        message_data.get("phase", "design"),
        message_data.get("iteration", 0),
        message_data["content"],
        json.dumps(message_data.get("references", [])),
        message_data.get("created_at"),
    ))

    conn.commit()
    conn.close()


def load_teaching_messages(session_id: str, limit: int = 1000) -> List[dict]:
    """Load all messages for a teaching session"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM teaching_messages
        WHERE session_id = ?
        ORDER BY created_at ASC
        LIMIT ?
    """, (session_id, limit))

    rows = cursor.fetchall()
    conn.close()

    messages = []
    for row in rows:
        msg = dict(row)
        msg["references"] = json.loads(msg.get("refs", "[]"))
        messages.append(msg)

    return messages


# =============================================================================
# Supervisor Suggestion Operations
# =============================================================================

def save_supervisor_suggestion(suggestion_data: dict) -> None:
    """Save a supervisor suggestion"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO supervisor_suggestions
        (id, session_id, agent_id, agent_name, iteration, phase, suggestion_content, dimension, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        suggestion_data["id"],
        suggestion_data["session_id"],
        suggestion_data["agent_id"],
        suggestion_data.get("agent_name", ""),
        suggestion_data.get("iteration", 0),
        suggestion_data.get("phase", "supervisor_comment"),
        suggestion_data["suggestion_content"],
        suggestion_data.get("dimension", ""),
        suggestion_data.get("created_at"),
    ))

    conn.commit()
    conn.close()


def load_supervisor_suggestions(session_id: str, limit: int = 1000) -> List[dict]:
    """Load all supervisor suggestions for a teaching session"""
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM supervisor_suggestions
        WHERE session_id = ?
        ORDER BY created_at ASC
        LIMIT ?
    """, (session_id, limit))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def delete_supervisor_suggestion(suggestion_id: str) -> None:
    """Delete a supervisor suggestion"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM supervisor_suggestions WHERE id = ?", (suggestion_id,))

    conn.commit()
    conn.close()


# =============================================================================
# Quiz Tables
# =============================================================================

def init_db_quiz():
    """Initialize quiz tables"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Quizzes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            time_limit INTEGER DEFAULT 30,
            total_score REAL DEFAULT 100.0,
            passing_score REAL DEFAULT 60.0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES teaching_sessions(id)
        )
    """)

    # Quiz questions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_questions (
            id TEXT PRIMARY KEY,
            quiz_id TEXT NOT NULL,
            question_type TEXT NOT NULL,
            question_text TEXT NOT NULL,
            options TEXT DEFAULT '[]',
            correct_answer TEXT DEFAULT '',
            explanation TEXT DEFAULT '',
            knowledge_point_id TEXT,
            knowledge_point_title TEXT,
            difficulty TEXT DEFAULT 'medium',
            score REAL DEFAULT 10.0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (quiz_id) REFERENCES quizzes(id)
        )
    """)

    # Quiz results table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_results (
            id TEXT PRIMARY KEY,
            quiz_id TEXT NOT NULL UNIQUE,
            total_score REAL DEFAULT 0.0,
            max_score REAL DEFAULT 100.0,
            passed INTEGER DEFAULT 0,
            weak_knowledge_points TEXT DEFAULT '[]',
            improvement_suggestions TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY (quiz_id) REFERENCES quizzes(id)
        )
    """)

    # Quiz answers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_answers (
            id TEXT PRIMARY KEY,
            quiz_id TEXT NOT NULL,
            question_id TEXT NOT NULL,
            answer_text TEXT DEFAULT '',
            is_correct INTEGER DEFAULT 0,
            score REAL DEFAULT 0.0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (quiz_id) REFERENCES quizzes(id),
            FOREIGN KEY (question_id) REFERENCES quiz_questions(id)
        )
    """)

    conn.commit()
    conn.close()


# Initialize quiz tables on module load
init_db_quiz()


# =============================================================================
# Quiz Operations
# =============================================================================

def save_quiz(quiz_data: dict) -> None:
    """Save or update a quiz"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO quizzes
        (id, session_id, title, description, time_limit, total_score, passing_score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        quiz_data["id"],
        quiz_data["session_id"],
        quiz_data.get("title", ""),
        quiz_data.get("description", ""),
        quiz_data.get("time_limit", 30),
        quiz_data.get("total_score", 100.0),
        quiz_data.get("passing_score", 60.0),
        quiz_data.get("created_at"),
    ))

    conn.commit()
    conn.close()


def load_quizzes() -> List[dict]:
    """Load all quizzes"""
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM quizzes ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def load_quiz(quiz_id: str) -> Optional[dict]:
    """Load a specific quiz"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def delete_quiz(quiz_id: str) -> None:
    """Delete a quiz and all related data"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM quiz_answers WHERE quiz_id = ?", (quiz_id,))
    cursor.execute("DELETE FROM quiz_questions WHERE quiz_id = ?", (quiz_id,))
    cursor.execute("DELETE FROM quiz_results WHERE quiz_id = ?", (quiz_id,))
    cursor.execute("DELETE FROM quizzes WHERE id = ?", (quiz_id,))

    conn.commit()
    conn.close()


# =============================================================================
# Quiz Question Operations
# =============================================================================

def save_quiz_question(question_data: dict) -> None:
    """Save or update a quiz question"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO quiz_questions
        (id, quiz_id, question_type, question_text, options, correct_answer,
         explanation, knowledge_point_id, knowledge_point_title, difficulty, score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        question_data["id"],
        question_data["quiz_id"],
        question_data.get("question_type", "single_choice"),
        question_data.get("question_text", ""),
        json.dumps(question_data.get("options", [])),
        question_data.get("correct_answer", ""),
        question_data.get("explanation", ""),
        question_data.get("knowledge_point_id"),
        question_data.get("knowledge_point_title"),
        question_data.get("difficulty", "medium"),
        question_data.get("score", 10.0),
        question_data.get("created_at"),
    ))

    conn.commit()
    conn.close()


def load_quiz_questions(quiz_id: str) -> List[dict]:
    """Load all questions for a quiz"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM quiz_questions WHERE quiz_id = ? ORDER BY created_at ASC", (quiz_id,))
    rows = cursor.fetchall()
    conn.close()

    questions = []
    for row in rows:
        question = dict(row)
        question["options"] = json.loads(question.get("options", "[]"))
        questions.append(question)

    return questions


def load_quiz_question(question_id: str) -> Optional[dict]:
    """Load a specific quiz question"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM quiz_questions WHERE id = ?", (question_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        question = dict(row)
        question["options"] = json.loads(question.get("options", "[]"))
        return question
    return None


def delete_quiz_question(question_id: str) -> None:
    """Delete a quiz question"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM quiz_questions WHERE id = ?", (question_id,))

    conn.commit()
    conn.close()


# =============================================================================
# Quiz Result Operations
# =============================================================================

def save_quiz_result(result_data: dict) -> None:
    """Save or update a quiz result"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Save result
    cursor.execute("""
        INSERT OR REPLACE INTO quiz_results
        (id, quiz_id, total_score, max_score, passed,
         weak_knowledge_points, improvement_suggestions, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result_data["id"],
        result_data["quiz_id"],
        result_data.get("total_score", 0.0),
        result_data.get("max_score", 100.0),
        1 if result_data.get("passed", False) else 0,
        json.dumps(result_data.get("weak_knowledge_points", [])),
        json.dumps(result_data.get("improvement_suggestions", [])),
        result_data.get("created_at"),
    ))

    # Save answers
    for answer in result_data.get("answers", []):
        cursor.execute("""
            INSERT OR REPLACE INTO quiz_answers
            (id, quiz_id, question_id, answer_text, is_correct, score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            answer["id"],
            answer["quiz_id"],
            answer["question_id"],
            answer.get("answer_text", ""),
            1 if answer.get("is_correct", False) else 0,
            answer.get("score", 0.0),
            answer.get("created_at"),
        ))

    conn.commit()
    conn.close()


def load_quiz_result(quiz_id: str) -> Optional[dict]:
    """Load the result for a quiz"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM quiz_results WHERE quiz_id = ?", (quiz_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    result = dict(row)
    result["passed"] = bool(result.get("passed", 0))
    result["weak_knowledge_points"] = json.loads(result.get("weak_knowledge_points", "[]"))
    result["improvement_suggestions"] = json.loads(result.get("improvement_suggestions", "[]"))

    # Load answers
    cursor.execute("SELECT * FROM quiz_answers WHERE quiz_id = ?", (quiz_id,))
    answer_rows = cursor.fetchall()

    answers = []
    for answer_row in answer_rows:
        answer = dict(answer_row)
        answer["is_correct"] = bool(answer.get("is_correct", 0))
        answers.append(answer)

    result["answers"] = answers
    conn.close()

    return result


def load_quiz_results_by_session(session_id: str) -> List[dict]:
    """Load all quiz results for a session"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT qr.* FROM quiz_results qr
        JOIN quizzes q ON qr.quiz_id = q.id
        WHERE q.session_id = ?
        ORDER BY qr.created_at DESC
    """, (session_id,))

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        result = dict(row)
        result["passed"] = bool(result.get("passed", 0))
        result["weak_knowledge_points"] = json.loads(result.get("weak_knowledge_points", "[]"))
        result["improvement_suggestions"] = json.loads(result.get("improvement_suggestions", "[]"))
        results.append(result)

    return results


def delete_quiz_result(result_id: str) -> None:
    """Delete a quiz result"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM quiz_answers WHERE quiz_id = (SELECT quiz_id FROM quiz_results WHERE id = ?)", (result_id,))
    cursor.execute("DELETE FROM quiz_results WHERE id = ?", (result_id,))

    conn.commit()
    conn.close()
