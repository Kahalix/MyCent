// static/js/identity/user_public.js
window.app = window.app || {};

app.userPublic = function (opts = {}) {
  return {
    userId: (opts.userId || '').trim(),
    data: null,
    loading: false,
    err: '',

    async init() {
      this.loading = true; this.err = '';
      try {
        const r = await app.api(`/api/public/users/${encodeURIComponent(this.userId)}/`, { method: 'GET' });
        if (!r.ok) throw new Error('Nie udało się pobrać profilu użytkownika.');
        this.data = await r.json().catch(() => (null));
      } catch (e) {
        this.err = e?.message || 'Błąd';
      } finally {
        this.loading = false;
      }
    },

    avatar() {
      const src = this.data?.user_image;
      return src && String(src).trim()
        ? src
        : 'https://placehold.co/96x96?text=%F0%9F%91%A4';
    },

    fullName() {
      const u = this.data || {};
      const name = [u.first_name, u.last_name].filter(Boolean).join(' ').trim();
      return name || u.email || 'Użytkownik';
    }
  };
};
