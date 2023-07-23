from abc import abstractmethod
import logging
from pathlib import Path
from typing import Any, Dict, List, Set

from DRSlib.utils import assertTrue
from FFmpyg.command import Command
from FFmpyg.encoder import FFmpegEncoder, RateControlMode
from FFmpyg.media import MediaFile, StreamCriteria, StreamType, FutureStream, Stream
from FFmpyg.ffmpeg_command import FfmpegInput, build_ffmpeg_command, FfmpegOptions
from FFmpyg.ffmpeg_lib import get_ffmpeg_info
from FFmpyg.virtualfs import WorkingDirectory

from container import ContainerHelper
from utils import (
    make_mkvmerge_merge_command_from_streams,
    MKVMergeMode,
    get_valid_ffmpeg2pass_name,
    ffmpeg2pass_file_names,
)

PROCESSING_STEP_RESULT_ATTR = "_result"
RESULT_OUTPUT_MEDIA_FILE = "output_media_file"
RESULT_OUTPUT_NEXT_SPRINT_STEPS = "next_sprint_steps"


LOG = logging.getLogger(__file__)


class ProcessingStep:
    """Represents a simple step in the transcoding process:
    - planning future steps
    - transcode a stream
    - perform additional processing (muxing, generate stats)
    ProcessingStep have as input parameters given to them by either
    the step or the StreamProcessor that created it.
    A ProcessingStep should not be worried about what happens if processing fails or
    not duplicating work if execution is successful, this is left to the StreamProcessor
    """

    parameters: Dict[str, Any]
    """Parameters of the step"""
    wd: WorkingDirectory | None
    """Organizes all produced files"""

    def __init__(
        self, parameters: Dict[str, Any], wd: WorkingDirectory | None = None
    ) -> None:
        self.parameters = parameters
        self.wd = wd
        _cwd = Path(".").resolve()
        assertTrue(
            self.wd._cwd == _cwd,
            "Nonmatching CWD: WorkingDirectory has {} but found {}",
            self.wd._cwd,
            _cwd,
        )
        try:
            self.verify()
        except Exception as e:
            raise ValueError("Parameter validation failed") from e

    @abstractmethod
    def verify(self) -> None:
        """Verifies parameters (should be called by run)"""

    @abstractmethod
    def run(self) -> None:
        """Verifies parameters, executes the step and stores the results self.result"""

    @property
    def result(self) -> Dict[str, Any]:
        """Contains any information resulting from execution"""
        if hasattr(self, "_result"):
            return getattr(self, PROCESSING_STEP_RESULT_ATTR)
        raise ValueError(
            "Property 'result' queried but doesn't exist; Either run() wasn't called, isn't finished, didn't finish correctly or otherwise didn't create it"
        )

    @property
    def cwd(self) -> Path:
        """Fetches CWD from WorkingDirectory, knowing this is equivalent to Path('.').resolve()"""
        return self.wd._cwd

    def verify_required(self, required: List[str]) -> None:
        """Verifies required parameters are set and not None"""
        for req in required:
            assertTrue(
                self.parameters.get(req, None) is not None,
                "Missing required parameter {}",
                req,
            )

    def new_file(
        self, stream: Stream, container: str, suffix: str | None = None
    ) -> Path:
        """Facility around wd.new_file"""
        return self.wd.new_file(
            f"stream{stream.idx}" + ("_" + suffix if suffix else "") + "." + container
        )


class MKVMergeProcessingStep(ProcessingStep):
    """Uses MKVMerge to mux or join streams to a MKV file
    Parameters:
    - inputs: List[FFmpyg.media.Stream]
    - output: Path (must be valid and not exist)
    - mode: MKVMergeMode
    - executable: str | Path | None (defaults to "mkvmerge")
    """

    REQUIRED_PARAMS = ["inputs", "output", "mode"]

    def verify(self) -> None:
        self.verify_required(self.REQUIRED_PARAMS)
        _output = self.parameters["output"]
        assertTrue(
            isinstance(_output, Path)
            and _output.suffix.lower() == ".mkv"
            and not _output.exists(),
            "Expected valid available path, got {}",
            _output,
        )
        _mode = self.parameters["mode"]
        assertTrue(
            isinstance(_mode, MKVMergeMode),
            "Invalid type: expected MKVMergeMode, got {}",
            type(_mode),
        )

    def run(self) -> None:
        _output = self.parameters["output"]

        cmd = Command(
            make_mkvmerge_merge_command_from_streams(
                executable=self.parameters.get("executable", "mkvmerge"),
                output=_output,
                inputs=self.parameters["inputs"],
                mode=self.parameters["mode"],
            )
        )

        stdX = None
        try:
            LOG.debug("Executing cmd=%s", cmd)
            stdX = cmd.execute()
            LOG.debug("stdX=%s", stdX)
            assertTrue(
                _output.exists(),
                "Output file wasn't created; There must have been an issue",
            )
            output_media_file = MediaFile(_output)
            setattr(
                self,
                PROCESSING_STEP_RESULT_ATTR,
                {RESULT_OUTPUT_MEDIA_FILE: output_media_file},
            )
        except Exception as e:
            raise RuntimeError(
                f"Something went wrong during execution. stdX={stdX}"
            ) from e


class FFmpegSimpleTranscodeProcessingStep(ProcessingStep):
    """Represents a simple transcoding step using FFmpeg
    Parameters:
    - input: FFmpyg.media.Stream
    - input_opt: dict with optional keys <fix_fps:int|float> and <more:List[str]>
    - encoder: FFmpegEncoder
    - ffmpeg_opt: FfmpegOptions | None
    """

    REQUIRED_PARAMS = ["input", "input_opt", "encoder"]

    def verify(self) -> None:
        self.verify_required(self.REQUIRED_PARAMS)
        _encoder: FFmpegEncoder = self.parameters["encoder"]
        _info = get_ffmpeg_info(_encoder.executable)
        assertTrue(
            _info.get("version") is not None,
            "Expected ffmpeg executable but couldn't verify {}",
            _encoder.executable,
        )

    def run(self) -> None:
        _stream: Stream = self.parameters["input"]
        _stream_opt: dict = self.parameters["input_opt"]
        _encoder: FFmpegEncoder = self.parameters["encoder"]
        _future_stream = FutureStream(index=0, encoder=_encoder)
        _output_file = self.new_file(
            _stream, ContainerHelper.preferred_container(_encoder.codec)
        )
        cmd, future_file = build_ffmpeg_command(
            inputs=[FfmpegInput(_stream.media_file, **_stream_opt)],
            ffmpeg=_encoder.executable,
            options=self.parameters.get("ffmpeg_opt"),
            output=_output_file,
            stream_mapping={_stream: _future_stream},
        )
        stdX = None
        try:
            LOG.debug("Executing cmd=%s", cmd)
            stdX = cmd.execute()
            output_media_file = future_file.load_actual_file()
            setattr(
                self,
                PROCESSING_STEP_RESULT_ATTR,
                {RESULT_OUTPUT_MEDIA_FILE: output_media_file},
            )
        except Exception as e:
            raise RuntimeError(
                f"Something went wrong during execution. stdX={stdX}"
            ) from e


class FFmpegTargetBitrate2passEncodeProcessingStep(FFmpegSimpleTranscodeProcessingStep):
    """Represents a simple transcoding step using FFmpeg
    Parameters:
    - input: FFmpyg.media.Stream
    - input_opt: dict with optional keys <fix_fps:int|float> and <more:List[str]>
    - encoder: FFmpegEncoder
    - target_bitrate: int | str (can be a ffmpeg-recognized human-friendly value like 2M or 1200k)
    - ffmpeg_opt: FfmpegOptions | None
    - ffmpeg2pass: str | None (do not set manually, used by first step to signal next step)
    """

    def run(self) -> None:
        _stream: Stream = self.parameters["input"]
        _stream_opt: dict = self.parameters["input_opt"]
        _bitrate = self.parameters["target_bitrate"]

        second_step: bool = self.parameters.get("ffmpeg2pass") is not None
        _encoder: FFmpegEncoder = self.parameters["encoder"].clone()
        parameters = {"pass": 2 if second_step else 1}
        _encoder.set_parameters(**parameters)
        _encoder.set_rate(RateControlMode.VBR, _bitrate)
        _future_stream = FutureStream(index=0, encoder=_encoder)

        if not second_step:
            # 1st pass
            ffmpeg2pass_name = get_valid_ffmpeg2pass_name(
                f"stream{_stream.idx}_passlog"
            )
            ffmpeg2pass_files = [
                (self.cwd / filename)
                for filename in ffmpeg2pass_file_names(ffmpeg2pass_name)
            ]
            cmd, _ = build_ffmpeg_command(
                inputs=[FfmpegInput(_stream.media_file, **_stream_opt)],
                ffmpeg=_encoder.executable,
                options=self.parameters.get("ffmpeg_opt"),
                stream_mapping={_stream: _future_stream},
                extra=["-passlogfile", ffmpeg2pass_name],
            )
            stdX = None
            try:
                LOG.debug("Executing cmd=%s", cmd)
                stdX = cmd.execute()
                print(stdX)

                assertTrue(
                    all(x.exists() for x in ffmpeg2pass_files),
                    "Pass 1: Expected 2-pass files but they were missing",
                )
                # Move ffmpeg2pass files to WorkingDirectory
                for f in ffmpeg2pass_files:
                    target = self.wd.get_file(f.name)
                    if target.exists():
                        LOG.warning("Overwriting file %s", target)
                        target.unlink()
                    f.rename(target)

                # Prepare next step
                next_step_parameters = dict(self.parameters)
                next_step_parameters["ffmpeg2pass"] = ffmpeg2pass_name
                next_step = FFmpegTargetBitrate2passEncodeProcessingStep(
                    parameters=next_step_parameters, wd=self.wd
                )
                setattr(
                    self,
                    PROCESSING_STEP_RESULT_ATTR,
                    {RESULT_OUTPUT_NEXT_SPRINT_STEPS: [next_step]},
                )
            except Exception as e:
                raise RuntimeError(
                    f"Something went wrong during execution. stdX={stdX}"
                ) from e
        else:
            # 2nd pass
            _output_file = self.new_file(
                _stream, ContainerHelper.preferred_container(_encoder.codec)
            )
            ffmpeg2pass_name = self.parameters["ffmpeg2pass"]
            ffmpeg2pass_files = [
                (self.cwd / filename)
                for filename in ffmpeg2pass_file_names(ffmpeg2pass_name)
            ]
            # Copy ffmpeg2pass files from WorkingDirectory to CWD
            for f in ffmpeg2pass_files:
                if f.exists():
                    LOG.warning("Overwriting file %s", f)
                    f.unlink()
                f.write_bytes(self.wd.get_file(f.name).read_bytes())

            cmd, future_file = build_ffmpeg_command(
                inputs=[FfmpegInput(_stream.media_file, **_stream_opt)],
                ffmpeg=_encoder.executable,
                options=self.parameters.get("ffmpeg_opt"),
                output=_output_file,
                stream_mapping={_stream: _future_stream},
                extra=["-passlogfile", ffmpeg2pass_name],
            )
            stdX = None
            try:
                LOG.debug("Executing cmd=%s", cmd)
                stdX = cmd.execute()
                output_media_file = future_file.load_actual_file()
                setattr(
                    self,
                    PROCESSING_STEP_RESULT_ATTR,
                    {RESULT_OUTPUT_MEDIA_FILE: output_media_file},
                )
            except Exception as e:
                raise RuntimeError(
                    f"Something went wrong during execution. stdX={stdX}"
                ) from e


def ProcessingStep_execute(base_step: ProcessingStep):
    current_sprint: Set[ProcessingStep] = {base_step}
    sprint_id = 0
    output_files = set()

    while len(current_sprint) > 0:
        LOG.info("Processing sprint %s", sprint_id)

        if output_files:
            LOG.info(
                "Discarding output files from steps in previous sprint: %s",
                output_files,
            )
            output_files = set()
        next_sprint = set()
        for step in current_sprint:
            step.run()
            res = step.result
            LOG.debug("Step result: %s", res)
            next_sprint_steps = res.pop(RESULT_OUTPUT_NEXT_SPRINT_STEPS, None)
            if next_sprint_steps:
                next_sprint.update(next_sprint_steps)
            output_file = res.pop(RESULT_OUTPUT_MEDIA_FILE, None)
            if output_file:
                output_files.add(output_file)

        current_sprint = next_sprint
        sprint_id += 1

    LOG.info("Stream processing finished with output files: %s", output_files)


def test01_2p():
    test_video = Path("./test.mp4")
    assertTrue(test_video.exists() and test_video.is_file(), "Can't find test file")
    wd = WorkingDirectory(target_file=test_video)
    encoder = FFmpegEncoder("libx264")
    print(encoder.spec)
    encoder.set_parameters(preset="fast")
    mf = MediaFile(test_video)
    streams = mf.get_streams(StreamCriteria(codec_type=StreamType.VIDEO, codec=None))
    assertTrue(len(streams) == 1, "Expected 1 stream, got {}", len(streams))
    # output_file = Path("./res3.mp4").resolve()
    step = FFmpegTargetBitrate2passEncodeProcessingStep(
        parameters={
            "input": streams[0],
            "input_opt": {},
            "encoder": encoder,
            "ffmpeg_opt": FfmpegOptions(hide_banner=True, no_stats=True),
            "target_bitrate": "2000k",
        },
        wd=wd,
    )
    ProcessingStep_execute(step)


def test01():
    test_video = Path("./test.mp4")
    assertTrue(test_video.exists() and test_video.is_file(), "Can't find test file")
    wd = WorkingDirectory(target_file=test_video)
    encoder = FFmpegEncoder("libx264")
    print(encoder.spec)
    encoder.set_parameters(crf=33, preset="fast")
    mf = MediaFile(test_video)
    streams = mf.get_streams(StreamCriteria(codec_type=StreamType.VIDEO, codec=None))
    assertTrue(len(streams) == 1, "Expected 1 stream, got {}", len(streams))
    step = FFmpegSimpleTranscodeProcessingStep(
        parameters={
            "input": streams[0],
            "input_opt": {},
            "encoder": encoder,
            "ffmpeg_opt": FfmpegOptions(hide_banner=True, no_stats=True),
        },
        wd=wd,
    )
    step.run()
    from pprint import pprint

    pprint(step.result)


def test02():
    """Tests MKVMergeMuxProcessingStep"""
    logging.basicConfig(level=logging.DEBUG)
    testVideo1 = Path(r"G:\Github-DRSCUI\video-test-clips\output.mp4")
    testVideo2 = Path(r"G:\Github-DRSCUI\video-test-clips\trailer.mkv")
    assertTrue(testVideo1.exists() and testVideo2.exists(), "Can't find test files")
    mf1, mf2 = MediaFile(testVideo1), MediaFile(testVideo2)
    step = MKVMergeProcessingStep(
        parameters={
            "inputs": [mf1.streams[0], mf2.streams[1]],
            "output": Path("./res.mkv"),
            "mode": MKVMergeMode.MERGE,
        },
    )
    step.run()
    print(step.result)


def test02_2():
    """Tests MKVMergeMuxProcessingStep"""
    logging.basicConfig(level=logging.DEBUG)
    testVideo1 = Path(r"G:\Github-DRSCUI\video-test-clips\animation-movie-01.ts")
    testVideo2 = Path(r"G:\Github-DRSCUI\video-test-clips\animation-movie-02.ts")
    assertTrue(testVideo1.exists() and testVideo2.exists(), "Can't find test files")
    mf1, mf2 = MediaFile(testVideo1), MediaFile(testVideo2)
    step = MKVMergeProcessingStep(
        parameters={
            "inputs": [mf1.streams[0], mf2.streams[0]],
            "output": Path("./res2.mkv"),
            "mode": MKVMergeMode.JOIN,
        },
    )
    step.run()
    print(step.result)


def test03():
    test_video = Path("has_chapters.mkv")
    from FFmpyg.ffprobe import file_stream_info

    # mf = MediaFile(test_video)
    # for stream in mf.streams.values():
    #     print(str(stream))
    from pprint import pprint

    pprint(file_stream_info(test_video))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    test01_2p()
