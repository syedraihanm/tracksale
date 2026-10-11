from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_login
from app.services.search import search_tickets
from app.services.warranty import is_under_warranty
from app.templating import templates

router = APIRouter(dependencies=[Depends(require_login)])


@router.get("/search", response_class=HTMLResponse)
def search_dropdown(request: Request, q: str = Query("", max_length=100), db: Session = Depends(get_db)):
    query = q.strip()
    if len(query) < 2:
        return HTMLResponse('<div class="p-4 text-xs text-slate-500 text-center">Type at least 2 characters to search...</div>')

    results = search_tickets(db, query, limit=20)
    if not results:
        return HTMLResponse('<div class="p-4 text-xs text-slate-500 text-center">No matching tickets found.</div>')

    enriched = []
    for t in results:
        enriched.append({
            "ticket": t,
            "under_warranty": is_under_warranty(t),
            "is_exact_ticket_no": t.ticket_no.lower() == query.lower(),
        })

    return templates.TemplateResponse(
        request=request,
        name="partials/search_results.html",
        context={"results": enriched, "query": query},
    )
