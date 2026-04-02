from typing import Union, List, Dict
from pydantic import BaseModel

class TaskInput(BaseModel):
    task: str = "summarize"
    input: Union[str, List[str]] = "How is it going?"
    options: Dict = {}
