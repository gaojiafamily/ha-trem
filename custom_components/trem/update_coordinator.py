"""Common Data class used by both sensor and entity."""

from __future__ import annotations

from asyncio.exceptions import TimeoutError
from datetime import timedelta
from io import BytesIO
import json
import logging
import random
from typing import Any

from aiohttp import ClientResponse, WebSocketError
from aiohttp.client_exceptions import ClientConnectorError
from aiohttp.hdrs import ACCEPT, CONTENT_TYPE, METH_GET, USER_AGENT
import validators

from homeassistant.components import persistent_notification
from homeassistant.const import CONF_EMAIL, CONTENT_TYPE_JSON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BASE_URLS,
    BASE_WS,
    CLIENT_NAME,
    CONF_PASS,
    CUSTOMIZE_PLAN,
    DOMAIN,
    FREE_PLAN,
    HA_USER_AGENT,
    NOTIFY_URL,
    REQUEST_TIMEOUT,
    SUBSCRIBE_PLAN,
)
from .exceptions import WebSocketClosure
from .session import WebSocketConnection

_LOGGER = logging.getLogger(__name__)


class tremUpdateCoordinator(DataUpdateCoordinator):
    """Class for handling the TREM data retrieval."""

    def __init__(
        self,
        hass: HomeAssistant,
        base_info: str | dict,
        region: str | int,
        update_interval: timedelta,
    ) -> None:
        """Initialize the data object."""

        self._hass = hass
        self._update_interval = update_interval

        self.connection: WebSocketConnection | None = None
        self.session = async_get_clientsession(hass)
        self._credentials: dict | None = None
        self.plan: str = FREE_PLAN

        self.region = region
        self.map: BytesIO | None = None
        self.mapSerial = ""

        if isinstance(base_info, dict):
            station, base_url = random.choice(list(BASE_WS.items()))
            self.plan = SUBSCRIBE_PLAN
            self._credentials = {
                CONF_EMAIL: base_info[CONF_EMAIL],
                CONF_PASS: base_info[CONF_PASS],
            }
        elif base_info in BASE_URLS:
            station = base_info
            base_url = BASE_URLS[base_info]
        elif validators.url(base_info):
            station = base_info
            base_url = base_info
            self.plan = CUSTOMIZE_PLAN
        else:
            station, base_url = random.choice(list(BASE_URLS.items()))
        self.station: str = station
        self._base_url: str = (
            base_url
            if self.plan == CUSTOMIZE_PLAN
            else f"{base_url}/api/v1/eq/eew?type=cwa"
        )
        self._protocol = "Http(s)"
        self.retry: int = 0
        self.earthquakeData: dict | list = {}
        self.rtsData: dict = {}
        self.tsunamiData: dict = {}

        if self.plan == SUBSCRIBE_PLAN:
            self._protocol = "Websocket"
            super().__init__(
                hass,
                _LOGGER,
                name=self._protocol,
                update_method=self._async_update_websocket,
                update_interval=self._update_interval,
            )
        else:
            super().__init__(
                hass,
                _LOGGER,
                name=self._protocol,
                update_method=self._async_update_http,
                update_interval=self._update_interval,
            )

        _LOGGER.debug(
            f"{self._protocol}: Fetching data from {self.station}, EEW(location: {self.region}) is monitoring..."  # noqa: G004
        )

    async def _async_update_http(self):
        """Poll earthquake data from Http(s) api."""

        if self.retry >= 5:
            self.update_interval = timedelta(seconds=86400)
            raise UpdateFailed

        response: ClientResponse | None = None
        payload = {}
        headers = {
            ACCEPT: CONTENT_TYPE_JSON,
            CONTENT_TYPE: CONTENT_TYPE_JSON,
            USER_AGENT: HA_USER_AGENT,
        }

        try:
            response = await self.session.request(
                method=METH_GET,
                url=self._base_url,
                data=json.dumps(payload),
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
        except ClientConnectorError as ex:
            self.retry = self.retry + 1

            _LOGGER.error(
                f"Failed fetching data from Http(s) API({self.station}), {ex.strerror}. Retry {self.retry}/5..."  # noqa: G004
            )
        except TimeoutError as ex:
            self.retry = self.retry + 1

            _LOGGER.error(
                f"Failed fetching data from Http(s) API({self.station}), {ex.strerror}. Retry {self.retry}/5..."  # noqa: G004
            )
        except Exception:
            _LOGGER.exception(
                f"An unexpected exception occurred fetching the data from Http(s) API({self.station})."  # noqa: G004
            )
        else:
            if response.ok:
                self.retry = 0

                self.earthquakeData = await response.json()
            else:
                self.retry = self.retry + 1

                _LOGGER.error(
                    f"Failed fetching data from Http(s) API({self.station}), (HTTP Status Code = {response.status}). Retry {self.retry}/5..."  # noqa: G004
                )

        if self.retry == 0:
            self.update_interval = self._update_interval

        if self.retry > 0:
            self.update_interval = timedelta(seconds=60)

            await self.switch_node()
            raise UpdateFailed

        return self

    async def _async_update_websocket(self):
        """Poll earthquake data from websocket."""

        if self.connection is None:
            try:
                self.connection = WebSocketConnection(
                    self._hass, self._base_url, self._credentials
                )
                self._hass.async_create_task(self.connection.connect())

            except WebSocketClosure:
                _LOGGER.error("The websocket server has closed the connection.")

            except WebSocketError:
                _LOGGER.error("Websocket connection had an error.")

            except Exception:
                _LOGGER.exception(
                    "An unexpected exception occurred on the websocket client."
                )
        else:
            isReady = self.connection.ready()
            if isReady:
                self.earthquakeData = self.connection.earthquakeData
                self.rtsData = self.connection.rtsData
                self.tsunamiData = self.connection.tsunamiData

                if len(self.connection.subscrib_service) == 0:
                    await _notify_message(
                        self._hass,
                        "MembershipExpired",
                        CLIENT_NAME,
                        "Your VIP membership has expired, Please re-subscribe.",
                    )
            else:
                if not self.connection.is_running:
                    self.connection = None
                    _LOGGER.warning("Reconnecting websocket...")
                raise UpdateFailed

        return self

    async def switch_node(self) -> str | None:
        """Switch the Http(s) api node for fetching earthquake data."""

        if self.plan == CUSTOMIZE_PLAN:
            return None

        tmpStations: dict = BASE_URLS.items()
        if self.plan == SUBSCRIBE_PLAN:
            tmpStations = BASE_WS.items()
        tmpStations.pop(self.station)

        station, base_url = random.choice(list(tmpStations))
        self.station = station
        self._base_url = base_url

        _LOGGER.warning(
            f"Switch Station {self.station} to {station}, Try to fetching data..."
        )

        return station


class dpipUpdateCoordinator(DataUpdateCoordinator):
    """Class for handling the DPIP data retrieval."""

    def __init__(
        self,
        hass: HomeAssistant,
        token: str,
        update_interval: timedelta,
    ) -> None:
        """Initialize the data object."""

        self._hass = hass
        self._update_interval = update_interval

        self.session = async_get_clientsession(hass)
        self.dpipData: dict = {}
        self.token = token

        super().__init__(
            hass,
            _LOGGER,
            name="DPIP",
            update_method=self.async_update_data,
            update_interval=self._update_interval,
        )

        _LOGGER.debug("Fetching DPIP data...")

    async def async_update_data(self) -> Any | None:
        """Poll DPIP data from notify api."""

        response: ClientResponse | None = None
        payload = {}
        headers = {
            ACCEPT: CONTENT_TYPE_JSON,
            CONTENT_TYPE: CONTENT_TYPE_JSON,
            USER_AGENT: HA_USER_AGENT,
        }

        try:
            response = await self.session.request(
                method=METH_GET,
                url=f"{NOTIFY_URL}/info/{self.token}",
                data=json.dumps(payload),
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
        except ClientConnectorError as ex:
            _LOGGER.error(f"Failed fetching DPIP data, {ex.strerror}.")  # noqa: G004
            raise UpdateFailed  # noqa: B904
        except TimeoutError as ex:
            _LOGGER.error(f"Failed fetching DPIP data, {ex.strerror}.")  # noqa: G004
            raise UpdateFailed  # noqa: B904
        except Exception:
            _LOGGER.exception("An unexpected exception occurred fetching DPIP data.")
            raise UpdateFailed  # noqa: B904
        else:
            if response.ok:
                self.dpipData = await response.json()
            else:
                _LOGGER.error(
                    f"Failed fetching DPIP data, (HTTP Status Code = {response.status})."  # noqa: G004
                )

        return self


async def _notify_message(
    hass: HomeAssistant, notification_id: str, title: str, message: str
) -> None:
    """Notify user with persistent notification."""

    persistent_notification.async_create(
        hass, message, title, f"{DOMAIN}.{notification_id}"
    )
