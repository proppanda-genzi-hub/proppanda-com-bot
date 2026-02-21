from sqlalchemy import select
from sqlalchemy.orm import load_only
from app.db.models import Agent
from sqlalchemy.ext.asyncio import AsyncSession


class AgentRepository:
    """Repository for Agent database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_agent_by_id(self, agent_id: str):
        """
        Get agent by their unique agent_id.
        """
        query = (
            select(Agent)
            .where(Agent.agent_id == agent_id)
            .options(
                load_only(
                    Agent.agent_id,
                    Agent.name,
                    Agent.email,
                    Agent.chatbot_enabled,
                    Agent.chatbot_name,
                    Agent.company_name,
                    Agent.bio,
                    Agent.registration_no,
                    Agent.co_living_property,
                    Agent.rooms_for_rent,
                    Agent.residential_property_rent,
                    Agent.residential_property_resale,
                    Agent.residential_property_developer,
                    Agent.commercial_property_rent,
                    Agent.commercial_property_resale,
                    Agent.commercial_property_developer,
                )
            )
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_agent_by_email(self, email: str):
        """
        Get agent by their email address.
        """
        query = (
            select(Agent)
            .where(Agent.email == email)
            .options(
                load_only(
                    Agent.agent_id,
                    Agent.name,
                    Agent.email,
                    Agent.chatbot_enabled,
                    Agent.chatbot_name,
                    Agent.company_name,
                    Agent.bio,
                    Agent.registration_no,
                    Agent.co_living_property,
                    Agent.rooms_for_rent,
                    Agent.residential_property_rent,
                    Agent.residential_property_resale,
                    Agent.residential_property_developer,
                    Agent.commercial_property_rent,
                    Agent.commercial_property_resale,
                    Agent.commercial_property_developer,
                )
            )
        )
        result = await self.db.execute(query)
        return result.scalars().first()

    async def get_all_agents(self, limit: int = 100):
        """
        Get all active agents.
        """
        query = (
            select(Agent)
            .where(Agent.chatbot_enabled == True)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return result.scalars().all()
