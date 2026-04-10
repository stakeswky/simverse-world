from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/skills_world"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    github_client_id: str = ""
    github_client_secret: str = ""
    anthropic_api_key: str = ""
    # Custom LLM endpoint (overrides anthropic_api_key if set)
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_default_model: str = "claude-haiku-4-5-20251001"
    llm_max_tokens: int = 512
    llm_thinking: bool = False  # disable thinking/reasoning for faster responses

    @property
    def effective_api_key(self) -> str:
        return self.llm_api_key or self.anthropic_api_key

    @property
    def effective_model(self) -> str:
        return self.llm_model or self.llm_default_model
    cors_origins: list[str] = ["http://localhost:5173"]

    # --- LinuxDo OAuth (Plan 1) ---
    linuxdo_client_id: str = ""
    linuxdo_client_secret: str = ""
    linuxdo_redirect_uri: str = ""
    linuxdo_min_trust_level: int = 0

    # --- Portrait LLM (Plan 1) ---
    portrait_llm_model: str = "gemini-3-pro-image-preview"
    portrait_llm_base_url: str = ""
    portrait_llm_api_key: str = ""
    portrait_llm_timeout: int = 180

    # --- System LLM advanced params (Plan 1) ---
    system_llm_temperature: float = 0.3
    system_llm_timeout: int = 30
    system_llm_max_retries: int = 2

    # --- User LLM advanced params (Plan 1) ---
    user_llm_temperature_chat: float = 0.7
    user_llm_temperature_forge: float = 0.5
    user_llm_timeout: int = 120
    user_llm_max_retries: int = 3
    user_llm_concurrency: int = 5

    # --- Media Upload (P2) ---
    media_upload_dir: str = "backend/static/uploads"
    media_max_image_size: int = 5 * 1024 * 1024   # 5 MB
    media_max_video_size: int = 50 * 1024 * 1024  # 50 MB
    video_llm_model: str = "kimi-k2.5"

    # --- SearXNG (research) ---
    searxng_url: str = "http://localhost:58080"

    allow_user_custom_llm: bool = False

    # --- Ollama (local embedding) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "qwen3-embedding:4b"
    ollama_embed_dimensions: int = 1024

    # --- Agent Loop ---
    agent_tick_interval: int = 60          # seconds between tick rounds
    agent_max_concurrent: int = 5          # max residents ticking in parallel
    agent_max_daily_actions: int = 20      # per-resident action cap per in-game day
    agent_chat_max_turns: int = 8          # max dialog turns in a resident-resident chat
    agent_chat_cooldown: int = 1800        # seconds before same pair can chat again
    agent_time_scale: float = 1.0          # world time multiplier (1.0 = realtime)
    agent_enabled: bool = True             # master switch (set False to pause loop)

    model_config = {"env_file": ".env"}


settings = Settings()
