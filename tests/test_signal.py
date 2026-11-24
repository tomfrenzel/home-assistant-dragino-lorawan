"""Tests for uplink link quality."""

from datetime import UTC, datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from lorawan_connection import DeviceDescriptor, GatewayReception, UplinkEvent
from lorawan_connection.mock import MockConnection
import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.dragino_lorawan._vendor.dragino_lorawan import (
    CPL03LB,
    LDS02,
    LHT65,
    LT22222,
    LWL02,
)

RSSI = "sensor.garden_signal_strength"
SNR = "sensor.garden_signal_to_noise_ratio"


@pytest.fixture(params=[LT22222, LHT65, LDS02, LWL02, CPL03LB])
def descriptor(request) -> DeviceDescriptor:
    """Describe each supported model."""
    brand, model = request.param.identifiers["tts"]
    return DeviceDescriptor(
        network_id="network",
        dev_eui="0201010101010101",
        name="Garden",
        stack="tts",
        brand_id=brand,
        model_id=model,
        application_id="app",
        profile_id="profile",
    )


def _uplink(
    descriptor: DeviceDescriptor,
    received_at: datetime,
    receptions: tuple[GatewayReception, ...],
) -> UplinkEvent:
    # The port carries no reading for any model, so only link quality changes.
    return UplinkEvent(
        descriptor=descriptor,
        received_at=received_at,
        f_port=99,
        data=b"\x00",
        receptions=receptions,
    )


@pytest.mark.usefixtures("connection_entry", "entity_registry_enabled_by_default")
async def test_signal_quality(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_connection: MockConnection,
    descriptor: DeviceDescriptor,
) -> None:
    """Report the strongest gateway of the latest uplink on any port."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(RSSI).state == "unknown"
    assert hass.states.get(SNR).state == "unknown"
    now = datetime.now(UTC)
    mock_connection.emit(
        _uplink(
            descriptor,
            now,
            (
                GatewayReception("far", rssi=-110, snr=-5),
                GatewayReception("near", rssi=-80, snr=7.5),
                GatewayReception("unmeasured"),
            ),
        )
    )
    await hass.async_block_till_done()
    assert hass.states.get(RSSI).state == "-80"
    assert hass.states.get(SNR).state == "7.5"
    assert hass.states.get(RSSI).attributes["unit_of_measurement"] == "dBm"
    assert hass.states.get(SNR).attributes["unit_of_measurement"] == "dB"

    for event in (
        # A delayed uplink must not replace newer link quality.
        _uplink(
            descriptor, now - timedelta(seconds=1), (GatewayReception("x", -60, 9),)
        ),
        # An uplink without gateway metadata keeps the last known values.
        _uplink(descriptor, now + timedelta(seconds=1), ()),
    ):
        mock_connection.emit(event)
        await hass.async_block_till_done()
        assert hass.states.get(RSSI).state == "-80"
        assert hass.states.get(SNR).state == "7.5"

    mock_connection.emit(
        _uplink(
            descriptor,
            now + timedelta(seconds=2),
            (GatewayReception("x", rssi=-95, snr=None),),
        )
    )
    await hass.async_block_till_done()
    assert hass.states.get(RSSI).state == "-95"
    assert hass.states.get(SNR).state == "unknown"
    await hass.config_entries.async_unload(config_entry.entry_id)


@pytest.mark.parametrize("descriptor", [LT22222], indirect=True)
@pytest.mark.usefixtures("connection_entry")
async def test_signal_quality_disabled_by_default(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Keep link-quality diagnostics out of the way until enabled."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    for entity_id, key in ((RSSI, "rssi"), (SNR, "snr")):
        entity = registry.async_get(entity_id)
        assert entity.unique_id == "network:0201010101010101:" + key
        assert entity.entity_category is er.EntityCategory.DIAGNOSTIC
        assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    await hass.config_entries.async_unload(config_entry.entry_id)
