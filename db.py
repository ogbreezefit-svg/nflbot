import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Check if we are running locally vs on Railway
raw_url = os.getenv("DATABASE_URL", "")

# Fallback to local SQLite if DATABASE_URL is missing OR if it points to a local postgres server that isn't running
if not raw_url or "localhost" in raw_url:
    DATABASE_URL = "sqlite:///shadow_bot_test.db"
else:
    DATABASE_URL = raw_url

# Standardize Railway / Postgres URL
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

# SQLite requires 'check_same_thread: False' for testing
engine_args = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, **engine_args)
SessionLocal = sessionmaker(bind=engine)

try:
    from sqlalchemy.orm import DeclarativeBase
    class Base(DeclarativeBase):
        pass
except ImportError:
    from sqlalchemy.orm import declarative_base
    Base = declarative_base()

class PickLog(Base):
    __tablename__ = "picks"
    
    id = Column(Integer, primary_key=True)
    player_name = Column(String, nullable=True)
    event_id = Column(String, nullable=True)
    market_name = Column(String)
    pick_side = Column(String)
    picked_line = Column(Float)
    picked_odds = Column(Float, nullable=True)
    
    closing_line = Column(Float, nullable=True)
    closing_odds = Column(Float, nullable=True)
    clv_edge = Column(Float, nullable=True)
    
    kickoff_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String)
    quarantine_reason = Column(String, nullable=True)
    stake = Column(Float, default=50.0)
    is_shadow = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(bind=engine)