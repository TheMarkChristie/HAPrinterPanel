"""Check the sidebar icon repair in headless Chrome, against Home Assistant's own ha-icon (frontend 20260930.4,
src/components/ha-icon.ts and src/data/custom_icons.ts, ported as they are onto the real Lit; the MDI download stood in
for). The sidebar draws before any custom icon set exists, which leaves the Printer and HACS items empty, as on Norway
on 18 Oct 2026; then printer-panel.js loads, and HACS's icon set a second after it. Also the usual order (the script
first), where there is nothing to repair. Needs the network for Lit (cdn.jsdelivr.net).

    python tests/render_icons.py
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "custom_components", "printer_panel", "www", "printer-panel.js")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

FRONTEND = r"""
import { LitElement, html, nothing } from "https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm";

// src/data/custom_icons.ts: the icon sets, read through a proxy over window.customIcons as it was when the frontend loaded
if (!("customIcons" in window)) window.customIcons = {};
if (!("customIconsets" in window)) window.customIconsets = {};
const customIcons = new Proxy(window.customIcons, {
  get: (obj, prop) => obj[prop] ?? (window.customIconsets[prop] ? { getIcon: window.customIconsets[prop] } : undefined),
});
const MDI_PREFIXES = ["mdi", "hass", "hassio", "hademo"];

customElements.define("ha-svg-icon", class extends LitElement {
  static properties = { path: {}, viewBox: {} };
  render() { return html`<svg viewBox=${this.viewBox || "0 0 24 24"} width="24" height="24"><path d=${this.path || ""}></path></svg>`; }
});

// src/components/ha-icon.ts
customElements.define("ha-icon", class extends LitElement {
  static properties = { icon: {}, _path: { state: true }, _secondaryPath: { state: true }, _viewBox: { state: true }, _legacy: { state: true } };
  constructor() { super(); this._legacy = false; }
  willUpdate(changedProps) {
    super.willUpdate(changedProps);
    if (changedProps.has("icon")) { this._path = undefined; this._secondaryPath = undefined; this._viewBox = undefined; this._loadIcon(); }
  }
  render() {
    if (!this.icon) return nothing;
    if (this._legacy) return html`<iron-icon .icon=${this.icon}></iron-icon>`;
    return html`<ha-svg-icon .path=${this._path} .viewBox=${this._viewBox}></ha-svg-icon>`;
  }
  async _loadIcon() {
    if (!this.icon) return;
    const requestedIcon = this.icon;
    const [iconPrefix, iconName] = this.icon.split(":", 2);
    if (!iconPrefix || !iconName) return;
    if (!MDI_PREFIXES.includes(iconPrefix)) {
      const customIcon = customIcons[iconPrefix];
      if (customIcon) {
        if (customIcon && typeof customIcon.getIcon === "function") this._setCustomPath(customIcon.getIcon(iconName), requestedIcon);
        return;
      }
      this._legacy = true;
      return;
    }
    this._legacy = false;
    window.MDI_ASKED = (window.MDI_ASKED || 0) + 1;
    const path = await new Promise((r) => setTimeout(() => r(iconName === "home" ? "M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z" : undefined), 30));
    if (this.icon === requestedIcon) this._path = path;
  }
  async _setCustomPath(promise, requestedIcon) {
    const icon = await promise;
    if (this.icon !== requestedIcon) return;
    this._path = icon.path; this._secondaryPath = icon.secondaryPath; this._viewBox = icon.viewBox;
  }
});

// the sidebar, where Home Assistant puts it: home-assistant > home-assistant-main > ha-drawer > ha-sidebar
const PANELS = [{ title: "Overview", icon: "mdi:home" }, { title: "HACS", icon: "hacs:hacs" }, { title: "Printer", icon: "printer-panel:creality" }];
customElements.define("ha-sidebar", class extends LitElement {
  render() { return html`${PANELS.map((p) => html`<div><ha-icon slot="start" .icon=${p.icon}></ha-icon>${p.title}</div>`)}`; }
});
customElements.define("home-assistant-main", class extends LitElement {
  render() { return html`<ha-drawer><ha-sidebar></ha-sidebar></ha-drawer>`; }
});
customElements.define("home-assistant", class extends LitElement {
  render() { return html`<home-assistant-main></home-assistant-main>`; }
});
window.frontendReady = true;
"""

RUN = r"""
const out = (t) => document.getElementById("out").textContent += t + "\n";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const HACS_PATH = "M20 22H4V10h16z";
const loadPrinterPanel = () => { const s = document.createElement("script"); s.textContent = SCRIPT; document.head.appendChild(s); };
const loadHacs = () => {  // HACS's iconset.js, in the shape it has
  window.customIcons = window.customIcons || {};
  window.customIcons["hacs"] = { getIcon: async (name) => ({ path: name === "hacs" ? HACS_PATH : undefined }), getIconList: async () => [{ name: "hacs" }] };
};
const sidebar = () => document.querySelector("home-assistant").shadowRoot.querySelector("home-assistant-main").shadowRoot.querySelector("ha-sidebar");
const icons = () => [...sidebar().shadowRoot.querySelectorAll("ha-icon")];
const state = () => icons().map((el) => {
  const svg = el.shadowRoot.querySelector("ha-svg-icon");
  const what = el.shadowRoot.querySelector("iron-icon") ? "EMPTY" : svg && svg.path ? (svg.path === HACS_PATH ? "hacs mark" : svg.path.startsWith("M1.58 21.73") ? "creality mark" : "mdi") : "blank";
  return `${el.icon}=${what}`;
}).join(", ");
const draw = async () => {
  document.body.appendChild(document.createElement("home-assistant"));
  for (let i = 0; i < 20 && !(document.querySelector("home-assistant").shadowRoot && document.querySelector("home-assistant").shadowRoot.querySelector("home-assistant-main")
       && document.querySelector("home-assistant").shadowRoot.querySelector("home-assistant-main").shadowRoot && sidebar() && sidebar().shadowRoot
       && sidebar().shadowRoot.querySelectorAll("ha-icon").length === 3); i++) await wait(20);
  await Promise.all(icons().map((el) => el.updateComplete));
  await wait(60);
};
(async () => {
  for (let i = 0; i < 100 && !window.frontendReady; i++) await wait(50);
  if (!window.frontendReady) { out("ERROR the frontend stand-in did not load (Lit from the CDN)"); return; }
  if (ORDER === "late") {
    await draw();
    out(`sidebar drawn before any icon set: ${state()}`);
    const mdiBefore = window.MDI_ASKED;
    loadPrinterPanel();
    await wait(300);
    out(`printer-panel.js loaded: ${state()}`);
    await wait(800);
    loadHacs();
    out(`HACS's icon set loaded: ${state()}`);
    await wait(1500);
    out(`a pass later: ${state()}`);
    out(`MDI asked during the repairs: ${window.MDI_ASKED - mdiBefore} (one per repaired icon)`);
    await wait(3000);
    out(`after every pass: ${state()} | MDI asked in all ${window.MDI_ASKED - mdiBefore}`);
  } else {
    loadHacs();
    loadPrinterPanel();
    await draw();
    const before = window.MDI_ASKED;
    await wait(4500);
    out(`script first, nothing to repair: ${state()} | MDI asked beyond Overview's own: ${window.MDI_ASKED - before}`);
  }
})();
"""


def page(order: str) -> str:
    return ("<!doctype html><html><head><meta charset='utf-8'></head><body><div id='out' style='white-space:pre-wrap'></div>"
            "<script>window.onerror=function(m,s,l){document.getElementById('out').textContent+='ERROR '+m+' @'+l+'\\n'}</script>"
            f"<script type='module'>{FRONTEND}</script>"
            f"<script>const SCRIPT={json_string(open(SCRIPT, encoding='utf-8').read())};const ORDER={json_string(order)};{RUN}</script>"
            "</body></html>")


def json_string(text: str) -> str:
    import json
    return json.dumps(text).replace("</", "<\\/")


def run(order: str) -> None:
    html = os.path.join(HERE, f"render_icons_{order}.html")
    try:
        open(html, "w", encoding="utf-8").write(page(order))
        dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=20000", "--dump-dom",
                              "file:///" + html.replace("\\", "/")], capture_output=True, text=True, encoding="utf-8", timeout=180).stdout
        start = dom.find('<div id="out"')
        start = dom.find(">", start) + 1
        print(dom[start: dom.find("</div>", start)].replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&").strip())
    finally:
        os.remove(html)


if __name__ == "__main__":
    run("late")
    run("early")
