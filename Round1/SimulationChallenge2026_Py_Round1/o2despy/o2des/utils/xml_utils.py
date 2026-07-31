"""
This module provides utilities for converting XML information between various formats:
- XML file <-> XML string <-> XML element <-> dictionary
- XML file -> XML element

The module supports bidirectional conversion and customizable attribute/text tag handling.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Sequence
from typing import Any
from xml.dom import minidom

from o2des.config import FileIoConfig
from o2des.utils import FileIoUtils

__all__ = [
    'set_attrib_tags',
    'set_text_tags',
    'parse_xml_file_to_dict',
    'parse_xml_element_to_dict',
    'convert_dict_to_xml_str',
    'convert_dict_to_xml_element',
    'convert_xml_element_to_xml_str',
    'prettyxml',
]


# =============================================================================
# Configuration for XML-Dictionary Conversion
# =============================================================================

_attrib_tags: tuple[str, ...] = ()
_value_tags: tuple[str, ...] = ("text", "value")


def set_attrib_tags(attrib_tags: Sequence[str]) -> None:
    """
    Configure which dictionary keys should be treated as XML attributes.

    Parameters
    ----------
    attrib_tags : Sequence[str]
        Tags to be treated as attributes of XML elements.

    Examples
    --------
    >>> set_attrib_tags(['id', 'type', 'class'])
    """
    global _attrib_tags
    _attrib_tags = tuple(attrib_tags)


def set_text_tags(text_tags: Sequence[str]) -> None:
    """
    Configure which dictionary keys should be treated as element text content.

    Parameters
    ----------
    text_tags : Sequence[str]
        Tags to be treated as the text content of XML elements.

    Examples
    --------
    >>> set_text_tags(['text', 'value', 'content'])
    """
    global _value_tags
    _value_tags = tuple(text_tags)


# =============================================================================
# XML file => XML element => Dictionary
# =============================================================================

def parse_xml_file_to_dict(
    filename: str,
    encoding: str = "",
) -> dict[str, Any]:
    """
    Parse an XML file into a dictionary structure.

    Parameters
    ----------
    filename : str
        Path to the XML file to parse.
    encoding : str, optional
        Character encoding for the file. Defaults to the default encoding if empty.

    Returns
    -------
    dict[str, Any]
        Dictionary containing the parsed XML structure with the root tag as key.

    Raises
    ------
    FileNotFoundError
        If the specified file does not exist.
    ET.ParseError
        If the XML file is malformed.
    """
    encoding = encoding or FileIoConfig.TEXT_ENCODING
    xml_element_tree = ET.parse(
        source=filename,
        parser=ET.XMLParser(encoding=encoding),
    )
    root = xml_element_tree.getroot()
    return parse_xml_element_to_dict(root)


def parse_xml_element_to_dict(root: ET.Element | None) -> dict[str, Any] | None:
    """
    Parse an XML element into a dictionary structure.

    Parameters
    ----------
    root : ET.Element | None
        Root XML element to parse.

    Returns
    -------
    dict[str, Any] | None
        Dictionary containing the parsed element structure with the root tag as key,
        or None if root is None.

    Notes
    -----
    The returned dictionary uses the element's tag as the key and the parsed
    content as the value. Nested elements are recursively parsed.
    """
    if root is None:
        return None
    return {root.tag: _parse_xml_element(root)}


def _parse_xml_element(
    element: ET.Element,
) -> str | dict[str, Any] | list[dict[str, Any]]:
    """
    Parse an XML element into a string, dictionary, or list of dictionaries.

    This internal function handles the recursive parsing of XML elements,
    preserving attributes, child elements, and text content. The output format
    depends on the element's structure:
    - Pure text content: returns as string
    - Unique keys (attributes + children): returns as dictionary
    - Duplicate keys: returns as list of single-item dictionaries

    Parameters
    ----------
    element : ET.Element
        XML element to parse.

    Returns
    -------
    str | dict[str, Any] | list[dict[str, Any]]
        Parsed content in the most appropriate format:
        - str: if element contains only text
        - dict: if all keys (attributes and child tags) are unique
        - list[dict]: if duplicate keys exist
    """
    results: list[tuple[str, Any]] = []

    # Parse attributes
    results.extend(element.attrib.items())

    # Parse child elements recursively
    for child in element:
        child_results = _parse_xml_element(child)
        if child_results:
            results.append((child.tag, child_results))

    # Parse text content
    text = element.text.strip() if element.text else ""
    if text:
        if results:
            # Element has attributes or children, store text under 'value' key
            results.append(("value", text))
        else:
            # Element contains only text
            return text

    # Return empty string if no content found
    if not results:
        return ""

    # Determine output format based on key uniqueness
    key_set = {key for key, _ in results}
    if len(results) == len(key_set):
        # All keys are unique, return as dictionary
        return dict(results)
    else:
        # Duplicate keys exist, return as list of single-item dictionaries
        return [{key: value} for key, value in results]


# =============================================================================
# XML file <= XML string <= XML element <= Dictionary
# =============================================================================

def convert_dict_to_xml_str(
    data: dict[str, Any],
    filename: str | None = None,
    encoding: str = "",
) -> str:
    """
    Convert a dictionary to an XML string, optionally saving to a file.

    Parameters
    ----------
    data : dict[str, Any]
        Dictionary containing the data to convert. Keys represent element tags,
        and values can be scalars, dicts, or lists.
    filename : str | None, optional
        Path to save the XML file. If None, no file is created.
    encoding : str, optional
        Character encoding for the output. Uses default encoding if empty.

    Returns
    -------
    str
        Pretty-printed XML string representation of the data with 4-space indentation.

    Raises
    ------
    OSError
        If filename is provided but the file cannot be written.

    Examples
    --------
    >>> data = {'root': {'child': 'value', 'attr': '123'}}
    >>> xml_str = convert_dict_to_xml_str(data)
    """
    root = convert_dict_to_xml_element(data)
    xmlstr = convert_xml_element_to_xml_str(root, encoding)

    if filename:
        encoding = encoding or FileIoConfig.TEXT_ENCODING
        with FileIoUtils.fopen(filename, mode="w", encoding=encoding) as file:
            file.write(xmlstr)

    return xmlstr


def convert_xml_element_to_xml_str(
    element: ET.Element | None,
    encoding: str = "",
) -> str:
    """
    Convert an XML element to a pretty-printed XML string.

    Parameters
    ----------
    element : ET.Element | None
        XML element to convert.
    encoding : str, optional
        Character encoding for the output. Uses default encoding if empty.

    Returns
    -------
    str
        Pretty-printed XML string with 4-space indentation and XML declaration,
        or empty string if element is None.

    Notes
    -----
    The output includes an XML declaration and uses minidom for pretty printing.
    Tabs are expanded to 4 spaces for consistent indentation.
    """
    if element is None:
        return ""

    encoding = encoding or FileIoConfig.TEXT_ENCODING
    xmlstr = ET.tostring(element, encoding=encoding)
    dom = minidom.parseString(xmlstr)
    pretty_xml = dom.toprettyxml(encoding=encoding)
    return pretty_xml.decode(encoding).expandtabs(4)


def convert_dict_to_xml_element(data: dict[str, Any]) -> ET.Element:
    """
    Convert a dictionary to an XML element structure.

    Parameters
    ----------
    data : dict[str, Any]
        Dictionary to convert. Should contain exactly one root key-value pair.
        If multiple keys exist or data is not a dict, they will be wrapped 
        in a 'Root' element.

    Returns
    -------
    ET.Element
        Root XML element containing the converted structure.

    Notes
    -----
    Dictionary keys become element tags. Use set_attrib_tags() and set_text_tags()
    to control which keys are treated as attributes or text content.

    Examples
    --------
    >>> data = {'person': {'name': 'John', 'age': 30}}
    >>> element = convert_dict_to_xml_element(data)
    """
    if isinstance(data, dict) and len(data) == 1:
        root_tag, root_data = next(iter(data.items()))
    else:
        root_tag, root_data = "Root", data

    return _create_xml_element(root_tag, root_data)


def _create_xml_element(tag: str, data: Any) -> ET.Element:
    """
    Create an XML element with the given tag and data.

    This internal function recursively creates child elements based on the
    data structure, handling dictionaries, lists, and scalar values. It respects
    the global _attrib_tags and _value_tags settings for special key handling.

    Parameters
    ----------
    tag : str
        Tag name for the XML element.
    data : Any
        Data to populate the element with. Can be:
        - Scalar: becomes text content
        - dict: keys become child elements or attributes
        - list: each item is processed recursively

    Returns
    -------
    ET.Element
        Created XML element with populated children, attributes, and text.
    """
    element = ET.Element(tag)

    # Handle scalar types (str, int, float, bool, None)
    if not isinstance(data, dict | list):
        element.text = str(data) if data is not None else ""
        return element

    # Normalize data to list of dictionaries
    data_list: list[Any] = [data] if isinstance(data, dict) else data

    # Process each item in the list
    for data_item in data_list:
        if not isinstance(data_item, dict):
            element.text = str(data_item)
            continue

        value_tag_data: dict[str, Any] = {}

        # Separate attributes, value tags, and child elements
        for child_tag, child_data in data_item.items():
            if child_tag in _attrib_tags:
                # Add as element attribute
                element.set(child_tag, str(child_data))
            elif child_tag in _value_tags:
                # Store for later processing as text or child element
                value_tag_data[child_tag] = child_data
            else:
                # Create as child element
                child = _create_xml_element(child_tag, child_data)
                element.append(child)

        # Handle value tags based on element structure
        if len(element) == 0:
            # No child elements exist, set first value tag as element text
            for child_data in value_tag_data.values():
                element.text = str(child_data)
                break  # Only use first value tag
        else:
            # Child elements exist, create separate elements for value tags
            for child_tag, child_data in value_tag_data.items():
                child = _create_xml_element(child_tag, child_data)
                element.append(child)

    return element


# =============================================================================
# XML Formatting Utilities
# =============================================================================

def prettyxml(element: ET.Element) -> None:
    """
    Format an XML element with proper indentation in-place.

    This function modifies the element's text and tail attributes to add
    newlines and tabs for human-readable formatting. The element is modified
    directly without creating a copy.

    Parameters
    ----------
    element : ET.Element
        XML element to format. Will be modified in-place.

    Notes
    -----
    This function uses tab characters for indentation. For file output,
    consider using convert_xml_element_to_xml_str() which uses spaces.

    Examples
    --------
    >>> root = ET.Element('root')
    >>> child = ET.SubElement(root, 'child')
    >>> prettyxml(root)
    """
    def _indent(elem: ET.Element, level: int) -> None:
        """
        Recursively add indentation to element and its children.

        Parameters
        ----------
        elem : ET.Element
            Element to indent.
        level : int
            Current indentation level (number of tabs).
        """
        indent_str = "\t" * level
        # Set tail for proper closing tag placement
        elem.tail = f"\n{indent_str}"

        # Leaf element, no children to process
        if len(elem) == 0:
            return

        # Format text content if present
        next_indent = "\t" * (level + 1)
        text = elem.text.strip() if elem.text else ""
        if text:
            elem.text = f"\n{next_indent}{text}"
        else:
            elem.text = f"\n{next_indent}"

        # Recursively indent children
        for child in elem:
            _indent(child, level + 1)

        # Adjust last child's tail to align closing tag with opening tag
        if len(elem) > 0:
            elem[-1].tail = f"\n{indent_str}"

    _indent(element, 0)
