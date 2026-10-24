import requests
import streamlit as st

BASE_URL = "https://hackathon.api.qloo.com"
TIMEOUT = 20


def _headers():
    return {
        "X-Api-Key": st.secrets["QLOO_API_KEY"],
        "Accept": "application/json",
    }


def _get_json(endpoint, params):
    try:
        response = requests.get(
            f"{BASE_URL}{endpoint}",
            headers=_headers(),
            params=params,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.HTTPError as error:
        status = (
            error.response.status_code
            if error.response is not None
            else "unknown"
        )
        detail = (
            error.response.text[:1000]
            if error.response is not None
            else str(error)
        )
        raise RuntimeError(
            f"Qloo API HTTP {status}: {detail}"
        ) from error

    except requests.exceptions.Timeout as error:
        raise RuntimeError(
            f"Qloo API timed out after {TIMEOUT} seconds."
        ) from error

    except requests.exceptions.RequestException as error:
        raise RuntimeError(
            f"Qloo connection failed: {error}"
        ) from error


def _extract_entities(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    results = data.get("results", [])

    if isinstance(results, list):
        return results

    if isinstance(results, dict):
        for key in ("entities", "tags", "recommendations", "results"):
            value = results.get(key)
            if isinstance(value, list):
                return value

    for key in ("entities", "tags", "recommendations"):
        value = data.get(key)
        if isinstance(value, list):
            return value

    return []


def _normalize_types(types):
    if isinstance(types, str):
        return [types]

    if isinstance(types, list):
        return types

    return []


def search_entities(query, entity_type=None, limit=5):
    query = (query or "").strip()

    if not query:
        return []

    params = {
        "query": query,
        "take": limit,
    }

    if entity_type:
        params["types"] = f"urn:entity:{entity_type}"

    data = _get_json("/search", params)
    matches = []

    for entity in _extract_entities(data):
        if not isinstance(entity, dict):
            continue

        entity_id = (
            entity.get("entity_id")
            or entity.get("id")
            or entity.get("urn")
        )

        types = _normalize_types(entity.get("types", []))

        if entity_type:
            expected_type = f"urn:entity:{entity_type}"
            if expected_type not in types:
                continue

        name = entity.get("name", "")

        if not entity_id or not name:
            continue

        matches.append({
            **entity,
            "name": name,
            "entity_id": entity_id,
            "types": types,
        })

        if len(matches) >= limit:
            break

    return matches


def search_tags(query, limit=5):
    """Resolve a descriptive interest into Qloo cultural tags."""
    query = (query or "").strip()

    if not query:
        return []

    data = _get_json(
        "/v2/tags",
        {
            "filter.query": query,
            "take": limit,
        },
    )

    matches = []

    for tag in _extract_entities(data):
        if not isinstance(tag, dict):
            continue

        tag_id = (
            tag.get("tag_id")
            or tag.get("id")
            or tag.get("tag")
            or tag.get("entity_id")
        )

        name = (
            tag.get("name")
            or tag.get("tag_name")
            or tag.get("value")
            or ""
        )

        if not tag_id:
            continue

        matches.append({
            **tag,
            "name": name or query,
            "tag_id": tag_id,
        })

    query_lower = query.lower()

    matches.sort(
        key=lambda item: (
            item["name"].strip().lower() != query_lower,
            query_lower not in item["name"].lower(),
        )
    )

    return matches[:limit]


def get_insights(
    entity_ids=None,
    result_type="place",
    city=None,
    limit=5,
    tag_ids=None,
):
    """Retrieve Qloo Insights recommendations using entity or tag signals."""
    entity_ids = entity_ids or []
    tag_ids = tag_ids or []

    if not entity_ids and not tag_ids:
        raise ValueError(
            "At least one Qloo entity ID or cultural tag ID is required."
        )

    allowed_types = {
        "artist",
        "book",
        "brand",
        "destination",
        "movie",
        "person",
        "place",
        "podcast",
        "tv_show",
        "video_game",
    }

    if result_type not in allowed_types:
        raise ValueError(
            f"Unsupported recommendation type: {result_type}"
        )

    params = {
        "filter.type": f"urn:entity:{result_type}",
        "take": limit,
    }

    if entity_ids:
        params["signal.interests.entities"] = ",".join(entity_ids)

    if tag_ids:
        params["signal.interests.tags"] = ",".join(tag_ids)

    if city and city.strip() and result_type in {"place", "destination"}:
        params["filter.location.query"] = city.strip()

    data = _get_json("/v2/insights", params)

    recommendations = _extract_entities(data)

    return {
        "result_type": result_type,
        "recommendations": [
            item for item in recommendations
            if isinstance(item, dict)
        ],
    }