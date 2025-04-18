from abc import ABC
from typing import Any, Generic, Never, TypeVar, cast

from attrs import frozen

T = TypeVar("T")
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

    @classmethod
    def success(cls, value: T) -> "Result[T]":
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
        # Ignore: mypy union-attr
        # Reason: self.is_failure returns True implies isinstance(self._value, Result._Failure)
        #   which has the attribute exc. I could inline the isinstance call here to
        #   help mypy, but why not use the property that's made for this.
        return self._value.exc if self.is_failure else None  # type: ignore[union-attr]
