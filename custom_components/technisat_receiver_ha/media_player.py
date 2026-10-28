"""Media player platform."""

from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import TechniSatEntity
from .receiver import TechniSatConfigEntry, TechniSatReceiver, resolve_command

_FEATURES = (
    MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TechniSatConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the media player."""
    async_add_entities([TechniSatMediaPlayer(entry.runtime_data)])


class TechniSatMediaPlayer(TechniSatEntity, MediaPlayerEntity, RestoreEntity):
    """The receiver as a media player.

    Channel up/down are exposed as next/previous track.
    """

    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_name = None
    _attr_supported_features = _FEATURES

    def __init__(self, receiver: TechniSatReceiver) -> None:
        super().__init__(receiver, "media_player")

    async def async_added_to_hass(self) -> None:
        """Restore the assumed power state after a restart."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None and last.state in (
            STATE_ON,
            STATE_OFF,
        ):
            self.receiver.restore_power(last.state == STATE_ON)

    @property
    def state(self) -> MediaPlayerState | None:
        """On, off or unknown."""
        power = self.receiver.power
        if power is None:
            return None
        return MediaPlayerState.ON if power else MediaPlayerState.OFF

    async def async_turn_on(self) -> None:
        """Wake the receiver from standby."""
        await self.receiver.async_set_power(True)

    async def async_turn_off(self) -> None:
        """Put the receiver into standby."""
        await self.receiver.async_set_power(False)

    async def async_volume_up(self) -> None:
        """Volume up."""
        await self.receiver.async_send_codes([resolve_command("vol_up")])

    async def async_volume_down(self) -> None:
        """Volume down."""
        await self.receiver.async_send_codes([resolve_command("vol_down")])

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute is a toggle on the receiver, the argument is ignored."""
        await self.receiver.async_send_codes([resolve_command("mute")])

    async def async_media_next_track(self) -> None:
        """Channel up."""
        await self.receiver.async_send_codes([resolve_command("prog_up")])

    async def async_media_previous_track(self) -> None:
        """Channel down."""
        await self.receiver.async_send_codes([resolve_command("prog_down")])

    async def async_media_play(self) -> None:
        """Play/pause key."""
        await self.receiver.async_send_codes([resolve_command("play_pause")])

    async def async_media_pause(self) -> None:
        """Play/pause key."""
        await self.receiver.async_send_codes([resolve_command("play_pause")])

    async def async_media_stop(self) -> None:
        """Stop key."""
        await self.receiver.async_send_codes([resolve_command("stop")])
