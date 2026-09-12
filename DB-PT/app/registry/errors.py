"""Errors that the API turns into consistent JSON responses."""

from __future__ import annotations


class FormError(Exception):
    """Validation problems tied to specific form fields."""

    def __init__(
        self,
        fields: dict[str, str],
        message: str = "Some fields need attention.",
        status_code: int = 422,
    ) -> None:
        super().__init__(message)
        self.fields = fields
        self.message = message
        self.status_code = status_code
