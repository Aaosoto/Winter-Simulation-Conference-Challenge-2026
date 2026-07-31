from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from functools import partial


class ActionSet:
    """
    Encapsulates a set of actions.

    This class allows grouping multiple callable objects that share the same
    argument signature and have no return value.

    Supported callable types include:
    - General functions (e.g., func_name)
    - Methods (e.g., obj.method_name)
    - Lambda functions (e.g., lambda args: expr)
    - Functions with partial application (e.g., functools.partial(func_name, *args, **kwargs))
    - Other ActionSet objects

    All encapsulated actions can be invoked sequentially by calling the ActionSet
    instance or its `invoke` method.

    Examples
    --------
    >>> action_set = ActionSet(int, str)
    >>> action_set.add(lambda x, y: print(x, y))
    >>> action_set.add(lambda a, b: print(f"{a}: {b}"))
    >>> action_set(42, "hello")
    42 hello
    42: hello

    >>> action_set1 = ActionSet(int)
    >>> action_set1.add(lambda x: print(f"Action 1: {x}"))
    >>> handler = lambda x: print(f"Action 2: {x}")
    >>> action_set1 += handler   # in-place, like C# Action +=
    >>> action_set1(100)
    Action 1: 100
    Action 2: 100

    >>> action_set1 -= handler   # in-place removal, like C# Action -=
    >>> action_set1(200)
    Action 1: 200
    """

    check_option: bool = True
    """Whether to check if objects can be encapsulated into an ActionSet object."""

    def __init__(self, *args, **kwargs) -> None:
        """
        Instantiate an ActionSet with specified argument types.

        Parameters
        ----------
        *args : type
            Positional argument types.
        **kwargs : type
            Keyword argument types.

        Notes
        -----
        The encapsulated actions must be callable, match the specified argument
        signature, and have no return value.
        """
        self._args: tuple[type, ...] = args
        self._kwargs: dict[str, type] = kwargs
        self._argcount: int = len(args) + len(kwargs)
        self._actions: list[Callable[..., None]] = []

    def __iadd__(self, obj: ActionSet | Callable) -> ActionSet:
        """
        Add a callable or ActionSet in-place (C# ``Action +=`` semantics).

        Modifies this object directly and returns ``self``, so the variable
        still points to the same instance after ``action_set += handler``.

        Parameters
        ----------
        obj : ActionSet or Callable
            Callable or ActionSet to subscribe.

        Returns
        -------
        ActionSet
            ``self``, unchanged identity.

        Raises
        ------
        TypeError
            If ``obj`` is an ActionSet with an incompatible signature.
        """
        if isinstance(obj, ActionSet):
            if obj._args != self._args or obj._kwargs != self._kwargs:
                raise TypeError(
                    f"Cannot combine ActionSets with different signatures. "
                    f"Expected args={self._args}, kwargs={self._kwargs}, "
                    f"but got args={obj._args}, kwargs={obj._kwargs}"
                )
            self.add(obj.actions)
        else:
            self.add(obj)
        return self

    def __isub__(self, obj: ActionSet | Callable) -> ActionSet:
        """
        Remove a callable or ActionSet in-place (C# ``Action -=`` semantics).

        Parameters
        ----------
        obj : ActionSet or Callable
            Callable or ActionSet to unsubscribe.

        Returns
        -------
        ActionSet
            ``self``, unchanged identity.
        """
        if isinstance(obj, ActionSet):
            for action in obj.actions:
                self._actions[:] = [a for a in self._actions if a is not action]
        else:
            self._actions[:] = [a for a in self._actions if a is not obj]
        return self

    def __add__(self, obj: ActionSet | Callable) -> ActionSet:
        """
        Return a new ActionSet combining this object and the given object.

        Unlike ``+=``, this does **not** modify either operand.

        Parameters
        ----------
        obj : ActionSet or Callable
            Given ActionSet object or callable object.

        Returns
        -------
        ActionSet
            A new ActionSet object.

        Raises
        ------
        TypeError
            If the given object is an ActionSet object with different signature.
        """
        new_actionset = ActionSet(*self._args, **self._kwargs)
        new_actionset.add(self.actions, False)

        if isinstance(obj, ActionSet):
            if obj._args != self._args or obj._kwargs != self._kwargs:
                raise TypeError(
                    f"Cannot combine ActionSets with different signatures. "
                    f"Expected args={self._args}, kwargs={self._kwargs}, "
                    f"but got args={obj._args}, kwargs={obj._kwargs}"
                )
            new_actionset.add(obj.actions)
        else:
            new_actionset.add(obj)
        return new_actionset

    def __call__(self, *args, **kwargs) -> None:
        """
        Call all callable objects encapsulated in this object sequentially.

        Parameters
        ----------
        *args
            Arguments to pass to each action.
        **kwargs
            Keyword arguments to pass to each action.
        """
        for action in self._actions:
            action(*args, **kwargs)

    def __len__(self) -> int:
        """
        Number of callable objects encapsulated in this object.
        """
        count = 0
        for action in self._actions:
            count += len(action) if isinstance(action, ActionSet) else 1
        return count

    def __bool__(self) -> bool:
        """
        Check if this object contains any actions.
        True if at least one action exists, False otherwise.
        """
        return bool(self._actions)

    @property
    def actions(self) -> tuple[Callable[..., None], ...]:
        """
        All callable objects encapsulated in this object.
        """
        return tuple(self._actions)

    def invoke(self, *args, **kwargs) -> None:
        """
        Call all callable objects encapsulated in this object sequentially.

        This method is equivalent to calling the object directly.

        Parameters
        ----------
        *args
            Arguments to pass to each action.
        **kwargs
            Keyword arguments to pass to each action.
        """
        self(*args, **kwargs)

    def clear(self) -> None:
        """
        Clear all callable objects encapsulated in this object.
        """
        self._actions.clear()

    def add(
        self,
        action: ActionSet | Callable[..., None] | Iterable[Callable[..., None]],
        check: bool | None = None
    ) -> ActionSet:
        """
        Encapsulate a specified object within this object.

        The specified object can be:
        - an ActionSet object.
        - a callable object.
        - an iterable object containing callable objects.

        Parameters
        ----------
        action : ActionSet or Callable[..., None] or Iterable[Callable[..., None]]
            Specified object.
        check : bool or None, optional
            Whether to check if given objects can be encapsulated into this object.
            If None, defaults to ActionSet.check_option.

        Returns
        -------
        ActionSet
            This object itself for method chaining.
        """
        if check is None:
            check = ActionSet.check_option

        # Handle different input types
        if isinstance(action, dict):
            # Handle dictionary of callable objects
            objs = action.values()
            for obj in objs:
                self._add_object(obj, check)
        elif isinstance(action, (str, type)):
            # Skip strings and types
            pass
        elif hasattr(action, '__iter__'):
            # Handle iterables (list, tuple, set, generator, etc.)
            for obj in action:
                self._add_object(obj, check)
        else:
            # Handle single callable object
            self._add_object(action, check)

        return self

    def _add_object(self, obj: Callable, check: bool) -> None:
        """
        Internal method for encapsulating a specific callable object.

        Parameters
        ----------
        obj : Callable
            The callable object to be encapsulated.
        check : bool
            Whether to check if the given object is able to be encapsulated into this object.
        """
        # Avoid duplicates (use identity comparison for performance)
        if any(obj is action for action in self._actions):
            return

        if check:
            self._check_object(obj)

        self._actions.append(obj)

    def _check_object(self, obj: Callable[..., None]) -> None:
        """
        Check whether an object can be encapsulated into this object.

        A valid action is a callable object that matches the argument signature
        defined for this ActionSet object, and has no return value.

        Currently, this method only checks whether an object is callable and
        the number of its arguments.

        Parameters
        ----------
        obj : Callable[..., None]
            The object to be checked.

        Raises
        ------
        TypeError
            If the given object is not callable, or the number of its arguments
            does not match the expected number.
        """
        if not callable(obj):
            raise TypeError(f"Non-callable object: {obj}")

        # Check if the ActionSet has compatible signature
        if isinstance(obj, ActionSet):
            if self._args != obj._args or self._kwargs != obj._kwargs:
                raise TypeError(
                    f"Incompatible ActionSet signature. "
                    f"Expected args={self._args}, kwargs={self._kwargs}, "
                    f"but got args={obj._args}, kwargs={obj._kwargs}"
                )
            return

        # Validate signature for regular callables
        narg_offset = 0
        checked_obj = obj

        # Calculate effective argument count for partial functions
        if isinstance(obj, partial):
            narg_offset -= len(obj.args) + len(obj.keywords)
            checked_obj = obj.func

        # Skip validation for objects without names (e.g., some built-ins)
        if not hasattr(checked_obj, '__name__'):
            return

        # Get signature and validate argument count
        sig = None
        try:
            sig = inspect.signature(checked_obj)
        except (ValueError, TypeError):
            # Some built-in functions don't have signatures - skip validation
            sig = None

        if sig is None:
            return

        narg_min, narg_max = narg_offset, narg_offset

        for _, param in sig.parameters.items():
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                narg_max = float('inf')  # With *args, only check minimum
                continue
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                continue

            if param.default is param.empty:
                narg_min += 1
            narg_max += 1

        # Check if argument count is within valid range
        if self._argcount < narg_min or narg_max < self._argcount:
            func_name = getattr(obj, '__qualname__', obj.__name__)
            if narg_max == float('inf'):
                expected = f"at least {narg_min}"
            elif narg_min == narg_max:
                expected = f"{narg_min}"
            else:
                expected = f"{narg_min}~{narg_max}"
            raise TypeError(
                f"Argument count mismatch. Expected {self._argcount} arguments, "
                f"but {func_name} takes {expected}"
            )
