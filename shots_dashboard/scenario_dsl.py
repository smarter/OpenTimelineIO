"""
Scenario DSL for declarative testing and demonstration.

Provides a mini-language for describing test/demo scenarios that can be:
1. Simulated in-memory for fast testing
2. Executed on actual filesystem for demos
3. Property-tested with Hypothesis to ensure equivalence
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Protocol, Any

import opentimelineio as otio


class ActionType(Enum):
    """Types of scenario actions."""
    CREATE_FILE = auto()
    CREATE_TIMELINE = auto()
    SCAN_DIRECTORY = auto()
    UPDATE_FROM_TIMELINE = auto()
    WAIT = auto()
    ASSERT_FILE_STATE = auto()
    ASSERT_FILE_COUNT = auto()


@dataclass(frozen=True)
class ScenarioAction:
    """Base class for scenario actions."""
    action_type: ActionType


@dataclass(frozen=True)
class CreateFile(ScenarioAction):
    """Create a file at the specified path."""
    path: Path
    action_type: ActionType = field(default=ActionType.CREATE_FILE, init=False)


@dataclass(frozen=True)
class CreateTimeline(ScenarioAction):
    """Create an OTIO timeline file with specified clips."""
    path: Path
    clip_names: tuple[str, ...]  # Tuple for immutability
    action_type: ActionType = field(default=ActionType.CREATE_TIMELINE, init=False)


@dataclass(frozen=True)
class ScanDirectory(ScenarioAction):
    """Scan a directory for media files."""
    path: Path
    action_type: ActionType = field(default=ActionType.SCAN_DIRECTORY, init=False)


@dataclass(frozen=True)
class UpdateFromTimeline(ScenarioAction):
    """Update file states from a timeline."""
    path: Path
    action_type: ActionType = field(default=ActionType.UPDATE_FROM_TIMELINE, init=False)


@dataclass(frozen=True)
class Wait(ScenarioAction):
    """Wait for specified seconds (for visual demos)."""
    seconds: float
    action_type: ActionType = field(default=ActionType.WAIT, init=False)


@dataclass(frozen=True)
class AssertFileState(ScenarioAction):
    """Assert a file is in expected state."""
    path: Path
    expected_state: str  # 'NEW', 'IN_USE', 'REMOVED'
    action_type: ActionType = field(default=ActionType.ASSERT_FILE_STATE, init=False)


@dataclass(frozen=True)
class AssertFileCount(ScenarioAction):
    """Assert the number of files in a state."""
    state: str  # 'NEW', 'IN_USE', 'REMOVED', 'TOTAL'
    expected_count: int
    action_type: ActionType = field(default=ActionType.ASSERT_FILE_COUNT, init=False)


@dataclass
class Scenario:
    """A complete scenario with name, description, and actions."""
    name: str
    description: str
    actions: list[ScenarioAction]
    base_dir: Path | None = None  # Base directory for relative paths


class ScenarioInterpreter(Protocol):
    """Protocol for scenario interpreters."""

    def execute(self, scenario: Scenario) -> dict[str, Any]:
        """Execute a scenario and return results."""
        ...

    def get_state(self) -> dict[str, Any]:
        """Get current state after execution."""
        ...


# Standard scenarios for testing and demos

def create_basic_workflow_scenario(base_dir: Path) -> Scenario:
    """Create a basic workflow scenario."""
    return Scenario(
        name="basic_workflow",
        description="Basic workflow: scan, update from timeline",
        base_dir=base_dir,
        actions=[
            # Create some files
            CreateFile(base_dir / "media" / "shot_001.mov"),
            CreateFile(base_dir / "media" / "shot_002.mov"),
            CreateFile(base_dir / "media" / "shot_003.mov"),

            # Scan directory
            ScanDirectory(base_dir / "media"),

            # Assert all files are NEW
            AssertFileCount("NEW", 3),
            AssertFileCount("IN_USE", 0),

            # Create timeline with some shots
            CreateTimeline(
                base_dir / "timeline_v1.otio",
                ("shot_001.mov", "shot_002.mov")
            ),

            # Update from timeline
            UpdateFromTimeline(base_dir / "timeline_v1.otio"),

            # Assert state changes
            AssertFileState(base_dir / "media" / "shot_001.mov", "IN_USE"),
            AssertFileState(base_dir / "media" / "shot_002.mov", "IN_USE"),
            AssertFileState(base_dir / "media" / "shot_003.mov", "NEW"),
            AssertFileCount("IN_USE", 2),
            AssertFileCount("NEW", 1),
        ]
    )


def create_state_transition_scenario(base_dir: Path) -> Scenario:
    """Create a scenario testing all state transitions."""
    return Scenario(
        name="state_transitions",
        description="Test NEW → IN_USE → REMOVED → IN_USE transitions",
        base_dir=base_dir,
        actions=[
            # Setup
            CreateFile(base_dir / "media" / "shot_001.mov"),
            ScanDirectory(base_dir / "media"),
            AssertFileState(base_dir / "media" / "shot_001.mov", "NEW"),

            # NEW → IN_USE
            CreateTimeline(base_dir / "timeline_v1.otio", ("shot_001.mov",)),
            UpdateFromTimeline(base_dir / "timeline_v1.otio"),
            AssertFileState(base_dir / "media" / "shot_001.mov", "IN_USE"),

            # IN_USE → REMOVED
            CreateTimeline(base_dir / "timeline_v2.otio", ()),  # Empty timeline
            UpdateFromTimeline(base_dir / "timeline_v2.otio"),
            AssertFileState(base_dir / "media" / "shot_001.mov", "REMOVED"),

            # REMOVED → IN_USE
            UpdateFromTimeline(base_dir / "timeline_v1.otio"),
            AssertFileState(base_dir / "media" / "shot_001.mov", "IN_USE"),
        ]
    )


def create_production_workflow_scenario(base_dir: Path) -> Scenario:
    """Create a realistic production workflow scenario with delays for demo."""
    return Scenario(
        name="production_workflow",
        description="Realistic animation studio workflow",
        base_dir=base_dir,
        actions=[
            # Day 1: Animation delivers initial renders
            CreateFile(base_dir / "media" / "shot_010_anim_v001.mov"),
            CreateFile(base_dir / "media" / "shot_020_anim_v001.mov"),
            CreateFile(base_dir / "media" / "shot_030_anim_v001.mov"),
            CreateFile(base_dir / "media" / "shot_040_anim_v001.mov"),
            CreateFile(base_dir / "media" / "bg_forest_001.mov"),

            ScanDirectory(base_dir / "media"),
            Wait(2.0),

            # Day 2: Editorial sends initial cut
            CreateTimeline(
                base_dir / "initial_cut.otio",
                ("shot_010_anim_v001.mov", "shot_020_anim_v001.mov", "bg_forest_001.mov")
            ),
            UpdateFromTimeline(base_dir / "initial_cut.otio"),
            AssertFileCount("IN_USE", 3),
            AssertFileCount("NEW", 2),
            Wait(2.0),

            # Day 3: More animation files delivered
            CreateFile(base_dir / "media" / "shot_050_anim_v001.mov"),
            ScanDirectory(base_dir / "media"),
            Wait(2.0),

            # Day 4: Editorial revises cut
            CreateTimeline(
                base_dir / "revised_cut.otio",
                ("shot_010_anim_v001.mov", "shot_030_anim_v001.mov",
                 "shot_040_anim_v001.mov", "bg_forest_001.mov")
            ),
            UpdateFromTimeline(base_dir / "revised_cut.otio"),
            AssertFileState(base_dir / "media" / "shot_020_anim_v001.mov", "REMOVED"),
            AssertFileState(base_dir / "media" / "shot_030_anim_v001.mov", "IN_USE"),
            Wait(2.0),

            # Day 5: Comp team delivers composited versions
            CreateFile(base_dir / "media" / "shot_010_comp_v001.mov"),
            CreateFile(base_dir / "media" / "shot_030_comp_v001.mov"),
            ScanDirectory(base_dir / "media"),
            Wait(2.0),

            # Day 6: Final cut with comp versions
            CreateTimeline(
                base_dir / "final_cut.otio",
                ("shot_010_comp_v001.mov", "shot_030_comp_v001.mov",
                 "shot_040_anim_v001.mov", "shot_050_anim_v001.mov")
            ),
            UpdateFromTimeline(base_dir / "final_cut.otio"),
            AssertFileCount("IN_USE", 4),
            AssertFileCount("REMOVED", 3),
            AssertFileCount("NEW", 1),
        ]
    )


# Standard scenarios
STANDARD_SCENARIOS = {
    "basic": create_basic_workflow_scenario,
    "transitions": create_state_transition_scenario,
    "production": create_production_workflow_scenario,
}
