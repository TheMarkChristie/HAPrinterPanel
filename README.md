# Printer Panel

A **Printer** page in Home Assistant's sidebar for a Creality printer, with Creality's mark as its icon. It shows the
live camera, the name of the print, its progress, the time left and when it will be done, the nozzle, bed and chamber
temperatures, and the colours loaded in the CFS. It can pause, resume and stop the print, pause it when it reaches a
G-code line, switch its light, set the temperature targets, the speed and the fans, and tell your
phone when a print finishes, pauses, runs out of filament or stops with an error. And it keeps a filament register: the
spools you have, each with a stock number, with what every print used taken off the spool it came from.

It is built on the [Creality integration](https://github.com/3dg1luk43/ha_creality_ws) (`ha_creality_ws`), which
talks to the printer; Printer Panel adds the page, the notifications, and two controls of its own that go through the
printer's Moonraker (port 7125, which the K2 series runs). Made for a K2 Plus with a CFS; other printers the Creality
integration supports show whatever they report (no CFS, no CFS card; no chamber, no chamber row).

| On the page | What it does |
| --- | --- |
| Camera | The printer's camera live, through Home Assistant's own picture card |
| The print | Its name (from the file, without the slicer's `_PLA_9h1m52s`), a picture of the model, layer, progress, time left and the clock time it will be done |
| Pause, Resume, Stop | Pause while printing, Resume while paused; Stop asks first, as a stopped print cannot be resumed |
| Pause at line | While printing, with Count G-code lines on: the line the printer is at ("Line 341,202 of 495,870"), and a box to pause the print when it reaches a line, with how long until it does |
| Light | The printer's light, on or off |
| Temperatures | Nozzle, bed and chamber now, with their targets: type one, or step it by 5 °C |
| CFS | Every slot's colour, material and how much is left (low at 10 % or less), the slot in use, each box's temperature and humidity, the external spool, the colours in the print file, and the stock number of the spool in each slot |
| Speed and fans | The print speed, stepped by 10 % or one of Silent, Standard, Sport and Ludicrous; part cooling, side and case fans, each a slider and a switch |
| Filament | The spools checked in, with what each has left, and the slots still waiting for a stock number |

The page is drawn once and then only its values change, so the camera keeps playing. It follows the theme and speaks
English or Norwegian bokmål after the user's language. On a phone the cards stack in one column.

## Install

1. Set the printer up with the Creality integration first, if it is not already.
2. HACS > Integrations > three dots > Custom repositories: add `https://github.com/TheMarkChristie/HAPrinterPanel` as
   an Integration, download **Printer Panel**, restart Home Assistant.
3. Settings > Devices & services > Add integration > **Printer Panel**. Pick the printer, the sidebar title
   (Printer), the phones to tell (every phone with the Home Assistant app is ticked to begin with) and when to tell
   them. Submit, and **Printer** is in the sidebar for everybody.

A second printer gets a second page (`/printer-2`). The sidebar title, the phones and the events can be changed later
under the entry's Configure.

The same view is a card, for a dashboard:

```yaml
type: custom:printer-panel-card
entry_id: 01J...   # optional: which printer, when there is more than one
```

## Notifications

| When | The phone says |
| --- | --- |
| A print is finished | GTA 6 stand - Warden of Bacon is finished, after 9 h 2 min. |
| A print is paused | GTA 6 stand - Warden of Bacon is paused at 56 %. |
| The filament runs out | GTA 6 stand - Warden of Bacon: the filament ran out at 56 %. |
| A print stops with an error | GTA 6 stand - Warden of Bacon stopped with an error at 56 %. |

The title is "3D printer"; the text is in Home Assistant's language (English or Norwegian). The notification shows the
picture of the print (the slicer's picture of the model, or the camera's still when the print has none), and tapping
it opens the Printer page, with the live camera. Each printer's notifications replace each other on the
phone instead of piling up. Only a change seen while Home Assistant is running counts: a printer that comes back
online after a restart, already finished, does not tell anybody again. A phone that has gone (its notify service no
longer exists) is noted once in the log, and the others are still told.

## Counting lines, and pausing at one

These are entities of Printer Panel's own on the printer's device, so automations and scripts can use them too:

- **Count G-code lines** (`switch`, off to begin with): while it is off, Printer Panel asks the printer nothing. While
  it is on and a print is under way, the page shows "Line X of Y" (asking every 10 seconds, only while the page is
  open), and a line can be set to pause at. Counting reads the print's file from the printer once per print, to count
  its lines. Setting a line turns it on; turning it off drops the line.
- **Pause at G-code line** (`number`): set a line and the print pauses about a second after the printer reaches it;
  0 means no pause. Home Assistant looks at where the printer is in the file every 5 minutes while the line is more
  than 10 minutes away, every minute until 2 minutes away, every 30 seconds until 1 minute, every 10 seconds, and every
  second for the last 20 seconds (the time worked out from the printer's own pace), then presses the printer's own
  Pause. So a line two hours off costs about 55 small looks, and the pause comes about a second after the line, some
  tens of lines on a K2. The phone is told "... is paused at line 400,018, as asked." A line already printed, a line
  past the end of the file, or nothing printing is refused with the reason. The line is kept through a restart of Home
  Assistant; the print ending, or another print starting, drops it.

## The filament register

**Check in** a spool on the Filament card with its brand, colour (a name and a swatch), type and the weight on its
label. It gets the next stock number, F001, F002 and on (a number is never given out twice), and the page says to write
it on the spool.

The CFS says what is in each slot, and the register follows it:

- **A Creality spool** has a chip the CFS reads. When exactly one spool in the register is a Creality spool of that type
  and colour, not in another slot and not used up, it is matched to the slot on its own (Found by the CFS).
- **Any other spool**, or two Creality spools alike, waits for its stock number: press **Confirm** on the slot, before
  the print or after it, and type the number written on the spool (`2`, `f2` and `F002` are all F002). The likeliest
  spools (the slot's type, nearest its colour) are offered to pick from. A spool on the slot not checked in yet can be
  checked in from there, with what the CFS says filled in.

While a print runs, the printer's own count of the filament it has used goes to the slot printing at that moment. When
the print ends (finished or stopped), each slot's length comes off its spool in grams (1.75 mm filament at the type's
density, so about 3 g a metre of PLA). A slot without a stock number keeps its grams waiting, shown on the Filament card,
until the number is confirmed; if that spool has since left the slot, the grams still go to the number given, without
putting it back in the slot. Grams from a spool that is not in the register are dropped with **Not a spool in the
register** on the slot. Taking a spool out of a slot clears the slot; the printer being off does not.

The card lists the spools in the CFS first, in slot order, then the shelf by stock number. With more than eight spools
it has a box to find one: by number (`14` finds F014), brand, colour, type or slot, every word matching.

Change a spool (or its grams left, after weighing it) with its pencil; **Remove** takes it out of the register. The
register is kept in Home Assistant's storage, a print under way when Home Assistant restarts is taken up where it was,
and deleting the printer's entry deletes its register. Printer Panel reads all of this from the Creality integration's
entities: it asks the printer nothing for it.

## How it finds the printer's entities

By their keys in the Creality integration, not their names: renaming an entity (or the device) keeps the page and the
notifications working. A disabled entity is left off the page. The page asks the integration for its printer
(`printer_panel/config` over the websocket), so nothing about the printer is written into the page or the dashboard.

## Troubleshooting

- "No printer found" when adding the integration: the Creality integration is not set up, or its printer has no print
  status entity yet. Set it up and add Printer Panel again.
- The page says the printer is off: the printer is off or asleep, or Home Assistant cannot reach it. The controls are
  greyed out until it is back.
- The camera is black or says there is no picture: the camera entity of the Creality integration is unavailable, or
  the printer's camera is off. The rest of the page still works.
- A button does nothing: the page shows why under the buttons ("Could not pause: ..."), from the printer or Home
  Assistant.
- No notification: check the phone is ticked under Configure and the event is chosen; the phone's notify service
  (`notify.mobile_app_<phone>`) must exist in Developer tools > Actions.
- Why the notification shows the model, not the camera: the K2's camera is WebRTC, and a still from it comes through
  go2rtc, which can take longer than Home Assistant waits for one; a phone that cannot fetch the picture shows none.
  The slicer's picture is always there while there is a print.
- "Could not reach the printer's Moonraker" from Pause at line: the printer is off, or Moonraker on port 7125 is not
  reachable from Home Assistant. "The printer's Moonraker said no: ..." passes on what Moonraker said.
- No Restart button: 0.2.0 and 0.2.1 had one, but the K2's firmware cannot reboot through Moonraker (it runs as root
  and has no `sudo`), so 0.2.2 took it out. A switched socket on the printer's power does the job instead.
- The Printer item in the sidebar had no icon (nor did HACS's): Home Assistant's frontend asks for a custom icon once,
  when it first draws it, and the scripts that bring the icons can load after the sidebar has drawn. Since 0.2.0 the
  page's script asks again for any sidebar icon left empty once its icon set is there.

## Development

`python -m pytest tests -q` runs the tests of the printer model (entities, the print's name, durations, events, the
notification texts, a G-code file's lines) and of the filament register's rules; `python -m pytest -c tests_ha/pytest.ini
tests_ha -q` sets a printer up in a real Home Assistant and checks the sidebar item, what the page is told, the
notifications, a renamed entity, the options, counting and Pause at line against a stand-in Moonraker, and the filament
register through a print, a restart and the printer off (needs `pytest-homeassistant-custom-component`; on
Windows also stand-ins for `fcntl` and `resource` on the path); `python tests/render_panel.py` draws the page in
headless Chrome from the K2 Plus fixture, presses every control and screenshots it wide and on a phone;
`python tests/render_icons.py` checks the sidebar icon repair against Home Assistant's own icon element;
`python brand/make_brand.py` fetches the brand images.

Creality and the Creality logo are trademarks of Shenzhen Creality 3D Technology Co., Ltd.; the mark is used only to
name the printers this works with. Printer Panel is not made or endorsed by Creality.

MIT licence. Copyright (c) 2026 Mark Christie.
