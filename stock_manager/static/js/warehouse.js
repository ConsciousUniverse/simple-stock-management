/*
 * The warehouse table engine.
 *
 * One script serves the two pages that need it: the items page (the editable
 * warehouse table, the add form and the Excel exchange) and the dashboard (the
 * site-request queue). It renders only the tables that are actually on the page,
 * so a page never carries markup it does not use.
 *
 * Everything the reader sees is escaped before it is interpolated: item codes
 * and descriptions are data, not markup.
 */
(() => {
    'use strict';

    /* ==============================================================
       State
       ============================================================== */

    // Global variable to hold the edit lock status.
    window.editLock = false;

    // Translations for the runtime messages, keyed by the English text.
    const source = document.getElementById('i18n-js');
    const I18N = source ? JSON.parse(source.textContent) : {};
    const tr = (text) => I18N[text] || text;

    // Global variable for records per page (default fallback).
    window.recordsPerPage = 25;

    // Globals to hold page, sort column & sort order.
    window.currentPageGlobals = [{
        page: 1,
        sort: 'last_updated',
        order: '',
        search: ''
    }, {
        page: 1,
        sort: 'last_updated',
        order: '',
        search: ''
    }, {
        page: 1,
        sort: 'last_updated',
        order: '',
        search: ''
    }];

    // Global cache for transfer quantities.
    window.cache = {
        'xfer_qnt': new Map()
    };

    // Global object to hold active AJAX requests for each table.
    window.currentFetchRequests = {
        1: null,
        2: null,
        3: null
    };

    // Per-table DOM handles, labels and KPI tile targets. Table 2 (site stock)
    // is rendered by the server on the items page, so it has no entry here.
    const TABLE_META = {
        1: {
            tbody: '#itemTable1',
            empty: '#empty1',
            count: '#count1',
            pagination: '#paginationControls1',
            kpi: 'kpiWarehouse',
            url: '/api/items/',
            label: 'warehouse item',
            labelPlural: 'warehouse items'
        },
        3: {
            tbody: '#itemTable3',
            empty: '#empty3',
            count: '#count3',
            pagination: '#paginationControls3',
            kpi: 'kpiTransfers',
            url: '/api/transfer_items/',
            label: 'pending transfer',
            labelPlural: 'pending transfers'
        }
    };

    // The tables this page actually renders.
    const tablesOnPage = () => Object.keys(TABLE_META)
        .map(Number)
        .filter((number) => document.querySelector(TABLE_META[number].tbody));

    /* ==============================================================
       Helpers
       ============================================================== */

    // Escape server-supplied values before interpolating them into HTML.
    // Covers element-content and quoted-attribute contexts so stored data
    // (e.g. item SKU / description) cannot inject markup or break out of an
    // attribute (XSS).
    const escapeHtml = (value) => {
        if (value === null || value === undefined) return '';
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    };

    // Get CSRF token from cookies.
    const getCSRFToken = () => {
        return document.cookie.split('; ')
            .find(row => row.startsWith('csrftoken='))?.split('=')[1];
    };

    // Ensure CSRF token is included in all AJAX requests.
    $.ajaxSetup({
        beforeSend: function (xhr, settings) {
            xhr.setRequestHeader("X-CSRFToken", getCSRFToken());
        }
    });

    // Extract a human-readable message from a failed AJAX response.
    const errorDetail = (xhr, fallback) => {
        let body = xhr && xhr.responseJSON;
        if (!body && xhr && xhr.responseText) {
            try {
                body = JSON.parse(xhr.responseText);
            } catch (e) {
                body = null;
            }
        }
        if (typeof body === 'string' && body.trim()) return body;
        if (body && typeof body === 'object') {
            if (typeof body.detail === 'string') return body.detail;
            if (typeof body.error === 'string') return body.error;
            const first = Object.keys(body).map(k => body[k])[0];
            if (Array.isArray(first) && first.length) return String(first[0]);
            if (typeof first === 'string') return first;
        }
        return fallback || tr('An error occurred.');
    };

    /* ==============================================================
       SAP-style message toast and confirmation dialog
       ============================================================== */

    const TOAST_ICONS = {
        info: '#i-info',
        success: '#i-check',
        error: '#i-x-circle',
        warning: '#i-alert'
    };

    const notify = (message, variant) => {
        const tone = variant || 'info';
        const stack = document.getElementById('toastStack');
        if (!stack) {
            window.alert(message);
            return null;
        }
        const toast = document.createElement('div');
        toast.className = 'sap-toast sap-toast--' + tone;
        toast.setAttribute('role', tone === 'error' ? 'alert' : 'status');

        const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        icon.setAttribute('class', 'sap-icon sap-toast__icon');
        icon.setAttribute('aria-hidden', 'true');
        const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
        use.setAttribute('href', TOAST_ICONS[tone] || TOAST_ICONS.info);
        icon.appendChild(use);

        const body = document.createElement('div');
        body.className = 'sap-toast__body';
        body.textContent = message === null || message === undefined ? '' : String(message);

        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'sap-toast__close';
        close.setAttribute('aria-label', tr('Dismiss notification'));
        close.textContent = '\u2715';

        const dismiss = () => {
            window.clearTimeout(timer);
            toast.classList.add('is-leaving');
            window.setTimeout(() => toast.remove(), 200);
        };
        close.addEventListener('click', dismiss);
        const timer = window.setTimeout(dismiss, tone === 'error' ? 9000 : 5000);

        toast.appendChild(icon);
        toast.appendChild(body);
        toast.appendChild(close);
        stack.appendChild(toast);
        return toast;
    };

    // Promise-based replacement for window.confirm().
    const confirmDialog = (options) => new Promise((resolve) => {
        const opts = options || {};
        const previouslyFocused = document.activeElement;
        const backdrop = document.createElement('div');
        backdrop.className = 'sap-dialog-backdrop';
        backdrop.innerHTML = `
<div class="sap-dialog" role="dialog" aria-modal="true" aria-labelledby="sapDialogTitle">
    <div class="sap-dialog__header">
        <span class="sap-dialog__icon">
            <svg class="sap-icon" aria-hidden="true"><use href="#i-alert"></use></svg>
        </span>
        <h2 class="sap-dialog__title" id="sapDialogTitle"></h2>
    </div>
    <div class="sap-dialog__body"></div>
    <div class="sap-dialog__footer">
        <button type="button" class="sap-btn sap-btn--transparent" data-dialog-cancel></button>
        <button type="button" class="sap-btn sap-btn--emphasized" data-dialog-confirm></button>
    </div>
</div>`;

        backdrop.querySelector('.sap-dialog__title').textContent =
            opts.title || tr('Please confirm');
        backdrop.querySelector('.sap-dialog__body').textContent = opts.message || '';

        const cancelBtn = backdrop.querySelector('[data-dialog-cancel]');
        const confirmBtn = backdrop.querySelector('[data-dialog-confirm]');
        cancelBtn.textContent = opts.cancelLabel || 'Cancel';
        confirmBtn.textContent = opts.confirmLabel || 'Continue';
        if (opts.destructive) {
            confirmBtn.className = 'sap-btn sap-btn--negative-emphasized';
        }

        const close = (result) => {
            document.removeEventListener('keydown', onKey);
            backdrop.remove();
            if (previouslyFocused && previouslyFocused.focus) {
                previouslyFocused.focus();
            }
            resolve(result);
        };
        const onKey = (event) => {
            if (event.key === 'Escape') {
                event.preventDefault();
                close(false);
            } else if (event.key === 'Enter') {
                event.preventDefault();
                close(true);
            }
        };
        cancelBtn.addEventListener('click', () => close(false));
        confirmBtn.addEventListener('click', () => close(true));
        backdrop.addEventListener('click', (event) => {
            if (event.target === backdrop) close(false);
        });
        document.addEventListener('keydown', onKey);
        document.body.appendChild(backdrop);
        confirmBtn.focus();
    });

    /* ==============================================================
       Configuration & lock status
       ============================================================== */

    // Fetch app config (records_per_page) from backend.
    const fetchAppConfig = () => {
        return $.get('/api/app_config/', data => {
            if (data.records_per_page) {
                window.recordsPerPage = data.records_per_page;
            }
            // Store allow_upload_deletions in a global variable.
            window.allowUploadDeletions = !!data.allow_upload_deletions;
        });
    };

    // Set edit lock status on the server.
    const setEditLockStatus = (status) => {
        if (window.userGroups && window.userGroups.includes("managers")) {
            $.ajax({
                url: '/api/set_edit_lock_status/',
                type: 'POST',
                contentType: 'application/json',
                headers: { 'X-CSRFToken': getCSRFToken() },
                data: JSON.stringify({ edit_lock_status: status }),
                success: response => {
                    window.editLock = response.edit_lock;
                    updateUIBasedOnEditLock();
                    tablesOnPage().forEach((tn) => fetchItems(tn));
                }
            });
        }
    };

    // Get the edit lock status from the server.
    const getEditLockStatus = () => {
        return new Promise((resolve, reject) => {
            $.ajax({
                url: '/api/get_edit_lock_status/',
                type: 'GET',
                success: response => {
                    window.editLock = response.edit_lock;
                    updateUIBasedOnEditLock();
                    resolve();
                },
                error: xhr => {
                    console.error("Failed to fetch edit lock status:", xhr.responseText);
                    reject(xhr);
                }
            });
        });
    };

    // Reflect the lock state in the banner and the maintenance switch.
    const updateUIBasedOnEditLock = () => {
        const isLocked = window.editLock;
        $('#itemTable1 input, #itemTable1 button').prop('disabled', isLocked);
        $('#updateModeToggle').prop('checked', isLocked);
        $('.maintenanceMode').toggleClass('d-none', !isLocked);
    };

    /* ==============================================================
       Paging / sorting / search
       ============================================================== */

    // Update global page variables and trigger a new fetch.
    const updatePageGlobals = (tableNum, page = null, sort = null, order = null, search = null) => {
        if (page !== null) {
            window.currentPageGlobals[tableNum - 1]['page'] = page;
        }
        if (sort !== null) {
            window.currentPageGlobals[tableNum - 1]['sort'] = sort;
        }
        if (order !== null) {
            window.currentPageGlobals[tableNum - 1]['order'] = order;
        }
        if (search !== null) {
            window.currentPageGlobals[tableNum - 1]['search'] = search;
        }
        fetchItems(tableNum);
    };

    // Search function for tables.
    const search = (tableNum, query) => {
        updatePageGlobals(tableNum, 1, null, null, query);
    };

    // Sorting functionality.
    const sortTable = (tableNum, column) => {
        const $table = $(`#itemTable${tableNum}`);
        const currentOrder = $table.data('sortOrder') || 'asc';
        const newOrder = currentOrder === 'asc' ? 'desc' : 'asc';
        $table.data('sortOrder', newOrder).data('sortColumn', column);
        const searchVal = $(`#searchBox${tableNum}`).val();
        updatePageGlobals(tableNum, 1, column, newOrder, searchVal);
    };

    // Update the update mode toggle button state.
    const setUpdateModeButtonState = () => {
        $('#updateModeToggle').prop('checked', window.editLock);
    };

    // Paint the sort direction on the column headers.
    const renderSortIndicators = (tableNum) => {
        const state = window.currentPageGlobals[tableNum - 1];
        const $table = $(`#itemTable${tableNum}`).closest('table');
        $table.find('thead th[data-sort-col]').each(function () {
            const $th = $(this);
            const column = $th.attr('data-sort-col');
            const $indicator = $th.find('.sap-sort');
            if (state.sort === column && state.order) {
                $th.attr('aria-sort', state.order === 'asc' ? 'ascending' : 'descending');
                if ($indicator.length) {
                    $indicator.text(state.order === 'asc' ? '\u25B2' : '\u25BC');
                }
            } else {
                $th.attr('aria-sort', 'none');
                if ($indicator.length) $indicator.text('\u2195');
            }
        });
    };

    // Show the time of the last successful refresh.
    const markUpdated = () => {
        const el = document.getElementById('lastUpdated');
        if (el) {
            el.textContent = ' \u00b7 ' + tr('Updated') + ' ' + new Date().toLocaleTimeString();
        }
    };

    /* ==============================================================
       Transfer quantity cache
       ============================================================== */

    // Set nested cache map values for transfer quantities.
    const setXferVals = (shop_user, sku, qty) => {
        const map = window.cache.xfer_qnt;
        if (!map.has(shop_user)) {
            map.set(shop_user, new Map());
        }
        map.get(shop_user).set(sku, qty);
    };

    // Get nested cache map values for transfer quantities.
    const getXferVals = (shop_user, sku) => {
        return window.cache.xfer_qnt.get(shop_user)?.get(sku);
    };

    // Delete transfer quantity values from cache.
    const deleteXferVals = (shop_user, sku) => {
        const map = window.cache.xfer_qnt;
        if (!map.has(shop_user)) return;
        const userMap = map.get(shop_user);
        userMap.delete(sku);
        if (userMap.size === 0) {
            map.delete(shop_user);
        }
    };

    /* ==============================================================
       Table rendering
       ============================================================== */

    // Fetch items via AJAX and populate the corresponding table.
    const fetchItems = async (tableNum) => {
        const meta = TABLE_META[tableNum];
        if (!meta || !document.querySelector(meta.tbody)) return;
        try {
            await getEditLockStatus();

            const state = window.currentPageGlobals[tableNum - 1];
            const isManager = !!(window.userGroups && window.userGroups.includes("managers"));
            const isShopUser = !!(window.userGroups && window.userGroups.includes("shop_users"));
            // The stock table merges the rows that share an internal code.
            // Sorting by another column would separate them, so the merge is
            // only asked for while the table is in its grouped order. The
            // default `last_updated` is not a header the operator can sort by,
            // so it counts as "no chosen order" and keeps the groups together.
            const groupedMode = tableNum === 1 && (!state.sort || state.sort === 'last_updated');

            let apiUrl = meta.url;
            if (tableNum === 3 && isShopUser) {
                apiUrl += `?shop_user_username=${encodeURIComponent(window.loggedInUsername || '')}`;
            }
            const separator = apiUrl.includes('?') ? '&' : '?';
            apiUrl += `${separator}page=${state.page}&page_size=${window.recordsPerPage}&search=${encodeURIComponent(state.search)}`;
            if (state.sort && !groupedMode) {
                apiUrl += `&ordering=${state.order === 'asc' ? '' : '-'}${state.sort}`;
            }
            if (groupedMode) {
                apiUrl += '&grouped=1';
            }

            // Cancel any existing request for this table.
            if (window.currentFetchRequests[tableNum]) {
                window.currentFetchRequests[tableNum].abort();
            }

            // Make the AJAX call and store its jqXHR.
            const xhr = $.get(apiUrl, data => {
                const $tableBody = $(meta.tbody);
                $tableBody.empty();

                // Rowspan of the merged internal-code cell: the first row of a
                // group carries the span, the rows below it carry no code cell.
                const groupSpans = {};
                if (groupedMode) {
                    let current = null;
                    let start = 0;
                    data.results.forEach((row, index) => {
                        const key = row.internal_code || `sku:${row.sku}`;
                        if (key !== current) {
                            current = key;
                            start = index;
                            groupSpans[index] = { span: 1, total: row.group_total };
                        } else {
                            groupSpans[start].span += 1;
                        }
                    });
                }

                data.results.forEach((item, index) => {
                    let row = '';
                    if (tableNum === 1) {
                        const safeSku = escapeHtml(item.sku);
                        const safeInternal = escapeHtml(item.internal_code || '—');
                        const internalCell = groupedMode
                            ? (groupSpans[index]
                                ? `<td class="sap-table__group" rowspan="${groupSpans[index].span}" dir="ltr">${safeInternal}</td>`
                                : '')
                            : `<td class="sap-table__group" dir="ltr">${safeInternal}</td>`;
                        const totalCell = groupedMode
                            ? (groupSpans[index]
                                ? `<td class="sap-table__group sap-table__num" rowspan="${groupSpans[index].span}">${groupSpans[index].total}</td>`
                                : '')
                            : `<td class="sap-table__group sap-table__num">${item.group_total}</td>`;
                        const quantityField = isManager ?
                            `<input type="number" min="0" value="${item.quantity}" class="sap-input wh_editable-field" data-sku="${safeSku}" data-field="quantity">` :
                            item.quantity;
                        const retailPriceField = isManager ?
                            `<input type="number" min="0" step="0.01" value="${item.retail_price}" class="sap-input wh_editable-field" data-sku="${safeSku}" data-field="retail_price">` :
                            parseFloat(item.retail_price).toFixed(2);
                        const descriptionField = isManager ?
                            `<input type="text" value="${escapeHtml(item.description)}" class="sap-input wh_editable-field" data-sku="${safeSku}" data-field="description">` :
                            escapeHtml(item.description);
                        const unitSuffix = item.unit ? `<span class="sap-muted"> · ${escapeHtml(item.unit)}</span>` : '';
                        const transferQuantityField = `<input type="number" min="0" class="sap-input xferQntField wh_editable-field" ${window.editLock ? 'disabled' : ''} value="" placeholder="${tr('How many?')}" data-sku="${safeSku}" data-field="xfer_qnt">`;
                        row = `
<tr class="${groupedMode && groupSpans[index] ? 'sap-table__groupstart' : ''}">
    ${internalCell}
    <td class="sap-table__sku">${safeSku}</td>
    <td>${descriptionField}${unitSuffix}</td>
    <td class="sap-table__num">${retailPriceField}</td>
    <td class="sap-table__num">${quantityField}</td>
    ${totalCell}
    ${isShopUser ? `<td class="sap-table__num">${transferQuantityField}</td>` : ''}
    ${isManager ? `<td class="actions"></td>` : ''}
</tr>`;
                    } else if (tableNum === 3) {
                        const highlightClass = item.ordered && isShopUser ? 'highlight-ordered' : '';
                        const shop_user = item.shop_user && item.shop_user.username ? item.shop_user.username : window.loggedInUsername;
                        setXferVals(shop_user, item.item.sku, item.quantity);
                        const safeSku = escapeHtml(item.item.sku);
                        const safeShopUser = escapeHtml(shop_user);
                        row = `
<tr class="${highlightClass}" data-ordered="${item.ordered}" data-sku="${safeSku}" data-quantity="${item.quantity}">
    ${isManager ? `<td>${safeShopUser}</td>` : ''}
    <td class="sap-table__sku">${safeSku}</td>
    <td>${escapeHtml(item.item.description)}</td>
    <td class="sap-table__num">${isManager ? `<input class="sap-input" type="number" min="0" value="${getXferVals(shop_user, item.item.sku)}" id="quantity3-${safeSku}" data-shop_user_id="${safeShopUser}">` : getXferVals(shop_user, item.item.sku)}</td>
    <td class="actions">
    ${isManager ? `<button class="sap-btn sap-btn--sm sap-btn--emphasized dispatch-btn" type="button" data-sku="${safeSku}" data-shop-user="${safeShopUser}" id="dispatchButton-${safeSku}">Dispatch</button>` : ''}
    <button class="sap-btn sap-btn--sm sap-btn--negative cancel-btn" type="button" data-sku="${safeSku}" data-shop-user="${safeShopUser}" ${window.userGroups && !isManager && item.ordered ? 'disabled' : ''} id="deleteButton-${safeSku}">Cancel</button>
    </td>
</tr>`;
                    }
                    $tableBody.append(row);
                    if (tableNum === 1 && isManager) {
                        $tableBody.find('tr:last .actions').append(`
<button class="sap-btn sap-btn--sm sap-btn--negative delete-item-btn" type="button" data-sku="${escapeHtml(item.sku)}">${tr('Delete')}</button>
`);
                    }
                });

                // Empty-state panel + record counter + KPI tile.
                $(meta.empty).toggleClass('d-none', data.results.length > 0);
                const total = typeof data.count === 'number' ? data.count : data.results.length;
                $(meta.count).text(
                    total === 1 ? `1 ${tr(meta.label)}` : `${total} ${tr(meta.labelPlural)}`
                );
                const kpi = document.getElementById(meta.kpi);
                if (kpi && typeof data.count === 'number') {
                    kpi.textContent = Number(data.count).toLocaleString('en-US');
                }

                renderSortIndicators(tableNum);
                setupPagination(tableNum, data);
                markUpdated();
            });

            // Store the active request.
            window.currentFetchRequests[tableNum] = xhr;

        } catch (error) {
            console.error("Error in fetchItems:", error);
        }
    };

    // Build and attach pagination controls.
    const setupPagination = (tn, data) => {
        const meta = TABLE_META[tn];
        const $paginationDiv = $(meta.pagination);
        $paginationDiv.empty();

        const currentPage = data.current_page || 1;
        const totalPages = data.total_pages || 1;
        const total = typeof data.count === 'number' ? data.count : data.results.length;
        const perPage = Math.min(window.recordsPerPage || 25, 100);
        // Grouped pages hold whole internal codes, so the first/last row are
        // reported by the server rather than assumed from the page number.
        const firstRow = typeof data.first_row === 'number'
            ? data.first_row
            : (total === 0 ? 0 : (currentPage - 1) * perPage + 1);
        const lastRow = typeof data.last_row === 'number'
            ? data.last_row
            : (total === 0 ? 0 : firstRow + data.results.length - 1);

        const $info = $('<span class="sap-pagination__info"></span>').text(
            total === 0 ? tr('No records') :
                `${tr('Showing')} \u2066${firstRow}\u2013${lastRow}\u2069 ${tr('of')} ${total}`
        );

        const $controls = $('<div class="sap-pagination__controls"></div>');

        const addButton = (label, page, options) => {
            const opts = options || {};
            const $btn = $('<button type="button" class="sap-pagination__btn"></button>');
            if (opts.html) {
                $btn.html(label);
            } else {
                $btn.text(label);
            }
            if (opts.active) {
                $btn.addClass('is-active').attr('aria-current', 'page');
            }
            if (opts.disabled) {
                $btn.addClass('is-disabled').attr('disabled', 'disabled');
            }
            if (page !== null && !opts.disabled) {
                $btn.on('click', () => updatePageGlobals(tn, page, null, null, null));
            }
            $controls.append($btn);
        };

        const startPage = Math.floor((currentPage - 1) / 5) * 5 + 1;
        const endPage = Math.min(startPage + 4, totalPages);

        addButton('<svg class="sap-icon sap-icon--sm" aria-hidden="true"><use href="#i-chevron-left"></use></svg>', Math.max(1, startPage - 5), {
            html: true,
            disabled: currentPage <= 5
        });

        for (let i = startPage; i <= endPage; i++) {
            addButton(String(i), i, { active: i === currentPage });
        }

        addButton('<svg class="sap-icon sap-icon--sm" aria-hidden="true"><use href="#i-chevron-right"></use></svg>', startPage + 5, {
            html: true,
            disabled: endPage >= totalPages
        });

        if (total === 0) {
            $paginationDiv.append($info);
            return;
        }
        $paginationDiv.append($info).append($controls);
    };

    /* ==============================================================
       Mutations
       ============================================================== */

    // Add a new item using AJAX POST.
    const addItem = () => {
        const retailPrice = $('#retail_price').val();
        if (!/^\d+(\.\d{1,2})?$/.test(retailPrice)) {
            notify(tr('Retail price must be a valid number with up to 2 decimal places.'), 'warning');
            return;
        }
        const data = {
            sku: $('#sku').val(),
            description: $('#description').val(),
            retail_price: retailPrice,
            quantity: $('#quantity').val(),
            unit: $('#unit').val()
        };
        $.ajax({
            url: '/api/items/',
            type: 'POST',
            contentType: 'application/json',
            headers: { 'X-CSRFToken': getCSRFToken() },
            data: JSON.stringify(data),
            success: () => {
                fetchItems(1);
                $('#sku, #description, #retail_price, #quantity, #unit').val('');
                notify(tr('Item created successfully.'), 'success');
            },
            error: xhr => {
                notify(errorDetail(xhr, tr('Could not create the item.')), 'error');
            }
        });
    };

    // Update an item using AJAX PUT.
    const updateItem = (tableNum, sku, fieldName, value) => {
        if (tableNum == 1) {
            if (fieldName == 'retail_price' && !/^\d+(\.\d{1,2})?$/.test(value)) {
                notify(tr('Retail price must be a valid number with up to 2 decimal places.'), 'warning');
                return;
            }
            const data = {
                sku: sku,
                [fieldName]: value
            };
            $.ajax({
                url: `/api/items/${encodeURIComponent(sku)}/`,
                type: 'PUT',
                contentType: 'application/json',
                headers: { 'X-CSRFToken': getCSRFToken() },
                data: JSON.stringify(data),
                success: () => fetchItems(1),
                error: xhr => {
                    notify(errorDetail(xhr, tr('Could not update the item.')), 'error');
                }
            });
        }
    };

    // Delete an item using AJAX DELETE.
    const deleteItem = async (sku, tableNum) => {
        const confirmed = await confirmDialog({
            title: tr('Delete item?'),
            message: `Remove "${sku}" from the active warehouse catalogue?\n\nExisting transfer records are unaffected.`,
            confirmLabel: tr('Delete'),
            cancelLabel: 'Cancel',
            destructive: true
        });
        if (!confirmed) return;

        const apiUrl = tableNum === 1 ?
            `/api/items/${encodeURIComponent(sku)}/` :
            `/api/shop_items/${encodeURIComponent(sku)}/`;
        $.ajax({
            url: apiUrl,
            type: 'DELETE',
            headers: { 'X-CSRFToken': getCSRFToken() },
            success: () => {
                fetchItems(tableNum);
                notify(tr('Item deleted.'), 'success');
            },
            error: xhr => {
                notify(errorDetail(xhr, tr('Could not delete the item.')), 'error');
            }
        });
    };

    // Transfer an item using AJAX POST.
    const transferItem = (sku, xfer_qnt) => {
        $.ajax({
            url: '/api/transfer/',
            type: 'POST',
            contentType: 'application/json',
            headers: { 'X-CSRFToken': getCSRFToken() },
            data: JSON.stringify({ sku, transfer_quantity: xfer_qnt }),
            success: () => {
                fetchItems(3);
            },
            error: xhr => {
                notify(errorDetail(xhr, tr('Could not add the transfer.')), 'error');
                fetchItems(1);
            }
        });
    };

    // Submit transfer request.
    const submitTransferRequest = () => {
        $.ajax({
            url: '/api/submit-transfer-request/',
            type: 'POST',
            contentType: 'application/json',
            headers: { 'X-CSRFToken': getCSRFToken() },
            data: JSON.stringify({}),
            success: () => {
                fetchItems(3);
                notify(tr('Transfer request sent to the warehouse.'), 'success');
            },
            error: xhr => notify(errorDetail(xhr, tr('Could not send the transfer request.')), 'error')
        });
    };

    // Complete or cancel a transfer using AJAX POST.
    const completeTransfer = (sku, shop_user_id, cancel) => {
        const quantity = getXferVals(shop_user_id, sku);
        $.ajax({
            url: '/api/complete-transfer/',
            type: "POST",
            contentType: 'application/json',
            headers: { 'X-CSRFToken': getCSRFToken() },
            data: JSON.stringify({ sku, shop_user_id, quantity, cancel }),
            success: () => {
                [1, 3].forEach(tn => fetchItems(tn));
                notify(cancel ? tr('Transfer cancelled.') : tr('Transfer dispatched.'), 'success');
            },
            error: xhr => notify(errorDetail(xhr, tr('Could not complete the transfer.')), 'error')
        });
        deleteXferVals(shop_user_id, sku);
    };

    // Download stock data.
    const downloadStockData = () => {
        const url = '/api/export_data/';
        window.location.href = url;
    };

    // Handle stock data upload.
    const uploadStockData = async () => {
        const fileInput = document.getElementById('uploadStockData');
        const file = fileInput.files[0];
        if (!file) {
            notify(tr('Please select a file to upload.'), 'warning');
            return;
        }

        // Check for destructive upload config.
        if (window.allowUploadDeletions) {
            const confirmed = await confirmDialog({
                title: 'Destructive upload',
                message: tr('The system is configured to delete all warehouse and site data that is not included in this upload.') + ' ' + tr('This action cannot be undone. Continue?'),
                confirmLabel: tr('Upload anyway'),
                cancelLabel: 'Cancel',
                destructive: true
            });
            if (!confirmed) {
                return;
            }
        }

        const formData = new FormData();
        formData.append('file', file);

        $.ajax({
            url: '/api/import_data/',
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            headers: { 'X-CSRFToken': getCSRFToken() },
            success: (data) => {
                let msg = tr('Stock data uploaded successfully.');
                if (data && data.detail) msg = data.detail;
                if (data && Array.isArray(data.skipped_skus) && data.skipped_skus.length) {
                    msg += '\n\nThe following SKUs had invalid retail_price values and were skipped:\n' + data.skipped_skus.join(', ');
                }
                notify(msg, 'success');
                fetchItems(1);
            },
            error: xhr => {
                notify(errorDetail(xhr, tr('Failed to upload stock data.')), 'error');
            }
        });
    };

    // Mark edited fields so unsaved changes are visible.
    const attachQntChangeColorUpdateListener = () => {
        Object.keys(TABLE_META).map(Number).forEach(tableNum => {
            $(`#itemTable${tableNum}`).on('input', 'input[type="number"]', function () {
                $(this).addClass('is-dirty');
            });
        });
    };

    // Toggle update mode.
    const updateModeChangeHandler = () => {
        let current_lock_status = $('#updateModeToggle').prop('checked');
        setEditLockStatus(current_lock_status);
    };

    /* ==============================================================
       Role tailoring
       ============================================================== */

    // Show the controls this reader may use. The shell (name, role, menu) is
    // rendered by the server, so only the page's own controls are tailored.
    const tailor_dashboard = () => {
        const groups = window.userGroups || [];
        const isManager = groups.includes("managers");
        const isShopUser = groups.includes("shop_users");

        if (isManager) {
            setEditLockStatus(false);
            $("#addItemSection, #updateModeSwitch").removeClass("d-none");
            $("#downloadStockData, #uploadStockData, #uploadStockDataButton, #importPanel").removeClass("d-none");
            $("#refreshWarehouse").removeClass("d-none");
        } else {
            $("#importPanel").addClass("d-none");
            if (isShopUser) {
                $("#submitTransferRequest").removeClass("d-none");
                $("#refreshWarehouse").removeClass("d-none");
                $("#downloadStockData").removeClass("d-none");
            }
        }
        if (!isShopUser) {
            $("th#whXferQnt").hide();
        }
        if (isShopUser) {
            $("th#whActions").hide();
        }
        updateUIBasedOnEditLock();
    };

    // Learn who is reading, then draw the tables this page has.
    const loadViewer = () => {
        return $.ajax({
            url: '/api/auth/user/',
            method: 'GET',
            xhrFields: { withCredentials: true },
            success: data => {
                window.loggedInUsername = data.username || '';
                window.userGroups = data.groups || [];
                tailor_dashboard();
                tablesOnPage().forEach((tn) => fetchItems(tn));
            },
            error: () => {
                window.userGroups = [];
                tailor_dashboard();
                tablesOnPage().forEach((tn) => fetchItems(tn));
            }
        });
    };

    /* ==============================================================
       Exports & event wiring
       ============================================================== */

    // Expose functions to global scope (inline handlers in the markup).
    window.sortTable = sortTable;
    window.fetchItems = fetchItems;
    window.updateItem = updateItem;
    window.deleteItem = deleteItem;
    window.transferItem = transferItem;
    window.completeTransfer = completeTransfer;
    window.updateModeChangeHandler = updateModeChangeHandler;
    window.tailor_dashboard = tailor_dashboard;
    window.updatePageGlobals = updatePageGlobals;
    window.search = search;
    window.notify = notify;

    $(document).on("blur", ".wh_editable-field", function () {
        var sku = $(this).data("sku");
        var fieldName = $(this).data("field");
        var newValue = $(this).val();
        if (fieldName == 'xfer_qnt') {
            if (Number.isInteger(parseInt(newValue), 10)) {
                newValue > 0 ? transferItem(sku, newValue) : console.log(tr('Enter more than 0!'));
            }
        } else {
            updateItem(1, sku, fieldName, newValue);
        }
    });

    // Transfer action buttons carry the SKU / shop user as data attributes
    // (read as exact strings) rather than interpolating them into inline
    // onclick handlers, so hostile values cannot inject JavaScript.
    $(document).on("click", ".dispatch-btn", function () {
        completeTransfer($(this).attr('data-sku'), $(this).attr('data-shop-user'), 'false');
    });
    $(document).on("click", ".cancel-btn", function () {
        completeTransfer($(this).attr('data-sku'), $(this).attr('data-shop-user'), 'true');
    });
    $(document).on("click", ".delete-item-btn", function () {
        deleteItem($(this).attr('data-sku'), 1);
    });

    $(document).on("blur", `input[id^="quantity3-"]`, function () {
        const id = $(this).attr('id');
        const sku = id.replace('quantity3-', '');
        const shopUserID = $(this).data('shop_user_id');
        setXferVals(shopUserID, sku, $(this).val());
    });

    $(document).ready(() => {
        fetchAppConfig().always(() => {
            loadViewer();
            $('#addItem').click(addItem);
            $('#submitTransferRequest').click(submitTransferRequest);
            $('#updateModeToggle').change(updateModeChangeHandler);
            attachQntChangeColorUpdateListener();
            $('#refreshInventory').click(() => tablesOnPage().forEach(tn => fetchItems(tn)));
            $('#refreshTransfersPending').click(() => tablesOnPage().forEach(tn => fetchItems(tn)));
            $('#refreshWarehouse').click(() => fetchItems(1));
            $('#downloadStockData').click(() => downloadStockData());
            $('#uploadStockDataButton').click(uploadStockData);
        });
    });
})();
