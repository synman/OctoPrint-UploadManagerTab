#!/usr/bin/env python3
"""Probe for the Upload Manager Tab plugin. Drives a live OctoPrint rig with Playwright.

Environment:
  UMT_BASE   rig URL (default http://127.0.0.1:5097)
  UMT_RIG    rig directory holding apikey (default ~/octoprint-rigs/live20)
  UMT_ONLY   comma list of check numbers to run (default: all)

Speed: checks are jobs run in parallel, each with its own browser. Each job uses fresh browser
contexts, so localStorage is never shared. Plugin settings reach the page through a per-context
response rewrite of GET /api/settings, so the probe changes no server settings while it runs.
Settings that change during a check go through the page's own observables. Requests the plugin
does not need (webcam, third-party hosts) are aborted. Waits are on conditions, not on time.

Output: one PASS or FAIL line per numbered check, SKIP lines for checks that do not apply, and
TIME lines with each job's wall-clock time. Exits non-zero on any FAIL.
"""
import itertools
import json
import os
import re
import sys
import time
import urllib.request
import uuid
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial
from multiprocessing import get_context
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

RIG = os.path.expanduser(os.environ.get("UMT_RIG", "~/octoprint-rigs/live20"))
BASE = os.environ.get("UMT_BASE", "http://127.0.0.1:5097")
TAB = "#tab_plugin_uploadmanagertab"
DIALOG = "#plugin_uploadmanager_dialog"
VIEW_KEY = "plugin.uploadmanagertab.view"
FILES_LISTING = re.compile(r"/api/files\?")
WORKERS = int(os.environ.get("UMT_WORKERS", "4"))  # worker processes, one browser each
# The machine is shared; these flags cut each browser's footprint without changing page behaviour.
BROWSER_ARGS = ["--no-proxy-server", "--disable-gpu", "--disable-dev-shm-usage", "--disable-extensions",
                "--disable-background-networking", "--disable-component-update", "--disable-sync"]
ROWS_TARGET = 20  # visible rows the fill-vertical wrapper needs to overflow at 900 px; bulk files fill the rest

DEFAULTS = {
    "fill_horizontal": True,
    "fill_vertical": True,
    "hide_pattern": "@eaDir",
    "remember_view": True,
    "show_uploaded": True,
    "show_printed": True,
    "show_size": True,
    "files_icon": "gray",
}

with open(os.path.join(RIG, "apikey")) as fh:
    APIKEY = fh.read().strip()

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
RUN = uuid.uuid4().hex[:6]
created_files = []
created_dirs = []
created_lock = __import__("threading").Lock()
ALL_ERRORS = []
PROC_ERRORS = []  # errors from the pages this worker process has closed; returned with each job


# ---------- API ----------

def api(method, path, body=None, raw=None):
    headers = {"X-Api-Key": APIKEY}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if raw is not None:
        data, ctype = raw
        headers["Content-Type"] = ctype
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    with _opener.open(req, timeout=30) as resp:
        payload = resp.read()
        return json.loads(payload) if payload else None


SERVER_VERSION = api("GET", "/api/version")["server"]
# OctoPrint 2.0 lists every storage; 1.11 has one listing and no storage selector.
MULTI = not SERVER_VERSION.startswith("1.")


def set_settings(values):
    api("POST", "/api/settings", {"plugins": {"uploadmanagertab": values}})


def upload(folder, name):
    boundary = "umtprobe" + uuid.uuid4().hex
    folder_part = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"path\"\r\n\r\n{folder}\r\n"
        if folder else ""
    )
    head = (
        f"{folder_part}--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{name}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
    ).encode()
    body = head + b"G28\n" + f"\r\n--{boundary}--\r\n".encode()
    api("POST", "/api/files/local", raw=(body, f"multipart/form-data; boundary={boundary}"))
    with created_lock:
        created_files.append(f"{folder}/{name}" if folder else name)


def mkdir(name):
    body = urlencode({"foldername": name}).encode()
    api("POST", "/api/files/local", raw=(body, "application/x-www-form-urlencoded"))
    with created_lock:
        created_dirs.append(name)


def remove(rel):
    try:
        api("DELETE", "/api/files/local/" + rel)
    except Exception:
        pass


def build_fixtures():
    """One batch: the fewest bulk files that still overflow, plus the named fixtures."""
    existing = [f["name"] for f in api("GET", "/api/files/local")["files"] if f["name"] != "@eaDir"]
    # Rows already on the rig count toward the overflow, so the bulk count depends on them.
    bulk = max(0, ROWS_TARGET - len(existing) - 3)  # 3 = test.gcode, bench.gcode, umtdir
    jobs_up = [("", "test.gcode"), ("", "bench.gcode")]
    jobs_up += [("", f"umt_bulk_{i:02d}.gcode") for i in range(1, bulk + 1)]
    with ThreadPoolExecutor(16) as ex:
        futures = [ex.submit(upload, f, n) for f, n in jobs_up]
        futures += [ex.submit(mkdir, "@eaDir"), ex.submit(mkdir, "umtdir")]
        for fut in futures:
            fut.result()
    upload("umtdir", "umt_inner.gcode")
    names = [f["name"] for f in api("GET", "/api/files/local")["files"]]
    return "@eaDir" in names and "umtdir" in names


def remove_fixtures():
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(remove, reversed(created_files)))
        list(ex.map(remove, reversed(created_dirs)))


# ---------- page wrapper ----------

class P:
    """One browser context and page. Plugin settings come from cfg, not the server."""

    def __init__(self, browser, seed=None, settings=None, hold=False):
        self.ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        self.page = self.ctx.new_page()
        self.errs = []
        self.cfg = {"settings": dict(settings or {}), "hold": hold, "held": []}
        if seed is not None:
            raw = seed if isinstance(seed, str) else json.dumps(seed)
            self.ctx.add_init_script(
                "try { if (!sessionStorage.getItem('umt-seeded')) {"
                f" localStorage.setItem({json.dumps(VIEW_KEY)}, {json.dumps(raw)});"
                " sessionStorage.setItem('umt-seeded', '1'); } } catch (e) {}"
            )
        self.ctx.route("**/*", self._route)
        self.page.on("pageerror", lambda e: self.errs.append(f"pageerror {str(e)[:300]}"))
        self.page.on("console", self._console)
        self.page.on("response", lambda r: r.status >= 400 and "uploadmanagertab" in r.url
                     and self.errs.append(f"http {r.status} {r.url}"))

    def _console(self, m):
        if m.type == "error" and "uploadmanagertab" in ((m.text or "") + (m.location or {}).get("url", "")):
            self.errs.append(f"console {m.text[:300]}")

    def _route(self, route):
        url = route.request.url
        if not url.startswith(BASE) or "/webcam" in url:
            return route.abort()
        if self.cfg["hold"] and FILES_LISTING.search(url):
            self.cfg["held"].append(route)
            return None
        if url == BASE + "/api/settings" and route.request.method == "GET":
            resp = route.fetch()
            data = resp.json()
            data.setdefault("plugins", {})["uploadmanagertab"] = {**DEFAULTS, **self.cfg["settings"]}
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(data))
        return route.continue_()

    def open_tab(self, rows=True):
        self.page.wait_for_selector(f'a[href="{TAB}"]', state="visible", timeout=60000)
        self.page.click(f'a[href="{TAB}"]')
        if rows:
            self.page.wait_for_function(
                f"() => document.querySelectorAll('{DIALOG} tbody tr').length > 0", timeout=20000)

    def start(self, rows=True):
        self.page.goto(BASE + "/", wait_until="domcontentloaded")
        self.open_tab(rows)

    def reload(self, settings=None, view=None, hold=None, rows=True):
        """Reload for load-time behaviour. view: None keeps the key, "" removes it, else stored."""
        if settings is not None:
            self.cfg["settings"] = dict(settings)
        if hold is not None:
            self.cfg["hold"] = hold
        if view is not None:
            raw = None if view == "" else (view if isinstance(view, str) else json.dumps(view))
            self.page.evaluate("([k, v]) => { if (v === null) localStorage.removeItem(k);"
                               " else localStorage.setItem(k, v); }", [VIEW_KEY, raw])
        self.page.reload(wait_until="domcontentloaded")
        self.open_tab(rows)

    def wait_held(self, timeout=8.0):
        deadline = time.time() + timeout
        while not self.cfg["held"] and time.time() < deadline:
            self.page.wait_for_timeout(20)
        return bool(self.cfg["held"])

    def release(self, transform=None):
        self.cfg["hold"] = False
        held, self.cfg["held"] = self.cfg["held"], []
        for route in held:
            if transform is None:
                route.continue_()
            else:
                data = transform(route.fetch().json())
                route.fulfill(status=200, content_type="application/json", body=json.dumps(data))

    def wait_js(self, expr, arg=None, timeout=8000):
        try:
            self.page.wait_for_function(expr, arg=arg, timeout=timeout)
            return True
        except Exception:
            return False

    def eval(self, expr, arg=None):
        return self.page.evaluate(expr, arg) if arg is not None else self.page.evaluate(expr)

    def close(self):
        PROC_ERRORS.extend(self.errs)
        self.ctx.close()


VM_JS = "ko.dataFor(document.getElementById('plugin_uploadmanager_dialog'))"
SET_JS = "ko.dataFor(document.getElementById('settings_dialog')).settings.plugins.uploadmanagertab"
NAMES_JS = "[...document.querySelectorAll('#plugin_uploadmanager_dialog tbody td.title')].map(td => td.textContent.trim())"


def cur_path(p):
    return p.eval(f"() => {{ const v = {VM_JS}.currentPath(); return v ? v : ''; }}")


def wait_path(p, expected):
    return p.wait_js(f"(e) => {{ const v = {VM_JS}.currentPath(); return (v ? v : '') === e; }}", arg=expected)


def names(p):
    return p.eval(f"() => {NAMES_JS}")


def wait_names(p, cond):
    return p.wait_js(f"() => {{ const n = {NAMES_JS}; return ({cond}); }}")


def names_now(p, cond):
    """Predicate on the rows as they are now. Knockout updates the list synchronously, so a live
    change must already show here: no wait, navigation, refresh or reload is allowed before it."""
    return p.eval(f"() => {{ const n = {NAMES_JS}; return ({cond}); }}")


def stored_view(p):
    return p.eval("(k) => window.localStorage.getItem(k)", VIEW_KEY)


def stored_obj(p):
    return json.loads(stored_view(p) or "null") or {}


def set_live(p, key, value):
    p.eval(f"([k, v]) => {{ {SET_JS}[k](v); }}", [key, value])


def set_list_style(p, style):
    p.eval(f"(s) => {{ {VM_JS}.listStyle(s); }}", style)


def enter_folder(p, name):
    p.page.locator(f"{DIALOG} tbody tr", has_text=name).first.dblclick()
    return wait_path(p, name)


def click_back(p):
    p.page.locator(f"{DIALOG} tbody tr", has_text="Back").first.click()
    return wait_path(p, "")


def refresh(p):
    """Push a new listing into the bundled view model, as a file refresh does (synchronous)."""
    if MULTI:
        p.eval("() => { const vm = " + VM_JS + "; vm.files.storageFiles({...vm.files.storageFiles()}); }")
    else:
        p.eval("() => { const vm = " + VM_JS + "; vm.files.allItems([...vm.files.allItems()]); }")


def add_sdcard(data):
    """Test-only: the listing also offers an 'sdcard' storage holding the same files as local."""
    data["sdcard"] = json.loads(json.dumps(data["local"]))
    return data


def open_settings(p):
    p.eval("() => $('#settings_dialog').modal('show')")
    p.page.wait_for_selector("#settings-uploadmanagertab-fill-horizontal", state="attached", timeout=30000)


def close_settings(p):
    p.eval("() => $('#settings_dialog').modal('hide')")
    p.wait_js("() => !document.getElementById('settings_dialog').classList.contains('in')")


def click_setting(p, element_id, state):
    p.eval("([id, st]) => { const el = document.getElementById(id); if (el.checked !== st) el.click(); }",
           [element_id, state])


def set_setting_element(p, element_id, value):
    p.eval("([id, v]) => { const el = document.getElementById(id); el.value = v;"
           " el.dispatchEvent(new Event('change', {bubbles: true})); }", [element_id, value])


METRICS_JS = """() => {
    const d = document.getElementById('plugin_uploadmanager_dialog');
    const r = d.getBoundingClientRect();
    const t = getComputedStyle(document.getElementById('tabs_content'));
    const w = d.querySelector('.table-wrapper');
    const wr = w ? w.getBoundingClientRect() : null;
    return {
        width: r.width, bottom: r.bottom, height: r.height, inline: d.style.height,
        padL: parseFloat(t.paddingLeft), padR: parseFloat(t.paddingRight),
        padB: parseFloat(t.paddingBottom), innerH: window.innerHeight,
        overflow: w ? getComputedStyle(w).overflowY : null,
        clientH: w ? w.clientHeight : null, scrollH: w ? w.scrollHeight : null,
        wrapBottom: wr ? wr.bottom : null,
    };
}"""

BOTTOM_OK_JS = """() => {
    const d = document.getElementById('plugin_uploadmanager_dialog');
    const pb = parseFloat(getComputedStyle(document.getElementById('tabs_content')).paddingBottom) || 0;
    return d.style.height !== '' && Math.abs(d.getBoundingClientRect().bottom - (window.innerHeight - pb)) <= 2;
}"""


def column_state(p, col):
    return p.eval("""(col) => {
        const cells = [...document.querySelectorAll(
            '#plugin_uploadmanager_dialog th.' + col + ', #plugin_uploadmanager_dialog td.' + col)];
        return cells.map(c => getComputedStyle(c).display);
    }""", col)


def column_hidden_js(col):
    return (f"() => {{ const c = [...document.querySelectorAll("
            f"'#plugin_uploadmanager_dialog th.{col}, #plugin_uploadmanager_dialog td.{col}')];"
            " return c.length > 0 && c.every(x => getComputedStyle(x).display === 'none'); }")


def column_shown_js(col):
    return (f"() => {{ const c = [...document.querySelectorAll("
            f"'#plugin_uploadmanager_dialog th.{col}, #plugin_uploadmanager_dialog td.{col}')];"
            " return c.length > 0 && c.every(x => getComputedStyle(x).display !== 'none'); }")


def back_row_visible(p):
    return p.eval("""() => [...document.querySelectorAll('#plugin_uploadmanager_dialog tbody tr')]
        .some(tr => tr.textContent.indexOf('Back') >= 0 && getComputedStyle(tr).display !== 'none')""")


ICON_JS = """() => {
    const b = $('#files_wrapper .accordion-heading .fa-folder-tree').closest('.accordion-heading-button')[0];
    if (!b) return null;
    return {inactive: b.classList.contains('uploadmanagertab-inactive'),
            hidden: b.classList.contains('uploadmanagertab-hidden'),
            opacity: getComputedStyle(b).opacity,
            display: getComputedStyle(b).display};
}"""

LAYOUT_JS = """() => {
    const table = document.querySelector('#plugin_uploadmanager_dialog table');
    const vis = el => getComputedStyle(el).display !== 'none';
    const sum = cs => cs.reduce((a, c) => a + c.getBoundingClientRect().width, 0);
    const tw = table.getBoundingClientRect().width;
    const headers = [...table.querySelectorAll('thead th')].filter(vis);
    const rows = [...table.querySelectorAll('tbody tr')];
    const data = rows.filter(tr => tr.querySelector('td.title')).map(tr => {
        const cs = [...tr.children].filter(vis);
        return {sum: sum(cs), lefts: cs.map(c => c.getBoundingClientRect().left)};
    });
    const back = rows.find(tr => !tr.querySelector('td.title') && tr.textContent.indexOf('Back') >= 0);
    let backInfo = null;
    if (back) {
        const cs = [...back.children].filter(vis);
        backInfo = {sum: sum(cs), cells: cs.length};
    }
    return {tw: tw, headers: headers.length, hl: headers.map(h => h.getBoundingClientRect().left),
            data: data, back: backInfo};
}"""


def layout(rec, p, label, in_folder):
    """Visible cells must fill the table, line up with the headers, and the Back row must span it."""
    m = p.eval(LAYOUT_JS)
    tw = m["tw"]
    rec.ok(m["headers"] >= 2, f"{label}: header cells missing")
    rec.ok(len(m["data"]) > 0, f"{label}: no data rows to measure")
    for i, row in enumerate(m["data"]):
        rec.ok(abs(row["sum"] - tw) <= 2, f"{label}: data row {i} visible cells sum {row['sum']:.0f} of table {tw:.0f}")
        rec.ok(len(row["lefts"]) == m["headers"],
               f"{label}: data row {i} shows {len(row['lefts'])} cells under {m['headers']} headers")
        for h, d in zip(m["hl"], row["lefts"]):
            rec.ok(abs(h - d) <= 2, f"{label}: data cell at {d:.0f} does not line up with header at {h:.0f}")
    if in_folder:
        rec.ok(m["back"] is not None, f"{label}: no Back row")
        if m["back"] is not None:
            rec.ok(abs(m["back"]["sum"] - tw) <= 2, f"{label}: Back row spans {m['back']['sum']:.0f} of table {tw:.0f}")
    else:
        rec.ok(m["back"] is None, f"{label}: Back row shown at root")


# ---------- recording ----------

class Rec:
    def __init__(self, num, name):
        self.num = num
        self.name = name
        self.fails = []
        self.skips = []
        self.elapsed = 0.0
        self.errors = []

    def ok(self, cond, msg):
        if not cond:
            self.fails.append(msg)
        return cond

    def skip(self, what):
        self.skips.append(what)


def skip_line(what):
    return f"SKIP {what}"


# ---------- jobs ----------

def job_panel(rec, browser):
    p = P(browser, settings={})
    p.start()
    open_settings(p)
    p.page.wait_for_timeout(0)
    for box in ["fill-horizontal", "fill-vertical", "remember-view", "show-uploaded", "show-printed", "show-size"]:
        rec.ok(p.page.is_checked(f"#settings-uploadmanagertab-{box}"), f"{box} not checked by default")
    rec.ok(p.page.input_value("#settings-uploadmanagertab-hide-pattern") == "@eaDir", "hide pattern default wrong")
    rec.ok(p.page.input_value("#settings-uploadmanagertab-files-icon") == "gray", "files icon default wrong")
    # The page reads defaults through the settings response rewrite, so also read the server's own
    # settings (not rewritten) and check the plugin block there.
    server_block = api("GET", "/api/settings")["plugins"]["uploadmanagertab"]
    rec.ok(all(server_block.get(k) == v for k, v in DEFAULTS.items()),
           f"server settings differ from the defaults: {server_block}")
    close_settings(p)
    p.close()


def job_fill_horizontal(rec, browser):
    p = P(browser)
    p.start()
    on = p.eval(METRICS_JS)
    pad_sum = on["padL"] + on["padR"]
    rec.ok(pad_sum > 0, "tabs_content has no horizontal padding to test")
    open_settings(p)
    click_setting(p, "settings-uploadmanagertab-fill-horizontal", False)
    close_settings(p)
    p.wait_js("(t) => Math.abs(document.getElementById('plugin_uploadmanager_dialog').getBoundingClientRect().width - t) <= 1.5",
              arg=on["width"] - pad_sum)
    off = p.eval(METRICS_JS)
    rec.ok(abs((on["width"] - off["width"]) - pad_sum) <= 1.5,
           f"width delta {on['width'] - off['width']:.1f} vs padding {pad_sum:.1f}")
    open_settings(p)
    click_setting(p, "settings-uploadmanagertab-fill-horizontal", True)
    close_settings(p)
    back_ok = p.wait_js("(t) => Math.abs(document.getElementById('plugin_uploadmanager_dialog').getBoundingClientRect().width - t) <= 1.5",
                        arg=on["width"])
    rec.ok(back_ok, "re-enabling did not restore the width")
    p.close()


def job_fill_vertical(rec, browser):
    p = P(browser)
    p.start()
    m = p.eval(METRICS_JS)
    rec.ok(m["inline"] != "", "no inline height with fill vertical on")
    rec.ok(abs(m["bottom"] - (m["innerH"] - m["padB"])) <= 2,
           f"bottom {m['bottom']:.1f} vs {m['innerH'] - m['padB']:.1f}")
    rec.ok(m["overflow"] in ("auto", "scroll"), f"wrapper overflow {m['overflow']}")
    rec.ok(m["clientH"] < m["scrollH"], "wrapper does not scroll its rows")
    rec.ok(m["wrapBottom"] <= m["bottom"] + 1, "wrapper extends below the dialog")
    p.page.set_viewport_size({"width": 1400, "height": 700})
    p.wait_js(BOTTOM_OK_JS)
    m2 = p.eval(METRICS_JS)
    rec.ok(abs(m2["bottom"] - (m2["innerH"] - m2["padB"])) <= 2, "bottom did not follow resize")
    rec.ok(m2["height"] < m["height"] - 100, f"height {m['height']:.0f} -> {m2['height']:.0f} on resize")
    p.page.set_viewport_size({"width": 1400, "height": 900})
    p.wait_js(BOTTOM_OK_JS)

    p.reload(settings={"fill_vertical": False})
    m3 = p.eval(METRICS_JS)
    rec.ok(m3["inline"] == "", f"inline height present with fill vertical off: {m3['inline']}")
    rec.ok(m3["overflow"] == "visible", f"wrapper still clips: {m3['overflow']}")
    rec.ok(m3["clientH"] >= m3["scrollH"], "wrapper scrolls with fill vertical off")
    rec.ok(p.eval("() => document.documentElement.scrollHeight > window.innerHeight"),
           "page does not overflow the window")
    p.eval("() => window.scrollTo(0, 300)")
    rec.ok(p.eval("() => window.scrollY") > 0, "page does not scroll")

    # Height floor: in a short window the raw height (innerHeight - top - padding-bottom) is under
    # 320, so only the floor keeps the dialog at 320. The JS floor (Math.max(320, height)) and the
    # CSS min-height: 320px on .uploadmanagertab-fill-vertical both hold this line, so a mutation
    # must remove both to fail here.
    set_live(p, "fill_vertical", True)
    p.wait_js("() => document.getElementById('plugin_uploadmanager_dialog').style.height !== ''")
    p.eval("() => window.scrollTo(0, 0)")
    p.page.set_viewport_size({"width": 1400, "height": 400})
    # At 400 px the floor (320) is taller than the room below the dialog, so the wait is on the floor itself.
    p.wait_js("() => Math.abs(parseFloat(document.getElementById('plugin_uploadmanager_dialog').style.height) - 320) < 0.5")
    m4 = p.eval(METRICS_JS)
    raw = m4["innerH"] - (m4["bottom"] - m4["height"]) - m4["padB"]
    rec.ok(raw < 320, f"short window is not short enough to test the floor: raw {raw:.0f}")
    rec.ok(m4["height"] >= 320 - 0.5, f"dialog {m4['height']:.1f}px under the 320px floor")
    p.close()


def job_hide_pattern(rec, browser):
    p = P(browser)
    p.start()
    n = names(p)
    rec.ok("@eaDir" not in n, "@eaDir shown by default")
    rec.ok("bench.gcode" in n and "umtdir" in n, "non-matching items missing by default")

    set_live(p, "hide_pattern", "")
    rec.ok(names_now(p, "n.includes('@eaDir')"), "@eaDir hidden with an empty pattern")

    set_live(p, "hide_pattern", "@EADIR")
    rec.ok(names_now(p, "!n.includes('@eaDir')"), "@EADIR did not hide @eaDir (case)")

    set_live(p, "hide_pattern", "te*")
    rec.ok(names_now(p, "!n.includes('test.gcode')"), "te* did not hide test.gcode")
    n = names(p)
    rec.ok("bench.gcode" in n and "@eaDir" in n and "umtdir" in n, "te* hid other names")

    mark = len(p.errs)
    set_live(p, "hide_pattern", "[(")
    rec.ok(names_now(p, "n.includes('test.gcode')"), "[( hid something")
    p.page.wait_for_timeout(300)  # negative assertion: a short settle is enough
    rec.ok(not p.errs[mark:], f"[( raised errors: {p.errs[mark:][:2]}")

    # List parsing: spaces around each comma-separated entry are trimmed.
    set_live(p, "hide_pattern", "  te*  ,   @eaDir  ")
    rec.ok(names_now(p, "!n.includes('test.gcode') && !n.includes('@eaDir')"),
           "padded list not trimmed")
    n = names(p)
    rec.ok("bench.gcode" in n and "umtdir" in n, "padded list hid non-matching names")
    p.close()


def job_restore_hold(rec, browser):
    """Restoring holds the listing back: the key must stay put, the folder applies on arrival."""
    p = P(browser, seed={"path": "umtdir", "storage": "local", "listStyle": "files_folders"}, hold=True)
    p.start(rows=False)
    rec.ok(p.wait_held(), "listing was never held, so restore did not wait")
    during = stored_obj(p)
    rec.ok(during.get("path") == "umtdir", f"key path during restore: {during.get('path')!r}")
    rec.ok(during.get("listStyle") == "files_folders", f"key listStyle during restore: {during.get('listStyle')!r}")
    rec.ok(cur_path(p) == "", "folder applied before the listing arrived")
    p.release()
    rec.ok(wait_path(p, "umtdir"), "folder not restored once the listing arrived")
    after = stored_obj(p)
    rec.ok(after.get("path") == "umtdir" and after.get("listStyle") == "files_folders", f"key after restore: {after}")
    p.close()


def job_restore_dispose(rec, browser):
    """The one-shot is disposed after it fires: a later listing update must not move the user."""
    p = P(browser, seed={"path": "umtdir", "storage": "local", "listStyle": "folders_files"}, hold=True)
    p.start(rows=False)
    rec.ok(p.wait_held(), "dispose case: listing not held")
    p.release()
    rec.ok(wait_path(p, "umtdir"), "dispose case: folder not restored")
    rec.ok(click_back(p), "Back did not return to root")
    refresh(p)
    p.page.wait_for_timeout(300)  # negative assertion: a short settle is enough
    rec.ok(cur_path(p) == "", f"a later listing update moved the user to {cur_path(p)!r}")
    p.close()


def job_restore_gone(rec, browser):
    """Already loaded and the saved folder is gone: settle at once, so a later navigation is stored."""
    p = P(browser, seed={"path": "nosuch", "storage": "local", "listStyle": "folders_files"})
    p.start()
    rec.ok(cur_path(p) == "", "gone folder did not fall back to root")
    rec.ok(enter_folder(p, "umtdir"), "navigation after a gone folder did not open")
    rec.ok(stored_obj(p).get("path") == "umtdir", f"navigation after a gone folder was not stored: {stored_obj(p)}")
    p.close()


def job_restore_sdcard(rec, browser):
    """A saved non-local storage survives the wait when the late listing offers it (2.0 only)."""
    if not MULTI:
        rec.skip("saved non-local storage survives the wait (no storage selector on 1.11)")
        return
    p = P(browser, seed={"path": "umtdir", "storage": "sdcard", "listStyle": "mixed"}, hold=True)
    p.start(rows=False)
    rec.ok(p.wait_held(), "sdcard case: listing not held")
    rec.ok(stored_obj(p).get("storage") == "sdcard", f"key lost the saved storage during the wait: {stored_obj(p)}")
    p.release(transform=add_sdcard)
    rec.ok(wait_path(p, "umtdir"), "saved sdcard folder not restored after the late listing")
    st = p.eval(f"() => {VM_JS}.currentStorage()")
    rec.ok(st == "sdcard", f"saved sdcard storage lost to {st!r} during the wait")
    rec.ok(stored_obj(p).get("storage") == "sdcard", f"sdcard not stored: {stored_obj(p)}")
    p.close()


def job_unavailable_storage(rec, browser, path):
    """A stored storage that is not offered is ignored; the view stays on local (2.0 only)."""
    if not MULTI:
        rec.skip("unavailable storage falls back to local (no storage selector on 1.11)")
        return
    p = P(browser, seed={"path": path, "storage": "sdcard", "listStyle": "mixed"})
    p.start()
    st = p.eval(f"() => {VM_JS}.currentStorage()")
    rec.ok(st == "local", f"unavailable storage applied for {path!r}: {st!r}")
    if path:
        rec.ok(wait_path(p, "umtdir"), "stored folder not found under local after storage fallback")
    p.close()


def job_restore_basic(rec, browser):
    """Stored path and list style are written as they change, and both come back after a reload."""
    p = P(browser)
    p.start()
    rec.ok(enter_folder(p, "umtdir"), "folder did not open")
    rec.ok(stored_obj(p).get("path") == "umtdir", f"stored path {stored_obj(p).get('path')!r}")
    set_list_style(p, "files_folders")
    rec.ok(stored_obj(p).get("listStyle") == "files_folders", "listStyle not stored")
    p.reload()
    rec.ok(wait_path(p, "umtdir"), "folder not restored after reload")
    style = p.eval(f"() => {VM_JS}.listStyle()")
    rec.ok(style == "files_folders", f"listStyle not restored: {style!r}")
    p.close()


def job_startup_race(rec, browser):
    """A reload during startup must not overwrite the saved path with ""."""
    p = P(browser, seed={"path": "umtdir", "storage": "local", "listStyle": "folders_files"})
    p.page.goto(BASE + "/", wait_until="commit")
    p.page.reload(wait_until="domcontentloaded")
    p.open_tab()
    rec.ok(wait_path(p, "umtdir"), "startup reload lost the saved folder")
    rec.ok(stored_obj(p).get("path") == "umtdir", f"startup reload overwrote path: {stored_obj(p).get('path')!r}")
    p.close()


def job_deleted_and_corrupt(rec, browser):
    gone = f"umtgone{RUN}"
    mkdir(gone)
    p = P(browser)
    p.start()
    rec.ok(enter_folder(p, gone), f"{gone} did not open")
    remove(gone)
    mark = len(p.errs)
    p.reload(view=None)
    rec.ok(cur_path(p) == "", "deleted folder did not fall back to root")
    rec.ok(not p.errs[mark:], f"errors after deleted folder: {p.errs[mark:][:2]}")

    p.close()


def job_corrupt_key(rec, browser):
    p = P(browser, seed="{")
    p.start()
    rec.ok(cur_path(p) == "", "corrupt key did not fall back to root")
    rec.ok(not p.errs, f"errors after corrupt key: {p.errs[:2]}")
    p.close()


def job_remember_off_at_load(rec, browser):
    """Remember view off at load removes a stored key, and writes nothing while off."""
    p = P(browser, seed={"path": "umtdir", "storage": "local", "listStyle": "mixed"},
          settings={"remember_view": False})
    p.start()
    rec.ok(stored_view(p) is None, "setting off did not remove the key on load")
    rec.ok(enter_folder(p, "umtdir"), "folder did not open with remember off")
    rec.ok(stored_view(p) is None, "view written while remember is off")
    p.close()


def job_remember_off_reload(rec, browser):
    """A stored key is still removed on a later load with the setting off."""
    p = P(browser, seed={"path": "umtdir", "storage": "local", "listStyle": "mixed"},
          settings={"remember_view": False})
    p.start()
    rec.ok(stored_view(p) is None, "key kept on load with remember off")
    p.reload(view={"path": "umtdir", "storage": "local", "listStyle": "mixed"})
    rec.ok(stored_view(p) is None, "key reappeared on a later load with remember off")
    p.close()


def job_storage_change(rec, browser):
    """A storage change writes the key (2.0 only): at root, switch storage in the page, read the key."""
    if not MULTI:
        rec.skip("storage change writes the key (no storage selector on 1.11)")
        return
    p = P(browser)
    p.start()
    set_storage = f"(s) => {{ {VM_JS}.currentStorage(s); }}"
    p.eval(set_storage, "sdcard")
    rec.ok(p.wait_js("() => { try { return JSON.parse(localStorage.getItem('plugin.uploadmanagertab.view') || 'null').storage === 'sdcard'; } catch (e) { return false; } }"),
           f"storage change not stored: {stored_obj(p)}")
    p.eval(set_storage, "local")
    rec.ok(p.wait_js("() => { try { return JSON.parse(localStorage.getItem('plugin.uploadmanagertab.view') || 'null').storage === 'local'; } catch (e) { return false; } }"),
           f"storage change back not stored: {stored_obj(p)}")
    p.close()


def job_columns_at_load(rec, browser, col, key):
    p = P(browser, seed={"path": "umtdir", "storage": "local", "listStyle": "folders_files"},
          settings={key: False})
    p.start()
    rec.ok(wait_path(p, "umtdir"), f"{col}: folder not open")
    states = column_state(p, col)
    rec.ok(len(states) > 0, f"{col}: no cells found")
    rec.ok(all(s == "none" for s in states), f"{col}: cells still displayed {states[:4]}")
    rec.ok(back_row_visible(p), f"{col}: Back row not rendered")
    p.close()


def job_layout_combos(rec, browser, combos):
    p = P(browser)
    p.start()
    for show_uploaded, show_printed, show_size in combos:
        label = (f"uploaded={'on' if show_uploaded else 'off'} printed={'on' if show_printed else 'off'} "
                 f"size={'on' if show_size else 'off'}")
        set_live(p, "show_uploaded", show_uploaded)
        set_live(p, "show_printed", show_printed)
        set_live(p, "show_size", show_size)
        layout(rec, p, f"{label} root", False)
        rec.ok(enter_folder(p, "umtdir"), f"{label}: folder did not open")
        layout(rec, p, f"{label} folder", True)
        refresh(p)
        layout(rec, p, f"{label} folder after refresh", True)
        rec.ok(click_back(p), f"{label}: Back row did not navigate up")
        layout(rec, p, f"{label} root after navigating out", False)
        refresh(p)
        layout(rec, p, f"{label} root after refresh", False)
    p.close()


def job_icon_gray(rec, browser):
    p = P(browser)
    p.start()
    on = p.eval(ICON_JS)
    rec.ok(on is not None, "files panel icon not found")
    if on is not None:
        rec.ok(on["inactive"] and abs(float(on["opacity"]) - 0.35) < 0.01, f"gray not applied on the tab: {on}")
    p.eval("() => $('#tabs a[href=\"#control\"]').tab('show')")
    p.wait_js("() => !document.querySelector('#files_wrapper .accordion-heading .fa-folder-tree')"
              ".closest('.accordion-heading-button').classList.contains('uploadmanagertab-inactive')")
    off = p.eval(ICON_JS)
    if off is not None:
        rec.ok((not off["inactive"]) and abs(float(off["opacity"]) - 1.0) < 0.01, f"gray still applied off the tab: {off}")
    p.page.click(f'a[href="{TAB}"]')
    p.wait_js("() => !!document.querySelector('#files_wrapper .accordion-heading .fa-folder-tree')"
              ".closest('.accordion-heading-button').classList.contains('uploadmanagertab-inactive')")
    p.close()


def job_icon_hide(rec, browser):
    p = P(browser, settings={"files_icon": "hide"})
    p.start()
    hid = p.eval(ICON_JS)
    rec.ok(hid is not None and hid["display"] == "none", f"hide not applied on the tab: {hid}")
    p.eval("() => $('#tabs a[href=\"#control\"]').tab('show')")
    hid = p.eval(ICON_JS)
    rec.ok(hid is not None and hid["display"] == "none", f"hide not applied off the tab: {hid}")
    p.close()


def job_live_apply(rec, browser):
    p = P(browser)
    p.start()
    open_settings(p)

    # Hide pattern, live, through the settings input.
    set_setting_element(p, "settings-uploadmanagertab-hide-pattern", "te*")
    rec.ok(names_now(p, "!n.includes('test.gcode') && n.includes('bench.gcode')"), "hide pattern not live")
    set_setting_element(p, "settings-uploadmanagertab-hide-pattern", "")
    rec.ok(names_now(p, "n.includes('test.gcode')"), "empty pattern did not show test.gcode live")
    set_setting_element(p, "settings-uploadmanagertab-hide-pattern", "@eaDir")
    rec.ok(names_now(p, "!n.includes('@eaDir')"), "restored pattern did not hide @eaDir live")

    # Columns, live.
    for box, col in [("show-uploaded", "uploaded"), ("show-printed", "printed"), ("show-size", "size")]:
        click_setting(p, f"settings-uploadmanagertab-{box}", False)
        rec.ok(p.wait_js(column_hidden_js(col)), f"{col} not hidden live: {column_state(p, col)[:3]}")
        click_setting(p, f"settings-uploadmanagertab-{box}", True)
        rec.ok(p.wait_js(column_shown_js(col)), f"{col} not shown again live: {column_state(p, col)[:3]}")

    # Columns, live, inside a folder: a data row must still fill the table after the toggle.
    close_settings(p)  # the open settings modal would block the folder double-click
    rec.ok(enter_folder(p, "umtdir"), "folder did not open for the column span check")
    set_live(p, "show_size", False)
    fill = p.eval("""() => {
        const t = document.querySelector('#plugin_uploadmanager_dialog table');
        const row = [...t.querySelectorAll('tbody tr')].find(tr => tr.querySelector('td.title'));
        const cs = [...row.children].filter(c => getComputedStyle(c).display !== 'none');
        return [t.getBoundingClientRect().width, cs.reduce((a, c) => a + c.getBoundingClientRect().width, 0)];
    }""")
    rec.ok(abs(fill[1] - fill[0]) <= 2, f"in a folder, size off: data row cells sum {fill[1]:.0f} of table {fill[0]:.0f}")
    set_live(p, "show_size", True)
    rec.ok(click_back(p), "Back did not return to root after the column span check")

    # Files panel icon, live (still on this tab).
    set_setting_element(p, "settings-uploadmanagertab-files-icon", "hide")
    rec.ok(p.wait_js("() => getComputedStyle(document.querySelector('#files_wrapper .accordion-heading .fa-folder-tree')"
                     ".closest('.accordion-heading-button')).display === 'none'"), "icon hide not live")
    set_setting_element(p, "settings-uploadmanagertab-files-icon", "gray")
    rec.ok(p.wait_js("() => { const b = document.querySelector('#files_wrapper .accordion-heading .fa-folder-tree')"
                     ".closest('.accordion-heading-button'); return getComputedStyle(b).display !== 'none' && b.classList.contains('uploadmanagertab-inactive'); }"),
           "icon gray not live on tab")

    # Fill vertical, live, on to off and back.
    click_setting(p, "settings-uploadmanagertab-fill-vertical", False)
    rec.ok(p.wait_js("() => { const d = document.getElementById('plugin_uploadmanager_dialog');"
                     " return d.style.height === '' && getComputedStyle(d.querySelector('.table-wrapper')).overflowY === 'visible'; }"),
           "fill vertical off not live")
    click_setting(p, "settings-uploadmanagertab-fill-vertical", True)
    rec.ok(p.wait_js("() => document.getElementById('plugin_uploadmanager_dialog').style.height !== ''"),
           "fill vertical on not live")

    # Remember view, live, on to off: key removed at once, no writes afterwards.
    close_settings(p)
    rec.ok(enter_folder(p, "umtdir"), "folder did not open before remember change")
    rec.ok(stored_obj(p).get("path") == "umtdir", "view not stored before remember change")
    open_settings(p)
    click_setting(p, "settings-uploadmanagertab-remember-view", False)
    rec.ok(p.wait_js("() => localStorage.getItem('plugin.uploadmanagertab.view') === null"),
           "remember off did not remove the key live")
    close_settings(p)
    rec.ok(click_back(p), "Back did not return to root with remember off")
    p.page.wait_for_timeout(300)  # negative assertion: a short settle is enough
    rec.ok(stored_view(p) is None, "view written after remember turned off")
    open_settings(p)
    click_setting(p, "settings-uploadmanagertab-remember-view", True)
    rec.ok(p.wait_js("() => localStorage.getItem('plugin.uploadmanagertab.view') !== null"),
           "remember on did not write live")
    close_settings(p)

    # Close reverts unsaved live changes.
    open_settings(p)
    set_setting_element(p, "settings-uploadmanagertab-hide-pattern", "te*")
    click_setting(p, "settings-uploadmanagertab-fill-vertical", False)
    rec.ok(wait_names(p, "!n.includes('test.gcode')"), "pre-close live change not applied")
    p.page.click('[data-test-id="settings-close-button"]')
    reverted = p.wait_js(f"() => {{ const s = {SET_JS}; return s.hide_pattern() === '@eaDir' && s.fill_vertical() === true; }}")
    vals = p.eval(f"() => {{ const s = {SET_JS}; return {{hide: s.hide_pattern(), fv: s.fill_vertical()}}; }}")
    rec.ok(reverted, f"Close did not revert settings: {vals}")
    rec.ok(wait_names(p, "n.includes('test.gcode')"), "Close did not revert the hide pattern live")
    rec.ok(p.eval(METRICS_JS)["inline"] != "", "Close did not revert fill vertical live")
    p.close()


# ---------- driver ----------

_WORKER = __import__("threading").local()
_BROWSERS = []


def worker_browser():
    """One Playwright and browser per worker thread, reused by every job that thread runs."""
    if not hasattr(_WORKER, "browser"):
        pw = sync_playwright().start()
        _WORKER.pw = pw
        _WORKER.browser = pw.chromium.launch(headless=True, args=BROWSER_ARGS)
        _BROWSERS.append(_WORKER.pw)
    return _WORKER.browser


def run_job(job):
    """Runs in a worker process: jobs share no server state, so processes give real parallelism."""
    num, name, fn = job
    rec = Rec(num, name)
    t0 = time.time()
    del PROC_ERRORS[:]
    try:
        fn(rec, worker_browser())
    except Exception as exc:
        rec.fails.append(f"exception {type(exc).__name__}: {str(exc)[:300]}")
    rec.elapsed = time.time() - t0
    rec.errors = list(PROC_ERRORS)
    return rec


def build_jobs():
    combos = list(itertools.product([True, False], repeat=3))
    return [
        (1, "1 panel", job_panel),
        (2, "2 fill horizontal", job_fill_horizontal),
        (3, "3 fill vertical", job_fill_vertical),
        (4, "4 hide pattern", job_hide_pattern),
        (5, "5 remember view", job_restore_hold),
        (5, "5 remember view", job_restore_dispose),
        (5, "5 remember view", job_restore_gone),
        (5, "5 remember view", job_restore_sdcard),
        (5, "5 remember view", partial(job_unavailable_storage, path="umtdir")),
        (5, "5 remember view", partial(job_unavailable_storage, path="")),
        (5, "5 remember view", job_restore_basic),
        (5, "5 remember view", job_startup_race),
        (5, "5 remember view", job_deleted_and_corrupt),
        (5, "5 remember view", job_corrupt_key),
        (5, "5 remember view", job_remember_off_at_load),
        (5, "5 remember view", job_remember_off_reload),
        (5, "5 remember view", job_storage_change),
        (6, "6 columns", partial(job_columns_at_load, col="uploaded", key="show_uploaded")),
        (6, "6 columns", partial(job_columns_at_load, col="printed", key="show_printed")),
        (6, "6 columns", partial(job_columns_at_load, col="size", key="show_size")),
        (6, "6 columns", partial(job_layout_combos, combos=combos[0:2])),
        (6, "6 columns", partial(job_layout_combos, combos=combos[2:4])),
        (6, "6 columns", partial(job_layout_combos, combos=combos[4:6])),
        (6, "6 columns", partial(job_layout_combos, combos=combos[6:8])),
        (7, "7 files icon", job_icon_gray),
        (7, "7 files icon", job_icon_hide),
        (9, "9 live apply", job_live_apply),
    ]


CHECK_ORDER = [1, 2, 3, 4, 5, 6, 7, 9, 8]
CHECK_NAMES = {1: "1 panel", 2: "2 fill horizontal", 3: "3 fill vertical", 4: "4 hide pattern",
               5: "5 remember view", 6: "6 columns", 7: "7 files icon", 8: "8 no errors", 9: "9 live apply"}


def main():
    T0 = time.time()
    only = os.environ.get("UMT_ONLY", "").strip()
    wanted = {int(x) for x in only.split(",") if x.strip()} if only else None
    results = []
    failures = 0
    try:
        set_settings(DEFAULTS)
        if not build_fixtures():
            print("FAIL setup-fixtures server does not list the fixtures", flush=True)
            failures += 1
            return failures
        jobs = [j for j in build_jobs() if wanted is None or j[0] in wanted]
        with ProcessPoolExecutor(max_workers=WORKERS, mp_context=get_context("spawn")) as ex:
            results = list(ex.map(run_job, jobs))
        ALL_ERRORS.extend(err for rec in results for err in rec.errors)
        by_num = {}
        for rec in results:
            by_num.setdefault(rec.num, []).append(rec)
        for num in CHECK_ORDER:
            if num == 8:
                if wanted is not None and 8 not in wanted:
                    continue
                rec8 = Rec(8, CHECK_NAMES[8])
                rec8.ok(not ALL_ERRORS, f"{len(ALL_ERRORS)} error(s): {ALL_ERRORS[:3]}")
                by_num[8] = [rec8]
            if num not in by_num:
                continue
            recs = by_num[num]
            for rec in recs:
                for what in rec.skips:
                    print(skip_line(what), flush=True)
            fails = [m for rec in recs for m in rec.fails]
            if fails:
                print(f"FAIL {CHECK_NAMES[num]} " + "; ".join(fails)[:1500], flush=True)
                failures += 1
            else:
                print(f"PASS {CHECK_NAMES[num]}", flush=True)
            print(f"TIME {CHECK_NAMES[num]} slowest job {max(r.elapsed for r in recs):.1f}s", flush=True)
            for idx, rec in enumerate(recs):
                print(f"TIME   job {idx + 1} {rec.elapsed:.1f}s", flush=True)
    finally:
        try:
            set_settings(DEFAULTS)
        except Exception as exc:
            print(f"FAIL restore-defaults {type(exc).__name__}", flush=True)
            failures += 1
        remove_fixtures()
        for pw in _BROWSERS:
            try:
                pw.stop()
            except Exception:
                pass
        print(f"TIME total {time.time() - T0:.1f}s", flush=True)
    return failures


if __name__ == "__main__":
    try:
        failed = main()
    except Exception as exc:
        print(f"FAIL harness {type(exc).__name__}: {str(exc)[:300]}", flush=True)
        failed = 1
    sys.exit(1 if failed else 0)
