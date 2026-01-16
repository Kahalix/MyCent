window.app = window.app || {};

app.shippingAddress = function () {
  return {
    addr: {
      first_name: '', last_name: '', phone_number: '', email: '',
      street: '', house_number: '', city: '', state: '', postal_code: '', country: ''
    },
    exists: false,
    busy: false,
    err: '',
    ok: '',

    async load() {
      this.err = ''; this.ok = '';
      try {
        const r = await app.api('/api/users/me/shipping-address');
        if (r.status === 404) { this.exists = false; return; }
        if (!r.ok) throw new Error('Load failed');
        this.addr = await r.json();
        this.exists = true;
      } catch (e) {
        this.err = 'Nie udało się wczytać adresu';
      }
    },

    async save() {
      this.busy = true; this.err = ''; this.ok = '';
      const method = this.exists ? 'PATCH' : 'POST';
      try {
        const r = await app.api('/api/users/me/shipping-address', {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.addr)
        });
        if (!r.ok) {
          const d = await r.json().catch(() => ({}));
          throw new Error(d.detail || 'Błąd zapisu');
        }
        const data = await r.json().catch(() => ({}));
        this.addr = { ...this.addr, ...data };
        this.exists = true;
        this.ok = 'Zapisano adres';
      } catch (e) {
        this.err = e.message || 'Błąd zapisu';
      } finally {
        this.busy = false;
      }
    },

    async remove() {
      if (!this.exists) return;
      this.busy = true; this.err = ''; this.ok = '';
      try {
        const r = await app.api('/api/users/me/shipping-address', { method: 'DELETE' });
        if (!r.ok && r.status !== 204) throw new Error('Nie udało się usunąć');
        this.exists = false;
        this.addr = {
          first_name: '', last_name: '', phone_number: '', email: '',
          street: '', house_number: '', city: '', state: '', postal_code: '', country: ''
        };
        this.ok = 'Usunięto adres';
      } catch (e) {
        this.err = e.message || 'Błąd usuwania';
      } finally {
        this.busy = false;
      }
    }
  };
};
