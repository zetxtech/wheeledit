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

    @property
    def dist_info_dir(self):
        """
        Dynamically get the .dist-info directory path.
        
        Returns:
            Path to the .dist-info directory
        """
        if self.unpacked_dir is None:
            return None
            
        dist_info_dirs = list(self.unpacked_dir.glob('*.dist-info'))
        if not dist_info_dirs:
            raise ValueError("No .dist-info directory found in the wheel")
        return dist_info_dirs[0]

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
        
        return self.unpacked_dir

    def rename_package(self, new_name):
        """
        Rename the package.
        
        Args:
            new_name: New package name
        
        Returns:
            New package name if successful
            
        Raises:
            ValueError: If the new name is invalid or dist-info directory is not found
        """
        if not self.validate_package_name(new_name):
            raise ValueError(f"Invalid package name: '{new_name}'. Package names must contain only ASCII letters, numbers, period, underscore, and hyphen, and must start and end with a letter or number.")
        
        if self.unpacked_dir is None:
            self.unpack()
        
        # Get current dist_info_dir
        old_dist_info = self.dist_info_dir
        
        if not old_dist_info:
            raise ValueError("No .dist-info directory found in the wheel")
        
        version = ""
        # Get everything before .dist-info using Path.stem
        stem = Path(old_dist_info.name).stem
        if '-' in stem:
            # Get the version (everything after the last hyphen)
            version = f"-{stem.split('-')[-1]}"
        
        # Rename the .dist-info directory, preserving version
        new_dist_info_name = f"{new_name.replace('-', '_')}{version}.dist-info"
        new_dist_info_path = old_dist_info.parent / new_dist_info_name
        old_dist_info.rename(new_dist_info_path)
        
        # Update METADATA file
        metadata_path = new_dist_info_path / 'METADATA'
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata_content = f.read()
            
            # Update the Name field - keep original format in metadata
            metadata_content = re.sub(r'Name: .*', f'Name: {new_name}', metadata_content)
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                f.write(metadata_content)
        
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
        Get the metadata of the wheel.
        
        Returns:
            The metadata as a string
        """
        if self.unpacked_dir is None:
            self.unpack()
        
        metadata_path = self.dist_info_dir / 'METADATA'
        if metadata_path.exists():
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return f.read()
        return None

    def cleanup(self):
        """
        Clean up temporary directories created during unpacking.
        """
        if self.unpacked_dir is not None and self.unpacked_dir.parent.exists():
            shutil.rmtree(self.unpacked_dir.parent)
            self.unpacked_dir = None

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

    def validate_package_name(self, name):
        """
        Validate that a package name meets Python packaging standards.
        
        Args:
            name: The package name to validate
            
        Returns:
            bool: True if name is valid, False otherwise
        """
        # Check if name is empty
        if not name:
            return False
            
        # Name must only contain ASCII letters, numbers, period, underscore, and hyphen
        if not re.match(r'^[a-zA-Z0-9._-]+$', name):
            return False
            
        # Name must start and end with a letter or number
        if not (name[0].isalnum() and name[-1].isalnum()):
            return False
            
        return True
