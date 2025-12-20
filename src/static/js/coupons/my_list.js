// static/js/coupons/my_list.js
window.app = window.app || {};

app.userCouponsList = function(){
  return {
    loading:false, err:'', items:[], next:null,
    redeemed:'', q:'',

    async init(){ await this.load(); },

    apiUrl(){
      const qs = [];
      if (this.redeemed === 'true')  qs.push('redeemed=true');
      if (this.redeemed === 'false') qs.push('redeemed=false');
      return '/api/users/me/coupons/?' + qs.join('&');
    },

    async load(url=null){
      this.loading=true; this.err=''; this.items=[]; this.next=null;
      try{
        if (!url) url = this.apiUrl();
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
      return this.items.filter(uc => {
        const c = uc.coupon || {};
        return this._contains(this.discountText(c), q) || this._contains(c.code||'', q) || this._contains(uc.public_id||'', q);
      });
    },
    discountText(c){
      if (!c) return '—';
      if (c.discount_type === 'PERCENTAGE') {
        const pct = (c.discount_value?.amount ?? c.discount_value ?? '').toString().replace(',', '.');
        const cap = c.max_discount_value ? ` (do ${app.moneyText(c.max_discount_value)})` : '';
        return `${pct}%${cap}`;
      }
      return app.moneyText(c.discount_value) || '—';
    },
    minPurchaseText(c){ return c?.min_purchase_value ? `Min. wartość zamówienia: ${app.moneyText(c.min_purchase_value)}` : ''; },
    expiresText(c){
      if (!c?.expiration_date) return 'Bez terminu ważności';
      try { return 'Ważny do: ' + new Date(c.expiration_date).toLocaleString(); } catch { return 'Ważny do: ' + (c?.expiration_date || '—'); }
    },

    copy(text){ try{ navigator.clipboard.writeText(String(text||'')); app.ok('Skopiowano.'); } catch { app.info(String(text||'')); } }
  };
};
