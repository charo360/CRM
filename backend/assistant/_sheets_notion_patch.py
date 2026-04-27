"""Google Sheets and Notion tools — appended to tools.py"""

_SHEETS_KEY = _os.getenv("NEXT_PUBLIC_NANGO_ID_GOOGLE_SHEETS", "google-sheet")
_NOTION_KEY = _os.getenv("NEXT_PUBLIC_NANGO_ID_NOTION", "notion")


# ── Google Sheets tools ───────────────────────────────────────────────────────

@tool(
    name="sheets_list",
    description=(
        "List Google Sheets spreadsheets the user has access to. "
        "Returns file name, spreadsheet ID, and last modified date."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query":       {"type": "string", "description": "Optional search term to filter by name"},
            "max_results": {"type": "integer", "description": "Max files to return (1-50, default 20)"},
        },
    },
)
async def sheets_list(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    limit = min(int(args.get("max_results") or 20), 50)
    q = "mimeType='application/vnd.google-apps.spreadsheet'"
    if args.get("query"):
        q += f" and name contains '{args['query']}'"
    try:
        data = await nango_proxy(
            ctx.business_id, _SHEETS_KEY, "GET",
            "drive/v3/files",
            params={"q": q, "pageSize": limit, "fields": "files(id,name,modifiedTime)"},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    files = data.get("files") or []
    return {
        "spreadsheets": [
            {"spreadsheet_id": f["id"], "name": f["name"], "modified": f.get("modifiedTime")}
            for f in files
        ],
        "total": len(files),
    }


@tool(
    name="sheets_read",
    description=(
        "Read data from a Google Sheets spreadsheet. "
        "Provide spreadsheet_id (from sheets_list) and optionally a range like 'Sheet1!A1:D20'. "
        "Returns rows as arrays of values."
    ),
    parameters={
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string", "description": "Google Sheets spreadsheet ID"},
            "range":          {"type": "string", "description": "A1 notation range e.g. 'Sheet1!A1:E50'. Default: first sheet all data."},
        },
        "required": ["spreadsheet_id"],
    },
)
async def sheets_read(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    sid = (args.get("spreadsheet_id") or "").strip()
    if not sid:
        return {"error": "spreadsheet_id is required"}
    rng = (args.get("range") or "").strip() or "A1:Z1000"
    try:
        data = await nango_proxy(
            ctx.business_id, _SHEETS_KEY, "GET",
            f"sheets/v4/spreadsheets/{sid}/values/{rng}",
        )
    except RuntimeError as e:
        return {"error": str(e)}
    rows = data.get("values") or []
    return {
        "spreadsheet_id": sid,
        "range": data.get("range", rng),
        "row_count": len(rows),
        "rows": rows[:500],
    }


@tool(
    name="sheets_append",
    description=(
        "Append rows to a Google Sheets spreadsheet. "
        "Each row is an array of values. Adds after the last row of data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string", "description": "Spreadsheet ID"},
            "sheet_name":     {"type": "string", "description": "Sheet/tab name. Default: Sheet1"},
            "rows":           {
                "type": "array",
                "items": {"type": "array"},
                "description": "Rows to append, e.g. [[\"John\", \"KES 5000\", \"2024-01-01\"]]",
            },
        },
        "required": ["spreadsheet_id", "rows"],
    },
    destructive=True,
)
async def sheets_append(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    sid = (args.get("spreadsheet_id") or "").strip()
    rows = args.get("rows") or []
    if not sid or not rows:
        return {"error": "spreadsheet_id and rows are required"}
    sheet = (args.get("sheet_name") or "Sheet1").strip()
    try:
        result = await nango_proxy(
            ctx.business_id, _SHEETS_KEY, "POST",
            f"sheets/v4/spreadsheets/{sid}/values/{sheet}:append",
            params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
            json={"values": rows},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    updates = result.get("updates") or {}
    return {
        "status": "appended",
        "rows_added": updates.get("updatedRows", len(rows)),
        "range": updates.get("updatedRange"),
    }


@tool(
    name="sheets_update",
    description=(
        "Update specific cells in a Google Sheets spreadsheet. "
        "Provide the A1 range and the values to write."
    ),
    parameters={
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string"},
            "range":          {"type": "string", "description": "A1 notation range e.g. 'Sheet1!B2:D5'"},
            "rows":           {
                "type": "array",
                "items": {"type": "array"},
                "description": "Values to write into the range",
            },
        },
        "required": ["spreadsheet_id", "range", "rows"],
    },
    destructive=True,
)
async def sheets_update(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    sid = (args.get("spreadsheet_id") or "").strip()
    rng = (args.get("range") or "").strip()
    rows = args.get("rows") or []
    if not sid or not rng or not rows:
        return {"error": "spreadsheet_id, range, and rows are required"}
    try:
        result = await nango_proxy(
            ctx.business_id, _SHEETS_KEY, "PUT",
            f"sheets/v4/spreadsheets/{sid}/values/{rng}",
            params={"valueInputOption": "USER_ENTERED"},
            json={"range": rng, "values": rows},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    return {
        "status": "updated",
        "cells_updated": result.get("updatedCells"),
        "range": result.get("updatedRange"),
    }


@tool(
    name="sheets_create",
    description="Create a new Google Sheets spreadsheet with an optional title.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Spreadsheet title"},
        },
        "required": ["title"],
    },
    destructive=True,
)
async def sheets_create(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    title = (args.get("title") or "Untitled").strip()
    try:
        result = await nango_proxy(
            ctx.business_id, _SHEETS_KEY, "POST",
            "sheets/v4/spreadsheets",
            json={"properties": {"title": title}},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    return {
        "status": "created",
        "spreadsheet_id": result.get("spreadsheetId"),
        "title": result.get("properties", {}).get("title"),
        "url": result.get("spreadsheetUrl"),
    }


# ── Notion tools ──────────────────────────────────────────────────────────────

@tool(
    name="notion_search",
    description=(
        "Search Notion pages and databases. Returns titles, IDs, and types. "
        "Use to find a page or database before reading or writing."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query":    {"type": "string", "description": "Search term"},
            "filter":   {"type": "string", "description": "Filter by type: page or database. Default: both."},
            "max_results": {"type": "integer", "description": "Max results (1-20, default 10)"},
        },
    },
)
async def notion_search(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    limit = min(int(args.get("max_results") or 10), 20)
    body: Dict[str, Any] = {"page_size": limit}
    if args.get("query"):
        body["query"] = args["query"]
    if args.get("filter") in ("page", "database"):
        body["filter"] = {"value": args["filter"], "property": "object"}
    try:
        data = await nango_proxy(ctx.business_id, _NOTION_KEY, "POST", "v1/search", json=body)
    except RuntimeError as e:
        return {"error": str(e)}
    results = []
    for r in (data.get("results") or []):
        obj_type = r.get("object")
        title = ""
        if obj_type == "page":
            props = r.get("properties") or {}
            title_prop = props.get("title") or props.get("Name") or {}
            title_list = title_prop.get("title") or []
            title = "".join(t.get("plain_text", "") for t in title_list) if title_list else r.get("url", "")
        elif obj_type == "database":
            title_list = r.get("title") or []
            title = "".join(t.get("plain_text", "") for t in title_list)
        results.append({
            "id":       r["id"],
            "type":     obj_type,
            "title":    title or "(untitled)",
            "url":      r.get("url"),
            "created":  r.get("created_time"),
            "edited":   r.get("last_edited_time"),
        })
    return {"results": results, "total": len(results)}


@tool(
    name="notion_read_page",
    description=(
        "Read the content blocks of a Notion page by page_id. "
        "Returns the page title and all text blocks."
    ),
    parameters={
        "type": "object",
        "properties": {
            "page_id": {"type": "string", "description": "Notion page ID (from notion_search)"},
        },
        "required": ["page_id"],
    },
)
async def notion_read_page(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    page_id = (args.get("page_id") or "").strip().replace("-", "")
    if not page_id:
        return {"error": "page_id is required"}
    try:
        page = await nango_proxy(ctx.business_id, _NOTION_KEY, "GET", f"v1/pages/{page_id}")
        blocks_data = await nango_proxy(ctx.business_id, _NOTION_KEY, "GET", f"v1/blocks/{page_id}/children", params={"page_size": 100})
    except RuntimeError as e:
        return {"error": str(e)}

    # Extract title
    props = page.get("properties") or {}
    title_prop = props.get("title") or props.get("Name") or {}
    title_list = title_prop.get("title") or []
    title = "".join(t.get("plain_text", "") for t in title_list) or "(untitled)"

    # Extract block text
    blocks = []
    for b in (blocks_data.get("results") or []):
        btype = b.get("type", "")
        block_content = b.get(btype) or {}
        rich = block_content.get("rich_text") or []
        text = "".join(t.get("plain_text", "") for t in rich)
        if text:
            blocks.append({"type": btype, "text": _email_trunc(text, 500)})

    return {"page_id": page_id, "title": title, "blocks": blocks, "block_count": len(blocks)}


@tool(
    name="notion_create_page",
    description=(
        "Create a new Notion page inside a parent page or database. "
        "Provide parent_id (page or database ID) and the page title. "
        "Optionally provide content as plain text."
    ),
    parameters={
        "type": "object",
        "properties": {
            "parent_id":   {"type": "string", "description": "Parent page or database ID"},
            "parent_type": {"type": "string", "description": "page or database (default: page)"},
            "title":       {"type": "string", "description": "Page title"},
            "content":     {"type": "string", "description": "Optional plain text body content"},
        },
        "required": ["parent_id", "title"],
    },
    destructive=True,
)
async def notion_create_page(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    parent_id   = (args.get("parent_id") or "").strip().replace("-", "")
    parent_type = (args.get("parent_type") or "page").strip()
    title       = (args.get("title") or "").strip()
    content     = (args.get("content") or "").strip()
    if not parent_id or not title:
        return {"error": "parent_id and title are required"}

    parent_key = "database_id" if parent_type == "database" else "page_id"
    payload: Dict[str, Any] = {
        "parent": {parent_key: parent_id},
        "properties": {
            "title": {"title": [{"text": {"content": title}}]}
        },
    }
    if content:
        payload["children"] = [{
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": content[:2000]}}]},
        }]
    try:
        result = await nango_proxy(ctx.business_id, _NOTION_KEY, "POST", "v1/pages", json=payload)
    except RuntimeError as e:
        return {"error": str(e)}
    return {
        "status": "created",
        "page_id": result.get("id"),
        "url": result.get("url"),
        "title": title,
    }


@tool(
    name="notion_append_blocks",
    description=(
        "Append text content to an existing Notion page. "
        "Content is added as paragraph blocks at the end of the page."
    ),
    parameters={
        "type": "object",
        "properties": {
            "page_id": {"type": "string", "description": "Notion page ID"},
            "content": {"type": "string", "description": "Text to append"},
        },
        "required": ["page_id", "content"],
    },
    destructive=True,
)
async def notion_append_blocks(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    page_id = (args.get("page_id") or "").strip().replace("-", "")
    content = (args.get("content") or "").strip()
    if not page_id or not content:
        return {"error": "page_id and content are required"}
    # Split into 2000-char chunks (Notion block limit)
    chunks = [content[i:i+2000] for i in range(0, len(content), 2000)]
    children = [
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": c}}]}}
        for c in chunks
    ]
    try:
        await nango_proxy(
            ctx.business_id, _NOTION_KEY, "PATCH",
            f"v1/blocks/{page_id}/children",
            json={"children": children},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    return {"status": "appended", "blocks_added": len(children)}


@tool(
    name="notion_query_database",
    description=(
        "Query a Notion database to retrieve its rows/entries. "
        "Returns up to 50 rows with all property values."
    ),
    parameters={
        "type": "object",
        "properties": {
            "database_id": {"type": "string", "description": "Notion database ID (from notion_search with filter=database)"},
            "max_results": {"type": "integer", "description": "Max rows to return (1-50, default 20)"},
        },
        "required": ["database_id"],
    },
)
async def notion_query_database(ctx: ToolContext, args: Dict[str, Any]):
    from .nango import nango_proxy
    db_id = (args.get("database_id") or "").strip().replace("-", "")
    limit = min(int(args.get("max_results") or 20), 50)
    if not db_id:
        return {"error": "database_id is required"}
    try:
        data = await nango_proxy(
            ctx.business_id, _NOTION_KEY, "POST",
            f"v1/databases/{db_id}/query",
            json={"page_size": limit},
        )
    except RuntimeError as e:
        return {"error": str(e)}
    rows = []
    for page in (data.get("results") or []):
        row: Dict[str, Any] = {"page_id": page["id"], "url": page.get("url")}
        for prop_name, prop_val in (page.get("properties") or {}).items():
            ptype = prop_val.get("type", "")
            val = prop_val.get(ptype)
            if ptype == "title":
                row[prop_name] = "".join(t.get("plain_text", "") for t in (val or []))
            elif ptype in ("rich_text", "email", "phone_number", "url"):
                if isinstance(val, list):
                    row[prop_name] = "".join(t.get("plain_text", "") for t in val)
                else:
                    row[prop_name] = val or ""
            elif ptype in ("number", "checkbox"):
                row[prop_name] = val
            elif ptype == "select":
                row[prop_name] = (val or {}).get("name")
            elif ptype == "multi_select":
                row[prop_name] = [s.get("name") for s in (val or [])]
            elif ptype == "date":
                row[prop_name] = (val or {}).get("start")
            else:
                row[prop_name] = str(val)[:100] if val else None
        rows.append(row)
    return {"database_id": db_id, "rows": rows, "total": len(rows)}
