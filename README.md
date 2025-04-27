# WheelEdit

A tool for editing Python wheel packages without modifying the internal package structure.

## Installation

```
pip install wheeledit
```

## Features

- Display wheel metadata
- Edit package metadata and repack
- Rename packages
- Process multiple wheel files or directories

**NOTE**: WheelEdit can not rename the internal packages and modules.

## Usage

### Edit Metadata

1. Extract the metadata to a file
2. Edit the file
3. Apply the changes

```bash
# Extract metadata
wheeledit example-1.0.0-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.whl > metadata.txt

# Edit metadata.txt with your preferred editor

# Apply changes
wheeledit example-1.0.0-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.whl --metadata metadata.txt
```

### Rename Package

```bash
wheeledit example-1.0.0-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.whl --rename new-package-name
```

## License

MIT
