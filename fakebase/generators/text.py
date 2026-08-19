"""Geradores de texto, web e mídia."""

from __future__ import annotations

from typing import Optional

from .base import GenContext, generator
from .people import slugify


@generator(
    "word",
    category="texto",
    doc="Uma ou mais palavras.",
    params={"count": "quantidade de palavras (padrão 1)"},
    aliases=("words",),
)
def word(ctx: GenContext, count: int = 1) -> str:
    return " ".join(ctx.faker.words(nb=max(count, 1)))


@generator(
    "sentence",
    category="texto",
    doc="Frase curta.",
    params={"words": "quantidade aproximada de palavras (padrão 6)"},
)
def sentence(ctx: GenContext, words: int = 6) -> str:
    return ctx.faker.sentence(nb_words=max(words, 1))


@generator(
    "paragraph",
    category="texto",
    doc="Parágrafo.",
    params={"sentences": "quantidade de frases (padrão 3)"},
)
def paragraph(ctx: GenContext, sentences: int = 3) -> str:
    return ctx.faker.paragraph(nb_sentences=max(sentences, 1))


@generator(
    "text",
    category="texto",
    doc="Bloco de texto.",
    params={"maxChars": "tamanho máximo em caracteres (padrão 200)"},
)
def text(ctx: GenContext, maxChars: int = 200) -> str:
    return ctx.faker.text(max_nb_chars=max(maxChars, 5))


@generator(
    "slug",
    category="texto",
    doc="Identificador amigável para URLs.",
    params={
        "value": "texto de origem, normalmente '__nomeDoCampo' (padrão: palavras aleatórias)",
        "separator": "separador (padrão -)",
    },
)
def slug(ctx: GenContext, value: Optional[str] = None, separator: str = "-") -> str:
    base = value if value is not None else " ".join(ctx.faker.words(nb=3))
    return slugify(base, separator)


@generator(
    "color",
    category="mídia",
    doc="Cor aleatória.",
    params={"valueFormat": "hex | name | rgb (padrão hex)"},
)
def color(ctx: GenContext, valueFormat: str = "hex") -> str:
    mode = str(valueFormat).lower()
    if mode == "name":
        return ctx.faker.color_name()
    if mode == "rgb":
        return ctx.faker.rgb_color()
    return ctx.faker.hex_color()


@generator(
    "imageUrl",
    category="mídia",
    doc="URL de imagem de placeholder.",
    params={"width": "largura (padrão 640)", "height": "altura (padrão 480)"},
)
def image_url(ctx: GenContext, width: int = 640, height: int = 480) -> str:
    return f"https://picsum.photos/seed/{ctx.rng.randrange(10**6)}/{width}/{height}"


@generator("url", category="web", doc="URL aleatória.")
def url(ctx: GenContext) -> str:
    return ctx.faker.url()


@generator("domain", category="web", doc="Nome de domínio.")
def domain(ctx: GenContext) -> str:
    return ctx.faker.domain_name()


@generator("ipv4", category="web", doc="Endereço IPv4.")
def ipv4(ctx: GenContext) -> str:
    return ctx.faker.ipv4()


@generator("ipv6", category="web", doc="Endereço IPv6.")
def ipv6(ctx: GenContext) -> str:
    return ctx.faker.ipv6()


@generator("macAddress", category="web", doc="Endereço MAC.")
def mac_address(ctx: GenContext) -> str:
    return ctx.faker.mac_address()


@generator("userAgent", category="web", doc="User agent de navegador.")
def user_agent(ctx: GenContext) -> str:
    return ctx.faker.user_agent()


@generator(
    "fileName",
    category="mídia",
    doc="Nome de arquivo.",
    params={"extension": "extensão fixa, por exemplo 'pdf' (opcional)"},
)
def file_name(ctx: GenContext, extension: Optional[str] = None) -> str:
    return ctx.faker.file_name(extension=extension) if extension else ctx.faker.file_name()


@generator("mimeType", category="mídia", doc="Tipo MIME.")
def mime_type(ctx: GenContext) -> str:
    return ctx.faker.mime_type()


@generator(
    "language",
    category="texto",
    doc="Código de idioma (pt_BR, en_US, ...).",
)
def language(ctx: GenContext) -> str:
    return ctx.faker.locale()


@generator(
    "currencyCode",
    category="negócios",
    doc="Código de moeda (BRL, USD, ...).",
)
def currency_code(ctx: GenContext) -> str:
    return ctx.faker.currency_code()
