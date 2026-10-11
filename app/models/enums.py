from enum import Enum


class TicketStatus(str, Enum):
    RECEIVED = "received"
    AWAITING_APPROVAL = "awaiting_approval"
    IN_PROGRESS = "in_progress"
    AWAITING_PARTS = "awaiting_parts"
    READY_FOR_PICKUP = "ready_for_pickup"
    DELIVERED = "delivered"
    DECLINED = "declined"
    UNREPAIRABLE = "unrepairable"


class Outcome(str, Enum):
    REPAIRED = "repaired"
    DECLINED = "declined"
    UNREPAIRABLE = "unrepairable"


class ItemType(str, Enum):
    LABOR = "labor"
    PART = "part"


class PaymentMode(str, Enum):
    CASH = "cash"
    CARD = "card"
    UPI = "upi"


class PaymentKind(str, Enum):
    ADVANCE = "advance"
    FINAL = "final"
    REFUND = "refund"


class AuditEntity(str, Enum):
    TICKET = "ticket"
    PAYMENT = "payment"
    ITEM = "item"
    CUSTOMER = "customer"
    CASH_CLOSING = "cash_closing"
    SETTINGS = "settings"


class AuditAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


ISSUE_CATEGORIES = [
    "Screen",
    "Battery",
    "Charging port",
    "Water damage",
    "Software",
    "Speaker/Mic",
    "Camera",
    "Motherboard",
    "Other",
]
