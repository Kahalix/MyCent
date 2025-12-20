// SPRZEDAŻ OFFLINE — wybór przedmiotu z ofert + autouzupełnianie klienta
window.app = window.app || {};

app.sellerOrderOfflineForm = function(){
  return {
    busy:false, err:'', ok:'',

    // walidacja pól
    fv: { selected:'', quantity:'', payment_method:'', customer_email:'', customer_phone:'' },

    // oferty
    q:'', items:[], next:null, loading:false, selected:null,

    // FILTR STATUSU
    status: { available: true, reserved: true },

    // sprzedaż
    quantity:1, payment_method:'CASH',

    // klient
    customer_public_id:'', // link do istniejącego klienta (opcjonalnie)
    customer:{
      first_name:'', last_name:'', email:'', phone:'',
      address_line1:'', address_line2:'', postal_code:'', city:'', country:''
    },

    // ====== KLIENCI (wyszukiwarka) ======
    cust:{
      q:'', results:[], loading:false, next:null,
      async search(url=null){
        this.loading=true; this.results=[]; this.next=null;
        try{
          if (!url){
            const qs = [];
            const qq = (this.q||'').trim();
            if (qq) qs.push(`q=${encodeURIComponent(qq)}`);   // <— ważne: q= zamiast search=
            qs.push('ordering=last_name');
            url = `/api/sellers/mine/customers/?${qs.join('&')}`;
          }
          const r = await app.api(url, {method:'GET'});
          const j = await r.json().catch(()=> ({}));
          this.results = j.results ?? (Array.isArray(j) ? j : []);
          this.next = j.next ?? null;
        } finally { this.loading=false; }
      },
      async more(){ if (this.next) await this.search(this.next); },
      pick: (c) => {
        const ctx = Alpine.$data(document.querySelector('[x-data^="app.sellerOrderOfflineForm"]'));
        ctx.customer_public_id = c.public_id || '';
        Object.assign(ctx.customer, {
          first_name: c.first_name || '',
          last_name:  c.last_name  || '',
          email:      c.email      || '',
          phone:      c.phone      || '',
          address_line1: c.address_line1 || '',
          address_line2: c.address_line2 || '',
          postal_code:   c.postal_code   || '',
          city:          c.city          || '',
          country:       c.country       || ''
        });
      },
      clearLink(){
        const ctx = Alpine.$data(document.querySelector('[x-data^="app.sellerOrderOfflineForm"]'));
        ctx.customer_public_id = '';
      }
    },

    async init(){ await this.search(); },

    // ====== OFERTY (lista + filtry) ======
    _statusQuery(){
      const vals = [];
      if (this.status.available) vals.push('AVAILABLE');
      if (this.status.reserved)  vals.push('RESERVED');
      // nic nie zaznaczone? — pokaż oba, żeby lista nie była pusta
      if (!vals.length) vals.push('AVAILABLE','RESERVED');
      return vals;
    },
    selectAllStatuses(){
      this.status.available = true;
      this.status.reserved  = true;
      this.search();
    },

    async search(url=null){
      this.loading=true; this.err='';
      try{
        if (!url){
          const qs = ['ordering=-created_at'];
          const qq = (this.q||'').trim(); if (qq) qs.push(`search=${encodeURIComponent(qq)}`);
          // <— filtr statusów
          this._statusQuery().forEach(s => qs.push(`statuses=${encodeURIComponent(s)}`));
          url = `/api/sellers/mine/item-sets/?${qs.join('&')}`;
        }
        const r = await app.api(url, { method:'GET' });
        const j = await r.json().catch(()=> ({}));
        this.items = j.results ?? (Array.isArray(j)? j : []);
        this.next  = j.next ?? null;
      }catch(e){ this.err=e?.message||'Błąd listy ofert.'; }
      finally{ this.loading=false; }
    },
    async more(){ if (this.next) await this.search(this.next); },

    pick(it){ this.selected = it || null; this.fv.selected=''; },
    clear(){ this.selected = null; },

    img(it){
      const first = (Array.isArray(it.images) && it.images.length) ? it.images[0] : null;
      const pic = it.cover_image_url
        || first?.image_path || first?.url || first?.image_url
        || it.catalog_item?.image_path || '';
      return app.imgUrl(pic);
    },
    priceText(it){
      if (it && typeof it.price === 'object') {
        const a = it.price.amount ?? ''; const c = it.price.currency || 'PLN';
        return (a !== '' ? a : '—') + ' ' + c;
      }
      if (typeof it?.price === 'number' || typeof it?.price === 'string') return `${it.price} PLN`;
      return '—';
    },

    _collectCustomer(){
      const c = this.customer;
      const nonEmpty = Object.values(c).some(v => (v ?? '') !== '');
      if (!nonEmpty && !this.customer_public_id) return null;
      return {
        ...(this.customer_public_id ? { customer_public_id: this.customer_public_id } : {}),
        first_name: (c.first_name||'') || undefined,
        last_name:  (c.last_name||'')  || undefined,
        email:      (c.email||'')      || undefined,
        phone:      (c.phone||'')      || undefined,
        address: {
          line1: (c.address_line1||'') || undefined,
          line2: (c.address_line2||'') || undefined,
          postal_code: (c.postal_code||'') || undefined,
          city: (c.city||'') || undefined,
          country: (c.country||'') || undefined
        }
      };
    },

    _validate(){
      // wyczyść
      this.fv = { selected:'', quantity:'', payment_method:'', customer_email:'', customer_phone:'' };
      let ok = true;

      if (!this.selected){
        this.fv.selected = 'Wybierz przedmiot z listy.';
        ok = false;
      }
      const qty = Math.max(1, parseInt(this.quantity||1, 10));
      if (!Number.isFinite(qty) || qty < 1){
        this.fv.quantity = 'Ilość musi być liczbą ≥ 1.';
        ok = false;
      }
      if (!this.payment_method){
        this.fv.payment_method = 'Wybierz metodę płatności.';
        ok = false;
      }
      const em = (this.customer.email||'').trim();
      if (em && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)){
        this.fv.customer_email = 'Nieprawidłowy adres email.';
        ok = false;
      }
      const ph = (this.customer.phone||'').trim();
      const digits = ph.replace(/\D+/g, '');
      if (ph && digits.length < 6){
        this.fv.customer_phone = 'Telefon wygląda na zbyt krótki.';
        ok = false;
      }
      if (!ok){
        this.err = 'Popraw zaznaczone pola.';
        this._focusFirstError();
      }
      return ok;
    },

    _focusFirstError(){
      // proste heurystyki focusu
      if (this.fv.selected){ return; }
      if (this.fv.quantity){ this.$nextTick(()=> document.getElementById('offline_qty')?.focus()); return; }
      if (this.fv.payment_method){ this.$nextTick(()=> document.getElementById('offline_pay')?.focus()); return; }
      if (this.fv.customer_email){ this.$nextTick(()=> document.getElementById('offline_cust_email')?.focus()); return; }
      if (this.fv.customer_phone){ this.$nextTick(()=> document.getElementById('offline_cust_phone')?.focus()); return; }
    },

    _applyBackendErrors(j){
      // DRF zwraca zwykle {"errors": {...}} lub bezpośrednio mapę pól
      const root = j?.errors || j || {};
      const nf = (root.non_field_errors && Array.isArray(root.non_field_errors)) ? root.non_field_errors.join('; ') : '';

      // ilość
      if (root.quantity){
        this.fv.quantity = Array.isArray(root.quantity) ? root.quantity.join('; ') : String(root.quantity);
      }
      // payment
      if (root.payment_method){
        this.fv.payment_method = Array.isArray(root.payment_method) ? root.payment_method.join('; ') : String(root.payment_method);
      }
      // customer.* (w naszym request to zagnieżdżone)
      const c = root.customer || {};
      if (c.email){ this.fv.customer_email = Array.isArray(c.email) ? c.email.join('; ') : String(c.email); }
      if (c.phone){ this.fv.customer_phone = Array.isArray(c.phone) ? c.phone.join('; ') : String(c.phone); }

      this.err = app.errText?.(j) || nf || j?.detail || 'Błąd walidacji.';
      this._focusFirstError();
    },

    async save(){
      this.busy=true; this.err=''; this.ok='';
      try{
        if (!this._validate()){ return; }

        const payload = {
          item_public_id: String(this.selected.public_id || this.selected.id || '').trim(),
          quantity: Math.max(1, parseInt(this.quantity||1, 10)),
          payment_method: this.payment_method || 'CASH'
        };
        const cust = this._collectCustomer();
        if (cust) payload.customer = cust;

        const r = await app.api(`/api/sellers/mine/orders/offline-checkout/`, {
          method:'POST',
          body: JSON.stringify(payload),
          autoToast: true,
          toastOn: [400,404,409,422]
        });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok){
          this._applyBackendErrors(j);
          return;
        }
        this.ok='Dodano.'; app.ok('Dodano.');
        app.goto(`/seller/orders/${j.public_id}`);
      }catch(e){
        this.err=e?.message || 'Błąd.';
        app.error?.(this.err);
      } finally { this.busy=false; }
    }
  };
};
