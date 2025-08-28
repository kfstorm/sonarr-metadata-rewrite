"""Utility functions for handling .nfo/.NFO files with case sensitivity."""

from pathlib import Path


def is_nfo_file(file_path: Path) -> bool:
    """Check if a file is an NFO file (case-insensitive).
    
    Args:
        file_path: Path to the file to check
        
    Returns:
        True if the file has .nfo or .NFO extension, False otherwise
    """
    return file_path.suffix.lower() == ".nfo"


def find_nfo_files(directory: Path, recursive: bool = True) -> list[Path]:
    """Find all .nfo and .NFO files in a directory (case-insensitive).
    
    Args:
        directory: Directory to search in
        recursive: Whether to search recursively in subdirectories
        
    Returns:
        List of paths to all NFO files found
    """
    if not directory.exists():
        return []
    
    if recursive:
        # Use rglob to find all files, then filter by case-insensitive extension
        all_files = directory.rglob("*")
    else:
        # Use glob for non-recursive search
        all_files = directory.glob("*")
    
    # Filter files that have .nfo extension (case-insensitive)
    nfo_files = []
    for file_path in all_files:
        if file_path.is_file() and is_nfo_file(file_path):
            nfo_files.append(file_path)
    
    return nfo_files


def get_nfo_file_extensions() -> list[str]:
    """Get all possible NFO file extensions (case variations).
    
    Returns:
        List of NFO file extensions: ['.nfo', '.NFO']
    """
    return [".nfo", ".NFO"]