import argparse
import re
import json
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def load_json_file(file_path: Path) -> Any:
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    raw = file_path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}

    return json.loads(raw)


def load_json_url(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=20) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read().decode("utf-8")

    if not raw.strip():
        return {}

    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"URL did not return valid JSON ({content_type}): {error}") from None


def save_json_file(file_path: Path, data: Any) -> None:
    file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def save_json_temp(data: Any) -> Path:
    fd, name = tempfile.mkstemp(prefix="m_json_", suffix=".json")
    with open(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return Path(name)


def parse_path(path: str) -> list[str]:
    segments = [segment for segment in path.split(".") if segment]
    if not segments:
        raise ValueError("A dotted path is required for this action.")
    return segments


def parse_value(raw_value: str) -> Any:
    text = raw_value.strip()

    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        relaxed = try_parse_relaxed_json(raw_value)
        if relaxed is not _UNSET:
            return relaxed

        if text.startswith("{") or text.startswith("["):
            raise ValueError(build_value_error_message(text))

        return raw_value


_UNSET = object()


def try_parse_relaxed_json(raw_value: str) -> Any:
    text = raw_value.strip()
    if not text or text[0] not in "[{":
        return _UNSET

    normalized = text
    normalized = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_-]*)(\s+)(?=[^,\]}])', r'\1"\2": ', normalized)
    normalized = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_-]*)(\s*:)', r'\1"\2"\3', normalized)
    normalized = re.sub(r"'", '"', normalized)

    def replace_bare_value(match: re.Match[str]) -> str:
        prefix = match.group(1)
        token = match.group(2)
        suffix = match.group(3)

        if token in {"true", "false", "null"}:
            return f"{prefix}{token}{suffix}"

        if re.fullmatch(r"-?\d+(?:\.\d+)?", token):
            return f"{prefix}{token}{suffix}"

        return f'{prefix}"{token}"{suffix}'

    normalized = re.sub(
        r'(:\s*|,\s*|\[\s*)([A-Za-z_][A-Za-z0-9_-]*)(\s*(?=[,\]}]))',
        replace_bare_value,
        normalized,
    )

    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        return _UNSET


def build_value_error_message(text: str) -> str:
    if text.startswith("["):
        if ":" in text:
            return (
                "Invalid array value. Arrays only contain items. "
                'Use JSON like ["item1","item2"]. If you meant key/value pairs, use an object like {"key1":"value1","key2":"value2"}.'
            )

        if text.count("[") != text.count("]"):
            return 'Invalid array value. Missing closing ]. Use JSON like ["item1","item2"].'

        return 'Invalid array value. Use JSON like ["item1","item2"].'

    if text.startswith("{"):
        if text.count("{") != text.count("}"):
            return 'Invalid object value. Missing closing }. Use JSON like {"key1":"value1","key2":"value2"}.'

        return (
            "Invalid object value. Each entry should be a key and a value. "
            'Example: {"key1":"value1","key2":"value2"}.'
        )

    return "Invalid value."


def format_error(error: Exception) -> str:
    if isinstance(error, KeyError) and error.args:
        return str(error.args[0])

    return str(error)


def to_display_value(value: Any) -> str:
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")) if isinstance(value, (dict, list)) else json.dumps(value, ensure_ascii=False)
    return str(value)


def get_child(node: Any, segment: str) -> Any:
    if isinstance(node, list):
        if not segment.isdigit():
            raise ValueError(f"Expected a numeric index at '{segment}'.")
        index = int(segment)
        if index < 0 or index >= len(node):
            raise IndexError(f"Index out of range: {segment}")
        return node[index]

    if isinstance(node, dict):
        if segment not in node:
            raise KeyError(f"Path not found: {segment}")
        return node[segment]

    raise TypeError(f"Cannot continue through '{segment}' because the current value is not an object or array.")


def get_value(root: Any, segments: list[str]) -> Any:
    current = root
    walked: list[str] = []
    for segment in segments:
        path_so_far = ".".join(walked + [segment])
        try:
            current = get_child(current, segment)
        except KeyError:
            raise KeyError(f"Path not found: {path_so_far}. Run 'list' to see valid paths.") from None
        except IndexError:
            raise IndexError(f"Index out of range: {path_so_far}") from None
        except ValueError:
            raise ValueError(f"Expected a numeric index at '{path_so_far}'.") from None

        walked.append(segment)

    return current


def ensure_child_container(parent: Any, segment: str, next_segment: str) -> Any:
    next_container: Any = [] if next_segment.isdigit() else {}

    if isinstance(parent, list):
        if not segment.isdigit():
            raise ValueError(f"Expected a numeric index at '{segment}'.")
        index = int(segment)
        while len(parent) <= index:
            parent.append(None)
        if parent[index] is None:
            parent[index] = next_container
        elif not isinstance(parent[index], (dict, list)):
            raise TypeError(f"Cannot continue through '{segment}' because the current value is not an object or array.")
        return parent[index]

    if isinstance(parent, dict):
        if segment not in parent or parent[segment] is None:
            parent[segment] = next_container
        elif not isinstance(parent[segment], (dict, list)):
            raise TypeError(f"Cannot continue through '{segment}' because the current value is not an object or array.")
        return parent[segment]

    raise TypeError(f"Cannot continue through '{segment}' because the current value is not an object or array.")


def set_value(root: Any, segments: list[str], value: Any) -> None:
    current = root
    for index, segment in enumerate(segments[:-1]):
        current = ensure_child_container(current, segment, segments[index + 1])

    last = segments[-1]
    if isinstance(current, list):
        if not last.isdigit():
            raise ValueError(f"Expected a numeric index at '{last}'.")
        list_index = int(last)
        while len(current) <= list_index:
            current.append(None)
        current[list_index] = value
        return

    if isinstance(current, dict):
        current[last] = value
        return

    raise TypeError(f"Cannot set '{last}' because the parent is not an object or array.")


def unset_value(root: Any, segments: list[str]) -> None:
    if len(segments) == 1:
        if not isinstance(root, dict):
            raise TypeError("Top-level unset only supports object properties.")
        if segments[0] not in root:
            raise KeyError(f"Path not found: {segments[0]}")
        del root[segments[0]]
        return

    parent = get_value(root, segments[:-1])
    last = segments[-1]

    if isinstance(parent, list):
        if not last.isdigit():
            raise ValueError(f"Expected a numeric index at '{last}'.")
        index = int(last)
        if index < 0 or index >= len(parent):
            raise IndexError(f"Index out of range: {last}")
        parent.pop(index)
        return

    if isinstance(parent, dict):
        if last not in parent:
            raise KeyError(f"Path not found: {last}")
        del parent[last]
        return

    raise TypeError(f"Cannot unset '{last}' because the parent is not an object or array.")


def flatten_json(node: Any, prefix: str = "") -> list[str]:
    lines: list[str] = []

    if isinstance(node, dict):
        for key, value in node.items():
            child_path = key if not prefix else f"{prefix}.{key}"
            lines.extend(flatten_json(value, child_path))
        return lines

    if isinstance(node, list):
        for index, value in enumerate(node):
            child_path = str(index) if not prefix else f"{prefix}.{index}"
            lines.extend(flatten_json(value, child_path))
        return lines

    lines.append(f"{prefix} = {to_display_value(node)}")
    return lines


def search_json(node: Any, query: str, prefix: str = "") -> list[str]:
    query_lower = query.lower()
    matches: list[str] = []

    if isinstance(node, dict):
        for key, value in node.items():
            child_path = key if not prefix else f"{prefix}.{key}"
            if query_lower in str(key).lower():
                matches.append(f"{child_path} = {to_display_value(value)}")
            matches.extend(search_json(value, query, child_path))
        return matches

    if isinstance(node, list):
        for index, value in enumerate(node):
            child_path = str(index) if not prefix else f"{prefix}.{index}"
            matches.extend(search_json(value, query, child_path))
        return matches

    value_text = to_display_value(node)
    if query_lower in value_text.lower():
        matches.append(f"{prefix} = {value_text}")
    return matches


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jsniffer: sniff, search, and edit JSON from files or URLs.")
    parser.add_argument("action", choices=["list", "get", "set", "unset", "search"])
    parser.add_argument("file", help="Path or URL to the JSON file")
    parser.add_argument("path", nargs="?", help="Dotted path like player.stats.level, or query for search")
    parser.add_argument("value", nargs="?", help="New value for the set action")
    parser.add_argument("--output", "-o", help="Save modified URL JSON here instead of a temp file")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        source_is_url = is_url(args.file)
        file_path = None if source_is_url else Path(args.file)
        data = load_json_url(args.file) if source_is_url else load_json_file(file_path)

        if args.action == "list":
            for line in flatten_json(data):
                print(line)
            return

        if args.action == "search":
            if not args.path:
                raise ValueError("A search query is required for the search action.")
            matches = search_json(data, args.path)
            if not matches:
                print("No matches found.")
                return
            for line in matches:
                print(line)
            return

        if not args.path:
            raise ValueError("A dotted path is required for this action.")

        segments = parse_path(args.path)

        if args.action == "get":
            print(to_display_value(get_value(data, segments)))
            return

        if args.action == "set":
            if args.value is None:
                raise ValueError("A value is required for the set action.")
            set_value(data, segments, parse_value(args.value))
            if source_is_url:
                output_path = Path(args.output) if args.output else save_json_temp(data)
                if args.output:
                    save_json_file(output_path, data)
                print(f"Updated {args.path}")
                print(f"Saved modified copy: {output_path}")
            else:
                save_json_file(file_path, data)
                print(f"Updated {args.path}")
            return

        unset_value(data, segments)
        if source_is_url:
            output_path = Path(args.output) if args.output else save_json_temp(data)
            if args.output:
                save_json_file(output_path, data)
            print(f"Removed {args.path}")
            print(f"Saved modified copy: {output_path}")
        else:
            save_json_file(file_path, data)
            print(f"Removed {args.path}")
    except Exception as error:
        print(f"Error: {format_error(error)}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
