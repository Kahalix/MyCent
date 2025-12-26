// static/js/orders/seller_order_detail.js
window.app = window.app || {};

app.sellerOrderDetail = function (orderPublicId) {
  return {
    loading:false, err:'', order:null,
    isPawn:false,

    // wysyłka (sprzedaż)
    pkgTypes: [], shippingByLine:{}, expanded:{},
    statuses:['PENDING','SHIPPED','DELIVERED','CANCELLED','RETURNED'],

    // formularze per linia (x-model — brak getElementById)
    linePkgSelection: {},      // { [linePid]: package_type_public_id | '' (pickup) }
    priceOverrideByLine: {},   // { [linePid]: '12.99' }
    statusByLine: {},          // { [linePid]: 'PENDING' | ... }
    trackingByLine: {},        // { [linePid]: 'XYZ123' }

    // klient
    custForm:{
      first_name:'', last_name:'', email:'', phone:'',
      address:{ line1:'', line2:'', postal_code:'', city:'', country:'' },
      document_type:'', document_number:'', birth_date:''
    },
    ensureInfo:'',
    custSearch:{ q:'', results:[], loading:false },

    // UI schemas (atrybuty)
    _uiByPath: Object.create(null),
    uiNonce: 0,

    async init(){
      this.loading=true; this.err='';
      try{
        const ro = await app.api(`/api/sellers/mine/orders/${orderPublicId}/`);
        this.order = await ro.json();
        this.isPawn = (this.order?.tx_type === 'PAWN_PURCHASE');

        // snapshot klienta
        const s = this.order?.customer_snapshot || {};
        const addr = s.address || {};
        this.custForm = {
          first_name: s.first_name || '',
          last_name:  s.last_name  || '',
          email:      s.email      || '',
          phone:      s.phone      || '',
          address: {
            line1: addr.line1 || '',
            line2: addr.line2 || '',
            postal_code: addr.postal_code || '',
            city: addr.city || '',
            country: addr.country || ''
          },
          document_type:  (s.document?.type || ''),
          document_number:(s.document?.number || ''),
          birth_date:     (s.birth_date || '')
        };

        if (!this.isPawn) {
          this._indexShippings();
          await this._loadPkgTypes();
          this._seedAllLineInputs();
        }

        // prefetch ui dla linii (atrybuty)
        (this.order?.order_lines || []).forEach(ln => {
          const path = ln?.item_snapshot?.type_path || ln?.item?.type?.path || '';
          if (path) this._ensureUiSchema(path).catch(()=>{});
        });
      } catch(e){ this.err = e?.message || 'Błąd'; }
      finally{ this.loading=false; }
    },

    async _loadPkgTypes(){
      try{
        const rp = await app.api(`/api/public/shipping/package-types/`);
        const raw = await rp.json().catch(()=> ({}));
        this.pkgTypes = Array.isArray(raw) ? raw : (Array.isArray(raw.results) ? raw.results : []);
      } catch { this.pkgTypes = []; }
    },

    // ---- wysyłka (sprzedaż) ----
    _indexShippings(){
      this.shippingByLine = {};
      (this.order?.shippings || []).forEach(s => this.shippingByLine[s.order_line_public_id] = s);
    },
    lineShipping(linePid){ return this.shippingByLine[linePid] || null; },

    toggle(pid){
      this.expanded[pid] = !this.expanded[pid];
      if (this.expanded[pid]) this._seedLineInputs(pid);
    },
    isExpanded(pid){ return !!this.expanded[pid]; },

    _seedLineInputs(linePid){
      const ship = this.lineShipping(linePid);
      if (!(linePid in this.linePkgSelection))   this.linePkgSelection[linePid]   = ship?.package_type_public_id || '';
      if (!(linePid in this.priceOverrideByLine)) this.priceOverrideByLine[linePid] = '';
      if (!(linePid in this.statusByLine))       this.statusByLine[linePid]       = ship?.shipping_status || 'PENDING';
      if (!(linePid in this.trackingByLine))     this.trackingByLine[linePid]     = ship?.tracking_number || '';
    },
    _seedAllLineInputs(){
      (this.order?.order_lines || []).forEach(ln => this._seedLineInputs(ln.public_id));
    },

    async addShipping(linePid, pkgPid, priceOverride){
      try{
        const body = {};
        const pkg = (pkgPid||'').trim();
        if (pkg !== '') body.package_type_public_id = pkg;  // '' => PICKUP
        const p = (priceOverride||'').toString().trim();
        if (p !== '') body.price = p.replace(',', '.');

        const r = await app.api(`/api/sellers/mine/orders/${this.order.public_id}/lines/${linePid}/shipping/`, {
          method:'POST', body: JSON.stringify(body)
        });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok){ app.error?.(app.errText?.(j) || 'Nie udało się ustawić wysyłki.'); return; }

        app.ok?.('Dodano/zmieniono wysyłkę');

        const ro = await app.api(`/api/sellers/mine/orders/${this.order.public_id}/`);
        this.order = await ro.json();
        this._indexShippings();
        this._seedAllLineInputs();
      } catch(e){ app.error?.(e?.message || 'Błąd'); }
    },

    async updateShippingStatus(linePid){
      try{
        const ship = this.lineShipping(linePid);
        if (!ship){ app.error?.('Brak wysyłki dla tej linii'); return; }

        const payload = {};
        const s = (this.statusByLine[linePid] || '').toString().trim();
        const t = (this.trackingByLine[linePid] || '').toString().trim();
        if (s) payload.shipping_status = s;
        if (t) payload.tracking_number = t;

        const r = await app.api(`/api/sellers/mine/orders/${this.order.public_id}/lines/${linePid}/shipping/${ship.public_id}/`, {
          method:'PATCH', body: JSON.stringify(payload)
        });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok){ app.error?.(app.errText?.(j) || 'Nie udało się zapisać statusu.'); return; }

        app.ok?.('Zapisano status wysyłki');

        const ro = await app.api(`/api/sellers/mine/orders/${this.order.public_id}/`);
        this.order = await ro.json();
        this._indexShippings();
        this._seedAllLineInputs();
      } catch(e){ app.error?.(e?.message || 'Błąd'); }
    },

    // ---- eksport (tylko w panelu podsumowania) ----
    async downloadReceipt(kind){
      try{
        const url = `/api/sellers/mine/orders/${this.order.public_id}/receipt.${kind}`;
        const r = await app.api(url, { method: 'GET' });
        if (!r.ok){
          let msg = 'Nie udało się wygenerować pliku.';
          try { const j = await r.json(); msg = app.errText?.(j) || j?.detail || msg; } catch {}
          app.error?.(msg); return;
        }
        const blob = await r.blob();
        const cd = r.headers.get('Content-Disposition') || '';
        const fallback = `receipt_${this.order.public_id}.${kind}`;
        const filename = this._filenameFromDisposition(cd) || fallback;

        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 0);
        app.ok?.('Pobrano plik.');
      } catch(e){ app.error?.(e?.message || 'Błąd pobierania pliku.'); }
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

    // ---- klient ----
    async searchCustomers(){
      this.custSearch.loading=true; this.custSearch.results=[];
      try{
        const qs = [];
        const qq = (this.custSearch.q||'').trim(); if (qq) qs.push(`q=${encodeURIComponent(qq)}`);
        const url = `/api/sellers/mine/customers/?${qs.join('&')}`;
        const r = await app.api(url,{method:'GET'});
        const j = await r.json().catch(()=> ({}));
        this.custSearch.results = j.results ?? (Array.isArray(j)? j : []);
      } finally { this.custSearch.loading=false; }
    },
    async attachCustomer(publicId){
      try{
        const r = await app.api(`/api/sellers/mine/orders/${this.order.public_id}/attach-customer/`, {
          method:'POST', body: JSON.stringify({ customer_public_id: publicId })
        });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok) throw new Error(app.errText?.(j) || 'Nie udało się połączyć klienta.');
        this.ensureInfo = 'Połączono klienta.';
        await this._reloadOrder();
      } catch(e){ app.error?.(e?.message || 'Błąd'); }
    },
    async ensureCustomer(){
      this.ensureInfo = 'Sprawdzam…';
      try{
        const r = await app.api(`/api/sellers/mine/orders/${this.order.public_id}/ensure-customer/`, {
          method:'POST', body: JSON.stringify(this.custForm)
        });
        const j = await r.json().catch(()=> ({}));
        if (r.status === 409) {
          this.ensureInfo = j?.detail || 'Znaleziono wielu kandydatów — wybierz z listy poniżej.';
          this.custSearch.results = (j?.candidates || []);
          return;
        }
        if (!r.ok) throw new Error(app.errText?.(j) || 'Nie udało się utworzyć/powiązać klienta.');
        this.ensureInfo = (j?.result === 'created') ? 'Utworzono i połączono nowego klienta.' : 'Połączono istniejącego klienta.';
        await this._reloadOrder();
      } catch(e){ this.ensureInfo=''; app.error?.(e?.message || 'Błąd'); }
    },
    async detachCustomer(){
      try{
        const r = await app.api(`/api/sellers/mine/orders/${this.order.public_id}/detach-customer/`, { method:'POST' });
        if (!r.ok){ const j=await r.json().catch(()=>({})); throw new Error(app.errText?.(j)||'Nie udało się odłączyć.'); }
        this.ensureInfo = 'Odłączono klienta.';
        await this._reloadOrder();
      } catch(e){ app.error?.(e?.message || 'Błąd'); }
    },
    async _reloadOrder(){
      const ro = await app.api(`/api/sellers/mine/orders/${this.order.public_id}/`);
      this.order = await ro.json();
      if (!this.isPawn) { this._indexShippings(); this._seedAllLineInputs(); }
    },

    // === UI schema helpers + atrybuty ===
    async _ensureUiSchema(path){
      if (!path || this._uiByPath[path]) return;
      try {
        const { ui_schema } = await app.getSchemaCached(path);
        this._uiByPath[path] = ui_schema || {};
      } catch { this._uiByPath[path] = {}; }
      finally { this.uiNonce++; }
    },
    _attrsFor(ln){
      const attrs = (ln?.item_snapshot?.attributes || ln?.item?.attributes || {}) || {};
      const path  = ln?.item_snapshot?.type_path || ln?.item?.type?.path || '';
      const ui    = path ? (this._uiByPath[path] || {}) : {};
      return { attrs, ui };
    },
    attrPairsFor(ln){
      try {
        const { attrs, ui } = this._attrsFor(ln);
        return app.attrPairs ? app.attrPairs(attrs, (ui?.attrs || ui) || {}) : Object.entries(attrs);
      } catch { return []; }
    },
    attrBadgesFor(ln){
      try {
        const { attrs, ui } = this._attrsFor(ln);
        if (!attrs || !Object.keys(attrs).length) return [];
        const UI = (ui && (ui.attrs || ui)) || {};
        const badgeKeys = new Set([...(UI.badges || UI.tags || [])]);
        const toneMap   = UI.badge_tone || {};
        const out = [];
        for (const [k, raw] of Object.entries(attrs)) {
          if (!badgeKeys.has(k)) continue;
          const label   = app.attrLabel ? app.attrLabel(k, UI) : k;
          if (typeof raw === 'boolean') {
            if (raw) out.push({ text: label, tone: toneMap[k] || 'success' });
          } else {
            const prettyV = app.attrValue ? app.attrValue(k, raw, UI) : String(raw);
            out.push({ text: `${label}: ${prettyV}`, tone: toneMap[k] || 'info' });
          }
        }
        return out;
      } catch { return []; }
    },

    // --- helpery dla badge w "Adres dostawy" ---
    pkgShipments(){
      return (this.order?.shippings || []).filter(s => (s.package_label || '') !== 'PICKUP');
    },
    pkgCount(){ return this.pkgShipments().length; },
    pkgWord(n){
      n = Number(n)||0;
      const teen = n % 100;
      if (teen >= 12 && teen <= 14) return 'paczek';
      const u = n % 10;
      if (n === 1) return 'paczka';
      if (u >= 2 && u <= 4) return 'paczki';
      return 'paczek';
    },
    shippingModeSummary(){
      const n = this.pkgCount();
      if (n === 0) return 'Odbiór osobisty';
      const total = this.order?.shipping_total;
      return `${n} ${this.pkgWord(n)}${total ? ' • ' + app.moneyText(total) : ''}`;
    },

    // === Tłumaczenia ===
    tOrderStatus(code){
      const m = { PENDING:'Oczekujące', COMPLETED:'Zakończone', CANCELLED:'Anulowane', SHIPPED:'Wysłane', DELIVERED:'Dostarczone' };
      return m[String(code||'').toUpperCase()] || (code || '');
    },
    tPaymentMethod(code){
      const m = {
        CASH:'Gotówka', ONLINE_PAYMENT:'Płatność Online',
        CREDIT_CARD:'Karta', DEBIT_CARD:'Karta debetowa',
        BANK_TRANSFER:'Przelew bankowy', CASH_ON_DELIVERY:'Pobranie',
        PAYPAL:'PayPal', BLIK:'BLIK', APPLE_PAY:'Apple Pay', GOOGLE_PAY:'Google Pay'
      };
      return m[String(code||'').toUpperCase()] || (code || '');
    },
    tShippingStatus(code){
      const m = { PENDING:'Oczekująca', SHIPPED:'Wysłana', DELIVERED:'Dostarczona', CANCELLED:'Anulowana', RETURNED:'Zwrócona' };
      return m[String(code||'').toUpperCase()] || (code || '');
    },
  };
};
