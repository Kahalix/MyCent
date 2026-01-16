window.app = window.app || {};

app.imgUrl = (p) => {
  if (!p) return 'https://placehold.co/96x96?text=IMG';
  if (/^https?:\/\//i.test(p)) return p;

  let s = String(p).replace(/^\/+/, '');
  s = s.replace(/^(?:media\/)+/, 'media/');
  if (s.startsWith('media/')) return '/' + s;
  return '/media/' + s;
};


// NEW (jakby coś nie działało zamienimy na OLD)
if (window.htmx && window.htmx.config) {
  window.htmx.config.historyCacheSize = 0;
}

document.body.addEventListener('htmx:beforeSwap', (e) => {
  try {
    const tgt = e?.detail?.target;
    if (tgt && window.Alpine) window.Alpine.destroyTree(tgt);
  } catch {}
});

document.body.addEventListener('htmx:afterSwap', (e) => {
  try {
    const tgt = e?.detail?.target || e.target;
    if (tgt && window.Alpine) window.Alpine.initTree(tgt);
  } catch {}
  try { window.app?.wsHub?.wake?.(); } catch {}
});

// OLD
//document.addEventListener('htmx:afterSwap', (evt) => {
//  try {
//    if (window.Alpine) window.Alpine.initTree(evt.target || document.body);
//  } catch {}
//});

document.body.addEventListener('htmx:historyRestore', () => {
  if (!window.htmx) return;
  htmx.ajax('GET', location.pathname + location.search, {
    target: '#app-root',
    swap: 'innerHTML',
    pushURL: false,
    history: false,
    historyElt: '#app-root'
  });
});

(function(){
  if (window.__GLOBAL_LOADING_INSTALLED__) return;
  window.__GLOBAL_LOADING_INSTALLED__ = true;

  const root    = document.getElementById('app-root');
  const bar     = document.getElementById('route-indicator');
  const overlay = document.getElementById('global-loader');

  let globalCount = 0;
  let routeCount  = 0;
  let barTimer    = null;
  let ovlTimer    = null;

  const showBar = () => {
    if (barTimer) clearTimeout(barTimer);
    barTimer = setTimeout(() => { bar && bar.classList.add('is-busy'); }, 120);
    document.documentElement.setAttribute('data-loading', '1');
  };
  const hideBar = () => {
    if (barTimer) { clearTimeout(barTimer); barTimer = null; }
    bar && bar.classList.remove('is-busy');
    document.documentElement.removeAttribute('data-loading');
  };

  const showOverlay = () => {
    if (ovlTimer) clearTimeout(ovlTimer);
    ovlTimer = setTimeout(() => {
      overlay?.classList.add('is-visible');
      overlay?.setAttribute('aria-hidden', 'false');
    }, 160);
  };
  const hideOverlay = () => {
    if (ovlTimer) { clearTimeout(ovlTimer); ovlTimer = null; }
    overlay?.classList.remove('is-visible');
    overlay?.setAttribute('aria-hidden', 'true');
  };

  const routeOn  = () => {
    if (++routeCount === 1) {
      root && root.setAttribute('aria-busy', 'true');
      showOverlay();
    }
  };
  const routeOff = () => {
    routeCount = Math.max(0, routeCount - 1);
    if (routeCount === 0) {
      root && root.removeAttribute('aria-busy');
      hideOverlay();
    }
  };

  window.app = window.app || {};
  app.loading = {
    inc(){ if (++globalCount === 1) showBar(); },
    dec(){ globalCount = Math.max(0, globalCount - 1); if (globalCount === 0) hideBar(); },
    wrap: async (fn) => { app.loading.inc(); try { return await fn(); } finally { app.loading.dec(); } },
    routeOn, routeOff, reset: () => { globalCount = routeCount = 0; hideBar(); hideOverlay(); }
  };

  const _fetch = window.fetch;
  const inflight = new Map();

  window.fetch = function(input, init){
    let url = '';
    let method = 'GET';

    try {
      if (typeof input === 'string') url = input;
      else if (input && typeof input.url === 'string') url = input.url;
      if (init && init.method) method = String(init.method).toUpperCase();
      else if (input && input.method) method = String(input.method).toUpperCase();
    } catch {}

    let skip = false;
    try {
      const H = init && init.headers;
      if (H instanceof Headers) {
        skip = H.has('X-No-Loading') || H.has('x-no-loading');
      } else if (Array.isArray(H)) {
        skip = H.some(([k]) => String(k).toLowerCase() === 'x-no-loading');
      } else if (H && typeof H === 'object') {
        skip = Object.keys(H).some(k => k.toLowerCase() === 'x-no-loading');
      }
    } catch {}

    const dedupe = method === 'GET' || method === 'HEAD';
    let key = null;

    if (dedupe) {
      const uid = (window.app?.me?.public_id)
        ? String(window.app.me.public_id)
        : (window.app?.authed === true ? 'authed' : 'anon');

      try {
        const abs = new URL(url, location.href).href;
        key = method + ' ' + abs + ' ' + uid;
      } catch {
        key = method + ' ' + String(url) + ' ' + uid;
      }

      const ex = inflight.get(key);
      if (ex) return ex.then(r => r.clone());
    }

    if (!skip) app.loading.inc();

    const p = _fetch.apply(this, arguments);
    const done = p.finally(() => {
      if (!skip) app.loading.dec();
      if (key && inflight.get(key) === done) inflight.delete(key);
    });

    if (key) inflight.set(key, done);

    return done;
  };

  document.body.addEventListener('htmx:beforeRequest', (e) => {
    const tgt = e?.detail?.target || e.target;
    app.loading.inc();
    if (tgt === root) routeOn();
  });

  document.body.addEventListener('htmx:afterRequest', () => {
    app.loading.dec();
  });

  document.body.addEventListener('htmx:sendError', (e) => {
    app.loading.dec();
    if ((e?.detail?.target || e.target) === root) routeOff();
  });

  document.body.addEventListener('htmx:afterSwap', (e) => {
    if (e.target === root) routeOff();
  });

  document.body.addEventListener('htmx:historyRestore', () => {
    app.loading.reset();
  });
})();

document.body.addEventListener('htmx:configRequest', (evt) => {
  const getCookie = (name) => {
    const pairs = document.cookie ? document.cookie.split('; ') : [];
    for (const p of pairs) {
      const idx = p.indexOf('=');
      const k = decodeURIComponent(p.substring(0, idx));
      if (k === name) return decodeURIComponent(p.substring(idx + 1));
    }
    return null;
  };
  const csrftoken = getCookie('csrftoken');
  if (csrftoken) evt.detail.headers['X-CSRFToken'] = csrftoken;
});

document.addEventListener('htmx:afterOnLoad', (evt) => {
  const root = document.getElementById('app-root');
  if (!root) return;
  if (evt.detail?.target !== root) return;

  const respURL = evt.detail?.xhr?.responseURL || '';
  let newUrl = '';
  if (respURL) {
    try {
      const u = new URL(respURL, location.origin);
      newUrl = u.pathname + u.search + u.hash;
    } catch {}
  }
  if (!newUrl) newUrl = evt.detail?.pathInfo?.finalRequestPath
                    || evt.detail?.pathInfo?.requestPath
                    || '';

  const curr = location.pathname + location.search + location.hash;
  if (newUrl && newUrl !== curr) {
    history.pushState({}, '', newUrl);
  }
});
