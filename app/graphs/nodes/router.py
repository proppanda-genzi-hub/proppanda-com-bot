from app.core.state import AgentState
from app.services.openai_service import OpenAIService
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
import json
import logging
import re

logger = logging.getLogger(__name__)

ROUTER_PROMPT = """
You are an Intelligent Intent Classifier for a Real Estate Bot.

### CONVERSATION HISTORY
{history}

### YOUR GOAL
Classify the user's latest message into one of the following intents.

### INTENTS

1. **"PROPERTY_SEARCH"**
   - User is STARTING a search (e.g., "I want a room", "Show me rentals").
   - User is CONTINUING a search (e.g., providing Budget, Location, Date, Gender).
   - User is PAGINATING (e.g., "Yes", "Next", "Show more").
   - **CRITICAL:** If user provides a short answer like "2000" or "Male" or "Bedok", assume it is for the search.

2. **"SWITCH_SEARCH"**
   - User explicitly wants to CHANGE property type.

3. **"CLARIFICATION"**
   - User's request is ambiguous regarding SEARCH PARAMETERS.
   - Do NOT use for questions about property details.

4. **"INTELLIGENT_CHAT"**
   - User asks about a SPECIFIC property (e.g., "Tell me more about the first one", "Does the second one allow pets?").
   - User asks about viewing, booking, scheduling a visit — these are property follow-up questions.
   - User asks general questions unrelated to search.
   - User says greeting or small talk.
   - **Everything else goes here.**

### OUTPUT JSON FORMAT
{{
  "intent": "PROPERTY_SEARCH" | "SWITCH_SEARCH" | "CLARIFICATION" | "INTELLIGENT_CHAT",
  "target_table": "table_name" (Required if intent is PROPERTY_SEARCH or SWITCH_SEARCH),
  "clarification_question": "Question" (Required if intent is CLARIFICATION)
}}

### AVAILABLE TABLES AND THEIR TRIGGER KEYWORDS

- **coliving_property** — co-living, coliving, shared room, flatmates, co-live
- **coliving_rooms** — room for rent, room to rent, looking for a room, single room, shared room, master room, common room, landlord room, HDB room, room in flat, need a room
- **residential_properties_for_rent** — whole unit, entire flat, entire apartment, 3 bedroom, 2BHK, 3BHK, studio, HDB rent, condo rent, family unit, whole house, full unit, private condo, apartment for rent
- **residential_properties_for_resale** — buy HDB, buy condo, purchase property, resale flat
- **residential_properties_for_sale_by_developers** — new launch, developer sale, BTO alternative, new condo
- **commercial_properties_for_rent** — office space, shop for rent, commercial unit, retail space
- **commercial_properties_for_resale** — buy office, commercial property for sale
- **commercial_properties_for_sale_by_developers** — new commercial, commercial new launch

When a user says "room", "room for rent", or "looking for a room" → always set target_table to "coliving_rooms".
When a user's message matches keywords for **residential_properties_for_rent**, always set target_table to "residential_properties_for_rent".
"""


async def router_node(state: AgentState, config: RunnableConfig):
    """
    Main router node that classifies user intent.
    Routes through load_user_data when email has not been collected yet.
    """
    print("🔵🔵🔵 ROUTER NODE ENTERED 🔵🔵🔵")
    logger.info(f"🔵 ROUTER NODE STARTED - Processing message")
    messages = state["messages"]
    last_message_content = messages[-1].content.strip()
    print(f"📨 Router processing: {last_message_content}")
    logger.info(f"📨 User message: {last_message_content[:100]}")
    msg_lower = last_message_content.lower()
    llm = OpenAIService().client

    # --- 0. ACTIVE FLOW BYPASSES ---
    active_flow = state.get("active_flow")

    # If we are mid-email-collection, always route back to load_user_data
    if active_flow == "LEAD_COLLECTION":
        result = {"next_step": "LOAD_USER_DATA"}
        print(f"🎯 Router returning (lead collection active): {result}")
        return result

    # If we are collecting post-search demographics, send reply directly to extractor
    if active_flow == "COLLECT_LEAD":
        result = {"next_step": "PROPERTY_SEARCH"}
        print(f"🎯 Router returning (collecting lead demographics): {result}")
        return result

    # --- 1. CONTEXT & KEYWORD OVERRIDES ---

    # A. Pagination
    target_table = state.get("target_table")
    pagination_keywords = ["yes", "yeah", "yep", "sure", "show more", "next", "continue"]

    last_bot_msg = messages[-2].content.lower() if len(messages) > 1 else ""
    is_clarification_question = "?" in last_bot_msg and len(last_bot_msg) < 200

    has_budget_update = any(keyword in msg_lower for keyword in ["above", "under", "below", "between", "min", "max", "$", "budget"])
    has_location_update = any(keyword in msg_lower for keyword in ["near", "mrt", "station", "area", "location", "district"])

    if target_table and any(w in msg_lower for w in pagination_keywords) and not is_clarification_question and not has_budget_update and not has_location_update:
        result = {"next_step": "PROPERTY_SEARCH"}
        print(f"🎯 Router returning (pagination): {result}")
        return result

    # B. Specific Room Reference
    room_pattern = r"\b(room\s+\d+|r\d+)\b"
    if re.search(room_pattern, msg_lower):
        logger.info("✅ Specific Room ID detected. Routing to INTELLIGENT_CHAT.")
        result = {"next_step": "INTELLIGENT_CHAT"}
        print(f"🎯 Router returning (room reference): {result}")
        return result

    # --- 2. BUILD HISTORY ---
    recent_messages = messages[-7:]
    history_str = ""
    for msg in recent_messages:
        role = "User" if isinstance(msg, HumanMessage) else "Bot"
        history_str += f"{role}: {msg.content}\n"

    # --- 3. AI CLASSIFICATION ---
    try:
        response = await llm.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": ROUTER_PROMPT.format(history=history_str)},
                {"role": "user", "content": f"Classify: {last_message_content}"}
            ],
            response_format={"type": "json_object"},
            temperature=0
        )

        data = json.loads(response.choices[0].message.content)
        intent = data.get("intent", "INTELLIGENT_CHAT")

        logger.info(f"🛤️ Router classified: {intent}")

        # HANDLE INTENTS
        if intent == "PROPERTY_SEARCH":
            new_table = data.get("target_table")

            if not new_table and target_table:
                # Continuing existing search — check if email is collected
                user_email = state.get("user_email")
                if not user_email:
                    result = {"next_step": "LOAD_USER_DATA", "active_flow": "LEAD_COLLECTION"}
                    print(f"🎯 Router returning (need email, continuing search): {result}")
                    return result
                result = {"next_step": "PROPERTY_SEARCH"}
                print(f"🎯 Router returning (continue search): {result}")
                return result

            if new_table and target_table and new_table != target_table:
                explicit_switch_keywords = ["buy", "rent", "commercial", "residential", "office", "shop", "store"]
                if not any(k in msg_lower for k in explicit_switch_keywords):
                    user_email = state.get("user_email")
                    if not user_email:
                        result = {
                            "next_step": "LOAD_USER_DATA",
                            "active_flow": "LEAD_COLLECTION",
                            "target_table": new_table
                        }
                        print(f"🎯 Router returning (need email, same search): {result}")
                        return result
                    result = {"next_step": "PROPERTY_SEARCH"}
                    print(f"🎯 Router returning (same search): {result}")
                    return result

                result = {"next_step": "RESET_MEMORY", "target_table": new_table}
                print(f"🎯 Router returning (reset): {result}")
                return result

            # New search with a table — route through email collection if needed
            resolved_table = new_table or target_table
            user_email = state.get("user_email")
            if not user_email:
                result = {
                    "next_step": "LOAD_USER_DATA",
                    "active_flow": "LEAD_COLLECTION",
                    "target_table": resolved_table
                }
                print(f"🎯 Router returning (need email first): {result}")
                return result

            result = {"next_step": "CHECK_CAPABILITY", "target_table": resolved_table}
            print(f"🎯 Router returning (check capability): {result}")
            return result

        elif intent == "SWITCH_SEARCH":
            result = {"next_step": "RESET_MEMORY", "target_table": data.get("target_table")}
            print(f"🎯 Router returning (switch): {result}")
            return result

        elif intent == "CLARIFICATION":
            result = {
                "next_step": "ASK_CLARIFICATION",
                "clarification_question": data.get("clarification_question")
            }
            print(f"🎯 Router returning (clarification): {result}")
            return result

        else:
            result = {"next_step": "INTELLIGENT_CHAT"}
            print(f"🎯 Router returning (intelligent chat): {result}")
            return result

    except Exception as e:
        logger.error(f"Router Error: {e}")
        result = {"next_step": "INTELLIGENT_CHAT"}
        print(f"🎯 Router returning (error fallback): {result}")
        return result
