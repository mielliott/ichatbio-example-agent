from typing import Optional, Self, Iterator

import geojson
from instructor import from_openai, retry, AsyncInstructor
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic import Field, model_validator

from util import JSON

Path = list[str]


class GiveUp(BaseModel):
    reason: str


class PropertyPaths(BaseModel):
    latitude: Path
    longitude: Path
    color_by: Optional[Path] = Field(
        None,
        description="The property to use to determine how the points will be colored on a map.",
    )


def trace_path_in_schema(schema: dict, target_path: list[str], index=0):
    if index < len(target_path):
        match schema.get("type"):
            case "object":
                next_property = schema["properties"].get(target_path[index])
                if next_property:
                    return trace_path_in_schema(next_property, target_path, index + 1)
            case "array":
                return trace_path_in_schema(schema["items"], target_path, index)

    return target_path[:index], schema


def make_validated_response_model(
    schema: dict, allowed_types=("integer", "number", "string")
):
    def validate_path(path: list[str]):
        trace, terminal_schema = trace_path_in_schema(schema, path)

        if trace != path:
            terminal_type = terminal_schema["type"]
            raise ValueError(
                f'Path does not exist in provided schema. Tip: {terminal_type} at path {trace} does not contain a property named "{path[len(trace)]}"'
            )

        if terminal_schema["type"] not in allowed_types:
            terminal_type = terminal_schema["type"]
            raise ValueError(
                f'Path {trace} in the schema has invalid type "{terminal_type}"; expected {allowed_types}'
            )

        return path

    class ResponseModel(BaseModel):
        response: GiveUp | PropertyPaths

        @model_validator(mode="after")
        def validate(self) -> Self:
            match self.response:
                case PropertyPaths() as paths:
                    validate_path(paths.latitude)
                    validate_path(paths.longitude)
                    if paths.color_by:
                        validate_path(paths.color_by)
            return self

    return ResponseModel


SYSTEM_PROMPT = """\
Your task is to look at a JSON schema and map paths in the schema to variables that the user is interested in, as 
defined by a provided data model.

A path is a list of property names that point to a scalar property. For example,

latitude: ["records", "data", "geo", "latitude"]
"""


async def select_properties(request: str, schema: dict):
    model = make_validated_response_model(schema)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Here is the schema of my data:\n\n{schema}",
        },
        {"role": "user", "content": request},
    ]

    client: AsyncInstructor = from_openai(AsyncOpenAI())
    try:
        generation = await client.chat.completions.create(
            model="gpt-4.1",
            temperature=0,
            response_model=model,
            messages=messages,
            max_retries=5,
        )
    except retry.InstructorRetryException as e:
        raise

    return generation.response


def read_path(content: JSON, path: list[str]) -> Iterator[float]:
    match content:
        case list() as records:
            for record in records:
                yield from read_path(record, path)
        case dict() as record:
            next_property = record.get(path[0])
            yield from read_path(next_property, path[1:])
        case _ as scalar if len(path) == 0:
            if scalar is None:
                yield None
            else:
                try:
                    yield float(scalar)
                except ValueError:
                    yield None


def render_points_as_geojson(
    coordinates: list[(float, float)], values: list[float | int | str] = None
) -> geojson.FeatureCollection:
    if values is None:
        values = (1.0 for _ in coordinates)

    geo = geojson.FeatureCollection(
        [
            geojson.Feature(
                id=i, geometry=geojson.Point((lon, lat)), properties={"value": value}
            )
            for i, ((lat, lon), value) in enumerate(zip(coordinates, values))
            if lat is not None and lon is not None
        ]
    )

    return geo
