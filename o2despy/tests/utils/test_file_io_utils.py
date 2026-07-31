"""
Unit tests for FileIoUtils module in o2des.utils.

This test suite covers:
- Basic file operations (fopen)
- JSON reading with JSON5 support
- JSON writing with various options
- Error handling and edge cases
- Integration scenarios for file operations
"""

import json
from pathlib import Path
from typing import Any

import pytest

from o2des.utils import FileIoUtils


@pytest.fixture
def sample_json_data() -> dict[str, Any]:
    """
    Fixture providing sample JSON data for tests.
    """
    return {
        "name": "Alice",
        "age": 30,
        "active": True,
        "tags": ["python", "testing"],
        "metadata": {"created": "2024-01-01", "updated": "2024-01-02"}
    }


class TestFopen:
    """
    Test cases for fopen function.
    """

    @pytest.mark.parametrize("mode,content,expected", [
        ('r', "Hello World", "Hello World"),
        ('r+', "Original", "Original"),
    ])
    def test_fopen_read_modes(
        self,
        tmp_path: Path,
        mode: str,
        content: str,
        expected: str,
    ) -> None:
        """
        Test various read modes.
        """
        test_file: Path = tmp_path / "test.txt"
        test_file.write_text(content, encoding="utf-8")

        with FileIoUtils.fopen(test_file, mode=mode) as f:
            result: str = f.read()

        assert expected in result

    @pytest.mark.parametrize("mode", ['w', 'x', 'a'])
    def test_fopen_write_modes(self, tmp_path: Path, mode: str) -> None:
        """
        Test various write modes.
        """
        test_file: Path = tmp_path / f"{mode}_test.txt"
        if mode == 'a':  # Pre-create file for append mode
            test_file.write_text("", encoding="utf-8")

        content: str = "Test Content"
        with FileIoUtils.fopen(test_file, mode=mode) as f:
            f.write(content)

        assert test_file.exists()
        assert content in test_file.read_text(encoding="utf-8")

    def test_fopen_append_preserves_content(self, tmp_path: Path) -> None:
        """
        Test that append mode preserves existing content.
        """
        test_file: Path = tmp_path / "append.txt"
        test_file.write_text("Line 1\n", encoding="utf-8")

        with FileIoUtils.fopen(test_file, mode='a') as f:
            f.write("Line 2\n")

        content: str = test_file.read_text(encoding="utf-8")
        assert content == "Line 1\nLine 2\n"

    def test_fopen_exclusive_mode_prevents_overwrite(self, tmp_path: Path) -> None:
        """
        Test that exclusive mode prevents overwriting existing files.
        """
        test_file: Path = tmp_path / "exclusive.txt"
        test_file.write_text("Existing", encoding="utf-8")

        with pytest.raises(FileExistsError):
            FileIoUtils.fopen(test_file, mode='x')

    def test_fopen_read_write_mode(self, tmp_path: Path) -> None:
        """
        Test read/write mode allows both operations.
        """
        test_file: Path = tmp_path / "readwrite.txt"
        test_file.write_text("Original\n", encoding="utf-8")

        with FileIoUtils.fopen(test_file, mode='r+') as f:
            content: str = f.read()
            f.write("Modified")

        final_content: str = test_file.read_text(encoding="utf-8")
        assert "Original" in final_content
        assert "Modified" in final_content

    @pytest.mark.parametrize("path_type", [str, Path])
    def test_fopen_accepts_string_and_path(
        self,
        tmp_path: Path,
        path_type: type[str] | type[Path]
    ) -> None:
        """
        Test fopen accepts both string and Path objects.
        """
        test_file: str | Path = path_type(tmp_path / "path_test.txt")

        with FileIoUtils.fopen(test_file, mode='w') as f:
            f.write("Content")

        assert Path(test_file).exists()

    @pytest.mark.parametrize("encoding", ['utf-8', 'utf-16', 'latin-1'])
    def test_fopen_custom_encoding(self, tmp_path: Path, encoding: str) -> None:
        """
        Test fopen with various encodings.
        """
        test_file: Path = tmp_path / f"encoding_{encoding}.txt"
        test_content: str = "Test Content with special chars: ñ, ü, é"

        with FileIoUtils.fopen(test_file, mode='w', encoding=encoding) as f:
            f.write(test_content)

        with FileIoUtils.fopen(test_file, mode='r', encoding=encoding) as f:
            content: str = f.read()

        assert content == test_content

    def test_fopen_read_nonexistent_file(self, tmp_path: Path) -> None:
        """
        Test that reading non-existent file raises FileNotFoundError.
        """
        test_file: Path = tmp_path / "nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            FileIoUtils.fopen(test_file, mode='r')

    def test_fopen_context_manager_closes_file(self, tmp_path: Path) -> None:
        """
        Test that context manager properly closes files.
        """
        test_file: Path = tmp_path / "context.txt"

        with FileIoUtils.fopen(test_file, mode='w') as f:
            f.write("Test")
            file_obj = f

        assert file_obj.closed


class TestReadJson:
    """
    Test cases for read_json function.
    """

    def test_read_json_valid_json(
        self,
        tmp_path: Path,
        sample_json_data: dict[str, Any]
    ) -> None:
        """
        Test reading a valid JSON file.
        """
        test_file: Path = tmp_path / "test.json"
        test_file.write_text(json.dumps(sample_json_data), encoding="utf-8")

        result: dict[str, Any] = FileIoUtils.read_json(test_file)

        assert result == sample_json_data

    @pytest.mark.parametrize("json5_content,expected", [
        # Comments support
        ('{"name": "Bob", /* block comment */ "age": 25}', {"name": "Bob", "age": 25}),
        ('{\n  // line comment\n  "key": "value"\n}', {"key": "value"}),
        # Trailing commas
        ('{"items": [1, 2, 3,]}', {"items": [1, 2, 3]}),
        ('{"trailing": "comma",}', {"trailing": "comma"}),
        # Single quotes
        ("{'name': 'Alice', 'age': 30}", {"name": "Alice", "age": 30}),
        # Unquoted keys
        ('{unquoted: "value", another: 123}', {"unquoted": "value", "another": 123}),
        # Mixed features
        ('{name: "Bob", /* comment */ age: 25,}', {"name": "Bob", "age": 25}),
    ])
    def test_read_json5_features(
        self,
        tmp_path: Path,
        json5_content: str,
        expected: dict[str, Any]
    ) -> None:
        """
        Test reading JSON5 with various features (comments, trailing commas, single quotes, unquoted keys).
        """
        test_file: Path = tmp_path / "test.json5"
        test_file.write_text(json5_content, encoding="utf-8")

        result: dict[str, Any] = FileIoUtils.read_json(test_file)

        assert result == expected

    @pytest.mark.parametrize("data_structure,expected_path,expected_value", [
        # Deeply nested dict
        (
            {"level1": {"level2": {"level3": {"level4": {"value": "deep"}}}}},
            ["level1", "level2", "level3", "level4", "value"],
            "deep"
        ),
        # Array with nested objects
        (
            {"users": [{"id": 1, "profile": {"name": "Alice"}}]},
            ["users", 0, "profile", "name"],
            "Alice"
        ),
        # Mixed nesting
        (
            {"data": [{"items": [{"nested": {"key": 42}}]}]},
            ["data", 0, "items", 0, "nested", "key"],
            42
        ),
    ])
    def test_read_json_complex_structures(
        self,
        tmp_path: Path,
        data_structure: dict[str, Any],
        expected_path: list[str | int],
        expected_value: Any
    ) -> None:
        """
        Test reading deeply nested and complex JSON structures.
        """
        test_file: Path = tmp_path / "nested.json"
        test_file.write_text(json.dumps(data_structure), encoding="utf-8")

        result: dict[str, Any] = FileIoUtils.read_json(test_file)

        # Navigate to nested value
        current = result
        for key in expected_path:
            current = current[key]

        assert current == expected_value

    @pytest.mark.parametrize("special_data", [
        # Unicode characters
        {"message": "你好世界", "emoji": "🌍"},
        {"math": "∑∫∂", "symbols": "←↑→↓"},
        {"cyrillic": "Привет", "arabic": "مرحبا"},
        # Mixed unicode
        {"mixed": "Hello 世界 🎉 مرحبا"},
    ])
    def test_read_json_unicode_characters(
        self,
        tmp_path: Path,
        special_data: dict[str, str]
    ) -> None:
        """
        Test reading JSON with various unicode characters.
        """
        test_file: Path = tmp_path / "unicode.json"
        test_file.write_text(
            json.dumps(special_data, ensure_ascii=False),
            encoding="utf-8"
        )

        result: dict[str, str] = FileIoUtils.read_json(test_file)

        assert result == special_data

    @pytest.mark.parametrize("data_content,data_type", [
        # Primitive types
        ("null", type(None)),
        ("true", bool),
        ("false", bool),
        ("42", int),
        ('"string"', str),
        ("3.14", float),
        # Collections
        ("[]", list),
        ("[1, 2, 3]", list),
        ('["a", "b", "c"]', list),
        ("{}", dict),
        ('{"key": "value"}', dict),
    ])
    def test_read_json_various_types(
        self,
        tmp_path: Path,
        data_content: str,
        data_type: type
    ) -> None:
        """
        Test reading JSON with various data types (primitives, arrays, objects).
        """
        test_file: Path = tmp_path / "types.json"
        test_file.write_text(data_content, encoding="utf-8")

        result = FileIoUtils.read_json(test_file)

        if data_type is type(None):
            assert result is None
        else:
            assert isinstance(result, data_type)

    @pytest.mark.parametrize("invalid_content,error_description", [
        ("{invalid json}", "missing quotes around key"),
        ("{missing: quotes}", "missing quotes around key and value"),
        ("{\"unclosed\": ", "unclosed bracket"),
        ("[1, 2, 3", "unclosed array bracket"),
        ('{"key": undefined}', "undefined keyword"),
        ('{"key":}', "missing value"),
        ('{,}', "leading comma"),
        ('{"a": "b",,}', "double comma"),
    ])
    def test_read_json_invalid_syntax(
        self,
        tmp_path: Path,
        invalid_content: str,
        error_description: str
    ) -> None:
        """
        Test that invalid JSON syntax raises appropriate errors.
        """
        test_file: Path = tmp_path / "invalid.json"
        test_file.write_text(invalid_content, encoding="utf-8")

        with pytest.raises(Exception) as exc_info:  # json.JSONDecodeError or pyjson5 error
            FileIoUtils.read_json(test_file)

        # Verify error was raised (error_description is for documentation)
        assert exc_info.value is not None

    @pytest.mark.parametrize("edge_case,description", [
        ("", "empty file"),
        ("   ", "whitespace only"),
        ("\n\n", "newlines only"),
    ])
    def test_read_json_empty_or_whitespace(
        self,
        tmp_path: Path,
        edge_case: str,
        description: str
    ) -> None:
        """
        Test reading empty or whitespace-only files raises error.
        """
        test_file: Path = tmp_path / f"{description.replace(' ', '_')}.json"
        test_file.write_text(edge_case, encoding="utf-8")

        with pytest.raises(Exception):
            FileIoUtils.read_json(test_file)

    def test_read_json_nonexistent_file(self, tmp_path: Path) -> None:
        """
        Test that reading non-existent file raises FileNotFoundError.
        """
        test_file: Path = tmp_path / "missing.json"

        with pytest.raises(FileNotFoundError):
            FileIoUtils.read_json(test_file)

    def test_read_json_duplicate_keys(self, tmp_path: Path) -> None:
        """
        Test behavior with duplicate keys (last value wins in most parsers).
        """
        test_file: Path = tmp_path / "duplicate.json"
        test_file.write_text('{"duplicate": 1, "duplicate": 2}', encoding="utf-8")

        result: dict[str, int] = FileIoUtils.read_json(test_file)

        # Most JSON parsers allow duplicate keys, last one wins
        assert result == {"duplicate": 2}
        assert len(result) == 1  # Only one key present


class TestWriteJson:
    """
    Test cases for write_json function.
    """

    def test_write_json_creates_file(
        self,
        tmp_path: Path,
        sample_json_data: dict[str, Any]
    ) -> None:
        """Test that write_json creates a new file with correct data."""
        test_file: Path = tmp_path / "output.json"

        FileIoUtils.write_json(sample_json_data, test_file, encoding="utf-8")

        assert test_file.exists()
        result: dict[str, Any] = json.loads(test_file.read_text(encoding="utf-8"))
        assert result == sample_json_data

    @pytest.mark.parametrize("indent", [None, 2, 4, "\t"])
    def test_write_json_indentation(
        self,
        tmp_path: Path,
        indent: int | str | None
    ) -> None:
        """
        Test writing JSON with various indentation options.
        """
        test_file: Path = tmp_path / f"indent.json"
        data: dict[str, int | dict[str, int]] = {"a": 1, "b": {"c": 2}}

        FileIoUtils.write_json(data, test_file, encoding="utf-8", indent=indent)

        content: str = test_file.read_text(encoding="utf-8")
        if indent:
            assert "\n" in content  # Formatted output
        result: dict[str, Any] = json.loads(content)
        assert result == data

    def test_write_json_overwrite_existing(self, tmp_path: Path) -> None:
        """
        Test that write mode overwrites existing files.
        """
        test_file: Path = tmp_path / "overwrite.json"

        FileIoUtils.write_json({"old": "data"}, test_file, encoding="utf-8")
        FileIoUtils.write_json({"new": "data"}, test_file, mode='w', encoding="utf-8")

        result: dict[str, str] = json.loads(test_file.read_text(encoding="utf-8"))
        assert result == {"new": "data"}
        assert "old" not in result

    def test_write_json_append_mode_warning(self, tmp_path: Path) -> None:
        """
        Test append mode behavior (creates invalid JSON with multiple objects).
        """
        test_file: Path = tmp_path / "append.json"

        FileIoUtils.write_json({"first": 1}, test_file, mode='w', encoding="utf-8")
        FileIoUtils.write_json({"second": 2}, test_file, mode='a', encoding="utf-8")

        content: str = test_file.read_text(encoding="utf-8")
        # Both objects present but not valid JSON
        assert "first" in content
        assert "second" in content

    def test_write_json_unicode_preservation(self, tmp_path: Path) -> None:
        """
        Test that unicode characters are preserved correctly.
        """
        test_file: Path = tmp_path / "unicode_out.json"
        data: dict[str, str] = {
            "chinese": "中文",
            "japanese": "日本語",
            "emoji": "🎉🎊",
            "mixed": "Hello 世界"
        }

        FileIoUtils.write_json(data, test_file, encoding="utf-8")

        result: dict[str, str] = json.loads(test_file.read_text(encoding="utf-8"))
        assert result == data

    @pytest.mark.parametrize("complex_data", [
        {"users": [{"id": i, "name": f"User{i}"} for i in range(5)]},
        {"matrix": [[1, 2], [3, 4], [5, 6]]},
        {"nested": {"a": {"b": {"c": {"d": "deep"}}}}},
    ])
    def test_write_json_complex_structures(
        self,
        tmp_path: Path,
        complex_data: dict[str, Any]
    ) -> None:
        """
        Test writing various complex data structures.
        """
        test_file: Path = tmp_path / "complex.json"

        FileIoUtils.write_json(complex_data, test_file, encoding="utf-8")

        result: dict[str, Any] = json.loads(test_file.read_text(encoding="utf-8"))
        assert result == complex_data

    def test_write_json_custom_types_with_default(self, tmp_path: Path) -> None:
        """
        Test that custom types are serialized using default=str.
        """
        test_file: Path = tmp_path / "custom_types.json"

        class CustomObject:
            def __str__(self) -> str:
                return "CustomString"

        data: dict[str, CustomObject | str] = {
            "custom": CustomObject(),
            "normal": "value"
        }

        FileIoUtils.write_json(data, test_file, encoding="utf-8")

        result: dict[str, str] = json.loads(test_file.read_text(encoding="utf-8"))
        assert result["custom"] == "CustomString"
        assert result["normal"] == "value"

    @pytest.mark.parametrize("edge_case_data", [
        {},
        [],
        {"null_value": None},
        {"empty_string": ""},
        {"empty_list": []},
        {"empty_dict": {}},
    ])
    def test_write_json_edge_cases(
        self,
        tmp_path: Path,
        edge_case_data: dict[str, Any] | list[Any]
    ) -> None:
        """
        Test writing edge case data.
        """
        test_file: Path = tmp_path / "edge_case.json"

        FileIoUtils.write_json(edge_case_data, test_file, encoding="utf-8")

        result: dict[str, Any] | list[Any] = json.loads(
            test_file.read_text(encoding="utf-8")
        )
        assert result == edge_case_data

    @pytest.mark.parametrize("data_type", [
        [1, 2, 3],
        ["a", "b", "c"],
        [{"id": 1}, {"id": 2}],
    ])
    def test_write_json_array_root(
        self,
        tmp_path: Path,
        data_type: list[int] | list[str] | list[dict[str, int]]
    ) -> None:
        """
        Test writing arrays as root element.
        """
        test_file: Path = tmp_path / "array_out.json"

        FileIoUtils.write_json(data_type, test_file, encoding="utf-8")

        result: list[Any] = json.loads(test_file.read_text(encoding="utf-8"))
        assert result == data_type

    def test_write_json_special_values(self, tmp_path: Path) -> None:
        """
        Test writing JSON with special numeric values.
        """
        test_file: Path = tmp_path / "special.json"
        data: dict[str, int | float] = {
            "int": 42,
            "float": 3.14159,
            "negative": -100,
            "zero": 0,
            "large": 1e10,
            "small": 1e-10,
        }

        FileIoUtils.write_json(data, test_file, encoding="utf-8")

        result: dict[str, int | float] = json.loads(
            test_file.read_text(encoding="utf-8")
        )
        assert result == data


class TestIntegration:
    """
    Integration tests for file_io operations.
    """

    @pytest.mark.parametrize("data", [
        {"simple": "test"},
        {"nested": {"deep": {"value": 123}}},
        [1, 2, {"mixed": "list"}],
        {"unicode": "测试 🎉"},
    ])
    def test_write_read_roundtrip(
        self,
        tmp_path: Path,
        data: dict[str, Any] | list[Any]
    ) -> None:
        """
        Test that write/read roundtrip preserves data integrity.
        """
        test_file: Path = tmp_path / "roundtrip.json"

        FileIoUtils.write_json(data, test_file)
        result: dict[str, Any] | list[Any] = FileIoUtils.read_json(test_file)

        assert result == data

    def test_multiple_operations_sequence(self, tmp_path: Path) -> None:
        """
        Test multiple file operations in sequence.
        """
        test_file: Path = tmp_path / "sequence.json"

        # Initial write
        FileIoUtils.write_json({"version": 1}, test_file)
        assert FileIoUtils.read_json(test_file)["version"] == 1

        # Update
        FileIoUtils.write_json({"version": 2, "updated": True}, test_file)
        data: dict[str, Any] = FileIoUtils.read_json(test_file)
        assert data["version"] == 2
        assert data["updated"] is True

        # Final update
        FileIoUtils.write_json({"version": 3}, test_file)
        assert FileIoUtils.read_json(test_file)["version"] == 3

    def test_concurrent_file_access_pattern(self, tmp_path: Path) -> None:
        """
        Test pattern of reading, modifying, and writing back.
        """
        test_file: Path = tmp_path / "concurrent.json"
        initial_data: dict[str, int | list[str]] = {"counter": 0, "items": []}

        FileIoUtils.write_json(initial_data, test_file)

        # Simulate multiple updates
        for i in range(3):
            data: dict[str, Any] = FileIoUtils.read_json(test_file)
            data["counter"] += 1
            data["items"].append(f"item_{i}")
            FileIoUtils.write_json(data, test_file)

        final_data: dict[str, Any] = FileIoUtils.read_json(test_file)
        assert final_data["counter"] == 3
        assert len(final_data["items"]) == 3

    def test_mixed_file_operations(self, tmp_path: Path) -> None:
        """
        Test mixing fopen and JSON operations.
        """
        json_file: Path = tmp_path / "data.json"
        txt_file: Path = tmp_path / "log.txt"

        # Write JSON
        FileIoUtils.write_json({"status": "start"}, json_file)

        # Write log
        with FileIoUtils.fopen(txt_file, mode='w') as f:
            f.write("Operation started\n")

        # Read and update JSON
        data: dict[str, str] = FileIoUtils.read_json(json_file)
        data["status"] = "complete"
        FileIoUtils.write_json(data, json_file)

        # Append to log
        with FileIoUtils.fopen(txt_file, mode='a') as f:
            f.write("Operation completed\n")

        # Verify
        final_json: dict[str, str] = FileIoUtils.read_json(json_file)
        assert final_json["status"] == "complete"

        with FileIoUtils.fopen(txt_file, mode='r') as f:
            log_content: str = f.read()
        assert "started" in log_content
        assert "completed" in log_content

    def test_large_data_handling(self, tmp_path: Path) -> None:
        """
        Test handling of larger data sets.
        """
        test_file: Path = tmp_path / "large.json"
        large_data: dict[str, list[dict[str, Any]]] = {
            "records": [
                {"id": i, "value": f"item_{i}", "metadata": {"index": i}}
                for i in range(1000)
            ]
        }

        FileIoUtils.write_json(large_data, test_file)
        result: dict[str, list[dict[str, Any]]] = FileIoUtils.read_json(test_file)

        assert len(result["records"]) == 1000
        assert result["records"][0]["id"] == 0
        assert result["records"][-1]["id"] == 999
