"""Streamlit UI for the AI Product Comparison and Recommendation System."""

import sys
import os
import logging

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd

from utils.helpers import setup_logging
from query_engine.parser import parse_query
from query_engine.schemas import ParsedQuery
from kb.kb_manager import add_products
from crawler.crawler import crawl_for_products
from matching.deduplicator import deduplicate
from comparison.compare import build_comparison_table
from recommendation.ranker import rank_products

setup_logging()
logger = logging.getLogger(__name__)

# ── Page Config ──
st.set_page_config(
    page_title="Smart Kitchen Storage Finder",
    page_icon="",
    layout="wide",
)

st.title("Smart Kitchen Storage Finder")
st.caption(
    "AI-powered product search, comparison, and recommendation "
    "for kitchen storage products"
)

# ── Search Box ──
user_query = st.text_input(
    "What are you looking for?",
    placeholder=(
        "e.g., best glass bowl under 500, "
        "microwave safe lunch box, "
        "borosil vs milton"
    ),
)


def _feature_display(val: bool, field_name: str = "") -> str:
    """Return 'Yes' if True, 'N/A' if False (unknown/not found)."""
    return "Yes" if val else "N/A"


# ── Main Search Flow ──
if user_query:
    # Phase 1: Query Understanding
    with st.spinner("Understanding your query..."):
        parsed = parse_query(user_query)

    # Domain check
    if not parsed.is_domain_relevant:
        msg = (
            parsed.clarification_needed[0]
            if parsed.clarification_needed
            else (
                "This system handles kitchen and home products. "
                "Try searching for containers, bowls, glasses, "
                "cookware, cutlery, etc."
            )
        )
        st.error(msg)
        st.stop()

    # Check for missing essential fields and prompt user
    missing_fields = []
    if not parsed.material:
        missing_fields.append("material")
    if not parsed.capacity_ml:
        missing_fields.append("capacity")
    if parsed.price_max is None and parsed.price_min is None:
        missing_fields.append("price")

    if missing_fields:
        st.info(
            "Some details were not specified. "
            "You can fill them below or leave as 'Any' to see all results."
        )
        with st.form("missing_fields_form"):
            col_fields = st.columns(len(missing_fields))
            field_vals = {}
            for idx, field in enumerate(missing_fields):
                with col_fields[idx]:
                    if field == "material":
                        field_vals["material"] = st.selectbox(
                            "Material",
                            ["Any", "Glass", "Borosilicate Glass",
                             "Plastic", "Stainless Steel"],
                        )
                    elif field == "capacity":
                        field_vals["capacity"] = st.selectbox(
                            "Capacity",
                            ["Any", "250ml", "500ml", "750ml",
                             "1L", "1.5L", "2L"],
                        )
                    elif field == "price":
                        field_vals["price"] = st.selectbox(
                            "Price Range",
                            ["Any", "Under 300", "Under 500",
                             "Under 1000", "Under 2000", "Under 5000"],
                        )

            submitted = st.form_submit_button("Search")
            if submitted:
                if field_vals.get("material") and field_vals["material"] != "Any":
                    parsed.material = field_vals["material"].lower()
                if field_vals.get("capacity") and field_vals["capacity"] != "Any":
                    cap_map = {"250ml": 250, "500ml": 500, "750ml": 750,
                               "1L": 1000, "1.5L": 1500, "2L": 2000}
                    parsed.capacity_ml = cap_map.get(field_vals["capacity"])
                if field_vals.get("price") and field_vals["price"] != "Any":
                    import re as _re
                    pm = _re.search(r'\d+', field_vals["price"])
                    if pm:
                        parsed.price_max = float(pm.group())
            elif missing_fields:
                st.stop()

    # Show parsed understanding
    with st.expander("How we understood your query", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Intent:** {parsed.intent.value}")
            st.markdown(
                f"**Product Type:** {parsed.product_type or 'Any'}"
            )
            st.markdown(
                f"**Material:** {parsed.material or 'Any'}"
            )
            brands_display = parsed.brand or "Any"
            if parsed.compare_brands:
                brands_display = ", ".join(parsed.compare_brands)
            st.markdown(f"**Brand:** {brands_display}")
        with col2:
            price_display = (
                f"Rs{parsed.price_min or 0:.0f} - "
                f"Rs{parsed.price_max or 'No limit'}"
            )
            st.markdown(f"**Price Range:** {price_display}")
            cap_display = (
                f"{parsed.capacity_ml}ml"
                if parsed.capacity_ml
                else "Any"
            )
            st.markdown(f"**Capacity:** {cap_display}")
            feat_display = (
                ", ".join(parsed.features)
                if parsed.features
                else "None specified"
            )
            st.markdown(f"**Features:** {feat_display}")
            st.markdown(
                f"**Confidence:** {parsed.confidence:.0%}"
            )

    # Phase 2: Live crawl — always fetch fresh results
    crawl_reports = []
    crawled_products = []

    with st.spinner(
        "Fetching latest products from the web... "
        "This may take a moment."
    ):
        crawled_products, crawl_reports = crawl_for_products(parsed)

        if crawled_products:
            crawled_products = deduplicate(crawled_products)

    products = list(crawled_products)

    # Re-filter combined results against the query
    filtered = []
    for p in products:
        passes = True
        if (
            parsed.price_max is not None
            and p.price_inr > parsed.price_max
        ):
            passes = False
        if (
            parsed.price_min is not None
            and p.price_inr < parsed.price_min
        ):
            passes = False
        if parsed.material and p.material:
            if parsed.material.lower() not in p.material.lower():
                passes = False
        # Multi-brand filter: keep products from any of the compare_brands
        if parsed.compare_brands and len(parsed.compare_brands) > 1:
            if p.brand.lower() not in [
                b.lower() for b in parsed.compare_brands
            ]:
                passes = False
        elif parsed.brand:
            if parsed.brand.lower() != p.brand.lower():
                passes = False
        if passes:
            filtered.append(p)

    products = filtered if filtered else products

    if not products:
        st.warning(
            "No products found matching your criteria. "
            "Try broadening your search."
        )
        st.stop()

    # Show sources info (positive message)
    success_sources = [
        r.source for r in crawl_reports if r.success
    ]
    if success_sources:
        sources_str = ", ".join(success_sources)
        st.success(f"Results fetched from: {sources_str}")

    # Comparison Table
    st.subheader(
        f"Product Comparison ({len(products)} products found)"
    )
    comparison_df = build_comparison_table(products)
    st.dataframe(
        comparison_df, width="stretch", hide_index=True
    )

    # Recommendations
    st.subheader("Recommendations")

    recommendations = rank_products(
        products, parsed, original_query=user_query
    )

    for i, rec in enumerate(recommendations[:5]):
        p = rec.product
        rank = f"#{i + 1}"
        display_label = f"{rank} — {rec.label}" if i == 0 and rec.label else rank

        with st.container():
            col1, col2, col3 = st.columns([1, 2, 1])

            with col1:
                st.markdown(f"### {display_label}")
                st.markdown(f"**Score: {rec.score}/100**")

            with col2:
                st.markdown(f"**{p.product_name}**")
                st.markdown(
                    f"Brand: {p.brand} | "
                    f"Material: {p.material or 'N/A'}"
                )
                cap_text = (
                    f"{p.capacity_ml}ml" if p.capacity_ml else "N/A"
                )
                st.markdown(
                    f"Capacity: {cap_text} | "
                    f"Lid: {_feature_display(p.lid)}"
                )
                if p.features:
                    features_str = ", ".join(p.features[:4])
                    st.markdown(f"Features: {features_str}")

            with col3:
                st.markdown(f"### Rs{p.price_inr:.0f}")
                st.markdown(f"Rating: {p.rating}/5" if p.rating is not None else "Rating: N/A")
                if p.sources:
                    best = min(p.sources, key=lambda s: s.price)
                    st.markdown(
                        f"Best: Rs{best.price:.0f} on {best.site}"
                    )

            # Show reasons
            if rec.reasons:
                for reason in rec.reasons:
                    st.markdown(f"- {reason}")

            # Show caveat
            if rec.caveat:
                st.caption(f"Note: {rec.caveat}")

            st.divider()

    # Price comparison across sites (with clickable URLs)
    st.subheader("Price Comparison Across Sites")
    price_data = []
    for p in products:
        for source in p.sources:
            url = source.url
            if url and url.startswith("http"):
                link = f"[View Product]({url})"
            else:
                link = "N/A"
            price_data.append(
                {
                    "Product": p.product_name[:40],
                    "Brand": p.brand,
                    "Site": source.site,
                    "Price (Rs)": int(source.price),
                    "Link": link,
                }
            )

    if price_data:
        price_df = pd.DataFrame(price_data)
        st.markdown(
            price_df.to_markdown(index=False),
            unsafe_allow_html=True,
        )

    # Phase 6: Save to KB in the background (after results are shown)
    if crawled_products:
        add_products(crawled_products)