from langgraph.checkpoint.memory import MemorySaver

# Create checkpointer globally for memory persistence
_checkpointer = MemorySaver()


async def get_checkpointer(engine):
    """
    Get the checkpointer for LangGraph state persistence.
    """
    return _checkpointer
