$(function () {
    var PLUGIN = "uploadmanagertab";
    var TAB = "#tab_plugin_uploadmanagertab";
    var DIALOG = "#plugin_uploadmanager_dialog";
    var VIEW_KEY = "plugin.uploadmanagertab.view";
    var LIST_STYLES = ["folders_files", "files_folders", "mixed"];

    function UploadManagerTabViewModel(parameters) {
        var self = this;
        var manager = parameters[0];
        var settingsModel = parameters[1];
        var docked = false;
        var state = "restoring";

        // OctoPrint 2.0 lists every storage and has a storage selector; 1.11 has one listing and
        // no storage. One check decides which symbols are used, so a missing one never throws.
        var multiStorage = typeof manager.currentStorage === "function" &&
            typeof manager.files.storageFiles === "function" &&
            typeof manager.files.availableStorages === "function" &&
            typeof manager.files.elementByPathAndStorage === "function";

        function val(key) {
            return settingsModel.settings.plugins[PLUGIN][key]();
        }

        function setting(key) {
            return settingsModel.settings.plugins[PLUGIN][key];
        }

        function currentTab() {
            return $("#tabs li.active a").attr("href");
        }

        // The Files panel's icon only switches to the tab, so it has nothing to do while
        // the tab is showing.
        function updateIcon(current) {
            var button = $("#files_wrapper .accordion-heading .fa-folder-tree")
                .closest(".accordion-heading-button");
            var hide = val("files_icon") === "hide";
            button.toggleClass("uploadmanagertab-hidden", hide)
                .toggleClass("uploadmanagertab-inactive", !hide && current === TAB);
        }

        function applyHorizontal() {
            var tabs = $("#tabs_content");
            var on = docked && val("fill_horizontal");
            $(DIALOG).css({
                "margin-left": on ? -(parseFloat(tabs.css("padding-left")) || 0) : 0,
                "margin-right": on ? -(parseFloat(tabs.css("padding-right")) || 0) : 0
            });
        }

        function applyVertical() {
            var dialog = $(DIALOG);
            var fill = docked && val("fill_vertical");
            dialog.toggleClass("uploadmanagertab-fill-vertical", !!fill);
            if (!fill) {
                dialog.css("height", "");
                return;
            }
            // A hidden tab has a zero rect, so there is nothing to measure yet.
            if (!$(TAB).is(":visible")) return;

            var rect = dialog[0].getBoundingClientRect();
            var bottom = parseFloat($("#tabs_content").css("padding-bottom")) || 0;
            var height = window.innerHeight - (rect.top + window.scrollY) - bottom;
            dialog.css("height", Math.max(320, height) + "px");
        }

        // The Back row's cell has a fixed colspan from the bundled template, and knockout resets
        // it whenever the row is rendered. Its span must be the visible columns after the icon, so
        // it is set from the header on every render and on every column change.
        function syncBackRow() {
            var table = $(DIALOG).find("table").first();
            var visible = table.find("thead th").filter(function () {
                return $(this).css("display") !== "none";
            }).length;
            table.find("tbody td[colspan]").attr("colspan", Math.max(1, visible - 1));
        }

        function applyColumns() {
            $(DIALOG)
                .toggleClass("uploadmanagertab-no-uploaded", !val("show_uploaded"))
                .toggleClass("uploadmanagertab-no-printed", !val("show_printed"))
                .toggleClass("uploadmanagertab-no-size", !val("show_size"));
            syncBackRow();
        }

        // "*" is the only wildcard; every other character is literal, so no pattern can throw.
        function matchers(pattern) {
            return String(pattern || "").split(",").map(function (part) {
                return part.trim();
            }).filter(function (part) {
                return part !== "";
            }).map(function (part) {
                var source = part.split("*").map(function (chunk) {
                    return chunk.replace(/[-\/\\^$+?.()|[\]{}]/g, "\\$&");
                }).join(".*");
                return new RegExp("^" + source + "$", "i");
            });
        }

        function installFilter() {
            var helper = manager.listHelper;
            var update = helper.updateItems;
            helper.updateItems = function (items) {
                if (!Array.isArray(items)) return update.apply(helper, arguments);
                var rules = matchers(val("hide_pattern"));
                return update.call(helper, items.filter(function (item) {
                    var name = item && item.name;
                    return !(typeof name === "string" && rules.some(function (rule) {
                        return rule.test(name);
                    }));
                }));
            };
        }

        // Re-run the current folder with the current storage (2.0) or without one (1.11).
        function reapply() {
            if (multiStorage) {
                manager.changeFolderByPath(manager.currentPath(), manager.currentStorage());
            } else {
                manager.changeFolderByPath(manager.currentPath());
            }
        }

        function readView() {
            try {
                var view = JSON.parse(window.localStorage.getItem(VIEW_KEY));
                return view && typeof view === "object" ? view : null;
            } catch (e) {
                return null;
            }
        }

        function writeView(view) {
            try {
                window.localStorage.setItem(VIEW_KEY, JSON.stringify(view));
            } catch (e) {
                // a blocked store just means the view is not remembered
            }
        }

        function clearView() {
            try {
                window.localStorage.removeItem(VIEW_KEY);
            } catch (e) {
                // nothing to clear
            }
        }

        function persist() {
            if (state !== "settled" || !val("remember_view")) return;
            var view = {path: manager.currentPath(), listStyle: manager.listStyle()};
            if (multiStorage) view.storage = manager.currentStorage();
            writeView(view);
        }

        // The listing has arrived: 2.0 once any storage is keyed, 1.11 once allItems is set
        // (an empty array counts).
        function isLoaded() {
            if (multiStorage) return Object.keys(manager.files.storageFiles()).length > 0;
            return manager.files.allItems() !== undefined;
        }

        function listing() {
            return multiStorage ? manager.files.storageFiles : manager.files.allItems;
        }

        // Storage is decided here, at apply time, so a saved storage is not lost while storages
        // are still empty.
        function applyView(view) {
            if (!multiStorage) {
                manager.changeFolderByPath(view.path);
                return;
            }
            var storage = manager.files.availableStorages().indexOf(view.storage) >= 0 ? view.storage : "local";
            manager.currentStorage(storage);
            manager.changeFolderByPath(view.path, storage);
        }

        function restore() {
            if (!val("remember_view")) {
                clearView();
                state = "settled";
                return;
            }

            var saved = readView();
            if (saved && LIST_STYLES.indexOf(saved.listStyle) >= 0) manager.listStyle(saved.listStyle);
            if (!saved) {
                state = "settled";
                return;
            }

            var view = {
                path: typeof saved.path === "string" ? saved.path : "",
                storage: typeof saved.storage === "string" ? saved.storage : "local"
            };

            if (isLoaded()) {
                applyView(view);
                state = "settled";
                return;
            }

            // Not loaded yet: wait for the first loaded listing, then apply once and never again.
            var sub = listing().subscribe(function () {
                if (!isLoaded()) return;
                sub.dispose();
                applyView(view);
                state = "settled";
            });
        }

        self.onAllBound = function () {
            var dialog = $(DIALOG);
            var tab = $(TAB);
            if (!dialog.length || !tab.length || !manager) {
                log.warn("Upload Manager Tab: dialog or tab not found, leaving the dialog as it is");
                return;
            }

            dialog
                .removeClass("modal hide fade-in large")
                .addClass("uploadmanagertab-docked")
                .appendTo(tab);
            docked = true;

            manager.showDialog = function () {
                $('a[href="' + TAB + '"]').tab("show");
                return false;
            };

            installFilter();
            applyColumns();
            applyHorizontal();
            applyVertical();
            updateIcon(currentTab());

            // Knockout re-renders rows on navigation and on every listing refresh; re-sync the Back
            // row's span after each render. Only childList is observed, and syncBackRow changes
            // attributes only, so this cannot loop.
            new MutationObserver(syncBackRow).observe(dialog[0], {childList: true, subtree: true});

            setting("fill_horizontal").subscribe(applyHorizontal);
            setting("fill_vertical").subscribe(applyVertical);
            setting("show_uploaded").subscribe(applyColumns);
            setting("show_printed").subscribe(applyColumns);
            setting("show_size").subscribe(applyColumns);
            setting("files_icon").subscribe(function () {
                updateIcon(currentTab());
            });
            setting("hide_pattern").subscribe(reapply);
            setting("remember_view").subscribe(function (on) {
                if (on) {
                    persist();
                } else {
                    clearView();
                }
            });

            manager.currentPath.subscribe(persist);
            if (multiStorage) manager.currentStorage.subscribe(persist);
            manager.listStyle.subscribe(persist);
            $(window).on("resize.uploadmanagertab", applyVertical);

            restore();
        };

        self.onAfterTabChange = function (current) {
            updateIcon(current);
            applyVertical();
        };
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: UploadManagerTabViewModel,
        dependencies: ["uploadmanagerViewModel", "settingsViewModel"],
        elements: []
    });
});
