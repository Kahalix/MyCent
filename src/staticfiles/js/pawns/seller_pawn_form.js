// static/js/pawns/seller_pawn_form.js
window.app = window.app || {};

app.sellerPawnForm = function () {
  return {
    busy:false, err:'', ok:'',
    fv: { principal_amount:'', due_in_days:'' },

    // pickery (modale)
    catPicker:{open:false}, ciPicker:{open:false},

    // sklep
    sellerPublicId:'',

    // klient
    customer_public_id:'',
    customer:{ first_name:'', last_name:'', email:'', phone:'',
               address_line1:'', address_line2:'', postal_code:'', city:'', country:'' },

    // parametry zastawu
    principal_amount: '', principal_currency: 'PLN',
    due_in_days: 30,

    // linie (N)
    lines: [],

    async init(){
      this.catPicker = app._makeCategoryPicker?.() || this.catPicker;
      this.ciPicker  = app._makeCatalogPicker?.()  || this.ciPicker;
      await this._loadSeller();
      if (!this.lines.length) this.addLine();
    },

    async _loadSeller(){
      try {
        const r = await app.api('/api/sellers/mine/', {method:'GET'});
        if (r.ok) {
          const j = await r.json();
          this.sellerPublicId = j.public_id || '';
          window.dispatchEvent(new CustomEvent('seller:exists'));
        }
      } catch {}
    },

    // === klient (jak w offline) ===
    cust:{
      q:'', results:[], loading:false, next:null,
      async search(url=null){
        this.loading=true; this.results=[]; this.next=null;
        try{
          if (!url){
            const qs = []; const qq = (this.q||'').trim(); if (qq) qs.push(`q=${encodeURIComponent(qq)}`);
            qs.push('ordering=last_name');
            url = `/api/sellers/mine/customers/?${qs.join('&')}`;
          }
          const r = await app.api(url, {method:'GET'});
          const j = await r.json().catch(()=> ({}));
          this.results = j.results ?? (Array.isArray(j)? j : []);
          this.next = j.next ?? null;
        } finally { this.loading=false; }
      },
      async more(){ if (this.next) await this.search(this.next); },
      pick: (c) => {
        const ctx = Alpine.$data(document.querySelector('[x-data^="app.sellerPawnForm"]'));
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
        const ctx = Alpine.$data(document.querySelector('[x-data^="app.sellerPawnForm"]'));
        ctx.customer_public_id = '';
      }
    },

    // helpery — obrazek/cena dla kart ofert (jak w offline)
    img(it){
      const first = (Array.isArray(it.images) && it.images.length) ? it.images[0] : null;
      const pic = it.cover_image_url
        || first?.image_path || first?.url || first?.image_url
        || it.catalog_item?.image_path || '';
      return app.imgUrl ? app.imgUrl(pic) : (pic || 'https://placehold.co/600x600?text=%20');
    },
    priceText(it){
      if (it && typeof it.price === 'object') {
        const a = it.price.amount ?? ''; const c = it.price.currency || 'PLN';
        return (a !== '' ? a : '—') + ' ' + c;
      }
      if (typeof it?.price === 'number' || typeof it?.price === 'string') return `${it.price} PLN`;
      return '—';
    },

    // === L I N I E ===
    _newRow(){
      const uid = Math.random().toString(36).slice(2,10);
      return {
        uid,
        mode: 'SET', // 'SET' | 'CAT'
        // wspólne
        title:'', description:'', quantity:1, appraisal_amount:'', appraisal_currency:'PLN',

        // SET
        item_set: { q:'', results:[], next:null, loading:false, selected:null },

        // CAT (modal pickery + SSF)
        _selectedType:null, _selectedTypePk:'',
        _selectedCatalog:null, catalog_public_id:'',
        _schema:{type:'object', properties:{}}, attributes:{}, _schemaErr:'',

        // błędy wyświetlane przy wierszu
        _errs:{ selected:'', quantity:'', appraisal_amount:'' }
      };
    },
    addLine(){ this.lines.push(this._newRow()); this.$nextTick(()=> this._mountRowSSF(this.lines.length-1)); },
    removeLine(i){ this.lines.splice(i,1); },

    // --- SET search ---
    async searchItemSets(row, url=null){
      row.item_set.loading = true; row.item_set.results=[]; row.item_set.next=null;
      try{
        if (!url){
          const qs = ['ordering=-created_at'];
          const qq = (row.item_set.q||'').trim(); if (qq) qs.push(`search=${encodeURIComponent(qq)}`);
          url = `/api/sellers/mine/item-sets/?${qs.join('&')}`;
        }
        const r = await app.api(url, {method:'GET'});
        const j = await r.json().catch(()=> ({}));
        row.item_set.results = j.results ?? (Array.isArray(j)? j : []);
        row.item_set.next = j.next ?? null;
      } finally { row.item_set.loading=false; }
    },
    async moreItemSets(row){ if (row.item_set.next) await this.searchItemSets(row, row.item_set.next); },
    pickItemSet(row, it){ row.item_set.selected = it; row._errs.selected=''; if (!row.title) row.title = it.set_name || row.title; },
    clearItemSet(row){ row.item_set.selected = null; },

    // --- CATEGORY picker (modal) ---
    openRowCategoryPicker(i){
      const row = this.lines[i]; if (!row) return;
      this.catPicker.onPick = async (node) => {
        if (row._selectedCatalog) return;
        await this._applyTypeForRow(i, node.path, node.name);
        this._mountRowSSF(i);
      };
      this.catPicker.openAtRoot();
    },
    clearRowCategory(i){
      const row = this.lines[i]; if (!row) return;
      row._selectedType=null; row._selectedTypePk=''; row._schema={type:'object',properties:{}};
      this._mountRowSSF(i);
    },

    async _applyTypeForRow(i, path, name=''){
      const row = this.lines[i]; if (!row) return;
      row._selectedType = { name, path, children_count:0 };

      try{
        const rs = await app.api(`/api/public/catalog/categories/schema/by-path/${encodeURIComponent(path)}`, {method:'GET'});
        if (rs.ok){
          const d = await rs.json().catch(()=> ({}));
          row._schema = d.schema || {type:'object',properties:{}};
        } else row._schema = {type:'object',properties:{}};
      } catch { row._schema = {type:'object',properties:{}}; }

      try{
        const rr = await app.api(`/api/public/catalog/categories/resolve?path=${encodeURIComponent(path)}`, {method:'GET'});
        const j  = await rr.json().catch(()=> ({}));
        row._selectedTypePk = j?.type_id || '';
      } catch { row._selectedTypePk=''; }
    },

    // --- CATALOG ITEM picker (modal) ---
    openRowCatalogPicker(i){
      const row = this.lines[i]; if (!row) return;
      this.ciPicker.onPick = async (it) => {
        row.catalog_public_id = it.public_id || '';
        row._selectedCatalog = {
          id: it.id || it.uuid || '',
          public_id: row.catalog_public_id,
          item_name: it.item_name || it.name || '',
          type: it.type || {},
          image_path: it.image_path || it.image_url || it.image || ''
        };
        if (!row.title) row.title = row._selectedCatalog.item_name || row.title;

        if (it?.type?.path) await this._applyTypeForRow(i, it.type.path, it.type.name || '');

        // prefill atrybutów
        try{
          if (row.catalog_public_id) {
            const r = await app.api(`/api/sellers/mine/item-sets/prefill?catalog_public_id=${encodeURIComponent(row.catalog_public_id)}`, {method:'GET'});
            if (r.ok){
              const d = await r.json().catch(()=> ({}));
              row.attributes = app._mergeAttrsPreferCurrent?.(row.attributes, d.attributes || {}) || (d.attributes || {});
            }
          }
        } catch {}

        this._mountRowSSF(i);
      };
      this.ciPicker.openWith(row._selectedType?.path || '');
    },
    clearRowCatalog(i){
      const row = this.lines[i]; if (!row) return;
      row._selectedCatalog=null; row.catalog_public_id='';
    },

    // --- SSF (atrybuty)
    _mountRowSSF(i){
      const row = this.lines[i]; if (!row) return;
      const el = document.getElementById('pawn_attrs_ssf_'+row.uid);
      if (!el) return;
      const val = (row.attributes && Object.keys(row.attributes).length) ? row.attributes : {};
      app.ssf.mount(el, row._schema, val);
    },
    _readRowSSF(i){
      const el = document.getElementById('pawn_attrs_ssf_'+this.lines[i].uid);
      try { return app.ssf.read(el) || {}; } catch { return {}; }
    },

    // === PAYLOAD ===
    _customerPayload(){
      const c = this.customer;
      const any = Object.values(c).some(v => (v ?? '') !== '');
      if (!any && !this.customer_public_id) return undefined;
      return {
        ...(this.customer_public_id ? {customer_public_id: this.customer_public_id} : {}),
        customer_snapshot: this.customer_public_id ? undefined : {
          first_name: c.first_name || undefined,
          last_name:  c.last_name  || undefined,
          email:      c.email      || undefined,
          phone:      c.phone      || undefined,
          address: {
            line1: c.address_line1 || undefined,
            line2: c.address_line2 || undefined,
            postal_code: c.postal_code || undefined,
            city: c.city || undefined,
            country: c.country || undefined
          }
        }
      }
    },

    _linePayload(row, idx){
      if (row.mode === 'CAT') row.attributes = this._readRowSSF(idx);

      const qty = Math.max(1, parseInt(row.quantity||1,10)) || 1;

      const norm = app.moneyNormalize({ amount: (row.appraisal_amount ?? '').toString().trim(), currency: row.appraisal_currency || 'PLN' });
      const appraisal_value = (norm && app.moneyAmount(norm) != null) ? norm.amount : null;

      if (row.mode === 'SET' && row.item_set.selected?.public_id){
        return {
          title: (row.title||'').trim() || undefined,
          description: (row.description||'').trim() || '',
          quantity: qty,
          appraisal_value,
          item_set_public_id: row.item_set.selected.public_id
        };
      }

      const t  = row._selectedType;
      const ci = row._selectedCatalog;
      const snap = {
        set_name: (row.title||ci?.item_name||'Pozycja'),
        description: row.description || '',
        price: null, currency: null,
        condition: 'USED',
        length_cm: null, width_cm: null, height_cm: null,
        weight_kg: null,
        type_path: t?.path || t?.full_path || null,
        catalog_item_public_id: ci?.public_id || null,
        attributes: row.attributes || {},
        seller_slug: null
      };
      return {
        title: (row.title||'').trim() || undefined,
        description: (row.description||'').trim() || '',
        quantity: qty,
        appraisal_value,
        item_snapshot: snap
      };
    },

    // === WALIDACJA ===
    _validate(){
      this.err=''; this.fv = { principal_amount:'', due_in_days:'' };
      let ok = true;

      const p = app.moneyNormalize({ amount: (this.principal_amount ?? '').toString().trim(), currency: this.principal_currency || 'PLN' });
      const pAmt = app.moneyAmount(p);
      if (!p || pAmt === null || pAmt <= 0){
        this.fv.principal_amount = 'Podaj prawidłową, dodatnią kwotę.';
        ok = false;
      }

      const dd = parseInt(this.due_in_days||0,10);
      if (!Number.isFinite(dd) || dd < 1){ this.fv.due_in_days = 'Termin (dni) musi być liczbą ≥ 1.'; ok=false; }

      if (!this.lines.length){ this.err = 'Dodaj co najmniej jedną pozycję.'; return false; }
      for (const r of this.lines){
        r._errs = { selected:'', quantity:'', appraisal_amount:'' };

        if (r.mode === 'SET' && !r.item_set?.selected){ r._errs.selected = 'Wybierz pozycję z ofert.'; ok=false; }
        if (r.mode === 'CAT' && !(r._selectedCatalog || r._selectedType)){ r._errs.selected = 'Wybierz z katalogu albo kategorię.'; ok=false; }

        const q = Math.max(1, parseInt(r.quantity||1,10));
        if (!Number.isFinite(q) || q<1){ r._errs.quantity = 'Ilość musi być liczbą ≥ 1.'; ok=false; }

        const aa = (r.appraisal_amount||'').toString().trim();
        if (aa){
          const m = app.moneyNormalize({amount:aa, currency:r.appraisal_currency||'PLN'});
          if (!m || app.moneyAmount(m) == null){ r._errs.appraisal_amount = 'Wycena musi być liczbą.'; ok=false; }
        }
      }

      const em = (this.customer.email||'').trim();
      if (em && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)){ this.err = 'Nieprawidłowy email klienta.'; ok=false; }
      const ph = (this.customer.phone||'').trim();
      const digits = ph.replace(/\D+/g,''); if (!this.err && ph && digits.length<6){ this.err='Telefon wygląda na zbyt krótki.'; ok=false; }

      if (!ok){
        if (!this.err) this.err = 'Popraw zaznaczone pola.';
        this._focusFirstError();
      }
      return ok;
    },

    _focusFirstError(){
      this.$nextTick(()=>{
        if (this.fv.principal_amount) { document.getElementById('pawn_principal_amount')?.focus(); return; }
        if (this.fv.due_in_days)       { document.getElementById('pawn_due_days')?.focus(); return; }
        const row = this.lines.find(r => r._errs.selected || r._errs.quantity || r._errs.appraisal_amount);
        if (!row) return;
        if (row._errs.quantity) { document.getElementById(`pawn_qty_${row.uid}`)?.focus(); return; }
        if (row._errs.appraisal_amount) { document.getElementById(`pawn_app_${row.uid}`)?.focus(); return; }
      });
    },

    _applyBackendErrors(j){
      const root = j?.errors || j || {};
      const nf = (root.non_field_errors && Array.isArray(root.non_field_errors)) ? root.non_field_errors.join('; ') : '';

      if (root.principal){
        this.fv.principal_amount = Array.isArray(root.principal) ? root.principal.join('; ') : String(root.principal);
      }
      if (root.due_in_days){ this.fv.due_in_days = Array.isArray(root.due_in_days) ? root.due_in_days.join('; ') : String(root.due_in_days); }

      if (Array.isArray(root.lines)){
        for (let i=0; i<root.lines.length && i<this.lines.length; i++){
          const e = root.lines[i] || {};
          const row = this.lines[i];
          if (!row._errs) row._errs = { selected:'', quantity:'', appraisal_amount:'' };
          if (e.quantity) row._errs.quantity = Array.isArray(e.quantity) ? e.quantity.join('; ') : String(e.quantity);
          if (e.appraisal_value){
            row._errs.appraisal_amount = Array.isArray(e.appraisal_value) ? e.appraisal_value.join('; ') : String(e.appraisal_value);
          }
          if (e.item_set_public_id) row._errs.selected = Array.isArray(e.item_set_public_id) ? e.item_set_public_id.join('; ') : String(e.item_set_public_id);
          if (e.item_snapshot)      row._errs.selected = Array.isArray(e.item_snapshot) ? e.item_snapshot.join('; ') : String(e.item_snapshot);
          if (e.attributes){ row._schemaErr = Array.isArray(e.attributes) ? e.attributes.join('\n') : String(e.attributes); }
        }
      }

      this.err = app.errText?.(j) || nf || j?.detail || 'Błąd walidacji.';
      this._focusFirstError();
    },

    // === SAVE ===
    async save(){
      this.busy=true; this.err=''; this.ok='';
      try{
        if (!this.sellerPublicId){ this.err='Brak sklepu.'; return; }

        for (let i=0;i<this.lines.length;i++){
          if (this.lines[i].mode === 'CAT') this.lines[i].attributes = this._readRowSSF(i);
        }
        if (!this._validate()) return;

        const pn = app.moneyNormalize({ amount: (this.principal_amount ?? '').toString().trim(), currency: this.principal_currency || 'PLN' });
        const principal = pn?.amount || '';

        const payload = {
          seller_public_id: this.sellerPublicId,
          principal,
          due_in_days: Math.max(1, parseInt(this.due_in_days||30,10)) || 30,
          lines: this.lines.map((r,idx) => this._linePayload(r, idx))
        };

        const cp = this._customerPayload();
        if (cp?.customer_public_id) payload.customer_public_id = cp.customer_public_id;
        if (cp?.customer_snapshot)  payload.customer_snapshot  = cp.customer_snapshot;

        const r = await app.api('/api/sellers/mine/pawns/create/', { method:'POST', body: JSON.stringify(payload) });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok){ this._applyBackendErrors(j); return; }

        app.ok('Utworzono zastaw.');
        app.goto(`/seller/pawns/${j.public_id}`);
      } catch(e){
        this.err=e?.message || 'Błąd';
        app.error?.(this.err);
      } finally { this.busy=false; }
    }
  };
};
