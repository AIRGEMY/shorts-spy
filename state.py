# state.py — shared mutable globals
# Import this module with "import state" and access as state.CHANNELS / state._active_profile
# Never do "from state import _active_profile" or reassignment won't propagate

from config import DEFAULT_CHANNELS

CHANNELS        = list(DEFAULT_CHANNELS)
_active_profile = None
