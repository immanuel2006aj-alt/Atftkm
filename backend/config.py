import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/atf")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key")
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "your-fernet-key")
    CHECK_INTERVAL: int = 7200  # 2 hours

    class Config:
        env_file = ".env"

settings = Settings()
