# ai-chatbot

A Phua Chu Kang chatbot web app — heavy Singlish, powered by Claude.

## Run it

```bash
export ANTHROPIC_API_KEY=sk-ant-...
npm start        # node server.mjs, then open http://localhost:3000
```

No dependencies — just Node 18+ and an Anthropic API key.

## Config

See `.env.example`:

- `ANTHROPIC_API_KEY` (required)
- `ANTHROPIC_MODEL` (default `claude-sonnet-4-5-20250929`)
- `CHAT_SYSTEM_PROMPT` (override the Chu Kang persona)
- `PORT` (default `3000`)

## API

`POST /api/chat` — body `{"messages": [{role, content}, ...]}`, streams back Anthropic SSE events.
