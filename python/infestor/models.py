from pydantic import BaseModel
from typing import List

# class.func.innerfn
class ReporterCall(BaseModel):
    call_type: str
    lineno: int
    scope_stack: List[str]


class ReporterDecorator(BaseModel):
    decorator_type: str
    lineno: int
    scope_stack: List[str]


class ReporterDecoratorCandidate(BaseModel):
    scope_stack: List[str]
    lineno: int
