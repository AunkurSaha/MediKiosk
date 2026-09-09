from .common import APIModel


class User(APIModel):
    id: str
    name: str
    role: str
    is_active: bool
