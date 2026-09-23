# The 1D-CNN drift model — a beginner's guide

What the model is, what one training run does, how much to trust its number, and what would move
it. The data it is trained on, and how windows and splits are made, are in
[`dataset.md`](dataset.md) (§11–§15). Read that first.

**Where the numbers come from.** Settings come from `1DCNN/config.yaml` and `use_case.lock.json`
in this folder. Results come from two places, and they are kept apart on purpose:

- **Held-out test result (evaluated 2026-09-21):** `1DCNN/portal_held_out.json`, the portal's
  evaluation of the sealed test split, checked into this folder. The table in §5 comes from it.
- **Training-run numbers (observed 2026-09-23):** read from the portal's training log for the run of
  2026-09-23. They are **not yet in a file in this folder**. They arrive with that run's model
  package, which is dropped in `from-neuroedge/` and unpacked by `/agentforge-ml`. Until then they
  are marked *(observed in the portal)*.

These two may not describe the same model. The held-out result names the model it scored
(`model.onnx` sha256 `24d3a85af18e…`), and the 2026-09-23 run may be a later one. When its package
is dropped in, `intake` matches the held-out result to it by that hash, or refuses.

---

## 1. What the model is

A small **1D convolutional network** (`1DCNN/model.py`). It slides short filters along the 64
time steps of a window (`dataset.md` §13) and learns which shapes in the three channels go with
`tool_wear`. It outputs one number between 0 and 1. Above a **threshold** it raises an alarm.

The threshold is not 0.5, and it is not chosen by hand. It is set on the **validation** split so
that no more than 1 in 100 normal windows raises an alarm (`at_fpr: 0.01` in the lock). The
held-out result records it as 0.7766, "from the model's meta.json, fixed before the test data was
seen".

A **MiniRocket** classical baseline (`MiniRocket/`) is trained on the same splits. It sets the
honesty floor: a deep model that cannot beat it is not earning its cost on the device.

---

## 2. What one training run actually does

The log shows a counter climbing to 21, stopping, then restarting at 1. Nothing went wrong, and
nothing was retried.

### First, what an "epoch" is

One **epoch** means the model has looked at every training window exactly once.

It does not look at all 8,079 at once. Memory will not take it, and learning works better in small
steps. They go through in batches of `batch_size: 128` (`config.yaml`). For each batch:

1. the model guesses `normal` or `tool_wear` for all 128 windows,
2. it is told how wrong it was (that is the **loss**, and lower is better),
3. every internal number nudges slightly in the direction that would have been less wrong.

8,079 ÷ 128 ≈ 63 batches, and after those 63 nudges one epoch is done. Then it is scored on the
validation windows it does not train on. That gives the `val_loss` and `val_pr_auc` in the log.

```
[real_only] epoch 7/100 train_loss=0.2526 val_loss=0.4259 val_pr_auc=0.8510
             │      │         │                 │              │
             │      │         └─ wrongness on data it IS learning from
             │      └─ the BUDGET, not a target (config: epochs: 100)
             └─ how many complete passes so far
                                  └─ wrongness on held-out data ┘
                                                 └─ how well it separates worn from normal
```

### Why it stopped at 21 when the budget was 100

`epochs: 100` is a ceiling, not a plan. The real stopping rule is `patience: 15`:

> Keep the best-scoring epoch. If **15 epochs in a row** fail to beat it, stop. The model is no
> longer improving, and further epochs start memorising the training data rather than learning the
> pattern (**overfitting**).

Best score came at epoch 6. Fifteen fruitless epochs later (6 + 15 = 21) it stopped. **The model
that is kept is epoch 6's, not epoch 21's.** *(observed in the portal)*

### Why the counter then restarted at 1

Because a *different model* started. One press of Train builds **six** models, one after another,
each from scratch with its own epoch count *(observed in the portal)*:

| # | Training | Budget | Stopped | What it is |
|---|---|---|---|---|
| 1 | `real_only` | 100 | 21 | trained on real windows only |
| 2 | `real_synthetic` | 100 | 20 | real + 4,039 synthetic windows (`dataset.md` §15) |
| 3 | `cv_IM-01R-A01` | 60 | 22 | fold, see §3 |
| 4 | `cv_IM-01R-A02` | 60 | 20 | fold |
| 5 | `cv_IM-01R-A05` | 60 | 23 | fold |
| 6 | `cv_IM-01R-A04` | 60 | 16 | fold |

**Trainings 1 and 2 are an experiment**, set by `ablation.enabled: true`: does adding synthetic
data help? Both are scored on the *same real* validation windows, so the comparison is fair
*(observed in the portal)*:

```
real_only       recall@fpr = 0.360
real_synthetic  recall@fpr = 0.398   ← winner, and the model that is kept
```

The M6 gate approved synthetic data only on that condition. Had it lost, `real_only` would have
shipped instead. The run decides, not an assumption.

**Trainings 3–6 are measurements, not candidates.** §3 explains them. They are thrown away.

---

## 3. Folds — how much should you trust that number?

The validation headline rests on **one worn trial**, `IM-01R-A04`. The held-out test headline rests
on one more, `IM-01R-A03`. The result file says so:

> *"The headline recall_at_fpr rests on 1 worn unit(s) (IM-01R-A03): a single-trial pass/fail, NOT
> a population estimate."* — `1DCNN/portal_held_out.json`

Maybe A03's wear is obvious and any model would catch it. Maybe it is unusually subtle. **One
number cannot tell you which.**

### Leave-one-worn-unit-out

The fix is to repeat the training several times, holding out a **different** worn trial each time.
Each repeat is called a **fold**:

```
fold 1:  train on A02, A05, A04  →  score on A01     ← A01 held out
fold 2:  train on A01, A05, A04  →  score on A02
fold 3:  train on A01, A02, A04  →  score on A05
fold 4:  train on A01, A02, A05  →  score on A04
```

There are **four folds because four worn trials can be held out**. They are listed in
`config.yaml` under `cross_validation.worn_units`. A fold is not a data file and not a trial. It is
one *rerun with a different trial held out*.

> **A03 is not in the list.** It is the sealed test unit, and cross-validation never touches it.
> `config.yaml` says so in a comment ("Never touches A03/test"). If folds borrowed A03, the final
> test would no longer be on unseen data.

Folds get a smaller budget (`epochs: 60`, `patience: 10`) because they are diagnostics. They are
trained, scored and deleted. None is ever deployed, and none is drawn on the portal's loss curve
or put in its headline tile.

**What you get is four scores, not one.** The spread between them answers "is the headline real?"

- If the four scores are similar, the number is stable and you can trust it.
- If they differ wildly, the result depends on which trial you happened to test on. The honest next
  step is **more worn trials**, not more training.

The spread is recorded in the run's `metrics.json` under `cross_validation`. It is not in this
folder until the model package is dropped in (see the top of this page).

---

## 4. What the number means — the KPI

**Accuracy is useless here.** Worn windows are rare on a real line. A model that answers "normal" to
everything scores well on accuracy and is worthless. So the KPI, from `use_case.lock.json`, is:

> **`recall_at_fpr`**: of all the genuinely worn windows, what fraction did we catch, *while*
> raising no more than 1 false alarm per 100 normal windows (`at_fpr: 0.01`)? The target is
> `min_value: 0.9`.

Both halves matter. Catching everything is easy if you alarm constantly. The false-alarm budget is
what makes it honest, and on a shop floor an alarm nobody trusts is worse than none.

`config.yaml` makes that the selection rule too: `monitor: "recall_at_fpr"`, with
`tie_break: "pr_auc"` when two epochs are level. **The thing you are judged on is the thing chosen
for.** Loss is only the training signal.

**PR-AUC** is shown beside it. It measures how well the scores rank worn above normal across *all*
thresholds, so it can be high while recall at the one allowed threshold is low. Both are true at
once here.

---

## 5. Where this model stands

| | Validation *(observed in the portal, 2026-09-23)* | **Held-out test** (`1DCNN/portal_held_out.json`, 2026-09-21) |
|---|---|---|
| split | `self_reported_val` (A04) | `held_out_test` (A03) |
| recall at 1% FPR | 0.398 | **0.318** |
| false-alarm rate actually reached | — | 0.009 |
| PR-AUC | 0.927 | 0.939 |
| AUROC | — | 0.918 |
| target recall | 0.90 | 0.90 |
| `meets_target` | false | **false** |

It catches about 3 to 4 in 10 worn windows at the allowed false-alarm rate, against a target of 9 in
10. **It does not meet the target on either split.** The validation number is the flattering one,
because val chose the epoch and the threshold. The held-out number is the one to quote.

**Caveats carried from the held-out result, as written:**

- "units IM-01R have rows in the test split AND in a file the training package carried: the
  package's code is trusted to have read only their train and val rows"
- "this test set has now been evaluated on 2 times: a number chosen after looking at earlier ones is
  no longer a clean held-out result"
- `IM-01R`'s test segment "is the tail of a run whose head was trained on, which can flatter
  specificity" (`dataset.md` §14).

**Against the baseline.** The MiniRocket baseline scored recall 0.027 on the same validation
windows *(observed in the portal)*, so the 1D-CNN beats it clearly. The approach works. There is
simply not enough evidence yet.

---

## 6. What would move the number

In order of expected effect, each with its evidence:

1. **More worn trials of the same program.** Four worn trials outside test, one normal run: this is
   the binding constraint (`dataset.md` §11, §14). Every training stopped early, in the teens or
   twenties out of 100 epochs, so the model stopped learning long before it ran out of budget
   *(observed in the portal)*. More data can change that; more epochs cannot.
2. **More normal runs of `IM-01R`.** With one baseline run, run-to-run variation cannot be separated
   from wear (`dataset.md` §8, §17). This also decides whether `vibration_rms` helps or misleads
   (`dataset.md` §12).
3. **Settling the unconfirmed inputs.** If the edge device has no accelerometer, `vibration_rms`
   cannot be an input, and the model must be retrained on two channels (`dataset.md` §17).
4. **Not recommended: moving the threshold.** A lower threshold catches more worn windows by
   raising false alarms past 1%. That breaks the KPI's other half. It does not improve the model.

---

## Attribution

Trained on the KIT CNC milling dataset: Ströbel, R. et al. (2025), DOI 10.35097/hvvwn1kfwf7qt48z,
CC BY 4.0. See [`dataset.md`](dataset.md#attribution). The attribution must reach the model card and
the product NOTICE.
