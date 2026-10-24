import streamlit as st
from qloo_client import search_entities

st.set_page_config(page_title="Gatherly AI Qloo Test")
st.title("Gatherly AI — Qloo Entity Test")
st.write("Click the button to test a clean entity search.")

if st.button("Test Taylor Swift Search"):
    try:
        with st.spinner("Searching Qloo..."):
            results = search_entities("Taylor Swift", limit=5)

        if results:
            st.success(f"Found {len(results)} entities")
            for item in results:
                st.write(f"**Name:** {item['name']}")
                st.write(f"**Types:** {', '.join(item['types']) or 'Not provided'}")
                st.code(item["entity_id"])
                st.divider()
        else:
            st.warning("No matching entities found. We may need to adjust the response parser.")

    except Exception as error:
        st.error(f"Qloo request failed: {error}")
