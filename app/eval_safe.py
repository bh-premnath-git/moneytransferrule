import ast
from evalidate import Expr, base_eval_model, EvalException

SAFE = base_eval_model.clone()

# deny ALL functions / attributes depending on evalidate version
if hasattr(SAFE, "funcs"):
    SAFE.funcs.clear()
    SAFE.names.clear()
    if hasattr(SAFE, "allowed_nodes"):
        SAFE.allowed_nodes.update({
            "Expression", "BoolOp", "BinOp", "UnaryOp", "Compare",
            "Name", "Load", "Constant",
            "And", "Or", "Not", "Eq", "NotEq", "Lt", "LtE", "Gt", "GtE",
        })
else:
    SAFE.allowed_functions = []
    SAFE.imported_functions = {}
    SAFE.attributes = []
    SAFE.nodes = [
        "Expression", "BoolOp", "BinOp", "UnaryOp", "Compare", "Name", "Load",
        "Constant", "And", "Or", "Not", "Eq", "NotEq", "Lt", "LtE", "Gt", "GtE",
    ]


ALLOWED = (
    ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare,
    ast.Name, ast.Load, ast.Constant, ast.And, ast.Or, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)

_AST_CACHE: dict[str, ast.AST] = {}


def _compile(expr: str) -> ast.AST:
    """Parse once & cache the tree."""
    if expr not in _AST_CACHE:
        tree = ast.parse(expr, mode="eval")
        for n in ast.walk(tree):
            if not isinstance(n, ALLOWED):
                raise ValueError(f"Disallowed node {type(n).__name__}")
        _AST_CACHE[expr] = tree
    return _AST_CACHE[expr]

def safe_eval(expr: str, ctx: dict) -> bool:
    tree = _compile(expr)
    try:
        return bool(Expr(tree, model=SAFE).eval(ctx))
    except EvalException:
        return False
