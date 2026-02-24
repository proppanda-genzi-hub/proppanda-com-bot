from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from app.core.state import AgentState
from app.schemas.property_search import PropertySearchFilters
from app.db.repositories.leads_repository import LeadsRepository
import re
import logging

logger = logging.getLogger(__name__)

# Regex to find an email address in free text
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')


def _is_residential(target_table: str) -> bool:
    return "residential" in (target_table or "")


def _user_is_complete(lead_data: dict, target_table: str) -> bool:
    """
    Type-aware completeness check.
    Residential: 'existing' if nationality is present.
    Coliving/Rooms: 'existing' if gender + nationality + profession + phone + pass_type + age_group all present.
    """
    if _is_residential(target_table):
        return bool(lead_data.get("nationality"))
    else:
        required = ["gender", "nationality", "profession", "phone", "pass_type", "age_group"]
        return all(lead_data.get(f) for f in required)


async def load_user_data_node(state: AgentState, config: RunnableConfig):
    """
    Step 1: Collect user's email if not yet known.
    Step 2: Look up email in prop_panda_com_leads.
    Step 3: Load available demographics into filters based on property type.
    Step 4: Route to capability_check if email is collected, or ask for email and stop.
    """
    print("📧📧📧 LOAD_USER_DATA NODE ENTERED 📧📧📧")

    messages = state["messages"]
    last_message = messages[-1].content.strip()
    target_table = state.get("target_table", "")
    db = config.get("configurable", {}).get("db_session")
    agent_id = state.get("agent_id")
    session_id = state.get("user_mobile")
    agent_name = state.get("agent_name") or "I"

    # --- STEP 1: Try to extract email from the latest user message ---
    email_match = EMAIL_PATTERN.search(last_message)
    existing_email = state.get("user_email")

    if not email_match and not existing_email:
        # No email found anywhere — ask for it
        logger.info("📧 No email found — asking user for email")
        return {
            "active_flow": "LEAD_COLLECTION",
            "next_step": "WAIT_EMAIL",
            "messages": [AIMessage(
                content=(
                    "Before I start searching for you, could you please share your "
                    "email address? This helps me save your preferences and make future "
                    "searches faster for you! 😊"
                )
            )]
        }

    # Use newly found email or fall back to one already in state
    email = email_match.group(0).lower().strip() if email_match else existing_email

    # --- STEP 2: Query the leads DB ---
    lead_data = {}
    if db:
        try:
            repo = LeadsRepository(db)
            existing = await repo.get_by_email(email)

            if existing:
                lead_data = existing
                logger.info(f"📧 Found existing lead for {email}")
            else:
                logger.info(f"📧 New lead — creating record for {email}")

            # Upsert with current session context
            await repo.upsert_lead({
                "email": email,
                "agent_id": agent_id,
                "session_id": session_id,
                "last_target_table": target_table or existing.get("last_target_table") if existing else target_table,
            })
        except Exception as e:
            logger.error(f"load_user_data DB error (non-critical): {e}")

    # --- STEP 3: Load demographics into filters ---
    current_filters = state.get("filters") or PropertySearchFilters()
    filter_update = {}

    # Always load nationality if available (used in both residential + coliving)
    if lead_data.get("nationality") and not current_filters.tenant_nationality:
        filter_update["tenant_nationality"] = lead_data["nationality"]

    # Load pass_type if available
    if lead_data.get("pass_type") and not current_filters.tenant_pass_type:
        filter_update["tenant_pass_type"] = lead_data["pass_type"]

    # Load phone if available
    if lead_data.get("phone") and not current_filters.tenant_phone:
        filter_update["tenant_phone"] = lead_data["phone"]

    if not _is_residential(target_table):
        # Coliving-specific demographics
        if lead_data.get("gender") and not current_filters.tenant_gender:
            filter_update["tenant_gender"] = lead_data["gender"]
        if lead_data.get("profession") and not current_filters.tenant_profession:
            filter_update["tenant_profession"] = lead_data["profession"]
        if lead_data.get("age_group") and not current_filters.tenant_age_group:
            filter_update["tenant_age_group"] = lead_data["age_group"]

    if filter_update:
        current_filters = current_filters.model_copy(update=filter_update)

    logger.info(f"📧 Email collected: {email} | Loaded demographics: {list(filter_update.keys())}")

    return {
        "user_email": email,
        "lead_data": lead_data,
        "active_flow": None,          # Clear LEAD_COLLECTION flow
        "next_step": "CHECK_CAPABILITY",
        "filters": current_filters,
    }
