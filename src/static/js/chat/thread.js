window.app = window.app || {};

app.chatThread = function (opts = {}) {
  return {
    threadId: (opts.threadId || '').trim(),

    // meta
    thread: null,

    // rozmowa
    messages: [],
    err: '',
    input: '',
    sending: false,
    typingOthers: new Set(),

    // stan
    _seen: new Set(),
    _alive: true,
    _unsub: null,      // wsHub unsubscribe handle

    // UI helpers
    newCount: 0,
    isNearBottom: true, // aktualizowane onScroll

    /* ========= lifecycle ========= */
    async init(){
      this._alive = true;
      await this._loadThreadMeta();
      await this._loadLatest();
      await this.$nextTick(() => this.scrollBottom()); // tylko na start

      // subskrypcja kanału wątku przez globalny WS Hub
      this._unsub = app.wsHub.subscribe(this.topic(), (raw) => {
      try{
        if (!this._alive) return;

        if (raw.type === 'message'){
          if (!this._isOnThreadRoute()) return;

          const obj = this._normFromWs(raw);
          const near = this._computeIsNearBottom();

          this._pushIfNew(obj);

          try { app.wsHub.send(this.topic(), { type:'read.up_to', message_public_id: obj.public_id }); } catch {}
          app.api(`/api/users/me/chats/threads/${encodeURIComponent(this.threadId)}/read/`, {
            method:'POST',
            silent:true,
          }).catch(()=>{});

          if (near || obj.mine) {
            this.$nextTick(() => this.scrollBottom());
            this.newCount = 0;
          } else {
            this.newCount = (this.newCount || 0) + 1;
          }
        }

        if (raw.type === 'typing') {
          const myPid = String(app.me?.public_id || app.auth?.user?.public_id || '');
          if (String(raw.user_id) !== myPid) {
            if (raw.state) this.typingOthers.add(String(raw.user_id));
            else this.typingOthers.delete(String(raw.user_id));
          }
        }
      } catch {}
    });
    },

    destroy(){
      this._alive = false;
      try{ this._unsub && this._unsub(); }catch{}
      this._unsub = null;
    },

    /* ========= helpers ========= */
    topic(){ return 'thread:' + this.threadId; },

    _isOnThreadRoute(){
      try{
        const p = location.pathname.replace(/\/+$/, '');
        const expected = (`/chat/t/${encodeURIComponent(this.threadId)}`).replace(/\/+$/, '');
        return p === expected;
      }catch{
        return false;
      }
    },

    /* ========= header ========= */
    partyName(){
      const mePid = app.me?.public_id || app.auth?.user?.public_id || null;
      const parts = Array.isArray(this.thread?.participants) ? this.thread.participants : [];
      const other = parts.find(p => p?.user?.public_id && p.user.public_id !== mePid);
      if (this.thread?.item?.seller_slug) return this.thread.item.seller_slug;
      return other?.user?.display_name || 'Rozmowa';
    },
    itemImg(){
      const it = this.thread?.item || {};
      const first = (Array.isArray(it.images) && it.images.length) ? it.images[0] : null;
      const cover = it.cover_image_url || first?.image_path || first?.image_url || it.catalog_item?.image_path || '';
      const url = app.imgUrl ? app.imgUrl(cover) : cover;
      return url || 'https://placehold.co/640x480?text=%20';
    },
    itemPrice(){
      const it = this.thread?.item;
      if (!it) return '';
      const v = it.price;
      if (v == null) return '—';
      if (typeof v === 'object') {
        const a = v.amount ?? '';
        const c = v.currency || 'PLN';
        return (a !== '' ? a : '—') + ' ' + c;
      }
      return `${v} PLN`;
    },

    /* ========= render helpers ========= */
    dt(iso){ try { return new Date(iso).toLocaleString(); } catch { return ''; } },
    trimmed(){ return (this.input || '').trim(); },
    sameAsPrev(i){ return i>0 && (this.messages[i]?.sender_pid === this.messages[i-1]?.sender_pid); },
    avatarFor(m){
      const ph = 'https://placehold.co/80x80?text=%F0%9F%91%A4';
      const direct = m?.sender_avatar ? (app.imgUrl ? app.imgUrl(m.sender_avatar) : m.sender_avatar) : '';
      if (direct) return direct;
      const pid = m?.sender_pid;
      const parts = Array.isArray(this.thread?.participants) ? this.thread.participants : [];
      const p = parts.find(x => x?.user?.public_id === pid);
      const u = p?.user;
      const url = u?.user_image ? (app.imgUrl ? app.imgUrl(u.user_image) : u.user_image) : '';
      return url || ph;
    },
    isMineFromPid(pid){
      const me = app.me?.public_id || app.auth?.user?.public_id || null;
      return pid === me;
    },

    /* ========= normalizacja ========= */
    _normFromApi(m){
      const pid = m?.sender?.public_id || '';
      const avatar = m?.sender?.user_image ? (app.imgUrl ? app.imgUrl(m.sender.user_image) : m.sender.user_image) : '';
      return {
        public_id: m?.public_id,
        content: m?.content || '',
        sent_at: m?.sent_at,
        sender_pid: pid,
        sender_name: m?.sender?.display_name || '',
        sender_avatar: avatar,
        mine: this.isMineFromPid(pid),
      };
    },
    _normFromWs(raw){
      const m = raw?.payload || raw || {};
      const pid = m?.sender_public_id || m?.sender_pid || '';
      const avatar = m?.sender_user_image ? (app.imgUrl ? app.imgUrl(m.sender_user_image) : m.sender_user_image) : '';
      return {
        public_id: m?.public_id,
        content: m?.content || '',
        sent_at: m?.sent_at,
        sender_pid: pid,
        sender_name: m?.sender_display_name || '',
        sender_avatar: avatar,
        mine: this.isMineFromPid(pid),
      };
    },

    _pushIfNew(obj){
      const id = obj && obj.public_id; if (!id) return;
      if (this._seen.has(id)) return;
      this._seen.add(id);
      this.messages.push(obj);
    },
    _reindexSeen(){ this._seen = new Set(this.messages.map(x => x.public_id).filter(Boolean)); },

    /* ========= API ========= */
    async _loadThreadMeta(){
      try{
        const r = await app.api(`/api/users/me/chats/threads/${encodeURIComponent(this.threadId)}/`, {
          method:'GET'
          // świadomie NIE silent: to jest główny load widoku
        });
        const j = await r.json().catch(()=> ({}));
        if (r.ok) this.thread = j;
      } catch {}
    },
    async _loadLatest(){
      try{
        // backend zwraca najnowsze najpierw -> odwróć do rosnąco
        const r = await app.api(`/api/users/me/chats/threads/${encodeURIComponent(this.threadId)}/messages/`, { method:'GET' });
        const list = await r.json().catch(()=> ([]));
        const base = (Array.isArray(list) ? list : []).reverse().map(m => this._normFromApi(m));
        this.messages = base;
        this._reindexSeen();

        // oznacz odczytane: WS (read.up_to) + cichy REST
        const lastId = this.messages.at(-1)?.public_id;
        if (lastId) {
          try { app.wsHub.send(this.topic(), { type:'read.up_to', message_public_id: lastId }); } catch {}
        }
        app.api(`/api/users/me/chats/threads/${encodeURIComponent(this.threadId)}/read/`, {
          method:'POST',
          silent:true,
        }).catch(()=>{});

        // wyzeruj licznik w nawigacji dla tego wątku
        window.dispatchEvent(new CustomEvent('chat:unread-total', { detail:{ countDeltaToZeroFor: this.threadId }}));
      } catch { this.err = 'Błąd wczytywania wątku'; }
    },

    /* ========= typing ========= */
    onTyping(){
      try { app.wsHub.send(this.topic(), { type:'typing', state:true }); } catch {}
    },

    /* ========= wysyłanie ========= */
    async send(){
      const content = this.trimmed(); if (!content || this.sending) return;
      const near = this._computeIsNearBottom(); // zapamiętaj stan przed dodaniem
      this.sending = true;
      try{
        const r = await app.api(`/api/users/me/chats/threads/${encodeURIComponent(this.threadId)}/messages/send/`, {
          method: 'POST',
          body: JSON.stringify({ content }),
          silent: true, // bez dimma/paska przy wysyłce
        });
        const m = await r.json().catch(()=> null);
        if (r.ok && m){
          // natychmiastowa aktualizacja lokalna (nie czekamy na echo WS)
          const obj = this._normFromApi(m);
          this._pushIfNew(obj);

          // od razu zgłoś read po swojej stronie (serwer i tak z-echo'uje)
          try { app.wsHub.send(this.topic(), { type:'read.up_to', message_public_id: obj.public_id }); } catch {}

          this.input = '';
          if (near) this.$nextTick(() => this.scrollBottom());
        } else {
          this.err = (m?.detail || 'Nie udało się wysłać wiadomości.');
        }
      } catch(e){ this.err = e?.message || 'Błąd sieci.'; }
      finally { this.sending = false; }
    },

    /* ========= scroll ========= */
    _computeIsNearBottom(){
      const el = this.$refs.scroller;
      if (!el) return true;
      const threshold = 120; // px tolerancji
      const distance = Math.ceil(el.scrollHeight - el.scrollTop - el.clientHeight);
      return distance <= threshold;
    },
    onScroll(){
      this.isNearBottom = this._computeIsNearBottom();
      if (this.isNearBottom) this.newCount = 0;
    },
    scrollBottom(){
      try{
        this.$refs.bottom?.scrollIntoView({ behavior:'auto', block:'end' });
        this.isNearBottom = true;
      } catch {}
    },
  };
};
