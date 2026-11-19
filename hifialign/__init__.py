"""HiFi multiplex alignment: out-of-core registration of multiplex imaging rounds."""
from .project import ChannelSpec, Project, RoundSpec, SectionSpec
from .naming import channel_matches
from .sources import open_source, round_label_from_path

__version__ = '2.0.0'


def make_round(path: str, reference_channel: str = 'DAPI') -> RoundSpec:
    """Create a RoundSpec from a file, with its channels read from the metadata."""
    src = open_source(path)
    try:
        chans = [ChannelSpec(channel=c, marker=(c if channel_matches(c, reference_channel) else ''))
                 for c in src.channels]
    finally:
        src.close()
    return RoundSpec(path=src.path, label=round_label_from_path(path), channels=chans)
