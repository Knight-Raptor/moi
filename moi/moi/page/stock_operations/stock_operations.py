import frappe
from frappe import _
from frappe.utils import nowdate, cint

@frappe.whitelist()
def get_items(item_group=None, item_code=None, barcode=None):
	conditions = ""
	if item_group:
		conditions += f" AND i.item_group = {frappe.db.escape(item_group)}"
	if item_code:
		conditions += f" AND i.name = {frappe.db.escape(item_code)}"
	if barcode:
		conditions += f" AND ib.barcode = {frappe.db.escape(barcode)}"


	items = frappe.db.sql(f"""
		SELECT 
			i.name AS item_code,
			i.item_name,
			ib.barcode,
			IFNULL(SUM(b.actual_qty), 0) AS balance_qty,
			IFNULL(expired.expired_qty, 0) AS expired_qty
		FROM `tabItem` i
		LEFT JOIN `tabBin` b ON b.item_code = i.name
		LEFT JOIN `tabItem Barcode` ib ON ib.parent = i.name
		LEFT JOIN (
			SELECT
				sbb.item_code,
				SUM(
					CASE
						WHEN (bt.expiry_date IS NOT NULL AND bt.expiry_date <= CURDATE())
						THEN IFNULL(sbe.qty, 0)
						ELSE 0
					END
				) AS expired_qty
			FROM
				`tabSerial and Batch Bundle` sbb
			LEFT JOIN
				`tabSerial and Batch Entry` sbe ON sbe.parent = sbb.name
			LEFT JOIN
				`tabBatch` bt ON bt.name = sbe.batch_no
			WHERE
				sbb.docstatus = 1
			GROUP BY
				sbb.item_code
		) AS expired ON expired.item_code = i.name
		WHERE 1=1 {conditions}
		GROUP BY i.name, ib.barcode
		LIMIT 50
	""", as_dict=True)

	return items


@frappe.whitelist()
def get_item_details(item_code):
	"""Get item details including batch info and default warehouse"""
	item = frappe.get_doc("Item", item_code)
	
	# Get default warehouse from mapping using your existing logic
	mapping = get_mapping(item_code)
	warehouse = mapping.get("warehouse") if mapping else None
	
	# Get valuation rate from item price or valuation rate field
	valuation_rate = frappe.db.get_value("Item Price", 
		{"item_code": item_code}, 
		"price_list_rate") or item.valuation_rate or 0
	
	# Get first barcode from Item Barcode child table
	barcode = frappe.db.get_value("Item Barcode", 
		{"parent": item_code}, 
		"barcode")
	
	frappe.log_error(f"Barcode for {item_code}: {barcode}", "Debug Barcode")  # Debug log

	return {
		"warehouse": warehouse,
		"valuation_rate": valuation_rate,
		"has_batch_no": item.has_batch_no,
		"item_name": item.item_name,
		"barcode": barcode or ""
	}


@frappe.whitelist()
def get_mapping(item_code):
	"""Get warehouse mapping from Table Mapping Setting based on item group"""
	mapping = frappe.db.sql("""
		SELECT parent, warehouse 
		FROM `tabTable Mapping Setting` 
		WHERE item_group IN (
			SELECT item_group FROM `tabItem` WHERE name = %s
		)
		LIMIT 1
	""", (item_code,), as_dict=True)
	
	return mapping[0] if mapping else {}


@frappe.whitelist()
def make_stock_entry(item_code, qty, price, warehouse, type, posting_date=None, 
					 target_warehouse=None, department=None, batch_no=None, 
					 batch_id=None, manufacturing_date=None, expiry_date=None):
	"""Create Stock Entry based on operation type"""
	
	# Map operation type to stock entry purpose
	purpose_map = {
		"Add": "Material Receipt",
		"Issue": "Material Issue",
		"Transfer": "Material Transfer"
	}
	
	purpose = purpose_map.get(type)
	if not purpose:
		frappe.throw(_("Invalid operation type"))
	
	# Create Stock Entry
	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.stock_entry_type = purpose
	stock_entry.posting_date = posting_date or nowdate()
	
	# Add department for Issue operations
	if department:
		stock_entry.custom_department = department
	
	# Prepare item details
	item_dict = {
		"item_code": item_code,
		"qty": qty,
		"basic_rate": price,
		"conversion_factor": 1,
		"transfer_qty": qty,
		"uom": frappe.db.get_value("Item", item_code, "stock_uom")
	}
	
	# Handle batch operations
	if batch_id and manufacturing_date:
		# Create new batch for Add operation
		batch = create_batch(item_code, batch_id, manufacturing_date, expiry_date)
		item_dict["batch_no"] = batch.name
	elif batch_no:
		# Use existing batch for Issue/Transfer
		item_dict["batch_no"] = batch_no
	
	# Set warehouses based on operation type
	if type == "Add":
		item_dict["t_warehouse"] = warehouse
	elif type == "Issue":
		item_dict["s_warehouse"] = warehouse
	elif type == "Transfer":
		item_dict["s_warehouse"] = warehouse
		item_dict["t_warehouse"] = target_warehouse
	
	stock_entry.append("items", item_dict)
	
	# Insert and submit
	stock_entry.insert()
	stock_entry.submit()
	
	return stock_entry.name


def create_batch(item_code, batch_id, manufacturing_date, expiry_date=None):
	"""Create a new batch for the item"""
	
	# Check if batch already exists
	if frappe.db.exists("Batch", batch_id):
		frappe.throw(_("Batch {0} already exists").format(batch_id))
	
	batch = frappe.new_doc("Batch")
	batch.batch_id = batch_id
	batch.item = item_code
	batch.manufacturing_date = manufacturing_date
	
	if expiry_date:
		batch.expiry_date = expiry_date
	
	batch.insert()
	return batch


@frappe.whitelist()
def get_barcode_data(item_code):
	"""Get item details and barcodes for printing"""
	item = frappe.get_doc("Item", item_code)
	
	if not item.barcodes:
		return None
	
	barcodes = []
	for barcode_row in item.barcodes:
		barcodes.append({
			"barcode": barcode_row.barcode
		})
	
	return {
		"item_code": item.name,
		"item_name": item.item_name,
		"barcodes": barcodes
	}