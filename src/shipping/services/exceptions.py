from __future__ import annotations

class DomainError(Exception):
    """Bazowy wyjątek domenowy modułu shipping."""

class NotAllowed(DomainError):
    """Brak uprawnień do wykonania akcji."""

class NotFound(DomainError):
    """Encji nie znaleziono."""

class AddressAlreadyExists(DomainError):
    """Użytkownik ma już przypięty adres (przy POST create)."""

class InvalidPackageLimits(DomainError):
    """Błędne/niekonsekwentne limity paczki lub inne naruszenie walidacji."""