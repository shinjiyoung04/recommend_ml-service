"""Deterministic catalog and embedding revision checks."""

import hashlib
import json
from pathlib import Path


def canonical_content_hash(movies: list[dict], ordered_ids: list[str]) -> str:
    by_id = {movie["internal_id"]: movie for movie in movies}
    fields = ("internal_id", "title", "original_title", "genres", "keywords", "overview", "runtime", "release_date")
    rows = [{field: by_id[movie_id].get(field) for field in fields} for movie_id in ordered_ids]
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def freeze_catalog(data_dir: Path) -> dict:
    movies = json.loads((data_dir / "movies.json").read_text(encoding="utf-8"))
    manifest_path = data_dir / "catalog_manifest.json"
    metadata_path = data_dir / "movie_embeddings_meta.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    ordered_ids = manifest["ordered_movie_ids"]
    existing_revision = metadata.get("model_revision")
    artifact_revision = existing_revision if existing_revision and existing_revision != "unversioned" else f"artifact-sha256:{metadata['embeddings_sha256']}"
    revision = f"{metadata['model_name']}@{artifact_revision}"
    manifest["catalog_content_sha256"] = canonical_content_hash(movies, ordered_ids)
    manifest["embedding_model_revision"] = revision
    metadata["catalog_content_sha256"] = manifest["catalog_content_sha256"]
    metadata["model_revision"] = artifact_revision
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"movie_count": len(ordered_ids), "catalog_content_sha256": manifest["catalog_content_sha256"], "embedding_model_revision": revision}
