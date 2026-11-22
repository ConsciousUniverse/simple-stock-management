/**
 * The two ways of creating an account.
 *
 * Kept as a page script rather than inline: the buttons carry the panel they
 * open, so a third kind of account is one button and one form, with no change
 * here.
 */
(function () {
    "use strict";

    const tabs = document.querySelectorAll("#newUserTabs .sap-tab");
    const panels = {
        panelApp: document.getElementById("createAppUserForm"),
        panelWeb: document.getElementById("createWebUserForm"),
    };

    tabs.forEach(function (tab) {
        tab.addEventListener("click", function () {
            tabs.forEach(function (other) {
                other.classList.toggle("is-active", other === tab);
            });
            Object.keys(panels).forEach(function (name) {
                const panel = panels[name];
                if (panel) {
                    panel.classList.toggle("is-hidden", name !== tab.dataset.panel);
                }
            });
        });
    });
})();
