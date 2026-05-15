from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str

    victoriametrics_url: str = "http://victoriametrics:8428"

    qdrant_url: str = "http://qdrant:6333"

    redis_url: str = "redis://localhost:6379"
    simulation_cache_ttl_seconds: int = 3600  # 1 hour default TTL

    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_llm_model: str = "llama3.1:8b"

    log_level: str = "INFO"
    dr_rto_threshold_minutes: int = 60
    dr_rpo_threshold_minutes: int = 15

    class Config:
        env_file = ".env"
        extra = "ignore"
