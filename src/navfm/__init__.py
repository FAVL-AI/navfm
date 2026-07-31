"""navfm -- reproducible GNM / ViNT / NoMaD research infrastructure.

Public surface:

``navfm.schema``      the GNM on-disk format, encoded as checkable constraints
``navfm.writer``      atomic, crash-safe GNM-format trajectory writer
``navfm.validate``    strict dataset validator (CLI: ``python -m navfm.validate``)
``navfm.stats``       derive ``metric_waypoint_spacing`` and ``action_stats``
``navfm.splits``      deterministic, scene-grouped train/test splits
``navfm.kinematics``  SE(2) helpers that bit-match the reference action pipeline
``navfm.control``     demonstrator and waypoint-tracking controllers
``navfm.planning``    occupancy grid, A*, path smoothing, episode sampling
``navfm.upstream``    locating and driving the pinned reference implementation
``navfm.isaac``       Isaac Sim collection (imports Isaac lazily)
``navfm.models``      checkpoint loading for the three released models
``navfm.train``       single-GPU fine-tuning
``navfm.eval``        reference-exact offline metrics and closed-loop metrics
"""

__version__ = "0.1.0"
