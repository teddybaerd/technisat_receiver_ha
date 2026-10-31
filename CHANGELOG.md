# Changelog

## 0.2.1
### Fixed
- After switching the receiver on or off from Home Assistant the commanded state is now
  used for up to 90 s until the SSDP observation confirms it. Before, the stale renderer
  state was shown for up to a minute and an immediate `turn_on` after `turn_off` (or the
  other way round) could be skipped because Home Assistant still assumed the old state.
- The `standby` key sent through `remote.send_command` updates the state the same way.
- If the state is not confirmed within 90 s (e.g. the key was not received), the SSDP
  observation takes over again.

### Known / not yet verified
- Behaviour during recordings and timers (no external disk available for testing).
- Radio mode: it is not known whether the renderer stays visible. Planned for a later release.

## 0.2.0
- Automatic on/standby detection via SSDP MediaRenderer discovery (no fixed device path).
- Brand icons.

## 0.1.0
- First release: discovery, media_player, remote, optional status entity.
