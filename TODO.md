# Sonarr Metadata Rewrite - Features

## Project Overview
Create a compatibility layer that monitors Sonarr-generated .nfo files and overwrites them with TMDB translations in desired languages, addressing [Sonarr Issue #269](https://github.com/Sonarr/Sonarr/issues/269).

## Core Features

### 🌍 Automatic Translation
- [x] **Monitor .nfo Files**: Automatically detect when Sonarr creates or updates metadata files
- [x] **Series Metadata Translation**: Translate TV show titles, descriptions, and other metadata
- [x] **Episode Metadata Translation**: Translate individual episode titles and descriptions
- [x] **Real-time Processing**: Translate files immediately after Sonarr writes them to minimize English metadata visibility

### 🗣️ Multi-language Support
- [x] **Multiple Preferred Languages**: Configure multiple target languages with priority order
- [x] **Priority-based Translation**: Try languages in order of preference until translation is found
- [x] **No Translation Fallback**: If none of the preferred languages are available, leave original metadata unchanged

### 💾 Backup & Recovery
- [x] **Original File Preservation**: Keep backups of original Sonarr-generated files
- [x] **Rollback Capability**: Ability to restore original English metadata if needed
- [x] **Safe File Operations**: Prevent data loss through atomic file operations

## Advanced Features

### ⚡ Performance & Efficiency
- [x] **Smart Caching**: Cache TMDB translations to minimize API calls and improve speed
- [ ] **Rate Limit Compliance**: Respect TMDB API rate limits
- [ ] **Skip Already Modified Files**: Track files we've already translated and skip re-processing when scanning or monitoring detects them again, preventing unnecessary API calls and processing cycles
- [x] **Batch Processing**: Efficiently handle large media libraries with hundreds/thousands of files
- [x] **Minimal Resource Usage**: Lightweight service that doesn't impact system performance

### 🔧 Configuration Management
- [x] **Minimal Configuration**: Work with just TMDB API key, monitoring directory, and preferred languages
- [x] **Flexible Setup**: Easy configuration of monitored directories and translation preferences
- [x] **Configuration Validation**: Clear error messages for invalid settings

### 🛡️ Reliability & Error Handling
- [x] **Sonarr Integration Protection**: Handle Sonarr's metadata refresh cycles without conflicts
- [x] **API Failure Recovery**: Continue operating gracefully when TMDB API is unavailable
- [x] **File System Resilience**: Handle concurrent file access and file system events safely
- [x] **Comprehensive Logging**: Detailed logging for troubleshooting and monitoring

## User Experience Features

### 🚀 Ease of Use
- [ ] **Simple Installation**: Easy setup process with clear documentation
- [ ] **Automatic Discovery**: Automatically find and monitor Sonarr media directories
- [ ] **Status Reporting**: Clear indication of translation progress and system status
- [x] **Command Line Interface**: Simple commands for starting service and checking status

### 🔍 Monitoring & Visibility
- [ ] **Translation Statistics**: Track how many files have been translated
- [ ] **Error Reporting**: Clear reporting of any issues or failures
- [ ] **Progress Tracking**: Show translation progress for large media libraries
- [ ] **Health Checks**: System health monitoring and diagnostics

### 🔗 Compatibility
- [ ] **Sonarr Compatibility**: Work seamlessly with existing Sonarr installations
- [ ] **Media Center Support**: Maintain compatibility with Kodi, Plex, Jellyfin, and other media centers
- [ ] **Cross-platform Support**: Work on Linux, Windows, and macOS
- [ ] **Docker Support**: Containerized deployment option

## Success Criteria

### Functional Requirements
- ✅ Successfully translates TV series metadata from English to target language
- ✅ Successfully translates episode metadata from English to target language
- ✅ Handles Sonarr metadata refresh cycles without data loss or conflicts
- ✅ Processes files quickly enough to be transparent to users (< 5 seconds per file)
- ✅ Supports multiple preferred languages with priority order

### Quality Requirements
- ✅ Maintains 100% compatibility with existing media center software
- ✅ Provides reliable error handling and recovery from failures
- ✅ Operates safely without corrupting or losing metadata files
- ✅ Scales to handle large media libraries (1000+ TV series)
- [ ] Respects TMDB API rate limits and terms of service

### User Experience Requirements
- ✅ Requires minimal configuration (TMDB API key, monitoring directory, and preferred languages)
- ✅ Provides clear status information and error messages
- ✅ Works invisibly in the background without user intervention
- ✅ Can be easily started, stopped, and configured by users
