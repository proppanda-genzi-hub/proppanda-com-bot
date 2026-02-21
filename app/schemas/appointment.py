from pydantic import BaseModel, Field
from typing import Optional


class AppointmentInfo(BaseModel):
    """
    Schema for appointment booking information extraction.
    """
    
    email: Optional[str] = Field(
        None,
        description="User's email address for appointment confirmation."
    )
    
    pass_type: Optional[str] = Field(
        None,
        description="Type of pass the user holds (EP, SP, Student, Citizen, PR)."
    )
    
    lease_months: Optional[int] = Field(
        None,
        description="Intended lease duration in months."
    )
    
    viewing_type: Optional[str] = Field(
        None,
        description="Type of viewing: 'In-Person' or 'Virtual'."
    )
    
    time_preference: Optional[str] = Field(
        None,
        description="Preferred time slot: 'Morning', 'After Lunch', or 'After Work'."
    )
    
    selected_slot: Optional[str] = Field(
        None,
        description="The specific date and time slot selected by the user."
    )
    
    property_reference: Optional[str] = Field(
        None,
        description="Reference to the property user wants to view."
    )
