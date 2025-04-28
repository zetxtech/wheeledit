import sys
import argparse
import os
import json
from pathlib import Path

from wheeledit.editor import WheelEditor

def get_content_type_from_readme(readme_path):
    """
    Determine the content type based on README file extension.
    
    Args:
        readme_path: Path to the README file
        
    Returns:
        str: Content type for the description
    """
    suffix = Path(readme_path).suffix.lower()
    
    if suffix in ('.md', '.markdown'):
        return 'text/markdown'
    elif suffix == '.rst':
        return 'text/x-rst'
    else:
        return 'text/plain'  # Default to plain text

def has_modifications(args):
    """
    Check if any modification arguments are provided.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        bool: True if any modification arguments are provided, False otherwise
    """
    modification_args = ['rename', 'metadata']
    return any(getattr(args, arg) is not None for arg in modification_args)

def process_wheel(wheel_path, args, is_directory=False):
    """
    Process a wheel file according to the provided arguments.
    
    Args:
        wheel_path: Path to the wheel file
        args: Parsed command line arguments
        is_directory: Whether the operation is part of a directory process
        
    Returns:
        tuple: (success, output_path) or (False, None) if only displaying metadata
    """
    wheel_path = Path(wheel_path)
    
    # Determine output path directly without a separate function
    if args.output:
        if is_directory:
            output_path = Path(args.output) / wheel_path.name
        else:
            output_path = Path(args.output)
    elif args.rename:
        # For rename operations, use a new filename in the same directory
        new_name = args.rename
        
        # Properly handle wheel filename format to preserve the exact structure
        wheel_filename = wheel_path.name
        if '-' in wheel_filename:
            # Find the first dash that separates the package name from the version
            parts = wheel_filename.split('-', 1)
            if len(parts) == 2:
                new_wheel_name = f"{new_name.replace('-', '_')}-{parts[1]}"
                output_path = wheel_path.parent / new_wheel_name
            else:
                # Fallback if the wheel name doesn't parse as expected
                output_path = wheel_path.with_name(f"{new_name}-{wheel_path.name}")
        else:
            # Fallback if the wheel name doesn't follow the expected format
            output_path = wheel_path.with_name(f"{new_name}-{wheel_path.name}")
    else:
        # Use original path as output for non-rename operations
        output_path = wheel_path
    
    # Initialize the editor
    editor = WheelEditor(wheel_path)
    
    # If no modifications are requested, display metadata and return
    if not has_modifications(args):
        editor.unpack()
        metadata = editor.get_metadata()
        if metadata:
            print(metadata)
        editor.cleanup()
        return False, None
    
    try:
        # Unpack the wheel
        editor.unpack()
        
        # Process according to arguments
        if args.rename:
            editor.rename_package(args.rename)
        
        # Process metadata file if provided
        if args.metadata:
            metadata_path = Path(args.metadata)
            if metadata_path.exists():
                # Read metadata from file
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    # Check if it's a JSON file
                    if metadata_path.suffix.lower() == '.json':
                        metadata_dict = json.load(f)
                        editor.update_metadata(**metadata_dict)
                    else:
                        # Treat as METADATA file content
                        metadata_content = f.read()
                        editor.replace_metadata(metadata_path)
            else:
                raise FileNotFoundError(f"Metadata file not found: {args.metadata}")
        
        # Repackage the wheel
        editor.repackage(output_path)
        return True, output_path
    finally:
        editor.cleanup()

def main():
    parser = argparse.ArgumentParser(description='Edit wheel metadata and content')
    
    parser.add_argument('input', nargs='+', help='Input wheel file(s) or directory')
    parser.add_argument('-o', '--output', help='Output path (file or directory)')
    parser.add_argument('--rename', help='Rename the package')
    parser.add_argument('--metadata', help='File containing metadata to update (JSON or METADATA format)')
    
    args = parser.parse_args()
    
    # Check if inputs exist first
    input_paths = [Path(p) for p in args.input]
    non_existent = [p for p in input_paths if not p.exists()]
    
    if non_existent:
        parser.error(f"Input file(s) or directory(ies) not found: {', '.join(str(p) for p in non_existent)}")
    
    # Check if inputs are all files or all directories
    are_files = [p.is_file() for p in input_paths]
    are_dirs = [p.is_dir() for p in input_paths]
    
    if not all(are_files) and not all(are_dirs):
        parser.error("Cannot mix files and directories as inputs")
    
    is_dir_mode = all(are_dirs)
    
    # If in directory mode, output must be a directory or None
    if is_dir_mode and args.output and not Path(args.output).is_dir():
        parser.error("When processing directories, output must also be a directory")
    
    # Process metadata file if provided
    if args.metadata and not Path(args.metadata).exists():
        parser.error(f"Metadata file not found: {args.metadata}")
    
    # Process wheel files
    processed_files = []
    
    if is_dir_mode:
        # Process all wheel files in the given directories
        for dir_path in input_paths:
            wheel_files = list(dir_path.glob('*.whl'))
            if not wheel_files:
                print(f"No wheel files found in {dir_path}")
                continue
                
            for wheel_file in wheel_files:
                try:
                    success, output_file = process_wheel(wheel_file, args, is_directory=True)
                    
                    if success and output_file:
                        processed_files.append(output_file)
                        print(f"Processed: {wheel_file} -> {output_file}")
                except Exception as e:
                    print(f"Error processing {wheel_file}: {e}", file=sys.stderr)
                    raise
    else:
        # Process individual wheel files
        for wheel_file in input_paths:
            if not str(wheel_file).endswith('.whl'):
                print(f"Warning: {wheel_file} does not appear to be a wheel file", file=sys.stderr)
                
            try:
                success, output_file = process_wheel(wheel_file, args)
                
                if success and output_file:
                    processed_files.append(output_file)
                    print(f"Processed: {wheel_file} -> {output_file}")
            except Exception as e:
                print(f"Error processing {wheel_file}: {e}", file=sys.stderr)
                raise
    
    if not processed_files and has_modifications(args):
        print("No files were processed successfully")
        return 1
        
    return 0

if __name__ == '__main__':
    sys.exit(main())
