import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def register_model(
    model_dir: Path,
    model_version: str,
    evaluation: dict,
    usable_events: int | None = None,
) -> dict:
    """현재 모델과 평가 결과를 버전별 Registry에 보관한다."""

    created_at = datetime.now(timezone.utc)
    run_id = created_at.strftime("%Y%m%dT%H%M%SZ")

    registry_dir = (
        model_dir
        / "registry"
        / model_version
        / run_id
    )

    registry_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    current_model = model_dir / "current.joblib"
    current_evaluation = model_dir / "evaluation.json"

    if not current_model.exists():
        raise FileNotFoundError(
            f"모델 파일이 없습니다: {current_model}"
        )

    if not current_evaluation.exists():
        raise FileNotFoundError(
            f"평가 파일이 없습니다: {current_evaluation}"
        )

    registered_model = registry_dir / "model.joblib"
    registered_evaluation = registry_dir / "evaluation.json"

    shutil.copy2(
        current_model,
        registered_model,
    )

    shutil.copy2(
        current_evaluation,
        registered_evaluation,
    )

    metadata = {
        "run_id": run_id,
        "model_version": model_version,
        "created_at": created_at.isoformat(),
        "model_path": str(registered_model),
        "evaluation_path": str(registered_evaluation),
        "metrics": evaluation.get(
            "metrics",
            {},
        ),
        "split_strategy": evaluation.get(
            "split_strategy",
        ),
        "embedding_backend": evaluation.get(
            "embedding_backend",
        ),
        "status": "REGISTERED",
        "usable_events": usable_events,
    }

    (
        registry_dir
        / "metadata.json"
    ).write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return metadata
def list_models(model_dir: Path) -> list[dict]:
    registry_root = model_dir / "registry"

    if not registry_root.exists():
        return []

    models = []

    for metadata_path in registry_root.glob("*/*/metadata.json"):
        models.append(
            json.loads(
                metadata_path.read_text(encoding="utf-8")
            )
        )

    models.sort(
        key=lambda item: item["created_at"],
        reverse=True,
    )

    return models

def latest_usable_events(model_dir: Path) -> int:
    models = list_models(model_dir)

    for model in models:
        usable_events = model.get("usable_events")

        if usable_events is not None:
            return int(usable_events)

    return 0