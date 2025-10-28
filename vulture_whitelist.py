# Vulture whitelist for sonarr-metadata-rewrite project
# This file contains false positives that should be ignored by vulture

# Pydantic model_config is used by the framework
_.model_config

# Pydantic validators are used by the framework
_.parse_preferred_languages
_.validate_service_mode
_.cls

# Pydantic settings customization is used by the framework
_.settings_customise_sources
_.env_settings

# Signal handler parameters are required by the interface
_.signum
_.frame


# Data class fields are accessed dynamically
_.description
_.file_modified
_.file_path
_.series_id
_.translated_content
_.iso_639_1
_.iso_3166_1
_.kind
_.selected_language
_.selected_file_path
_.message

# Model classes and functions that will be used in future implementation
ImageCandidate
ImageProcessResult
ImageProcessor
_.process
is_rewritable_image
find_rewritable_images
MediaFileHandler
_._handle_file_event

# Event handler methods are called by watchdog
_.on_created
_.on_modified


# Test mock attributes that vulture may not detect
_.return_value
_.side_effect

# Pytest fixtures with autouse=True are automatically used
patch_time_sleep
patch_retry_timeout
patch_fetch_with_retry
patch_image_download_retry

# TYPE_CHECKING imports for type annotations
ElementTree
