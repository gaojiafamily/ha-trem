"""Common Data class used by both sensor and entity."""

from __future__ import annotations

from asyncio.exceptions import TimeoutError
from datetime import timedelta
from io import BytesIO
import json
import logging
import random

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
        self._init_update_interval = update_interval

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
        self._tmpStation: str | None = None
        self._tmpUrl: str | None = None
        self._base_url: str = (
            f"{base_url}/api/v1/eq/eew?type=cwa" if self.plan == FREE_PLAN else base_url
        )
        self.protocol = "Http(s)"
        self.retry: int = 0
        self.earthquakeData: dict | list = {}
        self.rtsData: dict = {}
        self.tsunamiData: dict = {}

        if self.plan == SUBSCRIBE_PLAN:
            self.protocol = "Websocket"
            super().__init__(
                hass,
                _LOGGER,
                name=self.protocol,
                update_method=self._async_update_websocket,
                update_interval=self._init_update_interval,
            )
        else:
            super().__init__(
                hass,
                _LOGGER,
                name=self.protocol,
                update_method=self._async_update_http,
                update_interval=self._init_update_interval,
            )

        _LOGGER.debug(
            f"{self.protocol}: Fetching data from {self.station}, EEW(location: {self.region}) is monitoring..."  # noqa: G004
        )

    async def _fetch_data(self, url=None) -> ClientResponse:
        """Fetch earthquake data from the Http API."""

        self.protocol = "Http(s)"

        payload = {}
        headers = {
            ACCEPT: CONTENT_TYPE_JSON,
            CONTENT_TYPE: CONTENT_TYPE_JSON,
            USER_AGENT: HA_USER_AGENT,
        }

        return await self.session.request(
            method=METH_GET,
            url=self._base_url if url is None else url,
            data=json.dumps(payload),
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

    async def _async_update_http(self):
        """Poll earthquake data from Http(s) api."""

        if self.retry >= 5:
            self.update_interval = timedelta(seconds=86400)
            raise UpdateFailed

        try:
            response = await self._fetch_data()
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
            self.update_interval = self._init_update_interval

        if self.retry > 0:
            self.update_interval = timedelta(seconds=60)

            station, base_url = await self.get_route()
            self.station = station
            self._base_url = base_url
            _LOGGER.warning(
                f"Switch Station {self.station} to {station}, Try to fetching data..."
            )

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
                self.retry = 0
                self.protocol = "Websocket"

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
                self.retry = self.retry + 1

                if not self.connection.is_running:
                    self.connection = None
                    _LOGGER.warning("Reconnecting websocket...")

        if self.retry == 0:
            self.update_interval = self._init_update_interval

        if self.retry > 0:
            self.update_interval = timedelta(seconds=5)

            if self._tmpUrl is None:
                station, url = await self.get_route("Http(s)")
                self._tmpStation = station
                self._tmpUrl = f"{url}/api/v1/eq/eew?type=cwa"

            try:
                _LOGGER.debug(
                    f"Websocket is unavailable, Fetching data from Http(s) API({self._tmpStation})..."  # noqa: G004
                )
                response = await self._fetch_data(self._tmpUrl)
            except ClientConnectorError as ex:
                _LOGGER.error(
                    f"Failed fetching data from Http(s) API({self._tmpStation}), {ex.strerror}. Retry {self.retry}/5..."  # noqa: G004
                )
            except TimeoutError as ex:
                _LOGGER.error(
                    f"Failed fetching data from Http(s) API({self._tmpStation}), {ex.strerror}. Retry {self.retry}/5..."  # noqa: G004
                )
            except Exception:
                _LOGGER.exception(
                    f"An unexpected exception occurred fetching the data from Http(s) API({self._tmpStation})."  # noqa: G004
                )
            else:
                if response.ok:
                    self.earthquakeData = await response.json()
                    return self

                _LOGGER.error(
                    f"Failed fetching data from Http(s) API({self._tmpStation}), (HTTP Status Code = {response.status}). Retry {self.retry}/5..."  # noqa: G004
                )

            self._tmpUrl = None
            raise UpdateFailed

        return self

    async def get_route(self, protocol="Websocket"):
        """Random the node for fetching data."""

        if self.plan == CUSTOMIZE_PLAN:
            return None

        tmpStations = BASE_URLS.items()
        if self.plan == SUBSCRIBE_PLAN and protocol == "Websocket":
            tmpStations = BASE_WS.items()
        tmpStations = {
            k: v for k, v in tmpStations if k != self.station
        }  # tmpStations.pop(self.station)

        return random.choice(list(tmpStations.items()))


async def _notify_message(
    hass: HomeAssistant, notification_id: str, title: str, message: str
) -> None:
    """Notify user with persistent notification."""

    persistent_notification.async_create(
        hass, message, title, f"{DOMAIN}.{notification_id}"
    )
