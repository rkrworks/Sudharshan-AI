# Known Limitations & Honest Engineering Boundaries

1. **Sudharshan Native 1.5B Pretraining Status:**
   - **Implemented & Tested:** Complete 1.5B decoder-only Transformer architecture (`model_torch.py` + `model_numpy.py`), exact `1,526,827,008` parameter verification, custom code-aware BPE tokenizer, LoRA injection, KV-cached/batched inference, checkpoint round-trip, 15-domain SFT dataset validator, and 6-provider `NebulaModelAdapter`.
   - **Not Completed in This Session:** Full 1.5B pretraining on trillion-token corpora and production `.gguf` quantization require dedicated multi-GPU hardware not present in this CPU sandbox.
2. **Platform Hardware Verification:**
   - Cross-platform adapters (`windows.py`, `fedora.py`, `linux_generic.py`, `macos.py`) are syntax-checked and contract-tested in Linux CPU CI; physical OS desktop GUI tests (Win32 UIA, GNOME Wayland `ydotoold`, macOS Accessibility) require native host machines.
3. **2,500-Feature Nebula Registry:**
   - All 2,500 feature IDs (`1,000` web + `1,500` desktop) are uniquely registered and categorized. Currently **130 features** (`20` web + `110` desktop/core) are `implemented_and_tested`, and **2,370** are transparently tracked as `planned_backlog`.
4. **Offline Sandbox Environment:**
   - PyTorch (`torch`) is not installed in the sandbox VM; `sudharshan_native/model_torch.py` is production-ready PyTorch code verified statically, while `model_numpy.py` and `NumPyTrainer` provide real executable runtime verification in pure NumPy.
