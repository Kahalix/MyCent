window.app = window.app || {};

app.imgUrl = app.imgUrl || (p => p || 'https://placehold.co/600x600?text=%20');
app.api = app.api || ((url, opts = {}) => fetch(url, { credentials: 'include', ...opts }));
app.readJson = app.readJson || (async (r) => { try { return await r.json(); } catch { return {}; } });

app.moneyNormalize = app.moneyNormalize || (({ amount, currency = 'PLN' } = {}) => {
  const s = (amount ?? '').toString().trim().replace(',', '.');
  if (!s) return null;
  const n = Number(s);
  if (!Number.isFinite(n)) return null;
  return { amount: n, currency };
});
app.moneyAmount = app.moneyAmount || (m => (m && Number.isFinite(m.amount)) ? m.amount : null);

function _toErrorString(v) {
  if (!v) return '';
  if (typeof v === 'string') return v;
  if (Array.isArray(v)) return v.map(String).join(' ');
  if (typeof v === 'object') {
    const parts = [];
    for (const val of Object.values(v)) {
      if (!val) continue;
      if (Array.isArray(val)) parts.push(val.map(String).join(' '));
      else parts.push(String(val));
    }
    return parts.filter(Boolean).join(' ');
  }
  return String(v);
}

function _compact(obj) {
  if (!obj || typeof obj !== 'object') return obj;
  if (Array.isArray(obj)) {
    const a = obj.map(_compact).filter(v => v !== undefined);
    return a.length ? a : undefined;
  }
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    const vv = _compact(v);
    if (vv === undefined) continue;
    out[k] = vv;
  }
  return Object.keys(out).length ? out : undefined;
}

function _formatAttrErrors(errVal, row) {
  if (!errVal) return '';
  if (typeof errVal === 'string') return errVal;
  if (Array.isArray(errVal)) return errVal.map(String).join('\n');

  if (typeof errVal === 'object') {
    const labels = row?._ui_schema?.labels || {};
    const lines = [];

    for (const [k, v] of Object.entries(errVal)) {
      const label = labels[k] || k;
      if (typeof v === 'string') lines.push(`${label}: ${v}`);
      else if (Array.isArray(v)) lines.push(`${label}: ${v.map(String).join(' ')}`);
      else if (v && typeof v === 'object') lines.push(`${label}: ${_toErrorString(v)}`);
      else lines.push(`${label}: ${String(v)}`);
    }

    return lines.join('\n');
  }

  return String(errVal);
}

app.sellerPawnForm = function () {
  return {
    busy:false, err:'', ok:'',
    fv: { principal_amount:'', due_in_days:'' },

    catPicker: { open:false, loading:false, nodes:[], crumbs:[], onPick(){}, openAtRoot(){}, load(){}, enter(){}, backTo(){}, pick(){}, close(){} },
    ciPicker:  { open:false, q:'', typePath:'', loading:false, items:[], next:null, uiNonce:0, onPick(){}, openWith(){}, search(){}, more(){}, pairsFor(){ return []; }, pick(){}, close(){} },

    sellerPublicId:'',

    customer_public_id:'',
    customer:{ first_name:'', last_name:'', email:'', phone:'',
               address_line1:'', address_line2:'', postal_code:'', city:'', country:'' },

    principal_amount: '', principal_currency: 'PLN',
    due_in_days: 30,

    lines: [],

    async init(){
      if (app._makeCategoryPicker) Object.assign(this.catPicker, app._makeCategoryPicker());
      if (app._makeCatalogPicker)  Object.assign(this.ciPicker,  app._makeCatalogPicker());

      this.cust._ctx = this;

      await this._loadSeller();
      if (!this.lines.length) this.addLine();
    },

    async _loadSeller(){
      try {
        const r = await app.api('/api/sellers/mine/', {method:'GET'});
        if (r.ok) {
          const j = await app.readJson(r);
          this.sellerPublicId = j.public_id || '';
          window.dispatchEvent(new CustomEvent('seller:exists'));
        }
      } catch {}
    },

    cust:{
      _ctx:null,
      q:'', results:[], loading:false, next:null,

      async search(url=null, append=false){
        if (this.loading) return;
        this.loading=true;
        try{
          if (!append){ this.results=[]; this.next=null; }
          if (!url){
            const qs = [];
            const qq = (this.q||'').trim();
            if (qq) qs.push(`q=${encodeURIComponent(qq)}`);
            qs.push('ordering=last_name');
            url = `/api/sellers/mine/customers/?${qs.join('&')}`;
          }
          const r = await app.api(url, {method:'GET'});
          const j = await app.readJson(r);
          const fresh = j.results ?? (Array.isArray(j)? j : []);
          this.results = append ? [...this.results, ...fresh] : fresh;
          this.next = j.next ?? null;
        } finally {
          this.loading=false;
        }
      },

      async more(){
        if (!this.next || this.loading) return;
        await this.search(this.next, true);
      },

      pick(c){
        const ctx = this._ctx;
        if (!ctx) return;
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
        const ctx = this._ctx;
        if (!ctx) return;
        ctx.customer_public_id = '';
      }
    },

    img(it){
      const first = (Array.isArray(it.images) && it.images.length) ? it.images[0] : null;
      const pic = it.cover_image_url
        || first?.image_path || first?.url || first?.image_url
        || it.catalog_item?.image_path || '';
      return app.imgUrl ? app.imgUrl(pic) : (pic || 'https://placehold.co/600x600?text=%20');
    },

    priceText(it){
      if (it && typeof it.price === 'object') {
        const a = it.price.amount ?? '';
        const c = it.price.currency || 'PLN';
        return (a !== '' ? a : '—') + ' ' + c;
      }
      if (typeof it?.price === 'number' || typeof it?.price === 'string') return `${it.price} PLN`;
      return '—';
    },

    _newRow(){
      const uid = Math.random().toString(36).slice(2,10);
      return {
        uid,
        mode: 'SET',
        title:'', description:'', quantity:1, appraisal_amount:'', appraisal_currency:'PLN',
        item_set: { q:'', results:[], next:null, loading:false, selected:null },
        _selectedType:null, _selectedTypePk:'',
        _selectedCatalog:null, catalog_public_id:'',
        _schema:{type:'object', properties:{}}, _ui_schema:{}, attributes:{}, _schemaErr:'',
        _errs:{ selected:'', quantity:'', appraisal_amount:'' }
      };
    },

    addLine(){
      this.lines.push(this._newRow());
      this.$nextTick(()=> this._mountRowSSF(this.lines.length-1));
    },

    removeLine(i){
      this.lines.splice(i,1);
    },

    async searchItemSets(row, url=null, append=false){
      if (row.item_set.loading) return;
      row.item_set.loading = true;
      try{
        if (!append){ row.item_set.results=[]; row.item_set.next=null; }
        if (!url){
          const qs = ['ordering=-created_at'];
          const qq = (row.item_set.q||'').trim();
          if (qq) qs.push(`search=${encodeURIComponent(qq)}`);
          url = `/api/sellers/mine/item-sets/?${qs.join('&')}`;
        }
        const r = await app.api(url, {method:'GET'});
        const j = await app.readJson(r);
        const fresh = j.results ?? (Array.isArray(j)? j : []);
        row.item_set.results = append ? [...row.item_set.results, ...fresh] : fresh;
        row.item_set.next = j.next ?? null;
      } finally {
        row.item_set.loading=false;
      }
    },

    async moreItemSets(row){
      if (!row.item_set.next || row.item_set.loading) return;
      await this.searchItemSets(row, row.item_set.next, true);
    },

    pickItemSet(row, it){
      row.item_set.selected = it;
      row._errs.selected = '';
      if (!row.title) row.title = it.set_name || row.title;
    },

    clearItemSet(row){
      row.item_set.selected = null;
    },

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
      row._selectedType=null;
      row._selectedTypePk='';
      row._schema={type:'object',properties:{}};
      row._ui_schema={};
      row._schemaErr='';
      this._mountRowSSF(i);
    },

    async _applyTypeForRow(i, path, name=''){
      const row = this.lines[i]; if (!row) return;
      row._selectedType = { name, path, children_count:0 };
      row._schemaErr = '';

      try{
        const cached = app.getSchemaCached ? await app.getSchemaCached(path) : null;
        row._schema    = cached?.schema    || {type:'object',properties:{}};
        row._ui_schema = cached?.ui_schema || {};
      } catch {
        row._schema    = {type:'object',properties:{}};
        row._ui_schema = {};
      }

      try{
        const rr = await app.api(`/api/public/catalog/categories/resolve?path=${encodeURIComponent(path)}`, {method:'GET'});
        const j  = await app.readJson(rr);
        row._selectedTypePk = j?.type_id || '';
      } catch {
        row._selectedTypePk='';
      }
    },

    openRowCatalogPicker(i){
      const row = this.lines[i]; if (!row) return;

      this.ciPicker.onPick = async (it) => {
        row._schemaErr = '';

        const catAttrs = it.attributes || it.attrs || it.specs || it.properties || {};
        row.catalog_public_id = it.public_id || '';
        row._selectedCatalog = {
          id: it.id || it.uuid || '',
          public_id: row.catalog_public_id,
          item_name: it.item_name || it.name || '',
          type: it.type || {},
          image_path: it.image_path || it.image_url || it.image || '',
          attributes: catAttrs
        };

        if (!row.title) row.title = row._selectedCatalog.item_name || row.title;
        if (it?.type?.path) await this._applyTypeForRow(i, it.type.path, it.type.name || '');

        row.attributes = app._mergeAttrsPreferCurrent
          ? app._mergeAttrsPreferCurrent(row.attributes, catAttrs)
          : { ...(catAttrs||{}), ...(row.attributes||{}) };

        try{
          if (row.catalog_public_id) {
            const r = await app.api(`/api/sellers/mine/item-sets/prefill?catalog_public_id=${encodeURIComponent(row.catalog_public_id)}`, {method:'GET'});
            if (r.ok){
              const d = await app.readJson(r);
              row.attributes = app._mergeAttrsPreferCurrent
                ? app._mergeAttrsPreferCurrent(row.attributes, d.attributes || {})
                : { ...(d.attributes||{}), ...(row.attributes||{}) };
            }
          }
        } catch {}

        this._mountRowSSF(i);
      };

      this.ciPicker.openWith(row._selectedType?.path || '');
    },

    clearRowCatalog(i){
      const row = this.lines[i]; if (!row) return;
      row._selectedCatalog=null;
      row.catalog_public_id='';
    },

    _mountRowSSF(i){
      const row = this.lines[i]; if (!row) return;
      const el = document.getElementById('pawn_attrs_ssf_'+row.uid);
      if (!el || !app.ssf?.mount) return;
      const val = (row.attributes && Object.keys(row.attributes).length) ? row.attributes : {};
      app.ssf.mount(el, row._schema, val, row._ui_schema);
    },

    _readRowSSF(i){
      const row = this.lines[i]; if (!row) return {};
      const el = document.getElementById('pawn_attrs_ssf_'+row.uid);
      if (!el || !app.ssf?.read) return {};
      try { return app.ssf.read(el) || {}; } catch { return {}; }
    },

    _customerPayload(){
      const c = this.customer;
      const any = Object.values(c).some(v => (v ?? '') !== '');
      if (!any && !this.customer_public_id) return undefined;

      if (this.customer_public_id) {
        return { customer_public_id: this.customer_public_id };
      }

      const snap = _compact({
        first_name: (c.first_name||'').trim() || undefined,
        last_name:  (c.last_name||'').trim()  || undefined,
        email:      (c.email||'').trim()      || undefined,
        phone:      (c.phone||'').trim()      || undefined,
        address: {
          line1: (c.address_line1||'').trim() || undefined,
          line2: (c.address_line2||'').trim() || undefined,
          postal_code: (c.postal_code||'').trim() || undefined,
          city: (c.city||'').trim() || undefined,
          country: (c.country||'').trim() || undefined
        }
      });

      return snap ? { customer_snapshot: snap } : undefined;
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

      const snap = _compact({
        set_name: (row.title||ci?.item_name||'Pozycja'),
        description: row.description || '',
        condition: 'USED',
        type_path: t?.path || t?.full_path || null,
        catalog_item_public_id: ci?.public_id || null,
        attributes: row.attributes || {}
      }) || {};

      return {
        title: (row.title||'').trim() || undefined,
        description: (row.description||'').trim() || '',
        quantity: qty,
        appraisal_value,
        item_snapshot: snap
      };
    },

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
      if (!Number.isFinite(dd) || dd < 1){
        this.fv.due_in_days = 'Termin (dni) musi być liczbą ≥ 1.';
        ok = false;
      }

      if (!this.lines.length){
        this.err = 'Dodaj co najmniej jedną pozycję.';
        app.warn?.(this.err);
        return false;
      }

      for (const r of this.lines){
        r._schemaErr = '';
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
      const digits = ph.replace(/\D+/g,'');
      if (!this.err && ph && digits.length<6){ this.err='Telefon wygląda na zbyt krótki.'; ok=false; }

      if (!ok){
        if (!this.err) this.err = 'Popraw zaznaczone pola.';
        app.warn?.(this.err);
        this._focusFirstError();
      }

      return ok;
    },

    _focusFirstError(){
      this.$nextTick(()=> {
        if (this.fv.principal_amount) { document.getElementById('pawn_principal_amount')?.focus(); return; }
        if (this.fv.due_in_days)       { document.getElementById('pawn_due_days')?.focus(); return; }
        const row = this.lines.find(r => r._errs.selected || r._errs.quantity || r._errs.appraisal_amount || r._schemaErr);
        if (!row) return;

        if (row._errs.quantity) { document.getElementById(`pawn_qty_${row.uid}`)?.focus(); return; }
        if (row._errs.appraisal_amount) { document.getElementById(`pawn_app_${row.uid}`)?.focus(); return; }

        if (row._schemaErr) {
          document.getElementById(`pawn_attrs_ssf_${row.uid}`)?.scrollIntoView({behavior:'smooth', block:'center'});
        }
      });
    },

    _applyBackendErrors(j){
      const root = j?.errors || j || {};
      const nf = (root.non_field_errors && Array.isArray(root.non_field_errors)) ? root.non_field_errors.join('; ') : '';

      let hadFieldErrors = false;

      if (root.principal){
        this.fv.principal_amount = _toErrorString(root.principal);
        hadFieldErrors = true;
      }
      if (root.due_in_days){
        this.fv.due_in_days = _toErrorString(root.due_in_days);
        hadFieldErrors = true;
      }

      const applyLine = (idx, e) => {
        if (!Number.isFinite(idx) || idx < 0 || idx >= this.lines.length) return;
        const row = this.lines[idx];

        if (!row._errs) row._errs = { selected:'', quantity:'', appraisal_amount:'' };

        if (e.quantity) { row._errs.quantity = _toErrorString(e.quantity); hadFieldErrors = true; }

        if (e.appraisal_value) {
          row._errs.appraisal_amount = _toErrorString(e.appraisal_value);
          hadFieldErrors = true;
        }

        if (e.item_set_public_id) { row._errs.selected = _toErrorString(e.item_set_public_id); hadFieldErrors = true; }
        if (e.item_snapshot) { row._errs.selected = _toErrorString(e.item_snapshot); hadFieldErrors = true; }

        if (e.attributes) {
          row._schemaErr = _formatAttrErrors(e.attributes, row);
          hadFieldErrors = true;
        }

        if (e.non_field_errors) {
          const s = _toErrorString(e.non_field_errors);
          if (s) { row._errs.selected = row._errs.selected ? (row._errs.selected + ' ' + s) : s; hadFieldErrors = true; }
        }
      };

      if (root.lines && Array.isArray(root.lines)) {
        for (let i=0; i<root.lines.length && i<this.lines.length; i++){
          applyLine(i, root.lines[i] || {});
        }
      } else if (root.lines && typeof root.lines === 'object') {
        for (const [k, v] of Object.entries(root.lines)) {
          const idx = parseInt(k, 10);
          if (!Number.isFinite(idx)) continue;
          applyLine(idx, v || {});
        }
      }

      const general = app.errText?.(j) || nf || j?.detail || '';

      if (!hadFieldErrors) {
        this.err = general || 'Błąd walidacji.';
      } else {
        this.err = nf || j?.detail || '';
      }

      app.warn?.(this.err || 'Popraw zaznaczone pola.');
      this._focusFirstError();
    },

    async save(){
      this.busy=true; this.err=''; this.ok='';
      try{
        if (!this.sellerPublicId){ this.err='Brak sklepu.'; app.warn?.(this.err); return; }

        for (let i=0;i<this.lines.length;i++){
          if (this.lines[i].mode === 'CAT') this.lines[i].attributes = this._readRowSSF(i);
        }

        if (!this._validate()) return;

        const pn = app.moneyNormalize({ amount: (this.principal_amount ?? '').toString().trim(), currency: this.principal_currency || 'PLN' });
        const principal = pn ? String(pn.amount) : '';

        const payload = {
          seller_public_id: this.sellerPublicId,
          principal,
          due_in_days: Math.max(1, parseInt(this.due_in_days||30,10)) || 30,
          lines: this.lines.map((r,idx) => this._linePayload(r, idx))
        };

        const cp = this._customerPayload();
        if (cp?.customer_public_id) payload.customer_public_id = cp.customer_public_id;
        if (cp?.customer_snapshot)  payload.customer_snapshot  = cp.customer_snapshot;

        const r = await app.api('/api/sellers/mine/pawns/create/', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify(payload)
        });

        const j = await app.readJson(r);
        if (!r.ok){ this._applyBackendErrors(j); return; }

        app.ok?.('Utworzono zastaw.');
        app.goto?.(`/seller/pawns/${j.public_id}`);
      } catch(e){
        this.err=e?.message || 'Błąd';
        app.error?.(this.err);
      } finally {
        this.busy=false;
      }
    }
  };
};
