"""Constants for Printer Panel. Nothing here imports Home Assistant."""

DOMAIN = "printer_panel"
NAME = "Printer Panel"

URL_BASE = "/printer_panel"               # the panel's script and the Creality mark are served from here
PANEL_FILE = "printer-panel.js"
PANEL_ELEMENT = "printer-panel"
PANEL_PATH = "printer"                    # the sidebar item's address: /printer (then /printer-2 for a second printer)
SIDEBAR_ICON = "printer-panel:creality"   # the Creality mark, from the icon set the panel's script registers
DEFAULT_TITLE = "Printer"

SOURCE_DOMAIN = "ha_creality_ws"          # the Creality integration whose entities the panel shows and works

RESTART_SUFFIX = "restart_printer"        # this integration's own entities on the printer's device: <device id>_<suffix>
PAUSE_AT_LINE_SUFFIX = "pause_at_line"

CONF_DEVICE = "device_id"
CONF_TITLE = "title"
CONF_NOTIFY = "notify"                    # notify services to tell: mobile_app_<phone>
CONF_EVENTS = "events"                    # which events: finished, paused, runout, error
DEFAULT_EVENTS = ["finished", "paused", "runout", "error"]
NOT_TARGETS = {"notify", "persistent_notification", "send_message"}
