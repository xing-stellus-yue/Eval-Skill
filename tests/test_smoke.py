"""Offline integration checks: real CLI/HTTP client, synthetic data and judge."""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading

from datasets import Dataset, DatasetDict
import pytest

from src.eval_skill.eval_process import split_think_output
from src.eval_skill.managers.extraction_manager import parse_skill_branches


ROOT = Path(__file__).resolve().parents[1]
SUBSETS = ["chat", "chat-hard", "reasoning", "dangerous"]
RB2_SUBSETS = ["Factuality", "Focus", "Math", "Precise IF", "Safety"]
DEMO_DOMAINS = {
    "rewardbench2": RB2_SUBSETS,
    "rewardbench": SUBSETS,
    "judgebench": ["mixed"],
    "rmbench": ["chat", "safety", "math", "code"],
}


@pytest.mark.parametrize("content, expected", [
    ("Winner: A", ("Winner: A", "")),
    ("<think>check</think>Winner: B", ("Winner: B", "check")),
    ("<think>first</think><think>second</think>Winner: A",
     ("Winner: A", "first</think><think>second")),
])
def test_thinking_output(content, expected):
    assert split_think_output(content, "evaluation") == expected


@pytest.mark.parametrize("prefix, suffix", [
    ("", ""),
    ("thought\n[Planning notes]\n```json\n", "\n```\n[Done]"),
])
def test_skill_branch_json_with_prose(prefix, suffix):
    branches = [{"skill": "Check [constraints] and quoted \"answers\"", "inspired_by": [1]},
                {"skill": "Verify factual correctness", "inspired_by": [2]}]
    assert parse_skill_branches(prefix + json.dumps(branches) + suffix, 2) == branches


@pytest.mark.parametrize("content", ["no JSON", "[1, 2]", '[{"skill": ""}]',
                                     '[{"skill": "only one"}]'])
def test_skill_branch_json_rejects_invalid_or_insufficient_branches(content):
    with pytest.raises(ValueError, match="nonempty skill objects"):
        parse_skill_branches(content, 2)


@pytest.fixture
def local_runtime(tmp_path, monkeypatch):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(request)
            prompt = request["messages"][0]["content"]
            match = re.search(r"--- Response ([A-D]) ---\nGOOD_MARKER", prompt)
            if match:
                content = f"--- Final Judgment ---\nWinner: Response {match[1]}"
            elif "**Task:** Extract" in prompt:
                content = "1. The response must answer the question correctly. [Core Requirement]"
            else:
                content = "GOOD_MARKER"
            body = json.dumps({"id": "offline", "object": "chat.completion", "created": 0,
                               "model": "offline-judge", "choices": [{"index": 0,
                               "message": {"role": "assistant", "content": content},
                               "finish_reason": "stop"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for role in ["JUDGE", "RUBRIC", "EXTRACTION", "SUPER_JUDGE", "GENERATION", "FJ"]:
        monkeypatch.setenv(role + "_MODEL_NAME", "offline-judge")
        monkeypatch.setenv(role + "_API_BASE", f"http://127.0.0.1:{server.server_port}/v1")
        monkeypatch.setenv(role + "_API_KEY", "offline")
        monkeypatch.setenv(role + "_THINK", "false")
    data_dir = tmp_path / "data"
    for name, domains in DEMO_DOMAINS.items():
        benchmark = name + "_aug"
        rows = [{"id": f"{subset}-{split}", "subset": subset, "use": split,
                 "prompt": "Choose the correct answer.", "response_a": ["GOOD_MARKER"] * 3 if name == "rmbench" else "GOOD_MARKER",
                 "response_b": ["WRONG_1", "WRONG_2", "WRONG_3"] if name in {"rewardbench2", "rmbench"} else "WRONG"}
                for subset in domains
                for split in ["train", "test"]]
        DatasetDict(test=Dataset.from_list(rows)).save_to_disk(str(data_dir / benchmark))
    monkeypatch.setenv("EVAL_SKILL_DATA_DIR", str(data_dir))
    try:
        yield tmp_path, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def run_cli(*args):
    result = subprocess.run([sys.executable, "-m", *args], cwd=ROOT, env=os.environ.copy(),
                            capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.mark.parametrize("benchmark", ["rewardbench_aug", "rewardbench2_aug"])
@pytest.mark.parametrize("mode", ["vanilla", "rubric_based"])
def test_baseline_cli_and_resume(local_runtime, benchmark, mode):
    tmp_path, requests = local_runtime
    args = ("src.eval_skill", "evaluate", "--mode", mode, "--benchmark", benchmark,
            "--trial-num", "1", "--result-base", str(tmp_path / "results"),
            "--setting-name", "offline", "--raise-on-error")
    run_cli(*args)
    output = tmp_path / "results/offline" / benchmark
    summary = json.loads((output / "summary.json").read_text())
    expected_cases = 5 if benchmark == "rewardbench2_aug" else 4
    assert summary["total_cases"] == expected_cases
    assert summary["correct_count"] == expected_cases
    assert summary["skipped_due_to_llm_call_failure"] == 0
    assert summary["unexpected_count"] == 0
    rollouts = list((output / "rollouts").glob("*.json"))
    assert len(rollouts) == expected_cases
    assert all(json.loads(p.read_text())["id"].endswith("-test") for p in rollouts)
    request_count = len(requests)
    assert request_count == expected_cases * (2 if mode == "rubric_based" else 1)
    run_cli(*args)
    assert len(requests) == request_count, "A resumed run should reuse completed rollouts"


@pytest.mark.parametrize("benchmark, subset", [
    (benchmark, subset) for benchmark, domains in DEMO_DOMAINS.items() for subset in domains
])
def test_saved_skill_injection(local_runtime, benchmark, subset):
    tmp_path, requests = local_runtime
    run_cli("examples.evaluate_demo_skill", "--benchmark", benchmark, "--subset", subset, "--samples", "1",
            "--result-base", str(tmp_path / "demo"))
    output = tmp_path / "demo" / benchmark / subset
    summary = json.loads((output / "summary.json").read_text())
    assert summary["correct"] == 1
    assert summary["unexpected"] == 0
    assert summary["benchmark"] == benchmark + "_aug"
    rollout = json.loads(next((output / "rollouts").glob("*.json")).read_text())
    assert len(rollout["options"]) == (4 if benchmark == "rewardbench2" else 2)
    assert rollout["id"].endswith("-test")
    skill = (ROOT / "src/eval_skill/demo_skills" / benchmark / f"{subset.replace(' ', '_')}.md").read_text()
    assert len(requests) == 1
    assert skill in requests[0]["messages"][0]["content"]



@pytest.mark.parametrize("benchmark", DEMO_DOMAINS)
def test_skill_artifact_bytes(benchmark):
    folder = ROOT / "src/eval_skill/demo_skills" / benchmark
    records = json.loads((folder / "provenance.json").read_text())["skills"]
    assert {r["domain"] for r in records} == set(DEMO_DOMAINS[benchmark])
    for record in records:
        assert record["judge_model"] == "Qwen3-8B"
        assert hashlib.sha256((folder / record["file"]).read_bytes()).hexdigest() == record["sha256"]


def test_demo_defaults_to_rewardbench2_factuality(local_runtime):
    tmp_path, _ = local_runtime
    run_cli("examples.evaluate_demo_skill", "--samples", "1", "--result-base", str(tmp_path / "demo"))
    result = json.loads((tmp_path / "demo/rewardbench2/Factuality/summary.json").read_text())
    assert result["benchmark"] == "rewardbench2_aug"
    assert result["correct"] == 1


def test_best_of_n_generation_selection_summary_and_resume(local_runtime):
    tmp_path, requests = local_runtime
    subset = tmp_path / "skills/rewardbench_aug/chat"
    (subset / "test_best_workflow_only_skill_b0").mkdir(parents=True)
    (subset / "step1a_workflow_gen").mkdir()
    (subset / "step1a_workflow_gen/top_k_sel_skills.json").write_text(json.dumps([
        {"branch_id": 0, "evo_acc": 1.0, "skill": "Compare factual correctness and choose one winner."}
    ]))
    output = tmp_path / "best_of_n"
    args = ("src.eval_skill", "best-of-n", "--benchmark", "rewardbench_aug", "--subset", "chat",
            "--method", "workflow_only", "--result-base", str(tmp_path / "skills"),
            "--candidate-num", "2", "--sample-num", "1", "--trial-num", "1",
            "--candidate-workers", "1", "--max-workers", "1",
            "--candidate-cache-dir", str(tmp_path / "candidates"), "--output-dir", str(output))
    run_cli(*args)
    row = json.loads((output / "rollouts/compare_0_trial_0.json").read_text())
    assert row["status"] == "ok"
    assert len(row["candidates"]) == 2
    assert row["skill_runner"]["best_idx"] is not None
    assert row["vanilla_runner"]["best_idx"] is not None
    assert row["final_compare"]["winner_runner"] == "tie"
    summary = json.loads((output / "summary.json").read_text())
    assert summary["results"]["ok"] == 1
    assert summary["results"]["unknown_wins"] == 0
    request_count = len(requests)
    assert request_count == 4  # Two generated candidates and two selector calls.
    skill_text = "Compare factual correctness and choose one winner."
    assert sum(skill_text in r["messages"][0]["content"] for r in requests) == 1
    run_cli(*args)
    assert len(requests) == request_count
