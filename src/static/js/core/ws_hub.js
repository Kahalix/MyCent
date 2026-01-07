(function(){
  window.app = window.app || {};

  // ====== WS Hub (1 lider na wszystkie karty, broadcast przez BroadcastChannel) ======
  const bc = ('BroadcastChannel' in window) ? new BroadcastChannel('lown-ws') : null;
  const tabId = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2,8);

  let isLeader = false;
  let heartbeatTimer = null;
  const HEARTBEAT_MS = 1500;
  const LEADER_TIMEOUT = 4000;

  // Subskrypcje w TEJ karcie: topic -> Set(handlerów)
  const localSubs = new Map();

  // Tylko u lidera: licznik subów z wszystkich kart + gniazda
  const globalRefs = new Map();           // topic -> count
  const sockets    = new Map();           // topic -> WebSocket

  function getToken(){
    return (app.getAccessToken && app.getAccessToken()) || localStorage.getItem('lown_access') || '';
  }
  function wsUrlFor(topic){
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const tok = getToken(); const qp = tok ? ('?token='+encodeURIComponent(tok)) : '';
    if (topic === 'inbox') return `${proto}://${location.host}/ws/chat/inbox/${qp}`;
    if (topic.startsWith('thread:')) {
      const pid = topic.slice(7);
      return `${proto}://${location.host}/ws/chat/threads/${encodeURIComponent(pid)}/${qp}`;
    }
    return null;
  }

  // ----- leader election -----
  function beat(){
    try { localStorage.setItem('lown_ws_leader', JSON.stringify({ id: tabId, ts: Date.now() })); } catch {}
  }
  function becomeLeader(){
    if (isLeader) return;
    isLeader = true;
    beat();
    heartbeatTimer = setInterval(beat, HEARTBEAT_MS);

    // odtwórz refy dla lokalnych subów i upewnij się, że mamy sockety
    for (const topic of localSubs.keys()){
      _incRef(topic);
    }
  }
  function resignLeader(){
    if (!isLeader) return;
    isLeader = false;
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
    for (const ws of sockets.values()) { try { ws.close(); } catch {} }
    sockets.clear();
    globalRefs.clear();
  }
  function checkLeader(){
    let rec = null;
    try { rec = JSON.parse(localStorage.getItem('lown_ws_leader') || 'null'); } catch {}
    if (!rec || (Date.now() - (rec.ts||0)) > LEADER_TIMEOUT) {
      becomeLeader();
      _bc({ type:'leader', id: tabId });
      return;
    }
    if (rec.id === tabId) return; // my lider
    if (isLeader) resignLeader(); // ktoś inny jest liderem
  }
  window.addEventListener('storage', (e) => { if (e.key === 'lown_ws_leader') checkLeader(); });
  setInterval(checkLeader, 1200);
  checkLeader();

  // ----- helpers -----
  function _bc(msg){ if (bc) try { bc.postMessage(msg); } catch {} }
  function _dispatchLocal(topic, data){
    const set = localSubs.get(topic); if (!set || !set.size) return;
    for (const fn of set) { try { fn(data); } catch {} }
  }

  // Lider: utrzymuj sockety na podstawie globalRefs
  function _ensureSocket(topic){
    if (!isLeader || sockets.has(topic)) return;
    const url = wsUrlFor(topic); if (!url) return;
    const ws = new WebSocket(url);
    sockets.set(topic, ws);

    ws.onmessage = (ev) => {
      let data = null; try { data = JSON.parse(ev.data || '{}'); } catch {}
      if (!data) return;

      // 1) do innych kart
      _bc({ type:'event', topic, data });
      // 2) do subów w TEJ karcie
      _dispatchLocal(topic, data);
    };
    ws.onclose = () => {
      sockets.delete(topic);
      // jeżeli nadal ktoś subskrybuje — reconnect
      if ((globalRefs.get(topic) || 0) > 0) {
        setTimeout(() => _ensureSocket(topic), 1500 + Math.floor(Math.random()*800));
      }
    };
  }
  function _incRef(topic){
    const n = (globalRefs.get(topic) || 0) + 1;
    globalRefs.set(topic, n);
    if (n === 1) _ensureSocket(topic);
  }
  function _decRef(topic){
    const n = Math.max(0, (globalRefs.get(topic) || 0) - 1);
    globalRefs.set(topic, n);
    if (n === 0) {
      const ws = sockets.get(topic);
      if (ws) { try { ws.close(); } catch {} }
      sockets.delete(topic);
    }
  }

  // BroadcastChannel: komunikacja follower↔leader
  if (bc) {
    bc.onmessage = (e) => {
      const msg = e.data || {};
      if (msg.type === 'event') {
        // event z lidera -> do subów w TEJ karcie
        _dispatchLocal(msg.topic, msg.data);
      } else if (msg.type === 'sub'   && isLeader) _incRef(msg.topic);
      else if (msg.type === 'unsub' && isLeader) _decRef(msg.topic);
      else if (msg.type === 'send'  && isLeader) {
        const ws = sockets.get(msg.topic);
        if (ws && ws.readyState === 1) { try { ws.send(JSON.stringify(msg.data)); } catch {} }
      }
    };
  }

  // API
  function subscribe(topic, handler){
    if (!localSubs.has(topic)) localSubs.set(topic, new Set());
    localSubs.get(topic).add(handler);
    if (isLeader) _incRef(topic);
    else _bc({ type:'sub', topic });

    return () => {
      const set = localSubs.get(topic);
      if (set) { set.delete(handler); if (!set.size) localSubs.delete(topic); }
      if (isLeader) _decRef(topic);
      else _bc({ type:'unsub', topic });
    };
  }

  function send(topic, data){
    if (isLeader) {
      const ws = sockets.get(topic);
      if (ws && ws.readyState === 1) { try { ws.send(JSON.stringify(data)); } catch {} }
      return;
    }
    _bc({ type:'send', topic, data });
  }

  app.wsHub = { subscribe, send, isLeader: () => isLeader, tabId };
})();
