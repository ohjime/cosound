# 🎵 Environmental Sound Classification (ESC-50) — Linear Ridge Model

This folder contains scripts and resources for training and testing a sound classification model using the **ESC-50 dataset**.

---

## 🧠 Overview

The model is trained on the [ESC-50 dataset](https://github.com/karolpiczak/ESC-50) — a collection of environmental sounds across 50 categories.  
The trained model (`model_linear_ridge.npz`) can be used to predict classes for new audio clips.

---

## ⚙️ Setup

### 1. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

---

## 🚀 Usage

### 1. Build the dataset

```bash
python build_dataset.py
```

### 2. Train the linear regression model

```bash
python train_linear.py
```

### 3. Test with your own audio

Place your audio clips inside the `main_audio/` folder.

Run batch prediction to generate a CSV of results:

```bash
python batch_predict.py
```

The predictions will be saved as a `.csv` file with corresponding class labels and confidence scores.
