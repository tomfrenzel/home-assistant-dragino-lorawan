"""Tests for Dragino payloads."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from lorawan_connection import DeviceDescriptor, UplinkEvent
from lorawan_connection.mock import MockConnection
import pytest

from custom_components.dragino_lorawan._vendor.dragino_lorawan import (
    CPL03LB,
    LHT65,
    LT22222,
    DraginoDevices,
)


async def test_lht65_payload(descriptor: DeviceDescriptor) -> None:
    """Decode the TTN example and ignore malformed or older readings."""
    connection = MockConnection([descriptor], stack_type="tts")
    collection = DraginoDevices(connection)
    await collection.async_setup()
    device = collection.devices[descriptor.dev_eui]
    event = UplinkEvent(
        received_at=datetime.now(UTC),
        descriptor=descriptor,
        f_port=2,
        data=bytes.fromhex("cbf60b0d0376010add7fff"),
    )
    connection.emit(event)
    assert device.temperature == 28.29
    assert device.humidity == 88.6
    assert device.external_temperature == 27.81
    assert device.battery_voltage == 3.062
    connection.emit(replace(event, data=b"\x01"))
    connection.emit(replace(event, f_port=99))
    connection.emit(
        replace(
            event, received_at=event.received_at - timedelta(seconds=1), data=bytes(11)
        )
    )
    assert device.temperature == 28.29
    collection.close()


@pytest.mark.parametrize(
    ("payload", "key", "expected"),
    [
        ("cbeaff9c026d01ff387fff", "external_temperature", -2),
        ("cbf60b0d0376817fff7fff", "external_temperature", None),
        ("cbf60b0d03760500647fff", "illuminance", 100),
        ("cbf60b0d0376060bb87fff", "external_voltage", 3),
        ("cbf60b0d0376080000000a", "external_count", 10),
    ],
)
def test_extensions(payload: str, key: str, expected: float | None) -> None:
    """Decode external probes and disconnected sensors."""
    assert LHT65.decode(bytes.fromhex(payload))[key] == expected


def test_history() -> None:
    """Ignore datalog replies."""
    assert LHT65.decode(bytes.fromhex("cbea0105026d4101aa7fff")) == {}


@pytest.mark.parametrize("payload", ["01", "cbf60b0d037601", "cbf60b0d0fff010add7fff"])
def test_invalid_payload(payload: str) -> None:
    """Reject incomplete frames and invalid humidity."""
    with pytest.raises(ValueError):
        LHT65.decode(bytes.fromhex(payload))


@pytest.mark.parametrize(
    ("port", "payload", "expected"),
    [
        (
            2,
            "37ffffff010203ffffffff",
            {
                "work_mode": "cpl01",
                "counts_are_cumulative": False,
                "contact_open": True,
                "alarm": True,
                "pulse_count": 16777215,
                "last_duration": 66051,
            },
        ),
        (
            2,
            "0000000200003c00000000",
            {"contact_open": False, "alarm": False, "last_duration": 60},
        ),
        (
            6,
            "3f800000ffffff01020305",
            {
                "work_mode": "cpl03",
                "counts_are_cumulative": False,
                "pa8_count": 8388608,
                "pa4_count": 16777215,
                "pb15_count": 66051,
            },
        ),
        (
            6,
            "08000005000006ffffff",
            {
                "counts_are_cumulative": True,
                "pa8_count": 5,
                "pa4_count": 6,
                "pb15_count": 16777215,
            },
        ),
        (
            7,
            "19",
            {"pa8_open": False, "pa4_open": True, "pb15_open": False},
        ),
        (
            7,
            "26ffffffffffffffffffff",
            {"pa8_open": True, "pa4_open": False, "pb15_open": True},
        ),
        (5, "20011101ff0b45", {"firmware_version": "1.1.1", "battery_voltage": 2.885}),
        (5, "20011102030e10", {"firmware_version": "1.1.1", "battery_voltage": 3.6}),
    ],
)
def test_cpl03lb_codec_examples(
    port: int, payload: str, expected: dict[str, str | float | int | bool]
) -> None:
    """Match the ChirpStack catalog's unsigned values, units, and contact bits."""
    values = CPL03LB.decode(port, bytes.fromhex(payload))
    assert values.items() >= expected.items()


@pytest.mark.parametrize(
    ("port", "payload"),
    [
        (port, data[:length])
        for port, data in (
            (2, bytes(11)),
            (5, bytes.fromhex("20011101ff0b45")),
            (6, bytes.fromhex("08000005000006000007")),
            (7, b"\x00"),
        )
        for length in range(len(data))
    ]
    + [
        (2, bytes(12)),
        (5, bytes.fromhex("20011101ff0b4500")),
        (6, b"\x08" + bytes(11)),
        (2, b"\x08" + bytes(10)),
        (6, bytes(10)),
        (5, bytes.fromhex("21011101ff0b45")),
        (5, bytes.fromhex("20011100ff0b45")),
        (5, bytes.fromhex("2001110fff0b45")),
    ],
)
def test_cpl03lb_invalid_payload(port: int, payload: bytes) -> None:
    """Reject truncated, oversized, mismatched-mode, and wrong-model packets."""
    with pytest.raises(ValueError):
        CPL03LB.decode(port, payload)


@pytest.mark.parametrize("port", [3, 4, 8, 99])
def test_cpl03lb_non_measurements(port: int) -> None:
    """Do not turn history, configuration, or unknown layouts into live readings."""
    assert CPL03LB.decode(port, bytes(11)) == {}


def test_cpl03lb_partial_and_stale_updates(descriptor: DeviceDescriptor) -> None:
    """Retain independent reports and reject older values without notifying."""
    device = CPL03LB(descriptor)
    notified = Mock()
    device.add_update_listener(notified)
    event = UplinkEvent(
        descriptor=descriptor,
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
        f_port=2,
        data=bytes.fromhex("0300000200003c00000000"),
    )
    device.handle_event(event)
    status = replace(
        event,
        received_at=event.received_at + timedelta(seconds=2),
        f_port=5,
        data=bytes.fromhex("20011101ff0b45"),
    )
    device.handle_event(status)
    # A status report must not suppress a delayed but newer contact reading.
    contact = replace(
        event, received_at=event.received_at + timedelta(seconds=1), data=bytes(11)
    )
    device.handle_event(contact)
    assert device.contact_open is False
    assert device.pulse_count == 0
    assert device.battery_voltage == 2.885
    assert notified.call_count == 3
    for ignored in (
        event,
        replace(status, received_at=event.received_at),
        replace(status, data=b""),
        replace(status, f_port=99),
    ):
        device.handle_event(ignored)
    assert notified.call_count == 3
    device.close()
    device.handle_event(replace(event, received_at=status.received_at))
    assert notified.call_count == 3
    assert device.contact_open is False


def test_cpl03lb_mode_changes(descriptor: DeviceDescriptor) -> None:
    """Clear all inactive-mode readings, including stale interrupt levels."""
    device = CPL03LB(descriptor)
    event = UplinkEvent(
        descriptor=descriptor,
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
        f_port=7,
        data=b"\x00",
    )
    device.handle_event(event)
    assert device.work_mode == "interrupt"
    assert device.pa8_open is True
    single = replace(
        event,
        received_at=event.received_at + timedelta(seconds=1),
        f_port=2,
        data=bytes.fromhex("0300000200003c00000000"),
    )
    device.handle_event(single)
    assert device.work_mode == "cpl01"
    assert device.contact_open is True
    assert device.pa8_open is None
    assert device.pa8_count is None
    pulse = replace(
        event,
        received_at=event.received_at + timedelta(seconds=2),
        f_port=6,
        data=bytes.fromhex("08000005000006000007"),
    )
    device.handle_event(pulse)
    assert device.work_mode == "cpl03"
    assert device.pa8_count == 5
    assert device.contact_open is None
    assert device.alarm is None
    assert device.pulse_count is None
    assert device.last_duration is None
    device.handle_event(single)
    device.handle_event(event)
    assert device.work_mode == "cpl03"
    assert device.pa8_count == 5
    assert device.pa8_open is None
    device.handle_event(
        replace(event, received_at=event.received_at + timedelta(seconds=3))
    )
    assert device.work_mode == "interrupt"
    assert device.pa8_count is None
    assert device.pa8_open is True
    assert device.counts_are_cumulative is None


def test_lt22222_status(descriptor: DeviceDescriptor) -> None:
    """Decode the firmware version of a port-5 status report."""
    device = LT22222(descriptor)
    notified = Mock()
    device.add_update_listener(notified)
    # EU868, no sub-band, firmware 1.1.3, 600 s interval.
    status = UplinkEvent(
        descriptor=descriptor,
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
        f_port=5,
        data=bytes.fromhex("01ff0113000258"),
    )
    device.handle_event(status)
    assert device.firmware_version == "1.1.3"
    assert device.mode is None
    assert notified.call_count == 1
    newer = bytes.fromhex("01ff0220000258")
    for ignored in (
        replace(
            status, received_at=status.received_at - timedelta(seconds=1), data=newer
        ),
        replace(status, data=newer[:6]),
        replace(status, data=b"\x00" + newer[1:]),
    ):
        device.handle_event(ignored)
    assert device.firmware_version == "1.1.3"
    assert notified.call_count == 1
