import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, precision_recall_fscore_support
from sklearn.pipeline import Pipeline

from .chat_analysis import analyze_chat
from .chat_dataset import load_chat_dataset
from .schemas import ChatAnalyzeRequest, Movie


def train_relevance_model(records: list[dict]) -> Pipeline:
    train = [row for row in records if row["split"] == "train"]
    model = Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)),
        ("classifier", LogisticRegression(max_iter=500, class_weight="balanced", random_state=42)),
    ])
    model.fit([row["text"] for row in train], [row["relevance"] for row in train])
    return model


def evaluate_relevance(model: Pipeline, records: list[dict], split: str = "test") -> dict:
    selected = [row for row in records if row["split"] == split]
    truth = [row["relevance"] for row in selected]
    predicted = model.predict([row["text"] for row in selected])
    precision, recall, f1, _ = precision_recall_fscore_support(truth, predicted, labels=["MOVIE"], average="macro", zero_division=0)
    return {"split": split, "rows": len(selected), "accuracy": round(float(accuracy_score(truth, predicted)), 4),
            "movie_precision": round(float(precision), 4), "movie_recall": round(float(recall), 4), "movie_f1": round(float(f1), 4),
            "labels": ["CHAT", "MOVIE"], "confusion_matrix": confusion_matrix(truth, predicted, labels=["CHAT", "MOVIE"]).tolist()}


def evaluate_preference_extraction(records: list[dict], movies: list[Movie], split: str = "test") -> dict:
    selected = [row for row in records if row["split"] == split and row["relevance"] == "MOVIE"]
    predictions = []
    for row in selected:
        result = analyze_chat(ChatAnalyzeRequest(messages=[{"user_id": "eval-user", "text": row["text"]}]), movies)
        predictions.append(result.analyses[0])
    target_type_accuracy = np.mean([prediction.target_type == row["target_type"] for row, prediction in zip(selected, predictions)])
    target_rows = [(row, prediction) for row, prediction in zip(selected, predictions) if row["target"] is not None]
    target_accuracy = np.mean([prediction.target == row["target"] for row, prediction in target_rows]) if target_rows else 0
    attitude_accuracy = np.mean([prediction.attitude == row["attitude"] for row, prediction in zip(selected, predictions)])
    score_mae = np.mean([abs(prediction.preference_score - row["preference_score"]) for row, prediction in zip(selected, predictions)])
    return {"split": split, "rows": len(selected), "target_type_accuracy": round(float(target_type_accuracy), 4),
            "target_accuracy": round(float(target_accuracy), 4), "attitude_accuracy": round(float(attitude_accuracy), 4),
            "preference_score_mae": round(float(score_mae), 4)}


def run_chat_evaluation(dataset_path: Path, movies: list[Movie], output_dir: Path) -> dict:
    records = load_chat_dataset(dataset_path)
    model = train_relevance_model(records)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "chat_relevance.joblib"
    joblib.dump(model, model_path)
    report = {"dataset": str(dataset_path), "relevance": evaluate_relevance(model, records),
              "preference_extraction": evaluate_preference_extraction(records, movies), "model_path": str(model_path)}
    (output_dir / "chat_evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
