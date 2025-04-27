import os
import shutil
import hashlib
import sys
import tempfile
import re
from pathlib import Path

class HiddenPrints:
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout


class WheelEditor:
    def __init__(self, wheel_path):
        """
        Initialize a WheelEditor for a given wheel file.
        
        Args:
            wheel_path: Path to the wheel file to edit
        """
        self.wheel_path = Path(wheel_path)
        self.unpacked_dir = None
        self.dist_info_dir = None
        self.original_name = None
        self.original_metadata = None

    def unpack(self):
        """
        Unpack the wheel file to a temporary directory.
        
        Returns:
            Path to the unpacked directory
        """
        from wheel.cli import unpack
        
        if self.unpacked_dir is None:
            temp_dir = Path(tempfile.mkdtemp())
            
            with HiddenPrints():
                unpack.unpack(str(self.wheel_path), str(temp_dir))
            
            # The wheel is unpacked to a subdirectory named after the package and version
            # Find that subdirectory
            subdirs = [d for d in temp_dir.iterdir() if d.is_dir()]
            if not subdirs:
                raise ValueError("No subdirectories found after unpacking wheel")
            
            self.unpacked_dir = subdirs[0]  # Use the first subdirectory found
            
            # Find the .dist-info directory
            dist_info_dirs = list(self.unpacked_dir.glob('*.dist-info'))
            if not dist_info_dirs:
                raise ValueError("No .dist-info directory found in the wheel")
            self.dist_info_dir = dist_info_dirs[0]
            
            # Store the original package name
            self.original_name = self.dist_info_dir.name.split('-')[0]
            
            # Store original metadata as simple string
            metadata_path = self.dist_info_dir / 'METADATA'
            if metadata_path.exists():
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    self.original_metadata = f.read()
        
        return self.unpacked_dir

    def rename_package(self, new_name):
        """
        Rename the package.
        
        Args:
            new_name: New package name
        """
        if self.unpacked_dir is None:
            self.unpack()
        
        old_name = self.original_name
        
        # Rename the .dist-info directory
        new_dist_info_name = self.dist_info_dir.name.replace(old_name, new_name, 1)
        new_dist_info_path = self.dist_info_dir.parent / new_dist_info_name
        self.dist_info_dir.rename(new_dist_info_path)
        self.dist_info_dir = new_dist_info_path
        
        # Update METADATA file
        metadata_path = self.dist_info_dir / 'METADATA'
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata_content = f.read()
            
            # Update the Name field
            metadata_content = metadata_content.replace(f'Name: {old_name}', f'Name: {new_name}')
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                f.write(metadata_content)
        
        # Update WHEEL file if it exists
        wheel_path = self.dist_info_dir / 'WHEEL'
        if wheel_path.exists():
            with open(wheel_path, 'r', encoding='utf-8') as f:
                wheel_content = f.read()
            
            # Replace any occurrences of the old name in the wheel content
            wheel_content = wheel_content.replace(old_name, new_name)
            
            with open(wheel_path, 'w', encoding='utf-8') as f:
                f.write(wheel_content)
        
        # Update RECORD file if it exists
        record_path = self.dist_info_dir / 'RECORD'
        if record_path.exists():
            with open(record_path, 'r', encoding='utf-8') as f:
                record_lines = f.readlines()
            
            new_record_lines = []
            for line in record_lines:
                # Replace old_name with new_name in all paths
                new_line = line.replace(f"{old_name}-", f"{new_name}-")
                new_record_lines.append(new_line)
            
            with open(record_path, 'w', encoding='utf-8') as f:
                f.writelines(new_record_lines)
        
        # If there are .py files with the old name, we need to update imports
        # This is more complex and might need additional logic based on your requirements
        
        return new_name

    def replace_file(self, target_path, source_path):
        """
        Replace a file in the unpacked wheel with a new file.
        
        Args:
            target_path: Path within the wheel to replace
            source_path: Path to the source file that will replace the target
            
        Returns:
            Path to the replaced file
        """
        if self.unpacked_dir is None:
            self.unpack()
        
        # Normalize paths
        target_path = Path(target_path)
        source_path = Path(source_path)
        
        # Check if source file exists
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        # Calculate the absolute path within the wheel
        if target_path.is_absolute():
            # Convert to relative path if absolute
            try:
                target_path = target_path.relative_to(self.unpacked_dir)
            except ValueError:
                raise ValueError(f"Target path must be inside the wheel: {target_path}")
        
        full_target_path = self.unpacked_dir / target_path
        
        # Create parent directories if they don't exist
        full_target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy the file
        shutil.copy2(str(source_path), str(full_target_path))
        
        return full_target_path

    def replace_metadata(self, source_path):
        """
        Replace the METADATA file in the wheel with a new file.
        
        Args:
            source_path: Path to the source METADATA file
            
        Returns:
            Path to the replaced METADATA file
        """
        if self.unpacked_dir is None:
            self.unpack()
        
        # Normalize the source path
        source_path = Path(source_path)
        
        # Check if source file exists
        if not source_path.exists():
            raise FileNotFoundError(f"Source metadata file not found: {source_path}")
        
        # Get the target path for the METADATA file
        target_path = self.dist_info_dir / 'METADATA'
        
        # Copy the file
        shutil.copy2(str(source_path), str(target_path))
        
        return target_path

    def rename_file(self, pattern, replacement, use_regex=False):
        """
        Find and rename files in the unpacked wheel.
        
        Args:
            pattern: Pattern to match files (string or regex)
            replacement: Replacement string (can use $1, $2, etc. for regex groups)
            use_regex: Whether to use regex matching
            
        Returns:
            List of (old_path, new_path) tuples for renamed files
        """
        if self.unpacked_dir is None:
            self.unpack()
        
        renamed_files = []
        
        # Walk through all files in the unpacked directory
        for root, dirs, files in os.walk(self.unpacked_dir):
            for file in files:
                file_path = Path(root) / file
                rel_path = file_path.relative_to(self.unpacked_dir)
                str_path = str(rel_path)
                
                if use_regex:
                    # Use regex to match and replace
                    match = re.search(pattern, str_path)
                    if match:
                        # Replace with captured groups
                        new_path_str = re.sub(pattern, replacement, str_path)
                        
                        # Replace $1, $2, etc. with captured groups
                        for i, group in enumerate(match.groups(), 1):
                            new_path_str = new_path_str.replace(f'${i}', group)
                        
                        new_rel_path = Path(new_path_str)
                        new_abs_path = self.unpacked_dir / new_rel_path
                        
                        # Create parent directories if they don't exist
                        new_abs_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Rename the file
                        file_path.rename(new_abs_path)
                        renamed_files.append((str_path, str(new_rel_path)))
                else:
                    # Simple string matching
                    if pattern in str_path:
                        new_path_str = str_path.replace(pattern, replacement)
                        new_rel_path = Path(new_path_str)
                        new_abs_path = self.unpacked_dir / new_rel_path
                        
                        # Create parent directories if they don't exist
                        new_abs_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Rename the file
                        file_path.rename(new_abs_path)
                        renamed_files.append((str_path, str(new_rel_path)))
        
        return renamed_files

    def list(self, directory=''):
        """
        List files in the specified directory of the unpacked wheel.
        
        Args:
            directory: Directory path within the wheel to list (default: root)
            
        Returns:
            List of file paths (as Path objects) relative to the wheel root
        """
        if self.unpacked_dir is None:
            self.unpack()
        
        # Normalize the directory path
        directory = Path(directory)
        
        # Calculate the absolute path within the wheel
        target_dir = self.unpacked_dir / directory
        
        # Check if the directory exists
        if not target_dir.exists():
            raise FileNotFoundError(f"Directory not found in wheel: {directory}")
        
        # List all files in the directory and subdirectories
        result = []
        for path in target_dir.rglob('*'):
            if path.is_file():
                rel_path = path.relative_to(self.unpacked_dir)
                result.append(rel_path)
        
        return result

    def get_metadata(self):
        """
        Get the original metadata of the wheel.
        
        Returns:
            The original metadata as a string
        """
        if self.unpacked_dir is None:
            self.unpack()
        
        return self.original_metadata

    def cleanup(self):
        """
        Clean up temporary directories created during unpacking.
        """
        if self.unpacked_dir is not None and self.unpacked_dir.parent.exists():
            shutil.rmtree(self.unpacked_dir.parent)
            self.unpacked_dir = None
            self.dist_info_dir = None

    def repackage(self, output_path=None):
        """
        Repackage the wheel with any changes made.
        
        Args:
            output_path: Output path for the new wheel file.
                         If None, overwrites the original wheel.
        
        Returns:
            Path to the new wheel file
        """
        from wheel.cli import pack
        
        if self.unpacked_dir is None:
            raise ValueError("Wheel must be unpacked before repackaging")
        
        if output_path is None:
            output_path = self.wheel_path
        else:
            output_path = Path(output_path)
        
        # Update RECORD file with new hash values
        self._update_record_file()
        
        # Use wheel.cli.pack to repackage
        pack.pack(str(self.unpacked_dir), str(output_path.parent), build_number=None)
        
        # Clean up temporary directories
        self.cleanup()

    def _update_record_file(self):
        """Update the RECORD file with correct hash values."""
        record_path = self.dist_info_dir / 'RECORD'
        if not record_path.exists():
            return
        
        record_data = []
        for line in open(record_path, 'r', encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
                
            parts = line.split(',')
            if len(parts) >= 3:
                filepath = parts[0]
                
                # Skip the RECORD file itself
                if filepath.endswith('RECORD'):
                    record_data.append((filepath, '', ''))
                    continue
                
                # Calculate new hash and size
                full_path = self.unpacked_dir / filepath
                if os.path.exists(full_path):
                    with open(full_path, 'rb') as f:
                        content = f.read()
                    sha256 = hashlib.sha256(content).hexdigest()
                    size = len(content)
                    record_data.append((filepath, f"sha256={sha256}", str(size)))
                else:
                    # Keep original entry if file doesn't exist
                    record_data.append((filepath, parts[1], parts[2] if len(parts) > 2 else ''))
            else:
                # Keep original malformed entry
                record_data.append(tuple(parts + [''] * (3 - len(parts))))
        
        # Write updated RECORD file
        with open(record_path, 'w', encoding='utf-8') as f:
            for filepath, hash_val, size in record_data:
                f.write(f"{filepath},{hash_val},{size}\n")
