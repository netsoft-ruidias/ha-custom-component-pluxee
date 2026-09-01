"""Card Class."""

from datetime import datetime, timezone
from homeassistant.util import dt

class Card:
    """Represents a Pluxee card."""

    def __init__(self, data):
        self._data = data
        
    @property
    def id(self):
        return self._data["id"]

    @property
    def activated_at(self) -> datetime:
        raw = self._data.get("activated_at")
        return dt.parse_datetime(raw).astimezone(timezone.utc) if raw else None

    @property
    def expiration_date(self) -> datetime:
        raw = self._data.get("expiration_date")
        return dt.parse_datetime(raw).astimezone(timezone.utc) if raw else None

    @property
    def holder_company_name(self) -> str:
        return self._data.get("holder_company_name", "")

    @property
    def holder_name(self) -> str:
        return self._data.get("holder_name", "")

    @property
    def pan_last_digits(self) -> str:
        return self._data.get("pan_last_digits", "")

    @property
    def status(self):
        return self._data.get("status", "")

    def __repr__(self):
        return f"Card({self._data.get('holder_name')} [{self._data.get('status')}] pan=****{self._data.get('pan_last_digits')})"


class Balance:
    """Represents a Pluxee Balance."""

    def __init__(self, data):
        self._data = data
        
    @property
    def id(self):
        return self._data.get("id", "")

    @property
    def balance(self) -> float:
        amount = self._data.get("balance", {}).get("amount", 0)
        return float(amount) / 100

    @property
    def currency(self) -> str:
        return self._data.get("balance", {}).get("currency", "EUR")

    @property
    def type(self):
        return self._data.get("type", "")


class Transaction:
    """Represents a Pluxee Transaction."""

    def __init__(self, data):
        self._data = data
        
    @property
    def date(self) -> datetime:
        return dt.parse_datetime(self._data.get("executed_at", "")).astimezone(timezone.utc)

    @property
    def description(self) -> str:
        return self._data.get("description", "")

    @property
    def amount(self) -> float:
        amount = float(self._data.get("amount", {}).get("amount", 0)) / 100
        if self._data.get("is_debit"):
            return 0 - amount
        else:
            return amount

    @property
    def currency(self) -> str:
        return self._data.get("amount", {}).get("currency", "EUR")
