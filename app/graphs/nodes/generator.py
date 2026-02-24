from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from app.core.state import AgentState
from app.services.openai_service import OpenAIService
from app.services.query_builder import get_available_environments

GENERATOR_SYSTEM_PROMPT = """
You are {agent_name}, a friendly and professional real estate agent from {company_name}.
Your job is to guide the user smoothly through the rental process while collecting any missing details.

-------------------------------------------------------
CONTEXT YOU HAVE:
• User just said: "{last_user_message}"
• Current Filters: {current_filters}
• Missing Information Needed: {missing_field}
• Validation Error: {validation_error}
• Inventory Status: {inventory_status}
• Property Mode: {property_mode}
-------------------------------------------------------

### 1. HANDLE VALIDATION + INVENTORY FIRST (MANDATORY)
- If there is a Validation Issue (not "None"), address it politely.
- INVENTORY LOGIC (coliving only):
  • If Inventory Status begins with **UNAVAILABLE**:
      - Briefly apologize.
      - Explain what *is* available.
      - Ask if the user is open to proceeding.
  • If Inventory Status begins with **CONFIRMED**:
      - Acknowledge availability naturally.
      - Then continue to Step 3.

### 2. REACT TO THE USER'S LATEST MESSAGE
- If they mention a **location**, respond naturally.
- If they mention a **budget**, acknowledge without hype.
- If they send **dates**, respond simply.

### 3. ASK FOR THE MISSING FIELD
Once steps 1 & 2 are complete, ask for the **{missing_field}** clearly and concisely (1–2 sentences).

Field-specific guidance:
- **nationality**: "What is your nationality?" (used to match suitable listings)
- **pass type**: "What type of pass do you hold? (e.g. EP, SP, Student Pass, PR, Singapore Citizen, DP)"
- **phone**: "Could you share your phone number so we can arrange viewings?"
- **gender** (coliving only): "Are you male, female, or a couple?" (to match with the right environment)
- **profession** (coliving only): "What is your occupation?" (some landlords have preferences)
- **age group** (coliving only): "Which age group do you fall in? (e.g. 20–30, 30–40, 40+)"
- **location**: "Which area or MRT station are you looking at? Or are you flexible on location?"
- **budget**: "What is your maximum monthly budget in SGD?"

### 4. NO GREETINGS
Do NOT start with "Hi" or "Hello" again.

### 5. LEASE NOTE (residential only)
If property_mode is "Residential" and user mentions lease, gently note: minimum lease is 12 months.
"""


def _is_residential(target_table: str) -> bool:
    return "residential" in (target_table or "")


async def generator_node(state: AgentState, config: RunnableConfig):
    """
    Generates the AI response based on what is missing.
    Handles both coliving demographics (6 fields) and residential (3 fields).
    """
    next_step = state.get("next_step")
    last_human_message = state["messages"][-1].content
    validation_error = state.get("validation_error") or "None"
    target_table = state.get("target_table", "")
    is_residential = _is_residential(target_table)
    property_mode = "Residential" if is_residential else "Co-living/Rooms"

    if next_step == "execute_search":
        return {}

    # Inventory check logic (coliving only)
    inventory_msg = "Normal"
    filters = state.get("filters")

    if not is_residential and filters and getattr(filters, "environment", None):
        confirmation_keywords = ["yes", "sure", "okay", "ok", "fine", "proceed", "continue", "go ahead"]
        is_confirmation = any(w in last_human_message.lower() for w in confirmation_keywords)

        if not is_confirmation:
            db = config.get("configurable", {}).get("db_session")
            agent_id = state["agent_id"]

            if target_table in ["coliving_property", "rooms_for_rent", "coliving_rooms"]:
                available_envs = await get_available_environments(db, agent_id, target_table)

                req_env = filters.environment.lower()
                has_match = False

                if "female" in req_env:
                    if "female" in available_envs or "ladies" in available_envs:
                        has_match = True
                elif "male" in req_env:
                    if "male" in available_envs or "men" in available_envs:
                        has_match = True
                elif "mixed" in req_env:
                    if "mixed" in available_envs or "any" in available_envs:
                        has_match = True

                if has_match:
                    inventory_msg = f"CONFIRMED: We have {filters.environment} options available."
                else:
                    avail_list = [e.title() for e in available_envs if e != 'any']
                    if not avail_list:
                        avail_list = ["Mixed/Shared"]
                    inventory_msg = (
                        f"UNAVAILABLE: User wants '{filters.environment}', but we ONLY have: {', '.join(avail_list)}. "
                        "Apologize and ask if they want to proceed with available options."
                    )

    # Map next_step to human-readable missing field description
    missing_map = {
        "ask_location":    "where they would love to live (preferred location or MRT)",
        "ask_budget":      "their monthly rental budget (maximum in SGD)",
        # Demographics — shared
        "ask_nationality": "their nationality",
        "ask_pass_type":   "the type of pass they hold (EP, SP, PR, Citizen, Student, DP, etc.)",
        "ask_phone":       "their phone number for arranging viewings",
        # Demographics — coliving only
        "ask_gender":      "their gender (Male, Female, or Couple — to match them with suitable flatmates)",
        "ask_profession":  "their occupation / profession",
        "ask_age_group":   "their age group (e.g. 20–30, 30–40, 40+)",
        # Legacy
        "ask_date":        "when they are planning to move in",
    }

    missing_field_desc = missing_map.get(next_step, "more details")
    filters_json = filters.model_dump_json() if filters else "None"

    # Call OpenAI
    llm = OpenAIService().client
    agent_name = state.get("agent_name") or "Assistant"
    company_name = state.get("company_name") or "Company"

    response = await llm.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": GENERATOR_SYSTEM_PROMPT.format(
                agent_name=agent_name,
                company_name=company_name,
                missing_field=missing_field_desc,
                last_user_message=last_human_message,
                current_filters=filters_json,
                validation_error=validation_error,
                inventory_status=inventory_msg,
                property_mode=property_mode,
            )},
            {"role": "user", "content": last_human_message}
        ],
        temperature=0.7
    )

    ai_text = response.choices[0].message.content
    return {"messages": [AIMessage(content=ai_text)]}
