"""Official 2026 Indian festival dates (public panchang calendar). Not mock events."""
from datetime import date, timedelta

# Source: published 2026 Hindu festival calendars (Ganesh Chaturthi, Navratri, Diwali cluster).
FESTIVALS_2026 = [
    {"name": "गणेश चतुर्थी", "date": "2026-09-14", "stock": "मोदक, बेसन, गुड़, नारियल, पूजा सामग्री"},
    {"name": "अनंत चतुर्दशी / गणेश विसर्जन", "date": "2026-09-25", "stock": "प्रसाद पैक, पानी की बोतल, नमकीन"},
    {"name": "शारदीय नवरात्रि शुरू", "date": "2026-10-11", "stock": "व्रत आटा, सिंघाड़े का आटा, साबूदाना, कद्दू, दूध"},
    {"name": "दुर्गाष्टमी / महा नवमी", "date": "2026-10-19", "stock": "हलवा सामग्री, नारियल, सूखे मेवे"},
    {"name": "दशहरा / विजयादशमी", "date": "2026-10-20", "stock": "मिठाई, नमकीन, पानी, चिप्स"},
    {"name": "शरद पूर्णिमा", "date": "2026-10-25", "stock": "खीर सामग्री, दूध, चीनी, चावल"},
    {"name": "करवा चौथ", "date": "2026-10-29", "stock": "फल, मेवा, पूजा थाली सामान, मिठाई"},
    {"name": "धनतेरस", "date": "2026-11-06", "stock": "बर्तन, पूजा सामग्री, मिठाई बॉक्स"},
    {"name": "दिवाली / लक्ष्मी पूजा", "date": "2026-11-08", "stock": "घी, चीनी, मैदा, मिठाई, दिवाली गिफ्ट पैक, दीये"},
    {"name": "गोवर्धन पूजा", "date": "2026-11-09", "stock": "प्रसाद सामग्री, दही, मक्खन"},
    {"name": "भाई दूज", "date": "2026-11-11", "stock": "मिठाई, ड्राई फ्रूट्स"},
    {"name": "छठ पूजा", "date": "2026-11-15", "stock": "केला, नारियल, ठेकुआ सामग्री, गन्ना"},
    {"name": "गुरु नानक जयंती", "date": "2026-11-24", "stock": "लंगर सामान, आटा, दाल, चीनी"},
]


def get_upcoming_festivals(days_ahead: int = 365, limit: int = 1) -> list[dict]:
    """Return only the next festival(s). Default is the nearest upcoming one."""
    today = date.today()
    end = today + timedelta(days=days_ahead)
    upcoming = []
    for festival in FESTIVALS_2026:
        festival_date = date.fromisoformat(festival["date"])
        if today <= festival_date <= end:
            item = dict(festival)
            item["days_left"] = (festival_date - today).days
            upcoming.append(item)
    upcoming = upcoming[: max(1, limit)]
    print(f"DEBUG_FESTIVALS: Next {len(upcoming)} festival(s) from {today}", flush=True)
    return upcoming


def format_festivals_message(festivals: list[dict], area: str = "", city: str = "") -> str:
    """National calendar only. Do not put locality names here."""
    if not festivals:
        return "📅 *अगला त्योहार*\n\nअगले कुछ महीनों में कोई बड़ा त्योहार कैलेंडर में नहीं मिला।"
    festival = festivals[0]
    when = date.fromisoformat(festival["date"]).strftime("%d %b %Y")
    days_left = festival.get("days_left", 0)
    when_label = "आज" if days_left == 0 else f"{days_left} दिन बाकी"
    return (
        f"📅 *अगला त्योहार*\n\n"
        f"🎯 *{festival['name']}* — {when} ({when_label})\n"
        f"📦 स्टॉक: {festival['stock']}"
    )
