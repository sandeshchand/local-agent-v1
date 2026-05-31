from app.paths import (
    DEFAULT_QDRANT_PATH,
    DEFAULT_SQLITE_PATH,
    EVAL_CANDIDATES_PATH,
    GOLD_EVAL_PATH,
    GOLD_QA_DIR,
    LOGS_DIR,
    PROJECT_ROOT,
    VAR_DIR,
)


def test_gold_qa_path_is_in_benchmarks() -> None:
    assert GOLD_QA_DIR == PROJECT_ROOT / "benchmarks" / "gold_qa"
    assert GOLD_EVAL_PATH == GOLD_QA_DIR / "eval_multi_doc_rag.json"


def test_eval_candidate_path_is_in_data_evals() -> None:
    assert EVAL_CANDIDATES_PATH == PROJECT_ROOT / "data" / "evals" / "feedback_eval_candidates.json"


def test_runtime_paths_are_under_var() -> None:
    assert VAR_DIR == PROJECT_ROOT / "var"
    assert DEFAULT_SQLITE_PATH == VAR_DIR / "sqlite" / "app.db"
    assert DEFAULT_QDRANT_PATH == VAR_DIR / "qdrant"
    assert LOGS_DIR == VAR_DIR / "logs"
