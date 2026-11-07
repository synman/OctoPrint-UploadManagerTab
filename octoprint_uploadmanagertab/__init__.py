import octoprint.plugin


class UploadManagerTabPlugin(
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
):
    # The tab holds no markup of its own: the view model moves OctoPrint's bundled Upload
    # Manager dialog into it, so all behaviour stays in the bundled plugin.

    def get_assets(self):
        return {"js": ["js/uploadmanagertab.js"], "css": ["css/uploadmanagertab.css"]}

    def get_settings_defaults(self):
        return {
            "fill_horizontal": True,
            "fill_vertical": True,
            "hide_pattern": "@eaDir",
            "remember_view": True,
            "show_uploaded": True,
            "show_printed": True,
            "show_size": True,
            "files_icon": "gray",
        }

    def get_template_configs(self):
        return [
            {"type": "tab", "name": "Upload Manager", "custom_bindings": True},
            {"type": "settings", "custom_bindings": False, "name": "Upload Manager Tab"},
        ]

    def is_template_autoescaped(self):
        return True

    def get_update_information(self):
        return {
            "uploadmanagertab": {
                "displayName": "Upload Manager Tab Plugin",
                "displayVersion": self._plugin_version,
                "type": "github_release",
                "user": "synman",
                "repo": "OctoPrint-UploadManagerTab",
                "current": self._plugin_version,
                "pip": "https://github.com/synman/OctoPrint-UploadManagerTab/archive/{target_version}.zip",
            }
        }


__plugin_name__ = "Upload Manager Tab"
__plugin_description__ = "Shows OctoPrint's Upload Manager in a tab instead of a dialog"
__plugin_license__ = "AGPLv3"
__plugin_pythoncompat__ = ">=3.7,<4"
__plugin_implementation__ = UploadManagerTabPlugin()


def __plugin_load__():
    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
