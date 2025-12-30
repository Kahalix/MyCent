from __future__ import annotations

import random
import string

from locust import HttpUser, task, between

NUM_PERF_USERS = 500


class TestUser(HttpUser):
    wait_time = between(0.3, 1.5)
    item_ids: list[str] = []
    slug_ids: list[str] = []
    buyable_ids: list[str] = []

    def on_start(self):
        self.pick_credentials()
        self.login()
        self.bootstrap_items()

    def pick_credentials(self):
        idx = random.randint(1, NUM_PERF_USERS)
        self.email = f"perfuser{idx:04d}@example.com"
        self.password = "PerfPass123!"

    def login(self):
        payload = {"email": self.email, "password": self.password}
        with self.client.post(
            "/api/auth/login/",
            json=payload,
            name="/api/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"login failed {resp.status_code}")
                return
            data = resp.json()
            token = data.get("access")
            if not token:
                resp.failure("no access token")
                return
            self.client.headers.update({"Authorization": f"Bearer {token}"})

    def bootstrap_items(self):
        params = {"status": "AVAILABLE"}
        with self.client.get(
            "/api/public/item-sets/",
            params=params,
            name="/api/public/item-sets/ [initial-load]",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"bootstrap failed {resp.status_code}")
                return
            data = resp.json()
            results = data.get("results", data)
            ids = []
            slugs = []
            buyable = []
            for row in results:
                pid = row.get("public_id")
                slug = row.get("slug")
                if pid:
                    ids.append(pid)
                    if row.get("allow_online_checkout"):
                        buyable.append(pid)
                if slug:
                    slugs.append(slug)
            if ids:
                type(self).item_ids = ids
            if slugs:
                type(self).slug_ids = slugs
            if buyable:
                type(self).buyable_ids = buyable

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

    def random_id(self, source: list[str]) -> str | None:
        if not source:
            self.bootstrap_items()
        if not source:
            return None
        return random.choice(source)

    @task(5)
    def list_itemsets_filtered(self):
        params = self.random_filters()
        self.client.get(
            "/api/public/item-sets/",
            params=params,
            name="/api/public/item-sets/ [list]",
        )

    @task(3)
    def get_item_detail(self):
        pid = self.random_id(type(self).item_ids)
        if not pid:
            return
        path = f"/api/public/item-sets/{pid}/"
        self.client.get(path, name="/api/public/item-sets/{id}/ [detail]")

    @task(2)
    def get_item_detail_by_slug(self):
        slug = self.random_id(type(self).slug_ids)
        if not slug:
            return
        path = f"/api/public/item-sets/by-slug/{slug}/"
        self.client.get(path, name="/api/public/item-sets/by-slug/{slug} [detail]")

    @task(3)
    def add_item_to_cart(self):
        pid = self.random_id(type(self).buyable_ids)
        if not pid:
            return
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
        cart_resp = self.client.get(
            "/api/users/me/cart/",
            name="/api/users/me/cart/ [get]",
        )
        if cart_resp.status_code != 200:
            return
        data = cart_resp.json()
        items = data.get("items") or []
        if not items:
            return
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
