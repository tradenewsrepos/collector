import os
import datetime
import time
from sqlalchemy import create_engine

os.environ['TZ'] = 'UTC'

POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT")

TFIDF_SERVER = os.getenv("TFIDF_SERVER")

DELTA_DATE_ARTICLE = int(os.getenv("DELTA_DATE_ARTICLE"))
DELTA_DATE_TEXT=int(os.getenv("DELTA_DATE_TEXT"))

DOWNLOAD_ARTICLE_SLEEP = int(os.getenv("DOWNLOAD_ARTICLE_SLEEP"))*60
DOWNLOAD_TEXT_SLEEP = int(os.getenv("DOWNLOAD_TEXT_SLEEP"))*60

DB_STRING = (
    f"{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
DB_URI = f"postgresql+psycopg2://{DB_STRING}"

engine = create_engine(DB_URI, pool_pre_ping=True, connect_args={
    "options": "-c timezone=utc"})


def get_time():
    struct = time.localtime()
    start_time = time.strftime('%d.%m.%Y %H:%M:%S', struct)
    return start_time


def is_leap_year(year: int):
    if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0:
        return True
    else:
        return False
