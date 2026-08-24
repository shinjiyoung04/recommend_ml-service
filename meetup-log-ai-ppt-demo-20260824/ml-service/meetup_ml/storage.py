import json
import os
import tempfile
from pathlib import Path

from .schemas import Movie


class JsonStore:
    def __init__(self, root: Path):
        self.root = root
        self.raw = root / "raw"
        self.normalized = root / "normalized"
        self.state = root / "state"

        for path in (
            self.raw,
            self.normalized,
            self.state,
        ):
            path.mkdir(
                parents=True,
                exist_ok=True,
            )

    def append_jsonl(
        self,
        path: Path,
        row: dict,
    ) -> None:
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with path.open(
            "a",
            encoding="utf-8",
        ) as stream:
            stream.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )

    def save_movies(
        self,
        movies: list[Movie],
    ) -> Path:
        target = (
            self.normalized
            / "movies.json"
        )

        self._write_json_atomic(
            target,
            [movie.model_dump() for movie in movies],
        )

        # Build a searchable actor/director registry from every collected title.
        # No nationality filter is applied: Korean and international credits are
        # preserved together, with TMDB IDs and original-name aliases when present.
        people: dict[str, dict] = {}
        for movie in movies:
            credits = [
                *movie.cast_people,
                *movie.director_people,
            ]
            if not credits:
                credits = [
                    *({"name": name, "role": "ACTOR"} for name in movie.cast),
                    *({"name": name, "role": "DIRECTOR"} for name in movie.directors),
                ]
            for credit in credits:
                row = credit if isinstance(credit, dict) else credit.model_dump()
                name = row.get("name")
                if not name:
                    continue
                key = str(row.get("person_id") or f"{row.get('role')}:{name.casefold()}")
                person = people.setdefault(key, {
                    "person_id": row.get("person_id"), "name": name,
                    "original_name": row.get("original_name"), "role": row.get("role"),
                    "aliases": [], "movie_ids": [],
                })
                person["aliases"] = list(dict.fromkeys([
                    *person["aliases"], name, row.get("original_name"),
                ]))
                person["aliases"] = [value for value in person["aliases"] if value]
                person["movie_ids"].append(movie.internal_id)
        self._write_json_atomic(
            self.normalized / "people.json",
            list(people.values()),
        )

        return target

    @staticmethod
    def _write_json_atomic(target: Path, payload) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, target)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def load_movies(
        self,
        use_fixture: bool = True,
    ) -> list[Movie]:
        default_target = (
            self.normalized
            / "movies.json"
        )

        target = default_target

        if not target.exists():
            if not use_fixture:
                return []

            target = (
                Path(__file__).parents[1]
                / "fixtures"
                / "movies.json"
            )

        rows = json.loads(
            target.read_text(
                encoding="utf-8",
            )
        )

        return [
            Movie.model_validate(row)
            for row in rows
        ]
