import frappe
from frappe import _
from frappe.utils import nowdate, cint, flt

@frappe.whitelist()
def get_all_workspaces_with_mappings():
   
    try:
        workspaces = frappe.db.sql("""
            SELECT DISTINCT custom_workspace
            FROM `tabTable Mapping Setting`
            WHERE custom_workspace IS NOT NULL 
            AND custom_workspace != ''
        """, as_list=True)
        
        # Flatten the list of tuples to simple list
        workspace_list = [w[0] for w in workspaces if w[0]]
        
        frappe.logger().info(f"Found {len(workspace_list)} workspaces with mappings")
        
        return workspace_list
        
    except Exception as e:
        frappe.logger().error(f"Error in get_all_workspaces_with_mappings: {str(e)}")
        return []


@frappe.whitelist()
def get_workspace_filters(workspace):
    if not workspace:
        return {
            'success': False,
            'message': _('No workspace provided')
        }
    
    try:
        # Query all mappings for this workspace
        mappings = frappe.db.sql("""
            SELECT 
                tms.item_group,
                tms.warehouse,
                tms.custom_workspace
            FROM 
                `tabTable Mapping Setting` tms
            WHERE 
                tms.custom_workspace = %s
        """, (workspace,), as_dict=True)
        
        # Log for debugging
        frappe.logger().info(f"Searching for workspace: '{workspace}'")
        frappe.logger().info(f"Found {len(mappings)} mappings")
        
        if mappings:
            # Extract unique item groups and warehouses
            item_groups = list(set([m.item_group for m in mappings if m.item_group]))
            warehouses = list(set([m.warehouse for m in mappings if m.warehouse]))
            
            return {
                'success': True,
                'workspace': workspace,
                'item_groups': item_groups,
                'warehouses': warehouses,
                'mappings': mappings,
                'count': len(mappings)
            }
        else:
            # Log all available workspaces for debugging
            all_workspaces = frappe.db.sql("""
                SELECT DISTINCT custom_workspace, item_group, warehouse
                FROM `tabTable Mapping Setting`
                WHERE custom_workspace IS NOT NULL
            """, as_dict=True)
            
            frappe.logger().warning(f"No mapping found for workspace: '{workspace}'")
            frappe.logger().warning(f"Available workspaces: {all_workspaces}")
            
            # Print to console for debugging
            print("\n" + "="*80)
            print(f"DEBUG: No match found for workspace: '{workspace}'")
            print(f"All records in Table Mapping Setting:")
            for record in all_workspaces:
                print(f"  Item Group: {record.get('item_group')}, Warehouse: {record.get('warehouse')}, Workspace: '{record.get('custom_workspace')}'")
            print("="*80 + "\n")
            
            return {
                'success': False,
                'message': _('No mapping found for workspace: {0}').format(workspace),
                'workspace': workspace,
                'available_workspaces': [w.custom_workspace for w in all_workspaces]
            }
            
    except Exception as e:
        frappe.logger().error(f"Error in get_workspace_filters: {str(e)}")
        frappe.log_error(f"Workspace mapping error: {str(e)}", "Workspace Filter Error")
        import traceback
        traceback.print_exc()
        
        return {
            'success': False,
            'message': str(e)
        }


@frappe.whitelist()
def get_workspace_from_context():
    import re
    from urllib.parse import unquote
    
    # Try to get from referrer
    referrer = frappe.request.referrer or ""
    workspace_pattern = r'/app/([^/\?#]+)'
    match = re.search(workspace_pattern, referrer)
    
    if match:
        workspace_slug = match.group(1)
        # Decode URL encoding
        workspace_name = unquote(workspace_slug).replace('-', ' ')
        
        # Check if this workspace exists in our mappings
        exists = frappe.db.exists('Table Mapping Setting', {'custom_workspace': workspace_name})
        if exists:
            return workspace_name
    
    return None


@frappe.whitelist()
def get_items(item_group=None, item_code=None, barcode=None, workspace=None):
    
    if not workspace:
        workspace = get_workspace_from_context()
    
    conditions = ""
    
    # If workspace is provided, get its item groups and filter by them
    if workspace:
        workspace_data = get_workspace_filters(workspace)
        if workspace_data.get('success') and workspace_data.get('item_groups'):
            # Only apply workspace filter if user hasn't selected item_group manually
            if not item_group:
                item_groups = workspace_data['item_groups']
                # Create IN clause for item groups
                item_groups_str = ', '.join([frappe.db.escape(ig) for ig in item_groups])
                conditions += f" AND i.item_group IN ({item_groups_str})"

    
    # Additional filters
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
def get_item_group_by_workspace(workspace):
    result = get_workspace_filters(workspace)
    if result.get('success') and result.get('item_groups'):
        return {
            "item_group": result['item_groups'][0],
            "warehouse": result['warehouses'][0] if result.get('warehouses') else None
        }
    return {}


@frappe.whitelist()
def get_item_details(item_code):
    item = frappe.get_doc("Item", item_code)
    
    # Get default warehouse from mapping using your existing logic
    mapping = get_mapping(item_code)
    warehouse = mapping.get("warehouse") if mapping else None
    
    # Get default UOM
    default_uom = item.stock_uom
    
    # Get valuation rate - prioritize Item Price for stock UOM
    valuation_rate = 0
    
    # Try Item Price for stock UOM first
    item_price_stock_uom = frappe.db.sql("""
        SELECT price_list_rate 
        FROM `tabItem Price` 
        WHERE item_code = %s 
        AND uom = %s
        AND price_list_rate > 0
        ORDER BY valid_from DESC
        LIMIT 1
    """, (item_code, default_uom), as_dict=True)
    
    if item_price_stock_uom:
        valuation_rate = item_price_stock_uom[0].price_list_rate
    else:
        # Fallback to any item price or valuation rate
        valuation_rate = frappe.db.get_value("Item Price", 
            {"item_code": item_code}, 
            "price_list_rate") or item.valuation_rate or 0
    
    # Get first barcode from Item Barcode child table
    barcode = frappe.db.get_value("Item Barcode", 
        {"parent": item_code}, 
        "barcode")

    return {
        "warehouse": warehouse,
        "valuation_rate": valuation_rate,
        "has_batch_no": item.has_batch_no,
        "item_name": item.item_name,
        "barcode": barcode or "",
        "default_uom": default_uom
    }


@frappe.whitelist()
def get_single_item_uoms(doctype, txt, searchfield, start, page_len, filters):
    """Get UOMs defined for a specific item (must return list of lists for Link field)"""
    item_code = filters.get("item_code")
    if not item_code:
        return []

    # Get stock UOM (always available)
    stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
    uoms = [[stock_uom]]

    # Get additional UOMs from UOM Conversion Detail
    additional_uoms = frappe.db.sql("""
        SELECT uom
        FROM `tabUOM Conversion Detail`
        WHERE parent = %s AND uom != %s
    """, (item_code, stock_uom))

    uoms.extend(additional_uoms)

    # ✅ Must return list of lists, e.g. [["Box"], ["Set"]]
    return uoms


@frappe.whitelist()
def get_item_uoms(*args, **kwargs):
    # Case 1: Called manually via frappe.call
    item_code = kwargs.get("item_code")

    # Case 2: Called as query function
    if not item_code and len(args) >= 6:
        filters = args[5]
        item_code = filters.get("item_code") if filters else None

    if not item_code:
        return []

    # Get stock UOM (always available)
    stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
    uoms = [{"uom": stock_uom}]

    # Get additional UOMs from UOM Conversion Detail
    additional_uoms = frappe.db.sql("""
        SELECT uom 
        FROM `tabUOM Conversion Detail` 
        WHERE parent = %s AND uom != %s
    """, (item_code, stock_uom), as_dict=True)

    uoms.extend(additional_uoms)

    return uoms


@frappe.whitelist()
def get_price_for_uom(item_code, uom):
    """Get price/valuation rate for a specific UOM - prioritizes Item Price for selected UOM"""
    item = frappe.get_doc("Item", item_code)
    stock_uom = item.stock_uom
    
    # Get conversion factor for the selected UOM
    conversion_factor = 1
    if uom != stock_uom:
        conversion = frappe.db.get_value("UOM Conversion Detail", 
            {"parent": item_code, "uom": uom}, 
            "conversion_factor")
        if conversion:
            conversion_factor = flt(conversion)
    
    # PRIORITY 1: Check if Item Price exists for this specific UOM
    item_price_for_uom = frappe.db.sql("""
        SELECT price_list_rate 
        FROM `tabItem Price` 
        WHERE item_code = %s 
        AND uom = %s
        AND price_list_rate > 0
        ORDER BY valid_from DESC
        LIMIT 1
    """, (item_code, uom), as_dict=True)
    
    if item_price_for_uom:
        # Direct price found for this UOM - use it as is
        return {
            "price": item_price_for_uom[0].price_list_rate,
            "conversion_factor": conversion_factor,
            "source": "Item Price (UOM-specific)"
        }
    
    # PRIORITY 2: Get base rate (in stock UOM) and apply conversion
    base_rate = 0
    source = ""
    
    # Try to get from latest Stock Ledger Entry (stock UOM)
    latest_sle = frappe.db.sql("""
        SELECT valuation_rate 
        FROM `tabStock Ledger Entry` 
        WHERE item_code = %s 
        AND valuation_rate > 0
        ORDER BY posting_date DESC, posting_time DESC 
        LIMIT 1
    """, (item_code,), as_dict=True)
    
    if latest_sle:
        base_rate = latest_sle[0].valuation_rate
        source = "Stock Ledger Entry"
    else:
        # Try Item Price (stock UOM or any UOM)
        item_price = frappe.db.sql("""
            SELECT price_list_rate, uom
            FROM `tabItem Price` 
            WHERE item_code = %s 
            AND price_list_rate > 0
            ORDER BY 
                CASE WHEN uom = %s THEN 0 ELSE 1 END,
                valid_from DESC
            LIMIT 1
        """, (item_code, stock_uom), as_dict=True)
        
        if item_price:
            base_rate = item_price[0].price_list_rate
            source = "Item Price"
            
            # If the found price is for a different UOM, convert it to stock UOM first
            price_uom = item_price[0].uom
            if price_uom != stock_uom:
                price_uom_conversion = frappe.db.get_value("UOM Conversion Detail", 
                    {"parent": item_code, "uom": price_uom}, 
                    "conversion_factor")
                if price_uom_conversion:
                    # Convert price to stock UOM base
                    base_rate = base_rate / flt(price_uom_conversion)
        else:
            # Fallback to item's valuation_rate field
            base_rate = item.valuation_rate or 0
            source = "Item Valuation Rate"
    
    # Calculate price for the selected UOM
    # If conversion_factor = 2 (1 Box = 2 Units), price per Box = base_rate * 2
    price = flt(base_rate) * flt(conversion_factor)
    
    return {
        "price": price,
        "conversion_factor": conversion_factor,
        "source": source
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
    submit_setting = frappe.db.get_value("Table Mapping", None, "check_submit")

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
                     batch_id=None, manufacturing_date=None, expiry_date=None, uom=None,
                     custom_main_department=None, custom_division=None):
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
    
    # Get item details for stock UOM
    item = frappe.get_doc("Item", item_code)
    stock_uom = item.stock_uom
    
    # Get conversion factor if UOM is different from stock UOM
    conversion_factor = 1
    if uom and uom != stock_uom:
        conversion = frappe.db.get_value("UOM Conversion Detail", 
            {"parent": item_code, "uom": uom}, 
            "conversion_factor")
        if conversion:
            conversion_factor = flt(conversion)
    
    # Calculate quantity in stock UOM
    stock_qty = flt(qty) * flt(conversion_factor)
    
    # Create Stock Entry
    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.stock_entry_type = purpose
    stock_entry.posting_date = posting_date or nowdate()
    
    # Add department for Issue and Transfer operations
    if department:
        stock_entry.custom_department = department
    
    # Add Main Department for Issue and Transfer operations
    if custom_main_department:
        stock_entry.custom_main_department = custom_main_department
    
    # Add Division for Issue and Transfer operations
    if custom_division:
        stock_entry.custom_division = custom_division
    
    # Prepare item details
    item_dict = {

        "item_code": item_code,

        "qty": flt(qty),                 # user-entered qty

        "uom": uom or stock_uom,

        "stock_uom": stock_uom,

        "conversion_factor": conversion_factor,

        "basic_rate": flt(price)         # rate per Box

    }
    # item_dict = {
    #     "item_code": item_code,
    #     "qty": stock_qty,  # Stock quantity
    #     "basic_rate": flt(price) / flt(conversion_factor) if conversion_factor else flt(price),  # Rate per stock UOM
    #     "conversion_factor": conversion_factor,
    #     "transfer_qty": stock_qty,
    #     "uom": uom or stock_uom,
    #     "stock_uom": stock_uom
    # }
    
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
    
    # Submit only for ADD operation – Issue and Transfer will always remain draft
    if type == "Add" and get_submit_setting():
        stock_entry.submit()
        frappe.msgprint(_("Stock Entry {0} submitted").format(stock_entry.name))
    else:
        if type == "Add":
            frappe.msgprint(_("Stock Entry {0} created as Draft (auto submit disabled)").format(stock_entry.name))
        else:
            frappe.msgprint(_("Stock Entry {0} is created as Draft for approval workflow").format(stock_entry.name))

    return stock_entry.name


@frappe.whitelist()
def get_bulk_item_details(item_codes):
    """Get details for multiple items including latest valuation rate and default UOM"""
    import json
    if isinstance(item_codes, str):
        item_codes = json.loads(item_codes)
    
    items_data = []
    for item_code in item_codes:
        item = frappe.get_doc("Item", item_code)
        stock_uom = item.stock_uom
        
        # Get latest valuation rate - prioritize Item Price for stock UOM
        valuation_rate = 0
        
        # 1. Try to get Item Price for stock UOM first
        item_price_stock_uom = frappe.db.sql("""
            SELECT price_list_rate 
            FROM `tabItem Price` 
            WHERE item_code = %s 
            AND uom = %s
            AND price_list_rate > 0
            ORDER BY valid_from DESC
            LIMIT 1
        """, (item_code, stock_uom), as_dict=True)
        
        if item_price_stock_uom:
            valuation_rate = item_price_stock_uom[0].price_list_rate
        else:
            # 2. Try to get from latest Stock Ledger Entry
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
                # 3. Try any Item Price (any UOM) and convert to stock UOM
                any_item_price = frappe.db.sql("""
                    SELECT price_list_rate, uom
                    FROM `tabItem Price` 
                    WHERE item_code = %s 
                    AND price_list_rate > 0
                    ORDER BY valid_from DESC
                    LIMIT 1
                """, (item_code,), as_dict=True)
                
                if any_item_price:
                    price = any_item_price[0].price_list_rate
                    price_uom = any_item_price[0].uom
                    
                    # Convert to stock UOM if different
                    if price_uom != stock_uom:
                        conversion = frappe.db.get_value("UOM Conversion Detail", 
                            {"parent": item_code, "uom": price_uom}, 
                            "conversion_factor")
                        if conversion:
                            valuation_rate = price / flt(conversion)
                        else:
                            valuation_rate = price
                    else:
                        valuation_rate = price
                else:
                    # 4. Fallback to item's valuation_rate field
                    valuation_rate = item.valuation_rate or 0
        
        items_data.append({
            "item_code": item.name,
            "item_name": item.item_name,
            "valuation_rate": valuation_rate,
            "default_uom": stock_uom
        })
    
    return items_data


@frappe.whitelist()
def make_bulk_stock_entry(items, warehouse, type, posting_date=None,
                          target_warehouse=None, department=None, 
                          main_department=None, division=None):
    """Create bulk stock entries for multiple items with individual qty, price, and UOM"""
    
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
    
    # Add department for Issue and Transfer operations
    if department:
        stock_entry.custom_department = department
    
    # Add Main Department for Issue and Transfer operations
    if main_department:
        stock_entry.custom_main_department = main_department
    
    # Add Division for Issue and Transfer operations
    if division:
        stock_entry.custom_division = division
    
    # Add each item to the stock entry with its individual qty, price, and UOM
    for item in items:
        item_code = item.get("item_code")
        qty = flt(item.get("qty"))
        price = flt(item.get("price"))
        uom = item.get("uom")
        
        # Get item details for stock UOM
        item_doc = frappe.get_doc("Item", item_code)
        stock_uom = item_doc.stock_uom
        
        # Get conversion factor if UOM is different from stock UOM
        conversion_factor = 1
        if uom and uom != stock_uom:
            conversion = frappe.db.get_value("UOM Conversion Detail", 
                {"parent": item_code, "uom": uom}, 
                "conversion_factor")
            if conversion:
                conversion_factor = flt(conversion)
        
        # Calculate quantity in stock UOM
        stock_qty = qty * conversion_factor
        
        item_dict = {
            "item_code": item_code,
            "qty": stock_qty,  # Stock quantity
            "basic_rate": price / conversion_factor if conversion_factor else price,  # Rate per stock UOM
            "conversion_factor": conversion_factor,
            "transfer_qty": stock_qty,
            "uom": uom or stock_uom,
            "stock_uom": stock_uom
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
    
    # Submit only Add type – Leave Issue/Transfer draft
    if type == "Add" and get_submit_setting():
        stock_entry.submit()
        frappe.msgprint(_("Stock Entry {0} submitted").format(stock_entry.name))
    else:
        frappe.msgprint(_("Stock Entry {0} is Draft – waiting workflow approval").format(stock_entry.name))

    return {
        "status": "success",
        "stock_entry": stock_entry.name,
        "items_count": len(items),
        "submitted": (type == "Add" and get_submit_setting())
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
