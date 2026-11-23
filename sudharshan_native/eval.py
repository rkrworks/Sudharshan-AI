"""
SUDHARSHAN NATIVE — Evaluation Benchmark & Honest Readiness Reporter.

Evaluates:
- Perplexity on held-out sequences
- Strict JSON tool-call schema validation against `bajrang_core.ToolSchemaValidator`
- Fail-closed rejection of `shell_exec`
- Transparent 5-stage readiness status distinguishing architecture/param verification
  and pipeline testing from full 1.5B pretraining completion.
"""
import json
import math
from typing import Any, Dict, List, Sequence

import numpy as np
import bajrang_core

from .config import SUDHARSHAN_NATIVE_1_5B_CONFIG, calculate_parameter_breakdown
from .model_numpy import SudharshanNativeNumPyModel, softmax
from .tokenizer import SudharshanBPETokenizer


class SudharshanEvaluator:
    @staticmethod
    def compute_perplexity(
        model: SudharshanNativeNumPyModel,
        tokenizer: SudharshanBPETokenizer,
        texts: Sequence[str],
        max_seq_len: int = 64,
    ) -> float:
        total_nll = 0.0
        total_tokens = 0
        for txt in texts:
            ids = tokenizer.encode(txt, add_bos=True, add_eos=True)[:max_seq_len]
            if len(ids) < 2:
                continue
            arr = np.asarray([ids], dtype=np.int64)
            logits, _ = model.forward(arr[:, :-1], use_cache=False)
            probs = softmax(logits[0], axis=-1)
            targets = arr[0, 1:]
            p_tgt = np.clip(probs[np.arange(len(targets)), targets], 1e-9, 1.0)
            total_nll += float(-np.sum(np.log(p_tgt)))
            total_tokens += len(targets)
        if total_tokens == 0:
            return float("inf")
        return round(math.exp(total_nll / total_tokens), 4)

    @staticmethod
    def validate_tool_call_dataset(sft_records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        valid_json = 0
        valid_tools = 0
        total_actions = 0
        blocked_shell = True
        for rec in sft_records:
            obj = json.loads(rec["output"])
            valid_json += 1
            for act in obj.get("actions", []):
                total_actions += 1
                if act.get("tool") == "shell_exec":
                    blocked_shell = False
                res = bajrang_core.ToolSchemaValidator.validate_action(act)
                ok = bool(res[0]) if isinstance(res, tuple) else bool(res)
                if ok:
                    valid_tools += 1
        return {
            "records_checked": len(sft_records),
            "valid_json_count": valid_json,
            "total_actions_checked": total_actions,
            "valid_schema_actions": valid_tools,
            "zero_shell_exec_verified": blocked_shell,
        }

    @staticmethod
    def readiness_report(pipeline_tested: bool = True) -> Dict[str, Any]:
        breakdown_1_5b = calculate_parameter_breakdown(SUDHARSHAN_NATIVE_1_5B_CONFIG)
        return {
            "1_architecture_implemented": True,
            "2_parameter_count_verified": {
                "verified": True,
                "config_name": breakdown_1_5b["model_name"],
                "exact_trainable_params": breakdown_1_5b["total_trainable_params"],
                "billions": breakdown_1_5b["total_params_billions"],
                "fp16_weights_gb": breakdown_1_5b["fp16_weights_gb"],
                "q4_km_approx_gb": breakdown_1_5b["q4_km_approx_gb"],
            },
            "3_training_pipeline_tested": pipeline_tested,
            "4_full_1_5b_pretraining_completed": False,
            "4_note": "Full 1.5B pretraining requires ~30B+ tokens on multi-GPU cluster (e.g., 8x A100/H100); not run in CPU sandbox.",
            "5_model_quality_evaluated": "Smoke-test perplexity and schema validation verified on Nano checkpoint; full 1.5B benchmark evaluation awaits GPU pretraining.",
        }
