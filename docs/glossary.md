# Glossary

Terms the other guides use, in the words the plugin and OctoPrint use.

**Upload Manager**
OctoPrint's bundled file window. It lists the files on a printer's storage and handles upload, print,
move and remove. This plugin shows it in a tab.

**Upload Manager Tab**
This plugin. Its name in OctoPrint's Plugin Manager and in Settings. The tab in the top bar is named
**Upload Manager**.

**Files panel**
OctoPrint's panel of files. It has a folder icon that opens the
Upload Manager Tab. It is not changed by this plugin.

**Copy dialog**
The dialog used to copy a file. It is not changed by this plugin.

**Storage**
Where a file lives: the printer's local storage or an SD card. Remember view reopens the storage you last
used in the tab.

**List style**
How the tab orders folders and files. Remember view also remembers this.

**Hide by pattern**
The setting that hides matching names in the tab. Comma-separated. `*` matches any text.

**@eaDir**
The default pattern. Its name is the one the plugin hides first, so it is not in the list by default.

**Remember view**
The setting that reopens the last folder, storage and list style. Stored in the browser, not on the printer.

**Fill horizontal / Fill vertical**
Layout settings. Horizontal stretches the list across the tab. Vertical fits the list to the window height.

**Show Uploaded column / Show Last Printed column / Show Size column**
Columns for the upload date, the last print date and the file size (or folder total).

**Files panel icon**
The setting for the folder icon in the Files panel. Choices: **Disable while this tab is open**, or **Hide**.

**users group**
OctoPrint's access group for ordinary users. Remove in the Upload Manager needs a logged-in user in this group.

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
browser. It is not used by the plugin at run time.
