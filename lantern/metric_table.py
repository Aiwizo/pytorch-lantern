import textwrap
import pandas as pd
from lantern import FunctionalBase
from typing import Dict, Union, Any

# from wire_damage.tools import MapMetric, ReduceMetric, AggregateMetric


class MetricTable(FunctionalBase):
    name: str
    metrics: Dict[str, Any]
    # metrics: Dict[str, Union[MapMetric, ReduceMetric, AggregateMetric]]

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, name, metrics):
        super().__init__(
            name=name,
            metrics=metrics,
        )

    def compute(self):
        return {
            metric_name: value
            for metrics in self.metrics.values()
            for metric_name, value in metrics.compute().items()
        }

    def table(self):
        return "\n".join(
            [
                f"{self.name}:",
                textwrap.indent(
                    (
                        pd.Series(self.compute()).to_string(
                            name=True, dtype=False, index=True
                        )
                    ),
                    prefix="  ",
                ),
            ]
        )

    def __str__(self):
        return self.table()
