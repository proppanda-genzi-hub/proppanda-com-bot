from app.core.state import AgentState


def decision_node(state: AgentState):
    """
    Traffic Cop Logic:
    Checks the 'filters' state to decide what to do next.
    Accepts flexible location preferences like "anywhere", "no preference".
    """
    filters = state.get("filters")
    inv_status = state.get("inventory_check_status")

    props = state.get("found_properties")
    shown = state.get("shown_count", 0)

    if inv_status == "PENDING":
        return {"next_step": "check_inventory"}

    if props and shown < len(props):
        last_msg = state["messages"][-1].content.lower()
        positive_keywords = ["yes", "show", "more", "next", "okay", "sure", "go ahead", "yup", "yeah", "yea", "please"]
        
        if any(w in last_msg for w in positive_keywords):
            return {"next_step": "display_results"}
        
    # Define flexible location keywords
    flexible_locations = ["anywhere", "no preference", "flexible", "any", "doesnt matter", "doesn't matter", "no prefernce"]
    
    # PRIORITY 1: CRITICAL SEARCH FIELDS
    # Check if location is provided OR user has expressed flexibility
    has_location = False
    if filters and filters.location_query:
        location_lower = filters.location_query.lower()
        # Accept if it's a specific location OR a flexible preference
        if any(flex in location_lower for flex in flexible_locations):
            has_location = True  # Accept flexible location
        elif filters.location_query.strip():
            has_location = True  # Accept specific location
    
    if not has_location:
        return {"next_step": "ask_location"}
    
    if not filters.budget_max:
        return {"next_step": "ask_budget"}
    
    # Make move_in_date optional for flexible users
    # if not filters.move_in_date:
    #     return {"next_step": "ask_date"}

    # PRIORITY 2: ESSENTIAL DEMOGRAPHICS (Optional for search)
    # Make these optional to reduce repetitive questions
    # if not filters.tenant_gender:
    #     return {"next_step": "ask_gender"}

    # if not filters.tenant_nationality:
    #     return {"next_step": "ask_nationality"}

    # IF BASIC FIELDS ARE PRESENT
    return {"next_step": "execute_search"}
