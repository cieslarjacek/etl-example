"""Survey client: turns survey CSV files into batch uploads.

It stands for an outside program feeding the survey ETL service, so it
uses only the service's HTTP API and never imports ``survey_etl``.
"""

from survey_client.batches import (
    CellValue,
    SurveyRow,
    build_batch_body,
    parse_cell,
    parse_survey_csv,
)
from survey_client.errors import (
    CsvFormatError,
    CsvLocation,
    InvalidHeaderError,
    MissingHeaderError,
    RowLengthError,
    UnsupportedUrlError,
)
from survey_client.upload import HttpReply, Poster, batches_url, post_json

__all__ = [
    "CellValue",
    "CsvFormatError",
    "CsvLocation",
    "HttpReply",
    "InvalidHeaderError",
    "MissingHeaderError",
    "Poster",
    "RowLengthError",
    "SurveyRow",
    "UnsupportedUrlError",
    "batches_url",
    "build_batch_body",
    "parse_cell",
    "parse_survey_csv",
    "post_json",
]
