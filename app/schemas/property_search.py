from pydantic import BaseModel, Field
from typing import Optional


class PropertySearchFilters(BaseModel):
    """
    Structured extraction of user preferences for property search.
    Covers both coliving/rooms and residential property types.
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

    # --- 2. DEMOGRAPHICS (coliving + residential) ---
    tenant_name: Optional[str] = Field(
        None,
        description="Full name of the tenant."
    )
    tenant_gender: Optional[str] = Field(
        None,
        description="Gender of the tenant (Male, Female, Couple)."
    )
    tenant_nationality: Optional[str] = Field(
        None,
        description="Nationality of the tenant."
    )
    tenant_phone: Optional[str] = Field(
        None,
        description="Phone number of the tenant."
    )
    tenant_profession: Optional[str] = Field(
        None,
        description="Profession or occupation of the tenant."
    )
    tenant_age_group: Optional[str] = Field(
        None,
        description="Age group of the tenant (e.g. '20-30', '30-40')."
    )
    tenant_pass_type: Optional[str] = Field(
        None,
        description="Type of pass held by tenant (EP, SP, Student Pass, PR, Citizen, DP, etc.)."
    )
    tenant_lease_months: Optional[int] = Field(
        None,
        description="Intended lease duration in months (min 12 for residential, min 3 for coliving)."
    )

    # --- 3. COLIVING-SPECIFIC UNIT DETAILS ---
    room_type: Optional[str] = Field(
        None,
        description="Type of room (Master, Common). For coliving only."
    )
    needs_ensuite: Optional[bool] = Field(
        None,
        description="True if user needs an attached bathroom. For coliving only."
    )
    environment: Optional[str] = Field(
        None,
        description="Living environment preference: Female, Male, or Mixed. For coliving only."
    )

    # --- 4. RESIDENTIAL-SPECIFIC UNIT DETAILS ---
    bedrooms: Optional[int] = Field(
        None,
        description="Number of bedrooms required. For residential only."
    )
    bathrooms: Optional[int] = Field(
        None,
        description="Number of bathrooms required. For residential only."
    )
    property_type: Optional[str] = Field(
        None,
        description="Property type: HDB or Condo. For residential only."
    )
    furnishing_status: Optional[str] = Field(
        None,
        description="Furnishing preference: Fully Furnished, Partially Furnished, Unfurnished. For residential only."
    )
    min_lease_months: Optional[int] = Field(
        None,
        description="Minimum lease duration in months requested by user."
    )

    # --- 5. AMENITIES & POLICIES (shared) ---
    needs_cooking: Optional[bool] = Field(
        None,
        description="True if user needs to cook. For coliving only."
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
        description="True if user asks about bringing guests. For coliving only."
    )
    needs_wifi: Optional[bool] = Field(
        None,
        description="True if user asks for Wifi. For coliving only."
    )
    needs_aircon: Optional[bool] = Field(
        None,
        description="True if user requires air conditioning. For residential only."
    )
    needs_washer_dryer: Optional[bool] = Field(
        None,
        description="True if user requires washer/dryer. For residential only."
    )
