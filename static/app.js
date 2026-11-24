"use strict";

const $ = (selector) => document.querySelector(selector);
const storageKey = "ai-chatbot.chat.v2.";
const maxChats = 20;
// Keep failed writes usable for this visit, even after another history action.
const unsavedChats = new Map();
let chats = [];
let currentId = null;
let busy = false;
let ready = false;
let live = false;
let provider = "demo";
let controller = null;
let storageWarning = "";

function validMessages(messages) {
  return Array.isArray(messages) && messages.length <= 40 && messages.length % 2 === 0 &&
    messages.every((m, i) => m && m.role === (i % 2 ? "assistant" : "user") &&
      typeof m.content === "string" && m.content.trim().length > 0 && Array.from(m.content).length <= 4000);
}

function readChats(includeUnsaved = true) {
  const saved = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key?.startsWith(storageKey)) continue;
    try {
      const c = JSON.parse(localStorage.getItem(key));
      if (c && typeof c.id === "string" && key === storageKey + c.id && typeof c.title === "string" &&
          c.title.length <= 80 && validMessages(c.messages) && c.messages.length) saved.push(c);
    } catch { /* Ignore only the damaged entry, not every saved conversation. */ }
  }
  const combined = new Map(saved.map((chat) => [chat.id, chat]));
  if (includeUnsaved) for (const [id, entry] of unsavedChats) {
    // A failed update is not permission to resurrect another tab's deletion.
    if (entry.wasPersisted && !combined.has(id)) unsavedChats.delete(id);
    else combined.set(id, entry.chat);
  }
  // Persisted eviction candidates also respect activity whose write failed.
  const recency = (chat) => unsavedChats.get(chat.id)?.chat.updatedAt || chat.updatedAt || 0;
  return [...combined.values()].sort((a, b) => recency(b) - recency(a));
}

try { chats = readChats().slice(0, maxChats); }
catch { storageWarning = "Browser storage is unavailable. Chats will last only for this visit."; }

function save(chat, deletedId = null, existing = false) {
  let wasPersisted = chat ? (unsavedChats.get(chat.id)?.wasPersisted || false) : false;
  try {
    if (deletedId) {
      unsavedChats.delete(deletedId);
      localStorage.removeItem(storageKey + deletedId);
    }
    if (chat) {
      const stored = localStorage.getItem(storageKey + chat.id);
      const memoryOnly = unsavedChats.has(chat.id) && !unsavedChats.get(chat.id).wasPersisted;
      wasPersisted = wasPersisted || stored !== null;
      if (existing && stored === null && !memoryOnly) {
        unsavedChats.delete(chat.id);
        showError("This chat was deleted in another tab. Start a new chat to continue.");
        currentId = null;
        chats = readChats().slice(0, maxChats);
        return;
      }
      chat.updatedAt = Date.now();
      // Make room for the newest 20 before writing; restore evictions if it fails.
      const evicted = readChats(false).filter((c) => c.id !== chat.id).slice(maxChats - 1);
      const backups = evicted.map((c) => [storageKey + c.id, localStorage.getItem(storageKey + c.id)]);
      for (const [key] of backups) localStorage.removeItem(key);
      try {
        localStorage.setItem(storageKey + chat.id, JSON.stringify(chat));
      } catch (error) {
        for (const [key, value] of backups) if (value !== null) localStorage.setItem(key, value);
        throw error;
      }
      unsavedChats.delete(chat.id);
      for (const old of evicted) unsavedChats.delete(old.id);
    }
    for (const old of readChats(false).slice(maxChats)) localStorage.removeItem(storageKey + old.id);
    chats = readChats().slice(0, maxChats);
  }
  catch {
    if (chat) unsavedChats.set(chat.id, { chat, wasPersisted });
    storageWarning = "Couldn't save this chat in your browser. It will last only for this visit.";
    showError(storageWarning);
  }
}

function showError(message) {
  $("#error").textContent = message;
  $("#error").hidden = !message;
}

function activeChat() { return chats.find((c) => c.id === currentId); }

function closeMobileHistory() {
  $(".sidebar").classList.remove("history-open");
  $("#history-toggle").setAttribute("aria-expanded", "false");
}

function makeMessage(role, content, pending = false) {
  const item = document.createElement("article");
  item.className = `message ${role}${pending ? " pending" : ""}`;
  const name = document.createElement("div");
  name.className = "message-name";
  name.textContent = role === "user" ? "You" : (live ? "Uncle" : "Uncle · scripted demo");
  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = content;
  item.append(name, body);
  return item;
}

function updateControls() {
  $("#send").disabled = !busy && (!ready || !$("#prompt").value.trim());
  $("#send").type = busy ? "button" : "submit";
  $("#send").textContent = busy ? "■" : "↑";
  $("#send").setAttribute("aria-label", busy ? "Stop response" : "Send message");
  $("#prompt").disabled = busy;
  $("#new-chat").disabled = busy;
  $("#clear-chat").disabled = busy || !activeChat();
  document.querySelectorAll(".history-item, .suggestion").forEach((b) => { b.disabled = busy || !ready; });
}

function render() {
  const chat = activeChat();
  $("#welcome").hidden = Boolean(chat);
  $("#chat-title").textContent = chat?.title || "A seat at Uncle’s table";
  $("#messages").replaceChildren(...(chat?.messages || []).map((m) => makeMessage(m.role, m.content)));
  $("#chat-list").replaceChildren();
  for (const saved of chats) {
    const button = document.createElement("button");
    button.className = "history-item";
    button.textContent = saved.title;
    button.title = saved.title;
    if (saved.id === currentId) button.setAttribute("aria-current", "page");
    button.addEventListener("click", () => {
      if (busy) return;
      closeMobileHistory();
      currentId = saved.id;
      $("#prompt").value = "";
      showError("");
      render();
      scrollToBottom();
      $("#prompt").focus();
    });
    $("#chat-list").append(button);
  }
  $("#history-empty").hidden = chats.length > 0;
  updateControls();
}

function scrollToBottom() {
  const scroll = $("#conversation-scroll");
  scroll.scrollTop = scroll.scrollHeight;
}

async function sendMessage(event) {
  event.preventDefault();
  const content = $("#prompt").value.trim();
  if (busy || !ready || !content) return;
  if (content.length > 4000) { showError("Please keep messages under 4,000 characters."); return; }
  showError("");
  const existing = activeChat();
  const chat = existing || { id: crypto.randomUUID(), title: content.slice(0, 60), messages: [] };
  // Keep complete user/assistant pairs, with room for the next user message.
  const messages = [...chat.messages.slice(-38), { role: "user", content }];
  $("#welcome").hidden = true;
  $("#messages").append(makeMessage("user", content), makeMessage("assistant", "Uncle is stirring his kopi…", true));
  $("#prompt").value = "";
  busy = true;
  controller = new AbortController();
  const timeout = setTimeout(() => controller?.abort("timeout"), 38000);
  updateControls();
  scrollToBottom();
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, mode: live ? "live" : "demo", provider }),
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Couldn't send your message. Please try again.");
    if (typeof result.reply !== "string" || !result.reply.trim()) throw new Error("The reply was empty. Please try again.");
    chat.messages = [...messages, { role: "assistant", content: result.reply }];
    chats = [chat, ...chats.filter((c) => c.id !== chat.id)].slice(0, maxChats);
    currentId = chat.id;
    save(chat, null, Boolean(existing));
  } catch (error) {
    $("#prompt").value = content;
    const cancelled = controller.signal.aborted;
    showError(cancelled
      ? (controller.signal.reason === "timeout" ? "The reply took too long. Your message is ready to try again." : "Response stopped. Your message is ready to edit or send again.")
      : (error instanceof TypeError ? "Can't reach the server. Check your connection and try again." : error.message));
  } finally {
    clearTimeout(timeout);
    busy = false;
    controller = null;
    render();
    scrollToBottom();
    $("#prompt").focus();
  }
}

$("#chat-form").addEventListener("submit", sendMessage);
$("#prompt").addEventListener("input", updateControls);
$("#prompt").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("#chat-form").requestSubmit();
  }
});
$("#send").addEventListener("click", () => { if (busy) controller?.abort("stopped"); });
$("#new-chat").addEventListener("click", () => {
  if (busy) return;
  closeMobileHistory();
  currentId = null;
  $("#prompt").value = "";
  showError("");
  render();
  $("#conversation-scroll").scrollTop = 0;
  $("#prompt").focus();
});
$("#clear-chat").addEventListener("click", () => {
  if (busy || !activeChat()) return;
  if (!confirm("Delete this chat from this browser? This can't be undone.")) return;
  const deletedId = currentId;
  chats = chats.filter((c) => c.id !== deletedId);
  currentId = null;
  $("#prompt").value = "";
  showError("");
  save(null, deletedId);
  render();
  $("#new-chat").focus();
});
document.querySelectorAll(".suggestion").forEach((button) => {
  button.addEventListener("click", () => {
    $("#prompt").value = button.dataset.prompt;
    $("#chat-form").requestSubmit();
  });
});
const aboutDialog = $("#about-dialog");
let aboutOpener = null;
for (const selector of ["#about-button", "#details-button"]) {
  $(selector).addEventListener("click", (event) => {
    aboutOpener = event.currentTarget;
    aboutDialog.showModal();
    $("#close-about").focus();
  });
}
$("#close-about").addEventListener("click", () => aboutDialog.close());
aboutDialog.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.preventDefault();
    aboutDialog.close();
  } else if (event.key === "Tab") {
    // Native dialog tabbing can reach browser chrome; wrap within our two controls.
    const controls = [...aboutDialog.querySelectorAll('button:not(:disabled), a[href]')];
    const first = controls[0];
    const last = controls.at(-1);
    if (event.shiftKey && (document.activeElement === first || !aboutDialog.contains(document.activeElement))) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !aboutDialog.contains(document.activeElement))) {
      event.preventDefault();
      first?.focus();
    }
  }
});
aboutDialog.addEventListener("close", () => {
  if (aboutOpener?.isConnected) aboutOpener.focus();
});
$("#history-toggle").addEventListener("click", () => {
  const open = $("#history-toggle").getAttribute("aria-expanded") !== "true";
  $("#history-toggle").setAttribute("aria-expanded", String(open));
  $(".sidebar").classList.toggle("history-open", open);
});

async function configure() {
  try {
    const response = await fetch("/api/config");
    if (!response.ok) throw new Error("Configuration unavailable.");
    const config = await response.json();
    live = config.mode === "live";
    provider = config.provider;
    ready = true;
    const service = provider === "claude" ? "Anthropic" : "OpenAI";
    const assistant = provider === "claude" ? "Claude" : "AI";
    $("#about-button").textContent = live ? `${assistant} · live ↗` : "Scripted demo ↗";
    $("#mode-label").textContent = live ? `Uncle · ${assistant}` : "Uncle · scripted demo";
    if (live) {
      $("#welcome-note").textContent = `AI character powered by ${assistant}. Strong opinions, not always good advice.`;
      $("#privacy-note").textContent = `AI can make mistakes. Messages are sent to ${service}; chat history is saved in this browser.`;
      $("#about-mode").textContent = `This server is configured for live AI replies through ${service}. AI can make mistakes; check important details.`;
    }
    if (storageWarning) showError(storageWarning);
  } catch {
    $("#about-button").textContent = "Unavailable";
    $("#mode-label").textContent = "Not connected";
    showError("Can't connect to the chat server. Refresh the page to try again.");
  }
  render();
}

render();
configure();

window.addEventListener("storage", (event) => {
  if (busy || (event.key && !event.key.startsWith(storageKey))) return;
  try {
    chats = readChats().slice(0, maxChats);
    if (currentId && !activeChat()) currentId = null;
    render();
  } catch { /* The existing in-memory history remains usable. */ }
});
