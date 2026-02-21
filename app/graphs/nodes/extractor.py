from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from app.core.state import AgentState
from app.schemas.property_search import PropertySearchFilters
from app.schemas.appointment import AppointmentInfo
from app.services.openai_service import OpenAIService
from app.db.repositories.prospect_repository import ProspectRepository
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

SEARCH_EXTRACTOR_PROMPT = """
You are an expert data extractor for a Real Estate Bot.
Your job is to update the PropertySearchFilters based on the conversation history.
You must output your response in valid JSON format.

### CONTEXT
- Today's Date: {current_date}
- Current Filters: {current_filters}

### INSTRUCTIONS
1. Analyze recent history for updates.
2. Gender: If user says female-only → extract female. If male-only → extract male.
3. Date Parsing: Convert month names to future dates.
4. Update only fields explicitly mentioned.
5. Budget: 
   - "under 3000", "max 3000" → budget_max=3000. **Important**: If new budget_max < current budget_min, set budget_min=None.
   - "above 3000", "min 3000" → budget_min=3000. **Important**: If new budget_min > current budget_max, set budget_max=None.
   - "between 2000 and 3000" → budget_min=2000, budget_max=3000
   - Convert "2k" to 2000.
6. **Flexible Location Detection**:
   - If user says "anywhere", "no preference", "flexible", "anything is fine", "any location", "no location", "doesnt matter" → set location_query to "anywhere"
   - If user says "no specific location" or similar → set location_query to "anywhere"
   - This is VERY IMPORTANT - when detecting flexible location, ALWAYS set location_query to "anywhere"
"""

APPOINTMENT_EXTRACTOR_PROMPT = """
You are an expert appointment extractor.
Output valid JSON only.

### CONTEXT
- Current Data: {current_data}

### INSTRUCTIONS
Extract the following fields:
- email: User's email address
- pass_type: Type of pass (EP, SP, Student, Citizen, etc.)
- lease_months: Lease duration in months
- viewing_type: "In-Person" or "Virtual"
- time_preference: "Morning", "After Lunch", or "After Work"
- selected_slot: If user selects a specific time slot

Only include fields that are explicitly mentioned by the user.
"""


async def extractor_node(state: AgentState, config: RunnableConfig):
    """
    Extract structured data from conversation.
    """
    try:
        messages = state["messages"]
        recent_messages = messages[-7:] if len(messages) >= 7 else messages

        history_text = ""
        for m in recent_messages:
            role = "User" if isinstance(m, HumanMessage) else "AI"
            history_text += f"{role}: {m.content}\n"

        llm = OpenAIService().client
        validation_msg = None

        active_flow = state.get("active_flow")

        # MODE A — APPOINTMENT BOOKING
        if active_flow == "APPOINTMENT":
            current_appt = state.get("appointment_state") or {}

            completion = await llm.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system",
                     "content": APPOINTMENT_EXTRACTOR_PROMPT.format(
                         current_data=json.dumps(current_appt, default=str)
                     )},
                    {"role": "user", "content": f"History:\n{history_text}"}
                ],
                response_format={"type": "json_object"},
                functions=[{
                    "name": "extract_appt",
                    "parameters": AppointmentInfo.model_json_schema()
                }],
                function_call={"name": "extract_appt"}
            )

            args = completion.choices[0].message.function_call.arguments
            new_data = json.loads(args)

            updated_appt = {**current_appt,
                           **{k: v for k, v in new_data.items() if v}}

            # Validation → lease must be >= 3 months
            if updated_appt.get("lease_months") and updated_appt["lease_months"] < 3:
                validation_msg = (
                    "Please note the minimum lease duration is 3 months. "
                    "Could you confirm if that works for you?"
                )
                updated_appt["lease_months"] = None

            return {
                "appointment_state": updated_appt,
                "validation_error": validation_msg
            }

        # MODE B — PROPERTY SEARCH EXTRACTION
        else:
            today_str = datetime.now().strftime("%Y-%m-%d")
            current_filters = state.get("filters") or PropertySearchFilters()

            completion = await llm.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system",
                     "content": SEARCH_EXTRACTOR_PROMPT.format(
                         current_date=today_str,
                         current_filters=current_filters.model_dump_json()
                     )},
                    {"role": "user",
                     "content": f"Recent Conversation History:\n{history_text}"}
                ],
                response_format={"type": "json_object"},
                functions=[{
                    "name": "update_filters",
                    "description": "Updates the property search filters",
                    "parameters": PropertySearchFilters.model_json_schema()
                }],
                function_call={"name": "update_filters"}
            )

            function_args = completion.choices[0].message.function_call.arguments
            updated_data = PropertySearchFilters.model_validate_json(function_args)

            new_filters = current_filters.model_copy(
                update=updated_data.model_dump(exclude_unset=True)
            )

            # Date validation
            if new_filters.move_in_date:
                try:
                    target_date = datetime.strptime(new_filters.move_in_date, "%Y-%m-%d").date()
                    today = datetime.now().date()

                    if target_date < today:
                        logger.warning("Move-in date is in the past.")
                        new_filters.move_in_date = None
                        validation_msg = (
                            f"The date {target_date.strftime('%d %b %Y')} has passed. "
                            f"Please provide a future move-in date."
                        )

                except ValueError:
                    pass

            # Inventory check logic
            last_msg = state["messages"][-1].content.lower()
            confirmation_keywords = ["yes", "sure", "okay", "ok", "fine", "proceed"]
            is_confirmation = any(k in last_msg for k in confirmation_keywords)

            old_env = getattr(current_filters, "environment", None)
            new_env = new_filters.environment

            inv_status = state.get("inventory_check_status")

            if new_env and new_env != old_env:
                logger.info(f"🔄 Environment changed from {old_env} to {new_env}.")
                inv_status = "PENDING"
            elif new_env and inv_status is None:
                inv_status = "PENDING"

            if is_confirmation:
                inv_status = "DONE"

            if not new_env or new_env.lower() == "mixed":
                inv_status = "DONE"

            # Save to DB (CRM)
            # Save to DB (CRM) - wrap in try/except to not fail the main flow
            db_session = config.get("configurable", {}).get("db_session")
            if db_session:
                try:
                    repo = ProspectRepository(db_session)
                    prospect_data = {
                        "user_id": state["user_mobile"],
                        "agent_id": state["agent_id"],
                        "name": state.get("user_name"),
                        "email": None,
                        "gender": new_filters.tenant_gender,
                        "nationality": new_filters.tenant_nationality,
                        "move_in_date": new_filters.move_in_date,
                        "budget": new_filters.budget_max,
                        "location": new_filters.location_query
                    }
                    await repo.upsert_prospect(prospect_data)
                except Exception as e:
                    logger.warning(f"Failed to upsert prospect (non-critical): {e}")

            return {
                "filters": new_filters,
                "inventory_check_status": inv_status,
                "validation_error": validation_msg
            }

    except Exception as e:
        logger.error(f"Error in extractor node: {e}")
        return {"filters": state.get("filters")}
