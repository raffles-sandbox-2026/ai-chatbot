"""A small, dependency-free chat server. Run with Python 3.10+."""

import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

STATIC = Path(__file__).parent / "static"
# Covers 40 × 4,000 codepoints even with JSON's surrogate-pair escaping.
MAX_BODY = 2_000_000
MAX_MESSAGES = 40
MAX_CONTENT = 4_000
SYSTEM_PROMPT = """You are Uncle, a fictional grumpy but good-hearted Singaporean kopitiam uncle.
Chat with the user in heavy, natural Singlish: local rhythm, clipped grammar, and phrases
like aiyoh, alamak, walao, can or not, don't anyhow, lah, leh, lor and sia where they fit.
Don't just append 'lah' to standard English, and don't turn every sentence into a catchphrase.
You have strong opinions about kopi, food, work and everyday life. Be somewhat rude:
tease the user's choices, grumble, give cheeky roasts and blunt, actually useful advice.
Keep the warmth underneath; you are not cruel. No slurs, hateful stereotypes or threats.
If someone is distressed or needs serious help, drop the roasting and respond with care.
Stay conversational, usually one to three short paragraphs, and remember the recent chat.
You are an AI character, not a real person; don't claim real-world experiences or actions.
Answer the actual question rather than repeating a fixed introduction or advertising the app."""
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/uncle.svg": ("uncle.svg", "image/svg+xml"),
}


def connection_config():
    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        return "live", "claude"
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "live", "openai"
    return "demo", "demo"


def validate_messages(payload):
    if not isinstance(payload, dict):
        raise ValueError("Send an object containing messages.")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= MAX_MESSAGES:
        raise ValueError(f"Send between 1 and {MAX_MESSAGES} messages.")
    clean = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ValueError("Each message must contain a role and text.")
        expected = "user" if index % 2 == 0 else "assistant"
        content = message.get("content")
        if message.get("role") != expected:
            raise ValueError("Messages must alternate between user and assistant.")
        if not isinstance(content, str) or not content.strip() or len(content) > MAX_CONTENT:
            raise ValueError(f"Each message must contain 1–{MAX_CONTENT} characters.")
        clean.append({"role": expected, "content": content.strip()})
    if clean[-1]["role"] != "user":
        raise ValueError("The last message must be from the user.")
    return clean


def demo_reply(messages):
    """Scripted responses exercise the interface without an API key or AI claims."""
    prompt = messages[-1]["content"].lower()
    note = "\n\nThis is a scripted demo, not a live AI reply."
    if len(messages) > 1:
        first = messages[0]["content"][:180]
        return (
            f'Aiyoh, just now you say “{first}”, now got follow-up already ah? '
            "Uncle got listen lah.\n\nBut this demo only got fixed lines — cannot actually "
            "think about your follow-up yet. Connect the AI, then we properly lim kopi and talk."
        ) + note
    if any(word in prompt for word in ("kopi", "coffee", "lunch", "food", "eat")):
        return (
            "Eight-dollar kopi? Wah, inside got gold bar is it? Uncle hear already also heart pain.\n\n"
            "Go downstairs, order kopi-o kosong if you want black, no sugar. Add kaya toast "
            "and soft-boiled eggs, settle. Your wallet also can breathe a bit lah."
        ) + note
    if any(word in prompt for word in ("work", "boss", "sian", "meeting", "job")):
        return (
            "Another meeting? Your boss collecting meetings like loyalty points ah?\n\n"
            "Ask one thing first: what decision we making? If nobody can answer, "
            "ask whether a short message can settle it. Don't quietly suffer then "
            "complain to your kopi lah. Kopi cannot approve your leave."
        ) + note
    if any(word in prompt for word in ("singlish", "shiok", "lah", "teach", "explain")):
        return (
            "Singlish not just English then sprinkle 'lah' like pepper, hor. Got rhythm one.\n\n"
            "'Can' means yes. 'Can or not?' means possible? 'Can lah' means can, "
            "don't worry so much. 'Can meh?' means Uncle got doubts about your grand plan.\n\n"
            "See? One word, so many jobs. More hardworking than some people."
        ) + note
    return (
        "Eh, come sit lah. Stand there for what, you blocking the fan.\n\n"
        "Uncle got kopi, strong opinions, and absolutely no customer-service training. "
        "Want complain about work, talk makan, or learn some Singlish? Faster ask. "
        "Kopi getting cold already."
    ) + note


def ai_reply(messages, api_key):
    request = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps({
            "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            "instructions": SYSTEM_PROMPT,
            "input": messages,
            "max_output_tokens": 800,
            "store": False,
        }).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        result = json.loads(response.read(1_000_000))
    parts = [
        part.get("text") if part.get("type") == "output_text" else part["refusal"]
        for item in result.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if (part.get("type") == "output_text" and isinstance(part.get("text"), str))
        or (part.get("type") == "refusal" and isinstance(part.get("refusal"), str))
    ]
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("The AI returned no text. Try rephrasing your message.")
    return text[:MAX_CONTENT]


def claude_reply(messages, api_key):
    request = Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({
            "model": os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"),
            "system": SYSTEM_PROMPT,
            "messages": messages,
            "max_tokens": 800,
        }).encode(),
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        result = json.loads(response.read(1_000_000))
    text = "\n".join(part["text"] for part in result.get("content", [])
                     if part.get("type") == "text" and isinstance(part.get("text"), str)).strip()
    if not text:
        raise ValueError("Claude returned no text.")
    return text[:MAX_CONTENT]


class ChatHandler(BaseHTTPRequestHandler):
    # Bound read time as well as the upstream AI timeout.
    def setup(self):
        super().setup()
        self.connection.settimeout(40)

    def log_message(self, format, *args):
        # Do not log prompts, credentials, request paths, or upstream errors.
        pass

    def send_content(self, status, data, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json(self, status, payload):
        self.send_content(status, json.dumps(payload).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/config":
            mode, provider = connection_config()
            self.send_json(200, {"mode": mode, "provider": provider, "maxContent": MAX_CONTENT})
        elif path in ASSETS:
            filename, mime = ASSETS[path]
            self.send_content(200, (STATIC / filename).read_bytes(), mime)
        else:
            self.send_json(404, {"error": "Not found."})

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_json(404, {"error": "Not found."})
            return
        # JSON requests require preflight cross-origin; no CORS permission is granted.
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "Use application/json."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                self.send_json(413, {"error": "Your conversation is too large. Start a new chat."})
                return
            payload = json.loads(self.rfile.read(length))
            messages = validate_messages(payload)
        except (ValueError, UnicodeDecodeError) as error:
            message = str(error) if not isinstance(error, json.JSONDecodeError) else "Invalid JSON."
            self.send_json(400, {"error": message})
            return
        mode, provider = connection_config()
        if payload.get("mode") != mode or payload.get("provider") != provider:
            self.send_json(409, {"error": "The AI connection changed. Refresh the page before sending; live AI sends messages to the displayed provider."})
            return
        try:
            if provider == "claude":
                reply = claude_reply(messages, os.environ["ANTHROPIC_API_KEY"].strip())
            elif provider == "openai":
                reply = ai_reply(messages, os.environ["OPENAI_API_KEY"].strip())
            else:
                reply = demo_reply(messages)
            self.send_json(200, {"reply": reply, "mode": mode, "provider": provider})
        except HTTPError as error:
            status = 429 if error.code == 429 else 502
            message = "The AI is busy or its quota is exhausted. Please try again later." if status == 429 else "Couldn't reach the AI. The server owner may need to check the API configuration."
            self.send_json(status, {"error": message})
        except (TimeoutError, socket.timeout, URLError, ValueError, KeyError, TypeError):
            self.send_json(502, {"error": "The AI couldn't finish its reply. Please try again."})


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print(f"Chat server listening on {host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), ChatHandler).serve_forever()
