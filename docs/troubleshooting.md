# Troubleshooting

Each entry gives the symptom, the cause and the fix. Quote the exact text when you report a problem.

## The tab is empty, or the file list still opens as a pop-up

**Cause.** The plugin moves OctoPrint's bundled Upload Manager window into the tab. If that window is not on
the page, the plugin does nothing and logs this line to the browser console:

```
Upload Manager Tab: dialog or tab not found, leaving the dialog as it is
```

The bundled window comes from the bundled **Upload Manager** plugin. If that plugin is disabled, the
window is not there to move.

**Fix.**

1. Go to **Settings > Plugin Manager** and confirm the bundled **Upload Manager** plugin is enabled.
2. Reload the OctoPrint page. Use a hard reload (Ctrl+Shift+R, or Cmd+Shift+R on a Mac) if the old page is cached.
3. Open the browser console (F12) and look for the line above. If it is still there after steps 1 and 2,
   report it with your OctoPrint version.

## Remove is greyed out

**Cause.** Remove is part of OctoPrint's bundled Upload Manager. It stays disabled unless the logged-in
user is a user in OctoPrint's **users** group. This is OctoPrint behaviour, not this plugin's. The check is
`enableRemove` in `src/octoprint/plugins/uploadmanager/static/js/uploadmanager.js` in the OctoPrint source.

**Fix.** An admin adds the account to the **users** group in OctoPrint's access control. Then log in again.
Remove also needs at least one file selected.

## `@eaDir` still shows in the list

**Cause.** The **Hide by pattern** setting has been changed or cleared, or the name you see is not a match.
The default is `@eaDir`.

**Fix.**

1. Go to **Settings > Upload Manager Tab** and check **Hide by pattern**. It should read `@eaDir`, or include
   the name you want hidden.
2. Use commas to separate names, for example `@eaDir, *.tmp`. `*` matches any text.
3. Remember that the setting applies to the Upload Manager Tab only. The Files panel still shows the name.

## A setting does not seem to apply

**Cause.** A change shows at once, but only **Save** keeps it. **Close** without saving undoes it. **Remember view**
is stored in each browser.

**Fix.**

1. Click **Save** in the Settings dialog after changing a value.
2. If it still looks wrong, reload the OctoPrint page.
3. For the folder and list style, check **Remember view** is on. A different browser starts fresh.
4. For the Files panel folder icon, check the **Files panel icon** setting. **Disable while this tab is open**
   greys the icon while the tab is showing. **Hide** removes it.

## The plugin does not install from the URL

**Cause.** The OctoPrint host cannot reach `github.com`, or the URL is mistyped.

**Fix.** Check that the URL is exactly
`https://github.com/synman/OctoPrint-UploadManagerTab/archive/main.zip` and that the host has internet
access. Then try the install again from **Settings > Plugin Manager > Get More > ... from URL**.
