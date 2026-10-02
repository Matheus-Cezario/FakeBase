"""Date, time and timestamp generators."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from ..errors import GeneratorError
from .base import GenContext, generator

_INPUT_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y",
)


def _parse(value: str, param: str) -> datetime:
    for fmt in _INPUT_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise GeneratorError(
        f"Could not parse {param}={value!r}. "
        f"Accepted formats: {', '.join(_INPUT_FORMATS)}"
    )


def _window(
    dateType: str, dataRange: int, start: Optional[str], stop: Optional[str]
) -> tuple[datetime, datetime]:
    now = datetime.now()
    if start or stop:
        begin = _parse(start, "start") if start else now - timedelta(days=365 * dataRange)
        end = _parse(stop, "stop") if stop else now + timedelta(days=365 * dataRange)
        return (begin, end) if begin <= end else (end, begin)

    future = now + timedelta(days=365 * dataRange)
    past = now - timedelta(days=365 * dataRange)
    mode = str(dateType).lower()
    if mode == "future":
        return now, future
    if mode == "past":
        return past, now
    if mode == "all":
        return past, future
    raise GeneratorError(f"Invalid dateType '{dateType}'. Use past, all or future.")


def _random_datetime(ctx: GenContext, begin: datetime, end: datetime) -> datetime:
    seconds = int((end - begin).total_seconds())
    if seconds <= 0:
        return begin
    return begin + timedelta(seconds=ctx.rng.randrange(seconds))


@generator(
    "date",
    category="time",
    doc="Formatted random date.",
    params={
        "valueFormat": "strftime format (default %d/%m/%Y %H:%M:%S)",
        "dateType": "past | all | future (default all)",
        "dataRange": "maximum offset in years (default 20)",
        "start": "explicit start date (e.g. 2024-01-01)",
        "stop": "explicit end date",
    },
)
def date(
    ctx: GenContext,
    valueFormat: str = "%d/%m/%Y %H:%M:%S",
    dateType: str = "all",
    dataRange: int = 20,
    start: Optional[str] = None,
    stop: Optional[str] = None,
) -> str:
    begin, end = _window(dateType, dataRange, start, stop)
    return _random_datetime(ctx, begin, end).strftime(valueFormat)


@generator(
    "isoDate",
    category="time",
    doc="Date/time in ISO 8601 format.",
    params={
        "dateType": "past | all | future (default all)",
        "dataRange": "maximum offset in years (default 20)",
        "start": "explicit start date",
        "stop": "explicit end date",
        "dateOnly": "date only, without time (default false)",
    },
)
def iso_date(
    ctx: GenContext,
    dateType: str = "all",
    dataRange: int = 20,
    start: Optional[str] = None,
    stop: Optional[str] = None,
    dateOnly: bool = False,
) -> str:
    begin, end = _window(dateType, dataRange, start, stop)
    moment = _random_datetime(ctx, begin, end)
    return moment.date().isoformat() if dateOnly else moment.isoformat(timespec="seconds")


@generator(
    "timestamp",
    category="time",
    doc="Timestamp Unix.",
    params={
        "unit": "s | ms (default s)",
        "dateType": "past | all | future (default past)",
        "dataRange": "maximum offset in years (default 20)",
        "start": "explicit start date",
        "stop": "explicit end date",
    },
)
def timestamp(
    ctx: GenContext,
    unit: str = "s",
    dateType: str = "past",
    dataRange: int = 20,
    start: Optional[str] = None,
    stop: Optional[str] = None,
) -> int:
    begin, end = _window(dateType, dataRange, start, stop)
    moment = _random_datetime(ctx, begin, end)
    seconds = int(moment.timestamp())
    return seconds * 1000 if str(unit).lower() == "ms" else seconds


@generator(
    "time",
    category="time",
    doc="Random time of day.",
    params={"valueFormat": "strftime format (default %H:%M:%S)"},
)
def time_of_day(ctx: GenContext, valueFormat: str = "%H:%M:%S") -> str:
    moment = datetime(2000, 1, 1) + timedelta(seconds=ctx.rng.randrange(24 * 60 * 60))
    return moment.strftime(valueFormat)
