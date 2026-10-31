import importlib.util
from pathlib import Path


def test_document_metrics_deduplicate_chunks():
    path = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_rag.py"
    spec = importlib.util.spec_from_file_location("evaluate_rag", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.rank_metrics(["a", "a", "a", "a", "a", "b"], "b")
    assert result["recall"] == 1.0
    assert result["rr"] == 0.5
