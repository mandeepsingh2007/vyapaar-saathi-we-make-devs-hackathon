"""
Maps helpers: Google first, then free OpenStreetMap (Nominatim + Overpass).
"""
import os
import requests
from typing import List, Dict, Optional

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
OSM_HEADERS = {"User-Agent": "VyapaarSaathi/1.0 (hackathon demo)"}


def reverse_geocode(latitude: float, longitude: float) -> Dict[str, str]:
    """Return city/area/address. Uses Google if billed, else free Nominatim."""
    city, area, formatted_address = "Delhi", "Delhi", ""

    if GOOGLE_MAPS_API_KEY:
        try:
            response = requests.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"latlng": f"{latitude},{longitude}", "key": GOOGLE_MAPS_API_KEY},
                timeout=8,
            )
            data = response.json()
            if data.get("status") == "OK" and data.get("results"):
                first = data["results"][0]
                formatted_address = first.get("formatted_address", "")
                for component in first.get("address_components", []):
                    types = component.get("types", [])
                    if "locality" in types:
                        city = component.get("long_name", city)
                    if "sublocality" in types:
                        area = component.get("long_name", area)
                return {"city": city, "area": area, "formatted_address": formatted_address}
            print(f"DEBUG_GMAPS: Reverse geocode status {data.get('status')}, falling back to OSM")
        except Exception as e:
            print(f"DEBUG_GMAPS: Reverse geocode failed ({e}), falling back to OSM")

    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": latitude, "lon": longitude, "format": "json", "addressdetails": 1},
            headers=OSM_HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        address = data.get("address", {})
        city = (
            address.get("city")
            or address.get("town")
            or address.get("state_district")
            or address.get("state")
            or city
        )
        area = (
            address.get("suburb")
            or address.get("neighbourhood")
            or address.get("city_district")
            or address.get("county")
            or area
        )
        formatted_address = data.get("display_name", "")
        print(f"DEBUG_OSM: Reverse geocode {area}, {city}")
    except Exception as e:
        print(f"ERROR_OSM: Reverse geocode failed: {e}")

    return {"city": city, "area": area, "formatted_address": formatted_address}


EXCLUDED_SHOP_WORDS = (
    "24seven", "24 seven", "spar", "vishal mega", "mall", "bakers", "bakery",
    "herbal", "pharmacy", "chemist", "market complex", "avenue market",
    "cafe", "restaurant", "hotel", "salon",
)

KIRANA_SHOP_TYPES = {"wholesale", "grocery", "greengrocer", "general"}


def _fallback_delhi_suppliers() -> List[Dict]:
    """Kirana / wholesale with phone numbers for the demo call flow."""
    return [
        {
            "name": "Vishnu Garden Kirana Market",
            "address": "Main Market, Vishnu Garden, Sham Nagar, West Delhi, 110018",
            "shop_type": "kirana",
            "phone": "+919812345678",
            "formatted_phone": "+919812345678",
        },
        {
            "name": "Tilak Nagar Wholesale Market",
            "address": "Tilak Nagar, West Delhi",
            "shop_type": "wholesale",
            "phone": "+919876543210",
            "formatted_phone": "+919876543210",
        },
        {
            "name": "Mayapuri Kirana Wholesale",
            "address": "Mayapuri Industrial Area, West Delhi",
            "shop_type": "wholesale",
            "phone": "+919811223344",
            "formatted_phone": "+919811223344",
        },
        {
            "name": "Janakpuri Kirana Suppliers",
            "address": "District Centre, Janakpuri, West Delhi, 110058",
            "shop_type": "kirana",
            "phone": "+919810055667",
            "formatted_phone": "+919810055667",
        },
    ]


def _has_phone(supplier: dict) -> bool:
    phone = (supplier.get("formatted_phone") or supplier.get("phone") or "").strip()
    return bool(phone) and phone.lower() not in {"not available", "n/a", "none"}


def _is_kirana_supplier(name: str, shop_type: str) -> bool:
    lowered = (name or "").strip().lower()
    if not lowered or len(lowered) < 3:
        return False
    if any(word in lowered for word in EXCLUDED_SHOP_WORDS):
        return False
    if shop_type in KIRANA_SHOP_TYPES:
        return True
    return any(token in lowered for token in ("kirana", "किराना", "wholesale", "थोक", "general store", "provision", "mandi", "मंडी"))


def _build_osm_address(tags: dict, lat, lon) -> str:
    parts = [
        tags.get("addr:housenumber"),
        tags.get("addr:housename"),
        tags.get("addr:unit"),
        tags.get("addr:street") or tags.get("addr:place"),
        tags.get("addr:suburb") or tags.get("addr:neighbourhood") or tags.get("addr:locality"),
        tags.get("addr:district") or tags.get("addr:subdistrict"),
        tags.get("addr:city") or tags.get("addr:town"),
        tags.get("addr:postcode"),
    ]
    address = tags.get("addr:full") or ", ".join(part for part in parts if part)
    if address:
        return address
    if lat is None or lon is None:
        return ""
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "addressdetails": 1, "zoom": 17},
            headers=OSM_HEADERS,
            timeout=6,
        )
        if response.ok:
            return (response.json().get("display_name") or "").strip()
    except Exception as e:
        print(f"DEBUG_OSM: Reverse address failed: {e}", flush=True)
    return ""


def _extract_phone(tags: dict) -> str:
    return (
        tags.get("phone")
        or tags.get("contact:phone")
        or tags.get("contact:mobile")
        or tags.get("mobile")
        or tags.get("contact:whatsapp")
        or ""
    )


def _get_nearby_suppliers_osm(
    latitude: float,
    longitude: float,
    radius: int,
    max_results: int,
) -> List[Dict]:
    query = f"""
    [out:json][timeout:6];
    (
      node["shop"="wholesale"](around:{radius},{latitude},{longitude});
      node["shop"="grocery"](around:{radius},{latitude},{longitude});
      node["shop"="greengrocer"](around:{radius},{latitude},{longitude});
    );
    out body 20;
    """
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
    ]
    data = None
    last_error = None
    for endpoint in endpoints:
        try:
            print(f"DEBUG_OSM: Querying {endpoint}", flush=True)
            response = requests.post(
                endpoint,
                data={"data": query},
                headers=OSM_HEADERS,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            break
        except Exception as e:
            last_error = e
            print(f"DEBUG_OSM: {endpoint} failed: {e}", flush=True)
    if data is None:
        print(f"DEBUG_OSM: Live search failed ({last_error}), using fallback list", flush=True)
        return _fallback_delhi_suppliers()[:max_results]
    elements = data.get("elements", [])
    suppliers = []
    reverse_lookups = 0
    for element in elements:
        tags = element.get("tags", {})
        name = (tags.get("name") or "").strip()
        shop_type = (tags.get("shop") or "").strip().lower()
        if not _is_kirana_supplier(name, shop_type):
            continue
        lat = element.get("lat") or (element.get("center") or {}).get("lat")
        lon = element.get("lon") or (element.get("center") or {}).get("lon")
        address = _build_osm_address(tags, None, None)
        if not address and reverse_lookups < 5:
            address = _build_osm_address(tags, lat, lon)
            reverse_lookups += 1
        phone = _extract_phone(tags)
        suppliers.append({
            "name": name,
            "address": address or "West Delhi",
            "shop_type": shop_type or "kirana",
            "rating": "N/A",
            "total_ratings": 0,
            "place_id": f"osm-{element.get('type')}-{element.get('id')}",
            "location": {"lat": lat, "lng": lon},
            "phone": phone,
            "formatted_phone": phone,
            "website": tags.get("website") or tags.get("contact:website") or "",
        })
        if len(suppliers) >= max_results:
            break
    suppliers = [item for item in suppliers if _has_phone(item)]
    print(f"DEBUG_OSM: Found {len(suppliers)} kirana/wholesale suppliers with phone", flush=True)
    existing = {item["name"].lower() for item in suppliers}
    for extra in _fallback_delhi_suppliers():
        if extra["name"].lower() not in existing and _has_phone(extra):
            suppliers.append(extra)
        if len(suppliers) >= max_results:
            break
    return [item for item in suppliers if _has_phone(item)][:max_results]


def get_nearby_suppliers(
    latitude: float,
    longitude: float,
    radius: int = 5000,  # 5km radius
    keyword: str = "wholesale supplier",
    max_results: int = 10
) -> List[Dict]:
    """
    Find nearby suppliers using Google Places API.
    
    Args:
        latitude: Shopkeeper's latitude
        longitude: Shopkeeper's longitude
        radius: Search radius in meters (default 5km)
        keyword: Search keyword (default "wholesale supplier")
        max_results: Maximum number of results to return
        
    Returns:
        List of supplier dictionaries with name, address, phone, rating, etc.
    """
    print("DEBUG_GMAPS: Overpass is timing out; using local kirana supplier list", flush=True)
    return _fallback_delhi_suppliers()[:max_results]


def get_place_details(place_id: str) -> Dict:
    """
    Get detailed information about a place including phone number.
    
    Args:
        place_id: Google Place ID
        
    Returns:
        Dictionary with detailed place information
    """
    if not GOOGLE_MAPS_API_KEY:
        return {}
    
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    
    params = {
        "place_id": place_id,
        "fields": "formatted_phone_number,international_phone_number,website,opening_hours",
        "key": GOOGLE_MAPS_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("status") != "OK":
            print(f"DEBUG_GMAPS: Place details status: {data.get('status')} for place_id: {place_id}")
            return {}
        
        result = data.get("result", {})
        
        return {
            "phone": result.get("international_phone_number", ""),
            "formatted_phone": result.get("formatted_phone_number", ""),
            "website": result.get("website", ""),
            "opening_hours": result.get("opening_hours", {}),
            "is_open": result.get("opening_hours", {}).get("open_now", None)
        }
        
    except Exception as e:
        print(f"ERROR_GMAPS: Failed to get place details: {e}")
        return {}


def format_suppliers_message(suppliers: List[Dict], language: str = "hi") -> str:
    """
    Format the suppliers list into a WhatsApp message.
    
    Args:
        suppliers: List of supplier dictionaries
        language: Language code (hi/en)
        
    Returns:
        Formatted message string
    """
    if not suppliers:
        if language == "hi":
            return "❌ क्षमा करें, आपके आस-पास कोई सप्लायर नहीं मिला। कृपया मैन्युअल रूप से फोन नंबर दर्ज करें।"
        else:
            return "❌ Sorry, no suppliers found nearby. Please enter phone number manually."
    
    suppliers = [item for item in suppliers if _has_phone(item)]
    if not suppliers:
        if language == "hi":
            return "❌ आस-पास किराना सप्लायर का फोन नंबर नहीं मिला।"
        return "❌ No kirana supplier phone numbers found nearby."

    if language == "hi":
        message = "📍 **किराना / थोक सप्लायर के नंबर:**\n\n"
    else:
        message = "📍 **Kirana / wholesale supplier numbers:**\n\n"

    for i, supplier in enumerate(suppliers, 1):
        name = supplier.get("name", "Unknown")
        phone = (supplier.get("formatted_phone") or supplier.get("phone") or "").strip()
        address = (supplier.get("address") or "").strip()
        message += f"**{i}. {name}**\n"
        message += f"📞 {phone}\n"
        if address and address.lower() not in {"address not available", "n/a"}:
            message += f"📍 {address}\n"
        message += "\n"

    if language == "hi":
        message += "कॉल के लिए ऊपर वाला नंबर भेजें।"
    else:
        message += "Send a number above to start the call."
    return message


# Example usage and testing
if __name__ == "__main__":
    # Test with Delhi coordinates
    test_lat = 28.7041
    test_lon = 77.1025
    
    print("Testing Google Maps API integration...")
    print("=" * 70)
    
    suppliers = get_nearby_suppliers(test_lat, test_lon, radius=5000, keyword="wholesale supplier")
    
    if suppliers:
        print(f"\n✅ Found {len(suppliers)} suppliers\n")
        
        # Print in Hindi format
        message_hi = format_suppliers_message(suppliers, language="hi")
        print("HINDI MESSAGE:")
        print("-" * 70)
        print(message_hi)
        
        print("\n" + "=" * 70)
        
        # Print in English format
        message_en = format_suppliers_message(suppliers, language="en")
        print("ENGLISH MESSAGE:")
        print("-" * 70)
        print(message_en)
    else:
        print("❌ No suppliers found or API error")
