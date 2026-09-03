"""RFC 8785 conformance."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from uap.canonical import serialize, canonicalize, loads


def test_keys_sorted_by_utf16_code_unit():
    assert serialize({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    assert serialize({"€": "euro", "$": "dollar"}) == '{"$":"dollar","€":"euro"}'


@pytest.mark.parametrize("value,expected", [
    (0.1, "0.1"), (1e21, "1e+21"), (1e-7, "1e-7"), (-0.0, "0"),
    (1.0, "1"), (333333333.33333329, "333333333.3333333"), (0, "0"), (-5, "-5"),
])
def test_ecmascript_number_format(value, expected):
    assert serialize(value) == expected


def test_control_characters_escaped():
    assert serialize("a\nb\tc") == '"a\\nb\\tc"'
    assert serialize("\x00") == '"\\u0000"'


def test_canonical_form_is_stable_across_key_order():
    a = {"z": [1, {"b": 2, "a": 3}], "y": None}
    b = {"y": None, "z": [1, {"a": 3, "b": 2}]}
    assert canonicalize(a) == canonicalize(b)


def test_duplicate_keys_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        loads('{"a":1,"a":2}')
