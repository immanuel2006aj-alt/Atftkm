from celery import Celery
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import KeyboardButtonCallback
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import uuid
import asyncio

from config import settings
from encryption import decrypt, encrypt
from models import TelegramAccount, ClaimEvent, Base

engine = create_engine(settings.DATABASE_URL)
Session = sessionmaker(bind=engine)

celery = Celery(__name__, broker=settings.REDIS_URL)
celery.conf.update(result_backend=settings.REDIS_URL)

def log_event(account_id, level, message):
    session = Session()
    evt = ClaimEvent(account_id=uuid.UUID(account_id), level=level, message=message)
    session.add(evt)
    session.commit()
    session.close()

@celery.task(bind=True, max_retries=3)
def start_auth(self, account_id):
    session = Session()
    acc = session.get(TelegramAccount, uuid.UUID(account_id))
    if not acc:
        return
    try:
        api_hash = decrypt(acc.api_hash_encrypted.encode())
        phone = decrypt(acc.phone_encrypted.encode())
        client = TelegramClient(StringSession(), acc.api_id, api_hash)
        client.start(phone=phone)
        session_str = client.session.save()
        acc.session_blob_encrypted = encrypt(session_str).decode()
        acc.status = 'connected'
        session.commit()
        log_event(account_id, 'success', 'Authentication completed')
        claim_loop.apply_async(args=[account_id], countdown=5)
    except Exception as e:
        if 'PhoneCodeRequired' in str(e) or 'PhoneCode' in str(e):
            acc.status = 'awaiting_code'
            session.commit()
            log_event(account_id, 'info', 'Verification code required')
        elif 'PasswordRequired' in str(e):
            acc.status = 'awaiting_2fa'
            session.commit()
            log_event(account_id, 'info', '2FA password required')
        else:
            acc.status = 'error'
            session.commit()
            log_event(account_id, 'error', f'Auth error: {str(e)}')
            self.retry(exc=e, countdown=60)
    finally:
        session.close()

@celery.task(bind=True)
def resume_auth(self, account_id, code):
    session = Session()
    acc = session.get(TelegramAccount, uuid.UUID(account_id))
    if not acc:
        return
    try:
        api_hash = decrypt(acc.api_hash_encrypted.encode())
        phone = decrypt(acc.phone_encrypted.encode())
        client = TelegramClient(StringSession(), acc.api_id, api_hash)
        client.start(phone=phone, code_callback=lambda: code)
        session_str = client.session.save()
        acc.session_blob_encrypted = encrypt(session_str).decode()
        acc.status = 'connected'
        session.commit()
        log_event(account_id, 'success', 'Authentication completed')
        claim_loop.apply_async(args=[account_id], countdown=5)
    except Exception as e:
        if 'PasswordRequired' in str(e):
            acc.status = 'awaiting_2fa'
            session.commit()
            log_event(account_id, 'info', '2FA password required')
        else:
            acc.status = 'error'
            session.commit()
            log_event(account_id, 'error', f'Auth error: {str(e)}')
            self.retry(exc=e, countdown=60)
    finally:
        session.close()

@celery.task(bind=True, max_retries=3)
def claim_loop(self, account_id):
    session = Session()
    acc = session.get(TelegramAccount, uuid.UUID(account_id))
    if not acc or acc.status != 'connected':
        return
    try:
        api_hash = decrypt(acc.api_hash_encrypted.encode())
        phone = decrypt(acc.phone_encrypted.encode())
        session_str = decrypt(acc.session_blob_encrypted.encode())
        client = TelegramClient(StringSession(session_str), acc.api_id, api_hash)
        client.start(phone=phone)
        bot = client.get_entity('ATF_AIRDROP_bot')
        client.send_message(bot, f'/start {acc.start_param}')
        msgs = client.iter_messages(bot, limit=1)
        for msg in msgs:
            if msg.reply_markup:
                for row in msg.reply_markup.rows:
                    for btn in row.buttons:
                        if isinstance(btn, KeyboardButtonCallback) and any(
                            kw in btn.text.lower() for kw in ('claim', 'mine', 'harvest', 'collect')
                        ):
                            client(GetBotCallbackAnswerRequest(
                                peer=bot,
                                msg_id=msg.id,
                                data=btn.data,
                                game=False
                            ))
                            log_event(account_id, 'success', 'Claim executed successfully')
                            break
        acc.last_claimed_at = datetime.utcnow()
        session.commit()
        claim_loop.apply_async(args=[account_id], countdown=settings.CHECK_INTERVAL)
    except Exception as e:
        log_event(account_id, 'error', f'Claim failed: {str(e)}')
        self.retry(exc=e, countdown=60)
    finally:
        session.close()
