from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Text, Integer, Date, 
    DateTime, ForeignKey, Enum
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY as PG_ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base
from app.schemas.enums import UserType, CurrentListing


class Agent(Base):
    """Agent/Real Estate Agent model."""
    __tablename__ = 'agent'

    agent_id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=True)
    email = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    
    # Capability flags
    rooms_for_rent = Column(Boolean, nullable=True)
    co_living_property = Column(Boolean, nullable=True)
    residential_property_rent = Column(Boolean, nullable=True)
    commercial_property_rent = Column(Boolean, nullable=True)
    residential_property_resale = Column(Boolean, nullable=True)
    residential_property_developer = Column(Boolean, nullable=True)
    commercial_property_resale = Column(Boolean, nullable=True)
    commercial_property_developer = Column(Boolean, nullable=True)
    
    # Profile information
    show_guide = Column(Boolean, default=True)
    profile_photo = Column(Text, nullable=True)
    bio = Column(Text, nullable=True)
    accomplishments = Column(Text, nullable=True)
    registration_number = Column(String, nullable=True)
    company_name = Column(Text, nullable=True)
    linkedin_url = Column(String, nullable=True)
    instagram_url = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Additional fields
    embedded_domain = Column(Text, nullable=True)
    subscription_status = Column(Text, nullable=True)
    activated_on = Column(DateTime(timezone=True), nullable=True)
    consent_to_publish = Column(Boolean, default=True)
    password = Column(Text, nullable=True)
    verified = Column(Boolean, default=False)
    salesperson_name = Column(Text, nullable=True)
    registration_no = Column(Text, nullable=True)
    registration_start_date = Column(Date, nullable=True)
    registration_end_date = Column(Date, nullable=True)
    estate_agent_name = Column(Text, nullable=True)
    estate_agent_license_no = Column(Text, nullable=True)
    expiry_date = Column(DateTime(timezone=True), nullable=True)
    stripe_customer_id = Column(Text, nullable=True)
    stripe_subscription_id = Column(Text, nullable=True)
    
    # Chatbot settings
    chatbot_name = Column(Text, nullable=True)
    tokens_available = Column(Integer, nullable=True)
    current_plan = Column(Text, default='Gold')
    previous_plan = Column(Text, nullable=True)
    plan_change_history = Column(PG_ARRAY(JSONB), default=[])
    chatbot_enabled = Column(Boolean, default=True)
    chatbot_schedule_active = Column(Boolean, default=False)
    chatbot_business_hours = Column(JSONB, nullable=True)
    chatbot_timezone = Column(Text, default='Asia/Singapore')
    preferred_currency = Column(Text, default='SGD')
    
    # Contact information
    contact_name = Column(Text, nullable=True)
    contact_number = Column(Text, nullable=True)
    contact_email = Column(PG_ARRAY(String), nullable=True)
    
    # WhatsApp fields
    whatsapp_phone_number = Column(Text, nullable=True)
    whatsapp_phone_number_id = Column(Text, nullable=True)
    whatsapp_waba_id = Column(Text, nullable=True)
    whatsapp_access_token = Column(Text, nullable=True)

    # Relationships
    properties = relationship("ColivingProperty", back_populates="agent")
    prospects = relationship("ProspectInfo", back_populates="agent")


class ProspectInfo(Base):
    """Prospect/Lead information model."""
    __tablename__ = 'prospect_info'

    user_id = Column(String(50), primary_key=True)
    agent_id = Column(String(50), ForeignKey('agent.agent_id', ondelete='CASCADE', onupdate='CASCADE'), primary_key=True)
    session_id = Column(Text, nullable=True)
    mode = Column(String(20), nullable=True)
    name = Column(String(100), nullable=True)
    email = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    gender = Column(String(20), nullable=True)
    nationality = Column(String(50), nullable=True)
    created_date = Column(DateTime, server_default=func.now())
    last_interaction = Column(DateTime, server_default=func.now())
    status = Column(String(20), nullable=True)
    chat_link = Column(Text, nullable=True)
    profession = Column(Text, nullable=True)
    pass_field = Column('pass', Text, server_default='-')
    max_occupants = Column(Integer, nullable=True)
    user_occupant_type = Column(String(50), nullable=True)
    property_type = Column(Text, nullable=True)
    move_in_date = Column(Text, nullable=True)
    intended_lease_duration = Column(Text, nullable=True)
    mail_consent = Column(Boolean, default=False)
    nature_of_industry = Column(Text, server_default='-')
    property_intent = Column(Text, nullable=True)
    chat_summary = Column(Text, nullable=True)

    # Relationships
    agent = relationship("Agent", back_populates="prospects")


class ColivingProperty(Base):
    """Co-living property model."""
    __tablename__ = 'coliving_property'

    property_id = Column(Text, primary_key=True, server_default=func.gen_random_uuid())
    property_address = Column(Text, nullable=True)
    property_type = Column(Text, nullable=True)
    furnishing_status = Column(Text, nullable=True)
    room_type = Column(Text, nullable=True)
    gender_preference = Column(Text, nullable=True)
    nationality_preferences = Column(Text, nullable=True)
    room_size_sqft = Column(Integer, nullable=True)
    aircon = Column(Boolean, nullable=True)
    bedframe_mattress = Column('bedframe_ & _mattress', Boolean, nullable=True)
    wardrobe = Column(Boolean, nullable=True)
    study_table_chair = Column('study_table_ & _chair', Boolean, nullable=True)
    ensuite_bathroom = Column(Boolean, nullable=True)
    window_details = Column(Boolean, nullable=True)
    washroom_type = Column(Text, nullable=True)
    shared_by_count = Column(Integer, nullable=True)
    monthly_rent = Column(Integer, nullable=True)
    security_deposit = Column(Integer, nullable=True)
    utilities_included = Column(Text, nullable=True)
    utilities_split = Column(Text, nullable=True)
    cooking_allowed = Column(Boolean, nullable=True)
    gas_stove = Column(Boolean, default=True)
    microwave = Column(Boolean, nullable=True)
    washer = Column(Boolean, nullable=True)
    dryer = Column(Boolean, nullable=True)
    refrigirator = Column(Boolean, nullable=True)
    dinning_table = Column(Boolean, nullable=True)
    living_area_shared = Column(Boolean, nullable=True)
    wifi = Column(Text, nullable=True)
    cleaning_service = Column(Text, nullable=True)
    current_tenants_summary = Column(Text, nullable=True)
    max_occupancy = Column(Text, nullable=True)
    house_rules = Column(Text, nullable=True)
    swimming_pool = Column(Boolean, nullable=True)
    tennis_courts = Column(Boolean, nullable=True)
    barbeque = Column(Boolean, nullable=True)
    squash_court = Column(Boolean, nullable=True)
    gym = Column(Boolean, nullable=True)
    security_24_7 = Column('security_24 / 7', Boolean, nullable=True)
    parking_charges = Column(Text, nullable=True)
    lift_access = Column(Boolean, nullable=True)
    visitor_policy = Column(Text, nullable=True)
    pet_policy = Column(Text, nullable=True)
    smoking_vaping_policy = Column(Text, nullable=True)
    min_lease_months = Column(Integer, nullable=True)
    renewal_option = Column(Text, nullable=True)
    notice_period_weeks = Column(Text, nullable=True)
    video_tour_url = Column(Text, nullable=True)
    additional_information = Column(Text, nullable=True)
    prefered_viewing_details = Column(Text, nullable=True)
    media = Column(Text, nullable=True)
    nearest_mrt = Column(Text, nullable=True)
    property_name = Column(Text, nullable=True)
    unit_number = Column(Integer, nullable=True)
    block_house_no = Column('block_no_ / _house_no', Text, nullable=True)
    landlord_living = Column(Boolean, nullable=True)
    thumbnail_image = Column(Text, nullable=True)
    virtual_viewing_available = Column(Boolean, default=False)
    agent_id = Column(String, ForeignKey('agent.agent_id', ondelete='CASCADE', onupdate='CASCADE'), nullable=True)
    consent_to_publish = Column(Boolean, default=True)
    is_featured = Column(Boolean, nullable=True)
    listing_status = Column(Text, nullable=True)
    floor_level = Column(Integer, nullable=True)
    total_rooms = Column(Integer, default=5)
    total_washrooms = Column(Integer, default=2)
    district = Column(Text, nullable=True)
    badminton_court = Column(Boolean, nullable=True)
    room_number = Column(Text, nullable=True)
    agency_fee_applicable = Column(Boolean, nullable=True)
    agency_fee = Column(Text, nullable=True)
    available_from = Column(Date, server_default=func.now())
    currency_type = Column(Text, server_default='SGD')
    description = Column(Text, nullable=True)
    parking_facility_available = Column('parking _facility_available', Boolean, nullable=True)
    postal_code = Column(Integer, nullable=True)
    utilities_fees = Column(Text, nullable=True)
    current_listing = Column(Enum(CurrentListing), server_default='Available to rent')
    tv = Column(Boolean, default=False)
    environment = Column(Text, nullable=True)

    # Relationships
    agent = relationship("Agent", back_populates="properties")


class ChatHistory(Base):
    """Chat history model for web conversations."""
    __tablename__ = 'chat_history_web'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Text, nullable=False, index=True)
    user_id = Column(Text, nullable=False, index=True)
    agent_id = Column(String(50), ForeignKey('agent.agent_id', ondelete='CASCADE'), nullable=False)
    sender = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    message_metadata = Column('metadata', JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
