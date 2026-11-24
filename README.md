# AI chatbot

A small, dependency-free chatbot starter: a responsive chat page, local conversation history, and a Python server with an optional OpenAI connection.

## Run it

Requires Python 3.10 or newer. No package install or frontend build is needed.

```sh
python3 server.py
```

Open `http://127.0.0.1:8000`. The default is **demo mode**, with clearly labelled scripted replies. It works without credentials and does not call an AI service.

For a private Devin browser preview, run `HOST=0.0.0.0 python3 server.py` and expose port 8000 with the authenticated preview tool. Do not expose this starter directly to the public internet.

## Connect real AI

Set environment variables on the **server**, then restart it:

```sh
export OPENAI_API_KEY='your-api-key'
export OPENAI_MODEL='gpt-4.1-mini' # optional
python3 server.py
```

The server reads exported environment variables, not `.env` files. `.env.example` lists the available settings; do not commit keys. `HOST` defaults to `127.0.0.1` and `PORT` to `8000`.

The server uses the [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses/create). Keys never go to the browser. Recent messages are sent on each request, with `store: false`; upstream data handling still follows your OpenAI account's policies. API usage is billed to the key's owner. Failed AI requests show an error rather than silently falling back to demo replies.

## What works

- Send messages with Enter or the send button; Shift+Enter inserts a newline.
- Try starter prompts, stop a pending response, and retry an unsuccessful message.
- Start, revisit, and delete conversations. The last 20 chats are kept in browser local storage, with up to 40 recent messages per chat.
- Switch to live AI by configuring the server. This is request/response chat, not token streaming.
- Use keyboard navigation and a responsive layout. On small screens, New chat and Delete chat remain available; the saved-history sidebar is desktop-only.

Messages render as plain text, not HTML or Markdown, so untrusted content cannot inject markup. There is no server-side chat database, file upload, account system, or telemetry. Browser storage is not encrypted; don't use shared browsers for sensitive chats. Demo messages aren't sent to any external service.

## Checks

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q server.py tests
```

GitHub Actions runs these checks on pull requests and pushes to main. No pre-commit hooks are configured.

## Project layout and decisions

- `server.py`: allowlisted static assets, input validation, scripted demo, and server-side OpenAI calls.
- `static/`: vanilla HTML, CSS, and JavaScript. No Node.js toolchain or third-party runtime dependencies.
- `tests/`: HTTP integration and mocked upstream tests; no paid API calls.

This first version uses a quiet workbench layout and neutral/blue fallback design tokens; the blank repository had no existing brand assets or design system. Keep this branch unmerged to preserve the blank main branch until you're ready.

The Python standard-library HTTP server is intended for local development and an access-controlled preview. Before a public deployment, use a production server and add authentication, abuse/rate controls, and a deliberate data-retention policy.
