"""Check and screenshot the Printer page in headless Chrome, from the K2 Plus fixture (tests/fixtures/k2plus.json): what
it shows mid-print, what each control asks Home Assistant to do, the pause at a line, pictures that do not load,
Norwegian, and the printer off. The page inlines the script and the states (a file:// page cannot fetch), stands in for
the bit of hass the page reads, and records every service call; Home Assistant's own elements (ha-card, ha-icon,
ha-menu-button) are stood in for by plain ones, and without its card helpers the camera is the snapshot fallback. The
screenshots show the pictures loaded, with the brand images standing in for the camera and the print.

    python tests/render_panel.py   -> the checks printed; tests/render_wide.png and tests/render_phone.png
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _load  # noqa: E402,F401
from custom_components.printer_panel import printer as p  # noqa: E402

ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "custom_components", "printer_panel", "www", "printer-panel.js")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
FIXTURE = json.load(open(os.path.join(HERE, "fixtures", "k2plus.json"), encoding="utf-8"))
PAUSE_AT, COUNT = "number.k2plus_235d_pause_at_g_code_line", "switch.k2plus_235d_count_g_code_lines"
CONFIG = {"entry_id": "e1", "title": "Printer", "path": "printer", "device_id": "k2plus", "name": "K2Plus-235D", "model": "K2 Plus",
          **p.resolve(FIXTURE["registry"])}
CONFIG["entities"].update(pause_at_line=PAUSE_AT, count_lines=COUNT)
STATES = {s["entity_id"]: s for s in FIXTURE["states"]}
STATES[PAUSE_AT] = {"entity_id": PAUSE_AT, "state": "0", "attributes": {"min": 0, "max": 99999999, "step": 1, "mode": "box"}}
STATES[COUNT] = {"entity_id": COUNT, "state": "off", "attributes": {}}

STANDINS = r"""
customElements.define("home-assistant", class extends HTMLElement {});
customElements.define("ha-card", class extends HTMLElement { connectedCallback() { this.style.cssText += ";display:block;background:#1c1c1c;border-radius:12px;border:1px solid #333"; } });
customElements.define("ha-icon", class extends HTMLElement { connectedCallback() { this.style.cssText = "display:inline-block;width:18px;height:18px;border-radius:4px;background:currentColor;opacity:.6"; } });
customElements.define("ha-menu-button", class extends HTMLElement {});
"""

CHECKS = r"""
const out = (t) => document.getElementById('out').textContent += t + '\n';
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const calls = [];
let states = JSON.parse(JSON.stringify(STATES));
window.POS = { available: true, target: null, state: "printing", line: 341202, lines: 495870, eta: null };
const mk = (lang) => ({ states, locale: { language: lang, time_format: "24", time_zone: "local" }, config: { time_zone: "Europe/Oslo" },
  language: lang, hassUrl: (u) => u,
  callWS: async (m) => { if (m.type === "printer_panel/position") window.POS_ASKED = (window.POS_ASKED || 0) + 1;
    return m.type === "printer_panel/config" ? CONFIG : m.type === "printer_panel/position" ? JSON.parse(JSON.stringify(window.POS)) : null; },
  callService: async (d, s, data) => { calls.push(`${d}.${s} ${JSON.stringify(data)}`); if (window.REFUSE) throw new Error(window.REFUSE); } });
const set = (id, state) => { states = JSON.parse(JSON.stringify(states)); states[id] = { ...states[id], state }; panel.hass = mk("en"); };
const panel = document.createElement("printer-panel");
document.getElementById("app").appendChild(panel);
panel.panel = { config: { entry_id: "e1" } };
panel.narrow = false;
panel.hass = mk("en");
let r;    // the panel's shadow root, once the element is defined (it waits for Home Assistant's frontend)
const q = (s) => r.querySelector(s), txt = (s) => (q(s) ? q(s).textContent.trim() : "(none)");
const vis = (s) => !!q(s) && getComputedStyle(q(s)).display !== "none";
const pictures = async () => {
  // the brand images stand in for the camera and the print
  const cam = Object.keys(STATES).find((k) => k.startsWith("camera.")), pre = Object.keys(STATES).find((k) => k.startsWith("image."));
  states = JSON.parse(JSON.stringify(STATES));
  states[cam].attributes.entity_picture = "../custom_components/printer_panel/brand/logo@2x.png?token=x";
  states[pre].attributes.entity_picture = "../custom_components/printer_panel/brand/icon.png?token=x";
  states[COUNT_ID] = { ...states[COUNT_ID], state: "on" };
  panel.hass = mk("en"); panel._snapshot(); await wait(300);
};
(async () => {
  await wait(150);
  r = panel.shadowRoot;
  if (!CHECK) { await pictures(); return; }
  out(`pictures that do not load: print picture shown ${vis(".preview")}, name full width ${q(".head").classList.contains("nopic")} | camera: ${vis(".camwrap img")}, "${txt(".camwrap .nocam")}"`);
  out(`header: ${txt(".bar .title")} | status ${txt(".bar .status")}`);
  out(`print: ${txt(".name")} | ${txt(".sub")} | ${txt(".pct")} | ${txt(".times").replace(/\s+/g, " ")}`);
  out(`buttons: pause ${vis('[data-act="pause"]')}, resume ${vis('[data-act="resume"]')}, stop ${vis('[data-act="stop"]')}, light pressed ${q('[data-act="light"]').getAttribute("aria-pressed")}`);
  out(`counting off: line box ${vis(".line")} | toggle "${txt("[data-count]")}" | counter and box ${vis(".lineon")} | position asked ${window.POS_ASKED || 0}`);
  out(`temperatures: ${[...r.querySelectorAll("[data-temp]")].map((row) => `${row.querySelector(".what").textContent} ${row.querySelector(".now").textContent} target ${row.querySelector("input") ? row.querySelector("input").value : "-"}`).join(" | ")}`);
  out(`speed: ${txt("[data-speed] .now")} | modes pressed: ${[...r.querySelectorAll(".mode")].filter((b) => b.getAttribute("aria-pressed") === "true").map((b) => b.textContent).join(",")}`);
  out(`fans: ${[...r.querySelectorAll("[data-fan]")].map((row) => `${row.firstElementChild.textContent} ${row.querySelector(".val").textContent} ${row.querySelector(".switch").textContent}`).join(" | ")}`);
  out(`cfs: ${[...r.querySelectorAll(".slot")].map((row) => `${row.dataset.slot} ${row.querySelector(".swatch").style.background} ${row.querySelector(".mat").textContent.trim()} [${row.querySelector(".left").textContent.trim()}]${row.classList.contains("low") ? " LOW" : ""}${row.classList.contains("active") ? " ACTIVE" : ""}`).join(" | ")}`);
  out(`box: ${[...r.querySelectorAll(".boxhead")].map((b) => b.textContent.trim()).join(" | ")}`);
  out(`print uses: ${r.querySelectorAll(".uses .dot").length} colours`);
  // the controls
  q('[data-act="pause"]').click(); await wait(20);
  out(`pause -> ${calls.pop()} | buttons then disabled: ${q('[data-act="pause"]').disabled}`);
  panel.hass = mk("en"); await wait(10);
  q('[data-act="stop"]').disabled = false;
  q('[data-act="stop"]').click(); await wait(20);
  out(`stop asks first: dialog open ${q("dialog.confirm").open} "${txt("dialog h3")}" / "${txt('[data-dlg="go"]')}", calls ${calls.length}`);
  q('[data-dlg="cancel"]').click(); await wait(20);
  out(`cancel: dialog open ${q("dialog.confirm").open}, calls ${calls.length}`);
  q('[data-act="stop"]').click(); await wait(20); q('[data-dlg="go"]').click(); await wait(20);
  out(`confirm -> ${calls.pop()}`);
  q('[data-act="light"]').click(); await wait(20);
  out(`light -> ${calls.pop()}`);
  r.querySelector('[data-temp="nozzle"] [data-step="5"]').click(); await wait(20);
  out(`nozzle + -> ${calls.pop()}`);
  const bed = r.querySelector('[data-temp="bed"] input'); bed.value = "60"; bed.dispatchEvent(new Event("change", { bubbles: true })); await wait(20);
  out(`bed typed 60 -> ${calls.pop()}`);
  r.querySelector('.mode[data-mode="130"]').click(); await wait(20);
  out(`Sport -> ${calls.pop()}`);
  const fan = r.querySelector('[data-fan="fan_model"] input'); fan.value = "50"; fan.dispatchEvent(new Event("change", { bubbles: true })); await wait(20);
  out(`part fan 50 -> ${calls.pop()}`);
  fan.value = "0"; fan.dispatchEvent(new Event("change", { bubbles: true })); await wait(20);
  out(`part fan 0 -> ${calls.pop()}`);
  window.REFUSE = "printer busy";
  r.querySelector('[data-fan="fan_side"] .switch').click(); await wait(30);
  out(`refused: "${txt(".msg")}"`);
  window.REFUSE = null;
  calls.length = 0;
  // the pause at a line: counting on first
  q("[data-count]").click(); await wait(20);
  out(`count on -> ${calls.pop()}`);
  set(COUNT_ID, "on"); await wait(60);
  out(`counting on: toggle "${txt("[data-count]")}" | counter and box ${vis(".lineon")} | "${txt(".linepos")}" | position asked ${window.POS_ASKED}`);
  const line = q(".lineinput");
  q('[data-line="set"]').click(); await wait(20);
  out(`set with an empty box -> ${calls.length ? calls.pop() : "nothing asked"}`);
  line.value = "400000"; q('[data-line="set"]').click(); await wait(40);
  out(`set 400000 -> ${calls.pop()} | box emptied ${line.value === ""}`);
  line.value = "420000"; line.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); await wait(40);
  out(`Enter 420000 -> ${calls.pop()}`);
  window.POS = { ...window.POS, target: 400000, eta: 725 };
  set(PAUSE_AT_ID, "400000"); await panel._refreshPos(); await wait(20);
  out(`armed: "${txt(".linestate")}" | cancel ${vis('[data-line="cancel"]')}`);
  window.POS = { ...window.POS, eta: 40 }; await panel._refreshPos(); await wait(20);
  out(`close: "${txt(".linestate")}"`);
  q('[data-line="cancel"]').click(); await wait(20);
  out(`cancel -> ${calls.pop()}`);
  window.REFUSE = "Line 300000 is already printed: the printer is at line 341202.";
  line.value = "300000"; q('[data-line="set"]').click(); await wait(40);
  out(`refused line: "${txt(".msg")}" | box kept ${line.value}`);
  window.REFUSE = null;
  calls.length = 0;
  // the slot in use, from the active slot sensor (slots counted from 1; older versions of the integration said it in words)
  const act = Object.keys(STATES).find((k) => k.endsWith("_active_filament_slot"));
  for (const v of ["box_1_slot_4", "external", "Box 1 Slot 3", "unknown"]) {
    states = JSON.parse(JSON.stringify(STATES)); states[act].state = v; panel.hass = mk("en"); await wait(20);
    out(`active slot ${v} -> ${[...r.querySelectorAll(".slot.active")].map((row) => row.dataset.slot).join(",") || "none"}`);
  }
  out(`print file colours: "${txt(".uses")}" ${r.querySelectorAll(".uses .dot").length} dots`);
  // Norwegian
  window.POS = { ...window.POS, target: 400000, eta: 725 };
  states[PAUSE_AT_ID] = { ...states[PAUSE_AT_ID], state: "400000" };
  states[COUNT_ID] = { ...states[COUNT_ID], state: "on" };
  panel.hass = mk("nb"); await panel._refreshPos(); await wait(30);
  out(`nb: ${txt(".bar .status")} | ${txt(".times").replace(/\s+/g, " ")} | ${txt('[data-act="pause"]')} | "${txt(".linepos")}" | "${txt(".linestate")}"`);
  // idle
  const status = Object.keys(states).find((k) => k.endsWith("_print_status"));
  states = JSON.parse(JSON.stringify(STATES)); states[status] = { ...states[status], state: "idle" }; panel.hass = mk("en"); await wait(30);
  out(`idle: pause ${vis('[data-act="pause"]')} | stop ${vis('[data-act="stop"]')} | line box ${vis(".line")}`);
  // the printer off
  states = JSON.parse(JSON.stringify(states)); states[status] = { ...states[status], state: "unavailable", attributes: {} };
  panel.hass = mk("en"); await wait(30);
  out(`off: ${txt(".bar .status")} | "${txt(".offline")}" | pause shown ${vis('[data-act="pause"]')} | nozzle input disabled ${r.querySelector('[data-temp="nozzle"] input').disabled}`);
  // back to printing, the pictures loading
  await pictures();
  out(`pictures that load: print picture shown ${vis(".preview")}, name full width ${q(".head").classList.contains("nopic")} | camera: ${vis(".camwrap img")}, note shown ${vis(".camwrap .nocam")}`);
})();
"""


def page(width: int, checks: bool) -> str:
    return ("<!doctype html><html><head><meta charset='utf-8'><style>body{margin:0;background:#111;color:#e1e1e1;font-family:Roboto,'Segoe UI',sans-serif;"
            "--primary-background-color:#111;--primary-text-color:#e1e1e1;--secondary-text-color:#9b9b9b;--divider-color:#333;"
            "--primary-color:#03a9f4;--text-primary-color:#fff;--secondary-background-color:#262626;--card-background-color:#1c1c1c;"
            "--app-header-background-color:#101e24;--app-header-text-color:#e1e1e1;--error-color:#db4437;--warning-color:#ffa600;"
            f"--success-color:#43a047}} #app{{width:{width}px}} #out{{white-space:pre-wrap;font:12px monospace;color:#7f7;padding:8px}}</style></head>"
            "<body><div id='app'></div><div id='out'></div>"
            "<script>window.onerror=function(m,s,l){document.getElementById('out').textContent+='ERROR '+m+' @'+l+'\\n'}</script>"
            f"<script>{STANDINS}</script><script>{open(SCRIPT, encoding='utf-8').read()}</script>"
            f"<script>const STATES={json.dumps(STATES)};const CONFIG={json.dumps(CONFIG)};const CHECK={json.dumps(checks)};"
            f"const PAUSE_AT_ID={json.dumps(PAUSE_AT)};const COUNT_ID={json.dumps(COUNT)};{CHECKS}</script>"
            "</body></html>")


def chrome(url: str, *args: str) -> str:
    return subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
                           "--virtual-time-budget=15000", *args, url], capture_output=True, text=True, encoding="utf-8", timeout=120).stdout


def run(width: int, height: int, name: str, checks: bool) -> None:
    html = os.path.join(HERE, f"render_{name}.html")
    url = "file:///" + html.replace("\\", "/")
    try:
        if checks:
            open(html, "w", encoding="utf-8").write(page(width, True))
            dom = chrome(url, "--dump-dom")
            start = dom.find('<div id="out">')
            text = dom[start + 14: dom.find("</div>", start)]
            for code, char in (("&gt;", ">"), ("&lt;", "<"), ("&quot;", '"'), ("&nbsp;", " "), ("&amp;", "&")):
                text = text.replace(code, char)
            print(text)
        open(html, "w", encoding="utf-8").write(page(width, False))
        png = os.path.join(HERE, f"render_{name}.png")
        chrome(url, f"--window-size={width},{height}", f"--screenshot={png}")
        print("screenshot:", png)
    finally:
        os.remove(html)


if __name__ == "__main__":
    run(1280, 1460, "wide", True)
    run(400, 2280, "phone", False)
