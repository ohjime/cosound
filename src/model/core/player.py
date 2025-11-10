"""
Audio player module for handling playback and transitions using pygame.mixer.
Uses pygame's Channel system to crossfade between tracks.
"""
import threading
import pygame
from pathlib import Path
from typing import Optional
import logging

from .config import DEFAULT_FADE_DURATION

logger = logging.getLogger(__name__)


class Player:
    """
    Audio player using pygame.mixer to handle crossfades between tracks.
    Maintains two channels:
    - channel 0: current playing track
    - channel 1: next track during crossfade
    """

    def __init__(self, sr: int = 44100):
        self.sr = sr
        self._lock = threading.RLock()
        self._playing: Optional[str] = None
        self._initialized = False
        self._current_channel = 0
        self._next_channel = 1
        self._is_transitioning = False
        self._transition_duration = 0.0

    def _ensure_mixer(self):
        """Initialize pygame mixer if not already initialized."""
        if not self._initialized:
            try:
                pygame.mixer.init(frequency=self.sr, channels=1, buffer=512)
                # Reserve 2 channels for crossfading
                pygame.mixer.set_num_channels(2)
                self._initialized = True
                logger.info(f"Pygame mixer initialized at {self.sr}Hz")
            except pygame.error as e:
                logger.error(f"Failed to initialize pygame mixer: {e}")
                raise

    def _get_audio_path(self, sound: str) -> Path:
        """Get the full path to an audio file."""
        audio_path = Path(__file__).parent.parent / ".audio" / sound
        if not audio_path.exists():
            raise FileNotFoundError(f"Sound file not found: {audio_path}")
        return audio_path

    def play(self, sound: Optional[str] = None, fade_in: bool = True, fade_duration: float = 30.0) -> None:
        """Play a sound, optionally with fade-in, stopping any current playback."""
        # Choose random file if not provided
        if sound is None:
            import random
            sounds_dir = Path(__file__).parent.parent / ".audio"
            if not sounds_dir.exists():
                logger.error(f".audio/ directory not found at {sounds_dir}")
                return
            files = sum([
                list(sounds_dir.glob("*.wav")),
                list(sounds_dir.glob("*.mp3")),
                list(sounds_dir.glob("*.ogg")),
            ], [])
            if not files:
                logger.error("No sound files found in .audio/ directory")
                return
            sound = random.choice(files).name

        try:
            self._ensure_mixer()
            audio_path = self._get_audio_path(sound)
            
            with self._lock:
                # Stop all channels
                pygame.mixer.stop()
                
                # Load and play on current channel with infinite looping
                pygame_sound = pygame.mixer.Sound(str(audio_path))
                channel = pygame.mixer.Channel(self._current_channel)
                
                # Start playing with infinite loop
                channel.play(pygame_sound, loops=-1)
                
                if fade_in:
                    # Manual fade in using volume control
                    def fade_in_volume():
                        import time
                        steps = 100
                        step_duration = fade_duration / steps
                        for i in range(steps + 1):
                            volume = i / steps
                            channel.set_volume(volume)
                            time.sleep(step_duration)
                    
                    threading.Thread(target=fade_in_volume, daemon=True).start()
                    logger.info(f"Now playing (fading in over {fade_duration:.1f}s): {sound} ({pygame_sound.get_length():.2f}s) [looping]")
                else:
                    channel.set_volume(1.0)
                    logger.info(f"Now playing: {sound} ({pygame_sound.get_length():.2f}s) [looping]")
                
                self._playing = sound
                
        except Exception as e:
            logger.error(f"Error loading sound {sound}: {e}")

    def transition(self, sound: str, duration: float = 30.0, force: bool = False) -> None:
        """Crossfade to a new sound over `duration` seconds (in milliseconds for pygame)."""
        try:
            self._ensure_mixer()
            audio_path = self._get_audio_path(sound)
            
            with self._lock:
                # If it's the same sound and not forced, just let it continue playing
                if sound == self._playing and not force:
                    logger.info(f"Same sound already playing: {sound}, continuing seamlessly")
                    return
                
                # Prevent overlapping transitions
                if self._is_transitioning:
                    logger.warning(f"Transition already in progress, skipping request for {sound}")
                    return
                
                # Load the new sound
                new_sound = pygame.mixer.Sound(str(audio_path))
                
                # Get the current and next channels
                current_channel = pygame.mixer.Channel(self._current_channel)
                next_channel = pygame.mixer.Channel(self._next_channel)
                
                # Convert duration to seconds for volume control
                fade_duration_sec = duration
                
                # Mark as transitioning
                self._is_transitioning = True
                self._transition_duration = duration
                
                # Start the new sound on the next channel with infinite looping at volume 0
                next_channel.play(new_sound, loops=-1)
                next_channel.set_volume(0.0)
                
                # Manual crossfade using volume control
                def crossfade():
                    import time
                    steps = 100
                    step_duration = fade_duration_sec / steps
                    
                    for i in range(steps + 1):
                        progress = i / steps
                        # Fade out current channel
                        if current_channel.get_busy():
                            current_channel.set_volume(1.0 - progress)
                        # Fade in next channel
                        next_channel.set_volume(progress)
                        time.sleep(step_duration)
                    
                    # Ensure volumes are set correctly at the end
                    current_channel.set_volume(0.0)
                    next_channel.set_volume(1.0)
                    
                    with self._lock:
                        self._is_transitioning = False
                        logger.debug("Crossfade completed, ready for next transition")
                
                threading.Thread(target=crossfade, daemon=True).start()
                
                # Swap channels for next transition
                self._current_channel, self._next_channel = self._next_channel, self._current_channel
                
                self._playing = sound
                logger.info(f"Crossfading to: {sound} over {duration:.1f}s")
                
        except Exception as e:
            logger.error(f"Error during transition to {sound}: {e}")
            with self._lock:
                self._is_transitioning = False

    def get_playing(self) -> Optional[str]:
        """Get the name of the currently playing sound."""
        with self._lock:
            return self._playing

    def is_transitioning(self) -> bool:
        """Check if a transition is currently in progress."""
        with self._lock:
            return self._is_transitioning

    def stop(self) -> None:
        """Stop all playback and quit the mixer."""
        with self._lock:
            self._playing = None
            if self._initialized:
                try:
                    pygame.mixer.stop()
                    pygame.mixer.quit()
                    self._initialized = False
                    logger.info("Pygame mixer stopped")
                except Exception as e:
                    logger.error(f"Error stopping mixer: {e}")


# Singleton instance and module-level API for backward compatibility
_PLAYER = Player()


def play(sound: Optional[str] = None, fade_in: bool = True) -> None:
    _PLAYER.play(sound, fade_in=fade_in, fade_duration=30.0)


def transition(sound: str) -> None:
    # Force 30s as requested
    _PLAYER.transition(sound, duration=30.0)


def get_playing() -> Optional[str]:
    return _PLAYER.get_playing()


def is_transitioning() -> bool:
    return _PLAYER.is_transitioning()


def stop() -> None:
    _PLAYER.stop()