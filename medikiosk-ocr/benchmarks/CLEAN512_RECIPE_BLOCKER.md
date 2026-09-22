# Clean512 experiment: stopped at Phase 0

The historical report explicitly records **batch size 32**. The previously proposed command using 8 must not be executed as a matched historical baseline.

The selected historical checkpoint was not produced by a documented uninterrupted from-scratch run. `SYNTHETIC_BASELINE.md` states that the initial run was interrupted, its exact source epoch and optimizer state were not saved, and continuation restarted with a fresh optimizer. `generalization.json` records 10 requested continuation epochs, nine completed, labels 11–19, `warm_restart=true`, `optimizer_state_restored=false`, and `source_checkpoint_epoch=null`. Best label 14 is the fourth continuation epoch, not a proven absolute epoch.

The original epoch budget and CLI-overridable learning rate/min_delta are not in the retained resolved configuration. Current script defaults alone do not establish their historical values. The requested from-scratch run also intentionally differs from the historical warm-restart policy, beyond dataset/output paths. Consequently an exact matched recipe cannot presently be certified.

The machine-readable [comparison](clean512_v2_recipe_comparison.json) distinguishes recorded settings from current-code candidates and unresolved values. No model training or recognition inference was launched. No dataset, checkpoint, existing report, architecture or training code was modified in this task. Only these two new diagnostic files were created. Downstream metrics, decoder selection and A/B/C comparison remain pending, not zero or inferred.

Please supply the original command/resolved configuration, or explicitly authorize a revised protocol: fresh initialization, batch 32, seed41, unchanged current AdamW/augmentation/dropout/CTC settings, a specified epoch budget, and current stopping policy. Such a run must be labeled a new controlled baseline rather than an exact recreation of the historical interrupted schedule.

Validation contains Segoe Print only; validation-based checkpoint/decoder selection is renderer-conditioned and does not establish renderer-independent generalization. Test renderers must not select checkpoint or decoder. Clipping is repaired in clean512_v2 but is not proven to be the only recognition error source. This work does not establish clinical readiness. No MediKiosk integration, page OCR, width-1024 training, architecture change, commit or push is authorized or performed.
