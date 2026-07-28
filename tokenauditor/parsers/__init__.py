from dataclasses import dataclass, field


@dataclass
class Turn:
    index: int
    total_input: int = 0
    cache_creation: int = 0
    cache_read: int = 0
    output: int = 0
    added_user_text: int = 0
    added_tool_results: int = 0
    tool_results: list = field(default_factory=list)  # (tool_name:str, tokens:int)
    tool_calls: list = field(default_factory=list)    # (tool_name:str, input_hash:str)


@dataclass
class Session:
    format: str
    turns: list = field(default_factory=list)
    categories: dict = field(default_factory=dict)
    inferred_prefix: int = 0
    prefix_inferred: bool = False
    reported_total_input: int = 0
    reported_total_output: int = 0
    model: str | None = None