"""Sensor for the Taiwan Real-time Earthquake Monitoring."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ATTRIBUTION, CONF_EMAIL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    ATTRIBUTION,
    DOMAIN,
    MANUFACTURER,
    PLAN_NAME,
    TREM_COORDINATOR,
    TREM_NAME,
)
from .update_coordinator import tremUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=1)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_devices: Callable
) -> None:
    """Set up the TREM binary sensor from config."""

    domain_data: dict = hass.data[DOMAIN][config_entry.entry_id]
    name: str = domain_data[TREM_NAME]
    coordinator: tremUpdateCoordinator = domain_data[TREM_COORDINATOR]

    not_membership = _get_config_value(config_entry, CONF_EMAIL, False) is False
    if not_membership:
        return

    rts_device = rtsBinarySensor(hass, name, config_entry, coordinator)
    async_add_devices(
        [
            rts_device,
        ],
        update_before_add=True,
    )


class rtsBinarySensor(BinarySensorEntity):
    """Defines a rts sensor entity."""

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

        self._attr_name = "RTS Notification"
        self._attr_unique_id = "rts_notification"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=name,
            manufacturer=MANUFACTURER,
            model=PLAN_NAME[self._coordinator.plan],
        )

        self._state: bool = False
        self._attributes: dict = {}
        self._attr_value: dict = {}

    def update(self):
        """Schedule a custom update via the common entity update service."""

        self._attributes = {}

        rtsData = self._coordinator.rtsData
        rts: list = rtsData.get("int", [])
        if len(rts) > 0:
            for k in rts:
                self._attr_value[k["code"]] = k["i"]

            self._state = True
            self._attr_value = rtsData

            return self

        self._attr_value = {}
        self._state = False

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
    def is_on(self) -> bool:
        """Return the state of the sensor."""

        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""

        return None

    @property
    def device_class(self):
        """Return the device class."""

        return BinarySensorDeviceClass.VIBRATION

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
