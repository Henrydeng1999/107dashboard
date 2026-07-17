from pathlib import Path

import pytest

from app.slurm.parsers import (
    SlurmParseError,
    parse_sacct,
    parse_sacct_usage,
    parse_sinfo,
    parse_squeue,
)

FIXTURE_DIRECTORY = Path(__file__).parents[3] / "fixtures" / "slurm"


def _fixture(name: str) -> str:
    return (FIXTURE_DIRECTORY / name).read_text(encoding="utf-8")


def test_parse_squeue_extracts_status_nodes_and_resources() -> None:
    jobs = parse_squeue(_fixture("squeue.txt"))

    assert len(jobs) == 2
    assert jobs[0].job_id == "900001"
    assert jobs[0].state == "RUNNING"
    assert jobs[0].nodes == "demo-node-01"
    assert jobs[0].partition == "demo-students"
    assert jobs[0].allocated is not None
    assert jobs[0].allocated.cpus == 2
    assert jobs[0].allocated.memory_mb is None
    assert jobs[0].requested is not None
    assert jobs[0].requested.cpus is None
    assert jobs[0].requested.memory_mb == 4096
    assert jobs[0].requested.gpus == 1
    assert jobs[1].nodes is None
    assert jobs[1].reason == "Resources"


def test_parse_squeue_accepts_empty_output() -> None:
    assert parse_squeue(_fixture("squeue_empty.txt")) == []


def test_parse_squeue_routes_pending_cpus_to_requested_resources() -> None:
    job = parse_squeue("1|job|PENDING|user|demo-students|demo-account|demo-qos|||3|512||00:10:00")[
        0
    ]

    assert job.requested is not None
    assert job.requested.cpus == 3
    assert job.allocated is not None
    assert job.allocated.cpus is None


def test_parse_squeue_routes_running_cpus_to_allocated_resources() -> None:
    job = parse_squeue(
        "1|job|RUNNING|user|demo-students|demo-account|demo-qos|demo-node|None|3|512||00:10:00"
    )[0]

    assert job.requested is not None
    assert job.requested.cpus is None
    assert job.allocated is not None
    assert job.allocated.cpus == 3


def test_parse_squeue_treats_unitless_slurm_memory_as_megabytes() -> None:
    job = parse_squeue("1|job|PENDING|user|demo-students|demo-account|demo-qos|||1|512||00:10:00")[
        0
    ]

    assert job.requested is not None
    assert job.requested.memory_mb == 512


def test_parse_sacct_accepts_missing_trailing_fields() -> None:
    jobs = parse_sacct(_fixture("sacct.txt"))

    assert jobs[0].exit_code == "0:0"
    assert jobs[0].elapsed == "00:12:31"
    assert jobs[0].requested is not None
    assert jobs[0].requested.cpus == 2
    assert jobs[0].requested.memory_mb == 4096
    assert jobs[0].requested.gpus == 1
    assert jobs[0].allocated is not None
    assert jobs[0].allocated.cpus == 2
    assert jobs[0].allocated.memory_mb == 4096
    assert jobs[0].allocated.gpus == 1
    assert jobs[1].state == "FAILED"
    assert jobs[2].state == "CANCELLED"
    assert jobs[2].job_id == "899997"
    assert jobs[2].exit_code is None
    assert jobs[2].requested is not None
    assert jobs[2].requested.cpus is None


def test_parse_sacct_usage_preserves_allocation_and_step_metrics() -> None:
    records = parse_sacct_usage(_fixture("sacct_usage.txt"))

    allocation = records[0]
    batch = records[1]
    assert allocation.job_id == "899998"
    assert allocation.requested is not None
    assert allocation.requested.memory_mb == 4096
    assert allocation.allocated is not None
    assert allocation.allocated.cpus == 2
    assert allocation.allocated.gpus == 1
    assert allocation.elapsed_seconds == 751
    assert allocation.time_limit_seconds == 3600
    assert batch.job_id == "899998.batch"
    assert batch.max_rss_kb == 768 * 1024
    assert batch.total_cpu_seconds == 1122.5


def test_parse_sacct_usage_rejects_malformed_duration() -> None:
    with pytest.raises(SlurmParseError, match="invalid Elapsed duration"):
        parse_sacct_usage("1|job|COMPLETED|soon||||||||||")


def test_parse_sinfo_strips_default_marker_and_accepts_missing_gres() -> None:
    partitions = parse_sinfo(_fixture("sinfo.txt"))

    assert partitions[0].name == "demo-students"
    assert partitions[0].node_count == 12
    assert partitions[0].memory_mb == 512000
    assert partitions[1].gres is None


def test_parse_gpu_tres_does_not_double_count_generic_and_typed_entries() -> None:
    output = (
        "1|job|COMPLETED|demo-user|demo-students|demo-account|demo-qos|demo-node-01|0:0|"
        "cpu=2,mem=4G,gres/gpu=2,gres/gpu:model-a=1,gres/gpu:model-b=1|"
        "cpu=2,mem=4G,gres/gpu=2,gres/gpu:model-a=1,gres/gpu:model-b=1|"
        "01:00:00|00:10:00|None"
    )

    job = parse_sacct(output)[0]

    assert job.requested is not None
    assert job.requested.gpus == 2
    assert job.allocated is not None
    assert job.allocated.gpus == 2


def test_parse_gpu_tres_sums_typed_entries_when_generic_total_is_absent() -> None:
    job = parse_squeue(
        "1|job|RUNNING|demo-user|demo-students|demo-account|demo-qos|demo-node-01|None|"
        "2|4G|gpu:model-a:1,gpu:model-b:2|01:00:00"
    )[0]

    assert job.requested is not None
    assert job.requested.gpus == 3


@pytest.mark.parametrize(
    "output",
    [
        "1|job|RUNNING|user|partition|account|qos|node|None|two|4G||01:00:00",
        "1|job|RUNNING|user|partition|account|qos|node|None|2|lots||01:00:00",
        "1|job|RUNNING|user|partition|account|qos|node|None|2|4G|gpu:model:many|01:00:00",
    ],
)
def test_parse_squeue_rejects_malformed_nonempty_numeric_values(output: str) -> None:
    with pytest.raises(SlurmParseError, match="Malformed squeue output on line 1"):
        parse_squeue(output)


def test_parse_sinfo_rejects_malformed_numeric_value() -> None:
    with pytest.raises(SlurmParseError, match="invalid node count integer"):
        parse_sinfo("demo*|up|idle|many|0/0/0/0|1024|")


@pytest.mark.parametrize("tres", ["cpu=many,mem=4G", "cpu=2,mem=lots", "gres/gpu=many"])
def test_parse_sacct_rejects_malformed_tres_numeric_values(tres: str) -> None:
    output = (
        "1|job|COMPLETED|user|partition|account|qos|node|0:0|"
        f"{tres}|cpu=2,mem=4G|01:00:00|00:10:00|None"
    )

    with pytest.raises(SlurmParseError, match="Malformed sacct output on line 1"):
        parse_sacct(output)


def test_parser_rejects_extra_fields_instead_of_silently_truncating() -> None:
    output = "1|job|PENDING|user|partition|account|qos|||1|512||00:10:00|unexpected"

    with pytest.raises(SlurmParseError, match="expected at most 13 fields, got 14"):
        parse_squeue(output)


@pytest.mark.parametrize(
    ("slurm_state", "expected"),
    [
        ("COMPLETING+", "RUNNING"),
        ("CANCELLED by 4242", "CANCELLED"),
        ("OUT_OF_MEMORY", "FAILED"),
        ("DEADLINE", "TIMEOUT"),
        ("UNKNOWN", "UNKNOWN"),
        ("brand_new_state", "UNKNOWN"),
    ],
)
def test_parser_normalizes_slurm_states(slurm_state: str, expected: str) -> None:
    output = f"1|job|{slurm_state}|user|partition|account|qos|node|None|1|512||00:10:00"

    assert parse_squeue(output)[0].state == expected
