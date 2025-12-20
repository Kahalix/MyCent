window.app = window.app || {};

app.profileView = function () {
  return {
    // aktywna zakładka
    tab: 'overview',

    // user + stan
    me: null,
    busy: false,
    err: '',
    okMsg: '',

    // avatar
    avatarBusy: false,
    avatarErr: '',
    avatarOk: '',
    selectedFile: null,
    previewUrl: '',

    async load() {
      const r = await app.api('/api/users/me/');
      if (!r.ok) { this.err = 'Nie zalogowano'; return; }
      this.me = await r.json();
    },

    setTab(t) { this.tab = t; },

    async save() {
      this.busy = true; this.err = ''; this.okMsg = '';
      const r = await app.api('/api/users/me/', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          first_name: this.me.first_name || '',
          last_name: this.me.last_name || '',
          phone_number: this.me.phone_number || ''
        })
      });
      const d = await r.json().catch(() => ({}));
      this.busy = false;
      if (!r.ok) { this.err = d.detail || 'Błąd zapisu'; return; }
      this.okMsg = 'Zapisano';
    },

    onPickAvatar(e) {
      const f = e.target.files?.[0] || null;
      this.avatarErr = ''; this.avatarOk = '';
      this.selectedFile = f;
      if (this.previewUrl) { try { URL.revokeObjectURL(this.previewUrl); } catch {} }
      this.previewUrl = f ? URL.createObjectURL(f) : '';
    },

    async uploadAvatar() {
      if (!this.selectedFile) return;
      this.avatarBusy = true; this.avatarErr = ''; this.avatarOk = '';

      const fd = new FormData();
      fd.append('image', this.selectedFile);

      const r = await app.api('/api/users/me/avatar/', { method: 'POST', body: fd });
      const d = await r.json().catch(() => ({}));
      this.avatarBusy = false;

      if (!r.ok) { this.avatarErr = d.detail || 'Błąd wysyłki'; return; }

      this.avatarOk = 'Zaktualizowano zdjęcie';
      await this.load();
      this.clearAvatarSelection();
    },

    async deleteAvatar() {
      this.avatarBusy = true; this.avatarErr = ''; this.avatarOk = '';
      const r = await app.api('/api/users/me/avatar/', { method: 'DELETE' });
      this.avatarBusy = false;
      if (!r.ok) { this.avatarErr = 'Błąd usuwania'; return; }
      await this.load();
      this.avatarOk = 'Usunięto zdjęcie';
      this.clearAvatarSelection();
    },

    clearAvatarSelection() {
      this.selectedFile = null;
      if (this.previewUrl) { try { URL.revokeObjectURL(this.previewUrl); } catch {} }
      this.previewUrl = '';
      if (this.$refs?.avatarInput) this.$refs.avatarInput.value = '';
    }
  }
};
