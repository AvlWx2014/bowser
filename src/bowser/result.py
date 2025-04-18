from abc import ABC
from typing import TypeVar, Generic, Never, Any, cast

from attrs import frozen

Out = TypeVar("Out", covariant=True)
Nothing = Never


class Result(ABC, Generic[Out]):
    def __init__(self, value: Any | None) -> None:
        """Do not call the constructor directly from client code.

        Instead, use the factory methods Result.success and Result.failure.
        """
        self._value = value

    @frozen
    class _Failure:
        exc: Exception

        def __str__(self) -> str:
            return str(self.exc)

    @classmethod
    def success(cls, value: Out) -> "Result[Out]":
        return Result(value)

    @classmethod
    def failure(cls, exc: Exception) -> "Result[Out]":
        return Result(Result._Failure(exc))

    @property
    def is_success(self) -> bool:
        return not isinstance(self._value, self._Failure)

    @property
    def is_failure(self) -> bool:
        return isinstance(self._value, self._Failure)

    def get_or_none(self) -> Out | None:
        return cast(Out, self._value) if self.is_success else None

    def exception_or_none(self) -> Exception | None:
        return self._value.exc if self.is_failure else None
