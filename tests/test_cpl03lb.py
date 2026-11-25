"""CPL03-LB discovery, entities, lifecycle, and status requests."""

from asyncio import Event, timeout
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from dragino_lorawan import CPL03LB
from homeassistant.components.lorawan import LoRaWANDiscoveryInfo
from homeassistant.components.lorawan.websocket_api import _snapshot
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from lorawan_connection import (
    AddedEvent,
    ConnectionUnavailable,
    DeviceDescriptor,
    DownlinkError,
    RemovedEvent,
    UplinkEvent,
)
from lorawan_connection.mock import MockConnection
import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.dragino_lorawan.const import DOMAIN


@pytest.fixture(
    params=[
        ("tts", "dragino", "cpl03-lb"),
        ("chirpstack", 676, "621f921e-4685-4421-b8a0-b4cc6b5d77b8"),
    ],
    ids=["tts", "chirpstack"],
)
def descriptor(request: pytest.FixtureRequest) -> DeviceDescriptor:
    """Use actual catalog identifiers, not a local profile name."""
    stack, brand_id, model_id = request.param
    return DeviceDescriptor(
        network_id="network",
        dev_eui="0201010101010101",
        name="Garden",
        stack=stack,
        brand_id=brand_id,
        model_id=model_id,
        application_id="app",
        profile_id="local-profile",
    )


@pytest.fixture
def mock_connection(descriptor: DeviceDescriptor) -> MockConnection:
    """Connect the selected backend."""
    return MockConnection([descriptor], stack_type=descriptor.stack)


@pytest.mark.usefixtures("connection_entry")
@pytest.mark.parametrize("source", [SOURCE_USER, SOURCE_INTEGRATION_DISCOVERY])
async def test_setup(hass: HomeAssistant, source: str) -> None:
    """Accept CPL03-LB as the only supported device on either backend."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": source},
        data=LoRaWANDiscoveryInfo() if source == SOURCE_INTEGRATION_DISCOVERY else None,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    hass.config_entries.flow.async_abort(result["flow_id"])


@pytest.mark.usefixtures("connection_entry", "entity_registry_enabled_by_default")
async def test_entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    descriptor: DeviceDescriptor,
    mock_connection: MockConnection,
) -> None:
    """Expose typed readings, stable identities, mode transitions, and metadata."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert isinstance(
        config_entry.runtime_data.coordinators[("network", descriptor.dev_eui)].data,
        CPL03LB,
    )
    entities = er.async_entries_for_config_entry(
        er.async_get(hass), config_entry.entry_id
    )
    for entity in entities:
        assert hass.states.get(entity.entity_id).state == "unknown"
        assert entity.unique_id.startswith(f"network:{descriptor.dev_eui}:")
    contact = er.async_get(hass).async_get("binary_sensor.garden_opening")
    assert contact.unique_id == f"network:{descriptor.dev_eui}:contact_open"
    device = dr.async_get(hass).async_get(contact.device_id)
    assert device.model_id == "CPL03-LB"
    assert device.manufacturer == "Dragino"
    event = UplinkEvent(
        descriptor=descriptor,
        received_at=datetime.now(UTC),
        f_port=2,
        data=bytes.fromhex("0300000200003c00000000"),
    )
    mock_connection.emit(event)
    await hass.async_block_till_done()
    for entity_id, expected in {
        "binary_sensor.garden_opening": "on",
        "binary_sensor.garden_contact_alarm": "on",
        "sensor.garden_pulse_count": "2",
        "sensor.garden_last_event_duration": "60",
        "sensor.garden_work_mode": "cpl01",
        "sensor.garden_pa8_pulse_count": "unknown",
        "binary_sensor.garden_pa8_contact": "unknown",
    }.items():
        assert hass.states.get(entity_id).state == expected
    assert (
        hass.states.get("sensor.garden_last_event_duration").attributes[
            "unit_of_measurement"
        ]
        == "s"
    )
    assert (
        hass.states.get("sensor.garden_pulse_count").attributes["state_class"]
        == "total_increasing"
    )
    mock_connection.emit(replace(event, f_port=5, data=bytes.fromhex("20011101ff0b45")))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.garden_battery_voltage").state == "2.885"
    assert hass.states.get("sensor.garden_firmware_version").state == "1.1.1"
    assert hass.states.get("sensor.garden_battery").state == "unknown"
    mock_connection.emit(
        replace(
            event,
            received_at=event.received_at + timedelta(seconds=1),
            f_port=6,
            data=bytes.fromhex("3f800000ffffff01020305"),
        )
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.garden_work_mode").state == "cpl03"
    for name in ("pulse_count", "last_event_duration"):
        assert hass.states.get(f"sensor.garden_{name}").state == "unknown"
    assert hass.states.get("binary_sensor.garden_opening").state == "unknown"
    assert hass.states.get("binary_sensor.garden_contact_alarm").state == "unknown"
    assert hass.states.get("sensor.garden_pa8_pulse_count").state == "8388608"
    assert hass.states.get("sensor.garden_pa4_pulse_count").state == "16777215"
    assert hass.states.get("sensor.garden_pb15_pulse_count").state == "66051"
    assert (
        "state_class" not in hass.states.get("sensor.garden_pa8_pulse_count").attributes
    )
    mock_connection.emit(
        replace(
            event,
            received_at=event.received_at + timedelta(seconds=2),
            f_port=7,
            data=b"\x19",
        )
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.garden_work_mode").state == "interrupt"
    assert hass.states.get("sensor.garden_pa8_pulse_count").state == "unknown"
    for pin, expected in (("pa8", "off"), ("pa4", "on"), ("pb15", "off")):
        assert hass.states.get(f"binary_sensor.garden_{pin}_contact").state == expected
    metadata = next(
        entry
        for entry in _snapshot(hass)["devices"]
        if entry["dev_eui"] == descriptor.dev_eui
    )
    assert metadata["device_id"] == device.id
    assert metadata["support"] == "supported"
    mock_connection.disconnect()
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.garden_pa8_contact").state == "unavailable"
    await hass.config_entries.async_unload(config_entry.entry_id)


@pytest.mark.usefixtures("connection_entry")
async def test_defaults_and_removal(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    descriptor: DeviceDescriptor,
    mock_connection: MockConnection,
) -> None:
    """Register disabled diagnostics and remove them with the device."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    battery = registry.async_get("sensor.garden_battery")
    assert battery.disabled_by is None
    assert battery.entity_category is er.EntityCategory.DIAGNOSTIC
    for key in (
        "battery_voltage",
        "last_event_duration",
        "pulse_count",
        "pa8_pulse_count",
        "pa4_pulse_count",
        "pb15_pulse_count",
    ):
        entity_id = f"sensor.garden_{key}"
        entity = registry.async_get(entity_id)
        assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert entity.entity_category is er.EntityCategory.DIAGNOSTIC
        assert hass.states.get(entity_id) is None
    # User-enabled diagnostics must receive the same live reports.
    registry.async_update_entity("sensor.garden_pulse_count", disabled_by=None)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    mock_connection.emit(
        UplinkEvent(
            descriptor=descriptor,
            received_at=datetime.now(UTC),
            f_port=2,
            data=bytes.fromhex("0000000200003c00000000"),
        )
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.garden_pulse_count").state == "2"
    mock_connection.emit(RemovedEvent(descriptor=descriptor))
    await hass.async_block_till_done()
    assert not er.async_entries_for_config_entry(registry, config_entry.entry_id)
    assert not dr.async_entries_for_config_entry(
        dr.async_get(hass), config_entry.entry_id
    )
    mock_connection.emit(AddedEvent(descriptor=descriptor))
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.garden_opening").state == "unknown"
    await hass.config_entries.async_unload(config_entry.entry_id)


@pytest.mark.usefixtures("connection_entry")
async def test_request_status(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    descriptor: DeviceDescriptor,
    mock_connection: MockConnection,
) -> None:
    """Queue the documented command without an ACK or optimistic readings."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    entity_id = "button.garden_request_device_status"
    entity = er.async_get(hass).async_get(entity_id)
    assert entity.unique_id == f"network:{descriptor.dev_eui}:request_device_status"
    assert entity.entity_category is er.EntityCategory.DIAGNOSTIC
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )
    (downlink,) = mock_connection.downlinks.values()
    assert downlink.dev_eui == descriptor.dev_eui
    assert downlink.f_port == 2
    assert downlink.data == b"\x26\x01"
    assert downlink.confirmed is False
    assert hass.states.get("sensor.garden_firmware_version").state == "unknown"
    await hass.config_entries.async_unload(config_entry.entry_id)


@pytest.mark.usefixtures("connection_entry")
@pytest.mark.parametrize(
    ("error", "message"),
    [
        (DownlinkError("Read-only key"), "Unable to send"),
        (ConnectionUnavailable("Disconnected"), "Unable to send"),
        (TimeoutError(), "Timed out queueing"),
    ],
)
async def test_request_failure(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_connection: MockConnection,
    error: Exception,
    message: str,
) -> None:
    """Surface failed writes while keeping monitoring available."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    with (
        patch.object(mock_connection, "async_send_downlink", side_effect=error),
        pytest.raises(HomeAssistantError, match=message),
    ):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.garden_request_device_status"},
            blocking=True,
        )
    assert hass.states.get("sensor.garden_battery").state == "unknown"
    assert hass.states.get("binary_sensor.garden_opening").state == "unknown"
    await hass.config_entries.async_unload(config_entry.entry_id)


@pytest.mark.usefixtures("connection_entry")
async def test_request_deadline(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_connection: MockConnection,
) -> None:
    """Bound a stalled enqueue operation, not just acknowledgement waiting."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    async def stalled_send(*_args: object) -> str:
        await Event().wait()
        return "queued"

    with (
        patch.object(mock_connection, "async_send_downlink", side_effect=stalled_send),
        patch(
            "custom_components.dragino_lorawan.button.timeout",
            return_value=timeout(0),
        ) as deadline,
        pytest.raises(HomeAssistantError, match="Timed out queueing"),
    ):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.garden_request_device_status"},
            blocking=True,
        )
    deadline.assert_called_once_with(30)
    await hass.config_entries.async_unload(config_entry.entry_id)
