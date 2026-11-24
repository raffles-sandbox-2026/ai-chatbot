"""A small, dependency-free chat server. Run with Python 3.10+."""

import json
import os
import re
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


DEMO_DRINKS = {
    "teh tarik": "pulled milk tea",
    "kopi-o": "black coffee with sugar",
    "kopi-c": "coffee with evaporated milk and sugar",
    "teh-o": "tea without milk, with sugar",
    "teh-c": "tea with evaporated milk and sugar",
    "kopi": "coffee with condensed milk",
    "teh": "tea with condensed milk",
    "milo": "a chocolate malt drink",
    "bandung": "rose-syrup milk",
    "coffee": "a kopi break",
    "tea": "a tea break",
}
DEMO_FOOD = {
    "kaya toast": "Crispy toast, kaya and butter. Add soft-boiled eggs, breakfast settle.",
    "roti prata": "Crispy prata and curry. Eat while hot, not after your photo shoot lah.",
    "chicken rice": "Fragrant rice, chicken and chilli on the side. Simple, no need overthink.",
    "nasi lemak": "Coconut rice, sambal and the usual sides. Ask the stall what comes with it.",
    "laksa": "Spicy coconut broth and noodles. Wear white shirt then regret, hor.",
    "mee goreng": "Fried noodles, hot from the wok. Ask about the chilli before acting hero.",
    "prata": "Prata and curry. Eat while hot, not after your photo shoot lah.",
    "toast": "Toast first, gossip later. Cold toast not worth arguing over.",
}


def demo_item(text):
    """Recognize a small explicit demo menu, not arbitrary intent or real orders."""
    for kind, menu in (("drink", DEMO_DRINKS), ("food", DEMO_FOOD)):
        for item in menu:
            pattern = r"\b" + re.escape(item).replace(r"\-", "[- ]").replace(r"\ ", r"\s+") + r"\b"
            if re.search(pattern, text, re.I):
                return kind, item
    return None


def demo_reply(messages):
    """Scripted responses exercise the interface without an API key or AI claims."""
    prompt = messages[-1]["content"].lower()
    words = set(re.findall(r"[a-z]+", prompt))
    note = "\n\nThis is a scripted demo, not a live AI reply."
    named_item = demo_item(prompt)
    previous_item = next((item for m in reversed(messages[:-1]) if m["role"] == "user"
                          and (item := demo_item(m["content"]))), None)
    order = named_item or previous_item
    roast_coffee = bool(words & {"kopi", "coffee"} and words & {"roast", "dollar", "dollars", "expensive"})
    if order and not roast_coffee:
        kind, item = order
        order_note = note + " No real orders are placed."
        if kind == "drink":
            if words & {"sugar", "sweet", "sweetness", "kosong"} or "siew dai" in prompt:
                if "kosong" in words or re.search(r"\b(?:no|without|zero)\s+(?:any\s+|added\s+)?sugar\b", prompt):
                    advice = ("Ask for no added sugar. For milk drinks, ask about unsweetened milk too; "
                              "condensed milk, Milo powder and syrups can already contain sugar.")
                elif re.search(r"\b(?:more|extra)\s+(?:added\s+)?sugar\b|\bsweeter\b|\bmore sweet\b", prompt):
                    advice = "Sweeter, ah? Ask for more sugar or sweetened milk, a little at a time. Don't blame Uncle if too jelak."
                elif "less" in words or "siew dai" in prompt:
                    already_less = any("less sweet" in m["content"].lower() or "siew dai" in m["content"].lower()
                                       for m in messages[:-1] if m["role"] == "user")
                    advice = ("Even less sweet now ah? " if already_less else "Less sweet means siew dai, hor. ")
                    advice += ("Ask for less condensed milk" if item in {"teh tarik", "kopi", "teh"}
                               else "Ask the stall to reduce the sugar or sweetened ingredients")
                    advice += "; say how little you want. Uncle cannot read your sugar tolerance lah."
                else:
                    advice = "How sweet you want? Say less sweet (siew dai), no added sugar, or sweeter. Uncle not a mind reader lah."
                return f"For your {item}: {advice}" + order_note
            if words & {"ice", "iced", "cold", "hot", "peng"}:
                temperature = "iced (peng)" if words & {"ice", "iced", "cold", "peng"} else "hot"
                return (f"Your {item}, {temperature}. Say that at the stall, can already. "
                        "Temperature change only — don't anyhow change the sugar order too.") + order_note
            if named_item:
                return (f"{item.capitalize()} — {DEMO_DRINKS[item]}. Can lah. "
                        "Tell the stall if you want less sweet or iced. "
                        "Order one drink also need committee meeting is it?") + order_note
        else:
            if words & {"spicy", "chilli", "chili", "sambal"}:
                return (f"For your {item}, ask for chilli or sambal on the side, less spicy if possible. "
                        "Some curry and broth already spicy before you add anything, hor. "
                        "Don't act hero then drink everybody's water.") + order_note
            if named_item:
                return f"{item.capitalize()}, can. {DEMO_FOOD[item]}" + order_note
        if not named_item and words & {"another", "more", "two", "second"}:
            return (f"Another {item}? Can, but tell the stall the quantity properly. "
                    "Uncle gives commentary, not free refills.") + order_note
    if roast_coffee:
        return (
            "Eight-dollar kopi? Wah, inside got gold bar is it? Uncle hear already also heart pain.\n\n"
            "Go downstairs, order kopi-o kosong if you want black, no sugar. Add kaya toast "
            "and soft-boiled eggs, settle. Your wallet also can breathe a bit lah."
        ) + note
    if words & {"work", "boss", "sian", "meeting", "job"}:
        return (
            "Another meeting? Your boss collecting meetings like loyalty points ah?\n\n"
            "Ask one thing first: what decision we making? If nobody can answer, "
            "ask whether a short message can settle it. Don't quietly suffer then "
            "complain to your kopi lah. Kopi cannot approve your leave."
        ) + note
    if words & {"singlish", "shiok", "lah", "teach", "explain"}:
        return (
            "Singlish not just English then sprinkle 'lah' like pepper, hor. Got rhythm one.\n\n"
            "'Can' means yes. 'Can or not?' means possible? 'Can lah' means can, "
            "don't worry so much. 'Can meh?' means Uncle got doubts about your grand plan.\n\n"
            "See? One word, so many jobs. More hardworking than some people."
        ) + note
    if words & {"lunch", "food", "eat", "makan"}:
        return ("Hungry then go makan lah, don't stare at the menu until dinner. "
                "Kaya toast for a light bite, chicken rice if you want a meal. "
                "Tell Uncle which one — at least this argument got a useful ending.") + note
    if previous_item:
        kind, item = previous_item
        options = "less sweet, no added sugar, hot or iced" if kind == "drink" else "chilli on the side or another portion"
        return (f"Still on your {item}, hor. In this little demo, try asking for {options}. "
                "Other questions need the live AI connection — Uncle won't pretend to understand everything.") + note
    if len(messages) > 1:
        first = messages[0]["content"][:180]
        return (f'Aiyoh, we started with “{first}”. Uncle got listen lah. '
                "This demo only knows a small menu of fixed replies, not how to reason about every follow-up. "
                "Try a drink order, work complaint, or Singlish question.") + note
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
