import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

OUTPUT_ARTIGOS = os.path.join(BASE_DIR, "output/artigos")
