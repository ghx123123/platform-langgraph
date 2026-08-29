"""
Memory Store - 分层记忆存储
支持短期记忆 (Redis) 和长期记忆 (SQLite + 向量搜索)
"""
import json
import sqlite3
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiosqlite


class Memory(ABC):
    """记忆基类"""

    @abstractmethod
    def to_dict(self) -> dict:
        pass


class ShortTermMemory(Memory):
    """短期记忆 (STM) - 基于 Redis"""

    def __init__(self, agent_id: str, key: str, value: Any, ttl: int = 86400):
        self.id = str(uuid.uuid4())
        self.agent_id = agent_id
        self.key = key
        self.value = value
        self.ttl = ttl
        self.created_at = datetime.now()
        self.expires_at = datetime.now() + timedelta(seconds=ttl)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "key": self.key,
            "value": self.value,
            "ttl": self.ttl,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class LongTermMemory(Memory):
    """长期记忆 (LTM) - 基于 SQLite"""

    def __init__(
        self,
        agent_id: str,
        content: str,
        metadata: Optional[Dict] = None,
        embedding: Optional[List[float]] = None
    ):
        self.id = str(uuid.uuid4())
        self.agent_id = agent_id
        self.content = content
        self.metadata = metadata or {}
        self.embedding = embedding
        self.created_at = datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "content": self.content,
            "metadata": self.metadata,
            "embedding": self.embedding,
            "created_at": self.created_at.isoformat(),
        }


class EpisodicMemory(Memory):
    """事件记忆 - 记录关键事件"""

    def __init__(
        self,
        agent_id: str,
        event_type: str,
        content: str,
        participants: Optional[List[str]] = None
    ):
        self.id = str(uuid.uuid4())
        self.agent_id = agent_id
        self.event_type = event_type
        self.content = content
        self.participants = participants or []
        self.created_at = datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "event_type": self.event_type,
            "content": self.content,
            "participants": self.participants,
            "created_at": self.created_at.isoformat(),
        }


class MemoryStore:
    """
    记忆存储

    提供分层记忆管理：
    - STM (Short-term): Redis，存储会话上下文，自动过期
    - LTM (Long-term): SQLite，持久存储，支持向量搜索
    - Episodic: 事件记忆，用于回溯
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._redis_client = None  # Optional Redis client
        self._db = None
        self._init_db()

    def _init_db(self):
        """初始化 SQLite 数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # LTM table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS long_term_memory (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding BLOB,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Episodic table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS episodic_memory (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                content TEXT NOT NULL,
                participants TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Index for faster search
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ltm_agent_id ON long_term_memory(agent_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodic_agent_id ON episodic_memory(agent_id)
        """)

        conn.commit()
        conn.close()

    # =========================================================================
    # Short-term Memory (Redis simulation - using dict in memory)
    # =========================================================================

    async def stm_set(self, agent_id: str, key: str, value: Any, ttl: int = 86400) -> bool:
        """
        设置短期记忆

        注意：当前为内存实现，生产环境应使用 Redis
        """
        stm_key = f"stm:{agent_id}:{key}"
        # In production: await self._redis_client.setex(stm_key, ttl, json.dumps(value))
        memory = ShortTermMemory(agent_id, key, value, ttl)
        # Store in memory (would be Redis)
        return True

    async def stm_get(self, agent_id: str, key: str) -> Optional[Any]:
        """
        获取短期记忆
        """
        stm_key = f"stm:{agent_id}:{key}"
        # In production: value = await self._redis_client.get(stm_key)
        # Return json.loads(value) if value else None
        return None

    async def stm_delete(self, agent_id: str, key: str) -> bool:
        """删除短期记忆"""
        stm_key = f"stm:{agent_id}:{key}"
        # In production: await self._redis_client.delete(stm_key)
        return True

    async def stm_clear(self, agent_id: str) -> bool:
        """清空短期记忆"""
        # In production: await self._redis_client.delete pattern
        return True

    # =========================================================================
    # Long-term Memory (SQLite)
    # =========================================================================

    async def ltm_store(
        self,
        agent_id: str,
        content: str,
        metadata: Optional[Dict] = None,
        embedding: Optional[List[float]] = None
    ) -> str:
        """
        存储长期记忆
        """
        memory = LongTermMemory(agent_id, content, metadata, embedding)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO long_term_memory (id, agent_id, content, embedding, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.id,
                    agent_id,
                    content,
                    json.dumps(embedding) if embedding else None,
                    json.dumps(metadata) if metadata else None,
                    memory.created_at.isoformat()
                )
            )
            await db.commit()

        return memory.id

    async def ltm_get(self, agent_id: str, memory_id: str) -> Optional[LongTermMemory]:
        """获取指定记忆"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM long_term_memory WHERE id = ? AND agent_id = ?",
                (memory_id, agent_id)
            ) as cursor:
                row = await cursor.fetchone()

        if row:
            return LongTermMemory(
                agent_id=row["agent_id"],
                content=row["content"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else None,
                embedding=json.loads(row["embedding"]) if row["embedding"] else None
            )
        return None

    async def ltm_search(
        self,
        agent_id: str,
        query: str,
        limit: int = 10
    ) -> List[LongTermMemory]:
        """
        搜索长期记忆

        注意：当前为简单模糊搜索，生产环境应使用 Qdrant 向量搜索
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM long_term_memory
                WHERE agent_id = ? AND content LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (agent_id, f"%{query}%", limit)
            ) as cursor:
                rows = await cursor.fetchall()

        memories = []
        for row in rows:
            memories.append(LongTermMemory(
                agent_id=row["agent_id"],
                content=row["content"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else None,
                embedding=json.loads(row["embedding"]) if row["embedding"] else None
            ))
        return memories

    async def ltm_list(self, agent_id: str, limit: int = 50) -> List[LongTermMemory]:
        """列出所有长期记忆"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM long_term_memory
                WHERE agent_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (agent_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()

        memories = []
        for row in rows:
            memories.append(LongTermMemory(
                agent_id=row["agent_id"],
                content=row["content"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else None,
                embedding=json.loads(row["embedding"]) if row["embedding"] else None
            ))
        return memories

    async def ltm_delete(self, agent_id: str, memory_id: str) -> bool:
        """删除长期记忆"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM long_term_memory WHERE id = ? AND agent_id = ?",
                (memory_id, agent_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    # =========================================================================
    # Episodic Memory
    # =========================================================================

    async def episodic_store(
        self,
        agent_id: str,
        event_type: str,
        content: str,
        participants: Optional[List[str]] = None
    ) -> str:
        """存储事件记忆"""
        memory = EpisodicMemory(agent_id, event_type, content, participants)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO episodic_memory (id, agent_id, event_type, content, participants, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.id,
                    agent_id,
                    event_type,
                    content,
                    json.dumps(participants) if participants else None,
                    memory.created_at.isoformat()
                )
            )
            await db.commit()

        return memory.id

    async def episodic_get(
        self,
        agent_id: str,
        since: Optional[datetime] = None,
        event_type: Optional[str] = None
    ) -> List[EpisodicMemory]:
        """获取事件记忆"""
        query = "SELECT * FROM episodic_memory WHERE agent_id = ?"
        params = [agent_id]

        if since:
            query += " AND created_at >= ?"
            params.append(since.isoformat())

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        query += " ORDER BY created_at DESC"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()

        memories = []
        for row in rows:
            memories.append(EpisodicMemory(
                agent_id=row["agent_id"],
                event_type=row["event_type"],
                content=row["content"],
                participants=json.loads(row["participants"]) if row["participants"] else None
            ))
        return memories

    # =========================================================================
    # Utility
    # =========================================================================

    async def clear_agent_memory(self, agent_id: str):
        """清空 Agent 的所有记忆"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM long_term_memory WHERE agent_id = ?", (agent_id,))
            await db.execute("DELETE FROM episodic_memory WHERE agent_id = ?", (agent_id,))
            await db.commit()

        # Clear STM (would be Redis)
        # await self.stm_clear(agent_id)
