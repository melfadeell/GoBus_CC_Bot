from datetime import date, datetime, time
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


# Auth
class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# KB
class KbCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name_ar: str


class KbArticleBase(BaseModel):
    category_id: int
    title: str
    slug: str
    content: str
    service_scope: str = "gobus"
    source_file: str | None = None
    is_active: bool = True


class KbArticleCreate(BaseModel):
    category_id: int
    title: str
    slug: str | None = None
    content: str
    service_scope: str = "gobus"
    source_file: str | None = None
    is_active: bool = True


class KbArticleUpdate(BaseModel):
    category_id: int | None = None
    title: str | None = None
    slug: str | None = None
    content: str | None = None
    service_scope: str | None = None
    is_active: bool | None = None


class KbArticleOut(KbArticleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    category: KbCategoryOut | None = None


# Stations
class StationBase(BaseModel):
    name: str
    description: str
    working_hours: str | None = None
    is_24_hours: bool = False
    opens_at: str | None = None
    closes_at: str | None = None
    map_url: str | None = None
    map_text: str | None = None
    city: str | None = None
    is_active: bool = True


class StationCreate(StationBase):
    pass


class StationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    working_hours: str | None = None
    is_24_hours: bool | None = None
    opens_at: str | None = None
    closes_at: str | None = None
    map_url: str | None = None
    map_text: str | None = None
    city: str | None = None
    is_active: bool | None = None


class StationOut(StationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# Destinations
class DestinationBase(BaseModel):
    name_ar: str
    slug: str
    content: str
    gobus_web_id: int | None = None
    is_active: bool = True


class DestinationCreate(BaseModel):
    name_ar: str
    slug: str | None = None
    content: str
    gobus_web_id: int | None = None
    is_active: bool = True


class DestinationUpdate(BaseModel):
    name_ar: str | None = None
    slug: str | None = None
    content: str | None = None
    gobus_web_id: int | None = None
    is_active: bool | None = None


class DestinationOut(DestinationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# Services
class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name_ar: str
    name_en: str
    description: str
    has_detailed_data: bool
    is_active: bool


class ServiceUpdate(BaseModel):
    name_ar: str | None = None
    name_en: str | None = None
    description: str | None = None
    is_active: bool | None = None


# Routes & Trips
class RouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    origin: str
    destination: str
    service_code: str
    duration_minutes: int
    distance_km: int | None


class TripBase(BaseModel):
    route_id: int
    trip_date: date
    departure_time: time
    arrival_time: time
    bus_class: str = "standard"
    total_seats: int = 45
    available_seats: int = 45
    price_egp: float
    is_bookable: bool = True
    status: str = "open"


class TripCreate(TripBase):
    pass


class TripUpdate(BaseModel):
    route_id: int | None = None
    trip_date: date | None = None
    departure_time: time | None = None
    arrival_time: time | None = None
    bus_class: str | None = None
    total_seats: int | None = None
    available_seats: int | None = None
    price_egp: float | None = None
    is_bookable: bool | None = None
    status: str | None = None


class TripOut(TripBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    route: RouteOut | None = None


# Bot settings
class BotSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    system_prompt: str
    greeting_ar: str


class BotSettingsUpdate(BaseModel):
    greeting_ar: str | None = None


class PromptEnhanceRequest(BaseModel):
    instruction: str
    base_prompt: str | None = None


class PromptEnhanceResponse(BaseModel):
    proposed_prompt: str


class PromptSaveRequest(BaseModel):
    system_prompt: str
    instruction_note: str | None = None


class PromptVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    system_prompt: str
    instruction_note: str | None
    created_at: datetime


# Chat
class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=4000)
    session_id: str | None = Field(default=None, max_length=100)
    ocr_text: str | None = Field(default=None, max_length=8000)
    image_url: str | None = Field(default=None, max_length=500)
    channel: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def require_message_or_ocr(self) -> "ChatRequest":
        has_message = bool(self.message.strip())
        has_ocr = bool(self.ocr_text and self.ocr_text.strip())
        has_image = bool(self.image_url and self.image_url.strip())
        if not has_message and not has_ocr and not has_image:
            raise ValueError("message, ocr_text, or image_url is required")
        return self


class OcrResponse(BaseModel):
    text: str


class TextEnhanceRequest(BaseModel):
    text: str


class TextEnhanceResponse(BaseModel):
    text: str


# Conversations
class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    role: str
    content: str
    image_url: str | None = None
    created_at: datetime


class ChatSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    channel: str
    started_at: datetime
    message_count: int = 0


class DashboardStats(BaseModel):
    total_sessions: int
    total_messages: int
    total_tokens: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost_usd: float = 0.0
    kb_articles: int
    stations: int
    destinations: int
    active_trips: int


class ChannelTokenStat(BaseModel):
    channel: str
    sessions: int
    messages: int
    total_tokens: int
    prompt_tokens: int = 0
    completion_tokens: int = 0


class DailyAnalyticsPoint(BaseModel):
    date: str
    messages: int
    tokens: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


class DashboardAnalytics(BaseModel):
    by_channel: list[ChannelTokenStat]
    daily: list[DailyAnalyticsPoint]


# Metrics (logs DB)
class MetricsOverview(BaseModel):
    total_requests: int
    chat_turns: int
    llm_calls: int
    errors: int
    rate_limit_hits: int
    avg_latency_sec: float
    total_tokens: int
    date_from: str | None = None
    date_to: str | None = None


class MetricsDailyPoint(BaseModel):
    date: str
    requests: int
    chat_turns: int
    tokens: int
    errors: int
    rate_limit_hits: int


class MetricsCharts(BaseModel):
    daily: list[MetricsDailyPoint]


class ApiRequestLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str
    api_method: str
    api_path: str
    client_ip: str | None
    status_code: int | None
    response_time_sec: float | None
    success: bool
    error_message: str | None
    created_at: datetime


class ChatLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str | None
    session_id: str
    channel: str | None
    client_ip: str | None
    user_message: str | None
    ai_response: str | None
    model: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    response_time_sec: float | None
    has_image: bool
    success: bool
    error_message: str | None
    created_at: datetime


class LlmCallLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str | None
    session_id: str | None
    model: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    response_time_sec: float | None
    success: bool
    error_message: str | None
    created_at: datetime


class AuthLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    action: str
    client_ip: str | None
    status_code: int
    success: bool
    created_at: datetime


class ErrorLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str | None
    error_type: str
    message: str | None
    stack_trace: str | None
    created_at: datetime
