"""Sensor for the Taiwan Real-time Earthquake Monitoring."""

from __future__ import annotations


from .earthquake.eew import EEW
from .earthquake.model import calculate_expected_intensity_and_travel_time

import logging
import random
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorEntity,
)
from homeassistant.const import ATTR_ATTRIBUTION, CONF_NAME, CONF_REGION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from .const import (
    ATTRIBUTION,
    ATTR_ID,
    ATTR_AUTHOR,
    ATTR_LNG,
    ATTR_LAT,
    ATTR_DEPTH,
    ATTR_MAG,
    ATTR_LOC,
    ATTR_TIME,
    ATTR_EST,
    ATTR_LIST,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    HA_USER_AGENT,
    BASE_URLS,
    DEFAULT_ICON,
)
from requests import request


_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = DEFAULT_SCAN_INTERVAL
REQUIREMENTS = ["geopandas", "matplotlib"]


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_REGION): cv.string,
    }
)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""
    add_entities([TremSensor(name=config[CONF_NAME], region=config[CONF_REGION])], True)


class TremSensor(SensorEntity):
    def __init__(self, name: str, region: str):
        station, base_url = random.choice(list(BASE_URLS.items()))
        _LOGGER.info(f"Fetching data from HTTP API ({station})")
        self._name = name
        self._region = region
        self._state = None
        self._attr_value = {}
        self._base_url = f"{base_url}/api/v1/eq/eew?type=cwa"

    def update(self):
        try:
            header = {"Accept": "application/json", "User-Agent": HA_USER_AGENT}
            resp = request(
                "GET",
                self._base_url,
                headers=header,
            )
            resp.encoding = "utf-8"
            if resp.status_code == 200:
                earthquakeData = resp.json()
                if not earthquakeData == []:
                    eew = EEW.from_dict(earthquakeData[0])
                    _LOGGER.info(
                        "EEW alert updated\n"
                        "--------------------------------\n"
                        f"       ID: {eew.id} (Serial {eew.serial})\n"
                        f" Location: {eew.earthquake.location.display_name}({eew.earthquake.lon:.2f}, {eew.earthquake.lat:.2f})\n"
                        f"Magnitude: {eew.earthquake.mag}\n"
                        f"    Depth: {eew.earthquake.depth}km\n"
                        f"     Time: {eew.earthquake.time.strftime('%Y/%m/%d %H:%M:%S')}\n"
                        "--------------------------------"
                    )
                    intensities = calculate_expected_intensity_and_travel_time(
                        eew.earthquake
                    )
                    self._attr_value[ATTR_AUTHOR] = eew.author
                    self._attr_value[ATTR_ID] = f"{eew.id} (Serial {eew.serial})"
                    self._attr_value[ATTR_LOC] = (
                        f"{eew.earthquake.location.display_name}({eew.earthquake.lon:.2f}, {eew.earthquake.lat:.2f})"
                    )
                    self._attr_value[ATTR_LAT] = f"{eew.earthquake.lat:.2f}"
                    self._attr_value[ATTR_LNG] = f"{eew.earthquake.lon:.2f}"
                    self._attr_value[ATTR_MAG] = eew.earthquake.mag
                    self._attr_value[ATTR_DEPTH] = f"{eew.earthquake.depth}KM"
                    self._attr_value[ATTR_TIME] = (
                        f"{eew.earthquake.time.strftime('%Y/%m/%d %H:%M:%S')}"
                    )
                    self._attr_value[ATTR_EST] = intensities[
                        self._region
                    ].distance.s_left_time()
                    self._state = intensities[self._region].intensity.value
                else:
                    self._attr_value = {}
                    for i in ATTR_LIST:
                        self._attr_value[i] = ""
                    self._state = 0
            else:
                _LOGGER.warning(
                    f"Unable to get data from HTTP API ({resp.status_code})"
                )
        except Exception as ex:
            _LOGGER.debug("Unable to get data from HTTP API (%s)", repr(ex))

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def icon(self):
        return DEFAULT_ICON

    @property
    def unique_id(self):
        alias = self._name.replace(" ", "_")
        return f"trem_{alias}"

    @property
    def extra_state_attributes(self):
        self._attributes = {}
        self._attributes[ATTR_ATTRIBUTION] = ATTRIBUTION
        for k, _ in self._attr_value.items():
            self._attributes[k] = self._attr_value[k]
        return self._attributes
