// static/js/listings/offers_list.js
window.app = window.app || {};
app._emitToast = app._emitToast || function (type, message) {
  const detail = { type, message };
  try { window.dispatchEvent(new CustomEvent('toast', { detail })); } catch {}
  try { window.dispatchEvent(new CustomEvent('toast:show', { detail })); } catch {}
};
app.ok    = app.ok    || ((m) => app._emitToast('success', m));
app.error = app.error || ((m) => app._emitToast('error', m));
app.api   = app.api   || ((url, opts = {}) => fetch(url, { credentials: 'include', ...opts }));
app.imgUrl= app.imgUrl|| (p => p || 'https://placehold.co/600x600?text=%20');

app.sellerOffersList = function () {
  return {
    items: [],
    loading: false,
    err: '',
    next: null,

    q: '',
    ordering: '-created_at',

    // filtrowanie po statusach (multi)
    statusesAll: [
      { code: 'AVAILABLE', label: 'Aktywne' },
      { code: 'CLOSED',    label: 'Zakończone' },
      { code: 'RESERVED',  label: 'Zarezerwowane' },
      { code: 'SOLD',      label: 'Sprzedane' },
      { code: 'SUSPENDED', label: 'Zawieszone' },
      { code: 'EXPIRED',   label: 'Wygasłe' },
    ],
    statusSel: new Set(), // zbiór wybranych kodów

    // prywatne
    _debounce: null,
    _reqId: 0,
    _obs: null,

    init() {
      this.reload();
      this.$nextTick(() => this._setupObserver());
    },

    destroy() {
      if (this._obs) { try { this._obs.disconnect(); } catch {} this._obs = null; }
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

    // ——— FILTRY statusów ———
    toggleStatusFilter(code) {
      if (this.statusSel.has(code)) this.statusSel.delete(code);
      else this.statusSel.add(code);
      this.reload();
    },
    clearStatuses() {
      this.statusSel.clear();
      this.reload();
    },
    markAllStatuses() {
      this.statusSel = new Set(this.statusesAll.map(s => s.code));
    },

    sort(by) { this.ordering = by; this.reload(); },
    reload() { this.load(null, /*replace*/true); },
    async more() {
      if (!this.next || this.loading) return;
      await this.load(this.next, /*replace*/false);
    },

    async load(url = null, replace = false) {
      this.loading = replace ? true : this.loading;
      if (replace) { this.err = ''; this.items = []; this.next = null; }

      const myReq = ++this._reqId;
      try {
        if (!url) {
          const qs = [`ordering=${encodeURIComponent(this.ordering)}`];
          const qq = (this.q || '').trim();
          if (qq) qs.push(`search=${encodeURIComponent(qq)}`);
          if (this.statusSel.size) qs.push(`statuses=${encodeURIComponent(Array.from(this.statusSel).join(','))}`);
          url = `/api/sellers/mine/item-sets/?${qs.join('&')}`;
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

    // ——— Helpers UI ———
    img(it) {
      const first = (Array.isArray(it.images) && it.images.length) ? it.images[0] : null;
      const pic = it.cover_image_url
        || first?.image_path || first?.url || first?.image_url
        || it.catalog_item?.image_path || '';
      return app.imgUrl(pic);
    },

    priceText(it) {
      if (it && typeof it.price === 'object') {
        const a = it.price.amount ?? '';
        const c = it.price.currency || 'PLN';
        return (a !== '' ? a : '—') + ' ' + c;
      }
      if (typeof it?.price === 'number' || typeof it?.price === 'string') {
        return `${it.price} PLN`;
      }
      return '—';
    },

    statusLabel(code) {
      return this.statusesAll.find(s => s.code === code)?.label || code || '—';
    },

    // Które statusy można ustawić (zgodnie z API)
    allowedStatusTargets(it) {
      const staff = ['AVAILABLE','RESERVED','CLOSED','SOLD','SUSPENDED'];
      const user  = ['AVAILABLE','RESERVED','CLOSED'];
      return (it?.added_by === 'USER') ? user : staff;
    },

    // Kropeczka statusu (kolor)
    statusDotClass(code) {
      return {
        'AVAILABLE': 'bg-success',
        'RESERVED':  'bg-warning',
        'CLOSED':    'bg-error',
        'SOLD':      'bg-neutral',
        'SUSPENDED': 'bg-secondary',
        'EXPIRED':   'bg-base-300'
      }[code] || 'bg-base-300';
    },

    // ——— API statusów ———
    async setStatus(it, newStatus) {
      const id = it.public_id || it.id;
      try {
        const r = await app.api(`/api/sellers/mine/item-sets/${id}/set-status/`, {
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
        app.ok('Zmieniono status');
      } catch (e) {
        this.err = e?.message || 'Błąd zmiany statusu';
        app.error(this.err);
        setTimeout(() => { this.err=''; }, 3000);
      }
    },

    async changeStatus(it, newStatus) {
      if (newStatus === it.status) return;
      const needsConfirm = (newStatus === 'SOLD' || newStatus === 'CLOSED');
      if (needsConfirm) {
        const ok = confirm(`Na pewno ustawić status: ${this.statusLabel(newStatus)}?`);
        if (!ok) return;
      }
      await this.setStatus(it, newStatus);
    },

    // ——— USUWANIE ———
    async deleteItem(it) {
      const name = it?.set_name || '(bez nazwy)';
      const ok = confirm(`Usunąć ogłoszenie:\n“${name}”?\n\nTej operacji nie można cofnąć.`);
      if (!ok) return;

      const id = it.public_id || it.id;
      try {
        const r = await app.api(`/api/sellers/mine/item-sets/${id}/`, { method: 'DELETE' });
        if (!r.ok && r.status !== 204) {
          let msg = 'Nie udało się usunąć ogłoszenia.';
          try {
            const j = await r.json();
            msg = j?.detail || msg;
          } catch {}
          throw new Error(msg);
        }
        const idx = this.items.findIndex(x => (x.public_id||x.id) === id);
        if (idx >= 0) this.items.splice(idx, 1);
        app.ok('Ogłoszenie usunięte');
      } catch (e) {
        this.err = e?.message || 'Błąd usuwania';
        app.error(this.err);
        setTimeout(() => { this.err=''; }, 3000);
      }
    },

    // ——— Nawigacja ———
    end(it)   { return this.setStatus(it, 'CLOSED');    },
    resume(it){ return this.setStatus(it, 'AVAILABLE'); },

    gotoNew(){ app.goto('/seller/offers/new'); },
    gotoEdit(id){ app.goto(`/seller/offers/${id}`); },
  };
};
