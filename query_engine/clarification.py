"""Smart defaults and clarification suggestion engine."""

from query_engine.schemas import ParsedQuery


def apply_sidebar_overrides(
    parsed: ParsedQuery, filters: dict
) -> ParsedQuery:
    """Merge Streamlit sidebar filter values into the parsed query."""

    if filters.get("lid"):
        parsed.lid_required = True

    feature_toggles = {
        "microwave_safe": "microwave safe",
        "dishwasher_safe": "dishwasher safe",
        "bpa_free": "BPA free",
        "leakproof": "leakproof",
        "insulated": "insulated",
    }
    for key, feature in feature_toggles.items():
        if filters.get(key) and feature not in parsed.features:
            parsed.features.append(feature)

    if filters.get("price_min") is not None:
        val = filters["price_min"]
        if val > 0:
            # Only narrow (raise) the floor, never lower it
            if parsed.price_min is None or val > parsed.price_min:
                parsed.price_min = val

    if filters.get("price_max") is not None:
        val = filters["price_max"]
        if val < 50000:
            # Only narrow (lower) the ceiling, never raise it
            if parsed.price_max is None or val < parsed.price_max:
                parsed.price_max = val

    if filters.get("material") and filters["material"] != "Any":
        parsed.material = filters["material"].lower()

    if filters.get("brand") and filters["brand"] != "Any":
        parsed.brand = filters["brand"]

    if filters.get("capacity_ml"):
        parsed.capacity_ml = filters["capacity_ml"]

    return parsed


def get_clarification_messages(parsed: ParsedQuery) -> list[str]:
    """Generate user-friendly clarification messages."""
    messages = []
    for field in parsed.clarification_needed:
        field_lower = field.lower()
        if "lid" in field_lower:
            if not parsed.lid_required:
                messages.append(
                    "We assumed you want a lid. "
                    "Uncheck in sidebar if not needed."
                )
        elif "microwave" in field_lower:
            messages.append(
                "We added microwave-safe as a preference "
                "for lunch boxes."
            )
        elif "capacity" in field_lower:
            if not parsed.capacity_ml:
                messages.append(
                    "No capacity specified. "
                    "Use the sidebar to filter by size."
                )
        elif "llm" in field_lower:
            messages.append(
                "AI parsing unavailable. "
                "Showing basic keyword results."
            )
        else:
            messages.append(
                f"You didn't specify: {field}. "
                "Use sidebar to refine."
            )
    return messages