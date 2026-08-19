"""Geradores de dados pessoais, de contato e de negócio.

Apoiam-se no `Faker`, o que traz suporte a *locale*: com
``"Settings": {"locale": "pt_BR"}`` os nomes, cidades e documentos passam a
ser brasileiros.
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
            f"O locale '{getattr(ctx.faker, 'locales', ['?'])[0]}' não oferece '{name}'. "
            "Troque o locale em Settings ou use outro gerador."
        )
    return provider


def _gender(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = _GENDERS.get(str(value).strip().lower())
    if normalized is None:
        raise GeneratorError(f"gender '{value}' inválido. Use male, female ou null.")
    return normalized


def slugify(text: str, separator: str = "-") -> str:
    normalized = unicodedata.normalize("NFKD", str(text))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", separator, ascii_text).strip(separator)


@generator(
    "humanName",
    category="pessoas",
    doc="Nome de pessoa.",
    params={
        "gender": "male | female | null (padrão null)",
        "valueFormat": "lista com 'first' e/ou 'last' (padrão nome completo)",
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
    raise GeneratorError(f"valueFormat aceita 'first' e 'last', não {position!r}")


@generator(
    "firstName",
    category="pessoas",
    doc="Primeiro nome.",
    params={"gender": "male | female | null"},
)
def first_name(ctx: GenContext, gender: Optional[str] = None) -> str:
    return _name_part(ctx, "first", _gender(gender))


@generator("lastName", category="pessoas", doc="Sobrenome.")
def last_name(ctx: GenContext) -> str:
    return ctx.faker.last_name()


@generator(
    "email",
    category="pessoas",
    doc="Endereço de e-mail.",
    params={
        "name": "base do endereço, normalmente '__nomeDoCampo' (opcional)",
        "domain": "domínio fixo, por exemplo 'empresa.com' (opcional)",
    },
)
def email(ctx: GenContext, name: Optional[str] = None, domain: Optional[str] = None) -> str:
    if name:
        local_part = slugify(name, ".")
        return f"{local_part}@{domain or ctx.faker.domain_name()}"
    if domain:
        return f"{slugify(ctx.faker.user_name(), '.')}@{domain}"
    return ctx.faker.email()


@generator("username", category="pessoas", doc="Nome de usuário.")
def username(ctx: GenContext) -> str:
    return ctx.faker.user_name()


@generator(
    "password",
    category="pessoas",
    doc="Senha aleatória.",
    params={"length": "quantidade de caracteres (padrão 12)", "special": "usar símbolos (padrão true)"},
)
def password(ctx: GenContext, length: int = 12, special: bool = True) -> str:
    return ctx.faker.password(length=max(length, 4), special_chars=special)


@generator("phone", category="pessoas", doc="Número de telefone.", aliases=("phoneNumber",))
def phone(ctx: GenContext) -> str:
    return _provider(ctx, "phone_number")()


@generator("cpf", category="pessoas", doc="CPF (requer locale pt_BR).")
def cpf(ctx: GenContext) -> str:
    return _provider(ctx, "cpf")()


@generator("cnpj", category="pessoas", doc="CNPJ (requer locale pt_BR).")
def cnpj(ctx: GenContext) -> str:
    return _provider(ctx, "cnpj")()


@generator("address", category="lugares", doc="Endereço completo em uma linha.")
def address(ctx: GenContext) -> str:
    return " ".join(ctx.faker.address().splitlines())


@generator("street", category="lugares", doc="Logradouro.")
def street(ctx: GenContext) -> str:
    return ctx.faker.street_address()


@generator("city", category="lugares", doc="Cidade.")
def city(ctx: GenContext) -> str:
    return ctx.faker.city()


@generator(
    "state",
    category="lugares",
    doc="Estado/província.",
    params={"abbr": "usa a sigla, por exemplo RJ (padrão false)"},
)
def state(ctx: GenContext, abbr: bool = False) -> str:
    return _provider(ctx, "state_abbr")() if abbr else _provider(ctx, "state")()


@generator("country", category="lugares", doc="País.")
def country(ctx: GenContext) -> str:
    return ctx.faker.country()


@generator("postcode", category="lugares", doc="CEP / código postal.", aliases=("zipCode",))
def postcode(ctx: GenContext) -> str:
    return ctx.faker.postcode()


@generator(
    "coordinates",
    category="lugares",
    doc="Par de coordenadas geográficas.",
    params={"asObject": "devolve {lat, lng} em vez de lista (padrão true)"},
)
def coordinates(ctx: GenContext, asObject: bool = True) -> Any:
    lat = round(ctx.rng.uniform(-90, 90), 6)
    lng = round(ctx.rng.uniform(-180, 180), 6)
    return {"lat": lat, "lng": lng} if asObject else [lat, lng]


@generator("company", category="negócios", doc="Nome de empresa.")
def company(ctx: GenContext) -> str:
    return ctx.faker.company()


@generator("jobTitle", category="negócios", doc="Cargo/profissão.", aliases=("job",))
def job_title(ctx: GenContext) -> str:
    return ctx.faker.job()


@generator(
    "creditCard",
    category="negócios",
    doc="Número de cartão de crédito fictício.",
    params={"cardType": "visa, mastercard, amex... (opcional)", "brandOnly": "devolve só a bandeira"},
)
def credit_card(ctx: GenContext, cardType: Optional[str] = None, brandOnly: bool = False) -> str:
    if brandOnly:
        return ctx.faker.credit_card_provider(card_type=cardType)
    return ctx.faker.credit_card_number(card_type=cardType)


@generator(
    "faker",
    category="avançado",
    doc="Executa qualquer provider do Faker pelo nome.",
    params={
        "provider": "nome do provider, por exemplo 'iban' ou 'license_plate'",
        "args": "lista de argumentos posicionais (opcional)",
        "kwargs": "dicionário de argumentos nomeados (opcional)",
    },
)
def faker_provider(
    ctx: GenContext,
    provider: Optional[str] = None,
    args: Optional[Sequence[Any]] = None,
    kwargs: Optional[dict] = None,
) -> Any:
    if not provider:
        raise GeneratorError("O parâmetro 'provider' é obrigatório no gerador 'faker'")
    if provider.startswith("_"):
        raise GeneratorError(f"Provider '{provider}' não é público")
    target = _provider(ctx, provider)
    if not callable(target):
        return target
    return target(*(args or []), **(kwargs or {}))
