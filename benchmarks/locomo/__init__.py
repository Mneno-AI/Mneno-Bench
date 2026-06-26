"""LOCOMO external benchmark integration."""

from benchmarks.locomo.dataset import load_locomo_dataset
from benchmarks.locomo.schema import (
    LOCOMOConversation,
    LOCOMODataset,
    LOCOMOMessage,
    LOCOMOQuestion,
)

__all__ = [
    "LOCOMOConversation",
    "LOCOMODataset",
    "LOCOMOMessage",
    "LOCOMOQuestion",
    "load_locomo_dataset",
]
