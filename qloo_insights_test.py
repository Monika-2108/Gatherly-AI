import streamlit as st
from qloo_client import search_entities, get_insights

st.title("Gatherly AI — Insights Diagnostic")

if st.button("Test Qloo Insights"):
    try:
        st.write("Step 1: Searching Qloo...")
        matches = search_entities("Taylor Swift", limit=10)
        st.write("Search matches:", len(matches))

        if not matches:
            st.warning("Search returned no entities.")
        else:
            entity = matches[0]
            st.write("Resolved interest:", entity["name"])
            st.write("Entity types:", entity["types"])
            st.write("Entity ID:", entity["entity_id"])

            st.write("Step 2: Requesting place recommendations...")
            result = get_insights(
                entity_ids=[entity["entity_id"]],
                result_type="place",
                city="Bengaluru",
                limit=5,
            )

            st.write("Step 3: Insights response received.")
            st.write("Recommendation count:", len(result["recommendations"]))
            st.json(result["recommendations"])

    except Exception as error:
        st.error(f"{type(error).__name__}: {error}")