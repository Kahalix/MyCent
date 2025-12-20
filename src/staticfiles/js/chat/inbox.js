// static/js/chat/inbox.js
window.app = window.app || {};

app.chatInbox = function () {
  return {
    // ===== stan =====
    items: [],          // lista wątków
    next: null,         // next page URL
    loading: false,
    err: '',
    q: '',

    tab: 'all',         // 'all' | 'my_user' | 'users_other' | 'sellers' | 'dm'
    counts: {},         // liczniki nieprzeczytanych z /unread-counts

    _obs: null,
    _reqId: 0,
    _alive: true,
    _unsub: null,       // wsHub unsubscribe handle
    _debounce: null,    // debounce do wyszukiwania

    // unread per thread
    unreadByThread: new Map(),

    /* ===== lifecycle ===== */
    init(){
      this._alive = true;

      // start: pobierz liczniki + listę (domyślnie 'all')
      this.fetchCounts().finally(()=>{});
      this.reload();

      this.$nextTick(() => this._setupObserver());

      // subskrypcja kanału inbox (pojedyncza na kartę)
      this._unsub = app.wsHub.subscribe('inbox', async (msg) => {
        try{
          // 1) aktualizacja liczb zakładek
          if (msg.type === 'inbox.unread_counts'){
            const p = msg.payload || msg;
            if (p && typeof p === 'object') this._applyCounts(p);
            return;
          }

          // 2) aktualizacja wiersza/preview/unread
          if (msg.type !== 'inbox.thread_updated') return;

          const p   = msg.payload || msg;               // obsłuż payload z backendu i „spłaszczony”
          const pid = p.thread_public_id;
          const unread = Number(p.unread_count || 0);

          if (pid) this.unreadByThread.set(pid, unread);

          // zaktualizuj listę (bez duplikatów, z przestawieniem na górę)
          const idx = this.items.findIndex(t => t.public_id === pid);
          if (idx >= 0){
            const th = this.items[idx];
            if (p.last_message_preview) th.last_message_preview = p.last_message_preview;
            if (p.last_message_at)      th.last_message_at      = p.last_message_at;

            // przerzuć na górę (stabilnie)
            this.items.splice(idx, 1);
            this.items.unshift(th);
            this._sortItems();
          } else if (pid) {
            // jeżeli wątek nie jest jeszcze w liście (np. inna zakładka) – wczytaj i spróbuj wstawić
            await this._fetchAndInsert(pid, p);
          }

          // przelicz sumę (dla globalnego badge’a)
          this._emitUnreadSum();
        } catch {}
      });
    },

    destroy(){
      this._alive = false;
      try{ this._obs?.disconnect(); }catch{}
      try{ this._unsub && this._unsub(); }catch{}
      this._unsub = null;
      clearTimeout(this._debounce);
    },

    /* ===== zakładki ===== */
    setTab(kind){
      if (this.tab === kind) return;
      this.tab = kind;
      // reset i wczytanie z serwera w nowym kubełku
      this.reload();
    },
    // ile wyświetlać na badge dla danego kubełka (liczba wątków z unread)
    badge(key){
      const c = this.counts || {};
      if (key === 'total') return (c.total?.unread_threads || 0);
      if (key === 'all_listings') return (c.all_listings?.unread_threads || 0);
      return (c[key]?.unread_threads || 0);
    },

    /* ===== prezentacja ===== */
    thumb(th){
      const it = th?.item || {};
      const first = (Array.isArray(it.images) && it.images.length) ? it.images[0] : null;
      const cover = it.cover_image_url || first?.image_path || first?.image_url || it.catalog_item?.image_path || '';
      const url = app.imgUrl ? app.imgUrl(cover) : cover;
      return url || 'https://placehold.co/80x80?text=%20';
    },
    price(th){
      const it = th?.item;
      if (!it) return '';
      const v = it.price;
      if (v == null || v === '') return '';
      if (typeof v === 'object') {
        const a = (v.amount ?? v.net ?? v.gross);
        const c = v.currency || 'PLN';
        return (a != null ? a : '—') + ' ' + c;
      }
      return `${v} PLN`;
    },
    party(th){
      if (th?.item?.seller_slug) return th.item.seller_slug;
      const mePid = app.me?.public_id || app.auth?.user?.public_id || null;
      const other = (th.participants||[]).find(p => p.user?.public_id !== mePid);
      return other?.user?.display_name || 'Rozmowa';
    },
    title(th){ return th?.item?.set_name || 'DM'; },
    dt(iso){ try { return iso ? new Date(iso).toLocaleString() : ''; } catch { return ''; } },
    unread(pid){ return this.unreadByThread.get(pid) || 0; },

    /* ===== wyszukiwanie ===== */
    onSearchInput(){
      clearTimeout(this._debounce);
      this._debounce = setTimeout(() => this.reload(), 220);
    },

    /* ===== widok (już bez dodatkowego client-side filtra) ===== */
    get view(){ return this.items; },

    /* ===== API ===== */
    async fetchCounts(){
      try{
        const r = await app.api('/api/users/me/chats/threads/unread-counts', { method:'GET' });
        if (!r.ok) return;
        const j = await r.json().catch(()=> ({}));
        this._applyCounts(j);
      } catch {}
    },
    _applyCounts(j){
      // j: { my_user, users_other, sellers, dm, all_listings, total }
      if (!j || typeof j !== 'object') return;
      this.counts = j;
      // emit globalny badge (suma wiadomości albo wątków? – w naszej appce wysyłamy sumę wiadomości)
      // tu jednak nie ruszamy, bo globalną sumę liczymy z unreadByThread w _emitUnreadSum()
    },

    async reload(){ await this.load(null, true); },
    async more(){ if (!this.next || this.loading) return; await this.load(this.next, false); },

    _buildBaseUrl(){
      // bazowy listing z backendowym filtrem dla zakładki + backendowe 'q'
      const params = new URLSearchParams();
      params.set('page_size', '50');

      if (this.tab && this.tab !== 'all'){
        // backend przyjmuje alias thread_kind=...
        params.set('thread_kind', this.tab);
      }

      const qv = (this.q||'').trim();
      if (qv){ params.set('q', qv); }

      return `/api/users/me/chats/threads/?${params.toString()}`;
    },

    async load(url=null, replace=false){
      this.loading = replace ? true : this.loading;
      if (replace){ this.err=''; this.items=[]; this.next=null; this.unreadByThread.clear(); }
      const my = ++this._reqId;
      try{
        if (!url) url = this._buildBaseUrl();
        const r = await app.api(url, { method:'GET' });
        const j = await r.json().catch(()=> ({}));
        if (my !== this._reqId) return;

        const results = Array.isArray(j) ? j : (j.results || []);
        const next = Array.isArray(j) ? null : (j.next || null);

        // dedupe po public_id
        const seen = new Set(this.items.map(x => x.public_id));
        const incoming = results.filter(x => x && x.public_id && !seen.has(x.public_id));
        this.items = replace ? results.slice() : this.items.concat(incoming);
        this.next = next;

        // mapka unread
        const me = app.me?.public_id || app.auth?.user?.public_id || null;
        for (const th of results){
          const myPart = (th.participants||[]).find(p => p.user?.public_id === me);
          if (myPart) this.unreadByThread.set(th.public_id, Number(myPart.unread_count||0));
        }

        this._sortItems();
        this._emitUnreadSum();
      } catch(e){
        if (my !== this._reqId) return;
        this.err = 'Błąd ładowania wątków';
      } finally {
        if (my === this._reqId) this.loading = false;
      }
    },

    async _fetchAndInsert(pid, patch){
      // Dociągnięcie pojedynczego wątku (np. gdy pojawił się nowy i pasuje do aktywnej zakładki)
      try{
        const r = await app.api(`/api/users/me/chats/threads/${encodeURIComponent(pid)}/`, {
          method:'GET',
          silent: true,               // <— cichy: brak dimma/paska
        });
        if (!r.ok) return;
        const th = await r.json().catch(()=>null);
        if (!th) return;

        // jeżeli wątek nie należy do aktywnej zakładki – nie wstawiaj
        if (this.tab !== 'all'){
          const kind = th.thread_kind || null;
          if (kind !== this.tab) return;
        }

        if (patch?.last_message_preview) th.last_message_preview = patch.last_message_preview;
        if (patch?.last_message_at)      th.last_message_at      = patch.last_message_at;

        // dedupe: zanim dodamy — sprawdź, czy już nie ma
        const exists = this.items.some(x => x.public_id === th.public_id);
        if (!exists) this.items.unshift(th);
        this._sortItems();
      } catch {}
    },

    _sortItems(){
      // last_message_at malejąco, potem updated_at malejąco
      this.items.sort((a,b)=>{
        const da = a.last_message_at ? new Date(a.last_message_at).getTime() : 0;
        const db = b.last_message_at ? new Date(b.last_message_at).getTime() : 0;
        if (db !== da) return db - da;
        const ua = a.updated_at ? new Date(a.updated_at).getTime() : 0;
        const ub = b.updated_at ? new Date(b.updated_at).getTime() : 0;
        return ub - ua;
      });
    },

    /* ===== infinite scroll ===== */
    _setupObserver(){
      const el = this.$refs?.sentinel; if (!el || !('IntersectionObserver' in window)) return;
      this._obs = new IntersectionObserver((e)=>{ if (e.some(x => x.isIntersecting)) this.more(); }, { rootMargin: '240px' });
      this._obs.observe(el);
    },

    /* ===== emit do nav ===== */
    _emitUnreadSum(){
      let sum = 0; for (const v of this.unreadByThread.values()) sum += (Number(v)||0);
      window.dispatchEvent(new CustomEvent('chat:unread-total', { detail: { count: sum }}));
    },
  };
};
