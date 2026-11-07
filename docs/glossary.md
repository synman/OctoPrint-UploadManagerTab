# Glossary

Terms the other guides use, in the words the plugin and OctoPrint use.

**Upload Manager**
OctoPrint's bundled file window. It lists the files on a printer's storage and handles print, load, copy,
move and remove. This plugin shows it in a tab.

**Upload Manager Tab**
This plugin. Its name in OctoPrint's Plugin Manager and in Settings. The tab in the top bar is named
**Upload Manager**.

**Files panel**
OctoPrint's panel of files in the sidebar. This plugin changes only its folder icon, which switches to the tab.

**Copy dialog**
The dialog used to copy a file. It is not changed by this plugin.

**Storage**
Where a file lives: OctoPrint's own local storage or the printer's SD card. OctoPrint 2.0 lets you choose it in the
tab, and Remember view reopens your choice there. OctoPrint 1.11 has no such choice in the tab.

**List style**
How the tab orders folders and files. Remember view also remembers this.

**Hide by pattern**
The setting that hides matching names in the tab. Comma-separated. `*` matches any text.

**@eaDir**
A system folder that Synology NAS drives create. It appears in the list when your uploads live on a NAS share. The
default pattern hides it.

**Remember view**
The setting that reopens the last folder and list style, plus the storage on OctoPrint 2.0. Stored in the browser,
not on the printer.

**Fill horizontal / Fill vertical**
Layout settings. Horizontal stretches the list across the tab. Vertical fits the list to the window height.

**Show Uploaded column / Show Last Printed column / Show Size column**
Columns for the upload date, the last print date and the file size (or folder total).

**Files panel icon**
The setting for the folder icon in the Files panel. Choices: **Disable while this tab is open**, or **Hide**.

**users group**
OctoPrint's access group for ordinary users. Remove in the Upload Manager needs a logged-in user in this group.

**Access control, admin**
OctoPrint's user accounts and permissions. An admin is an account that can change them.

**Hard reload**
Reloading a web page while ignoring the browser's saved copy.

**Browser console**
The browser's developer panel that shows page errors. Open it with F12.

**Release**
A numbered version of this plugin published on GitHub. Software Update looks here.

**Plugin Manager**
The OctoPrint page under Settings where plugins are installed, uninstalled and listed.

**Get More > ... from URL**
The Plugin Manager option that installs a plugin from a web address, such as this plugin's GitHub zip.

**Software Update**
The OctoPrint plugin that checks for new releases of installed plugins.

**AGPLv3**
The license of this plugin. See `LICENSE` in the repository.

**Probe**
`tests/uploadmanagertab-probe.py`, a development script that drives a running OctoPrint with a headless
browser, a browser with no window, through Playwright, a browser automation tool. It is not used by the plugin at
run time.
