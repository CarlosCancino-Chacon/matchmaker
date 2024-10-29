import os
from typing import Optional, Union

import numpy as np
import partitura
from partitura.io.exportaudio import save_wav_fluidsynth
from partitura.io.exportmidi import get_ppq
from partitura.score import ScoreLike

from matchmaker.dp import OnlineTimeWarpingArzt, OnlineTimeWarpingDixon
from matchmaker.features.audio import (
    FRAME_RATE,
    SAMPLE_RATE,
    ChromagramProcessor,
    MelSpectrogramProcessor,
    MFCCProcessor,
)
from matchmaker.io.audio import AudioStream
from matchmaker.io.midi import MidiStream
from matchmaker.prob.hmm import PitchIOIHMM

PathLike = Union[str, bytes, os.PathLike]


class Matchmaker:
    """
    A class to perform online score following with I/O support for audio and MIDI

    Parameters
    ----------
    score_file : Union[str, bytes, os.PathLike]
        Path to the score file
    performance_file : Union[str, bytes, os.PathLike, None]
        Path to the performance file. If None, live input is used.
    input_type : str
        Type of input to use: audio or midi
    feature_type : str
        Type of feature to use
    method : str
        Score following method to use
    device_name_or_index : Union[str, int]
        Name or index of the audio device to be used.
        Ignored if `file_path` is given.

    """

    def __init__(
        self,
        score_file: PathLike,
        performance_file: Union[PathLike, None] = None,
        input_type: str = "audio",  # audio or midi
        feature_type: str = "chroma",
        method: str = None,
        device_name_or_index: Union[str, int] = None,
        sample_rate: int = SAMPLE_RATE,
        frame_rate: int = FRAME_RATE,
    ):
        self.feature_type = feature_type
        self.frame_rate = frame_rate
        self.score_data: Optional[ScoreLike] = None
        self.live_input = False
        self.device_index = None
        self.processor = None
        self.stream = None
        self.score_follower = None

        # setup score file
        if score_file is None:
            raise ValueError("Score file is required")

        self.score_data = partitura.load_score(score_file)

        # setup feature processor
        if feature_type == "chroma":
            self.processor = ChromagramProcessor(
                sample_rate=sample_rate,
            )
        elif feature_type == "mfcc":
            self.processor = MFCCProcessor(
                sample_rate=sample_rate,
            )
        elif feature_type == "mel":
            self.processor = MelSpectrogramProcessor(
                sample_rate=sample_rate,
            )
        else:
            raise ValueError("Invalid feature type")

        # setup stream device
        if input_type == "audio":
            self.stream = AudioStream(
                processor=self.processor,
                device_name_or_index=device_name_or_index,
                file_path=performance_file,
            )
        elif input_type == "midi":
            self.strema = MidiStream(
                processor=self.processor, file_path=performance_file
            )
        else:
            raise ValueError("Invalid input type")

        # setup score follower
        if method == "dixon":
            self.score_follower = OnlineTimeWarpingDixon
        elif method == "arzt":
            self.score_follower = OnlineTimeWarpingArzt
        elif method == "hmm":
            self.score_follower = PitchIOIHMM

    def preprocess_score(self):
        score_audio = save_wav_fluidsynth(self.score_data)
        reference_features = self.processor(score_audio)
        return reference_features

    def convert_frame_to_beat(
        self, current_frame: int, frame_rate: int = FRAME_RATE
    ) -> float:
        """
        Convert frame number to relative beat position in the score.

        Parameters
        ----------
        frame_rate : int
            Frame rate of the audio stream
        current_frame : int
            Current frame number
        """
        tick = get_ppq(self.score_data.parts[0])
        timeline_time = (current_frame / frame_rate) * tick * 2
        beat_position = np.round(
            self.score_data.parts[0].beat_map(timeline_time),
            decimals=2,
        )
        return beat_position

    def run(self):
        """
        Run the score following process

        Yields
        ------
        float
            Beat position in the score (interpolated)
        """
        reference_features = self.preprocess_score()

        with self.stream as stream:
            for current_frame in self.score_follower(
                reference_features=reference_features, queue=stream.queue
            ).run():
                position_in_beat = self.convert_frame_to_beat(current_frame)
                yield position_in_beat