class DomainError(Exception):
    """Base class for expected domain failures."""


class SeriesNotFoundError(DomainError):
    pass


class DuplicateSeriesSlugError(DomainError):
    pass


class EpisodeCreationError(DomainError):
    pass


class ReferencePinError(EpisodeCreationError):
    pass


class ReferenceNotFoundError(DomainError):
    pass


class DuplicateReferenceSlugError(DomainError):
    pass


class ReferenceVersionError(DomainError):
    pass


class ImmutableReferenceVersionError(ReferenceVersionError):
    pass


class ShotNotFoundError(DomainError):
    pass


class DuplicateShotIdError(DomainError):
    pass
