// static/js/payments/list.js
window.app = window.app || {};
app.payList = function () {
  return {
    loading:false, err:'', items: [],
    async init(){
      this.loading=true; this.err='';
      try{
        const r = await app.api('/api/users/me/payments/?ordering=-created_at');
        const raw = await r.json().catch(()=> ({}));
        this.items = Array.isArray(raw) ? raw : (Array.isArray(raw.results) ? raw.results : []);
      } catch(e){ this.err=e?.message||'Błąd'; }
      finally{ this.loading=false; }
    }
  };
};
