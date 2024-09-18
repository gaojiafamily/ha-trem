"""Service for the Taiwan Real-time Earthquake Monitoring."""

from __future__ import annotations

import json
import logging
import os

import voluptuous as vol

from homeassistant.components.image import ImageEntity
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import async_get_platforms

from .const import ATTR_EQDATA, ATTR_FILENAME, DOMAIN, TREM_COORDINATOR
from .sensor import earthquakeSensor
from .update_coordinator import tremUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


def register_services(hass: HomeAssistant) -> None:
    """Set up the TREM integration service."""

    async def save_image(service_call: ServiceCall) -> None:
        """Save the image to path."""

        entity_id = service_call.data[ATTR_ENTITY_ID]
        filepath = service_call.data[ATTR_FILENAME]

        if not hass.config.is_allowed_path(filepath):
            raise HomeAssistantError(
                f"Cannot write `{filepath}`, no access to path; `allowlist_external_dirs` may need to be adjusted in `configuration.yaml`"
            )

        platforms = async_get_platforms(hass, DOMAIN)

        if len(platforms) < 1:
            raise HomeAssistantError(f"Integration not found: {DOMAIN}")

        entity: ImageEntity | None = None

        for platform in platforms:
            entity_tmp: ImageEntity | None = platform.entities.get(entity_id, None)
            if entity_tmp is not None:
                entity = entity_tmp
                break

        if not entity:
            raise HomeAssistantError(
                f"Could not find entity {entity_id} from integration {DOMAIN}"
            )

        image = await entity.async_image()

        def _write_image(to_file: str, image_data: bytes) -> None:
            """Executor helper to write image."""
            os.makedirs(os.path.dirname(to_file), exist_ok=True)
            with open(to_file, "wb") as img_file:
                img_file.write(image_data)

        try:
            await hass.async_add_executor_job(_write_image, filepath, image)
        except OSError as err:
            _LOGGER.error("Can't write image to file: %s", err)

    async def simulator_eartkquake(service_call: ServiceCall) -> None:
        """Set up the earthquake simulator service."""

        entity_id: str | None = service_call.data[ATTR_ENTITY_ID]
        eartkquakeData: dict = service_call.data[ATTR_EQDATA]

        platforms = async_get_platforms(hass, DOMAIN)
        if len(platforms) < 1:
            raise HomeAssistantError(f"Integration not found: {DOMAIN}")

        entity: earthquakeSensor | None = None
        for platform in platforms:
            entity_tmp = platform.entities.get(entity_id, None)
            if entity_tmp is not None:
                entity = entity_tmp
                break
        if entity is None:
            raise HomeAssistantError(
                f"Could not find entity {entity_id} from integration {DOMAIN}"
            )

        _LOGGER.debug("Starting simulator earthquake")
        entity.simulator = json.loads(eartkquakeData)

    async def reconnect(service_call: ServiceCall) -> None:
        """Reconnect the service."""

        entity_id: str | None = service_call.data[ATTR_ENTITY_ID]

        platforms = async_get_platforms(hass, DOMAIN)
        if len(platforms) < 1:
            raise HomeAssistantError(f"Integration not found: {DOMAIN}")

        entry_id: str | None = None
        for platform in platforms:
            entity_tmp = platform.entities.get(entity_id, None)
            if entity_tmp is not None:
                entry_id = platform.config_entry.entry_id
                break
        if entry_id is None:
            raise HomeAssistantError(
                f"Could not find entity {entity_id} from integration {DOMAIN}"
            )

        domain_data: dict = hass.data[DOMAIN][entry_id]
        coordinator: tremUpdateCoordinator = domain_data[TREM_COORDINATOR]

        coordinator.retry = 0
        coordinator.connection = None
        coordinator.update_interval = coordinator.timer

    hass.services.async_register(
        DOMAIN,
        "simulator",
        simulator_eartkquake,
        vol.Schema(
            {
                vol.Required(ATTR_ENTITY_ID): cv.entity_id,
                vol.Required(ATTR_EQDATA): cv.string,
            },
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "save",
        save_image,
        vol.Schema(
            {
                vol.Required(ATTR_ENTITY_ID): cv.entity_id,
                vol.Required(ATTR_FILENAME): cv.string,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "reconnect",
        reconnect,
        vol.Schema(
            {
                vol.Required(ATTR_ENTITY_ID): cv.entity_id,
            }
        ),
    )
