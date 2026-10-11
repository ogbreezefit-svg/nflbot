import os
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, inspect, text, Index
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
    pick_key = Column(String, nullable=True)
    market_key = Column(String, nullable=True)
    realized_return = Column(Float, nullable=True)
    realized_profit = Column(Float, nullable=True)
    settled_at = Column(DateTime(timezone=True), nullable=True)
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


Index("uq_picks_pick_key", PickLog.pick_key, unique=True)

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


from sqlalchemy import ForeignKey, UniqueConstraint


# Ticket outcomes are separate from ACTIVE/ARCHIVED display status.
ParlaySlip.publication_mode = Column(String, nullable=True)
ParlaySlip.selection_method = Column(String, nullable=True)
ParlaySlip.ticket_key = Column(String, nullable=True)
ParlaySlip.outcome = Column(String, nullable=True)
ParlaySlip.settled_at = Column(DateTime(timezone=True), nullable=True)
ParlaySlip.paper_stake = Column(Float, nullable=True)
ParlaySlip.paper_return = Column(Float, nullable=True)
ParlaySlip.paper_profit = Column(Float, nullable=True)

# Monster approval metadata. Legacy records remain unapproved.
# publication_mode="MONSTER" identifies dedicated Monster records.
ParlaySlip.research_qualified = Column(Boolean, nullable=True)
ParlaySlip.prediction_approved = Column(Boolean, nullable=True)
ParlaySlip.publication_approved = Column(Boolean, nullable=True)
ParlaySlip.publication_approval_ref = Column(String, nullable=True)


Index("uq_parlays_ticket_key", ParlaySlip.ticket_key, unique=True)


class ParlayLeg(Base):
    __tablename__ = "parlay_legs"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(
        Integer, ForeignKey("parlays.id"), nullable=False
    )
    pick_id = Column(
        Integer, ForeignKey("picks.id"), nullable=False
    )
    position = Column(Integer, nullable=False)
    quoted_odds = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "ticket_id", "position",
            name="uq_parlay_legs_ticket_position"
        ),
        UniqueConstraint(
            "ticket_id", "pick_id",
            name="uq_parlay_legs_ticket_pick"
        ),
    )


def add_missing_columns():
    """create_all never adds columns to old tables, so add any that are missing."""
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            try:
                coltype = col.type.compile(dialect=engine.dialect)
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'))
                log.info("Added missing column %s.%s", table.name, col.name)
            except Exception:
                log.exception("Could not add column %s.%s", table.name, col.name)


def init_db():
    """Create tables if they don't exist yet, then fix old tables."""
    Base.metadata.create_all(bind=engine)
    add_missing_columns()
    for model in (PickLog, ParlaySlip):
        table_name = model.__tablename__
        existing = {
            c["name"] for c in inspect(engine).get_columns(table_name)
        }
        required = {c.name for c in model.__table__.columns}
        if not required.issubset(existing):
            missing = ", ".join(sorted(required - existing))
            raise RuntimeError(
                f"{table_name} schema migration incomplete; "
                f"missing columns: {missing}. Check database logs."
            )
    for model in (PickLog, ParlaySlip):
        for index in model.__table__.indexes:
            index.create(bind=engine, checkfirst=True)
    log.info("Database ready (%s)", engine.dialect.name)