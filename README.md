# � Vyapaar Saathi (व्यापार साथी)

> **Your AI-Powered Smart Business Companion for Kirana Stores.**
> *Empowering small shopkeepers with AI, Voice, and Local Intelligence.*

![Vyapaar Saathi Banner](https://img.shields.io/badge/Status-Active-success?style=for-the-badge) ![Python](https://img.shields.io/badge/Python-3.9+-blue?style=for-the-badge&logo=python&logoColor=white) ![WhatsApp](https://img.shields.io/badge/WhatsApp-Bot-25D366?style=for-the-badge&logo=whatsapp&logoColor=white) ![OpenAI](https://img.shields.io/badge/AI-Powered-412991?style=for-the-badge&logo=openai&logoColor=white)

---

## 📖 About The Project

**Vyapaar Saathi** is a revolutionary WhatsApp-based assistant designed specifically for Indian Kirana store owners. It bridges the gap between traditional retail and modern technology by offering a simple, chat-based interface to manage inventory, find suppliers, and discover new business opportunities.

No complex apps, no learning curve—just chat with **Vyapaar Saathi** on WhatsApp in your local language (Hindi/English) to run your business smarter.

---

## 🎥 Watch the Demo

[![Vyapaar Saathi Demo](https://img.youtube.com/vi/5Tt-9R037lk/0.jpg)](https://youtu.be/jtcB_SQLVqs)

> *Click on the above image to watch Vyapaar Saathi in action!*

---

##  Key Features

### 📦 Smart Inventory Management
- **Low Stock Alerts:** Automatically notifies you when items (like Milk, Bread) are running low.
- **Bill Digitization:** Simply take a photo of a supplier bill, and the AI automatically updates your inventory.
- **Voice Commands:** Just say *"Added 10kg Rice"* to update stock instantly.

### 📍 Local Supplier Discovery
- **Automatic Search:** Finds the best wholesale suppliers near your location.
- **Contact Details:** Get phone numbers, addresses, and ratings of nearby distributors instantly.

### 🧠 Business Opportunity Radar (New!)
- **Event Scanning:** Scans the web for local events (Festivals, Cricket Matches, Fairs) near your shop.
- **AI Strategy:** Suggests what to stock up on.
    - *Example:* "A Marathon is happening nearby on Sunday. Stock up on **Energy Drinks** and **Bananas**!"
- **Profit Maximization:** Helps you capitalize on local demand surges.

### �️ Multilingual & Accessible
- **Hinglish Support:** Understands mixed Hindi and English commands.
- **Voice-First:** Designed for users who prefer speaking over typing.

---

## 🛠️ Tech Stack

- **Backend:** Python, Flask
- **Database:** Supabase (PostgreSQL)
- **AI & ML:**
    - **OpenAI GPT-4o:** For natural language understanding and business logic.
    - **OpenAI Whisper:** For voice-to-text transcription.
    - **OpenAI Vision:** For reading bills and invoices.
    - **OpenAI gpt-4o-mini:** For automated call to suppliers for ordering low stock items with the permission of shopkeeper.
- **Communication:** Twilio API for WhatsApp.
- **Location Services:** Google Maps API.
- **Web Scraping:** DuckDuckGo Search (for event scanning).
- **Scheduling:** APScheduler (for automated alerts).

---

## ⚙️ Installation & Setup

Follow these steps to run Vyapaar Saathi locally:

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/vyapaar-saathi.git
cd vyapaar-saathi
```

### 2. Create a Virtual Environment
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory and add the following keys:
```env
OPENAI_API_KEY=your_openai_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_WHATSAPP_NUMBER=your_twilio_number
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
GOOGLE_MAPS_API_KEY=your_google_maps_key
FLASK_APP=app.py
```

### 5. Run the Application
```bash
python app.py
```

### 6. Connect WhatsApp
- Use **ngrok** to expose your local server: `ngrok http 5000`
- Update the webhook URL in your Twilio Console to the ngrok URL (e.g., `https://your-url.ngrok.io/whatsapp`).

---

## � How to Use

1.  **Start Chatting:** Send "Hi" or "Namaste" to the bot on WhatsApp.
2.  **Add Stock:** Send a voice note *"Maine 50 packet Maggie kharida"* or upload a bill photo.
3.  **Check Opportunities:** When you get a low stock alert, select **Option 3** to find "Business Opportunities". The AI will scan your area for events and suggest items to buy/sell.
4.  **Find Suppliers:** Share your location to get a list of nearby wholesalers.

---

## 🔮 Future Roadmap

- [ ] **Credit Ledger (Udhaar Khata):** Manage customer debts via WhatsApp.
- [ ] **Daily P&L Reports:** Automated daily profit and loss summaries.
- [ ] **Hyperlocal Marketing:** Send offers to nearby customers automatically.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

---

<div align="center">

**Made with ❤️ for India's Retail Heroes by team Matrix Infinity**

</div>
