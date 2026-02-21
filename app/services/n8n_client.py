import httpx
import os
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class N8NClient:
    """
    Simplified N8N client for appointment scheduling only.
    Human handoff functionality has been removed.
    """
    
    def __init__(self):
        self.calendar_events_url = os.getenv(
            "N8N_CALENDAR_EVENTS_URL",
            "https://rajigenzi.app.n8n.cloud/webhook/get_calender_events"
        )
        self.schedule_appointment_url = os.getenv(
            "N8N_APPOINTMENT_URL",
            "https://rajigenzi.app.n8n.cloud/webhook/schedule_appointment"
        )
        self.timeout = 30.0

    async def get_available_slots(self, agent_id: str, preferred_time: str) -> Optional[str]:
        """
        Fetch available appointment slots from N8N.
        
        Args:
            agent_id: Agent identifier
            preferred_time: Time preference (Morning, After Lunch, After Work)
            
        Returns:
            JSON string of available slots or None on error
        """
        payload = {
            "body": [
                {
                    "agent_id": agent_id,
                    "prefered_time": preferred_time  # Note: typo in N8N webhook (prefered instead of preferred)
                }
            ]
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"📤 Fetching calendar events from N8N: {payload}")
                response = await client.post(
                    self.calendar_events_url,
                    json=payload
                )
                response.raise_for_status()
                
                result = response.text
                logger.info(f"✅ Received calendar events from N8N")
                return result
                
        except httpx.HTTPError as e:
            logger.error(f"❌ N8N calendar events request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error fetching calendar events: {e}")
            return None

    async def schedule_appointment(self, appointment_data: Dict[str, Any]) -> bool:
        """
        Schedule an appointment via N8N webhook.
        
        Args:
            appointment_data: Dictionary containing appointment details
            
        Returns:
            True if successful, False otherwise
        """
        # Payload should be a list with the appointment data
        payload = [appointment_data]
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"📤 Scheduling appointment via N8N")
                response = await client.post(
                    self.schedule_appointment_url,
                    json=payload
                )
                response.raise_for_status()
                
                logger.info(f"✅ Appointment scheduled successfully via N8N")
                return True
                
        except httpx.HTTPError as e:
            logger.error(f"❌ N8N appointment scheduling failed: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error scheduling appointment: {e}")
            return False
