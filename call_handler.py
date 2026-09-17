import os
from twilio.rest import Client as TwilioRestClient # Renamed for clarity in this file
import asyncio
from app import omnidim_client # Import OmniDimension client and config
# Load environment variables
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
# Removed TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER") # This is the Twilio Voice enabled number
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
OMNIDIM_AGENT_ID= os.getenv("OMNIDIM_AGENT_ID")
OMNIDIM_FROM_NUMBER =  os.getenv("OMNIDIM_FROM_NUMBER")
# Removed OMNIDIM_API_KEY = os.getenv("OMNIDIM_API_KEY")
# Removed OMNIDIM_FROM_NUMBER_ID = os.getenv("OMNIDIM_FROM_NUMBER_ID") # New: OmniDimension 'from' number ID for outbound calls

twilio_rest_client = TwilioRestClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
# Removed omnidimension_client = OmniDimensionClient(OMNIDIM_API_KEY)

# --- Mock Data and Helper Functions (for now, will be replaced with proper imports/db fetches) ---
SUPPLIERS = {
    "Supplier A": {
        "phone": "+919971129359",
        "items": {
            "rice": {"price_per_unit": 45.0, "unit": "kg"},
            "flour": {"price_per_unit": 30.0, "unit": "kg"},
        }
    },
    "Supplier B": {
        "phone": "+919971129359",
        "items": {
            "rice": {"price_per_unit": 47.0, "unit": "kg"},
            "flour": {"price_per_unit": 28.0, "unit": "kg"},
        }
    },
}

MESSAGES = {
    "en": {
        "order_confirmed_shopkeeper": "✅ Order for {quantity} {unit} of {item_name} from {supplier_name} confirmed and stock updated. Expected delivery in 2 days.",
        "order_failed_shopkeeper": "❌ Failed to confirm order for {item_name} from {supplier_name}. Reason: {reason}"
    },
    "hi": {
        "order_confirmed_shopkeeper": "✅ {item_name} के {quantity} {unit} का {supplier_name} से ऑर्डर पुष्ट हो गया है। स्टॉक अपडेट कर दिया गया है। डिलीवरी 2 दिनों में अपेक्षित है।",
        "order_failed_shopkeeper": "❌ Failed to confirm order for {item_name} from {supplier_name}. Reason: {reason}"
    }
}

async def send_whatsapp_message(to_number: str, message_body: str, critical: bool = False):
    """
    Send a WhatsApp message via Twilio.
    
    Args:
        to_number: Recipient's WhatsApp number
        message_body: Message content
        critical: If True, raise exception on failure. If False, just log and continue.
    """
    # Check if WhatsApp notifications are disabled
    disable_notifications = os.getenv("DISABLE_WHATSAPP_NOTIFICATIONS", "false").lower() == "true"
    if disable_notifications:
        print(f"INFO: WhatsApp notifications disabled. Skipping message to {to_number}. Message: {message_body}")
        return
    
    try:
        print(f"DEBUG: Attempting to send WhatsApp message to {to_number} from {TWILIO_WHATSAPP_NUMBER}. Message: {message_body}")
        message = await asyncio.to_thread(
            twilio_rest_client.messages.create,
            to=to_number,
            from_=TWILIO_WHATSAPP_NUMBER,
            body=message_body
        )
        print(f"DEBUG: WhatsApp message sent successfully. SID: {message.sid}")
    except Exception as e:
        error_msg = str(e)
        # Check if it's a Twilio daily limit error
        if "exceeded" in error_msg.lower() and "limit" in error_msg.lower():
            print(f"WARNING: Twilio daily message limit exceeded. Cannot send WhatsApp notification to {to_number}.")
            print(f"WARNING: Message content (not sent): {message_body}")
            print(f"INFO: Core functionality (calls) will continue to work.")
        else:
            print(f"ERROR: Failed to send WhatsApp message to {to_number}: {e}")
        
        # Only raise if this is a critical message
        if critical:
            raise

# This will now be handled by app.py's MESSAGES dictionary
# def get_message(lang: str, key: str, **kwargs) -> str:
#     # Placeholder for message retrieval. In a real scenario, this would come from app.py MESSAGES dictionary.
#     messages = {
#         "en": {
#             "call_initiated": "Initiating call to {supplier_name} at {supplier_phone_number} for {quantity} {unit} of {item_name}. I will notify you once the order is confirmed.",
#             "order_confirmed_shopkeeper": "✅ Order for {quantity} {unit} of {item_name} from {supplier_name} confirmed and stock updated. Expected delivery in 2 days.",
#             "order_failed_shopkeeper": "❌ Failed to confirm order for {item_name} from {supplier_name}. Reason: {reason}"
#         }
#     }
#     return messages.get(lang, messages["en"]).get(key, f"Missing message for {key}").format(**kwargs)

# --- End Mock Data and Helper Functions ---

# Add this debugging function to your code to test the OmniDimension API connection

async def debug_omnidimension_connection():
    """Debug function to test OmniDimension API connection and agent access."""
    try:
        print(f"DEBUG: Testing OmniDimension connection...")
        print(f"DEBUG: Using Agent ID: {OMNIDIM_AGENT_ID}")
        print(f"DEBUG: Using From Number ID: {OMNIDIM_FROM_NUMBER}")
        
        # First, try to list available agents to verify API access
        try:
            agents = await asyncio.to_thread(omnidim_client.agent.list_agents)
            print(f"DEBUG: Available agents: {agents}")
            
            # Check if our agent ID exists in the list
            agent_found = any(agent.id == int(OMNIDIM_AGENT_ID) for agent in agents)
            print(f"DEBUG: Agent ID {OMNIDIM_AGENT_ID} found: {agent_found}")
            
        except Exception as e:
            print(f"ERROR: Failed to list agents: {e}")
            return False
        
        # Try to get specific agent details
        try:
            agent_details = await asyncio.to_thread(
                omnidim_client.agent.get_agent,
                agent_id=int(OMNIDIM_AGENT_ID)
            )
            print(f"DEBUG: Agent details: {agent_details}")
            
        except Exception as e:
            print(f"ERROR: Failed to get agent details: {e}")
            return False
        
        # Test a simple API call (like listing phone numbers)
        try:
            phone_numbers = await asyncio.to_thread(omnidim_client.phone_number.list_phone_numbers)
            print(f"DEBUG: Available phone numbers: {phone_numbers}")
            
            # Check if our from number exists
            from_number_found = any(phone.id == int(OMNIDIM_FROM_NUMBER) for phone in phone_numbers)
            print(f"DEBUG: From Number ID {OMNIDIM_FROM_NUMBER} found: {from_number_found}")
            
        except Exception as e:
            print(f"ERROR: Failed to list phone numbers: {e}")
            return False
            
        return True
        
    except Exception as e:
        print(f"ERROR: General OmniDimension API error: {e}")
        return False

# Modified version of your initiate_outbound_call function with better error handling
# Add this debugging function to your code to test the OmniDimension API connection

async def debug_omnidimension_connection():
    """Debug function to test OmniDimension API connection and agent access."""
    try:
        print(f"DEBUG: Testing OmniDimension connection...")
        print(f"DEBUG: Using Agent ID: {OMNIDIM_AGENT_ID}")
        print(f"DEBUG: Using From Number ID: {OMNIDIM_FROM_NUMBER}")
        
        # First, try to list available agents to verify API access
        try:
            agents = await asyncio.to_thread(omnidim_client.agent.list_agents)
            print(f"DEBUG: Available agents: {agents}")
            
            # Check if our agent ID exists in the list
            agent_found = any(agent.id == int(OMNIDIM_AGENT_ID) for agent in agents)
            print(f"DEBUG: Agent ID {OMNIDIM_AGENT_ID} found: {agent_found}")
            
        except Exception as e:
            print(f"ERROR: Failed to list agents: {e}")
            return False
        
        # Try to get specific agent details
        try:
            agent_details = await asyncio.to_thread(
                omnidim_client.agent.get_agent,
                agent_id=int(OMNIDIM_AGENT_ID)
            )
            print(f"DEBUG: Agent details: {agent_details}")
            
        except Exception as e:
            print(f"ERROR: Failed to get agent details: {e}")
            return False
        
        # Test a simple API call (like listing phone numbers)
        try:
            phone_numbers = await asyncio.to_thread(omnidim_client.phone_number.list_phone_numbers)
            print(f"DEBUG: Available phone numbers: {phone_numbers}")
            
            # Check if our from number exists
            from_number_found = any(phone.id == int(OMNIDIM_FROM_NUMBER) for phone in phone_numbers)
            print(f"DEBUG: From Number ID {OMNIDIM_FROM_NUMBER} found: {from_number_found}")
            
        except Exception as e:
            print(f"ERROR: Failed to list phone numbers: {e}")
            return False
            
        return True
        
    except Exception as e:
        print(f"ERROR: General OmniDimension API error: {e}")
        return False

# Modified version of your initiate_outbound_call function with better error handling
import os
import asyncio
from app import omnidim_client, OMNIDIM_AGENT_ID, OMNIDIM_FROM_NUMBER_ID

# --- Main Functions ---

async def initiate_outbound_call(to_number: str, order_details: str, supplier_name: str, user_id: str) -> str | None:
    """Initiates an outbound call to a supplier with a list of items."""
    
    # --- Step 1: Validate environment variables before use ---
    agent_id_str = os.getenv("OMNIDIM_AGENT_ID")
    from_number_id_str = os.getenv("OMNIDIM_FROM_NUMBER")
    api_key = os.getenv("OMNIDIM_API_KEY")

    print(f"DEBUG_CALL: Environment check - OMNIDIM_AGENT_ID: {agent_id_str}, OMNIDIM_FROM_NUMBER: {from_number_id_str}, OMNIDIM_API_KEY: {'SET' if api_key else 'MISSING'}")

    if not agent_id_str or not from_number_id_str:
        print("ERROR_CALL: Missing OMNIDIM_AGENT_ID or OMNIDIM_FROM_NUMBER in .env file.")
        return None

    if not api_key:
        print("ERROR_CALL: Missing OMNIDIM_API_KEY in .env file.")
        return None

    # Check if omnidim_client is properly initialized
    if omnidim_client is None:
        print("ERROR_CALL: omnidim_client is not initialized. Check OMNIDIM_API_KEY.")
        return None

    # Validate that OMNIDIM_FROM_NUMBER is a numeric ID, not a phone number
    # Phone numbers typically start with + or have 10+ digits, IDs are smaller integers
    import re
    if re.match(r'^\+?\d{10,}$', from_number_id_str):
        print(f"ERROR_CALL: OMNIDIM_FROM_NUMBER appears to be a phone number ({from_number_id_str}), but it should be a numeric ID.")
        print(f"ERROR_CALL: Please check your OmniDimension dashboard for the correct 'from_number_id' (it should be a small integer like 12345, not a phone number).")
        return None

    try:
        # Convert to integer - this will fail if it's not a valid integer
        from_number_id_int = int(from_number_id_str)
        agent_id_int = int(agent_id_str)
        
        print(f"DEBUG_CALL: Initiating outbound call to {to_number} using OmniDimension.")
        print(f"DEBUG_CALL: Agent ID: {agent_id_int}, From Number ID: {from_number_id_int}")
        
        # Parse order_details to extract individual items
        # Format: "5kg atta, 2kg chawal" -> extract first item for now
        # OmniDimension agent expects: item_name, quantity, unit
        
        def parse_order_items(order_str: str):
            """Parse order string like '5kg atta, 2kg chawal' into structured items."""
            items = []
            # Split by comma to get individual items
            parts = [p.strip() for p in order_str.split(',')]
            
            for part in parts:
                # Try to extract quantity, unit, and item name
                # Pattern: "5kg atta" or "2 kg chawal" or "10 किलो चावल"
                import re
                match = re.match(r'(\d+\.?\d*)\s*([a-zA-Z]+|किलो|ग्राम|लीटर)\s+(.+)', part, re.IGNORECASE)
                if match:
                    quantity = match.group(1)
                    unit = match.group(2).lower()
                    item_name = match.group(3).strip()
                    
                    # Normalize units
                    unit_map = {
                        'kg': 'किलो',
                        'g': 'ग्राम', 
                        'l': 'लीटर',
                        'litre': 'लीटर',
                        'liter': 'लीटर',
                        'किलो': 'किलो',
                        'ग्राम': 'ग्राम',
                        'लीटर': 'लीटर'
                    }
                    unit_hindi = unit_map.get(unit, unit)
                    
                    # Translate common item names to Hindi for the agent
                    item_map = {
                        'atta': 'आटा',
                        'chawal': 'चावल',
                        'rice': 'चावल',
                        'flour': 'आटा',
                        'basmati': 'बासमती',
                        'dal': 'दाल',
                        'oil': 'तेल',
                        'sugar': 'चीनी',
                        'salt': 'नमक'
                    }
                    
                    # Try to translate item name
                    item_words = item_name.lower().split()
                    translated_words = [item_map.get(word, word) for word in item_words]
                    item_name_hindi = ' '.join(translated_words)
                    
                    items.append({
                        'item_name': item_name_hindi,
                        'quantity': quantity,
                        'unit': unit_hindi,
                        'original': part
                    })
                else:
                    print(f"DEBUG_PARSE: Could not parse item: '{part}'")
            
            return items
        
        # Parse the order
        parsed_items = parse_order_items(order_details)
        print(f"DEBUG_PARSE: Parsed {len(parsed_items)} items from order: {parsed_items}")
        
        # Create context with all items, but prioritize first item for the agent's variables
        # (since the agent prompt expects single item_name, quantity, unit)
        context_for_call = {
            "order_details": order_details,
            "items": order_details,
            "order_text": order_details,
            "products": order_details,
            "supplier_name": supplier_name,
            "user_id": user_id,
        }
        
        # Add individual item variables for the first item (agent expects these)
        if parsed_items:
            first_item = parsed_items[0]
            context_for_call["item_name"] = first_item['item_name']
            context_for_call["quantity"] = first_item['quantity']
            context_for_call["unit"] = first_item['unit']
            
            # If multiple items, create a combined instruction
            if len(parsed_items) > 1:
                all_items_str = ", ".join([f"{item['quantity']} {item['unit']} {item['item_name']}" for item in parsed_items])
                context_for_call["task"] = f"Order the following items: {all_items_str}"
                context_for_call["goal"] = f"Confirm availability and price for: {all_items_str}"
                context_for_call["additional_items"] = all_items_str
                context_for_call["prompt_instruction"] = f"You are ordering multiple items: {all_items_str}. Start with {first_item['quantity']} {first_item['unit']} {first_item['item_name']}, then mention the other items."
            else:
                context_for_call["task"] = f"Order {first_item['quantity']} {first_item['unit']} {first_item['item_name']}"
                context_for_call["goal"] = f"Confirm availability and price for {first_item['item_name']}"
                context_for_call["prompt_instruction"] = f"You must order ONLY: {first_item['quantity']} {first_item['unit']} {first_item['item_name']}"
        else:
            # Fallback if parsing fails
            context_for_call["item_name"] = order_details
            context_for_call["quantity"] = "1"
            context_for_call["unit"] = "unit"
            context_for_call["task"] = f"Order: {order_details}"
            context_for_call["prompt_instruction"] = f"Order these items: {order_details}"

        
        print(f"DEBUG_CALL: Call context: {context_for_call}")

        call_response = await asyncio.to_thread(
            omnidim_client.call.dispatch_call,
            agent_id=agent_id_int,
            to_number=to_number,
            from_number_id=from_number_id_int,
            call_context=context_for_call
        )
        
        print(f"DEBUG_CALL: Raw call response type: {type(call_response)}")
        print(f"DEBUG_CALL: Raw call response: {call_response}")

        # Handle different response formats
        if isinstance(call_response, dict):
            if call_response.get('json', {}).get('success'):
                request_id = call_response.get('json', {}).get('requestId', 'unknown')
                print(f"DEBUG_CALL: OmniDimension Call dispatched successfully. Request ID: {request_id}")
                return request_id
            else:
                error_msg = call_response.get('json', {}).get('error', 'Unknown error')
                print(f"ERROR_CALL: Call dispatch failed. Error: {error_msg}")
                print(f"ERROR_CALL: Full response: {call_response}")
                return None
        elif hasattr(call_response, 'success') and call_response.success:
            # If it's an object and has a requestId attribute (hypothetically)
            request_id = getattr(call_response, 'requestId', 'unknown_obj_id')
            print(f"DEBUG_CALL: OmniDimension Call dispatched successfully. Request ID: {request_id}")
            return request_id
        else:
            print(f"ERROR_CALL: Call dispatch failed or returned unexpected format. Response: {call_response}")
            return None
            
    except AttributeError as e:
        print(f"ERROR_CALL: AttributeError - OmniDimension client may not be properly initialized.")
        print(f"ERROR_CALL: Error details: {repr(e)}")
        print(f"ERROR_CALL: Check if omnidim_client.call.dispatch_call exists")
        return None
    except ValueError as e:
        print(f"ERROR_CALL: ValueError - Invalid parameter (likely agent_id or from_number_id is not a valid integer).")
        print(f"ERROR_CALL: Error details: {repr(e)}")
        return None
    except Exception as e:
        print(f"ERROR_CALL: Failed to initiate outbound call via OmniDimension to {to_number}")
        print(f"ERROR_CALL: Exception type: {type(e).__name__}")
        print(f"ERROR_CALL: Error details: {repr(e)}")
        import traceback
        print(f"ERROR_CALL: Traceback: {traceback.format_exc()}")
        return False

# Environment variables validation function
def validate_environment_variables():
    """Validate all required environment variables are set."""
    required_vars = [
        'OMNIDIM_API_KEY',
        'OMNIDIM_AGENT_ID', 
        'OMNIDIM_FROM_NUMBER',
        'TWILIO_ACCOUNT_SID',
        'TWILIO_AUTH_TOKEN',
        'TWILIO_WHATSAPP_NUMBER'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"ERROR: Missing required environment variables: {missing_vars}")
        return False
    
    print("DEBUG: All required environment variables are set")
    return True

# The following functions related to local call handling are no longer needed
# as OmniDimension will manage the conversation entirely.

# Removed @call_bp.route("/omnidim_callback", methods=["POST", "GET"])
# Removed async def omnidim_callback(): and its content as it's now in app.py
# The following functions related to local call handling are no longer needed
# as OmniDimension will manage the conversation entirely.
# async def generate_speech_from_text(text: str) -> str:
#     pass
# async def transcribe_speech_from_url(audio_url: str) -> str:
#     pass
# call_states = {} # No longer managing call state locally
# @call_bp.route("/audio/<filename>")
# async def serve_audio(filename):
#     pass
# @call_bp.route("/voice", methods=['POST'])
# async def voice_webhook():
#     pass
# @call_bp.route("/call/handle_input", methods=['POST'])
# async def handle_call_input():
#     pass
