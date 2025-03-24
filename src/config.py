import os

from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_USER = os.getenv("SMTP_USER")
SECRET = "SECRET"
DEACTIVATION_DAYS = 30
# import os, base64
# print(base64.urlsafe_b64encode(os.urandom(32)).decode())
