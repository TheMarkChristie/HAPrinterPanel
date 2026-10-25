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
// the filament register as Home Assistant sends it: a Creality spool the CFS found in 1D, two not in the CFS (one nearly
// used up), grams from the last print waiting on 1A, and this print so far in 1B (no number yet) and 1D
const day = "2026-10-25";
window.FIL = {
  spools: [
    { stock: "F001", brand: "Creality", colour: "Purple", hex: "#9e007e", type: "Hyper PLA", weight: 1000, left: 812.4, checked_in: day, slot: "1D", price: 249.5 },
    { stock: "F002", brand: "Sunlu", colour: "Black", hex: "#000000", type: "PLA", weight: 1000, left: 1000, checked_in: day, slot: null, tag: "#00000e" },
    { stock: "F003", brand: "eSun", colour: "Pink", hex: "#ff37af", type: "PLA+", weight: 1000, left: 64, checked_in: day, slot: null },
  ],
  slots: { "1D": { stock: "F001", how: "auto" } }, pending: { "1A": 15.2 }, printing: { "1B": 4.1, "1D": 2 },
  last_print: { file: "/mnt/UDISK/printer_data/gcodes/tag Robert_PLA_5h51m22s.gcode", ended: "2026-10-25T23:00", grams: 42.3, cost: 9.8, uncosted: 0 },
  tares: { creality: 165 }, currency: "NOK",
};
// a register of n spools: these three, then a shelf of brands, colours and types, F014 confirmed in 1B
const many = (n) => {
  const colours = [["Black", "#000000"], ["White", "#f4f4f4"], ["Grey", "#808080"], ["Red", "#d32020"], ["Blue", "#1e5bd8"],
                   ["Green", "#2e9e44"], ["Yellow", "#f2c500"], ["Orange", "#f07818"], ["Pink", "#ff37af"], ["Purple", "#9e007e"]];
  const brands = ["Sunlu", "eSun", "Polymaker", "Elegoo", "Creality"], types = ["PLA", "PLA+", "PETG", "PLA Matte"];
  const fil = JSON.parse(JSON.stringify(window.FIL));
  for (let i = fil.spools.length + 1; i <= n; i++) {
    const [c, h] = colours[i % 10];
    fil.spools.push({ stock: `F${String(i).padStart(3, "0")}`, brand: brands[i % 5], colour: c, hex: h, type: types[i % 4], weight: 1000,
                      left: ((i * 137) % 1000) + 20, checked_in: day, slot: i === 14 ? "1B" : null });
  }
  if (n >= 14) fil.slots["1B"] = { stock: "F014", how: "confirmed" };
  return fil;
};
if (!CHECK) window.FIL = many(12);
const filament = (m) => {
  calls.push(`ws ${JSON.stringify(m)}`);
  if (window.WS_REFUSE) throw window.WS_REFUSE;
  if (m.type.endsWith("/check_in")) return { stock: "F004", brand: m.brand, colour: m.colour, hex: m.hex, type: m.material, weight: m.weight, left: m.weight, slot: null };
  if (m.type.endsWith("/confirm")) return { booked: 15.2 };
  if (m.type.endsWith("/update")) return { ...window.FIL.spools.find((x) => x.stock === m.stock), ...m };
  if (m.type.endsWith("/tag")) return { stock: m.stock, tag: "#00000e", material: "Generic PLA", weight: 1000 };
  return null;
};
const connection = { subscribeMessage: async (cb, m) => {
  window.SUBS = (window.SUBS || 0) + 1;
  if (window.SUB_FAIL) throw { code: "unknown_command", message: "Unknown command." };
  window.FIL_CB = cb;
  setTimeout(() => cb(JSON.parse(JSON.stringify(window.FIL))), 0);
  return () => { window.UNSUBBED = (window.UNSUBBED || 0) + 1; };
} };
const mk = (lang) => ({ states, locale: { language: lang, time_format: "24", time_zone: "local" }, config: { time_zone: "Europe/Oslo" },
  language: lang, hassUrl: (u) => u, connection,
  callWS: async (m) => { if (m.type === "printer_panel/position") window.POS_ASKED = (window.POS_ASKED || 0) + 1;
    if (m.type.startsWith("printer_panel/filament/")) return filament(m);
    if (m.type === "auth/sign_path") { calls.push(`ws ${JSON.stringify(m)}`); if (window.SIGN_REFUSE) throw { code: "unauthorized", message: window.SIGN_REFUSE };
      return { path: `${m.path}?authSig=x` }; }
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
  // the filament register: the card, the slots' stock numbers, and each dialog
  calls.length = 0;
  const slotDlg = q("dialog.slotform"), spoolDlg = q("dialog.spoolform");
  const sf = (n, v) => { spoolDlg.querySelector(`[name="${n}"]`).value = v; };
  const fields = (names) => names.map((n) => spoolDlg.querySelector(`[name="${n}"]`).value).join(", ");
  const picks = () => [...slotDlg.querySelectorAll(".pick")].map((b) => b.textContent.trim()).join(", ");
  out(`filament: card shown ${vis(".filament")} | subscribed ${window.SUBS} | waiting: ${[...r.querySelectorAll(".waiting span")].map((e) => `"${e.textContent}"`).join(" ")}`);
  out(`spools: ${[...r.querySelectorAll(".spool")].map((e) => `${e.querySelector(".who").textContent.replace(/\s+/g, " ").trim()} [${e.querySelector(".grams").textContent.trim()}]${e.classList.contains("low") ? " LOW" : ""}`).join(" | ")}`);
  const stockButtons = () => [...r.querySelectorAll(".slot")].map((e) => { const b = e.querySelector(".stock");
    return `${e.dataset.slot} ${b.hidden ? "-" : b.textContent}${b.classList.contains("due") ? " DUE" : ""}${b.classList.contains("unknown") ? " (dashed)" : ""}`; }).join(" | ");
  out(`slot stock numbers: ${stockButtons()} | 1D says "${r.querySelector('.slot[data-slot="1D"] .stock').title}"`);
  r.querySelector('.slot[data-slot="1D"] .stock').click(); await wait(20);
  out(`groups: ${[...r.querySelectorAll(".filament .boxhead")].map((e) => e.textContent.trim()).join(" / ")} | find box ${vis(".find")}`);
  out(`1D: open ${slotDlg.open} "${txt("dialog.slotform h3")}" | "${txt(".slothint")}" | number "${slotDlg.querySelector('[name="stock"]').value}" | clear shown ${vis('dialog.slotform [data-fil="clear"]')} | drop shown ${vis('dialog.slotform [data-fil="forget"]')} | likely: ${picks()}`);
  slotDlg.querySelector('[name="stock"]').value = "2"; slotDlg.querySelector("[data-go]").click(); await wait(30);
  out(`typed 2 -> ${calls.pop()} | open ${slotDlg.open}`);
  r.querySelector('.waiting [data-for="1A"]').click(); await wait(20);
  out(`1A from its note: "${txt("dialog.slotform h3")}" | "${txt(".slothint")}" | clear shown ${vis('dialog.slotform [data-fil="clear"]')} | drop "${txt('dialog.slotform [data-fil="forget"]')}" shown ${vis('dialog.slotform [data-fil="forget"]')} | likely: ${picks()}`);
  slotDlg.querySelector('[name="stock"]').value = "f099"; slotDlg.querySelector("[data-go]").click(); await wait(30);
  out(`f099: "${txt("dialog.slotform .dmsg")}" | asked ${calls.length} | open ${slotDlg.open}`);
  slotDlg.querySelector(".pick").click(); await wait(10);
  out(`picked "${slotDlg.querySelector('[name="stock"]').value}", focus on ${slotDlg.querySelector(":focus") ? slotDlg.querySelector(":focus").textContent.trim() : "-"}`);
  slotDlg.querySelector("[data-go]").click(); await wait(30);
  out(`-> ${calls.pop()} | open ${slotDlg.open}`);
  r.querySelector('.waiting [data-for="1A"]').click(); await wait(20);
  slotDlg.querySelector('[data-fil="forget"]').click(); await wait(30);
  out(`not a register spool -> ${calls.pop()} | open ${slotDlg.open}`);
  q('[data-fil="checkin"]').click(); await wait(20);
  out(`check in: open ${spoolDlg.open} "${txt("dialog.spoolform h3")}" | weight ${spoolDlg.querySelector('[name="weight"]').value} | left shown ${vis("dialog.spoolform [data-left]")} | remove shown ${vis('dialog.spoolform [data-fil="remove"]')} | button "${txt("dialog.spoolform [data-go]")}"`);
  spoolDlg.querySelector("[data-go]").click(); await wait(20);
  out(`nothing filled in: "${txt("dialog.spoolform .dmsg")}" | asked ${calls.length}`);
  sf("brand", "Polymaker"); sf("colour", "Grey"); sf("hex", "#7a7a7a"); sf("material", "PETG"); sf("weight", "0");
  spoolDlg.querySelector("[data-go]").click(); await wait(20);
  out(`weight 0: "${txt("dialog.spoolform .dmsg")}" | asked ${calls.length}`);
  sf("weight", "750"); spoolDlg.querySelector("[data-go]").click(); await wait(30);
  out(`-> ${calls.pop()}`);
  out(`checked in: "${txt("dialog.spoolform .done p")}" ${txt(".bignum")} "${txt(".donehint")}" | fields shown ${vis('dialog.spoolform [data-part="edit"]')} | cancel shown ${vis('dialog.spoolform [data-fil="close"]')} | button "${txt("dialog.spoolform [data-go]")}"`);
  spoolDlg.querySelector("[data-go]").click(); await wait(20);
  out(`Done: open ${spoolDlg.open} | asked ${calls.length}`);
  q('[data-fil="checkin"]').click(); await wait(20);
  const chips = () => [...spoolDlg.querySelectorAll('[data-fil="cfs"]')].map((b) => `${b.textContent.trim()}${b.getAttribute("aria-pressed") === "true" ? " (picked)" : ""}`).join(", ");
  const focused = () => (spoolDlg.querySelector(":focus") ? spoolDlg.querySelector(":focus").name || spoolDlg.querySelector(":focus").textContent.trim() : "-");
  out(`from the CFS: shown ${vis("dialog.spoolform .fromcfs")} | ${chips()}`);
  spoolDlg.querySelector('[data-fil="cfs"][data-slot="Ext"]').click(); await wait(10);
  out(`Ext picked: ${fields(["brand", "colour", "hex", "material", "weight"])} | ${chips()} | focus ${focused()}`);
  spoolDlg.querySelector('[data-fil="cfs"][data-slot="1A"]').click(); await wait(10);
  out(`1A picked: ${fields(["brand", "colour", "hex", "material"])} | focus ${focused()}`);
  spoolDlg.querySelector('[data-fil="cfs"][data-slot="1A"]').click(); await wait(10);
  out(`1A again: ${chips()} | fields kept ${fields(["colour", "material"])}`);
  spoolDlg.querySelector('[data-fil="cfs"][data-slot="Ext"]').click(); await wait(10);
  spoolDlg.querySelector("[data-go]").click(); await wait(40);
  out(`checked in from Ext -> ${calls.slice(-2).join(" then ")} | "${txt(".donehint")}"`);
  spoolDlg.close(); calls.length = 0;
  r.querySelector('.spool[data-stock="F002"] [data-fil="edit"]').click(); await wait(20);
  out(`changing a spool: from the CFS shown ${vis("dialog.spoolform .fromcfs")}`);
  spoolDlg.close();
  const realClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () { window.DOWNLOAD = `${this.getAttribute("href")} as ${this.download}`; };
  q('[data-fil="pdf"]').click(); await wait(30);
  out(`PDF -> ${calls.pop()} | download ${window.DOWNLOAD.replace(/\d{4}-\d\d-\d\d/, "YYYY-MM-DD")} | link left behind ${!!r.querySelector("a[download]")}`);
  window.SIGN_REFUSE = "Unauthorized"; q('[data-fil="pdf"]').click(); await wait(30);
  out(`PDF refused: "${txt(".fmsg")}" | button enabled ${!q('[data-fil="pdf"]').disabled}`);
  window.SIGN_REFUSE = null; HTMLAnchorElement.prototype.click = realClick; calls.length = 0;
  // prices, weighing and NFC tags
  out(`last print: "${txt(".lastprint")}" | F002 "${txt('.spool[data-stock="F002"] small')}"`);
  q('[data-fil="checkin"]').click(); await wait(20);
  out(`check in: "${txt("dialog.spoolform .plabel")}" shown ${vis('dialog.spoolform [name="price"]')} | weigh shown ${vis("dialog.spoolform [data-weigh]")} | NFC shown ${vis('dialog.spoolform [data-fil="tag"]')}`);
  sf("brand", "Sunlu"); sf("material", "PLA"); sf("price", "199"); spoolDlg.querySelector("[data-go]").click(); await wait(30);
  out(`with a price -> ${calls.pop()}`);
  spoolDlg.close(); calls.length = 0;
  r.querySelector('.spool[data-stock="F001"] [data-fil="edit"]').click(); await wait(20);
  out(`change F001: price ${fields(["price"])} | empty spool ${fields(["tare"])} (Creality's, kept) | weigh shown ${vis("dialog.spoolform [data-weigh]")} | NFC shown ${vis('dialog.spoolform [data-fil="tag"]')}`);
  sf("weighed", "100"); spoolDlg.querySelector("[data-go]").click(); await wait(20);
  out(`weighed 100, under the empty spool: "${txt("dialog.spoolform .dmsg")}" | asked ${calls.length}`);
  sf("weighed", "800"); sf("price", ""); spoolDlg.querySelector("[data-go]").click(); await wait(30);
  out(`weighed 800, price cleared -> ${calls.pop()}`);
  r.querySelector('.spool[data-stock="F002"] [data-fil="edit"]').click(); await wait(20);
  sf("weighed", "700"); spoolDlg.querySelector("[data-go]").click(); await wait(20);
  out(`Sunlu weighed, no empty spool known yet: "${txt("dialog.spoolform .dmsg")}" | asked ${calls.length}`);
  spoolDlg.querySelector('[data-fil="tag"]').click(); await wait(40);
  const tagDlg = q("dialog.tagform");
  out(`NFC: open ${tagDlg.open} "${txt("dialog.tagform h3")}" | ${txt(".tmat")} | ${txt(".tcol")} ${tagDlg.querySelector(".dot").style.background} | ${txt(".twt")} | "${txt(".tagafter")}" | -> ${calls.pop()}`);
  tagDlg.querySelector('[data-fil="copy"]').click(); await wait(20);
  tagDlg.querySelector("[data-go]").click(); await wait(20);
  out(`NFC done: tag dialog open ${tagDlg.open} | spool dialog still open ${spoolDlg.open}`);
  spoolDlg.close(); calls.length = 0;
  out(`money: ${["NOK", "GBP", "EUR"].map((c) => window.__printerPanel.money(1234.5, c, "en")).join(", ")} | nb ${window.__printerPanel.money(9.8, "NOK", "nb")}`);
  out(`colour names:${["#9e007e", "#2f6f7a", "#00a3ff", "#c12e1f", "#f4f4f4", "#ff37af"].map((h) => `${h} ${window.__printerPanel.colourName(h, "en")}`).join(", ")} | nb #2f6f7a ${window.__printerPanel.colourName("#2f6f7a", "nb")}`);
  r.querySelector('.spool[data-stock="F003"] [data-fil="edit"]').click(); await wait(20);
  out(`change F003: "${txt("dialog.spoolform h3")}" | ${fields(["brand", "colour", "hex", "material", "weight", "left"])} | left shown ${vis("dialog.spoolform [data-left]")} | remove shown ${vis('dialog.spoolform [data-fil="remove"]')} | button "${txt("dialog.spoolform [data-go]")}"`);
  sf("left", "50"); spoolDlg.querySelector("[data-go]").click(); await wait(30);
  out(`weighed, 50 left -> ${calls.pop()} | open ${spoolDlg.open}`);
  r.querySelector('.spool[data-stock="F003"] [data-fil="edit"]').click(); await wait(20);
  spoolDlg.querySelector('[data-fil="remove"]').click(); await wait(20);
  out(`remove asks first: "${txt("dialog.confirm h3")}" / "${txt('[data-dlg="go"]')}" | asked ${calls.length}`);
  q('[data-dlg="go"]').click(); await wait(30);
  out(`removed -> ${calls.pop()} | spool form open ${spoolDlg.open} | question open ${q("dialog.confirm").open}`);
  r.querySelector('.slot[data-slot="1C"] .stock').click(); await wait(20);
  out(`1C: "${txt(".slothint")}" | likely: ${picks()}`);
  slotDlg.querySelector('[data-fil="new"]').click(); await wait(20);
  out(`a new spool in 1C: slot dialog open ${slotDlg.open} | "${txt("dialog.spoolform h3")}" | ${fields(["brand", "colour", "hex", "material", "weight"])} | ${chips()}`);
  sf("brand", "Sunlu"); sf("colour", "Blue"); spoolDlg.querySelector("[data-go]").click(); await wait(40);
  out(`-> ${calls.slice(-2).join(" then ")} | "${txt(".donehint")}"`);
  spoolDlg.close(); calls.length = 0;
  r.querySelector('.slot[data-slot="Ext"] .stock').click(); await wait(20);
  out(`Ext: "${txt("dialog.slotform h3")}" | "${txt(".slothint")}"`);
  slotDlg.querySelector('[data-fil="new"]').click(); await wait(20);
  out(`a new Creality spool on the holder: ${fields(["brand", "hex", "material"])}`);
  window.WS_REFUSE = { code: "home_assistant_error", message: "Storage is read-only" };
  sf("colour", "Red"); spoolDlg.querySelector("[data-go]").click(); await wait(30);
  out(`refused: "${txt("dialog.spoolform .dmsg")}" | open ${spoolDlg.open} | button enabled ${!spoolDlg.querySelector("[data-go]").disabled}`);
  window.WS_REFUSE = null; spoolDlg.close(); calls.length = 0;
  window.FIL_CB({ ...JSON.parse(JSON.stringify(window.FIL)), slots: { "1A": { stock: "F002", how: "confirmed" }, "1D": { stock: "F001", how: "auto" } }, pending: {}, printing: {} }); await wait(20);
  out(`1A confirmed: waiting ${r.querySelectorAll(".waiting").length} | ${stockButtons()} | F002 "${txt('.spool[data-stock="F002"] small')}"`);
  const slotB = Object.keys(STATES).filter((k) => /_slot_2_(filament|color)$/.test(k));
  states = JSON.parse(JSON.stringify(states));
  for (const k of slotB) states[k] = { ...states[k], state: k.endsWith("_color") ? "" : "unknown",
    attributes: { ...states[k].attributes, vendor: "", type: "", name: "", color_hex: "", rfid: "", state: 1 } };
  panel.hass = mk("en"); await wait(20);
  const rowB = r.querySelector('.slot[data-slot="1B"]');
  out(`1B in, nothing set: "${rowB.querySelector(".mat").textContent.trim()}" | stock button ${rowB.querySelector(".stock").hidden ? "hidden" : `"${rowB.querySelector(".stock").textContent}"`}`);
  for (const k of slotB) states[k].attributes.state = 0;
  panel.hass = mk("en"); await wait(20);
  out(`1B empty (state 0): "${rowB.querySelector(".mat").textContent.trim()}" | stock button ${rowB.querySelector(".stock").hidden ? "hidden" : "shown"}`);
  states = JSON.parse(JSON.stringify(STATES)); panel.hass = mk("en"); await wait(20);
  const big = many(40);
  window.FIL_CB(big); await wait(20);
  out(`40 spools: find box ${vis(".find")} | ${[...r.querySelectorAll(".filament .boxhead")].map((e) => e.textContent.trim()).join(" / ")} | first ${[...r.querySelectorAll(".spool")].slice(0, 3).map((e) => e.dataset.stock).join(",")} | rows ${r.querySelectorAll(".spool").length} | card ${Math.round(q(".filament").getBoundingClientRect().height)} px`);
  const find = q(".find");
  const look = async (v) => { find.value = v; find.dispatchEvent(new Event("input", { bubbles: true })); await wait(10);
    return [...r.querySelectorAll(".spool")].map((e) => e.dataset.stock).join(",") || `"${txt(".spools")}"`; };
  out(`find "14" -> ${await look("14")} | "f2" -> ${await look("f2")} | "sunlu black" -> ${await look("sunlu black")} | "petg 1b" -> ${await look("petg 1b")} | "zzz" -> ${await look("zzz")}`);
  await look("polymaker"); window.FIL_CB(big); await wait(20);
  out(`the register updating while finding keeps it: "${find.value}" -> ${[...r.querySelectorAll(".spool")].map((e) => e.dataset.stock).join(",")}`);
  await look("");
  window.FIL_CB({ spools: [], slots: {}, pending: {}, printing: {} }); await wait(20);
  out(`no spools: "${txt(".spools")}"`);
  panel._unsubscribe(); window.SUB_FAIL = true; panel._reg = null; panel._subscribe(); await wait(30);
  out(`a Printer Panel without the register: card shown ${vis(".filament")} | stock buttons shown ${[...r.querySelectorAll(".slot .stock")].filter((b) => !b.hidden).length} | unsubscribed ${window.UNSUBBED || 0}`);
  window.SUB_FAIL = false; panel._subscribe(); await wait(30);
  out(`and back: card shown ${vis(".filament")} | subscribed ${window.SUBS}`);
  // Norwegian
  window.POS = { ...window.POS, target: 400000, eta: 725 };
  states[PAUSE_AT_ID] = { ...states[PAUSE_AT_ID], state: "400000" };
  states[COUNT_ID] = { ...states[COUNT_ID], state: "on" };
  panel.hass = mk("nb"); await panel._refreshPos(); await wait(30);
  window.FIL_CB(JSON.parse(JSON.stringify(window.FIL))); await wait(20);
  out(`nb: ${txt(".bar .status")} | ${txt(".times").replace(/\s+/g, " ")} | ${txt('[data-act="pause"]')} | "${txt(".linepos")}" | "${txt(".linestate")}"`);
  out(`nb filament: ${[...r.querySelectorAll(".waiting span")].map((e) => `"${e.textContent}"`).join(" ")} | ${txt('.spool[data-stock="F001"] .grams')} | 1C "${txt('.slot[data-slot="1C"] .stock')}"`);
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
    run(400, 2900, "phone", False)
