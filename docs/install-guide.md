# Install Guide

Use this guide to install, check, upgrade and remove the Upload Manager Tab plugin.

## Prerequisites

- OctoPrint 1.11.0 or newer. Tested on 1.11.8 and 2.0.0rc5.
- The bundled **Upload Manager** plugin enabled. It ships with OctoPrint. This plugin moves its window
  into a tab, so without it the tab stays empty.
- The OctoPrint host can reach `github.com` to download the plugin.
- An account that can manage plugins, to use the Plugin Manager.

## Install

1. Open OctoPrint and go to **Settings > Plugin Manager**.
2. Click **Get More**, then **... from URL**.
3. Paste this URL and install it:

   ```
   https://github.com/synman/OctoPrint-UploadManagerTab/archive/main.zip
   ```

4. Wait for the install to finish. If OctoPrint asks you to restart, restart it.

## Check the install

- A new **Upload Manager** tab appears at the top of OctoPrint.
- **Settings** shows an **Upload Manager Tab** section with eight settings.

If neither appears, see [troubleshooting.md](troubleshooting.md).

## Upgrade

OctoPrint's **Software Update** plugin reads the update information this plugin publishes, which points to
its GitHub releases. Use Software Update to move to a newer release.

## Uninstall

1. Go to **Settings > Plugin Manager**.
2. Find **Upload Manager Tab** in the list and click its **Uninstall Plugin** button.
3. Confirm, then restart OctoPrint if it asks.

After removal, the Upload Manager opens as the pop-up dialog again, as OctoPrint ships it.
