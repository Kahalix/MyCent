import time
import os
import socket
import threading
import secrets
import string
import hashlib
from django.db import models
from django.conf import settings
import uuid

# alfabet używany w wyniku (litery a-z + cyfry 0-9)
_ALPHABET = string.ascii_lowercase + string.digits
_BASE = len(_ALPHABET)

# helper: konwertuje liczbę całkowitą na reprezentację w zadanym alfabecie
def _to_base(n: int, alphabet: str = _ALPHABET) -> str:
    if n == 0:
        return alphabet[0]
    base = len(alphabet)
    out = []
    while n > 0:
        n, r = divmod(n, base)
        out.append(alphabet[r])
    return ''.join(reversed(out))

# globalny licznik z zabezpieczeniem wątkowym
_counter_lock = threading.Lock()
_counter = secrets.randbelow(_BASE**4)  # start losowy, żeby różne procesy miały inne początki
_COUNTER_MOD = _BASE**4  # długość pola licznika (tu 4 znaki w bazie _BASE)

def _next_counter() -> str:
    global _counter
    with _counter_lock:
        _counter = (_counter + 1) % _COUNTER_MOD
        return _to_base(_counter).rjust(4, _ALPHABET[0])  # zawsze 4 znaki (padding)

# fingerprint maszyny/processu
def _machine_fingerprint(length: int = 5) -> str:
    host = socket.gethostname()
    pid = os.getpid()
    data = f"{host}-{pid}".encode("utf-8")
    h = hashlib.sha256(data).digest()
    # zamień np. pierwsze 6 bajtów na int, następnie na bazę
    val = int.from_bytes(h[:6], "big")
    s = _to_base(val)
    # jeśli krócej - dopełnij z lewej, jeśli dłuższe - utnij do końca
    if len(s) < length:
        s = s.rjust(length, _ALPHABET[0])
    elif len(s) > length:
        s = s[-length:]
    return s

# główna funkcja generująca 24-znakowy identyfikator
def cuid2() -> str:
    """
    Generuje 24-znakowy identyfikator składający się z:
      * stempel czasowy w ms (ok. 9 znaków)
      * fingerprint maszyny/procesu (5 znaków)
      * licznik (4 znaki)
      * losowa część (6 znaków)
    Zwracany string jest złożony z a-z0-9.
    """
    # timestamp w ms
    ts_ms = int(time.time() * 1000)
    ts_part = _to_base(ts_ms)

    # ustandaryzuj długości segmentów tak, aby końcowy był 24-znakowy
    # plan: ts_len (9) + fp (5) + counter (4) + rand (6) = 24
    # ts może czasem być dłuższy - wtedy ucinamy z końca (nowsze bity)
    ts_len = 9
    if len(ts_part) < ts_len:
        ts_part = ts_part.rjust(ts_len, _ALPHABET[0])
    elif len(ts_part) > ts_len:
        ts_part = ts_part[-ts_len:]

    fp_part = _machine_fingerprint(length=5)
    counter_part = _next_counter()  # 4 znaki
    rand_part = ''.join(secrets.choice(_ALPHABET) for _ in range(6))

    return (ts_part + fp_part + counter_part + rand_part)

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class PublicIdModel(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    public_id = models.CharField(max_length=64, unique=True, default=cuid2, db_index=True)
    class Meta:
        abstract = True

class IdempotencyKey(models.Model):
    """
    magazyn idempotentnych wywołań.
    Unikalność: (user, scope, key).
    target_ids: JSON - np. ["pay_public_id"] albo lista public_id zamówień.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="idempo_keys")
    scope = models.CharField(max_length=64)  # np. "payments:intent:<tx_public_id>", "carts:checkout:<cart_public_id>"
    key = models.CharField(max_length=128)
    target_type = models.CharField(max_length=32, blank=True)  # PAYMENT / ORDER
    target_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "scope", "key"], name="uq_idempo_user_scope_key"),
        ]
        indexes = [
            models.Index(fields=["user", "scope", "created_at"], name="ix_idempo_user_scope"),
            models.Index(fields=["created_at"], name="ix_idempo_created_at"),
        ]

    # class Meta:
    #     unique_together = (("user","scope","key"),)
    #     indexes = [models.Index(fields=["user","scope","created_at"], name="ix_idempo_user_scope")]