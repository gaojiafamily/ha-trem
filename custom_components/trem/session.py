"""WebSocket Client for the Taiwan Real-time Earthquake Monitoring."""

from __future__ import annotations

import asyncio
from enum import Enum
import json
import logging
import time

from aiohttp import ClientWebSocketResponse, WSMsgType
from aiohttp.client_exceptions import (
    ClientConnectorError,
    ServerTimeoutError,
    TooManyRedirects,
    WSServerHandshakeError,
)
from aiohttp.hdrs import ACCEPT, CONTENT_TYPE, METH_POST, USER_AGENT

from homeassistant.const import (
    APPLICATION_NAME,
    CONF_NAME,
    CONTENT_TYPE_JSON,
    EVENT_HOMEASSISTANT_STOP,
    __version__ as HAVERSION,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CLIENT_NAME,
    DEFAULT_MAX_MSG_SIZE,
    HA_USER_AGENT,
    LOGIN_URL,
    REQUEST_TIMEOUT,
    __version__,
)
from .exceptions import (
    CannotConnect,
    UnknownError,
    WebSocketClosure,
    WebSocketException,
)

_LOGGER = logging.getLogger(__name__)


class WebSocketEvent(Enum):
    """Represent the websocket event."""

    EEW = "eew"
    INFO = "info"
    NTP = "ntp"
    REPORT = "report"
    RTS = "rts"
    RTW = "rtw"
    VERIFY = "verify"
    CLOSE = "close"
    ERROR = "error"
    TSUNAMI = "tsunami"
    INTENSITY = "intensity"


class WebSocketService(Enum):
    """Represent the supported websokcet service."""

    REALTIME_STATION = "trem.rts"
    REALTIME_WAVE = "trem.rtw"
    EEW = "websocket.eew"
    TREM_EEW = "trem.eew"
    REPORT = "websocket.report"
    TSUNAMI = "websocket.tsunami"
    CWA_INTENSITY = "cwa.intensity"
    TREM_INTENSITY = "trem.intensity"


class WebSocketConnection:
    """A Websocket connection to a TREM service."""

    def __init__(self, hass: HomeAssistant, url: str, credentials: list) -> None:
        """Initialize the websocket."""

        self._hass = hass

        self._connection: ClientWebSocketResponse | None = None
        self._session = async_get_clientsession(hass)
        self.is_running = False
        self.is_stopping = False

        self._url = url
        self._credentials = credentials
        self._access_token: str = "c0d30WNER$JTGAO"

        self._subscrib_service: list = []
        self._register_service: list[WebSocketService] = [
            WebSocketService.EEW.value,
            WebSocketService.TSUNAMI.value,
            WebSocketService.REALTIME_STATION.value,
            WebSocketService.CWA_INTENSITY.value,
            WebSocketService.TREM_INTENSITY.value,
        ]
        self.earthquakeData: list = []
        self.intensity: dict = {}
        self.rtsData: dict = {}
        self.tsunamiData: dict = {}

    async def connect(self):
        """Connect to Websocket..."""

        self.is_running = True

        try:
            session = self._session
            headers = {
                ACCEPT: CONTENT_TYPE_JSON,
                CONTENT_TYPE: CONTENT_TYPE_JSON,
                USER_AGENT: HA_USER_AGENT,
            }
            self._connection = await session.ws_connect(
                self._url,
                headers=headers,
                max_msg_size=DEFAULT_MAX_MSG_SIZE,
            )
        except WSServerHandshakeError:
            raise WebSocketException  # noqa: B904
        except Exception:  # noqa: BLE001
            raise CannotConnect  # noqa: B904

        async def _async_stop_handler(event):
            await asyncio.gather(*[self.close()])

        try:
            self._hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, _async_stop_handler
            )
        except Exception:  # noqa: BLE001
            await self.close()
            raise UnknownError  # noqa: B904

    async def close(self):
        """Close connection."""

        self.is_running = False
        self.is_stopping = True
        if self._connection is not None:
            await self._connection.close()

    async def recv(self) -> dict:
        """Recive websocket data."""

        if self._connection is None:
            return {}

        msg = await self._connection.receive()
        if msg:
            msg_type: WSMsgType = msg.type
        else:
            return {}

        if msg_type in (
            WSMsgType.CLOSE,
            WSMsgType.CLOSED,
            WSMsgType.CLOSING,
        ):
            raise WebSocketClosure

        msg_data: dict = json.loads(msg.data)

        if msg_type == WSMsgType.ERROR:
            handle_error = await self._handle_error(msg_data)
            if not handle_error:
                raise WebSocketException

        data_type = msg_data.get("type")
        if data_type == WebSocketEvent.VERIFY.value:
            self._access_token = await self._fetchToken(credentials=self._credentials)
            payload: dict = {
                "key": self._access_token,
                "service": self._register_service,
            }
            payload["type"] = "start"
            await self._connection.send_json(payload)

            data: dict = await asyncio.wait_for(self._wait_for_verify(), timeout=60)
            self._subscrib_service = data.get("list", [])
        elif data_type == "data":
            data: dict = msg_data.get("data")
            eventType: dict = data.get("type")

            if eventType == WebSocketEvent.RTS.value:
                self.rtsData = data.get("data")

            if eventType == WebSocketEvent.INTENSITY.value:
                self.intensity = data

            if eventType == WebSocketEvent.EEW.value:
                if data.get("author", None) == "cwa":
                    msgTime = msg_data.get("time", 0)
                    tmpData: dict = data
                    tmpData["time"] = data.get("time", msgTime)
                    self.earthquakeData = [tmpData]

            if eventType == WebSocketEvent.TSUNAMI.value:
                if data.get("author", None) == "cwa":
                    msgTime = msg_data.get("time", 0)
                    tmpData: dict = data
                    tmpData["time"] = data.get("time", msgTime)
                    self.tsunamiData = tmpData

        return {
            "list": self._subscrib_service,
            "data": msg_data,
        }

    async def _wait_for_verify(self):
        """Return websocket message data if verify successfully."""

        while True:
            msg = await self._connection.receive()
            if msg:
                msg_data: dict = json.loads(msg.data)
            else:
                continue

            data_type = msg_data.get("type")
            if data_type != WebSocketEvent.INFO.value:
                continue

            data: dict = msg_data.get("data")
            data_code = data.get("code")
            if data_code == 200:
                return data

            await self._handle_error(msg_data)

    def _connected(self) -> bool:
        """Whether the websocket is connected."""

        if self._connection is None:
            return False
        if self.is_stopping or self._connection.closed:
            return False

        return True

    async def _fetchToken(self, credentials: list) -> str:
        """Fetch token from Exptech Membership."""

        if self._access_token == "c0d30WNER$JTGAO":
            try:
                payload = credentials
                payload[CONF_NAME] = (
                    f"{APPLICATION_NAME}/{CLIENT_NAME}/{__version__}/{HAVERSION}"
                )
                headers = {
                    USER_AGENT: HA_USER_AGENT,
                    CONTENT_TYPE: CONTENT_TYPE_JSON,
                }
                response = await self._session.request(
                    method=METH_POST,
                    url=LOGIN_URL,
                    data=json.dumps(payload),
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                )

                if not response.ok:
                    message = response.json()
                    _LOGGER.error(
                        "Failed fetching token from Exptech Membership API, %s (HTTP Status Code = %s)",
                        message["message"],
                        response.status,
                    )
                else:
                    token = await response.text()
                    self._access_token = token

                    return token
            except ClientConnectorError as ex:
                _LOGGER.error(
                    "Failed fetching token from Exptech Membership API, %s", ex.strerror
                )
            except TooManyRedirects:
                _LOGGER.error(
                    "Failed fetching token from Exptech Membership API, Too many redirects"
                )
            except ServerTimeoutError:
                _LOGGER.error(
                    "Failed fetching token from Exptech Membership API, Timeout"
                )
        else:
            return self._access_token

        await self.close()
        raise CannotConnect

    async def _handle_error(self, msg_data: dict) -> bool:
        data: dict = msg_data.get("data")
        status_code = data.get("code")
        message: str | None = None

        if status_code == 400:
            message = (
                "The number of available authorization has reached the upper limit"
            )

        if status_code == 401:
            message = "The account does not exist or password is invalid"

        if status_code == 403:
            message = "Your VIP membership has expired, Please re-subscribe"

        if status_code == 429:
            message = "Too many requests in a given time"

        if message is None:
            return False

        _LOGGER.error(message)
