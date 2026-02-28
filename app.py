import os
import uuid
import requests
import resend
import io
import base64
import time
import qrcode
import traceback
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
from bakong_khqr import KHQR

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# 1. CONFIGURATION
# ==========================================

# 🔴 IMPORTANT: MOVE THESE TO ENV VARIABLES IN PRODUCTION
TELE_TOKEN = os.getenv("TELE_TOKEN", "8379666289:AAEiYiFzSf4rkkP6g_u_13vbrv0ILi9eh4o")
TELE_CHAT_ID = os.getenv("TELE_CHAT_ID", "5007619095")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "re_igigpwEr_2KkTAu1pqUJ1WpRrXXdtga7C")
resend.api_key = RESEND_API_KEY

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Irra@4455$")
SHOP_LOGO_URL = "https://i.pinimg.com/736x/93/1a/b7/931ab7b0393dab7b07fedb2b22b70a89.jpg"

# 💰 PRICE CONFIG ($15)
PRICE_USD = 15
USD_TO_KHR = 4000  # Cambodia average rate
PRICE_KHR = PRICE_USD * USD_TO_KHR  # = 60000 KHR

# Database
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Esign:Kboy%40%404455@cluster0.4havjl6.mongodb.net/?appName=Cluster0")
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client['irra_esign_db']
    orders_col = db['orders']
    print("✅ MongoDB Connected")
except Exception as e:
    print("❌ MongoDB Failed:", e)
    orders_col = None

# 🏦 BAKONG CONFIG (CORRECT WAY)
BAKONG_TOKEN = os.getenv("BAKONG_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiNGZiMDQwYzA3MWZhNGEwNiJ9LCJpYXQiOjE3NzA0ODM2NTYsImV4cCI6MTc3ODI1OTY1Nn0.5smV48QjYaLTDwzbjbNKBxAK5s615LvZG91nWbA7ZwYeyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiNGZiMDQwYzA3MWZhNGEwNiJ9LCJpYXQiOjE3NzA0ODM2NTYsImV4cCI6MTc3ODI1OTY1Nn0.5smV48QjYaLTDwzbjbNKBxAK5s615LvZG91nWbA7ZwYeyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiNGZiMDQwYzA3MWZhNGEwNiJ9LCJpYXQiOjE3NzA0ODM2NTYsImV4cCI6MTc3ODI1OTY1Nn0.5smV48QjYaLTDwzbjbNKBxAK5s615LvZG91nWbA7ZwYeyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhIjp7ImlkIjoiNGZiMDQwYzA3MWZhNGEwNiJ9LCJpYXQiOjE3NzA0ODM2NTYsImV4cCI6MTc3ODI1OTY1Nn0.5smV48QjYaLTDwzbjbNKBxAK5s615LvZG91nWbA7ZwY")
MY_BANK_ACCOUNT = "king_irra@bkrt"  # 🔴 YOUR REAL KHQR ID

# Initialize KHQR Client (Production Safe)
khqr = KHQR(BAKONG_TOKEN)

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def get_khmer_time():
    khmer_tz = timezone(timedelta(hours=7))
    return datetime.now(khmer_tz).strftime("%d-%b-%Y %I:%M %p")

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELE_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELE_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram Error:", e)

def generate_qr_base64(qr_string):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_string)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

# ==========================================
# 3. SERVE HTML
# ==========================================
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/status')
def status():
    return jsonify({
        "status": "Backend Live",
        "price_usd": PRICE_USD,
        "price_khr": PRICE_KHR,
        "time": get_khmer_time()
    })

# ==========================================
# 4. CREATE PAYMENT (DYNAMIC KHQR $15)
# ==========================================
@app.route('/api/create-payment', methods=['POST'])
def create_payment():
    try:
        data = request.json or {}
        udid = data.get('udid', 'N/A')
        email = data.get('email', 'no-email')

        order_id = str(uuid.uuid4())[:8].upper()
        bill_no = f"TRX-{int(time.time())}"

        # 🔥 Generate Dynamic KHQR ($15 ≈ 60000 KHR)
        qr_string = khqr.create_qr(
            bank_account=MY_BANK_ACCOUNT,
            merchant_name='Irra Store',
            merchant_city='Phnom Penh',
            amount=PRICE_KHR,
            currency='KHR',
            store_label='IrraStore',
            bill_number=bill_no,
            terminal_label='WEB-POS',
            static=False
        )

        # 🔐 Generate MD5 (VERY IMPORTANT FOR AUTO CHECK)
        md5_hash = khqr.generate_md5(qr_string)

        # 🔗 Deeplink (Optional)
        deeplink = khqr.generate_deeplink(
            qr_string,
            "https://irraesign.store",
            "Irra Store",
            SHOP_LOGO_URL
        )

        # 🖼 Generate QR Image (PythonAnywhere Safe)
        img_base64 = generate_qr_base64(qr_string)

        # 💾 Save to MongoDB
        if orders_col is not None:
            orders_col.insert_one({
                "order_id": order_id,
                "email": email,
                "udid": udid,
                "price_usd": PRICE_USD,
                "price_khr": PRICE_KHR,
                "status": "pending_payment",
                "md5": md5_hash,
                "bill_no": bill_no,
                "timestamp": get_khmer_time()
            })

        return jsonify({
            "success": True,
            "order_id": order_id,
            "amount_usd": PRICE_USD,
            "amount_khr": PRICE_KHR,
            "md5": md5_hash,
            "qr_image": img_base64,
            "deeplink": deeplink
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# ==========================================
# 5. AUTO PAYMENT CHECK (BAKONG MD5)
# ==========================================
@app.route('/api/check-payment/<md5>', methods=['GET'])
def check_payment(md5):
    try:
        # Check payment from Bakong server
        paid_list = khqr.check_bulk_payments([md5])

        if md5 in paid_list:
            if orders_col is not None:
                order = orders_col.find_one({"md5": md5})

                if order and order.get('status') != 'paid':
                    orders_col.update_one(
                        {"md5": md5},
                        {"$set": {"status": "paid", "paid_at": get_khmer_time()}}
                    )

                    # 📢 Telegram Alert
                    msg = (
                        f"💰 <b>NEW ORDER (AUTO PAID)</b>\n"
                        f"🆔 ID: <code>{order['order_id']}</code>\n"
                        f"📧 {order['email']}\n"
                        f"📱 UDID: <code>{order['udid']}</code>\n"
                        f"💵 Amount: ${PRICE_USD} ({PRICE_KHR} KHR)"
                    )
                    send_telegram_alert(msg)

            return jsonify({"status": "PAID"})

        return jsonify({"status": "UNPAID"})

    except Exception as e:
        print("Bakong Check Error:", e)

        # Token expired fallback
        if "Token" in str(e) or "Invalid" in str(e):
            return jsonify({
                "status": "UNPAID",
                "require_manual": True
            })

        return jsonify({"status": "ERROR", "msg": str(e)}), 500

# ==========================================
# 6. MANUAL CONFIRM (FALLBACK)
# ==========================================
@app.route('/api/confirm-manual', methods=['POST'])
def confirm_manual():
    try:
        data = request.json
        order_id = data.get('order_id')

        if orders_col is not None:
            orders_col.update_one(
                {"order_id": order_id},
                {"$set": {"status": "verification_pending"}}
            )

            order = orders_col.find_one({"order_id": order_id})
            if order:
                msg = (
                    f"⚠️ <b>MANUAL PAYMENT CHECK</b>\n"
                    f"🆔 ID: <code>{order['order_id']}</code>\n"
                    f"📧 {order['email']}\n"
                    f"📱 UDID: <code>{order['udid']}</code>\n"
                    f"User clicked: I Have Paid"
                )
                send_telegram_alert(msg)

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)})

# ==========================================
# 7. RUN (LOCAL)
# ==========================================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
