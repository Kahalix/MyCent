window.app = window.app || {};

app.navState = function () {
  return {
    authed: !!localStorage.getItem('lown_access'),
    theme: (app.getTheme && app.getTheme()) || 'lownLight',
    user: null,
    hasSeller: false,
    isSellerOwner: false,
    isModerator: false,
    canAdminPanel: false,
    sellerCtx: null,
    cartCount: 0,
    chatUnread: 0,
    _threadUnread: new Map(),
    _unsubInbox: null,

    init() {
      window.addEventListener('theme:changed', (e) => { this.theme = e.detail.theme; });

      window.addEventListener('cart:changed', () => { if (this.authed) this.fetchCartCount(); });
      if (this.authed) this.fetchCartCount();

      window.addEventListener('auth:changed', async (e) => {
        const now = !!e.detail?.authed;
        this.authed = now;
        if (now) {
          await this.fetchUser();
          this.fetchCartCount();
          await this.fetchChatUnread();
          this._subscribeInbox();
        } else {
          this._unsubscribeInbox();
          this.user = null;
          this.hasSeller = false;
          this.canAdminPanel = false;
          this.cartCount = 0;
          this.chatUnread = 0;
          this._threadUnread.clear();
        }
      });

      document.addEventListener('htmx:afterSettle', async () => {
        const now = !!localStorage.getItem('lown_access');
        if (now !== this.authed) {
          this.authed = now;
          if (now) {
            await this.fetchUser();
            this.fetchCartCount();
            await this.fetchChatUnread();
            this._subscribeInbox();
          } else {
            this._unsubscribeInbox();
            this.user = null;
            this.hasSeller = false;
            this.canAdminPanel = false;
            this.cartCount = 0;
            this.chatUnread = 0;
            this._threadUnread.clear();
          }
        }
      });

      window.addEventListener('seller:exists', () => { this.hasSeller = true; });

      window.addEventListener('chat:unread-total', (e) => {
        const d = e?.detail || {};
        if (d.countDeltaToZeroFor) {
          this._threadUnread.set(String(d.countDeltaToZeroFor), 0);
          this._recalcUnreadSum();
        }
      });

      if (this.authed) {
        this.fetchUser().then(async () => {
          await this.fetchChatUnread();
          this._subscribeInbox();
        });
      }
    },

    _subscribeInbox() {
      this._unsubscribeInbox();
      this._unsubInbox = app.wsHub.subscribe('inbox', (msg) => {
        try {
          if (msg.type === 'inbox.thread_updated') {
            const pid = msg.thread_public_id;
            const unread = Number(msg.unread_count || 0);
            if (pid) this._threadUnread.set(pid, unread);
            this._recalcUnreadSum();
          }
        } catch {}
      });
    },
    _unsubscribeInbox() {
      try { this._unsubInbox && this._unsubInbox(); } catch {}
      this._unsubInbox = null;
    },

    toggleTheme() { app.toggleTheme && app.toggleTheme(); },

    async fetchCartCount() {
      try {
        const r = await app.api('/api/users/me/cart/', { method: 'GET' });
        if (!r.ok) return;
        const j = await r.json().catch(() => ({}));
        const items = Array.isArray(j?.items) ? j.items : [];
        this.cartCount = items.reduce((s, it) => s + (parseInt(it.quantity, 10) || 0), 0);
      } catch {}
    },

    async fetchUser() {
      try {
        const r = await app.api('/api/users/me/');
        if (r.ok) {
          this.user = await r.json();
          app.me = this.user;
          this.canAdminPanel = !!(this.user?.is_staff || this.user?.is_superuser);
          await this.fetchSellerContext();
          this.fetchCartCount();
        }
      } catch {}
    },

    async fetchSellerContext() {
      try {
        const r = await app.api('/api/sellers/context/');
        if (!r.ok) {
          this.hasSeller = false;
          this.isSellerOwner = false;
          this.isModerator = false;
          this.sellerCtx = null;
          return;
        }
        const j = await r.json().catch(() => ({}));
        this.sellerCtx = j;
        this.hasSeller = !!j?.in_shop;
        this.isSellerOwner = j?.role === 'OWNER';
        this.isModerator = !!(j?.in_shop && ['MODERATOR', 'MANAGER', 'OWNER'].includes(j?.role));
      } catch {
        this.hasSeller = false;
        this.isSellerOwner = false;
        this.isModerator = false;
        this.sellerCtx = null;
      }
    },

    async fetchChatUnread() {
      if (!this.authed) {
        this.chatUnread = 0;
        return;
      }
      this._threadUnread.clear();
      let url = '/api/users/me/chats/threads/?page_size=10';
      let pages = 0;
      try {
        while (url && pages < 10) {
          pages++;
          const r = await app.api(url, { method: 'GET' });
          if (!r.ok) break;
          const j = await r.json().catch(() => ({}));
          const results = Array.isArray(j) ? j : (j.results || []);
          const mePid = this.user?.public_id || app.me?.public_id || null;

          for (const th of results) {
            const myPart = (th.participants || []).find(p => p.user?.public_id === mePid);
            const unread = myPart ? Number(myPart.unread_count || 0) : 0;
            this._threadUnread.set(th.public_id, unread);
          }

          url = Array.isArray(j) ? null : (j.next || null);
        }
      } catch {}
      this._recalcUnreadSum();
    },

    _recalcUnreadSum() {
      let sum = 0;
      for (const v of this._threadUnread.values()) sum += (Number(v) || 0);
      this.chatUnread = sum;
    },

    async logout() {
      if (typeof app.logout === 'function') {
        await app.logout();
        return;
      }
      try { await app.api('/api/auth/logout/', { method: 'POST' }); } catch {}
      app._onSignedOut({ redirect: true });
    }
  }
};

app.userMenu = function () {
  return {
    open: false,
    _timer: null,
    anchor: null,
    pos: { top: 0, left: 0, w: 240 },
    side: 'right',

    setAnchor(el) { this.anchor = el; },

    get style() {
      return { position: 'fixed', top: this.pos.top + 'px', left: this.pos.left + 'px', minWidth: this.pos.w + 'px' };
    },

    _place() {
      if (!this.anchor) return;
      const r = this.anchor.getBoundingClientRect();
      const gap = 8;
      const panelW = Math.max(224, r.width);

      let left = r.right - panelW;
      left = Math.max(8, Math.min(left, window.innerWidth - panelW - 8));
      const top = r.bottom + gap;

      const spaceRight = window.innerWidth - r.right;
      this.side = spaceRight < 200 ? 'left' : 'right';

      this.pos = { top, left, w: panelW };
    },

    enter() { clearTimeout(this._timer); this.open = true; this._place(); },
    leave() { clearTimeout(this._timer); this._timer = setTimeout(() => { this.open = false; }, 120); },
    toggle() { clearTimeout(this._timer); this.open = !this.open; if (this.open) this._place(); },
    close() { clearTimeout(this._timer); this.open = false; }
  };
};
