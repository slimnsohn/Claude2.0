/**
 * Claude 2.0 — Drop-in Gemini Chat Widget
 * Zero dependencies. Single <script> tag. Works on any page.
 *
 * Usage:
 *   <script src="/_shared/chat-widget.js"></script>
 *   — or —
 *   <script src="../../_skills/llm-chat-widget/dist/chat-widget.js"></script>
 *
 * Optional config (set before the script loads):
 *   window.CHAT_WIDGET_CONFIG = {
 *     appName: "My App",                    // shown in chat header
 *     systemPrompt: "You are a ...",        // custom system prompt
 *     contextFn: () => "current data ...",  // function returning live page context
 *     welcomeMessage: "Ask me anything!",   // first message in chat
 *     accentColor: "#58a6ff",               // theme accent color
 *     position: "bottom-right",             // bottom-right | bottom-left
 *     apiKeyEnvHint: "GEMINI_API_KEY",      // env var name shown in prompt
 *   };
 *
 * The widget will:
 *   1. Prompt for Gemini API key on first use (stores in sessionStorage)
 *   2. Read page context automatically (title, meta, visible text summary)
 *   3. Call Gemini API directly from the browser (no backend needed)
 *   4. Render a floating chat panel in the corner
 */
(function () {
  'use strict';

  // Prevent double-init
  if (window.__chatWidgetLoaded) return;
  window.__chatWidgetLoaded = true;

  const CFG = Object.assign({
    appName: document.title || 'This Page',
    systemPrompt: '',
    contextFn: null,
    welcomeMessage: 'Ask me anything about this page — how it works, what the data means, or how to use it.',
    accentColor: '#58a6ff',
    position: 'bottom-right',
    apiKeyEnvHint: 'GEMINI_API_KEY',
  }, window.CHAT_WIDGET_CONFIG || {});

  const STORAGE_KEY = 'gemini_api_key';
  const MODELS = ['gemini-2.5-flash-lite', 'gemini-2.5-flash', 'gemini-2.0-flash-lite', 'gemini-2.0-flash'];

  // Sanitize accentColor to prevent CSS injection
  const ACCENT = /^#[0-9a-fA-F]{3,8}$/.test(CFG.accentColor) ? CFG.accentColor : '#58a6ff';

  // ── Styles ──────────────────────────────────────────────────────────
  const isLeft = CFG.position === 'bottom-left';
  const posH = isLeft ? 'left' : 'right';

  const style = document.createElement('style');
  style.textContent = `
    .cw-toggle {
      position: fixed; bottom: 20px; ${posH}: 20px; width: 44px; height: 44px;
      border-radius: 50%; background: ${ACCENT}; color: #000; border: none;
      font-size: 20px; cursor: pointer; z-index: 10000;
      box-shadow: 0 2px 12px rgba(0,0,0,0.4);
      display: flex; align-items: center; justify-content: center;
      transition: transform 0.2s;
    }
    .cw-toggle:hover { transform: scale(1.08); }
    .cw-panel {
      position: fixed; bottom: 74px; ${posH}: 20px; width: 380px; height: 460px;
      background: #161b22; border: 1px solid #30363d; border-radius: 10px;
      display: none; flex-direction: column; z-index: 9999;
      box-shadow: 0 4px 24px rgba(0,0,0,0.5); font-family: -apple-system, BlinkMacSystemFont,
        'Segoe UI', Helvetica, Arial, sans-serif; font-size: 12px; color: #e6edf3;
    }
    .cw-panel.cw-open { display: flex; }
    .cw-header {
      padding: 10px 14px; border-bottom: 1px solid #30363d;
      display: flex; align-items: center; justify-content: space-between;
      font-size: 13px; font-weight: 700;
    }
    .cw-header-title { color: ${ACCENT}; }
    .cw-close {
      background: none; border: none; color: #8b949e; font-size: 18px;
      cursor: pointer; padding: 0 4px; line-height: 1;
    }
    .cw-close:hover { color: #e6edf3; }
    .cw-messages {
      flex: 1; overflow-y: auto; padding: 10px 14px;
      display: flex; flex-direction: column; gap: 8px;
    }
    .cw-msg {
      font-size: 12px; line-height: 1.5; padding: 8px 10px; border-radius: 8px;
      max-width: 90%; white-space: pre-wrap; word-wrap: break-word;
    }
    .cw-msg-user {
      background: ${ACCENT}; color: #000; align-self: flex-end; font-weight: 500;
    }
    .cw-msg-bot {
      background: #1c2333; color: #e6edf3; align-self: flex-start;
      border: 1px solid #30363d;
    }
    .cw-msg-error {
      background: rgba(248,81,73,0.15); color: #f85149; align-self: flex-start;
      border: 1px solid rgba(248,81,73,0.3); font-size: 11px;
    }
    .cw-thinking { color: #8b949e; font-style: italic; }
    .cw-input-row {
      padding: 10px; border-top: 1px solid #30363d; display: flex; gap: 6px;
    }
    .cw-input {
      flex: 1; padding: 8px 10px; background: #0d1117; border: 1px solid #30363d;
      border-radius: 6px; color: #e6edf3; font-size: 12px; outline: none;
      font-family: inherit;
    }
    .cw-input:focus { border-color: ${ACCENT}; }
    .cw-send {
      padding: 8px 14px; background: ${ACCENT}; color: #000; border: none;
      border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer;
    }
    .cw-send:disabled { opacity: 0.4; cursor: default; }
    .cw-key-prompt {
      padding: 14px; display: flex; flex-direction: column; gap: 8px;
    }
    .cw-key-prompt label { font-size: 11px; color: #8b949e; }
    .cw-key-prompt input {
      padding: 8px 10px; background: #0d1117; border: 1px solid #30363d;
      border-radius: 6px; color: #e6edf3; font-size: 12px; outline: none;
      font-family: inherit;
    }
    .cw-key-prompt input:focus { border-color: ${ACCENT}; }
    .cw-key-prompt button {
      padding: 8px; background: ${ACCENT}; color: #000; border: none;
      border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer;
    }
    .cw-key-prompt .cw-key-hint {
      font-size: 10px; color: #8b949e; line-height: 1.4;
    }
  `;
  document.head.appendChild(style);

  // ── DOM ─────────────────────────────────────────────────────────────
  const toggle = document.createElement('button');
  toggle.className = 'cw-toggle';
  toggle.title = 'Ask AI';
  toggle.textContent = '\u{1F4AC}';

  const panel = document.createElement('div');
  panel.className = 'cw-panel';
  panel.innerHTML = `
    <div class="cw-header">
      <span class="cw-header-title">${escHtml(CFG.appName)} AI</span>
      <button class="cw-close">&times;</button>
    </div>
    <div class="cw-messages" id="cwMessages">
      <div class="cw-msg cw-msg-bot">${escHtml(CFG.welcomeMessage)}</div>
    </div>
    <div class="cw-input-row">
      <input class="cw-input" id="cwInput" placeholder="Ask a question..." />
      <button class="cw-send" id="cwSend">Send</button>
    </div>
  `;

  document.body.appendChild(toggle);
  document.body.appendChild(panel);

  const msgs = panel.querySelector('#cwMessages');
  const input = panel.querySelector('#cwInput');
  const sendBtn = panel.querySelector('#cwSend');
  const closeBtn = panel.querySelector('.cw-close');

  // ── Events ──────────────────────────────────────────────────────────
  toggle.addEventListener('click', togglePanel);
  closeBtn.addEventListener('click', togglePanel);
  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  function togglePanel() {
    panel.classList.toggle('cw-open');
    if (panel.classList.contains('cw-open')) {
      ensureApiKey().then((hasKey) => { if (hasKey) input.focus(); });
    }
  }

  // ── API Key ─────────────────────────────────────────────────────────
  function getApiKey() {
    return sessionStorage.getItem(STORAGE_KEY) || '';
  }

  function ensureApiKey() {
    return new Promise((resolve) => {
      if (getApiKey()) { resolve(true); return; }

      // Show key prompt inline
      const existing = panel.querySelector('.cw-key-prompt');
      if (existing) { resolve(false); return; }

      const prompt = document.createElement('div');
      prompt.className = 'cw-key-prompt';
      prompt.innerHTML = `
        <label>Gemini API Key</label>
        <input type="password" id="cwKeyInput" placeholder="Paste your API key..." />
        <button id="cwKeySave">Save for this session</button>
        <div class="cw-key-hint">
          Key is stored in sessionStorage only — cleared when you close the tab.<br>
          Get a free key at <strong>aistudio.google.com</strong><br>
          Or set <strong>${escHtml(CFG.apiKeyEnvHint)}</strong> as a system environment variable.
        </div>
      `;
      msgs.parentNode.insertBefore(prompt, msgs.parentNode.querySelector('.cw-input-row'));

      const keyInput = prompt.querySelector('#cwKeyInput');
      const keyBtn = prompt.querySelector('#cwKeySave');
      keyInput.focus();

      function save() {
        const key = keyInput.value.trim();
        if (!key) return;
        sessionStorage.setItem(STORAGE_KEY, key);
        prompt.remove();
        input.focus();
        resolve(true);
      }

      keyBtn.addEventListener('click', save);
      keyInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') save();
      });
    });
  }

  // ── Page Context ────────────────────────────────────────────────────
  function gatherPageContext() {
    // Custom context function takes priority
    if (typeof CFG.contextFn === 'function') {
      try {
        const custom = CFG.contextFn();
        if (custom) return String(custom);
      } catch (e) { /* fall through to auto-discovery */ }
    }

    const parts = [];
    parts.push(`Page title: ${document.title}`);

    // Meta description
    const meta = document.querySelector('meta[name="description"]');
    if (meta) parts.push(`Description: ${meta.content}`);

    // Visible headings
    const headings = Array.from(document.querySelectorAll('h1, h2, h3')).slice(0, 15);
    if (headings.length) {
      parts.push('Page sections: ' + headings.map(h => h.textContent.trim()).join(' | '));
    }

    // Tables (summarize structure)
    const tables = document.querySelectorAll('table');
    if (tables.length) {
      parts.push(`Tables on page: ${tables.length}`);
      tables.forEach((t, i) => {
        const headers = Array.from(t.querySelectorAll('th')).map(th => th.textContent.trim());
        const rows = t.querySelectorAll('tbody tr').length || t.querySelectorAll('tr').length - 1;
        if (headers.length) {
          parts.push(`  Table ${i + 1}: ${headers.join(', ')} (${rows} rows)`);
        }
      });
    }

    // Visible text snapshot (first ~2000 chars from main content area)
    const main = document.querySelector('main, [role="main"], .content, #content, #app') || document.body;
    const textContent = main.innerText || '';
    const trimmed = textContent.replace(/\s+/g, ' ').trim().slice(0, 2000);
    if (trimmed.length > 100) {
      parts.push(`\nVisible content snapshot:\n${trimmed}`);
    }

    return parts.join('\n');
  }

  // ── Send Message ────────────────────────────────────────────────────
  let conversationHistory = [];

  async function sendMessage() {
    const question = input.value.trim();
    if (!question) return;

    const apiKey = getApiKey();
    if (!apiKey) { ensureApiKey(); return; }

    // Render user message
    appendMsg(question, 'user');
    input.value = '';
    sendBtn.disabled = true;

    // Thinking indicator
    const thinkingEl = document.createElement('div');
    thinkingEl.className = 'cw-msg cw-msg-bot';
    thinkingEl.innerHTML = '<span class="cw-thinking">Thinking...</span>';
    msgs.appendChild(thinkingEl);
    msgs.scrollTop = msgs.scrollHeight;

    try {
      const pageContext = gatherPageContext();

      const systemPrompt = CFG.systemPrompt || buildDefaultSystemPrompt();

      // Build conversation with context
      const contextBlock = `--- PAGE CONTEXT ---\n${pageContext}\n--- END CONTEXT ---`;

      // Build messages for API (don't add to history until we know it succeeded)
      const userMsg = { role: 'user', parts: [{ text: question }] };
      const pendingHistory = [...conversationHistory, userMsg];

      // Gemini doesn't support system role — prepend to first user message
      const apiMessages = [];
      for (let i = 0; i < pendingHistory.length; i++) {
        const msg = pendingHistory[i];
        if (i === 0) {
          apiMessages.push({
            role: 'user',
            parts: [{ text: `${systemPrompt}\n\n${contextBlock}\n\n${msg.parts[0].text}` }]
          });
        } else {
          apiMessages.push(msg);
        }
      }

      const answer = await callGemini(apiKey, apiMessages);

      // Only commit to history after successful response
      conversationHistory.push(userMsg);
      conversationHistory.push({
        role: 'model',
        parts: [{ text: answer }]
      });

      // Keep history manageable (last 20 turns)
      if (conversationHistory.length > 40) {
        conversationHistory = conversationHistory.slice(-40);
      }

      thinkingEl.remove();
      appendMsg(answer, 'bot');

    } catch (err) {
      thinkingEl.remove();
      appendMsg(err.message || 'Failed to reach Gemini API', 'error');

      // If auth error, clear key so user can re-enter
      if (err.message && err.message.includes('API key')) {
        sessionStorage.removeItem(STORAGE_KEY);
      }
    }

    sendBtn.disabled = false;
    msgs.scrollTop = msgs.scrollHeight;
  }

  function buildDefaultSystemPrompt() {
    return `You are a helpful assistant embedded in a web application called "${CFG.appName}".
You can see the current page content provided as context below.

Your job:
- Answer questions about what's on the page, how it was built, what the data means
- Explain calculations, formulas, or logic behind displayed values when asked
- Help users understand the data and suggest how to accomplish tasks
- If you can see data in the page context, reference it specifically in your answers

Rules:
- Be concise and direct. This is a small chat widget, not a document.
- Use bullet points or short paragraphs. No markdown headers.
- If you don't have enough context to answer, say so honestly.
- Never make up data that isn't in the page context.`;
  }

  // ── Gemini API ──────────────────────────────────────────────────────
  async function callGemini(apiKey, messages) {
    let lastErr = '';

    for (const model of MODELS) {
      try {
        const resp = await fetch(
          `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'x-goog-api-key': apiKey,
            },
            body: JSON.stringify({ contents: messages }),
          }
        );

        if (resp.ok) {
          const result = await resp.json();
          const text = result?.candidates?.[0]?.content?.parts?.[0]?.text;
          if (text) return text;
          lastErr = 'Empty response from Gemini';
        } else if (resp.status === 400 || resp.status === 403) {
          const errData = await resp.json().catch(() => ({}));
          throw new Error(errData?.error?.message || 'Invalid API key');
        } else if (resp.status === 429) {
          lastErr = 'Rate limited — try again in a moment';
          continue; // Try next model
        } else {
          const errData = await resp.json().catch(() => ({}));
          lastErr = errData?.error?.message || `HTTP ${resp.status}`;
          break; // Non-rate-limit error, stop
        }
      } catch (e) {
        if (e.message.includes('API key')) throw e;
        lastErr = e.message || 'Network error';
        break;
      }
    }

    throw new Error(lastErr || 'All Gemini models failed');
  }

  // ── Helpers ─────────────────────────────────────────────────────────
  function appendMsg(text, type) {
    const div = document.createElement('div');
    div.className = `cw-msg cw-msg-${type}`;
    div.textContent = text;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function escHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

})();
