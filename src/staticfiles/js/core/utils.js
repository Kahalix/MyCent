window.app = window.app || {};

/* ================== MONEY ================== */
app.moneyNormalize = function (val, defCur='PLN') {
  if (val == null) return null;
  if (typeof val === 'number') return { amount: String(val), currency: defCur };
  if (typeof val === 'string') {
    const s = val.trim();
    if (!s) return null;
    const m = s.match(/^(-?\d+(?:[.,]\d+)?)\s*([A-Z]{3})?$/);
    if (m) return { amount: m[1].replace(',', '.'), currency: m[2] || defCur };
    const parts = s.split(/\s+/);
    if (parts.length === 1) return { amount: parts[0].replace(',', '.'), currency: defCur };
    return { amount: parts[0].replace(',', '.'), currency: parts[1] || defCur };
  }
  if (typeof val === 'object' && ('amount' in val || 'currency' in val)) {
    const a = (val.amount != null) ? String(val.amount).replace(',', '.') : null;
    const c = val.currency || defCur;
    return a == null ? null : { amount: a, currency: c };
  }
  return null;
};

app.moneyAmount = function (val) {
  const m = app.moneyNormalize(val);
  if (!m) return null;
  const n = Number(m.amount);
  return Number.isFinite(n) ? n : null;
};

app.moneyText = function (val, dash='—') {
  const m = app.moneyNormalize(val);
  if (!m) return dash;
  const n = Number(m.amount);
  if (!Number.isFinite(n)) return dash;
  return n.toFixed(2) + ' ' + (m.currency || 'PLN');
};
app.money = app.moneyText;

/* ================== HELPERS ================== */
app.qs = (sel) => document.querySelector(sel);

app.readJson = async (resp) => {
  try { return await resp.json(); } catch { return {}; }
};

app.debounce = function (fn, ms) {
  let t = null;
  return function (...args) {
    clearTimeout(t);
    t = setTimeout(() => fn.apply(this, args), ms || 250);
  };
};

app.errText = (obj) => {
  if (!obj || typeof obj !== 'object') return '';
  if (obj.detail) return (typeof obj.detail === 'string') ? obj.detail : JSON.stringify(obj.detail);
  const parts = [];
  for (const [k, v] of Object.entries(obj)) {
    if (Array.isArray(v)) parts.push(`${k}: ${v.join(', ')}`);
    else if (typeof v === 'string') parts.push(`${k}: ${v}`);
    else parts.push(`${k}: ${JSON.stringify(v)}`);
  }
  return parts.join('\n');
};

app.imgUrl = (p) => p || 'https://placehold.co/600x600?text=%20';

/* ================== TOAST ALIASES ================== */
app.ok    = (text, ms) => { try { app.toast.ok(String(text||''),   { timeout: Number.isFinite(ms)?ms:undefined }); } catch { console.log('[ok]', text); } };
app.error = (text, ms) => { try { app.toast.err(String(text||''),  { timeout: Number.isFinite(ms)?ms:undefined }); } catch { console.error('[err]', text); } };
app.info  = (text, ms) => { try { app.toast.info(String(text||''), { timeout: Number.isFinite(ms)?ms:undefined }); } catch { console.info('[info]', text); } };
app.warn  = (text, ms) => { try { app.toast.warn(String(text||''), { timeout: Number.isFinite(ms)?ms:undefined }); } catch { console.warn('[warn]', text); } };

/* ================== COOKIES / CSRF ================== */
app.getCookie = function (name) {
  const pairs = document.cookie ? document.cookie.split('; ') : [];
  for (const p of pairs) {
    const idx = p.indexOf('=');
    if (idx < 0) continue;
    const k = decodeURIComponent(p.substring(0, idx));
    if (k === name) return decodeURIComponent(p.substring(idx + 1));
  }
  return null;
};

/* ===== Signed-out helper ===== */
app._onSignedOut = function (opts) {
  try { localStorage.removeItem('lown_access'); } catch {}
  try { sessionStorage.removeItem('post_login_redirect'); } catch {}
  window.dispatchEvent(new CustomEvent('auth:changed', { detail: { authed: false } }));
  const shouldRedirect = !opts || opts.redirect !== false;
  if (shouldRedirect) {
    const next = (opts && typeof opts.next === 'string') ? opts.next : (location.pathname + location.search);
    app.requireAuth(next);
  }
};

/* ===== Refresh access (singleton) ===== */
app._refreshPromise = null;

app._refreshAccess = async function () {
  if (app._refreshPromise) return app._refreshPromise;

  app._refreshPromise = (async () => {
    const headers = new Headers({ 'Accept': 'application/json', 'Content-Type': 'application/json' });
    const csrftoken = app.getCookie('csrftoken');
    if (csrftoken) headers.set('X-CSRFToken', csrftoken);

    let resp;
    try {
      resp = await fetch('/api/auth/refresh/', {
        method: 'POST',
        headers,
        credentials: 'include',
        body: '{}'
      });
    } catch {
      throw new Error('Network error');
    }
    if (!resp.ok) throw new Error('Refresh failed');

    const data = await resp.json().catch(() => ({}));
    if (!data?.access) throw new Error('No access in refresh response');

    try { localStorage.setItem('lown_access', data.access); } catch {}
    window.dispatchEvent(new CustomEvent('auth:changed', { detail: { authed: true } }));
    return data.access;
  })();

  try {
    return await app._refreshPromise;
  } finally {
    app._refreshPromise = null;
  }
};

/* ================== API ================== */
app.api = async (url, opts = {}) => {
  const silent = opts.silent === true || opts.background === true || opts.noBusy === true;

  if (!silent) app._busyOn();

  const headers = new Headers(opts.headers || {});
  headers.set('Accept', 'application/json');

  if (silent) headers.set('X-No-Loading', '1');

  const body = opts.body;
  const isForm = (typeof FormData !== 'undefined') && (body instanceof FormData);
  const isBlob = (typeof Blob !== 'undefined') && (body instanceof Blob);
  const isUrlParams = (typeof URLSearchParams !== 'undefined') && (body instanceof URLSearchParams);

  if (!headers.has('Content-Type') && body && !isForm && !isBlob && !isUrlParams) {
    headers.set('Content-Type', 'application/json');
  }

  const token = localStorage.getItem('lown_access');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const method = (opts.method || 'GET').toUpperCase();
  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    const csrftoken = app.getCookie('csrftoken');
    if (csrftoken) headers.set('X-CSRFToken', csrftoken);
  }

  const reqInit = { ...opts, headers, credentials: 'include' };

  const doFetch = () => fetch(url, reqInit);

  let resp;
  try {
    resp = await doFetch();
  } catch {
    throw new Error('Network error');
  } finally {
    if (!silent) app._busyOff();
  }

  if (resp.status === 401) {
    try {
      const newAccess = await app._refreshAccess();
      reqInit.headers.set('Authorization', `Bearer ${newAccess}`);
      resp = await doFetch();
    } catch {
      app._onSignedOut({ redirect: false });
      return resp;
    }
  }

  const autoToast = opts.autoToast === true;
  const toastOn = Array.isArray(opts.toastOn) ? opts.toastOn : [500, 502, 503, 504];

  if (!resp.ok && autoToast && toastOn.includes(resp.status) && window.app?.toast?.fromResponse) {
    try { await window.app.toast.fromResponse(resp.clone(), 'Błąd żądania'); } catch {}
  }

  return resp;
};

/* ================== SPA / HTMX ================== */
app.goto = function (url) {
  const root = document.getElementById('app-root');
  if (window.htmx && root) {
    htmx.ajax('GET', url, {
      target: root,
      swap: 'innerHTML',
      pushURL: true,
      history: true,
      historyElt: root
    });
  } else {
    window.location.assign(url);
  }
};

app.urlParams = (href) => new URL(href || location.href, location.origin).searchParams;

app.requireAuth = function (destPath) {
  if (localStorage.getItem('lown_access')) {
    app.goto(destPath);
    return;
  }
  try { sessionStorage.setItem('post_login_redirect', destPath); } catch {}
  app.goto('/login?next=' + encodeURIComponent(destPath));
};

document.addEventListener('click', (e) => {
  const a = e.target.closest('a[data-requires-auth]');
  if (!a) return;
  const authed = !!localStorage.getItem('lown_access');
  if (authed) {
    return;
  }
  e.preventDefault();
  const href = a.getAttribute('href') || a.dataset.href || '/';
  app.requireAuth(href);
});

document.addEventListener('click', (e) => {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  const a = e.target.closest('a[href]');
  if (!a) return;

  const root = document.getElementById('app-root');
  if (!root || !root.contains(a)) return;

  const href = a.getAttribute('href') || '';
  if (!href || href.startsWith('#') || a.hasAttribute('download') || (a.target||'').toLowerCase()==='_blank') return;
  if (a.closest('[data-no-boost],[hx-boost="false"]')) return;
  if (a.matches('[hx-get],[hx-post],[hx-put],[hx-delete]')) return;

  const u = new URL(href, location.origin);
  if (u.origin !== location.origin) return;

  e.preventDefault();
  app.goto(u.pathname + u.search + u.hash);
});

document.body.addEventListener('htmx:configRequest', (evt) => {
  const token = localStorage.getItem('lown_access');
  if (token) evt.detail.headers['Authorization'] = `Bearer ${token}`;
});

document.body.addEventListener('htmx:afterOnLoad', (evt) => {
  const xhr = evt.detail?.xhr;
  if (!xhr) return;
  if (xhr.status === 401 || xhr.status === 403) {
    app._onSignedOut({ redirect: true });
  }
});

document.addEventListener('htmx:afterOnLoad', (evt) => {
  const root = document.getElementById('app-root');
  if (!root || evt.detail?.target !== root) return;

  const status = evt.detail?.xhr?.status ?? 200;
  if (status >= 300) return;

  const requested = evt.detail?.pathInfo?.finalRequestPath
                 || evt.detail?.pathInfo?.requestPath
                 || '';

  let newUrl = '';
  const respURL = evt.detail?.xhr?.responseURL || '';
  if (respURL) {
    try {
      const u = new URL(respURL, location.origin);
      newUrl = u.pathname + u.search + u.hash;
    } catch {}
  }
  if (!newUrl) newUrl = requested;

  const curr = location.pathname + location.search + location.hash;
  if (!newUrl || newUrl === curr) return;

  if (requested && curr === requested) {
    history.replaceState({}, '', newUrl);
  } else {
    history.pushState({}, '', newUrl);
  }
});

function _clearOverlays() {
  const o = document.getElementById('overlays');
  if (o) o.innerHTML = '';
}
document.body.addEventListener('htmx:afterSwap', (evt) => {
  if (evt.target.id === 'app-root') _clearOverlays();
});
window.addEventListener('popstate', _clearOverlays);

document.addEventListener('DOMContentLoaded', () => {
  if (window.htmx) {
    const root = document.getElementById('app-root');
    if (root) {
      root.setAttribute('hx-history-elt', 'true');
      root.setAttribute('hx-swap', 'innerHTML');
      root.setAttribute('hx-target', 'this');
      root.setAttribute('hx-push-url', 'true');
      root.setAttribute('hx-boost', 'true');
    }
  }
  const root = document.getElementById('app-root');
  if (!root) return;
  const isProtected = root.querySelector('[data-protected]');
  if (isProtected && !localStorage.getItem('lown_access')) {
    app.requireAuth(location.pathname + location.search);
  }
});

app._busyCount = 0;
app._busyOn = function(){
  app._busyCount++;
  const root = document.getElementById('app-root');
  const bar  = document.getElementById('route-indicator');
  if (root) root.classList.add('is-route-loading');
  if (bar)  bar.classList.add('app-request');
};
app._busyOff = function(){
  app._busyCount = Math.max(0, app._busyCount - 1);
  if (app._busyCount > 0) return;
  const root = document.getElementById('app-root');
  const bar  = document.getElementById('route-indicator');
  if (root) root.classList.remove('is-route-loading');
  if (bar)  bar.classList.remove('app-request');
};

app.withBusy = async (fn) => { app._busyOn(); try { return await fn(); } finally { app._busyOff(); } };
