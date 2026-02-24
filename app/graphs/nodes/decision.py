from app.core.state import AgentState


def _is_residential(target_table: str) -> bool:
    return "residential" in (target_table or "")


def decision_node(state: AgentState):
    """
    Minimal Traffic Cop — asks only what is necessary to run a meaningful search.

    Before search, we collect:
      • BOTH types : location, budget_max
      • Coliving only : tenant_gender (needed for environment matching)
      • Residential   : nothing extra — bedrooms/property_type already extracted by LLM from first message

    All other demographics (nationality, pass_type, phone, profession, age_group)
    are collected AFTER properties are shown, when the user asks a follow-up question.
    """
    filters = state.get("filters")
    inv_status = state.get("inventory_check_status")
    target_table = state.get("target_table", "")
    is_residential = _is_residential(target_table)

    props = state.get("found_properties")
    shown = state.get("shown_count", 0)

    # Inventory check (coliving only)
    if inv_status == "PENDING":
        return {"next_step": "check_inventory"}

    # Pagination — show more results
    if props and shown < len(props):
        last_msg = state["messages"][-1].content.lower()
        positive_keywords = ["yes", "show", "more", "next", "okay", "sure", "go ahead",
                             "yup", "yeah", "yea", "please"]
        if any(w in last_msg for w in positive_keywords):
            return {"next_step": "display_results"}

    # Flexible location keywords
    flexible_locations = ["anywhere", "no preference", "flexible", "any",
                          "doesnt matter", "doesn't matter", "no prefernce", "anything is fine"]

    # --- PRIORITY 1: LOCATION (mandatory for both types) ---
    has_location = False
    if filters and filters.location_query:
        location_lower = filters.location_query.lower()
        if any(flex in location_lower for flex in flexible_locations):
            has_location = True
        elif filters.location_query.strip():
            has_location = True

    if not has_location:
        return {"next_step": "ask_location"}

    # --- PRIORITY 2: BUDGET (mandatory for both types) ---
    if not (filters and filters.budget_max):
        return {"next_step": "ask_budget"}

    # --- PRIORITY 3: GENDER (coliving only — needed to match environment) ---
    if not is_residential:
        if not (filters and filters.tenant_gender):
            return {"next_step": "ask_gender"}

    # --- READY TO SEARCH ---
    return {"next_step": "execute_search"}
