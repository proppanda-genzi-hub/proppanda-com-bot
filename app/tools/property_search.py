import httpx
import logging
import os

logger = logging.getLogger(__name__)


class PropertySearchTool:
    """Tool for property search with geocoding support."""
    
    def __init__(self, db_session, location_iq_key: str = None):
        self.db = db_session
        self.api_key = location_iq_key or os.getenv("LOCATION_IQ_KEY")

    async def get_coordinates(self, location_name: str):
        """
        Converts a location name into (latitude, longitude).
        """
        if not location_name or not self.api_key:
            return None

        url = "https://us1.locationiq.com/v1/search.php"
        params = {
            "key": self.api_key,
            "q": location_name,
            "format": "json",
            "countrycodes": "sg",
            "limit": 1
        }
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                if not data:
                    logger.warning(f"LocationIQ found no matches for: {location_name}")
                    return None
                
                lat = float(data[0]['lat'])
                lng = float(data[0]['lon'])
                return lat, lng
                
            except Exception as e:
                logger.error(f"Geocoding error: {e}")
                return None
