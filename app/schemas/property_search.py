from pydantic import BaseModel, Field
from typing import Optional


class PropertySearchFilters(BaseModel):
    """
    Structured extraction of user preferences for property search.
    """
    
    # --- 1. CORE REQUIREMENTS ---
    location_query: Optional[str] = Field(
        None, 
        description="Target area, MRT station, or region name."
    )
    budget_max: Optional[int] = Field(
        None, 
        description="Maximum monthly rental budget in SGD."
    )
    budget_min: Optional[int] = Field(
        None,
        description="Minimum monthly rental budget in SGD (e.g. 'above 3000')."
    )
    move_in_date: Optional[str] = Field(
        None, 
        description="Target move-in date in ISO format YYYY-MM-DD."
    )

    # --- 2. DEMOGRAPHICS ---
    tenant_gender: Optional[str] = Field(
        None, 
        description="Gender of the tenant (Male, Female, Couple)."
    )
    tenant_nationality: Optional[str] = Field(
        None, 
        description="Nationality of the tenant."
    )
    
    # --- 3. UNIT SPECIFICS ---
    room_type: Optional[str] = Field(
        None, 
        description="Type of room (Master, Common)."
    )
    needs_ensuite: Optional[bool] = Field(
        None, 
        description="True if user needs an attached bathroom."
    )

    # --- 4. AMENITIES & POLICIES ---
    needs_cooking: Optional[bool] = Field(
        None, 
        description="True if user needs to cook."
    )
    has_pets: Optional[bool] = Field(
        None, 
        description="True if user has pets."
    )
    needs_gym: Optional[bool] = Field(
        None, 
        description="True if user asks for gym access."
    )
    needs_pool: Optional[bool] = Field(
        None, 
        description="True if user asks for swimming pool."
    )
    needs_visitor_allowance: Optional[bool] = Field(
        None, 
        description="True if user asks about bringing guests."
    )
    needs_wifi: Optional[bool] = Field(
        None,
        description="True if user asks for Wifi."
    )
    environment: Optional[str] = Field(
        None, 
        description="Living environment preference: Female, Male, or Mixed."
    )
