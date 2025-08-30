# Vulture whitelist for sonarr-metadata-rewrite project
# This file contains false positives that should be ignored by vulture

# Pydantic model_config is used by the framework
_.model_config

# Pydantic validators are used by the framework
_.parse_preferred_languages
_.validate_service_mode
_.cls

# Signal handler parameters are required by the interface
_.signum
_.frame


# Data class fields are accessed dynamically
_.description
_.file_modified
_.file_path
_.selected_language
_.series_id
_.translations_found

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

# TYPE_CHECKING imports for type annotations
ElementTree
