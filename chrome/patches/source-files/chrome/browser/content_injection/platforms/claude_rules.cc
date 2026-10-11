// Copyright 2026 The Chromium Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/content_injection/platforms/claude_rules.h"

namespace content_injection {

namespace {

// Injected into claude.ai to intercept the Send action.
// Only reads the text input box once the send button (or Enter key) has been pressed.
// Once pressed, analyzes the prompt and decides whether to cancel the request.
constexpr std::string_view kClaudeJS = R"JS(
(function() {
  if (window.__claude_send_guard_installed__) return;
  window.__claude_send_guard_installed__ = true;
  console.log('[Claude Integrity Guard] Initialized on claude.ai.');

  function showNotification(msg) {
    let el = document.getElementById('claude-integrity-banner');
    if (!el) {
      el = document.createElement('div');
      el.id = 'claude-integrity-banner';
      el.style.cssText = 'position:fixed;top:24px;left:50%;transform:translateX(-50%);z-index:99999999;background:rgba(220,38,38,0.95);color:#fff;padding:12px 24px;border-radius:12px;font-family:system-ui,-apple-system,sans-serif;font-size:14px;font-weight:600;box-shadow:0 8px 30px rgba(0,0,0,0.35);backdrop-filter:blur(8px);display:flex;align-items:center;gap:10px;pointer-events:none;transition:all 0.3s cubic-bezier(0.4,0,0.2,1);opacity:0;';
      document.body.appendChild(el);
    }
    el.innerHTML = '<span>⚠️ ' + msg + '</span>';
    el.style.opacity = '1';
    el.style.transform = 'translateX(-50%) translateY(0)';
    setTimeout(() => {
      if (el) {
        el.style.opacity = '0';
        el.style.transform = 'translateX(-50%) translateY(-12px)';
      }
    }, 4500);
  }

  function getEditorPrompt() {
    const editor = document.querySelector('[data-testid="chat-input"]') ||
                   document.querySelector('.ProseMirror') ||
                   document.querySelector('[contenteditable="true"]') ||
                   document.querySelector('textarea');
    if (!editor) return '';
    return (editor.innerText || editor.textContent || editor.value || '').trim();
  }

  function classifyPrompt(text) {
    if (!text) return { allowed: true };
    const lower = text.toLowerCase();

    // Homework, question dumping, non-conceptual prompts
    const nonConceptualKeywords = [
      'answer the following questions',
      'answer the following',
      'what is the capital of',
      'who is the prime minister of',
      'terminal velocity',
      'solve this',
      'solve the following',
      'write a solution to my',
      'homework',
      'assignment',
      'exam question',
      'quiz problem'
    ];

    for (const kw of nonConceptualKeywords) {
      if (lower.includes(kw)) {
        return { allowed: false, reason: 'Direct homework/non-conceptual question detected.' };
      }
    }

    // Numbered question dumping (e.g. 1) ... 2) ... or 1. ... 2. ...)
    if (/(\b1[\.\)]\s+.*\b2[\.\)]\s+)/is.test(lower)) {
      return { allowed: false, reason: 'Multiple question dump detected.' };
    }

    return { allowed: true };
  }

  function isSendTrigger(target) {
    if (!target) return false;
    const btn = target.closest('button, [role="button"]');
    if (!btn) return false;
    const label = (btn.getAttribute('aria-label') || '').toLowerCase();
    const testid = (btn.getAttribute('data-testid') || '').toLowerCase();
    return label.includes('send') || testid.includes('send') || (btn.querySelector('svg') && btn.closest('[data-cds-part="send-slot"]'));
  }

  function checkAndHandleSend(event) {
    const prompt = getEditorPrompt();
    if (!prompt) return; // empty, default behavior

    console.log('[Claude Integrity Guard] Send pressed. Inspecting prompt:', prompt);
    const result = classifyPrompt(prompt);

    if (!result.allowed) {
      // CANCEL THE REQUEST - sending operation must not work!
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      console.warn('[Claude Integrity Guard] Request CANCELLED for prompt:', prompt);
      showNotification('Request Blocked: Direct non-conceptual / homework questions are prohibited.');
      return false;
    }

    console.log('[Claude Integrity Guard] Prompt allowed (Label 0). Proceeding with send.');
  }

  // Intercept send button clicks & touchstart at root capture phase
  window.addEventListener('click', function(e) {
    if (isSendTrigger(e.target)) {
      checkAndHandleSend(e);
    }
  }, true);

  window.addEventListener('touchstart', function(e) {
    if (isSendTrigger(e.target)) {
      checkAndHandleSend(e);
    }
  }, { capture: true, passive: false });

  // Intercept Enter key press
  window.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      const editor = document.querySelector('[data-testid="chat-input"]') ||
                     document.querySelector('.ProseMirror') ||
                     document.querySelector('[contenteditable="true"]');
      if (editor && (editor === e.target || editor.contains(e.target))) {
        checkAndHandleSend(e);
      }
    }
  }, true);

  // Deep network level intercept: block outgoing fetch requests if payload contains unallowed text
  const rawFetch = window.fetch;
  window.fetch = async function(...args) {
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    if (url.includes('/chat_conversations') || url.includes('/completion') || url.includes('/messages')) {
      const opts = args[1] || {};
      if (opts.body && typeof opts.body === 'string') {
        try {
          const bodyJson = JSON.parse(opts.body);
          const prompt = bodyJson.prompt || bodyJson.text || (bodyJson.messages && JSON.stringify(bodyJson.messages)) || '';
          const result = classifyPrompt(prompt);
          if (!result.allowed) {
            console.warn('[Claude Integrity Guard] Intercepted and killed network send fetch.');
            showNotification('Request Blocked: Non-conceptual prompt detected.');
            return new Response(JSON.stringify({ error: { message: "Request cancelled by browser integrity policy." } }), {
              status: 400,
              headers: { 'Content-Type': 'application/json' }
            });
          }
        } catch (err) {}
      }
    }
    return rawFetch.apply(this, args);
  };
})();
)JS";

constexpr InjectionRule kRules[] = {
    {"claude.ai", "", InjectionType::kJavaScript, kClaudeJS},
};

}  // namespace

base::span<const InjectionRule> GetClaudeInjectionRules() {
  return kRules;
}

}  // namespace content_injection
