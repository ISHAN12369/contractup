"""Messages in this module are safe to return to clients."""


class ServiceError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


class InvalidDocument(ServiceError):
    def __init__(self, message: str = "The document could not be parsed safely."):
        super().__init__(422, message)


class MissingDocument(ServiceError):
    def __init__(self) -> None:
        super().__init__(404, "Document expired or unavailable. Please upload it again.")


class ModelFailure(ServiceError):
    def __init__(self) -> None:
        super().__init__(502, "The analysis provider could not return a validated response. Please retry.")
