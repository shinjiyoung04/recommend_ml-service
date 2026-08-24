import json
from pathlib import Path

from meetup_ml.catalog_integrity import freeze_catalog

print(json.dumps(freeze_catalog(Path("data/normalized")), ensure_ascii=False, indent=2))
