"""The Taiwan Real-Time Earthquake Monitoring integration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REGION,
    MAJOR_VERSION,
    MINOR_VERSION,
)
from homeassistant.core import HomeAssistant

from .const import (
    CLIENT_NAME,
    CONF_NODE,
    CONF_PASS,
    DOMAIN,
    HTTPS_API_COORDINATOR_UPDATE_INTERVAL,
    MIN_HA_MAJ_VER,
    MIN_HA_MIN_VER,
    PLATFORMS,
    STARTUP,
    TREM_COORDINATOR,
    TREM_NAME,
    UPDATE_LISTENER,
    WEBSOCKET_COORDINATOR_UPDATE_INTERVAL,
    __min_ha_version__,
    __version__,
)
from .services import register_services
from .update_coordinator import tremUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def getRegionCode() -> dict:
    """Get the region options."""

    directory = os.path.dirname(os.path.realpath(__file__))
    region_path = os.path.join(directory, "asset/region.json")
    with open(
        region_path,
        encoding="utf-8",
    ) as f:
        codes: dict = {}
        data: dict = json.load(f)
        for city, region in data.items():
            for town in region:
                area = region[town]["area"]
                if area not in codes:
                    codes[area] = f"===== {area} ====="
                codes[region[town]["code"]] = f"{city}{town}"
    return codes


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up a TREM integration from a config entry."""

    if not is_valid_ha_version():
        msg = (
            "This integration require at least HomeAssistant version "
            f" {__min_ha_version__}, you are running version {__version__}."
            " Please upgrade HomeAssistant to continue use this integration."
        )
        await _notify_message(hass, "inv_ha_version", CLIENT_NAME, msg)
        _LOGGER.warning(msg)
        return False

    node: str | dict = _get_config_value(config_entry, CONF_NODE, "")
    region: int = _get_config_value(config_entry, CONF_REGION, None)
    email: str | None = _get_config_value(config_entry, CONF_EMAIL, None)
    passwd: str | None = _get_config_value(config_entry, CONF_PASSWORD, None)
    codes = await getRegionCode()

    # migrate data (also after first setup) to options
    if config_entry.data:
        hass.config_entries.async_update_entry(
            config_entry, data={}, options=config_entry.data
        )

    if email is None:
        base_info = node
        update_interval = HTTPS_API_COORDINATOR_UPDATE_INTERVAL
    else:
        base_info = {
            CONF_EMAIL: email,
            CONF_PASS: passwd,
        }
        update_interval = WEBSOCKET_COORDINATOR_UPDATE_INTERVAL

    # Fetch initial data so we have data when entities subscribe
    hass.data.setdefault(DOMAIN, {})
    domain_data: dict = {}

    tremCoordinator = tremUpdateCoordinator(
        hass,
        base_info,
        region,
        update_interval,
    )
    domain_data = {
        TREM_COORDINATOR: tremCoordinator,
        TREM_NAME: codes[region],
    }

    await tremCoordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][config_entry.entry_id] = domain_data

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(config_entry, platform)
        )

    update_listener = config_entry.add_update_listener(async_update_options)
    hass.data[DOMAIN][config_entry.entry_id][UPDATE_LISTENER] = update_listener
    register_services(hass)

    _LOGGER.info(STARTUP)
    return True


async def async_update_options(hass: HomeAssistant, config_entry: ConfigEntry):
    """Handle options update."""

    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Unload a config entry."""

    _email = _get_config_value(config_entry, CONF_EMAIL, None)
    if _email is None:
        pass
    else:
        coordinator: tremUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id][
            TREM_COORDINATOR
        ]
        await coordinator.connection.close()

    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(config_entry, platform)
                for platform in PLATFORMS
            ]
        )
    )

    if unload_ok:
        update_listener = hass.data[DOMAIN][config_entry.entry_id][UPDATE_LISTENER]
        update_listener()
        hass.data[DOMAIN].pop(config_entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Reload a config entry."""

    await async_unload_entry(hass, config_entry)
    await async_setup_entry(hass, config_entry)


def is_min_ha_version(min_ha_major_ver: int, min_ha_minor_ver: int) -> bool:
    """Check if HA version at least a specific version."""

    return min_ha_major_ver < MAJOR_VERSION or (
        min_ha_major_ver == MAJOR_VERSION and min_ha_minor_ver <= MINOR_VERSION
    )


def is_valid_ha_version() -> bool:
    """Check if HA version is valid for this integration."""

    return is_min_ha_version(MIN_HA_MAJ_VER, MIN_HA_MIN_VER)


async def _notify_message(
    hass: HomeAssistant, notification_id: str, title: str, message: str
) -> None:
    """Notify user with persistent notification."""

    persistent_notification.async_create(
        hass, message, title, f"{DOMAIN}.{notification_id}"
    )


def _get_config_value(config_entry: ConfigEntry, key: str, default: Any | None = None):
    if config_entry.options:
        return config_entry.options.get(key, default)
    return config_entry.data.get(key, default)
