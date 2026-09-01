from flask import Flask, request, jsonify, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import uuid
from datetime import datetime

from config import settings
from encryption import encrypt, decrypt
from models import Base, User, TelegramAccount, ClaimEvent
from tasks import start_auth, resume_auth, claim_loop

app = Flask(__name__, static_folder='../frontend', static_url_path='')
app.config['SECRET_KEY'] = settings.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = settings.DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
CORS(app, supports_credentials=True)

db = SQLAlchemy(app)
Base.metadata.create_all(app.app_context())

def get_or_create_demo_user():
    user = db.session.query(User).filter_by(email='demo@example.com').first()
    if not user:
        user = User(email='demo@example.com', password_hash='dummy')
        db.session.add(user)
        db.session.commit()
    return user

@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/api/auth/login', methods=['POST'])
def login():
    user = get_or_create_demo_user()
    session['user_id'] = str(user.id)
    return jsonify({'success': True})

@app.route('/api/accounts/connect', methods=['POST'])
def connect_telegram():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    api_id = data.get('api_id')
    api_hash = data.get('api_hash')
    phone = data.get('phone')
    start_param = data.get('start_param', '1287496525')
    if not all([api_id, api_hash, phone]):
        return jsonify({'error': 'Missing fields'}), 400

    user = db.session.get(User, uuid.UUID(session['user_id']))
    enc_api_hash = encrypt(api_hash).decode()
    enc_phone = encrypt(phone).decode()

    account = TelegramAccount(
        user_id=user.id,
        api_id=api_id,
        api_hash_encrypted=enc_api_hash,
        phone_encrypted=enc_phone,
        start_param=start_param,
        status='pending'
    )
    db.session.add(account)
    db.session.commit()

    start_auth.delay(str(account.id))
    return jsonify({'account_id': str(account.id), 'status': 'pending'})

@app.route('/api/accounts/status/<account_id>', methods=['GET'])
def account_status(account_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    account = db.session.get(TelegramAccount, uuid.UUID(account_id))
    if not account or str(account.user_id) != session['user_id']:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({
        'status': account.status,
        'last_claimed_at': account.last_claimed_at.isoformat() if account.last_claimed_at else None
    })

@app.route('/api/accounts/verify', methods=['POST'])
def verify_code():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    account_id = data.get('account_id')
    code = data.get('code')
    if not account_id or not code:
        return jsonify({'error': 'Missing fields'}), 400
    account = db.session.get(TelegramAccount, uuid.UUID(account_id))
    if not account or str(account.user_id) != session['user_id']:
        return jsonify({'error': 'Not found'}), 404
    resume_auth.delay(str(account.id), code)
    return jsonify({'status': 'verification_sent'})

@app.route('/api/claimers/start', methods=['POST'])
def start_claimer():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    account_id = data.get('account_id')
    account = db.session.get(TelegramAccount, uuid.UUID(account_id))
    if not account or str(account.user_id) != session['user_id']:
        return jsonify({'error': 'Not found'}), 404
    if account.status != 'connected':
        return jsonify({'error': 'Account not connected'}), 400
    claim_loop.delay(str(account.id))
    return jsonify({'status': 'started'})

@app.route('/api/claimers/stop', methods=['POST'])
def stop_claimer():
    # In production, implement proper stop mechanism (e.g., set flag)
    return jsonify({'status': 'stopped'})

@app.route('/api/claimers/logs/<account_id>', methods=['GET'])
def get_logs(account_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    account = db.session.get(TelegramAccount, uuid.UUID(account_id))
    if not account or str(account.user_id) != session['user_id']:
        return jsonify({'error': 'Not found'}), 404
    events = db.session.query(ClaimEvent).filter_by(account_id=account.id).order_by(ClaimEvent.created_at.desc()).limit(50).all()
    return jsonify([{
        'time': e.created_at.strftime('%H:%M:%S'),
        'level': e.level,
        'message': e.message
    } for e in reversed(events)])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
