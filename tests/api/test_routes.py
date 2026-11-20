from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient


def upload(
    client: TestClient, rows: Sequence[Mapping[str, object]]
) -> dict[str, Any]:
    """Post a batch and return the decoded batch report."""
    response = client.post("/batches", json={"respondents": rows})
    assert response.status_code == 200, response.text
    report: dict[str, Any] = response.json()

    return report


# ---- GET /health ----


def test_health_reports_dev_environment(client: TestClient) -> None:
    response = client.get("/health")

    assert response.json() == {"status": "ok", "environment": "dev"}


def test_health_reports_prod_environment(prod_client: TestClient) -> None:
    response = prod_client.get("/health")

    assert response.json() == {"status": "ok", "environment": "prod"}


# ---- POST /batches ----


def test_upload_returns_batch_report(
    client: TestClient, raw_row: dict[str, object]
) -> None:
    report = upload(client, [raw_row])

    assert report == {
        "rows_received": 1,
        "rows_loaded": 1,
        "invalid_rows": [],
        "corrected_values": [],
        "refreshed_waves": [3],
    }


def test_invalid_row_is_reported_with_values_as_received(
    client: TestClient, raw_row: dict[str, object]
) -> None:
    invalid_row = raw_row | {"respondent_id": 3002, "wave": 0}

    report = upload(client, [raw_row, invalid_row])

    assert report["rows_loaded"] == 1
    assert report["invalid_rows"] == [
        {
            "row_number": 2,
            "respondent_id": 3002,
            "values": invalid_row,
            "reason": "invalid_value",
            "details": "wave: Input should be greater than or equal to 1",
        }
    ]


def test_corrected_value_is_reported(
    client: TestClient, raw_row: dict[str, object]
) -> None:
    raw_row |= {"brand3_awareness": 0, "brand3_usage": 1}

    report = upload(client, [raw_row])

    assert report["corrected_values"] == [
        {
            "row_number": 1,
            "respondent_id": 3001,
            "column": "brand3_usage",
            "received": 1,
            "corrected": 0,
            "reason": "usage_without_awareness",
        }
    ]


def test_empty_batch_loads_nothing(client: TestClient) -> None:
    report = upload(client, [])

    assert report["rows_received"] == 0
    assert report["refreshed_waves"] == []


def test_body_without_respondents_is_unprocessable(client: TestClient) -> None:
    response = client.post("/batches", json={"rows": []})

    assert response.status_code == 422


def test_row_that_is_not_an_object_is_unprocessable(
    client: TestClient,
) -> None:
    response = client.post("/batches", json={"respondents": [1, 2]})

    assert response.status_code == 422


# ---- GET /summary ----


def upload_three_waves(client: TestClient, raw_row: dict[str, object]) -> None:
    """Upload waves 1 to 3, each with respondents aged 22 and 36."""
    upload(
        client,
        [
            raw_row
            | {"wave": wave, "respondent_id": wave * 10 + offset}
            | {"birth_year": birth_year}
            for wave in (1, 2, 3)
            for offset, birth_year in ((1, 2004), (2, 1990))
        ],
    )


def waves_and_categories(
    client: TestClient, query: str
) -> list[tuple[int, list[str]]]:
    """GET /summary and keep each wave with its category labels."""
    response = client.get(f"/summary{query}")
    assert response.status_code == 200, response.text

    return [
        (
            summary["wave"],
            [
                category["age_category"]
                for category in summary["age_categories"]
            ],
        )
        for summary in response.json()["waves"]
    ]


def test_summary_lists_brand_totals_per_age_category(
    client: TestClient, raw_row: dict[str, object]
) -> None:
    upload(client, [raw_row])

    response = client.get("/summary?wave=3")

    assert response.json() == {
        "waves": [
            {
                "wave": 3,
                "age_categories": [
                    {
                        "age_category": "35-44",
                        "respondents_total": 1,
                        "brands": [
                            {
                                "brand": "brand1",
                                "awareness_total": 1,
                                "usage_total": 1,
                            },
                            {
                                "brand": "brand2",
                                "awareness_total": 1,
                                "usage_total": 0,
                            },
                            {
                                "brand": "brand3",
                                "awareness_total": 0,
                                "usage_total": 0,
                            },
                        ],
                    }
                ],
            }
        ]
    }


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            "",
            [
                (1, ["18-24", "35-44"]),
                (2, ["18-24", "35-44"]),
                (3, ["18-24", "35-44"]),
            ],
        ),
        ("?wave=2", [(2, ["18-24", "35-44"])]),
        ("?wave_last=2", [(2, ["18-24", "35-44"]), (3, ["18-24", "35-44"])]),
        (
            "?wave_from=1&wave_to=2",
            [(1, ["18-24", "35-44"]), (2, ["18-24", "35-44"])],
        ),
        ("?wave=3&agecat=1", [(3, ["18-24"])]),
        ("?wave=3&agecat_from=2&agecat_to=5", [(3, ["35-44"])]),
    ],
)
def test_summary_selects_waves_and_age_categories(
    client: TestClient,
    raw_row: dict[str, object],
    query: str,
    expected: list[tuple[int, list[str]]],
) -> None:
    upload_three_waves(client, raw_row)

    assert waves_and_categories(client, query) == expected


def test_summary_without_match_is_not_found(
    client: TestClient, raw_row: dict[str, object]
) -> None:
    upload_three_waves(client, raw_row)

    response = client.get("/summary?wave=9")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "no stored summary matches the selected waves and age "
        "categories"
    }


@pytest.mark.parametrize(
    ("query", "detail"),
    [
        ("?wave=3&wave_last=2", "select waves in one way only"),
        ("?wave_from=3&wave_to=2", "wave range starts at 3, after its end 2"),
        ("?agecat=2&agecat_to=3", "select age categories in one way only"),
        ("?agecat=6", "age category 6 does not exist; there are 5"),
    ],
)
def test_contradictory_selection_is_unprocessable(
    client: TestClient, raw_row: dict[str, object], query: str, detail: str
) -> None:
    upload_three_waves(client, raw_row)

    response = client.get(f"/summary{query}")

    assert response.status_code == 422
    assert response.json()["detail"].startswith(detail)


@pytest.mark.parametrize("query", ["?wave=0", "?agecat=x", "?colour=red"])
def test_malformed_summary_query_is_unprocessable(
    client: TestClient, query: str
) -> None:
    assert client.get(f"/summary{query}").status_code == 422
