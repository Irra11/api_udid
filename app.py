import os
import uuid
import requests
import resend
import io
import base64
import time
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ==========================================
# 1. CONFIGURATION
# ==========================================

# 🔴 PUT YOUR STATIC QR IMAGE LINK HERE
STATIC_QR_URL = "https://i.pinimg.com/736x/b1/6a/e2/b16ae2b0fecbfe77a77c06494e589c5d.jpg"

# 🔴 Telegram Settings
TELE_TOKEN = "8470641780:AAHd2LRndd0dA2lBBkSEzxqh5FtgYqHpNwY"
TELE_CHAT_ID = "5007619095"

# 🔴 Resend Email Settings
RESEND_API_KEY = "re_M8VwiPH6_CYEbbqfg6nG737BEqR9nNWD5"
resend.api_key = RESEND_API_KEY
SHOP_LOGO_URL = "https://i.pinimg.com/736x/da/83/78/da8378a6ddba21823631bd644bee4266.jpg"
# 🔴 Admin Password
ADMIN_PASSWORD = "Irra@4455$" 

# 🔴 Database
MONGO_URI = "mongodb+srv://Esign:Kboy%40%404455@cluster0.4havjl6.mongodb.net/?appName=Cluster0"

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client['irra_esign_db']
    orders_col = db['orders']
    print("✅ MongoDB Connected")
except Exception as e:
    print(f"❌ MongoDB Failed: {e}")
    orders_col = None

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def get_khmer_time():
    khmer_tz = timezone(timedelta(hours=7))
    return datetime.now(khmer_tz).strftime("%d-%b-%Y %I:%M %p")

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELE_TOKEN}/sendMessage"
        payload = {"chat_id": TELE_CHAT_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

@app.route('/')
def status():
    return jsonify({"status": "Backend Live (Static QR Mode)", "time": get_khmer_time()})\
    



    
# ==========================================
# 4. UDID AUTO-EXTRACT ROUTES
# ==========================================

import re  # Add this at the top with other imports

# --- TESTING LOCALLY ---
# Use your local IP so your phone can redirect back to your website
# If your website is also running on your PC, put that address here
FRONTEND_URL = "https://www.irraesign.store/" # Change 5500 to your website's port (like Live Server)

@app.route('/api/get-profile')
def get_profile():
    # This XML tells the iPhone to send UDID to our /api/enroll endpoint
    # We use request.url_root so it automatically uses http://192.168.8.197:5000/
    profile_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <dict>
        <key>URL</key>
        <string>{request.url_root}api/enroll</string>
        <key>DeviceAttributes</key>
        <array>
            <string>UDID</string>
            <string>PRODUCT</string>
            <string>VERSION</string>
        </array>
    </dict>
    <key>PayloadOrganization</key>
    <string>Irra Esign Store</string>
    <key>PayloadDisplayName</key>
    <string>Irra Esign UDID Service</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
    <key>PayloadUUID</key>
    <string>7e366e60-466d-4660-966e-6e6e6e6e6e6e</string>
    <key>PayloadIdentifier</key>
    <string>com.irraesign.udid</string>
    <key>PayloadType</key>
    <string>Profile Service</string>
</dict>
</plist>"""
    return profile_xml, 200, {'Content-Type': 'application/x-apple-aspen-config'}

@app.route('/api/enroll', methods=['POST'])
def enroll():
    try:
        # iPhone sends data as signed PKCS7. We extract the UDID via Regex.
        raw_data = request.get_data().decode('latin-1')
        udid_search = re.search(r'<key>UDID</key>\s*<string>(.*?)</string>', raw_data)
        
        if udid_search:
            udid = udid_search.group(1)
            print(f"🎯 UDID Detected: {udid}")
            # Redirect back to your frontend with the UDID in the URL
            return "", 301, {'Location': f"{FRONTEND_URL}/?udid={udid}"}
        
        return "UDID not found", 400
    except Exception as e:
        print(f"Enroll Error: {e}")
        return str(e), 500

# ==========================================

# 3. PAYMENT ROUTES
# ==========================================

@app.route('/api/create-payment', methods=['POST'])
def create_payment():
    try:
        data = request.json
        udid = data.get('udid')
        email = data.get('email')
        
        order_id = str(uuid.uuid4())[:8].upper()
        
        # 1. Fetch Static QR Image from URL
        try:
            # We download the image on the server and send it as Base64 
            # to avoid CORS issues on the frontend
            qr_response = requests.get(STATIC_QR_URL)
            qr_response.raise_for_status()
            img_base64 = base64.b64encode(qr_response.content).decode('utf-8')
        except Exception as err:
            return jsonify({"success": False, "error": f"Failed to load QR Image: {err}"}), 500

        # 2. Save Order to Database
        if orders_col is not None:
            orders_col.insert_one({
                "order_id": order_id,
                "email": email,
                "udid": udid, 
                "price": "10.00",
                "plan": "Standard",
                "status": "pending_manual_check",
                "timestamp": get_khmer_time()
            })

        return jsonify({
            "success": True,
            "order_id": order_id,
            "qr_image": img_base64 # Sending the static image
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/confirm-manual', methods=['POST'])
def confirm_manual():
    try:
        data = request.json
        oid = data.get('order_id')
        
        if orders_col:
            order = orders_col.find_one({"order_id": oid})
            if order:
                # 1. Update Database Status
                orders_col.update_one({"order_id": oid}, {"$set": {"status": "pending_review"}})

                # 2. SEND TELEGRAM ALERT
                msg = (
                    f"⚠️ <b>MANUAL PAYMENT CLAIMED</b>\n"
                    f"User clicked 'I Have Paid'.\n\n"
                    f"🆔 Order: <code>{oid}</code>\n"
                    f"📧 Email: {order.get('email')}\n"
                    f"💰 Amount: $10.00\n"
                    f"📱 UDID: <code>{order.get('udid')}</code>\n\n"
                    f"🏦 <b>Action:</b> Check Bank App & Approve in Admin!"
                )
                send_telegram_alert(msg)
                
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    if data and data.get('password') == ADMIN_PASSWORD:
        return jsonify({"success": True}), 200
    return jsonify({"success": False}), 401

@app.route('/api/orders', methods=['GET'])
def get_orders():
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
    if orders_col is None: return jsonify([])
    all_orders = list(orders_col.find().sort("_id", -1))
    for o in all_orders: o['_id'] = str(o['_id'])
    return jsonify(all_orders)

@app.route('/api/update-order', methods=['POST'])
def update_order():
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    orders_col.update_one({"order_id": data.get('order_id')}, {"$set": {"email": data.get('email'), "download_link": data.get('link')}})
    return jsonify({"success": True})

@app.route('/api/delete-order/<order_id>', methods=['DELETE'])
def delete_order(order_id):
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401
    orders_col.delete_one({"order_id": order_id})
    return jsonify({"success": True})

@app.route('/api/send-email', methods=['POST'])
def api_send_email():
    # 1. Auth Check
    if request.headers.get('x-admin-password') != ADMIN_PASSWORD:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    oid = data.get('order_id')
    download_link = data.get('link')
    is_failed = data.get('type') == 'failed'

    order = orders_col.find_one({"order_id": oid})
    if not order: return jsonify({"success": False, "msg": "Order not found"}), 404

    # 2. Prepare Data
    price = order.get('price', '10.00')
    plan = order.get('plan', 'Standard Package')
    udid = order.get('udid', 'N/A')
    user_name = order.get('email').split('@')[0]

    if is_failed:
        theme_color = "#e74c3c"
        subject_text = "Order Rejected - Payment Verification Failed"
        status_title = "Order Failed"
        status_desc = "Payment Issue Detected"
        main_message = "We regret to inform you that your order could not be processed."
        button_text = "Contact Support"
        action_url = "https://t.me/irra_11"
    else:
        theme_color = "#27ae60"
        subject_text = "Order Completed - Device Registration Enabled"
        status_title = "Order Completed"
        status_desc = "Device Registration Enabled"
        main_message = "We are pleased to inform you that your order has been successfully completed."
        button_text = "Download Certificate"
        action_url = download_link

    # 3. HTML Template
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <link href="https://fonts.googleapis.com/css2?family=Hanuman:wght@400;700&family=Inter:wght@400;600&display=swap" rel="stylesheet">
    </head>
    <body style="margin: 0; padding: 0; background-color: #f4f7f6; font-family: 'Inter', sans-serif; color: #333;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 30px 0;">
            <tr>
                <td align="center">
                    <table width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.05); border-spacing: 0;">
                        <tr>
                            <td align="center" style="background-color: {theme_color}; padding: 40px 20px;">
                                <div style="display: inline-block; padding: 5px; background: rgba(255,255,255,0.2); border-radius: 50%; margin-bottom: 15px;">
                                    <img src="{SHOP_LOGO_URL}" width="70" height="70" style="display: block; border-radius: 50%; border: 3px solid #ffffff;">
                                </div>
                                <h2 style="margin: 0; color: #ffffff; font-size: 20px;">{status_title}</h2>
                                <p style="margin: 5px 0 0 0; color: #ffffff; opacity: 0.9; font-size: 13px;">{status_desc}</p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px 30px;">
                                <h3 style="margin: 0 0 15px 0; color: #2c3e50;">Dear {user_name},</h3>
                                <p style="font-size: 15px; line-height: 1.6; color: #555;">{main_message}</p>
                                <table width="100%" style="margin-top: 25px; border-collapse: collapse; font-size: 14px;">
                                    <tr><td colspan="2" style="padding: 10px 0; border-bottom: 2px solid #f4f7f6; font-weight: bold; color: {theme_color}; text-transform: uppercase;">Transaction Details</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Payment Amount:</td><td align="right" style="font-weight: 600;">${price}</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Method:</td><td align="right" style="font-weight: 600;">BAKONG KHQR</td></tr>
                                    <tr><td colspan="2" style="padding: 25px 0 10px 0; border-bottom: 2px solid #f4f7f6; font-weight: bold; color: {theme_color}; text-transform: uppercase;">Order Information</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Order ID:</td><td align="right" style="font-weight: 600;">#{oid}</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Package:</td><td align="right" style="font-weight: 600;">{plan}</td></tr>
                                    <tr><td style="padding: 12px 0; color: #777;">Device UDID:</td><td align="right" style="font-size: 11px; font-family: monospace; background: #f8f9fa; padding: 4px 8px; border-radius: 4px;">{udid}</td></tr>
                                </table>
                                <div style="text-align: center; margin-top: 40px;">
                                    <a href="{action_url}" style="background-color: {theme_color}; color: #ffffff; padding: 18px 35px; text-decoration: none; border-radius: 12px; font-weight: bold; font-size: 16px;">{button_text}</a>
                                </div>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    try:
        resend.Emails.send({
            "from": "Irra Store <admin@irra.store>",
            "to": [order['email']],
            "subject": subject_text,
            "html": html_body
        })
        
        new_status = "failed" if is_failed else "completed"
        orders_col.update_one({"order_id": oid}, {"$set": {"download_link": download_link, "status": new_status}})
        send_telegram_alert(f"✅ <b>EMAIL SENT</b> to {order['email']}")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
    import re # Add this at the top of your file with other imports
