from typing import TypedDict, Annotated, List, Optional, Dict, Any
from langgraph.graph.message import add_messages
from app.schemas.property_search import PropertySearchFilters


def replace_value(existing, new):
    """Reducer that replaces the value only if the new value is not None."""
    if new is None:
        return existing
    return new


class AgentState(TypedDict):
    """
    State definition for the agentic chatbot.
    """

    # 1. Chat History
    messages: Annotated[List, add_messages]

    # 2. Property Search Filters
    filters: Optional[PropertySearchFilters]

    # 3. Context Information
    agent_id: str
    user_mobile: str
    user_name: str
    agent_name: str
    company_name: str
    agent_bio: str

    # 4. Internal Logic Flags
    next_step: Optional[str]
    target_table: Optional[str]
    clarification_question: Optional[str]

    # 5. Active Flow Tracking
    active_flow: Optional[str]

    # 6. Search Results
    found_properties: Optional[List[Dict[str, Any]]]
    shown_count: Optional[int]
    shown_properties_details: Optional[List[Dict[str, Any]]]
    last_extraction_was_empty: Optional[bool]
    validation_error: Optional[str]

    # 7. Inventory Check Status
    inventory_check_status: Annotated[Optional[str], replace_value]

    # 8. Lead / User Data
    user_email: Optional[str]            # Email collected at start of conversation
    lead_data: Optional[Dict[str, Any]]  # Raw lead record from prop_panda_com_leads

    # 9. Post-search lead collection
    pending_follow_up: Optional[str]     # Stores the user's follow-up question while we collect lead details
