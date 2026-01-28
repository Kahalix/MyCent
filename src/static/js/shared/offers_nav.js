window.app = window.app || {};

(function () {
  const KEY = 'lown:offers:prefill';
  const TTL_MS = 2 * 60 * 1000;

  function now() { return Date.now ? Date.now() : +new Date(); }

  function safeParse(raw) {
    try { return JSON.parse(raw); } catch { return null; }
  }

  function isObj(v) {
    return !!v && typeof v === 'object' && !Array.isArray(v);
  }

  function normalizePayload(payload) {
    if (!isObj(payload)) return null;
    const out = {};
    for (const [k, v] of Object.entries(payload)) {
      if (typeof v === 'undefined') continue;
      out[k] = v;
    }
    return Object.keys(out).length ? out : null;
  }

  function getStore() {
    try { return window.sessionStorage; } catch { return null; }
  }

  function write(payload) {
    const store = getStore();
    if (!store) return;
    const p = normalizePayload(payload);
    if (!p) { try { store.removeItem(KEY); } catch {} return; }
    const rec = { t: now(), v: p };
    try { store.setItem(KEY, JSON.stringify(rec)); } catch {}
  }

  function read(remove) {
    const store = getStore();
    if (!store) return null;

    let raw = null;
    try { raw = store.getItem(KEY); } catch { raw = null; }
    if (!raw) return null;

    if (remove) { try { store.removeItem(KEY); } catch {} }

    const rec = safeParse(raw);
    if (!isObj(rec) || !isObj(rec.v) || typeof rec.t !== 'number') return null;

    if (TTL_MS > 0 && now() - rec.t > TTL_MS) return null;

    return rec.v;
  }

  function stripQ(s) {
    s = String(s || '').trim();
    if (!s) return '';
    return s.startsWith('?') ? s.slice(1) : s;
  }

  function fromQueryString(qs) {
    const s = stripQ(qs);
    const out = {};
    let p;
    try { p = new URLSearchParams(s); } catch { p = new URLSearchParams(); }
    for (const [k, v] of p.entries()) out[k] = v;
    return Object.keys(out).length ? out : null;
  }

  app.offersNav = app.offersNav || {
    key: KEY,
    set(payload) { write(payload); },
    take() { return read(true); },
    peek() { return read(false); },
    clear() {
      const store = getStore();
      if (!store) return;
      try { store.removeItem(KEY); } catch {}
    },
    fromQueryString(qs) { return fromQueryString(qs); },
    setFromQueryString(qs) { write(fromQueryString(qs)); },
    go(payload, url) {
      write(payload);
      const u = url || '/offers';
      if (app.goto) app.goto(u);
      else location.href = u;
    }
  };
})();
