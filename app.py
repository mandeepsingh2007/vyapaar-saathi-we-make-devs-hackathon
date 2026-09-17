import asyncio
import copy
from datetime import date
import logging
import os
import re
from threading import Thread
from multiprocessing import Manager
import json

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from flask import Flask, request, send_from_directory
from fuzzywuzzy import fuzz
from twilio.twiml.messaging_response import MessagingResponse
import twilio.rest
import omnidimension

from data_extractor import (
    extract_items_from_bill_image,
    extract_structured_data,
    transcribe_audio,
)
from supabase_client import (
    get_daily_sales_summary,
    get_low_stock_items,
    get_stock_levels,
    get_user_transactions_summary,
    save_transaction,
    supabase,
    update_stock_item,
    get_all_unique_user_ids_with_stock,
    get_user_location,
    save_user_location,
)

# FFmpeg path configuration
ffmpeg_bin_path = r"C:\Users\singh\Downloads\ffmpeg-8.0-essentials_build\ffmpeg-8.0-essentials_build\bin"
if ffmpeg_bin_path not in os.environ["PATH"]:
    os.environ["PATH"] += os.pathsep + ffmpeg_bin_path
    print(f"DEBUG: Added {ffmpeg_bin_path} to PATH for Flask app.")

load_dotenv(override=True)

# !! IMPORTANT !!
# Replace this with your actual public URL (e.g., from ngrok or your deployed server)
BASE_URL = os.getenv("BASE_URL", "https://0068-106-219-121-225.ngrok-free.app")

# Hackathon demo: only "2" (location link) and "3" (opportunities) reply on WhatsApp.
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

SHOPKEEPER_LOCATION = {"latitude": 28.7041, "longitude": 77.1025} # Default to Delhi, India
DEFAULT_LANGUAGE = "hi" # Define default language

OMNIDIM_FROM_NUMBER = os.getenv("OMNIDIM_FROM_NUMBER") # OmniDimension 'from' number for outbound calls
OMNIDIM_API_KEY = os.getenv("OMNIDIM_API_KEY")
OMNIDIM_FROM_NUMBER_ID = os.getenv("OMNIDIM_AGENT_ID")

from gemini_client import generate_text, generate_json
omnidim_client = omnidimension.Client(OMNIDIM_API_KEY)

app = Flask(__name__)
app.config['BASE_URL'] = BASE_URL  # Make BASE_URL available to blueprints
scheduler = AsyncIOScheduler() # Initialize scheduler here

# Register location sharing blueprint
from location_handler import location_bp
app.register_blueprint(location_bp)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
if TWILIO_WHATSAPP_NUMBER and not TWILIO_WHATSAPP_NUMBER.startswith("whatsapp:"):
    TWILIO_WHATSAPP_NUMBER = "whatsapp:" + TWILIO_WHATSAPP_NUMBER
print(f"DEBUG_TWILIO_INIT: Final TWILIO_WHATSAPP_NUMBER after prefix logic: {TWILIO_WHATSAPP_NUMBER}")

TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER") # Twilio Voice enabled number
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("gemini_api_key")
OMNIDIM_AGENT_ID = os.getenv("OMNIDIM_AGENT_ID")

twilio_client = twilio.rest.Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
INBOUND_BOT_NUMBER = None


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))




# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

language_map = {"en": "en", "english": "en", "hi": "hi", "hindi": "hi",
                "pa": "pa", "punjabi": "pa", "gu": "gu", "gujarati": "gu",
                "ta": "ta", "tamil": "ta", "te": "te", "telugu": "te",
                "bn": "bn", "bengali": "bn", "mr": "mr", "marathi": "mr",
                "ur": "hi", "urdu": "hi"}

MESSAGES = {
    "en": {
        "sale_success": "✅ Sale of ₹{amount:.2f} recorded for:\n{item_details}",
        "sale_success_no_item": "✅ Sale of ₹{amount:.2f} added to your records.",
        "expense_success": "✅ Expense of ₹{amount} ({item}) recorded.",
        "expense_success_no_item": "✅ Expense of ₹{amount} recorded.",
        "balance_inquiry": "📊 Your current digital khata balance is ₹{balance:.2f}.\n\nRecent Transactions:\n{transactions_summary}",
        "earnings_summary": "📈 Today's total sales: ₹{total_sales:.2f}.\n\nToday's transactions:\n{sales_details}",
        "extract_fail": "Could not extract structured data from your message. Please be more specific (e.g., 'Sold 1kg sugar for 50 rupees').",
        "transcribe_fail": "Could not understand your voice note. The audio quality might be poor or not in a supported language.",
        "download_fail": "Failed to download your voice note: {error_msg}. Please try again.",
        "network_error": "A network error occurred while downloading your voice note: {error_msg}. Please try again.",
        "file_error": "There was an issue with the voice note file: {error_msg}. Please try sending it again.",
        "unexpected_error": "An unexpected error occurred while processing your voice note. Please try again.",
        "no_voice_note": "Please send a voice note for transaction processing or a text message for balance inquiry.",
        "unsupported_media": "Unsupported media type: {media_type}. Please send a voice note or an image.",
        "no_transactions_found": "No recent transactions found.",
        "no_sales_found_today": "No sales found today.",
        "image_received_stock_update": "Image received! Processing for stock update...",
        "stock_update_success": "✅ Stock updated successfully for: {updates}.",
        "stock_update_fail": "❌ Failed to update stock from image. Error: {error_msg}",
        "file_download_error": "Failed to download your image: {error_msg}. Please try again.",
        "welcome": "Hello! I'm your inventory management bot. How can I help you?",
        "stock_updated": "Stock for {item_name} updated successfully. Current quantity: {current_quantity} {unit}.",
        "sale_recorded": "Sale of {quantity} {unit} of {item_name} recorded. Remaining stock: {current_quantity} {unit}. Total sale amount: {selling_amount}. Profit: {profit}.",
        "purchase_recorded": "Purchase of {quantity} {unit} of {item_name} recorded. New stock: {current_quantity} {unit}. Cost: {cost_price_per_unit} per {unit}.",
        "item_not_found": "'{item_name}' not found in stock. Would you like to add it?",
        "unknown_command": "I didn't understand that. Please try again or type 'help'.",
        "current_stock": "Current stock for {item_name}: {current_quantity} {unit}.",
        "all_stock_items": "Your current stock:\n{stock_list}",
        "daily_summary": "Daily Sales Summary for {date}:\nTotal Sales: {total_sales}\nTotal Profit: {total_profit}\n{sales_details}",
        "low_stock_alert": "⚠️ Low stock alert! The following items are running low:\n{low_stock_items_list}\nPlease consider ordering soon.",
        "call_initiated": "Initiating call to {supplier_name} at {supplier_phone_number} for {quantity} {unit} of {item_name}. I will notify you once the order is confirmed.",
        "order_confirmation_prompt": "Which item and supplier would you like to confirm an order for? Example: 'Order 10 kg rice from Supplier A'.",
        "order_confirmed_shopkeeper": "✅ Order for {quantity} {unit} of {item_name} from {supplier_name} confirmed. Expect delivery in 2 days.",
        "order_failed_shopkeeper": "❌ Failed to confirm order for {item_name} from {supplier_name}. Reason: {reason}"
    },
    "hi": {
        "sale_success": "✅ आपके डिजिटल खाते में ₹{amount:.2f} की बिक्री दर्ज की गई है:\n{item_details}",
        "sale_success_no_item": "✅ आपके डिजिटल खाते में ₹{amount:.2f} की बिक्री दर्ज की गई है।",
        "expense_success": "✅ आपके डिजिटल खाते में ₹{amount} ({item}) का खर्च दर्ज किया गया है।",
        "expense_success_no_item": "✅ आपके डिजिटल खाते में ₹{amount} का खर्च दर्ज किया गया है।",
        "balance_inquiry": "📊 आपके डिजिटल खाते में वर्तमान शेष राशि ₹{balance:.2f} है।\n\nहालिया लेनदेन:\n{transactions_summary}",
        "earnings_summary": "📈 आज की कुल बिक्री: ₹{total_sales:.2f}।\n\nआज के लेनदेन:\n{sales_details}",
        "extract_fail": "आपके वॉइस नोट से डेटा निकाला नहीं जा सका। कृपया स्पष्ट बोलें।",
        "transcribe_fail": "आपके वॉइस नोट को समझा नहीं जा सका। ऑडियो गुणवत्ता खराब हो सकती है या यह समर्थित भाषा में नहीं है।",
        "download_fail": "आपका वॉइस नोट डाउनलोड नहीं हो सका: {error_msg}। कृपया पुनः प्रयास करें।",
        "network_error": "आपका वॉइस नोट डाउनलोड करते समय नेटवर्क त्रुटि हुई: {error_msg}. कृपया पुनः प्रयास करें।",
        "file_error": "वॉइस नोट फ़ाइल में समस्या थी: {error_msg}। कृपया इसे फिर से भेजें।",
        "unexpected_error": "एक अप्रत्याशित त्रुटि हुई। कृपया पुनः प्रयास करें।",
        "no_voice_note": "कृपया लेनदेन के लिए एक वॉइस नोट भेजें या शेष राशि जानने के लिए टेक्स्ट मैसेज करें।",
        "unsupported_media": "असमर्थित मीडिया प्रकार: {media_type}. कृपया एक वॉइस नोट या एक इमेज भेजें।",
        "no_transactions_found": "कोई हालिया लेनदेन नहीं मिला।",
        "image_received_stock_update": "छवि प्राप्त हुई! स्टॉक अपडेट के लिए प्रक्रिया की जा रही है...",
        "stock_update_success": "✅ स्टॉक सफलतापूर्वक अपडेट किया गया: {updates}.",
        "stock_update_fail": "❌ छवि से स्टॉक अपडेट करने में असफल। त्रुटि: {error_msg}",
        "file_download_error": "आपकी छवि डाउनलोड नहीं हो सकी: {error_msg}। कृपया पुनः प्रयास करें।",
        "welcome": "नमस्ते! मैं आपका इन्वेंटरी प्रबंधन बॉट हूं। मैं आपकी कैसे मदद कर सकता हूं?",
        "stock_updated": "{item_name} का स्टॉक सफलतापूर्वक अपडेट किया गया। वर्तमान मात्रा: {current_quantity} {unit}.",
        "sale_recorded": "{quantity} {unit} {item_name} की बिक्री दर्ज की गई। शेष स्टॉक: {current_quantity} {unit}. कुल बिक्री राशि: {selling_amount}. लाभ: {profit}.",
        "purchase_recorded": "{quantity} {unit} {item_name} की खरीद दर्ज की गई। नया स्टॉक: {current_quantity} {unit}. लागत: {cost_price_per_unit} प्रति {unit}.",
        "item_not_found": "'{item_name}' स्टॉक में नहीं मिली। क्या आप इसे जोड़ना चाहेंगे?",
        "unknown_command": "मुझे समझ नहीं आया। कृपया पुनः प्रयास करें या 'सहायता' टाइप करें।",
        "current_stock": "{item_name} का वर्तमान स्टॉक: {current_quantity} {unit}.",
        "all_stock_items": "आपका वर्तमान स्टॉक:\n{stock_list}",
        "daily_summary": "{date} के लिए दैनिक बिक्री सारांश:\nकुल बिक्री: {total_sales}\nकुल लाभ: {total_profit}\n{sales_details}",
        "low_stock_alert": "⚠️ कम स्टॉक की चेतावनी! निम्नलिखित वस्तुएं कम हो रही हैं:\n{low_stock_items_list}",
        "low_stock_options_prompt": "आप क्या करना चाहेंगे? कृपया एक विकल्प चुनें:",
        "option_1_provide_number": "1. सप्लायर का फोन नंबर दें और ऑर्डर करें",
        "option_2_list_suppliers": "2. आस-पास के सप्लायरों की सूची दें",
        "request_supplier_number_prompt": "कृपया उस सप्लायर का फोन नंबर दें जिसे आप ऑर्डर करना चाहते हैं। (उदाहरण के लिए, '+919876543210')",
        "no_suppliers_found_nearby": "आपके आस-पास कोई सप्लायर नहीं मिला। कृपया बाद में प्रयास करें।",
        "call_initiated": "{item_name} के {quantity} {unit} के लिए {supplier_name} ({supplier_phone_number}) को कॉल शुरू किया जा रहा है। ऑर्डर की पुष्टि होने पर मैं आपको सूचित करूंगा।",
        "order_confirmation_prompt": "आप किस आइटम और आपूर्तिकर्ता के लिए ऑर्डर की पुष्टि करना चाहेंगे? उदाहरण: 'सप्लायर ए से 10 किलो चावल ऑर्डर करें'।",
        "order_confirmed_shopkeeper": "✅ {item_name} के {quantity} {unit} का {supplier_name} से ऑर्डर पुष्ट हो गया है। स्टॉक अपडेट कर दिया गया है। डिलीवरी 2 दिनों में अपेक्षित है।",
        "order_failed_shopkeeper": "❌ {item_name} का {supplier_name} से ऑर्डर पुष्ट करने में विफल। कारण: {reason}"
    },
    "pa": { # Punjabi messages
        "sale_success": "✅ ਤੁਹਾਡੇ ਡਿਜੀਟਲ ਖਾਤੇ ਵਿੱਚ ₹{amount:.2f} ({item}) ਦੀ ਵਿਕਰੀ ਦਰਜ ਕੀਤੀ ਗਈ ਹੈ।",
        "sale_success_no_item": "✅ ਤੁਹਾਡੇ ਡਿਜੀਟਲ ਖਾਤੇ ਵਿੱਚ ₹{amount:.2f} ਦੀ ਵਿਕਰੀ ਦਰਜ ਕੀਤੀ ਗਈ ਹੈ।",
        "expense_success": "✅ ਤੁਹਾਡੇ ਡਿਜੀਟਲ ਖਾਤੇ ਵਿੱਚ ₹{amount} ({item}) ਦਾ ਖਰਚ ਦਰਜ ਕੀਤਾ ਗਿਆ ਹੈ।",
        "expense_success_no_item": "✅ ਤੁਹਾਡੇ ਡਿਜੀਟਲ ਖਾਤੇ ਵਿੱਚ ₹{amount} ਦਾ ਖਰਚ ਦਰਜ ਕੀਤਾ ਗਿਆ ਹੈ।",
        "balance_inquiry": "📊 ਤੁਹਾਡੇ ਡਿਜੀਟਲ ਖਾਤੇ ਵਿੱਚ ਵਰਤਮਾਨ ਬੈਲੇਂਸ ₹{balance:.2f} ਹੈ।\n\nਹਾਲੀਆ ਲੈਣ-ਦੇਣ:\n{transactions_summary}",
        "extract_fail": "ਤੁਹਾਡੇ ਵੌਇਸ ਨੋਟ ਤੋਂ ਡਾਟਾ ਕੱਢਿਆ ਨਹੀਂ ਜਾ ਸਕਿਆ। ਕਿਰਪਾ ਕਰਕੇ ਸਪਸ਼ਟ ਬੋਲੋ।",
        "transcribe_fail": "ਤੁਹਾਡਾ ਵੌਇਸ ਨੋਟ ਟ੍ਰਾਂਸਕ੍ਰਾਈਬ ਜਾਂ ਅਨੁਵਾਦ ਨਹੀਂ ਕੀਤਾ ਜਾ ਸਕਿਆ। ਆਡੀਓ ਗੁਣਵੱਤਾ ਖਰਾਬ ਹੋ ਸਕਦੀ ਹੈ।",
        "download_fail": "ਤੁਹਾਡਾ ਵੌਇਸ ਨੋਟ ਡਾਊਨਲੋਡ ਨਹੀਂ ਹੋ ਸਕਿਆ: {error_msg}। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
        "network_error": "ਤੁਹਾਡਾ ਵੌਇਸ ਨੋਟ ਡਾਊਨਲੋਡ ਕਰਦੇ ਸਮੇਂ ਨੈੱਟਵਰਕ ਤਰੁੱਟੀ ਹੋਈ: {error_msg}. ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
        "file_error": "ਵੌਇਸ ਨੋਟ ਫਾਈਲ ਵਿੱਚ ਸਮੱਸਿਆ ਸੀ: {error_msg}। ਕਿਰਪਾ ਕਰਕੇ ਇਸਨੂੰ ਫਿਰ ਤੋਂ ਭੇਜੋ।",
        "unexpected_error": "ਇੱਕ ਅਣਕਿਆਸੀ ਤਰੁੱਟੀ ਹੋਈ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
        "no_voice_note": "ਕਿਰਪਾ ਕਰਕੇ ਲੈਣ-ਦੇਣ ਲਈ ਇੱਕ ਵੌਇਸ ਨੋਟ ਭੇਜੋ ਜਾਂ ਬੈਲੇਂਸ ਜਾਣਨ ਲਈ ਟੈਕਸਟ ਮੈਸੇਜ ਕਰੋ।",
        "unsupported_media": "ਅਸਮਰਥਿਤ ਮੀਡੀਆ ਕਿਸਮ: {media_type}. ਕਿਰਪਾ ਕਰਕੇ ਇੱਕ ਵੌਇਸ ਨੋਟ ਜਾਂ ਇੱਕ ਚਿੱਤਰ ਭੇਜੋ।",
        "no_transactions_found": "ਕੋਈ ਹਾਲੀਆ ਲੈਣ-ਦੇਣ ਨਹੀਂ ਮਿਲਿਆ।",
        "image_received_stock_update": "ਤਸਵੀਰ ਪ੍ਰਾਪਤ ਹੋਈ! ਸਟਾਕ ਅੱਪਡੇਟ ਲਈ ਪ੍ਰਕਿਰਿਆ ਕੀਤੀ ਜਾ ਰਹੀ ਹੈ...",
        "stock_update_success": "✅ ਸਟਾਕ ਸਫਲਤਾ੍ਪੂਰ੍ਵਕ ਅੱਪਡੇਟ ਕੀਤਾ ਗਿਆ: {updates}.",
        "stock_update_fail": "❌ ਤਸਵੀਰ ਤੋਂ ਸਟਾਕ ਅੱਪਡੇਟ ਕਰਨ ਵਿੱਚ ਅਸਫਲ। ਤਰੁੱਟੀ: {error_msg}",
        "file_download_error": "ਤੁਹਾਡੀ ਤਸਵੀਰ ਡਾਊਨਲੋਡ ਨਹੀਂ ਹੋ ਸਕੀ: {error_msg}। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
        "welcome": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ ਤੁਹਾਡਾ ਇਨਵੈਂਟਰੀ ਪ੍ਰਬੰਧਨ ਬੋਟ ਹਾਂ। ਮੈਂ ਤੁਹਾਡੀ ਕਿൽ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
        "stock_updated": "{item_name} ਦਾ ਸਟਾਕ ਸਫਲਤਾਪੂਰਵਕ ਅੱਪਡੇਟ ਕੀਤਾ ਗਿਆ। ਮੌਜੂਦਾ ਮਾਤਰਾ: {current_quantity} {unit}.",
        "sale_recorded": "{quantity} {unit} {item_name} ਦੀ ਵਿਕਰੀ ਦਰਜ ਕੀਤੀ ਗਈ। ਬਾਕੀ ਸਟਾਕ: {current_quantity} {unit}. ਕੁੱਲ ਵਿਕਰੀ ਰਾਸ਼ੀ: {selling_amount}. ਲਾਭ: {profit}.",
        "purchase_recorded": "{quantity} {unit} {item_name} ਦੀ ਖਰੀਦ ਦਰਜ ਕੀਤੀ ਗਈ। ਨਵો ਸਟਾਕ: {current_quantity} {unit}. ਲਾਗਤ: {cost_price_per_unit} ਪ੍ਰਤੀ {unit}.",
        "item_not_found": "'{item_name}' ਸਟਾਕ ਵਿੱਚ ਨਹੀਂ ਮਿਲਿਆ। ਕੀ ਤੁਸੀਂ ਇਸਨੂੰ ਜੋੜਨਾ ਚਾਹੋਗੇ?",
        "unknown_command": "ਮੈਨੂੰ ਸਮਝ ਨਹੀਂ ਆਇਆ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ ਜਾਂ 'ਸਹਾਇਤਾ' ਟਾਈਪ ਕਰੋ।",
        "current_stock": "{item_name} ਦਾ ਮੌਜੂਦਾ ਸਟਾਕ: {current_quantity} {unit}.",
        "all_stock_items": "ਤੁਹਾਡਾ ਮੌਜੂਦਾ ਸਟਾਕ:\n{stock_list}",
        "daily_summary": "{date} ਲਈ ਰੋਜ਼ਾਨਾ ਵਿਕਰੀ ਸੰਖੇਪ:\nਕੁੱਲ ਵਿਕਰੀ: {total_sales}\nਕੁੱਲ ਲਾਭ: {total_profit}\n{sales_details}",
        "low_stock_alert": "⚠️ ਘੱਟ ਸਟਾਕ ਚੇਤਾਵਨੀ! ਹੇਠਾਂ ਦਿੱਤੀਆਂ ਚੀਜ਼ਾਂ ਘੱਟ ਹੋ ਰਹੀਆਂ ਹਨ:\n{low_stock_items_list}",
        "low_stock_options_prompt": "आप क्या करना चाहेंगे? कृपया एक विकल्प चुनें:",
        "option_1_provide_number": "1. सप्लायर का फोन नंबर दें और ऑर्डर करें",
        "option_2_list_suppliers": "2. आस-पास के सप्लायरों की सूची दें",
        "request_supplier_number_prompt": "कृपया उस सप्लायर का फोन नंबर दें जिसे आप ऑर्डर करना चाहते हैं। (उदाहरण के लिए, '+919876543210')",
        "no_suppliers_found_nearby": "आपके आस-पास कोई सप्लायर नहीं मिला। कृपया बाद में प्रयास करें।",
        "call_initiated": "{item_name} के {quantity} {unit} के लिए {supplier_name} ({supplier_phone_number}) को कॉल शुरू किया जा रहा है। ऑर्डर की पुष्टि होने पर मैं आपको सूचित करूंगा।",
        "order_confirmation_prompt": "आप किस आइटम और आपूर्तिकर्ता के लिए ऑर्डर की पुष्टि करना चाहेंगे? उदाहरण: 'सप्लायर ए से 10 किलो चावल ऑर्डर करें'।",
        "order_confirmed_shopkeeper": "✅ {item_name} के {quantity} {unit} का {supplier_name} से ऑर्डर पुष्ट हो गया है। स्टॉक अपडेट कर दिया गया है। डिलीवरी 2 दिनों में अपेक्षित है।",
        "order_failed_shopkeeper": "❌ {item_name} का {supplier_name} से ऑर्डर पुष्ट करने में विफल। कारण: {reason}"
    },
    "gu": { # Gujarati messages
        "sale_success": "✅ તમારા ડિજિટલ ખાતામાં ₹{amount:.2f} ({item}) ની વેચાણ નોંધાઈ છે.",
        "sale_success_no_item": "✅ તમારા ડિજિટલ ખાતામાં ₹{amount:.2f} ની વેચાણ નોંધાઈ છે.",
        "expense_success": "✅ તમારા ડિજિટલ ખાતામાં ₹{amount} ({item}) નો ખર્ચ નોંધાયો છે.",
        "expense_success_no_item": "✅ તમારા ડિજિટલ ખાતામાં ₹{amount} નો ખર્ચ નોંધાયો છે.",
        "balance_inquiry": "📊 તમારા ડિજિટલ ખાતામાં વર્તમાન બેલેન્સ ₹{balance:.2f} છે।\n\nછેલ્લા વ્યવહારો:\n{transactions_summary}",
        "extract_fail": "તમારા વૉઇસ નોટમાંથી માહિતી કાઢી શકાઈ નથી. કૃપા કરીને સ્પષ્ટ બોલો.",
        "transcribe_fail": "તમારો વૉઇસ નોટ ટ્રાન્સક્રાઇબ અથવા અનુવાદ કરી શકાયું નથી. ઑડિયો ગુણવત્તા નબળી હોઈ શકે છે.",
        "download_fail": "તમારો વૉઇસ નોટ ડાઉનલોડ થઈ શક્યો નથી: {error_msg}. કૃપા કરીને ફરી પ્રયાસ કરો.",
        "network_error": "તમારો વૉઇસ નોટ ડાઉનલોડ કરતી વખતે નેટવર્ક ભૂલ થઈ: {error_msg}. કૃપા કરીને ફરી પ્રયાસ કરો.",
        "file_error": "વૉઇસ નૉટ ફાઇલમાં સમਸ્ય હતી: {error_msg}। કૃપા કરીને તેને ફરીથી મોકલો.",
        "unexpected_error": "તમારા વૉઇસ નોટ પર પ્રક્રિયા કરતી વખતે અણ્ધારી ભૂલ થઈ. કૃપા કરીને ફરી પ્રયાસ કરો.",
        "no_voice_note": "કૃપા કરીને વ્યવહાર પ્રક્રિયા માટે વૉઇસ નોટ મોકલો અથવા બેલેન્સ પૂછવા માટે ટેક્સ્ટ સંદેશ મોકલો.",
        "unsupported_media": "અસમર્થિત મીડિયા પ્રકાર: {media_type}। કૃપા કરીને એક વૉઇસ નોટ અથવા એક છબી મોકલો।",
        "no_transactions_found": "કોઈ તાજેતરના વ્યવહારો મળ્યા નથી।",
        "image_received_stock_update": "છબી પ્રાપ્ત ો રહી છે...",
        "stock_update_success": "✅ સ્ટોક સફળતા્ਪੂૂર્વક અપડેટ થયો: {updates}.",
        "stock_update_fail": "❌ છબીમાંથી સ્ટોક અપડેટ કરવામાં નિષ્ફળ. ભૂલ: {error_msg}",
        "file_download_error": "તમારી છબી ડાઉનલોડ થઈ શકી નથી: {error_msg}. કૃપા કરીને ફરી પ્રયાસ કરો.",
        "welcome": "નમસ્તે! હું તમારી ઇન્વેન્ટ્રી મેનેજમેન્ટ બોટ છું. હું તમને કેવી રીતે મદદ કરી શકું?",
        "stock_updated": "{item_name} નો સ્ટોક સ્ફળતાપૂર્વક અપડેટ થયો. વર્તમાન જથ્થો: {current_quantity} {unit}.",
        "sale_recorded": "{quantity} {unit} {item_name} નું વેચાણ નોંધાઈ. બાકી સ્ટોક: {current_quantity} {unit}. કુલ વેચાણ રકમ: {selling_amount}. નફો: {profit}.",
        "purchase_recorded": "{quantity} {unit} {item_name} ની ખਰીਦી નોંધાઈ. નਵો સ્ટોક: {current_quantity} {unit}. ખર્ચ: {cost_price_per_unit} ਪ੍ਰਤੀ {unit}.",
        "item_not_found": "'{item_name}' સ્ટોક વਿੱਚ નਹੀં મਿલੀ. કੀ તੁસੀં ઇસનੂં જੋડવા ચાહੋગੇ?",
        "unknown_command": "મੈਨੂੰ સਮઝ નਹੀં ਆયા. કਿਰਪਾ કਰਕੇ દੁਬਾਰਾ કੋਸ਼ਿਸ਼ ਕਰੋ જਾਂ 'સહાયતા' ਟਾਈਪ કોડો.",
        "current_stock": "{item_name} દਾ મੌજੂદા સ્ટોક: {current_quantity} {unit}.",
        "all_stock_items": "તੁਹાડા મੌજੂદા સ્ટોક:\n{stock_list}",
        "daily_summary": "{date} લਈ રੋજ਼ਾਨਾ ਵਿਕਰੀ ਸੰਖੇਪ:\nਕੁੱਲ ਵਿਕਰੀ: {total_sales}\nਕੁੱਲ ਲਾਭ: {total_profit}\n{sales_details}",
        "low_stock_alert": "⚠️ ਘੱਟ સਟਾક ોંચું! હੇઠાં દਿੱਤੀਆਂ ਚੀਜ਼ਾਂ ਘੱਟ ਹੋ રહી છે:\n{low_stock_items_list}\nજલ્દੀ હੀ આર્ડર કરની કથા ભાવુન।",
        "low_stock_options_prompt": "ਤੁਸੀਂ ਕੀ ਕਰਨਾ ਚਾਹੋਗੇ? ਕਿਰਪਾ ਕਰਕੇ ਇੱਕ ਵਿਕल्प ਚੁਣੋ:",
        "option_1_provide_number": "1. ਸਪਲਾਇਰ ਦਾ ਫੋਨ ਨੰਬਰ ਦਿਓ ਅਤੇ ਆਰਡਰ ਕਰੋ",
        "option_2_list_suppliers": "2. ਨੇੜਲੇ ਸਪਲਾਇਰਾਂ ਦੀ ਸੂਚੀ ਦਿਓ",
        "request_supplier_number_prompt": "ਕਿਰਪਾ ਕਰਕੇ ਉਸ ਸਪਲਾਇਰ ਦਾ ਫੋਨ ਨੰਬਰ ਦਿਓ ਜਿਸਨੂੰ ਤੁਸੀਂ ਆਰਡਰ ਕਰਨਾ ਚਾਹੁੰਦੇ ਹੋ। (ਉਦਾਹਰਨ ਲਈ, '+919876543210')",
        "no_suppliers_found_nearby": "ਤੁਹਾਡੇ ਨੇੜੇ ਕੋਈ ਸਪਲਾਇਰ ਨਹੀਂ ਮਿਲਿਆ। ਕਿਰਪਾ ਕਰਕੇ ਬਾਅਦ ਵਿੱਚ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
        "call_initiated": "{item_name} ਦੇ {quantity} {unit} ਲਈ {supplier_name} ({supplier_phone_number}) ਨੂੰ ਕਾਲ ਸ਼ੁਰੂ ਕੀਤਾ ਜਾ ਰਿਹਾ ਹੈ। ਆਰਡਰ ਦੀ ਪੁਸ਼ਟੀ ਹੋਣ 'ਤੇ ਮੈਂ ਤੁਹਾਨੂੰ ਸੂਚਿਤ ਕਰૂਂਗਾ।",
        "order_confirmation_prompt": "ਤੁਸੀਂ ਕਿਸ ਆਈਟਮ ਅਤੇ ਸਪਲਾਇਰ ਲਈ ਆਰਡਰ ਦੀ ਪੁਸ਼ਟੀ ਕਰਨਾ ਚਾਹੋਗੇ? ਉदाहरण: 'ਸਪਲਾਇਰ ਏ ਤੋਂ 10 ਕਿਲੋ ਚਾਵਲ ਆਰਡਰ ਕਰੋ'।",
        "order_confirmed_shopkeeper": "✅ {item_name} ਦੇ {quantity} {unit} ਦਾ {supplier_name} ਤੋਂ ਆਰਡਰ पुष्ट हो गया है। स्टॉक अपडेट कर दिया गया है। डिलीवरी 2 दिनों में अपेक्षित है।",
        "order_failed_shopkeeper": "❌ {item_name} च्या {supplier_name} कडून ऑर्डर पुष्ट करने में विफल। कारण: {reason}"
    },
    "te": { # Telugu messages
        "sale_success": "✅ మీ డిజిటల్ ఖాతాలో ₹{amount:.2f} ({item}) అమ్మకం జోడించబడింది.",
        "sale_success_no_item": "✅ మీ డిజిటల్ ఖాతాలో ₹{amount:.2f} అమ్మకం జోడించబడింది.",
        "expense_success": "✅ మీ డిజిటల్ ఖాతాలో ₹{amount} ({item}) ఖర్చు నమోదు చేయబడింది.",
        "expense_success_no_item": "✅ మీ డిజిటల్ ఖాతాలో ₹{amount} ఖర్చు నమోదు చేయబడింది.",
        "balance_inquiry": "📊 మీ డిజిటల్ ఖాతాలో ప్రస్తుత బ్యాలెన్స్ ₹{balance:.2f} ఉంది.\n\nతాజా లావాదేవీలు:\n{transactions_summary}",
        "extract_fail": "మీ వాయిస్ నోట్ నుండి డేటాను సేకరించలేము. దయచేసి స్పష్టంగా మాట్లాడండి.",
        "transcribe_fail": "మీ వాయిస్ నోట్‌ను లిప్యంతరీకరించడం లేదా అననువదించడం సాధయం కాలేదు. ఆడియో నాణ్యత తక్కువగా ఉండవచ్చు.",
        "download_fail": "మీ వాయిస్ నోట్‌ను డౌన్‌లోడ్ చేయడంలో విఫలమైంది: {error_msg}. దయచేసి మళ్లీ ప్రయత్నించండి.",
        "network_error": "మీ వాయిస్ నోట్‌ను డౌన్‌లోడ్ చేస్తున్నప్పుడు నెట్‌వర్క్ లోపం సంభవించింది: {error_msg}. దయచేసి మళ్లీ ప్రయత్నించండి.",
        "file_error": "వాయిస్ నోట్ ఫైల్‌లో సమస్య ఉంది: {error_msg}। దయచేసి దాన్ని మళ్లీ పంపండి.",
        "unexpected_error": "మీ వాయిస్ నోట్‌ను ప్రాసెస్ చేస్తున్నప్పుడు ఊహించని లోపం సంభవించింది. దయచేసి మళ్లీ ప్రయత్నించండి.",
        "no_voice_note": "దయచేసి లావాదేవీల ప్రాసెసింగ్ కోసం వాయిస్ నోట్ పంపండి లేదా బ్యాలెన్స్ విచారణ కోసం టెక్స్ట్ సందેశం పంపండి.",
        "unsupported_media": "మద్దతు లేని మీడియా రకం: {media_type}। దయచేసి వాయిస్ నోట్ లేదా చిత్రాన్ని పంపండి.",
        "no_transactions_found": "తాజా లావాదేవీలు ఏవీ కనుగొనబడలేదు.",
        "image_received_stock_update": "చిత్రం స్వీకరించబడింది! స్టాక్ అప్‌డేట్ కోసం ప్రాసెస్ చేయబడుతోంది...",
        "stock_update_success": "✅ స్టాక్ విజయవంతంగా నవీకరించబడింది: {updates}.",
        "stock_update_fail": "❌ చిత్రం నుండి స్టాక్‌ను నవీకరించడంలో విఫలమైంది. లోపం: {error_msg}",
        "file_download_error": "మీ చిత్రం డౌన్‌లోడ్ చేయడంలో విఫలమైంది: {error_msg}. దయచేసి మళ్లీ ప్రయత్నించండి.",
        "welcome": "నమస్కారం! నేను మీ ఇన్వెంటరీ నిర్వహణ బాట్ ని. నేను మీకు ఎలా సహాయం చేయగలను?",
        "stock_updated": "{item_name} నిల్వ విజయవంతంగా నవీకరించబడింది. ప్రస్తుత పరిమాణం: {current_quantity} {unit}.",
        "sale_recorded": "{quantity} {unit} {item_name} అమ్మకం నమోదు చేయబడింది. మిగిలిన నిల్వ: {current_quantity} {unit}. మొత్తం అమ్మకపు మొత్తం: {selling_amount}. లాభం: {profit}.",
        "purchase_recorded": "{quantity} {unit} {item_name} కొనుగోలు నమోదు చేయబడింది. కొత్త నిల్వ: {current_quantity} {unit}. ధర: {cost_price_per_unit} ప్రతి {unit}.",
        "item_not_found": "'{item_name}' నిల్వలో కనుగొనబడలేదు. మీరు దీన్ని జోడించాలనుకుంటున్నారా?",
        "unknown_command": "నాకు అర్థం కాలేదు. దయచేసి మళ్ళీ ప్రయత్నించండి లేదా 'సహాయం' అని టైప్ చేయండి.",
        "current_stock": "{item_name} ప్రస్తుత నిల్వ: {current_quantity} {unit}.",
        "all_stock_items": "మీ ప్రస్తుత నిల్వ:\n{stock_list}",
        "daily_summary": "{date} కోసం రోజువారీ అమ్మకాల సారాంశం:\nమొత్తం అమ్మకాలు: {total_sales}\nమొత్తం లాభం: {total_profit}\n{sales_details}",
        "low_stock_alert": "⚠️ తక్కువ నిల్వ హెచ్చరిక! క్రింది అంశాలు తక్కువగా ఉన్నాయి:\n{low_stock_items_list}\nత్వరలో ఆర్డర్ చేయాలని పరిగణించండి.",
        "call_initiated": "{item_name} యొక్క {quantity} {unit} కోసం {supplier_name} ({supplier_phone_number}) కు కాల్ ప్రారంభించబడుతోంది. ఆర్డర్ నిర్ధారించబడిన తర్వాత నేను మీకు తెలియజేస్తాను.",
        "order_confirmation_prompt": "మీరు ఏ వస్తੁవు మరియు సరఫరాదారు కోసం ఆర్డర్‌ను నిర్ధారించాలనుకుంటున్నారు? ఉదాహరణ: 'సప్లయర్ A నుండి 10 కిలોల బియ్యం ఆర్డర్ చేయండి'.",
        "order_confirmed_shopkeeper": "✅ {item_name} యొక్క {quantity} {unit} కొరకు {supplier_name} నుండి ఆర్డర్ నిర్ధారించబడింది. స్టాక్ అప్‌డేట్ చేయబడింది. 2 రోజులలో డెలివరీ ఆశించబడుతుంది.",
        "order_failed_shopkeeper": "❌ {item_name} యొక్క {supplier_name} నుండి ఆర్డర్‌ను నిర్ధారించడంలో విఫలమైంది. కారణం: {reason}"
    },
    "bn": { # Bengali messages
        "sale_success": "✅ আপনার ডিজিটাল অ্যাকাউন্টে ₹{amount:.2f} ({item}) বিক্রয় যোগ করা হয়েছে।",
        "sale_success_no_item": "✅ আপনার ডিজিটাল অ্যাকাউন্টে ₹{amount:.2f} বিক্রয় যোগ করা হয়েছে।",
        "expense_success": "✅ আপনার ডিজিটাল অ্যাকাউন্টে ₹{amount} ({item}) খরচ রেকর্ড করা হয়েছে।",
        "expense_success_no_item": "✅ আপনার ডিজিটাল অ্যাকাউন্টে ₹{amount} খরচ রেকর্ড করা হয়েছে।",
        "balance_inquiry": "📊 আপনার ডিজিটাল অ্যাকাউন্টের বর্তমান ব্যালেন্স ₹{balance:.2f}।\n\nসাম্প্রতিক লেনদেন:\n{transactions_summary}",
        "extract_fail": "আপনার ভয়েস নোট থেকে ডেটা এক্সট্র্যাক্ট করা যায়নি। অনুগ্রহ করে পরিষ্কার করে বলুন।",
        "transcribe_fail": "আপনার ভয়েস নোট ট্রান্সক্রাইব বা অনুবাদ করা যায়নি। অডিও গুণমান খারাপ হতে পারে।",
        "download_fail": "আপনার ভয়েস নোট ডাউনলোড করা যায়নি: {error_msg}। অনুগ্রহ করে আবার চেষ্টা করুন।",
        "network_error": "আপনার ভয়েস নোট ডাউনলোড করার সময় একটি নেটওয়ার্ক ত্রুটি হয়েছে: {error_msg}। অনুগ্রহ করে আবার চেষ্টা করুন।",
        "file_error": "ভয়েস নোট ফাইলটিতে একটি সমস্যা ছিল: {error_msg}। অনুগ্রহ করে এটি আবার পাঠান।",
        "unexpected_error": "আপনার ভয়েস নোট প্রক্রিয়া করার সময় একটি অপ্রত্যাশিত ত্রুটি ঘটেছে। অনুগ্রহ করে আবার চেষ্টা করুন।",
        "no_voice_note": "লেনদেন প্রক্রিয়াকরণের জন্য একটি ভয়েস নোট পাঠান অথবা ব্যালেন্স জানতে একটি পাঠ্য বার্তা পাঠান।",
        "unsupported_media": "অসমর্থিত মিডিয়া প্রকার: {media_type}। অনুগ্রহ করে একটি ভয়েস নোট বা একটি ছবি পাঠান।",
        "no_transactions_found": "কোনো সাম্প্রতিক লেনদেন পাওয়া যায়নি।",
        "image_received_stock_update": "ছবি গৃহীত হয়েছে! স্টক আপডেটের জন্য প্রক্রিয়া করা হচ্ছে...",
        "stock_update_success": "✅ স্টক সফলভাবে আপডেট করা হয়েছে: {updates}.",
        "stock_update_fail": "❌ ছবি থেকে স্টক আপডেট করতে ব্যর্থ হয়েছে। ত্রুটি: {error_msg}",
        "file_download_error": "আপনার ছবি ডাউনলোড করা যায়নি: {error_msg}। অনুগ্রহ করে আবার চেষ্টা করুন।",
        "low_stock_alert": "⚠️ কম স্টক সতর্কতা! নিম্নলিখিত আইটেমগুলি কম হচ্ছে:\n{low_stock_items_list}\nশীঘ্রই অর্ডার করার কথা ভাবুন।",
        "welcome": "নমস্কার! আমি আপনার ইনভেন্টরি ম্যানেজমেন্ট বট। আমি আপনাকে কিভাবে সাহায্য করতে পারি?",
        "stock_updated": "{item_name} এর স্টক সফলভাবে আপডেট হয়েছে। বর্তমান পরিমাণ: {current_quantity} {unit}.",
        "sale_recorded": "{quantity} {unit} {item_name} এর বিক্রয় রেকর্ড করা হয়েছে। অবশিষ্ট স্টক: {current_quantity} {unit}. মোট বিক্রয় পরিমাণ: {selling_amount}. লাভ: {profit}.",
        "purchase_recorded": "{quantity} {unit} {item_name} এর ক্রয় রেকর্ড করা হয়েছে। নতুন স্টক: {current_quantity} {unit}. খরচ: {cost_price_per_unit} প্রতি {unit}.",
        "item_not_found": "'{item_name}' স্টক পাওয়া যায়নি। আপনি কি এটি যোগ করতে চান?",
        "unknown_command": "আমি বুঝতে পারিনি। অনুগ্রহ করে আবার চেষ্টা করুন বা 'সাহায্য' টাইপ করুন।",
        "current_stock": "{item_name} এর বর্তমান স্টক: {current_quantity} {unit}.",
        "all_stock_items": "আপনার বর্তমান স্টক:\n{stock_list}",
        "daily_summary": "{date} এর জন্য দৈনিক বিক্রয় সারাংশ:\nমোট বিক্রয়: {total_sales}\nমোট লাভ: {total_profit}\n{sales_details}",
        
        "call_initiated": "{item_name} এর {quantity} {unit} এর জন্য {supplier_name} ({supplier_phone_number}) কে কল শুরু করা হচ্ছে। অর্ডার নিশ্চিত হওয়ার পরে আমি আপনাকে জানাবো।",
        "order_confirmation_prompt": "আপনি কোন আইটেম এবং সরবরাহকারীর জন্য অর্ডার নিশ্চিত করতে চান? উদাহরণ: 'সাপ্লায়ার এ থেকে 10 কেজি চাল অর্ডার করুন'.",
        "order_confirmed_shopkeeper": "✅ {item_name} এর {quantity} {unit} এর জন্য {supplier_name} থেকে অর্ডার নিশ্চিত হয়েছে। স্টক আপডেট করা হয়েছে। 2 দিনের মধ্যে ডেলিভারি আশা করা হচ্ছে।",
        "order_failed_shopkeeper": "❌ {item_name} এর {supplier_name} থেকে অর্ডার নিশ্চিত করা যায়নি। কারণ: {reason}"
    },
    "mr": { # Marathi messages
        "sale_success": "✅ तुमच्या डिजिटल खात्यात ₹{amount:.2f} ({item}) ची विक्री नोंदवली गेली आहे.",
        "sale_success_no_item": "✅ तुमच्या डिजिटल खात्यात ₹{amount:.2f} ची विक्री नोंदवली गेली आहे.",
        "expense_success": "✅ तुमच्या डिजिटल खात्यात ₹{amount} ({item}) चा खर्च नोंदवला गेला आहे.",
        "expense_success_no_item": "✅ तुमच्या डिजिटल खात्यात ₹{amount} चा खर्च नोंदवला गेला आहे.",
        "balance_inquiry": "📊 तुमच्या डिजिटल खात्यातील सध्याची शिल्लक ₹{balance:.2f} आहे.\n\nअलीकडील व्यवहार:\n{transactions_summary}",
        "extract_fail": "तुमच्या व्हॉइस नोटमधून डेटा काढता आला नाही. कृपया स्पष्ट बोला.",
        "transcribe_fail": "तुमचा व्हॉइस नोट ट्रान्सक्राइब किंवा अनुवादित करता आला नाही. ऑडिओ गुणवत्ता खराब असू शकते.",
        "download_fail": "तुमचे व्हॉइस नोट डाउनलोड करण्यात अयशस्वी: {error_msg}. कृपया पुन्हा प्रयत्न करा.",
        "network_error": "तुमचे व्हॉइस नोट डाउनलोड करताना नेटवर्क त्रुटि आली: {error_msg}. कृपया पुन्हा प्रयत्न करा.",
        "file_error": "व्हॉइस नोट फाइल्मध्ये समस्या होती: {error_msg}. कृपया ती पुन्हा पाठवा.",
        "unexpected_error": "तुमच्या व्हॉइस नोटवर प्रक्रिया करताना अनपेक्षित त्रुटी आली. कृपया पुन्हा प्रयत्न करा.",
        "no_voice_note": "कृपया व्यवहाराच्या प्रक्रियेसाठी व्हॉइस नोट पाठवा किंवा शिल्लक चौकशीसाठी मजकूर संदेश पाठवा.",
        "unsupported_media": "असमर्थित मीडिया प्रकार: {media_type}. कृपया व्हॉइस नोट किंवा इमेज पाठवा.",
        "no_transactions_found": "अलीकडील कोणतेही व्यवहार आढळले नाहीत.",
        "image_received_stock_update": "इमेज प्राप्त झाली! स्टॉक अद्ययावत करण्यासाठी प्रक्रिया सुरू आहे...",
        "stock_update_success": "✅ स्टॉक यशस्वीरित्या अद्ययावित झाला: {updates}.",
        "stock_update_fail": "❌ इमेजमधून स्टॉक अद्ययावित करण्यात अयशस्वी. त्रुटी: {error_msg}",
        "file_download_error": "तुमची इमेज डाउनलोड करण्यात अयशस्वी: {error_msg}. कृपया पुन्हा प्रयत्न करा.",
        "low_stock_alert": "⚠️ कमी स्टॉक अलर्ट! खालील वस्तू कमी होत आहेत:\n{low_stock_items_list}\nलवकरच ऑर्डर करण्याचा विचार करा।",
        "welcome": "नमस्कार! मी तुमचा इन्व्हेंटरी मॅनेजमेंट बॉट आहे. मी तुम्हाला कशी मदत करू शकतो?",
        "stock_updated": "{item_name} चा स्टॉक यशस्वीरित्या अद्ययावित झाला. सध्याची संख्या: {current_quantity} {unit}.",
        "sale_recorded": "{quantity} {unit} {item_name} ची विक्री नोंदवली गेली. उर्वरित स्टॉक: {current_quantity} {unit}. एकूण विक्री रक्कम: {selling_amount}. नफा: {profit}.",
        "purchase_recorded": "{quantity} {unit} {item_name} ची खरेदी नोंदवली गेली. नवीन स्टॉक: {current_quantity} {unit}. किंमत: {cost_price_per_unit} प्रति {unit}.",
        "item_not_found": "'{item_name}' स्टॉक मध्ये आढळले नाही. तुम्ही ते जोडू इच्छिता का?",
        "unknown_command": "मला समजले नाही. कृपया पुन्हा प्रयत्न करा किंवा 'मदत' टाइप करा.",
        "current_stock": "{item_name} चा वर्तमान स्टॉक: {current_quantity} {unit}.",
        "all_stock_items": "तुमचा वर्तमान स्टॉक:\n{stock_list}",
        "daily_summary": "{date} साठी दैनिक विक्री सारांश:\nएकूण विक्री: {total_sales}\nएकूण नफा: {total_profit}\n{sales_details}",
        
        "call_initiated": "{item_name} च्या {quantity} {unit} साठी {supplier_name} ({supplier_phone_number}) ला कॉल सुरू केला जात आहे. ऑर्डरची पुष्टी झाल्यावर मी तुम्हाला सूचित करेन।",
        "order_confirmation_prompt": "तुम्हाला कोणत्या वस्तू आणि पुरवठादारासाठी ऑर्डर निश्चित करायचा आहे? उदाहरण: 'पुरवठादार A कडून 10 किलो तांदूळ ऑर्डर करा'.",
        "order_confirmed_shopkeeper": "✅ {item_name} च्या {quantity} {unit} चा {supplier_name} कडून ऑर्डर निश्चित झाला आहे. स्टॉक अद्ययावित झाला आहे. 2 दिवसांत वितरण अपेक्षित आहे.",
        "order_failed_shopkeeper": "❌ {item_name} च्या {supplier_name} कडून ऑर्डर निश्चित करण्यात अयशस्वी. कारण: {reason}"
    }
}


SUPPLIERS = {
    "Supplier A": {
        "phone": "+919971129359",
        "items": {
            "चावल": {"price_per_unit": 45.0, "unit": "kg"},
            "आटा": {"price_per_unit": 30.0, "unit": "kg"},
            "सूजी": {"price_per_unit": 40.0, "unit": "kg"},
            "राजमा": {"price_per_unit": 120.0, "unit": "kg"},
            "मूंग दाल": {"price_per_unit": 90.0, "unit": "kg"},
            "उड़द दाल": {"price_per_unit": 100.0, "unit": "kg"},
        }
    },
    "Supplier B": {
        "phone": "+919988776655",
        "items": {
            "चावल": {"price_per_unit": 47.0, "unit": "kg"},
            "आटा": {"price_per_unit": 28.0, "unit": "kg"},
            "सूजी": {"price_per_unit": 42.0, "unit": "kg"},
            "राजमा": {"price_per_unit": 118.0, "unit": "kg"},
            "मूंग दाल": {"price_per_unit": 92.0, "unit": "kg"},
            "उड़द दाल": {"price_per_unit": 98.0, "unit": "kg"},
        }
    },
    "Supplier C": {
        "phone": "+917788990011",
        "items": {
            "चावल": {"price_per_unit": 46.0, "unit": "kg"},
            "आटा": {"price_per_unit": 31.0, "unit": "kg"},
            "सूजी": {"price_per_unit": 39.0, "unit": "kg"},
            "राजमा": {"price_per_unit": 125.0, "unit": "kg"},
            "मूंग दाल": {"price_per_unit": 88.0, "unit": "kg"},
            "उड़द दाल": {"price_per_unit": 105.0, "unit": "kg"},
        }
    }
}

class DownloadError(Exception):
    pass

async def find_cheapest_supplier_for_item(item_name: str, item_unit: str) -> dict | None:
    cheapest_supplier = None
    min_price = float('inf')

    # Normalize the item_name and item_unit for better matching
    normalized_item_name = item_name.lower().strip()
    normalized_item_unit = item_unit.lower().strip()

    print(f"DEBUG_SUPPLIER: Searching for cheapest supplier for '{normalized_item_name}' ({normalized_item_unit}).")

    for supplier_name, supplier_info in SUPPLIERS.items():
        for supplier_item_name, item_details in supplier_info["items"].items():
            normalized_supplier_item_name = supplier_item_name.lower().strip()
            supplier_item_unit = item_details["unit"].lower().strip()

            # Use fuzzy matching for item names
            name_score = max(fuzz.token_sort_ratio(normalized_item_name, normalized_supplier_item_name),
                             fuzz.partial_ratio(normalized_item_name, normalized_supplier_item_name))
            
            # Consider a high threshold for fuzzy matching to ensure accuracy
            if name_score >= 80 and normalized_item_unit == supplier_item_unit: # Also ensure units match
                price = item_details["price_per_unit"]
                print(f"DEBUG_SUPPLIER: Found match with {supplier_name} for '{supplier_item_name}' (score: {name_score}). Price: {price} {supplier_item_unit}")

                if price < min_price or (price == min_price and supplier_info["phone"] == "+919971129359"):
                    min_price = price
                    cheapest_supplier = {
                        "supplier_name": supplier_name,
                        "phone": supplier_info["phone"],
                        "item_name": supplier_item_name,
                        "price_per_unit": price,
                        "unit": supplier_item_unit
                    }
    
    if cheapest_supplier:
        print(f"DEBUG_SUPPLIER: Cheapest supplier found: {cheapest_supplier['supplier_name']} for {cheapest_supplier['item_name']} at ₹{cheapest_supplier['price_per_unit']}/{cheapest_supplier['unit']}")
    else:
        print(f"DEBUG_SUPPLIER: No cheapest supplier found for '{normalized_item_name}' ({normalized_item_unit}).")

    return cheapest_supplier

from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
import requests

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(DownloadError))
def download_media_with_retry(media_url: str, file_path: str):
    print(f"Attempting to download media from: {media_url}")
    response = requests.get(media_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN), timeout=10)
    print(f"Download response status code: {response.status_code}")
    response.raise_for_status()

    if not response.content:
        raise DownloadError(f"Downloaded content from {media_url} is empty.")

    with open(file_path, 'wb') as f:
        f.write(response.content)
    print(f"Media downloaded successfully to {file_path}")

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
        _safe_print(f"INFO: WhatsApp notifications disabled. Skipping message to {to_number}. Message: {message_body}")
        return

    from_number_whatsapp = INBOUND_BOT_NUMBER or TWILIO_WHATSAPP_NUMBER
    if from_number_whatsapp and not from_number_whatsapp.startswith("whatsapp:"):
        from_number_whatsapp = "whatsapp:" + from_number_whatsapp

    if to_number == from_number_whatsapp:
        _safe_print(f"DEBUG: Skipping sending message to self ({to_number}).")
        return
    
    try:
        _safe_print(f"DEBUG_TWILIO_FROM: sending from {from_number_whatsapp} to {to_number}")
        message = await asyncio.to_thread(
            twilio_client.messages.create,
            to=to_number,
            from_=from_number_whatsapp,
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

def _build_location_link_message(sender_id: str) -> str:
    location_share_url = f"{BASE_URL}/share_location/{sender_id}"
    return (
        "📍 **अपना स्थान साझा करें / Share Your Location**\n\n"
        "आपके आस-पास के सप्लायर खोजने के लिए कृपया अपना स्थान साझा करें:\n"
        "To find suppliers near you, please share your location:\n\n"
        f"🔗 {location_share_url}\n\n"
        "👆 इस लिंक पर क्लिक करें और \"Allow\" दबाएं\n"
        "Click the link above and tap \"Allow\"\n\n"
        "🔒 आपका स्थान सुरक्षित है और केवल सप्लायर खोजने के लिए उपयोग होगा।\n"
        "Your location is safe and will only be used to find suppliers."
    )

async def send_demo_location_link(sender_id: str) -> None:
    """Option 2: send only the shopkeeper location-sharing link."""
    global call_states
    if sender_id not in call_states:
        call_states[sender_id] = {}
    call_states[sender_id]["state"] = "waiting_for_location"
    call_states[sender_id]["location_intent"] = "suppliers"
    await send_whatsapp_message(sender_id, _build_location_link_message(sender_id))

def _send_opportunities_background(sender_id, latitude, longitude, city, area, from_number):
    """Run real event scan + Gemini off the webhook so Twilio does not time out."""
    global INBOUND_BOT_NUMBER
    INBOUND_BOT_NUMBER = from_number
    try:
        from opportunity_manager import analyze_opportunities
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        text = loop.run_until_complete(
            analyze_opportunities(
                sender_id, latitude, longitude, city, area, include_festivals=False
            )
        )
        if text:
            loop.run_until_complete(send_whatsapp_message(sender_id, text))
        loop.close()
        print("DEBUG_DEMO: Sent opportunity analysis via REST", flush=True)
    except Exception as e:
        print(f"ERROR_DEMO_OPP: {e}", flush=True)


async def send_demo_opportunities(sender_id: str) -> None:
    """Option 3: send only the business-opportunity result. No extra status texts."""
    global call_states
    user_location = await get_user_location(sender_id)
    if not user_location:
        print(f"DEBUG_DEMO: No location yet for {sender_id}, sending location link instead")
        await send_demo_location_link(sender_id)
        return

    from opportunity_manager import analyze_opportunities

    latitude = user_location["latitude"]
    longitude = user_location["longitude"]
    from google_maps_helper import reverse_geocode
    place = reverse_geocode(latitude, longitude)
    city = place.get("city") or "Delhi"
    area = place.get("area") or "Delhi"

    print(f"DEBUG_DEMO: Analyzing opportunities for {area}, {city}")
    analysis_result = await analyze_opportunities(sender_id, latitude, longitude, city, area)
    if sender_id not in call_states:
        call_states[sender_id] = {}
    call_states[sender_id]["state"] = "awaiting_low_stock_option"
    await send_whatsapp_message(sender_id, analysis_result)

@app.route("/whatsapp", methods=["POST"])
async def whatsapp_webhook():
    global call_states, active_calls, INBOUND_BOT_NUMBER
    sender_id = request.form.get('From', '')
    inbound_to = request.form.get('To', '')
    message_body = request.form.get('Body', '')
    media_url = request.form.get('MediaUrl0', None)
    media_content_type = request.form.get('MediaContentType0', None)
    current_date = date.today()
    INBOUND_BOT_NUMBER = inbound_to or TWILIO_WHATSAPP_NUMBER

    print(f"DEBUG_WEBHOOK: From={sender_id} To={inbound_to} Body={message_body!r}")

    if DEMO_MODE:
        choice = (message_body or "").strip()
        print(f"DEBUG_DEMO: Handling '{choice}' for {sender_id}")
        reply_text = None
        if choice in ["2", "2."]:
            if sender_id not in call_states:
                call_states[sender_id] = {}
            existing_location = await get_user_location(sender_id)
            print(f"DEBUG_DEMO: Option 2 location lookup for {sender_id}: {bool(existing_location)}")
            if existing_location:
                from google_maps_helper import get_nearby_suppliers, format_suppliers_message
                suppliers = get_nearby_suppliers(
                    latitude=existing_location["latitude"],
                    longitude=existing_location["longitude"],
                    radius=4000,
                    keyword="kirana wholesale grocery",
                    max_results=6,
                )
                call_states[sender_id]["state"] = "listing_suppliers"
                call_states[sender_id]["nearby_suppliers"] = suppliers
                reply_text = format_suppliers_message(suppliers, language="hi")
            else:
                call_states[sender_id]["state"] = "waiting_for_location"
                call_states[sender_id]["location_intent"] = "suppliers"
                reply_text = _build_location_link_message(sender_id)
        elif choice in ["3", "3."]:
            user_location = await get_user_location(sender_id)
            if not user_location:
                print(f"DEBUG_DEMO: No location yet for {sender_id}, sending location link instead")
                if sender_id not in call_states:
                    call_states[sender_id] = {}
                call_states[sender_id]["state"] = "waiting_for_location"
                call_states[sender_id]["location_intent"] = "suppliers"
                reply_text = _build_location_link_message(sender_id)
            else:
                from google_maps_helper import reverse_geocode
                from festival_calendar import format_festivals_message, get_upcoming_festivals
                place = reverse_geocode(user_location["latitude"], user_location["longitude"])
                city = place.get("city") or "Delhi"
                area = place.get("area") or "Delhi"
                reply_text = format_festivals_message(get_upcoming_festivals(limit=1))
                print(f"DEBUG_DEMO: Sending national festival; queue local scan for {area}, {city}", flush=True)
                Thread(
                    target=_send_opportunities_background,
                    args=(
                        sender_id,
                        user_location["latitude"],
                        user_location["longitude"],
                        city,
                        area,
                        INBOUND_BOT_NUMBER,
                    ),
                    daemon=True,
                ).start()
                if sender_id not in call_states:
                    call_states[sender_id] = {}
                call_states[sender_id]["state"] = "awaiting_low_stock_option"
        else:
            print("DEBUG_DEMO: Ignoring message — demo only replies to 2 and 3")
        resp = MessagingResponse()
        if reply_text:
            resp.message(reply_text)
        return str(resp)

    detected_language = 'en'
    original_transcription = ""
    english_translation = ""

    should_return_early = False

    balance_keywords = ["balance", "account", "kitna", "total", "shilak", "rupai", "money", "खाता", "कितने पैसे हैं", "how much money", "kitni rakam hai", "शिल्लक", "रक्कम"]
    earnings_keywords = ["kamai", "earnings", "profit", "aaj kii", "today's", "कितनी कमाई हुई", "आज की कमाई", "फायदा", "कमई", "how much did you earn today", "how much you earn today", "total sales today", "total earned today", "आज कमई", "कमई", "aaj ki kamai", "how much today earnings"]

    cleaned_original_transcription = ""
    cleaned_english_translation = ""

    if media_url:
        if media_content_type and 'audio' in media_content_type:
            try:
                audio_file_path = f"./temp_audio_{sender_id.replace(':', '_')}.ogg"
                download_media_with_retry(media_url, audio_file_path)

                from pydub import AudioSegment  # Ensure AudioSegment is imported

                mp3_file_path = audio_file_path.replace(".ogg", ".mp3")
                try:
                    AudioSegment.from_file(audio_file_path).export(mp3_file_path, format="mp3")
                except Exception as e:
                    print(f"Error converting audio file: {e}")
                    raise
                finally:
                    if os.path.exists(audio_file_path):
                        os.remove(audio_file_path)

                transcription_result = transcribe_audio(mp3_file_path)
                if os.path.exists(mp3_file_path):
                    os.remove(mp3_file_path)
               

                original_transcription = transcription_result["original_transcription"]
                english_translation = transcription_result["english_translation"]
                detected_language = language_map.get(transcription_result["detected_language"], 'en')
                print(f"Detected language: {detected_language}")
                print(f"Original Transcription: {original_transcription}")
                print(f"English Translation: {english_translation}")

                cleaned_original_transcription = re.sub(r'[^\w\s]', '', original_transcription, flags=re.IGNORECASE | re.UNICODE).lower().strip() if original_transcription else ''
                cleaned_english_translation = re.sub(r'[^\w\s]', '', english_translation, flags=re.IGNORECASE | re.UNICODE).lower().strip() if english_translation else ''

            except Exception as e:
                print(f"Error during voice note processing: {e}")
                reply_message = MESSAGES[detected_language]["file_error"].format(error_msg=str(e))
                await send_whatsapp_message(sender_id, reply_message)
                should_return_early = True
                original_transcription = ""
                english_translation = ""

        elif media_content_type and 'image' in media_content_type:
            try:
                image_file_path = f"./temp_image_{sender_id.replace(':', '_')}.jpg"
                download_media_with_retry(media_url, image_file_path)

                await send_whatsapp_message(sender_id, MESSAGES[detected_language]["image_received_stock_update"])

                extracted_bill_data = extract_items_from_bill_image(image_file_path)
                print(f"DEBUG_APP: Full extracted_bill_data: {extracted_bill_data}") # Add this line
                os.remove(image_file_path)

                bill_type = extracted_bill_data.get("bill_type", "unknown")
                extracted_items = extracted_bill_data.get("items", [])
                detected_language_from_bill = extracted_bill_data.get("detected_language", 'en')

                detected_language = language_map.get(detected_language_from_bill, 'en')
                print(f"DEBUG: Detected language from bill: {detected_language_from_bill} -> Normalized: {detected_language}")

                print(f"DEBUG: Extracted bill type: {bill_type}")
                print(f"DEBUG: Extracted items: {extracted_items}")

                if extracted_items:
                    update_messages = []

                    if bill_type == "unknown":
                        if any(item.get("cost_price_per_unit") is not None for item in extracted_items):
                            bill_type = "purchase"
                        elif any(item.get("selling_price_per_unit") is not None for item in extracted_items):
                            reply_message = MESSAGES[detected_language]["stock_update_fail"].format(error_msg="Sales via image are not supported. Please send sales details (item name, quantity, selling price) via voice note or text.")
                            await send_whatsapp_message(sender_id, reply_message)
                            should_return_early = True

                    if bill_type == "purchase":
                        total_bill_expense = 0.0
                        for item in extracted_items:
                            item_name = item.get("item_name")
                            quantity = item.get("quantity")
                            unit = item.get("unit", "pcs")
                            cost_price_per_unit = item.get("cost_price_per_unit")

                            if item_name and isinstance(quantity, (int, float)) and cost_price_per_unit is not None:
                                print(f"DEBUG: Processing purchase item: {item_name}, quantity={float(quantity)} {unit}, cost_price_per_unit={cost_price_per_unit}")
                                await update_stock_item(sender_id, item_name, float(quantity), unit, cost_price_per_unit)
                                update_messages.append(f"{item_name}: {quantity} {unit}")

                                # --- Robust total expense calculation ---
                                item_expense = None
                                try:
                                    per_unit_detected = False
                                    # Handle all weight/volume units
                                    weight_units = ["kg", "g", "litre", "ml"]
                                    unit_lower = str(unit).lower()
                                    # Check if unit is weight/volume and quantity > 1
                                    if unit_lower in weight_units and float(quantity) > 1.0:
                                        # Heuristic: If multiplication gives unrealistically high value, treat raw price as total for row
                                        per_unit_price = float(cost_price_per_unit) / float(quantity) if float(quantity) else float(cost_price_per_unit)
                                        # Price threshold (e.g., 500/kg as upper reasonable limit)
                                        if per_unit_price > 200: # Over 200 rupee/kg or litre, likely not per kg but for the set
                                            item_expense = float(cost_price_per_unit)
                                        else:
                                            item_expense = float(cost_price_per_unit) * float(quantity)
                                            per_unit_detected = True
                                    else:
                                        item_expense = float(cost_price_per_unit) * float(quantity)
                                        per_unit_detected = True
                                except Exception as e:
                                    print(f"EXPENSE_CALC_ERROR: {e}. Falling back to raw cost_price_per_unit.")
                                    item_expense = float(cost_price_per_unit)
                                print(f"DEBUG: Expense calc for '{item_name}': {item_expense} (per_unit={per_unit_detected})")
                                total_bill_expense += item_expense

                        if update_messages:
                            if total_bill_expense > 0:
                                expense_data = {
                                    "date": current_date.strftime('%Y-%m-%d'),
                                    "type": "expense",
                                    "amount": total_bill_expense,
                                    "item": f"Stock purchase via bill ({len(update_messages)} items)"
                                }
                                await save_transaction(expense_data, sender_id)
                                update_messages.append(f"Total expense of ₹{total_bill_expense:.2f} recorded.")

                            reply_message = MESSAGES[detected_language]["stock_update_success"].format(updates="\n".join(update_messages))
                            await send_whatsapp_message(sender_id, reply_message)
                            should_return_early = True
                        else:
                            reply_message = MESSAGES[detected_language]["stock_update_fail"].format(error_msg="Could not extract any valid items with cost prices from the purchase bill.")
                            await send_whatsapp_message(sender_id, reply_message)
                            should_return_early = True

                    elif bill_type == "sale":
                        reply_message = MESSAGES[detected_language]["stock_update_fail"].format(error_msg="Sales bills cannot be processed via image. Please send sales information via voice note or text (item name, quantity, selling price).")
                        await send_whatsapp_message(sender_id, reply_message)
                        should_return_early = True

                    else:
                        reply_message = MESSAGES[detected_language]["stock_update_fail"].format(error_msg="Could not extract any valid items or clear pricing information from the image to determine bill type.")
                        await send_whatsapp_message(sender_id, reply_message)
                        should_return_early = True

                else:
                    reply_message = MESSAGES[detected_language]["stock_update_fail"].format(error_msg="Could not extract any items from the image.")
                    await send_whatsapp_message(sender_id, reply_message)
                    should_return_early = True

            except Exception as e:
                print(f"Error during image processing: {e}")
                print(f"DEBUG: Type of exception e: {type(e)}")
                print(f"DEBUG: Content of exception e: {e}")
                reply_message = MESSAGES[detected_language]["stock_update_fail"].format(error_msg=str(e))
                await send_whatsapp_message(sender_id, reply_message)
                should_return_early = True
        else:
            print(f"Unsupported media type received: {media_content_type}")
            reply_message = MESSAGES[detected_language]["unsupported_media"].format(media_type=media_content_type)
            await send_whatsapp_message(sender_id, reply_message)
            should_return_early = True

    if should_return_early:
        return str(MessagingResponse())

    if message_body and not should_return_early:
        original_transcription = message_body
        english_translation = message_body
        print(f"Received text message: {message_body}")
        detected_language = 'en'
        cleaned_original_transcription = re.sub(r'[^\w\s]', '', original_transcription, flags=re.IGNORECASE | re.UNICODE).lower().strip() if original_transcription else ''
        cleaned_english_translation = re.sub(r'[^\w\s]', '', english_translation, flags=re.IGNORECASE | re.UNICODE).lower().strip() if english_translation else ''

    if should_return_early:
        return str(MessagingResponse())

    # Check for pending low stock alert responses
    user_state = call_states.get(sender_id, {})
    current_state = user_state.get("state")
    
    print(f"DEBUG_STATE: sender_id={sender_id}, current_state={current_state}, message_body={message_body}")

    if current_state == "awaiting_low_stock_option":
        # Handle "1" or "1." (with period)
        if message_body.strip() in ["1", "1."]:
            # Ensure call_states entry exists
            if sender_id not in call_states:
                call_states[sender_id] = {}
            
            call_states[sender_id]["state"] = "waiting_for_order_quantity"
            
            # Preserve low_stock_items if they exist
            low_stock_items = user_state.get("low_stock_items", [])
            if "low_stock_items" in user_state:
                call_states[sender_id]["low_stock_items"] = user_state["low_stock_items"]
            
            item_names = [item.get("item", "Items") for item in low_stock_items]
            items_str = ", ".join(item_names)

            print(f"DEBUG_STATE: Updated state to 'waiting_for_order_quantity' for {sender_id}")
            await send_whatsapp_message(sender_id, f"{items_str} के लिए आप कितनी मात्रा (quantity) ऑर्डर करना चाहते हैं? (उदाहरण: '10kg Atta')")
            return str(MessagingResponse())
        elif message_body.strip() in ["2", "2."]:
            # Check if user has shared their location
            user_location = await get_user_location(sender_id)
            
            if not user_location:
                # User hasn't shared location yet, send location sharing link
                # Extract user_id without 'whatsapp:' prefix for URL
                user_id_clean = sender_id.replace('whatsapp:', '').replace('+', '')
                location_share_url = f"{BASE_URL}/share_location/{sender_id}"
                
                location_request_message = (
                    "📍 **अपना स्थान साझा करें / Share Your Location**\n\n"
                    "आपके आस-पास के सप्लायर खोजने के लिए कृपया अपना स्थान साझा करें:\n"
                    "To find suppliers near you, please share your location:\n\n"
                    f"🔗 {location_share_url}\n\n"
                    "👆 इस लिंक पर क्लिक करें और \"Allow\" दबाएं\n"
                    "Click the link above and tap \"Allow\"\n\n"
                    "🔒 आपका स्थान सुरक्षित है और केवल सप्लायर खोजने के लिए उपयोग होगा।\n"
                    "Your location is safe and will only be used to find suppliers."
                )
                
                # Set state to waiting for location
                if sender_id not in call_states:
                    call_states[sender_id] = {}
                call_states[sender_id]["state"] = "waiting_for_location"
                call_states[sender_id]["location_intent"] = "suppliers"
                if "low_stock_items" in user_state:
                    call_states[sender_id]["low_stock_items"] = user_state["low_stock_items"]
                
                await send_whatsapp_message(sender_id, location_request_message)
                return str(MessagingResponse())
            
            # User has location, fetch nearby suppliers
            from google_maps_helper import get_nearby_suppliers, format_suppliers_message
            
            print(f"DEBUG_GMAPS: User selected option 2, fetching nearby suppliers...")
            print(f"DEBUG_LOCATION: Using user's saved location: ({user_location['latitude']}, {user_location['longitude']})")
            
            # Use user's actual location
            latitude = user_location['latitude']
            longitude = user_location['longitude']
            
            # Fetch suppliers from Google Maps
            suppliers = get_nearby_suppliers(
                latitude=latitude,
                longitude=longitude,
                radius=2000,  # 2km radius
                keyword="wholesale supplier grocery",
                max_results=10
            )
            
            # Format the message
            detected_language = 'hi'  # Default to Hindi
            supplier_list_message = format_suppliers_message(suppliers, language=detected_language)
            
            # Ensure call_states entry exists
            if sender_id not in call_states:
                call_states[sender_id] = {}
            call_states[sender_id]["state"] = "listing_suppliers"
            call_states[sender_id]["nearby_suppliers"] = suppliers  # Store for later reference
            if "low_stock_items" in user_state:
                call_states[sender_id]["low_stock_items"] = user_state["low_stock_items"]
            
            await send_whatsapp_message(sender_id, supplier_list_message)
            return str(MessagingResponse())
        elif message_body.strip() in ["3", "3."]:
            # Option 3: Find Business Opportunities
            
            # Check if user has shared their location
            user_location = await get_user_location(sender_id)
            
            if not user_location:
                # User hasn't shared location yet, send location sharing link
                user_id_clean = sender_id.replace('whatsapp:', '').replace('+', '')
                location_share_url = f"{BASE_URL}/share_location/{sender_id}"
                
                location_request_message = (
                    "📍 **अपना स्थान साझा करें / Share Your Location**\n\n"
                    "स्थानीय इवेंट्स और व्यापार के अवसर खोजने के लिए हमें आपका स्थान चाहिए:\n"
                    "To find local events and business opportunities, please share your location:\n\n"
                    f"🔗 {location_share_url}\n\n"
                    "👆 इस लिंक पर क्लिक करें और \"Allow\" दबाएं\n"
                    "Click the link above and tap \"Allow\"\n\n"
                    "🔒 आपका स्थान सुरक्षित है।\n"
                    "Your location is safe."
                )
                
                # Set state to waiting for location
                if sender_id not in call_states:
                    call_states[sender_id] = {}
                call_states[sender_id]["state"] = "waiting_for_location"
                call_states[sender_id]["location_intent"] = "opportunities"
                # Preserve low_stock_items if needed, though not strictly required for this feature
                if "low_stock_items" in user_state:
                    call_states[sender_id]["low_stock_items"] = user_state["low_stock_items"]
                
                await send_whatsapp_message(sender_id, location_request_message)
                return str(MessagingResponse())
            
            # User has location, proceed with analysis
            await send_whatsapp_message(sender_id, "🔍 **स्थानीय इवेंट्स और अवसरों की खोज की जा रही है...**\nकृपया प्रतीक्षा करें, इसमें कुछ सेकंड लग सकते हैं।")
            
            from opportunity_manager import analyze_opportunities
            
            # Get address details to find city/area
            latitude = user_location['latitude']
            longitude = user_location['longitude']
            from google_maps_helper import reverse_geocode
            place = reverse_geocode(latitude, longitude)
            city = place.get("city") or "Delhi"
            area = place.get("area") or "Delhi"
            
            print(f"DEBUG_OPP: Analyzing opportunities for {area}, {city}")
            
            # Run analysis
            analysis_result = await analyze_opportunities(sender_id, latitude, longitude, city, area)
            
            print("\n" + "="*80)
            print("📊 BUSINESS OPPORTUNITY ANALYSIS")
            print("="*80)
            print(analysis_result)
            print("="*80 + "\n")
            
            await send_whatsapp_message(sender_id, analysis_result)
            return str(MessagingResponse())

        else:
            await send_whatsapp_message(sender_id, "अमान्य विकल्प। कृपया '1', '2' या '3' चुनें।")
            return str(MessagingResponse())
    
    elif current_state == "waiting_for_location":
        # User is waiting for location to be shared via the link
        # Don't process their message as a transaction
        await send_whatsapp_message(
            sender_id, 
            "📍 कृपया पहले ऊपर दिए गए लिंक पर क्लिक करके अपना स्थान साझा करें।\n\n"
            "स्थान सहेजने के बाद, आपको स्वचालित रूप से आस-पास के सप्लायर की सूची मिल जाएगी।\n\n"
            "Please click the link above to share your location first.\n\n"
            "After saving your location, you'll automatically receive the list of nearby suppliers."
        )
        return str(MessagingResponse())
    
    elif current_state == "waiting_for_order_quantity":
        order_quantity_input = message_body.strip()
        
        if sender_id not in call_states:
            call_states[sender_id] = {}
            
        call_states[sender_id]["order_quantity"] = order_quantity_input
        call_states[sender_id]["state"] = "waiting_for_supplier_number"
        
        # Preserve low_stock_items
        if "low_stock_items" in user_state:
             call_states[sender_id]["low_stock_items"] = user_state["low_stock_items"]

        print(f"DEBUG_STATE: Captured order quantity '{order_quantity_input}', transitioning to 'waiting_for_supplier_number' for {sender_id}")
        await send_whatsapp_message(sender_id, "कृपया उस सप्लायर का फोन नंबर दें जिसे आप ऑर्डर करना चाहते हैं। (उदाहरण के लिए, '+919876543210' या '9971129359')")
        return str(MessagingResponse())

    elif current_state == "waiting_for_supplier_number":
        # Normalize phone number - accept with or without + prefix
        supplier_phone_number = message_body.strip()
        
        # Remove any spaces or dashes
        supplier_phone_number = re.sub(r'[\s\-]', '', supplier_phone_number)
        
        # If it's a 10-digit number (Indian format), add +91 prefix
        if re.fullmatch(r'^\d{10}$', supplier_phone_number):
            supplier_phone_number = "+91" + supplier_phone_number
            print(f"DEBUG_PHONE: Auto-added +91 prefix. Final number: {supplier_phone_number}")
        # If it starts with 91 and is 12 digits, add + prefix
        elif re.fullmatch(r'^91\d{10}$', supplier_phone_number):
            supplier_phone_number = "+" + supplier_phone_number
            print(f"DEBUG_PHONE: Auto-added + prefix. Final number: {supplier_phone_number}")
        
        # Validate phone number (with + prefix and 10-15 digits)
        if re.fullmatch(r'^\+\d{10,15}$', supplier_phone_number):
            print(f"DEBUG_PHONE: Valid phone number: {supplier_phone_number}")
            order_details_str = ""
            if "order_quantity" in user_state:
                order_details_str = user_state["order_quantity"].replace("\n", ", ").replace("\r", "")
                print(f"DEBUG_ORDER: Using user provided order quantity: {order_details_str}")
            else:
                low_stock_items = user_state.get("low_stock_items", [])
                if low_stock_items:
                    # Handle both formats: alert format (item, remaining_quantity) and full item format
                    order_details_list = []
                    for item in low_stock_items:
                        # Check if it's the alert format (from low_stock_alerts)
                        if "item" in item and "remaining_quantity" in item:
                            # Parse remaining_quantity string like "0.0 kg" or "0 pcs"
                            remaining_qty_str = item.get("remaining_quantity", "0 pcs")
                            # Extract quantity and unit from string
                            parts = remaining_qty_str.split()
                            qty = parts[0] if parts else "0"
                            unit = parts[1] if len(parts) > 1 else "pcs"
                            item_name = item.get("item", "N/A")
                            order_details_list.append(f"{qty} {unit} {item_name}")
                        else:
                            # Full item format (from database)
                            qty = item.get('quantity', 0)
                            unit = item.get('unit', 'pcs')
                            item_name = item.get('item_name', item.get('item', 'N/A'))
                            order_details_list.append(f"{qty} {unit} {item_name}")
                    order_details_str = ", ".join(order_details_list)
                    print(f"DEBUG_ORDER: Order details from low stock items: {order_details_str}")

            if order_details_str:
                from call_handler import initiate_outbound_call
                
                # Check if OmniDimension is properly configured
                if not OMNIDIM_API_KEY or not OMNIDIM_FROM_NUMBER or not os.getenv("OMNIDIM_AGENT_ID"):
                    error_msg = "OmniDimension API कॉन्फ़िगरेशन पूर्ण नहीं है। कृपया .env फ़ाइल में OMNIDIM_API_KEY, OMNIDIM_AGENT_ID, और OMNIDIM_FROM_NUMBER सेट करें।"
                    print(f"ERROR: {error_msg}")
                    await send_whatsapp_message(sender_id, error_msg)
                elif omnidim_client is None:
                    error_msg = "OmniDimension क्लाइंट प्रारंभ नहीं हो सका। कृपया OMNIDIM_API_KEY जांचें।"
                    print(f"ERROR: {error_msg}")
                    await send_whatsapp_message(sender_id, error_msg)
                else:
                    call_request_id = await initiate_outbound_call(
                        to_number=supplier_phone_number,
                        order_details=order_details_str,
                        supplier_name="Unknown Supplier", # Or try to infer from a database if available
                        user_id=sender_id
                    )

                    if call_request_id:
                        # Store the mapping of request_id to user_id
                        active_calls[str(call_request_id)] = sender_id
                        print(f"DEBUG_APP: Stored active call mapping: {call_request_id} -> {sender_id}")
                        
                        await send_whatsapp_message(sender_id, f"ऑर्डर के लिए {supplier_phone_number} को कॉल किया जा रहा है: {order_details_str}")
                    else:
                        await send_whatsapp_message(sender_id, "ऑर्डर कॉल शुरू करने में विफल रहा। कृपया सर्वर लॉग जांचें या बाद में पुनः प्रयास करें।")
            else:
                await send_whatsapp_message(sender_id, "कम स्टॉक वाली कोई वस्तु नहीं मिली और कोई मात्रा प्रदान नहीं की गई।")
            call_states.pop(sender_id, None) # Clear state
            return str(MessagingResponse())
        else:
            print(f"DEBUG_PHONE: Invalid phone number format: {supplier_phone_number}")
            await send_whatsapp_message(sender_id, "अमान्य फोन नंबर प्रारूप। कृपया सही फोन नंबर दर्ज करें (उदाहरण के लिए, '+919876543210' या '9971129359')।")
            return str(MessagingResponse())

    elif current_state == "listing_suppliers":
        selected_supplier_name = message_body.strip()
        supplier_phone_number = None
        supplier_found = False

        for name, info in SUPPLIERS.items():
            if fuzz.ratio(selected_supplier_name.lower(), name.lower()) >= 80:
                supplier_phone_number = info['phone']
                supplier_found = True
                break
        
        if supplier_found and supplier_phone_number:
            low_stock_items = user_state.get("low_stock_items", [])
            if low_stock_items:
                # Handle both formats: alert format (item, remaining_quantity) and full item format
                order_details_list = []
                for item in low_stock_items:
                    # Check if it's the alert format (from low_stock_alerts)
                    if "item" in item and "remaining_quantity" in item:
                        # Parse remaining_quantity string like "0.0 kg" or "0 pcs"
                        remaining_qty_str = item.get("remaining_quantity", "0 pcs")
                        # Extract quantity and unit from string
                        parts = remaining_qty_str.split()
                        qty = parts[0] if parts else "0"
                        unit = parts[1] if len(parts) > 1 else "pcs"
                        item_name = item.get("item", "N/A")
                        order_details_list.append(f"{qty} {unit} {item_name}")
                    else:
                        # Full item format (from database)
                        qty = item.get('quantity', 0)
                        unit = item.get('unit', 'pcs')
                        item_name = item.get('item_name', item.get('item', 'N/A'))
                        order_details_list.append(f"{qty} {unit} {item_name}")
                order_details_str = ", ".join(order_details_list)
                print(f"DEBUG_ORDER: Order details: {order_details_str}")

                from call_handler import initiate_outbound_call
                call_request_id = await initiate_outbound_call(
                    to_number=supplier_phone_number,
                    order_details=order_details_str,
                    supplier_name=selected_supplier_name,
                    user_id=sender_id
                )

                if call_request_id:
                    # Store the mapping of request_id to user_id
                    active_calls[str(call_request_id)] = sender_id
                    print(f"DEBUG_APP: Stored active call mapping: {call_request_id} -> {sender_id}")

                    await send_whatsapp_message(sender_id, f"ऑर्डर के लिए {selected_supplier_name} ({supplier_phone_number}) को कॉल किया जा रहा है: {order_details_str}")
                else:
                    await send_whatsapp_message(sender_id, "ऑर्डर कॉल शुरू करने में विफल रहा। कृपया बाद में पुनः प्रयास करें।")
            else:
                await send_whatsapp_message(sender_id, "कम स्टॉक वाली कोई वस्तु नहीं मिली।")
            call_states.pop(sender_id, None) # Clear state
            return str(MessagingResponse())
        else:
            print(f"DEBUG_SUPPLIER: Supplier not found for '{selected_supplier_name}'")
            await send_whatsapp_message(sender_id, "अमान्य सप्लायर का नाम। कृपया सूची से एक सप्लायर चुनें या '1' से स्वयं फोन नंबर दर्ज करें।")
            return str(MessagingResponse())

    if not should_return_early:
        print(f"DEBUG_APP: should_return_early at start of main processing block: {should_return_early}")

        if detected_language != 'en' and english_translation:
            text_for_extraction = english_translation
            print(f"DEBUG: Using English translation for extraction (prioritized due to non-English detected language): {text_for_extraction}")
        elif original_transcription:
            text_for_extraction = original_transcription
            print(f"DEBUG: Using original transcription for extraction (default or English detected): {text_for_extraction}")
        elif english_translation:
            text_for_extraction = english_translation
            print(f"DEBUG: Using English translation for extraction (fallback): {text_for_extraction}")
        else:
            text_for_extraction = ""
            print("DEBUG: No text available for extraction.")

        is_balance_inquiry = any(keyword in cleaned_original_transcription or keyword in cleaned_english_translation for keyword in balance_keywords)
        is_earnings_inquiry = any(keyword in cleaned_original_transcription or keyword in cleaned_english_translation for keyword in earnings_keywords)

        if is_earnings_inquiry:
            today_sales, today_sales_transactions = await get_daily_sales_summary(sender_id, current_date)

            sales_details_list = []
            if today_sales_transactions:
                for txn in today_sales_transactions:
                    txn_item = txn.get("item", "N/A")
                    txn_amount = f'{txn.get("amount", 0.0):.2f}'
                    sales_details_list.append(f"• {txn_item}: ₹{txn_amount}")
                sales_details_str = "\n".join(sales_details_list)
            else:
                sales_details_str = MESSAGES[detected_language].get("no_sales_found_today", "No sales found today.")

            reply_message = MESSAGES[detected_language]["earnings_summary"].format(
                total_sales=today_sales,
                sales_details=sales_details_str
            )
            await send_whatsapp_message(sender_id, reply_message)
            should_return_early = True

        elif is_balance_inquiry:
            total_balance, recent_transactions = await get_user_transactions_summary(sender_id)

            transactions_summary_list = []
            for txn in recent_transactions:
                txn_date = txn.get("transaction_date", "N/A")
                txn_type = txn.get("transaction_type", "N/A").capitalize()
                txn_amount = f'{txn.get("amount", "N/A"):.2f}' if isinstance(txn.get("amount"), (int, float)) else "N/A"
                txn_item = txn.get("item", "")

                formatted_txn_amount = txn_amount
                formatted_txn_date = txn_date

                summary_line = f"• Date: {formatted_txn_date}, Type: {txn_type}, Amount: ₹{formatted_txn_amount}"
                if txn_item:
                    summary_line += f" ({txn_item})"
                transactions_summary_list.append(summary_line)

            transactions_summary_str = "\n".join(transactions_summary_list) if transactions_summary_list else MESSAGES[detected_language].get("no_transactions_found", "No recent transactions found.")

            reply_message = MESSAGES[detected_language]["balance_inquiry"].format(
                balance=total_balance,
                transactions_summary=transactions_summary_str
            )

            await send_whatsapp_message(sender_id, reply_message)
            should_return_early = True

        elif (english_translation or original_transcription):
            if detected_language != 'en' and english_translation:
                text_for_extraction = english_translation
                print(f"DEBUG: Using English translation for extraction (prioritized due to non-English detected language): {text_for_extraction}")
            elif original_transcription:
                text_for_extraction = original_transcription
                print(f"DEBUG: Using original transcription for extraction (default or English detected): {text_for_extraction}")
            elif english_translation:
                text_for_extraction = english_translation
                print(f"DEBUG: Using English translation for extraction (fallback): {text_for_extraction}")
            else:
                text_for_extraction = ""
                print("DEBUG: No text available for extraction.")

            if not text_for_extraction:
                print("ERROR_APP: No valid text available for extraction after selection logic.")
                await send_whatsapp_message(sender_id, MESSAGES[detected_language]["extract_fail"])
                should_return_early = True
                return str(MessagingResponse()) # Return early

            print(f"DEBUG: Text for structured data extraction: {text_for_extraction}")
            try:
                raw_extracted_content = extract_structured_data(text_for_extraction, current_date)
                print(f"DEBUG_APP: Raw extracted content (from data_extractor): {raw_extracted_content}")
                extracted_data = copy.deepcopy(raw_extracted_content)
                print(f"DEBUG_APP: Extracted structured data (after direct deep copy): {extracted_data}")
            except Exception as e:
                print(f"ERROR_APP: Exception during data extraction or type checking: {e}")
                print(f"ERROR_APP: Type of exception: {type(e)}")
                extracted_data = {}
                should_return_early = True

            if isinstance(extracted_data, dict) and extracted_data:
                await _process_transaction_sync(
                    extracted_data,
                    sender_id,
                    detected_language,
                    current_date,
                    original_transcription,
                    english_translation
                )
            else:
                await send_whatsapp_message(sender_id, MESSAGES[detected_language]["extract_fail"])
                should_return_early = True
        else:
            await send_whatsapp_message(sender_id, MESSAGES[detected_language]["transcribe_fail"])
            should_return_early = True

    print("DEBUG_APP: whatsapp_webhook function completing.")
    return str(MessagingResponse())

async def _translate_text_to_target_language(text: str, target_language: str) -> str:
    try:
        prompt = f"""Translate the following text into {target_language}. Respond only with the translated text.
Text: {text}"""
        translated_text = generate_text(
            prompt,
            system="You are a helpful assistant that translates text.",
            temperature=0.0,
        ).strip()
        print(f"DEBUG_TRANSLATION: Original: '{text}', Translated to {target_language}: '{translated_text}'")
        return translated_text
    except Exception as e:
        print(f"ERROR_TRANSLATION: Error translating text: {e}")
        return text

async def _process_transaction_sync(extracted_data: dict, sender_id: str, detected_language: str, current_date: date, original_transcription: str, english_translation: str):
    print(f"DEBUG_APP: Entering synchronous transaction processing block with data: {extracted_data}")
    transaction_type = extracted_data.get("type", "").lower()
    print(f"DEBUG: Identified transaction type: {transaction_type}")

    profit_keywords = ["profit", "मुनाफा", "labh", "फायda", "profitability", "लाभ"]
    should_show_profit = any(keyword in original_transcription.lower() for keyword in profit_keywords) or \
                         any(keyword in english_translation.lower() for keyword in profit_keywords)

    if transaction_type == "sale":
        sales_summary_messages = []
        unprocessed_items_messages = []
        total_sales_amount = 0.0
        total_profit = 0.0

        items_sold = extracted_data.get("items_sold", [])
        if items_sold:
            stock_levels = await get_stock_levels(sender_id)
            stock_map = {f"{item['item_name']}-{item['unit']}": item for item in stock_levels}
            print(f"DEBUG_STOCK: Current stock_levels: {stock_levels}")
            print(f"DEBUG_STOCK: Current stock_map keys: {list(stock_map.keys())}")

            target_stock_language = "hi"

            for item in items_sold:
                item_name = item.get("item_name")
                quantity = item.get("quantity")
                unit = item.get("unit", "pcs")
                selling_amount = item.get("selling_amount")

                print(f"DEBUG_ITEM_PROCESSING: Processing extracted item: {{'item_name': '{item_name}', 'quantity': {quantity}, 'unit': '{unit}', 'selling_amount': {selling_amount}}}")

                if item_name and isinstance(quantity, (int, float)) and isinstance(selling_amount, (int, float)):
                    stock_item_name_for_lookup = item_name

                    contains_latin = bool(re.search(r'[a-zA-Z]', item_name))

                    if contains_latin and target_stock_language == "hi":
                        translated_item_name = await _translate_text_to_target_language(item_name, target_stock_language)
                        stock_item_name_for_lookup = translated_item_name
                        print(f"DEBUG: Extracted item name '{item_name}' contains Latin characters and target stock language is Hindi. Translated to '{translated_item_name}' for stock lookup.")
                    elif detected_language != target_stock_language:
                        translated_item_name = await _translate_text_to_target_language(item_name, target_stock_language)
                        stock_item_name_for_lookup = translated_item_name
                        print(f"DEBUG: Incoming item '{item_name}' (detected_lang={detected_language}) translated to '{translated_item_name}' (target_lang={target_stock_language}) for stock lookup.")
                    else:
                        print(f"DEBUG: Incoming item '{item_name}' (detected_lang={detected_language}) is already in target stock language ({target_stock_language}) or no translation needed. No translation performed.")

                    best_match_item_name = None
                    best_match_score = 0.0

                    print(f"DEBUG_FUZZY: Starting fuzzy match for '{stock_item_name_for_lookup}'")
                    for stock_item_obj in stock_levels:
                        item_name_in_stock = stock_item_obj['item_name']
                        current_score = max(fuzz.token_sort_ratio(stock_item_name_for_lookup.lower(), item_name_in_stock.lower()),
                                            fuzz.partial_ratio(stock_item_name_for_lookup.lower(), item_name_in_stock.lower()))
                        print(f"DEBUG_FUZZY: Comparing '{stock_item_name_for_lookup}' with stock item '{item_name_in_stock}'. Score: {current_score}")

                        if current_score > best_match_score:
                            best_match_score = current_score
                            best_match_item_name = item_name_in_stock

                    print(f"DEBUG_FUZZY: Best fuzzy match for '{stock_item_name_for_lookup}': '{best_match_item_name}' with score {best_match_score}")

                    if best_match_item_name and best_match_score >= 40:
                        original_lookup_name_before_fuzzy = stock_item_name_for_lookup
                        stock_item_name_for_lookup = best_match_item_name
                        print(f"DEBUG_FUZZY: Fuzzy match successful. Using '{stock_item_name_for_lookup}' (originally '{original_lookup_name_before_fuzzy}') for stock lookup.")
                    else:
                        print(f"DEBUG_FUZZY: No strong fuzzy match found for '{stock_item_name_for_lookup}' (score: {best_match_score}). Proceeding with original lookup name.")
                        pass

                    print(f"DEBUG_ITEM_MATCH: Attempting to find final stock item for '{stock_item_name_for_lookup}' with effective unit '{unit}'")
                    stock_key = f"{stock_item_name_for_lookup}-{unit}"

                    final_stock_item = None
                    if stock_key in stock_map:
                        final_stock_item = stock_map[stock_key]
                        print(f"DEBUG_ITEM_MATCH: Found exact match in stock_map for key: '{stock_key}'. Item: {final_stock_item}")
                    else:
                        print(f"DEBUG_ITEM_MATCH: No exact match in stock_map for key: '{stock_key}'. Attempting fuzzy unit match.")
                        for existing_stock_key, existing_stock_item in stock_map.items():
                            if fuzz.token_sort_ratio(stock_item_name_for_lookup.lower(), existing_stock_item['item_name'].lower()) >= 80:
                                final_stock_item = existing_stock_item
                                stock_key = existing_stock_key
                                unit = existing_stock_item['unit']
                                print(f"DEBUG_ITEM_MATCH: Found fuzzy item name match with stock item '{existing_stock_item['item_name']}' (unit: '{existing_stock_item['unit']}'). Using this item.")
                                break

                    print(f"DEBUG_FINAL_ITEM_CHECK: final_stock_item before not found check: {final_stock_item}")

                    if not final_stock_item:
                        debug_info = f"Original extracted: {item_name}"
                        if detected_language != target_stock_language:
                            debug_info += f", Translated (if applicable): {original_lookup_name_before_fuzzy if 'original_lookup_name_before_fuzzy' in locals() else item_name}"
                        if best_match_item_name:
                            debug_info += f", Fuzzy matched (if applicable): {best_match_item_name}"
                        debug_info += f", Unit: {unit}"
                        unprocessed_items_messages.append(f"'{item_name}' is not in stock. ({debug_info}). Sale not recorded.")
                        continue

                    if final_stock_item and 'unit' in final_stock_item:
                        unit = final_stock_item['unit']
                        print(f"DEBUG_UNIT: Final effective unit for transaction '{item_name}': '{unit}'. (Original extracted unit: '{item.get('unit', 'pcs')}')")


                    delta_for_update = -float(quantity)

                    await update_stock_item(sender_id, stock_item_name_for_lookup, delta_for_update, unit, None)

                    sale_data = {
                        "date": extracted_data.get("date", current_date.strftime('%Y-%m-%d')),
                        "type": "sale",
                        "amount": selling_amount,
                        "item": f"{stock_item_name_for_lookup} ({quantity} {item.get('unit', 'pcs')})"
                    }
                    await save_transaction(sale_data, sender_id)

                    total_sales_amount += selling_amount

                    cost_price_per_unit = None
                    if final_stock_item.get("cost_price_per_unit") is not None:
                        cost_price_per_unit = float(final_stock_item["cost_price_per_unit"])

                    profit_for_item = 0.0
                    if cost_price_per_unit is not None:
                        profit_for_item = selling_amount - (float(quantity) * cost_price_per_unit)
                        total_profit += profit_for_item

                    if should_show_profit and cost_price_per_unit is not None:
                        sales_summary_messages.append(f"{final_stock_item['item_name']}: ₹{selling_amount:.2f} (Profit: ₹{profit_for_item:.2f})")
                    else:
                        sales_summary_messages.append(f"{final_stock_item['item_name']}: ₹{selling_amount:.2f}")

            print(f"DEBUG_REPLY: sales_summary_messages: {sales_summary_messages}")
            print(f"DEBUG_REPLY: unprocessed_items_messages: {unprocessed_items_messages}")

            final_reply_parts = []
            item_details_content = "" # Initialize here
            if sales_summary_messages:
                success_item_summary = "\n".join(sales_summary_messages)
                # Construct the full item details content including profit if applicable
                if should_show_profit and total_profit > 0:
                    item_details_content = f"Total Profit: ₹{total_profit:.2f}\n{success_item_summary}"
                else:
                    item_details_content = success_item_summary

                # Check if the message format string expects 'item_details' or 'item'
                message_template = MESSAGES[detected_language]["sale_success"]
                format_args = {"amount": total_sales_amount}

                if "{item_details}" in message_template:
                    format_args["item_details"] = item_details_content
                elif "{item}" in message_template:
                    format_args["item"] = item_details_content # For Hindi etc.

                success_message = message_template.format(**format_args)
                final_reply_parts.append(success_message)

            if unprocessed_items_messages:
                error_message = "❌ Some items were not processed:\n" + "\n".join(unprocessed_items_messages)
                final_reply_parts.append(error_message)

            print(f"DEBUG_REPLY: final_reply_parts before join: {final_reply_parts}")
            if final_reply_parts:
                reply_message = "\n\n".join(final_reply_parts)
                await send_whatsapp_message(sender_id, reply_message)
            else:
                await send_whatsapp_message(sender_id, MESSAGES[detected_language]["extract_fail"])
        else:
            await send_whatsapp_message(sender_id, MESSAGES[detected_language]["extract_fail"])

    elif transaction_type == "purchase":
        purchase_summary_messages = []
        total_purchase_expense = 0.0

        items_purchased = extracted_data.get("items_purchased", [])
        if items_purchased:
            for item in items_purchased:
                item_name = item.get("item_name")
                quantity = item.get("quantity")
                unit = item.get("unit", "pcs")
                cost_price_per_unit = item.get("cost_price_per_unit")

                if item_name and isinstance(quantity, (int, float)) and cost_price_per_unit is not None:
                    await update_stock_item(sender_id, item_name, float(quantity), unit, cost_price_per_unit)
                    purchase_summary_messages.append(f"{item_name}: {quantity} {unit} @ ₹{cost_price_per_unit:.2f}/{unit}")

                    total_purchase_expense += float(quantity) * float(cost_price_per_unit)

            if purchase_summary_messages:
                if total_purchase_expense > 0:
                    expense_data = {
                        "date": extracted_data.get("date", current_date.strftime('%Y-%m-%d')),
                        "type": "expense",
                        "amount": total_purchase_expense,
                        "item": f"Stock purchase ({len(purchase_summary_messages)} items)"
                    }
                    await save_transaction(expense_data, sender_id)
                    purchase_summary_messages.append(f"Total expense of ₹{total_purchase_expense:.2f} recorded.")

                reply_message = MESSAGES[detected_language]["stock_update_success"].format(updates="\n".join(purchase_summary_messages))
                await send_whatsapp_message(sender_id, reply_message)
            else:
                await send_whatsapp_message(sender_id, MESSAGES[detected_language]["extract_fail"])
        else:
            await send_whatsapp_message(sender_id, MESSAGES[detected_language]["extract_fail"])

    elif transaction_type == "expense":
        amount = extracted_data.get("amount")
        description = extracted_data.get("description", "")
        if isinstance(amount, (int, float)):
            expense_data = {
                "date": extracted_data.get("date", current_date.strftime('%Y-%m-%d')), "type": "expense",
                "amount": amount, "item": description
            }
            await save_transaction(expense_data, sender_id)

            if description:
                reply_message = MESSAGES[detected_language]["expense_success"].format(amount=amount, item=description)
            else:
                reply_message = MESSAGES[detected_language]["expense_success_no_item"].format(amount=amount)
            await send_whatsapp_message(sender_id, reply_message)
        else:
            await send_whatsapp_message(sender_id, MESSAGES[detected_language]["extract_fail"])

    elif transaction_type == "order_confirmation":
        # CORRECTED: This block now handles a list of items for a single supplier.
        items_to_order = extracted_data.get("items_to_order", [])
        supplier_name = extracted_data.get("supplier_name")

        if items_to_order and supplier_name:
            print(f"DEBUG_ORDER_CONFIRMATION: Received order confirmation for {len(items_to_order)} items from {supplier_name}.")
            
            supplier_phone_number = None
            for sup_name, sup_info in SUPPLIERS.items():
                if fuzz.ratio(supplier_name.lower(), sup_name.lower()) >= 80:
                    supplier_phone_number = sup_info["phone"]
                    break

            if supplier_phone_number:
                # Format the list of items into a single string for the call agent
                order_details_list = [f"{item.get('quantity', 0)} {item.get('unit', 'pcs')} {item.get('item_name', '')}" for item in items_to_order]
                order_details_str = ", ".join(order_details_list)
                
                from call_handler import initiate_outbound_call
                call_request_id = await initiate_outbound_call(
                    to_number=supplier_phone_number,
                    order_details=order_details_str, # Pass the full order string
                    supplier_name=supplier_name,
                    user_id=sender_id
                )

                if call_request_id:
                    # Store the mapping of request_id to user_id
                    active_calls[str(call_request_id)] = sender_id
                    print(f"DEBUG_APP: Stored active call mapping: {call_request_id} -> {sender_id}")

                    reply_message = f"Calling {supplier_name} to place the following order:\n- {', '.join(order_details_list)}"
                    await send_whatsapp_message(sender_id, reply_message)
                else:
                    reply_message = MESSAGES[detected_language]["order_failed_shopkeeper"].format(
                        item_name=f"{len(items_to_order)} items",
                        supplier_name=supplier_name,
                        reason="Failed to initiate call."
                    )
                    await send_whatsapp_message(sender_id, reply_message)
            else:
                await send_whatsapp_message(sender_id, f"Supplier '{supplier_name}' not found.")
        else:
            await send_whatsapp_message(sender_id, MESSAGES[detected_language]["extract_fail"])
    else:
        await send_whatsapp_message(sender_id, MESSAGES[detected_language]["extract_fail"])

# Dictionary to store call states (e.g., conversation history, order details)
# In a production environment, this would be stored in a database.
call_states = {}
# Dictionary to map call_request_id to user_id for async callbacks
active_calls = {}



async def transcribe_speech_from_url(audio_url: str) -> str:
    """Transcribes speech from an audio URL using Gemini."""
    try:
        temp_audio_path = f"./temp_call_audio_{os.urandom(4).hex()}.wav"
        print(f"DEBUG_WHISPER: Downloading audio from {audio_url} to {temp_audio_path}")
        response = requests.get(audio_url, stream=True)
        response.raise_for_status()
        with open(temp_audio_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"DEBUG_WHISPER: Downloaded audio to {temp_audio_path}")

        from data_extractor import transcribe_audio
        transcription = await asyncio.to_thread(transcribe_audio, temp_audio_path)
        os.remove(temp_audio_path)
        text = transcription.get("original_transcription") or transcription.get("english_translation") or ""
        print(f"DEBUG_WHISPER: Transcription result: {text}")
        return text
    except Exception as e:
        print(f"ERROR_WHISPER: Failed to transcribe speech from {audio_url}: {e}")
        return ""

async def get_openai_response(conversation_history: list, temperature: float = 0.5, max_tokens: int = 150) -> str:
    """Gets a response from Gemini."""
    try:
        prompt_parts = []
        system = None
        for message in conversation_history:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system":
                system = content
            else:
                prompt_parts.append(f"{role}: {content}")
        return await asyncio.to_thread(
            generate_text,
            "\n".join(prompt_parts),
            system,
            temperature,
        )
    except Exception as e:
        print(f"ERROR_GEMINI_RESPONSE: Failed to get Gemini response: {e}")
        return "I'm sorry, I'm having trouble understanding right now. Please try again."

@app.route("/audio/<filename>")
def serve_audio(filename):
    print(f"DEBUG: Serving audio file: {filename}")
    try:
        return send_from_directory('audio', filename)
    except Exception as e:
        print(f"ERROR: Failed to serve audio file {filename}: {str(e)}")
        return ("Audio file not found", 404)

@app.route("/omnidim_post_call_webhook", methods=['POST', 'GET'])
async def omnidim_post_call_webhook():
    if request.method == 'GET':
        return "OmniDimension Post-Call Webhook is active.", 200

    try:
        payload = request.get_json()
        print("DEBUG_OMNIDIM_WEBHOOK: Received post-call webhook from OmniDimension.")
        print(f"DEBUG_OMNIDIM_WEBHOOK: Payload: {json.dumps(payload, indent=2)}")

        # Extract user_id from context/metadata
        # We check multiple possible locations for robustness
        user_id = payload.get("callContext", {}).get("user_id") or \
                  payload.get("context", {}).get("user_id") or \
                  payload.get("metadata", {}).get("user_id")

        if not user_id:
            # Try to look up user_id from active_calls using call_request_id or call_id
            call_request_id = payload.get("call_request_id")
            call_id = payload.get("call_id")
            
            if call_request_id and str(call_request_id) in active_calls:
                user_id = active_calls[str(call_request_id)]
                print(f"DEBUG_OMNIDIM_WEBHOOK: Found user_id {user_id} using call_request_id {call_request_id}")
                # Clean up
                del active_calls[str(call_request_id)]
            elif call_id and str(call_id) in active_calls:
                user_id = active_calls[str(call_id)]
                print(f"DEBUG_OMNIDIM_WEBHOOK: Found user_id {user_id} using call_id {call_id}")
                 # Clean up
                del active_calls[str(call_id)]
            
        if not user_id:
            print("ERROR_OMNIDIM_WEBHOOK: Could not find user_id in payload or active_calls. Cannot notify shopkeeper.")
            # Attempt to fallback to a default user if testing, or just log error
            # For now, we return 200 to acknowledge receipt but log the error
            return {"status": "success", "message": "Received but user_id missing"}, 200

        # Extract information from the payload
        # Check for direct keys or nested in call_report
        call_report = payload.get("call_report", {})
        
        call_summary = payload.get("callSummary") or payload.get("summary") or call_report.get("summary") or "No summary available."
        
        extracted_info = payload.get("extractedInformation") or payload.get("extracted_variables") or call_report.get("extracted_variables") or {}
        
        # Normalize keys to lower case for easier matching
        info_lower = {k.lower(): v for k, v in extracted_info.items()} if extracted_info else {}

        # Extract specific fields
        order_status = info_lower.get("order_status") or info_lower.get("status") or "Unknown"
        delivery_time = info_lower.get("delivery_time") or info_lower.get("delivery") or "Not specified"
        price = info_lower.get("price") or info_lower.get("total_price") or info_lower.get("cost") or "Not specified"
        
        # --- Enhanced Confirmation Logic ---
        is_confirmed = False
        if "confirm" in str(order_status).lower() or "yes" in str(order_status).lower() or "success" in str(order_status).lower():
            is_confirmed = True
        elif order_status == "Unknown":
            # Fallback to checking summary for positive confirmation
            summary_lower = str(call_summary).lower()
            if any(keyword in summary_lower for keyword in ["confirmed", "order placed", "successfully", "agreed", "responds positively", "positive", "accepts"]):
                is_confirmed = True
                order_status = "Confirmed (based on summary)"

        # --- Enhanced Price Extraction ---
        if price == "Not specified":
            # Try to find price in summary or full conversation
            full_conversation = payload.get("fullConversation") or call_report.get("full_conversation") or ""
            text_to_search = (str(call_summary) + " " + str(full_conversation)).lower()
            
            # Simple regex to find price mentions (e.g., "400 rupees", "rs 400", "400/-")
            import re
            price_matches = re.findall(r'(\d+(?:,\d+)?(?:\.\d+)?)\s*(?:rupees|rs|inr|ka padega|ki keemat)', text_to_search)
            if price_matches:
                # Take the last mentioned price as it's likely the total or final item price
                # This is a heuristic
                price = f"Approx. ₹{price_matches[-1]}"
            
            # Also check for "delivery" in summary if not extracted
            if delivery_time == "Not specified":
                if "tomorrow" in text_to_search or "kal" in text_to_search:
                    delivery_time = "Tomorrow"
                elif "today" in text_to_search or "aaj" in text_to_search:
                    delivery_time = "Today"

        print(f"DEBUG_OMNIDIM_WEBHOOK: Extracted - Status: {order_status} (Confirmed: {is_confirmed}), Delivery: {delivery_time}, Price: {price}")

        # Construct the notification message
        if is_confirmed:
            message = (
                f"✅ **Order Update**\n\n"
                f"Your order has been **CONFIRMED**.\n\n"
                f"• **Delivery Time:** {delivery_time}\n"
                f"• **Price:** {price}\n\n"
                f"**Call Summary:**\n{call_summary}"
            )
        else:
            message = (
                f"❌ **Order Update**\n\n"
                f"Your order could **NOT** be confirmed.\n\n"
                f"**Status:** {order_status}\n"
                f"**Reason/Details:** {call_summary}"
            )

        # Send the WhatsApp message
        await send_whatsapp_message(user_id, message)
        print(f"DEBUG_OMNIDIM_WEBHOOK: Notification sent to {user_id}")

        return {"status": "success", "message": "Post-call data processed and notification sent"}, 200
    except Exception as e:
        print(f"ERROR_OMNIDIM_WEBHOOK: Error processing OmniDimension post-call webhook: {str(e)}")
        return {"status": "error", "message": str(e)}, 500
        return {"status": "error", "message": str(e)}, 500

# Function to run the scheduler in its own event loop
def _run_scheduler():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.call_soon_threadsafe(scheduler.start)
    loop.run_forever()

# Shut down the scheduler when the Flask app stops
@app.teardown_appcontext
def shutdown_scheduler(exception=None):
    if scheduler.running:
        scheduler.shutdown()
        print("Scheduler for low stock alerts has been shut down.")

async def generate_local_insights():
    """
    Generates detailed, actionable insights for shopkeepers by combining 14-day weather forecasts,
    upcoming festivals, and current inventory levels into a single, efficient LLM call.
    """
    
    print("DEBUG_INSIGHTS: Generating local insights...")
    unique_user_ids = await get_all_unique_user_ids_with_stock()

    # Removed weather and festival insights fetching

    # --- Step 2: Process All Insights For Each User ---
    for user_id in unique_user_ids:
        print(f"DEBUG_INSIGHTS: Generating insights for user: {user_id}")
        
        stock_levels = await get_stock_levels(user_id)
        stock_list_str = ", ".join([item['item_name'].lower() for item in stock_levels]) if stock_levels else "कोई आइटम स्टॉक में नहीं है।"

        # --- Step 3: Create a Hindi-focused, Concise, and Structured Prompt ---
        # Removed weather_summary and festival_summary generation
        weather_summary = ""
        festival_summary = ""

        master_prompt = f"""
        You are a Retail Expert for Indian kirana stores. Your goal is to provide actionable advice in HINDI.

        **Data Provided:**
        3.  **Current Inventory:** {stock_list_str}

        **Your Tasks (in Hindi):**
        1.  **Low Stock Alerts:** Identify all items with 0.0 kg remaining and list them.
        
        **Output Format:**
        Respond ONLY with a valid JSON object. The root object MUST have one key: "low_stock_alerts".
        All string values MUST BE IN HINDI.

        Example:
        {{
          "low_stock_alerts": [
            {{
              "item": "आटा",
              "remaining_quantity": "0.0 kg"
            }},
            {{
              "item": "बासमती चावल",
              "remaining_quantity": "0.0 kg"
            }}
          ]
        }}
        """

        try:
            # --- Step 4: Make One Efficient LLM Call for Insights ---
            insights_json = await asyncio.to_thread(
                generate_json,
                master_prompt,
                "You are an expert for Indian grocery stores. You MUST reply with a valid JSON object where all string values are in Hindi, except for 'action' and 'potential'.",
                0.5,
            )
            low_stock_alerts = insights_json.get("low_stock_alerts", [])
            
            # --- Step 5: Format the Insightful Response for WhatsApp ---
            final_message_parts = []
            if low_stock_alerts:
                final_message_parts.append("⚠️ **कम स्टॉक की चेतावनी!**")
                for alert in low_stock_alerts:
                    item_name = alert.get("item", "N/A")
                    remaining_quantity = alert.get("remaining_quantity", "N/A")
                    final_message_parts.append(f"• **{item_name}**: केवल {remaining_quantity} बचा है।")
                
                final_message_parts.append("\n*आप क्या करना चाहेंगे? कृपया एक विकल्प चुनें:*")
                final_message_parts.append("1. सप्लायर का फोन नंबर दें और ऑर्डर करें")
                final_message_parts.append("2. आस-पास के सप्लायरों की सूची दें")
                final_message_parts.append("3. व्यापार के नए अवसर खोजें (Business Opportunities)")

                # Store low_stock_items in call_states for later use
                call_states[user_id] = {"state": "awaiting_low_stock_option", "low_stock_items": low_stock_alerts}

            # --- Step 6: Send the Final, Combined Message ---
            if final_message_parts:
                final_message_body = "\n".join(final_message_parts)
                await send_whatsapp_message(user_id, final_message_body)
            else:
                print(f"DEBUG_INSIGHTS: No actionable insights generated for {user_id}.")

        except Exception as e:
            print(f"ERROR_INSIGHTS: Failed to generate insights for user {user_id}: {e}")

# --- PATCH START: Only Low Stock Alerts (no weather/festival insights), fire every 2min ---
from flask import jsonify

from apscheduler.schedulers.background import BackgroundScheduler

def format_low_stock_alert_message(low_stock_alerts):
    msg_lines = ["⚠️ **कम स्टॉक की चेतावनी!**"]
    for alert in low_stock_alerts:
        item_name = alert.get("item", "N/A")
        remaining_quantity = alert.get("remaining_quantity", "N/A")
        msg_lines.append(f"• **{item_name}**: केवल {remaining_quantity} बचा है।")
    msg_lines.append("\n*आप क्या करना चाहेंगे? कृपया एक विकल्प चुनें:*")
    msg_lines.append("1. सप्लायर का फोन नंबर दें और ऑर्डर करें")
    msg_lines.append("2. आस-पास के सप्लायरों की सूची दें")
    return "\n".join(msg_lines)

async def low_stock_alerts_periodic():
    global call_states
    print("DEBUG: Running periodic low stock alerts job...")
    unique_user_ids = await get_all_unique_user_ids_with_stock()
    for user_id in unique_user_ids:
        current_user_state = call_states.get(user_id, {}).get("state")
        active_states = ["waiting_for_supplier_number", "listing_suppliers"]
        
        low_stock_items = await get_low_stock_items(user_id)
        low_stock_alerts = []
        for item in low_stock_items:
            low_stock_alerts.append({
                "item": item.get("item_name", "N/A"),
                "remaining_quantity": f"{item.get('quantity', 0.0)} {item.get('unit', 'pcs')}"
            })
        
        if low_stock_alerts:
            msg = format_low_stock_alert_message(low_stock_alerts)
            
            # If user is actively in a conversation (providing phone number or selecting supplier),
            # send the alert but preserve their current state and low_stock_items
            if current_user_state in active_states:
                # Preserve existing state and items, just send the alert
                existing_items = call_states.get(user_id, {}).get("low_stock_items", [])
                call_states[user_id] = {
                    "state": current_user_state,
                    "low_stock_items": existing_items  # Keep existing items, don't overwrite
                }
                await send_whatsapp_message(user_id, msg)
                print(f"DEBUG: Sent low stock alert to {user_id} (preserved state: {current_user_state})")
            else:
                # User is not in active conversation, update state normally
                call_states[user_id] = {"state": "awaiting_low_stock_option", "low_stock_items": low_stock_alerts}
                await send_whatsapp_message(user_id, msg)
                print(f"DEBUG: Sent low stock alert to {user_id} (new state: awaiting_low_stock_option)")

# Schedule this alert every 45 seconds
if __name__ == "__main__":
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        if DEMO_MODE:
            print("DEMO_MODE on — low stock alerts disabled. WhatsApp replies only to 2 and 3.")
        else:
            # Only schedule low stock alerts now
            if not scheduler.running:
                scheduler.add_job(low_stock_alerts_periodic, 'interval', seconds=45, id='low_stock_alerts_job', replace_existing=True)
            scheduler_thread = Thread(target=_run_scheduler)
            scheduler_thread.daemon = True
            scheduler_thread.start()
            print("Scheduler for ONLY low stock alerts started (every 45 sec).")
    app.run(debug=True, use_reloader=False, host="0.0.0.0", port=5000)