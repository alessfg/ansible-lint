import keyword
import sys
from typing import TYPE_CHECKING, Any, Dict, Generator, List, Optional, Tuple, Union

from ansiblelint.file_utils import Lintable
from ansiblelint.rules import AnsibleLintRule
from ansiblelint.utils import parse_yaml_from_file

if TYPE_CHECKING:
    from ansiblelint.constants import odict
    from ansiblelint.errors import MatchError


FAIL_PLAY = """
- hosts: localhost
  vars:
    true: false
"""


# properties/parameters are prefixed and postfixed with `__`
def is_property(k: str) -> bool:
    """Check if key is a property."""
    return k.startswith('__') and k.endswith('__')


def is_invalid_variable_name(ident: str) -> bool:
    """Check if variable name is using right pattern."""
    # Based on https://github.com/ansible/ansible/blob/devel/lib/ansible/utils/vars.py#L235
    if not isinstance(ident, str):
        return False

    try:
        ident.encode('ascii')
    except UnicodeEncodeError:
        return False

    if not ident.isidentifier():
        return False

    if keyword.iskeyword(ident):
        return False

    return True


class VariableNamingRule(AnsibleLintRule):
    id = 'var-naming'
    base_msg = 'All variables should be named using only lowercase and underscores'
    shortdesc = base_msg
    description = 'All variables should be named using only lowercase and underscores'
    severity = (
        'MEDIUM'  # ansible-lint displays severity when with --parseable-severity option
    )
    tags = ['formatting', 'readability', 'experimental']
    version_added = 'v5.0.8'

    def recursive_items(
        self, dictionary: Dict[str, Any]
    ) -> Generator[Tuple[str, Any], None, None]:
        """Return a recursive search for all keys in the dictionary."""
        for key, value in dictionary.items():
            # Avoid internal properties in the dictionary
            if not is_property(key):
                # Recurse if value is another ansible dictionary
                if isinstance(value, dict):
                    yield (key, value)
                    yield from self.recursive_items(value)
                else:
                    yield (key, value)

    def matchplay(
        self, file: "Lintable", data: "odict[str, Any]"
    ) -> List["MatchError"]:
        """Return matches found for a specific playbook."""
        results = []

        # If the Play uses the 'vars' section to set variables
        our_vars = data.get('vars', {})
        for key, value in self.recursive_items(our_vars):
            if is_invalid_variable_name(key):
                results.append(
                    self.create_matcherror(
                        filename=file,
                        linenumber=our_vars['__line__'],
                        message="Play defines variable '"
                        + key
                        + "' within 'vars' section that violates variable naming standards",
                    )
                )

        return results

    def matchtask(
        self, task: Dict[str, Any], file: Optional[Lintable] = None
    ) -> Union[bool, str]:
        """Return matches for task based variables."""
        # If the task uses the 'vars' section to set variables
        our_vars = task.get('vars', {})
        for key, value in self.recursive_items(our_vars):
            if is_invalid_variable_name(key):
                return "Task defines variables within 'vars' section that violates variable naming standards"

        # If the task uses the 'set_fact' module
        ansible_module = task['action']['__ansible_module__']
        ansible_action = task['action']
        if ansible_module == 'set_fact':
            for key, value in self.recursive_items(ansible_action):
                if is_invalid_variable_name(key):
                    return "Task uses 'set_fact' to define variables that violates variable naming standards"

        # If the task registers a variable
        registered_var = task.get('register', None)
        if registered_var and is_invalid_variable_name(registered_var):
            return "Task registers a variable that violates variable naming standards"

        return False

    def matchyaml(self, file: Lintable) -> List["MatchError"]:
        """Return matches for variables defined in vars files."""
        results: List["MatchError"] = []
        meta_data: Dict[str, Any] = {}

        if file.kind == "vars":
            meta_data = parse_yaml_from_file(str(file.path))
            for key, value in self.recursive_items(meta_data):
                if is_invalid_variable_name(key):
                    results.append(
                        self.create_matcherror(
                            filename=file,
                            # linenumber=vars['__line__'],
                            message="File defines variable '"
                            + key
                            + "' that violates variable naming standards",
                        )
                    )
        else:
            results.extend(super().matchyaml(file))
        return results


# testing code to be loaded only with pytest or when executed the rule file
if "pytest" in sys.modules:

    import pytest

    @pytest.mark.parametrize(
        'rule_runner', (VariableNamingRule,), indirect=['rule_runner']
    )
    def test_invalid_var_name_playbook(rule_runner: Any) -> None:
        """Test rule matches."""
        results = rule_runner.run_playbook(FAIL_PLAY)
        assert len(results) == 1
        for result in results:
            assert result.message == VariableNamingRule.shortdesc
