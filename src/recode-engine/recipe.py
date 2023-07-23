import logging
from typing import Any, Dict, Iterator, Set, Tuple

from DRSlib.utils import assertTrue
from DRSlib.mediainfo import MediaInfo
from FFmpyg.media import MediaFile, StreamCriteria, StreamType, FfprobeInfoKey

from logic import Grammar, DataStructureValidator
from utils import is_a_collection

LOG = logging.getLogger(__file__)

KW_SPEC_VERSION = "recode-engine"

KW_RECIPE_ROOT = "recipe"
KW_RECIPE_INPUT = "input"
KW_RECIPE_ARGUMENTS = "arguments"
KW_RECIPE_STREAM_PROCESSOR = "stream-processor"
KW_RECIPE_POST_PROCESSING = "post-processing"
KW_RECIPE_OUTPUT = "output"

KW_STREAMTYPE_ROOT = "streams"
KW_STREAMTYPE_VIDEO = "video"
KW_STREAMTYPE_AUDIO = "audio"
KW_STREAMTYPE_SUBTITLE = "subtitle"
KW_STREAMTYPE_ATTACHMENT = "attachment"

# Keywords exclusive to argument definition (also: see KW_DEFAULT)
KW_ARGUMENT_TYPE = "type"
KW_ARGUMENT_VALUE_LIST = "values"
KW_ARGUMENT_REQUIRED = "required"

# Control flow keywords
KW_CF_CASE = "case"  # should have a default case, may have as many if cases as needed
KW_CF_IF = "if"
KW_CF_THEN = "then"  # comes after if

# SPECIAL KEYWORDS
KW_DEFAULT = "default"  # used both for default value in arguments and default case

# Data point reference (in comment the applicable media scope: FILE, STREAM[?])
KW_DP_EXTENSION = "extension"  # FILE : str (no '.')
KW_DP_SIZE = "size"  # FILE, STREAM : int
KW_DP_DURATION = "duration"  # FILE, STREAM[VIDEO,AUDIO] : int
KW_DP_NB_STREAMS = "nb-streams"  # FILE : int
KW_DP_WIDTH = "width"  # STREAM[VIDEO] : int
KW_DP_HEIGHT = "height"  # STREAM[VIDEO] : int
KW_DP_BIT_DEPTH = "bit-depth"  # STREAM[VIDEO] : int
KW_DP_BITRATE = "bitrate"  # FILE, STREAM[VIDEO,AUDIO] : int
KW_DP_CODEC = "codec"  # STREAM : str
KW_DP_HAS_CHAPTERS = "has-chapters"  # FILE : bool
KW_DP_Q_INDEX = "quality-index"  # STREAM[VIDEO] : float

# Data point specifiers
KW_DPS_MAX = "max"
KW_DPS_MIN = "min"
KW_DPS_BLACKLIST = "blacklist"
KW_DPS_WHITELIST = "whitelist"

# Non-data point reference
KW_NDP_ARGUMENT = "argument"

# Non-data point specifiers
KW_NDPS_NAME = "name"
KW_NDPS_VALUE = "value"

KW_OUTPUT_DIRECTORY = "directory"
KW_OUTPUT_SUFFIX = "suffix"

KW_PROCESSOR = "processor"
KW_PROCESSOR_PARAMETERS = "parameters"

# KeyWord sets
ALL_DPS = {
    KW_DPS_MAX,
    KW_DPS_MIN,
    KW_DPS_BLACKLIST,
    KW_DPS_WHITELIST,
}
ALL_FILE_DP = {
    KW_DP_EXTENSION,
    KW_DP_SIZE,
    KW_DP_DURATION,
    KW_DP_NB_STREAMS,
    KW_DP_BITRATE,
    KW_DP_HAS_CHAPTERS,
}
ALL_STREAMTYPE = {
    KW_STREAMTYPE_VIDEO,
    KW_STREAMTYPE_AUDIO,
    KW_STREAMTYPE_SUBTITLE,
    KW_STREAMTYPE_ATTACHMENT,
}
ALL_GENERIC_STREAM_DP = {
    KW_DP_NB_STREAMS,
    KW_DP_CODEC,
}
ALL_AV_STREAM_DP = ALL_GENERIC_STREAM_DP.union(
    {
        KW_DP_SIZE,
        KW_DP_DURATION,
        KW_DP_BITRATE,
    }
)
ALL_VIDEO_DP = ALL_AV_STREAM_DP.union(  # add 'bit-depth'
    {
        KW_DP_WIDTH,
        KW_DP_HEIGHT,
        KW_DP_Q_INDEX,
        KW_DP_BIT_DEPTH,
    }
)
STREAM_PROCESSOR_GRAMMAR_DEFINITION = [
    Grammar.all_of({KW_PROCESSOR}),
    Grammar.all_of({KW_PROCESSOR_PARAMETERS}),
]

RECIPE_CASE_STRUCTURE = Grammar.nonterminal_collection(
    allowed_items={KW_DEFAULT, KW_CF_IF}
)

ARGUMENT_TYPE_MAPPER = {"str": str, "int": int, "float": float, "bool": bool}
ARGUMENT_TYPE_ALLOWED_VALUES = set(ARGUMENT_TYPE_MAPPER.keys())

RECIPE_STRUCTURE = {
    Grammar.DICT_TREE_ROOT: Grammar.all_of({KW_SPEC_VERSION, KW_RECIPE_ROOT}),
    KW_SPEC_VERSION: Grammar.terminal_variable(),
    KW_RECIPE_ROOT: Grammar.combine(
        [
            Grammar.all_of(
                {
                    KW_RECIPE_INPUT,
                    KW_RECIPE_STREAM_PROCESSOR,
                    KW_RECIPE_POST_PROCESSING,
                    KW_RECIPE_OUTPUT,
                }
            ),
            Grammar.any_of({KW_RECIPE_ARGUMENTS}),
        ]
    ),
    KW_RECIPE_INPUT: Grammar.any_of(ALL_FILE_DP.union({KW_STREAMTYPE_ROOT})),
    KW_STREAMTYPE_ROOT: Grammar.at_least_1_of(ALL_STREAMTYPE),
    KW_STREAMTYPE_VIDEO: Grammar.at_least_1_of(ALL_VIDEO_DP),
    KW_STREAMTYPE_AUDIO: Grammar.at_least_1_of(ALL_AV_STREAM_DP),
    KW_STREAMTYPE_SUBTITLE: Grammar.at_least_1_of(ALL_GENERIC_STREAM_DP),
    KW_STREAMTYPE_ATTACHMENT: Grammar.at_least_1_of(ALL_GENERIC_STREAM_DP),
    KW_DP_EXTENSION: Grammar.at_least_1_of(ALL_DPS),
    KW_DP_SIZE: Grammar.at_least_1_of(ALL_DPS),
    KW_DP_DURATION: Grammar.at_least_1_of(ALL_DPS),
    KW_DP_NB_STREAMS: Grammar.at_least_1_of(ALL_DPS),
    KW_DP_HEIGHT: Grammar.at_least_1_of(ALL_DPS),
    KW_DP_WIDTH: Grammar.at_least_1_of(ALL_DPS),
    KW_DP_BITRATE: Grammar.at_least_1_of(ALL_DPS),
    KW_DP_CODEC: Grammar.at_least_1_of(ALL_DPS),
    KW_DP_HAS_CHAPTERS: Grammar.terminal_variable(bool),
    KW_DP_Q_INDEX: Grammar.at_least_1_of(ALL_DPS),
    KW_RECIPE_ARGUMENTS: Grammar.any(),
    KW_RECIPE_ARGUMENTS
    + ".*": Grammar.combine(
        [
            Grammar.all_of({KW_ARGUMENT_TYPE, KW_ARGUMENT_REQUIRED, KW_DEFAULT}),
            Grammar.any_of(ALL_DPS),
        ]
    ),
    KW_RECIPE_ARGUMENTS
    + ".*."
    + KW_ARGUMENT_TYPE: Grammar.terminal_variable(
        str, allowed_values=ARGUMENT_TYPE_ALLOWED_VALUES
    ),
    KW_RECIPE_ARGUMENTS
    + ".*."
    + KW_ARGUMENT_VALUE_LIST: Grammar.terminal_collection(str),
    KW_RECIPE_ARGUMENTS + ".*." + KW_ARGUMENT_REQUIRED: Grammar.terminal_variable(bool),
    KW_RECIPE_ARGUMENTS + ".*." + KW_DEFAULT: Grammar.terminal_variable(),
    KW_DEFAULT: Grammar.combine(STREAM_PROCESSOR_GRAMMAR_DEFINITION),
    KW_RECIPE_STREAM_PROCESSOR: Grammar.at_least_1_of(ALL_STREAMTYPE),
    KW_RECIPE_STREAM_PROCESSOR
    + ".*": Grammar.combine(
        STREAM_PROCESSOR_GRAMMAR_DEFINITION + [Grammar.all_of({KW_CF_CASE})]
    ),
    KW_CF_CASE: RECIPE_CASE_STRUCTURE,
    KW_CF_IF: Grammar.combine([Grammar.all_of({KW_CF_THEN}), Grammar.any()]),
    KW_CF_THEN: Grammar.combine(STREAM_PROCESSOR_GRAMMAR_DEFINITION),
    KW_RECIPE_POST_PROCESSING: Grammar.nonterminal_collection(
        allowed_items={KW_CF_CASE}
    ),
    KW_RECIPE_OUTPUT: Grammar.all_of({KW_OUTPUT_DIRECTORY, KW_OUTPUT_SUFFIX}),
    KW_OUTPUT_DIRECTORY: Grammar.terminal_variable(str),
    KW_OUTPUT_SUFFIX: Grammar.terminal_variable(str),
    KW_DPS_MAX: Grammar.terminal_variable(),
    KW_DPS_MIN: Grammar.terminal_variable(),
    KW_DPS_BLACKLIST: Grammar.combine(
        [Grammar.terminal_collection(str), Grammar.terminal_variable(str)]
    ),
    KW_DPS_WHITELIST: Grammar.combine(
        [Grammar.terminal_collection(str), Grammar.terminal_variable(str)]
    ),
    KW_NDP_ARGUMENT: Grammar.any_of({KW_NDPS_NAME, KW_NDPS_VALUE}),
    KW_NDPS_NAME: Grammar.terminal_variable(str),
    KW_NDPS_VALUE: Grammar.terminal_variable(),
    KW_PROCESSOR: Grammar.terminal_variable(str),
    KW_PROCESSOR_PARAMETERS: Grammar.any(),
    KW_PROCESSOR_PARAMETERS + ".*": Grammar.terminal_variable(),
}

STREAMTYPE_FILTER_DP = {
    KW_STREAMTYPE_VIDEO: ALL_VIDEO_DP,
    KW_STREAMTYPE_AUDIO: ALL_AV_STREAM_DP,
    KW_STREAMTYPE_SUBTITLE: ALL_GENERIC_STREAM_DP,
    KW_STREAMTYPE_ATTACHMENT: ALL_GENERIC_STREAM_DP,
}

MI_VIDEO = "Video"
MI_AUDIO = "Audio"
MI_SUBTITLE = "Text"
MI_STREAM_SIZE = "Stream size"
MI_STREAM_DURATION = "Duration"
MI_STREAM_BITRATE = "Bit rate"
MI_STREAM_Q_INDEX = "Bits/(Pixel*Frame)"
MI_STREAM_BIT_DEPTH = "Bit depth"
MI_DURATION_QUALIFIERS = {"h": 60**2, "min": 60, "s": 1}

HUMAN_UNIT_FACTOR = {
    "G": 10**9,
    "M": 10**6,
    "K": 10**3,
}


def duration_MI_to_s(duration: str) -> int:
    """Converts MediaInfo duration into seconds
    ex:
    - '2 min 12 s' => 132
    - '1 h 10 min' => 4200
    - '4 s' => 4
    /!\ when calling you must catch exceptions
    """
    tokens = duration.split(" ")
    assertTrue(len(tokens) % 2 == 0, "Invalid format")
    res = 0
    for i in range(len(tokens) // 2):
        j = i * 2
        res += int(tokens[j]) * MI_DURATION_QUALIFIERS[tokens[j + 1]]
    return res


def weak_parse(s: Any) -> int | float | str | Any:
    """Attempts to parse strings into numbers
    ex:
    - duration into seconds : '1 h 10 min' => 4200; '2 min 12 s' => 132
    - human-friendly factors : '217M' => 217000000; '1.2k' => 1200
    """
    if not isinstance(s, str):
        # LOG.debug("weak_parse1")
        return s
    try:
        # LOG.debug("weak_parse2")
        return duration_MI_to_s(s)
    except (AssertionError, ValueError) as e:
        # LOG.debug("duration_MI_to_s failed on '%s' because of %s", s, e)
        pass
    unit_factor = s[-1].upper()
    if unit_factor in HUMAN_UNIT_FACTOR:
        # LOG.debug("weak_parse3")
        try:
            return int(s[:-1]) * HUMAN_UNIT_FACTOR[unit_factor]
        except ValueError:
            return float(s[:-1]) * HUMAN_UNIT_FACTOR[unit_factor]

    # LOG.debug("weak_parse4")
    return s


def weak_leaf_parse(tree: Any):
    """Goes through a data structure and attempts parsing leaf string values"""
    if isinstance(tree, dict):
        return {key: weak_leaf_parse(subtree) for key, subtree in tree.items()}
    if isinstance(tree, list):
        return [weak_leaf_parse(subtree) for subtree in tree]
    if isinstance(tree, str):
        return weak_parse(tree)
    return tree


def verify_rule(stream_rule: dict, stream_info: dict) -> bool:
    LOG.info("verify_rule: stream_rule=%s stream_info=%s", stream_rule, stream_info)
    assertTrue(
        len(stream_rule) == 1, "Expected a single rule entry, got {}", stream_rule
    )
    datapoint = next(iter(stream_rule))
    if datapoint not in stream_info:
        LOG.warning("Skipped because missing info for datapoint=%s", datapoint)
        return False

    data_is_set = isinstance(stream_info[datapoint], set)
    stream_info_dp = (
        {weak_parse(x) for x in stream_info[datapoint]}
        if data_is_set
        else weak_parse(stream_info[datapoint])
    )

    if not isinstance(stream_rule[datapoint], dict):
        return weak_parse(stream_rule[datapoint]) == stream_info_dp

    for dps in stream_rule[datapoint]:
        _r = stream_rule[datapoint][dps]
        r = (
            {weak_parse(x) for x in _r}
            if isinstance(_r, (set, list))
            else weak_parse(_r)
        )
        LOG.debug("dps=%s stream_info_dp=%s _r=%s r=%s", dps, stream_info_dp, _r, r)

        if dps == KW_DPS_MAX:
            if data_is_set:
                if any(r < v for v in stream_info_dp):
                    return False
            elif r < stream_info_dp:
                return False

        if dps == KW_DPS_MIN:
            if data_is_set:
                if any(v < r for v in stream_info_dp):
                    return False
            elif stream_info_dp < r:
                return False

        if dps == KW_DPS_BLACKLIST:
            if data_is_set:
                if any(v in r for v in stream_info_dp):
                    return False
            elif stream_info_dp in r:
                return False

        if dps == KW_DPS_WHITELIST:
            if data_is_set:
                if not all(v in r for v in stream_info_dp):
                    return False
            elif stream_info_dp not in r:
                return False

    return True


class Recipe:
    """A recipe declares how to transcode a media file :
    - Input
    - Options
    - Stream-specific processing
    - Post-processing steps (muxing, rename, etc)"""

    CURRENT_VERSION = 1
    VALIDATOR = DataStructureValidator(RECIPE_STRUCTURE)
    MEDIAINFO = MediaInfo()

    recipe: dict
    """Filter input files based on stream datapoints"""
    arguments: dict
    """recipe argument as <key:str>:<value:int|bool|str> dict"""

    def __init__(self, recipe: dict) -> None:
        self.recipe = weak_leaf_parse(Recipe.VALIDATOR.validate(recipe)[KW_RECIPE_ROOT])
        assertTrue(self.recipe is not None, "Invalid recipe")

    def validate_input(self, media: MediaFile) -> bool:
        def get_MI_streams_info(
            mediainfo_data: Dict[str, Dict[str, Any]],
            mediainfo_type: str,
            datapoint: str,
        ) -> set:
            return {
                stream_data[datapoint]
                for stream, stream_data in mediainfo_data.items()
                if stream.startswith(mediainfo_type) and datapoint in stream_data
            }

        def get_streams_info(
            stream_type: str, mediainfo_data: Dict[str, Dict[str, Any]]
        ) -> dict:
            """Returns media info from media for given type"""
            _type = (
                StreamType.VIDEO
                if stream_type == KW_STREAMTYPE_VIDEO
                else (
                    StreamType.AUDIO
                    if stream_type == KW_STREAMTYPE_AUDIO
                    else (
                        StreamType.SUBTITLE
                        if stream_type == KW_STREAMTYPE_SUBTITLE
                        else StreamType.ATTACHMENT
                    )
                )
            )
            _relevant_streams = media.get_streams(
                StreamCriteria(codec_type=_type, codec=None)
            )
            _info = {
                KW_DP_NB_STREAMS: len(_relevant_streams),
                KW_DP_CODEC: {s.get(FfprobeInfoKey.CODEC) for s in _relevant_streams},
            }
            if _type in (StreamType.VIDEO, StreamType.AUDIO):
                mediainfo_type = MI_VIDEO if _type == StreamType.VIDEO else MI_AUDIO
                _info[KW_DP_SIZE] = get_MI_streams_info(
                    mediainfo_data, mediainfo_type, MI_STREAM_SIZE
                )
                _info[KW_DP_DURATION] = get_MI_streams_info(
                    mediainfo_data, mediainfo_type, MI_STREAM_DURATION
                )
                _info[KW_DP_BITRATE] = get_MI_streams_info(
                    mediainfo_data, mediainfo_type, MI_STREAM_BITRATE
                )
            if _type == StreamType.VIDEO:
                _info[KW_DP_HEIGHT] = {
                    s.get(FfprobeInfoKey.HEIGHT) for s in _relevant_streams
                }
                _info[KW_DP_WIDTH] = {
                    s.get(FfprobeInfoKey.WIDTH) for s in _relevant_streams
                }
                _info[KW_DP_Q_INDEX] = get_MI_streams_info(
                    mediainfo_data, MI_VIDEO, MI_STREAM_Q_INDEX
                )
                _info[KW_DP_BIT_DEPTH] = get_MI_streams_info(
                    mediainfo_data, MI_VIDEO, MI_STREAM_BIT_DEPTH
                )

            return _info

        mediainfo_data = Recipe.MEDIAINFO.get_base_stats(media.path)
        file_info = {
            KW_DP_EXTENSION: media.path.suffix.replace(".", ""),
            KW_DP_SIZE: int(media.format_info["size"]),
            KW_DP_DURATION: float(media.format_info["duration"]),
            KW_DP_NB_STREAMS: len(media.streams),
            KW_DP_BITRATE: int(media.format_info["bit_rate"]),
            KW_DP_HAS_CHAPTERS: media.has_chapters,
        }

        input_rule = self.recipe[KW_RECIPE_ROOT][KW_RECIPE_INPUT]
        for key, rule in input_rule.items():
            if key == KW_STREAMTYPE_ROOT:
                for stream_type, stream_rules in rule.items():
                    stream_info = get_streams_info(stream_type, mediainfo_data)
                    LOG.debug("stream_type=%s stream_info=%s", stream_type, stream_info)
                    for stream_rule in stream_rules:
                        if not verify_rule(
                            {stream_rule: stream_rules[stream_rule]}, stream_info
                        ):
                            LOG.warning(
                                "File %s invalidated by rule %s.%s.%s",
                                media.path,
                                key,
                                stream_type,
                                stream_rule,
                            )
                            return False
            else:
                if not verify_rule({key: rule}, file_info):
                    LOG.warning("File %s invalidated by rule %s", media.path, key)
                    return False

        return True

    def load_arguments(self, actual_arguments: dict) -> None:
        """Load arguments from self.recipe into self.arguments"""
        res = {}
        if self.recipe[KW_RECIPE_ARGUMENTS]:
            for arg_name, arg_rules in self.recipe[KW_RECIPE_ARGUMENTS].items():
                if arg_name in actual_arguments:
                    res[arg_name] = match_actual_argument(
                        arg_name, arg_rules, actual_arguments[arg_name]
                    )
                elif KW_DEFAULT in arg_rules:
                    res[arg_name] = arg_rules[KW_DEFAULT]
                elif arg_rules.get(KW_ARGUMENT_REQUIRED, False):
                    raise ValueError(f"Missing required argument '{arg_name}'")
                else:
                    LOG.warning(
                        "Dropping argument '%s': no value given and no default set",
                        arg_name,
                    )
                    LOG.info("arg_rules=%s", arg_rules)
                    LOG.info(
                        "all_rules=%s", self.recipe[KW_RECIPE_ARGUMENTS]
                    )  #  default: 2M

        missed_args = set(actual_arguments).difference(set(res))
        if missed_args:
            LOG.warning("Arguments that were not loaded: %s", missed_args)

        self.arguments = res


def yield_items_with_keys(d: dict, keys: set) -> Iterator[tuple]:
    for k, v in d.items():
        if k in keys:
            yield k, v
        else:
            print(f"Skipping unexpected key '{k}': expected={keys})")


ALL_DPS_MIN_MAX = {KW_DPS_MIN, KW_DPS_MAX}
ALL_DPS_SETS = {KW_DPS_WHITELIST, KW_DPS_BLACKLIST}


def read_list(data: str | list) -> list:
    if isinstance(data, str):
        return [x.strip() for x in data.split(",")]
    if isinstance(data, list):
        return data
    raise ValueError(f"Expected string or list, found {type(data)}")


def match_dp_specifier(rules: dict, value: Any) -> bool:
    """Returns true if value is valid by dp specifier in rules"""
    is_numeric = isinstance(value, (int, float))
    if KW_DPS_MIN in rules:
        if not is_numeric or value < rules[KW_DPS_MIN]:
            return False
    if KW_DPS_MAX in rules:
        if not is_numeric or value > rules[KW_DPS_MAX]:
            return False
    if KW_DPS_BLACKLIST in rules:
        if value in rules[KW_DPS_BLACKLIST]:
            return False
    if KW_DPS_WHITELIST in rules:
        if value not in rules[KW_DPS_WHITELIST]:
            return False
    return True


def match_actual_argument(arg_name: str, arg_rules: dict, arg_value: Any) -> Any:
    try:
        # Cast type if needed
        expected_type = ARGUMENT_TYPE_MAPPER[arg_rules[KW_ARGUMENT_TYPE]]
        if not isinstance(arg_value, expected_type):
            arg_value = expected_type(arg_value)
        # Verify if value is in range if applicable
        assertTrue(
            match_dp_specifier(arg_rules, arg_value),
            "Value doesn't match min/max/whitelist/blacklist",
        )
        return arg_value
    except Exception as e:
        raise RuntimeError(
            f"Something went wrong while matching argument={arg_name} with value={arg_value} ({type(arg_value)}) given rules={arg_rules}"
        ) from e


def read_dp_specifier(
    spec: dict | str | float | int | bool,
) -> list | set | str | float | int | bool:
    """Reads specifier of the following types:
    - simple value
    - min-max interval
    - whitelist/blacklist set
    raises ValueError
    """
    # Case: simple value
    if not isinstance(spec, dict):
        return spec
    # Case: min-max (open or closed) interval specifier
    if any(x in spec for x in ALL_DPS_MIN_MAX):
        sspec = dict(yield_items_with_keys(spec, ALL_DPS_MIN_MAX))
        return [sspec.get(KW_DPS_MIN), sspec.get(KW_DPS_MAX)]
    # Case: whitelist/blacklist set specifier (either or)
    sspec = dict(yield_items_with_keys(spec, ALL_DPS_SETS))
    if KW_DPS_WHITELIST in sspec:
        if KW_DPS_BLACKLIST in sspec:
            print(f"Can't use both whitelist and blacklist on ")
        return read_list(sspec[KW_DPS_WHITELIST])
    if KW_DPS_BLACKLIST in sspec:
        return read_list(sspec[KW_DPS_BLACKLIST])
    # None of the previous cases
    raise ValueError(f"Failed to read specifier: {spec}")


def read_file_input(recipe: dict) -> Tuple[dict, dict]:
    input_filter_file = {}
    input_filter_streams = {}

    # Read file filter
    for _filter, value in yield_items_with_keys(recipe, ALL_FILE_DP):
        try:
            input_filter_file[_filter] = read_dp_specifier(value)
        except ValueError as e:
            print(e)

    # Read stream-secific filters
    if KW_STREAMTYPE_ROOT in recipe:
        for stream_type, filters in yield_items_with_keys(
            recipe[KW_STREAMTYPE_ROOT], ALL_STREAMTYPE
        ):
            _filters = {}
            for _filter, value in yield_items_with_keys(
                filters, STREAMTYPE_FILTER_DP[stream_type]
            ):
                try:
                    _filters[_filter] = read_dp_specifier(value)
                except ValueError as e:
                    print(e)
            input_filter_streams[stream_type] = _filters

    return input_filter_file, input_filter_streams


def read_recipe(recipe: dict, curr_token: str | None = None):
    if curr_token is None:
        curr_token = RECIPE_STRUCTURE_ROOT
    actual_recipe = {}
    expected_children_keys: Set[str] = RECIPE_STRUCTURE[curr_token]

    for k, v in recipe.items():
        if k in expected_children_keys:
            pass
        # RECIPE_STRUCTURE_SIMPLE_VALUE = "val"
        # RECIPE_STRUCTURE_LIST_VALUE = "lst"
        # RECIPE_STRUCTURE_ARGUMENT_FIELD = "arg"
        # RECIPE_STRUCTURE_POST_PROCESSING_STEP = "pps"

        print(
            f"Skipping unexpected key '{k}': curr_token={curr_token} expected={expected_children_keys})"
        )
