# ai-chatbot

A Phua Chu Kang chatbot web app — heavy Singlish, powered by Claude.

## Run it

```bash
export ANTHROPIC_API_KEY=sk-ant-...
npm start        # node server.mjs, then open http://localhost:3000
```

No dependencies — just Node 18+ and an Anthropic API key.

## Deploy (free hosts)

The app binds to `127.0.0.1` by default — on a host you must set `HOST=0.0.0.0`.
When it's public, also set `CHAT_PASSPHRASE`: visitors are asked for it once and
it gates `/api/chat` so strangers can't spend your quota.

**Render** — `render.yaml` is already in this repo:

1. Sign in at render.com → **New → Blueprint** → connect this repo.
2. When prompted, set `ANTHROPIC_API_KEY` (and `CHAT_PASSPHRASE` recommended).
3. Deploy. Free tier sleeps after ~15 min idle; first load after sleep takes ~30s.

**Railway** — no config file needed:

1. railway.app → **New Project → Deploy from GitHub repo** → pick this repo.
2. Variables: `ANTHROPIC_API_KEY`, `HOST=0.0.0.0`, `CHAT_PASSPHRASE` (recommended).
3. Railway runs `npm start` automatically and gives you a public URL.

## Config

See `.env.example`:

- `ANTHROPIC_API_KEY` (required)
- `CHAT_PASSPHRASE` (recommended when hosted publicly — gates `/api/chat`)
- `ANTHROPIC_MODEL` (default `claude-sonnet-4-5-20250929`)
- `CHAT_SYSTEM_PROMPT` (override the Chu Kang persona)
- `HOST` (default `127.0.0.1`)
- `PORT` (default `3000`)

## API

`POST /api/chat` — body `{"messages": [{role, content}, ...]}`, streams back Anthropic SSE events.
