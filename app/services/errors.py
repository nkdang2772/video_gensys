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

