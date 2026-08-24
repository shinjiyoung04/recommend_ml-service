import argparse
import asyncio
import json
from pathlib import Path
from .collectors import collect_kobis, collect_tmdb, enrich_tmdb_person_credits
from .config import settings
from .models import ModelBundle, evaluate_for_deployment
from .integration import integrate_kobis
from .storage import JsonStore
from .chat_dataset import MOVIES, write_chat_dataset
from .chat_evaluation import run_chat_evaluation
from .database import MeetupDatabase, MySQLMeetupDatabase
from .feedback import feedback_readiness
from .schemas import Movie


def main():
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect"); collect.add_argument("source", choices=["tmdb", "kobis"]); collect.add_argument("--pages", type=int, default=1); collect.add_argument("--incremental", action="store_true"); collect.add_argument("--with-english", action="store_true")
    person_sync = sub.add_parser("sync-person-ids")
    person_sync.add_argument("--limit", type=int)
    person_sync.add_argument("--checkpoint-every", type=int, default=250)
    person_sync.add_argument("--concurrency", type=int, default=2)
    integrate = sub.add_parser("integrate-kobis"); integrate.add_argument("--threshold", type=float, default=.78)
    train = sub.add_parser("train"); train.add_argument("--skip-evaluation", action="store_true")
    chat_data = sub.add_parser("build-chat-dataset"); chat_data.add_argument("--size", type=int, default=3000); chat_data.add_argument("--output", type=Path, default=Path("datasets/chat_labeled_3000.jsonl"))
    chat_eval = sub.add_parser("evaluate-chat"); chat_eval.add_argument("--dataset", type=Path, default=Path("datasets/chat_labeled_3000.jsonl")); chat_eval.add_argument("--output-dir", type=Path, default=Path("evaluation"))
    sub.add_parser("feedback-readiness")
    sub.add_parser("evaluate"); sub.add_parser("sample")
    args = parser.parse_args(); store = JsonStore(settings.meetup_data_dir)
    if args.command == "collect":
        rows = asyncio.run(collect_tmdb(store, args.pages, args.incremental, args.with_english) if args.source == "tmdb" else collect_kobis(store, args.pages)); print(json.dumps({"count": len(rows)}))
    elif args.command == "sync-person-ids":
        print(json.dumps(asyncio.run(enrich_tmdb_person_credits(
            store, args.limit, args.checkpoint_every, args.concurrency,
        )), ensure_ascii=False, indent=2))
    elif args.command == "integrate-kobis":
        print(json.dumps(integrate_kobis(store, args.threshold), ensure_ascii=False, indent=2))
    elif args.command == "build-chat-dataset":
        print(json.dumps(write_chat_dataset(args.output, args.size), ensure_ascii=False, indent=2))
    elif args.command == "evaluate-chat":
        evaluation_movies = [Movie(internal_id=f"eval-{index}", title=title) for index, title in enumerate(MOVIES)]
        print(json.dumps(run_chat_evaluation(args.dataset, evaluation_movies, args.output_dir), ensure_ascii=False, indent=2))
    elif args.command == "feedback-readiness":
        database = (MySQLMeetupDatabase(settings.meetup_mysql_host, settings.meetup_mysql_port, settings.meetup_mysql_database,
                    settings.meetup_mysql_user, settings.meetup_mysql_password) if settings.meetup_db_backend == "mysql" else MeetupDatabase(settings.meetup_db_path))
        print(json.dumps(feedback_readiness(database.recommendation_events()), ensure_ascii=False, indent=2))
    elif args.command in {"train", "evaluate"}:
        movies = [movie for movie in store.load_movies() if movie.recommendation_eligible]; bundle = ModelBundle(); report = bundle.fit(movies)
        metrics = guardrail = None
        if not (args.command == "train" and args.skip_evaluation):
            metrics, guardrail = evaluate_for_deployment(bundle, movies)
        bundle.save(settings.meetup_model_dir / "current.joblib"); print(json.dumps({**report, "metrics": metrics, "deployment_guardrail": guardrail}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"movies": len(store.load_movies()), "status": "fixture-ready"}))


if __name__ == "__main__": main()
