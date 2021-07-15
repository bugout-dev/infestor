from pydantic import BaseModel
from typing import List


class ReporterCall(BaseModel):
    call_type: str
    lineno: int
    scope_stack: str


class ReporterDecorator(BaseModel):
    decorator_type: str
    lineno: int
    scope_stack: str


class ReporterDecoratorCandidate(BaseModel):
    scope_stack: str
    lineno: int
