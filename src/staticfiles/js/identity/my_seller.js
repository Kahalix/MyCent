window.app = window.app || {};

app.mySeller = function () {
  return {
    tab: 'overview',
    perms: { overview:false, data:false, graphics:false, accounts:false, members:false, offers:false },
    can(t){ return !!this.perms[t]; },
    setTab(t) { this.tab = t },

    memberLookupQuery: '',
    memberLookupResults: [],
    lookupBusy: false,

    memberQuery: '',

    loading: true,
    busy: false,
    imgBusy: false,
    err: '',
    ok: '',
    imgErr: '',
    imgOk: '',
    seller: null,

    form: {
      company_name: '',
      slug: '',
      description: '',
      contact_email: '',
      contact_phone: '',
      website_url: ''
    },

    accounts: [],
    accBusy: false,
    accErr: '',
    accOk: '',
    accForm: { iban: '', bank_name: '', account_holder: '', is_default: false },

    roles: ['OWNER','MANAGER','MODERATOR','EMPLOYEE'],
    roleLabels: {
      OWNER: 'Właściciel',
      MANAGER: 'Menedżer',
      MODERATOR: 'Moderator',
      EMPLOYEE: 'Pracownik'
    },
    roleLabel(r) { return this.roleLabels[r] || r || '—'; },
    isOwner(m) { return (m?.role === 'OWNER'); },
    memberKey(m, idx) { return m?.public_id || m?.user_public_id || idx; },

    members: [],
    membersPage: 1,
    membersHasNext: false,
    membersHasPrev: false,
    membersTotal: 0,
    membersBusy: false,
    membersErr: '',
    membersOk: '',
    memberForm: { email: '', user_public_id: '', role: 'EMPLOYEE' },

    _ensureArray(d) {
      if (Array.isArray(d)) return d;
      if (d && Array.isArray(d.results)) return d.results;
      return [];
    },

    _fmtErr(d) {
      if (!d) return 'Wystąpił błąd';
      if (typeof d === 'string') return d;
      if (d.detail) return String(d.detail);
      if (Array.isArray(d.non_field_errors) && d.non_field_errors.length) {
        return d.non_field_errors.join('\n');
      }
      const keys = Object.keys(d);
      if (keys.length) {
        const v = d[keys[0]];
        if (Array.isArray(v)) return v.map(x => String(x)).join('\n');
        if (v && typeof v === 'object') {
          const inner = Object.values(v).flat();
          if (inner.length) return inner.map(x => String(x)).join('\n');
        }
        if (typeof v === 'string') return v;
      }
      return 'Wystąpił błąd';
    },

    async load() {
      this.loading = true; this.err = '';
      try {
        let ctx = null;
        try {
          const rc = await app.api('/api/sellers/context/');
          if (rc.ok) {
            ctx = await rc.json();
            const allowed = Array.isArray(ctx?.allowed_tabs) ? ctx.allowed_tabs : [];
            this.perms = { overview:false, data:false, graphics:false, accounts:false, members:false, offers:false };
            for (const k of allowed) this.perms[k] = true;
          }
        } catch {}

        if (ctx?.role === 'OWNER') {
          const r = await app.api('/api/sellers/mine/');
          if (r.ok) {
            this.seller = await r.json();
          } else if (r.status !== 404) {
            const d = await app.readJson(r);
            this.err = this._fmtErr(d);
            if (this.err) app.error(this.err);
          }
        } else if (ctx?.seller_slug) {
          const r = await app.api(`/api/public/sellers/${encodeURIComponent(ctx.seller_slug)}/`);
          if (r.ok) {
            this.seller = await r.json();
          }
        }

        const proms = [];
        if (this.can('accounts')) proms.push(this.loadAccounts());
        if (this.can('members'))  proms.push(this.loadMembers(1));
        await Promise.all(proms);
      } catch {
        this.err = 'Błąd sieci';
        app.error(this.err);
      }
      this.loading = false;
    },

    async create() {
      this.busy = true; this.err = ''; this.ok = '';
      try {
        const payload = { ...this.form, slug: (this.form.slug || '').trim().toLowerCase() };
        const r = await app.api('/api/sellers/mine/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const d = await app.readJson(r);
        if (!r.ok) throw new Error(this._fmtErr(d));
        this.seller = d;
        this.ok = 'Utworzono profil';
        app.ok(this.ok);
        await Promise.all([this.loadAccounts(), this.loadMembers(1)]);
        window.dispatchEvent(new CustomEvent('auth:changed', { detail: { authed: true } }));
      } catch (e) {
        this.err = e.message || 'Błąd tworzenia';
        app.error(this.err);
      } finally {
        this.busy = false;
      }
    },

    async update() {
      if (!this.seller) return;
      this.busy = true; this.err = ''; this.ok = '';
      try {
        const r = await app.api('/api/sellers/mine/', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            company_name: this.seller.company_name,
            description: this.seller.description,
            contact_email: this.seller.contact_email,
            contact_phone: this.seller.contact_phone,
            website_url: this.seller.website_url
          })
        });
        const d = await app.readJson(r);
        if (!r.ok) throw new Error(this._fmtErr(d));
        this.ok = 'Zapisano';
        app.ok(this.ok);
      } catch (e) {
        this.err = e.message || 'Błąd zapisu';
        app.error(this.err);
      } finally {
        this.busy = false;
      }
    },

    async searchCandidates() {
      if (!this.seller) return;
      const q = (this.memberLookupQuery || '').trim();
      if (q.length < 2) { this.memberLookupResults = []; return; }
      this.lookupBusy = true;
      try {
        const r = await app.api(`/api/sellers/${this.seller.public_id}/members/candidates/?search=${encodeURIComponent(q)}&role=EMPLOYEE`);
        const d = await app.readJson(r);
        this.memberLookupResults = this._ensureArray(d);
      } catch {
        this.memberLookupResults = [];
      } finally {
        this.lookupBusy = false;
      }
    },

    selectCandidate(u) {
      this.memberForm.user_public_id = u.public_id;
      this.memberForm.email = '';
      const name = [u.first_name||'', u.last_name||''].join(' ').trim();
      this.memberLookupQuery = `${name ? name+' ' : ''}<${u.email}>`;
      this.memberLookupResults = [];
    },

    async addCandidate(u) {
      if (!this.seller || !u?.public_id) return;
      this.membersBusy = true; this.membersErr=''; this.membersOk='';
      try {
        const r = await app.api(`/api/sellers/${this.seller.public_id}/members/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_public_id: u.public_id, role: this.memberForm.role || 'EMPLOYEE' })
        });
        const d = await app.readJson(r);
        if (!r.ok) throw new Error(this._fmtErr(d));
        this.membersOk = 'Dodano członka';
        app.ok(this.membersOk);
        this.memberLookupResults = [];
        this.memberLookupQuery = '';
        await this.loadMembers(1);
      } catch (e) {
        this.membersErr = e.message || 'Błąd dodawania';
        app.error(this.membersErr);
      } finally {
        this.membersBusy = false;
      }
    },

    async loadAccounts() {
      if (!this.seller) { this.accounts = []; return; }
      try {
        const url = `/api/sellers/mine/bank-accounts?seller_public_id=${encodeURIComponent(this.seller.public_id)}`;
        const r = await app.api(url);
        const d = await app.readJson(r);
        const list = this._ensureArray(d);
        this.accounts = list.map(a => a ? ({
          ...a,
          _edit_bank_name: a.bank_name || '',
          _edit_account_holder: a.account_holder || ''
        }) : a).filter(Boolean);
      } catch {
        this.accounts = [];
      }
    },

    async createAccount() {
      if (!this.seller) return;
      this.accBusy = true; this.accErr = ''; this.accOk = '';
      try {
        const payload = { ...this.accForm, seller_public_id: this.seller.public_id };
        const r = await app.api('/api/sellers/mine/bank-accounts/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const d = await app.readJson(r);
        if (!r.ok) throw new Error(this._fmtErr(d));
        this.accOk = 'Dodano konto';
        app.ok(this.accOk);
        this.accForm = { iban: '', bank_name: '', account_holder: '', is_default: false };
        await this.loadAccounts();
      } catch (e) {
        this.accErr = e.message || 'Błąd dodawania';
        app.error(this.accErr);
      } finally {
        this.accBusy = false;
      }
    },

    async updateAccount(public_id, changes) {
      this.accBusy = true; this.accErr = ''; this.accOk = '';
      try {
        const r = await app.api(`/api/sellers/mine/bank-accounts/${public_id}/`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(changes || {})
        });
        const d = await app.readJson(r);
        if (!r.ok) throw new Error(this._fmtErr(d));
        this.accOk = 'Zapisano';
        app.ok(this.accOk);
        await this.loadAccounts();
      } catch (e) {
        this.accErr = e.message || 'Błąd zapisu';
        app.error(this.accErr);
      } finally {
        this.accBusy = false;
      }
    },

    async setDefaultAccount(public_id) {
      this.accBusy = true; this.accErr = ''; this.accOk = '';
      try {
        const r = await app.api(`/api/sellers/mine/bank-accounts/${public_id}/set-default/`, { method: 'POST' });
        const d = await app.readJson(r);
        if (!r.ok) throw new Error(this._fmtErr(d));
        this.accOk = 'Ustawiono jako domyślne';
        app.ok(this.accOk);
        await this.loadAccounts();
      } catch (e) {
        this.accErr = e.message || 'Błąd operacji';
        app.error(this.accErr);
      } finally {
        this.accBusy = false;
      }
    },

    async deleteAccount(public_id) {
      this.accBusy = true; this.accErr = ''; this.accOk = '';
      try {
        const r = await app.api(`/api/sellers/mine/bank-accounts/${public_id}/`, { method: 'DELETE' });
        if (!r.ok && r.status !== 204) {
          const d = await app.readJson(r);
          throw new Error(this._fmtErr(d));
        }
        this.accOk = 'Usunięto konto';
        app.ok(this.accOk);
        await this.loadAccounts();
      } catch (e) {
        this.accErr = e.message || 'Błąd usuwania';
        app.error(this.accErr);
      } finally {
        this.accBusy = false;
      }
    },

    async loadMembers(page = null) {
      if (!this.seller) { this.members = []; return; }
      if (page) this.membersPage = page;
      try {
        const params = new URLSearchParams();
        if ((this.memberQuery || '').trim()) params.set('search', this.memberQuery.trim());
        params.set('page', this.membersPage);
        const r = await app.api(`/api/sellers/${this.seller.public_id}/members/?` + params.toString());
        const d = await app.readJson(r);
        const list = this._ensureArray(d).filter(Boolean);
        this.members = list;
        this.membersHasNext = Boolean(d?.next);
        this.membersHasPrev = Boolean(d?.previous);
        this.membersTotal   = Number.isFinite(d?.count) ? d.count : list.length;
      } catch {
        this.members = [];
        this.membersHasNext = this.membersHasPrev = false;
        this.membersTotal = 0;
      }
    },
    nextMembers(){ if (this.membersHasNext) this.loadMembers(this.membersPage + 1); },
    prevMembers(){ if (this.membersHasPrev) this.loadMembers(this.membersPage - 1); },

    handleRoleChange(m, newRole) {
      const prev = m._roleBefore ?? m.role;
      const role = (newRole === 'OWNER') ? 'MANAGER' : newRole;
      this.changeMemberRole(m.public_id, role, m, prev);
    },

    async changeMemberRole(member_public_id, role, mRef = null, prevRole = null) {
      if (!this.seller) return;
      this.membersBusy = true; this.membersErr = ''; this.membersOk = '';
      try {
        const r = await app.api(`/api/sellers/${this.seller.public_id}/members/${member_public_id}/`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role })
        });
        const d = await app.readJson(r);
        if (!r.ok) {
          if (mRef && prevRole != null) mRef.role = prevRole;
          throw new Error(this._fmtErr(d));
        }
        this.membersOk = 'Zmieniono rolę';
        app.ok(this.membersOk);
      } catch (e) {
        if (mRef && prevRole != null) mRef.role = prevRole;
        this.membersErr = e.message || 'Błąd zmiany roli';
        app.error(this.membersErr);
      } finally {
        this.membersBusy = false;
      }
    },

    async addMember() {
      if (!this.seller) return;
      this.membersBusy = true; this.membersErr = ''; this.membersOk = '';
      try {
        const role = (this.memberForm.role === 'OWNER') ? 'MANAGER' : this.memberForm.role;
        const payload = {
          email: (this.memberForm.email || '').trim() || undefined,
          user_public_id: (this.memberForm.user_public_id || '').trim() || undefined,
          role
        };
        const r = await app.api(`/api/sellers/${this.seller.public_id}/members/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const d = await app.readJson(r);
        if (!r.ok) throw new Error(this._fmtErr(d));
        this.membersOk = 'Dodano członka';
        app.ok(this.membersOk);
        this.memberForm = { email: '', user_public_id: '', role: 'EMPLOYEE' };
        await this.loadMembers(1);
      } catch (e) {
        this.membersErr = e.message || 'Błąd dodawania';
        app.error(this.membersErr);
      } finally {
        this.membersBusy = false;
      }
    },

    async removeMember(member_public_id) {
      if (!this.seller) return;
      this.membersBusy = true; this.membersErr = ''; this.membersOk = '';
      try {
        const r = await app.api(`/api/sellers/${this.seller.public_id}/members/${member_public_id}/`, { method: 'DELETE' });
        if (!r.ok && r.status !== 204) {
          const d = await app.readJson(r);
          throw new Error(this._fmtErr(d));
        }
        this.membersOk = 'Usunięto członka';
        app.ok(this.membersOk);
        await this.loadMembers(this.membersPage);
      } catch (e) {
        this.membersErr = e.message || 'Błąd usuwania';
        app.error(this.membersErr);
      } finally {
        this.membersBusy = false;
      }
    },

    async uploadLogo() {
      const file = this.$refs.logoInput?.files?.[0];
      if (!file) return;
      this.imgBusy = true; this.imgErr=''; this.imgOk='';
      const fd = new FormData(); fd.append('logo', file);
      try {
        const r = await app.api('/api/sellers/mine/logo/', { method: 'POST', body: fd });
        const d = await app.readJson(r);
        if (!r.ok) throw new Error(this._fmtErr(d));
        this.seller.logo_image = d.logo_url;
        this.imgOk = 'Zmieniono logo';
        app.ok(this.imgOk);
      } catch (e) {
        this.imgErr = e.message || 'Błąd uploadu';
        app.error(this.imgErr);
      } finally {
        this.imgBusy = false;
        if (this.$refs.logoInput) this.$refs.logoInput.value = '';
      }
    },

    async uploadBanner() {
      const file = this.$refs.bannerInput?.files?.[0];
      if (!file) return;
      this.imgBusy = true; this.imgErr=''; this.imgOk='';
      const fd = new FormData(); fd.append('banner', file);
      try {
        const r = await app.api('/api/sellers/mine/banner/', { method: 'POST', body: fd });
        const d = await app.readJson(r);
        if (!r.ok) throw new Error(this._fmtErr(d));
        this.seller.banner_image = d.banner_url;
        this.imgOk = 'Zmieniono banner';
        app.ok(this.imgOk);
      } catch (e) {
        this.imgErr = e.message || 'Błąd uploadu';
        app.error(this.imgErr);
      } finally {
        this.imgBusy = false;
        if (this.$refs.bannerInput) this.$refs.bannerInput.value = '';
      }
    }
  };
};
