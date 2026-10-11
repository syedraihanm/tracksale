from fastapi.templating import Jinja2Templates

from app.formatting import (
    days_ago,
    format_date,
    format_datetime,
    format_inr,
    format_time,
)

templates = Jinja2Templates(directory="app/templates")

# Register custom Jinja filters on the shared environment
templates.env.filters["inr"] = format_inr
templates.env.filters["date_ist"] = format_date
templates.env.filters["time_ist"] = format_time
templates.env.filters["datetime_ist"] = format_datetime
templates.env.filters["days_ago"] = days_ago
