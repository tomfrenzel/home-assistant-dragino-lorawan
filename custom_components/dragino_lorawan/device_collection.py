"""Dragino device collection with uplink timestamp tracking."""

from datetime import datetime
from typing import Protocol, cast, override

from lorawan_connection import DeviceEvent, UplinkEvent

from dragino_lorawan import DraginoDevices


class _TimestampedDevice(Protocol):
    """Expose the timestamp added by this collection."""

    last_uplink: datetime | None


class TimestampedDraginoDevices(DraginoDevices):
    """Track the latest uplink timestamp on each Dragino device."""

    @override
    def handle_event(self, event: DeviceEvent) -> None:
        """Store uplink timestamps before forwarding events to device models."""
        device = self.devices.get(event.dev_eui.replace(":", "").lower())
        updated = False
        if isinstance(event, UplinkEvent) and device is not None:
            timestamped_device = cast(_TimestampedDevice, device)
            last_uplink = getattr(timestamped_device, "last_uplink", None)
            if not isinstance(last_uplink, datetime) or event.received_at > last_uplink:
                timestamped_device.last_uplink = event.received_at
                updated = True

        super().handle_event(event)
        if updated and device is not None:
            device.notify()
