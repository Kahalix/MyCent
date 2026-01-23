window.app = window.app || {};

app.buyerOrderDetail = function (orderPublicId) {
  return {
    loading: false,
    err: '',
    order: null,

    optionsByLine: {},
    shippingByLine: {},
    selectedShipByLine: {},
    lineBusy: {},
    expanded: {},

    _uiByPath: Object.create(null),
    uiNonce: 0,

    orderAddress: {
      first_name: '', last_name: '', phone_number: '', email: '',
      street: '', house_number: '', city: '', state: '', postal_code: '', country: ''
    },
    addrErr: { first_name:'', last_name:'', phone_number:'', email:'', street:'', house_number:'', city:'', state:'', postal_code:'', country:'' },
    savingAddr: false,
    addrMsg: '',
    payBusy: false,

    async init() {
      this.loading = true;
      this.err = '';
      try {
        await this._loadOrder();
        this._indexShippings();
        await this._loadOptionsForLines();
        this._hydrateOrderAddress();
        (this.order?.order_lines || []).forEach(ln => {
          const path = ln?.item_snapshot?.type_path || ln?.item?.type?.path || '';
          if (path) this._ensureUiSchema(path).catch(()=>{});
        });
      } catch (e) {
        this.err = e?.message || 'Błąd';
        app.toast?.err?.(this.err);
      } finally {
        this.loading = false;
      }
    },

    async _loadOrder() {
      const ro = await app.api(`/api/users/me/orders/${orderPublicId}/`);
      if (!ro.ok) throw new Error('Nie udało się pobrać zamówienia');
      this.order = await app.readJson(ro);
    },

    _indexShippings() {
      this.shippingByLine = {};
      (this.order?.shippings || []).forEach(s => { this.shippingByLine[s.order_line_public_id] = s; });
      (this.order?.order_lines || []).forEach(ln => this._hydrateSelectedForLine(ln.public_id));
    },

    _selectedFromShip(linePid) {
      const ship = this.shippingByLine[linePid];
      if (!ship) return 'PICKUP';
      if (ship.mode && String(ship.mode).toUpperCase() === 'PICKUP') return 'PICKUP';
      if (ship.package_type_public_id) return ship.package_type_public_id;
      const label = String(ship.package_label || '').toUpperCase();
      return (label === 'PICKUP') ? 'PICKUP' : 'PICKUP';
    },

    _hydrateSelectedForLine(linePid) {
      this.selectedShipByLine[linePid] = this._selectedFromShip(linePid);
    },

    _hydrateOrderAddress() {
      const a = this.order?.shipping_address || {};
      this.orderAddress = {
        first_name: a.first_name || '',
        last_name: a.last_name || '',
        phone_number: a.phone_number || '',
        email: a.email || '',
        street: a.street || '',
        house_number: a.house_number || '',
        city: a.city || '',
        state: a.state || '',
        postal_code: a.postal_code || '',
        country: a.country || ''
      };
    },

    async _loadOptionsForLines() {
      this.optionsByLine = {};
      const lines = this.order?.order_lines || [];
      for (const ln of lines) {
        const itemPid = ln?.item?.public_id || null;

        const base = [{
          typePublicId: null,
          label: `Odbiór osobisty (${app.moneyText(0)})`,
          amount: 0,
          currency: (ln.unit_price?.currency || 'PLN'),
          pickup: true
        }];

        let opts = [];
        if (itemPid) {
          try {
            const r = await app.api(`/api/public/item-sets/${itemPid}/`);
            if (r.ok) {
              const it = await app.readJson(r);
              opts = (it?.shipping_options || []).map(row => {
                const m = row.effective_price || row.price_override || row.package_type?.price || null;
                return {
                  typePublicId: row.package_type?.public_id,
                  label: `${row.package_type?.provider || 'Paczka'} - ${app.moneyText(m)}`,
                  amount: app.moneyAmount?.(m) ?? null,
                  currency: (app.moneyNormalize?.(m)?.currency || 'PLN')
                };
              }).filter(x => x.typePublicId);
            }
          } catch {}
        }
        if (!opts.length) {
          const dims = {
            length_cm: ln?.item?.length_cm ?? ln?.item_snapshot?.length_cm ?? null,
            width_cm: ln?.item?.width_cm ?? ln?.item_snapshot?.width_cm ?? null,
            height_cm: ln?.item?.height_cm ?? ln?.item_snapshot?.height_cm ?? null,
            weight_kg: ln?.item?.weight_kg ?? ln?.item_snapshot?.weight_kg ?? null
          };
          const qs = new URLSearchParams();
          Object.entries(dims).forEach(([k, v]) => { if (v != null && v !== '') qs.set(k, v); });
          try {
            const r = await app.api(`/api/public/shipping/package-types/suggest?${qs.toString()}`);
            if (r.ok) {
              const arr = await app.readJson(r);
              opts = (arr || []).map(row => {
                const pt = row.package_type || {};
                const m = row.price || null;
                return {
                  typePublicId: pt.public_id,
                  label: `${pt.provider || 'Paczka'} - ${app.moneyText(m)}`,
                  amount: app.moneyAmount?.(m) ?? null,
                  currency: (app.moneyNormalize?.(m)?.currency || 'PLN')
                };
              }).filter(x => x.typePublicId);
            }
          } catch {}
        }

        this.optionsByLine[ln.public_id] = base.concat(opts);
        if (!this.selectedShipByLine[ln.public_id]) this._hydrateSelectedForLine(ln.public_id);
      }
    },

    toggle(pid) {
      this.expanded[pid] = !this.expanded[pid];
    },

    isExpanded(pid) {
      return !!this.expanded[pid];
    },

    isSelected(linePid, opt) {
      const current = this.selectedShipByLine[linePid] ?? this._selectedFromShip(linePid);
      const val = opt.pickup ? 'PICKUP' : (opt.typePublicId || '');
      return current === val;
    },

    onRadioChange(linePid, ev) {
      const val = (ev?.target?.value || '').trim();
      if (val) this.selectedShipByLine[linePid] = val;
    },

    canEditShipping() {
      return this.order?.order_status === 'PENDING';
    },

    needAddress() {
      const lines = this.order?.order_lines || [];
      return lines.some(ln => {
        const s = this.shippingByLine[ln.public_id];
        if (!s) return false;
        if (s.mode) return String(s.mode).toUpperCase() === 'PACKAGE';
        return !!(s.package_type_public_id || (s.package_label && s.package_label !== 'PICKUP'));
      });
    },

    chosen(linePid) {
      const el = document.querySelector(`input[name="ship-${linePid}"]:checked`);
      return el ? el.value : null;
    },

    async choose(linePid) {
      try {
        const val = this.chosen(linePid);
        if (val == null) return;
        this.lineBusy[linePid] = true;

        const body = (val === 'PICKUP') ? { mode: 'PICKUP' } : { mode: 'PACKAGE', package_type_public_id: val };
        const r = await app.api(`/api/users/me/orders/${this.order.public_id}/lines/${linePid}/select-shipping/`, { method: 'POST', body: JSON.stringify(body) });
        const j = await app.readJson(r);
        if (!r.ok) {
          app.toast?.err?.(app.errText?.(j) || 'Błąd zapisu wysyłki');
          return;
        }

        const cancelled = r.headers.get('X-Active-Payment-Cancelled') === '1';
        if (cancelled) app.toast?.info?.('Aktywna płatność została anulowana - utwórz nową po zmianie wysyłki.');

        await this._loadOrder();
        this._indexShippings();
        this._hydrateOrderAddress();
        app.toast?.ok?.('Zapisano formę wysyłki');
      } catch (e) {
        app.toast?.err?.(e?.message || 'Błąd');
      } finally {
        this.lineBusy[linePid] = false;
      }
    },

    async useDefaultAddress() {
      try {
        const r = await app.api('/api/users/me/shipping-address');
        if (r.status === 404) {
          app.toast?.err?.('Nie masz zapisanego domyślnego adresu.');
          return;
        }
        const a = await app.readJson(r);
        if (!r.ok) {
          app.toast?.err?.(app.errText?.(a) || 'Nie udało się pobrać domyślnego adresu');
          return;
        }

        const rr = await app.api(`/api/users/me/orders/${this.order.public_id}/shipping-address/`, { method: 'POST', body: JSON.stringify(a) });
        const jj = await app.readJson(rr);
        if (!rr.ok) {
          app.toast?.err?.(app.errText?.(jj) || 'Błąd zapisu adresu');
          return;
        }

        await this._loadOrder();
        this._indexShippings();
        this._hydrateOrderAddress();
        app.toast?.ok?.('Użyto domyślnego adresu');
      } catch (e) {
        app.toast?.err?.(e?.message || 'Błąd');
      }
    },

    _clearAddrErrors() {
      for (const k of Object.keys(this.addrErr)) this.addrErr[k] = '';
    },

    _applyAddrErrors(d) {
      const e = d?.errors || d || {};
      this._clearAddrErrors();
      for (const [k, v] of Object.entries(e)) {
        if (k in this.addrErr) this.addrErr[k] = Array.isArray(v) ? v.join('; ') : String(v);
      }
      const nf = e.non_field_errors || d?.detail;
      if (nf) app.toast?.err?.(Array.isArray(nf) ? nf.join('; ') : String(nf));
      this._scrollFirstAddrError();
    },

    _scrollFirstAddrError() {
      const first = Object.keys(this.addrErr).find(k => !!this.addrErr[k]);
      if (!first) return;
      try {
        document.getElementById(`addr-${first}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      } catch {}
    },

    _validateOrderAddressBasic() {
      this._clearAddrErrors();
      const a = this.orderAddress || {};
      let ok = true;
      const required = ["first_name","last_name","phone_number","email","street","house_number","city","postal_code","country"];
      for (const k of required) {
        const v = (a[k] == null ? '' : String(a[k])).trim();
        if (!v) {
          this.addrErr[k] = 'To pole jest wymagane';
          ok = false;
        }
      }
      const email = (a.email == null ? '' : String(a.email)).trim();
      if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
        this.addrErr.email = 'Nieprawidłowy adres e-mail';
        ok = false;
      }
      const phoneDigits = String(a.phone_number || '').replace(/\D+/g, '');
      if (phoneDigits && phoneDigits.length < 6) {
        this.addrErr.phone_number = 'Nieprawidłowy numer telefonu';
        ok = false;
      }
      const postal = (a.postal_code == null ? '' : String(a.postal_code)).trim();
      if (postal && !/^[0-9]{2}-[0-9]{3}$/.test(postal)) {
        this.addrErr.postal_code = 'Nieprawidłowy kod pocztowy';
        ok = false;
      }
      if (!ok) this._scrollFirstAddrError();
      return ok;
    },

    async saveOrderAddress() {
      this.addrMsg = '';
      if (!this._validateOrderAddressBasic()) return false;
      this.savingAddr = true;
      try {
        const r = await app.api(`/api/users/me/orders/${this.order.public_id}/shipping-address/`, { method: 'POST', body: JSON.stringify(this.orderAddress) });
        const d = await app.readJson(r);
        if (!r.ok) {
          this._applyAddrErrors(d || {});
          throw new Error(d?.detail || 'Błąd zapisu adresu');
        }
        await this._loadOrder();
        this._indexShippings();
        this._hydrateOrderAddress();
        this.addrMsg = 'Zapisano adres dla tego zamówienia';
        app.toast?.ok?.(this.addrMsg);
        setTimeout(() => this.addrMsg = '', 2000);
        return true;
      } catch (e) {
        app.toast?.err?.(e?.message || 'Błąd');
        return false;
      } finally {
        this.savingAddr = false;
      }
    },

    async onPayClick() {
      if (!this.order || this.order.order_status !== 'PENDING') return;
      if (!this.needAddress()) {
        const url = this.order.transaction_public_id ? (`/pay/${this.order.transaction_public_id}`) : '/pay';
        window.location.href = url;
        return;
      }
      if (this.payBusy) return;
      this.payBusy = true;
      try {
        const ok = await this.saveOrderAddress();
        if (!ok) return;
        const url = this.order.transaction_public_id ? (`/pay/${this.order.transaction_public_id}`) : '/pay';
        window.location.href = url;
      } finally {
        this.payBusy = false;
      }
    },

    async _ensureUiSchema(path){
      if (!path || this._uiByPath[path]) return;
      try {
        const { ui_schema } = await app.getSchemaCached(path);
        this._uiByPath[path] = ui_schema || {};
      } catch {
        this._uiByPath[path] = {};
      } finally {
        this.uiNonce++;
      }
    },

    _attrsFor(ln){
      const attrs = (ln?.item_snapshot?.attributes || ln?.item?.attributes || {}) || {};
      const path  = ln?.item_snapshot?.type_path || ln?.item?.type?.path || '';
      const ui    = path ? (this._uiByPath[path] || {}) : {};
      return { attrs, ui };
    },

    attrPairsFor(ln){
      try {
        const { attrs, ui } = this._attrsFor(ln);
        return app.attrPairs ? app.attrPairs(attrs, (ui?.attrs || ui) || {}) : Object.entries(attrs);
      } catch {
        return [];
      }
    },

    attrBadgesFor(ln){
      try {
        const { attrs, ui } = this._attrsFor(ln);
        if (!attrs || !Object.keys(attrs).length) return [];
        const UI = (ui && (ui.attrs || ui)) || {};
        const badgeKeys = new Set([...(UI.badges || UI.tags || [])]);
        const toneMap   = UI.badge_tone || {};
        const out = [];
        for (const [k, raw] of Object.entries(attrs)) {
          if (!badgeKeys.has(k)) continue;
          const label   = app.attrLabel ? app.attrLabel(k, UI) : k;
          const prettyV = (typeof raw === 'boolean') ? (raw ? '' : null) : (app.attrValue ? app.attrValue(k, raw, UI) : String(raw));
          if (typeof raw === 'boolean') {
            if (raw) out.push({ text: label, tone: toneMap[k] || 'success' });
          } else {
            out.push({ text: `${label}: ${prettyV}`, tone: toneMap[k] || 'info' });
          }
        }
        return out;
      } catch {
        return [];
      }
    },

    tOrderStatus(code){
      const m = { PENDING:'Oczekujące', COMPLETED:'Zakończone', CANCELLED:'Anulowane', SHIPPED:'Wysłane', DELIVERED:'Dostarczone' };
      return m[String(code||'').toUpperCase()] || (code || '');
    },

    tPaymentMethod(code){
      const m = { CASH:'Gotówka', CREDIT_CARD:'Karta', BANK_TRANSFER:'Przelew bankowy', BLIK:'BLIK', APPLE_PAY:'Apple Pay', GOOGLE_PAY:'Google Pay' };
      return m[String(code||'').toUpperCase()] || (code || '');
    },

    tShippingStatus(code){
      const m = { PENDING:'Oczekująca', SHIPPED:'Wysłana', DELIVERED:'Dostarczona', CANCELLED:'Anulowana', RETURNED:'Zwrócona' };
      return m[String(code||'').toUpperCase()] || (code || '');
    },
  };
};
