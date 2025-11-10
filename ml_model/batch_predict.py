import os
import csv
import numpy as np
import librosa
from glob import glob

MODEL = "model_linear_ridge.npz"
AUDIO_DIR = "main_audio"          # <- your folder with .wav files
OUT_CSV = "songs_seed.csv"

# The EXACT target order you want in the DB's vector(5)
TAGS_DESIRED = ['rain', 'sea_waves', 'thunderstorm', 'wind', 'crackling_fire']

# === feature extractor must match training ===
def extract_features(path, sr_target=22050):
    y, sr = librosa.load(path, sr=sr_target, mono=True)
    min_len = sr * 5
    if len(y) < min_len:
        y = np.pad(y, (0, min_len - len(y)))

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    mfcc_mean = mfcc.mean(axis=1)
    mfcc_std  = mfcc.std(axis=1)

    sc    = librosa.feature.spectral_centroid(y=y, sr=sr).mean()
    sroff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85).mean()
    flat  = librosa.feature.spectral_flatness(y=y).mean()
    zcr   = librosa.feature.zero_crossing_rate(y).mean()

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)

    feat = np.concatenate([mfcc_mean, mfcc_std, [sc, sroff, flat, zcr], chroma]).astype(np.float32)
    return feat

def predict_weights_for_file(path, mean, scale, W, model_tags):
    """Return dict(tag -> weight in [0,1]) from linear ridge model."""
    x = extract_features(path)
    xz = (x - mean) / (scale + 1e-8)          # standardize like training
    y_hat = xz @ W                             # (K,)
    weights = np.clip(y_hat, 0.0, 1.0)         # clamp to [0,1]
    return {tag: float(w) for tag, w in zip(model_tags, weights.tolist())}

def main():
    if not os.path.exists(MODEL):
        raise SystemExit("Train first: model_linear_ridge.npz not found.")

    m = np.load(MODEL, allow_pickle=True)
    mean, scale, W, model_tags = m["mean"], m["scale"], m["W"], list(m["tags"])
    model_tag_index = {t:i for i,t in enumerate(model_tags)}

    # gather wav files
    wavs = sorted(glob(os.path.join(AUDIO_DIR, "*.wav")))
    if not wavs:
        raise SystemExit(f"No .wav files found in {AUDIO_DIR}/")

    rows = []
    for wav_path in wavs:
        title = os.path.splitext(os.path.basename(wav_path))[0]

        # predict per model tags
        pred_map = predict_weights_for_file(wav_path, mean, scale, W, model_tags)

        # reorder to desired 5-tag order; fill 0.0 if tag not in model
        vec5 = []
        for tag in TAGS_DESIRED:
            vec5.append(pred_map.get(tag, 0.0))

        # format embedding for Supabase pgvector CSV import: "[v1,v2,...]"
        embedding_str = "[" + ",".join(f"{v:.6f}" for v in vec5) + "]"

        rows.append({"title": title, "embedding": embedding_str})

    # write CSV with only the columns your table needs to import
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "embedding"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUT_CSV}")
    print("Example row:")
    if rows:
        print(rows[0])

if __name__ == "__main__":
    main()
