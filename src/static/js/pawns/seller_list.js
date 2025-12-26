window.app = window.app || {};

app.sellerPawnsList = function () {
  const PAWN_STATUS = {
    ACTIVE: 'Aktywny',
    REDEEMED: 'Wykupiony',
    FORFEITED: 'Niewykupiony',
    CANCELLED: 'Anulowany',
  };

  return {
    loading:false, err:'',
    items: [],
    q:'', status:'', dueFrom:'', dueTo:'',

    async init(){ await this.load(); },

    statusLabel(st){ return PAWN_STATUS[st] || st; },

    apiUrl(){
      const qs = [];
      if (this.q.trim()) qs.push('search=' + encodeURIComponent(this.q.trim()));
      if (this.status) qs.push('status=' + encodeURIComponent(this.status));
      if (this.dueFrom) qs.push('due_from=' + encodeURIComponent(this.dueFrom));
      if (this.dueTo) qs.push('due_to=' + encodeURIComponent(this.dueTo));
      return '/api/sellers/mine/pawns/?' + qs.join('&');
    },

    exportUrl(){
      const qs = [];
      if (this.q.trim()) qs.push('search=' + encodeURIComponent(this.q.trim()));
      if (this.status) qs.push('status=' + encodeURIComponent(this.status));
      if (this.dueFrom) qs.push('due_from=' + encodeURIComponent(this.dueFrom));
      if (this.dueTo) qs.push('due_to=' + encodeURIComponent(this.dueTo));
      return '/api/sellers/mine/pawns/export.csv/' + (qs.length ? ('?' + qs.join('&')) : '');
    },

    async load(){
      this.loading = true; this.err='';
      try{
        const r = await app.api(this.apiUrl(), { method:'GET' });
        const j = await r.json().catch(()=> ({}));
        this.items = Array.isArray(j) ? j : (j.results || []);
      } catch(e){ this.err = e?.message || 'Błąd'; }
      finally { this.loading = false; }
    },

    async exportCsv(){
      try{
        const r = await app.api(this.exportUrl(), { method:'GET' });
        if (!r.ok){
          let msg = 'Nie udało się wyeksportować CSV.';
          try { const j = await r.json(); msg = app.errText?.(j) || j?.detail || msg; } catch {}
          app.error(msg); return;
        }
        const blob = await r.blob();
        const cd = r.headers.get('Content-Disposition') || '';
        const filename = this._filenameFromDisposition(cd) || 'pawns_export.csv';

        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 0);
        app.ok('Pobrano CSV.');
      } catch(e){ app.error(e?.message || 'Błąd pobierania pliku.'); }
    },

    _filenameFromDisposition(cd){
      try{
        const star = cd.match(/filename\*\s*=\s*([^']*)''([^;]+)/i);
        if (star && star[2]) return decodeURIComponent(star[2]);
        const norm = cd.match(/filename\s*=\s*"([^"]+)"/i) || cd.match(/filename\s*=\s*([^;]+)/i);
        if (norm && norm[1]) return norm[1].trim();
      } catch {}
      return null;
    },

    badgeCls(st){
      switch (st) {
        case 'ACTIVE': return 'badge-success';
        case 'REDEEMED': return 'badge-neutral';
        case 'FORFEITED': return 'badge-warning';
        case 'CANCELLED': return 'badge-ghost';
        default: return 'badge-ghost';
      }
    }
  }
};
