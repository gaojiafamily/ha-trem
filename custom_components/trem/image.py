"""Image for the Taiwan Real-time Earthquake Monitoring."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from io import BytesIO
import json
import logging
import os
import re
from typing import Any

from PIL import Image

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ATTRIBUTION, CONF_REGION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_ID,
    ATTRIBUTION,
    CONF_DRAW_MAP,
    DEFAULT_NAME,
    DOMAIN,
    MANUFACTURER,
    PLAN_NAME,
    TREM_COORDINATOR,
    TREM_NAME,
)
from .earthquake.eew import EEW
from .update_coordinator import tremUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config: ConfigEntry, async_add_devices: Callable
) -> None:
    """Set up the TREM Image from config."""

    draw_map: bool = _get_config_value(config, CONF_DRAW_MAP, False)

    if draw_map:
        domain_data: dict = hass.data[DOMAIN][config.entry_id]
        name: str = domain_data[TREM_NAME]
        coordinator: tremUpdateCoordinator = domain_data[TREM_COORDINATOR]

        device = earthquakeImage(hass, name, config, coordinator)
        async_add_devices([device], update_before_add=True)


class earthquakeImage(ImageEntity):
    """Defines a TREM image entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        config_entry: ConfigEntry,
        coordinator: tremUpdateCoordinator,
    ) -> None:
        """Initialize the image."""

        super().__init__(hass)

        self._coordinator = coordinator
        self._hass = hass

        self._first_draw: bool = False
        self._region: int = _get_config_value(config_entry, CONF_REGION)

        attr_name = f"{DEFAULT_NAME} {self._region} Isoseismal Map"
        self._attr_name = attr_name
        self._attr_unique_id = re.sub(r"\s+|@", "_", attr_name.lower())
        self._attr_content_type: str = "image/png"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=name,
            manufacturer=MANUFACTURER,
            model=PLAN_NAME[self._coordinator.plan],
        )

        self._image: BytesIO = BytesIO()
        self._mapSerial: dict = {
            "earthquake": "",
            "intensity": "",
        }
        self._attributes = {}
        self._attr_value = {}

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""

        self.async_on_remove(
            self._coordinator.async_add_listener(self._update_callback)
        )

    async def async_image(self) -> bytes | None:
        """Return bytes of image."""

        return self._image.getvalue()

    @callback
    def _update_callback(self):
        """Handle updated data from the coordinator."""

        eew = self._coordinator.eew
        intensity = self._coordinator.intensity
        image: BytesIO | None = self._draw(eew, intensity)

        if image is None:
            return

        self._image = image
        self._attr_value[ATTR_ID] = json.dumps(self._mapSerial)
        self._attr_image_last_updated = dt_util.utcnow()

        self.async_write_ha_state()

    def _draw(
        self, eew: EEW | None = None, intensity: dict | None = None
    ) -> BytesIO | None:
        """Draw the earthquake map."""

        image: BytesIO | None = None

        currentSerial = self._attr_value.get(ATTR_ID, "")
        if currentSerial == "":
            if not self._first_draw:
                image = BytesIO()
                self._first_draw = True

                directory = os.path.dirname(os.path.realpath(__file__))
                image_path = os.path.join(directory, "asset/default.png")

                default_img = Image.open(image_path, mode="r")
                default_img.save(image, format="PNG")
        elif isinstance(eew, EEW):
            tmp_intensity: dict = {}

            # Earthquake serial
            tmpSerial: dict = {"earthquake": f"{eew.id} (Serial: {eew.serial})"}

            # Intensity serial and get area intensity
            intAuthor = intensity.get("author", False)
            if intAuthor:
                intDrawID = intensity.get("id", "")
                intSerial = intensity.get("serial", "0")
                tmpSerial["intensity"] = f"{intAuthor}-{intDrawID} (Serial {intSerial})"

                intensityArea = intensity.get("area", {})
                for k in intensityArea:
                    for v in intensityArea[k]:
                        tmp_intensity[v] = k  # noqa: SLF001

            earthquake = eew.earthquake
            tmp_intensity[self._region] = earthquake._expected_intensity.get(  # noqa: SLF001
                self._region
            )

            if currentSerial != json.dumps(tmpSerial):
                earthquake.map.draw()

            waveDraw = earthquake.time + (600 * 1000) > datetime.now()
            waveSec = (datetime.now() - earthquake.time).total_seconds()
            if waveDraw and waveSec > 0:
                earthquake.map.draw_wave(time=waveSec)

            self._mapSerial = tmpSerial
            image = earthquake.map.save()

        return image

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""

        self._attributes[ATTR_ATTRIBUTION] = ATTRIBUTION
        for k in self._attr_value:
            self._attributes[k] = self._attr_value[k]
        return self._attributes


def _get_config_value(config_entry: ConfigEntry, key: str, default: Any | None = None):
    if config_entry.options:
        return config_entry.options.get(key, default)
    return config_entry.data.get(key, default)
