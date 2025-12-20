// static/js/orders/pawn_form.js
window.app = window.app || {};

app.imgUrl = app.imgUrl || (p => p || 'https://placehold.co/600x600?text=%20');

app.sellerOrderPawnForm = function(){
  return {
    busy:false, err:'', ok:'',

    catPicker:{open:false}, ciPicker:{open:false},

    // klient
    customer_public_id:'',
    customer:{
      first_name:'', last_name:'', email:'', phone:'',
      address_line1:'', address_line2:'', postal_code:'', city:'', country:'',
      document_type:'', document_number:'', birth_date:''
    },
    cust:{
      q:'', results:[], loading:false, next:null,
      async search(url=null){
        this.loading=true; this.results=[]; this.next=null;
        try{
          if (!url){
            const qs=[]; const qq=(this.q||'').trim(); if (qq) qs.push(`q=${encodeURIComponent(qq)}`);
            qs.push('ordering=last_name');
            url=`/api/sellers/mine/customers/?${qs.join('&')}`;
          }
          const r = await app.api(url, {method:'GET'});
          const j = await app.readJson(r);
          this.results = j.results ?? (Array.isArray(j) ? j : []);
          this.next = j.next ?? null;
        } finally { this.loading=false; }
      },
      async more(){ if (this.next) await this.search(this.next); },
      pick: (c) => {
        const ctx = Alpine.$data(document.querySelector('[x-data^="app.sellerOrderPawnForm"]'));
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
        const ctx = Alpine.$data(document.querySelector('[x-data^="app.sellerOrderPawnForm"]'));
        ctx.customer_public_id = '';
      }
    },

    form:{ lines:[], note:'', purchase_date:'', payment_method:'CASH', create_itemsets:true },

    async init(){
      this.catPicker = app._makeCategoryPicker();
      this.ciPicker  = app._makeCatalogPicker();
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

    /* --- linie --- */
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
    addLine(){ this.form.lines.push(this._newRow()); this.$nextTick(()=> this._mountRowSSF(this.form.lines.length-1)); },
    removeLine(i){ this.form.lines.splice(i,1); },

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
        row.catalog_public_id = it.public_id || '';
        const catAttrs = it.attributes || it.attrs || it.specs || it.properties || {};
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

        try{
          if (row.catalog_public_id) {
            const r = await app.api(`/api/sellers/mine/item-sets/prefill?catalog_public_id=${encodeURIComponent(row.catalog_public_id)}`,{method:'GET'});
            if (r.ok){
              const d = await app.readJson(r);
              row.attributes = app._mergeAttrsPreferCurrent(row.attributes, d.attributes || {});
              if (!Object.keys(catAttrs).length && d.attributes) row._selectedCatalog.attributes = d.attributes;
              this._mountRowSSF(i);
            }
          }
        } catch {}
      };
      this.ciPicker.openWith(row._selectedType?.path || '');
    },
    clearRowCategory(i){
      const row=this.form.lines[i]; if (!row) return;
      row._selectedType=null; row._selectedTypePk=''; row.item_type_public_id='';
      row._schema={type:'object',properties:{}};
      row._ui_schema={};
      this._mountRowSSF(i);
    },
    clearRowCatalog(i){
      const row=this.form.lines[i]; if (!row) return;
      row._selectedCatalog=null; row.catalog_public_id='';
    },

    async _applyTypeForRow(i, path, name=''){
      const row=this.form.lines[i]; if (!row) return;
      row._selectedType = { name, path, children_count:0 };

      try {
              const rs = await app.api(`/api/public/catalog/categories/schema/by-path/${encodeURIComponent(path)}`, {method:'GET'});
              if (rs.ok){
                const d = await app.readJson(rs);
                row._schema    = d.schema    || {type:'object',properties:{}};
                row._ui_schema = d.ui_schema || {};
              } else {
                row._schema    = {type:'object',properties:{}};
                row._ui_schema = {};
              }
            } catch {
              row._schema    = {type:'object',properties:{}};
              row._ui_schema = {};
            }

      try{
        const rr = await app.api(`/api/public/catalog/categories/resolve?path=${encodeURIComponent(path)}`, {method:'GET'});
        const j  = await app.readJson(rr);
        row._selectedTypePk = j?.type_id || '';
        row.item_type_public_id = row._selectedTypePk || '';
      } catch { row._selectedTypePk=''; }

      this._mountRowSSF(i);
    },

    _mountRowSSF(i){
      const row=this.form.lines[i]; if (!row) return;
      const el=document.getElementById('pawn_attrs_ssf_'+row.uid);
      if (!el) return;
      const val = (row.attributes && Object.keys(row.attributes).length) ? row.attributes : {};
      app.ssf.mount(el, row._schema, val, row._ui_schema);
    },
    _readRowSSF(i){
      const el=document.getElementById('pawn_attrs_ssf_'+this.form.lines[i].uid);
      try { return app.ssf.read(el) || {}; } catch { return {}; }
    },

    _collectCustomer(){
      const c=this.customer;
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
        },
        document_type:   (c.document_type||'')   || undefined,
        document_number: (c.document_number||'') || undefined,
        birth_date:      (c.birth_date||'')      || undefined,
      };
    },

    _validate(){
      this.err=''; let ok=true;
      for (const row of this.form.lines){
        row._errs={ title:'', unit_price:'', quantity:'' };
        const q=Math.max(1, parseInt(row.quantity||1,10));
        if (!row.title.trim()){ row._errs.title='Podaj tytuł pozycji.'; ok=false; }
        if (!row.unit_price.toString().trim()){ row._errs.unit_price='Podaj cenę skupu.'; ok=false; }
        else if (isNaN(parseFloat(String(row.unit_price).replace(',','.')))){ row._errs.unit_price='Cena musi być liczbą.'; ok=false; }
        if (!Number.isFinite(q) || q<1){ row._errs.quantity='Ilość musi być liczbą ≥ 1.'; ok=false; }
      }
      const em=(this.customer.email||'').trim();
      if (em && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)){ this.err='Nieprawidłowy email klienta.'; ok=false; }
      const ph=(this.customer.phone||'').trim();
      const digits=ph.replace(/\D+/g,'');
      if (!this.err && ph && digits.length<6){ this.err='Telefon klienta wygląda na zbyt krótki.'; ok=false; }
      if (!ok){
        if (!this.err) this.err='Popraw zaznaczone pola w wierszach.';
        app.warn(this.err);
        this._focusFirstRowError();
      }
      return ok;
    },

    _focusFirstRowError(){
      this.$nextTick(()=>{
        const row=this.form.lines.find(r => r._errs.title || r._errs.unit_price || r._errs.quantity);
        if (!row) return; const base=row.uid;
        if (row._errs.title) document.getElementById(`pawn_title_${base}`)?.focus();
        else if (row._errs.unit_price) document.getElementById(`pawn_price_${base}`)?.focus();
        else if (row._errs.quantity) document.getElementById(`pawn_qty_${base}`)?.focus();
      });
    },

    _applyBackendErrors(j){
      const root=j?.errors || j || {};
      if (Array.isArray(root.lines)){
        for (let i=0;i<root.lines.length && i<this.form.lines.length;i++){
          const e=root.lines[i] || {}; const row=this.form.lines[i];
          if (!row._errs) row._errs={ title:'', unit_price:'', quantity:'' };
          if (e.title)      row._errs.title      = Array.isArray(e.title) ? e.title.join('; ') : String(e.title);
          if (e.unit_price) row._errs.unit_price = Array.isArray(e.unit_price) ? e.unit_price.join('; ') : String(e.unit_price);
          if (e.quantity)   row._errs.quantity   = Array.isArray(e.quantity) ? e.quantity.join('; ') : String(e.quantity);
          if (e.attributes) row._schemaErr = Array.isArray(e.attributes) ? e.attributes.join('\n') : String(e.attributes);
        }
      }
      this.err = app.errText?.(j) || j?.detail || 'Błąd walidacji.';
      app.warn(this.err);
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
          unit_price: String(l.unit_price||'').replace(',','.'),
          attributes: l.attributes || {},
          notes: (l.notes||'').trim(),
          item_type_public_id: (l.item_type_public_id||'').trim() || undefined,
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

        const r = await app.api(`/api/sellers/mine/orders/pawn-purchase/`, { method:'POST', body: JSON.stringify(payload) });
        const j = await app.readJson(r);
        if (!r.ok){ this._applyBackendErrors(j); return; }

        this.ok='Dodano.'; app.ok('Dodano.');
        app.goto(`/seller/orders/${j.public_id}`);
      } catch(e){
        this.err = e?.message || 'Błąd.'; app.error?.(this.err);
      } finally { this.busy=false; }
    }
  };
};
