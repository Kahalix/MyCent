// static/js/listings/offer_form.js
window.app = window.app || {};

/* ---------- Fallbacki pomocnicze ---------- */
app.imgUrl   = app.imgUrl   || (p => p || 'https://placehold.co/600x600?text=%20');
app.api      = app.api      || ((url, opts = {}) => fetch(url, { credentials: 'include', ...opts }));
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

/* ---------- Lekki cache schematów/UI (TTL 10 min) ---------- */
app._schemaCache = app._schemaCache || new Map();
app.getSchemaCached = async function(path){
  const key = 'schema:'+path;
  const hit = app._schemaCache.get(key);
  if (hit && (!hit.t || Date.now() < hit.t)) return hit.v;
  const r = await app.api(`/api/public/catalog/categories/schema/by-path/${encodeURIComponent(path)}`, { method:'GET' });
  const j = await app.readJson(r);
  const v = { schema: j.schema || {type:'object',properties:{}}, ui_schema: j.ui_schema || {} };
  app._schemaCache.set(key, { v, t: Date.now() + 10*60*1000 });
  return v;
};

/* ---------- Helpers core ---------- */
app._mergeAttrsPreferCurrent = function (current, incoming) {
  const out = { ...(incoming || {}) };
  const cur = current || {};
  for (const [k, v] of Object.entries(cur)) {
    if (v !== '' && v !== null && typeof v !== 'undefined') out[k] = v; // prefer user value
  }
  for (const k of Object.keys(cur)) {
    if (!(k in out)) out[k] = cur[k];
  }
  return out;
};

function _toErrorString(v) {
  if (!v) return '';
  if (Array.isArray(v)) return v.map(String).join(' ');
  if (typeof v === 'object') return Object.values(v).flat().map(String).join(' ');
  return String(v);
}

/* ---------- Pickery ---------- */
app._makeCategoryPicker = function () {
  return {
    open: false, loading: false, nodes: [], crumbs: [],
    onPick: (node) => {},
    async openAtRoot() {
      this.crumbs = [];
      this.open = true;
      await this.load(null);
    },
    async load(parentPath) {
      this.loading = true; this.nodes = [];
      try {
        const u = parentPath
          ? `/api/public/catalog/categories?parent_path=${encodeURIComponent(parentPath)}`
          : `/api/public/catalog/categories`;
        const r = await app.api(u, { method: 'GET' });
        const j = await app.readJson(r);
        this.nodes = j.results ?? j ?? [];
      } finally { this.loading = false; }
    },
    async enter(n){
      this.crumbs.push({name:n.name, path:n.path});
      await this.load(n.path);
    },
    async backTo(i){
      this.crumbs = this.crumbs.slice(0, i);
      const p = this.crumbs.length ? this.crumbs.at(-1).path : null;
      await this.load(p);
    },
    pick(n){
      const cc = Number(n.children_count || 0);
      if (cc === 0){ this.onPick(n); this.open=false; }
      else { this.enter(n); }
    },
    close(){ this.open=false; }
  };
};

app._makeCatalogPicker = function () {
  return {
    open:false, q:'', typePath:'', loading:false, items:[], next:null,
    onPick:(it)=>{},

    // --- cache UI-schematów (po path) + nonce do re-renderu Alpine
    _uiByPath: Object.create(null),
    uiNonce: 0,

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

        // prefetch UI dla typów widocznych na liście
        const paths = new Set(this.items.map(it => it?.type?.path).filter(Boolean));
        for (const p of paths) this._ensureUiSchema(p).catch(()=>{});
      } finally { this.loading=false; }
    },

    async more(){ if(this.next) await this.search(this.next); },
    pick(it){ this.onPick(it); this.open=false; },
    close(){ this.open=false; },

    async _ensureUiSchema(path){
      if (!path || this._uiByPath[path]) return;
      try {
        const { ui_schema } = await app.getSchemaCached(path);
        this._uiByPath[path] = ui_schema || {};
      } catch {
        this._uiByPath[path] = {};
      } finally {
        // wymuś re-render atrybutów w Alpine (używane w :key)
        this.uiNonce++;
      }
    },

    // Używane w HTML: ciPicker.pairsFor(it)
    pairsFor(it){
      const attrs = (it && (it.attributes || it.attrs || it.specs || it.properties)) || {};
      if (!attrs || !Object.keys(attrs).length) return [];
      const path = it?.type?.path || '';
      const ui = path ? (this._uiByPath[path] || null) : null;

      // jeśli jeszcze nie mamy UI – odpal fetch asynchronicznie
      if (path && ui === null) {
        this._uiByPath[path] = undefined; // placeholder, by nie fetchować wielokrotnie
        this._ensureUiSchema(path).catch(()=>{});
      }

      try {
        // pretty (etykiety + jednostki) – wymaga attrs-pl.js
        return app.attrPairs ? app.attrPairs(attrs, ui || {}) : Object.entries(attrs).map(([k,v])=>[String(k), String(v)]);
      } catch {
        return Object.entries(attrs).map(([k,v])=>[String(k), String(v)]);
      }
    },
  };
};

/* ---------- Ship picker (modal) ---------- */
app._makeShipPicker = function (ctx) {
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
      return base || (`/api/public/shipping/package-types/?ordering=price${params.length?'&'+params.join('&'):''}`);
    },
    async search(url=null){
      this.loading=true; this.items=[]; this.next=null;
      try{
        const u = url || this._buildUrl();
        const r = await app.api(u,{method:'GET'});
        const j = await app.readJson(r);
        this.items = j.results ?? j ?? [];
        this.next = j.next ?? null;
      } finally { this.loading=false; }
    },
    async more(){ if(this.next) await this.search(this.next); },
    close(){ this.open=false; }
  };
};

// === UPIĘKSZANIE SCHEMATU wg ui_schema (labels/units/order) ===
app.decorateSchemaForUi = app.decorateSchemaForUi || function(schema, ui){
  const UI = (ui && (ui.attrs || ui)) || {};
  const labels = UI.labels || {};
  const units  = UI.units  || {};
  const order  = Array.isArray(UI.order) ? UI.order : null;

  const src = schema || { type:'object', properties:{} };
  const s = JSON.parse(JSON.stringify(src));

  function prettyLabel(key){
    if (labels[key]) return labels[key];
    return app.attrLabel ? app.attrLabel(key, UI) : key;
  }
  function labelWithUnit(key){
    const base = prettyLabel(key);
    const u = units[key];
    return u ? `${base} [${u}]` : base;
  }
  function applyLabels(def, key){
    const nice = labelWithUnit(key);
    const targets = ['title','label','x-title','xLabel','x_label'];
    for (const t of targets){
      if (!def[t] || def[t] === key) def[t] = nice;
    }
  }
  function walk(node){
    if (!node || typeof node !== 'object') return;
    if (node.type === 'object' && node.properties){
      if (order){
        const np = {};
        for (const k of order) if (k in node.properties) np[k] = node.properties[k];
        for (const k of Object.keys(node.properties)) if (!(k in np)) np[k] = node.properties[k];
        node.properties = np;
      }
      for (const [k, def] of Object.entries(node.properties)){
        applyLabels(def, k);
        walk(def);
      }
    }
    if (node.type === 'array' && node.items) walk(node.items);
    for (const key of ['oneOf','anyOf','allOf']) if (Array.isArray(node[key])) node[key].forEach(walk);
  }
  walk(s);
  return s;
};

app._replaceRequiredStar = function(el){
  const root = el.closest('.ssf-container') || el.parentElement || document;

  root.querySelectorAll('.ssf-field .ssf-label').forEach(lab => {
    // kontrolka skojarzona z etykietą
    let ctrl = null;
    const forId = lab.getAttribute('for');
    if (forId) { try { ctrl = root.querySelector('#'+CSS.escape(forId)); } catch {} }
    if (!ctrl) ctrl = lab.closest('.ssf-field')?.querySelector('input, select, textarea');

    const hadSpan = lab.querySelector('.ssf-required');     // gwiazdka w osobnym spanie
    const hasStarInText = /\*/.test(lab.textContent || '');
    const isReq = !!(ctrl?.required || lab.classList.contains('is-required') || hadSpan || hasStarInText);

    // usuń istniejące badge'y (by nie dublować)
    lab.querySelectorAll('.req-badge').forEach(n => n.remove());
    if (!isReq) return;

    // usuń fallbackową gwiazdkę, jeśli była
    if (hadSpan) hadSpan.remove();

    // na wszelki wypadek wyczyść gwiazdki TYLKO z węzła tekstowego etykiety (nie tykamy jednostek)
    const textEl = lab.querySelector('.ssf-label__text');
    if (textEl && textEl.firstChild && textEl.firstChild.nodeType === Node.TEXT_NODE){
      textEl.firstChild.nodeValue = textEl.firstChild.nodeValue.replace(/\s*\*\s*$/, '');
    }

    // wstaw pastylkę „Wymagane”
    const badge = document.createElement('span');
    badge.className = 'req-badge';
    badge.textContent = 'Wymagane';
    lab.append(badge);
  });
};


/* ---------- SSF helpers ---------- */
// === Po-renderowy patch labeli SSF ==
app._postFixSsfLabels = function(el, ui){
  const UI = (ui && (ui.attrs || ui)) || {};
  const labels = UI.labels || {};
  const units  = UI.units  || {};

  const normKey = (name) => {
    if (!name) return '';
    name = String(name);
    // weź ostatni segment z notacji kropkowej lub bracketowej
    // np. "attributes.power_w" -> "power_w", "attributes[power_w]" -> "power_w"
    if (name.includes('.')) name = name.split('.').pop();
    if (name.includes('[')) name = name.split('[').pop().split(']')[0];
    return name.trim();
  };

  const root = el.closest('.ssf-container') || el.parentElement || document;
  root.querySelectorAll('.ssf-field').forEach(fld => {
    const lab = fld.querySelector('.ssf-label');
    if (!lab) return;

    const raw = lab.textContent || '';
    const hasStar = /\*/.test(raw) || lab.classList.contains('is-required');

    // spróbuj wydobyć klucz z powiązanego elementu form
    const ctrl = fld.querySelector('input[name], select[name], textarea[name]');
    const key = normKey(ctrl?.name)
            || fld.getAttribute('data-key')
            || lab.getAttribute('data-key')
            || raw.replace(/\s*\*.*$/, '').trim(); // ostateczny fallback

    // Zbuduj ładną etykietę na podstawie PRAWDZIWEGO klucza:
    const base = labels[key] || (app.attrLabel ? app.attrLabel(key, UI) : key);
    const unit = units[key];
    const pretty = unit ? `${base} [${unit}]` : base;

    // Jeśli już jest dobrze (bez gwiazdki), nie grzebiemy
    const rawNoStar = raw.replace(/\s*\*.*$/, '').trim();
    if (rawNoStar === pretty) return;

    lab.textContent = '';
    const span = document.createElement('span');
    span.className = 'ssf-label__text';
    span.textContent = pretty;
    lab.append(span);

    if (hasStar){
      const star = document.createElement('span');
      star.className = 'ssf-required';
      star.textContent = ' *';
      lab.append(star);
    }

  });
};

// === SSF helpers ===
app.ssf = {
  mount(el, schema, value, ui){
    const deco = app.decorateSchemaForUi ? app.decorateSchemaForUi(schema, ui) : (schema || {type:'object',properties:{}});
    if (window.SSF){
      SSF.swapSchema(el, deco, value || {});
      const patchAll = () => {
        // zostawiamy Twoje etykiety/units
        app._postFixSsfLabels(el, ui);
        // tylko zamieniamy gwiazdkę na nasz znacznik
        app._replaceRequiredStar(el);
      };
      requestAnimationFrame(patchAll);
    }
  },
  read(el){ try { return window.SSF ? SSF.getValue(el) : {}; } catch { return {}; } }
};




/* ---------- Formularz oferty ---------- */
app.sellerOfferForm = function (opts = {}) {
  return {
    editingId: (opts.editingId || '').trim(),
    seller_public_id: '',

    async ensureSellerId(){
      if (this.seller_public_id) return this.seller_public_id;
      try{
        const r = await app.api('/api/sellers/mine/', {method:'GET'});
        if (r.ok){ const me = await app.readJson(r); this.seller_public_id = me.public_id || me?.seller?.public_id || ''; }
      } catch {}
      return this.seller_public_id;
    },

    form: {
      set_name:'', description:'', price_str:'',
      stock_quantity:1, condition:'USED', listing_type:'LISTING',
      allow_online_checkout:false, attributes:{},
      length_cm:null, width_cm:null, height_cm:null, weight_kg:null,
    },
    schema: { type:'object', properties:{} },
    ui_schema: {},

    selectedType:null, selectedTypePk:'',
    selectedCatalog:null, catalogItemUUID:'', catalogPublicId:'',
    initialCatalogItemUUID:'',

    existingImages:[], stagedFiles:[], removeExistingIds:[],
    _dzOver:false, _dragIdx:null,

    // shipping
    canAddShipping:false,
    ship:{ options:[], suggest:[], busy:false, err:'', ok:'' },

    // błędy
    errors: {},     // { field: "komunikat" }
    schemaErr:'',   // błędy atrybutów
    err:'', ok:'',  // ogólne

    // pickery — placeholdery (NIE PODMIENIAMY REFERENCJI!)
    catPicker:  { open:false, loading:false, nodes:[], crumbs:[], onPick(){}, openAtRoot(){}, load(){}, enter(){}, backTo(){}, pick(){}, close(){} },
    ciPicker:   { open:false, q:'', typePath:'', loading:false, items:[], next:null, onPick(){}, openWith(){}, search(){}, more(){}, pick(){}, close(){} },
    shipPicker: { open:false, loading:false, items:[], next:null, provider:'', price_override:'', length_cm:null, width_cm:null, height_cm:null, weight_kg:null, openWithDefaults(){}, _buildUrl(){}, search(){}, more(){}, close(){} },

    _attrPairs(attrs){
      try {
        return app.attrPairs
          ? app.attrPairs(attrs || {}, this.ui_schema || {})
          : Object.entries(attrs || {});
      } catch {
        return Object.entries(attrs || {});
      }
    },

    busy:false,

    /* ===== Walidacja frontowa ===== */
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

      // Kategoria
      this.catPicker.onPick = async (node) => {
        if (this.selectedCatalog) return;
        await this._applyTypeFromPath(node.path, node.name);
        delete this.errors.type;
        this._mountSSF();
      };

      // Catalog item
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
        if (it?.type?.path) {
          await this._applyTypeFromPath(it.type.path, it.type.name || '');
        }
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

      // Watchery UX
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

    // UI hooki do przycisków otwierających modale
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
      // po usunięciu katalogu kategoria może być edytowana — jeśli brak kategorii, pokaż błąd
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
            image_path: ci.image_path || ''
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

    // Files
    onFiles(ev){
      const files = Array.from(ev.target.files||[]);
      for (const f of files){ if (f.type.startsWith('image/')) this.stagedFiles.push(f); }
      ev.target.value='';
    },
    removeStaged(i){ this.stagedFiles.splice(i,1); },

    // Dropzone
    onDragOver(e){ e.preventDefault(); this._dzOver=true; },
    onDragLeave(e){ e.preventDefault(); this._dzOver=false; },
    onDrop(e){
      e.preventDefault();
      const files = Array.from(e.dataTransfer?.files || []);
      for (const f of files){ if (f.type?.startsWith('image/')) this.stagedFiles.push(f); }
      this._dzOver=false;
    },

    // Existing images: zaznacz do usunięcia
    toggleRemoveExisting(id){
      const i = this.removeExistingIds.indexOf(id);
      if (i>=0) this.removeExistingIds.splice(i,1); else this.removeExistingIds.push(id);
    },

    // Reorder (drag&drop)
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

    // Wysyłka
    async _loadShippingAll(){
      await Promise.all([this._loadShipOptions(), this._loadShipSuggest()]);
    },
    async _loadShipOptions(){
      if(!this.editingId) return;
      try{
        const r = await app.api(`/api/sellers/mine/item-sets/${this.editingId}/shipping-options/`, {method:'GET'});
        const j = await app.readJson(r);
        this.ship.options = Array.isArray(j) ? j : [];
      }catch{ this.ship.options = []; }
    },
    async _loadShipSuggest(){
      if(!this.editingId) return;
      try{
        const r = await app.api(`/api/sellers/mine/item-sets/${this.editingId}/suggest-package-types/`, {method:'GET'});
        const j = await app.readJson(r);
        this.ship.suggest = Array.isArray(j) ? j : [];
      }catch{ this.ship.suggest = []; }
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
      }catch(e){ this.ship.err = e?.message || 'Błąd.'; }
      finally{ this.ship.busy=false; }
    },
    async removeShipping(pkgPublicId){
      if(!this.editingId) return;
      this.ship.busy=true; this.ship.err=''; this.ship.ok='';
      try{
        await app.api(`/api/sellers/mine/item-sets/${this.editingId}/shipping-options/${pkgPublicId}/`, {method:'DELETE'});
        await this._loadShippingAll();
        this.ship.ok='Usunięto.';
      }catch(e){ this.ship.err = e?.message || 'Błąd.'; }
      finally{ this.ship.busy=false; }
    },

    // ZAPIS
    async save(){
      this.busy=true; this.ok=''; this.err=''; this.schemaErr='';

      try{
        // 1) walidacja frontowa
        if (!this._validateClient()){
          app.warn?.('Popraw zaznaczone pola.');
          this._scrollToFirstError();
          return;
        }

        // 2) payload
        this.form.attributes = this.readSSF();

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
          weight_kg: this.form.weight_kg ?? null,
        };
        if (priceStr !== '' && isFinite(parseFloat(priceStr))) base.price = parseFloat(priceStr);
        if (this.selectedTypePk) base.type = this.selectedTypePk;

        let createdId = this.editingId;

        // 3) call API
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
                this.schemaErr = this._prettyAttrError(_toErrorString(j.errors.attributes));
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

        // 4) usuwanie istniejących
        for (const imgId of this.removeExistingIds.slice()){
          const d = await app.api(`/api/sellers/mine/item-sets/${createdId}/images/${imgId}/`, { method:'DELETE' });
          if (!d.ok){ const msg='Nie udało się usunąć zdjęcia.'; this.err=msg; app.error?.(msg); return; }
        }
        this.removeExistingIds = [];

        // 5) upload nowych
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

        // 6) odśwież
        await this._reloadImages();
        if (this.canAddShipping) await this._loadShippingAll();

        // 7) ok
        const okMsg='Zapisano.';
        this.ok=okMsg; app.ok?.(okMsg);
        app.goto?.('/seller');

      } catch (e) {
        console.error('save() failed:', e);
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
    },
  };
};
