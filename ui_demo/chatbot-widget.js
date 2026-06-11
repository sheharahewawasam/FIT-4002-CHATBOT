/**
 * Triple A Super AI Chatbot Widget
 * ─────────────────────────────────
 * Drop-in floating chatbot for any page.
 *
 * INTEGRATION (add before </body> on any page):
 *   <script src="chatbot-widget.js"></script>
 *
 * OPTIONAL CONFIG (add before the script tag):
 *   <script>
 *     window.TASChatbotConfig = {
 *       apiUrl: 'http://127.0.0.1:8000/api/chat/',   // default
 *       title:  'Triple A Super AI',                  // panel title
 *       greeting: 'Hello! Ask me about your fund documents.'
 *     };
 *   </script>
 */
(function () {
    'use strict';

    const cfg = window.TASChatbotConfig || {};
    const API_URL  = cfg.apiUrl   || 'http://127.0.0.1:8000/api/chat/';
    const TITLE    = cfg.title    || 'Triple A Super AI';
    const GREETING = cfg.greeting || 'Hello! I\'m the Triple A Super AI assistant. Ask me anything about your fund documents.';

    /* ── Styles ─────────────────────────────────────────────────────────── */
    const CSS = `
        #tas-fab {
            position: fixed;
            bottom: 28px;
            right: 28px;
            width: 58px;
            height: 58px;
            border-radius: 50%;
            background: #0056b3;
            color: #fff;
            border: none;
            cursor: pointer;
            box-shadow: 0 4px 18px rgba(0,86,179,0.45);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            transition: background 0.2s, transform 0.18s, box-shadow 0.18s;
        }
        #tas-fab:hover {
            background: #004494;
            transform: scale(1.08);
            box-shadow: 0 6px 22px rgba(0,86,179,0.55);
        }
        #tas-fab svg { width: 26px; height: 26px; pointer-events: none; }

        #tas-fab-badge {
            position: absolute;
            top: -3px;
            right: -3px;
            width: 18px;
            height: 18px;
            background: #e53935;
            border-radius: 50%;
            font-size: 10px;
            font-weight: 700;
            color: #fff;
            display: none;
            align-items: center;
            justify-content: center;
            border: 2px solid #fff;
        }

        #tas-panel {
            position: fixed;
            bottom: 98px;
            right: 28px;
            width: 385px;
            height: 530px;
            background: #fff;
            border-radius: 14px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.18);
            display: flex;
            flex-direction: column;
            z-index: 9998;
            overflow: hidden;
            opacity: 0;
            pointer-events: none;
            transform: scale(0.92) translateY(16px);
            transform-origin: bottom right;
            transition: opacity 0.22s ease, transform 0.22s ease;
        }
        #tas-panel.tas-open {
            opacity: 1;
            pointer-events: all;
            transform: scale(1) translateY(0);
        }

        /* Header */
        .tas-header {
            background: linear-gradient(135deg, #0056b3 0%, #003d82 100%);
            color: #fff;
            padding: 13px 15px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
        }
        .tas-header-info { display: flex; align-items: center; gap: 10px; }
        .tas-header-avatar {
            width: 36px; height: 36px; border-radius: 50%;
            background: rgba(255,255,255,0.2);
            display: flex; align-items: center; justify-content: center;
            font-size: 18px; flex-shrink: 0;
        }
        .tas-header-text h3 { margin: 0; font-size: 14px; font-weight: 700; }
        .tas-header-text p  { margin: 0; font-size: 11px; opacity: 0.78; }
        .tas-header-close {
            background: none; border: none; color: #fff;
            cursor: pointer; padding: 4px; border-radius: 6px;
            display: flex; opacity: 0.75; transition: opacity 0.15s;
        }
        .tas-header-close:hover { opacity: 1; }

        /* Body */
        .tas-body {
            flex: 1;
            overflow-y: auto;
            padding: 14px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            background: #f6f8fb;
            scroll-behavior: smooth;
        }
        .tas-body::-webkit-scrollbar { width: 4px; }
        .tas-body::-webkit-scrollbar-thumb { background: #ccc; border-radius: 4px; }

        /* Messages */
        .tas-msg {
            max-width: 84%;
            padding: 10px 13px;
            border-radius: 14px;
            font-size: 13.5px;
            line-height: 1.5;
            word-wrap: break-word;
        }
        .tas-bot {
            background: #fff;
            border: 1px solid #e4e8ee;
            align-self: flex-start;
            border-radius: 4px 14px 14px 14px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }
        .tas-user {
            background: #0056b3;
            color: #fff;
            align-self: flex-end;
            border-radius: 14px 4px 14px 14px;
        }

        /* Citations */
        .tas-citations {
            font-size: 11px; color: #666;
            margin-top: 7px; padding-top: 7px;
            border-top: 1px solid #eee;
        }
        .tas-citations ul { margin: 3px 0 0 0; padding-left: 16px; }
        .tas-citations a { color: #0056b3; text-decoration: none; }
        .tas-citations a:hover { text-decoration: underline; }

        /* Typing indicator */
        .tas-typing {
            align-self: flex-start;
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 10px 14px;
            background: #fff;
            border: 1px solid #e4e8ee;
            border-radius: 4px 14px 14px 14px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        }
        .tas-typing span {
            width: 7px; height: 7px; border-radius: 50%;
            background: #0056b3; opacity: 0.6;
            animation: tas-blink 1.3s infinite ease-in-out;
        }
        .tas-typing span:nth-child(2) { animation-delay: 0.2s; }
        .tas-typing span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes tas-blink {
            0%, 80%, 100% { transform: scale(0.6); opacity: 0.3; }
            40%            { transform: scale(1);   opacity: 1;   }
        }

        /* Footer */
        .tas-footer {
            padding: 10px 12px;
            border-top: 1px solid #e8edf2;
            background: #fff;
            display: flex;
            gap: 8px;
            flex-shrink: 0;
            align-items: center;
        }
        .tas-footer input {
            flex: 1;
            padding: 9px 14px;
            border: 1px solid #dde2ea;
            border-radius: 22px;
            outline: none;
            font-size: 13px;
            font-family: inherit;
            background: #f6f8fb;
            transition: border-color 0.15s, background 0.15s;
        }
        .tas-footer input:focus { border-color: #0056b3; background: #fff; }
        .tas-footer input::placeholder { color: #aaa; }
        .tas-send-btn {
            width: 38px; height: 38px; border-radius: 50%;
            background: #0056b3; border: none;
            color: #fff; cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            flex-shrink: 0;
            transition: background 0.15s, transform 0.12s;
        }
        .tas-send-btn:hover  { background: #004494; }
        .tas-send-btn:active { transform: scale(0.93); }
        .tas-send-btn svg { width: 17px; height: 17px; }

        /* Mic button */
        .tas-mic-btn {
            width: 38px; height: 38px; border-radius: 50%;
            background: #f0f4f8; border: 1px solid #dde2ea;
            color: #555; cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            flex-shrink: 0;
            transition: background 0.15s, color 0.15s, border-color 0.15s, transform 0.12s;
        }
        .tas-mic-btn:hover  { background: #e3ecf7; border-color: #0056b3; color: #0056b3; }
        .tas-mic-btn:active { transform: scale(0.93); }
        .tas-mic-btn svg { width: 17px; height: 17px; pointer-events: none; }
        .tas-mic-btn.recording {
            background: #ffebee;
            border-color: #e53935;
            color: #e53935;
            animation: tas-mic-pulse 1s infinite ease-in-out;
        }
        @keyframes tas-mic-pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(229,57,53,0.35); }
            50%       { box-shadow: 0 0 0 7px rgba(229,57,53,0); }
        }
        .tas-mic-btn.unsupported { opacity: 0.35; cursor: not-allowed; }

        /* Responsive: shrink on small screens */
        @media (max-width: 440px) {
            #tas-panel { width: calc(100vw - 20px); right: 10px; bottom: 84px; }
            #tas-fab   { right: 16px; bottom: 16px; }
        }
    `;

    /* ── DOM construction ────────────────────────────────────────────────── */
    function buildWidget() {
        // Inject styles
        const style = document.createElement('style');
        style.id = 'tas-widget-styles';
        style.textContent = CSS;
        document.head.appendChild(style);

        // FAB
        const fab = document.createElement('button');
        fab.id = 'tas-fab';
        fab.title = 'Ask AI Assistant';
        fab.setAttribute('aria-label', 'Open AI assistant');
        fab.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            <span id="tas-fab-badge" aria-hidden="true"></span>`;

        // Panel
        const panel = document.createElement('div');
        panel.id = 'tas-panel';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-label', 'AI Chat Assistant');
        panel.innerHTML = `
            <div class="tas-header">
                <div class="tas-header-info">
                    <div class="tas-header-avatar">🤖</div>
                    <div class="tas-header-text">
                        <h3>${escHtml(TITLE)}</h3>
                        <p>AI-powered fund document assistant</p>
                    </div>
                </div>
                <button class="tas-header-close" id="tas-close-btn" aria-label="Close chat">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                        <line x1="18" y1="6" x2="6" y2="18"/>
                        <line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>
            </div>
            <div class="tas-body" id="tas-body">
                <div class="tas-msg tas-bot">${escHtml(GREETING)}</div>
            </div>
            <div class="tas-footer">
                <button class="tas-mic-btn" id="tas-mic-btn" aria-label="Speak your question" title="Speak your question">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                         stroke-linecap="round" stroke-linejoin="round">
                        <rect x="9" y="2" width="6" height="11" rx="3"/>
                        <path d="M19 10a7 7 0 0 1-14 0"/>
                        <line x1="12" y1="19" x2="12" y2="22"/>
                        <line x1="8"  y1="22" x2="16" y2="22"/>
                    </svg>
                </button>
                <input type="text" id="tas-input"
                       placeholder="Ask a question about your fund…"
                       autocomplete="off" aria-label="Your question"/>
                <button class="tas-send-btn" id="tas-send-btn" aria-label="Send message">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                    </svg>
                </button>
            </div>`;

        document.body.appendChild(fab);
        document.body.appendChild(panel);

        /* ── Events ──────────────────────────────────────────────────────── */
        fab.addEventListener('click', () => togglePanel(panel, fab));
        document.getElementById('tas-close-btn').addEventListener('click', () => closePanel(panel, fab));

        const input = document.getElementById('tas-input');
        document.getElementById('tas-send-btn').addEventListener('click', () => handleSend(input));
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) handleSend(input); });

        // Speech-to-text mic button
        const micBtn = document.getElementById('tas-mic-btn');
        initSpeechRecognition(micBtn, input);

        // Close when clicking outside the panel
        document.addEventListener('click', (e) => {
            if (panel.classList.contains('tas-open') &&
                !panel.contains(e.target) &&
                e.target !== fab &&
                !fab.contains(e.target)) {
                closePanel(panel, fab);
            }
        });
    }

    /* ── Speech-to-text ─────────────────────────────────────────────────── */
    function initSpeechRecognition(micBtn, input) {
        const SpeechRecognition =
            window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!SpeechRecognition) {
            micBtn.classList.add('unsupported');
            micBtn.title = 'Speech recognition is not supported in this browser. Try Chrome or Edge.';
            micBtn.disabled = true;
            return;
        }

        const recognition = new SpeechRecognition();
        recognition.lang = 'en-AU';
        recognition.continuous = false;    // stop after first pause
        recognition.interimResults = true; // stream partial results into input

        let isListening = false;

        micBtn.addEventListener('click', () => {
            if (isListening) {
                recognition.stop();
            } else {
                input.value = '';
                input.placeholder = 'Listening…';
                recognition.start();
            }
        });

        recognition.onstart = () => {
            isListening = true;
            micBtn.classList.add('recording');
            micBtn.setAttribute('aria-label', 'Stop recording');
            micBtn.title = 'Stop recording';
        };

        recognition.onresult = (e) => {
            // Show interim transcript in the input as the user speaks
            const transcript = Array.from(e.results)
                .map(r => r[0].transcript)
                .join('');
            input.value = transcript;
        };

        recognition.onend = () => {
            isListening = false;
            micBtn.classList.remove('recording');
            micBtn.setAttribute('aria-label', 'Speak your question');
            micBtn.title = 'Speak your question';
            input.placeholder = 'Ask a question about your fund…';
            // Auto-send if something was captured
            if (input.value.trim()) {
                handleSend(input);
            }
        };

        recognition.onerror = (e) => {
            isListening = false;
            micBtn.classList.remove('recording');
            input.placeholder = 'Ask a question about your fund…';
            if (e.error !== 'no-speech' && e.error !== 'aborted') {
                appendMessage('Microphone error: ' + e.error, 'tas-bot');
            }
        };
    }

    /* ── Panel toggle helpers ────────────────────────────────────────────── */
    function togglePanel(panel, fab) {
        if (panel.classList.contains('tas-open')) {
            closePanel(panel, fab);
        } else {
            openPanel(panel, fab);
        }
    }

    function openPanel(panel, fab) {
        panel.classList.add('tas-open');
        fab.setAttribute('aria-expanded', 'true');
        clearBadge();
        setTimeout(() => document.getElementById('tas-input').focus(), 250);
    }

    function closePanel(panel, fab) {
        panel.classList.remove('tas-open');
        fab.setAttribute('aria-expanded', 'false');
    }

    /* ── Message handling ────────────────────────────────────────────────── */
    function handleSend(input) {
        const query = input.value.trim();
        if (!query) return;
        input.value = '';
        appendMessage(query, 'tas-user');
        const typingEl = showTyping();
        callApi(query, typingEl);
    }

    function appendMessage(text, cls) {
        const body = document.getElementById('tas-body');
        const div = document.createElement('div');
        div.className = `tas-msg ${cls}`;
        div.textContent = text;
        body.appendChild(div);
        scrollToBottom(body);
        return div;
    }

    function appendBotResponse(answer, citations) {
        const body = document.getElementById('tas-body');
        const div = document.createElement('div');
        div.className = 'tas-msg tas-bot';

        let html = `<div>${escHtml(answer).replace(/\n/g, '<br>')}</div>`;

        if (citations && citations.length > 0) {
            const unique = Array.from(new Set(citations.map(c => c.source)))
                .map(src => citations.find(c => c.source === src));
            html += `<div class="tas-citations"><strong>Sources:</strong><ul>`;
            unique.forEach(c => {
                const name = escHtml(c.source.split('/').pop());
                const fund = escHtml(c.fund || '');
                html += `<li><a href="#" target="_blank" rel="noopener">${name}</a>${fund ? ` (${fund})` : ''}</li>`;
            });
            html += `</ul></div>`;
        }

        div.innerHTML = html;
        body.appendChild(div);
        scrollToBottom(body);

        // Show badge if panel is closed
        if (!document.getElementById('tas-panel').classList.contains('tas-open')) {
            showBadge();
        }
    }

    function showTyping() {
        const body = document.getElementById('tas-body');
        const div = document.createElement('div');
        div.className = 'tas-typing';
        div.id = 'tas-typing';
        div.innerHTML = '<span></span><span></span><span></span>';
        body.appendChild(div);
        scrollToBottom(body);
        return div;
    }

    function removeTyping() {
        const el = document.getElementById('tas-typing');
        if (el) el.remove();
    }

    function scrollToBottom(el) {
        el.scrollTop = el.scrollHeight;
    }

    /* ── API call ────────────────────────────────────────────────────────── */
    async function callApi(query, typingEl) {
        try {
            const res = await fetch(API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query })
            });
            const data = await res.json();
            removeTyping();

            if (data.error) {
                appendMessage('Error: ' + data.error, 'tas-bot');
            } else {
                appendBotResponse(data.answer, data.citations);
            }
        } catch {
            removeTyping();
            appendMessage('Could not reach the server. Please ensure the Django server is running.', 'tas-bot');
        }
    }

    /* ── Badge (unread indicator) ────────────────────────────────────────── */
    function showBadge() {
        const b = document.getElementById('tas-fab-badge');
        if (b) { b.style.display = 'flex'; b.textContent = '1'; }
    }
    function clearBadge() {
        const b = document.getElementById('tas-fab-badge');
        if (b) { b.style.display = 'none'; b.textContent = ''; }
    }

    /* ── Utility ─────────────────────────────────────────────────────────── */
    function escHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /* ── Init ────────────────────────────────────────────────────────────── */
    function init() {
        if (document.getElementById('tas-fab')) return; // already initialised
        buildWidget();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
