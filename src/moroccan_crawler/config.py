from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Moroccan Business Intelligence Graph"
    nvidia_api_key: str | None = None
    nvidia_model: str = "mistralai/mistral-large-4-1t-a52b"
    # Serving model for extraction. The reasoning-heavy ``nvidia_model`` spends
    # its whole token budget on hidden reasoning (~100s and often no answer), so
    # extraction runs on a fast instruct model with thinking disabled instead.
    nvidia_extraction_model: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    nvidia_disable_thinking: bool = True
    nvidia_embedding_model: str = "nvidia/nemotron-3-embed-1b"
    nvidia_enable_remote_ai: bool = False
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_timeout_seconds: float = 90
    nvidia_min_request_interval: float = 3
    nvidia_max_attempts: int = 4
    # Transient throttling (429) backs off as base * 2**attempt, so a provider
    # window of tens of seconds recovers instead of dropping the chunk. Attempt
    # count is capped so the worst-case cooldown stays under the 60s guard.
    nvidia_retry_base_seconds: float = 5
    shared_rate_limit_path: str = "data/provider_rate_limits.json"
    # Completed LLM extractions are cached so interrupted jobs resume and repeat
    # cycles are not re-billed. Only successful extractions are stored.
    extraction_cache_enabled: bool = True
    extraction_cache_path: str = "data/extraction_cache.jsonl"
    extraction_retry_queue_path: str = "data/extraction_retry_queue.json"
    extraction_retry_base_seconds: float = 60
    extraction_retry_max_seconds: float = 1800
    extraction_max_new_calls_per_run: int = 25
    # Mistral is the default entity/relation extractor; NVIDIA is reserved for
    # embeddings and answer generation unless explicitly overridden.
    extraction_provider: Literal["nvidia", "mistral", "heuristic"] = "mistral"
    mistral_api_key: str | None = None
    mistral_api_url: str = "https://api.mistral.ai/v1"
    mistral_api_model: str = "mistral-small-latest"
    mistral_disable_thinking: bool = True
    mistral_timeout_seconds: float = 90
    mistral_min_request_interval: float = 3
    mistral_max_attempts: int = 4
    neo4j_uri: str | None = None
    neo4j_username: str | None = None
    neo4j_password: str | None = None
    neo4j_enabled: bool = False
    qdrant_enabled: bool = False
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "moroccan_business_chunks_nemotron"
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    include_local_fixtures: bool = False
    # Raw-zone storage: WebHDFS when enabled, local filesystem otherwise.
    hdfs_enabled: bool = False
    hdfs_url: str = "http://localhost:9870"
    hdfs_user: str = "hdfs"
    hdfs_root: str = "/user/hdfs/moroccan-business"
    hdfs_fallback_root: str = "data/raw"
    # Distributed ETL: Spark when enabled, pure Python otherwise.
    spark_enabled: bool = False
    spark_master: str = "local[*]"
    ingest_api_url: str = "http://api:8000"
