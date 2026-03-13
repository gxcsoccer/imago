from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "IMAGO_", "env_file": ".env"}

    # Server
    host: str = "0.0.0.0"
    port: int = 8420

    # FLUX model
    model: str = "schnell"
    steps: int = 4
    width: int = 1024
    height: int = 1024
    quantize: int | None = 8

    # Output
    output_dir: Path = Path("./output")

    # LLM provider: "claude" | "bailian" | "qwen"
    llm_provider: str = "bailian"

    # Claude
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # Bailian (Alibaba Cloud DashScope, OpenAI-compatible)
    bailian_api_key: str = ""
    bailian_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    bailian_model: str = "qwen3.5-plus"

    # Qwen via Ollama
    ollama_base_url: str = "http://localhost:11434/v1"
    qwen_model: str = "qwen2.5:14b"

    # Model lifecycle
    idle_timeout: int = 300  # seconds before unloading model from memory (0 = never)

    # Feishu (M4)
    feishu_webhook_url: str = ""


settings = Settings()
