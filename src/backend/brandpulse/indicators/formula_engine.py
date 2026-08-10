"""可审计的自定义公式执行器。

公式只允许数值常量、变量、四则运算、幂运算和白名单数学函数，
不调用 Python eval，也不接触文件、网络或对象属性。
"""
import ast
import math
from typing import Any, Dict


class FormulaEvaluationError(ValueError):
    """公式无法在当前真实数据上下文中计算。"""


def _finite(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FormulaEvaluationError("结果不是数字") from exc
    if not math.isfinite(number) or abs(number) > 1e15:
        raise FormulaEvaluationError("结果超出可计算范围")
    return number


FUNCTIONS = {
    "abs": lambda x: abs(_finite(x)),
    "ln": lambda x: math.log(_finite(x)),
    "log": lambda x: math.log(_finite(x)),
    "sqrt": lambda x: math.sqrt(_finite(x)),
    "min": lambda *args: min(_finite(x) for x in args),
    "max": lambda *args: max(_finite(x) for x in args),
    "round": lambda x, ndigits=0: round(_finite(x), int(ndigits)),
}

ALLOWED_NODES = {
    ast.Expression, ast.Constant, ast.Name, ast.UnaryOp, ast.UAdd, ast.USub,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
    ast.Call, ast.Load,
}


def validate_expression_syntax(expression: str) -> None:
    """保存公式前验证语法和节点白名单；变量名在运行时再按真实数据校验。"""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise FormulaEvaluationError("表达式语法错误") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > 80:
        raise FormulaEvaluationError("表达式过于复杂")
    for node in nodes:
        if type(node) not in ALLOWED_NODES:
            raise FormulaEvaluationError(f"不支持的表达式节点: {type(node).__name__}")
        if isinstance(node, ast.Constant) and (isinstance(node.value, bool) or not isinstance(node.value, (int, float))):
            raise FormulaEvaluationError("只允许数值常量")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords:
                raise FormulaEvaluationError("只允许调用白名单数学函数")


class _Evaluator:
    def __init__(self, context: Dict[str, Any]):
        self.context = {key: _finite(value) for key, value in context.items()}
        self.nodes = 0

    def evaluate(self, expression: str) -> float:
        validate_expression_syntax(expression)
        tree = ast.parse(expression, mode="eval")
        return _finite(self.visit(tree))

    def visit(self, node: ast.AST) -> Any:
        self.nodes += 1
        if self.nodes > 80:
            raise FormulaEvaluationError("表达式过于复杂")
        method = getattr(self, f"visit_{type(node).__name__}", None)
        if not method:
            raise FormulaEvaluationError(f"不支持的表达式节点: {type(node).__name__}")
        return method(node)

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> float:
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise FormulaEvaluationError("只允许数值常量")
        return _finite(node.value)

    def visit_Name(self, node: ast.Name) -> float:
        if node.id not in self.context:
            raise FormulaEvaluationError(f"真实数据中不存在变量: {node.id}")
        return self.context[node.id]

    def visit_UnaryOp(self, node: ast.UnaryOp) -> float:
        value = _finite(self.visit(node.operand))
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.UAdd):
            return value
        raise FormulaEvaluationError("不支持的单目运算")

    def visit_BinOp(self, node: ast.BinOp) -> float:
        left = _finite(self.visit(node.left))
        right = _finite(self.visit(node.right))
        try:
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            elif isinstance(node.op, ast.Div):
                if right == 0:
                    raise FormulaEvaluationError("除数不能为 0")
                result = left / right
            elif isinstance(node.op, ast.Mod):
                if right == 0:
                    raise FormulaEvaluationError("模数不能为 0")
                result = left % right
            elif isinstance(node.op, ast.Pow):
                if abs(right) > 20:
                    raise FormulaEvaluationError("幂指数不能超过 20")
                result = left ** right
            else:
                raise FormulaEvaluationError("不支持的二元运算")
        except (OverflowError, ValueError, ZeroDivisionError) as exc:
            raise FormulaEvaluationError("数学运算失败") from exc
        return _finite(result)

    def visit_Call(self, node: ast.Call) -> float:
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            raise FormulaEvaluationError("只允许调用白名单数学函数")
        if node.keywords or len(node.args) > 8:
            raise FormulaEvaluationError("函数参数格式不支持")
        args = [self.visit(arg) for arg in node.args]
        try:
            return _finite(FUNCTIONS[node.func.id](*args))
        except (TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
            raise FormulaEvaluationError("数学函数计算失败") from exc


def evaluate_formula(expression: str, context: Dict[str, Any]) -> float:
    """在给定真实数据上下文中计算公式。"""
    return _Evaluator(context).evaluate(expression)
