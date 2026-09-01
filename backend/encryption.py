from cryptography.fernet import Fernet
from config import settings

fernet = Fernet(settings.ENCRYPTION_KEY.encode())

def encrypt(text: str) -> bytes:
    return fernet.encrypt(text.encode())

def decrypt(data: bytes) -> str:
    return fernet.decrypt(data).decode()
