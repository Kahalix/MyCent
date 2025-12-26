window.app = window.app || {};
app.txList = function () {
  const TX_TYPE_PL = {
    "PURCHASE": "Zakup",
    "PAWN_PURCHASE": "Skup",
    "PAWN_EXTENSION": "Przedłużenie zastawu",
    "PAWN_REDEEM": "Wykup zastawu",
    "PLEDGE": "Zastaw"
  };
  const TX_STATUS_PL = {
    "PENDING": "Oczekująca",
    "COMPLETED": "Zakończona",
    "CANCELLED": "Anulowana",
    "REFUNDED": "Zwrócona"
  };

  function labelTxType(code) { return TX_TYPE_PL[code] || code || '—'; }
  function labelTxStatus(code) { return TX_STATUS_PL[code] || code || '—'; }
  function badgeForTxStatus(code) {
    if (!code) return 'badge-ghost';
    if (code === 'COMPLETED') return 'badge-success';
    if (code === 'CANCELLED') return 'badge-error';
    if (code === 'PENDING') return 'badge-warning';
    if (code === 'REFUNDED') return 'badge-info';
    return 'badge-ghost';
  }

  function formatDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    return new Intl.DateTimeFormat('pl-PL', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    }).format(d);
  }

  return {
    loading: false,
    err: '',
    items: [],

    async init(){
      this.loading = true; this.err='';
      try{
        const r = await app.api('/api/users/me/transactions/?ordering=-created_at');
        const raw = await r.json().catch(()=> ({}));
        this.items = Array.isArray(raw) ? raw : (Array.isArray(raw.results) ? raw.results : []);
      } catch(e){
        this.err = e?.message || 'Błąd';
      } finally{
        this.loading=false;
      }
    },

    labelTxType,
    labelTxStatus,
    badgeForTxStatus,
    formatDate,

    formattedAmount(t) {
      const a = t?.expected_total_amount;
      const c = t?.expected_total_currency || 'PLN';
      if (a == null) return '—';
      if (typeof app.moneyText === 'function') {
        try {
          const r = app.moneyText(a, c);
          if (r != null) return r;
        } catch {}
      }
      const num = (typeof a === 'string') ? parseFloat(a) : a;
      return (isFinite(num) ? num.toFixed(2) : String(a)) + ' ' + c;
    }
  };
};
