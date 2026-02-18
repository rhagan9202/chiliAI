#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

REPO_NAME = "crushing-fraud-xai-accelerator"


def mkdirp(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text_if_missing(path: Path, content: str) -> bool:
    """
    Returns True if created, False if skipped (already exists).
    """
    mkdirp(path.parent)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as f:
            f.write(content)
        return True
    except FileExistsError:
        return False


def write_bytes_if_missing(path: Path, data: bytes) -> bool:
    """
    Returns True if created, False if skipped (already exists).
    """
    mkdirp(path.parent)
    try:
        with path.open("xb") as f:
            f.write(data)
        return True
    except FileExistsError:
        return False


def minimal_notebook_json(title: str) -> bytes:
    nb = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [f"# {title}\n", "\n", "Starter notebook.\n"],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["# Add your code here\n"],
            },
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return (json.dumps(nb, indent=2) + "\n").encode("utf-8")


def build_plan(root: Path) -> tuple[list[Path], dict[Path, str], dict[Path, bytes]]:
    repo_root = root / REPO_NAME

    dirs = [
        repo_root / "core" / "docs",
        repo_root / "core" / "templates",
        repo_root / "core" / "eval",
        repo_root / "core" / "monitoring",
        repo_root / "core" / "ui",
        repo_root / "domain-packs" / "medicare_ffs_claims",
        repo_root / "domain-packs" / "marketplace_agent_broker_enrollment",
        repo_root / "domain-packs" / "medicaid_dental_vision_claims",
        repo_root / "code-starters" / "notebooks",
        repo_root / "code-starters" / "pipelines",
        repo_root / "code-starters" / "iac",
    ]

    text_files: dict[Path, str] = {
        repo_root
        / "README.md": "# XAI Program Integrity Accelerator\n\nRepo scaffold.\n",
        repo_root
        / "CHANGELOG.md": "# Changelog\n\n## Unreleased\n- Initial scaffold.\n",
        # core/docs
        repo_root / "core" / "docs" / "00_overview.md": "# Overview\n\n",
        repo_root / "core" / "docs" / "01_roles-raci.md": "# Roles & RACI\n\n",
        repo_root
        / "core"
        / "docs"
        / "02_delivery-playbook.md": "# Delivery playbook\n\n",
        repo_root
        / "core"
        / "docs"
        / "03_indicator-contract.md": "# Indicator contract\n\n",
        repo_root
        / "core"
        / "docs"
        / "04_explainability-spec.md": "# Explainability spec\n\n",
        repo_root / "core" / "docs" / "05_eval-harness.md": "# Eval harness\n\n",
        repo_root / "core" / "docs" / "06_monitoring-ops.md": "# Monitoring & ops\n\n",
        repo_root
        / "core"
        / "docs"
        / "07_governance-change-control.md": "# Governance & change control\n\n",
        repo_root
        / "core"
        / "docs"
        / "08_security-privacy.md": "# Security & privacy\n\n",
        repo_root
        / "core"
        / "docs"
        / "09_reference-architecture_azure.md": "# Reference architecture (Azure)\n\n",
        repo_root
        / "core"
        / "docs"
        / "10_reference-architecture_aws.md": "# Reference architecture (AWS)\n\n",
        repo_root / "core" / "docs" / "11_ui-ux_spec.md": "# UI/UX spec\n\n",
        # core/templates
        repo_root
        / "core"
        / "templates"
        / "C01_use-case-canvas.md": "# C01 Use-case canvas\n\n",
        repo_root
        / "core"
        / "templates"
        / "C02_indicator-builder.md": "# C02 Indicator builder\n\n",
        repo_root
        / "core"
        / "templates"
        / "C03_high-impact-ai-screen.md": "# C03 High-impact AI screen\n\n",
        repo_root
        / "core"
        / "templates"
        / "C04_model-card-xai.md": "# C04 Model card (XAI)\n\n",
        repo_root
        / "core"
        / "templates"
        / "C05_data-provenance.md": "# C05 Data provenance\n\n",
        repo_root
        / "core"
        / "templates"
        / "C06_eval-plan-acceptance.md": "# C06 Eval plan & acceptance\n\n",
        repo_root
        / "core"
        / "templates"
        / "C07_go-live-checklist.md": "# C07 Go-live checklist\n\n",
        repo_root
        / "core"
        / "templates"
        / "C08_weekly-ops-review.md": "# C08 Weekly ops review\n\n",
        repo_root
        / "core"
        / "templates"
        / "C09_change-request.md": "# C09 Change request\n\n",
        # core/eval
        repo_root / "core" / "eval" / "scoring_rubric.md": "# Scoring rubric\n\n",
        repo_root
        / "core"
        / "eval"
        / "explanation_quality_rubric.md": "# Explanation quality rubric\n\n",
        # core/monitoring
        repo_root
        / "core"
        / "monitoring"
        / "telemetry_contract.md": "# Telemetry contract\n\n",
        repo_root
        / "core"
        / "monitoring"
        / "dashboards_spec.md": "# Dashboards spec\n\n",
        repo_root / "core" / "monitoring" / "drift_checks.md": "# Drift checks\n\n",
        repo_root
        / "core"
        / "monitoring"
        / "incident_runbook.md": "# Incident runbook\n\n",
        repo_root
        / "core"
        / "monitoring"
        / "pause_discontinue_policy.md": "# Pause/discontinue policy\n\n",
        # core/ui
        repo_root / "core" / "ui" / "screens_spec.md": "# Screens spec\n\n",
        repo_root / "core" / "ui" / "fields_dictionary.md": "# Fields dictionary\n\n",
        repo_root / "core" / "ui" / "api_contract.md": "# API contract (optional)\n\n",
        # domain packs
        repo_root
        / "domain-packs"
        / "medicare_ffs_claims"
        / "README.md": "# Medicare FFS claims\n\n",
        repo_root
        / "domain-packs"
        / "medicare_ffs_claims"
        / "schema.md": "# Schema\n\n",
        repo_root
        / "domain-packs"
        / "medicare_ffs_claims"
        / "feature_dictionary.md": "# Feature dictionary\n\n",
        repo_root
        / "domain-packs"
        / "medicare_ffs_claims"
        / "indicators_v0.1.md": "# Indicators v0.1\n\n",
        repo_root
        / "domain-packs"
        / "medicare_ffs_claims"
        / "eval_dataset_spec.md": "# Eval dataset spec\n\n",
        repo_root
        / "domain-packs"
        / "medicare_ffs_claims"
        / "evidence_bundle_spec.md": "# Evidence bundle spec\n\n",
        repo_root
        / "domain-packs"
        / "marketplace_agent_broker_enrollment"
        / "README.md": "# Marketplace agent/broker enrollment\n\n",
        repo_root
        / "domain-packs"
        / "marketplace_agent_broker_enrollment"
        / "schema.md": "# Schema\n\n",
        repo_root
        / "domain-packs"
        / "marketplace_agent_broker_enrollment"
        / "feature_dictionary.md": "# Feature dictionary\n\n",
        repo_root
        / "domain-packs"
        / "marketplace_agent_broker_enrollment"
        / "indicators_v0.1.md": "# Indicators v0.1\n\n",
        repo_root
        / "domain-packs"
        / "marketplace_agent_broker_enrollment"
        / "eval_dataset_spec.md": "# Eval dataset spec\n\n",
        repo_root
        / "domain-packs"
        / "marketplace_agent_broker_enrollment"
        / "evidence_bundle_spec.md": "# Evidence bundle spec\n\n",
        repo_root
        / "domain-packs"
        / "medicaid_dental_vision_claims"
        / "README.md": "# Medicaid dental/vision claims\n\n",
        repo_root
        / "domain-packs"
        / "medicaid_dental_vision_claims"
        / "schema.md": "# Schema\n\n",
        repo_root
        / "domain-packs"
        / "medicaid_dental_vision_claims"
        / "feature_dictionary.md": "# Feature dictionary\n\n",
        repo_root
        / "domain-packs"
        / "medicaid_dental_vision_claims"
        / "indicators_v0.1.md": "# Indicators v0.1\n\n",
        repo_root
        / "domain-packs"
        / "medicaid_dental_vision_claims"
        / "eval_dataset_spec.md": "# Eval dataset spec\n\n",
        repo_root
        / "domain-packs"
        / "medicaid_dental_vision_claims"
        / "evidence_bundle_spec.md": "# Evidence bundle spec\n\n",
        # code-starters
        repo_root
        / "code-starters"
        / "pipelines"
        / "pipeline_skeleton.md": "# Pipeline skeleton\n\n",
        repo_root
        / "code-starters"
        / "iac"
        / "terraform_skeleton.md": "# Terraform skeleton\n\n",
    }

    # A lightweight "spec" CSV (header + one example row).
    # Adjust columns to your internal contract as needed.
    text_files[repo_root / "core" / "eval" / "testset_format.csv"] = (
        "record_id,domain,entity_id,as_of_date,label,notes\n"
        "ex_0001,medicare_ffs_claims,12345,2026-01-01,0,example row\n"
    )

    binary_files: dict[Path, bytes] = {
        repo_root
        / "code-starters"
        / "notebooks"
        / "01_build_features.ipynb": minimal_notebook_json("01 Build features"),
        repo_root
        / "code-starters"
        / "notebooks"
        / "02_score_indicators.ipynb": minimal_notebook_json("02 Score indicators"),
        repo_root
        / "code-starters"
        / "notebooks"
        / "03_generate_explanations.ipynb": minimal_notebook_json(
            "03 Generate explanations"
        ),
    }

    return dirs, text_files, binary_files


def create_repo(root: Path) -> None:
    dirs, text_files, binary_files = build_plan(root)

    created = 0
    skipped = 0

    for d in dirs:
        mkdirp(d)

    for path, content in sorted(text_files.items(), key=lambda x: str(x[0])):
        if write_text_if_missing(path, content):
            created += 1
            print(f"CREATE  {path}")
        else:
            skipped += 1
            print(f"SKIP    {path} (exists)")

    for path, data in sorted(binary_files.items(), key=lambda x: str(x[0])):
        if write_bytes_if_missing(path, data):
            created += 1
            print(f"CREATE  {path}")
        else:
            skipped += 1
            print(f"SKIP    {path} (exists)")

    print(f"\nDone. Created {created} files, skipped {skipped} existing files.")
    print(f"Repo root: {(root / REPO_NAME).resolve()}")


if __name__ == "__main__":
    # Creates ./crushing-fraud-xai-accelerator by default.
    create_repo(Path.cwd())
