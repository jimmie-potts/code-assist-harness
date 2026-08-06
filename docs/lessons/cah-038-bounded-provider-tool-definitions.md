# CAH-038 lesson: Bounded provider tool definitions

- **Unit:** CAH-038
- **Milestone:** M2 - Read-only coding assistant
- **Learning emphasis:** Supporting implementation unit
- **Review focus:** Converting native tool metadata into a bounded provider definition tuple without
  moving orchestration or input policy into the provider layer
- **Lesson status:** Planned
- **Implementation status:** Planned; no canonical provider-definition bridge exists yet
- **Story:** [CAH-038](../../user-stories/cah-038-canonicalize-provider-tool-definitions.md)
- **Visual companion:** None; do not add or revise presentation files
- **Related architecture:** [Architecture](../architecture.md), [Tool system](../tool-system.md), and
  [Safety model](../safety-model.md)

> This lesson explains accepted planned behavior. Its code blocks are pseudocode, not shipped
> evidence.

## Quick summary

CAH-038 turns the four CAH-031 read-tool descriptors and native Pydantic schemas into immutable,
provider-neutral definitions. The key lesson is that schema generation is not schema admission: the
harness applies a small closed grammar and explicit work/byte bounds before the definition tuple
reaches a provider request.

## Learning objectives

After completing this unit, you should be able to:

- explain why a generated Pydantic schema is still untrusted boundary data;
- distinguish O(1) cardinality gates, bounded semantic validation, and incremental encoding;
- trace ownership from a native descriptor to a fresh immutable provider definition; and
- explain why exact required names are defined here while runtime argument-key enforcement belongs
  to CAH-039.

## Why this unit matters

Tool definitions cross from harness-owned Python types toward provider adapters. Without a narrow
conversion boundary, unsupported schema features, mutable caller data, huge collections, or
provider SDK types could leak into the core agent loop. Splitting this work from CAH-032 makes the
definition boundary independently reviewable before calls and history are added.

## Junior engineer foundation

JSON Schema describes the shape of JSON, but implementations support different subsets. A Pydantic
model may generate annotations such as root `title`/`description` or property `title`/`default`; that does not mean the harness wants to
promise those semantics to a model.

For this model:

```python
class ReadRequest(BaseModel):
    path: str
    max_bytes: int = 4096
```

Pydantic emits `required=["path"]` and a `default` only for `max_bytes`. The bridge validates that
exact producer shape, then may remove those generated annotations while its provider
definition lists both `path` and `max_bytes` as required. An all-default model such as
`ListFilesRequest` omits `required` entirely; an injected empty list is drift, not an equivalent
producer snapshot. A common misconception is that canonicalizing every field as required also rejects a model
call missing `max_bytes`. It does not: CAH-038 only builds definitions. CAH-039 later compares the
pair-preserved runtime argument keys with this exact required-name set before Pydantic can apply a
default.

“Remove annotations” must not mean “recursively walk the schema first.” Such a generic cleanup can
already traverse a huge or hostile candidate before the real budget begins. The bridge recognizes
only root `title`/`description`, property `title`, and property `default` while performing the same
bounded shape-directed copy. Their values are exact built-in scalars, pass O(1) length/work gates, and are charged before
being omitted. A huge annotation, subclass hook, or annotation at another location fails closed.

JSON Schema `maxLength` counts characters, not UTF-8 bytes. A path property may therefore advertise
`maxLength: 4095` only as a coarse necessary cap; it cannot exactly express CAH-024's 4,095-byte,
256-component, or 255-byte-name native contract. CAH-039's strict native validation remains the
authority, especially for multibyte names.

Another misconception is that checking final JSON length bounds the work required to produce it. A
million-item candidate can consume large memory or CPU before serialization. CAH-038 therefore
checks container lengths first, copies only known flat fields under one work budget, and encodes
incrementally. It accepts exact built-in containers and scalars rather than arbitrary Python
mapping/sequence subclasses, whose user-defined hooks could make even `len()` or iteration perform
unbounded work.

Schema *generation* is a separate trust decision. M2 invokes `model_json_schema()` only for the exact
four repository-owned input-model class identities paired with `list_files`, `stat_path`,
`read_file`, and `search_text`. A foreign model or subclass is rejected before its hook runs. The
generated dictionaries are nevertheless admitted as boundary data because trusted code can drift.

## Key concepts

- **Provider tool definition:** SDK-free exact name/description strings, bounded canonical
  `parameters_json`, and immutable `required_keys` shown to a provider through fresh projection.
- **Closed schema subset:** the only accepted root and scalar-property keywords; unknown or nested
  shapes fail instead of being interpreted generously.
- **Shape-directed copy:** a new value built by visiting only expected fields, never `deepcopy` or
  arbitrary recursion.
- **Non-resetting budget:** one 16,384-unit allowance shared by the whole candidate, not one allowance
  per property or enum.
- **Incremental encoder:** compact canonical JSON emitted in chunks and stopped before the 16,385th
  UTF-8 byte is retained.
- **Atomic bridge:** all CAH-031 descriptors convert in registry order or none are published.
- **Closed generator set:** four exact repository-owned Pydantic model identities are the only
  schema-generation authority; their output still passes bounded admission.
- **In-pass annotation handling:** expected generated annotations are charged and omitted only while
  copying their known field positions, never by a generic recursive cleanup.
- **Schema honesty:** a model-facing character hint never masquerades as native byte/component/name
  enforcement.
- **Independent grammar parity:** CAH-031 owns inventory names; this one-way bridge independently
  re-admits the same exact `[a-z][a-z0-9_]{0,63}` grammar and locks it with mutation tests.

## Architecture and design

```text
Ink TUI                 Python harness                              Provider
   |                         |                                          |
   |                  CAH-031 read registry                             |
   |        descriptor + one of four exact native Pydantic models       |
   |                         v                                          |
   |           [CAH-038 definition bridge]                              |
   |  trusted generation -> O(1) gates -> bounded fresh copy            |
   |  (charge/omit expected annotations/default in that same pass) ->   |
   |        semantic checks -> incremental encode                       |
   |                         |                                          |
   |       immutable tuple[ProviderToolDefinition, ...]                  |
   |                         v                                          |
   |               CAH-032 bounded request ---------------------------->|
   |                                                                    |
   +-------------------- no TUI/protocol change ------------------------+

Later CAH-039: pair-preserved call arguments -> exact required-key gate -> native validation
Evidence: constructor boundaries + canonical snapshots + real-registry atomic bridge tests
```

The registry remains the source of tool identity and native input models. CAH-038 owns only the
conversion and immutable provider definition. CAH-032 consumes the resulting tuple; it neither
generates nor validates schemas. The provider never owns tool-definition selection, dispatch, or the agent
loop.

The definition stores no dictionary. Its sole schema carrier is compact canonical `parameters_json`
plus the exact matching `required_keys` tuple. `materialize_parameters()` decodes that already
bounded flat string into a fresh built-in object only for CAH-032 request projection and CAH-036 SDK
mapping. Mutating one returned object cannot affect the definition or another projection.

Construction is available only through the bounded direct factory or the private trusted-generator
path; callers cannot inject stored JSON/required fields. Every failure is
`ProviderToolDefinitionError(code="invalid_provider_tool_definition", message="Provider tool definition is invalid.")`.
It is content-suppressed and never exposes schema data, Pydantic diagnostics, or chained exceptions.

`ProviderToolDefinition` belongs in `provider/models.py`; the sole
`build_provider_tool_definitions(registry) -> tuple[ProviderToolDefinition, ...]` integration bridge
belongs in top-level `tool_definitions.py`. That bridge may import both contracts, while neither the
provider package nor CAH-031 imports the other side.

## Practical walkthrough

Use one stage order in implementation and tests:

1. Confirm the descriptor name/model pair belongs to the exact four-model generator set before any
   schema-generation hook, then obtain its generated candidate.
2. Validate the bounded definition name and description and identify only exact built-in expected
   root containers.
3. Apply O(1) lengths before iteration: four canonical root members (plus optional generated root
   `title` and `description`, with `required` absent only for the exact all-default producer), at most six root entries, 32
   properties/required names, six canonical property members (plus optional
   generated `title`/`default`), and at most 256 enum values.
4. Copy only admitted flat fields into fresh containers under one shared 16,384-unit visit/scalar
   budget. Recognize, charge, and omit expected annotations inside this pass; do not pre-strip them.
5. Validate Unicode scalars, signed-64-bit integers, type-specific keyword relations, enum
   uniqueness, and mode-specific `required`/`default` membership. Direct candidates require every
   property and no defaults. Generated candidates must match the exact four-model producer snapshot:
   no `required` key for `ListFilesRequest`, `path` for stat/read, and `query` for search; precisely
   the omitted fields carry compatible defaults. Sort property names by UTF-8 bytes and rebuild exact
   `required` names from every property.
6. Incrementally encode compact sorted-key JSON and stop before retaining byte 16,385.
7. Freeze one definition. The bridge repeats the bounded constructor in registry order and publishes
   the tuple only after all four succeed.

Any failure before step 6 produces no definition. An invalid member during bridge conversion
produces no partial definition tuple and starts provider work zero times.

## Implementation code samples

### Planned pseudocode: one bounded constructor

```python
def provider_tool_definition(name, description, candidate):
    require_bounded_name_and_description(name, description)
    require_expected_container_lengths(candidate)       # O(1) gates first
    fresh = copy_closed_fields(candidate, budget=16_384) # one shared budget
    validate_source_shape_and_order(fresh)               # direct mode: every field required
    canonical = encode_incrementally(fresh, limit=16_384)
    return freeze_definition(name, description, fresh, canonical)
```

The constructor does not `deepcopy` the candidate or serialize it to discover whether it is too
large. The work budget charges aggregate visits and Unicode scalars. The encoder has a separate
16-KiB output limit and never retains the excess byte. The frozen definition retains only that
canonical string and its matching immutable required-name tuple; it exposes fresh decoded objects
through `materialize_parameters()` rather than a mutable schema reference.

### Planned pseudocode: atomic registry bridge

```python
def build_provider_tool_definitions(
    registry: ReadToolRegistry,
) -> tuple[ProviderToolDefinition, ...]:
    definitions = []
    for read_tool in registry.entries:
        descriptor = read_tool.descriptor
        generator = require_exact_m2_model_pair(descriptor)  # rejects before foreign hooks
        generated = generator.model_json_schema()
        definitions.append(
            provider_tool_definition_from_generated(
                descriptor.name,
                descriptor.description,
                generated,  # bounded copy handles source-only annotations/default in place
            )
        )
    return tuple(definitions)
```

The real implementation must build into a local candidate and return only after every descriptor
succeeds. `provider_tool_definition_from_generated` never calls a generic annotation remover. It
recognizes only expected root `title`/`description`, property `title`, and property `default` during the same bounded copy,
charges their exact built-in values, validates absent/partial generated `required` against the exact
model's default-bearing fields, rejects every other drift, and then makes every property required.

## Failure scenarios to study

| Scenario | Owner | Safe result | Planned evidence |
| --- | --- | --- | --- |
| 33 properties or 257 enum values | O(1) cardinality gates | reject before visiting members or sorting | length and late-sentinel spies |
| custom mapping, sequence, or scalar subclass | exact built-in type gate | reject before caller-defined hooks | hostile-subclass interaction spy |
| foreign/subclassed Pydantic input model | exact four-model generator gate | reject before `model_json_schema()` or caller hooks | model-generation interaction spy |
| huge, subclassed, nested, or misplaced root/property annotation or property default | in-pass generated-schema copier | reject before annotation hooks, generic recursion, or encoding | four real producer snapshots plus annotation visit/serializer spies |
| generated `required` is absent/partial in the wrong model or disagrees with defaults | trusted-generator admission | fixed definition failure before canonical rebuild | four real-schema snapshots plus one-field mutations |
| aggregate work exceeds 16,384 | shape-directed copier | reject without resetting at a child | below/at/above aggregate-work test |
| signed-64-bit overflow or boolean integer | semantic validator | fixed definition failure | endpoint and 5,000-digit cases |
| nested, cyclic, or unknown schema shape | closed-field copier | reject at expected field without recursive traversal | shape table and visit spy |
| canonical JSON reaches byte 16,385 | incremental encoder | reject without retaining excess output | exact byte-bound test |
| serializer raises `RecursionError` or `ValueError` | defensive encoder guard | fixed content-suppressed failure | injected-failure test |
| third registry descriptor drifts | atomic bridge | publish no definitions; zero provider starts | real-registry failure injection |
| caller mutates one materialized parameter object | fresh projection | definition and next projection unchanged | two-call identity/equality mutation test |
| model omits a required runtime key | later CAH-039 | not decided or parsed by this unit | ownership boundary test |

## Production expansion

### Example enterprise scenario

A platform may publish hundreds of versioned tools from several teams. It would need schema-version
governance, compatibility checks, catalog signatures, and revocation rather than simply increasing
these local limits.

### Typical production capabilities and tools

- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) defines the broader vocabulary;
  supporting more of it adds interoperability and validation cost.
- [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/) generates schemas
  from Python models but does not replace boundary-specific admission.
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling) consumes
  provider-mapped definitions; it does not own the harness definition inventory.
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture) can expose remote tool
  catalogs, adding transport trust, capability classification, and revocation work.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Published artifact | four immutable local definitions | versioned multi-team catalog |
| Schema | closed flat scalar subset | governed compatibility profiles |
| Admission | synchronous bounded bridge | signed snapshots and policy service |
| Operations | deterministic offline tests | catalog health, audit, and revocation |
| Cost | narrow code and review surface | migration and governance overhead |

### Trade-offs and graduation signals

The closed subset rejects useful advanced schemas, but it makes model-facing behavior deterministic
and reviewable. Expand it only when a real tool needs a missing feature and cross-provider fixtures
can prove identical semantics without weakening work bounds.

## Practical exercises

1. Reorder source properties and predict why the canonical bytes remain equal.
2. Design a candidate where every enum is individually small but aggregate work exceeds 16,384;
   explain why a per-enum budget would be unsafe.
3. Trace a native default from Pydantic generation to the definition's `required` list, then identify
   the exact later CAH-039 check that prevents the default from filling a model omission.
4. Snapshot all four documented Pydantic models and explain why a root `description` is valid trusted
   producer input but invalid canonical output.

## Key takeaways

- The harness, not Pydantic or a provider SDK, owns schema admission.
- M2 explicitly trusts schema generation only for four exact native model identities; it does not
  generalize that trust to arbitrary Pydantic models.
- Expected generated annotations are bounded and discarded inside the shape-directed copy, never in
  an unmetered recursive pre-pass.
- Cardinality, work, and encoded-byte limits are separate invariants and all fail atomically.
- The definition records exact required names; runtime argument-key enforcement remains CAH-039's
  responsibility.

## Glossary

- **Canonical schema:** one immutable, deterministically ordered representation of an admitted
  provider parameter contract.
- **Cardinality gate:** an O(1) container-length check performed before element traversal.
- **Fresh copy:** new containers that retain no mutable references from the candidate.
- **Atomic publication:** returning the complete definition tuple or no tuple after a failure.

See the shared [glossary](../glossary.md) for provider port, tool registry, and harness terms.

## Further reading

- [CAH-038 delivery contract](../../user-stories/cah-038-canonicalize-provider-tool-definitions.md)
- [CAH-031 read-tool registry](../../user-stories/cah-031-register-read-tools.md)
- [Architecture](../architecture.md)
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)
- [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/)
