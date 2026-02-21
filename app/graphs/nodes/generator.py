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
-------------------------------------------------------

### 1. HANDLE VALIDATION + INVENTORY FIRST (MANDATORY)
- If there is a Validation Issue (not "None"), address it politely.
- INVENTORY LOGIC:
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
Once steps 1 & 2 are complete:
- Ask for the **{missing_field}** clearly.
- Be concise (1–2 sentences).

### 4. NO GREETINGS
Do NOT start with "Hi" or "Hello" again.
"""


async def generator_node(state: AgentState, config: RunnableConfig):
    """
    Generates the AI response based on what is missing.
    """
    next_step = state.get("next_step")
    last_human_message = state["messages"][-1].content
    validation_error = state.get("validation_error") or "None"
    
    if next_step == "execute_search":
        return {} 

    # Inventory check logic
    inventory_msg = "Normal"
    filters = state.get("filters")
    
    confirmation_keywords = ["yes", "sure", "okay", "ok", "fine", "proceed", "continue", "go ahead"]
    is_confirmation = any(w in last_human_message.lower() for w in confirmation_keywords)
    
    if filters and getattr(filters, "environment", None) and not is_confirmation:
        db = config.get("configurable", {}).get("db_session")
        agent_id = state["agent_id"]
        target_table = state.get("target_table")
        
        if target_table in ["coliving_property", "rooms_for_rent"]:
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

    # Map next step to missing field description
    missing_map = {
        "ask_location": "where they would love to live (preferred location or MRT)",
        "ask_budget": "their monthly rental budget",
        "ask_date": "when they are planning to move in",
        "ask_gender": "their gender (to match them with suitable flatmates)",
        "ask_nationality": "their nationality"
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
                inventory_status=inventory_msg
            )},
            {"role": "user", "content": last_human_message}
        ],
        temperature=0.7 
    )
    
    ai_text = response.choices[0].message.content
    return {"messages": [AIMessage(content=ai_text)]}
