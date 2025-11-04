"""Integration tests using the scenario DSL."""

import tempfile
from pathlib import Path

import pytest

from shots_dashboard.scenario_dsl import (
    AssertFileCount, AssertFileState, CreateFile, CreateTimeline,
    Scenario, ScanDirectory, UpdateFromTimeline, create_basic_workflow_scenario,
    create_state_transition_scenario
)
from shots_dashboard.scenario_interpreters import FileSystemInterpreter, SimulatedInterpreter


@pytest.mark.integration
class TestScenarioExecution:
    """Test executing scenarios with both interpreters."""

    def test_basic_workflow_with_filesystem(self, tmp_path: Path) -> None:
        """Test basic workflow on filesystem."""
        db_path = tmp_path / "test.json"
        scenario = create_basic_workflow_scenario(tmp_path)

        interpreter = FileSystemInterpreter(db_path)
        result = interpreter.execute(scenario)

        assert result["success"]
        assert result["final_state"]["stats"]["total"] == 3
        assert result["final_state"]["stats"]["in_use"] == 2

    def test_basic_workflow_with_simulation(self) -> None:
        """Test basic workflow in simulation."""
        base_dir = Path("test")
        scenario = create_basic_workflow_scenario(base_dir)

        interpreter = SimulatedInterpreter()
        result = interpreter.execute(scenario)

        assert result["success"]
        assert result["final_state"]["stats"]["total"] == 3
        assert result["final_state"]["stats"]["in_use"] == 2

    def test_state_transitions_simulation(self) -> None:
        """Test state transitions in simulation."""
        base_dir = Path("test")
        scenario = create_state_transition_scenario(base_dir)

        interpreter = SimulatedInterpreter()
        result = interpreter.execute(scenario)

        assert result["success"]
        # Final state should be IN_USE (after REMOVED → IN_USE transition)
        state = result["final_state"]
        assert state["stats"]["in_use"] == 1

    def test_custom_scenario(self, tmp_path: Path) -> None:
        """Test a custom scenario."""
        scenario = Scenario(
            name="custom",
            description="Custom test scenario",
            actions=[
                CreateFile(tmp_path / "media" / "test.mov"),
                ScanDirectory(tmp_path / "media"),
                AssertFileCount("TOTAL", 1),
                AssertFileCount("NEW", 1),
                CreateTimeline(tmp_path / "timeline.otio", ("test.mov",)),
                UpdateFromTimeline(tmp_path / "timeline.otio"),
                AssertFileCount("IN_USE", 1),
                AssertFileState(tmp_path / "media" / "test.mov", "IN_USE"),
            ]
        )

        db_path = tmp_path / "test.json"
        interpreter = FileSystemInterpreter(db_path)
        result = interpreter.execute(scenario)

        assert result["success"]

    def test_scenario_with_multiple_timelines(self, tmp_path: Path) -> None:
        """Test scenario with multiple timeline versions."""
        scenario = Scenario(
            name="multiple_timelines",
            description="Test with multiple timeline versions",
            actions=[
                # Create files
                CreateFile(tmp_path / "media" / "shot1.mov"),
                CreateFile(tmp_path / "media" / "shot2.mov"),
                CreateFile(tmp_path / "media" / "shot3.mov"),
                ScanDirectory(tmp_path / "media"),

                # Timeline v1: shots 1 and 2
                CreateTimeline(tmp_path / "v1.otio", ("shot1.mov", "shot2.mov")),
                UpdateFromTimeline(tmp_path / "v1.otio"),
                AssertFileCount("IN_USE", 2),
                AssertFileCount("NEW", 1),

                # Timeline v2: shots 2 and 3 (shot 1 removed, shot 3 added)
                CreateTimeline(tmp_path / "v2.otio", ("shot2.mov", "shot3.mov")),
                UpdateFromTimeline(tmp_path / "v2.otio"),
                AssertFileCount("IN_USE", 2),
                AssertFileCount("REMOVED", 1),
                AssertFileState(tmp_path / "media" / "shot1.mov", "REMOVED"),
                AssertFileState(tmp_path / "media" / "shot3.mov", "IN_USE"),
            ]
        )

        db_path = tmp_path / "test.json"
        interpreter = FileSystemInterpreter(db_path)
        result = interpreter.execute(scenario)

        assert result["success"]
