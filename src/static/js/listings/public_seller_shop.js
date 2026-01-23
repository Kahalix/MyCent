window.app = window.app || {};

app.publicSellerShop = function (opts = {}) {
  const base = app.publicOffersList({ sellerSlug: (opts.sellerSlug || '').trim() });

  return {
    ...base,

    seller: null,
    sellerLoading: false,
    sellerErr: '',

    async init() {
      await this._loadSeller();
      base.init.call(this);
    },

    async _loadSeller() {
      const slug = (this.sellerSlug || '').trim();
      if (!slug) return;

      this.sellerLoading = true;
      this.sellerErr = '';
      try {
        const r = await app.api(`/api/public/sellers/${encodeURIComponent(slug)}/`, { method: 'GET' });
        if (!r.ok) throw new Error('Nie udało się pobrać danych sklepu.');
        this.seller = await r.json().catch(() => null);
      } catch (e) {
        this.sellerErr = e?.message || 'Błąd';
        this.seller = null;
      } finally {
        this.sellerLoading = false;
      }
    },

    shopTitle() {
      const name = (this.seller?.company_name || '').trim();
      return name || `Sklep: ${this.sellerSlug || ''}`;
    },

    logoSrc() {
      const v = this.seller?.logo_image;
      return v && String(v).trim() ? v : '';
    },

    bannerSrc() {
      const v = this.seller?.banner_image;
      return v && String(v).trim() ? v : '';
    },

    phone() {
      const v = this.seller?.contact_phone;
      return v && String(v).trim() ? String(v).trim() : '';
    },

    email() {
      const v = this.seller?.contact_email;
      return v && String(v).trim() ? String(v).trim() : '';
    },

    hasContact() {
      return !!(this.phone() || this.email());
    },

    hasRating() {
      return this.seller?.rating !== null && this.seller?.rating !== undefined && String(this.seller.rating).trim() !== '';
    },

    ratingText() {
      if (!this.hasRating()) return '';
      const r = Number(this.seller.rating);
      const rating = Number.isFinite(r) ? r.toFixed(2) : String(this.seller.rating);
      const cnt = Number(this.seller?.rating_count ?? 0);
      return `Ocena: ${rating} (${Number.isFinite(cnt) ? cnt : (this.seller?.rating_count ?? 0)})`;
    },
  };
};
