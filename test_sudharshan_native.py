import tempfile
import unittest
from pathlib import Path

import numpy as np
import bajrang_core
from sudharshan_native import (
    SUDHARSHAN_NATIVE_1_5B_CONFIG,
    SUDHARSHAN_NATIVE_NANO_CONFIG,
    SudharshanBPETokenizer,
    SudharshanNativeNumPyModel,
    GenerationConfig,
    TrainingConfig,
    DatasetValidator,
    NumPyTrainer,
    build_sudharshan_synthetic_corpus,
    build_sudharshan_sft_dataset,
    SudharshanEvaluator,
    NebulaModelAdapter,
    calculate_parameter_breakdown,
)


class TestSudharshanNative15B(unittest.TestCase):
    def test_1_5b_parameter_count_programmatically_verified(self) -> None:
        b = calculate_parameter_breakdown(SUDHARSHAN_NATIVE_1_5B_CONFIG)
        self.assertGreaterEqual(b["total_trainable_params"], 1_450_000_000)
        self.assertLessEqual(b["total_trainable_params"], 1_600_000_000)
        self.assertEqual(b["total_trainable_params"], 1_526_827_008)
        self.assertAlmostEqual(b["total_params_billions"], 1.5268, places=3)

    def test_nano_instantiated_params_match_calculator_exactly(self) -> None:
        calc = calculate_parameter_breakdown(SUDHARSHAN_NATIVE_NANO_CONFIG)
        model = SudharshanNativeNumPyModel(SUDHARSHAN_NATIVE_NANO_CONFIG, seed=7)
        self.assertEqual(model.count_instantiated_parameters(), calc["total_trainable_params"])

    def test_bpe_tokenizer_train_special_tokens_and_serialization(self) -> None:
        corpus = build_sudharshan_synthetic_corpus()
        tok = SudharshanBPETokenizer()
        stats = tok.train(corpus, target_vocab_size=260, min_freq=2)
        self.assertGreater(stats["merges"], 10)
        sample = '<|user|>Organize ~/Downloads<|eos|><|assistant|><|tool_call|>{"tool":"organize_directory"}<|/tool_call|>'
        ids = tok.encode(sample)
        self.assertEqual(tok.decode(ids), sample)

        with tempfile.TemporaryDirectory() as tmp:
            p = tok.save(Path(tmp) / "tokenizer.json")
            tok2 = SudharshanBPETokenizer.load(p)
            self.assertEqual(tok2.encode(sample), ids)

    def test_kv_cache_matches_full_forward_and_batched_inference(self) -> None:
        model = SudharshanNativeNumPyModel(SUDHARSHAN_NATIVE_NANO_CONFIG, seed=11)
        seq = np.array([[1, 15, 22, 33, 44]], dtype=np.int64)
        full_logits, _ = model.forward(seq, use_cache=False)

        prefix_logits, cache = model.forward(seq[:, :-1], use_cache=True)
        last_logits, _ = model.forward(seq[:, -1:], kv_cache=cache, use_cache=True)
        np.testing.assert_allclose(full_logits[:, -1, :], last_logits[:, 0, :], atol=1e-4, rtol=1e-4)

        # Batched inference (B=2)
        batch = np.array([[1, 10, 20, 30], [1, 11, 21, 31]], dtype=np.int64)
        b_logits, _ = model.forward(batch, use_cache=False)
        self.assertEqual(b_logits.shape, (2, 4, SUDHARSHAN_NATIVE_NANO_CONFIG.vocab_size))

    def test_generation_sampling_lora_and_checkpoint_roundtrip(self) -> None:
        model = SudharshanNativeNumPyModel(SUDHARSHAN_NATIVE_NANO_CONFIG, seed=19)
        streamed = []
        out = model.generate(
            [1, 12, 18],
            gen_cfg=GenerationConfig(max_new_tokens=6, temperature=0.8, top_k=10, top_p=0.9, repetition_penalty=1.15),
            on_token=streamed.append,
        )
        self.assertGreaterEqual(len(out), 4)
        self.assertGreaterEqual(len(streamed), 1)

        lora_params = model.attach_lora(rank=4, alpha=8.0)
        self.assertGreater(lora_params, 0)

        with tempfile.TemporaryDirectory() as tmp:
            ckpt = model.save_checkpoint(Path(tmp) / "ckpt")
            loaded = SudharshanNativeNumPyModel.load_checkpoint(ckpt)
            probe = np.array([[1, 12, 18]], dtype=np.int64)
            # Clear LoRA on original to verify exact base weight round-trip
            model.lora_adapters.clear()
            l1, _ = model.forward(probe)
            l2, _ = loaded.forward(probe)
            np.testing.assert_allclose(l1, l2, atol=1e-5)

    def test_training_smoke_test_dedup_eval_and_adapter(self) -> None:
        corpus = build_sudharshan_synthetic_corpus()
        val = DatasetValidator.deduplicate_and_validate(corpus + [corpus[0], "hi"])
        self.assertEqual(val["duplicates_removed"], 1)
        self.assertEqual(val["rejected_short"], 1)

        tok = SudharshanBPETokenizer()
        tok.train(corpus, target_vocab_size=260, min_freq=2)
        model = SudharshanNativeNumPyModel(SUDHARSHAN_NATIVE_NANO_CONFIG, seed=42)

        with tempfile.TemporaryDirectory() as tmp:
            tcfg = TrainingConfig(mode="sft", learning_rate=0.05, min_learning_rate=0.01, warmup_steps=1, total_steps=6, grad_accum_steps=1, max_seq_len=32)
            res = NumPyTrainer(model, tok, tcfg).train(corpus, Path(tmp) / "run1")
            self.assertEqual(res["steps_completed"], 6)
            self.assertTrue(Path(res["log_file"]).is_file())
            self.assertTrue((Path(res["checkpoint_dir"]) / "weights.npz").is_file())

            ppl = SudharshanEvaluator.compute_perplexity(model, tok, corpus[:3], max_seq_len=32)
            self.assertTrue(np.isfinite(ppl))

            sft_check = SudharshanEvaluator.validate_tool_call_dataset(build_sudharshan_sft_dataset())
            self.assertEqual(sft_check["records_checked"], 15)
            self.assertEqual(sft_check["valid_schema_actions"], sft_check["total_actions_checked"])
            self.assertTrue(sft_check["zero_shell_exec_verified"])

            readiness = SudharshanEvaluator.readiness_report(pipeline_tested=True)
            self.assertTrue(readiness["1_architecture_implemented"])
            self.assertFalse(readiness["4_full_1_5b_pretraining_completed"])

            # Unified NebulaModelAdapter test
            cfg = bajrang_core.ConfigManager(config_dir=Path(tmp) / "cfg", data_dir=Path(tmp) / "data")
            adapter = NebulaModelAdapter(cfg, native_model=model, native_tokenizer=tok)
            caps = adapter.discover_capabilities()
            self.assertTrue(caps["sudharshan_native"]["available"])
            adapter.switch_provider("sudharshan_native")
            gen = adapter.generate("List windows", max_new_tokens=5)
            self.assertTrue(gen["ok"])
            self.assertEqual(gen["provider"], "sudharshan_native")
            self.assertGreaterEqual(adapter.token_accounting["requests"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
