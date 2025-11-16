"""
Property-based tests for media algebra using Hypothesis.

These tests verify algebraic laws and invariants hold for all inputs.
"""

import pytest
from hypothesis import given, assume, strategies as st
from pathlib import Path
import tempfile

from media_algebra import (
    TimeRange,
    MediaFile,
    VideoStream,
    AudioStream,
    AudioMix,
    AVComposition,
    Output,
)


# ============================================================================
# Hypothesis Strategies
# ============================================================================

@st.composite
def time_ranges(draw, min_start=0.0, max_start=1000.0, min_duration=0.01, max_duration=100.0):
    """Generate valid TimeRange objects"""
    start = draw(st.floats(min_value=min_start, max_value=max_start, allow_nan=False, allow_infinity=False))
    duration = draw(st.floats(min_value=min_duration, max_value=max_duration, allow_nan=False, allow_infinity=False))
    return TimeRange(start, duration)


@st.composite
def media_files(draw):
    """Generate MediaFile objects with temp paths"""
    # Use a simple incremental path for testing
    filename = draw(st.text(alphabet='abcdefghijklmnopqrstuvwxyz0123456789', min_size=5, max_size=20))
    return MediaFile(Path(f"/tmp/test_{filename}.mp4"))


@st.composite
def video_streams(draw):
    """Generate VideoStream objects"""
    media = draw(media_files())
    source_range = draw(time_ranges())
    return VideoStream(media, source_range)


@st.composite
def audio_streams(draw):
    """Generate AudioStream objects"""
    media = draw(media_files())
    source_range = draw(time_ranges())
    track_index = draw(st.integers(min_value=0, max_value=7))
    offset = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    return AudioStream(media, source_range, track_index, offset)


# ============================================================================
# TimeRange Property Tests
# ============================================================================

class TestTimeRangeProperties:
    """Property-based tests for TimeRange algebra"""

    @given(time_ranges())
    def test_end_equals_start_plus_duration(self, tr: TimeRange):
        """Property: end = start + duration"""
        assert abs(tr.end - (tr.start + tr.duration)) < 1e-10

    @given(time_ranges(), st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False))
    def test_offset_preserves_duration(self, tr: TimeRange, offset: float):
        """Property: offset_by preserves duration"""
        shifted = tr.offset_by(offset)
        assert abs(shifted.duration - tr.duration) < 1e-10

    @given(time_ranges(), st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False))
    def test_offset_shifts_start(self, tr: TimeRange, offset: float):
        """Property: offset_by shifts start by offset amount"""
        shifted = tr.offset_by(offset)
        assert abs(shifted.start - (tr.start + offset)) < 1e-10

    @given(time_ranges())
    def test_overlaps_is_reflexive(self, tr: TimeRange):
        """Property: A range overlaps with itself"""
        assert tr.overlaps(tr)

    @given(time_ranges(), time_ranges())
    def test_overlaps_is_symmetric(self, tr1: TimeRange, tr2: TimeRange):
        """Property: if A overlaps B, then B overlaps A"""
        assert tr1.overlaps(tr2) == tr2.overlaps(tr1)

    @given(time_ranges(), time_ranges())
    def test_intersection_is_commutative(self, tr1: TimeRange, tr2: TimeRange):
        """Property: intersection(A, B) = intersection(B, A)"""
        int1 = tr1.intersection(tr2)
        int2 = tr2.intersection(tr1)

        if int1 is None:
            assert int2 is None
        else:
            assert int2 is not None
            assert abs(int1.start - int2.start) < 1e-10
            assert abs(int1.duration - int2.duration) < 1e-10

    @given(time_ranges(), time_ranges())
    def test_intersection_implies_overlap(self, tr1: TimeRange, tr2: TimeRange):
        """Property: if intersection exists, ranges overlap"""
        intersection = tr1.intersection(tr2)
        if intersection is not None:
            assert tr1.overlaps(tr2)

    @given(time_ranges(), time_ranges())
    def test_no_overlap_means_no_intersection(self, tr1: TimeRange, tr2: TimeRange):
        """Property: if ranges don't overlap, intersection is None"""
        if not tr1.overlaps(tr2):
            assert tr1.intersection(tr2) is None

    @given(time_ranges(), time_ranges())
    def test_intersection_within_both_ranges(self, tr1: TimeRange, tr2: TimeRange):
        """Property: intersection is contained in both ranges"""
        intersection = tr1.intersection(tr2)
        if intersection is not None:
            # Intersection start >= max of both starts
            assert intersection.start >= tr1.start - 1e-10
            assert intersection.start >= tr2.start - 1e-10
            # Intersection end <= min of both ends
            assert intersection.end <= tr1.end + 1e-10
            assert intersection.end <= tr2.end + 1e-10


# ============================================================================
# Stream Immutability Tests
# ============================================================================

class TestStreamImmutability:
    """Verify that stream operations return new objects (immutability)"""

    @given(video_streams(), time_ranges())
    def test_video_trim_returns_new_object(self, vs: VideoStream, tr: TimeRange):
        """Property: trim returns a new VideoStream"""
        trimmed = vs.trim(tr)
        assert trimmed is not vs
        assert trimmed.media == vs.media  # Media reference unchanged
        assert trimmed.source_range == tr  # Range changed

    @given(audio_streams(), time_ranges())
    def test_audio_trim_returns_new_object(self, aus: AudioStream, tr: TimeRange):
        """Property: trim returns a new AudioStream"""
        trimmed = aus.trim(tr)
        assert trimmed is not aus
        assert trimmed.source_range == tr

    @given(audio_streams(), st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False))
    def test_audio_with_offset_returns_new_object(self, aus: AudioStream, offset: float):
        """Property: with_offset returns a new AudioStream"""
        shifted = aus.with_offset(offset)
        assert shifted is not aus
        assert shifted.offset == offset
        assert shifted.source_range == aus.source_range


# ============================================================================
# AudioMix Tests
# ============================================================================

class TestAudioMix:
    """Tests for AudioMix composition"""

    def test_audio_mix_requires_at_least_one_stream(self):
        """Property: AudioMix with empty streams raises ValueError"""
        with pytest.raises(ValueError):
            AudioMix(())

    @given(audio_streams())
    def test_from_streams_single_returns_stream(self, aus: AudioStream):
        """Property: from_streams([single]) returns AudioStream"""
        result = AudioMix.from_streams([aus])
        assert isinstance(result, AudioStream)
        assert result == aus

    @given(st.lists(audio_streams(), min_size=2, max_size=5))
    def test_from_streams_multiple_returns_mix(self, streams: list[AudioStream]):
        """Property: from_streams([multiple]) returns AudioMix"""
        result = AudioMix.from_streams(streams)
        assert isinstance(result, AudioMix)
        assert len(result.streams) == len(streams)

    def test_from_streams_empty_returns_none(self):
        """Property: from_streams([]) returns None"""
        result = AudioMix.from_streams([])
        assert result is None

    @given(st.lists(audio_streams(), min_size=1, max_size=3), audio_streams())
    def test_add_stream_immutability(self, initial_streams: list[AudioStream], new_stream: AudioStream):
        """Property: add_stream returns new AudioMix"""
        mix = AudioMix(tuple(initial_streams))
        new_mix = mix.add_stream(new_stream)

        assert new_mix is not mix
        assert len(new_mix.streams) == len(mix.streams) + 1
        assert new_stream in new_mix.streams


# ============================================================================
# AVComposition Tests
# ============================================================================

class TestAVComposition:
    """Tests for AVComposition"""

    @given(video_streams(), st.one_of(st.none(), audio_streams()))
    def test_replace_audio_returns_new_composition(self, vs: VideoStream, new_audio):
        """Property: replace_audio returns new AVComposition"""
        comp = AVComposition(vs, None)
        new_comp = comp.replace_audio(new_audio)

        assert new_comp is not comp
        assert new_comp.video == vs
        assert new_comp.audio == new_audio

    @given(video_streams(), st.one_of(st.none(), audio_streams()), time_ranges())
    def test_trim_video_returns_new_composition(self, vs: VideoStream, audio, tr: TimeRange):
        """Property: trim_video returns new AVComposition"""
        comp = AVComposition(vs, audio)
        new_comp = comp.trim_video(tr)

        assert new_comp is not comp
        assert new_comp.video.source_range == tr
        assert new_comp.audio == audio


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple operations"""

    def test_simple_composition_workflow(self):
        """Test a simple workflow: create video, audio, compose"""
        # Create media files
        video_file = MediaFile(Path("/tmp/video.mp4"))
        audio_file = MediaFile(Path("/tmp/audio.wav"))

        # Create streams
        video = VideoStream(video_file, TimeRange(0.0, 10.0))
        audio = AudioStream(audio_file, TimeRange(5.0, 10.0), offset=0.0)

        # Create composition
        comp = AVComposition(video, audio)

        # Verify structure
        assert comp.video.media == video_file
        assert comp.audio.media == audio_file

    def test_audio_mix_workflow(self):
        """Test mixing multiple audio streams"""
        video = VideoStream(MediaFile(Path("/tmp/video.mp4")), TimeRange(0.0, 10.0))

        audio1 = AudioStream(MediaFile(Path("/tmp/audio1.wav")), TimeRange(0.0, 10.0), offset=0.0)
        audio2 = AudioStream(MediaFile(Path("/tmp/audio2.wav")), TimeRange(0.0, 5.0), offset=2.0)
        audio3 = AudioStream(MediaFile(Path("/tmp/audio3.wav")), TimeRange(0.0, 8.0), offset=5.0)

        mix = AudioMix((audio1, audio2, audio3))
        comp = AVComposition(video, mix)

        assert len(comp.audio.streams) == 3


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--hypothesis-show-statistics'])
