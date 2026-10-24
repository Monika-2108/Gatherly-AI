import streamlit as st
import json
import re
from datetime import datetime

from qloo_client import search_entities, search_tags, get_insights

st.set_page_config(
    page_title="Gatherly AI",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

MAX_SEARCH_RESULTS = 8
MAX_INSIGHT_SIGNALS = 8

# -------------------- ORIGINAL DARK DASHBOARD THEME --------------------

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

:root {
    --bg: #0b0b12;
    --panel: #12121d;
    --border: #29283b;
    --text: #f5f3ff;
    --muted: #a5a1bd;
    --pink: #ef79d5;
    --purple: #9a83ff;
}

.stApp {
    background: var(--bg);
    color: var(--text);
    font-family: 'DM Sans', sans-serif;
}

h1, h2, h3 {
    font-family: 'Space Grotesk', sans-serif !important;
    color: var(--text) !important;
}

section[data-testid="stSidebar"] {
    background: #12121d;
    border-right: 1px solid #29283b;
}

section[data-testid="stSidebar"] * {
    color: #f5f3ff;
}

div[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: #29283b !important;
    border-radius: 16px !important;
}

.hero {
    background: linear-gradient(120deg, #211638 0%, #151b35 55%, #30203b 100%);
    padding: 30px;
    border: 1px solid #39304e;
    border-radius: 22px;
    margin-bottom: 24px;
}

.hero h1 {
    font-size: 42px;
    margin: 0;
    background: linear-gradient(90deg, #ffffff, #ef9ee0, #b4a5ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.hero p, .muted {
    color: #bcb6d4;
}

.eyebrow {
    color: #e7a2e2;
    text-transform: uppercase;
    letter-spacing: 2px;
    font-size: 11px;
    font-weight: 700;
}

.metric {
    background: #141421;
    border: 1px solid #302c45;
    padding: 18px;
    border-radius: 15px;
    min-height: 95px;
}

.metric-label {
    color: #aaa4c4;
    font-size: 12px;
}

.metric-value {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 25px;
    font-weight: 700;
    margin-top: 5px;
}

.venue {
    background: linear-gradient(145deg, #171625, #11111b);
    border: 1px solid #302b45;
    border-radius: 15px;
    padding: 18px;
    margin-bottom: 12px;
}

.pill {
    display: inline-block;
    padding: 4px 9px;
    border-radius: 20px;
    background: #302044;
    color: #efb5e8;
    font-size: 11px;
    margin: 3px 3px 3px 0;
}

div.stButton > button[kind="primary"] {
    background: linear-gradient(100deg, #9469f7, #e36bc5);
    border: none;
    color: white;
    border-radius: 10px;
    font-weight: 700;
    min-height: 43px;
}

div.stButton > button {
    border-radius: 10px;
}

input, textarea {
    border-radius: 10px !important;
}

[data-testid="stMetricValue"] {
    color: #e8a2e6;
}

hr {
    border-color: #29283b;
}

#MainMenu, footer {
    visibility: hidden;
}
</style>
""", unsafe_allow_html=True)


# -------------------- SESSION STATE --------------------

defaults = {
    "page": "Plan an Event",
    "events": [],
    "candidates": [],
    "research_logs": [],
    "research_summary": {},
    "last_plan": None,
    "research_error": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# -------------------- DATA HELPERS --------------------

def extract_results(response):
    """Normalize common API response structures into a list."""
    if isinstance(response, list):
        return response

    if not isinstance(response, dict):
        return []

    for key in (
        "recommendations", "results", "entities",
        "places", "items", "tags",
    ):
        value = response.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            found = extract_results(value)
            if found:
                return found

    for key in ("response", "data", "result"):
        value = response.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            found = extract_results(value)
            if found:
                return found

    return []


def entity_id(item):
    if not isinstance(item, dict):
        return None

    value = (
        item.get("entity_id")
        or item.get("id")
        or item.get("entity", {}).get("entity_id")
        if isinstance(item.get("entity"), dict)
        else item.get("entity_id") or item.get("id")
    )

    return str(value) if value else None


def item_name(item):
    if not isinstance(item, dict):
        return str(item)

    entity = item.get("entity")
    if isinstance(entity, dict):
        item = {**entity, **item}

    return (
        item.get("name")
        or item.get("title")
        or item.get("display_name")
        or "Unnamed result"
    )


def item_description(item):
    if not isinstance(item, dict):
        return ""

    parts = []

    for key in ("description", "short_description", "address", "location"):
        value = item.get(key)

        if isinstance(value, str) and value.strip():
            parts.append(value.strip())

    properties = item.get("properties")
    if isinstance(properties, dict):
        for key in ("address", "description", "city"):
            value = properties.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())

    return " · ".join(dict.fromkeys(parts))[:450]


def make_search_queries(event_type, city, interests):
    queries = [
        f"{event_type} venues in {city}",
        f"popular places for {event_type} in {city}",
        f"{event_type} locations {city}",
    ]

    if interests.strip():
        queries.append(f"{interests.strip()} places in {city}")

    return list(dict.fromkeys(queries))


def add_candidate(candidates, item, source):
    if not isinstance(item, dict):
        return

    name = item_name(item).strip()
    if not name or name == "Unnamed result":
        return

    identifier = entity_id(item)
    key = identifier or name.casefold()

    for candidate in candidates:
        existing_key = candidate.get("id") or candidate["name"].casefold()

        if existing_key == key:
            candidate["sources"].add(source)
            if not candidate.get("description"):
                candidate["description"] = item_description(item)
            return

    candidates.append({
        "id": identifier,
        "name": name,
        "description": item_description(item),
        "sources": {source},
        "raw": item,
    })


# -------------------- QLOO RESEARCH --------------------

def research_event(city, event_type, interests, limit=MAX_SEARCH_RESULTS):
    candidates = []
    logs = []
    entity_ids = []
    tag_ids = []
    attempted = 0
    successful = 0

    queries = make_search_queries(event_type, city, interests)

    logs.append(f"Started research for {event_type} in {city}.")

    for query in queries:
        attempted += 1
        logs.append(f"Searching entities: {query}")

        try:
            response = search_entities(query, limit=limit)
            results = extract_results(response)
            successful += 1

            logs.append(f"Received {len(results)} entity results.")

            for item in results:
                if not isinstance(item, dict):
                    continue

                add_candidate(candidates, item, "Entity Search")
                identifier = entity_id(item)

                if identifier and identifier not in entity_ids:
                    entity_ids.append(identifier)

        except Exception as error:
            logs.append(f"Entity search error: {str(error)[:250]}")

    if interests.strip():
        logs.append(f"Resolving interest tags: {interests}")

        try:
            response = search_tags(interests.strip(), limit=5)
            tags = extract_results(response)

            for tag in tags:
                if not isinstance(tag, dict):
                    continue

                identifier = (
                    tag.get("tag_id")
                    or tag.get("entity_id")
                    or tag.get("id")
                )

                if identifier and str(identifier) not in tag_ids:
                    tag_ids.append(str(identifier))

            logs.append(f"Resolved {len(tag_ids)} interest tags.")

        except Exception as error:
            logs.append(f"Tag search error: {str(error)[:250]}")

    if entity_ids or tag_ids:
        logs.append("Requesting Qloo Insights.")

        try:
            response = get_insights(
                entity_ids=entity_ids[:MAX_INSIGHT_SIGNALS] or None,
                result_type="place",
                city=city,
                limit=limit,
                tag_ids=tag_ids[:MAX_INSIGHT_SIGNALS] or None,
            )

            recommendations = extract_results(response)
            logs.append(
                f"Insights returned {len(recommendations)} records."
            )

            for item in recommendations:
                add_candidate(candidates, item, "Qloo Insights")

        except Exception as error:
            logs.append(f"Insights error: {str(error)[:250]}")

    else:
        logs.append(
            "Insights skipped: no usable entity or tag IDs were found."
        )

    logs.append(f"Research finished with {len(candidates)} unique results.")

    summary = {
        "queries_attempted": attempted,
        "successful_searches": successful,
        "entity_signals": len(entity_ids),
        "tag_signals": len(tag_ids),
        "candidate_count": len(candidates),
    }

    return candidates, logs, summary


def rank_candidates(candidates, event_type, interests):
    terms = [
        word.casefold()
        for word in re.findall(r"[a-zA-Z0-9]+", f"{event_type} {interests}")
        if len(word) > 2
    ]

    ranked = []

    for candidate in candidates:
        text = (
            candidate["name"] + " " + candidate.get("description", "")
        ).casefold()

        score = 0
        matched = []

        for term in terms:
            if term in text:
                score += 2
                matched.append(term)

        if "Qloo Insights" in candidate["sources"]:
            score += 3

        if candidate.get("description"):
            score += 1

        ranked.append({
            **candidate,
            "score": score,
            "matched": list(dict.fromkeys(matched)),
        })

    return sorted(
        ranked,
        key=lambda item: (item["score"], item["name"].casefold()),
        reverse=True,
    )


# -------------------- SIDEBAR --------------------

with st.sidebar:
    st.markdown("## ✦ Gatherly AI")
    st.caption("Your intelligent event companion")
    st.divider()

    pages = ["Plan an Event", "Research Activity", "My Events"]

    for page in pages:
        if st.button(
            ("✦  " if st.session_state.page == page else "　") + page,
            key=f"nav_{page}",
            use_container_width=True,
            type="primary" if st.session_state.page == page else "secondary",
        ):
            st.session_state.page = page
            st.rerun()

    st.divider()
    st.markdown("**Powered by Qloo**")
    st.caption("Cultural intelligence for event discovery")
    st.caption("Research results depend on API access and returned data.")


# -------------------- HERO --------------------

def render_hero(title, subtitle):
    st.markdown(
        f"""
        <div class="hero">
            <div class="eyebrow">✦ GATHERLY INTELLIGENCE</div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -------------------- PAGE: PLAN EVENT --------------------

if st.session_state.page == "Plan an Event":

    render_hero(
        "Make moments memorable.",
        "Plan smarter events with cultural intelligence, relevant discoveries, and a clear budget.",
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            f'<div class="metric"><div class="metric-label">SAVED EVENTS</div>'
            f'<div class="metric-value">{len(st.session_state.events)}</div></div>',
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f'<div class="metric"><div class="metric-label">RESEARCH RESULTS</div>'
            f'<div class="metric-value">{len(st.session_state.candidates)}</div></div>',
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            '<div class="metric"><div class="metric-label">INTELLIGENCE</div>'
            '<div class="metric-value">Qloo AI</div></div>',
            unsafe_allow_html=True,
        )

    st.write("")

    left, right = st.columns([1.15, 0.85], gap="large")

    with left:
        with st.container(border=True):
            st.subheader("✦ Design your event")
            st.caption("Tell Gatherly what you're planning.")

            with st.form("event_form"):
                event_name = st.text_input(
                    "Event name",
                    placeholder="e.g. Moonlight Celebration",
                )

                c1, c2 = st.columns(2)

                with c1:
                    city = st.text_input(
                        "City",
                        value="Bengaluru",
                    )

                with c2:
                    event_type = st.selectbox(
                        "Event type",
                        [
                            "Birthday Party",
                            "Wedding",
                            "Corporate Event",
                            "College Fest",
                            "Music Event",
                            "Networking Event",
                            "Private Party",
                            "Workshop",
                            "Family Gathering",
                            "Other",
                        ],
                    )

                interests = st.text_input(
                    "Interests and vibe",
                    placeholder="e.g. music, art, food, luxury, nature",
                )

                c3, c4 = st.columns(2)

                with c3:
                    guests = st.number_input(
                        "Number of guests",
                        min_value=1,
                        max_value=10000,
                        value=50,
                    )

                with c4:
                    budget = st.number_input(
                        "Total budget (₹)",
                        min_value=0,
                        value=25000,
                        step=1000,
                    )

                event_date = st.date_input(
                    "Event date",
                    min_value=datetime.today().date(),
                )

                submitted = st.form_submit_button(
                    "✦ Research my event",
                    type="primary",
                    use_container_width=True,
                )

        if submitted:
            if not city.strip():
                st.error("Please enter a city.")
            else:
                plan = {
                    "name": event_name.strip() or f"{event_type} in {city}",
                    "city": city.strip(),
                    "type": event_type,
                    "interests": interests.strip(),
                    "guests": int(guests),
                    "budget": int(budget),
                    "date": event_date.isoformat(),
                }

                with st.spinner(
                    "Gatherly is researching entities, interests, and recommendations..."
                ):
                    try:
                        candidates, logs, summary = research_event(
                            plan["city"],
                            plan["type"],
                            plan["interests"],
                        )

                        ranked = rank_candidates(
                            candidates,
                            plan["type"],
                            plan["interests"],
                        )

                        st.session_state.candidates = ranked
                        st.session_state.research_logs = logs
                        st.session_state.research_summary = summary
                        st.session_state.last_plan = plan
                        st.session_state.research_error = None

                    except Exception as error:
                        st.session_state.research_error = str(error)
                        st.session_state.research_logs = [
                            f"Research failed: {str(error)}"
                        ]

                st.rerun()

    with right:
        with st.container(border=True):
            st.subheader("Your event preview")
            st.caption("A live overview of your event plan.")

            current = st.session_state.last_plan

            if current:
                st.markdown(f"### {current['name']}")
                st.markdown(
                    f'<span class="pill">{current["type"]}</span>'
                    f'<span class="pill">{current["city"]}</span>',
                    unsafe_allow_html=True,
                )

                st.write("")
                st.write(f"📅 **Date:** {current['date']}")
                st.write(f"👥 **Guests:** {current['guests']:,}")
                st.write(f"💰 **Budget:** ₹{current['budget']:,}")

                per_guest = (
                    current["budget"] / current["guests"]
                    if current["guests"]
                    else 0
                )

                st.metric("Budget per guest", f"₹{per_guest:,.0f}")

                st.progress(
                    min(current["guests"] / 10000, 1.0),
                    text="Guest count indicator",
                )

                if st.button(
                    "＋ Save this event",
                    type="primary",
                    use_container_width=True,
                ):
                    saved = dict(current)
                    saved["saved_at"] = datetime.now().isoformat()

                    if not any(
                        item["name"] == saved["name"]
                        and item["date"] == saved["date"]
                        for item in st.session_state.events
                    ):
                        st.session_state.events.append(saved)
                        st.success("Event saved!")
                    else:
                        st.info("This event is already saved.")

            else:
                st.markdown("### Your next great moment starts here")
                st.write(
                    "Complete the event details to begin researching "
                    "relevant places and cultural interests."
                )
                st.markdown(
                    '<span class="pill">Personalized discovery</span>'
                    '<span class="pill">Budget planning</span>'
                    '<span class="pill">Research insights</span>',
                    unsafe_allow_html=True,
                )

    if st.session_state.research_error:
        st.error(
            "Research could not complete. Check the Qloo API configuration "
            "and try again."
        )
        with st.expander("Technical details"):
            st.code(st.session_state.research_error)

    if st.session_state.last_plan:
        st.divider()
        st.subheader("✦ Research-backed recommendations")

        summary = st.session_state.research_summary

        m1, m2, m3 = st.columns(3)

        m1.metric("Results collected", summary.get("candidate_count", 0))
        m2.metric("Entity signals", summary.get("entity_signals", 0))
        m3.metric("Interest tags", summary.get("tag_signals", 0))

        if not st.session_state.candidates:
            st.warning(
                "No usable places were returned. Check Research Activity "
                "for API errors. Gatherly won't invent venue recommendations."
            )

        for index, candidate in enumerate(
            st.session_state.candidates[:MAX_SEARCH_RESULTS],
            start=1,
        ):
            st.markdown(
                f"""
                <div class="venue">
                    <div class="eyebrow">RESULT {index}</div>
                    <h3>{candidate['name']}</h3>
                    <p class="muted">{candidate.get('description') or 'No description supplied by the API.'}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            sources = ", ".join(sorted(candidate["sources"]))
            st.caption(f"Source: {sources}")

            if candidate.get("matched"):
                st.caption(
                    "Matched interests: " + ", ".join(candidate["matched"])
                )

            if candidate.get("id"):
                st.caption(f"Qloo entity ID: {candidate['id']}")


# -------------------- PAGE: RESEARCH ACTIVITY --------------------

elif st.session_state.page == "Research Activity":

    render_hero(
        "Behind the intelligence.",
        "Review Gatherly's research steps, Qloo results, and diagnostics.",
    )

    summary = st.session_state.research_summary

    if summary:
        a, b, c, d = st.columns(4)

        a.metric("Queries", summary.get("queries_attempted", 0))
        b.metric("Search calls", summary.get("successful_searches", 0))
        c.metric("Entity signals", summary.get("entity_signals", 0))
        d.metric("Candidates", summary.get("candidate_count", 0))

    st.subheader("Research timeline")

    logs = st.session_state.research_logs

    if logs:
        for index, log in enumerate(logs, start=1):
            st.markdown(
                f"""
                <div class="venue">
                    <span class="pill">STEP {index}</span>
                    {log}
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info(
            "No research activity yet. Go to Plan an Event and start a research run."
        )

    with st.expander("API configuration diagnostics"):
        try:
            api_key = st.secrets.get("QLOO_API_KEY", "")
            if api_key:
                st.success("QLOO_API_KEY is configured.")
            else:
                st.warning("QLOO_API_KEY was not found in Streamlit secrets.")
        except Exception:
            st.warning(
                "Could not read Streamlit secrets. Check your .streamlit/secrets.toml."
            )

        st.caption(
            "Never share your API key. A configured key does not guarantee "
            "that the API account has access to every endpoint."
        )

    if st.button("Clear research history"):
        st.session_state.research_logs = []
        st.session_state.research_summary = {}
        st.session_state.candidates = []
        st.session_state.research_error = None
        st.rerun()


# -------------------- PAGE: MY EVENTS --------------------

elif st.session_state.page == "My Events":

    render_hero(
        "Your moments, organized.",
        "View and manage the events you've saved in this session.",
    )

    events = st.session_state.events

    if not events:
        st.info(
            "You haven't saved any events yet. Create a plan and select Save this event."
        )
    else:
        st.caption(f"{len(events)} saved event(s)")

        for index, event in enumerate(events):
            with st.container(border=True):
                left, right = st.columns([4, 1])

                with left:
                    st.markdown(f"### {event['name']}")
                    st.caption(f"{event['type']} · {event['city']}")
                    st.write(f"📅 {event['date']}")
                    st.write(f"👥 {event['guests']:,} guests")
                    st.write(f"💰 Budget: ₹{event['budget']:,}")

                    if event.get("interests"):
                        st.caption(f"Interests: {event['interests']}")

                with right:
                    if st.button("Delete", key=f"delete_{index}"):
                        st.session_state.events.pop(index)
                        st.rerun()

        st.divider()

        export_data = json.dumps(events, indent=2, ensure_ascii=False)

        st.download_button(
            "↓ Export events as JSON",
            data=export_data,
            file_name="gatherly_events.json",
            mime="application/json",
            use_container_width=True,
        )


# -------------------- FOOTER --------------------

st.divider()
st.markdown(
    '<p style="text-align:center;color:#77728f;font-size:12px;">'
    'GATHERLY AI · PLAN WITH INTELLIGENCE · MAKE IT MEMORABLE'
    '</p>',
    unsafe_allow_html=True,
)