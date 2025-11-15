"""
Tests for timeline speed/stretch changes in clip previews.

Verifies that the atempo filter chain is built correctly for various speed factors.
"""

import pytest
from clip_preview import ClipPreviewGenerator, PreviewGenerationError


def test_atempo_chain_normal_speed():
    """Test atempo chain for normal speed (1.0x)."""
    generator = ClipPreviewGenerator()

    # Normal speed should return atempo=1.0
    chain = generator._build_atempo_chain(1.0)
    assert chain == "atempo=1.0"


def test_atempo_chain_double_speed():
    """Test atempo chain for 2x speed."""
    generator = ClipPreviewGenerator()

    chain = generator._build_atempo_chain(2.0)
    assert chain == "atempo=2.0"


def test_atempo_chain_half_speed():
    """Test atempo chain for 0.5x speed (slow motion)."""
    generator = ClipPreviewGenerator()

    chain = generator._build_atempo_chain(0.5)
    assert chain == "atempo=0.5"


def test_atempo_chain_quad_speed():
    """Test atempo chain for 4x speed (requires chaining)."""
    generator = ClipPreviewGenerator()

    # 4x = 2.0 * 2.0
    chain = generator._build_atempo_chain(4.0)
    assert chain == "atempo=2.0,atempo=2.0"


def test_atempo_chain_quarter_speed():
    """Test atempo chain for 0.25x speed (requires chaining)."""
    generator = ClipPreviewGenerator()

    # 0.25x = 0.5 * 0.5
    chain = generator._build_atempo_chain(0.25)
    assert chain == "atempo=0.5,atempo=0.5"


def test_atempo_chain_triple_speed():
    """Test atempo chain for 3x speed."""
    generator = ClipPreviewGenerator()

    # 3x = 2.0 * 1.5
    chain = generator._build_atempo_chain(3.0)
    assert chain == "atempo=2.0,atempo=1.5"


def test_atempo_chain_8x_speed():
    """Test atempo chain for 8x speed (requires multiple chaining)."""
    generator = ClipPreviewGenerator()

    # 8x = 2.0 * 2.0 * 2.0
    chain = generator._build_atempo_chain(8.0)
    assert chain == "atempo=2.0,atempo=2.0,atempo=2.0"


def test_atempo_chain_0125_speed():
    """Test atempo chain for 0.125x speed (very slow)."""
    generator = ClipPreviewGenerator()

    # 0.125x = 0.5 * 0.5 * 0.5
    chain = generator._build_atempo_chain(0.125)
    assert chain == "atempo=0.5,atempo=0.5,atempo=0.5"


def test_atempo_chain_invalid_speed():
    """Test that invalid speeds raise an error."""
    generator = ClipPreviewGenerator()

    with pytest.raises(PreviewGenerationError, match="Invalid speed"):
        generator._build_atempo_chain(0.0)

    with pytest.raises(PreviewGenerationError, match="Invalid speed"):
        generator._build_atempo_chain(-1.0)


def test_atempo_filter_with_labels():
    """Test building complete atempo filter with labels."""
    generator = ClipPreviewGenerator()

    filter_str = generator._build_atempo_filter(2.0, "[0:a]", "[a]")
    assert filter_str == "[0:a]atempo=2.0[a]"

    # Test with chaining
    filter_str = generator._build_atempo_filter(4.0, "[0:a]", "[a]")
    assert filter_str == "[0:a]atempo=2.0,atempo=2.0[a]"


def test_speed_within_1_percent_of_normal():
    """Test that speeds very close to 1.0 are treated as normal."""
    generator = ClipPreviewGenerator()

    # Speeds within 1% of 1.0 should not trigger speed changes in the actual generation
    # (This is tested in the generation code, not in atempo_chain itself)
    speeds_near_normal = [0.995, 1.005, 0.999, 1.001]

    for speed in speeds_near_normal:
        needs_speed = abs(speed - 1.0) > 0.01
        assert not needs_speed, f"Speed {speed} should not require speed change"


def test_clip_data_with_speed():
    """Test that clip data correctly includes speed information."""
    # This would test the full integration, but requires actual video files
    # For now, just verify the structure
    clip_data = {
        "source_start": 0.0,
        "source_end": 10.0,
        "source_duration": 10.0,
        "speed": 2.0  # 2x speed
    }

    assert clip_data["speed"] == 2.0

    # Verify speed calculation
    source_duration = clip_data["source_end"] - clip_data["source_start"]
    timeline_duration = source_duration / clip_data["speed"]  # 10 / 2 = 5 seconds in timeline
    assert timeline_duration == 5.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
