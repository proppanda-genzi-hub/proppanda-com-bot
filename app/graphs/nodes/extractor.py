from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from app.core.state import AgentState
from app.schemas.property_search import PropertySearchFilters
from app.services.openai_service import OpenAIService
from app.db.repositories.prospect_repository import ProspectRepository
from app.db.repositories.leads_repository import LeadsRepository
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PROMPTS
# ---------------------------------------------------------------------------

COLIVING_EXTRACTOR_PROMPT = """
You are an expert data extractor for a Real Estate Bot (Co-living / Rooms for Rent).
Your job is to update the PropertySearchFilters based on the conversation history.
Output ONLY valid JSON.

### CONTEXT
- Today's Date: {current_date}
- Current Filters: {current_filters}

### INSTRUCTIONS
1. Analyze recent history for updates.
2. Gender: If user says female-only → extract female. If male-only → extract male.
3. Date Parsing: Convert month names to future dates.
4. Update only fields explicitly mentioned.
5. Budget:
   - "under 3000", "max 3000" → budget_max=3000. If new budget_max < current budget_min, set budget_min=None.
   - "above 3000", "min 3000" → budget_min=3000. If new budget_min > current budget_max, set budget_max=None.
   - "between 2000 and 3000" → budget_min=2000, budget_max=3000
   - Convert "2k" → 2000.
6. Flexible Location Detection:
   - "anywhere", "no preference", "flexible", "anything is fine", "any location" → location_query="anywhere"
7. Extract demographics: tenant_gender, tenant_nationality, tenant_phone, tenant_profession, tenant_age_group, tenant_pass_type.
8. Do NOT extract: bedrooms, bathrooms, property_type, furnishing_status (coliving-only mode).
"""

RESIDENTIAL_EXTRACTOR_PROMPT = """
You are an expert data extractor for a Real Estate Bot (Residential Properties for Rent).
Your job is to update the PropertySearchFilters based on the conversation history.
Output ONLY valid JSON.

### CONTEXT
- Today's Date: {current_date}
- Current Filters: {current_filters}

### INSTRUCTIONS
1. Analyze recent history for updates.
2. Date Parsing: Convert month names to future dates.
3. Update only fields explicitly mentioned.
4. Budget:
   - "under 5000", "max 5000" → budget_max=5000. If new budget_max < current budget_min, set budget_min=None.
   - "above 3000", "min 3000" → budget_min=3000. If new budget_min > current budget_max, set budget_max=None.
   - "between 3000 and 5000" → budget_min=3000, budget_max=5000
   - Convert "5k" → 5000.
5. Flexible Location: "anywhere", "no preference", "flexible" → location_query="anywhere"
6. Extract residential-specific fields:
   - bedrooms: number of bedrooms (e.g. "3 bedroom" → 3, "2BHK" → 2, "studio" → 1)
   - bathrooms: number of bathrooms
   - property_type: "HDB" or "Condo" — detect from user message
   - furnishing_status: "Fully Furnished", "Partially Furnished", or "Unfurnished"
   - needs_aircon, needs_washer_dryer, needs_gym, needs_pool, has_pets
7. Extract demographics: tenant_nationality, tenant_pass_type, tenant_phone only.
8. Do NOT extract: tenant_gender, environment, room_type, needs_ensuite, needs_cooking,
   needs_visitor_allowance, needs_wifi, tenant_profession, tenant_age_group (residential mode).
9. Minimum lease for residential is 12 months. If user mentions lease duration,
   validate it is >= 12 months. If less, do not set min_lease_months.
"""

DEMOGRAPHICS_EXTRACTOR_PROMPT = """
You are a data extractor for a Real Estate Bot.
The user just replied with their personal details. Extract ONLY the demographic fields below.
Output ONLY valid JSON matching the PropertySearchFilters schema.

### CONTEXT
- Current Filters: {current_filters}
- Property Type: {property_type}
- Min Lease Months: {min_lease} months

### FIELDS TO EXTRACT (only what the user explicitly mentioned)
- tenant_name: their full name (e.g. "John Smith")
- tenant_nationality: nationality string (e.g. "Indian", "Singaporean", "British")
- tenant_pass_type: EP / SP / PR / Citizen / DP / Student Pass / Work Permit
- tenant_phone: phone number as a string
- tenant_lease_months: intended lease duration as an integer number of months
  (e.g. "1 year" → 12, "6 months" → 6, "2 years" → 24)

### COLIVING-ONLY FIELDS (only if property_type is coliving)
- tenant_gender: Male / Female / Couple
- tenant_profession: their occupation / job title
- tenant_age_group: age range string like "20-30", "30-40", "40-50"

Do NOT extract anything else (no location, budget, bedrooms, etc.).
Return only the fields that were clearly stated.
"""


def _is_residential(target_table: str) -> bool:
    return "residential" in (target_table or "")


# ---------------------------------------------------------------------------
# EXTRACTOR NODE
# ---------------------------------------------------------------------------

async def extractor_node(state: AgentState, config: RunnableConfig):
    """
    Extract structured data from conversation.
    Handles: property search (coliving vs residential) and appointment booking.
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
        target_table = state.get("target_table", "")
        is_residential = _is_residential(target_table)

        active_flow = state.get("active_flow")

        # ---------------------------------------------------------------
        # MODE B — COLLECT_LEAD
        # User just provided their personal details in response to our ask.
        # Extract demographics, save to lead with property agent_id, then clear flow.
        # ---------------------------------------------------------------
        if active_flow == "COLLECT_LEAD":
            current_filters = state.get("filters") or PropertySearchFilters()
            property_type = "residential" if is_residential else "coliving"

            system_prompt = DEMOGRAPHICS_EXTRACTOR_PROMPT.format(
                current_filters=current_filters.model_dump_json(),
                property_type=property_type,
                min_lease=12 if is_residential else 3,
            )

            completion = await llm.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"User message:\n{history_text}"}
                ],
                response_format={"type": "json_object"},
                functions=[{
                    "name": "update_demographics",
                    "description": "Updates only the demographic fields",
                    "parameters": PropertySearchFilters.model_json_schema()
                }],
                function_call={"name": "update_demographics"}
            )

            function_args = completion.choices[0].message.function_call.arguments
            extracted = PropertySearchFilters.model_validate_json(function_args)

            # Lease duration validation
            min_lease = 12 if is_residential else 3
            if extracted.tenant_lease_months and extracted.tenant_lease_months < min_lease:
                logger.warning(
                    f"Lease {extracted.tenant_lease_months}m below minimum {min_lease}m — clearing"
                )
                extracted = extracted.model_copy(update={"tenant_lease_months": None})

            # Merge demographics into existing filters
            demo_updates = {}
            if extracted.tenant_name:
                demo_updates["tenant_name"] = extracted.tenant_name
            if extracted.tenant_nationality:
                demo_updates["tenant_nationality"] = extracted.tenant_nationality
            if extracted.tenant_pass_type:
                demo_updates["tenant_pass_type"] = extracted.tenant_pass_type
            if extracted.tenant_phone:
                demo_updates["tenant_phone"] = extracted.tenant_phone
            if extracted.tenant_lease_months:
                demo_updates["tenant_lease_months"] = extracted.tenant_lease_months
            if not is_residential:
                if extracted.tenant_gender:
                    demo_updates["tenant_gender"] = extracted.tenant_gender
                if extracted.tenant_profession:
                    demo_updates["tenant_profession"] = extracted.tenant_profession
                if extracted.tenant_age_group:
                    demo_updates["tenant_age_group"] = extracted.tenant_age_group

            new_filters = current_filters.model_copy(update=demo_updates)

            # Save demographics to lead record
            db_session = config.get("configurable", {}).get("db_session")
            user_email = state.get("user_email")

            if db_session and user_email and demo_updates:
                try:
                    leads_repo = LeadsRepository(db_session)
                    lead_updates = {}

                    if extracted.tenant_name:
                        lead_updates["name"] = extracted.tenant_name
                    if extracted.tenant_nationality:
                        lead_updates["nationality"] = extracted.tenant_nationality
                    if extracted.tenant_pass_type:
                        lead_updates["pass_type"] = extracted.tenant_pass_type
                    if extracted.tenant_phone:
                        lead_updates["phone"] = extracted.tenant_phone
                    if not is_residential:
                        if extracted.tenant_gender:
                            lead_updates["gender"] = extracted.tenant_gender
                        if extracted.tenant_profession:
                            lead_updates["profession"] = extracted.tenant_profession
                        if extracted.tenant_age_group:
                            lead_updates["age_group"] = extracted.tenant_age_group

                    if lead_updates:
                        await leads_repo.update_fields(user_email, lead_updates)
                        logger.info(f"✅ Lead demographics saved for {user_email}")
                except Exception as e:
                    logger.warning(f"Failed to save lead demographics (non-critical): {e}")

            # Update user_name in state if we extracted a name
            state_updates: dict = {
                "filters": new_filters,
                "active_flow": None,
            }
            if extracted.tenant_name:
                state_updates["user_name"] = extracted.tenant_name

            return state_updates

        # ---------------------------------------------------------------
        # MODE B — PROPERTY SEARCH EXTRACTION
        # ---------------------------------------------------------------
        today_str = datetime.now().strftime("%Y-%m-%d")
        current_filters = state.get("filters") or PropertySearchFilters()

        # Choose prompt based on property type
        system_prompt = (
            RESIDENTIAL_EXTRACTOR_PROMPT if is_residential else COLIVING_EXTRACTOR_PROMPT
        ).format(
            current_date=today_str,
            current_filters=current_filters.model_dump_json()
        )

        completion = await llm.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Recent Conversation History:\n{history_text}"}
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

        # If residential, strip coliving-only fields from the update to avoid overwriting
        if is_residential:
            updated_data = updated_data.model_copy(update={
                "tenant_gender": None,
                "environment": None,
                "room_type": None,
                "needs_ensuite": None,
                "needs_cooking": None,
                "needs_visitor_allowance": None,
                "needs_wifi": None,
                "tenant_profession": None,
                "tenant_age_group": None,
            })

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

        # Minimum lease validation for residential (filter extraction step)
        if is_residential and new_filters.min_lease_months and new_filters.min_lease_months < 12:
            validation_msg = (
                "The minimum lease for residential properties is 12 months. "
                "Please confirm you're looking for at least a 12-month lease."
            )
            new_filters.min_lease_months = None

        # Inventory check logic (coliving only)
        inv_status = state.get("inventory_check_status")
        if not is_residential:
            last_msg = state["messages"][-1].content.lower()
            confirmation_keywords = ["yes", "sure", "okay", "ok", "fine", "proceed"]
            is_confirmation = any(k in last_msg for k in confirmation_keywords)

            old_env = getattr(current_filters, "environment", None)
            new_env = new_filters.environment

            if new_env and new_env != old_env:
                inv_status = "PENDING"
            elif new_env and inv_status is None:
                inv_status = "PENDING"
            if is_confirmation:
                inv_status = "DONE"
            if not new_env or new_env.lower() == "mixed":
                inv_status = "DONE"
        else:
            inv_status = "DONE"  # No inventory check for residential

        # Save demographics to lead record
        db_session = config.get("configurable", {}).get("db_session")
        user_email = state.get("user_email")

        if db_session and user_email:
            try:
                leads_repo = LeadsRepository(db_session)
                lead_updates = {}

                if new_filters.tenant_nationality:
                    lead_updates["nationality"] = new_filters.tenant_nationality
                if new_filters.tenant_pass_type:
                    lead_updates["pass_type"] = new_filters.tenant_pass_type
                if new_filters.tenant_phone:
                    lead_updates["phone"] = new_filters.tenant_phone

                if not is_residential:
                    if new_filters.tenant_gender:
                        lead_updates["gender"] = new_filters.tenant_gender
                    if new_filters.tenant_profession:
                        lead_updates["profession"] = new_filters.tenant_profession
                    if new_filters.tenant_age_group:
                        lead_updates["age_group"] = new_filters.tenant_age_group

                if lead_updates:
                    await leads_repo.update_fields(user_email, lead_updates)
            except Exception as e:
                logger.warning(f"Failed to update lead demographics (non-critical): {e}")

        # Legacy CRM upsert (prospect_info) — kept for backward compatibility
        if db_session:
            try:
                repo = ProspectRepository(db_session)
                prospect_data = {
                    "user_id": state["user_mobile"],
                    "agent_id": state["agent_id"],
                    "name": state.get("user_name"),
                    "email": user_email,
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
