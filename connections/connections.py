import os
from psycopg2 import pool
from groq import Groq
from dotenv import load_dotenv
load_dotenv()


groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


try:
    db_conn = pool.ThreadedConnectionPool(
        1, 5,   # min 1, max 5 connections
        host=os.environ.get("DB_HOST"),
        database=os.environ.get("DB_NAME"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        port=os.environ.get("DB_PORT"),
        sslmode="require"
)
except Exception as e:
    print(f"[error] could not connect to Postgres at startup: {e}")
    print("[error] db_conn is None — personal account lookups will fail until this is fixed")
    db_conn = None


VACHANA_API_KEY = os.environ.get("VACHANA_API_KEY")
VACHANA_STT     = os.environ.get("VACHANA_STT")
VACHANA_TTS     = os.environ.get("VACHANA_TTS")