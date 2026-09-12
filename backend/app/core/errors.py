class WorkflowError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        self.code = code
        self.message = message
        self.status = status


class ProviderUnavailable(Exception):
    pass


class ProviderFailure(Exception):
    """Only application-owned reason codes cross the vendor boundary."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)
