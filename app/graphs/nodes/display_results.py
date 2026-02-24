from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from app.core.state import AgentState
import json


def _extract_first_image(media_str) -> str:
    """Parse a media field (JSON array string, raw URL, or list) and return the first image URL."""
    if not media_str:
        return ""
    try:
        if isinstance(media_str, str) and media_str.startswith('['):
            media_list = json.loads(media_str)
            if media_list and isinstance(media_list, list):
                return media_list[0]
        if isinstance(media_str, str):
            return media_str
        if isinstance(media_str, list) and media_str:
            return media_str[0]
    except Exception:
        pass
    return ""


async def display_results_node(state: AgentState, config: RunnableConfig):
    """
    Formats and displays properties in batches of 3.
    Uses column names appropriate to the target table (residential vs coliving).
    """
    properties = state.get("found_properties") or []
    start_idx  = state.get("shown_count", 0)
    batch_size = 3

    target_table  = state.get("target_table", "")
    is_residential = "residential" in target_table

    current_batch = properties[start_idx: start_idx + batch_size]

    # CASE A: NO RESULTS AT ALL
    if not properties:
        filters = state.get('filters')
        loc = filters.location_query if filters else "your area"
        bud = filters.budget_max if filters else "your budget"
        msg = (
            f"I searched based on your criteria (Location: {loc}, "
            f"Budget: ${bud}), but I couldn't find any exact matches nearby.\n\n"
            "Would you like to try a different location or adjust your budget?"
        )
        return {"messages": [AIMessage(content=msg)], "next_step": "complete"}

    # CASE B: RAN OUT OF RESULTS
    if not current_batch:
        msg = "That's all the properties I have matching your current criteria! Would you like to arrange a viewing for any of the ones above?"
        return {"messages": [AIMessage(content=msg)], "next_step": "complete"}

    # CASE C: DISPLAY BATCH
    msg = ""
    if start_idx == 0:
        msg = f"Great news! I found {len(properties)} properties. Here are the top {len(current_batch)}:\n\n"
    else:
        msg = "Here are a few more options:\n\n"

    for p in current_batch:
        # ── Column name mapping: residential vs coliving ──────────────────
        if is_residential:
            name      = p.get('condo_name') or p.get('property_name') or "Property"
            rent      = p.get('rental_price') or "N/A"
            unit_no   = p.get('unit_number') or ""
            bedrooms  = p.get('bedrooms')
            prop_type = p.get('property_type') or "Unit"
        else:
            name      = p.get('property_name') or "Property"
            rent      = p.get('monthly_rent') or "N/A"
            unit_no   = p.get('room_number') or p.get('unit_number') or ""
            bedrooms  = p.get('num_bedrooms') or p.get('bedrooms')
            prop_type = p.get('room_type') or p.get('property_type') or "Unit"
        # ─────────────────────────────────────────────────────────────────

        bedroom_text = f" | {bedrooms} BR" if bedrooms else ""
        addr = (
            p.get('property_address') or
            p.get('address') or
            p.get('nearest_mrt') or
            "Singapore"
        )

        # Furnishing badge for residential
        furnishing = p.get('furnishing_status') or p.get('furnishing') or ""
        furnishing_text = f" | {furnishing}" if furnishing and is_residential else ""

        # Image URL
        image_url = _extract_first_image(p.get('media') or p.get('images'))

        # Format card
        title = f"🏠 **{name}**"
        if unit_no:
            title += f" (Unit #{unit_no})"
        msg += f"{title}\n"
        msg += f"💰 ${rent}/mo | 🏢 {prop_type}{bedroom_text}{furnishing_text}\n"
        msg += f"📍 {addr}\n"

        if image_url:
            msg += f"🖼 {image_url}\n"

        msg += "──────────────────────────\n"

    # Calculate counters
    new_count = start_idx + len(current_batch)
    remaining = len(properties) - new_count
    
    if remaining > 0:
        msg += f"I have {remaining} more options. Should I show them?"
    else:
        msg += "That's all the matches! Would you like to arrange a viewing for any of these?"
    
    return {
        "messages": [AIMessage(content=msg)],
        "shown_count": new_count,
        "next_step": "waiting_for_user" 
    }
