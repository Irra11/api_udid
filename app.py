import os
import uuid
import base64
import traceback
from datetime import datetime
from io import BytesIO

from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import qrcode

from bakong_khqr import KHQR

# ======================
# CONFIG
# ======================
app = Flask(__name__)
CORS(app)

# 🔴 CHANGE THESE
BAKONG_ID = "yourname@aclb"   # Example: irra@aclb or irra@aba
PRICE_USD = 15
USD_TO_KHR = 4000  # Conversion rate (15$ ≈ 60000 KHR)
PRICE_KHR = PRICE_USD * USD_TO_KHR

# Telegram (optional)
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

# MongoDB (optional but recommended)
MONGO_URI = "mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority"

# ======================
# DATABASE CONNECTION
# ======================
orders_col = None
try:
    client = MongoClient(MONGO_URI)
    db = client["khqr_db"]
    orders_col = db["orders"]
    print("✅ MongoDB Connected")
except Exception as e:
    print("⚠️ MongoDB not connected:", e)

# ======================
# UTIL FUNCTIONS
# ======================
def get_khmer_time():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def send_telegram_alert(message):
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print("Telegram Error:", e)

def generate_qr_base64(qr_string):
    qr = qrcode.make(qr_string)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()

# ======================
# HOME
# ======================
@app.route("/")
def home():
    return jsonify({
        "status": "API RUNNING",
        "price_usd": PRICE_USD,
        "price_khr": PRICE_KHR
    })

# ======================
# CREATE PAYMENT (KHQR $15)
# ======================
@app.route("/api/create-payment", methods=["POST"])
def create_payment():
    try:
        data = request.json
        email = data.get("email", "no-email")
        product = data.get("product", "Service")

        order_id = str(uuid.uuid4())[:8].upper()

        # 🔥 Generate Dynamic KHQR
        khqr = KHQR(
            bakong_id=BAKONG_ID,
            merchant_name="Irra Store",
            city="Phnom Penh"
        )

        khqr_data = khqr.generate(amount=PRICE_KHR)
        qr_string = khqr_data["qr_string"]
        md5 = khqr_data["md5"]

        # Generate QR Image locally (PythonAnywhere safe)
        qr_image_base64 = generate_qr_base64(qr_string)

        # Save order to DB
        if orders_col is not None:
            orders_col.insert_one({
                "order_id": order_id,
                "email": email,
                "product": product,
                "amount_usd": PRICE_USD,
                "amount_khr": PRICE_KHR,
                "md5": md5,
                "status": "unpaid",
                "created_at": get_khmer_time()
            })

        return jsonify({
            "success": True,
            "order_id": order_id,
            "amount_usd": PRICE_USD,
            "amount_khr": PRICE_KHR,
            "md5": md5,
            "qr_image": f"data:image/png;base64,{qr_image_base64}"
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ======================
# CHECK PAYMENT (AUTO)
# ======================
@app.route("/api/check-payment/<md5>", methods=["GET"])
def check_payment(md5):
    try:
        khqr = KHQR(bakong_id=BAKONG_ID)

        # Check payment from Bakong
        paid_list = khqr.check_bulk_payments([md5])

        if md5 in paid_list:
            if orders_col is not None:
                order = orders_col.find_one({"md5": md5})

                if order and order["status"] != "paid":
                    orders_col.update_one(
                        {"md5": md5},
                        {"$set": {"status": "paid"}}
                    )

                    # Telegram Notification
                    msg = (
                        f"💰 <b>PAYMENT RECEIVED</b>\n"
                        f"🆔 Order: <code>{order['order_id']}</code>\n"
                        f"📧 Email: {order['email']}\n"
                        f"💵 Amount: ${PRICE_USD}\n"
                        f"🇰🇭 {PRICE_KHR} KHR"
                    )
                    send_telegram_alert(msg)

            return jsonify({"status": "PAID"})

        return jsonify({"status": "UNPAID"})

    except Exception as e:
        print("Check Payment Error:", e)
        return jsonify({
            "status": "ERROR",
            "message": str(e)
        }), 500

# ======================
# GET ORDER (OPTIONAL)
# ======================
@app.route("/api/order/<order_id>", methods=["GET"])
def get_order(order_id):
    if orders_col is None:
        return jsonify({"error": "DB not connected"}), 500

    order = orders_col.find_one({"order_id": order_id})
    if not order:
        return jsonify({"error": "Order not found"}), 404

    order["_id"] = str(order["_id"])
    return jsonify(order)

# ======================
# RUN (FOR LOCAL ONLY)
# ======================
if __name__ == "__main__":
    app.run(debug=True)
