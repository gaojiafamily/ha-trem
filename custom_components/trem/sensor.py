"""Sensor for the Taiwan Real-time Earthquake Monitoring."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ATTRIBUTION, CONF_EMAIL, CONF_REGION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    ATTR_AUTHOR,
    ATTR_CODE,
    ATTR_DEPTH,
    ATTR_EST,
    ATTR_ID,
    ATTR_INT,
    ATTR_LAT,
    ATTR_LNG,
    ATTR_LOC,
    ATTR_MAG,
    ATTR_NODE,
    ATTR_OFFSET,
    ATTR_PROTOCOL,
    ATTR_TIME,
    ATTRIBUTION,
    CONF_DRAW_MAP,
    CONF_PRESERVE_DATA,
    CONNECTION_MSG,
    DEFAULT_ICON,
    DEFAULT_NAME,
    DOMAIN,
    EARTHQUAKE_ATTR,
    EARTHQUAKE_ICON,
    MANUFACTURER,
    PLAN_NAME,
    TREM_COORDINATOR,
    TREM_NAME,
    TSUNAMI_ATTR,
    TSUNAMI_ICON,
)
from .earthquake.eew import EEW, EarthquakeData
from .earthquake.location import REGIONS
from .update_coordinator import tremUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=1)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_devices: Callable
) -> None:
    """Set up the TREM sensor from config."""

    domain_data: dict = hass.data[DOMAIN][config_entry.entry_id]
    name: str = domain_data[TREM_NAME]
    coordinator: tremUpdateCoordinator = domain_data[TREM_COORDINATOR]

    earthquake_device = earthquakeSensor(hass, name, config_entry, coordinator)

    not_membership = _get_config_value(config_entry, CONF_EMAIL, False) is False
    if not_membership:
        async_add_devices(
            [earthquake_device],
            update_before_add=True,
        )
    else:
        tsunami_device = tsunamiSensor(hass, name, config_entry, coordinator)
        async_add_devices(
            [
                earthquake_device,
                tsunami_device,
            ],
            update_before_add=True,
        )


class earthquakeSensor(SensorEntity):
    """Defines a earthquake sensor entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        config_entry: ConfigEntry,
        coordinator: tremUpdateCoordinator,
    ) -> None:
        """Initialize the sensor."""

        self._coordinator = coordinator
        self._hass = hass
        self._name = name

        self.simulator: dict | None = None
        self.simulatorTime: datetime | None = None

        self._region: int = _get_config_value(config_entry, CONF_REGION)
        self._preserve_data: bool = _get_config_value(
            config_entry, CONF_PRESERVE_DATA, False
        )
        self._draw_map: bool = _get_config_value(config_entry, CONF_DRAW_MAP, False)

        attr_name = f"{DEFAULT_NAME} {self._region} Notification"
        self._attr_name = attr_name
        self._attr_unique_id = re.sub(r"\s+|@", "_", attr_name.lower())
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=self._name,
            manufacturer=MANUFACTURER,
            model=PLAN_NAME[self._coordinator.plan],
        )

        self._attributes = {}
        self._attr_value = {}
        for i in EARTHQUAKE_ATTR:
            self._attr_value[i] = ""
        self._icon = DEFAULT_ICON
        self._state = ""

    def update(self):
        """Schedule a custom update via the common entity update service."""

        eew: EEW | None = None
        data = self._coordinator.earthquakeData

        if isinstance(data, list) and len(data) > 0:
            self.simulator = None

            eew = EEW.from_dict(data[0])
        elif isinstance(self.simulator, dict):
            if self.simulatorTime is None:
                self.simulatorTime = datetime.now()

            eew = EEW.from_dict(self.simulator)

            time = datetime.now() - self.simulatorTime
            if time.total_seconds() >= 240:
                self.simulator = None

        if isinstance(eew, EEW):
            earthquakeSerial = f"{eew.id} (Serial {eew.serial})"
            if self._coordinator.eew is None:
                self._coordinator.eew = eew
                old_earthquakeSerial = ""
            else:
                old_eew = self._coordinator.eew
                old_earthquakeSerial = f"{old_eew.id} (Serial {old_eew.serial})"

            earthquake = eew.earthquake
            earthquakeForecast = EarthquakeData.calc_expected_intensity(
                earthquake, [REGIONS[self._region]]
            ).get(self._region)

            if earthquakeSerial != old_earthquakeSerial:
                self._coordinator.eew = eew

                tz_TW = timezone(timedelta(hours=8))
                earthquakeTime = earthquake.time.astimezone(tz_TW).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                earthquakeProvider = (
                    f"{eew.provider.display_name} ({eew.provider.name})"
                )
                earthquakeLocation = f"{earthquake.location.display_name} ({earthquake.lon:.2f}, {earthquake.lat:.2f})"

                intensity = earthquakeForecast.intensity
                self._attr_value[ATTR_INT] = intensity.value
                self._attr_value[ATTR_AUTHOR] = earthquakeProvider
                self._attr_value[ATTR_ID] = earthquakeSerial
                self._attr_value[ATTR_LOC] = earthquakeLocation
                self._attr_value[ATTR_LNG] = f"{earthquake.lon:.2f}"
                self._attr_value[ATTR_LAT] = f"{earthquake.lat:.2f}"
                self._attr_value[ATTR_MAG] = earthquake.mag
                self._attr_value[ATTR_DEPTH] = earthquake.depth
                self._attr_value[ATTR_TIME] = earthquakeTime
                self._state = intensity
                self._icon = EARTHQUAKE_ICON[intensity.value]

            earthquakeEst = int(
                earthquakeForecast.distance.s_left_time().total_seconds()
            )
            self._attr_value[ATTR_EST] = earthquakeEst if earthquakeEst > 0 else 0
        else:
            self._attr_value[ATTR_EST] = 0

        # Always display
        self._attr_value[ATTR_CODE] = self._name
        if _LOGGER.isEnabledFor(logging.DEBUG):
            timestamp = datetime.timestamp(datetime.now()) * 1000
            offsetTime: float = (timestamp - self._coordinator.recvTime) / 1000

            self._attr_value[ATTR_NODE] = self._coordinator.station
            self._attr_value[ATTR_OFFSET] = (
                f"{offsetTime:.2f}s" if offsetTime < 2 else "2s+"
            )
            self._attr_value[ATTR_PROTOCOL] = CONNECTION_MSG[self._coordinator.status]

        if self._preserve_data:
            return self

        # Clear earthquake data
        for i in EARTHQUAKE_ATTR:
            self._attr_value[i] = ""
        self._icon = DEFAULT_ICON
        self._state = ""

        return self

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""

        self.async_on_remove(
            self._coordinator.async_add_listener(self._update_callback)
        )

    @property
    def available(self):
        """Return True if entity is available."""

        if self._coordinator.retry > 1:
            return self._coordinator.last_update_success

        return True

    @property
    def state(self) -> str:
        """Return the state of the sensor."""

        return self._state

    @property
    def icon(self) -> str:
        """Icon to use in the frontend, if any."""

        return self._icon

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""

        self._attributes[ATTR_ATTRIBUTION] = ATTRIBUTION
        for k in self._attr_value:
            self._attributes[k] = self._attr_value[k]
        return self._attributes

    @callback
    def _update_callback(self) -> None:
        """Handle updated data from the coordinator."""

        self.async_write_ha_state()


class tsunamiSensor(SensorEntity):
    """Defines a tsunami sensor entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        config: ConfigEntry,
        coordinator: tremUpdateCoordinator,
    ) -> None:
        """Initialize the sensor."""

        self._coordinator = coordinator
        self._hass = hass

        self._tsunami: dict | None = None

        self._preserve_data: bool = _get_config_value(config, CONF_PRESERVE_DATA, False)

        self._attr_name = "Tsunami Notification"
        self._attr_unique_id = "tsunami_notification"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config.entry_id)},
            name=name,
            manufacturer=MANUFACTURER,
            model=PLAN_NAME[self._coordinator.plan],
        )

        self._state = ""
        self._attributes = {}
        self._attr_value = {}
        for i in TSUNAMI_ATTR:
            self._attr_value[i] = ""

    def update(self):
        """Schedule a custom update via the common entity update service."""

        tsunami = self._coordinator.tsunamiData
        if tsunami.get("id", False):
            if self._tsunami is None:
                self._tsunami = tsunami
                old_tsunamiSerial = ""
            else:
                old_tsunami = self._tsunami
                old_tsunamiSerial = (
                    f"{old_tsunami["id"]} (Serial {old_tsunami["serial"]})"
                )

            tsunamiSerial = f"{tsunami["id"]} (Serial {tsunami["serial"]})"
            if tsunamiSerial != old_tsunamiSerial:
                self._tsunami = tsunami

                self._attr_value[ATTR_AUTHOR] = tsunami.get("author", "MISSING")
                self._attr_value[ATTR_ID] = tsunamiSerial
                self._state = tsunami.get("content", "MISSING")

        if self._preserve_data:
            return self

        # Clear tsunami data
        for i in TSUNAMI_ATTR:
            self._attr_value[i] = ""
        self._state = ""

        return self

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""

        self.async_on_remove(
            self._coordinator.async_add_listener(self._update_callback)
        )

    @property
    def available(self):
        """Return True if entity is available."""

        if self._coordinator.retry > 1:
            return self._coordinator.last_update_success

        return True

    @property
    def state(self) -> str:
        """Return the state of the sensor."""

        return self._state

    @property
    def icon(self) -> str:
        """Icon to use in the frontend, if any."""

        return TSUNAMI_ICON

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""

        self._attributes[ATTR_ATTRIBUTION] = ATTRIBUTION
        for k in self._attr_value:
            self._attributes[k] = self._attr_value[k]
        return self._attributes

    @callback
    def _update_callback(self) -> None:
        """Handle updated data from the coordinator."""

        self.async_write_ha_state()


def _get_config_value(config_entry: ConfigEntry, key: str, default: Any | None = None):
    if config_entry.options:
        return config_entry.options.get(key, default)
    return config_entry.data.get(key, default)
