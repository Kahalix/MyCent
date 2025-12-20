window.app = window.app || {};

app.cartPage = function () {
  return {
    loading: false,
    err: '', ok: '',
    items: [], // { public_id, quantity, item: ItemSetPublicResponse }
    payment: 'ONLINE_PAYMENT', // zostawiamy dla zgodności z backendem (nie pokazujemy w UI)
    checkingOut: false,

    async init(){ await this.reload(); },

    async reload(){
      this.loading = true; this.err=''; this.ok='';
      try{
        const r = await app.api('/api/users/me/cart/', { method:'GET' });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok){ this.err = app.errText?.(j) || 'Nie udało się wczytać koszyka.'; return; }
        this.items = Array.isArray(j.items) ? j.items : [];
        window.dispatchEvent(new CustomEvent('cart:changed', { detail:{ source:'reload' }}));
      } catch(e){ this.err = e?.message || 'Błąd sieci.'; }
      finally{ this.loading = false; }
    },

    img(it){
      const url = it?.item?.cover_image_url
        || it?.item?.catalog_item?.image_path
        || it?.item?.images?.[0]?.image_path
        || it?.item?.images?.[0]?.image
        || 'https://placehold.co/160x160?text=%20';
      return app.imgUrl ? app.imgUrl(url) : url;
    },

    itemUrl(it){
      const slug = it?.item?.slug || it?.item?.public_id || '';
      return slug ? `/i/${slug}` : '/offers';
    },

    priceAmount(it){
      const p = it?.item?.price;
      if (!p) return 0;
      if (typeof p === 'number') return p;
      if (typeof p === 'string') return parseFloat(p) || 0;
      const a = p.amount ?? p.net ?? p.gross;
      return parseFloat(a) || 0;
    },
    currency(it){ const p = it?.item?.price; return p?.currency || 'PLN'; },

    lineTotal(it){ return this.priceAmount(it) * (parseInt(it.quantity,10)||0); },

    total(){ return this.items.reduce((s,it)=> s + this.lineTotal(it), 0); },

    async inc(it){ await this.setQty(it, (parseInt(it.quantity,10) || 0) + 1); },
    async dec(it){ await this.setQty(it, (parseInt(it.quantity,10) || 0) - 1); },

    async setQty(it, q){
      this.err=''; this.ok='';
      try{
        const pid = it?.item?.public_id || it?.item?.id;
        if (!pid) return;
        const r = await app.api(`/api/users/me/cart/items/${encodeURIComponent(pid)}/`, {
          method:'PATCH', body: JSON.stringify({ quantity: Math.max(0, parseInt(q||0,10)) })
        });
        if (r.status === 204){
          this.items = this.items.filter(x => (x?.item?.public_id || x?.item?.id) !== pid);
          app.info?.('Usunięto z koszyka.');
        } else {
          const j = await r.json().catch(()=> ({}));
          if (!r.ok){ app.error?.(app.errText?.(j) || 'Nie udało się zaktualizować ilości.'); return; }
          const idx = this.items.findIndex(x => (x?.item?.public_id || x?.item?.id) === pid);
          if (idx >= 0) this.items[idx] = j;
        }
        window.dispatchEvent(new CustomEvent('cart:changed', { detail:{ source:'set-qty' }}));
      } catch(e){ app.error?.(e?.message || 'Błąd'); }
    },

    async remove(it){
      const pid = it?.item?.public_id || it?.item?.id;
      if (!pid) return;
      try{
        const r = await app.api(`/api/users/me/cart/items/${encodeURIComponent(pid)}/remove/`, { method:'DELETE' });
        if (r.ok || r.status === 204) {
          this.items = this.items.filter(x => (x?.item?.public_id || x?.item?.id) !== pid);
          app.ok?.('Usunięto.');
          window.dispatchEvent(new CustomEvent('cart:changed', { detail:{ source:'remove' }}));
        }
      } catch{}
    },

    async clear(){
      try{
        const r = await app.api('/api/users/me/cart/clear/', { method:'DELETE' });
        if (r.ok || r.status === 204){
          this.items = [];
          app.ok?.('Koszyk wyczyszczony.');
          window.dispatchEvent(new CustomEvent('cart:changed', { detail:{ source:'clear' }}));
        }
      } catch{}
    },

    async checkout(){
      if (!this.items.length) return;
      this.checkingOut = true; this.err=''; this.ok='';
      try{
        const key = 'cart-' + Date.now() + '-' + Math.random().toString(36).slice(2,8);
        const payload = {};
        if (this.payment) payload.payment_method = this.payment; // zgodność z API

        const r = await app.api('/api/users/me/cart/checkout/', {
          method:'POST',
          headers: { 'Idempotency-Key': key },
          body: JSON.stringify(payload)
        });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok){ this.err = app.errText?.(j) || 'Nie udało się sfinalizować zamówienia.'; app.error?.(this.err); return; }
        this.items = [];
        window.dispatchEvent(new CustomEvent('cart:changed', { detail:{ source:'checkout' }}));
        this.ok = 'Zamówienie złożone. Przechodzę do szczegółów…';
        app.ok?.(this.ok);

        let firstOrderId = null;
        if (Array.isArray(j) && j.length && j[0]?.public_id) firstOrderId = j[0].public_id;
        if (Array.isArray(j.orders) && j.orders.length && j.orders[0]?.public_id) firstOrderId = j.orders[0].public_id;
        if (j.order?.public_id) firstOrderId = j.order.public_id;

        app.goto(firstOrderId ? ('/orders/'+firstOrderId) : '/orders');
      } catch(e){
        this.err = e?.message || 'Błąd checkoutu.';
        app.error?.(this.err);
      } finally { this.checkingOut = false; }
    }
  };
};
