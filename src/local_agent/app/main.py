from __future__ import annotations

from local_agent.app.bootstrap import bootstrap_app
from local_agent.app.cli import build_parser, run_ask, run_ingest, run_list_docs, run_list_memory, run_remember


def main() ->None:
    parser= build_parser()
    args = parser.parse_args()

    deps = bootstrap_app(".env")

    if args.command == "ingest":
        run_ingest(deps, args.path)
    elif args.command == "ask":
        run_ask(deps, args.query, approved_tools=args.approve_tool)
    elif args.command == "list-docs":
        run_list_docs(deps)
    elif args.command == "remember":
        run_remember(
            deps,
            content=args.content,
            kind=args.kind,
            scope=args.scope,
            session_id=args.session_id,
            importance=args.importance,
        )
    elif args.command == "list-memory":
        run_list_memory(deps, session_id=args.session_id, limit=args.limit)
    else:
        raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()

