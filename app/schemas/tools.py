TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "reverse_geocode",
            "description": "Convert GPS latitude/longitude to a human-readable street address.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude":  {"type": "number", "description": "GPS latitude"},
                    "longitude": {"type": "number", "description": "GPS longitude"},
                },
                "required": ["latitude", "longitude"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_civic_report",
            "description": "Send a formatted civic issue report email to the municipal department.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmed": {
                        "type": "boolean",
                        "description": "Set to true to confirm you want to send the report.",
                    }
                },
                "required": ["confirmed"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_to_official_ledger",
            "description": "Write the completed action to the official PostgreSQL ledger.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmed": {
                        "type": "boolean",
                        "description": "Set to true to confirm logging.",
                    }
                },
                "required": ["confirmed"],
            },
        },
    },
]