"""
license_server/app/models.py — SQLAlchemy ORM models.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class License(Base):
    __tablename__ = "licenses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, index=True)
    license_key = Column(String(64), nullable=False, unique=True, index=True)
    plan = Column(String(50), nullable=False, default="monthly")
    is_active = Column(Boolean, nullable=False, default=True)

    # Machine binding
    hw_fingerprint = Column(String(64), nullable=True)
    hw_components = Column(JSONB, nullable=True)
    machine_name = Column(String(255), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)

    # Validity
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_verified = Column(DateTime(timezone=True), nullable=True)

    # Payment
    payment_id = Column(String(255), nullable=True)
    payment_amount = Column(Integer, nullable=True)  # in paise (INR)

    # Admin
    notes = Column(Text, nullable=True)
    max_machines = Column(Integer, nullable=False, default=1)

    # Relationships
    logs = relationship("LicenseLog", back_populates="license", lazy="selectin")

    def __repr__(self):
        return f"<License {self.license_key} ({self.email})>"


class LicenseLog(Base):
    __tablename__ = "license_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    license_id = Column(UUID(as_uuid=True), ForeignKey("licenses.id"), nullable=True)
    action = Column(String(50), nullable=False)  # activate, verify, deactivate, reject
    hw_fingerprint = Column(String(64), nullable=True)
    ip_address = Column(String(45), nullable=True)
    details = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    license = relationship("License", back_populates="logs")

    def __repr__(self):
        return f"<LicenseLog {self.action} for {self.license_id}>"
