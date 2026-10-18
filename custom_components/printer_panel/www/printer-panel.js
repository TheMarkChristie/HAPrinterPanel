/*
 * Printer Panel: the Printer page in Home Assistant's sidebar, and the same view as a card (custom:printer-panel-card),
 * for a Creality printer set up with the Creality integration (ha_creality_ws): the live camera, the print's name,
 * progress, time left and finish time, the temperatures with their targets, the CFS's colours, speed and fans, the light,
 * and Pause, Resume and Stop (Stop asks first).
 *
 * The integration (printer_panel) tells the page which entity is which (printer_panel/config), found by their keys, so a
 * renamed entity is still found. The page is drawn once and then only its values change, so the camera keeps playing.
 *
 * Copyright (c) 2026 Mark Christie. MIT licence. Creality and the Creality logo are trademarks of Shenzhen Creality 3D
 * Technology Co., Ltd.; the mark is used only to name the printer this works with.
 */
(function () {
  "use strict";

  // Creality's mark, one path in 24 x 24: the sidebar item's icon (printer-panel:creality) and the page's header
  const MARK = "M1.58 21.73C1.30 21.60 1.12 21.39 1.05 21.13C0.96 20.79 1.03 20.50 1.32 19.98C1.47 19.71 1.68 19.32 1.80 19.10C2.02 18.69 2.87 17.13 3.65 15.70C3.89 15.26 4.18 14.73 4.29 14.52C4.40 14.32 4.77 13.64 5.12 13.01C5.47 12.38 5.75 11.86 5.75 11.85C5.75 11.84 5.93 11.51 6.14 11.11C6.36 10.72 6.77 9.97 7.05 9.45C7.33 8.93 7.65 8.35 7.76 8.17C7.86 7.98 7.95 7.82 7.95 7.81C7.95 7.80 8.18 7.38 8.45 6.88C8.73 6.38 8.95 5.96 8.95 5.95C8.95 5.94 9.04 5.78 9.14 5.59C9.50 4.97 9.82 4.37 10.31 3.46C10.59 2.93 10.88 2.61 11.28 2.42C11.71 2.21 12.11 2.18 12.54 2.32C13.11 2.51 13.40 2.80 13.81 3.57C14.09 4.10 14.29 4.47 14.61 5.04C14.75 5.29 14.96 5.68 15.09 5.92C15.21 6.16 15.42 6.54 15.55 6.77C15.68 7.01 15.93 7.47 16.11 7.80C16.72 8.94 16.64 8.77 17.85 11C18.11 11.47 18.38 11.96 18.45 12.10C18.58 12.33 19.62 14.25 19.96 14.88C20.15 15.22 21.01 16.80 21.24 17.22C21.34 17.40 21.58 17.85 21.78 18.21C21.98 18.58 22.15 18.89 22.15 18.89C22.15 18.90 22.35 19.28 22.60 19.73C23.01 20.47 23.05 20.58 23.05 20.81C23.05 21.27 22.88 21.54 22.48 21.73C22.37 21.78 22.20 21.82 22.11 21.82C21.98 21.82 21.37 21.61 20.78 21.35C20.69 21.31 20.20 21.11 19.68 20.90C18.75 20.53 18.30 20.34 17.57 20.04C17.38 19.96 17.01 19.81 16.75 19.70C16.49 19.60 16.24 19.50 16.19 19.47C16.14 19.45 15.96 19.37 15.79 19.30C15.62 19.24 15.06 19.01 14.55 18.80C13.46 18.35 13.33 18.31 12.68 18.20C11.60 18.01 10.98 18.17 8.37 19.27C8.04 19.40 7.35 19.69 6.83 19.90C5.94 20.26 5.63 20.39 5.05 20.63C4.93 20.68 4.38 20.90 3.83 21.12C3.28 21.35 2.76 21.56 2.67 21.60C2.13 21.85 1.89 21.88 1.58 21.73ZM8.33 15.78C8.52 15.68 9.17 15.32 9.77 14.98C10.37 14.64 10.99 14.32 11.14 14.27C11.56 14.13 12.25 14.09 12.65 14.19C12.98 14.28 13.46 14.49 13.93 14.77C14.06 14.85 14.25 14.96 14.35 15.01C16.19 16.06 16.15 16.04 16.40 15.83C16.62 15.66 16.56 15.46 15.93 14.15C15.60 13.49 15.16 12.58 14.94 12.12C12.45 7.02 12.60 7.32 12.41 7.19C12.18 7.04 11.87 7.04 11.65 7.19C11.47 7.32 11.44 7.36 10.53 9.23C10.17 9.98 9.68 10.98 9.45 11.45C8.44 13.53 7.88 14.68 7.69 15.06C7.51 15.44 7.50 15.49 7.55 15.65C7.60 15.81 7.79 15.97 7.93 15.97C7.96 15.97 8.14 15.89 8.33 15.78Z";
  const ICONSET = "printer-panel";

  // registered at once, so the sidebar finds the icon when it first draws
  window.customIcons = window.customIcons || {};
  if (!window.customIcons[ICONSET]) {
    window.customIcons[ICONSET] = {
      getIcon: async (name) => ({ path: name === "creality" ? MARK : "" }),
      getIconList: async () => [{ name: "creality" }],
    };
  }

  /* Home Assistant's ha-icon asks for a custom icon once, when it is first drawn, and an icon set that is not there yet
   * leaves it empty for good (frontend 2026.9 and 2026.10). Extra scripts load alongside the frontend, so the sidebar
   * can draw first: the Printer item (and HACS's) with no icon. So a sidebar icon left empty whose set is there now is
   * asked again: by way of an MDI icon, which clears the empty state it was left in, then its own. Only sidebar icons,
   * only empty ones, only for sets that now exist; a few times in the first minute, for sets that load after this. */
  const SWAP_ICON = "mdi:blank";
  function repairSidebarIcons() {
    const ha = document.querySelector("home-assistant");
    const main = ha && ha.shadowRoot && ha.shadowRoot.querySelector("home-assistant-main");
    const sidebar = main && main.shadowRoot && main.shadowRoot.querySelector("ha-sidebar");
    if (!sidebar || !sidebar.shadowRoot) return 0;
    let repaired = 0;
    sidebar.shadowRoot.querySelectorAll("ha-icon").forEach((el) => {
      const icon = typeof el.icon === "string" ? el.icon : "";
      const prefix = icon.split(":")[0];
      const known = (window.customIcons && window.customIcons[prefix]) || (window.customIconsets && window.customIconsets[prefix]);
      if (!known || el.__printerPanelRepair || !el.shadowRoot || !el.shadowRoot.querySelector("iron-icon")) return;
      el.__printerPanelRepair = true;
      repaired += 1;
      el.icon = SWAP_ICON;
      Promise.resolve(el.updateComplete).then(() => {
        if (el.icon === SWAP_ICON) el.icon = icon;
      }).finally(() => { el.__printerPanelRepair = false; });
    });
    return repaired;
  }
  [0, 500, 1500, 4000, 10000, 30000, 60000].forEach((ms) => setTimeout(repairSidebarIcons, ms));

  const STR = {
    en: {
      title: "Printer", camera: "Camera", noCamera: "No camera", noPicture: "No picture from the camera yet", preview: "Picture of the print",
      status: {
        printing: "Printing", paused: "Paused", completed: "Finished", stopped: "Stopped", error: "Error", idle: "Ready",
        off: "Off", "self-testing": "Self-test", processing: "Preparing", unavailable: "Off", unknown: "Unknown",
      },
      offline: "The printer is off, or Home Assistant cannot reach it.",
      noPrint: "Nothing printing", lastPrint: "Last print",
      layer: (a, b) => `Layer ${a} of ${b}`, left: "left", doneAt: "done at", finishedAfter: (t) => `Finished after ${t}`,
      printingFor: (t) => `Printing for ${t}`,
      pause: "Pause", resume: "Resume", stop: "Stop", light: "Light",
      stopAsk: "Stop the print?", stopHint: "A stopped print cannot be resumed.", cancel: "Cancel", stopPrint: "Stop the print",
      restart: "Restart", restartAsk: "Restart the printer?", restartPrinter: "Restart printer",
      restartHint: "It switches off and on again: the screen, the camera and the CFS restart, and it is back in a minute or two.",
      restarting: "Restarting the printer: it is back in a minute or two.",
      lineAt: (a, b) => `Line ${a} of ${b}`, pauseAt: "Pause at line", setLine: "Set", cancelLine: "Cancel",
      pausesAt: (n, when) => `Pauses at line ${n}${when ? `, ${when}` : ""}`, inAbout: (t) => `in about ${t}`, soon: "any moment now",
      lineHint: "It pauses about a second after the printer reaches the line.",
      temps: "Temperatures", nozzle: "Nozzle", bed: "Bed", chamber: "Chamber", target: "Target", off2: "off", onW: "On", offW: "Off",
      lower: (w) => `Lower the ${w} target`, raise: (w) => `Raise the ${w} target`, setTarget: (w) => `${w} target`,
      cfs: "CFS", box: (n) => `Box ${n}`, external: "External spool", empty: "Empty", low: "Low", inUse: "In use",
      uses: "Colours in the print file", remaining: (p) => `${p} % left`,
      tune: "Speed and fans", speed: "Speed", slower: "Slower", faster: "Faster",
      modes: [["Silent", 50], ["Standard", 100], ["Sport", 130], ["Ludicrous", 160]],
      fanModel: "Part cooling", fanSide: "Side fan", fanCase: "Case fan", fanOn: (w) => `${w} on or off`, fanLevel: (w) => `${w} speed`,
      failed: (what, why) => `Could not ${what}: ${why}`,
      verbs: { pause: "pause", resume: "resume", stop: "stop", set: "change that", restart: "restart the printer", line: "set the pause" },
      notSetUp: "No printer is set up in Printer Panel yet. Add it under Settings, Devices & services.",
      cantLoad: "The printer's details could not be read; trying again.",
    },
    nb: {
      title: "Skriver", camera: "Kamera", noCamera: "Ikke noe kamera", noPicture: "Ikke noe bilde fra kameraet ennå", preview: "Bilde av utskriften",
      status: {
        printing: "Skriver ut", paused: "Pause", completed: "Ferdig", stopped: "Stoppet", error: "Feil", idle: "Klar",
        off: "Av", "self-testing": "Selvtest", processing: "Forbereder", unavailable: "Av", unknown: "Ukjent",
      },
      offline: "Skriveren er av, eller Home Assistant når den ikke.",
      noPrint: "Ingen utskrift", lastPrint: "Siste utskrift",
      layer: (a, b) => `Lag ${a} av ${b}`, left: "igjen", doneAt: "ferdig", finishedAfter: (t) => `Ferdig etter ${t}`,
      printingFor: (t) => `Har skrevet ut i ${t}`,
      pause: "Pause", resume: "Fortsett", stop: "Stopp", light: "Lys",
      stopAsk: "Stoppe utskriften?", stopHint: "En stoppet utskrift kan ikke fortsettes.", cancel: "Avbryt", stopPrint: "Stopp utskriften",
      restart: "Omstart", restartAsk: "Starte skriveren på nytt?", restartPrinter: "Start skriveren på nytt",
      restartHint: "Den slås av og på igjen: skjermen, kameraet og CFS starter på nytt, og den er tilbake om et minutt eller to.",
      restarting: "Starter skriveren på nytt: den er tilbake om et minutt eller to.",
      lineAt: (a, b) => `Linje ${a} av ${b}`, pauseAt: "Pause ved linje", setLine: "Sett", cancelLine: "Avbryt",
      pausesAt: (n, when) => `Pauser ved linje ${n}${when ? `, ${when}` : ""}`, inAbout: (t) => `om omtrent ${t}`, soon: "når som helst nå",
      lineHint: "Den pauser omtrent et sekund etter at skriveren når linjen.",
      temps: "Temperaturer", nozzle: "Dyse", bed: "Plate", chamber: "Kammer", target: "Mål", off2: "av", onW: "På", offW: "Av",
      lower: (w) => `Senk målet for ${w.toLowerCase()}`, raise: (w) => `Øk målet for ${w.toLowerCase()}`, setTarget: (w) => `Mål for ${w.toLowerCase()}`,
      cfs: "CFS", box: (n) => `Boks ${n}`, external: "Ekstern spole", empty: "Tom", low: "Lite igjen", inUse: "I bruk",
      uses: "Farger i utskriftsfilen", remaining: (p) => `${p} % igjen`,
      tune: "Fart og vifter", speed: "Fart", slower: "Saktere", faster: "Raskere",
      modes: [["Stille", 50], ["Standard", 100], ["Sport", 130], ["Ludicrous", 160]],
      fanModel: "Delkjøling", fanSide: "Sidevifte", fanCase: "Kabinettvifte", fanOn: (w) => `${w} av eller på`, fanLevel: (w) => `Fart for ${w.toLowerCase()}`,
      failed: (what, why) => `Kunne ikke ${what}: ${why}`,
      verbs: { pause: "sette på pause", resume: "fortsette", stop: "stoppe", set: "endre det", restart: "starte skriveren på nytt", line: "sette pausen" },
      notSetUp: "Ingen skriver er satt opp i Printer Panel ennå. Legg den til under Innstillinger, Enheter og tjenester.",
      cantLoad: "Kunne ikke lese skriverens detaljer; prøver igjen.",
    },
  };

  const SLICER_SUFFIX = /(?:_[A-Z][A-Z0-9+-]*)+_(?:\d+d)?(?:\d+h)?\d+m(?:\d+s)?$/;
  const GCODE_EXT = /\.(?:gcode|gco|g|bgcode)$/i;
  const ACTIVE = ["printing", "processing", "paused", "self-testing"];

  /** "/mnt/UDISK/printer_data/gcodes/GTA 6 stand - Warden of Bacon_PLA_9h1m52s.gcode" -> "GTA 6 stand - Warden of Bacon" */
  function printName(path) {
    if (!path) return null;
    let name = String(path).trim().split(/[\\/]/).pop();
    name = name.replace(GCODE_EXT, "").replace(SLICER_SUFFIX, "");
    name = name.replace(/^[\s_-]+|[\s_-]+$/g, "");
    return name || null;
  }
  /** the active slot sensor's state -> the slot's label: "box_1_slot_2" (slots from 1) -> "1B", "external" -> "Ext";
   *  older versions of the Creality integration said "Box 1 Slot 2" and "External" */
  function slotLabel(state) {
    const v = String(state == null ? "" : state);
    const m = /box\D*(\d+)\D*slot\D*(\d+)/i.exec(v);
    if (m) { const n = Number(m[2]); return n >= 1 && n <= 26 ? `${Number(m[1])}${String.fromCharCode(64 + n)}` : null; }
    return /^ext/i.test(v) ? "Ext" : null;
  }
  function duration(seconds, lang) {
    const total = Math.max(0, Math.floor(Number(seconds)));
    if (!Number.isFinite(total)) return "";
    const hours = Math.floor(total / 3600), minutes = Math.floor((total % 3600) / 60);
    const h = lang === "nb" ? "t" : "h";
    if (hours && minutes) return `${hours} ${h} ${minutes} min`;
    if (hours) return `${hours} ${h}`;
    if (minutes) return `${minutes} min`;
    return lang === "nb" ? "under ett minutt" : "under a minute";
  }
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const num = (v) => { if (v === null || v === undefined || v === "") return null; const n = Number(v); return Number.isFinite(n) ? n : null; };
  /** "#ff37af", "#F3BBCAFF" (with alpha) or "ff37af" -> "#ff37af"; anything else -> null */
  const colour = (v) => { const m = /^#?([0-9a-f]{6})(?:[0-9a-f]{2})?$/i.exec(String(v == null ? "" : v).trim()); return m ? `#${m[1].toLowerCase()}` : null; };
  const markSvg = (cls) => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true"><path fill-rule="evenodd" d="${MARK}"></path></svg>`;

  const STYLE = `
    :host { display: block; container-type: inline-size; color: var(--primary-text-color); }
    [hidden] { display: none !important; }
    .page { min-height: 100%; background: var(--primary-background-color); }
    :host(.card) .page { background: none; }
    .bar { display: flex; align-items: center; gap: 12px; height: var(--header-height, 56px); padding: 0 12px;
           background: var(--app-header-background-color); color: var(--app-header-text-color, #fff);
           border-bottom: var(--app-header-border-bottom, none); box-sizing: border-box; }
    .bar .title { font-size: 20px; font-weight: 400; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bar .mark { width: 24px; height: 24px; fill: currentColor; flex: 0 0 24px; }
    .grid { display: grid; gap: 16px; padding: 16px; grid-template-columns: minmax(0, 1.5fr) minmax(300px, 1fr); align-items: start;
            max-width: 1500px; margin: 0 auto; box-sizing: border-box; }
    :host(.card) .grid { padding: 0; }
    @container (max-width: 860px) { .grid { grid-template-columns: minmax(0, 1fr); padding: 12px; } :host(.card) .grid { padding: 0; } }
    .col { display: grid; gap: 16px; min-width: 0; }
    ha-card { display: block; padding: 16px; box-sizing: border-box; }
    h2 { font-size: 16px; font-weight: 500; margin: 0 0 12px; display: flex; align-items: center; gap: 8px; }
    h2 .aside { margin-left: auto; font-size: 13px; font-weight: 400; color: var(--secondary-text-color); }
    .camwrap { min-width: 0; }
    .camwrap .fallback { width: 100%; display: block; border-radius: var(--ha-card-border-radius, 12px); background: #000; aspect-ratio: 16 / 9; object-fit: contain; }
    .camwrap .nocam { aspect-ratio: 16 / 9; display: grid; place-items: center; color: var(--secondary-text-color);
                      background: var(--secondary-background-color); border-radius: var(--ha-card-border-radius, 12px); }
    .cardmark { width: 22px; height: 22px; fill: #6fb23a; flex: 0 0 22px; }
    .job .head { display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 12px; align-items: center; }
    .job .head.nopic { grid-template-columns: minmax(0, 1fr); }
    .preview { width: 72px; height: 72px; border-radius: 10px; object-fit: contain; background: var(--secondary-background-color); }
    .name { font-size: 18px; font-weight: 500; overflow-wrap: anywhere; }
    .sub { color: var(--secondary-text-color); font-size: 14px; margin-top: 2px; }
    .chip { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 13px; font-weight: 500; white-space: nowrap;
            color: var(--chip, var(--primary-color)); background: color-mix(in srgb, var(--chip, var(--primary-color)) 16%, transparent); }
    .bar .chip { color: var(--app-header-text-color, #fff); background: color-mix(in srgb, var(--chip, #fff) 45%, transparent); }
    .progress { display: flex; align-items: center; gap: 10px; margin: 14px 0 6px; }
    .track { flex: 1; height: 10px; border-radius: 5px; background: var(--divider-color); overflow: hidden; }
    .track i { display: block; height: 100%; width: 0; background: var(--primary-color); border-radius: 5px; transition: width 0.6s; }
    .pct { font-variant-numeric: tabular-nums; font-weight: 500; min-width: 3.5em; text-align: right; }
    .times { display: flex; flex-wrap: wrap; gap: 4px 16px; color: var(--secondary-text-color); font-size: 14px; }
    .times b { color: var(--primary-text-color); font-weight: 500; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
    .btn { font: inherit; font-size: 14px; display: inline-flex; align-items: center; gap: 6px; padding: 0 16px; min-height: 44px; border-radius: 12px;
           border: 1px solid var(--divider-color); background: var(--secondary-background-color); color: var(--primary-text-color); cursor: pointer; }
    .btn ha-icon { --mdc-icon-size: 20px; }
    .btn.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
    .btn.danger { color: var(--error-color, #db4437); border-color: var(--error-color, #db4437); background: none; }
    .btn[aria-pressed="true"] { background: color-mix(in srgb, var(--warning-color, #ffa600) 25%, transparent); border-color: var(--warning-color, #ffa600); }
    .btn:disabled { opacity: 0.45; cursor: default; }
    .btn:focus-visible, .step:focus-visible, input:focus-visible, .mode:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
    .msg { min-height: 0; margin-top: 8px; font-size: 13px; color: var(--error-color, #db4437); }
    .msg.info { color: var(--secondary-text-color); }
    .msg:empty { display: none; }
    .btn.small { min-height: 36px; padding: 0 12px; }
    .line { display: grid; gap: 6px; margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--divider-color); }
    .linepos { font-size: 14px; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
    .lineset { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
    .lineset label { display: flex; align-items: center; gap: 8px; font-size: 14px; }
    .lineinput { font: inherit; width: 9em; height: 36px; box-sizing: border-box; padding: 0 8px; border-radius: 10px;
                 border: 1px solid var(--divider-color); background: var(--card-background-color, transparent); color: var(--primary-text-color); }
    .lineinput:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
    .linestate { font-size: 14px; font-weight: 500; color: var(--warning-color, #ffa600); font-variant-numeric: tabular-nums; }
    .linehint { font-size: 12px; color: var(--secondary-text-color); }
    .linepos:empty, .linestate:empty { display: none; }
    .offline { margin-top: 12px; padding: 10px 12px; border-radius: 10px; font-size: 14px;
               background: color-mix(in srgb, var(--warning-color, #ffa600) 14%, transparent); }
    .offline:empty { display: none; }
    .row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 10px; padding: 8px 0;
           border-top: 1px solid var(--divider-color); }
    .row:first-of-type { border-top: none; }
    .row .what { font-weight: 500; }
    .row .now { font-variant-numeric: tabular-nums; font-size: 18px; font-weight: 500; text-align: right; min-width: 3.5em; }
    .stepper { display: flex; align-items: center; gap: 4px; }
    .step { font: inherit; width: 40px; height: 40px; border-radius: 10px; border: 1px solid var(--divider-color); cursor: pointer;
            background: var(--secondary-background-color); color: var(--primary-text-color); font-size: 18px; line-height: 1; }
    .step:disabled { opacity: 0.45; cursor: default; }
    .stepper input { font: inherit; width: 64px; height: 40px; box-sizing: border-box; text-align: center; border-radius: 10px;
                     border: 1px solid var(--divider-color); background: var(--card-background-color, transparent); color: var(--primary-text-color); }
    .stepper .unit { color: var(--secondary-text-color); font-size: 13px; min-width: 1.6em; }
    .modes { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 6px; }
    .mode { font: inherit; font-size: 13px; padding: 6px 12px; border-radius: 999px; border: 1px solid var(--divider-color); cursor: pointer;
            background: none; color: var(--primary-text-color); }
    .mode[aria-pressed="true"] { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
    .fan { display: grid; grid-template-columns: minmax(0, 7em) minmax(0, 1fr) 3.2em auto; align-items: center; gap: 10px; padding: 8px 0;
           border-top: 1px solid var(--divider-color); }
    .fan input[type=range] { width: 100%; accent-color: var(--primary-color); }
    .fan .val { text-align: right; font-variant-numeric: tabular-nums; }
    .switch { font: inherit; font-size: 13px; min-width: 52px; height: 32px; border-radius: 16px; border: 1px solid var(--divider-color);
              background: var(--secondary-background-color); color: var(--secondary-text-color); cursor: pointer; }
    .switch[aria-pressed="true"] { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
    .slots { display: grid; gap: 8px; }
    .slot { display: grid; grid-template-columns: 36px 2.4em minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 6px 8px;
            border-radius: 10px; }
    .slot.active { background: color-mix(in srgb, var(--primary-color) 12%, transparent); }
    .swatch { width: 32px; height: 32px; border-radius: 50%; border: 2px solid var(--divider-color); box-sizing: border-box; }
    .slot .lbl { font-weight: 600; font-variant-numeric: tabular-nums; }
    .slot .mat { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .slot .mat small { display: block; color: var(--secondary-text-color); font-size: 12px; }
    .slot .left { text-align: right; font-variant-numeric: tabular-nums; font-size: 14px; white-space: nowrap; }
    .slot .left .mini { display: block; width: 56px; height: 4px; border-radius: 2px; background: var(--divider-color); margin-top: 4px; overflow: hidden; }
    .slot .left .mini i { display: block; height: 100%; background: var(--primary-color); }
    .slot.low .left { color: var(--warning-color, #ffa600); font-weight: 500; }
    .slot.low .left .mini i { background: var(--warning-color, #ffa600); }
    .tag { font-size: 11px; font-weight: 600; padding: 1px 6px; border-radius: 6px; margin-left: 6px; vertical-align: 1px;
           background: var(--primary-color); color: var(--text-primary-color, #fff); }
    .boxhead { display: flex; justify-content: space-between; color: var(--secondary-text-color); font-size: 13px; margin: 12px 0 4px; }
    .boxhead:first-child { margin-top: 0; }
    .uses { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 12px; color: var(--secondary-text-color); font-size: 13px; }
    .uses .dot { width: 20px; height: 20px; border-radius: 50%; border: 2px solid var(--divider-color); box-sizing: border-box; }
    .note { color: var(--secondary-text-color); padding: 24px 16px; }
    dialog { border: none; border-radius: 16px; padding: 20px; max-width: min(420px, 90vw); background: var(--card-background-color, #fff);
             color: var(--primary-text-color); box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4); }
    dialog::backdrop { background: rgba(0, 0, 0, 0.45); }
    dialog h3 { margin: 0 0 8px; font-size: 18px; font-weight: 500; }
    dialog p { margin: 0 0 18px; color: var(--secondary-text-color); }
    dialog .actions { justify-content: flex-end; }
  `;

  class PrinterView extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._cfg = null;
      this._built = false;
      this._loading = false;
      this._pending = null;          // a print button pressed, until the status moves on (or 15 s)
      this._slotsKey = null;
      this._msgTimer = null;
    }

    get _fullPage() { return false; }

    set hass(hass) {
      this._hass = hass;
      const l = String((hass.locale && hass.locale.language) || hass.language || "en").toLowerCase();
      this._lang = /^(nb|nn|no)\b/.test(l) ? "nb" : "en";
      if (!this._cfg) {
        if (!this._loading && !this._retry) this._load();
        return;
      }
      if (this._built) this._update();
    }

    get _s() { return STR[this._lang || "en"]; }

    async _load() {
      this._loading = true;
      try {
        const msg = { type: "printer_panel/config" };
        if (this._entryId) msg.entry_id = this._entryId;
        this._cfg = await this._hass.callWS(msg);
        this._build();
        this._update();
      } catch (err) {
        const notSetUp = err && err.code === "not_found";
        this._note(notSetUp ? this._s.notSetUp : this._s.cantLoad);
        this._retry = setTimeout(() => { this._retry = null; if (this._hass) this._load(); }, notSetUp ? 60000 : 20000);
      } finally {
        this._loading = false;
      }
    }

    _note(text) {
      this.shadowRoot.innerHTML = `<style>${STYLE}</style><div class="page">${this._fullPage ? this._barHtml() : ""}<div class="note">${esc(text)}</div></div>`;
      this._placeMenu();
    }

    _barHtml() {
      return `<div class="bar"><span class="menu"></span>${markSvg("mark")}<span class="title"></span><span class="chip status" role="status"></span></div>`;
    }

    _placeMenu() {
      const slot = this.shadowRoot.querySelector(".bar .menu");
      if (!slot || !this._hass) return;
      if (!this._menu) this._menu = document.createElement("ha-menu-button");
      this._menu.hass = this._hass;
      this._menu.narrow = !!this._narrow;
      if (this._menu.parentNode !== slot) slot.appendChild(this._menu);
    }

    _build() {
      const s = this._s, e = this._cfg.entities || {};
      const has = (k) => !!e[k];
      const temp = (k, label) => has(k) || has(`${k}_target`) ? `
        <div class="row" data-temp="${k}">
          <span class="what">${esc(label)}</span><span class="now">-</span>
          ${has(`${k}_target`) ? `<span class="stepper">
            <button class="step" data-step="-5" aria-label="${esc(s.lower(label))}">−</button>
            <input type="number" inputmode="numeric" aria-label="${esc(s.setTarget(label))}">
            <button class="step" data-step="5" aria-label="${esc(s.raise(label))}">+</button><span class="unit">°C</span></span>` : "<span></span>"}
        </div>` : "";
      const fan = (k, label) => has(k) ? `
        <div class="fan" data-fan="${k}"><span>${esc(label)}</span>
          <input type="range" min="0" max="100" step="5" aria-label="${esc(s.fanLevel(label))}"><span class="val">-</span>
          <button class="switch" aria-label="${esc(s.fanOn(label))}" aria-pressed="false">${esc(s.offW)}</button></div>` : "";
      this.shadowRoot.innerHTML = `<style>${STYLE}</style>
        <div class="page">
          ${this._fullPage ? this._barHtml() : ""}
          <div class="grid">
            <div class="col">
              <div class="camwrap"></div>
            </div>
            <div class="col">
              <ha-card class="job">
                ${this._fullPage ? "" : `<h2>${markSvg("cardmark")}<span class="ctitle"></span><span class="aside"><span class="chip status" role="status"></span></span></h2>`}
                <div class="head"><img class="preview" alt="${esc(s.preview)}" hidden><div><div class="name"></div><div class="sub"></div></div></div>
                <div class="progress"><div class="track" role="progressbar" aria-valuemin="0" aria-valuemax="100"><i></i></div><span class="pct"></span></div>
                <div class="times"></div>
                <div class="actions">
                  ${has("pause") ? `<button class="btn primary" data-act="pause"><ha-icon icon="mdi:pause"></ha-icon>${esc(s.pause)}</button>` : ""}
                  ${has("resume") ? `<button class="btn primary" data-act="resume"><ha-icon icon="mdi:play"></ha-icon>${esc(s.resume)}</button>` : ""}
                  ${has("stop") ? `<button class="btn danger" data-act="stop"><ha-icon icon="mdi:stop"></ha-icon>${esc(s.stop)}</button>` : ""}
                  ${has("light") ? `<button class="btn" data-act="light" aria-pressed="false"><ha-icon icon="mdi:lightbulb-outline"></ha-icon>${esc(s.light)}</button>` : ""}
                  ${has("restart") ? `<button class="btn" data-act="restart" hidden><ha-icon icon="mdi:restart"></ha-icon>${esc(s.restart)}</button>` : ""}
                </div>
                ${has("pause_at_line") ? `<div class="line" hidden>
                  <div class="linepos"></div>
                  <div class="lineset"><label>${esc(s.pauseAt)}<input class="lineinput" type="number" inputmode="numeric" min="1" step="1"></label>
                    <button class="btn small" data-line="set">${esc(s.setLine)}</button>
                    <button class="btn small" data-line="cancel" hidden>${esc(s.cancelLine)}</button></div>
                  <div class="linestate" role="status"></div>
                  <div class="linehint">${esc(s.lineHint)}</div>
                </div>` : ""}
                <div class="msg" role="status" aria-live="polite"></div>
                <div class="offline"></div>
              </ha-card>
              ${has("nozzle") || has("bed") || has("chamber") ? `<ha-card class="temps"><h2>${esc(s.temps)}</h2>
                ${temp("nozzle", s.nozzle)}${temp("bed", s.bed)}${temp("chamber", s.chamber)}</ha-card>` : ""}
              ${(this._cfg.boxes || []).length || this._cfg.external ? `<ha-card class="cfs"><h2>${esc(s.cfs)}</h2><div class="slots"></div><div class="uses" hidden></div></ha-card>` : ""}
              ${has("speed") || has("fan_model") || has("fan_side") || has("fan_case") ? `<ha-card class="tune"><h2>${esc(s.tune)}</h2>
                ${has("speed") ? `<div class="row" data-speed><span class="what">${esc(s.speed)}</span><span class="now">-</span>
                  <span class="stepper"><button class="step" data-sstep="-10" aria-label="${esc(s.slower)}">−</button>
                  <input type="number" inputmode="numeric" aria-label="${esc(s.speed)}">
                  <button class="step" data-sstep="10" aria-label="${esc(s.faster)}">+</button><span class="unit">%</span></span></div>
                  <div class="modes">${s.modes.map(([label, pct]) => `<button class="mode" data-mode="${pct}" aria-pressed="false">${esc(label)} ${pct} %</button>`).join("")}</div>` : ""}
                ${fan("fan_model", s.fanModel)}${fan("fan_side", s.fanSide)}${fan("fan_case", s.fanCase)}</ha-card>` : ""}
            </div>
          </div>
          <dialog class="confirm" aria-labelledby="dlg-title">
            <h3 id="dlg-title"></h3><p></p>
            <div class="actions"><button class="btn" data-dlg="cancel" autofocus>${esc(s.cancel)}</button>
              <button class="btn danger" data-dlg="go"><ha-icon></ha-icon><span></span></button></div>
          </dialog>
        </div>`;
      this._placeMenu();
      this._wire();
      this._camera();
      this._built = true;
      this._slotsKey = null;
    }

    _wire() {
      const root = this.shadowRoot;
      root.addEventListener("click", (ev) => {
        const t = ev.target.closest && ev.target.closest("button");
        if (!t) return;
        if (t.dataset.act) this._act(t.dataset.act);
        else if (t.dataset.dlg) this._dialog(t.dataset.dlg);
        else if (t.dataset.step) this._nudgeTemp(t.closest("[data-temp]").dataset.temp, Number(t.dataset.step));
        else if (t.dataset.sstep) this._nudgeSpeed(Number(t.dataset.sstep));
        else if (t.dataset.mode) this._setNumber("speed", Number(t.dataset.mode));
        else if (t.dataset.line === "set") this._setLine();
        else if (t.dataset.line === "cancel") this._call("number", "set_value", { entity_id: this._cfg.entities.pause_at_line, value: 0 }, "line");
        else if (t.classList.contains("switch")) this._call("fan", "toggle", { entity_id: this._cfg.entities[t.closest("[data-fan]").dataset.fan] }, "set");
      });
      root.addEventListener("change", (ev) => {
        const t = ev.target;
        if (t.matches("[data-temp] input")) this._setNumber(`${t.closest("[data-temp]").dataset.temp}_target`, Number(t.value));
        else if (t.matches("[data-speed] input")) this._setNumber("speed", Number(t.value));
        else if (t.matches("[data-fan] input[type=range]")) {
          const entity = this._cfg.entities[t.closest("[data-fan]").dataset.fan];
          const pct = Number(t.value);
          if (pct <= 0) this._call("fan", "turn_off", { entity_id: entity }, "set");
          else this._call("fan", "set_percentage", { entity_id: entity, percentage: pct }, "set");
        }
      });
      root.addEventListener("keydown", (ev) => {
        if (ev.key !== "Enter" || !ev.target.matches) return;
        if (ev.target.matches(".lineinput")) { ev.preventDefault(); this._setLine(); } else if (ev.target.matches(".stepper input")) ev.target.blur();
      });
      const dlg = root.querySelector("dialog.confirm");
      if (dlg) dlg.addEventListener("close", () => { const opener = root.querySelector(`[data-act="${this._asking}"]`); if (opener && !opener.hidden) opener.focus(); });
      const pic = root.querySelector(".preview");
      if (pic) {
        pic.addEventListener("load", () => { pic.dataset.ok = "1"; this._showPic(pic); });
        pic.addEventListener("error", () => { pic.dataset.ok = ""; this._showPic(pic); });
      }
    }

    _showPic(img) {
      const on = !!img.dataset.want && !!img.dataset.ok;
      img.hidden = !on;
      img.parentElement.classList.toggle("nopic", !on);
    }

    /* the live camera: Home Assistant's own picture card in live view, which plays whatever stream the camera offers;
       without the card helpers (or a camera), a snapshot every ten seconds or a note */
    async _camera() {
      const box = this.shadowRoot.querySelector(".camwrap");
      const cam = this._cfg.entities.camera;
      if (!box) return;
      if (!cam) { box.innerHTML = `<div class="nocam">${esc(this._s.noCamera)}</div>`; return; }
      try {
        if (!window.loadCardHelpers) throw new Error("no card helpers");
        const helpers = await window.loadCardHelpers();
        const card = await helpers.createCardElement({ type: "picture-entity", entity: cam, camera_view: "live", show_name: false,
                                                      show_state: false, aspect_ratio: "16:9", fit_mode: "contain" });
        card.hass = this._hass;
        this._cam = card;
        box.replaceChildren(card);
      } catch (err) {
        // the picture shows once one has loaded; until then, or when the camera stops answering, a note
        const img = document.createElement("img");
        img.className = "fallback";
        img.alt = this._s.camera;
        img.hidden = true;
        const note = document.createElement("div");
        note.className = "nocam";
        note.textContent = this._s.noPicture;
        img.addEventListener("load", () => { img.hidden = false; note.hidden = true; });
        img.addEventListener("error", () => { img.hidden = true; note.hidden = false; });
        this._camImg = img;
        box.replaceChildren(img, note);
        this._snapshot();
        this._snapTimer = setInterval(() => this._snapshot(), 10000);
      }
    }

    _snapshot() {
      const st = this._hass && this._hass.states[this._cfg.entities.camera];
      if (this._camImg && st && st.attributes.entity_picture) {
        this._camImg.src = this._hass.hassUrl(st.attributes.entity_picture) + `&t=${Date.now()}`;
      }
    }

    disconnectedCallback() {
      if (this._snapTimer) { clearInterval(this._snapTimer); this._snapTimer = null; }
      this._stopPos();
    }

    connectedCallback() {
      if (this._camImg && !this._snapTimer) this._snapTimer = setInterval(() => this._snapshot(), 10000);
      if (this._built && this._hass) this._update();
    }

    _st(what) {
      const id = this._cfg.entities[what];
      return id ? this._hass.states[id] : undefined;
    }

    _text(el, value) {
      if (el && el.textContent !== value) el.textContent = value;
    }

    _clock(date) {
      const loc = this._hass.locale || {};
      const tz = loc.time_zone === "server" && this._hass.config ? this._hass.config.time_zone : undefined;
      const lang = this._lang === "nb" ? "nb-NO" : (loc.language || "en-GB");
      const hour12 = loc.time_format === "12" ? true : loc.time_format === "24" ? false : undefined;
      const time = new Intl.DateTimeFormat(lang, { hour: "2-digit", minute: "2-digit", hour12, timeZone: tz }).format(date);
      const day = (d) => new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: tz }).format(d);
      if (day(date) === day(new Date())) return time;
      return `${new Intl.DateTimeFormat(lang, { weekday: "short", timeZone: tz }).format(date)} ${time}`;
    }

    _update() {
      const s = this._s, root = this.shadowRoot, h = this._hass;
      if (!root.querySelector(".grid")) return;
      const status = this._st("status");
      const state = status ? status.state : "unavailable";
      const online = !!status && !["unavailable", "unknown", "off"].includes(state);
      const active = ACTIVE.includes(state);
      if (this._pending && (this._pending.from !== state || Date.now() > this._pending.until)) this._pending = null;

      // the title, the status
      root.querySelectorAll(".status").forEach((chip) => {
        this._text(chip, s.status[state] || state);
        const tone = { printing: "var(--primary-color)", processing: "var(--primary-color)", "self-testing": "var(--primary-color)",
                       paused: "var(--warning-color, #ffa600)", completed: "var(--success-color, #43a047)",
                       error: "var(--error-color, #db4437)", stopped: "var(--secondary-text-color)" }[state] || "var(--disabled-text-color, #9e9e9e)";
        chip.style.setProperty("--chip", tone);
      });
      this._text(root.querySelector(".bar .title"), this._cfg.title || s.title);
      this._text(root.querySelector(".ctitle"), this._cfg.title || s.title);

      // the print
      const material = this._st("material");
      const file = (status && status.attributes.file) || (material && material.attributes.gcode_file);
      const name = printName(file);
      const pct = num(this._st("progress") && this._st("progress").state) ?? num(status && status.attributes.progress);
      const left = num(this._st("time_left") && this._st("time_left").state) ?? num(status && status.attributes.left_time_s);
      const job = num(this._st("job_time") && this._st("job_time").state) ?? num(status && status.attributes.job_time_s);
      const layer = num(this._st("layer") && this._st("layer").state), layers = num(this._st("layers") && this._st("layers").state);
      const finished = state === "completed";
      this._text(root.querySelector(".name"), name ? (active || finished ? name : `${s.lastPrint}: ${name}`) : s.noPrint);
      this._text(root.querySelector(".sub"), active && layer != null && layers ? s.layer(layer, layers) : "");
      const shown = active || finished;
      const track = root.querySelector(".track");
      const progress = root.querySelector(".progress");
      if (progress) progress.hidden = !shown || pct == null;
      if (track && pct != null) {
        track.firstElementChild.style.width = `${Math.max(0, Math.min(100, finished ? 100 : pct))}%`;
        track.setAttribute("aria-valuenow", String(finished ? 100 : pct));
      }
      this._text(root.querySelector(".pct"), pct != null ? `${finished ? 100 : Math.round(pct)} %` : "");
      const times = root.querySelector(".times");
      let html = "";
      if (active && left != null && left > 0) {
        const done = new Date(Date.now() + left * 1000);
        html = `<span><b>${esc(duration(left, this._lang))}</b> ${esc(s.left)}</span><span>${esc(s.doneAt)} <b>${esc(this._clock(done))}</b></span>`;
      } else if (active && job != null) {
        html = `<span>${esc(s.printingFor(duration(job, this._lang)))}</span>`;
      } else if (finished && job != null) {
        html = `<span>${esc(s.finishedAfter(duration(job, this._lang)))}</span>`;
      }
      if (times && times.innerHTML !== html) times.innerHTML = html;

      // the picture of the model: shown once it has loaded (a print without one leaves the name the whole width); the
      // image's state is when it last changed, added so a new print's picture is fetched, not taken from the cache
      const preview = this._st("preview");
      const img = root.querySelector(".preview");
      if (img) {
        const pic = preview && preview.state !== "unavailable" && preview.attributes.entity_picture;
        const src = pic && (active || finished) ? `${h.hassUrl(pic)}${pic.includes("?") ? "&" : "?"}v=${encodeURIComponent(preview.state)}` : "";
        if (src && img.dataset.src !== src) { img.dataset.src = src; img.src = src; }
        img.dataset.want = src ? "1" : "";
        this._showPic(img);
      }

      // the buttons
      const pend = !!this._pending;
      const show = (act, visible, enabled) => {
        const b = root.querySelector(`[data-act="${act}"]`);
        if (!b) return;
        b.hidden = !visible;
        b.disabled = !enabled;
      };
      show("pause", ["printing", "processing"].includes(state), online && !pend);
      show("resume", state === "paused", online && !pend);
      show("stop", active, online && !pend);
      const light = this._st("light");
      const lightBtn = root.querySelector('[data-act="light"]');
      if (lightBtn) {
        lightBtn.hidden = false;
        lightBtn.disabled = !light || light.state === "unavailable";
        lightBtn.setAttribute("aria-pressed", String(!!light && light.state === "on"));
        const icon = lightBtn.querySelector("ha-icon");
        if (icon) icon.setAttribute("icon", light && light.state === "on" ? "mdi:lightbulb-on" : "mdi:lightbulb-outline");
      }
      // Restart: not while a print is under way (Mark: hidden while printing); kept usable while the printer is out of
      // reach, as a restart is how it comes back
      const restartBtn = root.querySelector('[data-act="restart"]');
      if (restartBtn) restartBtn.hidden = active;
      this._text(root.querySelector(".offline"), online ? "" : s.offline);

      // the pause at a line, and where the printer is in the file (asked every few seconds while a print is under way)
      this._lineUpdate(active);
      if (active && this.isConnected && this._cfg.entities.pause_at_line) this._startPos(); else this._stopPos();

      // temperatures
      root.querySelectorAll("[data-temp]").forEach((row) => {
        const k = row.dataset.temp;
        const now = num(this._st(k) && this._st(k).state);
        this._text(row.querySelector(".now"), now != null ? `${Math.round(now)}°` : "-");
        const target = this._st(`${k}_target`);
        const input = row.querySelector("input");
        if (input && target) {
          const value = num(target.state);
          input.min = String(num(target.attributes.min) ?? 0);
          input.max = String(num(target.attributes.max) ?? 300);
          if (root.activeElement !== input && value != null && input.value !== String(Math.round(value))) input.value = String(Math.round(value));
          input.disabled = !online || target.state === "unavailable";
          row.querySelectorAll(".step").forEach((b) => { b.disabled = input.disabled; });
          input.title = value === 0 ? s.off2 : "";
        }
      });

      // speed and fans
      const speedRow = root.querySelector("[data-speed]");
      if (speedRow) {
        const speed = this._st("speed");
        const value = num(speed && speed.state);
        this._text(speedRow.querySelector(".now"), value != null ? `${Math.round(value)} %` : "-");
        const input = speedRow.querySelector("input");
        if (speed) {
          input.min = String(num(speed.attributes.min) ?? 1);
          input.max = String(num(speed.attributes.max) ?? 200);
        }
        if (root.activeElement !== input && value != null && input.value !== String(Math.round(value))) input.value = String(Math.round(value));
        const off = !online || !speed || speed.state === "unavailable";
        input.disabled = off;
        speedRow.querySelectorAll(".step").forEach((b) => { b.disabled = off; });
        root.querySelectorAll(".mode").forEach((b) => {
          b.disabled = off;
          b.setAttribute("aria-pressed", String(value != null && Math.round(value) === Number(b.dataset.mode)));
        });
      }
      root.querySelectorAll("[data-fan]").forEach((row) => {
        const fan = this._st(row.dataset.fan);
        const on = !!fan && fan.state === "on";
        const pctFan = on ? (num(fan.attributes.percentage) ?? 100) : 0;
        const range = row.querySelector("input[type=range]");
        if (root.activeElement !== range && range.value !== String(pctFan)) range.value = String(pctFan);
        this._text(row.querySelector(".val"), fan && fan.state !== "unavailable" ? `${Math.round(pctFan)} %` : "-");
        const sw = row.querySelector(".switch");
        sw.setAttribute("aria-pressed", String(on));
        this._text(sw, on ? s.onW : s.offW);
        const off = !online || !fan || fan.state === "unavailable";
        range.disabled = off;
        sw.disabled = off;
      });

      this._cfs();
      if (this._cam) this._cam.hass = h;
      if (this._menu) { this._menu.hass = h; this._menu.narrow = !!this._narrow; }
    }

    /* the CFS: each box's slots, then the external spool, then the colours this print needs */
    _cfs() {
      const root = this.shadowRoot, s = this._s;
      const list = root.querySelector(".cfs .slots");
      if (!list) return;
      const rows = [];
      for (const box of this._cfg.boxes || []) rows.push({ head: box }, ...box.slots.map((slot) => ({ slot })));
      if (this._cfg.external) rows.push({ head: { external: true } }, { slot: this._cfg.external });
      const key = JSON.stringify(rows);
      if (key !== this._slotsKey) {
        this._slotsKey = key;
        list.innerHTML = rows.map((r) => r.head
          ? `<div class="boxhead"><span>${esc(r.head.external ? s.external : s.box(r.head.box))}</span><span class="env" data-box="${r.head.external ? "" : r.head.box}"></span></div>`
          : `<div class="slot" data-slot="${esc(r.slot.label)}"><span class="swatch"></span><span class="lbl">${esc(r.slot.label === "Ext" ? "" : r.slot.label)}</span>
              <span class="mat"></span><span class="left"></span></div>`).join("");
      }
      const activeSlot = this._st("active_slot");
      const activeLabel = activeSlot ? slotLabel(activeSlot.state) : null;
      for (const box of this._cfg.boxes || []) {
        const env = list.querySelector(`.env[data-box="${box.box}"]`);
        if (env) {
          const t = box.temperature && this._hass.states[box.temperature], hu = box.humidity && this._hass.states[box.humidity];
          const parts = [];
          if (t && num(t.state) != null) parts.push(`${Math.round(num(t.state))} °C`);
          if (hu && num(hu.state) != null) parts.push(`${Math.round(num(hu.state))} %`);
          this._text(env, parts.join(" · "));
        }
      }
      const all = [...(this._cfg.boxes || []).flatMap((b) => b.slots), ...(this._cfg.external ? [this._cfg.external] : [])];
      for (const slot of all) {
        const row = list.querySelector(`.slot[data-slot="${window.CSS && window.CSS.escape ? window.CSS.escape(slot.label) : slot.label}"]`);
        if (!row) continue;
        const c = slot.color && this._hass.states[slot.color];
        const f = slot.filament && this._hass.states[slot.filament];
        const r = slot.remaining && this._hass.states[slot.remaining];
        const attrs = (c && c.attributes) || (f && f.attributes) || {};
        const hex = colour(attrs.color_hex) || colour(c && c.state);
        const filament = f && !["unknown", "unavailable", "", "-", "None"].includes(f.state) ? f.state : null;
        const left = num(r && r.state);
        const empty = !hex && !filament;
        row.querySelector(".swatch").style.background = hex || "transparent";
        row.querySelector(".swatch").style.borderStyle = empty ? "dashed" : "solid";
        const inUse = activeLabel ? activeLabel === slot.label : Number(attrs.selected) === 1;
        row.classList.toggle("active", !!inUse);
        const low = !empty && left != null && left <= 10;
        row.classList.toggle("low", low);
        const mat = row.querySelector(".mat");
        const matHtml = empty ? esc(s.empty)
          : `${esc(filament || attrs.name || "")}${inUse ? `<span class="tag">${esc(s.inUse)}</span>` : ""}<small>${esc([attrs.type, hex].filter(Boolean).join(" · "))}</small>`;
        if (mat.innerHTML !== matHtml) mat.innerHTML = matHtml;
        const leftHtml = empty || left == null ? ""
          : `${esc(low ? `${s.low} · ${Math.round(left)} %` : `${Math.round(left)} %`)}<span class="mini"><i style="width:${Math.max(0, Math.min(100, left))}%"></i></span>`;
        const leftEl = row.querySelector(".left");
        if (leftEl.innerHTML !== leftHtml) leftEl.innerHTML = leftHtml;
        row.setAttribute("aria-label", empty ? `${slot.label} ${s.empty}` : `${slot.label === "Ext" ? s.external : slot.label} ${filament || ""} ${left != null ? s.remaining(Math.round(left)) : ""}`);
      }
      // the colours the print was sliced with
      const uses = root.querySelector(".cfs .uses");
      const material = this._st("material");
      const status = this._st("status");
      const colours = material && ACTIVE.includes(status ? status.state : "") ? String(material.attributes.color || "").split(";").map(colour).filter(Boolean) : [];
      const types = material ? String(material.attributes.material || "").split(";") : [];
      const usesHtml = colours.length ? `${esc(s.uses)}: ${colours.map((hex, i) => `<span class="dot" style="background:${hex}" title="${esc([types[i], hex].filter(Boolean).join(" "))}"></span>`).join("")}` : "";
      if (uses) {
        uses.hidden = !usesHtml;
        if (uses.innerHTML !== usesHtml) uses.innerHTML = usesHtml;
      }
    }

    _act(act) {
      const e = this._cfg.entities;
      if (act === "light") { this._call("light", "toggle", { entity_id: e.light }, "set"); return; }
      if (act === "stop" || act === "restart") { this._ask(act); return; }
      this._press(act);
    }

    /* Stop and Restart ask first, in one dialog */
    _ask(kind) {
      const s = this._s, dlg = this.shadowRoot.querySelector("dialog.confirm");
      if (!dlg || !dlg.showModal) return;
      const [title, hint, go, icon] = kind === "restart"
        ? [s.restartAsk, s.restartHint, s.restartPrinter, "mdi:restart"] : [s.stopAsk, s.stopHint, s.stopPrint, "mdi:stop"];
      this._asking = kind;
      dlg.querySelector("h3").textContent = title;
      dlg.querySelector("p").textContent = hint;
      const button = dlg.querySelector('[data-dlg="go"]');
      button.querySelector("span").textContent = go;
      button.querySelector("ha-icon").setAttribute("icon", icon);
      dlg.showModal();
    }

    _dialog(choice) {
      const dlg = this.shadowRoot.querySelector("dialog.confirm");
      if (dlg) dlg.close();
      if (choice !== "go") return;
      if (this._asking === "stop") this._press("stop");
      else if (this._asking === "restart") this._restart();
    }

    async _restart() {
      if (await this._call("button", "press", { entity_id: this._cfg.entities.restart }, "restart")) this._info(this._s.restarting);
    }

    /* the pause at a line: the box, the line it is set to, and where the printer is */
    _setLine() {
      const input = this.shadowRoot.querySelector(".lineinput");
      const n = Math.round(Number(input && input.value));
      if (!input || !input.value || !Number.isFinite(n) || n < 1) { if (input) input.focus(); return; }
      this._call("number", "set_value", { entity_id: this._cfg.entities.pause_at_line, value: n }, "line")
        .then((ok) => { if (ok) { input.value = ""; this._refreshPos(); } });
    }

    _lineUpdate(active) {
      const root = this.shadowRoot, s = this._s;
      const box = root.querySelector(".line");
      if (!box) return;
      box.hidden = !active;
      const ent = this._st("pause_at_line");
      const target = ent && !["unavailable", "unknown"].includes(ent.state) ? num(ent.state) : null;
      const armed = target != null && target > 0;
      const pos = this._pos;
      this._text(root.querySelector(".linepos"), pos && pos.available && pos.lines ? s.lineAt(this._n(pos.line), this._n(pos.lines)) : "");
      let when = null;
      if (armed && pos && pos.target === target && pos.eta != null) when = pos.eta < 60 ? s.soon : s.inAbout(duration(pos.eta, this._lang));
      this._text(root.querySelector(".linestate"), armed ? s.pausesAt(this._n(target), when) : "");
      const cancel = root.querySelector('[data-line="cancel"]');
      if (cancel) cancel.hidden = !armed;
      const off = !ent || ent.state === "unavailable";
      root.querySelectorAll('.lineinput, [data-line="set"]').forEach((el) => { el.disabled = off; });
    }

    _startPos() {
      if (this._posTimer) return;
      this._posTimer = setInterval(() => this._refreshPos(), 3000);
      this._refreshPos();
    }

    _stopPos() {
      if (this._posTimer) { clearInterval(this._posTimer); this._posTimer = null; }
      this._pos = null;
    }

    async _refreshPos() {
      if (!this._hass || !this._cfg || this._posBusy) return;
      this._posBusy = true;
      try {
        const msg = { type: "printer_panel/position" };
        if (this._entryId) msg.entry_id = this._entryId;
        this._pos = await this._hass.callWS(msg);
      } catch (err) {
        this._pos = null;
      } finally {
        this._posBusy = false;
      }
      if (!this._posTimer) this._pos = null;  // stopped while asking
      const status = this._st("status");
      this._lineUpdate(!!status && ACTIVE.includes(status.state));
    }

    _n(n) {
      const lang = this._lang === "nb" ? "nb-NO" : ((this._hass.locale && this._hass.locale.language) || "en-GB");
      try { return new Intl.NumberFormat(lang).format(n); } catch (err) { return String(n); }
    }

    /* a note under the buttons that is not a failure */
    _info(text) {
      const msg = this.shadowRoot.querySelector(".msg");
      if (!msg) return;
      msg.classList.add("info");
      msg.textContent = text;
      clearTimeout(this._msgTimer);
      this._msgTimer = setTimeout(() => { msg.textContent = ""; msg.classList.remove("info"); }, 20000);
    }

    _press(act) {
      const entity = this._cfg.entities[act];
      if (!entity) return;
      const status = this._st("status");
      this._pending = { from: status ? status.state : null, until: Date.now() + 15000 };
      this._update();
      this._call("button", "press", { entity_id: entity }, act).then((ok) => { if (!ok) { this._pending = null; this._update(); } });
    }

    _nudgeTemp(k, step) {
      const target = this._st(`${k}_target`);
      const value = num(target && target.state) ?? 0;
      this._setNumber(`${k}_target`, value + step);
    }

    _nudgeSpeed(step) {
      const speed = this._st("speed");
      this._setNumber("speed", (num(speed && speed.state) ?? 100) + step);
    }

    _setNumber(what, value) {
      const st = this._st(what);
      if (!st || !Number.isFinite(value)) return;
      const min = num(st.attributes.min) ?? 0, max = num(st.attributes.max) ?? value;
      const v = Math.max(min, Math.min(max, Math.round(value)));
      this._call("number", "set_value", { entity_id: st.entity_id, value: v }, "set");
    }

    /** a service call; a refusal is said under the buttons for a few seconds. Resolves true when it worked. */
    async _call(domain, service, data, verb) {
      try {
        await this._hass.callService(domain, service, data);
        return true;
      } catch (err) {
        const msg = this.shadowRoot.querySelector(".msg");
        if (msg) {
          msg.classList.remove("info");
          msg.textContent = this._s.failed(this._s.verbs[verb] || this._s.verbs.set, (err && err.message) || String(err));
          clearTimeout(this._msgTimer);
          this._msgTimer = setTimeout(() => { msg.textContent = ""; }, 8000);
        }
        return false;
      }
    }
  }

  /* the sidebar page */
  class PrinterPanel extends PrinterView {
    get _fullPage() { return true; }
    set panel(panel) {
      const id = panel && panel.config && panel.config.entry_id;
      if (id && id !== this._entryId) {
        this._entryId = id;
        this._cfg = null;
        this._built = false;
        if (this._hass && !this._loading) this._load();
      }
    }
    set narrow(narrow) {
      this._narrow = narrow;
      if (this._menu) this._menu.narrow = !!narrow;
    }
    set route(_route) { /* one page: nothing to route */ }
  }

  /* the same view as a card for any dashboard: custom:printer-panel-card, with entry_id to pick a printer */
  class PrinterPanelCard extends PrinterView {
    static getStubConfig() { return {}; }
    setConfig(config) {
      this._config = Object.assign({}, config || {});
      this.classList.add("card");
      if (this._config.entry_id && this._config.entry_id !== this._entryId) {
        this._entryId = this._config.entry_id;
        this._cfg = null;
        this._built = false;
      }
      if (this._hass && !this._cfg && !this._loading) this._load();
    }
    getCardSize() { return 10; }
  }

  /* Home Assistant's frontend replaces the custom element registry's methods as it starts, so an element defined before
   * that is reported as missing afterwards: define once the frontend's root element exists (at once inside the panel) */
  function whenFrontendReady(fn) {
    const ready = () => !!customElements.get("home-assistant");
    if (ready()) { fn(); return; }
    let tries = 0;
    const timer = setInterval(() => {
      if (ready() || ++tries > 600) { clearInterval(timer); fn(); }
    }, 50);
  }
  whenFrontendReady(() => {
    if (!customElements.get("printer-panel")) customElements.define("printer-panel", PrinterPanel);
    if (!customElements.get("printer-panel-card")) customElements.define("printer-panel-card", PrinterPanelCard);
    window.customCards = window.customCards || [];
    if (!window.customCards.some((c) => c.type === "printer-panel-card")) {
      window.customCards.push({ type: "printer-panel-card", name: "Printer Panel", preview: false,
                                description: "A Creality printer: the camera, the print, temperatures, the CFS colours, and Pause, Resume and Stop." });
    }
  });

  // for the tests
  window.__printerPanel = { printName, duration, colour, slotLabel, repairSidebarIcons };
})();
