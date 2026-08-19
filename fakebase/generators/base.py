"""Infraestrutura dos geradores de valores.

Um gerador é uma função registrada com :func:`generator` que recebe um
:class:`GenContext` e os parâmetros declarados no *schematic*::

    @generator("number", doc="Número aleatório")
    def number(ctx: GenContext, start: float = -1000.0, stop: float = 1000.0):
        ...

O registro guarda a assinatura, o que permite validar parâmetros
desconhecidos, converter tipos vindos do JSON e documentar tudo em
``fakebase generators``.
"""

from __future__ import annotations

import inspect
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from ..errors import GeneratorError

Renderer = Callable[[Any], Any]


@dataclass
class GenContext:
    """Estado compartilhado por todos os geradores durante a geração."""

    rng: random.Random
    faker: Any
    base_dir: Path
    #: estado persistente por escopo (``banco.campo``) - pools, contadores...
    state: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    #: campos já gerados da linha atual
    row: Dict[str, Any] = field(default_factory=dict)
    database: str = ""
    field_name: str = ""
    row_index: int = 0
    #: gera o valor de uma sub-especificação (usado por ``object``/``array``)
    render: Optional[Renderer] = None

    @property
    def scope(self) -> str:
        return f"{self.database}.{self.field_name}"

    def local(self) -> Dict[str, Any]:
        """Estado persistente do campo atual."""
        return self.state.setdefault(self.scope, {})

    def shared(self) -> Dict[str, Any]:
        """Estado compartilhado por toda a geração (cache de arquivos)."""
        return self.state.setdefault("__shared__", {})

    def for_field(self, field_name: str) -> "GenContext":
        clone = GenContext(
            rng=self.rng,
            faker=self.faker,
            base_dir=self.base_dir,
            state=self.state,
            row=self.row,
            database=self.database,
            field_name=field_name,
            row_index=self.row_index,
            render=self.render,
        )
        return clone


SizeLimit = Callable[[Mapping[str, Any], Path], Optional[int]]


@dataclass
class GeneratorSpec:
    """Metadados de um gerador registrado."""

    name: str
    func: Callable[..., Any]
    doc: str = ""
    params: Dict[str, str] = field(default_factory=dict)
    aliases: Sequence[str] = ()
    size_limit: Optional[SizeLimit] = None
    category: str = "geral"

    @property
    def signature(self) -> inspect.Signature:
        return inspect.signature(self.func)

    def accepted_params(self) -> List[str]:
        return [p for p in self.signature.parameters if p != "ctx"]

    def call(self, ctx: GenContext, params: Mapping[str, Any]) -> Any:
        kwargs = self._prepare(params)
        try:
            return self.func(ctx, **kwargs)
        except GeneratorError:
            raise
        except Exception as exc:  # pragma: no cover - proteção genérica
            raise GeneratorError(
                f"Falha no gerador '{self.name}' (campo '{ctx.field_name}'): {exc}"
            ) from exc

    def _prepare(self, params: Mapping[str, Any]) -> Dict[str, Any]:
        signature = self.signature
        accepted = set(self.accepted_params())
        has_var_kw = any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()
        )
        kwargs: Dict[str, Any] = {}
        for key, value in params.items():
            if key not in accepted and not has_var_kw:
                raise GeneratorError(
                    f"Parâmetro '{key}' não existe no gerador '{self.name}'. "
                    f"Disponíveis: {', '.join(sorted(accepted)) or 'nenhum'}"
                )
            parameter = signature.parameters.get(key)
            kwargs[key] = _convert(value, parameter.annotation if parameter else None, self.name, key)
        return kwargs


REGISTRY: Dict[str, GeneratorSpec] = {}


def generator(
    name: str,
    *,
    doc: str = "",
    params: Optional[Dict[str, str]] = None,
    aliases: Sequence[str] = (),
    size_limit: Optional[SizeLimit] = None,
    category: str = "geral",
):
    """Registra uma função como gerador de valores."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        summary = doc.strip() if doc else _first_line(func.__doc__)
        spec = GeneratorSpec(
            name=name,
            func=func,
            doc=summary,
            params=params or {},
            aliases=tuple(aliases),
            size_limit=size_limit,
            category=category,
        )
        REGISTRY[name] = spec
        for alias in spec.aliases:
            REGISTRY[alias] = spec
        return func

    return decorator


def _first_line(text: Optional[str]) -> str:
    for line in (text or "").strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def get(name: str) -> Optional[GeneratorSpec]:
    return REGISTRY.get(name)


def exists(name: Any) -> bool:
    return isinstance(name, str) and name in REGISTRY


def available() -> List[GeneratorSpec]:
    """Geradores registrados, sem repetir os apelidos."""
    seen: Dict[int, GeneratorSpec] = {}
    for spec in REGISTRY.values():
        seen.setdefault(id(spec), spec)
    return sorted(seen.values(), key=lambda s: (s.category, s.name))


# ---------------------------------------------------------------------------
# Conversão de parâmetros vindos do JSON
# ---------------------------------------------------------------------------

_TRUE = {"1", "true", "yes", "on", "y"}
_FALSE = {"0", "false", "no", "off", "n"}


def _convert(value: Any, annotation: Any, generator_name: str, param: str) -> Any:
    if annotation is inspect.Parameter.empty or annotation is None or value is None:
        return value
    text_annotation = str(annotation)
    try:
        if annotation is bool or "bool" in text_annotation:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in _TRUE:
                    return True
                if lowered in _FALSE:
                    return False
            if isinstance(value, (int, float)):
                return bool(value)
            return value
        if annotation is int or ("int" in text_annotation and "float" not in text_annotation):
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                return value
            return int(float(value))
        if annotation is float or "float" in text_annotation:
            if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                return value
            return float(value)
    except (TypeError, ValueError):
        raise GeneratorError(
            f"Parâmetro '{param}' do gerador '{generator_name}' recebeu {value!r}, "
            f"incompatível com {text_annotation}"
        )
    return value


# ---------------------------------------------------------------------------
# Helpers reutilizados por vários geradores
# ---------------------------------------------------------------------------


def load_data(ctx: GenContext, data: Any, *, param: str = "data") -> List[Any]:
    """Normaliza o parâmetro ``data``.

    Aceita uma lista literal, o caminho de um arquivo texto (um valor por
    linha) ou o resultado já resolvido de uma referência entre bancos.
    """
    if data is None:
        raise GeneratorError(f"O parâmetro '{param}' é obrigatório")
    if isinstance(data, (list, tuple)):
        return list(data)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, str):
        return read_lines(ctx, data)
    return [data]


def read_lines(ctx: GenContext, path: str) -> List[str]:
    """Lê (com cache) um arquivo texto como lista de valores."""
    cache: Dict[str, List[str]] = ctx.shared().setdefault("files", {})
    if path in cache:
        return list(cache[path])
    resolved = resolve_path(ctx.base_dir, path)
    if not resolved.is_file():
        raise GeneratorError(f"Arquivo de dados não encontrado: {path}")
    lines = [line.strip() for line in resolved.read_text(encoding="utf-8").splitlines()]
    values = [line for line in lines if line]
    cache[path] = values
    return list(values)


def resolve_path(base_dir: Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    relative = base_dir / candidate
    if relative.exists():
        return relative
    return candidate


def data_length(data: Any, base_dir: Path) -> Optional[int]:
    """Tamanho de ``data`` sem precisar de um contexto (usado nos limites)."""
    if isinstance(data, (list, tuple)):
        return len(data)
    if isinstance(data, str):
        if data.startswith("@"):  # referência entre bancos: só se sabe em runtime
            return None
        resolved = resolve_path(base_dir, data)
        if resolved.is_file():
            return sum(
                1 for line in resolved.read_text(encoding="utf-8").splitlines() if line.strip()
            )
    return None


def no_repeat_limit(params: Mapping[str, Any], base_dir: Path) -> Optional[int]:
    """Limite de linhas quando o gerador não pode repetir valores."""
    repeat = params.get("repeat", True)
    if isinstance(repeat, str):
        repeat = repeat.strip().lower() not in _FALSE
    if repeat:
        return None
    return data_length(params.get("data"), base_dir)


def pick_pool(ctx: GenContext, data: Iterable[Any]) -> List[Any]:
    """Pool persistente por campo, usado quando ``repeat`` é ``false``.

    Se o estado trouxer um conjunto ``exclude`` (valores já gravados no
    banco), eles ficam de fora — é o que mantém a promessa de "sem
    repetição" quando novos documentos são acrescentados depois.
    """
    local = ctx.local()
    if "pool" not in local:
        excluded = local.get("exclude") or set()
        local["pool"] = [value for value in data if not _is_excluded(value, excluded)]
    return local["pool"]


def _is_excluded(value: Any, excluded: Any) -> bool:
    try:
        return value in excluded
    except TypeError:  # valores não hasheáveis (listas, dicionários)
        return False
