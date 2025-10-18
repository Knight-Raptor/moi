frappe.pages['stock-operations'].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Stock Operations',
		single_column: true
	});

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

	let $table = $('<div class="stock-table mt-4"></div>').appendTo(page.body);

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
					render_table(r.message);
				}
			}
		});
	}

	function render_table(data) {
		let html = `
			<table class="table table-bordered">
				<thead>
					<tr>
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
			html += `
				<tr>
					<td>${d.item_code || ''}</td>
					<td>${d.item_name || ''}</td>
					<td>${d.barcode || ''}</td>
					<td>${d.balance_qty || 0}</td>
					<td>${d.expired_qty || 0}</td>
					<td>
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

		bind_button_events();
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
			console.log('Print button clicked for item:', item);
			open_print_dialog(item);
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
				let has_batch = item_details.has_batch_no || 0;
				let barcode = item_details.barcode || '';

				console.log('Item Details:', item_details); // Debug log

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

				// Batch fields (if item has batch)
				if (has_batch) {
					if (type === 'Add') {
						// For Add operation, create new batch
						fields.push({ fieldtype: 'Section Break', label: 'Batch Details' });
						fields.push({
							label: 'Batch ID',
							fieldname: 'batch_id',
							fieldtype: 'Data',
							reqd: 1
						});
						fields.push({
							label: 'Manufacturing Date',
							fieldname: 'manufacturing_date',
							fieldtype: 'Date',
							reqd: 1
						});
						fields.push({
							label: 'Expiry Date',
							fieldname: 'expiry_date',
							fieldtype: 'Date'
						});
					} else {
						// For Issue/Transfer, select existing batch
						fields.push({
							label: 'Batch',
							fieldname: 'batch_no',
							fieldtype: 'Link',
							options: 'Batch',
							reqd: 1,
							get_query: function() {
								return {
									filters: {
										'item': item_code,
										'disabled': 0
									}
								};
							}
						});
					}
				}

				// Quantity and Price
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
					primary_action_label: 'Submit',
					primary_action(values) {
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

						// Add batch-related fields
						if (has_batch) {
							if (type === 'Add') {
								data.batch_id = values.batch_id;
								data.manufacturing_date = values.manufacturing_date;
								data.expiry_date = values.expiry_date;
							} else {
								data.batch_no = values.batch_no;
							}
						}

						frappe.call({
							method: 'moi.moi.page.stock_operations.stock_operations.make_stock_entry',
							args: data,
							callback: function (res) {
								if (!res.exc) {
									frappe.msgprint(__(`${type} Stock Entry created: ${res.message}`));
									d.hide();
									load_items();
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