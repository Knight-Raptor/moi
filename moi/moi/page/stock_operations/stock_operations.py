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
        conditions += f" AND ib.barcode= {frappe.db.escape(barcode)}"

    items = frappe.db.sql(f"""
        SELECT 
            i.name AS item_code,
            i.item_name,
            ib.barcode,
            IFNULL(SUM(CASE WHEN b.warehouse = mapping.warehouse THEN b.actual_qty ELSE 0 END), 0) AS balance_qty,
            IFNULL(expired.expired_qty, 0) AS expired_qty
        FROM `tabItem` i
        LEFT JOIN `tabBin` b ON b.item_code = i.name
        LEFT JOIN `tabItem Barcode` ib ON ib.parent = i.name
        LEFT JOIN (
            SELECT item_group, warehouse 
            FROM `tabTable Mapping Setting`
        ) AS mapping ON mapping.item_group = i.item_group
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
def get_mapping_by_item_group(item_group):
    """Get warehouse mapping from Table Mapping Setting based on item group"""
    mapping = frappe.db.sql("""
        SELECT warehouse 
        FROM `tabTable Mapping Setting` 
        WHERE item_group = %s
        LIMIT 1
    """, (item_group,), as_dict=True)
    
    return mapping[0] if mapping else {}


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


def get_submit_setting():
    """Get submit setting from Table Mapping doctype"""
    # Get the check_submit field from Table Mapping doctype
    submit_setting = frappe.db.get_value("Table Mapping", None, "check_submit")

    # Debug log to see what value we're getting
    frappe.log_error(f"Submit setting raw value: {submit_setting}, Type: {type(submit_setting)}", "Debug Submit Setting")

    # Convert to integer safely (handles '0', '1', None, etc.)
    try:
        submit_setting = cint(submit_setting)
    except Exception:
        submit_setting = 0

    # Return True only if check_submit is checked (1)
    return submit_setting == 1



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
    
    # Insert
    stock_entry.insert()
    
    # Check if we should submit based on Table Mapping setting
    should_submit = get_submit_setting()
    if should_submit:
        stock_entry.submit()
        frappe.msgprint(_("Stock Entry {0} submitted successfully").format(stock_entry.name))
    else:
        frappe.msgprint(_("Stock Entry {0} created in draft").format(stock_entry.name))
    
    return stock_entry.name


@frappe.whitelist()
def get_bulk_item_details(item_codes):
    """Get details for multiple items including latest valuation rate"""
    import json
    if isinstance(item_codes, str):
        item_codes = json.loads(item_codes)
    
    items_data = []
    for item_code in item_codes:
        item = frappe.get_doc("Item", item_code)
        
        # Get latest valuation rate from multiple sources (in priority order)
        valuation_rate = 0
        
        # 1. Try to get from latest Stock Ledger Entry
        latest_sle = frappe.db.sql("""
            SELECT valuation_rate 
            FROM `tabStock Ledger Entry` 
            WHERE item_code = %s 
            AND valuation_rate > 0
            ORDER BY posting_date DESC, posting_time DESC 
            LIMIT 1
        """, (item_code,), as_dict=True)
        
        if latest_sle:
            valuation_rate = latest_sle[0].valuation_rate
        else:
            # 2. Try Item Price (Buying)
            item_price = frappe.db.get_value("Item Price", 
                {"item_code": item_code, "buying": 1}, 
                "price_list_rate")
            
            if item_price:
                valuation_rate = item_price
            else:
                # 3. Fallback to item's valuation_rate field
                valuation_rate = item.valuation_rate or 0
        
        items_data.append({
            "item_code": item.name,
            "item_name": item.item_name,
            "valuation_rate": valuation_rate
        })
    
    return items_data


@frappe.whitelist()
def make_bulk_stock_entry(items, warehouse, type, posting_date=None,
                          target_warehouse=None, department=None):
    """Create bulk stock entries for multiple items with individual qty and price"""
    
    # Convert items from JSON string to list
    import json
    if isinstance(items, str):
        items = json.loads(items)
    
    # Map operation type to stock entry purpose
    purpose_map = {
        "Add": "Material Receipt",
        "Issue": "Material Issue",
        "Transfer": "Material Transfer"
    }
    
    purpose = purpose_map.get(type)
    if not purpose:
        frappe.throw(_("Invalid operation type"))
    
    # Create a single stock entry with multiple items
    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.stock_entry_type = purpose
    stock_entry.posting_date = posting_date or nowdate()
    
    # Add department for Issue operations
    if department:
        stock_entry.custom_department = department
    
    # Add each item to the stock entry with its individual qty and price
    for item in items:
        item_dict = {
            "item_code": item.get("item_code"),
            "qty": item.get("qty"),
            "basic_rate": item.get("price"),
            "conversion_factor": 1,
            "transfer_qty": item.get("qty"),
            "uom": frappe.db.get_value("Item", item.get("item_code"), "stock_uom")
        }
        
        # Set warehouses based on operation type
        if type == "Add":
            item_dict["t_warehouse"] = warehouse
        elif type == "Issue":
            item_dict["s_warehouse"] = warehouse
        elif type == "Transfer":
            item_dict["s_warehouse"] = warehouse
            item_dict["t_warehouse"] = target_warehouse
        
        stock_entry.append("items", item_dict)
    
    # Insert
    stock_entry.insert()
    
    # Check if we should submit based on Table Mapping setting
    should_submit = get_submit_setting()
    if should_submit:
        stock_entry.submit()
        frappe.msgprint(_("Stock Entry {0} submitted successfully").format(stock_entry.name))
    else:
        frappe.msgprint(_("Stock Entry {0} created in draft").format(stock_entry.name))
    
    return {
        "status": "success",
        "stock_entry": stock_entry.name,
        "items_count": len(items),
        "submitted": should_submit
    }


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