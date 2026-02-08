// ============================================
// Nexzoneo Support Chatbot — Popup Logic
// ============================================

const DEFAULT_BACKEND_URL = "http://localhost:8000";
const MAX_HISTORY = 20; // max messages to save

// DOM elements
const settingsBtn = document.getElementById("settings-btn");
const settingsPanel = document.getElementById("settings-panel");
const backendUrlInput = document.getElementById("backend-url");
const saveSettingsBtn = document.getElementById("save-settings-btn");
const settingsStatus = document.getElementById("settings-status");
const chatMessages = document.getElementById("chat-messages");
const questionInput = document.getElementById("question-input");
const sendBtn = document.getElementById("send-btn");
const suggestionsContainer = document.getElementById("suggestions");

let backendUrl = DEFAULT_BACKEND_URL;
let conversationHistory = []; // {role, content} pairs for LLM context
let chatLog = []; // full chat log for persistence

// ---- Initialization ----

document.addEventListener("DOMContentLoaded", async () => {
  await loadSettings();
  await loadChatHistory();
  questionInput.focus();
});

async function loadSettings() {
  try {
    const data = await chrome.storage.local.get(["backendUrl"]);
    if (data.backendUrl) {
      backendUrl = data.backendUrl;
      backendUrlInput.value = backendUrl;
    } else {
      backendUrlInput.value = DEFAULT_BACKEND_URL;
    }
  } catch {
    backendUrlInput.value = DEFAULT_BACKEND_URL;
  }
}

async function loadChatHistory() {
  try {
    const data = await chrome.storage.local.get(["chatLog", "conversationHistory"]);
    if (data.chatLog && data.chatLog.length > 0) {
      chatLog = data.chatLog;
      conversationHistory = data.conversationHistory || [];

      // Render saved messages
      for (const msg of chatLog) {
        if (msg.type === "user") {
          renderMessage(msg.text, "user", false);
        } else if (msg.type === "bot" && msg.citations) {
          renderBotMessage(msg.text, msg.citations, false);
        } else {
          renderMessage(msg.text, "bot", false);
        }
      }
      hideSuggestions();
    } else {
      // First time — show greeting + suggestions
      const greeting = "Welcome to Nexzoneo Support! How can we help you today?";
      renderMessage(greeting, "bot", false);
      chatLog.push({ type: "bot", text: greeting });
      showSuggestions();
      saveChatHistory();
    }
  } catch {
    // First time or error
    const greeting = "Welcome to Nexzoneo Support! How can we help you today?";
    renderMessage(greeting, "bot", false);
    chatLog.push({ type: "bot", text: greeting });
    showSuggestions();
    saveChatHistory();
  }
}

async function saveChatHistory() {
  try {
    // Keep only last MAX_HISTORY messages
    const trimmedLog = chatLog.slice(-MAX_HISTORY);
    const trimmedHistory = conversationHistory.slice(-10);
    await chrome.storage.local.set({
      chatLog: trimmedLog,
      conversationHistory: trimmedHistory,
    });
  } catch (e) {
    console.warn("Failed to save chat history:", e);
  }
}

// ---- Suggestions ----

function showSuggestions() {
  if (suggestionsContainer) {
    suggestionsContainer.classList.remove("hidden");
  }
}

function hideSuggestions() {
  if (suggestionsContainer) {
    suggestionsContainer.classList.add("hidden");
  }
}

function handleSuggestionClick(e) {
  const btn = e.target.closest(".suggestion-btn");
  if (!btn) return;
  const question = btn.dataset.question;
  if (question) {
    questionInput.value = question;
    hideSuggestions();
    sendQuestion();
  }
}

if (suggestionsContainer) {
  suggestionsContainer.addEventListener("click", handleSuggestionClick);
}

// ---- Settings ----

settingsBtn.addEventListener("click", () => {
  settingsPanel.classList.toggle("hidden");
});

saveSettingsBtn.addEventListener("click", async () => {
  const url = backendUrlInput.value.trim().replace(/\/+$/, "");
  if (!url) {
    showSettingsStatus("Please enter a valid URL.", "error");
    return;
  }

  backendUrl = url;
  await chrome.storage.local.set({ backendUrl });
  showSettingsStatus("Settings saved!", "success");

  // Quick health check
  try {
    const resp = await fetch(`${backendUrl}/health`, { method: "GET" });
    if (resp.ok) {
      const data = await resp.json();
      showSettingsStatus(
        `Connected! ${data.document_count} document(s) indexed.`,
        "success"
      );
    } else {
      showSettingsStatus("Backend responded with an error.", "error");
    }
  } catch {
    showSettingsStatus("Cannot reach backend. Is it running?", "error");
  }
});

function showSettingsStatus(msg, type) {
  settingsStatus.textContent = msg;
  settingsStatus.className = `settings-status ${type}`;
  setTimeout(() => {
    settingsStatus.textContent = "";
    settingsStatus.className = "settings-status";
  }, 4000);
}

// ---- Chat ----

sendBtn.addEventListener("click", sendQuestion);
questionInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendQuestion();
  }
});

async function sendQuestion() {
  const question = questionInput.value.trim();
  if (!question) return;

  // Hide suggestions after first message
  hideSuggestions();

  // Add user message
  renderMessage(question, "user");
  chatLog.push({ type: "user", text: question });
  conversationHistory.push({ role: "user", content: question });

  questionInput.value = "";
  setInputState(false);

  // Show typing indicator
  const loadingEl = appendLoading();

  try {
    const resp = await fetch(`${backendUrl}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        history: conversationHistory.slice(-10),
      }),
    });

    loadingEl.remove();

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: "Unknown error" }));
      const errMsg = err.detail || "Something went wrong.";
      renderMessage(errMsg, "bot");
      chatLog.push({ type: "bot", text: errMsg });
    } else {
      const data = await resp.json();
      renderBotMessage(data.answer, data.citations || []);
      chatLog.push({
        type: "bot",
        text: data.answer,
        citations: data.citations || [],
      });
      conversationHistory.push({ role: "assistant", content: data.answer });
    }
  } catch (err) {
    loadingEl.remove();
    const errMsg =
      "Could not connect to our support service. Please try again later.";
    renderMessage(errMsg, "bot");
    chatLog.push({ type: "bot", text: errMsg });
  }

  saveChatHistory();
  setInputState(true);
  questionInput.focus();
}

// ---- DOM Helpers ----

function renderMessage(text, type, scroll = true) {
  if (type === "bot") {
    const wrapper = document.createElement("div");
    wrapper.className = "message-wrapper bot-wrapper";

    const avatar = document.createElement("div");
    avatar.className = "bot-avatar";
    avatar.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><circle cx="9" cy="9" r="1" fill="currentColor"/><circle cx="15" cy="9" r="1" fill="currentColor"/><path d="M8 15s1.5 2 4 2 4-2 4-2"/><rect x="5" y="4" width="14" height="16" rx="3" ry="3"/><path d="M9 2v2m6-2v2"/></svg>';

    const div = document.createElement("div");
    div.className = "message bot";
    div.innerHTML = linkify(escapeHtml(text));

    wrapper.appendChild(avatar);
    wrapper.appendChild(div);
    chatMessages.appendChild(wrapper);
    if (scroll) scrollToBottom();
    return wrapper;
  } else {
    const div = document.createElement("div");
    div.className = `message ${type}`;
    div.textContent = text;
    chatMessages.appendChild(div);
    if (scroll) scrollToBottom();
    return div;
  }
}

function renderBotMessage(answer, citations, scroll = true) {
  const wrapper = document.createElement("div");
  wrapper.className = "message-wrapper bot-wrapper";

  const avatar = document.createElement("div");
  avatar.className = "bot-avatar";
  avatar.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><circle cx="9" cy="9" r="1" fill="currentColor"/><circle cx="15" cy="9" r="1" fill="currentColor"/><path d="M8 15s1.5 2 4 2 4-2 4-2"/><rect x="5" y="4" width="14" height="16" rx="3" ry="3"/><path d="M9 2v2m6-2v2"/></svg>';

  const div = document.createElement("div");
  div.className = "message bot";

  const answerP = document.createElement("p");
  answerP.innerHTML = linkify(escapeHtml(answer));
  div.appendChild(answerP);

  wrapper.appendChild(avatar);
  wrapper.appendChild(div);
  chatMessages.appendChild(wrapper);
  if (scroll) scrollToBottom();
  return wrapper;
}

function linkify(text) {
  return text.replace(
    /(https?:\/\/[^\s<]+)/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer" class="chat-link">$1</a>'
  );
}

function appendLoading() {
  const wrapper = document.createElement("div");
  wrapper.className = "message-wrapper bot-wrapper";

  const avatar = document.createElement("div");
  avatar.className = "bot-avatar";
  avatar.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24"><circle cx="9" cy="9" r="1" fill="currentColor"/><circle cx="15" cy="9" r="1" fill="currentColor"/><path d="M8 15s1.5 2 4 2 4-2 4-2"/><rect x="5" y="4" width="14" height="16" rx="3" ry="3"/><path d="M9 2v2m6-2v2"/></svg>';

  const div = document.createElement("div");
  div.className = "message bot typing-message";
  div.innerHTML =
    '<div class="typing-indicator"><span></span><span></span><span></span></div>';

  wrapper.appendChild(avatar);
  wrapper.appendChild(div);
  chatMessages.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function setInputState(enabled) {
  questionInput.disabled = !enabled;
  sendBtn.disabled = !enabled;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
