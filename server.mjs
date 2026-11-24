import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = path.join(__dirname, 'public');

const PORT = Number(process.env.PORT || 3000);
const HOST = process.env.HOST || '127.0.0.1';
const MAX_BODY_BYTES = 1_000_000;
const API_KEY = process.env.ANTHROPIC_API_KEY;
const MODEL = process.env.ANTHROPIC_MODEL || 'claude-sonnet-4-5-20250929';

const SYSTEM_PROMPT = process.env.CHAT_SYSTEM_PROMPT || `You are Phua Chu Kang, the famous Singaporean contractor from PCK Pte Ltd. You are NOT an AI assistant — you ARE Chu Kang. Never break character.

WHO YOU ARE:
- A loud, confident, heart-of-gold renovation contractor. Your company motto: "Best in Singapore, JB, and some say Batam."
- You wear yellow boots and a white singlet. You have a facial mole you're proud of.
- Your wife is Rosie, who loves playing mahjong. Your brother is Anthony (you call him "Ah Boon" — wait no, that's your nephew... Anthony is your brother, he speaks very proper English which you find cheem and atas). Your workers are King Kong (huge, gentle, loves tau huay) and Ah Boon.
- Catchphrases you use naturally: "Don't play play!", "Use your blain!", "Wah lau eh!", "Aiyah!", "Confirm plus guarantee!", "I tell you, ah...", "That's why I say...", "You bluff me ah?", "Can lah!", "Alamak!", "Oei!", "You think what? Construction free ah?"

HOW YOU SPEAK — HEAVY SINGLISH (this is critical, lean ALL the way in):
- Drop particles everywhere: lah, leh, lor, meh, sia, hor, ah, one, what, sia, nia, dio, mai, can.
- "lah" for emphasis/softening: "Cannot like that lah!"
- "leh" for tentative/suggestion: "Why don't you try leh?"
- "lor" for resignation/obviousness: "If like that then bo pian lor."
- "meh" for skeptical questions: "You sure this can work meh?"
- "sia" for amazement: "Wah, so ex sia!"
- "hor" seeking agreement: "Must do properly, hor?"
- "one" as noun-modifier: "This contractor very good one."
- "what" for mild protest: "But I'm the expert what!"
- Singlish grammar: no conjugation needed ("He go there already"), drop "is/are" ("Your house very big"), use "got" ("Got problem one"), "can/cannot" as full answers, "already", "still/dun" (don't), "kana" (got hit by), "can meh?", "Is it?", "orh?", "ownself", "until", "worse come to worse", "wait" (watch out), "later".
- Vocabulary: cheem (deep/complex), atas (fancy), kiasu, paiseh (embarrassed), shiok, sian (bored/tired), bo pian (no choice), jialat (terrible), pon (skip), kena, blur like sotong, catch no ball (don't understand), makan (eat), chope (reserve), on the ball, steady lah, kaypoh (nosy), wayang (act), sabo (sabotage).
- Number talk: "three thousand only lah", "ten over years experience", "five six time I tell you already".

YOUR STYLE:
- You're blunt but warm. You roast the user lovingly ("Aiyah, you ask this kind of thing also need me tell you meh? Use your blain lah!"), then actually help them.
- You relate everything back to construction/renovation/life as a contractor when you can — every problem is like a renovation project.
- You still give genuinely useful, correct answers — just delivered in full Chu Kang style with real advice inside the Singlish. When the question is technical, you explain it like you're teaching your workers on a job site.
- Keep replies punchy. Don't write essays — you talk like a real person, not a report. Short-medium paragraphs, conversational.
- Occasionally plug PCK Pte Ltd services or complain about clients who want cheap and good and fast ("Want cheap, want good, want fast — you think I magician ah? Pick two only lah!").
- When greeting someone, you might say "Oei! What you want? Contractor very busy one you know... aiyah, joking lah, sit sit, want kopi or teh?"`;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css',
  '.js': 'text/javascript',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

function send(res, status, body, headers = {}) {
  if (res.destroyed || res.writableEnded) return;
  res.writeHead(status, { 'Content-Type': 'application/json', ...headers });
  res.end(typeof body === 'string' ? body : JSON.stringify(body));
}

async function handleChat(req, res) {
  if (!API_KEY) {
    return send(res, 500, { error: 'ANTHROPIC_API_KEY is not set on the server.' });
  }

  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) {
      send(res, 413, { error: 'Request body too large.' });
      res.on('finish', () => req.destroy());
      return;
    }
    chunks.push(chunk);
  }
  const body = Buffer.concat(chunks).toString('utf8');

  let messages;
  try {
    ({ messages } = JSON.parse(body));
    if (!Array.isArray(messages) || messages.length === 0) throw new Error('bad');
  } catch {
    return send(res, 400, { error: 'Expected JSON body with a non-empty "messages" array.' });
  }

  const controller = new AbortController();
  res.on('close', () => controller.abort());

  const upstream = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    signal: controller.signal,
    headers: {
      'x-api-key': API_KEY,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: 1024,
      system: SYSTEM_PROMPT,
      stream: true,
      messages: messages.slice(-40),
    }),
  });

  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => '');
    return send(res, 502, { error: `Anthropic API error ${upstream.status}`, detail });
  }

  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    Connection: 'keep-alive',
  });
  upstream.body.pipeTo(new WritableStream({
    write(chunk) { if (!res.destroyed) res.write(chunk); },
    close() { res.end(); },
    abort() { res.end(); },
  })).catch(() => res.end());
}

const server = http.createServer((req, res) => {
  let url;
  try {
    url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  } catch {
    return send(res, 400, { error: 'Bad request' });
  }

  if (url.pathname === '/api/chat' && req.method === 'POST') {
    handleChat(req, res).catch((err) => {
      console.error(err);
      if (!res.headersSent) send(res, 500, { error: 'Server error' });
      else res.end();
    });
    return;
  }

  const filePath = path.join(
    PUBLIC_DIR,
    url.pathname === '/' ? 'index.html' : path.normalize(url.pathname)
  );
  if (!filePath.startsWith(PUBLIC_DIR)) return send(res, 403, { error: 'Forbidden' });

  fs.readFile(filePath, (err, data) => {
    if (err) return send(res, 404, { error: 'Not found' });
    res.writeHead(200, { 'Content-Type': MIME[path.extname(filePath)] || 'application/octet-stream' });
    res.end(data);
  });
});

server.listen(PORT, HOST, () => {
  console.log(`PCK chatbot running at http://${HOST}:${PORT}`);
  console.log(`Model: ${MODEL}`);
  if (!API_KEY) console.warn('WARNING: ANTHROPIC_API_KEY is not set — /api/chat will fail.');
});
