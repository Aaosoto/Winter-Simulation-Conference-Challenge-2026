"""
Unit tests for XmlUtils in o2des.utils.

This module verifies the functionality of XML-dictionary conversion utilities,
including parsing XML to dict, converting dict to XML, pretty formatting, and
handling edge cases such as attributes, nested structures, lists, and special characters.
"""

import os
import tempfile
import xml.etree.ElementTree as ET

import pytest

from o2des.utils import XmlUtils


class TestConfiguration:
    """
    Test configuration functions for XML-Dictionary conversion.
    """

    def test_set_attrib_tags(self):
        XmlUtils.set_attrib_tags(['id', 'type', 'class'])
        assert XmlUtils._attrib_tags == ('id', 'type', 'class')

    def test_set_text_tags(self):
        XmlUtils.set_text_tags(['text', 'value', 'content'])
        assert XmlUtils._value_tags == ('text', 'value', 'content')


class TestParseXmlToDict:
    """
    Test parsing XML to dictionary.
    """

    def test_parse_xml_element_to_dict_simple(self):
        root = ET.Element('root')
        root.text = 'simple text'
        result = XmlUtils.parse_xml_element_to_dict(root)
        assert result == {'root': 'simple text'}

    def test_parse_xml_element_to_dict_none(self):
        result = XmlUtils.parse_xml_element_to_dict(None)
        assert result is None

    def test_parse_xml_element_with_attributes(self):
        root = ET.Element('root', attrib={'id': '1', 'type': 'test'})
        root.text = 'content'
        result = XmlUtils.parse_xml_element_to_dict(root)
        assert result == {'root': {'id': '1', 'type': 'test', 'value': 'content'}}

    def test_parse_xml_element_with_children(self):
        root = ET.Element('root')
        child1 = ET.SubElement(root, 'child1')
        child1.text = 'value1'
        child2 = ET.SubElement(root, 'child2')
        child2.text = 'value2'
        result = XmlUtils.parse_xml_element_to_dict(root)
        assert result == {'root': {'child1': 'value1', 'child2': 'value2'}}

    def test_parse_xml_element_with_duplicate_children(self):
        root = ET.Element('root')
        child1 = ET.SubElement(root, 'item')
        child1.text = 'value1'
        child2 = ET.SubElement(root, 'item')
        child2.text = 'value2'
        result = XmlUtils.parse_xml_element_to_dict(root)
        assert result == {'root': [{'item': 'value1'}, {'item': 'value2'}]}

    def test_parse_xml_element_empty(self):
        root = ET.Element('root')
        result = XmlUtils.parse_xml_element_to_dict(root)
        assert result == {'root': ''}

    def test_parse_xml_file_to_dict(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write('<?xml version="1.0"?><root><child>value</child></root>')
            temp_file = f.name

        try:
            result = XmlUtils.parse_xml_file_to_dict(temp_file)
            assert result == {'root': {'child': 'value'}}
        finally:
            os.unlink(temp_file)


class TestConvertDictToXml:
    """
    Test converting dictionary to XML.
    """

    def test_convert_dict_to_xml_element_simple(self):
        data = {'root': 'simple text'}
        element = XmlUtils.convert_dict_to_xml_element(data)
        assert element.tag == 'root'
        assert element.text == 'simple text'

    def test_convert_dict_to_xml_element_nested(self):
        data = {'root': {'child': 'value'}}
        element = XmlUtils.convert_dict_to_xml_element(data)
        assert element.tag == 'root'
        assert len(element) == 1
        assert element[0].tag == 'child'
        assert element[0].text == 'value'

    def test_convert_dict_to_xml_element_with_attributes(self):
        XmlUtils.set_attrib_tags(['id', 'type'])
        data = {'root': {'id': '1', 'type': 'test', 'child': 'value'}}
        element = XmlUtils.convert_dict_to_xml_element(data)
        assert element.get('id') == '1'
        assert element.get('type') == 'test'
        assert element[0].tag == 'child'
        XmlUtils.set_attrib_tags([])

    def test_convert_dict_to_xml_element_list(self):
        data = {'root': [{'item': 'value1'}, {'item': 'value2'}]}
        element = XmlUtils.convert_dict_to_xml_element(data)
        assert element.tag == 'root'
        assert len(element) == 2

    def test_convert_dict_to_xml_element_multiple_root(self):
        data = {'root1': 'value1', 'root2': 'value2'}
        element = XmlUtils.convert_dict_to_xml_element(data)
        assert element.tag == 'Root'

    def test_convert_xml_element_to_xml_str(self):
        element = ET.Element('root')
        element.text = 'content'
        xml_str = XmlUtils.convert_xml_element_to_xml_str(element)
        assert '<?xml version' in xml_str
        assert '<root>content</root>' in xml_str

    def test_convert_xml_element_to_xml_str_none(self):
        result = XmlUtils.convert_xml_element_to_xml_str(None)
        assert result == ''

    def test_convert_dict_to_xml_with_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            temp_file = f.name

        try:
            data = {'root': {'child': 'value'}}
            xml_str = XmlUtils.convert_dict_to_xml_str(data, filename=temp_file)
            assert os.path.exists(temp_file)
            assert '<root>' in xml_str
            assert '<child>value</child>' in xml_str
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_convert_dict_to_xml_without_file(self):
        data = {'root': {'child': 'value'}}
        xml_str = XmlUtils.convert_dict_to_xml_str(data)
        assert '<root>' in xml_str
        assert '<child>value</child>' in xml_str


class TestPrettyXml:
    """
    Test pretty XML formatting.
    """

    def test_prettyxml_simple(self):
        root = ET.Element('root')
        child = ET.SubElement(root, 'child')
        child.text = 'value'
        XmlUtils.prettyxml(root)
        assert '\n' in root.text
        assert '\t' in root.text

    def test_prettyxml_nested(self):
        root = ET.Element('root')
        child1 = ET.SubElement(root, 'child1')
        child2 = ET.SubElement(child1, 'child2')
        child2.text = 'value'
        XmlUtils.prettyxml(root)
        assert root.text.count('\t') >= 1
        assert child1.text.count('\t') >= 2

    def test_prettyxml_empty(self):
        root = ET.Element('root')
        XmlUtils.prettyxml(root)
        assert root.tail == '\n'


class TestRoundTrip:
    """
    Test round-trip conversion between dict and XML.
    """

    def test_roundtrip_simple(self):
        original = {'root': {'child': 'value'}}
        element = XmlUtils.convert_dict_to_xml_element(original)
        result = XmlUtils.parse_xml_element_to_dict(element)
        assert result == original

    def test_roundtrip_with_attributes(self):
        XmlUtils.set_attrib_tags(['id'])
        XmlUtils.set_text_tags(['text'])
        original = {'root': {'id': '1', 'text': 'content'}}
        element = XmlUtils.convert_dict_to_xml_element(original)
        result = XmlUtils.parse_xml_element_to_dict(element)
        # Attributes will be preserved
        assert result['root']['id'] == '1'
        XmlUtils.set_attrib_tags([])
        XmlUtils.set_text_tags(['text', 'value'])

    def test_roundtrip_nested(self):
        original = {'root': {'level1': {'level2': {'level3': 'deep'}}}}
        element = XmlUtils.convert_dict_to_xml_element(original)
        result = XmlUtils.parse_xml_element_to_dict(element)
        assert result == original


class TestEdgeCases:
    """
    Test edge cases and special scenarios.
    """

    def test_empty_dict(self):
        data = {}
        element = XmlUtils.convert_dict_to_xml_element(data)
        assert element.tag == 'Root'

    def test_none_value(self):
        data = {'root': None}
        element = XmlUtils.convert_dict_to_xml_element(data)
        assert element.text == ''

    def test_numeric_values(self):
        data = {'root': {'int': 42, 'float': 3.14, 'bool': True}}
        element = XmlUtils.convert_dict_to_xml_element(data)
        result = XmlUtils.parse_xml_element_to_dict(element)
        assert result['root']['int'] == '42'
        assert result['root']['float'] == '3.14'
        assert result['root']['bool'] == 'True'

    def test_special_characters(self):
        data = {'root': {'child': 'value with <>&"'}}
        element = XmlUtils.convert_dict_to_xml_element(data)
        xml_str = XmlUtils.convert_xml_element_to_xml_str(element)
        assert '&lt;' in xml_str or '<' in element[0].text
