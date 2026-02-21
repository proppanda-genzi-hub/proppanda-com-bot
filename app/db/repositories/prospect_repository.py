from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger(__name__)


class ProspectRepository:
    """Repository for Prospect/Lead database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_prospect(self, data: dict):
        """
        Inserts a new prospect or updates existing one.
        Skips for common chatbot mode (no valid agent).
        """
        user_id = data.get("user_id")
        agent_id = data.get("agent_id")
        
        if not user_id or not agent_id:
            logger.error("Cannot upsert prospect: Missing user_id or agent_id")
            return

        # Check if agent exists (for common chatbot mode)
        try:
            agent_check = text("SELECT 1 FROM agent WHERE agent_id = :aid LIMIT 1")
            result = await self.db.execute(agent_check, {"aid": agent_id})
            agent_exists = result.scalar() is not None
            
            if not agent_exists:
                logger.info(f"Skipping prospect upsert - agent {agent_id} doesn't exist (common mode)")
                return
        except Exception as e:
            logger.error(f"Error checking agent existence: {e}")
            return

        # Generate placeholder email if not provided
        provided_email = data.get("email")
        placeholder_email = f"{user_id}@web.user"
        target_email = provided_email if provided_email else placeholder_email

        try:
            # First, try to check if record exists
            check_query = text("""
                SELECT 1 FROM prospect_info 
                WHERE user_id = :user_id AND agent_id = :agent_id
                LIMIT 1
            """)
            result = await self.db.execute(check_query, {"user_id": user_id, "agent_id": agent_id})
            exists = result.scalar() is not None

            if exists:
                # Update existing record
                update_query = text("""
                    UPDATE prospect_info SET
                        last_interaction = NOW(),
                        phone = COALESCE(:phone, phone),
                        name = COALESCE(:name, name),
                        gender = COALESCE(:gender, gender),
                        nationality = COALESCE(:nationality, nationality),
                        pass = COALESCE(:pass_type, pass),
                        profession = COALESCE(:profession, profession),
                        move_in_date = COALESCE(:move_in_date, move_in_date),
                        session_id = COALESCE(:session_id, session_id)
                    WHERE user_id = :user_id AND agent_id = :agent_id
                """)
                await self.db.execute(update_query, {
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "phone": data.get("phone"),
                    "name": data.get("name"),
                    "gender": data.get("gender"),
                    "nationality": data.get("nationality"),
                    "pass_type": data.get("pass_type", "-"),
                    "profession": data.get("profession"),
                    "move_in_date": data.get("move_in_date"),
                    "session_id": data.get("session_id"),
                })
            else:
                # Insert new record
                insert_query = text("""
                    INSERT INTO prospect_info (
                        user_id, agent_id, email, phone, name, gender, nationality, 
                        pass, profession, move_in_date, session_id, last_interaction
                    )
                    VALUES (
                        :user_id, :agent_id, :email, :phone, :name, :gender, :nationality, 
                        :pass_type, :profession, :move_in_date, :session_id, NOW()
                    )
                """)
                await self.db.execute(insert_query, {
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "email": target_email,
                    "phone": data.get("phone"),
                    "name": data.get("name"),
                    "gender": data.get("gender"),
                    "nationality": data.get("nationality"),
                    "pass_type": data.get("pass_type", "-"),
                    "profession": data.get("profession"),
                    "move_in_date": data.get("move_in_date"),
                    "session_id": data.get("session_id"),
                })
            
            # Don't commit here - let the caller handle it
            
        except Exception as e:
            logger.error(f"Error upserting prospect: {e}")
            # Don't rollback here - let the caller handle it

    async def update_email(self, agent_id: str, user_id: str, new_email: str):
        """
        Update prospect's email when they provide a real email address.
        """
        placeholder_email = f"{user_id}@web.user"

        try:
            # Check if new email already exists
            check_query = text(
                "SELECT 1 FROM prospect_info WHERE email = :new_email AND agent_id = :agent_id"
            )
            result = await self.db.execute(
                check_query, 
                {"new_email": new_email, "agent_id": agent_id}
            )
            
            if result.scalar():
                # Email exists - merge records
                logger.info(f"Email {new_email} exists. Merging identities.")
                
                merge_query = text("""
                    UPDATE prospect_info 
                    SET last_interaction = NOW()
                    WHERE email = :new_email AND agent_id = :agent_id
                """)
                await self.db.execute(
                    merge_query, 
                    {"new_email": new_email, "agent_id": agent_id}
                )
                
                # Delete placeholder record
                del_query = text(
                    "DELETE FROM prospect_info WHERE email = :placeholder AND agent_id = :agent_id"
                )
                await self.db.execute(
                    del_query, 
                    {"placeholder": placeholder_email, "agent_id": agent_id}
                )
            else:
                # Update placeholder to real email
                update_query = text("""
                    UPDATE prospect_info 
                    SET email = :new_email 
                    WHERE email = :placeholder AND agent_id = :agent_id
                """)
                await self.db.execute(update_query, {
                    "new_email": new_email,
                    "placeholder": placeholder_email,
                    "agent_id": agent_id
                })

            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error updating email: {e}")
            await self.db.rollback()
