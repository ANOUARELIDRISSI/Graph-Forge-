"""Run Ragas when the evaluation dependency group is installed."""

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full", action="store_true", help="Also evaluate answer relevance with embeddings"
    )
    args = parser.parse_args()
    try:
        from langchain_core.rate_limiters import InMemoryRateLimiter
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from ragas import EvaluationDataset, evaluate
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import AnswerRelevancy, Faithfulness, LLMContextPrecisionWithoutReference
        from ragas.run_config import RunConfig

        from moroccan_crawler.config import Settings
    except ImportError as error:
        raise SystemExit(
            "Install evaluation dependencies with: uv sync --group evaluation"
        ) from error
    rows = [
        json.loads(line)
        for line in Path("data/eval_dataset.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    dataset = EvaluationDataset.from_pandas(__import__("pandas").DataFrame(rows))
    settings = Settings()
    if not settings.nvidia_api_key:
        raise SystemExit("Set NVIDIA_API_KEY in .env before running Ragas evaluation")
    llm = LangchainLLMWrapper(
        ChatOpenAI(
            model=settings.nvidia_model,
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
            temperature=0,
            max_tokens=8192,
            timeout=90,
            max_retries=0,
            rate_limiter=InMemoryRateLimiter(requests_per_second=0.5, max_bucket_size=1),
        )
    )
    embeddings = OpenAIEmbeddings(
        model=settings.nvidia_embedding_model,
        api_key=settings.nvidia_api_key,
        base_url=settings.nvidia_base_url,
    )
    result = evaluate(
        dataset,
        metrics=(
            [Faithfulness(), AnswerRelevancy(), LLMContextPrecisionWithoutReference()]
            if args.full
            else [Faithfulness(), LLMContextPrecisionWithoutReference()]
        ),
        llm=llm,
        embeddings=embeddings,
        run_config=RunConfig(timeout=120, max_workers=1, max_retries=0),
    )
    frame = result.to_pandas()
    metric_columns = [
        name
        for name in ("faithfulness", "answer_relevancy", "llm_context_precision_without_reference")
        if name in frame.columns
    ]
    if not metric_columns or frame[metric_columns].isna().any().any():
        raise SystemExit(
            "Ragas returned missing/failed scores; no successful results file was written"
        )
    Path("data/ragas_results.json").write_text(
        json.dumps(frame.to_dict(orient="records"), indent=2, allow_nan=False), encoding="utf-8"
    )
    print(result)


if __name__ == "__main__":
    main()
