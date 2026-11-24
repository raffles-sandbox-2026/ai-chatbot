"""A small, dependency-free chat server. Run with Python 3.10+."""

import json
import os
import socket
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

STATIC = Path(__file__).parent / "static"
# Covers 40 × 4,000 codepoints even with JSON's surrogate-pair escaping.
MAX_BODY = 2_000_000
MAX_MESSAGES = 40
MAX_CONTENT = 4_000
SYSTEM_PROMPT = "You are a helpful assistant. Be clear, thoughtful, and concise."
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}


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
    if len(messages) > 1:
        first = messages[0]["content"][:180]
        return (
            f'We started with: “{first}”. Your follow-up stays in this conversation.\n\n'
            "This preview uses scripted replies, so I can't reason about that follow-up yet. "
            "With an AI connection, the assistant receives this conversation's recent messages "
            "and can build on your earlier ideas."
        )
    if "brainstorm" in prompt or "idea" in prompt:
        return (
            "Here's a starting point for your next project:\n\n"
            "1. A reading companion that turns notes into questions.\n"
            "2. A meal planner built around what's in your fridge.\n"
            "3. A focused assistant for your team's frequently asked questions.\n\n"
            "Start with one person, one problem, and one useful conversation. "
            "What would you like to explore?\n\n"
            "This is a scripted demo response, not an AI-generated answer."
        )
    if "explain" in prompt or "learn" in prompt:
        return (
            "A good way to learn something new is to break it into three parts:\n\n"
            "• The idea: explain it in one plain sentence.\n"
            "• An example: connect it to something you already know.\n"
            "• A check: try explaining it back without your notes.\n\n"
            "Try a follow-up to see how conversations work. This is a scripted demo; "
            "connect an AI model for answers tailored to your question."
        )
    if "write" in prompt or "draft" in prompt:
        return (
            "Here's a simple template to get you started:\n\n"
            "Hi [name],\n\nI'm reaching out about [topic]. "
            "The main thing I'd love your input on is [question]. "
            "Would [next step] work for you?\n\nThanks,\n[your name]\n\n"
            "This is a scripted demo template. An AI connection will let you tailor "
            "the tone, details, and format to your request."
        )
    return (
        "Hello! This is your chatbot's first home. You can send messages, try a follow-up, "
        "and start a fresh conversation from the sidebar.\n\n"
        "I'm running in demo mode with scripted replies, not a live AI model. "
        "To get real answers, the server owner can connect an OpenAI API key. "
        "In the meantime, try one of the starter prompts to explore the experience."
    )


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
        part["text"]
        for item in result.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text" and isinstance(part.get("text"), str)
    ]
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("The AI returned no text. Try rephrasing your message.")
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
            is_live = bool(os.getenv("OPENAI_API_KEY", "").strip())
            self.send_json(200, {"mode": "live" if is_live else "demo", "maxContent": MAX_CONTENT})
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
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        mode = "live" if api_key else "demo"
        if payload.get("mode") != mode:
            self.send_json(409, {"error": "The connection mode changed. Refresh the page before sending; live AI sends your messages to OpenAI."})
            return
        try:
            reply = ai_reply(messages, api_key) if api_key else demo_reply(messages)
            self.send_json(200, {"reply": reply, "mode": "live" if api_key else "demo"})
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
