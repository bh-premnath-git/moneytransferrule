import ast
from evalidate import Expr, base_eval_model, EvalException

SAFE = base_eval_model.clone()
SAFE.allowed_functions = []
SAFE.imported_functions = {}
SAFE.attributes = []
SAFE.nodes = [
    'Expression', 'BoolOp', 'BinOp', 'UnaryOp', 'Compare', 'Name', 'Load',
    'Constant', 'And', 'Or', 'Not', 'Eq', 'NotEq', 'Lt', 'LtE', 'Gt', 'GtE'
]

ALLOWED = (
    ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare,
    ast.Name, ast.Load, ast.Constant, ast.And, ast.Or, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)

def _assert_safe(expr: str):
    for node in ast.walk(ast.parse(expr, mode="eval")):
        if not isinstance(node, ALLOWED):
            raise ValueError(f"Disallowed node: {type(node).__name__}")

def safe_eval(expr: str, ctx: dict) -> bool:
    _assert_safe(expr)                       # compile‑time guard
    try:
        return bool(Expr(expr, model=SAFE).eval(ctx))
    except EvalException:
        return False
