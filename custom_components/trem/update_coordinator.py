"""Common Data class used by both sensor and entity."""

from __future__ import annotations

from asyncio.exceptions import TimeoutError
from datetime import datetime, timedelta
import json
import logging
import random

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
from .earthquake.eew import EEW
from .exceptions import UnknownError, WebSocketClosure, WebSocketException
from .session import WebSocketConnection

_LOGGER = logging.getLogger(__name__)


class tremUpdateCoordinator(DataUpdateCoordinator):
    """Class for handling the TREM data retrieval."""

    def __init__(
        self,
        hass: HomeAssistant,
        base_info: str | dict,
        update_interval: timedelta,
    ) -> None:
        """Initialize the data object."""

        # Coordinator data
        self._hass = hass
        self.timer = update_interval
        self.plan: str = FREE_PLAN
        self.status: str = "http"
        self.retry: int = 0

        # Websocket data
        self.connection: WebSocketConnection | None = None
        self.session = async_get_clientsession(hass)
        self._credentials: dict | None = None

        # Connection data
        self._http_url = ""
        self._http_station = ""
        self._ws_url = ""
        self._ws_station = ""

        # Get the route for fetching data
        if isinstance(base_info, dict):
            self.plan = SUBSCRIBE_PLAN

            self._credentials = {
                CONF_EMAIL: base_info.get(CONF_EMAIL, ""),
                CONF_PASS: base_info.get(CONF_PASS, ""),
            }

            self.get_route()
        elif base_info in BASE_URLS:
            self._http_station = base_info
            self._http_url = f"{BASE_URLS[base_info]}/api/v1/eq/eew"
        elif validators.url(base_info):
            self.plan = CUSTOMIZE_PLAN

            self._http_station = base_info
            self._http_url = base_info
        else:
            self.get_route()

        # Connection status
        self.station = (
            self._ws_station if self.plan == SUBSCRIBE_PLAN else self._http_station
        )
        self.recvTime: float = datetime.timestamp(datetime.now()) * 1000

        # Sensor data
        self.earthquakeData: list = []
        self.intensity: dict = {}
        self.rtsData: dict = {}
        self.tsunamiData: dict = {}

        # Earthquake data
        self.eew: EEW | None = None

        super().__init__(
            hass,
            _LOGGER,
            name="TREM",
            update_interval=self.timer,
        )

    async def _async_update_data(self):
        """Poll earthquake data."""

        if self.retry >= 5:
            self.update_interval = timedelta(seconds=86400)
            raise UpdateFailed

        resp: dict = {}
        if self.plan == SUBSCRIBE_PLAN:
            try:
                if self.connection is None:
                    self.connection = WebSocketConnection(
                        self._hass, self._ws_url, self._credentials
                    )
                    self._hass.async_create_task(self.connection.connect())

                if self.connection.is_running:
                    self.retry = 0
                    resp = await self.connection.recv()

                    recvData: dict | bool = resp.get("data", False)
                    if recvData:
                        self.recvTime = recvData.get(
                            "time", datetime.timestamp(datetime.now()) * 1000
                        )

                        subscrib_service: list = resp.get("list", [])
                        if len(subscrib_service) > 0:
                            self.earthquakeData = self.connection.earthquakeData
                            self.intensity = self.connection.intensity
                            self.rtsData = self.connection.rtsData
                            self.tsunamiData = self.connection.tsunamiData

                            self.status = SUBSCRIBE_PLAN
                        else:
                            await _notify_message(
                                self._hass,
                                "MembershipExpired",
                                CLIENT_NAME,
                                "Your VIP membership has expired, Please re-subscribe.",
                            )

                            self.status = FREE_PLAN
                    else:
                        resp = {}
                        self.status = "ws_reconnect"
                        self.recvTime = datetime.timestamp(datetime.now()) * 1000
                else:
                    self.retry = self.retry + 1

                    self.connection = None
                    resp = {}
                    self.status = "ws_reconnect"
                    _LOGGER.warning("Reconnecting websocket")

            except ConnectionResetError:
                await self.connection.close()
                self.status = "failure"

                _LOGGER.error("The websocket server has closed the connection")
            except WebSocketClosure:
                self.connection = None
                self.status = "ws_reconnect"

                _LOGGER.error("The websocket server has closed the connection")
            except WebSocketException:
                _LOGGER.error("Websocket connection had an error")
            except UnknownError:
                _LOGGER.error("An unexpected error occurred")
            except TimeoutError:
                _LOGGER.error("Unable to login to account")
            except TypeError:
                if not self.connection.is_stopping:
                    _LOGGER.error("Received non-JSON data from server")
            except (KeyboardInterrupt, SystemExit):
                await self.connection.close()
            except Exception:
                _LOGGER.exception(
                    "An unexpected exception occurred on the websocket client"
                )

        if not resp.get("data", False):
            try:
                payload = {}
                headers = {
                    ACCEPT: CONTENT_TYPE_JSON,
                    CONTENT_TYPE: CONTENT_TYPE_JSON,
                    USER_AGENT: HA_USER_AGENT,
                }

                response = await self.session.request(
                    method=METH_GET,
                    url=self._http_url,
                    data=json.dumps(payload),
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                )
                self.recvTime = datetime.timestamp(datetime.now()) * 1000
            except ClientConnectorError as ex:
                self.retry = self.retry + 1

                _LOGGER.error(
                    "Failed fetching data from HTTP API(%s), %s. Retry %s/5",
                    self.station,
                    ex.strerror,
                    self.retry,
                )
            except TimeoutError as ex:
                self.retry = self.retry + 1

                _LOGGER.error(
                    "Failed fetching data from HTTP API(%s), %s. Retry %s/5",
                    self.station,
                    ex.strerror,
                    self.retry,
                )
            except Exception:
                _LOGGER.exception(
                    "An unexpected exception occurred fetching the data from HTTP API(%s)",
                    self.station,
                )
            else:
                if response.ok:
                    self.retry = 0

                    resp = await response.json()
                    self.earthquakeData = resp
                else:
                    self.retry = self.retry + 1

                    _LOGGER.error(
                        "Failed fetching data from HTTP API(%s), (HTTP Status Code = %s). Retry %s/5",
                        self.station,
                        response.status,
                        self.retry,
                    )

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.info("Recv: %s", resp)

        if self.retry == 0:
            self.update_interval = self.timer

        if self.retry > 0:
            self.update_interval = timedelta(
                seconds=5 if self.plan == SUBSCRIBE_PLAN else 60
            )

            # Switch route
            self.get_route(
                {
                    FREE_PLAN: self._http_station,
                    SUBSCRIBE_PLAN: self._ws_station,
                }
            )

            raise UpdateFailed

        return self

    def get_route(self, exclude: dict | None = None):
        """Random the node for fetching data."""

        # Self server
        if self.plan == CUSTOMIZE_PLAN:
            return None

        # HTTP route
        if isinstance(exclude, dict) and exclude.get(FREE_PLAN):
            HTTP_Route = {k: v for k, v in BASE_URLS.items() if k != exclude[FREE_PLAN]}
        else:
            HTTP_Route = BASE_URLS.items()
        self._http_station, base_url = random.choice(list(HTTP_Route))
        self._http_url = f"{base_url}/api/v1/eq/eew"

        # Websocket route
        if isinstance(exclude, dict) and exclude.get(SUBSCRIBE_PLAN):
            WS_Route = {
                k: v for k, v in BASE_WS.items() if k != exclude[SUBSCRIBE_PLAN]
            }
        else:
            WS_Route = BASE_WS.items()
        self._ws_station, base_url = random.choice(list(WS_Route))
        self._ws_url = base_url

        if isinstance(exclude, dict) and exclude.get(self.plan, False):
            _LOGGER.warning(
                "Switch Station {%s} to {%s}, Try to fetching data",
                exclude[self.plan],
                self._ws_station if self.plan == SUBSCRIBE_PLAN else self._http_station,
            )


async def _notify_message(
    hass: HomeAssistant, notification_id: str, title: str, message: str
) -> None:
    """Notify user with persistent notification."""

    persistent_notification.async_create(
        hass, message, title, f"{DOMAIN}.{notification_id}"
    )
