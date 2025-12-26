window.app = window.app || {};

app.chatInbox = function () {
  return {
    items: [],
    next: null,
    loading: false,
    err: '',
    q: '',

    tab: 'all',
    counts: {},

    _obs: null,
    _reqId: 0,
    _alive: true,
    _unsub: null,
    _debounce: null,

    unreadByThread: new Map(),
    mutedThreads: new Set(),

    init() {
      this._alive = true;
      this.fetchCounts().finally(() => {});
      this.reload();
      this.$nextTick(() => this._setupObserver());

      this._unsub = app.wsHub.subscribe('inbox', async (msg) => {
        try {
          if (msg.type === 'inbox.unread_counts') {
            const p = msg.payload || msg;
            if (p && typeof p === 'object') this._applyCounts(p);
            return;
          }

          if (msg.type !== 'inbox.thread_updated') return;

          const p = msg.payload || msg;
          const pid = p.thread_public_id;
          const unread = Number(p.unread_count || 0);

          if (pid) this.unreadByThread.set(pid, unread);

          const idx = this.items.findIndex(t => t.public_id === pid);
          if (idx >= 0) {
            const th = this.items[idx];
            if (p.last_message_preview) th.last_message_preview = p.last_message_preview;
            if (p.last_message_at) th.last_message_at = p.last_message_at;
            this.items.splice(idx, 1);
            this.items.unshift(th);
            this._sortItems();
          } else if (pid) {
            await this._fetchAndInsert(pid, p);
          }

          this._emitUnreadSum();
        } catch {}
      });
    },

    destroy() {
      this._alive = false;
      try { this._obs?.disconnect(); } catch {}
      try { this._unsub && this._unsub(); } catch {}
      this._unsub = null;
      clearTimeout(this._debounce);
    },

    setTab(kind) {
      if (this.tab === kind) return;
      this.tab = kind;
      this.reload();
    },

    badge(key) {
      const c = this.counts || {};
      if (key === 'total') return (c.total?.unread_threads || 0);
      if (key === 'all_listings') return (c.all_listings?.unread_threads || 0);
      return (c[key]?.unread_threads || 0);
    },

    thumb(th) {
      const it = th?.item || {};
      const first = (Array.isArray(it.images) && it.images.length) ? it.images[0] : null;
      const cover = it.cover_image_url || first?.image_path || first?.image_url || it.catalog_item?.image_path || '';
      const url = app.imgUrl ? app.imgUrl(cover) : cover;
      return url || 'https://placehold.co/80x80?text=%20';
    },

    price(th) {
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

    party(th) {
      if (th?.item?.seller_slug) return th.item.seller_slug;
      const mePid = app.me?.public_id || app.auth?.user?.public_id || null;
      const other = (th.participants || []).find(p => p.user?.public_id !== mePid);
      return other?.user?.display_name || 'Rozmowa';
    },

    title(th) {
      return th?.item?.set_name || 'DM';
    },

    dt(iso) {
      try { return iso ? new Date(iso).toLocaleString() : ''; } catch { return ''; }
    },

    unread(pid) {
      return this.unreadByThread.get(pid) || 0;
    },

    isMuted(th) {
      const pid = th?.public_id;
      if (!pid) return false;
      return this.mutedThreads.has(pid);
    },

    onSearchInput() {
      clearTimeout(this._debounce);
      this._debounce = setTimeout(() => this.reload(), 220);
    },

    get view() {
      return this.items;
    },

    async fetchCounts() {
      try {
        const r = await app.api('/api/users/me/chats/threads/unread-counts', { method: 'GET' });
        if (!r.ok) return;
        const j = await r.json().catch(() => ({}));
        this._applyCounts(j);
      } catch {}
    },

    _applyCounts(j) {
      if (!j || typeof j !== 'object') return;
      this.counts = j;
    },

    async reload() {
      await this.load(null, true);
    },

    async more() {
      if (!this.next || this.loading) return;
      await this.load(this.next, false);
    },

    _buildBaseUrl() {
      const params = new URLSearchParams();
      params.set('page_size', '50');
      if (this.tab && this.tab !== 'all') {
        params.set('thread_kind', this.tab);
      }
      const qv = (this.q || '').trim();
      if (qv) params.set('q', qv);
      return `/api/users/me/chats/threads/?${params.toString()}`;
    },

    async load(url = null, replace = false) {
      this.loading = replace ? true : this.loading;
      if (replace) {
        this.err = '';
        this.items = [];
        this.next = null;
        this.unreadByThread.clear();
        this.mutedThreads.clear();
      }
      const my = ++this._reqId;
      try {
        if (!url) url = this._buildBaseUrl();
        const r = await app.api(url, { method: 'GET' });
        const j = await r.json().catch(() => ({}));
        if (my !== this._reqId) return;

        const results = Array.isArray(j) ? j : (j.results || []);
        const next = Array.isArray(j) ? null : (j.next || null);

        const seen = new Set(this.items.map(x => x.public_id));
        const incoming = results.filter(x => x && x.public_id && !seen.has(x.public_id));
        this.items = replace ? results.slice() : this.items.concat(incoming);
        this.next = next;

        const me = app.me?.public_id || app.auth?.user?.public_id || null;
        for (const th of results) {
          const myPart = (th.participants || []).find(p => p.user?.public_id === me);
          if (myPart) {
            this.unreadByThread.set(th.public_id, Number(myPart.unread_count || 0));
            if (myPart.is_muted) this.mutedThreads.add(th.public_id);
            else this.mutedThreads.delete(th.public_id);
          }
        }

        this._sortItems();
        this._emitUnreadSum();
      } catch (e) {
        if (my !== this._reqId) return;
        this.err = 'Błąd ładowania wątków';
      } finally {
        if (my === this._reqId) this.loading = false;
      }
    },

    async _fetchAndInsert(pid, patch) {
      try {
        const r = await app.api(`/api/users/me/chats/threads/${encodeURIComponent(pid)}/`, {
          method: 'GET',
          silent: true,
        });
        if (!r.ok) return;
        const th = await r.json().catch(() => null);
        if (!th) return;

        if (this.tab !== 'all') {
          const kind = th.thread_kind || null;
          if (kind !== this.tab) return;
        }

        if (patch?.last_message_preview) th.last_message_preview = patch.last_message_preview;
        if (patch?.last_message_at) th.last_message_at = patch.last_message_at;

        const me = app.me?.public_id || app.auth?.user?.public_id || null;
        const myPart = (th.participants || []).find(p => p.user?.public_id === me);
        if (myPart) {
          this.unreadByThread.set(th.public_id, Number(myPart.unread_count || 0));
          if (myPart.is_muted) this.mutedThreads.add(th.public_id);
          else this.mutedThreads.delete(th.public_id);
        }

        const exists = this.items.some(x => x.public_id === th.public_id);
        if (!exists) this.items.unshift(th);
        this._sortItems();
        this._emitUnreadSum();
      } catch {}
    },

    _sortItems() {
      this.items.sort((a, b) => {
        const da = a.last_message_at ? new Date(a.last_message_at).getTime() : 0;
        const db = b.last_message_at ? new Date(b.last_message_at).getTime() : 0;
        if (db !== da) return db - da;
        const ua = a.updated_at ? new Date(a.updated_at).getTime() : 0;
        const ub = b.updated_at ? new Date(b.updated_at).getTime() : 0;
        return ub - ua;
      });
    },

    _setupObserver() {
      const el = this.$refs?.sentinel;
      if (!el || !('IntersectionObserver' in window)) return;
      this._obs = new IntersectionObserver(
        (e) => { if (e.some(x => x.isIntersecting)) this.more(); },
        { rootMargin: '240px' }
      );
      this._obs.observe(el);
    },

    _emitUnreadSum() {
      let sum = 0;
      for (const [pid, v] of this.unreadByThread.entries()) {
        if (this.mutedThreads.has(pid)) continue;
        sum += (Number(v) || 0);
      }
      window.dispatchEvent(new CustomEvent('chat:unread-total', { detail: { count: sum } }));
    },

    async toggleMute(th) {
      const pid = th?.public_id;
      if (!pid) return;
      const target = !this.isMuted(th);
      try {
        const r = await app.api(`/api/users/me/chats/threads/${encodeURIComponent(pid)}/mute/`, {
          method: 'POST',
          body: JSON.stringify({ muted: target }),
          silent: true,
        });
        if (!r.ok) return;
        if (target) this.mutedThreads.add(pid);
        else this.mutedThreads.delete(pid);

        const me = app.me?.public_id || app.auth?.user?.public_id || null;
        const idx = this.items.findIndex(x => x.public_id === pid);
        if (idx >= 0) {
          const parts = this.items[idx].participants || [];
          const myPart = parts.find(p => p.user?.public_id === me);
          if (myPart) myPart.is_muted = target;
        }

        this._emitUnreadSum();
      } catch (e) {
        this.err = 'Nie udało się zmienić ustawień powiadomień';
        setTimeout(() => { this.err = ''; }, 3000);
      }
    },

    async deleteThread(th) {
      const pid = th?.public_id;
      if (!pid) return;
      const ok = window.confirm('Usunąć tę rozmowę z listy?');
      if (!ok) return;
      try {
        const r = await app.api(`/api/users/me/chats/threads/${encodeURIComponent(pid)}/`, {
          method: 'DELETE',
          silent: true,
        });
        if (r.ok || r.status === 204) {
          this.items = this.items.filter(x => x.public_id !== pid);
          this.unreadByThread.delete(pid);
          this.mutedThreads.delete(pid);
          this._emitUnreadSum();
        }
      } catch (e) {
        this.err = 'Nie udało się usunąć wątku';
        setTimeout(() => { this.err = ''; }, 3000);
      }
    },
  };
};
