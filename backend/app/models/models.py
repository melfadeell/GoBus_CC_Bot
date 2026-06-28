from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Customer(Base):
    """End-customer account (distinct from AdminUser). Created via self-register
    from the chat; used for ticketing + personalized greeting."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(40), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Ticket(Base):
    """A customer support ticket raised from the bot (or via the external API)."""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ref_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    # Either a logged-in customer OR an anonymous guest (email+phone captured).
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    guest_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guest_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guest_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    channel: Mapped[str] = mapped_column(String(50), default="website")
    category: Mapped[str] = mapped_column(String(40), default="other")
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="open")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    # The classifier's original priority (admin may override `priority`).
    priority_auto: Mapped[str | None] = mapped_column(String(20), nullable=True)
    assigned_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id"), nullable=True
    )
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    messages: Mapped[list["TicketMessage"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )
    customer: Mapped["Customer | None"] = relationship()


class TicketMessage(Base):
    """A single entry in a ticket's thread (customer / agent / bot / system)."""

    __tablename__ = "ticket_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    author_type: Mapped[str] = mapped_column(String(20), nullable=False)
    author_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    ticket: Mapped["Ticket"] = relationship(back_populates="messages")


class EmailOtp(Base):
    """One-time code emailed to a guest to verify their email before they can
    create / look up a ticket. The code is stored hashed."""

    __tablename__ = "email_otps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False, default="ticket_create")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class KbCategory(Base):
    __tablename__ = "kb_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    articles: Mapped[list["KbArticle"]] = relationship(back_populates="category")


class KbArticle(Base):
    __tablename__ = "kb_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("kb_categories.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    service_scope: Mapped[str] = mapped_column(String(50), default="gobus")
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    category: Mapped["KbCategory"] = relationship(back_populates="articles")


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    working_hours: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_24_hours: Mapped[bool] = mapped_column(Boolean, default=False)
    opens_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    closes_at: Mapped[str | None] = mapped_column(String(20), nullable=True)
    map_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    map_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Destination(Base):
    __tablename__ = "destinations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    gobus_web_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    has_detailed_data: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    origin: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    service_code: Mapped[str] = mapped_column(String(50), default="gobus")
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    trips: Mapped[list["Trip"]] = relationship(back_populates="route")


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), nullable=False)
    trip_date: Mapped[date] = mapped_column(Date, nullable=False)
    departure_time: Mapped[time] = mapped_column(Time, nullable=False)
    arrival_time: Mapped[time] = mapped_column(Time, nullable=False)
    bus_class: Mapped[str] = mapped_column(String(50), default="standard")
    total_seats: Mapped[int] = mapped_column(Integer, default=45)
    available_seats: Mapped[int] = mapped_column(Integer, default=45)
    price_egp: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    is_bookable: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    departure_station_id: Mapped[int | None] = mapped_column(
        ForeignKey("stations.id"), nullable=True
    )
    arrival_station_id: Mapped[int | None] = mapped_column(
        ForeignKey("stations.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    route: Mapped["Route"] = relationship(back_populates="trips")
    departure_station: Mapped["Station | None"] = relationship(foreign_keys=[departure_station_id])
    arrival_station: Mapped["Station | None"] = relationship(foreign_keys=[arrival_station_id])

    @property
    def departure_station_name(self) -> str | None:
        return self.departure_station.name if self.departure_station else None

    @property
    def arrival_station_name(self) -> str | None:
        return self.arrival_station.name if self.arrival_station else None


class BotSettings(Base):
    __tablename__ = "bot_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    greeting_ar: Mapped[str] = mapped_column(Text, nullable=False)
    hotline: Mapped[str] = mapped_column(String(50), default="19567")
    model_name: Mapped[str] = mapped_column(String(50), default="gpt-5.4-mini")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class BotPromptVersion(Base):
    __tablename__ = "bot_prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    instruction_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"), nullable=True)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(50), default="web")
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.session_id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
