"""statwarrant: what your statistical result warrants you to say.

Declare the smallest effect size of interest and its reason, analyse a result,
and get the claims it supports, the claims it does not, and why.

>>> import statwarrant as sw
>>> plan = sw.declare(sesoi=3, sesoi_source="smallest score gain teachers act on",
...                   units="points", scope="first-year students, one university, one term")
>>> res = plan.analyze(estimate=4.2, se=1.6, df=58)
>>> res.check("There is no difference between the groups.").level
'conflict'
"""

from ._core import Evidence, Thresholds, evaluate
from ._version import __version__
from .adapters import AdapterMismatch
from .claims import CheckResult, Claim, Claims, Part
from .design import DesignPoint, DesignTable, design_point
from .plan import Plan, Result, declare


__all__ = [
    "declare",
    "Plan",
    "Result",
    "Evidence",
    "Thresholds",
    "Claim",
    "Claims",
    "CheckResult",
    "Part",
    "AdapterMismatch",
    "DesignPoint",
    "DesignTable",
    "design_point",
    "evaluate",
    "__version__",
]
