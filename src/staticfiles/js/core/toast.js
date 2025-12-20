// static/js/core/toast.js
window.app = window.app || {};

(function bootstrapToasts(){
  if (window.__APP_TOASTS_BOOTSTRAPPED__) return;
  window.__APP_TOASTS_BOOTSTRAPPED__ = true;

  // Kolejka na toasty zanim Alpine podniesie komponent
  window.__app_toasts_queue = window.__app_toasts_queue || [];

  // ---- Publiczne API
  app.toast = {
    _push(payload){
      const el = document.getElementById('toasts') || document.querySelector('[data-app-toasts]');
      const api = el && el.__app_toasts_api;
      if (api && typeof api.push === 'function') {
        api.push(payload.message || '', payload.type || 'info', payload.timeout);
      } else {
        window.__app_toasts_queue.push({
          message: String(payload.message || ''),
          type: payload.type || 'info',
          timeout: Number.isFinite(payload.timeout) ? payload.timeout : undefined
        });
      }
    },
    show(message, opts = {}) { this._push({ message: String(message || ''), ...opts }); },
    ok(message, opts = {})   { this._push({ message, type: 'success', ...opts }); },
    err(message, opts = {})  { this._push({ message, type: 'error',   ...opts }); },
    info(message, opts = {}) { this._push({ message, type: 'info',    ...opts }); },
    warn(message, opts = {}) { this._push({ message, type: 'warning', ...opts }); },

    // Parsuje DRF {detail / field:[]}
    fromResponse: async function(resp, fallback) {
      let d = {};
      try { d = await resp.clone().json(); } catch {}
      const txt = (window.app?.errText ? window.app.errText(d) : (d?.detail || fallback)) || `Błąd (${resp.status})`;
      this.err(txt);
    },

    // Flash – pokaż po nast. przeładowaniu
    flash(type, message, timeout) {
      try {
        sessionStorage.setItem('app_flash_toast', JSON.stringify({
          type: type || 'info',
          message: String(message || ''),
          timeout: Number.isFinite(timeout) ? timeout : undefined
        }));
      } catch {}
    },
    flashOk(message, timeout)  { this.flash('success', message, timeout); },
    flashErr(message, timeout) { this.flash('error',   message, timeout); },
    flashInfo(message, timeout){ this.flash('info',    message, timeout); },
    flashWarn(message, timeout){ this.flash('warning', message, timeout); },
  };

  // ---- Komponent Alpine (kontener w base.html)
  app.toasts = function () {
    return {
      items: [],
      counter: 0,

      init() {
        // Ujawnij API komponentu (dla app.toast)
        this.$root.__app_toasts_api = this;

        // Opróżnij kolejkę z czasu przed inicjalizacją
        const q = window.__app_toasts_queue || [];
        while (q.length) {
          const p = q.shift();
          this.push(p.message, p.type, p.timeout);
        }

        // Rejestrujemy JEDEN globalny listener.
        if (!window.__app_toasts_event_listener__) {
          window.addEventListener('toast:show', (e) => {
            const { message, type = 'info', timeout } = e.detail || {};
            this.push(String(message || ''), type, timeout);
          });
          window.__app_toasts_event_listener__ = true;
        }

        // Flash po przeładowaniu
        try {
          const raw = sessionStorage.getItem('app_flash_toast');
          if (raw) {
            sessionStorage.removeItem('app_flash_toast');
            const f = JSON.parse(raw);
            if (f?.message) this.push(f.message, f.type || 'info', f.timeout);
          }
        } catch {}
      },

      push(message, type = 'info', timeout) {
        const id = ++this.counter;
        const ms = Number.isFinite(timeout) ? timeout : (type === 'error' ? 6000 : 4000);
        const t = {
          id,
          message: String(message || ''),
          type,
          show: true,
          timeout: ms,
          remaining: ms,
          timer: null,
          started: Date.now(),
          paused: false
        };
        this.items.push(t);
        this._start(t);
      },

      _start(t) { this._clearTimer(t); t.started = Date.now(); t.timer = setTimeout(() => this.close(t.id), t.remaining); },
      _clearTimer(t) { if (t.timer) { clearTimeout(t.timer); t.timer = null; } },
      pause(t) { if (!t || t.paused) return; t.paused = true; t.remaining -= (Date.now() - t.started); this._clearTimer(t); },
      resume(t) { if (!t || !t.paused) return; t.paused = false; this._start(t); },

      close(id) {
        const i = this.items.findIndex(x => x.id === id);
        if (i > -1) {
          const t = this.items[i];
          this._clearTimer(t);
          t.show = false;
          setTimeout(() => { this.items.splice(i, 1); }, 180);
        }
      },

      // style helpers
      role(t) { return t.type === 'error' ? 'alert' : 'status'; },
      aria(t) { return t.type === 'error' ? 'assertive' : 'polite'; }
    };
  };
})();
