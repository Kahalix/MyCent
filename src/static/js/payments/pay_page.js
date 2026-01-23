window.app = window.app || {};

window._stripeLoadPromise = window._stripeLoadPromise || null;
function ensureStripeJs() {
  if (window.Stripe) return Promise.resolve();
  if (window._stripeLoadPromise) return window._stripeLoadPromise;
  window._stripeLoadPromise = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://js.stripe.com/v3/';
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('Nie udało się załadować Stripe.js'));
    document.head.appendChild(s);
  });
  return window._stripeLoadPromise;
}

app.payPage = function (opts = {}) {
  const TX_TYPE_PL = {
    "PURCHASE": "Zakup",
    "PAWN_PURCHASE": "Skup",
    "PAWN_EXTENSION": "Przedłużenie zastawu",
    "PAWN_REDEEM": "Wykup zastawu",
    "PLEDGE": "Zastaw"
  };
  const TX_STATUS_PL = {
    "PENDING": "Oczekująca",
    "COMPLETED": "Zakończona",
    "CANCELLED": "Anulowana",
    "REFUNDED": "Zwrócona"
  };
  const PAY_STATUS_PL = {
    "REQUIRES_CONFIRMATION": "Wymaga potwierdzenia",
    "REQUIRES_ACTION": "Wymaga działania",
    "PROCESSING": "Przetwarzana",
    "SUCCEEDED": "Zakończona pomyślnie",
    "FAILED": "Niepowodzenie",
    "CANCELLED": "Anulowana"
  };
  const PROVIDER_PL = { "STRIPE": "Stripe", "SIM": "Symulacja" };

  const ACTIVE_STATUSES = new Set(["REQUIRES_CONFIRMATION", "REQUIRES_ACTION", "PROCESSING"]);

  return {
    txId: (opts.txPublicId || '').trim(),
    tx: null,
    payment: null,

    loading: false,
    err: '', ok: '',

    orders: [],
    ordersLoading: false,
    ordersErr: '',
    orderExpanded: {},
    orderUrl: (opts.orderUrl || '').trim(),

    couponCode: '',
    coupons: [],
    couponsLoading: false,
    selectedUserCouponId: '',

    creating: false,
    confirming: false,

    stripe: null,
    stripeElements: null,
    stripeElement: null,
    stripeMounted: false,
    stripeErr: '',
    _lastClientSecret: '',
    _loadHandlersBound: false,

    async init() {
      await this._loadTx();
      if (!this.txId) return;

      await this._loadOrdersForTx();
      await this._tryAttachExistingPayment();

      if (this.isPurchase) { await this._loadUserCoupons(); } else { this.coupons = []; }

      if (this.isStripe && this.payment?.client_secret) {
        if (this.$nextTick) await this.$nextTick();
        await this._mountStripeElement(true);
      }
    },

    stripePk() {
      const meta = document.querySelector('meta[name="stripe-pk"]');
      const fromMeta = (meta && meta.getAttribute('content')) || '';
      const fromWin = (window.STRIPE_PK || '');
      return (fromMeta || fromWin || '').trim();
    },

    async _loadTx() {
      this.loading = true; this.err='';
      try {
        if (this.txId) {
          const r = await app.api(`/api/users/me/transactions/${this.txId}/`);
          if (!r.ok) throw new Error('Nie udało się pobrać transakcji.');
          this.tx = await app.readJson(r);
        } else {
          const r = await app.api(`/api/users/me/transactions/?status=PENDING&ordering=-created_at&page_size=1`);
          const raw = await r.json().catch(()=> ({}));
          const list = Array.isArray(raw) ? raw : (Array.isArray(raw.results) ? raw.results : []);
          this.tx = list[0] || null;
        }

        this.txId = this.tx?.public_id || this.txId || '';
        if (!this.txId) this.err = 'Nie znaleziono aktywnej transakcji do opłacenia.';
        if (this.tx && this.tx.status !== 'PENDING') {
          this.err = 'Ta transakcja nie jest już w statusie „Oczekująca” - płatność niedostępna.';
        }
      } catch (e) {
        this.err = e?.message || 'Błąd sieci.';
      } finally {
        this.loading = false;
      }
    },

    async _loadOrdersForTx() {
      this.ordersLoading = true;
      this.ordersErr = '';
      try {
        if (!this.txId) return;
        const q = new URLSearchParams({
          tx: this.txId,
          ordering: '-created_at'
        });
        const r = await app.api(`/api/users/me/orders/?${q.toString()}`);
        const raw = await r.json().catch(() => ({}));
        const list = Array.isArray(raw) ? raw : (Array.isArray(raw.results) ? raw.results : []);
        this.orders = list;
        if (!this.orderUrl && this.orders.length === 1) {
          this.orderUrl = `/orders/${this.orders[0].public_id}`;
        }
      } catch (e) {
        this.ordersErr = e?.message || 'Nie udało się pobrać zamówień dla tej transakcji.';
      } finally {
        this.ordersLoading = false;
      }
    },

    async _tryAttachExistingPayment() {
      if (!this.txId) return;
      try {
        const q = new URLSearchParams({
          tx: this.txId, active: 'true', ordering: '-created_at', page_size: '1'
        });
        const r = await app.api(`/api/users/me/payments/?${q.toString()}`);
        const raw = await r.json().catch(()=> ({}));
        const list = Array.isArray(raw) ? raw : (Array.isArray(raw.results) ? raw.results : []);
        const cand = list[0];
        if (cand) this.payment = cand;
      } catch {}
    },

    async _loadUserCoupons() {
      if (!this.txId || !this.isPurchase) return;
      this.couponsLoading = true;
      try {
        const url = `/api/users/me/coupons/?redeemed=false&usable_for_tx=${encodeURIComponent(this.txId)}&ordering=-created_at`;
        const r = await app.api(url, { method:'GET' });
        const j = await r.json().catch(()=> ({}));
        this.coupons = Array.isArray(j) ? j : (Array.isArray(j.results) ? j.results : []);
      } finally { this.couponsLoading = false; }
    },

    async _refreshPayment() {
      try {
        if (!this.payment?.public_id) return;
        const r = await app.api(`/api/users/me/payments/${this.payment.public_id}/`);
        if (!r.ok) return;
        this.payment = await app.readJson(r);
      } catch {}
    },

    async _awaitWebhookUpdate(maxTries = 8, delayMs = 500) {
      for (let i = 0; i < maxTries; i++) {
        await this._refreshPayment();
        const hasPoints = Number(this.payment?.metadata?.loyalty_points_awarded ?? 0) > 0;
        const isFinal = ['SUCCEEDED','FAILED','CANCELLED'].includes(this.payment?.status);
        if (hasPoints || isFinal) break;
        await new Promise(r => setTimeout(r, delayMs));
      }
    },

    get amountStr() {
      const a = this.tx?.expected_total_amount;
      const c = this.tx?.expected_total_currency || 'PLN';
      if (a == null) return '—';
      const num = (typeof a === 'string') ? parseFloat(a) : a;
      return (isFinite(num) ? num.toFixed(2) : String(a)) + ' ' + c;
    },
    get couponApplied(){ return !!(this.tx && (this.tx.coupon_id || this.tx.user_coupon_id)); },
    get isPurchase(){ return (this.tx?.type === 'PURCHASE'); },
    get isStripe(){ return (this.payment?.provider === 'STRIPE'); },

    get isDone(){
      const s = this.payment?.status;
      return s === 'SUCCEEDED' || s === 'FAILED' || s === 'CANCELLED';
    },
    get isSuccess(){ return this.payment?.status === 'SUCCEEDED'; },
    get isFailure(){ return this.payment?.status === 'FAILED' || this.payment?.status === 'CANCELLED'; },

    get awardedPoints(){
      const n = Number(this.payment?.metadata?.loyalty_points_awarded ?? 0);
      return Number.isFinite(n) ? n : 0;
    },

    labelTxType(code){ return TX_TYPE_PL[code] || code || '—'; },
    labelTxStatus(code){ return TX_STATUS_PL[code] || code || '—'; },
    labelPaymentStatus(code){ return PAY_STATUS_PL[code] || code || '—'; },
    labelProvider(code){ return PROVIDER_PL[code] || code || '—'; },

    badgeForPayment(code){
      if (!code) return 'badge-ghost';
      if (code === 'SUCCEEDED') return 'badge-success';
      if (code === 'FAILED' || code === 'CANCELLED') return 'badge-error';
      if (ACTIVE_STATUSES.has(code)) return 'badge-warning';
      return 'badge-ghost';
    },

    labelOrderStatus(code) {
      const m = {
        PENDING: 'Oczekujące',
        COMPLETED: 'Zakończone',
        CANCELLED: 'Anulowane',
        REFUNDED: 'Zwrócone'
      };
      const key = String(code || '').toUpperCase();
      return m[key] || code || '—';
    },

    labelForUserCoupon(uc){
      const c = uc?.coupon || {};
      const code = c.code ? (c.code + ' • ') : '';
      if (c.discount_type === 'PERCENTAGE') {
        const pct = app.moneyAmount(c.discount_value);
        return code + (Number.isFinite(pct) ? (pct.toFixed(0) + '%') : '—%');
      }
      return code + app.moneyText(c.discount_value, '0.00 PLN');
    },

    shippingForLine(order, linePid) {
      if (!order || !Array.isArray(order.shippings)) return null;
      for (let i = 0; i < order.shippings.length; i++) {
        const s = order.shippings[i];
        if (s.order_line_public_id === linePid) return s;
      }
      return null;
    },

    shippingLabel(order, line) {
      const s = this.shippingForLine(order, line.public_id);
      if (!s) return 'Odbiór osobisty';
      const label = (s.package_label || '').trim();
      if (!s.package_type_public_id || !label || label.toUpperCase() === 'PICKUP') {
        return 'Odbiór osobisty';
      }
      return label + ' • ' + app.moneyText(s.price);
    },

    toggleOrder(pid) {
      this.orderExpanded[pid] = !this.orderExpanded[pid];
    },

    isOrderExpanded(pid) {
      return !!this.orderExpanded[pid];
    },

    async applyCoupon(){
      if (!this.txId || !this.isPurchase) return;
      const code = (this.couponCode||'').trim();
      const ucid = (this.selectedUserCouponId||'').trim();
      if (!code && !ucid) return;
      if (code && ucid) { app.warn('Użyj tylko jednego źródła rabatu: kod LUB kupon z listy.'); return; }

      this.err=''; this.ok='';
      try{
        const r = await app.api(`/api/users/me/transactions/${this.txId}/attach-coupon/`, {
          method:'POST',
          body: JSON.stringify(code ? { coupon_code: code } : { user_coupon_public_id: ucid })
        });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok){ this.err = app.errText(j) || 'Nie udało się zastosować kuponu.'; app.error(this.err); return; }
        this.tx = j;
        this.ok = 'Kupon zastosowany.'; app.ok(this.ok);
        if (code) this.couponCode = '';
      } catch(e){ this.err = e?.message || 'Błąd'; app.error(this.err); }
    },

    async removeCoupon(){
      if (!this.txId || !this.isPurchase) return;
      this.err=''; this.ok='';
      try{
        const r = await app.api(`/api/users/me/transactions/${this.txId}/attach-coupon/`, {
          method:'POST', body: JSON.stringify({})
        });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok){ this.err = app.errText(j) || 'Nie udało się usunąć kuponu.'; app.error(this.err); return; }
        this.tx = j;
        this.ok = 'Kupon usunięty.'; app.ok(this.ok);
      } catch(e){ this.err = e?.message || 'Błąd'; app.error(this.err); }
    },

    async createIntent(provider = 'STRIPE'){
      if (!this.txId) return;

      if (provider === 'STRIPE' && !this.stripePk()) {
        app.warn('Brak publicznego klucza Stripe - używam trybu symulacji.');
        provider = 'SIM';
      }

      this.creating = true; this.err=''; this.ok='';
      try {
        const idem = 'pay-' + this.txId + '-' + Math.random().toString(36).slice(2,8);
        const body = { transaction_public_id: this.txId, provider };

        const r = await app.api('/api/users/me/payments/intents/', {
          method: 'POST',
          headers: { 'Idempotency-Key': idem },
          body: JSON.stringify(body)
        });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok){ this.err = app.errText(j) || 'Nie udało się zainicjować płatności.'; app.error(this.err); return; }
        this.payment = j;
        this.ok = 'Płatność zainicjowana.'; app.ok(this.ok);

        if (this.isStripe && this.payment?.client_secret) {
          if (this.$nextTick) await this.$nextTick();
          await this._mountStripeElement(true);
        }
      } catch(e){ this.err = e?.message || 'Błąd'; app.error(this.err); }
      finally { this.creating = false; }
    },

    async refreshIntent(){
      try{
        if (this.payment?.public_id) {
          await app.api(`/api/users/me/payments/${this.payment.public_id}/cancel/`, {
            method:'POST', body: JSON.stringify({ reason: 'refresh-intent' })
          }).catch(()=>{});
        }
        try { this.stripeElement?.unmount(); } catch{}
        this.stripeElement = null;
        this.stripeElements = null;
        this.stripeMounted = false;
        this._lastClientSecret = '';
        this._loadHandlersBound = false;
        this.stripeErr = '';
        this.payment = null;

        await this.createIntent('STRIPE');
      } catch(e){
        app.error(e?.message || 'Nie udało się odświeżyć płatności.');
      }
    },

    async _waitForHost(selector = '#payment-element', attempts = 60) {
      for (let i = 0; i < attempts; i++) {
        const el = document.querySelector(selector);
        if (el && el.isConnected) return el;
        await new Promise(r => requestAnimationFrame(r));
      }
      return null;
    },

    _stripeAppearance(){
      const isDark = document.documentElement.classList.contains('dark')
                  || (document.documentElement.getAttribute('data-theme') || '').toLowerCase().includes('dark');

      const vars = isDark ? {
        colorPrimary: '#d4af37',
        colorBackground: '#2B3038',
        colorText: '#EEF1F5',
        colorDanger: '#f87171',
        colorTextSecondary: '#a0a6b0',
        borderRadius: '12px',
        fontFamily: 'Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif',
      } : {
        colorPrimary: '#d4af37',
        colorBackground: '#ffffff',
        colorText: '#0b0b0c',
        colorDanger: '#dc2626',
        colorTextSecondary: '#6b7280',
        borderRadius: '12px',
        fontFamily: 'Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif',
      };

      return {
        theme: 'flat',
        variables: vars,
        rules: {
          '.Input': { boxShadow: 'none', border: '1px solid var(--colorBackgroundAccent, #e6e8ee)' },
          '.Tab, .Block': { borderRadius: '12px' }
        }
      };
    },

    async _mountStripeElement(forceRemount = false){

      await ensureStripeJs().catch((e) => { this.stripeErr = e.message || 'Stripe.js nie załadował się.'; return; });
      if (this.stripeErr) return;

      try{
        this.stripeErr = '';
        if (!window.Stripe) { this.stripeErr = 'Stripe.js nie załadował się.'; return; }
        const pk = this.stripePk();
        if (!pk) { this.stripeErr = 'Brak publicznego klucza Stripe.'; return; }
        if (!this.payment?.client_secret) { this.stripeErr = 'Brak client_secret.'; return; }

        const host = await this._waitForHost('#payment-element', 60);
        if (!host) { this.stripeErr = 'Brak kontenera #payment-element.'; return; }

        const locale = 'pl';
//        if (!this.stripe) this.stripe = Stripe(pk); Auto Lang

        if (!this.stripe) this.stripe = Stripe(pk, { locale });

        const secret = this.payment.client_secret;
        const mustRemount = forceRemount || (this._lastClientSecret && this._lastClientSecret !== secret);

        if (mustRemount && this.stripeElement) {
          try { this.stripeElement.unmount(); } catch {}
          this.stripeElement = null;
          this.stripeMounted = false;
          this._loadHandlersBound = false;
        }
        if (mustRemount) { this.stripeElements = null; }

        if (!this.stripeElements) {
          this.stripeElements = this.stripe.elements({
            clientSecret: secret,
            appearance: this._stripeAppearance()
          });
        } else {
          try { this.stripeElements.update({ appearance: this._stripeAppearance() }); } catch {}
        }

        if (!this.stripeElement) {
          this.stripeElement = this.stripeElements.create('payment', { layout: { type: 'tabs' } });
          if (!this._loadHandlersBound) {
            this.stripeElement.on('loaderror', (ev) => {
              const code = ev?.error?.code ? ` [${ev.error.code}]` : '';
              const msg = ev?.error?.message || 'Stripe: nie udało się załadować Payment Element.';
              this.stripeErr = msg + code + ' — kliknij „Odśwież płatność”.';
              console.error('Stripe loaderror:', ev);
            });
            this.stripeElement.on('ready', () => {
              if (this.stripeErr.startsWith('Stripe')) this.stripeErr = '';
            });
            this._loadHandlersBound = true;
          }
        }

        if (!this.stripeMounted) {
          this.stripeElement.mount(host);
          this.stripeMounted = true;
        }

        this._lastClientSecret = secret;
      } catch (e) {
        this.stripeErr = e?.message || 'Nie udało się zainicjować Stripe Elements.';
      }
    },

    async confirmStripe(){
      if (!this.isStripe) return;

      if (!this.stripe || !this.stripeElements || !this.stripeElement || !this.stripeMounted) {
        if (this.$nextTick) await this.$nextTick();
        await this._mountStripeElement(true);
      }

      this.confirming = true; this.err=''; this.ok='';
      try{
        const returnUrl = new URL(`/pay/${this.txId}`, location.origin).toString();

        const { error, paymentIntent } = await this.stripe.confirmPayment({
          elements: this.stripeElements,
          confirmParams: { return_url: returnUrl },
          redirect: 'if_required'
        });

        if (error) {
          this.err = error.message || 'Płatność odrzucona przez Stripe.';
          app.error(this.err);
          await this._refreshPayment();
          return;
        }

        if (paymentIntent?.status === 'succeeded') {
          this.ok = 'Płatność zakończona powodzeniem. Dziękujemy!';
          app.ok(this.ok);
          this.payment = { ...this.payment, status: 'SUCCEEDED' };
          await this._awaitWebhookUpdate(8, 500);
        } else if (paymentIntent?.status === 'processing' || paymentIntent?.status === 'requires_action') {
          this.ok = 'Płatność przetwarzana…';
          app.info(this.ok);
          await this._refreshPayment();
        } else {
          await this._refreshPayment();
        }
      } catch(e){
        this.err = e?.message || 'Błąd potwierdzania Stripe.';
        app.error(this.err);
      } finally {
        this.confirming = false;
      }
    },

    async confirm(result='success'){
      if (!this.payment?.public_id) return;
      this.confirming = true; this.err=''; this.ok='';
      try{
        const r = await app.api(`/api/users/me/payments/${this.payment.public_id}/confirm/`, {
          method:'POST', body: JSON.stringify({ result })
        });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok){ this.err = app.errText(j) || 'Błąd potwierdzania.'; app.error(this.err); return; }
        this.payment = j;
        if (j.status === 'SUCCEEDED'){ this.ok = 'Płatność zakończona powodzeniem. Dziękujemy!'; app.ok(this.ok); }
        else if (j.status === 'FAILED'){ this.err = 'Płatność odrzucona.'; app.error(this.err); }
      } catch(e){ this.err = e?.message || 'Błąd'; app.error(this.err); }
      finally { this.confirming = false; }
    },

    async cancel(){
      if (!this.payment?.public_id) return;
      try{
        const r = await app.api(`/api/users/me/payments/${this.payment.public_id}/cancel/`, {
          method:'POST', body: JSON.stringify({ reason: 'User cancelled' })
        });
        const j = await r.json().catch(()=> ({}));
        if (!r.ok){ app.error(app.errText(j) || 'Nie udało się anulować.'); return; }
        this.payment = j;
        app.info('Płatność anulowana.');
      } catch{}
    }
  };
};
