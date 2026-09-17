"""
Opportunity Manager Module
Analyzes local events and inventory to generate smart business tips.
"""
from event_scanner import scan_local_events
from festival_calendar import format_festivals_message, get_upcoming_festivals


def format_local_events_message(events: list, area: str, city: str) -> str:
    place = f"{area}, {city}" if area and area.lower() != city.lower() else (city or area)
    if not events:
        return (
            f"📍 *{place} — स्थानीय इवेंट*\n\n"
            "अभी वेब पर इस इलाके का कोई इवेंट नहीं मिला।"
        )
    lines = [f"📍 *{place} — स्थानीय इवेंट*\n"]
    for event in events[:5]:
        title = (event.get("title") or "").strip()
        snippet = (event.get("snippet") or "").strip()
        if title:
            lines.append(f"• *{title}*")
        if snippet:
            lines.append(snippet[:180])
        lines.append("")
    return "\n".join(lines).strip()


async def analyze_opportunities(user_id, latitude, longitude, city, area, include_festivals=True):
    """
    Festival = national calendar (no locality).
    Local events = area search only (e.g. Sham Nagar).
    No mock events.
    """
    try:
        festival_block = format_festivals_message(get_upcoming_festivals(limit=1))

        print(f"DEBUG_OPP: Scanning local events for {area}, {city}...", flush=True)
        raw_events = scan_local_events(city, area)
        local_block = format_local_events_message(raw_events, area, city)

        if include_festivals:
            return f"{festival_block}\n\n{local_block}"
        return local_block

    except Exception as e:
        print(f"ERROR_OPP: {e}", flush=True)
        if include_festivals:
            return format_festivals_message(get_upcoming_festivals(limit=1))
        return format_local_events_message([], area or "", city or "Delhi")
