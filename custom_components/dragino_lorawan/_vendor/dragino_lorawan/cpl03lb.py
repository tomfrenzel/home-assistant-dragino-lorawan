"""Dragino CPL03-LB pulse and dry-contact telemetry."""

from datetime import datetime
import logging
from typing import override

from lorawan_connection import DeviceDescriptor, DeviceEvent, EventType

from .base import DraginoBaseDevice

_LOGGER = logging.getLogger(__name__)

_SINGLE_FIELDS = ("contact_open", "alarm", "pulse_count", "last_duration")
_COUNTER_FIELDS = ("pa8_count", "pa4_count", "pb15_count")
_CONTACT_FIELDS = ("pa8_open", "pa4_open", "pb15_open")


class CPL03LB(DraginoBaseDevice):
    """A single-contact, three-counter, or three-interrupt sensor."""

    identifiers = {
        "chirpstack": (676, "621f921e-4685-4421-b8a0-b4cc6b5d77b8"),
        "tts": ("dragino", "cpl03-lb"),
    }
    model_name = "CPL03-LB"

    def __init__(self, descriptor: DeviceDescriptor) -> None:
        """Initialize unknown readings until the device reports them."""
        super().__init__(descriptor)
        self.work_mode: str | None = None
        self.counts_are_cumulative: bool | None = None
        self.contact_open: bool | None = None
        self.alarm: bool | None = None
        self.pulse_count: int | None = None
        self.last_duration: int | None = None
        self.pa8_count: int | None = None
        self.pa4_count: int | None = None
        self.pb15_count: int | None = None
        self.pa8_open: bool | None = None
        self.pa4_open: bool | None = None
        self.pb15_open: bool | None = None
        self.battery_voltage: float | None = None
        self.firmware_version: str | None = None
        self._updated: dict[str, datetime] = {}

    @override
    def handle_event(self, event: DeviceEvent) -> None:
        """Apply validated, current fields without replacing unrelated readings."""
        if self.closed or event.type != EventType.UPLINK:
            return
        self._update_signal(event)
        try:
            values = self.decode(event.f_port, event.data)
        except ValueError as err:
            _LOGGER.debug("Ignoring CPL03-LB uplink on port %s: %s", event.f_port, err)
            return
        if not values:
            return
        # Status and the mutually exclusive input modes have independent clocks.
        group = "status" if event.f_port == 5 else "inputs"
        if group in self._updated and event.received_at < self._updated[group]:
            return
        for key, value in values.items():
            setattr(self, key, value)
        self._updated[group] = event.received_at
        self.notify()

    @staticmethod
    def decode(f_port: int, data: bytes) -> dict[str, str | float | int | bool | None]:
        """Decode live reports; history and configuration are not measurements."""
        if f_port not in (2, 5, 6, 7):
            return {}
        if (f_port == 7 and not data) or (
            f_port != 7 and len(data) not in {2: (11,), 5: (7,), 6: (10, 11)}[f_port]
        ):
            raise ValueError("Invalid payload length")
        if f_port == 5:
            if data[0] != 0x20:
                raise ValueError("Unexpected sensor model")
            if not 1 <= data[3] <= 14:
                raise ValueError("Unknown frequency band")
            return {
                "firmware_version": (
                    f"{data[1] & 0x0F}.{data[2] >> 4}.{data[2] & 0x0F}"
                ),
                "battery_voltage": int.from_bytes(data[5:7]) / 1000,
            }
        if f_port == 7:
            # Status bits mean CLOSED; interrupt bits do not indicate the level.
            return {
                **dict.fromkeys((*_SINGLE_FIELDS, *_COUNTER_FIELDS)),
                "work_mode": "interrupt",
                "counts_are_cumulative": None,
                "pa8_open": not bool(data[0] & 0x01),
                "pa4_open": not bool(data[0] & 0x04),
                "pb15_open": not bool(data[0] & 0x10),
            }
        if bool(data[0] & 0x08) != (f_port == 6):
            raise ValueError("Unexpected work mode")
        values: dict[str, str | float | int | bool | None] = {
            "work_mode": "cpl01" if f_port == 2 else "cpl03",
            "counts_are_cumulative": not bool(data[0] & 0x20),
        }
        if f_port == 2:
            values.update(dict.fromkeys((*_COUNTER_FIELDS, *_CONTACT_FIELDS)))
            values.update(
                contact_open=bool(data[0] & 0x01),
                alarm=bool(data[0] & 0x02),
                pulse_count=int.from_bytes(data[1:4]),
                last_duration=int.from_bytes(data[4:7]),
            )
        else:
            values.update(dict.fromkeys((*_SINGLE_FIELDS, *_CONTACT_FIELDS)))
            values.update(
                pa8_count=int.from_bytes(data[1:4]),
                pa4_count=int.from_bytes(data[4:7]),
                pb15_count=int.from_bytes(data[7:10]),
            )
        return values

    async def async_request_device_status(self) -> None:
        """Queue a device-information request for the next receive window."""
        await self.async_send_downlink(data=b"\x26\x01", f_port=2, wait_for_ack=False)
