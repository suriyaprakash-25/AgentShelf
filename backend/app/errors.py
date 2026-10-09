"""Stable errors shared by REST and MCP."""


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)

    def payload(self):
        """Return the public error envelope."""
        return {"error": {"code": self.code, "message": self.message}}
