"""WaferNet: the two-layer convolutional network from the project spec.

Layer               Output         Parameters   Runs on
conv1  8 x 3x3      30 x 30 x 8    80           hardware
maxpool 2x2         15 x 15 x 8    0            host
conv2  8 x 3x3x8    13 x 13 x 8    584          hardware
maxpool 2x2         6 x 6 x 8      0            host
dense               9              2,601        host

Convolutions use no padding ("valid"), matching the hardware, which only
computes full 3x3 windows.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

# Order matters: these indices are the class labels everywhere in the project.
CLASS_NAMES = [
    "Center", "Donut", "Edge-Loc", "Edge-Ring", "Loc",
    "Near-full", "Random", "Scratch", "none",
]

INPUT_SIZE = 32


class WaferNet(nn.Module):
    def __init__(self, n1: int = 8, n2: int = 8, n_classes: int = len(CLASS_NAMES)):
        super().__init__()
        self.conv1 = nn.Conv2d(1, n1, kernel_size=3)
        self.conv2 = nn.Conv2d(n1, n2, kernel_size=3)
        side = ((INPUT_SIZE - 2) // 2 - 2) // 2  # 32 -> 30 -> 15 -> 13 -> 6
        self.fc = nn.Linear(n2 * side * side, n_classes)

    def forward(self, x: torch.Tensor, return_layer_inputs: bool = False):
        p1 = F.max_pool2d(F.relu(self.conv1(x)), 2)
        p2 = F.max_pool2d(F.relu(self.conv2(p1)), 2)
        logits = self.fc(p2.flatten(1))
        if return_layer_inputs:
            # The tensors that would be streamed into the hardware for each layer.
            return logits, {"conv1": x, "conv2": p1}
        return logits


def count_parameters(model: nn.Module) -> dict:
    return {name: sum(p.numel() for p in m.parameters())
            for name, m in model.named_children()}
