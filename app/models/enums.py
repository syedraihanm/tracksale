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
    INVENTORY = "inventory"


class AuditAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class SpareCategory(str, Enum):
    DISPLAY = "display"
    BACKDOOR = "backdoor"
    BATTERY = "battery"
    CAMERA = "camera"
    MOTHERBOARD = "motherboard"
    CHARGER_BOARD = "charger board"
    GLASS = "glass"
    OTHER = "other"


SPARE_CATEGORIES = [
    "display",
    "backdoor",
    "battery",
    "camera",
    "motherboard",
    "charger board",
    "glass",
    "other",
]

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
