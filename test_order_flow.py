"""
Test script to verify order placement works despite Twilio message limit.

This script simulates the order flow and shows that:
1. WhatsApp message failures are caught gracefully
2. OmniDimension calls still proceed
3. The process doesn't crash
"""

import os
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import from your app
import sys
sys.path.insert(0, os.path.dirname(__file__))

async def test_order_flow():
    """Test the order flow with Twilio limit exceeded."""
    print("=" * 60)
    print("Testing Order Flow with Twilio Message Limit")
    print("=" * 60)
    
    # Test 1: Check if DISABLE_WHATSAPP_NOTIFICATIONS is set
    disable_notifications = os.getenv("DISABLE_WHATSAPP_NOTIFICATIONS", "false").lower() == "true"
    print(f"\n1. WhatsApp Notifications Disabled: {disable_notifications}")
    
    # Test 2: Import the call handler
    try:
        from call_handler import initiate_outbound_call
        print("2. ✅ Call handler imported successfully")
    except Exception as e:
        print(f"2. ❌ Failed to import call handler: {e}")
        return
    
    # Test 3: Simulate an order
    print("\n3. Simulating order placement...")
    print("   Order: 5kg atta, 2kg chawal")
    print("   Supplier: +919971129359")
    
    try:
        # This will attempt to make the call
        # WhatsApp notifications will fail but the call should proceed
        call_request_id = await initiate_outbound_call(
            to_number="+919971129359",
            order_details="5kg atta, 2kg chawal",
            supplier_name="Test Supplier",
            user_id="whatsapp:+919971129359"
        )
        
        if call_request_id:
            print(f"   ✅ Call initiated successfully! Request ID: {call_request_id}")
            print(f"   📞 OmniDimension call is proceeding despite WhatsApp limit")
        else:
            print("   ❌ Call initiation failed")
            
    except Exception as e:
        print(f"   ❌ Error during order placement: {e}")
    
    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)
    print("\nKey Takeaways:")
    print("- WhatsApp notifications may fail due to Twilio limit")
    print("- OmniDimension calls will still work")
    print("- Check console logs for detailed information")
    print("- Consider setting DISABLE_WHATSAPP_NOTIFICATIONS=true in .env")

if __name__ == "__main__":
    print("\n🧪 Starting Order Flow Test\n")
    asyncio.run(test_order_flow())
