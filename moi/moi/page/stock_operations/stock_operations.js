frappe.pages['stock-operations'].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Stock Operations',
		single_column: true
	});

	// Track selected items
	let selected_items = new Set();

	// --- Filters ---
	let filters = {
		item_group: page.add_field({
			fieldname: "item_group",
			label: "Item Group",
			fieldtype: "Link",
			options: "Item Group",
			change() {
				load_items();
			}
		}),
		item_code: page.add_field({
			fieldname: "item_code",
			label: "Item Code",
			fieldtype: "Link",
			options: "Item",
			change() {
				load_items();
			}
		}),
		barcode: page.add_field({
			fieldname: "barcode",
			label: "Barcode",
			fieldtype: "Data",
			change() {
				load_items();
			}
		})
	};

	// --- Bulk Action Toolbar ---
	let $bulk_toolbar = $(`
		<div class="bulk-actions-toolbar mb-3" style="display: none; padding: 10px; background: #f8f9fa; border-radius: 5px;">
			<button class="btn btn-sm btn-primary bulk-add-btn" disabled>
				<i class="fa fa-plus"></i> Add
			</button>
			<button class="btn btn-sm btn-warning bulk-issue-btn" disabled>
				<i class="fa fa-arrow-right"></i> Issue
			</button>
			<button class="btn btn-sm btn-info bulk-transfer-btn" disabled>
				<i class="fa fa-exchange"></i> Transfer
			</button>
			<span class="ml-3 text-muted" style="margin-left: 15px;">
				<span class="selected-count">0</span> item(s) selected
			</span>
		</div>
	`).appendTo(page.body);

	let $table = $('<div class="stock-table mt-2"></div>').appendTo(page.body);

	// Bulk button event handlers
	$('.bulk-add-btn').on('click', function() {
		if (selected_items.size > 0) {
			open_bulk_popup('Add', Array.from(selected_items));
		}
	});

	$('.bulk-issue-btn').on('click', function() {
		if (selected_items.size > 0) {
			open_bulk_popup('Issue', Array.from(selected_items));
		}
	});

	$('.bulk-transfer-btn').on('click', function() {
		if (selected_items.size > 0) {
			open_bulk_popup('Transfer', Array.from(selected_items));
		}
	});

	function load_items() {
		frappe.call({
			method: 'moi.moi.page.stock_operations.stock_operations.get_items',
			args: {
				item_group: filters.item_group.get_value(),
				item_code: filters.item_code.get_value(),
				barcode: filters.barcode.get_value()
			},
			callback: function (r) {
				if (r.message) {
					selected_items.clear();
					render_table(r.message);
					update_bulk_toolbar();
				}
			}
		});
	}

	function render_table(data) {
		let html = `
			<table class="table table-bordered">
				<thead>
					<tr>
						<th style="width: 40px;">
							<input type="checkbox" id="select-all-checkbox" />
						</th>
						<th>Item Code</th>
						<th>Item Name</th>
						<th>Barcode</th>
						<th>Balance Qty</th>
						<th>Expired Qty</th>
						<th>Actions</th>
					</tr>
				</thead>
				<tbody>
		`;

		data.forEach(d => {
			const isSelected = selected_items.has(d.item_code);
			html += `
				<tr>
					<td>
						<input type="checkbox" class="item-checkbox" 
							   data-item="${d.item_code}" 
							   ${isSelected ? 'checked' : ''} />
					</td>
					<td>
						<a href="/app/item/${encodeURIComponent(d.item_code)}" 
						   target="_blank" 
						   style="color: #2490ef; text-decoration: none;">
							${d.item_code || ''}
						</a>
					</td>
					<td>${d.item_name || ''}</td>
					<td>${d.barcode || ''}</td>
					<td>${d.balance_qty || 0}</td>
					<td>${d.expired_qty || 0}</td>
					<td class="action-buttons">
						<button class="btn btn-sm btn-primary add-btn" data-item="${d.item_code}">Add</button>
						<button class="btn btn-sm btn-warning issue-btn" data-item="${d.item_code}">Issue</button>
						<button class="btn btn-sm btn-info transfer-btn" data-item="${d.item_code}">Transfer</button>
						<button class="btn btn-sm btn-secondary print-btn" data-item="${d.item_code}">Print Barcode</button>
					</td>
				</tr>
			`;
		});

		html += `</tbody></table>`;
		$table.html(html);

		bind_checkbox_events();
		bind_button_events();
		update_row_buttons_state();
	}

	function bind_checkbox_events() {
		// Select All checkbox
		$('#select-all-checkbox').off().on('change', function() {
			const isChecked = $(this).prop('checked');
			$('.item-checkbox').prop('checked', isChecked);
			
			if (isChecked) {
				$('.item-checkbox').each(function() {
					selected_items.add($(this).data('item'));
				});
			} else {
				selected_items.clear();
			}
			
			update_bulk_toolbar();
			update_row_buttons_state();
		});

		// Individual item checkboxes
		$('.item-checkbox').off().on('change', function() {
			const item_code = $(this).data('item');
			
			if ($(this).prop('checked')) {
				selected_items.add(item_code);
			} else {
				selected_items.delete(item_code);
				$('#select-all-checkbox').prop('checked', false);
			}
			
			// Update "Select All" checkbox state
			const total_checkboxes = $('.item-checkbox').length;
			const checked_checkboxes = $('.item-checkbox:checked').length;
			$('#select-all-checkbox').prop('checked', total_checkboxes === checked_checkboxes);
			
			update_bulk_toolbar();
			update_row_buttons_state();
		});
	}

	function update_bulk_toolbar() {
		const count = selected_items.size;
		
		if (count > 0) {
			$bulk_toolbar.show();
			$('.bulk-add-btn, .bulk-issue-btn, .bulk-transfer-btn').prop('disabled', false);
			$('.selected-count').text(count);
		} else {
			$bulk_toolbar.hide();
			$('.bulk-add-btn, .bulk-issue-btn, .bulk-transfer-btn').prop('disabled', true);
			$('.selected-count').text(0);
		}
	}

	function update_row_buttons_state() {
		if (selected_items.size > 0) {
			// Grey out/disable row action buttons when in bulk mode
			$('.action-buttons button').not('.print-btn').css({
				'opacity': '0.5',
				'pointer-events': 'none'
			});
		} else {
			// Enable row action buttons when not in bulk mode
			$('.action-buttons button').css({
				'opacity': '1',
				'pointer-events': 'auto'
			});
		}
	}

	function bind_button_events() {
		$('.add-btn').off().on('click', function () {
			open_popup('Add', $(this).data('item'));
		});
		$('.issue-btn').off().on('click', function () {
			open_popup('Issue', $(this).data('item'));
		});
		$('.transfer-btn').off().on('click', function () {
			open_popup('Transfer', $(this).data('item'));
		});
		$('.print-btn').off().on('click', function () {
			let item = $(this).data('item');
			open_print_dialog(item);
		});
	}

	function open_bulk_popup(type, item_codes) {
		frappe.call({
			method: 'moi.moi.page.stock_operations.stock_operations.get_bulk_item_details',
			args: { item_codes },
			callback: function(r) {
				if (!r.message) return;
				let items_data = r.message;

				// First, auto-fetch warehouse from selected item group
				let item_group = filters.item_group.get_value() || null;
				let default_warehouse = '';
				if (item_group) {
					frappe.call({
						method: 'moi.moi.page.stock_operations.stock_operations.get_mapping_by_item_group',
						args: { item_group },
						async: false,
						callback: (res) => {
							if (res.message && res.message.warehouse)
								default_warehouse = res.message.warehouse;
						}
					});
				}

				let fields = [
					{
						label: 'Warehouse',
						fieldname: 'warehouse',
						fieldtype: 'Link',
						options: 'Warehouse',
						reqd: 1,
						default: default_warehouse
					}
				];

				if (type === 'Transfer') fields.push({
					label: 'Target Warehouse', fieldname: 'target_warehouse',
					fieldtype: 'Link', options: 'Warehouse', reqd: 1
				});
				if (type === 'Issue') fields.push({
					label: 'Department', fieldname: 'department',
					fieldtype: 'Link', options: 'Department', reqd: 1
				});

				fields.push({
					label: 'Posting Date',
					fieldname: 'posting_date',
					fieldtype: 'Date',
					default: frappe.datetime.get_today(),
					reqd: 1
				});

				fields.push({ fieldtype: 'Section Break', label: 'Items' });

				// 🟡 Global Quantity Field
				fields.push({
					label: 'Set Quantity for All Items',
					fieldname: 'set_all_qty',
					fieldtype: 'Float',
					description: 'Enter a number to apply to all rows automatically'
				});

				fields.push({
					fieldname: 'items',
					fieldtype: 'Table',
					label: 'Items',
					cannot_add_rows: true,
					cannot_delete_rows: true,
					fields: [
						{ fieldname: 'item_code', fieldtype: 'Link', label: 'Item Code', options: 'Item', in_list_view: 1, read_only: 1 },
						{ fieldname: 'item_name', fieldtype: 'Data', label: 'Item Name', in_list_view: 1, read_only: 1 },
						{ fieldname: 'qty', fieldtype: 'Float', label: 'Quantity', in_list_view: 1, reqd: 1 },
						{ fieldname: 'price', fieldtype: 'Currency', label: 'Price', in_list_view: 1, reqd: 1 }
					],
					data: items_data.map(i => ({
						item_code: i.item_code,
						item_name: i.item_name,
						qty: 1,
						price: i.valuation_rate || 0
					}))
				});

				let d = new frappe.ui.Dialog({
					title: `Bulk ${type} - ${item_codes.length} Items`,
					fields,
					size: 'large',
					primary_action_label: 'Create',
					primary_action(values) {
						let items = values.items || [];
						if (!items.length) return;
						for (let row of items) {
							if (!row.qty || !row.price) {
								frappe.msgprint(__('All rows must have quantity and price'));
								return;
							}
						}
						
						// Show processing message
						frappe.show_alert({
							message: __('Creating Stock Entry...'),
							indicator: 'blue'
						});
						
						frappe.call({
							method: 'moi.moi.page.stock_operations.stock_operations.make_bulk_stock_entry',
							args: {
								items, warehouse: values.warehouse,
								type, posting_date: values.posting_date,
								target_warehouse: values.target_warehouse || null,
								department: values.department || null
							},
							callback: function(res) {
								if (!res.exc) {
									let message = res.message;
									
									if (message.submitted) {
										frappe.show_alert({
											message: __('Stock Entry {0} submitted successfully', [message.stock_entry]),
											indicator: 'green'
										});
									} else {
										frappe.show_alert({
											message: __('Stock Entry {0} created in draft', [message.stock_entry]),
											indicator: 'blue'
										});
									}
									
									d.hide(); 
									selected_items.clear(); 
									load_items();
								}
							}
						});
					}
				});

				// --- 🟡 Bind global qty update ---
				d.fields_dict.set_all_qty.df.onchange = function() {
					let qty = d.get_value('set_all_qty');
					let table = d.fields_dict.items.grid;
					table.data.forEach(row => row.qty = qty);
					table.refresh();
				};

				d.show();
			}
		});
	}

	function open_popup(type, item_code) {
		frappe.call({
			method: 'moi.moi.page.stock_operations.stock_operations.get_item_details',
			args: { item_code },
			callback: function (r) {
				if (!r.message) return;

				let item_details = r.message;
				let warehouse = item_details.warehouse || '';
				let valuation_rate = item_details.valuation_rate || 0;
				let barcode = item_details.barcode || '';

				// Build dialog fields based on operation type
				let fields = [
					{ 
						label: 'Item Code', 
						fieldname: 'item_code', 
						fieldtype: 'Data', 
						read_only: 1, 
						default: item_code 
					}
				];

				// Add barcode field if exists
				if (barcode) {
					fields.push({ 
						label: 'Barcode', 
						fieldname: 'barcode', 
						fieldtype: 'Data', 
						read_only: 1, 
						default: barcode 
					});
				}

				// Add warehouse field
				fields.push({ 
					label: 'Warehouse', 
					fieldname: 'warehouse', 
					fieldtype: 'Link', 
					options: 'Warehouse', 
					default: warehouse,
					reqd: 1
				});

				// Add type-specific fields
				if (type === 'Transfer') {
					fields.push({
						label: 'Target Warehouse',
						fieldname: 'target_warehouse',
						fieldtype: 'Link',
						options: 'Warehouse',
						reqd: 1
					});
				}

				if (type === 'Issue') {
					fields.push({
						label: 'Department',
						fieldname: 'department',
						fieldtype: 'Link',
						options: 'Department',
						reqd: 1
					});
				}

				// Common fields
				fields.push({
					label: 'Date',
					fieldname: 'posting_date',
					fieldtype: 'Date',
					default: frappe.datetime.get_today(),
					reqd: 1
				});

				fields.push({
					label: 'Quantity',
					fieldname: 'qty',
					fieldtype: 'Float',
					reqd: 1
				});
				fields.push({
					label: 'Price',
					fieldname: 'price',
					fieldtype: 'Currency',
					default: valuation_rate
				});

				// Create dialog
				let d = new frappe.ui.Dialog({
					title: `${type} Item - ${item_code}`,
					fields: fields,
					primary_action_label: 'Create',
					primary_action(values) {
						// Show processing message
						frappe.show_alert({
							message: __('Creating Stock Entry...'),
							indicator: 'blue'
						});
						
						// Prepare data for submission
						let data = {
							item_code: values.item_code,
							qty: values.qty,
							price: values.price,
							warehouse: values.warehouse,
							posting_date: values.posting_date,
							type: type
						};

						// Add type-specific fields
						if (type === 'Transfer') {
							data.target_warehouse = values.target_warehouse;
						}
						if (type === 'Issue') {
							data.department = values.department;
						}

						frappe.call({
							method: 'moi.moi.page.stock_operations.stock_operations.make_stock_entry',
							args: data,
							callback: function (res) {
								if (!res.exc) {
									let stock_entry_name = res.message;
									
									// Check if stock entry was submitted or saved as draft
									frappe.call({
										method: 'frappe.client.get_value',
										args: {
											doctype: 'Stock Entry',
											filters: { name: stock_entry_name },
											fieldname: 'docstatus'
										},
										callback: function(doc_res) {
											if (!doc_res.exc) {
												let docstatus = doc_res.message.docstatus;
												
												if (docstatus === 1) {
													frappe.show_alert({
														message: __('Stock Entry {0} submitted successfully', [stock_entry_name]),
														indicator: 'green'
													});
												} else {
													frappe.show_alert({
														message: __('Stock Entry {0} created in draft', [stock_entry_name]),
														indicator: 'blue'
													});
												}
												
												d.hide();
												load_items();
											}
										}
									});
								}
							}
						});
					}
				});
				d.show();
			}
		});
	}

	function open_print_dialog(item_code) {
		let d = new frappe.ui.Dialog({
			title: `Print Barcode - ${item_code}`,
			fields: [
				{
					label: 'Number of Copies',
					fieldname: 'copies',
					fieldtype: 'Int',
					reqd: 1,
					default: 1
				}
			],
			primary_action_label: 'Print',
			primary_action(values) {
				if (values.copies < 1) {
					frappe.msgprint(__('Please enter a valid number of copies'));
					return;
				}
				print_barcode(item_code, values.copies);
				d.hide();
			}
		});
		d.show();
	}

	function print_barcode(item_code, copies) {
		frappe.call({
			method: 'moi.moi.page.stock_operations.stock_operations.get_barcode_data',
			args: { item_code: item_code },
			callback: function (r) {
				if (!r.message) {
					frappe.msgprint(__('No barcode found for this item'));
					return;
				}

				let item_data = r.message;
				let print_content = '';

				// Generate print content for each copy
				for (let i = 0; i < copies; i++) {
					item_data.barcodes.forEach(barcode_row => {
						print_content += `
							<div class="text-center">
								<div class="barcodemainbox">
									<p class="barcode-title"><b>${item_data.item_code}</b></p>
									<img style="width:100%;height:50px;"
										 src="https://generator.barcodetools.com/barcode.png?gen=0&data=${barcode_row.barcode}&bcolor=FFFFFF&fcolor=000000&tcolor=000000&fh=8&bred=0&w2n=1&xdim=2&w=&h=100&debug=1&btype=7&angle=0&quiet=1&balign=2&talign=2&guarg=1&text=0&tdown=0&stst=1&schk=0&cchk=1&ntxt=1&c128=0"/>
									<p class="barcode-number">${item_data.item_name}</p>
								</div>
							</div>
							<div class="page-break"></div>
						`;
					});
				}

				// Create print window with styles
				let print_html = `
					<!DOCTYPE html>
					<html>
					<head>
						<title>Print Barcode - ${item_data.item_code}</title>
						<style>
							@media print {
								.page-break {
									page-break-after: always;
								}
							}
							.text-center {
								text-align: center;
							}
							.barcodemainbox {
								margin: 20px auto;
								padding: 10px;
								max-width: 300px;
							}
							.barcode-title {
								font-size: 16px;
								margin-bottom: 10px;
							}
							.barcode-number {
								font-size: 14px;
								margin-top: 10px;
							}
						</style>
					</head>
					<body>
						${print_content}
					</body>
					</html>
				`;

				// Open print window
				let print_window = window.open('', '_blank');
				print_window.document.write(print_html);
				print_window.document.close();
				
				// Wait for images to load before printing
				setTimeout(() => {
					print_window.print();
				}, 500);
			}
		});
	}

	load_items();
};