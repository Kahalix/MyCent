// window.app = window.app || {};
// app.savedPage = function() {
//   return {
//     loading: true,
//     err: '',
//     listings: [],
//     searches: [],
//     resultsMap: new Map(), // search_public_id -> items[]
//
//     async init() {
//       this.loading = true; this.err=''; this.listings=[]; this.searches=[];
//       try {
//         await Promise.all([this.fetchListings(), this.fetchSearches()]);
//       } catch (e) {
//         this.err = 'Błąd ładowania zapisanych.';
//       } finally {
//         this.loading = false;
//       }
//     },
//
//     async fetchListings() {
//       const r = await app.api('/api/users/me/saved/listings?page_size=200');
//       if (!r.ok) return;
//       const j = await r.json().catch(()=>({}));
//       this.listings = Array.isArray(j) ? j : (j.results || []);
//     },
//     async fetchSearches() {
//       const r = await app.api('/api/users/me/saved/searches?page_size=200');
//       if (!r.ok) return;
//       const j = await r.json().catch(()=>({}));
//       this.searches = Array.isArray(j) ? j : (j.results || []);
//     },
//
//     priceText: (it) => {
//       const p = it?.price;
//       if (!p) return '—';
//       if (typeof p === 'object') return `${p.amount ?? '—'} ${p.currency || 'PLN'}`;
//       return `${p} PLN`;
//     },
//
//     async removeListing(pid) {
//       try {
//         const r = await app.api(`/api/users/me/saved/listings/${encodeURIComponent(pid)}`, { method:'DELETE' });
//         if (r.status === 401 || r.status === 403) { app.requireAuth('/saved'); return; }
//         if (!r.ok) throw new Error('Nie udało się usunąć.');
//         this.listings = this.listings.filter(x => (x.item?.public_id || x.item?.id) !== pid);
//         app.ok('Usunięto z zapisanych.');
//         window.dispatchEvent(new CustomEvent('saved:changed', { detail: { op:'remove', item_public_id: pid }}));
//       } catch (e) {
//         app.error(e?.message || 'Błąd.');
//       }
//     },
//
//     async deleteSearch(spid) {
//       try {
//         const r = await app.api(`/api/users/me/saved/searches/${encodeURIComponent(spid)}`, { method:'DELETE' });
//         if (!r.ok) throw new Error('Nie udało się usunąć wyszukiwania.');
//         this.searches = this.searches.filter(s => s.public_id !== spid);
//         this.resultsMap.delete(spid);
//         app.ok('Usunięto zapisane wyszukiwanie.');
//       } catch (e) { app.error(e?.message || 'Błąd.'); }
//     },
//
//     async refreshSearch(spid) {
//       try {
//         const r = await app.api(`/api/users/me/saved/searches/${encodeURIComponent(spid)}/refresh/`, {
//           method:'POST', headers:{'Content-Type':'application/json'},
//           body: JSON.stringify({ limit: 200 })
//         });
//         if (!r.ok) throw new Error('Nie udało się odświeżyć.');
//         app.ok('Odświeżono wyniki.');
//       } catch (e) { app.error(e?.message || 'Błąd.'); }
//     },
//
//     async loadResults(spid) {
//       try {
//         const r = await app.api(`/api/users/me/saved/searches/${encodeURIComponent(spid)}/results`);
//         if (!r.ok) throw new Error('Nie udało się pobrać wyników.');
//         const items = await r.json().catch(()=>[]);
//         this.resultsMap.set(spid, items || []);
//       } catch (e) { app.error(e?.message || 'Błąd.'); }
//     },
//
//     gotoItemBySlug(slugOrId) {
//       if (slugOrId) app.goto(`/i/${encodeURIComponent(slugOrId)}`);
//     },
//     img(it){
//       const first = (Array.isArray(it.images) && it.images.length) ? it.images[0] : null;
//       const pic = it.cover_image_url
//         || first?.image_path || first?.url || first?.image_url
//         || it.catalog_item?.image_path || '';
//       return app.imgUrl ? app.imgUrl(pic) : pic;
//     },
//   }
// };
