from bowser.result import Result


def test_success_construction() -> None:
    success = Result[str].success("Success")
    assert success.is_success
    assert not success.is_failure
    assert success.get_or_none() is not None
    assert success.get_or_none() == "Success"
    assert success.exception_or_none() is None


def test_failure_construction() -> None:
    err = RuntimeError("Failure")
    failure = Result[str].failure(err)
    assert failure.is_failure
    assert not failure.is_success
    assert failure.get_or_none() is None
    assert failure.exception_or_none() is not None
    assert failure.exception_or_none() is err
