"""Minimal config object for TruFor inference — replaces yacs dependency.

Matches the configuration in test_docker/src/trufor.yaml exactly.
"""


class _Cfg:
    """Simple attribute-access config matching yacs CfgNode interface."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __contains__(self, key):
        return hasattr(self, key)


def get_trufor_config():
    """Return a config object matching trufor.yaml for inference."""
    cfg = _Cfg(
        MODEL=_Cfg(
            NAME="detconfcmx",
            PRETRAINED="",  # empty → skip pretrained loading, use full checkpoint
            MODS=("RGB", "NP++"),
            EXTRA=_Cfg(
                BACKBONE="mit_b2",
                DECODER="MLPDecoder",
                DECODER_EMBED_DIM=512,
                PREPRC="imagenet",
                BN_EPS=0.001,
                BN_MOMENTUM=0.1,
                DETECTION="confpool",
                CONF=True,
                NP_WEIGHTS="",
            ),
        ),
        DATASET=_Cfg(NUM_CLASSES=2),
    )
    return cfg
