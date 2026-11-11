"""statwarrant: what your statistical result warrants you to say.

Declare the smallest effect size of interest and its reason, analyse a result,
and get the claims it supports, the claims it does not, and why.

>>> import statwarrant as sw
>>> plan = sw.declare(sesoi=3, sesoi_source="smallest score gain teachers act on",
...                   units="points", scope="first-year students, one university, one term")
>>> res = plan.analyze(estimate=4.2, se=1.6, df=58)
>>> res.check("There is no difference between the groups.").verdict
'blocked'
"""

from ._core import Evidence, evaluate
from .claims import CheckResult, Claim, Claims
from .design import DesignPoint, DesignTable, design_point
from .plan import Plan, Result, declare

__version__ = "0.1.0"

__all__ = [
    "declare",
    "Plan",
    "Result",
    "Evidence",
    "Claim",
    "Claims",
    "CheckResult",
    "DesignPoint",
    "DesignTable",
    "design_point",
    "evaluate",
    "__version__",
]
