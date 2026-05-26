import json
import time
from pathlib import Path
from typing import Generic, TypeVar

import structlog
from pydantic import BaseModel

from app.integrations.anthropic_client import create_message
from app.integrations.langfuse_client import langfuse

logger = structlog.get_logger()

TIn = TypeVar("TIn", bound=BaseModel)
TOut = TypeVar("TOut", bound=BaseModel)

PROMPTS_DIR = Path(__file__).parent / "prompts"


class Agent(Generic[TIn, TOut]):
    """Base class for all LLM agents.

    Each agent has a single `run()` method that:
    1. Loads its prompt template
    2. Calls the Anthropic API with tool-use for structured output
    3. Validates the output via Pydantic
    4. Wraps everything in a Langfuse trace span
    """

    name: str = ""
    model: str = ""
    prompt_file: str = ""
    output_schema: type[BaseModel]
    max_tokens: int = 4096

    def _load_prompt(self) -> str:
        """Load the markdown prompt from disk."""
        path = PROMPTS_DIR / self.prompt_file
        return path.read_text(encoding="utf-8")

    def _tool_definition(self) -> dict:
        """Build the Anthropic tool definition from the Pydantic schema."""
        schema = self.output_schema.model_json_schema()
        return {
            "name": self.output_schema.__name__,
            "description": f"Structured output for {self.name}",
            "input_schema": schema,
        }

    def _build_messages(self, input_data: TIn, **kwargs: object) -> list[dict]:
        """Build the messages array. Override for multimodal agents."""
        system_prompt = self._load_prompt()
        return [
            {"role": "user", "content": f"{system_prompt}\n\n---\n\nDocument data:\n{input_data.model_dump_json(indent=2)}"},
        ]

    async def run(self, input_data: TIn, *, trace_id: str | None = None, **kwargs: object) -> TOut:
        """Execute the agent: prompt → LLM → validate → return."""
        trace = None
        span = None

        if trace_id and langfuse.enabled:
            try:
                trace = langfuse.trace(id=trace_id, name=f"pipeline-{trace_id}")
                span = trace.span(name=self.name, input=input_data.model_dump())
            except (AttributeError, Exception) as exc:
                logger.debug("langfuse_tracing_unavailable", error=str(exc))

        start = time.monotonic()

        try:
            messages = self._build_messages(input_data, **kwargs)
            response = await create_message(
                model=self.model,
                max_tokens=self.max_tokens,
                tools=[self._tool_definition()],
                tool_choice={"type": "tool", "name": self.output_schema.__name__},
                messages=messages,
            )

            # Extract tool use block
            tool_use = None
            for block in response.content:
                if block.type == "tool_use":
                    tool_use = block
                    break

            if tool_use is None:
                raise ValueError(f"Agent {self.name}: no tool_use block in response")

            result = self.output_schema.model_validate(tool_use.input)
            duration_ms = int((time.monotonic() - start) * 1000)

            logger.info(
                "agent_success",
                agent=self.name,
                model=self.model,
                duration_ms=duration_ms,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

            if span:
                span.end(
                    output=result.model_dump(),
                    metadata={
                        "duration_ms": duration_ms,
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                    },
                )

            return result  # type: ignore[return-value]

        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.exception("agent_error", agent=self.name, duration_ms=duration_ms)
            if span:
                span.end(level="ERROR", status_message=str(exc))
            raise
