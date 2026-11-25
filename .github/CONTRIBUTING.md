# Contributing

Run commands from the repository root. Home Assistant does not run natively on Windows;
use Linux or WSL.

## Development

The device library is bundled under `custom_components/dragino_lorawan/_vendor`.
It uses the shared LoRaWAN dependency provided by Home Assistant.

```sh
uv sync --group dev
uv run python script/prepare_tests.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The development environment pins Core and its test helpers to the same revision.

## Tests

Tests use Home Assistant's official pytest helpers and an in-memory connection.
They cover discovery, decoded readings, entity identity, connection loss,
reconnection, and removal, plus output commands and errors.
Payload tests use codec examples, including the ChirpStack LDS02 and LWL02 fixtures.
LT-22222-L commands were also exercised against a simulated ChirpStack radio during the
original PoC.

## Home Assistant compatibility

The **CI** workflow runs on pushes, pull requests, weekly, and manually. It tests:

- **Pinned:** the Core revision pinned in `pyproject.toml` and `uv.lock`.
- **Dev:** the current Home Assistant `dev` branch.

It also validates the integration with hassfest.

## References

Payload references: [Dragino TTN codecs](https://github.com/TheThingsNetwork/lorawan-devices/tree/master/vendor/dragino).

LDS02 and LWL02 profiles were identified from
[LoRaWANDeviceProfiles](https://github.com/BenAhrdt/LoRaWANDeviceProfiles/tree/main/DeviceProfiles/Dragino)
and checked against the
[ChirpStack catalog](https://github.com/chirpstack/chirpstack-device-profiles/tree/master/vendors/dragino).
