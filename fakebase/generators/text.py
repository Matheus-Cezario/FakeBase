"""Text, web and media generators."""

from __future__ import annotations

from typing import Optional

from .base import GenContext, generator
from .people import slugify


@generator(
    "word",
    category="text",
    doc="One or more words.",
    params={"count": "number of words (default 1)"},
    aliases=("words",),
)
def word(ctx: GenContext, count: int = 1) -> str:
    return " ".join(ctx.faker.words(nb=max(count, 1)))


@generator(
    "sentence",
    category="text",
    doc="Short sentence.",
    params={"words": "approximate number of words (default 6)"},
)
def sentence(ctx: GenContext, words: int = 6) -> str:
    return ctx.faker.sentence(nb_words=max(words, 1))


@generator(
    "paragraph",
    category="text",
    doc="Paragraph.",
    params={"sentences": "number of sentences (default 3)"},
)
def paragraph(ctx: GenContext, sentences: int = 3) -> str:
    return ctx.faker.paragraph(nb_sentences=max(sentences, 1))


@generator(
    "text",
    category="text",
    doc="Block of text.",
    params={"maxChars": "maximum length in characters (default 200)"},
)
def text(ctx: GenContext, maxChars: int = 200) -> str:
    return ctx.faker.text(max_nb_chars=max(maxChars, 5))


@generator(
    "slug",
    category="text",
    doc="URL-friendly identifier.",
    params={
        "value": "source text, usually '__fieldName' (default: random words)",
        "separator": "separator (default -)",
    },
)
def slug(ctx: GenContext, value: Optional[str] = None, separator: str = "-") -> str:
    base = value if value is not None else " ".join(ctx.faker.words(nb=3))
    return slugify(base, separator)


@generator(
    "color",
    category="media",
    doc="Random color.",
    params={"valueFormat": "hex | name | rgb (default hex)"},
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
    category="media",
    doc="Placeholder image URL.",
    params={"width": "width (default 640)", "height": "height (default 480)"},
)
def image_url(ctx: GenContext, width: int = 640, height: int = 480) -> str:
    return f"https://picsum.photos/seed/{ctx.rng.randrange(10**6)}/{width}/{height}"


@generator("url", category="web", doc="Random URL.")
def url(ctx: GenContext) -> str:
    return ctx.faker.url()


@generator("domain", category="web", doc="Domain name.")
def domain(ctx: GenContext) -> str:
    return ctx.faker.domain_name()


@generator("ipv4", category="web", doc="IPv4 address.")
def ipv4(ctx: GenContext) -> str:
    return ctx.faker.ipv4()


@generator("ipv6", category="web", doc="IPv6 address.")
def ipv6(ctx: GenContext) -> str:
    return ctx.faker.ipv6()


@generator("macAddress", category="web", doc="MAC address.")
def mac_address(ctx: GenContext) -> str:
    return ctx.faker.mac_address()


@generator("userAgent", category="web", doc="Browser user agent.")
def user_agent(ctx: GenContext) -> str:
    return ctx.faker.user_agent()


@generator(
    "fileName",
    category="media",
    doc="File name.",
    params={"extension": "fixed extension, for example 'pdf' (optional)"},
)
def file_name(ctx: GenContext, extension: Optional[str] = None) -> str:
    return ctx.faker.file_name(extension=extension) if extension else ctx.faker.file_name()


@generator("mimeType", category="media", doc="MIME type.")
def mime_type(ctx: GenContext) -> str:
    return ctx.faker.mime_type()


@generator(
    "language",
    category="text",
    doc="Language code (pt_BR, en_US, ...).",
)
def language(ctx: GenContext) -> str:
    return ctx.faker.locale()


@generator(
    "currencyCode",
    category="business",
    doc="Currency code (BRL, USD, ...).",
)
def currency_code(ctx: GenContext) -> str:
    return ctx.faker.currency_code()
