import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://postgres:password@localhost/sysmonitor"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    COLLECTION_INTERVAL = int(os.environ.get("COLLECTION_INTERVAL", 30))
    RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", 30))
    ALERT_COOLDOWN_MINUTES = int(os.environ.get("ALERT_COOLDOWN_MINUTES", 15))

    # SMTP
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "monitor@localhost")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
