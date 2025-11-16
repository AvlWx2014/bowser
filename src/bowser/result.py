from typing import Any, Generic, Never, TypeVar, cast

from attrs import frozen

T = TypeVar("T")
Out = TypeVar("Out", covariant=True)
Nothing = Never


class Result(Generic[Out]):
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
        return Result(cast(Any, Result._Failure(exc)))

    @property
    def is_success(self) -> bool:
        return not isinstance(self._value, self._Failure)

    @property
    def is_failure(self) -> bool:
        return isinstance(self._value, self._Failure)

    def get(self) -> Out:
        if self.is_failure:
            exc = self.exception()
            raise exc
        return cast(Out, self._value)

    def get_or_none(self) -> Out | None:
        return cast(Out, self._value) if self.is_success else None

    def exception(self) -> Exception:
        if self.is_failure:
            return cast(Result._Failure, self._value).exc
        raise TypeError("No Exception for a success Result.")

    def exception_or_none(self) -> Exception | None:
        return cast(Result._Failure, self._value).exc if self.is_failure else None
