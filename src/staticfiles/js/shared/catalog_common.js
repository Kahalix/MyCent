window.app = window.app || {};

app.imgUrl = app.imgUrl || (p => p || 'https://placehold.co/600x600?text=%20');
app.api = app.api || ((url, opts = {}) => fetch(url, { credentials: 'include', ...opts }));
app.readJson = app.readJson || (async (r) => { try { return await r.json(); } catch { return {}; } });

app._schemaCache = app._schemaCache || new Map();
app.getSchemaCached = app.getSchemaCached || (async function(path){
  const key = 'schema:' + path;
  const hit = app._schemaCache.get(key);
  if (hit && (!hit.t || Date.now() < hit.t)) return hit.v;

  const r = await app.api(`/api/public/catalog/categories/schema/by-path/${encodeURIComponent(path)}`, { method:'GET' });
  const j = await app.readJson(r);
  const v = { schema: j.schema || { type:'object', properties:{} }, ui_schema: j.ui_schema || {} };

  app._schemaCache.set(key, { v, t: Date.now() + 10*60*1000 });
  return v;
});

app._mergeAttrsPreferCurrent = app._mergeAttrsPreferCurrent || function (current, incoming) {
  const out = { ...(incoming || {}) };
  const cur = current || {};
  for (const [k, v] of Object.entries(cur)) {
    if (v !== '' && v !== null && typeof v !== 'undefined') out[k] = v;
  }
  for (const k of Object.keys(cur)) {
    if (!(k in out)) out[k] = cur[k];
  }
  return out;
};

app._makeCategoryPicker = app._makeCategoryPicker || function () {
  return {
    open: false, loading: false, nodes: [], crumbs: [],
    onPick: (node) => {},
    async openAtRoot() {
      this.crumbs = [];
      this.open = true;
      await this.load(null);
    },
    async load(parentPath) {
      this.loading = true;
      this.nodes = [];
      try {
        const u = parentPath
          ? `/api/public/catalog/categories?parent_path=${encodeURIComponent(parentPath)}`
          : `/api/public/catalog/categories`;
        const r = await app.api(u, { method: 'GET' });
        const j = await app.readJson(r);
        this.nodes = j.results ?? j ?? [];
      } finally {
        this.loading = false;
      }
    },
    async enter(n) {
      this.crumbs.push({ name: n.name, path: n.path });
      await this.load(n.path);
    },
    async backTo(i) {
      this.crumbs = this.crumbs.slice(0, i);
      const p = this.crumbs.length ? this.crumbs.at(-1).path : null;
      await this.load(p);
    },
    pick(n) {
      const cc = Number(n.children_count || 0);
      if (cc === 0) {
        this.onPick(n);
        this.open = false;
      } else {
        this.enter(n);
      }
    },
    close() { this.open = false; }
  };
};

app._makeCatalogPicker = app._makeCatalogPicker || function () {
  return {
    open:false, q:'', typePath:'', loading:false, items:[], next:null,
    onPick:(it)=>{},
    _uiByPath: Object.create(null),
    _uiFetchByPath: Object.create(null),
    uiNonce: 0,

    async openWith(typePath=''){
      this.q = '';
      this.typePath = typePath || '';
      this.open = true;
      await this.search(null, false).catch(()=>{});
    },

    async _ensureUiSchema(path){
      if (!path) return;
      if (this._uiByPath[path]) return;
      if (this._uiFetchByPath[path]) return this._uiFetchByPath[path];

      this._uiFetchByPath[path] = (async () => {
        try {
          const { ui_schema } = await app.getSchemaCached(path);
          this._uiByPath[path] = ui_schema || {};
        } catch {
          this._uiByPath[path] = {};
        } finally {
          delete this._uiFetchByPath[path];
          this.uiNonce++;
        }
      })();

      return this._uiFetchByPath[path];
    },

    async search(url=null, append=false){
      if (this.loading) return;
      this.loading = true;

      if (!append){
        this.items = [];
        this.next = null;
      }

      try{
        const params=[];
        if ((this.q||'').trim().length>=2) params.push(`search=${encodeURIComponent(this.q.trim())}`);
        if (this.typePath) params.push(`type_path=${encodeURIComponent(this.typePath)}`);

        const u = url || `/api/public/catalog/items/?ordering=item_name${params.length ? '&'+params.join('&') : ''}`;
        const r = await app.api(u,{method:'GET'});
        const j = await app.readJson(r);

        const fresh = j.results ?? j ?? [];
        this.items = append ? [...this.items, ...fresh] : fresh;
        this.next = j.next ?? null;

        const paths = new Set(fresh.map(it => it?.type?.path).filter(Boolean));
        for (const p of paths) this._ensureUiSchema(p).catch(()=>{});
      } finally {
        this.loading = false;
      }
    },

    async more(){
      if (!this.next || this.loading) return;
      await this.search(this.next, true);
    },

    pairsFor(it){
      const attrs = (it && (it.attributes || it.attrs || it.specs || it.properties)) || {};
      if (!attrs || !Object.keys(attrs).length) return [];

      const path = it?.type?.path || '';
      const ui = path ? (this._uiByPath[path] || null) : null;
      if (path && ui === null) this._ensureUiSchema(path).catch(()=>{});

      try {
        return app.attrPairs
          ? app.attrPairs(attrs, ui || {})
          : Object.entries(attrs).map(([k,v])=>[String(k), String(v)]);
      } catch {
        return Object.entries(attrs).map(([k,v])=>[String(k), String(v)]);
      }
    },

    pick(it){ this.onPick(it); this.open=false; },
    close(){ this.open=false; }
  };
};

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

app._postFixSsfLabels = app._postFixSsfLabels || function(el, ui){
  const UI = (ui && (ui.attrs || ui)) || {};
  const labels = UI.labels || {};
  const units  = UI.units  || {};

  const normKey = (name) => {
    if (!name) return '';
    name = String(name);
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
    const ctrl = fld.querySelector('input[name], select[name], textarea[name]');
    const key = normKey(ctrl?.name)
      || fld.getAttribute('data-key')
      || lab.getAttribute('data-key')
      || raw.replace(/\s*\*.*$/, '').trim();

    const base = labels[key] || (app.attrLabel ? app.attrLabel(key, UI) : key);
    const unit = units[key];
    const pretty = unit ? `${base} [${unit}]` : base;

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

app._replaceRequiredStar = app._replaceRequiredStar || function(el){
  const root = el.closest('.ssf-container') || el.parentElement || document;

  root.querySelectorAll('.ssf-field .ssf-label').forEach(lab => {
    let ctrl = null;
    const forId = lab.getAttribute('for');
    if (forId) { try { ctrl = root.querySelector('#'+CSS.escape(forId)); } catch {} }
    if (!ctrl) ctrl = lab.closest('.ssf-field')?.querySelector('input, select, textarea');

    const hadSpan = lab.querySelector('.ssf-required');
    const hasStarInText = /\*/.test(lab.textContent || '');
    const isReq = !!(ctrl?.required || lab.classList.contains('is-required') || hadSpan || hasStarInText);

    lab.querySelectorAll('.req-badge').forEach(n => n.remove());
    if (!isReq) return;

    if (hadSpan) hadSpan.remove();

    const textEl = lab.querySelector('.ssf-label__text');
    if (textEl && textEl.firstChild && textEl.firstChild.nodeType === Node.TEXT_NODE){
      textEl.firstChild.nodeValue = textEl.firstChild.nodeValue.replace(/\s*\*\s*$/, '');
    }

    const badge = document.createElement('span');
    badge.className = 'req-badge';
    badge.textContent = 'Wymagane';
    lab.append(badge);
  });
};

app.ssf = app.ssf || {
  mount(el, schema, value, ui){
    if (!window.SSF) return;
    const deco = app.decorateSchemaForUi ? app.decorateSchemaForUi(schema, ui) : (schema || {type:'object',properties:{}});
    SSF.swapSchema(el, deco, value || {});
    const patchAll = () => {
      app._postFixSsfLabels(el, ui);
      app._replaceRequiredStar(el);
    };
    requestAnimationFrame(patchAll);
  },
  read(el){ try { return window.SSF ? SSF.getValue(el) : {}; } catch { return {}; } }
};
