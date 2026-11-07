# Operators Guide

This guide is for running the Upload Manager Tab day to day: what you see, what each setting does, and
what to check when something looks wrong.

Examples use 3D printers and print files.

## What you get

OctoPrint's Upload Manager is the file window you open from the Files panel. By default it pops up over
the page. With this plugin it lives in its own **Upload Manager** tab next to your other OctoPrint tabs.

Use it to:

- Look through a folder of old prints, such as `Benchies/`, without a pop-up covering the page.
- Load or print a `.gcode` file, or download a copy.
- Check when a file was uploaded or last printed.
- Move or remove an old test print.

The Files panel and the copy dialog work as before.

## Open the tab

1. Click the **Upload Manager** tab at the top of OctoPrint.
2. Or click the folder icon in the Files panel. That icon switches to this tab. Its behaviour depends on
   the **Files panel icon** setting (see below).

Printing and file actions are OctoPrint's own. The plugin changes only where the window is
shown.

## The eight settings

Find them under **Settings > Upload Manager Tab**. Defaults are the values the plugin ships with.
(proof: `get_settings_defaults` in `octoprint_uploadmanagertab/__init__.py`; labels from
`octoprint_uploadmanagertab/templates/uploadmanagertab_settings.jinja2`)

| Setting | Label in Settings | Default | What it does |
|---|---|---|---|
| `fill_horizontal` | Fill horizontal | on | Stretches the file list to the inner edges of the tab. |
| `fill_vertical` | Fill vertical | on | Fits the list to the window height and scrolls inside it. Off: the page scrolls instead. |
| `hide_pattern` | Hide by pattern | `@eaDir` | Hides names that match. Comma-separated; `*` matches any text. |
| `remember_view` | Remember view | on | Reopens the last folder and list style when you come back, plus the storage on OctoPrint 2.0. |
| `show_uploaded` | Show Uploaded column | on | Shows the date each file was uploaded. |
| `show_printed` | Show Last Printed column | on | Shows the date each file was last printed. |
| `show_size` | Show Size column | on | Shows the file size, or the total for a folder. |
| `files_icon` | Files panel icon | Disable while this tab is open | The folder icon in the Files panel. The other choice is **Hide**. |

### Examples with printers and files

- **Hide by pattern** `@eaDir`: the default. It hides any `@eaDir` entry in the list. Add more names with
  commas, for example `@eaDir, *.tmp`. A `*` matches any text, so `*.tmp` hides every name ending in `.tmp`.
- **Hide by pattern** applies to this tab only. A file you hide here still shows in the Files panel.
- **Show Last Printed column** on: useful when you keep many test prints and want the one you ran last week.
- **Show Size column** off: a shorter list if you only care about names.
- **Fill vertical** off: the whole OctoPrint page scrolls instead of only the list. Useful on a small
  screen beside the printer.
- **Remember view** on: if you last looked at `Benchies/`, the tab reopens there. The memory is stored in
  the browser you used, so a second computer starts fresh.

## Known limits

- Hide by pattern does not change the Files panel or the copy dialog.
- Remember view is per browser.
- The Files panel and the copy dialog are unchanged.

## Check it works

1. Open the **Upload Manager** tab. The file list should load inside the tab, not in a pop-up.
2. Turn **Show Size column** off in Settings, save, and confirm the Size column disappears. Turn it back on.
3. If a check fails, go to [troubleshooting.md](troubleshooting.md).
