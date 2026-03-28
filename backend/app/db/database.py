"""SQLAlchemy async database setup and ORM models."""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from app.core.config import settings


# ── Engine & Session ───────────────────────────────────

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ── ORM Models ─────────────────────────────────────────

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String(255), unique=True, index=True)
    device_fingerprint = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    flagged = Column(Boolean, default=False)

    claims = relationship("Claim", back_populates="account")


class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_db_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    filename = Column(String(512), nullable=False)
    image_path = Column(String(1024), nullable=False)
    risk_score = Column(Float, default=0.0)
    risk_tier = Column(String(16), default="low")
    layer_scores = Column(JSON, default=dict)
    ela_heatmap_path = Column(String(1024), nullable=True)
    gemini_reasoning = Column(Text, nullable=True)
    processing_time_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    account = relationship("Account", back_populates="claims")
    image_hashes = relationship("ImageHash", back_populates="claim", uselist=False)


class ImageHash(Base):
    __tablename__ = "image_hashes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    ahash = Column(String(64), nullable=True)
    phash = Column(String(64), nullable=True)
    dhash = Column(String(64), nullable=True)
    whash = Column(String(64), nullable=True)

    claim = relationship("Claim", back_populates="image_hashes")


class HashMatchRecord(Base):
    __tablename__ = "hash_matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    claim_id = Column(Integer, ForeignKey("claims.id"), nullable=False)
    matched_claim_id = Column(Integer, nullable=False)
    hamming_distance = Column(Integer, nullable=False)
    hash_type = Column(String(16), nullable=False)


# ── Helpers ────────────────────────────────────────────

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
