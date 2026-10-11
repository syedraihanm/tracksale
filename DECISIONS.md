# Architectural & Design Decisions

This document records the architectural decisions, assumptions, and trade-offs made in the Mobile Repair Shop Management System.

| ID | Decision | Reason |
|---|---|---|
| A-01 | PDF via print CSS + browser "Save as PDF", not WeasyPrint | Client-permitted fallback; WeasyPrint is heavy on Windows |
| A-02 | Store UTC, compute days in IST; `tzdata` dependency | Correct day boundaries, Windows support |
| A-03 | `issue_category` column and dropdown from Phase 1 intake (default Other) | Listed in Phase 3, but needed early so analytics has data |
| A-04 | `tickets.outcome` (`repaired/declined/unrepairable`) set on delivery | Client's "status repaired" does not exist as a status; needed for metrics |
| A-05 | Accessories detail stored as `accessories_note` in intake JSON | Intake lists accessories separately from the checklist |
| A-06 | `paid_at` is server-set and not editable | Protects cash reconciliation |
| A-07 | Audit entities also include `cash_closing` and `settings` | "All edits" must be audited |
| A-08 | `cash_closings.is_closed/closed_at/reopened_at` | Needed to support close and reopen |
| A-09 | Overpay check uses items total, else estimate, else unlimited; advances allowed before items exist | Required to allow intake advances while honouring "cannot exceed balance" |
| A-10 | Item edits after delivery require owner PIN | Protects historical billed value |
| A-11 | Ticket deletion blocked while it has non-deleted payments | Keeps cash and revenue consistent |
| A-12 | Warranty-return button on any delivered ticket, with an "expired" warning when applicable | Simple and flexible |
| A-13 | `ready_at` overwritten on each entry to ready_for_pickup | Reflects final readiness |
| A-14 | Receipt also shows payments and items when present | Useful at pickup; still plain receipt |
| A-15 | Default terms text provided | Client left content to settings |
| A-16 | Queue is a grouped table, not a board | Fits 1366 px and phones |
| A-17 | Read-only audit log page | Needed to verify AC7 in the UI |
| A-18 | Catch-up backup at startup if last backup > 24 h old | PC may be off at 02:00 |
| A-19 | Import creates delivered/repaired tickets with one labor item and one final payment | Simplest consistent mapping |
| A-20 | PIN unlock for dashboard lasts 15 minutes, sliding | Usability vs safety |
| A-21 | Previous period = immediately preceding window of equal length | Unambiguous comparison |
| A-22 | Avg turnaround uses tickets with `ready_at` in the period | Defined window for the metric |
| A-23 | Warranty return = non-deleted child ticket received on or before parent's `warranty_until` | Concrete reading of "within their warranty period" |
| A-24 | Brand/model/issue stats use `received_at` in period | Measures demand |
| A-25 | Sanity cap ₹10,00,000 on money inputs | Catches typos |
| A-26 | All phase columns created in the first migration | Avoids backfill |
| A-27 | Reopening a past day shows a warning about later openings | Cash chain integrity |
| A-28 | Single-row `settings` also stores admin password hash, ticket sequence, and message templates | Avoids an extra users table for a single login |
| A-29 | Settings page ships in Phase 1 with Backups only; forms arrive in Phase 2 | Phase order in client doc |
| A-30 | Phone validated as 10 digits only (no 6-9 first-digit rule) | Follows the client wording exactly |
