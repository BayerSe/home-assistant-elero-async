"""Support for Elero electrical drives."""

import logging

from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform, CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from custom_components.elero.const import (
    CONF_LOG_LEVEL,
    DEFAULT_LOG_LEVEL,
    DOMAIN,
    LOG_LEVEL_OPTIONS,
)
from custom_components.elero.coordinator import EleroDataUpdateCoordinator
from custom_components.elero.transmitter.transmitter import TransmitterConnectionError

_LOGGER = logging.getLogger(__name__)


def _apply_log_level(entry: ConfigEntry) -> None:
    """Apply the configured integration log level."""
    log_level = str(entry.options.get(CONF_LOG_LEVEL, DEFAULT_LOG_LEVEL)).lower()
    if log_level not in LOG_LEVEL_OPTIONS:
        _LOGGER.warning(
            "Invalid Elero log level '%s' for entry '%s'; using '%s'",
            log_level,
            entry.title,
            DEFAULT_LOG_LEVEL,
        )
        log_level = DEFAULT_LOG_LEVEL
    _LOGGER.info("Applying Elero log level '%s' for entry '%s'", log_level, entry.title)
    logger = logging.getLogger(f"custom_components.{DOMAIN}")
    logger.setLevel(getattr(logging, log_level.upper()))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Elero integration from a configuration entry.

    Initializes the data update coordinator, connects to the transmitter,
    and forwards the entry setup to supported platforms.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): The configuration entry.

    Returns:
        bool: True if setup was successful, False otherwise.
    """

    _apply_log_level(entry)
    _LOGGER.debug("Starting setup of the Elero integration")

    _LOGGER.debug(
        "Setting up Elero entry: unique_id=%s title=%s address=%s data_keys=%s",
        entry.unique_id,
        entry.title,
        entry.data.get(CONF_ADDRESS),
        list(entry.data.keys()),
    )

    _LOGGER.info("Setting up Elero integration entry '%s'", entry.title)
    coordinator = EleroDataUpdateCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    entry.add_update_listener(async_update_options)

    try:
        await coordinator.connect()
    except TransmitterConnectionError as err:
        _LOGGER.error("Failed to set up Elero integration: %s", err)
        return False
    _LOGGER.info("Connected Elero transmitter for entry '%s'", entry.title)

    try:
        await hass.config_entries.async_forward_entry_setups(entry, [Platform.COVER])
    except HomeAssistantError:
        _LOGGER.error("An error occurred while forwarding entry setups.")
        return False

    async def close_serial_ports(_):
        """Close the serial port."""
        await coordinator.disconnect()

    # Register the shutdown cleanup — tied to entry lifecycle so it's
    # removed automatically on unload.
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, close_serial_ports)
    )

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle an update to the integration options.

    This method is called when the user updates the integration's options
    via the Home Assistant UI. It triggers the coordinator to refresh its
    configuration and apply any new settings.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): The configuration entry being updated.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id]
    _apply_log_level(entry)
    _LOGGER.info("Applying updated options for Elero entry '%s'", entry.title)
    await coordinator.async_config_entry_updated(entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the Elero integration and clean up resources.

    This method is called when the integration is removed from Home Assistant.
    It unloads all associated platforms and removes the coordinator from hass.data.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): The configuration entry being unloaded.

    Returns:
        bool: True if the unload was successful, False otherwise.
    """
    _LOGGER.info("Unloading Elero integration entry '%s'", entry.title)
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, [Platform.COVER]
    )
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator:
            await coordinator.disconnect()
        _LOGGER.info("Elero integration entry '%s' unloaded", entry.title)
    return unload_ok
