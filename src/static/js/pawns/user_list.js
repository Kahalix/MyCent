window.app = window.app || {};

app.userPawnsList = function () {
  const PAWN_STATUS = {
    ACTIVE: 'Aktywny',
    REDEEMED: 'Wykupiony',
    FORFEITED: 'Niewykupiony',
    CANCELLED: 'Anulowany',
  };

  return {
    loading: false, err: '',
    items: [],
    q: '', status: '', // ACTIVE | REDEEMED | FORFEITED | CANCELLED
    dueFrom: '', dueTo: '',

    async init() { await this.load(); },

    statusLabel(st){ return PAWN_STATUS[st] || st; },

    apiUrl(){
      const qs = [];
      if (this.q.trim()) qs.push('search=' + encodeURIComponent(this.q.trim()));
      if (this.status) qs.push('status=' + encodeURIComponent(this.status));
      if (this.dueFrom) qs.push('due_from=' + encodeURIComponent(this.dueFrom));
      if (this.dueTo) qs.push('due_to=' + encodeURIComponent(this.dueTo));
      return '/api/users/me/pawns/?' + qs.join('&');
    },

    async load(){
      this.loading = true; this.err = '';
      try{
        const r = await app.api(this.apiUrl(), { method:'GET' });
        const raw = await r.json().catch(()=> ({}));
        this.items = Array.isArray(raw) ? raw : (raw.results || []);
      } catch(e){ this.err = e?.message || 'Błąd'; }
      finally { this.loading = false; }
    },

    badgeCls(st){
      switch (st) {
        case 'ACTIVE': return 'badge-success';
        case 'REDEEMED': return 'badge-neutral';
        case 'FORFEITED': return 'badge-warning';
        case 'CANCELLED': return 'badge-ghost';
        default: return 'badge-ghost';
      }
    },

    isExpired(p){
      if (!p?.due_date) return false;
      try { return new Date(p.due_date) < new Date().setHours(0,0,0,0); } catch { return false; }
    }
  }
};
