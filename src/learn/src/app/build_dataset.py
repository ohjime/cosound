import os, numpy as np, pandas as pd
import librosa
from tqdm import tqdm
from config import TAGS

ESC_DIR = "ESC-50"  # change if you placed it elsewhere
META_CSV = os.path.join(ESC_DIR, "meta", "esc50.csv")
AUDIO_DIR = os.path.join(ESC_DIR, "audio")
OUT_PATH = "dataset.npz"  # features + labels + filenames

# --- feature extractor (compact, robust) ---
def extract_features(path, sr_target=22050):
    y, sr = librosa.load(path, sr=sr_target, mono=True)
    # pad to at least 5s so stats are comparable
    min_len = sr * 5
    if len(y) < min_len:
        y = np.pad(y, (0, min_len - len(y)))

    # MFCCs (means + stds)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    mfcc_mean = mfcc.mean(axis=1)
    mfcc_std  = mfcc.std(axis=1)

    # Spectral stats
    sc   = librosa.feature.spectral_centroid(y=y, sr=sr).mean()
    sroff= librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85).mean()
    flat = librosa.feature.spectral_flatness(y=y).mean()
    zcr  = librosa.feature.zero_crossing_rate(y).mean()

    # Chroma (captures pitch color; helps for birds vs noise)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)

    feat = np.concatenate([mfcc_mean, mfcc_std, [sc, sroff, flat, zcr], chroma]).astype(np.float32)
    return feat  # shape (F,)

def main():
    meta = pd.read_csv(META_CSV)
    keep = meta[meta["category"].isin(TAGS)].copy()
    keep.reset_index(drop=True, inplace=True)

    label_to_idx = {t:i for i,t in enumerate(TAGS)}
    X, Y, FN = [], [], []

    for _, row in tqdm(keep.iterrows(), total=len(keep), desc="Extracting"):
        wav = os.path.join(AUDIO_DIR, row["filename"])
        if not os.path.exists(wav):
            continue
        try:
            x = extract_features(wav)
        except Exception as e:
            print(f"[WARN] {wav}: {e}")
            continue

        y = np.zeros(len(TAGS), dtype=np.float32)
        y[label_to_idx[row["category"]]] = 1.0

        X.append(x)
        Y.append(y)
        FN.append(wav)

    X = np.stack(X)                 # (N,F)
    Y = np.stack(Y)                 # (N,K)

    np.savez_compressed(
        OUT_PATH,
        X=X, Y=Y, files=np.array(FN, dtype=object),
        tags=np.array(TAGS, dtype=object)
    )
    print(f"Saved {OUT_PATH} with X={X.shape}, Y={Y.shape}")

if __name__ == "__main__":
    main()
