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
    shown_properties_details: Optional[List[Dict[str, Any]]]  # Stores details of shown properties
    last_extraction_was_empty: Optional[bool]
    validation_error: Optional[str]

    # 7. Appointment Data
    selected_property: Optional[Dict[str, Any]] 
    appointment_state: Optional[Dict[str, Any]] 
    available_slots: Optional[str]
    
    # 8. Inventory Check Status
    inventory_check_status: Annotated[Optional[str], replace_value]
