"""Dragino sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from homeassistant.components.lorawan import LoRaWANEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    LIGHT_LUX,
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DraginoConfigEntry
from ._vendor.dragino_lorawan import (
    CPL03LB,
    LDS02,
    LHT65,
    LT22222,
    LWL02,
    DraginoDevice,
)
from ._vendor.dragino_lorawan.contact import ContactDevice
from .coordinator import DraginoCoordinator
from .entity import DraginoEntity, async_setup_entities

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class DraginoSensorDescription(SensorEntityDescription):
    """Describe a measurement exposed by a model."""

    channels: tuple[int, ...]
    value_fn: Callable[[LT22222, int], float | int | None]


SENSORS = (
    DraginoSensorDescription(
        key="voltage",
        channels=(1, 2),
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device, channel: device.voltages[channel],
    ),
    DraginoSensorDescription(
        key="current",
        channels=(1, 2),
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device, channel: device.currents[channel],
    ),
    DraginoSensorDescription(
        key="digital_count",
        channels=(1, 2),
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device, channel: device.digital_counts[channel],
    ),
    DraginoSensorDescription(
        key="voltage_count",
        channels=(1,),
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device, channel: device.voltage_count,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DraginoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create measurement entities for the collection."""
    async_setup_entities(
        hass,
        entry,
        async_add_entities,
        lambda coordinator: [
            DraginoSensor(coordinator, description, channel)
            for description in SENSORS
            for channel in description.channels
        ],
    )

    @callback
    def added(coordinator: DraginoCoordinator) -> None:
        if isinstance(coordinator.data, (LHT65, LDS02, LWL02, CPL03LB)):
            async_add_entities(
                [
                    DraginoBattery(
                        coordinator,
                        SensorEntityDescription(
                            key="battery",
                            device_class=SensorDeviceClass.BATTERY,
                            native_unit_of_measurement=PERCENTAGE,
                            state_class=SensorStateClass.MEASUREMENT,
                            entity_category=EntityCategory.DIAGNOSTIC,
                        ),
                    )
                ]
            )
        if isinstance(coordinator.data, LHT65):
            async_add_entities(
                LHT65Sensor(coordinator, description) for description in LHT65_SENSORS
            )

        elif isinstance(coordinator.data, (LDS02, LWL02)):
            async_add_entities(
                ContactSensor(coordinator, description)
                for description in CONTACT_SENSORS
            )
        elif isinstance(coordinator.data, CPL03LB):
            async_add_entities(
                CPL03LBSensor(coordinator, description)
                for description in CPL03LB_SENSORS
            )

    entry.async_on_unload(entry.runtime_data.subscribe_coordinator_added(added))


class DraginoSensor(DraginoEntity, SensorEntity):
    """Represent an LT-22222-L measurement."""

    entity_description: DraginoSensorDescription

    def __init__(
        self,
        coordinator: DraginoCoordinator,
        description: DraginoSensorDescription,
        channel: int,
    ) -> None:
        """Bind a measurement description and channel."""
        super().__init__(coordinator, description, channel)

    @property
    @override
    def native_value(self) -> float | int | None:
        return self.entity_description.value_fn(self.device, self.channel)


@dataclass(frozen=True, kw_only=True)
class LHT65SensorDescription(SensorEntityDescription):
    """Describe a value supplied by the LHT65 model."""

    value_fn: Callable[[LHT65], float | int | None]


LHT65_SENSORS = (
    LHT65SensorDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.temperature,
    ),
    LHT65SensorDescription(
        key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.humidity,
    ),
    LHT65SensorDescription(
        key="battery_voltage",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.battery_voltage,
    ),
    LHT65SensorDescription(
        key="external_temperature",
        translation_key="external_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.external_temperature,
    ),
    LHT65SensorDescription(
        key="illuminance",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit_of_measurement=LIGHT_LUX,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.illuminance,
    ),
    LHT65SensorDescription(
        key="external_voltage",
        translation_key="external_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.external_voltage,
    ),
    LHT65SensorDescription(
        key="external_count",
        translation_key="external_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.external_count,
    ),
)


class LHT65Sensor(LoRaWANEntity[DraginoDevice], SensorEntity):
    """Represent an LHT65 measurement."""

    coordinator: DraginoCoordinator
    entity_description: LHT65SensorDescription

    @property
    @override
    def device_info(self) -> DeviceInfo:
        return self.coordinator.device_info

    @property
    @override
    def native_value(self) -> float | int | None:
        device = self.device
        if TYPE_CHECKING:
            assert isinstance(device, LHT65)
        return self.entity_description.value_fn(device)


@dataclass(frozen=True, kw_only=True)
class ContactSensorDescription(SensorEntityDescription):
    """Describe a door or leak measurement."""

    value_fn: Callable[[ContactDevice], float | int | None]


CONTACT_SENSORS = (
    ContactSensorDescription(
        key="battery_voltage",
        entity_registry_enabled_default=False,
        translation_key="battery_voltage",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.battery_voltage,
    ),
    ContactSensorDescription(
        key="event_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        translation_key="event_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device: device.event_count,
    ),
    ContactSensorDescription(
        key="last_duration",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        translation_key="last_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda device: device.last_duration,
    ),
)


class ContactSensor(LoRaWANEntity[DraginoDevice], SensorEntity):
    """Represent a door or leak sensor measurement."""

    coordinator: DraginoCoordinator
    entity_description: ContactSensorDescription

    @property
    @override
    def device_info(self) -> DeviceInfo:
        return self.coordinator.device_info

    @property
    @override
    def native_value(self) -> float | int | None:
        device = self.device
        if TYPE_CHECKING:
            assert isinstance(device, ContactDevice)
        return self.entity_description.value_fn(device)


@dataclass(frozen=True, kw_only=True)
class CPL03LBSensorDescription(SensorEntityDescription):
    """Describe a pulse-contact measurement."""

    value_fn: Callable[[CPL03LB], str | float | int | None]


CPL03LB_SENSORS = (
    CPL03LBSensorDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.firmware_version,
    ),
    CPL03LBSensorDescription(
        key="work_mode",
        translation_key="cpl03lb_work_mode",
        device_class=SensorDeviceClass.ENUM,
        options=["cpl01", "cpl03", "interrupt"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.work_mode,
    ),
    CPL03LBSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.battery_voltage,
    ),
    CPL03LBSensorDescription(
        key="last_duration",
        translation_key="last_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.last_duration,
    ),
    *(
        CPL03LBSensorDescription(
            key=key,
            translation_key=key,
            state_class=SensorStateClass.TOTAL_INCREASING,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=value_fn,
        )
        for key, value_fn in (
            ("pulse_count", lambda device: device.pulse_count),
            ("pa8_count", lambda device: device.pa8_count),
            ("pa4_count", lambda device: device.pa4_count),
            ("pb15_count", lambda device: device.pb15_count),
        )
    ),
)


class CPL03LBSensor(LoRaWANEntity[CPL03LB], SensorEntity):
    """Represent a CPL03-LB measurement."""

    coordinator: DraginoCoordinator
    entity_description: CPL03LBSensorDescription

    @property
    @override
    def device_info(self) -> DeviceInfo:
        return self.coordinator.device_info

    @property
    @override
    def native_value(self) -> str | float | int | None:
        return self.entity_description.value_fn(self.device)

    @property
    @override
    def state_class(self) -> SensorStateClass | None:
        """Do not treat interval pulse counts (CMOD=PART) as cumulative totals."""
        if (
            self.entity_description.state_class == SensorStateClass.TOTAL_INCREASING
            and self.device.counts_are_cumulative is not True
        ):
            return None
        return self.entity_description.state_class


class DraginoBattery(LoRaWANEntity[DraginoDevice], SensorEntity):
    """Represent the device battery percentage."""

    coordinator: DraginoCoordinator

    @property
    @override
    def device_info(self) -> DeviceInfo:
        return self.coordinator.device_info

    @property
    @override
    def native_value(self) -> float | None:
        if (battery_level := self.device.battery_level) is not None:
            return battery_level
        if isinstance(self.device, (LDS02, LWL02)):
            return self.device.battery_percentage
        return None
