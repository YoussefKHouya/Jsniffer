# Jsniffer

Sniff, search, and edit JSON from files or URLs.

Jsniffer is a small Python script for working with nested JSON using dotted paths:

```text
player.stats.level
player.inventory.0.name
settings.audio.music
```

## Features

- List JSON as dotted paths
- Get one nested value
- Set or create nested values
- Remove values
- Smart search across keys and values
- Read JSON directly from URLs
- For URL edits, save a local modified copy instead of touching remote data
- No external dependencies

## Usage

Run it with Python:

```bash
python3 jsniffer.py <command> <file-or-url> [path-or-query] [value]
```

## Commands

### List JSON

```bash
python3 jsniffer.py list data.json
```

Example output:

```text
player.stats.level = 12
player.inventory.0.name = "Sword"
```

### Get value

```bash
python3 jsniffer.py get data.json player.stats.level
```

### Set value

```bash
python3 jsniffer.py set data.json player.stats.level 15
python3 jsniffer.py set data.json settings.debug true
python3 jsniffer.py set data.json player.items '["sword","shield"]'
```

### Remove value

```bash
python3 jsniffer.py unset data.json player.stats.level
```

### Smart search

Search keys and values:

```bash
python3 jsniffer.py search data.json sword
```

Example output:

```text
player.inventory.0.name = "Sword"
player.items.0 = "sword"
```

## URL mode

Read JSON from URL:

```bash
python3 jsniffer.py list https://example.com/endpoint.json
python3 jsniffer.py get https://example.com/endpoint.json player.stats.level
python3 jsniffer.py search https://example.com/endpoint.json sword
```

Edit JSON from URL. Jsniffer downloads it, modifies a local copy, and saves it to a temp file:

```bash
python3 jsniffer.py set https://example.com/endpoint.json player.stats.level 15
```

Choose output path:

```bash
python3 jsniffer.py set https://example.com/endpoint.json player.stats.level 15 -o edited.json
python3 jsniffer.py unset https://example.com/endpoint.json player.stats.level -o edited.json
```

For URL mode, `set` and `unset` never modify remote data. Jsniffer only saves a modified local copy.

## Requirements

- Python 3.10+
