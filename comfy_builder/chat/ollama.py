"""Ollama REST API client (stdlib-only)."""

import json
import os
import urllib.request
import urllib.error

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "300"))  # seconds (first run / tool use can be slow)


def check() -> dict:
    """Check if Ollama is reachable and list available models."""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        names = [m.get("name", "") for m in data.get("models", [])]
        return {"online": True, "models": names, "url": OLLAMA_URL}
    except Exception as e:
        return {"online": False, "error": str(e), "url": OLLAMA_URL}


def chat(messages: list[dict], tools: list[dict] | None = None,
         model: str | None = None) -> dict:
    """Send a chat request to Ollama. Returns the full response (non-streaming).

    Args:
        messages: List of {role, content} dicts.
        tools: Optional list of tool definitions (Ollama tool-calling format).
        model: Model name override.

    Returns:
        Parsed response dict with 'message' key containing {role, content, tool_calls}.
    """
    body = {
        "model": model or OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }
    if tools:
        body["tools"] = tools

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        return {"error": f"HTTP {e.code}: {error_body}"}
    except urllib.error.URLError as e:
        return {"error": f"Connection failed: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def chat_stream(messages: list[dict], tools: list[dict] | None = None,
                model: str | None = None):
    """Send a streaming chat request. Yields parsed JSON chunks.

    Each chunk has a 'message' with partial 'content'.
    The final chunk has 'done': true.
    """
    body = {
        "model": model or OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
    }
    if tools:
        body["tools"] = tools

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT)
        for line in resp:
            line = line.decode().strip()
            if line:
                yield json.loads(line)
        resp.close()
    except Exception as e:
        yield {"error": str(e), "done": True}
