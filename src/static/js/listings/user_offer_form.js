// static/js/user_offer_form.js
window.app = window.app || {};

/* ---------- Fallbacki spójne z offer_form.js ---------- */
app.imgUrl   = app.imgUrl   || (p => p || 'https://placehold.co/600x600?text=%20');
app.api      = app.api      || ((url, opts = {}) => fetch(url, { credentials: 'include', ...opts }));
app.readJson = app.readJson || (async (r) => { try { return await r.json(); } catch { return {}; } });

app._mergeAttrsPreferCurrent = app._mergeAttrsPreferCurrent || function (current, incoming) {
  const out = { ...(incoming || {}) };
  const cur = current || {};
  for (const [k, v] of Object.entries(cur)) if (v !== '' && v !== null && typeof v !== 'undefined') out[k] = v;
  for (const k of Object.keys(cur)) if (!(k in out)) out[k] = cur[k];
  return out;
};

function _toErrorString(v) {
  if (!v) return '';
  if (Array.isArray(v)) return v.map(String).join(' ');
  if (typeof v === 'object') return Object.values(v).flat().map(String).join(' ');
  return String(v);
}

/* ---------- Wspólny cache schematów/UI (TTL 10 min) ---------- */
app._schemaCache = app._schemaCache || new Map();
app.getSchemaCached = app.getSchemaCached || async function(path){
  const key = 'schema:'+path;
  const hit = app._schemaCache.get(key);
  if (hit && (!hit.t || Date.now() < hit.t)) return hit.v;
  const r = await app.api(`/api/public/catalog/categories/schema/by-path/${encodeURIComponent(path)}`, { method:'GET' });
  const j = await app.readJson(r);
  const v = { schema: j.schema || {type:'object',properties:{}}, ui_schema: j.ui_schema || {} };
  app._schemaCache.set(key, { v, t: Date.now() + 10*60*1000 });
  return v;
};

/* ---------- Pickery ---------- */
app._makeCategoryPicker = app._makeCategoryPicker || function () {
  return {
    open: false, loading: false, nodes: [], crumbs: [],
    onPick: (node) => {},
    async openAtRoot(){ this.crumbs = []; this.open = true; await this.load(null); },
    async load(parentPath){
      this.loading = true; this.nodes = [];
      try{
        const u = parentPath
          ? `/api/public/catalog/categories?parent_path=${encodeURIComponent(parentPath)}`
          : `/api/public/catalog/categories`;
        const r = await app.api(u, { method: 'GET' });
        const j = await app.readJson(r);
        this.nodes = j.results ?? j ?? [];
      } finally { this.loading=false; }
    },
    async enter(n){ this.crumbs.push({name:n.name, path:n.path}); await this.load(n.path); },
    async backTo(i){ this.crumbs = this.crumbs.slice(0, i); const p = this.crumbs.length ? this.crumbs.at(-1).path : null; await this.load(p); },
    pick(n){ const cc = Number(n.children_count || 0); if (cc === 0){ this.onPick(n); this.open=false; } else { this.enter(n); } },
    close(){ this.open=false; }
  };
};

app._makeCatalogPicker = app._makeCatalogPicker || function () {
  return {
    open:false, q:'', typePath:'', loading:false, items:[], next:null,
    onPick:(it)=>{},

    /* cache UI po path + nonce do re-renderu Alpine */
    _uiByPath: Object.create(null),
    uiNonce: 0,

    async _ensureUiSchema(path){
      if (!path || this._uiByPath[path]) return;
      try{
        const { ui_schema } = await app.getSchemaCached(path);
        this._uiByPath[path] = ui_schema || {};
      } catch {
        this._uiByPath[path] = {};
      } finally {
        this.uiNonce++;
      }
    },
    pairsFor(it){
      const attrs = (it && (it.attributes || it.attrs || it.specs || it.properties)) || {};
      if (!attrs || !Object.keys(attrs).length) return [];
      const path = it?.type?.path || '';
      const ui = path ? (this._uiByPath[path] ?? null) : null;
      if (path && ui === null) { this._uiByPath[path] = undefined; this._ensureUiSchema(path).catch(()=>{}); }
      try { return app.attrPairs ? app.attrPairs(attrs, ui || {}) : Object.entries(attrs); }
      catch { return Object.entries(attrs); }
    },

    async openWith(typePath=''){
      this.q=''; this.typePath=typePath||'';
      this.open = true;
      await this.search().catch(()=>{});
    },
    async search(url=null){
      this.loading=true; this.items=[]; this.next=null;
      try{
        const params=[];
        if ((this.q||'').trim().length>=2) params.push(`search=${encodeURIComponent(this.q.trim())}`);
        if (this.typePath) params.push(`type_path=${encodeURIComponent(this.typePath)}`);
        const u = url || `/api/public/catalog/items/?ordering=item_name${params.length?'&'+params.join('&'):''}`;
        const r = await app.api(u,{method:'GET'});
        const j = await app.readJson(r);
        this.items = j.results ?? j ?? [];
        this.next = j.next ?? null;

        const paths = new Set(this.items.map(x => x?.type?.path).filter(Boolean));
        for (const p of paths) this._ensureUiSchema(p).catch(()=>{});
      } finally { this.loading=false; }
    },
    async more(){ if(this.next) await this.search(this.next); },
    pick(it){ this.onPick(it); this.open=false; },
    close(){ this.open=false; }
  };
};

/* ---------- SSF helpers ---------- */
app.ssf = app.ssf || {
  mount(el, schema, value){ if (window.SSF) SSF.swapSchema(el, schema||{type:'object',properties:{}}, value||{}); },
  read(el){ try { return window.SSF ? SSF.getValue(el) : {}; } catch { return {}; } }
};

/* ---------- Formularz USER ---------- */
app.userOfferForm = function (opts = {}) {
  return {
    editingId: (opts.editingId || '').trim(),

    form: {
      set_name:'', description:'', price_str:'',
      stock_quantity:1, condition:'USED', listing_type:'LISTING',
      attributes:{},
      length_cm:null, width_cm:null, height_cm:null, weight_kg:null,
    },
    schema: { type:'object', properties:{} },
    ui_schema: {},

    selectedType:null, selectedTypePk:'',
    selectedCatalog:null, catalogItemUUID:'', catalogPublicId:'',
    initialCatalogItemUUID:'',

    existingImages:[], stagedFiles:[], removeExistingIds:[],
    _dzOver:false, _dragIdx:null,

    // pickery — placeholdery (zachowujemy referencję)
    catPicker:  { open:false, loading:false, nodes:[], crumbs:[], onPick(){}, openAtRoot(){}, load(){}, enter(){}, backTo(){}, pick(){}, close(){} },
    ciPicker:   { open:false, q:'', typePath:'', loading:false, items:[], next:null, onPick(){}, openWith(){}, search(){}, more(){}, pick(){}, close(){} },

    // błędy/stan
    busy:false, err:'', ok:'', schemaErr:'',
    errors: {},

    /* ===== Walidacja frontowa ===== */
    _clearErrors(){ this.errors = {}; this.schemaErr=''; this.err=''; },
    _setError(field, msg){ if (msg) this.errors[field] = String(msg); else delete this.errors[field]; },
    _scrollToFirstError(){
      const order = ['set_name','price_str','type','stock_quantity'];
      for (const k of order){
        if (this.errors[k]){
          const el = document.getElementById('f_'+k) || document.querySelector(`[name="${k}"]`);
          if (el?.scrollIntoView) el.scrollIntoView({behavior:'smooth', block:'center'});
          try { el?.focus({ preventScroll: true }); } catch {}
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
    },
    _validateClient(){
      this._clearErrors();
      this._validateField('set_name');
      this._validateField('price_str');
      this._validateField('type');
      this._validateField('stock_quantity');
      return Object.keys(this.errors).length === 0;
    },

    /* ===== INIT ===== */
    async init(){
      Object.assign(this.catPicker, app._makeCategoryPicker());
      Object.assign(this.ciPicker,  app._makeCatalogPicker());

      if (this.editingId) await this.loadForEdit(this.editingId);
      this._mountSSF();

      // Kategoria
      this.catPicker.onPick = async (node) => {
        if (this.selectedCatalog) return;
        await this._applyTypeFromPath(node.path, node.name);
        delete this.errors.type;
        this._mountSSF();
      };

      // Katalog (prefill public)
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
            const r = await app.api(`/api/public/catalog/items/${encodeURIComponent(this.catalogPublicId)}/prefill`,{method:'GET'});
            if (r.ok){
              const d = await app.readJson(r);
              this.form.attributes = app._mergeAttrsPreferCurrent(this.form.attributes, d.attributes || {});
            }
          }
        } catch {}
        delete this.errors.type;
        this._mountSSF();
      };

      // Watchery UX
      this.$watch('form.set_name', () => this._validateField('set_name'));
      this.$watch('form.price_str', () => this._validateField('price_str'));
      this.$watch('form.stock_quantity', () => this._validateField('stock_quantity'));
    },

    async loadForEdit(id){
      try{
        const r = await app.api(`/api/users/me/item-sets/${id}/`, {method:'GET'});
        if (!r.ok){ this.err='Nie udało się wczytać ogłoszenia.'; return; }
        const row = await app.readJson(r);

        const rawPrice = row.price ?? null;
        const amount = (rawPrice && typeof rawPrice === 'object') ? rawPrice.amount : rawPrice;

        this.form = {
          set_name: row.set_name || '',
          description: row.description || '',
          price_str: (amount ?? '') === '' ? '' : String(amount),
          stock_quantity: row.stock_quantity ?? 1,
          condition: row.condition || 'USED',
          listing_type: (row.listing_type === 'BUY') ? 'LISTING' : (row.listing_type || 'LISTING'),
          attributes: row.attributes || {},
          length_cm: row.length_cm ?? null,
          width_cm:  row.width_cm ?? null,
          height_cm: row.height_cm ?? null,
          weight_kg: row.weight_kg ?? null,
        };

        if (row.type?.path){ await this._applyTypeFromPath(row.type.path, row.type.name); }
        this.existingImages = Array.isArray(row.images)? row.images : [];

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

      } catch { this.err='Błąd sieci.'; }
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
      } catch { this.selectedTypePk=''; }
      this.selectedType = { name, path, children_count: 0 };
    },

    _mountSSF(){
      const el = document.getElementById('user_offer_attrs_ssf');
      if (!el) return;
      const val = (this.form.attributes && Object.keys(this.form.attributes).length) ? this.form.attributes : {};
      app.ssf.mount(el, this.schema, val, this.ui_schema);
    },
    readSSF(){
      const el = document.getElementById('user_offer_attrs_ssf');
      if (!el) return {};
      try { return app.ssf.read(el) || {}; } catch { return {}; }
    },
    _scrollToAttrs(){
      const el = document.getElementById('user_offer_attrs_ssf');
      if (!el) return;
      try { el.scrollIntoView({behavior:'smooth', block:'center'}); } catch {}
    },

    /* Czytelne pary (etykieta, wartość) — do podglądu selectedCatalog */
    _attrPairs(attrs){
      try { return app.attrPairs ? app.attrPairs(attrs || {}, this.ui_schema || {}) : Object.entries(attrs || {}); }
      catch { return Object.entries(attrs || {}); }
    },

    // UI pickery
    openCategoryPicker(){ if (this.selectedCatalog) return; this.catPicker.openAtRoot(); },
    clearCategory(){
      if (this.selectedCatalog) return;
      this.selectedType=null; this.selectedTypePk='';
      this.schema={type:'object',properties:{}};
      this.ui_schema={};
      this._mountSSF();
      this._validateField('type');
    },
    openCatalogPicker(){ this.ciPicker.openWith(this.selectedType?.path || ''); },
    clearCatalog(){
      this.selectedCatalog=null; this.catalogItemUUID=''; this.catalogPublicId='';
      this._mountSSF();
      this._validateField('type');
    },

    // Files
    onFiles(ev){ const files = Array.from(ev.target.files||[]); for (const f of files){ if (f.type.startsWith('image/')) this.stagedFiles.push(f); } ev.target.value=''; },
    removeStaged(i){ this.stagedFiles.splice(i,1); },

    // Dropzone
    onDragOver(e){ e.preventDefault(); this._dzOver=true; },
    onDragLeave(e){ e.preventDefault(); this._dzOver=false; },
    onDrop(e){ e.preventDefault(); const files = Array.from(e.dataTransfer?.files || []); for (const f of files){ if (f.type?.startsWith('image/')) this.stagedFiles.push(f); } this._dzOver=false; },

    // Existing images
    toggleRemoveExisting(id){
      const i = this.removeExistingIds.indexOf(id);
      if (i>=0) this.removeExistingIds.splice(i,1); else this.removeExistingIds.push(id);
    },

    // Reorder (drag&drop)
    startDrag(idx){ this._dragIdx = idx; },
    async dropDrag(idx){
      const from = this._dragIdx; this._dragIdx = null;
      if (from===null || from===idx) return;
      const arr = this.existingImages; const [m] = arr.splice(from,1); arr.splice(idx,0,m);
      await this._persistReorder().catch(()=>this._reloadImages());
    },
    async _persistReorder(){
      if (!this.editingId) return;
      const order = this.existingImages.map(x => x.public_id || x.id).filter(Boolean);
      const r = await app.api(`/api/users/me/item-sets/${this.editingId}/images/reorder/`, {
        method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ order })
      });
      await app.readJson(r).catch(()=>{});
    },
    async _reloadImages(){
      if(!this.editingId) return;
      const r = await app.api(`/api/users/me/item-sets/${this.editingId}/images/`, {method:'GET'});
      const j = await app.readJson(r);
      this.existingImages = Array.isArray(j) ? j : [];
    },

    /* ===== ZAPIS ===== */
    async save(){
      this.busy=true; this.err=''; this.ok=''; this.schemaErr='';
      try{
        if (!this._validateClient()){
          app.warn?.('Popraw zaznaczone pola.');
          this._scrollToFirstError();
          return;
        }

        this.form.attributes = this.readSSF();
        const priceStr = (this.form.price_str ?? '').toString().trim().replace(',', '.');

        const base = {
          set_name: this.form.set_name,
          description: this.form.description,
          stock_quantity: Math.max(1, parseInt(this.form.stock_quantity || 1, 10)),
          condition: this.form.condition,
          listing_type: (this.form.listing_type === 'BUY') ? 'LISTING' : this.form.listing_type,
          attributes: this.form.attributes || {},
          length_cm: this.form.length_cm ?? null,
          width_cm:  this.form.width_cm ?? null,
          height_cm: this.form.height_cm ?? null,
          weight_kg: this.form.weight_kg ?? null,
        };
        if (priceStr !== '' && isFinite(parseFloat(priceStr))) base.price = parseFloat(priceStr);
        if (this.selectedTypePk) base.type = this.selectedTypePk;

        let createdId = this.editingId;

        // PATCH vs POST
        if (this.editingId){
          const payload = { ...base };
          if (this.catalogItemUUID) payload.catalog_item = String(this.catalogItemUUID);
          else if (this.initialCatalogItemUUID) payload.catalog_item = null;

          const r = await app.api(`/api/users/me/item-sets/${this.editingId}/`, {
            method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
          });
          const j = await app.readJson(r);

          if (!r.ok){
            if (this._handleKnownErrors(r, j)) return;
            if (j?.errors?.attributes){ this.schemaErr = _toErrorString(j.errors.attributes); this._scrollToAttrs(); }
            this._mapServerErrorsToFields(j);
            app.warn?.('Popraw zaznaczone pola.');
            this._scrollToFirstError();
            return;
          }
        } else {
          const payload = { ...base };
          if (this.catalogItemUUID) payload.catalog_item = String(this.catalogItemUUID);

          const r = await app.api(`/api/users/me/item-sets/`, {
            method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
          });
          const j = await app.readJson(r);

          if (!r.ok){
            if (this._handleKnownErrors(r, j)) return;
            if (j?.errors?.attributes){ this.schemaErr = _toErrorString(j.errors.attributes); this._scrollToAttrs(); }
            this._mapServerErrorsToFields(j);
            app.warn?.('Popraw zaznaczone pola.');
            this._scrollToFirstError();
            return;
          }
          createdId = j.public_id || j.id || createdId;
          this.editingId = createdId;
          this.initialCatalogItemUUID = this.catalogItemUUID || '';
        }

        // usuwanie istniejących
        for (const imgId of this.removeExistingIds.slice()){
          const d = await app.api(`/api/users/me/item-sets/${createdId}/images/${imgId}/`, { method:'DELETE' });
          if (!d.ok){
            const jj = await app.readJson(d);
            const msg = _toErrorString(jj) || 'Nie udało się usunąć zdjęcia.';
            this.err = msg; app.error?.(msg); return;
          }
        }
        this.removeExistingIds = [];

        // upload nowych
        for (const f of this.stagedFiles.slice()){
          const fd = new FormData();
          fd.append('image', f);
          const up = await app.api(`/api/users/me/item-sets/${createdId}/images/upload/`, { method:'POST', body: fd });
          if (!up.ok){
            const j=await app.readJson(up);
            const msg=_toErrorString(j) || 'Nie udało się wgrać zdjęcia.';
            this.err = msg; app.error?.(msg); return;
          }
        }
        this.stagedFiles = [];

        await this._reloadImages();

        const okMsg='Zapisano.';
        this.ok=okMsg; app.ok?.(okMsg);
        app.goto?.('/me');
      } catch (e) {
        const msg = e?.message || 'Błąd';
        this.err = msg; app.error?.(msg);
      } finally {
        this.busy=false;
      }
    },

    /* ===== Specjalne ścieżki błędów ===== */
    _handleKnownErrors(r, j){
      const code = String(j?.code || '').toLowerCase();
      if (r.status === 409 || code === 'no_slots_left'){
        this._applyNoSlotsError(j);
        return true;
      }
      if (j && j.detail && !j.errors){
        const msg = typeof j.detail === 'string' ? j.detail : _toErrorString(j.detail);
        this.err = msg; app.warn?.(msg);
      }
      return false;
    },
    _applyNoSlotsError(payload){
      const msg = payload?.detail || 'Wyczerpałeś limit ogłoszeń w tej kategorii.';
      this._setError('type', 'Brak wolnych slotów w tej kategorii.');
      this.err = msg;
      app.warn?.(msg);
      this._scrollToFirstError();
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
        if (map[k] || ['attributes','non_field_errors','detail','price','price_str','set_name','type','stock_quantity','code'].includes(k)) continue;
        map[k] = _toErrorString(v);
      }
      this.errors = { ...this.errors, ...map };
    },
  };
};
