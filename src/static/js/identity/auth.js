window.app = window.app || {};

app._apiErr = async (r) => {
  try {
    const d = await r.clone().json();
    if (d?.detail) return typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail);
    if (d && typeof d === 'object') {
      const parts = [];
      for (const [k, v] of Object.entries(d)) {
        if (Array.isArray(v)) parts.push(`${k}: ${v.join(', ')}`);
        else if (typeof v === 'string') parts.push(`${k}: ${v}`);
      }
      if (parts.length) return parts.join(' • ');
    }
  } catch {}
  return `Błąd (${r.status})`;
};

app.loginForm = function () {
  return {
    email: '',
    password: '',
    busy: false,
    err: '',
    emailErr: '',
    pwdErr: '',

    _clearErrors() { this.err = this.emailErr = this.pwdErr = ''; },
    _validEmail(v) { return /^\S+@\S+\.\S+$/.test(v || ''); },

    _validate() {
      this._clearErrors();
      let ok = true;
      if (!this._validEmail(this.email)) { this.emailErr = 'Wpisz poprawny adres e-mail'; ok = false; }
      if (!this.password) { this.pwdErr = 'Podaj hasło'; ok = false; }
      return ok;
    },

    async submit() {
      if (!this._validate()) return;
      this.busy = true;
      try {
        if (typeof app.ensureCsrfCookie === 'function') {
          await app.ensureCsrfCookie();
        }
        const r = await app.api('/api/auth/login/', {
          method: 'POST',
          body: JSON.stringify({ email: this.email, password: this.password })
        });
        if (!r.ok) {
          this.err = await app._apiErr(r);
          return;
        }

        try { await app.ensureAuthed(); } catch {}
        try { window.dispatchEvent(new CustomEvent('auth:changed', { detail: { authed: true } })); } catch {}

        let next = '/';
        try {
          const saved = sessionStorage.getItem('post_login_redirect');
          if (saved) next = saved;
          sessionStorage.removeItem('post_login_redirect');
        } catch {}

        app.goto(next);
      } catch {
        this.err = 'Błąd sieci';
      } finally {
        this.busy = false;
      }
    }
  };
};

app.registerForm = function () {
  return {
    email:'', first_name:'', last_name:'', password:'',
    busy:false,
    emailErr:'', firstErr:'', lastErr:'', pwdErr:'',
    formErr:'', ok:'',

    _clearErrors(){ this.emailErr=this.firstErr=this.lastErr=this.pwdErr=this.formErr=''; },
    _validEmail(v){ return /^\S+@\S+\.\S+$/.test(v || ''); },

    _validate(){
      this._clearErrors();
      let ok = true;
      if (!this._validEmail(this.email)) { this.emailErr = 'Wpisz poprawny adres e-mail'; ok = false; }
      if (!this.first_name?.trim())      { this.firstErr = 'Podaj imię'; ok = false; }
      if (!this.last_name?.trim())       { this.lastErr  = 'Podaj nazwisko'; ok = false; }
      if (!this.password || this.password.length < 10) { this.pwdErr = 'Hasło min. 10 znaków'; ok = false; }
      return ok;
    },

    async submit(){
      if (!this._validate()) return;
      this.busy = true; this.ok = ''; this.formErr = '';
      try {
        if (typeof app.ensureCsrfCookie === 'function') {
          await app.ensureCsrfCookie();
        }
        const r = await app.api('/api/auth/register/', {
          method: 'POST',
          body: JSON.stringify({
            email: this.email,
            first_name: this.first_name,
            last_name: this.last_name,
            password: this.password
          })
        });
        if (!r.ok) {
          this.formErr = await app._apiErr(r);
          return;
        }
        const d = await r.json().catch(() => ({}));
        app.toast.flashOk(d.message || 'Rejestracja udana. Sprawdź e-mail, aby aktywować konto.');
        app.goto('/login');
      } catch {
        this.formErr = 'Błąd sieci';
      } finally {
        this.busy = false;
      }
    }
  };
};

app.confirmRegistrationHelper = async function () {
  const t = (window.app.urlParams && app.urlParams().get('confirm')) || null;
  if (!t) return null;
  try {
    if (typeof app.ensureCsrfCookie === 'function') {
      await app.ensureCsrfCookie();
    }
    const r = await app.api('/api/auth/confirm-registration/', {
      method: 'POST',
      body: JSON.stringify({ token: t })
    });
    if (!r.ok) throw new Error(await app._apiErr(r));
    return 'Konto aktywowane. Możesz się zalogować.';
  } catch (e) {
    return e?.message || 'Nie udało się potwierdzić rejestracji.';
  }
};

app.forgotForm = function () {
  return {
    email:'', busy:false, err:'',
    _validEmail(v){ return /^\S+@\S+\.\S+$/.test(v || ''); },
    async submit() {
      if (!this._validEmail(this.email)) { app.error('Wpisz poprawny adres e-mail.'); return; }
      this.busy = true; this.err='';
      try {
        if (typeof app.ensureCsrfCookie === 'function') {
          await app.ensureCsrfCookie();
        }
        const r = await app.api('/api/auth/forgot-password/', {
          method:'POST', body: JSON.stringify({ email: this.email })
        });
        const d = await app.readJson(r);
        if (!r.ok) {
          const m = app.errText(d) || 'Nie udało się wysłać wiadomości';
          this.err = m; app.error(m);
        } else {
          app.toast.ok('Jeśli konto istnieje, wysłaliśmy link do resetu hasła.');
          app.goto('/login');
        }
      } catch {
        this.err='Błąd sieci'; app.error(this.err);
      } finally {
        this.busy=false;
      }
    }
  };
};

app.resetForm = function () {
  return {
    token:'', new_password:'', new_password2:'',
    busy:false, ok:'', err:'',

    init(){ this.token = (window.app.urlParams && app.urlParams().get('token')) || ''; },

    async submit(){
      this.busy = true; this.ok=''; this.err='';
      if (!this.token) { this.err = 'Brak tokenu.'; this.busy=false; return; }
      if (this.new_password !== this.new_password2) {
        this.err = 'Hasła muszą być identyczne.'; this.busy = false; return;
      }
      try {
        if (typeof app.ensureCsrfCookie === 'function') {
          await app.ensureCsrfCookie();
        }
        const r = await app.api('/api/auth/reset-password/', {
          method: 'POST',
          body: JSON.stringify({ token: this.token, new_password: this.new_password })
        });
        if (!r.ok) { this.err = await app._apiErr(r); return; }
        const d = await r.json().catch(() => ({}));
        this.ok = d.message || 'Hasło ustawione. Zaloguj się.';
      } catch {
        this.err = 'Błąd sieci';
      } finally {
        this.busy = false;
      }
    }
  };
};

app.changeEmailForm = function () {
  return {
    new_email:'', busy:false, ok:'', err:'', emailErr:'',
    _validEmail(v){ return /^\S+@\S+\.\S+$/.test(v || ''); },

    async submit(){
      this.ok=''; this.err=''; this.emailErr=''; this.busy = true;
      if (!this._validEmail(this.new_email)) { this.emailErr='Wpisz poprawny e-mail'; this.busy=false; return; }
      try {
        if (typeof app.ensureCsrfCookie === 'function') {
          await app.ensureCsrfCookie();
        }
        const r = await app.api('/api/auth/change-email/', {
          method: 'POST',
          body: JSON.stringify({ new_email: this.new_email })
        });
        if (!r.ok) { this.err = await app._apiErr(r); return; }
        const d = await r.json().catch(() => ({}));
        this.ok = d.message || 'Sprawdź nową skrzynkę i kliknij link.';
      } catch {
        this.err = 'Błąd sieci';
      } finally {
        this.busy = false;
      }
    }
  };
};

app.confirmEmailChangeView = function () {
  return {
    state:'loading', msg:'', err:'',
    async init(){
      const token = (window.app.urlParams && app.urlParams().get('token')) || '';
      if (!token) { this.state='done'; this.err='Brak tokenu.'; return; }
      try {
        if (typeof app.ensureCsrfCookie === 'function') {
          await app.ensureCsrfCookie();
        }
        const r = await app.api('/api/auth/confirm-email-change/', {
          method: 'POST',
          body: JSON.stringify({ token })
        });
        if (!r.ok) throw new Error(await app._apiErr(r));
        const d = await r.json().catch(() => ({}));
        this.msg = d.message || 'E-mail zmieniony.';
      } catch(e){
        this.err = e?.message || 'Błąd potwierdzania.';
      } finally {
        this.state = 'done';
      }
    }
  };
};

app.changePasswordForm = function () {
  return {
    old_password:'', new_password:'', new_password2:'',
    busy:false, ok:'', err:'',
    show_old:false, show_n1:false, show_n2:false,

    get weak(){ return (this.new_password || '').length > 0 && this.new_password.length < 10; },

    async submit(){
      this.busy = true; this.ok=''; this.err='';
      if (this.new_password !== this.new_password2) {
        this.err = 'Hasła muszą być identyczne.'; this.busy=false; return;
      }
      try {
        if (typeof app.ensureCsrfCookie === 'function') {
          await app.ensureCsrfCookie();
        }
        const r = await app.api('/api/auth/change-password/', {
          method: 'POST',
          body: JSON.stringify({ old_password: this.old_password, new_password: this.new_password })
        });
        if (!r.ok) { this.err = await app._apiErr(r); return; }
        const d = await r.json().catch(() => ({}));
        this.ok = d.message || 'Hasło zmienione.';
        app.toast.flashOk('Hasło zmienione. Zaloguj się ponownie.');
        app._onSignedOut({ redirect: true });
      } catch {
        this.err = 'Błąd sieci';
      } finally {
        this.busy=false;
      }
    }
  };
};

app.logout = async function () {
  try {
    if (typeof app.ensureCsrfCookie === 'function') {
      await app.ensureCsrfCookie();
    }
    await app.api('/api/auth/logout/', { method: 'POST', silent: true, autoToast: false });
  } catch {}
  try { app.toast.flashOk('Wylogowano'); } catch {}
  app._onSignedOut({ redirect: true });
};
