"""Caption-to-Accessible-Transcript — portable caption cleaning / publishing core.

All logic here is pure Python with no Claude/Cowork dependencies, so the same
code runs locally (driven by a sub-agent) and on a server (driven by an API
call). The LLM is consulted only through the judgment interface (judgment.py).
"""

__version__ = "0.1.0"
