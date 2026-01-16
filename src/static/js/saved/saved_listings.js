// window.app = window.app || {};
//
// app.savedListingsPage = function () {
//   return {
//     items: [],
//     next: null,
//     loading: false,
//     err: '',
//
//     async init() { await this.load(); },
//
//     async load(url) {
//       this.loading = true; this.err = '';
//       try {
//         const u = url || '/api/users/me/saved/listings';
//         const r = await app.api(u, { method: 'GET' });
//         if (r.status === 401 || r.status === 403) { app.requireAuth('/saved'); return; }
//         const j = await r.json().catch(()=>({}));
//         const results = Array.isArray(j.results) ? j.results : (Array.isArray(j) ? j : []);
//         this.items = url ? (this.items.concat(results)) : results;
//         this.next = j.next || null;
//       } catch (e) {
//         this.err = e?.message || 'Błąd ładowania.';
//       } finally { this.loading = false; }
//     },
//
//     async loadMore(){ if (this.next && !this.loading) await this.load(this.next); },
//
//     async unsave(item_public_id) {
//       try{
//         const r = await app.api(`/api/users/me/saved/listings/${encodeURIComponent(item_public_id)}`, { method: 'DELETE' });
//         if (r.status === 401 || r.status === 403) { app.requireAuth('/saved'); return; }
//         if (!r.ok) { app.error('Nie udało się usunąć.'); return; }
//         this.items = this.items.filter(x => x.item?.public_id !== item_public_id);
//         app.ok('Usunięto z zapisanych.');
//         window.dispatchEvent(new CustomEvent('saved:changed', { detail:{ op:'remove', item_public_id }}));
//       } catch(e){ app.error(e?.message || 'Błąd.'); }
//     },
//
//     img(u){ return app.imgUrl ? app.imgUrl(u) : (u || 'https://placehold.co/320x240?text=%20'); },
//     priceText(v){ return app.moneyText ? app.moneyText(v) : '—'; },
//     gotoItem(slug){ app.goto(`/i/${encodeURIComponent(slug)}`); },
//   };
// };
