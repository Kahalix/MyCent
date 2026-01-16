window.app = window.app || {};
app.getSchemaCached = app.getSchemaCached || (async () => ({ schema:{}, ui_schema:{} }));

app.sellerPawnDetail = function (publicId) {
  return {
    loading:false, err:'', pawn:null,
    busy:false, extendDays: 30,

    // UI-schema cache + nonce do re-renderu pigułek
    _uiByPath: Object.create(null),
    uiNonce: 0,

    // --- klient
    custForm:{
      first_name:'', last_name:'', email:'', phone:'',
      address:{ line1:'', line2:'', postal_code:'', city:'', country:'' },
      document_type:'', document_number:'', birth_date:''
    },
    ensureInfo:'',
    custSearch:{ q:'', results:[], loading:false },

    async init(){ await this.reload(); },

    createListingFromPawn: true,

    async reload(){
      this.loading = true; this.err='';
      try{
        const r = await app.api(`/api/sellers/mine/pawns/${publicId}/`, { method:'GET' });
        if (!r.ok){ this.err='Nie znaleziono'; return; }
        this.pawn = await r.json();

        if (this.pawn?.forfeited_item) this.createListingFromPawn = false;

        // zasiej formularz klienta ze snapshotu
        const s = this.pawn?.customer_snapshot || {};
        const addr = s.address || {};
        this.custForm = {
          first_name: s.first_name || '',
          last_name:  s.last_name  || '',
          email:      s.email      || '',
          phone:      s.phone      || '',
          address: {
            line1: addr.line1 || '',
            line2: addr.line2 || '',
            postal_code: addr.postal_code || '',
            city: addr.city || '',
            country: addr.country || ''
          },
          document_type:  (s.document?.type || ''),
          document_number:(s.document?.number || ''),
          birth_date:     (s.birth_date || '')
        };

        // Prefetch UI schema dla wszystkich type_path w liniach
        const paths = new Set((this.pawn?.lines || [])
          .map(ln => ln?.item_snapshot?.type_path)
          .filter(Boolean));
        for (const p of paths) this._ensureUiSchema(p).catch(()=>{});
      } catch(e){ this.err=e?.message||'Błąd'; }
      finally { this.loading=false; }
    },

    get active(){ return !!this.pawn?.is_active; },

    async extendOffline(days){
      if (!this.active) return;
      this.busy = true;
      try{
        const r = await app.api(`/api/sellers/mine/pawns/${this.pawn.public_id}/extend/`, {
          method:'POST', body: JSON.stringify({ days })
        });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok){ app.error(app.errText?.(j) || 'Nie udało się przedłużyć.'); return; }
        app.ok('Przedłużono zastaw (offline).');
        this.pawn = j;
      } catch(e){ app.error(e?.message || 'Błąd'); }
      finally { this.busy = false; }
    },

    async redeem(){
      this.busy = true;
      try{
        const r = await app.api(`/api/sellers/mine/pawns/${this.pawn.public_id}/redeem/`, { method:'POST' });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok){ app.error(app.errText?.(j) || 'Nie udało się wykupić.'); return; }
        app.ok('Zastaw oznaczono jako wykupiony.');
        this.pawn = j;
      } catch(e){ app.error(e?.message || 'Błąd'); }
      finally { this.busy = false; }
    },

    async forfeit(){
      if (!confirm('Oznaczyć jako niewykupiony?')) return;
      this.busy = true;
      try{
        const create_listing = (!!this.createListingFromPawn) && (!this.pawn?.forfeited_item);

        const r = await app.api(`/api/sellers/mine/pawns/${this.pawn.public_id}/forfeit/`, {
          method:'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ create_listing })
        });

        const j = await r.json().catch(()=> ({}));
        if (!r.ok){ app.error(app.errText?.(j) || 'Nie udało się oznaczyć jako niewykupiony.'); return; }
        app.ok('Zastaw oznaczony jako niewykupiony.');
        this.pawn = j;

        if (this.pawn?.forfeited_item) this.createListingFromPawn = false;
      } catch(e){ app.error(e?.message || 'Błąd'); }
      finally { this.busy = false; }
    },

    // ---- eksport (PDF/CSV) ----
    async downloadReceipt(kind){
      try{
        const url = `/api/sellers/mine/pawns/${this.pawn.public_id}/receipt.${kind}`;
        const r = await app.api(url, { method:'GET' });
        if (!r.ok){
          let msg = 'Nie udało się wygenerować pliku.';
          try { const j = await r.json(); msg = app.errText?.(j) || j?.detail || msg; } catch {}
          app.error(msg);
          return;
        }
        const blob = await r.blob();
        const cd = r.headers.get('Content-Disposition') || '';
        const fallback = `pawn_${this.pawn.public_id}.${kind}`;
        const filename = this._filenameFromDisposition(cd) || fallback;

        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 0);
        app.ok('Pobrano plik.');
      } catch(e){
        app.error(e?.message || 'Błąd pobierania pliku.');
      }
    },

    _filenameFromDisposition(cd){
      try{
        const star = cd.match(/filename\*\s*=\s*([^']*)''([^;]+)/i);
        if (star && star[2]) return decodeURIComponent(star[2]);
        const norm = cd.match(/filename\s*=\s*"([^"]+)"/i) || cd.match(/filename\s*=\s*([^;]+)/i);
        if (norm && norm[1]) return norm[1].trim();
      } catch {}
      return null;
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

    // ==== AKCJE KLIENTA ====
    async searchCustomers(){
      this.custSearch.loading=true; this.custSearch.results=[];
      try{
        const qs = [];
        const qq = (this.custSearch.q||'').trim(); if (qq) qs.push(`q=${encodeURIComponent(qq)}`);
        const url = `/api/sellers/mine/customers/?${qs.join('&')}`;
        const r = await app.api(url,{method:'GET'});
        const j = await r.json().catch(()=> ({}));
        this.custSearch.results = j.results ?? (Array.isArray(j)? j : []);
      } finally { this.custSearch.loading=false; }
    },

    async attachCustomer(publicId){
      try{
        const r = await app.api(`/api/sellers/mine/pawns/${this.pawn.public_id}/attach-customer/`, {
          method:'POST', body: JSON.stringify({ customer_public_id: publicId })
        });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok) throw new Error(app.errText?.(j) || 'Nie udało się połączyć klienta.');
        this.ensureInfo = 'Połączono klienta.';
        await this._reloadPawn();
      } catch(e){ app.error(e?.message || 'Błąd'); }
    },

    async ensureCustomer(){
      this.ensureInfo = 'Sprawdzam…';
      try{
        const r = await app.api(`/api/sellers/mine/pawns/${this.pawn.public_id}/ensure-customer/`, {
          method:'POST', body: JSON.stringify(this.custForm)
        });
        const j = await r.json().catch(()=> ({}));
        if (r.status === 409) {
          this.ensureInfo = j?.detail || 'Znaleziono wielu kandydatów — wybierz z listy poniżej.';
          this.custSearch.results = (j?.candidates || []);
          return;
        }
        if (!r.ok) throw new Error(app.errText?.(j) || 'Nie udało się utworzyć/powiązać klienta.');
        this.ensureInfo = (j?.result === 'created') ? 'Utworzono i połączono nowego klienta.' : 'Połączono istniejącego klienta.';
        await this._reloadPawn();
      } catch(e){ this.ensureInfo=''; app.error(e?.message || 'Błąd'); }
    },

    async detachCustomer(){
      try{
        const r = await app.api(`/api/sellers/mine/pawns/${this.pawn.public_id}/detach-customer/`, { method:'POST' });
        if (!r.ok){ const j=await r.json().catch(()=>({})); throw new Error(app.errText?.(j)||'Nie udało się odłączyć.'); }
        this.ensureInfo = 'Odłączono klienta.';
        await this._reloadPawn();
      } catch(e){ app.error(e?.message || 'Błąd'); }
    },

    async _reloadPawn(){
      const r = await app.api(`/api/sellers/mine/pawns/${this.pawn.public_id}/`, { method:'GET' });
      if (r.ok) this.pawn = await r.json();
    }
  }
};
