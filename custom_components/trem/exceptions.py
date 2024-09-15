"""Exceptions for the Taiwan Real-time Earthquake Monitoring."""

from homeassistant import exceptions


class AccountInvalid(exceptions.HomeAssistantError):
    """Represents an account cannot log in."""


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class RegionInvalid(exceptions.HomeAssistantError):
    """Represents a region code is invalid."""


class FCMTokenInvalid(exceptions.HomeAssistantError):
    """Represents a FCM Token is invalid."""


class UnknownError(exceptions.HomeAssistantError):
    """Represents an unknown error."""


class WebSocketClosure(exceptions.HomeAssistantError):
    """Represents a websocket closed signal."""


class WebSocketException(exceptions.HomeAssistantError):
    """Represents a websocket closed signal."""
