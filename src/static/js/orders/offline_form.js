window.app = window.app || {};

app.sellerOrderOfflineForm = function(){
  return {
    busy:false, err:'', ok:'',

    fv: { lines:'', payment_method:'', customer_email:'', customer_phone:'', total:'' },

    q:'', items:[], next:null, loading:false, selected:null,

    status: { available: true, reserved: true },

    cart: [],
    currency: 'PLN',
    baseTotal: 0,
    targetTotal: 0,
    targetTotalInput: '',
    totalMode: 'AUTO',
    discountAmount: 0,

    payment_method:'CASH',

    customer_public_id:'',
    customer:{
      first_name:'', last_name:'', email:'', phone:'',
      address_line1:'', address_line2:'', postal_code:'', city:'', country:''
    },

    cust:{
      q:'', results:[], loading:false, next:null,
      async search(url=null){
        this.loading=true; this.results=[]; this.next=null;
        try{
          if (!url){
            const qs = [];
            const qq = (this.q||'').trim();
            if (qq) qs.push(`q=${encodeURIComponent(qq)}`);
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

    _statusQuery(){
      const vals = [];
      if (this.status.available) vals.push('AVAILABLE');
      if (this.status.reserved)  vals.push('RESERVED');
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

    pick(it){ this.selected = it || null; },
    clear(){ this.selected = null; },

    img(it){
      const first = (Array.isArray(it.images) && it.images.length) ? it.images[0] : null;
      const pic = it.cover_image_url
        || first?.image_path || first?.url || first?.image_url
        || it.catalog_item?.image_path || '';
      return app.imgUrl(pic);
    },

    _moneyFromAny(v){
      if (!v) return { amount: 0, currency: this.currency || 'PLN' };
      if (typeof v === 'object'){
        const a = v.amount ?? 0;
        const c = v.currency || this.currency || 'PLN';
        const n = Number(String(a).replace(',', '.'));
        return { amount: Number.isFinite(n) ? n : 0, currency: c };
      }
      const n = Number(String(v).replace(',', '.'));
      return { amount: Number.isFinite(n) ? n : 0, currency: this.currency || 'PLN' };
    },

    priceText(it){
      const p = this._moneyFromAny(it?.price);
      return `${p.amount.toFixed(2)} ${p.currency}`;
    },

    _round2(x){
      const n = Number(x);
      if (!Number.isFinite(n)) return 0;
      return Math.round((n + Number.EPSILON) * 100) / 100;
    },

    moneyText(amount, currency){
      const a = this._round2(amount);
      return `${a.toFixed(2)} ${currency || this.currency || 'PLN'}`;
    },

    addSelectedToCart(){
      if (!this.selected) return;

      const pid = String(this.selected.public_id || this.selected.id || '').trim();
      if (!pid) return;

      const p = this._moneyFromAny(this.selected.price);
      if (p.currency) this.currency = p.currency;

      const ln = {
        _key: `${pid}_${Date.now()}_${Math.random().toString(16).slice(2)}`,
        item_public_id: pid,
        set_name: this.selected.set_name || '',
        type_path: this.selected.type?.path || '',
        quantity: 1,
        currency: p.currency || this.currency || 'PLN',
        base_unit_price: this._round2(p.amount),
        unit_price: this._round2(p.amount),
        line_total: this._round2(p.amount)
      };

      this.cart.push(ln);
      this.selected = null;
      this.fv.lines = '';
      this._recalcTotals();
    },

    removeLine(idx){
      this.cart.splice(idx, 1);
      this._recalcTotals();
    },

    onQtyChange(idx){
      const ln = this.cart[idx];
      if (!ln) return;
      const q = Math.max(1, parseInt(ln.quantity || 1, 10));
      ln.quantity = Number.isFinite(q) ? q : 1;
      this._recalcTotals();
    },

    resetTotalToBase(){
      this.totalMode = 'AUTO';
      this._recalcTotals();
    },

    onTargetTotalInput(){
      const raw = String(this.targetTotalInput || '').trim();
      const n = Number(raw.replace(',', '.'));
      if (!Number.isFinite(n) || n < 0){
        this.fv.total = 'Podaj poprawną sumę (0 lub więcej).';
        return;
      }
      this.fv.total = '';
      this.totalMode = 'MANUAL';
      this.targetTotal = this._round2(n);
      this._applyRatio();
    },

    _recalcTotals(){
      const cur = this.currency || 'PLN';
      this.currency = cur;

      const base = this.cart.reduce((acc, ln) => {
        const q = Math.max(1, parseInt(ln.quantity || 1, 10));
        const lineBase = this._round2((ln.base_unit_price || 0) * q);
        return acc + lineBase;
      }, 0);

      this.baseTotal = this._round2(base);

      if (this.totalMode === 'AUTO'){
        this.targetTotal = this.baseTotal;
        this.targetTotalInput = this.targetTotal.toFixed(2);
      } else {
        if (!this.targetTotalInput){
          this.targetTotalInput = (this.targetTotal || 0).toFixed(2);
        }
      }

      this._applyRatio();
    },

    _applyRatio(){
      const base = this._round2(this.baseTotal);
      const target = this._round2(this.totalMode === 'AUTO' ? base : (this.targetTotal || 0));

      if (this.totalMode !== 'AUTO'){
        this.targetTotalInput = target.toFixed(2);
      }

      const ratio = base > 0 ? (target / base) : 1;

      let sum = 0;
      for (let i=0;i<this.cart.length;i++){
        const ln = this.cart[i];
        const q = Math.max(1, parseInt(ln.quantity || 1, 10));
        ln.quantity = q;

        const u = this._round2((ln.base_unit_price || 0) * ratio);
        ln.unit_price = u < 0 ? 0 : u;

        const lt = this._round2(ln.unit_price * q);
        ln.line_total = lt;
        sum += lt;
      }

      sum = this._round2(sum);
      const diff = this._round2(target - sum);
      if (this.cart.length && diff !== 0){
        const last = this.cart[this.cart.length - 1];
        const q = Math.max(1, parseInt(last.quantity || 1, 10));
        const newLineTotal = this._round2((last.line_total || 0) + diff);
        last.line_total = newLineTotal < 0 ? 0 : newLineTotal;
        last.unit_price = this._round2(last.line_total / q);
      }

      const curSum = this._round2(this.cart.reduce((a, ln) => a + (ln.line_total || 0), 0));
      this.discountAmount = this._round2(this.baseTotal - curSum);
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
      this.fv = { lines:'', payment_method:'', customer_email:'', customer_phone:'', total:'' };
      let ok = true;

      if (!this.cart.length){
        this.fv.lines = 'Dodaj co najmniej jedną pozycję do koszyka.';
        ok = false;
      } else {
        for (const ln of this.cart){
          const q = Math.max(1, parseInt(ln.quantity||1, 10));
          if (!Number.isFinite(q) || q < 1){
            this.fv.lines = 'Każda pozycja musi mieć ilość co najmniej 1.';
            ok = false;
            break;
          }
        }
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

      if (this.totalMode === 'MANUAL'){
        const n = Number(String(this.targetTotalInput||'').replace(',', '.'));
        if (!Number.isFinite(n) || n < 0){
          this.fv.total = 'Podaj poprawną sumę (0 lub więcej).';
          ok = false;
        }
      }

      if (!ok){
        this.err = 'Popraw zaznaczone pola.';
      }
      return ok;
    },

    _applyBackendErrors(j){
      const root = j?.errors || j || {};

      if (root.payment_method){
        this.fv.payment_method = Array.isArray(root.payment_method) ? root.payment_method.join('; ') : String(root.payment_method);
      }

      if (root.lines){
        const msg = typeof root.lines === 'string'
          ? root.lines
          : (Array.isArray(root.lines) ? root.lines.join('; ') : 'Sprawdź pozycje w koszyku.');
        this.fv.lines = msg;
      }

      const c = root.customer || {};
      if (c.email){ this.fv.customer_email = Array.isArray(c.email) ? c.email.join('; ') : String(c.email); }
      if (c.phone){ this.fv.customer_phone = Array.isArray(c.phone) ? c.phone.join('; ') : String(c.phone); }

      const nf = (root.non_field_errors && Array.isArray(root.non_field_errors)) ? root.non_field_errors.join('; ') : '';
      this.err = app.errText?.(j) || nf || j?.detail || 'Błąd walidacji.';
    },

    async save(){
      this.busy=true; this.err=''; this.ok='';
      try{
        if (!this._validate()){ return; }

        const lines = this.cart.map(ln => ({
          item_public_id: String(ln.item_public_id || '').trim(),
          quantity: Math.max(1, parseInt(ln.quantity||1, 10)),
          unit_price: {
            amount: this._round2(ln.unit_price || 0).toFixed(2),
            currency: ln.currency || this.currency || 'PLN'
          }
        }));

        const payload = {
          lines,
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
