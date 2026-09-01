from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, Text, UUID, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

class TelegramAccount(Base):
    __tablename__ = 'telegram_accounts'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    api_id = Column(Integer, nullable=False)
    api_hash_encrypted = Column(Text, nullable=False)
    phone_encrypted = Column(Text, nullable=False)
    session_blob_encrypted = Column(Text, nullable=True)
    start_param = Column(String, default='1287496525')
    status = Column(String, default='pending')  # pending, awaiting_code, awaiting_2fa, connected, error
    created_at = Column(DateTime, default=datetime.utcnow)
    last_claimed_at = Column(DateTime, nullable=True)

class ClaimJob(Base):
    __tablename__ = 'claim_jobs'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey('telegram_accounts.id'))
    next_run_at = Column(DateTime, nullable=True)
    status = Column(String, default='idle')

class ClaimEvent(Base):
    __tablename__ = 'claim_events'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey('telegram_accounts.id'))
    level = Column(String)
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
