from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from .models import Order


class BaseBrokerGateway(ABC):
    """
    Abstract base class for broker gateways.
    Defines the contract for submitting orders, checking statuses,
    and managing the physical connection to a broker or simulation engine.
    """

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the broker."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the broker."""
        pass

    @abstractmethod
    def submit_orders(self, orders: Sequence[Order]) -> list[Order]:
        """
        Submit a batch of orders to the broker.
        Should return the updated orders with assigned broker IDs and initial statuses.
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Attempt to cancel an order. Returns True if cancellation was sent successfully.
        """
        pass

    @abstractmethod
    def sync_orders(self, orders: Sequence[Order]) -> list[Order]:
        """
        Sync the status of active orders with the broker.
        Returns the list of updated orders.
        """
        pass

    @abstractmethod
    def get_account_cash(self) -> float:
        """Return the current available cash in the account."""
        pass

    @abstractmethod
    def get_account_positions(self) -> dict[str, int]:
        """Return a mapping of symbol to current holding shares."""
        pass
