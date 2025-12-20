// static/js/pawns/user_detail.js
window.app = window.app || {};
// fallback, gdyby nie było globalnie
app.getSchemaCached = app.getSchemaCached || (async () => ({ schema:{}, ui_schema:{} }));

app.userPawnDetail = function (publicId) {
  return {
    loading:false, err:'', pawn:null,
    extending:false,

    // UI-schema cache + nonce dla pigułek atrybutów
    _uiByPath: Object.create(null),
    uiNonce: 0,

    async init(){ await this.reload(); },

    async reload(){
      this.loading = true; this.err='';
      try{
        const r = await app.api(`/api/users/me/pawns/${publicId}/`, { method:'GET' });
        if (!r.ok){ this.err = 'Nie znaleziono zastawu.'; return; }
        this.pawn = await r.json();

        // Prefetch UI schema dla type_path z linii
        const paths = new Set((this.pawn?.lines || []).map(ln => ln?.item_snapshot?.type_path).filter(Boolean));
        for (const p of paths) this._ensureUiSchema(p).catch(()=>{});
      } catch(e){ this.err = e?.message || 'Błąd'; }
      finally { this.loading = false; }
    },

    get active(){ return !!this.pawn?.is_active; },
    get expired(){
      if (!this.pawn?.due_date) return false;
      try { return new Date(this.pawn.due_date) < new Date().setHours(0,0,0,0); } catch { return false; }
    },

    async startExtension(days){
      if (!this.active) return;
      this.extending = true; this.err='';
      try{
        const r = await app.api(`/api/users/me/pawns/${this.pawn.public_id}/extend-intent/`, {
          method:'POST', body: JSON.stringify({ days })
        });
        if (!r.ok){ return app.toast.fromResponse?.(r, 'Nie udało się zainicjować przedłużenia.'); }
        const j = await r.json();
        const txid = j.public_id;
        if (!txid){ app.error?.('Brak transaction_public_id.'); return; }
        app.ok?.('Przedłużenie utworzone – przejdź do płatności.');
        app.goto?.(`/pay/${txid}`);
      } catch(e){ app.error?.(e?.message || 'Błąd'); }
      finally { this.extending=false; }
    },

    // ==== ATRYBUTY ====
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

    attrPairsFor(ln){
      try{
        const attrs = (ln?.item_snapshot?.attributes || ln?.item_snapshot?.attrs || ln?.item_snapshot?.properties || {});
        if (!attrs || !Object.keys(attrs).length) return [];
        const path = ln?.item_snapshot?.type_path || '';
        const ui = path ? (this._uiByPath[path] || {}) : {};
        if (path && !this._uiByPath[path]) this._ensureUiSchema(path).catch(()=>{});
        return app.attrPairs ? app.attrPairs(attrs, ui) : Object.entries(attrs);
      } catch { return []; }
    },
  }
};
