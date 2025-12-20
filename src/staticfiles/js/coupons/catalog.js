// static/js/coupons/catalog.js
window.app = window.app || {};

app.userCouponCatalog = function(){
  return {
    loading:false, err:'', items:[], next:null,
    q:'', buying:null, userPoints:null,

    async init(){
      await Promise.all([this.load(), this._loadUserPoints()]);
    },

    async _loadUserPoints(){
      try {
        const r = await app.api('/api/users/me/', { method:'GET' });
        if (!r.ok) return;
        const j = await r.json().catch(()=> ({}));
        if (typeof j.points !== 'undefined') this.userPoints = Number(j.points) || 0;
      } catch {}
    },

    async load(url=null){
      this.loading=true; this.err=''; this.items=[]; this.next=null;
      try{
        if (!url) url = '/api/users/me/coupons/catalog/';
        const r = await app.api(url, { method:'GET' });
        const j = await r.json().catch(()=> ({}));
        this.items = j.results ?? (Array.isArray(j)? j : []);
        this.next = j.next ?? null;
      } catch(e){ this.err = e?.message || 'Błąd listy kuponów.'; }
      finally { this.loading=false; }
    },
    async more(){
      if (!this.next) return;
      try{
        const r = await app.api(this.next, { method:'GET' });
        const j = await r.json().catch(()=> ({}));
        const more = j.results ?? (Array.isArray(j)? j : []);
        this.items = [...this.items, ...more];
        this.next = j.next ?? null;
      } catch {}
    },

    _contains(h, n){ try { return (h||'').toString().toLowerCase().includes((n||'').toString().toLowerCase()); } catch { return false; } },
    filtered(){
      const q = (this.q||'').trim();
      if (!q) return this.items;
      return this.items.filter(c => this._contains(this.discountText(c), q) || this._contains(c.code||'', q));
    },
    canBuy(c){ return c.points_cost != null && (c.quantity == null || Number(c.quantity) > 0); },
    discountText(c){
      if (c.discount_type === 'PERCENTAGE') {
        const pct = (c.discount_value?.amount ?? c.discount_value ?? '').toString().replace(',', '.');
        const cap = c.max_discount_value ? ` (do ${app.moneyText(c.max_discount_value)})` : '';
        return `${pct}%${cap}`;
      }
      return app.moneyText(c.discount_value) || '—';
    },
    minPurchaseText(c){ return c.min_purchase_value ? `Min. wartość zamówienia: ${app.moneyText(c.min_purchase_value)}` : ''; },
    expiresText(c){
      if (!c.expiration_date) return 'Bez terminu ważności';
      try { return 'Ważny do: ' + new Date(c.expiration_date).toLocaleString(); } catch { return 'Ważny do: ' + c.expiration_date; }
    },

    async buy(c){
      if (!this.canBuy(c)) return;
      this.buying = c.public_id; this.err = '';
      try{
        const r = await app.api('/api/users/me/coupons/purchase/', {
          method:'POST',
          body: JSON.stringify({ coupon_public_id: c.public_id })
        });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok){ app.error(app.errText?.(j) || j?.detail || 'Nie udało się kupić kuponu.'); return; }
        app.ok('Kupon kupiony za punkty.');
        if (c.quantity != null) c.quantity = Math.max(0, Number(c.quantity) - 1);
        if (this.userPoints != null && c.points_cost != null) this.userPoints = Math.max(0, Number(this.userPoints) - Number(c.points_cost));
      } catch(e){ app.error(e?.message || 'Błąd.'); }
      finally { this.buying = null; }
    }
  };
};
