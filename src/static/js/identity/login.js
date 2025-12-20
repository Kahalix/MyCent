// static/js/identity/login.js
window.app = window.app || {};

app.loginForm = function () {
  return {
    email: '',
    password: '',
    busy: false,
    // inline errors
    emailErr: '',
    pwdErr: '',
    // błąd z backendu pod formularzem
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
        const r = await fetch('/api/auth/login/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          body: JSON.stringify({ email: this.email, password: this.password })
        });
        const d = await r.json().catch(() => ({}));

        if (!r.ok) {
          this.formErr = d?.detail || 'Błędne dane logowania';
          return;
        }

        if (d && d.access) localStorage.setItem('lown_access', d.access);

        // poinformuj resztę UI
        window.dispatchEvent(new CustomEvent('auth:changed', { detail: { authed: true } }));
        window.dispatchEvent(new Event('login:success'));

        // dokąd wrócić?
        let next =
          sessionStorage.getItem('post_login_redirect') ||
          new URLSearchParams(location.search).get('next') ||
          '/';

        try { sessionStorage.removeItem('post_login_redirect'); } catch {}

        app.toast.flashOk('Zalogowano pomyślnie');

        // replace = bez zaśmiecania historii (mniej duplikatów widoków przy cofaniu)
        window.location.replace(next);

      } catch (e) {
        this.formErr = 'Błąd sieci';
      } finally {
        this.busy = false;
      }
    }
  }
};

/* ========== Auto-confirm helper caller (BEZ console.log) ==========
   Jeśli URL zawiera ?confirm=<token>, wywołaj app.confirmRegistrationHelper()
   (funkcja jest zdefiniowana w auth.js). Pokazujemy tylko toast z wynikiem.
*/
(function () {
  document.addEventListener('DOMContentLoaded', async () => {
    try {
      if (!window.app || typeof app.confirmRegistrationHelper !== 'function') return;
      const params = app.urlParams && app.urlParams();
      const token = params ? params.get('confirm') : new URLSearchParams(location.search).get('confirm');
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
