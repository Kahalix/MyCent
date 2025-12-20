// static/js/home/landing.js
window.app = window.app || {};

app.landing = function () {
  return {
    latest: { loading: true, items: [] },
    buy:    { loading: true, items: [] },
    staff:  { loading: true, items: [] },
    user:   { loading: true, items: [] },
    cats:   { loading: true, items: [] },

    async init(){
      // lekkie feedy – tylko próbki; pełna paginacja jest na /offers
      this._loadFeed(this.latest, '/api/public/item-sets/?ordering=-created_at');
      this._loadFeed(this.buy,    '/api/public/item-sets/?allow_online_checkout=true&ordering=-created_at');
      this._loadFeed(this.staff,  '/api/public/item-sets/?added_by=STAFF&ordering=-created_at');
      this._loadFeed(this.user,   '/api/public/item-sets/?added_by=USER&ordering=-created_at');

      // Kategorie (Top 6) + liczność — korzystamy z DRF .count (paginacja)
      await this._buildCategories();
    },

    async _loadFeed(slot, url){
      slot.loading = true;
      try{
        const r = await app.api(url, { method:'GET' });
        const j = await r.json().catch(()=> ({}));
        const arr = Array.isArray(j) ? j : (j.results || []);
        slot.items = Array.isArray(arr) ? arr : [];
      } catch { slot.items = []; }
      finally { slot.loading = false; }
    },

    async _buildCategories(){
      this.cats.loading = true;
      try{
        const r = await app.api('/api/public/item-sets/?ordering=-created_at', { method:'GET' });
        const j = await r.json().catch(()=> ({}));
        const pool = Array.isArray(j) ? j : (j.results || []);
        this.cats.items = this._deriveCategories(pool).slice(0, 6);
        await this._hydrateCategoryCounts();
      } catch {
        this.cats.items = [];
      } finally {
        this.cats.loading = false;
      }
    },

    _deriveCategories(items){
      const map = new Map();
      for (const it of items) {
        const path = it?.type?.path || '';
        if (!path) continue;
        const name = path.split('/').slice(-1)[0] || path;
        const img = this.img(it);
        if (!map.has(path)){
          map.set(path, {
            path, name, img,
            count: null,
            href: this.offersLink({ type_path: path })
          });
        }
      }
      return Array.from(map.values());
    },

    async _hydrateCategoryCounts(){
      // POBIERAMY .count z DRF (globalna liczba rekordów), fallback na length gdyby endpoint był „gołą listą”
      const top = this.cats.items.slice(0, 6);
      await Promise.all(top.map(async (c, idx) => {
        try{
          const ru = `/api/public/item-sets/?type_path=${encodeURIComponent(c.path)}`;
          const r = await app.api(ru, { method:'GET' });
          const j = await r.json().catch(()=> ({}));
          const total = Array.isArray(j) ? (j.length ?? null) : (typeof j.count === 'number' ? j.count : null);
          this.cats.items[idx] = { ...c, count: total };
        } catch {}
      }));
    },

    // === helpers ===
    img(it){
      const first = (Array.isArray(it.images) && it.images.length) ? it.images[0] : null;
      const pic = it.cover_image_url
        || first?.image_path || first?.url || first?.image_url
        || it.catalog_item?.image_path || '';
      return app.imgUrl ? app.imgUrl(pic) : (pic || 'https://placehold.co/600x600?text=%20');
    },
    money(it){ return app.moneyText(it?.price || null); },
    itemUrl(it){
      const slug = it?.slug || it?.public_id || '';
      return slug ? `/i/${slug}` : '/offers';
    },
    offersLink(q){
      const p = new URLSearchParams();
      if (q.type_path)     p.set('type_path', q.type_path);
      if (q.added_by)      p.set('added_by', q.added_by);
      if (q.listing_type)  p.set('listing_type', q.listing_type);
      p.set('ordering', q.ordering || '-created_at');
      return `/offers?${p.toString()}`;
    },
  };
};
