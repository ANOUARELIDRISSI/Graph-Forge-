# Evaluation data

`navigation_cases.jsonl` contains four agent-authored English/French source-finding
questions linked to document titles in the official corpus. The questions are
written separately from the automatic first-12-token smoke signatures. They test
navigation, not answer correctness or multi-hop reasoning. Their single expected
URL can omit other relevant pages. They require human review before being used
as an independent benchmark. Do not tune retrieval on them and call them held-out.

Run from the repository root with `PYTHONPATH=src`:

```text
uv run --no-sync python scripts/evaluate_rag.py --cases evaluation/navigation_cases.jsonl
uv run --no-sync python scripts/prepare_live_eval.py
uv run --no-sync python scripts/evaluate_ragas.py
```

The first command defaults to offline embeddings/generation. The latter commands
capture a real NVIDIA-generated answer and judge its retrieved passages. A one-row
Ragas diagnostic is useful for integration verification, not a corpus-wide score.
Independent evaluation still needs reviewed factual references, extraction labels,
multi-hop questions, unanswerable questions and direct Cypher comparison.
