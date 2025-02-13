import logging
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from reactivex import Observable

LOGGER = logging.getLogger("bowser")


_T_out = TypeVar("_T_out", covariant=True)


class ObservableTransformer(ABC, Generic[_T_out]):
    @abstractmethod
    def __call__(self, upstream: Observable[_T_out]) -> Observable[_T_out]:
        raise NotImplementedError()
