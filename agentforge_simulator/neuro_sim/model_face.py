"""Canned answers for model invocations (ADR-0038 D-5 / FR-09).

A simulated run that reaches a model invocation used to call a real provider: it needed a key, it
spent money, and it returned something different next month. None of those belong in a rehearsal,
and the third is the worst — a scenario whose expected outcome drifts on the provider's schedule is
not a regression test, it is a subscription.

So a model answer is **canned**, keyed by the model reference and a fingerprint of the prompt.

🔴 **Canned, not record-and-replay, and that is a deliberate ceiling.** Record-and-replay would
reproduce a real provider's answers faithfully, which is a better simulation and a much larger
build: a recorder, a store, a redaction pass over whatever the prompts contained. Canned answers
cost a JSON file and buy the two properties a rehearsal actually needs — it is free, and it is the
same answer twice.

**The fingerprint is over the prompt, not the whole request.** A request carries fields that vary
between runs without changing what was asked; keying on all of them would make every lookup a miss
and every rehearsal a loud failure for no reason. A file may also omit the fingerprint entirely,
which means "this model answers this way whatever it is asked" — the common case while a scenario
is being written.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from typing import Optional

#: Request fields that carry the question. Anything else is metadata and is not fingerprinted.
PROMPT_FIELDS = ("prompt", "input", "question", "text")


class ModelResponseError(ValueError):
    """A responses file that cannot be read, or that says two contradictory things.

    Distinct from "no file": absent is legal and means "this hub cans no model answers", so a
    scenario that has not configured one still starts. Unreadable is not -- a malformed file
    silently treated as empty would report "nothing canned" for a file full of answers.
    """


def prompt_fingerprint(payload: Any) -> str:
    """A stable short hash of what was asked.

    Reads the first :data:`PROMPT_FIELDS` key present; falls back to the whole payload, sorted, so
    a request that names its question something else still fingerprints deterministically rather
    than collapsing every call onto one key.
    """
    if isinstance(payload, dict):
        for field in PROMPT_FIELDS:
            if field in payload:
                material = json.dumps(payload[field], sort_keys=True, default=str)
                break
        else:
            material = json.dumps(payload, sort_keys=True, default=str)
    else:
        material = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


class ModelResponses:
    """Resolves ``(model_ref, prompt)`` to a canned answer.

    Resolution is most-specific-first, the same chain shape :class:`~neuro_sim.fixtures.FixtureStore`
    uses, so an author who has learned one has learned both::

        (model_ref, fingerprint)  ->  (model_ref, any prompt)  ->  nothing canned
    """

    def __init__(self, entries: Optional[list] = None) -> None:
        self._by_key: dict = {}
        for entry in entries or []:
            if not isinstance(entry, dict):
                raise ModelResponseError(f"a model response is {type(entry).__name__}, not an object")
            unknown = sorted(set(entry) - {"model_ref", "prompt_fingerprint", "returns", "description"})
            if unknown:
                raise ModelResponseError(f"model response has unrecognised key(s) {unknown}")
            model_ref = str(entry.get("model_ref") or "")
            if not model_ref:
                raise ModelResponseError("a model response names no model_ref")
            if "returns" not in entry:
                raise ModelResponseError(f"model response for '{model_ref}' declares no `returns`")
            key = (model_ref, str(entry.get("prompt_fingerprint") or ""))
            if key in self._by_key:
                raise ModelResponseError(
                    f"two model responses share the key {key}. Refused rather than resolved by "
                    "order -- picking a winner silently is how an author edits the answer that is "
                    "not being served and concludes the sim ignores edits."
                )
            self._by_key[key] = entry["returns"]

    def entries(self) -> tuple:
        """``((model_ref, fingerprint), returns)`` pairs -- what this face was built from.

        Exists so a caller can merge two faces without reaching into private state; the merge then
        goes back through ``__init__``, which is what refuses a duplicate key.
        """
        return tuple(self._by_key.items())

    def model_refs(self) -> tuple:
        """Every model this face can answer for. Named in a miss so it says what IS canned."""
        return tuple(sorted({model_ref for model_ref, _ in self._by_key}))

    def answer(self, model_ref: str, payload: Any) -> Optional[Any]:
        """The canned answer for this call, or ``None`` when nothing is configured for it."""
        fingerprint = prompt_fingerprint(payload)
        for key in ((model_ref, fingerprint), (model_ref, "")):
            if key in self._by_key:
                return self._by_key[key]
        return None


def load_model_responses(path: Path) -> ModelResponses:
    """Read a responses file, or an empty face when it does not exist."""
    path = Path(path)
    if not path.exists():
        return ModelResponses()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelResponseError(f"model responses file '{path}' is unreadable: {exc}") from exc
    entries = loaded.get("responses") if isinstance(loaded, dict) else loaded
    if not isinstance(entries, list):
        raise ModelResponseError(
            f"model responses file '{path}' must hold a list of responses, or an object with a "
            "'responses' list"
        )
    return ModelResponses(entries)
