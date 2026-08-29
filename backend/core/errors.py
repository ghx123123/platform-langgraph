class AppError(Exception):
    def __init__(self, message: str, code: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(f"{resource} not found: {resource_id}", "NOT_FOUND", 404)


class ConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "CONFLICT", 409)
