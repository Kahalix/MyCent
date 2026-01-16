window.app = window.app || {};

app.loginForm = function () {
  return {
    email: '',
    password: '',
    busy: false,
    emailErr: '',
    pwdErr: '',
    formErr: '',

    _validEmail(v) { return /^\S+@\S+\.\S+$/.test(v || ''); },
    _clear() { this.emailErr=''; this.pwdErr=''; this.formErr=''; },

    _validate() {
      this._clear();
      let ok = true;
      if (!this._validEmail(this.email)) { this.emailErr = 'Wpisz poprawny adres e-mail'; ok = false; }
      if (!this.password) { this.pwdErr = 'Podaj hasło'; ok = false; }
      return ok;
    },

    async submit () {
      if (!this._validate()) return;
      this.busy = true; this.formErr = '';

      try {
        if (typeof app.ensureCsrfCookie === 'function') {
          await app.ensureCsrfCookie();
        }

        const r = await app.api('/api/auth/login/', {
          method: 'POST',
          body: JSON.stringify({ email: this.email, password: this.password }),
          silent: true,
          autoToast: false
        });

        const d = await r.json().catch(() => ({}));

        if (!r.ok) {
          this.formErr = (d?.detail && String(d.detail)) || 'Błędne dane logowania';
          return;
        }

        try { await app.ensureAuthed(); } catch {}
        try { window.dispatchEvent(new CustomEvent('auth:changed', { detail: { authed: true } })); } catch {}

        let next =
          sessionStorage.getItem('post_login_redirect') ||
          new URLSearchParams(location.search).get('next') ||
          '/';

        try { sessionStorage.removeItem('post_login_redirect'); } catch {}
        try { app.toast.flashOk('Zalogowano pomyślnie'); } catch {}

        window.location.replace(next);

      } catch {
        this.formErr = 'Błąd sieci';
      } finally {
        this.busy = false;
      }
    }
  }
};

(function () {
  document.addEventListener('DOMContentLoaded', async () => {
    try {
      if (!window.app || typeof app.confirmRegistrationHelper !== 'function') return;
      const params = (app.urlParams && app.urlParams()) || new URLSearchParams(location.search);
      const token = params.get('confirm');
      if (!token) return;

      const msg = await app.confirmRegistrationHelper();
      if (msg) {
        try { app.toast.ok(msg); } catch {}
      }
    } catch (e) {
      try { app.toast.err(e?.message || 'Błąd potwierdzania'); } catch {}
    }
  });
})();
