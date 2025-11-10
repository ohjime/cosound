"""
Background task for polling sound updates from the backend.
"""
import asyncio
import httpx
from typing import Optional
import logging

from core.config import BACKEND_URL, POLL_INTERVAL

logger = logging.getLogger(__name__)


async def request_sound() -> Optional[str]:
    """
    Make an HTTP GET request to the backend to retrieve the most relevant sound.
    
    This function makes an async call and does NOT interrupt the audio player.
    
    Returns:
        The sound filename/id if available, None otherwise.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BACKEND_URL}/api/model/currentSong",
                timeout=5.0
            )
            if response.status_code == 200:
                data = response.json()
                # Extract sound title from the recommendations object
                sound = data.get("recommendations", {}).get("title")
                logger.debug(f"Received sound from backend: {sound}")
                return sound
            else:
                logger.warning(f"Backend returned status code: {response.status_code}")
                return None
                
    except httpx.TimeoutException:
        logger.warning("Request to backend timed out")
        return None
    except httpx.RequestError as e:
        logger.error(f"Error connecting to backend: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_playing(): {e}")
        return None


async def poll_sound(player_module):
    """
    Continuously poll for sound updates and transition when necessary.
    
    Args:
        player_module: The player module with transition() and get_playing() functions.
    """
    logger.info("Starting sound update polling...")
    while True:
        try:
            # Get the sound that should be playing from backend
            new_sound = await request_sound()
            if new_sound:
                playing_sound = player_module.get_playing()
                # Only transition if the sound has changed
                if new_sound != playing_sound:
                    logger.info(f"sound change detected: {playing_sound} -> {new_sound}")
                    player_module.transition(new_sound)
                else:
                    logger.debug(f"sound unchanged: {playing_sound}")
            # Wait before polling again
            await asyncio.sleep(POLL_INTERVAL)
        except Exception as e:
            logger.error(f"Error in poll_sound_updates loop: {e}")
            # Continue polling even if there's an error
            await asyncio.sleep(POLL_INTERVAL)
