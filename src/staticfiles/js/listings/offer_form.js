window.app = window.app || {};

app.imgUrl = app.imgUrl || (p => p || 'https://placehold.co/600x600?text=%20');
app.api = app.api || ((url, opts = {}) => fetch(url, { credentials: 'include', ...opts }));
app.readJson = app.readJson || (async (r) => { try { return await r.json(); } catch { return {}; } });

app.moneyText = app.moneyText || (v => {
  if (v == null || v === '') return '—';
  if (typeof v === 'object') {
    const a = v.amount ?? '';
    const c = v.currency || 'PLN';
    return (a !== '' ? a : '—') + ' ' + c;
  }
  return `${v} PLN`;
});

function _toErrorString(v) {
  if (!v) return '';
  if (Array.isArray(v)) return v.map(String).join(' ');
  if (typeof v === 'object') return Object.values(v).flat().map(String).join(' ');
  return String(v);
}

app._makeShipPicker = app._makeShipPicker || function (ctx) {
  return {
    open:false, loading:false, items:[], next:null,
    provider:'', price_override:'',
    length_cm:null, width_cm:null, height_cm:null, weight_kg:null,

    async openWithDefaults(){
      this.length_cm = ctx.form.length_cm ?? null;
      this.width_cm  = ctx.form.width_cm  ?? null;
      this.height_cm = ctx.form.height_cm ?? null;
      this.weight_kg = ctx.form.weight_kg ?? null;
      this.provider = '';
      this.price_override = '';
      this.items=[]; this.next=null;
      this.open = true;
      await this.search().catch(()=>{});
    },

    _buildUrl(base=null){
      const params = [];
      if (this.provider) params.push(`provider=${encodeURIComponent(this.provider)}`);
      if (this.length_cm) params.push(`length_cm=${encodeURIComponent(this.length_cm)}`);
      if (this.width_cm)  params.push(`width_cm=${encodeURIComponent(this.width_cm)}`);
      if (this.height_cm) params.push(`height_cm=${encodeURIComponent(this.height_cm)}`);
      if (this.weight_kg) params.push(`weight_kg=${encodeURIComponent(this.weight_kg)}`);
      return base || (`/api/public/shipping/package-types/?ordering=price${params.length ? '&'+params.join('&') : ''}`);
    },

    async search(url=null, append=false){
      if (this.loading) return;
      this.loading = true;

      if (!append){ this.items=[]; this.next=null; }

      try{
        const u = url || this._buildUrl();
        const r = await app.api(u,{method:'GET'});
        const j = await app.readJson(r);
        const fresh = j.results ?? j ?? [];
        this.items = append ? [...this.items, ...fresh] : fresh;
        this.next = j.next ?? null;
      } finally {
        this.loading = false;
      }
    },

    async more(){ if(this.next && !this.loading) await this.search(this.next, true); },
    close(){ this.open=false; }
  };
};

app.sellerOfferForm = function (opts = {}) {
  return {
    editingId: (opts.editingId || '').trim(),
    seller_public_id: '',

    async ensureSellerId(){
      if (this.seller_public_id) return this.seller_public_id;
      try{
        const r = await app.api('/api/sellers/mine/', {method:'GET'});
        if (r.ok){
          const me = await app.readJson(r);
          this.seller_public_id = me.public_id || me?.seller?.public_id || '';
        }
      } catch {}
      return this.seller_public_id;
    },

    form: {
      set_name:'', description:'', price_str:'',
      stock_quantity:1, condition:'USED', listing_type:'LISTING',
      allow_online_checkout:false, attributes:{},
      length_cm:null, width_cm:null, height_cm:null, weight_kg:null
    },

    schema: { type:'object', properties:{} },
    ui_schema: {},

    selectedType:null, selectedTypePk:'',
    selectedCatalog:null, catalogItemUUID:'', catalogPublicId:'',
    initialCatalogItemUUID:'',

    existingImages:[], stagedFiles:[], removeExistingIds:[],
    _dzOver:false, _dragIdx:null,

    canAddShipping:false,
    ship:{ options:[], suggest:[], busy:false, err:'', ok:'' },

    errors: {},
    schemaErr:'',
    err:'', ok:'',

    catPicker:  { open:false, loading:false, nodes:[], crumbs:[], onPick(){}, openAtRoot(){}, load(){}, enter(){}, backTo(){}, pick(){}, close(){} },
    ciPicker:   { open:false, q:'', typePath:'', loading:false, items:[], next:null, uiNonce:0, onPick(){}, openWith(){}, search(){}, more(){}, pairsFor(){ return []; }, pick(){}, close(){} },
    shipPicker: { open:false, loading:false, items:[], next:null, provider:'', price_override:'', length_cm:null, width_cm:null, height_cm:null, weight_kg:null, openWithDefaults(){}, _buildUrl(){}, search(){}, more(){}, close(){} },

    _attrPairs(attrs){
      try {
        return app.attrPairs ? app.attrPairs(attrs || {}, this.ui_schema || {}) : Object.entries(attrs || {});
      } catch {
        return Object.entries(attrs || {});
      }
    },

    busy:false,

    _sanitizeAttrsForSubmit(attrs){
      const out = { ...(attrs || {}) };
      const schema = this.schema || {};
      const props = schema.properties || {};
      const required = new Set(Array.isArray(schema.required) ? schema.required : []);

      const isEmptyObject = (v) => v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0;
      const isEmptyArray = (v) => Array.isArray(v) && v.length === 0;

      for (const [k, v] of Object.entries(out)){
        const emptyScalar =
          v === null ||
          typeof v === 'undefined' ||
          (typeof v === 'string' && v.trim() === '') ||
          (typeof v === 'number' && Number.isNaN(v));

        const emptyStruct = isEmptyArray(v) || isEmptyObject(v);

        if ((emptyScalar || emptyStruct) && !required.has(k)){
          delete out[k];
          continue;
        }

        const spec = props[k];
        const typ = spec && typeof spec === 'object' ? spec.type : null;

        if ((typ === 'number' || typ === 'integer') && typeof out[k] === 'string'){
          const s = out[k].trim();
          if (s !== ''){
            const n = Number(s.replace(',', '.'));
            if (!Number.isNaN(n)){
              if (typ === 'integer'){
                if (Number.isInteger(n)) out[k] = n;
              } else {
                out[k] = n;
              }
            }
          }
        }

        if (typ === 'boolean' && typeof out[k] === 'string'){
          const s = out[k].trim().toLowerCase();
          if (['1','true','tak','yes','y','t'].includes(s)) out[k] = true;
          else if (['0','false','nie','no','n','f'].includes(s)) out[k] = false;
        }
      }

      return out;
    },

    _toAttrErrorString(v){
      if (!v) return '';
      if (typeof v === 'string') return v;
      if (Array.isArray(v)) return v.map(String).join(' ');
      if (typeof v === 'object'){
        const parts = [];
        for (const [k, val] of Object.entries(v)){
          if (val == null) continue;
          if (Array.isArray(val)) parts.push(`${k}: ${val.map(String).join(' ')}`);
          else if (typeof val === 'object') parts.push(`${k}: ${Object.values(val).flat().map(String).join(' ')}`);
          else parts.push(`${k}: ${String(val)}`);
        }
        return parts.join('; ');
      }
      return String(v);
    },

    _prettyAttrError(msg){
      const s = String(msg || '');
      const ui = this.ui_schema || {};
      return s.replace(/(^|[\s;,\n])([a-zA-Z0-9_]+)\s*:/g, (all, pre, key) => {
        const label = (window.app && app.attrLabel) ? app.attrLabel(key, ui) : key;
        return `${pre}${label}:`;
      });
    },

    _clearErrors(){ this.errors = {}; this.schemaErr=''; this.err=''; },
    _setError(field, msg){ if (msg) this.errors[field] = String(msg); else delete this.errors[field]; },

    _scrollToFirstError(){
      const order = ['set_name','price_str','type','stock_quantity','allow_online_checkout'];
      for (const k of order){
        if (this.errors[k]){
          const el = document.getElementById('f_'+k) || document.querySelector(`[name="${k}"]`);
          if (el && typeof el.scrollIntoView === 'function'){
            el.scrollIntoView({behavior:'smooth', block:'center'});
            try { el.focus({ preventScroll: true }); } catch {}
          }
          break;
        }
      }
    },

    _validateField(field){
      if (field === 'set_name'){
        const name = (this.form.set_name||'').trim();
        this._setError('set_name', name ? '' : 'To pole jest wymagane.');
      }
      if (field === 'price_str'){
        const priceStr = (this.form.price_str ?? '').toString().trim().replace(',', '.');
        const priceNum = priceStr === '' ? NaN : Number(priceStr);
        this._setError('price_str', (Number.isFinite(priceNum) && priceNum > 0) ? '' : 'Podaj cenę większą od zera.');
      }
      if (field === 'type'){
        this._setError('type', this.selectedTypePk ? '' : 'Wybierz kategorię.');
      }
      if (field === 'stock_quantity'){
        const qty = parseInt(this.form.stock_quantity || 1, 10);
        this._setError('stock_quantity', (Number.isFinite(qty) && qty >= 1) ? '' : 'Wprowadź liczbę całkowitą ≥ 1.');
      }
      if (field === 'allow_online_checkout'){
        const bad = !!this.form.allow_online_checkout && this.form.listing_type !== 'BUY';
        this._setError('allow_online_checkout', bad ? 'Płatność online wymaga typu „Kup teraz (BUY)”.' : '');
      }
    },

    _validateClient(){
      this._clearErrors();
      this._validateField('set_name');
      this._validateField('price_str');
      this._validateField('type');
      this._validateField('stock_quantity');
      this._validateField('allow_online_checkout');
      return Object.keys(this.errors).length === 0;
    },

    async init(){
      await this.ensureSellerId();
      Object.assign(this.catPicker,  app._makeCategoryPicker());
      Object.assign(this.ciPicker,   app._makeCatalogPicker());
      Object.assign(this.shipPicker, app._makeShipPicker(this));

      if (this.editingId) await this.loadForEdit(this.editingId);
      this._mountSSF();

      this.catPicker.onPick = async (node) => {
        if (this.selectedCatalog) return;
        await this._applyTypeFromPath(node.path, node.name);
        delete this.errors.type;
        this._mountSSF();
      };

      this.ciPicker.onPick = async (it) => {
        this.catalogItemUUID = it.id || it.uuid || '';
        this.catalogPublicId = it.public_id || '';
        this.selectedCatalog = {
          id: this.catalogItemUUID,
          public_id: this.catalogPublicId,
          item_name: it.item_name,
          type: it.type,
          image_path: it.image_path || it.image_url || it.image || '',
          attributes: it.attributes || it.attrs || it.specs || it.properties || {}
        };

        if (it?.type?.path) await this._applyTypeFromPath(it.type.path, it.type.name || '');

        try{
          if (this.catalogPublicId) {
            const r = await app.api(`/api/sellers/mine/item-sets/prefill?catalog_public_id=${encodeURIComponent(this.catalogPublicId)}`,{method:'GET'});
            if (r.ok){
              const d = await app.readJson(r);
              this.form.attributes = app._mergeAttrsPreferCurrent(this.form.attributes, d.attributes || {});
            }
          }
        } catch {}

        delete this.errors.type;
        this._mountSSF();
      };

      this.$watch('form.set_name', () => this._validateField('set_name'));
      this.$watch('form.price_str', () => this._validateField('price_str'));
      this.$watch('form.stock_quantity', () => this._validateField('stock_quantity'));

      this.$watch('form.listing_type', () => {
        this._validateField('allow_online_checkout');
        this._recomputeCanAdd();
      });
      this.$watch('form.allow_online_checkout', () => {
        this._validateField('allow_online_checkout');
        this._recomputeCanAdd();
      });

      this.$watch('form.listing_type', ()=> this._recomputeCanAdd());
      this.$watch('form.allow_online_checkout', ()=> this._recomputeCanAdd());

      this._recomputeCanAdd();
      if (this.canAddShipping) await this._loadShippingAll();
    },

    openCategoryPicker(){ if (this.selectedCatalog) return; this.catPicker.openAtRoot(); },
    openCatalogPicker(){ this.ciPicker.openWith(this.selectedType?.path || ''); },

    clearCategory(){
      if (this.selectedCatalog) return;
      this.selectedType=null; this.selectedTypePk='';
      this.schema={type:'object',properties:{}};
      this.ui_schema={};
      this._mountSSF();
      this._validateField('type');
    },

    clearCatalog(){
      this.selectedCatalog=null;
      this.catalogItemUUID='';
      this.catalogPublicId='';
      this._mountSSF();
      this._validateField('type');
    },

    _recomputeCanAdd(){
      const prev = this.canAddShipping;
      this.canAddShipping = !!(this.editingId && this.form.listing_type==='BUY' && this.form.allow_online_checkout);
      if (this.canAddShipping && !prev) this._loadShippingAll();
    },

    async loadForEdit(id){
      try{
        const r = await app.api(`/api/sellers/mine/item-sets/${id}/`, {method:'GET'});
        if (!r.ok){ this.err='Nie udało się wczytać oferty.'; return; }
        const row = await app.readJson(r);

        const rawPrice = row.price ?? null;
        const amount = (rawPrice && typeof rawPrice === 'object') ? rawPrice.amount : rawPrice;

        this.form = {
          set_name: row.set_name || '',
          description: row.description || '',
          price_str: (amount ?? '') === '' ? '' : String(amount),
          stock_quantity: row.stock_quantity ?? 1,
          condition: row.condition || 'USED',
          listing_type: row.listing_type || 'LISTING',
          allow_online_checkout: !!row.allow_online_checkout,
          attributes: row.attributes || {},
          length_cm: row.length_cm ?? null,
          width_cm:  row.width_cm ?? null,
          height_cm: row.height_cm ?? null,
          weight_kg: row.weight_kg ?? null
        };

        if (row.type?.path) await this._applyTypeFromPath(row.type.path, row.type.name);

        this.existingImages = Array.isArray(row.images) ? row.images : [];

        if (row.catalog_item_id || row.catalog_item) {
          this.catalogItemUUID = row.catalog_item_id || '';
          const ci = row.catalog_item || {};
          this.catalogPublicId = ci.public_id || '';
          this.selectedCatalog = ci.public_id ? {
            id: this.catalogItemUUID,
            public_id: ci.public_id,
            item_name: ci.item_name,
            type: ci.type || {},
            image_path: ci.image_path || '',
            attributes: ci.attributes || {}
          } : null;
        }

        this.initialCatalogItemUUID = this.catalogItemUUID || '';
      } catch {
        this.err='Błąd sieci.';
      }
    },

    async _fetchSchemaForPath(path){
      try{
        const { schema, ui_schema } = await app.getSchemaCached(path);
        this.schema = schema || {type:'object',properties:{}};
        this.ui_schema = ui_schema || {};
      } catch {
        this.schema = {type:'object',properties:{}};
        this.ui_schema = {};
      }
    },

    async _applyTypeFromPath(path, name=''){
      await this._fetchSchemaForPath(path);
      try{
        const rr = await app.api(`/api/public/catalog/categories/resolve?path=${encodeURIComponent(path)}`, {method:'GET'});
        this.selectedTypePk = rr.ok ? (await app.readJson(rr)).type_id : '';
      } catch {
        this.selectedTypePk='';
      }
      this.selectedType = { name, path, children_count: 0 };
    },

    _mountSSF(){
      const el = document.getElementById('offer_attrs_ssf');
      if (!el) return;
      const val = (this.form.attributes && Object.keys(this.form.attributes).length) ? this.form.attributes : {};
      app.ssf.mount(el, this.schema, val, this.ui_schema);
    },

    readSSF(){
      const el = document.getElementById('offer_attrs_ssf');
      if (!el) return {};
      try { return app.ssf.read(el) || {}; } catch { return {}; }
    },

    _scrollToAttrs(){
      const el = document.getElementById('offer_attrs_ssf');
      if (!el) return;
      try { el.scrollIntoView({behavior:'smooth', block:'center'}); } catch {}
    },

    onFiles(ev){
      const files = Array.from(ev.target.files||[]);
      for (const f of files){ if (f.type.startsWith('image/')) this.stagedFiles.push(f); }
      ev.target.value='';
    },

    removeStaged(i){ this.stagedFiles.splice(i,1); },

    onDragOver(e){ e.preventDefault(); this._dzOver=true; },
    onDragLeave(e){ e.preventDefault(); this._dzOver=false; },

    onDrop(e){
      e.preventDefault();
      const files = Array.from(e.dataTransfer?.files || []);
      for (const f of files){ if (f.type?.startsWith('image/')) this.stagedFiles.push(f); }
      this._dzOver=false;
    },

    toggleRemoveExisting(id){
      const i = this.removeExistingIds.indexOf(id);
      if (i>=0) this.removeExistingIds.splice(i,1); else this.removeExistingIds.push(id);
    },

    startDrag(idx){ this._dragIdx = idx; },

    async dropDrag(idx){
      const from = this._dragIdx; this._dragIdx = null;
      if (from===null || from===idx) return;
      const arr = this.existingImages;
      const [m] = arr.splice(from,1);
      arr.splice(idx,0,m);
      await this._persistReorder().catch(()=>this._reloadImages());
    },

    async _persistReorder(){
      if (!this.editingId) return;
      const order = this.existingImages.map(x => x.public_id || x.id).filter(Boolean);
      const r = await app.api(`/api/sellers/mine/item-sets/${this.editingId}/images/reorder/`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ order })
      });
      await app.readJson(r).catch(()=>{});
    },

    async _reloadImages(){
      if(!this.editingId) return;
      const r = await app.api(`/api/sellers/mine/item-sets/${this.editingId}/images/`, {method:'GET'});
      const j = await app.readJson(r);
      this.existingImages = Array.isArray(j) ? j : [];
    },

    async _loadShippingAll(){
      await Promise.all([this._loadShipOptions(), this._loadShipSuggest()]);
    },

    async _loadShipOptions(){
      if(!this.editingId) return;
      try{
        const r = await app.api(`/api/sellers/mine/item-sets/${this.editingId}/shipping-options/`, {method:'GET'});
        const j = await app.readJson(r);
        this.ship.options = Array.isArray(j) ? j : [];
      }catch{
        this.ship.options = [];
      }
    },

    async _loadShipSuggest(){
      if(!this.editingId) return;
      try{
        const r = await app.api(`/api/sellers/mine/item-sets/${this.editingId}/suggest-package-types/`, {method:'GET'});
        const j = await app.readJson(r);
        this.ship.suggest = Array.isArray(j) ? j : [];
      }catch{
        this.ship.suggest = [];
      }
    },

    async addShipping(pkgPublicId, priceOverride=null){
      if(!this.editingId) return;
      this.ship.busy=true; this.ship.err=''; this.ship.ok='';
      try{
        const payload = { package_type_public_id: pkgPublicId };
        if (priceOverride !== null && String(priceOverride).trim() !== '') payload.price_override = String(priceOverride).replace(',','.');
        const r = await app.api(`/api/sellers/mine/item-sets/${this.editingId}/shipping-options/add/`, {
          method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
        });
        const j = await app.readJson(r);
        if(!r.ok) throw new Error(app.errText?.(j) || 'Nie udało się dodać wysyłki.');
        await this._loadShippingAll();
        this.ship.ok='Dodano/zmieniono.';
      }catch(e){
        this.ship.err = e?.message || 'Błąd.';
      }finally{
        this.ship.busy=false;
      }
    },

    async removeShipping(pkgPublicId){
      if(!this.editingId) return;
      this.ship.busy=true; this.ship.err=''; this.ship.ok='';
      try{
        await app.api(`/api/sellers/mine/item-sets/${this.editingId}/shipping-options/${pkgPublicId}/`, {method:'DELETE'});
        await this._loadShippingAll();
        this.ship.ok='Usunięto.';
      }catch(e){
        this.ship.err = e?.message || 'Błąd.';
      }finally{
        this.ship.busy=false;
      }
    },

    async save(){
      this.busy=true; this.ok=''; this.err=''; this.schemaErr='';
      try{
        if (!this._validateClient()){
          app.warn?.('Popraw zaznaczone pola.');
          this._scrollToFirstError();
          return;
        }

        this.form.attributes = this._sanitizeAttrsForSubmit(this.readSSF());

        if (!this.editingId){
          await this.ensureSellerId();
          if (!this.seller_public_id){ this.err='Brak seller_public_id.'; app.error?.(this.err); return; }
        }

        const priceStr = (this.form.price_str ?? '').toString().trim().replace(',', '.');

        const base = {
          set_name: this.form.set_name,
          description: this.form.description,
          stock_quantity: Math.max(1, parseInt(this.form.stock_quantity || 1, 10)),
          condition: this.form.condition,
          listing_type: this.form.listing_type,
          allow_online_checkout: !!this.form.allow_online_checkout,
          attributes: this.form.attributes || {},
          length_cm: this.form.length_cm ?? null,
          width_cm:  this.form.width_cm ?? null,
          height_cm: this.form.height_cm ?? null,
          weight_kg: this.form.weight_kg ?? null
        };

        if (priceStr !== '' && isFinite(parseFloat(priceStr))) base.price = parseFloat(priceStr);
        if (this.selectedTypePk) base.type = this.selectedTypePk;

        let createdId = this.editingId;

        if (this.editingId){
          const payload = { ...base };
          if (this.catalogItemUUID) payload.catalog_item = String(this.catalogItemUUID);
          else if (this.initialCatalogItemUUID) payload.catalog_item = null;

          const r = await app.api(`/api/sellers/mine/item-sets/${this.editingId}/`, {
            method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
          });
          const j = await app.readJson(r);

          if (!r.ok){
            if (j?.errors?.attributes){
              this.schemaErr = this._prettyAttrError(this._toAttrErrorString(j.errors.attributes));
              this._scrollToAttrs();
            }
            this._mapServerErrorsToFields(j);
            app.warn?.('Popraw zaznaczone pola.');
            this._scrollToFirstError();
            return;
          }
        } else {
          const payload = { ...base, seller_public_id: String(this.seller_public_id) };
          if (this.catalogItemUUID) payload.catalog_item = String(this.catalogItemUUID);

          const r = await app.api(`/api/sellers/mine/item-sets/`, {
            method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
          });
          const j = await app.readJson(r);

          if (!r.ok){
            if (j?.errors?.attributes){
              this.schemaErr = this._prettyAttrError(this._toAttrErrorString(j.errors.attributes));
              this._scrollToAttrs();
            }
            this._mapServerErrorsToFields(j);
            app.warn?.('Popraw zaznaczone pola.');
            this._scrollToFirstError();
            return;
          }

          createdId = j.public_id || j.id || createdId;
          this.editingId = createdId;
          this.initialCatalogItemUUID = this.catalogItemUUID || '';
        }

        for (const imgId of this.removeExistingIds.slice()){
          const d = await app.api(`/api/sellers/mine/item-sets/${createdId}/images/${imgId}/`, { method:'DELETE' });
          if (!d.ok){ const msg='Nie udało się usunąć zdjęcia.'; this.err=msg; app.error?.(msg); return; }
        }
        this.removeExistingIds = [];

        for (const f of this.stagedFiles.slice()){
          const fd = new FormData();
          fd.append('image', f);
          const up = await app.api(`/api/sellers/mine/item-sets/${createdId}/images/upload/`, { method:'POST', body: fd });
          if (!up.ok){
            const j=await app.readJson(up);
            const msg=_toErrorString(j) || 'Nie udało się wgrać zdjęcia.';
            this.err = msg; app.error?.(msg); return;
          }
        }
        this.stagedFiles = [];

        await this._reloadImages();
        if (this.canAddShipping) await this._loadShippingAll();

        const okMsg='Zapisano.';
        this.ok=okMsg; app.ok?.(okMsg);
        app.goto?.('/seller');
      } catch (e) {
        const msg = e?.message || 'Błąd sieci';
        this.err = msg;
        app.error?.(msg);
      } finally {
        this.busy = false;
      }
    },

    _mapServerErrorsToFields(j){
      const src = j?.errors || j || {};
      const map = {};
      const setIf = (k, v) => { if (v) map[k] = _toErrorString(v); };

      setIf('set_name', src.set_name);
      setIf('price_str', src.price || src.price_str);
      setIf('type', src.type);
      setIf('stock_quantity', src.stock_quantity);

      const nfe = src.non_field_errors || src.detail;
      if (nfe) this.err = _toErrorString(nfe);

      for (const [k, v] of Object.entries(src)) {
        if (map[k] || ['attributes','non_field_errors','detail','price','price_str','set_name','type','stock_quantity'].includes(k)) continue;
        map[k] = _toErrorString(v);
      }
      this.errors = { ...this.errors, ...map };
    }
  };
};
