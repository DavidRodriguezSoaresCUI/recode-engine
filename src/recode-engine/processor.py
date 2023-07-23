from abc import abstractmethod
from dataclasses import dataclass
import logging
from typing import Any, Dict

from FFmpyg.stream import Stream
from FFmpyg.virtualfs import WorkingDirectory


LOG = logging.getLogger(__file__)


@dataclass
class StreamProcessor:
    """Abstracts away the complexities of transcoding a stream, with discrete processing steps.
    Form a user standpoint, it is given an input, a configuration and its execution results
    in output files being generated.
    A stream processor is based on the use of processing steps: each processing step converts
    the source stream into another stream, and these steps can be chained to achieve more complex
    transcodes. In that way, the sole responsability of the stream processor is to manage the
    execution of these steps.
    """

    source: Stream
    """The source media file"""
    wd: WorkingDirectory
    """Organizes all produced files"""
    parameters: Dict[str, Any]
    """Configuration for the processor"""

    @abstractmethod
    def save(self) -> None:
        """Saves processor's configuration to file"""

    @abstractmethod
    def load(self, wd: WorkingDirectory) -> "StreamProcessor":
        """Load processor's configuration from file"""

    def process_step(base_step: ProcessingStep):
        """Executes given step. This involves working in sprints made of steps that are run in
        parallel. The first sprint only includes the base step, and each subsequent sprint is
        made of steps created in the previous sprint"""
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
