from langchain_core.runnables import RunnableConfig
from app.core.state import AgentState
import logging

logger = logging.getLogger(__name__)


async def clear_memory_node(state: AgentState, config: RunnableConfig):
    """
    Wipes the 'filters' from the state to start a fresh search.
    """
    new_target = state.get("target_table")
    logger.info(f"🧹 Clearing Search History. New Target: {new_target}")
    
    return {
        "filters": None, 
        "next_step": "CHECK_CAPABILITY"
    }
