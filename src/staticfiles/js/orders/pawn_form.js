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
  if (Array.isArray(v)) return v.map(String).join(' ');
  if (typeof v === 'object') return Object.values(v).flat().map(String).join(' ');
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

app.sellerOrderPawnForm = function(){
  return {
    busy:false, err:'', ok:'',

    catPicker: { open:false, loading:false, nodes:[], crumbs:[], onPick(){}, openAtRoot(){}, load(){}, enter(){}, backTo(){}, pick(){}, close(){} },
    ciPicker:  { open:false, q:'', typePath:'', loading:false, items:[], next:null, uiNonce:0, onPick(){}, openWith(){}, search(){}, more(){}, pairsFor(){ return []; }, pick(){}, close(){} },

    customer_public_id:'',
    customer:{
      first_name:'', last_name:'', email:'', phone:'',
      address_line1:'', address_line2:'', postal_code:'', city:'', country:'',
      document_type:'', document_number:'', birth_date:''
    },

    cust:{
      _ctx:null,
      q:'', results:[], loading:false, next:null,

      async search(url=null, append=false){
        if (this.loading) return;
        this.loading = true;
        try{
          if (!append){ this.results=[]; this.next=null; }
          if (!url){
            const qs=[];
            const qq=(this.q||'').trim();
            if (qq) qs.push(`q=${encodeURIComponent(qq)}`);
            qs.push('ordering=last_name');
            url=`/api/sellers/mine/customers/?${qs.join('&')}`;
          }
          const r = await app.api(url, {method:'GET'});
          const j = await app.readJson(r);
          const fresh = j.results ?? (Array.isArray(j) ? j : []);
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
          country:       c.country       || '',
          document_type:   c.document_type   || '',
          document_number: c.document_number || '',
          birth_date:      c.birth_date      || ''
        });
      },

      clearLink(){
        const ctx = this._ctx;
        if (!ctx) return;
        ctx.customer_public_id = '';
      }
    },

    form:{ lines:[], note:'', purchase_date:'', payment_method:'CASH', create_itemsets:true },

    async init(){
      this.cust._ctx = this;

      if (app._makeCategoryPicker) Object.assign(this.catPicker, app._makeCategoryPicker());
      if (app._makeCatalogPicker)  Object.assign(this.ciPicker,  app._makeCatalogPicker());

      this.addLine();
    },

    _attrPairsForRow(row, attrs){
      try {
        return app.attrPairs
          ? app.attrPairs(attrs || {}, row._ui_schema || {})
          : Object.entries(attrs || {});
      } catch {
        return Object.entries(attrs || {});
      }
    },

    _newRow(){
      const uid=Math.random().toString(36).slice(2,10);
      return {
        uid, title:'', quantity:1, unit_price:'', notes:'',
        item_type_public_id:'',
        catalog_public_id:'',
        _selectedType:null, _selectedTypePk:'', _selectedCatalog:null,
        _schema:{type:'object',properties:{}}, _ui_schema:{}, attributes:{}, _schemaErr:'',
        _errs:{ title:'', unit_price:'', quantity:'' }
      };
    },

    addLine(){
      this.form.lines.push(this._newRow());
      this.$nextTick(()=> this._mountRowSSF(this.form.lines.length-1));
    },

    removeLine(i){
      this.form.lines.splice(i,1);
    },

    openRowCategoryPicker(i){
      const row=this.form.lines[i]; if (!row) return;
      this.catPicker.onPick = async (node) => {
        if (row._selectedCatalog) return;
        await this._applyTypeForRow(i, node.path, node.name);
        this._mountRowSSF(i);
      };
      this.catPicker.openAtRoot();
    },

    openRowCatalogPicker(i){
      const row=this.form.lines[i]; if (!row) return;

      this.ciPicker.onPick = async (it) => {
        row._schemaErr = '';

        const catAttrs = it.attributes || it.attrs || it.specs || it.properties || {};
        row.catalog_public_id = it.public_id || '';
        row._selectedCatalog = {
          id: it.id || it.uuid || '',
          public_id: row.catalog_public_id,
          item_name: it.item_name || '',
          type: it.type || {},
          image_path: it.image_path || it.image_url || it.image || '',
          attributes: catAttrs
        };

        if (!row.title) row.title = it.item_name || row.title;
        if (it?.type?.path) await this._applyTypeForRow(i, it.type.path, it.type.name||'');

        row.attributes = app._mergeAttrsPreferCurrent
          ? app._mergeAttrsPreferCurrent(row.attributes, catAttrs)
          : { ...(catAttrs||{}), ...(row.attributes||{}) };

        try{
          if (row.catalog_public_id) {
            const r = await app.api(`/api/sellers/mine/item-sets/prefill?catalog_public_id=${encodeURIComponent(row.catalog_public_id)}`,{method:'GET'});
            if (r.ok){
              const d = await app.readJson(r);
              row.attributes = app._mergeAttrsPreferCurrent
                ? app._mergeAttrsPreferCurrent(row.attributes, d.attributes || {})
                : { ...(d.attributes||{}), ...(row.attributes||{}) };
              if (!Object.keys(catAttrs).length && d.attributes) row._selectedCatalog.attributes = d.attributes;
            }
          }
        } catch {}

        this._mountRowSSF(i);
      };

      this.ciPicker.openWith(row._selectedType?.path || '');
    },

    clearRowCategory(i){
      const row=this.form.lines[i]; if (!row) return;
      row._selectedType=null; row._selectedTypePk=''; row.item_type_public_id='';
      row._schema={type:'object',properties:{}};
      row._ui_schema={};
      row._schemaErr='';
      this._mountRowSSF(i);
    },

    clearRowCatalog(i){
      const row=this.form.lines[i]; if (!row) return;
      row._selectedCatalog=null; row.catalog_public_id='';
    },

    async _applyTypeForRow(i, path, name=''){
      const row=this.form.lines[i]; if (!row) return;

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
        row.item_type_public_id = row._selectedTypePk || '';
      } catch {
        row._selectedTypePk='';
        row.item_type_public_id = '';
      }

      this._mountRowSSF(i);
    },

    _mountRowSSF(i){
      const row=this.form.lines[i]; if (!row) return;
      const el=document.getElementById('pawn_attrs_ssf_'+row.uid);
      if (!el || !app.ssf?.mount) return;
      const val = (row.attributes && Object.keys(row.attributes).length) ? row.attributes : {};
      app.ssf.mount(el, row._schema, val, row._ui_schema);
    },

    _readRowSSF(i){
      const row=this.form.lines[i]; if (!row) return {};
      const el=document.getElementById('pawn_attrs_ssf_'+row.uid);
      if (!el || !app.ssf?.read) return {};
      try { return app.ssf.read(el) || {}; } catch { return {}; }
    },

    _collectCustomer(){
      const c=this.customer;
      const nonEmpty = Object.values(c).some(v => (v ?? '') !== '');
      if (!nonEmpty && !this.customer_public_id) return null;

      const payload = _compact({
        customer_public_id: this.customer_public_id || undefined,
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
        },
        document_type:   (c.document_type||'').trim()   || undefined,
        document_number: (c.document_number||'').trim() || undefined,
        birth_date:      (c.birth_date||'').trim()      || undefined
      });

      return payload || null;
    },

    _validate(){
      this.err=''; let ok=true;

      for (const row of this.form.lines){
        row._schemaErr = row._schemaErr || '';
        row._errs={ title:'', unit_price:'', quantity:'' };

        const q=Math.max(1, parseInt(row.quantity||1,10));
        if (!(row.title||'').trim()){ row._errs.title='Podaj tytuł pozycji.'; ok=false; }

        const up = (row.unit_price ?? '').toString().trim();
        if (!up){ row._errs.unit_price='Podaj cenę skupu.'; ok=false; }
        else if (!Number.isFinite(Number(up.replace(',','.')))){ row._errs.unit_price='Cena musi być liczbą.'; ok=false; }

        if (!Number.isFinite(q) || q<1){ row._errs.quantity='Ilość musi być liczbą ≥ 1.'; ok=false; }
      }

      const em=(this.customer.email||'').trim();
      if (em && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)){ this.err='Nieprawidłowy email klienta.'; ok=false; }

      const ph=(this.customer.phone||'').trim();
      const digits=ph.replace(/\D+/g,'');
      if (!this.err && ph && digits.length<6){ this.err='Telefon klienta wygląda na zbyt krótki.'; ok=false; }

      if (!ok){
        if (!this.err) this.err='Popraw zaznaczone pola w wierszach.';
        app.warn?.(this.err);
        this._focusFirstRowError();
      }

      return ok;
    },

    _focusFirstRowError(){
      this.$nextTick(()=> {
        const row=this.form.lines.find(r => r._errs.title || r._errs.unit_price || r._errs.quantity);
        if (!row) return;
        const base=row.uid;
        if (row._errs.title) document.getElementById(`pawn_title_${base}`)?.focus();
        else if (row._errs.unit_price) document.getElementById(`pawn_price_${base}`)?.focus();
        else if (row._errs.quantity) document.getElementById(`pawn_qty_${base}`)?.focus();
      });
    },

    _applyBackendErrors(j){
      const root=j?.errors || j || {};

      if (Array.isArray(root.lines)){
        for (let i=0;i<root.lines.length && i<this.form.lines.length;i++){
          const e=root.lines[i] || {};
          const row=this.form.lines[i];

          if (!row._errs) row._errs={ title:'', unit_price:'', quantity:'' };

          if (e.title)      row._errs.title      = _toErrorString(e.title);
          if (e.unit_price) row._errs.unit_price = _toErrorString(e.unit_price);
          if (e.quantity)   row._errs.quantity   = _toErrorString(e.quantity);
          if (e.attributes) row._schemaErr = _toErrorString(e.attributes);
        }
      }

      this.err = app.errText?.(j) || _toErrorString(root.non_field_errors) || j?.detail || 'Błąd walidacji.';
      app.warn?.(this.err);
      this._focusFirstRowError();
    },

    async save(){
      this.busy=true; this.err=''; this.ok='';
      try{
        for (let i=0;i<this.form.lines.length;i++){
          this.form.lines[i].attributes = this._readRowSSF(i);
        }

        if (!this._validate()) return;

        const lines = this.form.lines.map(l => ({
          title:(l.title||'').trim(),
          quantity: Math.max(1, parseInt(l.quantity||1,10)),
          unit_price: String(l.unit_price||'').trim().replace(',','.'),
          attributes: l.attributes || {},
          notes: (l.notes||'').trim(),
          item_type_public_id: (l.item_type_public_id||'').trim() || undefined
        })).filter(x => x.title && x.unit_price!=='');

        const payload = {
          lines,
          note: (this.form.note||'').trim() || undefined,
          payment_method: this.form.payment_method || 'CASH',
          purchase_date: (this.form.purchase_date||'') || undefined,
          create_itemsets: !!this.form.create_itemsets
        };

        const cust=this._collectCustomer();
        if (cust) payload.customer=cust;

        const r = await app.api(`/api/sellers/mine/orders/pawn-purchase/`, {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify(payload)
        });

        const j = await app.readJson(r);
        if (!r.ok){ this._applyBackendErrors(j); return; }

        this.ok='Dodano.';
        app.ok?.('Dodano.');
        app.goto?.(`/seller/orders/${j.public_id}`);
      } catch(e){
        this.err = e?.message || 'Błąd.';
        app.error?.(this.err);
      } finally {
        this.busy=false;
      }
    }
  };
};
