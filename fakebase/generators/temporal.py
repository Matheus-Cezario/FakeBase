"""Geradores de datas, horas e timestamps."""

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
        f"Não foi possível interpretar {param}={value!r}. "
        f"Formatos aceitos: {', '.join(_INPUT_FORMATS)}"
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
    raise GeneratorError(f"dateType '{dateType}' inválido. Use past, all ou future.")


def _random_datetime(ctx: GenContext, begin: datetime, end: datetime) -> datetime:
    seconds = int((end - begin).total_seconds())
    if seconds <= 0:
        return begin
    return begin + timedelta(seconds=ctx.rng.randrange(seconds))


@generator(
    "date",
    category="tempo",
    doc="Data aleatória formatada.",
    params={
        "valueFormat": "formato strftime (padrão %d/%m/%Y %H:%M:%S)",
        "dateType": "past | all | future (padrão all)",
        "dataRange": "deslocamento máximo em anos (padrão 20)",
        "start": "data inicial explícita (ex.: 2024-01-01)",
        "stop": "data final explícita",
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
    category="tempo",
    doc="Data/hora no formato ISO 8601.",
    params={
        "dateType": "past | all | future (padrão all)",
        "dataRange": "deslocamento máximo em anos (padrão 20)",
        "start": "data inicial explícita",
        "stop": "data final explícita",
        "dateOnly": "somente a data, sem hora (padrão false)",
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
    category="tempo",
    doc="Timestamp Unix.",
    params={
        "unit": "s | ms (padrão s)",
        "dateType": "past | all | future (padrão past)",
        "dataRange": "deslocamento máximo em anos (padrão 20)",
        "start": "data inicial explícita",
        "stop": "data final explícita",
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
    category="tempo",
    doc="Horário aleatório do dia.",
    params={"valueFormat": "formato strftime (padrão %H:%M:%S)"},
)
def time_of_day(ctx: GenContext, valueFormat: str = "%H:%M:%S") -> str:
    moment = datetime(2000, 1, 1) + timedelta(seconds=ctx.rng.randrange(24 * 60 * 60))
    return moment.strftime(valueFormat)
