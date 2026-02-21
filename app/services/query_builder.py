from sqlalchemy import text


async def get_available_environments(db, agent_id: str, table_name: str):
    """
    Checks distinct 'environment' values for all properties (common across all agents).
    Note: agent_id parameter kept for backward compatibility but not used in query.
    """
    allowed_tables = ["coliving_property", "rooms_for_rent"]
    if table_name not in allowed_tables:
        return set()

    try:
        # Query ALL properties, not filtered by agent_id (common property pool)
        query = text(f"SELECT DISTINCT environment FROM {table_name}")
        result = await db.execute(query)
        
        envs = set()
        for row in result.fetchall():
            val = row[0]
            if val:
                envs.add(val.lower())
            else:
                envs.add("mixed")
                
        return envs
    except Exception:
        return set()


def build_property_query(
    filters: dict, 
    agent_id: str, 
    lat: float = None, 
    lng: float = None, 
    text_search_term: str = None
):
    """
    Build a SQL query for property search based on filters.
    """
    # Query ALL properties (common pool - NOT filtered by agent_id)
    # agent_id is kept in params for backward compatibility but not used in WHERE clause
    sql_parts = ["""
        SELECT p.*,
            CASE 
                WHEN CAST(:lat AS numeric) IS NOT NULL AND CAST(:lng AS numeric) IS NOT NULL THEN 
                    ST_Distance(g.location, ST_SetSRID(ST_MakePoint(CAST(:lng AS numeric), CAST(:lat AS numeric)), 4326)::geography)
                ELSE 0 
            END as dist_meters
        FROM coliving_property p
        LEFT JOIN property_geolocations g ON p.property_id = g.property_id
        WHERE p.listing_status = 'active'
        AND p.current_listing = 'Available to rent'
    """]
    
    params = {
        "agent_id": agent_id,  # Kept for compatibility, not used in query
        "lng": lng,
        "lat": lat,
        "text_search": f"%{text_search_term}%" if text_search_term else None
    }

    # Location filter
    if lat and lng:
        sql_parts.append("AND ST_DWithin(g.location, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, 3000)")
    elif text_search_term:
        sql_parts.append("""
            AND (
                p.property_name ILIKE :text_search 
                OR p.property_address ILIKE :text_search 
                OR p.nearest_mrt ILIKE :text_search 
                OR p.district ILIKE :text_search
            )
        """)

    # Budget filter
    if filters.get("budget_max"):
        sql_parts.append("AND p.monthly_rent <= :budget_max")
        params["budget_max"] = filters["budget_max"]
        
    if filters.get("budget_min"):
        sql_parts.append("AND p.monthly_rent >= :budget_min")
        params["budget_min"] = filters["budget_min"]

    # Gender & Environment filter
    gender = filters.get("tenant_gender")
    env = filters.get("environment")

    if env:
        term = env.lower()
        if "female" in term or "ladies" in term:
            sql_parts.append("AND p.environment ILIKE 'female'")
        elif "male" in term or "men" in term:
            sql_parts.append("AND p.environment ILIKE 'male'")
        elif "mixed" in term:
            sql_parts.append("AND p.environment ILIKE 'mixed'")

    if gender:
        term = gender.lower()
        if term == 'male':
            sql_parts.append("AND (p.gender_preference ILIKE 'male' OR p.gender_preference ILIKE 'any' OR p.gender_preference ILIKE 'mixed' OR p.gender_preference IS NULL)")
            sql_parts.append("AND (p.environment NOT ILIKE 'female' OR p.environment IS NULL)")
        elif term == 'female':
            sql_parts.append("AND (p.gender_preference ILIKE 'female' OR p.gender_preference ILIKE 'any' OR p.gender_preference ILIKE 'mixed' OR p.gender_preference IS NULL)")
            sql_parts.append("AND (p.environment NOT ILIKE 'male' OR p.environment IS NULL)")
        elif term == 'couple':
            sql_parts.append("AND (p.gender_preference ILIKE 'any' OR p.gender_preference ILIKE 'couple' OR p.gender_preference ILIKE 'mixed' OR p.gender_preference IS NULL)")
            sql_parts.append("AND (p.environment NOT ILIKE 'male' AND p.environment NOT ILIKE 'female')")
    
    # Nationality filter
    nationality = filters.get("tenant_nationality")
    if nationality:
        sql_parts.append("""
            AND (
                p.nationality_preferences ILIKE :nationality_pattern
                OR p.nationality_preferences ILIKE 'any'
                OR p.nationality_preferences ILIKE 'all'
                OR p.nationality_preferences IS NULL
            )
        """)
        params["nationality_pattern"] = f"%{nationality}%"

    # Room type filter
    if filters.get("room_type") == "Common" or filters.get("needs_ensuite") is False:
        sql_parts.append("AND p.room_type ILIKE '%without attached%'")
    elif filters.get("room_type") == "Master" or filters.get("needs_ensuite") is True:
        sql_parts.append("AND p.room_type ILIKE '%with attached%'")

    # Amenities filters
    if filters.get("needs_cooking"):
        sql_parts.append("AND (p.cooking_allowed = true OR p.gas_stove = true)")
    if filters.get("needs_gym"):
        sql_parts.append("AND p.gym = true")
    if filters.get("needs_pool"):
        sql_parts.append("AND p.swimming_pool = true")
    if filters.get("needs_wifi"):
        sql_parts.append("AND (p.wifi ILIKE 'true' OR p.wifi ILIKE 'available' OR p.wifi ILIKE 'free')")

    # Policy filters
    if filters.get("has_pets"):
        sql_parts.append("AND ((p.pet_policy NOT ILIKE '%not allowed%' AND p.pet_policy NOT ILIKE '%no pets%') OR p.pet_policy IS NULL)")
    if filters.get("needs_visitor_allowance"):
        sql_parts.append("AND (p.visitor_policy NOT ILIKE '%not allowed%' OR p.visitor_policy IS NULL)")

    # Availability filter
    if filters.get("move_in_date"):
        sql_parts.append("AND (p.available_from <= :move_in_date OR p.available_from IS NULL)")
        params["move_in_date"] = filters["move_in_date"]

    # Sort & Limit
    if lat and lng:
        sql_parts.append("ORDER BY dist_meters ASC LIMIT 10")
    else:
        sql_parts.append("ORDER BY p.monthly_rent ASC LIMIT 10")
    
    return text("\n".join(sql_parts)), params
