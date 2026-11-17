import os

from openai import OpenAI


def local_client() -> OpenAI:
    # Bot generation uses the internal Compose hostname, not a remote provider.
    return OpenAI(base_url="http://ollama:11434/v1", api_key="ollama", timeout=120, max_retries=0)


def local_model() -> str:
    return os.environ.get("DEMO_LOCAL_MODEL", "qwen2.5:7b")
