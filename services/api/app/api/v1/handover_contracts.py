from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HandoverCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    channel_id: str = Field(alias="channelId", min_length=1)
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    source_type: str | None = Field(default=None, alias="sourceType")
    source_id: str | None = Field(default=None, alias="sourceId")
    source_version_id: str | None = Field(default=None, alias="sourceVersionId")
    recipient_ids: list[str] = Field(alias="recipientIds", min_length=1)
    entry_source: str = Field(default="field_user", alias="entrySource", max_length=30)
    device_id: str | None = Field(default=None, alias="deviceId", max_length=64)
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey", max_length=160)


class HandoverReceiptUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    receipt_status: str = Field(alias="receiptStatus", min_length=1)
    note: str | None = None
    delivery_run_id: str | None = Field(default=None, alias="deliveryRunId", max_length=120)
    displayed_at: datetime | None = Field(default=None, alias="displayedAt")


class HandoverReceiptResponse(BaseModel):
    receipt_id: str
    handover_id: str
    recipient_id: str
    receipt_status: str
    note: str | None
    read_at: datetime | None
    acknowledged_at: datetime | None
    follow_up_required_at: datetime | None
    updated_by: str | None
    created_at: datetime
    updated_at: datetime


class HandoverResponse(BaseModel):
    handover_id: str
    idempotency_key: str | None
    channel_id: str
    title: str
    body: str
    source_type: str | None
    source_id: str | None
    source_version_id: str | None
    status: str
    created_by: str | None
    entry_source: str
    device_id: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime
    receipts: list[HandoverReceiptResponse]
