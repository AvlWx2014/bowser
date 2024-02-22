from pathlib import Path
from typing import Any, cast

from hamcrest import assert_that, equal_to
from reactivex import from_iterable, zip

from bowser.extensions.rx import observable_background_process

HERE = Path(__file__).parent
DATA = HERE / "data"


def test_observable_background_process():
    """Test the observable_background_process factory.

    This is done by using a known data file and ``cat`` to simulate the background process
    represented by ``observable_background_process``.

    The lines from the known data file are combined with the Observable returned by the
    function under test using the :func:`reactivex.zip` factory function so that lines
    can be compared directly very easily.

    This test case is kept at a reasonable length for unit testsing by using a very small
    data file (2 lines).
    """
    data_file = DATA / "test_observable_background_process.txt"
    with data_file.open("rb") as in_:
        left = from_iterable(line.strip() for line in in_.readlines())
    right = observable_background_process(f"cat {data_file!s}")
    observable = zip(left, right)

    def on_next(zipped: tuple[Any, ...]) -> None:
        # we only zipped 2 observables together, each of them Observable[bytes]
        # so we can expect zipped's actual type to be Tuple[bytes, bytes]
        expected, actual = cast(tuple[bytes, bytes], zipped)
        assert_that(actual, equal_to(expected))

    observable.subscribe(on_next=on_next)
