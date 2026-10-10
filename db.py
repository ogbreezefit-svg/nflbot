import os
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()
log = logging.getLogger("ogbreeze.db")

raw_url = os.getenv("DATABASE_URL", "")

# Use a local SQLite file if no real database is configured
if not raw_url or "localhost" in raw_url:
    DATABASE_URL = "sqlite:///shadow_bot_test.db"
    log.warning("No usable DATABASE_URL found. Using temporary SQLite file (data may be wiped on deploy).")
else:
    DATABASE_URL = raw_url

# Make Railway / Heroku style Postgres URLs work with SQLAlchemy
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


class PickLog(Base):
    __tablename__ = "picks"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    player_name = Column(String, nullable=True)
    event_id = Column(String, nullable=True)
    market_name = Column(String)
    pick_side = Column(String, nullable=True)
    picked_line = Column(Float, nullable=True)
    picked_odds = Column(Float, nullable=True)

    closing_line = Column(Float, nullable=True)
    closing_odds = Column(Float, nullable=True)
    clv_edge = Column(Float, nullable=True)

    kickoff_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String)
    quarantine_reason = Column(String, nullable=True)
    stake = Column(Float, default=50.0)
    is_shadow = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ParlaySlip(Base):
    __tablename__ = "parlays"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True)
    category = Column(String)
    odds = Column(String)
    stake = Column(String)
    payout = Column(String)
    legs_json = Column(Text)
    status = Column(String, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), default=utcnow)


def init_db():
    """Create tables if they don't exist yet."""
    Base.metadata.create_all(bind=engine)
    log.info("Database ready (%s)", engine.dialect.name)