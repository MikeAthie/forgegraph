# Data Transfer Objects
#
# Used to transfer data across layer boundaries.

from application.dto.auth import (
    LoginInput,
    RegisterInput,
    TokenOutput,
    UserOutput,
)
from application.dto.graph import (
    CreateGraphInput,
    CreateGraphVersionInput,
    GraphOutput,
    GraphVersionOutput,
    UpdateGraphInput,
)
from application.dto.prompt import (
    CreatePromptInput,
    PromptOutput,
    PublishPromptInput,
    UpdatePromptInput,
)
from application.dto.run import (
    NodeRunOutput,
    ResumeRunInput,
    RunOutput,
    StartRunInput,
)

__all__ = [
    # Auth
    "RegisterInput",
    "LoginInput",
    "UserOutput",
    "TokenOutput",
    # Graph
    "CreateGraphInput",
    "UpdateGraphInput",
    "GraphOutput",
    "CreateGraphVersionInput",
    "GraphVersionOutput",
    # Prompt
    "CreatePromptInput",
    "UpdatePromptInput",
    "PublishPromptInput",
    "PromptOutput",
    # Run
    "StartRunInput",
    "ResumeRunInput",
    "RunOutput",
    "NodeRunOutput",
]
