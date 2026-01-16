(function () {
  window.app = window.app || {};

  if (window.app.wsHub && window.app.wsHub.__tag === "lown-wsHub") return;

  const CHANNEL_NAME = "lown-ws";
  const LEADER_KEY = "lown_ws_leader";
  const TAB_KEY = "lown_ws_tab_id";

  const HEARTBEAT_MS = 4000;
  const LEADER_TIMEOUT = 9000;

  const APP_PROTO = "lown.v1";

  const WS_PING_MS = 25000;
  const WS_STALE_MS = 90000;
  const WS_WATCHDOG_MS = 10000;

  let bc = null;

  let tabId = null;
  try { tabId = sessionStorage.getItem(TAB_KEY); } catch {}
  if (!tabId) {
    tabId = Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
    try { sessionStorage.setItem(TAB_KEY, tabId); } catch {}
  }

  let isLeader = false;
  let heartbeatTimer = null;

  const localSubs = new Map();
  const globalRefs = new Map();
  const sockets = new Map();
  const socketPromises = new Map();
  const attempts = new Map();
  const socketMeta = new Map();

  let authBlockUntil = 0;

  let probeNonce = null;
  let probeTimer = null;

  function ensureBc() {
    if (!("BroadcastChannel" in window)) { bc = null; return null; }
    if (bc) return bc;
    try { bc = new BroadcastChannel(CHANNEL_NAME); } catch { bc = null; return null; }
    bc.onmessage = onBcMessage;
    return bc;
  }

  function _bc(msg) {
    const ch = ensureBc();
    if (!ch) return;
    try { ch.postMessage(msg); } catch {}
  }

  function _readLeader() {
    try { return JSON.parse(localStorage.getItem(LEADER_KEY) || "null"); } catch { return null; }
  }

  function _writeLeader(id) {
    try { localStorage.setItem(LEADER_KEY, JSON.stringify({ id, ts: Date.now() })); } catch {}
  }

  function beat() {
    _writeLeader(tabId);
  }

  async function fetchWsRefToken() {
    const now = Date.now();
    if (now < authBlockUntil) {
      const err = new Error("auth-blocked");
      err.status = 401;
      throw err;
    }

    if (typeof app.ensureCsrfCookie === "function") {
      try { await app.ensureCsrfCookie(); } catch {}
    }

    const r = await app.api("/api/auth/ws-token/", {
      method: "POST",
      body: "{}",
      silent: true,
      autoToast: false,
      credentials: "include"
    });

    if (!r.ok) {
      let d = {};
      try { d = await r.json(); } catch {}
      const msg = (d && d.detail) ? String(d.detail) : `ws-token failed (${r.status})`;
      const err = new Error(msg);
      err.status = r.status;
      if (r.status === 401 || r.status === 403) authBlockUntil = Date.now() + 4000;
      throw err;
    }

    const d = await r.json().catch(() => ({}));
    if (!d || !d.ws_token) throw new Error("ws-token missing");

    authBlockUntil = 0;
    return String(d.ws_token);
  }

  function wsUrlFor(topic) {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    if (topic === "inbox") return `${proto}://${location.host}/ws/chat/inbox/`;
    if (topic.startsWith("thread:")) {
      const pid = topic.slice(7);
      return `${proto}://${location.host}/ws/chat/threads/${encodeURIComponent(pid)}/`;
    }
    return null;
  }

  function _dispatchLocal(topic, data) {
    const set = localSubs.get(topic);
    if (!set || !set.size) return;
    for (const fn of set) {
      try { fn(data); } catch {}
    }
  }

  function _backoffMs(topic) {
    const a = attempts.get(topic) || 0;
    const pow = Math.min(a, 7);
    const base = 700 * Math.pow(2, pow);
    const jitter = Math.floor(Math.random() * 400);
    return Math.min(25000, base + jitter);
  }

  async function _openSocket(topic) {
    const url = wsUrlFor(topic);
    if (!url) return null;

    let rt = null;
    try { rt = await fetchWsRefToken(); } catch { return null; }

    const protocols = [`rt.${rt}`, APP_PROTO];
    try {
      return new WebSocket(url, protocols);
    } catch {
      return null;
    }
  }

  function _setMeta(topic, ws) {
    const meta = {
      lastRxAt: Date.now(),
      pingTimer: null,
      watchdogTimer: null
    };

    meta.pingTimer = setInterval(() => {
      if (ws.readyState !== 1) return;
      try { ws.send(JSON.stringify({ type: "ping" })); } catch {}
    }, WS_PING_MS);

    meta.watchdogTimer = setInterval(() => {
      if (ws.readyState !== 1) return;
      if ((Date.now() - meta.lastRxAt) > WS_STALE_MS) {
        try { ws.close(4000, "stale"); } catch {}
      }
    }, WS_WATCHDOG_MS);

    socketMeta.set(topic, meta);
  }

  function _clearMeta(topic) {
    const meta = socketMeta.get(topic);
    if (!meta) return;
    try { if (meta.pingTimer) clearInterval(meta.pingTimer); } catch {}
    try { if (meta.watchdogTimer) clearInterval(meta.watchdogTimer); } catch {}
    socketMeta.delete(topic);
  }

  function _ensureSocket(topic) {
    if (!isLeader) return;
    if ((globalRefs.get(topic) || 0) <= 0) return;

    const existing = sockets.get(topic);
    if (existing && (existing.readyState === 0 || existing.readyState === 1)) return;

    if (socketPromises.has(topic)) return;

    const p = (async () => {
      let ws = null;

      try { ws = await _openSocket(topic); } catch { ws = null; }

      if (!ws) {
        const ms = Math.max(900, _backoffMs(topic));
        attempts.set(topic, (attempts.get(topic) || 0) + 1);
        setTimeout(() => _ensureSocket(topic), ms);
        return;
      }

      sockets.set(topic, ws);
      _setMeta(topic, ws);

      ws.onopen = () => {
        attempts.set(topic, 0);
        const meta = socketMeta.get(topic);
        if (meta) meta.lastRxAt = Date.now();
      };

      ws.onerror = () => {
        try { ws.close(); } catch {}
      };

      ws.onmessage = (ev) => {
        let data = null;
        try { data = JSON.parse(ev.data || "{}"); } catch {}
        if (!data) return;

        const meta = socketMeta.get(topic);
        if (meta) meta.lastRxAt = Date.now();

        const t = data && data.type ? String(data.type) : "";

        if (t === "ping") {
          try { ws.send(JSON.stringify({ type: "pong" })); } catch {}
          return;
        }

        if (t === "pong") {
          return;
        }

        _bc({ type: "event", topic, data });
        _dispatchLocal(topic, data);
      };

      ws.onclose = (ev) => {
        sockets.delete(topic);
        _clearMeta(topic);

        const code = ev && typeof ev.code === "number" ? ev.code : 0;

        if (code === 4403) {
          globalRefs.set(topic, 0);
          attempts.delete(topic);
          return;
        }

        if (code === 4401) {
          authBlockUntil = Date.now() + 4000;
        }

        if ((globalRefs.get(topic) || 0) > 0) {
          const ms = Math.max(1200, _backoffMs(topic));
          attempts.set(topic, (attempts.get(topic) || 0) + 1);
          setTimeout(() => _ensureSocket(topic), ms);
        }
      };
    })().finally(() => {
      socketPromises.delete(topic);
    });

    socketPromises.set(topic, p);
  }

  function _incRef(topic) {
    const n = (globalRefs.get(topic) || 0) + 1;
    globalRefs.set(topic, n);
    if (n === 1) _ensureSocket(topic);
  }

  function _decRef(topic) {
    const n = Math.max(0, (globalRefs.get(topic) || 0) - 1);
    globalRefs.set(topic, n);
    if (n === 0) {
      attempts.delete(topic);
      const ws = sockets.get(topic);
      if (ws) { try { ws.close(); } catch {} }
      sockets.delete(topic);
      _clearMeta(topic);
    }
  }

  function _announceAllSubs() {
    for (const topic of localSubs.keys()) _bc({ type: "sub", topic });
  }

  function becomeLeader() {
    if (isLeader) return;
    isLeader = true;

    beat();
    heartbeatTimer = setInterval(beat, HEARTBEAT_MS);

    for (const topic of localSubs.keys()) _incRef(topic);

    _bc({ type: "leader", id: tabId, ts: Date.now() });
  }

  function resignLeader() {
    if (!isLeader) return;
    isLeader = false;

    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }

    for (const ws of sockets.values()) { try { ws.close(); } catch {} }
    sockets.clear();
    socketPromises.clear();
    for (const topic of Array.from(socketMeta.keys())) _clearMeta(topic);
    globalRefs.clear();
    attempts.clear();
  }

  function checkLeader() {
    const rec = _readLeader();

    if (rec && rec.id === tabId) {
      if (!isLeader) becomeLeader();
      return;
    }

    if (!rec || (Date.now() - (rec.ts || 0)) > LEADER_TIMEOUT) {
      becomeLeader();
      return;
    }

    if (isLeader) resignLeader();
  }

  function probeLeaderFast() {
    const ch = ensureBc();
    if (!ch) return;

    clearTimeout(probeTimer);
    probeNonce = Math.random().toString(36).slice(2) + Date.now().toString(36);

    _bc({ type: "probe", from: tabId, nonce: probeNonce, ts: Date.now() });

    probeTimer = setTimeout(() => {
      if (isLeader) return;

      const rec = _readLeader();
      if (rec && rec.id === tabId) {
        becomeLeader();
        return;
      }

      if (!rec || (Date.now() - (rec.ts || 0)) > LEADER_TIMEOUT) {
        becomeLeader();
        return;
      }
    }, 250);
  }

  function onBcMessage(e) {
    const msg = (e && e.data) ? e.data : {};

    if (msg.type === "probe") {
      if (isLeader && msg.from && msg.nonce) {
        _bc({ type: "probe_ack", to: msg.from, nonce: msg.nonce, id: tabId, ts: Date.now() });
      }
      return;
    }

    if (msg.type === "probe_ack") {
      if (msg.to === tabId && msg.nonce && probeNonce && msg.nonce === probeNonce) {
        clearTimeout(probeTimer);
        probeTimer = null;
        probeNonce = null;
        if (msg.id) _writeLeader(String(msg.id));
      }
      return;
    }

    if (msg.type === "leader") {
      if (msg.id && String(msg.id) !== tabId) {
        if (isLeader) resignLeader();
        _announceAllSubs();
      }
      return;
    }

    if (msg.type === "event") {
      _dispatchLocal(msg.topic, msg.data);
      return;
    }

    if (msg.type === "sub") {
      if (isLeader) _incRef(msg.topic);
      return;
    }

    if (msg.type === "unsub") {
      if (isLeader) _decRef(msg.topic);
      return;
    }

    if (msg.type === "send") {
      if (!isLeader) return;
      const ws = sockets.get(msg.topic);
      if (ws && ws.readyState === 1) {
        try { ws.send(JSON.stringify(msg.data)); } catch {}
      }
    }
  }

  let _wakeTimer = null;
  let _wakeInFlight = null;

  function wake() {
    ensureBc();

    clearTimeout(_wakeTimer);
    _wakeTimer = setTimeout(() => {
      if (_wakeInFlight) return;

      _wakeInFlight = (async () => {
        try {
          if (typeof app.ensureAuthed === "function") await app.ensureAuthed();
        } catch {}

        authBlockUntil = 0;

        checkLeader();
        probeLeaderFast();

        if (!isLeader) {
          _announceAllSubs();
          return;
        }

        for (const topic of localSubs.keys()) {
          const cur = globalRefs.get(topic) || 0;
          if (cur <= 0) globalRefs.set(topic, 1);
          _ensureSocket(topic);
        }
      })().finally(() => {
        _wakeInFlight = null;
      });
    }, 200);
  }

  function refreshAuth(opts = {}) {
    const force = !!opts.force;

    authBlockUntil = 0;

    probeLeaderFast();

    if (!isLeader) {
      _announceAllSubs();
      return;
    }

    if (force) {
      for (const ws of sockets.values()) { try { ws.close(); } catch {} }
      sockets.clear();
      socketPromises.clear();
      for (const topic of socketMeta.keys()) _clearMeta(topic);
      attempts.clear();
    }

    for (const topic of globalRefs.keys()) {
      if ((globalRefs.get(topic) || 0) > 0) _ensureSocket(topic);
    }
  }

  ensureBc();

  window.addEventListener("storage", (e) => {
    if (e.key === LEADER_KEY) checkLeader();
  });

  setInterval(() => {
    checkLeader();
    probeLeaderFast();
  }, 2000);

  checkLeader();
  probeLeaderFast();

  window.addEventListener("pageshow", () => {
    wake();
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) wake();
  });

  window.addEventListener("focus", () => {
    wake();
  });

  window.addEventListener("online", () => {
    wake();
  });

  window.addEventListener("pagehide", (ev) => {
    if (ev && ev.persisted) return;
    try {
      const rec = _readLeader();
      if (rec && rec.id === tabId) {
        try { localStorage.removeItem(LEADER_KEY); } catch {}
      }
    } catch {}
    try { if (bc) bc.close(); } catch {}
    bc = null;
    resignLeader();
  });

  function subscribe(topic, handler) {
    if (!localSubs.has(topic)) localSubs.set(topic, new Set());
    localSubs.get(topic).add(handler);

    if (isLeader) _incRef(topic);
    else _bc({ type: "sub", topic });

    probeLeaderFast();

    return () => {
      const set = localSubs.get(topic);
      if (set) {
        set.delete(handler);
        if (!set.size) localSubs.delete(topic);
      }

      if (isLeader) _decRef(topic);
      else _bc({ type: "unsub", topic });
    };
  }

  function send(topic, data) {
    if (isLeader) {
      const ws = sockets.get(topic);
      if (ws && ws.readyState === 1) {
        try { ws.send(JSON.stringify(data)); } catch {}
      }
      return;
    }
    _bc({ type: "send", topic, data });
  }

  window.app.wsHub = {
    __tag: "lown-wsHub",
    subscribe,
    send,
    refreshAuth,
    wake,
    isLeader: () => isLeader,
    tabId
  };
})();
