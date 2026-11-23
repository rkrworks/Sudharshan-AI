# Changelog — Sudharshan AI (Project Nebula)

## [2.0.0-nebula] — Project Nebula Release
### Added
- **`sudharshan_native/`**: Complete 1.5B-class decoder-only Transformer (`1,526,827,008` verified parameters) with RoPE, RMSNorm, 16Q/4KV GQA, SwiGLU, KV caching, batched inference, LoRA, code-aware BPE tokenizer, training/eval harness, 15-domain SFT datasets, and unified 6-provider `NebulaModelAdapter`.
- **`registry/`**: Deterministic 2,500-feature honest registry (`1,000` web features across 30 categories + `1,500` desktop features across 10 domains), clearly separating `130` `implemented_and_tested` from `2,370` `planned_backlog`.
- **`DESIGN_SPEC_NEBULA.md`**: Distilled Taste Skill v2.5.1 design specification (Precision Obsidian Dark `#0B0B0D` + Warm Paper Light `#F8F8FA`, Solar Orange `#FF5A1F`, strict shape lock).
- **`test_sudharshan_native.py` & `test_nebula_verification.py`**: Expanded automated test coverage to **40/40 passing tests** across 4 suites.
- **Technical Documentation & Presentation Deliverables**: 27-section Technical PDF, 36-slide Executive & Engineering PPTX, and clean `SUDHARSHAN_AI_NEBULA_COMPLETE.zip` package.

### Changed & Fixed
- Removed 105 stray flattened duplicate files and 88 unused HTML assets from `assets/` and `web/assets/`.
- Fixed `memory_store` SFT action schema (`key` + `content`) for 100% strict `ToolSchemaValidator` compliance.
- Synced `web/` portal upgrades (Dark/Light toggle, Native 1.5B section, Registry transparency panel) to root HTML/CSS.
- Regenerated `SHA256SUMS` and `web/SHA256SUMS` across all 42 tracked release files.
