from app.db.repositories.agent_repository import AgentRepository
import logging

logger = logging.getLogger(__name__)


class AgentResolver:
    """
    Resolves agent information from the database.
    """
    
    def __init__(self, db):
        self.repository = AgentRepository(db)

    async def resolve_by_agent_id(self, agent_id: str):
        """
        Resolve agent by their unique agent_id.
        """
        try:
            agent = await self.repository.get_agent_by_id(agent_id)
            
            if agent:
                logger.info(f"Resolved Agent: {agent.name} (ID: {agent.agent_id})")
                return agent
            else:
                logger.warning(f"No agent found for ID: {agent_id}")
                return None

        except Exception as e:
            logger.error(f"Error resolving agent: {e}")
            return None

    async def resolve_by_email(self, email: str):
        """
        Resolve agent by their email address.
        """
        try:
            agent = await self.repository.get_agent_by_email(email)
            
            if agent:
                logger.info(f"Resolved Agent: {agent.name} (Email: {email})")
                return agent
            else:
                logger.warning(f"No agent found for email: {email}")
                return None

        except Exception as e:
            logger.error(f"Error resolving agent by email: {e}")
            return None
