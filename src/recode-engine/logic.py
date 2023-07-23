"""
How grammar rules are typically represented as production rules:
<non-terminal token> -> <product>
Here grammar is represented as a dict with entries <non-terminal token>:<GrammarRule>
GrammarRule here represents a matcher for product, but also contains logic to keep
matched product in data structure
In a dict tree, keys are non-terminal and values are terminal/leafs. This means that collections
of dicts are not allowed.
"""

import logging
import re
from re import Pattern
from time import time
from typing import Any, Callable, Dict, List, Type

from utils import is_a_collection

LOG = logging.getLogger(__file__)


EXPECTED_TERMINAL_TYPES = (str, int, float, bool)
EXPECTED_NON_TERMINAL_TYPES = (dict, list)
GRAMAR_RULE_TYPE = Callable[[Any], set]


class Grammar:
    """Implements grammar rules to verify the structure of given dict trees"""

    DICT_TREE_ROOT = "/"

    @staticmethod
    def combine(grammar_rules: List[GRAMAR_RULE_TYPE]) -> GRAMAR_RULE_TYPE:
        """Combines multiple grammar rules in an or-like fashion"""

        def wrapped(values: Any) -> set:
            nonlocal grammar_rules
            res = set()
            for rule in grammar_rules:
                res = res.union(rule(values))
            return res

        return wrapped

    @staticmethod
    def any() -> GRAMAR_RULE_TYPE:
        return lambda x: x

    @staticmethod
    def any_of(what: set) -> GRAMAR_RULE_TYPE:
        """For when values may exist but aren't required"""

        def wrapped(values: Any) -> set:
            nonlocal what
            res = set()
            if isinstance(values, set):
                res = values.intersection(what)
            else:
                LOG.warning(
                    "any_of: expected set, got %s: values=%s",
                    type(values),
                    limit_dict_depth(values, depth=1),
                )
            return res

        return wrapped

    @staticmethod
    def at_least_n_of(n: int, what: set) -> GRAMAR_RULE_TYPE:
        """For when at least n in a set of values may exist"""

        def wrapped(values: Any) -> set:
            nonlocal n, what
            res = set()
            if isinstance(values, set):
                common = values.intersection(what)
                if len(common) >= n:
                    res = common
                else:
                    nb_missing = n - len(common)
                    missing_candidates = what.difference(common)
                    LOG.warning(
                        "Missing %s among allowed items %s",
                        nb_missing,
                        missing_candidates,
                    )
            else:
                LOG.warning(
                    "at_least_n_of: expected set, got %s: values=%s",
                    type(values),
                    limit_dict_depth(values, depth=1),
                )
            return res

        if n > len(what):
            raise ValueError(f"n={n} larger than collection of allowed items {what}")
        return wrapped

    @staticmethod
    def at_least_1_of(what: set) -> GRAMAR_RULE_TYPE:
        """For when exactly n in a set of values may exist"""
        return Grammar.at_least_n_of(1, what)

    @staticmethod
    def n_of(n: int, what: set) -> GRAMAR_RULE_TYPE:
        """For when exactly n in a set of values may exist"""

        def wrapped(values: Any) -> set:
            nonlocal n, what
            res = set()
            if isinstance(values, set):
                common = values.intersection(what)
                if len(common) == n:
                    res = common
                else:
                    nb_missing = n - len(common)
                    missing_candidates = what.difference(common)
                    LOG.warning(
                        "Expected %s items among %s, got %s",
                        n,
                        what,
                        len(common),
                    )
            else:
                LOG.warning(
                    "n_of: expected set, got %s: values=%s",
                    type(values),
                    limit_dict_depth(values, depth=1),
                )
            return res

        return wrapped

    @staticmethod
    def one_of(what: set) -> GRAMAR_RULE_TYPE:
        """For when only 1 in a set of values may exist"""
        return Grammar.n_of(1, what)

    @staticmethod
    def all_of(what: set) -> GRAMAR_RULE_TYPE:
        """For when a set of values are required to exist"""
        return Grammar.n_of(len(what), what)

    @staticmethod
    def terminal_variable(
        var_type: Type | None = None, allowed_values: set | None = None
    ) -> GRAMAR_RULE_TYPE:
        """Terminal variables are not collections"""

        def wrapped(values: Any) -> set:
            nonlocal var_type
            return (
                {values}
                if not (is_a_collection(values) or isinstance(values, dict))
                and (var_type is None or isinstance(values, var_type))
                and (allowed_values is None or values in allowed_values)
                else set()
            )

        return wrapped

    @staticmethod
    def terminal_collection(
        var_type: Type,
        allowed_items: set | None = None,
        required_items: set | None = None,
    ) -> GRAMAR_RULE_TYPE:
        """Terminal collections can be iterated upon and are not simple variables"""

        def wrapped(values: Any) -> set:
            nonlocal var_type, allowed_items, required_items
            return (
                set(values)
                if is_a_collection(values)
                and all(isinstance(v, var_type) for v in values)
                and (allowed_items is None or all(v in allowed_items for v in values))
                and (required_items is None or all(r in values for r in required_items))
                else set()
            )

        return wrapped

    @staticmethod
    def nonterminal_collection(
        allowed_items: set | None = None,
        required_items: set | None = None,
    ) -> GRAMAR_RULE_TYPE:
        """Non-terminal collections are collections of dicts with a single key"""

        def wrapped(values: Any) -> set:
            nonlocal allowed_items, required_items
            if not is_a_collection(values):
                return set()
            all_keys = {next(iter(v)) for v in values}
            LOG.debug("nonterminal_collection: values=%s", limit_dict_depth(values, 1))
            return (
                {
                    next(iter(v))
                    for v in values
                    if len(v) == 1 and next(iter(v)) in allowed_items
                }
                if all(isinstance(v, dict) for v in values)
                and (
                    required_items is None or all(r in all_keys for r in required_items)
                )
                else set()
            )

        return wrapped


class DataStructureValidator:
    """Let a formal grammar describe the structure of a dict-based
    data structure, with production rules as key-value pairs.
    This class implements a validator that checks actual dict
    values against said grammar"""

    def __init__(self, grammar: Dict[str, GRAMAR_RULE_TYPE]) -> None:
        assert (
            Grammar.DICT_TREE_ROOT in grammar
        ), "Grammar without DICT_TREE_ROOT element"
        self.grammar = grammar
        self.grammar_key_by_pattern = (
            DataStructureValidator.make_grammar_key_pattern_map(grammar)
        )
        self.grammar_usage = set()
        LOG.info("Loaded grammar with %s rules", len(grammar))
        LOG.debug("grammar_key_by_pattern=%s", self.grammar_key_by_pattern)

    @staticmethod
    def make_grammar_key_pattern_map(grammar: dict) -> Dict[Pattern, Any]:
        """For each grammar key, build pattern for later path matching"""
        return {
            re.compile(
                r"^.*\.?" + _key.replace(".", r"\.").replace("*", r"[^\.]*") + r"$"
            ): _key
            for _key in grammar
        }

    def load_grammar_rule(self, path: str) -> GRAMAR_RULE_TYPE | None:
        """Loads grammar by matching path"""
        compatible_keys = [
            _key
            for _pattern, _key in self.grammar_key_by_pattern.items()
            if _pattern.match(path)
        ]
        key_match = None
        if len(compatible_keys) == 1:
            key_match = compatible_keys[0]
        elif len(compatible_keys) > 1:
            LOG.info("Multiple candidated for '%s': '%s'", path, compatible_keys)
            candidate_key_with_match_power = {
                k: sum(0.5 if x == "*" else (0 if x == "" else 1) for x in k.split("."))
                for k in compatible_keys
            }
            max_match_power = max(candidate_key_with_match_power.values())
            candidate_key_with_max_match_power = [
                k
                for k, v in candidate_key_with_match_power.items()
                if v == max_match_power
            ]
            if len(candidate_key_with_max_match_power) == 1:
                key_match = candidate_key_with_max_match_power[0]
                LOG.debug(
                    "Heuristics: selected %s as match to %s based on %s",
                    key_match,
                    path,
                    candidate_key_with_match_power,
                )
            elif max_match_power == 1:
                # Select the longest
                key_match = sorted(
                    candidate_key_with_max_match_power, key=len, reverse=True
                )[0]
            else:
                LOG.error(
                    "Could not determine match for %s with heuristics %s",
                    path,
                    candidate_key_with_match_power,
                )

        if key_match is None:
            LOG.warning("Failed to match '%s' to grammar rule", path)
            return None

        LOG.debug("Matched '%s' to grammar rule '%s'", path, key_match)
        self.grammar_usage.add(key_match)
        return self.grammar[key_match]

    def _validate(self, data: Any, path: str) -> Any:
        def warn_on_empty_collection(coll: dict | list) -> None:
            if not coll:
                LOG.warning(
                    "Grammar rule returned an empty collection for %s; see warning message above",
                    path,
                )

        res = None
        grammar_rule = self.load_grammar_rule(path)
        LOG.debug(
            "Called _validate with data=%s key=%s => grammar rule=%s",
            limit_dict_depth(data, depth=1),
            path,
            grammar_rule,
        )
        if grammar_rule is None:
            LOG.info(
                "Could not find rule at path %s; discarding %s",
                path,
                limit_dict_depth(data, depth=1),
            )
        elif isinstance(data, EXPECTED_TERMINAL_TYPES):
            valid_item = grammar_rule(data)
            if valid_item:
                res = data
        elif isinstance(data, dict):
            res = {
                valid_item: self._validate(
                    data[valid_item], path + "." + str(valid_item)
                )
                for valid_item in grammar_rule(set(data.keys()))
            }
            warn_on_empty_collection(res)
        elif isinstance(data, list):
            valid_items = grammar_rule(data)
            res = []
            for item in data:
                if isinstance(item, dict):
                    assert len(item) == 1
                    dict_only_key = next(iter(item))
                    if dict_only_key in valid_items:
                        res.append(
                            {
                                dict_only_key: self._validate(
                                    item[dict_only_key], path + f".{dict_only_key}"
                                )
                            }
                        )
                elif isinstance(item, EXPECTED_TERMINAL_TYPES):
                    if item in valid_items:
                        res.append(item)
                else:
                    LOG.warning(
                        "Could not deal with item %s of unexpected type %s",
                        item,
                        type(item),
                    )
            warn_on_empty_collection(res)
        else:
            LOG.error("Value %s of unexpected type %s", data, type(data))
        return res

    def validate(self, data: dict) -> dict:
        """Checks data structure against grammar and returns the valid
        subset of it. Logs grammar rule violations"""
        start_t = time()
        tmp = self._validate(data, path=Grammar.DICT_TREE_ROOT)
        unused_grammar_keys = set(self.grammar.keys()).difference(self.grammar_usage)
        if unused_grammar_keys:
            LOG.warning("Unused grammar keys: %s", unused_grammar_keys)
        LOG.debug("Data structure validation took %.0fms", 1000 * (time() - start_t))
        return tmp


def limit_dict_depth(d: dict | Any, depth: int) -> dict | Any:
    if not isinstance(d, dict):
        return d
    if depth <= 0:
        return "{...}"
    return {k: limit_dict_depth(v, depth - 1) for k, v in d.items()}
