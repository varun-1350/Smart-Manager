from pydantic import BaseModel, ConfigDict, Field, StrictBool

class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")        # unknown fields are errors, not ignored


class MessageIn(_Body):
    text: str = Field(max_length=2000)


class ApproveIn(_Body):
    turn_id: str = Field(min_length=1, max_length=64)
    digest: str = Field(min_length=64, max_length=64)    # a SHA-256 hex digest


class RejectIn(_Body):
    turn_id: str = Field(min_length=1, max_length=64)


class UndoIn(_Body):
    confirm: bool


class RunIn(_Body):
    run_id: str = Field(min_length=1, max_length=200)


class RunUndoIn(RunIn):
    confirm: bool

class ClearIn(_Body):
    confirm: bool


class SettingIn(_Body):
    key: str = Field(min_length=1, max_length=64)
    value: StrictBool           # a real true/false, never "yes" or 1