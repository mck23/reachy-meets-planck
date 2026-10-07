"""Tests for the reading state machine, using stand-ins for the robot.

Run with:  .venv/bin/python -m unittest discover tests
"""

import threading
import unittest

from reachy_meets_planck import main
from reachy_meets_planck.listener import BEGIN, CONTINUE, END, STOP
from reachy_meets_planck.playlist import FLOURISH, LECTURE, Item

PLAYLIST = [
    Item("greeting", LECTURE, "Hello."),
    Item("seg-000", LECTURE, "Title.", "nod"),
    Item("seg-001", LECTURE, "Sentence one."),
    Item("flourish-001", FLOURISH, "Heh-heh."),
    Item("seg-002", LECTURE, "Sentence two."),
]


class FakeListener:
    """Delivers scripted commands: {clip key being played: command to hear}."""

    def __init__(self, during_play: dict[str, str], when_waiting: list[str]):
        self.during_play = dict(during_play)
        self.when_waiting = list(when_waiting)
        self.now_playing = None
        self.waiting = False

    def take(self, allowed):
        if self.waiting:
            if self.when_waiting and self.when_waiting[0] in allowed:
                return self.when_waiting.pop(0)
            return None
        command = self.during_play.pop(self.now_playing, None)
        return command if command in allowed else None

    def clear(self):
        pass


class FakeSpeaker:
    def __init__(self, listener: FakeListener):
        self.listener = listener
        self.played: list[str] = []

    def load(self, path):
        return path.stem

    def prefetch(self, path):
        pass

    def play(self, key, interrupted):
        self.listener.now_playing = key
        self.listener.waiting = False
        if interrupted():
            self.played.append(f"{key}(interrupted)")
            return False
        self.played.append(key)
        return True

    def pause(self, seconds, interrupted):
        return True


class FakeGestures:
    def __init__(self):
        self.played: list[str] = []

    def play(self, name):
        self.played.append(name)

    def wait_idle(self, timeout=10.0):
        pass


def perform(during_play, when_waiting):
    listener = FakeListener(during_play, when_waiting)
    speaker = FakeSpeaker(listener)
    gestures = FakeGestures()
    perf = main.Performance(PLAYLIST, speaker, listener, gestures, threading.Event())
    original_wait_for = perf._wait_for

    def wait_for(allowed):
        listener.waiting = True
        return original_wait_for(allowed)

    perf._wait_for = wait_for
    perf.perform()
    return speaker.played, gestures.played


class PerformanceTest(unittest.TestCase):
    def test_reads_everything_then_end_exits(self):
        played, gestures = perform({}, [END])
        self.assertEqual(played, ["greeting", "seg-000", "seg-001", "flourish-001", "seg-002"])
        self.assertEqual(gestures, ["nod", "bow"])

    def test_stop_then_continue_resumes_same_sentence(self):
        played, gestures = perform({"seg-001": STOP}, [CONTINUE, END])
        self.assertEqual(
            played,
            ["greeting", "seg-000", "seg-001(interrupted)", "seg-001", "flourish-001", "seg-002"],
        )
        self.assertEqual(gestures, ["nod", "tilt", "nod", "bow"])

    def test_stop_then_begin_restarts_from_top(self):
        played, _ = perform({"seg-002": STOP}, [BEGIN, END])
        self.assertEqual(
            played,
            ["greeting", "seg-000", "seg-001", "flourish-001", "seg-002(interrupted)",
             "greeting", "seg-000", "seg-001", "flourish-001", "seg-002"],
        )

    def test_stop_then_end_exits_without_reading_more(self):
        played, gestures = perform({"seg-000": STOP}, [END])
        self.assertEqual(played, ["greeting", "seg-000(interrupted)"])
        self.assertEqual(gestures[-1], "bow")

    def test_commands_other_than_stop_are_ignored_while_reading(self):
        played, _ = perform({"seg-001": END, "seg-002": BEGIN}, [END])
        self.assertEqual(played, ["greeting", "seg-000", "seg-001", "flourish-001", "seg-002"])

    def test_begin_after_finishing_reads_again(self):
        played, _ = perform({}, [BEGIN, END])
        self.assertEqual(played, [i.key for i in PLAYLIST] * 2)


class GestureSafetyTest(unittest.TestCase):
    def test_every_cue_names_a_known_gesture(self):
        from reachy_meets_planck.gestures import GESTURES
        from reachy_meets_planck.playlist import load_playlist

        for item in load_playlist():
            if item.gesture:
                self.assertIn(item.gesture, GESTURES, item.key)

    def test_nothing_spoken_contains_stop(self):
        from reachy_meets_planck.playlist import load_playlist

        for item in load_playlist():
            self.assertNotIn(STOP, item.text.lower().replace(",", " ").replace(".", " ").split(), item.key)


if __name__ == "__main__":
    unittest.main()


class SpeakerDecodeTest(unittest.TestCase):
    """The compressed clips decode, apply gain, and prefetching returns the same audio."""

    def setUp(self):
        from reachy_meets_planck.speech import Speaker

        class Media:
            def get_output_audio_samplerate(self):
                return 16000

        self.plain = Speaker(Media())
        self.loud = Speaker(Media(), gain=1.25)

    def tearDown(self):
        self.plain.close()
        self.loud.close()

    def test_prefetched_clip_matches_direct_decode_with_gain(self):
        import numpy as np

        from reachy_meets_planck.playlist import clip_path, load_playlist

        path = clip_path(load_playlist()[1])
        self.loud.prefetch(path)
        prefetched = self.loud.load(path)
        direct = self.plain.decode(path)
        self.assertEqual(len(prefetched), len(direct))
        self.assertGreater(len(direct), 16000)  # more than a second of speech
        np.testing.assert_allclose(prefetched, np.clip(direct * 1.25, -1, 1), atol=1e-5)

    def test_every_clip_is_present_and_current(self):
        from reachy_meets_planck.playlist import load_performance, load_playlist, missing_clips

        self.assertEqual(missing_clips(load_playlist(), load_performance()["voice"]), [])
