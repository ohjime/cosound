"""Configuration settings for the audio model."""
import os

# Backend server configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:3000")

# Polling configuration
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))  # seconds

# Audio configuration
BUFFER_SIZE = 44100 * 120  # 120 seconds buffer
DEFAULT_FADE_DURATION = 2.0  # seconds