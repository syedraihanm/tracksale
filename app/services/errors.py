class DomainError(Exception):
    """Base domain exception."""


class InvalidTransition(DomainError):
    """Invalid ticket status transition."""


class ValidationFailed(DomainError):
    """Business rule validation failed."""


class PinRequired(DomainError):
    """Action requires owner PIN verification."""


class DayClosed(DomainError):
    """Cash day is closed; mutations forbidden."""


class NeedsConfirmation(DomainError):
    """Action requires explicit confirmation (overpay, pending balance)."""
