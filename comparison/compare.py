"""Comparison table builder."""

import pandas as pd
from query_engine.schemas import Product


def _feature_val(val: bool) -> str:
    """Return 'Yes' if True, 'N/A' if False (not confirmed)."""
    return "Yes" if val else "N/A"


def build_comparison_table(products: list[Product]) -> pd.DataFrame:
    """Build a side-by-side comparison DataFrame."""
    rows = []
    for p in products:
        sites = ", ".join(s.site for s in p.sources)
        rows.append(
            {
                "Product": p.product_name[:50],
                "Brand": p.brand,
                "Material": (p.material or "N/A").title(),
                "Capacity": (
                    f"{p.capacity_ml}ml" if p.capacity_ml else "N/A"
                ),
                "Price": f"Rs{p.price_inr:.0f}",
                "Lid": _feature_val(p.lid),
                "Microwave": _feature_val(p.microwave_safe),
                "Dishwasher": _feature_val(p.dishwasher_safe),
                "BPA Free": _feature_val(p.bpa_free),
                "Rating": f"{p.rating}/5" if p.rating is not None else "N/A",
                "Available On": sites,
            }
        )
    return pd.DataFrame(rows)