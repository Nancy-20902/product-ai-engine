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
        best_price = min(
            (s.price for s in p.sources), default=p.price_inr
        )
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
                "Best Price": f"Rs{best_price:.0f}",
                "Lid": _feature_val(p.lid),
                "Microwave": _feature_val(p.microwave_safe),
                "Dishwasher": _feature_val(p.dishwasher_safe),
                "BPA Free": _feature_val(p.bpa_free),
                "Rating": f"{p.rating}",
                "Available On": sites,
            }
        )
    return pd.DataFrame(rows)