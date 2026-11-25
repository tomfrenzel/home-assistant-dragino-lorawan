"""Behaviour shared by all Dragino models."""

from datetime import datetime

from lorawan_connection import Device, DeviceDescriptor, UplinkEvent


class DraginoBaseDevice(Device):
    """Track the link quality of every uplink, whatever its payload."""

    def __init__(self, descriptor: DeviceDescriptor) -> None:
        """Initialize unknown link quality."""
        super().__init__(descriptor)
        self.rssi: float | None = None
        self.snr: float | None = None
        self._signal_updated: datetime | None = None

    def _update_signal(self, event: UplinkEvent) -> None:
        """Keep the strongest gateway reception of the latest uplink."""
        if (
            self._signal_updated is not None
            and event.received_at < self._signal_updated
        ):
            return
        measured = [
            reception for reception in event.receptions if reception.rssi is not None
        ]
        if not measured:
            return
        best = max(measured, key=lambda reception: reception.rssi or 0)
        self.rssi = best.rssi
        self.snr = best.snr
        self._signal_updated = event.received_at
        # Notifications are coalesced while the device handles an event.
        self.notify()
