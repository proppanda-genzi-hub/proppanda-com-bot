from openai import AsyncOpenAI
import os
import logging

logger = logging.getLogger(__name__)


class OpenAIService:
    """Service for interacting with OpenAI API."""
    
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY is missing in environment variables!")
        
        self.client = AsyncOpenAI(api_key=api_key)

    async def get_chat_response(self, system_prompt: str, user_message: str, model: str = "gpt-4o"):
        """
        Sends the prompt and user message to OpenAI and gets a response.
        """
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI Error: {e}")
            return "I'm having a little trouble connecting right now. Can you try again in a moment?"

    async def get_structured_response(
        self, 
        system_prompt: str, 
        user_message: str, 
        response_format: dict = None,
        model: str = "gpt-4o"
    ):
        """
        Get a structured JSON response from OpenAI.
        """
        try:
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0
            }
            
            if response_format:
                kwargs["response_format"] = response_format
            
            response = await self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI Structured Response Error: {e}")
            return None
