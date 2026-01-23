window.app = window.app || {};

app.savedSearchResultsPage = function (opts = {}) {
  return {
    pid: (opts.publicId || '').trim(),
    meta: null,
    results: [],
    headErr: '',
    busy: false,

    async init() {
      await this.loadMeta();
      await this.refreshNow();
      await this.loadResults();
    },

    normQS(qs) {
      const s = (qs || '').trim();
      if (!s) return '';
      return s.startsWith('?') ? s.slice(1) : s;
    },

    async loadMeta() {
      try {
        const r = await app.api(`/api/users/me/saved/searches/${encodeURIComponent(this.pid)}/`, { method: 'GET' });
        const j = await r.json().catch(() => ({}));
        this.meta = r.ok ? j : null;
      } catch {
        this.meta = null;
      }
    },

    async refreshNow() {
      if (!this.pid) return;
      this.busy = true; this.headErr = '';
      try {
        const r = await app.api(`/api/users/me/saved/searches/${encodeURIComponent(this.pid)}/refresh/`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
        });
        if (!r.ok) {
          const j = await r.json().catch(() => ({}));
          this.headErr = j?.detail || 'Błąd odświeżania.';
        }
      } catch {
        this.headErr = 'Błąd sieci.';
      } finally {
        this.busy = false;
      }
    },

    async loadResults() {
      if (!this.pid) return;
      try {
        const r = await app.api(`/api/users/me/saved/searches/${encodeURIComponent(this.pid)}/items/`, { method: 'GET' });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) { this.headErr = j?.detail || 'Błąd pobierania wyników.'; return; }
        const rows = Array.isArray(j?.results) ? j.results : (Array.isArray(j) ? j : []);
        this.results = rows.map(x => x.item);
      } catch {
        this.headErr = 'Błąd sieci.';
      }
    },

    async markSeen() {
      if (!this.pid) return;
      this.busy = true;
      try {
        const r = await app.api(`/api/users/me/saved/searches/${encodeURIComponent(this.pid)}/mark-seen/`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
        });
        if (r.ok) {
          this.results = [];
          app.ok('Zapisane wyszukiwanie oznaczone jako przeczytane.');
        }
      } finally {
        this.busy = false;
      }
    },

    offersUrl() {
      const qs = this.normQS(this.meta?.query_string || '');
      return `/offers${qs ? ('?' + qs) : ''}`;
    },

    img(it) {
      const first = (Array.isArray(it.images) && it.images.length) ? it.images[0] : null;
      const pic = it.cover_image_url
        || first?.image_path || first?.url || first?.image_url
        || it.catalog_item?.image_path || '';
      return app.imgUrl ? app.imgUrl(pic) : pic;
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

    gotoItem(it) {
      const slug = it.slug || (it.public_id || '');
      if (slug) app.goto(`/i/${slug}`);
    },
  };
};
