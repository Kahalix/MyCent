from __future__ import annotations

import os
import random
import string
from datetime import date, timedelta

import gevent
from locust import HttpUser, task, between
from locust.exception import StopUser

NUM_PERF_USERS = 500

ACCESS_COOKIE_NAME = os.getenv("ACCESS_COOKIE_NAME", "access_token")
AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "refresh_token")
CSRF_COOKIE_NAME = os.getenv("CSRF_COOKIE_NAME", "csrftoken")


def _pick_results(payload):
    if isinstance(payload, dict) and "results" in payload:
        return payload.get("results") or []
    if isinstance(payload, list):
        return payload
    return []


def _merge_unique(dst: list[str], src: list[str], limit: int = 5000) -> list[str]:
    if not src:
        return dst
    s = set(dst)
    for x in src:
        if x and x not in s:
            dst.append(x)
            s.add(x)
            if len(dst) >= limit:
                break
    return dst


class TestUser(HttpUser):
    wait_time = between(0.3, 1.5)

    item_ids: list[str] = []
    slug_ids: list[str] = []
    buyable_ids: list[str] = []

    def on_start(self):
        self.pawn_ids: list[str] = []
        self.pick_credentials()
        gevent.sleep(random.uniform(0.0, 3.0))
        self.login()

    def pick_credentials(self):
        idx = random.randint(1, NUM_PERF_USERS)
        self.email = f"perfuser{idx:04d}@example.com"
        self.password = "PerfPass123!"

    def _origin(self) -> str:
        return (self.host or "").rstrip("/")

    def _sync_csrf_headers(self):
        token = self.client.cookies.get(CSRF_COOKIE_NAME)
        origin = self._origin()
        hdrs = {}
        if token:
            hdrs["X-CSRFToken"] = token
        if origin:
            hdrs["Origin"] = origin
            hdrs["Referer"] = f"{origin}/"
        if hdrs:
            self.client.headers.update(hdrs)

    def ensure_csrf_cookie(self):
        resp = self.client.get("/api/auth/csrf/", name="/api/auth/csrf/")
        if resp.status_code not in (200, 204):
            raise StopUser(f"csrf bootstrap failed {resp.status_code}")
        self._sync_csrf_headers()
        if not self.client.cookies.get(CSRF_COOKIE_NAME):
            raise StopUser("no csrftoken cookie after /api/auth/csrf/")

    def login(self):
        payload = {"email": self.email, "password": self.password}

        for _ in range(6):
            resp = self.client.post("/api/auth/login/", json=payload, name="/api/auth/login/")
            if resp.status_code == 200:
                break
            if resp.status_code == 429:
                gevent.sleep(random.uniform(0.5, 2.0))
                continue
            raise StopUser(f"login failed {resp.status_code}")

        if resp.status_code != 200:
            raise StopUser(f"login failed {resp.status_code}")

        if not self.client.cookies.get(ACCESS_COOKIE_NAME):
            raise StopUser(f"no {ACCESS_COOKIE_NAME} cookie after login")
        if not self.client.cookies.get(AUTH_COOKIE_NAME):
            raise StopUser(f"no {AUTH_COOKIE_NAME} cookie after login")

        if not self.client.cookies.get(CSRF_COOKIE_NAME):
            self.ensure_csrf_cookie()
        else:
            self._sync_csrf_headers()

    def random_filters(self) -> dict:
        scenarios = [
            {},
            {"search": "perf"},
            {"status": "AVAILABLE"},
            {"price_min": 100, "price_max": 1000},
            {"allow_online_checkout": "true"},
        ]
        base = random.choice(scenarios).copy()
        if "price_min" in base and "price_max" in base:
            lo = random.choice([0, 50, 100])
            hi = random.choice([200, 500, 1000, 1500])
            if lo > hi:
                lo, hi = hi, lo
            base["price_min"] = lo
            base["price_max"] = hi
        return base

    def random_pawn_filters(self) -> dict:
        scenarios = [
            {},
            {"status": "ACTIVE"},
            {"status": "REDEEMED"},
            {"status": "FORFEITED"},
            {"search": "example.com"},
            {
                "due_from": (date.today() - timedelta(days=60)).isoformat(),
                "due_to": (date.today() + timedelta(days=60)).isoformat(),
            },
        ]
        base = random.choice(scenarios).copy()
        if "due_from" in base and "due_to" in base and base["due_from"] > base["due_to"]:
            base["due_from"], base["due_to"] = base["due_to"], base["due_from"]
        return base

    def random_id(self, source: list[str]) -> str | None:
        if not source:
            return None
        return random.choice(source)

    def random_my_pawn_id(self) -> str | None:
        if not self.pawn_ids:
            return None
        return random.choice(self.pawn_ids)

    def _update_item_caches_from_list_payload(self, payload):
        results = _pick_results(payload)
        ids: list[str] = []
        slugs: list[str] = []
        buyable: list[str] = []
        for row in results:
            pid = row.get("public_id")
            slug = row.get("slug")
            if pid:
                ids.append(pid)
                if row.get("allow_online_checkout"):
                    buyable.append(pid)
            if slug:
                slugs.append(slug)

        cls = type(self)
        if ids:
            cls.item_ids = _merge_unique(cls.item_ids, ids)
        if slugs:
            cls.slug_ids = _merge_unique(cls.slug_ids, slugs)
        if buyable:
            cls.buyable_ids = _merge_unique(cls.buyable_ids, buyable)

    @task(6)
    def list_itemsets_filtered(self):
        params = self.random_filters()
        resp = self.client.get("/api/public/item-sets/", params=params, name="/api/public/item-sets/ [list]")
        if resp.status_code == 200:
            try:
                self._update_item_caches_from_list_payload(resp.json())
            except Exception:
                pass

    @task(2)
    def get_item_detail_by_slug(self):
        slug = self.random_id(type(self).slug_ids)
        if not slug:
            return
        self.client.get(
            f"/api/public/item-sets/by-slug/{slug}/",
            name="/api/public/item-sets/by-slug/{slug}/ [detail]",
        )

    @task(3)
    def add_item_to_cart(self):
        pid = self.random_id(type(self).buyable_ids)
        if not pid:
            return
        self._sync_csrf_headers()
        payload = {"item_public_id": pid, "quantity": 1}
        with self.client.post(
            "/api/users/me/cart/items/",
            json=payload,
            name="/api/users/me/cart/items/ [add]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (201, 409):
                resp.success()
            else:
                resp.failure(f"add_to_cart failed {resp.status_code}")

    @task(1)
    def checkout_cart(self):
        cart_resp = self.client.get("/api/users/me/cart/", name="/api/users/me/cart/ [get]")
        if cart_resp.status_code != 200:
            return
        data = cart_resp.json()
        items = data.get("items") or []
        if not items:
            return

        self._sync_csrf_headers()
        payload = {"payment_method": "ONLINE_PAYMENT"}
        key = "".join(random.choices(string.ascii_lowercase + string.digits, k=16))
        headers = {"Idempotency-Key": key}
        with self.client.post(
            "/api/users/me/cart/checkout/",
            json=payload,
            headers=headers,
            name="/api/users/me/cart/checkout/ [post]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201, 409):
                resp.success()
            else:
                resp.failure(f"checkout failed {resp.status_code}")

    @task(3)
    def list_my_pawns(self):
        params = self.random_pawn_filters()
        resp = self.client.get("/api/users/me/pawns/", params=params, name="/api/users/me/pawns/ [list]")
        if resp.status_code == 200:
            data = resp.json()
            results = _pick_results(data)
            ids: list[str] = []
            for row in results:
                pid = row.get("public_id")
                if pid:
                    ids.append(pid)
            if ids:
                self.pawn_ids = ids

    @task(3)
    def get_my_pawn_detail(self):
        pid = self.random_my_pawn_id()
        if not pid:
            return
        self.client.get(
            f"/api/users/me/pawns/{pid}/",
            name="/api/users/me/pawns/{public_id}/ [detail]",
        )
