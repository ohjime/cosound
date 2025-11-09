from fastapi import FastAPI
from pathlib import Path
import numpy as np
import librosa
import sounddevice as sd

app = FastAPI()

# Global buffer and stream
playing = {"buffer": None, "sr": None, "stream": None, "pos": 0}

BUFFER_SIZE = 44100 * 120  # 60 seconds buffer, adjust as needed

def callback(outdata, frames, time, status):
    if playing["buffer"] is None:
        outdata.fill(0)
        return

    start = playing["pos"]
    end = start + frames
    if end > len(playing["buffer"]):
        end = len(playing["buffer"])
    
    outdata[: end - start] = playing["buffer"][start:end].reshape(-1, 1)
    
    # Fill remaining with zeros if buffer is shorter
    if frames > end - start:
        outdata[end - start :] = 0

    playing["pos"] = end % len(playing["buffer"])


@app.on_event("startup")
async def startup_event():
    audio_file = Path(__file__).parent / ".audio" / "gmulyk-edit__7965__ingeos__hong-linh-ha-tinh-vietnam.wav"
    y, sr = librosa.load(str(audio_file), sr=None)
    
    # Initialize buffer
    buffer = np.zeros(max(len(y), BUFFER_SIZE))
    buffer[:len(y)] = y
    playing["buffer"] = buffer
    playing["sr"] = sr
    playing["pos"] = 0
    
    # Start output stream
    stream = sd.OutputStream(channels=1, samplerate=sr, callback=callback)
    stream.start()
    playing["stream"] = stream


@app.get("/")
def read_root():
    audio_file = Path(__file__).parent / ".audio" / "gmulyk-edit__121968__nfsgit__quiet-forest.wav"
    y2, sr2 = librosa.load(str(audio_file), sr=None)

    buffer = playing["buffer"]
    min_len = min(len(buffer), len(y2))

    # Define fade length (in samples)
    fade_len = int(sr2 * 1.0)  # 1 second fade
    fade_len = min(fade_len, min_len)

    # Create linear fade-in and fade-out arrays
    fade_in = np.linspace(0, 1, fade_len)
    fade_out = np.linspace(1, 0, fade_len)

    # Gradually mix old buffer with new clip
    merged = np.zeros(min_len)
    merged[:fade_len] = buffer[:fade_len] * fade_out + y2[:fade_len] * fade_in
    if min_len > fade_len:
        merged[fade_len:] = y2[fade_len:]  # rest of new clip

    # Write merged clip back into buffer
    playing["buffer"][:min_len] = merged
    playing["pos"] = 0  # reset read position to start

    return {"Hello": "World"}