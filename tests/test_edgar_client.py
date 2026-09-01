"""
Tests for src/edgar_client.py.

These mock `requests.get` with response shapes matching SEC's real API
schemas (ticker lookup, submissions JSON, filing document) - verifying
the parsing logic is correct without making live network calls in CI.
"""

from unittest.mock import MagicMock, patch

import pytest

from src import edgar_client


@pytest.fixture(autouse=True)
def _set_user_agent(monkeypatch):
    monkeypatch.setattr(edgar_client.settings, "sec_user_agent", "Test User test@example.com")


def _mock_response(json_data=None, text_data=None, status=200):
    resp = MagicMock()
    resp.status_code = status
    if json_data is not None:
        resp.json.return_value = json_data
    if text_data is not None:
        resp.text = text_data
    resp.raise_for_status = MagicMock()
    return resp


def test_missing_user_agent_raises_clear_error(monkeypatch):
    monkeypatch.setattr(edgar_client.settings, "sec_user_agent", "")
    with pytest.raises(edgar_client.EdgarClientError, match="SEC_USER_AGENT"):
        edgar_client.get_cik_for_ticker("AAPL")


@patch("src.edgar_client.requests.get")
def test_get_cik_for_ticker_finds_match(mock_get):
    mock_get.return_value = _mock_response(
        json_data={
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
        }
    )
    cik = edgar_client.get_cik_for_ticker("AAPL")
    assert cik == "0000320193"


@patch("src.edgar_client.requests.get")
def test_get_cik_for_ticker_raises_when_not_found(mock_get):
    mock_get.return_value = _mock_response(json_data={"0": {"cik_str": 1, "ticker": "ZZZZ"}})
    with pytest.raises(edgar_client.EdgarClientError, match="No CIK found"):
        edgar_client.get_cik_for_ticker("NOTREAL")


@patch("src.edgar_client.requests.get")
def test_get_latest_10k_filing_finds_10k_among_mixed_forms(mock_get):
    mock_get.return_value = _mock_response(
        json_data={
            "filings": {
                "recent": {
                    "form": ["8-K", "10-Q", "10-K", "4"],
                    "accessionNumber": ["0001-a", "0002-b", "0003-c", "0004-d"],
                    "primaryDocument": ["a.htm", "b.htm", "c.htm", "d.htm"],
                    "filingDate": ["2025-01-01", "2025-06-01", "2025-11-01", "2025-12-01"],
                }
            }
        }
    )
    filing = edgar_client.get_latest_10k_filing("0000320193")
    assert filing["accession_number"] == "0003-c"
    assert filing["primary_document"] == "c.htm"
    assert filing["filing_date"] == "2025-11-01"


@patch("src.edgar_client.requests.get")
def test_get_latest_10k_filing_raises_when_no_10k_present(mock_get):
    mock_get.return_value = _mock_response(
        json_data={
            "filings": {
                "recent": {
                    "form": ["8-K"],
                    "accessionNumber": ["x"],
                    "primaryDocument": ["x.htm"],
                    "filingDate": ["2025-01-01"],
                }
            }
        }
    )
    with pytest.raises(edgar_client.EdgarClientError, match="No 10-K filing found"):
        edgar_client.get_latest_10k_filing("0000320193")


def test_strip_html_removes_tags_and_collapses_whitespace():
    html = "<html><body><p>Revenue   was  $100M.</p>\n\n<div>Net income grew.</div></body></html>"
    text = edgar_client._strip_html(html)
    assert "<" not in text
    assert "Revenue was $100M." in text
    assert "Net income grew." in text


@patch("src.edgar_client.requests.get")
def test_download_filing_text_builds_correct_url_and_strips_html(mock_get):
    mock_get.return_value = _mock_response(text_data="<p>Some filing content here.</p>")
    text = edgar_client.download_filing_text("320193", "0000320193-25-000100", "aapl-10k.htm")

    called_url = mock_get.call_args[0][0]
    assert "320193" in called_url
    assert "000032019325000100" in called_url
    assert "aapl-10k.htm" in called_url
    assert "Some filing content here." in text


@patch("src.edgar_client.download_filing_text")
@patch("src.edgar_client.get_latest_10k_filing")
@patch("src.edgar_client.get_cik_for_ticker")
def test_fetch_latest_10k_chains_all_three_calls(mock_cik, mock_filing, mock_download):
    mock_cik.return_value = "0000320193"
    mock_filing.return_value = {
        "accession_number": "0000320193-25-000100",
        "primary_document": "aapl-10k.htm",
        "filing_date": "2025-11-01",
    }
    mock_download.return_value = "full filing text"

    result = edgar_client.fetch_latest_10k("AAPL")

    mock_cik.assert_called_once_with("AAPL")
    mock_filing.assert_called_once_with("0000320193")
    mock_download.assert_called_once_with("0000320193", "0000320193-25-000100", "aapl-10k.htm")
    assert result == "full filing text"
