"""Registry of the sketch tools. The right-click menu is built from it, so a new tool shows up there
as soon as it is listed here (a test fails if a tool the viewport handles is missing)."""

# the rectangle kinds behind the one ribbon button: tool -> (label, icon)
RECT_TOOLS = {
    "RECT": ("2-Point\nRect (R)", "🔲"),
    "CENTER_RECT": ("Center\nRect", "⛶"),
    "ROUNDED_RECT": ("Rounded\nRect", "▢"),
    "CENTER_ROUNDED_RECT": ("Center\nRounded", "▣"),
}

# (tool, label, menu group, submenu or None). Order is the menu order.
SKETCH_TOOLS = [
    ("LINE", "Line  (L)", "Draw", None),
    *[(t, label.replace("\n", " "), "Draw", "Rectangle") for t, (label, _i) in RECT_TOOLS.items()],
    ("CIRCLE", "Circle  (C)", "Draw", None),
    ("SMART_CIRCLE", "Smart Circle  (Shift+C)", "Draw", None),
    ("ARC", "Arc", "Draw", None),
    ("SLOT", "Slot", "Draw", None),
    ("POLYGON", "Polygon", "Draw", None),
    ("TEXT", "Text", "Draw", None),
    ("TRIM", "Trim", "Modify", None),
    ("OFFSET", "Offset  (O)", "Modify", None),
    ("MIRROR", "Mirror", "Modify", None),
    ("FILLET", "Fillet  (F)", "Modify", None),
    ("MOVE", "Move", "Modify", None),
    ("DIMENSION", "Dimension", "Dimension", None),
]
# tool names the viewport uses that are not menu entries
NON_MENU_TOOLS = {"NONE"}
