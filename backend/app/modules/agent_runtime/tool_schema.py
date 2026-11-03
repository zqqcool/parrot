from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

JsonScalarType = Literal["boolean", "integer", "number", "string"]
JsonType = Literal["array", "boolean", "integer", "number", "object", "string"]


def _empty_properties() -> Mapping[str, JsonSchema]:
    return {}


@dataclass(frozen=True)
class JsonSchema:
    """Small immutable authoring model for Parrot's provider-compatible schema subset."""

    type_name: JsonType | tuple[JsonScalarType, ...]
    description: str | None = None
    enum: tuple[str, ...] = ()
    const: str | None = None
    properties: Mapping[str, JsonSchema] = field(default_factory=_empty_properties)
    required: tuple[str, ...] = ()
    items: JsonSchema | None = None
    additional_properties: bool | JsonSchema | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    min_length: int | None = None
    max_length: int | None = None
    min_items: int | None = None
    max_items: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "properties", MappingProxyType(dict(self.properties)))
        self._validate_shape()

    @classmethod
    def string(
        cls,
        description: str | None = None,
        *,
        enum: Sequence[str] = (),
        const: str | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
    ) -> JsonSchema:
        if enum and const is not None:
            raise ValueError("string schema cannot declare both enum and const")
        return cls(
            type_name="string",
            description=description,
            enum=tuple(enum),
            const=const,
            min_length=min_length,
            max_length=max_length,
        )

    @classmethod
    def integer(
        cls,
        description: str | None = None,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> JsonSchema:
        return cls(
            type_name="integer",
            description=description,
            minimum=minimum,
            maximum=maximum,
        )

    @classmethod
    def number(cls, description: str | None = None) -> JsonSchema:
        return cls(type_name="number", description=description)

    @classmethod
    def boolean(cls, description: str | None = None) -> JsonSchema:
        return cls(type_name="boolean", description=description)

    @classmethod
    def scalar_union(
        cls,
        *types: JsonScalarType,
        description: str | None = None,
    ) -> JsonSchema:
        unique_types = tuple(dict.fromkeys(types))
        if len(unique_types) < 2:
            raise ValueError("scalar_union requires at least two distinct types")
        return cls(type_name=unique_types, description=description)

    @classmethod
    def object(
        cls,
        properties: Mapping[str, JsonSchema] | None = None,
        *,
        required: Sequence[str] = (),
        description: str | None = None,
        additional_properties: bool | JsonSchema = False,
    ) -> JsonSchema:
        return cls(
            type_name="object",
            description=description,
            properties=properties or {},
            required=tuple(required),
            additional_properties=additional_properties,
        )

    @classmethod
    def open_object(cls, description: str | None = None) -> JsonSchema:
        return cls.object(description=description, additional_properties=True)

    @classmethod
    def array(
        cls,
        items: JsonSchema,
        *,
        description: str | None = None,
        min_items: int | None = None,
        max_items: int | None = None,
    ) -> JsonSchema:
        return cls(
            type_name="array",
            description=description,
            items=items,
            min_items=min_items,
            max_items=max_items,
        )

    def to_dict(self) -> dict[str, object]:
        schema: dict[str, object] = {
            "type": list(self.type_name) if isinstance(self.type_name, tuple) else self.type_name
        }
        self._add_annotations(schema)
        self._add_structure(schema)
        self._add_bounds(schema)
        return schema

    def validate_schema(self) -> None:
        Draft202012Validator.check_schema(self.to_dict())

    def matches(self, value: object) -> bool:
        try:
            Draft202012Validator(self.to_dict()).validate(  # pyright: ignore[reportUnknownMemberType]
                value
            )
        except ValidationError:
            return False
        return True

    def _add_annotations(self, schema: dict[str, object]) -> None:
        if self.description:
            schema["description"] = self.description
        if self.enum:
            schema["enum"] = list(self.enum)
        if self.const is not None:
            schema["const"] = self.const

    def _add_structure(self, schema: dict[str, object]) -> None:
        if self.properties:
            schema["properties"] = {
                name: child.to_dict() for name, child in self.properties.items()
            }
        elif self.type_name == "object":
            schema["properties"] = {}
        if self.required:
            schema["required"] = list(self.required)
        if self.items is not None:
            schema["items"] = self.items.to_dict()
        if self.additional_properties is not None:
            schema["additionalProperties"] = (
                self.additional_properties.to_dict()
                if isinstance(self.additional_properties, JsonSchema)
                else self.additional_properties
            )

    def _add_bounds(self, schema: dict[str, object]) -> None:
        for key, value in (
            ("minimum", self.minimum),
            ("maximum", self.maximum),
            ("minLength", self.min_length),
            ("maxLength", self.max_length),
            ("minItems", self.min_items),
            ("maxItems", self.max_items),
        ):
            if value is not None:
                schema[key] = value

    def _validate_shape(self) -> None:
        if self.properties and self.type_name != "object":
            raise ValueError("properties are only valid for object schemas")
        if self.required and self.type_name != "object":
            raise ValueError("required is only valid for object schemas")
        unknown_required = set(self.required) - set(self.properties)
        if unknown_required:
            names = ", ".join(sorted(unknown_required))
            raise ValueError(f"required properties are not declared: {names}")
        if self.items is not None and self.type_name != "array":
            raise ValueError("items is only valid for array schemas")
        if self.additional_properties is not None and self.type_name != "object":
            raise ValueError("additional_properties is only valid for object schemas")
        if (self.enum or self.const is not None) and self.type_name != "string":
            raise ValueError("enum and const are only valid for string schemas")
        for label, lower, upper in (
            ("numeric", self.minimum, self.maximum),
            ("string length", self.min_length, self.max_length),
            ("array length", self.min_items, self.max_items),
        ):
            if lower is not None and upper is not None and lower > upper:
                raise ValueError(f"{label} minimum cannot exceed maximum")
