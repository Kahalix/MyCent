window.app = window.app || {};

app.buyerOrders = function () {
  return {
    loading: false,
    err: '',
    items: [],

    async init() {
      this.loading = true; this.err = '';
      try {
        const r = await app.api('/api/users/me/orders/?ordering=-created_at');
        const raw = await r.json().catch(() => ({}));
        this.items = Array.isArray(raw) ? raw : (Array.isArray(raw.results) ? raw.results : []);
      } catch (e) {
        this.err = e?.message || 'Błąd';
      } finally {
        this.loading = false;
      }
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
