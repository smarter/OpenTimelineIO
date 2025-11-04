"""
Property-based tests using Hypothesis to compare simulated and actual interpreters.

Generates random scenarios and verifies that both interpreters produce
equivalent results.
"""

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, strategies as st, settings, assume

from shots_dashboard.scenario_dsl import (
    AssertFileCount, AssertFileState, CreateFile, CreateTimeline,
    Scenario, ScanDirectory, UpdateFromTimeline
)
from shots_dashboard.scenario_interpreters import (
    FileSystemInterpreter, SimulatedInterpreter
)


# Hypothesis strategies for generating scenarios

@st.composite
def file_path_strategy(draw, base_dir="media"):
    """Generate a valid file path."""
    filename = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), blacklist_characters="."),
        min_size=1,
        max_size=10
    ))
    extension = draw(st.sampled_from([".mov", ".mp4", ".mxf"]))
    return Path(base_dir) / f"{filename}{extension}"


@st.composite
def create_file_action(draw, base_dir=Path("test")):
    """Generate a CreateFile action."""
    rel_path = draw(file_path_strategy())
    return CreateFile(base_dir / rel_path)


@st.composite
def create_timeline_action(draw, base_dir=Path("test"), available_files=None):
    """Generate a CreateTimeline action."""
    if available_files is None or len(available_files) == 0:
        clip_names = ()
    else:
        # Select a subset of available files
        num_clips = draw(st.integers(min_value=0, max_value=min(5, len(available_files))))
        selected = draw(st.lists(
            st.sampled_from(available_files),
            min_size=num_clips,
            max_size=num_clips,
            unique=True
        ))
        clip_names = tuple(f.name for f in selected)

    timeline_name = draw(st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        min_size=1,
        max_size=10
    ))

    return CreateTimeline(base_dir / f"{timeline_name}.otio", clip_names)


@st.composite
def simple_scenario_strategy(draw):
    """Generate a simple scenario with file operations."""
    base_dir = Path("test")

    # Generate 1-5 files
    num_files = draw(st.integers(min_value=1, max_value=5))
    files = [draw(create_file_action(base_dir)) for _ in range(num_files)]

    # Scan directory
    scan = ScanDirectory(base_dir / "media")

    # Optionally create a timeline
    create_timeline = None
    update_timeline = None
    if draw(st.booleans()):
        file_paths = [f.path for f in files]
        timeline_action = draw(create_timeline_action(base_dir, file_paths))
        create_timeline = timeline_action
        update_timeline = UpdateFromTimeline(timeline_action.path)

    # Build action list
    actions = files + [scan]
    if create_timeline:
        actions.append(create_timeline)
        if update_timeline:
            actions.append(update_timeline)

    return Scenario(
        name="generated_scenario",
        description="Hypothesis-generated scenario",
        base_dir=base_dir,
        actions=actions
    )


@pytest.mark.property
class TestScenarioEquivalence:
    """Property tests comparing simulated and filesystem interpreters."""

    @given(simple_scenario_strategy())
    @settings(max_examples=50, deadline=None)
    def test_interpreters_produce_same_stats(self, scenario: Scenario) -> None:
        """
        Property: Both interpreters should produce the same statistics.

        This is the key invariant - whether we simulate or actually touch
        the filesystem, the final state should be identical.
        """
        # Run simulation
        sim_interp = SimulatedInterpreter()
        sim_result = sim_interp.execute(scenario)
        sim_state = sim_result["final_state"]

        # Run on actual filesystem
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = tmp_path / "test_db.json"

            # Adjust paths to actual temp directory
            adjusted_actions = []
            for action in scenario.actions:
                if hasattr(action, 'path'):
                    # Replace base_dir with actual temp dir
                    new_path = tmp_path / action.path.relative_to(Path("test"))

                    if isinstance(action, CreateFile):
                        adjusted_actions.append(CreateFile(new_path))
                    elif isinstance(action, ScanDirectory):
                        adjusted_actions.append(ScanDirectory(new_path))
                    elif isinstance(action, UpdateFromTimeline):
                        adjusted_actions.append(UpdateFromTimeline(new_path))
                    elif isinstance(action, CreateTimeline):
                        adjusted_actions.append(
                            CreateTimeline(new_path, action.clip_names)
                        )
                else:
                    adjusted_actions.append(action)

            adjusted_scenario = Scenario(
                name=scenario.name,
                description=scenario.description,
                base_dir=tmp_path,
                actions=adjusted_actions
            )

            fs_interp = FileSystemInterpreter(db_path)
            fs_result = fs_interp.execute(adjusted_scenario)
            fs_state = fs_result["final_state"]

        # Assert states are equivalent
        assert sim_state["stats"] == fs_state["stats"], \
            f"Stats differ:\nSim: {sim_state['stats']}\nFS:  {fs_state['stats']}"

        # File lists should have same lengths
        for state_name in ["new", "in_use", "removed"]:
            sim_count = len(sim_state["files"][state_name])
            fs_count = len(fs_state["files"][state_name])
            assert sim_count == fs_count, \
                f"{state_name} files differ: sim={sim_count}, fs={fs_count}"

    def test_basic_workflow_equivalence(self) -> None:
        """Test that a basic workflow produces equivalent results."""
        base_dir = Path("test")

        scenario = Scenario(
            name="basic_test",
            description="Basic test",
            base_dir=base_dir,
            actions=[
                CreateFile(base_dir / "media" / "file1.mov"),
                CreateFile(base_dir / "media" / "file2.mov"),
                ScanDirectory(base_dir / "media"),
                CreateTimeline(base_dir / "timeline.otio", ("file1.mov",)),
                UpdateFromTimeline(base_dir / "timeline.otio"),
                AssertFileCount("IN_USE", 1),
                AssertFileCount("NEW", 1),
            ]
        )

        # Run simulation
        sim_interp = SimulatedInterpreter()
        sim_result = sim_interp.execute(scenario)

        # Run on filesystem
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = tmp_path / "test_db.json"

            # Adjust paths
            adjusted_actions = [
                CreateFile(tmp_path / "media" / "file1.mov"),
                CreateFile(tmp_path / "media" / "file2.mov"),
                ScanDirectory(tmp_path / "media"),
                CreateTimeline(tmp_path / "timeline.otio", ("file1.mov",)),
                UpdateFromTimeline(tmp_path / "timeline.otio"),
                AssertFileCount("IN_USE", 1),
                AssertFileCount("NEW", 1),
            ]

            adjusted_scenario = Scenario(
                name="basic_test",
                description="Basic test",
                base_dir=tmp_path,
                actions=adjusted_actions
            )

            fs_interp = FileSystemInterpreter(db_path)
            fs_result = fs_interp.execute(adjusted_scenario)

        # Both should succeed
        assert sim_result["success"]
        assert fs_result["success"]

        # Stats should match
        assert sim_result["final_state"]["stats"] == fs_result["final_state"]["stats"]


@pytest.mark.unit
class TestScenarioActions:
    """Unit tests for individual scenario actions."""

    def test_create_file_in_simulation(self) -> None:
        """Test CreateFile in simulation."""
        interp = SimulatedInterpreter()
        scenario = Scenario(
            name="test",
            description="test",
            actions=[CreateFile(Path("test/file.mov"))]
        )

        result = interp.execute(scenario)
        assert result["success"]
        assert Path("test/file.mov") in interp.files

    def test_scan_directory_finds_files(self) -> None:
        """Test ScanDirectory finds created files."""
        interp = SimulatedInterpreter()
        scenario = Scenario(
            name="test",
            description="test",
            actions=[
                CreateFile(Path("test/media/f1.mov")),
                CreateFile(Path("test/media/f2.mov")),
                ScanDirectory(Path("test/media")),
                AssertFileCount("TOTAL", 2),
            ]
        )

        result = interp.execute(scenario)
        assert result["success"]

    def test_timeline_update_changes_state(self) -> None:
        """Test UpdateFromTimeline changes file states."""
        interp = SimulatedInterpreter()
        scenario = Scenario(
            name="test",
            description="test",
            actions=[
                CreateFile(Path("test/media/file1.mov")),
                ScanDirectory(Path("test/media")),
                CreateTimeline(Path("test/timeline.otio"), ("file1.mov",)),
                UpdateFromTimeline(Path("test/timeline.otio")),
                AssertFileState(Path("test/media/file1.mov"), "IN_USE"),
            ]
        )

        result = interp.execute(scenario)
        assert result["success"]
