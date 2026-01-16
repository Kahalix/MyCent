window.app = window.app || {};

/* ---- Fallbacki core + toasty -- */
app._emitToast = app._emitToast || function (type, message) {
  const detail = { type, message };
  try { window.dispatchEvent(new CustomEvent('toast', { detail })); } catch {}
  try { window.dispatchEvent(new CustomEvent('toast:show', { detail })); } catch {}
};
app.ok    = app.ok    || (m => app._emitToast('success', m));
app.error = app.error || (m => app._emitToast('error', m));

app.api = app.api || ((url, opts = {}) =>
  fetch(url, { credentials: 'include', ...opts }));

app.imgUrl = app.imgUrl || (p => p || 'https://placehold.co/600x600?text=%20');
app.moneyText = app.moneyText || (v => {
  if (v == null || v === '') return '—';
  if (typeof v === 'object') {
    const a = v.amount ?? '';
    const c = v.currency || 'PLN';
    return (a !== '' ? a : '—') + ' ' + c;
  }
  return `${v} PLN`;
});
app.goto = app.goto || (u => { location.href = u; });
app.requireAuth = app.requireAuth || (ret =>
  app.goto(`/login?next=${encodeURIComponent(ret || location.pathname + location.search)}`));

/* -- Canvasowe miniatury ---- */
app._paintThumb = app._paintThumb || function (canvas, src) {
  if (!canvas) return;
  const dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
  const cssW = canvas.clientWidth || 72;
  const cssH = canvas.clientHeight || 72;
  canvas.width  = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);

  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.fillStyle = '#e5e7eb';
  ctx.fillRect(0,0,canvas.width, canvas.height);

  const img = new Image();
  img.crossOrigin = 'anonymous';
  img.decoding = 'async';
  img.onload = () => {
    const cw = canvas.width, ch = canvas.height;
    const iw = img.naturalWidth || img.width;
    const ih = img.naturalHeight || img.height;
    if (!iw || !ih) return;

    const scale = Math.max(cw / iw, ch / ih);
    const sw = iw * scale, sh = ih * scale;
    const dx = (cw - sw) / 2;
    const dy = (ch - sh) / 2;

    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(img, dx, dy, sw, sh);
  };
  img.onerror = () => {
    const cw = canvas.width, ch = canvas.height;
    ctx.fillStyle = '#f3f4f6';
    ctx.fillRect(0,0,cw,ch);
    ctx.fillStyle = '#9ca3af';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = `${Math.floor(Math.min(cw,ch)/5)}px system-ui, sans-serif`;
    ctx.fillText('—', cw/2, ch/2);
  };
  img.src = app.imgUrl(src);
};

/* -- Detal ogłoszenia ---- */
app.itemDetailPage = function (opts = {}) {
  const COND_PL = { NEW:'Nowy', USED:'Używany', DAMAGED:'Uszkodzony' };
  const TYPE_PL = { LISTING:'Ogłoszenie', EXCHANGE:'Wymiana', BUY:'Sprzedaż' };

  return {
    slug: (opts.slug || '').trim(),
    item: null,
    ui: {},

    loading: false,
    err: '',
    ok: '',
    isSaved: false,

    // galeria
    curIdx: 0,
    lightboxOpen: false,
    lbIdx: 0,

    // koszyk
    qty: 1,
    addBusy: false,

    // czat / zapis
    chatBusy: false,
    saveBusy: false,

    async init() { this.load(); },

    async _loadUiForPath(typePath){
      if (!typePath) { this.ui = {}; return; }
      try{
        const r = await app.api(`/api/public/catalog/categories/schema/by-path/${encodeURIComponent(typePath)}`, { method:'GET' });
        const j = await r.json().catch(()=>({}));
        this.ui = j?.ui_schema || {};
      } catch { this.ui = {}; }
    },

    async load() {
      this.loading = true; this.err = ''; this.item = null; this.curIdx = 0; this.lightboxOpen = false;
      try {
        const r = await app.api(`/api/public/item-sets/by-slug/${encodeURIComponent(this.slug)}`, { method: 'GET' });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) { this.err = j?.detail || 'Nie znaleziono ogłoszenia.'; return; }
        this.item = j;
        this.isSaved = !!j.is_saved;

        // UI-schema do ładnych etykiet
        await this._loadUiForPath(this.item?.type?.path || '');
      } catch {
        this.err = 'Błąd sieci.';
      } finally {
        this.loading = false;
      }
    },

    // tylko zdjęcia z ogłoszenia użytkownika/sprzedawcy: bez obrazka katalogowego
    imgs() {
      if (!this.item) return [];
      const list = Array.isArray(this.item.images) ? this.item.images : [];
      return list
        .map(i => i.image_path || i.image || i.url || i.image_url || i.path)
        .filter(Boolean);
    },

    setIdx(i) {
      const n = this.imgs().length;
      this.curIdx = Math.max(0, Math.min(i, n ? n - 1 : 0));
    },

    openLightbox(i = null) {
      const arr = this.imgs();
      if (!arr.length) return;
      this.lbIdx = (i == null) ? this.curIdx : Math.max(0, Math.min(i, arr.length - 1));
      this.lightboxOpen = true;
    },
    closeLightbox(){ this.lightboxOpen = false; },
    lbNext(){ const n = this.imgs().length; if (n) this.lbIdx = (this.lbIdx + 1) % n; },
    lbPrev(){ const n = this.imgs().length; if (n) this.lbIdx = (this.lbIdx - 1 + n) % n; },

    priceText() { return app.moneyText(this.item?.price); },
    condText(){ return COND_PL[this.item?.condition] || (this.item?.condition || ''); },
    typeText(){ return TYPE_PL[this.item?.listing_type] || (this.item?.listing_type || ''); },

    dimsText(){
      const L = this.item?.length_cm, W = this.item?.width_cm, H = this.item?.height_cm;
      if (L || W || H) return `${L ?? '—'} × ${W ?? '—'} × ${H ?? '—'} cm`;
      return '';
    },
    weightText(){
      const w = this.item?.weight_kg;
      return (w || w === 0) ? `${w} kg` : '';
    },

    // Polskie pary: [Stan] [Wymiary] [Masa] + atrybuty z ui_schema
    attrPairs(){
      const out = [];
      const c = this.condText(); if (c) out.push(['Stan', c]);
      const d = this.dimsText(); if (d) out.push(['Wymiary', d]);
      const w = this.weightText(); if (w) out.push(['Masa', w]);

      const attrs = this.item?.attributes || {};
      const pairs = app.attrPairs(attrs, this.ui);
      return out.concat(pairs);
    },

    // zakup online
    canBuy() {
      const it = this.item || {};
      return it.status === 'AVAILABLE'
        && it.added_by === 'STAFF'
        && it.listing_type === 'BUY'
        && !!it.allow_online_checkout;
    },

    // akcje
    gotoCategory() {
      const p = this.item?.type?.path;
      if (!p) return;
      app.goto(`/offers?cat=${encodeURIComponent(p)}`);
    },
    gotoSeller() {
      const slug = this.item?.seller_slug;
      if (!slug) return;
      app.goto(`/shop/${encodeURIComponent(slug)}`);
    },
    gotoOwner() {
      const id = this.item?.owner?.public_id;
      if (!id) return;
      app.goto(`/u/${encodeURIComponent(id)}`);
    },

    async startChat() {
      if (!this.item) return;
      this.chatBusy = true; this.err = ''; this.ok = '';
      try {
        const r = await app.api(`/api/users/me/chats/threads/start/`, {
          method: 'POST',
          headers: { 'Content-Type':'application/json' },
          body: JSON.stringify({ item_public_id: this.item.public_id })
        });
        const j = await r.json().catch(() => ({}));
        if (r.status === 401 || r.status === 403) { app.requireAuth(location.pathname + location.search); return; }
        if (!r.ok) { const msg = j?.detail || 'Nie udało się rozpocząć czatu.'; this.err = msg; app.error(msg); return; }
        this.ok = 'Czat rozpoczęty.'; app.ok(this.ok);
        if (j?.public_id) app.goto(`/chat/t/${j.public_id}`);
      } catch (e) {
        this.err = e?.message || 'Błąd.'; app.error(this.err);
      } finally { this.chatBusy = false; }
    },

    async addToCart() {
      if (!this.item || !this.canBuy()) return;
      const qty = Math.max(1, parseInt(this.qty || 1, 10));
      this.addBusy = true; this.err = ''; this.ok = '';
      try {
        const r = await app.api(`/api/users/me/cart/items/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ item_public_id: this.item.public_id, quantity: qty })
        });
        const j = await r.json().catch(() => ({}));
        if (r.status === 401 || r.status === 403) { app.requireAuth(location.pathname + location.search); return; }
        if (!r.ok) { this.err = (j?.detail || 'Nie udało się dodać do koszyka.'); app.error(this.err); return; }
        this.ok = 'Dodano do koszyka.'; app.ok(this.ok);
        window.dispatchEvent(new CustomEvent('cart:changed', { detail: { source: 'item-detail' }}));
      } catch (e) {
        this.err = e?.message || 'Błąd.'; app.error(this.err);
      } finally { this.addBusy = false; }
    },

    async toggleSave() {
      if (!this.item || this.saveBusy) return;
      this.saveBusy = true;
      try {
        if (!this.isSaved) {
          const r = await app.api(`/api/users/me/saved/listings/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_public_id: this.item.public_id })
          });
          if (r.status === 401 || r.status === 403) { app.requireAuth(location.pathname + location.search); return; }
          if (!r.ok) { const j = await r.json().catch(()=>({})); throw new Error(j?.detail || 'Nie udało się zapisać.'); }
          this.isSaved = true; app.ok('Dodano do zapisanych.');
          window.dispatchEvent(new CustomEvent('saved:changed', { detail: { op: 'add', item_public_id: this.item.public_id }}));
        } else {
          const r = await app.api(`/api/users/me/saved/listings/${encodeURIComponent(this.item.public_id)}/`, { method: 'DELETE' });
          if (r.status === 401 || r.status === 403) { app.requireAuth(location.pathname + location.search); return; }
          if (!r.ok) { const j = await r.json().catch(()=>({})); throw new Error(j?.detail || 'Nie udało się usunąć.'); }
          this.isSaved = false; app.ok('Usunięto z zapisanych.');
          window.dispatchEvent(new CustomEvent('saved:changed', { detail: { op: 'remove', item_public_id: this.item.public_id }}));
        }
      } catch (e) {
        app.error(e?.message || 'Błąd.');
      } finally {
        this.saveBusy = false;
      }
    },
  };
};
