from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class WatchlistRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)


class ManualPositionRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    quantity: int = Field(gt=0)
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    target_price: Optional[float] = Field(default=None, gt=0)
    opened_on: date
    manual_recorded: bool


class ManualCloseRequest(BaseModel):
    exit_price: float = Field(gt=0)
    closed_on: date
    manual_confirmation: bool


class PaperTradeRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    quantity: int = Field(gt=0)
    entry_price: float = Field(gt=0, allow_inf_nan=False)
    stop_loss: float = Field(gt=0, allow_inf_nan=False)
    target_price: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    opened_on: date
    simulation_confirmation: bool


class PaperTradeCloseRequest(BaseModel):
    exit_price: float = Field(gt=0, allow_inf_nan=False)
    closed_on: date
    simulation_confirmation: bool


class TelegramAlertRequest(BaseModel):
    manual_confirmation: bool
