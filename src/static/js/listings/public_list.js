window.app = window.app || {};
app._emitToast = app._emitToast || function (type, message) {
  const detail = { type, message };
  try { window.dispatchEvent(new CustomEvent('toast', { detail })); } catch {}
  try { window.dispatchEvent(new CustomEvent('toast:show', { detail })); } catch {}
};
app.ok    = app.ok    || ((m) => app._emitToast('success', m));
app.error = app.error || ((m) => app._emitToast('error', m));
app.api   = app.api   || ((url, opts = {}) => fetch(url, { credentials: 'include', ...opts }));
app.imgUrl= app.imgUrl|| (p => p || 'https://placehold.co/600x600?text=%20');
app.urlParams = app.urlParams || (() => new URLSearchParams(location.search));
app.goto  = app.goto  || (u => { location.href = u; });

app.publicOffersList = function (opts = {}) {
  return {
    // kontekst
    sellerSlug: (opts.sellerSlug || '').trim(),
    ownerPublicId: (opts.ownerPublicId || '').trim(),

    // dane
    items: [],
    loading: false,
    err: '',
    next: null,

    // filtry
    q: '',
    ordering: '-created_at',
    source: 'ALL',
    listing_type: 'ANY',
    condition: 'ANY',
    allow_checkout_only: false,
    price_min: '',
    price_max: '',

    // kategoria
    selectedType: null,
    typePath: '',
    catPicker: null,

    // UI
    filtersOpen: false,

    // zapisy
    saveBusy: {},
    saveSearchBusy: false,

    // prywatne
    _debounce: null,
    _reqId: 0,
    _obs: null,

    _applyPrefill(p) {
      if (!p || typeof p !== 'object') return;

      const truthy = v => ['1','true','True','yes','on'].includes(String(v || '').trim());

      const typePath = String(p.type_path || p.typePath || p.cat || '').trim();
      if (typePath) {
        this.typePath = typePath;
        this.selectedType = { name: typePath.split('/').at(-1), path: typePath, children_count: 0 };
      } else if ('type_path' in p || 'typePath' in p || 'cat' in p) {
        this.typePath = '';
        this.selectedType = null;
      }

      const q = String(p.search || p.q || '').trim();
      if (q) this.q = q;
      else if ('search' in p || 'q' in p) this.q = '';

      const src = String(p.added_by || p.source || '').toUpperCase().trim();
      if (src === 'STAFF' || src === 'USER') this.source = src;
      else if ('added_by' in p || 'source' in p) this.source = 'ALL';

      const lt = String(p.listing_type || '').toUpperCase().trim();
      if (['BUY','LISTING','EXCHANGE'].includes(lt)) this.listing_type = lt;
      else if ('listing_type' in p) this.listing_type = 'ANY';

      const cond = String(p.condition || '').toUpperCase().trim();
      if (['NEW','USED','DAMAGED'].includes(cond)) this.condition = cond;
      else if ('condition' in p) this.condition = 'ANY';

      const ao = truthy(p.allow_online_checkout) || truthy(p.allow_checkout_only) || truthy(p.checkout);
      if ('allow_online_checkout' in p || 'allow_checkout_only' in p || 'checkout' in p) {
        this.allow_checkout_only = !!ao;
      }

      const ord = String(p.ordering || '').trim();
      if (ord) this.ordering = ord;

      if ('price_min' in p) this.price_min = String(p.price_min ?? '');
      if ('price_max' in p) this.price_max = String(p.price_max ?? '');

      const sellerSlug = String(p.seller_slug || '').trim();
      if (sellerSlug) this.sellerSlug = sellerSlug;

      const ownerPublicId = String(p.owner_public_id || '').trim();
      if (ownerPublicId) this.ownerPublicId = ownerPublicId;
    },

    init() {
      // picker
      this.catPicker = app._makeCategoryPicker ? app._makeCategoryPicker() : {
        open:false, openAtRoot(){}, onPick() {}
      };
      this.catPicker.onPick = async (node) => {
        this.selectedType = { name: node.name, path: node.path, children_count: node.children_count || 0 };
        this.typePath = node.path || '';
        this.reload();
      };

      // prefill z shared (sessionStorage) landing/saved
      let usedPrefill = false;
      try {
        const pre = app.offersNav && app.offersNav.take ? app.offersNav.take() : null;
        if (pre) {
          this._applyPrefill(pre);
          usedPrefill = true;
        }
      } catch {}

      // fallback: prefill z URL (OLD)
      if (!usedPrefill) {
        try {
          const p = app.urlParams();
          const typePath = p.get('type_path') || p.get('cat') || '';
          const q = p.get('search') || p.get('q') || '';
          const src = (p.get('added_by') || p.get('source') || '').toUpperCase();
          const lt  = (p.get('listing_type') || '').toUpperCase();
          const cond= (p.get('condition')    || '').toUpperCase();
          const truthy = v => ['1','true','True','yes','on'].includes(String(v||'').trim());
          const ao  = truthy(p.get('allow_online_checkout')) || truthy(p.get('checkout'));
          const o   = p.get('ordering') || '';
          const pmin= p.get('price_min') || p.get('min') || '';
          const pmax= p.get('price_max') || p.get('max') || '';

          if (!this.sellerSlug)     this.sellerSlug     = (p.get('seller_slug')      || '').trim();
          if (!this.ownerPublicId)  this.ownerPublicId  = (p.get('owner_public_id')  || '').trim();

          if (typePath) {
            this.typePath = typePath;
            this.selectedType = { name:typePath.split('/').at(-1), path:typePath, children_count:0 };
          }
          if (q) this.q = q;
          if (src === 'STAFF' || src === 'USER') this.source = src;
          if (['BUY','LISTING','EXCHANGE'].includes(lt)) this.listing_type = lt;
          if (['NEW','USED','DAMAGED'].includes(cond))   this.condition    = cond;
          if (ao) this.allow_checkout_only = true;
          if (o)  this.ordering = o;
          if (pmin) this.price_min = pmin;
          if (pmax) this.price_max = pmax;
        } catch {}
      }
      this.reload();
      this.$nextTick(() => this._setupObserver());
    },

    destroy() {
      if (this._obs) { try { this._obs.disconnect(); } catch {} this._obs = null; }
    },

    _setupObserver() {
      if (!('IntersectionObserver' in window)) return;
      const el = this.$refs?.sentinel;
      if (!el) return;
      this._obs = new IntersectionObserver((entries) => {
        if (entries.some(e => e.isIntersecting)) this.more();
      }, { rootMargin: '240px' });
      this._obs.observe(el);
    },

    onSearchInput() {
      clearTimeout(this._debounce);
      this._debounce = setTimeout(() => this.reload(), 350);
    },

    // Modal
    closeFilters(){ this.filtersOpen = false; },
    applyFilters(){ this.filtersOpen = false; this.reload(); },
    resetAdvanced(){
      this.source = 'ALL';
      this.listing_type = 'ANY';
      this.condition = 'ANY';
      this.allow_checkout_only = false;
      this.price_min = '';
      this.price_max = '';
    },
    filtersCount(){
      let n = 0;
      if (this.source !== 'ALL') n++;
      if (this.listing_type !== 'ANY') n++;
      if (this.condition    !== 'ANY') n++;
      if (this.allow_checkout_only) n++;
      if ((this.price_min||'').trim() !== '') n++;
      if ((this.price_max||'').trim() !== '') n++;
      return n;
    },

    openCategoryPicker() { this.catPicker.openAtRoot(); },
    clearCategory()      { this.selectedType = null; this.typePath = ''; this.reload(); },

    sort(by) { this.ordering = by; this.reload(); },
    reload() { this.load(null, /*replace*/true); },
    async more() {
      if (!this.next || this.loading) return;
      await this.load(this.next, /*replace*/false);
    },

    _qs() {
      const qs = [];
      qs.push(`ordering=${encodeURIComponent(this.ordering)}`);

      const qq = (this.q || '').trim();
      if (qq) qs.push(`search=${encodeURIComponent(qq)}`);

      if (this.sellerSlug) qs.push(`seller_slug=${encodeURIComponent(this.sellerSlug)}`);
      if (this.ownerPublicId) qs.push(`owner_public_id=${encodeURIComponent(this.ownerPublicId)}`);
      if (this.typePath) qs.push(`type_path=${encodeURIComponent(this.typePath)}`);
      if (this.source === 'STAFF' || this.source === 'USER') qs.push(`added_by=${this.source}`);
      if (this.listing_type !== 'ANY') qs.push(`listing_type=${this.listing_type}`);
      if (this.condition    !== 'ANY') qs.push(`condition=${this.condition}`);
      if (this.allow_checkout_only) qs.push('allow_online_checkout=true');

      const pmin = (this.price_min || '').trim();
      const pmax = (this.price_max || '').trim();
      if (pmin !== '') qs.push(`price_min=${encodeURIComponent(pmin)}`);
      if (pmax !== '') qs.push(`price_max=${encodeURIComponent(pmax)}`);

      return qs.join('&');
    },

    async load(url = null, replace = false) {
      this.loading = replace ? true : this.loading;
      if (replace) { this.err = ''; this.items = []; this.next = null; }

      const myReq = ++this._reqId;
      try {
        if (!url) url = `/api/public/item-sets/?${this._qs()}`;

        const r = await app.api(url, { method:'GET' });
        const j = await r.json().catch(() => ({}));
        if (myReq !== this._reqId) return;

        const results = Array.isArray(j) ? j : (j.results ?? []);
        const next = Array.isArray(j) ? null : (j.next ?? null);

        for (const it of results) it.is_saved = !!it.is_saved;

        this.items = replace ? results : this.items.concat(results);
        this.next = next;
      } catch (e) {
        if (myReq !== this._reqId) return;
        this.err = 'Błąd pobierania listy';
      } finally {
        if (myReq === this._reqId) this.loading = false;
      }
    },

    // helpers
    img(it) {
      const first = (Array.isArray(it.images) && it.images.length) ? it.images[0] : null;
      const pic = it.cover_image_url
        || first?.image_path || first?.url || first?.image_url
        || it.catalog_item?.image_path || '';
      return app.imgUrl ? app.imgUrl(pic) : pic;
    },

    priceText(it) {
      if (it && typeof it.price === 'object') {
        const a = it.price.amount ?? '';
        const c = it.price.currency || 'PLN';
        return (a !== '' ? a : '—') + ' ' + c;
      }
      if (typeof it?.price === 'number' || typeof it?.price === 'string') {
        return `${it.price} PLN`;
      }
      return '—';
    },

    who(it) { return it.added_by === 'USER' ? 'użytkownik' : 'sprzedawca'; },

    // mapowania PL
    listingTypePL(it){
      const t = (it?.listing_type || '').toUpperCase();
      return ({ BUY:'Kup teraz', LISTING:'Ogłoszenie', EXCHANGE:'Wymiana' }[t]) || t || '—';
    },
    conditionPL(it){
      const c = (it?.condition || '').toUpperCase();
      return ({ NEW:'Nowy', USED:'Używany', DAMAGED:'Uszkodzony' }[c]) || c || '—';
    },

    // Data + godzina (DD.MM.RRRR, HH:MM)
    createdText(it){
      const iso = it?.created_at || it?.updated_at || '';
      if (!iso) return '';
      const d = new Date(iso);
      if (isNaN(d)) return '';
      const dd = String(d.getDate()).padStart(2,'0');
      const mm = String(d.getMonth()+1).padStart(2,'0');
      const yyyy = d.getFullYear();
      const hh = String(d.getHours()).padStart(2,'0');
      const mi = String(d.getMinutes()).padStart(2,'0');
      return `${dd}.${mm}.${yyyy}, ${hh}:${mi}`;
    },

    // akcje
    gotoItem(it) {
      const slug = it.slug || (it.public_id || '');
      if (slug) app.goto(`/i/${slug}`);
    },

    async toggleSave(it) {
      if (!it || !it.public_id || this.saveBusy[it.public_id]) return;
      const pid = it.public_id;
      this.saveBusy = { ...this.saveBusy, [pid]: true };
      try {
        if (!it.is_saved) {
          const r = await app.api(`/api/users/me/saved/listings/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_public_id: pid })
          });
          if (r.status === 401 || r.status === 403) { app.requireAuth(location.pathname + location.search); return; }
          if (!r.ok) { const j = await r.json().catch(()=>({})); throw new Error(j?.detail || 'Nie udało się zapisać.'); }
          it.is_saved = true;
          app.ok('Dodano do zapisanych.');
          window.dispatchEvent(new CustomEvent('saved:changed', { detail: { op:'add', item_public_id: pid }}));
        } else {
          const r = await app.api(`/api/users/me/saved/listings/${encodeURIComponent(pid)}/`, { method: 'DELETE' });
          if (r.status === 401 || r.status === 403) { app.requireAuth(location.pathname + location.search); return; }
          if (!r.ok) { const j = await r.json().catch(()=>({})); throw new Error(j?.detail || 'Nie udało się usunąć.'); }
          it.is_saved = false;
          app.ok('Usunięto z zapisanych.');
          window.dispatchEvent(new CustomEvent('saved:changed', { detail: { op:'remove', item_public_id: pid }}));
        }
      } catch (e) {
        app.error(e?.message || 'Błąd.');
      } finally {
        this.saveBusy = { ...this.saveBusy, [pid]: false };
      }
    },

    saveCurrentSearch: async function () {
      if (this.saveSearchBusy) return;

      const phrase = window.prompt('Opcjonalna nazwa wyszukiwania:', this.q || '');
      if (phrase === null) return;

      this.saveSearchBusy = true;
      try {
        const body = {
          category_path: this.typePath || '',
          query_string: this._qs(),
          search_phrase: phrase
        };
        const r = await app.api(`/api/users/me/saved/searches/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        if (r.status === 401 || r.status === 403) { app.requireAuth(location.pathname + location.search); return; }
        if (!r.ok) { const j = await r.json().catch(()=>({})); throw new Error(j?.detail || 'Nie udało się zapisać wyszukiwania.'); }
        app.ok('Zapisano wyszukiwanie.');
      } catch (e) {
        app.error(e?.message || 'Błąd.');
      } finally {
        this.saveSearchBusy = false;
      }
    },


    resetAll() {
      this.q = '';
      this.ordering = '-created_at';
      this.source = 'ALL';
      this.listing_type = 'ANY';
      this.condition = 'ANY';
      this.allow_checkout_only = false;
      this.price_min = '';
      this.price_max = '';
      this.clearCategory();
    },
  };
};
