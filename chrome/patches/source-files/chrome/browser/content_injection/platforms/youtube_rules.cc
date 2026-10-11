// Copyright 2026 The Chromium Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "chrome/browser/content_injection/platforms/youtube_rules.h"

namespace content_injection {

namespace {

// youtube.com — distraction-free YouTube:
//
// Blocks:
//   - Home / browse feed entirely (mobile & desktop)
//   - Video suggestions / related items under the player and in sidebar
//   - Comments section
//   - Shorts shelves, carousels, reels, and shorts containers
//   - Shorts navigation tab / pivot button
// Preserves:
//   - Video player (ytm-watch, #player-container-id, #player, video element, controls)
//   - Header bar, search bar, navigation header
constexpr std::string_view kYouTubeJS = R"JS(
(function() {
  var old = document.getElementById('youtube-distraction-blocker-style');
  if (old) old.parentNode.removeChild(old);

  var css = [
    /* 1. Hide Home / Browse Feeds (Mobile & Desktop) */
    'ytm-browse[page-subtype="home"]',
    'ytm-single-column-browse-results-renderer[tab-identifier="FEwhat_to_watch"]',
    'ytm-browse:not([page-subtype="channels"]):not([page-subtype="history"]):not([page-subtype="subscriptions"]) ytm-rich-grid-renderer',
    'ytd-browse[page-subtype="home"]',
    'ytd-browse[page-subtype="home"] ytd-rich-grid-renderer',

    /* 2. Hide Related Videos / Suggestions Under & Beside Player */
    'ytm-single-column-watch-next-results-renderer [section-identifier="related-items"]',
    'ytm-single-column-watch-next-results-renderer .related-items-container',
    'ytm-single-column-watch-next-results-renderer ytm-item-section-renderer:not([section-identifier="comments-entry-point"])',
    'ytd-watch-flexy #secondary',
    'ytd-watch-next-secondary-results-renderer',

    /* 3. Hide Comments */
    'ytm-comments-entry-point-renderer',
    'ytm-item-section-renderer:has(ytm-comments-entry-point-renderer)',
    '#comments',
    'ytd-comments',

    /* 4. Hide Shorts Shelves, Carousels, and Containers */
    'ytm-shorts-shelf-renderer',
    'ytm-reel-shelf-renderer',
    'ytm-shorts',
    '#shorts-container',
    'ytd-reel-shelf-renderer',
    'ytd-rich-shelf-renderer[is-shorts]',
    'ytd-rich-section-renderer:has(ytd-rich-shelf-renderer[is-shorts])',

    /* 5. Hide Shorts Navigation Tab / Buttons */
    'ytm-pivot-bar-item-renderer[aria-label*="Shorts" i]',
    'ytm-pivot-bar-item-renderer:has(a[href*="/shorts"])',
    'ytd-guide-entry-renderer:has(a[href*="/shorts"])',
    'ytd-mini-guide-entry-renderer:has(a[href*="/shorts"])',

    /* 6. Hide Shorts In Search Results / Item Lists */
    'ytm-video-with-context-renderer:has(a[href*="/shorts"])',
    'ytm-compact-video-renderer:has(a[href*="/shorts"])',
    'ytd-video-renderer:has(a[href*="/shorts"])'
  ].join(', ') + ' { display: none !important; } ';

  /* Ensure Video Player and Core Player Elements are Always Visible and Playable */
  css += 'ytm-watch, #player-container-id, .player-container, #player, .html5-video-player, video { display: block !important; visibility: visible !important; } ';

  var style = document.createElement('style');
  style.id = 'youtube-distraction-blocker-style';
  style.type = 'text/css';
  if (style.styleSheet) {
    style.styleSheet.cssText = css;
  } else {
    style.appendChild(document.createTextNode(css));
  }
  (document.head || document.documentElement).appendChild(style);
})();
)JS";

constexpr InjectionRule kRules[] = {
    {"youtube.com", "", InjectionType::kJavaScript, kYouTubeJS},
    {"youtu.be",    "", InjectionType::kJavaScript, kYouTubeJS},
};

}  // namespace

base::span<const InjectionRule> GetYouTubeInjectionRules() {
  return kRules;
}

}  // namespace content_injection
