import numpy as np
from sklearn.preprocessing import StandardScaler

DATA = "dataset.npz"
MODEL_OUT = "model_linear_ridge.npz"
LAMBDA = 1.0  # ridge strength; 0.1–5.0 usually OK

def fit_ridge_closed_form(Xz, Y, lam=1.0):
    F = Xz.shape[1]
    XtX = Xz.T @ Xz
    # (X^T X + λI)^{-1} X^T Y
    W = np.linalg.solve(XtX + lam * np.eye(F, dtype=Xz.dtype), Xz.T @ Y)
    return W  # (F,K)

def main():
    data = np.load(DATA, allow_pickle=True)
    X, Y = data["X"], data["Y"]
    tags = list(data["tags"])

    scaler = StandardScaler().fit(X)
    Xz = scaler.transform(X)

    W = fit_ridge_closed_form(Xz, Y, lam=LAMBDA)  # (F,K)

    # Save model (scaler stats + weights + meta)
    np.savez_compressed(
        MODEL_OUT,
        mean=scaler.mean_.astype(np.float32),
        scale=scaler.scale_.astype(np.float32),
        W=W.astype(np.float32),
        tags=np.array(tags, dtype=object)
    )
    print(f"Saved {MODEL_OUT} | W shape={W.shape} | tags={tags}")

if __name__ == "__main__":
    main()
