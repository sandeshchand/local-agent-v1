from __future__ import annotations

from app.bootstrap import bootstrap_app
from app.cli import build_parser, run_ask, run_ingest,run_list_docs


def main() ->None:
    parser= build_parser()
    args = parser.parse_args()

    deps = bootstrap_app(".env")

    if args.command == "ingest":
        run_ingest(deps, args.path)
    elif args.command == "ask":
        run_ask(deps, args.query)
    elif args.command == "list-docs":
        run_list_docs(deps)
    else:
        raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()

