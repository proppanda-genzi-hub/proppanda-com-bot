from sqlalchemy import text
import uuid
from datetime import datetime, timedelta, timezone
import logging
import json

logger = logging.getLogger(__name__)


class ConversationService:
    """Service for managing conversation history and sessions."""
    
    def __init__(self, db_session):
        self.db = db_session

    async def get_active_session_id(self, user_id: str, provided_session_id: str = None) -> str:
        """
        Retrieves the current session ID or creates a new one.
        """
        # If session ID provided and still active, use it
        if provided_session_id:
            query = text("""
                SELECT session_id, created_at 
                FROM chat_history_web 
                WHERE session_id = :session_id 
                ORDER BY created_at DESC 
                LIMIT 1
            """)
            
            result = await self.db.execute(query, {"session_id": provided_session_id})
            last_record = result.mappings().first()
            
            if last_record:
                last_time = last_record['created_at']
                if last_time.tzinfo:
                    now = datetime.now(timezone.utc)
                else:
                    now = datetime.now()
                
                time_diff = now - last_time
                
                if time_diff < timedelta(minutes=30):
                    return provided_session_id
        
        # Check for any recent session by user_id
        query = text("""
            SELECT session_id, created_at 
            FROM chat_history_web 
            WHERE user_id = :user_id 
            ORDER BY created_at DESC 
            LIMIT 1
        """)
        
        result = await self.db.execute(query, {"user_id": user_id})
        last_record = result.mappings().first()

        if last_record:
            last_time = last_record['created_at']
            if last_time.tzinfo:
                now = datetime.now(timezone.utc)
            else:
                now = datetime.now()

            time_diff = now - last_time
            
            if time_diff < timedelta(minutes=30):
                return last_record['session_id']

        # Create new session
        new_session = provided_session_id or str(uuid.uuid4())
        logger.info(f"🆕 Starting new session: {new_session} for user {user_id}")
        return new_session

    async def log_message(
        self, 
        session_id: str, 
        user_id: str, 
        agent_id: str, 
        sender: str, 
        message: str, 
        metadata: dict = None
    ):
        """
        Logs a message (User or Bot) into the database.
        Uses commonbotlog table if agent doesn't exist (common chatbot mode).
        """
        try:
            # Check if agent exists in database
            agent_exists = False
            if agent_id:
                check_query = text("SELECT 1 FROM agent WHERE agent_id = :aid LIMIT 1")
                result = await self.db.execute(check_query, {"aid": agent_id})
                agent_exists = result.scalar() is not None
            
            if agent_exists:
                # Use chat_history_web for agent-specific chatbot
                query = text("""
                    INSERT INTO chat_history_web (session_id, user_id, agent_id, sender, message, metadata)
                    VALUES (:sid, :uid, :aid, :sender, :msg, :meta)
                """)
                
                await self.db.execute(query, {
                    "sid": session_id,
                    "uid": user_id,
                    "aid": agent_id,
                    "sender": sender,
                    "msg": message,
                    "meta": json.dumps(metadata, default=str) if metadata else "{}"
                })
            else:
                # Use commonbotlog for common chatbot (no agent)
                query = text("""
                    INSERT INTO commonbotlog (session_id, user_id, sender, message, metadata)
                    VALUES (:sid, :uid, :sender, :msg, :meta)
                """)
                
                await self.db.execute(query, {
                    "sid": session_id,
                    "uid": user_id,
                    "sender": sender,
                    "msg": message,
                    "meta": json.dumps(metadata, default=str) if metadata else "{}"
                })
                logger.debug(f"📝 Logged to commonbotlog: {sender} - {message[:50]}...")
            
        except Exception as e:
            logger.error(f"Failed to log chat message: {e}")

    async def get_session_history(self, session_id: str, limit: int = 50) -> list:
        """
        Retrieve conversation history for a specific session.
        """
        try:
            query = text("""
                SELECT sender, message, created_at, metadata
                FROM chat_history_web
                WHERE session_id = :session_id
                ORDER BY created_at ASC
                LIMIT :limit
            """)
            
            result = await self.db.execute(query, {
                "session_id": session_id,
                "limit": limit
            })
            
            messages = []
            for row in result.mappings().all():
                msg = dict(row)
                if isinstance(msg.get('metadata'), str):
                    try:
                        msg['metadata'] = json.loads(msg['metadata'])
                    except:
                        msg['metadata'] = {}
                messages.append(msg)
            
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get session history: {e}")
            return []

    async def get_user_sessions(self, user_id: str, limit: int = 10) -> list:
        """
        Get all sessions for a specific user.
        """
        try:
            query = text("""
                SELECT 
                    session_id,
                    MIN(created_at) as started_at,
                    MAX(created_at) as last_message_at,
                    COUNT(*) as message_count
                FROM chat_history_web
                WHERE user_id = :user_id
                GROUP BY session_id
                ORDER BY MAX(created_at) DESC
                LIMIT :limit
            """)
            
            result = await self.db.execute(query, {
                "user_id": user_id,
                "limit": limit
            })
            
            return [dict(row) for row in result.mappings().all()]
            
        except Exception as e:
            logger.error(f"Failed to get user sessions: {e}")
            return []
