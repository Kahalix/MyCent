// // Prosty helper do API z (opcjonalnym) JWT w localStorage
// function api(url, opts = {}) {
//   const token = localStorage.getItem('lown_access');
//   const headers = Object.assign(
//     { 'Accept': 'application/json' },
//     opts.headers || {},
//     token ? { 'Authorization': `Bearer ${token}` } : {}
//   );
//   return fetch(url, Object.assign({}, opts, { headers }));
// }
//
// // Globalny namespace dla Alpine
// window.app = {
//   // Motyw (dark/light)
//   themeState() {
//     return {
//       theme: localStorage.getItem('theme')
//         || (matchMedia('(prefers-color-scheme: dark)').matches ? 'lownDark' : 'lownLight'),
//       init() {
//         document.documentElement.setAttribute('data-theme', this.theme);
//       },
//       toggleTheme() {
//         this.theme = (this.theme === 'lownDark') ? 'lownLight' : 'lownDark';
//         document.documentElement.setAttribute('data-theme', this.theme);
//         localStorage.setItem('theme', this.theme);
//       }
//     }
//   },
//
//   // Nawigacja + auth
//   navState() {
//     return {
//       authed: !!localStorage.getItem('lown_access'),
//       theme: localStorage.getItem('theme')
//         || (matchMedia('(prefers-color-scheme: dark)').matches ? 'lownDark' : 'lownLight'),
//       init() {
//         // Aktualizuj stan po przeładowaniu fragmentów HTMX
//         document.addEventListener('htmx:afterSettle', () => {
//           this.authed = !!localStorage.getItem('lown_access');
//           this.theme = localStorage.getItem('theme') || this.theme;
//         });
//       },
//       toggleTheme() {
//         // delegacja do komponentu na <html> nie jest potrzebna — po prostu zmień globalnie
//         this.theme = (this.theme === 'lownDark') ? 'lownLight' : 'lownDark';
//         document.documentElement.setAttribute('data-theme', this.theme);
//         localStorage.setItem('theme', this.theme);
//       },
//       async logout() {
//         try { await api('/api/auth/logout/', { method: 'POST' }); } catch (e) {}
//         localStorage.removeItem('lown_access');
//         this.authed = false;
//         if (window.htmx) htmx.ajax('GET', '/', '#app-root', { pushURL: true });
//         else window.location.href = '/';
//       }
//     }
//   },
//
//   // Logowanie
//   loginForm() {
//     return {
//       email: '',
//       password: '',
//       busy: false,
//       err: '',
//       async submit() {
//         this.busy = true; this.err = '';
//         try {
//           const r = await fetch('/api/auth/login/', {
//             method: 'POST',
//             headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
//             body: JSON.stringify({ email: this.email, password: this.password })
//           });
//           const d = await r.json().catch(() => ({}));
//           this.busy = false;
//           if (!r.ok) { this.err = d.detail || 'Błąd logowania'; return; }
//           localStorage.setItem('lown_access', d.access);
//           if (window.htmx) htmx.ajax('GET', '/profile', '#app-root', { pushURL: true });
//           else window.location.href = '/profile';
//         } catch (e) {
//           this.busy = false; this.err = 'Błąd sieci';
//         }
//       }
//     }
//   },
//
//   // Profil
//   profileView() {
//     return {
//       me: null,
//       busy: false,
//       err: '',
//       okMsg: '',
//       async load() {
//         const r = await api('/api/users/me/');
//         if (!r.ok) { this.err = 'Nie zalogowano'; return; }
//         this.me = await r.json();
//       },
//       async save() {
//         this.busy = true; this.err = ''; this.okMsg = '';
//         const r = await api('/api/users/me/', {
//           method: 'PATCH',
//           headers: { 'Content-Type': 'application/json' },
//           body: JSON.stringify({
//             first_name: this.me.first_name || '',
//             last_name: this.me.last_name || '',
//             phone_number: this.me.phone_number || ''
//           })
//         });
//         const d = await r.json().catch(() => ({}));
//         this.busy = false;
//         if (!r.ok) { this.err = d.detail || 'Błąd zapisu'; return; }
//         this.okMsg = 'Zapisano';
//       },
//       async uploadAvatar(file) {
//         if (!file) return;
//         const fd = new FormData(); fd.append('image', file);
//         const r = await api('/api/users/me/avatar/', { method: 'POST', body: fd });
//         const d = await r.json().catch(() => ({}));
//         if (!r.ok) { this.err = d.detail || 'Błąd wysyłki'; return; }
//         await this.load();
//       },
//       async deleteAvatar() {
//         const r = await api('/api/users/me/avatar/', { method: 'DELETE' });
//         if (!r.ok) { this.err = 'Błąd usuwania'; return; }
//         await this.load();
//       }
//     }
//   }
// };
