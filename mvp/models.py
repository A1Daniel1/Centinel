"""Modelo del piloto: ResNet-18 adaptada a N canales, una salida (logit de deforestación).

Las dos configuraciones comparadas usan la MISMA arquitectura; solo cambia el número
de canales de entrada (8 ópticos vs. 12 = ópticos + SAR).
"""
import torch.nn as nn
from torchvision.models import resnet18


def build_model(in_ch, pretrained=False):
    m = resnet18(weights="IMAGENET1K_V1" if pretrained else None)
    conv = nn.Conv2d(in_ch, 64, kernel_size=7, stride=2, padding=3, bias=False)
    if pretrained:   # promedia los pesos RGB y los replica en los canales de entrada
        w = m.conv1.weight.data.mean(1, keepdim=True).repeat(1, in_ch, 1, 1) * 3.0 / in_ch
        conv.weight.data.copy_(w)
    m.conv1 = conv
    m.maxpool = nn.Identity()          # parches pequeños: conservar resolución espacial
    m.fc = nn.Linear(512, 1)
    return m
