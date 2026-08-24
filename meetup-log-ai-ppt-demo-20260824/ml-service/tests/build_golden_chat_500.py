"""Build the versioned 500-utterance conversational golden set."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from meetup_ml.chat_dataset import build_chat_dataset


output = Path("data/golden/chat_golden_500.jsonl")
output.parent.mkdir(parents=True, exist_ok=True)
rows = build_chat_dataset(size=500, seed=20260812)
start = datetime(2025, 1, 1, tzinfo=timezone.utc)
with output.open("w", encoding="utf-8", newline="\n") as stream:
    for index, row in enumerate(rows):
        # Split strictly by time, never by random/template membership.
        row["created_at"] = (start + timedelta(minutes=index)).isoformat()
        row["conversation_id"] = f"golden-{index // 10 + 1:03d}"
        row["split"] = "train" if index < 350 else "validation" if index < 425 else "test"
        row["source"] = "curated_conversation_v2"
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
print(json.dumps({"path": str(output), "rows": len(rows), "train": 350, "validation": 75, "test": 75}, ensure_ascii=False))
