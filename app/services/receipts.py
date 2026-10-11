import io
import re
import urllib.parse

import qrcode
import qrcode.image.svg

from app.formatting import format_inr
from app.models.ticket import Ticket
from app.services.payments import get_ticket_totals


def generate_qr_svg(content: str) -> str:
    """Generate an inline SVG QR code for the given text (e.g. ticket number)."""
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(content, image_factory=factory, box_size=10, border=1)
    stream = io.BytesIO()
    img.save(stream)
    return stream.getvalue().decode("utf-8")


def render_message_template(template: str, values: dict[str, str]) -> str:
    """Safely replace {placeholder} keys with values; leave unknown placeholders intact."""
    def replacer(match):
        key = match.group(1)
        return str(values.get(key, match.group(0)))

    return re.sub(r"\{([a-zA-Z0-9_]+)\}", replacer, template)


def generate_whatsapp_url(ticket: Ticket, template_text: str, shop_name: str) -> str:
    """Generate WhatsApp wa.me URL for the customer with the filled message."""
    _, net_paid, balance_due = get_ticket_totals(ticket)

    # Indian-grouped numbers WITHOUT ₹ prefix because template contains ₹
    advance_str = format_inr(net_paid, prefix=False) if net_paid > 0 else "0"
    due_str = format_inr(max(0, balance_due), prefix=False)

    placeholders = {
        "name": ticket.customer.name,
        "device": f"{ticket.device_brand} {ticket.device_model}".strip(),
        "ticket_no": ticket.ticket_no,
        "issue": ticket.reported_issue,
        "advance": advance_str,
        "due": due_str,
        "shop_name": shop_name,
    }

    message = render_message_template(template_text, placeholders)
    encoded_message = urllib.parse.quote(message)
    phone = ticket.customer.phone
    return f"https://wa.me/91{phone}?text={encoded_message}"
