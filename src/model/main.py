from fastapi import FastAPI
import asyncio
import logging
from contextlib import asynccontextmanager

from core import player
from tasks import update

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("Starting audio player...")
    # request_sound
    new_sound = await update.request_sound()
    if new_sound:
        player.play(new_sound, fade_in=True)
    # Start background polling task
    logger.info("Starting background sound polling...")
    polling_task = asyncio.create_task(update.poll_sound(player))
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    player.stop()
    logger.info("Shutdown complete")


app = FastAPI(lifespan=lifespan)


@app.get("/")
def read_root():
    """Get the audio players most current status."""
    playing = player.get_playing()
    return {
        "status": "playing" if playing else "idle",
        "playing": playing
    }


@app.post("/transition")
def trigger_transition(sound: str):
    """
    Manually trigger a transition to a specific sound.
    
    Args:
        sound: The filename of the sound to transition to.
    """
    logger.info(f"Manual transition requested to: {sound}")
    player.transition(sound)
    return {
        "status": "transitioning",
        "new_sound": sound
    }