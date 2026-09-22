"""Central configuration for Pihu-BreakThough.

All secrets come from environment variables. No provider is mandatory except
that at least one AI provider must be configured for cloud responses.
"""

import os


APP_NAME = "Pihu-BreakThough"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
HF_API_KEY = os.getenv("HF_API_KEY", "").strip()

# Optional OpenAI-compatible providers. Keep these disabled unless explicitly configured.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "").strip()

# Local provider is optional. Pihu must work without the user's PC being online.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()

# Free-only safety rule. The application never attempts paid fallbacks.
FREE_ONLY = os.getenv("PIHU_FREE_ONLY", "true").lower() == "true"

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
HF_MODEL = os.getenv("HF_MODEL", "").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b").strip()

REQUEST_TIMEOUT_SECONDS = float(os.getenv("PIHU_REQUEST_TIMEOUT", "30"))
