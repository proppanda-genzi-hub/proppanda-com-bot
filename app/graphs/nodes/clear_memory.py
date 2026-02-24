from langchain_core.runnables import RunnableConfig
from app.core.state import AgentState
from app.schemas.property_search import PropertySearchFilters
import logging

logger = logging.getLogger(__name__)


async def clear_memory_node(state: AgentState, config: RunnableConfig):
    """
    Wipes property search filters when the user switches property type.
    Preserves shared demographics (nationality, gender, profession, age_group, pass_type, phone)
    so users aren't asked again after switching from coliving → residential or vice versa.
    """
    new_target = state.get("target_table")
    logger.info(f"🧹 Clearing Search History. New Target: {new_target}")

    # Preserve demographics from old filters — don't re-ask what we already know
    old_filters = state.get("filters")
    preserved = {}

    if old_filters:
        demographic_fields = [
            "tenant_nationality",
            "tenant_gender",
            "tenant_profession",
            "tenant_age_group",
            "tenant_pass_type",
            "tenant_phone",
        ]
        for field in demographic_fields:
            val = getattr(old_filters, field, None)
            if val:
                preserved[field] = val

    # Start with a clean filter object, then restore demographics
    new_filters = PropertySearchFilters(**preserved) if preserved else None

    logger.info(f"🧹 Preserved demographics after table switch: {list(preserved.keys())}")

    return {
        "filters": new_filters,
        "found_properties": None,
        "shown_count": 0,
        "shown_properties_details": None,
        "inventory_check_status": None,
        "validation_error": None,
        "next_step": "CHECK_CAPABILITY"
    }
