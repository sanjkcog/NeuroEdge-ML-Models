---
description: Compile and profile a trained ONNX model on Qualcomm AI Hub with the user's own Qualcomm account, offline from the portal and behind a hard human gate that names exactly which files leave the machine and that they go to Qualcomm's cloud (ADR-0028 D-10). Writes the compiled artifact, its SoC, SDK version, sha256 and the profile report for upload in the portal's Optimize tab.
argument-hint: --dest <folder> --onnx <model.onnx> --device "<AI Hub device name>" [--precision fp16|int8 --calibration <folder>]
---

# /aihub-compile — Compile for a Qualcomm device on AI Hub, behind a hard gate

## Arguments

`$ARGUMENTS`:

- `--dest <folder>` — the model folder.
- `--onnx <file>` — the trained `model.onnx`. **The human downloads it** from the portal's Ready tab and puts it
  inside the model folder, for example `<dest>/aihub/input/model.onnx`. A file outside the folder is refused.
- `--device "<name>"` — the device, exactly as AI Hub lists it.
- `--precision fp16|int8` — default `fp16`. `int8` needs `--calibration <folder>`, and **those samples are sent too**.

## What this does

A Qualcomm device runs a compiled QNN context binary. It is tied to the SoC and the SDK version, so it is built
for one device. Qualcomm AI Hub builds it and profiles it on a real device in Qualcomm's farm.

**The job sends the model to a third party's cloud.** For INT8 it also sends calibration data, which is training
data. So a **hard human gate** opens first. It names every file that leaves, with its size and sha256, and where
it goes. **Nothing is sent before a human approves it.**

This does not touch the rule that nothing calls the portal (ADR-0025 D-1). The portal is not involved: the human
downloads the ONNX from it before, and uploads the result to it after.

You run this in the main session, because it asks the human a question.

## Procedure

1. **Make the request. It sends nothing.**
   ```
   python -m agentforge.src.ml_contract.aihub request --dest <dest> --onnx <file> --device "<name>" [--precision int8 --calibration <folder>]
   ```
   It hashes the files, writes `aihub/compile-request-<digest>.md` and `.json`, opens the hard gate
   `aihub/compile-request-<digest>.md`, and exits 3. The digest is part of the gate id. A request that is edited
   after the approval has another digest, so it has no approved gate.
2. **Ask the human.** Show the whole gate page inline: where the files go, the file table, and the sentence about
   calibration data. Ask with `AskUserQuestion`: **approve** or **reject**. Record exactly what they chose:
   `gate_state.py decide aihub/compile-request-<digest>.md <approved|rejected> --identity <user> --reason "<their words>"`.
   Rejected → stop. Nothing was sent.
3. **The human's account.** The job runs under the human's own Qualcomm account. They install the client and
   configure their token themselves (`pip install qai-hub`, then `qai-hub configure`). Never ask for the token,
   never write it, never pass it on a command line.
4. **Run the approved job.**
   ```
   python -m agentforge.src.ml_contract.aihub run --dest <dest> --request <dest>/aihub/compile-request-<digest>.json
   ```
   It refuses unless the gate is approved **and** every file still has the sha256 the human saw. Then it submits
   the compile job and the profile job, downloads both results, and writes `aihub/<device>/artifact.json`: the
   device, the SoC, the SDK version, the artifact's sha256 and size, the profile report and its sha256, the job ids,
   and who approved the gate and when.
5. **Hand over.** Tell the human what to upload in the portal's **Optimize** tab: the compiled artifact,
   `artifact.json` and the profile report. **They upload it.** Nothing here does.

## Limits, stated plainly

- **Unverified:** the built-in job runner was written from `qai_hub`'s public documentation. No real job has
  been run with it. Treat the first real run as a test, and read `artifact.json` before uploading.
- The built-in runner does **FP16 only**. It refuses INT8, because the calibration samples must be loaded into
  the input dictionary the model expects, and that is not built yet. The request and the gate for INT8 work.
- The SDK version is read from the profile report. When the runner cannot find it, `artifact.json` says
  `unknown` and you fill it in from the report before upload. Never invent it.

## Do NOT

- Do not run `aihub run` before the gate is approved, and do not approve it for the human.
- Do not send a file the gate page did not name. Make a new request instead.
- Do not send the withheld test split as calibration data. Calibration comes from the train split only.
- Do not call the portal. Do not upload for the human.
- Do not write the Qualcomm token anywhere.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /aihub-compile · Skills: ml-model-package, qualcomm-ai-hub, ml-artifact-destination`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-ml/ml-model-package.md`
> - `agentic-assets/skills/DEPLOY-TARGETS/qualcomm/qualcomm-ai-hub.md`
> - `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`
<!-- neuroedge-assets-patched source-version=a3cf127 -->
