from itertools import product
from PIL import Image, ImageFont
import numpy as np
import torch
import torch.nn.functional as F
from pydantic import BaseModel
from typing import Tuple

from {{cookiecutter.package_name}} import problem


def class_index(class_name):
    return problem.settings.CLASS_NAMES.index(class_name)


class Prediction(BaseModel):
    logits: torch.Tensor
    preprocessed: torch.Tensor
    image: Image.Image

    class Config:
        arbitrary_types_allowed = True
        allow_mutation = False

    def class_name(self):
        return problem.settings.CLASS_NAMES[self.logits.argmax()]

    def annotated_image(self):
        return self.example.annotated_image()

    @property
    def _repr_png_(self):
        return self.annotated_image()._repr_png_


class PredictionBatch(BaseModel):
    logits: torch.Tensor
    preprocessed: torch.Tensor
    images: Tuple[Image.Image, ...]

    class Config:
        arbitrary_types_allowed = True
        allow_mutation = False

    def __len__(self):
        return len(self.logits)

    def __getitem__(self, index):
        return Prediction(
            logits=self.logits[index],
            preprocessed=self.preprocessed[index],
            image=self.images[index],
        )

    def __iter__(self):
        for index in range(len(self)):
            yield self[index]

    def loss(self, class_names):
        targets = torch.tensor(
            [class_index(class_name) for class_name in class_names],
        ).to(self.logits).long()
        return F.cross_entropy(self.logits, targets)