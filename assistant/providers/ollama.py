import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.conf import settings


class ProviderUnavailable(Exception):
    pass


def chat(messages):
    endpoint = settings.CARELINK_OLLAMA_URL
    try:
        parsed = urlparse(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise ProviderUnavailable("The configured local Ollama endpoint is invalid.") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or port not in {None, 11434}
        or parsed.path != "/api/chat"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderUnavailable("The configured model endpoint must be a local Ollama service.")

    payload = json.dumps(
        {
            "model": settings.CARELINK_AI_MODEL,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 350},
        }
    ).encode("utf-8")
    request = Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.CARELINK_AI_TIMEOUT) as response:
            result = json.loads(response.read(1_000_000).decode("utf-8"))
    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ProviderUnavailable("The local AI model could not be reached.") from exc

    try:
        content = result["message"]["content"]
    except (TypeError, KeyError) as exc:
        raise ProviderUnavailable("The local AI model returned an invalid response.") from exc
    if not isinstance(content, str) or not content.strip():
        raise ProviderUnavailable("The local AI model returned an empty response.")
    return content.strip()
