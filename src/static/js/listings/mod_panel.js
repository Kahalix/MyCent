window.app = window.app || {};

app.moderationUserOffersList = function () {
  return {
    items: [],
    loading: false,
    err: '',
    next: null,
    q: '',
    ordering: '-created_at',
    statusesAll: [
      { code: 'AVAILABLE', label: 'Aktywne' },
      { code: 'RESERVED',  label: 'Zarezerwowane' },
      { code: 'CLOSED',    label: 'Zakończone' },
      { code: 'SUSPENDED', label: 'Zawieszone' }
    ],
    statusSel: new Set(),
    _debounce: null,
    _reqId: 0,
    _obs: null,

    init() {
      this.reload();
      this.$nextTick(() => this._setupObserver());
    },

    destroy() {
      if (this._obs) {
        try { this._obs.disconnect(); } catch {}
        this._obs = null;
      }
    },

    _setupObserver() {
      if (!('IntersectionObserver' in window)) return;
      const el = this.$refs?.sentinel;
      if (!el) return;
      this._obs = new IntersectionObserver((entries) => {
        if (entries.some(e => e.isIntersecting)) this.more();
      }, { rootMargin: '240px' });
      this._obs.observe(el);
    },

    onSearchInput() {
      clearTimeout(this._debounce);
      this._debounce = setTimeout(() => this.reload(), 350);
    },

    toggleStatusFilter(code) {
      if (this.statusSel.has(code)) this.statusSel.delete(code);
      else this.statusSel.add(code);
      this.reload();
    },

    clearStatuses() {
      this.statusSel.clear();
      this.reload();
    },

    resetAll() {
      this.q = '';
      this.ordering = '-created_at';
      this.statusSel.clear();
      this.reload();
    },

    sort(by) {
      this.ordering = by;
      this.reload();
    },

    reload() {
      this.load(null, true);
    },

    async more() {
      if (!this.next || this.loading) return;
      await this.load(this.next, false);
    },

    async load(url = null, replace = false) {
      this.loading = replace ? true : this.loading;
      if (replace) {
        this.err = '';
        this.items = [];
        this.next = null;
      }
      const myReq = ++this._reqId;
      try {
        if (!url) {
          const qs = [`ordering=${encodeURIComponent(this.ordering)}`, `added_by=USER`];
          const qq = (this.q || '').trim();
          if (qq) qs.push(`search=${encodeURIComponent(qq)}`);
          if (this.statusSel.size) qs.push(`statuses=${encodeURIComponent(Array.from(this.statusSel).join(','))}`);
          url = `/api/moderation/item-sets/?${qs.join('&')}`;
        }
        const r = await app.api(url, { method:'GET' });
        const j = await r.json().catch(() => ({}));
        if (myReq !== this._reqId) return;
        const results = Array.isArray(j) ? j : (j.results ?? []);
        const next = Array.isArray(j) ? null : (j.next ?? null);
        this.items = replace ? results : this.items.concat(results);
        this.next = next;
      } catch (e) {
        if (myReq !== this._reqId) return;
        this.err = 'Błąd pobierania listy';
      } finally {
        if (myReq === this._reqId) this.loading = false;
      }
    },

    img(it) {
      const first = (Array.isArray(it.images) && it.images.length) ? it.images[0] : null;
      const pic = it.cover_image_url
        || first?.image_path || first?.url || first?.image_url
        || it.catalog_item?.image_path || '';
      return app.imgUrl ? app.imgUrl(pic) : (pic || '');
    },

    priceText(it) {
      if (it && typeof it.price === 'object') {
        const a = it.price.amount ?? '';
        const c = it.price.currency || 'PLN';
        return (a !== '' ? a : '—') + ' ' + c;
      }
      if (typeof it?.price === 'number' || typeof it?.price === 'string') return `${it.price} PLN`;
      return '—';
    },

    ownerText(it) {
      const u = it?.owner;
      if (!u) return '';
      const n = [u.first_name, u.last_name].filter(Boolean).join(' ').trim();
      return n || u.email || '';
    },

    statusLabel(code) {
      return this.statusesAll.find(s => s.code === code)?.label || code || '—';
    },

    statusDotClass(code) {
      return {
        'AVAILABLE': 'bg-success',
        'RESERVED':  'bg-warning',
        'CLOSED':    'bg-error',
        'SUSPENDED': 'bg-neutral'
      }[code] || 'bg-base-300';
    },

    async setStatus(it, newStatus) {
      const id = it.public_id || it.id;
      const r = await app.api(`/api/moderation/item-sets/${id}/set-status/`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ status: newStatus })
      });
      const j = await r.json().catch(()=> ({}));
      if (!r.ok) {
        const msg = (j?.detail || 'Nie udało się zmienić statusu.');
        throw new Error(msg);
      }
      const idx = this.items.findIndex(x => (x.public_id||x.id) === id);
      if (idx >= 0) this.items[idx] = j;
      if (app.ok) app.ok('Zmieniono status');
    },

    async changeStatus(it, newStatus) {
      if (newStatus === it.status) return;
      try {
        await this.setStatus(it, newStatus);
      } catch (e) {
        this.err = e?.message || 'Błąd zmiany statusu';
        if (app.error) app.error(this.err);
        setTimeout(()=>{ this.err=''; }, 3000);
      }
    }
  };
};
