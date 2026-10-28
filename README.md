# TechniSat Receiver HA

[![hacs](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

Home Assistant custom integration for **TechniSat DIGIT satellite receivers** (developed and tested with the **DIGIT ISIO STC+**). It talks to the receiver locally over the same network protocol as the TechniSat CONNECT app. No cloud, no account.

> 🇩🇪 Deutsche Beschreibung: [weiter unten](#deutsch)

## Features

- Discovery of receivers on the network (or manual IP address)
- `media_player` entity: power on/off, volume ±, mute, channel up/down (as next/previous), play/pause, stop
- `remote` entity: `remote.send_command` with key names or raw key codes (menu, OK, arrows, colour keys, digits, …)
- Optional status source (e.g. the power sensor of a smart plug) to get a *real* on/off state
- English and German UI

## Limitations — please read

- **The receiver does not report whether it is on or in standby**, and it does not report the current channel/programme. Therefore the integration cannot show them. By default the on/off state is **assumed** (it follows the commands HA sends and is restored after a restart). Standby is a *toggle* key on the receiver.
- To get a real state, set a **status entity** in the integration options: a power `sensor` (on above a threshold, default 9 W — the DIGIT ISIO STC+ datasheet lists 13.5 W on vs. 5 W Quick-Start standby), or any `binary_sensor`/`switch`/`input_boolean`.
- Only the keys `standby` and `menu` were verified on real hardware so far. The other key codes come from the documented protocol and should work, but are untested. Please report your findings via an issue.
- Only set-top boxes were tested. TechniSat TVs or other devices are not supported.

## Receiver prerequisites

On the receiver:

1. **App control** ("App-Steuerung") enabled in the network settings. Without it the receiver ignores the PIN request and nothing works.
2. **Quick Start** ("Schnellstart") enabled in the basic settings. Otherwise the network is off in standby, and the receiver can neither be reached nor woken up.
3. Note the PIN (default `0000`).

Network: the receiver listens on **UDP 8090** and replies **from UDP 8093**. If Home Assistant runs in Docker with bridge networking, those replies can get dropped — use `network_mode: host` (or Home Assistant OS). Discovery uses UDP broadcast; if it finds nothing, enter the IP manually (give the receiver a fixed IP/DHCP reservation).

## Installation

### HACS (custom repository)

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/teddybaerd/technisat_receiver_ha`, category *Integration*.
2. Install **TechniSat Receiver HA**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → TechniSat Receiver HA*.

### Manual

Copy `custom_components/technisat_receiver_ha` to `<config>/custom_components/` and restart.

## Usage

Entity IDs depend on the receiver name, the UI language and already existing entities (e.g. `_2` is appended if the DLNA integration already uses `media_player.digit_isio_stc`; with a German UI the remote is called `…_fernbedienung`). Replace `<your_receiver>` below with your own entity names (*Settings → Devices & services → TechniSat Receiver HA*).

```yaml
# Switch on / off (toggle is skipped if the state already matches)
action: media_player.turn_on
target:
  entity_id: media_player.<your_receiver>

# Open the menu and confirm with OK (0.5 s between keys)
action: remote.send_command
target:
  entity_id: remote.<your_receiver>_remote
data:
  command: [menu, ok]
  delay_secs: 0.5

# Raw key code
action: remote.send_command
target:
  entity_id: remote.<your_receiver>_remote
data:
  command: ["36"]
```

Key names: `0`–`9`, `standby`, `mute`, `list`, `vol_up`, `vol_down`, `help`, `prog_up`, `prog_down`, `back`, `audio`, `epg`, `teletext`, `off`, `tv_sat`, `info`, `up`, `down`, `menu`, `tv_radio`, `left`, `right`, `ok`, `red`, `green`, `yellow`, `blue`, `option`, `sleep`, `record`, `rewind`, `stop`, `play_pause`, `forward`, `subtitle`, `page_up`, `page_down`, `pvr`, `timer`.

Note: `standby` sent through `remote.send_command` toggles the receiver; with an assumed state the integration flips its guess accordingly.

## Troubleshooting

| Symptom | Cause |
|---|---|
| "No answer to the PIN" | App control is disabled on the receiver |
| Entities unavailable in standby | Quick Start disabled |
| Nothing found / no replies in Docker | Bridge network drops replies from port 8093 → host networking, or enter IP manually |
| State is wrong after using the physical remote | State is assumed → use a status entity |

Debug logging (add to `configuration.yaml`, restart or use the `logger.set_level` action):

```yaml
logger:
  default: warning
  logs:
    custom_components.technisat_receiver_ha: debug  # shows sent keys, discovery, UDP socket
```

`unknown` on the media player is normal without a status entity: the receiver does not report on/standby (see Limitations). `unavailable` means the receiver does not answer.

## Credits

Protocol knowledge from [feuster/TechniSatAPI](https://github.com/feuster/TechniSatAPI) (key code list, protocol description). This integration is an independent implementation. Not affiliated with TechniSat.

## License

MIT

---

## Deutsch

Home-Assistant-Integration für **TechniSat DIGIT Satellitenreceiver** (entwickelt und getestet mit dem **DIGIT ISIO STC+**). Die Kommunikation läuft lokal über dasselbe Netzwerkprotokoll wie die TechniSat-CONNECT-App, ohne Cloud und ohne Konto.

**Funktionen:** automatische Suche im Netzwerk (oder manuelle IP), `media_player` (Ein/Aus, Lautstärke, Mute, Programm ±, Play/Pause, Stop), `remote` (`remote.send_command` mit Tastennamen oder Tastencodes), optionale Statusquelle für den echten Ein/Aus-Zustand.

**Einschränkungen:**
- Der Receiver meldet **weder Standby/Ein noch das aktuelle Programm**. Der Ein/Aus-Zustand ist daher standardmäßig **angenommen** (folgt den gesendeten Befehlen, wird nach Neustart wiederhergestellt). Standby ist am Receiver eine Umschalttaste.
- Für einen echten Zustand in den Integrationsoptionen eine **Status-Entität** wählen, z. B. den Leistungssensor einer smarten Steckdose (Schwellwert standardmäßig 9 W; laut Datenblatt ca. 13,5 W an, 5 W Standby mit Schnellstart).
- Nur `standby` und `menu` sind bisher an echter Hardware geprüft; die übrigen Tastencodes stammen aus der dokumentierten Protokollbeschreibung.
- Getestet nur mit Receivern, nicht mit TechniSat-Fernsehern.

**Voraussetzungen am Receiver:**
1. **App-Steuerung** in den Netzwerkeinstellungen aktivieren (sonst ignoriert der Receiver alles).
2. **Schnellstart** in den Grundeinstellungen aktivieren (sonst ist das Netzwerk im Standby aus, der Receiver ist nicht erreichbar und lässt sich nicht einschalten).
3. PIN merken (Standard `0000`).

**Entitätsnamen:** Sie hängen von Receivername, Sprache und bereits vorhandenen Entitäten ab (z. B. `_2`, wenn die DLNA-Integration den Namen schon belegt; bei deutscher Oberfläche heißt die Fernbedienung `…_fernbedienung`).

**Zustand `unbekannt`:** Ohne Status-Entität normal, der Receiver meldet Ein/Standby nicht. `nicht verfügbar` bedeutet, dass der Receiver nicht antwortet.

**Docker:** Der Receiver antwortet von UDP-Port 8093 auf Anfragen an Port 8090. Im Docker-Bridge-Netz können diese Antworten verloren gehen, daher `network_mode: host` verwenden (bei Portainer: Network „host“). Bei fehlgeschlagener Suche die IP manuell eingeben und dem Receiver per DHCP-Reservierung eine feste IP geben.

**Installation:** HACS → Benutzerdefinierte Repositories → `https://github.com/teddybaerd/technisat_receiver_ha` (Kategorie Integration) → installieren → Home Assistant neu starten → *Einstellungen → Geräte & Dienste → Integration hinzufügen*.

**Danksagung:** Protokollwissen von [feuster/TechniSatAPI](https://github.com/feuster/TechniSatAPI). Keine Verbindung zu TechniSat.
