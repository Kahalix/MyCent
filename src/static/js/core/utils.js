window.app = window.app || {};
var app = window.app;

app.accessStorage = 'none';
app._accessMem = '';
app.useBearer = false;

app.setAccessStorage = function (mode) {
  const m = String(mode || '').toLowerCase();
  if (m === 'local') app.accessStorage = 'local';
  else if (m === 'memory') app.accessStorage = 'memory';
  else app.accessStorage = 'none';

  if (app.accessStorage !== 'local') {
    try { localStorage.removeItem('lown_access'); } catch {}
  }
};

app.getAccessToken = function () {
  if (!app.useBearer) return '';
  return String(app._accessMem || '');
};

app.setAccessToken = function (tok) {
  const t = String(tok || '');
  app._accessMem = t;

  if (!app.useBearer) {
    try { localStorage.removeItem('lown_access'); } catch {}
    return;
  }

  if (app.accessStorage === 'local') {
    try { localStorage.setItem('lown_access', t); } catch {}
  } else {
    try { localStorage.removeItem('lown_access'); } catch {}
  }
};

app.clearAccessToken = function () {
  app._accessMem = '';
  try { localStorage.removeItem('lown_access'); } catch {}
};

try { localStorage.removeItem('lown_access'); } catch {}

app.authed = null;
app.me = null;

app._setAuthState = function (authed, me) {
  const next = !!authed;
  const prev = app.authed;
  app.authed = next;
  app.me = me || null;
  if (prev !== next) {
    try { window.dispatchEvent(new CustomEvent('auth:changed', { detail: { authed: next } })); } catch {}
  }
};

app._mePromise = null;

app.ensureAuthed = async function () {
  if (app._mePromise) return app._mePromise;

  app._mePromise = (async () => {
    const fetchMe = async () => {
      try {
        return await fetch('/api/users/me/', {
          method: 'GET',
          credentials: 'include',
          headers: { 'Accept': 'application/json' }
        });
      } catch {
        return null;
      }
    };

    let resp = await fetchMe();
    if (!resp) return app.authed === true;

    if (resp.ok) {
      const d = await resp.json().catch(() => null);
      app._setAuthState(true, d);
      return true;
    }

    if (resp.status === 401 || resp.status === 403) {
      try {
        await app._refreshAccess();
        resp = await fetchMe();
      } catch {
        resp = null;
      }

      if (resp && resp.ok) {
        const d2 = await resp.json().catch(() => null);
        app._setAuthState(true, d2);
        return true;
      }

      app._setAuthState(false, null);
      return false;
    }

    return app.authed === true;
  })();

  try {
    return await app._mePromise;
  } finally {
    app._mePromise = null;
  }
};

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

app.imgUrl = function (p) {
  if (!p) return 'https://placehold.co/600x600?text=%20';
  if (/^https?:\/\//i.test(p)) return p;
  let s = String(p).replace(/^\/+/, '');
  s = s.replace(/^(?:media\/)+/, 'media/');
  if (s.startsWith('media/')) return '/' + s;
  return '/media/' + s;
};

app.ok    = (text, ms) => { try { app.toast.ok(String(text||''),   { timeout: Number.isFinite(ms)?ms:undefined }); } catch { console.log('[ok]', text); } };
app.error = (text, ms) => { try { app.toast.err(String(text||''),  { timeout: Number.isFinite(ms)?ms:undefined }); } catch { console.error('[err]', text); } };
app.info  = (text, ms) => { try { app.toast.info(String(text||''), { timeout: Number.isFinite(ms)?ms:undefined }); } catch { console.info('[info]', text); } };
app.warn  = (text, ms) => { try { app.toast.warn(String(text||''), { timeout: Number.isFinite(ms)?ms:undefined }); } catch { console.warn('[warn]', text); } };

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

app.ensureCsrfCookie = async function () {
  if (app.getCookie('csrftoken')) return true;
  try {
    await fetch('/api/auth/csrf/', { method: 'GET', credentials: 'include', headers: { 'Accept': 'application/json' } });
  } catch {}
  return !!app.getCookie('csrftoken');
};

app._onSignedOut = function (opts) {
  try { app.clearAccessToken(); } catch {}
  try { sessionStorage.removeItem('post_login_redirect'); } catch {}
  app._setAuthState(false, null);
  const shouldRedirect = !opts || opts.redirect !== false;
  if (shouldRedirect) {
    const next = (opts && typeof opts.next === 'string') ? opts.next : (location.pathname + location.search);
    app.requireAuth(next);
  }
};

app._refreshPromise = null;
app._refreshNeedMe = false;

app._hasMe = function () {
  const m = app.me || (window.app && window.app.me);
  return !!(m && typeof m === 'object' && m.public_id);
};

app._fetchMeOnce = async function () {
  try {
    const r = await fetch('/api/users/me/', {
      method: 'GET',
      credentials: 'include',
      headers: { 'Accept': 'application/json' }
    });
    if (!r.ok) return null;
    const me = await r.json().catch(() => null);
    if (me) {
      app.me = me;
      window.app = window.app || {};
      window.app.me = me;
    }
    return me;
  } catch {
    return null;
  }
};

app._refreshLock = async function (fn) {
  const locks = navigator && navigator.locks;
  if (locks && typeof locks.request === 'function') {
    return await locks.request('mycent:refresh', { mode: 'exclusive' }, async () => await fn());
  }
  return await fn();
};

app._refreshAccess = async function (opts) {
  const o = (opts && typeof opts === 'object') ? opts : {};
  const forceMe = o.forceMe === true;

  app._refreshNeedMe = app._refreshNeedMe || forceMe;

  if (app._refreshPromise) return app._refreshPromise;

  const wait = (ms) => new Promise(r => setTimeout(r, ms));

  app._refreshPromise = app._refreshLock(async () => {
    await app.ensureCsrfCookie();

    const mkHeaders = () => {
      const headers = new Headers({ 'Accept': 'application/json', 'Content-Type': 'application/json' });
      const csrftoken = app.getCookie('csrftoken');
      if (csrftoken) headers.set('X-CSRFToken', csrftoken);
      return headers;
    };

    const doRefresh = async () => {
      return await fetch('/api/auth/refresh/', {
        method: 'POST',
        headers: mkHeaders(),
        credentials: 'include',
        body: '{}'
      });
    };

    let resp;

    try { resp = await doRefresh(); } catch { throw new Error('Network error'); }

    if (resp.status === 403) {
      await app.ensureCsrfCookie();
      try { resp = await doRefresh(); } catch { throw new Error('Network error'); }
    }

    let tries409 = 0;
    let tries5xx = 0;
    let tries429 = 0;

    while (!resp.ok) {
      if (resp.status === 409 && tries409 < 3) {
        tries409++;
        await wait(150 * tries409);
        try { resp = await doRefresh(); } catch { throw new Error('Network error'); }
        continue;
      }

      if (resp.status === 429 && tries429 < 2) {
        tries429++;
        let ms = 800 * tries429;
        try {
          const ra = resp.headers.get('Retry-After');
          if (ra) {
            const n = Number(ra);
            if (Number.isFinite(n) && n > 0) ms = Math.min(5000, Math.max(ms, Math.floor(n * 1000)));
          }
        } catch {}
        await wait(ms);
        try { resp = await doRefresh(); } catch { throw new Error('Network error'); }
        continue;
      }

      if (resp.status >= 500 && tries5xx < 2) {
        tries5xx++;
        await wait(200 * tries5xx);
        try { resp = await doRefresh(); } catch { throw new Error('Network error'); }
        continue;
      }

      throw new Error('Refresh failed');
    }

    if (app._refreshNeedMe && !app._hasMe()) {
      await app._fetchMeOnce();
    }

    app._setAuthState(true, app.me || window.app?.me || null);
    return true;
  });

  try {
    return await app._refreshPromise;
  } finally {
    app._refreshPromise = null;
    app._refreshNeedMe = false;
  }
};

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

  const method = (opts.method || 'GET').toUpperCase();
  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    if (!app.getCookie('csrftoken') && typeof app.ensureCsrfCookie === 'function') {
      try { await app.ensureCsrfCookie(); } catch {}
    }
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
      await app._refreshAccess({ forceMe: opts.forceMe === true });
      resp = await doFetch();
      if (resp.ok) app._setAuthState(true, app.me || window.app?.me || null);
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

app.requireAuth = async function (destPath) {
  try {
    const ok = await app.ensureAuthed();
    if (ok) {
      app.goto(destPath);
      return;
    }
  } catch {}

  try {
    await app._refreshAccess();
    const ok2 = await app.ensureAuthed();
    if (ok2) {
      app.goto(destPath);
      return;
    }
  } catch {}

  try { sessionStorage.setItem('post_login_redirect', destPath); } catch {}
  app.goto('/login?next=' + encodeURIComponent(destPath));
};

document.addEventListener('click', (e) => {
  const a = e.target.closest('a[data-requires-auth]');
  if (!a) return;
  if (app.authed === true) return;
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

app._htmx401InFlight = false;

document.body.addEventListener('htmx:afterOnLoad', async (evt) => {
  const xhr = evt.detail?.xhr;
  if (!xhr) return;
  if (xhr.status !== 401) return;
  if (app._htmx401InFlight) return;

  app._htmx401InFlight = true;
  try {
    await app._refreshAccess();
    window.location.reload();
  } catch {
    app._onSignedOut({ redirect: true });
  } finally {
    app._htmx401InFlight = false;
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
  try { app.ensureAuthed(); } catch {}

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
  if (isProtected && app.authed !== true) {
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
