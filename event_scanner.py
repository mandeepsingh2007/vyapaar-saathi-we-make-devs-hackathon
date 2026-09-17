"""
Event Scanner Module
Scans for local events using DuckDuckGo Search to identify business opportunities.
"""
from duckduckgo_search import DDGS
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def scan_local_events(city, area=None):
    """
    Scans for upcoming events in the specified city and area.
    Returns a list of relevant events. No mock/fallback events.
    """
    try:
        now = datetime.now()
        current_month = now.strftime("%B")
        year = now.year

        locality = (area or "").strip()
        if locality and locality.lower() != (city or "").lower():
            queries = [
                f"{locality} {city} events {current_month} {year}",
                f"{locality} {city} mela fair festival {year}",
                f"{locality} West Delhi events {current_month} {year}",
            ]
        else:
            queries = [
                f"{city} local events {current_month} {year}",
                f"{city} mela fair festival {current_month} {year}",
                f"{city} exhibition marathon {current_month} {year}",
            ]

        events = []
        seen_urls = set()

        with DDGS() as ddgs:
            for query in queries:
                print(f"DEBUG_EVENTS: Searching for: {query}", flush=True)
                try:
                    results = list(ddgs.text(query, max_results=3, backend="lite"))
                    for row in results:
                        url = row.get("href")
                        if url and url not in seen_urls:
                            events.append({
                                "title": row.get("title"),
                                "snippet": row.get("body"),
                                "link": row.get("href"),
                                "source": "Web Search",
                            })
                            seen_urls.add(url)
                except Exception as e:
                    print(f"DEBUG_EVENTS: Error with query '{query}': {e}", flush=True)

        print(f"DEBUG_EVENTS: Found {len(events)} potential event signals", flush=True)
        return events

    except Exception as e:
        logger.error(f"Error scanning events: {e}")
        print(f"ERROR_EVENTS: {e}", flush=True)
        return []

if __name__ == "__main__":
    print("Testing Event Scanner...")
    found_events = scan_local_events("Delhi", "Janakpuri")
    for event in found_events:
        print(f"- {event['title']}")
