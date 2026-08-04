from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(180))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    landing_title: Mapped[str] = mapped_column(String(220), default="Dapatkan File Excel")
    landing_description: Mapped[str] = mapped_column(Text, default="Isi data singkat untuk memperoleh akses personal.")
    landing_body: Mapped[str] = mapped_column(Text, default="")
    highlights: Mapped[str] = mapped_column(Text, default="")
    business_types: Mapped[str] = mapped_column(Text, default="FMCG\nRetail\nEducation\nTechnology\nOther")
    master_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Kept for backwards compatibility with v0.4. Existing cover files are
    # automatically exposed as the first slide when no gallery rows exist.
    cover_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expiry_hours: Mapped[int] = mapped_column(Integer, default=48)
    max_downloads: Mapped[int] = mapped_column(Integer, default=2)
    product_mode: Mapped[str] = mapped_column(String(20), default="free", index=True)
    price_amount: Mapped[int] = mapped_column(Integer, default=0)
    checkout_url: Mapped[str | None] = mapped_column(String(700), nullable=True)
    payment_instructions: Mapped[str] = mapped_column(Text, default="")
    purchase_button_label: Mapped[str] = mapped_column(String(80), default="BELI SEKARANG")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    leads: Mapped[list[Lead]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    images: Mapped[list[CampaignImage]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="CampaignImage.sort_order, CampaignImage.id",
    )

    @property
    def business_type_options(self) -> list[str]:
        return [item.strip() for item in self.business_types.splitlines() if item.strip()]

    @property
    def highlight_options(self) -> list[str]:
        return [item.strip() for item in self.highlights.splitlines() if item.strip()]

    @property
    def is_paid(self) -> bool:
        return self.product_mode == "paid"

    @property
    def formatted_price(self) -> str:
        if self.price_amount <= 0:
            return "Harga belum ditentukan"
        return f"Rp{self.price_amount:,.0f}".replace(",", ".")

    @property
    def storefront_label(self) -> str:
        return self.formatted_price if self.is_paid else "GRATIS"


class CampaignImage(Base):
    __tablename__ = "campaign_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    alt_text: Mapped[str] = mapped_column(String(220), default="Preview produk")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    campaign: Mapped[Campaign] = relationship(back_populates="images")


class SiteSetting(Base):
    __tablename__ = "site_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    home_mode: Mapped[str] = mapped_column(String(20), default="redirect")
    home_campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    email: Mapped[str] = mapped_column(String(254), index=True)
    business_type: Mapped[str] = mapped_column(String(180))
    whatsapp: Mapped[str] = mapped_column(String(40))
    request_ip: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    payment_status: Mapped[str] = mapped_column(String(30), default="not_required", index=True)
    payment_amount: Mapped[int] = mapped_column(Integer, default=0)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    license_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    access_token: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    access_password_enc: Mapped[str] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    campaign: Mapped[Campaign] = relationship(back_populates="leads")
    download: Mapped[Download | None] = relationship(back_populates="lead", uselist=False, cascade="all, delete-orphan")


class Download(Base):
    __tablename__ = "downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id"), unique=True, index=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    max_downloads: Mapped[int] = mapped_column(Integer, default=2)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lead: Mapped[Lead] = relationship(back_populates="download")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=4)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
