from pydantic import BaseModel


class ModelConnectionTestView(BaseModel):
    connected: bool
