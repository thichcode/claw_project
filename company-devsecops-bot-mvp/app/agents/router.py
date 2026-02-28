from ..config import settings


def route_model(message: str) -> str:
    """
    MVP routing:
    - security/deploy keywords => azure for stronger reasoning
    - default => ollama local
    """
    msg = message.lower()
    if any(k in msg for k in ["deploy", "security", "policy", "incident", "production"]):
        return "azure:gpt-5-mini"
    return f"ollama:{settings.ollama_model}"
