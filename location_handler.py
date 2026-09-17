"""
Location sharing web page for shopkeepers.
When accessed, this page requests GPS location and sends it back to the server.
"""
from flask import Blueprint, render_template_string, request, jsonify, redirect
import json

location_bp = Blueprint('location', __name__)

# HTML template for location sharing page
LOCATION_PAGE_HTML = """
<!DOCTYPE html>
<html lang="hi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>अपना स्थान साझा करें - Share Your Location</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            text-align: center;
        }
        
        .icon {
            font-size: 80px;
            margin-bottom: 20px;
        }
        
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }
        
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 16px;
        }
        
        .info-box {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 30px;
            text-align: left;
        }
        
        .info-box p {
            color: #555;
            line-height: 1.6;
            margin-bottom: 10px;
        }
        
        .info-box strong {
            color: #667eea;
        }
        
        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 40px;
            font-size: 18px;
            border-radius: 50px;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            width: 100%;
            font-weight: bold;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }
        
        button:active {
            transform: translateY(0);
        }
        
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }
        
        .status {
            margin-top: 20px;
            padding: 15px;
            border-radius: 10px;
            font-size: 16px;
        }
        
        .status.loading {
            background: #fff3cd;
            color: #856404;
        }
        
        .status.success {
            background: #d4edda;
            color: #155724;
        }
        
        .status.error {
            background: #f8d7da;
            color: #721c24;
        }
        
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .location-info {
            background: #e7f3ff;
            border-radius: 10px;
            padding: 15px;
            margin-top: 20px;
            text-align: left;
        }
        
        .location-info p {
            margin: 5px 0;
            color: #333;
        }
        
        .location-info strong {
            color: #667eea;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">📍</div>
        <h1>अपना स्थान साझा करें</h1>
        <p class="subtitle">Share Your Location</p>
        
        <div class="info-box">
            <p><strong>📌 क्यों जरूरी है?</strong></p>
            <p>आपके आस-पास के सप्लायर खोजने के लिए हमें आपका सटीक स्थान चाहिए।</p>
            <br>
            <p><strong>🔒 सुरक्षित है?</strong></p>
            <p>हाँ! आपका स्थान केवल सप्लायर खोजने के लिए उपयोग होगा और सुरक्षित रूप से संग्रहीत किया जाएगा।</p>
            <br>
            <p><strong>📍 सटीक स्थान के लिए:</strong></p>
            <p>• मोबाइल फोन से खोलें (डेस्कटॉप से नहीं)<br>
            • बाहर या खिड़की के पास खड़े हों<br>
            • GPS चालू रखें</p>
        </div>
        
        <button id="shareBtn" onclick="getLocation()">
            📍 स्थान साझा करें / Share Location
        </button>
        
        <div id="status"></div>
        <div id="locationInfo"></div>
    </div>

    <script>
        const userId = "{{ user_id }}";
        const baseUrl = "{{ base_url }}";
        
        function getLocation() {
            const btn = document.getElementById('shareBtn');
            const status = document.getElementById('status');
            const locationInfo = document.getElementById('locationInfo');
            
            btn.disabled = true;
            status.className = 'status loading';
            status.innerHTML = '<div class="spinner"></div><p>स्थान प्राप्त कर रहे हैं... / Getting location...</p>';
            
            if (!navigator.geolocation) {
                status.className = 'status error';
                status.innerHTML = '❌ आपका ब्राउज़र GPS का समर्थन नहीं करता।<br>Your browser doesn\\'t support GPS.';
                btn.disabled = false;
                return;
            }
            
            navigator.geolocation.getCurrentPosition(
                function(position) {
                    const latitude = position.coords.latitude;
                    const longitude = position.coords.longitude;
                    const accuracy = position.coords.accuracy;
                    
                    // Show location info
                    locationInfo.className = 'location-info';
                    locationInfo.innerHTML = `
                        <p><strong>📍 स्थान मिल गया!</strong></p>
                        <p>Latitude: ${latitude.toFixed(6)}</p>
                        <p>Longitude: ${longitude.toFixed(6)}</p>
                        <p>Accuracy: ${accuracy.toFixed(0)} meters</p>
                    `;
                    
                    // Send to server
                    sendLocationToServer(latitude, longitude, accuracy);
                },
                function(error) {
                    let errorMsg = '';
                    switch(error.code) {
                        case error.PERMISSION_DENIED:
                            errorMsg = '❌ आपने स्थान साझा करने की अनुमति नहीं दी।<br>You denied location permission.';
                            break;
                        case error.POSITION_UNAVAILABLE:
                            errorMsg = '❌ स्थान जानकारी उपलब्ध नहीं है।<br>Location information unavailable.';
                            break;
                        case error.TIMEOUT:
                            errorMsg = '❌ समय समाप्त हो गया।<br>Request timeout.';
                            break;
                        default:
                            errorMsg = '❌ कुछ गलत हो गया।<br>Something went wrong.';
                    }
                    status.className = 'status error';
                    status.innerHTML = errorMsg;
                    btn.disabled = false;
                }
            );
        }
        
        function sendLocationToServer(latitude, longitude, accuracy) {
            const status = document.getElementById('status');
            
            fetch(`${baseUrl}/save_location`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: userId,
                    latitude: latitude,
                    longitude: longitude,
                    accuracy: accuracy
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    status.className = 'status success';
                    status.innerHTML = `
                        ✅ <strong>स्थान सफलतापूर्वक सहेजा गया!</strong><br>
                        Location saved successfully!<br><br>
                        📱 आपकी रिक्वेस्ट प्रोसेस की जा रही है। WhatsApp चेक करें।<br>
                        Your request is being processed. Please check WhatsApp.<br><br>
                        अब आप WhatsApp पर वापस जा सकते हैं।<br>
                        You can now go back to WhatsApp.
                    `;
                    
                    // Auto-close after 3 seconds
                    setTimeout(() => {
                        window.close();
                    }, 3000);
                } else {
                    throw new Error(data.error || 'Unknown error');
                }
            })
            .catch(error => {
                status.className = 'status error';
                status.innerHTML = `❌ स्थान सहेजने में त्रुटि: ${error.message}<br>Error saving location`;
                document.getElementById('shareBtn').disabled = false;
            });
        }
    </script>
</body>
</html>
"""

@location_bp.route('/share_location/<user_id>')
def share_location_page(user_id):
    """Render the location sharing page."""
    from flask import current_app
    base_url = current_app.config.get('BASE_URL', 'http://localhost:5000')
    
    return render_template_string(
        LOCATION_PAGE_HTML,
        user_id=user_id,
        base_url=base_url
    )

@location_bp.route('/save_location', methods=['POST'])
def save_location():
    """Save user's location to database and automatically send supplier list."""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        accuracy = data.get('accuracy')
        
        if not all([user_id, latitude, longitude]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Import here to avoid circular imports
        from supabase_client import supabase
        import asyncio
        
        # Save to database
        result = supabase.table('user_locations').upsert({
            'user_id': user_id,
            'latitude': float(latitude),
            'longitude': float(longitude),
            'accuracy': float(accuracy) if accuracy else None,
            'updated_at': 'now()'
        }, on_conflict='user_id').execute()
        
        print(f"DEBUG_LOCATION: Saved location for {user_id}: ({latitude}, {longitude})")
        if accuracy:
            print(f"DEBUG_LOCATION: GPS Accuracy: {accuracy} meters")
        
        # Get human-readable address using reverse geocoding (Google, else free OSM)
        try:
            from google_maps_helper import reverse_geocode
            place = reverse_geocode(float(latitude), float(longitude))
            formatted_address = place.get("formatted_address") or "Unknown"
            city = place.get("city") or "Delhi"
            area = place.get("area") or "Delhi"
            print(f"DEBUG_LOCATION: Address: {formatted_address}")
            print(f"DEBUG_LOCATION: City: {city}")
            print(f"DEBUG_LOCATION: Area: {area}")
        except Exception as e:
            print(f"DEBUG_LOCATION: Could not get address: {e}")
        
        # Automatically fetch and send supplier list OR opportunities
        try:
            from google_maps_helper import get_nearby_suppliers, format_suppliers_message
            
            # Get user intent from app module
            import sys
            app_module = sys.modules.get('app')
            call_states = getattr(app_module, 'call_states', {})
            user_state = call_states.get(user_id, {})
            intent = user_state.get("location_intent", "suppliers") # Default to suppliers
            
            print(f"DEBUG_LOCATION: User intent is '{intent}'")

            if user_id not in call_states:
                call_states[user_id] = {}
            call_states[user_id]["state"] = "awaiting_low_stock_option"

            if intent == "opportunities":
                print(f"DEBUG_LOCATION: Starting opportunity analysis for {user_id}")
                
                # Send "Analyzing..." message first
                if app_module:
                    send_whatsapp_message = app_module.send_whatsapp_message
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(send_whatsapp_message(user_id, "🔍 **स्थान प्राप्त हुआ!**\nस्थानीय इवेंट्स और अवसरों की खोज की जा रही है..."))
                    loop.close()

                # Get city/area for analysis
                from google_maps_helper import reverse_geocode
                place = reverse_geocode(float(latitude), float(longitude))
                city = place.get("city") or "Delhi"
                area = place.get("area") or "Delhi"

                # Run analysis
                from opportunity_manager import analyze_opportunities
                
                # We need to run async function from sync context
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                analysis_result = loop.run_until_complete(analyze_opportunities(user_id, latitude, longitude, city, area))
                loop.close()
                
                # Send result
                import os
                import twilio.rest
                TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
                TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
                TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
                if not TWILIO_WHATSAPP_NUMBER.startswith("whatsapp:"):
                    TWILIO_WHATSAPP_NUMBER = "whatsapp:" + TWILIO_WHATSAPP_NUMBER
                
                disable_whatsapp = os.getenv("DISABLE_WHATSAPP_NOTIFICATIONS", "false").lower() == "true"
                
                if not disable_whatsapp:
                    twilio_client = twilio.rest.Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                    message = twilio_client.messages.create(
                        body=analysis_result,
                        from_=TWILIO_WHATSAPP_NUMBER,
                        to=user_id
                    )
                    print(f"DEBUG_LOCATION: Sent analysis to {user_id}")
                else:
                    print(f"DEBUG_LOCATION: WhatsApp disabled. Analysis result:\n{analysis_result}")

            else:
                # Default behavior: Find Suppliers
                print(f"DEBUG_LOCATION: Starting automatic supplier search for {user_id}")
                
                # Fetch suppliers
                suppliers = get_nearby_suppliers(
                    latitude=float(latitude),
                    longitude=float(longitude),
                    radius=5000,
                    keyword="wholesale supplier grocery",
                    max_results=10
                )
                
                print(f"DEBUG_LOCATION: Found {len(suppliers)} suppliers")
                
                # Print supplier details to terminal
                if suppliers:
                    print("=" * 80)
                    print(f"SUPPLIERS NEAR ({latitude}, {longitude}) - Within 5km: {len(suppliers)}")
                    print("=" * 80)
                else:
                    print(f"No suppliers found within 5km of ({latitude}, {longitude})")
                
                # Format message
                supplier_list_message = format_suppliers_message(suppliers, language='hi')
                
                # Send WhatsApp message using Twilio directly
                import os
                import twilio.rest
                
                TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
                TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
                TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
                
                if not TWILIO_WHATSAPP_NUMBER.startswith("whatsapp:"):
                    TWILIO_WHATSAPP_NUMBER = "whatsapp:" + TWILIO_WHATSAPP_NUMBER
                
                # Check if WhatsApp notifications are disabled
                disable_whatsapp = os.getenv("DISABLE_WHATSAPP_NOTIFICATIONS", "false").lower() == "true"
                
                if not disable_whatsapp:
                    twilio_client = twilio.rest.Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                    
                    message = twilio_client.messages.create(
                        body=supplier_list_message,
                        from_=TWILIO_WHATSAPP_NUMBER,
                        to=user_id
                    )
                    
                    print(f"DEBUG_LOCATION: Automatically sent supplier list to {user_id} (Message SID: {message.sid})")
                else:
                    print(f"DEBUG_LOCATION: WhatsApp notifications disabled, skipping automatic supplier list")
                
        except Exception as e:
            print(f"ERROR_LOCATION: Failed to process location intent: {e}")
            import traceback
            traceback.print_exc()
            # Don't fail the location save if this fails
        
        return jsonify({
            'success': True,
            'message': 'Location saved successfully',
            'latitude': latitude,
            'longitude': longitude
        })
        
    except Exception as e:
        print(f"ERROR_LOCATION: Failed to save location: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
