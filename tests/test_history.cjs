// Node is needed only for these browser-storage regression tests, not the app.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');

function historyStore(initial = [], quota = Infinity) {
  const values = new Map(initial.map(c => ['ai-chatbot.chat.v2.' + c.id, JSON.stringify(c)]));
  const storage = {
    get length() { return values.size; },
    key: i => [...values.keys()][i],
    getItem: key => values.get(key) ?? null,
    removeItem: key => values.delete(key),
    setItem(key, value) {
      const next = new Map(values).set(key, value);
      if ([...next.values()].join('').length > quota) throw new Error('QuotaExceededError');
      values.set(key, value);
    },
  };
  const context = vm.createContext({ localStorage: storage, document: {}, Date });
  const source = readFileSync(__dirname + '/../static/app.js', 'utf8');
  vm.runInContext(source.slice(0, source.indexOf('function showError')) + '\nfunction showError() {}', context);
  return { values, run: code => vm.runInContext(code, context) };
}

function chat(id, content = id) {
  return { id, title: id, updatedAt: 1, messages: [
    { role: 'user', content }, { role: 'assistant', content: 'Aiyoh, can lah.' },
  ] };
}

test('a failed write survives deleting a different chat without a reload', () => {
  const store = historyStore([chat('old')], 1);
  store.run(`const fresh = ${JSON.stringify(chat('fresh'))}; chats.unshift(fresh); save(fresh);`);
  store.run(`save(null, 'old');`);
  assert.equal(store.run(`chats.find(c => c.id === 'fresh').messages[0].content`), 'fresh');
  assert.equal(store.values.size, 0, 'the new chat remains memory-only');
});

test('a failed update shadows the stale persisted reply for this visit', () => {
  const store = historyStore([chat('edited'), chat('other')], 1);
  store.run(`const edited = ${JSON.stringify(chat('edited', 'new reply'))}; save(edited, null, true);`);
  store.run(`save(null, 'other');`);
  assert.equal(store.run(`chats.find(c => c.id === 'edited').messages[0].content`), 'new reply');
});

test('the newest 20 fit at quota by evicting the oldest before writing', () => {
  const initial = Array.from({ length: 20 }, (_, i) => ({ ...chat('c' + String(i).padStart(2, '0')), updatedAt: i }));
  const quota = initial.reduce((total, c) => total + JSON.stringify(c).length, 0) + 20;
  const store = historyStore(initial, quota);
  store.run(`save(${JSON.stringify(chat('new'))});`);
  assert.ok(store.values.has('ai-chatbot.chat.v2.new'));
  assert.ok(!store.values.has('ai-chatbot.chat.v2.c00'));
  assert.equal(store.values.size, 20);
});

test('an oversized replacement does not erase the oldest persisted chat', () => {
  const initial = Array.from({ length: 20 }, (_, i) => ({ ...chat('c' + String(i).padStart(2, '0')), updatedAt: i }));
  const quota = initial.reduce((total, c) => total + JSON.stringify(c).length, 0);
  const store = historyStore(initial, quota);
  store.run(`save(${JSON.stringify(chat('new', 'x'.repeat(4000)))});`);
  assert.ok(store.values.has('ai-chatbot.chat.v2.c00'));
  assert.equal(store.values.size, 20);
  assert.ok(store.run(`readChats().some(c => c.id === 'new')`));
});
