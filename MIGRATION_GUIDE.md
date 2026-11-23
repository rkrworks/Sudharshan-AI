# Migration Guide: Sudharshan AI v1.x -> Project Nebula (v2.0)

## Backwards Compatibility
- All existing entry points (`bajrang_core.py`, `windows.py`, `fedora.py`, `linux_generic.py`, `macos.py`, `sudharshan_cli.py`, `razorpay_server.py`) remain intact and backwards-compatible.
- All 21 legacy security and audit tests (`test_bajrang_suite.py`) and all 100 Wave 1–10 feature tests (`test_waves_1_to_10.py`) pass with zero regressions.

## What Changed in Project Nebula
1. **New `sudharshan_native/` Package:** Adds the 1.5B Transformer architecture, BPE tokenizer, training/LoRA pipeline, 15-domain synthetic dataset generator, evaluation harness, and unified 6-provider `NebulaModelAdapter`.
2. **Honest Feature Registries (`registry/`):** Adds machine-readable `web_features_1000.json` and `desktop_features_1500.json` generated deterministically by `registry/build_feature_registry.py`.
3. **Taste-Skill Design System (`DESIGN_SPEC_NEBULA.md` + `web/`):** Upgrades the web portal with Warm Paper light theme toggle, Sudharshan Native 1.5B section, and Nebula Registry transparency dashboard while syncing root HTML/CSS files.
4. **Repository Hygiene:** Removed 105 flattened duplicate files and 88 unused demo/lab HTML files inside `assets/`.
