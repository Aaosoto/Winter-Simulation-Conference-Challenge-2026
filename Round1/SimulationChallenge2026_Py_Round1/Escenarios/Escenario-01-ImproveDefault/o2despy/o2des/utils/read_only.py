"""
This module provides utilities to convert mutable objects into their immutable
read-only counterparts.

Classes:
    ReadOnlyList: An immutable list wrapper that prevents modifications.
    ReadOnlyDict: An immutable dictionary wrapper that prevents modifications.

Functions:
    as_read_only: Convert any supported object to its read-only version.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol, TypeVar, overload

__all__ = [
    'as_read_only',
    'ReadOnlyList',
    'ReadOnlyDict',
]

# =============================================================================
# Type Variables and Protocols
# =============================================================================

T = TypeVar('T')


class SupportsReadOnly(Protocol):
    """
    Protocol for objects that support conversion to read-only.
    """

    def as_read_only(self) -> Any:
        """
        Return a read-only version of this object.
        """
        ...


# =============================================================================
# Internal Helper Functions
# =============================================================================

def _try_convert_to_readonly(obj: T) -> T | ReadOnlyDict | ReadOnlyList | Any:
    """
    Internal helper to convert an object to its read-only equivalent.

    This function handles the conversion logic shared by as_read_only(),
    ReadOnlyList, and ReadOnlyDict. It recursively converts nested mutable
    collections while preserving immutable objects unchanged.

    Parameters
    ----------
    obj : T
        The object to convert.

    Returns
    -------
    T | ReadOnlyDict | ReadOnlyList | Any
        The read-only version of the object. Can be:
        - ReadOnlyDict if obj is a Mapping
        - ReadOnlyList if obj is a list, set, or tuple
        - The result of obj.as_read_only() if obj has that method
        - The original object if conversion is not needed

    Notes
    -----
    - Mapping objects are converted to ReadOnlyDict
    - Lists, sets, and tuples are converted to ReadOnlyList
    - Objects with `as_read_only` method are converted via that method
    - Primitive types and other immutable objects are returned unchanged
    """
    if isinstance(obj, Mapping):
        return ReadOnlyDict(obj)
    if isinstance(obj, list | set | tuple):
        return ReadOnlyList(obj)
    if hasattr(obj, "as_read_only"):
        return obj.as_read_only()  # Return type depends on implementation
    return obj


# =============================================================================
# Public API Functions
# =============================================================================

@overload
def as_read_only(obj: Mapping[Any, Any]) -> ReadOnlyDict: ...


@overload
def as_read_only(obj: list[Any] | set[Any] | tuple[Any, ...]) -> ReadOnlyList: ...


@overload
def as_read_only(obj: SupportsReadOnly) -> Any: ...


def as_read_only(obj: Any) -> ReadOnlyDict | ReadOnlyList | Any:
    """
    Convert an object to its read-only equivalent.

    This function provides a unified interface for converting mutable collections
    and objects into their immutable read-only counterparts. Nested mutable
    collections are recursively converted to ensure deep immutability.

    Supported types include:
    - Dictionaries and other Mapping objects → ReadOnlyDict
    - Lists, sets, and tuples → ReadOnlyList
    - Objects implementing the `as_read_only` method
    - Primitive types (int, str, float, bool, None) are returned unchanged

    Parameters
    ----------
    obj : Any
        The object to convert to read-only.

    Returns
    -------
    ReadOnlyDict | ReadOnlyList | Any
        The read-only version of the input object. If the object is already
        immutable or doesn't require conversion, it may be returned unchanged.

    Raises
    ------
    TypeError
        If the object type is not supported for conversion to read-only.

    Examples
    --------
    >>> data = {'a': [1, 2, 3], 'b': {'c': 4}}
    >>> ro_data = as_read_only(data)
    >>> ro_data['a'][0] = 10  # Raises RuntimeError

    >>> as_read_only(42)  # Raises TypeError (primitives don't need conversion)
    TypeError: Cannot convert object of type int to read-only...

    >>> nested = {'outer': {'inner': [1, 2, 3]}}
    >>> ro_nested = as_read_only(nested)
    >>> ro_nested['outer']['inner'].append(4)  # Raises RuntimeError
    """
    result = _try_convert_to_readonly(obj)
    if result is obj:
        raise TypeError(
            f"Cannot convert object of type {type(obj).__name__} to read-only. "
            "Supported types: Mapping, list, set, tuple, or objects with "
            "'as_read_only' method."
        )
    return result


# =============================================================================
# ReadOnlyList Class
# =============================================================================

class ReadOnlyList(list[Any]):
    """
    An immutable list wrapper that prevents all modification operations.

    This class inherits from list but overrides all mutating methods to raise
    RuntimeError, ensuring the list cannot be modified after creation. Nested
    mutable objects (dicts, lists, sets) are recursively converted to their
    read-only counterparts during initialization.

    All read operations (indexing, iteration, slicing, etc.) work normally.
    Operations that would create new lists (__add__, __mul__) are allowed as
    they don't modify the original object.

    Parameters
    ----------
    data : Iterable[Any] | None, optional
        The iterable to convert. Nested mutable collections are recursively
        converted to read-only versions. If None, creates an empty read-only list.

    Raises
    ------
    RuntimeError
        When any modification operation is attempted.

    Examples
    --------
    >>> data = [1, 2, {'key': 'value'}]
    >>> ro_list = ReadOnlyList(data)
    >>> ro_list[0]  # Reading is allowed
    1
    >>> ro_list[0] = 10  # Raises RuntimeError
    >>> ro_list.append(3)  # Raises RuntimeError
    >>> new_list = ro_list + [3, 4]  # Creates new list (allowed)

    Notes
    -----
    - This class provides shallow immutability at the list level
    - Nested collections are automatically converted to read-only versions
    - The underlying data is stored in the parent list class for efficiency
    """

    def __init__(self, data: Iterable[Any] | None = None) -> None:
        """
        Initialize a read-only list from the given iterable.

        Parameters
        ----------
        data : Iterable[Any] | None, optional
            The iterable to convert. Nested mutable collections are recursively
            converted to read-only versions. If None, creates an empty list.
        """
        converted_data: list[Any] = []
        if data is not None:
            converted_data = [_try_convert_to_readonly(item) for item in data]

        super().__init__(converted_data)

    def _raise_readonly_error(self, *args: Any, **kwargs: Any) -> None:
        """
        Raise an error indicating the object is read-only.

        This method is assigned to all mutating operations to prevent
        modifications to the read-only list.

        Parameters
        ----------
        *args : Any
            Unused positional arguments (required for method signature compatibility).
        **kwargs : Any
            Unused keyword arguments (required for method signature compatibility).

        Raises
        ------
        RuntimeError
            Always raised to prevent any modification to the read-only list.
        """
        raise RuntimeError("Cannot modify read-only list")

    # Override all mutating methods to prevent modifications
    # Note: Non-mutating operations like __add__, __mul__, __reversed__ are
    # intentionally not overridden as they return new objects without modifying self
    __setitem__ = _raise_readonly_error  # type: ignore[assignment]
    __delitem__ = _raise_readonly_error  # type: ignore[assignment]
    __iadd__ = _raise_readonly_error  # type: ignore[assignment]
    __imul__ = _raise_readonly_error  # type: ignore[assignment]
    append = _raise_readonly_error  # type: ignore[assignment]
    insert = _raise_readonly_error  # type: ignore[assignment]
    extend = _raise_readonly_error  # type: ignore[assignment]
    pop = _raise_readonly_error  # type: ignore[assignment]
    remove = _raise_readonly_error  # type: ignore[assignment]
    clear = _raise_readonly_error  # type: ignore[assignment]
    reverse = _raise_readonly_error  # type: ignore[assignment]
    sort = _raise_readonly_error  # type: ignore[method-assign]


# =============================================================================
# ReadOnlyDict Class
# =============================================================================

class ReadOnlyDict(dict[Any, Any]):
    """
    An immutable dictionary wrapper that prevents all modification operations.

    This class inherits from dict but overrides all mutating methods to raise
    RuntimeError, ensuring the dictionary cannot be modified after creation.
    Nested mutable objects (dicts, lists, sets) are recursively converted to
    their read-only counterparts during initialization.

    All read operations (key access, iteration, views, etc.) work normally.

    Parameters
    ----------
    data : Mapping[Any, Any] | None, optional
        The mapping to convert. Nested mutable collections are recursively
        converted to read-only versions. If None, creates an empty read-only dict.

    Raises
    ------
    RuntimeError
        When any modification operation is attempted.

    Examples
    --------
    >>> data = {'a': 1, 'b': [2, 3]}
    >>> ro_dict = ReadOnlyDict(data)
    >>> ro_dict['a']  # Reading is allowed
    1
    >>> ro_dict['a'] = 10  # Raises RuntimeError
    >>> ro_dict.update({'c': 3})  # Raises RuntimeError
    >>> ro_dict.get('a', default=0)  # Non-mutating methods work
    1

    Notes
    -----
    - This class provides shallow immutability at the dict level
    - Nested collections are automatically converted to read-only versions
    - The underlying data is stored in the parent dict class for efficiency
    - Dictionary views (keys(), values(), items()) remain functional
    """

    def __init__(self, data: Mapping[Any, Any] | None = None) -> None:
        """
        Initialize a read-only dictionary from the given mapping.

        Parameters
        ----------
        data : Mapping[Any, Any] | None, optional
            The mapping to convert. Nested mutable collections are recursively
            converted to read-only versions. If None, creates an empty dict.
        """
        converted_data: dict[Any, Any] = {}
        if data is not None:
            converted_data = {
                key: _try_convert_to_readonly(value)
                for key, value in data.items()
            }

        super().__init__(converted_data)

    def _raise_readonly_error(self, *args: Any, **kwargs: Any) -> None:
        """
        Raise an error indicating the object is read-only.

        This method is assigned to all mutating operations to prevent
        modifications to the read-only dictionary.

        Parameters
        ----------
        *args : Any
            Unused positional arguments (required for method signature compatibility).
        **kwargs : Any
            Unused keyword arguments (required for method signature compatibility).

        Raises
        ------
        RuntimeError
            Always raised to prevent any modification to the read-only dictionary.
        """
        raise RuntimeError("Cannot modify read-only dictionary")

    # Override all mutating methods to prevent modifications
    __setitem__ = _raise_readonly_error  # type: ignore[assignment]
    __delitem__ = _raise_readonly_error  # type: ignore[assignment]
    setdefault = _raise_readonly_error  # type: ignore[assignment]
    pop = _raise_readonly_error  # type: ignore[assignment]
    popitem = _raise_readonly_error  # type: ignore[assignment]
    update = _raise_readonly_error  # type: ignore[assignment]
    clear = _raise_readonly_error  # type: ignore[assignment]
