# NOTICE

NeuroEdge AgentForge is a derived work that includes content
adapted from third-party sources. This file records those attributions
as required by the upstream licenses.

---

## Effective Claude Code (ECC)

Approximately 80% of the skill files in `skills/` (every file carrying
`origin: ECC` in its YAML frontmatter) are adapted or directly ported
from **Effective Claude Code (ECC)** by Affaan Mustafa.

- Upstream repository: https://github.com/affaan-m/ECC
- License: MIT
- Author's statement: *"OSS stays free. This repo is MIT-licensed forever."*

The MIT License copyright notice and permission notice of the upstream
work are preserved below, as required by the MIT License:

```
MIT License

Copyright (c) 2026 Affaan Mustafa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Files derived from ECC retain individual `origin: ECC` markers in
their YAML frontmatter for per-file provenance.

---

## Other attributions (pending verification)

- `skills/SDLC/development/plankton-code-quality.md` — `origin: community`
  (upstream license to be verified)
- `skills/SDLC/development/prompt-optimizer.md` — `origin: community`
  (upstream license to be verified)
- `skills/DOMAIN/healthcare/healthcare-phi-compliance.md`,
  `skills/DOMAIN/healthcare/healthcare-emr-patterns.md`,
  `skills/DOMAIN/healthcare/healthcare-cdss-patterns.md`
  — contributed by Dr. Keyur Patel, Health1 Super Speciality Hospitals
  (contributor license clarification pending)

---

## Cognizant-original works

All other content — Python scripts (`setup_neuroedge_agentic_tools.py`,
`install.py`, `patch_assets.py`), the `src/neuroedge_marketing/`
package, shell hooks, project templates, NeuroEdge-origin skills,
the NeuroEdge AgentForge toolkit identity, and all documentation
under `docs/` — is © Cognizant.

License terms for the overall repository will be defined when this
repo is prepared for external distribution. Current scope is
internal Cognizant use.

---

## External services consumed at runtime

The `src/neuroedge_marketing/` pipeline calls the following third-party
APIs. None require attribution in the rendered output, but each is
governed by its provider's Terms of Service — API keys must be held by
Cognizant under the relevant commercial terms before any externally
distributed marketing asset is rendered.

- **Pexels Video API** — [pexels.com/license](https://www.pexels.com/license/)
  (free for commercial use, no attribution; identifiable people / brand
  restrictions apply — enforced by the human-review gate in the
  `/marketing-video` command)
- **Pixabay Video + Music API** — [pixabay.com/service/license-summary/](https://pixabay.com/service/license-summary/)
  (free for commercial use, no attribution; 24-hour response caching
  required and implemented in `providers.py`)
- **OpenAI Audio API** (`gpt-4o-mini-tts`) — [openai.com/policies](https://openai.com/policies)
- **ElevenLabs Text-to-Speech** — [elevenlabs.io/terms-of-use](https://elevenlabs.io/terms-of-use)
  (free tier requires attribution; pipeline expects a paid-tier key)

The `faster-whisper` library (CTranslate2-backed Whisper) is consumed as
a pip dependency, not vendored, and remains under its upstream MIT
license — see [github.com/SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper).

---

*Last updated: 2026-06-05*
