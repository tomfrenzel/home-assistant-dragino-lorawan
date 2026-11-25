[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tomfrenzel&repository=home-assistant-dragino-lorawan&category=integration)

# Dragino LoRaWAN

Use Dragino devices with Home Assistant's LoRaWAN connections.
Requires Home Assistant 2026.11.0b0 or newer, including 2026.11 beta releases.

## Maintenance

This integration started as Balloob's (@balloob) proof of concept. With his
agreement, maintenance has moved to
[tomfrenzel/home-assistant-dragino-lorawan](https://github.com/tomfrenzel/home-assistant-dragino-lorawan).
All new development will happen in this repository, not the original
balloobbot repository. Please submit issues and pull requests here.

## Install

1. Open the HACS link above and download the integration.
2. Restart Home Assistant.
3. Configure a connection supported by your device in the table below.
4. Add your device to the network server using its official catalog profile.
5. Open **Settings > Devices & services** and configure the discovered
   **Dragino LoRaWAN** integration. You can also select it under **Add integration**.

To install manually, copy `custom_components/dragino_lorawan` into your Home
Assistant `config/custom_components` directory and restart.

## Devices

| Model | Entities | Connections |
| --- | --- | --- |
| LT-22222-L | Two relays, two digital outputs, two digital inputs, voltage, current, and counters | ChirpStack and The Things Network / The Things Stack |
| LDS02 | Door state, open alarm, event count, last opening duration, battery percentage, and battery voltage | ChirpStack and The Things Network / The Things Stack |
| LWL02 | Water leak, event count, last leak duration, battery percentage, battery voltage, reporting interval, and Request reset | ChirpStack and The Things Network / The Things Stack |
| LHT65 | Temperature, humidity, battery percentage, battery voltage, and external probe readings | The Things Network / The Things Stack |
| CPL03-LB | Single contact and alarm, three pulse counters or three contact inputs, last event duration, battery percentage, battery voltage, firmware, work mode, and Request device status | ChirpStack and The Things Network / The Things Stack |

LT-22222-L input measurements depend on its reporting mode. LHT65 illuminance,
external voltage, and external counter entities are disabled by default; enable
the ones that match your attached probe.

Relay and digital-output commands wait up to 30 seconds for acknowledgement.
Their state changes when the device reports it. A timeout does not remove a
queued command from the network server.

For LWL02, **Reporting interval** sets the periodic keep-alive interval in seconds.
It shows the last value requested during this Home Assistant session, not a
setting read from the sensor. Leak-triggered reports remain enabled.
**Request reset** clears both the event count and last leak duration on the sensor.
The displayed readings change when the sensor reports them.

For CPL03-LB, single-contact mode reports its contact, alarm, pulse count, and last
event duration in **seconds** (open or closed, depending on the trigger setting).
Three-counter mode (`AT+MOD=2`, port 6) reports PA8, PA4, and PB15 pulse counts;
three-interrupt mode (`AT+MOD=3`, port 7) reports their contact levels instead.
Entities for all three modes are registered with stable IDs; changing modes
clears readings that the new mode does not report.
Pulse counts use cumulative statistics only in `CMOD=SUM`; interval counts
(`CMOD=PART`) are not treated as growing totals. History and configuration
responses do not replace live readings. People-counter mode (port 8) is not
supported.

**Request device status** queues `26 01` on port 2. A later port-5 reply supplies
the firmware version and battery voltage; it does not supply a battery percentage.
See the [CPL03-LB manual](https://docs.dragino.com/docs/LoRaWAN-End-Node/door-water-leak-contact-sensors/cpl03-lb/).

These controls queue a downlink and return without waiting for device acknowledgement.
The sensor receives it after a subsequent uplink. The connection's API key needs
downlink write permission. See [Dragino's downlink commands](https://wiki.dragino.com/docs/LoRaWAN-End-Node/door-water-leak-contact-sensors/lwl02/#44-downlink-payload).

Devices are matched by catalog identity. Renaming a custom profile to a supported
model does not make it discoverable. One integration entry handles matching
devices across all configured LoRaWAN connections.

Battery percentage is enabled by default. Battery voltage, event count, and
event duration are diagnostic entities disabled by default; enable them in the
entity settings if needed.

Every model also has disabled-by-default diagnostic **Signal strength** (RSSI)
and **Signal-to-noise ratio** (SNR) entities. They show the strongest gateway
reception of the latest uplink, for any payload port, when the LoRaWAN
connection reports gateway metadata.

Battery percentage uses LoRaWAN device-status reports when available. LDS02 and
LWL02 otherwise estimate it from uplink voltage, following the
[device profile decoders](https://github.com/BenAhrdt/LoRaWANDeviceProfiles/tree/main/DeviceProfiles/Dragino):
2.1 V is 0% and 3.1 V is 100%, with values clamped to that range. LHT65 and CPL03-LB battery
percentage remains unknown until a LoRaWAN
device-status report supplies it.

Readings remain unknown until an uplink or status report supplies them.

Brand images are included in the integration's `brand` directory.

## Development

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for the development setup, tests, and payload references.
