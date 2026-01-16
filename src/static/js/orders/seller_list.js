window.app = window.app || {};

app.sellerOrders = function () {
  return {
    loading: false, err: '', items: [],
    f: { kind: '', search: '', status: '' },

    _buildQuery() {
      const params = [];
      if ((this.f.kind || '').trim())   params.push(`kind=${encodeURIComponent(this.f.kind.trim())}`);
      if ((this.f.search || '').trim()) params.push(`search=${encodeURIComponent(this.f.search.trim())}`);
      if ((this.f.status || '').trim()) params.push(`status=${encodeURIComponent(this.f.status.trim())}`);
      return params.join('&');
    },

    _buildUrl() {
      const qs = this._buildQuery();
      const params = [qs, 'ordering=-created_at'].filter(Boolean).join('&');
      return `/api/sellers/mine/orders/?${params}`;
    },

    exportUrl() {
      const qs = this._buildQuery();
      return `/api/sellers/mine/orders/export.csv/?${qs}`;
    },

    async init() { await this.reload(); },

    async reload() {
      this.loading = true; this.err = ''; this.items = [];
      try {
        const r = await app.api(this._buildUrl());
        const raw = await r.json().catch(() => ({}));
        this.items = Array.isArray(raw) ? raw : (Array.isArray(raw.results) ? raw.results : []);
      } catch (e) {
        this.err = e?.message || 'Błąd';
      } finally {
        this.loading = false;
      }
    },

    async downloadExport() {
      try {
        const r = await app.api(this.exportUrl(), { method: 'GET' });
        if (!r.ok) {
          let msg = 'Nie udało się wygenerować pliku.';
          try { const j = await r.json(); msg = app.errText?.(j) || j?.detail || msg; } catch {}
          app.error(msg); return;
        }
        const blob = await r.blob();
        const cd = r.headers.get('Content-Disposition') || '';
        const filename = this._filenameFromDisposition(cd) || 'orders_export.csv';

        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 0);
        app.ok('Pobrano plik.');
      } catch (e) {
        app.error(e?.message || 'Błąd pobierania pliku.');
      }
    },

    _filenameFromDisposition(cd) {
      try {
        const star = cd.match(/filename\*\s*=\s*([^']*)''([^;]+)/i);
        if (star && star[2]) return decodeURIComponent(star[2]);
        const norm = cd.match(/filename\s*=\s*"([^"]+)"/i) || cd.match(/filename\s*=\s*([^;]+)/i);
        if (norm && norm[1]) return norm[1].trim();
      } catch {}
      return null;
    },

    // PL etykiety statusów zamówień
    statusLabel(st) {
      switch ((st || '').toUpperCase()) {
        case 'PENDING':    return 'Oczekujące';
        case 'COMPLETED':  return 'Zakończone';
        case 'CANCELLED':  return 'Anulowane';
        case 'REFUNDED':   return 'Zwrócone';
        default:           return st || '—';
      }
    }
  };
};
