"""
Diagnostic script to check what call context is being sent to OmniDimension.
Run this after making a test order to see the exact variables.
"""

# Sample order parsing test
def parse_order_items(order_str: str):
    """Parse order string like '5kg atta, 2kg chawal' into structured items."""
    import re
    items = []
    # Split by comma to get individual items
    parts = [p.strip() for p in order_str.split(',')]
    
    for part in parts:
        # Try to extract quantity, unit, and item name
        # Pattern: "5kg atta" or "2 kg chawal" or "10 किलो चावल"
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
            print(f"Could not parse item: '{part}'")
    
    return items

# Test cases
test_orders = [
    "5kg atta, 2kg chawal",
    "10kg basmati rice",
    "3 kg dal, 2 litre oil",
    "5किलो आटा"
]

print("=" * 70)
print("ORDER PARSING DIAGNOSTIC")
print("=" * 70)

for order in test_orders:
    print(f"\n📦 Order: '{order}'")
    print("-" * 70)
    parsed = parse_order_items(order)
    
    if parsed:
        for i, item in enumerate(parsed, 1):
            print(f"  Item {i}:")
            print(f"    item_name: {item['item_name']}")
            print(f"    quantity: {item['quantity']}")
            print(f"    unit: {item['unit']}")
            print(f"    original: {item['original']}")
        
        # Show what would be sent to OmniDimension
        first_item = parsed[0]
        print(f"\n  🔧 Variables sent to OmniDimension:")
        print(f"    item_name = '{first_item['item_name']}'")
        print(f"    quantity = '{first_item['quantity']}'")
        print(f"    unit = '{first_item['unit']}'")
        
        if len(parsed) > 1:
            all_items = ", ".join([f"{item['quantity']} {item['unit']} {item['item_name']}" for item in parsed])
            print(f"    additional_items = '{all_items}'")
    else:
        print("  ❌ Failed to parse order")

print("\n" + "=" * 70)
print("IMPORTANT NOTES:")
print("=" * 70)
print("""
1. The OmniDimension agent expects these EXACT variable names:
   - item_name
   - quantity  
   - unit
   - supplier_name

2. These variables must be configured in OmniDimension agent settings as
   "Custom Variables" or "Context Variables"

3. If the agent is still using hardcoded values (10 kg basmati rice),
   it means:
   a) The variables are not properly configured in OmniDimension
   b) The agent prompt has hardcoded example values that override variables
   c) The variable names don't match what the agent expects

SOLUTION:
Go to OmniDimension dashboard → Your Agent → Settings → Custom Variables
and ensure these variables are defined and linked to the agent prompt.
""")
