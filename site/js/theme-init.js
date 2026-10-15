// Runs before first paint so the saved theme / colour convention never flashes.
(function applySavedPreferences() {
  try {
    var saved = JSON.parse(window.localStorage.getItem('fw.settings.v1') || '{}');
    var root = document.documentElement;
    if (saved.theme === 'dark' || saved.theme === 'light') root.setAttribute('data-theme', saved.theme);
    root.setAttribute('data-updown', saved.updown === 'us' ? 'us' : 'tw');
  } catch (error) {
    document.documentElement.setAttribute('data-updown', 'tw');
  }
})();

// Web fonts are inserted by script so they never block rendering or the app scripts (CSP forbids onload tricks).
(function loadFonts() {
  var link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href =
    'https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&family=Noto+Sans+TC:wght@400;500;700&display=swap';
  document.head.appendChild(link);
})();
