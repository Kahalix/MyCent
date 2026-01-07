window.app = window.app || {};

// Prosty helper do obrazków (zachowuje absolutne URL-e)
app.imgUrl = (p) => {
  // brak obrazka -> placeholder
  if (!p) return 'https://placehold.co/96x96?text=IMG';

  if (/^https?:\/\//i.test(p)) return p;

  let s = String(p).replace(/^\/+/, '');

  s = s.replace(/^(?:media\/)+/, 'media/');

  if (s.startsWith('media/')) return '/' + s;

  return '/media/' + s;
};

// Po każdym swapie HTMX zainicjuj Alpine w drzewie docelowym.
// umożliwia x-teleport -> #overlays
document.addEventListener('htmx:afterSwap', (evt) => {
  try {
    if (window.Alpine) window.Alpine.initTree(evt.target || document.body);
  } catch {}
});

// To czyści ewentualne resztki pustych kart z cache przeglądarki.
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

// === GLOBAL LOADING (HTMX + fetch) ===
(function(){
  if (window.__GLOBAL_LOADING_INSTALLED__) return;
  window.__GLOBAL_LOADING_INSTALLED__ = true;

  const root    = document.getElementById('app-root');
  const bar     = document.getElementById('route-indicator');
  const overlay = document.getElementById('global-loader');

  let globalCount = 0;   // wszystkie requesty (fetch + htmx)
  let routeCount  = 0;   // tylko trasa (#app-root)
  let barTimer    = null;
  let ovlTimer    = null;

  const showBar = () => {
    if (barTimer) clearTimeout(barTimer);
    barTimer = setTimeout(() => { bar && bar.classList.add('is-busy'); }, 120); // anty-migotanie
    document.documentElement.setAttribute('data-loading', '1');
  };
  const hideBar = () => {
    if (barTimer) { clearTimeout(barTimer); barTimer = null; }
    bar && bar.classList.remove('is-busy');
    document.documentElement.removeAttribute('data-loading');
  };

  const showOverlay = () => {
    if (ovlTimer) clearTimeout(ovlTimer);
    // małe opóźnienie, żeby krótkie trasy nie mrugały
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
      // dim + overlay
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

  // --- hook: fetch (obejmie app.api i każde inne fetch) ---
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
      const tok = localStorage.getItem('lown_access') || '';
      try {
        const abs = new URL(url, location.href).href;
        key = method + ' ' + abs + ' ' + tok;
      } catch {
        key = method + ' ' + String(url) + ' ' + tok;
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

  // --- hook: HTMX (globalny) ---
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

  // Na wypadek przywrócenia historii z cache (bez afterSwap)
  document.body.addEventListener('htmx:historyRestore', () => {
    app.loading.reset();
  });
})();



// CSRF dla HTMX (Authorization w utils.js)
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


// Fallback: po udanym ładowaniu do #app-root dopchnij URL ręcznie
document.addEventListener('htmx:afterOnLoad', (evt) => {
  const root = document.getElementById('app-root');
  if (!root) return;
  if (evt.detail?.target !== root) return; // tylko główny swap

  // spróbuj wziąć finalny adres z XHR
  const respURL = evt.detail?.xhr?.responseURL || '';
  let newUrl = '';
  if (respURL) {
    try {
      const u = new URL(respURL, location.origin);
      newUrl = u.pathname + u.search + u.hash;
    } catch {}
  }
  // fallback: ścieżka, o którą prosiliśmy
  if (!newUrl) newUrl = evt.detail?.pathInfo?.finalRequestPath
                    || evt.detail?.pathInfo?.requestPath
                    || '';

  // jeżeli jest różnica — pchnij do historii
  const curr = location.pathname + location.search + location.hash;
  if (newUrl && newUrl !== curr) {
    history.pushState({}, '', newUrl);
  }
});
