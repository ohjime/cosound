import os, sys, numpy as np, librosa

MODEL = "model_linear_ridge.npz"

# same features as training:
def extract_features(path, sr_target=22050):
    y, sr = librosa.load(path, sr=sr_target, mono=True)
    min_len = sr * 5
    if len(y) < min_len:
        y = np.pad(y, (0, min_len - len(y)))

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    mfcc_mean = mfcc.mean(axis=1)
    mfcc_std  = mfcc.std(axis=1)

    sc   = librosa.feature.spectral_centroid(y=y, sr=sr).mean()
    sroff= librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85).mean()
    flat = librosa.feature.spectral_flatness(y=y).mean()
    zcr  = librosa.feature.zero_crossing_rate(y).mean()

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)

    feat = np.concatenate([mfcc_mean, mfcc_std, [sc, sroff, flat, zcr], chroma]).astype(np.float32)
    return feat

def softmax(v):
    v = v - v.max()
    e = np.exp(v)
    return e / (e.sum() + 1e-9)

def main(path):
    if not os.path.exists(MODEL):
        raise SystemExit("Train first: model_linear_ridge.npz not found.")

    m = np.load(MODEL, allow_pickle=True)
    mean, scale, W, tags = m["mean"], m["scale"], m["W"], list(m["tags"])

    x = extract_features(path)
    # standardize using training stats
    xz = (x - mean) / (scale + 1e-8)

    y_hat = xz @ W  # (K,)
    # choose either:
    # 1) clamp to [0,1]
    weights = np.clip(y_hat, 0.0, 1.0)

    # or 2) normalized distribution (probabilities)
    # weights = softmax(y_hat)

    print("\nPredicted tag weights:")
    for tag, w in sorted(zip(tags, weights.tolist()), key=lambda z: z[1], reverse=True):
        print(f"{tag:16s} {w:.3f}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python predict.py path/to/your_audio.wav")
        raise SystemExit(1)
    main(sys.argv[1])
