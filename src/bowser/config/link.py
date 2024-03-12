from abc import ABC, abstractmethod
from re import Pattern, sub
from typing import Literal

from pydantic import BaseModel, Field

from bowser.extensions.pydantic import Literally


class LinkTargetMatcher(BaseModel, ABC, frozen=True):
    kind: str
    """A convenient discriminator and label for printing or log messages.

    This should be overridden by subclasses.
    """

    @abstractmethod
    def matches(self, value: str) -> bool:
        """Determine if ``value`` is valid according to the rules of this matcher.

        Actual match logic is dependent on the concrete subclass.
        """
        raise NotImplementedError()


class RegexLinkTargetMatcher(LinkTargetMatcher, frozen=True):
    """Uses ``pattern`` to determine if a string is a valid link target.

    Notes:
        Determining a match uses :py:func:`re.search`, rather than a strict match.
    """

    pattern: Pattern[str]
    kind: Literal["RegexMatch"] = Literally("RegexMatch")

    def matches(self, value: str) -> bool:
        """Determine if ``value`` matches ``pattern`` using :py:func:`re.Pattern.search`."""
        return bool(self.pattern.search(value))


class LiteralLinkTargetMatcher(LinkTargetMatcher, frozen=True):
    """Uses ``literal`` to determine if a string is a valid link target.

    Notes:
        This is done using string equality.
    """

    literal: str
    kind: Literal["Literal"] = Literally("Literal")

    def matches(self, value: str) -> bool:
        """Determine if ``value`` matches ``literal`` through string equality."""
        return value == self.literal


LinkTargetMatcherT = LiteralLinkTargetMatcher | RegexLinkTargetMatcher


class Link(BaseModel, frozen=True):
    """Represents a symbolic-like link named ``name`` pointing to ``target``."""

    target: LinkTargetMatcherT = Field(discriminator="kind")
    """The link target."""
    name: str
    """The link name."""

    def substitute(self, string: str) -> str:
        """Return ``string`` with whatever matches ``target`` replaced by ``name``.

        Examples:
            >>> from bowser.config.link import LiteralLinkTargetMatcher, RegexLinkTargetMatcher
            >>> link = Link(target=LiteralLinkTargetMatcher(literal="some/prefix"), name="latest")
            >>> object_key = "some/prefix/20240311T123456/report.json"
            >>> link_key = link.substitute(object_key)
            >>> assert link_key == "latest/20240311T123456/report.json"
            >>> link = Link(target=RegexLinkTargetMatcher(pattern="\\d{8}T\\d{6}"), name="latest")
            >>> link_key = link.substitute(object_key)
            >>> assert link_key == "some/prefix/latest/report.json"

        ValueError: If nothing matches ``target``.
        """
        if not self.target.matches(string):
            raise ValueError(f"'{string}' does not match link target.")
        match self.target:
            case LiteralLinkTargetMatcher():
                substitution = sub(self.target.literal, self.name, string)
            case RegexLinkTargetMatcher():
                substitution = self.target.pattern.sub(self.name, string)
            case _:
                raise RuntimeError(
                    "Exhaustive match on LinkTargetMatcherT filed to match."
                    f"Unknown match type: '{type(self.target)}'"
                )
        return substitution
