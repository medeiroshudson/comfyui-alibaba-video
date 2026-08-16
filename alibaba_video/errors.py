from __future__ import annotations


class AlibabaVideoError(RuntimeError):
    """Base class for safe, user-facing provider errors."""


class AlibabaAuthenticationError(AlibabaVideoError):
    pass


class AlibabaQuotaError(AlibabaVideoError):
    pass


class AlibabaValidationError(AlibabaVideoError):
    pass


class AlibabaModerationError(AlibabaVideoError):
    pass


class AlibabaTransientError(AlibabaVideoError):
    pass


class AlibabaJobFailedError(AlibabaVideoError):
    pass


class AlibabaTimeoutError(AlibabaVideoError):
    pass


class AlibabaArtifactError(AlibabaVideoError):
    pass
