# OctoPrint-UploadManagerTab

Shows OctoPrint's Upload Manager in a tab instead of a dialog.

OctoPrint's bundled Upload Manager opens as a pop-up window over the page. This plugin moves that same
window into its own **Upload Manager** tab, so your printer's files stay one click away with nothing
covering the page. It adds no new file features. Printing, moving and removing files all work the way
OctoPrint already does them.

## Prerequisites

- OctoPrint 1.11.0 or newer. Tested on 1.11.8 and 2.0.0rc5.
- The bundled **Upload Manager** plugin enabled (it ships with OctoPrint).

## Install

Install from the OctoPrint Plugin Manager using this URL:

```
https://github.com/synman/OctoPrint-UploadManagerTab/archive/main.zip
```

Full steps, uninstall and upgrade notes are in [docs/install-guide.md](docs/install-guide.md).

## Usage

Open the **Upload Manager** tab at the top of OctoPrint. Use the eight settings under
**Settings > Upload Manager Tab** to choose the columns, the layout and what is hidden.

The day-to-day guide, with a printer example for every setting, is
[docs/operators-guide.md](docs/operators-guide.md).

Something not right? See [docs/troubleshooting.md](docs/troubleshooting.md). Unfamiliar word? See
[docs/glossary.md](docs/glossary.md).

## Known limits

- **Hide by pattern** applies to this tab only. The Files panel and the copy dialog still show every file.
- **Remember view** is stored in each browser, not on the printer. A new browser or a cleared browser
  starts from OctoPrint's default view.
- The Files panel and the copy dialog are unchanged.

## Project structure

```
octoprint_uploadmanagertab/   the plugin package
  __init__.py                 settings defaults, tab and settings templates, update hook
  static/js/uploadmanagertab.js   moves the bundled dialog into the tab
  static/css/uploadmanagertab.css
  templates/                  the settings form (the tab template is empty by design)
docs/                         operator, install, troubleshooting and glossary guides
tests/uploadmanagertab-probe.py   live browser probe (development only)
pyproject.toml, setup.py, MANIFEST.in   packaging
```

## Development

The probe drives a running OctoPrint with a headless Chromium browser through Playwright.

```
pip install playwright
playwright install chromium
UMT_BASE=http://127.0.0.1:5097 UMT_RIG=~/octoprint-rigs/live20 python3 tests/uploadmanagertab-probe.py
```

- `UMT_BASE` is the URL of the OctoPrint instance under test.
- `UMT_RIG` is the directory that holds that instance's `apikey` file.
- `UMT_ONLY` (optional) is a comma list of check numbers to run.

The probe prints one PASS or FAIL line per check and exits non-zero on any FAIL.

To build an installable zip, run `python3 -m py_compile octoprint_uploadmanagertab/*.py setup.py`
and then zip the repository, excluding `.git`, under one top folder.

## Contributing

Open an issue or a pull request on GitHub. Keep changes to the plugin's behaviour in step with the
guides in `docs/`, and keep the bundled Upload Manager's behaviour out of this plugin.

## License

AGPLv3. See [LICENSE](LICENSE).
