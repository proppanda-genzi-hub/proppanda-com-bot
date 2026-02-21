from langchain_core.runnables import RunnableConfig
from app.core.state import AgentState
from app.tools.property_search import PropertySearchTool
from app.services.query_builder import build_property_query
from sqlalchemy import text
import logging
import os

logger = logging.getLogger(__name__)


async def search_node(state: AgentState, config: RunnableConfig):
    """
    Hybrid Search Strategy:
    1. Check if location is flexible ("anywhere", "no preference")
    2. Try DB Text Search.
    3. If 0 results, Geocode -> Radius Search.
    4. If still no results, search all properties.
    """
    db = config.get("configurable", {}).get("db_session")
    agent_id = state["agent_id"]
    filters = state["filters"]
    filter_dict = filters.model_dump() if filters else {}
    
    tool = PropertySearchTool(db, location_iq_key=os.getenv("LOCATION_IQ_KEY"))
    
    properties = []
    location_str = filters.location_query if filters else None
    
    # Define flexible location keywords
    flexible_keywords = ["anywhere", "no preference", "flexible", "any", "doesnt matter", "doesn't matter", "no prefernce", "anything is fine", "any location"]
    
    is_flexible_location = False
    if location_str:
        location_lower = location_str.lower()
        is_flexible_location = any(keyword in location_lower for keyword in flexible_keywords)
    
    # STRATEGY 0: FLEXIBLE LOCATION - Search ALL properties
    if is_flexible_location or not location_str:
        logger.info(f"🌍 Flexible location detected: '{location_str}' - Searching ALL properties")
        query_text, params = build_property_query(
            filters=filter_dict, 
            agent_id=agent_id, 
            lat=None, 
            lng=None,
            text_search_term=None
        )
        
        final_query_str = str(query_text).replace("LIMIT 5", "LIMIT 10")
        result = await db.execute(text(final_query_str), params)
        properties = [dict(row) for row in result.mappings().all()]
        
        if properties:
            logger.info(f"✅ Found {len(properties)} properties (all locations)")
            # Do not return early, let it flow to deduplication logic

    
    # STRATEGY 1: DIRECT DB TEXT SEARCH (for specific locations)
    if location_str and not is_flexible_location:
        clean_loc = location_str.lower()
        for word in ["near", "around", "at", "in", "area", "location"]:
            clean_loc = clean_loc.replace(word, "")
            
        clean_loc = clean_loc.replace("mrt", "").replace("station", "")
        clean_loc = clean_loc.strip()
        
        logger.info(f"🔍 Text Search: Original='{location_str}' -> Clean='{clean_loc}'")
        
        if len(clean_loc) > 2:
            query_text, params = build_property_query(
                filters=filter_dict, 
                agent_id=agent_id, 
                lat=None, 
                lng=None, 
                text_search_term=clean_loc
            )
            
            final_query_str = str(query_text).replace("LIMIT 5", "LIMIT 10")
            
            result = await db.execute(text(final_query_str), params)
            properties = [dict(row) for row in result.mappings().all()]
            
            if properties:
                logger.info(f"✅ Text Search found {len(properties)} matches.")

    # STRATEGY 2: FALLBACK TO GEOCODING (only for specific locations)
    if not properties and location_str and not is_flexible_location:
        logger.info(f"⚠️ Text Search failed. Trying Geocoding for: '{location_str}'")
        
        coords = await tool.get_coordinates(location_str)
        if coords:
            lat, lng = coords
            
            query_text, params = build_property_query(
                filters=filter_dict, 
                agent_id=agent_id, 
                lat=lat, 
                lng=lng
            )
            
            final_query_str = str(query_text).replace("LIMIT 5", "LIMIT 10")
            result = await db.execute(text(final_query_str), params)
            properties = [dict(row) for row in result.mappings().all()]
        else:
            logger.warning("❌ Geocoding failed - falling back to all properties")
            # FALLBACK: Search all properties if geocoding fails
            # FALLBACK: Search all properties if geocoding fails
            query_text, params = build_property_query(
                filters=filter_dict, 
                agent_id=agent_id, 
                lat=None, 
                lng=None,
                text_search_term=None
            )
            final_query_str = str(query_text).replace("LIMIT 5", "LIMIT 10")
            result = await db.execute(text(final_query_str), params)
            properties = [dict(row) for row in result.mappings().all()]

    # Deduplicate properties based on property_id
    seen_ids = set()
    unique_properties = []
    for p in properties:
        p_id = p.get('property_id')
        if p_id and p_id not in seen_ids:
            seen_ids.add(p_id)
            unique_properties.append(p)
        elif not p_id:
            # If no ID, keep it (unlikely but safe)
            unique_properties.append(p)

    return {
        "found_properties": unique_properties, 
        "shown_count": 0, 
        "next_step": "display_results" 
    }
