"""The sim's fixture manifest and store: roles, their answers, and the resolution chain.

**A generic capability of the simulator, not a NeuroEdge feature.** Any project driving this
simulator has the same problem: one process standing in for several external systems, each of which
must be able to answer the *same* question differently depending on who is asking. Three dealer
branches answering "do you have capacity?" identically makes "find the branch with room"
unexercisable, and that is true of any multi-party scenario, not just one product's.

**The resolution chain**, most specific wins::

    (role, caller, capability) + matching `matches`   the branch's answer about this thing
    (role, caller, capability)                        the branch's answer about anything
    (role, capability)         + matching `matches`   anyone's answer about this thing
    (role, capability)                                anyone's answer about anything
    nothing configured                                -> a loud 404

``caller`` empty means *shared fact*: the health of a battery does not depend on who asks, so its
fixture is authored once. Authoring per-caller entries yields the differing answer.

``matches`` is the same idea one axis over: ``caller`` distinguishes **who is asking**, ``matches``
distinguishes **what they are asking about**. A capability declaring ``input_schema={"sku": ...}``
is a per-SKU lookup, and without this the sim answered every SKU -- real, invented or absent --
with one number, so a rehearsal could not tell a hit from a miss and "find the SKU that is short"
was unexercisable. **Omitting ``matches`` is the catch-all and is exactly the old behaviour**, so
bundles authored before this field keep working unchanged.

🔴 **Fix the receiver, not the caller.** The transport already sends the argument and already
refuses a call that omits a required one; nothing was wrong on the asking side. A fixture stands in
for a field endpoint, so it has to discriminate the way that endpoint does -- otherwise the
simulated run proves a behaviour the real one does not have, which is the one thing a rehearsal
must never do. Leaving out a catch-all is how you get the field endpoint's *other* honest answer:
an unknown key 404s instead of being quietly served someone else's data.

🔴 **An unconfigured route resolves to ``None``, and callers must not turn that into ``{}``.** "This
role was never given a fixture for this capability" and "this capability returns an empty object"
are different facts. The server answers the first with a loud 404 (see :mod:`fixture_server`) --
never a silent 200, which would teach a green run to mean nothing.

🔴 **Plain dataclasses, deliberately.** This module validates its own input rather than importing a
schema library, because the simulator ships with a split, minimal dependency set (see
``requirements*.txt``: transports, input decoders and PyYAML for bundles, no schema library) and a
host that merely runs a fixture server should not inherit a validation framework to do it. The
checks below are the ones that actually prevent a silently-wrong manifest; they are short because
there are few of them.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Optional

#: A manifest's filename by convention, beside whatever the host treats as its scenario root.
DEFAULT_MANIFEST_FILENAME = "sim_manifest.json"

#: Names a role may not take -- the server routes each of these path prefixes to a face of its own.
#: Duplicated from ``stub_server.MODEL_PATH_PREFIX`` / ``mcp_face.MCP_PATH_PREFIX`` rather than
#: imported, because importing the server here would make the fixture model depend on the thing that
#: serves it. The spellings are pinned equal by a test, the same treatment the caller-header
#: constant gets across the installer seam.
RESERVED_ROLE_PREFIXES = frozenset({"models", "mcp"})


def comparable(value: Any) -> str:
    """One spelling for a request argument, whichever wire it arrived on.

    A read carries its arguments on a query string, so everything is text; a write carries JSON, so
    ``bool``/``int``/``float`` survive. An entry's ``matches`` is authored once and must select the
    same call either way, so both sides are reduced here before comparison.

    Two normalisations beyond ``str()``, each closing a case where the raw form differs only by
    transport:

    * **Booleans take their JSON spelling** -- ``str(True)`` is ``"True"`` but a query string
      carries ``"true"``, so an authored ``{"active": true}`` would have matched a POST and
      silently missed the identical GET. That is exactly the asymmetry this function exists to
      remove, and it is easy to miss because the shipped capabilities all match on string ids.
    * **A float that is a whole number takes its integer spelling** -- ``14.0`` and ``14`` are the
      same horizon, and JSON gives no way for an author to insist on one.

    Deliberately NOT a general coercion: ``"01"`` and ``1`` stay different, because a part number
    with a leading zero is a different part number, and guessing otherwise would silently answer
    about the wrong thing.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class ManifestError(ValueError):
    """A manifest that cannot be read, or that says two contradictory things.

    Distinct from "no manifest": absent is legal and means "no roles configured", so a scenario that
    has never been set up still starts. What is *not* legal is an unreadable one -- a malformed file
    silently treated as empty would report "no fixtures configured" for a file full of them.
    """


@dataclass(frozen=True)
class FaultConfig:
    """What can go wrong on purpose.

    🔴 **The reason fault injection is worth modelling at all**: a fixture that can only answer
    correctly makes every simulated run a happy path. A timeout, a 5xx and a malformed payload are
    the three failures an integration actually meets, and a rehearsal that cannot produce them is
    not a rehearsal.
    """

    #: Seconds to stall before answering. Whether that *becomes* a timeout is decided by the
    #: caller's own timeout configuration, which is the point: it exercises the caller's wiring.
    delay_seconds: float = 0.0
    #: Fraction of calls answered ``500``. Drawn from the run's seeded RNG, so a flaky role is
    #: exactly as flaky on every run with the same seed.
    error_rate: float = 0.0
    #: Answer with a body that is not the declared shape, to exercise the consumer's parsing.
    malformed: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.error_rate <= 1.0:
            raise ManifestError(
                f"error_rate {self.error_rate} is not a fraction between 0 and 1. A value outside "
                "that range reads as a percentage and behaves as 'always' or 'never'."
            )
        if self.delay_seconds < 0:
            raise ManifestError(f"delay_seconds {self.delay_seconds} is negative")

    @classmethod
    def from_dict(cls, raw: Any) -> Optional[FaultConfig]:
        """Decode a ``faults`` block. ``None``/absent means "nothing goes wrong for this role"."""
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ManifestError(f"faults is {type(raw).__name__}, not an object")
        unknown = sorted(set(raw) - {"delay_seconds", "error_rate", "malformed"})
        if unknown:
            raise ManifestError(f"faults has unrecognised keys {unknown} -- a misspelled one injects nothing")
        return cls(
            delay_seconds=float(raw.get("delay_seconds", 0.0)),
            error_rate=float(raw.get("error_rate", 0.0)),
            malformed=bool(raw.get("malformed", False)),
        )


@dataclass(frozen=True)
class FixtureEntry:
    """One answer, scoped by the resolution key.

    ``caller`` empty means the entry answers for everyone asking this role -- the shared-fact
    reading. A non-empty ``caller`` is the differing one.

    ``matches`` scopes the entry by what was *asked*, which is the second half of the same idea:
    ``caller`` distinguishes **who** is asking, ``matches`` distinguishes **what about**.
    """

    capability: str
    caller: str = ""
    #: The answer. 🔴 Exactly one of this or :attr:`sequence` -- see :meth:`__post_init__`.
    returns: Optional[dict] = None
    #: Successive answers across calls, cycling when exhausted. This is what makes "the branch is
    #: full on the second ask" expressible; a single ``returns`` answers identically forever.
    sequence: Optional[list] = None
    faults: Optional[FaultConfig] = None
    #: Request arguments this entry answers for, e.g. ``{"sku": "REG-110V"}``. ``None``/absent is
    #: the **catch-all**: it answers whatever it is asked, which is exactly how every entry behaved
    #: before this field existed, so an authored bundle keeps working untouched.
    #:
    #: 🔴 **Why this belongs on the receiver.** A capability declaring ``input_schema={"sku": ...}``
    #: is a per-SKU lookup, and a fixture that ignores the argument answers 3,120 units for every
    #: SKU ever asked about -- including one that does not exist. The caller was never the problem:
    #: the transport already sends the argument and already refuses a call that omits a required
    #: one. The stand-in for a field endpoint has to discriminate the way the field endpoint does,
    #: or the rehearsal proves a behaviour production does not have.
    matches: Optional[dict] = None

    def __post_init__(self) -> None:
        if not self.capability:
            raise ManifestError("a fixture names no capability")
        if self.matches is not None:
            if not isinstance(self.matches, dict) or not self.matches:
                raise ManifestError(
                    f"fixture for '{self.capability}' declares a `matches` that is not a non-empty "
                    "object. An empty one would read as 'matches nothing' while behaving as "
                    "'matches everything', which is the catch-all -- omit the key to mean that."
                )
            for name in self.matches:
                if not isinstance(name, str) or not name:
                    raise ManifestError(f"fixture for '{self.capability}' has a `matches` key that is not a name")
        if (self.returns is None) == (self.sequence is None):
            both = "both `returns` and `sequence`" if self.returns is not None else "neither `returns` nor `sequence`"
            raise ManifestError(
                f"fixture for '{self.capability}' declares {both}; exactly "
                "one states the answer. Refused rather than resolved by precedence -- picking a "
                "winner silently is how an author edits the value that is not being served and "
                "concludes the sim ignores edits."
            )
        if self.sequence is not None and not self.sequence:
            raise ManifestError(f"fixture for '{self.capability}' declares an empty `sequence`, which answers nothing")

    @property
    def specificity(self) -> int:
        """How many request arguments this entry constrains. ``0`` is the catch-all."""
        return len(self.matches or {})

    @property
    def signature(self) -> tuple:
        """This entry's identity within its ``(role, caller, capability)`` scope.

        Two entries constraining the same arguments to the same values are the same entry; they
        must not both be held, and must not share a ``sequence`` counter with a *differing* one.
        Built from :func:`comparable` so duplicate detection agrees with matching -- otherwise
        ``true`` and ``"true"`` would be refused as duplicates by one and treated as distinct by
        the other, or the reverse.
        """
        return tuple(sorted((key, comparable(value)) for key, value in (self.matches or {}).items()))

    def selects(self, inputs: Optional[dict]) -> bool:
        """Whether this entry answers a call carrying ``inputs``.

        🔴 **Compared as text, deliberately.** A query string is the wire for a read
        (``?sku=REG-110V``), so every argument arrives as ``str`` however it was declared -- while
        a write's JSON body preserves ``int``/``bool``. Comparing values raw would make
        ``matches: {quantity_units: 500}`` match a POST and silently miss the identical GET, which
        is a difference in the *transport*, not in what was asked. Author values as they read.
        """
        if not self.matches:
            return True  # the catch-all: answers whatever it is asked
        supplied = inputs or {}
        return all(
            name in supplied and comparable(supplied[name]) == comparable(value)
            for name, value in self.matches.items()
        )

    @classmethod
    def from_dict(cls, raw: Any) -> FixtureEntry:
        if not isinstance(raw, dict):
            raise ManifestError(f"a fixture is {type(raw).__name__}, not an object")
        unknown = sorted(set(raw) - {"capability", "caller", "returns", "sequence", "faults", "matches"})
        if unknown:
            raise ManifestError(f"fixture has unrecognised keys {unknown}")
        return cls(
            capability=str(raw.get("capability", "")),
            caller=str(raw.get("caller", "")),
            returns=raw.get("returns"),
            sequence=raw.get("sequence"),
            faults=FaultConfig.from_dict(raw.get("faults")),
            matches=raw.get("matches"),
        )


@dataclass(frozen=True)
class SimRole:
    """One system the sim plays -- a dealer DMS, an ERP, a telematics feed, a map POI server.

    One process, many roles, routed by path prefix. A role is a path segment rather than a port so
    that pointing a whole deployment at the sim stays one address.
    """

    id: str
    description: str = ""
    fixtures: tuple = ()
    #: Faults applied to every capability of this role unless a fixture overrides them.
    faults: Optional[FaultConfig] = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ManifestError("a role has no id")
        if self.id in RESERVED_ROLE_PREFIXES:
            # 🔴 Refused at load, not resolved by priority order. The server checks each dedicated
            # face before the fixture scheme, so a role named `models` or `mcp` would have every one
            # of its capabilities swallowed -- answering that face's own miss for a fixture the
            # author can see in their own file. Silent shadowing is exactly what the duplicate-key
            # refusal below and the loud-404 rule exist to prevent; a reserved name deserves the
            # same treatment.
            raise ManifestError(
                f"role id '{self.id}' is reserved: the server routes that path prefix to a face of "
                f"its own, so this role's capabilities would be unreachable. Reserved: "
                f"{sorted(RESERVED_ROLE_PREFIXES)}. Rename the role."
            )

    @classmethod
    def from_dict(cls, raw: Any) -> SimRole:
        if not isinstance(raw, dict):
            raise ManifestError(f"a role is {type(raw).__name__}, not an object")
        unknown = sorted(set(raw) - {"id", "description", "fixtures", "faults"})
        if unknown:
            raise ManifestError(f"role has unrecognised keys {unknown}")
        return cls(
            id=str(raw.get("id", "")),
            description=str(raw.get("description", "")),
            fixtures=tuple(FixtureEntry.from_dict(entry) for entry in raw.get("fixtures", ())),
            faults=FaultConfig.from_dict(raw.get("faults")),
        )


@dataclass(frozen=True)
class SimManifest:
    """A scenario's simulated world: which roles are live, and what each answers."""

    scenario: str = ""
    roles: tuple = ()

    @classmethod
    def from_dict(cls, raw: Any) -> SimManifest:
        if not isinstance(raw, dict):
            raise ManifestError(f"a manifest is {type(raw).__name__}, not an object")
        unknown = sorted(set(raw) - {"scenario", "roles"})
        if unknown:
            raise ManifestError(f"manifest has unrecognised keys {unknown}")
        return cls(
            scenario=str(raw.get("scenario", "")),
            roles=tuple(SimRole.from_dict(role) for role in raw.get("roles", ())),
        )


class FixtureStore:
    """Resolves ``(role, caller, capability)`` to an answer, and serves it at run time.

    🔴 **Mutable on purpose.** :meth:`upsert` takes effect on the next call, with no rebuild of
    whatever is driving the simulator. A fixture the operator has to regenerate to change is a
    fixture they will stop changing.
    """

    def __init__(self, manifest: Optional[SimManifest] = None) -> None:
        self._manifest = manifest or SimManifest()
        # 🔴 `answer` read-modify-writes the sequence counter, and the fixture server runs on
        # `ThreadingHTTPServer` -- one thread per connection. Two callers hitting the same sequenced
        # capability concurrently could both read index 0 and both get the first answer, silently
        # turning "full on the second ask" back into the unvarying behaviour sequences exist to
        # escape. Guarding the whole read-modify-write is cheap: a dict lookup and an increment.
        self._lock = threading.Lock()
        #: ``(role, caller, capability)`` -> entries, **most specific first**. ``caller`` ``""`` is
        #: the shared-fact scope.
        #:
        #: 🔴 A **list**, not one entry per key. It was a dict, so one scope held exactly one
        #: answer -- which is why a per-SKU lookup could not be expressed at all: authoring a
        #: second entry for the same capability silently replaced the first. Ordering is by
        #: :attr:`FixtureEntry.specificity`, so a ``matches``-bearing entry is preferred over the
        #: catch-all, and Python's stable sort keeps authored order among equals.
        self._entries: dict = {}
        #: Per-key call counters, for `sequence` fixtures. Reset only by :meth:`reset`.
        self._calls: dict = {}
        for role in self._manifest.roles:
            for entry in role.fixtures:
                self._entries.setdefault((role.id, entry.caller, entry.capability), []).append(entry)
        for scope, bucket in self._entries.items():
            self._refuse_duplicates(scope, bucket)
            bucket.sort(key=lambda entry: -entry.specificity)
        self._role_faults = {role.id: role.faults for role in self._manifest.roles}

    @staticmethod
    def _refuse_duplicates(scope: tuple, bucket: list) -> None:
        """Refuse two entries constraining the same arguments in one scope.

        🔴 Loud at load, never resolved by order. Two entries that both claim ``sku=REG-110V`` are
        an author asking two different questions of one call; picking the first would serve the
        value they were not editing, which is the same silent-precedence failure ``__post_init__``
        refuses ``returns``+``sequence`` for.
        """
        seen: dict = {}
        for entry in bucket:
            if entry.signature in seen:
                role, caller, capability = scope
                where = f"role '{role}', capability '{capability}'" + (f", caller '{caller}'" if caller else "")
                what = dict(entry.matches) if entry.matches else "no `matches` (the catch-all)"
                raise ManifestError(f"two fixtures for {where} both answer {what}; exactly one may")
            seen[entry.signature] = entry

    @property
    def scenario(self) -> str:
        """Which scenario this world belongs to."""
        return self._manifest.scenario

    def roles(self) -> tuple:
        """Every system this sim plays. Named in a 404 so an unroutable call says what *is* live."""
        return tuple(role.id for role in self._manifest.roles)

    def upsert(self, role: str, entry: FixtureEntry) -> None:
        """Add or replace one fixture; takes effect on the next call.

        Replacement is by :attr:`FixtureEntry.signature` within the scope, so editing the
        ``sku=REG-110V`` answer leaves the ``sku=BATTERY-2V`` one and the catch-all alone -- the
        whole point of per-argument entries being that they are separately editable.

        The sequence position is reset with it: an edited fixture is a new answer, and resuming
        mid-sequence would serve part of the old one.
        """
        scope = (role, entry.caller, entry.capability)
        with self._lock:
            bucket = [held for held in self._entries.get(scope, []) if held.signature != entry.signature]
            bucket.append(entry)
            bucket.sort(key=lambda held: -held.specificity)
            self._entries[scope] = bucket
            self._calls.pop((role, entry.caller, entry.capability, entry.signature), None)

    def reset(self) -> None:
        """Forget every sequence position. A new scenario starts where the last one began."""
        with self._lock:
            self._calls.clear()

    def resolve(
        self, role: str, capability: str, caller: str = "", inputs: Optional[dict] = None
    ) -> Optional[FixtureEntry]:
        """The most specific entry for this call, or ``None`` when the sim has nothing to say.

        Two dimensions, both most-specific-first: the caller scope is tried before the shared one,
        and within each, an entry constraining what was *asked* is preferred over the catch-all.
        A caller-scoped catch-all therefore beats a shared per-argument entry -- "this branch
        always answers X" is a more specific statement about *this* call than "anyone asking about
        SKU-Y gets Z".
        """
        for key in ((role, caller, capability), (role, "", capability)):
            for entry in self._entries.get(key, ()):
                if entry.selects(inputs):
                    return entry
        return None

    def answer(
        self, role: str, capability: str, caller: str = "", inputs: Optional[dict] = None
    ) -> Optional[tuple]:
        """Resolve and *consume* one answer -- advancing a ``sequence`` fixture by one call.

        :param inputs: The call's arguments, for entries scoped by ``matches``. Omitted means "no
            arguments were supplied", which only catch-all entries answer.
        :return: ``(payload, faults)``, or ``None`` when nothing is configured for this call.
        """
        entry = self.resolve(role, capability, caller, inputs)
        if entry is None:
            return None
        faults = entry.faults or self._role_faults.get(role) or FaultConfig()
        if entry.returns is not None:
            return dict(entry.returns), faults
        # Keyed by the entry's OWN scope, not the caller's: several callers sharing one shared-fact
        # sequence walk it together, which is the honest reading of a single fact changing over
        # time. A per-caller sequence gets its own counter because its key differs.
        #
        # 🔴 The signature is part of the key for the same reason: two per-argument sequences on one
        # capability ("SKU-A drains, SKU-B holds") are different facts changing over time, and a
        # shared counter would advance SKU-B's answer because someone asked about SKU-A.
        key = (role, entry.caller, capability, entry.signature)
        with self._lock:
            index = self._calls.get(key, 0)
            self._calls[key] = index + 1
        sequence = entry.sequence or []
        return dict(sequence[index % len(sequence)]), faults


def load_manifest(path: Path) -> SimManifest:
    """Read a manifest, or an empty one when the file does not exist.

    🔴 Absent is legal and means "no roles configured", not an error: a scenario that has never been
    set up must still start. Unreadable is not -- see :class:`ManifestError`.
    """
    if not Path(path).exists():
        return SimManifest()
    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"sim manifest '{path}' is unreadable: {exc}") from exc
    return SimManifest.from_dict(loaded)
