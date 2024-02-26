#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Tests for the io/midi.py module
"""
import unittest

import mido

import numpy as np
import time


from matchmaker.io.midi import MidiStream

from matchmaker.utils.misc import RECVQueue

from matchmaker.features.midi import (
    PitchIOIProcessor,
    PianoRollProcessor,
    CumSumPianoRollProcessor,
)

from typing import Optional

RNG = np.random.RandomState(1984)

from tests.utils import DummyMidiPlayer

from partitura import save_performance_midi
from partitura.performance import PerformedPart

from tempfile import NamedTemporaryFile


def setup_midi_player():
    # Open virtual MIDI port
    # the input uses the "created" virtual
    # port
    port = mido.open_input("port1", virtual=True)
    outport = mido.open_output("port1")
    queue = RECVQueue()

    # Generate a random MIDI file
    n_notes = 5
    iois = 2 * RNG.rand(n_notes - 1)
    note_array = np.empty(
        n_notes,
        dtype=[
            ("pitch", int),
            ("onset_sec", float),
            ("duration_sec", float),
            ("velocity", int),
        ],
    )

    note_array["pitch"] = RNG.randint(low=0, high=127, size=n_notes)
    note_array["onset_sec"] = np.r_[0, np.cumsum(iois)]
    note_array["duration_sec"] = 2 * RNG.rand(n_notes)
    note_array["velocity"] = RNG.randint(low=0, high=127, size=n_notes)

    tmp_file = NamedTemporaryFile(delete=True)
    save_performance_midi(
        performance_data=PerformedPart.from_note_array(note_array),
        out=tmp_file.name,
    )
    midi_player = DummyMidiPlayer(
        port=outport,
        filename=tmp_file.name,
    )
    # close and delete tmp midi file
    tmp_file.close()
    return port, queue, midi_player


class TestMidiStream(unittest.TestCase):

    def test_stream(self):
        port, queue, midi_player = setup_midi_player()
        features = [
            PitchIOIProcessor(),
            PianoRollProcessor(),
            CumSumPianoRollProcessor(),
        ]
        midi_stream = MidiStream(
            port=port,
            queue=queue,
            features=features,
        )
        midi_stream.start()

        midi_player.start()

        while midi_player.is_playing:
            output = queue.recv()
            self.assertTrue(len(output) == len(features))
        midi_stream.stop_listening()
        port.close()

    def test_stream_with_midi_messages(self):
        port, queue, midi_player = setup_midi_player()
        features = [PitchIOIProcessor()]
        midi_stream = MidiStream(
            port=port,
            queue=queue,
            features=features,
            return_midi_messages=True,
        )
        midi_stream.start()

        midi_player.start()

        while midi_player.is_playing:
            (msg, msg_time), output = queue.recv()
            self.assertTrue(isinstance(msg, mido.Message))
            self.assertTrue(isinstance(msg_time, float))

            if msg.type== "note_on" and output[0] is not None:
                self.assertTrue(msg.note == int(output[0][0][0]))
            self.assertTrue(len(output) == len(features))
        midi_stream.stop_listening()
        port.close()