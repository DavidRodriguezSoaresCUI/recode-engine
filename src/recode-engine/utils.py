from collections.abc import Sequence
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Tuple

from FFmpyg.media import MediaFile, Stream, StreamType

MKVMERGE_STREAM_TYPE_ARGUMENT = {
    StreamType.VIDEO: {True: "--video-tracks", False: "--no-video"},
    StreamType.AUDIO: {True: "--audio-tracks", False: "--no-audio"},
    StreamType.SUBTITLE: {True: "--subtitle-tracks", False: "--no-subtitles"},
    StreamType.ATTACHMENT: {True: "--attachments", False: "--no-attachments"},
}


class MKVMergeMode(Enum):
    """Represents MKVMerge modes"""

    MERGE = auto()
    JOIN = auto()


def make_mkvmerge_merge_command_from_streams(
    executable: str | Path, output: Path, inputs: List[Stream], mode: MKVMergeMode
) -> list:
    """Generate mkvmkerge list-style command to merge streams into a MKV file"""
    # Prepare data for mkvmerge command
    _source_files: List[MediaFile] = []
    _stream_id: Dict[Stream, str] = {}
    _stream_per_file: Dict[MediaFile, Dict[StreamType, List[int]]] = {}
    for input_stream in inputs:
        _src_file: MediaFile = input_stream.media_file
        if _src_file is None:
            raise ValueError("MediaFile must be initialized")

        # Compute stream id
        if _src_file not in _source_files:
            _source_files.append(_src_file)
        _file_id = _source_files.index(_src_file)
        _stream_id[input_stream] = f"{_file_id}:{input_stream.idx}"

        # Add info on file stream list
        _stream_per_file.setdefault(_src_file, {}).setdefault(
            input_stream.stream_type, []
        ).append(input_stream.idx)

    # Crafting mkvmkerge command
    mkvmerge_cmd = [executable, "--output", output]
    for idx, _src_file in enumerate(_source_files):
        for stream_type, rule in MKVMERGE_STREAM_TYPE_ARGUMENT.items():
            _matching_stream_idxs = _stream_per_file[_src_file].get(stream_type)
            if _matching_stream_idxs:
                mkvmerge_cmd += [
                    rule[True],
                    ",".join(str(i) for i in _matching_stream_idxs),
                ]
            else:
                mkvmerge_cmd.append(rule[False])
        if idx > 0 and mode == MKVMergeMode.JOIN:
            mkvmerge_cmd.append("+")
        mkvmerge_cmd.append(_src_file.path)

    if mode == MKVMergeMode.MERGE:
        mkvmerge_cmd.append("--track-order")
        mkvmerge_cmd.append(
            ",".join(_stream_id[input_stream] for input_stream in inputs)
        )

    return mkvmerge_cmd


def ffmpeg2pass_file_names(name: str) -> Tuple[str, str]:
    """Return the names of the 2 files generated during 2-pass encoding"""
    return f"{name}-0.log", f"{name}-0.log.mbtree"


def get_valid_ffmpeg2pass_name(base_name: str) -> str:
    """Returns name for ffmpeg2pass that doesn't already exist"""
    cwd = Path(".").resolve()
    idx = 0
    while True:
        for filename in ffmpeg2pass_file_names(f"{base_name}_{idx}"):
            if (cwd / filename).exists():
                idx += 1
                continue
        return f"{base_name}_{idx}"


def is_a_collection(obj: Any) -> bool:
    """Returns True on collection, False on collection-like objects and"""
    return isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray))
