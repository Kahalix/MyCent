window.app = window.app || {};

app.savedCenterPage = function () {
  return {
    tab: 'items',
    items: [],
    searches: [],
    loadingItems: false,
    loadingSearches: false,
    err: '',
    busy: false,

    async init() {
      await Promise.all([this.loadItems(), this.loadSearches()]);
    },
    setTab(t) { this.tab = t; },

    async loadItems() {
      this.loadingItems = true;
      try {
        const r = await app.api('/api/users/me/saved/listings', { method: 'GET' });
        const j = await r.json().catch(()=>({}));
        if (!r.ok) { this.err = j?.detail || 'Błąd pobierania zapisanych przedmiotów.'; return; }
        this.items = Array.isArray(j?.results) ? j.results : (Array.isArray(j) ? j : []);
      } catch { this.err = 'Błąd sieci.'; }
      finally { this.loadingItems = false; }
    },

    async loadSearches() {
      this.loadingSearches = true;
      try {
        const r = await app.api('/api/users/me/saved/searches', { method: 'GET' });
        const j = await r.json().catch(()=>({}));
        if (!r.ok) { this.err = j?.detail || 'Błąd pobierania zapisanych wyszukiwań.'; return; }
        this.searches = Array.isArray(j?.results) ? j.results : (Array.isArray(j) ? j : []);
      } catch { this.err = 'Błąd sieci.'; }
      finally { this.loadingSearches = false; }
    },

    async removeSavedItem(rec) {
      if (!rec?.item?.public_id) return;
      this.busy = true;
      try {
        const r = await app.api(`/api/users/me/saved/listings/${encodeURIComponent(rec.item.public_id)}/`, { method: 'DELETE' });
        if (!r.ok) return;
        this.items = this.items.filter(x => x.item?.public_id !== rec.item.public_id);
        app.ok('Usunięto z zapisanych.');
      } finally { this.busy = false; }
    },

    async deleteSearch(s) {
      if (!s?.public_id) return;
      this.busy = true;
      try {
        const r = await app.api(`/api/users/me/saved/searches/${encodeURIComponent(s.public_id)}/`, { method: 'DELETE' });
        if (!r.ok) return;
        this.searches = this.searches.filter(x => x.public_id !== s.public_id);
        app.ok('Usunięto zapisane wyszukiwanie.');
      } finally { this.busy = false; }
    },

    openResults(s) {
      if (!s?.public_id) return;
      app.goto(`/saved/searches/${encodeURIComponent(s.public_id)}`);
    },

    // helpers
    img(it) {
      const first = (Array.isArray(it?.images) && it.images.length) ? it.images[0] : null;
      const pic = it?.cover_image_url
        || first?.image_path || first?.url || first?.image_url
        || it?.catalog_item?.image_path || '';
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
    gotoItem(it) {
      const slug = it?.slug || (it?.public_id || '');
      if (slug) app.goto(`/i/${slug}`);
    },

    parseQS(str) {
    try { return new URLSearchParams((str || '').replace(/^\?/, '')); }
    catch { return new URLSearchParams(); }
  },
  chipsFor(s) {
    const p = this.parseQS(s?.query_string || '');
    const out = [];

    const ORDER = {
      '-created_at': 'Najnowsze',
      'created_at':  'Najstarsze',
      '-price':      'Cena ⬇︎',
      'price':       'Cena ⬆︎',
    };
    const LISTING = { 'BUY':'Kup teraz', 'LISTING':'Ogłoszenie', 'EXCHANGE':'Wymiana' };
    const COND    = { 'NEW':'Nowy', 'USED':'Używany', 'DAMAGED':'Uszkodzony' };
    const SOURCE  = { 'STAFF':'sprzedawcy', 'USER':'użytkownicy' };

    // fraza
    const search = (p.get('search') || '').trim();
    if (search) out.push(`Fraza: “${search}”`);

    // kategoria
    const typePath = (p.get('type_path') || '').trim();
    if (typePath) out.push(`Kategoria: ${typePath}`);

    // typ ogłoszenia
    const lt = (p.get('listing_type') || '').toUpperCase();
    if (LISTING[lt]) out.push(`Typ: ${LISTING[lt]}`);

    // źródło
    const src = (p.get('added_by') || '').toUpperCase();
    if (SOURCE[src]) out.push(`Źródło: ${SOURCE[src]}`);

    // stan
    const cond = (p.get('condition') || '').toUpperCase();
    if (COND[cond]) out.push(`Stan: ${COND[cond]}`);

    // online checkout
    if ((p.get('allow_online_checkout') || '').toLowerCase() === 'true') {
      out.push('Tylko z zakupem online');
    }

    // cena
    const pmin = (p.get('price_min') || '').trim();
    const pmax = (p.get('price_max') || '').trim();
    if (pmin && pmax) out.push(`Cena: ${pmin}–${pmax} PLN`);
    else if (pmin)    out.push(`Cena od: ${pmin} PLN`);
    else if (pmax)    out.push(`Cena do: ${pmax} PLN`);

    // sprzedawca / właściciel (opcjonalnie)
    const seller = (p.get('seller_slug') || '').trim();
    if (seller) out.push(`Sprzedawca: ${seller}`);
    const owner = (p.get('owner_public_id') || '').trim();
    if (owner) out.push(`Właściciel: ${owner}`);

    // sortowanie
    const ord = p.get('ordering') || '';
    if (ORDER[ord]) out.push(`Sort: ${ORDER[ord]}`);

    // wszystko, czego nie rozpoznaliśmy - dorzućmy jako param=value
    const known = new Set([
      'search','type_path','listing_type','added_by','condition','allow_online_checkout',
      'price_min','price_max','seller_slug','owner_public_id','ordering'
    ]);
    for (const [k, v] of p.entries()) {
      if (!known.has(k) && v) out.push(`${k}: ${v}`);
    }

    return out;
  },
  };
};
