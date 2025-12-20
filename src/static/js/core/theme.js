window.app = window.app || {};

app.getTheme = function () {
  try {
    return localStorage.getItem('theme') ||
      (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'lownDark' : 'lownLight');
  } catch { return 'lownLight'; }
};

app.applyTheme = function (t) {
  document.documentElement.setAttribute('data-theme', t);
  document.documentElement.classList.toggle('dark', t === 'lownDark');
};

app.toggleTheme = function () {
  const t = app.getTheme() === 'lownDark' ? 'lownLight' : 'lownDark';
  try { localStorage.setItem('theme', t); } catch {}
  app.applyTheme(t);
  window.dispatchEvent(new CustomEvent('theme:changed', { detail: { theme: t } }));
};

app.applyTheme(app.getTheme());
