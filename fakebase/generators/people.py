"""Personal, contact and business data generators.

They rely on `Faker`, which brings *locale* support: with
``"Settings": {"locale": "pt_BR"}`` names, cities and ID numbers become
Brazilian.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, List, Optional, Sequence

from ..errors import GeneratorError
from .base import GenContext, generator

_GENDERS = {"male": "male", "m": "male", "female": "female", "f": "female"}


def _provider(ctx: GenContext, name: str) -> Any:
    provider = getattr(ctx.faker, name, None)
    if provider is None:
        raise GeneratorError(
            f"Locale '{getattr(ctx.faker, 'locales', ['?'])[0]}' does not provide '{name}'. "
            "Change the locale in Settings or use another generator."
        )
    return provider


def _gender(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = _GENDERS.get(str(value).strip().lower())
    if normalized is None:
        raise GeneratorError(f"Invalid gender '{value}'. Use male, female or null.")
    return normalized


def slugify(text: str, separator: str = "-") -> str:
    normalized = unicodedata.normalize("NFKD", str(text))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", separator, ascii_text).strip(separator)


@generator(
    "humanName",
    category="people",
    doc="Person name.",
    params={
        "gender": "male | female | null (default null)",
        "valueFormat": "list with 'first' and/or 'last' (default full name)",
    },
    aliases=("name",),
)
def human_name(
    ctx: GenContext, gender: Optional[str] = None, valueFormat: Optional[Sequence[str]] = None
) -> str:
    normalized = _gender(gender)
    if not valueFormat:
        if normalized == "male":
            return _provider(ctx, "name_male")()
        if normalized == "female":
            return _provider(ctx, "name_female")()
        return ctx.faker.name()
    parts: List[str] = []
    for position in valueFormat:
        parts.append(_name_part(ctx, str(position).lower(), normalized))
    return " ".join(part for part in parts if part)


def _name_part(ctx: GenContext, position: str, gender: Optional[str]) -> str:
    if position == "first":
        if gender == "male":
            return ctx.faker.first_name_male()
        if gender == "female":
            return ctx.faker.first_name_female()
        return ctx.faker.first_name()
    if position == "last":
        return ctx.faker.last_name()
    raise GeneratorError(f"valueFormat accepts 'first' and 'last', not {position!r}")


@generator(
    "firstName",
    category="people",
    doc="First name.",
    params={"gender": "male | female | null"},
)
def first_name(ctx: GenContext, gender: Optional[str] = None) -> str:
    return _name_part(ctx, "first", _gender(gender))


@generator("lastName", category="people", doc="Last name.")
def last_name(ctx: GenContext) -> str:
    return ctx.faker.last_name()


@generator(
    "email",
    category="people",
    doc="Email address.",
    params={
        "name": "base of the address, usually '__fieldName' (optional)",
        "domain": "fixed domain, for example 'company.com' (optional)",
    },
)
def email(ctx: GenContext, name: Optional[str] = None, domain: Optional[str] = None) -> str:
    if name:
        local_part = slugify(name, ".")
        return f"{local_part}@{domain or ctx.faker.domain_name()}"
    if domain:
        return f"{slugify(ctx.faker.user_name(), '.')}@{domain}"
    return ctx.faker.email()


@generator("username", category="people", doc="Username.")
def username(ctx: GenContext) -> str:
    return ctx.faker.user_name()


@generator(
    "password",
    category="people",
    doc="Random password.",
    params={"length": "number of characters (default 12)", "special": "use symbols (default true)"},
)
def password(ctx: GenContext, length: int = 12, special: bool = True) -> str:
    return ctx.faker.password(length=max(length, 4), special_chars=special)


@generator("phone", category="people", doc="Phone number.", aliases=("phoneNumber",))
def phone(ctx: GenContext) -> str:
    return _provider(ctx, "phone_number")()


@generator("cpf", category="people", doc="CPF (requires locale pt_BR).")
def cpf(ctx: GenContext) -> str:
    return _provider(ctx, "cpf")()


@generator("cnpj", category="people", doc="CNPJ (requires locale pt_BR).")
def cnpj(ctx: GenContext) -> str:
    return _provider(ctx, "cnpj")()


@generator("address", category="places", doc="Full address on one line.")
def address(ctx: GenContext) -> str:
    return " ".join(ctx.faker.address().splitlines())


@generator("street", category="places", doc="Street address.")
def street(ctx: GenContext) -> str:
    return ctx.faker.street_address()


@generator("city", category="places", doc="City.")
def city(ctx: GenContext) -> str:
    return ctx.faker.city()


@generator(
    "state",
    category="places",
    doc="State/province.",
    params={"abbr": "use the abbreviation, for example RJ (default false)"},
)
def state(ctx: GenContext, abbr: bool = False) -> str:
    return _provider(ctx, "state_abbr")() if abbr else _provider(ctx, "state")()


@generator("country", category="places", doc="Country.")
def country(ctx: GenContext) -> str:
    return ctx.faker.country()


@generator("postcode", category="places", doc="Postal code.", aliases=("zipCode",))
def postcode(ctx: GenContext) -> str:
    return ctx.faker.postcode()


@generator(
    "coordinates",
    category="places",
    doc="Pair of geographic coordinates.",
    params={"asObject": "return {lat, lng} instead of a list (default true)"},
)
def coordinates(ctx: GenContext, asObject: bool = True) -> Any:
    lat = round(ctx.rng.uniform(-90, 90), 6)
    lng = round(ctx.rng.uniform(-180, 180), 6)
    return {"lat": lat, "lng": lng} if asObject else [lat, lng]


@generator("company", category="business", doc="Company name.")
def company(ctx: GenContext) -> str:
    return ctx.faker.company()


@generator("jobTitle", category="business", doc="Job title.", aliases=("job",))
def job_title(ctx: GenContext) -> str:
    return ctx.faker.job()


@generator(
    "creditCard",
    category="business",
    doc="Fake credit card number.",
    params={"cardType": "visa, mastercard, amex... (optional)", "brandOnly": "return only the brand"},
)
def credit_card(ctx: GenContext, cardType: Optional[str] = None, brandOnly: bool = False) -> str:
    if brandOnly:
        return ctx.faker.credit_card_provider(card_type=cardType)
    return ctx.faker.credit_card_number(card_type=cardType)


@generator(
    "faker",
    category="advanced",
    doc="Run any Faker provider by name.",
    params={
        "provider": "provider name, for example 'iban' or 'license_plate'",
        "args": "list of positional arguments (optional)",
        "kwargs": "dictionary of keyword arguments (optional)",
    },
)
def faker_provider(
    ctx: GenContext,
    provider: Optional[str] = None,
    args: Optional[Sequence[Any]] = None,
    kwargs: Optional[dict] = None,
) -> Any:
    if not provider:
        raise GeneratorError("Parameter 'provider' is required by generator 'faker'")
    if provider.startswith("_"):
        raise GeneratorError(f"Provider '{provider}' is not public")
    target = _provider(ctx, provider)
    if not callable(target):
        return target
    return target(*(args or []), **(kwargs or {}))
