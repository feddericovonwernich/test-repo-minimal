"""Validate Scorecards workflow JSON from yq; no scoring or network writes.

Run: yq -o=json '.' .github/workflows/scorecards.yml | python3 tests/check_producer.py
This checks checkout/input semantics, not live evaluation or badge readiness.
"""

import json
import sys


def validate(workflow):
    steps = workflow["jobs"]["scorecard"]["steps"]
    checkouts = [step for step in steps if step.get("uses", "").startswith("actions/checkout@")]
    assert len(checkouts) == 2, "Expected separate service and platform checkouts"
    service, platform = checkouts
    service_inputs = service.get("with", {})
    platform_inputs = platform.get("with", {})
    assert service_inputs.get("path") == "service", "Service must have its own checkout root"
    assert not service_inputs.get("repository"), "Service must be the evaluated repository"
    assert not service_inputs.get("ref"), "Service must use the evaluated event revision"
    assert platform_inputs.get("path") == ".scorecards-platform", "Platform must be outside service"
    assert platform_inputs.get("repository") == "feddericovonwernich/scorecards", "Wrong suite repository"
    assert not platform_inputs.get("ref"), "Resolve the final central default-branch revision at run time"
    assert platform_inputs.get("persist-credentials") is False, "Do not persist catalog credentials"
    token = "${{ secrets.SCORECARDS_CATALOG_TOKEN }}"
    assert platform_inputs.get("token") == token, "Use the existing catalog credential"

    actions = [step for step in steps if step.get("id") == "scorecards"]
    assert len(actions) == 1, "Expected one scoring action"
    action = actions[0]
    assert action.get("uses") == "./.scorecards-platform/action", "Action must execute from the suite checkout"
    assert steps.index(service) < steps.index(platform) < steps.index(action), "Check out both sources before evaluation"
    for step in (service, platform, action):
        assert "if" not in step, "Required producer steps must not be conditionally skipped"
        assert not step.get("continue-on-error"), "Producer failures must fail the workflow"
    assert action.get("with") == {
        "github-token": token,
        "scorecards-repo": "feddericovonwernich/scorecards",
        "scorecards-branch": "catalog",
        "service-workspace": "${{ github.workspace }}/service",
    }, "Producer inputs must evaluate the service and publish to the central catalog"
    events = workflow["on"]
    assert set(events) == {"push", "schedule", "workflow_dispatch"}, "Scoring must not run on pull requests"
    assert set(events["push"]["branches"]) == {"main", "master"}, "Scoring must not run on feature pushes"


if __name__ == "__main__":
    try:
        validate(json.load(sys.stdin))
    except (AssertionError, KeyError, TypeError, ValueError) as error:
        sys.exit(f"Producer contract failed: {error}")
    print("Producer checkout and input contract passed (not a live evaluation).")
