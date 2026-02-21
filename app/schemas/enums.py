import enum


class UserType(enum.Enum):
    """User type enumeration."""
    AGENT = "agent"
    PROSPECT = "prospect"
    ADMIN = "admin"


class CurrentListing(enum.Enum):
    """Property listing status enumeration."""
    AVAILABLE = "Available to rent"
    RENTED = "Rented"
    PENDING = "Pending"
    INACTIVE = "Inactive"
